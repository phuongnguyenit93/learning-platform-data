# Manifest trong JAR

**Manifest** là tệp metadata nằm trong gói JAR tại đường dẫn `META-INF/MANIFEST.MF`. Nó mô tả thông tin về archive và các thành phần bên trong, chẳng hạn lớp khởi chạy, classpath phụ thuộc, phiên bản sản phẩm, nhà cung cấp, thuộc tính package, thông tin module hoặc digest phục vụ ký JAR.

Manifest là một phần của định dạng JAR, không phải mã Java và cũng không phải một tệp cấu hình JVM độc lập. Các công cụ như `jar`, `java`, `jarsigner` và API `java.util.jar` sử dụng manifest theo những quy tắc khác nhau.

## 1. Vị trí và vai trò của MANIFEST.MF

Một JAR có cấu trúc ZIP. Manifest chuẩn nằm ở:

```text
META-INF/MANIFEST.MF
```

Ví dụ cấu trúc của một ứng dụng đã đóng gói:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        ├── Main.class
        └── Greeting.class
```

Manifest có thể cung cấp các thông tin như:

- Phiên bản định dạng manifest thông qua `Manifest-Version`.
- Lớp chứa điểm vào chương trình thông qua `Main-Class`.
- Các JAR/thư mục phụ thuộc thông qua `Class-Path`.
- Thông tin sản phẩm như `Implementation-Title`, `Implementation-Version`, `Implementation-Vendor`.
- Tên module tự động thông qua `Automatic-Module-Name`.
- Cách xử lý package hoặc archive đa phiên bản thông qua `Sealed`, `Multi-Release`.
- Thông tin digest của các entry trong quy trình ký JAR.

Manifest không tự chứa toàn bộ dependency và cũng không thay thế mã nguồn, bytecode, cấu hình build hay cơ chế bảo mật của ứng dụng. Nó là metadata được các công cụ và runtime diễn giải theo quy ước.

## 2. Cấu trúc cơ bản của manifest

Manifest là tệp văn bản gồm các header theo dạng:

```text
Attribute-Name: Attribute-Value
```

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Java Tooling Demo
Implementation-Version: 1.0.0

```

Một số quy tắc quan trọng:

- Header gồm tên thuộc tính, dấu hai chấm, một dấu cách và giá trị.
- Tên thuộc tính không phân biệt chữ hoa/chữ thường.
- Giá trị thuộc tính được giữ theo nội dung đã ghi; không nên tự giả định giá trị cũng không phân biệt hoa/thường.
- Các header trong main section được kết thúc bằng một dòng trống.
- Manifest có thể có nhiều section, mỗi section bắt đầu bằng header `Name` chỉ định entry mà section áp dụng.
- Nếu `Manifest-Version` xuất hiện, nó phải là header đầu tiên trong main section.
- Dòng trong manifest bị giới hạn độ dài theo byte; khi quá dài, phải ngắt dòng theo quy tắc continuation.

Manifest thường được ghi bằng UTF-8. Độ dài tối đa của một dòng là 72 byte, không tính ký tự kết thúc dòng. Nếu giá trị dài hơn, tiếp tục ở dòng kế tiếp bằng một dấu cách ở đầu dòng. Dấu cách đầu dòng tiếp nối không thuộc nội dung giá trị; khi đọc, các phần được ghép lại.

Ví dụ một giá trị dài được ngắt dòng:

```text
Implementation-Title: Java Core JDK Tooling Learning Application
Implementation-Version: 1.0.0
```

Với giá trị dài hơn 72 byte, công cụ tạo manifest nên tự xử lý việc ngắt dòng. Nếu tự viết manifest bằng tay, cần bảo đảm continuation đúng định dạng, đặc biệt khi có ký tự tiếng Việt vì một ký tự Unicode có thể chiếm nhiều byte UTF-8.

## 3. Main section và per-entry sections

Manifest có hai phạm vi chính.

### 3.1. Main section

Main section nằm ở đầu tệp và chứa các thuộc tính áp dụng chung cho archive. Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Example Application
Implementation-Version: 2.4.0
Implementation-Vendor: Example Team

```

Các thuộc tính như `Main-Class`, `Class-Path` và `Multi-Release` thường nằm trong main section.

### 3.2. Section theo từng entry

Sau dòng trống kết thúc main section, manifest có thể chứa các section dành cho từng entry trong JAR. Mỗi section bắt đầu bằng header `Name`:

```text
Manifest-Version: 1.0
Implementation-Title: Example Application

