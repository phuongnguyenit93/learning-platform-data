# Stream là luồng xử lý thay vì nơi lưu dữ liệu (Java 8)

## 1. Hiểu đúng bản chất của `Stream`

Trong Java, **`java.util.stream.Stream<T>` biểu diễn một chuỗi phần tử được xử lý theo một pipeline các thao tác**, chứ **không phải một cấu trúc dữ liệu để lưu trữ phần tử** như `List`, `Set` hoặc mảng. Stream mô tả **nguồn dữ liệu** và **các phép tính sẽ thực hiện trên các phần tử từ nguồn**; những phép tính đó có thể được thực thi khi một **terminal operation** yêu cầu kết quả.

Ví dụ:

```java
List<String> names = Arrays.asList("An", "Binh", "Chi");

List<String> result = names.stream()
        .filter(s -> s.length() >= 3)
        .map(String::toUpperCase)
        .collect(Collectors.toList());
```

Đây là **đoạn code minh họa bên trong một method**, với import từ `java.util` và `java.util.stream.Collectors`. `names` là **collection lưu dữ liệu**; `names.stream()` là **luồng xử lý** đi qua các bước lọc và chuyển đổi. `result` là **collection mới** được tạo ở bước `collect`. Stream ở giữa **không tự giữ một danh sách phần tử đã lọc** để bạn truy cập bằng index.

**Mục tiêu bài học:**

- Phân biệt **data source**, **stream pipeline** và **terminal result**.
- Nắm các đặc điểm cốt lõi: **no storage**, **lazy intermediate operations**, **single-use/consumable**, có thể **short-circuit**, và xử lý tổng hợp.
- Giải thích vì sao `filter`, `map` không tự sửa `List` nguồn, còn `collect` tạo một đích kết quả cụ thể.
- Hiểu cách stream bắt đầu đánh giá và những trường hợp không thể tái sử dụng stream sau terminal operation.
- Áp dụng các nguyên tắc **non-interference** và **stateless behavioral parameters** để tránh lỗi khi source biến đổi hoặc khi chạy parallel.
- Biết khi nào nên dùng `Stream`, khi nào nên giữ `Collection`, và cách chuyển đổi giữa hai mô hình.
- Nhận biết các nhầm lẫn về lazy, side effect, `count`, `forEach`, `Stream.toList()` và vô hạn phần tử.

**Phạm vi:** các nguyên tắc dưới đây được Java 8 đưa vào và **vẫn còn áp dụng trong Java hiện đại**. Bài dùng API hiện hành, không dạy những cơ chế lỗi thời hoặc đã legacy. Ví dụ chính chạy được với JDK 17+ và chỉ sử dụng những tính năng đã có từ Java 8.

## 2. Collection lưu dữ liệu; Stream mô tả phép tính

| Khía cạnh | `Collection` như `List`, `Set` | `Stream` |
| --- | --- | --- |
| Mục tiêu chính | **Quản lý và truy cập phần tử** | **Mô tả và thực thi các phép xử lý tổng hợp** |
| Lưu trữ phần tử | Có; collection nắm giữ/cấu trúc các phần tử | **Không tự là kho chứa phần tử** |
| Truy cập bằng index | `List.get(index)` có thể hỗ trợ | Không có `stream.get(index)` |
| Duyệt lại nhiều lần | Thường tạo iterator mới để duyệt lại collection | Một stream pipeline chỉ được **tiêu thụ một lần** |
| Biến đổi phần tử | Có API như `add`, `remove`, `set` tùy loại | `map`, `filter` mô tả một view xử lý, không tự ghi ngược vào source |
| Kết quả | Collection vẫn quản lý dữ liệu của nó | Terminal operation có thể trả collection, số, boolean, `Optional`, array hoặc thực hiện side effect |
| Tính lazy | Việc gọi `add`/`get` có nghĩa ngay theo contract | Các intermediate operations **lazy**; terminal operation mới kích hoạt xử lý |
| Kích thước | Collection thường hữu hạn và có `size()` | Stream có thể hữu hạn hoặc **không bị giới hạn về số phần tử** |

**Trọng tâm:** Collection trả lời *"Dữ liệu nằm ở đâu, được lưu và truy cập thế nào?"*; Stream trả lời *"Ta muốn thực hiện phép tính nào trên dãy phần tử?"*.

