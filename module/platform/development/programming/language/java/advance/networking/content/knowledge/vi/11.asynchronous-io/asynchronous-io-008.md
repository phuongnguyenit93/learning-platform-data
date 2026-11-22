# Thời hạn, hủy thao tác và trạng thái channel sau khi có lỗi trong Java NIO bất đồng bộ

## 1. Một timeout không đồng nghĩa I/O đã dừng

Trong Java NIO bất đồng bộ, khi gọi `AsynchronousSocketChannel.read(...)`, `write(...)` hoặc `connect(...)`, lời gọi có thể **khởi tạo công việc rồi trả về ngay**, trong khi I/O vẫn đang diễn ra. Kết quả thường được nhận theo một trong hai cách:

- **`Future<V>`**: gọi `get()` khi muốn đợi và nhận kết quả, hoặc kiểm tra `isDone()`, `cancel(...)`.
- **`CompletionHandler<V,A>`**: nhận callback `completed(result, attachment)` hoặc `failed(error, attachment)` sau khi thao tác kết thúc.

Một lỗi nghiêm trọng là dùng `future.get(200, MILLISECONDS)`, bắt `TimeoutException`, rồi cho rằng **đọc/ghi đã được hủy**, có thể tái sử dụng `ByteBuffer` hoặc tiếp tục đọc trên cùng channel ngay. Thực tế, timeout của `Future.get(timeout)` **chỉ giới hạn thời gian thread chờ kết quả**; nó không tự động ngắt I/O bên dưới. Nếu một operation vẫn pending, việc dùng lại buffer hoặc khởi tạo thêm operation cùng chiều có thể gây race, `ReadPendingException`/`WritePendingException` hoặc hỏng dữ liệu.

Với overload có timeout **ngay trên `AsynchronousSocketChannel.read/write`**, khi quá hạn, thao tác hoàn thành với `InterruptedByTimeoutException`. Nhưng ngay cả lúc đó, API Java 17 cũng cảnh báo **trạng thái channel/connection và buffer có thể không còn được bảo đảm**, do runtime không nhất thiết biết có byte đã đọc/ghi hay sẽ tiếp tục được chuyển hay không.

**Kết luận mở đầu:** cần phân biệt ba câu hỏi độc lập:

1. *Deadline của người gọi đã hết chưa?* — thread/logic không muốn chờ thêm.
2. *Thao tác I/O thực sự đã kết thúc hoặc bị hủy chưa?* — trạng thái operation, callback/future.
3. *Channel còn an toàn để dùng tiếp không?* — một cờ `isOpen()` không chứng minh mọi thứ vẫn nhất quán sau lỗi.

Bài học thuộc mục **I/O bất đồng bộ**, tập trung vào thời hạn, hủy operation và xử lý channel sau khi gặp lỗi trong Java 17+.

## 2. Mô hình vòng đời của một thao tác bất đồng bộ

Hãy coi mỗi thao tác đọc/ghi là một đối tượng logic có **trạng thái**, **deadline**, **buffer riêng** và **chủ sở hữu**:

```text
NEW -- initiate read/write/connect --> PENDING
                                     |
                   +-----------------+------------------+
                   |                 |                  |
                   v                 v                  v
              COMPLETED           FAILED            ABANDONED
              (có kết quả)    (I/O error/timeout)  (caller bỏ chờ)
                   |                 |                  |
                   v                 v                  v
           kiểm tra số byte     xác định recovery    có thể I/O vẫn chạy
           + xử lý frame        /đóng channel       -> phải quản lý lifetime
                                     |
                                     v
                         CANCEL_REQUESTED / CLOSED
```

Sơ đồ là **mô hình điều phối ứng dụng**. `Future.cancel` không cam kết hệ điều hành đã dừng I/O, nên `ABANDONED` không được đồng nhất với “cancel thành công ở tầng transport”. Kết quả `Future` có thể được coi là canceled, nhưng tác động bên dưới và tính nhất quán của channel còn phụ thuộc triển khai.

### 2.1. Ba “đồng hồ” khác nhau

| Loại thời hạn | Được áp dụng ở đâu? | Khi hết hạn thực sự xảy ra điều gì? |
|---|---|---|
| **Wait timeout** | `future.get(200, MILLISECONDS)` | Thread chờ nhận `TimeoutException`; **operation vẫn có thể pending** |
| **I/O operation timeout** | `AsynchronousSocketChannel.read(dst, 200, MILLISECONDS, att, handler)` hoặc `write` overload tương tự | Callback `failed` với `InterruptedByTimeoutException` nếu thao tác chưa hoàn tất; channel/buffer có thể ở trạng thái không xác định |
| **Business/request deadline** | Do ứng dụng/framework quản lý, chẳng hạn ngân sách từ lúc bắt đầu request | Phải bao trùm nhiều giai đoạn: connect, gửi, nhận, xử lý, retry; không có một `Future.get` nào tự làm điều này |
| **Shutdown/drain deadline** | Khi server dừng, đợi các request đang chạy | Là chính sách vòng đời; quá hạn phải cleanup có giới hạn và có thể chấp nhận kết quả chưa xác định |

Không nhầm **timeout do người gọi tự tính** với **timeout được API I/O áp dụng**. Ví dụ `AsynchronousFileChannel.read(dst, position)` trả `Future<Integer>`; `get(timeout)` trên future này cũng chỉ hạn chế việc đợi, không tạo một thao tác đọc file có deadline nội tại tương đương overload `read` của `AsynchronousSocketChannel`.

### 2.2. Dùng deadline tổng bằng đồng hồ đơn điệu

Nếu một yêu cầu có ngân sách 2 giây, đừng đặt ba timeout 2 giây cho connect, write, read rồi nói tổng tối đa 2 giây. Mỗi bước có thể tiêu tốn gần trọn thời gian đó.

