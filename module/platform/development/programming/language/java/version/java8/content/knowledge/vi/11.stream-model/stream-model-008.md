# Tránh phụ thuộc trạng thái thay đổi bên ngoài khi dùng Java Stream

**Mục tiêu quan trọng của mô hình Stream** là mô tả phép tính trên dữ liệu bằng một pipeline gồm source, intermediate operations và terminal operation, thay vì duyệt phần tử rồi sửa các biến ở ngoài. Những hàm được truyền vào `filter`, `map`, `flatMap`, `sorted` hoặc các thao tác tương tự nên **không can thiệp vào nguồn** (*non-interfering*) và trong phần lớn trường hợp phải **không phụ thuộc trạng thái đang thay đổi** (*stateless*).

Ví dụ dễ đọc và an toàn:

~~~java
List<String> eligibleIds = sales.stream()
    .filter(sale -> sale.amount() >= 50)
    .map(Sale::id)
    .collect(Collectors.toList());
~~~

Ở đây, callback xác định kết quả từ **phần tử đầu vào** và ngưỡng được cố định trong thời gian thực thi. Danh sách kết quả được xây dựng bởi cơ chế `collect`, không phải do callback tùy ý chèn vào một danh sách bên ngoài pipeline.

Đối lập:

~~~java
List<String> result = new ArrayList<>();
sales.stream()
    .filter(sale -> sale.amount() >= 50)
    .forEach(sale -> result.add(sale.id()));
~~~

Đây là một cách **tích lũy thông qua side effect bên ngoài**. Nó có thể cho kết quả như mong muốn khi chạy tuần tự ở ví dụ đơn giản, nhưng tạo thêm mutable state, khiến ý định “thu thập thành một danh sách” bị che khuất. Đặc biệt nếu đổi sang `parallelStream()`, `ArrayList` bị nhiều thread sửa đồng thời, có thể dẫn đến kết quả không đúng hoặc lỗi. Cách viết đầu tiên dùng `collect` là hướng phù hợp hơn.

Bài này giải thích chính xác ranh giới giữa **non-interference**, **stateless behavioral parameters**, **side effects**, **parallel execution**, việc Java cho phép **capture biến effectively final** và cách thay code phụ thuộc trạng thái ngoài bằng `map`, `filter`, `reduce`, `collect`, `groupingBy` hay thao tác chuyên dụng. Chỉ xét các quy tắc còn áp dụng trong Java hiện đại; ví dụ đầy đủ biên dịch bằng **JDK 17** và chủ yếu sử dụng API đã có từ Java 8.

## 1. Vì sao Stream có yêu cầu này?

Java Stream không đơn thuần là một vòng lặp `for` được viết gọn. Một stream pipeline thường:

1. Xác định **source**: `List`, `Set`, array, generator, file data hoặc stream khác.
2. Xây dựng chuỗi **intermediate operations**: `map`, `filter`, `flatMap`, `sorted`, `distinct`, `limit`...
3. Chỉ thực hiện công việc khi gọi **terminal operation**: `collect`, `reduce`, `count`, `findFirst`, `forEach`, `sum`...

Các intermediate operations nói chung được thực thi **lazily**; pipeline có thể short-circuit, xử lý từng phần tử theo cách khác nhau, chia công việc chạy song song hoặc **loại bỏ những bước không ảnh hưởng đến kết quả được phép quan sát**. Vì vậy, ta không nên dùng callback của intermediate operation như một chỗ “bảo đảm” những side effect phải chạy đúng một lần, đúng thứ tự và đúng thread.

Oracle Javadoc mô tả hai yêu cầu thiết kế:

- **Non-interfering**: behavioral parameters **không được sửa nguồn stream không hỗ trợ concurrent modification** trong lúc pipeline đang thực thi.
- **Stateless**: kết quả callback **không phụ thuộc một trạng thái có thể thay đổi trong thời gian xử lý pipeline**.

Ví dụ, cùng một giá trị `Sale("A1", 120)` nên được `filter` quyết định như nhau trong cùng một phép tính, thay vì khi thì đúng khi thì sai do một counter bên ngoài đã thay đổi.

### Hai tính chất khác nhau

| Tính chất | Điều cần tránh | Ví dụ vi phạm |
| --- | --- | --- |
| Non-interference | Thay đổi chính nguồn đang được duyệt | `source.stream().forEach(source::remove)` |
| Stateless behavioral parameter | Kết quả phụ thuộc state đang biến đổi | `filter(x -> counter.incrementAndGet() % 2 == 0)` |
| Tránh side effect không cần thiết | Thay đổi biến/danh sách ngoài thay cho dùng kết quả terminal operation | `map(x -> { results.add(x); return x; })` |
| Thread safety | Nhiều thread đọc/ghi state chung mà không có đồng bộ đúng | `parallelStream().forEach(sharedArrayList::add)` |
| Có chủ đích về ordering | Phụ thuộc callback chạy theo encounter order | `parallelStream().forEach(System.out::println)` rồi giả định thứ tự |
| Tính đúng đắn khi tối ưu hóa | Coi `peek`/`map` như hook được gọi chắc chắn | `stream.peek(audit::write).count()` |

Các điểm này có liên quan nhưng không đồng nhất: một function có thể **không sửa nguồn** nhưng vẫn là **stateful** vì đọc counter ngoài; hoặc thread-safe ở mức thao tác đơn lẻ mà vẫn sai về logic nghiệp vụ.

## 2. Hiểu “trạng thái thay đổi bên ngoài”

“Trạng thái bên ngoài” là dữ liệu không được cung cấp như tham số hiện tại của callback nhưng ảnh hưởng đến kết quả hoặc bị callback sửa. Ví dụ:

- Biến local dạng object có thể thay đổi: `List`, `Map`, `StringBuilder`, mảng, `AtomicInteger`.
- Instance fields hoặc `static` fields có thể được thread khác cập nhật.
- Thời gian hiện tại, random generator có trạng thái, cấu hình được reload hoặc service trả dữ liệu khác nhau theo lời gọi.
- Cursor/iterator ngoài pipeline; đối tượng cache; thread-local context không được thiết kế theo đúng vòng đời thực thi.
- Chính collection cung cấp source, nếu callback sửa collection đó.

Không phải mọi đọc dữ liệu ngoài đều sai. Ví dụ:

~~~java
final int threshold = 50;
List<Sale> chosen = sales.stream()
    .filter(sale -> sale.amount() >= threshold)
    .collect(Collectors.toList());
~~~

`threshold` là cấu hình số nguyên cố định trong lượt tính toán, nên callback không phụ thuộc vào state đang đổi. `sale.amount()` cũng nên trả dữ liệu ổn định trong lượt tính toán; nếu `Sale` mutable và thread khác sửa `amount`, tình huống cần được thiết kế thêm.

**Phân biệt capture với mutable state:** Lambda được phép capture **biến local là final hoặc effectively final**; điều này chỉ giới hạn việc **gán lại biến local**, không làm object được capture trở nên immutable:

~~~java
List<String> collected = new ArrayList<>();
// collected = new ArrayList<>(); // Nếu biến được capture, gán lại sẽ không hợp lệ.
sales.forEach(sale -> collected.add(sale.id())); // Vẫn có thể sửa nội dung list!
~~~

Java cho phép đoạn mã trên vì **tham chiếu local `collected` không bị gán lại**, nhưng bản thân `ArrayList` vẫn mutable. `effectively final` **không đồng nghĩa** stateless hay thread-safe.

## 3. Hai cách sai khác nhau: sửa nguồn và sửa accumulator ngoài

### 3.1. Sửa chính collection đang tạo stream

~~~java
List<String> source = new ArrayList<>(Arrays.asList("a", "b", "c"));

// Không làm trong Stream pipeline:
source.stream().forEach(source::remove);
~~~

Đây là **anti-pattern minh họa**, không phải mã cần chạy. Với nguồn collection thông thường không hỗ trợ traversal đồng thời với sửa đổi cấu trúc, hành vi có thể không xác định như người viết mong đợi: ném `ConcurrentModificationException`, xử lý sai phần tử hoặc tạo kết quả không hợp lệ. **Không được dựa vào việc “luôn ném lỗi”**: cơ chế phát hiện concurrent modification của một số collection là best-effort.

Nếu mục đích là xóa phần tử khỏi danh sách có thể sửa, dùng API phù hợp:

~~~java
List<String> source = new ArrayList<>(Arrays.asList("a", "", "b"));
source.removeIf(String::isEmpty);
// source = ["a", "b"]
~~~

`Collection.removeIf` (từ Java 8) là **thao tác trên chính collection**, không phải callback được dùng để phá nguồn của một stream pipeline đang duyệt. Nếu cần một danh sách mới, giữ source và lọc:

~~~java
List<String> cleaned = source.stream()
    .filter(s -> !s.isEmpty())
    .collect(Collectors.toList());
~~~

**Lựa chọn giữa mutate và transform phải rõ:** `removeIf` thay đổi collection hiện có; `filter(...).collect(...)` tạo kết quả khác. API nào phù hợp phụ thuộc hợp đồng của đoạn code.

### 3.2. Sửa danh sách ngoài khi duyệt

~~~java
List<String> result = new ArrayList<>();
sales.parallelStream()
    .filter(s -> s.amount() >= 50)
    .forEach(s -> result.add(s.id())); // Không an toàn cho ArrayList chia sẻ
~~~

Đây cũng là **anti-pattern minh họa, không chạy như một test hợp lệ**. `ArrayList.add` không có cơ chế đồng bộ để hỗ trợ nhiều thread cùng ghi. Kết quả có thể thiếu phần tử, hỏng cấu trúc hoặc xuất hiện các hành vi không mong đợi; đôi khi chạy qua được không có nghĩa là an toàn.

Sửa thành:

~~~java
List<String> result = sales.parallelStream()
    .filter(s -> s.amount() >= 50)
    .map(Sale::id)
    .collect(Collectors.toList());
~~~

Hệ thống stream quản lý các **partial result containers** và kết hợp kết quả theo Collector contract. Callback `filter` và `map` chỉ tính từ tham số hiện tại, không truy cập một danh sách kết quả do chúng tự sửa bên ngoài.

Đừng cố “sửa” chỉ bằng `Collections.synchronizedList(new ArrayList<>())`. Cách đó có thể làm từng thao tác add an toàn hơn, nhưng vẫn tăng tranh chấp khóa, không bảo đảm thứ tự khi `forEach` song song, không loại bỏ coupling và không làm callback trở nên stateless.

## 4. “Thread-safe” chưa chắc “stateless”

Lỗi tư duy phổ biến:

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> selected = words.parallelStream()
    .filter(word -> counter.incrementAndGet() % 2 == 0)
    .collect(Collectors.toList());
~~~

Đây là **anti-pattern**. `AtomicInteger.incrementAndGet()` giúp phép tăng là atomic, nhưng câu hỏi “từ nào được chọn?” phụ thuộc **thứ tự thread nào gọi predicate trước**. Trong parallel stream, thứ tự đánh giá predicate không nhất thiết là encounter order. Kết quả có thể khác giữa các lượt chạy ngay cả khi counter không mất cập nhật.

**Atomicity chỉ giải quyết một phần thread safety**, không biến hàm phụ thuộc thứ tự đánh giá thành hàm stateless. Nếu muốn “lấy phần tử tại chỉ số chẵn”, hãy diễn đạt bằng **chỉ số** có ý nghĩa, ví dụ:

~~~java
List<String> source = Arrays.asList("a", "b", "c", "d");
List<String> everyOther = IntStream.range(0, source.size())
    .filter(index -> index % 2 == 0)
    .mapToObj(source::get)
    .collect(Collectors.toList());
// ["a", "c"]
~~~

Ở đây quyết định dựa trên **index của nguồn**, không phải số lần callback vô tình được gọi. `IntStream.range`, `mapToObj` và `collect` có từ Java 8. Nếu source có thể thay đổi đồng thời, cần snapshot hoặc bảo vệ source trước, vì việc dùng index không tự bảo đảm source ổn định.

### Không dùng mutable boolean flag để điều khiển pipeline

~~~java
AtomicBoolean enabled = new AtomicBoolean(true);

List<String> result = words.parallelStream()
    .filter(word -> enabled.get())
    .collect(Collectors.toList());
~~~

Nếu thread khác đổi `enabled` giữa lúc chạy, cùng một phép xử lý có thể chọn những phần tử khác nhau mà không có quy tắc nghiệp vụ rõ. Để tạo một **quyết định nhất quán cho cả batch**, đọc flag **trước** rồi truyền một snapshot bất biến:

~~~java
final boolean enabledForThisBatch = enabled.get();
List<String> result = words.stream()
    .filter(word -> enabledForThisBatch)
    .collect(Collectors.toList());
~~~

Nếu nghiệp vụ thực sự yêu cầu thay đổi chính sách theo thời gian, pipeline Stream với predicate stateless có thể không phải mô hình thích hợp; hãy thiết kế xử lý sự kiện hoặc chia batch rõ ràng thay vì giấu giao thức state vào lambda.

## 5. Side effect và stateless là hai trục khác nhau

Một hàm `map` có thể có **side effect** mà giá trị trả ra vẫn không phụ thuộc state ngoài:

~~~java
List<Integer> lengths = words.stream()
    .map(word -> {
        System.out.println(word);
        return word.length();
    })
    .collect(Collectors.toList());
~~~

Kết quả độ dài có thể được tính theo input, nhưng thao tác in ra là **side effect**. Không nên dựa vào thứ tự, số lần hay thread chạy đoạn in trong intermediate operations, trừ khi đặc tả của thao tác cụ thể bảo đảm điều đó.

Tương tự, một hàm có thể **đọc state mutable** mà không trực tiếp ghi ra đâu:

~~~java
Predicate<String> matchesCurrentPrefix =
    word -> word.startsWith(config.getPrefix());
