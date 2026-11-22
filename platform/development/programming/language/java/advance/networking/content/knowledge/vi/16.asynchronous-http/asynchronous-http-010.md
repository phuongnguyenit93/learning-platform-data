# Đóng HttpClient sau khi các yêu cầu và nội dung đang truyền được xử lý

Một `java.net.http.HttpClient` có thể dùng chung cho nhiều yêu cầu HTTP, tận dụng pool kết nối và thực hiện các tác vụ `sendAsync()` trên nền. Nhưng “Future đã hoàn tất” **không phải lúc nào cũng có nghĩa toàn bộ response body đã được tiêu thụ**, và “đóng HttpClient” không nên được hiểu đơn giản là đóng một socket. Muốn dừng ứng dụng an toàn, cần điều phối **vòng đời request, response-body stream, subscriber, executor, connection và client**.

Bài Knowledge này tập trung vào **HTTP bất đồng bộ trong Java 17+**, đồng thời chỉ rõ sự khác nhau của JDK:

- **Java 11–20, bao gồm Java 17:** `HttpClient` **chưa triển khai `AutoCloseable`** và **không có** các phương thức `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination()`, `isTerminated()` của API mới. Không sao chép ví dụ `try (HttpClient client = ...)` từ Java 21 vào project Java 17: nó không biên dịch.
- **Java 21 trở lên:** `HttpClient` **triển khai `AutoCloseable`**, có `close()`/`shutdown()`/`awaitTermination(Duration)`/`shutdownNow()`/`isTerminated()`. Implementation tích hợp của JDK cung cấp shutdown **best-effort**. `close()` bắt đầu đóng có trật tự và **chờ** các hoạt động liên quan hoàn tất; nếu body stream còn mở hoặc publisher không được yêu cầu dữ liệu, nó có thể phải chờ rất lâu.
- **Với cả hai nhóm phiên bản:** phải xử lý đầy đủ body hoặc hủy/đóng nó theo đúng `BodyHandler`, quản lý `CompletableFuture`/deadline, và chỉ giải phóng tài nguyên sau khi đã có chính sách cho mọi tác vụ in-flight.

Bài gồm **hai ví dụ chạy độc lập**: ví dụ Java 17 điều phối `sendAsync + ofString + ofInputStream + ofPublisher` trên một server loopback; ví dụ Java 21+ dùng shutdown có thời hạn sau khi nhận đủ response. Mỗi ví dụ có kết quả stdout được kiểm chứng trên JDK mới tương thích với những API đang dùng.

## 1. Vòng đời đúng: không đóng khi còn trao đổi dữ liệu

Hãy tách ít nhất năm khái niệm:

| Tầng | Đơn vị cần quản lý | Điều kiện hoàn thành |
| --- | --- | --- |
| Yêu cầu | `HttpRequest`, upload `BodyPublisher` | Request không còn cần phát bytes, hoặc đã có quyết định cancel/abort |
| Kết quả | `CompletableFuture<HttpResponse<T>>` | Stage hoàn tất thành công/thất bại; ý nghĩa về body tùy `BodyHandler<T>` |
| Nội dung response | `String`, `InputStream`, `Stream<String>`, `Flow.Publisher<List<ByteBuffer>>`… | Body đã tiêu thụ đến EOF/terminal signal, hoặc đã đóng/cancel rõ ràng |
| Client/transport | `HttpClient`, HTTP/1.1 connection pool, HTTP/2 streams | Không còn request được nhận mới; các hoạt động cũ đã giải quyết; tài nguyên được thu hồi theo API/JDK |
| Executor ứng dụng | `ExecutorService` nếu code tự tạo và cấp vào client | Tác vụ thuộc executor đã hoàn thành/hủy, executor được shutdown theo ownership |

Mẫu điều phối lý tưởng:

~~~text
Ứng dụng vẫn đang phục vụ
     |
     v
[RUNNING] nhận request mới; sendAsync(...)
     |
     | yêu cầu dừng có trật tự
     v
[QUIESCING] ngừng tạo/nhận công việc HTTP mới
     |
     v
[DRAINING] đợi các request cũ + BODY CONSUMER kết thúc
     |            |
     |            +-- body nhỏ ofString/ofByteArray: future hoàn tất sau khi body đã gom
     |            +-- ofInputStream/ofLines: đọc EOF hoặc close
     |            +-- ofPublisher: subscribe 1 lần, request đến terminal hoặc cancel
     |            +-- custom subscriber: cấp demand/hoàn tất hoặc cancel
     |
     v
[CLOSING] Java 21+: shutdown/awaitTermination hoặc close
     |         Java 17: không có HttpClient.close(); cleanup streams,
     |                  futures, executor sở hữu và thả tham chiếu phù hợp
     v
[TERMINATED hoặc STOPPED BY POLICY]
~~~

Nguyên tắc: **dừng nhận công việc mới trước, giải quyết công việc đã nhận, xử lý body còn đang truyền, rồi mới shutdown client/transport**. Nếu bạn đóng client trước rồi đợi một subscriber đang chờ có dữ liệu nhưng chưa gọi `request(1)`, bạn có thể tạo vòng chờ không tiến triển.

Tách biệt **ứng dụng không còn dùng client** với **JDK đã giải phóng hoàn toàn mọi socket ngay lập tức**. API có thể thực hiện việc dọn tài nguyên bất đồng bộ, đặc biệt khi hủy request ở giữa đường truyền; không dùng `future.isDone()` như chứng cứ kernel đã đóng tất cả connection.

## 2. Đối chiếu Java 17 và Java 21+: khác biệt API bắt buộc

| API/vấn đề | Java 17 | Java 21+ |
| --- | --- | --- |
| Tạo và tái sử dụng `HttpClient.newBuilder().build()` | Có | Có |
| `HttpClient.sendAsync()` trả `CompletableFuture<HttpResponse<T>>` | Có | Có |
| `HttpClient implements AutoCloseable` | **Không** | **Có** |
| `HttpClient.close()` | **Không** | **Có**, có thể chờ rất lâu |
| `HttpClient.shutdown()` | **Không** | **Có**, khởi động orderly shutdown, không đợi |
| `HttpClient.awaitTermination(Duration)` | **Không** | **Có**, đợi có giới hạn khi đã shutdown |
| `HttpClient.shutdownNow()` | **Không** | **Có**, thử dừng ngay; best-effort |
| `HttpClient.isTerminated()` | **Không** | **Có**, trạng thái sau shutdown |
| `InputStream.close()` cho `BodyHandlers.ofInputStream()` | Có và cần khi không đọc hết | Có và vẫn cần |
| `Flow.Subscription.cancel()` cho `ofPublisher()` | Có và cần khi không tiêu thụ tiếp | Có và vẫn cần |

Ví dụ **không biên dịch trên Java 17**:

