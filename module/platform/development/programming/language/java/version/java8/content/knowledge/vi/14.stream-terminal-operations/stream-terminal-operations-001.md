# forEach và hành động trên từng phần tử trong Java Stream

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao `Stream.forEach` là **terminal operation** (thao tác kết thúc) và cách nó kích hoạt các bước `filter`, `map` trước đó.
- Viết `Consumer` bằng lambda hoặc method reference để thực hiện một hành động trên từng phần tử.
- Phân biệt `forEach`, `forEachOrdered` và `Iterable.forEach`; lựa chọn đúng khi cần thứ tự xử lý.
- Nhận biết những rủi ro của side effect, sửa nguồn dữ liệu, shared mutable state và parallel stream.
- Biết lúc nào nên dùng `map`, `collect`, `reduce`, `anyMatch` hoặc `findFirst` thay cho `forEach`.

Các API `forEach` của Stream được đưa vào từ Java 8 và vẫn là kiến thức đang áp dụng trong các phiên bản Java hiện đại. Ví dụ trong bài dùng cú pháp tương thích Java 8, vì vậy chạy được trên JDK 17, 21 và các JDK mới hơn.

## 2. `forEach` là gì?

Chữ ký phương thức:

```java
void forEach(Consumer<? super T> action)
```

- `Stream<T>` cung cấp các phần tử; `action` là một hàm nhận một phần tử kiểu `T` (hoặc một kiểu cha của `T`).
- `Consumer<T>` là functional interface có phương thức trừu tượng `void accept(T value)`. Hành động có thể là ghi log, hiển thị hoặc gọi một tác vụ bên ngoài.
- `forEach` là **terminal operation**: nó khởi động quá trình duyệt pipeline, nhận các phần tử đi qua những bước trung gian và gọi `action` trên từng phần tử được xử lý.
- Kiểu trả về là `void`: `forEach` không tạo Stream mới, không trả về danh sách kết quả và không thể nối tiếp `.map(...)` sau `.forEach(...)`.
- Sau khi đã sử dụng một Stream bằng thao tác kết thúc, không được dùng lại chính đối tượng Stream đó. Muốn chạy tác vụ khác, hãy tạo Stream mới từ nguồn.

Ví dụ dạng pipeline:

```text
List dữ liệu
    → stream()
    → filter(...)      [trung gian, lazy]
    → map(...)         [trung gian, lazy]
    → forEach(action)  [kết thúc, kích hoạt xử lý]
```

`filter` và `map` tạo mô tả pipeline, chưa nhất thiết chạy ngay lúc được khai báo. Khi gọi `forEach`, các phần tử cần thiết đi qua các bước trước đó rồi được chuyển cho `Consumer`. Vì `forEach` là thao tác kết thúc không short-circuit, nó thường duyệt hết các phần tử của một Stream hữu hạn nếu hành động hoàn tất bình thường.

## 3. Ví dụ chạy được: lọc, biến đổi rồi thực hiện hành động

Lưu chương trình thành `ForEachDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class ForEachDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi", "Duyen");

        names.stream()
                .filter(name -> name.length() >= 4)
                .map(name -> name.toUpperCase(Locale.ROOT))
                .forEachOrdered(name -> System.out.println("Ten: " + name));
    }
}
```

Biên dịch và chạy:

```bash
javac ForEachDemo.java
java ForEachDemo
```

Kết quả chính xác:

```text
Ten: BINH
Ten: DUYEN
```

Diễn giải: `filter` bỏ `An` và `Chi` vì độ dài nhỏ hơn 4; `map` đổi hai chuỗi còn lại thành chữ hoa; `forEachOrdered` in từng tên. Ví dụ dùng `forEachOrdered` để đảm bảo thứ tự đầu ra theo danh sách gốc. Nếu thay bằng `forEach` trên Stream tuần tự, kết quả thường quan sát được giống như trên, nhưng hợp đồng API của `Stream.forEach` **không bảo đảm thứ tự encounter order**; không nên lấy hiện tượng thường gặp đó làm điều kiện đúng của chương trình.

