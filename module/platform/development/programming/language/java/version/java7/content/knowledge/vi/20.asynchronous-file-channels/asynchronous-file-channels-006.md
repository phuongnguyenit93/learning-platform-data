# Kênh tệp bất đồng bộ trong Java: Tổ chức nhiều thao tác độc lập và kiểm soát bộ đệm

## 1. Mục tiêu bài học

Giả sử một chương trình xử lý tệp dữ liệu lớn gồm nhiều khối độc lập: đọc các đoạn ở những vị trí khác nhau để tính toán, hoặc ghi bốn đoạn kết quả vào các vùng xác định của cùng một file. Nếu dùng `AsynchronousFileChannel`, chương trình có thể **khởi tạo nhiều thao tác I/O mà không phải đợi từng thao tác hoàn thành trước khi gửi thao tác tiếp theo**.

Tuy nhiên, “bất đồng bộ” không đồng nghĩa “muốn gửi bao nhiêu thao tác cùng lúc cũng được”. Ba nhóm vấn đề quyết định tính đúng đắn:

1. **Vị trí I/O rõ ràng:** mỗi `read`/`write` chỉ định một file offset cụ thể. Các thao tác độc lập không được ghi chồng lên nhau mà thiếu phối hợp.
2. **Quyền sở hữu `ByteBuffer`:** buffer là dữ liệu/điểm nhận dữ liệu của một yêu cầu bất đồng bộ. Trong lúc I/O đang chờ, không sửa, `clear`, `flip`, thay `position/limit` hay tái sử dụng vùng nhớ của buffer đó cho một tác vụ khác.
3. **Quản lý số tác vụ đang chờ (*in-flight*) và vòng đời:** có giới hạn tài nguyên, nhận completion/failure, xử lý đọc/ghi từng phần, EOF, timeout, cancellation và chỉ đóng kênh khi các tác vụ cần hoàn tất đã được xử lý.

Trọng tâm là **`java.nio.channels.AsynchronousFileChannel`**, API NIO.2 có từ Java 7 và **vẫn còn áp dụng trong Java 17+**. Ví dụ hoàn chỉnh sử dụng Java 17+ để dùng `record`, `Set.of` và những tiện ích hiện hành. Các kiến thức cũ/lỗi thời không được dùng làm định hướng chính.

### 1.1. Bài toán minh họa

File nguồn chứa 20 byte ASCII:

```text
Offset:  0    4    8    12   16
         |    |    |     |    |
Dữ liệu: ABCD EFGH IJKL MNOP QRST
```

Các thao tác đọc độc lập:

| Tác vụ | File offset | ByteBuffer capacity | Kết quả mong muốn |
| --- | ---: | ---: | --- |
| R0 | 0 | 4 | `ABCD` |
| R1 | 4 | 4 | `EFGH` |
| R2 | 8 | 4 | `IJKL` |
| R3 | 12 | 4 | `MNOP` |
| R4 | 16 | 4 | `QRST` |

Ở bước ghi, bốn tác vụ tạo file đích:

```text
Offset:  0    4    8    12
Dữ liệu: WXYZ 1234 mnop QRST
Kết quả: WXYZ1234mnopQRST
```

Điều quan trọng: **completion order không nhất thiết trùng submission order**. Ta khôi phục thứ tự logic bằng offset và metadata tác vụ, không dựa vào thread nào hoàn thành trước.

## 2. `AsynchronousFileChannel` hoạt động theo file position tường minh

### 2.1. Mở kênh bất đồng bộ

```java
Path source = Path.of("source.bin");

try (AsynchronousFileChannel channel =
        AsynchronousFileChannel.open(
                source,
                Set.of(StandardOpenOption.READ),
                executor)) {

    // Gửi các yêu cầu đọc ở nhiều vị trí khác nhau.
}
```

Đây là **mã minh họa trong phương thức**, với `executor` là `ExecutorService` đã được tạo, và cần import `java.nio.channels.AsynchronousFileChannel`, `java.nio.file.*`, `java.util.Set`.

Overload `open(Path, Set<? extends OpenOption>, ExecutorService, FileAttribute<?>...)` nhận tập open options và một executor dùng theo triển khai của asynchronous file channel. Tham số `executor` có thể là `null` để provider dùng nhóm thread mặc định, nhưng trong bài ta truyền một pool có giới hạn rõ.

Một kênh chỉ đọc thường dùng `READ`; kênh chỉ ghi dùng `WRITE` cùng `CREATE_NEW` hoặc `CREATE` theo hợp đồng. Không tự cho rằng có quyền viết khi kênh chỉ được mở bằng `READ`.

### 2.2. Hai kiểu API đọc/ghi

Các phương thức trả `Future<Integer>`:

```java
Future<Integer> pendingRead = channel.read(dst, 0L);
Future<Integer> pendingWrite = channel.write(src, 4096L);
```

Các phương thức dùng `CompletionHandler`:

```java
channel.read(dst, 0L, request, handler);
channel.write(src, 4096L, request, handler);
```

Đây là mã minh họa: `dst`/`src` là `ByteBuffer`, `request` là attachment, `handler` có kiểu generic đúng cho kết quả và attachment.

Cả hai cách đều thao tác với **`position` của file tính theo byte**, là đối số `long`. `AsynchronousFileChannel` **không có một file cursor chung tự động tiến như một số cách sử dụng `FileChannel.position()`**. Mỗi request nói rõ bắt đầu tại offset nào. Đây là nền tảng để gửi nhiều yêu cầu độc lập.

### 2.3. File offset khác buffer position

Đừng nhầm:

- **`filePosition`:** vị trí bắt đầu đọc/ghi trong file, tính bằng byte từ đầu file.
- **`buffer.position()`:** số byte đã được đặt vào/lấy khỏi `ByteBuffer` theo trạng thái hiện tại của buffer.
- **`buffer.limit()`:** giới hạn vùng đọc/ghi của buffer.
- **`buffer.capacity()`:** dung lượng được cấp cho buffer, thường không đổi.

Ví dụ:

```java
ByteBuffer dst = ByteBuffer.allocate(4);
channel.read(dst, 12L);
```

Lệnh yêu cầu đọc từ **file offset 12**, ghi dữ liệu nhận được vào buffer từ **`dst.position()` hiện tại**. Nếu đọc được đủ 4 byte, `dst.position()` sẽ tiến tới 4. Tệp không có nghĩa “kênh hiện đang ở offset 16” cho các request khác; lần đọc tiếp theo phải chỉ định offset mới.

## 3. “Nhiều thao tác độc lập” nghĩa là gì?

### 3.1. Độc lập về khoảng byte trên file

Khi bốn yêu cầu ghi sử dụng các vùng **không chồng lấp**:

```text
write A: [0, 4)
write B: [4, 8)
write C: [8, 12)
write D: [12, 16)
```

thì nội dung mỗi vùng được xác định bởi tác vụ của vùng đó. Các khoảng nửa mở `[start, end)` giúp tránh lỗi off-by-one. Không cần ép mọi lần ghi diễn ra theo thứ tự R0 → R1 → R2 → R3 nếu ứng dụng chỉ yêu cầu file cuối có đúng dữ liệu ở đúng vị trí.

**Cẩn thận:** Nếu các thao tác ghi lên **cùng vùng byte** hoặc một thao tác đọc đồng thời một vùng đang được ghi, đừng suy ra thứ tự hay kết quả deterministic nếu không có đồng bộ/giao thức riêng. Việc dùng một `AsynchronousFileChannel` không tạo transaction hay write-order guarantee cho các request chồng lấp.

### 3.2. Độc lập về vùng nhớ của `ByteBuffer`

Mỗi request cần một buffer không bị request khác ghi đè hoặc thay đổi khi còn pending. Ví dụ đúng:

