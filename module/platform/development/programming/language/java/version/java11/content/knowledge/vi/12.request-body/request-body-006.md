# `HttpRequest.BodyPublishers.ofInputStream` và cấp lại nguồn khi cần gửi lại trong Java 11

## 1. Mục tiêu bài học

Khi ứng dụng Java gửi dữ liệu lớn qua HTTP, chẳng hạn tệp log, tài liệu hoặc dữ liệu xuất từ hệ thống, việc chuyển toàn bộ nội dung thành `byte[]` trước khi gửi có thể tốn bộ nhớ. Java 11 hỗ trợ **đọc request body theo luồng** thông qua:

```java
HttpRequest.BodyPublishers.ofInputStream(
        Supplier<? extends InputStream> streamSupplier)
```

Điểm khác biệt quan trọng: API này nhận **`Supplier<InputStream>`**, không phải một `InputStream` duy nhất. Khi cần phát lại body, chẳng hạn một request được gửi lại, `BodyPublisher` có thể được đăng ký (subscribe) lần nữa và phải tạo ra **cùng dữ liệu** từ đầu. Một stream đã đọc hết sẽ không đáp ứng yêu cầu đó.

Sau bài học, bạn có thể:

1. Giải thích `ofInputStream` hoạt động với `BodyPublisher` và `Flow.Subscriber` như thế nào.
2. Viết supplier tạo **stream mới**, đọc từ đầu trong mỗi lần gọi.
3. Phân biệt một nguồn **có khả năng phát lại (repeatable)** với nguồn dùng một lần.
4. Chọn đúng `ofInputStream`, `ofFile`, `ofByteArray` hoặc `ofString` theo khối lượng dữ liệu.
5. Xử lý các vấn đề khi gửi lại: nguồn thay đổi, I/O failure, unknown content length, authentication/redirect, timeout, retry và HTTP idempotency.
6. Kiểm tra tính đúng đắn bằng chương trình Java 11 tự chạy, không cần truy cập Internet.

Các API được trình bày có trên **Java 11** và vẫn được hỗ trợ trên các JDK hiện đại. Không dựa vào phương thức chỉ có ở JDK mới hoặc hành vi không được tài liệu API bảo đảm.

## 2. Phân biệt request body và response body

Trong `java.net.http` có hai API tên gần giống nhưng dùng ở **hai chiều khác nhau**:

| API | Chiều dữ liệu | Vai trò |
| --- | --- | --- |
| `HttpRequest.BodyPublishers.ofInputStream(supplier)` | **Gửi đi** | HTTP client đọc byte từ một `InputStream` do supplier cung cấp để tạo request body |
| `HttpResponse.BodyHandlers.ofInputStream()` | **Nhận về** | HTTP client cung cấp một `InputStream` để caller đọc response body; caller phải tiêu thụ hoặc đóng stream |
| `HttpResponse.BodySubscribers.ofInputStream()` | **Nhận về** | Mức API subscriber tương ứng với handler ở trên |

Bài này tập trung vào **request body**, cụ thể là `HttpRequest.BodyPublishers.ofInputStream`.

`HttpRequest.BodyPublisher` là một `Flow.Publisher<ByteBuffer>`; khi gửi request, HTTP client đăng ký subscriber để lấy dãy byte được phát ra. Tài liệu `BodyPublisher` Java 11 quy định: **nếu cần gửi lại request body vì bất kỳ lý do gì, một subscription mới sẽ được tạo và được kỳ vọng cung cấp cùng dữ liệu như trước**.

`ofInputStream` không buffer toàn bộ request body; vì vậy nó nhận **supplier của các input stream đã mở** để có thể chuẩn bị lại dữ liệu khi cần.

## 3. Vì sao không truyền một `InputStream` duy nhất?

Một `InputStream` có **trạng thái con trỏ đọc**. Sau khi đọc đến EOF, nó không tự quay về đầu; có loại stream hỗ trợ `mark/reset` nhưng không phải mọi stream đều hỗ trợ, và việc reset không giải quyết được mọi tình huống đóng/cancel/retry.

**Sai về thiết kế nguồn phát lại:**

```java
InputStream once = Files.newInputStream(path);

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(() -> once);
```

Đây là **trích đoạn minh họa anti-pattern**, cần import `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.Path` và `java.net.http.HttpRequest`; `path` là đường dẫn đã được chuẩn bị trước đó.

