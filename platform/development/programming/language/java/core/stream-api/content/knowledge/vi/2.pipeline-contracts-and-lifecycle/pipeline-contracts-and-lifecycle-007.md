# Hàm không trạng thái, tác dụng phụ và khả năng quan sát kết quả

## 1. Vì sao đây là một phần của hợp đồng Stream?

Java Stream API cho phép mô tả **cần tính ra điều gì** bằng một pipeline gồm nguồn dữ liệu, các phép biến đổi trung gian và phép toán kết thúc. Thư viện có quyền trì hoãn, kết hợp, thực thi song song hoặc bỏ qua những bước không cần thiết, miễn là vẫn bảo toàn kết quả mà hợp đồng Stream quy định. Vì vậy, code bên trong `filter`, `map`, `flatMap`, `peek` hay các hàm xử lý phần tử không nên ngầm phụ thuộc vào việc nó được gọi bao nhiêu lần, trên luồng nào hoặc theo thứ tự nào.

Đây là nội dung cốt lõi của chương **Hợp đồng và vòng đời pipeline** trong **JAVA_STREAM_API**: học cách xử lý dữ liệu khai báo bằng pipeline lazy, đồng thời biết ranh giới giữa kết quả của phép toán và tác dụng phụ có thể xảy ra khi chạy pipeline.

```text
Nguồn dữ liệu       Trung gian (lazy)                    Kết thúc (terminal)
List<Order>  ────► filter(...) ────► map(...) ─────► collect(...)
                         │               │                 │
                mô tả điều kiện   mô tả phép chiếu   kích hoạt xử lý,
                                                   tạo kết quả quan sát được
```

Ví dụ sau chỉ tạo pipeline; khi chưa có terminal operation, hàm `map` chưa cần chạy:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3, 4);

Stream<Integer> pipeline = numbers.stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10); // Mới mô tả pipeline, chưa xử lý phần tử.

List<Integer> result = pipeline.toList(); // [20, 40]; terminal kích hoạt xử lý.
```

Các ví dụ sử dụng Java 17+ (có `Stream.toList()`); mỗi Stream chỉ nên thực hiện **một** terminal operation. Sau terminal, Stream đã bị tiêu thụ, không được tái sử dụng để chạy terminal khác.

## 2. Phân biệt không trạng thái, không can thiệp và thuần hàm

Ba tính chất thường đi cùng nhau nhưng không đồng nghĩa:

| Tính chất | Ý nghĩa trong pipeline | Ví dụ |
| --- | --- | --- |
| **Stateless (không trạng thái)** | Kết quả xử lý một phần tử không phụ thuộc vào trạng thái có thể thay đổi do xử lý phần tử khác của cùng pipeline. | `n -> n * 2`; `s -> s.trim()` |
| **Non-interfering (không can thiệp)** | Hàm xử lý không sửa đổi nguồn dữ liệu đang được Stream duyệt, trừ những nguồn hỗ trợ sửa đổi đồng thời theo hợp đồng riêng. | Đọc `order.amount()` mà không thêm/xóa phần tử của danh sách nguồn. |
| **Pure (thuần hàm)** | Với cùng đầu vào và cùng ngữ cảnh bất biến, trả cùng kết quả và không gây tác dụng phụ quan sát được. | `n -> Math.abs(n)` với giá trị `int`. |

Tài liệu Stream yêu cầu các *behavioral parameters* (lambda/method reference truyền vào các operation) nhìn chung phải **không can thiệp** và **không trạng thái**. Một lambda không trạng thái vẫn có thể có tác dụng phụ, chẳng hạn `n -> { logger.info("{}", n); return n * 2; }`; do đó chỉ kiểm tra tính stateless là chưa đủ để dựa vào hành vi an toàn, dễ kiểm thử.

### 2.1. Lambda không trạng thái

```java
import java.util.List;
import java.util.Locale;

List<String> names = List.of(" An ", "Bình", "  ", "Chi");

List<String> normalized = names.stream()
    .map(String::trim)
    .filter(name -> !name.isBlank())
    .map(name -> name.toUpperCase(Locale.ROOT))
    .toList();