Khi không cần thứ tự cụ thể, cách viết gọn với `forEach` là:

```java
names.stream()
        .filter(name -> name.length() >= 4)
        .forEach(System.out::println);
```

`System.out::println` là method reference tương đương `name -> System.out.println(name)`; kết quả phụ thuộc vào phần tử đã lọc, nhưng không nên ràng buộc tính đúng đắn vào thứ tự in của `Stream.forEach`.

## 4. Cách truyền hành động bằng `Consumer`

Có ba cách phổ biến, đều là cú pháp Java 8 vẫn được sử dụng:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Consumer;

public class ConsumerDemo {
    public static void main(String[] args) {
        List<String> tasks = Arrays.asList("build", "test");

        // 1. Lambda: viết hành động ngay tại chỗ.
        tasks.stream().forEachOrdered(task -> System.out.println(task));

        // 2. Method reference: chuyển thẳng phần tử vào phương thức.
        tasks.stream().forEachOrdered(System.out::println);

        // 3. Consumer có tên: tái sử dụng một hành động.
        Consumer<String> logTask = task -> System.out.println("Task: " + task);
        tasks.stream().forEachOrdered(logTask);
    }
}
```

Chạy với `javac ConsumerDemo.java` và `java ConsumerDemo`; stdout:

```text
build
test
build
test
Task: build
Task: test
```

Dùng lambda khi cần thêm điều kiện hoặc logic nhỏ, method reference khi có sẵn phương thức phù hợp, và biến `Consumer` khi muốn tái sử dụng hoặc truyền hành động giữa các phương thức. `Consumer.accept` có kiểu trả về `void`; một lambda trả giá trị để tạo dữ liệu mới thuộc vai trò của `Function`, thường dùng với `map`, chứ không phải `forEach`.

Với primitive stream, các phương thức tương ứng nhận consumer chuyên biệt: `IntStream.forEach(IntConsumer)`, `LongStream.forEach(LongConsumer)`, `DoubleStream.forEach(DoubleConsumer)`. Chúng tránh boxing chỉ để duyệt các giá trị nguyên thủy.

## 5. Thứ tự xử lý: `forEach` và `forEachOrdered`

**Encounter order** là thứ tự có ý nghĩa do nguồn Stream và các bước pipeline xác định. `List`, mảng và `IntStream.range(...)` có thứ tự encounter order; `HashSet` thường không có thứ tự được bảo đảm. Gọi `unordered()` cho phép pipeline bỏ yêu cầu duy trì encounter order.

| API | Bảo đảm thứ tự hành động? | Hành vi chính |
| --- | --- | --- |
| `Stream.forEach(action)` | Không, kể cả khi nguồn có encounter order | Terminal operation, có thể chạy hành động trên các thread khác nhau khi parallel |
| `Stream.forEachOrdered(action)` | Có, nếu Stream có encounter order | Terminal operation, thực hiện hành động theo encounter order |
| `Iterable.forEach(action)` (ví dụ `List.forEach`) | Theo thứ tự lặp của Iterable nếu thứ tự ấy được quy định | Duyệt trực tiếp Iterable; không cần pipeline Stream |

Đối với `forEachOrdered`, hành động của phần tử trước **happens-before** hành động của phần tử tiếp theo theo encounter order. Điều đó không có nghĩa mọi bước `filter`/`map` trước nó đều chạy tuần tự, cũng không bảo đảm tất cả hành động chạy cùng một thread. Với nguồn không có encounter order, `forEachOrdered` không tự tạo thứ tự có ý nghĩa; nếu thực sự cần thứ tự, hãy thiết kế một nguồn có thứ tự hoặc sắp xếp dữ liệu theo tiêu chí rõ ràng.

Ví dụ parallel có đầu ra ổn định:

```java
import java.util.stream.IntStream;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        IntStream.rangeClosed(1, 5)
                .parallel()
                .forEachOrdered(System.out::print);

        System.out.println();
        System.out.println("Tong = " +
                IntStream.rangeClosed(1, 5).parallel().sum());
    }
}
```

```bash
javac ParallelOrderDemo.java
java ParallelOrderDemo
```

```text
12345
Tong = 15
```

Ngược lại, `IntStream.rangeClosed(1, 5).parallel().forEach(System.out::print)` có thể in các chữ số theo thứ tự khác nhau giữa các lần chạy. `forEachOrdered` giữ thứ tự hành động nhưng có thể giảm lợi ích hiệu năng của parallel do ràng buộc thứ tự; đo hiệu năng trên công việc thực tế trước khi quyết định dùng parallel.

**Lưu ý:** `List.forEach` và `list.stream().forEach` là hai API khác nhau. `List.forEach` đi theo thứ tự iterator của List; `Stream.forEach` có hợp đồng thứ tự riêng như bảng trên. `Map.forEach((key, value) -> ...)` lại nhận `BiConsumer` và thuộc API Map, không phải terminal operation của Stream.

## 6. Side effect: lúc nào hữu ích, lúc nào nguy hiểm?

`forEach` tồn tại chủ yếu để thực hiện **side effect**: tạo một tác động ngoài giá trị trả về của pipeline, chẳng hạn in ra màn hình, ghi log, cập nhật một hệ thống được kiểm soát hoặc gửi một sự kiện. Không phải mọi side effect đều sai, nhưng chúng cần được thiết kế rõ ràng:

1. **Non-interference:** hành động không được thay đổi nguồn Stream không hỗ trợ chỉnh sửa đồng thời. Ví dụ duyệt `list.stream()` rồi `list.remove(...)` ngay trong `forEach` là sai thiết kế; có thể gây ngoại lệ, bỏ sót hoặc kết quả không xác định.
2. **An toàn luồng:** khi `parallel()`, nhiều lời gọi `action` có thể chạy đồng thời. Việc `new ArrayList<>()` rồi thêm phần tử bằng `forEach(list::add)` từ parallel stream có data race, có thể mất phần tử hoặc gây lỗi.
3. **Độc lập giữa các phần tử:** nên để mỗi hành động ít phụ thuộc vào trạng thái thay đổi từ các lần gọi khác. Không suy luận rằng phần tử trước luôn chạy xong trước phần tử sau trong `forEach`.
4. **I/O và lỗi bên ngoài:** ghi file, gọi API hoặc gửi thông báo có thể thất bại giữa chừng. `forEach` không cung cấp cơ chế transaction, retry hay rollback. Nếu chạy lại tác vụ có tác động bên ngoài, cân nhắc idempotency, kiểm soát trùng lặp và báo lỗi phù hợp ở tầng ứng dụng.
5. **Không lạm dụng parallel:** nhiều thao tác I/O hoặc ghi vào cùng một tài nguyên làm tăng tranh chấp; parallel stream không tự bảo đảm nhanh hơn.

Đặc biệt, đừng dùng `forEach` để tự xây dựng danh sách kết quả khi có thể diễn đạt bằng phép biến đổi và thu thập:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class CollectInsteadOfForEach {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);

        List<Integer> squares = numbers.stream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .collect(Collectors.toList());

        System.out.println(squares);
    }
}
```

