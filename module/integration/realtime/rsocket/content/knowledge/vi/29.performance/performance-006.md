# Ảnh hưởng của phân mảnh, zero-copy và bộ nhớ trực tiếp

RSocket được xây dựng trên các transport bất đồng bộ như TCP và WebSocket. Trong RSocket Java, Netty thường đảm nhiệm I/O và quản lý buffer; dữ liệu đi qua nhiều lớp từ object Java, codec, `Payload`, frame RSocket đến transport. Hiệu năng và mức sử dụng bộ nhớ phụ thuộc vào số lần cấp phát, sao chép, cách chia nhỏ payload, allocator và vòng đời của các buffer.

Ba khái niệm trong bài có liên hệ nhưng không đồng nghĩa:

- **Phân mảnh (fragmentation):** có thể nói về việc chia một payload thành nhiều frame RSocket hoặc tình trạng vùng nhớ bị chia thành các block khó tái sử dụng hiệu quả.
- **Zero-copy:** giảm hoặc loại bỏ việc sao chép bytes giữa các buffer/lớp khi các bên có thể chia sẻ cùng vùng nhớ.
- **Bộ nhớ trực tiếp (direct memory):** vùng nhớ native/off-heap mà Java có thể truy cập qua `ByteBuffer` hoặc Netty `ByteBuf`.

Direct memory không tự động tạo ra zero-copy; zero-copy cũng không có nghĩa là không cần quản lý ownership. Muốn tối ưu RSocket, cần nhìn toàn bộ đường đi dữ liệu và đo chi phí thực tế thay vì chỉ chọn một API có tên “direct” hoặc “slice”.

## 1. Đường đi của dữ liệu trong RSocket Java

Một request có thể đi qua các bước khái quát sau:

```text
Object Java / DTO
      |
      v
Message encoder / codec
      |
      v
Payload (data + metadata)
      |
      v
RSocket frame encoder
      |
      v
Netty ByteBuf
      |
      v
TCP hoặc WebSocket transport
```

Ở phía nhận, các bước diễn ra theo chiều ngược lại: transport nhận bytes, Netty tạo/đọc buffer, RSocket giải mã frame, runtime tạo payload và Spring codec có thể giải mã thành object Java.

Một payload nhỏ vẫn có thể tạo nhiều lần cấp phát hoặc copy nếu ứng dụng chuyển qua `byte[]`, `String`, JSON, `ByteBuffer` và `ByteBuf` ở nhiều lớp. Ngược lại, dùng direct buffer hoặc slice chỉ giảm copy ở một số ranh giới; encoder, TLS, compression hoặc consumer vẫn có thể cần tạo buffer mới.

Khi tối ưu, hãy xác định cụ thể copy nào đang xảy ra: copy từ heap sang native I/O buffer, copy do codec serialize, copy do ghép các component, copy khi giải nén, hay copy do ứng dụng tạo DTO mới.

## 2. Hai loại phân mảnh cần phân biệt

Từ “fragmentation” thường được dùng cho hai hiện tượng khác nhau.

| Loại | Xảy ra ở đâu? | Hệ quả chính |
|---|---|---|
| Protocol/frame fragmentation | Một payload lớn được chia thành nhiều frame RSocket. | Tăng số frame, header, trạng thái reassembly và bộ nhớ tạm. |
| Memory allocator fragmentation | Vùng nhớ heap hoặc native được chia thành các block có kích thước/vị trí khác nhau. | Có thể còn tổng dung lượng trống nhưng khó cấp phát block lớn hoặc giữ lại nhiều dung lượng chưa sử dụng. |

Ngoài ra, TCP chia byte stream thành segment và IP có cơ chế phân mảnh ở tầng mạng trong một số điều kiện. Đây là các khái niệm khác với fragmentation do RSocket runtime thực hiện. Ứng dụng không nên coi ranh giới TCP segment là ranh giới message RSocket.

## 3. Phân mảnh payload ở tầng RSocket

Một frame RSocket có giới hạn kích thước theo cấu hình transport/runtime. Khi payload lớn hơn kích thước frame cho phép, RSocket có thể chia payload thành nhiều fragment. Các frame fragment mang thông tin cho biết payload còn tiếp tục; cờ `FOLLOWS` được dùng để đánh dấu phần chưa phải fragment cuối.

```text
Payload logic: [---------------- 900 KB ----------------]

RSocket frames:
  Frame 1: [fragment A] [FOLLOWS]
  Frame 2: [fragment B] [FOLLOWS]
  Frame 3: [fragment C] [FOLLOWS]
  Frame 4: [fragment D] [last fragment]

Receiver:
  nhận fragments -> ghép/reassemble -> chuyển payload hoàn chỉnh
```

