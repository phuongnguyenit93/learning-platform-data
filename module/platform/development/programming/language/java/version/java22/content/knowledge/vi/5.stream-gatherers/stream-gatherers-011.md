# Đánh giá bộ nhớ cùng khả năng dừng sớm khi xử lý luồng lớn hoặc vô hạn

## Vì sao cần quan tâm đến bộ nhớ và dừng sớm?

Stream có thể đại diện cho dữ liệu rất lớn, dữ liệu được sinh liên tục hoặc một luồng vô hạn. Khi thêm `Gatherer`, ta có thể giữ trạng thái giữa các phần tử, tạo cửa sổ, tích lũy kết quả hoặc xử lý nhiều tác vụ đồng thời. Những khả năng này hữu ích, nhưng cũng làm phát sinh hai câu hỏi quan trọng:

1. Gatherer cần giữ bao nhiêu dữ liệu trong bộ nhớ khi xử lý từng phần tử?
2. Khi downstream đã có đủ kết quả, pipeline có thể ngừng đọc upstream hay vẫn tiếp tục tiêu thụ dữ liệu?

Stream Gatherers là API chính thức từ JDK 24 qua JEP 485. Các ví dụ trong bài dùng `Stream.gather`, `Gatherer` và `Gatherers` theo API ổn định hiện hành, không sử dụng cú pháp preview của Java 22 hoặc Java 23.

## Phân biệt bộ nhớ của Gatherer và bộ nhớ của pipeline

`Stream.gather(...)` là một stateful intermediate operation. Nó có thể giữ trạng thái nội bộ, nhưng bản thân pipeline vẫn lazy: intermediate operation chưa xử lý phần tử cho tới khi terminal operation bắt đầu tiêu thụ stream.

Khi đánh giá bộ nhớ, cần tách ít nhất bốn phần:

```text
Nguồn dữ liệu
     |
     v
Gatherer state (A)
     |
     v
Các phần tử được phát xuống downstream
     |
     v
Terminal operation / nơi lưu kết quả

Bộ nhớ tổng còn phụ thuộc các tác vụ đang chạy,
các kết quả chờ đúng encounter order và cấu trúc trung gian.
```

Một Gatherer có trạng thái nhỏ vẫn có thể dẫn tới tiêu thụ bộ nhớ lớn nếu terminal operation lưu toàn bộ kết quả. Ngược lại, một pipeline chạy mãi trên stream vô hạn vẫn có thể giữ bộ nhớ ổn định nếu Gatherer chỉ giữ một lượng trạng thái hữu hạn và terminal operation xử lý từng kết quả rồi bỏ đi.

Một cách ước lượng hữu ích là:

\[
M_{total} \approx M_{source} + M_{gatherer} + M_{in\text{-}flight} + M_{downstream} + M_{overhead}
\]

Đây là mô hình tư duy, không phải công thức đo chính xác. API không cam kết cách hiện thực hoặc số byte cấp phát cho từng Gatherer.

## Chi phí bộ nhớ của các Gatherer dựng sẵn

### `windowFixed(size)`

`windowFixed(size)` gom các phần tử thành những cửa sổ liên tiếp, không chồng lấp. Mỗi cửa sổ có tối đa `size` phần tử; cửa sổ cuối có thể ít phần tử hơn nếu upstream kết thúc.

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
        .gather(Gatherers.windowFixed(3))
        .toList();

// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Ở mức thuật toán, Gatherer chỉ cần tích lũy một cửa sổ hiện tại trước khi phát nó xuống downstream. Vì vậy, trạng thái đang gom có kích thước giới hạn theo `size`. Tuy nhiên, tài liệu API lưu ý các cửa sổ có thể được cấp phát liền nhau và sớm vì lý do hiệu năng; chọn kích thước cửa sổ quá lớn cho stream nhỏ có thể gây tiêu thụ bộ nhớ đáng kể trong suốt lần đánh giá.

