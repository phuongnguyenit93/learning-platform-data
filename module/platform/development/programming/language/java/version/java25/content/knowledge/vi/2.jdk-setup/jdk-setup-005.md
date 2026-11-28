# Chạy tệp nguồn, biên dịch lớp và đóng gói chương trình Java 25

## 1. Mục tiêu và phạm vi bài học

Trong **JAVA_VERSION_JAVA25**, người học khám phá những khả năng Java 25 còn phù hợp với phát triển Java hiện đại: chương trình nguồn gọn (*compact source files*), câu lệnh nhập theo module, constructor linh hoạt, `ScopedValue`, API dẫn xuất khóa, AOT cache và quan sát bằng Java Flight Recorder (JFR). Trước khi học sâu các API này, cần nắm vững **ba cách đưa mã Java thành một chương trình chạy được**:

1. **Chạy thẳng mã nguồn** bằng `java TenTep.java`, phù hợp thử nghiệm và chương trình nhỏ.
2. **Biên dịch thành `.class`** bằng `javac`, sau đó chạy bằng `java` với classpath hoặc module path.
3. **Đóng gói và phân phối** bằng `jar`; khi cần, tạo runtime image với `jlink` và application image/installer với `jpackage`.

Đây là ba bước phục vụ các nhu cầu khác nhau, không phải các lựa chọn loại trừ nhau. Một dự án có thể bắt đầu từ tệp Java đơn giản, sau đó chuyển sang cấu trúc package và build tool khi phát triển lớn hơn.

Bài học thuộc chương **Thiết lập JDK 25**. Nội dung chỉ sử dụng cách làm và cú pháp **còn được hỗ trợ, phù hợp trong JDK 25**. Đặc biệt, *compact source files and instance main methods* (JEP 512) đã là tính năng chính thức ở Java 25, nên ví dụ của bài **không cần** `--enable-preview`.

### Sau bài này bạn có thể

- Xác nhận terminal đang dùng đúng JDK 25, phân biệt `java`, `javac`, `jar` và JDK runtime.
- Chạy tệp `Hello.java` có `void main()` mà không khai báo lớp tường minh.
- Biên dịch source vào một thư mục riêng và chạy class theo tên định danh đầy đủ.
- Tạo JAR có entry point, xem nội dung, kiểm tra và chạy bằng `java -jar`.
- Biên dịch, đóng gói và chạy **named Java module** có `module-info.java`.
- Nhận biết thời điểm nên chọn `jlink` hoặc `jpackage` và tránh các lỗi thiết lập thường gặp.
- Kiểm tra tính tái lập, nền tảng triển khai, dependency và tính tương thích bytecode.

> Các lệnh `java`, `javac`, `jar`, `jlink` và `jpackage` đều là **công cụ JDK**. Các ví dụ dưới đây cần một JDK 25 đã được cài đặt, không chỉ một môi trường runtime tối giản. Đường dẫn/hostname giả định được nêu rõ, không yêu cầu tải các tài nguyên đã lỗi thời.

## 2. Hiểu chuỗi xử lý từ .java đến chương trình chạy

~~~mermaid
flowchart TD
    A[Tệp nguồn .java] --> B{Cách thực hiện}
    B -->|java Hello.java| C[Biên dịch trong bộ nhớ và chạy]
    B -->|javac -d out ...| D[Tệp .class trên đĩa]
    D --> E[java --class-path out MainClass]
    D --> F[jar --create ...]
    F --> G[java -jar app.jar]
    F --> H[jpackage hoặc phân phối JAR]
    D --> I[.class + module-info.class]
    I --> J[Modular JAR]
    J --> K[java --module-path ... -m ...]
    J --> L[jlink tạo runtime image]
~~~

| Khái niệm | Tệp hoặc lệnh | Vai trò |
| --- | --- | --- |
| **Mã nguồn** | `Hello.java` | Chứa cú pháp Java đọc được |
| **Trình biên dịch** | `javac` | Tạo bytecode Java trong `.class` |
| **Launcher** | `java` | Khởi tạo JVM và gọi `main` |
| **Bytecode** | `Hello.class` | Đầu vào chạy trên JVM hỗ trợ phiên bản class file |
| **Classpath** | `--class-path out` | Tìm lớp/resource trong thư mục và JAR |
| **Module path** | `--module-path mods` | Tìm các Java module có tên |
| **JAR** | `app.jar` | Lưu các `.class`, resources và metadata trong một archive |
| **Modular JAR** | JAR có `module-info.class` | Artifact module dùng được trên module path |
| **Runtime image** | `jlink` | Chọn các Java modules cần thiết để tạo runtime tùy chỉnh |
| **Application image/package** | `jpackage` | Đóng gói launcher, runtime và application cho hệ điều hành đích |

**JAR không phải bản thân JVM**. Một ordinary JAR chỉ đóng gói code/resources; máy chạy vẫn cần Java runtime thích hợp, trừ khi dùng công cụ đóng gói mang runtime đi cùng.

## 3. Kiểm tra JDK 25 trước khi thực hành

### 3.1. Lệnh kiểm tra đa nền tảng

Mở terminal rồi chạy:

~~~bash
java -version
javac -version
jar --version
jlink --version
jpackage --version
~~~

Kết quả mong đợi ở các lệnh version đều cho thấy **25** hoặc một phiên bản cập nhật `25.0.x`. Tên vendor có thể khác nhau, chẳng hạn Eclipse Temurin, Oracle, Microsoft Build of OpenJDK hoặc một OpenJDK distribution còn được bảo trì.

