# Khi nào dùng nguồn Stream tùy chỉnh thay cho nguồn JDK có sẵn?

## 1. Vấn đề: có cần tự xây nguồn Stream hay không?

Trong Java, một Stream pipeline gồm **nguồn phần tử**, các **intermediate operations** như `filter` / `map` và một **terminal operation** như `toList` / `collect`. Nhiều bài toán chỉ cần tạo nguồn với API sẵn có:

```java
List<String> names = List.of("Lan", "An");
Stream<String> a = names.stream();
Stream<String> b = Stream.of("Java", "Stream");
IntStream c = IntStream.range(1, 5);
```

Đây là các khai báo trong một phương thức với các import tương ứng; mỗi nguồn đã biết cách tạo phần tử nên **không cần viết Spliterator riêng**.

Nhưng có những nguồn đặc thù: API phân trang, con trỏ đọc bản ghi, bộ sinh tuần tự theo giao thức riêng, dữ liệu chỉ đọc được từng đợt hoặc tài nguyên cần đóng. Khi ấy câu hỏi “có nên dùng nguồn tùy chỉnh?” phải bắt đầu từ yêu cầu thực tế, **không phải từ việc muốn viết thêm mã Java nâng cao**.

**Quy tắc ưu tiên:** chọn nguồn chuẩn JDK đơn giản nhất đáp ứng đúng hợp đồng. Chỉ tạo adapter hoặc Spliterator tùy chỉnh khi một khác biệt cụ thể về cách lấy phần tử, lazy fetching, sở hữu tài nguyên, thứ tự, kích thước hoặc cơ chế chia việc làm cho API chuẩn không đủ trực tiếp.

Bài này tập trung vào **quyết định lựa chọn nguồn** và những trách nhiệm phát sinh khi tự xây nguồn cho Java Stream 17+.

## 2. Stream source là gì?

Nguồn là nơi Stream nhận các phần tử. Nó không nhất thiết là một `Collection` đã có sẵn trong bộ nhớ.

Ví dụ:

```text
Collection / Array / File / Iterator / API phân trang
                    |
                    v
                Nguồn Stream
                    |
                    v
            filter → map → limit
                    |
                    v
              toList / reduce
```

Stream mô tả quá trình xử lý phần tử; bản thân Stream **không phải cấu trúc lưu trữ dữ liệu có thể dùng lại tùy ý**. Một đối tượng Stream thường chỉ dùng cho một pipeline rồi terminal operation, không dùng lại để xử lý lần hai.

Các nguồn JDK tiêu biểu:

| Nguồn dữ liệu | Cách tạo thường dùng | Khi thích hợp |
| --- | --- | --- |
| `Collection<T>` | `collection.stream()` / `parallelStream()` | Đã có collection |
| Mảng tham chiếu | `Arrays.stream(array)` | Duyệt từng phần tử mảng |
| Mảng nguyên thủy | `Arrays.stream(intArray)` → `IntStream` | Tính toán số nguyên không boxing |
| Vài giá trị | `Stream.of(a, b, c)` | Tạo nguồn nhỏ, rõ ràng |
| Một giá trị có thể null | `Stream.ofNullable(value)` | Null tương ứng 0 phần tử (Java 9+) |
| Dãy số nguyên | `IntStream.range(start, end)` | Dãy có quy luật, biên kết thúc rõ |
| Dãy do hàm sinh | `Stream.iterate(...)`, `Stream.generate(...)` | Quy tắc sinh đơn giản |
| Các dòng văn bản của file | `Files.lines(path)` | Đọc file theo dòng; cần đóng Stream |
| Dòng từ `BufferedReader` | `reader.lines()` | Đã có reader cần quản lý vòng đời |
| Tách chuỗi theo pattern | `Pattern.splitAsStream(text)` | Các token theo regex |
| Iterator đặc thù | `Spliterators.spliteratorUnknownSize(...)` + `StreamSupport.stream(...)` | Adapter từ iterator chưa có Stream |
| Nguồn tùy chỉnh hoàn toàn | `Spliterator<T>` + `StreamSupport.stream(...)` | Cần tự điều khiển cách nhận phần tử |

Đối với dữ liệu vốn đang nằm trong List, xây lại nguồn Spliterator thường không tạo thêm giá trị. Với nguồn file đã có `Files.lines`, viết lại logic mở/đọc file thường chỉ làm tăng rủi ro.

## 3. Sơ đồ quyết định trước khi tạo nguồn tùy chỉnh

```text
Đã có Collection / Array?
    ├─ Có → collection.stream() / Arrays.stream()
    └─ Không
         |
         v
Có API JDK phù hợp trực tiếp?
(Stream.of, ofNullable, range, iterate, generate, Files.lines...)
    ├─ Có → dùng API sẵn có, quản lý tài nguyên theo hợp đồng
    └─ Không
         |
         v
Nguồn đã cung cấp Iterator hoặc Iterable?
    ├─ Có → cân nhắc adapter qua spliteratorUnknownSize
    └─ Không
         |
         v
Có giao thức lấy phần tử đặc thù?
(con trỏ, paging, bộ giải mã trạng thái, dữ liệu nhận từng batch)
    ├─ Không → xem lại cách mô hình hóa nguồn
    └─ Có → viết Spliterator/adapter riêng khi lợi ích đủ lớn
                 |
                 v
     Xác định ORDERED, size, null, close, exception,
     cancellation, split/parallel và cách kiểm thử
```

**Không phải lúc nào “tùy chỉnh” cũng đồng nghĩa tự triển khai `Spliterator`.** Thường chỉ cần một hàm adapter trả về Stream từ iterator hoặc một cách dùng `Stream.generate` có giới hạn hợp lý. Spliterator tùy chỉnh là một lựa chọn có chi phí thiết kế và bảo trì cao hơn.