Khi quản lý trong cùng JVM, dùng `System.nanoTime()` để đo **khoảng thời gian trôi qua**; không dùng `System.currentTimeMillis()` làm đồng hồ điều khiển duration vì đồng hồ tường có thể bị điều chỉnh. Một phép tính có thể dùng:

```java
// Mã minh họa, duration hợp lệ và không gây tràn số.
long started = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(2);

// Trước mỗi bước:
long remaining = budgetNanos - (System.nanoTime() - started);
if (remaining <= 0) {
    // Business deadline đã hết: bỏ chờ và chuyển sang cleanup.
}
```

Nếu một API timeout tính theo mili giây cần giá trị dương, phải cẩn thận với làm tròn nano→mili, giới hạn overflow, và không được lặng lẽ chuyển deadline đã hết thành một thời gian đợi vô hạn. Với `AsynchronousSocketChannel`, timeout **≤ 0** trong overload `read/write` có nghĩa **không timeout**; đó không phải “fail ngay”.

## 3. Timeout ở Future.get: dừng chờ, KHÔNG dừng thao tác

Giả sử:

```java
// Mã minh họa; channel đã kết nối và thuộc quyền quản lý của caller.
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> pendingRead = channel.read(dst);

try {
    int bytes = pendingRead.get(200, TimeUnit.MILLISECONDS);
    // Đọc kết quả I/O đã hoàn tất.
} catch (TimeoutException waitExpired) {
    // Chỉ thread chờ quá hạn; read có thể VẪN đang chạy.
    // Không clear/flip/đọc dst; không lập tức gọi thêm read.
}
```

**`TimeoutException` từ `Future.get(timeout)` là gì?** Nó chỉ nói rằng future không có kết quả mà thread lấy được trong thời gian chờ. Nó **không tự gọi `cancel`**, **không đóng channel**, **không bảo đảm I/O chưa đọc byte** và **không chứng minh peer không gửi dữ liệu**.

Khi bắt được exception, ứng dụng cần quyết định một chính sách rõ ràng:

- **Tiếp tục chờ trên cùng future** nếu business policy cho phép và deadline chưa hết. Không tạo một read khác khi read đầu chưa kết thúc.
- **Abandon + đóng channel** nếu request đã quá hạn và không còn lý do giữ connection. Đóng để thu hồi tài nguyên và đánh thức các I/O đang chờ theo semantics của channel. Đây thường là chính sách đơn giản, an toàn sau khi không còn cần kết quả.
- **Yêu cầu cancel** nhưng không coi kết quả `Future.cancel` là bằng chứng operation hệ điều hành đã dừng. Kiểm soát buffer/channel và không tiếp tục theo giả định “state chắc chắn sạch”.
- **Đối soát nghiệp vụ** nếu đã gửi một lệnh có side effect trước khi chờ response. Không tự kết luận lệnh chưa xử lý chỉ vì get timeout.

### 3.1. `get()` còn có các đường lỗi khác

| Kết quả của `Future.get` | Ý nghĩa | Xử lý cơ bản |
|---|---|---|
| Trả `Integer n` | I/O completed; `n` có thể là partial byte count hoặc `-1` khi EOF (với read) | Xử lý `ByteBuffer`, framing, partial I/O/EOF theo contract |
| `TimeoutException` của `get(timeout)` | Người gọi đã đợi quá hạn | Operation có thể còn pending; quản lý cleanup |
| `ExecutionException` | Operation hoàn thành thất bại; lỗi gốc nằm trong `getCause()` | Phân loại nguyên nhân, lỗi socket/file/permission/close |
| `CancellationException` | Future đã ở trạng thái canceled | Không suy ra underlying I/O chưa chuyển byte |
| `InterruptedException` | Thread đợi bị interrupt | Bảo tồn interrupt flag với `Thread.currentThread().interrupt()` và đi qua chính sách hủy/đóng |

**Đặc biệt:** `InterruptedException` khi chờ `get` khác với `InterruptedByTimeoutException` khi operation I/O có timeout. Cùng có chữ *Interrupted* không có nghĩa cơ chế giống nhau.

## 4. Timeout ở AsynchronousSocketChannel.read/write: có thể làm channel không dùng tiếp được

Java 17 có các overload:

```java
// Mã minh họa chữ ký API:
<A> void read(ByteBuffer dst, long timeout, TimeUnit unit,
              A attachment, CompletionHandler<Integer, ? super A> handler);

<A> void write(ByteBuffer src, long timeout, TimeUnit unit,
               A attachment, CompletionHandler<Integer, ? super A> handler);
```

Đây là **chữ ký minh họa**, không phải mã Java độc lập. Khác với `read(ByteBuffer)` trả `Future<Integer>` không có tham số timeout, overload trên gắn deadline vào chính thao tác bất đồng bộ.

Khi timeout dương hết trước khi I/O hoàn tất:

1. Operation kết thúc qua callback `failed` với **`InterruptedByTimeoutException`**.
2. Theo tài liệu Java 17, timeout **có thể để lại trạng thái channel hoặc underlying connection không nhất quán**. Nếu implementation không thể bảo đảm byte chưa hoặc sẽ không được đọc/ghi, nó có thể đặt channel vào **implementation-specific error state** cho hướng I/O đó.
3. Sau timeout đọc, một lần `read` tiếp theo **có thể ném runtime exception không được định danh trước**. Tương tự cho `write` sau write timeout.
4. **Trạng thái `ByteBuffer` hoặc chuỗi buffer dùng cho I/O timeout là *không xác định***. Tài liệu khuyên bỏ buffer hoặc không truy cập khi channel vẫn mở; chính sách thực tế dễ kiểm soát nhất là **đóng channel, không tái sử dụng buffer đó cho request khác**.

Sự khác biệt quan trọng:

- `channel.isOpen()==true` chỉ cho biết channel **chưa đóng** ở mức API; **không chứng minh** nó vẫn có thể đọc/ghi bình thường sau timeout.
- Một hướng có thể bị lỗi; đừng dựa vào khả năng ghi thành công để kết luận mọi read sẽ tiếp tục hợp lệ, hay ngược lại.
- Runtime có quyền đưa channel vào trạng thái lỗi theo platform/provider, nên **không thiết kế recovery dựa trên một runtime exception cụ thể** sau khi timeout.
- Không nên gọi `buffer.clear()` rồi trả vào pool như thể chắc chắn không còn I/O đụng tới vùng nhớ.

### 4.1. Minh họa CompletionHandler với timeout

```java
// Mã minh họa đặt trong một phương thức có biến channel, dst
// và một hàm closeQuietly(channel) do ứng dụng cài.
channel.read(dst, 500, TimeUnit.MILLISECONDS, null,
        new CompletionHandler<Integer, Void>() {
            @Override
            public void completed(Integer count, Void ignored) {
                if (count == -1) {
                    closeQuietly(channel); // EOF
                    return;
                }
                // count có thể ít hơn số byte của một message.
                handleBytes(count, dst);
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                if (error instanceof InterruptedByTimeoutException) {
                    recordTimeout(error);
                } else {
                    recordFailure(error);
                }
                // Giữ policy đơn giản: channel lỗi -> đóng,
                // không dùng lại dst/pool khi trạng thái không chắc chắn.
                closeQuietly(channel);
            }
        });
```

Đoạn code minh họa, **không phải class biên dịch độc lập**: `handleBytes`, `recordTimeout`, `recordFailure` và `closeQuietly` là các hàm do ứng dụng định nghĩa. Khi hoàn thành thành công, ứng dụng có thể lấy buffer/position sau callback; không nên đọc/ghi cùng buffer trước completion. Khi thất bại do timeout, đừng suy ra buffer có nội dung/position còn hợp lệ.

### 4.2. Không dùng timeout ≤ 0 để biểu đạt deadline đã hết

Tài liệu `AsynchronousSocketChannel` quy định timeout **≤ 0** trong overload nhận timeout nghĩa là operation **không timeout**. Nếu bạn chuyển `remainingNanos` âm thành `0` rồi truyền vào `read`, request lẽ ra phải chấm dứt lại trở thành read không giới hạn.

Thay vào đó, kiểm tra **deadline đã hết** và không khởi tạo I/O mới khi `remaining ≤ 0`. Nếu vẫn còn thời gian, truyền đơn vị thích hợp với giá trị dương; cân nhắc làm tròn và giới hạn nhỏ nhất đủ để không đánh mất deadline.

## 5. Future.cancel: hủy trạng thái Future không đồng nghĩa rollback byte

`Future.cancel(boolean mayInterruptIfRunning)` là một **yêu cầu hủy**. Theo `AsynchronousChannel` trong Java 17, khả năng hủy I/O nền tảng là **implementation-specific**; không có bảo đảm tổng quát rằng byte chưa được truyền hoặc operation thực tế đã dừng ngay khi `cancel` trả về.

### 5.1. `cancel(false)` và `cancel(true)`

| Thao tác | Có thể quan sát | Điều không nên suy ra |
|---|---|---|
| `future.cancel(false)` | Nếu hủy thành công, `isCancelled()` thành true; người đợi nhận `CancellationException` | Underlying read/write chắc chắn chưa chuyển byte; buffer an toàn để tái sử dụng |
| `future.cancel(true)` | Có thể yêu cầu mạnh hơn; runtime **có thể đóng channel** để ngắt operation; người đợi trên future bị hủy nhận `CancellationException` | Channel bắt buộc luôn đóng hoặc an toàn để sử dụng lại |
| `channel.close()` | Kênh bị đóng; outstanding I/O chưa hoàn thành kết thúc với lỗi phù hợp như `AsynchronousCloseException` | Remote application chắc chắn chưa xử lý lệnh trước khi close |

Tham số `mayInterruptIfRunning` **không phải một tùy chọn “rollback network write”**. Nếu implementation không thể xác minh trạng thái byte sau cancel, nó có thể đặt channel vào error state, khiến các operation tương tự kế tiếp thất bại.

**Rủi ro buffer:** Sau khi cancel một read/write, tài liệu khuyên bỏ các `ByteBuffer` đã dùng hoặc rất thận trọng, không truy cập khi channel còn mở. Từ góc độ sở hữu tài nguyên, đừng trả buffer đã “abandoned” cho pool ngay lập tức.

### 5.2. Một quy tắc vận hành có thể kiểm chứng

Nếu request hết deadline khi một read/write còn pending:

1. Đánh dấu request không còn chấp nhận kết quả cuối (một lần duy nhất) trong trạng thái ứng dụng.
2. Không khởi tạo read/write mới cùng hướng trên channel đó.
3. Yêu cầu cancel nếu chính sách có dùng, **không kỳ vọng cancel bảo đảm I/O nền tảng đã dừng**.
4. Đóng channel và giải phóng các tài nguyên khác sau khi đã xác định quyền sở hữu, tránh truy cập buffer đang có trạng thái không chắc chắn.
5. Nếu đã gửi lệnh có side effect, đánh dấu **kết quả nghiệp vụ chưa xác định** và đối soát theo request ID/idempotency, không tự retry mù quáng.

Trong một số ứng dụng, có thể chọn không cancel future mà **đóng channel trực tiếp** khi deadline tổng hết. Đây là đường cleanup đơn giản hơn vì không cần cố tận dụng một connection đã ở trạng thái nghi vấn.

### 5.3. Race giữa hoàn tất và cancel

Giả sử I/O vừa hoàn tất trong khi một timer chuẩn bị hủy:

```text
Thread timer:      kiểm tra deadline -> chuẩn bị cancel
Thread completion: operation hoàn tất -> callback success
Thread timer:      gọi cancel / close
Ứng dụng:          có thể nhận tín hiệu success lẫn thao tác cleanup gần nhau
```

Vì thế logic request cần một **state machine hoặc atomic terminal decision**:

- `PENDING -> SUCCEEDED` nếu operation hoàn tất và kết quả được chấp nhận khi request còn sống.
- `PENDING -> FAILED/TIMED_OUT/CANCELLED` nếu quyết định timeout/error xảy ra trước.
- Một khi trạng thái terminal đã được thiết lập, callback muộn chỉ **cleanup/log**, không ghi đè quyết định đã phát ra và không gửi response thứ hai.

`AtomicBoolean.compareAndSet(false, true)` hoặc `AtomicReference<State>` là công cụ hữu ích cho quyết định một lần. Nhưng đảm bảo *single terminal callback* ở tầng ứng dụng không biến một network operation thành giao dịch exactly-once.

## 6. Trạng thái channel sau khi gặp từng loại lỗi

Không thể suy ra “I/O bất đồng bộ ném exception = channel luôn đóng”. Cần phân biệt **loại lỗi**, **trạng thái connection** và **quyết định cleanup**.

| Tình huống | Channel có thể ở trạng thái nào? | Chính sách an toàn |
|---|---|---|
| `Future.get(timeout)` ném `TimeoutException` | Vẫn mở, operation có thể pending | Không động tới buffer; nếu bỏ request, đóng channel |
| `InterruptedByTimeoutException` của timed read/write | Có thể mở nhưng **inconsistent/error state**, buffer không xác định | Đóng channel; không retry cùng buffer/connection như chưa có gì xảy ra |
| `Future.cancel(false/true)` thành công | Future canceled; underlying I/O và channel phụ thuộc provider, có thể lỗi hoặc đóng | Không coi là rollback; tránh reuse và cleanup có kiểm soát |
| `AsynchronousCloseException` | Channel bị đóng trong lúc I/O pending | Không tiếp tục dùng channel; xử lý close/cleanup |
| `ClosedChannelException` | Channel đã đóng khi cố khởi tạo I/O | Tạo channel mới nếu muốn kết nối lại; kiểm tra lifecycle |
| `ReadPendingException` / `WritePendingException` | Đã có I/O cùng hướng pending trên `AsynchronousSocketChannel`; không nhất thiết channel hỏng | Sửa state/serialization; không mở read/write thứ hai cùng hướng trước completion |
| `NotYetConnectedException` | Socket channel chưa hoàn thành connect | Chờ connect thành công hoặc báo lỗi, không dùng như đã kết nối |
| `ConnectionPendingException` | Đang có một connect operation | Không khởi tạo kết nối thứ hai trên cùng channel |
| `ExecutionException` có cause I/O | Operation hoàn thành lỗi, nguyên nhân cụ thể tùy đường I/O | Phân loại cause; thường đóng socket lỗi và quyết định retry ở tầng request |
| `CancellationException` của `get` | Future được đánh dấu canceled | Không biết chắc byte đã đi đâu; không suy ra channel healthy |
| EOF (read trả `-1`) | Peer kết thúc hướng gửi; không phải cùng nghĩa mọi business request đã thành công | Xử lý giao thức, dữ liệu dở dang, đóng/half-close phù hợp |
| Read/write trả số byte dương nhỏ hơn mong đợi | I/O **thành công một phần**, chưa phải lỗi | Duy trì buffer/connection state, tiếp tục operation hợp lệ |

### 6.1. `isOpen()` chỉ trả lời một phần câu hỏi

`channel.isOpen()` cho biết channel đã bị đóng chưa; nó **không bảo đảm**:

- Đã `connect` thành công.
- Không còn operation đang pending.
- Không có error state do timeout/cancel trước đó.
- Peer còn sống và sẵn sàng xử lý dữ liệu.
- Ứng dụng ở đầu kia đã commit nghiệp vụ.

Muốn dùng lại channel sau lỗi, trước hết phải có **bằng chứng** nó hợp lệ theo hợp đồng API. Với `AsynchronousSocketChannel` sau timeout read/write hoặc hủy operation khiến tình trạng byte không rõ ràng, **đóng và tạo kết nối mới** là chính sách thực dụng hơn cố phục hồi cùng connection.

### 6.2. Một read và một write có thể chạy đồng thời

`AsynchronousSocketChannel` cho phép **một read và một write outstanding cùng lúc**, nhưng **không cho hai read outstanding hoặc hai write outstanding**. Gọi thêm operation cùng hướng khi operation cũ chưa hoàn tất dẫn tới `ReadPendingException` hoặc `WritePendingException`. Lỗi này thường phản ánh **bug trong state machine I/O**, không phải dấu hiệu cần gọi lại liên tục để thử vận may.

Khi muốn ghi nhiều chunk, hãy nối chuỗi write theo completion, cập nhật `ByteBuffer.position()` và chỉ bắt đầu lượt ghi tiếp theo theo đúng quyền sở hữu buffer; không cho nhiều callbacks đồng thời dùng chung mutable buffer.

### 6.3. Kết nối chưa xong và kết nối thất bại

`AsynchronousSocketChannel.connect(remote)` trả `Future<Void>`. Nếu người gọi `get(timeout)` hết hạn, connect có thể vẫn pending: **đừng phát read/write như thể đã kết nối**. Nếu callback/future báo connect thất bại, JDK xác định channel được đóng; muốn kết nối lại hãy mở channel mới. Đối với timeout “người gọi không muốn đợi connect nữa”, đóng channel để tránh kết nối hoàn tất muộn ngoài ý muốn.

## 7. Quyền sở hữu ByteBuffer trong I/O bất đồng bộ

### 7.1. Không truy cập buffer khi operation chưa hoàn tất

`ByteBuffer` có mutable `position`, `limit` và vùng dữ liệu. Trong khi `AsynchronousSocketChannel.read(dst)` còn pending, runtime có thể sẽ cập nhật vị trí/dữ liệu `dst`. Nếu thread khác `clear()`, `flip()`, `put()` hoặc trả buffer về pool trong lúc ấy, có thể xảy ra race và dữ liệu bị sai.

