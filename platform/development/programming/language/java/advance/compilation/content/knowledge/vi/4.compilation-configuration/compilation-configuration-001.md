# Chọn rõ tập nguồn và đường tìm mã nguồn khi biên dịch Java

## 1. Vì sao cần chọn nguồn một cách tường minh?

Một dự án Java thường có mã sản phẩm, kiểm thử, công cụ nội bộ, mã do generator tạo và thư viện bên ngoài. Chúng đều có thể chứa tệp `.java`, nhưng không phải tất cả đều thuộc cùng một lần biên dịch. Nếu chọn nhầm, mã kiểm thử có thể lọt vào sản phẩm, thiếu mã nguồn phụ thuộc hoặc vô tình dùng class cũ còn sót từ build trước.

Có hai câu hỏi độc lập:

1. **Tập nguồn được chọn (source files/source set):** những tệp `.java` nào phải được biên dịch trong pha này, chẳng hạn `main` trước rồi `test`?
2. **Đường tìm mã nguồn (source path):** nếu một kiểu được tham chiếu chưa có dưới dạng class đã biên dịch, compiler có thể tìm tệp `.java` tương ứng dưới source roots nào?

Một compiler còn cần đường tìm thư viện đã biên dịch (**classpath** hoặc **module path**) và nơi ghi kết quả (**output directory**). Các vai trò này cần được khai báo riêng.

~~~text
.java được chọn rõ ──────────────┐
                                │
Source path: tìm .java liên quan ├── javac ──► -d: .class
Classpath: tìm .class / JAR ─────┤
                                │
--release, -encoding, ... ───────┘
~~~

Mục tiêu của cấu hình rõ ràng là tái lập được cùng kết quả từ checkout sạch, chạy test sau main, không lẫn code test vào JAR và không phụ thuộc vào cách IDE tự đánh dấu thư mục.

## 2. Source root, source file, package và output

Xét cây dự án:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── demo/
│   │   │       ├── app/Main.java
│   │   │       └── lib/Formatter.java
│   │   └── resources/
│   └── test/
│       ├── java/
│       │   └── demo/test/FormatterSmokeTest.java
│       └── resources/
├── build/generated/sources/model/java/
└── out/
    ├── main/
    └── test/
~~~

- **Source root:** `src/main/java`, `src/test/java` hoặc một thư mục sinh mã. Đây là gốc để ánh xạ tên package tới đường dẫn tệp.
- **Source file:** `src/main/java/demo/lib/Formatter.java` là một compilation unit cụ thể.
- **Package:** `package demo.lib;` khai báo namespace; từ root `src/main/java`, tệp nằm tại `demo/lib/Formatter.java`.
- **Output:** `out/main/demo/lib/Formatter.class` là bytecode sau khi compile, không phải Java source.
- **Resources:** tệp trong `src/main/resources` và `src/test/resources` được xử lý/copy theo build tool; `javac` không tự copy tài nguyên chỉ vì đã đưa thư mục vào source path.

Một source root có thể chứa nhiều package. Cùng một package đôi khi có class nằm ở nhiều roots nếu build cấu hình như vậy; tuy nhiên, không nên khai báo **hai định nghĩa cùng fully qualified name** ở hai nơi, nhất là giữa nguồn viết tay và nguồn sinh.

Đường tới source root phải dừng **trước** chuỗi thư mục package. Để tìm `demo.lib.Formatter`, đưa `src/main/java` vào source path, không đưa `src/main/java/demo/lib`.

## 3. Các tùy chọn của javac và ý nghĩa chính xác