~~~java
// Java 21+ ONLY; KHÔNG biên dịch với --release 17.
try (HttpClient client = HttpClient.newHttpClient()) {
    // Gửi/nhận HTTP và tiêu thụ hết body trước khi thoát.
} // client.close() khi thoát try.
~~~

Ví dụ **hợp lệ trên Java 17**:

~~~java
// Java 17+; HttpClient là tài nguyên chia sẻ, không AutoCloseable ở Java 17.
HttpClient client = HttpClient.newHttpClient();

// Điều phối sendAsync, tiêu thụ/đóng response body.
// Không thể gọi client.close()/shutdown() bằng API Java 17.
~~~

Trong Java 17, việc không có `close()` ở client **không miễn trừ trách nhiệm** cleanup `InputStream`/`Stream`/Flow Subscription và các executor do ứng dụng sở hữu. Tuy nhiên cũng không nên tuyên bố “đóng body xong thì client lập tức đóng pool kết nối”: HttpClient có thể giữ connection để tái sử dụng và tài nguyên nội bộ được thu hồi theo cơ chế runtime.

Đối với Java 21+, Javadoc nói rõ **implementation tích hợp của JDK** override các phương thức shutdown. `HttpClient` là lớp abstract và các phương thức shutdown có default implementation; không mặc định custom subclass luôn quản lý tài nguyên tốt như built-in client.

## 3. Future hoàn tất: phải biết BodyHandler nào đang dùng

`sendAsync(request, bodyHandler)` trả về `CompletableFuture<HttpResponse<T>>`. Ý nghĩa “response đã sẵn sàng” khác nhau theo kiểu `T`.

| Handler | Kiểu kết quả `T` | Khi response Future hoàn tất, body đã được xử lý hết? | Việc cần làm tiếp |
| --- | --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `String` | Thông thường **có**, vì handler gom toàn bộ body trước khi trả | Parse/validate, xử lý nghiệp vụ |
| `BodyHandlers.ofByteArray()` | `byte[]` | Thông thường **có**, nếu exchange thành công | Giải mã/ghi xử lý; lưu ý memory |
| `BodyHandlers.ofFile(path)` | `Path` | Thông thường handler đã xử lý/ghi body đến khi hoàn tất | Kiểm tra file, đóng tài nguyên khác theo design |
| `BodyHandlers.discarding()` | `Void` | Body được đọc và bỏ theo handler khi exchange hoàn thành | Kiểm tra status hoặc side effects |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Không nhất thiết**; có thể trả response ngay sau headers | Đọc tới EOF hoặc `close()` |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Không nhất thiết**; đọc stream lines tiếp sau | Tiêu thụ hoặc `Stream.close()` |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Không**; publisher có thể còn toàn bộ body chờ subscriber | Subscribe đúng một lần, request đến `onComplete/onError` hoặc `cancel()` |
| Custom `BodyHandler/BodySubscriber<T>` | Phụ thuộc implementation | **Phụ thuộc thời điểm `getBody()` stage hoàn thành** | Tuân theo contract riêng và resource ownership |

**Bẫy thường gặp:**

~~~java
CompletableFuture<HttpResponse<InputStream>> f =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = f.join();
// join() ở đây không bảo đảm body InputStream đã được đọc tới EOF.
// Nếu ứng dụng bỏ response.body() không đọc/close, exchange có thể giữ tài nguyên.
~~~

Một phản ví dụ khác:

~~~java
CompletableFuture<HttpResponse<Flow.Publisher<List<ByteBuffer>>>> f =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofPublisher());

CompletableFuture.allOf(f).join();
// Chỉ chứng minh response Future đã complete.
// Chưa chắc publisher được subscribe, chưa chắc onComplete đã chạy.
~~~

Với handler streaming, **cần stage/trạng thái thứ hai** theo dõi nội dung: completion signal của subscriber, kết thúc đọc InputStream hoặc xử lý close/error.

Không dùng `HttpResponse.statusCode()==200` như chứng cứ body đã đọc: status và headers có thể tới trước, còn body vẫn streaming hoặc bị lỗi sau đó.

## 4. Quản lý nhiều sendAsync() bằng CompletableFuture.allOf()

Khi body được gom đầy đủ bởi handler, bạn có thể đợi nhiều request bất đồng bộ:

~~~java
// Fragment Java 17+, client/request1/request2 đã có.
CompletableFuture<HttpResponse<String>> first =
        client.sendAsync(
                request1,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

CompletableFuture<HttpResponse<String>> second =
        client.sendAsync(
                request2,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

CompletableFuture<Void> all = CompletableFuture.allOf(first, second);
all.orTimeout(10, TimeUnit.SECONDS).join();

System.out.println(first.join().statusCode());
System.out.println(second.join().statusCode());
~~~

Dùng `allOf()` khi cần cả hai exchange hoàn tất. Với `ofString`, response body đã được materialize trước khi Future thành công. **Nhưng**:

- `allOf()` hoàn thành exceptionally nếu một future thành phần thất bại. Điều đó **không phải cam kết tất cả future còn lại đã được hủy**. Khi shutdown phải kiểm tra/giải quyết tất cả công việc còn active.
- `join()` có thể ném `CompletionException`, không chỉ `IOException`. Cần lấy nguyên nhân thực bằng `getCause()` khi log/xử lý lỗi.
- Nếu `allOf(...).orTimeout(...)` hết hạn, nó hoàn tất future tổng hợp theo timeout; các future request thành phần **không tự động bị cancel**. Bạn cần chính sách rõ với từng request còn pending.
- Nếu phía ứng dụng có các stage tiếp theo như parse JSON, ghi DB, cập nhật cache hoặc stream ra file, `allOf(first,second)` **không chờ những stage được tạo riêng**. Hãy chờ các `CompletableFuture<Void> processingFutures` đại diện **toàn bộ công việc cần thiết**, không chỉ các response future gốc.
- `Future.isDone()` bao gồm cả thành công/thất bại/cancel, không đồng nghĩa thành công. `isCompletedExceptionally()` và xử lý `join/get` giúp phân loại.

### allOf khác “đợi đủ nghiệp vụ”

~~~text
sendAsync(A) ----> response HTTP đầy đủ --+--> parse A ---> save A
                                         |
sendAsync(B) ----> response HTTP đầy đủ --+--> parse B ---> save B

allOf(sendAsync(A), sendAsync(B))  = chỉ đợi ở dấu +.
allOf(save(A), save(B))            = đợi các stage lưu hoàn tất,
                                    nếu được nối/chuyển lỗi đúng cách.
~~~

Ví dụ chuỗi phụ thuộc:

~~~java
// Fragment: saveResult là helper trả CompletionStage<Void>.
CompletableFuture<Void> processed =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .thenCompose(response -> saveResult(response.statusCode(),
                                            response.body()))
        .toCompletableFuture();

// Chờ processed nếu điều kiện shutdown cần cả saveResult hoàn tất.
processed.join();
~~~

Đừng nhét tác vụ blocking dài vào callback của HttpClient nếu executor đó có số thread hạn chế; có thể dùng `thenApplyAsync/thenComposeAsync` với executor ứng dụng được giới hạn, đồng thời quản lý lifecycle của executor này.

## 5. Đọc hết hoặc đóng InputStream từ BodyHandlers.ofInputStream()

`BodyHandlers.ofInputStream()` trả về một `InputStream` phục vụ stream body **sau khi response headers có thể đã đến**. Tài liệu Java 17 nói người gọi **bắt buộc** đọc đến EOF **hoặc** gọi `InputStream.close()` nếu không muốn/không thể đọc tiếp.

Mẫu đọc thành công:

~~~java
// Fragment Java 17+, input/URI/client đã được cấu hình.
CompletableFuture<HttpResponse<InputStream>> pending =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = pending.join();
try (InputStream body = response.body()) {
    // Đây chỉ phù hợp body NHỎ, có hạn mức được xác minh.
    byte[] all = body.readAllBytes();
    processBytes(all);
}
~~~

**Với response lớn**, không dùng `readAllBytes()` vô giới hạn. Đọc từng buffer cố định và chuyển ra file/decoder có giới hạn:

~~~java
// Fragment: xử lý streaming bằng buffer cố định.
// outputStream là sink do ứng dụng sở hữu, sẽ được đóng ở lớp tương ứng.
try (InputStream body = response.body()) {
    byte[] chunk = new byte[8192];
    int n;
    long total = 0;
    long maxBytes = 20L * 1024 * 1024;

    while ((n = body.read(chunk)) != -1) {
        if (n > maxBytes - total) {
            throw new IOException("Response body exceeds size limit");
        }
        outputStream.write(chunk, 0, n);
        total += n;
    }
}
~~~

Nếu mạng hoặc server ngừng gửi trong lúc body chưa EOF, việc đọc stream có thể block; thiết kế cần **deadline tổng, timeout hoạt động và quyết định cancel/close**, không chỉ đặt một timeout nhỏ cho `CompletableFuture<HttpResponse<InputStream>>` nhận headers.

### Nếu chỉ đọc một phần body rồi bỏ đi?

Phải gọi `body.close()`; nếu không, connection có thể còn giữ dữ liệu chưa tiêu thụ. Đóng stream có thể khiến connection HTTP/1.1 bị ngắt và không thể reuse; với HTTP/2, stream có thể bị reset/tác động ở mức protocol. Đây là đánh đổi có chủ đích, tốt hơn việc âm thầm rò rỉ body stream hoặc giữ client shutdown mãi.

Nếu dùng `BodyHandlers.ofLines()`, body là `Stream<String>`. Cũng phải **duyệt hết hoặc close stream**, không để stream dang dở và coi `sendAsync().join()` đã làm xong mọi việc. Một Stream không giống body `String` đã gom xong.

## 6. Đóng vòng đời Publisher và Subscription của HTTP body

Với `BodyHandlers.ofPublisher()`:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofPublisher())
                .join();

Flow.Publisher<List<ByteBuffer>> body = response.body();
body.subscribe(mySubscriber);
~~~

Publisher này cần được subscribe **đúng một lần** theo hợp đồng JDK. Subscriber phải:

1. Nhận `onSubscribe(subscription)`.
2. Gọi `subscription.request(n)` với **n > 0** để cho phép nhận các `List<ByteBuffer>`. `request(1)` là **một item List**, không phải một byte.
3. Xử lý từng `onNext(batch)`, có thể ghi ra file, parse hoặc forward downstream. Khi sẵn sàng nhận thêm thì `request(n)` tiếp.
4. Khi `onComplete()`, đánh dấu body đã đọc xong; khi `onError(error)`, báo thất bại và dọn tài nguyên.
5. Nếu quyết định dừng trước EOF hoặc deadline hết, gọi `subscription.cancel()` và không tiếp tục đợi `onComplete`, vì **cancel không bắt buộc phát terminal callback**.

### Anti-pattern: Publisher không có demand

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    // Sai nếu đợi onComplete nhưng không bao giờ request dữ liệu:
    // publisher có thể chưa thể phát và dẫn tới shutdown treo.
}
~~~

Đây là **fragment** của một subscriber, không phải chương trình độc lập. `HttpClient.close()` Java 21+ có thể phải chờ outstanding request mà body publisher không bao giờ được demand. Tài liệu chính thức gọi đích danh cả `ofInputStream`/`ofLines`/`ofPublisher` và custom BodySubscriber không request/cancel là nguyên nhân orderly shutdown có thể **stall**.

### Dùng CompletableFuture theo dõi riêng completion của body

~~~java
// Fragment Java 17+; bodyPublisher là Flow.Publisher<List<ByteBuffer>>.
CompletableFuture<Void> bodyFinished = new CompletableFuture<>();
AtomicReference<Flow.Subscription> active = new AtomicReference<>();

bodyPublisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    @Override
    public void onSubscribe(Flow.Subscription s) {
        active.set(s);
        s.request(1);
    }

    @Override
    public void onNext(List<ByteBuffer> batch) {
        try {
            for (ByteBuffer buffer : batch) {
                handleChunk(buffer); // Helper: xử lý đồng bộ hoặc có backpressure.
            }
            active.get().request(1);
        } catch (Throwable failure) {
            Flow.Subscription s = active.get();
            if (s != null) s.cancel();
            bodyFinished.completeExceptionally(failure);
        }
    }

    @Override
    public void onError(Throwable failure) {
        bodyFinished.completeExceptionally(failure);
    }

    @Override
    public void onComplete() {
        bodyFinished.complete(null);
    }
});
~~~

Đây là **fragment**: `handleChunk`, imports và những phần quản lý timeout/response thuộc ứng dụng. Nếu hết thời hạn chờ `bodyFinished` mà chưa terminal, **cancel subscription**, rồi giải quyết future theo nhánh “đã hủy”, không đợi onComplete mãi. Với sink bất đồng bộ, không nên `request(1)` ngay sau khi chỉ xếp queue nếu chưa có backpressure end-to-end: cần chờ sink xử lý xong hoặc giữ queue bounded.

Lưu ý `onNext(List<ByteBuffer>)` phát một danh sách các buffer chỉ-đọc; bytes có thể bị chia bất kỳ, không tương ứng message nghiệp vụ hay ký tự UTF-8. Khi giải mã text hãy giữ decoder state hoặc ghép bytes theo giới hạn. Không tăng bộ nhớ vô hạn bằng việc gom tất cả vào `ByteArrayOutputStream` mà vẫn gọi nó là “streaming bounded memory”.

## 7. Java 21+: close(), shutdown(), awaitTermination(), shutdownNow()

Các phương thức mới này **được bổ sung từ Java 21**.

### close() — shutdown có trật tự và chờ tới khi hoàn tất