~~~

Đây là ví dụ phụ thuộc `config` của ứng dụng. Nếu `config.getPrefix()` có thể trả giá trị khác nhau **trong lúc pipeline chạy**, predicate trở thành stateful theo nghĩa của Stream contract. Nếu cấu hình là bất biến trong batch, ta có thể snapshot rõ ràng:

~~~java
final String prefixForBatch = config.getPrefix();
Predicate<String> matchesPrefix =
    word -> word.startsWith(prefixForBatch);
~~~

Đối với `String` bất biến, giá trị `prefixForBatch` là snapshot trực tiếp. Với một object mutable phức tạp, **chỉ copy reference chưa đủ**: cần tạo bản sao dữ liệu theo nhu cầu hoặc bảo đảm bất biến phù hợp.

### Tính thuần (*pure*) và deterministic là mục tiêu hữu ích

Một behavioral parameter dễ suy luận thường là hàm mà:
- Kết quả chỉ phụ thuộc các đối số và cấu hình bất biến.
- Không sửa source, external accumulator hoặc shared fields.
- Không phụ thuộc thứ tự đánh giá hay thread thực thi.
- Không che giấu I/O hoặc cập nhật tài nguyên nếu không cần thiết.

Ví dụ:

~~~java
Function<String, String> normalize = s -> s.trim().toLowerCase(Locale.ROOT);
~~~

Hàm xử lý `String` đầu vào và trả `String` mới. Với đầu vào không null và một `Locale.ROOT` cụ thể, ý nghĩa rõ ràng. Đối với các ứng dụng cần xử lý Unicode và whitespace nâng cao, `String.strip()` từ Java 11 có thể phù hợp hơn `trim()` tùy quy tắc; cả hai vẫn là API hợp lệ nhưng không hoàn toàn tương đương.

Không phải ứng dụng nào cũng cần “functional programming thuần” tuyệt đối. Điểm quan trọng là **tách phần biến đổi dữ liệu ra khỏi phần side effects có chủ ý**.

## 6. Thay biến đếm/sum bên ngoài bằng terminal reduction

### 6.1. Tính tổng bằng `mapToInt().sum()`

Cách không nên dùng:

~~~java
AtomicInteger total = new AtomicInteger();
sales.parallelStream().forEach(sale -> total.addAndGet(sale.amount()));
int result = total.get();
~~~

Vì `AtomicInteger` atomic, ví dụ chỉ tính tổng này có thể đúng nếu dữ liệu ổn định và không có tương tác ngoài. Tuy nhiên nó vẫn duy trì **shared accumulator bên ngoài**, tạo tranh chấp trên cùng một ô nhớ và làm phức tạp lifecycle. API Stream đã có phép tổng chuyên dụng:

~~~java
int total = sales.parallelStream()
    .mapToInt(Sale::amount)
    .sum();
~~~

Mã thứ hai không cần external state. `IntStream.sum()` diễn đạt ý định chính xác hơn và tránh boxing không cần thiết. **Lưu ý về overflow:** tổng `int` có thể tràn; nếu dữ liệu nghiệp vụ cần phạm vi lớn hơn, cân nhắc `mapToLong(...).sum()` hoặc `BigDecimal` và chính sách kiểm tra tràn số thích hợp. Việc bỏ mutable state không tự động giải quyết overflow.

### 6.2. Tổng bằng `reduce`

~~~java
int total = sales.parallelStream()
    .map(Sale::amount)
    .reduce(0, Integer::sum);
~~~

Ở đây:
- `0` là **identity** cho phép cộng.
- `Integer::sum` là phép gộp **associative** trên các giá trị `int` theo ngữ nghĩa Java.
- Các phần có thể được chia ra xử lý và kết hợp mà không cần một biến `total` chung.

Với số thực floating point, cần nhớ phép cộng `double` không hoàn toàn associative do rounding; kết quả khi thay đổi thứ tự gom có thể khác chút ít. Khi cần kết quả tài chính có quy tắc làm tròn chặt, chọn kiểu số/thiết kế reduction phù hợp.

### 6.3. Không dùng `reduce` để sửa cùng một container mutable

Sai lầm điển hình:

~~~java
List<String> shared = new ArrayList<>();
List<String> result = words.parallelStream()
    .reduce(shared,
        (acc, value) -> { acc.add(value); return acc; },
        (left, right) -> { left.addAll(right); return left; });
~~~

Đây là **anti-pattern**, không phải một `reduce` an toàn. `shared` là **cùng một identity object mutable**, không phải một identity value bất biến có thể gộp tùy ý. Các accumulator/combiner sửa object bên ngoài khiến contract `reduce` bị phá, đặc biệt trong parallel execution.

Dùng `collect` cho mutable reduction:

~~~java
List<String> result = words.parallelStream()
    .collect(ArrayList::new, List::add, List::addAll);
~~~

`collect(supplier, accumulator, combiner)` có thể tạo các container riêng cho từng phần việc, rồi kết hợp theo contract; không cần một `shared` list duy nhất do callback ngoài nắm giữ. Với trường hợp đơn giản, dùng `collect(Collectors.toList())` còn rõ hơn.

## 7. Mutable reduction đúng: `collect` sở hữu trạng thái trung gian

`collect` vẫn sử dụng **mutable state**, nhưng điểm khác biệt rất quan trọng là **state được quản lý bên trong terminal operation**, không phải một collection ngoài bị nhiều callback tự ý sửa.

~~~java
List<String> ids = sales.parallelStream()
    .map(Sale::id)
    .collect(ArrayList::new, List::add, List::addAll);
~~~

Ba hàm cung cấp:
1. **Supplier** tạo `ArrayList` mới cho phần tích lũy.
2. **Accumulator** thêm một phần tử vào container được giao.
3. **Combiner** nối các container trung gian.

Đây là một *mutable reduction* hợp lệ vì các tác vụ không phải cùng cập nhật một danh sách kết quả toàn cục. **Không tái sử dụng một instance có sẵn trong supplier**:

~~~java
List<String> shared = new ArrayList<>();

// SAI: supplier liên tục trả cùng một instance.
List<String> result = words.parallelStream()
    .collect(() -> shared, List::add, List::addAll);
~~~

Supplier phải tạo **fresh result container** khi cần. Nếu supplier luôn trả cùng một object, các partial accumulations có thể cùng sửa object, phá tính độc lập và gây kết quả bất thường.

### Collector chuẩn thường rõ hơn

~~~java
List<String> ids = sales.stream()
    .map(Sale::id)
    .collect(Collectors.toList());
~~~

`Collectors.toList()` không cam kết loại list, độ sửa được, thread safety hay khả năng serialization của kết quả; nếu **cần một ArrayList sửa được cụ thể**, viết:

~~~java
List<String> mutableIds = sales.stream()
    .map(Sale::id)
    .collect(Collectors.toCollection(ArrayList::new));
~~~

Với JDK 16+, `Stream.toList()` là lựa chọn gọn:

~~~java
List<String> ids = sales.stream().map(Sale::id).toList();
~~~