## 4. Khi nguồn chuẩn đã đủ: đừng tự viết lại

### 4.1. Dữ liệu đã ở trong Collection hoặc mảng

Ví dụ:

```java
List<Integer> numbers = List.of(4, 1, 3, 2);

List<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();
```

Đây là đoạn mã trong phương thức có import `List`. Kết quả là `[2, 4]`. Không có yêu cầu tạo nguồn khác: List đã cung cấp kích thước, thứ tự gặp phần tử và spliterator phù hợp.

Với mảng nguyên thủy:

```java
int[] scores = {8, 4, 9};
int total = Arrays.stream(scores).sum();
```

Đoạn này cần import `java.util.Arrays`; `total == 21`. Dùng `IntStream` tiện hơn xây `Stream<Integer>` thủ công vì tránh boxing từng phần tử.

### 4.2. Dữ liệu có quy luật sinh đơn giản

`IntStream.range(0, n)` đã giải quyết dãy index. `Stream.iterate(seed, next)` hoặc overload ba đối số `Stream.iterate(seed, hasNext, next)` dùng cho chuỗi trạng thái có quy luật. `Stream.generate(supplier)` dùng khi từng phần tử do Supplier tạo ra và không cần thông tin từ phần tử trước.

Ví dụ:

```java
List<Integer> odds = Stream.iterate(
        1, n -> n <= 9, n -> n + 2)
        .toList();
```

Trong phương thức có import `Stream` và `List`, kết quả là `[1, 3, 5, 7, 9]`. Overload ba tham số có từ Java 9; nó dừng theo predicate trước khi phát phần tử không thỏa.

Nếu nhu cầu chỉ là sinh một dãy như thế, viết Spliterator riêng thường là quá mức. Phải giới hạn hợp lý nguồn vô hạn từ `generate` hoặc overload hai đối số của `iterate` trước khi gọi các terminal operation cần thu toàn bộ phần tử.

### 4.3. Nguồn file đã có trong JDK

Dùng `Files.lines(path, charset)` cho dòng văn bản. Đây là API tạo Stream từ tài nguyên cần đóng, đã có cách xử lý đọc, charset và phối hợp terminal operation. Viết nguồn Stream mới chỉ để đọc từng dòng file thông thường sẽ tăng số trạng thái phải tự kiểm soát mà chưa chắc giúp ích.

## 5. Ví dụ Java 17+: ba nguồn chuẩn đáp ứng phần lớn nhu cầu

Lưu file `JdkSourcesDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class JdkSourcesDemo {
    public static void main(String[] args) {
        List<Integer> fromList = List.of(5, 1, 4, 2)
                .stream()
                .filter(n -> n % 2 == 0)
                .sorted()
                .toList();

        int sum = Arrays.stream(new int[] {2, 3, 4}).sum();

        List<Integer> fromRange = IntStream.range(1, 5)
                .boxed()
                .toList();

        List<Integer> fromIterate = Stream.iterate(
                1, n -> n <= 7, n -> n + 2)
                .toList();

        List<String> fromGenerate = Stream.generate(() -> "x")
                .limit(3)
                .toList();

        System.out.println("list=" + fromList);
        System.out.println("sum=" + sum);
        System.out.println("range=" + fromRange);
        System.out.println("iterate=" + fromIterate);
        System.out.println("generate=" + fromGenerate);
    }
}
```

Chạy:

```bash
javac JdkSourcesDemo.java
java JdkSourcesDemo
```

Output:

```text
list=[2, 4]
sum=9
range=[1, 2, 3, 4]
iterate=[1, 3, 5, 7]
generate=[x, x, x]
```

Tại đây, mọi yêu cầu đều được giải quyết bằng nguồn chuẩn. `Stream.generate` có nguồn không giới hạn theo mặc định, nhưng `limit(3)` giúp pipeline thu đúng ba phần tử. Cách viết phù hợp khi nguồn Supplier chỉ cần trả một giá trị theo nhu cầu mà không phải giữ cursor theo trang.

**Đừng biến một nhu cầu biến đổi phần tử thành nhu cầu tạo nguồn tùy chỉnh.** Các yêu cầu “lọc”, “đổi sang DTO”, “ghép chuỗi”, “nhóm theo khóa” thông thường thuộc về `filter`, `map`, `flatMap` và collector, không phải lý do tự viết Spliterator.

## 6. Các lý do thực sự để cân nhắc nguồn tùy chỉnh

Một nguồn tùy chỉnh có giá trị khi cần một hoặc nhiều khả năng mà adapter chuẩn khó diễn đạt trực tiếp:

1. **Lấy dữ liệu lười theo trang hoặc cursor.** Thay vì tải mọi trang từ API về List trước rồi mới dùng Stream, nguồn có thể lấy trang mới khi phần tử cũ đã tiêu thụ hết.
2. **Chuyển giao thức lấy bản ghi độc quyền thành Stream.** Driver, SDK hoặc parser chỉ cung cấp cách gọi như `nextRecord()`, `readNextBatch()`, `fetchPage(cursor)`.
3. **Tiêu thụ nguồn một lần.** Dữ liệu đọc từ socket, parser hoặc con trỏ không tua lại được; adapter phải xác định quyền sở hữu và vòng đời rõ ràng.
4. **Tạo phần tử từ một máy trạng thái** có điều kiện kết thúc đặc thù, không biểu diễn rõ bằng `iterate` hoặc `generate`.
5. **Quản lý metadata của Spliterator**: encounter order, ước lượng kích thước, khả năng phân tách công việc và các đặc tính khác cần mô tả chính xác.
6. **Tích hợp cleanup tài nguyên**: trả về Stream cùng `onClose(...)` hoặc bao kết quả trong một abstraction có quyền đóng, để caller không rò tài nguyên.
7. **Giảm bộ nhớ khi nguồn lớn**: chỉ giữ phần dữ liệu cần xử lý, thay vì materialize toàn bộ dữ liệu vào RAM từ đầu; lợi ích vẫn phụ thuộc terminal operation và stateful stages.

