# javac --patch-module trong build hoặc test

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích `--patch-module` dùng để làm gì khi biên dịch một named module.
- Phân biệt `--patch-module`, `--module-path` và `--class-path`.
- Biên dịch test source như một phần của module cần kiểm thử.
- Cho phép test truy cập package-private code trong cùng package mà không phải export package nội bộ ra API công khai.
- Cấu hình các compiler argument cần thiết trong lệnh `javac` hoặc Gradle.
- Nhận biết vì sao cần patch module cả ở thời điểm chạy test.

## 1. Vấn đề khi kiểm thử named module

Giả sử một module chỉ export package API:

~~~java
module com.example.calc {
    exports com.example.calc.api;
}
~~~

Trong module có một package nội bộ:

~~~java
package com.example.calc.internal;

final class Calculator {

    int add(int left, int right) {
        return left + right;
    }
}
~~~

`Calculator` có access modifier mặc định nên chỉ code trong cùng package mới truy cập được. Package `com.example.calc.internal` cũng không được export ra module khác.

Đây là một lựa chọn đóng gói hợp lý: ứng dụng bên ngoài dùng API công khai, còn implementation nội bộ được giữ kín.

Tuy nhiên, test cần kiểm tra trực tiếp `Calculator`, bao gồm các hành vi package-private. Nếu test được biên dịch như code của một module riêng hoặc nằm trong unnamed module trên classpath, nó không tự động có quyền truy cập như một class cùng package và cùng module.

`javac --patch-module` giải quyết trường hợp này bằng cách đưa source hoặc class bổ sung vào một named module đã tồn tại trong lúc biên dịch.

## 2. Cú pháp và ý nghĩa của --patch-module

Cú pháp tổng quát:

~~~text
javac --patch-module <module>=<path>[<path-separator><path>...]
~~~

Ví dụ:

~~~bash
javac --patch-module com.example.calc=src/test/java ...
~~~

Ý nghĩa:

- `com.example.calc` là tên module cần được patch.
- `src/test/java` là thư mục chứa source test được biên dịch như một phần của module đó.
- Có thể truyền nhiều đường dẫn, ngăn cách bằng path separator của hệ điều hành.
- Với Windows, path separator là dấu chấm phẩy (`;`); với Linux/macOS, path separator là dấu hai chấm (`:`).

Khi dùng `--patch-module`, compiler xem các source được patch là thành viên của module đích. Vì thế, test class có thể nằm trong package nội bộ của module và truy cập các thành viên package-private trong cùng package.

`--patch-module` không tạo một module mới. Module đích phải được xác định trong module graph của lần biên dịch. Option này bổ sung hoặc thay thế nội dung của module theo các đường dẫn được chỉ định.

### 2.1. Phân biệt ba loại đường dẫn

| Option | Mục đích |
|---|---|
| `--module-path` | Tìm các named module và dependency của chúng |
| `--class-path` / `-cp` | Tìm class thuộc unnamed module |
| `--patch-module` | Bổ sung source/class vào một named module cụ thể |

Ví dụ, `--module-path build/mods` giúp compiler tìm module `com.example.calc`; `--patch-module com.example.calc=src/test/java` đưa test source vào module đó; `-cp libs/junit-platform-console-standalone.jar` cung cấp thư viện JUnit trên classpath.

Ba option có vai trò khác nhau và có thể cần xuất hiện cùng một lệnh.

## 3. Ví dụ cấu trúc project

Giả sử project có cấu trúc:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/
│   │       ├── module-info.java
│   │       └── com/example/calc/
│   │           ├── api/CalculatorService.java
│   │           └── internal/Calculator.java
│   └── test/
│       └── java/
│           └── com/example/calc/
│               └── internal/CalculatorTest.java
├── libs/
│   └── junit-platform-console-standalone.jar
└── build/
~~~

Module descriptor:

~~~java
module com.example.calc {
    exports com.example.calc.api;
}
~~~

Test nằm trong đúng package của class cần kiểm tra:

~~~java
package com.example.calc.internal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        assertEquals(5, calculator.add(2, 3));
    }
}
~~~

`CalculatorTest` không cần được export. Khi được patch vào `com.example.calc`, test class và `Calculator` thuộc cùng module và cùng package `com.example.calc.internal`.