Nhưng `Stream.toList()` trả danh sách **không sửa được**, khác với việc yêu cầu một `ArrayList` cụ thể. **Đây là lưu ý phiên bản**, không phải lý do bỏ Stream API hiện đại. Khi code phải chạy trên Java 8, dùng `collect` với collector tương thích.

## 8. Thống kê và phân nhóm mà không dùng `Map` chia sẻ

Cách phụ thuộc state ngoài:

~~~java
Map<String, Integer> totals = new HashMap<>();
sales.stream().forEach(sale ->
    totals.merge(sale.category(), sale.amount(), Integer::sum));
~~~

Ví dụ tuần tự có thể cho tổng đúng, nhưng ý định “gom tổng theo nhóm” bị đưa vào side effect. Nếu chạy song song, `HashMap` chia sẻ không an toàn để cập nhật đồng thời.

Thay bằng:

~~~java
Map<String, Integer> totals = sales.parallelStream()
    .collect(Collectors.groupingBy(
        Sale::category,
        TreeMap::new,
        Collectors.summingInt(Sale::amount)));
~~~

`groupingBy` và `summingInt` tạo phép **reduction có cấu trúc**, còn `TreeMap::new` xác định loại Map cho kết quả để in theo key có thứ tự ổn định. Trong chương trình runnable, dữ liệu `food` và `book` được tổng hợp thành `{book=110, food=170}`.

Đếm phần tử theo nhóm:

~~~java
Map<String, Long> counts = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::category,
        TreeMap::new,
        Collectors.counting()));
~~~

Kết quả sample là `{book=2, food=2}`.

**Không kết luận** rằng `groupingBy` luôn cho Map có thứ tự key: overload không chỉ định map factory không cam kết loại Map cụ thể. Dùng `TreeMap::new` trong demo để output ổn định khi quan sát.

### `groupingByConcurrent` là một lựa chọn riêng, không phải “mặc định tốt hơn”

Khi không cần encounter order của những giá trị bên trong nhóm và cần concurrency phù hợp, có thể xem xét `Collectors.groupingByConcurrent(...)`. Nó có **concurrent collector semantics** và các ràng buộc tương ứng, nhưng:

- Không tự biến key classifier phụ thuộc state ngoài thành stateless.
- Không tự bảo đảm thứ tự phần tử trong collection theo từng key.
- Không mặc nhiên nhanh hơn: phụ thuộc dữ liệu, tranh chấp, số nhóm và chi phí hợp nhất.
- Không nhất thiết cho cùng kiểu map/order với `groupingBy(..., TreeMap::new, ...)`.

Nếu thứ tự theo encounter order quan trọng, cần chọn collector/source/order semantics phù hợp và **kiểm thử kết quả**, không chỉ tin rằng “parallel luôn nhanh hơn”.

## 9. Khi nào callback thật sự được chạy?

Một nhầm lẫn quan trọng là coi mọi callback của stream luôn được gọi **mỗi phần tử đúng một lần**.

Ví dụ:

~~~java
long count = Stream.of("a", "b", "c")
    .peek(value -> audit(value))
    .count();
~~~

**Không dùng đoạn này để ghi audit bắt buộc.** `peek` là intermediate operation; theo Javadoc, một stream implementation có thể loại bỏ một số stage/callback nếu chứng minh chúng không cần thiết cho kết quả terminal operation. Với nguồn `SIZED` thích hợp, `count()` có thể xác định kích thước mà không gọi `peek`. Câu lệnh trên có thể trả 3 nhưng **không hề thực hiện audit**.

Cùng rủi ro xuất hiện nếu dùng:

~~~java
List<String> result = words.stream()
    .map(word -> {
        saveAuditRecord(word);  // Không nên đặt side effect bắt buộc ở đây.
        return word.toUpperCase(Locale.ROOT);
    })
    .collect(Collectors.toList());
~~~

Đây là mã minh họa phụ thuộc `saveAuditRecord` của ứng dụng. Dù pipeline cụ thể thường thực hiện mapper, không nên suy ra callback side effects có **lịch trình, thread, thứ tự hoặc số lần chạy được bảo đảm** ngoài những cam kết của operation.

### `peek` phù hợp với quan sát/debug có kiểm soát

~~~java
List<String> values = words.stream()
    .peek(word -> System.out.println("seen=" + word))
    .map(String::trim)
    .collect(Collectors.toList());
~~~

Có thể hữu ích tạm thời khi debug, nhưng không phải cơ chế logging/audit cốt lõi. `peek` với parallel stream có thể được gọi từ thread nào và thứ tự nào tùy execution; với short-circuit/optimization, số lần gọi cũng có thể khác điều người viết suy nghĩ.

Nếu audit là một **hành vi nghiệp vụ bắt buộc**, đặt nó ở terminal operation có contract side effect thích hợp hoặc tách thành bước tường minh, có chính sách lỗi, retry, idempotency và ordering rõ. Không “ẩn” nghiệp vụ đó trong `map`/`filter`/`peek`.

## 10. `forEach` và `forEachOrdered`: side effects có chủ đích

Không phải mọi side effect trong Stream đều bị cấm. `forEach` là **terminal operation dùng `Consumer`**, hợp lý khi mục tiêu thực sự là **thực hiện một hành động cho mỗi phần tử**, chẳng hạn xuất dữ liệu tới sink đã được thiết kế cho điều kiện thực thi tương ứng.

~~~java
sales.stream()
    .map(Sale::id)
    .forEach(System.out::println);
~~~

Khi chạy tuần tự với encounter-ordered List, output thường theo thứ tự nguồn. Với parallel stream:

~~~java
sales.parallelStream()
    .map(Sale::id)
    .forEach(System.out::println);
~~~

**Không có bảo đảm encounter order** của `forEach` trên parallel pipeline; các side effects cũng có thể diễn ra trên nhiều thread.

Khi một nguồn có encounter order và cần tuân theo thứ tự ấy:

~~~java
IntStream.rangeClosed(1, 4)
    .parallel()
    .forEachOrdered(System.out::print);
System.out.println();
~~~

Trong chương trình runnable, output `orderedTerminal=1234` là ổn định về encounter order. Theo hợp đồng `forEachOrdered`, hành động cho một phần tử **happens-before** hành động cho phần tử kế tiếp trong encounter order. Dẫu vậy:

- `forEachOrdered` vẫn là **side effect terminal operation**, không phải collector để tạo dữ liệu.
- Hạn chế order có thể giảm cơ hội song song hóa.
- Không biến I/O bên ngoài thành một transaction duy nhất hay bảo đảm exactly-once khi toàn bộ ứng dụng có lỗi/retry.
- Nếu nguồn **không có encounter order**, không được tự kỳ vọng thứ tự có ý nghĩa của dữ liệu.

Nếu mục tiêu chỉ là tạo một danh sách có thứ tự, thường nên dùng `collect(Collectors.toList())` trên nguồn có encounter order hoặc `toList()` trên JDK hỗ trợ, thay vì `forEachOrdered(sharedList::add)`.