| Cơ chế | Tùy chọn | Tác dụng |
| --- | --- | --- |
| Chọn tệp cần biên dịch | Đối số `Some.java` hoặc `@argfile` | Nêu những compilation units ban đầu |
| Tìm Java source phụ thuộc | `--source-path`, `-sourcepath` | Tra cứu thêm tệp nguồn theo package khi cần |
| Tìm class/JAR trên classpath | `--class-path`, `-classpath`, `-cp` | Tra cứu mã đã biên dịch và thư viện |
| Đặt output binary | `-d` | Ghi các tệp `.class` |
| Chọn ngôn ngữ/API nền tảng | `--release 17` | Hạn chế cú pháp, bytecode và Java SE API theo phiên bản |
| Chọn encoding đầu vào | `-encoding UTF-8` | Giải mã tệp nguồn |
| Module source roots | `--module-source-path` | Tìm nguồn của nhiều named modules |
| Module dependencies | `--module-path`, `-p` | Tìm named modules được dùng khi compile/run |
| Output generated source của processor | `-s` | Ghi Java source do annotation processor tạo |
| Tìm annotation processors | `--processor-path` | Tìm công cụ xử lý annotation, khác classpath chạy ứng dụng |

Trong ví dụ không dùng named modules, một lệnh mẫu có thể là:

~~~text
javac --release 17 -encoding UTF-8 --source-path src/main/java -cp lib/api.jar -d out/main src/main/java/demo/app/Main.java
~~~

Đây là mẫu cú pháp; `lib/api.jar` chỉ có ý nghĩa nếu dự án thực sự có dependency đó. Ví dụ chạy được ở phần tiếp theo không yêu cầu JAR ngoài.

**Lưu ý then chốt:** `--source-path src/main/java` không yêu cầu biên dịch *mọi* tệp dưới thư mục đó. Nó chỉ cung cấp vị trí để compiler tìm các tệp nguồn phụ thuộc. Ngược lại, nếu liệt kê trực tiếp một danh sách đầy đủ các tệp `.java`, compiler đã có các compilation units ban đầu và có thể không cần tra thêm source path.

Nếu không khai báo source path, `javac` có thể tìm source files trên user classpath. Việc vô tình để đường chứa `.java` trong classpath dễ tạo kết quả khó dự đoán; hãy chọn source roots và binary dependencies tường minh.

## 4. Ví dụ Java 17+ chạy được từ đầu đến cuối

Tạo ba file chính xác theo cây thư mục mục 2. Ví dụ cố tình không dùng JUnit để có thể kiểm tra chỉ bằng JDK.

### 4.1. `src/main/java/demo/lib/Formatter.java`

~~~java
package demo.lib;

public final class Formatter {
    private Formatter() {}

    public static String wrap(String text) {
        return "[" + text.trim() + "]";
    }
}
~~~

Đây là mã sản phẩm. Tên đầy đủ của class là `demo.lib.Formatter`.

### 4.2. `src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.lib.Formatter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Formatter.wrap(" Java "));
    }
}
~~~

`Main` import class ở package khác, nên lần biên dịch phải nhìn thấy `Formatter` từ danh sách nguồn, source path hoặc binary dependency đã compile.

### 4.3. `src/test/java/demo/test/FormatterSmokeTest.java`

~~~java
package demo.test;

import demo.lib.Formatter;

public final class FormatterSmokeTest {
    public static void main(String[] args) {
        String actual = Formatter.wrap(" Java ");
        if (!"[Java]".equals(actual)) {
            throw new AssertionError("Expected [Java], got " + actual);
        }
        System.out.println("TEST OK");
    }
}
~~~

Đây là **smoke test gọi qua `main`**, không phải test JUnit được test runner phát hiện tự động. Sử dụng `AssertionError` trực tiếp nên không cần JVM option `-ea`.

### 4.4. Cách A: nêu rõ tất cả source files của main

Từ thư mục `project/`, chạy trong Bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p out/main out/test
javac --release 17 -encoding UTF-8 -d out/main src/main/java/demo/lib/Formatter.java src/main/java/demo/app/Main.java
java -cp out/main demo.app.Main
~~~

Stdout:

~~~text
[Java]
~~~

Hai tệp `.java` được liệt kê rõ. Compiler ghi `out/main/demo/lib/Formatter.class` và `out/main/demo/app/Main.class`. Vì đã cấp đầy đủ source files cần thiết, trường hợp này không cần `--source-path`.

Đây là mô hình dễ quan sát nhất về **tập nguồn được chọn**. Trong dự án lớn, công cụ build sẽ thu thập toàn bộ source files của source set, thay vì yêu cầu người dùng gõ hàng nghìn đường dẫn.

