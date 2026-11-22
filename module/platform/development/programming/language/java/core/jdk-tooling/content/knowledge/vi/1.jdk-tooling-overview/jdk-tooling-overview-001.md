# JDK Tooling là gì?

## 1. Khái niệm

**JDK Tooling** là tập hợp các công cụ đi kèm **Java Development Kit (JDK)**, hỗ trợ toàn bộ vòng đời phát triển và vận hành ứng dụng Java: kiểm tra môi trường, biên dịch mã nguồn, chạy chương trình, đóng gói, tạo tài liệu, phân tích phụ thuộc, tạo bộ runtime riêng, quản lý chứng chỉ và chẩn đoán ứng dụng đang chạy.

JDK Tooling không phải một chương trình duy nhất. Đó là nhiều lệnh và tiện ích chuyên biệt, thường được chạy từ Terminal hoặc Command Prompt, được IDE và hệ thống build gọi ở phía sau.

Ví dụ, khi chạy `javac`, bạn dùng trình biên dịch Java. Khi chạy `jar`, bạn đóng gói các lớp đã biên dịch thành tệp JAR. Khi chạy `jcmd` hoặc `jstack`, bạn kiểm tra trạng thái của một tiến trình Java đang hoạt động.

Mục tiêu của tooling là giúp lập trình viên kiểm soát rõ ràng các bước kỹ thuật thay vì chỉ phụ thuộc vào nút Run trong IDE.

## 2. JDK, JVM và các công cụ liên quan

Để hiểu JDK Tooling, cần phân biệt ba khái niệm:

- **JVM (Java Virtual Machine):** môi trường thực thi bytecode Java. JVM tải lớp, kiểm tra bytecode, quản lý bộ nhớ, garbage collection và có thể biên dịch các đoạn mã thường chạy thành mã máy bằng JIT compiler.
- **JDK (Java Development Kit):** bộ công cụ phát triển Java. JDK cung cấp runtime để chạy ứng dụng, thư viện chuẩn, trình biên dịch và nhiều tiện ích phục vụ phát triển, đóng gói, kiểm tra và chẩn đoán.
- **JDK tools:** các chương trình như `java`, `javac`, `jar`, `javadoc`, `jshell`, `jdeps`, `jlink`, `jpackage`, `keytool` và `jcmd`.

Luồng cơ bản khi phát triển một chương trình Java:

```text
Mã nguồn .java
      |
      | javac
      v
Bytecode .class
      |
      | jar (tùy chọn)
      v
Tệp .jar
      |
      | java
      v
JVM thực thi chương trình
```

Tệp `.class` chứa bytecode, không phải mã máy dành riêng cho một CPU. JVM trên từng nền tảng chịu trách nhiệm thực thi bytecode và tương tác với hệ điều hành. Vì vậy, cùng một JAR có thể chạy trên nhiều hệ điều hành nếu các nền tảng có runtime tương thích và ứng dụng không phụ thuộc vào thành phần đặc thù của một hệ điều hành.

Trong các phiên bản Java hiện đại, JDK đã bao gồm môi trường cần thiết để chạy ứng dụng. Khái niệm cài đặt một JRE riêng từng phổ biến trong các phiên bản cũ; với Java 9 trở đi, hệ thống module và các runtime image tùy chỉnh làm cho cách phân phối runtime linh hoạt hơn. Khi học và phát triển ứng dụng, thông thường bạn cài một bản JDK phù hợp thay vì tìm một gói JRE riêng.

## 3. Các nhóm công cụ quan trọng

Tên và cách sử dụng chi tiết có thể khác đôi chút theo phiên bản JDK, nhà cung cấp và hệ điều hành. Các công cụ dưới đây là những công cụ thường gặp trong JDK hiện đại, đặc biệt hữu ích khi làm việc với Java 17 trở lên.

