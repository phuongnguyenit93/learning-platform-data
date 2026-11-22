# Những năng lực Java 11 tiếp tục được dùng trong Java hiện đại

**Chủ đề:** Java 11 · **Nhánh:** Định hướng  
**Trọng tâm:** Chọn những kiến thức, API và công cụ có giá trị trong dự án Java ngày nay; hiểu cách dùng đúng và giới hạn của chúng.

Java 11 là một mốc quan trọng của hệ sinh thái Java. Nhiều khả năng có mặt trên JDK 11 vẫn là nền tảng khi phát triển, kiểm thử và vận hành ứng dụng trên các JDK mới hơn. Bài này **không yêu cầu chọn Java 11 làm phiên bản triển khai cho dự án mới**: phiên bản chạy thực tế phải theo chính sách hỗ trợ, bảo mật và yêu cầu thư viện của dự án. Khi nói “năng lực Java 11”, cần phân biệt **tính năng ra đời ở Java 11** với **tính năng từ Java 9/10 nhưng đã có trong Java 11 và vẫn được sử dụng**.

## 1. Sau bài này cần làm được gì?

1. Viết mã Java rõ nghĩa bằng suy luận kiểu cục bộ, lambda, Stream, `Optional` và collection không thể sửa cấu trúc.
2. Xử lý văn bản và tệp UTF-8 bằng API chuẩn hiện đại của JDK.
3. Gọi HTTP/HTTPS với `java.net.http.HttpClient`, hiểu request, response, timeout, status và bất đồng bộ.
4. Dùng `javac --release`, chạy trực tiếp tệp `.java` cho chương trình nhỏ, phân biệt classpath với module path.
5. Biết khi nào dùng Java Flight Recorder (JFR), TLS hiện đại, JVM có nhận thức môi trường container; tránh phỏng đoán khi điều chỉnh hiệu năng.
6. Đánh giá mã nguồn viết được trên JDK 11 còn phù hợp với các bản Java mới hơn hay không, dựa trên hành vi API, kiểm thử và yêu cầu thực tế.

## 2. Bản đồ năng lực vẫn còn giá trị

| Năng lực | Có từ | Tình huống dùng hiện nay | Điều cần nhớ |
|---|---|---|---|
| `var` trong biến cục bộ; `var` ở tham số lambda | Java 10; Java 11 | Rút bớt kiểu dài khi kiểu suy ra rõ ràng | Java vẫn kiểm tra kiểu tĩnh; `var` không phải `dynamic` |
| `String.isBlank`, `strip`, `lines`, `repeat` | Java 11 | Chuẩn hóa dữ liệu nhập, text, log, import | Ý nghĩa whitespace và đầu vào `null` cần xem xét |
| `Path.of`, `Files.readString`, `Files.writeString` | Java 11 | Đọc/ghi tệp cấu hình, dữ liệu văn bản nhỏ, script | Chọn charset và quy mô dữ liệu phù hợp |
| `HttpClient` trong `java.net.http` | Java 11 (API chuẩn) | REST, tích hợp dịch vụ, request HTTP/2 khi được hỗ trợ | Timeout, trạng thái HTTP và xử lý lỗi là bắt buộc |
| `Predicate.not`, `Optional.isEmpty`, `Collection.toArray(IntFunction)` | Java 11 | Pipeline Stream và diễn đạt điều kiện rõ hơn | Không lạm dụng `Optional` hoặc Stream |
| `List.of` / `Set.of` / `Map.of`; `copyOf` | Java 9; Java 10 | Dữ liệu cấu hình và snapshot danh sách | Không sửa được cấu trúc; không phải bất biến sâu |
| JPMS / `module-info.java` | Java 9 | Đóng gói theo module khi kiến trúc yêu cầu | Không ép mọi dự án phải modular hóa |
| Source-file launcher `java Demo.java` | Java 11 | Ví dụ nhỏ, công cụ nội bộ, thử nghiệm nhanh | Dự án lớn vẫn cần build và kiểm thử đầy đủ |
| Java Flight Recorder và công cụ JDK | Có sẵn trên JDK 11 và các bản mới | Điều tra CPU, allocation, GC, độ trễ | Thu thập dữ kiện trước khi tối ưu |

