# Ngôn ngữ nguồn, phiên bản class file và tập API nền tảng đích

Khi biên dịch một dự án Java cho nhiều phiên bản JDK, cần phân biệt ba lựa chọn thường bị gộp làm một: **phiên bản ngôn ngữ nguồn**, **phiên bản định dạng class file** và **tập API nền tảng Java được phép sử dụng**. Ba yếu tố này liên quan với nhau nhưng trả lời ba câu hỏi khác nhau.

- Phiên bản ngôn ngữ nguồn xác định compiler chấp nhận cú pháp và tính năng ngôn ngữ Java ở mức nào.
- Phiên bản class file xác định định dạng bytecode được tạo ra và mức JVM tối thiểu có thể đọc định dạng đó.
- Tập API nền tảng đích xác định những lớp, phương thức và trường thuộc Java platform mà mã nguồn được phép tham chiếu.

Một dự án có thể dùng cú pháp Java cũ, tạo class file cũ nhưng vẫn tham chiếu API chỉ có ở JDK mới. Khi đó build có thể thành công trên máy developer nhưng ứng dụng lỗi khi chạy trên JDK mục tiêu. Để tránh tình huống này, cần cấu hình và kiểm tra cả ba yếu tố, đồng thời xác minh các thư viện bên ngoài và runtime thực tế.

## 1. Ba khái niệm cần tách biệt

### 1.1. Phiên bản ngôn ngữ nguồn (source language level)

Source language level quy định những cấu trúc cú pháp và tính năng ngôn ngữ mà compiler cho phép trong mã nguồn.

Ví dụ, các tính năng Java xuất hiện ở những release khác nhau:

- Lambda expression và method reference có từ Java 8.
- **var** cho biến cục bộ có từ Java 10.
- Text block được chuẩn hóa ở Java 15.
- Record được chuẩn hóa ở Java 16.
- Pattern matching cho **instanceof** được chuẩn hóa ở Java 16.

Nếu source level của dự án là Java 8, mã nguồn không thể dùng record hoặc text block như tính năng ngôn ngữ chính thức. Compiler có thể báo lỗi cú pháp hoặc lỗi source version dù JDK đang cài là phiên bản mới hơn.

Source level trả lời câu hỏi: **Mã nguồn được viết bằng tập tính năng ngôn ngữ của release nào?**

Nó không tự trả lời câu hỏi: API Java nào được phép gọi. Một lệnh cấu hình source level cũ không nhất thiết giới hạn API nền tảng mà compiler nhìn thấy.

### 1.2. Phiên bản class file (class-file target)

Sau khi biên dịch, Java compiler tạo bytecode được lưu trong file **.class**. Class file có cấu trúc và phiên bản định dạng riêng. JVM đọc định dạng này để nạp lớp và thực thi bytecode.

Mỗi Java release gắn với một class-file major version. Ví dụ:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Khi compiler tạo class file có major version 65, JVM cần hỗ trợ định dạng đó, tương ứng Java 21 trở lên trong trường hợp class file thông thường. JVM Java 17 không đọc được class file major version 65 và có thể báo **UnsupportedClassVersionError**.

Class-file target trả lời câu hỏi: **Bytecode được tạo theo định dạng mà JVM release nào có thể đọc?**

Nó không đảm bảo rằng mọi API được gọi trong bytecode đều tồn tại trên JVM đó. Một class file có major version 52 vẫn có thể chứa tham chiếu tới phương thức chỉ được thêm vào Java 11 nếu compiler được phép biên dịch tham chiếu đó từ JDK mới.

### 1.3. Tập API nền tảng đích (platform API release)

Java platform cung cấp các API như **java.lang**, **java.util**, **java.time**, **java.sql**, các module chuẩn và nhiều API khác. Các API này thay đổi qua các release: có API mới được thêm, API cũ bị deprecated, thay đổi hoặc loại bỏ.

Ví dụ:

- **List.of(...)** có từ Java 9.
- **String.isBlank()** có từ Java 11.
- Một số API cũ hoặc API nội bộ có thể bị hạn chế hoặc không còn tồn tại trong JDK mới.

Nếu ứng dụng cần chạy trên Java 8, mã nguồn và bytecode phải tránh gọi API chỉ có từ Java 9 trở đi. Nếu không, class file có thể được JVM Java 8 đọc nhưng lời gọi API vẫn thất bại khi thực thi.

Platform API release trả lời câu hỏi: **Mã nguồn được phép sử dụng những API Java SE có trong release nào?**

### 1.4. Bảng phân biệt tổng hợp

| Yếu tố | Kiểm soát | Ví dụ lỗi nếu cấu hình sai |
|---|---|---|
| Source language level | Cú pháp và tính năng ngôn ngữ | Dùng record nhưng source level quá thấp |
| Class-file target | Định dạng bytecode đầu ra | Java 17 không nạp được class file Java 21 |
| Platform API release | API Java nền tảng mà mã nguồn được phép gọi | Java 8 thiếu String.isBlank() |
| Compiler JDK/toolchain | Phiên bản compiler thực tế được dùng | Local và CI biên dịch bằng JDK khác nhau |

Một cấu hình tương thích thường phải làm rõ cả compiler JDK, source level, class-file target và platform API release. Với các JDK hiện đại, **--release** là cách trực tiếp để đồng bộ ba lựa chọn đầu tiên về cùng một release mục tiêu.

## 2. Phân biệt các tùy chọn của javac

Java compiler có các tùy chọn liên quan nhưng không thể thay thế lẫn nhau.

### 2.1. -source

Tùy chọn **-source** chọn phiên bản ngôn ngữ nguồn mà compiler dùng để phân tích mã Java. Ví dụ, **-source 8** yêu cầu compiler xử lý mã nguồn theo mức ngôn ngữ Java 8.

Tùy chọn này không tự giới hạn class-file version đầu ra và cũng không giới hạn đầy đủ tập API Java nền tảng.

### 2.2. -target

Tùy chọn **-target** chọn phiên bản class file được tạo ra. Ví dụ, **-target 8** tạo class file theo định dạng Java 8.

Tùy chọn này không tự ngăn mã nguồn gọi API mới hơn từ JDK đang dùng để biên dịch. Vì vậy, chỉ đặt **-target 8** chưa đủ để chứng minh artifact chạy được trên Java 8.

### 2.3. --release

Tùy chọn **--release N** được giới thiệu từ JDK 9 để biên dịch cho một Java release mục tiêu. Nó kết hợp ba yêu cầu:

1. Dùng quy tắc ngôn ngữ nguồn tương ứng release đó.
2. Tạo class file tương ứng release đó.
3. Giới hạn API Java SE có thể sử dụng theo release đó.

Ví dụ:

~~~bash
javac --release 8 -d out src/com/example/App.java
~~~

Lệnh trên biên dịch mã theo Java 8, tạo class file Java 8 và giới hạn API nền tảng Java SE theo Java 8, dù compiler được chạy từ JDK mới hơn có hỗ trợ **--release 8**.

Không kết hợp **--release** với **-source** hoặc **-target** trong cùng một lần gọi javac. Chúng là các cách cấu hình mục tiêu khác nhau và javac không cho phép dùng đồng thời.

### 2.4. Bảng so sánh các lựa chọn

