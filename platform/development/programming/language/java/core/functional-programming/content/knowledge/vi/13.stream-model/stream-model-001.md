# Stream là dòng xử lý dữ liệu và không phải cấu trúc lưu trữ trong Java

## 1. Hiểu đúng bản chất của Stream

`java.util.stream.Stream<T>` mô tả **một chuỗi phần tử để thực hiện các phép tính trên chúng**. Một Stream thường lấy phần tử từ một *nguồn* (source), đưa chúng qua các thao tác trung gian và chỉ tính toán khi có thao tác kết thúc (*terminal operation*). Bản thân Stream **không phải một cấu trúc lưu trữ dữ liệu** như `List`, `Set` hay mảng.

Ví dụ:

```java
List<String> names = List.of("Lan", "Minh", "An");

List<String> shortNames = names.stream()
        .filter(name -> name.length() <= 3)
        .map(String::toUpperCase)
        .toList();

// shortNames: [LAN, AN]
// names vẫn là [Lan, Minh, An]
```

`names` là collection chứa các phần tử; `names.stream()` tạo một Stream dùng để xử lý dữ liệu từ collection đó. `filter` và `map` mô tả những gì cần làm, còn `toList()` thực thi pipeline và trả về một **đối tượng List mới** mang kết quả. Chính danh sách kết quả này lưu trữ các phần tử, không phải Stream trước khi kết thúc.

Một Stream có thể có các vùng đệm nội bộ để thực hiện những phép toán nhất định như `sorted` hoặc `distinct`, nhưng đó là chi tiết phục vụ xử lý, **không biến Stream thành container lưu trữ lâu dài**. Stream cũng có thể xử lý nguồn không phải collection, ví dụ dãy số được sinh ra hoặc các dòng đọc từ tệp.

## 2. Cấu trúc pipeline: nguồn → trung gian → kết thúc

Một pipeline Stream điển hình gồm ba thành phần:

```text
Nguồn (source)
  List / Set / array / generator / file ...
        │
        ▼
   Stream<T>
        │
        ▼
Thao tác trung gian (intermediate)
  filter → map → distinct → sorted → limit ...
        │
        ▼
Thao tác kết thúc (terminal)
  toList / collect / forEach / count / reduce / findFirst ...
        │
        ▼
Kết quả / tác dụng phụ / Optional / scalar / collection mới
```

### Nguồn (source)

Nguồn cung cấp phần tử để Stream xử lý. Các cách tạo thường gặp:

```java
List<String> words = List.of("a", "bb", "ccc");
Stream<String> fromList = words.stream();

Stream<String> fromValues = Stream.of("a", "bb", "ccc");

int[] numbers = {1, 2, 3};
java.util.stream.IntStream fromArray = java.util.Arrays.stream(numbers);

java.util.stream.IntStream fromRange =
        java.util.stream.IntStream.range(0, 3); // 0, 1, 2
```

Đây là các đoạn minh họa riêng; cần import `java.util.List`, `java.util.stream.Stream` (và `Arrays` nếu không ghi tên đầy đủ). Tạo Stream không có nghĩa là mọi phần tử đã được chép thành một collection mới. Với nguồn collection, Stream thường truy cập dữ liệu nguồn khi pipeline được tiêu thụ.

### Thao tác trung gian (intermediate operation)

Thao tác trung gian như `filter`, `map`, `flatMap`, `peek`, `sorted`, `distinct`, `skip`, `limit` trả về một Stream tiếp tục mô tả chuỗi xử lý. Phần lớn chúng không duyệt nguồn ngay khi được khai báo.

```java
Stream<String> pipeline = Stream.of("A", "BB", "CCC")
        .filter(s -> s.length() >= 2)
        .map(String::toLowerCase);

// Chưa có terminal operation; pipeline vẫn chỉ là mô tả xử lý.
```

