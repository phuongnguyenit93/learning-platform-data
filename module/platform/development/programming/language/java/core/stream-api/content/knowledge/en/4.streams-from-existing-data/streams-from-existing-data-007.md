# Nối nguồn bằng Stream.concat và quản lý chuỗi nối

Trong Java Stream API, dữ liệu thường nằm rải rác ở nhiều nguồn: danh sách đơn hàng mới và cũ, kết quả tra cứu chính và dự phòng, các đoạn log theo ngày hoặc hai tập bản ghi cần đưa qua cùng một pipeline. `Stream.concat` cho phép tạo **một Stream hợp nhất từ hai Stream có sẵn**, để tiếp tục dùng `filter`, `map`, `reduce`, `collect` và các thao tác khác theo phong cách khai báo.

Bài học thuộc chương **Tạo Stream từ dữ liệu có sẵn** của module `JAVA_STREAM_API`. Mục tiêu là hiểu thứ tự phần tử khi nối, tính *lazy*, vòng đời sử dụng một lần, cách đóng các nguồn giữ tài nguyên, đồng thời biết khi nào nên chuyển từ `Stream.concat` sang cách tổ chức nhiều nguồn bằng `flatMap`. Các quyết định này ảnh hưởng trực tiếp đến tính đúng đắn, bộ nhớ và hiệu năng, đặc biệt khi xử lý I/O hoặc chạy song song.

## 1. Stream.concat nối hai nguồn như thế nào?

Chữ ký của phương thức tĩnh trong `java.util.stream.Stream`:

```java
public static <T> Stream<T> concat(
        Stream<? extends T> a,
        Stream<? extends T> b
);
```

`Stream.concat(a, b)` tạo một Stream mới, gồm các phần tử của `a` theo sau bởi các phần tử của `b`. Nếu **cả hai Stream có thứ tự gặp phần tử** (*encounter order*), Stream kết quả giữ thứ tự của từng nguồn và đặt toàn bộ phần tử của `a` trước `b`.

```text
Nguồn A: [A1, A2, A3] ─┐
                        ├─ Stream.concat(A, B) → [A1, A2, A3, B1, B2]
Nguồn B: [B1, B2] ──────┘
```

Ví dụ cơ bản, dùng được từ Java 8:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> current = Arrays.asList("An", "Binh");
List<String> archived = Arrays.asList("Chi", "Dung");

List<String> all = Stream.concat(
        current.stream(),
        archived.stream()
).collect(Collectors.toList());

System.out.println(all); // [An, Binh, Chi, Dung]
```

Các điểm cần ghi nhớ:

- `concat` nhận **hai Stream**, không nhận trực tiếp hai `List`. Với collection, gọi `stream()` trước.
- `concat` tạo **pipeline mới**, không sao chép toàn bộ hai nguồn thành collection ở thời điểm gọi. Các phần tử được xử lý khi có thao tác kết thúc.
- Nối không tự loại bản ghi trùng lặp, không tự sắp xếp lại và không trộn xen kẽ hai nguồn.
- Mỗi đối số là một Stream có thể tiêu thụ **một lần**. Sau khi dùng chúng trong pipeline nối, không được tiếp tục sử dụng độc lập hai Stream nguồn.
- Nếu một nguồn rỗng, kết quả mang các phần tử của nguồn còn lại. Cả hai nguồn phải khác `null`; truyền `null` gây `NullPointerException`.

Khác biệt với `Stream.of` đặc biệt dễ nhầm:

```java
Stream<String> a = Stream.of("x", "y");
Stream<String> b = Stream.of("z");

Stream<Stream<String>> nested = Stream.of(a, b); // 2 phần tử, mỗi phần tử là Stream
// Chỉ đóng gói tham chiếu; a và b chưa bị tiêu thụ ở thời điểm này.
```

`Stream.of(a, b)` tạo Stream **chứa hai đối tượng Stream**. `Stream.concat(a, b)` tạo Stream **chứa phần tử bên trong** hai Stream đó. Nếu muốn ghép nhiều nguồn, `flatMap` có thể làm phẳng Stream lồng nhau, nhưng cần cân nhắc tài nguyên và số lượng nguồn ở các phần sau.

## 2. Nối pipeline là lazy, nhưng việc tạo nguồn có thể không lazy

Hãy tách biệt hai thời điểm:

1. **Tạo nguồn và xây dựng pipeline:** Java đánh giá biểu thức đối số để lấy hai Stream rồi tạo Stream nối.
2. **Duyệt các phần tử:** Thường chỉ xảy ra khi gọi thao tác kết thúc như `count`, `toArray`, `findFirst` hoặc `collect`.

```java
import java.util.stream.Stream;