// [AN, BÌNH, CHI]
```

Mỗi phép biến đổi chỉ phụ thuộc vào phần tử hiện tại và hằng số `Locale.ROOT`. Một biến được capture cũng có thể an toàn **nếu nội dung được dùng là bất biến trong suốt lần thực thi**:

```java
int minLength = 3;
List<String> selected = names.stream()
    .map(String::trim)
    .filter(name -> name.length() >= minLength)
    .toList();
```

Java yêu cầu biến cục bộ được lambda capture phải `final` hoặc *effectively final*, nhưng quy tắc biên dịch này **không làm mọi đối tượng được capture trở nên bất biến**. Ví dụ, biến tham chiếu `Set` có thể không đổi trong khi nội dung `Set` liên tục bị sửa.

### 2.2. Lambda có trạng thái: một kết quả phụ thuộc phần tử trước

```java
import java.util.HashSet;
import java.util.Set;

Set<String> seen = new HashSet<>();

List<String> unique = names.stream()
    .map(String::trim)
    .filter(name -> seen.add(name)) // SAI CÁCH: phụ thuộc và thay đổi seen.
    .toList();
```

`seen.add(name)` vừa kiểm tra vừa sửa trạng thái được chia sẻ qua các lần gọi `filter`. Trên Stream tuần tự, kết quả có thể trông đúng trong một tình huống cụ thể, nhưng lambda không còn stateless. Chuyển sang `.parallel()` có thể tạo race condition vì `HashSet` không an toàn cho truy cập đồng thời. Việc dùng một tập hợp đồng bộ cũng không biến phép lọc thành hàm không trạng thái; thứ tự phần tử được nhận còn phụ thuộc lịch chạy.

Hãy giao phần loại bỏ trùng lặp cho operation có hợp đồng rõ ràng:

```java
List<String> unique = names.stream()
    .map(String::trim)
    .distinct()
    .toList();
```

**Lưu ý:** `distinct()`, `sorted()`, `limit()` và `skip()` là những *stateful intermediate operations*: bản thân thư viện có thể cần nhớ phần tử đã gặp, giữ bộ đệm hoặc theo dõi vị trí. Điều này **không mâu thuẫn** với yêu cầu lambda do người lập trình truyền vào phải stateless. Trạng thái được quản lý bên trong operation theo đúng hợp đồng; một số operation này có chi phí bộ nhớ hoặc giảm hiệu quả khi chạy song song, nhất là khi cần giữ encounter order.

### 2.3. Không can thiệp vào nguồn

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// KHÔNG LÀM: sửa nguồn khi chính Stream đang duyệt nó.
source.stream()
    .filter(n -> {
        if (n == 2) source.add(4);
        return n % 2 == 0;
    })
    .forEach(System.out::println);
```

Kết quả có thể là `ConcurrentModificationException`, hành vi bất thường hoặc lỗi khác tùy nguồn và thời điểm; **không được dựa vào việc ngoại lệ luôn xuất hiện**. Nếu cần bổ sung hoặc loại bỏ phần tử, hãy tạo danh sách kết quả rồi cập nhật nguồn sau khi pipeline hoàn tất, hoặc dùng cấu trúc/thuật toán có hợp đồng concurrency riêng.

## 3. Tác dụng phụ: giá trị trả về khác với điều xảy ra bên ngoài

**Tác dụng phụ (side effect)** là thay đổi trạng thái hoặc tương tác quan sát được ngoài giá trị mà lambda trả về: thêm phần tử vào danh sách bên ngoài, tăng bộ đếm, ghi log, gửi request, cập nhật cơ sở dữ liệu, ghi file hoặc thay đổi object dùng chung.

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> output = new ArrayList<>();

List<Integer> doubled = List.of(1, 2, 3).stream()
    .map(n -> {
        output.add(n);        // Tác dụng phụ lên trạng thái bên ngoài.
        return n * 2;         // Kết quả của phép biến đổi.
    })
    .toList();