```java
ByteBuffer first = ByteBuffer.allocate(4);
ByteBuffer second = ByteBuffer.allocate(4);

channel.read(first, 0L);
channel.read(second, 4L);
```

Nếu muốn tái sử dụng buffer theo pool, **chỉ trả buffer về pool sau khi thao tác liên quan thật sự hoàn tất** và không còn callback nào sử dụng nó.

Sai:

```java
ByteBuffer shared = ByteBuffer.allocate(4096);

channel.read(shared, 0L);
shared.clear();             // Sai: I/O có thể chưa xong!
channel.read(shared, 4096L); // Sai: hai request tranh cùng buffer.
```

Ngay cả khi hai file offsets không chồng lấp, **buffer offsets có thể chồng lấp**, làm nội dung sai và phá trạng thái `position/limit`.

### 3.3. Độc lập về kết quả và lỗi

Một request đọc từ vùng A có thể thành công trong khi request ghi vùng B thất bại. Nếu dùng `CompletableFuture` cho mỗi task:

- Một task có completion value.
- Một task có exception.
- Tác vụ phối hợp toàn bộ có thể báo fail và cleanup theo policy.
- Không nên đánh dấu toàn job thành công chỉ vì “đã gửi đủ yêu cầu”.

Tương tự, `CompletionHandler.completed(...)` chỉ báo **một thao tác I/O** hoàn tất; chưa chắc **toàn bộ khối logic** đã được đọc/ghi. Cần kiểm tra số byte và buffer còn lại.

## 4. Vòng đời `ByteBuffer` trước, trong và sau I/O

Một `ByteBuffer` có bốn khái niệm:

- `capacity`: tổng dung lượng byte đã cấp.
- `position`: vị trí của phần tử tiếp theo sẽ được đọc/ghi.
- `limit`: chỉ số phần tử đầu tiên không được phép đọc/ghi.
- `mark`: dấu mốc tùy chọn của buffer.

Khi mới `ByteBuffer.allocate(4)`:

```text
position = 0, limit = 4, capacity = 4
        v
[ _ ][ _ ][ _ ][ _ ]
                    ^
                  limit
```

### 4.1. Đọc file vào buffer

```java
ByteBuffer destination = ByteBuffer.allocate(4);
Future<Integer> f = channel.read(destination, 8L);

// Trên thread điều phối, chờ request này hoàn tất.
int bytesRead = f.get();

// Chỉ sau completion mới đọc/flip buffer.
destination.flip();
```

Đây là ví dụ minh họa trong phương thức có xử lý `ExecutionException`/`InterruptedException`, và cần kiểm tra `bytesRead`. `flip()` đặt `limit` bằng `position` hiện tại rồi đặt `position=0` để chuyển từ **chế độ ghi dữ liệu vào buffer** sang **chế độ đọc dữ liệu ra buffer**.

Nếu `read` trả ít byte hơn yêu cầu, `flip()` ngay có thể chỉ cho nội dung partial. Khi muốn đọc đủ một khối, phải **đọc tiếp** (hoặc đánh dấu EOF/partial) trước khi flip.

### 4.2. Ghi buffer ra file

```java
ByteBuffer sourceBuffer = ByteBuffer.wrap(
        "DATA".getBytes(StandardCharsets.US_ASCII));

Future<Integer> f = channel.write(sourceBuffer, 0L);
int bytesWritten = f.get();

// Chỉ khi completion đã được xác nhận mới được reuse.
```

Đây là mã minh họa. Buffer đang ở trạng thái phù hợp để đọc: `position=0, limit=4`. `write` tiêu thụ byte từ buffer, tăng `position` theo số byte đã ghi.

Nếu buffer được điền bằng `put(...)`:

```java
ByteBuffer sourceBuffer = ByteBuffer.allocate(4);
sourceBuffer.put(new byte[]{'D', 'A', 'T', 'A'});
sourceBuffer.flip(); // Chuyển sang chế độ để kênh đọc ra.
```

**Không gọi `clear()` ngay sau khi gửi asynchronous write** chỉ vì method `write` đã trả về; method có thể chỉ vừa **khởi động** thao tác.

### 4.3. Vai trò của `clear()`, `flip()`, `rewind()`, `compact()`

| Method | Biến đổi trạng thái | Dùng khi |
| --- | --- | --- |
| `flip()` | `limit=position`, `position=0` | Chuẩn bị **đọc dữ liệu vừa ghi vào buffer** hoặc gửi buffer đã `put` ra file |
| `clear()` | `position=0`, `limit=capacity` | Chuẩn bị ghi dữ liệu mới vào toàn bộ buffer |
| `rewind()` | `position=0`, giữ `limit` | Đọc lại vùng dữ liệu hiện tại |
| `compact()` | Dồn dữ liệu chưa đọc lên đầu, đặt position sau phần còn lại | Dùng lại buffer với phần dữ liệu chưa tiêu thụ |

**Không có method nào trong bảng tự xóa byte vật lý của buffer hay tự đợi I/O hoàn thành.** Chúng thay đổi trạng thái `position/limit`, và `compact` còn di chuyển nội dung. Chỉ dùng chúng khi không còn tác vụ bất đồng bộ nào sở hữu vùng nhớ cần thao tác.

### 4.4. `duplicate()` và `slice()` có thật sự độc lập?

`ByteBuffer.duplicate()` tạo một view có `position/limit/mark` riêng nhưng **chia sẻ cùng vùng byte bên dưới**. `slice()` cũng tạo view chia sẻ nội dung trong một khoảng con.

Ví dụ:

```java
ByteBuffer root = ByteBuffer.allocate(8);
ByteBuffer view = root.duplicate();

// Dù position của root và view khác nhau,
// chúng vẫn chia sẻ underlying byte storage.
```

Nếu một request ghi vào `root` và request khác ghi vào phần **trùng nhau** qua `view`, data race vẫn tồn tại. Có thể dùng slice cho **các vùng tách biệt thực sự** với hợp đồng ownership chặt, nhưng không nên diễn giải `duplicate` là copy dữ liệu.

Muốn một buffer chứa **bản sao byte độc lập**, phải copy nội dung sang vùng cấp phát khác.

### 4.5. Heap buffer và direct buffer

`ByteBuffer.allocate(...)` tạo heap buffer, trong khi `ByteBuffer.allocateDirect(...)` tạo direct buffer. Direct buffer có thể hữu ích với một số I/O provider, nhưng:

- Không bảo đảm luôn nhanh hơn với mọi workload.
- Chi phí cấp phát/thu hồi bộ nhớ direct có thể cao.
- Nhiều direct buffers đang pending có thể tiêu tốn bộ nhớ ngoài heap.
- Không thay đổi nguyên tắc **không tái sử dụng buffer trước completion**.
- Provider có thể vẫn cần staging/copy nội bộ; không tự hứa zero-copy.

Lựa chọn dựa trên benchmark, lifetime và giới hạn bộ nhớ, không chỉ từ tên “direct”.

## 5. Đọc/ghi từng phần: `Integer` trả về không phải cam kết “đủ khối”

### 5.1. Một lần `read` có thể trả ít byte hơn `remaining()`

`AsynchronousFileChannel.read(dst, offset)` trả `Future<Integer>`; completion count là số byte **thực sự đọc được**. Với buffer còn chỗ, lời gọi vẫn có thể trả nhỏ hơn số byte muốn nhận.

Đặc biệt:

- `n > 0`: buffer đã nhận `n` byte; `position` tiến thêm `n`.
- `n == -1`: đã tới EOF trước khi đọc được byte nào cho thao tác.
- `n == 0`: có thể gặp trong một số tình huống; không được coi đó là “khối đã hoàn tất”.
- `n < -1`: không phải kết quả đọc thông thường của API này.

Nếu bắt buộc đọc đúng 4 byte từ vị trí 8, cần lặp:

