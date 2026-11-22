# Không sửa hoặc tái sử dụng buffer khi thao tác chưa hoàn tất trong Java NIO bất đồng bộ

## 1. Nguyên tắc quan trọng nhất

Với I/O đồng bộ, lệnh như `channel.write(buffer)` thường trả về sau khi **lượt ghi đó** kết thúc, nên chương trình có thể xem số byte đã ghi và tiếp tục điều chỉnh buffer. Với I/O bất đồng bộ (asynchronous I/O), các API như `AsynchronousFileChannel.write(...)` hoặc `AsynchronousSocketChannel.read(...)` **khởi tạo** một thao tác rồi trả về `Future` hoặc nhận `CompletionHandler`. Việc sử dụng buffer có thể tiếp diễn **sau khi lời gọi khởi tạo đã trả về**.

Vì vậy phải có quy tắc sở hữu:

> **Từ lúc bắt đầu một thao tác đọc/ghi bất đồng bộ đến khi chính thao tác đó hoàn tất, buffer được truyền vào phải được dành riêng cho thao tác: không đọc, sửa, thay đổi position/limit hay tái sử dụng nó và không để một thao tác I/O bất đồng bộ khác truy cập cùng bộ nhớ backing.**

Quy tắc này áp dụng cho cả:

- **Ghi (`write`):** byte nguồn phải được giữ ổn định; một thread không được `put`, `clear`, `flip` hoặc thay `position/limit` trên buffer nguồn trong lúc thao tác ghi còn pending.
- **Đọc (`read`):** vùng đích đang được hệ thống cập nhật; không đọc dữ liệu trước khi hoàn tất, không viết vào cùng vùng, không `flip` hoặc dùng lại buffer đích khi thao tác đọc còn pending.
- **Heap hay direct buffer:** lựa chọn `ByteBuffer.allocate` / `allocateDirect` không thay đổi quy tắc đồng thời.
- **Buffer view:** `duplicate()`, `slice()` và `asReadOnlyBuffer()` vẫn có thể chia sẻ **cùng backing storage**; cursor độc lập **không** làm vùng byte trở nên độc lập.

Đây không phải chỉ là quy tắc “code đẹp”. Tài liệu Java SE nêu rõ ByteBuffer không an toàn cho truy cập đồng thời trong khi I/O bất đồng bộ còn đang thực hiện. Nếu vi phạm, có thể gửi sai payload, nhận dữ liệu bị ghi đè, tính sai số byte, phát sinh exception, hoặc có lỗi rất khó tái hiện.

## 2. Buffer được ứng dụng giao cho một thao tác I/O

Một `ByteBuffer` có hai thành phần cần quan tâm:

1. **Trạng thái điều khiển:** `position`, `limit`, `capacity`, `mark`, và một số thuộc tính khác.
2. **Vùng dữ liệu:** byte trên heap hoặc off-heap mà buffer nhìn thấy; có thể dùng chung giữa nhiều view.

Ví dụ:

```java
ByteBuffer source = ByteBuffer.wrap(new byte[]{10, 20, 30, 40});
source.position(1);
source.limit(3); // remaining = 2 byte: 20 và 30
```

Đây là đoạn minh họa có `import java.nio.ByteBuffer;`.

Giả sử `write(source)` được khởi tạo tại thời điểm này. Thao tác I/O có thể lấy byte từ vùng `[position, limit)` theo contract của channel; khi hoàn tất, `position` được cập nhật tương ứng số byte đã truyền. Nếu một thread khác tự thay `source.position(0)`, `source.limit(4)` hoặc `source.put(1,(byte)99)` khi thao tác chưa kết thúc, chương trình phá vỡ giả định về **dữ liệu nguồn và vùng còn lại** mà thao tác I/O dùng. Không có cam kết là channel đã copy toàn bộ byte tại đúng thời điểm gọi.

### 2.1. “Lời gọi đã trả về” khác “thao tác đã hoàn tất”

```text
Thread ứng dụng                         Hệ thống I/O / thread hoàn tất
----------------                       ----------------------------
tạo ByteBuffer B
khởi tạo async write(B)  ────────────► thao tác đang pending
nhận Future F
  │                                         │
  ├── KHÔNG sửa hoặc tái sử dụng B           ├── đọc bytes của B
  │                                         └── báo hoàn tất
  ▼
F.get() hoàn tất thành công ◄───────── result: số byte đã ghi
  │
  └── có thể kiểm tra remaining, tiếp tục ghi, hoặc tái sử dụng B
```

Trong thời gian pending, chỉ việc đọc `buffer.position()` để “xem tiến độ” từ thread khác cũng không phải cơ chế an toàn: byte buffer không được thiết kế như công cụ progress concurrent. `Future.isDone()` có thể hữu ích để biết trạng thái Future, nhưng cần xét trường hợp cancelled/failed; **`Future.get()` thành công của chính thao tác** hoặc callback `completed` là ranh giới thông thường để bàn giao quyền sử dụng buffer trở lại.

### 2.2. Kết quả `read` và `write` có thể là từng phần

Với `AsynchronousFileChannel` và `AsynchronousSocketChannel`:

- Đọc vào `ByteBuffer dst` có thể chỉ đọc **một phần** `dst.remaining()`. `result` dương cho biết số byte thực tế; `-1` biểu thị EOF trong điều kiện contract.
- Ghi từ `ByteBuffer src` có thể chỉ ghi **một phần** `src.remaining()`; kết quả trả số byte thực tế.
- Khi có `n > 0`, position của buffer được cập nhật để phản ánh n byte đã xử lý; limit thường không đổi theo mô tả API.
- Nếu cần hoàn tất một message, caller phải thiết kế **chuỗi thao tác kế tiếp**, nhưng chỉ bắt đầu thao tác tiếp theo với cùng buffer **sau khi thao tác trước đã hoàn tất**.

Sơ đồ:

```text
Buffer gửi:          [A B C D E F]
                     ^           ^
                  position      limit

async write #1 ── hoàn tất 2 byte ──► remaining = [C D E F]
async write #2 ── hoàn tất 4 byte ──► remaining = []
                                                    ↑
                                               có thể tái dùng
```

Không đặt `position` thủ công dựa trên một kết quả đang còn pending hoặc suy ra “gọi `write` một lần sẽ ghi hết”.

## 3. Các API bất đồng bộ liên quan

### 3.1. `AsynchronousFileChannel`

`AsynchronousFileChannel` thao tác trên file bằng offset tường minh:

```java
Future<Integer> writeFuture = file.write(src, fileOffset);
Future<Integer> readFuture  = file.read(dst, fileOffset);
```

Đây là hai lời gọi **minh họa độc lập**; `file` phải là `AsynchronousFileChannel` mở đúng quyền và `src`/`dst` là các ByteBuffer thích hợp. Phương thức này **không có file position chung**: mỗi lượt `read/write` truyền `long fileOffset` riêng. Điều đó không làm `ByteBuffer.position()` tự mất ý nghĩa; file offset và vị trí trong buffer là **hai tọa độ khác nhau**.

Overload callback:

```java
file.write(src, fileOffset, attachment, handler);
file.read(dst, fileOffset, attachment, handler);
```

Hai dòng là ví dụ về chữ ký (không phải chương trình biên dịch độc lập): `attachment` là đối tượng do ứng dụng cung cấp, và `handler` là `CompletionHandler<Integer,A>` phù hợp. Tài liệu Java cho phép nhiều lượt read/write outstanding trên cùng `AsynchronousFileChannel`, **nhưng không được dùng cùng một ByteBuffer cho nhiều thao tác I/O concurrent**. Ngoài ra thứ tự hoàn tất các operation và callback không được bảo đảm theo thứ tự bắt đầu. Nếu các thao tác cùng ghi đè vùng file, cần một giao thức riêng.

### 3.2. `AsynchronousSocketChannel`

Socket bất đồng bộ cung cấp:

```java
Future<Integer> fRead  = socket.read(dst);
Future<Integer> fWrite = socket.write(src);
```

Đoạn minh họa với `socket` là `AsynchronousSocketChannel` đã kết nối. Với socket này, **tối đa một read outstanding và một write outstanding tại cùng thời điểm**. Nếu khởi tạo read thứ hai trong khi read trước chưa hoàn tất, có thể ném `ReadPendingException`; tương tự `WritePendingException` cho write thứ hai.

Một read và một write có thể diễn ra đồng thời **khi chúng dùng buffer riêng và ứng dụng phối hợp trạng thái đúng**. Tính thread-safe ở mức channel **không đồng nghĩa** ByteBuffer truyền vào là thread-safe.

### 3.3. `ByteBuffer` không sở hữu kiến thức về lifecycle của channel

`ByteBuffer` không có trạng thái `isInFlight()` hoặc `awaitIo()` được tích hợp. Nếu bạn gọi `src.clear()` hoặc `src.put(...)`, ByteBuffer không tự biết có Future đang sử dụng nó để ngăn chặn. Vì thế trách nhiệm quản lý **ownership** thuộc về ứng dụng.

## 4. Ví dụ sai: sửa buffer ngay sau khi bắt đầu async write

Mã sau cố ý mô tả **lỗi**, không phải chương trình nên chạy trong production:

```java
ByteBuffer payload = ByteBuffer.wrap("FIRST".getBytes(StandardCharsets.US_ASCII));

Future<Integer> pending = channel.write(payload, 0L);

// SAI: thao tác trước vẫn có thể đang dùng payload.
payload.clear();
payload.put("LATER".getBytes(StandardCharsets.US_ASCII));
payload.flip();

int written = pending.get(); // Đợi ở đây là quá muộn.
```

Đoạn minh họa giả định `channel` là `AsynchronousFileChannel` và đã import `ByteBuffer`, `Future`, `StandardCharsets`. Có thể trên một máy nhanh, operation kết thúc trước khi `clear()` chạy nên lỗi **không xuất hiện** trong lần thử đó; nhưng mã vẫn sai vì không có quy tắc đồng bộ và thời điểm I/O hoàn tất không được bảo đảm tại lúc chỉnh buffer.

Những thứ có thể bị ảnh hưởng:

- Content được ghi có thể không phải `FIRST`.
- Position/limit của cùng buffer bị hai phía can thiệp.
- `pending.get()` trả số byte đã ghi nhưng không cung cấp ảnh chụp byte gốc khi buffer đã bị sửa.
- Một test chạy 10.000 lần thành công không chứng minh code an toàn trên mọi OS, executor và tải hệ thống.

**Sửa đúng:** đợi `pending.get()` thành công rồi mới `clear()/put()/flip()` cho lần ghi kế tiếp.

### 4.1. Tại sao `duplicate()` cũng không phải giải pháp nếu vẫn sửa byte gốc?

```java
byte[] data = "FIRST".getBytes(StandardCharsets.US_ASCII);
ByteBuffer original = ByteBuffer.wrap(data);
ByteBuffer view = original.duplicate();

Future<Integer> f = channel.write(view, 0L);

// SAI: view và original chia sẻ cùng bytes.
original.put(0, (byte) 'L');
```

`duplicate()` có position/limit riêng, nhưng **chia sẻ storage**. Tương tự:

- `slice()`: cửa sổ dữ liệu chung.
- `asReadOnlyBuffer()`: view chỉ đọc **qua alias đó**, không ngăn original hoặc array gốc thay bytes.
- `ByteBuffer.wrap(data)`: lưu tham chiếu tới mảng gốc, không sao chép.
- `buffer.array()`: nếu accessible, trả mảng backing, không phải bản copy.

Muốn producer được sửa dữ liệu nguồn trong lúc consumer ghi bất đồng bộ, phải tạo một **snapshot dữ liệu riêng**:

```java
byte[] snapshot = originalBytes.clone();
ByteBuffer owned = ByteBuffer.wrap(snapshot);
Future<Integer> f = channel.write(owned, position);
// Giữ owned và snapshot không bị thay đổi tới khi f hoàn tất.
```

