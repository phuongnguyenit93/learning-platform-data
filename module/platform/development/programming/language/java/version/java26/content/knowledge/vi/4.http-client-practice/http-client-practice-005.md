# Đọc hết, đóng hoặc hủy body để giải phóng tài nguyên

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vòng đời của response body trong `java.net.http.HttpClient`.
- Chọn `BodyHandler` phù hợp với kích thước và cách xử lý dữ liệu.
- Đọc và đóng `InputStream` đúng cách bằng try-with-resources.
- Dùng `discarding()` khi không cần nội dung và phân biệt việc đọc hết với hủy luồng.
- Quản lý backpressure và `Flow.Subscription` khi xử lý body dạng publisher.
- Tránh giữ kết nối, stream hoặc bộ nhớ lâu hơn cần thiết, kể cả khi xử lý response lỗi hay request bất đồng bộ.

## 1. Vì sao response body phải được xử lý đến cùng?

Java 11 đưa `java.net.http.HttpClient` vào Java SE. Đây là HTTP client chuẩn hiện hành của JDK, hỗ trợ HTTP/1.1, HTTP/2 và các kiểu xử lý body đồng bộ hoặc bất đồng bộ. Khi gửi request, ứng dụng nhận một `HttpResponse<T>`; kiểu `T` và vòng đời dữ liệu phụ thuộc vào `BodyHandler<T>` mà ứng dụng chọn.

`HttpClient`, `BodyHandlers` và các API `Flow` được dùng trong bài là API Java SE ổn định; không cần bật preview hoặc thêm module incubator để quản lý response body theo các cách này trên JDK 26.

Body có thể giữ tài nguyên trong lúc dữ liệu đang được truyền hoặc chờ ứng dụng tiêu thụ. Tùy giao thức và cách triển khai, những tài nguyên liên quan có thể gồm:

- Socket hoặc stream của kết nối HTTP.
- Bộ đệm mạng và bộ đệm trong JVM.
- Tài nguyên ghi file hoặc xử lý dữ liệu.
- Vị trí trong connection pool mà client cần để tái sử dụng kết nối.

Nếu ứng dụng lấy một `InputStream` nhưng không đọc hoặc đóng nó, việc tiêu thụ response có thể không kết thúc. Khi tải tăng, nhiều response bị bỏ dở có thể giữ tài nguyên lâu hơn dự kiến, làm giảm khả năng tái sử dụng kết nối và gây chậm hoặc cạn tài nguyên.

Có ba cách kết thúc body thường gặp:

1. **Đọc hết:** tiếp tục đọc đến EOF. Client biết toàn bộ nội dung đã được tiêu thụ.
2. **Đóng:** đóng stream hoặc reader khi không cần đọc tiếp. Việc này kết thúc quyền sử dụng body của ứng dụng và cho phép client giải phóng tài nguyên liên quan.
3. **Hủy subscription:** với body dạng reactive publisher, gọi `Flow.Subscription.cancel()` khi không cần nhận thêm dữ liệu.

Không phải response nào cũng cần ứng dụng tự đóng một stream. Một số `BodyHandler` đọc toàn bộ body trước khi trả kết quả; một số trả về stream để ứng dụng tự quản lý. Vì vậy, cần hiểu kiểu body được chọn thay vì chỉ nhìn vào `HttpResponse`.

## 2. Chọn BodyHandler theo cách sử dụng dữ liệu

`HttpResponse.BodyHandlers` cung cấp các handler phổ biến:

| BodyHandler | Kiểu body trả về | Cách kết thúc và lưu ý |
|---|---|---|
| `ofString(Charset)` | `String` | Đọc hết body trước khi response hoàn tất; toàn bộ nội dung nằm trong heap. |
| `ofByteArray()` | `byte[]` | Đọc hết body vào mảng byte; phù hợp với payload nhỏ, có giới hạn kích thước. |
| `ofFile(Path)` | `Path` | Ghi body vào file; thao tác ghi được quản lý bởi handler và hoàn tất trước khi body stage hoàn tất. Kiểm tra file đích và xử lý file dở dang khi lỗi. |
| `ofInputStream()` | `InputStream` | Trả stream để ứng dụng đọc sau khi nhận response; ứng dụng phải đọc hết hoặc đóng stream. |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Ứng dụng subscribe, yêu cầu dữ liệu theo nhu cầu và cancel nếu dừng sớm. |
| `discarding()` | `Void` | Tiêu thụ và bỏ qua body khi không cần nội dung. |