Kích thước fragment và cách reassembly phụ thuộc cấu hình cùng implementation. Ý nghĩa của fragmentation là cho phép truyền payload lớn qua giới hạn frame, không phải biến một payload lớn thành nhiều message nghiệp vụ độc lập.

### Chi phí của frame fragmentation

- Mỗi fragment có frame header và chi phí encode/decode riêng.
- Receiver cần giữ trạng thái và dữ liệu fragment cho đến khi payload hoàn chỉnh.
- Nhiều fragment có thể làm tăng số lần xử lý frame và scheduling.
- Reassembly có thể giữ buffer trong thời gian dài nếu một fragment đến chậm hoặc kết nối bị gián đoạn.
- Payload lớn làm tăng peak memory, đặc biệt khi nhiều stream cùng gửi payload lớn.

Fragment nhỏ giảm kích thước mỗi lần ghi nhưng tăng số frame và overhead. Fragment lớn giảm số frame nhưng có thể tạo buffer lớn hơn và burst memory cao hơn. Không có một kích thước tối ưu cho mọi workload.

### Fragmentation không thay thế streaming

Nếu nghiệp vụ có thể xử lý dữ liệu theo từng phần, `requestStream` hoặc `requestChannel` thường phù hợp hơn việc gửi một payload rất lớn rồi chờ reassembly toàn bộ. Streaming cho phép consumer xử lý từng phần, áp dụng backpressure và giới hạn lượng dữ liệu đang giữ.

Ví dụ thay vì gửi toàn bộ danh sách telemetry trong một payload, client có thể phát từng batch có kích thước giới hạn. Server xử lý batch rồi tiếp tục nhận phần tiếp theo theo demand. Cách này giảm peak memory và giúp giới hạn thời gian xử lý từng phần.

## 4. Phân mảnh bộ nhớ: internal và external fragmentation

Memory allocator cấp phát vùng nhớ theo kích thước và cấu trúc riêng. Khi các vùng nhớ được cấp phát và giải phóng theo thời gian, có thể xuất hiện hai dạng phân mảnh:

**Internal fragmentation:** allocator cấp phát một block lớn hơn kích thước ứng dụng yêu cầu do làm tròn theo size class, page hoặc đơn vị quản lý. Phần chênh lệch bên trong block chưa được ứng dụng sử dụng.

**External fragmentation:** tổng dung lượng trống có thể đủ lớn nhưng bị chia thành nhiều vùng không liền nhau. Một yêu cầu cần block liên tục lớn có thể không được đáp ứng bằng một vùng duy nhất.

```text
Một vùng nhớ ban đầu:
┌────────────────────────────────────────────────────┐
│                    free space                       │
└────────────────────────────────────────────────────┘

Sau nhiều lần allocate/release:
┌────────┬───────┬────────┬──────┬────────┬───────────┐
│ live A │ free  │ live B │ free │ live C │   free    │
└────────┴───────┴────────┴──────┴────────┴───────────┘

Tổng free có thể đủ, nhưng không nhất thiết có một block liền đủ lớn.
```

Allocator hiện đại dùng pool, arena và size class để giảm chi phí cấp phát cũng như kiểm soát phân mảnh. Đổi lại, allocator có thể giữ lại vùng nhớ để tái sử dụng thay vì trả ngay cho hệ điều hành.

## 5. Heap memory và direct memory

Java có thể dùng buffer dựa trên heap hoặc vùng nhớ trực tiếp ngoài heap.

| Đặc điểm | Heap buffer | Direct buffer |
|---|---|---|
| Vùng nhớ | Heap do JVM quản lý | Native/off-heap memory |
| Vòng đời | Đối tượng được quản lý bởi GC | Buffer object do GC quản lý, vùng nhớ native được giải phóng theo cơ chế của JVM/allocator |
| Truy cập từ Java | Có thể truy cập backing array nếu API cho phép | Không có backing array Java thông thường |
| Native I/O | Có thể cần copy sang vùng native phù hợp | Có thể cho native I/O truy cập trực tiếp vùng nhớ |
| Chi phí cấp phát | Thường thấp hơn và dễ thu hồi theo GC | Cấp phát/thu hồi thường đắt hơn; phù hợp hơn khi tái sử dụng |
| Quan sát bộ nhớ | Heap metrics và GC | Cần theo dõi direct/native memory riêng |

`ByteBuffer.allocate(...)` tạo heap buffer; `ByteBuffer.allocateDirect(...)` tạo direct buffer. Netty `ByteBuf` cũng có thể được backed bởi heap hoặc direct memory.