| Cấu hình | Ngôn ngữ nguồn | Class file | API nền tảng |
|---|---|---|---|
| Chỉ -source 8 | Java 8 | Theo mặc định/compiler target | Có thể nhìn thấy API của JDK compiler |
| Chỉ -target 8 | Theo mặc định/compiler source | Java 8 | Có thể nhìn thấy API của JDK compiler |
| -source 8 -target 8 | Java 8 | Java 8 | Không được giới hạn đầy đủ về Java 8 |
| --release 8 | Java 8 | Java 8 | Java SE API của Java 8 |
| --release 17 | Java 17 | Java 17 | Java SE API của Java 17 |

Khi sử dụng JDK 9 trở lên, hãy ưu tiên **--release** nếu mục tiêu là biên dịch ứng dụng cho một Java platform release cụ thể.

## 3. Vì sao source và target cũ vẫn có thể gọi API mới?

Giả sử developer dùng JDK 17 để biên dịch một dự án cần chạy trên Java 8. Dự án đặt **-source 8 -target 8**, nhưng không giới hạn API nền tảng.

Mã nguồn sau dùng phương thức **String.isBlank()**, được bổ sung từ Java 11:

~~~java
public class ApiCompatibilityExample {

    public static void main(String[] args) {
        String value = "   ";

        if (value.isBlank()) {
            System.out.println("Blank value");
        }
    }
}
~~~

Cú pháp của đoạn mã tương thích với Java 8, và class file có thể được tạo theo định dạng Java 8. Tuy nhiên, compiler JDK 17 nhìn thấy phương thức **isBlank()** trong API của JDK 17 nên có thể biên dịch lời gọi đó khi chỉ dùng **-source 8 -target 8**.

Khi chạy class file này trên Java 8, JVM có thể nạp định dạng class file nhưng không tìm thấy phương thức **String.isBlank()**. Lỗi có thể là:

~~~text
java.lang.NoSuchMethodError:
  java.lang.String.isBlank()Z
~~~

Đây là trường hợp source language level và class-file target đều trông đúng nhưng platform API target lại sai.

Nếu thay cấu hình bằng:

~~~bash
javac --release 8 -d out src/com/example/ApiCompatibilityExample.java
~~~

compiler sẽ báo lỗi vì **isBlank()** không tồn tại trong Java 8 API. Lỗi được phát hiện ngay khi biên dịch thay vì đợi tới runtime.

Một ví dụ khác là **List.of(...)**, có từ Java 9:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
~~~

Đoạn mã này không thể dùng khi platform API mục tiêu là Java 8. Nếu ứng dụng phải chạy trên Java 8, có thể chọn API tương thích như **Arrays.asList(...)** tùy theo yêu cầu về khả năng thay đổi collection và semantics của chương trình.

## 4. Hiểu class-file version và lỗi JVM

Class file bắt đầu bằng magic number **CAFEBABE**, tiếp theo là minor version và major version. JVM kiểm tra phiên bản định dạng khi nạp lớp.

Một số major version thường gặp:

| Major version | Java release |
|---:|---|
| 52 | Java 8 |
| 55 | Java 11 |
| 61 | Java 17 |
| 65 | Java 21 |
| 69 | Java 25 |

Nếu một class được biên dịch cho Java 21 nhưng chạy trên JVM Java 17, thông báo lỗi thường cho biết class file version 65.0 trong khi runtime chỉ hỗ trợ đến 61.0. Đây là lỗi định dạng bytecode, không phải lỗi thiếu một phương thức API.

Cần phân biệt hai nhóm lỗi:

- **UnsupportedClassVersionError**: JVM không hỗ trợ class-file version của lớp đang nạp.
- **NoSuchMethodError**, **NoSuchFieldError** hoặc **NoClassDefFoundError**: class file có thể được nạp, nhưng một tham chiếu cần thiết không thể được phân giải hoặc lớp cần thiết không thể được sử dụng.

Vì vậy, khi thấy lỗi runtime, hãy đọc đúng loại lỗi và kiểm tra cả class-file version lẫn dependency/API. Không nên kết luận mọi lỗi liên quan đến Java version đều do bytecode quá mới.

### 4.1. JVM mới và class file cũ

Các JVM mới thường có khả năng chạy class file của những release cũ hơn trong phạm vi định dạng và API tương thích. Tuy nhiên, điều đó không có nghĩa mọi ứng dụng cũ đều chạy đúng trên JDK mới: API bị loại bỏ, thay đổi module access, reflection, TLS, charset mặc định, GC hoặc hành vi thư viện vẫn có thể gây vấn đề.

Chiều ngược lại bị giới hạn rõ hơn: JVM cũ không thể đọc class file được tạo theo định dạng mới hơn mà nó chưa hỗ trợ.

### 4.2. Minor version và preview features

Các tính năng preview của Java được phát hành để thử nghiệm trong một release. Khi biên dịch có bật preview, class file có thể dùng minor version đặc biệt là 65535. Việc chạy class file preview yêu cầu bật preview trên JVM và phải dùng đúng Java release đã tạo ra class file đó.

Ví dụ:

~~~bash
javac --enable-preview --release 21 -d out src/com/example/PreviewApp.java
java --enable-preview -cp out com.example.PreviewApp
~~~

Không nên dùng class file preview làm artifact triển khai thông thường nếu môi trường production không được cấu hình và kiểm soát đúng release. Khi migration, hãy kiểm tra xem dự án hoặc dependency có sử dụng preview feature hay không.

## 5. API nền tảng Java và API của thư viện bên ngoài

**--release** giúp giới hạn API Java SE, nhưng không kiểm soát mọi API mà ứng dụng sử dụng.

Một dự án thường phụ thuộc vào:

- Java SE platform API như **java.util**, **java.time**, **java.net**.
- API của framework như Spring Framework hoặc Spring Boot.
- API của thư viện bên thứ ba như Jackson, Hibernate, Netty hoặc HTTP client.
- API nội bộ của JDK hoặc implementation-specific API.
- API do application server, container hoặc nền tảng triển khai cung cấp.

**--release 17** không có nghĩa mọi thư viện bên thứ ba trong dependency graph đều tương thích Java 17. Nó cũng không tự bảo đảm một dependency được biên dịch cho Java 17; một JAR bên ngoài có thể chứa class file Java 21 và khiến runtime Java 17 thất bại khi nạp lớp.

Tương tự, **--release** không chứng minh các API reflection, service provider, native library, cấu hình framework hoặc giao thức dữ liệu vẫn hoạt động. Những phần này cần kiểm tra riêng.

### 5.1. Java SE API và JDK internal API

Không nên phụ thuộc vào các package nội bộ như **sun.*** hoặc những API không được Java SE cam kết. Chúng có thể thay đổi hoặc bị đóng quyền truy cập giữa các JDK release.

Có thể dùng công cụ **jdeps** để phát hiện một số phụ thuộc vào JDK internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

Đây là một bước phân tích tĩnh hữu ích, nhưng không phát hiện đầy đủ mọi truy cập được tạo bằng reflection, tên lớp trong cấu hình hoặc mã native. Cần kết hợp với kiểm thử runtime.

### 5.2. API của thư viện bên thứ ba

Giả sử mã nguồn dùng Spring API hoặc một thư viện JSON. Compiler kiểm tra chữ ký theo JAR trên compile classpath. Nếu runtime lại nạp phiên bản JAR khác, lời gọi có thể không còn tương thích.

