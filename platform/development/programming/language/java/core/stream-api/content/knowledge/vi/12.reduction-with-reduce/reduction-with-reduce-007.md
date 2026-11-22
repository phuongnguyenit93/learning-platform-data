# Vì sao không dùng bộ chứa mutable làm identity của `reduce`?

Trong **Java Stream API**, `reduce` dùng để rút gọn nhiều phần tử thành **một giá trị** theo phép kết hợp. Ví dụ, tính tổng, tìm giá trị lớn nhất hoặc ghép các kết quả bất biến. Khi muốn gom phần tử thành `ArrayList`, `HashMap` hay `StringBuilder`, nhiều người cũng thử truyền một container rỗng vào tham số `identity` rồi sửa nó ngay trong accumulator.

Đó là một bẫy quan trọng trong chương **Phép rút gọn với reduce**: `identity` là **một giá trị khởi đầu tham gia hợp đồng toán học của phép rút gọn**, không phải một factory được gọi để tạo container mới. Nếu accumulator thay đổi đối tượng ấy, pipeline có thể tình cờ cho kết quả đúng khi chạy tuần tự nhưng tạo phần tử trùng, mất dữ liệu hoặc gặp tranh chấp khi chuyển sang song song.

Giải pháp thông thường là **`reduce` cho phép kết hợp giá trị bất biến; `collect` cho phép tích lũy vào container mutable**. Cần hiểu lý do này từ hợp đồng API, thay vì chỉ thay tên một phương thức.

## 1. Phân biệt giá trị rút gọn và bộ chứa tích lũy

Một pipeline Stream có thể gồm nguồn, các phép toán trung gian lazy (`filter`, `map`, ...) và terminal operation (`reduce`, `collect`, ...). Terminal operation kích hoạt xử lý; sau đó cùng đối tượng `Stream` không thể được sử dụng lại.

| Tiêu chí | `reduce` | `collect` |
| --- | --- | --- |
| Mục đích chính | Kết hợp các phần tử hoặc kết quả tạm thành một **giá trị**. | Tích lũy phần tử vào một **container có thể thay đổi**. |
| Khởi tạo | Nhận `identity` là **giá trị** thuộc kiểu kết quả. | Nhận `supplier` **tạo container** mới khi cần. |
| Phép tích lũy | Trả kết quả tích lũy mới về mặt ngữ nghĩa. | Thường sửa container của lượt tích lũy và trả `void`. |
| Kết hợp các nhánh | `BinaryOperator` trả một giá trị kết hợp. | `Stream.collect` ba tham số dùng `BiConsumer`; `Collector.of` dùng `BinaryOperator` trả container gộp. |
| Ví dụ điển hình | Tổng, tích, phép chọn min/max, `BigDecimal::add`. | `List`, `Set`, `Map`, `groupingBy`, collector tùy chỉnh. |

**Mutable** nghĩa là trạng thái bên trong đối tượng có thể thay đổi sau khi tạo. `ArrayList.add`, `HashMap.put` và `StringBuilder.append` là những thao tác thay đổi đối tượng. Trái lại, `Integer`, `String` và `BigDecimal` là các kiểu bất biến: phép tính thường tạo giá trị kết quả mới.

## 2. Ba overload của `reduce` và ý nghĩa của `identity`

Các chữ ký khái quát trên `Stream<T>`:

```java
Optional<T> reduce(BinaryOperator<T> accumulator);

T reduce(T identity, BinaryOperator<T> accumulator);

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

- **Không có identity:** `reduce(BinaryOperator<T>)` trả `Optional<T>`, vì stream rỗng không có phần tử để trả về.
- **Có identity và cùng kiểu:** `reduce(T, BinaryOperator<T>)` trả `T`; identity là kết quả khi nguồn rỗng và là phần tử đơn vị của phép kết hợp.
- **Có identity và kết quả khác kiểu:** `reduce(U, BiFunction<U,T,U>, BinaryOperator<U>)` cho phép phần tử kiểu `T` được tích lũy thành giá trị kiểu `U`. Combiner gộp **hai** giá trị `U`.

Ví dụ đúng với giá trị bất biến:

```java
import java.util.stream.Stream;

int sum = Stream.of(2, 4, 6).reduce(0, Integer::sum);
int emptySum = Stream.<Integer>empty().reduce(0, Integer::sum);