Direct memory hữu ích khi dữ liệu được truyền tới native I/O vì có thể tránh một lần copy từ heap sang native buffer. Nhưng direct memory không miễn phí: cấp phát nhiều buffer direct nhỏ, ngắn hạn có thể đắt hơn dùng pool; dữ liệu vẫn có thể bị copy ở codec, TLS hoặc các lớp trung gian.

## 6. Netty ByteBuf và allocator

Trong Netty, `ByteBuf` cung cấp API đọc/ghi bytes với `readerIndex`, `writerIndex`, capacity và cơ chế reference counting. Nó trừu tượng hóa việc buffer nằm trên heap, direct memory hay vùng nhớ được quản lý bởi allocator.

```java
ByteBuf buffer = allocator.directBuffer(1024);
try {
    buffer.writeBytes(payloadBytes);
    // encode hoặc chuyển buffer cho component sở hữu tiếp theo
} finally {
    buffer.release();
}
```

Đoạn code minh họa việc cấp phát và giải phóng buffer do ứng dụng sở hữu. Trong RSocket runtime, ownership có thể được chuyển cho component khác; không release một buffer sau khi đã chuyển quyền sở hữu theo contract API.

### Pooled allocator

Netty có pooled allocator để tái sử dụng vùng nhớ thay vì liên tục gọi native allocator. Các triển khai pool thường tổ chức bộ nhớ theo arena, chunk, page và các lớp kích thước nhỏ hơn. Việc tái sử dụng giảm chi phí cấp phát/thu hồi và giảm áp lực allocator dưới tải cao.

Pool cũng có trade-off:

- Dung lượng đã cấp cho pool có thể tiếp tục được giữ lại để tái sử dụng.
- Các arena hoặc thread-local cache có thể giữ vùng nhớ chưa được dùng ngay.
- Một chunk còn vài allocation sống có thể chưa được trả lại hoàn toàn.
- Workload có kích thước buffer thay đổi mạnh có thể để lại vùng trống khó tận dụng.

Do đó, RSS hoặc direct memory không giảm ngay sau khi ứng dụng release payload chưa chắc là memory leak. Cần phân biệt memory đang được pool giữ để tái sử dụng với reference bị rò rỉ.

### Unpooled allocator

Unpooled allocation có thể hữu ích cho một số workload ít cấp phát hoặc buffer tồn tại ngắn, nhưng thường làm tăng chi phí cấp phát khi số lượng thao tác cao. Không nên chuyển toàn bộ hệ thống sang pooled hoặc unpooled chỉ dựa trên một benchmark nhỏ; cần đo với phân bố kích thước payload, concurrency và transport thật.

## 7. Zero-copy nghĩa là gì?

Zero-copy là cách tổ chức đường đi dữ liệu để tránh sao chép bytes khi có thể chia sẻ cùng vùng nhớ hoặc để hệ thống native chuyển dữ liệu trực tiếp giữa các vùng phù hợp.

Trong ứng dụng Netty/RSocket, zero-copy thường được dùng theo nghĩa hẹp: tạo view/slice của một buffer, ghép nhiều component hoặc chuyển buffer giữa các lớp mà không copy toàn bộ bytes. Nó không bảo đảm toàn bộ hành trình từ object Java đến NIC và ngược lại không có bất kỳ bản sao nào.

Ví dụ một đường đi có thể vẫn copy:

```text
DTO -> JSON encoder -> byte[] -> ByteBuf -> TLS buffer -> socket
       copy/encode       copy      wrap/copy?   copy/transform
```

Đường đi tối ưu hơn có thể giảm một số bước:

```text
ByteBuf-backed payload -> frame encoder -> transport buffer -> socket
       shared view          có thể encode header/metadata riêng
```

Ngay cả ở đường đi thứ hai, frame header, TLS encryption, compression hoặc transport implementation vẫn có thể tạo buffer mới. Hãy mô tả chính xác copy nào được loại bỏ thay vì gọi toàn bộ pipeline là zero-copy.

## 8. `slice()`, `duplicate()` và `copy()`

Netty `ByteBuf` cung cấp các cách tạo view hoặc bản sao:

| API | Có copy bytes? | Index | Reference count/lifetime |
|---|---:|---|---|
| `slice()` | Không | View có reader/writer index riêng cho vùng con | Chia sẻ reference count và lifetime với buffer gốc; không tự retain. |
| `duplicate()` | Không | Có index riêng nhưng nhìn cùng nội dung | Chia sẻ reference count và lifetime với buffer gốc; không tự retain. |
| `retainedSlice()` | Không | View của vùng con | Tăng reference count để giữ vùng nhớ sống thêm một reference. |
| `retainedDuplicate()` | Không | View toàn buffer với index riêng | Giữ thêm một reference. |
| `copy()` | Có | Buffer mới với nội dung được sao chép | Có ownership/lifetime độc lập. |

