# Một pipeline Stream chỉ được tiêu thụ một lần trong Java

## 1. Quy tắc cốt lõi của mô hình Stream

Một đối tượng `java.util.stream.Stream<T>` đại diện cho **một chuỗi thao tác xử lý dữ liệu** (*pipeline*), không phải bộ sưu tập có thể duyệt đi duyệt lại tùy ý. Theo hợp đồng Stream API, mỗi stream chỉ nên được thao tác qua pipeline của nó **một lần**; không được dùng lại cùng stream để thực hiện nhiều lần duyệt hoặc tạo các nhánh xử lý độc lập.

Một pipeline điển hình gồm:

```text
Nguồn (List, mảng, file, ...)
       |
       v
stream() -> filter(...) -> map(...) -> terminal operation
                         (count / toList / collect / forEach / ...)
```

- **Nguồn dữ liệu** có thể là collection, mảng, bộ sinh hoặc tài nguyên I/O.
- **Thao tác trung gian** (*intermediate operation*) như `filter`, `map`, `sorted` thường tạo một pipeline mới để mô tả việc xử lý; chúng thường **lazy** (chưa bắt đầu duyệt dữ liệu).
- **Thao tác kết thúc** (*terminal operation*) như `count`, `toList`, `collect`, `findFirst`, `anyMatch`, `forEach`, `reduce`, `sum` bắt đầu quá trình xử lý theo ngữ nghĩa của terminal operation đó. Pipeline được xem là **đã tiêu thụ** sau khi thực hiện terminal operation.
- Muốn thực hiện phép xử lý thứ hai trên cùng dữ liệu, hãy **tạo một stream mới từ nguồn**, hoặc lưu kết quả cần dùng nhiều lần vào collection phù hợp.

Ví dụ đúng:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);
long count = numbers.stream().filter(n -> n % 2 == 0).count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
```

Đây là các lệnh minh họa đặt trong phương thức có `import java.util.List;`. Hai lần gọi `numbers.stream()` tạo **hai đối tượng stream riêng biệt**. Không phải bạn đang duyệt lại cùng đối tượng `Stream`. `List` vẫn có thể được truy cập và dùng để tạo stream mới vì nó là nguồn, không bị tiêu thụ như pipeline.

## 2. Điều gì xảy ra khi gọi terminal operation lần hai?

Xét ví dụ minh họa:

```text
Stream<String> names = Stream.of("An", "Binh", "Chi");
long count = names.count(); // Terminal operation lần 1
long again = names.count(); // Sai: cố tiêu thụ cùng Stream lần 2
```

Đây là **phản ví dụ cố ý vi phạm hợp đồng Stream**, không dùng làm mẫu chương trình hợp lệ về hành vi. Trên nhiều triển khai Java, lần dùng thứ hai ném `IllegalStateException` với thông điệp dạng `stream has already been operated upon or closed`.

**Phân biệt hợp đồng API với biểu hiện lỗi:** tài liệu Java nói một triển khai *có thể* ném `IllegalStateException` nếu phát hiện stream bị dùng lại. Do một số phương thức trả chính đối tượng stream đang dùng, không phải mọi hành vi tái sử dụng sai đều chắc chắn được phát hiện bằng exception trong mọi triển khai. Vì vậy, **không được viết chương trình dựa vào việc lần tái sử dụng luôn trả lỗi cụ thể**. Dùng lại là sai theo hợp đồng ngay cả khi một thao tác tình cờ không báo lỗi.

Quy tắc không đổi với terminal operation trả về một giá trị đơn (`count`, `findFirst`, `anyMatch`) hay một collection (`toList`), và cũng không thay đổi khi terminal operation kết thúc sớm.

## 3. Intermediate operation không có nghĩa là stream nguồn dùng được tùy ý

Một thao tác trung gian như `filter` có thể nối một stage mới vào pipeline, nhưng điều này **không cho phép rẽ nhánh pipeline** từ cùng nguồn stream:

```text
Stream<Integer> source = Stream.of(1, 2, 3);
Stream<Integer> even = source.filter(x -> x % 2 == 0);
Stream<Integer> doubled = source.map(x -> x * 2); // Sai: tái sử dụng source
```

Đây là cách tổ chức **không hợp lệ theo hợp đồng Stream**: sau khi nối `filter`, đối tượng `source` đã tham gia vào pipeline đó. Không dùng nó như nguồn độc lập cho một nhánh khác. Một số triển khai ném `IllegalStateException` ngay ở lời gọi `source.map(...)` thứ hai.

Sửa bằng cách giữ lại **nguồn dữ liệu** thay vì chia sẻ cùng **đối tượng Stream**:

```java
List<Integer> numbers = List.of(1, 2, 3);
List<Integer> even = numbers.stream()
        .filter(x -> x % 2 == 0)
        .toList();