### 4.5. Cách B: chỉ nêu Main.java, chỉ rõ nơi tìm source phụ thuộc

Dùng một thư mục output khác để quan sát riêng:

~~~bash
mkdir -p out/by-sourcepath
javac --release 17 -encoding UTF-8 --source-path src/main/java -d out/by-sourcepath src/main/java/demo/app/Main.java
java -cp out/by-sourcepath demo.app.Main
~~~

Stdout:

~~~text
[Java]
~~~

Danh sách source files chỉ có `Main.java`. Khi thấy `Main` dùng `demo.lib.Formatter`, compiler có thể tìm `src/main/java/demo/lib/Formatter.java` từ source path và biên dịch gián tiếp file đó. Vì thế output vẫn có class cần để chạy chương trình.

**Không suy ra rằng mọi file trong `src/main/java` đã được compile.** Nếu thêm một `Unused.java` không được class nào tham chiếu, việc chỉ compile `Main.java` với source path không buộc compiler phát hiện và biên dịch `Unused.java`. Đối với một bản build sản phẩm hoàn chỉnh, cần nguồn đầu vào được chọn đầy đủ, hoặc để build tool thực hiện nhiệm vụ này.

Nếu một nguồn vừa tồn tại dưới dạng `.java` vừa có `.class` ở nơi compiler tìm, lựa chọn còn có thể liên quan timestamp và tùy chọn compiler. Không dựa vào class cũ để làm build “qua được”; kiểm thử trên output sạch.

### 4.6. Compile test bằng class main đã biên dịch

Tiếp tục với `out/main` của cách A:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/main -d out/test src/test/java/demo/test/FormatterSmokeTest.java
java -cp out/main:out/test demo.test.FormatterSmokeTest
~~~

Stdout:

~~~text
TEST OK
~~~

Lần compile test có đầu vào là **test source**; `-cp out/main` chỉ tới class sản phẩm đã biên dịch. `out/test` chỉ chứa class kiểm thử. Khi chạy test, runtime classpath phải gồm cả main và test output.

Trên Windows, dấu phân cách danh sách đường dẫn là `;` thay vì `:`. Ví dụ PowerShell:

~~~powershell
java -cp 'out/main;out/test' demo.test.FormatterSmokeTest
~~~

Trong PowerShell, đặt tham số `-cp` có dấu chấm phẩy vào chuỗi trích dẫn để shell không coi đó là dấu kết thúc câu lệnh. Có thể dùng `New-Item -ItemType Directory -Force out/main, out/test` để tạo thư mục thay cho `mkdir -p` của Bash.

## 5. Khi nào biên dịch đủ tập nguồn, khi nào dùng source lookup?

Hãy phân biệt hai mục tiêu:

**Build toàn bộ thư viện/ứng dụng:** mọi Java file thuộc source set phải được xem xét, kể cả class chưa có caller trong cùng build. Việc dùng `--source-path` để compile chỉ một entry point là chưa đủ để chứng minh tất cả source files hợp lệ.

**Biên dịch một chương trình nhỏ hoặc một file đang thử:** có thể đưa một số tệp cụ thể và `--source-path` để compiler tìm các nguồn phụ thuộc. Kết quả phù hợp với mục tiêu hẹp ấy.

Với command line, có thể lưu danh sách nguồn vào **argument file** khi tên tệp quá nhiều. Ví dụ tệp văn bản `main-sources.args` chứa:

~~~text
src/main/java/demo/lib/Formatter.java
src/main/java/demo/app/Main.java
~~~

Sau đó chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d out/main @main-sources.args
~~~

File `@argfile` chứa đối số cho compiler và có thể được generator/build script tạo từ danh sách source files đã kiểm soát. Không để file danh sách chứa cả test file, hoặc để file có các đường dẫn phụ thuộc thư mục làm việc khác với dự kiến. Đối số file có cách quote/escape riêng khi tên đường dẫn chứa khoảng trắng; trong dự án lớn nên để build tool xử lý.

Ngoài ra, `javac -implicit:none` chỉ điều khiển **việc ghi class file của những nguồn được phát hiện gián tiếp**. Nó không biến `--source-path` thành một cơ chế “cấm đọc nguồn khác”, và không thay thế việc chọn nguồn đầu vào đầy đủ.