Ví dụ tạo slice để xử lý đồng bộ:

```java
ByteBuf view = source.slice(offset, length);
decodeSynchronously(view);
// Không release view như một allocation độc lập.
// Owner của source chỉ release sau khi decodeSynchronously hoàn tất.
```

`slice()` không giữ parent sống. Nếu component sở hữu `source` release nó trước khi `decodeSynchronously` hoàn tất, view cũng không còn hợp lệ.

Nếu cần giữ dữ liệu qua ranh giới bất đồng bộ, dùng retained view và release reference được giữ:

```java
ByteBuf retained = source.retainedSlice(offset, length);
source.release(); // chỉ khi method hiện tại sở hữu reference ban đầu

return asyncProcessor.process(retained)
    .doFinally(signal -> retained.release());
```

Ví dụ giả định `asyncProcessor.process(...)` không giữ `retained` sau khi publisher kết thúc và việc tạo publisher không ném lỗi đồng bộ. Trong code production, phải giải phóng retained reference cả khi việc khởi tạo tác vụ thất bại; có thể dùng resource operator hoặc một helper quản lý cleanup. Mỗi `retain()` cần đúng một lần `release()` tương ứng.

`copy()` tạo bản sao thật sự. Nó tốn CPU và memory bandwidth nhưng có ích khi cần lifetime độc lập, cần sửa bytes mà không ảnh hưởng nguồn hoặc cần gom dữ liệu từ nhiều vùng thành một buffer liên tục.

## 9. CompositeByteBuf và ghép nhiều vùng nhớ

`CompositeByteBuf` có thể biểu diễn nhiều `ByteBuf` thành một buffer logic bằng cách quản lý danh sách component, tránh copy toàn bộ nội dung chỉ để ghép header và body.

```text
Logical composite buffer
┌──────────────┬───────────────────┬──────────────┐
│ header bytes │ body component A  │ body B       │
└──────────────┴───────────────────┴──────────────┘
       |                |                 |
       +----------------+-----------------+
            các component được tham chiếu
```

Khi consumer có thể đọc qua các component, việc ghép logic này tránh copy. Nhưng nếu consumer yêu cầu một vùng nhớ liên tục duy nhất, thao tác coalesce/consolidate hoặc codec tiếp theo có thể phải copy.

Composite buffer cũng làm ownership phức tạp hơn: component có thể được quản lý như một phần của composite. Cần đọc contract của API `addComponent(s)` đang dùng và xác định ai chịu trách nhiệm release composite cùng các component; không retain/release theo phỏng đoán.

## 10. Direct ByteBuffer và view NIO

Netty có thể cung cấp NIO `ByteBuffer` view của dữ liệu `ByteBuf` qua các API như `nioBuffer()`. Với một buffer contiguous, view có thể chia sẻ vùng nhớ bên dưới thay vì copy bytes. Tuy nhiên, với composite buffer hoặc trường hợp cần nhiều NIO buffers, kết quả phụ thuộc cấu trúc và API cụ thể; đừng giả định mọi lời gọi `nioBuffer()` luôn zero-copy.

Một `ByteBuffer` view cũng không tự kéo dài lifetime của `ByteBuf` gốc. Nếu vùng nhớ Netty được release trong khi code khác vẫn đọc NIO view, hành vi đó không an toàn. Giữ ownership của buffer gốc hoặc tạo một bản sao độc lập theo contract.

Direct `ByteBuffer` phù hợp khi API native cần địa chỉ vùng nhớ trực tiếp. Nhưng việc chuyển một heap `byte[]` sang `ByteBuffer.allocateDirect(...)` rồi copy bytes vào đó vẫn là một lần copy. Muốn giảm copy, cần tránh tạo bản sao ở ranh giới trước đó chứ không chỉ thay loại buffer ở cuối pipeline.

## 11. Direct memory không đồng nghĩa zero-copy

Hai quyết định này giải quyết vấn đề khác nhau:

| Quyết định | Tác động | Không bảo đảm |
|---|---|---|
| Dùng direct memory | Có thể giảm copy giữa heap và native I/O; giảm áp lực một số đường GC heap. | Không bảo đảm không copy trong codec, TLS hoặc ứng dụng. |
| Dùng slice/duplicate | Tạo view cùng vùng nhớ, tránh copy bytes cho thao tác đó. | Không tự giữ lifetime, không làm dữ liệu bất biến. |
| Dùng retained slice | Chia sẻ vùng nhớ và giữ thêm reference. | Không miễn phí; phải release và có thể giữ vùng lớn lâu hơn. |
| Dùng composite buffer | Ghép nhiều component theo logic mà không cần copy ngay. | Consumer cuối có thể yêu cầu buffer contiguous và gây copy. |
| Dùng pooled allocator | Tái sử dụng vùng nhớ, giảm chi phí cấp phát. | Không bảo đảm RSS giảm ngay hoặc không có fragmentation. |