## 11. Thứ tự kết quả khác thứ tự thực thi callback

Java Stream phân biệt:

- **Encounter order** của source/pipeline (ví dụ `List` có encounter order; `HashSet` không cam kết một encounter order cụ thể).
- **Thứ tự tạo ra kết quả** của những terminal/intermediate operations có hợp đồng giữ order.
- **Thứ tự và thread chạy behavioral parameters** trong parallel execution.

Ví dụ:

~~~java
List<String> ids = sales.parallelStream()
    .filter(sale -> sale.amount() >= 50)
    .map(Sale::id)
    .collect(Collectors.toList());
~~~

Nếu `sales` là `List` có encounter order và pipeline vẫn ordered, kết quả List tuân theo thứ tự encounter như `[A1, B2, C3]`. Tuy nhiên **không suy ra** rằng mapper cho A1 luôn chạy trước mapper cho B2. Pipeline có thể chia dữ liệu thành phần và kết hợp kết quả sau.

Điều này giải thích vì sao code dạng:

~~~java
AtomicInteger sequence = new AtomicInteger();
List<String> numbered = sales.parallelStream()
    .map(sale -> sequence.incrementAndGet() + ":" + sale.id())
    .collect(Collectors.toList());
~~~

là một thiết kế có vấn đề nếu muốn “số thứ tự theo source”: index được cấp theo **thứ tự callback chạy**, không phải encounter order. Dù collector trả List theo encounter order, những số đầu dòng có thể không khớp index.

Nếu cần index gắn với source List không đổi:

~~~java
List<String> numbered = IntStream.range(0, sales.size())
    .mapToObj(i -> (i + 1) + ":" + sales.get(i).id())
    .collect(Collectors.toList());
~~~

Số thứ tự được tính từ **index ổn định**, không từ side effect counter. Hãy bảo đảm List không bị sửa trong lúc đọc; việc dùng index không sửa được lỗi dữ liệu bị thay đổi đồng thời.

## 12. Khi cần snapshot dữ liệu trước pipeline

Một cách tránh phụ thuộc state ngoài là **chốt đầu vào cho một lượt xử lý**. Ví dụ:

~~~java
List<String> mutable = new ArrayList<>(Arrays.asList("x", "y"));
List<String> snapshot = new ArrayList<>(mutable);
mutable.set(0, "changed");

List<String> stable = snapshot.stream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
// stable = ["X", "Y"]
~~~

Kết quả của pipeline trên snapshot không phụ thuộc vào `mutable.set(0, "changed")` **đã xảy ra sau khi tạo snapshot**.

**Đây là shallow copy:** các phần tử `String` bất biến nên phù hợp. Nếu List chứa các object mutable như `Sale` với field được phép sửa, `new ArrayList<>(original)` chỉ sao chép **tham chiếu**, không sao chép trạng thái trong từng object. Muốn một batch snapshot thực sự ổn định, có thể cần:

- Immutable value objects/records với dữ liệu không đổi.
- Chuyển sang DTO/value snapshot ngay tại boundary.
- Copy sâu các phần cần thiết.
- Đọc dưới lock hoặc từ transactional snapshot khi dữ liệu bị cập nhật đồng thời.
- Dùng versioning/snapshot semantics do data source hỗ trợ.

### Nguồn có thể đổi trước terminal operation

Stream intermediate operations thường lazy:

~~~java
List<String> items = new ArrayList<>(Arrays.asList("a", "b"));
Stream<String> stream = items.stream().map(String::toUpperCase);

items.add("c"); // Thay đổi TRƯỚC terminal operation.
List<String> result = stream.collect(Collectors.toList());
~~~

Đây là ví dụ minh họa. Với nguồn collection thường và stream chưa bắt đầu traversal, các thay đổi **trước terminal operation** thường được phản ánh trong dữ liệu mà stream duyệt; `result` có thể chứa `[A, B, C]` theo semantics source đó. Không nên dựa vào giả định “tạo `stream` là đã snapshot dữ liệu”. Khi source thay đổi **trong lúc** traversal, đó là một tình huống khác, có thể vi phạm non-interference và gây lỗi.

Tốt hơn nếu tính toán đòi dữ liệu bất biến:

~~~java
List<String> snapshot = new ArrayList<>(items);
List<String> result = snapshot.stream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
~~~

Nếu có writer khác đồng thời sửa `items` ngay trong khi copy, việc `new ArrayList<>(items)` cũng không phải cơ chế snapshot thread-safe; cần coordination phù hợp.

## 13. Stateful intermediate operations không giống stateful lambda

Java Stream có những **stateful intermediate operations hợp pháp**:

- `distinct()` theo dõi phần tử đã thấy để loại trùng.
- `sorted()` cần sắp xếp dữ liệu.
- `limit(n)` và `skip(n)` có thể tạo ràng buộc về vị trí/encounter order, nhất là ở parallel stream.

Chúng có thể duy trì state **bên trong implementation của stream**, theo contract được thư viện quản lý. Điều này **không cho phép** lập trình viên mặc định đưa mutable state ngoài vào callback của chúng.

Ví dụ:

~~~java
List<Integer> sortedUnique = numbers.parallelStream()
    .distinct()
    .sorted()
    .collect(Collectors.toList());
~~~

Đây là dạng dùng các operations có state bên trong nhưng vẫn có contract rõ. Ngược lại:

~~~java
Set<Integer> seen = new HashSet<>();
List<Integer> unique = numbers.parallelStream()
    .filter(seen::add)
    .collect(Collectors.toList());
~~~

là **anti-pattern**: `HashSet` ngoài không thread-safe, và predicate trả true/false tùy state đang biến đổi. Thay bằng `distinct()`, vốn được thiết kế đúng cho nhiệm vụ loại trùng.

**Quy tắc:** “Stream operation có state nội bộ” không đồng nghĩa “callback của người dùng được phép stateful”.

## 14. Khi nào một Collector là concurrent?

Một Collector có thể báo các characteristics như:

- `CONCURRENT`: accumulator có thể được gọi đồng thời trên một result container nếu điều kiện của stream/collector cho phép.
- `UNORDERED`: collector không cam kết bảo toàn encounter order.
- `IDENTITY_FINISH`: finisher là identity theo quy định của contract.

Không nên tự gắn `CONCURRENT` cho một custom collector dùng `ArrayList` hoặc `HashMap` không đồng bộ. Việc đánh dấu sai có thể làm stream framework đưa nhiều thread ghi cùng một container và tạo race.

Nếu viết custom collector, cần đảm bảo:
1. Supplier tạo container mới hợp lệ.
2. Accumulator và combiner có tương thích; combiner phải associative theo contract.
3. Các bước không phụ thuộc mutable external state.
4. Characteristics được khai báo **đúng với implementation**.
5. Kết quả song song tương đương kết quả tuần tự theo quan hệ equivalence được thiết kế.
6. Nếu accumulator được phép chạy đồng thời trên một container, container và operation đó phải thực sự hỗ trợ.