Một `Stream` có thể bắt nguồn từ `List`, `Set`, mảng, `IntStream.range`, một generator, một file/nguồn I/O, hoặc một nguồn có cách cấp phần tử khác. **Stream và nguồn dữ liệu không phải cùng một thực thể.** Tạo stream từ collection không khiến collection trở thành stream hoặc chuyển quyền sở hữu toàn bộ phần tử cho stream.

### Không nhầm với `InputStream`

`java.io.InputStream` là API đọc **bytes từ nguồn vào**; `java.util.stream.Stream<T>` là abstraction xử lý **các phần tử kiểu T** bằng pipeline. Hai lớp có chữ "Stream" nhưng contract khác nhau. Ví dụ `Files.lines(path)` có thể trả `Stream<String>` lấy dữ liệu từ file và cần quản lý tài nguyên phù hợp, nhưng điều đó không biến `Stream<String>` thành một `InputStream`.

## 3. Cấu trúc pipeline: nguồn → intermediate → terminal

Một stream pipeline gồm:

```text
Data source
  │  list / array / generator / file / ...
  ▼
Stream source
  │
  ├── filter(...)      intermediate, lazy
  ├── map(...)         intermediate, lazy
  ├── distinct(...)    intermediate, lazy (có thể giữ state nội bộ)
  └── sorted(...)      intermediate, lazy (có thể cần đệm phần tử)
  │
  ▼
Terminal operation
  ├── collect(...)     -> Collection/Map hoặc kết quả tổng hợp
  ├── count()          -> long
  ├── reduce(...)      -> kết quả gộp
  ├── findFirst()      -> Optional<T>
  ├── anyMatch(...)    -> boolean
  └── forEach(...)     -> side effect (void)
```

**Source:** nơi phát sinh phần tử. Ví dụ `users.stream()` dùng `users` làm nguồn; `IntStream.range(0, 10)` sinh phần tử số nguyên từ 0 đến 9 mà không cần một `List<Integer>` ban đầu.

**Intermediate operation:** nhận một stream và trả **stream mới** để tiếp tục mô tả phép tính, ví dụ `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`, `skip`. **Việc gọi intermediate operation không tự bắt đầu duyệt nguồn.**

**Terminal operation:** yêu cầu kết quả hoặc side effect, ví dụ `collect`, `reduce`, `count`, `sum`, `forEach`, `findFirst`. Với các terminal operation thông thường này, chúng kích hoạt xử lý pipeline và tiêu thụ stream. Các thao tác `iterator()` và `spliterator()` là ngoại lệ chuyên biệt cho phép traversal do caller điều khiển; đừng vì ngoại lệ đó mà bỏ qua tính single-use của stream.

Ví dụ:

```java
long count = java.util.stream.Stream.of("a", "bb", "ccc")
        .filter(s -> s.length() >= 2)
        .count(); // 2
```

`Stream.of(...)` cung cấp nguồn, `filter` mô tả điều kiện, `count` yêu cầu tính số phần tử phù hợp.

## 4. Lazy không có nghĩa là dữ liệu đã được xử lý trước

**Intermediate operations là lazy.** Khi viết:

```java
Stream<String> pipeline = names.stream()
        .filter(s -> !s.isEmpty())
        .map(String::toUpperCase);
```

compiler tạo một **mô tả pipeline**. Lúc này không có danh sách chuỗi in hoa sẵn được materialize chỉ vì bạn gọi `map`, và cũng không có vòng lặp duyệt hết `names` để thực hiện filter ngay tại chỗ.

Khi viết:

```java
List<String> output = pipeline.collect(Collectors.toList());
```

`collect` kích hoạt việc duyệt các phần tử cần thiết, đưa chúng qua các thao tác phù hợp và tạo kết quả collection. Hai đoạn minh họa trên cần import `Stream`, `List`, `Collectors` và biến `names`; chương trình độc lập ở mục 9 sẽ cho thấy điều này qua stdout.

### Trình tự xử lý thường "fused" theo phần tử

Với pipeline tuần tự:

```java
numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .forEach(System.out::println);
```

Java thường có thể xử lý **từng phần tử** qua nhiều stage của pipeline mà không phải tạo một collection trung gian ở mỗi `filter`/`map`. Điều đó khác với cách thủ công:

```java
List<Integer> evens = new ArrayList<>();
for (Integer n : numbers) {
    if (n % 2 == 0) evens.add(n);
}
List<Integer> squares = new ArrayList<>();
for (Integer n : evens) {
    squares.add(n * n);
}
```

Đây là các **mảnh code minh họa trong method**, có `numbers` và import tương ứng. Hai lần tạo `ArrayList` là lựa chọn thủ công của programmer; API stream có thể tổ chức pipeline để tránh materialize các danh sách trung gian như vậy.