Các lý do không đủ thuyết phục: “muốn code trông functional hơn”, “chỉ cần thêm một `filter`”, “cần sort một mảng”, “cần đổi Integer thành String”, “muốn Stream chạy bất đồng bộ” hoặc “muốn tự động nhanh hơn”.

**Stream là abstraction xử lý dữ liệu, không tự động là reactive stream hay hệ thống backpressure/asynchronous I/O.** Một nguồn tùy chỉnh blocking có thể vẫn block thread đang tiêu thụ khi cần phần tử tiếp theo.

## 7. Adapter từ Iterator: bước ít phức tạp trước khi viết Spliterator riêng

Nhiều API cũ đã cung cấp `Iterator<T>` nhưng không cung cấp `Stream<T>`. Java có thể tạo Spliterator bao quanh iterator:

```java
Spliterator<String> sp = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

Stream<String> stream = StreamSupport.stream(sp, false);
```

Đây là đoạn trong phương thức đã có `Iterator<String> iterator`, với import `Spliterator`, `Spliterators` và `StreamSupport`. Đối số `false` yêu cầu **sequential Stream**. Tránh đánh dấu `NONNULL` nếu iterator thực sự có thể trả null.

Lưu file `IteratorAdapterDemo.java`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class IteratorAdapterDemo {
    static <T> Stream<T> fromIterator(Iterator<T> iterator) {
        Spliterator<T> spliterator =
                Spliterators.spliteratorUnknownSize(
                        iterator, Spliterator.ORDERED);
        return StreamSupport.stream(spliterator, false);
    }

    public static void main(String[] args) {
        Iterator<String> legacy = List.of(
                "Lan", "An", "Binh").iterator();

        String result = fromIterator(legacy)
                .filter(name -> name.length() >= 3)
                .collect(Collectors.joining(", "));

        System.out.println(result);
    }
}
```

Biên dịch/chạy:

```bash
javac IteratorAdapterDemo.java
java IteratorAdapterDemo
```

Output:

```text
Lan, Binh
```

Đây là adapter cho **một iterator một lần**. Nếu từ đầu bạn đã có `List` như ví dụ mô phỏng, dùng `list.stream()` đơn giản hơn. Khi iterator đến từ SDK, database cursor hoặc parser thật, adapter có thể giúp đưa việc xử lý tiếp vào Stream API mà không cần tải toàn bộ dữ liệu.

**Không sử dụng lại iterator đã tiêu thụ** để mong tạo Stream đi qua cùng dữ liệu từ đầu. Quyền reset/reopen thuộc về API dữ liệu nguồn, không phải Stream.

## 8. Khi cần tự định nghĩa Spliterator

`Spliterator<T>` vừa là abstraction duyệt phần tử vừa mô tả khả năng chia nguồn. Hai phương thức cốt lõi:

```java
boolean tryAdvance(Consumer<? super T> action);
Spliterator<T> trySplit();
```

Đây là chữ ký phương thức cốt lõi để giải thích API, không phải một interface Java tự định nghĩa.

- `tryAdvance(action)`: nếu có phần tử tiếp theo, thực hiện action với phần tử đó và trả `true`; khi nguồn đã hết, trả `false`. **Không được trả true mà không chuyển phần tử**.
- `trySplit()`: có thể trả một Spliterator khác quản lý **một tập phần tử không trùng** với phần còn lại, hỗ trợ parallel; nếu không tách được, trả `null`.
- `estimateSize()`: ước lượng số phần tử còn lại; không được khẳng định độ chính xác nếu không biết.
- `characteristics()`: bit flags như `ORDERED`, `SIZED`, `NONNULL`, `IMMUTABLE` phải phản ánh **sự thật của nguồn**.

Lớp tiện ích `Spliterators.AbstractSpliterator<T>` giảm lượng mã cần viết: có triển khai mặc định cho một số phần như `estimateSize()`, `characteristics()` và `trySplit()`. Ta có thể override `trySplit()` trả `null` để biểu thị nguồn trạng thái chỉ hỗ trợ duyệt tuần tự, thay vì hứa khả năng phân tách mà không làm được.

Tạo Stream từ Spliterator:

```java
Stream<T> result = StreamSupport.stream(spliterator, false);
```

Đây là mẫu generic trong ngữ cảnh đã có `Spliterator<T> spliterator`. `StreamSupport.stream` kết nối nguồn tùy chỉnh với pipeline Stream. Đối số boolean là cờ yêu cầu parallel; nó **không bảo đảm tăng tốc**, nhất là khi trySplit không thể chia nguồn.

## 9. Ví dụ Java 17 hoàn chỉnh: nguồn phân trang lấy dữ liệu khi cần

Giả sử một API trả từng trang số nguyên, với trang rỗng báo hết dữ liệu. Ta muốn tạo Stream chỉ gọi API để lấy trang mới khi đã dùng hết trang hiện tại.

Ví dụ cố tình dùng một hàm giả lập thay cho network để output chính xác và có thể chạy ngay. Cách kết nối với API thật chỉ cần thay logic `fetch.apply(pageNumber)` theo contract tương ứng.

Lưu file `PagedSourceDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Consumer;
import java.util.function.IntFunction;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class PagedSourceDemo {
    static Stream<Integer> fromPages(
            IntFunction<List<Integer>> fetch) {

        Objects.requireNonNull(fetch);

        Spliterator<Integer> spliterator =
                new Spliterators.AbstractSpliterator<>(
                        Long.MAX_VALUE,
                        Spliterator.ORDERED | Spliterator.NONNULL) {

                    int pageNumber = 0;
                    int position = 0;
                    List<Integer> page = List.of();
                    boolean done = false;

                    @Override
                    public boolean tryAdvance(
                            Consumer<? super Integer> action) {
                        Objects.requireNonNull(action);

                        while (!done) {
                            if (position < page.size()) {
                                action.accept(page.get(position++));
                                return true;
                            }

                            page = Objects.requireNonNull(
                                    fetch.apply(pageNumber++));
                            position = 0;

                            if (page.isEmpty()) {
                                done = true;
                            }
                        }
                        return false;
                    }

                    @Override
                    public Spliterator<Integer> trySplit() {
                        return null; // Nguồn một cursor, duyệt tuần tự.
                    }
                };

        return StreamSupport.stream(spliterator, false);
    }

    static List<Integer> fetchPage(int pageNumber) {
        System.out.println("fetch page " + pageNumber);

        return switch (pageNumber) {
            case 0 -> List.of(7, 2);
            case 1 -> List.of(9, 4);
            default -> List.of();
        };
    }

    public static void main(String[] args) {
        Stream<Integer> firstStream =
                fromPages(PagedSourceDemo::fetchPage);

        System.out.println("stream created");

        List<Integer> firstTwoAboveFive = firstStream
                .filter(n -> n > 5)
                .limit(2)
                .toList();

        System.out.println("selected=" + firstTwoAboveFive);

        int total = fromPages(PagedSourceDemo::fetchPage)
                .mapToInt(Integer::intValue)
                .sum();

        System.out.println("sum=" + total);
    }
}
```

Biên dịch/chạy:

```bash
javac PagedSourceDemo.java
java PagedSourceDemo
```

Output xác định cho ví dụ tuần tự:

```text
stream created
fetch page 0
fetch page 1
selected=[7, 9]
fetch page 0
fetch page 1
fetch page 2
sum=22
```

Giải thích từng mốc:

1. `fromPages(...)` tạo Spliterator và Stream; nó **chưa gọi hàm lấy trang**. Bởi vậy `stream created` được in trước `fetch page 0`.
2. Terminal `toList()` trên pipeline có `filter(n -> n > 5).limit(2)` bắt đầu yêu cầu các phần tử.
3. Trang 0 có `[7,2]`: 7 được nhận, 2 bị lọc. Trang 1 có `[9,4]`: 9 là giá trị thỏa thứ hai, đủ cho `limit(2)`; không cần lấy trang 2.
4. Để tính tổng toàn bộ nguồn, ta tạo **Stream mới**, có trạng thái trang mới. Nó gọi page 0, 1 rồi page 2 rỗng để nhận biết hết nguồn; tổng 7 + 2 + 9 + 4 = 22.
5. `trySplit()` trả `null` vì ví dụ dùng một cursor phân trang theo thứ tự. Đây là lựa chọn trung thực: không có chiến lược tách trang độc lập an toàn cho parallel.

**Giới hạn của ví dụ:** quy tắc “trang rỗng nghĩa là hết” chỉ là hợp đồng API giả lập. API thật có thể dùng cursor/token/hasMore hoặc trả trang rỗng tạm thời nhưng vẫn còn dữ liệu; khi đó **phải triển khai theo hợp đồng thật**, không tự dùng trang rỗng làm điều kiện dừng.

Cần suy nghĩ thêm về timeout, retry, lỗi mạng, hủy tiêu thụ và đóng tài nguyên trước khi đưa adapter mạng vào sản xuất. Không được tự động retry một lời gọi có side effect mà không xét idempotency.

## 10. Vì sao không chỉ dùng `Stream.generate()` cho paging?

Có thể viết một Supplier giữ trạng thái trang và kết hợp với `Stream.generate`. Nhưng `generate` tạo nguồn **vô hạn** theo hợp đồng, không có cách biểu diễn “hết phần tử” trực tiếp bằng Supplier trả null: null là một **giá trị phần tử**, không phải tín hiệu kết thúc Stream. Bạn có thể dùng sentinel + `takeWhile` hoặc một dạng wrapper, nhưng phải xét các trường hợp dữ liệu null hợp lệ, short-circuit và thread safety.

Ví dụ một nguồn có số trang cố định có thể làm đơn giản hơn với `IntStream.range(0, numberOfPages).mapToObj(fetchPage).flatMap(List::stream)`. Nếu tổng số trang biết trước và các trang độc lập, cách này có thể **không cần Spliterator tùy chỉnh**.

Lựa chọn:

| Bài toán | Cách viết ưu tiên |
| --- | --- |
| Sinh giá trị độc lập vô hạn | `Stream.generate(supplier)` kết hợp giới hạn/terminal thích hợp |
| Dãy trạng thái có quy tắc next và điều kiện dừng | `Stream.iterate(seed, hasNext, next)` |
| API có số trang cố định | `IntStream.range(...).mapToObj(fetch).flatMap(...)` |
| API chỉ có `Iterator` một lần | `spliteratorUnknownSize + StreamSupport.stream` |
| API paging có cursor và thời điểm kết thúc riêng | Có thể dùng Spliterator tùy chỉnh |
| API đã trả `Stream<T>` chính xác | Dùng Stream có sẵn, không bọc lại vô cớ |

**Một nguồn tùy chỉnh có thể tốt hơn nếu việc dừng và trạng thái hiện có không diễn đạt gọn bằng các factory chuẩn.** Nhưng điều đó không làm mất các quy tắc Stream về một lần tiêu thụ, short-circuit, tài nguyên và thread safety.

## 11. Chi tiết quan trọng: source laziness không giống side effect khi dựng nguồn

Nhìn lại:

```java
Stream<String> stream = Stream.of(loadData());
```

Ở đây, `loadData()` là đối số của lời gọi phương thức nên Java đánh giá nó **ngay khi tạo nguồn**. Dù các stage phía sau là lazy, phép I/O trong `loadData()` không được hoãn.

Còn:

```java
Stream<String> stream = Stream.generate(() -> loadData())
        .limit(1);
