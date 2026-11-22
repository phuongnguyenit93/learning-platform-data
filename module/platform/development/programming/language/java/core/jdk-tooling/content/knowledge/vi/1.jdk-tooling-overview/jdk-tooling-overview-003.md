# JDK và JRE

JDK và JRE đều liên quan đến việc sử dụng nền tảng Java, nhưng phục vụ hai mục đích khác nhau:

- **JDK (Java Development Kit)** cung cấp công cụ để viết, biên dịch, kiểm thử và đóng gói chương trình Java. Người phát triển Java cần JDK.
- **JRE (Java Runtime Environment)** là môi trường cần thiết để chạy chương trình Java đã được biên dịch.
- **JVM (Java Virtual Machine)** là máy ảo thực thi bytecode Java. JVM là một thành phần cốt lõi của môi trường chạy Java.

Có thể ghi nhớ nhanh: **JDK dùng để phát triển; JRE dùng để chạy; JVM thực thi bytecode.**

## 1. Chương trình Java được biên dịch và chạy như thế nào?

Một chương trình Java thông thường đi qua các bước sau:

1. Lập trình viên viết mã nguồn trong tệp `.java`.
2. Trình biên dịch `javac` chuyển mã nguồn thành bytecode và lưu trong tệp `.class`.
3. JVM nạp, kiểm tra và thực thi bytecode. Tùy JVM, mã có thể được thông dịch hoặc biên dịch tức thời (JIT) thành mã máy để tăng hiệu năng.
4. Trong lúc chạy, chương trình sử dụng các lớp và API của thư viện Java tiêu chuẩn, cùng những thành phần runtime cần thiết.

Bytecode được thiết kế để có thể chạy trên nhiều hệ điều hành và kiến trúc phần cứng. Tuy vậy, mỗi nền tảng cần một bản cài đặt JVM phù hợp. Vì thế, cùng một tệp `.class` có thể chạy trên Windows, macOS hoặc Linux nếu môi trường Java tương thích được cài đặt.

## 2. JVM là gì?

**JVM (Java Virtual Machine)** là máy ảo định nghĩa cách nạp và thực thi bytecode Java. JVM tạo ra lớp trừu tượng giữa chương trình Java và hệ điều hành.

Một số nhiệm vụ chính của JVM:

- **Nạp lớp (Class Loading):** tìm và nạp các lớp cần thiết khi chương trình chạy.
- **Kiểm tra bytecode (Bytecode Verification):** kiểm tra cấu trúc và tính hợp lệ của bytecode trước khi thực thi.
- **Thực thi:** thông dịch bytecode hoặc dùng JIT (Just-In-Time Compiler) để biên dịch những đoạn mã phù hợp thành mã máy.
- **Quản lý bộ nhớ:** tổ chức vùng nhớ runtime và phối hợp với bộ thu gom rác (Garbage Collector) để thu hồi đối tượng không còn được sử dụng.
- **Cung cấp môi trường thực thi:** hỗ trợ luồng, ngoại lệ, đồng bộ và các cơ chế runtime khác.

JVM là một đặc tả; các nhà cung cấp có thể xây dựng những bản triển khai JVM khác nhau. Bản triển khai phải phù hợp với hệ điều hành và kiến trúc mà nó chạy trên đó.

## 3. JRE là gì?

**JRE (Java Runtime Environment)** là môi trường chạy một ứng dụng Java. Theo mô hình truyền thống, JRE gồm:

- JVM để thực thi bytecode.
- Các thư viện Java tiêu chuẩn mà ứng dụng cần khi chạy.
- Những tệp và thành phần hỗ trợ runtime khác.

JRE hướng đến người cần **chạy** ứng dụng Java. Một người dùng chỉ chạy một ứng dụng đã được đóng gói thường không cần các công cụ phát triển như trình biên dịch `javac`.

JRE không phải là một phiên bản Java khác với JDK. Đây là cách gọi môi trường runtime và các thành phần cần thiết để chạy ứng dụng. Cách đóng gói JRE phụ thuộc vào phiên bản Java và nhà cung cấp bản phân phối.

## 4. JDK là gì?

**JDK (Java Development Kit)** là bộ công cụ dành cho phát triển phần mềm Java. JDK cung cấp môi trường runtime cùng các công cụ để tạo và kiểm tra chương trình.

Các công cụ thường gặp gồm:

| Công cụ | Công dụng |
| --- | --- |
| `java` | Khởi chạy ứng dụng Java |
| `javac` | Biên dịch mã nguồn `.java` thành bytecode `.class` |
| `jar` | Tạo và thao tác với tệp JAR |
| `javadoc` | Sinh tài liệu API từ mã nguồn và chú thích |
| `jshell` | Chạy thử biểu thức và câu lệnh Java tương tác |
| `jdb` | Gỡ lỗi chương trình Java |
| `jlink` | Tạo runtime image tùy chỉnh từ các module cần thiết |

