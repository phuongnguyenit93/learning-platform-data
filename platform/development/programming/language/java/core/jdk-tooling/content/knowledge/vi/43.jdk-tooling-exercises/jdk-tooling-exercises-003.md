# Đóng gói ứng dụng Java bằng JAR

**JAR (Java Archive)** là định dạng lưu trữ dựa trên ZIP, dùng để đóng gói Java class, resource, metadata và đôi khi cả dependency thành một artifact có thể phân phối. JAR giúp gom các thành phần của ứng dụng vào một file có version rõ ràng, dễ lưu trong artifact repository, upload lên server, kiểm tra checksum và triển khai qua CI/CD.

Một file JAR có thể là thư viện để project khác sử dụng hoặc là ứng dụng có thể chạy bằng lệnh Java. Muốn chạy bằng `java -jar app.jar`, JAR cần khai báo điểm vào trong manifest bằng thuộc tính `Main-Class` và class đó phải có phương thức `public static void main(String[] args)`. Tuy nhiên, có `Main-Class` không có nghĩa JAR đã chứa mọi thư viện mà ứng dụng cần.

Bài này đi từ cấu trúc JAR, cách biên dịch và đóng gói thủ công bằng JDK 17+, đến manifest, resource, dependency, Maven, Gradle, modular JAR, kiểm tra và phát hành artifact.

## 1. JAR là gì và dùng để làm gì?

JAR là một file archive có phần mở rộng `.jar`. Về cấu trúc, nó tuân theo định dạng ZIP và bổ sung quy ước cho Java như thư mục `META-INF`, manifest và metadata module.

JAR thường được dùng cho ba mục đích:

- **Library JAR:** chứa class và resource để ứng dụng khác khai báo làm dependency.
- **Executable JAR:** có điểm vào để khởi chạy bằng `java -jar app.jar`.
- **Distribution artifact:** một JAR kèm các thư viện, script khởi chạy, file cấu hình mẫu hoặc tài liệu trong một thư mục/ZIP phát hành.

JAR không phải file native executable. Hệ điều hành không tự chạy JAR như file EXE; cần có Java runtime và khởi chạy bằng Java launcher.

Một JAR có thể được phân phối độc lập, nhưng ứng dụng vẫn cần Java runtime tương thích. Nếu bytecode được biên dịch cho Java 17, runtime cũ hơn Java 17 không thể chạy trực tiếp class đó.

## 2. Cấu trúc bên trong một JAR

Một JAR điển hình có thể chứa:

```text
hello.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── hello/
            └── App.class
```

Ý nghĩa:

- `META-INF/MANIFEST.MF`: metadata chính của archive, gồm version manifest, main class, classpath hoặc thông tin build.
- `com/example/hello/App.class`: bytecode của class Java thuộc package `com.example.hello`.
- Resource như `config/app.properties` hoặc `messages/messages_vi.properties` có thể nằm ở các đường dẫn khác trong archive.
- `META-INF/services/` có thể chứa file khai báo provider cho Java ServiceLoader.
- Modular JAR có thể chứa `module-info.class` ở root của archive.

Đường dẫn entry trong JAR dùng dấu gạch chéo xuôi `/` kể cả khi build trên Windows. Tên package được ánh xạ thành thư mục: `com.example.hello` thành `com/example/hello/`.

JAR không bắt buộc phải chứa source code. Source JAR là artifact riêng, thường có hậu tố `-sources.jar`; Javadoc JAR cũng thường là artifact riêng có hậu tố `-javadoc.jar`.

## 3. Các kiểu đóng gói thường gặp

| Kiểu artifact | Thành phần | Cách chạy/sử dụng |
|---|---|---|
| Library JAR | Class và resource của thư viện | Đưa vào compile/runtime classpath của ứng dụng khác |
| Thin executable JAR | Class ứng dụng và manifest | Chạy với dependency được cung cấp ngoài JAR |
| Fat/Uber JAR | Class ứng dụng cùng dependency được đóng gói vào một archive | Thường chạy trực tiếp bằng `java -jar` |
| Application distribution | JAR, thư viện riêng và script khởi chạy | Giải nén, cấu hình rồi chạy script hoặc classpath |
| Modular JAR | Class và `module-info.class` | Chạy trên module path hoặc dùng như module |