Một hệ thống có thể dùng direct memory nhưng vẫn copy nhiều lần. Ngược lại, một pipeline heap-based có thể dùng slice và tránh một số copy. Hãy đo số bytes được copy và allocation rate thực tế.

## 12. TLS, compression và codec ảnh hưởng zero-copy

Các lớp xử lý bảo mật và serialization thường biến đổi nội dung bytes:

- **TLS:** mã hóa/giải mã record; thường cần buffer và bước xử lý riêng, có thể làm giảm cơ hội chia sẻ buffer xuyên suốt.
- **Compression:** đọc dữ liệu đầu vào và tạo nội dung đã nén/giải nén, thường phát sinh buffer mới.
- **JSON/CBOR codec:** chuyển object Java thành bytes và ngược lại; đây là công việc encode/decode, không thể bỏ qua chỉ bằng cách dùng direct memory.
- **WebSocket framing:** thêm hoặc xử lý frame header/mask theo vai trò client/server; transport có thể tạo buffer trung gian.
- **Logging/tracing:** chuyển payload thành chuỗi hoặc copy một phần nội dung để ghi log có thể thêm allocation và CPU đáng kể.

Zero-copy tối ưu một số đường truyền bytes, nhưng không loại bỏ chi phí biến đổi dữ liệu. Với payload nhạy cảm, tránh log toàn bộ nội dung chỉ để debug hiệu năng.

## 13. Quản lý reference count khi dùng view

Netty `ByteBuf` và nhiều RSocket `Payload` dùng reference counting. Khi reference count về `0`, vùng nhớ không còn được phép truy cập. Garbage collector không thay thế trách nhiệm release đối với reference-counted buffer.

Quy tắc thực hành:

1. Mỗi component chỉ release reference mà nó sở hữu.
2. Khi chuyển ownership cho runtime hoặc subscriber, không release thêm ở phía đã chuyển quyền.
3. `slice()`/`duplicate()` thông thường chia sẻ lifetime với nguồn; không dùng chúng vượt quá lifetime nguồn.
4. `retainedSlice()`/`retain()` tạo thêm reference; phải release đúng một lần.
5. `copy()` tạo buffer mới và có ownership độc lập.
6. Cleanup phải chạy ở cả complete, error và cancellation.

Ví dụ `Payload` chứa data và tạo một view được giữ riêng:

```java
ByteBuf dataView = payload.data().retainedSlice();
payload.release(); // chỉ khi handler đang sở hữu payload đầu vào

return processAsync(dataView)
    .doFinally(signal -> dataView.release());
```

Đoạn code minh họa ranh giới ownership: retained view vẫn sống sau khi payload gốc được release. Nếu `processAsync` có thể ném lỗi đồng bộ trước khi trả publisher, cần giải phóng `dataView` trong nhánh lỗi đó. Nếu framework hoặc codec đã sở hữu payload, không tự release payload từ một handler không có ownership theo contract.

## 14. Direct memory và garbage collection

Direct memory nằm ngoài Java heap nên không được phản ánh đầy đủ qua chỉ số heap used. Một ứng dụng có heap còn nhiều nhưng vẫn có thể gặp lỗi cấp phát direct buffer nếu direct memory chạm giới hạn hoặc native memory bị áp lực.

Các nguồn tiêu thụ cần theo dõi riêng:

- Direct `ByteBuffer` do JDK tạo.
- Direct `ByteBuf` do Netty allocator quản lý.
- Pooled chunks và thread-local caches.
- Memory mapping nếu ứng dụng dùng mapped buffers.
- Native memory của TLS, compression hoặc thư viện native khác.

`-XX:MaxDirectMemorySize` có thể giới hạn dung lượng direct buffer do JVM quản lý theo cơ chế tương ứng. Đây không phải giới hạn tổng RSS của process và không bao phủ mọi loại native allocation của thư viện bên thứ ba. Cần hiểu runtime và Netty version đang dùng trước khi thay đổi giới hạn.

Không tăng `MaxDirectMemorySize` chỉ để che lỗi `OutOfMemoryError: Direct buffer memory`. Trước tiên hãy xác định buffer đang được giữ hợp lệ, pool đang giữ vùng nhớ để tái sử dụng hay reference bị leak.

## 15. Pooled allocator và hiện tượng bộ nhớ không giảm

Một allocator pool có thể giữ chunk sau khi một số buffer được release để phục vụ allocation tiếp theo. Vì vậy:

- Direct memory usage có thể giữ ở mức cao sau khi tải giảm.
- RSS không nhất thiết giảm ngay sau khi một request hoàn tất.
- Một số arena/cache có thể giữ vùng nhớ riêng để giảm contention.
- Một allocation còn sống có thể ngăn một phần chunk được tái sử dụng hoặc trả lại hệ điều hành.

Để phân biệt pool retention và leak, quan sát xu hướng theo thời gian:

| Quan sát | Cách diễn giải có thể |
|---|---|
| Usage tăng khi tải tăng rồi ổn định ở plateau | Có thể là pool đã mở rộng để đáp ứng peak và đang tái sử dụng. |
| Usage tăng liên tục qua nhiều chu kỳ tải và không ổn định | Có thể có leak, queue giữ buffer hoặc workload chưa giải phóng. |
| Heap ổn định nhưng direct memory tăng | Kiểm tra Netty ByteBuf, direct ByteBuffer và native allocation. |
| Release xong nhưng RSS vẫn cao | Pool/native allocator có thể giữ vùng nhớ; cần kiểm tra allocator metrics và process memory. |
| Leak detector báo allocation chưa release | Lần theo stack trace và ownership của reference. |

Không dùng RSS đơn lẻ để kết luận memory leak; cũng không dùng việc pool giữ memory để bỏ qua cảnh báo leak detector.

## 16. Backpressure và giới hạn bộ nhớ

Backpressure điều tiết số phần tử mà subscriber yêu cầu từ publisher. Nó giúp kiểm soát tốc độ giữa producer và consumer, nhưng không tự giới hạn kích thước bytes của từng payload.

Ví dụ `requestStream` có thể phát một phần tử mỗi lần demand, nhưng nếu một payload đơn lẻ chứa hàng trăm MB thì peak memory vẫn rất lớn. Tương tự, `flatMap` với concurrency cao có thể giữ nhiều payload/inner request cùng lúc.

Các biện pháp kết hợp:

- Giới hạn kích thước payload và metadata.
- Chia dữ liệu lớn thành batch/stream có kích thước kiểm soát.
- Đặt concurrency và prefetch phù hợp với capacity downstream.
- Giới hạn queue/buffer ở producer và consumer.
- Hủy stream không còn cần thiết và release buffer đúng ownership.
- Theo dõi số payload đang chờ, số bytes đang giữ và active streams.

Backpressure giải quyết tốc độ phát/nhận; size limit giải quyết lượng bytes mỗi message; allocator/ownership giải quyết cách vùng nhớ được cấp phát và thu hồi. Cần cả ba lớp.

## 17. Chọn kích thước payload và batch

Payload quá nhỏ làm tăng số frame, header, scheduler và call overhead. Payload quá lớn làm tăng latency trước khi consumer có dữ liệu hoàn chỉnh, peak memory, reassembly và chi phí retry.

| Kích thước/kiểu dữ liệu | Cân nhắc |
|---|---|
| Message nhỏ, tần suất cao | Giảm allocation và codec overhead; tránh tạo nhiều object/buffer nhỏ không cần thiết. |
| Batch vừa phải | Cân bằng số frame, throughput và peak memory; thường dễ áp dụng backpressure. |
| Payload rất lớn | Cân nhắc streaming/chunking, giới hạn kích thước và xử lý theo cursor. |
| Stream dài hạn | Kiểm soát demand, queue và lifetime của buffer từng phần tử. |
| Metadata lớn | Giữ metadata gọn; không dùng metadata thay cho data payload lớn. |

Kích thước batch tối ưu phụ thuộc payload schema, network latency, codec, TLS, transport và khả năng xử lý của server. Cần benchmark với dữ liệu gần thực tế thay vì dùng một con số cố định cho mọi route.

## 18. Đo direct memory và allocator metrics

JVM cung cấp `BufferPoolMXBean` để quan sát các buffer pool như `direct` và `mapped`. Có thể truy cập qua `ManagementFactory`:

```java
List<BufferPoolMXBean> pools =
    ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);

for (BufferPoolMXBean pool : pools) {
    log.info("bufferPool={} count={} used={} capacity={}",
        pool.getName(),
        pool.getCount(),
        pool.getMemoryUsed(),
        pool.getTotalCapacity());
}
```

`getMemoryUsed()` và `getTotalCapacity()` có thể trả về `-1` nếu không xác định được. Dữ liệu này giúp quan sát direct/mapped ByteBuffer pool nhưng không phải báo cáo đầy đủ cho mọi native allocation.

Netty `PooledByteBufAllocator` cũng cung cấp allocator metrics tùy version, có thể bao gồm used heap/direct memory, số arena và thread-local cache. Có thể lấy metric từ allocator đang dùng và xuất ra hệ thống monitoring. Không tạo một allocator khác chỉ để đọc metrics vì sẽ đo nhầm pool.