System.out.println(sum);      // 12
System.out.println(emptySum); // 0
```

`0` là phần tử đơn vị của phép cộng: `0 + x = x + 0 = x`. `Integer::sum` không thay đổi bất kỳ `Integer` nào; nó trả một giá trị `int` mới. Dữ liệu có thể được chia thành các nhóm để tính tổng từng phần rồi kết hợp mà không phụ thuộc ranh giới chia nhóm, miễn là tổng không vượt quá phạm vi kiểu số.

### `identity` khác `Supplier` như thế nào?

```text
reduce(identity, accumulator, combiner)
       |
       +-- identity là một GIÁ TRỊ được truyền vào lời gọi reduce

collect(supplier, accumulator, combiner)
        |
        +-- supplier.get() có thể được gọi nhiều lần
            để tạo những CONTAINER RIÊNG cho các phần tích lũy
```

Khi `identity` là số 0 hoặc chuỗi rỗng, chia sẻ giá trị ấy không gây vấn đề vì ta không sửa nó. Nhưng khi `identity` là **một tham chiếu đến danh sách mutable**, các nhánh song song có thể nhận **cùng tham chiếu đó** làm điểm khởi đầu. Không có cơ chế tự động sao chép danh sách mỗi khi một nhánh bắt đầu.

## 3. Ví dụ sai: dùng `ArrayList` làm identity rồi gọi `add`

Đoạn mã sau **biên dịch được nhưng vi phạm hợp đồng reduction**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

// VÍ DỤ SAI: không dùng trong ứng dụng.
List<String> result = Stream.of("A", "B", "C")
    .reduce(
        new ArrayList<String>(),
        (acc, item) -> {
            acc.add(item);  // Sửa chính identity hoặc kết quả tạm
            return acc;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Khi chạy tuần tự, đoạn mã có thể in ra `[A, B, C]`. Kết quả ấy dễ tạo ấn tượng rằng cách làm là đúng. Nhưng cả accumulator lẫn combiner đều **thay đổi đối tượng đầu vào** rồi trả lại chính nó.

Khi chạy song song, một cách thực thi có thể chia nguồn thành các phần `[A]`, `[B]`, `[C]` và bắt đầu tích lũy từ cùng đối tượng danh sách được truyền làm `identity`. Các tình huống có thể xảy ra:

1. Hai nhánh cùng gọi `add` trên một `ArrayList` không an toàn luồng, gây tranh chấp và kết quả không tin cậy.
2. Khi combiner nhận hai kết quả đều trỏ đến **chính danh sách ấy**, thao tác `left.addAll(right)` có thể sao chép danh sách vào chính nó, tạo bản ghi trùng.
3. Trong một số lần chạy, kết quả có vẻ đúng; trong lần khác, thứ tự, số lượng hoặc nội dung có thể sai. Không có bảo đảm được phép dựa vào.

Không cần chạy thử để coi đây là lỗi: mã **đã sai hợp đồng** dù một ví dụ nhỏ tình cờ cho đầu ra như mong muốn.

### Cùng lỗi với `StringBuilder`

```java
import java.util.stream.Stream;

// VÍ DỤ SAI: StringBuilder::append sửa đối tượng bên trái.
StringBuilder text = Stream.of("a", "b", "c")
    .parallel()
    .reduce(
        new StringBuilder(),
        StringBuilder::append,
        StringBuilder::append
    );
```

`StringBuilder` rất phù hợp làm bộ đệm mutable **trong collector**, nhưng không phù hợp với kiểu `reduce` sửa trực tiếp identity như trên. Việc đồng bộ hóa thủ công hoặc đổi sang `StringBuffer` không tự sửa hợp đồng identity và combiner: hai biến kết quả tạm vẫn có thể tham chiếu cùng một đối tượng và bị gộp lặp.

## 4. Tại sao sai: các luật của phép rút gọn

Để `reduce` đúng với cách Stream được phép phân chia và kết hợp, các hàm cần thỏa những điều kiện về **phần tử đơn vị, tính kết hợp và tương thích accumulator/combiner**.

Gọi:

- `e`: identity kiểu `U`;
- `A(u, t)`: accumulator đưa phần tử nguồn `t` kiểu `T` vào kết quả tạm `u` kiểu `U`;
- `C(u1, u2)`: combiner gộp hai kết quả tạm kiểu `U`.

Về mặt giá trị, cần bảo đảm:

| Điều kiện | Ý nghĩa |
| --- | --- |
| `C(e, u) = u` | Identity là phần tử đơn vị ở bên trái. |
| `C(u, e) = u` | Identity là phần tử đơn vị ở bên phải. |
| `C(C(a, b), c) = C(a, C(b, c))` | Combiner có tính kết hợp (*associative*). |
| `C(u, A(e, t)) = A(u, t)` | Accumulator tương thích với combiner. |

Các đẳng thức ở đây là **tương đương theo giá trị kết quả**, không nhất thiết hai đối tượng phải cùng địa chỉ bộ nhớ. Với `reduce`, các hàm hành vi còn phải **không can thiệp vào nguồn** (*non-interfering*) và **không dựa vào trạng thái dùng chung có thể thay đổi** (*stateless*) theo yêu cầu của Stream API.

Ví dụ tính tổng độ dài chuỗi thành `int`:

```java
import java.util.stream.Stream;

