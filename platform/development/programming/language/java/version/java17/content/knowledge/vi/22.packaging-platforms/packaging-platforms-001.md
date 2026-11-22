# Đóng gói JAR và khai báo lớp khởi chạy trong Java 17

Một ứng dụng Java thường được biên dịch thành nhiều file .class, có thể kèm resource như cấu hình, mẫu email hoặc ảnh. Khi triển khai, việc gửi từng file và giữ đúng cấu trúc thư mục dễ gây nhầm lẫn. **JAR (Java Archive)** gom các class và resource vào một file archive để phân phối, chạy hoặc dùng làm thư viện.

Để chạy một JAR trực tiếp bằng lệnh java -jar, archive cần khai báo lớp khởi chạy trong manifest thông qua thuộc tính Main-Class. Lớp đó phải cung cấp entry point hợp lệ mà Java launcher có thể gọi. Nếu ứng dụng có dependency, cần bảo đảm các thư viện đó cũng nằm trên classpath hoặc được đóng gói theo cách mà launcher/build tool hỗ trợ.

Bài này trình bày cách tạo JAR bằng công cụ jar của JDK 17, khai báo Main-Class, chạy bằng java -jar, xử lý dependency, phân biệt JAR thông thường với modular JAR và kiểm tra artifact trước khi triển khai.

## 1. JAR là gì?

JAR là định dạng archive dựa trên ZIP, được dùng để gom các thành phần của ứng dụng Java vào một file. Một JAR có thể chứa:

- Bytecode .class đã biên dịch.
- Resource như .properties, JSON, XML, template hoặc ảnh.
- Metadata trong thư mục META-INF.
- Manifest mô tả thông tin archive, trong đó có thể khai báo lớp khởi chạy.
- Chữ ký số và metadata liên quan nếu archive được ký.

Ví dụ cấu trúc một JAR đơn giản:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── app/
            ├── Main.class
            └── GreetingService.class
```

JAR không phải định dạng bytecode riêng. Các file .class bên trong vẫn là bytecode JVM; JAR chỉ đóng gói chúng cùng resource và metadata.

### 1.1. JAR thư viện và executable JAR

Có hai cách sử dụng JAR phổ biến:

| Loại | Mục đích | Cách dùng thường gặp |
| --- | --- | --- |
| Library JAR | Cung cấp class/resource để ứng dụng khác sử dụng | Đặt trên classpath hoặc module path |
| Executable JAR | Có entry point để khởi chạy ứng dụng | java -jar app.jar |

Một JAR thư viện không nhất thiết có Main-Class. Một executable JAR thông thường cần manifest có Main-Class để lệnh java -jar biết phải gọi lớp nào.

Việc có Main-Class không tự biến mọi dependency thành một phần của JAR. Archive chỉ chứa những file được đóng gói vào đó; thư viện bên ngoài vẫn phải được cung cấp cho runtime.

## 2. Chuẩn bị mã nguồn và thư mục output

Giả sử ứng dụng có một lớp khởi chạy trong package com.example.app:

```text
jar-demo/
├── src/
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
└── out/
```

Nội dung Main.java:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a JAR");

        if (args.length > 0) {
            System.out.println("First argument: " + args[0]);
        }
    }
}
```

Điểm vào ứng dụng là phương thức:

```java
public static void main(String[] args)
```

Java launcher tìm phương thức main theo quy ước này. Tên lớp trong manifest là tên đầy đủ gồm package, ví dụ com.example.app.Main, không phải tên file Main.java hoặc Main.class.

### 2.1. Biên dịch bằng javac

Từ thư mục jar-demo, biên dịch mã nguồn vào thư mục out:

```bash
javac -d out src/com/example/app/Main.java
```

Sau khi biên dịch:

```text
out/
└── com/
    └── example/
        └── app/
            └── Main.class
```

Tùy chọn -d out yêu cầu compiler ghi file .class vào thư mục output và tạo các thư mục package tương ứng. JAR thường được tạo từ bytecode đã biên dịch, không phải từ file .java.

Nếu ứng dụng có nhiều source file, có thể liệt kê chúng hoặc dùng cơ chế build để quản lý source set. Ví dụ:

```bash
javac -d out src/com/example/app/Main.java src/com/example/app/GreetingService.java
```

## 3. Tạo JAR bằng công cụ jar

JDK 17 có công cụ dòng lệnh jar. Tạo JAR từ thư mục output:

```bash
jar --create --file app.jar -C out .
```