Vấn đề: mọi lần supplier được gọi đều trả về **cùng object stream**. Lần phát đầu có thể đã tiêu thụ hoặc đóng nó; lần phát thứ hai sẽ bắt đầu sai vị trí, không có dữ liệu hoặc thất bại. Không có bảo đảm một request sẽ chỉ có một subscription. Việc cache stream vào field rồi dùng lại có cùng lỗi.

**Đúng hơn với tệp có thể mở lại:**

```java
Supplier<InputStream> source = () -> {
    try {
        return Files.newInputStream(path);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(source);
```

Đây là **trích đoạn Java 11** cần các import `java.io.IOException`, `java.io.InputStream`, `java.io.UncheckedIOException`, `java.nio.file.Files`, `java.net.http.HttpRequest` và `java.util.function.Supplier`.

Mỗi lần supplier thực thi, nó mở một **`InputStream` riêng** tại đầu tệp. Nếu không mở được, lỗi sẽ được biểu diễn thành `UncheckedIOException` vì `Supplier.get()` không có khai báo `throws IOException`. Thất bại có thể được báo lúc HTTP client thực sự lấy body, **không nhất thiết ngay lúc xây dựng request**.

**Cảnh báo:** mở lại cùng `Path` chưa bảo đảm các byte giống nhau nếu tệp bị sửa hoặc thay thế giữa hai lần mở. Vấn đề **tính bất biến nguồn** được giải thích ở mục tiếp theo.

## 4. Hợp đồng API và hành vi khi gửi lại

Tài liệu `HttpRequest.BodyPublishers.ofInputStream` Java 11 mô tả:

- Publisher lấy dữ liệu từ `InputStream` mà supplier cung cấp.
- Nội dung **không được buffer** toàn bộ chỉ nhằm phục vụ việc phát lại.
- Supplier tồn tại để **có nguồn mới nếu request body phải gửi lại**.
- Supplier **có thể trả `null` ở lần thử tiếp theo**, nhưng khi đó **request thất bại**; không nên dùng `null` trong workflow mong đợi retry thành công.
- `BodyPublisher` có thể nhận **subscription mới** khi cần gửi lại, và subscription mới được kỳ vọng phát ra **cùng chuỗi byte**.

Dịch ra yêu cầu triển khai:

1. **Mỗi lần gọi `get()` phải cho một stream có thể đọc được từ đầu**, không phải đã tiêu thụ.
2. **Nội dung mỗi lần phát phải tương đương byte-for-byte** nếu đang phát lại *cùng request body*.
3. Supplier không được phụ thuộc vào iterator, socket hay request stream một lần đã hết; nếu không tạo lại được nguồn, phải thiết kế lại.
4. Supplier nên đơn giản, không có tác dụng phụ nghiệp vụ như ghi nhận thanh toán hay tăng số lần xử lý bản ghi.
5. Tên tệp/nguồn phải tiếp tục tồn tại cho đến khi các attempt cần thiết kết thúc; không xóa file ngay sau `build()` hay sau khi bắt đầu `sendAsync()`.
6. Không giả định supplier được gọi **đúng một lần**, **luôn hai lần** hoặc **tự động retry trong mọi lỗi**; số lần gọi phụ thuộc quá trình gửi, điều kiện HTTP và implementation.

**Điểm rất quan trọng:** việc publisher có khả năng tạo lại body **không phải** cam kết HTTP client sẽ tự động phát lại mọi request, hay ứng dụng nên retry mọi POST. Khả năng lặp lại body và **chính sách gửi lại request ở tầng nghiệp vụ** là hai trách nhiệm riêng.

## 5. Khi nào cần nguồn phát lại?

Một request body có thể cần được phát lại trong nhiều kịch bản:

- **Authentication challenge**: việc trao đổi xác thực có thể yêu cầu gửi lại request, tùy cơ chế và cấu hình client.
- **Redirect giữ nguyên method/body**: một số dạng chuyển hướng theo HTTP (chẳng hạn 307/308 khi được client xử lý theo policy) yêu cầu giữ nguyên nội dung body. Không mặc định mọi mã 3xx đều phát lại POST nguyên vẹn; redirect còn phụ thuộc chính sách `HttpClient.Redirect` và đặc tả HTTP.
- **Lỗi kết nối và khôi phục**: có những tình huống network hoặc connection reuse khiến client cần thử lại theo chính sách của implementation, nhưng không có bảo đảm mọi lỗi đều được retry.
- **Ứng dụng chủ động gửi lại**: code có retry/backoff có thể gửi lại cùng `HttpRequest` hoặc tạo request tương đương; BodyPublisher cần có nguồn nguyên vẹn cho mỗi lần gửi.
- **Kiểm thử repeatability**: dù môi trường hiện tại luôn chỉ gửi một lần, thư viện và pipeline có thể thay đổi; supplier tốt không dựa vào giả định chỉ có một lần đăng ký.