Nếu dùng `toList()`, toàn bộ các cửa sổ đã phát ra tiếp tục được giữ trong danh sách kết quả. Với `n` phần tử đầu vào và kích thước cửa sổ `k`, số cửa sổ xấp xỉ `ceil(n / k)`, còn tổng số tham chiếu phần tử trong kết quả vẫn xấp xỉ `n`. Vì vậy, Gatherer có trạng thái giới hạn không có nghĩa kết quả cuối cùng cũng có bộ nhớ giới hạn.

### `windowSliding(size)`

`windowSliding(size)` tạo các cửa sổ chồng lấp. Mỗi cửa sổ mới giữ lại các phần tử của cửa sổ trước, bỏ phần tử cũ nhất và thêm phần tử kế tiếp.

```java
List<List<Integer>> windows = Stream.of(10, 20, 30, 40, 50)
        .gather(Gatherers.windowSliding(3))
        .toList();

// [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
```

Gatherer cần nhớ tối đa một cửa sổ gồm `size` phần tử để tạo kết quả kế tiếp. Nếu stream có ít phần tử hơn kích thước cửa sổ, Gatherer chỉ phát ra một cửa sổ chứa tất cả phần tử hiện có; stream rỗng không tạo cửa sổ.

Giống `windowFixed`, tài liệu API cho phép hiện thực cấp phát cửa sổ liền nhau và sớm. Không nên dựa vào giả định rằng các danh sách kết quả dùng chung một vùng lưu trữ hoặc chỉ chiếm một bản sao dữ liệu. Nếu giữ mọi cửa sổ bằng `toList()`, cùng một phần tử đầu vào có thể xuất hiện trong nhiều cửa sổ kết quả; lượng tham chiếu đầu ra có thể tăng theo số cửa sổ nhân kích thước cửa sổ.

### `scan(initial, accumulator)`

`scan` thực hiện prefix scan: sau mỗi phần tử, nó phát ra kết quả tích lũy mới. Trạng thái cần giữ phụ thuộc kiểu dữ liệu và logic của accumulator.

```java
List<Long> totals = Stream.of(2L, 3L, 5L, 7L)
        .gather(Gatherers.scan(() -> 0L, Long::sum))
        .toList();

// [2, 5, 10, 17]
```

Với accumulator là một số `long`, Gatherer chỉ cần một giá trị tích lũy, tức trạng thái có kích thước cố định. Nếu accumulator giữ một `List` chứa mọi phần tử đã thấy, trạng thái tăng theo độ dài stream. Vì vậy, chi phí của `scan` không thể đánh giá chỉ dựa trên tên operation; phải xem cấu trúc dữ liệu mà accumulator trả về.

`scan` phát một kết quả cho mỗi phần tử đầu vào. Nếu downstream chỉ cần vài prefix đầu tiên, `limit` hoặc `findFirst` có thể dừng pipeline sớm. Nếu dùng `toList()` trên stream lớn, tất cả prefix được lưu lại và bộ nhớ đầu ra tăng theo số phần tử.

### `fold(initial, folder)`

`fold` tích lũy toàn bộ đầu vào theo thứ tự và chỉ phát ra một kết quả khi upstream hoàn tất. Nó phù hợp với phép tích lũy không có combiner phù hợp hoặc có phụ thuộc thứ tự.

```java
long total = Stream.of(2L, 3L, 5L, 7L)
        .gather(Gatherers.fold(() -> 0L, Long::sum))
        .findFirst()
        .orElse(0L);

// 17
```

Với accumulator là `long`, trạng thái có kích thước cố định. Nhưng nếu folder liên tục thêm phần tử vào một danh sách, trạng thái tăng theo kích thước đầu vào. Ngoài ra, `fold` không phát kết quả trung gian để downstream xử lý dần.

Điểm quan trọng với stream vô hạn: `fold` cần upstream kết thúc mới có thể phát kết quả. Vì vậy, `findFirst()` đặt sau `fold` không làm cho phép tính trên stream vô hạn kết thúc; `findFirst` đang chờ kết quả mà Gatherer chỉ tạo khi hoàn tất toàn bộ upstream.