Stream<String> left = Stream.of("cat", "dog")
        .peek(s -> System.out.println("A: " + s));
Stream<String> right = Stream.of("bird")
        .peek(s -> System.out.println("B: " + s));

Stream<String> merged = Stream.concat(left, right);
System.out.println("Đã tạo pipeline");

merged.forEachOrdered(System.out::println);
```

Ở pipeline tuần tự, phần in từ `peek` và các phần tử bắt đầu xuất hiện khi chạy `forEachOrdered`, sau thông báo `Đã tạo pipeline`. `peek` chỉ minh họa hoạt động; không nên dựa vào nó để ghi log hoặc dọn dẹp có tính bắt buộc vì một số thao tác kết thúc có thể được tối ưu hóa và bỏ qua việc duyệt phần tử.

Đặc biệt, **lazy trong duyệt không có nghĩa lazy trong mở tài nguyên**:

```java
// Hai lời gọi Files.lines(...) được đánh giá khi tạo joined,
// dù chưa có thao tác kết thúc nào trên joined.
Stream<String> joined = Stream.concat(
        Files.lines(firstPath),
        Files.lines(secondPath)
);
```

Đoạn này minh họa thời điểm mở nguồn, **chưa phải mẫu quản lý tài nguyên an toàn**. Nếu mở tệp thứ hai thất bại, tệp đầu tiên có thể vẫn mở; nếu xử lý thành công mà không đóng, cả hai cũng có thể còn giữ tài nguyên. Phần 4 trình bày cách viết an toàn.

### Nối với thao tác ngắn mạch

```java
import java.util.stream.Stream;

Stream<String> joined = Stream.concat(
        Stream.of("A1", "A2", "A3"),
        Stream.of("B1", "B2")
);

joined.limit(2).forEachOrdered(System.out::println);
// A1
// A2
```

Với hai nguồn có thứ tự và pipeline tuần tự như trên, `limit(2)` không cần lấy phần tử từ nguồn B. Tương tự, `findFirst()` thường lấy từ A khi A có phần tử. Nhưng nếu thêm các thao tác cần quan sát toàn bộ dữ liệu, như `sorted()`, chi phí thực thi có thể tăng; còn với pipeline không có encounter order hoặc khi chạy song song, không nên suy diễn thứ tự xử lý nội bộ.

**Hệ quả quan trọng:** dù phép ngắn mạch chưa đọc phần tử nào từ B, nếu B đã mở tệp hoặc giữ kết nối thì B vẫn phải được đóng.

## 3. Thứ tự, trùng lặp, kiểu dữ liệu và chế độ song song

| Thuộc tính | Hành vi khi nối | Ý nghĩa thực hành |
| --- | --- | --- |
| Encounter order | Có thứ tự nếu **cả A và B** có thứ tự | Dữ liệu A đứng trước B trong thứ tự gặp phần tử |
| Phần tử trùng lặp | Được giữ nguyên | Dùng `distinct()` nếu thực sự cần loại trùng |
| Sắp xếp | Không tự tạo một thứ tự sắp xếp toàn cục | Hai nguồn đã sắp xếp riêng chưa chắc kết quả đã sắp xếp |
| Lazy | Tiếp tục là pipeline lazy | Không có bản sao toàn bộ dữ liệu khi gọi `concat` |
| Tái sử dụng nguồn | Không được tái sử dụng A/B hoặc Stream kết quả | Tạo Stream mới cho lần xử lý tiếp theo |
| Song song | Kết quả là parallel nếu **ít nhất một** nguồn parallel | Cần cân nhắc thứ tự và chi phí phối hợp |
| Nguyên thủy | Có `IntStream.concat`, `LongStream.concat`, `DoubleStream.concat` | Tránh boxing không cần thiết |

### Ưu tiên dữ liệu nguồn trước và loại trùng

Giả sử ưu tiên mã từ nguồn chính, sau đó mới bổ sung những mã chưa có từ nguồn phụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> primary = Arrays.asList("u01", "u02", "u02");
List<String> fallback = Arrays.asList("u02", "u03");

List<String> ids = Stream.concat(
        primary.stream(),
        fallback.stream()
).distinct().collect(Collectors.toList());

System.out.println(ids); // [u01, u02, u03]
```