Với thư viện bên ngoài, cần kiểm tra:

- Phiên bản được resolve khi build.
- Phiên bản thực tế được đóng gói hoặc cung cấp bởi môi trường.
- Class-file version của các lớp trong dependency.
- Java baseline mà nhà phát hành thư viện hỗ trợ.
- Thay đổi API và hành vi trong release notes/migration guide.
- Dependency bắc cầu có bị nâng/hạ ngoài dự kiến không.

Một build dùng **--release 17** vẫn có thể tạo artifact không chạy được trên Java 17 nếu một dependency chứa bytecode mới hơn hoặc yêu cầu runtime API không có trên Java 17.

## 6. Chọn compiler JDK và runtime target có chủ đích

Compiler JDK là JDK thực tế chạy javac. Runtime target là nền tảng mà artifact cần hỗ trợ. Hai giá trị có thể khác nhau.

Ví dụ, nhóm có thể dùng JDK 21 làm compiler nhưng tạo artifact nhắm Java 17:

| Thành phần | Giá trị |
|---|---|
| Compiler JDK | 21 |
| Source language level | 17 |
| Class-file target | 17 |
| Java SE API target | 17 |
| Runtime tối thiểu dự kiến | Java 17 |
| Runtime kiểm chứng | Java 17 và các môi trường được hỗ trợ |

Cách làm này cho phép nhóm sử dụng compiler mới trong CI, đồng thời kiểm soát nền tảng đầu ra. Điều kiện là mọi source code và dependency đều tuân thủ baseline đã chọn.

Không nên nhầm **JAVA_HOME** với runtime triển khai. **JAVA_HOME** trong pipeline có thể trỏ tới JDK biên dịch, trong khi container hoặc máy chủ production lại dùng JRE/JDK khác. Hãy kiểm tra riêng cả hai.

## 7. Cấu hình bằng Gradle

Với Gradle Java plugin, nên dùng Java toolchain để chọn compiler JDK và **options.release** để chỉ định Java platform release mục tiêu.

Ví dụ dùng JDK 21 để biên dịch cho Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong cấu hình này:

- Toolchain chọn JDK 21 để chạy compiler.
- **options.release = 17** giới hạn source language, class-file target và Java SE API ở mức Java 17.
- Artifact tạo ra có class-file major version 61.
- Mã nguồn không được dùng tính năng ngôn ngữ hoặc API Java SE chỉ có sau Java 17.

Nếu ứng dụng phải chạy trên Java 17, hãy kiểm tra test task và môi trường chạy artifact bằng Java 17. Toolchain cấu hình cho compile/test có thể khiến test chạy bằng JDK toolchain mới; việc compile với release 17 tự nó không chứng minh test đã chạy trên JVM 17.

Có thể cấu hình launcher cho test rõ ràng:

~~~groovy
def java17 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}

tasks.withType(Test).configureEach {
    javaLauncher = java17
}
~~~

Tên biến và cách tổ chức có thể điều chỉnh theo build script. Điều quan trọng là phải xác định riêng compiler JDK và JVM chạy test khi chúng khác nhau.

### 7.1. sourceCompatibility và targetCompatibility

Gradle cũng có các thuộc tính **sourceCompatibility** và **targetCompatibility**. Chúng biểu diễn mức source và bytecode target cho Java compilation. Chúng không tự chọn JDK cài đặt để chạy compiler và không giới hạn đầy đủ tập API Java SE như **options.release**.

Ví dụ:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}
~~~

Nếu build chạy bằng JDK mới, cấu hình này vẫn có thể cho phép mã nguồn tham chiếu API mới hơn. Với JDK 9 trở lên, nếu mục tiêu là đảm bảo API Java SE theo release, hãy ưu tiên **options.release**.

Không nên khai báo đồng thời **options.release** và các tùy chọn source/target theo cách xung đột. Chọn một cách cấu hình mục tiêu nhất quán và kiểm tra task compile thực tế.

### 7.2. Multi-module Gradle

Trong dự án nhiều module, không nên chỉ cấu hình một module rồi giả định tất cả module khác đều theo cùng baseline. Cần kiểm tra:

- Các module Java đều dùng cùng Java toolchain hoặc có ngoại lệ được ghi rõ.
- Mỗi **JavaCompile** task dùng release target phù hợp.
- Module test, integration test và generated source có cấu hình tương ứng.
- Plugin build, annotation processor và code generator có chạy được trên compiler JDK đã chọn.
- Dependency nội bộ không phát hành class file mới hơn runtime target của ứng dụng tiêu thụ.

Có thể áp dụng cấu hình tập trung trong convention plugin hoặc build logic dùng chung, sau đó cho phép module có yêu cầu riêng được khai báo rõ ràng. Tránh để cấu hình ở root và cấu hình module con âm thầm ghi đè lẫn nhau.

## 8. Cấu hình bằng Maven

Với Maven Compiler Plugin, thuộc tính **maven.compiler.release** là cách gọn để chọn release mục tiêu trên JDK hỗ trợ **--release**.

Ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hoặc khai báo trực tiếp trong plugin configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

Cấu hình release 17 yêu cầu compiler dùng API Java SE và class-file target tương ứng Java 17. JDK dùng để chạy Maven/compiler vẫn cần được xác định qua môi trường hoặc toolchain Maven nếu dự án quản lý nhiều JDK.

Các thuộc tính **maven.compiler.source** và **maven.compiler.target** là cấu hình kiểu cũ. Chúng không cung cấp đầy đủ bảo vệ API như **release**. Nếu phải biên dịch cho Java 8 bằng JDK 9 trở lên, hãy dùng release 8 khi compiler hỗ trợ.

## 9. Trường hợp compiler quá cũ hoặc quá mới

**--release** chỉ có thể chọn một release nằm trong phạm vi mà compiler hỗ trợ. Ví dụ, compiler JDK 17 không thể tạo class file và API target Java 21. Muốn biên dịch cho Java 21, cần compiler JDK 21 hoặc mới hơn có hỗ trợ release 21.

Ngược lại, nếu dùng JDK 8 để biên dịch cho Java 8 thì chưa có tùy chọn **--release** vì tùy chọn này được giới thiệu từ JDK 9. Khi đó compiler JDK 8 vốn nhìn thấy Java 8 API, hoặc có thể sử dụng cấu hình boot class path phù hợp trong các quy trình legacy. Với dự án mới, nên nâng compiler/build tool lên phiên bản hỗ trợ **--release** để cấu hình rõ ràng hơn.

Cũng cần kiểm tra phiên bản Gradle, Maven Compiler Plugin và plugin liên quan. Một JDK mới có thể không tương thích với build tool cũ, dù source code của ứng dụng không thay đổi. Build tool compatibility là một phần của migration, độc lập với source/class-file/API target của ứng dụng.

## 10. Multi-release JAR không phải là --release

Multi-release JAR là cơ chế đóng gói nhiều phiên bản class cho các Java release khác nhau trong cùng một file JAR. Các lớp dành cho release cụ thể nằm dưới **META-INF/versions/N**, và manifest cần khai báo **Multi-Release: true**.

Ví dụ cấu trúc:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/FastFormatter.class
│       └── 17/
│           └── com/example/FastFormatter.class
└── com/
    └── example/
        └── FastFormatter.class
~~~