// doubled là kết quả khai báo cần lấy: [2, 4, 6].
// Không nên thiết kế thuật toán dựa trên output.
```

Ngay cả khi ví dụ tuần tự có thể tạo `output = [1, 2, 3]`, kết quả phụ này không nằm trong hợp đồng của `map`. Khi áp dụng tối ưu hóa, short-circuit hoặc song song hóa, ta không nên suy luận về số lần gọi, thứ tự và thread thực hiện callback chỉ từ kết quả cuối.

Tác dụng phụ **không bị cấm tuyệt đối**. Ví dụ `forEach` là terminal operation dùng để thực thi hành động đối với phần tử. Vấn đề là phải đặt tác dụng phụ tại nơi thật sự cần chúng, hiểu giới hạn về thứ tự/thread, và không sử dụng chúng như một phần ngầm định của phép tính mà Stream được phép tối ưu.

### 3.1. `count()` có thể không chạy `map()` hoặc `peek()`

```java
import java.util.List;

List<String> items = List.of("a", "b", "c");

long count = items.stream()
    .map(item -> {
        System.out.println("map: " + item);
        return item.toUpperCase();
    })
    .count();

// count == 3, nhưng không được kỳ vọng 3 dòng "map".
```

Với nguồn có kích thước đã biết như `List`, và các operation không làm thay đổi số phần tử như `map`, Stream có thể tính `count()` trực tiếp từ kích thước nguồn mà **không duyệt các phần tử**. Do vậy `map` (và `peek` trong trường hợp tương tự) có thể không chạy. Đây là tối ưu hóa hợp lệ, không phải lỗi của JDK. Với `filter`, thư viện thường cần xét điều kiện để biết còn bao nhiêu phần tử, vì `filter` có thể thay đổi số lượng.

Không dùng `map`, `filter` hoặc `peek` để ép thực hiện một công việc bên ngoài rồi chỉ gọi `count()` để kích hoạt nó. Tốt hơn là xác định rõ cần **đếm**, **biến đổi**, hay **thực hiện hành động** và chọn terminal tương ứng.

### 3.2. Short-circuit chỉ cần xử lý một phần nguồn

```java
boolean hasNegative = List.of(4, 8, -3, 10, 12).stream()
    .anyMatch(n -> n < 0);

// true; không cần xét hết các phần tử sau khi đã tìm thấy phần tử phù hợp.
```

`anyMatch`, `allMatch`, `noneMatch`, `findFirst`, `findAny`, các phép toán kết hợp `limit`... có thể kết thúc khi đã đủ thông tin. Trong pipeline song song, một số tác vụ đang chạy vẫn có thể xử lý thêm phần tử trước khi nhận tín hiệu dừng. Vì thế không có lời hứa rằng một callback sẽ chạy với **đúng N phần tử** chỉ vì ta quan sát một kết quả ở lần chạy trước.

## 4. Khả năng quan sát kết quả: điều gì được bảo đảm?

Trong Stream, nên phân biệt ba lớp quan sát:

1. **Giá trị terminal trả về**: ví dụ `List` từ `toList()`, `Map` từ `collect(...)`, `long` từ `count()`; đây là đầu ra để kiểm tra.
2. **Tác dụng phụ có chủ đích của terminal**: ví dụ `forEach(System.out::println)`; việc hành động diễn ra là mục đích của operation, nhưng thứ tự và thread vẫn phụ thuộc hợp đồng cụ thể.
3. **Tác dụng phụ nằm bên trong bước trung gian**: log, tăng biến đếm, thay đổi state trong `map`/`filter`/`peek`; có thể bị tối ưu bỏ qua hoặc thực thi ở luồng/thứ tự khác nên không phải bằng chứng đầy đủ cho việc phần tử đã được xử lý thế nào.

| Pipeline | Có thể khẳng định | Không được suy ra |
| --- | --- | --- |
| `list.stream().map(f).toList()` | Danh sách trả về chứa kết quả phép biến đổi theo encounter order nếu nguồn có thứ tự. | Mọi side effect bên trong `f` đều an toàn hoặc có thể dùng để đồng bộ. |
| `list.stream().map(f).count()` | Số phần tử theo hợp đồng `count()`. | `f` đã được gọi đúng một lần cho mọi phần tử. |
| `stream.anyMatch(p)` | Có ít nhất một phần tử thỏa `p` nếu trả `true`. | `p` đã xét toàn bộ nguồn. |
| `stream.parallel().forEach(action)` | `action` được thực hiện cho các phần tử mà terminal duyệt theo hợp đồng. | Thứ tự tương ứng thứ tự nguồn, hoặc các action chạy trên cùng một thread. |
| `stream.forEachOrdered(action)` | Nếu Stream có encounter order, action được thực hiện theo thứ tự đó. | Mọi action đều chạy trên cùng một thread hoặc chi phí tương đương `forEach`. |

`forEachOrdered` còn bảo đảm việc thực hiện action trên một phần tử *happens-before* action trên phần tử tiếp theo. Nó hữu ích khi thật sự cần thứ tự, nhưng có thể hạn chế khả năng thực thi song song. `forEach` không cam kết giữ encounter order, đặc biệt khi dùng parallel stream.

### 4.1. `peek()` để quan sát tạm thời, không phải cơ chế audit

```java
List<Integer> result = List.of(1, 2, 3, 4, 5).stream()
    .filter(n -> n % 2 == 0)
    .peek(n -> System.out.println("sau filter: " + n))
    .map(n -> n * n)
    .toList();

