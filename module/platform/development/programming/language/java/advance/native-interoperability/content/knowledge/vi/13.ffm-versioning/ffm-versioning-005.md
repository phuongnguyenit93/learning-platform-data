# An toàn phạm vi, thời gian sống và truy cập theo luồng mà FFM kiểm tra

Java Foreign Function & Memory API (FFM) cung cấp một cách mô hình hóa vùng nhớ ngoài Java heap, truy cập chúng có kiểm tra và gọi hàm native qua `java.lang.foreign`. Điểm khác biệt quan trọng so với việc dùng địa chỉ C trần là: một `MemorySegment` không chỉ là pointer. Nó mang **giới hạn kích thước**, **scope/thời gian sống**, và trong trường hợp phù hợp còn có **ràng buộc thread**. Nhờ vậy, một số lỗi bộ nhớ có thể bị phát hiện bằng Java exception trước khi truy cập sai.

Ví dụ, một vùng nhớ 8 byte được cấp bởi `Arena.ofConfined()` cho thread A:

- Thread A đọc `int` tại offset `0` khi arena còn mở → hợp lệ.
- Thread A đọc 4 byte tại offset `8` → `IndexOutOfBoundsException` vì vượt giới hạn 8 byte.
- Thread B cố đọc vùng này khi arena vẫn mở → `WrongThreadException` vì sai owner thread.
- Arena được đóng đúng cách; thread A cố đọc lại → `IllegalStateException` vì scope không còn alive.

**Điều cần hiểu đúng:** Các kiểm tra trên có hiệu lực với **những truy cập được thực hiện qua FFM API và những ràng buộc mà segment thực sự mô tả**. FFM không thể tự suy ra tuổi thọ của một địa chỉ native không rõ nguồn gốc, không thể sửa mọi data race giữa các thread và không thể đảm bảo an toàn cho toàn bộ code C/C++ được gọi qua FFM. Cấp sai vùng nhớ hoặc gán kích thước/thời gian sống giả bằng một restricted method vẫn có nguy cơ lỗi bộ nhớ nghiêm trọng.

## 1. Mốc phiên bản: mã ví dụ trong bài dùng Java 22+

FFM phát triển qua nhiều phiên bản và tên API đã thay đổi. Để tránh nhầm giữa ví dụ cũ và API hiện hành:

| JDK | Trạng thái API | Điểm cần lưu ý |
| --- | --- | --- |
| Java 17 | API foreign memory/function thời kỳ **incubator** trong module `jdk.incubator.foreign` | Không sử dụng cùng mã `java.lang.foreign.Arena`/`MemorySegment` dưới đây |
| Java 19 | FFM API **preview** theo JEP 424 | Phải bật preview; tên API/hành vi còn thay đổi |
| Java 20 | Preview tiếp theo, JEP 434 | Một số factory và cách dùng arena khác bản cuối |
| Java 21 | Preview tiếp theo, JEP 442 | Có `java.lang.foreign`, nhưng preview vẫn có khác biệt với Java 22 |
| **Java 22 trở lên** | FFM được **finalize theo JEP 454** | Dùng `java.lang.foreign.Arena`, `MemorySegment`, `ValueLayout` và ví dụ trong bài |

Các đoạn runnable ở đây yêu cầu **JDK 22+**, không tuyên bố biên dịch được bằng JDK 17. Chúng chỉ thực hiện native memory allocation/access thông thường, **không gọi restricted foreign functions**, nên không cần `--enable-native-access` để chạy chương trình minh họa. Khi ứng dụng dùng các API restricted như mở thư viện native để thực hiện downcall hay `MemorySegment.reinterpret`, phải kiểm tra chính sách native access của JDK đang chạy, chẳng hạn `--enable-native-access=ALL-UNNAMED` cho chương trình trên classpath khi phù hợp.

**Đừng chỉ thay số phiên bản:** một đoạn JDK 20 dùng `Arena.openConfined()` hoặc `allocateUtf8String` có thể không còn khớp API đã finalize. Trong JDK 22+, cách khởi tạo arena phổ biến là `Arena.ofConfined()`/`Arena.ofShared()`, và các phương thức cấp phát chuỗi ở API mới có tên phù hợp như `allocateFrom(String)`. Mọi hướng dẫn bảo mật/concurrency phải gắn với đúng phiên bản API.

## 2. Ba lớp an toàn: không gian, thời gian và thread

Một truy cập FFM có ý nghĩa nếu nó thỏa các điều kiện độc lập:

```text
MemorySegment (địa chỉ + kích thước + scope + đặc tính truy cập)
             │
             ├── [1] Spatial: offset + sizeof(layout)
             │         phải nằm hoàn toàn trong byteSize()
             │
             ├── [2] Temporal: scope phải còn alive
             │         trong thời gian thực hiện thao tác
             │
             ├── [3] Thread access: thread hiện tại
             │         phải tương thích với confinement
             │
             └── [4] Other access rules:
                       alignment đúng theo ValueLayout,
                       không ghi vào read-only segment,
                       layout/operation tương thích
             │
             ▼
        Đọc/ghi bộ nhớ hợp lệ qua FFM
```

| Kiểm tra | FFM biết từ đâu? | Lỗi thường gặp |
| --- | --- | --- |
| **Spatial safety** | `byteSize()`, offset, kích thước layout | `IndexOutOfBoundsException` |
| **Temporal safety** | `scope()` và trạng thái arena alive/closed | `IllegalStateException` khi access sau close |
| **Thread confinement** | Owner thread/đặc tính của scope | `WrongThreadException` |
| **Alignment** | `ValueLayout.byteAlignment()` và địa chỉ/offset | `IllegalArgumentException` |
| **Read-only** | `segment.isReadOnly()` | `IllegalArgumentException` khi ghi |
| **Foreign pointer thực sự hợp lệ?** | Không thể xác minh mọi địa chỉ, allocation/lifetime native bên ngoài | Có thể dẫn đến crash/corruption nếu khai báo sai hoặc gọi native code lỗi |