### `mapConcurrent(maxConcurrency, mapper)`

`mapConcurrent` thực thi mapper đồng thời bằng virtual thread và giữ encounter order của stream. Tham số `maxConcurrency` giới hạn số tác vụ được thực hiện đồng thời.

```java
List<String> firstNames = names.stream()
        .gather(Gatherers.mapConcurrent(8, this::lookupDisplayName))
        .limit(20)
        .toList();
```

Giới hạn đồng thời giúp kiểm soát số tác vụ đang chạy, nhưng không đồng nghĩa toàn bộ pipeline có bộ nhớ cố định. Mỗi tác vụ có thể giữ input, tài nguyên I/O và kết quả riêng; kết quả hoàn tất sau có thể phải chờ kết quả trước để giữ encounter order. Nếu mapper tạo ra đối tượng lớn hoặc tự giữ dữ liệu không giới hạn, bộ nhớ vẫn có thể tăng.

Khi downstream không cần thêm phần tử, `mapConcurrent` cố gắng hủy các tác vụ đang chạy theo cơ chế best-effort. Không nên dựa vào việc mọi tác vụ sẽ bị dừng tức thời; mapper nên có hành vi an toàn khi tác vụ hoàn tất muộn hoặc không thể hủy ngay.

### Bảng so sánh nhanh

| Gatherer | Trạng thái logic cần giữ | Khi phát kết quả | Hành vi trên stream vô hạn |
|---|---|---|---|
| `windowFixed(k)` | Tối đa một cửa sổ `k` phần tử đang gom, ngoài các kết quả downstream giữ lại. | Sau mỗi `k` phần tử; cửa sổ cuối thiếu phần tử được phát khi upstream kết thúc bình thường. | Có thể phát cửa sổ liên tục; `limit` sau Gatherer có thể dừng sau một số cửa sổ hữu hạn. |
| `windowSliding(k)` | Một cửa sổ gồm tối đa `k` phần tử gần nhất, ngoài các kết quả downstream giữ lại. | Sau khi có đủ `k` phần tử, rồi phát sau mỗi phần tử mới. | Có thể phát cửa sổ liên tục; `limit` sau Gatherer có thể dừng sớm. |
| `scan` | Một accumulator; kích thước phụ thuộc kiểu accumulator. | Sau mỗi phần tử. | Có thể phát kết quả liên tục; `limit` hoặc `findFirst` có thể dừng sớm. |
| `fold` | Một accumulator; có thể cố định hoặc tăng theo đầu vào. | Chỉ khi upstream hoàn tất. | Không phát kết quả nếu upstream không bao giờ kết thúc. |
| `mapConcurrent(c)` | Tác vụ đang chạy và kết quả chờ; số tác vụ đồng thời bị giới hạn bởi `c`. | Khi kết quả có thể được phát theo encounter order. | Có thể xử lý liên tục; downstream short-circuit yêu cầu hủy tác vụ đang chạy theo best-effort. |

Đây là mô tả trạng thái logic và hành vi quan sát được, không phải cam kết số byte hoặc cấu trúc cấp phát nội bộ. Riêng `windowFixed` và `windowSliding` có API note về việc cấp phát cửa sổ liền nhau và sớm.

## Short-circuit trong Stream pipeline

Short-circuit là khả năng dừng tiêu thụ upstream khi đã có đủ kết quả để hoàn tất yêu cầu. Một số operation quan trọng:

| Operation | Điều kiện dừng |
|---|---|
| `limit(n)` | Đã nhận đủ `n` phần tử đầu ra. |
| `findFirst()` | Tìm được phần tử đầu tiên theo encounter order. |
| `findAny()` | Tìm được một phần tử phù hợp. |
| `anyMatch(predicate)` | Có ít nhất một phần tử thỏa predicate. |
| `allMatch(predicate)` | Có một phần tử không thỏa predicate. |
| `noneMatch(predicate)` | Có một phần tử thỏa predicate. |