```

Lời gọi `loadData()` nằm trong thân Supplier, nên được yêu cầu lúc tiêu thụ phần tử. Hai đoạn này không tương đương về thời điểm I/O, dù nếu `loadData()` trả cùng giá trị, kết quả một phần tử có thể giống nhau.

Với `StreamSupport.stream(spliterator, false)`, sự lười chủ yếu đến từ `tryAdvance`. Nhưng **constructor và các câu lệnh tạo Spliterator vẫn chạy khi tạo đối tượng**. Nếu code tự gọi API trong constructor để lấy trang đầu tiên, I/O vẫn chạy sớm.

Khi đặc biệt cần **trì hoãn gắn nguồn** tới lúc bắt đầu terminal, `StreamSupport` có overload nhận một `Supplier<? extends Spliterator<T>>` cùng giá trị characteristics và cờ parallel:

```java
Stream<T> stream = StreamSupport.stream(
        spliteratorSupplier,
        characteristics,
        false
);
```

Đây là mẫu generic để hiểu API; cần có biến supplier phù hợp, characteristics phản ánh đúng Spliterator mà supplier tạo, và đầy đủ import. Overload này có thể trì hoãn việc gọi supplier cho tới khi bắt đầu terminal operation, đồng thời có lợi khi nguồn có thể biến đổi giữa lúc xây pipeline và lúc tiêu thụ. Nhưng **biểu thức tạo supplier** vẫn được đánh giá bình thường, và source có thể gắn tài nguyên khi supplier được gọi. Dùng đúng khi có yêu cầu thực tế, không mặc định mọi source cần overload này.

## 12. Spliterator characteristics: chỉ khai báo điều bạn chứng minh được

Cờ characteristics giúp Stream framework hiểu nguồn. Khai báo sai có thể tạo ra kết quả sai hoặc bỏ qua xử lý cần thiết.

| Flag | Ý nghĩa | Sai lầm điển hình |
| --- | --- | --- |
| `ORDERED` | Nguồn có encounter order xác định | Khai báo cho một nguồn vốn không có thứ tự |
| `DISTINCT` | Các phần tử theo nghĩa equality không trùng | Khai báo dù API có thể phát trùng |
| `SORTED` | Phần tử được sắp theo comparator/natural order phù hợp | Khai báo dù nguồn chưa thật sự sorted |
| `SIZED` | Biết đúng số phần tử còn lại | Khai báo cho nguồn phân trang chưa biết bao nhiêu bản ghi |
| `SUBSIZED` | Mọi Spliterator tạo ra khi split cũng có size chính xác | Khai báo khi chia nguồn chưa có khả năng đếm đúng |
| `NONNULL` | Nguồn bảo đảm không trả phần tử null | Khai báo dù cursor có thể trả null |
| `IMMUTABLE` | Nguồn phần tử không chịu structural modification theo hợp đồng | Khai báo cho collection mutable bị thay đổi giữa lúc duyệt |
| `CONCURRENT` | Nguồn hỗ trợ sửa đồng thời theo hợp đồng phù hợp | Gắn cờ chỉ vì có nhiều thread dùng nguồn |

Trong ví dụ paging ở trên, nguồn có thứ tự trang và các phần tử int boxed không null, nên `ORDERED | NONNULL` hợp lý. Nhưng **không biết kích thước tổng**, nên không khai báo `SIZED`. Việc trả `Long.MAX_VALUE` cho estimate ban đầu là một ước lượng đại diện “unknown” theo mẫu AbstractSpliterator; nó **không có nghĩa sẽ có Long.MAX_VALUE bản ghi**.

Lưu ý về `IMMUTABLE`: immutable characteristics nói về tính ổn định về cấu trúc của nguồn trong quá trình duyệt, không có nghĩa các object phần tử tự thân đều immutable. Mỗi flag phải tương ứng với bảo đảm thực sự của nguồn dữ liệu, không phải mong muốn.

## 13. Nguồn tùy chỉnh và parallel: có nên bật `true`?

`StreamSupport.stream(spliterator, true)` yêu cầu parallel pipeline, nhưng để thật sự chia nguồn hiệu quả, `trySplit()` cần cung cấp các phần dữ liệu độc lập, không trùng lặp, có thể xử lý đồng thời.

Đối với cursor chỉ tiến về phía trước hoặc API trang phải chờ token của trang trước, cố chia nguồn có thể làm hỏng thứ tự, duplicate record hoặc mất bản ghi. Trong trường hợp này, hãy trả `null` từ `trySplit()` và dùng sequential stream.

Nếu dữ liệu có thể chia theo index/partition độc lập, có thể cân nhắc Spliterator hỗ trợ split. Khi tự viết, phải bảo đảm:

1. Mỗi phần tử thuộc **đúng một** nhánh sau khi tách, không bị lặp hoặc mất.
2. Không có race giữa các nhánh trên cursor/state dùng chung.
3. Các đặc tính `ORDERED`, `SIZED`, `SUBSIZED` và size estimate vẫn đúng sau split.
4. Thứ tự kết quả nếu cần được giữ theo hợp đồng Stream; thứ tự callback không tự động tương đương encounter order.
5. Chi phí split/merge phù hợp; parallel không mặc định nhanh hơn.

Nếu nguồn đã là List hoặc mảng, Spliterator chuẩn của JDK thường đã hỗ trợ chia tốt hơn một implementation tự viết đơn giản. Do đó, chỉ tự viết parallel Spliterator khi có lý do rõ và kiểm thử nghiêm túc.

## 14. Tài nguyên: terminal operation không tự đóng Stream

Khi nguồn đọc file, database cursor, socket hoặc handle ngoài JVM, phần quan trọng nhất là **ai sở hữu tài nguyên và khi nào đóng?**

Một hiểu lầm nguy hiểm: gọi `toList()` hoặc `count()` thì Stream tự động đóng mọi resource. Theo API, **Stream không được tự động đóng bởi terminal operation**. Với Stream có nguồn I/O cần đóng, ứng dụng nên dùng `try-with-resources` và đóng rõ.

Nguồn JDK đã làm mẫu đúng:

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> selected = lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .toList();
    System.out.println(selected);
}
```

