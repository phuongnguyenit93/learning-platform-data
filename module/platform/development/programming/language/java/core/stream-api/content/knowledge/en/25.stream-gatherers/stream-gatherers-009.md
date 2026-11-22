# Xử lý thứ tự, nguồn vô hạn và dừng sớm khi dùng Gatherer

## 1. Bài toán: một phép biến đổi không chỉ nhận một phần tử và trả một phần tử

Trong module **JAVA_STREAM_API**, những pipeline dùng `filter`, `map`, `reduce` và `collect` đã giải quyết nhiều yêu cầu xử lý dữ liệu khai báo. Tuy nhiên, có các phép biến đổi phải **nhớ trạng thái**, **phát nhiều hoặc ít phần tử hơn số phần tử nhận vào**, hoặc **quyết định dừng xử lý nguồn ngay khi đủ điều kiện**:

- Gom các phép đo liên tiếp thành cửa sổ 3 phần tử.
- Tính tổng tích lũy sau mỗi giao dịch, thay vì chỉ trả tổng cuối.
- Tìm các sự kiện đến **và bao gồm** sự kiện đánh dấu kết thúc.
- Đọc luồng có thể vô hạn, chỉ lấy 5 kết quả đầu tiên mà không tiêu thụ hết nguồn.
- Ánh xạ đồng thời những phần tử tốn công xử lý, nhưng vẫn cần trả kết quả theo encounter order.

Từ **Java 24**, giao diện `Gatherer` và phương thức `Stream.gather(...)` là API chuẩn. Các phép biến đổi có sẵn trong `Gatherers` gồm `windowFixed`, `windowSliding`, `scan`, `fold` và `mapConcurrent`. Một custom gatherer còn có thể kiểm soát thời điểm yêu cầu **short-circuit**.

Trong bài thuộc chương **Stream Gatherer**, chúng ta tập trung vào **ba trục tính đúng**:

1. **Thứ tự**: phân biệt encounter order, thứ tự làm việc của các thread và thứ tự kết quả cuối.
2. **Nguồn vô hạn**: xác định phép biến đổi có sinh kết quả từng bước hay phải đợi nguồn kết thúc.
3. **Dừng sớm**: hiểu hai tín hiệu `Integrator.integrate(...)` trả `false` và `Downstream.push(...)` trả `false`; phối hợp với `limit`, `findFirst` và các terminal operation khác.

Sau bài học, người học có thể tự thiết kế custom gatherer tuần tự có trạng thái riêng, giải thích vì sao một pipeline có thể chạy mãi dù có `limit(1)`, kiểm thử kết quả mà không dựa vào timing/thread scheduling, và quản lý nguồn I/O đúng vòng đời.

### 1.1. Sơ đồ ba tầng

```text
Nguồn                            Gatherer                        Downstream
┌─────────────────┐             ┌────────────────────────┐      ┌─────────────────────┐
│ Stream<T>       │  input T    │ initializer()          │  R   │ filter/map/limit   │
│ ordered?        ├────────────►│ integrator()           ├─────►│ findFirst/toList   │
│ finite/infinite?│             │ state A                │      │                     │
│ resource-backed?│             │ combiner()/finisher()  │      │ chấp nhận thêm?     │
└─────────────────┘             └────────────────────────┘      └─────────────────────┘
                                           │                            │
                                           │  false: ngừng nhận input   │
                                           ◄────────────────────────────┘
                                               push() == false
```

Một gatherer có thể **không phát** kết quả cho một input, phát **một**, hoặc phát **nhiều**. Tính đúng phụ thuộc cả vào **điều kiện phát** và **điều kiện ngừng**.

## 2. Phiên bản JDK và cấu hình chạy ví dụ

| Phiên bản | Trạng thái của Stream Gatherers | Lưu ý |
| --- | --- | --- |
| Java 8–21 | Chưa có `Gatherer` trong API chuẩn | Dùng các phép Stream hiện có hoặc viết logic riêng |
| JDK 22 | Stream Gatherers ở **preview lần đầu** | Cần `--enable-preview`, API có thể đổi |
| JDK 23 | **Preview lần thứ hai** | Vẫn cần `--enable-preview` |
| **JDK 24 trở lên** | **API chính thức** | Không cần bật preview cho `Gatherer` |

Toàn bộ **mã hoàn chỉnh** và kiểm thử trong bài lấy **JDK 24+** làm phiên bản đích. Không sao chép nguyên mã Java 24 để biên dịch với `--release 22` hoặc `--release 23` rồi kỳ vọng tương thích 100% với preview API: hãy đọc đúng Javadoc của release đang sử dụng.

Ví dụ với máy dùng JDK 24:

```bash
javac --release 24 GathererOrderAndStopDemo.java
java GathererOrderAndStopDemo
```

Không thêm `--enable-preview` cho ví dụ JDK 24. Với một dự án buộc chạy trên JDK 17 hoặc JDK 21, cần phương án thay thế và không được viện dẫn một API mà runtime đích không có.

Tài liệu tham chiếu chính thức:

- [`Gatherer` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- [`Gatherer.Integrator` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html)
- [`Gatherer.Downstream` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [`Gatherers` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- [`Stream.gather` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer))

## 3. Hợp đồng cơ bản của `Gatherer<T,A,R>`

Một gatherer có ba kiểu:

- `T`: kiểu phần tử nguồn mà gatherer nhận.
- `A`: kiểu trạng thái tích lũy trung gian, có thể mutable.
- `R`: kiểu phần tử kết quả đẩy về downstream.

Các phần quan trọng:

| Thành phần | Chức năng | Điều cần kiểm tra |
| --- | --- | --- |
| `initializer()` | Tạo trạng thái `A` mới nếu cần | Không chia sẻ nhầm state giữa những lần chạy |
| `integrator()` | Nhận từng `T`, cập nhật `A`, gọi downstream để phát `R` | Xử lý đúng tín hiệu stop và thứ tự |
| `combiner()` | Gộp trạng thái khi có thể đánh giá song song | Chỉ cung cấp nếu chứng minh tính đúng khi phân hoạch/gộp |
| `finisher()` | Thực hiện bước kết thúc và có thể phát kết quả cuối | Có cần đợi EOF? Có biết downstream từ chối chưa? |
| `andThen(...)` | Ghép các gatherer | Tín hiệu dừng phải truyền hợp lệ qua chuỗi |

Chữ ký của integrator:

```java
@FunctionalInterface
interface Integrator<A, T, R> {
    boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream
    );
}
```

Ý nghĩa của giá trị trả về:

- `true`: gatherer **có thể tiếp tục nhận** các phần tử nguồn nếu pipeline còn nhu cầu.
- `false`: gatherer yêu cầu **ngừng cung cấp thêm input** cho nó; coi như không còn input để tích lũy.

Tín hiệu dừng này là **điều khiển pipeline**, không phải kết quả boolean của phần tử đang được lọc. Trả `false` không tự phát phần tử nào; muốn đưa phần tử cuối ra kết quả, phải gọi `downstream.push(element)` đúng thời điểm.

### 3.1. Không dùng state chung giữa hai pipeline

Sai về lifecycle:

```java
// Phản ví dụ: counter bị capture ngoài gatherer và chia sẻ giữa các lần dùng.
// AtomicInteger global = new AtomicInteger();
// Gatherer<Integer, ?, Integer> g = Gatherer.ofSequential(
//     (ignored, n, downstream) ->
//         global.incrementAndGet() <= 5 && downstream.push(n)
// );
```

Ngay cả khi `AtomicInteger` an toàn cho phép cộng đồng thời, state dùng chung làm các lần chạy stream **ảnh hưởng nhau**. Với gatherer stateful, đặt trạng thái vào `initializer()` để mỗi lần đánh giá có state riêng.

### 3.2. Không giữ state hoặc downstream để phát về sau

Theo hợp đồng `Gatherer`, không giữ, phát tán hoặc chia sẻ tham chiếu state hay `Downstream` ra ngoài phạm vi invocation đang xử lý. Đừng cất `downstream` vào trường static rồi dùng callback bất đồng bộ vài giây sau để `push`: đó không phải mô hình reactive stream, cũng không có hợp đồng an toàn cho thao tác ấy.

## 4. Encounter order: thứ tự nguồn khác thứ tự thực thi

**Encounter order** là thứ tự các phần tử được xác định bởi nguồn và các intermediate operation. Ví dụ `List`, mảng và `IntStream.range` có encounter order. Một số nguồn như `HashSet` không cam kết thứ tự, và `BaseStream.unordered()` có thể bỏ yêu cầu duy trì encounter order.

Ví dụ ordered:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> windows = List.of(1, 2, 3, 4, 5, 6, 7)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7]]
```

Các cửa sổ gồm **những phần tử liên tiếp theo encounter order**, không phải những giá trị được tự động sắp số tăng dần. Nếu nguồn là `List.of(7, 1, 5, 4)`, cửa sổ kích thước 2 sẽ là `[7,1]` và `[5,4]`.

### 4.1. `parallel()` không có nghĩa kết quả ordered bị đảo

`parallel()` chỉ biểu thị ý định đánh giá song song. Với pipeline có encounter order và các thao tác phải duy trì thứ tự, kết quả `toList()` vẫn phải theo encounter order. Nhưng **các lời gọi mapper ở nhiều worker có thể xảy ra theo thứ tự khác**.

```java
import java.util.stream.IntStream;