Tên và tập công cụ cụ thể có thể thay đổi theo phiên bản hoặc nhà cung cấp. JDK là lựa chọn phù hợp khi viết mã, biên dịch, chạy thử, gỡ lỗi hoặc đóng gói ứng dụng Java.

## 5. JDK, JRE và JVM liên hệ với nhau như thế nào?

Có thể hình dung mối quan hệ theo chức năng:

- JVM thực thi bytecode.
- JRE cung cấp JVM, thư viện và các thành phần cần thiết để chạy ứng dụng.
- JDK cung cấp các công cụ phát triển, đồng thời có runtime để chạy và kiểm thử ứng dụng.

Bảng sau giúp phân biệt ba khái niệm:

| Tiêu chí | JVM | JRE | JDK |
| --- | --- | --- | --- |
| Mục đích | Thực thi bytecode | Chạy ứng dụng Java | Phát triển và chạy ứng dụng |
| Thành phần chính | Máy ảo thực thi | JVM và thư viện runtime | Runtime cùng công cụ phát triển |
| Có trình biên dịch `javac` | Không | Thông thường không | Có |
| Đối tượng sử dụng | Thành phần nền tảng runtime | Người dùng/chủ máy chạy ứng dụng | Lập trình viên và môi trường build |
| Vai trò | Thực thi | Cung cấp môi trường chạy | Cung cấp bộ công cụ phát triển |

**Lưu ý:** Bảng mô tả vai trò và mô hình thành phần. Các bản phân phối Java hiện đại có thể tổ chức hoặc đóng gói các thành phần khác nhau; không nên chỉ dựa vào tên thư mục để kết luận một thành phần có hay không.

## 6. Vì sao cách đóng gói JRE thay đổi theo phiên bản Java?

Ở các bản Java cũ, đặc biệt là Java 8, người dùng thường gặp hai gói cài đặt riêng: JDK cho phát triển và JRE cho chạy ứng dụng. Trong nhiều bản phân phối Java 8, thư mục cài JDK còn có thư mục con tên `jre`.

Từ Java 9, Java chuyển sang hệ thống module. Runtime có thể được tổ chức thành một ảnh runtime (runtime image) gồm những module cần thiết. Vì vậy, cấu trúc cài đặt không nhất thiết còn có thư mục `jre` nằm bên trong JDK.

Ngoài ra, Oracle không còn phát hành gói cài JRE riêng theo cách quen thuộc cùng các bản Oracle JDK 11 trở đi. Tuy nhiên, một số nhà cung cấp Java khác vẫn có thể cung cấp gói runtime-only hoặc JRE riêng.

Do đó:

- Không thấy thư mục `jre` trong thư mục JDK hiện đại không có nghĩa là JDK thiếu khả năng chạy Java.
- Tên gói tải xuống và cách tổ chức thư mục phụ thuộc vào nhà cung cấp.
- Khi triển khai ứng dụng, hãy kiểm tra tài liệu của bản phân phối đang dùng và yêu cầu runtime của ứng dụng.

## 7. Khi nào nên cài JDK, khi nào cần runtime?

**Cài JDK khi:**

- Bạn học hoặc phát triển Java.
- Bạn cần chạy `javac`, `jar`, `javadoc`, `jshell` hoặc công cụ phát triển khác.
- Bạn chạy Maven, Gradle hoặc một quy trình build cần JDK.
- Bạn cần biên dịch và kiểm thử ứng dụng trên máy cá nhân hoặc máy build.

**Chỉ cần runtime khi:**

- Máy chỉ có nhiệm vụ chạy một ứng dụng Java đã được biên dịch.
- Nhà cung cấp ứng dụng chỉ yêu cầu runtime tương thích.
- Bạn triển khai một runtime image tối giản đã được tạo và kiểm thử cho ứng dụng.

Cài JDK trên máy chạy ứng dụng vẫn có thể hoạt động, nhưng thường mang theo nhiều công cụ hơn mức cần thiết. Với môi trường triển khai, nhóm phát triển có thể dùng `jlink` để tạo runtime image chỉ gồm các module cần thiết. Cách làm này cần được kiểm thử cùng ứng dụng và thư viện thực tế.

## 8. Kiểm tra Java đã được cài đặt

Mở Terminal, Command Prompt hoặc PowerShell và chạy:

```bash
java -version
javac -version
```

- `java -version` hiển thị phiên bản trình khởi chạy/runtime Java đang được tìm thấy qua `PATH`.
- `javac -version` hiển thị phiên bản trình biên dịch. Công cụ này thường có trong JDK.

Trên Windows, có thể xác định tệp thực thi đang được chọn bằng:

```powershell
where.exe java
where.exe javac
```

Trên macOS hoặc Linux:

```bash
command -v java
command -v javac
```

Nếu `java` chạy được nhưng `javac` không được tìm thấy, có thể máy đang trỏ đến một runtime-only package hoặc `PATH` chưa trỏ đến thư mục `bin` của JDK.

### JAVA_HOME và PATH