int totalLength = Stream.of("Java", "Stream", "API")
    .parallel()
    .reduce(
        0,
        (length, word) -> length + word.length(),
        Integer::sum
    );

System.out.println(totalLength); // 13
```

Ở đây, `T = String`, `U = Integer`, `e = 0`. Accumulator lấy độ dài một chuỗi và cộng vào tổng; combiner cộng hai tổng. Với các giá trị trong ví dụ, mọi cách chia và gộp đều cho 13.

### Bộ chứa mutable phá vỡ hợp đồng ra sao?

Nếu `e` là một `ArrayList` và `A(e, t)` gọi `e.add(t)`, **bản thân `e` không còn rỗng sau lời gọi**. Identity đã đổi trạng thái, nên không còn là phần tử đơn vị ổn định của việc gộp các kết quả tạm. Việc combiner có thể được gọi trên hai tham chiếu trỏ cùng một danh sách càng làm phép gộp thiếu tính độc lập.

Vấn đề chính không chỉ là “`ArrayList` không thread-safe”. Ngay cả trong pipeline tuần tự, việc sửa identity do bên gọi cung cấp khiến kết quả phụ thuộc vào lịch sử thay đổi của chính đối tượng ấy; nếu chạy lại với cùng một identity đã bị sửa, kết quả tích lũy còn có thể mang dữ liệu của lần trước.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> seed = new ArrayList<>();

// VÍ DỤ SAI: sau lần giảm thứ nhất, seed đã bị sửa.
List<String> one = Stream.of("A").reduce(
    seed,
    (acc, item) -> { acc.add(item); return acc; },
    (left, right) -> { left.addAll(right); return left; }
);

System.out.println(seed); // [A] trong thực thi tuần tự này
// Dùng lại seed trong lần reduce khác sẽ mang theo dữ liệu cũ.
```

Đừng sửa lỗi bằng `synchronizedList`, `CopyOnWriteArrayList` hay `AtomicReference` rồi vẫn giữ cùng cấu trúc `reduce`. Đồng bộ có thể giảm tranh chấp trên trạng thái dùng chung, nhưng **không thay thế quy tắc identity và kết hợp** mà reduction yêu cầu.

## 5. Cách đúng: `collect` với supplier tạo container độc lập

Nếu mục tiêu là thu các phần tử vào danh sách mutable, hãy dùng `collect`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> result = Stream.of("A", "B", "C")
    .parallel()
    .collect(
        ArrayList::new,             // Supplier: tạo danh sách mới
        List::add,                  // BiConsumer: thêm phần tử
        List::addAll                // BiConsumer: gộp danh sách
    );

System.out.println(result); // [A, B, C]
```

Trong overload `Stream.collect(supplier, accumulator, combiner)`:

1. **Supplier** có kiểu `Supplier<R>`, được gọi để tạo bộ chứa mới. Khi chia pipeline thành các phần, các bộ chứa có thể được khởi tạo độc lập.
2. **Accumulator** có kiểu `BiConsumer<R, T>`, cập nhật bộ chứa của phần tích lũy với một phần tử nguồn.
3. **Combiner** có kiểu `BiConsumer<R, R>`, chuyển dữ liệu từ bộ chứa này vào bộ chứa khác khi gộp kết quả. Không cần trả về giá trị.

`List::add` và `List::addAll` có giá trị trả về kiểu `boolean`, nhưng ở ngữ cảnh `BiConsumer` giá trị trả về đó được bỏ qua. Kết quả của collector này vẫn giữ encounter order của nguồn có thứ tự theo hợp đồng tích lũy phù hợp; đừng áp dụng suy luận đó cho collector tùy chỉnh khai báo `UNORDERED` hoặc cho nguồn không có thứ tự.

### Cách ngắn gọn hơn với `Collectors`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> items = Stream.of("A", "B", "C")
    .parallel()
    .collect(Collectors.toList());

ArrayList<String> editable = Stream.of("A", "B", "C")
    .collect(Collectors.toCollection(ArrayList::new));
```

