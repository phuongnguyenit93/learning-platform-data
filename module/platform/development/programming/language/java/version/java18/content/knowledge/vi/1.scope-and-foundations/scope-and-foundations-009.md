# Phân loại kết quả quan sát theo bảo đảm API, đặc tính hệ điều hành và hành vi riêng của bản JDK

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Biết phân biệt kết quả nào được Java SE/JDK API bảo đảm, kết quả nào phụ thuộc hệ điều hành hoặc môi trường, kết quả nào thuộc implementation của vendor/bản JDK, và kết quả nào specification để ngỏ. Áp dụng cách phân loại này khi kiểm chứng UTF-8 mặc định, Simple Web Server, Javadoc snippet, resolver SPI, reflection và MethodHandle trên JDK hiện đại.

## 1. Kết quả quan sát không tự động là hợp đồng

Khi chạy một chương trình Java, ta nhìn thấy output, exception, thứ tự phần tử, thời gian thực thi hoặc một hành vi cụ thể. Nhưng việc một kết quả xuất hiện trên máy của mình **không có nghĩa mọi JDK và mọi hệ điều hành đều phải tạo ra kết quả đó**.

Ví dụ:

- `Charset.defaultCharset()` trả về `UTF-8` trên JDK hiện đại theo mặc định là hành vi được JEP 400 và API mô tả.
- `InetAddress.getAllByName("example.com")` trả về một danh sách IP cụ thể phụ thuộc DNS, mạng, resolver và thời điểm.
- `Method.invoke()` bọc exception của method đích trong `InvocationTargetException` là hợp đồng API.
- JDK 18 thay đổi triển khai core reflection bằng method handles là chi tiết triển khai của JDK; ứng dụng không được phụ thuộc vào lớp nội bộ hay đường đi tối ưu cụ thể.
- `jwebserver` là công cụ JDK được tài liệu hóa; sự hiện diện của nó phụ thuộc bộ JDK/runtime image đang dùng.

Nếu không phân loại, một bài học có thể vô tình biến output tình cờ thành expected output bắt buộc. Khi chạy trên vendor khác, JDK patch khác hoặc OS khác, test sẽ báo lỗi dù chương trình vẫn tuân thủ hợp đồng.

Mục tiêu của bài này là trả lời bốn câu hỏi trước khi viết assertion:

1. **Specification/API cam kết điều gì?**
2. **Điều gì phụ thuộc OS, locale, filesystem, DNS, mạng hoặc cấu hình?**
3. **Điều gì được tài liệu hóa riêng cho JDK/tool/vendor?**
4. **Điều gì không được đặc tả đủ để có thể so khớp chính xác?**

## 2. Các nhóm kết quả cần phân biệt

Các nhóm dưới đây là cách phân loại thực dụng để thiết kế ví dụ và test. Một quan sát có thể thuộc nhiều nhóm cùng lúc: API có thể bảo đảm cách trả kết quả, trong khi dữ liệu cụ thể do môi trường quyết định.

### 2.1. Hành vi được Java SE/API contract bảo đảm

Đây là hành vi được mô tả trong Java Language Specification, Java Virtual Machine Specification hoặc Java SE API Specification. Một implementation Java SE phù hợp phải đáp ứng hợp đồng đó.

Ví dụ:

- `String.strip()` loại bỏ khoảng trắng ở hai đầu theo định nghĩa của API.
- `Method.invoke()` ném `InvocationTargetException` khi method đích ném exception.
- `MethodHandle.invokeExact()` yêu cầu kiểu tại call site khớp chính xác method type của handle; mismatch có thể gây `WrongMethodTypeException`.
- `Files.readString(path, UTF_8)` giải mã dữ liệu bằng charset được chỉ định.
- `Charset.defaultCharset()` cung cấp default charset của JVM đang chạy.

Khi test một hợp đồng, hãy kiểm tra đúng điều được API cam kết: kiểu kết quả, exception, cause, trạng thái hoặc quy tắc chuyển đổi. Không mở rộng kết luận sang những thuộc tính API không cam kết, chẳng hạn thứ tự, hiệu năng hoặc chuỗi message đầy đủ.

### 2.2. Hành vi được tài liệu hóa riêng cho JDK hoặc công cụ JDK

Một số API và công cụ được JDK công bố nhưng không thuộc Java SE API portable. Chúng có tài liệu riêng và hữu ích khi dự án chủ động chọn JDK có thành phần đó.

Ví dụ:

- `jdk.httpserver` và các API `com.sun.net.httpserver`.
- Công cụ `jwebserver` được bổ sung Simple Web Server trong Java 18 qua JEP 408.
- `javadoc` và standard doclet hỗ trợ `{@snippet}` từ Java 18 qua JEP 413.
- Các tùy chọn command line của `jwebserver`, `javadoc`, `jlink` và `jdeps`.

Với nhóm này, hãy ghi rõ JDK/tool version và đọc tool specification hoặc JDK API docs. Không tuyên bố tính năng là một phần của mọi implementation Java SE nếu nó chỉ được JDK cụ thể cung cấp.

### 2.3. Hành vi phụ thuộc hệ điều hành và môi trường

Đây là kết quả chịu ảnh hưởng bởi cấu hình máy, OS, user permissions, locale, timezone, filesystem, DNS, network, terminal hoặc tài nguyên đang có.

Ví dụ:

- Địa chỉ IP của một hostname.
- Tên đường dẫn, separator, case sensitivity và quyền truy cập file.
- `System.lineSeparator()` và line ending trong file.
- Locale/timezone mặc định.
- Cổng TCP có đang bị tiến trình khác chiếm hay không.
- File có thể được tạo, đổi tên hoặc xóa hay không theo quyền của user.
- Encoding của terminal khi hiển thị output.

Một API có thể định nghĩa rõ cách yêu cầu hệ điều hành thực hiện thao tác, nhưng kết quả thực tế vẫn phụ thuộc trạng thái của OS. Ví dụ `Files.delete(path)` có hợp đồng exception, song việc xóa thành công còn phụ thuộc file tồn tại, quyền và lock của hệ thống.

### 2.4. Hành vi phụ thuộc implementation, vendor hoặc bản build JDK

Một số kết quả có thể thay đổi theo cách nhà cung cấp triển khai JVM, compiler, garbage collector, JIT, provider hoặc tool.

Ví dụ:

- Thời gian khởi động và thời gian chạy benchmark.
- Chiến lược tối ưu JIT, inline hoặc layout đối tượng.
- Chi tiết nội bộ của core reflection sau JEP 416.
- Cách trình bày stack trace, đường dẫn source hoặc thông điệp lỗi ngoài phần API bảo đảm.
- Build string, vendor name, patch number và một số lựa chọn cấu hình riêng của distribution.

Chỉ dựa vào một kết quả quan sát trên Temurin, Oracle JDK, Corretto hoặc một vendor khác không đủ để khẳng định mọi JDK phải có cùng chi tiết đó. Nếu vendor có tài liệu cam kết cụ thể, ghi rõ đó là cam kết của vendor/build tương ứng.

### 2.5. Hành vi không được đặc tả đủ hoặc có chủ ý để ngỏ

Specification đôi khi không quy định một thứ tự hoặc một giá trị duy nhất. Trong trường hợp này, nhiều kết quả có thể đều hợp lệ.

Ví dụ thường gặp:

- Thứ tự duyệt entry trong một số API filesystem không được bảo đảm.
- Thứ tự hoặc nội dung địa chỉ do resolver trả về có thể thay đổi theo DNS và môi trường.
- Giá trị thời gian, header HTTP như `Date` và thời gian thực thi thay đổi theo thời điểm.
- Thứ tự phát hiện provider không nên được giả định nếu hợp đồng không cam kết.

Không nên gọi chung mọi khác biệt là “undefined behavior”. Java specification thường có cách mô tả riêng như unspecified behavior, implementation-dependent behavior hoặc các giới hạn được nêu trong API. Khi tài liệu không cam kết thứ tự, hãy nói “thứ tự không được bảo đảm” thay vì tự gán một thuật ngữ mạnh hơn.

## 3. Phân loại theo hai trục thay vì chỉ gắn một nhãn

Một kết quả có thể vừa dựa trên hợp đồng API, vừa chịu tác động môi trường. Ví dụ `InetAddress.getAllByName()` có hợp đồng về việc trả về các địa chỉ phân giải được hoặc ném `UnknownHostException`, nhưng địa chỉ thực tế do resolver và DNS cung cấp.

Vì vậy, hãy ghi hai trục:

- **Nguồn bảo đảm:** Java SE contract, JDK documented contract, vendor documentation, hoặc không có cam kết chính xác.
- **Yếu tố quyết định giá trị:** đầu vào cố định, runtime option, OS, locale, DNS/network, filesystem, vendor/build hoặc thời gian.

Bảng ví dụ:

| Quan sát | Nguồn bảo đảm | Yếu tố quyết định giá trị cụ thể |
|---|---|---|
| `Method.invoke()` bọc exception target | Java SE API | Loại exception do method đích ném |
| `Charset.defaultCharset()` trên JDK 18+ mặc định là UTF-8 | JEP 400 và Java SE API | Runtime option/cấu hình tương thích |
| IP của `example.com` | Hợp đồng `InetAddress` | DNS, resolver, cache, mạng, thời điểm |
| `jwebserver` phục vụ GET/HEAD | JDK tool specification | JDK/tool có mặt, file fixture, port, OS |
| HTML do Javadoc tạo có snippet | JDK standard doclet | Phiên bản `javadoc`, doclet, nội dung source |
| Thứ tự file từ directory stream | Không có thứ tự tổng quát được bảo đảm | Filesystem, OS, trạng thái thư mục |
| Thời gian một method chạy | Không có hợp đồng thời gian cố định | CPU, JIT, GC, tải máy, runtime build |

Không dùng nhãn “OS-specific” để bỏ qua hợp đồng exception. Ví dụ `Files.readString()` có thể ném `IOException` theo API; lý do cụ thể như file permission hoặc filesystem state thuộc môi trường. Cả hai thông tin đều cần được ghi.

## 4. Tìm nguồn có thẩm quyền trước khi kết luận

Không phải nguồn nào cũng có cùng giá trị khi xác định một hành vi có được bảo đảm hay không.

### 4.1. Thứ tự nguồn nên tra cứu

