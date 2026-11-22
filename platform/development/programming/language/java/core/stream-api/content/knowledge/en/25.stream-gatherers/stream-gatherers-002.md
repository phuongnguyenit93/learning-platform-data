# Phân biệt Gatherer với map, mapMulti và Collector

Khi thiết kế một pipeline Java Stream, bốn công cụ dễ bị đặt cạnh nhau là `map`, `mapMulti`, **Stream Gatherer** và **Collector**. Chúng đều tham gia chuyển đổi hoặc tổng hợp dữ liệu, nhưng **không làm cùng một việc**. Chọn sai công cụ có thể khiến code phức tạp, làm mất phần tử, mất thứ tự, chia sẻ trạng thái không an toàn hoặc trả về một kết quả không phù hợp với yêu cầu.

Điểm cần ghi nhớ ngay từ đầu:

- **`map`**: mỗi phần tử đầu vào tạo **một phần tử đầu ra** qua hàm ánh xạ.
- **`mapMulti`**: mỗi phần tử đầu vào có thể phát **0, 1 hoặc nhiều phần tử đầu ra** qua một consumer; thường dùng khi không cần duy trì trạng thái qua các phần tử đầu vào.
- **`gather` với `Gatherer`**: thao tác trung gian mở rộng; có thể phát 0..n phần tử, **giữ trạng thái riêng**, quyết định dừng tích hợp và thực hiện bước hoàn tất.
- **`collect` với `Collector`**: thao tác kết thúc để **tích lũy đầu vào thành một kết quả cuối**, ví dụ `List`, `Map`, số liệu thống kê hoặc DTO.

Bài thuộc chương **Stream Gatherer** của module **JAVA_STREAM_API**, nơi người học đã gặp pipeline lazy, `filter`, `map`, `reduce` và `collect`, cũng như grouping, collector tùy chỉnh, `Spliterator` và xử lý song song. Chúng ta sẽ phân biệt công cụ theo **kiểu kết quả, cách dùng trạng thái, tính lazy, thứ tự, dừng sớm và hợp đồng song song**, sau đó triển khai ví dụ Java 24 hoàn chỉnh và các bài tập thực hành.

## 1. Mức JDK và vị trí của từng API trong pipeline

| API | Có từ JDK | Vai trò | Hình dạng kết quả |
|---|---:|---|---|
| `Stream.map(Function)` | Java 8 | *Intermediate operation* | `Stream<R>` |
| `Stream.mapMulti(BiConsumer)` | Java 16 | *Intermediate operation* | `Stream<R>` |
| `Stream.gather(Gatherer)` | Java 24 chính thức | *Intermediate operation* | `Stream<R>` |
| `Stream.collect(Collector)` | Java 8 | *Terminal operation* | `R`, thường không phải Stream |

Stream Gatherers xuất hiện dưới dạng **preview** ở Java 22 và Java 23, rồi trở thành tính năng chính thức trong **Java 24**. Những ví dụ dùng `Gatherer` ở bài này hướng tới **JDK 24 trở lên**. Không thể sao chép chúng nguyên vẹn vào một dự án Java 8, 11, 17 hoặc 21 rồi mong biên dịch được.

### 1.1. Intermediate operation khác terminal operation

`map`, `mapMulti` và `gather` đều trả về **một Stream mới** để có thể nối thêm các bước:

```java
List<String> result = source
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();
```

Ở đây, `map` và `filter` mô tả pipeline. `toList()` mới là **terminal operation** kích hoạt xử lý và trả danh sách.

Ngược lại:

```java
Map<String, Long> counts = source
        .collect(Collectors.groupingBy(
                s -> s.substring(0, 1),
                Collectors.counting()));
```

`collect` đã kết thúc pipeline và trả `Map`. Nếu muốn tiếp tục dùng Stream trên các entry, phải tạo một Stream **mới** từ `counts.entrySet()`, chứ không thể nối `.filter(...)` trực tiếp lên `Map`.

### 1.2. Một bảng quyết định ngắn

| Câu hỏi nghiệp vụ | Công cụ nên nghĩ tới trước |
|---|---|
| “Đổi `Order` thành mã đơn?” | `map` |
| “Một đơn có nhiều dòng, muốn phát từng dòng?” | `flatMap` hoặc `mapMulti` |
| “Muốn số thứ tự hoặc tổng lũy kế sau **mỗi dòng**?” | `Gatherer` có trạng thái |
| “Muốn chia các dòng liên tiếp thành cửa sổ?” | `Gatherers.windowFixed` hoặc Gatherer tùy biến |
| “Muốn dừng Gatherer sau một quy tắc nội bộ?” | `Gatherer.Integrator` có tín hiệu `boolean` |
| “Muốn tổng doanh thu **cuối cùng** theo SKU?” | `collect(groupingBy(...))` hoặc `toMap` |
| “Muốn số lượng, min, max, average của một trường số?” | `summarizingInt`/`summarizingLong` |
| “Muốn một báo cáo đa chỉ số khi pipeline kết thúc?” | `Collector` tùy biến hoặc `Collectors.teeing` |

**Không có công cụ nào luôn tốt hơn công cụ còn lại**. Lựa chọn đúng là công cụ đơn giản nhất diễn đạt **đúng số đầu ra, đúng thời điểm phát kết quả và đúng trạng thái cần lưu**.

## 2. map: một phần tử thành một phần tử

Chữ ký cốt lõi:

```java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper);
```

Đối với mỗi phần tử `T` được pipeline thực sự xử lý, mapper trả về **một giá trị `R`**. Giá trị đó có thể là một đối tượng phức tạp, một collection, thậm chí là `null`; `map` **không tự loại null** hay làm phẳng collection.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> words = Arrays.asList(" java ", "stream", " api ");

List<String> cleaned = words.stream()
        .map(String::trim)
        .collect(Collectors.toList());

System.out.println(cleaned); // [java, stream, api]
```

Mỗi chuỗi đầu vào tạo **một chuỗi** trong kết quả. Nếu một đơn hàng có danh sách dòng sản phẩm:

```java
Stream<List<OrderLine>> nested = orders.stream()
        .map(Order::getLines);