```java
ByteBuffer dst = ByteBuffer.allocate(4);
long start = 8L;

while (dst.hasRemaining()) {
    Future<Integer> step = channel.read(
            dst, start + dst.position());

    int n = step.get();

    if (n < 0) {
        throw new EOFException("Not enough input bytes");
    }
    if (n == 0) {
        throw new IOException("Read made no progress");
    }
}

dst.flip();
```

Đây là mã minh họa cho **buffer ban đầu có position 0** và cần import `EOFException`, `ByteBuffer`. Chính sách ném lỗi khi `n==0` chỉ phù hợp với demo muốn tránh vòng lặp không tiến triển; với production có thể chọn retry với giới hạn/thời gian chờ và cancellation, chứ không busy-loop.

**Điểm then chốt của vị trí lần tiếp theo:** `start + dst.position()`, vì `position` đã tăng theo tổng byte đã nhận. Nếu cứ đọc lại từ `start`, ta có thể đọc trùng bytes và làm hỏng logic ghép khối.

### 5.2. Một lần `write` cũng có thể ghi chưa hết buffer

```java
ByteBuffer src = ByteBuffer.wrap(
        "WXYZ".getBytes(StandardCharsets.US_ASCII));
long start = 0L;

while (src.hasRemaining()) {
    Future<Integer> step = channel.write(
            src, start + src.position());

    int n = step.get();

    if (n <= 0) {
        throw new IOException("Write made no progress");
    }
}
```

Cũng là snippet minh họa; `n==0` được coi là lỗi theo demo chứ không hứa API không bao giờ trả 0.

Sau mỗi completion:

- `src.position()` tăng tương ứng.
- `start + src.position()` là file offset cho phần còn lại.
- Chỉ khi `!src.hasRemaining()` thì **toàn bộ buffer đã được tiêu thụ**.

Nếu chỉ xét kết quả của lần `write` đầu tiên và tuyên bố 4 byte đã ghi đủ, chương trình có thể lưu file bị thiếu nội dung trong những tình huống short write.

### 5.3. Tính offset trong producer–consumer phức tạp

Ở ví dụ nhỏ, buffer bắt đầu với `position=0` nên công thức `base + buffer.position()` đúng. Nếu buffer có `position` ban đầu khác 0 hoặc dùng view, offset cần tính:

```java
long nextFilePosition =
        baseFilePosition + (buffer.position() - initialPosition);
```

Đó là lý do một task thực tế nên **lưu offset gốc và position ban đầu** trong attachment, không suy đoán những thông số này từ biến global thay đổi theo thời gian.

Tương tự, các phép cộng offset/length nên kiểm tra overflow và offset âm khi dữ liệu đến từ input chưa tin cậy.

## 6. `CompletionHandler` và attachment: giữ đúng trạng thái từng request

### 6.1. Callback nhận completion của một thao tác

```java
channel.read(buffer, offset, task,
        new CompletionHandler<Integer, Task>() {
            @Override
            public void completed(Integer n, Task t) {
                // Nhận số byte đã đọc và trạng thái task riêng.
            }

            @Override
            public void failed(Throwable error, Task t) {
                // Lỗi I/O của request.
            }
        });
```

Đây là mã minh họa, `Task` là kiểu do ứng dụng tạo, không phải API JDK. `CompletionHandler<V,A>` có hai type parameters: kiểu kết quả và kiểu **attachment**.

Một attachment tốt thường giữ:

- `baseFileOffset` và `initialBufferPosition`.
- `ByteBuffer` thuộc riêng request.
- `CompletableFuture` hoặc callback của nghiệp vụ.
- Số byte dự kiến, số byte đã hoàn thành.
- Mã request/index, trạng thái cancellation khi cần.
- Thời hạn (deadline) hoặc token điều phối được quản lý ngoài I/O.

Nhờ vậy, khi callbacks đến **không theo thứ tự gửi**, chúng vẫn xử lý đúng buffer và offset của chính request.

### 6.2. Vì sao không dùng một biến `ByteBuffer` chung trong lambda?

Ví dụ sai:

```java
ByteBuffer shared = ByteBuffer.allocate(4096);

for (int i = 0; i < 4; i++) {
    channel.read(shared, (long) i * 4096L);
}
```

Nhiều I/O đang chờ cùng tham chiếu `shared`; có thể làm sai dữ liệu/position. Đúng hơn, mỗi vòng cấp một buffer hoặc lấy một buffer **đã được trả về pool sau completion**.

### 6.3. Callback không nên thực hiện công việc CPU/I/O dài

Provider có thể dùng executor/pool để thực hiện I/O và gọi completion handlers. Nếu trong `completed(...)` bạn giải nén file 1 GiB, gọi network blocking hoặc giữ khóa rất lâu, các completions khác có thể bị chậm.

Thiết kế thường tốt hơn:

1. Callback ghi nhận số byte và trạng thái task.
2. Nếu còn byte thì gửi yêu cầu I/O tiếp.
3. Nếu hoàn tất, chuyển dữ liệu/hành động nặng sang executor nghiệp vụ khác.
4. Hoàn thành `CompletableFuture`/giải phóng semaphore permit.
5. Không làm blocking `get()` của một operation khác trên chính pool cần chạy completions.

Tùy provider, callback có thể được gọi bằng thread quản lý khác nhau; **không dựa vào thread-name hay thứ tự callback như một contract**.

## 7. `Future<Integer>`: chủ động chờ hoặc kiểm tra trạng thái

### 7.1. Khi nào `Future` đơn giản hơn?

`Future<Integer> pending = channel.read(dst, position)` phù hợp khi code điều phối có thể thực hiện việc khác, sau đó chờ:

```java
Future<Integer> pending = channel.read(dst, 100L);

// Làm việc độc lập khác ở thread điều phối.

int n = pending.get(5, TimeUnit.SECONDS);
```

Snippet minh họa này cần xử lý `InterruptedException`, `ExecutionException` và `TimeoutException`; `get(timeout)` giúp **thread đợi** không bị block vô hạn theo thời hạn đó.

Nhưng `Future.get()` là thao tác blocking. Nếu gọi ngay sau mỗi submission, ta **đưa workflow trở lại tuần tự** và đánh mất phần lợi ích của việc gửi nhiều request độc lập.

### 7.2. Gửi nhiều request trước rồi mới collect

```java
List<Future<Integer>> pending = new ArrayList<>();
List<ByteBuffer> buffers = new ArrayList<>();

for (int i = 0; i < 4; i++) {
    ByteBuffer dst = ByteBuffer.allocate(4096);
    buffers.add(dst);
    pending.add(channel.read(dst, (long) i * 4096L));
}

for (int i = 0; i < pending.size(); i++) {
    int n = pending.get(i).get();
    // Kiểm tra n; chỉ bây giờ mới xử lý buffer i.
}
```

Đây là **mã minh họa, không phải readFully**: một request có thể trả ít byte hơn `buffer.remaining()`. Nếu cần đọc đầy đủ, phải dùng thêm vòng partial-read, kiểm tra EOF và giới hạn số request đồng thời. Không sử dụng mô hình này nguyên xi để queue hàng triệu buffers.

### 7.3. Timeout và cancel không luôn đồng nghĩa I/O đã dừng hẳn

Nếu `pending.get(timeout)` ném `TimeoutException`, **operation I/O không tự nhiên bị hủy**. Khi `Future.cancel(...)` được gọi, hành vi hủy I/O có thể phụ thuộc provider; không được mặc định bytes đã không được ghi hoặc buffer có thể tái sử dụng ngay.

Trong ứng dụng cần cancellation, phân biệt:

- Thread chờ đã ngừng đợi.
- `Future` báo cancelled.
- I/O thực tế còn tác động đến file/buffer hay đã quiescent.
- Những task và callback liên quan đã kết thúc an toàn hay chưa.