Có các thao tác **stateless** như `map` và `filter`, xử lý từng phần tử không cần giữ trạng thái của phần tử khác. Có các thao tác **stateful** như `sorted` và `distinct` có thể cần ghi nhớ/buffer để tạo đúng kết quả. Vì vậy không được hiểu “lười” là “không bao giờ lưu bất cứ dữ liệu trung gian nào”.

### Thao tác kết thúc (terminal operation)

Terminal operation yêu cầu đánh giá pipeline, thường tạo kết quả hoặc tác dụng phụ:

```java
List<String> result = pipeline.toList(); // [bb, ccc]
```

Sau terminal operation, **không sử dụng lại cùng Stream instance** để thực hiện thao tác tiếp. Nếu muốn chạy lại, hãy tạo Stream mới từ nguồn hoặc tạo một hàm/supplier sinh Stream mới.

Một số terminal operation là *short-circuiting*, ví dụ `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`: có thể dừng sớm khi đã xác định được kết quả. `limit` là thao tác trung gian short-circuiting nên cũng có thể giới hạn việc lấy dữ liệu từ nguồn.

## 3. Stream khác Collection như thế nào?

| Đặc điểm | `Collection` / `List` | `Stream` |
| --- | --- | --- |
| Mục đích chính | Quản lý tập hợp phần tử | Diễn tả và thực thi phép tính trên chuỗi phần tử |
| Lưu trữ | Có cấu trúc chứa phần tử | Không phải container lưu trữ kết quả lâu dài |
| Sử dụng lặp lại | Có thể duyệt nhiều lần (tùy collection và thay đổi nguồn) | Một pipeline chỉ dùng một lần |
| Truy cập bằng chỉ số | `List` có `get(index)` | Không có API truy cập ngẫu nhiên như `get(index)` |
| Thay đổi phần tử | Phụ thuộc collection có cho phép mutation hay không | Không có `add`/`remove` để cập nhật nguồn như collection |
| Đánh giá | Thao tác collection có ngữ nghĩa riêng của từng method | Các bước trung gian thường lười; terminal kích hoạt tính toán |
| Kết quả | Các phần tử vẫn tồn tại trong collection | Có thể trả `List`, `Optional`, một giá trị, hoặc không trả giá trị |
| Nguồn dữ liệu | Chính collection sở hữu cấu trúc chứa phần tử | Có thể lấy từ collection, mảng, generator, tệp hoặc nguồn khác |

**Đừng nhầm `Stream` với `InputStream`/`OutputStream` của `java.io`.** `Stream<T>` trong package `java.util.stream` là API xử lý phần tử; `InputStream`/`OutputStream` làm việc với byte của luồng I/O. Chúng đều dùng từ “stream” nhưng có ngữ nghĩa, API và vòng đời khác nhau.

Một `List` có thể là **nguồn** của nhiều Stream khác nhau. Ngược lại, gọi `toList()` trên Stream sẽ sinh ra một `List` kết quả; bước này không làm bản thân Stream trở thành `List`.

## 4. Ví dụ Java 17+ hoàn chỉnh: thấy rõ không lưu trữ, lười và dùng một lần