Trường hợp thông thường, **ưu tiên `Collectors` dựng sẵn** như `toList`, `toSet`, `groupingBy`, `partitioningBy`, `summingInt`, `counting` hoặc `joining` thay vì tự cài Collector. Các collector dựng sẵn giúp biểu đạt loại reduction cần làm và tránh viết nhầm cấu trúc đồng bộ/combiner.

## 15. Tách tính toán và side effects

Trong ứng dụng thực tế, có thể vẫn cần ghi database, gửi email, xuất file, log event hoặc gọi API ngoài. Cách tiếp cận đơn giản:

**Bước 1 — biến đổi và quyết định bằng pipeline:**

~~~java
List<Notification> planned = users.stream()
    .filter(StreamStateDemo::isEligible)
    .map(StreamStateDemo::toNotification)
    .collect(Collectors.toList());
~~~

Đoạn này **chỉ minh họa kiến trúc**; `Notification`, `users`, `isEligible` và `toNotification` thuộc ứng dụng, không được định nghĩa trong chương trình runnable ở phần 17. Những helper ấy cần được thiết kế không phụ thuộc external mutable state khi chạy Stream.

**Bước 2 — đưa kết quả sang nơi thực hiện side effects:**

~~~java
for (Notification notification : planned) {
    notificationSender.send(notification);
}
~~~

Đây cũng là pseudocode Java theo ngữ cảnh ứng dụng, không phải file biên dịch độc lập. Ý đồ tách bạch:

- Pipeline tạo **kế hoạch hành động** là dữ liệu rõ ràng.
- Vòng lặp/đơn vị xử lý chuyên trách thực thi các hành động I/O, có thể bổ sung retry, error handling, transaction, idempotency key, rate limiting và audit phù hợp.
- Nếu một phần I/O thất bại, ta biết kết quả tính toán đã được chốt chứ không phải việc tính toán và gửi xen kẽ khó kiểm soát.

**Không phải Stream bảo đảm exactly-once delivery.** Nếu yêu cầu transactional messaging, dùng giải pháp ứng dụng như outbox pattern, idempotent consumer hoặc workflow phù hợp. Mục đích của việc tránh mutable state bên ngoài là **giảm coupling và bảo toàn semantics của pipeline**, không tự động cung cấp giao thức phân tán.

### Vẫn có nơi `forEach` hợp lý

Nếu nguồn nhỏ, chạy tuần tự và mỗi phần tử cần được in ra, `items.forEach(System.out::println)` là hoàn toàn hợp lý. Nhưng nếu mục tiêu là **xây dựng một cấu trúc dữ liệu**, dùng `collect`; nếu mục tiêu là **tính một giá trị**, dùng `reduce`/`sum`/`count`; nếu mục tiêu là **side effect nghiệp vụ**, tách thiết kế đó ra và xác định rõ ordering/threading/error semantics.

## 16. Những câu hỏi chọn API khi refactor

| Mục đích | Dạng dễ rủi ro | Cách diễn đạt thường tốt hơn |
| --- | --- | --- |
| Lấy danh sách IDs | `forEach(result::add)` với result ngoài | `map(Sale::id).collect(toList())` |
| Tổng tiền | `forEach(x -> total.addAndGet(x.amount()))` | `mapToInt(Sale::amount).sum()` |
| Đếm phần tử | `forEach(x -> counter.incrementAndGet())` | `count()` |
| Nhóm theo category | `forEach(x -> map.computeIfAbsent(...).add(x))` trên map ngoài | `collect(groupingBy(...))` |
| Tổng theo category | `forEach(x -> totals.merge(...))` trên map ngoài | `collect(groupingBy(..., summingInt(...)))` |
| Nối text | `forEach(builder::append)` trên StringBuilder ngoài | `map(...).collect(joining(","))` |
| Loại trùng | `filter(seen::add)` với Set ngoài | `distinct()` |
| Lọc theo thứ tự index | `filter(x -> counter.incrementAndGet()%2==0)` | `IntStream.range(0,size).filter(i -> i%2==0)` |
| Kiểm tra điều kiện | `forEach(x -> flag.set(...))` | `anyMatch`, `allMatch`, `noneMatch` |
| Lấy phần tử đầu hợp lệ | `forEach(x -> { if (...) first.set(x); })` | `filter(...).findFirst()` |
| Lấy một phần tử hợp lệ bất kỳ | Biến kết quả cập nhật tranh chấp | `filter(...).findAny()` khi không cần thứ tự |
| Audit bắt buộc | `peek(audit::write)` | Tách thành bước xử lý side effect rõ ràng |
| Loại bỏ phần tử khỏi nguồn | `source.stream().forEach(source::remove)` | `source.removeIf(predicate)` hoặc tạo list mới |
| Lọc theo cấu hình | Predicate đọc config live liên tục | Snapshot config bất biến cho một batch |
| In theo encounter order khi parallel | `parallel().forEach(print)` | `parallel().forEachOrdered(print)` nếu cần và hiểu chi phí |
| Thu gom từ parallel stream | `sharedArrayList::add` | `collect` hoặc collector phù hợp |

**Lưu ý:** `findAny()` chủ đích có thể trả một phần tử bất kỳ phù hợp; không thay `findFirst()` khi ứng dụng cần “đầu tiên theo encounter order”. Tương tự, `anyMatch`/`allMatch` có thể short-circuit, nên callback không phù hợp để thực hiện side effects “cho mọi phần tử”.

## 17. Chương trình Java 17 hoàn chỉnh, đã kiểm chứng

Chương trình minh họa cách dùng **cấu hình bất biến trong callback**, **`sum`/`groupingBy`/`counting`**, **collector sở hữu container**, **nguồn snapshot** và **`forEachOrdered`** khi thứ tự terminal side effect là yêu cầu thật. Không đưa các anti-pattern có data race vào chương trình chạy.

