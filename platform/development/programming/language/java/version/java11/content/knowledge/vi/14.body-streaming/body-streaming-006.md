# List<ByteBuffer> và vòng đời dữ liệu nhận trong HTTP body streaming (Java 11)

Khi phản hồi HTTP lớn hoặc được gửi dần theo thời gian, việc nhận toàn bộ body thành một `String` hoặc `byte[]` trước khi xử lý có thể gây tốn bộ nhớ và làm mất lợi ích của streaming. **Java 11** có `java.net.http.HttpClient` và `HttpResponse.BodyHandlers.ofPublisher()`, cho phép ứng dụng nhận nội dung response dưới dạng:

```java
Flow.Publisher<List<ByteBuffer>>
```

Mỗi lần subscriber được gọi `onNext`, nó nhận **một danh sách các `ByteBuffer`**, chứa một phần các byte của response body. Điều quan trọng không chỉ là đọc được byte, mà còn là quản lý **vòng đời dữ liệu nhận**: đăng ký subscriber, yêu cầu thêm dữ liệu (backpressure), xử lý các buffer đúng thứ tự, quản lý bộ nhớ, nhận thông báo hoàn tất/lỗi và hủy subscription khi không muốn đọc tiếp.

Bài thuộc nhóm **Body streaming** của Java 11. Những API được dùng vẫn được duy trì trên JDK hiện đại. Khi thực hành, nên dùng JDK còn được nhà cung cấp hỗ trợ; có thể biên dịch các ví dụ với `javac --release 11` nếu toolchain còn hỗ trợ mức Java 11.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu vì sao publisher phát `List<ByteBuffer>` thay vì một `byte[]` hoặc một `ByteBuffer` duy nhất.
2. Phân biệt vòng đời **HTTP response headers** và **response body đang tiếp tục truyền**.
3. Cài đặt `Flow.Subscriber<List<ByteBuffer>>` đúng các callback `onSubscribe`, `onNext`, `onError` và `onComplete`.
4. Biết `subscription.request(1)` yêu cầu **một item/batch**, **không** phải một byte.
5. Đọc đúng `ByteBuffer.remaining()`, `position`, `limit` và giữ nguyên con trỏ bằng `duplicate()` khi cần.
6. Hiểu các danh sách/byte buffer được HTTP Client cung cấp có tính **read-only**, và ý nghĩa của việc giữ lại hoặc sao chép dữ liệu.
7. Giới hạn kích thước body, hủy subscription khi vượt hạn mức và phân biệt hủy với hoàn tất bình thường.
8. Xử lý dữ liệu nhị phân hoặc UTF-8 bị chia cắt giữa các buffer mà không làm hỏng nội dung.
9. Chọn đúng `ofPublisher()`, `ofInputStream()`, `ofFile()` hoặc một `BodySubscriber` tùy nhu cầu.

## 2. Nhìn toàn bộ vòng đời của một response streaming

`HttpResponse.BodyHandlers.ofPublisher()` tạo một body handler nhận response body bằng publisher. Chữ ký và kiểu trả về:

```java
HttpResponse.BodyHandler<Flow.Publisher<List<ByteBuffer>>> handler =
        HttpResponse.BodyHandlers.ofPublisher();
```

Đây là **đoạn mã đặt bên trong một phương thức**, với imports `java.net.http.HttpResponse`, `java.util.concurrent.Flow`, `java.nio.ByteBuffer` và `java.util.List`; chưa phải chương trình độc lập.

Luồng hoạt động:

```text
Gửi HttpRequest qua HttpClient
                  |
                  v
          Nhận HTTP response headers
                  |
                  v
 HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                  |
                  | response.body()
                  v
      Publisher<List<ByteBuffer>>
                  |
                  | subscribe(subscriber) -- chỉ một lần
                  v
         subscriber.onSubscribe(subscription)
                  |
                  | subscription.request(n)
                  v
         subscriber.onNext(List<ByteBuffer>)
                  |
                  | Xử lý từng buffer và yêu cầu thêm batch
                  v
            ... onNext ...
                  |
            +-----+------+
            |            |
            v            v
       onComplete()   onError(error)
       Đã nhận hết    Có lỗi trong flow

Nếu không muốn tiếp tục: subscription.cancel()
```

**Điểm khác với `BodyHandlers.ofString()`:** khi `HttpClient.send(..., ofPublisher())` trả về `HttpResponse`, **headers đã được đọc**, nhưng **body có thể vẫn đang được truyền**. Phương thức `response.body()` lúc đó là publisher, **không** phải nội dung đã nhận đủ.

Vì vậy, có hai mốc độc lập cần theo dõi:

- **HTTP response có sẵn:** có thể kiểm tra `response.statusCode()` và `response.headers()`.
- **Xử lý body đã hoàn tất:** cần đợi subscriber nhận `onComplete` hoặc `onError` (hoặc biết rằng subscription đã chủ động bị hủy).

Chỉ thấy `send` trả thành công **không** cho phép khẳng định payload đã được xử lý toàn bộ.

## 3. `List<ByteBuffer>` thực sự chứa những gì?

`HttpResponse.BodySubscriber<T>` mở rộng:

```java
Flow.Subscriber<List<ByteBuffer>>
```

Một `onNext(List<ByteBuffer> batch)` có thể mang nhiều buffer. Các buffer cùng với các batch liên tiếp biểu diễn response body **theo đúng thứ tự byte**.

```text
Response bytes: A B C D E F G H ...

onNext batch 1:
    [ByteBuffer: A B]
    [ByteBuffer: C]

onNext batch 2:
    [ByteBuffer: D E F]
    [ByteBuffer: G H]

Ghép đúng thứ tự: A B C D E F G H ...
```

Sơ đồ trên **chỉ minh họa cách phân mảnh**. Trong một lần truyền HTTP thật, số batch, số buffer trong mỗi batch và kích thước buffer **không cố định**, phụ thuộc dữ liệu, hệ thống và triển khai. **Không giả định** mỗi batch tương ứng một TCP packet, một HTTP chunk, một dòng văn bản hay một JSON object.