Đoạn minh họa với `originalBytes` và `channel` đã được khai báo; clone với `byte[]` tạo bản sao byte độc lập, nhưng caller vẫn phải bảo đảm không có alias khác sửa `snapshot`. Với một `ByteBuffer` bất kỳ (có thể direct/read-only), sao chép `remaining()` bằng `duplicate().get(...)` **trước khi bắt đầu operation**, khi nguồn ổn định và được sở hữu hợp lệ.

## 5. Ví dụ Java 17+ chạy được: `Future.get()` trước khi tái sử dụng

Ví dụ hoàn chỉnh sau ghi một chuỗi byte vào file tạm bằng `AsynchronousFileChannel`; mỗi lần ghi đợi hoàn tất và xem số byte thực tế rồi mới tiếp tục. Sau đó đọc lại, chờ từng thao tác đọc hoàn tất, và **chỉ cuối cùng mới tái sử dụng buffer nguồn**.

**Tệp:** `AsyncBufferOwnershipDemo.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncBufferOwnershipDemo {
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempFile("async-buffer-", ".bin");

        try {
            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            temp,
                            StandardOpenOption.READ,
                            StandardOpenOption.WRITE)) {

                ByteBuffer outgoing = ByteBuffer.wrap(
                        "ASYNC".getBytes(StandardCharsets.US_ASCII));

                long writePos = 0L;
                while (outgoing.hasRemaining()) {
                    Future<Integer> operation = channel.write(
                            outgoing, writePos);

                    // Từ đây đến get() thành công: KHÔNG truy cập outgoing.
                    int count = operation.get();

                    if (count <= 0) {
                        throw new IOException("No write progress");
                    }
                    writePos += count; // Chỉ cập nhật sau completion.
                }

                System.out.println("written bytes: " + writePos);
                System.out.println("write remaining: "
                        + outgoing.remaining());

                ByteBuffer incoming = ByteBuffer.allocate(16);
                long readPos = 0L;

                while (readPos < writePos) {
                    Future<Integer> operation = channel.read(
                            incoming, readPos);

                    // Tương tự: không đọc/flip incoming khi I/O pending.
                    int count = operation.get();

                    if (count <= 0) {
                        throw new IOException(
                                "Unexpected EOF/no progress");
                    }
                    readPos += count;
                }

                incoming.flip(); // Sau khi lượt read cuối đã xong.
                System.out.println("read bytes: " + readPos);
                System.out.println("content: "
                        + StandardCharsets.US_ASCII.decode(incoming));

                // Bây giờ lượt ghi đã hoàn tất nên tái dùng outgoing an toàn.
                outgoing.clear();
                outgoing.put(
                        "LATER".getBytes(StandardCharsets.US_ASCII));
                outgoing.flip();
                System.out.println("reused: "
                        + StandardCharsets.US_ASCII.decode(outgoing));
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac AsyncBufferOwnershipDemo.java
java AsyncBufferOwnershipDemo
```

**Stdout (với hệ thống file tạm hoạt động bình thường):**

```text
written bytes: 5
write remaining: 0
read bytes: 5
content: ASYNC
reused: LATER
```

### 5.1. Phân tích chính xác

1. `Files.createTempFile` tạo file riêng cho demo, không cần mạng hoặc process ngoài.
2. `channel.write(outgoing, writePos)` trả `Future<Integer>`. **Không** chỉnh outgoing trong khoảng đang chờ. `get()` trả số byte đã ghi, đồng thời bảo đảm operation hoàn tất thành công tại thời điểm này.
3. Nếu lượt ghi chỉ xử lý một phần, `outgoing.position()` đã tiến lên theo số byte ghi. Vòng sau dùng `writePos` được cộng đúng số byte đó, tránh ghi đè vùng cũ.
4. Vòng đọc tương tự, sử dụng `incoming` làm destination và từng offset file. Chỉ sau khi đã đọc đủ byte dự kiến và lượt cuối xong mới `flip()` để giải mã.
5. Tái dùng `outgoing` bằng `clear()/put()/flip()` ở cuối là **đúng** vì tất cả các write Future đã hoàn tất trước đó. Việc in `LATER` chỉ thể hiện nội dung buffer mới; demo **không ghi `LATER` vào file**.
6. `try-with-resources` đóng channel sau khi tất cả Future đã hoàn tất. `finally` dọn file tạm. Nếu `get()` ném `InterruptedException` hoặc `ExecutionException`, ví dụ báo lỗi thay vì chạy tiếp như thể thành công; trong ứng dụng production cần giao thức dọn dẹp/điều phối cancellation trước khi tái sử dụng hoặc trả buffer về pool.

**Điểm quan trọng:** vòng lặp gọi `get()` ngay nên ở ví dụ này thread gọi thực tế phải **đợi** completion. API vẫn là asynchronous; cách viết tuần tự này phục vụ dạy về ownership, không phải minh họa tối ưu throughput. Trong chương trình thật, có thể dùng handler hoặc pipeline nhiều **buffer độc lập** để tiếp tục xử lý nghiệp vụ khác trong lúc I/O đang pending.

## 6. Cách đúng với `CompletionHandler`: bàn giao ownership cho callback

Với API callback:

```java
channel.write(payload, 0L, context,
        new CompletionHandler<Integer, Context>() {
            @Override
            public void completed(Integer written, Context ctx) {
                // Thao tác này đã hoàn tất.
                // Xem written, cập nhật offset và ownership.
            }

            @Override
            public void failed(Throwable error, Context ctx) {
                // Báo lỗi và dọn operation/context.
            }
        });
```

Đây là **mã minh họa API**, không phải chương trình biên dịch độc lập: `Context`, `channel`, `payload`, `context` cần được khai báo, với `import java.nio.channels.CompletionHandler;`. Ý tưởng:

- **Trước khi gọi:** chuẩn bị byte hợp lệ, chọn position/limit, có chính sách giữ tham chiếu đến buffer.
- **Khi vừa khởi tạo:** trạng thái buffer thuộc operation. Producer không được sửa, `flip`, `clear`, hoặc trả về pool.
- **Trong `completed`:** xác định số byte thành công, có thể tiếp tục ghi phần còn lại bằng **operation mới trên cùng buffer**, hoặc trả lại quyền cho producer nếu đã xong.
- **Trong `failed`:** báo lỗi và giải quyết trạng thái operation. Với trường hợp timeout/cancellation đặc biệt, phải đọc contract và không tái chế buffer bừa bãi.
- **Ở application layer:** chỉ báo cho caller rằng buffer đã rảnh khi việc dùng nó thực sự kết thúc, không chỉ vì lời gọi `channel.write(...)` đã trả.

### 6.1. Ví dụ helper biên dịch được: chuỗi ghi một `ByteBuffer` đến hết

Để xử lý partial write không chặn caller, helper dưới đây dùng callback để tiếp tục ghi phần `remaining`, và hoàn tất một `CompletableFuture<Void>` chỉ khi toàn bộ bytes đã được ghi (hoặc phát hiện lỗi).

**Tệp:** `AsyncWriteAll.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CompletableFuture;

public final class AsyncWriteAll {
    private AsyncWriteAll() {}

    public static CompletableFuture<Void> writeAll(
            AsynchronousFileChannel channel,
            ByteBuffer owned,
            long startOffset) {

        CompletableFuture<Void> done = new CompletableFuture<>();

        if (startOffset < 0) {
            done.completeExceptionally(
                    new IllegalArgumentException("negative offset"));
            return done;
        }

        if (!owned.hasRemaining()) {
            done.complete(null);
            return done;
        }

        CompletionHandler<Integer, Long> handler =
                new CompletionHandler<>() {
            @Override
            public void completed(Integer count, Long pos) {
                if (count == null || count < 0) {
                    done.completeExceptionally(
                            new IOException("Invalid write result"));
                    return;
                }
                if (count == 0) {
                    // Tránh đệ quy gọi lại lập tức vô hạn khi không tiến độ.
                    done.completeExceptionally(
                            new IOException("No write progress"));
                    return;
                }

                if (!owned.hasRemaining()) {
                    done.complete(null);
                    return;
                }

                try {
                    channel.write(owned, pos + count,
                                  pos + count, this);
                } catch (Throwable failure) {
                    done.completeExceptionally(failure);
                }
            }

            @Override
            public void failed(Throwable error, Long pos) {
                done.completeExceptionally(error);
            }
        };

        try {
            channel.write(owned, startOffset, startOffset, handler);
        } catch (Throwable failure) {
            done.completeExceptionally(failure);
        }

        return done;
    }
}
```

Đây là **helper class có thể biên dịch** bằng `javac AsyncWriteAll.java`, không chứa `main` và không có stdout. Để dùng:

```java
ByteBuffer owned = ByteBuffer.wrap(payload.clone());
CompletableFuture<Void> finished =
        AsyncWriteAll.writeAll(channel, owned, 0L);

// Không đụng tới owned trong lúc finished chưa hoàn tất.
finished.join(); // Chỉ minh họa chờ ở caller.
owned.clear();   // Sau hoàn tất thành công: có thể tái sử dụng.
```

Đoạn caller là ví dụ, yêu cầu `payload` là `byte[]` có dữ liệu, `channel` là AsynchronousFileChannel phù hợp, các import và xử lý trạng thái thất bại. Helper **giả định chỉ một chủ sở hữu** đối với `owned`: không ai khác truy cập bytes hoặc cursor khi `writeAll` đang sử dụng.

**Cẩn thận thực tế:** helper này minh họa cách chain callback, không phải một retry engine đầy đủ. Nó trả lỗi nếu write báo 0 để tránh retry loop vô hạn; production cần timeout, backoff/giám sát và chính sách lỗi thích hợp. Nếu caller dùng `finished.cancel(...)`, việc cancel chính `CompletableFuture` bên ngoài **không tự động hủy các write đã khởi tạo**; không được dùng cancelled state để kết luận vùng buffer đã rảnh. Với lỗi xảy ra trong lúc lên lịch thao tác kế tiếp hoặc đóng channel giữa chừng, phải thiết kế bàn giao lại buffer dựa trên trạng thái I/O thực tế chứ không chỉ là cờ Future của ứng dụng.

### 6.2. Callback chạy trên thread nào?

Đối với `AsynchronousFileChannel`, completion handler được thực thi bằng các thread trong thread pool gắn với channel; trong một số điều kiện khi operation hoàn tất ngay và caller thuộc pool, handler có thể chạy trực tiếp trên thread đó. Không dựa vào một callback luôn chạy trên UI thread, main thread hoặc một thread riêng duy nhất.

Nếu callback phải cập nhật UI, queue ứng dụng, hoặc trạng thái dùng chung, cần bàn giao sang executor/loop phù hợp và bảo đảm synchronization. Lỗi thường gặp là callback hoàn tất I/O đúng rồi lại sửa các object ứng dụng không thread-safe.

## 7. Buffer pool: không được trả buffer về quá sớm

Buffer pool giúp tái sử dụng các vùng nhớ được cấp phát, đặc biệt direct buffer. Nhưng **đưa buffer về pool khi operation còn pending** sẽ cho phép task khác lấy ra và ghi đè vùng bytes mà I/O đang dùng.

**Ví dụ sai:**

```java
ByteBuffer leased = pool.acquire();
prepare(leased);
channel.write(leased, fileOffset); // trả Future chưa hoàn tất
pool.release(leased);              // SAI: release quá sớm
```

Đây là pseudo-code minh họa có `pool`/`prepare` do ứng dụng tự định nghĩa; không phải một Java class độc lập. Nếu buffer được đưa cho task khác, cả vị trí lẫn bytes đều có thể bị thay đổi trong lúc write còn pending.

**Luồng đúng:**