Không có một kiểu phù hợp cho mọi dự án. Library thường không nên tự gói toàn bộ dependency vào một fat JAR vì dễ xung đột phiên bản với ứng dụng tiêu thụ. Ứng dụng triển khai như service có thể dùng fat JAR hoặc distribution chứa thư viện riêng. Công cụ CLI có thể cần script khởi chạy để cấu hình JVM và classpath.

## 4. Chuẩn bị project Java tối giản

Tạo cấu trúc:

```text
jar-demo/
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── hello/
│                       └── App.java
├── out/
└── dist/
```

File `src/main/java/com/example/hello/App.java`:

```java
package com.example.hello;

public class App {
    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];

        System.out.println("Hello from executable JAR");
        System.out.println("Target: " + target);
    }
}
```

Class có package rõ ràng và một phương thức main hợp lệ. Tên class đầy đủ (fully qualified class name) là `com.example.hello.App`. Giá trị này sẽ được khai báo trong manifest.

## 5. Biên dịch class trước khi đóng gói

JAR chứa bytecode, vì vậy cần biên dịch source code thành file `.class` trước.

Tại thư mục gốc project, tạo thư mục output:

```sh
mkdir -p out dist
```

Biên dịch bằng JDK 17:

```sh
javac --release 17 -d out src/main/java/com/example/hello/App.java
```

Giải thích:

- `javac` là Java compiler.
- `--release 17` biên dịch theo Java 17 language/API target; compiler cũng kiểm tra API thuộc Java 17.
- `-d out` chỉ định thư mục chứa class output.
- Đường dẫn source có thể gồm nhiều file Java nếu ứng dụng có nhiều class.

Sau lệnh này, file được tạo tại:

```text
out/
└── com/
    └── example/
        └── hello/
            └── App.class
```

Nếu project dùng nhiều source file, có thể truyền danh sách file cho javac hoặc dùng build tool để quản lý source set và dependency. Không đưa file .java trực tiếp vào JAR thay cho bytecode nếu mục tiêu là chạy ứng dụng.

## 6. Tạo executable JAR bằng jar tool

JDK có công cụ `jar` để tạo, cập nhật, liệt kê và kiểm tra archive.

Tạo JAR có Main-Class:

```sh
jar --create --file dist/hello.jar --main-class com.example.hello.App -C out .
```

Các tham số:

- `--create`: tạo archive mới.
- `--file dist/hello.jar`: tên file đích.
- `--main-class com.example.hello.App`: ghi class khởi chạy vào manifest.
- `-C out .`: chuyển working directory của jar tool sang `out` và thêm toàn bộ nội dung thư mục đó vào archive.

Lệnh này tạo manifest tự động. Không cần tự tạo file manifest nếu chỉ cần một Main-Class đơn giản.

Chạy ứng dụng:

```sh
java -jar dist/hello.jar
```

Stdout:

```text
Hello from executable JAR
Target: local
```

Truyền argument:

```sh
java -jar dist/hello.jar production
```

Stdout:

```text
Hello from executable JAR
Target: production
```

Argument xuất hiện sau tên JAR được truyền vào `main(String[] args)`. Khi chạy qua service manager hoặc container, các argument này có thể được cấu hình trong command/entrypoint.

## 7. Chạy JAR và phân biệt các lệnh launcher

Có hai cách chạy phổ biến:

**Chạy theo Main-Class trong manifest:**

```sh
java -jar dist/hello.jar
```

**Chạy class bằng classpath:**

```sh
java -cp dist/hello.jar com.example.hello.App
```

Khác biệt:

- `java -jar` yêu cầu manifest có `Main-Class` và sử dụng class đó làm điểm vào.
- `java -cp` hoặc `java --class-path` chỉ định nơi launcher tìm class; sau classpath là tên class cần chạy.
- Khi dùng `-jar`, các thiết lập classpath bên ngoài như `-cp` và biến `CLASSPATH` bị bỏ qua. Dependency bổ sung cần được khai báo theo cách phù hợp, chẳng hạn manifest `Class-Path` hoặc fat JAR.
- Khi chạy bằng classpath, class chính phải được chỉ định trên command line.

Không nhầm `jar` (công cụ đóng gói) với `java` (launcher chạy chương trình).

## 8. Kiểm tra nội dung và manifest của JAR

Liệt kê entry trong archive:

```sh
jar --list --file dist/hello.jar
```