**Không lạm dụng tự động retry:** một POST có side effect có thể đã được server xử lý dù client không nhận response vì mất kết nối. Khi gửi lại, server có thể xử lý **hai lần**. Cần thiết kế idempotency key phía server, nhận diện request trùng hoặc thỏa thuận giao thức tương ứng; `ofInputStream` không giải quyết tính idempotent.

## 6. Chương trình Java 11 đầy đủ: tạo hai stream độc lập từ cùng nguồn

Chương trình này dùng `ByteArrayInputStream` cho dữ liệu thử nghiệm bất biến và mô phỏng việc xin nguồn nhiều lần. Nó tạo `HttpRequest` với `BodyPublishers.ofInputStream`, nhưng **không gửi request thực** để output không phụ thuộc mạng. Việc gọi trực tiếp supplier hai lần chứng minh thiết kế source repeatable, **không có nghĩa chương trình đã tạo hai HTTP subscription**.

Tạo tệp **`RepeatableInputStreamDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class RepeatableInputStreamDemo {
    public static void main(String[] args) throws IOException {
        final byte[] snapshot =
                "data-123".getBytes(StandardCharsets.UTF_8);
        AtomicInteger opened = new AtomicInteger();

        Supplier<InputStream> freshSource = () -> {
            opened.incrementAndGet();
            return new ByteArrayInputStream(snapshot);
        };

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/upload"))
                .header("Content-Type", "text/plain; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofInputStream(
                        freshSource))
                .build();

        System.out.println("Method: " + request.method());
        System.out.println("Supplier calls before get: " + opened.get());

        try (InputStream first = freshSource.get();
             InputStream second = freshSource.get()) {
            System.out.println("Different streams: " + (first != second));
            System.out.println("First bytes: "
                    + first.read() + "/" + second.read());
            System.out.println("Remaining first: "
                    + new String(first.readAllBytes(),
                            StandardCharsets.UTF_8));
            System.out.println("Remaining second: "
                    + new String(second.readAllBytes(),
                            StandardCharsets.UTF_8));
        }
        System.out.println("Supplier calls after get: " + opened.get());
    }
}
```

Biên dịch và chạy với **JDK 11**:

```bash
javac --release 11 -encoding UTF-8 RepeatableInputStreamDemo.java
java RepeatableInputStreamDemo
```

**Kết quả chuẩn:**

```text
Method: POST
Supplier calls before get: 0
Different streams: true
First bytes: 100/100
Remaining first: ata-123
Remaining second: ata-123
Supplier calls after get: 2
```

Giải thích:

1. `newBuilder(...).POST(...).build()` chỉ tạo request; không gửi, vì vậy supplier chưa được gọi. Việc tạo `BodyPublisher` không đòi hỏi cấp dữ liệu ngay trong ví dụ này.
2. Hai lần `freshSource.get()` tạo **hai `ByteArrayInputStream` khác nhau** trên cùng snapshot byte. `first != second` là `true`.
3. Byte đầu là ký tự `d`, mã UTF-8/ASCII **100** ở cả hai stream.
4. Đọc mỗi stream một byte làm con trỏ từng stream tiến lên độc lập; phần còn lại cùng là `ata-123`.
5. Sau hai lần xin nguồn, bộ đếm `AtomicInteger` là **2**.
6. `try-with-resources` đóng hai stream do **chính chương trình thử nghiệm mở trực tiếp**. Trong request thực, HTTP client là consumer của nguồn cấp cho `BodyPublisher`; test đường gửi, lỗi, cancel và resource cleanup theo runtime được dùng.

**Vì sao dùng `AtomicInteger`?** Ví dụ này không cần concurrency, nhưng một supplier có thể được kích hoạt từ các tác vụ bất đồng bộ; counter thường nên thread-safe nếu dùng để quan sát số lần mở nguồn. **Đừng đưa counter vào logic nghiệp vụ** để trả “lần đầu nội dung này, lần sau nội dung khác”.

