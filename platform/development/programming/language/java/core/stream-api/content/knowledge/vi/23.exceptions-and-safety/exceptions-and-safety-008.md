# Nhận diện thao tác nguy hiểm khi xử lý song song

Java Stream API cho phép chuyển một pipeline tuần tự thành pipeline có khả năng xử lý song song bằng `parallel()` hoặc `parallelStream()`. Cú pháp ngắn không đồng nghĩa mọi phép biến đổi đều **an toàn khi chạy đồng thời**. Một lambda ghi vào `ArrayList` dùng chung có thể mất dữ liệu; một phép `reduce` không kết hợp được có thể cho kết quả khác tuần tự; một thao tác truy cập tệp, kết nối hoặc giao dịch có thể bị thực thi ở luồng không mong muốn. Ngay cả khi kết quả đúng, chi phí chia việc, đồng bộ hoặc giữ thứ tự cũng có thể khiến parallel Stream chậm hơn.

Bài thuộc chương **Ngoại lệ và tính an toàn** của mô-đun **JAVA_STREAM_API**. Mục tiêu là **nhận diện** các thao tác nguy hiểm từ cấu trúc pipeline, giải thích vì sao chúng nguy hiểm, sửa bằng cách sử dụng `filter`, `map`, `reduce`, `collect`, collector phù hợp hoặc một giải pháp tuần tự rõ ràng, và kiểm thử các bất biến về kết quả. Bài cũng liên hệ đến `Spliterator`, trạng thái tích lũy của collector, Stream Gatherers, ngoại lệ, tài nguyên và hiệu năng.

Các ví dụ cốt lõi sử dụng **Java 17+**. Phần liên quan đến `Stream.gather` và custom Gatherer cần **Java 24+**, khi Stream Gatherers đã trở thành API chính thức.

> **Nguyên tắc nền tảng:** Song song hóa không tự biến code sai thành code đúng, và thread-safe không đồng nghĩa với đúng nghiệp vụ. Hãy xác định tính đúng của phép toán **trước** khi đo lợi ích hiệu năng.

## 1. Parallel Stream thực sự thay đổi điều gì?

`parallelStream()` tạo Stream với chế độ thực thi song song; `parallel()` đánh dấu pipeline chuyển sang chế độ song song. Khi thực thi terminal operation, framework **có thể** chia nguồn thành các phần và xử lý trên nhiều tác vụ.

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5);

long sequential = values.stream()
    .filter(n -> n % 2 == 0)
    .mapToLong(n -> (long) n * n)
    .sum();

long parallel = values.parallelStream()
    .filter(n -> n % 2 == 0)
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(sequential); // 20
System.out.println(parallel);   // 20
```

Ở đây hai pipeline cùng tính tổng bình phương các số chẵn. `filter` và `mapToLong` không cần sửa dữ liệu bên ngoài; phép cộng số nguyên với giá trị nhỏ được chọn bảo đảm không tràn. Do đó có thể so sánh hai chế độ thực thi trên cùng kết quả nghiệp vụ.

Những điều **không được mặc định** khi chuyển sang song song:

- Thứ tự **gọi lambda**, `peek` hoặc `forEach` sẽ giống tuần tự.
- Mỗi phần tử luôn được xử lý trên một thread cụ thể.
- Tác vụ có thể dùng chung một biến mutable bên ngoài mà không cần đồng bộ.
- Tổng hợp có trạng thái sẽ tự được chia/gộp đúng.
- `findAny`, `limit` trên nguồn unordered hoặc phép có side effect sẽ có cùng diễn tiến thực thi.
- `parallel()` chắc chắn sử dụng nhiều CPU hơn theo cách đem lại lợi ích.

### 1.1. Phân biệt thứ tự kết quả và thứ tự thực thi

Một nguồn `List` có **encounter order**. Một pipeline song song vẫn có thể bảo toàn **thứ tự kết quả** nếu phép toán yêu cầu, như `toList()` trên ordered Stream:

```java
List<Integer> doubled = values.parallelStream()
    .map(n -> n * 2)
    .toList();

System.out.println(doubled); // [2, 4, 6, 8, 10]
```

Điều này **không có nghĩa** các lời gọi `map` xảy ra theo thứ tự 1 → 2 → 3 → 4 → 5, hoặc cùng thread. Framework có thể tính các phần ở những thời điểm khác nhau rồi ghép kết quả theo encounter order.

## 2. Ba tiêu chí nhận diện thao tác an toàn

Một behavioral parameter như `Predicate`, `Function`, `Consumer` hoặc accumulator trong Stream cần được xem xét theo **ba trục**:

| Trục | Câu hỏi | Dấu hiệu nguy hiểm |
| --- | --- | --- |
| **Non-interference** | Lambda có sửa nguồn đang được duyệt không? | `source.add(...)` hoặc `source.remove(...)` trong `filter` |
| **Stateless behavior** | Kết quả có phụ thuộc trạng thái mutable thay đổi ngoài lambda không? | Bộ đếm, cờ, danh sách hoặc vị trí hiện hành dùng chung |
| **Hợp đồng phép tổng hợp** | Identity, accumulator, combiner có tương thích và kết hợp đúng không? | Dùng phép trừ làm reduction; dùng cùng container mutable làm identity |

Song song còn đòi hỏi xem **thread safety** của mọi phụ thuộc có trạng thái: formatter mutable, cache, repository, transaction context, bộ ghi log tùy chỉnh và các đối tượng mà lambda gọi vào.

### 2.1. Hai lớp “đúng” cần tách biệt

- **Đúng về dữ liệu:** kết quả đúng điều kiện lọc, đúng số lượng, đúng thứ tự khi nghiệp vụ yêu cầu và không mất phần tử.
- **Đúng về điều phối/tài nguyên:** không data race, không sửa nguồn trái hợp đồng, không rò rỉ tệp, không dùng transaction context sai thread, không để công việc tiếp tục gây side effect ngoài ý muốn.

Một chương trình có thể không ném ngoại lệ và vẫn sai cả hai lớp.

## 3. Dấu hiệu đỏ số 1: cập nhật `ArrayList` dùng chung trong `forEach`

Đây là lỗi kinh điển:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

IntStream.range(0, 100_000)
    .parallel()
    .forEach(shared::add); // NGUY HIỂM.
```

`ArrayList.add` thay đổi mảng lưu trữ và bộ đếm kích thước mà không có cơ chế đồng bộ cho nhiều luồng ghi đồng thời. Có thể gặp mất phần tử, phần tử không nhất quán, dữ liệu sai hoặc ngoại lệ; **không có bảo đảm** lỗi sẽ biểu hiện ở mọi lần chạy.

Bản sửa:

```java
List<Integer> result = IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .toList();

System.out.println(result.size()); // 100000
```

Khi dùng terminal operation `toList()`, framework chịu trách nhiệm xây kết quả và bảo toàn encounter order của nguồn ordered.

### 3.1. Vì sao `Collections.synchronizedList` chưa phải lời giải tổng quát?

Có thể dùng:

```java
List<Integer> synchronizedResult =
    java.util.Collections.synchronizedList(new ArrayList<>());

IntStream.range(0, 100_000)
    .parallel()
    .forEach(synchronizedResult::add);
```

Các lần `add` đơn lẻ được bảo vệ theo hợp đồng của wrapper. Tuy nhiên:

- Thứ tự các lần ghi **không** nhất thiết là encounter order.
- Ghi vào một lock chung có thể gây tranh chấp, làm giảm lợi ích song song.
- Các thao tác ghép nhiều bước như “kiểm tra rồi thêm” cần xem lại tính nguyên tử.
- Nếu không thực sự cần side effect, `collect` hoặc `toList` diễn đạt ý định tốt hơn.

**Quy tắc:** Thấy `parallel().forEach(collection::add)` hoặc `parallel().peek(collection::add)` thì phải kiểm tra ngay; đừng chỉ thêm `synchronized` rồi xem như đã giải quyết mọi yêu cầu.

## 4. Dấu hiệu đỏ số 2: bộ đếm mutable dùng chung

Ví dụ sai:

```java
int[] counter = {0};

long count = IntStream.range(0, 100_000)
    .parallel()
    .filter(n -> {
        if (n % 2 == 0) {
            counter[0]++; // Data race.
            return true;
        }
        return false;
    })
    .count();
```