Tạo file `StreamIsNotStorageDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamIsNotStorageDemo {
    private static void check(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("  Lan  ", "", "Minh", " An "));

        // Chỉ dùng bộ đếm để minh họa thời điểm filter được gọi.
        AtomicInteger inspected = new AtomicInteger();

        Stream<String> pipeline = source.stream()
                .filter(s -> {
                    inspected.incrementAndGet();
                    return !s.isBlank();
                })
                .map(String::strip)
                .map(s -> s.toUpperCase(Locale.ROOT));

        check(0, inspected.get(), "intermediate operations are lazy");
        System.out.println("beforeTerminal=" + inspected.get());

        // Terminal operation: pipeline thực sự duyệt và xử lý nguồn.
        List<String> result = pipeline.toList();

        check(4, inspected.get(), "all source elements inspected");
        check(List.of("LAN", "MINH", "AN"), result, "stream result");
        check(4, source.size(), "source still has four elements");
        check("  Lan  ", source.get(0), "source was not transformed");

        System.out.println("afterTerminal=" + inspected.get());
        System.out.println("result=" + result);
        System.out.println("sourceSize=" + source.size());
        System.out.println("sourceFirstUnchanged="
                + source.get(0).equals("  Lan  "));

        // Collection nguồn có thể tiếp tục tồn tại và được cập nhật.
        source.add("Bao");
        check(5, source.size(), "source updated");
        check(3, result.size(), "existing result stays separate");

        System.out.println("sourceSizeAfterAdd=" + source.size());
        System.out.println("resultSizeAfterAdd=" + result.size());

        // Tạo Stream MỚI từ cùng nguồn sau khi dữ liệu nguồn đổi.
        long freshCount = source.stream()
                .filter(s -> !s.isBlank())
                .count();
        check(4L, freshCount, "fresh stream sees updated source");
        System.out.println("freshCount=" + freshCount);

        boolean unmodifiable = false;
        try {
            result.add("EXTRA");
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        check(true, unmodifiable, "Stream.toList result is unmodifiable");
        System.out.println("resultUnmodifiable=" + unmodifiable);

        boolean reusedRejected = false;
        try {
            pipeline.count();
        } catch (IllegalStateException expected) {
            reusedRejected = true;
        }
        check(true, reusedRejected, "stream cannot be reused");
        System.out.println("streamReusedRejected=" + reusedRejected);

        List<Integer> range = IntStream.rangeClosed(1, 3)
                .boxed()
                .toList();
        check(List.of(1, 2, 3), range, "generated source");
        System.out.println("range=" + range);

        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac StreamIsNotStorageDemo.java
java StreamIsNotStorageDemo
```

Kết quả stdout theo đúng thứ tự:

```text
beforeTerminal=0
afterTerminal=4
result=[LAN, MINH, AN]
sourceSize=4
sourceFirstUnchanged=true
sourceSizeAfterAdd=5
resultSizeAfterAdd=3
freshCount=4
resultUnmodifiable=true
streamReusedRejected=true
range=[1, 2, 3]
tests=PASS
```

**Điều cần quan sát:**

1. `beforeTerminal=0`: khai báo `filter` và `map` chưa làm lambda trong `filter` chạy. Khi `toList()` tiêu thụ pipeline tuần tự, cả bốn phần tử của nguồn được kiểm tra.
2. `result` chứa ba chuỗi mới sau biến đổi; collection `source` vẫn giữ bốn phần tử ban đầu (bao gồm chuỗi rỗng). Vì vậy thao tác `filter` không tự xóa dòng khỏi danh sách nguồn và `map` không tự thay giá trị trong danh sách đó.
3. Sau khi thêm `"Bao"` vào `source`, kích thước `result` vẫn bằng 3; `result` là danh sách kết quả thu được trước lúc nguồn thay đổi. Một Stream **mới** từ `source` thấy dữ liệu hiện có, cho `freshCount=4`.
4. `Stream.toList()` từ Java 16 trả về danh sách **không thể chỉnh sửa**; cố `add` ném `UnsupportedOperationException`. Đây là tính chất của **danh sách trả về từ terminal operation**, không phải khả năng lưu trữ của Stream.
5. Đã gọi `pipeline.toList()` thì không gọi tiếp `pipeline.count()` trên cùng instance. Lời gọi thứ hai trong chương trình dùng `try/catch` chỉ để minh họa lỗi `IllegalStateException`.
6. `IntStream.rangeClosed(1, 3)` sinh một dãy số để tính toán mà không cần xây dựng danh sách đầu vào trước; chỉ khi `.boxed().toList()` thì chương trình thu thập các giá trị vào `List<Integer>`.

Bộ đếm `AtomicInteger` trong demo chỉ để quan sát việc `filter` được thực thi khi nào. Trong mã xử lý nghiệp vụ, tránh dựa vào side effect trong thao tác trung gian; Java có quyền tối ưu một số pipeline và bỏ qua những bước không ảnh hưởng kết quả. Ví dụ tiêu biểu: `list.stream().map(...).count()` có thể biết kích thước từ nguồn mà không gọi `map` trên từng phần tử.

