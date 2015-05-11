if (System != null) {
    System.getProperties().each { k, v ->
        println "[ System ]:   ${k}: ${v}"
    }
} else {
    println "[ System ] is null"
}

if (this.hasProperty("build") && build != null) {
    build.properties.each { k, v ->
        println "[ build ]:    ${k}: ${v}"
    }
} else {
    println "[ build ] is null"
}

if (this.hasProperty("env") && env != null) {
    env.each { k, v ->
        println "[ env ]:      ${k}: ${v}"
    }
} else {
    println "[ env ] is null"
}

if (this.hasProperty("params") && params != null) {
    params.each { k, v ->
        println "[ params ]:   ${k}: ${v}"
    }
} else {
    println "[ params ] is null"
}

if (this.hasProperty("upstream") && upstream != null) {
    upstream.properties.each { k, v ->
        println "[ upstream ]: ${k}: ${v}"
    }
} else {
    println "[ upstream ] is null"
}