Không phụ thuộc vào tên exception như một cách điều khiển luồng bình thường. Thiết kế nên **ngăn truy cập sai ngay từ ownership/lifecycle**, còn exception giúp phát hiện và chẩn đoán lỗi. Nếu một thao tác vi phạm đồng thời nhiều điều kiện, đừng xây logic dựa trên thứ tự kiểm tra/ưu tiên ngoại lệ chưa được API cam kết.

## 3. `MemorySegment` không chỉ là địa chỉ

`MemorySegment` là interface mô hình hóa **vùng nhớ liên tiếp**. Một native segment có thể được tạo bởi arena:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(8, 4);
    segment.set(ValueLayout.JAVA_INT, 0, 123);
    System.out.println(segment.get(ValueLayout.JAVA_INT, 0));
}
```

Đoạn này minh họa một khối mã đặt trong method phù hợp; nếu sử dụng như Java source cần một class/method bao ngoài. `allocate(8, 4)` cấp **8 byte** với **căn lề 4 byte**; `ValueLayout.JAVA_INT` đọc/ghi Java `int` kích thước 4 byte. Output trong điều kiện thành công là `123`.

Các khái niệm:

- `segment.address()`: địa chỉ mô tả vùng nhớ. Với native segment, đó là địa chỉ native; với heap segment, nó có nghĩa khác. Đừng dùng số địa chỉ trần làm thay cho segment có scope và byte bounds.
- `segment.byteSize()`: kích thước vùng **theo byte**, không phải số phần tử `int`/`long`.
- `segment.scope()`: đối tượng `MemorySegment.Scope` mô hình hóa **lifetime** của vùng.
- `segment.scope().isAlive()`: cho biết scope còn hiệu lực tại thời điểm hỏi.
- `segment.isAccessibleBy(Thread)`: cho biết khả năng truy cập segment theo một thread nhất định.
- `segment.isReadOnly()`: phân biệt vùng có thể ghi hay view chỉ đọc.
- `segment.asSlice(offset, size)`: tạo view vào một phần vùng gốc, **không cấp thêm backing memory** và **không kéo dài lifetime**.

Đừng nhầm `byteSize()` với khả năng truy cập vô điều kiện. Một `MemorySegment` Java object có thể vẫn tồn tại trong heap sau khi backing memory đã được giải phóng. Giữ được biến `segment` chỉ có nghĩa giữ được **metadata/handle**, không hồi sinh scope đã đóng.

### Heap segment và native segment không giống nhau

`MemorySegment.ofArray(new int[]{10, 20})` tạo **heap segment** dùng Java array backing store. Theo đặc tả, heap segments có scope tự động gắn với lifecycle Java object và có thể được truy cập từ mọi thread; không cần/không thể tùy ý đóng một confined arena riêng cho array đó.

Ngược lại, `arena.allocate(...)` tạo native segment ngoài Java heap, và arena chọn **khi nào** backing memory được giải phóng cũng như **thread nào** có thể truy cập. Cả hai đều chịu kiểm tra bounds/alignment theo FFM, nhưng không nên gán chính sách close của native memory cho Java arrays.

## 4. `Arena` định nghĩa vòng đời và confinement

`Arena` thực hiện `AutoCloseable` và `SegmentAllocator`. Các segment cấp từ cùng một arena gắn với arena scope; khi một arena có khả năng đóng được đóng **thành công**, scope không còn alive và các native regions backing các segment của arena được giải phóng.

| Kiểu arena (JDK 22+) | Lifetime | Đóng tường minh? | Nhiều thread có thể truy cập segment? | Phù hợp |
| --- | --- | --- | --- | --- |
| `Arena.ofConfined()` | Có giới hạn, do caller quản lý | **Có**, bởi owner thread | **Không**; chỉ owner | Native buffer ngắn hạn trong một method/thread |
| `Arena.ofShared()` | Có giới hạn, do caller quản lý | **Có**, từ bất kỳ thread theo contract | **Có** | Workflows nhiều thread đã đồng bộ ownership |
| `Arena.ofAuto()` | GC quản lý, thời điểm thu hồi không xác định | **Không**; `close` gây `UnsupportedOperationException` | **Có** | Vùng được quản lý tự động khi không cần deterministic close |
| `Arena.global()` | Không giới hạn trong thời gian chạy VM | **Không**; `close` gây `UnsupportedOperationException` | **Có** | Vùng tồn tại lâu dài, có ý thức về chi phí bộ nhớ |

**Không có một kiểu arena “tốt nhất” cho mọi tình huống.** Nên bắt đầu bằng `ofConfined()` cho dữ liệu chỉ sống trong một thread và dùng `try-with-resources` để dọn deterministic. Dùng `ofShared()` khi thật sự cần nhiều threads; thêm đồng bộ/lifecycle policy. Dùng `ofAuto()` khi GC-controlled lifetime là phù hợp, không dựa vào thời điểm giải phóng cụ thể. Tránh lạm dụng `Arena.global()` cho dữ liệu tùy ý hoặc cấp phát trong vòng lặp không có kế hoạch thu hồi: native memory có thể tăng mà không được giải phóng trong đời tiến trình.

### Vì sao `try-with-resources` là mặc định tốt?

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment input = arena.allocate(64);
    MemorySegment output = arena.allocate(64);
    // Xử lý nhanh trên owner thread, không làm segment thoát khỏi scope.
} // arena.close() tự được gọi khi rời block.
```

Đây là đoạn minh họa trong method. Khi block kết thúc bình thường hoặc có Java exception, `try-with-resources` thực hiện `close()`. Một arena sở hữu nhiều segment vẫn được dọn tập trung. Không cần gọi `free` cho từng segment hay lưu địa chỉ trần.

Chú ý: `Arena.close()` không idempotent. Nếu đã close rồi gọi lần nữa, JDK quy định có thể ném `IllegalStateException`. Đừng thiết kế hai component tự cùng gọi `close` trên một arena mà không có quy tắc ownership.

## 5. Temporal safety: scope còn sống mới được truy cập

Ví dụ phổ biến nhất:

```java
MemorySegment escaped;
try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(4, 4);
    escaped.set(ValueLayout.JAVA_INT, 0, 7);
}
int x = escaped.get(ValueLayout.JAVA_INT, 0);
// Sai: truy cập sau close -> IllegalStateException.
```