Đây là đoạn mã trong phương thức có `Path path` và import `Files`, `StandardCharsets`, `Stream`, `List`, và cần xử lý/khai báo `IOException`. `Files.lines` mở tài nguyên file; đóng Stream giải phóng tài nguyên liên quan.

Với nguồn tùy chỉnh, có thể gắn hành động cleanup:

```java
Stream<Record> stream = StreamSupport
        .stream(spliterator, false)
        .onClose(() -> cursor.close());
```

Đây là **mẫu thiết kế minh họa**, giả định `cursor.close()` không ném checked exception hoặc đã được xử lý thích hợp. Phải dùng `try (Stream<Record> stream = ...)` ở phía consumer để đảm bảo gọi `close()`. `onClose` không đồng nghĩa terminal tự gọi cleanup.

**Cần suy nghĩ về thời điểm mở nguồn:** nếu mở cursor ngay khi gọi factory nhưng caller không đóng Stream, có nguy cơ rò rỉ; nếu mở lười ở lần `tryAdvance` đầu, phải đảm bảo lỗi mở/đọc và dọn tài nguyên khi kết thúc sớm được xử lý. Với nhiều tài nguyên phức tạp, có thể cần abstraction `AutoCloseable` rõ ràng hơn thay vì chỉ cung cấp Stream.

