# Kiểm tra JAR bằng công cụ jar của JDK

JAR (Java ARchive) là định dạng lưu trữ dựa trên ZIP, dùng để đóng gói class file, resource, metadata và các thành phần của ứng dụng hoặc thư viện Java vào một tệp duy nhất. Công cụ **jar** đi kèm JDK giúp tạo, liệt kê, trích xuất, cập nhật và kiểm tra cấu trúc JAR.

Kiểm tra JAR là bước quan trọng khi đóng gói ứng dụng, điều tra lỗi classpath/module path, xác minh manifest, kiểm tra phiên bản class file, hoặc xác định một dependency có chứa đúng class và resource hay không. Một file có đuôi .jar chưa chắc là ứng dụng chạy độc lập; khả năng chạy bằng java -jar phụ thuộc vào manifest và cách đóng gói dependency.

## 1. JAR chứa những gì?

Một JAR là archive gồm các entry. Entry có thể là:

- Class file, ví dụ com/example/Main.class.
- Resource, ví dụ application.properties, ảnh, template hoặc file cấu hình.
- Manifest ở META-INF/MANIFEST.MF.
- Metadata về module, dịch vụ và chữ ký.
- Các entry đặc biệt của multi-release JAR trong META-INF/versions/.

Tên entry thường dùng dấu gạch chéo xuôi và phản ánh đường dẫn tương đối bên trong archive. Class có package com.example.Main phải nằm ở entry com/example/Main.class để class loader tìm thấy theo tên class.

JAR có thể được dùng như:

- **Library JAR**: cung cấp class và resource cho ứng dụng khác.
- **Executable JAR**: có manifest chỉ định Main-Class để chạy bằng java -jar.
- **Modular JAR**: chứa module descriptor module-info.class.
- **Multi-release JAR**: chứa implementation khác nhau theo Java release.
- **Signed JAR**: có metadata chữ ký để kiểm tra tính toàn vẹn và nguồn ký.

Các loại này không hoàn toàn loại trừ nhau. Ví dụ, một JAR có thể vừa modular vừa signed; một executable JAR cũng có thể là multi-release JAR.

## 2. Chuẩn bị và cú pháp jar

Công cụ jar nằm trong thư mục bin của JDK. Kiểm tra phiên bản và trợ giúp:

~~~bash
jar --version
jar --help
~~~

Cú pháp hiện đại dùng các chế độ dài:

~~~bash
jar --create --file archive.jar [options] [files]
jar --list --file archive.jar [options]
jar --extract --file archive.jar [files]
jar --update --file archive.jar [options] [files]
jar --describe-module --file archive.jar
~~~

Các dạng viết tắt truyền thống như c, t, x, u, f và v vẫn xuất hiện trong tài liệu và script cũ. Trong script mới, nên dùng dạng dài để dễ đọc:

| Chế độ | Tác dụng |
|---|---|
| --create | Tạo archive mới |
| --list | Liệt kê entry trong archive |
| --extract | Trích xuất entry |
| --update | Thêm hoặc cập nhật entry |
| --describe-module | Hiển thị module descriptor của JAR |
| --validate | Kiểm tra cấu trúc multi-release JAR |

Một lệnh jar thường thao tác trên file archive, không cần chạy ứng dụng. Việc liệt kê entry cũng không đồng nghĩa class trong JAR đã được JVM nạp hoặc xác minh khi thực thi.

## 3. Liệt kê nội dung JAR

Dùng --list để xem danh sách entry:

~~~bash
jar --list --file app.jar
~~~

Kết quả minh họa:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
com/example/Service.class
config/
config/application.properties
~~~

Dùng verbose để xem thêm thông tin như kích thước và timestamp:

~~~bash
jar --list --verbose --file app.jar
~~~

Liệt kê entry là bước đầu để kiểm tra:

- Class có nằm đúng package path hay không.
- Resource có được đóng gói hay bị thiếu.
- Manifest có tồn tại không.
- JAR có module-info.class hoặc các entry multi-release không.
- Có file hoặc package không mong muốn được đưa vào artifact không.

Nếu cần tìm một entry trong danh sách, có thể pipe output qua công cụ lọc của hệ điều hành.

Linux/macOS:

~~~bash
jar --list --file app.jar | grep 'Main.class'
~~~

Windows PowerShell:

~~~powershell
jar --list --file app.jar | Select-String 'Main.class'
~~~

Khi kiểm tra dependency, hãy chắc chắn đang đọc đúng file JAR và đúng phiên bản artifact. Nhiều phiên bản của cùng thư viện có thể tồn tại trong cache hoặc thư mục build.

