# NIO CompletionHandler: chuyển callback completed()/failed() sang CompletionStage

## 1. Mục tiêu và bối cảnh

Các API NIO.2 bất đồng bộ trong Java (từ Java 7), như `AsynchronousFileChannel` và `AsynchronousSocketChannel`, có những overload nhận `CompletionHandler<V, A>`. Khi thao tác kết thúc, thư viện gọi `completed(V result, A attachment)`; khi thao tác thất bại, thư viện gọi `failed(Throwable exc, A attachment)`. Mô hình này hoạt động tốt cho từng lần I/O, nhưng khi có nhiều bước nối tiếp, các callback lồng nhau khiến đường thành công, xử lý lỗi và giải phóng tài nguyên khó theo dõi.

`CompletionStage<T>` (Java 8+) biểu diễn kết quả sẽ có trong tương lai và cho phép ghép bước với `thenApply`, `thenCompose`, `thenCombine`, `handle`, `exceptionally` và `whenComplete`. `CompletableFuture<T>` là một implementation vừa cung cấp cơ chế hoàn tất kết quả, vừa triển khai `CompletionStage<T>`.

**Phạm vi:** Chuyển callback NIO thuần Java thành stage, bao gồm điểm hoàn tất, lỗi, dữ liệu từng phần, quản lý channel, huỷ và timeout. Đây là cơ chế concurrency chung của Java; không cần Spring hay framework.

Sau bài này, bạn cần có thể:

- Nhận ra chính xác khi nào hoàn tất stage bằng giá trị và khi nào hoàn tất bằng lỗi.
- Viết adapter từ `CompletionHandler` thành `CompletableFuture` và công khai `CompletionStage`.
- Dùng stage để nối thao tác, phục hồi lỗi và phối hợp nhiều thao tác.
- Xử lý đúng byte count, EOF, vòng đời `ByteBuffer` và channel; tránh nhầm hoàn tất một lần đọc với hoàn tất một thông điệp.
- Hiểu ranh giới giữa huỷ/timeout của stage và huỷ I/O thật sự.

## 2. Đọc đúng hợp đồng CompletionHandler

~~~java
public interface CompletionHandler<V, A> {
    void completed(V result, A attachment);
    void failed(Throwable exc, A attachment);
}
~~~

Hai tham số kiểu có ý nghĩa khác nhau:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `V` | Kết quả của **một thao tác I/O** | `Integer`: số byte đọc/ghi; `Void`: kết nối thành công |
| `A` | Attachment do **người gọi** truyền vào để mang ngữ cảnh qua callback | Một request/context, hoặc `Void` khi không dùng |
| `completed(result, attachment)` | Thao tác đã hoàn tất bình thường | Không mặc định rằng đã đọc đủ dữ liệu ứng dụng |
| `failed(error, attachment)` | Thao tác I/O hoàn tất với lỗi | Có thể do đóng channel, kết nối hỏng, quyền truy cập… |

Ví dụ chữ ký thường gặp (đã giản lược):

~~~java
// AsynchronousFileChannel
<A> void read(
    ByteBuffer dst, long position, A attachment,
    CompletionHandler<Integer, ? super A> handler);

// AsynchronousSocketChannel
<A> void connect(
    SocketAddress remote, A attachment,
    CompletionHandler<Void, ? super A> handler);

<A> void read(
    ByteBuffer dst, A attachment,
    CompletionHandler<Integer, ? super A> handler);
~~~

Với `read`, `completed(n, …)` cho biết **n byte của lần đọc đó**, không phải chắc chắn toàn bộ file hay toàn bộ bản tin. Giá trị `-1` biểu thị đã đến cuối luồng đọc (EOF); `0` không đồng nghĩa EOF. `ByteBuffer` bị thay đổi `position` trong lúc đọc nên phải `flip()` trước khi lấy dữ liệu và `clear()`/`compact()` trước lần đọc tiếp theo.

Đặc biệt, lỗi có thể xuất hiện ở **hai thời điểm**: (1) lúc gọi phương thức bắt đầu I/O, chẳng hạn đối số sai hoặc một thao tác cùng loại đang chờ; (2) muộn hơn trong `failed()`. Adapter phải xử lý cả hai đường.