```text
FREE (trong pool)
  └── acquire ──► OWNED_BY_PRODUCER
                      │ prepare
                      └── submit I/O ──► IN_FLIGHT
                                            │
                                            ├── completion + xử lý kết quả
                                            ▼
                                    OWNED_BY_CONSUMER
                                            │ chỉ khi không còn tham chiếu pending
                                            └── release ──► FREE
```

Nguyên tắc:

- Một buffer vật lý chỉ có **một chủ sở hữu độc quyền** trong thời gian một operation đang dùng nó.
- Trả buffer về pool ở **điểm hoàn tất thực sự** (và khi không còn thao tác khác cùng dùng storage), không phải trong `finally` ngay sau khi khởi tạo async I/O.
- Nếu một bản ghi cần nhiều lần write do partial result, buffer vẫn thuộc **cùng một chuỗi operation logic** cho tới khi chuỗi đó thực sự xong.
- Nếu pool chứa các view `slice()/duplicate()` của cùng backing storage, chúng **không** trở thành các buffer độc lập để giao đồng thời. Phải tránh overlap vùng nhớ và có quy tắc ownership theo backing.
- Thất bại, timeout và cancellation cần đường hoàn trả riêng, không được lấy “operation trả exception” làm bằng chứng mọi tác nhân I/O đã ngừng chạm vào buffer.

### 7.1. Khi nào nên copy payload?

Giả sử producer đang dùng một `byte[]` có thể bị thay liên tục, còn I/O cần ghi snapshot của phiên bản hiện tại. Hãy copy tại ranh giới handoff:

```java
byte[] snapshot = producerBytes.clone();
ByteBuffer pendingWrite = ByteBuffer.wrap(snapshot);

Future<Integer> f = asyncFile.write(pendingWrite, 0L);

// Producer tiếp tục sửa producerBytes; pendingWrite vẫn giữ snapshot riêng.
```

Đoạn minh họa yêu cầu producer **không sửa source trong lúc clone đang chạy** nếu snapshot cần nhất quán; clone và handoff vẫn cần phối hợp đúng. Snapshot là byte[] riêng nhưng không cho phép task khác sửa `snapshot` trong lúc I/O sử dụng. Copy có chi phí và không phải lúc nào cần; nếu producer có thể nhường ownership của buffer gốc thì có thể tránh copy.

## 8. Không dùng `slice`/`duplicate`/`asReadOnlyBuffer` để né ràng buộc pending

So sánh các cách tạo buffer:

| Cách tạo | Cursor độc lập? | Bytes chia sẻ? | Có tự giải quyết in-flight ownership? |
|---|---|---|---|
| `ByteBuffer.allocate(n)` hai lần riêng | Có | Không | Có thể giao hai vùng riêng cho hai operation |
| `ByteBuffer.wrap(byte[])` | Cursor riêng của view | Có với mảng gốc | Không |
| `buffer.duplicate()` | Có | Có với buffer gốc | Không |
| `buffer.slice()` | Có | Có với buffer gốc (phần vùng liên quan) | Không |
| `buffer.asReadOnlyBuffer()` | Có | Có với alias writable khác | Không |
| `ByteBuffer.allocateDirect(n)` hai lần riêng | Có | Không giữa hai allocation độc lập | Không tự xử lý vòng đời từng operation |
| Copy bytes vào `byte[]` mới/`ByteBuffer` riêng | Có | Không với nguồn (nếu copy đúng) | Hữu ích nhưng vẫn phải giữ bản sao không bị sửa khi pending |

Ví dụ:

```java
ByteBuffer original =
        ByteBuffer.wrap("HELLO".getBytes(StandardCharsets.US_ASCII));
ByteBuffer view = original.asReadOnlyBuffer();

Future<Integer> f = channel.write(view, 0L);

// SAI: read-only view vẫn nhìn chung byte với original.
original.put(0, (byte) 'X');
```

Read-only chỉ ngăn `view.put(...)`, không ngăn owner sửa bytes qua `original`. Đối với những buffer có `array()`, người giữ tham chiếu mảng cũng có thể sửa bytes bất chấp wrapper read-only; do đó phải kiểm soát nguồn bên dưới.

### 8.1. Không chuyển ByteBuffer sang `byte[]` bằng cách dùng ngay `array()`

`buffer.array()` chỉ dùng được khi backing array truy cập được; direct buffer hoặc read-only heap buffer có thể không cho phép. Hơn nữa array có thể dài hơn vùng `remaining()` cần gửi, và nó chính là storage chia sẻ.

Nếu cần một bản sao độc lập chính xác vùng còn lại trước I/O:

```java
static ByteBuffer copiedRemaining(ByteBuffer source) {
    ByteBuffer reader = source.duplicate();
    byte[] snapshot = new byte[reader.remaining()];
    reader.get(snapshot);
    return ByteBuffer.wrap(snapshot);
}
```

Đoạn trên là **method helper**, dùng được trong class đã import `ByteBuffer`. Nó không thay cursor của `source` và hoạt động cả với direct/read-only buffer; tuy nhiên **caller phải bảo đảm source không bị sửa đồng thời trong chính thời gian copy**. Bản sao độc lập chỉ được giao cho operation khi đã copy xong.

## 9. Timeout, cancellation và failure: góc cạnh nguy hiểm

### 9.1. `Future.get(timeout, unit)` hết thời gian đợi không phải là I/O kết thúc

```java
Future<Integer> f = channel.write(buf, 0L);
try {
    f.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    // Chỉ có nghĩa thread đợi chưa có kết quả trong 100 ms.
    // Không được buf.clear() hoặc trả buf về pool ở đây.
}
```

Đoạn minh họa với `channel` là AsynchronousFileChannel, `buf` thuộc riêng operation và import `Future`, `TimeUnit`, `TimeoutException`. `TimeoutException` ở đây thuộc **lượt chờ Future**, không có nghĩa system I/O đã bị hủy. Thao tác có thể vẫn đang đọc/ghi buffer.