- `JAVA_HOME` thường trỏ đến thư mục gốc của JDK, ví dụ `C:\Program Files\Java\jdk-17` trên Windows hoặc `/opt/jdk-17` trên Linux.
- `PATH` cần chứa thư mục `bin` của JDK nếu muốn gọi `java`, `javac` và các công cụ khác từ mọi thư mục.
- Không đặt `JAVA_HOME` trỏ thẳng vào thư mục `bin`; hãy trỏ đến thư mục gốc của JDK.

Ví dụ cấu hình trong PowerShell cho phiên làm việc hiện tại:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

Ví dụ trên Linux/macOS (thay đường dẫn bằng nơi JDK thực sự được cài):

```bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
```

Việc đặt `JAVA_HOME` không phải điều kiện bắt buộc để chính lệnh `java` hoạt động, nhưng nhiều công cụ build và môi trường phát triển sử dụng biến này để tìm JDK.

## 9. Ví dụ: biên dịch và chạy một chương trình Java

Tạo tệp `Hello.java` với nội dung:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Java!");
    }
}
```

Mở terminal tại thư mục chứa tệp và chạy:

```bash
javac Hello.java
java Hello
```

Kết quả:

```text
Xin chào Java!
```

Giải thích:

1. `javac Hello.java` dùng trình biên dịch thuộc JDK để tạo tệp `Hello.class`.
2. `java Hello` khởi chạy lớp `Hello`; JVM nạp và thực thi bytecode trong lớp đó.
3. Khi chạy lệnh `java`, chỉ ghi tên lớp `Hello`, không thêm phần mở rộng `.class`.

Ví dụ này cho thấy lý do môi trường phát triển cần JDK: bạn cần `javac` để biên dịch. Khi đã có bytecode, máy chạy ứng dụng cần một runtime tương thích để thực thi.

## 10. Tương thích giữa phiên bản biên dịch và runtime

Một ứng dụng được biên dịch bằng JDK mới có thể sử dụng bytecode hoặc API mà runtime cũ không hỗ trợ. Khi chạy trên runtime quá cũ, chương trình có thể báo lỗi `UnsupportedClassVersionError`.

Với JDK 9 trở lên, tùy chọn `--release` giúp biên dịch theo phiên bản Java mục tiêu, đồng thời giới hạn API Java tiêu chuẩn phù hợp với phiên bản đó.

Ví dụ biên dịch chương trình cho Java 17:

```bash
javac --release 17 -d out Hello.java
java -cp out Hello
```

Trong đó:

- `--release 17` đặt phiên bản nền tảng mục tiêu là Java 17.
- `-d out` đặt thư mục chứa tệp `.class` đầu ra.
- `-cp out` thêm thư mục `out` vào classpath khi chạy.

Runtime dùng để chạy ứng dụng phải hỗ trợ phiên bản bytecode mục tiêu và các API mà chương trình sử dụng. Với dự án thực tế, cần thống nhất phiên bản JDK trong môi trường phát triển, build và triển khai.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `javac` không được nhận diện | Chưa cài JDK hoặc `PATH` chưa trỏ đến JDK | Cài JDK và kiểm tra thư mục `bin` trong `PATH` |
| `java` không được nhận diện | Chưa có runtime phù hợp hoặc `PATH` sai | Cài JDK/runtime phù hợp và cập nhật `PATH` |
| `UnsupportedClassVersionError` | Runtime cũ hơn phiên bản bytecode của ứng dụng | Nâng cấp runtime hoặc biên dịch lại với phiên bản mục tiêu phù hợp |
| Công cụ build không tìm thấy Java | `JAVA_HOME` sai hoặc trỏ đến phiên bản khác | Đặt `JAVA_HOME` về thư mục gốc của JDK cần dùng |
| `java` và `javac` báo hai phiên bản khác nhau | Máy có nhiều bản Java và thứ tự `PATH` không như mong đợi | Dùng `where.exe` hoặc `command -v` để kiểm tra đường dẫn thực tế |

Không nên xử lý lỗi bằng cách sao chép ngẫu nhiên tệp DLL, thư viện hoặc thư mục runtime giữa các bản Java. Hãy cài đặt hoặc cấu hình lại một bản phân phối Java đầy đủ và tương thích.

## 12. Ghi nhớ

- **JVM** là máy ảo thực thi bytecode Java.
- **JRE** là môi trường cung cấp JVM và các thành phần runtime để chạy ứng dụng.
- **JDK** là bộ công cụ phát triển, có trình biên dịch và các công cụ cần thiết để xây dựng ứng dụng Java.
- Khi học và phát triển Java, hãy cài JDK.
- Khi triển khai, chọn runtime tương thích với phiên bản Java và nhu cầu thực tế của ứng dụng.
- Cách đóng gói JRE thay đổi theo phiên bản và nhà cung cấp; không dùng sự tồn tại của thư mục `jre` làm tiêu chí duy nhất để nhận biết môi trường Java.