| Nguồn | Dùng để xác định |
|---|---|
| Java Language Specification (JLS) | Cú pháp, ngữ nghĩa ngôn ngữ và quy tắc compile |
| Java Virtual Machine Specification (JVMS) | Class file, linking, loading và hành vi JVM được đặc tả |
| Java SE API Specification | Hợp đồng public của class, method, exception, thread safety và side effect |
| JDK API Specification | API/tool thuộc JDK như `jdk.httpserver` |
| JDK tool specification | Tùy chọn, input, output và giới hạn của `java`, `javadoc`, `jwebserver`, `jlink` |
| JEP | Bối cảnh, mục tiêu và thiết kế của thay đổi trong một release |
| Vendor documentation | Cam kết riêng của distribution hoặc tính năng vendor-specific |
| Source code/benchmark/blog | Hữu ích để hiểu implementation, nhưng không tự trở thành hợp đồng portable |

### 4.2. Đọc đúng phần trong tài liệu API

Khi kiểm tra một method, không chỉ nhìn phần mô tả ngắn. Tìm:

- **Parameters:** input nào hợp lệ, giá trị null có được phép không.
- **Returns:** kết quả và điều kiện trả về.
- **Throws:** loại exception và điều kiện ném.
- **Specified by / Overrides:** hợp đồng kế thừa từ interface hoặc superclass.
- **Since:** API xuất hiện từ release nào.
- **API Note:** thông tin giải thích hoặc khuyến nghị.
- **Implementation Requirements / Implementation Note:** yêu cầu hoặc ghi chú liên quan implementation.
- **Thread safety / synchronization:** nếu tài liệu có nêu.
- **Ordering:** có bảo đảm thứ tự hay không.

Đừng suy ra rằng một method luôn trả về cùng dữ liệu chỉ vì kiểu trả về không đổi. Contract có thể bảo đảm cấu trúc nhưng để giá trị cụ thể phụ thuộc môi trường.

### 4.3. JEP giải thích nguồn gốc, không thay toàn bộ API contract

JEP rất hữu ích để hiểu vì sao tính năng được thêm và vấn đề ban đầu. Tuy nhiên, khi viết test cho method hiện tại, hãy đối chiếu Javadoc của JDK đang sử dụng.

Ví dụ:

- JEP 400 giải thích UTF-8 trở thành default charset.
- API `Charset.defaultCharset()` là nơi kiểm tra hợp đồng API đang gọi.
- JEP 408 giải thích Simple Web Server được thêm vào Java 18.
- Tool specification `jwebserver` xác định tùy chọn và hành vi công cụ ở JDK cụ thể.
- JEP 416 giải thích core reflection được tái triển khai bằng method handles.
- API `Method.invoke()` vẫn là nơi xác định exception wrapper mà ứng dụng được phép dựa vào.

## 5. Ví dụ JEP 400: UTF-8 mặc định và giới hạn của kết luận

JEP 400 đặt UTF-8 làm default charset trên JDK 18 trở lên theo cấu hình mặc định. Đây là thay đổi quan trọng vì trước đó default charset thường chịu ảnh hưởng mạnh hơn từ môi trường.

Chương trình kiểm tra:

~~~java
import java.nio.charset.Charset;

public final class CharsetObservation {
    public static void main(String[] args) {
        System.out.println(Charset.defaultCharset().name());
    }
}
~~~

Compile và chạy bằng JDK hiện đại:

~~~shell
javac --release 18 -d out CharsetObservation.java
java -cp out CharsetObservation
~~~

Kết quả mong đợi trên JDK 18+ với cấu hình mặc định:

~~~text
UTF-8
~~~

### 5.1. Phân loại kết quả

| Thành phần | Phân loại | Cách ghi trong bài |
|---|---|---|
| API `Charset.defaultCharset()` trả charset mặc định của JVM | Java SE API contract | Có thể assert tên charset trả về |
| UTF-8 là default trên JDK 18+ theo mặc định | JEP 400 / hành vi platform | Ghi rõ runtime release và options |
| Compatibility mode hoặc cấu hình startup | Runtime configuration | Ghi JVM options khi chạy |
| Terminal hiển thị ký tự có dấu | OS/terminal/font | Không dùng làm bằng chứng duy nhất về charset JVM |

JEP 400 có chế độ tương thích cho phép chạy với default charset cũ thông qua cấu hình `file.encoding=COMPAT` ở các JDK hỗ trợ cơ chế đó. Nếu dùng cấu hình tương thích để tái hiện hệ thống cũ, ghi rõ option này trong hồ sơ. Không thay đổi `file.encoding` bằng `System.setProperty()` giữa lúc chương trình chạy rồi kỳ vọng default charset được khởi tạo lại.

### 5.2. Tách default charset khỏi encoding được chỉ định

Đối với file, hãy chỉ định encoding trong API nếu định dạng dữ liệu yêu cầu một encoding cố định:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ExplicitUtf8File {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("message.txt");
        Files.writeString(file, "Xin chào", StandardCharsets.UTF_8);

        String value = Files.readString(file, StandardCharsets.UTF_8);
        System.out.println(value);
    }
}
~~~

Kết quả `Xin chào` là output của fixture đã xác định. Việc round-trip thành công chứng minh code dùng UTF-8 explicit; nó không chứng minh terminal, console hoặc một API khác cũng dùng UTF-8 mặc định.

### 5.3. Những assertion nên tránh

Không nên:

- Assert terminal phải hiển thị Unicode giống hệt trên mọi môi trường.
- Dùng default charset để định dạng một file có hợp đồng yêu cầu UTF-8 rõ ràng.
- Suy ra compiler encoding từ `Charset.defaultCharset()`.
- Ghi “mọi API I/O đều dùng default charset”. Nhiều API nhận charset hoặc có quy tắc encoding riêng.