JVM có hỗ trợ multi-release JAR sẽ chọn lớp phù hợp nhất với Java release đang chạy. Cơ chế này cho phép thư viện cung cấp implementation tối ưu hơn cho JDK mới và giữ implementation nền cho JDK cũ.

Nó khác với **--release**:

- **--release** là lựa chọn khi biên dịch một source set cho một Java platform release.
- Multi-release JAR là cấu trúc artifact chứa nhiều implementation theo release.
- Một JAR multi-release vẫn phải bảo đảm lớp nền và các lớp theo phiên bản có định dạng, API và semantics phù hợp.
- Không phải mọi thư viện hoặc mọi cách đóng gói đều tự động trở thành multi-release JAR.

Nếu dependency là multi-release JAR, hãy kiểm tra manifest, nội dung **META-INF/versions** và cách công cụ phân tích dependency được cấu hình. Khi kiểm tra bằng jdeps, có thể chỉ định release cần phân tích bằng tùy chọn **--multi-release**.

## 11. Kiểm tra cấu hình và artifact thực tế

Không nên chỉ đọc build.gradle hoặc pom.xml rồi kết luận artifact đã được tạo đúng. Cần kiểm tra compiler, class file và runtime.

### 11.1. Kiểm tra JDK compiler và runtime

~~~bash
java -version
javac -version
~~~

Hai lệnh có thể trả về phiên bản khác nhau nếu **PATH**, **JAVA_HOME**, toolchain hoặc môi trường shell được cấu hình khác nhau. Trong Gradle, có thể xem các JDK mà Gradle nhận diện:

~~~bash
./gradlew -q javaToolchains
~~~

Nếu dự án dùng Maven Toolchains, kiểm tra cấu hình toolchain và log compiler plugin để xác định JDK thực sự được dùng.

### 11.2. Kiểm tra class-file major version

Dùng **javap -verbose** để đọc thông tin class file:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.App
~~~

Trong output, tìm dòng:

~~~text
major version: 61
~~~

Major version 61 tương ứng Java 17. Hãy kiểm tra nhiều lớp đại diện, nhất là lớp được sinh tự động hoặc được đóng gói từ module nội bộ. Một artifact có thể chứa các class file khác release nếu dependency hoặc module được build riêng.

Có thể dùng **javap** với JAR trên classpath để xem một lớp thuộc dependency. Đừng chỉ kiểm tra một class của ứng dụng rồi suy ra toàn bộ JAR đều có cùng bytecode version.

### 11.3. Kiểm tra nội dung artifact

Dùng lệnh:

~~~bash
jar tf app.jar
~~~

Với Spring Boot executable JAR, kiểm tra các lớp ứng dụng và thư viện nằm trong cấu trúc đóng gói phù hợp, chẳng hạn **BOOT-INF/classes** và **BOOT-INF/lib**. Đối chiếu với dependency graph để phát hiện thư viện thiếu hoặc phiên bản không mong đợi.

### 11.4. Kiểm tra API và dependency

Với Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Có thể dùng:

~~~bash
jdeps --multi-release 17 --jdk-internals app.jar
~~~

để kiểm tra phụ thuộc JDK internal API khi phân tích artifact cho Java 17. Điều chỉnh release theo mục tiêu thực tế. Công cụ phân tích tĩnh không thay thế việc chạy artifact trên JVM mục tiêu.

### 11.5. Chạy artifact bằng runtime mục tiêu

Cuối cùng, chạy đúng artifact đã đóng gói bằng đúng Java runtime dự kiến triển khai:

~~~bash
java -version
java -jar app.jar
~~~

Trong pipeline, nên dùng image/container có JDK hoặc JRE mục tiêu. Xác nhận startup, health check, các luồng nghiệp vụ và kết nối dịch vụ. Nếu ứng dụng cần chạy trên nhiều Java release, hãy kiểm thử trên từng release được công bố hỗ trợ.

## 12. Các tình huống lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo source version không hỗ trợ | Compiler JDK quá cũ so với source level yêu cầu | Dùng compiler JDK phù hợp |
| Lỗi cú pháp với record/text block | Source level thấp hơn release có tính năng đó | Chọn source release phù hợp hoặc viết lại bằng cú pháp cũ |
| UnsupportedClassVersionError | Class file mới hơn JVM đang chạy | Hạ class-file target hoặc nâng runtime |
| NoSuchMethodError trên Java cũ | Class file tham chiếu API không có trong runtime | Dùng --release đúng target và kiểm tra dependency |
| NoClassDefFoundError | Thiếu class hoặc lần khởi tạo lớp trước đó thất bại | Kiểm tra runtime classpath và nguyên nhân khởi tạo |
| Lỗi chỉ xuất hiện trong container | Container dùng JRE/JDK hoặc thư viện khác local | Kiểm tra image, runtime version và artifact |
| Chỉ một module lỗi | Module đó có release target hoặc dependency khác | Kiểm tra task và cấu hình từng module |
| Lỗi khi chạy test nhưng compile thành công | Test JVM hoặc test dependency khác compile environment | Xác định test launcher và runtime classpath |
| Lỗi reflection trên JDK mới | Quyền truy cập module hoặc internal API thay đổi | Dùng API được hỗ trợ, cập nhật thư viện và kiểm thử |

Cần đọc stack trace để xác định lớp, phương thức và class loader liên quan. Một lỗi **NoSuchMethodError** có thể do JDK API hoặc do thư viện bên thứ ba; tên lớp trong stack trace và dependency graph giúp phân biệt.

## 13. Ma trận xác minh đa phiên bản

Với hệ thống phải hỗ trợ nhiều Java release, nên tạo ma trận để ghi rõ cấu hình và kết quả kiểm thử.

Ví dụ dự án hỗ trợ Java 17 và Java 21:

| Thành phần | Build mục tiêu Java 17 | Build mục tiêu Java 21 |
|---|---|---|
| Compiler JDK | 21 | 21 |
| Source level | 17 | 21 |
| Class-file major | 61 | 65 |
| Java SE API | Release 17 | Release 21 |
| Runtime kiểm tra | Java 17 | Java 21 |
| Unit/integration test | Chạy trên Java 17 | Chạy trên Java 21 |
| Kiểm tra chức năng | Luồng chính và dữ liệu | Luồng chính và dữ liệu |
| Kiểm tra hiệu năng | Baseline tương ứng | Baseline tương ứng |

Nếu chỉ phát hành một artifact cho Java 17, có thể chạy artifact đó trên Java 17 và Java 21 để xác nhận cả runtime cũ và mới nếu đó là phạm vi hỗ trợ. Nếu phát hành artifact riêng cho từng release, mỗi artifact phải được build, kiểm tra và nhận diện rõ.

Một ma trận nên ghi trạng thái từng ô như PASS, FAIL, BLOCKED hoặc NOT RUN, kèm log và artifact checksum. Không điền PASS chỉ vì build task thành công; cần xác định rõ bước nào đã chạy.

## 14. Kiểm soát source level và API target trong dự án nhiều module

Dự án nhiều module có thể gặp tình trạng module A biên dịch cho Java 17, module B tạo class file Java 21, module C dùng API Java 21 nhưng được đóng gói cùng ứng dụng Java 17. Mỗi module có thể build thành công riêng, nhưng ứng dụng tổng hợp lại không chạy được trên runtime mục tiêu.

Nên thống nhất một chính sách baseline:

1. Xác định Java runtime tối thiểu mà sản phẩm cam kết hỗ trợ.
2. Chọn source/API release tương ứng cho module ứng dụng.
3. Chọn compiler toolchain được CI và developer sử dụng.
4. Áp dụng **options.release** cho mọi task JavaCompile liên quan.
5. Kiểm tra module nội bộ và dependency bên ngoài có bytecode/API tương thích.
6. Kiểm thử test source, integration test, annotation processor và generated source.
7. Kiểm tra artifact cuối cùng, không chỉ từng module riêng lẻ.

Nếu có module chủ đích yêu cầu Java mới hơn, hãy thể hiện điều đó trong metadata, dependency graph và tài liệu phát hành. Không để module mới hơn bị kéo vào ứng dụng có runtime thấp hơn mà không có kiểm soát.

Đối với annotation processor hoặc code generator, cần phân biệt JDK dùng để chạy processor với release mà mã được sinh ra cần tuân thủ. Generated source phải được biên dịch bằng đúng **--release** mục tiêu. Plugin build có thể cần JDK mới hơn ứng dụng, nhưng bytecode của ứng dụng vẫn phải tuân theo target đã định.

## 15. Những gì --release không đảm bảo

**--release** là cơ chế quan trọng để kiểm soát Java SE API và class-file target, nhưng không phải chứng nhận tương thích toàn hệ thống.

Nó không tự xác nhận:

- Dependency bên thứ ba có class-file version phù hợp.
- Runtime classpath trùng với compile classpath.
- Spring bean, reflection, service loader hoặc cấu hình framework khởi tạo thành công.
- Driver database, native library hoặc application server tương thích.
- Schema database và payload giữa các service không thay đổi semantics.
- Ứng dụng đáp ứng latency, throughput và resource target.
- Ứng dụng chạy đúng trên mọi OS, container và cấu hình production.

Vì vậy, sau khi biên dịch với **--release**, vẫn cần dependency analysis, artifact inspection, runtime test và kiểm thử chức năng.

## 16. Quy trình chọn và xác minh target

Có thể áp dụng quy trình sau khi chuẩn bị build đa phiên bản:

### Bước 1: Xác định runtime tối thiểu

Làm rõ Java release thấp nhất mà ứng dụng cần hỗ trợ. Căn cứ vào nền tảng triển khai, thư viện, framework và chính sách sản phẩm.

### Bước 2: Chọn compiler JDK

Chọn JDK có thể biên dịch source release và API target đã chọn. Ghi rõ vendor và version trong CI để tránh máy local và pipeline sử dụng compiler khác nhau.

### Bước 3: Cấu hình source, class file và API

Với JDK 9 trở lên, dùng **--release N** hoặc cấu hình tương ứng trong Gradle/Maven. Không dựa riêng vào **sourceCompatibility** và **targetCompatibility** nếu yêu cầu là giới hạn Java SE API.

### Bước 4: Kiểm tra dependency

Xác minh thư viện nội bộ, thư viện bên thứ ba, annotation processor và plugin build. Đọc release notes và Java compatibility của các phiên bản được chọn.

### Bước 5: Kiểm tra artifact

Đọc class-file major version, nội dung JAR và dependency đóng gói. Xem xét multi-release JAR và preview feature nếu dự án có sử dụng.

### Bước 6: Chạy trên runtime mục tiêu

Chạy artifact trong JDK/JRE mục tiêu, thực hiện startup test, unit/integration test và các luồng nghiệp vụ quan trọng. Với nhiều target, kiểm tra từng target được công bố hỗ trợ.

### Bước 7: Lưu bằng chứng

Lưu build log, JDK version, cấu hình release, dependency report, checksum artifact và kết quả test. Khi có lỗi, ghi rõ release, module, class hoặc API liên quan.

## 17. Nguyên tắc cần nhớ

- Source language level kiểm soát cú pháp và tính năng ngôn ngữ.
- Class-file target kiểm soát định dạng bytecode mà JVM cần đọc.
- Platform API release kiểm soát API Java SE mà mã nguồn được phép sử dụng.
- Compiler JDK/toolchain xác định compiler thực tế, không đồng nghĩa runtime triển khai.
- **-source** và **-target** riêng lẻ không giới hạn đầy đủ API nền tảng.
- **--release** đồng bộ source, class file và Java SE API target trên JDK hỗ trợ.
- Dependency bên ngoài, reflection, native code và cấu hình vẫn cần được xác minh riêng.
- Chỉ chạy artifact trên runtime mục tiêu mới cung cấp bằng chứng trực tiếp về khả năng nạp và khởi tạo trên nền tảng đó.

Một cấu hình biên dịch đa phiên bản đáng tin cậy phải nói rõ mã nguồn dùng ngôn ngữ nào, bytecode được tạo cho JVM nào và API nền tảng nào được phép tham chiếu. Khi ba lựa chọn này được kiểm soát cùng với dependency và runtime thực tế, nhóm có thể phát hiện sớm lỗi tương thích và đưa ra kết luận migration dựa trên bằng chứng rõ ràng.
## 4. Hiểu class-file version và lỗi JVM

Class file bắt đầu bằng magic number **CAFEBABE**, tiếp theo là minor version và major version. JVM kiểm tra phiên bản định dạng khi nạp lớp.

Một số major version thường gặp:

| Major version | Java release |
|---:|---|
| 52 | Java 8 |
| 55 | Java 11 |
| 61 | Java 17 |
| 65 | Java 21 |
| 69 | Java 25 |

Nếu một class được biên dịch cho Java 21 nhưng chạy trên JVM Java 17, thông báo lỗi thường cho biết class file version 65.0 trong khi runtime chỉ hỗ trợ đến 61.0. Đây là lỗi định dạng bytecode, không phải lỗi thiếu một phương thức API.

Cần phân biệt hai nhóm lỗi:

- **UnsupportedClassVersionError**: JVM không hỗ trợ class-file version của lớp đang nạp.
- **NoSuchMethodError**, **NoSuchFieldError** hoặc **NoClassDefFoundError**: class file có thể được nạp, nhưng một tham chiếu cần thiết không thể được phân giải hoặc lớp cần thiết không thể được sử dụng.

Vì vậy, khi thấy lỗi runtime, hãy đọc đúng loại lỗi và kiểm tra cả class-file version lẫn dependency/API. Không nên kết luận mọi lỗi liên quan đến Java version đều do bytecode quá mới.

### 4.1. JVM mới và class file cũ

Các JVM mới thường có khả năng chạy class file của những release cũ hơn trong phạm vi định dạng và API tương thích. Tuy nhiên, điều đó không có nghĩa mọi ứng dụng cũ đều chạy đúng trên JDK mới: API bị loại bỏ, thay đổi module access, reflection, TLS, charset mặc định, GC hoặc hành vi thư viện vẫn có thể gây vấn đề.

Chiều ngược lại bị giới hạn rõ hơn: JVM cũ không thể đọc class file được tạo theo định dạng mới hơn mà nó chưa hỗ trợ.

### 4.2. Minor version và preview features

Các tính năng preview của Java được phát hành để thử nghiệm trong một release. Khi biên dịch có bật preview, class file có thể dùng minor version đặc biệt là 65535. Việc chạy class file preview yêu cầu bật preview trên JVM và phải dùng đúng Java release đã tạo ra class file đó.

Ví dụ:

~~~bash
javac --enable-preview --release 21 -d out src/com/example/PreviewApp.java
java --enable-preview -cp out com.example.PreviewApp
~~~

Không nên dùng class file preview làm artifact triển khai thông thường nếu môi trường production không được cấu hình và kiểm soát đúng release. Khi migration, hãy kiểm tra xem dự án hoặc dependency có sử dụng preview feature hay không.

## 5. API nền tảng Java và API của thư viện bên ngoài

**--release** giúp giới hạn API Java SE, nhưng không kiểm soát mọi API mà ứng dụng sử dụng.

Một dự án thường phụ thuộc vào:

- Java SE platform API như **java.util**, **java.time**, **java.net**.
- API của framework như Spring Framework hoặc Spring Boot.
- API của thư viện bên thứ ba như Jackson, Hibernate, Netty hoặc HTTP client.
- API nội bộ của JDK hoặc implementation-specific API.
- API do application server, container hoặc nền tảng triển khai cung cấp.

**--release 17** không có nghĩa mọi thư viện bên thứ ba trong dependency graph đều tương thích Java 17. Nó cũng không tự bảo đảm một dependency được biên dịch cho Java 17; một JAR bên ngoài có thể chứa class file Java 21 và khiến runtime Java 17 thất bại khi nạp lớp.

Tương tự, **--release** không chứng minh các API reflection, service provider, native library, cấu hình framework hoặc giao thức dữ liệu vẫn hoạt động. Những phần này cần kiểm tra riêng.

### 5.1. Java SE API và JDK internal API

Không nên phụ thuộc vào các package nội bộ như **sun.*** hoặc những API không được Java SE cam kết. Chúng có thể thay đổi hoặc bị đóng quyền truy cập giữa các JDK release.

Có thể dùng công cụ **jdeps** để phát hiện một số phụ thuộc vào JDK internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

Đây là một bước phân tích tĩnh hữu ích, nhưng không phát hiện đầy đủ mọi truy cập được tạo bằng reflection, tên lớp trong cấu hình hoặc mã native. Cần kết hợp với kiểm thử runtime.

### 5.2. API của thư viện bên thứ ba

Giả sử mã nguồn dùng Spring API hoặc một thư viện JSON. Compiler kiểm tra chữ ký theo JAR trên compile classpath. Nếu runtime lại nạp phiên bản JAR khác, lời gọi có thể không còn tương thích.

Với thư viện bên ngoài, cần kiểm tra:

- Phiên bản được resolve khi build.
- Phiên bản thực tế được đóng gói hoặc cung cấp bởi môi trường.
- Class-file version của các lớp trong dependency.
- Java baseline mà nhà phát hành thư viện hỗ trợ.
- Thay đổi API và hành vi trong release notes/migration guide.
- Dependency bắc cầu có bị nâng/hạ ngoài dự kiến không.

Một build dùng **--release 17** vẫn có thể tạo artifact không chạy được trên Java 17 nếu một dependency chứa bytecode mới hơn hoặc yêu cầu runtime API không có trên Java 17.

## 6. Chọn compiler JDK và runtime target có chủ đích

Compiler JDK là JDK thực tế chạy javac. Runtime target là nền tảng mà artifact cần hỗ trợ. Hai giá trị có thể khác nhau.

Ví dụ, nhóm có thể dùng JDK 21 làm compiler nhưng tạo artifact nhắm Java 17:

| Thành phần | Giá trị |
|---|---|
| Compiler JDK | 21 |
| Source language level | 17 |
| Class-file target | 17 |
| Java SE API target | 17 |
| Runtime tối thiểu dự kiến | Java 17 |
| Runtime kiểm chứng | Java 17 và các môi trường được hỗ trợ |

Cách làm này cho phép nhóm sử dụng compiler mới trong CI, đồng thời kiểm soát nền tảng đầu ra. Điều kiện là mọi source code và dependency đều tuân thủ baseline đã chọn.

Không nên nhầm **JAVA_HOME** với runtime triển khai. **JAVA_HOME** trong pipeline có thể trỏ tới JDK biên dịch, trong khi container hoặc máy chủ production lại dùng JRE/JDK khác. Hãy kiểm tra riêng cả hai.

## 7. Cấu hình bằng Gradle

Với Gradle Java plugin, nên dùng Java toolchain để chọn compiler JDK và **options.release** để chỉ định Java platform release mục tiêu.

Ví dụ dùng JDK 21 để biên dịch cho Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong cấu hình này:

- Toolchain chọn JDK 21 để chạy compiler.
- **options.release = 17** giới hạn source language, class-file target và Java SE API ở mức Java 17.
- Artifact tạo ra có class-file major version 61.
- Mã nguồn không được dùng tính năng ngôn ngữ hoặc API Java SE chỉ có sau Java 17.

Nếu ứng dụng phải chạy trên Java 17, hãy kiểm tra test task và môi trường chạy artifact bằng Java 17. Toolchain cấu hình cho compile/test có thể khiến test chạy bằng JDK toolchain mới; việc compile với release 17 tự nó không chứng minh test đã chạy trên JVM 17.

Có thể cấu hình launcher cho test rõ ràng:

~~~groovy
def java17 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}

tasks.withType(Test).configureEach {
    javaLauncher = java17
}
~~~

Tên biến và cách tổ chức có thể điều chỉnh theo build script. Điều quan trọng là phải xác định riêng compiler JDK và JVM chạy test khi chúng khác nhau.

### 7.1. sourceCompatibility và targetCompatibility

Gradle cũng có các thuộc tính **sourceCompatibility** và **targetCompatibility**. Chúng biểu diễn mức source và bytecode target cho Java compilation. Chúng không tự chọn JDK cài đặt để chạy compiler và không giới hạn đầy đủ tập API Java SE như **options.release**.

Ví dụ:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}
~~~

Nếu build chạy bằng JDK mới, cấu hình này vẫn có thể cho phép mã nguồn tham chiếu API mới hơn. Với JDK 9 trở lên, nếu mục tiêu là đảm bảo API Java SE theo release, hãy ưu tiên **options.release**.

Không nên khai báo đồng thời **options.release** và các tùy chọn source/target theo cách xung đột. Chọn một cách cấu hình mục tiêu nhất quán và kiểm tra task compile thực tế.

### 7.2. Multi-module Gradle

Trong dự án nhiều module, không nên chỉ cấu hình một module rồi giả định tất cả module khác đều theo cùng baseline. Cần kiểm tra:

- Các module Java đều dùng cùng Java toolchain hoặc có ngoại lệ được ghi rõ.
- Mỗi **JavaCompile** task dùng release target phù hợp.
- Module test, integration test và generated source có cấu hình tương ứng.
- Plugin build, annotation processor và code generator có chạy được trên compiler JDK đã chọn.
- Dependency nội bộ không phát hành class file mới hơn runtime target của ứng dụng tiêu thụ.

Có thể áp dụng cấu hình tập trung trong convention plugin hoặc build logic dùng chung, sau đó cho phép module có yêu cầu riêng được khai báo rõ ràng. Tránh để cấu hình ở root và cấu hình module con âm thầm ghi đè lẫn nhau.

## 8. Cấu hình bằng Maven

Với Maven Compiler Plugin, thuộc tính **maven.compiler.release** là cách gọn để chọn release mục tiêu trên JDK hỗ trợ **--release**.

Ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hoặc khai báo trực tiếp trong plugin configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