## 4. Tạo JAR từ class file và resource

Giả sử project đã biên dịch thành thư mục classes:

~~~text
project/
  classes/
    com/example/Main.class
    com/example/Service.class
    config/app.properties
~~~

Tạo JAR:

~~~bash
jar --create --file app.jar -C classes .
~~~

Giải thích:

- --create yêu cầu tạo archive.
- --file app.jar chỉ định tên file kết quả.
- -C classes chuyển thư mục làm việc sang classes cho phần entry tiếp theo.
- Dấu chấm chọn toàn bộ nội dung trong thư mục đó.

Sau khi tạo, kiểm tra:

~~~bash
jar --list --file app.jar
~~~

Có thể thêm một nhóm file hoặc resource cụ thể:

~~~bash
jar --create --file library.jar -C classes com/example -C resources .
~~~

Mỗi cặp -C DIR áp dụng cho các file hoặc thư mục theo sau nó trong danh sách đối số cho đến khi gặp một -C khác. Hãy kiểm tra danh sách entry sau khi đóng gói để xác nhận cấu trúc archive đúng như mong muốn.

Không nên đưa cả thư mục project hoặc thư mục .git vào JAR. Chỉ đóng gói class và resource mà runtime hoặc người dùng thư viện thực sự cần.

## 5. Tạo executable JAR với Main-Class

Để chạy JAR bằng lệnh java -jar, manifest cần có thuộc tính Main-Class chứa tên đầy đủ của class có phương thức main phù hợp.

Ví dụ source:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d classes src/com/example/Main.java
~~~

Tạo JAR và đặt Main-Class:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Chạy:

~~~bash
java -jar app.jar
~~~

Stdout:

~~~text
Hello from executable JAR
~~~

Có thể xem manifest bằng cách trích xuất entry META-INF/MANIFEST.MF hoặc mở JAR bằng một công cụ đọc ZIP. Nội dung manifest minh họa:

~~~text
Manifest-Version: 1.0
Created-By: 17
Main-Class: com.example.Main
~~~

Tên class trong Main-Class phải là fully qualified name, dùng dấu chấm và không có phần mở rộng .class.

Executable JAR không tự động chứa mọi dependency. Nếu Main phụ thuộc vào thư viện ngoài, runtime cần tìm được các JAR đó qua manifest Class-Path, classpath được quản lý bởi launcher khác, hoặc một cơ chế đóng gói như fat/uber JAR do build tool tạo. Lệnh java -jar sử dụng cấu hình classpath của chế độ JAR và không dùng tùy chọn -cp để thay thế classpath đó.

## 6. Manifest và các thuộc tính quan trọng

Manifest là file metadata ở META-INF/MANIFEST.MF. Nó gồm các thuộc tính dạng tên: giá trị, chia thành main section và có thể có các section riêng cho entry.

Một manifest tùy chỉnh có thể được viết trong file MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Demo Application
Implementation-Version: 1.2.0
Automatic-Module-Name: com.example.demo
~~~

Tạo JAR từ manifest:

~~~bash
jar --create --file app.jar --manifest MANIFEST.MF -C classes .
~~~

Một số thuộc tính thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| Manifest-Version | Phiên bản định dạng manifest |
| Main-Class | Class khởi chạy khi dùng java -jar |
| Class-Path | Các URL tương đối để launcher tìm dependency của executable JAR |
| Implementation-Title | Tên sản phẩm hoặc implementation |
| Implementation-Version | Phiên bản implementation |
| Specification-Title | Tên specification mà thư viện triển khai |
| Specification-Version | Phiên bản specification |
| Automatic-Module-Name | Tên module ổn định khi JAR không có module-info.class |

Manifest có quy tắc định dạng riêng: mỗi thuộc tính nằm trên một dòng, dòng kết thúc bằng CRLF theo chuẩn manifest, section được ngăn cách bằng dòng trống và dòng dài có thể được gấp tiếp theo quy tắc của định dạng. Khi tự tạo manifest, dùng editor hoặc công cụ có hỗ trợ để tránh sai cú pháp.

Thuộc tính Class-Path dùng đường dẫn tương đối theo vị trí của JAR và các mục cách nhau bằng khoảng trắng. Nó không phải là cách thay thế tốt cho dependency management trong ứng dụng lớn. Với Maven/Gradle, thường nên để build hoặc launcher quản lý classpath một cách rõ ràng.

## 7. Trích xuất nội dung JAR

Để giải nén toàn bộ archive vào thư mục hiện tại:

~~~bash
jar --extract --file app.jar
~~~