Output minh họa:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/hello/
com/example/hello/App.class
```

Thứ tự entry có thể khác tùy công cụ và cách tạo archive. Điều cần xác nhận là class nằm đúng package path và manifest có mặt.

Đọc manifest:

```sh
unzip -p dist/hello.jar META-INF/MANIFEST.MF
```

Hoặc giải nén archive để kiểm tra nội dung:

```sh
jar --extract --file dist/hello.jar --dir inspect
```

Sau khi extract, xem file `inspect/META-INF/MANIFEST.MF` và đường dẫn class.

Có thể dùng `javap` để xem bytecode/class signature:

```sh
javap -classpath dist/hello.jar com.example.hello.App
```

Kiểm tra artifact trước khi phát hành giúp phát hiện thiếu class, sai package, thiếu resource hoặc manifest không đúng.

## 9. Tự tạo manifest

Manifest là file text theo định dạng Java Manifest. Nó nằm tại `META-INF/MANIFEST.MF` trong JAR.

Ví dụ file `manifest.mf`:

```text
Manifest-Version: 1.0
Main-Class: com.example.hello.App
Implementation-Title: Hello Application
Implementation-Version: 1.0.0

```

Manifest có các quy tắc định dạng:

- Mỗi thuộc tính có dạng `Name: Value`.
- Phần main section kết thúc bằng dòng trống.
- File nên kết thúc bằng newline.
- Tên thuộc tính và giá trị phải tuân theo manifest specification.
- Dòng dài được jar tool xử lý theo quy tắc continuation của manifest; nếu tự tạo file, tránh cắt tùy tiện giữa một thuộc tính.

Đóng gói với manifest:

```sh
jar --create --file dist/hello.jar --manifest manifest.mf -C out .
```

Khi manifest đã khai báo `Main-Class`, không cần truyền thêm `--main-class`. Tránh khai báo hai giá trị Main-Class khác nhau.

Các thuộc tính metadata khác như `Implementation-Title` và `Implementation-Version` giúp công cụ vận hành nhận diện artifact. Không đặt secret, password hoặc token vào manifest vì manifest có thể được đọc bởi bất kỳ ai có file JAR.

## 10. Main-Class và điều kiện để chạy bằng java -jar

Thuộc tính `Main-Class` phải chứa tên class đầy đủ, không có hậu tố `.class`:

```text
Main-Class: com.example.hello.App
```

Class được chỉ định phải có phương thức entry point hợp lệ, ví dụ:

```java
public static void main(String[] args)
```

Nếu không có Main-Class, launcher có thể báo:

```text
no main manifest attribute, in dist/hello.jar
```

Nếu khai báo sai tên class, launcher thường báo không tìm thấy hoặc không tải được main class. Hãy kiểm tra:

1. Tên package trong source.
2. Class path bên trong JAR.
3. Giá trị Main-Class trong manifest.
4. Class có được biên dịch và đóng gói không.
5. Bytecode có tương thích với Java runtime không.

Một library JAR không cần Main-Class. Không thêm một main class giả chỉ để tất cả JAR đều chạy được bằng `java -jar`.

## 11. Đóng gói resource

Resource là dữ liệu ứng dụng cần khi chạy, ví dụ file properties, template, schema, certificate public, ảnh hoặc message bundle.

Với cấu trúc project chuẩn, đặt resource trong:

```text
src/main/resources/
└── config/
    └── app.properties
```

Nội dung `src/main/resources/config/app.properties`:

```properties
app.name=Jar Demo
app.environment=local
```

Khi build thủ công, copy resource vào output directory trước khi tạo JAR:

```sh
cp -R src/main/resources/. out/
jar --create --file dist/hello.jar --main-class com.example.hello.App -C out .
```

Khi dùng Maven hoặc Gradle, build tool thường tự động copy resource từ source set chuẩn vào output.

Đọc resource từ classpath:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class ResourceReader {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                ResourceReader.class.getResourceAsStream(
                        "/config/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing resource: config/app.properties");
            }
            properties.load(input);
        }

        System.out.println("app.name=" + properties.getProperty("app.name"));
        System.out.println("app.environment="
                + properties.getProperty("app.environment"));
    }
}
```

Stdout khi resource được đóng gói đúng:

```text
app.name=Jar Demo
app.environment=local
```

Không dùng `Path.of("config/app.properties")` để đọc resource nằm bên trong JAR như thể đó là file bình thường trên filesystem. Hãy dùng classpath resource API như `getResourceAsStream`. Nếu resource cần được sửa trong lúc chạy, hãy lưu bản runtime bên ngoài JAR ở thư mục cấu hình/dữ liệu được thiết kế riêng.