// result == [4, 16]. peek có ích khi kiểm tra luồng dữ liệu trong lúc debug.
```

`peek` là phép toán trung gian, chỉ có cơ hội chạy khi phần tử thực sự đi qua đoạn pipeline đó. Nó không bảo đảm một lần log cho mỗi phần tử nguồn, không bảo đảm trật tự log trên parallel stream và có thể bị loại khỏi quá trình thực thi khi tối ưu hóa không làm đổi kết quả terminal. Vì thế `peek` không phù hợp để ghi sự kiện nghiệp vụ bắt buộc, kiểm toán, tính phí, cập nhật tồn kho hay thống kê chính thức.

Nếu sự kiện cần ghi **chính xác theo những phần tử đã chọn**, hãy xác định chúng bằng phép tính thuần trước, sau đó thực hiện bước ghi có chủ đích, cùng chiến lược xử lý lỗi/nhắc lại phù hợp với hệ thống:

```java
List<Integer> selected = List.of(1, 2, 3, 4, 5).stream()
    .filter(n -> n % 2 == 0)
    .toList();

selected.forEach(n -> System.out.println("Đã chọn: " + n));
```

Trong hệ thống thực, quy trình ghi sự kiện còn cần quản lý giao dịch và idempotency; Stream API không tự cung cấp các bảo đảm đó.

## 5. Thay mutation bên ngoài bằng kết quả của terminal

Với phần lớn bài toán, cách xử lý dễ hiểu và an toàn là dùng `filter` để chọn, `map` để biến đổi, `reduce` để gộp bằng phép toán kết hợp, hoặc `collect` để gom phần tử thành cấu trúc kết quả.

### 5.1. Tránh dùng `forEach` để tự đắp kết quả

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> bad = new ArrayList<>();
numbers.stream()
    .filter(n -> n % 2 == 0)
    .forEach(n -> bad.add(n * n)); // Gắn việc tạo kết quả với state ngoài.

List<Integer> good = numbers.stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .toList(); // [4, 16]
```

Ở luồng tuần tự, `bad` có thể hoạt động nhưng làm chương trình phụ thuộc vào mutation. Nếu chuyển sang `parallelStream()`, `ArrayList.add` đồng thời có thể gây race và hỏng kết quả. `good` thể hiện mục tiêu ngay trong pipeline; Stream tự quản lý việc gom kết quả. `Stream.toList()` trả về danh sách không sửa đổi được; nếu cần một danh sách có thể thay đổi, có thể dùng `collect(Collectors.toCollection(ArrayList::new))`.

### 5.2. `reduce` cho phép gộp, `collect` cho tích lũy có quản lý

```java
import java.util.List;

long sum = List.of(10L, 20L, 30L).stream()
    .reduce(0L, Long::sum); // 60
```