**Không trả buffer dùng lại khi chỉ mới timeout**, nếu chưa có một cơ chế chắc chắn thao tác bất đồng bộ không còn sử dụng buffer.

## 8. Giới hạn số tác vụ in-flight bằng `Semaphore`

Gửi quá nhiều tác vụ cùng lúc có thể gây:

- Hàng ngàn `ByteBuffer` chiếm heap/direct memory.
- Hàng ngàn request/attachment/`CompletableFuture` đang tồn tại.
- Queue executor quá dài.
- Áp lực lên filesystem, disk, page cache.
- Dễ mất kiểm soát khi lỗi hàng loạt hoặc shutdown.

`Semaphore` cung cấp số permit để giới hạn số **request logic đang hoạt động**.

### 8.1. Mẫu acquire trước, release sau completion

```java
Semaphore permits = new Semaphore(2);

for (Request request : requests) {
    permits.acquire(); // Thread điều phối chờ; không phải callback worker.
    CompletableFuture<Result> task = startAsync(request);

    task.whenComplete((result, error) -> {
        permits.release();
    });
}
```

Đây là **pseudocode**: `Request`, `Result` và `startAsync` là abstraction của ứng dụng. Khi code thật có khả năng ném exception **ngay lúc submit**, phải giải phóng permit trong mọi đường lỗi. Nếu tác vụ bị cancel nhưng underlying I/O vẫn chưa quiescent, không được chỉ dựa vào trạng thái CompletableFuture wrapper để quyết định buffer có thể reuse.

Trong ví dụ hoàn chỉnh, `readAsync`/`writeAsync` chuyển lỗi khởi tạo sang `CompletableFuture`; `whenComplete` nhận success/failure và release permit. **Demo không thực hiện cancellation** nên mỗi future hoàn tất sau khi toàn bộ khối logic đã xong hoặc nhận failure.

### 8.2. Không chặn chính executor phục vụ I/O completions

Một lỗi kiến trúc:

```java
// Không nên submit nhiều Runnable như sau lên đúng pool I/O:
// executor.submit(() -> {
//     permits.acquire();
//     channel.read(...).get();  // Có thể khiến pool bị kẹt/chậm.
// });
```

Nếu tất cả threads của pool chặn đợi permit hay `Future.get()`, có thể không còn tài nguyên để thực thi phần công việc/completion cần làm tiến triển, tùy provider.

**Cách tốt hơn:** để thread điều phối độc lập thực hiện backpressure, hoặc dùng hàng đợi bất đồng bộ với giới hạn và callback không blocking. Executor I/O nên tập trung phục vụ I/O/completion; tác vụ nghiệp vụ nặng chuyển sang pool khác khi cần.

### 8.3. Semaphore giới hạn logical requests, không nhất thiết OS operations

Một logical task đọc 1 MiB có thể cần nhiều `read` nhỏ nối tiếp. Nếu giữ permit cho tới khi task **đủ dữ liệu**, giới hạn thật sự là số logical tasks in-flight; nếu release permit sau mỗi partial read rồi lại acquire, thống kê và chính sách có thể khác.

Nên đặt tên và đo metric rõ: `logicalRequestsInFlight`, `pendingIoOperations`, `allocatedBufferBytes`. Một permit không hứa “một OS native request” trong mọi provider.

### 8.4. Có cần giữ đúng thứ tự kết quả không?

Có. Có thể lưu `CompletableFuture` theo **thứ tự request/index** và chờ `CompletableFuture.allOf(...)` trước khi ghép kết quả:

```java
CompletableFuture.allOf(
        tasks.toArray(new CompletableFuture<?>[0]))
        .get(10, TimeUnit.SECONDS);
```

Đây là đoạn minh họa; `tasks` là một danh sách futures đã tạo. `allOf` **không tự gộp giá trị**; sau khi chờ, đọc từng future theo thứ tự index hoặc map offset để ghép.

**Completion order** vẫn tự do: bảo đảm kết quả logic được tạo ra bởi việc lưu index/offset, không bởi may mắn các callback hoàn tất theo thứ tự.

## 9. Ghi song song và tránh chồng lấp vùng byte

### 9.1. Các khoảng file không giao nhau

Ví dụ bốn buffer ghi:

```text
Tác vụ W0: offset  0, bytes WXYZ, phạm vi [0,4)
Tác vụ W1: offset  4, bytes 1234, phạm vi [4,8)
Tác vụ W2: offset  8, bytes mnop, phạm vi [8,12)
Tác vụ W3: offset 12, bytes QRST, phạm vi [12,16)
```

Nếu mỗi task sở hữu buffer riêng và xử lý short write, nội dung file cuối sau tất cả completions có thể kiểm tra bằng `Files.readAllBytes` hoặc `Files.mismatch`.

### 9.2. Ghi chồng lấp: cần policy đồng bộ hoặc từ chối

```text
W0: ghi 8 byte tại offset 0  => [0,8)
W1: ghi 8 byte tại offset 4  => [4,12)
                                    [4,8) giao nhau
```

Nếu không có ordering/locking, phần giao nhau có kết quả phụ thuộc timing. Không gọi việc này là “nhiều tác vụ độc lập”. Muốn sửa cùng vùng, cần serial hóa thay đổi hoặc một giao thức ghi có version và conflict resolution.

### 9.3. Đọc một file đang được cập nhật

Một batch đọc nhiều vùng có thể chạy đồng thời với process khác ghi/xóa/truncate file. Các reads có thể nhìn **những trạng thái khác thời điểm**, không phải snapshot đồng nhất. Nếu cần tính nhất quán, xây dựng snapshot, khóa hoặc copy-on-write/versioned storage theo môi trường.

### 9.4. Chọn kích thước block

Block quá nhỏ tạo rất nhiều completion và overhead; block quá lớn giữ nhiều RAM và có thể ảnh hưởng fairness. Kích thước phù hợp tùy media, provider, workload và mục tiêu latency/throughput. Không có “block 4 KB” hay “direct buffer” luôn tối ưu.

Nên benchmark với các kích thước, số inflight requests, kiểu filesystem và CPU load thực tế; đặt quota bộ nhớ dựa trên `bufferBytes * maxInFlight` và những chi phí phụ khác.

## 10. Lỗi, EOF, close và xử lý failure

### 10.1. Những lỗi cần phân biệt

| Hiện tượng | Nơi phát hiện | Cách phản ứng |
| --- | --- | --- |
| Đọc trả `-1` trước khi đủ khối | Kết quả `read` | EOF không mong đợi, fail/partial theo hợp đồng |
| `read`/`write` trả ít byte | Kết quả completion | Gửi phần còn lại ở offset mới |
| Trả 0 byte, không tiến triển | Kết quả completion | Retry có giới hạn/backoff hoặc fail, không spin vô hạn |
| I/O ném `IOException` | Callback `failed` hoặc `ExecutionException` | Ghi nhận failure, cleanup/đối soát |
| File bị đóng khi I/O pending | Pending I/O có thể thất bại với `AsynchronousCloseException` | Không đóng kênh trước khi tasks hoàn tất theo hợp đồng |
| Thread bị interrupt khi `get`/`acquire` | `InterruptedException` | Tôn trọng cancellation, thường khôi phục interrupt flag |
| `Future.get(timeout)` hết thời gian | `TimeoutException` | Quản lý timed-out operation riêng; không tự reuse buffer |
| Gửi request khi channel đã đóng | `ClosedChannelException` hoặc lỗi theo API | Không submit sau close |
| Ghi vào vùng trùng nhau | Kết quả file phụ thuộc thứ tự thực thi | Phân chia offsets hoặc đồng bộ |
| Không đủ quyền/quota/đĩa | Error từ provider | Không báo success, dọn output/staging theo ownership |

### 10.2. `failed(Throwable,A)` là completion thất bại của request

`CompletionHandler.failed(...)` cần đẩy lỗi về future/collector của request:

```java
@Override
public void failed(Throwable error, ReadTask task) {
    task.done().completeExceptionally(error);
}
```

Đây là đoạn trong một `CompletionHandler` với attachment `ReadTask`. Đừng `System.err.println(error)` rồi không hoàn thành future/callback của nghiệp vụ, vì thread điều phối có thể chờ mãi.

### 10.3. Không đóng `AsynchronousFileChannel` khi còn task cần kết quả

`AsynchronousFileChannel` implements `AutoCloseable` và cần đóng. Nhưng chỉ vì block `try-with-resources` kết thúc không có nghĩa những operations gửi gần cuối đều đã hoàn tất.

Thứ tự an toàn:

1. Gửi các requests mà nghiệp vụ cho phép.
2. Dừng nhận requests mới khi chuẩn bị shutdown.
3. Chờ/đối soát all futures hoặc callbacks theo deadline.
4. Xử lý failures, timeout, cancellation và trạng thái buffer.
5. Đóng kênh.
6. Tắt/đợi executor theo ownership của ứng dụng.

Nếu đóng channel với I/O còn pending, provider có thể hoàn thành chúng bằng failure (ví dụ `AsynchronousCloseException`) và không bảo đảm output đủ như trước. Với app cần kết quả bền vững, còn phải xem xét `force(metaData)`/close, và mức độ bảo đảm storage thực tế.

### 10.4. `force(boolean metaData)` không phải commit transaction

`AsynchronousFileChannel.force(boolean)` là phương thức yêu cầu cập nhật dữ liệu (và có thể metadata) xuống thiết bị lưu trữ, theo contract và khả năng provider. Nó **không biến nhiều writes thành một giao dịch atomic**. Chỉ xem xét sau khi những writes cần thiết đã hoàn thành; nếu cần durability mạnh, đọc kỹ giới hạn của filesystem/network storage.

### 10.5. Không xóa tệp người dùng khi xử lý thất bại

Một demo có thể tạo file tạm và xóa toàn bộ workspace do nó sở hữu. Nhưng trong ứng dụng thực, chỉ rollback/xóa output mà job thực sự có ownership; không xóa source file hay thư mục chung chỉ vì một request bị lỗi. Khi cần thay một file đang tồn tại, dùng staging riêng, verify và publish theo hợp đồng.

## 11. Thiết kế luồng xử lý thực tế

### 11.1. Tách I/O executor và business executor

```text
Request planner
      |
Chia file offsets thành vùng độc lập, kiểm tra không giao nhau
      |
Bounded dispatcher (Semaphore / queue)
      |
AsynchronousFileChannel.read/write
      |
CompletionHandler nhận n / error
      |
+-----+---------------------------------+
| n chưa đủ: submit phần còn lại         |
| n đủ: complete task / release permit  |
| error: fail task / release permit     |
+-----+---------------------------------+
      |
Aggregation theo index/offset
      |
Verify bytes + metadata quan trọng
      |
Publish kết quả / báo lỗi / cleanup
```

Đặt công việc CPU/JSON parsing/compression nặng sang pool nghiệp vụ nếu cần. Callback của FileChannel nên nhanh và không block trên các futures có thể phải chạy trên cùng executor.

### 11.2. Mô hình ownership của buffer

Một task tiến qua trạng thái:

```text
ALLOCATED
    |
BUFFER_PREPARED
    |
SUBMITTED  --- buffer không được sửa hoặc reuse ---
    |
+---+--------------------------------+
| COMPLETED đủ / PARTIAL / FAILED    |
+---+--------------------------------+
    |
PARTIAL -> gửi tiếp với phần còn lại (task vẫn sở hữu buffer)
    |
COMPLETE/ERROR sau khi I/O quiescent
    |
BUFFER_CAN_BE_CONSUMED / RETURNED_TO_POOL
```

**Không coi `Future.cancel(true)` hoặc timeout là một bằng chứng tổng quát rằng I/O thực tế không còn đụng buffer**. Nếu có buffer pool, cần chính sách hủy và xác nhận quiescence rõ ràng.

### 11.3. Metadata của một task

Một kiểu dữ liệu có thể là:

```java
record IoChunk(
        int index,
        long fileOffset,
        int expectedBytes,
        ByteBuffer buffer) {}
```

`record` có từ Java 16; dùng được trong ví dụ Java 17+. Trong production có thể cần `initialPosition`, deadline, status, destination file, retry count, cancellation token.

Không lưu các biến mutable như `currentOffset` vào một singleton dùng chung cho mọi request. Khi completions đến không theo thứ tự, singleton đó làm các tác vụ ảnh hưởng lẫn nhau.

## 12. Chương trình Java 17+ độc lập đã kiểm thử

Chương trình tạo một workspace tạm do chính nó sở hữu:

1. Ghi file nguồn `ABCDEFGHIJKLMNOPQRST` (20 byte ASCII).
2. Mở `AsynchronousFileChannel` đọc với `ExecutorService` 3 threads.
3. Gửi 4 logical read tasks bằng `CompletionHandler`; mỗi task có **ByteBuffer riêng**, offset 0/4/8/12.
4. Dùng `Semaphore(2)` trước khi gửi, release khi future tương ứng hoàn tất; kiểm tra số logical reads inflight không vượt 2.
5. Đồng thời minh họa cách đọc khối cuối `QRST` bằng `Future<Integer>` và vòng short-read.
6. Chờ đủ 4 read tasks, ghép theo **thứ tự index trong danh sách**, không dựa vào callback order.
7. Mở kênh ghi file mới, gửi bốn tasks ở các vùng byte không chồng lấp với buffer riêng, cùng giới hạn 2 inflight writes.
8. Kiểm tra nội dung cuối `WXYZ1234mnopQRST` và bytes khớp kỳ vọng.
9. Đóng channels, shutdown executor, xóa đúng workspace tạm.

**Giới hạn của ví dụ:** Để tránh vòng lặp không tiến triển vô hạn, `n==0` được xem là lỗi theo policy demo; production có thể dùng retry/backoff/deadline. Phần demo không thực hiện cancel và không dùng một `ByteBuffer` cho hai requests cùng lúc. Việc provider thực thi I/O thật sự song song hay dùng worker threads là implementation-dependent; chỉ số max inflight phản ánh logic request, **không phải** đo số native operations đồng thời trong OS.