Với pipeline có encounter order, `distinct()` giữ **lần xuất hiện đầu tiên**, nên thứ tự ưu tiên nguồn chính được bảo toàn. Tuy vậy, `distinct()` xác định trùng lặp qua `equals`/`hashCode`, có thể tiêu tốn bộ nhớ cho tập phần tử đã thấy; với bản ghi đối tượng, cần quyết định rõ hai bản ghi có trùng nhau theo ID hay theo toàn bộ đối tượng.

### Hai nguồn đều được sắp xếp vẫn có thể cần sorted()

```java
Stream<Integer> a = Stream.of(1, 4, 7);
Stream<Integer> b = Stream.of(2, 3, 8);

Stream.concat(a, b).forEachOrdered(System.out::println);
// 1, 4, 7, 2, 3, 8  (không phải thứ tự tăng dần toàn cục)
```

Nếu cần toàn cục tăng dần, dùng `Stream.concat(a, b).sorted()` với **những Stream mới**. `sorted()` có thể cần giữ nhiều phần tử trong bộ nhớ trước khi xuất kết quả; với hai nguồn lớn đã được sắp xếp, bài toán *merge sorted streams* cần thuật toán riêng thay vì chỉ nối rồi sắp xếp.

### Nối các Stream số nguyên thủy

```java
import java.util.stream.IntStream;

int sum = IntStream.concat(
        IntStream.rangeClosed(1, 3),
        IntStream.of(10, 20)
).sum();

System.out.println(sum); // 36
```

`Stream.concat` làm việc với Stream đối tượng. Khi nguồn là `IntStream`, `LongStream` hoặc `DoubleStream`, hãy dùng phương thức `concat` tương ứng để có pipeline xử lý số nguyên thủy hiệu quả hơn, tránh boxing chỉ để nối.

### Lưu ý khi chạy song song

```java
Stream<Integer> merged = Stream.concat(
        Stream.of(1, 2).parallel(),
        Stream.of(3, 4)
);

System.out.println(merged.isParallel()); // true
merged.forEachOrdered(System.out::println); // 1, 2, 3, 4
```

`forEachOrdered` bảo đảm thứ tự gặp phần tử khi thứ tự đó tồn tại; `forEach` trên pipeline parallel không bảo đảm thứ tự in. Việc nối không tự bảo đảm tăng tốc: đặc điểm tách công việc từ hai nguồn và ràng buộc thứ tự có thể ảnh hưởng hiệu năng. Chỉ dùng parallel khi phép xử lý độc lập, không phụ thuộc trạng thái chia sẻ, và có lý do hiệu năng rõ ràng.

## 4. Vòng đời và đóng chuỗi nối đúng cách

`Stream.concat` kết nối **hai Stream nguồn vào cùng một pipeline sử dụng một lần**. Terminal operation như `count()` hoặc `collect()` làm pipeline được tiêu thụ nhưng **không tự gọi `close()`**. Điều này đặc biệt quan trọng với Stream trả về từ `Files.lines`, `Files.list` hoặc các nguồn I/O.

### Đóng Stream nối sẽ đóng cả hai nguồn

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> events = new ArrayList<>();

Stream<String> a = Stream.of("A")
        .onClose(() -> events.add("close A"));
Stream<String> b = Stream.of("B")
        .onClose(() -> events.add("close B"));

Stream<String> joined = Stream.concat(a, b);
long count = joined.count();

System.out.println(count);  // 2
System.out.println(events); // []: count() không tự đóng nguồn

joined.close();
System.out.println(events); // [close A, close B]
```

Theo hợp đồng, khi đóng Stream kết quả từ `Stream.concat`, các hành động đóng của A và B được thực hiện. Hành động đăng ký bằng `onClose` chạy khi đóng, kể cả khi không duyệt hết nguồn. Nếu handler đóng ném ngoại lệ, Java vẫn cố chạy các handler còn lại và có thể lưu ngoại lệ bổ sung dưới dạng *suppressed exceptions*.

Nếu một Stream nguồn được sử dụng ở nhiều chỗ độc lập, việc ghép và đóng chung có thể làm các chỗ khác không dùng được nữa. Không dùng lại cùng một nguồn theo kiểu `Stream.concat(s, s)` hoặc dùng `a`/`b` sau khi đã gắn vào pipeline nối.

### Nối hai tệp: mở và đóng trong cùng phạm vi

Đây là mẫu nên dùng khi cần nối các dòng log của hôm qua với hôm nay rồi đếm cảnh báo:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countWarnings(Path yesterday, Path today)
        throws IOException {
    try (Stream<String> oldLines =
                 Files.lines(yesterday, StandardCharsets.UTF_8);
         Stream<String> newLines =
                 Files.lines(today, StandardCharsets.UTF_8);
         Stream<String> joined =
                 Stream.concat(oldLines, newLines)) {

        return joined
                .filter(line -> line.contains("WARN"))
                .count();
    }
}
```