Nên theo dõi đồng thời:

- Heap used, GC frequency và pause time.
- Direct/mapped buffer pool usage.
- Netty pooled allocator metrics.
- Process RSS và native memory nếu môi trường hỗ trợ.
- Số buffer/payload đang sống, active streams và queue depth.
- Allocation rate, bytes copied nếu profiler có thể quan sát.
- p50/p95/p99 latency, throughput và CPU.

## 19. Phát hiện leak và lỗi ownership

Netty ResourceLeakDetector giúp phát hiện một số trường hợp reference-counted resource không được release. Trong môi trường phát triển hoặc test, có thể tăng mức kiểm tra:

```text
-Dio.netty.leakDetection.level=advanced
```

Các mức kiểm tra cao hơn có thể tăng overhead. `paranoid` phù hợp với test cô lập hoặc điều tra có kiểm soát, không nên bật tùy tiện cho production tải lớn.

Các dấu hiệu cần phân biệt:

| Lỗi | Triệu chứng thường gặp |
|---|---|
| Memory leak | Direct memory tăng dần, leak detector cảnh báo, buffer không được release. |
| Double release | `IllegalReferenceCountException` hoặc reference count không hợp lệ. |
| Use-after-release | Truy cập buffer sau khi reference count về 0. |
| Pool retention | Allocator giữ vùng nhớ để tái sử dụng dù buffer đã release. |
| Fragmentation | Tổng vùng nhớ trống không đồng nghĩa có block phù hợp với yêu cầu cấp phát. |

Khi nhận `OutOfMemoryError: Direct buffer memory`, kiểm tra cả leak, peak concurrency, kích thước payload, allocator pool và giới hạn direct memory. Không chỉ tăng heap vì heap và direct memory là hai vùng khác nhau.

## 20. Benchmark zero-copy và direct memory đúng cách

Một benchmark chỉ đo `slice()` nhanh hơn `copy()` không đủ để kết luận toàn bộ ứng dụng RSocket nhanh hơn. Cần đo đường đi end-to-end và workload thực tế.

### Các biến cần thay đổi

- Heap buffer so với direct buffer.
- Pooled so với unpooled allocator.
- Copy so với slice/retained slice/composite buffer.
- Kích thước payload và metadata.
- Payload đơn so với fragmentation.
- TCP so với WebSocket.
- TLS bật/tắt nếu production sử dụng TLS.
- Mức concurrency và số connection.
- `requestResponse`, `requestStream`, `requestChannel` và fire-and-forget.
- Codec và compression thực tế.

### Các chỉ số cần đo

- Throughput (messages/s và bytes/s).
- Latency p50, p95 và p99.
- CPU và memory bandwidth.
- Allocation rate và GC pause.
- Direct memory, heap và RSS.
- Số buffer còn sống và leak detector warnings.
- Số frame trên mỗi payload và thời gian reassembly.
- Tỷ lệ timeout, cancellation và lỗi transport.

### Quy trình

1. Dùng JMH cho các phép đo hẹp như copy, slice, encode hoặc decode.
2. Dùng integration/load test qua RSocket transport thật để đo overhead của frame, TLS và scheduler.
3. Warm up JVM và allocator trước khi ghi số liệu.
4. Dùng cùng dữ liệu, concurrency và thời gian chạy giữa các phương án.
5. Đo cả steady state và burst/peak load.
6. Chạy đủ lâu để thấy pool growth, GC và hành vi sau khi tải giảm.
7. So sánh p99 và memory footprint, không chỉ throughput trung bình.
8. Lặp lại nhiều lần và ghi rõ JVM, Netty, Spring và phần cứng.

Tối ưu chỉ có giá trị nếu cải thiện mục tiêu đã chọn mà không làm xấu latency tail, memory footprint hoặc độ ổn định.

## 21. Khi nào nên dùng direct memory, pooling và zero-copy?

| Điều kiện | Hướng cân nhắc |
|---|---|
| I/O network throughput cao, buffer được tái sử dụng | Direct `ByteBuf` và pooled allocator có thể hữu ích; đo allocator metrics. |
| Buffer nhỏ, ngắn hạn và số lượng thấp | Heap buffer có thể đơn giản và đủ nhanh. |
| Cần truyền một vùng dữ liệu con đồng bộ | `slice()`/`duplicate()` tránh copy nếu lifetime nguồn được bảo đảm. |
| Cần giữ view qua async boundary | `retainedSlice()`/`retain()` với cleanup rõ ràng hoặc copy nếu cần ownership độc lập. |
| Ghép nhiều component mà consumer đọc được từng vùng | `CompositeByteBuf` có thể tránh copy ngay lúc ghép. |
| Consumer bắt buộc một vùng liên tục | Có thể cần consolidate/copy; benchmark trước khi tối ưu. |
| Payload lớn và stream dài | Chia batch/stream, backpressure và giới hạn bytes. |
| Native memory tăng không kiểm soát | Kiểm tra ownership, leak, pool retention, concurrency và direct-memory limit. |