## 15. Ví dụ Java 17: dùng nguồn file chuẩn và đóng đúng cách

Lưu `FileLinesSourceDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FileLinesSourceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("stream-source-", ".txt");

        try {
            Files.write(file, List.of(
                    "  Lan  ", "", "An", "  Binh"),
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {

                List<String> names = lines
                        .map(String::trim)
                        .filter(s -> !s.isBlank())
                        .toList();

                System.out.println(names);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac FileLinesSourceDemo.java
java FileLinesSourceDemo
```

Output:

```text
[Lan, An, Binh]
```

Đây là ví dụ có tạo file tạm để chạy độc lập; nó không cần tự viết Spliterator. Phần xử lý file được quản lý trong `try-with-resources` và file tạm được xóa trong `finally`. Nếu lỗi I/O xuất hiện khi đang duyệt `Files.lines`, implementation có thể bọc thành `UncheckedIOException`; vẫn cần thiết kế đường xử lý lỗi và cleanup đúng.

Việc file tồn tại sẵn trong thực tế không làm thay đổi nguyên tắc: **đã có nguồn JDK đọc dòng thì ưu tiên dùng nguồn đó**, chỉ tạo nguồn tùy chỉnh khi định dạng hoặc giao thức vượt khỏi khả năng hiện tại.

## 16. Stream từ nguồn bên ngoài không tự động là luồng bất đồng bộ

Khi gọi `terminalOperation` trên Stream tuần tự, framework kéo các phần tử qua nguồn theo nhu cầu. Với source truy cập mạng, một lần `tryAdvance` có thể phải chờ HTTP/API/database. Vì vậy pipeline Stream thường có thể **block thread đang gọi** trong thời gian truy xuất.

Không đồng nhất:

- Java Stream = API xử lý phần tử, hỗ trợ lazy intermediate operations và parallel trong những tình huống phù hợp.
- Reactive Streams/Flow API = mô hình phối hợp producer-consumer theo giao thức subscription, demand/backpressure và bất đồng bộ theo thiết kế cụ thể.
- Asynchronous I/O = cơ chế I/O không chặn hoặc trả kết quả qua future/callback/event.

Một nguồn Stream tùy chỉnh không tự biến server pagination thành backpressure đầy đủ hoặc retry/resilience chính xác. Nếu ứng dụng cần xử lý liên tục, nhiều người tiêu thụ, hủy theo demand hay giao thức async, nên đánh giá mô hình API phù hợp thay vì ép mọi vấn đề vào `StreamSupport.stream`.

## 17. Null, dữ liệu lỗi và quy tắc kết thúc

Khi tự xây nguồn, có ba tình huống cần tách:

1. **Có phần tử null hợp lệ:** nếu API cho phép, không khai báo `NONNULL`; quyết định stage downstream xử lý null ra sao.
2. **Không còn phần tử:** `tryAdvance` trả `false`; đó là tín hiệu kết thúc của Spliterator, **không** phải một lời gọi `action.accept(null)`.
3. **Nguồn lỗi:** nên phát exception phù hợp, tránh tự trả `false` để che giấu lỗi đọc dữ liệu và làm kết quả thiếu bản ghi không rõ nguyên nhân.