## 7. Mẫu Java 11 thực tế: stream file lớn và mở lại khi cần

Với file có thể đọc lại, pattern sau không giữ toàn bộ file trong heap:

```java
static HttpRequest buildUpload(Path sourceFile, URI target) {
    Supplier<InputStream> fresh = () -> {
        try {
            return Files.newInputStream(sourceFile);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    };

    return HttpRequest.newBuilder(target)
            .timeout(Duration.ofSeconds(30))
            .header("Content-Type", "application/octet-stream")
            .POST(HttpRequest.BodyPublishers.ofInputStream(fresh))
            .build();
}
```

Đây là **phương thức minh họa** bên trong một lớp; cần import `java.io.InputStream`, `java.io.IOException`, `java.io.UncheckedIOException`, `java.net.URI`, `java.net.http.HttpRequest`, `java.nio.file.Files`, `java.nio.file.Path`, `java.time.Duration` và `java.util.function.Supplier`.

Cách gọi trích đoạn:

```java
HttpRequest upload = buildUpload(
        Path.of("report.bin"),
        URI.create("https://example.com/upload"));

HttpResponse<String> response = client.send(
        upload, HttpResponse.BodyHandlers.ofString());
```

Đoạn này cần khai báo `client` kiểu `HttpClient`, import `HttpResponse` và xử lý `IOException`/`InterruptedException`; nó **không chạy được nếu không có endpoint thực**. `ofInputStream` cho phép luồng đọc byte dần thay vì gom hết tệp vào `byte[]`.

**Bảo đảm cần bổ sung:** `sourceFile` phải đại diện cho dữ liệu **ổn định** trong suốt mọi attempt. Nếu một tiến trình khác sửa nội dung sau lần gửi đầu, lần mở thứ hai có thể phát dữ liệu khác. Để bảo toàn:

- Tạo snapshot bất biến trong vùng lưu trữ do ứng dụng quản lý, hạn chế thay đổi cho đến khi upload kết thúc.
- Hoặc dùng nội dung đã chốt trong `byte[]` cho payload nhỏ.
- Với dữ liệu quan trọng, có thể ghi checksum/version vào metadata và xác minh trước/sau việc xử lý; chỉ dùng checksum không tự động khóa dữ liệu tránh sửa trong lúc đọc.
- Nếu file là tạm, chỉ xóa sau khi kết thúc **toàn bộ** workflow gửi/cancel/retry. Với `sendAsync`, không xóa ngay khi hàm trả `CompletableFuture`.

Đừng kết luận từ việc `Files.newInputStream(path)` mở thành công rằng các byte trong hai lần mở chắc chắn giống nhau. Nếu dữ liệu cần snapshot tuyệt đối, phải chọn cơ chế lưu và sở hữu phù hợp, tính cả khả năng file bị thay thế hoặc xóa giữa hai attempt.

## 8. `ofInputStream` và `ofFile` có gì khác?

Đều là API hợp lệ trên **Java 11** và vẫn dùng được hiện nay:

| API | Nguồn | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| `BodyPublishers.ofInputStream(supplier)` | `InputStream` từ supplier | Linh hoạt với file, object storage, stream do ứng dụng xây dựng, nguồn có thể mở lại | Trách nhiệm đảm bảo **fresh stream** và **same bytes** khi cần replay; kích thước body có thể chưa biết |
| `BodyPublishers.ofFile(path)` | `Path` của file | Ngắn gọn cho file có sẵn; tránh tự viết supplier mở file | File vẫn có thể đổi/xóa trong khi gửi; cần bảo đảm ổn định nguồn |
| `BodyPublishers.ofByteArray(bytes)` | `byte[]` | Nguồn nhỏ và cố định, dễ lặp lại nếu ứng dụng không sửa mảng | Giữ toàn bộ byte trong heap |
| `BodyPublishers.ofString(text, UTF_8)` | `String` | Tiện cho JSON/text nhỏ | Có bước mã hóa và dữ liệu trong bộ nhớ; charset phải đúng |
| `BodyPublishers.fromPublisher(pub)` | Publisher do người dùng cung cấp | Tích hợp nguồn bất đồng bộ/Reactive Streams | Không mặc định replayable; publisher phải tuân thủ hợp đồng subscription và body |