`Collectors.toList()` **không bảo đảm** kiểu cài đặt hoặc khả năng sửa đổi của danh sách kết quả. Khi cần chắc chắn một `ArrayList` có thể thay đổi, dùng `toCollection(ArrayList::new)`. Từ Java 16, `Stream.toList()` cung cấp danh sách không thể sửa đổi; không chọn nó nếu phần sau bắt buộc phải `add` hoặc `remove`.

Điểm khác biệt cốt lõi: trong `collect`, **mutation là một phần được thiết kế trong hợp đồng**, với supplier và combiner phối hợp để việc tích lũy đúng ngay cả khi stream được chia nhỏ.

## 6. Trường hợp `Collector.of`: combiner trả container

Khi xây **collector tùy chỉnh**, chữ ký `Collector.of` khác với overload `Stream.collect` ở trên. Accumulator vẫn là `BiConsumer`, nhưng combiner là `BinaryOperator<A>` và phải **trả lại** bộ chứa đã kết hợp:

```java
import java.util.ArrayList;
import java.util.stream.Collector;
import java.util.stream.Stream;

Collector<String, ArrayList<String>, ArrayList<String>> toArrayList =
    Collector.of(
        ArrayList::new,             // Supplier<ArrayList<String>>
        ArrayList::add,             // BiConsumer<ArrayList<String>, String>
        (left, right) -> {
            left.addAll(right);
            return left;            // BinaryOperator<ArrayList<String>>
        }
    );

ArrayList<String> values = Stream.of("A", "B", "C")
    .parallel()
    .collect(toArrayList);

System.out.println(values); // [A, B, C]
```

Phép `left.addAll(right)` ở đây **được phép** vì collector dùng **những container tích lũy độc lập** mà supplier tạo. Combiner gộp các container bộ phận, còn identity của `reduce` không tham gia vào quy trình này.

Một collector do người dùng viết cũng phải thỏa hợp đồng đồng nhất và kết hợp của **collector**. Không được để `supplier` trả **cùng một danh sách dùng chung** cho mọi lần gọi:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> shared = new ArrayList<>();

// VÍ DỤ SAI: mỗi lần gọi supplier đều trả cùng một container.
List<String> broken = Stream.of("A", "B", "C").parallel()
    .collect(
        () -> shared,
        List::add,
        List::addAll
    );
```

Đổi tên `reduce` thành `collect` **chưa đủ** nếu vẫn dùng một bộ chứa chia sẻ. Supplier trong collector phải đáp ứng yêu cầu tạo kết quả tích lũy thích hợp cho các lời gọi độc lập.

## 7. Khi nào `reduce` vẫn là lựa chọn đúng?

`reduce` rất phù hợp khi giá trị kết quả được **kết hợp mà không sửa đối tượng đầu vào**.

### Tính tổng với `BigDecimal`

```java
import java.math.BigDecimal;
import java.util.stream.Stream;

BigDecimal amount = Stream.of(
        new BigDecimal("12.30"),
        new BigDecimal("4.70"),
        new BigDecimal("1.25")
    )
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(amount); // 18.25
```

`BigDecimal.add` trả về một `BigDecimal` kết quả và không sửa hai toán hạng. Với `BigDecimal.ZERO` là identity, quy tắc tích lũy và combiner dùng cùng phép cộng có ý nghĩa rõ ràng. Với bài toán có `MathContext` và quy tắc làm tròn đặc biệt, tính kết hợp theo giá trị số sau mỗi lần làm tròn vẫn cần được cân nhắc khi chạy song song.

### Ghép chuỗi bất biến

```java
import java.util.stream.Stream;

String joined = Stream.of("Java", "-", "Stream")
    .reduce("", String::concat);