Các bước hợp lý: tiếp tục theo dõi Future hoặc thực hiện policy cancellation/đóng channel có điều phối; chỉ trả vùng bộ nhớ khi biết chắc không còn hoạt động dùng nó. Không lấy điều kiện `f.isDone()==false` hoặc thời gian đã trôi qua làm cơ chế giải phóng.

### 9.2. `Future.cancel(...)` có phải hủy I/O tức thì?

Không được giả định. `Future.cancel(...)` yêu cầu hủy theo hợp đồng Future; khả năng hủy một thao tác I/O đã được chuyển xuống OS phụ thuộc implementation và trạng thái thực tế. Kể cả khi Future chuyển sang trạng thái cancelled, ứng dụng nên **bảo thủ** với tính an toàn của backing memory nếu không có bảo đảm cụ thể rằng I/O nền đã thôi truy cập buffer.

Đặc biệt với `AsynchronousSocketChannel`, tài liệu Java mô tả các trường hợp timeout có thể khiến channel hoặc kết nối nằm trong trạng thái lỗi phụ thuộc implementation; khi timeout, trạng thái của `ByteBuffer` có thể **không xác định**. Cách an toàn trong tình huống như vậy thường là đóng channel theo chính sách, loại buffer khỏi pool để không bị tái sử dụng ngay, và thiết lập kết nối mới khi cần.

**Không** lập luận rằng “đã timeout/cancel” = “chưa byte nào được đọc/ghi” hoặc “buffer còn nguyên”.

### 9.3. `ExecutionException`, `InterruptedException` và trạng thái completion

- `future.get()` thành công: operation hoàn tất và trả kết quả; có thể xử lý buffer ở phía ứng dụng.
- `ExecutionException`: operation kết thúc có lỗi; kiểm tra nguyên nhân, số byte có thể đã thay đổi phụ thuộc API, và policy recovery. Không coi luôn là 0 byte đã truyền.
- `InterruptedException` khi thread đang `get()`: **lượt đợi bị ngắt**; bản thân I/O có thể tiếp tục. Đừng quay lại thao tác lên buffer chỉ vì thread không còn chờ. Thường khôi phục interrupt flag theo policy và giữ quản lý lifecycle.
- `CancellationException`: Future báo trạng thái hủy; đừng tự suy luận an toàn tái sử dụng buffer nếu có rủi ro I/O nền chưa chấm dứt hoàn toàn.
- Đóng channel khi operation đang pending có thể khiến operation kết thúc với `AsynchronousCloseException` hoặc lỗi liên quan theo contract; cần đảm bảo cleanup được điều phối.

Một cấu trúc API tốt thường trả một **handle operation** chứa cả Future/callback và quyền sở hữu buffer, thay vì đưa buffer lên pool ngay trong nhánh catch.

## 10. “Dùng buffer khác” vẫn phải xét vùng nhớ dùng chung

Giả sử có hai view khác object:

```java
byte[] bytes = new byte[1024];
ByteBuffer a = ByteBuffer.wrap(bytes);
ByteBuffer b = ByteBuffer.wrap(bytes);
```

Hai đối tượng `a` và `b` có vị trí riêng nhưng nhìn **cùng byte[]**. Nếu giao chúng cho hai I/O async đồng thời, có thể gây dữ liệu cạnh tranh, đặc biệt một thao tác read và một thao tác write hoặc hai lần write mà producer vẫn can thiệp mảng.

Tương tự, một `ByteBuffer` slice của vùng lớn hơn có thể là hợp lệ để giao nhiều operation **chỉ khi** các phần vùng vật lý hoàn toàn không chồng nhau và code quản lý đúng bounds, owner, trạng thái và lifecycle của từng phần. Không sử dụng identity `a != b` làm bằng chứng memory regions không overlap.

### 10.1. Nhiều operation trên cùng AsynchronousFileChannel

Java cho phép các read/write file operation tồn tại đồng thời và không định nghĩa thứ tự bắt đầu/hoàn tất. Nếu muốn I/O song song:

- Cấp buffer **độc lập** cho từng operation hoặc chia vùng không overlap với ownership rõ ràng.
- Cấp file offset **riêng**, tránh ghi chồng cùng vùng file nếu nghiệp vụ không cho phép.
- Không mặc định callback A xảy ra trước callback B theo thứ tự `write(A)` rồi `write(B)`.
- Khi ghép dữ liệu, dựa vào file offsets và results, không chỉ thứ tự hoàn tất.
- Nếu tạo stream/log tuần tự, có thể cần một writer queue thay vì khởi tạo một loạt ghi async cùng offset rồi hy vọng hệ thống tự sắp thứ tự.

### 10.2. Một read và một write trên socket cùng lúc

`AsynchronousSocketChannel` hỗ trợ đồng thời tối đa một read và một write ở cùng thời điểm, nhưng **hai buffer phải độc lập về ownership**. Dùng một buffer duy nhất cho cả input và output đồng thời là lỗi ngay cả khi socket cho phép hai operation khác hướng diễn ra cùng lúc.

Sử dụng input/output state riêng:

```text
ConnectionState:
   inboundBuffer  → pending read → completed → decode → chuẩn bị lần read mới
   outboundBuffer → pending write → completed → cập nhật remaining → write tiếp
```

Nếu muốn echo byte vừa đọc lại cho client, phải chờ read hoàn tất, `flip` vùng input đúng lúc, rồi **chuyển ownership** của nó sang write hoặc copy vào buffer output. Không khởi tạo read mới trên cùng backing bytes khi write echo vẫn pending.

## 11. Đối chiếu vòng đời buffer giữa đọc và ghi