```text
t0: client.read(buffer)         -> Future pending
t1: future.get(100ms) timeout -> CHỈ chờ quá hạn
t2: ứng dụng buffer.clear()    -> SAI: I/O có thể vẫn dùng buffer
t3: runtime nhận byte         -> ghi vào buffer ngoài dự kiến
t4: handler khác dùng buffer  -> dữ liệu đè lên nhau / sai frame
```

**Quy tắc:** buffer được **mượn/giữ độc quyền** cho một I/O cho đến khi có điểm hoàn thành hợp lệ. Khi timeout/cancel khiến tính nhất quán không chắc chắn, không đưa buffer trở lại pool chỉ dựa trên `Future.isCancelled()`.

### 7.2. Một callback có thể đến trên thread khác

`CompletionHandler` được runtime gọi trên thread liên quan đến asynchronous channel group. Vì thế code trong callback phải xử lý an toàn việc:

- Cập nhật state/buffer mà không race với timer, thread gọi API và handler khác.
- Không chặn lâu trong callback; nếu cần nghiệp vụ nặng thì chuyển sang executor riêng.
- Không dùng chung `ByteBuffer` cho hai operation đang chạy.
- Phối hợp cleanup khi channel bị đóng hoặc request deadline hết.

Đừng coi callback luôn chạy trên thread gọi `read()`. Và đừng giả định `close()` làm mọi callback biến mất; outstanding operation có thể hoàn tất thất bại và callback `failed` vẫn cần xử lý cleanup một cách idempotent.

### 7.3. Read/write từng phần

Với read, kết quả `n` có thể nhỏ hơn một frame; cần framing (length prefix/delimiter) và tích lũy bytes. Với write, kết quả `n` có thể nhỏ hơn `src.remaining()` lúc bắt đầu; cập nhật trạng thái và phát operation tiếp để gửi phần còn lại. Một lần future hoàn thành thành công **không** chứng minh toàn bộ message đã được giao hoặc remote application đã xử lý.

Với `AsynchronousFileChannel`, mỗi read/write có **file position** được truyền rõ, và nhiều operation có thể outstanding đồng thời; thứ tự hoàn thành không được bảo đảm. Vì vậy file channel càng cần **buffer và range ownership** rõ ràng, tránh hai write cùng đoạn file mà không có giao thức đồng bộ.

## 8. Java 17+ chạy được: hết thời gian đợi nhưng read vẫn tiếp tục, rồi hủy read kế tiếp

Ví dụ dưới đây dùng TCP loopback với `AsynchronousServerSocketChannel` và `AsynchronousSocketChannel`, không cần Internet hay dependency ngoài JDK. Không dựa vào `Thread.sleep` để làm timeout: phía server **cố ý chưa gửi dữ liệu** cho đến khi client chứng minh đã hết thời gian chờ.

**Kết quả muốn chứng minh:**

1. Client kết nối bất đồng bộ thành công.
2. Client khởi tạo `Future<Integer>` đọc một byte, gọi `get(150ms)`. Vì server chưa gửi và chưa đóng, **chỉ thao tác đợi hết hạn**.
3. Server gửi byte `X`. **Future read cũ** hoàn tất và trả lại `X`; nó chưa bị hủy bởi `get` timeout.
4. Client khởi tạo read thứ hai khi server vẫn mở nhưng không gửi gì, gọi `cancel(false)`. Future báo cancelled nhưng mã **không coi đây là rollback underlying I/O**.
5. Client đóng channel, không dùng lại buffer của operation đã hủy.