```

Kết quả vẫn là `Stream<List<OrderLine>>`: một phần tử đầu ra là **cả danh sách con**. `map` không có trách nhiệm nối các danh sách thành một Stream dòng sản phẩm.

### 2.1. Khi không nên viết stateful map

Một cách viết sai là giữ biến đếm chung bên ngoài mapper:

```java
int[] counter = {0};

List<String> numbered = words.parallelStream()
        .map(word -> (++counter[0]) + ":" + word)
        .collect(Collectors.toList());
// SAI: mảng mutable được chia sẻ giữa các worker.
```

Lỗi này có hai tầng:

1. `map` được thiết kế cho hàm **non-interfering** và thường **stateless**; biến đếm bên ngoài biến phép ánh xạ thành thao tác phụ thuộc thứ tự và trạng thái.
2. Khi Stream song song, cập nhật `counter[0]` có **data race**; số thứ tự có thể trùng, mất hoặc không tương ứng encounter order.

Nếu chỉ cần **đánh số theo vị trí một List**, có thể dùng `IntStream.range(0, list.size())`. Nếu cần biến đổi trạng thái theo dãy phần tử một cách tổng quát, **Gatherer tuần tự** thể hiện ý định rõ hơn.

## 3. mapMulti: phát nhiều phần tử không cần tạo Stream con

`Stream.mapMulti` có từ **Java 16**. Chữ ký khái quát:

```java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper);
```

Mapper nhận:

- Một phần tử đầu vào kiểu `T`.
- Một `Consumer<R>` (gọi là `emit` trong ví dụ) để phát các giá trị đầu ra.

Mapper có thể gọi `emit.accept(...)` **không lần nào, một lần hoặc nhiều lần**:

```java
List<Integer> values = List.of(1, 2, 3);

List<Integer> output = values.stream()
        .<Integer>mapMulti((n, emit) -> {
            if (n % 2 != 0) {
                emit.accept(n);
                emit.accept(n * 10);
            }
        })
        .toList();

System.out.println(output); // [1, 10, 3, 30]
```

Số `2` không phát phần tử nào; mỗi số lẻ phát hai kết quả. Đây là điều `map` không thực hiện trực tiếp được vì `map` ánh xạ mỗi phần tử đầu vào thành **một giá trị**.

### 3.1. So với flatMap

`flatMap` từ Java 8 có thể giải bài toán tương tự bằng việc trả **Stream con**:

```java
List<Integer> output = List.of(1, 2, 3).stream()
        .flatMap(n -> n % 2 == 0
                ? Stream.<Integer>empty()
                : Stream.of(n, n * 10))
        .toList();
// [1, 10, 3, 30]
```

Trong `mapMulti`, mapper phát trực tiếp qua `emit.accept`; trong `flatMap`, mapper trả `Stream<R>`. `mapMulti` có thể tránh tạo một Stream con cho mỗi phần tử, đặc biệt hữu ích khi mỗi đầu vào tạo ít phần tử con. Nhưng **không được suy ra mapMulti luôn nhanh hơn**; cần đo chi phí thực tế.

### 3.2. Giới hạn của mapMulti

`mapMulti` rất hợp lý khi xử lý **mỗi phần tử độc lập** và phát ra 0..n giá trị. Nó không cung cấp riêng:

- Một `initializer` tạo trạng thái cho toàn bộ lượt biến đổi.
- Một `finisher` để đẩy dữ liệu còn tồn đọng khi nguồn kết thúc.
- Một `Integrator` trả tín hiệu dừng tích hợp theo quy tắc của phép biến đổi.
- Một `combiner` để mô tả cách kết hợp trạng thái khi được phép tích hợp song song.

Có thể cố lưu state bên ngoài callback, nhưng làm vậy khiến chương trình phụ thuộc thứ tự/lịch chạy và dễ vi phạm yêu cầu stateless của Stream. Khi bài toán thật sự **liên kết các phần tử kế tiếp**, `Gatherer` là lựa chọn có hợp đồng rõ hơn.

## 4. Gatherer: phép biến đổi trung gian có khả năng giữ trạng thái

Giao diện `Gatherer<T, A, R>` mô tả:

- **`T`**: kiểu phần tử đầu vào.
- **`A`**: kiểu trạng thái tích lũy, thường có thể thay đổi qua các bước.
- **`R`**: kiểu phần tử đầu ra được phát cho pipeline phía sau.

Ở mức khái niệm:

```text
Stream<T>
    |
    v
 Gatherer initializer ---> trạng thái A
    |
    v
 integrator(A, T, downstream)
    |      |
    |      +-- có thể push 0..n phần tử R
    |      +-- có thể trả true / false để tiếp tục / dừng
    |
    v
 finisher(A, downstream)  [nếu cần]
    |
    v
Stream<R> ---> map/filter/limit/collect/... tiếp theo
```

Khác với `Collector`, Gatherer vẫn nằm ở **giữa pipeline**. Ví dụ:

```java
List<RunningTotal> totals = transactions.stream()
        .gather(runningTotals())
        .filter(total -> total.amountCents() > 0)
        .toList();
```

Đoạn này giả định đã định nghĩa kiểu `RunningTotal` và Gatherer `runningTotals()`; mã tự chạy đầy đủ nằm ở phần 7.

### 4.1. Những bộ phận quan trọng

| Bộ phận | Ý nghĩa | Khác `mapMulti` ở đâu? |
|---|---|---|
| `initializer` | Tạo trạng thái `A` của quá trình tích hợp | `mapMulti` không có tham số này |
| `integrator` | Nhận state, phần tử nguồn và downstream | Có thể dựa vào state qua các phần tử |
| `downstream.push(R)` | Phát phần tử tới pipeline tiếp theo | Trả `boolean`, báo còn chấp nhận đầu ra không |
| `integrator` trả `boolean` | Báo có tiếp tục tích hợp đầu vào không | Có giao thức dừng riêng |
| `finisher` | Dùng trạng thái cuối để phát thêm nếu cần | `mapMulti` không có bước hoàn tất |
| `combiner` | Cách kết hợp trạng thái trong Gatherer có thể tích hợp song song | Không phải mọi Gatherer cần hoặc có combiner |

Không phải Gatherer nào cũng bắt buộc có state/finisher. Với biến đổi stateless, có overload không cần state, nhưng khi `map` hoặc `mapMulti` đã đủ, thêm Gatherer thường chỉ làm code khó đọc hơn.

### 4.2. Các biến thể tạo Gatherer

Ví dụ Gatherer **tuần tự có trạng thái**:

```java
Gatherer<T, State, R> gatherer = Gatherer.ofSequential(
        State::new,
        (state, value, downstream) -> {
            // Cập nhật state.
            // Có thể downstream.push(output).
            return true;
        });