### Kiểu generic ở ba mức

| Kiểu | Ý nghĩa |
| --- | --- |
| `ByteBuffer` | Một vùng byte có `position`/`limit`, có thể là heap hoặc direct buffer |
| `List<ByteBuffer>` | **Một item** được gửi tới `onNext`; có thể chứa nhiều buffer |
| `Flow.Publisher<List<ByteBuffer>>` | Nguồn phát nhiều item theo `Flow.Subscription` |

Từ khóa quan trọng: `subscription.request(1)` yêu cầu tối đa **một lần `onNext` tiếp theo**, tức là **một `List<ByteBuffer>`**, không phải đúng một buffer và càng không phải đúng một byte.

## 4. Đọc đúng `ByteBuffer`: `position`, `limit` và `remaining()`

Với một `ByteBuffer`, phần byte chưa đọc nằm trong khoảng chỉ số:

```text
[position, limit)

remaining() = limit - position
```

Các phương thức cần nhớ:

| API | Ý nghĩa |
| --- | --- |
| `buffer.position()` | Con trỏ hiện tại của buffer |
| `buffer.limit()` | Giới hạn của vùng có thể đọc/ghi |
| `buffer.remaining()` | Số byte còn có thể đọc, **không** phải `capacity()` |
| `buffer.get()` | Đọc một byte và tăng position |
| `buffer.get(byte[])` | Đọc nhiều byte vào mảng và tăng position |
| `buffer.duplicate()` | Tạo view **có con trỏ độc lập**, nhưng **dùng chung nội dung** |
| `buffer.asReadOnlyBuffer()` | Tạo read-only view có con trỏ riêng, dùng chung nội dung |
| `buffer.hasArray()` | Cho biết có mảng nền truy cập được hay không |

**Không dùng `buffer.array()` một cách mặc định.** Buffer đến từ HTTP Client có thể là direct hoặc read-only; `array()` có thể không được hỗ trợ. Tương tự, `capacity()` không phải số byte có nội dung của một callback.

### Ai sở hữu nội dung buffer?

Hợp đồng Java 11 `HttpResponse.BodySubscriber` nêu rằng:

- HTTP Client cung cấp flow các **danh sách không cho sửa** và **`ByteBuffer` read-only**.
- **Sau khi bàn giao** một danh sách và các buffer cho subscriber, HTTP Client **không tiếp tục sử dụng** chính các đối tượng dữ liệu đó.
- Thứ tự các danh sách và thứ tự các buffer trong mỗi danh sách đều quan trọng, phải được giữ.

Điều này có nghĩa không phải cứ kết thúc `onNext` là các byte lập tức **không hợp lệ** hoặc chắc chắn bị HTTP Client ghi đè. **Có thể giữ tham chiếu nếu chủ đích thiết kế cho phép.** Tuy nhiên, giữ hàng nghìn buffer lâu dài có thể giữ cả vùng bộ nhớ heap/direct phía sau, khiến streaming không còn tiết kiệm RAM.

**Chính sách thực tế:**

1. Nếu chỉ tính checksum, thống kê hoặc chuyển tiếp dữ liệu, hãy **xử lý rồi giải phóng tham chiếu** tới batch.
2. Nếu cần đọc độc lập mà không làm thay đổi position của buffer gốc, dùng `duplicate()` (không sao chép bytes).
3. Nếu cần **sở hữu một bản dữ liệu độc lập** lâu dài, sao chép bytes vào mảng/đích do ứng dụng kiểm soát và áp hạn mức.
4. Không dùng `put(...)` để thay đổi dữ liệu nhận; buffer từ HTTP Client được công bố là read-only.
5. Khi bộ nhớ là yếu tố quan trọng, đừng giữ toàn bộ `List<ByteBuffer>` chỉ vì tưởng rằng `duplicate()` đã tạo bản sao dữ liệu. `duplicate()` **vẫn chia sẻ nội dung**.

## 5. Ví dụ 1 — nhiều batch, nhiều buffer và UTF-8 bị chia cắt

Để thấy rõ cấu trúc `List<ByteBuffer>` mà không phụ thuộc mạng, tạo **`BufferBatchDemo.java`**. Ví dụ tự tạo hai batch, trong đó mã UTF-8 của ký tự `é` bị tách ra giữa hai buffer. Nó đọc dữ liệu bằng `duplicate()` rồi chỉ decode **sau khi ghép đủ byte**.

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