Name: com/example/Main.class
SHA-256-Digest: <digest-value>

Name: com/example/
Sealed: true

```

Section đầu tiên ở ví dụ trên gắn với entry `com/example/Main.class`; section thứ hai có thể dùng để đặt thuộc tính cho package `com.example`.

Khi một thuộc tính xuất hiện ở cả main section và section cụ thể, giá trị trong section cụ thể được ưu tiên cho entry tương ứng. Cách tổ chức này hữu ích cho thuộc tính package, sealing và các digest gắn với entry.

Tên entry dùng đường dẫn bên trong JAR, với dấu gạch chéo `/`, không dùng đường dẫn hệ điều hành. Ví dụ `com/example/Main.class` là entry name hợp lệ; `com\example\Main.class` không phải cách viết chuẩn trong manifest.

## 4. Tạo executable JAR với Main-Class

Thuộc tính `Main-Class` xác định lớp chứa phương thức khởi chạy mà lệnh `java -jar` sẽ gọi. Giá trị là tên lớp đầy đủ (binary name), bao gồm package, không có phần mở rộng `.class`.

Ví dụ:

```text
Main-Class: com.example.Main
```

Lớp đó cần có điểm vào phù hợp với phiên bản Java mục tiêu, ví dụ:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
```

Giả sử class file nằm trong thư mục `out`:

```text
out/
└── com/
    └── example/
        └── Main.class
```

Có thể tạo JAR và đặt Main-Class trực tiếp bằng công cụ `jar`:

```sh
jar --create --file app.jar --main-class com.example.Main -C out .
```

Hoặc tạo tệp `manifest.mf`:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main

```

Sau đó dùng tệp manifest khi đóng gói:

```sh
jar --create --file app.jar --manifest manifest.mf -C out .
```

Kiểm tra danh sách entry:

```sh
jar --list --file app.jar
```

Chạy ứng dụng:

```sh
java -jar app.jar
```

Kết quả:

```text
Hello from executable JAR
```

Nếu manifest không có `Main-Class`, lệnh `java -jar app.jar` thường báo lỗi không có main manifest attribute. Nếu tên lớp sai hoặc class file không được đóng gói, JVM sẽ không thể nạp lớp khởi chạy.

`Main-Class` chỉ khai báo điểm vào. Nó không tự biến JAR thành executable native và cũng không tự đưa dependency bên ngoài vào trong JAR.

## 5. Class-Path: khai báo thư viện phụ thuộc

Thuộc tính `Class-Path` trong main section liệt kê các URL mà class loader dùng để tìm thêm lớp khi chạy executable JAR. Các mục được phân tách bằng dấu cách.

Ví dụ cấu trúc:

```text
dist/
├── app.jar
└── lib/
    ├── commons.jar
    └── logging.jar
```

Manifest trong `app.jar`:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/commons.jar lib/logging.jar

```

Khi chạy:

```sh
java -jar dist/app.jar
```

Các URL tương đối trong `Class-Path` được phân giải dựa trên URL/vị trí của JAR chứa manifest. Vì vậy, `lib/commons.jar` ở ví dụ trên được tìm tương đối với thư mục chứa `app.jar`.

Các lưu ý quan trọng:

- `Class-Path` chỉ tham chiếu đến dependency bên ngoài; nó không sao chép hoặc đóng gói các JAR đó vào archive.
- Các mục được phân tách bằng khoảng trắng, không dùng dấu hai chấm hoặc dấu chấm phẩy như biến môi trường `CLASSPATH`.
- Đường dẫn có khoảng trắng cần được mã hóa đúng theo quy tắc URL, ví dụ dùng `%20`, thay vì viết một khoảng trắng khiến parser hiểu thành hai mục.
- Đường dẫn tương đối sẽ không còn đúng nếu di chuyển JAR mà không di chuyển thư mục dependency theo cùng cấu trúc.
- Dependency phải thực sự có mặt và có thể đọc được khi chạy.
- Khi dùng `java -jar`, các tùy chọn classpath bên ngoài như `-cp` không được dùng làm classpath ứng dụng thay cho cấu hình của chế độ `-jar`; hãy khai báo dependency theo cách đóng gói phù hợp.

Có thể kiểm tra dependency và classpath thực tế khi chạy bằng cách dùng `-verbose:class`:

```sh
java -verbose:class -jar app.jar
```

Log sẽ cho biết các lớp được nạp từ nguồn nào, hữu ích khi điều tra thiếu hoặc xung đột dependency.

## 6. Các thuộc tính manifest thường dùng