**Nhưng không hiểu "no storage" thành "stream không bao giờ cần bộ nhớ trung gian".** Những thao tác **stateful** như `sorted`, `distinct`, một số `limit` trên parallel/ordered pipeline hoặc collector vẫn có thể cần bộ đệm hoặc cấu trúc dữ liệu nội bộ. Stream không phải kho lưu trữ, nhưng **cách thực thi phép tính** vẫn có thể sử dụng memory.

## 5. Terminal operation biến mô tả xử lý thành kết quả

Ví dụ trên danh sách:

```java
List<String> source = Arrays.asList("An", "Binh", "Chi");

List<String> longNames = source.stream()
        .filter(s -> s.length() >= 3)
        .collect(Collectors.toList());
```

Đây là đoạn code minh họa bên trong method, với import `java.util.List`, `java.util.Arrays` và `java.util.stream.Collectors`.

Sau khi chạy:

- `source` vẫn có các phần tử `["An", "Binh", "Chi"]`: thao tác `filter` **không xóa phần tử khỏi collection nguồn**.
- `longNames` chứa `["Binh", "Chi"]`: kết quả đã được **materialize** vào một collection.
- `source` và `longNames` là **hai collection khác nhau**. Tuy nhiên, nếu phần tử là object mutable và bạn chỉ lọc, cả hai collection **có thể tham chiếu cùng những object phần tử**, không có deep copy tự động.

Một Stream không "nhớ" kết quả để lần sau trả lại khi gọi `collect`. Nếu bạn cần một tập kết quả có thể truy cập nhiều lần hoặc truyền qua nhiều nơi, **lưu kết quả** vào một collection hoặc một value object thích hợp.

### Collectors và kết quả materialize

- `collect(Collectors.toList())`: tạo kết quả `List<T>`. Contract **không bảo đảm** loại implementation, mutability, serializability hoặc thread safety cụ thể. Đừng dựa vào `ArrayList` nếu API không cam kết.
- `collect(Collectors.toCollection(ArrayList::new))`: khi thực sự cần một `ArrayList` mới theo contract.
- `collect(Collectors.toSet())`: tạo kết quả Set, nhưng không tự bảo đảm encounter order của Set.
- `collect(Collectors.groupingBy(...))`: materialize dữ liệu thành các nhóm.
- `Stream.toList()`: API được thêm ở **Java 16**, hiện vẫn dùng trong Java hiện đại; kết quả **unmodifiable**. Không dùng nó khi cần source code chạy trực tiếp với Java 8, và không coi nó tương đương hoàn toàn với `Collectors.toList()`.

Một terminal operation cũng có thể trả **scalar** như `long` từ `count()`, `int` từ `sum()`, **boolean** từ `anyMatch`, hoặc **`Optional<T>`** từ `findFirst`. Không phải mọi stream bắt buộc kết thúc bằng một List.

## 6. Stream là single-use: pipeline chỉ được tiêu thụ một lần

Khi một terminal operation đã chạy, stream pipeline được coi là **consumed**. Bạn không thể biến nó thành một collection được duyệt lại vô hạn lần.

```java
Stream<Integer> stream = Stream.of(1, 2, 3);
long count = stream.count();
// stream.collect(Collectors.toList()); // Không được tái sử dụng stream.
```

Đây là snippet trong method có import `Stream`, `Collectors`. Tái sử dụng stream đã consumed vi phạm contract và thường dẫn đến `IllegalStateException`. Java có thể phát hiện một số dạng reuse sớm hơn ngay cả trước terminal operation; **không dựa vào việc exception luôn xuất hiện ở đúng một chỗ** để xử lý logic.

Nếu cần duyệt **nguồn** lần nữa, tạo stream mới:

```java
List<Integer> source = Arrays.asList(1, 2, 3);
long count = source.stream().count();
int sum = source.stream().mapToInt(Integer::intValue).sum();
```

Bạn có thể tạo **nhiều stream khác nhau từ collection nguồn**. Điều đó hoàn toàn khác với việc gọi nhiều terminal operation trên **cùng một instance Stream**.

Nếu API nhận `Supplier<Stream<T>>`, caller có thể gọi `supplier.get()` để tạo **stream mới** mỗi lần, nhưng supplier phải được thiết kế để thực sự tạo pipeline mới và quản lý đúng nguồn/tài nguyên.