```

Ví dụ Gatherer **tuần tự có bước hoàn tất**:

```java
Gatherer<T, State, R> gatherer = Gatherer.ofSequential(
        State::new,
        (state, value, downstream) -> {
            // Tích lũy, có thể phát đầu ra.
            return true;
        },
        (state, downstream) -> {
            // Phát phần dữ liệu còn lại khi hoàn tất nếu cần.
        });
```

Đây là những mẫu chữ ký, không phải chương trình tự chạy do các kiểu `T`, `State`, `R` và quy tắc tích hợp chưa được định nghĩa. Cần dùng chúng khi thiết kế Gatherer cụ thể, thay vì gắn một state mutable dùng chung bên ngoài Stream.

### 4.3. push(false) và return false không phải “lọc bỏ”

Với integrator:

```java
(state, value, downstream) -> {
    if (!isValid(value)) {
        return true; // Bỏ qua phần tử, tiếp tục xử lý đầu vào khác.
    }
    return downstream.push(transform(value));
}
```

- Không gọi `push` nghĩa là **không phát đầu ra cho phần tử này**.
- Trả `true` nghĩa là **tiếp tục tích hợp** nếu downstream còn nhu cầu.
- Trả `false` nghĩa là **Gatherer muốn dừng tích hợp đầu vào**.
- `downstream.push(...)` trả `false` khi downstream từ chối thêm đầu ra; nên truyền tín hiệu dừng khi phù hợp.

Không dùng `return false` chỉ để bỏ một phần tử không hợp lệ. Điều đó làm mất những phần tử hợp lệ nằm sau nó.

## 5. Collector: tập trung vào một kết quả cuối

`Collector<T, A, R>` mô tả phép *mutable reduction* từ phần tử `T` qua trạng thái `A` thành **kết quả cuối `R`**.

```java
Map<String, Long> revenueBySku = lines.stream()
        .collect(Collectors.groupingBy(
                LineView::sku,
                Collectors.summingLong(LineView::amountCents)));
```

`collect` tiêu thụ pipeline và trả `Map<String, Long>`. Nó **không phát một Stream kết quả trung gian sau mỗi `LineView`** để các thao tác Stream phía sau tiếp tục lọc theo tổng lũy kế.

### 5.1. Năm thành phần của Collector

| Thành phần | Chức năng |
|---|---|
| `supplier` | Tạo container tích lũy mới |
| `accumulator` | Cập nhật container khi nhận phần tử |
| `combiner` | Gộp hai container, nhất là khi framework chia nhánh |
| `finisher` | Chuyển container thành kết quả cuối |
| `characteristics` | Mô tả `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` |

Gatherer cũng có initializer/integrator/finisher, nhưng **không nên đồng nhất máy móc các cặp tên gần giống nhau**:

- `Collector.accumulator` nhận phần tử để xây một kết quả giảm dần; nó không có downstream để `push` từng phần tử đầu ra.
- `Gatherer.integrator` có thể phát **nhiều đầu ra ngay trong lúc duyệt**, có thể dừng sớm, và phần đầu ra ấy vẫn đi qua các intermediate operation tiếp theo.
- `Collector.finisher` tạo kết quả `R` của terminal `collect`; `Gatherer.finisher` có thể **phát thêm phần tử Stream**.
- Một Gatherer được tạo bằng `ofSequential` không cần combiner cho tích hợp song song; Collector hợp lệ phải có `combiner` theo hợp đồng ngay cả khi ứng dụng hiện chủ yếu chạy tuần tự.

### 5.2. Gatherer.fold và Collector có vẻ giống nhau ở đâu?

Một số Gatherer chuẩn, chẳng hạn `Gatherers.fold`, có thể giảm nhiều phần tử thành một giá trị rồi phát giá trị ấy vào Stream. Về **dữ liệu xuất ra**, nó có thể gần một reduction/collector; về **vị trí trong pipeline**, nó vẫn là intermediate operation:

```java
// Sơ đồ ý tưởng:
source.gather(foldingGatherer)
      .map(this::formatSummary)
      .toList();