| Giai đoạn | Buffer đọc (đích) | Buffer ghi (nguồn) |
|---|---|---|
| Chuẩn bị | `clear()` hoặc đặt position/limit tới vùng có thể nhận byte | `flip()` sau bước ghi payload, hoặc `wrap(bytes)` |
| Khởi tạo | `read(dst, ...)` | `write(src, ...)` |
| Đang pending | **Không đọc, sửa, flip, clear, tái sử dụng** | **Không đọc, sửa, flip, clear, tái sử dụng** |
| Hoàn tất thành công | Xem số byte `n`, position đã tiến; `flip()` khi sẵn sàng tiêu thụ | Xem số byte `n`, position đã tiến; nếu `hasRemaining()`, tiếp tục write |
| Kết thúc logical operation | Consume dữ liệu và giải phóng quyền sở hữu khi parser xong | Trả pool hoặc dùng lại khi không còn byte chờ ghi |
| Timeout/cancel/error | Xử lý theo contract, không giả định buffer còn nguyên hoặc nền I/O đã dừng | Cũng vậy; phải giữ chính sách tránh reuse sớm |

**Ví dụ sai phía read:**

```java
ByteBuffer receive = ByteBuffer.allocate(4096);
Future<Integer> f = socket.read(receive);

receive.flip();  // SAI: read có thể chưa ghi byte vào receive.
parse(receive);  // SAI: parse dữ liệu chưa hoàn tất.
```

Snippet có `socket` thuộc `AsynchronousSocketChannel` và `parse` là hàm ứng dụng, không độc lập. Hành vi sai không nhất thiết ném exception; có thể parse được dữ liệu rỗng/cũ, thay limit khiến kết quả read không đúng contract sử dụng.

**Sửa:**

```java
Future<Integer> f = socket.read(receive);
int n = f.get(); // Đợi completion thành công.
if (n > 0) {
    receive.flip();
    parse(receive);
}
```

Đoạn này minh họa caller đồng bộ đợi kết quả; cần import và xử lý checked exceptions. Nếu n = -1, xử lý EOF/đóng kết nối, không parse dữ liệu mới. Nếu n = 0, xử lý retry/event state, không tự giả định đã có thông điệp.

## 12. Asynchronous I/O không đồng nghĩa mọi đoạn code phải đa luồng

`Future.get()` tạo một điểm đợi có kiểm soát; giúp dạy quy tắc ownership nhưng có thể khiến event loop bị chặn nếu dùng liên tục. `CompletionHandler` cho phép caller làm việc khác; tuy nhiên callback phải xử lý thread safety và vòng đời tài nguyên.

Có thể thiết kế một queue `PendingOperation`:

```text
Producer:
    tạo payload/buffer mới
    enqueue request có ownership
    signal I/O worker

I/O worker / async API:
    lấy request
    khởi tạo read/write
    giữ tham chiếu và đánh dấu IN_FLIGHT

Completion callback:
    xử lý result
    nếu còn bytes → khởi tạo operation tiếp theo, vẫn giữ buffer
    nếu kết thúc → signal completion + chuyển ownership/return pool

Error/cancel:
    đi qua cleanup state machine riêng, tránh premature release
```

Khi chuyển ownership qua nhiều thread, cần công cụ Java Memory Model thích hợp: `BlockingQueue`, `CompletableFuture` với callback đã điều phối, hoặc executor/lock. Chỉ dùng biến boolean thường (không volatile/synchronization) để một thread “tự biết” buffer đã rảnh có thể gây race và thiếu memory visibility.

### 12.1. Backpressure tránh tăng số buffer pending vô hạn

Nếu producer tạo dữ liệu nhanh hơn channel ghi, hệ thống có thể tích lũy hàng nghìn buffer và Future:

- Đặt giới hạn số operation outstanding và tổng bytes pending.
- Chặn, giảm tốc hoặc từ chối producer khi vượt quota.
- Dùng pool cố định nhưng **chỉ phát lại buffer đã giải phóng an toàn**.
- Phân biệt “đã enqueue”, “I/O đang pending”, “đã hoàn tất”, và “đã được application xác nhận”.
- Với TCP, việc write hoàn tất nghĩa byte đã được chấp nhận theo semantics channel, **không** có nghĩa peer đã đọc và xử lý toàn bộ message; muốn ACK ở tầng nghiệp vụ cần giao thức riêng.

## 13. Các lỗi thường gặp

1. **Gọi async `write` rồi lập tức `clear()`.** I/O vẫn có thể sử dụng bytes và cursor cũ.
2. **Gọi async `read` rồi `flip()` trước completion.** Có thể thay limit trong khi hệ thống đang ghi vào buffer.
3. **Sửa `byte[]` gốc sau `wrap(array)`** dù ByteBuffer đang được write async sử dụng. Wrap không copy.
4. **Tưởng `duplicate()` tạo storage độc lập.** Nó chỉ tách cursor, vẫn chia sẻ backing bytes.
5. **Tưởng `asReadOnlyBuffer()` đóng băng payload.** Alias writable khác vẫn sửa bytes được.
6. **Dùng direct buffer để bỏ qua quy tắc concurrent access.** Heap/direct đều yêu cầu ownership.
7. **Cho rằng Java channel thread-safe thì ByteBuffer cũng thread-safe.** Hai contract khác nhau.
8. **Gọi hai read hoặc hai write socket khi thao tác trước pending.** `ReadPendingException`/`WritePendingException`.
9. **Ghi socket một lần rồi kết luận message đã gửi hết.** Có thể partial write, cần giữ remaining.
10. **Tái sử dụng file buffer trong nhiều write outstanding.** `AsynchronousFileChannel` cho phép nhiều operation, không cho phép dùng một buffer concurrent an toàn.
11. **Dựa vào callback thứ tự bắt đầu.** Completion handlers file có thể chạy không theo thứ tự submit.
12. **Trả buffer pool trong `finally` bao quanh lời gọi khởi tạo.** Finally chạy ngay khi phương thức khởi tạo trả về, không đợi async completion.
13. **Dùng `get(timeout)` hết hạn như dấu hiệu thao tác đã dừng.** Nó chỉ báo lượt chờ chưa xong.
14. **Hủy Future rồi tái chế buffer ngay.** Không mặc định cancellation bảo đảm backend đã ngừng truy cập memory.
15. **Dùng `Future.isDone()` như dấu hiệu mọi kiểu kết thúc đều an toàn như success.** Cancelled/failed cần policy khác.
16. **Nuốt `InterruptedException` và sửa buffer.** Thread chờ bị ngắt không có nghĩa I/O đã hoàn tất.
17. **Đóng channel rồi lập tức gửi buffer cho I/O khác mà không xét lifecycle/callback.** Operation còn outstanding phải được dọn và xác nhận trạng thái theo contract.
18. **Không quản lý file offsets trong partial file writes.** Dễ ghi lặp/ghi đè hoặc tạo lỗ.
19. **Dùng cùng backing array với hai view khác nhau đồng thời.** Identity object khác không bảo đảm storage độc lập.
20. **Gọi `read` trên read-only ByteBuffer.** Destination phải ghi được; nếu không có thể ném `IllegalArgumentException`.
21. **Tưởng ghi hoàn tất nghĩa dữ liệu file đã durable qua mất điện.** Completion I/O khác `force(true)` và chính sách durability.
22. **Tưởng write TCP hoàn tất nghĩa peer đã nhận/ACK.** Đây là quy tắc tầng truyền thông, không phải application acknowledgment.
23. **Không kiểm tra số byte hoàn tất.** Nếu kết quả khác số bytes mong đợi, phải tiếp tục/ghi nhận EOF/lỗi.
24. **Không phân biệt application queue và in-flight operation.** Buffer có thể vẫn được callback dùng trong một chuỗi writeAll.
25. **Dùng timeout socket rồi vẫn cố đoán buffer còn nguyên.** Contract timeout có thể để buffer/channel trong trạng thái không xác định.