Hàm dùng với `reduce` cần tuân theo tính kết hợp (*associativity*) và giá trị khởi tạo phù hợp. Không dùng một `ArrayList` chia sẻ làm identity của `reduce` rồi thêm phần tử vào đó: khi pipeline song song, các nhánh cần có khả năng kết hợp kết quả đúng đắn mà không phụ thuộc mutation chung.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<Integer> collected = List.of(1, 2, 3, 4).parallelStream()
    .collect(Collector.of(
        ArrayList::new,                    // supplier: tạo container tích lũy mới
        ArrayList::add,                    // accumulator: thêm vào container của nhánh
        (left, right) -> {                 // combiner: gộp kết quả hai nhánh
            left.addAll(right);
            return left;
        }
    ));

// [1, 2, 3, 4] với nguồn có encounter order này.
```

Đây là mutation **bên trong cơ chế `Collector`**, được thiết kế qua `supplier`, `accumulator` và `combiner`, thay vì các lambda cùng ghi vào một danh sách ngoài. Một collector có thể dùng container mutable một cách an toàn trong parallel stream nếu tuân thủ các ràng buộc identity, associativity, cách phân tách/kết hợp và các characteristics khai báo. Khi không cần logic riêng, ưu tiên collector có sẵn như `toList`, `groupingBy`, `counting`, `summingLong`.

### 5.3. Ví dụ nghiệp vụ: tính doanh thu theo khách hàng

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String customer, long amount, boolean paid) {}

List<Order> orders = List.of(
    new Order("An", 100, true),
    new Order("Bình", 80, true),
    new Order("An", 120, true),
    new Order("An", 500, false),
    new Order("Chi", -20, true)
);

Map<String, Long> revenueByCustomer = orders.stream()
    .filter(Order::paid)
    .filter(order -> order.amount() > 0)
    .collect(Collectors.groupingBy(
        Order::customer,
        Collectors.summingLong(Order::amount)
    ));

// {An=220, Bình=80} (Map không mặc định bảo đảm thứ tự duyệt).
```

Ở đây không có bộ đếm/doanh thu mutable bên ngoài để `filter` hay `map` cập nhật. Kết quả được biểu diễn bằng `Map<String, Long>`, nên ta có thể kiểm tra trực tiếp theo key, dùng lại cho xử lý tiếp theo hoặc so sánh với kết quả mong đợi. Nếu cần collector tùy chỉnh, vẫn giữ nguyên nguyên tắc: không chia sẻ container tích lũy tùy ý giữa các nhánh song song.

## 6. Thực thi song song làm lộ rõ những giả định sai

`parallel()` cho phép Stream phân chia công việc, nhưng **không tự biến callback có state thành thread-safe** và cũng không cam kết chúng chạy trên thread cụ thể. Chẳng hạn:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

IntStream.range(0, 100_000)
    .parallel()
    .forEach(shared::add); // KHÔNG AN TOÀN: ArrayList bị ghi đồng thời.

// Không thể tin shared.size() luôn là 100_000.
```

Sửa bằng cách để terminal tạo kết quả:

```java
List<Integer> values = IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .toList();

// values.size() == 100_000; giữ encounter order của IntStream.range.
```

Đổi `shared` sang `Collections.synchronizedList(...)` chỉ xử lý một phần vấn đề an toàn truy cập; nó không khiến thứ tự hoàn thành các lời gọi `forEach` tương ứng với thứ tự nguồn, và vẫn buộc các worker cạnh tranh khóa. Tương tự, dùng `AtomicInteger` cho bộ đếm chỉ tránh mất cập nhật đồng thời, **không** bảo đảm số lần callback chạy khi pipeline có short-circuit hoặc tối ưu hóa bỏ qua bước trung gian.

Nếu bắt buộc thực hiện hành động theo encounter order:

```java
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::println); // In 1, 2, 3, 4, 5 theo thứ tự.
```

Đừng mặc định parallel sẽ nhanh hơn: tác vụ nhỏ, operation có trạng thái, đòi hỏi encounter order, I/O hoặc tranh chấp tài nguyên có thể khiến chi phí chia nhánh/kết hợp vượt quá lợi ích. Trước khi song song hóa, cần chứng minh phép tính độc lập, collector phù hợp và đo hiệu năng với khối lượng dữ liệu thật.

## 7. Hệ quả đối với vòng đời, tài nguyên và kiểm thử

**Vòng đời.** Intermediate operations là lazy; terminal operation kích hoạt việc xử lý nhưng có thể kết thúc sớm hoặc bỏ qua một số stage nhờ tối ưu hóa. Khi đã tiêu thụ, Stream không tái sử dụng được. Một số nguồn I/O như `Files.lines` sở hữu tài nguyên và cần đóng Stream bằng `try-with-resources`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;
import java.util.List;
import java.util.stream.Stream;

static List<String> nonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.map(String::trim)
            .filter(line -> !line.isEmpty())
            .toList();
    }
}
```