Không khẳng định phiên bản patch cụ thể của JDK 25 mãi là “mới nhất”: khi cài hãy chọn **bản cập nhật bảo mật 25.x mới nhất** đang được nhà cung cấp hỗ trợ trên nền tảng của bạn.

Với **Windows PowerShell**:

~~~powershell
Get-Command java
Get-Command javac
Get-Command jar
$env:JAVA_HOME
~~~

Với **Bash/zsh (Linux/macOS)**:

~~~bash
command -v java
command -v javac
command -v jar
printf '%s\n' "$JAVA_HOME"
~~~

Nếu `java -version` hiển thị 25 nhưng `javac -version` hiển thị một version khác, PATH của máy có thể trỏ tới **hai bản JDK**. Hãy sửa PATH/JAVA_HOME rồi mở terminal mới, kiểm tra lại.

### 3.2. JAVA_HOME và PATH trên Windows

Giả sử JDK 25 được cài tại thư mục thực tế như `C:\Java\jdk-25`, trong một phiên PowerShell có thể cấu hình tạm thời:

~~~powershell
$env:JAVA_HOME = "C:\Java\jdk-25"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
~~~

Đường dẫn này **chỉ là ví dụ**; thay bằng vị trí cài JDK 25 của bạn. Việc sửa `$env:Path` theo cách trên chỉ có hiệu lực trong session PowerShell hiện tại. Để cấu hình lâu dài, dùng thiết lập môi trường của hệ điều hành hoặc cơ chế quản lý JDK của công ty/IDE.

Trên Windows, `where.exe java` có thể cho biết các executable cùng tên xuất hiện theo thứ tự tìm kiếm PATH; dùng `Get-Command java` để xác định lệnh được PowerShell chọn.

### 3.3. Phân biệt JDK dùng để biên dịch và Java dùng để chạy

Nếu muốn sử dụng cú pháp hoặc API chỉ có từ Java 25, trình biên dịch cần hiểu version đó; **JDK 25** là lựa chọn trực tiếp. Bytecode biên dịch theo Java 25 có **class-file major version 69** và cần JVM hỗ trợ Java 25 trở lên, trừ khi đã chủ động biên dịch cho một release cũ bằng `--release` mà mã nguồn tương thích.

Để chọn một toolchain khác trong Maven/Gradle/IDE, cấu hình **JDK và release target** cho dự án; không dựa duy nhất vào việc terminal đang trỏ đến một JDK nào đó.

## 4. Cách 1 — Chạy trực tiếp tệp nguồn Java 25

### 4.1. Chương trình compact source file đầu tiên

Tạo một thư mục thực hành, trong đó có tệp **`Hello.java`**:

~~~java
void main() {
    IO.println("Xin chào Java 25!");
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
java Hello.java
~~~

Kết quả:

~~~text
Xin chào Java 25!
~~~

Trong Java 25, ví dụ này là Java hợp lệ vì:

- `void main()` có thể là **instance main method**; không bắt buộc phải viết `public static void main(String[] args)`.
- Tệp có phương thức cấp cao nhất nhưng không khai báo `class` tường minh được gọi là **compact source file**. Trình biên dịch tạo lớp ngầm định tương ứng.
- `IO.println` thuộc lớp `java.lang.IO` được bổ sung cho cách viết console đơn giản.
- Compact source file được hưởng import tự động các kiểu public phù hợp được `java.base` export, tương tự `import module java.base;`.

**Điểm mấu chốt:** đây là tính năng đã chính thức của Java 25 (JEP 512), không cần cờ preview. Những tài liệu cũ hướng dẫn bật preview chỉ phản ánh giai đoạn tính năng còn thử nghiệm ở JDK trước đó.

### 4.2. Tham số dòng lệnh và phương thức phụ trợ

Thay nội dung tệp **`Hello.java`** bằng:

~~~java
String greet(String name) {
    return "Xin chào, " + name + "!";
}

void main(String[] args) {
    String name = args.length == 0 ? "Java 25" : args[0];
    IO.println(greet(name));
}
~~~

Chạy:

~~~bash
java Hello.java Lan
java Hello.java
~~~

Kết quả lần lượt:

~~~text
Xin chào, Lan!
Xin chào, Java 25!
~~~

Các đối số sau tên tệp nguồn sẽ được truyền vào `args`. Không được đặt `--class-path` hoặc các tùy chọn launcher cần áp dụng cho compilation **sau** tên tệp; các tùy chọn của JVM/launcher phải được viết trước source file khi cần.

### 4.3. java source-file mode thực hiện điều gì?

Khi gọi `java Hello.java`, Java launcher:

1. Nhận diện đối số là một tệp nguồn có đuôi `.java`.
2. Biên dịch mã nguồn bằng compiler của JDK đang dùng trong **source-file mode**.
3. Tìm một `main` có thể khởi chạy theo quy tắc Java 25.
4. Chạy chương trình mà không yêu cầu bạn thực hiện bước `javac` riêng.

Ở chế độ này, compilation phục vụ **lần chạy hiện tại**; bạn không nên mong có `Hello.class` được lưu bền trên đĩa sau mỗi lệnh. Đây là cách rất hữu ích cho ví dụ nhỏ, script phát triển và thử nhanh API. Với dự án lớn, chạy lặp lại và đóng gói phân phối, quy trình biên dịch thành `.class` riêng vẫn có giá trị.

Nếu muốn nêu rõ phiên bản source:

~~~bash
java --source 25 Hello.java Lan
~~~

Lệnh này vẫn là **source-file mode**. Trong một môi trường đã dùng JDK 25 và tệp `.java` thông thường, `--source 25` không bắt buộc.

### 4.4. Compile compact source file khi cần .class

Bạn cũng có thể biên dịch tệp có lớp ngầm định:

~~~bash
javac --release 25 Hello.java
java Hello Lan
~~~

Sau lệnh `javac`, compiler sinh ra class file có tên dựa trên tên tệp, ví dụ `Hello.class`. Tên `Hello` ở đây là chi tiết đầu ra của compiler và launcher; **mã nguồn khác không thể tham chiếu trực tiếp kiểu lớp ngầm định đó bằng tên như một public API**.

Biên dịch vào thư mục riêng để tránh để `.class` lẫn với source:

~~~bash
javac --release 25 -d out Hello.java
java --class-path out Hello Lan
~~~

Trong ví dụ này, `out` phải là thư mục compiler có quyền tạo/ghi. Lệnh `javac -d out` có thể tạo package subdirectories bên dưới `out`, nhưng nên chuẩn bị thư mục đầu ra ở bước thiết lập khi cần. Trên PowerShell, tạo trước bằng `New-Item -ItemType Directory -Force out`; trên Bash dùng `mkdir -p out`.

### 4.5. Khi nào không nên giữ compact source file làm cấu trúc chính?

Compact source file thích hợp cho chương trình độc lập, mục tiêu học tập và công cụ nhỏ. Khi cần khai báo package công khai, chia nhiều class có thể tái sử dụng, test API hoặc đóng gói JAR có entry point rõ ràng, hãy **chuyển dần sang class tường minh trong named package**. Đây là bước tổ chức mã cho quy mô lớn, không phải vì compact source là cú pháp lỗi thời.

## 5. Cách 2 — Biên dịch một class trong named package

Ta sẽ tạo một ứng dụng khác, độc lập với `Hello.java` ở phần trước, để theo dõi rõ từ nguồn đến bytecode rồi JAR.

### 5.1. Cấu trúc thư mục

~~~text
java25-packaging/
└── src/
    └── main/
        └── java/
            └── vn/
                └── example/
                    └── java25/
                        └── Main.java
~~~

Nội dung **`src/main/java/vn/example/java25/Main.java`**:

~~~java
package vn.example.java25;

public final class Main {

    public static void main(String[] args) {
        String who = args.length == 0 ? "Java 25" : args[0];
        System.out.println("Xin chào, " + who + "!");
    }
}
~~~

`public static void main(String[] args)` **vẫn là cách viết Java hiện đại và được hỗ trợ đầy đủ**. Java 25 cho phép thêm các dạng `main` mới; nó không xóa cú pháp quen thuộc. Với một ứng dụng cần entry point rõ ràng và phân phối JAR, cách này dễ nhận biết với nhiều công cụ và nhóm phát triển.

### 5.2. Dùng javac --release 25

Từ thư mục gốc **`java25-packaging`**, tạo thư mục đầu ra:

~~~powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Hoặc trên Bash:

~~~bash
mkdir -p out
~~~

Biên dịch (lệnh Java giống nhau giữa các hệ điều hành):

~~~bash
javac --release 25 -encoding UTF-8 -d out src/main/java/vn/example/java25/Main.java
~~~

Giải thích:

- `--release 25`: biên dịch theo quy tắc của **Java 25**, gồm API và class-file target được hỗ trợ.
- `-encoding UTF-8`: xác định rõ cách đọc tệp nguồn có tiếng Việt.
- `-d out`: ghi `.class` vào thư mục đầu ra riêng.
- Đường dẫn cuối là **tệp nguồn thực** cần biên dịch.

Sau đó có:

~~~text
out/
└── vn/
    └── example/
        └── java25/
            └── Main.class
~~~

### 5.3. Chạy class đã biên dịch

~~~bash
java --class-path out vn.example.java25.Main Minh
~~~

Kết quả:

~~~text
Xin chào, Minh!
~~~

Phân tích:

- `out` là **classpath root**, không phải đường dẫn tới tệp `Main.class`.
- `vn.example.java25.Main` là **tên class đầy đủ** (fully qualified class name, FQCN), không có hậu tố `.class`.
- Java launcher tìm class theo đường dẫn tương ứng `vn/example/java25/Main.class` dưới classpath root.
- `Minh` được truyền vào `main(String[] args)`.

Nếu bạn chạy `java Main` trong thư mục gốc, JVM không tìm thấy class thuộc package `vn.example.java25`. Nếu chỉ định `--class-path out/vn/example/java25`, root cũng sai vì nó không tương ứng gốc package.

### 5.4. Kiểm tra bytecode và phiên bản class file

~~~bash
javap --class-path out vn.example.java25.Main
javap -verbose --class-path out vn.example.java25.Main
~~~

`javap` giúp kiểm tra chữ ký class/method. Trong đầu ra `-verbose`, class file biên dịch cho Java 25 thường có:

~~~text
major version: 69
~~~

Kiểm tra major version hữu ích khi chạy trên JVM khác phiên bản. Nếu ứng dụng yêu cầu Java 25 API, biên dịch bằng `--release 25` là phù hợp; nếu bạn chủ động nhắm tới Java 21, phải chỉ dùng cú pháp/API Java 21 và biên dịch `--release 21`. Không thể chỉ đổi target version mà vẫn sử dụng tính năng chỉ tồn tại ở Java 25.

## 6. Cách 3 — Tạo executable JAR và chạy bằng java -jar

JAR dùng định dạng archive để đóng gói `.class`, resources và metadata. Tạo JAR từ thư mục `out` vừa biên dịch:

~~~bash
jar --create --file hello-java25.jar \
    --main-class vn.example.java25.Main \
    -C out .
~~~

Trong **Windows PowerShell**, để tránh vấn đề dấu xuống dòng của Bash, dùng một dòng:

~~~powershell
jar --create --file hello-java25.jar --main-class vn.example.java25.Main -C out .
~~~

`--main-class` khai báo entry point. Công cụ `jar` tạo manifest chứa `Main-Class` để Java launcher biết class cần gọi. Tham số `-C out .` yêu cầu lấy các nội dung bên dưới thư mục `out` và đặt chúng tại gốc JAR; không thêm một tầng `out/` vào package path bên trong archive.

### 6.1. Xem và xác minh artifact

~~~bash
jar --list --file hello-java25.jar
jar --validate --file hello-java25.jar
~~~

Danh sách nội dung sẽ có các mục tương tự:

~~~text
META-INF/
META-INF/MANIFEST.MF
vn/
vn/example/
vn/example/java25/
vn/example/java25/Main.class
~~~

`jar --validate` kiểm tra tính hợp lệ của archive theo các quy tắc mà công cụ JDK hỗ trợ. Nó **không** thay unit test, kiểm tra security hay xác minh dependency của cả ứng dụng.

Chạy JAR:

~~~bash
java -jar hello-java25.jar Huy
~~~

Kết quả:

~~~text
Xin chào, Huy!
~~~

### 6.2. JAR có resource

Giả sử có tệp **`src/main/resources/application.properties`**:

~~~properties
app.greeting=Xin chao tu resource
~~~

Đưa cả các class và resource vào JAR:

~~~bash
jar --create --file hello-java25.jar \
    --main-class vn.example.java25.Main \
    -C out . \
    -C src/main/resources .
~~~

Bản PowerShell một dòng:

~~~powershell
jar --create --file hello-java25.jar --main-class vn.example.java25.Main -C out . -C src/main/resources .
~~~

Resource nằm ở gốc archive và có thể được nạp bằng `Main.class.getResourceAsStream("/application.properties")`. Đây là cách tách cấu hình/tài nguyên khỏi source code; với cấu hình bí mật của môi trường vận hành, nên inject từ ngoài artifact thay vì đóng password vào JAR.

### 6.3. Điều gì xảy ra nếu chương trình có thư viện ngoài?

Ví dụ hiện tại chỉ dùng **Java standard API**, nên một JAR chứa `Main.class` là đủ. Với JDBC driver, JSON library hoặc framework, JAR bạn tạo bằng lệnh `jar --create` **không tự động** nhúng mọi transitive dependency.

Có hai chiến lược còn phổ biến:

1. **JAR cùng thư mục libraries:** phân phối `app.jar` và các dependency JAR trong `lib/`, chạy bằng classpath phù hợp hoặc cơ chế launcher của ứng dụng.
2. **Executable/fat JAR do build tool tạo:** sử dụng plugin phù hợp của Maven/Gradle/framework (ví dụ Spring Boot plugin cho Spring Boot app), sau đó chạy theo cách plugin công bố.

Ví dụ nếu cần chạy class có library ngoài trong thư mục `lib/`:

~~~bash
# Linux/macOS: dấu : ngăn cách các mục classpath
java --class-path "hello-java25.jar:lib/*" vn.example.java25.Main
~~~

~~~powershell
# Windows: dấu ; ngăn cách các mục classpath
java --class-path "hello-java25.jar;lib/*" vn.example.java25.Main
~~~

Nếu dùng `java -jar hello-java25.jar`, option `--class-path` bên ngoài **không được dùng để bổ sung dependency** theo cách giống lệnh classpath. Muốn chạy JAR có dependencies, cần manifest `Class-Path` hợp lệ, launcher hỗ trợ hoặc artifact được đóng gói bằng build tool đúng chuẩn.

**Không tự coi JAR tạo bởi công cụ JDK là fat JAR.** Đối với ứng dụng thực tế, Maven/Gradle quản lý version và dependency là cách phù hợp để tái lập build.

## 7. Maven/Gradle trong dự án thực tế

Thực hành bằng `javac` và `jar` giúp hiểu pipeline. Khi dự án có nhiều tệp nguồn, dependency, unit test và nhiều môi trường, nên dùng build tool.

### 7.1. Cấu hình Maven cho JDK 25

Một cấu hình mục tiêu compilation điển hình trong `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Thực thi bằng Maven Wrapper nếu dự án có wrapper:

~~~bash
./mvnw -version
./mvnw clean package
~~~

Trên Windows PowerShell có thể dùng `.\mvnw.cmd -version` và `.\mvnw.cmd clean package`. Dự án phải có `pom.xml`, Maven Compiler Plugin thích hợp và toolchain/JDK 25. Ví dụ này **không tự tạo** một project Maven hoàn chỉnh; entry point executable JAR cũng cần cấu hình plugin/manifest theo mục tiêu.

### 7.2. Cấu hình Gradle cho JDK 25

Trong `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

application {
    mainClass = 'vn.example.java25.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 25
    options.encoding = 'UTF-8'
}
~~~

Sau khi dùng **phiên bản Gradle hỗ trợ JDK 25**, có thể:

~~~bash
./gradlew clean build
./gradlew run --args="Lan"
~~~

Trên Windows, thay `./gradlew` bằng `.\gradlew.bat`. Plugin `application` có thể tạo distribution bao gồm dependency và start scripts; `jar` task thuần túy không tự tạo fat JAR.

**Phân biệt hai điều:**

- **Toolchain 25** chọn compiler/JDK tương ứng.
- **`options.release = 25`** chọn Java API, cú pháp và target bytecode của release 25.

Đặt cùng giá trị làm thiết kế rõ ràng. Nếu ứng dụng cần chạy trên nhiều phiên bản Java, đánh giá mục tiêu release riêng theo API thực tế, không chỉ chọn JDK mới nhất.

## 8. Biên dịch và chạy ứng dụng Java module có module-info.java

Java Platform Module System (JPMS) vẫn là một lựa chọn hiện đại cho dự án muốn khai báo rõ module dependencies/encapsulation. Đây là **Java module**, khác với ranh giới nghiệp vụ kiểu application module của Spring Modulith.

### 8.1. Cấu trúc module ví dụ

Tạo một dự án độc lập **`java25-modular`**:

~~~text
java25-modular/
└── src-modules/
    └── vn.example.greeting/
        ├── module-info.java
        └── vn/
            └── example/
                └── greeting/
                    └── Main.java
~~~

`src-modules/vn.example.greeting/module-info.java`:

~~~java
module vn.example.greeting {
}
~~~

`src-modules/vn.example.greeting/vn/example/greeting/Main.java`:

~~~java
package vn.example.greeting;

public final class Main {

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java 25" : args[0];
        System.out.println("Module xin chào " + name + "!");
    }
}
~~~