Nếu nguồn đơn giản chỉ là một file ổn định, `ofFile(path)` thường dễ đọc hơn. `ofInputStream` phù hợp khi **cách mở nguồn** cần tùy biến (snapshot lưu ở storage riêng, stream giải mã, tài liệu được tạo theo yêu cầu...) và có thể cung cấp nguồn tương đương cho mỗi lần thử.

Đừng nhầm `BodyPublishers.ofInputStream` với `Files.readAllBytes` rồi `ofByteArray`. Cách thứ hai bắt buộc giữ tất cả byte trong bộ nhớ. Với file nhiều GB, nên xem xét gửi theo luồng, giới hạn kích thước, nguồn có thể mở lại và backpressure thay vì chỉ tối ưu việc xây dựng body.

## 9. Độ dài body: không tự tính bằng `InputStream.available()`

`HttpRequest.BodyPublisher.contentLength()` trả:

- Một số dương nếu biết độ dài.
- `0` nếu body rỗng.
- Số âm nếu không biết độ dài trước khi phát.

Publisher từ `ofInputStream` thường không biết trước số byte; API không yêu cầu đọc toàn bộ dữ liệu để tính length. **`InputStream.available()` không phải kích thước toàn bộ stream**: nó chỉ ước lượng số byte có thể đọc ngay mà không block theo hợp đồng của InputStream.

Hệ quả vận hành:

- Giao thức HTTP có cơ chế gửi request body khi chưa biết độ dài; cách truyền thực tế phụ thuộc phiên bản HTTP và JDK.
- Một số server, proxy hoặc upload endpoint yêu cầu `Content-Length` xác định; cần kiểm thử với hệ thống đó.
- **Không tự gắn `Content-Length` tùy ý** nếu không khớp dữ liệu phát ra. `HttpClient` quản lý nhiều header hạn chế; truyền length sai có thể làm request thất bại, treo hoặc gây lỗi giao thức.
- Nếu endpoint bắt buộc độ dài được biết trước, cân nhắc `ofFile` cho nguồn file ổn định, `ofByteArray` cho payload nhỏ, hoặc triển khai `BodyPublisher` riêng có hợp đồng length chính xác và replayability phù hợp.

Khi nguồn có độ dài thay đổi giữa các lần gửi, request bị phát lại có thể không còn tương đương. Vì vậy cần chốt payload và tránh sửa nguồn trong suốt chu kỳ gửi.

## 10. Chính sách retry, redirects và idempotency

**Khả năng mở lại stream không đồng nghĩa một POST có thể retry an toàn.**

Giả sử server đã nhận và tạo đơn hàng, nhưng kết nối bị rớt trước khi client đọc response. Client không thể kết luận chắc chắn server đã hay chưa xử lý request. Nếu gửi lại với cùng body mà server không có chống trùng, đơn hàng có thể được tạo hai lần.

Khi thiết kế:

1. **Phân biệt retry transport và retry nghiệp vụ.** Transport có thể gửi lại do một số điều kiện HTTP/network; retry nghiệp vụ do ứng dụng quyết định.
2. **Thiết kế idempotency ở phía nhận** nếu endpoint có side effect. Sử dụng khóa idempotency ổn định cho cùng thao tác và quy tắc deduplication trên server.
3. **Giữ nguyên nội dung byte** cho mọi attempt của cùng một thao tác. Supplier tạo stream mới không được tự tạo dữ liệu khác giữa các lần gọi.
4. **Không retry vô hạn**; có deadline, số attempt tối đa và backoff phù hợp. Tránh retry lỗi xác thực, kiểm tra input hoặc lỗi không thể phục hồi như một thao tác tự động.
5. **Đánh giá redirect theo method/status.** HTTP 307/308 thường giữ method/body, nhưng xử lý thực tế phụ thuộc policy của client; không mặc định mọi redirect chuyển tiếp body.
6. **Theo dõi số lần phát thật.** Đếm số lần mở stream chỉ là chỉ báo hoạt động supplier, không tự tương đương với số request server nhận.
7. **Giữ trạng thái cancellation.** Khi request bị hủy, có thể đã có byte gửi đi; hủy future không thể đảo ngược một side effect ở server.

### Ví dụ chính sách idempotency

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/orders"))
        .header("Idempotency-Key", stableBusinessOperationId)
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofInputStream(
                streamSupplier))
        .build();