## 7. Nguồn không bị sửa bởi `map` và `filter`, nhưng dữ liệu có thể thay đổi bên ngoài

Một stream pipeline dùng `filter`, `map` trên collection **không tự thay đổi cấu trúc collection nguồn**. Ví dụ:

```java
List<String> raw = new ArrayList<>(Arrays.asList(" a ", "b "));
List<String> clean = raw.stream()
        .map(String::trim)
        .collect(Collectors.toList());
```

Sau terminal operation, `raw` vẫn là `[" a ", "b "]`, `clean` là `["a", "b"]`. `map` tạo kết quả mới theo hàm chuyển đổi, **không gọi `raw.set` để ghi ngược**.

Tuy vậy, cần phân biệt ba chuyện:

1. **Stream API không tự sửa source**: đúng với các thao tác thuần như filter/map; không có lời hứa rằng lambda user viết không thể gây side effect.
2. **Lambda vẫn là Java code**: nếu bạn tự gọi `source.add(...)`, sửa shared object hoặc gọi I/O trong lambda, bạn đã đưa side effect vào pipeline. Java Stream không chặn mọi side effect bằng type system.
3. **Collection kết quả không tự deep copy các phần tử**: nếu `filter` trả về cùng các tham chiếu object, thay đổi trạng thái object có thể được nhìn thấy qua source và result. Chỉ có **cấu trúc container kết quả** là riêng biệt theo collector đã tạo nó.

### Non-interference: không sửa nguồn trong lúc duyệt

Tài liệu Stream yêu cầu các behavioral parameters thông thường **không được can thiệp vào nguồn** (*non-interfering*). Nếu stream lấy từ `ArrayList` hay nguồn không hỗ trợ concurrent modification, sửa source **trong lúc terminal operation đang duyệt** có thể gây `ConcurrentModificationException`, kết quả sai hoặc hành vi không xác định theo contract.

Ví dụ **cố ý sai, không đưa vào chương trình runnable**:

```java
List<String> source = new ArrayList<>(Arrays.asList("a", "b"));
source.stream().forEach(s -> source.add(s)); // Không nên làm.
```

Đừng giải thích rằng "stream không lưu dữ liệu nên sửa list thoải mái". Stream lấy dữ liệu từ source và chịu ảnh hưởng cấu trúc/consistency của source. Đối với những concurrent data structures có contract riêng, behavior có thể khác, nhưng không tự suy ra rằng mọi stream là concurrent-safe.

### Source được thay sau terminal operation

Khi `collect` đã hoàn tất, việc sửa `List` nguồn **sau đó** không làm một `List<String>` kết quả đã materialize tự cập nhật lại theo pipeline cũ. Nếu muốn tính kết quả với nguồn mới, tạo **stream mới** và chạy lại phép tính.

Đối với nguồn có đặc điểm **late-binding**, những thay đổi diễn ra **trước khi terminal traversal bắt đầu** có thể được quan sát bởi stream; không nên coi việc gọi `source.stream()` là snapshot cố định trong mọi trường hợp. Nếu cần snapshot, tạo bản sao dữ liệu có chủ đích trước rồi xử lý.

## 8. Short-circuit: không nhất thiết xử lý hết nguồn

Stream có thể **tiêu thụ phần tử chỉ khi cần thiết**. Một số terminal operations kết thúc sớm:

- `findFirst()`: có thể dừng khi tìm được phần tử đầu tiên theo encounter order.
- `anyMatch(predicate)`: có thể dừng khi tìm thấy ít nhất một phần tử phù hợp.
- `allMatch(predicate)`: có thể dừng ở phần tử đầu tiên không phù hợp.
- `noneMatch(predicate)`: có thể dừng khi tìm thấy phần tử phù hợp.
- `limit(n)`: intermediate operation có tính short-circuiting; downstream terminal có thể chỉ cần tối đa n phần tử tùy pipeline.

Ví dụ:

```java
Optional<Integer> first = Stream.of(1, 3, 5, 8, 10)
        .filter(n -> n % 2 == 0)
        .findFirst(); // Optional[8]
```

Đây là snippet trong method với import `Optional` và `Stream`. Không cần đánh giá `10` để biết phần tử chẵn đầu tiên của ordered sequential stream này là `8`.

### Nguồn vô hạn hoặc không giới hạn

Một collection thường có số phần tử hữu hạn, nhưng stream có thể được tạo từ generator không có điểm kết thúc tự nhiên:

```java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .collect(Collectors.toList());
```