## 12. Dependency bên ngoài và thin JAR

Một JAR được tạo từ output class của ứng dụng thường chỉ chứa class/resource của project. Nó không tự động chứa các thư viện được dùng khi compile.

Ví dụ project sử dụng thư viện logging hoặc HTTP client. Nếu chỉ đóng gói class ứng dụng vào `app.jar` rồi chạy `java -jar app.jar`, runtime có thể báo `NoClassDefFoundError` hoặc `ClassNotFoundException` khi cần class của dependency.

Thin JAR là artifact chỉ chứa ứng dụng, còn dependency nằm ngoài. Có thể chạy với classpath:

Linux/macOS:

```sh
java -cp "app.jar:lib/*" com.example.hello.App
```

Windows:

```powershell
java -cp "app.jar;lib/*" com.example.hello.App
```

Dấu phân cách classpath là dấu hai chấm trên Unix-like OS và dấu chấm phẩy trên Windows. Wildcard `lib/*` được Java launcher hỗ trợ để đưa các JAR trong thư mục lib vào classpath.

Khi dùng classpath, chỉ định main class ở cuối lệnh. Không dùng `-jar` trong cùng lệnh với mục đích bổ sung `-cp` vì classpath ngoài bị bỏ qua khi `-jar` được sử dụng.

## 13. Manifest Class-Path cho dependency nằm ngoài JAR

Một executable JAR có thể khai báo dependency bên ngoài bằng thuộc tính `Class-Path` trong manifest.

Ví dụ cấu trúc:

```text
release/
├── app.jar
└── lib/
    ├── commons-text.jar
    └── logging.jar
```

Manifest của app.jar:

```text
Manifest-Version: 1.0
Main-Class: com.example.hello.App
Class-Path: lib/commons-text.jar lib/logging.jar

```

Giá trị Class-Path gồm các URL tương đối với vị trí JAR chứa manifest. Khi chuyển cả thư mục release sang máy khác, giữ nguyên cấu trúc tương đối để launcher tìm thấy dependency.

Manifest Class-Path không phải wildcard classpath. Hãy liệt kê các dependency cần thiết theo định dạng URL và thứ tự phù hợp.

Ưu điểm là có thể chạy:

```sh
java -jar release/app.jar
```

Nhược điểm là phải phát hành đúng cấu trúc thư mục và danh sách dependency. Nếu file lib bị thiếu hoặc sai version, ứng dụng vẫn không khởi chạy được.

## 14. Fat JAR hoặc Uber JAR

Fat JAR (còn gọi là Uber JAR) đóng gói class ứng dụng cùng dependency vào một archive. Đây là lựa chọn phổ biến cho service nhỏ hoặc ứng dụng triển khai bằng một file.

Ưu điểm:

- Dễ upload và quản lý một artifact.
- Lệnh khởi chạy đơn giản.
- Ít phụ thuộc vào cấu trúc thư mục lib bên ngoài.
- Thuận tiện cho container image khi chỉ cần copy một file.

Nhược điểm:

- Kích thước artifact lớn hơn.
- Dependency có thể xung đột class/resource.
- Service loader metadata cần được merge đúng.
- Signature của dependency có thể không còn hợp lệ sau khi unpack/repackage.
- Nâng một dependency thường yêu cầu build lại toàn bộ fat JAR.
- Không nên dùng fat JAR như cách mặc định cho mọi library.

Không tự giải nén mọi dependency rồi zip lại bằng một lệnh đơn giản nếu chưa xử lý resource trùng tên, service descriptors, module metadata và file signature trong META-INF. Dùng plugin chuyên dụng đã được kiểm tra.

## 15. Đóng gói bằng Maven

Maven sử dụng lifecycle và plugin để compile, test, package và tạo JAR. Với cấu trúc chuẩn, source nằm trong `src/main/java`, resource trong `src/main/resources` và artifact được tạo tại `target`.

Ví dụ `pom.xml` tối giản:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.hello.App</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Implementation-Title>Hello Application</Implementation-Title>
                            <Implementation-Version>1.0.0</Implementation-Version>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo JAR:

```sh
mvn clean package
```

Artifact:

```text
target/hello-1.0.0.jar
```

Chạy:

```sh
java -jar target/hello-1.0.0.jar
```