Các handler dạng `String` hoặc `byte[]` tiện lợi nhưng giữ toàn bộ body trong bộ nhớ. Không nên dùng chúng cho nội dung lớn hoặc kích thước không kiểm soát. Với file lớn, dùng `ofFile`; với xử lý theo từng phần, dùng `ofInputStream` hoặc `ofPublisher`.

Ví dụ, đọc JSON nhỏ thành chuỗi với charset được chỉ định:

~~~java
HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);

int status = response.statusCode();
String body = response.body();
~~~

Khi `send` trả về, handler đã hoàn tất việc đọc body vào `String`. Không cần gọi `close()` trên `HttpResponse` hay trên chuỗi. Tuy nhiên, ứng dụng đã cấp phát bộ nhớ cho nội dung; hãy đặt giới hạn hợp lý cho response mà mình chấp nhận.

## 3. Đọc InputStream và luôn đóng bằng try-with-resources

`BodyHandlers.ofInputStream()` hữu ích khi body lớn hoặc cần xử lý dữ liệu theo luồng. `send()` có thể trả về sau khi header và stream sẵn sàng, trong khi body vẫn còn dữ liệu đang được truyền.

Ví dụ tải body xuống file mà không cần nạp toàn bộ vào heap:

~~~java
HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

Path destination = Path.of("download.bin");

try (InputStream body = response.body();
     OutputStream output = Files.newOutputStream(destination)) {
    body.transferTo(output);
}
~~~

Cần import các kiểu tương ứng từ `java.io`, `java.net.http`, `java.nio.file`. Đoạn code giả định file đích đã được chọn an toàn và có thể ghi. Nếu không muốn ghi đè file hiện có, hãy cấu hình việc tạo file bằng các `OpenOption` phù hợp hoặc kiểm tra đích trước khi tải.

Try-with-resources đảm bảo cả input stream và output stream đều được đóng, kể cả khi `transferTo` hoặc xử lý file ném exception. Khi đọc đến EOF, toàn bộ body đã được tiêu thụ. Nếu ứng dụng dừng trước EOF, đóng input stream sẽ kết thúc việc đọc và hủy phần body còn lại theo cơ chế của client.

### Đọc theo từng khối để xử lý

Không cần sao chép toàn bộ body vào một mảng lớn. Có thể xử lý từng khối:

~~~java
try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];

    for (int count; (count = body.read(buffer)) != -1; ) {
        processChunk(buffer, count);
    }
}
~~~

`processChunk` đại diện cho logic ứng dụng, ví dụ giải mã, kiểm tra định dạng hoặc ghi vào một bộ xử lý khác. Phải xử lý xong dữ liệu trong buffer trước khi ghi đè buffer ở lần đọc kế tiếp. Nếu logic xử lý thất bại, try-with-resources vẫn đóng stream.

Không dùng `InputStream.available()` để kết luận body đã đọc hết. Phương thức này chỉ ước lượng số byte có thể đọc mà không bị chặn; giá trị bằng 0 không đồng nghĩa với EOF.

## 4. Đóng sớm khi chỉ cần một phần body

Có những trường hợp ứng dụng chỉ cần một đoạn đầu của body, ví dụ đọc phần đầu file để kiểm tra định dạng hoặc lấy một đoạn thông tin chẩn đoán. Khi đó, hãy giới hạn số byte đọc và đóng stream ngay khi đã đủ dữ liệu.

~~~java
byte[] prefix;

try (InputStream body = response.body()) {
    prefix = body.readNBytes(4096);
}

// Xử lý prefix sau khi stream đã đóng.
inspectHeader(prefix);
~~~