// Trong khi collect kết thúc pipeline:
Summary summary = source.collect(summaryCollector);
```

Hai dòng là hai phương án độc lập, cần nguồn Stream mới mỗi lần; `foldingGatherer`, `Summary` và `summaryCollector` là kiểu/giá trị giả định. Chọn `collect` khi nghiệp vụ chỉ cần kết quả cuối; chọn Gatherer khi kết quả cần **tiếp tục đi qua các bước Stream** hoặc cần một giao thức tích hợp/phát đầu ra phức tạp.

## 6. Bảng so sánh đầy đủ bốn công cụ

| Tiêu chí | `map` | `mapMulti` | `Gatherer` | `Collector` |
|---|---|---|---|---|
| Bước trong pipeline | Intermediate | Intermediate | Intermediate | Terminal |
| Đầu ra mỗi phần tử đầu vào | Đúng một giá trị | 0..n giá trị | 0..n giá trị, tùy state | Tích lũy, không phát Stream trung gian |
| Kiểu kết quả lời gọi | `Stream<R>` | `Stream<R>` | `Stream<R>` | `R` |
| State cục bộ sống qua nhiều input | Không phải mô hình được cung cấp | Không phải mô hình được cung cấp | Có thể có `A` riêng | Có trạng thái tích lũy `A` |
| Bước hoàn tất để phát thêm phần tử | Không | Không | Có thể có | Finisher trả một kết quả cuối |
| Tín hiệu dừng tích hợp riêng | Không | Không | Có, `boolean` từ integrator | Không phải giao thức của collector |
| Có thể tiếp tục `filter/map/limit` trực tiếp | Có | Có | Có | Không, vì đã kết thúc Stream |
| Khi song song | Hàm thường phải stateless/non-interfering | Callback thường phải stateless/non-interfering | Phụ thuộc thiết kế Gatherer và combiner | Phụ thuộc hợp đồng supplier/accumulator/combiner |
| Trường hợp nên ưu tiên | Biến đổi đơn giản 1:1 | Phát 0..n từ một input độc lập | Biến đổi có trạng thái, cửa sổ, phát khi kết thúc, dừng có quy tắc | Tổng hợp cuối, grouping, báo cáo |

**Cẩn trọng với từ “0..n”:** không có nghĩa một pipeline luôn phát đúng mọi phần tử dự kiến nếu phía sau dùng `limit`, `findFirst` hoặc một terminal operation ngắn mạch. Stream có thể dừng sớm; Gatherer còn có giao thức dừng riêng. Hãy kiểm thử theo **hợp đồng kết quả** chứ không lấy số lần gọi lambda làm chỉ số nghiệp vụ.

## 7. Ví dụ Java 24 hoàn chỉnh: map, mapMulti, Gatherer, Collector trên cùng dữ liệu

Bài toán: có danh sách đơn hàng, mỗi đơn chứa nhiều dòng chi tiết. Ta cần:

1. **`map`** để lấy mã từng đơn.
2. **`mapMulti`** để phát các dòng chi tiết kèm mã đơn, bỏ đơn không có chi tiết.
3. **`Gatherer`** để phát **doanh thu lũy kế sau mỗi dòng**, kèm số thứ tự dòng.
4. **`Collector`** để tạo một báo cáo cuối gồm số dòng, tổng đơn vị hàng và tổng doanh thu.
5. Dùng `groupingBy` để tính doanh thu theo SKU.

Lưu toàn bộ đoạn dưới đây thành `GathererComparisonDemo.java`. Ví dụ sử dụng các `record` và `Stream.toList()`, nên phù hợp với yêu cầu **JDK 24+** của `Gatherer`.

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Gatherer;

public class GathererComparisonDemo {

    record Item(String sku, int quantity, long unitPriceCents) {
        Item {
            if (sku == null || sku.isEmpty()) {
                throw new IllegalArgumentException("sku không hợp lệ");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("Số lượng/đơn giá sai");
            }
        }
    }

    record Order(String id, List<Item> items) {
        Order {
            if (id == null || items == null) {
                throw new IllegalArgumentException("Order không hợp lệ");
            }
            items = List.copyOf(items);
        }
    }

    record LineView(
            String orderId,
            String sku,
            long quantity,
            long amountCents) {}

    record RunningTotal(
            long lineNumber,
            long amountCents) {}

    record Report(
            long lineCount,
            long units,
            long revenueCents) {}

    // A: trạng thái dành riêng cho Gatherer.
    static final class RunningState {
        long lineNumber;
        long amountCents;
    }

    // Gatherer trung gian có trạng thái; mỗi dòng phát một snapshot.
    static Gatherer<LineView, RunningState, RunningTotal>
            runningTotals() {
        return Gatherer.ofSequential(
                RunningState::new,
                (state, line, downstream) -> {
                    state.lineNumber = Math.addExact(
                            state.lineNumber, 1L);
                    state.amountCents = Math.addExact(
                            state.amountCents, line.amountCents());
                    return downstream.push(new RunningTotal(
                            state.lineNumber, state.amountCents));
                });
    }

    // Collector kết thúc pipeline; trả một Report.
    static Collector<LineView, long[], Report>
            reportCollector() {
        return Collector.of(
                () -> new long[3],
                (state, line) -> {
                    state[0] = Math.addExact(state[0], 1L);
                    state[1] = Math.addExact(
                            state[1], line.quantity());
                    state[2] = Math.addExact(
                            state[2], line.amountCents());
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] = Math.addExact(left[i], right[i]);
                    }
                    return left;
                },
                state -> new Report(
                        state[0], state[1], state[2]));
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("D01", List.of(
                        new Item("P01", 2, 100L),
                        new Item("P02", 1, 50L))),
                new Order("D02", List.of(
                        new Item("P01", 3, 100L))),
                new Order("D03", List.of())
        );

        // 1) map: mỗi đơn tạo đúng một mã đơn.
        List<String> orderIds = orders.stream()
                .map(Order::id)
                .toList();
        System.out.println(orderIds);
        // [D01, D02, D03]

        // 2) mapMulti: mỗi đơn phát 0..n LineView.
        List<LineView> lines = orders.stream()
                .<LineView>mapMulti((order, emit) -> {
                    for (Item item : order.items()) {
                        long amount = Math.multiplyExact(
                                (long) item.quantity(),
                                item.unitPriceCents());
                        emit.accept(new LineView(
                                order.id(), item.sku(),
                                item.quantity(), amount));
                    }
                })
                .toList();

        System.out.println(lines.size()); // 3
        // D01 phát 2 dòng; D02 phát 1 dòng; D03 phát 0 dòng.

        // 3) Gatherer: phát tổng doanh thu sau mỗi dòng.
        List<RunningTotal> running = lines.stream()
                .gather(runningTotals())
                .toList();

        System.out.println(running);
        // [RunningTotal[lineNumber=1, amountCents=200],
        //  RunningTotal[lineNumber=2, amountCents=250],
        //  RunningTotal[lineNumber=3, amountCents=550]]

        // 4) Collector: chỉ trả một kết quả cuối.
        Report report = lines.stream()
                .collect(reportCollector());

        System.out.println(report);
        // Report[lineCount=3, units=6, revenueCents=550]

        // 5) Một Collector có sẵn để nhóm theo SKU.
        Map<String, Long> revenueBySku = lines.stream()
                .collect(Collectors.groupingBy(
                        LineView::sku,
                        TreeMap::new,
                        Collectors.summingLong(
                                LineView::amountCents)));

        System.out.println(revenueBySku);
        // {P01=500, P02=50}

        // 6) Gatherer là intermediate operation nên còn lọc tiếp được.
        List<RunningTotal> overTwoHundred = lines.stream()
                .gather(runningTotals())
                .filter(total -> total.amountCents() > 200)
                .toList();

        System.out.println(overTwoHundred);
        // [RunningTotal[lineNumber=2, amountCents=250],
        //  RunningTotal[lineNumber=3, amountCents=550]]
    }
}
```