## 5. Tính lười (laziness) không có nghĩa là không làm việc

Xét hai pipeline:

```java
List<String> items = List.of("a", "bb", "ccc");
Stream<String> selected = items.stream()
        .filter(s -> s.length() >= 2);

// selected mới chỉ mô tả thao tác lọc.
List<String> copied = selected.toList(); // [bb, ccc]
```

Lợi ích của tính lười:

- Các thao tác có thể được ghép thành pipeline trước khi chọn cách dùng kết quả.
- Có thể chỉ xử lý số phần tử cần thiết khi kết hợp với thao tác dừng sớm.
- Có thể đưa xử lý vào từng bước mà không buộc tạo một collection trung gian sau mỗi `filter` hoặc `map`.

Tuy vậy, Java không cam kết rằng mọi lambda trung gian luôn được gọi đúng một lần cho mỗi phần tử bất kể terminal operation. Stream có thể tối ưu nếu không làm thay đổi kết quả. Vì thế các lambda trong `map`, `filter`, `peek` nên **không có tác dụng phụ cần thiết cho tính đúng đắn**.

Một ví dụ ngắn về tính ngắn mạch:

```java
List<Integer> firstThreeEven = Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();

// [2, 4, 6]
```

`Stream.iterate(1, n -> n + 1)` là nguồn sinh ra dãy có thể vô hạn; `limit(3)` giới hạn số phần tử đầu ra. Không cần lưu toàn bộ dãy vô hạn. Ngược lại, đòi đánh giá toàn bộ nguồn vô hạn bằng các thao tác không dừng, như `.count()` không giới hạn trên một dãy tăng không kết thúc, là không thích hợp.

**Cẩn thận với `sorted`, `distinct` và các bước stateful:** chúng có thể cần bộ nhớ/tính toán trên nhiều phần tử trước khi trả kết quả. Tính lười không đồng nghĩa chi phí bộ nhớ luôn là hằng số, đặc biệt với nguồn lớn hoặc vô hạn.

## 6. Stream là một chuỗi xử lý dùng một lần

Quy tắc thiết kế quan trọng: **mỗi Stream instance chỉ được liên kết vào một pipeline và tiêu thụ một lần**. Có thể viết:

```java
long count = numbers.stream().filter(n -> n > 0).count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
```

Nếu `numbers` là `List<Integer>`, mỗi lần `numbers.stream()` trả về một instance mới. Điều này hợp lệ vì danh sách nguồn vẫn có thể được duyệt lại.

Ví dụ sai:

```java
// Sai: không sử dụng lại Stream sau một terminal operation.
Stream<Integer> oneShot = Stream.of(1, 2, 3);
long count = oneShot.count();
List<Integer> values = oneShot.toList(); // IllegalStateException
```

Ngay cả khi không có terminal operation, **tái sử dụng một Stream branch** để tạo nhiều nhánh pipeline cũng không phải cách dùng đúng. Nhiều thao tác đã liên kết Stream gốc với một pipeline khác; trường hợp tái sử dụng có thể bị phát hiện và ném `IllegalStateException`. Khi muốn nhiều phép tính, hãy tạo Stream mới từ nguồn hoặc tổng hợp các chỉ số trong một terminal/collector thích hợp.

Có thể dùng `Supplier<Stream<T>>` để mô tả cách tạo pipeline **mới mỗi lần gọi**:

```java
List<String> data = List.of("a", "bbb", "cc");

java.util.function.Supplier<Stream<String>> pipeline =
        () -> data.stream().filter(s -> s.length() > 1);

long count = pipeline.get().count();         // 2
List<String> values = pipeline.get().toList(); // [bbb, cc]
```

Mỗi `pipeline.get()` tạo một Stream độc lập. Nếu nguồn là I/O, generator có trạng thái hoặc một nguồn dùng một lần, việc gọi supplier nhiều lần **không tự bảo đảm** có thể phát lại dữ liệu; phải hiểu vòng đời và khả năng mở lại của nguồn.