Khối `try-with-resources` giải quyết đồng thời các tình huống:

1. Cả hai nguồn được mở thành công: xử lý xong thì đóng `joined`, và theo đó đóng hai nguồn.
2. Mở nguồn thứ hai thất bại: Java đóng `oldLines` đã mở trước đó, không để tệp đầu bị bỏ quên.
3. Pipeline ném ngoại lệ trong khi đọc hoặc xử lý: Java vẫn thực hiện đóng tài nguyên khi rời khối.
4. Đóng `joined` đóng các nguồn, rồi khối `try` có thể gọi `close()` lần nữa trên từng Stream đã khai báo. Đóng một Stream đã đóng là thao tác không gây hiệu lực bổ sung.

Ví dụ trên trả **kết quả đã tính** (`long`), nên người gọi không phải giữ tài nguyên I/O. Khi cần trả Stream cho người gọi tự xử lý, phải thiết kế hợp đồng sở hữu rõ ràng: ai mở, ai gọi `close()`, và khi nào được tiêu thụ. Không trả Stream tạo trong `try-with-resources` mà khối `try` đã kết thúc trước khi người gọi dùng nó.

Một lưu ý về lỗi: `Files.lines(...)` có thể ném `IOException` khi mở; lỗi đọc phát sinh trong lúc duyệt lazy có thể được bọc thành `UncheckedIOException`. Cơ chế đóng trong `try-with-resources` vẫn áp dụng cho cả hai tình huống.

### Trường hợp có thao tác ngắn mạch

```java
public static boolean containsError(Path first, Path second)
        throws IOException {
    try (Stream<String> a = Files.lines(first);
         Stream<String> b = Files.lines(second);
         Stream<String> joined = Stream.concat(a, b)) {
        return joined.anyMatch(line -> line.contains("ERROR"));
    }
}
```

Khi tìm thấy `ERROR` ở nguồn đầu, `anyMatch` có thể dừng mà chưa đọc nguồn thứ hai. Dù vậy, **cả hai Stream đã mở vẫn được đóng**. Đây là lý do phải gắn vòng đời tài nguyên với phạm vi `try` thay vì dựa vào việc terminal operation có đọc hết phần tử hay không.

## 5. Nối nhiều hơn hai nguồn

`Stream.concat` chỉ nhận **hai đối số**. Có thể lồng lời gọi để nối ba nguồn:

```java
Stream<String> three = Stream.concat(
        Stream.concat(
                Stream.of("A1", "A2"),
                Stream.of("B1")
        ),
        Stream.of("C1", "C2")
);
```

Với số lượng nguồn nhỏ và cố định, cách này rõ ràng. Nhưng **không nên xây chuỗi nối lồng nhau quá sâu** trong vòng lặp với hàng trăm hoặc hàng nghìn nguồn. Tài liệu Java cảnh báo truy cập phần tử của Stream được nối lặp nhiều tầng có thể tạo chuỗi lời gọi rất sâu, thậm chí `StackOverflowError`.

### Nhiều collection: dùng flatMap để làm phẳng

```java
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

List<List<String>> batches = Arrays.asList(
        Arrays.asList("a1", "a2"),
        Arrays.asList("b1"),
        Arrays.asList("c1", "c2")
);

List<String> all = batches.stream()
        .flatMap(Collection::stream)
        .collect(Collectors.toList());

System.out.println(all); // [a1, a2, b1, c1, c2]
```

`batches.stream()` tạo Stream các collection; `flatMap(Collection::stream)` biến mỗi collection thành Stream phần tử rồi làm phẳng chúng theo thứ tự gặp phần tử. Đây là phương án tự nhiên khi có **danh sách nguồn có độ dài thay đổi** và nguồn là collection không giữ tài nguyên phải đóng.

Có thể viết `Stream.of(s1, s2, s3).flatMap(Function.identity())` khi mỗi `s1`/`s2`/`s3` đã là Stream. `flatMap` sẽ đóng các Stream con mà nó đã xử lý, nhưng nếu những Stream con đó đã được mở từ tệp từ trước và một phép ngắn mạch bỏ qua một số nguồn, các Stream chưa được đưa vào xử lý vẫn có thể còn mở. Vì vậy **không nên tạo trước hàng loạt Stream giữ tài nguyên rồi đưa vào `flatMap`**.