## 6. Nhiều source roots: mã viết tay và mã được sinh

Một source set main có thể có nhiều nguồn gốc:

~~~text
src/main/java/                             # mã người viết
build/generated/sources/models/java/       # mã generator tạo cho main
src/test/java/                             # mã test, không thuộc main
build/generated/sources/test-fixtures/java/ # mã sinh cho test
~~~

Nếu một class main phụ thuộc class đã được sinh dưới `build/generated/sources/models/java`, có thể khai báo nhiều source roots. Ví dụ lệnh trên Bash:

~~~bash
javac --release 17 --source-path 'src/main/java:build/generated/sources/models/java' -d out/main src/main/java/demo/app/Main.java
~~~

Đây là **ví dụ cấu hình tổng quát**: với chương trình mẫu mục 4, `Main` không phụ thuộc generated source nên không cần thư mục đó. Với dự án thật, phải bảo đảm generator đã chạy và tạo file đúng trước khi compile.

Nguyên tắc lựa chọn:

1. Chỉ thêm mã sinh dành cho **main** vào main source roots; mã sinh dành cho test thuộc test source roots.
2. Đừng khai báo test directory là source path của production để giải quyết lỗi import; sửa thiết kế dependency nếu main đang import code test.
3. Nếu generator viết cùng một fully qualified class mà source main đã có, có thể gây lỗi duplicate class hoặc lựa chọn sai nguồn; phải chỉ định một owner rõ.
4. Đừng để generator ghi vào `src/main/java` nếu không có quyết định quản lý source sinh theo Git rất rõ. Output build riêng dễ làm sạch và tái tạo hơn.
5. Source root cho biết **đọc ở đâu**, chưa đủ cho biết **khi nào sinh mã**. Build tool phải quản lý task dependency từ generator tới compiler.

Nếu có JAR, đặt nó vào classpath, không vào source path. `--source-path` dành cho mã nguồn; `-cp` dành cho class/JAR được compiler tham chiếu.

## 7. Phân biệt source path, compile classpath, runtime classpath

| Pha | Tập nguồn đã chọn | Nơi tìm phụ thuộc | Nơi ghi/chạy |
| --- | --- | --- | --- |
| Compile main | Java files main | main source roots khi cần; compile libraries trên classpath | output `out/main` |
| Compile test | Java files test | compiled main, test libraries và test source roots khi cần | output `out/test` |
| Run main | Không biên dịch nguồn (theo chế độ class thông thường) | runtime classpath main và runtime dependencies | `java -cp out/main demo.app.Main` |
| Run test | Class test đã compile | main + test classes và test runtime libraries | `java -cp out/main:out/test ...` |

Một số lỗi dễ nhầm:

- `javac -cp out/main -d out/test src/test/java/demo/test/FormatterSmokeTest.java` là đúng khi main đã được biên dịch.
- `javac -d out/test src/test/java/demo/test/FormatterSmokeTest.java` trên classpath sạch có thể lỗi vì không thấy `demo.lib.Formatter`.
- `java -cp src/main/java demo.app.Main` không tìm class đã ghi trong `out/main`; `-cp` của Java runtime trỏ tới class directories/JAR, không trỏ source root.
- Dùng `src/test/java` làm một source root của `main` có thể khiến class test hoặc các dependency kiểm thử lọt vào build sản phẩm.
- Chạy `javac -d out/main ...` nhưng không phân biệt output của test làm khó kiểm tra class nào thuộc artifact.

Khi runtime thiếu class dù compile thành công, cần kiểm tra **runtime** classpath hoặc module path; thêm source path vào lệnh `java` không giải quyết vấn đề class đã biên dịch.

## 8. Chọn source sets trong Gradle