## 6. Ví dụ JEP 408: Simple Web Server là hành vi được tài liệu hóa của JDK

JEP 408 đưa Simple Web Server vào JDK 18. Công cụ `jwebserver` thuộc module `jdk.httpserver`; đây là công cụ JDK có tool specification riêng.

Tạo fixture:

~~~text
web-example/
└── public/
    └── index.html
~~~

Nội dung `public/index.html`:

~~~html
<!doctype html>
<html lang="vi">
  <meta charset="UTF-8">
  <body>Simple Web Server OK</body>
</html>
~~~

Từ thư mục `web-example/`, chạy:

~~~shell
jwebserver -b 127.0.0.1 -p 8000 -d public
~~~

Từ terminal khác:

~~~shell
curl -i http://127.0.0.1:8000/index.html
~~~

### 6.1. Phân loại kết quả

| Quan sát | Phân loại | Assertion phù hợp |
|---|---|---|
| `jwebserver` là công cụ của module `jdk.httpserver` | JDK documented tool/module | Xác minh module/tool có mặt |
| Công cụ phục vụ tệp tĩnh qua HTTP/1.1 và hỗ trợ GET/HEAD | JDK tool specification | Kiểm tra request method và response |
| File fixture tồn tại, request GET thành công | Hành vi công cụ + trạng thái filesystem | Assert status và nội dung file |
| Port 8000 đang bị chiếm | OS/process state | Ghi lỗi bind; không coi là lỗi API |
| Response có header `Date` | Giá trị thời gian | Không so khớp chính xác |
| Nội dung lỗi cho path không tồn tại | Công cụ/runtime version | Assert status nếu tool docs cam kết; tránh so khớp nguyên văn error page |

Dùng địa chỉ loopback `127.0.0.1` để kiểm thử cục bộ. Nếu bind address hoặc firewall khác, khả năng truy cập có thể thay đổi. Không dùng một test loopback để khẳng định máy khác trong mạng có thể truy cập server.

### 6.2. Không suy rộng thành web server production

Simple Web Server là công cụ phục vụ file tĩnh cho phát triển, thử nghiệm và gỡ lỗi. Tool specification mô tả phạm vi HTTP/1.1, GET và HEAD; nó không phải server production đầy đủ có HTTPS/HTTP/2, authentication, reverse proxy, application routing hoặc vận hành bảo mật tương đương nền tảng web chuyên dụng.

Khi bài học chỉ kiểm tra JEP 408, ghi rõ mục đích và giới hạn này. Đừng đánh giá công cụ theo các tính năng mà nó không hứa cung cấp.

## 7. Ví dụ JEP 413: Javadoc snippet được render, không tự động được chạy

JEP 413 bổ sung cú pháp snippet cho standard doclet của Javadoc. Ví dụ:

~~~java
/**
 * Chuẩn hóa chuỗi trước khi hiển thị.
 *
 * {@snippet lang="java" :
 *     String value = "  Java 18  ".strip();
 *     System.out.println(value); // Java 18
 * }
 */
public final class SnippetDoc {
    public static String normalize(String input) {
        return input.strip();
    }
}
~~~

Tạo tài liệu:

~~~shell
javadoc -encoding UTF-8 -d docs SnippetDoc.java
~~~

Kiểm tra HTML được sinh ra và xác nhận đoạn snippet hiển thị đúng.

### 7.1. Phân loại

- **Được tài liệu hóa:** standard doclet hiểu và render snippet theo Javadoc specification của JDK.
- **Phụ thuộc tool:** `javadoc` version và doclet thực sự được gọi.
- **Không được bảo đảm bởi snippet:** code snippet không tự động trở thành unit test hoặc được thực thi khi tạo tài liệu.
- **Có thể thay đổi:** cấu trúc HTML/CSS nội bộ, class name, markup và cách trình bày có thể khác giữa các phiên bản doclet.

Test phù hợp là kiểm tra snippet xuất hiện với nội dung mong muốn hoặc kiểm tra HTML semantic theo nhu cầu. Không nên snapshot toàn bộ HTML rồi coi mọi thay đổi markup là lỗi API. Nếu code cần compile và chạy, tạo source/test riêng và gọi compiler/test runner.

## 8. Ví dụ JEP 418: resolver API có hợp đồng, địa chỉ DNS phụ thuộc môi trường

JEP 418 giới thiệu SPI cho phép thay thế cơ chế phân giải địa chỉ của `InetAddress`. API `InetAddressResolverProvider` và `InetAddressResolver` nằm trong `java.base`.

Ví dụ kiểm tra phân giải tên thông thường:

~~~java
import java.net.InetAddress;

public final class ResolveHost {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: ResolveHost <hostname>");
            System.exit(2);
            return;
        }

        InetAddress[] addresses = InetAddress.getAllByName(args[0]);
        for (InetAddress address : addresses) {
            System.out.println(address.getHostAddress());
        }
    }
}
~~~

Compile và chạy:

~~~shell
javac --release 18 -d out ResolveHost.java
java -cp out ResolveHost example.com
~~~

### 8.1. Điều gì được bảo đảm và điều gì biến thiên?