Kết quả `[1,2,3,4,5]` trong ví dụ minh họa (cần `List`, `Stream`, `Collectors`). `limit(5)` làm phép xử lý có thể kết thúc. Không gọi `collect(toList())` trên một generator vô hạn **không có bước giới hạn/kết thúc phù hợp** rồi mong nó trả về.

**Lưu ý hiệu năng:** các stateful operations như `sorted` trên một stream vô hạn không bị giới hạn thích hợp có thể không kết thúc, hoặc cần giữ lượng bộ nhớ không kiểm soát được. Lazy giúp tối ưu nhưng không xóa các ràng buộc toán học của phép tính.

## 9. Chương trình Java độc lập: cùng nguồn, pipeline và kết quả khác nhau

Tạo tệp **`StreamPipelineDemo.java`**. Chương trình có một bộ đếm phụ trong `map` **chỉ để minh họa thời điểm xử lý**, không phải cách thiết kế pipeline production. Nó dùng một pipeline tuần tự với `map` ảnh hưởng đến các giá trị được thu thập qua `collect`, sau đó kiểm tra result và source.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamPipelineDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                Arrays.asList("  apple  ", " ", " banana", " pear "));
        AtomicInteger visited = new AtomicInteger();

        Stream<String> pipeline = source.stream()
                .map(s -> {
                    visited.incrementAndGet(); // Demo only: avoid side effects in production.
                    return s.trim();
                })
                .filter(s -> !s.isEmpty())
                .map(String::toUpperCase);

        System.out.println("beforeTerminal=" + visited.get());
        List<String> result = pipeline.collect(Collectors.toList());
        System.out.println("afterTerminal=" + visited.get());
        System.out.println("result=" + result);
        System.out.println("source=" + source);

        source.set(0, "changed"); // Done only after the terminal operation.
        System.out.println("sourceNow=" + source.get(0));
        System.out.println("resultFirst=" + result.get(0));

        try {
            pipeline.collect(Collectors.toList());
        } catch (IllegalStateException expected) {
            System.out.println("reused=illegal");
        }

        List<String> fresh = source.stream()
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .map(String::toUpperCase)
                .collect(Collectors.toList());
        System.out.println("fresh=" + fresh);

        Optional<String> first = Stream.of("ant", "bee", "cat", "dog")
                .filter(s -> s.startsWith("c"))
                .findFirst();
        System.out.println("first=" + first.orElse("none"));

        int sum = IntStream.rangeClosed(1, 5)
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .sum();
        System.out.println("sumEvenSquares=" + sum);
    }
}
```

**Biên dịch và chạy bằng JDK 17+**, chương trình chỉ dùng API tương thích Java 8:

```bash
javac StreamPipelineDemo.java
java StreamPipelineDemo
```

**Stdout chính xác:**

```text
beforeTerminal=0
afterTerminal=4
result=[APPLE, BANANA, PEAR]
source=[  apple  ,  ,  banana,  pear ]
sourceNow=changed
resultFirst=APPLE
reused=illegal
fresh=[CHANGED, BANANA, PEAR]
first=cat
sumEvenSquares=20
```

### Giải thích từng dòng

**`beforeTerminal=0`**: trước `collect`, chưa có phần tử nào được đưa qua `map`; pipeline chỉ được dựng bằng các intermediate operations.

**`afterTerminal=4`**: với pipeline tuần tự cụ thể này, `collect` cần các giá trị do `map` tạo cho bốn phần tử source; stage đầu xử lý bốn phần tử, còn dòng chỉ gồm khoảng trắng bị `filter` loại.

**`result=[APPLE, BANANA, PEAR]`**: các thao tác `trim`, loại chuỗi rỗng và `toUpperCase` tạo đầu ra có ba chuỗi.

**`source=[  apple  ,  ,  banana,  pear ]`**: collection nguồn vẫn giữ bốn chuỗi ban đầu cùng whitespace; `map`/`filter` không ghi ngược vào List.

**`sourceNow=changed`**: chương trình sửa phần tử đầu tiên **sau khi `collect` hoàn tất**, không sửa source trong lúc stream đang duyệt.

**`resultFirst=APPLE`**: List kết quả đã materialize giữ giá trị chuỗi in hoa đầu tiên. Thay `source[0]` sau đó không tự làm pipeline chạy lại. Ví dụ dùng `String` immutable nên dễ quan sát sự độc lập của hai container.

**`reused=illegal`**: gọi terminal operation lần thứ hai trên cùng pipeline là không hợp lệ; trong chương trình này Java ném `IllegalStateException`.

**`fresh=[CHANGED, BANANA, PEAR]`**: tạo `source.stream()` mới và chạy lại pipeline sẽ thấy nguồn **ở trạng thái mới**.

**`first=cat`**: `findFirst` trên ordered stream tìm phần tử đầu tiên bắt đầu bằng `c`.

**`sumEvenSquares=20`**: `IntStream` sinh 1..5; lọc số chẵn 2,4; bình phương thành 4,16; terminal `sum()` trả 20, **không cần một List<Integer>** ở mỗi bước.

### Vì sao bộ đếm `visited` chỉ nên dùng để minh họa?

Tài liệu Stream cảnh báo các side effects trong callback nói chung **không được bảo đảm luôn chạy**: implementation có thể tối ưu loại bỏ những stage không ảnh hưởng kết quả. Ví dụ `source.stream().peek(log).count()` có thể **không gọi `peek` cho từng phần tử** nếu size được biết và không cần duyệt. Với parallel stream, thời điểm và thread chạy callback còn khó dự đoán.

Ở chương trình trên, `map` thực sự cần để tạo chuỗi được `collect` và chạy tuần tự, nên output được kiểm chứng. **Không sao chép pattern đếm/tích lũy mutable state trong `map` làm giải pháp production**. Khi cần đếm, dùng `count`; khi cần tổng, dùng `sum`/`reduce`; khi cần collection, dùng `collect`.

## 10. Non-interference và statelessness: điều kiện để pipeline đúng

Java Stream cho phép khai báo functional-style operations. Các lambda/method references truyền vào `map`, `filter`, `reduce` nên là:

- **Non-interfering:** không sửa nguồn stream trong quá trình duyệt, trừ trường hợp nguồn concurrent được thiết kế đặc biệt và contract cho phép.
- **Stateless:** kết quả xử lý phần tử không phụ thuộc vào shared mutable state thay đổi bởi những phần tử khác.

Ví dụ nên dùng:

```java
List<Integer> squares = numbers.stream()
        .filter(n -> n > 0)
        .map(n -> n * n)
        .collect(Collectors.toList());