~~~java
// Java 21+ ONLY. Trước khi thoát try, mọi body cần được drain/close/cancel.
try (HttpClient client = HttpClient.newHttpClient()) {
    CompletableFuture<HttpResponse<String>> future =
            client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

    HttpResponse<String> response = future.join();
    consumeResult(response);
} // close() thực hiện orderly shutdown và đợi client terminated.
~~~

Đây là **fragment** cần `request` và `consumeResult`. Điểm nhấn: `try-with-resources` tự gọi `close()` khi ra khỏi block, nhưng **không tạo deadline hữu hạn** cho việc đợi các body chưa xử lý. Khi request có body dạng Publisher không được request, close có thể chờ kéo dài. `close()` là cơ chế **blocking** để kết thúc, không phải `shutdownNow()`.

Trong trường hợp thread đợi `close()` bị interrupt, API cho phép nó thử gọi `shutdownNow()` rồi tiếp tục đợi tới khi các hoạt động kết thúc; sau đó cờ interrupt được khôi phục. Đừng dựa vào interrupt như một “timeout đóng client luôn xong ngay”.

### shutdown() — không nhận request mới, cho request cũ cơ hội hoàn tất

~~~java
// Java 21+ ONLY.
client.shutdown();
// Không gửi request mới qua client này.
// Các request đã submit và body consumer phải tiếp tục hoàn tất.
~~~

`shutdown()` **không đợi**. Nó mở đầu orderly shutdown: request cũ vẫn có thể cần đọc response, gọi subscriber demand, ghi file hoặc chờ network. Nếu caller ngừng chạy mọi body consumer ngay sau shutdown, pipeline có thể không hoàn thành.

### awaitTermination(Duration) — đợi có thời hạn

~~~java
// Java 21+ ONLY; dùng sau shutdown() hoặc shutdownNow().
client.shutdown();

boolean terminated =
        client.awaitTermination(Duration.ofSeconds(10));

if (!terminated) {
    // Chưa hoàn thành trong 10 giây; cần chính sách escalation.
    client.shutdownNow(); // best-effort, không bảo đảm dừng ngay.
}
~~~

`awaitTermination(Duration)` trả về `true` nếu đã terminated, `false` nếu timeout trước; có thể ném `InterruptedException`. Nếu duration ≤ 0, nó thực hiện kiểm tra trạng thái tức thời, không chờ. `isTerminated()` có ý nghĩa sau khi shutdown; trước đó nó không được kỳ vọng trả true chỉ vì hiện không có request nào.

### shutdownNow() — hủy mạnh hơn nhưng KHÔNG phải “kill chắc chắn”

~~~java
// Java 21+ ONLY, dành cho forced-stop khi đã quá deadline.
client.shutdownNow();
boolean stopped =
        client.awaitTermination(Duration.ofSeconds(2));
if (!stopped) {
    reportStillRunning(); // Helper của ứng dụng: ghi nhận cleanup chưa xong.
}
~~~

Theo Javadoc, `shutdownNow()` **attempts** immediate shutdown, có thể interrupt hoạt động đang chạy. Hành vi của operation đang bị interrupt **không xác định** và không bảo đảm các operation sẽ kết thúc hay các thread đang chờ nhận notification. Do đó:
- Đừng tuyên bố `shutdownNow()` luôn giải phóng socket trong đúng 2 giây.
- Đừng giả định một POST/upload đã bị rollback ở server.
- Không reuse client đã shutdown cho request mới.
- Nếu thời hạn đã cạn mà `isTerminated()==false`, cần báo trạng thái không chắc chắn, quyết định chính sách đóng process/health/readiness theo hệ thống.

### Ưu tiên thứ tự bình thường

~~~text
1) Ngừng accept/create công việc HTTP mới
2) Chờ toàn bộ processing futures với deadline tổng
3) Drain hoặc close/cancel mọi body stream chưa hoàn tất
4) client.shutdown()
5) client.awaitTermination(gracePeriod)
6) Nếu quá hạn: cancel pending, client.shutdownNow() (best-effort)
7) awaitTermination(shortFollowUp) và ghi nhận còn hoạt động nếu chưa xong
8) Thu hồi executor/app resources do ứng dụng sở hữu
~~~

Với ứng dụng nhỏ có giới hạn rõ ràng và không có body streaming bị bỏ quên, `try-with-resources HttpClient` có thể là cách ngắn gọn. Với server lớn cần thời hạn dừng, `shutdown()/awaitTermination()/shutdownNow()` cung cấp khả năng đo/điều phối thay vì chỉ gọi close rồi chờ vô hạn.

## 8. Java 17+ — chương trình hoàn chỉnh xử lý xong request và streaming body

Ví dụ này dùng `com.sun.net.httpserver.HttpServer` trên `127.0.0.1` cổng động để mô phỏng bốn endpoint: hai response String, một response InputStream, một response Flow Publisher. Chương trình minh họa **đợi body thật sự** trước khi kết thúc lifecycle phía ứng dụng trên **Java 17**; không gọi bất kỳ method `HttpClient.close/shutdown` nào vì chúng chưa tồn tại ở JDK 17.