public class BufferBatchDemo {
    public static void main(String[] args) {
        byte[] utf8 = "AéB".getBytes(StandardCharsets.UTF_8);
        ByteBuffer one = ByteBuffer.wrap(Arrays.copyOfRange(utf8, 0, 1))
                .asReadOnlyBuffer();
        ByteBuffer two = ByteBuffer.wrap(Arrays.copyOfRange(utf8, 1, 2))
                .asReadOnlyBuffer();
        ByteBuffer three = ByteBuffer.wrap(Arrays.copyOfRange(utf8, 2, 4))
                .asReadOnlyBuffer();

        List<List<ByteBuffer>> batches =
                List.of(List.of(one, two), List.of(three));
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int batchCount = 0;
        int bufferCount = 0;

        for (List<ByteBuffer> batch : batches) {
            batchCount++;
            for (ByteBuffer original : batch) {
                bufferCount++;
                ByteBuffer copyOfCursor = original.duplicate();
                byte[] part = new byte[copyOfCursor.remaining()];
                copyOfCursor.get(part);
                output.write(part, 0, part.length);
            }
        }

        System.out.println("Batches: " + batchCount);
        System.out.println("Buffers: " + bufferCount);
        System.out.println("Bytes: " + output.size());
        System.out.println("Text: " +
                new String(output.toByteArray(), StandardCharsets.UTF_8));
        System.out.println("Cursor positions preserved: " +
                (one.position() == 0 && two.position() == 0
                        && three.position() == 0));
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 BufferBatchDemo.java
java BufferBatchDemo
```

**Stdout chính xác:**

```text
Batches: 2
Buffers: 3
Bytes: 4
Text: AéB
Cursor positions preserved: true
```

Giải thích:

- `"AéB"` gồm **ba Unicode code point** nhưng **bốn byte UTF-8**: `A` có 1 byte, `é` có 2 byte, `B` có 1 byte.
- Batch thứ nhất có **hai buffer**; batch thứ hai có **một buffer**. Tổng cộng 2 batch nhưng 3 buffer, cho thấy vì sao không được đồng nhất chúng.
- Hai byte của `é` nằm ở các buffer khác nhau. Nếu gọi `new String(part, UTF_8)` cho **từng buffer** rồi ghép các chuỗi, kết quả có thể bị ký tự thay thế do cắt giữa một chuỗi mã hóa.
- `duplicate()` tạo con trỏ đọc mới; dữ liệu gốc vẫn dùng chung, nhưng `one.position()`, `two.position()` và `three.position()` không đổi.
- `List.of` và `asReadOnlyBuffer` giúp giả lập tính chất không sửa được của dữ liệu HTTP Client cung cấp. Đây là **mô hình kiểm thử nhân tạo**, không phải bằng chứng về kích thước batch của HTTP thật.

**Lưu ý về bộ nhớ:** ví dụ này gom toàn bộ bytes để decode vì dữ liệu chỉ dài 4 byte. Với body lớn, cần **incremental `CharsetDecoder`**, parser streaming hoặc đích ghi liên tục thay vì tích lũy mọi byte vào `ByteArrayOutputStream`.

## 6. Vòng đời `Flow.Subscriber<List<ByteBuffer>>`

Một subscriber có bốn callback chính:

| Callback | Khi nào gọi? | Việc cần làm |
| --- | --- | --- |
| `onSubscribe(subscription)` | Trước các sự kiện dữ liệu của subscription | Lưu subscription, quyết định yêu cầu bao nhiêu item hoặc hủy |
| `onNext(List<ByteBuffer> batch)` | Có một item đã được yêu cầu | Xử lý **mọi buffer** trong batch theo thứ tự; kiểm tra hạn mức; request thêm khi sẵn sàng |
| `onError(Throwable error)` | Publisher/subscription thất bại | Ghi nhận lỗi, hoàn tất future lỗi, giải phóng trạng thái ứng dụng |
| `onComplete()` | Publisher không còn dữ liệu, hoàn tất bình thường | Hoàn tất kết quả, đóng/commit đích sau khi validate |

Thông thường, `onError` và `onComplete` là hai tín hiệu **kết thúc loại trừ nhau**. Sau một terminal event, không còn `onNext` cho subscription đó.

### `request(n)` là backpressure theo item, không theo byte

`Flow.Subscription.request(n)` tăng số item được yêu cầu:

```java
subscription.request(1); // Tối đa một lần onNext tiếp theo.
```

Đây là **snippet trong subscriber**, không phải chương trình độc lập. Với `Flow.Publisher<List<ByteBuffer>>`, một item có thể chứa **nhiều buffer** và tổng kích thước có thể khác nhau. Không dùng `request(1024)` với ý nghĩ chỉ xin 1024 byte.

- `request(n)` với `n <= 0` vi phạm giao kèo; subscriber nhận `onError` với `IllegalArgumentException`.
- `request(Long.MAX_VALUE)` có thể được xem như nhu cầu gần như không giới hạn; không phù hợp khi bạn cần hạn chế số batch đang chờ.
- `request(1)` rồi chỉ yêu cầu batch tiếp theo **sau khi xử lý batch hiện tại** là một mẫu điều tiết đơn giản.
- Backpressure không thay thế **giới hạn byte tuyệt đối**, vì mỗi batch có thể lớn, HTTP Client có thể có buffering nội bộ, và các tầng socket/proxy có đặc tính riêng.

### Đừng làm gì trong callback?

Tránh thao tác nặng hoặc chặn không kiểm soát trực tiếp trong `onNext`. Callback có thể chạy trên executor của HTTP Client; block lâu có thể ảnh hưởng throughput và các request khác. Nếu cần đưa dữ liệu sang thread/queue khác, thiết kế **hàng đợi hữu hạn** và chỉ `request` thêm khi downstream thực sự tiếp nhận được.

Không tự gọi `onComplete` hoặc `onError` để kết thúc upstream. Nếu muốn dừng sớm, dùng `subscription.cancel()` rồi tự hoàn tất trạng thái ứng dụng; **cancel không bảo đảm sẽ có một terminal callback** sau đó.

## 7. Ví dụ 2 — HTTP loopback thật, body streaming và giới hạn byte

Ví dụ dưới đây dựng một server HTTP/1.1 nhỏ trên **`127.0.0.1`**, gửi body `"AéB\n"`, rồi nhận response qua `BodyHandlers.ofPublisher()`. Subscriber đọc từng `List<ByteBuffer>`, yêu cầu từng batch, giữ tối đa **128 byte** và kết thúc qua `CompletableFuture`.

Tạo file **`PublisherResponseDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PublisherResponseDemo {
    static final class BoundedCollector
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final long limit;
        private final ByteArrayOutputStream data =
                new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        private long received;
        final CompletableFuture<String> finished =
                new CompletableFuture<>();

        BoundedCollector(long limit) {
            this.limit = limit;
        }

        @Override
        public void onSubscribe(Flow.Subscription s) {
            if (subscription != null) {
                s.cancel();
                return;
            }
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> batch) {
            if (finished.isDone()) {
                return;
            }
            try {
                for (ByteBuffer buffer : batch) {
                    ByteBuffer view = buffer.duplicate();
                    int size = view.remaining();
                    if (size > limit - received) {
                        subscription.cancel();
                        finished.completeExceptionally(
                                new IOException("Body limit exceeded"));
                        return;
                    }
                    byte[] bytes = new byte[size];
                    view.get(bytes);
                    data.write(bytes, 0, bytes.length);
                    received += size;
                }
                subscription.request(1);
            } catch (RuntimeException failure) {
                subscription.cancel();
                finished.completeExceptionally(failure);
            }
        }

        @Override
        public void onError(Throwable failure) {
            finished.completeExceptionally(failure);
        }

        @Override
        public void onComplete() {
            finished.complete(new String(
                    data.toByteArray(), StandardCharsets.UTF_8));
        }

        long byteCount() {
            return received;
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByName("127.0.0.1");

        try (ServerSocket server = new ServerSocket(0, 1, loopback)) {
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<?> serverTask = worker.submit(() -> {
                    try (Socket socket = server.accept()) {
                        socket.setSoTimeout(5000);
                        BufferedReader reader = new BufferedReader(
                                new InputStreamReader(
                                        socket.getInputStream(),
                                        StandardCharsets.US_ASCII));

                        String line = reader.readLine();
                        if (line == null || !line.startsWith("GET ")) {
                            throw new IOException("Unexpected request");
                        }
                        while ((line = reader.readLine()) != null
                                && !line.isEmpty()) {
                            // Read HTTP/1.1 request headers.
                        }

                        byte[] body = "AéB\n".getBytes(
                                StandardCharsets.UTF_8);
                        String headers =
                                "HTTP/1.1 200 OK\r\n"
                                + "Content-Type: text/plain; charset=utf-8\r\n"
                                + "Content-Length: " + body.length + "\r\n"
                                + "Connection: close\r\n\r\n";
                        OutputStream out = socket.getOutputStream();
                        out.write(headers.getBytes(
                                StandardCharsets.US_ASCII));
                        out.write(body);
                        out.flush();
                    } catch (IOException failure) {
                        throw new UncheckedIOException(failure);
                    }
                });

                URI uri = URI.create("http://127.0.0.1:"
                        + server.getLocalPort() + "/demo");
                HttpClient client = HttpClient.newBuilder()
                        .version(HttpClient.Version.HTTP_1_1)
                        .connectTimeout(Duration.ofSeconds(2))
                        .build();
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5))
                        .GET().build();

                HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
                        client.send(request,
                                HttpResponse.BodyHandlers.ofPublisher());
                BoundedCollector collector = new BoundedCollector(128);
                response.body().subscribe(collector);
                String body = collector.finished.get(5, TimeUnit.SECONDS);
                serverTask.get(5, TimeUnit.SECONDS);

                System.out.println("HTTP status: " +
                        response.statusCode());
                System.out.println("Received bytes: " +
                        collector.byteCount());
                System.out.println("Body text: " + body.strip());
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
```

### Biên dịch và chạy

Dùng JDK còn được cập nhật và compiler còn hỗ trợ `--release 11`:

```sh
javac --release 11 -encoding UTF-8 PublisherResponseDemo.java
java PublisherResponseDemo
```

**Stdout khi hệ thống cho phép mở HTTP loopback:**

```text
HTTP status: 200
Received bytes: 5
Body text: AéB
```

**Giải thích chi tiết vòng đời:**

1. Server thử nghiệm nhận một yêu cầu GET và gửi response body **5 byte UTF-8**: `A` = 1, `é` = 2, `B` = 1, xuống dòng `\n` = 1.
2. `client.send(..., BodyHandlers.ofPublisher())` trả `HttpResponse` có publisher. Body có thể chưa được nhận hết tại thời điểm lời gọi trả về.
3. `response.body().subscribe(collector)` đăng ký một subscriber **đúng một lần**.
4. `onSubscribe` lưu `Flow.Subscription` và `request(1)` yêu cầu batch đầu.
5. Mỗi `onNext` duyệt mọi `ByteBuffer` trong batch, dùng `duplicate()` để đọc mà không thay đổi position của buffer do HTTP Client bàn giao.
6. Trước khi sao chép, `size > limit - received` kiểm tra có vượt trần hay không. Kiểm tra theo hiệu tránh tràn phép cộng `received + size`. Nếu vượt, subscriber **cancel** và hoàn tất `finished` một cách exceptional.
7. Sau khi xử lý thành công một batch, `request(1)` yêu cầu batch tiếp theo.
8. `onComplete` chuyển toàn bộ bytes đã nhận trong phạm vi 128 byte thành text UTF-8 và hoàn tất `CompletableFuture`.
9. `collector.finished.get(5, TimeUnit.SECONDS)` chờ hoàn tất **body**, không nhầm với lúc `send` có headers. `serverTask.get` xác nhận server thử nghiệm đã kết thúc.
10. `worker.shutdownNow()` và `try-with-resources` quản lý executor và socket thử nghiệm.

**Tính chất có chủ đích của demo:** `BoundedCollector` gom tối đa **128 byte** vào `ByteArrayOutputStream` chỉ vì body thử nghiệm nhỏ. Trong production streaming lớn, nên ghi từng batch vào đích có backpressure, tính hash hoặc giải mã theo luồng thay vì giữ toàn bộ response. Chương trình không phụ thuộc Internet hay một API bên ngoài; tuy vậy, môi trường chặn loopback có thể khiến ví dụ không chạy được.

### Vì sao không in số lần `onNext`?

Số batch, số buffer trong batch và kích thước mỗi buffer **không được API bảo đảm cố định**, ngay cả khi server gửi cùng 5 byte. Nếu test mong đợi đúng 1 hoặc đúng 2 lần `onNext`, nó dễ lỗi trên JDK, OS hoặc điều kiện mạng khác. Ví dụ chỉ kiểm tra dữ liệu đầu cuối là **5 byte** và text đúng `AéB`.

## 8. Kết thúc bình thường, lỗi và hủy giữa chừng

### `onComplete()`

Khi upstream gọi `onComplete()`, toàn bộ body được gửi tới subscriber đã kết thúc bình thường. Subscriber có thể hoàn thành checksum, đóng/commit đích ghi và báo kết quả cho caller. Tuy nhiên, việc nhận hết bytes không đồng nghĩa **JSON/XML/schema đã hợp lệ**: business validation phải thực hiện đúng lớp.

### `onError(Throwable)`

`onError` báo lỗi không thể phục hồi của luồng. Có thể là lỗi mạng, lỗi trong quá trình nhận, hoặc tín hiệu từ một publisher không chấp nhận request. Phải:

- Hoàn tất future/result với **failure** chứ không trả nội dung đã đọc một phần như thể đầy đủ.
- Dọn tài nguyên ứng dụng (file tạm, buffer, queue, context).
- Giữ nguyên cause phục vụ diagnostics; tránh log dữ liệu nhạy cảm.
- Không tiếp tục `request` sau khi đã có lỗi terminal.

### `subscription.cancel()`

Khi quyết định không đọc tiếp (ví dụ body quá lớn, user hủy tác vụ, không cần phần còn lại), gọi:

```java
subscription.cancel();
```

Đây là **mã minh họa bên trong subscriber** đã lưu `subscription` hợp lệ.

- `cancel` là thao tác **best-effort**; một số sự kiện đang trên đường truyền có thể còn xảy ra.
- Sau `cancel`, **không có bảo đảm** sẽ được gọi `onComplete` hoặc `onError`. Vì vậy phải hoàn tất **future riêng** hoặc dọn trạng thái bằng cơ chế do ứng dụng quản lý.
- Hủy trước khi tiêu thụ hết body có thể khiến HTTP connection bị đóng và **không thể tái sử dụng**, tùy protocol và implementation. Đây là một đánh đổi để tránh đọc dữ liệu không mong muốn.
- Đừng “bỏ mặc” một publisher không subscribe cũng không cancel. Tài liệu Java yêu cầu phải subscribe một lần, rồi **đọc đến terminal event** hoặc **hủy subscription** để giải phóng tài nguyên trao đổi HTTP.

### Nếu xảy ra timeout trong lúc đợi body?

`CompletableFuture.get(timeout, unit)` hết thời hạn chờ ở **caller** không tự bảo đảm subscription đã được hủy. Trong sản phẩm thực tế, cần phối hợp **timeout/deadline với cancel** và xử lý tình huống race giữa cancel, onNext, onError, onComplete. Ví dụ học tập dùng timeout hữu hạn và server local hoàn tất nhanh; khi mở rộng ra hệ thống thật, hãy thiết kế một đường hủy rõ ràng và kiểm thử nó.

## 9. Lưu buffer hay sao chép? Chọn theo quyền sở hữu và ngân sách bộ nhớ

Có ba chiến lược phổ biến:

| Chiến lược | Việc làm | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Xử lý ngay | Duyệt buffer trong `onNext`, tính hash/thống kê/ghi ra đích rồi thả tham chiếu | Streaming liên tục, tiết kiệm RAM | Nếu downstream chậm phải điều tiết request |
| Giữ tham chiếu | Lưu `List<ByteBuffer>` hoặc `duplicate()` trong queue có giới hạn | Downstream cần xử lý bất đồng bộ | Giữ vùng nhớ heap/direct, có thể gây áp lực bộ nhớ |
| Sao chép dữ liệu | Chép phần `remaining()` sang `byte[]`/file do ứng dụng sở hữu | Cần độc lập vòng đời, lưu trữ có giới hạn | Có chi phí cấp phát/copy; cần max size |

**Quan trọng:** HTTP Client không còn dùng các list/buffer sau khi đã đưa cho subscriber, nhưng điều đó **không miễn trừ việc ứng dụng quản lý memory retention**. Nếu buffer direct trỏ tới vùng native memory lớn, giữ một view nhỏ lâu dài có thể vẫn giữ phần backing storage lớn. Muốn có dữ liệu thật sự độc lập và không giữ backing buffer, phải sao chép **bytes** có giới hạn.

### Đừng dùng `duplicate()` như một cơ chế copy dữ liệu

`ByteBuffer.duplicate()` tạo object buffer mới có `position`, `limit` và `mark` độc lập, nhưng **nội dung phía dưới là chung**. Nó thích hợp để đọc mà không làm thay đổi con trỏ của original. Nếu mục tiêu là lưu byte độc lập với bộ nhớ nền, cần:

```java
ByteBuffer view = original.duplicate();
byte[] owned = new byte[view.remaining()];
view.get(owned);
```

Đây là **snippet trong phương thức** nơi `original` là `ByteBuffer` và kích thước đã được kiểm tra. `owned` là một mảng mới chứa đúng phần bytes còn lại. Nếu dữ liệu nhận rất lớn, không nên copy vô hạn vào mảng; dùng đích ghi theo luồng.

## 10. Byte và văn bản: không giải mã UTF-8 theo từng buffer

Một ký tự Unicode có thể trải qua nhiều bytes UTF-8, và những bytes ấy có thể nằm trong **hai batch khác nhau**. Ví dụ ký tự `é` có hai byte UTF-8. Nếu decoder nhận riêng byte đầu mà được yêu cầu tạo text hoàn chỉnh ngay, nó có thể sinh ký tự thay thế hoặc báo dữ liệu thiếu.

**Không khuyến nghị:**

```java
for (ByteBuffer buffer : batch) {
    byte[] bytes = new byte[buffer.remaining()];
    buffer.get(bytes);
    String text = new String(bytes, StandardCharsets.UTF_8);
    // Có thể decode sai nếu một code point bị cắt giữa hai buffer.
}
```

Đây là **đoạn minh họa cách làm sai** trong `onNext`. Ngoài vấn đề position, nó **giải mã từng fragment độc lập**.

Hai cách xử lý đúng tùy quy mô:

- **Payload nhỏ, có giới hạn cứng:** gom đủ bytes (như hai ví dụ), sau đó giải mã toàn bộ bằng charset đúng; kiểm tra schema/định dạng.
- **Payload lớn/stream vô hạn:** sử dụng một **`CharsetDecoder` có trạng thái** giữa các batch; giữ lại bytes chưa đủ để tạo ký tự trong buffer dư, gọi decoder theo đúng cờ `endOfInput` và xử lý `CoderResult` (`UNDERFLOW`/`OVERFLOW`/`ERROR`). Không tạo decoder mới cho mỗi buffer.

Nếu ứng dụng chỉ tải file nhị phân, **không cần chuyển bytes thành `String`**. Ghi raw bytes xuống đích, kiểm tra checksum, media type và giới hạn kích thước phù hợp.

**Đếm kích thước theo byte:** `String.length()` đếm đơn vị UTF-16, không phải byte trên mạng. Với giới hạn body 10 MiB, kiểm tra tổng `ByteBuffer.remaining()` đã nhận, không suy từ số ký tự.

## 11. Backpressure thực tế: batch, queue và tải hệ thống

Mẫu `request(1)` giúp subscriber không chủ động đòi nhiều item cùng lúc. Tuy nhiên, đây là **điều tiết theo batch**, không phải một giới hạn bộ nhớ tuyệt đối.

Một hệ thống thực có thể có pipeline:

```text
HTTP Client (publisher)
        |
        v
Subscriber<List<ByteBuffer>>
        |
        v
Queue hữu hạn / xử lý từng batch
        |
        +--> Ghi file
        +--> Incremental hash
        +--> Streaming parser
        +--> Kiểm tra giới hạn/trạng thái
```

Nếu downstream nhanh, xử lý xong batch rồi gọi `request(1)`. Nếu downstream chậm, giữ ít item trong queue có giới hạn và **chỉ request thêm** khi downstream có năng lực tiếp nhận. Nếu queue đã đầy và không thể xử lý hoặc chờ an toàn, có thể cancel/error theo chính sách.

Không nên gọi `request(Long.MAX_VALUE)` rồi đưa mọi `List<ByteBuffer>` vào một collection không giới hạn. Khi đó ứng dụng đã bỏ lợi ích backpressure và có thể tự tạo out-of-memory dù HTTP Client cung cấp dữ liệu theo stream.

### Các tầng đều có buffering

- TCP và HTTP Client có thể đã nhận hoặc đệm dữ liệu trước khi subscriber tiêu thụ.
- `Flow.Subscription.request(n)` kiểm soát **nhu cầu item** ở giao diện Publisher/Subscriber; nó không trực tiếp điều khiển kích thước TCP packet hay bảo đảm chỉ đúng N byte nằm trong RAM.
- `ByteBuffer.remaining()` là kích thước **vùng đọc của buffer hiện tại**; một `onNext` có thể mang nhiều buffer.
- Để đặt **hạn mức body cứng**, phải đếm **từng byte thực nhận** và hủy khi vượt.
- Nếu có nén HTTP, phân biệt kích thước **body trên wire** và kích thước **dữ liệu đã giải nén** theo mục tiêu bảo vệ; áp giới hạn ở đúng tầng.

## 12. Mã HTTP status và việc tiêu thụ body

`BodyHandlers.ofPublisher()`, giống các body handler chuẩn của Java 11, **không tự từ chối response dựa trên `statusCode()`**. Có thể nhận `HttpResponse` có `404` hay `503` và publisher của một body lỗi.

Điều này dẫn đến một quyết định quan trọng:

1. Đọc `response.statusCode()` và các headers khi chúng có sẵn.
2. Nếu body của response cần thiết (ví dụ JSON lỗi), hãy subscribe và xử lý với **hạn mức riêng**.
3. Nếu không cần body, vẫn phải **subscribe để tiêu thụ** hoặc **subscribe rồi cancel**, không bỏ mặc publisher.
4. Trả kết quả đã phân loại theo API contract, không dùng mỗi `IOException` để suy luận success.

Ví dụ `onError` có thể báo lỗi I/O sau khi đã nhận được response headers; ngược lại, HTTP `500` có thể hoàn tất body bình thường bằng `onComplete`. **Sự hoàn tất của stream không đồng nghĩa HTTP/đối tác báo thành công nghiệp vụ.**

Với ứng dụng có chính sách status phức tạp, có thể dùng **custom `HttpResponse.BodyHandler`** để chọn `BodySubscriber` theo `ResponseInfo.statusCode()` và headers trước khi nhận body. Phải giữ kiểu trả về của handler nhất quán, xử lý rõ dữ liệu lỗi và tài nguyên. Đây là hướng mở rộng, không phải yêu cầu phải tự viết lại HTTP protocol.

## 13. Chọn body handler đúng với loại dữ liệu

| Nhu cầu | API Java 11 | Đặc điểm vòng đời |
| --- | --- | --- |
| Response nhỏ, biết chắc hạn mức | `BodyHandlers.ofString(UTF_8)` / `ofByteArray()` | Kết quả body đã được gom trước khi `HttpResponse` hoàn tất |
| Tải file | `BodyHandlers.ofFile(path)` | Ghi body vào file, hữu ích cho tải nội dung; vẫn cần policy kích thước và dọn file lỗi |
| Xử lý tuần tự qua `InputStream` | `BodyHandlers.ofInputStream()` | Response có thể về trước body; phải **đọc tới EOF hoặc close stream** |
| Xử lý theo các batch buffer và backpressure | **`BodyHandlers.ofPublisher()`** | Phải **subscribe đúng một lần**, xử lý tới terminal hoặc cancel |
| Gửi trực tiếp bytes đến một `Flow.Subscriber` của ứng dụng | `BodyHandlers.fromSubscriber(subscriber)` | Adapter đưa dữ liệu tới subscriber; thời điểm kết quả phụ thuộc callback hoàn tất |
| Chuỗi văn bản theo dòng | `BodyHandlers.ofLines()` | Trả `Stream<String>`; phải đọc hết/đóng stream |
| Không cần nội dung response | `BodyHandlers.discarding()` | Body bị bỏ, không giữ dữ liệu |
| Điều chỉnh kích thước batch cho downstream | `BodyHandlers.buffering(handler, size)` | `size` điều chỉnh buffering; không phải **giới hạn tổng số byte body** |

Các API trong bảng có mặt ở Java 11. Một số phiên bản JDK mới hơn có helper bổ sung để giới hạn body; **đừng dùng API chỉ được bổ sung sau Java 11** nếu bài tập hoặc thư viện phải biên dịch bằng `--release 11`. Với Java 11, hãy triển khai quota rõ ràng bằng subscriber hoặc kiểm soát stream phù hợp.

### `ofPublisher()` và `fromSubscriber()` khác gì?

- `ofPublisher()`: response trả về một **`Publisher<List<ByteBuffer>>`**; code gọi sau đó **tự subscribe** khi sẵn sàng xử lý body.
- `fromSubscriber(subscriber)`: truyền **subscriber do ứng dụng tạo** ngay lúc chọn handler; HTTP Client chuyển các batch vào subscriber. Với overload trả `Void`, response hoàn tất khi subscriber nhận terminal event thích hợp.
- Dùng `ofPublisher()` khi muốn điều khiển thời điểm subscribe và đường đi của publisher; dùng `fromSubscriber` khi subscriber đã được thiết kế để nhận trực tiếp body.

## 14. Kỹ thuật test: đừng phụ thuộc kích thước batch

Một số bài test nên có:

| Tình huống | Kiểm tra |
| --- | --- |
| Body chia thành 1, 2 hoặc nhiều buffer | Nối lại vẫn giữ đúng thứ tự byte |
| Một ký tự UTF-8 bị cắt giữa hai batch | Decoder/assembler vẫn tạo đúng văn bản |
| Một batch có nhiều `ByteBuffer` | Subscriber xử lý hết từng buffer |
| `ByteBuffer.position()` ban đầu khác 0 | Chỉ đọc phần `remaining()`, không lấy nhầm `capacity()` |
| Buffer direct/read-only | Không gọi `array()` hoặc `put()` |
| Batch lớn hơn hạn mức | Subscriber cancel và hoàn tất kết quả lỗi |
| Upstream báo `onError` giữa body | Không báo thành công với dữ liệu đã đọc dở |
| Upstream báo `onComplete` | Kết thúc thành công, đóng/commit đích khi hợp lệ |
| Cancel do người dùng hoặc deadline | Không chờ mãi terminal callback không được bảo đảm |
| HTTP 200/404/503 cùng body khác nhau | Status được phân loại **riêng** với stream lifecycle |
| Subscriber gọi `request(0)` | Luồng báo lỗi theo `Flow.Subscription` |
| Subscribe lại publisher lần hai | Nhận `IllegalStateException` theo hợp đồng của publisher một lần |
| HTTP/1.1 và HTTP/2 | Không giả định số chunk/batch cố định giữa các giao thức |

**Đừng viết assertion “`onNext` phải gọi đúng 3 lần”.** Test nên dựa vào **nội dung byte, thứ tự, giới hạn, callback hoàn tất/lỗi** và việc giải phóng tài nguyên. HTTP Client có quyền chọn cách chia buffer khác.

## 15. Những lỗi thường gặp

**Lỗi 1 — Xem `List<ByteBuffer>` như `byte[]`.** `onNext` nhận **danh sách** chứa nhiều buffer, không phải một buffer duy nhất. Phải duyệt cả hai mức.

**Lỗi 2 — `request(1)` rồi tin rằng nhận đúng một byte.** Một lần `onNext` mang một `List<ByteBuffer>` có kích thước thay đổi. Hạn mức byte phải kiểm tra riêng.

**Lỗi 3 — Tin rằng `send(...ofPublisher())` đã đợi body đọc xong.** Nó trả response khi headers sẵn sàng; body có thể còn đang truyền. Cần theo dõi `onComplete`/`onError`.

**Lỗi 4 — Không bao giờ subscribe.** Publisher được trả về phải được subscribe một lần và tiêu thụ hoặc hủy; nếu không, tài nguyên HTTP có thể bị giữ.

**Lỗi 5 — Subscribe nhiều lần.** `ofPublisher()` chỉ hỗ trợ một subscriber; lần sau bị báo `IllegalStateException`.

**Lỗi 6 — Gọi `buffer.array()` trên buffer read-only/direct.** Không có bảo đảm mảng nền truy cập được. Đọc từ `duplicate()` bằng `get`/`remaining`.

**Lỗi 7 — Dùng `capacity()` để đếm bytes.** Cần dùng `remaining()` và phần từ `position` đến `limit`.

**Lỗi 8 — Cố sửa list hoặc `put` vào buffer của HTTP Client.** Dữ liệu được đưa tới subscriber dưới dạng **unmodifiable list** và **read-only ByteBuffer**.

**Lỗi 9 — Giữ lại mọi buffer vô hạn.** Buffer có thể giữ nhiều heap/direct memory. Nếu cần lưu lâu, xác lập budget và phương thức copy/ghi stream.

**Lỗi 10 — Dùng `duplicate()` như bản sao bytes độc lập.** Nó chỉ có cursor riêng, vẫn dùng chung nội dung nền.

**Lỗi 11 — `new String(bytes, UTF_8)` cho từng chunk.** Có thể cắt giữa một ký tự nhiều byte, gây dữ liệu sai. Decode theo stream hoặc ghép bytes có hạn mức.

**Lỗi 12 — Hủy subscription rồi vẫn chờ `onComplete`.** Cancel không đảm bảo terminal event; caller cần cơ chế kết thúc/cancel riêng.

**Lỗi 13 — `onError` nhưng vẫn commit file/tính tổng như thành công.** Xử lý fail-fast, xóa dữ liệu tạm hoặc giữ trạng thái thất bại rõ ràng.

**Lỗi 14 — Nghĩ flow control giải quyết mọi vấn đề RAM.** `request(1)` chỉ hạn chế số item được yêu cầu, không giới hạn bytes và không kiểm soát toàn bộ buffering nội bộ.

**Lỗi 15 — Nghĩ response stream kết thúc thành công nghĩa là HTTP status 2xx.** `404`/`503` vẫn có thể mang body và kết thúc bình thường.

**Lỗi 16 — Gọi xử lý nặng hoặc blocking I/O vô hạn trong callback.** Có thể cản trở throughput và các request khác. Dùng queue hữu hạn, executor có kiểm soát và backpressure.

## 16. Bài tập thực hành

### Bài 1 — Đếm batch, buffer và byte

Chạy `BufferBatchDemo.java` rồi giải thích vì sao:
- `Batches: 2`;
- `Buffers: 3`;
- `Bytes: 4` với text `AéB`.

Sửa phân nhóm thành một batch có ba buffer rồi xác nhận **tổng bytes và text vẫn không đổi**, dù số batch thay đổi.

### Bài 2 — Kiểm tra cursor

Thay một buffer trong `BufferBatchDemo` bằng một `ByteBuffer` có `position = 1` và `limit = 3`. Hãy xác định chỉ hai byte ở vị trí hiện tại được đọc. Giải thích vì sao `remaining()` mới là kích thước cần đọc, còn `capacity()` không đủ.

### Bài 3 — Giới hạn body và cancel

Trong `PublisherResponseDemo.java`, đổi:

```java
BoundedCollector collector = new BoundedCollector(128);
```

thành:

```java
BoundedCollector collector = new BoundedCollector(3);
```

Đây là **chỉ thay một dòng trong chương trình**, không phải chương trình độc lập. Body server vẫn dài **5 byte**, nên collector phải gọi `cancel()` và hoàn tất `finished` **exceptionally** với lỗi `"Body limit exceeded"`. Khi chạy, vì `main` đang đợi `finished.get` và khai báo `throws Exception`, kết quả sẽ là một exception thay vì ba dòng stdout thành công. Trong bài production, nên bắt `ExecutionException`, lấy `getCause()` để báo lỗi có phân loại, đồng thời dọn/ghi trạng thái hủy rõ ràng.

### Bài 4 — Không phụ thuộc số batch

Thêm bộ đếm số `onNext` của ví dụ loopback, chạy nhiều lần và quan sát. Tránh khẳng định một số callback cố định; thay vào đó kiểm tra **tổng byte 5** và nội dung `AéB`. Giải thích vì sao TCP/HTTP fragmentation và buffering không phải ranh giới bản ghi nghiệp vụ.

### Bài 5 — Lưu file lớn

Thiết kế subscriber ghi từng `ByteBuffer` vào một file **tạm**, có tổng giới hạn 20 MiB và thời hạn xử lý. Chỉ chuyển file tạm thành file chính khi `onComplete` và checksum/metadata hợp lệ. Khi `onError` hoặc hủy, xóa file tạm theo chính sách. Trình bày cách xử lý partial write và backpressure với đích ghi chậm.

### Bài 6 — Decoder UTF-8 có trạng thái

Đưa bytes của một code point ngoài BMP qua hai `onNext` khác nhau. Dùng cùng một `CharsetDecoder` để decode theo luồng, giữ các byte chưa đủ từ `CoderResult.UNDERFLOW`, và chỉ kết thúc decoder khi `onComplete`. Giải thích vì sao không gọi `new String` cho từng buffer.

### Checklist hoàn thành

- [ ] Hiểu kiểu `Flow.Publisher<List<ByteBuffer>>` từ `BodyHandlers.ofPublisher()` trong Java 11.
- [ ] Phân biệt response headers có sẵn và body chưa hoàn tất.
- [ ] Biết một `onNext` nhận một **List**, có thể chứa nhiều buffer.
- [ ] Biết `request(n)` đếm item, không đếm byte.
- [ ] Đọc buffer bằng `remaining()`, `duplicate()` và không phụ thuộc `array()`.
- [ ] Hiểu list unmodifiable, buffers read-only, client không còn dùng chúng sau khi bàn giao.
- [ ] Biết giữ view có thể giữ backing storage; `duplicate()` không copy bytes.
- [ ] Theo dõi `onComplete`/`onError` và chủ động cancel khi không muốn đọc tiếp.
- [ ] Áp giới hạn byte, thời hạn và quy tắc xử lý body lớn.
- [ ] Không decode UTF-8 riêng rẽ theo từng buffer.
- [ ] Đã chạy hai ví dụ bằng compiler hỗ trợ `--release 11` và đối chiếu stdout.

## 17. Tài liệu tham khảo chính thức, vẫn còn áp dụng

1. [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofPublisher()`, `ofInputStream()`, `ofFile()`, `fromSubscriber()`, `ofLines()` và `buffering()`.
2. [Java SE 11 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): quy tắc publisher **subscribe một lần**, đọc đến terminal hoặc cancel, khả năng mất connection reuse.
3. [Java SE 11 — HttpResponse.BodySubscriber](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): flow có thứ tự, unmodifiable lists, read-only buffers và vòng đời bàn giao.
4. [Java SE 11 — Flow.Subscriber](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html): bốn callback và thứ tự thông báo.
5. [Java SE 11 — Flow.Subscription](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)`, `cancel()`, tín hiệu lỗi khi `n <= 0` và cancel best-effort.
6. [Java SE 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, `duplicate`, direct/read-only buffers.
7. [Java SE 25 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): xác nhận các API streaming vẫn được duy trì trên JDK LTS hiện đại.

**Kết luận áp dụng:** với `BodyHandlers.ofPublisher()`, vòng đời dữ liệu HTTP **không kết thúc khi `HttpResponse` được trả về**. Caller phải subscribe **một lần**, điều tiết số `List<ByteBuffer>` nhận qua `request`, xử lý từng buffer theo `remaining()` và đúng thứ tự, rồi **tiêu thụ tới `onComplete`/`onError` hoặc hủy subscription**. Đừng nhầm batch với byte, con trỏ buffer với bản sao dữ liệu, hay hoàn tất I/O với payload hợp lệ theo nghiệp vụ.