## 14. Tự kiểm tra

**Câu 1.** `AsynchronousFileChannel.write(buffer,pos)` đã trả `Future`. Có thể gọi `buffer.clear()` ngay không?  
**Không.** Future đại diện một operation pending; chỉ an toàn sau khi operation hoàn tất và ownership được bàn giao lại.

**Câu 2.** Dùng `ByteBuffer duplicate = buffer.duplicate()` có an toàn cho writer nếu producer vẫn sửa bytes gốc?  
**Không.** Duplicate có cursor riêng nhưng share backing storage.

**Câu 3.** Có thể bắt đầu một read và một write đồng thời trên `AsynchronousSocketChannel` không?  
**Có**, theo giới hạn một read và một write outstanding, nhưng phải dùng buffer độc lập và điều phối kết nối đúng.

**Câu 4.** `Future.get(100, MILLISECONDS)` ném `TimeoutException`. Buffer có thể được đưa ngay vào pool không?  
**Không.** Thao tác I/O vẫn có thể đang chạy; timeout của lượt chờ không phải completion.

**Câu 5.** `Future.get()` trả 2 cho buffer ban đầu còn 5 byte. Có thể dùng lại buffer cho payload khác ngay không?  
**Chưa nên** nếu logical write phải gửi đủ 5 byte. Sau completion, buffer còn 3 byte; hãy tiếp tục operation mới với đúng offset, chờ xong toàn bộ rồi mới tái dùng.

**Câu 6.** Vì sao `channel.isOpen() == false` không phải là tín hiệu giải phóng mọi buffer pool mà không cần kiểm tra?  
**Vì** close, cancellation và callback/lỗi của các operation outstanding có lifecycle riêng. Cần xử lý trạng thái I/O/callback và bảo đảm không còn truy cập concurrent.

**Câu 7.** `ByteBuffer.wrap(byte[])` có tự sao chép mảng không?  
**Không.** Nó chia sẻ mảng. Nếu caller cần snapshot byte riêng, copy trước khi giao cho I/O.

**Câu 8.** Gọi `read(dst)` trả Future xong; lúc nào nên `dst.flip()` để parse?  
**Sau** khi operation read hoàn tất thành công (và đã xét result/EOF), không phải ngay sau lời gọi khởi tạo.

**Câu 9.** Hai lần write file có buffer riêng, file offset riêng; callback có chắc theo thứ tự gửi không?  
**Không.** `AsynchronousFileChannel` không cam kết thứ tự completion của các operation outstanding.

**Câu 10.** Muốn cấp phát nhiều buffer từ pool mà không tăng memory vô hạn, cần gì?  
**Cần** quota/backpressure và quy tắc chỉ trả buffer khi không còn operation hay alias đang sử dụng nó.

## 15. Tóm tắt áp dụng và tài liệu chính thức

**Quy tắc kiểm tra trước khi tái sử dụng ByteBuffer:**

1. Operation bất đồng bộ nào đang giữ buffer (hoặc bất kỳ view/backing array dùng chung) đã **thực sự hoàn tất** chưa?
2. Đã xử lý kết quả `n`, partial read/write, EOF, lỗi, timeout/cancellation đúng contract chưa?
3. Có một operation kế tiếp trong chuỗi logical read/write vẫn cần giữ buffer không?
4. Có thread, callback, attachment hoặc alias khác còn quyền ghi/đọc concurrent lên cùng bytes không?
5. Chỉ khi quyền sở hữu đã về phía ứng dụng/pool, mới `clear()`, `flip()`, sửa nội dung hoặc đưa buffer cho nhiệm vụ mới.

Một câu cần nhớ: **“Asynchronous I/O mượn buffer cho đến khi hoàn tất; lời gọi khởi tạo trả về không kết thúc lượt mượn.”**

Tài liệu Java SE 21:

- `AsynchronousFileChannel` — nhiều operation, thứ tự completion, cảnh báo không truy cập ByteBuffer trước khi xong: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
- `AsynchronousByteChannel` — partial read/write, buffer ownership và pending exceptions: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html
- `AsynchronousSocketChannel` — một read/one write outstanding, timeout và tình trạng buffer: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- `CompletionHandler` — `completed`/`failed`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html
- `ByteBuffer` — `position`, `limit`, `duplicate`, `slice`, backing array: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `Future` — `get`, cancellation và timeout: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html