Tạo file **`AsyncDeadlineCancelDemo.java`**:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncDeadlineCancelDemo {

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> accept = listener.accept();

            InetSocketAddress address =
                    (InetSocketAddress) listener.getLocalAddress();
            client.connect(address).get(3, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                         accept.get(3, TimeUnit.SECONDS)) {

                System.out.println("Connected: " + client.isOpen());

                ByteBuffer firstBuffer = ByteBuffer.allocate(1);
                Future<Integer> firstRead = client.read(firstBuffer);

                try {
                    firstRead.get(150, TimeUnit.MILLISECONDS);
                    throw new IllegalStateException(
                            "Read unexpectedly completed");
                } catch (TimeoutException expected) {
                    if (firstRead.isDone()) {
                        throw new IllegalStateException(
                                "Read ended unexpectedly");
                    }
                    System.out.println(
                            "Wait timeout: read still pending");
                }

                // Server gửi SAU khi caller đã bị get() timeout.
                ByteBuffer outgoing =
                        ByteBuffer.wrap(new byte[] { (byte) 'X' });

                while (outgoing.hasRemaining()) {
                    int written = peer.write(outgoing)
                            .get(3, TimeUnit.SECONDS);
                    if (written <= 0) {
                        throw new IllegalStateException(
                                "No write progress");
                    }
                }

                int count = firstRead.get(3, TimeUnit.SECONDS);
                if (count != 1) {
                    throw new IllegalStateException(
                            "Expected exactly one byte");
                }
                firstBuffer.flip();

                System.out.println("Read after wait timeout: "
                        + (char) (firstBuffer.get() & 0xff));

                // Read thứ hai pending vì server giữ kết nối
                // nhưng không phát thêm dữ liệu.
                ByteBuffer abandonedBuffer = ByteBuffer.allocate(4);
                Future<Integer> secondRead = client.read(abandonedBuffer);
                boolean cancelled = secondRead.cancel(false);

                System.out.println("Cancel returned: " + cancelled);
                System.out.println(
                        "Future cancelled: " + secondRead.isCancelled());

                // Không truy cập abandonedBuffer sau cancellation.
                // Đóng channel: không thử read lại trên state nghi vấn.
                client.close();
                System.out.println(
                        "Channel open after close: " + client.isOpen());
            }
        }
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 AsyncDeadlineCancelDemo.java
java AsyncDeadlineCancelDemo
```

**Stdout dự kiến trên môi trường cho phép TCP loopback:**

```text
Connected: true
Wait timeout: read still pending
Read after wait timeout: X
Cancel returned: true
Future cancelled: true
Channel open after close: false
```

### Vì sao trình tự này có ý nghĩa?

- `listener.accept()` và `client.connect(address)` đều dùng API bất đồng bộ; `get` ở ví dụ chỉ giúp trình tự test dễ đọc. Trong hệ thống production, có thể dùng callback để không chặn thread điều phối.
- `firstRead` pending vì server chưa gửi, không vì scheduler bị `sleep`. Mốc 150ms chỉ là **timeout của `get`**, không phải timeout operation.
- Future `firstRead` còn dùng được sau `get` timeout: khi server gửi `X`, lời gọi `get` lần sau trên **cùng future** trả dữ liệu. Đó là bằng chứng trực tiếp cho sự khác nhau giữa “bỏ chờ” và “operation kết thúc”.
- `secondRead.cancel(false)` làm Future canceled trong kịch bản không có dữ liệu tới. Demo **không phát biểu** underlying OS read đã ngừng; nó đóng client để xử lý tài nguyên theo chính sách an toàn.
- `client.isOpen()` là `false` **sau khi gọi `close()` chủ động**. Demo không suy ra state channel ngay sau cancel hay timeout ở operation-level.
- ByteBuffer bị hủy không được in/`clear`/trả vào pool; điều này tránh biến trạng thái operation-specific thành giả định an toàn.

**Không nên dùng output để khẳng định cách mọi JDK/provider xử lý cancel**: hành vi hủy I/O nền tảng là implementation-specific. Demo chỉ dựa vào những điều kiện điều phối dễ kiểm chứng: server chưa phát dữ liệu trước `get` timeout, sau đó gửi đúng một byte, và Future ở tầng Java báo canceled theo hợp đồng. Kết nối loopback có thể bị chặn bởi sandbox/firewall; khi đó đây là lỗi môi trường, không phải bằng chứng đặc tính I/O khác.

## 9. Nếu dùng CompletionHandler thay vì Future thì deadline được thiết kế thế nào?

### 9.1. Callback nhận thành công hoặc thất bại

Ở dạng:

```java
// Mã minh họa; channel, buffer và handleCompletion,
// handleFailure là các biến/hàm do ứng dụng định nghĩa.
channel.read(buffer, 750, TimeUnit.MILLISECONDS, null,
        new CompletionHandler<Integer, Void>() {
            @Override
            public void completed(Integer bytes, Void ignored) {
                handleCompletion(bytes);
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                handleFailure(error);
            }
        });
```

Caller không chờ `get`; runtime sẽ báo callback khi operation hoàn tất hoặc lỗi. Nếu read timeout 750ms trước khi có completion, `failed` nhận `InterruptedByTimeoutException`. Cần đảm bảo cả `completed` và `failed` đi vào cơ chế **terminal decision duy nhất** và cleanup tương ứng.

### 9.2. Deadline tổng không tự xuất hiện chỉ vì có timeout trong read

Một client có thể cần:

```text
t0              t1           t2                  t3
|-- connect ----|-- write ---|--- read response ---|
                 tất cả phải nằm trước deadline tổng