### Nhiều tệp: mở nguồn khi thực sự đến lượt xử lý

Khi số lượng tệp thay đổi, có thể duyệt danh sách đường dẫn và mở từng Stream con trong `flatMap`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public static long countErrors(List<Path> files) {
    try (Stream<String> lines = files.stream().flatMap(path -> {
        try {
            return Files.lines(path, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException(
                    "Không mở được tệp: " + path, ex
            );
        }
    })) {
        return lines
                .filter(line -> line.contains("ERROR"))
                .count();
    }
}
```

Với cách này, `Files.lines` được gọi **khi mapper của `flatMap` cần đến đường dẫn tương ứng**, thay vì mở toàn bộ tệp ngay lúc xây dựng pipeline. `flatMap` có trách nhiệm đóng Stream con mà mapper trả về sau khi xử lý nó. `try-with-resources` vẫn đóng pipeline ngoài khi kết thúc, kể cả khi có ngoại lệ.

Chú ý hai điểm:

- Vì `Files.lines` khai báo `IOException` trong khi mapper của `flatMap` không khai báo checked exception, ví dụ bọc lỗi mở tệp thành `UncheckedIOException`. Phần xử lý gọi phương thức cần tính đến dạng ngoại lệ này.
- Mở lười giảm số tệp đang mở cùng lúc trong pipeline tuần tự, nhưng **không biến việc đọc tệp thành một giao dịch toàn vẹn**. Nếu một tệp lỗi giữa chừng, dữ liệu từ các tệp trước có thể đã được xử lý; nếu ghi ra bên ngoài ngay trong pipeline, không có cơ chế rollback tự động.

Đối với xử lý parallel, nhiều nguồn I/O và nguồn có tài nguyên, cần đánh giá cẩn thận thứ tự mở/đóng và khả năng mở đồng thời trước khi cho pipeline chạy song song.

## 6. Thiết kế hàm cung cấp nguồn nối

Một API tốt cần làm rõ nó trả về **kết quả đã tính** hay **một Stream còn sống**:

| Kiểu API | Vòng đời và trách nhiệm | Thích hợp khi |
| --- | --- | --- |
| `List<T> combine(List<T>, List<T>)` | Tạo Stream ngắn hạn, trả kết quả đã thu thập | Kích thước dữ liệu phù hợp bộ nhớ |
| `Stream<T> concatViews(Collection<T>, Collection<T>)` | Trả pipeline mới; nguồn collection thường không cần đóng | Muốn caller tiếp tục lọc/ánh xạ |
| `long analyzeFiles(Path, Path)` | Mở, xử lý, đóng tệp trong phương thức | Muốn giữ trách nhiệm tài nguyên một chỗ |
| `Stream<String> openJoinedFiles(Path, Path)` | Caller phải đóng Stream trả về; phải xử lý lỗi khi mở nguồn thứ hai | Muốn cho caller tự chọn terminal operation |
| `Stream<T> fromSuppliers(...)` | Mỗi lần sử dụng phải tạo pipeline mới từ factory | Cần phân tích nguồn nhiều lần |

Ví dụ API trả Stream từ **hai collection có sẵn**, không mở tài nguyên bên ngoài:

```java
import java.util.Collection;
import java.util.stream.Stream;

public static <T> Stream<T> concatViews(
        Collection<? extends T> first,
        Collection<? extends T> second
) {
    return Stream.concat(first.stream(), second.stream());
}
```

Caller có thể chọn terminal operation:

```java
long count = concatViews(
        Arrays.asList("a", "bb"),
        Arrays.asList("ccc")
).filter(s -> s.length() > 1).count(); // 2
```

Vì `concatViews` tạo Stream mới trên mỗi lần gọi, caller có thể gọi lại phương thức để phân tích dữ liệu lần khác. Điều này khác hẳn với việc lưu một biến `Stream` dùng chung cho nhiều lời gọi.

Đối với API mở hai tệp và trả Stream, cần xử lý trường hợp mở nguồn thứ hai thất bại **trước khi** ghép. Một mẫu an toàn là:

```java
public static Stream<String> openJoinedFiles(Path first, Path second)
        throws IOException {
    Stream<String> a = Files.lines(first, StandardCharsets.UTF_8);
    try {
        Stream<String> b = Files.lines(second, StandardCharsets.UTF_8);
        return Stream.concat(a, b);
    } catch (IOException | RuntimeException ex) {
        a.close();
        throw ex;
    }
}

// Caller sở hữu Stream kết quả và phải đóng:
try (Stream<String> lines = openJoinedFiles(fileA, fileB)) {
    long total = lines.count();
}
```

Nếu mở nguồn B thất bại, phương thức đóng A trước khi trả lỗi. Khi cả hai đã mở, quyền đóng cả hai được chuyển qua Stream kết quả cho caller. Mẫu này minh họa hợp đồng sở hữu; với API sản xuất, còn cần cân nhắc cách giữ ngoại lệ gốc nếu `close` cũng ném lỗi, chính sách phát sinh lỗi I/O trong quá trình duyệt và tài liệu hướng dẫn sử dụng.

## 7. Lỗi phổ biến và cách lựa chọn

| Tình huống | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `Stream.concat(listA, listB)` | `concat` cần Stream, không nhận List | `listA.stream()` và `listB.stream()` |
| `Stream.of(streamA, streamB)` rồi tưởng đã nối phần tử | Tạo `Stream<Stream<T>>` | Dùng `concat` hoặc `flatMap` |
| Dùng lại `streamA` sau `Stream.concat(streamA, streamB)` | Vi phạm vòng đời sử dụng một lần | Tạo Stream mới |
| `Stream.concat(s, s)` | Hai nhánh cùng tham chiếu đến một Stream | Tạo hai Stream độc lập từ nguồn |
| Nối các nguồn đã sorted rồi cho rằng toàn bộ vẫn sorted | Nối không thực hiện merge có sắp xếp | Dùng thuật toán merge phù hợp hoặc `sorted()` toàn cục |
| Dùng `forEach` song song và kỳ vọng A luôn in trước B | `forEach` không bảo đảm thứ tự khi parallel | Dùng `forEachOrdered` nếu cần thứ tự |
| Gọi `count` trên Stream nối hai tệp nhưng không đóng | Terminal operation không tự đóng | `try-with-resources` |
| Tạo trước nhiều `Files.lines` rồi `flatMap`, sau đó `findFirst` | Nguồn chưa thăm tới có thể còn mở | Mở Stream trong mapper, hoặc quản lý tất cả nguồn tường minh |
| Lồng `concat` hàng nghìn tầng | Pipeline có thể rất sâu, nguy cơ `StackOverflowError` | Dùng `flatMap` với collection hoặc factory nguồn |
| Dùng `distinct`/`sorted` trên dữ liệu lớn mà bỏ qua bộ nhớ | Các thao tác trạng thái có thể tốn nhiều bộ nhớ | Đánh giá quy mô, đặc điểm nguồn và thuật toán thích hợp |

## 8. Bài tập thực hành ngắn

1. Có `A = [4, 1]` và `B = [3, 1]`. Dự đoán kết quả `Stream.concat(A.stream(), B.stream()).distinct().collect(toList())`. **Đáp án:** `[4, 1, 3]` khi A/B có encounter order.
2. Nối `IntStream.range(0, 3)` với `IntStream.of(10)` và tính tổng. **Đáp án:** `13`.
3. Một Stream nối từ hai `Files.lines` gọi `findFirst()` thành công. Đã giải phóng cả hai tệp chưa? **Chưa**; vẫn cần `close()` hoặc `try-with-resources`.
4. Vì sao không nên tạo trước 500 `Files.lines` rồi đưa vào `flatMap` để lấy phần tử đầu tiên? **Vì** nhiều tệp có thể đã mở dù phần lớn Stream con không được duyệt đến.
5. Vì sao `Stream.concat(sortedA, sortedB)` có thể không tăng dần? **Vì** nối đặt toàn bộ A trước B, không so sánh để trộn phần tử giữa hai nguồn.
6. Khi nào nên chọn `flatMap(Collection::stream)`? **Khi** có danh sách nhiều collection và muốn duyệt chúng trong một pipeline phẳng, tránh lồng `concat` quá sâu.

**Nguyên tắc thực hành:** Dùng `Stream.concat` cho hai nguồn hoặc một số ít nguồn cố định; giữ rõ thứ tự và vòng đời một lần. Khi nối nguồn I/O, quản lý việc mở và đóng ngay trong cấu trúc API hoặc chuyển trách nhiệm đóng cho caller một cách minh bạch. Khi số lượng nguồn tăng, ưu tiên tạo nguồn theo nhu cầu và làm phẳng bằng `flatMap` phù hợp với đặc điểm tài nguyên.