Một số thuộc tính phổ biến trong main section:

| Thuộc tính | Ý nghĩa |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest; thường là `1.0` |
| `Main-Class` | Tên lớp chứa điểm vào khi chạy bằng `java -jar` |
| `Class-Path` | Danh sách URL dependency bổ sung |
| `Created-By` | Công cụ tạo archive/manifest |
| `Build-Jdk-Spec` | Phiên bản Java specification của JDK dùng để build |
| `Implementation-Title` | Tên sản phẩm hoặc phần triển khai |
| `Implementation-Version` | Phiên bản phần triển khai |
| `Implementation-Vendor` | Nhà cung cấp phần triển khai |
| `Specification-Title` | Tên specification mà JAR thực hiện |
| `Specification-Version` | Phiên bản specification |
| `Specification-Vendor` | Nhà cung cấp specification |
| `Automatic-Module-Name` | Tên module ổn định cho JAR khi dùng trên module path và không có module descriptor tường minh |
| `Multi-Release` | Đánh dấu JAR có nội dung theo nhiều phiên bản Java |
| `Sealed` | Thiết lập package sealing mặc định cho các package trong archive |

Có thể bổ sung thuộc tính riêng của ứng dụng, nhưng nên dùng tên rõ ràng và tránh xung đột với các tên chuẩn. Thuộc tính tùy chỉnh không tự có ý nghĩa với JVM; ứng dụng hoặc công cụ phải chủ động đọc và diễn giải chúng.

## 7. Đọc manifest bằng Java

Java cung cấp API trong package `java.util.jar` để đọc manifest mà không cần tự giải nén hoặc phân tích văn bản.

Ví dụ:

```java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class ReadManifest {
    public static void main(String[] args) throws IOException {
        try (JarFile jar = new JarFile("app.jar")) {
            Manifest manifest = jar.getManifest();

            if (manifest == null) {
                System.out.println("No manifest");
                return;
            }

            Attributes attributes = manifest.getMainAttributes();

            System.out.println(
                attributes.getValue(Attributes.Name.MAIN_CLASS)
            );
            System.out.println(
                attributes.getValue("Implementation-Version")
            );
        }
    }
}
```

Nếu manifest có:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Version: 2.4.0

```

Kết quả:

```text
com.example.Main
2.4.0
```

`JarFile.getManifest()` trả về đối tượng `Manifest`, hoặc `null` nếu archive không có manifest. `getMainAttributes()` lấy các thuộc tính chung. Để đọc section của một entry cụ thể, dùng:

```java
Attributes entryAttributes =
    manifest.getAttributes("com/example/Main.class");
```

Tên entry truyền vào phải khớp đường dẫn bên trong JAR. Giá trị trả về có thể là `null` nếu không có section cho entry đó.

## 8. Tạo manifest bằng Maven

Với Maven, cấu hình `maven-jar-plugin` để thêm `Main-Class` và các thuộc tính khác:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>com.example.Main</mainClass>
                    </manifest>
                    <manifestEntries>
                        <Implementation-Title>Java Tooling Demo</Implementation-Title>
                        <Implementation-Version>1.0.0</Implementation-Version>
                        <Implementation-Vendor>Example Team</Implementation-Vendor>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Build:

```sh
mvn clean package
```

JAR được tạo trong thư mục `target` với manifest do plugin cấu hình. Tên tệp thường dựa trên artifactId và version của Maven project.

Maven JAR Plugin đóng gói các class/resource của project theo cấu hình; cấu hình `Main-Class` không tự đưa mọi dependency runtime vào trong JAR. Nếu muốn phân phối một JAR chứa dependency, cần dùng cách đóng gói phù hợp như shaded/uber JAR hoặc phân phối dependency bên cạnh và cấu hình classpath.

## 9. Tạo manifest bằng Gradle

Với Gradle Groovy DSL, có thể đặt thuộc tính cho task `jar`:

```groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.Main',
            'Implementation-Title': 'Java Tooling Demo',
            'Implementation-Version': '1.0.0',
            'Implementation-Vendor': 'Example Team'
        )
    }
}
```

Chạy:

```sh
./gradlew clean jar
```

Trên Windows:

```powershell
gradlew.bat clean jar
```

JAR thường nằm trong `build/libs`. Kiểm tra manifest:

```sh
jar --extract --file build/libs/app.jar META-INF/MANIFEST.MF
```

Sau khi giải nén entry manifest, đọc tệp `META-INF/MANIFEST.MF`. Tên JAR thực tế phụ thuộc cấu hình project.

Cấu hình `Main-Class` chỉ xác định entry point. Nếu project có dependency runtime, cần thêm cách phân phối phù hợp: đặt JAR dependency cạnh ứng dụng và khai báo `Class-Path`, tạo fat JAR bằng plugin, hoặc dùng cơ chế packaging của framework. Không giả định task `jar` mặc định tự đóng gói dependency.

## 10. Multi-Release JAR

Multi-release JAR cho phép một archive chứa các phiên bản class/resource khác nhau cho các Java release khác nhau. Manifest cần có:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Các lớp dành riêng cho phiên bản được đặt dưới:

```text
META-INF/versions/<N>/
```

Ví dụ:

```text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/PlatformHelper.class
│       └── 17/
│           └── com/example/PlatformHelper.class
└── com/
    └── example/
        └── PlatformHelper.class