```bash
javac CollectInsteadOfForEach.java
java CollectInsteadOfForEach
```

```text
[4, 16, 36]
```

`collect` diễn đạt rõ ý định **tạo kết quả tổng hợp** và tránh viết vào một `ArrayList` được chia sẻ trong `forEach`. `Collectors.toList()` có mặt từ Java 8; đặc tính cụ thể về kiểu danh sách và khả năng chỉnh sửa của kết quả không được API này bảo đảm. Trên JDK 16 trở lên, `Stream.toList()` là lựa chọn khác khi phù hợp, nhưng nó trả về danh sách không thể chỉnh sửa.

Muốn tính tổng, đếm hoặc thống kê, dùng `sum`, `count`, `reduce` hoặc collector tương ứng. Ví dụ `IntStream.rangeClosed(1, 1_000).parallel().sum()` vừa thể hiện đúng mục đích, vừa không cần một biến đếm/tổng chia sẻ giữa các thread.

## 7. `forEach` không phải vòng lặp có `break`

`forEach` không trả về giá trị boolean để dừng duyệt như vòng lặp thông thường. `return` bên trong một lambda chỉ kết thúc lần gọi lambda hiện tại, không thoát khỏi phương thức bao quanh và không buộc toàn bộ Stream dừng lại.

Nếu muốn:

- **Chỉ xử lý tối đa N phần tử:** đặt `limit(N)` trước terminal operation, ví dụ `stream.limit(3).forEach(action)`.
- **Kiểm tra có phần tử phù hợp hay không:** dùng `anyMatch(predicate)`, thao tác có thể short-circuit.
- **Lấy phần tử đầu tiên theo encounter order:** dùng `findFirst()`; xem xét `Optional` trả về.
- **Tạo tập con:** dùng `filter(predicate)` rồi `collect(...)` thay vì điều khiển dừng bằng side effect.
- **Điều khiển vòng lặp tùy biến bằng `break`/`continue` phức tạp:** một vòng `for` thông thường có thể rõ ràng hơn.

Với Stream vô hạn như `Stream.iterate(0, n -> n + 1)`, gọi trực tiếp `forEach` sẽ không tự kết thúc. Hãy dùng giới hạn phù hợp hoặc một terminal operation có điều kiện dừng, chẳng hạn `limit(5).forEachOrdered(...)`.

## 8. Ngoại lệ và quản lý tài nguyên

- Nếu `action` ném unchecked exception, ngoại lệ có thể được truyền đến lời gọi terminal. Không được giả định mọi phần tử còn lại sẽ được xử lý; khi parallel, một số hành động khác có thể đã được khởi chạy hoặc hoàn thành.
- `Consumer.accept` không khai báo checked exception. Với thao tác có thể ném checked exception, hãy xử lý hoặc chuyển đổi ngoại lệ một cách có chủ đích tại ranh giới phù hợp, thay vì nuốt lỗi.
- Nếu nguồn Stream giữ tài nguyên cần đóng (ví dụ `Files.lines`), dùng `try-with-resources`. Gọi `forEach` không thay thế trách nhiệm đóng Stream có tài nguyên nền.
- Nếu `action` là lời gọi dịch vụ bên ngoài, việc “đã chạy `forEach`” không chứng minh mọi tác động bên ngoài đều thành công; hãy xác định chính sách lỗi cho từng tác vụ.

Ví dụ mẫu khi đọc từng dòng từ file; **đoạn này cần có file thật** và được đặt trong phương thức khai báo `throws IOException` hoặc có xử lý ngoại lệ:

```java
try (java.util.stream.Stream<String> lines =
             java.nio.file.Files.lines(
                     java.nio.file.Paths.get("input.txt"),
                     java.nio.charset.StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.trim().isEmpty())
         .forEachOrdered(System.out::println);
}
```

`try-with-resources` đóng Stream (và tài nguyên đọc file) sau khi sử dụng, kể cả khi có lỗi. Đây là snippet minh họa, không phải chương trình độc lập; các ví dụ ở mục 3, 4, 5 và 6 là các lớp Java có thể biên dịch/chạy nguyên vẹn.

## 9. Phân biệt các thao tác thường bị nhầm

| Nhu cầu | Nên ưu tiên | Vì sao |
| --- | --- | --- |
| Thực hiện một hành động lên từng phần tử, thứ tự không quan trọng | `forEach` | Terminal, nhận `Consumer`, trả `void` |
| Thực hiện hành động theo encounter order có sẵn | `forEachOrdered` | Bảo đảm thứ tự hành động khi nguồn có thứ tự |
| Biến đổi mỗi phần tử thành giá trị khác | `map` | Intermediate, trả Stream kết quả |
| Lọc theo điều kiện | `filter` | Intermediate, chỉ giữ phần tử phù hợp |
| Gom kết quả thành danh sách/map/nhóm | `collect` | Terminal, thực hiện phép gom có cấu trúc |
| Kết hợp thành một kết quả | `reduce`, `sum`, `count` | Tránh biến tích lũy chia sẻ |
| Xem giá trị đi qua pipeline để kiểm tra trong lúc phát triển | `peek` (thận trọng) | Intermediate; không nên dựa vào side effect vì có thể bị bỏ qua khi tối ưu |
| Dừng sớm khi tìm thấy kết quả | `anyMatch`, `findFirst` | Short-circuit terminal operations |