Cấu hình release 17 yêu cầu compiler dùng API Java SE và class-file target tương ứng Java 17. JDK dùng để chạy Maven/compiler vẫn cần được xác định qua môi trường hoặc toolchain Maven nếu dự án quản lý nhiều JDK.

Các thuộc tính **maven.compiler.source** và **maven.compiler.target** là cấu hình kiểu cũ. Chúng không cung cấp đầy đủ bảo vệ API như **release**. Nếu phải biên dịch cho Java 8 bằng JDK 9 trở lên, hãy dùng release 8 khi compiler hỗ trợ.

## 9. Trường hợp compiler quá cũ hoặc quá mới

**--release** chỉ có thể chọn một release nằm trong phạm vi mà compiler hỗ trợ. Ví dụ, compiler JDK 17 không thể tạo class file và API target Java 21. Muốn biên dịch cho Java 21, cần compiler JDK 21 hoặc mới hơn có hỗ trợ release 21.

Ngược lại, nếu dùng JDK 8 để biên dịch cho Java 8 thì chưa có tùy chọn **--release** vì tùy chọn này được giới thiệu từ JDK 9. Khi đó compiler JDK 8 vốn nhìn thấy Java 8 API, hoặc có thể sử dụng cấu hình boot class path phù hợp trong các quy trình legacy. Với dự án mới, nên nâng compiler/build tool lên phiên bản hỗ trợ **--release** để cấu hình rõ ràng hơn.

Cũng cần kiểm tra phiên bản Gradle, Maven Compiler Plugin và plugin liên quan. Một JDK mới có thể không tương thích với build tool cũ, dù source code của ứng dụng không thay đổi. Build tool compatibility là một phần của migration, độc lập với source/class-file/API target của ứng dụng.

## 10. Multi-release JAR không phải là --release

Multi-release JAR là cơ chế đóng gói nhiều phiên bản class cho các Java release khác nhau trong cùng một file JAR. Các lớp dành cho release cụ thể nằm dưới **META-INF/versions/N**, và manifest cần khai báo **Multi-Release: true**.

Ví dụ cấu trúc:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/FastFormatter.class
│       └── 17/
│           └── com/example/FastFormatter.class
└── com/
    └── example/
        └── FastFormatter.class
~~~

JVM có hỗ trợ multi-release JAR sẽ chọn lớp phù hợp nhất với Java release đang chạy. Cơ chế này cho phép thư viện cung cấp implementation tối ưu hơn cho JDK mới và giữ implementation nền cho JDK cũ.

Nó khác với **--release**:

- **--release** là lựa chọn khi biên dịch một source set cho một Java platform release.
- Multi-release JAR là cấu trúc artifact chứa nhiều implementation theo release.
- Một JAR multi-release vẫn phải bảo đảm lớp nền và các lớp theo phiên bản có định dạng, API và semantics phù hợp.
- Không phải mọi thư viện hoặc mọi cách đóng gói đều tự động trở thành multi-release JAR.

Nếu dependency là multi-release JAR, hãy kiểm tra manifest, nội dung **META-INF/versions** và cách công cụ phân tích dependency được cấu hình. Khi kiểm tra bằng jdeps, có thể chỉ định release cần phân tích bằng tùy chọn **--multi-release**.

## 11. Kiểm tra cấu hình và artifact thực tế

Không nên chỉ đọc build.gradle hoặc pom.xml rồi kết luận artifact đã được tạo đúng. Cần kiểm tra compiler, class file và runtime.

### 11.1. Kiểm tra JDK compiler và runtime

~~~bash
java -version
javac -version
~~~

Hai lệnh có thể trả về phiên bản khác nhau nếu **PATH**, **JAVA_HOME**, toolchain hoặc môi trường shell được cấu hình khác nhau. Trong Gradle, có thể xem các JDK mà Gradle nhận diện:

~~~bash
./gradlew -q javaToolchains
~~~

Nếu dự án dùng Maven Toolchains, kiểm tra cấu hình toolchain và log compiler plugin để xác định JDK thực sự được dùng.

### 11.2. Kiểm tra class-file major version

Dùng **javap -verbose** để đọc thông tin class file:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.App
~~~

Trong output, tìm dòng:

~~~text
major version: 61
~~~

Major version 61 tương ứng Java 17. Hãy kiểm tra nhiều lớp đại diện, nhất là lớp được sinh tự động hoặc được đóng gói từ module nội bộ. Một artifact có thể chứa các class file khác release nếu dependency hoặc module được build riêng.

Có thể dùng **javap** với JAR trên classpath để xem một lớp thuộc dependency. Đừng chỉ kiểm tra một class của ứng dụng rồi suy ra toàn bộ JAR đều có cùng bytecode version.

### 11.3. Kiểm tra nội dung artifact

Dùng lệnh:

~~~bash
jar tf app.jar
~~~

Với Spring Boot executable JAR, kiểm tra các lớp ứng dụng và thư viện nằm trong cấu trúc đóng gói phù hợp, chẳng hạn **BOOT-INF/classes** và **BOOT-INF/lib**. Đối chiếu với dependency graph để phát hiện thư viện thiếu hoặc phiên bản không mong đợi.

### 11.4. Kiểm tra API và dependency

Với Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Có thể dùng:

~~~bash
jdeps --multi-release 17 --jdk-internals app.jar
~~~

để kiểm tra phụ thuộc JDK internal API khi phân tích artifact cho Java 17. Điều chỉnh release theo mục tiêu thực tế. Công cụ phân tích tĩnh không thay thế việc chạy artifact trên JVM mục tiêu.

### 11.5. Chạy artifact bằng runtime mục tiêu

Cuối cùng, chạy đúng artifact đã đóng gói bằng đúng Java runtime dự kiến triển khai:

~~~bash
java -version
java -jar app.jar
~~~

Trong pipeline, nên dùng image/container có JDK hoặc JRE mục tiêu. Xác nhận startup, health check, các luồng nghiệp vụ và kết nối dịch vụ. Nếu ứng dụng cần chạy trên nhiều Java release, hãy kiểm thử trên từng release được công bố hỗ trợ.

## 12. Các tình huống lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo source version không hỗ trợ | Compiler JDK quá cũ so với source level yêu cầu | Dùng compiler JDK phù hợp |
| Lỗi cú pháp với record/text block | Source level thấp hơn release có tính năng đó | Chọn source release phù hợp hoặc viết lại bằng cú pháp cũ |
| UnsupportedClassVersionError | Class file mới hơn JVM đang chạy | Hạ class-file target hoặc nâng runtime |
| NoSuchMethodError trên Java cũ | Class file tham chiếu API không có trong runtime | Dùng --release đúng target và kiểm tra dependency |
| NoClassDefFoundError | Thiếu class hoặc lần khởi tạo lớp trước đó thất bại | Kiểm tra runtime classpath và nguyên nhân khởi tạo |
| Lỗi chỉ xuất hiện trong container | Container dùng JRE/JDK hoặc thư viện khác local | Kiểm tra image, runtime version và artifact |
| Chỉ một module lỗi | Module đó có release target hoặc dependency khác | Kiểm tra task và cấu hình từng module |
| Lỗi khi chạy test nhưng compile thành công | Test JVM hoặc test dependency khác compile environment | Xác định test launcher và runtime classpath |
| Lỗi reflection trên JDK mới | Quyền truy cập module hoặc internal API thay đổi | Dùng API được hỗ trợ, cập nhật thư viện và kiểm thử |