Lưu đúng tệp **`AsyncCloseLessonDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncCloseLessonDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final long WAIT_SECONDS = 5;

    private static void reply(HttpExchange ex, String text)
            throws IOException {
        try (InputStream ignored = ex.getRequestBody()) {
            byte[] bytes = text.getBytes(UTF8);
            ex.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            ex.sendResponseHeaders(200, bytes.length);

            try (OutputStream out = ex.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static HttpRequest get(String root, String path) {
        return HttpRequest.newBuilder(
                    URI.create(root + path))
                .timeout(Duration.ofSeconds(WAIT_SECONDS))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/one", ex -> reply(ex, "ONE"));
        server.createContext("/two", ex -> reply(ex, "TWO"));
        server.createContext("/stream",
                ex -> reply(ex, "STREAM"));
        server.createContext("/publisher",
                ex -> reply(ex, "PUBLISH"));
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            // Java 17: không try-with-resources HttpClient,
            // không close()/shutdown() trên HttpClient.
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            // A: Hai HTTP exchanges gom body đầy đủ vào String.
            CompletableFuture<HttpResponse<String>> first =
                    client.sendAsync(
                            get(root, "/one"),
                            HttpResponse.BodyHandlers.ofString(UTF8));

            CompletableFuture<HttpResponse<String>> second =
                    client.sendAsync(
                            get(root, "/two"),
                            HttpResponse.BodyHandlers.ofString(UTF8));

            CompletableFuture.allOf(first, second)
                    .orTimeout(WAIT_SECONDS, TimeUnit.SECONDS)
                    .join();

            System.out.println(
                    "first=" + first.join().body());
            System.out.println(
                    "second=" + second.join().body());

            // B: Future<InputStream> có thể xong sau headers,
            // body vẫn cần đọc EOF hoặc close().
            HttpResponse<InputStream> streamResponse =
                    client.sendAsync(
                            get(root, "/stream"),
                            HttpResponse.BodyHandlers.ofInputStream())
                    .orTimeout(WAIT_SECONDS, TimeUnit.SECONDS)
                    .join();

            try (InputStream input = streamResponse.body()) {
                // Response này chỉ có 6 byte do server demo kiểm soát.
                // KHÔNG dùng readAllBytes vô hạn cho dữ liệu không tin cậy.
                System.out.println(
                        "stream="
                                + new String(
                                        input.readAllBytes(), UTF8));
            }

            // C: ofPublisher trả response khi headers có sẵn;
            // body phải được subscribe và tiêu thụ riêng.
            HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                    publisherResponse =
                    client.sendAsync(
                            get(root, "/publisher"),
                            HttpResponse.BodyHandlers.ofPublisher())
                    .orTimeout(WAIT_SECONDS, TimeUnit.SECONDS)
                    .join();

            CountDownLatch complete = new CountDownLatch(1);
            AtomicReference<Flow.Subscription> subscription =
                    new AtomicReference<>();
            AtomicReference<Throwable> problem =
                    new AtomicReference<>();
            ByteArrayOutputStream received =
                    new ByteArrayOutputStream();

            publisherResponse.body().subscribe(
                    new Flow.Subscriber<List<ByteBuffer>>() {
                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription.set(s);
                    s.request(1);
                }

                @Override
                public void onNext(List<ByteBuffer> group) {
                    try {
                        for (ByteBuffer buffer : group) {
                            byte[] chunk =
                                    new byte[buffer.remaining()];
                            buffer.get(chunk);
                            received.write(
                                    chunk, 0, chunk.length);
                        }
                        subscription.get().request(1);
                    } catch (Throwable failure) {
                        problem.compareAndSet(null, failure);
                        subscription.get().cancel();
                        complete.countDown();
                    }
                }

                @Override
                public void onError(Throwable failure) {
                    problem.compareAndSet(null, failure);
                    complete.countDown();
                }

                @Override
                public void onComplete() {
                    complete.countDown();
                }
            });

            if (!complete.await(
                    WAIT_SECONDS, TimeUnit.SECONDS)) {
                Flow.Subscription s = subscription.get();
                if (s != null) {
                    s.cancel();
                }
                throw new TimeoutException(
                        "Response publisher not completed");
            }
            if (problem.get() != null) {
                throw new IOException(
                        "Body failed", problem.get());
            }

            System.out.println(
                    "publisher="
                            + new String(
                                    received.toByteArray(), UTF8));
            System.out.println(
                    "requestsAndBodiesFinished=true");

            // Kết thúc sử dụng client ở cấp ứng dụng.
            // Java 17 không có API đóng HttpClient trực tiếp.
        } finally {
            server.stop(0);
        }
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac AsyncCloseLessonDemo.java
java AsyncCloseLessonDemo
~~~

Chương trình sử dụng module JDK `jdk.httpserver` (không cần dependency ngoài). Với cấu hình module-path đặc thù có thể cần thêm `--add-modules jdk.httpserver` ở cả compile/run; ở classpath của JDK thông thường module này được resolve.

**Stdout được kiểm tra trên JDK tương thích qua JShell:**

~~~text
first=ONE
second=TWO
stream=STREAM
publisher=PUBLISH
requestsAndBodiesFinished=true
~~~

Giải thích:

1. Hai `sendAsync(...ofString)` chạy song song về mặt asynchronous API. `allOf` chỉ cho phép in hai String **sau khi cả hai response futures đã hoàn thành thành công**.
2. Response `InputStream` đã có header, nhưng chương trình vẫn vào `try (InputStream ...)` và đọc tới EOF; dù phát sinh exception, stream được đóng.
3. Response `Publisher<List<ByteBuffer>>` được subscribe một lần. `onSubscribe` gọi `request(1)`; `onNext` đọc các ByteBuffer, rồi cấp demand tiếp; `onComplete/onError` đánh dấu kết thúc qua latch. Khi quá hạn, code lấy subscription hiện tại và cancel để không bỏ mặc body.
4. Chương trình chỉ dùng `ByteArrayOutputStream` vì body Publisher cố định 7 byte. Với dữ liệu production lớn, dùng bounded sink, tuyệt đối không tích lũy response không giới hạn trong RAM.
5. `server.stop(0)` dừng server loopback sau khi các thao tác mẫu hoàn tất. Nó **không thay thế** API đóng HttpClient trong Java 21+ và không biến Java 17 client thành AutoCloseable.

**Giới hạn demo:** `orTimeout(5s)` áp lên CompletableFuture tương ứng; nếu timeout trước khi Future hoàn tất, nó **không tự hủy chắc chắn** underlying exchange. Trong demo, endpoint trả body ngắn và luôn hoàn tất nên không phát sinh nhánh hủy. Ngoài môi trường lab, cần lưu và xử lý mọi future pending, có timeout cấp ứng dụng, cancel/close đúng cách và không để các kết nối chậm giữ tài nguyên vô thời hạn. Đoạn InputStream với `readAllBytes()` không đặt timeout độc lập cho *việc tiêu thụ body*, cần kế hoạch cancel/close trong service thật.

## 9. Java 21+: chương trình hoàn chỉnh graceful shutdown có thời hạn

Ví dụ này cần **JDK 21+** vì sử dụng `HttpClient.shutdown()`, `awaitTermination(Duration)` và `shutdownNow()`. Nó tạo server loopback riêng và gửi một HTTP request tới `/done`. Vì response dùng `BodyHandlers.ofString()`, Future thành công nghĩa body String đã được gom xong; sau đó mới shutdown client.

Lưu thành **`HttpClientShutdown21Demo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class HttpClientShutdown21Demo {
    private static void reply(HttpExchange ex)
            throws IOException {
        byte[] body = "DONE".getBytes(StandardCharsets.UTF_8);

        try (InputStream ignored = ex.getRequestBody()) {
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext(
                "/done", HttpClientShutdown21Demo::reply);
        server.start();

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort()
                            + "/done");
            HttpRequest req = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> response =
                    client.sendAsync(
                            req,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));

            System.out.println(
                    "response="
                            + response.get(
                                    5, TimeUnit.SECONDS).body());
        } finally {
            // Java 21+:
            client.shutdown(); // Không nhận yêu cầu mới.
            boolean stopped =
                    client.awaitTermination(Duration.ofSeconds(5));

            if (!stopped) {
                client.shutdownNow(); // Chỉ là best-effort.
                stopped = client.awaitTermination(
                        Duration.ofSeconds(2));
            }

            System.out.println("terminated=" + stopped);
            server.stop(0);
        }
    }
}
~~~

Lệnh biên dịch/chạy JDK 21+:

~~~bash
javac HttpClientShutdown21Demo.java
java HttpClientShutdown21Demo
~~~

**Stdout quan sát trong môi trường kiểm thử loopback JDK 24:**

~~~text
response=DONE
terminated=true
~~~