Có operation short-circuit là điều kiện cần nhưng chưa đủ để một pipeline trên stream vô hạn kết thúc. Gatherer có thể cần tiêu thụ nhiều phần tử trước khi phát ra kết quả, hoặc operation đứng trước Gatherer có thể cần toàn bộ đầu vào.

Ví dụ, `sorted().limit(10)` trên stream vô hạn không thể phát mười phần tử đầu tiên vì `sorted` phải biết toàn bộ đầu vào trước khi xác định thứ tự. Tương tự, `fold(...).findFirst()` không thể kết thúc trên stream vô hạn vì `fold` chỉ phát kết quả khi upstream hoàn tất.

## Vị trí của `limit` làm thay đổi ý nghĩa

`limit` đặt trước hoặc sau Gatherer giới hạn hai loại dữ liệu khác nhau:

```java
// Tối đa 100 phần tử ĐẦU VÀO được Gatherer nhìn thấy.
source.limit(100)
      .gather(Gatherers.windowFixed(10))
      .toList();

// Tối đa 10 cửa sổ ĐẦU RA được giữ lại.
source.gather(Gatherers.windowFixed(10))
      .limit(10)
      .toList();
```

Với `windowFixed(10)`, pipeline thứ hai cần tối đa 100 phần tử đầu vào để tạo mười cửa sổ. Với Gatherer có thể phát nhiều đầu ra cho một đầu vào, số lượng đầu vào cần tiêu thụ có thể khác; không nên thay thế giới hạn đầu ra bằng giới hạn đầu vào nếu hai ý nghĩa không tương đương.

## Ví dụ: xử lý ba cửa sổ đầu tiên của stream vô hạn