Lưu tên file **StreamStateDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class StreamStateDemo {
    static final class Sale {
        private final String id;
        private final String category;
        private final int amount;
        Sale(String id, String category, int amount) {
            this.id = id;
            this.category = category;
            this.amount = amount;
        }
        String id() { return id; }
        String category() { return category; }
        int amount() { return amount; }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
                new Sale("A1", "food", 120),
                new Sale("B2", "book", 80),
                new Sale("C3", "food", 50),
                new Sale("D4", "book", 30));

        final int threshold = 50;
        List<String> eligible = sales.stream()
                .filter(sale -> sale.amount() >= threshold)
                .map(Sale::id)
                .collect(Collectors.toList());
        System.out.println("eligible=" + eligible);

        int sum = sales.parallelStream()
                .mapToInt(Sale::amount).sum();
        System.out.println("total=" + sum);

        Map<String, Integer> totals = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        Sale::category, TreeMap::new,
                        Collectors.summingInt(Sale::amount)));
        System.out.println("byCategory=" + totals);

        Map<String, Long> counts = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category, TreeMap::new,
                        Collectors.counting()));
        System.out.println("counts=" + counts);

        List<String> parallelOrdered = sales.parallelStream()
                .filter(sale -> sale.amount() >= threshold)
                .map(Sale::id)
                .collect(Collectors.toList());
        System.out.println("parallelOrdered=" + parallelOrdered);

        List<String> viaCollector = sales.parallelStream()
                .map(Sale::id)
                .collect(ArrayList::new, List::add, List::addAll);
        System.out.println("ownedAccumulator=" + viaCollector);

        List<String> mutable = new ArrayList<>(Arrays.asList("x", "y"));
        List<String> snapshot = new ArrayList<>(mutable);
        mutable.set(0, "changed");
        List<String> stable = snapshot.stream()
                .map(String::toUpperCase)
                .collect(Collectors.toList());
        System.out.println("sourceNow=" + mutable);
        System.out.println("snapshotResult=" + stable);

        Optional<String> firstOver100 = sales.stream()
                .filter(sale -> sale.amount() > 100)
                .map(Sale::id).findFirst();
        System.out.println("firstOver100=" + firstOver100.orElse("none"));

        String joined = sales.stream().map(Sale::id)
                .collect(Collectors.joining(","));
        System.out.println("joined=" + joined);

        System.out.print("orderedTerminal=");
        IntStream.rangeClosed(1, 4).parallel()
                .forEachOrdered(System.out::print);
        System.out.println();
        System.out.println("checks=PASS");
    }
}
~~~

Dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 StreamStateDemo.java
java StreamStateDemo
~~~

Stdout **đã biên dịch và chạy thực tế**:

~~~text
eligible=[A1, B2, C3]
total=280
byCategory={book=110, food=170}
counts={book=2, food=2}
parallelOrdered=[A1, B2, C3]
ownedAccumulator=[A1, B2, C3, D4]
sourceNow=[changed, y]
snapshotResult=[X, Y]
firstOver100=A1
joined=A1,B2,C3,D4
orderedTerminal=1234
checks=PASS
~~~

### Giải thích các kết quả

1. **`eligible`:** `threshold` cố định là 50; `filter` không cần counter hoặc configuration live, `map` lấy ID và `collect` trả dữ liệu mới.
2. **`total=280`:** `parallelStream` tính tổng bằng phép reduction `mapToInt(...).sum()`, không có `AtomicInteger` bên ngoài. `120+80+50+30=280`.
3. **`byCategory`:** `groupingBy` + `summingInt` tổng hợp `book=80+30=110`, `food=120+50=170`, còn `TreeMap::new` giữ thứ tự in key ổn định cho demo.
4. **`counts`:** `Collectors.counting()` đếm hai phần tử mỗi nhóm. Dùng Map rõ ràng hơn tăng counter ngoài.
5. **`parallelOrdered`:** các callback có thể chạy khác thứ tự, nhưng collector trên nguồn List có encounter order vẫn cho `[A1, B2, C3]`.
6. **`ownedAccumulator`:** `collect(ArrayList::new, List::add, List::addAll)` dùng những container được supplier tạo ra; không sửa một `ArrayList` toàn cục.
7. **`sourceNow` và `snapshotResult`:** sau khi copy List String, thay source gốc không ảnh hưởng snapshot; vì phần tử `String` bất biến nên shallow copy là đủ cho ví dụ.
8. **`firstOver100=A1`:** `findFirst` chốt phần tử đầu thỏa điều kiện dựa theo encounter order.
9. **`joined`:** `Collectors.joining(",")` tạo chuỗi từ IDs, không cần StringBuilder capture bên ngoài.
10. **`orderedTerminal=1234`:** `forEachOrdered` thể hiện một side effect có chủ đích theo thứ tự nguồn ngay cả khi stream được đánh dấu parallel. Nó không phải lời khuyên dùng `forEachOrdered` thay collector để thu thập dữ liệu.
11. **`checks=PASS`:** chương trình đã kết thúc bình thường; ví dụ này là minh họa kết quả thực tế đã chạy, còn các code anti-pattern ở phần lý thuyết **không được chạy như khuyến nghị**.

Bản runnable dùng `Arrays.asList`, `Collectors`, `IntStream`, `Optional` và các Stream APIs có từ Java 8; cờ biên dịch chọn JDK 17 để kiểm tra trong toolchain hiện đại. Không cần `Stream.toList()` hay records trong chương trình này.

## 18. Những lỗi khó phát hiện trong dự án thực tế

| Lỗi | Triệu chứng | Nguyên nhân và hướng xử lý |
| --- | --- | --- |
| Dùng `parallelStream().forEach(results::add)` | Thiếu phần tử, lỗi ngẫu nhiên | `ArrayList` bên ngoài không thread-safe; dùng `collect` |
| Dùng `AtomicInteger` để chọn phần tử thứ N | Kết quả thay đổi qua các lượt chạy | Atomic không cố định thứ tự callback; dùng index/source semantics |
| Sửa `source` trong callback | `ConcurrentModificationException` hoặc dữ liệu sai | Vi phạm non-interference; dùng `removeIf` riêng hoặc list mới |
| Ghi audit trong `peek` | Có lượt mất log | Intermediate stage có thể bị bỏ qua; tách side effect bắt buộc |
| Dùng `count()` rồi giả định `map` luôn được gọi | Callback không chạy như mong muốn | Tối ưu hóa không ảnh hưởng kết quả count; không dùng side effect để tính đúng |
| Đọc mutable field trong `filter` | Kết quả phụ thuộc timing | Snapshot cấu hình/đầu vào |
| Capture `final List` rồi sửa nó | Sai lầm “final là immutable” | final chỉ khóa reference; dùng immutable/snapshot |
| Dùng `reduce` với mutable identity object | Sai kết quả song song | Dùng `collect` với fresh supplier |
| `collect(() -> shared, ...)` | Nhiều worker cùng sửa một container | Supplier phải tạo container mới |
| Dùng `forEach` rồi mong encounter order khi parallel | Log/side effects đảo thứ tự | `forEachOrdered` nếu cần order, hoặc tách xử lý |
| Dùng `groupingByConcurrent` rồi mong mọi List theo thứ tự | Kết quả thứ tự khác dự kiến | Hiểu collector characteristics |
| Nghĩ `Collectors.toList()` luôn là ArrayList sửa được | Phụ thuộc implementation | Dùng `toCollection(ArrayList::new)` khi cần |
| Nghĩ `Stream.toList()` luôn sửa được | `UnsupportedOperationException` khi cố mutate | `Stream.toList()` trả unmodifiable list (Java 16+) |
| Snapshot `List<MutableObject>` bằng copy shallow | Các object con vẫn đổi | Snapshot fields hoặc dùng immutable objects |
| Đưa I/O retry vào `map` | Thao tác không rõ số lần/thứ tự | Tách tính toán và side effect workflow |
| Dùng `findAny()` thay `findFirst()` | Phần tử trả về thay đổi | Chọn theo yêu cầu ordering |
| Dùng cùng một stream hai lần | `IllegalStateException` hoặc hành vi không hợp lệ | Mỗi stream pipeline chỉ được tiêu thụ một lần; tạo stream mới từ source khi cần |
| Cho rằng stream song song luôn nhanh hơn | Hiệu năng giảm vì scheduling/combining | Benchmark dữ liệu và workload thực |
| Cho rằng collection thread-safe là đủ cho mọi lambda | Có thể sai logic theo thứ tự/visibility | Kiểm tra tính stateless và hợp đồng kết quả |
| Cho rằng không có exception nghĩa là code đúng | Race có thể hiếm khi xuất hiện | Kiểm thử quy tắc, thiết kế tránh mutable state ngoài |