Không áp dụng zero-copy bằng mọi giá. Một lần copy có kiểm soát đôi khi tốt hơn chia sẻ buffer phức tạp, kéo dài lifetime hoặc gây contention. Copy cũng có thể giúp giảm coupling giữa component và đơn giản hóa ownership.

## 22. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ direct memory luôn nhanh hơn heap | Tăng chi phí cấp phát hoặc native memory mà không giảm copy thực tế. | Benchmark theo workload và vòng đời buffer. |
| Đồng nhất direct memory với zero-copy | Bỏ qua copy trong codec, TLS, compression và transport. | Theo dõi từng ranh giới copy. |
| Dùng `slice()` sau khi parent đã release | View trỏ vào vùng nhớ không còn hợp lệ. | Giữ parent sống hoặc dùng retained view đúng cách. |
| Gọi `retain()` nhưng quên `release()` | Giữ buffer và làm direct memory tăng. | Ghép mỗi retain với một release ở mọi đường complete/error/cancel. |
| Release payload sau khi đã chuyển ownership | Runtime hoặc subscriber có thể truy cập buffer đã giải phóng. | Theo đúng ownership contract của RSocket API. |
| Dùng `copy()` cho mọi thao tác nhỏ | Tăng CPU, memory bandwidth và allocation rate. | Dùng view khi lifetime cho phép; copy khi cần độc lập. |
| Cho rằng `CompositeByteBuf` không bao giờ copy | Consumer có thể yêu cầu vùng liên tục và kích hoạt copy. | Đo toàn bộ consumer path. |
| Chỉ nhìn heap để chẩn đoán OOM | Bỏ qua direct/native memory. | Theo dõi BufferPoolMXBean, Netty metrics và RSS. |
| Coi pool giữ memory là leak | Tuning sai allocator hoặc tăng churn không cần thiết. | Quan sát xu hướng, live references và leak detector. |
| Coi mọi memory không trả OS là pool retention | Bỏ sót leak thật. | Kết hợp allocator metrics, leak detector và load-cycle tests. |
| Gửi payload cực lớn rồi dựa vào fragmentation | Peak memory/reassembly có thể rất cao. | Dùng streaming/chunking và size limit. |
| Chỉ benchmark micro-operation | Kết quả không phản ánh TLS, transport và concurrency thật. | Bổ sung end-to-end load test. |

## 23. Checklist tối ưu RSocket memory path

Trước khi thay đổi allocator hoặc buffer strategy, hãy trả lời:

- Payload được encode/decode qua những lớp nào và copy xảy ra ở đâu?
- Payload lớn có thực sự cần là một message duy nhất hay có thể stream theo batch?
- Kích thước frame và fragmentation có phù hợp với workload không?
- Direct memory có giảm copy trong đường I/O thực tế hay chỉ chuyển nơi cấp phát?
- Pooled allocator đang giữ bao nhiêu heap/direct memory?
- Buffer nào được chia sẻ qua slice/duplicate và ai sở hữu lifetime?
- Mỗi `retain()` có một `release()` tương ứng trong complete/error/cancel không?
- Composite buffer có bị consumer consolidate thành một vùng liên tục không?
- Backpressure, concurrency, prefetch và queue có giới hạn số bytes đang giữ không?
- Heap, direct memory, RSS, GC và allocator metrics có được quan sát riêng không?
- Có test leak, use-after-release và peak-load không?
- Benchmark có bao gồm transport, TLS, codec, payload size và p99 latency không?

## Kết luận

Phân mảnh payload ở tầng RSocket làm tăng số frame và chi phí reassembly; phân mảnh allocator làm vùng nhớ khó được tái sử dụng hiệu quả. Direct memory có thể giảm một số lần copy giữa heap và native I/O, còn zero-copy dựa trên view hoặc composite buffer có thể tránh copy ở những ranh giới cụ thể. Cả hai đều có trade-off về allocation, pooling, lifetime và ownership. Trong RSocket Java, hãy hiểu rõ `ByteBuf`/`Payload` reference counting, phân biệt direct memory với zero-copy, giới hạn kích thước và concurrency, theo dõi heap/direct/native memory riêng và benchmark qua transport thật. Một pipeline tối ưu là pipeline giảm được copy và allocation thực sự mà vẫn giữ vòng đời buffer an toàn, backpressure ổn định và latency dự đoán được.