Tạo tệp **`AsyncIndependentBuffersDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.channels.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class AsyncIndependentBuffersDemo {
    private static final int CHUNK = 4;

    record ReadTask(
            long base,
            ByteBuffer buffer,
            CompletableFuture<String> done) {}

    record WriteTask(
            long base,
            ByteBuffer buffer,
            CompletableFuture<Void> done) {}

    static CompletableFuture<String> readAsync(
            AsynchronousFileChannel channel, long offset, int length) {

        CompletableFuture<String> result = new CompletableFuture<>();

        ReadTask task = new ReadTask(
                offset, ByteBuffer.allocate(length), result);

        CompletionHandler<Integer, ReadTask> handler =
                new CompletionHandler<Integer, ReadTask>() {

            @Override
            public void completed(Integer count, ReadTask t) {
                if (count == null || count < 0) {
                    t.done().completeExceptionally(
                            new EOFException("Not enough bytes"));
                    return;
                }

                if (count == 0) {
                    t.done().completeExceptionally(
                            new IOException("Read made no progress"));
                    return;
                }

                if (t.buffer().hasRemaining()) {
                    try {
                        channel.read(
                                t.buffer(),
                                t.base() + t.buffer().position(),
                                t, this);
                    } catch (RuntimeException e) {
                        t.done().completeExceptionally(e);
                    }
                } else {
                    t.buffer().flip();

                    byte[] bytes = new byte[
                            t.buffer().remaining()];

                    t.buffer().get(bytes);

                    t.done().complete(
                            new String(bytes,
                                    StandardCharsets.US_ASCII));
                }
            }

            @Override
            public void failed(Throwable error, ReadTask t) {
                t.done().completeExceptionally(error);
            }
        };

        try {
            channel.read(task.buffer(), offset, task, handler);
        } catch (RuntimeException e) {
            result.completeExceptionally(e);
        }

        return result;
    }

    static CompletableFuture<Void> writeAsync(
            AsynchronousFileChannel channel, long offset, String value) {

        CompletableFuture<Void> result = new CompletableFuture<>();

        WriteTask task = new WriteTask(
                offset,
                ByteBuffer.wrap(
                        value.getBytes(StandardCharsets.US_ASCII)),
                result);

        CompletionHandler<Integer, WriteTask> handler =
                new CompletionHandler<Integer, WriteTask>() {

            @Override
            public void completed(Integer count, WriteTask t) {
                if (count == null || count <= 0) {
                    t.done().completeExceptionally(
                            new IOException("Write made no progress"));
                    return;
                }

                if (t.buffer().hasRemaining()) {
                    try {
                        channel.write(
                                t.buffer(),
                                t.base() + t.buffer().position(),
                                t, this);
                    } catch (RuntimeException e) {
                        t.done().completeExceptionally(e);
                    }
                } else {
                    t.done().complete(null);
                }
            }

            @Override
            public void failed(Throwable error, WriteTask t) {
                t.done().completeExceptionally(error);
            }
        };

        try {
            channel.write(task.buffer(), offset, task, handler);
        } catch (RuntimeException e) {
            result.completeExceptionally(e);
        }

        return result;
    }

    static String readWithFutures(
            AsynchronousFileChannel channel,
            long offset, int length) throws Exception {

        ByteBuffer buffer = ByteBuffer.allocate(length);

        while (buffer.hasRemaining()) {
            Future<Integer> step = channel.read(
                    buffer, offset + buffer.position());

            int n = step.get(5, TimeUnit.SECONDS);

            if (n < 0) {
                throw new EOFException("Unexpected EOF");
            }

            if (n == 0) {
                throw new IOException("Read made no progress");
            }
        }

        buffer.flip();
        return StandardCharsets.US_ASCII.decode(buffer).toString();
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error) throws IOException {
                if (error != null) throw error;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws Exception {
        Path work =
                Files.createTempDirectory("async-buffers-");

        try {
            Path source = work.resolve("source.bin");
            Path target = work.resolve("target.bin");

            Files.writeString(
                    source, "ABCDEFGHIJKLMNOPQRST",
                    StandardCharsets.US_ASCII);

            ExecutorService pool =
                    Executors.newFixedThreadPool(3);

            try {
                List<CompletableFuture<String>> reads =
                        new ArrayList<>();

                Semaphore readPermits = new Semaphore(2);
                AtomicInteger activeReads = new AtomicInteger();
                AtomicInteger maxReads = new AtomicInteger();

                try (AsynchronousFileChannel in =
                        AsynchronousFileChannel.open(
                                source,
                                Set.of(StandardOpenOption.READ),
                                pool)) {

                    for (int i = 0; i < 4; i++) {
                        readPermits.acquire();

                        int n = activeReads.incrementAndGet();
                        maxReads.accumulateAndGet(n, Math::max);

                        CompletableFuture<String> f =
                                readAsync(in,
                                        (long) i * CHUNK,
                                        CHUNK);

                        f.whenComplete((value, error) -> {
                            activeReads.decrementAndGet();
                            readPermits.release();
                        });

                        reads.add(f);
                    }

                    String byFuture =
                            readWithFutures(in, 16, CHUNK);

                    CompletableFuture.allOf(
                            reads.toArray(
                                    new CompletableFuture<?>[0]))
                            .get(10, TimeUnit.SECONDS);

                    List<String> values = new ArrayList<>();

                    for (CompletableFuture<String> f : reads) {
                        values.add(f.join());
                    }

                    String blocks = String.join("|", values);

                    boolean bounded = maxReads.get() <= 2
                            && activeReads.get() == 0;

                    System.out.println("read.blocks=" + blocks);
                    System.out.println("read.future=" + byFuture);
                    System.out.println(
                            "read.maxInFlightAtMost2=" + bounded);

                    check(blocks.equals("ABCD|EFGH|IJKL|MNOP")
                            && byFuture.equals("QRST")
                            && bounded,
                            "independent reads");
                }

                String[] pieces = {
                        "WXYZ", "1234", "mnop", "QRST"
                };

                List<CompletableFuture<Void>> writes =
                        new ArrayList<>();

                Semaphore writePermits = new Semaphore(2);
                AtomicInteger activeWrites = new AtomicInteger();
                AtomicInteger maxWrites = new AtomicInteger();

                try (AsynchronousFileChannel out =
                        AsynchronousFileChannel.open(
                                target,
                                Set.of(
                                        StandardOpenOption.CREATE_NEW,
                                        StandardOpenOption.WRITE),
                                pool)) {

                    for (int i = 0; i < pieces.length; i++) {
                        writePermits.acquire();

                        int n = activeWrites.incrementAndGet();
                        maxWrites.accumulateAndGet(n, Math::max);

                        CompletableFuture<Void> f =
                                writeAsync(
                                        out,
                                        (long) i * CHUNK,
                                        pieces[i]);

                        f.whenComplete((value, error) -> {
                            activeWrites.decrementAndGet();
                            writePermits.release();
                        });

                        writes.add(f);
                    }

                    CompletableFuture.allOf(
                            writes.toArray(
                                    new CompletableFuture<?>[0]))
                            .get(10, TimeUnit.SECONDS);
                }

                String written = Files.readString(
                        target, StandardCharsets.US_ASCII);

                boolean writesBounded =
                        maxWrites.get() <= 2
                        && activeWrites.get() == 0;

                boolean bytesEqual = Arrays.equals(
                        Files.readAllBytes(target),
                        "WXYZ1234mnopQRST".getBytes(
                                StandardCharsets.US_ASCII));

                System.out.println("write.result=" + written);
                System.out.println(
                        "write.maxInFlightAtMost2=" + writesBounded);
                System.out.println(
                        "write.bytesEqual=" + bytesEqual);

                check(written.equals("WXYZ1234mnopQRST")
                        && bytesEqual
                        && writesBounded,
                        "independent writes");

                System.out.println("checks=PASS");
            } finally {
                pool.shutdown();

                if (!pool.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        } finally {
            deleteTree(work);
        }

        System.out.println(
                "workspace.cleaned=" + !Files.exists(work));
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 AsyncIndependentBuffersDemo.java
java AsyncIndependentBuffersDemo
```

**Stdout đã được kiểm chứng thực tế bằng `javac`/`java` trên JDK 17+:**

```text
read.blocks=ABCD|EFGH|IJKL|MNOP
read.future=QRST
read.maxInFlightAtMost2=true
write.result=WXYZ1234mnopQRST
write.maxInFlightAtMost2=true
write.bytesEqual=true
checks=PASS
workspace.cleaned=true
```

### 12.1. Ý nghĩa `read.blocks=ABCD|EFGH|IJKL|MNOP`

Bốn tasks đọc được gửi ở các vị trí `0`, `4`, `8` và `12`, mỗi task có một `ByteBuffer.allocate(4)` và một `CompletableFuture<String>`. Dù callback có thể hoàn thành theo thứ tự bất kỳ, chương trình lưu futures theo **index đã submit**, chờ tất cả rồi lấy giá trị đúng thứ tự đó.

### 12.2. Ý nghĩa `read.future=QRST`

Đây là khối thứ năm ở file offset `16`, được đọc bằng API `Future<Integer>`. Method `readWithFutures` dùng vòng lặp theo `ByteBuffer.position()` để đảm bảo nhận đủ 4 byte hoặc báo lỗi, chứ không tin một lần `read` sẽ luôn đủ.