List<Integer> ordered = IntStream.range(1, 10)
    .boxed()
    .parallel()
    .gather(Gatherers.mapConcurrent(3, n -> n * 10))
    .toList();

System.out.println(ordered);
// [10, 20, 30, 40, 50, 60, 70, 80, 90]
```

`Gatherers.mapConcurrent` dùng **virtual threads**, giới hạn số tác vụ đồng thời theo `maxConcurrency` và **bảo toàn thứ tự kết quả của stream** theo Javadoc. Điều này không nói mapper thực thi theo thứ tự 1 → 9. Mỗi tác vụ có thể hoàn thành ở những thời điểm khác nhau. Nếu đầu vào đã unordered, không tự áp đặt một thứ tự mà nguồn không có.

### 4.2. `forEach` và `forEachOrdered`

```java
List<Integer> input = List.of(1, 2, 3, 4);

input.parallelStream()
    .gather(Gatherers.mapConcurrent(2, n -> n * 2))
    .forEach(System.out::println);
// Không cam kết thứ tự dòng in.

input.parallelStream()
    .gather(Gatherers.mapConcurrent(2, n -> n * 2))
    .forEachOrdered(System.out::println);
// 2, 4, 6, 8 theo encounter order.
```

`forEachOrdered` giữ thứ tự ở terminal stage nhưng có chi phí phối hợp. Đừng dùng thứ tự log hoặc tên thread để kiểm chứng thứ tự dữ liệu cuối cùng.

### 4.3. Khi gọi `unordered()`

```java
var result = IntStream.range(1, 7)
    .boxed()
    .unordered()
    .gather(Gatherers.windowFixed(2))
    .toList();
```

Pipeline trên **không nên được kiểm thử với giả định nhóm chính xác luôn là `[1,2]`, `[3,4]`, `[5,6]`** theo hợp đồng có thứ tự từ đầu nguồn. `unordered()` bỏ ràng buộc đó. Nếu nghiệp vụ yêu cầu “ba sự kiện liên tiếp”, giữ nguồn có encounter order và không tự ý gọi `unordered()` để tối ưu.

**Quy tắc:** nếu một phép biến đổi cần khái niệm **phần tử trước/sau**, phải định nghĩa “trước/sau” bằng một thứ tự dữ liệu đáng tin. Thời điểm thread hoàn tất không thay được encounter order.

## 5. `Gatherers.windowFixed`: gom cửa sổ cố định và thứ tự

`Gatherers.windowFixed(windowSize)` gom các phần tử liên tiếp thành các cửa sổ **không chồng lấn**:

```java
List<List<Integer>> result = List.of(10, 20, 30, 40, 50, 60, 70)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(result);
// [[10, 20, 30], [40, 50, 60], [70]]
```

Đặc điểm:

- `windowSize` phải **lớn hơn 0**, ngược lại ném `IllegalArgumentException`.
- Mỗi cửa sổ gồm các phần tử liên tiếp theo encounter order.
- Khi nguồn hữu hạn còn dư ít hơn `windowSize`, cửa sổ **cuối có thể nhỏ hơn kích thước yêu cầu**.
- Nguồn rỗng không tạo cửa sổ.
- Các `List` cửa sổ trả ra **không sửa đổi được**; không phụ thuộc implementation cụ thể hoặc serialization.
- Kích thước cửa sổ lớn có thể làm tốn bộ nhớ ngay cả khi luồng nguồn nhỏ.

### 5.1. Cửa sổ cố định trên nguồn vô hạn

```java
import java.util.stream.Stream;

List<List<Long>> firstTwo = Stream.iterate(1L, n -> n + 1L)
    .gather(Gatherers.windowFixed(3))
    .limit(2)
    .toList();

System.out.println(firstTwo);
// [[1, 2, 3], [4, 5, 6]]
```

Nguồn `Stream.iterate(1L, n -> n + 1L)` **không có điểm kết thúc tự nhiên**. Pipeline trên vẫn có thể hoàn thành vì:

1. Gatherer phát một cửa sổ sau khi đủ ba phần tử.
2. `limit(2)` cần hai cửa sổ rồi dừng nhận kết quả.
3. Tín hiệu dừng truyền qua pipeline, nên không cần đợi nguồn vô hạn kết thúc.

**Không khẳng định framework chỉ gọi đúng 6 lần hàm tạo nguồn trong mọi chế độ hoặc mọi implementation.** Pipeline có thể có buffering, lookahead hoặc công việc đã bắt đầu trước khi downstream dừng. Điều có thể kiểm chứng theo hợp đồng là **nội dung hai cửa sổ** và việc phép tính có đường kết thúc.

### 5.2. Nguồn không đủ một cửa sổ

```java
List<List<Integer>> partial = Stream.of(1, 2)
    .gather(Gatherers.windowFixed(5))
    .toList();

System.out.println(partial); // [[1, 2]]
```

Ở đây, `finisher`/giai đoạn hoàn tất của gatherer có thể phát cửa sổ cuối chưa đủ kích thước khi nguồn hữu hạn **đã kết thúc**. Với nguồn vô hạn không đạt kích thước cửa sổ và không có điểm kết thúc, không có cách tự nhiên để “kết thúc rồi phát cửa sổ dư”.

## 6. `Gatherers.windowSliding`: các cửa sổ chồng lấn

`windowSliding(size)` duy trì một cửa sổ trượt: phần tử đầu của cửa sổ cũ bị bỏ, phần tử mới được thêm vào.

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Các `List` cửa sổ **không sửa đổi được**. Với nguồn có ít phần tử hơn `size`, Javadoc quy định **một cửa sổ chứa toàn bộ phần tử** nếu nguồn không rỗng:

```java
System.out.println(Stream.of(5, 9)
    .gather(Gatherers.windowSliding(4))
    .toList());
// [[5, 9]]
```

Nguồn rỗng cho danh sách cửa sổ rỗng. `windowSize < 1` là không hợp lệ.

### 6.1. Nguồn vô hạn cần giới hạn kết quả

```java
List<List<Integer>> firstThree = Stream.iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(3)
    .toList();

System.out.println(firstThree);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Sau khi đã đủ dữ liệu cho cửa sổ đầu, gatherer có thể phát thêm cửa sổ mỗi khi nhận một phần tử tiếp theo. `limit(3)` phía sau tạo điều kiện dừng với một kết quả hữu hạn.

### 6.2. Kích thước cửa sổ quyết định độ trễ đầu ra

Với cửa sổ kích thước 1.000.000, phép `findFirst()` **không nhất thiết có kết quả ngay**, vì gatherer cần tích lũy đủ dữ liệu cho một cửa sổ hoàn chỉnh hoặc đợi nguồn hữu hạn kết thúc để phát phần cửa sổ cuối. Nếu nguồn vô hạn liên tục sinh dữ liệu thì cuối cùng có thể đủ, nhưng thời gian và bộ nhớ phụ thuộc tốc độ nguồn và kích thước cửa sổ.

**Không** xem `limit(1)` hoặc `findFirst()` là bảo đảm “đọc một phần tử nguồn rồi trả kết quả”. Chúng giới hạn **phần tử đầu ra**, không mặc nhiên giới hạn **số phần tử đầu vào gatherer phải nhận**.

## 7. `scan` và `fold`: hai cách tích lũy có hành vi kết thúc khác nhau

`Gatherers.scan(initial, scanner)` phát kết quả **sau mỗi input**. `Gatherers.fold(initial, folder)` chỉ phát **một kết quả tích lũy cuối** khi quá trình thu thập kết thúc bình thường.

### 7.1. `scan`: có đầu ra tăng dần

```java
List<Long> prefixSums = Stream.of(2L, 3L, 5L)
    .gather(Gatherers.scan(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .toList();

System.out.println(prefixSums); // [2, 5, 10]
```

Số `0L` chỉ là trạng thái khởi tạo; nó **không được phát như một phần tử kết quả riêng**. Sau input đầu tiên `2`, kết quả là `2`.

### 7.2. `scan` trên nguồn vô hạn

```java
List<Long> runningTotals = Stream.iterate(1L, n -> n + 1L)
    .gather(Gatherers.scan(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .limit(5)
    .toList();

System.out.println(runningTotals);
// [1, 3, 6, 10, 15]
```

Mỗi input sinh được một prefix sum. `limit(5)` phía sau có thể lấy năm kết quả mà không cần chờ EOF của nguồn vô hạn.

### 7.3. `fold`: đợi kết thúc nguồn

```java
List<Long> oneTotal = Stream.of(2L, 3L, 5L)
    .gather(Gatherers.fold(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .toList();

System.out.println(oneTotal); // [10]
```

Với nguồn vô hạn, đoạn sau **không có đường kết thúc tự nhiên**:

```java
// KHÔNG CHẠY trong demo hoặc unit test:
// Stream.iterate(1L, n -> n + 1L)
//     .gather(Gatherers.fold(() -> 0L, Long::sum))
//     .limit(1)
//     .toList();
```

`limit(1)` yêu cầu một **kết quả của fold**, nhưng fold thường không phát kết quả cho tới khi đã tiêu thụ hết input. Nguồn vô hạn không tự kết thúc, nên fold không có kết quả để downstream nhận. Đây là ví dụ điển hình rằng **short-circuit phía sau không bảo đảm hoàn tất nếu giai đoạn trước không phát phần tử**.