- API thực hiện phân giải tên và trả về một mảng địa chỉ khi thành công.
- API có thể ném `UnknownHostException` khi không phân giải được tên.
- Địa chỉ IP cụ thể có thể thay đổi theo DNS, resolver, cache, mạng, IPv4/IPv6 và thời điểm.
- Số lượng và thứ tự địa chỉ không nên được đóng đinh trong test nếu API hoặc môi trường không cam kết.
- Kết quả khác nhau giữa máy offline và máy có mạng không tự chứng minh lỗi JDK.

Hồ sơ kiểm thử nên ghi hostname, JDK/runtime, OS, resolver/network context và exception nếu có. Nếu cần kiểm tra logic ứng dụng, dùng resolver/provider test double được kiểm soát thay vì phụ thuộc DNS Internet.

### 8.2. Kiểm tra custom provider riêng với DNS thông thường

Một lần gọi `InetAddress.getAllByName()` không chứng minh provider tùy biến đã được chọn. Để kiểm tra SPI:

1. Tạo provider triển khai đúng API `InetAddressResolverProvider`.
2. Đăng ký provider qua module `provides` hoặc service configuration phù hợp.
3. Đóng gói provider và dependency theo module path/classpath của thiết kế.
4. Khởi chạy JVM mới với cấu hình test được kiểm soát.
5. Dùng hostname thuộc fixture của provider.
6. Kiểm tra log hoặc dấu hiệu do provider tạo ra để xác nhận request đi qua implementation mong muốn.

Không assert thứ tự provider nếu tài liệu không bảo đảm thứ tự đó. Test nên kiểm soát các provider được đóng gói, thay vì phụ thuộc vào provider tình cờ có trên máy phát triển.

## 9. Ví dụ JEP 416: hợp đồng reflection khác với implementation nội bộ

JEP 416 thay đổi implementation core reflection trong JDK 18 bằng method handles. Điều này không thay đổi toàn bộ hợp đồng public của reflection.

