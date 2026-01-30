fn main() {
    cc::Build::new()
        .file("daisy_module.c")
        .compile("daisy_module");
}