## 7. Tạo kết quả không có nghĩa là Stream lưu kết quả

Một Stream có thể kết thúc bằng nhiều dạng:

```java
List<String> values = Stream.of("a", "bb").toList();
long size = Stream.of("a", "bb").count();
boolean exists = Stream.of("a", "bb").anyMatch(s -> s.length() == 2);
java.util.Optional<String> first = Stream.of("a", "bb").findFirst();
String joined = Stream.of("a", "bb").collect(
        java.util.stream.Collectors.joining(","));
```

Kết quả tương ứng: `[a, bb]`, `2`, `true`, `Optional[a]`, `"a,bb"`. Ở mỗi dòng là **một Stream mới**, nên hoàn toàn hợp lệ.

`Stream.toList()` trả về List không thể chỉnh sửa (Java 16+). `Collectors.toList()` **không cam kết** loại List, khả năng chỉnh sửa, cách triển khai hay tính thread-safe của List nhận được. Nếu cần một `ArrayList` chỉnh sửa được, hãy yêu cầu tường minh:

```java
List<String> editable = Stream.of("a", "bb")
        .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
editable.add("ccc"); // Hợp lệ.
```

Đoạn này giả định `java.util.List`, `java.util.ArrayList` và `java.util.stream.Stream` đã được import. Dù kết quả cuối cùng là `List`, `Set`, `Map` hay một giá trị tổng hợp, chúng là **kết quả của phép tính**, không chứng minh Stream là collection. Không dùng Stream như bộ nhớ cache hay đối tượng sở hữu lâu dài danh sách.

## 8. Quan hệ với nguồn và những giới hạn phải tôn trọng

### Stream không tự tạo bản sao dữ liệu nguồn

Nếu gọi `list.stream()` trên `ArrayList`, Stream có thể giữ tham chiếu đến cơ chế duyệt nguồn. Không nên mặc định Stream chụp bản sao tất cả phần tử tại thời điểm gọi `stream()`.

Một đặc tính quan trọng của Stream là **non-interference**: trong lúc pipeline đang đánh giá, thông thường không được thay đổi nguồn dữ liệu không được thiết kế cho sửa đổi đồng thời. Ví dụ sửa `ArrayList` từ lambda `map`/`forEach` khi đang duyệt chính danh sách đó có thể dẫn đến kết quả khó đoán hoặc `ConcurrentModificationException` và không được coi là phương án sửa danh sách an toàn.

Phân biệt hai tình huống:

- Trong demo, `source.add("Bao")` được gọi **sau khi** pipeline kết thúc, nên không ảnh hưởng danh sách kết quả đã tạo.
- Việc thay đổi nguồn **trong khi** pipeline đang xử lý là vấn đề khác, cần tránh hoặc dùng cấu trúc/thiết kế đồng bộ được phép.

Với những nguồn có khả năng sửa đồng thời hoặc cơ chế late binding, các quy tắc quan sát dữ liệu cụ thể phụ thuộc nguồn; không suy diễn rằng mọi Stream sẽ nhìn thấy dữ liệu mới cùng cách. Khi cần snapshot ổn định, hãy tạo bản sao tại thời điểm phù hợp (ví dụ `List.copyOf(original)` khi phần tử và điều kiện null cho phép), rồi xử lý bản sao đó.

### Không nhất thiết có thứ tự

Stream có thể có hoặc không có *encounter order*, tùy nguồn và thao tác. `List.stream()` thường mang thứ tự theo List; `HashSet.stream()` không cam kết thứ tự. Các thao tác như `unordered()` có thể bỏ ràng buộc thứ tự nếu phù hợp. Với parallel Stream, `forEach` không bảo đảm thứ tự xuất hiện, còn `forEachOrdered` giữ thứ tự gặp phần tử khi nguồn có thứ tự (với chi phí phối hợp).

`parallel()` không biến Stream thành lưu trữ song song; nó chỉ yêu cầu pipeline có thể được thực thi song song. Tránh state mutable chia sẻ trong lambda. Hiệu quả thực tế phụ thuộc kích thước dữ liệu, loại thao tác, source splitting, chi phí đồng bộ và tác dụng phụ.