```

Khi chạy trên một Java release hỗ trợ multi-release JAR, runtime chọn phiên bản entry phù hợp cao nhất không vượt quá phiên bản Java đang chạy; nếu không có entry tương ứng, dùng bản ở gốc archive. JAR phải có `Multi-Release: true`; nếu thiếu hoặc không phải `true`, các thư mục versioned không được xử lý như lớp thay thế theo cơ chế multi-release.

Cơ chế này hữu ích khi thư viện muốn tối ưu cho API mới nhưng vẫn giữ một triển khai nền tương thích với Java cũ hơn. Các phiên bản class trong thư mục versioned phải tuân theo quy tắc tương thích của JAR spec và không được làm thay đổi API công khai theo cách gây bất ngờ cho người dùng.

## 11. Package sealing

Package sealing là cơ chế khai báo rằng các lớp thuộc một package phải được nạp từ cùng một nguồn JAR/code source theo quy tắc của class loader. Nó giúp ngăn việc ghép các lớp cùng package từ nhiều archive khác nhau trong các trường hợp cần bảo vệ tính toàn vẹn package.

Để seal tất cả package trong JAR, đặt trong main section:

```text
Manifest-Version: 1.0
Sealed: true

```

Để chỉ seal một package, dùng section theo package:

```text
Manifest-Version: 1.0

Name: com/example/
Sealed: true