Ý nghĩa:

- --create tạo archive mới.
- --file app.jar chỉ định tên file JAR đầu ra.
- -C out . chuyển thư mục làm việc của lệnh đóng gói sang out rồi thêm toàn bộ nội dung thư mục đó vào archive.

JAR sau khi tạo sẽ có các entry theo package, ví dụ com/example/app/Main.class. Không có thư mục out/ ở đầu đường dẫn entry vì -C out . đóng gói nội dung bên trong out.

### 3.1. Tạo executable JAR bằng --main-class

Để khai báo lớp khởi chạy ngay khi tạo archive:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out .
```

Tùy chọn --main-class (viết tắt -e) đặt entry point cho archive. Với JAR thông thường, công cụ ghi thuộc tính Main-Class vào manifest.

Có thể kiểm tra nội dung archive:

```bash
jar --list --file app.jar
```

Kết quả ví dụ:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/app/
com/example/app/Main.class
```

### 3.2. Kiểm tra manifest

Manifest nằm tại:

```text
META-INF/MANIFEST.MF
```

Nội dung chính có dạng:

```text
Manifest-Version: 1.0
Created-By: 17
Main-Class: com.example.app.Main

```

Các dòng metadata có thể khác tùy cách tạo JAR và bản JDK. Thuộc tính quan trọng cho java -jar là Main-Class.

### 3.3. Tạo manifest thủ công

Có thể tạo file MANIFEST.MF:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

```

Manifest phải có dòng trống kết thúc phần main attributes. Sau đó tạo JAR:

```bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
```

Tên thuộc tính không phân biệt chữ hoa/thường theo quy tắc manifest, nhưng nên viết đúng dạng chuẩn Main-Class. Giá trị phải là tên lớp đầy đủ và không có phần mở rộng .class.

Nếu đã dùng --main-class, thường không cần tạo manifest thủ công chỉ để đặt Main-Class. Manifest riêng hữu ích khi cần khai báo thêm metadata như Class-Path hoặc thông tin phiên bản.

## 4. Chạy executable JAR bằng java -jar

Khi manifest có Main-Class hợp lệ:

```bash
java -jar app.jar
```

Kết quả:

```text
Hello from a JAR
```

Java launcher đọc manifest, nạp lớp được chỉ định và gọi phương thức main.

### 4.1. Truyền tham số cho ứng dụng

Các đối số đặt sau tên JAR được truyền vào main(String[] args):

```bash
java -jar app.jar production --port 8080
```

Trong chương trình:

```java
public static void main(String[] args) {
    for (String arg : args) {
        System.out.println(arg);
    }
}
```

Mảng args không chứa tên JAR hoặc tùy chọn JVM đã dùng để khởi chạy. Nó chỉ chứa các đối số ứng dụng đặt sau JAR.

### 4.2. Truyền tùy chọn JVM

Tùy chọn dành cho JVM phải đặt trước -jar:

```bash
java -Xms256m -Xmx1g -Dapp.environment=production -jar app.jar
```

Trong đó:

- -Xms256m đặt heap ban đầu.
- -Xmx1g đặt giới hạn heap tối đa.
- -Dapp.environment=production tạo system property cho ứng dụng.

Các tham số sau app.jar được truyền cho ứng dụng:

```bash
java -Dapp.environment=production -jar app.jar --port 8080
```

### 4.3. Lỗi no main manifest attribute

Nếu chạy:

```bash
java -jar library.jar
```

và nhận lỗi no main manifest attribute, manifest của JAR không có Main-Class mà launcher cần.

Có thể xử lý bằng cách:

- Nếu JAR là ứng dụng, tạo lại với --main-class hoặc manifest chứa Main-Class.
- Nếu JAR chỉ là thư viện, chạy một lớp main riêng trên classpath thay vì giả định thư viện là executable.

Không nên thêm một Main-Class tùy ý vào library JAR nếu archive không được thiết kế để khởi chạy như ứng dụng.

## 5. Khai báo lớp khởi chạy chính xác

Main-Class là tên lớp đầy đủ của entry point:

```text
Main-Class: com.example.app.Main
```

Các lỗi phổ biến:

| Khai báo sai | Vì sao sai |
| --- | --- |
| Main-Class: Main | Thiếu package nếu lớp thuộc com.example.app. |
| Main-Class: com/example/app/Main | Dùng đường dẫn file thay cho tên lớp Java. |
| Main-Class: com.example.app.Main.class | Không thêm phần mở rộng .class. |
| Main-Class: com.example.app | Đây là package, không phải lớp. |
| Main-Class: com.example.app.Main.java | Manifest tham chiếu lớp đã biên dịch, không phải source file. |

Lớp khởi chạy phải có phương thức main hợp lệ, thông thường:

```java
public static void main(String[] args)
```

Phương thức có thể khai báo throws nếu cần. Nếu lớp không tồn tại trong JAR hoặc không có entry point hợp lệ, launcher sẽ báo lỗi khi chạy.

### 5.1. Ứng dụng có nhiều lớp chứa main

Một dự án có thể có nhiều lớp với phương thức main, chẳng hạn:

- com.example.app.ServerMain
- com.example.app.MigrationMain
- com.example.app.AdminMain

Một manifest chỉ khai báo một Main-Class mặc định cho java -jar. Nếu cần nhiều chế độ chạy, có thể:

1. Tạo các JAR riêng với entry point khác nhau.
2. Dùng một lớp launcher duy nhất để đọc đối số rồi điều phối sang các chức năng.
3. Chạy trực tiếp lớp mong muốn bằng java -cp ... fully.qualified.ClassName.

Không nên dựa vào thứ tự class trong archive để chọn lớp khởi chạy.

## 6. JAR có resource

Ứng dụng thường cần đóng gói file cấu hình hoặc resource cùng bytecode:

```text
jar-demo/
├── src/
│   └── com/example/app/Main.java
├── resources/
│   └── app.properties
└── out/
```

Có thể copy resource vào output trước khi đóng gói, hoặc thêm thư mục resource bằng -C:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out . -C resources .
```