| Công cụ | Chức năng | Khi nào sử dụng |
|---|---|---|
| `java` | Khởi chạy ứng dụng Java, lớp chính, JAR hoặc module | Chạy chương trình |
| `javac` | Biên dịch mã nguồn `.java` thành bytecode `.class` | Biên dịch ứng dụng |
| `jar` | Tạo, xem và cập nhật tệp JAR | Đóng gói ứng dụng hoặc thư viện |
| `javadoc` | Sinh tài liệu HTML từ mã nguồn và JavaDoc comment | Tạo API documentation |
| `jshell` | Môi trường REPL để thử biểu thức và câu lệnh Java | Học, thử API hoặc kiểm tra ý tưởng nhanh |
| `javap` | Phân tích thông tin lớp và bytecode | Kiểm tra chữ ký phương thức, modifier và bytecode |
| `jdeps` | Phân tích phụ thuộc giữa các lớp, JAR và module | Kiểm tra phụ thuộc, chuẩn bị chuyển sang module |
| `jdeprscan` | Phát hiện việc sử dụng API đã bị đánh dấu deprecated | Rà soát mã trước khi nâng cấp |
| `jlink` | Tạo runtime image tùy chỉnh từ các module | Phân phối runtime gọn hơn |
| `jpackage` | Đóng gói ứng dụng thành gói cài đặt phù hợp nền tảng | Phân phối ứng dụng desktop hoặc ứng dụng độc lập |
| `keytool` | Quản lý keystore, khóa và chứng chỉ số | Làm việc với TLS, chứng chỉ và khóa |
| `jarsigner` | Ký và kiểm tra chữ ký JAR | Xác minh nguồn gốc và tính toàn vẹn gói JAR |
| `jcmd` | Gửi lệnh chẩn đoán tới tiến trình JVM | Kiểm tra thread, runtime, heap và Java Flight Recorder |
| `jstack` | Lấy thread dump | Điều tra deadlock hoặc thread bị treo |
| `jmap` | Xem thông tin heap và tạo heap dump | Điều tra lỗi bộ nhớ |
| `jstat` | Hiển thị thống kê JVM, garbage collection và class loading | Theo dõi hoạt động runtime |
| `jfr` | Đọc và phân tích bản ghi Java Flight Recorder | Điều tra hiệu năng |
| `jmod`, `jimage` | Làm việc với tệp JMOD và ảnh runtime | Công việc nâng cao liên quan đến module và runtime image |
| `serialver` | Hiển thị `serialVersionUID` của lớp Serializable | Kiểm tra tương thích tuần tự hóa |

Không phải mọi bản phân phối hoặc môi trường runtime tối giản đều có đầy đủ các lệnh này. Một runtime image được tạo bằng `jlink` có thể chỉ chứa những module cần thiết để chạy ứng dụng, do đó không nhất thiết có compiler hoặc các công cụ chẩn đoán.

### 3.1. Công cụ biên dịch và chạy chương trình

- `javac`: chuyển mã nguồn Java thành bytecode. Có thể chỉ định thư mục đầu ra, classpath, module path và phiên bản API mục tiêu.
- `java`: khởi chạy chương trình từ class, JAR hoặc module. Lệnh này cũng nhận các tùy chọn cấu hình JVM như bộ nhớ heap, garbage collector và system properties.
- `jshell`: cho phép nhập câu lệnh Java tương tác mà không cần tạo một dự án hoàn chỉnh.
- `javap`: giúp xem cấu trúc lớp đã biên dịch, hữu ích khi tìm hiểu bytecode hoặc kiểm tra API mà một thư viện cung cấp.

### 3.2. Công cụ đóng gói và tài liệu

- `jar`: gom các tệp `.class`, tài nguyên và metadata thành một gói JAR.
- `javadoc`: tạo tài liệu API từ comment có cú pháp JavaDoc như `/** ... */`.
- `jpackage`: tạo gói phân phối hoặc bộ cài đặt theo hệ điều hành đích. Khả năng tạo định dạng cài đặt phụ thuộc nền tảng và công cụ hệ thống tương ứng.

### 3.3. Công cụ module và phụ thuộc