Kết quả `terminated=true` đúng cho **lần thử** trên: server trả lời ngay, body đã được gom xong, không có stream body nào tồn đọng. Với server chậm, body chưa được đọc hoặc task bị nghẽn, `awaitTermination` có thể trả `false`, và `shutdownNow` **không bảo đảm** lần đợi sau sẽ trả true. Đó là lý do code **in ra kết quả thực tế** thay vì khẳng định shutdown đã thành công chỉ vì đã gọi phương thức.

Mẫu thay thế ngắn gọn khi mọi body được xử lý rõ ràng:

~~~java
// Java 21+ ONLY, phù hợp khi có thể chờ orderly shutdown.
try (HttpClient client = HttpClient.newHttpClient()) {
    // Gửi request, đợi những processing futures,
    // đọc hết/đóng InputStream và Stream,
    // subscribe-drain/cancel mọi Publisher.
} // AutoCloseable.close() được gọi ở đây, có thể chờ không giới hạn.
~~~

**Không chọn cả hai API một cách mù quáng:** khi cần deadline shutdown có đo lường được, dùng `shutdown + awaitTermination + escalation` thay cho `close()` blocking vô điều kiện. Khi dùng try-with-resources, vẫn phải tiêu thụ/đóng tất cả streaming responses trong khối; nếu không, ngay đoạn đóng client cũng có thể dừng tiến triển.

## 10. Executor do ứng dụng sở hữu: thứ tự shutdown

`HttpClient.Builder.executor(Executor)` cho phép định nghĩa executor cho các tác vụ bất đồng bộ/dependent tasks theo contract. Nếu bạn tự tạo `ExecutorService` và đưa vào client, phải có chính sách shutdown **cho executor của chính mình**, tách biệt với client:

~~~java
// Fragment Java 17+; chỉ mô tả ownership, không phải class chạy độc lập.
ExecutorService ioExecutor =
        Executors.newFixedThreadPool(4);
HttpClient client =
        HttpClient.newBuilder().executor(ioExecutor).build();

try {
    // Submit request(s) và body handler(s);
    // chờ toàn bộ công việc liên quan, xử lý/cancel stream.
} finally {
    // Chỉ shutdown khi không còn operation cần sử dụng executor.
    ioExecutor.shutdown();
    if (!ioExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
        ioExecutor.shutdownNow();
    }
}
~~~

**Cảnh báo:** gọi `ioExecutor.shutdown()` quá sớm **trong khi HTTP exchange hoặc body subscriber vẫn chạy** có thể khiến các tác vụ cần executor không được thực thi, làm pipeline treo/thất bại. Với Java 17, shutdown executor **không đồng nghĩa đóng HttpClient connection pool** (API đó không có). Với Java 21+, cũng không nên giả định `HttpClient.close()` sẽ tự đóng một executor sở hữu bên ngoài do ứng dụng cấp vào; quản lý lifecycle của nó riêng.

Đừng dùng một executor đơn thread để vừa chạy HTTP callbacks **vừa block trong `future.get/join()` đang phụ thuộc các callbacks đó**, vì có nguy cơ deadlock/starvation. Một shutdown plan phải tách rõ tác vụ xử lý HTTP, tác vụ nghiệp vụ, queue, callbacks và thread đang đợi.

## 11. Hủy request bất đồng bộ: không có rollback bảo đảm

Với `sendAsync`, `CompletableFuture.cancel(true)` trên future do implementation JDK trả về là **một nỗ lực** hủy HTTP exchange và thu hồi tài nguyên. API không hứa request chưa rời máy hay server chưa xử lý:

~~~java
// Fragment Java 17+, myFuture được trả từ client.sendAsync(...).
if (!myFuture.isDone()) {
    boolean cancelled = myFuture.cancel(true);
    // cancelled là tình trạng Future, không phải xác nhận server rollback.
}
~~~

Theo Javadoc, với HTTP/1.1 việc cancel có thể đóng connection đột ngột; với HTTP/2 có thể reset stream, đôi khi cũng dẫn tới đóng connection trong tình huống nhất định. Nếu upload POST đã tới server trước khi cancel, **server có thể đã hoàn thành side effect**. Không thực hiện retry vô hạn cho các POST thanh toán, tạo đơn hàng, cập nhật dữ liệu khi không có idempotency key/dedup hoặc API trạng thái.

### Request timeout, Future wait timeout và body timeout không đồng nhất