Lệnh `counter[0]++` là chuỗi đọc–tăng–ghi, không phải phép cập nhật nguyên tử. Nhiều thread có thể đọc cùng giá trị rồi ghi đè kết quả của nhau.

Đoạn này còn tạo **tác dụng phụ trong predicate**, làm hành vi phụ thuộc cách framework gọi predicate; một số pipeline có thể tối ưu bớt callback khi kết quả terminal vẫn giữ nguyên ngữ nghĩa.

Cách đúng để đếm:

```java
long evenCount = IntStream.range(0, 100_000)
    .parallel()
    .filter(n -> n % 2 == 0)
    .count();

System.out.println(evenCount); // 50000
```

### 4.1. `AtomicInteger` sửa race nhưng không sửa ý định sai

```java
java.util.concurrent.atomic.AtomicInteger counter =
    new java.util.concurrent.atomic.AtomicInteger();

IntStream.range(0, 100_000)
    .parallel()
    .forEach(n -> counter.incrementAndGet());

System.out.println(counter.get()); // 100000 nếu duyệt toàn bộ thành công
```

`AtomicInteger` giúp tăng nguyên tử, nhưng:

- Không bảo đảm thứ tự thực thi các phần tử.
- Không biến một chuỗi nhiều thao tác trên các object khác thành transaction.
- Có thể làm mọi worker tranh chấp cùng một biến.
- Nếu pipeline short-circuit hoặc bị tối ưu, số callback không phải mặc nhiên là số phần tử nguồn.
- Với việc **đếm kết quả**, `count()` thường gọn và đúng hơn.

`LongAdder` có thể phù hợp cho counter cập nhật đồng thời trong những thiết kế riêng, nhưng `sum()` trong lúc các luồng còn cập nhật không phải snapshot nguyên tử của tất cả cập nhật. Không dùng `LongAdder` để “sửa” một phép đếm vốn nên được tính bằng terminal operation.

## 5. Dấu hiệu đỏ số 3: `peek` có side effect bắt buộc

`peek` thường được dùng để debug:

```java
List<Integer> result = List.of(1, 2, 3, 4)
    .parallelStream()
    .peek(n -> System.out.println("saw " + n))
    .map(n -> n * 2)
    .toList();
```

Log có thể xen kẽ, không theo thứ tự List. Điều đó không chứng minh kết quả sai.

Nguy hiểm hơn là dùng `peek` để ghi nghiệp vụ:

```java
orders.parallelStream()
    .peek(order -> repository.markProcessed(order.id()))
    .count(); // KHÔNG nên dùng peek để bảo đảm side effect.
```

Theo hợp đồng Stream, những side effect từ behavioral parameters **không được bảo đảm thực thi** trong mọi tình huống tối ưu; riêng `count()` trên nguồn có kích thước biết trước có thể không cần duyệt toàn bộ giai đoạn trung gian. Vì vậy số dòng được đánh dấu trong repository có thể không phù hợp ý định.

**Đúng về thiết kế:** dùng Stream để tính danh sách ID/bản ghi cần cập nhật; sau đó thực thi một bước ghi riêng với hợp đồng retry, transaction và idempotency được kiểm soát. Nếu việc cập nhật là nhiệm vụ chính, một vòng lặp tuần tự tường minh đôi khi đáng tin và dễ vận hành hơn.

### 5.1. Những dấu hiệu cần review

- `peek(System.out::println)`: phù hợp để quan sát tạm thời, không đo số lần gọi.
- `peek(cache::put)`: nguy cơ race và side effect bị bỏ.
- `peek(metrics::increment)`: số lần chạy callback không phải KPI nghiệp vụ.
- `map(x -> { save(x); return x; })`: `map` được biến thành nơi làm I/O có side effect; phải xác định hợp đồng thực thi rõ ràng.

## 6. Dấu hiệu đỏ số 4: sửa collection nguồn ngay khi duyệt

Ví dụ nguy hiểm ở cả tuần tự lẫn song song, đặc biệt khi song song:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.parallelStream()
    .filter(n -> {
        if (n % 2 == 0) {
            source.remove(n); // Sửa nguồn đang được duyệt.
        }
        return true;
    })
    .toList();
```

`ArrayList` không được thiết kế để sửa cấu trúc đồng thời với việc duyệt bằng Spliterator thông thường. Code có thể ném `ConcurrentModificationException`, đọc thiếu dữ liệu hoặc cho kết quả không mong muốn. **Fail-fast là cơ chế phát hiện theo nỗ lực tốt nhất, không phải bảo đảm phát hiện mọi race.**

Thay vào đó, tạo collection mới:

```java
List<Integer> odd = source.parallelStream()
    .filter(n -> n % 2 != 0)
    .toList();

System.out.println(odd); // [1, 3]
```

Nếu nghiệp vụ cần thay đổi chính `source`, hãy thực hiện ở một bước được kiểm soát **sau khi đã kết thúc việc duyệt**, hoặc dùng phương thức collection phù hợp trong một luồng khi thiết kế không đòi parallel Stream.

### 6.1. `Spliterator.CONCURRENT` không cho phép mọi side effect

Một số nguồn concurrent có Spliterator hỗ trợ cập nhật nguồn đồng thời theo **hợp đồng riêng của nguồn**. Đặc tính `Spliterator.CONCURRENT` không đồng nghĩa:

- Lambda ghi vào một `ArrayList` khác được an toàn.
- Encounter order được giữ khi nguồn biến đổi.
- Snapshot của nguồn luôn cố định.
- Mọi collector downstream trở thành concurrent.

Phải xem đúng đặc tính `ORDERED`, `SIZED`, `CONCURRENT`, `IMMUTABLE` và hành vi của nguồn, không suy diễn từ từ khóa “parallel”.

## 7. Dấu hiệu đỏ số 5: phụ thuộc vào thứ tự gọi lambda

Ví dụ code có trạng thái:

```java
java.util.concurrent.atomic.AtomicInteger index =
    new java.util.concurrent.atomic.AtomicInteger();

List<String> labels = List.of("A", "B", "C", "D")
    .parallelStream()
    .map(s -> index.getAndIncrement() + ":" + s)
    .toList();
```

`AtomicInteger` giúp mỗi lần tăng trả về một số riêng, nhưng **không gắn số đó với vị trí nguồn**. Kết quả có thể là `["2:A", "0:B", "3:C", "1:D"]` hoặc một thứ tự số khác; thứ tự danh sách đầu ra vẫn có thể là A, B, C, D.

Muốn đánh số **theo vị trí trong một List**:

```java
List<String> items = List.of("A", "B", "C", "D");

List<String> indexed = IntStream.range(0, items.size())
    .parallel()
    .mapToObj(i -> i + ":" + items.get(i))
    .toList();

System.out.println(indexed); // [0:A, 1:B, 2:C, 3:D]
```

Điều kiện áp dụng: `items` phải ổn định trong thời gian duyệt và hỗ trợ truy cập theo chỉ số phù hợp; với `ArrayList` hoặc `List.of` thì cách làm này trực tiếp. Không dùng random access lặp lại trên `LinkedList` rất lớn mà mặc định hiệu năng tốt.

### 7.1. `forEach` khác `forEachOrdered`

```java
List.of(1, 2, 3, 4)
    .parallelStream()
    .forEach(System.out::println); // Thứ tự in không được bảo đảm.

List.of(1, 2, 3, 4)
    .parallelStream()
    .forEachOrdered(System.out::println); // Theo encounter order.
```

`forEachOrdered` bảo đảm hành động của các phần tử theo encounter order trên nguồn ordered; điều này có thể yêu cầu điều phối và làm mất lợi ích song song ở terminal stage.

**Không suy rằng `forEachOrdered` biến mọi mutable shared state thành an toàn** trong môi trường rộng hơn: dữ liệu vẫn có thể được code khác truy cập đồng thời, và những side effect ở `map`/`peek` upstream vẫn có thể xảy ra ở các thread khác.

## 8. Dấu hiệu đỏ số 6: dùng phép `reduce` không kết hợp được

Parallel reduction có thể chia nguồn thành các nhóm, tính kết quả từng phần, rồi gộp. Vì thế phép toán phải có **identity đúng** và **tính kết hợp (*associativity*)** trong miền dữ liệu mong muốn.

Phép trừ là ví dụ không kết hợp:

```text
(10 - 4) - 2 = 4
10 - (4 - 2) = 8
```

Đoạn sau là thiết kế nguy hiểm:

```java
int result = List.of(10, 4, 2)
    .parallelStream()
    .reduce(0, (a, b) -> a - b);

