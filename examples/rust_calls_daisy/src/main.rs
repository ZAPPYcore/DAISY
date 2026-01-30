extern "C" {
    fn daisy_exported() -> i64;
}

fn main() {
    let value = unsafe { daisy_exported() };
    println!("daisy_exported -> {}", value);
}