Đây là đoạn minh họa, cần các imports phù hợp. Biến `escaped` vẫn trỏ tới một `MemorySegment`, nhưng arena đã được đóng. FFM phát hiện lỗi **use-after-close** trên thao tác Java `get` và không cho phép đọc backing memory qua API đó.

Những hình thức “đổi vỏ” không gia hạn thời gian sống:

- `MemorySegment view = segment.asSlice(0, 4)`: view kế thừa scope; close arena của segment gốc khiến slice không còn truy cập được.
- `MemorySegment readonly = segment.asReadOnly()`: view readonly không tự sở hữu native allocation mới, cũng không kéo dài lifetime.
- `ByteBuffer buffer = segment.asByteBuffer()`: buffer có lifecycle gắn với segment; sau khi scope đóng, truy cập buffer cũng bị kiểm tra theo contract.
- Lưu segment vào `static`, field, collection, lambda hoặc closure **không** biến vùng memory thành global.
- Giữ địa chỉ `long address = segment.address()` càng không kéo dài vòng đời backing memory.

### Phân biệt `scope().isAlive()` và an toàn đến cuối thao tác

`scope().isAlive()` hữu ích để chẩn đoán. Nhưng đoạn sau **không đủ** làm hàng rào đồng bộ khi nhiều threads cùng thao tác với shared arena:

```java
// Mã minh họa lỗi TOCTOU, không phải giải pháp đồng bộ.
if (segment.scope().isAlive()) {
    // Thread khác có thể cố đóng arena tại thời điểm này.
    consume(segment);
}
```

Đây là vấn đề *time-of-check to time-of-use*: kiểm tra alive ở thời điểm T1 không phải hợp đồng bảo đảm rằng scope còn mở ở T2. FFM có cơ chế để ngăn use-after-free trong các thao tác FFM hợp lệ và quy tắc đóng arena, nhưng logic của ứng dụng vẫn cần xác định ai có quyền close, khi nào workers đã kết thúc và khi nào không còn outstanding operations/callbacks.

Với Java API dựa vào native data, an toàn nhất là **không trả một segment có scope sắp đóng** ra ngoài. Nếu cần trả kết quả sống lâu hơn, **copy giá trị** sang Java heap hoặc cấp nó từ arena có owner/lifetime phù hợp, được caller quản lý rõ.

## 6. Thread confinement: `ofConfined()` thực sự giới hạn thread

Arena confined có **owner thread**, thường là thread tạo arena. Các native segments được allocate từ nó chỉ được truy cập từ owner thread. Chuyển tham chiếu `MemorySegment` sang thread B qua `Thread`, `ExecutorService`, `CompletableFuture` hoặc virtual thread **không chuyển quyền ownership**.

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(4, 4);
    segment.set(ValueLayout.JAVA_INT, 0, 41);

    Thread worker = new Thread(() -> {
        // Truy cập native segment từ thread khác: WrongThreadException.
        segment.get(ValueLayout.JAVA_INT, 0);
    });
    worker.start();
    worker.join();
}
```

Đoạn minh họa ở trên thiếu code xử lý exception trong thread mới; phần thực hành đầy đủ bên dưới dùng `catch`, nên không có stack trace ngoài dự kiến. Đặc điểm đáng chú ý:

- `segment.isAccessibleBy(Thread.currentThread())` ở owner thread trả `true`.
- Cùng phép kiểm tra trong thread khác trả `false` cho segment từ confined arena.
- `get`/`set` trên segment từ thread khác gây `java.lang.WrongThreadException`.
- Gọi `arena.close()` trên **thread khác owner** cũng gây `WrongThreadException`; đây là kiểm tra lifetime ownership.
- `WrongThreadException` thuộc **`java.lang`**, không phải `java.lang.foreign`. Không import từ package sai.

Đặt một `synchronized` block quanh segment confined **không** thay đổi owner thread. Sử dụng `volatile` cũng không khiến nó trở nên multi-thread accessible. Đây là **quy tắc truy cập của FFM**, không phải chỉ là race condition mà bạn có thể giải quyết bằng lock.

### Chọn cách truyền dữ liệu sang worker

Có hai cách phổ biến:

1. **Copy sang Java data:** owner thread đọc/chép dữ liệu khi confined arena còn alive, giao `byte[]`, `int[]`, record bất biến hoặc `String` cho worker. Các Java objects đó có lifecycle và luật đồng bộ riêng, không lệ thuộc vào confined scope đã đóng.
2. **Sử dụng shared arena có kiểm soát:** các threads cùng dùng native segment từ `Arena.ofShared()`, và coordinator chỉ đóng arena sau khi mọi outstanding tasks đã kết thúc (ví dụ `Future.get`/`join`).

Đừng tạo một confined arena ở thread A rồi mong worker thread B sẽ “nhận” nó sau khi A kết thúc. Nếu worker tự tạo confined arena **bên trong chính worker**, nó có thể dùng native segment trong thread đó và tự close trước khi hoàn thành.

## 7. Shared arena: được nhiều thread truy cập không có nghĩa thread-safe data

`Arena.ofShared()` cho phép các segments của nó được truy cập từ nhiều threads và arena có thể được đóng từ thread bất kỳ theo API contract. Nó **không tự đồng bộ mọi phép đọc/ghi của dữ liệu** nằm trong native memory.

```java
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(8, 4);

    segment.set(ValueLayout.JAVA_INT, 0, 100);

    Thread worker = new Thread(() -> {
        int v = segment.get(ValueLayout.JAVA_INT, 0);
        segment.set(ValueLayout.JAVA_INT, 4, v + 7);
    });

    worker.start();
    worker.join(); // Chờ worker xong trước khi close arena.

    System.out.println(segment.get(ValueLayout.JAVA_INT, 4)); // 107
}
```

Ở ví dụ này, thread chính **ghi trước khi worker khởi chạy**, worker đọc/ghi, thread chính **đợi `join`** rồi mới đọc kết quả và đóng arena. Cách sắp xếp đó tránh truy cập đồng thời vào vùng đang xử lý. Không thể bỏ `join` rồi kết luận `ofShared` đủ để đảm bảo consistency.

Nếu hai threads cùng cập nhật một counter trong shared segment bằng `get` → tăng → `set`, đây có thể là **read-modify-write race**, tương tự như truy cập shared fields Java không đồng bộ. Hãy dùng cơ chế synchronization thích hợp, memory ordering và `VarHandle` với thao tác atomic khi được hỗ trợ (và đúng alignment/ABI). FFM kiểm tra **quyền truy cập và vùng nhớ**, không tự biến mọi operation thành atomic.

### Nếu một thread đóng shared arena khi thread khác đang làm việc?

Đặc tả cung cấp temporal safety: sau khi close thành công, các segment không còn được truy cập. `Arena.close()` có thể ném `IllegalStateException` nếu có thao tác trên segment đang diễn ra đồng thời, chẳng hạn một downcall; đây không phải là API “ép đóng” mọi hoạt động. Không nên dùng close như một primitive hủy task.

Chính sách tốt:

```text
Application owner
  |
  +-- Tạo Arena.ofShared()
  +-- Phát segment cho các worker có giới hạn rõ
  +-- Ngừng phát task mới
  +-- Chờ workers/callbacks hoàn tất
  +-- Close shared arena một lần
  +-- Không cho phép task mới dùng segment cũ