System.out.println(joined); // Java-Stream
```

`String` bất biến và chuỗi rỗng là identity của phép nối. Tuy nhiên, `reduce` bằng `String::concat` có thể tạo nhiều chuỗi trung gian, nhất là khi dữ liệu lớn. Để nối nhiều chuỗi hiệu quả, dùng `Collectors.joining`, vốn sử dụng bộ tích lũy mutable một cách hợp lệ:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String joined = Stream.of("Java", "Stream", "API")
    .collect(Collectors.joining(", "));

System.out.println(joined); // Java, Stream, API
```

### Nếu kiểu kết quả là mutable nhưng accumulator không sửa nó?

Về lý thuyết, một đối tượng thuộc **kiểu mutable** vẫn có thể được dùng trong reduction **nếu mọi bước đối xử với nó như một giá trị bất biến**: không thay đổi identity hoặc các đối tượng tạm, tạo một đối tượng mới ở mỗi phép kết hợp và giữ đúng những luật ở mục 4. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", "B", "C").reduce(
    new ArrayList<String>(),
    (existing, item) -> {
        List<String> copy = new ArrayList<>(existing);
        copy.add(item);
        return copy;
    },
    (left, right) -> {
        List<String> copy = new ArrayList<>(left);
        copy.addAll(right);
        return copy;
    }
);

System.out.println(values); // [A, B, C]
```

Đoạn này **không sửa** danh sách đầu vào trong accumulator và combiner, nên tránh bẫy chia sẻ identity. Tuy nhiên, mỗi lần thêm phần tử lại sao chép nội dung đã có: chi phí cấp phát và sao chép có thể tăng mạnh theo độ dài dãy. Vì vậy, **`collect` vẫn là lựa chọn tự nhiên và hiệu quả hơn khi mục tiêu là xây danh sách mutable**.

## 8. Song song làm lộ lỗi, nhưng lỗi có từ trước

Với pipeline song song, Stream API được phép chia nguồn và gộp kết quả theo cây:

```text
Nguồn dữ liệu:        A   B   C   D
                       \ /     \ /
Nhánh độc lập:         R1       R2
                        \      /