Để chỉ trích xuất một số entry:

~~~bash
jar --extract --file app.jar com/example/Main.class META-INF/MANIFEST.MF
~~~

Nên chuyển tới một thư mục rỗng trước khi trích xuất để dễ kiểm soát file đầu ra:

Linux/macOS:

~~~bash
mkdir extracted
cd extracted
jar --extract --file ../app.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force extracted | Out-Null
Set-Location extracted
jar --extract --file ../app.jar
~~~

Sau khi giải nén, có thể dùng javap để đọc bytecode:

~~~bash
javap -c -p com.example.Main
~~~

Lệnh trên giả định đang ở thư mục gốc chứa package path com/example/Main.class. Nếu class nằm trong thư mục khác, dùng -classpath để chỉ rõ vị trí.

JAR là archive có thể chứa file thực thi, script, service provider hoặc resource không tin cậy. Trước khi giải nén hoặc đưa JAR vào classpath, hãy kiểm tra nguồn gốc và nội dung. Không chạy ứng dụng hoặc plugin chỉ vì archive giải nén thành công.

## 8. Cập nhật JAR

Dùng --update để thêm entry mới hoặc thay thế entry có cùng đường dẫn trong archive:

~~~bash
jar --update --file app.jar -C updated-classes .
~~~

Ví dụ cập nhật một resource:

~~~bash
jar --update --file app.jar -C resources config/app.properties
~~~

Sau khi cập nhật, liệt kê lại:

~~~bash
jar --list --file app.jar
~~~

Một số lưu ý:

- --update có thể thêm entry mới hoặc thay entry cùng tên.
- Việc cập nhật nội dung JAR đã ký có thể làm chữ ký không còn hợp lệ.
- Cập nhật manifest hoặc class có thể làm artifact khác với bản đã được kiểm thử và phát hành.
- jar không cung cấp một quy trình xóa entry tổng quát tương đương update. Nếu cần loại bỏ entry, hãy tạo archive mới từ tập file mong muốn hoặc dùng công cụ quản lý ZIP phù hợp.

Trong quy trình release, nên tạo artifact mới từ build sạch thay vì cập nhật thủ công JAR đã phát hành. Điều này giúp build có thể tái lập và dễ truy vết.

## 9. Kiểm tra modular JAR

Từ Java 9, module system cho phép đóng gói module trong JAR có module descriptor là module-info.class ở thư mục gốc.

Ví dụ cấu trúc:

~~~text
library.jar
  module-info.class
  com/example/api/Service.class
  com/example/internal/ServiceImpl.class
~~~

Xem mô tả module:

~~~bash
jar --describe-module --file library.jar
~~~

Kết quả minh họa:

~~~text
com.example.library
exports com.example.api
requires java.base mandated
~~~

Module descriptor xác định:

- Tên module.
- Các package được exports.
- Các module được requires.
- Các service được uses hoặc provides.
- Các package được opens cho reflection theo khai báo.

Nếu JAR không có module-info.class, nó có thể được dùng như automatic module khi đặt trên module path. Tên automatic module có thể được suy ra từ tên JAR hoặc lấy từ thuộc tính Automatic-Module-Name trong manifest.

Phân biệt classpath và module path:

- Trên classpath, class thuộc unnamed module và cơ chế truy cập package theo module system không được áp dụng như với named module.
- Trên module path, JVM/module system đọc module descriptor hoặc tạo automatic module.
- Một JAR chạy được trên classpath chưa chắc chạy được như named module vì có thể gặp vấn đề exports, requires, split package hoặc reflection access.

Để xem mô tả module của JDK, dùng lệnh java hoặc jmod phù hợp:

~~~bash
java --describe-module java.base
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

JMOD là định dạng đóng gói riêng của JDK; nó không phải JAR ứng dụng thông thường để phân phối trên classpath.

## 10. Multi-release JAR

Multi-release JAR cho phép một archive cung cấp class khác nhau cho các Java runtime khác nhau. Manifest phải có thuộc tính:

~~~text
Multi-Release: true
~~~

Các class dành cho release cụ thể được đặt dưới META-INF/versions/N/, trong đó N là số Java release.

Ví dụ:

~~~text
library.jar
  META-INF/
    MANIFEST.MF
    versions/
      11/
        com/example/Feature.class
      17/
        com/example/Feature.class
  com/
    example/
      Feature.class
~~~

Class ở thư mục gốc là implementation nền. Runtime Java 11 có thể chọn bản trong versions/11; runtime Java 17 có thể chọn bản trong versions/17 nếu có; nếu không có bản phù hợp thì dùng entry nền.