Đóng sớm kết thúc việc tiêu thụ body ở phía ứng dụng. Phần dữ liệu còn lại sẽ không được ứng dụng đọc. Client có thể phải hủy stream hoặc loại bỏ kết nối tùy giao thức và trạng thái truyền; không nên giả định rằng một response bị đóng giữa chừng luôn giữ được kết nối để tái sử dụng.

Nếu cần bảo đảm body được tái sử dụng kết nối theo đường đọc thông thường, hãy đọc đến EOF. Nếu không cần dữ liệu, dùng `discarding()` để client tiêu thụ body theo handler phù hợp thay vì lấy stream rồi bỏ quên nó.

## 5. Không cần nội dung: dùng discarding()

Một số request chỉ cần status code hoặc header, ví dụ kiểm tra health endpoint hoặc gửi lệnh mà body phản hồi không có ý nghĩa với ứng dụng. Khi đó, dùng `BodyHandlers.discarding()`:

~~~java
HttpResponse<Void> response = client.send(
    request,
    HttpResponse.BodyHandlers.discarding()
);

if (response.statusCode() == 200) {
    // Xử lý kết quả dựa trên status/header.
}
~~~

Handler này tiêu thụ và bỏ qua body, do đó ứng dụng không phải giữ một stream để tự đóng. Đây thường là lựa chọn rõ ràng hơn việc dùng `ofInputStream()` rồi không đọc body.

Không nhầm `discarding()` với việc hủy request ngay lập tức: handler vẫn xử lý body để hoàn tất response. Nếu body rất lớn và ứng dụng thực sự muốn ngừng nhận dữ liệu ngay, hãy cân nhắc hủy stream hoặc subscription; việc đó có thể ảnh hưởng đến khả năng tái sử dụng kết nối.

## 6. Xử lý body trong publisher và Flow

`BodyHandlers.ofPublisher()` trả về một `Flow.Publisher<List<ByteBuffer>>`. Đây là lựa chọn khi muốn điều khiển quá trình nhận body theo backpressure thay vì đọc qua một `InputStream`.

Subscriber nhận subscription trong `onSubscribe`, sau đó phải gọi `request(n)` để yêu cầu dữ liệu. Mỗi lần nhận `onNext`, subscriber xử lý các buffer rồi yêu cầu phần tiếp theo. Nếu không cần phần còn lại, gọi `cancel()`.

Ví dụ khung xử lý:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
    client.send(request, HttpResponse.BodyHandlers.ofPublisher());

response.body().subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(List<ByteBuffer> buffers) {
        try {
            for (ByteBuffer buffer : buffers) {
                while (buffer.hasRemaining()) {
                    byte value = buffer.get();
                    processByte(value);
                }
            }

            if (shouldStop()) {
                subscription.cancel();
                return;
            }

            // Yêu cầu nhóm buffer tiếp theo sau khi xử lý xong nhóm hiện tại.
            subscription.request(1);
        } catch (RuntimeException failure) {
            subscription.cancel();
            handleFailure(failure);
        }
    }

    @Override
    public void onError(Throwable error) {
        handleFailure(error);
    }

    @Override
    public void onComplete() {
        handleComplete();
    }

});
~~~

Các hàm `processByte`, `shouldStop`, `handleFailure` và `handleComplete` là logic do ứng dụng định nghĩa. Trong code thực tế, chỉ gọi `request(1)` khi vẫn muốn nhận dữ liệu; nếu điều kiện xử lý đã đạt, gọi `cancel()` và không yêu cầu thêm.

Lưu ý khi viết subscriber:

- Phải phản hồi `onSubscribe` và yêu cầu dữ liệu nếu muốn body tiếp tục được phát.
- Không yêu cầu lượng dữ liệu vô hạn nếu ứng dụng muốn kiểm soát bộ nhớ và tốc độ xử lý.
- Xử lý exception trong `onNext`; nếu không thể tiếp tục, hủy subscription và ghi nhận lỗi.
- Không giữ các buffer lâu hơn cần thiết; xử lý hoặc sao chép dữ liệu cần giữ theo đúng vòng đời.
- Không giả định `onComplete` sẽ xảy ra sau khi đã gọi `cancel()`. Hủy là kết thúc luồng nhận dữ liệu theo yêu cầu của subscriber.