```

Chỉ một component quyết định lifecycle cuối cùng. Nếu dùng async API, cần hiểu callback có thể chạy sau khi phương thức Java trả về; đóng arena ngay trong `finally` của hàm khởi tạo async work có thể là **quá sớm**.

## 8. Spatial safety, alignment và read-only cũng là phần của kiểm tra

### Bounds: offset tính bằng **byte**

Một vùng `arena.allocate(8, 4)` chứa 8 byte, đủ cho 2 giá trị `int`. Với layout 4 byte `ValueLayout.JAVA_INT`:

| Thao tác | Offset | Vùng đụng tới | Kết quả |
| --- | ---: | --- | --- |
| `get(JAVA_INT, 0)` | 0 | Byte 0–3 | Hợp lệ |
| `get(JAVA_INT, 4)` | 4 | Byte 4–7 | Hợp lệ |
| `get(JAVA_INT, 8)` | 8 | Byte 8–11 | **Vượt biên** |
| `get(JAVA_INT, 1)` | 1 | Byte 1–4 | Trong 8 byte nhưng **không đúng alignment 4** |

Vì vậy chỉ kiểm tra `offset < byteSize()` là chưa đủ; phải có chỗ cho **toàn bộ `layout.byteSize()`**, và đúng alignment. `MemorySegment.get`/`set` làm các kiểm tra cần thiết theo API. Với offset 8 ở bảng, `IndexOutOfBoundsException`; với offset 1 khi vùng base aligned 4, `IllegalArgumentException` do alignment.

`getAtIndex(ValueLayout.JAVA_INT, index)` tính offset theo index của phần tử, thay vì byte offset; tránh nhầm index 1 thành offset 1 byte. `ValueLayout.JAVA_INT` mang byte order theo mặc định của layout (native order), nhưng encoding/ABI của struct C vẫn cần được kiểm tra riêng.

### Slice có bounds riêng, nhưng không có lifetime riêng

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(16, 4);
    MemorySegment secondInt = block.asSlice(4, 4);

    secondInt.set(ValueLayout.JAVA_INT, 0, 99);
    // secondInt.get(JAVA_INT, 4) sai: slice chỉ dài 4 byte.
}
```

Mọi truy cập qua `secondInt` phải nằm trong 4 byte của **slice**, không phải 16 byte của `block`. Khi arena đóng, cả `block` lẫn `secondInt` đều không còn quyền truy cập.

### Read-only view

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(4, 4);
    block.set(ValueLayout.JAVA_INT, 0, 5);

    MemorySegment readOnly = block.asReadOnly();
    int value = readOnly.get(ValueLayout.JAVA_INT, 0); // hợp lệ.
    // readOnly.set(ValueLayout.JAVA_INT, 0, 6): IllegalArgumentException.
}
```

`asReadOnly()` chỉ tạo một **view**; nó không làm backing bytes bất biến nếu alias writable khác vẫn còn. Và nó không làm segment được đọc từ mọi thread hay sống mãi sau khi arena đóng.

## 9. Bài thực hành độc lập: phân biệt từng lỗi FFM (Java 22+)

Chương trình sau chỉ dùng FFM memory access, không gọi native function hay `reinterpret`. Nó kiểm tra:

- `Arena.ofConfined()`: đọc hợp lệ trên owner thread và fail trên thread khác.
- Bounds/alignment/read-only: ba dạng lỗi khác nhau.
- `scope().isAlive()`: `true` trong block, `false` sau `close`.
- Slice còn là Java object sau khi close nhưng không thể `get`.
- `Arena.ofShared()`: worker có thể đọc/ghi trước khi arena đóng.
- Heap segment: `MemorySegment.ofArray` truy cập Java array.

**File `FfmScopeSafetyDemo.java`**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class FfmScopeSafetyDemo {
    public static void main(String[] args) throws InterruptedException {
        MemorySegment escaped = null;

        try (Arena confined = Arena.ofConfined()) {
            MemorySegment segment = confined.allocate(8, 4);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            segment.set(ValueLayout.JAVA_INT, 4, 99);

            escaped = segment.asSlice(4, 4);

            System.out.println("confined=" +
                    segment.get(ValueLayout.JAVA_INT, 0));
            System.out.println("aliveInside=" +
                    segment.scope().isAlive());

            Thread worker = new Thread(() -> {
                System.out.println("otherAccessible=" +
                        segment.isAccessibleBy(Thread.currentThread()));
                try {
                    segment.get(ValueLayout.JAVA_INT, 0);
                    System.out.println("unexpectedThreadSuccess");
                } catch (WrongThreadException e) {
                    System.out.println(
                            "otherThread=WrongThreadException");
                }
            });

            worker.start();
            worker.join();

            try {
                segment.get(ValueLayout.JAVA_INT, 8);
                System.out.println("unexpectedBoundsSuccess");
            } catch (IndexOutOfBoundsException e) {
                System.out.println(
                        "outOfBounds=IndexOutOfBoundsException");
            }

            try {
                segment.get(ValueLayout.JAVA_INT, 1);
                System.out.println("unexpectedAlignmentSuccess");
            } catch (IllegalArgumentException e) {
                System.out.println("misaligned=IllegalArgumentException");
            }

            try {
                segment.asReadOnly().set(ValueLayout.JAVA_INT, 0, 1);
                System.out.println("unexpectedReadOnlySuccess");
            } catch (IllegalArgumentException e) {
                System.out.println("readOnly=IllegalArgumentException");
            }
        }

        System.out.println("aliveAfter=" +
                escaped.scope().isAlive());

        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
            System.out.println("unexpectedAfterCloseSuccess");
        } catch (IllegalStateException e) {
            System.out.println("afterClose=IllegalStateException");
        }

        try (Arena shared = Arena.ofShared()) {
            MemorySegment segment = shared.allocate(8, 4);
            segment.set(ValueLayout.JAVA_INT, 0, 100);

            Thread worker = new Thread(() -> {
                int value = segment.get(ValueLayout.JAVA_INT, 0);
                segment.set(ValueLayout.JAVA_INT, 4, value + 7);
            });

            worker.start();
            worker.join();

            System.out.println("sharedResult=" +
                    segment.get(ValueLayout.JAVA_INT, 4));
        }

        MemorySegment heap = MemorySegment.ofArray(
                new int[] {5, 6});
        System.out.println("heapValue=" +
                heap.getAtIndex(ValueLayout.JAVA_INT, 1));
    }
}
```