Nếu yêu cầu là “tổng của 100 số đầu”, đặt `limit` **trước `fold`**:

```java
List<Long> first100Total = Stream.iterate(1L, n -> n + 1L)
    .limit(100)
    .gather(Gatherers.fold(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .toList();

System.out.println(first100Total); // [5050]
```

**Đặt `limit` ở đâu là lựa chọn ngữ nghĩa**, không chỉ tối ưu:

```text
Nguồn vô hạn → limit(100) → fold → một tổng cuối       (có đường kết thúc)
Nguồn vô hạn → fold → limit(1)   → đợi tổng cuối mãi   (không có EOF)
Nguồn vô hạn → scan → limit(100) → 100 tổng tích lũy   (có đường kết thúc)
```

## 8. Hai tín hiệu dừng phải được hiểu riêng

### 8.1. `Integrator.integrate` trả `false`

Một custom gatherer có thể quyết định “đã gặp mốc dừng, không nhận thêm phần tử nguồn”. Đây là **short-circuit chủ động từ gatherer**.

Ví dụ yêu cầu lấy giá trị đến **và bao gồm** số đầu tiên lớn hơn hoặc bằng 5:

```java
// [1, 2, 3, 4, 5], sau đó yêu cầu dừng nguồn.
Stream.iterate(1, n -> n + 1)
    .gather(takeUntilInclusive(n -> n >= 5))
    .toList();
```

Hàm `takeUntilInclusive` sẽ được cài đặt đầy đủ ở mục 11.

### 8.2. `Downstream.push(value)` trả `false`

`downstream.push(value)` chuyển giá trị sang giai đoạn tiếp theo và trả:

- `true` khi downstream còn có khả năng nhận thêm.
- `false` khi downstream **không nhận thêm phần tử nữa**. Những lần `push` tiếp theo trên cùng downstream cũng sẽ trả `false`.

Một integrator muốn hỗ trợ dừng sớm cần **quan sát và truyền lại** tín hiệu đó, ví dụ:

```java
boolean wantsMore = downstream.push(element);
return wantsMore;
```

Nếu downstream đã nhận đủ một kết quả do `findFirst` hoặc đủ `N` phần tử do `limit(N)`, việc tiếp tục gọi `push` là làm việc thừa, và có thể khiến logic trở nên khó lý giải.

### 8.3. `Downstream.isRejecting()` là tín hiệu hỗ trợ, không phải dự đoán tuyệt đối

`downstream.isRejecting()` trả `true` nếu downstream **đã biết** là không muốn nhận thêm; đây là kiểm tra **best effort**. Trả `false` **không bảo đảm** lần `push` kế tiếp chắc chắn được chấp nhận.

Do đó:

- Khi chuẩn bị làm một thao tác tạo đầu ra tốn kém, có thể kiểm tra `isRejecting()`.
- Vẫn phải kiểm tra **giá trị trả về từ `push`** khi thực sự phát dữ liệu.
- Không dùng `isRejecting()` như một cơ chế pause/resume hay backpressure bất đồng bộ.

### 8.4. Sơ đồ điều khiển dừng

```text
                  integrator(state, input, downstream)
                                │
                     Có phần tử cần phát?
                         /             \
                        Không          Có
                         │              │
             Cần ngừng input?      downstream.push(output)
                   /     \              │
                 Có     Không      true / false
                 │        │          │     │
              return    return   có thể   ngừng phát,
              false     true     nhận tiếp trả false
```

Tín hiệu `integrator == false` còn có thể xuất hiện **mà không phát output**, ví dụ khi phát hiện một điều kiện lỗi hoặc một marker phải dừng trước khi đưa vào kết quả.

## 9. `Integrator.ofGreedy` không dùng để chủ động short-circuit

`Gatherer.Integrator.Greedy` biểu thị integrator **không tự khởi xướng dừng nguồn**; nó chỉ phản ánh việc downstream không muốn nhận thêm. Vì thế JDK có thể tối ưu mà không cần kiểm tra giá trị boolean của integrator greedy trong một số tình huống.

Ví dụ dùng đúng:

```java
Gatherer<Integer, ?, Integer> doubleValues =
    Gatherer.ofSequential(
        Gatherer.Integrator.ofGreedy(
            (ignored, n, downstream) -> downstream.push(n * 2)
        )
    );

List<Integer> result = Stream.of(1, 2, 3)
    .gather(doubleValues)
    .toList();
// [2, 4, 6]
```

Vì integrator chỉ biến đổi phần tử và truyền `push`, nó không cần tự đặt mốc dừng. Nhưng nếu muốn **gặp số 5 thì ngừng nhận input kể cả downstream vẫn sẵn sàng**, phải dùng **Integrator thường** (`ofSequential` với lambda thông thường hoặc `Integrator.of(...)`), **không dùng `ofGreedy`** để trả `false` cho điều kiện riêng.

**Sai về hợp đồng:**

```java
// Phản ví dụ: greedy nhưng chủ động trả false khi n == 5.
// Gatherer.Integrator.ofGreedy(
//     (state, n, downstream) -> n != 5 && downstream.push(n)
// )
```

Trong implementation cho phép tối ưu bỏ việc kiểm tra boolean của greedy, quy tắc dừng của đoạn phản ví dụ có thể không được thực thi như mong muốn.

## 10. Dừng sớm từ downstream không đồng nghĩa đúng một lần gọi upstream

Với một pipeline:

```java
var first = Stream.iterate(0, n -> n + 1)
    .gather(Gatherers.scan(
        () -> 0L,
        (sum, next) -> sum + next
    ))
    .findFirst();
```

Kết quả có thể nhận được từ lần đầu gatherer phát giá trị, nhưng **không nên viết đặc tả bắt buộc mapper, supplier, finisher hoặc upstream phải được gọi đúng một lần**. Stream API có quyền sử dụng buffering, speculative work hoặc tối ưu hóa, nhất là khi xử lý song song.

### 10.1. Không đặt side effect nghiệp vụ trong mapper với mong muốn “chỉ chạy N lần”

```java
// Không làm:
// Stream.generate(() -> paymentApi.chargeCard())
//     .gather(Gatherers.mapConcurrent(8, this::validate))
//     .limit(1)
//     .findFirst();
```

Khi gatherer hoặc upstream có concurrency, nhiều tác vụ có thể đã được khởi động trước khi downstream quyết định dừng. `Gatherers.mapConcurrent` chỉ **cố gắng hủy** công việc chưa hoàn thành theo cơ chế best effort; nó không bảo đảm mọi side effect bên ngoài chưa xảy ra sẽ được thu hồi.

Nếu là thanh toán, ghi cơ sở dữ liệu hoặc gửi thông báo, hãy tách thao tác không thể đảo ngược khỏi một pipeline có speculative work, hoặc thiết kế **idempotency**, transaction và chính sách retry/cancellation ở tầng ứng dụng.

### 10.2. Các loại “đã dừng” khác nhau

| Cơ chế | Ai phát tín hiệu? | Tác động |
| --- | --- | --- |
| `integrate(...) == false` | Gatherer | Ngừng nhận input theo hợp đồng gatherer |
| `downstream.push(...) == false` | Downstream | Không muốn nhận thêm output |
| `limit(N)` | Intermediate stage phía sau | Chỉ cần tối đa `N` phần tử đầu ra |
| `findFirst` | Terminal operation | Chỉ cần phần tử đầu tiên theo encounter order |
| `anyMatch` / `noneMatch` | Terminal operation | Dừng khi đủ điều kiện xác định kết quả |
| `takeWhile` | Intermediate stage | Ngừng khi predicate không còn đúng trên ordered stream |
| `Stream.close()` | Owner/caller | Giải phóng tài nguyên, **không phải** một phép tính terminal thay `collect` |

**Ghi nhớ:** ngừng tính toán, ngừng phát dữ liệu và đóng tài nguyên là ba trách nhiệm khác nhau.

## 11. Custom Gatherer: lấy đến và bao gồm phần tử đánh dấu

`Stream.takeWhile(predicate)` (Java 9+) lấy phần tử **trong khi điều kiện còn đúng** và **không phát phần tử đầu tiên khiến predicate sai** trên ordered stream. Trong khi đó, một số bài toán yêu cầu **giữ lại marker kết thúc**:

```text
Input:  [10, 20, 30, -1, 40, 50, ...]
Mục tiêu: [10, 20, 30, -1]
                            ^
                      giữ phần tử đánh dấu
```

Đây là một trường hợp Gatherer phù hợp hơn `takeWhile(n -> n != -1)`, bởi `takeWhile` sẽ chỉ trả `[10,20,30]`.

### 11.1. Ý tưởng thuật toán

Với từng phần tử:

1. Gọi `downstream.push(element)` **trước** để phần tử hiện tại (kể cả marker) được phát.
2. Kiểm tra predicate có phải phần tử dừng hay không.
3. Trả `false` nếu downstream từ chối **hoặc** predicate báo đã tới mốc dừng.
4. Trả `true` trong các trường hợp còn lại.

Vì gatherer cần chủ động dừng trên predicate, **không dùng `Integrator.ofGreedy`**.