Với phần lớn ứng dụng, `ofInputStream()` dễ đọc và dễ quản lý hơn. Dùng publisher khi cần tích hợp với pipeline reactive hoặc cần kiểm soát backpressure theo từng phần dữ liệu.

## 7. Xử lý response lỗi cũng phải kết thúc body

`HttpClient` không tự ném exception chỉ vì server trả status 400, 404 hoặc 500. Request có thể hoàn tất bình thường ở tầng HTTP và status được cung cấp qua `response.statusCode()`. Body lỗi vẫn cần được đọc, lưu hoặc bỏ qua.

Ví dụ, khi cần thông báo lỗi ngắn, đọc tối đa một lượng byte giới hạn rồi đóng stream:

~~~java
HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

if (response.statusCode() >= 200 && response.statusCode() < 300) {
    try (InputStream body = response.body()) {
        handleSuccess(body);
    }
} else {
    try (InputStream body = response.body()) {
        byte[] errorPrefix = body.readNBytes(16 * 1024);
        logSafeError(response.statusCode(), errorPrefix);
    }
}
~~~

`handleSuccess` và `logSafeError` là hàm minh họa của ứng dụng. Khi body lỗi dài hơn giới hạn, đóng stream sẽ kết thúc việc đọc phần còn lại. Trước khi ghi nội dung lỗi vào log, cần lọc token, cookie, dữ liệu cá nhân và thông tin nhạy cảm.

Nếu không cần nội dung lỗi, hãy dùng `discarding()` ngay từ đầu. Nếu cần cả body thành công lẫn body lỗi, chọn một handler phù hợp với kích thước và cách xử lý chung; đừng để nhánh status lỗi bỏ quên stream.

## 8. Kết hợp với sendAsync

Với `sendAsync`, kiểu quản lý body không thay đổi. Nếu chọn `ofString`, future chỉ hoàn tất khi handler đã tạo xong chuỗi. Nếu chọn `ofInputStream`, future có thể hoàn tất khi stream sẵn sàng, còn việc đọc và đóng stream thuộc trách nhiệm của ứng dụng.

Ví dụ:

~~~java
CompletableFuture<HttpResponse<InputStream>> pending =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

pending.thenAcceptAsync(response -> {
    try (InputStream body = response.body()) {
        consumeBody(body);
    } catch (IOException error) {
        reportBodyFailure(error);
    }
}, bodyExecutor);
~~~

`bodyExecutor`, `consumeBody` và `reportBodyFailure` do ứng dụng cung cấp. Nên dùng executor phù hợp với công việc đọc/giải mã body, tránh thực hiện xử lý blocking nặng trên executor dành cho các tác vụ khác.

Hủy `CompletableFuture` sau khi future đã hoàn tất và đã trả về một `InputStream` không thay thế cho việc đóng stream đó. Khi ứng dụng đã nhận response, phải quản lý chính body theo handler đã chọn. Với publisher, hủy `Flow.Subscription`; với input stream, đóng stream.

## 9. Ảnh hưởng đến kết nối và connection pool

HTTP client có thể tái sử dụng kết nối đã thiết lập cho các request tiếp theo khi điều kiện giao thức cho phép. Việc tiêu thụ body ảnh hưởng đến thời điểm một response được xem là hoàn tất và khả năng dùng lại tài nguyên truyền tải.

- **Đọc hết body:** client biết toàn bộ nội dung response đã được tiêu thụ. Kết nối có thể được tái sử dụng nếu giao thức, server và trạng thái kết nối cho phép.
- **Đóng stream sớm:** ứng dụng ngừng đọc. Client giải phóng hoặc hủy tài nguyên body; kết nối HTTP/1.1 có thể phải bị loại bỏ nếu không thể đồng bộ tới cuối response. Với HTTP/2, stream có thể được hủy trong khi kết nối nền vẫn phục vụ các stream khác.
- **Cancel publisher:** subscriber báo không cần thêm dữ liệu. Client có thể dừng việc truyền body cho stream đó theo cơ chế của giao thức.
- **Discard body:** handler đọc và bỏ dữ liệu, cho phép hoàn tất quá trình tiêu thụ mà không lưu nội dung trong ứng dụng.