### 7.1. Phân tích kết quả

| Bước | Số phần tử đầu vào | Số đầu ra | Nội dung trọng tâm |
|---|---:|---:|---|
| `orders.stream().map(Order::id)` | 3 đơn | 3 mã đơn | **1:1**, vẫn giữ D03 |
| `orders.stream().mapMulti(...)` | 3 đơn | 3 dòng chi tiết | **0..n**, D03 không tạo dòng |
| `lines.stream().gather(runningTotals())` | 3 dòng | 3 snapshot | Dòng 1: 200; dòng 2: 250; dòng 3: 550 |
| `lines.stream().collect(reportCollector())` | 3 dòng | Một `Report` | 3 dòng, 6 đơn vị, 550 cents |
| `groupingBy(..., summingLong(...))` | 3 dòng | Một `Map` | P01: 500, P02: 50 |

Để đạt **doanh thu lũy kế**, Gatherer phải biết tổng tiền từ các dòng **trước đó**. `mapMulti` có thể phát dòng chi tiết của từng đơn, nhưng không nên dùng một biến `sum` nằm ngoài callback để giả làm state xuyên phần tử. Trong Collector, chúng ta chỉ cần báo cáo cuối, nên không phải tạo một danh sách snapshot rồi lấy phần tử cuối.

### 7.2. Vì sao dùng Math.multiplyExact và Math.addExact?

`quantity × unitPriceCents` có thể vượt miền `long` nếu số liệu lớn. Ví dụ bảo vệ phép nhân bằng `Math.multiplyExact`; cả Gatherer và Collector đều dùng `Math.addExact` để phát hiện tổng tràn. Nếu số học vượt phạm vi `long`, chương trình ném `ArithmeticException` thay vì âm thầm tạo báo cáo sai.

Với bài toán tiền tệ thực tế, còn phải xác định đơn vị tiền, chính sách giảm giá, hoàn tiền và chuyển đổi ngoại tệ. Ví dụ cố ý dùng cents nguyên để tránh sai số do `double`, không ngụ ý mọi dữ liệu tiền tệ đều biểu diễn được an toàn bằng `long`.

### 7.3. Vì sao tạo Stream mới cho mỗi phép?

Một đối tượng `Stream` chỉ được tiêu thụ một lần. `orders` và `lines` là các `List` có thể duyệt lại, nên ta gọi `stream()` mới cho mỗi phép kiểm tra. Không được gọi `collect` xong rồi dùng tiếp `map` trên chính Stream đã tiêu thụ.

## 8. Ví dụ Gatherer có finisher: gộp phần tử liên tiếp

Một số bài toán không chỉ cần state sau từng dòng mà còn cần **phát phần dữ liệu đang giữ khi đầu vào kết thúc**. Ví dụ, ta muốn nén chuỗi phần tử thành các “đợt” gồm những giá trị liên tiếp giống nhau:

```text
Đầu vào: A, A, B, B, B, A
Đầu ra:  A:2, B:3, A:1
```

Nếu chỉ dùng `groupingBy` để đếm theo khóa, kết quả là `{A=3, B=3}` và **không thể hiện hai đợt A tách nhau**. Nếu dùng `mapMulti` thông thường, mỗi phần tử không có state được cung cấp để nhớ đợt hiện tại. Gatherer tuần tự có state và finisher diễn đạt đúng bài toán.

### 8.1. Code Java 24

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class ConsecutiveRunsDemo {

    static final class RunState {
        String current;
        long count;
    }

    static Gatherer<String, RunState, String> consecutiveRuns() {
        return Gatherer.ofSequential(
                RunState::new,
                (state, value, downstream) -> {
                    if (state.current == null) {
                        state.current = value;
                        state.count = 1L;
                        return true;
                    }

                    if (state.current.equals(value)) {
                        state.count++;
                        return true;
                    }

                    String completed =
                            state.current + ":" + state.count;
                    state.current = value;
                    state.count = 1L;

                    return downstream.push(completed);
                },
                (state, downstream) -> {
                    if (state.current != null) {
                        downstream.push(
                                state.current + ":" + state.count);
                    }
                });
    }

    public static void main(String[] args) {
        List<String> runs = Stream.of(
                        "A", "A", "B", "B", "B", "A")
                .gather(consecutiveRuns())
                .toList();

        System.out.println(runs); // [A:2, B:3, A:1]

        System.out.println(
                Stream.<String>empty()
                        .gather(consecutiveRuns())
                        .toList()); // []
    }
}
```

**Giải thích:** integrator giữ `current` và `count`. Khi gặp giá trị mới, nó **phát đợt đã hoàn thành**, rồi bắt đầu đợt mới. Đợt cuối không có “giá trị tiếp theo” để kích hoạt bước phát; vì vậy `finisher` đẩy đợt cuối ra downstream. Chương trình giả định phần tử đầu vào **khác null**, để giá trị `null` được dùng làm sentinel “chưa có đợt”. Nếu null là dữ liệu hợp lệ, cần một cờ trạng thái riêng.

### 8.2. Vì sao phải giữ encounter order?

Kết quả `A:2, B:3, A:1` mô tả **những lần xuất hiện liên tiếp**. Nếu nguồn không có encounter order, ranh giới các đợt không có ý nghĩa ổn định. Dùng một `List` có thứ tự hoặc sắp xếp theo một khóa nghiệp vụ trước khi `gather`.

### 8.3. Vì sao không dùng Collector để nén các đợt?

Có thể viết Collector tùy biến với state và combiner phức tạp để xử lý các phân đoạn, nhưng phải giải bài toán gộp **đợt cuối của nhánh trái với đợt đầu của nhánh phải**. Gatherer tuần tự phù hợp hơn khi yêu cầu là **phát từng đợt theo thứ tự** để pipeline phía sau tiếp tục xử lý.

Đây cũng là trường hợp `Gatherers.windowFixed` không hoàn toàn thay thế: cửa sổ cố định chia theo **kích thước**, còn bài toán này chia theo **ranh giới thay đổi giá trị**.

## 9. Thứ tự, xử lý song song và trạng thái

Không thể chọn công cụ chỉ bằng câu “nên chạy nhanh hơn trên parallel stream”.

### 9.1. map và mapMulti

`map` và `mapMulti` diễn đạt tốt các phép biến đổi **không can thiệp nguồn**, thường **stateless**. Với parallel stream, các lambda có thể được gọi bằng nhiều worker, theo lịch không giống encounter order. Nếu nguồn là `List` có thứ tự và kết quả thu thập bằng `toList()`, Stream vẫn phải đáp ứng hợp đồng thứ tự đầu ra phù hợp; nhưng **thứ tự thực thi side effect trong lambda không được bảo đảm**.

### 9.2. Gatherer.ofSequential

Một Gatherer được tạo bằng `Gatherer.ofSequential` **không cung cấp combiner để tích hợp trạng thái song song tùy tiện**. Điều đó phù hợp cho các phép biến đổi mà kết quả mỗi bước phụ thuộc trạng thái từ bước trước.

```java
List<Long> ordered = List.of(5L, 3L, -2L, 7L);