### 12.3. Ý nghĩa `read.maxInFlightAtMost2=true`

`Semaphore(2)` buộc thread điều phối phải nhận permit trước khi gửi một logical task đọc mới. `AtomicInteger` theo dõi các logical tasks đang đợi kết quả; khi future kết thúc, callback ngắn giải phóng permit.

Điều kiện `maxReads.get() <= 2 && activeReads.get() == 0` xác minh không vượt hai và không còn task đang hoạt động sau khi chờ. **Không tuyên bố đã chạy đúng hai native reads đồng thời**: giá trị peak có thể 1 hoặc 2 tùy lịch I/O thực tế.

### 12.4. Ý nghĩa nhóm `write`

Bốn buffer độc lập lần lượt chứa `WXYZ`, `1234`, `mnop` và `QRST`, ghi vào các offset `0`, `4`, `8`, `12`. Mỗi task có callback xử lý short write bằng cách gửi tiếp tại `base + buffer.position()`.

Khi mọi futures hoàn tất, chương trình đóng kênh, đọc file đích và xác minh bytes bằng `Arrays.equals`. Vì các vùng **không giao nhau**, file cuối không phụ thuộc thứ tự thực thi của các requests.

### 12.5. Vì sao chương trình dùng `CountDownLatch` hay `Thread.sleep`?

**Chương trình không cần hai kỹ thuật đó.** `CompletableFuture.allOf` bảo đảm phương thức điều phối chỉ tiếp tục khi các logical tasks tương ứng đã hoàn tất, còn `Semaphore` giới hạn số in-flight. `Thread.sleep` không phải cơ chế đáng tin để xác định một I/O asynchronous đã xong.

### 12.6. Giới hạn cần nhớ khi đưa vào production

Chương trình dùng một thư mục tạm, một file nhỏ, vùng ghi tách biệt và không thực hiện cancellation. Một pipeline thật cần quản lý:

- Fail-fast hoặc collect-all errors.
- Timeout, cancellation và khi nào buffer thật sự được trả về pool.
- Dung lượng buffer/queue tối đa.
- Kiểm tra permissions/quota và thay đổi file trong lúc đọc.
- Kiểm tra tính nhất quán/atomic publish nếu thay file quan trọng.
- Các thao tác partial/zero progress theo policy có retry giới hạn.
- Kênh có bị đóng khi task còn pending hay không.
- Bảo đảm final output theo contract, không chỉ dựa vào futures done.

## 13. Kiểm thử unit và integration cho nhiều yêu cầu I/O

### 13.1. Các trường hợp tính đúng đắn

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Một chunk ở offset 0 | Đọc/ghi byte đúng |
| Nhiều chunks không giao nhau | Ghép lại đúng nội dung dù callback không theo thứ tự |
| Buffer có position ban đầu khác 0 | Offset tiến đúng theo `position-initialPosition` |
| Short read | Task tiếp tục với buffer remaining |
| EOF trước khi đủ khối | Task báo EOF/partial theo contract |
| Short write | Task tiếp tục ở offset đúng, không ghi trùng |
| `n==0` | Retry/backoff hoặc fail có giới hạn, không spin |
| Một request thất bại | Logical future hoàn thành exceptionally |
| Nhiều requests, Semaphore(2) | Không vượt 2 logical tasks in-flight |
| File đích đã tồn tại với `CREATE_NEW` | Không ghi đè bất ngờ |
| Callback đến thứ tự đảo ngược | Kết quả vẫn ghép theo index/offset |
| Kênh đóng giữa chừng | Tác vụ được báo lỗi theo provider, không thành công giả |
| Buffer bị tái sử dụng quá sớm (test giám sát ownership) | Từ chối hoặc phát hiện bug |
| Executor shutdown sau khi xong | Không rò threads và tài nguyên |

### 13.2. Không nên phụ thuộc vào thứ tự completion

Trong integration test, không nên assert “task offset 0 luôn hoàn thành trước task offset 4”. Hãy assert **output bytes** và kết quả của từng task được map theo metadata, không phụ thuộc scheduling.

Cũng không nên assert “chạy song song phải nhanh gấp 4 lần”: OS, cache, thiết bị, executor, file system provider và kích thước dữ liệu khác nhau có thể làm throughput tăng, giảm hoặc tương đương.

### 13.3. Kiểm thử áp lực tài nguyên

Thử với:

- Nhiều chunks nhỏ và chunks lớn.
- Giới hạn in-flight 1, 2, 4, 8 dưới cùng workload.
- Heap vs direct buffers.
- Slow I/O/provider giả lập.
- Cancellation đúng lúc I/O pending.
- Một task callback fail, những task khác vẫn đang hoạt động.
- Network/file store mất kết nối (nếu provider phù hợp).
- Pool nhỏ và business queue lớn để kiểm tra deadlock/backpressure.
- File bị thay đổi kích thước trong lúc đọc.

Không cần làm đầy đĩa hoặc làm hỏng file người dùng; tạo dữ liệu thử riêng và fault injection ở tầng abstraction.

## 14. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng một `ByteBuffer` cho nhiều asynchronous operations | Data race, position/limit sai | Buffer riêng cho mỗi task hoặc pool với ownership |
| Gọi `clear()` sau khi submit | Thay vị trí buffer khi I/O pending | Chỉ clear sau completion thật |
| Coi `duplicate/slice` là copy nội dung | Các views vẫn chia sẻ storage | Kiểm soát vùng không chồng lấp hoặc copy bytes |
| Dùng buffer chưa `flip()` sau `put()` rồi ghi | Ghi sai phạm vi hoặc 0 byte | Flip trước khi channel tiêu thụ |
| Quên `flip()` sau khi đọc đầy đủ | Đọc từ cuối buffer, ra rỗng | Flip sau completion và đủ dữ liệu |
| Giả định một `read` đủ `remaining()` | Thiếu bytes | Lặp ở offset mới |
| Giả định một `write` ghi hết | File thiếu nội dung | Xử lý short write |
| Lặp lại cùng file offset khi partial read | Đọc trùng vùng | `base + buffer.position()` khi initial position 0 |
| Ghi vào các vùng trùng nhau không đồng bộ | Kết quả phụ thuộc timing | Phân vùng không giao nhau hoặc serial hóa |
| Gửi toàn bộ hàng triệu tasks một lúc | Cạn bộ nhớ/queue | Bounded in-flight bằng Semaphore/dispatcher |
| Gọi `Future.get` ngay sau từng submit | Tuần tự hóa workflow | Submit có kiểm soát trước, collect sau |
| Chặn I/O executor bằng nhiều `get/acquire` | Nguy cơ deadlock/chậm | Điều phối ở thread khác, callback nhẹ |
| Đọc buffer trước khi completion | Nội dung chưa đáng tin | Chỉ tiêu thụ sau done |
| Bỏ qua `failed(Throwable)` | Future nghiệp vụ có thể chờ mãi | Complete exceptionally và cleanup |
| Coi timeout là đã hủy I/O | Reuse buffer/file sai | Quản lý cancellation và quiescence |
| Đóng channel khi task còn pending | Tác vụ có thể thất bại | Chờ hoặc hủy có chủ đích rồi đóng |
| Tin các reads là snapshot toàn file | Source có thể đổi trong lúc đọc | Snapshot/locking/versioning nếu cần |
| Coi direct buffer luôn tối ưu | Có thể tốn native memory, chậm hơn | Benchmark thực tế |
| Tưởng `AsynchronousFileChannel` bảo đảm native nonblocking I/O | Provider có thể dùng worker threads | Đo hành vi trên platform |
| Dọn cả thư mục đầu vào khi lỗi | Mất dữ liệu không thuộc job | Chỉ cleanup staging do job sở hữu |

## 15. Câu hỏi ôn tập