```java
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, T> takeUntilInclusive(
    Predicate<? super T> stopWhen
) {
    Objects.requireNonNull(stopWhen, "stopWhen");
    return Gatherer.<T, T>ofSequential(
        (unusedState, element, downstream) -> {
            boolean wantsMore = downstream.push(element);
            return wantsMore && !stopWhen.test(element);
        }
    );
}
```

Ở đây, overload `ofSequential(Integrator<Void,T,R>)` không cần state vì điều kiện dừng chỉ phụ thuộc **phần tử hiện tại** và predicate. `Void` là kiểu state mặc định của overload này; `unusedState` không được sử dụng.

### 11.2. Nguồn hữu hạn và nguồn vô hạn

```java
List<Integer> finite = Stream.of(10, 20, 30, -1, 40)
    .gather(takeUntilInclusive(n -> n == -1))
    .toList();

System.out.println(finite); // [10, 20, 30, -1]

List<Integer> infinite = Stream.iterate(1, n -> n + 1)
    .gather(takeUntilInclusive(n -> n >= 5))
    .toList();

System.out.println(infinite); // [1, 2, 3, 4, 5]
```

Ví dụ thứ hai **không đặt `limit` phía sau**. Nó vẫn có đường kết thúc vì chính Gatherer sẽ trả `false` sau khi đẩy phần tử 5. Đây là **short-circuit chủ động** từ integrator, khác với downstream `limit(5)`.

### 11.3. Mốc dừng không bao giờ xuất hiện?

Nếu nguồn hữu hạn không có marker, Gatherer trên phát toàn bộ dữ liệu rồi kết thúc khi nguồn hết. Nếu nguồn vô hạn không bao giờ thỏa `stopWhen` và downstream cũng không dừng, pipeline **không hoàn tất**:

```java
// KHÔNG CHẠY: nguồn vô hạn luôn phát 1L, predicate luôn sai.
// Stream.iterate(1L, n -> n)
//     .gather(takeUntilInclusive(n -> n < 0L))
//     .toList();
```

Trong hệ thống thật, nên có **một giới hạn phòng vệ** (số phần tử, deadline, giới hạn tài nguyên) nếu marker có thể thiếu. Nhưng chỉ thêm `limit` mà không xác định dữ liệu bị cắt ở đâu sẽ biến báo cáo đầy đủ thành báo cáo một phần; phải nêu rõ hợp đồng.

### 11.4. Cẩn thận nếu predicate có side effect

Ví dụ dùng `downstream.push(element)` rồi mới tính `stopWhen.test(element)`. Nếu downstream đã từ chối phần tử tiếp, biểu thức `&&` không gọi predicate nữa. Do đó **không đưa hành động bắt buộc** vào predicate (ghi hóa đơn, tăng audit counter, gọi API bên ngoài). Predicate nên thuần và non-interfering.

## 12. Custom Gatherer có state: lấy tối đa N phần tử

`Stream.limit(N)` đã giải quyết bài toán này trong hầu hết tình huống. Ta cài một Gatherer tương đương cho **N > 0** để hiểu cách quản lý **state riêng cho mỗi lần chạy** và phối hợp hai loại tín hiệu dừng.

```java
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, T> firstN(int max) {
    if (max <= 0) {
        throw new IllegalArgumentException("max phải lớn hơn 0");
    }

    class Counter {
        int emitted;
    }

    return Gatherer.<T, Counter, T>ofSequential(
        Counter::new,
        (state, element, downstream) -> {
            if (state.emitted >= max) {
                return false;
            }

            state.emitted++;
            boolean wantsMore = downstream.push(element);
            return wantsMore && state.emitted < max;
        }
    );
}
```

**Phân tích:**

- `Counter::new` tạo state mới; không có một biến đếm dùng chung ở bên ngoài.
- Mỗi element được phát một lần; biến `emitted` tăng trước khi đánh giá giới hạn.
- Khi đạt `max`, integrator trả `false` **ngay sau khi phát phần tử thứ N**, không chờ nhận thêm input rồi mới phát hiện.
- Khi downstream đã trả `false`, integrator cũng trả `false` dù chưa đạt `max`.
- Với `max == 0`, ví dụ cố ý từ chối đầu vào để tránh giả vờ không đọc phần tử nào; dùng **`Stream.limit(0)`** nếu mục tiêu là kết quả rỗng ngay tại nguồn.

Sử dụng:

```java
List<Integer> firstFour = Stream.iterate(1, n -> n + 1)
    .gather(firstN(4))
    .toList();

System.out.println(firstFour); // [1, 2, 3, 4]
```

### 12.1. Vì sao `ofSequential` phù hợp hơn một combiner tự tạo?

`firstN` phụ thuộc **thứ tự các phần tử** và số đã phát trong phần tiền tố. Nếu chia nguồn thành hai nửa, không thể chỉ lấy counter của mỗi nửa rồi cộng mà vẫn bảo đảm “đúng N phần tử đầu tiên” và dừng ở vị trí mong muốn.

`Gatherer.ofSequential` cung cấp **default combiner yêu cầu gatherer đánh giá tuần tự**. Nó tránh việc ta viết một combiner giả đúng trên dữ liệu nhỏ nhưng sai khi chạy song song.

### 12.2. Mã chạy song song vẫn phải đúng kết quả

```java
List<Integer> result = java.util.stream.IntStream.rangeClosed(1, 10)
    .boxed()
    .parallel()
    .gather(firstN(4))
    .toList();
// Kết quả cần tuân semantics firstN trên ordered source.
```

Không suy ra từ lời gọi `parallel()` rằng tích lũy có state phải chạy trên nhiều nhánh đồng thời. Gatherer không có combiner phù hợp chỉ được đánh giá **tuần tự ở chính giai đoạn gather**. Các phần khác của pipeline có thể có chiến lược thực thi riêng; không viết test về số thread hoặc thời điểm đánh giá.

## 13. Chương trình Java 24 đầy đủ: ba cách dừng và hai loại nguồn

Chương trình sau độc lập với các đoạn mã rời phía trên. Lưu trong file `GathererOrderAndStopDemo.java` và chạy trên **JDK 24+**.

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public final class GathererOrderAndStopDemo {

    private GathererOrderAndStopDemo() {}

    public static <T> Gatherer<T, ?, T> takeUntilInclusive(
        Predicate<? super T> stopWhen
    ) {
        Objects.requireNonNull(stopWhen, "stopWhen");
        return Gatherer.<T, T>ofSequential(
            (state, element, downstream) -> {
                boolean wantsMore = downstream.push(element);
                return wantsMore && !stopWhen.test(element);
            }
        );
    }

    public static <T> Gatherer<T, ?, T> firstN(int max) {
        if (max <= 0) {
            throw new IllegalArgumentException(
                "max phải lớn hơn 0"
            );
        }

        class Counter {
            int emitted;
        }

        return Gatherer.<T, Counter, T>ofSequential(
            Counter::new,
            (state, element, downstream) -> {
                if (state.emitted >= max) {
                    return false;
                }

                state.emitted++;
                boolean wantsMore = downstream.push(element);
                return wantsMore && state.emitted < max;
            }
        );
    }

    public static List<List<Integer>> firstTwoFixedWindows() {
        return Stream.iterate(1, n -> n + 1)
            .gather(Gatherers.windowFixed(3))
            .limit(2)
            .toList();
    }

    public static List<List<Integer>> firstTwoSlidingWindows() {
        return Stream.iterate(1, n -> n + 1)
            .gather(Gatherers.windowSliding(3))
            .limit(2)
            .toList();
    }

    public static List<Long> firstFiveRunningTotals() {
        return Stream.iterate(1L, n -> n + 1L)
            .gather(Gatherers.scan(
                () -> 0L,
                (sum, next) -> Math.addExact(sum, next)
            ))
            .limit(5)
            .toList();
    }

    public static List<Long> foldFirstFive() {
        return Stream.iterate(1L, n -> n + 1L)
            .limit(5) // Quan trọng: giới hạn INPUT trước fold.
            .gather(Gatherers.fold(
                () -> 0L,
                (sum, next) -> Math.addExact(sum, next)
            ))
            .toList();
    }

    public static List<Integer> untilFiveInclusive() {
        return Stream.iterate(1, n -> n + 1)
            .gather(takeUntilInclusive(n -> n >= 5))
            .toList();
    }

    public static List<Integer> firstThree() {
        return Stream.iterate(1, n -> n + 1)
            .gather(firstN(3))
            .toList();
    }

    public static List<Integer> concurrentOrdered() {
        return Stream.of(5, 1, 4, 2, 3)
            .gather(Gatherers.mapConcurrent(3, n -> n * 10))
            .toList();
    }

    public static void main(String[] args) {
        System.out.println(firstTwoFixedWindows());
        // [[1, 2, 3], [4, 5, 6]]

        System.out.println(firstTwoSlidingWindows());
        // [[1, 2, 3], [2, 3, 4]]

        System.out.println(firstFiveRunningTotals());
        // [1, 3, 6, 10, 15]

        System.out.println(foldFirstFive());
        // [15]

        System.out.println(untilFiveInclusive());
        // [1, 2, 3, 4, 5]

        System.out.println(firstThree());
        // [1, 2, 3]

        System.out.println(concurrentOrdered());
        // [50, 10, 40, 20, 30]
    }
}
```

Điểm nổi bật: chương trình có **nguồn vô hạn** nhưng **không có phép terminal đợi nguồn vô hạn tự kết thúc**. Mỗi pipeline hoặc sử dụng gatherer phát tăng dần kết hợp `limit`, hoặc tự trả `false` để dừng nguồn, hoặc cắt nguồn thành hữu hạn **trước `fold`**.

### 13.1. Cách biên dịch

```bash
javac --release 24 GathererOrderAndStopDemo.java
java GathererOrderAndStopDemo
```

Các lệnh này yêu cầu trình biên dịch hỗ trợ `--release 24`; không dùng `--release 17` vì Java 17 chưa có `Stream.gather`. Với Java 24, Gatherers đã là API chính thức.

### 13.2. Tại sao ví dụ dùng `Stream.iterate` thay vì `Stream.generate`?

`Stream.iterate(seed, next)` có encounter order, hữu ích khi bài toán kiểm chứng “những giá trị đầu tiên” hoặc các cửa sổ liên tiếp. `Stream.generate(supplier)` được đặc tả như một nguồn **unordered**, mặc dù khi chạy tuần tự supplier vẫn được gọi để sinh giá trị. Nếu cần kết quả mang nghĩa vị trí theo thứ tự, dùng nguồn và thao tác có encounter order rõ ràng.

## 14. Một custom Gatherer cần `finisher`: xử lý phần cửa sổ cuối

`Gatherers.windowFixed` đã có hành vi cửa sổ cuối ngắn hơn kích thước yêu cầu. Nhưng để hiểu rõ vai trò `finisher`, ta có thể tự xây một gatherer gom theo lô.

**Yêu cầu:**

- Phát một `List<T>` mỗi khi gom đủ `size` phần tử.
- Khi input hữu hạn kết thúc mà còn phần dư, phát **một lô cuối**.
- Không phát tiếp nếu downstream đã từ chối.
- Không giữ tham chiếu mutable của buffer trong kết quả.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, List<T>> batches(int size) {
    if (size < 1) {
        throw new IllegalArgumentException(
            "size phải lớn hơn 0"
        );
    }

    class State {
        final ArrayList<T> pending = new ArrayList<>(size);
    }

    return Gatherer.<T, State, List<T>>ofSequential(
        State::new,
        (state, element, downstream) -> {
            Objects.requireNonNull(element, "element");
            state.pending.add(element);

            if (state.pending.size() == size) {
                List<T> batch = List.copyOf(state.pending);
                state.pending.clear();
                return downstream.push(batch);
            }

            return !downstream.isRejecting();
        },
        (state, downstream) -> {
            if (!state.pending.isEmpty() &&
                    !downstream.isRejecting()) {
                downstream.push(List.copyOf(state.pending));
            }
        }
    );
}
```

