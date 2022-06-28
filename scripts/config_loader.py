

def loadConfig(fp):
    with open(fp,'r') as file:
        lines = file.read().split('\n')
    lines = [x.strip() for x in lines if x]
    
    output = {}

    for line in lines:
        line_content = line.split("#",1)[0]
        if not line_content:
            continue
        
        try:
            before, after = line_content.split("=",1)
        except:
            continue

        before = before.strip()
        after = after.strip()

        output[before] = after
    
    return output