Module này chỉ dùng `java.base`, được đọc ngầm định theo quy tắc JPMS, vì vậy không cần viết `requires java.base;`. Nó cũng không cần `exports` vì chưa cung cấp API public cho module khác; việc launcher gọi main class là một cơ chế riêng.

### 8.2. Biên dịch named module

Từ thư mục `java25-modular`:

~~~bash
javac --release 25 --module-source-path src-modules \
    -d mods -m vn.example.greeting
~~~

Bản PowerShell một dòng:

~~~powershell
javac --release 25 --module-source-path src-modules -d mods -m vn.example.greeting
~~~

Kết quả:

~~~text
mods/
└── vn.example.greeting/
    ├── module-info.class
    └── vn/example/greeting/Main.class
~~~

`--module-source-path` cho compiler biết cấu trúc module nguồn; `-m` chọn module cần biên dịch. Tùy project, có thể dùng module-aware build tool thay vì tự viết lệnh cho hàng chục module.

### 8.3. Chạy module bằng -m

~~~bash
java --module-path mods \
    --module vn.example.greeting/vn.example.greeting.Main Mai
~~~

PowerShell một dòng:

~~~powershell
java --module-path mods --module vn.example.greeting/vn.example.greeting.Main Mai
~~~

Kết quả:

~~~text
Module xin chào Mai!
~~~