### Nguồn có tài nguyên cần đóng

Đối với Stream lấy từ `Files.lines(path)`, cần đóng Stream để giải phóng tài nguyên tệp. Ví dụ minh họa bên trong phương thức khai báo `throws IOException`:

```java
try (Stream<String> lines =
             java.nio.file.Files.lines(path)) {
    long nonBlankLines = lines
            .filter(s -> !s.isBlank())
            .count();
    System.out.println(nonBlankLines);
}
```

Ở đây `path` là biến `java.nio.file.Path` và cần import `Stream` hoặc dùng tên đầy đủ. Đây **không phải** chương trình nguồn độc lập. `try-with-resources` gọi `close()` sau khi hoàn thành hoặc có lỗi. Terminal operation tự nó không đồng nghĩa với việc đóng mọi tài nguyên. Các Stream từ collection thông thường không cần đóng thủ công vì chúng không giữ resource bên ngoài như file handle.

## 9. Những lỗi tư duy và lập trình thường gặp

**1. Gọi `stream()` rồi tưởng đã tạo bản sao.**

```java
Stream<String> view = names.stream();
```

Đây là khai báo pipeline xử lý; không có `List` kết quả. Muốn sao chép/thu thập cần terminal như `toList()` hoặc một collector thích hợp. Lưu ý tính chỉnh sửa của danh sách được tạo.

**2. Tưởng `filter` xóa phần tử khỏi collection.**

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));
List<Integer> even = source.stream()
        .filter(n -> n % 2 == 0)
        .toList();
// even = [2, 4]; source vẫn là [1, 2, 3, 4].
```

`filter` chỉ quyết định phần tử nào đi tiếp trong pipeline, không gọi `source.remove(...)`.

**3. Gọi terminal hai lần trên một Stream.**

```java
Stream<String> s = Stream.of("a", "b");
s.count();
s.findFirst(); // Không hợp lệ: Stream đã được tiêu thụ.
```

Muốn hai kết quả, tạo hai Stream từ nguồn có thể duyệt lại hoặc dùng một phép tổng hợp phù hợp.

**4. Phụ thuộc vào side effect của `peek`/`map`.**

```java
long count = List.of(1, 2, 3).stream()
        .map(n -> {
            System.out.println(n);
            return n * 2;
        })
        .count();