**Chính sách dữ liệu:** ví dụ chủ động từ chối phần tử `null` bằng `Objects.requireNonNull`; `List.copyOf` cũng không nhận null. Nếu nguồn có null hợp lệ, cần thiết kế cách biểu diễn khác thay vì giả vờ không có null.

### 14.1. Thử trên nguồn hữu hạn

```java
System.out.println(Stream.of("A", "B", "C", "D", "E")
    .gather(batches(2))
    .toList());
// [[A, B], [C, D], [E]]

System.out.println(Stream.<String>empty()
    .gather(batches(2))
    .toList());
// []
```

Với lô cuối `[E]`, giai đoạn hoàn tất sau EOF phát phần còn lại; không cần gọi `push` trên mỗi input.

### 14.2. Cẩn thận trên nguồn vô hạn

Nguồn vô hạn **không có EOF** để kích hoạt ý nghĩa “phát lô dư sau cùng”, nhưng gatherer có thể phát **những lô đầy đủ** liên tục:

```java
List<List<Integer>> firstTwo = Stream.iterate(1, n -> n + 1)
    .gather(batches(2))
    .limit(2)
    .toList();

System.out.println(firstTwo);
// [[1, 2], [3, 4]]
```

Nếu size rất lớn và downstream cần chỉ một lô, gatherer vẫn phải gom đủ `size` input trước khi phát. Nếu nguồn có tốc độ đầu vào thấp, `findFirst` không làm xuất hiện lô sớm hơn yêu cầu tích lũy.

### 14.3. Tại sao phải sao chép buffer khi phát?

Nếu gọi `downstream.push(state.pending)` rồi `state.pending.clear()`, những danh sách đã được phát sẽ **bị xóa dữ liệu** vì cùng tham chiếu mutable. `List.copyOf(state.pending)` tạo snapshot cấu trúc không sửa đổi được cho từng lô.

Với phần tử object mutable, các object bên trong list vẫn có thể đổi; `List.copyOf` không phải deep copy. Với pipeline song song, implementation `ofSequential` giữ logic stateful theo thứ tự mà không cần một combiner không chính xác.

## 15. `andThen` và nhiều Gatherer trong một pipeline

`Gatherer.andThen(other)` tạo một gatherer tổng hợp: kết quả `R` của gatherer đầu trở thành input của gatherer tiếp. Một cách viết khác là gọi nhiều lần `Stream.gather(...)`.

Ví dụ: chia cửa sổ cố định rồi tiếp tục scan theo **kích thước cửa sổ**:

```java
List<Integer> runningCounts = Stream.of(1, 2, 3, 4, 5, 6, 7)
    .gather(Gatherers.windowFixed(3))
    .map(List::size)
    .gather(Gatherers.scan(
        () -> 0,
        Integer::sum
    ))
    .toList();

System.out.println(runningCounts); // [3, 6, 7]
```

Trong pipeline này:

1. `windowFixed(3)` phát `[1,2,3]`, `[4,5,6]`, `[7]`.
2. `map(List::size)` phát `3`, `3`, `1`.
3. `scan` cộng tích lũy thành `3`, `6`, `7`.

Đừng nhầm `limit(2)` trước và sau `windowFixed`:

```java
// Giới hạn số input: 2 phần tử -> một cửa sổ ngắn.
Stream.of(1, 2, 3, 4, 5)
    .limit(2)
    .gather(Gatherers.windowFixed(3))
    .toList(); // [[1, 2]]

// Giới hạn số OUTPUT: 2 cửa sổ -> có thể chứa tới 6 input.
Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .limit(2)
    .toList(); // [[1, 2, 3], [4, 5]]
```

JDK được phép tối ưu một chuỗi gatherer, nhưng **không** được làm thay đổi ngữ nghĩa được cam kết. Không viết chương trình phụ thuộc một giai đoạn gatherer nhất định chắc chắn được thực thi trên một thread/được gọi đúng một lần nếu API không hứa điều đó.

## 16. Song song, combiner và giới hạn của cách chia nguồn

### 16.1. Không có combiner thì gatherer stateful thường tuần tự

Với một gatherer có trạng thái phụ thuộc tiền tố, ví dụ `scan` hay `takeUntilInclusive`, việc chia input thành nhiều vùng và gộp state ở cuối **không đơn giản**. `ofSequential` cung cấp một lựa chọn an toàn: gatherer **được đánh giá tuần tự**, ngay cả khi stream phía ngoài bật parallel.

Không suy ra `ofSequential` biến **toàn bộ pipeline** thành một thread đơn duy nhất ở mọi giai đoạn. Điều quan trọng là gatherer không bị framework chia state tùy tiện rồi gọi một combiner không tồn tại.

### 16.2. Nếu tự cung cấp combiner, phải chứng minh tính kết hợp

Với `Gatherer.of(initializer, integrator, combiner, finisher)`, framework có thể:

1. Chia nguồn thành các phân vùng.
2. Tạo một state độc lập cho mỗi vùng.
3. Tích lũy từng vùng.
4. Gộp kết quả qua combiner phù hợp.
5. Thực hiện finisher.

Nếu phép tính có quy tắc **“đến marker đầu tiên theo encounter order thì dừng”**, chỉ cộng bộ đếm giữa các vùng không đủ. Combiner phải hiểu **vị trí marker**, phần input đã thuộc tiền tố nào và dữ liệu nào cần bỏ; điều đó khó hơn một phép cộng đơn giản.

**Phản mẫu:**

```java
// Ý tưởng sai:
// State có ArrayList<T> đã thấy và flag stopped.
// combiner = (left, right) -> {
//     left.seen.addAll(right.seen);
//     return left;
// };
// Không xử lý flag stopped, thứ tự tiền tố và vị trí marker.
```

Kết quả có thể đúng trên nguồn nhỏ hoặc khi không chia, rồi sai ở parallel stream. Nếu không chứng minh được associativity và tính đúng theo encounter order, **đừng tự thêm combiner chỉ để “bật song song”**.

### 16.3. `mapConcurrent` khác parallel stream thông thường

`Gatherers.mapConcurrent(maxConcurrency, mapper)` dùng **virtual threads** để thực hiện mapper đồng thời, có giới hạn. API giữ thứ tự kết quả. Đối với mapper làm I/O blocking hoặc việc độc lập có thể được thực thi đồng thời, nó là một lựa chọn đáng thử.

```java
List<String> values = Stream.of("a", "bb", "ccc", "dddd")
    .gather(Gatherers.mapConcurrent(
        2,
        String::toUpperCase
    ))
    .toList();

System.out.println(values); // [A, BB, CCC, DDDD]
```