## 4. Biên dịch main module trước

Trước tiên, biên dịch source chính thành một exploded module:

~~~bash
javac -d build/mods/com.example.calc \
    src/main/java/module-info.java \
    src/main/java/com/example/calc/api/CalculatorService.java \
    src/main/java/com/example/calc/internal/Calculator.java
~~~

Sau lệnh này, thư mục output có dạng:

~~~text
build/mods/
└── com.example.calc/
    ├── module-info.class
    └── com/example/calc/
        ├── api/CalculatorService.class
        └── internal/Calculator.class
~~~

Đường dẫn `build/mods` là module path root. Bên trong nó có exploded module `com.example.calc`.

## 5. Biên dịch test bằng javac --patch-module

Nếu JUnit được đặt trên classpath, có thể biên dịch test như sau:

~~~bash
javac \
    --module-path build/mods \
    --patch-module com.example.calc=src/test/java \
    --add-reads com.example.calc=ALL-UNNAMED \
    -cp libs/junit-platform-console-standalone.jar \
    -d build/test-classes \
    src/test/java/com/example/calc/internal/CalculatorTest.java
~~~

Giải thích từng option:

1. `--module-path build/mods` giúp compiler tìm named module `com.example.calc`.
2. `--patch-module com.example.calc=src/test/java` đưa test source vào module `com.example.calc` trong lần biên dịch này.
3. `--add-reads com.example.calc=ALL-UNNAMED` cho phép module đích đọc các type trên classpath, bao gồm JUnit.
4. `-cp` cung cấp JUnit API mà test source import.
5. `-d build/test-classes` đặt test class đã biên dịch vào một output directory riêng.
6. Đường dẫn cuối cùng là source file được biên dịch.

`ALL-UNNAMED` là mục tiêu readability dành cho các class thuộc unnamed module. Nếu test framework được đặt trên module path và có tên module, hãy dùng tên module tương ứng thay cho `ALL-UNNAMED`.

Điểm quan trọng: test class được biên dịch như một phần của `com.example.calc`, dù file `.class` được ghi vào `build/test-classes`. Vì vậy, nó có thể truy cập `Calculator` package-private trong cùng package.

## 6. Patch module khi chạy test

`--patch-module` trong lệnh `javac` chỉ có hiệu lực cho lần biên dịch đó. Nó không tự động làm test class trở thành thành viên của module khi chạy JVM.

Khi chạy test, cần patch thư mục chứa test class vào cùng module:

~~~bash
java \
    --module-path build/mods \
    --patch-module com.example.calc=build/test-classes \
    --add-reads com.example.calc=ALL-UNNAMED \
    --add-opens com.example.calc/com.example.calc.internal=ALL-UNNAMED \
    -cp libs/junit-platform-console-standalone.jar \
    org.junit.platform.console.ConsoleLauncher execute \
    --select-class com.example.calc.internal.CalculatorTest
~~~

Ở lệnh runtime:

- `--patch-module` đưa test class đã biên dịch vào module đích.
- `--add-reads` cho module đích đọc JUnit nằm trên classpath.
- `--add-opens` mở package nội bộ cho code trên classpath để framework test có thể truy cập bằng reflection khi cần.
- `--select-class` yêu cầu JUnit chạy test class cụ thể.

`--add-opens` phục vụ truy cập reflective ở runtime. Nó không thay thế `--add-reads` khi compiler cần đọc type của JUnit. Nếu test framework nằm trong named module, thay `ALL-UNNAMED` bằng module name phù hợp và cấu hình các quyền cần thiết theo module đó.

## 7. Cấu hình trong Gradle

Với Gradle Java Plugin, có thể truyền compiler arguments vào `compileTestJava`. Ví dụ sau giả định module chính là `com.example.calc`, test dùng JUnit trên classpath và Gradle đã nhận diện main output là named module:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}

tasks.named('compileTestJava', JavaCompile) {
    options.compilerArgs.addAll([
        '--patch-module',
        'com.example.calc=' + sourceSets.test.java.srcDirs.asPath,
        '--add-reads',
        'com.example.calc=ALL-UNNAMED'
    ])
}
~~~

Ở đây:

- `sourceSets.test.java.srcDirs.asPath` lấy tất cả test source roots và nối bằng path separator phù hợp với hệ điều hành.
- `compileTestJava` vẫn dùng dependency configuration của Gradle để tìm JUnit.
- `--patch-module` điều chỉnh module membership của test source khi compiler xử lý chúng.

Cần cấu hình cả runtime của task test để test classes được patch vào module khi JVM khởi chạy:

~~~groovy
tasks.named('test', Test) {
    jvmArgs(
        '--patch-module',
        'com.example.calc=' + sourceSets.test.output.classesDirs.asPath,
        '--add-reads',
        'com.example.calc=ALL-UNNAMED',
        '--add-opens',
        'com.example.calc/com.example.calc.internal=ALL-UNNAMED'
    )
}
~~~

Các đường dẫn output trong ví dụ là cấu hình minh họa cho một project đơn giản. Nếu build có nhiều source set, nhiều output directory, custom test task hoặc JUnit được chạy trên module path, hãy điều chỉnh module name và đường dẫn theo cấu hình thực tế. Cũng cần kiểm tra test output không bị nạp đồng thời theo hai cách gây xung đột giữa module path và classpath.

## 8. Khi nào nên dùng --patch-module?

Các trường hợp thường gặp:

- Test cần truy cập package-private class hoặc method trong module.
- Test cần đặt trong cùng package với implementation nhưng package đó không được export.
- Build có test source riêng, cần biên dịch test như phần mở rộng của module chính.
- Cần bổ sung class/resource để thử nghiệm module trong một lần chạy cụ thể.

Không nên dùng `--patch-module` như cách thay thế thiết kế API. Nếu một package cần được ứng dụng bên ngoài sử dụng thường xuyên, hãy cân nhắc thiết kế API công khai phù hợp. Nếu chỉ test nội bộ cần truy cập implementation, patch module là một cơ chế kiểm thử có mục tiêu rõ ràng.

Cũng cần phân biệt `--patch-module` với `--add-exports`. `--add-exports` thay đổi quyền truy cập package ở ranh giới module; `--patch-module` đưa nội dung vào chính module đích. Với test nằm trong cùng package và cùng module, patch module thường phù hợp hơn việc export package nội bộ chỉ để test có thể truy cập.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `module not found` | Module đích không được tìm thấy trên module path | Kiểm tra `--module-path` và tên module |
| `package ... is not visible` khi import JUnit | Module đích chưa đọc unnamed module hoặc module JUnit | Bổ sung `--add-reads` đúng mục tiêu |
| Test không truy cập được package-private member | Test chưa được patch vào đúng module hoặc package | Kiểm tra module name và package declaration |
| Test compile được nhưng runtime không tìm thấy class | Chỉ patch ở `javac`, chưa patch khi chạy JVM | Thêm runtime `--patch-module` trỏ tới test output |
| Framework không truy cập được test bằng reflection | Package chưa được mở cho module chứa framework | Dùng `--add-opens` phù hợp ở runtime |
| Provider hoặc class bị tìm thấy khác dự kiến | Patch path hoặc module path chứa nhiều bản class | Kiểm tra đường dẫn và thứ tự nạp module |

Khi chẩn đoán, hãy kiểm tra command line thực tế mà build tool gửi cho compiler và JVM. Cấu hình Gradle/Maven có thể thêm module path hoặc classpath tự động, vì vậy chỉ nhìn vào một đoạn `build.gradle` chưa chắc đã phản ánh toàn bộ lệnh thực thi.

## 10. Tóm tắt

`javac --patch-module` cho phép biên dịch source bổ sung như một phần của named module đã tồn tại. Trong kiểm thử modular Java, kỹ thuật này giúp test nằm cùng module và package với implementation, nhờ đó có thể kiểm tra package-private code mà không phải export package nội bộ.

Một cấu hình test modular thường cần ba việc: đưa module chính lên `--module-path`, patch test source vào module bằng `--patch-module`, và cấu hình readability tới thư viện test bằng `--add-reads` nếu thư viện nằm trên classpath. Khi chạy test, patch thư mục test output vào module lần nữa và mở package cho framework nếu nó cần reflection.

Tài liệu tham khảo:

- [javac — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [java launcher — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