Cột “Có từ” rất quan trọng: `List.of` không phải tính năng **được giới thiệu** ở Java 11, nhưng vẫn là một năng lực hữu ích mà lập trình viên dùng khi làm việc với Java 11 và các JDK mới.

## 3. Viết Java dễ đọc với `var` và lambda

`var` cho phép trình biên dịch suy luận kiểu biến cục bộ từ biểu thức khởi tạo. Kiểu được quyết định **ngay lúc biên dịch**, không thể tự đổi giữa các lần gán. Từ Java 11, có thể viết `var` cho tham số lambda khi muốn khai báo kiểu nhất quán hoặc dùng annotation trên tham số.

**Ví dụ chạy độc lập — `TypeInferenceDemo.java`:**

```java
import java.util.List;
import java.util.function.BiFunction;

public class TypeInferenceDemo {
    public static void main(String[] args) {
        var labels = List.of("Java", "HTTP"); // suy ra List<String>
        BiFunction<String, String, String> join =
                (var first, var second) -> first + " / " + second;

        System.out.println(labels.get(0));
        System.out.println(join.apply("read", "write"));
    }
}
```

Chạy bằng JDK 11 trở lên:

```bash
javac --release 11 TypeInferenceDemo.java
java TypeInferenceDemo
```

Kết quả:

```text
Java
read / write
```

**Quy tắc áp dụng:**

- Ưu tiên `var` khi vế phải làm kiểu dữ liệu rõ ràng, chẳng hạn `var client = HttpClient.newHttpClient();`. Dùng kiểu tường minh khi nó giúp người đọc hiểu hợp đồng dữ liệu hơn.
- Không dùng `var` cho field, tham số phương thức thông thường hay kiểu trả về; `var x = null;` không đủ thông tin để suy luận kiểu.
- Với lambda, nếu một tham số dùng `var` thì tất cả tham số lambda phải cùng kiểu khai báo `var`; không trộn với cú pháp suy luận ngầm hoặc kiểu tường minh.
- `var` không làm mã tự động ngắn gọn hơn về ý nghĩa. Ví dụ `var result = process(input);` có thể khó hiểu nếu tên phương thức và kiểu kết quả mơ hồ.

## 4. Xử lý chuỗi: dữ liệu người dùng, dòng văn bản và khoảng trắng

Các phương thức của `String` bổ sung ở Java 11 giảm mã tự viết khi làm sạch đầu vào:

- `isBlank()`: chuỗi rỗng hoặc chỉ chứa whitespace theo `Character.isWhitespace`.
- `strip()`, `stripLeading()`, `stripTrailing()`: loại whitespace ở hai đầu, đầu hoặc cuối theo định nghĩa trên.
- `lines()`: tạo `Stream<String>` từ các dòng; hỗ trợ `\n`, `\r` và `\r\n`, không giữ ký tự kết thúc dòng.
- `repeat(n)`: lặp nội dung chuỗi `n` lần; `n` âm là không hợp lệ.

**Ví dụ chạy độc lập — `StringDemo.java`:**

```java
public class StringDemo {
    public static void main(String[] args) {
        System.out.println("[" + "  Java 11 \n".strip() + "]");
        System.out.println("\t \n".isBlank());
        System.out.println("A\n\nB".lines().count());
        System.out.println("Go".repeat(2));
    }
}
```

```bash
javac --release 11 StringDemo.java
java StringDemo
```

```text
[Java 11]
true
3
GoGo
```

`strip()` thường phù hợp hơn `trim()` khi cần xử lý khoảng trắng Unicode: `trim()` có quy tắc cũ dựa trên mã ký tự đến U+0020, còn `strip()` dựa trên `Character.isWhitespace`. Tuy vậy, `strip()` **không có nghĩa là loại mọi ký tự trông giống khoảng trắng trong Unicode**; cần xác định chính sách làm sạch nếu dữ liệu có ký tự đặc biệt. Một chuỗi `null` không thể gọi `isBlank()` hay `strip()` trực tiếp. `isBlank()` cũng không thay thế kiểm tra tính hợp lệ nghiệp vụ, chẳng hạn định dạng email.