```

Đoạn minh họa này dùng danh sách `numbers` đã được khai báo. `n -> n > 0`, `n -> n * n` là các phép biến đổi thuần đối với giá trị `Integer` trong ví dụ.

Ví dụ nên tránh:

```java
List<Integer> output = new ArrayList<>();
numbers.parallelStream()
        .filter(n -> n > 0)
        .forEach(output::add); // Shared ArrayList không an toàn.
```

Đây là **mẫu sai cố ý**, không dùng trong ví dụ runnable. `ArrayList` không thread-safe khi nhiều worker thêm phần tử đồng thời. Thay bằng:

```java
List<Integer> output = numbers.parallelStream()
        .filter(n -> n > 0)
        .collect(Collectors.toList());
```

Đó là snippet khác trong method, không ghép với đoạn khai báo `output` phía trên. Collector được Stream API phối hợp để tạo result theo contract; tránh shared mutable accumulation thủ công.

**Lưu ý:** parallel stream không mặc nhiên nhanh hơn. Kích thước dữ liệu, chi phí per-element, splitting/merging, tính thứ tự và contention đều ảnh hưởng hiệu năng. Cần benchmark bằng workload thực và kiểm chứng thread safety; đừng bật `parallelStream()` chỉ để thay vòng for.

## 11. Thứ tự phần tử và thứ tự side effects không phải một

Một `List` có **encounter order** rõ. Nhiều pipeline giữ thứ tự đó, ví dụ `list.stream().map(...).collect(Collectors.toList())` thông thường trả kết quả theo thứ tự encounter order tương ứng.

Nhưng:

- `HashSet` không hứa thứ tự duyệt cố định; một stream từ đó không nên được xem như stream có thứ tự danh sách.
- `forEach` trong parallel stream **không cam kết** callback chạy theo encounter order.
- `forEachOrdered` tuân theo encounter order nếu source có encounter order, nhưng có thể thêm chi phí.
- `findAny` có thể chọn một phần tử bất kỳ; `findFirst` cần trả phần tử đầu tiên theo encounter order nếu một order tồn tại.
- `unordered()` có thể bỏ ràng buộc thứ tự khi phép tính không cần thứ tự, nhưng đừng dùng nếu business logic phải ổn định.

Không dựa vào **thứ tự callback có side effect** để xác định business result của parallel stream. Sử dụng kết quả của reduction/collector và contract encounter order thay vì log/biến shared làm nguồn chân lý.

## 12. Những trường hợp Stream phù hợp và không phù hợp

**Stream phù hợp khi:**

- Cần **lọc–chuyển đổi–gộp** nhiều bước theo một pipeline dễ đọc.
- Cần tìm phần tử đầu tiên phù hợp, bất kỳ phần tử phù hợp hoặc kiểm tra `anyMatch`, `allMatch`.
- Cần sum, count, min/max, grouping, partitioning, mapping.
- Dữ liệu tới từ nguồn có thể truy cập bằng stream và không muốn tự viết nhiều vòng lặp/collection trung gian.
- Muốn tái sử dụng các functional transformations như `Function` và `Predicate` trong API.

**Collection phù hợp khi:**

- Cần **lưu kết quả lâu dài**, truy cập phần tử theo index, quản lý membership, thêm/xóa/sắp xếp in-place.
- Cần duyệt nhiều lần trên cùng dữ liệu đã ổn định.
- Cần kiểm soát state và mutability của một cấu trúc dữ liệu.
- Cần semantics cụ thể của `List`, `Set`, `Map` mà Stream tự nó không cung cấp.

**Vòng lặp thông thường phù hợp khi:**

- Logic có nhiều nhánh điều khiển phức tạp hoặc cập nhật trạng thái cần trình bày rõ.
- Phép xử lý có side effect bắt buộc và yêu cầu thứ tự/transaction.
- Dùng stream khiến code kém dễ hiểu hơn một vòng for đơn giản.

Không coi Stream là "bắt buộc tốt hơn" mọi vòng lặp. Mục tiêu là code **đúng contract, rõ và dễ kiểm thử**, không phải nhiều method chain nhất.

## 13. Những lỗi phổ biến về Stream không lưu trữ dữ liệu

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| "Stream là một List kiểu khác." | Stream không phải kho lưu trữ và không có `get(index)`. |
| "Gọi `filter` sẽ xóa phần tử khỏi List nguồn." | `filter` mô tả phần tử được truyền xuống pipeline, không tự xóa nguồn. |
| "Gọi `map` sẽ sửa object trong List." | `map` không ghi ngược cấu trúc nguồn; callback do bạn viết **có thể** gây mutation nếu lập trình sai. |
| "Có `map` là mọi phần tử đã được tính xong." | Intermediate operations lazy; traversal diễn ra khi terminal yêu cầu. |
| "Cùng một Stream có thể `count` rồi `collect`." | Stream single-use; tạo stream mới từ source cho lần xử lý khác. |
| "Stream không có bộ nhớ trung gian nào." | Một số stage stateful và terminal collector có thể cần buffer/storage. |
| "Stream là snapshot cố định của source." | Không mặc nhiên; nhiều nguồn có late-binding behavior. |
| "Dùng `peek` để log bảo đảm log từng phần tử." | Side effect trong pipeline có thể bị lược bỏ khi tối ưu, nhất là `count()`. |
| "Parallel `forEach` luôn theo thứ tự List." | Không; dùng contract phù hợp và tránh side effects không cần thiết. |
| "Kết quả `collect` là deep copy của mọi object." | Không; với object mutable, tham chiếu phần tử có thể được chia sẻ. |
| "Stream.toList() có từ Java 8." | Nó xuất hiện từ Java 16; dùng `Collectors.toList()` nếu cần source chạy trên Java 8. |
| "Mọi kết quả `collect(toList())` đều mutable `ArrayList`." | Collector không hứa implementation hoặc mutability cụ thể. |
| "Stream vô hạn `collect(toList())` luôn hoàn tất vì lazy." | Không; cần giới hạn/short-circuit hợp lý. |
| "Tạo Stream từ file thì không cần đóng tài nguyên." | Stream backed by I/O có thể cần `close`/try-with-resources. |

## 14. Stream từ I/O cần quản lý tài nguyên

Đa số stream lấy từ collection/array không yêu cầu đóng. Nhưng một số stream có nguồn I/O như `Files.lines(path)` sở hữu **tài nguyên bên ngoài** và nên dùng **try-with-resources**:

```java
try (Stream<String> lines = java.nio.file.Files.lines(path)) {
    long nonEmpty = lines.filter(s -> !s.isEmpty()).count();
    System.out.println(nonEmpty);
}
```

Đây là snippet trong method có biến `path` kiểu `Path`, có xử lý/khai báo `IOException` và import `Stream` phù hợp; **không phải chương trình độc lập**. `try-with-resources` đảm bảo `close` được gọi ngay cả khi xử lý phát sinh exception.

Không hiểu rằng mọi terminal operation tự gọi `close()` cho stream của bạn. **Single-use** và **resource management** là hai khái niệm khác nhau. Một stream được consumed không nhất thiết đồng nghĩa tài nguyên I/O đã được đóng.

## 15. Câu hỏi và đáp án

**1.** `names.stream().filter(...)` đã tạo một List mới chưa?  
**Chưa.** Đó là intermediate Stream; muốn List dùng một terminal collector như `collect(toList())` hoặc API tương đương phù hợp với version.

**2.** `source.stream().map(String::trim).collect(toList())` có sửa chuỗi gốc trong source không?  
**Không.** `trim` trả giá trị theo contract và `collect` xây result; `String` immutable. Đừng dùng kết luận này cho một callback tự mutate object.

**3.** Tại sao cùng `Stream<T>` không nên chạy hai terminal operations?  
Vì Stream là **single-use**; sau terminal, pipeline đã consumed.

**4.** Cần xử lý lại cùng List thì làm gì?  
Tạo một stream **mới** qua `source.stream()` hoặc lưu sẵn kết quả thành collection nếu muốn tái sử dụng.

**5.** Vì sao `findFirst` có thể không đọc hết source?  
Nó là **short-circuiting terminal operation**, có thể dừng khi tìm được phần tử đầu tiên phù hợp với encounter order.

**6.** `collect(toList())` có deep copy phần tử object không?  
**Không.** Nó tạo collection kết quả, nhưng các tham chiếu object có thể được chia sẻ.

**7.** Dùng `peek(System.out::println).count()` có đảm bảo in hết source?  
**Không.** Stream implementation có thể tối ưu `count` mà không chạy stage không cần thiết, nên không dựa vào side effect.

**8.** Một `Stream<Integer>` từ generator vô hạn có thể `collect(toList())` an toàn không?  
Không nếu không có cơ chế giới hạn/kết thúc phù hợp. Thường cần `limit(n)` hoặc terminal short-circuiting.

**9.** `Stream.toList()` và `Collectors.toList()` có hoàn toàn giống nhau không?  
**Không.** `Stream.toList()` xuất hiện từ Java 16 và trả List unmodifiable; `Collectors.toList()` không bảo đảm kiểu/mutability cụ thể.

**10.** Có nên dùng `parallelStream().forEach(output::add)` nếu `output` là `ArrayList` chung?  
**Không.** Việc thêm phần tử đồng thời vào ArrayList không thread-safe; dùng collector phù hợp.

**11.** Stream from `Files.lines(path)` cần xử lý gì khác collection stream?  
Quản lý tài nguyên I/O bằng `try-with-resources` hoặc `close`.

**12.** Vì sao nguồn là List nhưng Stream có thể không cần danh sách trung gian ở mỗi stage?  
Bởi Stream tổ chức pipeline để thực hiện các stage khi terminal xử lý; với các stateless operations có thể được **fused**.

## 16. Kết luận và tài liệu chính thức

**Stream là mô hình xử lý dữ liệu, không phải nơi lưu dữ liệu.** Nó nhận phần tử từ một source, xây pipeline lazy gồm các phép biến đổi/lọc và khi terminal operation chạy sẽ thực thi tính toán cần thiết. Stream có thể trả `List`, `Map`, số, boolean, `Optional` hoặc thực hiện action; bản thân stream không thay thế cấu trúc dữ liệu lưu kết quả.

Nhớ năm quy tắc: **no storage; intermediate lazy; single-use; non-interference/statelessness; terminal produces result/side effect**. Dùng `collect` khi cần materialize, tạo stream mới nếu muốn xử lý nguồn lần nữa, tránh mutating source trong quá trình duyệt, và đừng dựa vào side effect của `map`/`peek` như điều kiện nghiệp vụ. Những nguyên tắc này tiếp tục đúng trong Java hiện đại.

**Nguồn chính thức:**

- [Java SE — `java.util.stream` package summary](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): so sánh stream/collection, laziness, single-use, non-interference, ordering và side effects.
- [Java SE — `Stream` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): source/intermediate/terminal, `count`, `findFirst`, `collect`, `toList`, `peek`.
- [Java SE — `Collectors` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): kết quả materialize bằng các collector.
- [Java SE — `BaseStream` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html): single-use, close, iterator/spliterator và sequential/parallel execution.