// Không dự đoán một giá trị cố định hoặc đòi giống tuần tự.
```

`0` không phải identity hai phía của phép trừ, và phép trừ không kết hợp. Việc kết quả tình cờ giống nhau ở một lần chạy không chứng minh tính đúng.

Dùng phép toán có hợp đồng phù hợp, chẳng hạn cộng số nguyên khi không tràn:

```java
int total = List.of(10, 4, 2)
    .parallelStream()
    .reduce(0, Integer::sum);

System.out.println(total); // 16
```

### 8.1. Identity phải trung lập theo hợp đồng

Ví dụ:

```java
int wrong = List.of(1, 2, 3)
    .parallelStream()
    .reduce(10, Integer::sum); // 10 không trung lập.
```

Trong xử lý song song, identity có thể được dùng ở các phần tích lũy; không được xem `10` là một “giá trị cộng thêm đúng một lần” rồi suy ra kết quả `16`.

Muốn cộng thêm 10 vào **tổng cuối**, hãy đặt nó ngoài phép reduce:

```java
int correct = 10 + List.of(1, 2, 3)
    .parallelStream()
    .reduce(0, Integer::sum);

System.out.println(correct); // 16
```

### 8.2. Associativity không đồng nghĩa commutativity

Phép nối chuỗi có thể kết hợp về mặt toán học:

```text
("A" + "B") + "C" = "A" + ("B" + "C")
```

nhưng không giao hoán:

```text
"A" + "B" != "B" + "A"
```

Với ordered Stream, framework cần tôn trọng hợp đồng encounter order của phép giảm phù hợp; với unordered Stream, không được đòi mọi phép tổng hợp nhạy thứ tự tạo cùng chuỗi theo một thứ tự nghiệp vụ cố định.

## 9. Dấu hiệu đỏ số 7: dùng container mutable làm identity của `reduce`

Ví dụ sai rất phổ biến:

```java
List<Integer> result = IntStream.range(0, 1000)
    .boxed()
    .parallel()
    .reduce(
        new ArrayList<>(),
        (list, n) -> {
            list.add(n);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    ); // NGUY HIỂM.
```

Vấn đề:

- `reduce` được thiết kế cho **giá trị tích lũy** với identity/accumulator/combiner tuân thủ luật tương thích và kết hợp.
- Một `ArrayList` mutable làm identity không đáp ứng kỳ vọng identity độc lập của từng nhánh.
- Accumulator sửa chính object đã được truyền như identity; khi thực thi song song có thể gây trạng thái chia sẻ, race, nhân bản phần tử hoặc kết quả sai.
- Combiner `addAll` cũng sửa object, khiến lý luận về identity và tính kết hợp sai.

Đúng cho **mutable reduction**:

```java
List<Integer> result = IntStream.range(0, 1000)
    .boxed()
    .parallel()
    .collect(
        ArrayList::new,
        ArrayList::add,
        ArrayList::addAll
    );

System.out.println(result.size()); // 1000
```

`collect` dạng ba đối số có `supplier` tạo **container riêng** để tích lũy, `accumulator` thêm một phần tử và `combiner` ghép các container.

Hoặc đơn giản hơn:

```java
List<Integer> result = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .toList();
```

**Phân biệt:** Việc `ArrayList::add` là thao tác mutable **không làm `collect` sai**, bởi collector quản lý việc phân chia container đúng cách. Sai là cố diễn đạt **mutable reduction** bằng overload `reduce` không có hợp đồng phù hợp.

## 10. Ba loại rủi ro khi dùng `Collector` song song

Một collector có các vai trò cơ bản:

```text
supplier      -> tạo container tích lũy
accumulator   -> thêm phần tử vào container
combiner      -> gộp hai container
finisher      -> tạo kết quả cuối
characteristics -> mô tả những bảo đảm đặc biệt
```

Điều cần đọc không chỉ là code accumulator, mà còn **cách nhiều container được ghép**.

| Thành phần | Dấu hiệu nguy hiểm | Câu hỏi kiểm tra |
| --- | --- | --- |
| Supplier | Trả về cùng một object static | Mỗi phần tích lũy được cấp trạng thái độc lập không? |
| Accumulator | Ghi thêm vào biến ngoài, mutable shared state | Có cập nhật chỉ container được cung cấp không? |
| Combiner | Bỏ dữ liệu hoặc ghép sai thứ tự | Kết quả hợp nhất có tương đương xử lý toàn bộ nguồn không? |
| Finisher | Trả object nội bộ mutable cho bên ngoài rồi tiếp tục sửa | Kết quả có bất biến theo hợp đồng không? |
| Characteristics | Khai báo `CONCURRENT` khi accumulator không thread-safe | Có đúng thực sự chấp nhận đồng thời không? |

### 10.1. `Collectors.toList()` vẫn dùng được với parallel Stream

```java
List<String> ids = orders.parallelStream()
    .map(Order::id)
    .collect(java.util.stream.Collectors.toList());
```

Không cần tự thay `Collectors.toList()` bằng một `synchronizedList` dùng chung. Một collector không mang đặc tính `CONCURRENT` vẫn có thể hoạt động đúng trên parallel Stream, vì framework có thể dùng các container tích lũy **độc lập** rồi gọi combiner.

**Parallel collection không đồng nghĩa mọi thread cùng ghi vào một `ArrayList` duy nhất.**

### 10.2. `CONCURRENT` là lời hứa, không phải “tăng tốc”

Nếu tự viết collector và gắn `Collector.Characteristics.CONCURRENT`, bạn đang tuyên bố rằng accumulator có thể được gọi **đồng thời trên cùng container kết quả** một cách an toàn theo hợp đồng.

Không khai báo `CONCURRENT` cho collector ghi vào một `HashMap` hoặc `ArrayList` bình thường mà không có cơ chế an toàn tương ứng.

`Collector.Characteristics.UNORDERED` mô tả kết quả không bị ràng buộc bởi encounter order; `IDENTITY_FINISH` chỉ hợp lệ khi trạng thái tích lũy cũng chính là kiểu kết quả và finisher là identity đúng nghĩa. Không dùng các characteristics như “gợi ý hiệu năng” nếu không thỏa hợp đồng.

## 11. `groupingBy` và `groupingByConcurrent`: chọn theo yêu cầu dữ liệu

Ví dụ nhóm đơn hàng đã thanh toán theo vùng:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

Map<String, Long> counts = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

ConcurrentMap<String, Long> concurrentCounts = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.counting()
    ));

System.out.println(counts.equals(concurrentCounts)); // true
```

Hai lựa chọn có thể tạo Map có cùng số đếm, nhưng hợp đồng khác nhau:

- `groupingBy` tạo một phép gom nhóm phù hợp cả tuần tự và song song; khi song song, combiner có thể phải hợp nhất Map của các nhánh.
- `groupingByConcurrent` tạo một **concurrent/unordered collector**, thích hợp khi **không yêu cầu encounter order của giá trị trong từng nhóm**.
- `ConcurrentMap` là kiểu kết quả thread-safe ở cấp các thao tác Map được hỗ trợ, nhưng **không biến mọi object mutable chứa bên trong thành thread-safe sau khi collect**.
- Với khóa “nóng” (rất nhiều phần tử cùng khóa), contention có thể ảnh hưởng hiệu năng. Không mặc định `groupingByConcurrent` nhanh hơn.

### 11.1. Đừng kiểm thử thứ tự của danh sách trong nhóm concurrent

```java
ConcurrentMap<String, List<Order>> byRegion =
    orders.parallelStream()
        .collect(Collectors.groupingByConcurrent(Order::region));
```

Danh sách của mỗi nhóm không được bảo đảm phản ánh encounter order như một danh sách đã được tạo tuần tự. Nếu thứ tự các đơn theo timestamp là yêu cầu nghiệp vụ, hãy sắp xếp rõ ràng sau đó hoặc dùng thiết kế đảm bảo thứ tự.

**An toàn trong lúc collect** và **an toàn khi nhiều thread cùng sửa danh sách kết quả sau collect** là hai giai đoạn khác nhau. Không sửa các `List<Order>` trong `byRegion` đồng thời nếu không có cơ chế bảo vệ riêng.

## 12. `toMap`: trùng khóa, merge function và phép gộp

`Collectors.toMap` thường được dùng trong pipeline song song, nhưng dữ liệu có thể có khóa trùng.

```java
// Nhiều Order có cùng region.
// Nếu không có merge function, toMap có thể ném IllegalStateException.
Map<String, Long> unsafe = orders.parallelStream()
    .collect(Collectors.toMap(
        Order::region,
        Order::amountVnd
    ));
```

Đây không chỉ là vấn đề parallel: dữ liệu trùng khóa cũng làm phiên bản tuần tự bị lỗi.

Để tính tổng theo vùng:

```java
Map<String, Long> totals = orders.parallelStream()
    .collect(Collectors.toMap(
        Order::region,
        Order::amountVnd,
        Long::sum
    ));
```

Nếu hàm merge phụ thuộc thứ tự hoặc có side effect, cần kiểm tra xem phép gộp có phù hợp hợp đồng khi phân chia nguồn không. Với số tiền, phải xét tràn `long`; với giá trị có phần thập phân nên dùng `BigDecimal` và quy tắc làm tròn rõ ràng.

### 12.1. Khóa mutable cũng nguy hiểm

Nếu object khóa thay đổi `equals`/`hashCode` trong lúc hoặc sau khi xây Map, Map có thể không còn tìm lại khóa như mong muốn. Dùng khóa bất biến như `String` hoặc record bất biến phù hợp; không để worker sửa trường dùng làm khóa trong khi grouping/toMap đang chạy.

## 13. Dấu hiệu đỏ số 8: tác vụ phụ thuộc `ThreadLocal` và ngữ cảnh giao dịch

`ThreadLocal` lưu một giá trị theo **thread thực thi**, không phải theo “một yêu cầu nghiệp vụ” hoặc “một lần xử lý Stream”.

Ví dụ nguy hiểm về mặt thiết kế:

```java
static final ThreadLocal<String> TENANT = new ThreadLocal<>();

TENANT.set("tenant-A");

orders.parallelStream()
    .forEach(order -> {
        // Không được mặc định TENANT.get() ở worker thread
        // có giá trị "tenant-A".
        processForTenant(TENANT.get(), order);
    });

TENANT.remove();
```

Ở các worker khác, `TENANT.get()` có thể không có giá trị như thread gọi hoặc có ngữ cảnh không phù hợp nếu hệ thống quản lý sai vòng đời. Đây là rủi ro nghiêm trọng nếu tenant ID, user context, tracing, transaction hoặc thông tin phân quyền được truyền ngầm qua thread-local storage.

**Giải pháp ưu tiên:** truyền ngữ cảnh bất biến tường minh qua tham số:

```java
String tenant = "tenant-A";

List<Result> results = orders.parallelStream()
    .map(order -> processForTenant(tenant, order))
    .toList();
```

Trong ví dụ, `tenant` là giá trị bất biến được capture, không phải một context mutable phụ thuộc thread. Phải xác định `processForTenant` thực sự thread-safe và không dựa vào transaction gắn thread ở tầng dưới.

### 13.1. Có nên tạo một `ThreadLocal` cho mỗi tác vụ?

`ThreadLocal` không phải “container trạng thái riêng cho mỗi phần tử”: thread có thể xử lý nhiều phần tử và được tái sử dụng. Trong mã phụ thuộc thread pool, cần xử lý vòng đời, cleanup và tính đúng của context. Với phép tích lũy của Stream, ưu tiên **state do Collector/Gatherer quản lý** hoặc một vòng lặp tuần tự rõ ràng.

## 14. Dấu hiệu đỏ số 9: đối tượng hỗ trợ không thread-safe

Không chỉ collection/counter mới có trạng thái. Một số utility object cũng mutable:

```java
// Không nên dùng cùng một SimpleDateFormat mutable từ nhiều worker.
java.text.SimpleDateFormat sharedFormatter =
    new java.text.SimpleDateFormat("yyyy-MM-dd");

List<java.util.Date> legacyDates = List.of(
    new java.util.Date(0L),
    new java.util.Date(86_400_000L)
);

List<String> dates = legacyDates.parallelStream()
    .map(sharedFormatter::format)
    .toList();
```

`SimpleDateFormat` không được thiết kế để nhiều thread cùng sử dụng mà không có cơ chế đồng bộ thích hợp. Khi parse/format đồng thời, kết quả có thể sai hoặc phát sinh ngoại lệ.

Đối với timestamp theo `java.time`, `DateTimeFormatter` là immutable và thread-safe theo hợp đồng:

```java
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

DateTimeFormatter formatter = DateTimeFormatter
    .ofPattern("uuuu-MM-dd")
    .withZone(ZoneOffset.UTC);

List<java.time.Instant> timestamps = List.of(
    java.time.Instant.parse("2026-01-01T10:00:00Z"),
    java.time.Instant.parse("2026-01-02T10:00:00Z")
);

List<String> dates = timestamps.parallelStream()
    .map(formatter::format)
    .toList();
```

Ví dụ thứ nhất dùng `java.util.Date` với formatter mutable kiểu cũ; ví dụ thứ hai dùng `List<Instant>` với formatter bất biến của `java.time`. Việc formatter an toàn không làm cho các đối tượng khác mà pipeline sử dụng mặc nhiên an toàn.

### 14.1. Kết nối và session có trạng thái

Các đối tượng như JDBC `Connection`, transaction-bound session, mutable parser hoặc writer thường có **hợp đồng concurrency riêng**. Không chia sẻ một connection/session vào `parallel().forEach(...)` chỉ vì Java cho phép capture biến đó trong lambda.

Với I/O ngoài hệ thống, cần quyết định cách cấp tài nguyên cho mỗi tác vụ, giới hạn đồng thời, xử lý timeout, retry và idempotency. Nhiều trường hợp thích hợp hơn với executor/structured concurrency và bước tổng hợp kết quả riêng thay vì parallel Stream.

## 15. Dấu hiệu đỏ số 10: bất biến đúng của `double` bị hiểu thành so sánh bit

Phép cộng số thực nhị phân không kết hợp hoàn toàn vì làm tròn:

```text
(a + b) + c có thể khác a + (b + c)
```

Ví dụ minh họa:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Khi một parallel reduction chia/ghép các giá trị theo nhóm khác nhau, khác biệt do thứ tự cộng có thể xuất hiện. `DoubleStream.sum()` có quyền sử dụng kỹ thuật cộng bù và chiến lược tổng hợp phù hợp, vì vậy không được buộc nó khớp bit với một vòng lặp cộng naïve trong mọi tình huống.

Nếu nghiệp vụ yêu cầu:

- **Thống kê số thực:** xác định sai số chấp nhận được và kiểm thử theo tolerance.
- **Tiền tệ với phần thập phân:** dùng `BigDecimal`, thỏa thuận scale và rounding.
- **Tổng số nguyên rất lớn:** dùng `BigInteger` hoặc kiểm tra tràn.

**Thread-safe không giải quyết sai số làm tròn.** Một kết quả không khớp bit không mặc nhiên chứng minh data race; cần phân biệt vấn đề toán học với vấn đề concurrency.

### 15.1. Integer overflow cũng cần kiểm tra

`IntStream.sum()` trả `int` nên có thể tràn. `LongStream.sum()` cũng có thể tràn `long`. `Math.addExact` phát hiện tràn trong từng phép cộng; kết quả trung gian của cách phân chia song song có thể ảnh hưởng điểm phát sinh ngoại lệ. Nếu yêu cầu một tổng nguyên chính xác không giới hạn, dùng `BigInteger`.

## 16. Dấu hiệu đỏ số 11: dựa vào `findAny` hoặc thao tác unordered để chọn bản ghi “đầu tiên”

`findFirst()` và `findAny()` có cùng kiểu kết quả `Optional<T>` nhưng khác bảo đảm:

```java
List<String> ids = List.of("A", "B", "C", "D");

String first = ids.parallelStream()
    .findFirst()
    .orElseThrow(); // A trên nguồn List có thứ tự.

String any = ids.parallelStream()
    .findAny()
    .orElseThrow(); // Có thể là A, B, C hoặc D.
```

`findAny` được phép trả một phần tử bất kỳ để thuận lợi cho thực thi song song. Đừng dùng nó khi yêu cầu “đơn đầu tiên theo thời gian”.

Các thao tác như `limit`, `skip`, `takeWhile`, `dropWhile` nhạy với encounter order. Đặc biệt:

- Trên ordered Stream, `takeWhile(p)` lấy **tiền tố dài nhất** còn thỏa p.
- `dropWhile(p)` bỏ tiền tố đó và giữ phần còn lại.
- Trên unordered Stream, các phép while được phép chọn/bỏ một tập con phù hợp theo hợp đồng, không còn điểm cắt nghiệp vụ rõ ràng.
- `unordered()` bỏ ràng buộc thứ tự, **không phải một lệnh shuffle**.

Không dùng `unordered()` chỉ để tăng tốc khi kết quả phụ thuộc vào “phần tử đầu”, “N bản ghi đầu” hoặc “cửa sổ gần nhất”.

## 17. Dấu hiệu đỏ số 12: quên chi phí thao tác có trạng thái trong parallel Stream

Những thao tác sau thường cần nhớ hoặc điều phối dữ liệu:

| Thao tác | Vì sao song song có thể đắt | Cần kiểm tra |
| --- | --- | --- |
| `sorted()` | Sắp xếp và ghép kết quả có thứ tự | Có thật sự cần sorted toàn nguồn? |
| `distinct()` | Theo dõi các giá trị đã gặp | Có yêu cầu giữ encounter order? |
| `limit(n)` / `skip(n)` | Chọn phần đầu/bỏ phần đầu theo thứ tự | Nguồn có chia hiệu quả? |
| `takeWhile` / `dropWhile` | Xác định điểm cắt tiền tố | Có phải ordered Stream? |
| `groupingBy` | Gộp Map từ các nhánh | Độ phân bố khóa có gây merge lớn? |
| `flatMap` với nguồn con phức tạp | Số đầu ra mỗi nhánh không đều | Có load imbalance? |

Thí dụ:

```java
List<Integer> firstTen = IntStream.range(0, 1_000_000)
    .parallel()
    .boxed()
    .sorted()
    .limit(10)
    .toList();
```

Vì `IntStream.range` đã có encounter order và giá trị tăng dần, thêm `sorted` trong trường hợp này thường không cần thiết cho **ngữ nghĩa**. Một pipeline đơn giản hơn:

```java
List<Integer> firstTen = IntStream.range(0, 1_000_000)
    .limit(10)
    .boxed()
    .toList();
```

Không hứa rằng cách thứ hai “luôn nhanh hơn” trong mọi môi trường; điểm chính là **loại bước không cần thiết trước khi tối ưu bằng song song**.

### 17.1. `parallel()` không phải yêu cầu kết quả khác

Khi phép toán có tính đúng và bảo đảm phù hợp, giá trị đầu ra về mặt logic nên nhất quán giữa tuần tự và song song. Chênh lệch đáng kể về dữ liệu có thể là tín hiệu side effect, phép giảm sai hợp đồng, nguồn bị can thiệp hoặc kỳ vọng thứ tự không được bảo đảm.

## 18. Dấu hiệu đỏ số 13: ngoại lệ trong worker được hiểu sai là dừng đồng loạt ngay lập tức

Một mapper có thể ném ngoại lệ:

```java
List<Integer> processed = values.parallelStream()
    .map(n -> {
        if (n == 0) {
            throw new IllegalArgumentException("zero is forbidden");
        }
        return 100 / n;
    })
    .toList();
```

Trên parallel Stream, nhiều phần có thể đã được lên lịch hoặc đang xử lý khi một task gặp lỗi. **Không bảo đảm mọi task khác dừng ngay ở cùng một thời điểm** hoặc side effect trước đó được hoàn tác.

Những nguy cơ khi lambda có I/O:

- Một số bản ghi đã được gửi/ghi trước khi task khác ném lỗi.
- Lần thử lại toàn bộ pipeline có thể thực hiện thao tác đó lần nữa.
- Ngoại lệ có thể được truyền qua cơ chế xử lý song song; không dựa vào thứ tự phát hiện lỗi hoặc đúng một ngoại lệ duy nhất được quan sát.
- Việc gọi `findFirst`/`anyMatch`/`limit` có thể dừng sớm về mặt kết quả nhưng không phải “công tắc transaction rollback”.

### 18.1. Phân biệt ngoại lệ có thể phục hồi với lỗi dữ liệu

Nếu từng bản ghi có thể thất bại độc lập, một mẫu thiết kế phù hợp là **mô hình hóa kết quả thành công/thất bại** thay vì giấu lỗi rồi bỏ qua:

```java
public class ParseResultsDemo {
    record ParseResult(String raw, Integer value, String error) {
        boolean ok() { return error == null; }
    }

    static ParseResult parseNumber(String raw) {
        try {
            return new ParseResult(raw, Integer.parseInt(raw), null);
        } catch (NumberFormatException e) {
            return new ParseResult(raw, null, "invalid integer");
        }
    }

    public static void main(String[] args) {
        List<ParseResult> results = List.of("10", "oops", "20")
            .parallelStream()
            .map(ParseResultsDemo::parseNumber)
            .toList();

        results.forEach(System.out::println);
    }
}
```

Ví dụ tự chứa này tạo một kết quả cho từng đầu vào, bao gồm cả trường hợp lỗi. Kết quả cho biết chính xác bản ghi nào thất bại mà không dùng collection mutable dùng chung.

Không tự quy mọi ngoại lệ như `OutOfMemoryError`, lỗi phân quyền hoặc lỗi hệ thống về một trạng thái “input invalid”; chính sách bắt lỗi phải phân biệt lỗi dữ liệu có thể tiếp tục với lỗi nghiêm trọng cần dừng.

### 18.2. Checked exception và Stream lambda

Các `Function`/`Predicate` tiêu chuẩn không khai báo checked exception tùy ý, vì thế code I/O thường phải bọc hoặc ánh xạ lỗi:

```java
.map(path -> {
    try {
        return java.nio.file.Files.size(path);
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
})
```

`UncheckedIOException` giữ nguyên nguyên nhân `IOException` nhưng không giải quyết tự động việc retry, rollback hay đóng tài nguyên. Với pipeline có nhiều tác vụ, cần cân nhắc liệu xử lý I/O song song có thật sự đúng về giới hạn tài nguyên.

## 19. Dấu hiệu đỏ số 14: side effect không có hợp đồng exactly-once

Ví dụ:

```java
orders.parallelStream()
    .forEach(order -> paymentGateway.charge(order));
```

Ngay cả khi API gateway có thể được gọi từ nhiều thread, thao tác thu tiền có **tác dụng bên ngoài**. Nếu một phần thất bại, **parallel Stream không cung cấp transaction toàn cục** để hoàn tác những lần charge đã thành công.

Nếu người vận hành thử lại batch sau lỗi, có thể tạo charge trùng khi không có khóa idempotency. Đây là vấn đề nghiệp vụ, không chỉ là Java thread safety.

Đối với tác vụ có side effect không thể bỏ qua, cần thiết kế riêng:

1. Xác định tập công việc cần làm bằng pipeline thuần dữ liệu.
2. Kiểm tra dữ liệu đầu vào, quyền truy cập và điều kiện nghiệp vụ.
3. Dùng idempotency key/transaction/outbox hoặc giao thức tin cậy tương ứng với hệ thống đích.
4. Giới hạn concurrency và theo dõi kết quả từng tác vụ.
5. Có chính sách bù trừ, retry và phân loại lỗi rõ ràng.

**Không có từ khóa `parallel`, `synchronized` hay `AtomicInteger` nào tự bảo đảm exactly-once khi gọi hệ thống ngoài.**

## 20. Dấu hiệu đỏ số 15: bỏ quên vòng đời tài nguyên I/O

Một `Stream` trả bởi `Files.lines(path)` giữ tài nguyên cần đóng:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileStreamSafetyDemo {
    static long countErrors(Path path) throws java.io.IOException {
        try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> line.contains("ERROR"))
                .count();
        }
    }
}
```

`try-with-resources` trong ví dụ bảo đảm giải phóng tài nguyên khi hàm kết thúc hoặc khi có ngoại lệ.

Nếu thêm `parallel()`:

```java
try (Stream<String> lines = Files.lines(path)) {
    long errors = lines.parallel()
        .filter(line -> line.contains("ERROR"))
        .count();
    System.out.println(errors);
}
```

vẫn phải giữ `try-with-resources`. `count()` hay việc kết thúc sớm **không tự gọi `close()`** cho mọi nguồn Stream I/O. Ngoài ra, cách phân chia nguồn và chi phí đọc/giải mã tệp có thể khiến song song không mang lại lợi ích.

### 20.1. Đừng dùng cùng writer không an toàn cho các worker

```java
// Cần xem xét kỹ hợp đồng của writer và điều phối ghi.
lines.parallel()
    .forEach(line -> writer.write(line + System.lineSeparator()));