Nếu API phân trang có thể trả một **trang rỗng nhưng chưa hết**, cần dùng field `hasMore` hoặc next cursor từ response. Nếu API có thể trả duplicate sau retry hoặc thay đổi thứ tự giữa các trang, phải xác định idempotency và consistency; Spliterator không sửa hộ giao thức nguồn.

Không hứa rằng một stream từ nguồn ngoài luôn có thể chạy lại. Nếu cursor chỉ một lần, muốn chạy lại phải mở cursor mới hoặc cung cấp một factory tạo nguồn mới, có quản lý tài nguyên cho từng lượt.

## 18. Nguồn custom có thể khó test hơn nguồn JDK

Một adapter tùy chỉnh nên được kiểm thử ở **ranh giới lấy phần tử**, không chỉ ở một terminal operation.

Checklist kiểm thử:

- **Đầy đủ:** mọi phần tử được phát đúng một lần, đúng giá trị, không mất/nhân đôi.
- **Thứ tự:** nguồn có ORDERED thì thứ tự đúng theo contract nguồn, kể cả khi có trang rỗng hoặc dữ liệu trùng.
- **Kết thúc:** nguồn hết → `tryAdvance` trả false; không liên tục gọi API sau khi đã done.
- **Short-circuit:** `limit(n)` / `findFirst()` không tải thêm trang không cần thiết khi có thể tránh.
- **Null:** không tuyên bố NONNULL sai; không biến null thành kết thúc nếu null là dữ liệu.
- **Lỗi:** exception từ fetch được truyền/biến đổi theo hợp đồng, cleanup không bị bỏ quên.
- **Close:** `onClose` có được gọi khi consumer đóng và trong các trường hợp exception không?
- **Một lần dùng:** Stream không thể bị tiêu thụ lại; adapter không vô tình chia sẻ cursor giữa các lượt.
- **Parallel:** nếu có split, các nhánh không chồng lấn và metadata đúng.
- **Kích thước:** không khai báo SIZED khi chỉ biết một ước lượng.
- **Timeout/cancellation:** source ngoài có thể đang block; cần chiến lược cancel thực tế nếu hệ thống yêu cầu.
- **Hiệu năng:** đo việc fetch, số lần gọi API, memory và chi phí kết hợp thay vì chỉ xem cách viết code.

Với nguồn tùy chỉnh thật, nên kiểm thử bằng một **fake fetcher** có đếm số lần gọi để xác minh lazy fetching, sau đó dùng integration test cho API thật.

## 19. Những lỗi thiết kế thường gặp

1. **Tự tạo Spliterator chỉ để lọc List.** Dùng `list.stream().filter(...)`; đừng biến đổi dữ liệu thành vấn đề tạo nguồn.
2. **Tưởng mọi API bên ngoài đều cần nguồn custom.** Nếu SDK đã có Stream hoặc Iterator tốt, hãy dùng hoặc bọc tối thiểu.
3. **Tưởng `generate` trả null là hết nguồn.** Null không phải tín hiệu kết thúc Stream; cần điều kiện dừng rõ.
4. **Đánh dấu `SIZED` khi chưa biết số bản ghi.** Vi phạm sự thật về số phần tử và có thể làm framework tối ưu sai.
5. **Khai báo `NONNULL` dù API đôi khi trả null.** Tạo metadata không trung thực.
6. **Dùng parallel với một cursor chia không được.** Dễ race hoặc làm hỏng thứ tự; nếu không split an toàn, dùng sequential.
7. **Tin rằng terminal tự đóng file/cursor.** Dùng `try-with-resources`, `close()` và `onClose` theo hợp đồng.
8. **Gọi API khi dựng Stream nhưng quảng cáo nguồn là lazy.** Cần phân biệt constructor/callback creation với `tryAdvance` và Supplier.
9. **Materialize mọi trang vào List trước dù mục tiêu chỉ lấy hai phần tử.** Mất lợi thế lazy fetching; cân nhắc adapter theo nhu cầu.
10. **Trả null như sentinel trong nguồn có dữ liệu null hợp lệ.** Phải phân biệt giá trị hợp lệ và tín hiệu kết thúc bằng giao thức/kiểu rõ.
11. **Cho rằng `StreamSupport.stream(..., true)` luôn nhanh.** Parallel có chi phí và cần Spliterator thực sự chia được.
12. **Viết iterator/spliterator có trạng thái dùng chung rồi chia sẻ cho nhiều Stream.** Gây lỗi tiêu thụ, race và dữ liệu mất/trùng.
13. **Bỏ qua ngoại lệ từ API trong `tryAdvance`.** Dễ cho kết quả thiếu mà không báo lỗi.
14. **Tin rằng `onClose` tự chạy khi đến cuối nguồn.** Phải đóng Stream hoặc tài nguyên theo trách nhiệm caller.
15. **Dựa vào thứ tự log để suy ra thứ tự dữ liệu khi parallel.** Callback có thể chạy không theo encounter order.
16. **Tự làm lại nguồn đọc file chuẩn JDK.** Trừ khi cần parse/giao thức đặc biệt, `Files.lines` thường an toàn hơn.
17. **Cho rằng mọi stream có thể lấy lại toàn bộ dữ liệu bằng cách gọi terminal lần hai.** Stream dùng một lần; cursor cũng thường không tua lại.
18. **Cố dùng Stream cho dữ liệu reactive vô hạn không có chiến lược dừng.** Cần xem mô hình backpressure/hủy và lựa chọn API phù hợp.