Plugin `java` của Gradle đã có hai source sets mặc định là `main` và `test`. Mặc định chúng dùng các thư mục `src/main/java`, `src/main/resources`, `src/test/java`, `src/test/resources`. Có thể đặt tường minh trong `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            setSrcDirs(['src/main/java'])
        }
        resources {
            setSrcDirs(['src/main/resources'])
        }
    }
    test {
        java {
            setSrcDirs(['src/test/java'])
        }
        resources {
            setSrcDirs(['src/test/resources'])
        }
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Đoạn `setSrcDirs` **đặt lại** danh sách root của từng tập nguồn; nó hữu ích khi muốn loại bỏ root không mong muốn. Nếu cần **bổ sung** một root, dùng `srcDir(...)` hoặc `srcDirs(...)` thích hợp thay vì vô ý thay thế danh sách đang có. Với đúng cấu trúc mặc định, không bắt buộc viết phần `sourceSets`; ví dụ chỉ làm rõ ý định.

Các tác vụ Gradle liên quan:

- `compileJava` biên dịch các file main được chọn và ghi main classes.
- `compileTestJava` biên dịch các file test bằng main output và dependency test trên compile classpath phù hợp.
- `processResources` và `processTestResources` xử lý resources riêng.
- `test` chạy test do framework/runner cấu hình; smoke test có phương thức `main` tại mục 4 sẽ không tự được nhận thành JUnit test.

Khi repository có Gradle Wrapper, dùng:

~~~bash
./gradlew compileJava
./gradlew compileTestJava
~~~

Trên Windows chạy `gradlew.bat` thay vì `./gradlew`.

Với generated sources, cấu hình đúng phải nối **task tạo nguồn** với source set. Nếu một tác vụ `generateModels` đã được định nghĩa với thư mục output hợp lệ, dạng cấu hình minh họa có thể là:

~~~groovy
sourceSets {
    main {
        java.srcDir(tasks.named('generateModels'))
    }
}
~~~

Đoạn này **không độc lập chạy được** nếu chưa định nghĩa task `generateModels`. Ý nghĩa là dùng output của producer task làm source directory, giúp Gradle suy ra dependency; tránh chỉ đưa vào một đường dẫn `build/generated/...` cố định rồi hy vọng task sinh mã đã chạy. Nếu generated code chỉ phục vụ test, nối với `sourceSets.test`.

Cần thêm source set như integration tests thì nên cấu hình riêng sources, output, dependency classpath, runtime classpath và task thực thi; không nhập integration test vào production source set cho tiện.

## 9. Quy ước tương đương trong Maven

Maven dùng những root mặc định tương ứng: `src/main/java` và `src/test/java`, tài nguyên ở `src/main/resources` và `src/test/resources`, class output thường ở `target/classes` và `target/test-classes`.

Khi phải đổi root, `pom.xml` có thể chỉ định:

~~~xml
<build>
    <sourceDirectory>src/main/java</sourceDirectory>
    <testSourceDirectory>src/test/java</testSourceDirectory>
</build>
~~~

Đây là fragment **bên trong** phần tử `project` của POM, không phải một POM độc lập. Hai giá trị trên là mặc định nên thông thường không cần khai báo.

Mã sinh trong Maven nên được plugin/lifecycle liên kết với pha phù hợp (`generate-sources` hoặc `generate-test-sources` khi thích hợp), đồng thời khai báo source root sinh cho compile hay test-compile tương ứng. Chỉ sửa đường dẫn trong IDE không làm build Maven tự biết generator đã tạo mã. Dependency chỉ phục vụ test cần scope test phù hợp.

## 10. Source path của named modules (JPMS) là trường hợp khác

Khi có nhiều Java modules khai báo `module-info.java`, `--module-source-path` thay cho mô hình tra cứu nguồn đa module, còn `--module-path` là đường tìm **module dependencies đã biên dịch/đóng gói**. `-m` hoặc `--module` chọn module cần compile.

Ví dụ **độc lập** với mục 4:

~~~text
modulesrc/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Tệp `modulesrc/com.example.app/module-info.java`:

~~~java
module com.example.app {
}
~~~

Tệp `modulesrc/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("MODULE OK");
    }
}
~~~

Biên dịch và chạy:

~~~bash
mkdir -p out/modules
javac --release 17 --module-source-path modulesrc -d out/modules -m com.example.app
java --module-path out/modules -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
MODULE OK
~~~