```

Nhiều writer mutable không phù hợp với thao tác gọi đồng thời nếu thiếu đồng bộ; và kể cả có lock, thứ tự dòng có thể sai. Nếu yêu cầu xuất tệp **theo thứ tự**, cách đơn giản hơn có thể là xử lý dữ liệu rồi ghi tuần tự.

## 21. Dấu hiệu đỏ số 16: deadlock, blocking và resource starvation

Không phải phép nào có thể chạy trong parallel Stream cũng nên được chạy như vậy. Những thao tác sau cần thận trọng:

- Chờ một lock mà worker khác cần để hoàn tất.
- Chặn vô hạn trên `Future.get()`/`join()` trong một mạng phụ thuộc công việc.
- Gọi I/O mạng thời gian dài mà không giới hạn số kết nối.
- Thực thi pipeline song song lồng nhau với số lượng lớn.
- Kết hợp database pool nhỏ với lượng công việc song song lớn.
- Lẫn lộn context của transaction gắn thread với worker pool.

Một ví dụ logic nguy hiểm là mỗi phần tử tạo công việc mới trên cùng executor hữu hạn rồi **đợi** kết quả trong khi mọi worker executor đã bận chờ. Đó là mẫu *thread starvation deadlock* có thể xuất hiện trong nhiều mô hình concurrency, không riêng Stream API.

**Đối sách:** đo mức độ chặn, giới hạn đồng thời, tránh chuỗi phụ thuộc vòng, xác định timeout/cancellation và cân nhắc cơ chế quản lý tác vụ có cấu trúc hoặc executor do ứng dụng kiểm soát. Không dùng `parallelStream()` như thay thế tổng quát cho kiến trúc thực thi I/O có giới hạn.

## 22. Custom `Spliterator` và cách chia nguồn sai

Parallel Stream dựa nhiều vào `Spliterator.trySplit()` để chia dữ liệu. Một Spliterator tùy chỉnh sai hợp đồng có thể tạo:

- **Mất phần tử** giữa các nhánh.
- **Lặp phần tử** khi hai nhánh duyệt vùng trùng nhau.
- Thứ tự sai mặc dù đã khai báo `ORDERED`.
- Kích thước sai mặc dù khai báo `SIZED`/`SUBSIZED`.
- Data race khi hai Spliterator con cùng sửa một con trỏ chia nguồn.

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<Integer> s = List.of(1, 2, 3).spliterator();

System.out.println(s.hasCharacteristics(Spliterator.ORDERED)); // true
System.out.println(s.estimateSize());                         // 3
```