List<Integer> doubled = numbers.stream()
        .map(x -> x * 2)
        .toList();
```

Trong thân phương thức đã import `List`, kết quả là `even = [2]` và `doubled = [2, 4, 6]`. Hai pipeline độc lập đọc chung dữ liệu trong `numbers`, không chia sẻ vòng đời của cùng đối tượng Stream.

**Lưu ý:** `map`, `filter` không phải terminal operation và thường chưa đánh giá các phần tử tại thời điểm được gọi; tuy vậy việc *liên kết stage* có thể khiến stream upstream không còn là đối tượng thích hợp để gọi thêm một nhánh khác. “Lazy” không đồng nghĩa “có thể tùy ý dùng lại”.

## 4. Chương trình Java 17 đầy đủ: sáu tình huống quan trọng

Lưu toàn bộ mã dưới đây vào `StreamOneShotDemo.java`:

```java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class StreamOneShotDemo {
    public static void main(String[] args) {
        Stream<String> words = Stream.of("java", "go", "kotlin")
                .map(String::toUpperCase);
        System.out.println("firstCount=" + words.count());
        try {
            words.findFirst();
        } catch (IllegalStateException ex) {
            System.out.println("reuse=" + ex.getClass().getSimpleName());
        }

        List<Integer> data = List.of(1, 2, 3, 4);
        System.out.println("evens=" +
                data.stream().filter(n -> n % 2 == 0).toList());
        System.out.println("sum=" +
                data.stream().mapToInt(Integer::intValue).sum());

        Supplier<Stream<String>> fresh = () ->
                Stream.of("java", "go", "kotlin")
                        .filter(s -> s.length() > 2);
        System.out.println("freshCount=" + fresh.get().count());
        System.out.println("freshList=" +
                fresh.get().map(String::toUpperCase).toList());

        Stream<Integer> root = Stream.of(1, 2, 3);
        Stream<Integer> branch = root.filter(n -> n > 1);
        try {
            root.map(n -> n * 2).count();
        } catch (IllegalStateException ex) {
            System.out.println("branch=" + ex.getClass().getSimpleName());
        }
        System.out.println("branchResult=" + branch.toList());

        Stream<Integer> iteratorStream = Stream.of(7, 8);
        var iterator = iteratorStream.iterator();
        System.out.println("iteratorFirst=" + iterator.next());
        try {
            iteratorStream.count();
        } catch (IllegalStateException ex) {
            System.out.println("iteratorReuse=" + ex.getClass().getSimpleName());
        }

        Stream<Integer> closed = Stream.of(4, 5)
                .onClose(() -> System.out.println("closeHandler=ran"));
        closed.close();
        try {
            closed.count();
        } catch (IllegalStateException ex) {
            System.out.println("closedReuse=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 StreamOneShotDemo.java
java StreamOneShotDemo
```

Đầu ra đã kiểm chứng bằng Java 17:

```text
firstCount=3
reuse=IllegalStateException
evens=[2, 4]
sum=10
freshCount=2
freshList=[JAVA, KOTLIN]
branch=IllegalStateException
branchResult=[2, 3]
iteratorFirst=7
iteratorReuse=IllegalStateException
closeHandler=ran
closedReuse=IllegalStateException
```

Đọc từng tình huống:

1. **Terminal operation đầu tiên:** `words.count()` cho `3` và tiêu thụ pipeline `words`. Lần gọi `words.findFirst()` kế tiếp được bắt trong `catch`; triển khai Java 17 của bài thử phát hiện tái sử dụng và ném `IllegalStateException`.
2. **Tạo stream mới từ List:** hai biểu thức `data.stream()` là hai pipeline mới; `toList()` cho `[2, 4]`, còn `mapToInt(...).sum()` cho `10`.
3. **Factory bằng Supplier:** mỗi `fresh.get()` tạo stream riêng từ `Stream.of(...)`; vì thế một lần có thể `count()`, lần kế tiếp `map(...).toList()`.
4. **Rẽ nhánh:** `root.filter(...)` tạo `branch`. Cố dùng lại `root.map(...)` bị từ chối; `branch` ban đầu vẫn được dùng một lần để `toList()`. Đừng dựa vào việc nhánh cũ luôn còn chạy được sau một lần sử dụng sai trong mọi triển khai; hãy tránh kiểu mã rẽ nhánh đó.
5. **Lấy Iterator:** `iteratorStream.iterator()` là một thao tác kết thúc (dù mới gọi `iterator.next()` một lần), vì vậy không thể dùng `iteratorStream.count()` sau đó.
6. **Đóng stream:** `closed.close()` thực hiện close handler đã đăng ký bằng `onClose`. Stream đã đóng không được sử dụng tiếp; Java 17 ném `IllegalStateException` khi chương trình thử `count()`.

Các exception trong chương trình này được **bắt có chủ đích để minh họa lỗi**, không có nghĩa nên cố ý tái sử dụng stream trong ứng dụng thực tế.

## 5. Phân biệt nguồn dữ liệu và đối tượng Stream

| Đối tượng / thao tác | Có thể lặp lại không? | Ghi chú |
| --- | --- | --- |
| `List<T>` đang còn khả dụng | Có thể đọc hoặc tạo nhiều stream mới | Dữ liệu thuộc List; từng stream mới có vòng đời riêng |
| `List.of(...).stream()` được gọi lần nữa | Có | Mỗi lời gọi trả stream mới |
| `Stream.of(...)` được gọi lần nữa | Có | Mỗi lời gọi tạo stream mới từ các đối số |
| Biến `Stream<T> stream` sau `count()` | **Không** | Pipeline đã được tiêu thụ |
| Cùng `Stream<T>` sau `findFirst()` | **Không** | Dù `findFirst` có thể chỉ đọc một phần tử |
| Cùng `Stream<T>` sau `anyMatch()` | **Không** | Short-circuit không cho phép dùng lại |
| Cùng `Stream<T>` sau `iterator()` | **Không** | `iterator()` là terminal operation |
| `List<T> result = stream.toList()` | Có thể đọc lại **List** kết quả | Không thể gọi lại `stream.toList()` trên cùng stream |
| `Stream<T>` sau `close()` | **Không** | Stream đã đóng |
| `Supplier<Stream<T>>` tạo stream mới mỗi lần | Có thể gọi factory nhiều lần | Đúng nếu supplier thực sự xây một stream mới và nguồn còn khả dụng |

Một stream **không giống Iterator có thể reset** và cũng không giống `Collection`. Một `Collection` có thể cung cấp iterator/stream mới mỗi lần gọi; một đối tượng `Stream` chỉ biểu diễn một pipeline xử lý.

Ngay cả khi gọi `stream.toList()` và lưu kết quả, bạn cũng chỉ được sử dụng nhiều lần **danh sách kết quả** — không được tái chạy pipeline cũ. `Stream.toList()` có từ Java 16 và trả danh sách **không thể chỉnh sửa**; muốn một danh sách thay đổi được, có thể tạo `new ArrayList<>(stream.toList())` khi stream còn chưa tiêu thụ.

## 6. Cách 1: tạo stream mới trực tiếp mỗi lần

Đối với nguồn Collection, thường không cần lưu stream vào biến:

```java
List<String> items = List.of("java", "go", "kotlin");

long longWords = items.stream()
        .filter(s -> s.length() > 2)
        .count();

List<String> upper = items.stream()
        .map(String::toUpperCase)
        .toList();
```

Đặt các lệnh trên trong phương thức đã import `java.util.List`. `longWords = 2`, còn `upper = [JAVA, GO, KOTLIN]`. Dòng `items.stream()` xuất hiện **hai lần**, do đó mỗi terminal operation có pipeline riêng.

Khi đầu vào có thể thay đổi trong lúc xử lý, cần xem xét tính nhất quán của nguồn: tạo stream mới không tự chụp ảnh dữ liệu tại thời điểm cũ, cũng không đảm bảo an toàn khi collection bị sửa đồng thời. Nếu cần nhiều lần xử lý trên dữ liệu cố định, có thể tạo snapshot bất biến phù hợp trước khi dùng.

## 7. Cách 2: dùng Supplier<Stream<T>> để cung cấp stream mới

Khi muốn truyền “cách tạo pipeline” cho nhiều nơi, thay vì truyền một đối tượng stream đã tạo sẵn, có thể truyền **factory**:

```java
Supplier<Stream<String>> factory = () ->
        Stream.of("java", "go", "kotlin")
                .filter(s -> s.length() > 2);

long count = factory.get().count();
List<String> upper = factory.get()
        .map(String::toUpperCase)
        .toList();
```

Đây là các lệnh minh họa trong phương thức đã import `java.util.function.Supplier`, `java.util.stream.Stream`, `java.util.List`. Đầu ra tương ứng `count = 2` và `upper = [JAVA, KOTLIN]`.

Cách **sai** là factory chỉ trả về cùng stream được lưu từ trước:

```text
Stream<String> original = Stream.of("A", "B");
Supplier<Stream<String>> broken = () -> original;
broken.get().count();
broken.get().count(); // Sai: hai lần get trả cùng đối tượng Stream
```

Đoạn trên là **phản ví dụ cố ý sai về tái sử dụng**, dù có thể biên dịch. Lần `get()` thứ hai không tạo stream mới. Từ khóa `Supplier` không mang phép màu “làm mới”; điều quan trọng là **biểu thức tạo stream phải được thực thi lại**.

Với nguồn file hoặc truy vấn cơ sở dữ liệu, supplier muốn tạo stream mới phải **mở tài nguyên/truy vấn mới phù hợp**, không thể tái đọc một cursor/reader đã bị tiêu thụ. Đồng thời cần định nghĩa rõ ai là người đóng tài nguyên được tạo ra.

## 8. Cách 3: materialize kết quả khi cần dùng nhiều lần

Nếu phần xử lý tốn kém và kết quả cần đọc đi đọc lại, bạn có thể **tiêu thụ stream một lần rồi lưu kết quả**:

```java
List<String> normalized = Stream.of("  Java ", " Kotlin  ")
        .map(String::strip)
        .toList();

long count = normalized.size();
String first = normalized.get(0);
long startsWithJ = normalized.stream()
        .filter(s -> s.startsWith("J"))
        .count();
```

Các lệnh minh họa cần import `List` và `Stream`. `normalized` là danh sách `[Java, Kotlin]`, `count = 2`, `first = "Java"`, `startsWithJ = 1`.

Đây **không phải chạy lại stream cũ**: stream nguồn được tiêu thụ khi gọi `toList()`. Về sau bạn thao tác trên danh sách đã lưu hoặc tạo **stream mới từ danh sách**.

Có đánh đổi: `toList()` lưu toàn bộ kết quả trong bộ nhớ. Nếu nguồn rất lớn hoặc vô hạn, materialize toàn bộ có thể tốn bộ nhớ, chạy mãi hoặc không phù hợp. Khi đó hãy thiết kế một lần duyệt, tính nhiều thống kê trong một terminal operation, hoặc dùng nguồn có khả năng mở lại.

## 9. Short-circuit vẫn tiêu thụ stream

Một số terminal operation có thể kết thúc trước khi duyệt hết nguồn: `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()`, `noneMatch()`. Chẳng hạn:

```java
Stream<Integer> numbers = Stream.of(2, 4, 6, 9);
boolean found = numbers.anyMatch(x -> x % 2 != 0);
```

Các lệnh trên thuộc thân phương thức có import `Stream`. `found` là `true` vì có phần tử lẻ `9`. Tuy nhiên, **dù terminal operation chỉ duyệt một phần nguồn trong tình huống khác, stream đó vẫn đã được tiêu thụ**.

Việc một terminal operation có duyệt **tất cả** phần tử hay không phụ thuộc vào ngữ nghĩa của operation, đặc điểm nguồn và việc tối ưu hóa. Ví dụ `count()` có thể tận dụng kích thước nguồn đã biết mà không phải chạy mọi stage như người lập trình kỳ vọng; không nên dùng `peek` hay tác dụng phụ trong `map` để đếm số lần hàm đã chạy.

**Một lần tiêu thụ** không đồng nghĩa **mỗi phần tử được đánh giá chính xác một lần** trong mọi tình huống. Điều được ràng buộc là **vòng đời pipeline**, không phải bảo đảm về số lần side effect.

## 10. iterator() và spliterator() cũng là terminal operation

Một hiểu nhầm phổ biến: “Nếu mới lấy iterator, chưa đọc hết phần tử, thì stream chắc vẫn có thể duyệt tiếp bằng `count()`”. Sai. `BaseStream.iterator()` và `BaseStream.spliterator()` được mô tả là **terminal operations**.

Ví dụ trong chương trình ở mục 4:

```java
Stream<Integer> stream = Stream.of(7, 8);
var iterator = stream.iterator();
System.out.println(iterator.next()); // 7
```

Sau `iterator()`, stream không thể dùng lại cho một terminal operation khác, dù `iterator` mới đọc phần tử `7`. Nếu muốn duyệt qua iterator, hãy tiếp tục dùng **iterator đó** theo quy tắc của nó, không quay lại gọi terminal method trên đối tượng `Stream`.

Điều này cũng áp dụng với `spliterator()`. Đừng nhầm terminal operation có trả về **cấu trúc hỗ trợ duyệt** với thao tác trung gian có thể được nối nhánh khác.

## 11. Đóng stream khác với tiêu thụ stream

Có hai khái niệm cần tách bạch:

1. **Tiêu thụ** stream thông qua terminal operation: không được tái sử dụng stream, nhưng không đồng nghĩa Java đã gọi `close()` trên tất cả tài nguyên.
2. **Đóng** stream bằng `close()`: kết thúc khả năng sử dụng stream và kích hoạt các close handler đã đăng ký qua `onClose()`.

Với nhiều stream tạo từ `List` hoặc mảng, thường không có tài nguyên hệ điều hành cần đóng. Nhưng `Files.lines(path)` tạo stream gắn với tài nguyên file; nó cần được **đóng** sau khi dùng. Terminal operation `count()` hay `toList()` **không tự động bảo đảm đóng stream file**.

Trong mục 4, stream `closed` có `onClose` handler. `closed.close()` làm handler chạy, và thử dùng `closed.count()` sau đó bị Java 17 từ chối. `close()` không có nghĩa “reset rồi duyệt từ đầu”.

Với stream nguồn từ file, socket hoặc tài nguyên cần giải phóng, dùng **try-with-resources**; đây là vấn đề quản lý tài nguyên bên cạnh quy tắc single-use.

## 12. Ví dụ file đầy đủ: đọc lại bằng cách mở stream mới

Chương trình sau tự tạo file tạm, mở và đóng hai stream khác nhau rồi xóa file tạm. Lưu vào `StreamFreshFileDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class StreamFreshFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("stream-one-shot-", ".txt");
        try {
            Files.writeString(file, "alpha\nbeta\n");
            try (Stream<String> lines = Files.lines(file)) {
                System.out.println("lineCount=" + lines.count());
            }
            try (Stream<String> lines = Files.lines(file)) {
                System.out.println("upper=" +
                        lines.map(String::toUpperCase).toList());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 StreamFreshFileDemo.java
java StreamFreshFileDemo
```

Đầu ra:

```text
lineCount=2
upper=[ALPHA, BETA]
```

Giải thích:

- `Files.writeString(...)` tạo hai dòng `alpha` và `beta`; phương thức main khai báo `throws IOException` để xử lý checked exception ở mức chương trình minh họa.
- Lần thứ nhất, `Files.lines(file)` mở một stream có tài nguyên I/O; `count()` tiêu thụ stream đó. Hết khối `try`, stream được đóng.
- Lần thứ hai, gọi `Files.lines(file)` **một lần khác**, tạo stream mới để `map(String::toUpperCase).toList()` và cho `[ALPHA, BETA]`. Không hề tái sử dụng stream đầu tiên.
- `finally` xóa file tạm do chương trình tạo ra. Đây là ví dụ độc lập không cần dữ liệu có sẵn và không yêu cầu thư viện bên ngoài.

Cần lưu ý khi áp dụng với dữ liệu thay đổi: mở file lần thứ hai có thể đọc nội dung mới nếu file đã bị sửa. Quy tắc one-shot không đảm bảo tính bất biến của nguồn giữa nhiều lần gọi.

## 13. Hậu quả trong ứng dụng: thiết kế API thế nào?

Một phương thức nhận `Stream<T>` nên được hiểu là **nhận quyền sử dụng một pipeline một lần**. Ví dụ:

```java
static long countWords(Stream<String> words) {
    return words.filter(s -> !s.isBlank()).count();
}
```

Đây là phương thức minh họa đặt trong lớp có import `Stream`. Một caller không nên truyền cùng đối tượng `Stream<String>` vào `countWords` nhiều lần. Với API tái sử dụng thường xuyên, bạn có thể:

- Nhận `Collection<T>` hoặc `List<T>` rồi tự gọi `.stream()` cho mỗi phép tính, nếu mô hình dữ liệu cho phép.
- Nhận `Supplier<Stream<T>>` (factory) nếu muốn mỗi lần xử lý có pipeline mới, và tài liệu hóa việc cấp phát/đóng nguồn.
- Nhận `Stream<T>` khi API được thiết kế rõ là **tiêu thụ dữ liệu một lần**. Nên ghi rõ hợp đồng để caller không trông đợi dùng lại.
- Tính nhiều kết quả trong **một terminal operation** nếu không thể tạo lại nguồn hoặc kết quả rất lớn; ví dụ dùng collector thích hợp hoặc vòng lặp đơn nhất tùy nhu cầu.

Không nên lưu một stream làm field dài hạn để nhiều phương thức công khai cùng dùng. Việc lưu stream trong biến cục bộ để xây pipeline và tiêu thụ một lần là bình thường; việc chia sẻ cùng stream giữa những nơi khác nhau dễ tạo lỗi vòng đời.

**Parallel stream vẫn one-shot:** `parallel()` không biến stream thành nguồn có thể dùng lại, cũng không tạo bản sao độc lập để chạy nhiều terminal operations. Một pipeline được thực thi song song vẫn chỉ được tiêu thụ một lần.

## 14. Những lỗi phổ biến và cách sửa

| Lỗi / hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi `stream.count()` rồi `stream.toList()` | Hai terminal operations trên một stream | Tạo hai stream mới từ nguồn, hoặc lấy danh sách trước và tính size |
| `Stream<T> a = source.stream();` dùng trong hai hàm khác nhau | `a` có vòng đời dùng một lần | Truyền collection hoặc factory để các hàm tự tạo stream |
| `source.filter(...)` rồi `source.map(...)` thành hai nhánh | Rẽ nhánh từ cùng đối tượng stream | Gọi `collection.stream()` cho mỗi nhánh |
| `findFirst()` xong dùng lại vì chưa duyệt hết | Terminal short-circuit vẫn tiêu thụ stream | Tạo stream mới |
| `iterator()` xong `count()` | `iterator()` là terminal operation | Duyệt trên iterator đã nhận hoặc tạo stream mới |
| Nghĩ `Stream` là `List` hay `Iterable` | Stream mô tả một pipeline, không phải collection có thể duyệt lại | Lưu nguồn hoặc materialize kết quả |
| Dùng `Supplier<Stream>` nhưng trả stream cũ | `get()` không làm mới nếu closure giữ stream cũ | Mỗi `get()` phải xây stream mới |
| Gọi `close()` rồi muốn chạy pipeline lần nữa | `close` kết thúc vòng đời stream | Mở nguồn mới, không reset |
| Nghĩ `toList()` tự đóng `Files.lines` | Tiêu thụ khác với giải phóng tài nguyên | Dùng try-with-resources |
| Cho rằng lần dùng sai luôn ném `IllegalStateException` | API chỉ cho phép phát hiện reuse khi có thể | Không viết mã dựa vào behavior sai hợp đồng |
| Dùng `peek` để chắc chắn mọi phần tử được xử lý | Terminal ops có thể short-circuit hoặc tối ưu | Không dựa vào side effects trong pipeline cho công việc bắt buộc |
| Chia sẻ stream cho các thread độc lập | Stream không được thiết kế làm nguồn dùng nhiều lượt | Tạo pipeline riêng; đồng bộ hóa nguồn/tài nguyên theo thiết kế |

## 15. Tự luyện tập (có đáp án)

**Bài 1.** Đoạn nào vi phạm hợp đồng?

```text
Stream<Integer> s = Stream.of(1, 2, 3);
System.out.println(s.count());
System.out.println(s.findFirst());
```

Đáp án: lời gọi `s.findFirst()` thứ hai vi phạm; `s.count()` đã tiêu thụ stream. Một số triển khai ném `IllegalStateException`.

**Bài 2.** Viết lại đoạn trên để in `3` rồi `Optional[1]` mà không tái sử dụng stream.

```java
List<Integer> data = List.of(1, 2, 3);
System.out.println(data.stream().count());
System.out.println(data.stream().findFirst());
```

Đây là các lệnh trong phương thức đã import `List`; mỗi lời gọi `data.stream()` tạo pipeline mới.

**Bài 3.** Vì sao `Supplier<Stream<Integer>> supplier = () -> existingStream;` không đảm bảo dùng được nhiều lần?

Đáp án: supplier chỉ trả **cùng đối tượng** `existingStream`. Nếu lần đầu đã tiêu thụ, lần sau vẫn là cùng stream đã tiêu thụ. Hãy viết `() -> values.stream()` khi `values` là collection còn khả dụng.

**Bài 4.** `stream.findFirst()` đọc một phần tử. Có thể dùng lại stream để `count()` các phần tử còn lại không?

Đáp án: **Không**. `findFirst()` là terminal operation; muốn đếm dữ liệu còn lại cần thiết kế một cách duyệt khác, không dựa vào tái dùng Stream đã tiêu thụ.

**Bài 5.** Sau `List<String> result = source.stream().map(...).toList();`, có thể duyệt `result` hai lần không?

Đáp án: **Có**. `result` là List, không phải stream cũ. Nếu cần duyệt qua stream thì mỗi lần gọi `result.stream()` tạo pipeline mới.

**Bài 6.** `Files.lines(path).count()` đã trả về kết quả. Có cần đóng stream không?

Đáp án: **Có**, vì stream này dùng tài nguyên I/O. Đặt `Files.lines(path)` trong try-with-resources để được `close()` khi rời khối. Terminal operation không thay thế việc đóng.

**Bài 7.** Sau khi gọi `Stream<Integer> s = Stream.of(1,2,3); s.filter(...)`, có thể gọi `s.map(...)` để tạo nhánh thứ hai không?

Đáp án: **Không** theo hợp đồng stream, dù thao tác `filter` lazy và chưa có terminal. Muốn hai nhánh, dùng hai stream mới từ cùng collection hoặc factory.

## 16. Ghi nhớ quan trọng

- **Mỗi đối tượng Stream chỉ dùng cho một pipeline xử lý duy nhất.** Sau terminal operation hoặc `close()`, không được tái sử dụng.
- **Intermediate operation có thể lazy** nhưng không cho phép rẽ nhánh từ cùng đối tượng upstream.
- **Short-circuit vẫn là terminal operation** và vẫn tiêu thụ stream; `iterator()`/`spliterator()` cũng là terminal.
- **Tạo stream mới** từ `List`, `Stream.of`, `Supplier<Stream<T>>` tạo mới thực sự, hoặc mở lại nguồn khi cần một lượt xử lý khác.
- **Tiêu thụ ≠ đóng tài nguyên**: các stream I/O cần được đóng đúng cách, thường bằng try-with-resources.
- Lần dùng sai **có thể** ném `IllegalStateException`, nhưng API không cam kết phát hiện tất cả trường hợp tái sử dụng. Cách đúng là không tái sử dụng.
- Kết quả đã materialize thành `List` có thể được truy cập nhiều lần, nhưng không biến pipeline Stream ban đầu thành reusable.

Tài liệu tham khảo chính thống: [Java SE 17 Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [BaseStream API — close, iterator, spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html), [Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)).