Cần đọc stack trace để xác định lớp, phương thức và class loader liên quan. Một lỗi **NoSuchMethodError** có thể do JDK API hoặc do thư viện bên thứ ba; tên lớp trong stack trace và dependency graph giúp phân biệt.

## 13. Ma trận xác minh đa phiên bản

Với hệ thống phải hỗ trợ nhiều Java release, nên tạo ma trận để ghi rõ cấu hình và kết quả kiểm thử.

Ví dụ dự án hỗ trợ Java 17 và Java 21:

| Thành phần | Build mục tiêu Java 17 | Build mục tiêu Java 21 |
|---|---|---|
| Compiler JDK | 21 | 21 |
| Source level | 17 | 21 |
| Class-file major | 61 | 65 |
| Java SE API | Release 17 | Release 21 |
| Runtime kiểm tra | Java 17 | Java 21 |
| Unit/integration test | Chạy trên Java 17 | Chạy trên Java 21 |
| Kiểm tra chức năng | Luồng chính và dữ liệu | Luồng chính và dữ liệu |
| Kiểm tra hiệu năng | Baseline tương ứng | Baseline tương ứng |

Nếu chỉ phát hành một artifact cho Java 17, có thể chạy artifact đó trên Java 17 và Java 21 để xác nhận cả runtime cũ và mới nếu đó là phạm vi hỗ trợ. Nếu phát hành artifact riêng cho từng release, mỗi artifact phải được build, kiểm tra và nhận diện rõ.

Một ma trận nên ghi trạng thái từng ô như PASS, FAIL, BLOCKED hoặc NOT RUN, kèm log và artifact checksum. Không điền PASS chỉ vì build task thành công; cần xác định rõ bước nào đã chạy.

## 14. Kiểm soát source level và API target trong dự án nhiều module

Dự án nhiều module có thể gặp tình trạng module A biên dịch cho Java 17, module B tạo class file Java 21, module C dùng API Java 21 nhưng được đóng gói cùng ứng dụng Java 17. Mỗi module có thể build thành công riêng, nhưng ứng dụng tổng hợp lại không chạy được trên runtime mục tiêu.

Nên thống nhất một chính sách baseline:

1. Xác định Java runtime tối thiểu mà sản phẩm cam kết hỗ trợ.
2. Chọn source/API release tương ứng cho module ứng dụng.
3. Chọn compiler toolchain được CI và developer sử dụng.
4. Áp dụng **options.release** cho mọi task JavaCompile liên quan.
5. Kiểm tra module nội bộ và dependency bên ngoài có bytecode/API tương thích.
6. Kiểm thử test source, integration test, annotation processor và generated source.
7. Kiểm tra artifact cuối cùng, không chỉ từng module riêng lẻ.

Nếu có module chủ đích yêu cầu Java mới hơn, hãy thể hiện điều đó trong metadata, dependency graph và tài liệu phát hành. Không để module mới hơn bị kéo vào ứng dụng có runtime thấp hơn mà không có kiểm soát.

Đối với annotation processor hoặc code generator, cần phân biệt JDK dùng để chạy processor với release mà mã được sinh ra cần tuân thủ. Generated source phải được biên dịch bằng đúng **--release** mục tiêu. Plugin build có thể cần JDK mới hơn ứng dụng, nhưng bytecode của ứng dụng vẫn phải tuân theo target đã định.

## 15. Những gì --release không đảm bảo

**--release** là cơ chế quan trọng để kiểm soát Java SE API và class-file target, nhưng không phải chứng nhận tương thích toàn hệ thống.

Nó không tự xác nhận:

- Dependency bên thứ ba có class-file version phù hợp.
- Runtime classpath trùng với compile classpath.
- Spring bean, reflection, service loader hoặc cấu hình framework khởi tạo thành công.
- Driver database, native library hoặc application server tương thích.
- Schema database và payload giữa các service không thay đổi semantics.
- Ứng dụng đáp ứng latency, throughput và resource target.
- Ứng dụng chạy đúng trên mọi OS, container và cấu hình production.

Vì vậy, sau khi biên dịch với **--release**, vẫn cần dependency analysis, artifact inspection, runtime test và kiểm thử chức năng.

## 16. Quy trình chọn và xác minh target

Có thể áp dụng quy trình sau khi chuẩn bị build đa phiên bản:

### Bước 1: Xác định runtime tối thiểu

Làm rõ Java release thấp nhất mà ứng dụng cần hỗ trợ. Căn cứ vào nền tảng triển khai, thư viện, framework và chính sách sản phẩm.

### Bước 2: Chọn compiler JDK

Chọn JDK có thể biên dịch source release và API target đã chọn. Ghi rõ vendor và version trong CI để tránh máy local và pipeline sử dụng compiler khác nhau.

### Bước 3: Cấu hình source, class file và API

Với JDK 9 trở lên, dùng **--release N** hoặc cấu hình tương ứng trong Gradle/Maven. Không dựa riêng vào **sourceCompatibility** và **targetCompatibility** nếu yêu cầu là giới hạn Java SE API.

### Bước 4: Kiểm tra dependency

Xác minh thư viện nội bộ, thư viện bên thứ ba, annotation processor và plugin build. Đọc release notes và Java compatibility của các phiên bản được chọn.

### Bước 5: Kiểm tra artifact

Đọc class-file major version, nội dung JAR và dependency đóng gói. Xem xét multi-release JAR và preview feature nếu dự án có sử dụng.

### Bước 6: Chạy trên runtime mục tiêu

Chạy artifact trong JDK/JRE mục tiêu, thực hiện startup test, unit/integration test và các luồng nghiệp vụ quan trọng. Với nhiều target, kiểm tra từng target được công bố hỗ trợ.

### Bước 7: Lưu bằng chứng

Lưu build log, JDK version, cấu hình release, dependency report, checksum artifact và kết quả test. Khi có lỗi, ghi rõ release, module, class hoặc API liên quan.

## 17. Nguyên tắc cần nhớ

- Source language level kiểm soát cú pháp và tính năng ngôn ngữ.
- Class-file target kiểm soát định dạng bytecode mà JVM cần đọc.
- Platform API release kiểm soát API Java SE mà mã nguồn được phép sử dụng.
- Compiler JDK/toolchain xác định compiler thực tế, không đồng nghĩa runtime triển khai.
- **-source** và **-target** riêng lẻ không giới hạn đầy đủ API nền tảng.
- **--release** đồng bộ source, class file và Java SE API target trên JDK hỗ trợ.
- Dependency bên ngoài, reflection, native code và cấu hình vẫn cần được xác minh riêng.
- Chỉ chạy artifact trên runtime mục tiêu mới cung cấp bằng chứng trực tiếp về khả năng nạp và khởi tạo trên nền tảng đó.

Một cấu hình biên dịch đa phiên bản đáng tin cậy phải nói rõ mã nguồn dùng ngôn ngữ nào, bytecode được tạo cho JVM nào và API nền tảng nào được phép tham chiếu. Khi ba lựa chọn này được kiểm soát cùng với dependency và runtime thực tế, nhóm có thể phát hiện sớm lỗi tương thích và đưa ra kết luận migration dựa trên bằng chứng rõ ràng.