Một nguồn chuẩn như `List.of` đã có Spliterator thích hợp. Đừng tự viết Spliterator nếu một nguồn sẵn có đã biểu diễn đúng dữ liệu.

### 22.1. `CONCURRENT` của nguồn khác `CONCURRENT` của collector

| Đặc tính | Áp dụng lên | Ý nghĩa |
| --- | --- | --- |
| `Spliterator.CONCURRENT` | Nguồn duyệt | Nguồn hỗ trợ sửa đổi đồng thời theo hợp đồng |
| `Collector.Characteristics.CONCURRENT` | Bộ thu thập | Accumulator có thể chấp nhận các lời gọi đồng thời trên cùng container |
| `Gatherer.Integrator.Greedy` (Java 24+) | Integrator | Không tự khởi phát short-circuit |

Không suy rằng đặc tính này kéo theo đặc tính kia; mỗi phần có một hợp đồng riêng.

## 23. Stream Gatherers và parallel safety (Java 24+)

`Stream.gather(...)` mở rộng Stream bằng custom intermediate operations. Một `Gatherer<T,A,R>` có thể duy trì trạng thái và phát nhiều đầu ra. Cũng vì vậy, nó có thể mang rủi ro song song nếu **combiner** không phù hợp.

Ví dụ nguyên tắc:

```java
// Java 24+, dạng gatherer tuần tự có trạng thái.
static java.util.stream.Gatherer<Integer, long[], Long> runningTotal() {
    return java.util.stream.Gatherer.ofSequential(
        () -> new long[] {0L},
        (state, value, downstream) -> {
            state[0] = Math.addExact(state[0], value.longValue());
            return downstream.push(state[0]);
        }
    );
}
```

Đây là tổng tích lũy theo thứ tự. Nếu chia nguồn thành hai đoạn, tổng chạy ở đầu đoạn thứ hai **phụ thuộc tổng của đoạn thứ nhất**. Chỉ cộng hai state cuối của mỗi nhánh không đủ tạo đúng toàn bộ chuỗi prefix sums.

Do đó, `ofSequential` là lựa chọn đúng khi chưa xây được combiner có hợp đồng tương ứng.

### 23.1. Greedy và parallel là hai câu hỏi khác nhau

`Gatherer.Integrator.ofGreedy(...)` chỉ tuyên bố integrator **không tự yêu cầu ngừng nhận upstream**; nó có thể trả `false` khi downstream đã từ chối.

Greedy **không đồng nghĩa** thread-safe, không cung cấp combiner, không làm một state mutable dùng chung trở nên an toàn. Một gatherer có thể **greedy nhưng tuần tự**.

**Đặc biệt nguy hiểm:** khai báo Greedy cho một Integrator thực ra tự dừng ở một marker. Triển khai Stream được phép bỏ qua boolean trả về của Greedy Integrator; điều này có thể làm chương trình không dừng đúng nghiệp vụ.

### 23.2. `mapConcurrent` và virtual threads

`Gatherers.mapConcurrent(maxConcurrency, mapper)` có cơ chế ánh xạ đồng thời giới hạn bằng virtual threads. Nó khác `parallelStream().map(...)` về mô hình thực thi và giới hạn concurrency; một mapper vẫn phải đúng về dữ liệu, thread safety, ngoại lệ và tài nguyên.

Không suy rằng virtual threads tự biến connection mutable hoặc transaction-bound context thành một tài nguyên có thể chia sẻ an toàn.

## 24. Kiểm thử tính đúng: phải so sánh kết quả, không so log

Với pipeline parallel, không nên dựa vào chuỗi log `peek` để kiểm tra thứ tự hoặc số lần thực thi. Cách tốt hơn là kiểm tra **bất biến kết quả** trên dữ liệu có thể dự đoán.

### 24.1. Những bất biến cần có

- `filter` không tạo thêm phần tử.
- `map` giữ số phần tử logic trong một phép biến đổi 1:1.
- `flatMap` có thể làm thay đổi số phần tử theo số kết quả con.
- `distinct` không tăng số phần tử.
- `toList()` trên ordered Stream giữ encounter order của kết quả.
- Tổng theo nhóm phải có cùng khóa và giá trị dù lựa chọn `groupingBy` hay một biến thể concurrent phù hợp.
- Không có phần tử trùng/lạc/mất ngoài quy tắc nghiệp vụ.
- Sau terminal operation, Stream không được dùng lại.
- Nếu có lỗi từ hệ thống ngoài, việc retry không gây side effect sai hợp đồng.

### 24.2. Kiểm thử với nguồn đa dạng

| Dữ liệu | Lỗi dễ bộc lộ |
| --- | --- |
| Nguồn rỗng | Identity sai, `Optional.get` không có giá trị |
| Một phần tử | Vấn đề xử lý khởi đầu và kết thúc |
| Nhiều phần tử trùng | `distinct`, `toMap` merge, khóa mutable |
| Tất cả cùng khóa grouping | Contention, xử lý khóa nóng |
| Giá trị âm/lớn | Overflow, dấu, non-associativity |
| Nguồn không có thứ tự | Giả định sai về `findAny`, `limit`, cửa sổ |
| Kích thước rất lớn | Scheduling, bộ nhớ, phân chia Spliterator |
| Đọc tệp/I/O | Ngoại lệ, đóng tài nguyên và retry |
| Nhiều lần chạy/fork | Lỗi race không ổn định theo lịch thực thi |

**Cảnh báo:** Một test chạy 1000 lần mà không phát hiện race **không chứng minh không có race**. Kiểm tra hợp đồng và dùng các công cụ concurrency testing/profiling phù hợp vẫn cần thiết.

## 25. Chương trình Java 17 hoàn chỉnh: lựa chọn xử lý song song an toàn