Maven JAR Plugin thêm Main-Class vào manifest. JAR mặc định không tự đóng gói dependency runtime vào bên trong; Maven quản lý dependency trong build classpath. Nếu cần executable package có dependency, chọn Maven Shade Plugin hoặc tạo distribution phù hợp và kiểm tra kết quả sau khi package.

Không dùng version plugin thay đổi theo máy developer. Pin version plugin trong POM hoặc parent build để CI và local build có hành vi nhất quán.

## 16. Đóng gói bằng Gradle

Gradle Java Plugin cung cấp task `jar`. Application Plugin bổ sung cách chạy ứng dụng và tạo distribution có script khởi chạy cùng thư viện runtime.

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("com.example.hello.App")
}

tasks.jar {
    manifest {
        attributes["Main-Class"] = "com.example.hello.App"
        attributes["Implementation-Version"] = project.version
    }
}
```

Build JAR:

```sh
./gradlew clean jar
```

Artifact thường ở:

```text
build/libs/<project-name>-1.0.0.jar
```

Chạy ứng dụng bằng runtime classpath do Gradle quản lý:

```sh
./gradlew run --args="production"
```

Tạo application distribution:

```sh
./gradlew installDist
./gradlew distZip
```

`installDist` tạo thư mục distribution gồm script chạy và thư viện runtime; `distZip` tạo ZIP distribution. Đây thường là lựa chọn phù hợp khi ứng dụng cần nhiều dependency mà không muốn gom tất cả vào một fat JAR.

Task `jar` mặc định không tự nhúng mọi dependency runtime. Nếu cần fat JAR trong Gradle, có thể dùng plugin như Shadow Plugin, pin version plugin và kiểm tra quy tắc merge resource/service descriptor.

## 17. So sánh Maven, Gradle và jar tool

| Công cụ | Phù hợp khi | Điểm cần nhớ |
|---|---|---|
| JDK jar tool | Project nhỏ, học cấu trúc archive hoặc đóng gói thủ công | Tự quản lý compile, resource và dependency |
| Maven JAR Plugin | Project dùng Maven lifecycle | Main-Class có thể cấu hình trong manifest; dependency không tự được nhúng |
| Gradle Java/Application Plugin | Project dùng Gradle và cần task build/run/distribution | jar tạo artifact; Application Plugin có installDist/distZip |
| Shade/Shadow plugin | Cần một fat/uber JAR | Phải xử lý resource, service metadata và dependency conflict |
| jpackage | Cần installer hoặc application image theo nền tảng | Đây là native distribution/installer, không phải cách tạo JAR |

Chọn công cụ theo cách project quản lý dependency, build lifecycle và deployment target. Không trộn nhiều cơ chế đóng gói trong một pipeline nếu chưa xác định artifact nào là đầu ra chính thức.

## 18. Modular JAR và module-info.java

Từ Java Platform Module System, một module có thể khai báo descriptor trong file `module-info.java`. Khi biên dịch, `module-info.class` được đặt ở root của output và đóng gói vào JAR.

Ví dụ `src/main/java/module-info.java`:

```java
module com.example.hello {
    exports com.example.hello;
}
```

Biên dịch:

```sh
javac --release 17 -d out src/main/java/module-info.java src/main/java/com/example/hello/App.java
```

Đóng gói:

```sh
jar --create --file dist/hello-module.jar --main-class com.example.hello.App -C out .
```

Xem module descriptor:

```sh
jar --describe-module --file dist/hello-module.jar
```

Có thể chạy module trên module path:

```sh
java --module-path dist/hello-module.jar --module com.example.hello/com.example.hello.App
```

Modular JAR vẫn là JAR. Điểm khác là module có tên và khai báo dependency/export rõ ràng. Nếu chạy một module không có main class trong descriptor, có thể chỉ định class chính bằng cú pháp module/class khi khởi chạy.

Không phải mọi JAR đều là named module. JAR không có module descriptor có thể được xử lý như automatic module trên module path theo quy tắc đặt tên module; tên suy ra có thể không ổn định nếu tên file không được quản lý cẩn thận.

## 19. JAR signing và xác minh chữ ký

JAR có thể được ký bằng công cụ `jarsigner`. Chữ ký giúp người nhận xác minh integrity của các entry đã ký và certificate signer theo trust policy.

Ví dụ lệnh ký (dùng keystore và alias đã được provision an toàn):

```sh
jarsigner -keystore release-keystore.p12 -storetype PKCS12 dist/hello.jar release-key
```

Xác minh:

```sh
jarsigner -verify -verbose -certs dist/hello.jar
```

Lệnh verify kiểm tra chữ ký entry theo cơ chế JAR signing. Để tin danh tính signer, còn phải xác minh certificate chain, fingerprint, thời hạn, revocation policy và trust store theo quy trình của tổ chức.

Không đưa password keystore vào source code hoặc command log. Trong CI, dùng signing service hoặc secret store, giới hạn quyền và audit thao tác ký.

Ký JAR làm thay đổi bytes của archive. Nếu phát hành cả checksum và chữ ký, hãy tạo checksum của artifact cuối cùng sau bước ký.

## 20. Kiểm tra version và compatibility của JAR

Trước khi phát hành, xác định rõ:

- JDK dùng để compile.
- Java release/target mà bytecode hỗ trợ.
- JRE tối thiểu cần để chạy.
- Dependency version và runtime scope.
- Operating system/architecture nếu artifact có thành phần native.
- Module path hay classpath.
- Cách truyền cấu hình và secret lúc runtime.

Kiểm tra Java version của môi trường:

```sh
java --version
javac --version
jar --version
```

Nếu compile bằng JDK 21 nhưng target release 17, dùng `--release 17` để compiler kiểm tra API của Java 17. Chỉ đặt `-source 17 -target 17` mà không giới hạn API có thể vô tình tham chiếu API mới hơn runtime target hỗ trợ.

Nếu dependency yêu cầu Java mới hơn target của ứng dụng, toàn bộ ứng dụng vẫn có thể không chạy trên runtime cũ. Hãy kiểm tra compatibility của dependency và bytecode trong release test.

## 21. Lưu ý về cấu hình khi chạy

Không đóng password, token, database URL có credential hoặc secret production vào JAR. JAR thường được lưu trong artifact repository, cache CI, container image và máy triển khai; nhiều người có thể tải hoặc inspect nó.

Cấu hình runtime nên đến từ:

- Environment variable được quản lý bởi deployment platform.
- Secret manager hoặc credential provider.
- File cấu hình bên ngoài có permission phù hợp.
- JVM system property cho giá trị không nhạy cảm.
- Config service có authentication và authorization.

Một JAR nên có thể chạy ở nhiều môi trường mà không cần build lại chỉ để thay URL hoặc password. Phân tách artifact bất biến với configuration riêng của môi trường giúp release dễ kiểm tra và rollback.

Nếu dùng resource mặc định trong JAR, có thể cho phép override bằng file cấu hình bên ngoài. Quy tắc ưu tiên cần được tài liệu hóa, ví dụ: command-line option > environment variable > external config > packaged default.

## 22. Kiểm tra JAR trước khi release

Một quy trình smoke test tối thiểu:

1. Build artifact từ source commit dự kiến.
2. Liệt kê nội dung bằng `jar --list`.
3. Đọc manifest và xác nhận Main-Class/version.
4. Xác nhận resource bắt buộc có trong archive.
5. Chạy bằng đúng Java runtime mục tiêu.
6. Chạy với argument/configuration đại diện.
7. Kiểm tra dependency runtime trên máy sạch/container mới.
8. Xác minh chữ ký nếu release có ký.
9. Tính SHA-256 của artifact cuối cùng.
10. Lưu artifact, checksum, version và commit metadata.

Không chỉ chạy `./gradlew run` hoặc `mvn exec:java` rồi kết luận JAR đã chạy đúng. Các task đó có thể chạy class từ build output và dependency classpath mà không sử dụng chính artifact JAR đã publish. Hãy chạy đúng file JAR hoặc distribution cuối cùng trong smoke test.

## 23. Lỗi thường gặp khi đóng gói JAR

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| no main manifest attribute | Thiếu Main-Class trong manifest | Cấu hình Main-Class hoặc dùng --main-class |
| Could not find or load main class | Sai package/class name hoặc thiếu class entry | Kiểm tra jar --list và manifest |
| NoClassDefFoundError | Dependency runtime không nằm trong classpath | Cung cấp lib, manifest Class-Path hoặc fat JAR |
| ClassNotFoundException | Classpath hoặc tên class sai | Kiểm tra -cp, package path và spelling |
| UnsupportedClassVersionError | Runtime cũ hơn bytecode target | Dùng runtime mới hoặc compile với --release phù hợp |
| Resource không tìm thấy | Resource chưa được copy vào JAR hoặc path sai | Kiểm tra src/main/resources và jar --list |
| Chạy được trong IDE nhưng không chạy bằng JAR | IDE cung cấp dependency/resource ngoài artifact | Smoke test artifact trên môi trường sạch |
| Chạy bằng -cp được nhưng -jar lỗi | Manifest Main-Class/Class-Path thiếu hoặc sai | Kiểm tra manifest; nhớ -jar bỏ qua -cp ngoài |
| Fat JAR lỗi ServiceLoader | META-INF/services bị ghi đè thay vì merge | Cấu hình transformer/service resource merge |
| JAR ký rồi nhưng verify fail | Archive bị sửa sau khi ký hoặc signature metadata không hợp lệ | Ký sau bước package cuối và verify lại |
| JAR chạy local nhưng fail production | Runtime/configuration/permission khác nhau | Kiểm tra Java version, env, path và dependency |
| Resource đọc được khi IDE nhưng lỗi sau đóng gói | Code dùng filesystem path cho resource trong archive | Dùng classpath resource API |
| JAR thiếu class khi chạy trên module path | Module descriptor hoặc module dependency không đúng | Kiểm tra module-info và --describe-module |

## 24. Pipeline phát hành JAR mẫu

Một pipeline CI có thể gồm các bước:

```text
Checkout commit
      |
      v