List<RunningTotal> totals = ordered.parallelStream()
        .gather(runningTotals())
        .toList();
```

Khi nguồn có encounter order, yêu cầu tổng lũy kế là `5, 8, 6, 13` theo thứ tự ấy. `ofSequential` không biến bài toán tổng lũy kế thành phép reduction có thể chia tùy ý; việc yêu cầu parallel stream không mặc nhiên đem lại lợi ích cho giai đoạn trạng thái tuần tự. Không dựa vào tên thread cụ thể hoặc thứ tự gọi lambda như một hợp đồng.

### 9.3. Collector không CONCURRENT vẫn dùng được trên parallel stream

`Collectors.toList()` hay `Collectors.groupingBy(...)` có thể chạy đúng trên parallel stream mà không cần accumulator của chúng nhận ghi đồng thời trên **cùng container**. Framework có thể tạo trạng thái riêng cho các nhánh và gọi `combiner` để gộp.

`Collectors.groupingByConcurrent(...)` hoặc `toConcurrentMap(...)` có tính chất khác về chiến lược tích lũy và thứ tự; không đổi sang concurrent collector chỉ vì tên gọi hấp dẫn. Nếu kết quả phụ thuộc thứ tự đầu/cuối, thay collector có thể **đổi ngữ nghĩa**.

### 9.4. Mutable state và ownership

| Công cụ | Nên giữ state ở đâu? | Tránh điều gì? |
|---|---|---|
| `map` | Không cần state xuyên các phần tử | Biến đếm chung bên ngoài lambda |
| `mapMulti` | State cục bộ trong một lần gọi để phát phần tử độc lập | Map chung hoặc List chung bị callback sửa đồng thời |
| `Gatherer.ofSequential` | Trạng thái mới từ `initializer` | Một đối tượng `static` dùng chung cho nhiều pipeline |
| `Collector` | Container từ `supplier`, được framework quản lý | Supplier luôn trả lại một container dùng chung; combiner sai |

Trong Gatherer, nếu phải phát một collection được lưu trong state, hãy **chụp bản sao** trước khi `push`. Nếu `push(state.list)` rồi `clear()`, các output đã phát có thể bị thay đổi do cùng giữ tham chiếu tới một List mutable.

## 10. Hiệu năng, bộ nhớ và ngắn mạch

### 10.1. Bộ nhớ của từng giải pháp

- `map` có thể xử lý từng phần tử mà không cần giữ toàn bộ đầu vào; bộ nhớ phụ thuộc pipeline và terminal operation.
- `mapMulti` có thể tránh tạo một Stream con cho từng phần tử nguồn; nếu đẩy toàn bộ output vào `toList()`, bộ nhớ kết quả vẫn tăng theo số phần tử được giữ.
- Gatherer lũy kế chỉ cần hai bộ đếm, tức trạng thái **`O(1)`**; Gatherer chia cửa sổ kích thước `k` có thể cần **`O(k)`** bộ đệm.
- Collector tính tổng/đếm có thể chỉ giữ **`O(1)`** trạng thái; `groupingBy` giữ trạng thái theo số nhóm, còn `toList` giữ toàn bộ các phần tử đầu ra.

Không phải dùng Gatherer nghĩa là luôn tiết kiệm bộ nhớ. Một Gatherer phát các List lớn rồi `collect(toList())` vẫn có thể cần giữ hầu hết dữ liệu.

### 10.2. Short-circuit

Một pipeline như:

```java
List<RunningTotal> firstTwo = transactions.stream()
        .gather(runningTotals())
        .limit(2)
        .toList();
```

có thể ngừng sau khi downstream nhận đủ hai kết quả. Gatherer cần tôn trọng tín hiệu `downstream.push(...)` và không giả định mọi giao dịch nguồn đã được tích hợp. `collect` tự nó không phải phép biến đổi trung gian để phát dần snapshot cho các bước Stream tiếp theo.

Với `mapMulti`, nếu callback phát nhiều phần tử trong một lần gọi, không dựa vào việc một terminal operation ngắn mạch sẽ luôn ngăn **mọi** `emit.accept` còn lại ngay lập tức. Hãy tránh side effect trong callback; ngắn mạch là hợp đồng về kết quả đầu ra, không phải bảo đảm đếm số lần callback.

### 10.3. Nguồn I/O vẫn phải được đóng

Một Stream từ `Files.lines` có thể nắm giữ tài nguyên:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> processed = lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .toList();
}
```

`map`, `mapMulti`, `gather` và `collect` **không thay thế** `try-with-resources` cho nguồn I/O. Đoạn code minh họa giả định `path` được khai báo và phương thức gọi có xử lý `IOException`. Nếu một Gatherer dùng Stream con hoặc tài nguyên riêng, cũng phải hiểu rõ vòng đời tài nguyên ấy.

### 10.4. Đo đúng trước khi tối ưu