```

Không nên mong chắc chắn `println` chạy ba lần: có thể tồn tại tối ưu hóa `count` mà không cần áp dụng `map` trên từng phần tử. Dùng terminal thích hợp nếu mục đích là tác dụng phụ, và tránh yêu cầu tác dụng phụ để quyết định tính đúng đắn.

**5. Cho rằng Stream luôn tiết kiệm RAM.** `sorted()` có thể phải gom nhiều phần tử trước khi phát đầu ra; việc gọi `toList()` rõ ràng xây dựng một danh sách kết quả trong bộ nhớ. Đối với tệp khổng lồ, `Files.lines` có thể đọc theo luồng, nhưng kết thúc bằng `toList()` vẫn có thể ngốn bộ nhớ rất lớn.

**6. Dùng Stream vô hạn với terminal không giới hạn.** `Stream.iterate(...)` hoặc `Stream.generate(...)` có thể không kết thúc. Dùng `limit`, predicate kết thúc hoặc các phương án dừng phù hợp khi cần. Với nguồn vô hạn và thao tác stateful như `sorted`, cần xem xét cả khả năng hoàn thành lẫn bộ nhớ.

**7. Quên đóng Stream dùng I/O.** `Files.lines` có tài nguyên hệ điều hành; dùng `try-with-resources`. Stream thông thường từ `List` không cần close.

**8. Gắn hành vi của mọi nguồn vào `List`.** Stream từ `HashSet` không có cam kết thứ tự như `List`; nguồn có thể thay đổi, có thể dùng một lần, hoặc sinh phần tử theo yêu cầu. Cần đọc hợp đồng của nguồn cụ thể.

**9. Lẫn lộn `Stream<T>` và `IntStream`.** `Stream<Integer>` chứa các giá trị kiểu tham chiếu `Integer`; `IntStream` là dòng chuyên biệt cho `int`, cung cấp `sum`, `average` và tránh boxing không cần thiết ở nhiều phép toán. `boxed()` chuyển `IntStream` thành `Stream<Integer>` khi cần API chung.

## 10. Quy trình lựa chọn Stream hay Collection

Hãy chọn **collection** khi cần:

- Giữ phần tử để tra cứu, truy cập lại nhiều lần hoặc thêm/xóa theo hợp đồng.
- Lưu trạng thái lâu dài của dữ liệu trong bộ nhớ.
- Sử dụng API cấu trúc như `List.get(index)` hoặc `Map.get(key)`.

Hãy chọn **Stream** khi cần:

- Diễn đạt một lần xử lý: lọc, biến đổi, nhóm, tổng hợp hoặc tìm kiếm.
- Kết hợp nhiều bước mà không tự tạo List trung gian sau từng bước.
- Xử lý một phần nguồn hoặc tạo phần tử theo nhu cầu khi thao tác cho phép dừng sớm.
- Sử dụng pipeline rõ ràng với các hàm stateless, ít tác dụng phụ.

Hai hướng không đối lập: một collection có thể là nguồn Stream; Stream có thể trả về collection kết quả. Tùy việc cần kiểm soát lỗi, break/continue, I/O và cập nhật trạng thái phức tạp, vòng lặp `for` truyền thống đôi khi minh bạch hơn Stream.

## 11. Bài tập tự kiểm tra

1. Với `List.of(1, 2, 3, 4, 5)`, dùng Stream tạo List các bình phương của số lẻ. Giải thích liệu danh sách ban đầu có thay đổi hay không.
2. Tạo `Stream<String>` rồi chỉ gọi `map(String::toUpperCase)`. Khi nào lambda thực sự có thể được thực thi? Bổ sung terminal `toList()`.
3. Vì sao đoạn `Stream.of(1, 2, 3).count()` không biến Stream thành cấu trúc lưu trữ? Kết quả kiểu gì?
4. Viết `Supplier<Stream<Integer>>` tạo Stream chẵn từ một `List<Integer>` và gọi hai lần để lấy tổng và số lượng, mỗi lần tạo một Stream mới.
5. Dùng `Stream.iterate(1, n -> n + 1).filter(n -> n % 2 == 0).limit(3).toList()` dự đoán kết quả và giải thích vì sao phép toán kết thúc dù nguồn không hữu hạn.
6. Đọc file bằng `Files.lines`, đếm số dòng khác rỗng và bảo đảm đóng tài nguyên bằng `try-with-resources`.

**Gợi ý:** (1) `source.stream().filter(n -> n % 2 != 0).map(n -> n * n).toList()` cho `[1, 9, 25]`, `source` không đổi. (2) Các thao tác trung gian thường lười và chạy khi terminal đòi phần tử. (3) `count()` trả `long` và Stream dùng xong. (4) `() -> source.stream().filter(n -> n % 2 == 0)` tạo pipeline mới cho mỗi `get()`. (5) `[2, 4, 6]` nhờ `limit(3)` giới hạn số phần tử đầu ra. (6) Đặt `Files.lines(path)` ở đầu `try` và terminal `count()` bên trong.

Điểm cốt lõi: **Collection giữ dữ liệu; Stream mô tả việc xử lý dữ liệu từ một nguồn**. Các thao tác trung gian thường lười, terminal kích hoạt tính toán, cùng Stream instance chỉ dùng một lần, và collection nguồn không tự bị biến đổi bởi `filter`/`map`. Nắm rõ sự phân biệt này giúp chọn đúng API, tránh sử dụng lại Stream, tránh giả định sai về bộ nhớ và kiểm soát vòng đời của các nguồn dữ liệu.