**Kiểm thử.** Thay vì dùng số dòng log hoặc giá trị biến ngoài để chứng minh một stage chạy, hãy so sánh kết quả terminal:

```java
List<Integer> actual = List.of(1, 2, 3, 4).stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .toList();

if (!actual.equals(List.of(4, 16))) {
    throw new AssertionError("Unexpected result: " + actual);
}
```

Với pipeline có yếu tố ngẫu nhiên, thời gian, I/O hoặc cập nhật trạng thái ngoài, hãy tách logic tính toán thành hàm có thể kiểm thử độc lập; quản lý side effect ở lớp thực thi tương ứng. Nếu yêu cầu quan trọng là xử lý mỗi sự kiện đúng một lần, lưu bền và khôi phục khi lỗi, cần thiết kế riêng các bảo đảm giao dịch/idempotency ở tầng ứng dụng.

### Bảng tự rà soát khi viết Stream

| Câu hỏi | Dấu hiệu nên sửa |
| --- | --- |
| Lambda có đọc/ghi biến mutable dùng chung giữa các phần tử không? | `seen.add(...)`, `counter++`, `result.add(...)` trong `map`/`filter`. |
| Lambda có sửa nguồn đang được duyệt không? | `source.add(...)`, `source.remove(...)` trong callback. |
| Có đang dựa vào việc stage trung gian chắc chắn chạy không? | Ghi log bắt buộc trong `peek`, xử lý nghiệp vụ trong `map` rồi chỉ gọi `count`. |
| Có đang dựa vào thứ tự hoặc thread callback không? | `parallel().forEach(...)` để tạo danh sách có thứ tự hay cập nhật state không đồng bộ. |
| Có thể biểu diễn yêu cầu bằng giá trị trả về không? | Dùng `map` + `toList`, `reduce`, `groupingBy`, `summingLong` thay mutation bên ngoài. |
| Có quản lý vòng đời nguồn/tài nguyên không? | Stream từ file chưa đóng, hoặc cố tái sử dụng Stream sau terminal. |

## 8. Tự kiểm tra hiểu biết

1. Một pipeline gọi `.map(x -> { log(x); return x; }).count()` trên `List` có buộc ghi log cho từng phần tử không? **Không**: `count` có thể biết trước kích thước và bỏ qua `map`.
2. Vì sao `filter(x -> seen.add(x))` có thể chạy "đúng" tuần tự mà vẫn sai hợp đồng? **Vì lambda phụ thuộc vào và thay đổi trạng thái chia sẻ giữa các lần gọi**; kết quả phụ thuộc thứ tự xử lý và không an toàn khi song song.
3. `distinct()` có state, vậy có vi phạm yêu cầu stateless không? **Không**: đó là stateful operation do Stream quản lý; điều cần tránh là tự đưa state mutable giữa các lần gọi lambda.
4. Muốn gom danh sách từ parallel stream nên dùng `forEach(shared::add)` hay `collect`/`toList`? **Dùng terminal trả kết quả** để Stream quản lý quá trình tích lũy và kết hợp.
5. `forEachOrdered` có đồng nghĩa callback luôn chạy trên cùng một thread không? **Không**: nó bảo đảm encounter order khi có và quan hệ happens-before giữa các action liên tiếp, không bảo đảm thread cố định.

**Nguyên tắc áp dụng:** hãy coi kết quả terminal là hợp đồng chính của pipeline, giữ lambda không trạng thái và không can thiệp vào nguồn, dùng collector để gom dữ liệu, và đưa side effect bắt buộc vào một bước thực thi được kiểm soát rõ ràng. Khi đó pipeline vẫn dễ hiểu nếu JDK tối ưu khác đi hoặc chương trình chuyển từ tuần tự sang song song.