`lines()` phù hợp khi nội dung đã nằm trong bộ nhớ. Nó không tự đọc tệp và không trả thêm một dòng rỗng chỉ vì chuỗi kết thúc bằng ký tự xuống dòng.

## 5. Đọc/ghi tệp bằng `Path` và `Files`

`Path.of(...)` tạo đường dẫn theo hệ tệp; `Files.readString(...)` và `Files.writeString(...)` giúp thao tác với tệp văn bản nhỏ mà không cần tự dựng reader/writer. Hai phương thức một tham số dùng UTF-8; trong mã liên quan dữ liệu bên ngoài, việc ghi rõ `StandardCharsets.UTF_8` giúp hợp đồng dễ nhận biết.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTextDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("java11-text-", ".txt");
        try {
            Files.writeString(file, "Một dòng\nHai dòng\n",
                    StandardCharsets.UTF_8);
            String text = Files.readString(file, StandardCharsets.UTF_8);
            System.out.println(text.lines().count());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 11 FileTextDemo.java
java FileTextDemo
```

```text
2
```

Ví dụ tạo tệp tạm, đọc rồi dọn trong `finally`. Trong ứng dụng thật, các lỗi I/O cần được xử lý theo ngữ cảnh và không nên che nguyên nhân của lỗi chính bằng lỗi dọn dẹp.

**Phân biệt đường đi xử lý:**

- Tệp văn bản nhỏ: `Files.readString(path, charset)` / `Files.writeString(path, text, charset)`.
- Tệp lớn: đọc theo dòng hoặc luồng để không nạp toàn bộ nội dung vào RAM. `Files.lines(...)` trả về stream có tài nguyên I/O, cần `try-with-resources`.
- Đường dẫn lấy từ người dùng: phải giới hạn đường dẫn trong thư mục được phép, phân quyền và kiểm soát tên tệp; `Path.normalize()` một mình không giải quyết mọi trường hợp đi xuyên thư mục hoặc liên kết tượng trưng.
- `Files.writeString` không truyền tùy chọn sẽ tạo tệp mới hoặc ghi đè nội dung tệp có sẵn. Muốn nối thêm cần chọn `StandardOpenOption.APPEND` một cách có chủ đích.

Ví dụ cho trường hợp tệp lớn, khi `path` đã là một `Path` hợp lệ:

```java
try (var rows = Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = rows.map(String::strip)
            .filter(Predicate.not(String::isBlank))
            .count();
    System.out.println(nonBlank);
}
```

Đoạn trên là **trích đoạn trong một phương thức**, cần import `Files`, `StandardCharsets`, `Predicate` và khai báo `path`; không phải chương trình độc lập.

## 6. HTTP/HTTPS bằng `java.net.http.HttpClient`

`HttpClient` được chuẩn hóa trong Java 11 và tiếp tục hữu ích khi gọi dịch vụ HTTP mà không cần phụ thuộc HTTP client bên thứ ba cho yêu cầu cơ bản. Nó hỗ trợ gửi đồng bộ bằng `send(...)` và gửi bất đồng bộ bằng `sendAsync(...)` trả `CompletableFuture`. Client nên được **tái sử dụng** để tận dụng việc quản lý kết nối; request mô tả riêng URL, method, headers, body và thời hạn chờ.

**Ví dụ chạy độc lập khi máy có kết nối HTTPS — `HttpExample.java`:**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "text/html")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("Response chars: " + response.body().length());
    }
}
```

```bash
javac --release 11 HttpExample.java
java HttpExample
```

Kết quả phụ thuộc mạng, chứng chỉ, máy chủ và thời điểm chạy; **không giả định status hoặc số ký tự cố định**. Trong dịch vụ thật, cần diễn giải status (`2xx`, `4xx`, `5xx`) đúng nghĩa nghiệp vụ và tránh vô tình ghi log dữ liệu nhạy cảm.

**Đồng bộ và bất đồng bộ:** `send` chặn luồng gọi cho tới khi có phản hồi hoặc lỗi. `sendAsync` trả ngay một `CompletableFuture` để kết hợp bước sau. Ví dụ dưới đây là **trích đoạn**, sử dụng `client` và `request` đã tạo ở chương trình trên:

```java
var result = client.sendAsync(
        request, HttpResponse.BodyHandlers.discarding());

result.thenApply(HttpResponse::statusCode)
        .thenAccept(code -> System.out.println("Status: " + code))
        .join(); // chỉ để chương trình demo đợi kết quả
```

Trong server, nên kết hợp các future theo luồng nghiệp vụ thay vì gọi `join()` ngay sau mọi request. Chọn `BodyHandlers.ofFile(...)` hoặc xử lý stream nếu phản hồi lớn; `ofString` sẽ giữ toàn bộ body dưới dạng chuỗi.

**Nguyên tắc sử dụng còn đúng:**

1. Ưu tiên HTTPS, giữ xác minh chứng chỉ và hostname theo mặc định; không tắt kiểm tra TLS để “sửa” lỗi kết nối.
2. `connectTimeout` dành cho thiết lập kết nối; `HttpRequest.Builder.timeout` giới hạn thời gian của request. Đặt giá trị theo SLA, có retry/backoff khi phù hợp và nhớ rằng retry thao tác ghi phải xét tính idempotent.
3. Không nhầm “request hoàn thành” với “request thành công”: response HTTP 404/500 vẫn là một `HttpResponse` có mã trạng thái.
4. JDK hỗ trợ HTTP/2, nhưng giao thức thực tế phụ thuộc quá trình đàm phán với server/proxy; không mặc định mọi lần gọi đều dùng HTTP/2.
5. Xử lý `IOException`, `InterruptedException` và lỗi tương lai bất đồng bộ. Nếu bắt `InterruptedException` trong tầng ứng dụng, thường phải khôi phục interrupt flag hoặc truyền tiếp theo hợp đồng.

## 7. Collections và pipeline dữ liệu rõ ràng

`List.of`, `Set.of`, `Map.of` có từ Java 9; `List.copyOf`, `Set.copyOf`, `Map.copyOf` có từ Java 10. Chúng hiện diện trên JDK 11 và vẫn là lựa chọn tốt cho tập giá trị cố định, cấu hình hoặc snapshot dữ liệu đưa qua các tầng ứng dụng.

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionDemo {
    public static void main(String[] args) {
        var mutable = new ArrayList<>(List.of("Java", "HTTP"));
        List<String> snapshot = List.copyOf(mutable);
        mutable.add("Files");

        System.out.println(snapshot);
        System.out.println(mutable);
    }
}
```

```bash
javac --release 11 CollectionDemo.java
java CollectionDemo
```

```text
[Java, HTTP]
[Java, HTTP, Files]
```

`copyOf` tạo danh sách không thể sửa cấu trúc; sửa `mutable` sau đó không làm danh sách `snapshot` đổi thành phần. Tuy nhiên, nếu phần tử là object **có thể thay đổi trạng thái**, nội dung bên trong object vẫn có thể đổi. Đây là **bất biến nông**, không phải sao chép sâu. Các factory/copy này không chấp nhận phần tử `null`; `Set.of` không chấp nhận phần tử trùng và `Map.of` không chấp nhận khóa trùng.

**Những cải tiến nhỏ ở Java 11 đáng dùng:**

- `Predicate.not(String::isBlank)` đọc tự nhiên trong `filter(...)` khi loại dòng rỗng.
- `Optional.isEmpty()` diễn đạt rõ nhánh “không có kết quả”. `Optional` phù hợp nhất làm kiểu trả về biểu thị kết quả có thể vắng mặt; đừng để bản thân biến `Optional` là `null`.
- `collection.toArray(String[]::new)` tạo mảng đúng kiểu từ collection (quá tải nhận `IntFunction`, có từ Java 11).

**Ví dụ chạy độc lập — `FunctionalDemo.java`:**

```java
import java.util.List;
import java.util.Optional;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class FunctionalDemo {
    public static void main(String[] args) {
        List<String> cleaned = List.of("  ", " Java ", "\t", "HTTP")
                .stream()
                .map(String::strip)
                .filter(Predicate.not(String::isBlank))
                .collect(Collectors.toList());

        Optional<String> first = cleaned.stream().findFirst();
        String[] array = cleaned.toArray(String[]::new);

        System.out.println(cleaned);
        System.out.println("Empty? " + first.isEmpty());
        System.out.println("Length: " + array.length);
    }
}
```

```bash
javac --release 11 FunctionalDemo.java
java FunctionalDemo
```

```text
[Java, HTTP]
Empty? false
Length: 2
```

Đừng dùng `Optional.get()` mà không xử lý trường hợp rỗng; dùng `orElse(...)`, `orElseGet(...)`, `orElseThrow(...)` hoặc `ifPresent(...)` theo yêu cầu nghiệp vụ. `Collectors.toList()` trong Java 11 **không cam kết** kiểu cụ thể hay khả năng thay đổi của danh sách trả về; khi cần bảo đảm không sửa được, dùng `List.copyOf(...)` hoặc collector phù hợp. Không xây pipeline Stream quá dài nếu các bước xử lý vòng lặp thông thường dễ đọc, debug và tối ưu hơn.

## 8. Công cụ build, chạy và quan sát còn hữu ích

### 8.1 Chạy tệp nguồn đơn lẻ và thử nhanh

Java 11 cho phép chạy trực tiếp chương trình đơn giản trong một tệp nguồn:

```bash
java StringDemo.java
```

Lệnh trên dùng source-file mode: JVM launcher biên dịch trong bộ nhớ rồi chạy chương trình. Nó thuận tiện cho demo, nhưng không thay thế build, kiểm thử và quản lý dependency ở dự án lớn. `jshell` (đã có từ Java 9) tiếp tục hữu ích để kiểm tra biểu thức/API nhanh trong REPL.

### 8.2 Tính tương thích bằng `--release`

Khi build bằng JDK mới hơn nhưng phải chạy trên Java 11, dùng:

```bash
javac --release 11 Java11Everyday.java
java Java11Everyday
```

`--release 11` yêu cầu cú pháp, bytecode và API công khai khớp đích Java 11. Chỉ cấu hình `-source`/`-target` riêng lẻ có thể khiến mã biên dịch tham chiếu nhầm API ra đời sau đích chạy. Với Maven/Gradle, đặt toolchain và compiler release nhất quán rồi **chạy test trên runtime Java thực tế** mà hệ thống hỗ trợ. `--release` không xác minh dependency bên ngoài, cấu hình triển khai hay hành vi runtime của mọi thư viện.

### 8.3 JPMS: dùng khi giải quyết vấn đề kiến trúc

Java Platform Module System (đã có từ Java 9) giúp khai báo module, dependency và phạm vi export package khi ứng dụng cần ranh giới rõ ràng. Ví dụ khai báo:

```java
module app.example {
    requires java.net.http;
}
```

Đây là nội dung file `src/app.example/module-info.java`; một lớp `com.example.Main` trong cùng module có thể dùng `HttpClient`. Có thể biên dịch và chạy module theo cấu trúc nguồn phù hợp:

```bash
javac -d mods --module-source-path src -m app.example
java --module-path mods -m app.example/com.example.Main
```

Đoạn lệnh giả định đã có `src/app.example/com/example/Main.java` chứa `public static void main(String[] args)`. Đây là **hướng dẫn cấu trúc module**, không phải một ví dụ đủ các file để chạy ngay. Hệ thống nhiều thư viện hoặc framework vẫn có thể dùng classpath; chỉ đưa JPMS vào khi lợi ích về đóng gói, công bố API hoặc phân phối module đủ rõ.

### 8.4 Java Flight Recorder và chẩn đoán có bằng chứng

Java Flight Recorder (JFR) có thể ghi các sự kiện liên quan CPU, allocation, GC, lock, thread, I/O và nhiều hoạt động khác với overhead thường thấp; dùng để tìm nguyên nhân chậm hoặc tăng bộ nhớ thay vì chỉnh JVM theo cảm tính.

Với tiến trình Java đang chạy, có thể bắt đầu ghi thông qua `jcmd` (thay `<PID>` bằng PID thực tế):

```bash
jcmd <PID> JFR.start name=diagnosis settings=profile duration=60s filename=app.jfr
jfr summary app.jfr
```

Cần quyền truy cập tiến trình và chờ bản ghi hoàn tất trước khi xem file. Tệp JFR có thể chứa thông tin vận hành đáng bảo vệ, vì vậy lưu trữ và chia sẻ theo quy định hệ thống. Mở `.jfr` bằng công cụ phân tích JFR/JDK Mission Control khi cần soi các sự kiện chi tiết.

### 8.5 TLS, container và tối ưu JVM

- Khả năng TLS 1.3 trong JDK 11 là nền tảng còn dùng; dùng JSSE và thiết lập mặc định an toàn của JDK cập nhật, kiểm tra tương thích với server và certificate authority thay vì cố định giao thức khi không cần.
- JVM hiện đại nhận biết một số giới hạn CPU/bộ nhớ của container. Giám sát heap, bộ nhớ ngoài heap, GC pause và giới hạn container cùng lúc; không xem `-Xmx` là toàn bộ bộ nhớ tiến trình.
- Garbage Collector và chính sách mặc định tiến hóa theo các bản JDK. Đo tải thực tế và phân tích JFR/metrics trước khi chọn collector hay flag tinh chỉnh. Tránh mang nguyên bộ cờ JVM cũ sang JDK mới mà chưa kiểm chứng sự hỗ trợ và tác dụng của từng cờ.

## 9. Bài thực hành tổng hợp chạy được từ Java 11

Bài nhỏ sau nhận dữ liệu nhiều dòng, loại khoảng trắng và dòng rỗng, bỏ tên trùng, giữ snapshot không thể sửa rồi báo kết quả. Nó kết hợp `Files`, `String.lines`, `strip`, `Predicate.not`, `List.copyOf`, `Optional.isEmpty` và `var`. Tệp tạm được xóa sau khi chạy.

Lưu thành **`Java11Everyday.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class Java11Everyday {
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempFile("java11-people-", ".txt");
        try {
            Files.writeString(temp, "  An  \n\n Binh \nAn\n",
                    StandardCharsets.UTF_8);

            var names = Files.readString(temp, StandardCharsets.UTF_8)
                    .lines()
                    .map(String::strip)
                    .filter(Predicate.not(String::isBlank))
                    .distinct()
                    .collect(Collectors.toList());

            List<String> immutableNames = List.copyOf(names);
            Optional<String> first = immutableNames.stream().findFirst();

            System.out.println("Danh sach: " + immutableNames);
            System.out.println("Rong? " + first.isEmpty());
            System.out.println("So nguoi: " + immutableNames.size());
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 Java11Everyday.java
java Java11Everyday
```

Kết quả chính xác:

```text
Danh sach: [An, Binh]
Rong? false
So nguoi: 2
```

**Vì sao ví dụ đáng học:** đầu vào và đầu ra có charset rõ; xử lý theo các bước thuần chức năng có thể đọc được; không giữ tài nguyên tệp tạm; `List.copyOf` ngăn tầng khác sửa cấu trúc danh sách thành quả; `Optional` thể hiện được trường hợp không có dòng hợp lệ. Trong ứng dụng thực, nguồn nhập có thể là tệp do người dùng cung cấp và phải xử lý lỗi, kích thước, kiểm soát đường dẫn và quy tắc trùng tên theo nghiệp vụ.

## 10. Các lỗi dễ gặp khi mang kiến thức Java 11 sang ứng dụng hiện đại

| Sai lầm | Hệ quả | Cách đúng |
|---|---|---|
| Nghĩ `var` bỏ kiểm tra kiểu | Hiểu sai lỗi compiler, API mập mờ | Dùng `var` cho biến cục bộ có kiểu suy ra rõ ràng; giữ kiểu tường minh tại ranh giới API |
| Dùng `trim()` cho mọi dữ liệu Unicode | Có thể không loại các whitespace theo chính sách mong muốn | Xác định quy tắc dữ liệu; dùng `strip()` khi cần `Character.isWhitespace` |
| Đọc tệp rất lớn bằng `readString` | Tốn RAM, thậm chí lỗi bộ nhớ | Dùng stream/buffer, đóng tài nguyên |
| Coi `List.copyOf` là deep copy | Object phần tử vẫn có thể đổi | Dùng immutable domain objects hoặc copy sâu khi cần |
| Cho `null` vào `List.of`/`copyOf` | `NullPointerException` | Làm rõ hợp đồng không-null, lọc/kiểm tra có chủ đích |
| Coi status 404/500 là exception tự động của `HttpClient` | Xử lý sai kết quả API | Kiểm tra `response.statusCode()` và hợp đồng response |
| Không đặt timeout hoặc retry mù quáng | Request treo lâu hoặc tác vụ ghi bị lặp | Đặt timeout theo SLA; retry theo loại lỗi và tính idempotent |
| Gọi `join()` ngay sau mọi `sendAsync` | Mất lợi ích phối hợp bất đồng bộ | Kết hợp future, chờ ở ranh giới thực sự cần |
| Chỉ dùng `-source`/`-target` khi phải chạy Java 11 | Có thể dùng API vượt phiên bản đích | Dùng `--release 11` và test trên runtime đích |
| Sao chép cờ GC/JVM từ hệ thống cũ | Flag không còn phù hợp hoặc hại hiệu năng | Đo metrics/JFR trên JDK đang triển khai, chỉnh đúng điểm nghẽn |

## 11. Tiêu chí tự kiểm tra năng lực

Bạn đã nắm được hướng ứng dụng thực tế nếu trả lời được:

1. **Khi nào nên dùng `var`?** Khi biến cục bộ có kiểu suy ra rõ ràng; nó vẫn có kiểu tĩnh và không thay kiểu API public.
2. **`strip()` khác `trim()` thế nào?** Khác quy tắc nhận diện whitespace; cả hai không thay thế validation và chuẩn hóa Unicode theo nghiệp vụ.
3. **Khi nào dùng `readString`, khi nào dùng `Files.lines`?** `readString` hợp với tệp đủ nhỏ để giữ trong bộ nhớ; `Files.lines` cho xử lý theo luồng và phải đóng stream.
4. **Vì sao HTTP status 500 không nhất thiết làm `send` ném exception?** Đó là response hợp lệ ở tầng HTTP; mã status phải được ứng dụng đánh giá.
5. **`List.copyOf` bảo vệ điều gì?** Ngăn thay đổi cấu trúc danh sách, không đóng băng trạng thái object bên trong.
6. **`--release 11` có đủ để bảo đảm chạy được trên mọi môi trường Java 11?** Không; còn dependency, OS, runtime và kiểm thử tích hợp.
7. **Khi ứng dụng chậm, hành động đầu tiên là gì?** Thu thập số liệu/traces/JFR, xác định CPU, allocation, GC, lock hay I/O trước khi thay cờ JVM.

## 12. Tài liệu chính thức để tra cứu tiếp

- [Java SE 11 — String](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): `strip`, `isBlank`, `lines`, `repeat`.
- [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html) và [Path](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Path.html): thao tác đường dẫn và tệp.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): gửi đồng bộ/bất đồng bộ.
- [Java SE 11 — Optional](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html) và [Predicate](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/function/Predicate.html): API theo kiểu hàm.
- [Java 11 — java launcher](https://docs.oracle.com/en/java/javase/11/tools/java.html): source-file mode, các tùy chọn thực thi.

**Nguyên tắc thực hành lâu dài:** Học sâu các API và cơ chế còn tạo ra mã dễ đọc, kiểm thử được, an toàn và dễ quan sát; đối chiếu tài liệu của **JDK đang triển khai** trước khi áp dụng tùy chọn runtime hoặc kết luận về hiệu năng.