## 20. Bài tập tự kiểm tra

### Bài 1: Chọn nguồn phù hợp

Hãy chọn API thích hợp nhất cho từng trường hợp:

A. Có `List<Product>` trong bộ nhớ, muốn lọc sản phẩm còn hàng.

B. Có một mảng `int[]`, muốn tính tổng.

C. Có dãy index từ 0 đến n-1.

D. Có `Iterator<Record>` từ thư viện cũ, chỉ hỗ trợ đi tới, không có Stream.

E. Có API phân trang mà chỉ nhận next cursor sau khi gọi trang hiện tại; mong chỉ tải đủ bản ghi cho `limit(5)`.

F. Có file văn bản cần duyệt từng dòng và đóng handle.

**Gợi ý đáp án:**

- A: `list.stream().filter(...)`.
- B: `Arrays.stream(array).sum()`.
- C: `IntStream.range(0, n)`.
- D: Adapter bằng `spliteratorUnknownSize(iterator, characteristics)` rồi `StreamSupport.stream(..., false)`, cân nhắc cleanup nguồn.
- E: Nguồn custom theo paging/cursor hoặc adapter lười phù hợp nếu API JDK đơn giản chưa đủ; thiết kế cách dừng/close/exception rõ.
- F: `try (Stream<String> lines = Files.lines(path)) { ... }`.

### Bài 2: Hiểu output của nguồn phân trang

Trong ví dụ `PagedSourceDemo`, nếu chỉ dùng:

```java
List<Integer> values = fromPages(PagedSourceDemo::fetchPage)
        .filter(n -> n > 5)
        .limit(1)
        .toList();
```

điều gì được in?

**Đáp án:** fetch chỉ trang 0 vì trang đó đã có 7 thỏa điều kiện; kết quả là `[7]`. Việc tạo Stream không tải trang 0 trước terminal.

### Bài 3: Cờ characteristics

Một API có thể trả null, không biết trước số bản ghi, nhưng trả bản ghi theo thứ tự cursor. Có thể khai báo `SIZED | NONNULL | ORDERED` không?

**Đáp án:** Không. Chỉ `ORDERED` có căn cứ từ mô tả; `SIZED` và `NONNULL` là sai. Việc trả estimate “unknown” không biến nguồn thành SIZED.

### Bài 4: Vì sao cần đóng Stream?

Một Stream từ file trả đúng List sau `toList()`. Vậy có thể bỏ `try-with-resources` không?

**Đáp án:** Không. Terminal operation không có nghĩa tài nguyên bên ngoài sẽ được đóng tự động. `Files.lines` cần đóng Stream theo hợp đồng để giải phóng handle.

### Bài 5: Có cần custom Spliterator cho API có tổng số trang xác định?

Có 10 trang độc lập, có thể gọi `fetch(pageNo)` bằng số trang. Có thể tránh tự viết Spliterator không?

**Đáp án:** Có thể dùng `IntStream.range(0, 10).mapToObj(fetch::apply).flatMap(List::stream)`, với cách xử lý lỗi và giới hạn tài nguyên phù hợp. Khi API có cursor phụ thuộc kết quả trang trước hoặc cần cleanup phức tạp, adapter riêng có thể có lợi hơn.

## 21. Checklist quyết định áp dụng vào dự án

Trước khi tạo nguồn Stream tùy chỉnh, hãy viết ngắn gọn một hợp đồng:

1. **Nguồn gốc:** collection, mảng, file, iterator, database cursor, API paging hay bộ sinh?
2. **Factory JDK nào đã đủ?** Kiểm tra `stream`, `Arrays.stream`, `of`, `range`, `iterate`, `generate` và `Files.lines`.
3. **Lý do khác biệt cụ thể:** lazy fetching, protocol dừng, metadata, resource, splitting hay một tập yêu cầu khác?
4. **Phần tử:** kiểu, null, trạng thái mutable và quy tắc equality.
5. **Kết thúc:** biết kích thước, nhận EOF, next cursor hay dấu hiệu nguồn hết?
6. **Thứ tự:** có encounter order thật không, hay chỉ quan sát tình cờ?
7. **Tài nguyên:** ai mở, ai đóng, đóng khi lỗi hoặc short-circuit thế nào?
8. **Đồng thời:** có chia nguồn an toàn không, hay phải sequential?
9. **Khả năng dùng lại:** phải tạo stream/cursor mới mỗi lần không?
10. **Chi phí:** số lần gọi API, kích thước trang, memory và terminal operation.
11. **Kiểm thử:** trường hợp rỗng, một phần tử, nhiều trang, lỗi, cancel và close.
12. **Tài liệu:** caller cần biết dùng `try-with-resources` và các giới hạn nào?

**Kết luận:** nếu dữ liệu đã đến từ List, mảng, dãy số, file dòng hay Iterator, **ưu tiên nguồn hoặc adapter chuẩn JDK**. Chỉ viết nguồn tùy chỉnh khi cần biểu diễn đúng một giao thức phát phần tử mà API chuẩn không diễn đạt hợp lý, như cursor phân trang hoặc parser trạng thái đặc thù. Khi đã tự tạo nguồn, trách nhiệm không chỉ là phát ra giá trị, mà còn là nói đúng về **laziness, thứ tự, kích thước, tài nguyên, lỗi và khả năng chia việc**.

**Tham khảo:** Java SE 17 API `java.util.stream.StreamSupport`, `java.util.Spliterator`, `java.util.Spliterators`, `java.util.stream.Stream`, `java.util.stream.IntStream`, `java.nio.file.Files.lines`; Java Stream package specification về lazy evaluation, non-interference và resource handling.