Đóng body không bảo đảm kết nối luôn được tái sử dụng. Server có thể đóng kết nối, response có thể yêu cầu đóng, lỗi mạng có thể xảy ra hoặc giao thức có thể cần hủy stream. Mục tiêu là kết thúc đúng vòng đời body để client có cơ hội quản lý tài nguyên một cách chính xác.

Cũng cần phân biệt body với chính `HttpClient`: response body được quản lý theo `BodyHandler` và kiểu body trả về. `HttpResponse` không phải tài nguyên mà ứng dụng đóng bằng `response.close()`; không có API như vậy trong mô hình response này. Ở các JDK hiện hành, `HttpClient` có vòng đời riêng, nhưng đóng client khi ứng dụng kết thúc không thay thế việc đóng các body stream đang mở.

## 10. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả có thể xảy ra | Cách xử lý |
|---|---|---|
| Lấy `ofInputStream()` rồi bỏ qua body | Stream hoặc tài nguyên kết nối bị giữ lâu. | Đọc đến EOF hoặc đóng stream bằng try-with-resources. |
| Đọc một phần rồi rời khỏi nhánh xử lý | Body còn dang dở. | Đóng stream trong mọi nhánh, kể cả khi xử lý lỗi. |
| Dùng `ofString()` cho file rất lớn | Heap tăng cao, có thể gây áp lực GC hoặc `OutOfMemoryError`. | Dùng `ofFile()` hoặc xử lý streaming. |
| Không subscribe hoặc không request dữ liệu từ publisher | Body không được tiêu thụ theo nhu cầu subscriber. | Subscribe, gọi `request(n)` và cancel khi dừng. |
| Subscriber gặp lỗi nhưng không cancel | Luồng nhận dữ liệu có thể tiếp tục giữ tài nguyên. | Hủy subscription khi không thể tiếp tục và xử lý lỗi. |
| Chỉ xử lý body khi status thành công | Response lỗi bị bỏ quên body. | Dùng handler phù hợp cho cả nhánh thành công và lỗi; đọc, đóng hoặc discard. |
| Hủy future nhưng quên stream đã nhận | Body stream vẫn có vòng đời riêng. | Đóng stream sau khi response đã được giao cho ứng dụng. |

## 11. Checklist trước khi đưa HTTP client vào production

- [ ] Mỗi response body đều có cách kết thúc rõ ràng: đọc hết, đóng hoặc cancel.
- [ ] Stream và reader được đặt trong try-with-resources.
- [ ] Handler phù hợp với kích thước tối đa của payload.
- [ ] Body lỗi cũng được xử lý, không chỉ body của status 2xx.
- [ ] Nội dung log được lọc để không lộ thông tin nhạy cảm.
- [ ] Publisher tuân thủ backpressure và hủy subscription khi dừng sớm.
- [ ] Xử lý body bất đồng bộ dùng executor phù hợp.
- [ ] Kiểm tra tải lặp lại để phát hiện tăng số kết nối, socket hoặc bộ nhớ theo thời gian.

## Kết luận

Trong `java.net.http.HttpClient`, vòng đời response body phụ thuộc vào `BodyHandler` được chọn. Handler tạo `String`, `byte[]`, file hoặc giá trị discard sẽ tự quản lý việc tiêu thụ body theo cách của nó; handler trả `InputStream` yêu cầu ứng dụng đọc hết hoặc đóng stream; handler trả publisher yêu cầu subscriber quản lý demand và cancel khi không cần dữ liệu nữa. Xử lý body đúng cách giúp giải phóng tài nguyên kịp thời, tránh giữ kết nối không cần thiết và duy trì khả năng phục vụ ổn định dưới tải.

## Tài liệu tham khảo

- [Java 26 API – HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 26 API – HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java 26 API – HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java 26 API – Flow](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.html)
- [Java 26 API – InputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html)
- [JEP 321: HTTP Client (Standard)](https://openjdk.org/jeps/321)