Ví dụ method đích ném exception:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class ReflectionContract {
    public static void fail() {
        throw new IllegalStateException("target failed");
    }

    public static void main(String[] args) throws Exception {
        Method method = ReflectionContract.class.getMethod("fail");

        try {
            method.invoke(null);
        } catch (InvocationTargetException exception) {
            System.out.println(exception.getCause().getClass().getSimpleName());
            System.out.println(exception.getCause().getMessage());
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
IllegalStateException
target failed
~~~

Đây là phần contract có thể kiểm tra:

- `Method.invoke()` bọc exception từ method đích trong `InvocationTargetException`.
- Cause của wrapper là exception do method đích ném.
- Các lỗi khác như quyền truy cập hoặc argument không hợp lệ có thể được báo trực tiếp theo hợp đồng API.

Với MethodHandle:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class MethodHandleContract {
    public static void fail() {
        throw new IllegalStateException("target failed");
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
                MethodHandleContract.class,
                "fail",
                MethodType.methodType(void.class));

        try {
            handle.invokeExact();
        } catch (IllegalStateException exception) {
            System.out.println(exception.getClass().getSimpleName());
            System.out.println(exception.getMessage());
        }
    }
}
~~~

MethodHandle gọi method đích và exception từ target được truyền trực tiếp. Với `invokeExact()`, kiểu tại call site phải khớp chính xác method type; mismatch có thể gây `WrongMethodTypeException`.

### 9.1. Phân loại đúng khi quan sát reflection

| Quan sát | Phân loại | Có nên dựa vào không? |
|---|---|---|
| `Method.invoke()` bọc target exception | Java SE API contract | Có |
| Cause của `InvocationTargetException` là target exception | Java SE API contract | Có |
| `invokeExact()` kiểm tra method type chính xác | Java SE API contract | Có |
| JDK 18 dùng MethodHandle bên trong core reflection | JEP/implementation design | Dùng để hiểu lịch sử, không phụ thuộc nội bộ |
| Tên lớp reflection nội bộ, object layout, call path | Implementation detail | Không |
| Benchmark reflection nhanh/chậm hơn MethodHandle | Phụ thuộc JDK, CPU, warmup, workload | Chỉ dùng kết quả đo có điều kiện |

Không dùng reflection performance trên một JDK để tuyên bố tất cả JDK khác có cùng hiệu năng. Không dựa vào tên class nội bộ hoặc cờ triển khai cũ để tạo hành vi ứng dụng.

## 10. Những đặc tính OS thường bị nhầm thành bảo đảm Java

### 10.1. Đường dẫn và filesystem

Java cung cấp `Path`, `Files` và các API filesystem, nhưng các thuộc tính cụ thể vẫn có thể phụ thuộc filesystem/OS:

- Phân biệt chữ hoa/chữ thường trong tên file.
- Quyền đọc/ghi/thực thi.
- Symlink và cách resolve đường dẫn.
- File lock và hành vi khi file đang được tiến trình khác sử dụng.
- Metadata như owner, permissions và timestamps.
- Thứ tự duyệt thư mục.

Ví dụ `Files.list(directory)` cung cấp stream các entry trong thư mục, nhưng không nên mặc định thứ tự luôn alphabetically hoặc giống nhau giữa các lần chạy. Nếu ứng dụng cần thứ tự xác định, hãy sort rõ ràng:

~~~java
try (var entries = Files.list(Path.of("input"))) {
    entries.map(path -> path.getFileName().toString())
            .sorted()
            .forEach(System.out::println);
}
~~~

Ở đây thứ tự output sau `sorted()` là quyết định bởi logic ứng dụng. Không cần suy ra filesystem có thứ tự ổn định.

### 10.2. Path separator và line separator

Phân biệt:

- `File.separator`: separator trong một đường dẫn, ví dụ `/` hoặc `\`.
- `File.pathSeparator`: separator giữa nhiều phần tử trong classpath/module path, thường là `:` hoặc `;`.
- `System.lineSeparator()`: line separator của môi trường.

Không hard-code dấu `\` hoặc `:` nếu code cần chạy trên nhiều OS. Khi test output nhiều dòng, cân nhắc so sánh nội dung theo dòng hoặc dùng newline được xác định trong fixture thay vì giả định line ending giống nhau.

### 10.3. Locale và timezone

Locale mặc định và timezone mặc định là thuộc tính môi trường/runtime. Cùng một ngày có thể được định dạng khác nhau theo locale; cùng một instant có thể hiển thị giờ địa phương khác nhau theo timezone.

Nếu output cần ổn định:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class StableFormatting {
    public static void main(String[] args) {
        var formatter = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        System.out.println(formatter.format(Instant.parse(
                "2026-11-27T00:00:00Z")));
    }
}
~~~

Việc chỉ định locale và timezone làm rõ điều kiện format. Nếu muốn kiểm tra timezone mặc định của máy, hãy ghi nhận nó như dữ liệu môi trường thay vì biến thành expected value chung cho mọi hệ thống.

### 10.4. DNS, socket và port

Các API mạng có contract về loại thao tác và exception, nhưng thành công còn phụ thuộc:

- DNS resolver và cache.
- Route, firewall, proxy và VPN.
- IPv4/IPv6 availability.
- Port có đang được sử dụng.
- Bind address và interface có tồn tại.
- Quyền hoặc policy của môi trường.

Khi test server, dùng loopback và port được kiểm soát. Khi test DNS, tránh assert một IP Internet cố định. Khi test lỗi bind, cố tình chiếm port trong fixture và kiểm tra loại lỗi theo API/tool contract, không phụ thuộc message đầy đủ.

## 11. Không biến chi tiết của một bản JDK thành hợp đồng ứng dụng

Một ứng dụng có thể quan sát được nhiều chi tiết từ runtime, nhưng không phải chi tiết nào cũng là API được bảo đảm.

### 11.1. Các chi tiết không nên dùng làm assertion portable

- Tên class implementation nội bộ.
- Cấu trúc stack trace đầy đủ.
- Thời gian chạy chính xác hoặc số lần JIT compile.
- Thứ tự GC, thời điểm GC hoặc số byte heap tại một thời điểm tùy ý.
- Layout bộ nhớ của object.
- Tên thread nội bộ hoặc thứ tự scheduling không được cam kết.
- Nội dung error message không được API đặc tả.
- Thứ tự provider hoặc địa chỉ DNS khi không có cam kết.
- Markup/CSS chi tiết của HTML do Javadoc tạo.

Nếu cần theo dõi các giá trị này để chẩn đoán, ghi chúng trong phần **Observed diagnostics** và ghi rõ vendor/version. Không dùng chúng làm điều kiện pass/fail chung trừ khi sản phẩm có một cam kết cụ thể với môi trường được kiểm soát.

### 11.2. Đừng nhầm implementation-specific với JDK API documented

Một API thuộc `jdk.httpserver` là JDK-specific nhưng có tài liệu công khai. Ứng dụng chủ động phụ thuộc nó có thể dựa trên tài liệu tương ứng của JDK mục tiêu.

Ngược lại, một class nội bộ trong package implementation không trở thành public API chỉ vì có thể import bằng reflection hoặc tìm thấy trong source. Không sử dụng internal API hoặc cờ legacy đã bị loại bỏ làm nền tảng cho ví dụ mới.

### 11.3. Vendor và patch level là dữ liệu cần ghi

Hai runtime cùng major version có thể khác vendor hoặc patch. Khi điều tra khác biệt, thu thập:

~~~shell
java --version
javac --version
java -XshowSettings:properties -version
~~~

Trong chương trình, có thể ghi:

~~~java
System.out.println(System.getProperty("java.vendor"));
System.out.println(System.getProperty("java.runtime.version"));
System.out.println(System.getProperty("java.home"));
~~~

Đối với công cụ, ghi riêng `javadoc --version` và `jwebserver --version`. Không suy ra version của tool từ `java --version` nếu PATH có thể trỏ đến các JDK khác nhau.

## 12. Quy tắc thiết kế assertion theo loại kết quả

### 12.1. Assertion chính xác

Dùng khi đầu vào và hợp đồng xác định duy nhất kết quả:

- Chuỗi đã normalize từ input cố định.
- Byte output khi dùng charset explicit.
- Exception wrapper/cause theo API.
- Class file major version khi compile với release cụ thể.
- HTTP status và body của fixture local theo tool contract.

### 12.2. Assertion theo điều kiện hoặc thuộc tính

Dùng khi giá trị cụ thể biến thiên nhưng có một điều kiện hợp đồng cần thỏa:

- DNS thành công: mảng địa chỉ không rỗng, nếu môi trường test cam kết hostname phân giải được.
- `Charset.defaultCharset()` là UTF-8 trên JDK 18+ trong cấu hình mặc định; nếu bật compatibility option, kiểm tra theo cấu hình đó.
- File có thể đọc được: kiểm tra nội dung và encoding đã chỉ định, không assert metadata OS không liên quan.
- Javadoc snippet: kiểm tra code text/semantic element xuất hiện, không snapshot toàn bộ HTML.
- Module cần thiết: kiểm tra `jdk.httpserver` có trong runtime image và lệnh khởi chạy hoạt động.

### 12.3. Chỉ ghi nhận, không dùng làm pass/fail

Dùng cho thông tin chẩn đoán hoặc kết quả không được cam kết ổn định:

- IP cụ thể từ DNS Internet.
- Header thời gian.
- Thời gian chạy benchmark.
- Stack trace đầy đủ.
- Đường dẫn cài JDK của một máy cá nhân.
- Tên implementation nội bộ.
- Thứ tự duyệt file nếu API không quy định.

### 12.4. Negative test cần xác định trigger và exception

Khi kiểm tra lỗi, hãy ghi:

1. Input gây lỗi.
2. Điều kiện môi trường cần có.
3. Thời điểm lỗi phát sinh: compile, class loading, lookup, invocation, I/O hoặc network.
4. Exception type.
5. Cause/wrapper nếu có.
6. Exit code nếu tiến trình kết thúc.
7. Phần nào trong message được bảo đảm và phần nào chỉ để chẩn đoán.

Ví dụ `Method.invoke()` và `MethodHandle.invokeExact()` cùng gọi một method ném `IllegalStateException`, nhưng cách exception được quan sát khác nhau theo hợp đồng. Đó là khác biệt đáng assert. Stack trace line number không phải.

## 13. Mẫu bảng phân loại một quan sát

Dùng bảng sau khi viết bài học hoặc báo cáo bug:

~~~text
Observation ID:
Observed behavior:
Input / fixture:
Command:
Working directory:

Guarantee source:
[ ] Java SE API / JLS / JVMS
[ ] JDK API / JDK tool specification
[ ] Vendor documentation
[ ] No exact guarantee found

Value dependencies:
[ ] Fixed input
[ ] Runtime option / JVM configuration
[ ] OS / filesystem / permissions
[ ] Locale / timezone / terminal
[ ] DNS / network / external service
[ ] JDK vendor / patch / implementation
[ ] Time / scheduling / resource pressure

Expected behavior:
Exact assertion:
Conditional assertion:
Diagnostic only:

Exception:
Cause / wrapper:
Exit code:

Environment:
JDK vendor:
java.runtime.version:
java.home:
Compiler version:
Tool version:
OS / architecture:
Locale / timezone:
Charset:
Relevant modules:

Conclusion:
What is guaranteed:
What may vary:
What is not asserted:
~~~

Một dòng có thể được đánh dấu ở nhiều nhóm. Ví dụ DNS có thể là Java SE API contract về loại kết quả/exception, đồng thời là network-dependent về IP cụ thể.

## 14. Ví dụ phân loại nhanh cho các chủ đề Java 18

| Chủ đề | Phần được bảo đảm hoặc tài liệu hóa | Phần phụ thuộc môi trường/implementation | Cách kiểm tra đúng |
|---|---|---|---|
| JEP 400 — UTF-8 default | Default charset UTF-8 trên JDK 18+ theo mặc định; API trả default charset | Compatibility option, terminal, encoding file ngoài | In `Charset.defaultCharset()`, ghi runtime options, test explicit UTF-8 riêng |
| JEP 408 — Simple Web Server | JDK tool spec mô tả HTTP/1.1, GET/HEAD, bind và directory options | Port, file permissions, network, headers thời gian | Dùng fixture loopback, assert status/body và ghi tool version |
| JEP 413 — Javadoc snippet | Standard doclet xử lý `{@snippet}` | HTML markup/CSS, custom doclet, tool version | Kiểm tra snippet semantic; compile/run code riêng |
| JEP 418 — Resolver SPI | API provider/resolver và contract của `InetAddress` | DNS, resolver, IP, cache, provider deployment | Test provider riêng với JVM mới; không assert IP Internet cố định |
| JEP 416 — Reflection | `Method.invoke` wrapper/cause; MethodHandle invocation contract | Core reflection implementation và hiệu năng | Assert exception type/cause, không assert internal class hoặc benchmark cố định |

Bảng này không nói rằng mọi kết quả của một chủ đề chỉ thuộc một nhóm. Nó chỉ ra nơi nên tìm hợp đồng và những yếu tố thường làm giá trị quan sát thay đổi.

## 15. Quy trình phân loại khi gặp kết quả khác nhau giữa hai máy

Khi một ví dụ chạy khác giữa máy phát triển và CI/production, tiến hành theo thứ tự:

1. **Chụp đầu vào:** xác nhận source, fixture, arguments, request và working directory giống nhau.
2. **Ghi môi trường:** OS, architecture, locale, timezone, charset, DNS/network và permissions.
3. **Ghi toolchain:** `java`, `javac`, `javadoc`, `jwebserver`, vendor, runtime version và `java.home`.
4. **Tìm contract:** tra JLS/JVMS/API docs/tool spec cho đúng method hoặc command.
5. **Tách phần bảo đảm:** ghi điều kiện, return type, exception, status hoặc output mà tài liệu cam kết.
6. **Tách phần biến thiên:** IP, ordering không bảo đảm, header thời gian, filesystem metadata, performance.
7. **Tạo test tối thiểu:** loại bỏ network/filesystem nếu chúng không phải đối tượng cần kiểm tra.
8. **Chạy trên ma trận:** OS/JDK/vendor mà dự án thực sự hỗ trợ.
9. **Kết luận có phạm vi:** nêu khác biệt vi phạm contract hay chỉ là một kết quả hợp lệ khác.

Không đổi expected output để khớp một máy duy nhất trước khi xác định nguồn bảo đảm. Một test portable phải phản ánh contract và điều kiện đầu vào đã công bố.

## 16. Bài tập thực hành

### Bài 1 — Phân loại default charset

Chạy `Charset.defaultCharset()` trên JDK hiện đại. Ghi runtime version, vendor và JVM options. Thử một cấu hình compatibility nếu JDK hỗ trợ.

**Tiêu chí đạt:** Phân biệt default charset theo JEP 400 với encoding của source file, file dữ liệu và terminal.

### Bài 2 — Phân loại kết quả DNS

Chạy `InetAddress.getAllByName()` với một hostname được phép. Chạy lại trên môi trường mạng khác hoặc resolver test được kiểm soát.

**Tiêu chí đạt:** Chỉ ra API contract về loại kết quả/exception và yếu tố môi trường quyết định IP; không đóng đinh địa chỉ hoặc thứ tự.

### Bài 3 — Phân loại reflection và MethodHandle

Gọi cùng method target ném exception qua `Method.invoke()` và `MethodHandle.invokeExact()`.

**Tiêu chí đạt:** Assert wrapper/cause và exception trực tiếp theo contract; không dựa vào implementation nội bộ của JEP 416.

### Bài 4 — Phân loại Javadoc snippet

Tạo Javadoc với `{@snippet}` trên JDK được hỗ trợ. So sánh HTML giữa hai patch/tool version.

**Tiêu chí đạt:** Xác nhận snippet được render nhưng không khẳng định code đã chạy; tránh snapshot markup không ổn định.

### Bài 5 — Phân loại Simple Web Server

Chạy `jwebserver` trên loopback với file fixture. Thử port bị chiếm và file không tồn tại.

**Tiêu chí đạt:** Tách hành vi được tool spec tài liệu hóa khỏi port/process/filesystem state; chỉ assert những thuộc tính ổn định.

### Bài 6 — Viết kết luận cho một bug report

Chọn một kết quả khác giữa Windows và Linux. Viết kết luận gồm: contract liên quan, đặc tính OS, môi trường, output ổn định cần test và output không nên assert.

**Tiêu chí đạt:** Kết luận có bằng chứng và phạm vi rõ; không gọi một khác biệt hợp lệ là lỗi JDK.

## 17. Checklist trước khi công bố kết quả quan sát

- [ ] Đã tìm đúng Java SE/JDK API hoặc tool specification.
- [ ] Đã phân biệt API contract với JEP/history và implementation detail.
- [ ] Đã ghi JDK vendor, runtime version, patch và tool version liên quan.
- [ ] Đã ghi OS, architecture, locale, timezone và charset nếu ảnh hưởng.
- [ ] Đã ghi DNS/network/filesystem/permissions nếu ví dụ dùng chúng.
- [ ] Đã cố định input, fixture, command và working directory.
- [ ] Expected output chỉ assert phần specification bảo đảm.
- [ ] Không assert IP, thời gian, stack trace hoặc thứ tự không được bảo đảm.
- [ ] Exception được mô tả bằng type, cause/wrapper và trigger.
- [ ] Đã tách JDK-specific API/tool khỏi Java SE portable API.
- [ ] Không phụ thuộc internal API, cờ triển khai cũ hoặc chi tiết legacy.
- [ ] Đã kiểm thử trên JDK hiện đại còn được nhà cung cấp hỗ trợ.

## 18. Tài liệu chính thức

1. [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/): hợp đồng API Java SE và package/module.
2. [Java Language Specification — Java SE 27](https://docs.oracle.com/javase/specs/jls/se27/html/index.html): quy tắc ngôn ngữ và các hành vi được đặc tả.
3. [Java Virtual Machine Specification — Java SE 27](https://docs.oracle.com/javase/specs/jvms/se27/html/index.html): class file, loading, linking và JVM behavior.
4. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset và chế độ tương thích.
5. [The Charset API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): hợp đồng `defaultCharset()`.
6. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu và phạm vi Simple Web Server.
7. [The jwebserver Tool — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): các tùy chọn và hành vi được tài liệu hóa của công cụ.
8. [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): snippet trong standard doclet.
9. [Javadoc Documentation Comment Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html): cú pháp và xử lý documentation comment.
10. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): resolver provider SPI.
11. [The InetAddressResolverProvider API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): hợp đồng provider.
12. [The Method API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): `invoke()` và `InvocationTargetException`.
13. [The MethodHandle API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact()` và method type.
14. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi implementation core reflection trong JDK 18.

**Kết quả cần đạt:** Khi một ví dụ cho ra kết quả khác giữa hai máy hoặc hai bản JDK, bạn có thể chỉ ra phần nào là hợp đồng API, phần nào phụ thuộc OS/môi trường, phần nào là hành vi được tài liệu hóa riêng của JDK và phần nào không có bảo đảm chính xác. Từ đó viết expected output và assertion đúng phạm vi, giúp bài học Java 18 tiếp tục có giá trị trên JDK hiện đại.
