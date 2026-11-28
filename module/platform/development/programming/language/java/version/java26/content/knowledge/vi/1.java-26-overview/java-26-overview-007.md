# Ranh giới ví dụ Java 26 và phần cập nhật API preview trên Java 27

*Tình trạng phiên bản tại ngày 27/11/2026.*

Java 26 phát hành GA ngày 17/03/2026; Java 27 đã phát hành GA ngày 15/09/2026. Vì vậy, “preview trên Java 27” mô tả trạng thái của từng tính năng trong một JDK đã GA, không có nghĩa bản thân JDK 27 vẫn là bản thử nghiệm. Một JDK GA có thể chứa đồng thời API ổn định, tính năng ngôn ngữ preview và module incubator. [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) · [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

## 1. Phân biệt ba trạng thái trước khi viết ví dụ

| Trạng thái | Ý nghĩa | Cách sử dụng | Có nên làm phụ thuộc sản phẩm? |
|---|---|---|---|
| **Final / stable** | Đã trở thành phần chính thức của Java SE hoặc JDK ở bản phát hành được nêu. | Dùng API theo tài liệu của JDK đích; không cần bật preview. | Có thể, sau khi kiểm tra tương thích và hỗ trợ của nhà cung cấp JDK. |
| **Preview** | Thiết kế và triển khai đã đủ để thử nghiệm, nhưng tính năng chưa được cam kết là ổn định. Nó có thể đổi, tiếp tục preview hoặc bị loại bỏ. | Bật ở cả bước biên dịch và chạy bằng `--enable-preview`; dùng đúng JDK phát hành tính năng đó. | Tránh làm phụ thuộc bắt buộc của production; nếu thử nghiệm, cô lập và có kế hoạch thay thế. |
| **Incubator** | API thử nghiệm được cung cấp trong module riêng, có thể thay đổi đáng kể hoặc bị loại bỏ. | Thêm module bằng `--add-modules`; thường không cần `--enable-preview` chỉ vì API đang incubate. | Không xem là API Java SE ổn định; chỉ dùng khi chấp nhận chi phí nâng cấp. |

Preview và incubator không phải hai cách gọi cho cùng một trạng thái. Preview có thể là cú pháp ngôn ngữ hoặc API preview trong Java SE; incubator API được đặt trong module có tên riêng như `jdk.incubator.vector`. Cần đọc release notes và API specification của đúng JDK thay vì chỉ nhìn số JEP hoặc bài viết giới thiệu. [Preview Features – Java 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html) · [JVM Specification – Preview Features](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html)

## 2. Những ranh giới quan trọng ở Java 26

### API HTTP Client hỗ trợ HTTP/3 là tính năng ổn định

JEP 517 đưa HTTP/3 vào API chuẩn `java.net.http` từ JDK 26. Có thể chọn phiên bản giao thức bằng `HttpClient.Version.HTTP_3`; không cần bật preview và không cần thêm module incubator.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class Http3Example {
    public static void main(String[] args) throws Exception {
        var client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .build();

        var request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .GET()
                .build();

        var response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("Protocol thực tế: " + response.version());
        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

Có ba điều cần giữ đúng khi giải thích ví dụ này:

- HTTP/3 không phải phiên bản mặc định. `HttpClient.newHttpClient()` vẫn ưu tiên HTTP/2 nếu không cấu hình khác.
- HTTP/3 chỉ áp dụng cho URI HTTPS trong implementation tích hợp của JDK 26; implementation này không dùng HTTP/3 khi request đi qua proxy.
- Chọn HTTP/3 là đặt phiên bản ưu tiên. Giao thức thực tế còn phụ thuộc khả năng máy chủ, quá trình khám phá/kết nối, TLS và cấu hình mạng. Hãy đọc `response.version()` và kiểm thử trên môi trường đích, thay vì giả định mọi request đều đi qua HTTP/3.

Nguồn API: [HttpClient – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html) và [HttpClient.Version – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html).

### Các tính năng vẫn ở trạng thái thử nghiệm trong Java 26

| Tính năng | JEP trên JDK 26 | Trạng thái ở JDK 26 |
|---|---:|---|
| Primitive types trong pattern, `instanceof` và `switch` | 530 | Preview lần thứ tư |
| Lazy Constants | 526 | Preview lần thứ hai |
| Structured Concurrency | 525 | Preview lần thứ sáu |
| Vector API | 529 | Incubator lần thứ mười một |
| PEM Encodings of Cryptographic Objects | 524 | Preview lần thứ hai |

Vì vậy, một ví dụ Java 26 dùng pattern primitive, `LazyConstant`, `StructuredTaskScope` hoặc API PEM phải được gắn nhãn preview; ví dụ dùng Vector API phải được gắn nhãn incubator. Không ghi chung rằng tất cả các tính năng này đã là API chính thức ổn định của Java 26.

Java 26 còn có cải tiến ổn định về hiệu năng như giảm đồng bộ giữa luồng ứng dụng và luồng GC của G1 (JEP 522), cùng mở rộng AOT Object Caching để dùng được với mọi garbage collector (JEP 516). Đây là thay đổi của runtime/JVM; chúng không biến API preview thành API ổn định. [JDK 26 Release Notes – Major New Functionality](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)

## 3. Cập nhật đúng trạng thái khi chuyển sang Java 27

JDK 27 tiếp tục các nhánh thử nghiệm của Java 26. Số lần preview/incubator tăng lên không đồng nghĩa API đã ổn định.

| Tính năng | Java 26 | Java 27 | Cách ghi trong ví dụ Java 27 |
|---|---|---|---|
| Primitive types trong pattern, `instanceof`, `switch` | JEP 530 – Preview 4 | JEP 532 – Preview 5 | Ngôn ngữ preview |
| Lazy Constants | JEP 526 – Preview 2 | JEP 531 – Preview 3 | API preview |
| Structured Concurrency | JEP 525 – Preview 6 | JEP 533 – Preview 7 | API preview |
| Vector API | JEP 529 – Incubator 11 | JEP 537 – Incubator 12 | API incubator `jdk.incubator.vector` |
| PEM Encodings of Cryptographic Objects | JEP 524 – Preview 2 | JEP 538 – Preview 3 | API preview |

JDK 27 cũng có các thay đổi đã hoàn tất, không cần bật preview:

- **JEP 527 – Post-Quantum Hybrid Key Exchange for TLS 1.3:** bổ sung cơ chế trao đổi khóa lai hậu lượng tử cho TLS 1.3. Ứng dụng dùng các API `javax.net.ssl` có thể nhận lợi ích từ cấu hình mặc định của JDK; vẫn cần kiểm thử khả năng tương thích với máy chủ, thiết bị trung gian và chính sách TLS của hệ thống.
- **JEP 523 – G1 trở thành garbage collector mặc định trong mọi môi trường:** thay đổi lựa chọn mặc định của runtime; không có nghĩa mọi ứng dụng đều đạt độ trễ hoặc thông lượng tốt hơn mà không cần đo đạc.
- **JEP 534 – Compact Object Headers mặc định:** thay đổi bố cục header đối tượng của HotSpot; trên kiến trúc 64-bit, header gọn hơn có thể giảm mức dùng heap. Cần benchmark ứng dụng và kiểm tra agent, profiler hoặc công cụ phụ thuộc chi tiết runtime.
- **JEP 536 – JFR In-Process Data Redaction:** bổ sung khả năng che dữ liệu nhạy cảm trong bản ghi JDK Flight Recorder trước khi dữ liệu rời khỏi tiến trình.

HTTP/3 của JEP 517 đã là API ổn định từ Java 26; không xếp nó vào nhóm preview mới của Java 27. Danh sách chính thức của JDK 27 xác nhận bốn tính năng preview và một tính năng incubator trong nhóm cải tiến chính. [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) · [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)

## 4. Ví dụ ngôn ngữ preview phải gắn với đúng JDK

Primitive patterns cho phép dùng kiểu nguyên thủy trong ngữ cảnh pattern, đồng thời mở rộng `switch` và `instanceof` để làm việc với kiểu nguyên thủy. Đoạn sau minh họa cú pháp `switch` với `double` trong JDK 27:

```java
public class PrimitivePatternPreview {
    static String describe(double value) {
        return switch (value) {
            case 0d -> "zero";
            case double n when n > 0d -> "positive";
            case double n when n < 0d -> "negative";
            default -> "NaN";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(12.5d));
        System.out.println(describe(-3d));
        System.out.println(describe(Double.NaN));
    }
}
```

Đây vẫn là preview trong JDK 27 (JEP 532). Cú pháp tương ứng đã xuất hiện ở Java 26 dưới JEP 530, nhưng số phiên bản preview và các quy tắc ngôn ngữ phải được xác định theo JDK dùng để biên dịch.

```bash
# Terminal đang dùng javac và java thuộc JDK 26
javac --enable-preview --release 26 -d out26 PrimitivePatternPreview.java
java --enable-preview -cp out26 PrimitivePatternPreview

# Terminal đang dùng javac và java thuộc JDK 27
javac --enable-preview --release 27 -d out27 PrimitivePatternPreview.java
java --enable-preview -cp out27 PrimitivePatternPreview
```

Hai nhóm lệnh trên là hai lần biên dịch độc lập. Không dùng class file được biên dịch với preview của JDK 26 để chạy trên JDK 27, hoặc ngược lại. `--enable-preview` phải được bật ở cả compiler và runtime, và phải dùng đúng bản phát hành đã định nghĩa preview đó. Trình biên dịch JDK 27 không thể được dùng để bật preview của JDK 26 bằng cách đặt `--release 26`.

## 5. Ví dụ API preview Java 27 có thể đổi chữ ký

Structured Concurrency cho thấy vì sao không nên sao chép nguyên ví dụ preview từ phiên bản trước. Trong Java 27, `StructuredTaskScope` có ba tham số kiểu và chính sách mặc định của `join()` dùng `ExecutionException`. Tài liệu Java 26 mô tả chữ ký hai tham số kiểu và `FailedException` cho luồng lỗi mặc định. Hãy dùng API specification của JDK mục tiêu để viết code.

Ví dụ rút gọn theo API Java 27:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

static Profile loadProfile(String id)
        throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.<Object>open()) {
        var user = scope.fork(() -> loadUser(id));
        var orders = scope.fork(() -> loadOrders(id));

        scope.join();
        return new Profile(user.get(), orders.get());
    }
}
```

Ví dụ trên giả định `loadUser`, `loadOrders` và `Profile` đã được định nghĩa. `fork` chạy các tác vụ con trong scope; `join` đợi theo chính sách của scope; sau khi join thành công, chương trình lấy kết quả từ từng subtask. Đây là API preview trong JDK 27, vì vậy ví dụ cần biên dịch và chạy bằng JDK 27 với preview được bật.

Các API preview khác của JDK 27 gồm:

- `java.lang.LazyConstant`: giữ một giá trị được khởi tạo tối đa một lần; API vẫn preview, dù mục đích là cho JVM tối ưu như hằng số sau khi khởi tạo.
- `java.security.BinaryEncodable` cùng các API PEM liên quan: hỗ trợ biểu diễn và mã hóa/giải mã vật liệu khóa, chứng thư và dữ liệu mật mã dưới dạng PEM; vẫn preview.
- `java.util.concurrent.StructuredTaskScope`: API điều phối nhóm tác vụ đồng thời; vẫn preview.

Nguồn API: [StructuredTaskScope – Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) · [LazyConstant – Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html) · [BinaryEncodable – Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html).

## 6. Vector API là incubator, không phải preview

Trong JDK 27, Vector API vẫn nằm trong module `jdk.incubator.vector` (JEP 537). Khi biên dịch và chạy, thêm module rõ ràng:

```bash
javac --add-modules jdk.incubator.vector -d out VectorExample.java
java --add-modules jdk.incubator.vector -cp out VectorExample
```

Không thêm `--enable-preview` chỉ vì Vector API đang incubate. Nếu cùng một chương trình còn sử dụng một tính năng preview khác, khi đó phải bật preview riêng theo đúng JDK. Module incubator có thể đổi tên, đổi chữ ký hoặc bị loại bỏ ở bản phát hành sau; không đưa nó vào hợp đồng API công khai của thư viện nếu chưa chấp nhận rủi ro tương thích.

## 7. Quy tắc biên dịch và kiểm tra phiên bản

Dùng các quy tắc sau khi tạo ví dụ, cấu hình IDE hoặc pipeline build:

| Mục tiêu | Compiler | Runtime |
|---|---|---|
| API ổn định của Java 26 | JDK 26; có thể dùng `--release 26` | JDK tương thích với bytecode/API được dùng |
| Preview của Java 26 | JDK 26 với `--enable-preview --release 26` | JDK 26 với `--enable-preview` |
| Preview của Java 27 | JDK 27 với `--enable-preview --release 27` | JDK 27 với `--enable-preview` |
| Vector API incubator của Java 27 | JDK 27 với `--add-modules jdk.incubator.vector` | JDK 27 với `--add-modules jdk.incubator.vector` |
| API ổn định của Java 27 | JDK 27; có thể dùng `--release 27` | JDK tương thích với bytecode/API được dùng |

Trước khi kết luận một ví dụ chạy được, kiểm tra cả hai công cụ trong cùng môi trường:

```bash
java -version
javac -version
```

Với preview, class file mang dấu hiệu phụ thuộc preview của đúng release. JVM chỉ nạp được class file đó khi chạy cùng phiên bản Java SE và bật preview. Do đó, không xem `--enable-preview` là công tắc tương thích ngược hoặc cách giữ API preview chạy qua các bản JDK.

## 8. Cách ghi nhãn và nâng cấp ví dụ trong tài liệu

- Ghi rõ **JDK 26 stable**, **JDK 26 preview lần 4**, **JDK 27 preview lần 5** hoặc **JDK 27 incubator lần 12** ngay cạnh ví dụ. Không dùng nhãn chung “Java mới”.
- Ghi JEP và phiên bản JDK tương ứng. Nếu một tính năng được preview lại, cập nhật JEP của release mới và kiểm tra lại API, cú pháp, ngoại lệ, cấu hình compiler/runtime.
- Đặt ví dụ preview trong phần thử nghiệm riêng. Với ứng dụng thực tế, ưu tiên API stable; nếu buộc phải thử preview, bọc sau adapter, khóa toolchain, kiểm thử hồi quy và chuẩn bị đường thay thế.
- Với incubator, ghi cả tên module và cờ `--add-modules`. Không nhầm module incubator với module chuẩn chỉ vì cả hai đều có trong JDK.
- Khi nâng cấp runtime, kiểm tra source compatibility, binary compatibility và behavioral compatibility; cập nhật thư viện, plugin, agent và cấu hình JVM. Đo lại GC, heap, độ trễ, TLS và hành vi ghi JFR trên môi trường đại diện.
- Với HTTP/3, xác minh giao thức thực tế và thử các tình huống HTTPS, proxy, TLS và máy chủ không hỗ trợ HTTP/3.
- Với JDK 27, kiểm tra tác động của G1 mặc định, Compact Object Headers và TLS hậu lượng tử bằng benchmark và bài kiểm thử tương thích. Không suy ra hiệu năng hoặc khả năng tương thích chỉ từ mô tả tính năng.

## Tài liệu tham chiếu

1. [Oracle – Consolidated JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
2. [Oracle – Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
3. [Oracle – Preview Features, Java 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
4. [Oracle – Primitive Types in Patterns, instanceof, and switch, Java 27](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html)
5. [Oracle API – HttpClient, Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
6. [Oracle API – StructuredTaskScope, Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
7. [Oracle Migration Guide – Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
8. [Java Virtual Machine Specification, Java SE 27 – Preview Features](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html)