```

Nếu mỗi đoạn có timeout 1 giây nhưng request budget tổng là 1,5 giây, một connection có thể tốn 2–3 giây khi retry nối tiếp. Nên lưu `deadlineNanos` ở **request context** và tính `remaining` trước mỗi operation. Đối với connect overload không nhận timeout trực tiếp, có thể đặt timer ứng dụng để quyết định bỏ request rồi **đóng channel** nếu chưa kết nối xong.

Một timer không tự dừng I/O nếu nó chỉ đặt cờ. Khi timer thắng cuộc đua terminal state, code phải hành động (ví dụ đóng channel) để giải phóng tài nguyên thay vì chỉ gửi về caller một `TimeoutException` rồi quên socket.

### 9.3. Callback muộn và cleanup nhiều lần

Một hàm callback có thể đến ngay trước/sau thời hạn business. Khi đó:

- Không gửi hai response, không gọi success callback sau khi request đã báo timeout.
- Không dùng lại buffer mà operation khác có thể vẫn đang quản lý.
- Đóng channel/buffer lease tối đa một lần ở mức ownership, dù timer và callback cùng đi qua `finally`/cleanup.
- Nếu hệ thống dùng request ID, log đủ ID, error type, deadline và hướng I/O; không log payload nhạy cảm.
- Đừng block lâu trong `CompletionHandler`, vì nó có thể chạy trên thread pool phục vụ các operation khác.

Một mẫu state transition:

```java
// Mã minh họa: terminal là AtomicBoolean ban đầu false.
// Timer và callback dùng chung một request context.
if (terminal.compareAndSet(false, true)) {
    // Chỉ nhánh thắng được phát kết quả cuối tới caller.
    // Nếu là timeout/cancel: đóng channel và dọn resource.
}
// Nhánh thua không phát kết quả lần thứ hai; vẫn cleanup phù hợp.
```

Phải tránh một bug tinh vi: timer đánh dấu terminal=true, nhưng không đóng channel, còn callback tới muộn và bị bỏ qua mà không cleanup; khi đó socket/buffer có thể bị rò rỉ. **Terminal decision** và **resource cleanup** là hai trách nhiệm liên quan nhưng không thay thế nhau.

## 10. Khi gặp lỗi: tái sử dụng channel hay mở kết nối mới?

Trong thực tế có ba quyết định khác nhau:

1. **Operation hoàn tất một phần nhưng không có lỗi:** tiếp tục đúng phần còn thiếu trên channel, ví dụ `write` 100/500 byte; giữ ByteBuffer còn 400 byte.
2. **Lỗi logic/serialization:** `ReadPendingException` cho biết đã có read pending; cần sửa concurrency/state chứ không gọi `read` thêm hoặc hủy connection một cách mù quáng. Nếu owner không thể khôi phục invariant, đóng channel là phương án chấp nhận được.
3. **Timeout/cancellation/transport error làm byte state không chắc chắn:** thay vì cố hồi phục bằng cách gọi `clear`, nên đóng channel, giải phóng trạng thái cũ, tạo channel mới khi chính sách retry cho phép.

### 10.1. Có thể retry request không?

Giả sử client gửi một lệnh chuyển tiền; `write` hoàn tất nhưng `read` trả timeout. Lệnh ở server **có thể đã được áp dụng**, còn phản hồi mất/chậm. Nếu client mở channel mới và gửi lại như lệnh mới, có thể gây thực hiện hai lần.

Thiết kế thực tế nên có:

- **Request ID / idempotency key** được giữ nguyên khi retry cùng một ý định nghiệp vụ.
- API **tra cứu trạng thái** hoặc đối soát theo request ID.
- Server có cơ chế **deduplication/transaction** phù hợp, không chỉ kiểm tra ID tại tầng mạng.
- Retry có giới hạn, exponential backoff, jitter và deadline tổng; chỉ retry khi hợp đồng cho phép.
- Phân biệt lỗi trước khi request có thể đến server và lỗi sau khi server có thể đã thực thi; nếu không xác định được thì đánh dấu **outcome unknown**.

TCP/async channel không cung cấp “exactly once business action”. Channel mới chỉ giải quyết hạ tầng kết nối, không giải quyết nghiệp vụ đã chạy ở đầu kia.

### 10.2. Mở lại channel không phải khôi phục cùng phiên

`AsynchronousSocketChannel` đã đóng không được mở lại; cần tạo đối tượng/channel mới để kết nối lại. Kết nối mới có trạng thái TCP mới. Session application, authentication, TLS handshake, transaction context hoặc việc subscribe phải được thiết lập lại tùy giao thức. Không assume dữ liệu pending từ connection cũ được mang theo tự động.

### 10.3. Khác nhau giữa socket channel và file channel

`AsynchronousFileChannel` hỗ trợ I/O vị trí file bất đồng bộ. Khác `AsynchronousSocketChannel`:

- Một số operation đọc/ghi file có thể outstanding đồng thời; thứ tự hoàn thành **không được bảo đảm**.
- Mỗi I/O nhận `file position` riêng; không có shared current file position như stream.
- `Future.get(timeout)` vẫn chỉ giới hạn thời gian **chờ kết quả**, không bảo đảm rollback write xuống file.
- Close làm outstanding operations thất bại theo semantics `AsynchronousChannel`; thay đổi file đã ghi một phần trước lỗi có thể cần kiểm tra/khôi phục bằng giao thức ứng dụng.
- Không nên áp dụng nguyên xi “một read và một write” của `AsynchronousSocketChannel` cho mọi loại asynchronous channel.

**Thời hạn và cancellation là vấn đề chung**, nhưng hành vi I/O và khả năng phục hồi phải tra tài liệu **đúng class và phương thức**, không suy luận từ tên “asynchronous” chung chung.

## 11. Checklist xử lý lỗi an toàn cho async I/O

Một triển khai vận hành có thể dùng trình tự:

1. **Trước khi khởi tạo operation:** xác nhận channel đã ở trạng thái phù hợp; không còn cùng hướng I/O pending; request còn deadline; cấp buffer riêng và ghi nhận ownership.
2. **Khi khởi tạo:** đặt timeout operation nếu API hỗ trợ; ghi start time (monotonic), request ID, direction, expected size, state `PENDING`.
3. **Khi success:** chỉ xử lý sau completion; đọc kết quả số byte/EOF; xử lý partial read/write và framing; cập nhật pending state; giải phóng buffer sau khi không còn alias/I/O dùng.
4. **Khi get wait timeout:** biết chỉ caller hết giờ, operation có thể pending; quyết định tiếp tục đợi hoặc abandon + close; không `clear` buffer hoặc phát operation mới vội.
5. **Khi timed I/O failed:** nếu cause `InterruptedByTimeoutException`, coi channel/ByteBuffer nghi vấn; đóng channel và dùng buffer mới khi muốn retry.
6. **Khi cancel:** quan sát Future/callback đúng semantics; nhớ cancel có thể để channel error state hoặc đóng; không coi cancel là rollback byte.
7. **Khi AsynchronousCloseException/ClosedChannelException:** xác định cleanup dự kiến hay lỗi từ bên ngoài; không reuse channel đã đóng.
8. **Khi ReadPending/WritePending:** sửa logic đồng thời, không retry nóng; bảo đảm một owner cho mỗi hướng read/write.
9. **Khi dừng service:** ngừng nhận request mới, có deadline drain; sau quá hạn đóng channels còn pending và chờ group/executors hoàn tất theo ngân sách.
10. **Khi retry:** có backoff và idempotency/đối soát nếu action có side effect; tạo channel/ByteBuffer mới khi state cũ không còn được bảo đảm.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Sự thật |
|---|---|
| “`future.get(timeout)` quá hạn thì Java tự hủy read/write.” | Không. `get` chỉ chấm dứt việc chờ của caller. |
| “`cancel(false)` đã rollback các byte vừa đọc/ghi.” | Không có bảo đảm rollback I/O nền tảng; cancel behavior phụ thuộc implementation. |
| “`cancel(true)` chắc chắn chỉ interrupt một thread.” | Với asynchronous channel, runtime **có thể đóng channel** và làm các I/O khác thất bại. |
| “`isCancelled()==true` là ByteBuffer an toàn để dùng lại.” | Không. Đặc biệt khi underlying operation chưa chắc dừng, phải quản lý lifetime an toàn. |
| “`InterruptedByTimeoutException` là `TimeoutException` của `Future.get`.” | Hai cơ chế khác nhau: operation timeout và wait timeout. |
| “Read timeout nhưng `isOpen()==true` thì đọc lại bình thường.” | Channel có thể ở **implementation-specific error state**; read sau đó có thể ném runtime exception. |
| “Timeout read không thể đã nhận byte nào.” | Không đảm bảo; buffer có thể có trạng thái không xác định sau timed I/O. |
| “`ByteBuffer.clear` xóa sạch dữ liệu và hủy I/O.” | Không. Nó chỉ reset chỉ số buffer; không cancel operation. |
| “Mọi async channel chỉ cho phép một read/write outstanding.” | Quy tắc này áp dụng cho `AsynchronousSocketChannel`; file channel có semantics khác. |
| “Future canceled nghĩa server chắc chắn không thực hiện request.” | Không. Server có thể đã nhận và xử lý payload; business outcome có thể unknown. |
| “`close` bảo đảm client và server biết cùng một kết quả nghiệp vụ.” | Không. Close là thao tác tài nguyên/kết nối, không thay application acknowledgment. |
| “Cứ retry khi thấy `ReadPendingException`.” | Đây thường là bug quản lý outstanding I/O; retry nóng làm tình hình tệ hơn. |
| “Timer/callback chỉ cần đánh dấu terminal là đủ.” | Còn phải dọn channel, buffer và các operation pending, kể cả khi callback đến muộn. |

## 13. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Sau khi `channel.read(dst)` trả Future, `future.get(100, MILLISECONDS)` ném `TimeoutException`. Có thể gọi `dst.clear()` và bắt đầu một read khác ngay không?

**Đáp án:** Không. Future wait timeout không dừng I/O; read đầu có thể còn pending và sử dụng `dst`. Lần read mới cùng hướng còn có thể gặp `ReadPendingException`. Phải giữ ownership, chờ completion hoặc đóng/cleanup channel khi abandon.

**Câu 2.** Timeout gắn trực tiếp vào `AsynchronousSocketChannel.read(dst, t, unit, attachment, handler)` thường báo kiểu exception nào?

**Đáp án:** `InterruptedByTimeoutException` trong callback `failed`. Sau timeout, trạng thái channel và buffer có thể không xác định; không giả định retry read trên cùng channel an toàn.

**Câu 3.** Nếu `future.cancel(true)` trả true, channel luôn chắc chắn đóng không?

**Đáp án:** Không. API nói runtime **có thể đóng channel**; việc hủy I/O nền tảng là implementation-specific. Không coi giá trị true là bằng chứng mọi byte chưa được truyền.

**Câu 4.** Lệnh `read` bị cancel nhưng `isOpen()==true`. Có thể dùng lại cùng buffer và connection như ban đầu không?

**Đáp án:** Không mặc định. Cancellation có thể tạo trạng thái lỗi và buffer còn bị ảnh hưởng. Chính sách đơn giản là đóng channel, bỏ buffer nghi vấn và mở kết nối mới nếu cần.

**Câu 5.** `Future.get` ném `ExecutionException` có phải đây là nguyên nhân I/O gốc không?

**Đáp án:** `ExecutionException` là lớp bọc; kiểm tra `getCause()` để xác định `IOException`, `AsynchronousCloseException` hoặc nguyên nhân khác.

**Câu 6.** `AsynchronousSocketChannel` cho phép một read và một write đồng thời không? Hai read cùng lúc không?

**Đáp án:** Có thể một read và một write đồng thời; không cho hai read outstanding. Gọi read thứ hai khi read đầu chưa hoàn tất ném `ReadPendingException`.

**Câu 7.** Một Future read timeout ở caller, rồi vài giây sau get trên **cùng Future** trả dữ liệu. Có mâu thuẫn không?

**Đáp án:** Không. Timeout ban đầu chỉ là hết thời gian chờ; underlying read có thể hoàn thành về sau. Ví dụ `AsyncDeadlineCancelDemo` minh họa chính xác điều này.

**Câu 8.** Sau khi write tới server thành công, read response bị timeout. Có thể kết luận server chưa commit không?

**Đáp án:** Không. Trạng thái nghiệp vụ có thể unknown. Cần request ID, idempotency và cơ chế đối soát/truy vấn trạng thái thay vì retry mù.

**Câu 9.** Nếu timeout nội tại nhận tham số `0` ở `AsynchronousSocketChannel.read`, read có timeout ngay không?

**Đáp án:** Không. Với overload timeout của class này, giá trị **≤ 0** nghĩa là operation **không timeout**. Check deadline trước khi gọi thay vì chuyển thời gian còn lại âm thành 0.

**Câu 10.** Một callback success và timer timeout chạy cạnh nhau. Làm sao tránh phát hai kết quả?

**Đáp án:** Dùng state machine hoặc atomic terminal decision chỉ cho một nhánh thắng; đồng thời cleanup resource đúng cách ở cả nhánh thắng/thua, không để callback muộn tạo rò rỉ.

## 14. Ghi nhớ và nguồn API

**Bốn điểm phải nhớ:**

1. **`Future.get(timeout)` chỉ giới hạn thời gian chờ**, không mặc định hủy I/O.
2. **Timed `AsynchronousSocketChannel.read/write` có thể kết thúc bằng `InterruptedByTimeoutException`**, và trạng thái channel/**ByteBuffer** sau đó có thể không xác định.
3. **`Future.cancel` không bảo đảm rollback hoặc underlying I/O đã ngừng**; `cancel(true)` còn có thể đóng channel. `isOpen()` không đủ để đánh giá channel healthy sau lỗi.
4. **Thiết kế deadline phải đi kèm state, ownership, cleanup và business idempotency.** Khi đã không chắc byte nào được truyền/đã xử lý, đóng channel nghi vấn và mở kết nối mới, không reuse buffer mù quáng.

Tài liệu chính thức của Java SE 17:

- [AsynchronousChannel — Cancellation và close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannel.html)
- [AsynchronousSocketChannel — Timed read/write, error state, pending ops](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html)
- [AsynchronousFileChannel — Multiple outstanding operations, buffers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html)
- [Future — get(timeout), cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [ByteBuffer — position, limit, ownership](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)