```

Đây là **trích đoạn**, `stableBusinessOperationId` là khóa ổn định đã được tạo cho **một nghiệp vụ** và `streamSupplier` là supplier phát lại cùng nội dung. `Idempotency-Key` không phải cơ chế mà `HttpClient` tự thực thi; **server phải chủ động hỗ trợ và xử lý chống trùng**. Đừng tự tạo khóa mới cho mỗi lần thử lại của cùng một nghiệp vụ.

## 11. Quản lý lỗi, đóng nguồn và vòng đời bất đồng bộ

### 11.1. Khi mở stream thất bại

`Supplier.get()` không khai báo checked exception; khi `Files.newInputStream` ném `IOException`, có thể bọc bằng `UncheckedIOException` trong supplier để HTTP exchange thất bại có ý nghĩa. Đừng bắt lỗi rồi trả một stream rỗng: server có thể nhận payload rỗng và nhầm là dữ liệu hợp lệ.

Nếu muốn **từ chối phát lại** do nguồn không thể cung cấp nữa, tài liệu cho phép supplier trả `null` ở các lần sau; việc đó làm request **fail**, không phải “đã gửi lại thành công với payload rỗng”. Với workflow yêu cầu retry thành công, vẫn nên trả stream thật hoặc thất bại có kiểm soát.

### 11.2. Ai đóng các `InputStream` được supplier tạo?

Stream do supplier đưa cho HTTP client để phát request body sẽ được sử dụng trong chu kỳ subscription. Tài nguyên cần được xử lý đúng cả khi thành công, lỗi, hủy hoặc retry. Không dùng cách “mở một stream từ trước, giữ lại rồi đóng thủ công ngay sau `sendAsync`”, vì có thể đóng nó trước khi client kịp đọc.

Nên:

- Cung cấp stream mới khi mỗi subscription cần nguồn.
- Đọc tài liệu và kiểm thử lifecycle cho loại nguồn cụ thể, đặc biệt nếu stream do ứng dụng tự triển khai hoặc có phụ thuộc kết nối/tài nguyên bên ngoài.
- Quản lý vòng đời nguồn theo *toàn bộ* request và mọi attempt, không theo thời điểm tạo `HttpRequest`.
- Nếu triển khai một `BodyPublisher` tùy biến thay vì dùng `ofInputStream`, phải chịu trách nhiệm đóng/cancel tài nguyên đúng theo hợp đồng `Flow.Subscription`.
- Không giả định `ByteArrayInputStream` cần được xử lý giống một socket hoặc stream file; loại tài nguyên quyết định mức độ cleanup phải kiểm tra.

### 11.3. Không nhầm hoàn thành future với việc chuẩn bị nguồn mới

Với `sendAsync`, lời gọi trả `CompletableFuture` ngay, trong khi supplier có thể được thực thi sau đó khi body được tiêu thụ. Nếu ứng dụng xóa file hoặc thay đổi payload ngay sau khi nhận future, request có thể lỗi hoặc gửi dữ liệu không như dự kiến.

Mẫu tổ chức:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

future.whenComplete((response, error) -> {
    if (error != null) {
        System.err.println("Upload failed: " + error);
    } else {
        System.out.println("HTTP status: " + response.statusCode());
    }
    // Chỉ dọn snapshot khi chắc chắn mọi attempt/
    // retry nghiệp vụ và consumer phụ thuộc đã kết thúc.
});
```

Đây là **trích đoạn** cần import `CompletableFuture`, `HttpResponse`, `HttpClient` và khai báo `client/request`, không phải chương trình độc lập. Nếu workflow tiếp tục retry sau khi future đầu tiên hoàn tất lỗi, callback đó **chưa phải** thời điểm xóa snapshot dùng chung cho mọi attempt.

Trong ứng dụng thật cần quan sát timeout, giới hạn số upload song song, kích thước nguồn, đường truyền và lỗi từ server. Việc giữ snapshot trên ổ đĩa cũng cần cleanup cuối workflow thành công, thất bại hoặc hủy.

## 12. Các nguồn một lần không thể “biến thành repeatable” chỉ bằng lambda

Ví dụ nguồn dùng một lần:

- `System.in` hoặc stream từ socket nhận dữ liệu trực tiếp.
- Stream của một giao dịch upload chỉ đọc một lần.
- Một iterator/queue tiêu thụ dữ liệu không thể tua lại.
- Dữ liệu được sinh có tính thời điểm, số ngẫu nhiên hoặc truy vấn luôn thay đổi.
- Một stream đã được mở rồi đưa lại qua lambda `() -> existingStream`.

Lựa chọn thiết kế:

- **Payload nhỏ:** chốt dữ liệu vào `byte[]` và dùng `ofByteArray`.
- **Payload lớn:** spool vào một file/snapshot bất biến có giới hạn trên ổ đĩa, mở `InputStream` mới mỗi attempt.
- **Nguồn có thể tái tạo:** xây lại stream từ cùng dữ liệu đầu vào bất biến, có kiểm tra nội dung và thời điểm.
- **Không thể tái tạo:** thiết kế protocol/policy chấp nhận lỗi nếu cần phát lại, không hứa retry tự động. Có thể từ chối redirect/retry nếu chức năng không cho phép.

Một số trường hợp cần giữ nguyên bản ghi nhận sự kiện, định danh giao dịch hoặc metadata. Bất biến **theo byte** là điều kiện chặt hơn bất biến “nhìn giống nhau”: JSON sinh lại có thể đổi thứ tự trường, timestamp hoặc whitespace; với chữ ký/HMAC, nội dung byte phải được cố định theo đúng hợp đồng giao thức.

## 13. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `() -> sameInputStream` | Lần thứ hai nhận stream đã hết/đóng | Tạo stream mới từ đầu mỗi lần `get()` |
| Tin rằng chỉ có một subscription | Lỗi khi HTTP client cần gửi lại | Supplier phải hoạt động lặp lại, không phụ thuộc số lần gọi |
| Mở lại cùng file nhưng file đang bị thay đổi | Nội dung lần gửi lại khác lần trước | Chốt snapshot bất biến cho toàn workflow |
| Trả `null` rồi tưởng đã upload body rỗng thành công | Request thất bại | Trả stream thật nếu mong retry thành công; báo lỗi khi không có nguồn |
| Nuốt `IOException` rồi trả stream rỗng | Có thể gửi sai dữ liệu | Bọc lỗi thích hợp, fail rõ ràng |
| Tin `available()` là tổng kích thước body | Gắn length không đúng | Dựa trên length đã biết từ nguồn/hợp đồng |
| Thêm `Content-Length` tùy tiện | Mâu thuẫn với byte thực gửi | Dùng BodyPublisher có length chính xác hoặc cơ chế HTTP tự quản |
| Nghĩ stream repeatable làm POST idempotent | Server có thể xử lý trùng nghiệp vụ | Dùng idempotency/deduplication phía server |
| Dùng `readAllBytes` cho file khổng lồ chỉ để retry | Nguy cơ OOME | Dùng snapshot trên đĩa và stream theo khối |
| Xóa file ngay sau `sendAsync` | Supplier mở nguồn thất bại khi body chưa được đọc | Dọn file sau khi hoàn tất mọi attempt |
| Nhầm `BodyHandlers.ofInputStream` là API gửi request | Dùng sai chiều dữ liệu | `BodyPublishers.ofInputStream` để gửi |
| Không test lỗi/cancel/redirect | Rò rỉ nguồn hoặc retry sai | Test các nhánh response, lỗi và vòng đời |
| Tưởng HTTP client luôn retry mọi lỗi | Không dự đoán được kết quả thực | Thiết kế chính sách retry có điều kiện và quan sát thực tế |

## 14. Kiểm thử repeatability và điều kiện production

Một bộ kiểm thử tốt cho `ofInputStream` gồm:

1. **Hai lần xin nguồn** trả hai object stream độc lập và cùng chuỗi byte khi đọc từ đầu.
2. **Nguồn rỗng** được phát đúng như một body 0 byte, không nhầm với trả `null`.
3. **Nguồn lớn** được gửi theo luồng mà không giữ toàn bộ trong heap.
4. **Lỗi mở file** làm request fail rõ, không chuyển thành dữ liệu rỗng.
5. **File thay đổi/xóa** sau attempt đầu: ứng dụng có bảo đảm snapshot hay xử lý lỗi phù hợp.
6. **Redirect/authentication** trên server thử nghiệm: xem body có được yêu cầu lại khi điều kiện giao thức cho phép.
7. **Cancel/timeout** trong lúc đang đọc: tài nguyên và snapshot được xử lý theo workflow.
8. **Retry ứng dụng**: số attempt có giới hạn, payload ổn định, idempotency key không đổi cho cùng nghiệp vụ.
9. **Kết nối chậm/backpressure**: không chạy vô hạn, không giữ dữ liệu/stream không giới hạn.
10. **Tích hợp endpoint thực**: kiểm tra server có chấp nhận body length chưa biết hay yêu cầu Content-Length và định dạng cụ thể.