## 3. Quy tắc chuyển callback sang stage

Ánh xạ cơ bản là:

| Tín hiệu NIO | Tác động lên `CompletableFuture<T>` |
| --- | --- |
| `completed(value, attachment)` | `future.complete(value)` |
| `failed(error, attachment)` | `future.completeExceptionally(error)` |
| Lệnh khởi tạo I/O ném exception đồng bộ | `future.completeExceptionally(error)` |
| Kết quả `read` bằng `-1` | Quyết định EOF theo giao thức của **adapter** trước khi hoàn tất stage |

Một adapter gọn cho **một callback hoàn tất duy nhất**, chưa quản lý channel/timeout:

~~~java
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.function.Consumer;

static <T> CompletionStage<T> fromCallback(
        Consumer<CompletionHandler<T, Void>> register) {
    CompletableFuture<T> promise = new CompletableFuture<>();

    CompletionHandler<T, Void> handler = new CompletionHandler<>() {
        @Override
        public void completed(T value, Void ignored) {
            promise.complete(value);
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            promise.completeExceptionally(error);
        }
    };

    try {
        register.accept(handler);
    } catch (RuntimeException startError) {
        promise.completeExceptionally(startError);
    }

    return promise;
}
~~~

Ở đây `register` nhận callback và đăng ký I/O. Đầu ra là `CompletionStage<T>` để tầng gọi tập trung vào phép ghép stage. `CompletableFuture` vẫn nằm bên trong để adapter điều khiển kết quả. `complete`/`completeExceptionally` chỉ thành công ở lần kết thúc đầu tiên; các lần hoàn tất sau trả về `false`. Điều này hữu ích khi có race, nhưng không thay thế việc quản lý tài nguyên đúng cách.

Ví dụ dùng adapter này với một lần đọc trên socket đang mở:

~~~java
// Đoạn minh hoạ đặt trong một class có fromCallback ở trên.
// channel: AsynchronousSocketChannel đang kết nối
// dst: ByteBuffer còn dung lượng để nhận dữ liệu
CompletionStage<Integer> oneRead =
    fromCallback(handler -> channel.read(dst, null, handler));
~~~

Stage `oneRead` chỉ mang **số byte của một lần đọc**. Nếu ứng dụng cần một dòng, một frame có độ dài cố định hay một file hoàn chỉnh thì phải tiếp tục đọc và gom dữ liệu theo giao thức trước khi hoàn tất stage cấp ứng dụng.

## 4. Ví dụ Java 17+ chạy được: đọc hết file NIO rồi trả CompletionStage<String>

Ví dụ tự tạo file UTF-8, mở bằng `AsynchronousFileChannel`, đọc từng chunk cho đến EOF, gom byte trước khi giải mã UTF-8, đóng channel, rồi hoàn tất stage. Đường lỗi ở cả bước mở, phát lệnh đọc và callback đều chuyển thành exceptional completion. Giải mã **sau khi gom tất cả byte** tránh cắt đôi ký tự UTF-8 tại ranh giới chunk.

Lưu thành `CompletionHandlerBridgeDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CompletionHandlerBridgeDemo {
    static CompletionStage<String> readUtf8(Path path) {
        final AsynchronousFileChannel channel;
        try {
            channel = AsynchronousFileChannel.open(
                path, StandardOpenOption.READ);
        } catch (IOException | SecurityException error) {
            return CompletableFuture.failedFuture(error);
        }

        CompletableFuture<String> result = new CompletableFuture<>();
        ByteBuffer buffer = ByteBuffer.allocate(1024);
        ByteArrayOutputStream data = new ByteArrayOutputStream();

        class ReadLoop implements CompletionHandler<Integer, Void> {
            private long position;

            void submit() {
                try {
                    channel.read(buffer, position, null, this);
                } catch (RuntimeException error) {
                    finish(null, error);
                }
            }

            @Override
            public void completed(Integer count, Void ignored) {
                if (count == -1) {
                    finish(new String(
                        data.toByteArray(), StandardCharsets.UTF_8), null);
                    return;
                }

                if (count > 0) {
                    position += count;
                    buffer.flip();
                    byte[] chunk = new byte[buffer.remaining()];
                    buffer.get(chunk);
                    data.write(chunk, 0, chunk.length);
                    buffer.clear();
                }

                // count == 0: chưa đến EOF, thử lại.
                submit();
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                finish(null, error);
            }

            private void finish(String value, Throwable failure) {
                try {
                    channel.close();
                } catch (IOException closeError) {
                    if (failure == null) {
                        failure = closeError;
                    } else {
                        failure.addSuppressed(closeError);
                    }
                }

                if (failure == null) {
                    result.complete(value);
                } else {
                    result.completeExceptionally(failure);
                }
            }
        }

        new ReadLoop().submit();
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-demo-", ".txt");
        Path missing = Files.createTempFile("nio-missing-", ".txt");
        Files.delete(missing);

        try {
            Files.writeString(
                file, "Xin chào NIO", StandardCharsets.UTF_8);

            String upper = readUtf8(file)
                .thenApply(s -> s.toUpperCase(Locale.ROOT))
                .toCompletableFuture()
                .join();
            System.out.println(upper);

            String fallback = readUtf8(missing)
                .exceptionally(error -> "Không đọc được")
                .toCompletableFuture()
                .join();
            System.out.println(fallback);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 CompletionHandlerBridgeDemo.java
java CompletionHandlerBridgeDemo
~~~

Stdout khi thực thi bình thường:

~~~text
XIN CHÀO NIO
Không đọc được
~~~

Phân tích từng điểm then chốt:

1. **Mở channel:** Lỗi xảy ra ngay lúc `open` trở thành `CompletableFuture.failedFuture(error)`; người gọi vẫn nhận một stage lỗi thay vì phải viết hai cơ chế xử lý lỗi.
2. **Bắt đầu I/O:** `submit` gọi `read(buffer, position, null, this)`. `this` là `CompletionHandler<Integer, Void>` của chính vòng đọc. Exception đồng bộ từ lệnh gửi được đưa vào `finish`.
3. **Đọc từng phần:** `count > 0` mới tăng offset và chép dữ liệu ra `ByteArrayOutputStream`. Sau `flip()` và lấy byte, gọi `clear()` để chuẩn bị buffer cho lần đọc sau. `count == 0` không tăng offset; vòng đọc phát lệnh lại.
4. **EOF:** `count == -1` nghĩa là không còn byte để đọc. Lúc này mới giải mã toàn bộ byte UTF-8 và kết thúc **stage đọc file**.
5. **Lỗi bất đồng bộ:** `failed(error, …)` đi qua `finish(null, error)`. Stage chuyển sang thất bại; các phép `exceptionally`/`handle` phía sau có thể xử lý nó.
6. **Sở hữu tài nguyên:** Adapter **tự mở** channel nên cũng **tự đóng** ở điểm thành công hoặc thất bại, trước khi hoàn tất stage. Nếu đóng channel lỗi, ví dụ giữ lỗi đóng làm lỗi chính khi chưa có lỗi khác, hoặc gắn vào lỗi gốc bằng `addSuppressed`.
7. **Phép ghép:** `thenApply` biến nội dung đọc thành chữ hoa; `exceptionally` phục hồi lỗi file không tồn tại thành giá trị dự phòng. `join()` chỉ xuất hiện trong `main` để demo đợi kết quả; các callback I/O không gọi chờ đồng bộ.

Mã này dành cho file nhỏ và một người sở hữu channel: `ByteArrayOutputStream` giữ **toàn bộ** dữ liệu trong RAM. Với file lớn, dùng giới hạn dung lượng, ghi ra sink/stream hay thiết kế consumer theo chunk. Nếu file đang bị thay đổi trong khi đọc, dữ liệu quan sát có thể không phải ảnh chụp nhất quán. Việc `read` bất đồng bộ không bảo đảm tầng hệ điều hành thực hiện file I/O hoàn toàn không chặn thread; implementation có thể dựa vào thread pool.

## 5. Chuyển các thao tác khác: connect, read, write

### Kết nối: completed(Void) thành CompletionStage<Void>

`AsynchronousSocketChannel.connect` dùng kết quả `Void`. Một kết nối thành công hoàn tất stage với `null`; không cần gán giá trị giả như `true`.

~~~java
// Đặt cùng class với phương thức fromCallback ở mục 3.
// Bổ sung import java.net.SocketAddress;
// và import java.nio.channels.AsynchronousSocketChannel;
static CompletionStage<Void> connectStage(
        AsynchronousSocketChannel channel, SocketAddress remote) {
    return fromCallback(handler ->
        channel.connect(remote, null, handler));
}
~~~

Ở ví dụ này, **bên gọi** tạo và sở hữu socket; adapter `connectStage` không tự đóng socket sau khi kết nối thành công vì còn phải đọc/ghi. Nếu kết nối thất bại, tầng quản lý socket phải quyết định đóng và giải phóng.

### Đọc socket: CompletionStage<Integer> không phải thông điệp hoàn chỉnh

~~~java
static CompletionStage<Integer> readOnce(
        AsynchronousSocketChannel channel, ByteBuffer dst) {
    return fromCallback(handler ->
        channel.read(dst, null, handler));
}
~~~

Sau khi `readOnce` thành công, kiểm tra n: `-1` là EOF của luồng đọc; số dương là số byte mới nhận, có thể chỉ là **một phần** của frame hoặc thông điệp. TCP truyền byte stream, không lưu ranh giới message. Hãy xây protocol: ví dụ 4 byte độ dài + đọc đủ payload; hoặc đọc tới dấu phân cách. Không được coi một callback `completed()` là “đã nhận một request đầy đủ”.

### Ghi socket: phải tính đến partial write

`AsynchronousSocketChannel.write` hoàn tất một thao tác với số byte thực sự ghi; có thể còn byte trong `src` (kiểm tra `src.hasRemaining()`). Nếu mục tiêu là “gửi hết thông điệp”, nối các lần `write` đến khi buffer cạn rồi mới `complete(null)` cho stage cấp ứng dụng. Tránh thay đổi hay dùng lại buffer khi một operation chưa hoàn tất.

## 6. Ghép stage để tạo luồng xử lý dễ đọc

Giả sử `connectStage`, `readOnce` là hai hàm trên và socket được quản lý ở tầng gọi:

~~~java
// Chỉ minh hoạ một lần đọc; chưa phải bộ đọc đầy đủ một message.
CompletionStage<Integer> pipeline =
    connectStage(channel, remote)
        .thenCompose(unused -> readOnce(channel, dst))
        .thenApply(n -> {
            if (n == -1) {
                throw new IllegalStateException("Peer đã đóng chiều đọc");
            }
            return n;
        });

pipeline.whenComplete((n, error) -> {
    if (error != null) {
        // Ghi log và đóng socket theo chính sách sở hữu.
    } else {
        // n byte đã nhận; flip và xử lý buffer ở đây.
    }
});
~~~

Phân biệt các toán tử:

| Toán tử | Khi dùng | Lưu ý |
| --- | --- | --- |
| `thenApply(T -> U)` | Biến đổi kết quả thuần tuý | Nếu callback ném exception, stage kế tiếp thất bại |
| `thenCompose(T -> CompletionStage<U>)` | Bước sau **bất đồng bộ phụ thuộc** bước trước | “Làm phẳng” stage, không tạo stage lồng nhau |
| `thenCombine(other, (a,b) -> c)` | Ghép hai kết quả độc lập | Cả hai stage phải hoàn tất thành công để tính kết quả |
| `exceptionally(error -> T)` | Phục hồi bằng giá trị dự phòng | Tạo stage thành công nếu hàm phục hồi thành công |
| `handle((value,error) -> U)` | Ánh xạ cả thành công lẫn thất bại | Không dùng khi chỉ muốn quan sát |
| `whenComplete((value,error) -> …)` | Quan sát/log/cleanup | Thường giữ nguyên kết quả hoặc lỗi đầu vào nếu action không phát sinh lỗi mới |

Một phép `thenApply` không nhất thiết chạy trên thread gọi đăng ký stage: khi upstream được hoàn tất, logic phụ thuộc có thể chạy ngay trong thread đang gọi `complete` (thường là thread xử lý completion của NIO). Nếu bước xử lý CPU nặng, dùng `thenApplyAsync(fn, executor)` hoặc `thenComposeAsync(fn, executor)` với executor do ứng dụng quản lý, tránh chiếm worker của completion I/O. `Async` không tự làm I/O nhanh hơn.

Không gọi `join()`/`get()` trong callback của channel để “đợi bước kế tiếp”; việc chặn thread phục vụ callback có thể làm giảm thông lượng hoặc gây bế tắc nếu các công việc phụ thuộc cùng executor.

## 7. Lỗi, timeout và huỷ: ba việc khác nhau

### Exceptional completion

Trong adapter, `failed(Throwable)` phải dùng `completeExceptionally` để downstream nhận cùng nguyên nhân thất bại. Khi gọi `join()` trên stage lỗi, người gọi thường gặp `CompletionException` bao quanh nguyên nhân; `get()` dùng `ExecutionException` và có checked exceptions. Với lỗi trong `thenApply`, chính phép biến đổi đó cũng làm stage tiếp theo lỗi. Không nên tự biến mọi lỗi thành chuỗi rỗng hoặc `null`, vì sẽ che nguyên nhân và nhầm thất bại thành thành công.

### Timeout của future không đồng nghĩa huỷ I/O

~~~java
// stage đọc được tạo từ CompletableFuture do adapter trả về.
CompletableFuture<String> timed =
    readUtf8(path).toCompletableFuture()
        .orTimeout(2, java.util.concurrent.TimeUnit.SECONDS);
~~~

`orTimeout` (Java 9+) làm `CompletableFuture` liên quan hoàn tất bằng `TimeoutException` nếu chưa xong; trong ví dụ này nó tác động lên chính future được adapter tạo. **Nó không tự yêu cầu channel ngừng đọc hay đóng channel.** Nếu thao tác NIO hoàn tất sau timeout, lời gọi `complete(...)` của callback sẽ trả về `false`. Adapter vẫn phải thu dọn tài nguyên khi I/O thật sự kết thúc, hoặc thiết kế một chính sách dừng I/O riêng.

`completeOnTimeout(fallback, …)` cũng hoàn tất future bằng giá trị dự phòng khi hết hạn; thao tác I/O đang chạy không vì vậy tự dừng. Đóng channel để buộc pending I/O thất bại có thể ảnh hưởng **mọi** thao tác đang dùng chung channel. Đừng dùng cơ chế huỷ một request để đóng socket chia sẻ của request khác khi chưa có chính sách sở hữu rõ ràng.

### Cancellation cũng không tự lan qua CompletionHandler

`CompletableFuture.cancel(true)` thường đánh dấu future bị cancel (kết thúc bằng `CancellationException`); với `CompletableFuture`, tham số `mayInterruptIfRunning` không mang nghĩa ngắt một thread đang chạy tác vụ NIO. Nếu adapter không đăng ký thao tác dừng riêng, cancel future **không tự gọi cancel trên operation NIO**. Các API NIO cũng có overload trả `Future<Integer>`: đó là đối tượng khác, với khả năng huỷ cụ thể theo channel/provider. Đừng đánh đồng hai API hay mặc định `cancel()` của một đối tượng này điều khiển đối tượng kia.

Quyết định trước chính sách của ứng dụng: nếu chỉ bỏ qua kết quả muộn, giữ channel sống đến callback và dọn khi hoàn tất; nếu cần hủy I/O thật, tìm biện pháp được API hỗ trợ và xác định tác động tới những operation chia sẻ channel. Mọi đường đóng tài nguyên nên idempotent hoặc có cơ chế đảm bảo đóng đúng một lần nếu nhiều tín hiệu cùng cạnh tranh.

## 8. Những race và lỗi thực tế cần phòng tránh

1. **Quên đường failed:** Chỉ cài `completed` sẽ khiến stage treo vô hạn khi NIO báo lỗi. Cả submission exception lẫn callback `failed` đều phải được xử lý.
2. **Nhầm một callback với dữ liệu đầy đủ:** `read` có thể trả ít byte hơn cần. Xử lý `-1`, `0`, partial read/write và framing của socket hoặc vòng đọc file.
3. **Dùng lại ByteBuffer quá sớm:** Không ghi/`clear`/`flip` buffer từ thread khác trong khi pending I/O còn sử dụng nó. Sau callback, tuân thủ chuyển `position`/`limit` đúng cách.
4. **Đóng channel khi hàm adapter vừa return:** Với I/O bất đồng bộ, `try (channel)` bao trùm riêng lời gọi khởi động rồi return sẽ đóng channel **trước khi callback đến**. Đóng sau completion thật sự hoặc giao ownership cho tầng gọi.
5. **Không rõ ai sở hữu channel:** Adapter mở channel riêng thì nên đóng; adapter nhận socket từ caller thì không tự đóng ở lần `readOnce` thành công. Thiết kế timeout/cancel cũng phụ thuộc ownership đó.
6. **Bỏ sót lỗi đóng tài nguyên:** Nếu cleanup thất bại, ghi nhận lỗi này; tránh đè mất lỗi I/O gốc. `addSuppressed` giữ được cả hai.
7. **Để callback quá nặng:** Khối CPU dài trong callback hay `thenApply` đồng bộ có thể chiếm thread xử lý completion. Chuyển xử lý nặng sang executor thích hợp.
8. **Gộp nhiều lần pending I/O thiếu kiểm soát:** Gửi chồng các lần read trên một `AsynchronousSocketChannel` có thể ném `ReadPendingException`; write tương tự với `WritePendingException`. Chuỗi lần đọc/ghi theo trạng thái operation.
9. **Phản ứng nhầm với future đã timeout/cancel:** `complete` trả `false` nếu stage đã kết thúc, nhưng callback vẫn có thể đến. Đừng chỉ dựa vào việc hoàn tất future để dọn channel.
10. **Tin rằng mọi completion luôn chạy trên một thread cố định:** Không dựa vào thứ tự thread hoặc callback thread để bảo vệ state; chỉ dùng một lần đọc đang chờ, đồng bộ state cần thiết và quản lý executor rõ ràng.

## 9. Cách tự kiểm chứng adapter

Tối thiểu kiểm tra các trường hợp sau khi hiện thực riêng cho mỗi NIO operation:

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| `completed(value)` hợp lệ | Stage thành công, downstream nhận đúng value |
| `failed(cause)` | Stage exceptional, giữ được cause |
| API ném exception ngay khi khởi tạo | Hàm adapter trả stage exceptional; không thất thoát channel đã mở |
| Một read chỉ nhận một phần byte | Tiếp tục đọc đến điều kiện hoàn tất cấp ứng dụng |
| Read trả `-1` | Kết thúc/đánh dấu EOF đúng giao thức |
| Dữ liệu UTF-8 bị cắt giữa hai chunk | Giải mã vẫn đúng sau khi ghép toàn bộ byte hoặc dùng decoder có trạng thái |
| Timeout hoặc caller cancel trước callback | Không nhân đôi kết quả; I/O/tài nguyên được xử lý theo chính sách đã chọn |
| Lỗi close sau lỗi I/O | Lỗi I/O chính vẫn còn, lỗi close xuất hiện trong suppressed exceptions |

Có thể kiểm chứng code hoàn chỉnh ở mục 4 bằng `javac`/`java`, sau đó tăng kích thước file vượt 1.024 byte và chèn nhiều ký tự tiếng Việt để quan sát vòng đọc vẫn ghép đúng. Đối với socket, thử chia payload thành nhiều lần gửi để thấy một lần `read` không nhất thiết tương ứng một thông điệp. Khi test timeout/cancel, dùng điều kiện điều khiển được, không dựa vào may rủi timing của hệ điều hành.

## 10. Ghi nhớ để áp dụng

`CompletionHandler` là cơ chế **nhận tín hiệu hoàn tất từ NIO**; `CompletableFuture` là cơ chế **xuất tín hiệu thành công/lỗi ra luồng xử lý**; `CompletionStage` là giao diện **ghép bước bất đồng bộ**. Việc chuyển đổi đúng bắt đầu từ hai lời gọi `complete`/`completeExceptionally`, nhưng một adapter dùng được trong ứng dụng phải định nghĩa thêm **đơn vị kết quả** (một read hay cả message), **thời điểm đóng tài nguyên**, **đường lỗi đồng bộ**, và **chính sách timeout/cancel**.

Hãy công khai `CompletionStage<T>` khi caller chỉ cần compose; giữ quyền hoàn tất trong adapter. Với NIO, luôn phân biệt **operation đã completed** và **công việc cấp ứng dụng đã hoàn thành**.