| Nguồn timeout | Ý nghĩa | Điều chưa được bảo đảm |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(d)` | Timeout khi phải mở kết nối mới | Không phải deadline cho đọc body sau khi có connection |
| `HttpRequest.Builder.timeout(d)` | Timeout của HTTP exchange theo API | Với streaming body, code tiêu thụ stream có thể cần deadline riêng |
| `future.get(d, unit)` | Thời gian một thread chờ Future | Không tự cancel underlying exchange |
| `future.orTimeout(d, unit)` | Future này hoàn thành exceptionally nếu chưa xong trước deadline | Không tự chứng minh network operation đã bị hủy |
| `InputStream.read(...)` / `Flow.Subscriber` | Đọc/body processing có thể kéo dài riêng | Không được thay thế bằng chỉ một timeout chờ headers |

Nếu body response được đọc trong worker khác, deadline shutdown phải xét **cả worker/body completion**, không chỉ lấy `responseFuture.isDone()`.

## 12. Kịch bản dừng ứng dụng theo thời hạn tổng

Một service lớn có thể định nghĩa `gracePeriod = 10 s`:

~~~text
T0: nhận SIGTERM / stop event
    |
    +-- Đặt lifecycle = QUIESCING
    +-- Chặn / từ chối NEW sendAsync()
    |
    +-- Snapshot các activeRequestFutures
    |      - những future cần thiết để nhận response
    |      - những bodyCompletionFutures cần để xử lý xong stream
    |      - những processingFutures ghi file/DB/cache
    |
    +-- Đợi với MỘT deadline tổng bằng monotonic clock
    |      - không reset 10 s cho từng stream/client riêng lẻ
    |      - mỗi lần đợi lấy remaining time
    |
    +-- Nếu body đang stream: drain khi hợp lý;
    |      nếu quá hạn/bỏ tác vụ: close InputStream hoặc cancel Subscription
    |
    +-- Java 21+: client.shutdown() và awaitTermination(remaining)
    |
    +-- Nếu chưa terminated: cancel pending / shutdownNow()
    |      - đánh dấu mọi request chưa chắc trạng thái
    |      - chờ bounded follow-up, không giả định hoàn tất
    |
    +-- Đóng các executor sở hữu sau khi HTTP không còn cần chúng
    +-- Cập nhật readiness/liveness, metrics, shutdown result
~~~

Một cách đo remaining time:

~~~java
// Fragment Java 17+.
long deadlineNanos =
        System.nanoTime() + TimeUnit.SECONDS.toNanos(10);

// Tại mỗi điểm chờ:
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0L) {
    // Hết tổng thời hạn; cancel/close và escalation.
} else {
    // Chờ tối đa remainingNanos, không cấp lại 10 s từ đầu.
}
~~~

Sử dụng `System.nanoTime()` để đo thời gian trôi thay vì timestamp wall-clock có thể thay đổi vì đồng bộ giờ. Với thời hạn rất lớn cần tính đến overflow số nguyên và giới hạn duration phù hợp, nhưng grace period ngắn của shutdown thông thường có thể quản lý đơn giản như trên.

**Không đồng nhất “thời gian chờ bằng 0” với “tất cả request đã xử lý xong”.** Khi hết deadline, ứng dụng phải lựa chọn shutdown mạnh hơn, ghi nhận những hoạt động chưa hoàn tất, và không báo thành công giả.

## 13. HTTP streaming có thể làm đóng client treo như thế nào?

### 13.1. Quên close InputStream

~~~java
HttpResponse<InputStream> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofInputStream())
        .join();

// Anti-pattern: không đọc response.body(), không close.
// Response Future xong nhưng body/network exchange có thể vẫn active.
~~~

**Sửa:** trong `try-with-resources InputStream`, đọc đến EOF hoặc close khi không cần nữa. Với response lớn dùng bounded streaming, không tải tất cả vào RAM.

### 13.2. Quên subscribe hoặc không request từ Publisher

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofPublisher())
        .join();

// Anti-pattern: không có body.subscribe(...).
// Không có subscriber để xử lý/cancel body.
~~~

Hoặc subscriber có `onSubscribe` nhưng không gọi `request(n>0)`, khiến body có thể không phát tiếp. **Sửa:** một subscriber đúng lifecycle, cấp demand, xử lý đến `onComplete/onError` hoặc `cancel()` khi bỏ cuộc.

### 13.3. Đóng client trước khi callback phải chạy

~~~java
// Anti-pattern về thứ tự (Java 21+):
client.shutdown();
executor.shutdownNow();
// Một body handler hoặc processing stage còn cần executor đó!
// awaitTermination có thể bị trì hoãn hoặc thất bại.
~~~

**Sửa:** dừng tạo request mới; cho operations và callbacks đang dùng executor hoàn tất hoặc cancel; sau đó shutdown client và executor theo ownership/role. Nếu custom executor phục vụ nhiều subsystem, không shutdown nó chỉ vì một client không còn cần.

### 13.4. `allOf` đúng các response future nhưng sai các body future

~~~java
// Anti-pattern:
CompletableFuture.allOf(responseFutures).join();
client.close(); // Java 21+: body Publisher có thể chưa onComplete.
~~~

**Sửa:** theo dõi thêm body completion stage (hoặc close/cancel). Với `BodyHandlers.ofPublisher`, `responseFuture.join()` mới trả publisher để subscribe; phải tiếp tục đợi completion signal của chính subscriber.

### 13.5. Thời hạn chờ chia nhỏ làm shutdown vượt budget

Nếu một service có 100 request, mỗi request được cấp 10 s **nối tiếp**, tổng chờ có thể lên tới 1.000 s. **Sửa:** đợi đồng thời theo groups/futures, sử dụng một monotonic deadline tổng và thời gian còn lại, sau đó quyết định cancellation/escalation.

### 13.6. Cancel xong chờ onComplete mãi

Theo Flow contract, `Subscription.cancel()` không nhất thiết phát `onComplete()`. **Sửa:** tự hoàn tất state của ứng dụng theo nhánh cancelled, cleanup idempotent, không giữ latch chờ signal không được bảo đảm.

## 14. Hướng dẫn xử lý lỗi khi dừng HTTP bất đồng bộ

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra/hành động |
| --- | --- | --- |
| Java 17: `cannot find symbol: close()` | Dùng API Java 21 với JDK17 | Bỏ close/shutdown trên HttpClient; cleanup từng body/executor; hoặc nâng JDK |
| Java 17: HttpClient không dùng được try-with-resources | Chưa implements AutoCloseable | Quản lý như shared client, không giả định API của Java21 |
| Java 21+: `close()` không trở về | Stream chưa đọc/đóng, Publisher không request/cancel, callback nghẽn | Kiểm tra outstanding body, subscriber, executor; chuyển sang bounded shutdown plan |
| `future.isDone()==true` nhưng còn socket activity | Handler streaming trả response sớm; callback nghiệp vụ còn chạy | Theo dõi body completion/processing futures |
| `get(timeout)` báo quá hạn nhưng request còn chạy | Wait timeout không phải cancel | Cancel future, close/cancel body hoặc shutdown theo policy |
| `allOf` thất bại | Một future thành phần lỗi; future khác có thể vẫn active | Kiểm tra từng future, không mặc định tất cả đã hủy |
| Sau shutdown() vẫn có thread chạy | Shutdown có trật tự không đợi; outstanding requests đang active | awaitTermination với deadline; xử lý streaming và escalation |
| awaitTermination() trả false | Chưa terminated trong thời gian cho phép | shutdownNow best-effort, log những request chưa xử lý, thử bounded follow-up |
| shutdownNow() không dừng hết | API không bảo đảm dừng tức thì | Theo dõi trạng thái/metrics và policy của process; không báo terminated giả |
| Program Java17 không thoát vì custom ExecutorService | Executor có thread non-daemon đang chạy | Chờ task cần thiết, sau đó executor.shutdown và awaitTermination |
| Response ofPublisher() không có onNext | Subscriber chưa request n>0 hoặc không subscribe | Kiểm tra onSubscribe, demand, cancellation |
| Response bị cắt khi close InputStream sớm | Đã chủ động bỏ phần còn lại của body | Chỉ cancel/close sớm khi không cần nội dung; tránh parse body bị cắt như thành công |
| Server nhận POST dù future bị cancel | Request đã được gửi trước khi cancel | Idempotency key / trạng thái nghiệp vụ, không retry bừa |
| CPU/RAM cao khi shutdown | Subscriber buffer vô hạn, callbacks chậm, executor nghẽn | Bounded queues, max body, metrics in-flight, queue depth |
| Connection HTTP/1.1 không reuse sau cancel | Cancel giữa body có thể đóng socket | Đây có thể là hành vi đúng; cân nhắc drain khi chi phí thấp |
| HTTP/2 stream reset sau cancel | Cơ chế hủy ở cấp stream | Xử lý lỗi trên request cụ thể, không đồng nhất toàn client đã đóng |

### Quan sát chính xác bằng metrics

Nên theo dõi:

- `activeRequests`: request đã submit nhưng chưa kết luận success/failure/cancel.
- `activeBodyStreams`: InputStream/Stream/Publisher còn chưa EOF/terminal/close/cancel.
- `inFlightBytes` và `queuedBytes`: tổng bytes đang chờ tiêu thụ hoặc xuất đi.
- `processingFutures`: công việc phụ thuộc response (parse, DB, file, queue).
- `clientLifecycleState`: RUNNING/QUIESCING/DRAINING/SHUTDOWN/TERMINATED.
- `shutdownDuration`, `shutdownGraceExpired`, `forcedCancellationCount` và `responseBodyAbandonedCount`.
- `statusCode`/error class/timeout/correlation ID, tránh log credentials hoặc raw body nhạy cảm.

Một metric chỉ đếm `responseFuture.isDone()` không đủ để xác nhận an toàn khi dừng; cần phản ánh **body chưa kết thúc** và **các tác vụ nghiệp vụ tiếp theo**.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Trên Java 17, đoạn `try (HttpClient client = HttpClient.newHttpClient()) { ... }` có biên dịch không?  
**Đáp án:** Không. `HttpClient` Java 17 chưa implements AutoCloseable. Các API close/shutdown được bổ sung từ Java 21.

**Câu 2.** `HttpClient.close()` Java 21+ có chờ request cũ không?  
**Đáp án:** Có. Nó bắt đầu orderly shutdown và đợi những operations trước đó hoàn tất; nếu body stream chưa đọc/đóng hoặc publisher không request/cancel, có thể chờ rất lâu. Không coi close là timeout bounded mặc định.

**Câu 3.** `HttpClient.shutdown()` có đợi mọi request xong không?  
**Đáp án:** Không. Nó khởi tạo orderly shutdown và không nhận request mới, nhưng trả về ngay; dùng `awaitTermination` hoặc `close` để đợi.

**Câu 4.** `awaitTermination(Duration)` trả false có nghĩa shutdown thất bại vĩnh viễn không?  
**Đáp án:** Không. Nó chỉ nói client chưa terminated trước khi timeout; có thể dần hoàn tất hoặc cần escalation/cancel. Không mặc định kết thúc khi chưa có chứng cứ.

**Câu 5.** `shutdownNow()` có bảo đảm dừng mọi thread/HTTP exchange ngay lập tức không?  
**Đáp án:** Không. Đó là best-effort attempt, hành vi active operations có thể không xác định.

**Câu 6.** `sendAsync(...ofString())` thành công có nghĩa body đã nhận đủ chưa?  
**Đáp án:** Thông thường có, vì `BodyHandler` gom response thành String trước khi future hoàn thành thành công. Vẫn cần kiểm tra status, nội dung, processing tasks.

**Câu 7.** `sendAsync(...ofInputStream())` hoàn tất có nghĩa đã đọc hết body chưa?  
**Đáp án:** Không. Response có thể có ngay sau headers. Phải đọc InputStream tới EOF hoặc close nếu không muốn tiếp tục.

**Câu 8.** `ofPublisher()` trả response nhưng chưa subscribe, có thể bắt đầu Java21 `close()` mà chắc chắn không treo không?  
**Đáp án:** Không. Body có thể chưa chạy, đóng có trật tự có thể bị trì hoãn. Subscribe đúng một lần và request tới terminal hoặc cancel.

**Câu 9.** `subscription.cancel()` có bắt buộc callback `onComplete()` không?  
**Đáp án:** Không. Cancellation là best-effort và không bảo đảm terminal signal; xử lý nhánh canceled riêng.

**Câu 10.** `CompletableFuture.allOf(first, second)` ném CompletionException. Có phải cả hai request đã bị cancel không?  
**Đáp án:** Không. Một request có thể thất bại, request kia còn đang chạy. Cần kiểm tra từng future và xử lý công việc còn active.

**Câu 11.** Vì sao `future.get(5,SECONDS)` báo TimeoutException nhưng vẫn có thể thấy HTTP request ở server?  
**Đáp án:** Vì timeout này chỉ giới hạn luồng đang chờ Future. Request có thể đã được gửi/được server xử lý; bản thân timeout không cancel.

**Câu 12.** Khi nào cần `processingFuture` riêng sau HTTP response?  
**Đáp án:** Khi còn parse, lưu file, ghi DB, gửi tiếp dữ liệu hoặc xử lý body asynchronously. Đợi responseFuture không tự đợi một stage riêng nếu chưa compose/đưa stage đó vào nhóm chờ.

**Câu 13.** Nếu tự cấp `ExecutorService` vào HttpClient, có thể `shutdownNow()` executor ngay sau khi submit HTTP request không?  
**Đáp án:** Không nên. HTTP callbacks/operations có thể còn cần nó. Phải đợi/cancel công việc liên quan rồi đóng executor theo ownership.

**Câu 14.** Cần xử lý `ofLines()` thế nào khi không đọc hết dòng?  
**Đáp án:** Đóng `Stream<String>` trả về. Tương tự InputStream, không bỏ quên tài nguyên khi response future đã xong.

**Câu 15.** Đóng client có bảo đảm POST đã thực hiện ở server bị rollback không?  
**Đáp án:** Không. Server có thể đã nhận và commit request. Dùng idempotency key, correlation ID hoặc API kiểm tra trạng thái nghiệp vụ.

**Câu 16.** Vì sao một grace period 10 giây không nên dùng làm timeout riêng cho từng request nối tiếp?  
**Đáp án:** Vì tổng thời gian chờ sẽ cộng dồn. Cần deadline tổng bằng monotonic clock và mỗi bước chờ dùng remaining time.

**Câu 17.** Khi nào nên ưu tiên `BodyHandlers.ofFile(path)`?  
**Đáp án:** Khi muốn tải body lớn về tệp mà không cần tự viết subscriber. Handler tự xử lý streaming ra file; sau Future thành công cần kiểm tra kết quả file.

**Câu 18.** Nếu ngừng đọc body ngay ở header vì server trả 4xx, có nên bỏ luôn InputStream mà không close không?  
**Đáp án:** Không. Nếu không cần body lỗi, close InputStream hoặc cancel Subscription theo handler; điều đó có thể ảnh hưởng tái sử dụng connection, nhưng tránh rò rỉ.

## 16. Tài liệu tham khảo chuẩn

- Oracle Java SE 17 — `HttpClient`, `sendAsync()`, cancellation; **chưa có close/shutdown**: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 21 — `HttpClient implements AutoCloseable`, `close/shutdown/shutdownNow/awaitTermination/isTerminated` và implementation note về unfinished bodies: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `HttpResponse.BodyHandlers` và `ofInputStream/ofLines/ofPublisher/ofString/ofFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Oracle Java SE 17 — `HttpResponse.BodySubscribers`, trách nhiệm đọc EOF/close InputStream và subscribe/request/cancel Publisher: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- Oracle Java SE 17 — `HttpResponse.BodySubscriber` và `getBody()` CompletionStage: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html
- Oracle Java SE 17 — `HttpRequest.BodyPublishers`, nguồn HTTP request body: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- Oracle Java SE 17 — `CompletableFuture`, `allOf/orTimeout/cancel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java SE 17 — `Flow.Subscription.request/cancel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Oracle Java SE 17 — `InputStream` và close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Oracle Java SE 17 — `HttpServer` phục vụ kiểm chứng loopback: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