**Câu 1.** Vì sao `AsynchronousFileChannel` thích hợp cho nhiều yêu cầu đọc ở những phần khác nhau của file?  
**Đáp án:** Mỗi `read` chỉ định file offset tường minh và có kết quả bất đồng bộ riêng. Không cần dùng một file cursor chung.

**Câu 2.** Hai tasks đọc ở offsets khác nhau có thể dùng cùng một `ByteBuffer` không?  
**Đáp án:** Không nên khi chúng còn pending. Cần buffer/vùng nhớ độc lập để tránh tranh nội dung và position/limit.

**Câu 3.** Sau khi gọi `channel.read(dst, offset)` trả về `Future`, được `dst.flip()` ngay chưa?  
**Đáp án:** Chưa. Đợi request hoàn thành, xử lý short read/EOF và chỉ flip khi đã có dữ liệu muốn tiêu thụ.

**Câu 4.** `ByteBuffer.duplicate()` có tạo bản sao bytes độc lập không?  
**Đáp án:** Không. Nó tạo view với state riêng nhưng **chia sẻ underlying storage**.

**Câu 5.** Một lần `write` báo đã ghi 2 byte cho buffer 4 byte, bước tiếp theo là gì?  
**Đáp án:** Gửi tiếp 2 byte còn lại ở `base + bytesWritten` (hoặc `base + buffer.position()` khi initial position 0).

**Câu 6.** `Future.get()` có phải API không blocking?  
**Đáp án:** Không. `get()` chờ kết quả; chính lời gọi `read/write` mới trả sớm để điều phối có thể làm công việc khác.

**Câu 7.** Vì sao `Semaphore(2)` có ích?  
**Đáp án:** Nó giới hạn số logical requests in-flight, giảm áp lực bộ nhớ, thread pool và queue I/O.

**Câu 8.** `Semaphore` có tự bảo đảm chỉ đúng hai tác vụ I/O của OS đang chạy không?  
**Đáp án:** Không. Nó giới hạn theo cách ứng dụng acquire/release permits; provider có thể thực hiện I/O theo cơ chế riêng.

**Câu 9.** Completion của offset 8 đến trước offset 0 có làm file sai không?  
**Đáp án:** Không, nếu các writes không giao nhau và từng task quản lý đúng offset/buffer; kết quả đọc được ghép theo index/offset.

**Câu 10.** Nếu một `CompletableFuture` bị cancel, có được trả `ByteBuffer` về pool ngay không?  
**Đáp án:** Không được tự giả định như vậy. Cần biết I/O nền đã thật sự chấm dứt/không còn truy cập buffer theo provider/policy.

**Câu 11.** Có thể đặt `CompletionHandler` làm công việc parse một file rất lớn không?  
**Đáp án:** Không nên chặn thread phục vụ I/O completion lâu; chuyển công việc nặng sang worker khác khi cần.

**Câu 12.** Vì sao phải kiểm tra `n==0` ở vòng partial read/write?  
**Đáp án:** Nếu không tiến triển mà vẫn lặp ngay, ứng dụng có thể spin vô hạn. Cần policy retry giới hạn/backoff/timeout hoặc fail.

**Câu 13.** `AsynchronousFileChannel` có tự tạo snapshot nhất quán khi file khác bị sửa đồng thời không?  
**Đáp án:** Không. Các chunk có thể được đọc từ những trạng thái khác nhau; cần storage snapshot hoặc phối hợp riêng nếu nghiệp vụ yêu cầu.

**Câu 14.** Trong ví dụ, vì sao kết quả `read.blocks` có thứ tự ổn định?  
**Đáp án:** Do danh sách futures được giữ theo thứ tự submission/index và được ghép theo thứ tự đó, không phải do completion callback luôn theo cùng thứ tự.

**Câu 15.** Khi nào được đóng channel và shutdown pool?  
**Đáp án:** Khi đã xử lý trạng thái/đầu ra của những requests cần hoàn tất (hoặc đã có policy cancellation/quiescence) và sẽ không submit request mới.

## 16. Checklist trước khi dùng cho hệ thống thật

- [ ] Đã tách file thành các vùng byte rõ ràng, không ghi chồng lấp vô ý.
- [ ] Mỗi logical task có id/index, file offset, buffer và completion riêng.
- [ ] Không cho hai I/O pending cùng sửa/tiêu thụ vùng nhớ buffer bị chia sẻ.
- [ ] Với buffer lấy từ pool, chỉ trả về sau khi I/O đã thật sự quiescent.
- [ ] Đã phân biệt file offset và `ByteBuffer.position()/limit()`.
- [ ] Trước write, buffer chứa bytes cần ghi và `position/limit` chính xác.
- [ ] Sau read, đã kiểm tra số byte thực và chỉ `flip()` khi chuẩn bị consume.
- [ ] Đã xử lý short reads, EOF, zero progress và short writes.
- [ ] Có bound số tasks in-flight, tổng memory và queue.
- [ ] Không `Future.get()` ngay sau từng submit một cách vô tình tuần tự hóa.
- [ ] Không block pool phục vụ I/O/completion bằng công việc nặng hay chờ vô hạn.
- [ ] Errors được truyền về caller; không để future nghiệp vụ chờ mãi.
- [ ] Có timeout và cancellation policy không tái sử dụng buffer trước quiescence.
- [ ] Mọi task completion được xác minh trước khi đóng channel/publish file.
- [ ] ExecutorService được shutdown/await theo ownership.
- [ ] Khi đọc file đang thay đổi, có policy consistency rõ.
- [ ] Khi cập nhật file quan trọng, có staging/verify/publish và recovery.
- [ ] Có unit tests cho partial, EOF, offsets, buffer ownership và giới hạn in-flight.
- [ ] Có integration tests trên filesystem/provider thực tế.
- [ ] Không hứa asynchronous luôn chạy nhanh hơn hoặc native nonblocking trên mọi máy.

## 17. Kết luận và tài liệu chính thức còn hiệu lực

**Tổ chức nhiều thao tác độc lập với `AsynchronousFileChannel` có ba lớp bảo đảm phải tự xây:**

1. **Tính đúng theo file offset:** mỗi request đọc/ghi đúng vùng byte; thao tác ghi không giao nhau hoặc được phối hợp.
2. **Tính đúng theo `ByteBuffer`:** mỗi request có buffer/vùng nhớ thuộc quyền sở hữu rõ ràng; không `flip/clear/reuse` khi I/O còn pending; xử lý short read/write và EOF.
3. **Quản lý tài nguyên/vòng đời:** giới hạn request in-flight, nhận completion/failure, tổ chức pool, cancellation, close/force và verify output.

`CompletionHandler` thích hợp cho pipeline không blocking ở thread điều phối; `Future<Integer>` phù hợp khi cần giữ handle rồi đợi/kiểm tra về sau. Dùng `Semaphore` hoặc bounded dispatcher để tránh queue vô hạn. Kết quả bất đồng bộ có thể hoàn thành sai khác thứ tự, vì vậy **index/offset** và kiểm tra bytes là nguồn sự thật của bài toán, không phải thứ tự callbacks.

### Tài liệu chính thức Java SE 17

- [Oracle Java SE 17 — `AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): cách mở channel, `read`/`write` trả `Future` hoặc nhận `CompletionHandler`, file position, `force`, các giới hạn.
- [Oracle Java SE 17 — `CompletionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): `completed(V,A)`, `failed(Throwable,A)`.
- [Oracle Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `clear`, `duplicate`, `slice`, heap/direct.
- [Oracle Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout và cancellation.
- [Oracle Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): aggregation, `allOf`, exceptional completion.
- [Oracle Java SE 17 — `Semaphore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): bounded concurrency.
- [Oracle Java SE 17 — `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý thread pool và shutdown.
- [Oracle Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): tạo dữ liệu thử, readback, verify file.