Khi đó app.properties nằm ở root của JAR. Có thể đọc resource qua class loader:

```java
try (var input = Main.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing app.properties");
    }
    // Đọc nội dung từ input.
}
```

Không nên dùng đường dẫn filesystem như new File("app.properties") để đọc resource được đóng gói bên trong JAR. Resource trong archive không nhất thiết là file riêng trên filesystem; hãy dùng classpath/module resource API.

## 7. Dependency: JAR không tự gom các thư viện khác

Một ứng dụng có thể phụ thuộc vào thư viện ngoài:

```text
app.jar
lib/
├── logging.jar
└── database-driver.jar
```

Lệnh tạo JAR cơ bản chỉ đóng gói các file được chỉ định. Nó không tự tìm và nhúng dependency từ Maven hoặc Gradle.

Có hai cách thường dùng để cung cấp dependency cho ứng dụng không modular.

### 7.1. Chạy bằng classpath

Thay vì java -jar, có thể chỉ định classpath và tên lớp:

Trên Linux/macOS, dấu phân cách classpath là dấu hai chấm:

```bash
java -cp "app.jar:lib/*" com.example.app.Main
```

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

```powershell
java -cp "app.jar;lib/*" com.example.app.Main
```

Wildcard lib/* cho phép launcher đưa các JAR trong thư mục lib vào classpath. Tên lớp khởi chạy được chỉ định trực tiếp sau -cp.

Khi dùng -jar, launcher lấy JAR được chỉ định làm nguồn lớp ứng dụng và bỏ qua các thiết lập classpath bên ngoài như -cp/CLASSPATH. Vì vậy không dùng đồng thời java -cp ... -jar app.jar với kỳ vọng -cp sẽ bổ sung thư viện cho ứng dụng.

### 7.2. Dùng thuộc tính Class-Path trong manifest

Nếu muốn giữ lệnh java -jar, manifest có thể khai báo Class-Path:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/logging.jar lib/database-driver.jar

```

Khi chạy:

```bash
java -jar app.jar
```

Launcher bổ sung các URL trong Class-Path vào classpath của ứng dụng. Đường dẫn tương đối được phân giải tương đối với vị trí của JAR chứa manifest, không phải tùy ý theo thư mục làm việc hiện tại.

Ví dụ:

```text
deploy/
├── app.jar
└── lib/
    ├── logging.jar
    └── database-driver.jar
```

Với cấu trúc trên, lib/logging.jar được tính từ thư mục chứa app.jar.

Các entry trong manifest Class-Path là URL/đường dẫn archive theo quy tắc manifest, phân tách bằng khoảng trắng. Nếu tên có khoảng trắng, cần mã hóa/escape đúng quy tắc URL; tránh tự ghép chuỗi tên file tùy ý mà không kiểm tra.

Class-Path hữu ích cho một layout triển khai đơn giản, nhưng cần bảo đảm toàn bộ JAR phụ thuộc được copy đúng vị trí. Nó không phải hệ thống quản lý dependency hoặc phiên bản.

### 7.3. Fat JAR hoặc uber JAR

Một cách khác là tạo **fat JAR** (còn gọi uber JAR) chứa ứng dụng và nội dung các dependency cần thiết trong một archive.

Các build tool như Maven và Gradle có plugin chuyên dụng để tạo artifact kiểu này. Chúng có thể xử lý việc hợp nhất resource, metadata và service provider configuration theo quy tắc của plugin.

Không nên tự giải nén mọi dependency rồi ghép tất cả file vào một JAR mà không xử lý:

- Trùng tên resource.
- Trùng file META-INF/services.
- Chữ ký số của các dependency.
- File manifest và metadata module.
- License và notice của thư viện.

Một số framework dùng định dạng executable JAR riêng, có launcher và cấu trúc nested JAR. Những archive này cần được tạo và chạy theo hướng dẫn của framework; không nên giả định một lệnh jar cơ bản sẽ tạo được cấu trúc tương đương.

## 8. Chạy JAR không có Main-Class

JAR thư viện hoặc JAR được đóng gói mà không khai báo entry point vẫn có thể chạy nếu chỉ định classpath và lớp main:

```bash
java -cp library.jar com.example.tools.DiagnosticMain
```

Trong trường hợp này:

- library.jar được đưa lên classpath.
- com.example.tools.DiagnosticMain là lớp launcher.
- Không cần Main-Class trong manifest vì tên lớp đã có trên dòng lệnh.

Đây cũng là cách chạy một trong nhiều lớp main của cùng một artifact.

## 9. Modular JAR và lớp khởi chạy

Từ Java 9, một JAR có thể là **modular JAR** nếu chứa module-info.class ở root. Java 17 tiếp tục hỗ trợ mô hình này.

Ví dụ source module:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

module-info.java:

```java
module com.example.app {
    exports com.example.app;
}
```

Lớp main:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a named module");
    }
}
```

### 9.1. Biên dịch module

Từ thư mục dự án:

```bash
javac -d mods --module-source-path src -m com.example.app
```

Output:

```text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

### 9.2. Đóng gói modular JAR

Đóng gói nội dung module:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C mods/com.example.app .
```

Với modular JAR, --main-class ghi thông tin lớp khởi chạy vào metadata module (ModuleMainClass) để launcher có thể dùng khi chạy module mà không phải chỉ rõ class ở dòng lệnh.

Kiểm tra descriptor:

```bash
jar --describe-module --file app.jar
```

### 9.3. Chạy modular JAR qua module path

Chạy module có main class được khai báo:

```bash
java --module-path app.jar --module com.example.app
```

Có thể viết ngắn -m thay cho --module:

```bash
java --module-path app.jar -m com.example.app
```

Nếu không khai báo main class trong metadata module, có thể chỉ rõ lớp:

```bash
java --module-path app.jar -m com.example.app/com.example.app.Main
```

Đây là cách chạy ứng dụng theo module path. Khi làm việc với modular JAR, cần phân biệt module name với tên file JAR: module name lấy từ module descriptor, không nhất thiết trùng tên file.

### 9.4. Main-Class của manifest và ModuleMainClass

Đối với JAR thông thường, Main-Class trong manifest là thông tin entry point cho java -jar.

Đối với modular JAR, jar --main-class cũng ghi lớp main vào metadata module. Khi chạy bằng java -m module, launcher dùng ModuleMainClass nếu có; nếu không có, cung cấp module/class trên dòng lệnh.

Hai trường hợp đều chỉ định một lớp Java có main, nhưng cách launcher tìm module và lớp khởi chạy khác nhau.

## 10. Kiểm tra và xem nội dung JAR

Sau khi tạo artifact, nên xác nhận archive có đúng class, resource và manifest.

### 10.1. Liệt kê entry

```bash
jar --list --file app.jar
```

Có thể lọc kết quả theo tên file/package bằng công cụ shell tương ứng.

### 10.2. Giải nén archive

```bash
mkdir extracted
jar --extract --file app.jar --directory extracted
```

Sau khi giải nén, kiểm tra:

- META-INF/MANIFEST.MF.
- Lớp được khai báo trong Main-Class có tồn tại ở đúng package.
- Các resource cần thiết đã được đưa vào archive.
- module-info.class có mặt nếu đây là modular JAR.

### 10.3. Kiểm tra module descriptor

Với modular JAR:

```bash
jar --describe-module --file app.jar
```

Lệnh này cho biết module name, các package được export, dependency và metadata module mà công cụ có thể hiển thị.

### 10.4. Kiểm tra bằng lệnh chạy thật

Cuối cùng, chạy artifact theo đúng kiểu triển khai:

```bash
java -jar app.jar
```

Hoặc với modular JAR:

```bash
java --module-path app.jar -m com.example.app
```

Chạy trực tiếp từ thư mục out không chứng minh JAR đã đóng gói đúng. Cần chạy chính file JAR trong một thư mục triển khai độc lập với cấu trúc dependency dự kiến.

## 11. Manifest và các thuộc tính thường gặp

Manifest là file văn bản theo định dạng manifest của Java, nằm tại META-INF/MANIFEST.MF.

Một số thuộc tính thường gặp:

| Thuộc tính | Mục đích |
| --- | --- |
| Manifest-Version | Phiên bản định dạng manifest; thường là 1.0. |
| Main-Class | Lớp khởi chạy cho executable JAR thông thường. |
| Class-Path | Các URL/JAR dependency bổ sung cho class loader của ứng dụng. |
| Implementation-Title | Tên sản phẩm/thành phần. |
| Implementation-Version | Phiên bản triển khai. |
| Specification-Title | Tên đặc tả mà JAR cung cấp. |
| Multi-Release | Đánh dấu multi-release JAR nếu archive thực sự được đóng gói theo cấu trúc đó. |

Không phải mọi JAR đều cần tất cả thuộc tính này. Chỉ thêm metadata mà ứng dụng hoặc công cụ triển khai thực sự sử dụng.

### 11.1. Dòng dài trong manifest

Manifest có quy tắc giới hạn độ dài dòng và cách continuation line. Nếu tự tạo manifest, không nên nối một dòng Class-Path cực dài bằng tay mà bỏ qua quy tắc này. Dùng công cụ jar hoặc build tool để sinh manifest khi danh sách dependency lớn.

### 11.2. Không sửa tùy tiện JAR đã ký

Nếu archive đã được ký số, việc sửa nội dung hoặc thay đổi entry có thể làm chữ ký không còn hợp lệ. Khi cần cập nhật ứng dụng, hãy tạo và ký lại artifact theo quy trình phát hành thay vì sửa trực tiếp một JAR đã ký.

## 12. Đóng gói bằng build tool trong dự án thực tế

Với dự án nhỏ, javac và jar đủ để minh họa quy trình. Dự án thực tế thường có nhiều dependency, resource, test, version và cấu hình môi trường. Maven hoặc Gradle giúp tái lập quá trình build và quản lý dependency.

Một quy trình build thông thường:

1. Khai báo source set và dependency.
2. Biên dịch source thành class.
3. Copy resource vào output.
4. Tạo JAR với manifest phù hợp.
5. Nếu cần, tạo artifact có dependency theo plugin chuyên dụng.
6. Chạy thử chính artifact được tạo.

Ví dụ với Maven, plugin JAR có thể cấu hình Main-Class trong manifest; nếu cần fat JAR, dùng plugin chuyên cho việc đóng gói dependency. Với Gradle, cấu hình jar task hoặc plugin phù hợp để đặt manifest và tạo artifact.

Tên plugin và cú pháp có thể thay đổi theo phiên bản build tool; nên dùng tài liệu của phiên bản dự án đang sử dụng. Điều quan trọng là artifact cuối cùng phải chứa manifest/metadata và dependency theo đúng cách launcher mong đợi.

## 13. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| no main manifest attribute | JAR không có Main-Class. | Tạo executable JAR bằng --main-class hoặc thêm manifest đúng. |
| Could not find or load main class | Tên lớp sai, class chưa được đóng gói hoặc package path sai. | Kiểm tra Main-Class và danh sách entry trong JAR. |
| Main method not found | Lớp được khai báo không có phương thức main hợp lệ. | Dùng lớp có public static void main(String[] args). |
| Chạy từ IDE được nhưng JAR lỗi ClassNotFoundException. | Dependency có trong IDE classpath nhưng không được cung cấp khi chạy JAR. | Cấu hình classpath, manifest Class-Path hoặc tạo artifact chứa dependency. |
| java -cp ... -jar app.jar vẫn thiếu thư viện. | Khi dùng -jar, classpath bên ngoài bị bỏ qua. | Chọn -cp với tên lớp main, hoặc dùng manifest Class-Path/fat JAR. |
| Resource không tìm thấy sau khi đóng gói. | Resource chưa được thêm vào JAR hoặc code dùng đường dẫn filesystem. | Đưa resource vào archive và đọc bằng class loader/module resource API. |
| Modular JAR không chạy bằng module name dự kiến. | Module name trong descriptor khác tên file hoặc descriptor không nằm đúng root. | Dùng jar --describe-module để kiểm tra module metadata. |
| Manifest không được đọc như mong muốn. | Định dạng sai, thiếu dòng trống cuối hoặc continuation line không đúng. | Dùng manifest chuẩn và kiểm tra META-INF/MANIFEST.MF sau khi đóng gói. |
| JAR chạy trên máy dev nhưng không chạy ở máy khác. | Thiếu dependency, khác runtime hoặc resource/path phụ thuộc môi trường. | Kiểm thử artifact trong môi trường sạch với JDK/runtime mục tiêu. |

## 14. Quy trình hoàn chỉnh: từ source đến executable JAR

Với ứng dụng không modular đơn giản:

**Bước 1 — Biên dịch**

```bash
javac -d out src/com/example/app/Main.java
```

**Bước 2 — Tạo JAR và đặt main class**

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out .
```

**Bước 3 — Kiểm tra nội dung**

```bash
jar --list --file app.jar
```

**Bước 4 — Chạy**

```bash
java -jar app.jar
```

**Bước 5 — Chạy với đối số và cấu hình JVM**

```bash
java -Xmx512m -Dapp.environment=production -jar app.jar --port 8080
```

Nếu ứng dụng có dependency, thêm chúng qua classpath/manifest hoặc dùng build tool tạo artifact triển khai tương ứng. Nếu là modular JAR, dùng module path và launcher -m.

## 15. Bài tập thực hành

### Bài 1 — Tạo executable JAR

Tạo lớp com.example.app.Main có phương thức main, biên dịch vào thư mục out, đóng gói bằng jar --main-class rồi chạy bằng java -jar.

### Bài 2 — Tự viết manifest

Tạo MANIFEST.MF chứa Manifest-Version và Main-Class. Đóng gói lại JAR bằng --manifest, sau đó kiểm tra manifest bên trong archive.

### Bài 3 — Truyền tham số

Chạy JAR với các đối số dev, --port, 8080. In các giá trị trong main(String[] args) và phân biệt chúng với -Xmx hoặc -D là tùy chọn JVM.

### Bài 4 — Dependency bên ngoài

Tạo hai JAR: ứng dụng và thư viện. Chạy ứng dụng bằng -cp trên Linux/macOS và Windows; sau đó thử manifest Class-Path. Giải thích vì sao -cp không bổ sung classpath khi dùng -jar.

### Bài 5 — Resource trong JAR

Đóng gói app.properties cùng ứng dụng. Đọc resource bằng getResourceAsStream và thử chạy JAR từ một thư mục làm việc khác để chứng minh resource không phụ thuộc current working directory.

### Bài 6 — Modular JAR

Tạo module-info.java, biên dịch bằng --module-source-path, đóng gói modular JAR có main class và chạy bằng java --module-path ... -m .... Dùng jar --describe-module để kiểm tra descriptor.

## 16. Tài liệu Java 17 chính thức

- [Java SE 17 jar tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo, cập nhật, liệt kê và mô tả JAR; các tùy chọn --main-class, --manifest, --describe-module.
- [Java SE 17 Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cách chạy class, JAR và module; tùy chọn -jar, -cp, --module-path, -m.
- [Java SE 17 javac tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): biên dịch source và module.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): cấu trúc archive, manifest và thuộc tính.
- [Java Platform Module System — JLS §7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declaration và cách tổ chức module.

JAR gom bytecode, resource và metadata vào một archive để phân phối. Với executable JAR thông thường, Main-Class trong manifest chỉ định lớp có phương thức main; java -jar dùng thông tin đó để khởi chạy. Dependency vẫn phải được cung cấp bằng classpath, manifest Class-Path hoặc cách đóng gói do build tool hỗ trợ. Với modular JAR, hãy kiểm tra module-info.class và chạy qua module path. Luôn kiểm tra và chạy thử chính artifact cuối cùng trước khi triển khai.