**Biên dịch và chạy (JDK 22+):**

```bash
javac FfmScopeSafetyDemo.java
java FfmScopeSafetyDemo
```

Đây là **Java 22+ source hoàn chỉnh** (class và tên file trùng nhau); dùng cả `javac` và `java` từ cùng một JDK 22 hoặc mới hơn. Không dùng `--enable-preview` cho FFM đã finalize ở Java 22. Nếu dùng JDK 21 hoặc cũ hơn, không coi compilation failure là lỗi chương trình: hãy chọn đúng JDK cho ví dụ.

**Stdout kỳ vọng:**

```text
confined=42
aliveInside=true
otherAccessible=false
otherThread=WrongThreadException
outOfBounds=IndexOutOfBoundsException
misaligned=IllegalArgumentException
readOnly=IllegalArgumentException
aliveAfter=false
afterClose=IllegalStateException
sharedResult=107
heapValue=6
```

Giải thích output:

1. Vùng native confined có 8 byte, chứa hai `int`. Giá trị offset 0 là 42, scope còn sống trước khi rời `try`.
2. Worker thread thấy `isAccessibleBy` bằng `false`; một lần `get` trên segment confined phát sinh `WrongThreadException`. Thread chính dùng `join` nên output theo đúng thứ tự.
3. Offset 8 dành cho `int` 4 byte vượt bounds; offset 1 chưa đúng alignment 4; view read-only không cho `set`.
4. `escaped` là slice dài 4 byte nằm tại offset 4 của khối gốc, nhưng **cùng scope** với arena confined. Sau khi rời `try`, `isAlive() == false`; truy cập slice tạo `IllegalStateException`.
5. Shared arena cho phép worker đọc 100 và ghi 107 ở offset 4, rồi thread chính đọc 107 sau `join`. Không có phép truy cập sau khi shared arena đóng.
6. Heap segment bọc `int[]{5,6}` nên `getAtIndex(..., 1)` trả 6.

Ví dụ không dùng `System.loadLibrary`, JNI, FFM downcall hoặc con trỏ C, bởi mục đích là kiểm tra **memory safety/lifecycle** trước khi thêm các rủi ro của native function interoperability.

## 10. Lỗi phổ biến khi truyền segment qua async API

### Lỗi: đóng arena trước khi callback dùng segment

```java
// Pseudocode: service.submit() là một executor đã được cấu hình.
MemorySegment segment;
try (Arena arena = Arena.ofShared()) {
    segment = arena.allocate(128);
    service.submit(() -> consume(segment));
} // Sai về thiết kế: arena có thể đóng trước khi consume() chạy.
```

Đây là **mã minh họa** với `service`/`consume` chưa được khai báo. `ofShared` cho phép worker truy cập theo thread nhưng **không** bảo đảm tồn tại đến lúc worker thực sự chạy. Chương trình có thể gặp `IllegalStateException` hoặc thất bại ở thời điểm sử dụng nếu arena đã đóng.

### Cách đúng: owner đợi mọi task xong trước khi close

```java
// Minh họa trong method có ExecutorService executor và
// phương thức consume(MemorySegment) đã khai báo.
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(128);

    java.util.concurrent.Future<?> task =
            executor.submit(() -> consume(segment));

    task.get(); // Ví dụ này cần xử lý checked exceptions thích hợp.
} // task đã hoàn thành, mới close.
```

Đây là **đoạn ý tưởng**, không phải code độc lập. Trong ứng dụng thực, còn phải đảm bảo không có task khác, callback hoặc native code nào vẫn sử dụng segment, xử lý cancellation/failure và đóng owner sau khi tất cả outstanding operations được xác nhận hoàn tất. `Future.get()` ném checked exceptions, cần `throws` hoặc `catch` đúng chỗ.

### Lỗi: dùng ThreadLocal để giả định chuyển quyền confined

```java
// Không hợp lệ về mặt thiết kế:
MemorySegment confinedData = createOnThreadA();
startThreadB(() -> confinedData.get(ValueLayout.JAVA_INT, 0));
```

Đây là pseudocode; không có phép “đổi owner” bằng việc đi qua Java collection, `ThreadLocal`, `CompletableFuture` hoặc thay thread name. Nếu cần truy cập ở thread B, hoặc copy dữ liệu sang đối tượng Java, hoặc tạo confined arena **trên B**, hoặc dùng shared arena từ đầu.

## 11. Trường hợp API cầu nối: slice, ByteBuffer và closure

Một library Java có thể bọc segment thành một API nhìn rất bình thường:

```java
// Đoạn minh họa; không phải chương trình độc lập.
final class NativeBlock implements AutoCloseable {
    private final Arena arena = Arena.ofConfined();
    private final MemorySegment data = arena.allocate(64);

    byte read(long index) {
        return data.get(ValueLayout.JAVA_BYTE, index);
    }

    @Override
    public void close() {
        arena.close();
    }
}
```