`maxConcurrency` phải lớn hơn hoặc bằng 1. **Không** kết luận có đúng `maxConcurrency` tác vụ chạy ở mọi thời điểm, hoặc tối ưu này nhất định nhanh hơn `map`; chi phí điều phối, đặc tính nguồn, khóa nóng ở downstream và độ trễ I/O đều ảnh hưởng.

### 16.4. Hủy tác vụ là best effort

Khi downstream không muốn nhận thêm, `mapConcurrent` **cố gắng hủy** tác vụ đang thực hiện, nhưng không thể bảo đảm mọi mapper đã bắt đầu sẽ dừng ngay hoặc không còn side effect. Bởi vậy, không dùng nó như một cơ chế giao dịch rollback.

## 17. Nguồn vô hạn: bảng đánh giá khả năng hoàn tất

| Pipeline trên nguồn vô hạn | Có đường hoàn tất? | Vì sao |
| --- | --- | --- |
| `scan(...).limit(5).toList()` | Có | `scan` phát từng bước, `limit` chặn output |
| `windowFixed(3).limit(2).toList()` | Có | Phát một kết quả mỗi ba input, sau đó đủ hai output |
| `windowSliding(3).limit(2).toList()` | Có | Phát cửa sổ trượt khi đủ dữ liệu |
| `takeUntilInclusive(n >= 5).toList()` | Có với nguồn tăng từ 1 | Integrator tự trả `false` tại marker |
| `firstN(5).toList()` | Có | Integrator tự dừng sau N output |
| `limit(5).fold(...).toList()` | Có | Nguồn đã hữu hạn **trước** fold |
| `fold(...).limit(1).toList()` | Không có đường hoàn tất tự nhiên | Fold chờ EOF để phát |
| `filter(n -> false).limit(1).toList()` | Không có đường hoàn tất tự nhiên | Không phần tử nào vượt qua filter |
| `takeUntilInclusive(n < 0).toList()` với input dương mãi | Không | Predicate dừng không bao giờ đúng |
| `windowFixed(1_000_000).findFirst()` | Có nếu nguồn tiếp tục đủ input | Cần đủ dữ liệu cho cửa sổ; có thể rất chậm/tốn bộ nhớ |

### 17.1. Bốn câu hỏi kiểm tra liveness

Trước khi đặt một gatherer sau `Stream.iterate` hoặc `Stream.generate`, hãy tự hỏi:

1. Gatherer có **phát đầu ra trước EOF** không?
2. Downstream có **điều kiện dừng** như `limit` hoặc `findFirst` không?
3. Gatherer có **tự ngừng nguồn** qua `integrate == false` không?
4. Nếu không có đầu ra trong thời gian dài, chương trình cần deadline, cancellation hoặc giới hạn dữ liệu nào?

Nếu câu 1, 2, 3 đều không tạo ra một cơ chế hoàn tất, pipeline có khả năng **chạy vô thời hạn**. Không chạy thử một pipeline vô hạn mà chưa có cách hủy trong bài tập tự động.

## 18. Vòng đời tài nguyên khi Gatherer nằm giữa pipeline

Gatherer không có nghĩa là nguồn I/O sẽ được đóng tự động khi terminal operation hoàn tất. Ví dụ `Files.lines` mở tài nguyên đọc file, nên caller phải dùng `try-with-resources`.

### 18.1. Lấy hai cửa sổ đầu từ file lớn

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

static List<List<String>> firstTwoBatches(Path path)
    throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .gather(Gatherers.windowFixed(3))
            .limit(2)
            .toList();
    }
}
```

Đặc điểm:

- `Files.lines` trả một stream **đọc lười**, giúp không cần nạp cả file bằng `readAllLines`.
- `windowFixed(3)` gom các dòng theo thứ tự file.
- `limit(2)` chỉ cần tối đa hai cửa sổ đầu ra, không yêu cầu đọc hết một file rất lớn.
- `toList()` hoàn thành **không tự đóng** stream `lines`.
- `try-with-resources` đóng stream nguồn cả khi đọc bình thường hoặc một giai đoạn ném ngoại lệ.

**Không khẳng định chỉ có chính xác sáu lần đọc vật lý ở mọi implementation**: buffering, read-ahead và mã hóa có thể làm tầng I/O đọc dữ liệu trước khi pipeline cần đến tất cả các dòng.

### 18.2. `findFirst` không phải `close`

```java
try (Stream<String> lines = Files.lines(path)) {
    var first = lines
        .gather(Gatherers.windowFixed(10))
        .findFirst();
    // first: Optional<List<String>>
}
```

`findFirst` có thể short-circuit sau khi nhận cửa sổ đầu; nhưng việc **đóng descriptor** xảy ra khi thoát `try`, không phải một tác dụng phụ được đảm bảo của `findFirst`.

### 18.3. Khi Gatherer tự mở tài nguyên

Nếu custom Gatherer mở một file, stream con hoặc kết nối ở `initializer`/`integrator`, phải chỉ rõ:

- Ai là **owner**?
- Có cơ chế đóng khi dừng sớm hay ngoại lệ không?
- Có thể phát sinh nhiều state song song không?
- Finisher có thật sự được gọi trên mọi đường đi mà tài nguyên cần giải phóng không?

Không đặt toàn bộ trách nhiệm dọn tài nguyên vào `finisher` rồi ngầm coi nó là một `finally` thay cho `try-with-resources`. Nguồn có tài nguyên nên được đóng ở một phạm vi sở hữu rõ ràng bên ngoài pipeline, hoặc thiết kế close handler/owner riêng có thể kiểm thử.

### 18.4. Dừng sớm không đồng nghĩa huỷ công việc nền

Khi dùng `mapConcurrent` với mapper chờ I/O, downstream có thể đã nhận đủ kết quả và yêu cầu dừng. Gatherer cố gắng hủy công việc đang chạy theo cơ chế **best effort**, nhưng thời gian phản hồi còn phụ thuộc API I/O, interruptibility và những tác vụ đã được khởi động.

Thiết kế hệ thống không nên phụ thuộc vào “đã gọi `limit(1)` nên chỉ có đúng một HTTP request được gửi”. Nếu cần bảo đảm exactly-once, đó là vấn đề **giao thức và idempotency**, không phải tác dụng phụ tự động của gatherer.

## 19. Kiểm thử JUnit 5: thứ tự, nguồn vô hạn và dừng sớm

Các phép thử sau dùng class `GathererOrderAndStopDemo` từ mục 13 trên **JDK 24+**. Nên chạy chúng với JUnit Jupiter của dự án. Ví dụ dùng `@Timeout` cho các pipeline bắt đầu từ nguồn vô hạn; đây là **hàng rào kiểm thử**, không phải API hủy tác vụ production.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class GathererOrderAndStopDemoTest {

    @Test
    void fixedWindowPreservesOrderAndLastPartialWindow() {
        List<List<Integer>> actual = Stream.of(
            7, 2, 9, 1, 4, 8, 5
        )
            .gather(Gatherers.windowFixed(3))
            .toList();

        assertEquals(
            List.of(
                List.of(7, 2, 9),
                List.of(1, 4, 8),
                List.of(5)
            ),
            actual
        );
    }

    @Test
    void slidingWindowsOverlapByAllButOneElement() {
        List<List<Integer>> actual = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowSliding(3))
            .toList();

        assertEquals(
            List.of(
                List.of(1, 2, 3),
                List.of(2, 3, 4),
                List.of(3, 4, 5)
            ),
            actual
        );
    }

    @Test
    void shortFiniteSourceProducesOnePartialSlidingWindow() {
        var actual = Stream.of(10, 20)
            .gather(Gatherers.windowSliding(5))
            .toList();
        assertEquals(List.of(List.of(10, 20)), actual);
    }

    @Test
    void emptySourceProducesNoWindow() {
        assertTrue(Stream.<Integer>empty()
            .gather(Gatherers.windowFixed(3))
            .toList().isEmpty());

        assertTrue(Stream.<Integer>empty()
            .gather(Gatherers.windowSliding(3))
            .toList().isEmpty());
    }

    @Test
    void fixedWindowsAreUnmodifiable() {
        var windows = Stream.of("a", "b", "c")
            .gather(Gatherers.windowFixed(2))
            .toList();

        assertThrows(UnsupportedOperationException.class, () ->
            windows.get(0).add("x")
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void infiniteSourceTerminatesWithOutputLimit() {
        assertEquals(
            List.of(List.of(1, 2, 3), List.of(4, 5, 6)),
            GathererOrderAndStopDemo.firstTwoFixedWindows()
        );

        assertEquals(
            List.of(List.of(1, 2, 3), List.of(2, 3, 4)),
            GathererOrderAndStopDemo.firstTwoSlidingWindows()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void scanProducesPrefixSumsWithoutWaitingForEof() {
        assertEquals(
            List.of(1L, 3L, 6L, 10L, 15L),
            GathererOrderAndStopDemo.firstFiveRunningTotals()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void foldCompletesWhenInputIsBoundedFirst() {
        assertEquals(
            List.of(15L),
            GathererOrderAndStopDemo.foldFirstFive()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void customGathererStopsAtMarkerInclusively() {
        assertEquals(
            List.of(1, 2, 3, 4, 5),
            GathererOrderAndStopDemo.untilFiveInclusive()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void customStatefulGathererStopsAfterN() {
        assertEquals(
            List.of(1, 2, 3),
            GathererOrderAndStopDemo.firstThree()
        );
    }

    @Test
    void downstreamCanStopBeforeGathererPredicate() {
        var result = Stream.iterate(1, n -> n + 1)
            .gather(GathererOrderAndStopDemo
                .takeUntilInclusive(n -> n >= 20))
            .limit(3)
            .toList();

        assertEquals(List.of(1, 2, 3), result);
    }

    @Test
    void missingMarkerInFiniteStreamEmitsEverything() {
        var result = Stream.of(1, 2, 3)
            .gather(GathererOrderAndStopDemo
                .takeUntilInclusive(n -> n > 10))
            .toList();

        assertEquals(List.of(1, 2, 3), result);
    }

    @Test
    void firstNRejectsNonPositiveSize() {
        assertThrows(IllegalArgumentException.class, () ->
            GathererOrderAndStopDemo.firstN(0)
        );
        assertThrows(IllegalArgumentException.class, () ->
            GathererOrderAndStopDemo.firstN(-1)
        );
    }

    @Test
    void windowsRejectNonPositiveSize() {
        assertThrows(IllegalArgumentException.class, () ->
            Gatherers.windowFixed(0)
        );
        assertThrows(IllegalArgumentException.class, () ->
            Gatherers.windowSliding(-1)
        );
    }

    @Test
    void concurrentMapPreservesEncounterOrderOfResult() {
        assertEquals(
            List.of(50, 10, 40, 20, 30),
            GathererOrderAndStopDemo.concurrentOrdered()
        );
    }

    @Test
    void customGathererDoesNotLeakStateBetweenRuns() {
        var gatherer = GathererOrderAndStopDemo
            .<Integer>firstN(2);

        assertEquals(
            List.of(1, 2),
            Stream.of(1, 2, 3).gather(gatherer).toList()
        );
        assertEquals(
            List.of(10, 20),
            Stream.of(10, 20, 30).gather(gatherer).toList()
        );
    }
}
```