Trong cấu trúc này, `modulesrc` chứa thư mục con theo tên module, khác cách dùng source root đơn lẻ của dự án classpath. Không thay `--module-source-path` bằng `--source-path` theo cảm tính, và không nhầm `--module-path` với thư mục chứa `.java`.

## 11. Kiểm tra đường tìm nguồn thực tế và lỗi thường gặp

Lệnh `javac -verbose` có thể in thông tin về file nguồn compiler đọc, class/JAR được tải và output. Ví dụ:

~~~bash
javac -verbose --release 17 -encoding UTF-8 --source-path src/main/java -d out/by-sourcepath src/main/java/demo/app/Main.java
~~~

Log `-verbose` thay đổi theo phiên bản JDK, hệ điều hành và project; không coi log như một chuỗi stdout cố định để so khớp. Hãy nhìn **đường dẫn nguồn được đọc** để phát hiện compiler lấy file từ root sai.

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol Formatter` | Thiếu `Formatter.java` trong nguồn được chọn, source path hoặc classpath | Kiểm tra import, tên package, source root và binary dependencies |
| Một file độc lập không tạo `.class` | File không nằm trong explicit source list và không được tham chiếu | Bổ sung file vào source set của nhiệm vụ build |
| Tìm thấy file trên ổ đĩa nhưng compiler không resolve package | Source path đi quá sâu vào cây package | Trỏ `--source-path` tới thư mục trước package tree |
| Test compile không thấy class main | Thiếu main output ở test compile classpath | Compile main trước, đưa output main vào classpath của test |
| Main compile đòi JUnit | Test source hoặc test dependencies bị trộn vào main | Tách source sets và dependency scopes |
| IDE chạy được nhưng CI lỗi | IDE từng đánh dấu generated root hoặc dùng class cũ | Chạy build sạch qua command line, khai báo generator dependency |
| Có duplicate class | Cùng fully qualified name từ mã chính/mã sinh/JAR | Chọn một nguồn sở hữu và loại bản trùng |
| Chạy ứng dụng lỗi `ClassNotFoundException` | Runtime classpath trỏ sai output | Kiểm tra fully qualified main class và class/JAR directories |
| Windows báo lỗi dù Unix chạy được | Dùng dấu `:` thay cho `;` trong path list | Dùng separator đúng cho hệ điều hành, quote path |
| Java module không được tìm | Nhầm module source path với module path | Kiểm tra cây module và tùy chọn `--module-source-path`/`--module-path` |

Bản build đáng tin cậy phải trả lời được: những file nào thuộc main, những file nào thuộc test, compiler có thể tìm thêm nguồn ở những root nào, dependency binary nào hiện diện, generator chạy trước hay sau, và `.class` ghi ở đâu. Hãy kiểm tra sau `clean` hoặc dùng output mới để tránh file cũ che khuất cấu hình thiếu.

## 12. Bài thực hành tự kiểm chứng

1. Biên dịch hai file main từ **danh sách tường minh** ở mục 4.4 và chạy `demo.app.Main`; xác nhận stdout đúng `[Java]`.
2. Dùng cách **source path** ở mục 4.5, chỉ nêu `Main.java`; xác nhận compiler vẫn tìm được `Formatter`.
3. Tạo thêm `src/main/java/demo/lib/Unused.java` độc lập, không được class nào import, chẳng hạn `package demo.lib; public class Unused {}`. Biên dịch chỉ `Main.java` với source path; quan sát `Unused.class` không tự xuất hiện chỉ vì nó nằm trong root. Thêm `Unused.java` vào danh sách explicit sources để nó được biên dịch.
4. Biên dịch test theo mục 4.6, rồi thử bỏ `-cp out/main` trên một classpath sạch để quan sát lỗi phụ thuộc. Khôi phục classpath và xác nhận `TEST OK`.
5. Nếu dùng Gradle, kiểm tra `main` và `test` source roots; build sạch bằng wrapper và bảo đảm chỉ main classes/resources thuộc artifact sản phẩm.

Sau các bước này, khác biệt giữa **tệp được yêu cầu biên dịch**, **thư mục cho phép tìm tệp nguồn**, **classpath của class đã biên dịch** và **đường ghi output** sẽ thể hiện bằng kết quả quan sát được.