### Với cửa sổ cố định

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FixedWindowShortCircuit {
    public static void main(String[] args) {
        AtomicLong consumed = new AtomicLong();

        List<List<Long>> firstWindows = Stream.iterate(1L, n -> n + 1)
                .peek(ignored -> consumed.incrementAndGet())
                .gather(Gatherers.windowFixed(4))
                .limit(3)
                .toList();

        System.out.println(firstWindows);
        System.out.println("Input consumed: " + consumed.get());
    }
}
```

Kết quả:

```text
[[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
Input consumed: 12
```

Stream nguồn là vô hạn, nhưng `limit(3)` giới hạn số cửa sổ đầu ra. Mỗi cửa sổ cần bốn phần tử, nên pipeline chỉ cần tiêu thụ mười hai phần tử rồi dừng. `toList()` chỉ giữ ba cửa sổ, không tích lũy toàn bộ stream.

### Với cửa sổ trượt

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class SlidingWindowShortCircuit {
    public static void main(String[] args) {
        AtomicLong consumed = new AtomicLong();

        List<List<Long>> firstWindows = Stream.iterate(1L, n -> n + 1)
                .peek(ignored -> consumed.incrementAndGet())
                .gather(Gatherers.windowSliding(4))
                .limit(3)
                .toList();

        System.out.println(firstWindows);
        System.out.println("Input consumed: " + consumed.get());
    }
}
```

Kết quả:

```text
[[1, 2, 3, 4], [2, 3, 4, 5], [3, 4, 5, 6]]
Input consumed: 6
```

Để tạo cửa sổ đầu tiên, Gatherer cần bốn phần tử. Mỗi cửa sổ tiếp theo chỉ cần thêm một phần tử mới, nên ba cửa sổ cần tổng cộng sáu phần tử đầu vào.

## Dừng sớm ngay bên trong Gatherer tùy chỉnh

Ngoài short-circuit từ downstream như `limit` và `findFirst`, một Gatherer tự viết có thể quyết định không nhận thêm phần tử. `Gatherer.Integrator.integrate(...)` trả về:

- `true`: tiếp tục nhận phần tử đầu vào.
- `false`: Gatherer không muốn nhận thêm phần tử và yêu cầu dừng xử lý upstream.

`Gatherer.Downstream.push(value)` trả về `false` khi downstream không còn nhận phần tử. Có thể truyền kết quả này trực tiếp làm kết quả của integrator để dừng khi downstream đã từ chối.

Ví dụ sau chỉ phát ra phần tử đầu tiên đạt ngưỡng rồi yêu cầu dừng upstream:

```java
import java.util.Optional;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class StopAtThreshold {
    static Gatherer<Long, Void, Long> stopAt(long threshold) {
        return Gatherer.ofSequential(
                (state, element, downstream) -> {
                    if (element >= threshold) {
                        downstream.push(element);
                        return false;
                    }

                    return true;
                },
                (state, downstream) -> { }
        );
    }

    public static void main(String[] args) {
        Optional<Long> first = Stream.iterate(1L, n -> n + 1)
                .gather(stopAt(100L))
                .findFirst();

        System.out.println(first.orElseThrow());
    }
}
```

Kết quả là `100`. Khi integrator gặp giá trị đạt ngưỡng, nó đẩy giá trị đó xuống downstream rồi trả `false`; upstream không cần tiếp tục tạo phần tử tiếp theo.

`Gatherer.Downstream.isRejecting()` cho biết downstream có được biết là đang từ chối nhận thêm phần tử hay không. Đây chỉ là thông tin best-effort; có thể dùng để bỏ qua công việc tốn kém trước khi tạo output, nhưng không thay thế việc kiểm tra kết quả của `push`. Khi integrator cần khả năng dừng sớm, hãy dùng `Gatherer.Integrator` thông thường; `Gatherer.Integrator.Greedy` được định nghĩa là loại integrator tiêu thụ toàn bộ input và không thể tự short-circuit.

## Cách xử lý kết quả mà không tích lũy toàn bộ

Nếu mục tiêu là phân tích một luồng dài hoặc vô hạn, hãy xử lý kết quả ngay khi nhận được thay vì gom tất cả vào một collection:

```java
Stream.iterate(1L, n -> n + 1)
        .gather(Gatherers.windowSliding(60))
        .forEach(window -> {
            double average = window.stream()
                    .mapToLong(Long::longValue)
                    .average()
                    .orElse(0.0);

            // Xử lý kết quả ngay rồi bỏ đi, không gom mọi cửa sổ vào List.
            System.out.println(average);
        });
```

Đoạn này chạy liên tục với stream vô hạn nên terminal operation không trả về. Tuy nhiên, nếu `processAverage` không giữ lại mọi cửa sổ hoặc kết quả đã nhận, Gatherer chỉ cần giữ trạng thái của cửa sổ hiện tại cùng các đối tượng đang được xử lý. Trong ứng dụng thực tế, `processAverage` cũng cần có giới hạn hàng đợi và backpressure phù hợp nếu nó gửi dữ liệu sang một hệ thống chậm hơn.

Tránh các cách sau nếu nguồn có thể rất lớn hoặc vô hạn:

```java
// Không kết thúc với stream vô hạn; cố giữ toàn bộ kết quả.
List<List<Long>> allWindows = Stream.iterate(1L, n -> n + 1)
        .gather(Gatherers.windowSliding(60))
        .toList();

// Cũng không kết thúc: fold chỉ phát kết quả khi upstream kết thúc.
Optional<Long> result = Stream.iterate(1L, n -> n + 1)
        .gather(Gatherers.fold(() -> 0L, Long::sum))
        .findFirst();
```

Với stream vô hạn, `toList()`, `count()` hoặc `fold` chờ upstream kết thúc sẽ không hoàn tất. Một terminal operation không short-circuit có thể chạy mãi; điều đó không nhất thiết làm bộ nhớ tăng nếu không lưu kết quả, nhưng nó cũng không tạo ra một kết quả cuối cùng.

## Tác động của parallel stream

Gatherer có thể được thiết kế để xử lý song song nếu cung cấp combiner hợp lệ. Trong quá trình xử lý song song, nhiều trạng thái trung gian có thể được tạo cho các phân vùng rồi kết hợp lại. Do đó:

- Trạng thái riêng của mỗi phân vùng làm tổng bộ nhớ có thể tăng theo số phân vùng.
- Combiner có thể cần giữ đồng thời hai trạng thái trong khi hợp nhất.
- Downstream short-circuit có thể không ngăn mọi tác vụ đã bắt đầu ngay lập tức; một lượng công việc dư có thể hoàn tất trước khi tín hiệu dừng lan tới tất cả phân vùng.
- Không phải mọi Gatherer đều có thể kết hợp đúng. Không tự thêm combiner nếu chưa chứng minh được kết quả tương đương với xử lý tuần tự.

Với bài toán cần dừng sớm chính xác và dễ dự đoán, hãy bắt đầu bằng stream tuần tự. Chỉ chuyển sang parallel sau khi đo hiệu năng và xác minh ngữ nghĩa của combiner, thứ tự kết quả và chi phí bộ nhớ.

## Checklist thiết kế Gatherer cho dữ liệu lớn

1. **Xác định trạng thái tối thiểu.** Chỉ giữ dữ liệu cần cho kết quả kế tiếp; ưu tiên ring buffer hoặc cấu trúc có kích thước giới hạn khi bài toán cho phép.
2. **Đặt giới hạn đúng vị trí.** `source.limit(n)` giới hạn số input; `.gather(...).limit(n)` giới hạn số output.
3. **Kiểm tra thời điểm phát kết quả.** `scan` phát từng prefix; `window*` cần đủ phần tử cho cửa sổ đầu; `fold` đợi upstream kết thúc.
4. **Kiểm tra terminal operation.** `findFirst`, `anyMatch` và `limit` có thể short-circuit; `toList`, `count` và `forEach` không tự giới hạn số phần tử.
5. **Không tích lũy vô hạn ở downstream.** Một Gatherer có trạng thái O(1) không cứu được pipeline nếu downstream lưu mọi kết quả.
6. **Tính cả công việc đang chạy.** Với `mapConcurrent`, chọn `maxConcurrency` dựa trên tài nguyên và khả năng chịu tải của dịch vụ đích.
7. **Xử lý cancellation.** Tác vụ đồng thời có thể chỉ bị hủy best-effort; không đặt side effect không thể đảo ngược vào mapper nếu không có cơ chế xử lý kết quả đến muộn.
8. **Đo trên dữ liệu thực.** Dùng Java Flight Recorder, profiler hoặc benchmark để đo allocation, heap, GC pause và throughput; không suy ra số byte chỉ từ chữ ký Gatherer.

## Kết luận

Muốn xử lý luồng lớn hoặc vô hạn an toàn, cần thiết kế cả trạng thái Gatherer lẫn nơi tiêu thụ kết quả. `windowFixed`, `windowSliding` và `scan` có thể phát dữ liệu tăng dần; `fold` chỉ phát khi nguồn kết thúc; `mapConcurrent` giới hạn tác vụ đang chạy nhưng vẫn có chi phí cho kết quả và tác vụ chờ. Dùng `limit`, `findFirst` hoặc integrator trả `false` khi đã đủ dữ liệu, đồng thời tránh terminal operation lưu toàn bộ kết quả nếu không cần thiết.

## Tài liệu tham khảo

- [JEP 485 — Stream Gatherers (JDK 24)](https://openjdk.org/jeps/485)
- [Java SE 27 API — `Gatherers`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html)
- [Java SE 27 API — `Gatherer`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 27 API — `Gatherer.Downstream`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [Java SE 27 API — `Stream.gather`, `limit` and short-circuit operations](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java 25 Core Libraries Guide — Stream Gatherers](https://docs.oracle.com/en/java/javase/25/core/stream-gatherers.html)