**Lưu ý quan trọng về `@Timeout`:** timeout trong test giúp phát hiện hành vi treo, nhưng một tác vụ bị kẹt trong I/O hoặc vòng lặp không đáp ứng interrupt có thể cần cơ chế cách ly/cancel mạnh hơn ở môi trường kiểm thử. Không chạy pipeline `fold` trên nguồn vô hạn để “chứng minh nó treo”; giải thích từ ngữ nghĩa của API và kiểm thử phiên bản được giới hạn **trước fold** là đủ.

### 19.1. Test thứ tự khác test số lần gọi hàm

Các test ở trên so sánh danh sách kết quả với **dữ liệu kỳ vọng**. Chúng không buộc supplier/mapper được gọi chính xác N lần; API có thể cho phép buffering, cancellation muộn hoặc speculative work, nhất là với `mapConcurrent`.

### 19.2. Test tách state giữa các lần chạy

Test `customGathererDoesNotLeakStateBetweenRuns` đặc biệt quan trọng: sử dụng **cùng một instance Gatherer** trên hai stream mới. Nếu code lưu một counter bên ngoài thay vì tạo state qua initializer, lần chạy thứ hai có thể chỉ phát 0 phần tử hoặc ít hơn mong muốn.

### 19.3. Test không được phụ thuộc thứ tự thread completion

Nếu thay ví dụ `mapConcurrent` bằng mapper có `Thread.sleep` ngẫu nhiên, **không** kiểm thử thứ tự log “start/end”. Hãy kiểm tra thứ tự danh sách cuối với ordered source; nếu cần kiểm thử concurrency thực, dùng một bài kiểm thử/benchmark chuyên biệt tránh phụ thuộc vào clock và lập lịch.

## 20. Property-based checks: thay ví dụ đơn lẻ bằng bất biến

Ngoài một vài ví dụ cố định, có thể kiểm chứng `windowFixed`/`windowSliding` với mọi độ dài nguồn nhỏ và nhiều kích thước cửa sổ.

### 20.1. Bất biến của `windowFixed`

Với nguồn có `n >= 0` phần tử và cửa sổ `size > 0`:

- Số cửa sổ bằng `n / size` cộng thêm 1 nếu `n % size != 0`.
- Mọi cửa sổ trừ cửa sổ cuối có độ dài `size`.
- Cửa sổ cuối dài trong khoảng `[1, size]` nếu nguồn không rỗng.
- Ghép các cửa sổ theo thứ tự phải thu lại **đúng danh sách gốc**, không mất hoặc lặp phần tử.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

for (int n = 0; n <= 40; n++) {
    List<Integer> source = IntStream.range(0, n)
        .boxed().toList();

    for (int size = 1; size <= 8; size++) {
        List<List<Integer>> windows = source.stream()
            .gather(Gatherers.windowFixed(size))
            .toList();

        int expectedCount =
            n / size + (n % size == 0 ? 0 : 1);

        if (windows.size() != expectedCount) {
            throw new AssertionError("Sai số cửa sổ");
        }

        List<Integer> flattened = windows.stream()
            .flatMap(List::stream)
            .toList();
        if (!source.equals(flattened)) {
            throw new AssertionError("Mất/trùng phần tử");
        }
    }
}
```

Với `windowFixed`, phép kiểm tra **flatten** đặc biệt hiệu quả vì các cửa sổ không chồng lấn và giữ encounter order. Nó phát hiện lỗi thiếu/trùng phần tử mà một phép kiểm tra tổng số cửa sổ đơn lẻ có thể bỏ qua.

### 20.2. Bất biến của `windowSliding`

Với `n > 0`:

- Nếu `n < size`: có một cửa sổ chứa toàn bộ nguồn.
- Nếu `n >= size`: có `n - size + 1` cửa sổ.
- Với mỗi hai cửa sổ kế tiếp đầy đủ, **đuôi dài `size - 1` của cửa sổ trước bằng đầu dài `size - 1` của cửa sổ sau**.
- Nếu `n == 0`: không có cửa sổ.

Ví dụ kiểm tra trên một dãy:

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

for (int i = 1; i < windows.size(); i++) {
    List<Integer> prev = windows.get(i - 1);
    List<Integer> curr = windows.get(i);

    if (!prev.subList(1, 3).equals(curr.subList(0, 2))) {
        throw new AssertionError("Cửa sổ trượt sai");
    }
}
```

### 20.3. Bất biến của custom `takeUntilInclusive`

Trên nguồn ordered hữu hạn:

1. Nếu có marker, kết quả là **tiền tố kết thúc tại marker đầu tiên**.
2. Nếu không có marker, kết quả bằng toàn bộ nguồn.
3. Không có phần tử sau marker trong kết quả.
4. Các phần tử trước và tại marker giữ nguyên thứ tự và số lần xuất hiện.

Với nguồn cho phép trùng giá trị, **không** chỉ so sánh `Set`; `Set` sẽ loại mất thông tin tần suất. Dùng `List.equals` để kiểm chứng tiền tố trong trường hợp ordered.

## 21. Các phản mẫu thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Dùng `fold(...).limit(1)` trên nguồn vô hạn | Fold đợi kết thúc nguồn để phát kết quả | Cắt input **trước fold**, hoặc dùng `scan` |
| Cho rằng `limit(2)` sau `windowFixed(3)` nghĩa là đọc hai input | Limit tính theo số cửa sổ **đầu ra** | Xác định số input cần cho mỗi output |
| Gắn `unordered()` vào nguồn cần thứ tự sự kiện | Encounter order không còn được cam kết | Giữ ordered source hoặc định nghĩa thứ tự khác |
| Cho rằng `parallel()` làm `ofSequential` chạy state song song | Gatherer dùng default combiner phải được đánh giá tuần tự | Chỉ viết combiner khi chứng minh đúng |
| Trả `false` từ `Integrator.ofGreedy` để tự dừng | Greedy cam kết không tự khởi xướng short-circuit | Dùng integrator thông thường |
| Bỏ qua `downstream.push(...) == false` | Downstream đã từ chối output tiếp | Truyền lại tín hiệu dừng |
| Tin `isRejecting() == false` nghĩa là `push` chắc chắn thành công | Đây là kiểm tra best effort | Luôn kiểm tra kết quả `push` |
| Dùng một counter mutable ngoài initializer | Nhiều lần chạy có thể dùng chung state | Tạo state mới trong `initializer` |
| Gọi `push` với `ArrayList` rồi `clear` | Kết quả đã phát bị thay đổi qua cùng tham chiếu | Tạo snapshot `List.copyOf` |
| Giữ `Downstream` cho callback bất đồng bộ | Vi phạm vòng đời tham chiếu | Phát đồng bộ trong integrator/finisher |
| Dùng `mapConcurrent` cho thao tác có side effect không idempotent | Có tác vụ bắt đầu trước khi downstream dừng | Tách giao dịch/thiết kế idempotency |
| Đòi mapper chạy đúng N lần khi dùng `limit` | Buffering, speculative work, tối ưu hóa | Kiểm thử kết quả và ranh giới tài nguyên |
| Quên `Files.lines.close` sau `findFirst` | Terminal operation không tự đóng tài nguyên | `try-with-resources` |
| Dùng cửa sổ cực lớn không tính bộ nhớ | Gatherer phải đệm dữ liệu | Giới hạn kích thước, đo peak memory |
| Chạy test “pipeline vô hạn phải treo” | Có thể treo bộ test | Kiểm tra bằng lập luận và test nhánh hữu hạn |
| Biên dịch `Stream.gather` bằng `--release 17` | API chưa tồn tại | JDK 24+ hoặc phương án fallback |