```

Thuộc tính `Sealed` trong section cụ thể có thể ghi đè giá trị mặc định ở main section cho package đó. Nếu lớp cùng package được nạp từ nguồn khác sau khi package đã được seal, class loader có thể ném `SecurityException` với thông báo sealing violation.

Sealing không thay thế chữ ký số, kiểm soát quyền truy cập hoặc sandbox. Nó là quy tắc về nguồn gốc lớp trong package, được class loader áp dụng khi định nghĩa package.

## 12. Manifest và ký số JAR

Quy trình ký JAR sử dụng manifest cùng các tệp chữ ký trong `META-INF`. Thông thường có:

```text
META-INF/
├── MANIFEST.MF
├── SIGNER.SF
└── SIGNER.RSA
```

Tên và phần mở rộng của signature block phụ thuộc thuật toán/chứng thư, ví dụ `.RSA`, `.DSA` hoặc `.EC`.

Manifest có thể chứa digest của từng entry. Tệp chữ ký `.SF` chứa digest liên quan đến manifest hoặc các phần của manifest; signature block chứa chữ ký mật mã của tệp chữ ký. Công cụ xác minh dùng các dữ liệu này để phát hiện thay đổi nội dung đã ký.

Có thể xác minh JAR bằng:

```sh
jarsigner -verify -verbose -certs app.jar
```

Lưu ý:

- Chỉ thêm `Main-Class` hoặc `Implementation-Version` không có nghĩa JAR đã được ký.
- Manifest không tự bảo đảm tính xác thực của archive.
- Sửa hoặc đóng gói lại một JAR đã ký có thể làm digest/chữ ký không còn hợp lệ.
- Hãy hoàn thiện nội dung, manifest và dependency trước, sau đó mới ký.
- Không coi việc lệnh verify chạy thành công là đánh giá đầy đủ độ tin cậy của nhà phát hành; cần kiểm tra chứng thư, chuỗi tin cậy và chính sách triển khai.

Không nên sửa manifest của JAR đã ký rồi tiếp tục phân phối như thể chữ ký cũ còn nguyên vẹn. Nếu thay đổi nội dung archive, hãy thực hiện lại quy trình ký bằng khóa và chứng thư hợp lệ.

## 13. Kiểm tra manifest trong JAR

Có thể dùng công cụ `jar` để liệt kê và trích xuất manifest:

```sh
jar --list --file app.jar
jar --extract --file app.jar META-INF/MANIFEST.MF
```

Lệnh đầu liệt kê các entry trong JAR. Lệnh thứ hai trích xuất manifest vào đường dẫn `META-INF/MANIFEST.MF` dưới thư mục hiện tại. Nếu đường dẫn đích đã tồn tại, hãy chú ý tránh ghi đè tệp đang cần giữ.

Có thể đọc nội dung manifest mà không giải nén toàn bộ JAR bằng một tiện ích ZIP như `unzip -p` nếu công cụ đó có sẵn:

```sh
unzip -p app.jar META-INF/MANIFEST.MF
```

Hoặc dùng API Java `JarFile` như phần trước.

Khi kiểm tra một JAR được tạo tự động bởi Maven/Gradle, đừng chỉ nhìn cấu hình trong build file. Hãy kiểm tra manifest thực tế trong artifact được phát hành, vì plugin, task khác hoặc quy trình đóng gói có thể bổ sung hoặc ghi đè thuộc tính.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | JAR không có `Main-Class` trong main section | Thêm Main-Class và tạo lại JAR |
| `Could not find or load main class` | Tên Main-Class sai hoặc class file không nằm trong archive | Kiểm tra tên đầy đủ và liệt kê JAR bằng `jar --list` |
| `ClassNotFoundException` cho dependency | Thiếu JAR trong Class-Path hoặc URL tương đối sai | Kiểm tra vị trí dependency tương đối với JAR và nội dung manifest |
| Chạy bằng `java -cp` được nhưng `java -jar` lỗi | Chế độ `-jar` dùng manifest/entry point riêng; classpath ngoài không thay thế được manifest | Đặt Main-Class và dependency đúng trong manifest hoặc đóng gói dependency |
| Thuộc tính manifest không có hiệu lực | Đặt nhầm section, sai tên header hoặc đọc nhầm artifact | Kiểm tra vị trí thuộc tính, tên entry và manifest thực tế |
| Manifest bị parser từ chối | Dòng không đúng định dạng, thiếu dấu cách sau dấu hai chấm hoặc ngắt dòng sai | Tuân thủ cú pháp header và continuation; ưu tiên công cụ tạo manifest |
| Dependency không tìm thấy sau khi di chuyển ứng dụng | Class-Path dùng đường dẫn tương đối đến vị trí cũ | Di chuyển cả thư mục dependency theo cấu trúc hoặc đóng gói theo cách khác |
| `SecurityException: sealing violation` | Lớp cùng package được nạp từ nguồn khác với package đã seal | Kiểm tra manifest sealing và cách chia package giữa các JAR |
| JAR signature invalid | Nội dung/manifest bị thay đổi sau khi ký hoặc digest không khớp | Đóng gói hoàn chỉnh rồi ký lại và xác minh |
| Lớp phiên bản mới trong multi-release JAR không được chọn | Thiếu `Multi-Release: true`, sai thư mục version hoặc runtime không hỗ trợ | Kiểm tra manifest, đường dẫn `META-INF/versions/N` và phiên bản JVM |

## 15. Checklist khi tạo JAR có manifest

- [ ] JAR chứa `META-INF/MANIFEST.MF`.
- [ ] Main section có `Manifest-Version: 1.0` khi cần.
- [ ] `Main-Class` là tên lớp đầy đủ và lớp đó có điểm vào hợp lệ.
- [ ] Các dependency cần thiết được đóng gói hoặc khai báo qua Class-Path đúng cách.
- [ ] URL tương đối trong Class-Path vẫn hợp lệ sau khi triển khai.
- [ ] Thuộc tính tùy chỉnh có tên rõ ràng và được đặt đúng section.
- [ ] Dòng dài tuân thủ giới hạn byte và continuation format.
- [ ] Multi-Release và Sealed chỉ bật khi archive được cấu trúc tương ứng.
- [ ] Manifest được kiểm tra trong artifact cuối, không chỉ trong file cấu hình.
- [ ] Nếu ký số, chỉ ký sau khi đã hoàn tất archive và xác minh lại chữ ký.

Manifest là lớp metadata quan trọng của JAR. Nắm được main section, per-entry sections, Main-Class, Class-Path, thuộc tính package và cơ chế ký giúp bạn tạo artifact dễ chạy, dễ kiểm tra và có thể triển khai nhất quán giữa môi trường phát triển, kiểm thử và production.