Mẫu trên hữu ích khi `NativeBlock` luôn được dùng **trên thread tạo nó**, đóng đúng một lần và không để `MemorySegment`/`ByteBuffer` thoát ra những nơi có lifetime dài hơn. Nhưng nếu `NativeBlock` được truyền giữa threads hay đăng ký callback mà không điều phối, wrapper Java không tự giải quyết được `WrongThreadException`/`IllegalStateException`.

Đừng viết API trả thẳng `ByteBuffer` hoặc `MemorySegment` từ một `try (Arena arena = ...)` rồi đóng arena trước khi caller dùng dữ liệu. `ByteBuffer` tạo từ `segment.asByteBuffer()` giữ ràng buộc lifetime/thread theo segment. Caller cầm được buffer không có nghĩa backing native memory còn hợp lệ.

Lựa chọn API rõ ràng hơn:

- Với dữ liệu nhỏ/không cần zero-copy, trả `byte[]`, `int[]`, `String` hoặc immutable record và copy ra khi arena vẫn còn alive.
- Với dữ liệu lớn và zero-copy, yêu cầu caller quản lý `AutoCloseable` owner hoặc callback nhận segment **chỉ trong phạm vi** lifetime.
- Với multi-thread, dùng shared arena nhưng vẫn có cơ chế reference counting/leases/task coordinator và một nơi chịu trách nhiệm close.
- Với plugin native, xác định rõ library handles, downcall handles, callbacks/upcall stubs có sống lâu hơn arena hay không.

`try-with-resources` chỉ kiểm soát **thời điểm Java owner gọi close**; muốn an toàn trên toàn hệ thống phải biết mọi alias/consumer sử dụng tài nguyên này.

## 12. Ngoại lệ dự kiến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` khi `get`/`set` | Scope đã đóng, segment hoặc slice/buffer vẫn bị sử dụng | Sửa lifetime; copy dữ liệu hoặc kéo dài arena ownership hợp lý |
| `WrongThreadException` khi `get` | Confined segment được truy cập từ thread không phải owner | Dùng trên owner thread, copy hoặc chuyển sang shared arena đúng cách |
| `WrongThreadException` khi `arena.close()` | Đóng confined arena từ thread khác owner | Owner thread đóng; không offload việc close sang bất kỳ executor nào |
| `IndexOutOfBoundsException` | Offset/length vượt `byteSize()` hoặc slice bounds | Tính theo **byte**, dự trù đủ kích thước layout và kiểm tra index |
| `IllegalArgumentException` về alignment | Địa chỉ+offset không đáp ứng layout alignment | Cấp phát/offset theo `byteAlignment()`, dùng layout phù hợp |
| `IllegalArgumentException` khi `set` | Segment/read-only view không cho ghi | Chỉ đọc hoặc làm việc với writable segment |
| `IllegalStateException` ở `Arena.close()` | Arena đã đóng, hoặc đang có thao tác segment concurrent theo contract | Quy định một owner đóng một lần; đợi operations kết thúc |
| `UnsupportedOperationException` ở `Arena.ofAuto().close()`/`Arena.global().close()` | Kiểu arena không cho close tường minh | Chọn confined/shared cho lifetime deterministic |
| `IllegalCallerException` ở `reinterpret`/restricted API | Module caller chưa có native access | Cấu hình `--enable-native-access` phù hợp, đồng thời đánh giá rủi ro |
| Crash native/segfault dù Java segment có bounds | Native code dùng invalid pointer, ABI sai, hoặc restricted reinterpret gán bounds/lifetime sai | Kiểm tra C ownership/ABI/symbols, tránh forged pointers, dùng sanitizer/logs |

**Không dùng một try/catch rộng bắt `RuntimeException` để bỏ qua lỗi FFM** rồi tiếp tục với cùng segment. Lỗi lifetime hoặc wrong-thread cho thấy cấu trúc ownership đang sai; phải sửa thiết kế thay vì liên tục thử lại bằng một pointer cũ.

### `scope().isAlive()` không phải debugger toàn năng

`isAlive() == true` chỉ cho biết trạng thái scope theo mô hình FFM **tại lúc được hỏi**. Nó không chứng minh:

- Địa chỉ native do thư viện C trả về còn backing allocation thực.
- Thread được quyền truy cập (còn cần confinement check).
- Offset và layout hợp lệ (còn bounds/alignment).
- Dữ liệu đã được đồng bộ giữa nhiều threads.
- Native code không giữ pointer sau khi Java close arena.
- Không có async callback sẽ truy cập sau thời điểm bạn đóng arena.

Để chẩn đoán, log **kiểu arena**, thread owner/caller, thời điểm allocate/close, byteSize, source của segment và phase của callback. Đừng log/trao đổi địa chỉ bộ nhớ native như một token có thể truy cập mãi.

## 13. Ranh giới an toàn của FFM: raw pointers, reinterpret và native functions

FFM kiểm tra rất tốt khi segment **được tạo đúng từ một arena hợp lệ** và mọi truy cập được thực hiện qua FFM API. Nhưng khi tương tác với thư viện C, FFM thường chỉ nhận **địa chỉ** chứ không nhận được toàn bộ metadata về allocation:

```c
/* C minh họa: hàm native có thể trả địa chỉ buffer.
 * Phần định nghĩa create_buffer/free_buffer và ownership
 * phải được tài liệu thư viện C nói rõ.
 */
void *create_buffer(size_t *size_out);
void free_buffer(void *buffer);
```

Một `MemorySegment` đại diện địa chỉ trần có thể chỉ có **byteSize 0** vì Java không biết vùng đó dài bao nhiêu. Nếu cố `get(JAVA_INT, 0)` trên zero-length segment thì FFM không có bằng chứng bounds hợp lệ và sẽ chặn bằng `IndexOutOfBoundsException`. Đây là chủ ý thiết kế.

Các phương thức restricted như `reinterpret(long newSize)` hoặc `reinterpret(long, Arena, Consumer)` cho phép **gán kích thước hoặc scope giả định** cho địa chỉ native. Chúng hữu ích khi C API cung cấp contract đáng tin về size và lifetime, nhưng nếu người lập trình khai báo sai:

- `newSize` lớn hơn vùng C thật → FFM có thể cho phép truy cập nằm trong **bounds đã khai báo** nhưng lại vượt backing allocation thật.
- Arena Java còn alive trong khi C đã `free` vùng bên dưới → có thể có **use-after-free** dù `scope().isAlive() == true`.
- Cleanup callback gọi `free` hai lần hoặc dùng allocator không khớp → memory corruption.
- Giữ raw address sau khi arena deallocated hoặc callback/upcall đã hết hiệu lực → native code có thể crash.
- `Arena.global()` không giải phóng tài nguyên còn không đồng nghĩa pointer của thư viện khác còn hợp lệ.

**Vì vậy:** FFM không loại bỏ yêu cầu hiểu **hợp đồng ownership của C**. Khi dùng pointer-returning functions, phải biết ai cấp phát, số byte, alignment, ai giải phóng, khi nào callback còn hợp lệ và native code có giữ con trỏ qua lời gọi hay không. Cách dùng restricted API đòi hỏi review kỹ hơn nhiều so với việc gọi `Arena.ofConfined().allocate(...)`.

### Downcall/upcall và lifetime

Với foreign function call, một `MemorySegment` có thể được chuyển thành pointer native argument; một downcall handle có thể giữ liên quan đến loaded library/lookup và lifetime của arena; một upcall stub cũng có scope/lifecycle và có thể bị native code giữ lại. Khi arena đóng, Java wrappers có thể bị invalidated, nhưng **native code bên ngoài không nhất thiết tuân thủ mọi kiểm tra Java FFM**.

Trong thiết kế:

1. Tài liệu hóa rõ native library nào sở hữu allocation, callback function pointer nào cần sống bao lâu.
2. Không cho native code lưu pointer đến buffer của arena ngắn hạn sau khi arena sẽ đóng, trừ khi có hợp đồng copy.
3. Quản lý scope của symbol lookup/upcall stub phù hợp với toàn bộ thời gian native có thể gọi tới.
4. Trước khi close, dừng tasks/callbacks và chờ các foreign calls còn dùng tài nguyên kết thúc theo contract.
5. Đừng tùy ý `reinterpret` để “sửa” một exception bounds/lifetime; sửa nguồn metadata và ownership.

## 14. Mẫu lựa chọn thiết kế cho ứng dụng

| Nhu cầu | Cách phù hợp | Điều vẫn phải bảo đảm |
| --- | --- | --- |
| Buffer native trong một hàm đồng bộ | `try (Arena a = Arena.ofConfined())` | Dùng đúng owner thread, không trả segment thoát scope |
| Nhiều worker đọc vùng native chung | `Arena.ofShared()` | Chờ tasks xong trước close; đồng bộ nếu có writes |
| Kết quả cần sống sau lời gọi | Copy sang Java heap hoặc trả owner `AutoCloseable` | Caller biết ai đóng và khi nào |
| Vùng native tạm thời lớn, GC-managed | `Arena.ofAuto()` | Không dựa vào thời điểm GC giải phóng |
| Dữ liệu thật sự sống toàn đời VM | `Arena.global()` có kiểm soát | Chấp nhận lifetime không giới hạn và áp lực native memory |
| Tạo view vào một phần buffer | `asSlice(...)` | Slice có bounds nhỏ hơn và kế thừa scope |
| Cung cấp view không cho ghi | `asReadOnly()` | Writable alias khác vẫn có thể thay dữ liệu; cùng lifecycle |
| Dùng Java array có sẵn | `MemorySegment.ofArray(...)` | Heap lifecycle, thread synchronization của Java |
| Nhận con trỏ C + length từ native library | Kiểm tra contract và restricted reinterpret nếu cần | Tính đúng backing size, ownership, ABI, lifetime; tránh crash |
| Chạy trên JDK 17 | Dùng API phù hợp JDK 17, hoặc nâng JDK để dùng code Java 22+ | Không copy nguyên code `java.lang.foreign` finalized vào JDK 17 |

Chọn arena theo **mô hình sở hữu thật** và đường thực thi, không theo mục tiêu “chỉ cần không bị WrongThreadException”. Chuyển mọi buffer sang shared/global chỉ để lỗi biến mất có thể khiến việc thu hồi bộ nhớ và dữ liệu dùng chung **khó kiểm soát hơn**.

## 15. Checklist review và kiểm thử

Trước khi đưa FFM vào production, duyệt lần lượt:

1. **Version:** build và runtime cùng chính sách API, sử dụng JDK 22+ cho `java.lang.foreign` finalized; các API restricted có native access policy phù hợp.
2. **Nguồn dữ liệu:** memory segment là heap/native/mapped/raw address? Ai sở hữu backing memory?
3. **Byte bounds:** `byteSize()` đúng số byte thực tế, không nhầm byte với element count và không vượt native allocation.
4. **Alignment:** `ValueLayout.byteAlignment()` tương ứng C ABI/struct field alignment và offset thực tế.
5. **Scope:** ai tạo arena, ai close, rời scope nào? Có biến/lambda/ByteBuffer/slice còn giữ segment không?
6. **Thread:** confined owner là thread nào; có worker, virtual thread, async callback hoặc executor chuyển việc không?
7. **Shared data:** các writers có bảo vệ bằng lock/atomic operation/memory ordering thích hợp không?
8. **Close:** coordinator đã chờ hết outstanding consumers, callbacks và foreign calls trước khi đóng shared arena chưa?
9. **Heap conversion:** nếu trả kết quả ra ngoài scope, đã copy dữ liệu cần thiết sang Java-owned representation chưa?
10. **Native contract:** pointer-returning function, `free`/allocator, restricted reinterpret và callbacks có size/lifetime thực sự đã xác minh chưa?
11. **Error paths:** mọi Java exception, task cancellation và thất bại native đều dẫn đến close/cleanup đúng một lần?
12. **Tests:** có kiểm thử off-by-one, read-only, misalignment, wrong-thread, access-after-close, concurrent lifecycle và version mismatch không?

### Bộ kiểm thử nhỏ cho ba cơ chế