Đừng kết luận `mapMulti` nhanh hơn `flatMap`, hoặc Gatherer nhanh hơn Collector, chỉ từ một ví dụ có vài phần tử. Kết quả phụ thuộc:

- Kích thước nguồn và số phần tử con trung bình trên mỗi phần tử cha.
- Chi phí cấp phát đối tượng trung gian.
- Trạng thái mutable, phép kết hợp và yêu cầu thứ tự.
- Khả năng chia việc của `Spliterator`.
- Chi phí terminal operation và lượng dữ liệu phải giữ.

Nếu hiệu năng thực sự quan trọng, dùng dữ liệu đại diện, kiểm tra tương đương kết quả trước, khởi động JVM, đo nhiều lần và cân nhắc JMH. Chọn thuật toán đúng trước khi tối ưu.

## 11. Những lỗi dễ mắc và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `map` cho danh sách con rồi mong phẳng thành từng dòng | `Stream<List<T>>` thay vì `Stream<T>` | Dùng `flatMap` hoặc `mapMulti` |
| Dùng `mapMulti` với counter mutable ngoài callback | Data race hoặc kết quả phụ thuộc lịch xử lý | Dùng nguồn có chỉ số hoặc Gatherer có state |
| Dùng `mapMulti` khi cần phát phần tồn ở cuối nguồn | Không có finisher | Dùng Gatherer có finisher |
| Trả `false` trong integrator chỉ để lọc một đầu vào | Dừng toàn bộ phần tích hợp | Không push và trả `true` |
| Không xét giá trị trả về của `downstream.push` | Tiêu thụ nguồn thừa hoặc sai quy tắc dừng | Lan truyền tín hiệu khi thích hợp |
| Initializer của Gatherer trả state static | Các pipeline lẫn trạng thái, có thể race | Tạo state mới cho mỗi lượt tích hợp |
| Phát tham chiếu mutable rồi sửa sau đó | Những output trước thay đổi nội dung | Phát snapshot/DTO mới |
| Dùng `collect` rồi nối `filter` trực tiếp trên kết quả | `collect` đã kết thúc Stream | Tạo Stream mới từ kết quả nếu cần |
| Viết Gatherer lũy kế để chỉ lấy tổng cuối | Code phức tạp không cần thiết | Dùng `sum`/`reduce` hoặc Collector |
| Chỉ đổi `toMap` sang `toConcurrentMap` để tăng tốc | Có thể mất thứ tự đầu/cuối | Xác định yêu cầu encounter order và benchmark |
| Kỳ vọng `Gatherer` chạy trên JDK 21 | API chưa sẵn có chính thức | Nâng JDK 24+ hoặc chọn API tương thích |
| Dựa vào `HashMap.toString()` để kiểm tra thứ tự | Không có cam kết thứ tự khóa | So nội dung hoặc chọn Map có thứ tự |
| Quên đóng `Files.lines` sau terminal operation | Rò rỉ file handle | `try-with-resources` |

## 12. Bài tập thực hành và lời giải

### Bài 1. Chọn map hay mapMulti

Cho `List<String> words = List.of("A", "B", "C")`. Muốn biến mỗi chuỗi thành độ dài thì dùng API nào? Muốn mỗi chuỗi phát cả chuỗi gốc và chuỗi viết thường thì sao?

**Đáp án:** Độ dài là phép **1:1**, dùng `map(String::length)`. Phát hai chuỗi cho mỗi phần tử có thể dùng `mapMulti`:

```java
List<String> pairs = words.stream()
        .<String>mapMulti((word, emit) -> {
            emit.accept(word);
            emit.accept(word.toLowerCase());
        })
        .toList();
// [A, a, B, b, C, c]
```

### Bài 2. Làm phẳng danh sách con

Cho `List<List<Integer>> nested = List.of(List.of(1, 2), List.of(), List.of(3))`. Dùng `mapMulti` phát từng số.

```java
List<Integer> flat = nested.stream()
        .<Integer>mapMulti((list, emit) -> {
            for (Integer value : list) {
                emit.accept(value);
            }
        })
        .toList();
// [1, 2, 3]
```

`flatMap(List::stream)` cũng phù hợp và có thể ngắn hơn. Không cần Gatherer có trạng thái cho bài toán này.

### Bài 3. Tính tổng hay tổng lũy kế?

Đầu vào `[5, 3, -2]`. Một dashboard chỉ cần tổng cuối; dashboard khác cần `[5, 8, 6]` sau từng giao dịch. Nên dùng gì?

**Đáp án:** Tổng cuối dùng `mapToLong(...).sum()` hoặc `reduce`. Tổng lũy kế dùng Gatherer có state như `runningTotals()` hoặc Gatherer chuẩn `Gatherers.scan` khi phù hợp.

### Bài 4. Khác biệt giữa Collector và Gatherer

`orders.stream().collect(groupingBy(...))` có thể nối trực tiếp `.filter(...)` để lọc **các nhóm đã được tạo** không?

**Đáp án:** Không, `collect` trả Map và kết thúc Stream. Có thể tạo `map.entrySet().stream()` từ kết quả Map. Gatherer thì là intermediate operation và có thể nối tiếp `filter` ngay trên những phần tử nó phát.

### Bài 5. Trả false trong Gatherer

Gatherer nhận `[-1, 2, 3]`, chỉ muốn bỏ số âm. Nếu khi gặp `-1` nó trả `false`, điều gì xảy ra?

**Đáp án:** Gatherer ngừng tích hợp, nên các số 2 và 3 không được xử lý. Để **lọc** số âm, không gọi `push` nhưng trả `true`.

### Bài 6. Vì sao cần finisher?

Gatherer nhóm các giá trị liên tiếp: `A,A,B,B,B,A`. Nếu chỉ phát một nhóm khi gặp giá trị khác, nhóm nào bị mất nếu không có finisher?

**Đáp án:** Nhóm cuối `A:1` không được phát vì không còn phần tử kế tiếp để đóng nhóm. Finisher phát phần tồn ở cuối Stream.

### Bài 7. Bài toán song song

Một Gatherer đánh số liên tiếp theo thời điểm nhận đầu vào; nguồn lại là `HashSet` không có encounter order được bảo đảm. `ofSequential` có tự xác định thứ tự thời gian không?