Cú pháp `--module moduleName/mainClass` hoặc `-m moduleName/mainClass` chọn Java module và class entry point. Nếu một module có nhiều classes có main, nên chỉ định class để tránh nhầm.

### 8.4. Tạo modular JAR

~~~bash
jar --create --file greeting-modular.jar \
    --main-class vn.example.greeting.Main \
    -C mods/vn.example.greeting .
~~~

PowerShell một dòng:

~~~powershell
jar --create --file greeting-modular.jar --main-class vn.example.greeting.Main -C mods/vn.example.greeting .
~~~

Kiểm tra:

~~~bash
jar --describe-module --file greeting-modular.jar
jar --list --file greeting-modular.jar
jar --validate --file greeting-modular.jar
~~~

Một **modular JAR** có `module-info.class` tại root archive. Đây là điểm phân biệt với ordinary JAR không có module descriptor. Lệnh `--main-class` có thể ghi nhận main class của module; không cần tự ghép manifest bằng chuỗi.

Chạy modular JAR trên module path:

~~~bash
java --module-path greeting-modular.jar \
    --module vn.example.greeting
~~~

PowerShell một dòng:

~~~powershell
java --module-path greeting-modular.jar --module vn.example.greeting
~~~

Hoặc chỉ định entry point tường minh:

~~~bash
java --module-path greeting-modular.jar \
    --module vn.example.greeting/vn.example.greeting.Main
~~~

Không đặt `module-info.java` vào ordinary classpath dự án cũ rồi giả định nó sẽ thực hiện kiểm tra JPMS. Khi dùng module path, compiler và launcher tuân thủ **module readability, exports/opens** theo descriptor đã khai báo.

## 9. Tạo runtime image tùy chỉnh bằng jlink

Một JAR Java thường cần một Java runtime ở máy đích. Với **modular application**, `jlink` có thể ghép các JDK modules cùng application module cần thiết để tạo runtime image phù hợp.

Từ thư mục `java25-modular`, sau khi đã tạo `greeting-modular.jar`:

~~~bash
jlink --module-path greeting-modular.jar \
    --add-modules vn.example.greeting \
    --launcher greeting=vn.example.greeting/vn.example.greeting.Main \
    --output runtime-image
~~~

PowerShell một dòng:

~~~powershell
jlink --module-path greeting-modular.jar --add-modules vn.example.greeting --launcher greeting=vn.example.greeting/vn.example.greeting.Main --output runtime-image
~~~

Công cụ `jlink` có thể tìm các JDK modules chuẩn trong `jmods` của JDK đang chạy nếu không được cung cấp riêng. Kiểm tra runtime image đã tạo:

~~~bash
runtime-image/bin/java --list-modules
runtime-image/bin/greeting An
~~~

Trên Windows, executable có thể được gọi là:

~~~powershell
.\runtime-image\bin\java.exe --list-modules
.\runtime-image\bin\greeting.exe An
~~~

Chú ý:

- Runtime image được tạo cho **hệ điều hành/kiến trúc phù hợp với JDK và công cụ dùng để link**; không mặc định sao chép image Windows sang Linux.
- Không phải mọi thư viện trong một ứng dụng lớn đều đã có JPMS module descriptor. Cần đánh giá cách kết hợp non-modular dependencies; `jlink` có yêu cầu rõ về module graph và không phải giải pháp tự động cho mọi classpath app.
- Một runtime image tùy chỉnh là artifact triển khai; vẫn cần theo dõi bản cập nhật bảo mật của Java 25 và **rebuild image** khi JDK nền tảng được vá.
- `jlink` giải quyết runtime composition; nó không tự thay thế hệ thống package/installer của OS.

## 10. Đóng gói ứng dụng bằng jpackage

`jpackage` dùng để tạo application image hoặc native installer phù hợp với hệ điều hành đích. Đây là lựa chọn thích hợp khi muốn phân phối **ứng dụng desktop hoặc command-line** với launcher và runtime đi kèm.

Đối với ordinary JAR `hello-java25.jar` đã tạo ở phần 6, sao chép JAR vào một thư mục đầu vào riêng tên `package-input`:

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force package-input | Out-Null
Copy-Item hello-java25.jar package-input/
~~~

Trên Bash:

~~~bash
mkdir -p package-input
cp hello-java25.jar package-input/
~~~

~~~text
java25-packaging/
├── hello-java25.jar
└── package-input/
    └── hello-java25.jar
~~~

Sau đó chạy:

~~~bash
jpackage --type app-image \
    --name Java25Hello \
    --input package-input \
    --main-jar hello-java25.jar \
    --main-class vn.example.java25.Main \
    --dest packages
~~~

PowerShell một dòng:

~~~powershell
jpackage --type app-image --name Java25Hello --input package-input --main-jar hello-java25.jar --main-class vn.example.java25.Main --dest packages --win-console
~~~

`--type app-image` tạo một **thư mục application image** với launcher/runtime cần thiết; không nhất thiết tạo bộ cài MSI/DEB/DMG. Muốn native installer, cần chọn loại package theo OS và chuẩn bị toolchain đóng gói của OS đó.

Trên Windows, thêm `--win-console` cho chương trình dòng lệnh cần hiện đầu ra và nhận tương tác qua console. Đây là tùy chọn **riêng của Windows**; không đặt nó vào lệnh `jpackage` trên Linux/macOS.

**Lưu ý thực tế:** không đặt `--input .` khi thư mục project chứa source, test reports, secrets hoặc nhiều build outputs, vì `jpackage` sử dụng nội dung của thư mục input. Nên dùng thư mục staging package chỉ có artifact cần phân phối.

Với ứng dụng Java module có tên, `jpackage` cũng hỗ trợ `--module-path` và `--module`; không cần chuyển hết thành ordinary JAR chỉ để tạo launcher.

## 11. Tự kiểm tra đầu ra và khả năng tái lập

### 11.1. Ma trận kiểm tra tối thiểu

| Ca kiểm tra | Lệnh hoặc hành động | Kết quả kỳ vọng |
| --- | --- | --- |
| JDK đúng | `java -version`, `javac -version` | Cùng JDK 25 đã chọn |
| Chạy compact source | `java Hello.java` | In thông báo, không cần preview |
| Truyền đối số | `java Hello.java Lan` | `Lan` được đọc từ `args` |
| Tạo class file | `javac --release 25 -d out ...` | Có `.class` trong đúng package path |
| Chạy class | `java --class-path out vn.example.java25.Main` | Thực thi main thành công |
| Kiểm tra bytecode | `javap -verbose ...` | Class-file major 69 khi target Java 25 |
| Tạo JAR | `jar --create --file ... --main-class ...` | Có manifest, class đúng vị trí |
| Chạy JAR | `java -jar hello-java25.jar` | Chương trình chạy đúng |
| Biên dịch module | `javac --module-source-path ... -m ...` | Có `module-info.class` |
| Chạy modular JAR | `java --module-path ... --module ...` | Module resolve và launcher chạy |
| jlink | Tạo runtime image và gọi launcher | Runtime có module cần thiết |
| jpackage | `--type app-image` | Có app image đúng OS |

### 11.2. Vì sao không chỉ kiểm tra “exit code = 0”?

Với ứng dụng phân phối, nên xác minh:

1. **Bytecode target:** sử dụng `javap` và `--release` phù hợp.
2. **Main-Class/ModuleMainClass:** bảo đảm launcher tìm được entry point đúng.
3. **Resources:** những tệp config/resource không bị thiếu hoặc đặt sai archive path.
4. **Dependency resolution:** mọi library cần thiết xuất hiện khi chạy.
5. **Kết quả thực thi:** chạy smoke test của artifact mới tạo với args điển hình.
6. **Môi trường đích:** đúng JDK/runtime, architecture, path và permissions.
7. **Tính lặp lại:** ghi rõ JDK distribution + patch, build tool/plugin version và checksum của artifact theo quy trình CI/CD.
8. **An toàn supply chain:** kiểm tra dependency provenance và cập nhật security patches khi tạo lại image.