## 19. Checklist để review một Stream pipeline

1. **Source là gì?** Có thể bị sửa trong lúc pipeline chạy không? Nếu không phải concurrent source được thiết kế cho điều đó, tránh interference.
2. **Mỗi callback trả kết quả từ input và cấu hình bất biến?** Có đọc counter, time, random state hay mutable singleton không?
3. **Có ghi vào list/map/builder nằm ngoài pipeline?** Nếu có, xem liệu `collect`/`reduce`/`groupingBy`/`joining` giải quyết đúng hơn không.
4. **Có cần thứ tự của callback, hay chỉ thứ tự của kết quả?** Hai yêu cầu khác nhau.
5. **Có dùng parallel stream?** Nếu có, callback có an toàn khi chạy nhiều thread và không phụ thuộc lịch chạy không?
6. **Có thể bị short-circuit hoặc optimization bỏ callback?** Không để side effect bắt buộc trong `peek`/`map`/`filter`.
7. **Identity và combiner của reduction đúng contract?** Đặc biệt tránh mutable identity dùng chung.
8. **Collector có bao giờ trả cùng container cho nhiều supplier invocations?** Nếu có, cần sửa.
9. **Có cần loại collection cụ thể hoặc tính sửa được?** Phân biệt `Collectors.toList`, `toCollection` và `Stream.toList`.
10. **Input snapshot có đủ sâu không?** Shallow copy không đóng băng các phần tử mutable.
11. **Có I/O side effects?** Nên tách workflow, quy định lỗi, retry, idempotency, ordering.
12. **Có đổi từ tuần tự sang song song chỉ vì một cờ?** Kiểm tra lại contract, benchmark và test.
13. **Có thể diễn đạt bằng một operation chuẩn?** `distinct`, `count`, `sum`, `anyMatch`, `findFirst` thường tốt hơn trạng thái ngoài.
14. **Test có xác minh kết quả, chứ không phụ thuộc số lần callback chạy?** Test tập trung vào contract, không vào implementation detail.

## 20. Bài tập tự luyện

1. Cho `List<Integer> numbers`, viết code tính tổng bằng `AtomicInteger` ngoài `forEach` rồi refactor sang `mapToInt(...).sum()`. Giải thích cách mới tốt hơn cả khi xử lý tuần tự.
2. Thử `parallelStream().forEach(sharedList::add)` với dữ liệu lớn trong một bài test cô lập để quan sát rủi ro. **Không dựa vào việc lỗi luôn tái hiện**; hãy sửa bằng `collect(Collectors.toList())`.
3. Với `List<String>` có trùng, giải thích tại sao `filter(seen::add)` là stateful predicate và thay bằng `distinct()`.
4. Dùng `IntStream.range(0, names.size())` để tạo `index:name` theo source order mà không dùng `AtomicInteger`.
5. Viết `groupingBy` + `counting` đếm số sản phẩm theo category. Vì sao dùng `HashMap` ngoài `forEach` có thể tạo rủi ro khi song song?
6. So sánh `reduce(0,Integer::sum)` với `collect(ArrayList::new, List::add, List::addAll)`. Trường hợp nào là immutable reduction, trường hợp nào là mutable reduction?
7. Giải thích vì sao `collect(() -> sharedList, ...)` không phải một supplier tốt cho parallel collector.
8. Hãy viết một ví dụ `Stream.of(...).peek(...).count()`, rồi giải thích vì sao side effect của `peek` không được dùng làm audit bắt buộc.
9. Dùng `findFirst` và `findAny` trên parallel stream; trường hợp nào cần encounter order?
10. Chụp snapshot một `List<String>` rồi thay đổi source gốc trước terminal operation. Kết quả snapshot thay đổi không? Nếu phần tử là object mutable thì khác thế nào?
11. Cho `AtomicBoolean flag` thay đổi theo thời gian, viết code chốt `final boolean forBatch = flag.get()` trước khi tạo predicate. Vì sao phù hợp hơn với xử lý batch?
12. Viết chương trình `parallel().forEach(System.out::println)` và `parallel().forEachOrdered(System.out::println)` với source ordered, mô tả khác biệt được API bảo đảm.
13. Nếu cần phát email cho mỗi người dùng có cùng rule, tách pipeline tạo danh sách `Notification` và bước gửi. Bạn sẽ xử lý lỗi gửi, retry và idempotency thế nào?
14. Tại sao `Stream.toList()` và `Collectors.toList()` không có cùng hợp đồng modifiability? Cho một ví dụ cần `toCollection(ArrayList::new)`.
15. Giải thích vì sao “dùng synchronizedList” chỉ sửa một phần của bài toán chia sẻ mutable state, không giải quyết vấn đề thứ tự, coupling hay collector semantics.
16. Viết test so sánh kết quả tổng nhóm giữa `stream()` và `parallelStream()` với các classifier và accumulator stateless. Không kiểm tra thứ tự thread chạy callbacks.
17. Phân tích trường hợp `config.getCurrentThreshold()` đổi liên tục trong một pipeline dài. Có nên đọc config mỗi callback hay snapshot threshold trước khi xử lý batch?
18. Khi cần debug pipeline bằng `peek`, bạn có thể dựa vào thứ tự log hoặc số lần log để kết luận tính đúng đắn không? Vì sao?

## 21. Tài liệu chuẩn và vẫn còn áp dụng

- [Java SE 17 — java.util.stream package: Non-interference, Statelessness, Side-effects, Reduction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)
- [Java SE 26 — java.util.stream package summary (đặc tả API hiện hành)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Java SE 17 — Stream: map, filter, peek, count, collect, forEach/forEachOrdered](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 17 — Collector và Characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html)
- [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 17 — Spliterator.CONCURRENT](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)
- [Java SE 17 — Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate))

**Kết luận:** Cách thiết kế đáng tin cậy với Java Stream là **giữ nguồn ổn định**, **dùng callback không phụ thuộc state đang thay đổi**, và **để reduction/collector sở hữu trạng thái tích lũy**. Dùng `map`/`filter` để mô tả biến đổi, `sum`/`reduce`/`count` để tổng hợp, `collect`/`groupingBy`/`joining` để tạo kết quả, và dùng terminal side effect khi đó thực sự là mục đích. `AtomicInteger` hay collection synchronized **không thay thế** yêu cầu stateless; pipeline đúng phải giữ semantics dưới những thứ tự thực thi được Stream API cho phép, kể cả khi chạy song song hoặc được tối ưu hóa.