Select JDK/toolchain
      |
      v
Compile source and process resources
      |
      v
Run unit/integration tests
      |
      v
Package JAR or distribution
      |
      v
Inspect manifest and archive entries
      |
      v
Smoke test the packaged artifact
      |
      v
Sign artifact (if required)
      |
      v
Calculate checksum
      |
      v
Publish immutable versioned artifact
```

Artifact nên có tên và version rõ ràng, ví dụ `orders-service-2.4.0.jar`. Tránh ghi đè cùng version đã publish; nếu build lại, cần quy trình version/release mới hoặc metadata phân biệt.

Lưu cùng artifact các thông tin cần audit: source commit, build number, JDK/build tool version, dependency lock/verification state, test result, checksum và signature/provenance nếu có.

## 25. Checklist

- [ ] Đã hiểu JAR là ZIP archive có quy ước Java.
- [ ] Đã phân biệt library JAR, executable JAR, thin JAR, fat JAR và distribution.
- [ ] Đã tạo project với package và source layout rõ ràng.
- [ ] Đã compile bằng JDK và release target phù hợp.
- [ ] Đã tạo JAR bằng jar tool hoặc build tool.
- [ ] Đã khai báo Main-Class chính xác nếu cần java -jar.
- [ ] Đã kiểm tra META-INF/MANIFEST.MF.
- [ ] Đã đóng gói resource và đọc qua classpath API.
- [ ] Đã hiểu dependency không tự xuất hiện trong thin JAR.
- [ ] Đã chọn classpath, manifest Class-Path, fat JAR hoặc distribution phù hợp.
- [ ] Đã cấu hình Maven/Gradle plugin version và Java toolchain.
- [ ] Đã kiểm tra module-info nếu dùng JPMS.
- [ ] Đã xác minh JAR trên runtime mục tiêu.
- [ ] Đã smoke test chính artifact sau package.
- [ ] Đã ký artifact nếu release policy yêu cầu.
- [ ] Đã tính checksum sau bước ký.
- [ ] Đã giữ secret bên ngoài artifact.
- [ ] Đã lưu version, commit và build metadata.

## 26. Tài liệu tham khảo

- Oracle Java SE 17 — The jar Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 17 — JAR File Specification: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Oracle Java SE 17 — JAR Manifest: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html#jar-manifest
- Oracle Java SE 17 — jarsigner: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Apache Maven JAR Plugin — Usage: https://maven.apache.org/plugins/maven-jar-plugin/usage.html
- Gradle User Manual — The Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
- Gradle User Manual — Building Java Projects: https://docs.gradle.org/current/userguide/building_java_projects.html

Đóng gói JAR là bước biến bytecode và resource thành artifact có thể kiểm tra, phân phối và triển khai. Hãy khai báo đúng điểm vào, kiểm tra manifest và resource, cung cấp dependency theo một chiến lược rõ ràng, rồi smoke test chính artifact sau khi package. Maven/Gradle giúp tự động hóa quy trình, còn checksum, signature và metadata giúp release có thể truy vết và xác minh.