`peek` không nên là nơi thực thi nghiệp vụ cần chạy chắc chắn, vì các bước trung gian có thể bị tối ưu bỏ qua nếu không ảnh hưởng kết quả cuối. Với `forEach` và `forEachOrdered`, chính hành động terminal là mục đích thực thi, nên không bị loại bỏ theo cách tối ưu các side effect trung gian; vẫn có giới hạn do ngoại lệ, Stream vô hạn và lỗi ứng dụng.

## 10. Bài tập tự kiểm tra

**Bài 1.** Cho `List<Integer> numbers = Arrays.asList(3, 4, 5, 6, 7);`. Hãy dùng Stream để in bình phương của các số chẵn, theo thứ tự xuất hiện trong danh sách.

Lời giải:

```java
import java.util.Arrays;
import java.util.List;

public class ForEachExercise {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(3, 4, 5, 6, 7);

        numbers.stream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .forEachOrdered(System.out::println);
    }
}
```

```bash
javac ForEachExercise.java
java ForEachExercise
```

```text
16
36
```

**Bài 2.** Một chương trình chạy `parallelStream().forEach(result::add)` với `result` là `ArrayList` dùng chung. Lỗi thiết kế là gì? Cách thay thế đúng là biểu diễn phép thu thập bằng `collect(Collectors.toList())` (hoặc phép gom phù hợp), thay vì ghi đồng thời vào danh sách không đồng bộ.

**Bài 3.** Vì sao thêm `forEachOrdered` vào `HashSet.stream()` chưa thể bảo đảm thứ tự tăng dần? Vì `HashSet` không cam kết encounter order. Muốn tăng dần, cần áp đặt thứ tự rõ ràng bằng `sorted()` trước `forEachOrdered`, giả sử phần tử so sánh được.

**Bài 4.** Khi nào chọn `forEach` thay vì `map`? Chọn `forEach` khi kết quả mong muốn chính là hành động được thực hiện trên mỗi phần tử; chọn `map` khi muốn tạo giá trị mới để tiếp tục pipeline.

## 11. Checklist trước khi dùng trong thực tế

- Tôi có thực sự cần **side effect** trên từng phần tử, hay nên dùng `map`/`collect`/`reduce`?
- Nguồn có encounter order không? Kết quả nghiệp vụ có cần tuân thủ thứ tự đó không?
- Nếu dùng `parallel()`, hành động có thread-safe và độc lập không?
- Hành động có vô tình sửa nguồn Stream hoặc một biến mutable được chia sẻ không?
- Nếu một hành động lỗi giữa chừng, có chính sách retry, idempotency và báo lỗi phù hợp không?
- Stream có hữu hạn không, và nguồn có cần đóng tài nguyên không?
- Tôi có đang cố dùng `forEach` để `break`, trả kết quả hoặc dùng lại Stream không?

## 12. Tài liệu API đang áp dụng

- Oracle Java SE 26, `Stream.forEach` và `Stream.forEachOrdered`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- Oracle Java SE 26, `java.util.stream` (ordering, non-interference, side effects, parallelism): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 25, `Iterable.forEach`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Iterable.html

Các tài liệu trên mô tả hợp đồng API hiện hành. Nguyên tắc cốt lõi cần nhớ: `forEach` là terminal operation để thực hiện hành động, thứ tự hành động chỉ được bảo đảm bởi `forEachOrdered` khi Stream có encounter order, và side effect phải được thiết kế an toàn.