Tạo multi-release JAR bằng jar:

~~~bash
jar --create --file library.jar -C base-classes . --release 11 -C java11-classes . --release 17 -C java17-classes .
~~~

Tùy chọn --release VERSION đưa các file tiếp theo vào thư mục META-INF/versions/VERSION và đánh dấu manifest là multi-release. Các class trong từng thư mục phiên bản cần được biên dịch cho release tương ứng và phải giữ hợp đồng API mà thư viện công bố.

Kiểm tra cấu trúc:

~~~bash
jar --list --file library.jar
jar --validate --file library.jar
~~~

--validate kiểm tra các ràng buộc của multi-release JAR. Nó không thay thế việc chạy test trên từng runtime được hỗ trợ.

## 11. Kiểm tra chữ ký và tính toàn vẹn

JAR có thể được ký bằng công cụ **jarsigner**. Chữ ký giúp xác minh các entry được ký không bị thay đổi kể từ khi ký và cho biết chứng thư nào được dùng để ký.

Kiểm tra chữ ký:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Một số lưu ý:

- jar dùng để đóng gói và liệt kê; jarsigner dùng để ký và xác minh chữ ký.
- Kết quả verify cần được xem cùng thông tin chứng thư, chuỗi tin cậy, thời hạn và chính sách bảo mật.
- Một chữ ký hợp lệ về mặt mật mã không tự động chứng minh người ký đáng tin cậy.
- Thay đổi entry sau khi ký có thể làm xác minh thất bại hoặc khiến entry không còn được bảo vệ như mong đợi.
- Nên ký sau khi đã hoàn tất build, cập nhật manifest và mọi bước đóng gói.

Để kiểm tra chi tiết chứng thư và chữ ký, đọc output đầy đủ của jarsigner và dùng keytool khi cần xem truststore hoặc certificate chain. Không bỏ qua cảnh báo về chứng thư không đáng tin cậy, hết hạn hoặc thuật toán yếu.

## 12. Kiểm tra dependency và class bên trong JAR

Khi gặp lỗi ClassNotFoundException hoặc NoClassDefFoundError, trước tiên xác nhận class có thực sự nằm trong artifact:

~~~bash
jar --list --file dependency.jar
~~~

Có thể lọc theo tên class:

~~~bash
jar --list --file dependency.jar | grep 'com/example/Service.class'
~~~

Sau đó dùng javap để kiểm tra class:

~~~bash
javap -classpath dependency.jar -p com.example.Service
~~~

Dùng jdeps để phân tích dependency giữa các class hoặc module:

~~~bash
jdeps --summary dependency.jar
jdeps --jdk-internals dependency.jar
~~~

jdeps là công cụ riêng của JDK, không phải chế độ của jar. Nó giúp xem phụ thuộc package/module và phát hiện một số tham chiếu tới API nội bộ của JDK.

Các bước điều tra:

1. Xác định class đang bị thiếu hoặc không liên kết được.
2. Liệt kê nội dung JAR nghi ngờ bằng jar --list.
3. Kiểm tra tên package và đường dẫn entry.
4. Xác định classpath/module path thực tế lúc chạy.
5. Kiểm tra phiên bản JAR và dependency bắc cầu.
6. Kiểm tra class file version bằng javap nếu lỗi liên quan phiên bản runtime.
7. Chạy lại trên môi trường có cùng cấu hình với production.

Một class có trong JAR chưa chắc được class loader tìm thấy. JAR cũng phải nằm trên đúng classpath/module path và không bị xung đột với một class cùng tên từ nguồn khác.

## 13. JAR trong Maven và Gradle

Trong dự án thực tế, build tool thường tạo JAR từ output directory và resource đã được xử lý. Nên để Maven hoặc Gradle quản lý artifact thay vì tự đóng gói thủ công trong từng môi trường.

### Maven

Với packaging jar, Maven thường tạo artifact khi chạy:

~~~bash
mvn clean package
~~~

Artifact mặc định nằm trong thư mục target. Kiểm tra:

~~~bash
jar --list --file target/app-1.0.0.jar
~~~

Nếu cần cấu hình Main-Class và manifest metadata, dùng maven-jar-plugin:

~~~xml
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
                <Implementation-Version>1.0.0</Implementation-Version>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
~~~

Maven JAR Plugin tạo manifest và đóng gói artifact; nó khác với công cụ jar của JDK dù cùng tạo ra định dạng JAR.

### Gradle

Với Java plugin, task jar thường tạo archive trong build/libs:

~~~bash
gradle clean jar
~~~