Chương trình sau tự chứa, chạy được trên Java 17+ và **không** dùng side effect trong pipeline. Nó so sánh kết quả tuần tự với kết quả song song và gom nhóm theo vùng.

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class SafeParallelStreamDemo {

    record Order(String id, String region, long amountVnd, boolean paid) {}

    static List<Order> sample() {
        return List.of(
            new Order("O1", "Bac", 100_000L, true),
            new Order("O2", "Nam",  50_000L, false),
            new Order("O3", "Bac", 200_000L, true),
            new Order("O4", "Trung", 70_000L, true),
            new Order("O5", "Nam",  30_000L, true),
            new Order("O6", "Trung", 10_000L, false)
        );
    }

    static long totalPaidSequential(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();
    }

    static long totalPaidParallel(List<Order> orders) {
        return orders.parallelStream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();
    }

    static Map<String, Long> countsSequential(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }

    static Map<String, Long> countsParallel(List<Order> orders) {
        return orders.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }

    static ConcurrentMap<String, Long> countsConcurrent(
            List<Order> orders) {
        return orders.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingByConcurrent(
                Order::region,
                Collectors.counting()
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = sample();

        long sequentialTotal = totalPaidSequential(orders);
        long parallelTotal = totalPaidParallel(orders);

        Map<String, Long> sequentialCounts = countsSequential(orders);
        Map<String, Long> parallelCounts = countsParallel(orders);
        ConcurrentMap<String, Long> concurrentCounts =
            countsConcurrent(orders);

        List<String> paidIds = orders.parallelStream()
            .filter(Order::paid)
            .map(Order::id)
            .toList();

        System.out.println("Total: " + parallelTotal);
        System.out.println("Paid IDs: " + paidIds);

        if (sequentialTotal != 400_000L) {
            throw new AssertionError("Unexpected sequential total");
        }
        if (parallelTotal != sequentialTotal) {
            throw new AssertionError("Parallel total mismatch");
        }
        if (!parallelCounts.equals(sequentialCounts)) {
            throw new AssertionError("Parallel grouping mismatch");
        }
        if (!concurrentCounts.equals(sequentialCounts)) {
            throw new AssertionError("Concurrent grouping mismatch");
        }
        if (!paidIds.equals(List.of("O1", "O3", "O4", "O5"))) {
            throw new AssertionError("Encounter-order mismatch");
        }

        System.out.println("All checks passed");
    }
}
```

Kết quả mong đợi:

```text
Total: 400000
Paid IDs: [O1, O3, O4, O5]
All checks passed
```

Kiểu Map có thể có thứ tự in khóa khác nhau nếu in trực tiếp; code kiểm tra bằng `Map.equals` để không phụ thuộc vào thứ tự khóa.

### 25.1. Vì sao chương trình này an toàn về mô hình?

- `Order` là record bất biến với các trường bất biến trong ví dụ.
- Nguồn `List.of` không bị sửa trong thời gian duyệt.
- `filter` và `mapToLong`/`map` không có side effect.
- `sum` và `counting` được giao cho terminal operation/collector quản lý.
- `groupingBy` và `groupingByConcurrent` dùng đúng hợp đồng.
- Không dùng `forEach` để ghi vào một Map/List bên ngoài.
- `toList` trên ordered Stream giữ thứ tự ID.
- Kết quả được kiểm tra bằng bất biến cụ thể.

**Giới hạn:** Ví dụ chọn các số nhỏ để tránh tràn `long`. Với dữ liệu tài chính thực tế, cần kiểm soát miền giá trị và quy tắc tiền tệ. Việc pipeline đúng không tự bảo đảm nó nhanh hơn bản tuần tự.

## 26. Kiểm thử JUnit 5 và property-based thinking

Nếu dự án có JUnit 5, có thể so sánh hai cách thực hiện trên nhiều bộ dữ liệu:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ParallelStreamSafetyTest {

    @Test
    void sequentialAndParallelTotalsMatch() {
        List<SafeParallelStreamDemo.Order> data =
            SafeParallelStreamDemo.sample();

        assertEquals(
            SafeParallelStreamDemo.totalPaidSequential(data),
            SafeParallelStreamDemo.totalPaidParallel(data)
        );
    }

    @Test
    void emptyInputHasZeroTotalAndEmptyGroups() {
        List<SafeParallelStreamDemo.Order> empty = List.of();

        assertEquals(0L,
            SafeParallelStreamDemo.totalPaidParallel(empty));
        assertEquals(
            SafeParallelStreamDemo.countsSequential(empty),
            SafeParallelStreamDemo.countsParallel(empty)
        );
    }

    @Test
    void concurrentGroupingHasSameCounts() {
        var data = SafeParallelStreamDemo.sample();

        assertEquals(
            SafeParallelStreamDemo.countsSequential(data),
            SafeParallelStreamDemo.countsConcurrent(data)
        );
    }
}
```

Với kiểm thử tạo dữ liệu tự động, có thể phát biểu:

> Với mọi danh sách Order hợp lệ có tổng trong miền `long`, hàm tính tổng của pipeline tuần tự và pipeline song song trả cùng giá trị.

Tuy nhiên, kiểm thử **không phải chứng minh toán học** rằng mọi lambda đều thread-safe. Với custom collector/Spliterator, phải kiểm tra cả hợp đồng supplier, combiner, đặc tính nguồn và những biến dùng chung.

### 26.1. Không dùng test log làm oracle

`peek(System.out::println)` có thể in xen kẽ hoặc bị tối ưu bỏ trong một số pipeline. Số log và thứ tự log không phải là oracle đáng tin cho mọi thao tác. Hãy kiểm tra **dữ liệu kết quả** và các invariants đã được định nghĩa.

## 27. Checklist review: thấy dấu hiệu nào thì dừng việc thêm `parallel()`?

| Dấu hiệu trong code | Nguy cơ | Hướng xử lý ưu tiên |
| --- | --- | --- |
| `parallel().forEach(list::add)` | Ghi đồng thời `ArrayList` | `toList()` / `collect` |
| `parallel().peek(cache::put)` | Side effect/race/bỏ callback | Tách bước cập nhật có kiểm soát |
| `counter[0]++` trong lambda | Data race | `count()` hoặc thiết kế counter phù hợp |
| `AtomicInteger` dùng để đánh index | Index phụ thuộc lịch chạy | `IntStream.range` với index nguồn |
| `source.remove(...)` khi duyệt | Interference | Không sửa nguồn trong pipeline |
| `reduce(0, (a,b)->a-b)` | Không kết hợp/identity sai | Chọn phép toán hợp đồng đúng |
| `reduce(new ArrayList<>(), ...)` | Mutable identity trong reduce | `collect` hoặc `toList` |
| Collector supplier trả object static | Chia sẻ state giữa nhánh | Supplier tạo object mới |
| Collector `CONCURRENT` với `HashMap` | Accumulator không an toàn | Sửa collector/characteristics |
| `groupingByConcurrent` nhưng cần thứ tự từng nhóm | Thứ tự không bảo đảm | Dùng thiết kế có yêu cầu thứ tự rõ |
| `toMap` không có merge khi trùng khóa | Ngoại lệ | Bổ sung merge hợp lệ |
| Shared `SimpleDateFormat` | Mutable non-thread-safe | `DateTimeFormatter` |
| `ThreadLocal` chứa context nghiệp vụ | Context không truyền theo tác vụ | Truyền tham số tường minh |
| `findAny` dùng để tìm bản ghi “đầu tiên” | Không bảo đảm thứ tự | `findFirst` và ordered source |
| `unordered().takeWhile(...)` cần đúng tiền tố | Ngữ nghĩa không như yêu cầu | Giữ encounter order |
| `sorted()/distinct()/limit()` trên ordered parallel lớn | Chi phí state/đồng bộ | Đánh giá lại thiết kế, benchmark |
| Lambda ghi DB/charge/cập nhật bên ngoài | Không có exactly-once/rollback | Tách I/O, idempotency và transaction |
| `Files.lines` không được đóng | Rò rỉ tài nguyên | `try-with-resources` |
| `parallel()` trên nguồn có custom Spliterator | Sai `trySplit` gây mất/trùng | Kiểm thử hợp đồng nguồn |
| `gather` có state nhưng combiner không đúng | Sai chuỗi đầu ra | `ofSequential`/combiner hợp lệ |
| `parallel()` với workload cực nhỏ | Overhead > công việc | Đo JMH, cân nhắc tuần tự |

## 28. Bài tập thực hành

### Bài 1: Tìm và sửa data race

Cho:

```java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 10000)
    .parallel()
    .forEach(output::add);
```

Hãy giải thích vì sao `output.size()` không phải luôn 10000 theo hợp đồng. Viết lại bằng `boxed().toList()` và kiểm tra kích thước, thứ tự kết quả.

### Bài 2: Atomic chưa đủ bảo đảm thứ tự

Dùng `AtomicInteger` để gắn index cho `List.of("A","B","C","D")` trên parallel Stream. So sánh với `IntStream.range(0, list.size()).mapToObj(...)`. Vì sao đầu ra cuối giữ encounter order vẫn có thể chứa index sai?

### Bài 3: Identity của `reduce`

So sánh `reduce(10, Integer::sum)` và `10 + stream.reduce(0, Integer::sum)` khi xử lý song song. Tại sao identity không thể là “giá trị cộng thêm một lần”?

### Bài 4: Phép toán không kết hợp

Tìm một danh sách `int` khiến reduction dùng phép trừ cho kết quả khác nhau tùy cách nhóm. Giải thích vì sao không thể chỉ dựa vào một lần chạy thực tế để chứng minh phép trừ an toàn.

### Bài 5: Mutable reduction

Chuyển đoạn `reduce(new ArrayList<>(), ...)` thành `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)`. Giải thích sự khác nhau giữa identity của `reduce` và supplier trong `collect`.

### Bài 6: Gộp nhóm song song

Tạo 1000 đơn với khóa region trùng nhiều lần. So sánh `groupingBy(..., counting())` và `groupingByConcurrent(..., counting())` theo Map equality; không so thứ tự in khóa. Sau đó thử đo JMH khi phân bố khóa đồng đều và khi tất cả đơn có cùng khóa.

### Bài 7: `ThreadLocal` và phân quyền

Một ứng dụng lưu tenant ID trong `ThreadLocal` của request thread rồi chạy `parallelStream()`. Phân tích điều gì có thể xảy ra trong worker thread. Viết lại bằng tham số tenant bất biến và xác minh API xử lý được dùng đúng tenant.

### Bài 8: Ngoại lệ giữa batch I/O

Một pipeline song song gọi hệ thống ngoài để cập nhật 100 đơn. Bản ghi thứ 20 thất bại; đã có 15 cập nhật thành công. Vì sao retry toàn batch có thể nguy hiểm? Thiết kế bước ghi với idempotency key và kết quả từng bản ghi.

### Bài 9: Phân biệt sai số số thực và race

Tính tổng `double` bằng vòng lặp và parallel reduction. Nếu hai kết quả lệch ở chữ số cuối, có đủ bằng chứng kết luận race không? Hãy nêu cách kiểm tra tính toán đúng với tolerance và bài toán dùng tiền `BigDecimal`.

### Bài 10: `findAny` và encounter order

Trên `List` ordered, so sánh `parallelStream().findAny()` với `parallelStream().findFirst()`. Khi nghiệp vụ yêu cầu bản ghi sớm nhất, cần bảo đảm thêm điều gì về thứ tự nguồn?

### Bài 11: Bộ lọc có side effect

Một predicate dùng `counter[0]++` để đánh số phần tử rồi quyết định giữ/bỏ theo chỉ số. Vì sao cách làm sai trong xử lý song song? Thiết kế giải pháp theo index nguồn hoặc tạo snapshot tuần tự tùy nghiệp vụ.

### Bài 12: Tài nguyên

Viết hàm đếm dòng lỗi từ `Files.lines(path)` bằng `try-with-resources`. Thử thêm `parallel()`; phân tích vì sao việc source có tài nguyên và phép `close` không thay đổi theo cách chỉ thêm một từ khóa.

### Bài 13: Custom Gatherer

Trên JDK 24+, viết một Gatherer phát tổng tích lũy theo thứ tự bằng `ofSequential`. Giải thích vì sao không thể tự ý thêm combiner cộng hai state cuối nếu đầu ra gồm mọi prefix sum.

### Bài 14: Thiết kế benchmark công bằng

Dùng JMH so sánh tuần tự và song song cho phép tổng bình phương số chẵn trên `int[]`. Chọn ít nhất ba kích thước, kiểm tra tổng bằng nhau và đo GC allocation. Vì sao phép nhanh hơn trên một triệu phần tử có thể chậm hơn trên một nghìn phần tử?

### Bài 15: Review hệ thống thực tế

Chọn một pipeline có gọi repository hoặc gửi request bên ngoài. Viết checklist về thread safety, transaction, idempotency, giới hạn đồng thời, timeout, retry, cancellation, monitoring và rollback. Từ đó quyết định có nên dùng parallel Stream hay một cơ chế điều phối tác vụ tường minh.

## 29. Câu hỏi tự kiểm tra

- Vì sao `parallelStream()` không bảo đảm lambda chạy theo encounter order?
- `toList()` trên ordered parallel Stream có thể giữ đúng thứ tự dù `map` chạy lệch thứ tự không?
- Non-interference khác stateless behavior ở điểm nào?
- Vì sao `ArrayList.add` trong `parallel().forEach` nguy hiểm?
- `AtomicInteger` giải quyết được race nào và không giải quyết được yêu cầu thứ tự nào?
- Vì sao `peek` không phải cơ chế ghi nhận nghiệp vụ đáng tin?
- Sửa `source` đang được duyệt có thể gây điều gì?
- Vì sao `reduce` cần identity trung lập và phép kết hợp?
- Mutable container trong `reduce` khác supplier của `collect` ra sao?
- `Collector.Characteristics.CONCURRENT` có nghĩa là gì?
- `groupingByConcurrent` có bảo đảm thứ tự danh sách trong nhóm không?
- Khi nào `findAny` phù hợp, khi nào cần `findFirst`?
- Vì sao `ThreadLocal` không tự lan truyền ngữ cảnh sang worker?
- Vì sao `DateTimeFormatter` thường phù hợp hơn một `SimpleDateFormat` chia sẻ?
- Khi task song song ném ngoại lệ, các side effect đã thực hiện có tự rollback không?
- `Files.lines` có tự đóng khi gọi `count()` không?
- Tại sao `parallel()` có thể làm giảm hiệu năng dù kết quả đúng?
- Vì sao `Spliterator.CONCURRENT` không đồng nghĩa một collector tùy chỉnh an toàn?
- Tại sao `Gatherer.Integrator.ofGreedy` không phải một cam kết về thread safety?
- Một kết quả `double` khác vài bit có đủ để kết luận có data race không?

## 30. Tài liệu tham khảo

- [Java SE 17 — `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): non-interference, stateless behaviors, side effects, `parallel`, `forEach` và `forEachOrdered`.
- [Java SE 17 — `Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `groupingBy`, `groupingByConcurrent`, `toMap` và collector characteristics.
- [Java SE 17 — `Collector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html): supplier, accumulator, combiner, finisher và các ràng buộc identity/associativity.
- [Java SE 17 — `Spliterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): `trySplit`, `ORDERED`, `SIZED`, `SUBSIZED` và `CONCURRENT`.
- [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `lines` và cách quản lý tài nguyên Stream I/O.
- [Java SE 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): cập nhật nguyên tử và các giới hạn của việc dùng bộ đếm.
- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): giá trị phụ thuộc thread và quản lý vòng đời.
- [Java SE 24 — `Gatherer`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): trạng thái, combiner, finisher và thiết kế Gatherer an toàn.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): công cụ benchmark đo hiệu năng/GC cho phép so sánh tuần tự và song song.

**Ghi nhớ:** Khi đọc một pipeline song song, hãy tìm **trạng thái mutable dùng chung**, **side effect**, **sửa nguồn khi duyệt**, **giả định thứ tự thực thi**, **identity/combiner sai hợp đồng**, **nguồn hoặc tài nguyên không thread-safe** và **thao tác có trạng thái gây chi phí lớn**. Ưu tiên `map`/`filter` thuần dữ liệu, `reduce` với phép toán hợp lệ và `collect` quản lý container riêng; chọn `groupingByConcurrent` chỉ khi hợp đồng unordered phù hợp. Một pipeline chỉ thật sự an toàn khi **kết quả, trạng thái, ngoại lệ, tài nguyên và các side effect bên ngoài** đều được xử lý đúng — không chỉ khi nó chạy mà không ném lỗi.