- `jdeps`: cho biết một ứng dụng hoặc thư viện phụ thuộc vào package, module nào. Đây là bước hữu ích khi loại bỏ phụ thuộc không cần thiết hoặc chuẩn bị dùng JPMS.
- `jlink`: ghép các module cần thiết để tạo runtime image riêng. Ứng dụng có thể được phân phối cùng runtime này mà không yêu cầu người dùng cài một JDK đầy đủ.
- `jmod` và `jimage`: hỗ trợ các định dạng module và runtime image ở mức thấp hơn.

### 3.4. Công cụ bảo mật

- `keytool`: tạo và quản lý keystore, cặp khóa và chứng chỉ. Keystore thường được dùng khi cấu hình HTTPS/TLS hoặc ký ứng dụng.
- `jarsigner`: ký tệp JAR bằng khóa phù hợp và kiểm tra chữ ký của gói đã ký.

Cần bảo vệ keystore và mật khẩu của nó như thông tin nhạy cảm. Không đưa private key hoặc mật khẩu vào repository, log build hay tài liệu công khai.

### 3.5. Công cụ chẩn đoán runtime

- `jcmd`: giao tiếp với tiến trình JVM để lấy thông tin hoặc yêu cầu thực hiện một thao tác chẩn đoán.
- `jstack`: lấy stack trace của các thread tại một thời điểm.
- `jmap`: hỗ trợ kiểm tra heap và tạo heap dump.
- `jstat`: hiển thị số liệu runtime theo chu kỳ.
- `jfr`: đọc các bản ghi Java Flight Recorder; việc bắt đầu và dừng ghi thường được điều khiển qua `jcmd`.

Các công cụ này hữu ích khi ứng dụng chậm, tiêu thụ nhiều CPU, có dấu hiệu rò rỉ bộ nhớ, dừng phản hồi hoặc nghi ngờ deadlock.

## 4. Kiểm tra và cấu hình môi trường JDK

Trước khi sử dụng tooling, hãy xác định máy đang cài JDK nào và Terminal đang gọi đúng phiên bản hay chưa.

Chạy các lệnh:

```bash
java --version
javac --version
jshell --version
```

`java --version` cho biết phiên bản runtime launcher. `javac --version` xác nhận có compiler và cho biết phiên bản compiler. Hai phiên bản này nên được kiểm tra cùng nhau vì máy có thể cài nhiều JDK và PATH có thể trỏ tới các bản khác nhau.

Có thể kiểm tra đường dẫn lệnh đang được hệ điều hành tìm thấy:

- Windows PowerShell: `Get-Command java` và `Get-Command javac`.
- Windows Command Prompt: `where java` và `where javac`.
- Linux/macOS: `which java` và `which javac`.

### 4.1. JAVA_HOME và PATH

`JAVA_HOME` thường trỏ đến thư mục gốc của JDK, ví dụ:

```text
C:\Program Files\Java\jdk-17
```

PATH cần chứa thư mục `bin` bên trong JDK:

- Windows: `%JAVA_HOME%\bin`
- Linux/macOS: `$JAVA_HOME/bin`

Không đặt `JAVA_HOME` trỏ thẳng vào thư mục `bin`. Nhiều công cụ build, IDE và script dựa vào `JAVA_HOME` để tìm JDK.

Nếu máy có nhiều JDK, hãy kiểm tra cả `JAVA_HOME`, PATH và kết quả của `java --version`/`javac --version`. Chỉ sửa một biến mà bỏ qua các vị trí còn lại có thể khiến terminal, IDE và hệ thống build sử dụng các JDK khác nhau.

## 5. Ví dụ thực hành: biên dịch và chạy một chương trình