Một JAR chạy đúng trên máy developer vẫn có thể thất bại trên server nếu thiếu runtime hoặc external dependency. Thử nghiệm artifact cuối cùng trên môi trường gần production là một phần của quy trình đóng gói.

## 12. Những lỗi thường gặp và cách chẩn đoán

### 12.1. 'java' works but 'javac' is not recognized

**Nguyên nhân:** PATH trỏ tới runtime khác, JDK chưa cài, hoặc `JAVA_HOME/bin` chưa nằm trong PATH.

**Cách xử lý:** kiểm tra lại `java -version`, `javac -version` và vị trí executable được shell chọn. Dùng JDK 25 thực sự để compile; không dựa vào thông báo từ IDE nếu terminal dùng JDK khác.

### 12.2. error: release version 25 not supported

**Nguyên nhân:** compiler `javac` đang chạy không phải JDK đủ mới để hiểu `--release 25`.

**Cách xử lý:** dùng đúng toolchain/JDK 25 hoặc mới hơn có hỗ trợ release 25; xác nhận qua `javac -version`. Không sửa lệnh thành `--release 17` nếu mã nguồn đang dùng Java 25 APIs/features.

### 12.3. preview features are disabled

Có thể bạn đang dùng JDK cũ để biên dịch mã compact source hoặc các tính năng đã ở preview trước Java 25. Trong Java 25, compact source/instance main đã **final**, vì vậy cần xác nhận **đúng JDK 25**, thay vì bật `--enable-preview` theo hướng dẫn cũ.

**Ngoại lệ:** nếu chính ứng dụng dùng *một tính năng khác* còn preview trong JDK cụ thể đang chạy, nó cần quy tắc opt-in riêng. Bài hiện tại không sử dụng tính năng preview.

### 12.4. Could not find or load main class

**Nguyên nhân thường gặp:** sai classpath root, gõ `Main` thay cho `vn.example.java25.Main`, hoặc bỏ `-d out` khiến class nằm sai cấu trúc.

**Cách xử lý:** kiểm tra `jar --list` hoặc thư mục `out`, đối chiếu package declaration và chạy bằng FQCN.

### 12.5. no main manifest attribute

**Nguyên nhân:** JAR không có `Main-Class` thích hợp, hoặc đóng gói nhầm class.

**Cách xử lý:** tạo lại bằng `jar --create --main-class vn.example.java25.Main ...`, kiểm tra manifest và chạy `java -jar`. Với modular JAR, dùng `jar --describe-module` và launcher theo module path nếu phù hợp.

### 12.6. UnsupportedClassVersionError

**Nguyên nhân:** JVM đang chạy không hiểu major version của bytecode, ví dụ class version 69 trên một Java runtime cũ hơn 25.

**Cách xử lý:** nâng runtime đích đúng phiên bản được yêu cầu hoặc chủ động biên dịch cho release cũ nếu code/API thực sự tương thích. Không sửa file `.class` thủ công.

### 12.7. NoClassDefFoundError khi chạy JAR

**Nguyên nhân:** thiếu dependency runtime hoặc xung đột version; tạo ordinary JAR không tự nhúng toàn bộ `lib`.

**Cách xử lý:** kiểm tra classpath/module path, manifest `Class-Path`, dependency graph Maven/Gradle và packaging plugin. Tránh chép JAR không kiểm soát từ máy cá nhân sang production.

### 12.8. Classpath và module path bị nhầm

**Biểu hiện:** chạy `java -jar` không kiểm tra tính đọc module như lệnh `java --module-path ... -m ...`, hoặc mô-đun không resolve.

**Cách xử lý:** nếu dùng JPMS, giữ `module-info.class` ở root modular JAR, thiết lập module path và khai báo dependencies/exports/opens có chủ đích. Không cho rằng classpath và module path có semantics tương đương.

### 12.9. jlink hoặc jpackage lỗi trên máy khác

**Nguyên nhân:** khác OS/CPU architecture, thiếu packaging tools, module graph không hợp lệ hoặc thiếu resources/native libraries.

**Cách xử lý:** build trên hệ điều hành/kiến trúc đích tương ứng, dùng các lệnh `--list-modules`, `jar --describe-module` và kiểm tra package contents. Với installer, đọc yêu cầu toolchain hệ điều hành của `jpackage` trong tài liệu JDK 25.

## 13. Quy trình đề xuất khi dự án phát triển lớn hơn

~~~mermaid
flowchart TD
    A[Thử ý tưởng bằng compact source] --> B{Chương trình cần mở rộng?}
    B -- Chưa --> C[java TenTep.java]
    B -- Có --> D[Named packages + classes]
    D --> E[Maven/Gradle toolchain JDK 25]
    E --> F[javac --release 25 và tests]
    F --> G{Cần named JPMS module?}
    G -- Không --> H[Executable JAR / distribution]
    G -- Có --> I[Modular JAR]
    I --> J[jlink runtime image khi thích hợp]
    H --> K[jpackage nếu cần ứng dụng đóng gói cùng runtime]
    J --> K
    K --> L[Kiểm thử artifact trên OS đích]
~~~

Chọn phương thức dựa theo **quy mô và nhu cầu phân phối**:

- Một đoạn kiểm tra thuật toán hoặc thí nghiệm Java 25: `java Hello.java`.
- Một CLI đơn giản trong nội bộ: explicit class, Maven/Gradle và JAR có Main-Class.
- Nhiều package/API và dependency: build tool quản lý việc biên dịch, test và phân phối.
- Ứng dụng cần ranh giới JPMS rõ ràng: named module và modular JAR.
- Sản phẩm desktop/CLI cần runtime đi kèm: `jpackage` hoặc `jlink` kết hợp packaging.
- Ứng dụng server Spring Boot: dùng packaging plugin/framework và container/runtime theo yêu cầu vận hành; không thay thế quy trình dependency management bằng vài lệnh `jar` tự viết.

Java 25 còn có các cải tiến khác như **ScopedValue, KDF API, AOT cache, JFR**. Việc các API này tồn tại không làm thay đổi nguyên tắc cơ bản của `java`, `javac`, classpath, modules và JAR. Khi sử dụng tính năng mới, hãy kiểm tra trạng thái final/preview của **chính tính năng** trước khi chọn compiler flags.

## 14. Bài tập và tiêu chí hoàn thành

### Bài tập A — compact source file

Tạo `Hello.java` không có khai báo class, dùng `void main(String[] args)` và `IO.println`. Chạy với 0 và 1 đối số, giải thích cách JVM tìm và gọi `main`.

**Đạt khi:** chạy `java Hello.java` trên JDK 25 mà không cần preview flag; truyền args đúng.

### Bài tập B — source so với class

Biên dịch `Hello.java` vào `out`, sau đó chuyển sang tệp `Main.java` có package `vn.example.java25`. So sánh output của source-file mode với `.class` được lưu trên đĩa.

**Đạt khi:** chạy `java --class-path out vn.example.java25.Main`, có thể giải thích FQCN và `--release 25`.

### Bài tập C — executable JAR

Tạo `hello-java25.jar` bằng `jar --create --main-class`, xem nội dung bằng `jar --list`, rồi chạy bằng `java -jar`. Thêm một resource và xác minh vị trí của resource trong archive.

**Đạt khi:** JAR chạy độc lập với source folder và có manifest đúng, không cần hardcode classpath tới file `.class`.

### Bài tập D — Java module

Tạo `module-info.java` và biên dịch module `vn.example.greeting`. Chạy module từ `mods`, đóng gói modular JAR và kiểm tra descriptor.

**Đạt khi:** `jar --describe-module` cho thấy named module, `java --module-path ... -m ...` chạy thành công.

### Bài tập E — runtime/application image

Tạo runtime image bằng `jlink` cho modular JAR, hoặc app image bằng `jpackage` cho ordinary JAR. Ghi lại JDK build, hệ điều hành, kiến trúc và kết quả smoke test.

**Đạt khi:** có launcher chạy được trên đúng môi trường đích, phân biệt được portable JAR với OS-specific image.

### Checklist tự đánh giá

- [ ] `java`, `javac`, `jar`, `jlink`, `jpackage` đến từ JDK 25 đã chọn.
- [ ] Chạy được compact source file `void main()` / `IO.println` mà không bật preview.
- [ ] Biết khi nào source-file mode biên dịch tạm và khi nào `javac` tạo `.class` thật trên đĩa.
- [ ] Biên dịch named package bằng `javac --release 25 -d out` và chạy theo FQCN.
- [ ] Kiểm tra class-file major version 69 cho target Java 25.
- [ ] Tạo JAR có `Main-Class`, kiểm tra archive và chạy `java -jar`.
- [ ] Phân biệt dependencies ngoài với mã được đóng gói trong ordinary JAR.
- [ ] Biên dịch, chạy và đóng gói được named Java module khi cần JPMS.
- [ ] Hiểu vai trò của `jlink` và `jpackage`, kể cả giới hạn về hệ điều hành/kiến trúc.
- [ ] Có test cho artifact đầu ra, danh sách thư viện và bản vá JDK sử dụng.

## 15. Nguồn tham khảo chính thức

Các hướng dẫn và cú pháp trong bài dựa trên tài liệu cho **JDK 25**, tập trung vào những công cụ vẫn dùng trong Java hiện đại:

1. [Oracle Java 25 – Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): cách viết compact source, `java.lang.IO`, quy tắc launcher và compilation.
2. [JEP 512 – Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): trạng thái tính năng đã chính thức trong Java 25.
3. [Oracle Java 25 – The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): source-file mode, class launcher, JAR và module launcher.
4. [Oracle Java 25 – The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `-d`, classpath/module path.
5. [Oracle Java 25 – The jar Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): `--create`, `--main-class`, `--list`, `--validate` và modular JAR.
6. [Oracle Java 25 – The jlink Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html): tạo runtime image từ modules.
7. [Oracle Java 25 – The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): application image và native package.
8. [Oracle Java 25 – Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): ví dụ đóng gói ứng dụng có và không có Java module.

**Kết quả mong đợi:** người học đi được trọn chu trình **mã nguồn Java 25 → chương trình chạy trực tiếp → class files → executable/modular JAR → runtime/application image khi cần**, hiểu rõ từng entry point, classpath/module path và giới hạn môi trường triển khai. Những cách làm này tiếp tục phù hợp để xây dựng, kiểm thử và phân phối ứng dụng Java hiện đại, đồng thời tạo nền tảng vững chắc trước khi ứng dụng các API nâng cao của Java 25.