Kết quả cuối:          combine(R1, R2)
```

Không có bảo đảm sẽ có đúng hai nhánh, hay rằng các nhánh chạy theo thứ tự cố định. Vì vậy, reduction phải đúng với cách phân chia và cách gộp hợp lệ. Khi accumulator sửa identity dùng chung, hai `R1` và `R2` có thể thực chất là **cùng một đối tượng**, làm mất tính độc lập cần thiết.

Ngược lại, `collect` tạo container qua supplier, nên mỗi phần tích lũy có thể giữ trạng thái **riêng**, rồi kết hợp có kiểm soát. Đó là lý do API tách `reduce` và `collect`.

Một số giới hạn khác cần nhớ:

- `parallel()` không tự bảo đảm nhanh hơn. Hiệu quả phụ thuộc Spliterator của nguồn, lượng dữ liệu, chi phí kết hợp và tải của hệ thống.
- Các phép toán trung gian `map`, `filter` đều lazy; không nên dùng hiệu ứng phụ của chúng để ghi nhận mọi phần tử, vì có thể xuất hiện tối ưu hóa hoặc ngắn mạch.
- Dấu phẩy động `double` không có tính kết hợp tuyệt đối do làm tròn; phép cộng song song có thể chênh lệch một vài bit cuối so với tuần tự.
- Một terminal operation tiêu thụ stream. Muốn `reduce` và `collect` cùng một nguồn collection để so sánh, hãy tạo **hai stream mới**.
- Với nguồn I/O như `Files.lines`, dùng `try-with-resources`; terminal operation không tự đóng tài nguyên.

## 9. Bảng chọn cách làm theo mục đích

| Cần làm | Phương án đề xuất | Lý do |
| --- | --- | --- |
| Cộng các giá trị `int`, `long` | `IntStream.sum()`, `LongStream.sum()` hoặc `reduce` phù hợp | Tạo một kết quả số, không cần container mutable. |
| Cộng `BigDecimal` | `reduce(BigDecimal.ZERO, BigDecimal::add)` | `BigDecimal` là giá trị bất biến. |
| Tìm phần tử nhỏ nhất/lớn nhất | `min`/`max` hoặc `reduce(BinaryOperator.minBy/maxBy(...))` | Phép chọn giữa các giá trị. |
| Thu phần tử thành `List` | `collect(Collectors.toList())` | Collector quản lý tích lũy và kết hợp. |
| Cần `ArrayList` có thể sửa | `collect(Collectors.toCollection(ArrayList::new))` | Chỉ rõ factory và loại container. |
| Thu phần tử thành `Set` | `collect(Collectors.toSet())` | Thực hiện loại trùng theo ngữ nghĩa của tập hợp. |
| Gom phần tử theo khóa | `collect(Collectors.groupingBy(...))` | Tích lũy nhiều bộ chứa theo nhóm. |
| Nối nhiều chuỗi | `collect(Collectors.joining(...))` | Tránh nối chuỗi bất biến lặp đi lặp lại. |
| Tạo collector tùy chỉnh | `Collector.of(supplier, accumulator, combiner, ...)` | Kiểm soát container mới và cách gộp kết quả. |

## 10. Các dấu hiệu cho thấy một `reduce` đang sai

Khi đọc một pipeline có `reduce`, cần xem kỹ những đoạn như:

1. **Identity là `new ArrayList<>()`, `new HashMap<>()`, `new StringBuilder()`** và accumulator gọi `add`, `put` hoặc `append` trên nó.
2. Accumulator **trả chính đối tượng vừa sửa**, thay vì biểu diễn một phép kết hợp theo giá trị.
3. Combiner gọi `left.addAll(right)`/`left.putAll(right)` trong khi `left` và `right` có thể cùng tham chiếu identity.
4. Một đối tượng mutable đặt ngoài pipeline được lambda ghi vào, ví dụ một danh sách hoặc bộ đếm dùng chung.
5. Kết quả tuần tự đúng nhưng sau khi thêm `parallel()` xuất hiện phần tử trùng, số lượng biến động hoặc ngoại lệ.
6. Có đề xuất dùng `synchronized` chỉ để giữ nguyên cấu trúc reduction đang sai.

Những dấu hiệu trên không có nghĩa mọi trường hợp dùng kiểu mutable trong `reduce` đều bị cấm. Cần xét **hành vi thay đổi trạng thái** và các luật của reduction; nếu cần đổ dữ liệu vào bộ chứa, thiết kế của `collect` phù hợp hơn.

## 11. Bài tập tự kiểm tra

**Bài 1 — Phát hiện lỗi.** Cho:

```java
List<Integer> result = numbers.parallelStream().reduce(
    new ArrayList<Integer>(),
    (list, n) -> { list.add(n); return list; },
    (left, right) -> { left.addAll(right); return left; }
);
```

Hãy chỉ ra accumulator và combiner thay đổi trạng thái ở đâu, vì sao identity có thể bị dùng chung, và vì sao chỉ đồng bộ `list.add` chưa đủ. Viết lại bằng `collect(ArrayList::new, List::add, List::addAll)`.

**Bài 2 — Chọn đúng overload.** Tính tổng độ dài của `Stream.of("a", "bb", "ccc")` bằng `reduce(0, (sum, s) -> sum + s.length(), Integer::sum)`. Giải thích vì sao accumulator là `BiFunction<Integer, String, Integer>` và combiner là `BinaryOperator<Integer>`. Dự đoán kết quả bằng **6**.

**Bài 3 — Lựa chọn collector.** Thu các tên sản phẩm từ stream vào danh sách được bảo đảm có thể thay đổi. Vì sao `Collectors.toCollection(ArrayList::new)` phù hợp hơn việc sửa một `ArrayList` trong `reduce`? Phân biệt nó với `Stream.toList()` (Java 16+).

**Bài 4 — Chi phí.** So sánh reduction trả về bản sao mới của `List` sau mỗi phần tử với `collect` tích lũy vào danh sách riêng rồi gộp. Phương án nào tạo nhiều đối tượng hơn khi số phần tử rất lớn? Khi nào một giá trị kết quả bất biến như `BigDecimal` vẫn nên được dùng với `reduce`?

**Ghi nhớ:** `reduce` nhận **một giá trị identity** và đòi hỏi các phép kết hợp tuân thủ luật toán học, kể cả khi Stream được chia và gộp song song. Sửa trực tiếp một `ArrayList`, `HashMap` hoặc `StringBuilder` dùng làm identity phá vỡ tính độc lập và có thể gây kết quả sai. Khi muốn tạo container mutable, hãy dùng `collect` với supplier tạo container riêng và combiner hợp lệ.