Ví dụ sau sử dụng Java 17 trở lên. Tạo tệp `src/com/example/Hello.java` với nội dung:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, JDK Tooling!");
    }
}
```

Tạo thư mục đầu ra `out`, sau đó biên dịch:

```bash
mkdir out
javac --release 17 -d out src/com/example/Hello.java
```

Ý nghĩa các tùy chọn:

- `--release 17`: biên dịch theo bộ ngôn ngữ, bytecode và API công khai của Java 17. Tùy chọn này phù hợp khi dùng JDK mới hơn nhưng cần bảo đảm ứng dụng tương thích Java 17.
- `-d out`: ghi các tệp `.class` vào thư mục `out`. Do lớp khai báo package `com.example`, compiler tự tạo cấu trúc thư mục tương ứng bên trong `out`.

Chạy chương trình:

```bash
java -cp out com.example.Hello
```

Kết quả:

```text
Hello, JDK Tooling!
```

Trong lệnh trên:

- `-cp out` đặt thư mục `out` vào classpath để JVM tìm lớp đã biên dịch.
- `com.example.Hello` là tên đầy đủ của lớp (fully qualified class name), gồm package và tên lớp.
- Phương thức `main` là điểm bắt đầu của chương trình theo cách khởi chạy truyền thống.

Nếu thư mục `out` đã tồn tại, không cần tạo lại. Các lệnh trên có thể chạy trong Terminal tại thư mục gốc của dự án; cú pháp đường dẫn có thể thay đổi tùy shell và hệ điều hành.

## 6. Ví dụ thực hành: đóng gói thành JAR

Sau khi biên dịch thành công, dùng `jar` để tạo một JAR có khai báo lớp chính:

```bash
jar --create --file app.jar --main-class com.example.Hello -C out .
```

Ý nghĩa:

- `--create`: tạo JAR mới.
- `--file app.jar`: đặt tên tệp đầu ra.
- `--main-class com.example.Hello`: ghi lớp chính vào manifest của JAR.
- `-C out .`: chuyển vào thư mục `out` rồi đưa nội dung thư mục đó vào JAR.

Liệt kê nội dung JAR:

```bash
jar --list --file app.jar
```

Chạy JAR:

```bash
java -jar app.jar
```

Kết quả chương trình vẫn là:

```text
Hello, JDK Tooling!
```

Cách này minh họa vai trò phối hợp của `javac`, `jar` và `java`: biên dịch mã nguồn, đóng gói bytecode, rồi khởi chạy gói ứng dụng.

## 7. Một số thao tác tooling hữu ích khác

### 7.1. Thử nhanh với JShell

Mở JShell:

```bash
jshell
```

Nhập một biểu thức:

```java
int total = 12 + 8;
System.out.println(total);
```

JShell thực thi câu lệnh ngay trong phiên tương tác. Thoát bằng lệnh:

```text
/exit
```

JShell phù hợp để thử một API, kiểm tra biểu thức hoặc minh họa một tính năng ngôn ngữ. Với ứng dụng cần quản lý nhiều lớp, dependency và cấu trúc dự án, hãy dùng dự án Java thông thường.

### 7.2. Xem bytecode bằng javap

Sau khi biên dịch ví dụ ở trên:

```bash
javap -classpath out -c com.example.Hello
```

`-classpath out` cho `javap` biết nơi tìm lớp. `-c` yêu cầu hiển thị bytecode của các phương thức. Đây là cách quan sát mã nguồn Java được chuyển thành các lệnh bytecode mà JVM thực thi.

### 7.3. Tạo tài liệu bằng javadoc

Từ thư mục gốc của dự án:

```bash
javadoc -d docs src/com/example/Hello.java
```

Tài liệu HTML được tạo trong thư mục `docs`. Để tài liệu có ích cho người dùng thư viện, hãy viết JavaDoc comment cho class, constructor và các phương thức API công khai. `javadoc` có thể phát cảnh báo khi thiếu comment hoặc thông tin tài liệu chưa đầy đủ.

### 7.4. Phân tích phụ thuộc bằng jdeps

```bash
jdeps --summary app.jar
```

Lệnh này tóm tắt các phụ thuộc module của JAR. Kết quả có thể giúp xác định module nào cần có khi tạo runtime image bằng `jlink`.

### 7.5. Tạo runtime image bằng jlink

Ví dụ tạo runtime tối giản chỉ chứa module `java.base`:

```bash
jlink --add-modules java.base --output runtime-image
```

`jlink` ghép các module cần thiết để tạo runtime image riêng. Ứng dụng có thể được phân phối cùng runtime này mà không yêu cầu người dùng cài một JDK đầy đủ.

Runtime image này chứa runtime có thể chạy ứng dụng chỉ dùng các API thuộc `java.base`. Nếu ứng dụng sử dụng module khác, cần thêm các module tương ứng, ví dụ bằng danh sách module lấy từ phân tích phụ thuộc và cấu hình ứng dụng.

Runtime image này không phải một JDK đầy đủ: nó được tạo để chạy ứng dụng, không nhằm cung cấp toàn bộ compiler và công cụ phát triển.

### 7.6. Chẩn đoán tiến trình Java bằng jcmd

Liệt kê các tiến trình JVM mà công cụ có thể phát hiện:

```bash
jcmd -l
```

Xem phiên bản JVM của một tiến trình:

```bash
jcmd <pid> VM.version
```

Lấy thread dump:

```bash
jcmd <pid> Thread.print
```

Trong đó `<pid>` là process ID của ứng dụng Java. Có thể dùng `jstack <pid>` cho mục đích lấy thread dump tương tự.

### 7.7. Theo dõi garbage collection bằng jstat

```bash
jstat -gc <pid> 1000 5
```

Lệnh này yêu cầu thống kê GC của tiến trình với khoảng lấy mẫu 1.000 mili giây, tối đa 5 lần. Các cột thể hiện thông tin về vùng heap và hoạt động garbage collection; ý nghĩa cụ thể của từng cột cần được đọc theo tài liệu của phiên bản JDK đang dùng.

### 7.8. Ghi Java Flight Recorder

Có thể yêu cầu JVM bắt đầu ghi JFR trong 60 giây:

```bash
jcmd <pid> JFR.start duration=60s filename=app.jfr
```

Sau khi bản ghi được tạo, xem phần tổng quan:

```bash
jfr summary app.jfr
```

JFR thu thập sự kiện runtime phục vụ phân tích hiệu năng và hành vi ứng dụng. Khi cần tìm nguyên nhân chậm, hãy kết hợp dữ liệu JFR với log, metrics và thông tin tải thực tế.

### 7.9. Kiểm tra keystore bằng keytool

Ví dụ liệt kê nội dung một keystore định dạng PKCS12:

```bash
keytool -list -keystore my-keystore.p12 -storetype PKCS12
```

Lệnh có thể yêu cầu mật khẩu keystore. Không ghi mật khẩu thật vào script hoặc lịch sử terminal dùng chung.

## 8. JDK Tooling và Maven, Gradle, IDE

JDK Tooling là nền tảng kỹ thuật mà nhiều công cụ phát triển khác sử dụng:

- **Maven** và **Gradle** là công cụ build và quản lý dependency. Chúng điều phối các bước như biên dịch, chạy test, đóng gói và tạo artifact; thông thường chúng gọi compiler và runtime từ một JDK được cấu hình.
- **IDE** như IntelliJ IDEA, Eclipse hoặc VS Code cung cấp giao diện viết mã, debug, refactor và quản lý dự án. IDE có thể gọi `javac`, `java` và các công cụ JDK ở phía sau.
- **Framework và thư viện** như Spring hoặc JUnit cung cấp chức năng cho ứng dụng và kiểm thử. Chúng không phải là các lệnh JDK và thường được quản lý như dependency của dự án.

Do đó, cài một JDK không đồng nghĩa đã cài Maven hoặc Gradle. Ngược lại, một dự án dùng Maven/Gradle vẫn cần JDK phù hợp để biên dịch và chạy các tác vụ Java.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `javac` không được nhận diện | Chưa cài JDK hoặc PATH không có thư mục `bin` của JDK | Kiểm tra JDK, `JAVA_HOME`, PATH và `Get-Command`/`where`/`which` |
| `java` và `javac` có phiên bản khác nhau | PATH trỏ tới nhiều bản Java hoặc terminal dùng JDK khác với IDE | Kiểm tra đường dẫn và cấu hình JDK của từng công cụ |
| `UnsupportedClassVersionError` | Runtime đang chạy cũ hơn phiên bản bytecode mà compiler tạo ra | Dùng runtime tương thích hoặc biên dịch với `--release` phù hợp |
| `Could not find or load main class` | Sai classpath, sai tên package/lớp hoặc chạy sai thư mục | Kiểm tra `-cp`, cấu trúc thư mục và tên lớp đầy đủ |
| Không chạy được `java -jar` | JAR thiếu manifest hoặc không khai báo `Main-Class` hợp lệ | Tạo lại JAR với `--main-class` hoặc cấu hình manifest |
| `NoSuchMethodError` khi chạy | Phiên bản thư viện lúc chạy không giống phiên bản lúc biên dịch hoặc dependency bị xung đột | Kiểm tra dependency tree và classpath thực tế |
| `jcmd` không thấy hoặc không attach được tiến trình | Khác người dùng hệ điều hành, giới hạn attach, container hoặc cấu hình runtime | Kiểm tra quyền truy cập, môi trường tiến trình và giới hạn của nền tảng |

Một số lưu ý khi xử lý:

1. Nếu `java` chạy được nhưng `javac` không tồn tại, hãy kiểm tra xem máy có chỉ cài runtime tối giản hoặc PATH đang trỏ tới một runtime khác hay không.
2. Nếu có nhiều JDK, kiểm tra phiên bản trong terminal, IDE và Maven/Gradle. Không nên giả định tất cả cùng dùng một JDK.
3. Trên Windows, dấu phân cách nhiều mục classpath thường là dấu chấm phẩy (`;`); trên Linux/macOS thường là dấu hai chấm (`:`).
4. Khi dùng package, tên lớp chạy phải bao gồm package. Ví dụ `com.example.Hello`, không phải chỉ `Hello`.
5. Các công cụ tạo heap dump hoặc lấy dữ liệu chẩn đoán có thể ảnh hưởng đến hiệu năng và tạo tệp lớn. Heap dump có thể chứa dữ liệu nhạy cảm trong bộ nhớ ứng dụng, vì vậy cần bảo vệ tệp và chỉ thu thập khi phù hợp.

## 10. Cách chọn công cụ theo công việc

| Nhu cầu | Công cụ nên bắt đầu |
|---|---|
| Kiểm tra máy đã cài đúng Java chưa | `java --version`, `javac --version` |
| Biên dịch mã nguồn | `javac` |
| Chạy chương trình | `java` |
| Thử một đoạn Java nhỏ | `jshell` |
| Xem bytecode hoặc cấu trúc lớp | `javap` |
| Đóng gói ứng dụng | `jar` |
| Sinh tài liệu API | `javadoc` |
| Kiểm tra phụ thuộc module | `jdeps` |
| Tạo runtime riêng | `jlink` |
| Tạo bộ cài ứng dụng | `jpackage` |
| Quản lý chứng chỉ và khóa | `keytool`, `jarsigner` |
| Xem thread của ứng dụng đang chạy | `jcmd`, `jstack` |
| Điều tra bộ nhớ | `jcmd`, `jmap`, `jstat` |
| Phân tích hiệu năng theo sự kiện runtime | `jcmd`, `jfr` |

## 11. Tổng kết

JDK Tooling là bộ công cụ hỗ trợ lập trình viên làm việc trực tiếp với mã nguồn, bytecode, runtime và quá trình phân phối ứng dụng Java. Các lệnh quan trọng nhất cần làm quen đầu tiên là:

- `java` để chạy chương trình.
- `javac` để biên dịch.
- `jar` để đóng gói.
- `jshell` để thử nghiệm nhanh.
- `javadoc` để tạo tài liệu.
- `javap` và `jdeps` để kiểm tra cấu trúc và phụ thuộc.
- `jcmd`, `jstack`, `jstat` và `jfr` để chẩn đoán runtime.

Khi đã hiểu vai trò của từng công cụ, bạn có thể đọc được các lệnh mà IDE hoặc hệ thống build thực hiện, tự biên dịch và đóng gói một ứng dụng nhỏ, đồng thời biết bắt đầu từ đâu khi cần điều tra sự cố của một tiến trình Java.