Có thể cấu hình manifest trong build.gradle:

~~~groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.Main',
            'Implementation-Version': project.version
        )
    }
}
~~~

Kiểm tra artifact:

~~~bash
jar --list --file build/libs/app.jar
jar --describe-module --file build/libs/app.jar
~~~

Tên file thực tế phụ thuộc project name, version và archiveBaseName. Nếu dùng Shadow plugin hoặc công cụ tạo fat JAR, hãy kiểm tra cấu hình riêng và tránh nhầm archive do plugin tạo với JAR chuẩn của task jar.

## 14. Lỗi thường gặp khi kiểm tra JAR

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Main class không tìm thấy khi chạy java -jar | Manifest thiếu/sai Main-Class hoặc class không nằm đúng package path | Kiểm tra META-INF/MANIFEST.MF và entry class |
| ClassNotFoundException | Thiếu JAR trên classpath hoặc thiếu entry | Kiểm tra jar --list và lệnh khởi chạy |
| NoClassDefFoundError | Dependency có thể thiếu lúc runtime hoặc khởi tạo class thất bại | Kiểm tra dependency và nguyên nhân gốc trong stack trace |
| JAR chạy trên máy dev nhưng không chạy trên server | Khác JDK, dependency hoặc working directory | Kiểm tra runtime, manifest Class-Path và môi trường triển khai |
| Không thấy module descriptor | JAR không có module-info.class hoặc đang kiểm tra sai artifact | Liệt kê entry và chạy jar --describe-module |
| Signature verification failed | Entry bị sửa sau khi ký hoặc chữ ký/chứng thư có vấn đề | Build lại, ký lại sau cùng và xác minh certificate |
| Resource không tìm thấy | Resource không được đóng gói hoặc đường dẫn lookup sai | Kiểm tra entry path và cách dùng ClassLoader |
| Multi-release entry không được chọn | Thiếu Multi-Release: true hoặc sai thư mục phiên bản | Kiểm tra manifest và META-INF/versions |
| Archive cập nhật nhưng chữ ký lỗi | Nội dung đã thay đổi sau khi ký | Hoàn tất cập nhật trước khi ký lại |

## 15. Quy trình kiểm tra JAR trước khi phát hành

1. **Xác định artifact**: tên, version, module và loại JAR (library, executable, modular hay multi-release).
2. **Liệt kê entry**: dùng jar --list để kiểm tra class, resource, manifest và cấu trúc thư mục.
3. **Kiểm tra manifest**: xác nhận Main-Class, version metadata, Class-Path hoặc Automatic-Module-Name khi cần.
4. **Kiểm tra class file**: dùng javap để xem class version, descriptor và bytecode của class quan trọng.
5. **Kiểm tra module**: dùng jar --describe-module nếu artifact có module descriptor hoặc được dùng trên module path.
6. **Kiểm tra dependency**: dùng jdeps và build report để hiểu phụ thuộc, xác nhận dependency có mặt lúc chạy.
7. **Kiểm tra multi-release**: xem manifest, META-INF/versions và chạy jar --validate.
8. **Xác minh chữ ký**: dùng jarsigner -verify nếu artifact được ký.
9. **Chạy smoke test**: chạy executable JAR hoặc ứng dụng tích hợp trên đúng runtime mục tiêu.
10. **Lưu artifact và checksum**: quản lý phiên bản, nguồn build và checksum theo quy trình phát hành của dự án.

## 16. Ghi nhớ

- JAR là archive dựa trên ZIP, có thể chứa class, resource, manifest, module metadata và chữ ký.
- Dùng jar --list để xem entry, --create để tạo, --extract để giải nén và --update để thêm hoặc thay thế entry.
- Executable JAR cần Main-Class hợp lệ trong manifest; dependency phải được cung cấp riêng hoặc đóng gói theo chiến lược phù hợp.
- jar --describe-module giúp xem module descriptor; classpath và module path có quy tắc nạp khác nhau.
- Multi-release JAR dùng Multi-Release: true và các entry trong META-INF/versions/N.
- jarsigner là công cụ ký/xác minh; sửa JAR sau khi ký có thể làm chữ ký mất hiệu lực.
- jar --validate kiểm tra ràng buộc multi-release JAR, không thay thế test runtime.
- jar --list xác nhận entry tồn tại nhưng không chứng minh ứng dụng có thể nạp hoặc chạy được.
- Luôn kiểm tra artifact cuối cùng, dependency, manifest, class version và runtime trước khi phát hành.

## Tài liệu tham khảo chính thức

- [jar Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [JAR File Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [jarsigner Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Java Platform Module System — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)