| Trường hợp | Bố trí | Kết quả mong đợi |
| --- | --- | --- |
| Truy cập hợp lệ | Owner thread, scope alive, offset hợp lệ | Giá trị đã ghi được đọc đúng |
| Ngoài bounds | Segment 8 byte, đọc `JAVA_INT` tại offset 8 | `IndexOutOfBoundsException` |
| Sai alignment | Segment aligned 4, đọc `JAVA_INT` tại offset 1 | `IllegalArgumentException` |
| Sai thread | Worker đọc segment từ confined arena của main | `WrongThreadException` |
| Sau close | Main đóng arena, đọc segment/slice cũ | `IllegalStateException` |
| Read-only | `asReadOnly().set(...)` | `IllegalArgumentException` |
| Shared có điều phối | Worker xử lý, main `join`, sau đó close | Thành công |
| Shared thiếu điều phối | Close trong lúc tasks có thể còn chạy | Vi phạm thiết kế; không dựa vào một exception cụ thể để lập trình |
| Forge native pointer | Gán bounds/lifetime sai bằng restricted API | Có thể dẫn tới lỗi bộ nhớ native/JVM crash; không thử trên hệ thống production |

## 16. Câu hỏi tự kiểm tra

**1. Vì sao giữ `MemorySegment` trong một field `static` không đủ để truy cập sau `Arena.close()`?**

Bởi `MemorySegment` là Java object mô tả một **scope**. Khi arena đóng, scope mất hiệu lực và vùng native backing được giải phóng; reference tới Java object không gia hạn lifetime của vùng native. Truy cập qua FFM sau close thường bị chặn bằng `IllegalStateException`.

**2. Có thể dùng `synchronized(segment)` để thread B truy cập segment của `Arena.ofConfined()` không?**

**Không.** Lock không thay owner thread được gắn với confined arena. Thread B vẫn nhận `WrongThreadException` khi truy cập. Hãy copy dữ liệu, dùng arena được tạo trên B, hoặc dùng shared arena và synchronization phù hợp.

**3. Nếu dùng `Arena.ofShared()`, hai threads cùng tăng counter bằng `get` rồi `set` có tự động atomic không?**

**Không.** Shared chỉ cho phép truy cập từ nhiều threads; nó không bảo đảm một chuỗi read-modify-write không bị race. Sử dụng `VarHandle` atomic operations hoặc lock với memory ordering hợp lệ.

**4. Một đoạn Java tạo slice `asSlice(4,4)` từ segment gốc 16 byte. Slice có thể đọc offset 12 không?**

**Không.** Offset của slice tính từ **base của slice**, và slice chỉ dài 4 byte. Đọc `JAVA_INT` tại offset 12 vượt bounds, dù vùng gốc vẫn còn byte ở offset 16. Slice có spatial bounds riêng nhưng cùng lifetime scope.

**5. `isAlive()==true` có đảm bảo con trỏ C được bọc bằng `reinterpret` còn sống không?**

**Không.** Nó chỉ phản ánh scope Java được khai báo. Nếu native code đã giải phóng allocation trước đó, thông tin Java có thể không khớp với lifetime thật và vẫn có nguy cơ use-after-free.

**6. Khi nào nên dùng `Arena.ofAuto()` thay vì `ofConfined()`?**

Khi lifecycle do GC quản lý đáp ứng yêu cầu và không cần thời điểm close xác định. `ofAuto()` cho phép multi-thread access, nhưng `close` không được hỗ trợ; không phù hợp khi native memory phải được thu hồi ngay khi hoàn thành thao tác.

**7. Tại sao Java 17 không biên dịch được chương trình `FfmScopeSafetyDemo.java` ở bài này?**

Vì các API `java.lang.foreign` dạng finalized (JEP 454) chỉ có từ JDK 22. Java 17 có API foreign **incubator** khác package/module và shape; phải dùng đúng API của JDK đó hoặc nâng JDK.

**8. Bắt `IllegalStateException` rồi thử lại `segment.get(...)` sau khi arena đóng có nên không?**

Không. Một scope đã đóng không được hồi sinh bằng retry; phải cấp một segment mới trong một arena còn alive và chuyển/copy dữ liệu theo ownership contract phù hợp.

**9. `WrongThreadException` cho biết chương trình có data race không?**

Nó chủ yếu cho biết **vi phạm thread confinement** của segment/arena. Nó không phải một bộ phát hiện mọi data race. Shared arena có thể cho phép hai threads truy cập mà code vẫn sai do thiếu đồng bộ.

**10. Vì sao không dùng `Arena.global()` để né cả close và thread restrictions?**

Global arena có lifetime không giới hạn và không đóng tường minh, nên native allocations có thể không được giải phóng trong đời JVM. Nó cũng không sửa data races, native ABI, ownership của pointer bên ngoài hay lỗi của C/C++ code. Cần chọn lifetime đúng thay vì bỏ vòng đời để dễ truy cập.

## 17. Tài liệu chính thức

- Oracle Java SE 22 — [`java.lang.foreign` package: spatial và temporal safety](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- Oracle Java SE 22 — [`Arena`: confined/shared/automatic/global, `close()` và thread confinement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- Oracle Java SE 22 — [`MemorySegment`: scope, `isAccessibleBy`, `asSlice`, bounds và alignment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- Oracle Java SE 22 — [`MemorySegment.Scope` và `isAlive()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html).
- OpenJDK JEP 454 — [Foreign Function & Memory API, finalized ở JDK 22](https://openjdk.org/jeps/454).
- Oracle Java SE 25 — [Foreign Function and Memory API guide, memory segments và foreign functions](https://docs.oracle.com/en/java/javase/25/core/foreign-function-and-memory-api.html).

**Ghi nhớ:** FFM giúp ngăn **out-of-bounds**, **use-after-close**, **wrong-thread access** trên memory segment hợp lệ bằng các kiểm tra runtime tương ứng. `Arena` quyết định lifetime và confinement; `MemorySegment` giữ byte bounds và scope; ứng dụng chịu trách nhiệm quyết định khi nào được đóng, thread nào sở hữu và cách phối hợp các consumers. Với địa chỉ C tùy ý, restricted reinterpret, callbacks và data races, **an toàn vẫn phụ thuộc vào thiết kế ownership và hợp đồng native thực**.