**Đáp án:** Không. `ofSequential` quy định cách tích hợp tuần tự, không tự sắp xếp. Cần nguồn có encounter order phù hợp hoặc `sorted(comparator)` theo thời gian và quy tắc phá hòa.

### Bài 8. Kiểm tra trạng thái dùng chung

Một Gatherer có `initializer` là `() -> SHARED`, trong đó `SHARED` là đối tượng mutable static. Vì sao điều này nguy hiểm?

**Đáp án:** Nhiều lần thực thi có thể chia sẻ cùng đối tượng, làm lẫn số đếm và dữ liệu. Nếu các pipeline chạy đồng thời còn có nguy cơ data race. Dùng `State::new` để tạo state riêng.

### Bài 9. Kiểm thử nguồn rỗng

Với Stream rỗng, `map` và `mapMulti` sẽ phát bao nhiêu phần tử? Một Gatherer có finisher có bắt buộc phát 0 phần tử không?

**Đáp án:** `map` và `mapMulti` không nhận phần tử đầu vào nào, nên không phát phần tử. **Gatherer có finisher** có thể được thiết kế để phát một giá trị mặc định hoặc báo cáo tổng kết khi hoàn tất, tùy hợp đồng; ví dụ `consecutiveRuns` không phát gì vì không có nhóm dở dang. Không được giả định mọi Gatherer đều xử lý nguồn rỗng giống `map`.

### Bài 10. Chọn công cụ cho báo cáo

Có 50.000 dòng giao dịch, yêu cầu tính số dòng, tổng tiền và tổng tiền theo SKU, nhưng **không** cần các mốc lũy kế. Có nên viết Gatherer tự quản một `HashMap` và chỉ phát kết quả ở cuối?

**Đáp án:** Không cần. Một collector có sẵn hoặc custom `Collector` là lựa chọn tự nhiên để trả báo cáo cuối. Gatherer chỉ đáng cân nhắc nếu cần các phép biến đổi trung gian, phát kết quả theo từng mốc hoặc tiếp tục pipeline với nhiều đầu ra.

## 13. Bài tập mở rộng: thống kê theo cửa sổ rồi lọc

**Đề bài:** Một cảm biến gửi dãy nhiệt độ có thứ tự. Cần chia thành các cửa sổ **ba mẫu liên tiếp**, tính trung bình từng cửa sổ, rồi chỉ giữ những cửa sổ có trung bình vượt ngưỡng.

Hướng xây dựng trên Java 24:

```java
List<Double> hotWindows = temperatures.stream()
        .gather(java.util.stream.Gatherers.windowFixed(3))
        .map(window -> window.stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElseThrow())
        .filter(avg -> avg > threshold)
        .toList();
```

Đây là đoạn minh họa giả định có `List<Double> temperatures` và `double threshold` được khai báo. Vì `Gatherers.windowFixed` phát các List cửa sổ, sau đó `map` ánh xạ **một cửa sổ thành một trung bình**; cuối cùng `filter` loại cửa sổ không vượt ngưỡng. Bài toán cho thấy **Gatherer không thay thế map hay filter**: chúng phối hợp trong cùng pipeline.

Nếu yêu cầu cửa sổ **trượt** thay vì cửa sổ không chồng lấn, hãy cân nhắc `Gatherers.windowSliding` với việc kiểm tra hợp đồng về độ dài cửa sổ và thứ tự đầu vào. Nếu chỉ cần trung bình toàn bộ chuỗi, `mapToDouble(...).average()` đơn giản hơn rất nhiều.

## 14. Checklist trước khi chọn API

1. **Nhu cầu cần một đầu ra hay nhiều đầu ra cho mỗi input?** Một đầu ra đơn giản thì ưu tiên `map`.
2. **Các đầu ra của một phần tử có thể tính độc lập không?** Nếu có, `mapMulti` hoặc `flatMap` thường đủ.
3. **Có cần giữ state giữa các input không?** Nếu có, xem xét Gatherer.
4. **Có phải phát phần dữ liệu còn lại khi nguồn kết thúc không?** Nếu có, thiết kế finisher hoặc dùng Gatherer chuẩn phù hợp.
5. **Cần một kết quả cuối hay một Stream kết quả để tiếp tục xử lý?** Kết quả cuối ưu tiên `collect`; Stream trung gian ưu tiên `gather`.
6. **Hợp đồng phiên bản JDK ra sao?** `map`/`collect` từ Java 8; `mapMulti` từ 16; `Gatherer` chính thức từ 24.
7. **Có thứ tự nghiệp vụ không?** Tổng lũy kế và nhóm liên tiếp cần encounter order được xác định.
8. **Có trạng thái mutable dùng chung không?** Tránh side effect trong `map`/`mapMulti`; tạo state mới cho Gatherer/Collector.
9. **Có yêu cầu ngắn mạch không?** Phân biệt “lọc một phần tử” với “dừng toàn bộ tích hợp”.
10. **Có cần tương thích xử lý song song không?** Kiểm tra combiner/hợp đồng collector hoặc tính tuần tự của Gatherer và chi phí giữ thứ tự.
11. **Có dữ liệu null, rỗng, số tiền tràn hoặc I/O cần đóng không?** Quy định chính sách trước khi viết pipeline.
12. **Có thể dùng API chuẩn đơn giản hơn không?** `Collectors.summarizingLong`, `groupingBy`, `Gatherers.scan`, `windowFixed` hoặc `windowSliding` có thể giải quyết bài toán.

**Kết luận:** `map` giải quyết **1:1**, `mapMulti` xử lý **0..n giá trị độc lập từ một đầu vào**, Gatherer mở rộng khả năng **biến đổi trung gian có trạng thái, dừng sớm và finisher**, còn Collector **tích lũy thành kết quả cuối**. Khác biệt cốt lõi không nằm ở việc cả bốn đều có lambda, mà ở **dòng dữ liệu đầu ra, vòng đời trạng thái và hợp đồng thực thi**. Chọn đúng công cụ giúp pipeline JAVA_STREAM_API ngắn gọn, chính xác và dễ kiểm soát thứ tự, hiệu năng cũng như tài nguyên khi nâng cấp JDK.