## 22. Bài tập thực hành có định hướng

### Bài 1 — Cửa sổ cố định trên log hữu hạn

Cho `List<String> events = List.of("A", "B", "C", "D", "E", "F", "G")`. Dùng `windowFixed(3)` và kiểm tra:

- Có ba cửa sổ.
- Cửa sổ cuối chỉ có `G`.
- Ghép các cửa sổ bằng `flatMap(List::stream)` thu lại đúng nguồn.
- Không thể gọi `add` lên cửa sổ kết quả.

### Bài 2 — Cửa sổ trượt và thứ tự

Dùng `Stream.of(5, 1, 9, 3, 2)` và `windowSliding(3)`. Viết ra chính xác ba cửa sổ, kiểm tra hai phần tử cuối của cửa sổ trước khớp hai phần tử đầu của cửa sổ sau. Sau đó thử `unordered()` và giải thích vì sao không thể khẳng định **thứ tự cửa sổ** tương ứng với nguồn ban đầu nếu ràng buộc encounter order đã bị bỏ.

### Bài 3 — Tổng tích lũy từ nguồn vô hạn

Tính 10 số tam giác đầu bằng `scan(() -> 0L, Math::addExact)` và `limit(10)`. Kiểm chứng phần tử thứ 10 bằng `55` và giải thích vì sao `fold(...).limit(10)` không thay thế được `scan` trên nguồn vô hạn.

### Bài 4 — Dừng tại marker, có bao gồm marker

Với nguồn `[10,20,30,-1,40,50]`, dùng `takeUntilInclusive(n -> n == -1)`. Đối chiếu với `takeWhile(n -> n != -1)`. Viết test chứng minh trường hợp có marker, không có marker, marker ở phần tử đầu và nguồn rỗng.

### Bài 5 — Giới hạn input hay output?

Trên `Stream.iterate(1, n -> n + 1)`:

1. `limit(5).gather(windowFixed(3)).toList()`.
2. `gather(windowFixed(3)).limit(5).toList()`.

Dự đoán hai kết quả và giải thích tại sao chúng không tương đương về số phần tử nguồn cần xem. Không đưa số lần gọi supplier chính xác vào điều kiện test.

### Bài 6 — Lỗi state dùng chung

Viết một gatherer “lấy 3 phần tử” nhưng counter bị capture từ bên ngoài. Dùng cùng instance gatherer trên hai stream hữu hạn và quan sát lỗi. Sửa lại bằng `Gatherer.ofSequential(Counter::new, integrator)`, viết test chứng minh các lần chạy độc lập.

### Bài 7 — `Integrator.Greedy` có thích hợp không?

Một integrator phát gấp đôi mỗi số và **không tự dừng** nguồn có thể dùng `ofGreedy` không? Một integrator **dừng khi gặp 0** thì sao? Giải thích vì sao JDK có quyền bỏ qua giá trị trả về của greedy trong các tối ưu hóa.

### Bài 8 — Nguồn I/O và dừng sớm

Đọc file văn bản lớn bằng `Files.lines`. Tìm hai cửa sổ ba dòng đầu, đóng file đúng cách và nêu cách kiểm chứng tài nguyên được đóng trong cả thành công và lỗi. Không coi `limit(2)` là bảo đảm tầng I/O chỉ đọc chính xác 6 dòng vật lý.

### Bài 9 — `mapConcurrent` và mapper chậm

Cho 30 ID yêu cầu gọi một dịch vụ giả lập mất thời gian. Dùng `mapConcurrent(4, mapper)` để tính giá trị, kiểm tra kết quả **theo encounter order**. Bổ sung `limit(3)` phía sau rồi phân tích vì sao một số tác vụ đã bắt đầu có thể còn làm việc và vì sao cần idempotency nếu mapper có side effect.

### Bài 10 — Tự viết batch gatherer có finisher

Cài `batches(4)` theo mục 14. Trên nguồn 10 phần tử, kiểm tra kích thước các lô là `4,4,2`. Dùng nguồn vô hạn và `limit(2)` để nhận hai lô đủ bốn phần tử. Chứng minh các list đã phát không bị thay đổi khi state nội bộ được xóa để nhận lô mới.

### Bài 11 — Cần một combiner thật sự

Đề xuất cách thiết kế một gatherer có thể gộp các phân vùng cho phép tổng hợp **kết hợp, độc lập thứ tự**, rồi so sánh với `takeUntilInclusive` phụ thuộc **marker đầu tiên**. Chỉ viết combiner nếu có thể chứng minh tính đúng trong mọi cách chia và mọi thứ tự gộp hợp lệ. Nếu chỉ cần tổng, vì sao `mapToLong(...).sum()` hoặc `Collectors.summingLong` thường đơn giản hơn?

### Bài 12 — Liveness có giới hạn

Thiết kế một ứng dụng đọc các sự kiện tiềm năng vô hạn, tìm sự kiện đáp ứng điều kiện rồi dừng. Yêu cầu có **giới hạn số sự kiện** hoặc deadline rõ ràng, phân biệt:

- Không có sự kiện thỏa trong khoảng đã kiểm tra.
- Nguồn kết thúc thật sự.
- Nguồn bị hủy hoặc không đọc được.

Không đánh đồng ba tình huống thành “kết quả rỗng” và không dùng pipeline vô hạn không có đường hủy trong bài test.

## 23. Bảng quyết định và tổng kết

| Bài toán | Cách làm | Điểm cần kiểm chứng |
| --- | --- | --- |
| Gom các phần tử liên tiếp theo từng lô cố định | `Gatherers.windowFixed(size)` | Thứ tự, lô cuối ngắn, kích thước bộ đệm |
| Cửa sổ chồng lấn | `Gatherers.windowSliding(size)` | Vùng chồng lấn, nguồn ngắn, số cửa sổ |
| Tổng/tình trạng tích lũy sau từng input | `Gatherers.scan(initial, scanner)` | Mỗi input phát một output; xử lý overflow |
| Chỉ cần một tổng cuối trên nguồn hữu hạn | `Gatherers.fold(initial, folder)` | Cần EOF để phát kết quả |
| Nguồn vô hạn + tổng của N input đầu | `limit(N)` **trước `fold`** | Giới hạn input, không phải output |
| Nguồn vô hạn + N kết quả đầu từ cửa sổ/scan | `gather(...).limit(N)` | Gatherer phát từng bước; bộ đệm vừa phải |
| Giữ luôn marker dừng | Custom `ofSequential` integrator trả `false` | Phát marker trước khi dừng, thứ tự rõ |
| Lấy tối đa N phần tử đơn giản | `Stream.limit(N)` | Ưu tiên API có sẵn, không viết gatherer vô ích |
| Downstream đã đủ kết quả | `push(...) == false` | Dừng phát, truyền tín hiệu phù hợp |
| Downstream có thể đã từ chối | `isRejecting()` | Best effort, không thay kiểm tra `push` |
| Integrator chủ động short-circuit | Integrator thường, **không** `ofGreedy` | Giữ đúng tín hiệu dừng |
| Gatherer có state và phụ thuộc thứ tự | `Gatherer.ofSequential` | State riêng mỗi lần chạy, không combiner giả |
| Mapper độc lập, có thể thực hiện đồng thời | `Gatherers.mapConcurrent(k, mapper)` | Thứ tự output và hủy best effort |
| Cần sắp thứ tự từ nguồn unordered | `sorted` hoặc thứ tự nghiệp vụ tường minh | Không dựa vào timing worker |
| Nguồn là file/tài nguyên I/O | `try-with-resources` quanh owner | Short-circuit không auto-close |
| Kiểm thử nguồn vô hạn | Pipeline có đường dừng và `@Timeout` | Không để test treo |
| Chạy trên JDK 17/21 | Dùng Stream operations cũ | Không có `Gatherer` API chuẩn |
| Chạy trên JDK 24+ | `Stream.gather` API chính thức | Không cần `--enable-preview` |

### Kết luận

**Xử lý thứ tự, nguồn vô hạn và dừng sớm khi dùng Gatherer** đòi hỏi ba loại suy luận khác nhau. **Thứ tự** đến từ encounter order của nguồn và hợp đồng biến đổi, không phải thứ tự các thread kết thúc. **Nguồn vô hạn** chỉ xử lý được thành kết quả hữu hạn khi có cơ chế phát output và điều kiện kết thúc thực sự; `scan` và cửa sổ có thể phát tăng dần, còn `fold` phải đợi kết thúc input. **Dừng sớm** có thể bắt đầu từ integrator hoặc downstream, nhưng vẫn phải quản lý tài nguyên bằng owner rõ ràng.

Khi viết custom gatherer, hãy dùng state khởi tạo **riêng cho mỗi lần đánh giá**, tôn trọng `Downstream.push` và đừng sử dụng `Integrator.ofGreedy` nếu chính gatherer cần chủ động short-circuit. Chỉ bổ sung combiner khi chứng minh được tính đúng trong các cách phân hoạch song song. Bắt đầu bằng những API có sẵn, kiểm thử nội dung và liveness trên nguồn hữu hạn/vô hạn đã kiểm soát, rồi mới đo hiệu năng và cân nhắc dùng Gatherer cho các pipeline thực tế.