Đừng kiểm thử bằng cách chỉ gọi `get()` hai lần rồi kết luận mọi redirect và error path đã đúng. Unit test như ví dụ độc lập xác nhận đặc tính nguồn; integration test với HTTP server kiểm chứng phần giao thức. Với dữ liệu nhạy cảm, đừng log toàn bộ request body hoặc token để debug.

## 15. Bài luyện tập

**Bài 1.** Vì sao `ofInputStream(() -> Files.newInputStream(path))` với checked `IOException` không biên dịch ngay trong Java 11?

**Đáp án:** `Supplier.get()` không khai báo `throws IOException`, trong khi `Files.newInputStream` có thể ném checked `IOException`. Cần `try/catch` trong lambda, bọc `UncheckedIOException` hoặc dùng phương án nguồn khác.

**Bài 2.** Một supplier trả cùng `ByteArrayInputStream` đã được tiêu thụ trong lần gửi đầu. Lần thứ hai có thể gửi sai gì?

**Đáp án:** Stream có thể đang ở EOF hoặc đã đóng; lần phát lại không được đảm bảo cung cấp cùng dữ liệu. Tạo **`new ByteArrayInputStream(snapshot)`** mỗi lần `get()`.

**Bài 3.** Một file được mở lại ở mỗi attempt, nhưng tiến trình khác ghi thêm cuối file sau attempt đầu. Có bảo đảm body tương đương không?

**Đáp án:** Không. Mở lại cùng đường dẫn là tạo stream mới, **không** bảo đảm tính bất biến byte. Cần snapshot ổn định hoặc quy trình khóa/version phù hợp.

**Bài 4.** Nếu supplier trả `null` khi HTTP client muốn gửi lại, đó là body rỗng thành công?

**Đáp án:** Không. Theo Javadoc, request **thất bại** khi supplier không cung cấp stream trong attempt tiếp theo.

**Bài 5.** Một POST được client retry cùng byte và cùng idempotency key nhưng server bỏ qua kiểm tra idempotency. Có chắc chắn chỉ tạo một bản ghi?

**Đáp án:** Không. Hỗ trợ idempotency phải tồn tại và được thực thi phía server; chỉ có một header không tự bảo vệ.

**Bài 6.** Nên dùng `ofInputStream` hay `ofByteArray` khi dữ liệu vài KB đã có sẵn trong một mảng byte bất biến?

**Đáp án:** `ofByteArray` thường đơn giản hơn và dễ replay. `ofInputStream` cần thiết khi nguồn có tính streaming hoặc cách tạo nguồn tùy biến.

## 16. Ghi nhớ và tài liệu chính thức

- **`BodyPublishers.ofInputStream` nhận `Supplier<? extends InputStream>`** để có thể xin nguồn mới; nó **không buffer toàn bộ body** phục vụ gửi lại.
- Khi request body cần được gửi lại, `BodyPublisher` có thể có **subscription mới** và phải phát **cùng byte**.
- Supplier tốt cấp **stream mới, đọc từ đầu**; không trả cùng một stream đã tiêu thụ hoặc đóng.
- **Mở stream lại không đồng nghĩa giữ nguyên dữ liệu:** với file hoặc nguồn thay đổi, cần snapshot bất biến.
- **Replayable không đồng nghĩa idempotent.** Retry request có side effect cần chính sách nghiệp vụ và server hỗ trợ chống trùng.
- Không xem `InputStream.available()` là độ dài toàn bộ body; không gắn Content-Length sai.
- Đây là API Java 11 tiếp tục phù hợp trên JDK hiện đại. Chọn `ofFile`, `ofByteArray` hoặc `ofString` nếu nguồn dữ liệu làm những API đó đơn giản và an toàn hơn.

Tài liệu chính thức:

- [`HttpRequest.BodyPublishers` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) — `ofInputStream`, `ofFile`, `ofByteArray`, `ofString`.
- [`HttpRequest.BodyPublisher` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html) — subscription khi cần gửi lại, kỳ vọng cùng body.
- [`HttpRequest` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html) — xây dựng request và body publisher.
- [`InputStream` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html) — đọc, EOF, available, readAllBytes.
- [`HttpRequest.BodyPublishers` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) — đối chiếu API vẫn được hỗ trợ trên JDK hiện đại.
