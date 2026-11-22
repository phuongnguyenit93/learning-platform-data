# Stream tuần tự và Stream song song trong Java

Java Stream API cho phép mô tả cách xử lý một chuỗi phần tử bằng các phép biến đổi và phép kết thúc, thay vì tự viết vòng lặp cho từng bước. **Stream tuần tự (sequential stream)** xử lý pipeline theo chế độ tuần tự; **Stream song song (parallel stream)** cho phép thư viện chia công việc ra nhiều phần và thực hiện trên nhiều luồng (*threads*) khi phù hợp.

Hai chế độ dùng cùng nhiều API như `filter`, `map`, `reduce`, `collect`, nhưng **không có nghĩa chúng luôn có cùng đặc điểm thứ tự thực thi, hiệu năng hoặc tương tác với side effect**. Đặc biệt, chuyển một pipeline sang song song không tự biến logic sai, phép gộp không kết hợp được hoặc shared mutable state thành an toàn.

Sau bài học, bạn có thể:
- Tạo Stream tuần tự bằng `stream()`, Stream song song bằng `parallelStream()` hoặc `parallel()`.
- Hiểu *pipeline*, tính lazy, terminal operation và các quy tắc chuyển chế độ.
- Phân biệt **encounter order** với **thứ tự chạy trên thread**, và chọn đúng `forEach`, `forEachOrdered`, `toList`, `findFirst`, `findAny`.
- Dùng `reduce` và collector an toàn với phép tính song song.
- Tránh side effect chia sẻ, lỗi race condition và các giả định hiệu năng không có cơ sở.
- Quyết định lúc nào parallel stream có lợi, khi nào nên chọn stream tuần tự.

Các ví dụ hoàn chỉnh dùng **JDK 17 trở lên**, có lệnh biên dịch và đầu ra xác định. Đoạn mã cố ý sai hoặc kết quả không xác định sẽ được đánh dấu riêng.

## 1. Stream pipeline hoạt động như thế nào?

Một pipeline thường có ba thành phần:

1. **Nguồn (source):** collection, mảng, range số hoặc nguồn khác.
2. **Các intermediate operations:** `filter`, `map`, `distinct`, `sorted`, `limit`… tạo ra một Stream mới mô tả bước xử lý. Chúng thường **lazy**, chưa duyệt nguồn ngay.
3. **Terminal operation:** `toList`, `collect`, `sum`, `count`, `reduce`, `forEach`, `findFirst`… kích hoạt việc thực thi pipeline.

Ví dụ minh họa:

```java
List<Integer> result = List.of(1, 2, 3, 4, 5, 6)
        .stream()                 // nguồn và chế độ tuần tự
        .filter(n -> n % 2 == 0) // intermediate
        .map(n -> n * n)         // intermediate
        .toList();               // terminal
// [4, 16, 36]
```

Đây là **mảnh mã** cần `import java.util.List;` và nằm trong phương thức. `toList()` được thêm từ Java 16 và chạy trên Java 17.

**Một Stream không phải collection chứa sẵn mọi kết quả.** Stream thể hiện pipeline có thể duyệt một lần, và phải dùng một Stream mới nếu muốn chạy lại terminal operation. Không thể dùng chung một Stream đã tiêu thụ rồi gọi terminal lần thứ hai.

Chế độ tuần tự/song song quyết định **cách pipeline được thực thi** khi terminal operation chạy, không thay đổi ý nghĩa toán học của các phép biến đổi thuần hợp lệ.

## 2. Tạo Stream tuần tự và Stream song song

Với `Collection<T>` thông thường:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

Stream<Integer> sequential = numbers.stream();
Stream<Integer> parallel = numbers.parallelStream();
```

Đoạn trên cần `import java.util.List;` và `import java.util.stream.Stream;`.

- `numbers.stream()` tạo Stream ở chế độ **tuần tự**.
- `numbers.parallelStream()` tạo Stream ở chế độ **song song**.
- Trên một Stream, `parallel()` yêu cầu chế độ song song; `sequential()` yêu cầu tuần tự.
- `isParallel()` trả về cờ chế độ hiện tại của Stream, **không khẳng định đã có bao nhiêu thread thực sự chạy**.

Ví dụ:

```java
Stream<Integer> s = numbers.stream().parallel();
boolean parallelMode = s.isParallel(); // true
```

Có thể chuyển lại bằng `sequential()` trong quá trình xây pipeline. **Chế độ hiệu lực ở lúc terminal chạy** là yếu tố cần xét; việc gọi `parallel()` ở đầu rồi `sequential()` ở cuối không tạo hai giai đoạn tách biệt “nửa đầu parallel, nửa sau sequential”.

Với primitive streams:

```java
int total = java.util.stream.IntStream.rangeClosed(1, 100)
        .parallel()
        .sum();
```

Đây là mảnh mã độc lập trong phương thức. `IntStream` tránh boxing cho phép tính `int`, nhưng bản thân việc thêm `parallel()` **không bảo đảm nhanh hơn**.

## 3. Ví dụ Java 17: cùng kết quả ở cả hai chế độ

Lưu thành **`SequentialParallelDemo.java`**:

```java
import java.util.List;
import java.util.stream.Stream;

public class SequentialParallelDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

        List<Integer> sequentialSquares = numbers.stream()
                .map(n -> n * n)
                .toList();

        List<Integer> parallelSquares = numbers.parallelStream()
                .map(n -> n * n)
                .toList();

        int sequentialSum = numbers.stream()
                .mapToInt(Integer::intValue)
                .sum();

        int parallelSum = numbers.parallelStream()
                .mapToInt(Integer::intValue)
                .sum();

        Stream<Integer> mode = numbers.stream()
                .parallel()
                .sequential();

        System.out.println("sequential=" + sequentialSquares);
        System.out.println("parallel=" + parallelSquares);
        System.out.println("sum sequential=" + sequentialSum);
        System.out.println("sum parallel=" + parallelSum);
        System.out.println("isParallel=" + mode.isParallel());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SequentialParallelDemo.java
java SequentialParallelDemo
```

**Stdout chính xác:**

```text
sequential=[1, 4, 9, 16, 25, 36]
parallel=[1, 4, 9, 16, 25, 36]
sum sequential=21
sum parallel=21
isParallel=false
```

Giải thích: `List.of` có encounter order theo thứ tự phần tử ban đầu. `map` là phép biến đổi không có side effect; `toList()` giữ encounter order của Stream có thứ tự, kể cả khi công việc được thực hiện song song. `sum()` cho cùng tổng ở ví dụ số nguyên này. `mode` đã gọi `sequential()` sau `parallel()`, nên cờ chế độ cuối cùng là false.

Điều này **không có nghĩa phần tử phải được xử lý lần lượt theo thứ tự 1, 2, 3… trong parallel stream**. Chế độ song song có thể thực hiện các phần tử trên nhiều thread theo một thứ tự khác, rồi kết hợp kết quả để bảo toàn những bảo đảm đầu ra của terminal operation.

## 4. Encounter order khác execution order

**Encounter order** là thứ tự phần tử được xác định bởi nguồn và các phép xử lý giữ thứ tự. Ví dụ `List.of("A","B","C")` có encounter order `A, B, C`. Tuy nhiên `HashSet` không bảo đảm encounter order xác định như `List`.

**Execution order** là thứ tự các thao tác được thực hiện thực tế trong pipeline. Với Stream song song, các thao tác trên các phần tử có thể diễn ra ở những thread và thời điểm khác nhau. Không được dựa vào thứ tự chạy của `map`, `filter` hoặc `peek` để suy ra thứ tự kết quả.

| API | Với Stream có encounter order | Điều cần hiểu |
| --- | --- | --- |
| `toList()` | Giữ encounter order trong danh sách kết quả | Công việc nội bộ vẫn có thể song song. |
| `forEach(action)` | Không bảo đảm thứ tự gọi action khi song song | Không dùng để xuất log cần theo thứ tự. |
| `forEachOrdered(action)` | Gọi action theo encounter order | Có thể tốn chi phí điều phối; không bắt mọi upstream chạy tuần tự. |
| `findFirst()` | Chọn phần tử đầu tiên theo encounter order khi tồn tại | Có thể tốn hơn `findAny` trong pipeline có thứ tự. |
| `findAny()` | Được phép trả bất kỳ phần tử phù hợp nào | Không giả định luôn trả phần tử đầu tiên. |
| `sorted()` | Tạo thứ tự sắp xếp theo comparator/natural ordering phù hợp | Là phép có trạng thái và có thể tốn chi phí. |
| `unordered()` | Bỏ yêu cầu giữ encounter order | Không đồng nghĩa kết quả bị xáo ngẫu nhiên. |

Bảo đảm thứ tự chỉ có ý nghĩa **khi nguồn/pipeline có encounter order**. Nếu nguồn không có thứ tự, `forEachOrdered` không thể tạo ra một “thứ tự gốc” mà nguồn vốn không cung cấp.

## 5. Ví dụ Java 17: đầu ra có thứ tự và hành vi không bảo đảm

Lưu thành **`StreamOrderDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class StreamOrderDemo {
    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");

        List<String> lower = words.parallelStream()
                .map(word -> word.toLowerCase(Locale.ROOT))
                .toList();
        System.out.println("toList=" + lower);

        System.out.print("forEachOrdered=");
        words.parallelStream().forEachOrdered(System.out::print);
        System.out.println();

        System.out.println("findFirst="
                + words.parallelStream().findFirst().orElse("-"));

        boolean anyIsInList = words.parallelStream()
                .findAny()
                .filter(words::contains)
                .isPresent();
        System.out.println("findAny belongs=" + anyIsInList);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StreamOrderDemo.java
java StreamOrderDemo
```

**Stdout chính xác:**

```text
toList=[a, b, c, d]
forEachOrdered=ABCD
findFirst=A
findAny belongs=true
```

`findAny()` có thể chọn một trong bốn phần tử; ví dụ **không in trực tiếp giá trị đó** mà chỉ kiểm tra nó thuộc danh sách nguồn, nên đầu ra luôn xác định và không phụ thuộc vào scheduling. `forEachOrdered` bảo toàn thứ tự action theo encounter order. Với `forEach` trên parallel stream, **không được đưa ra một stdout cố định** như `ABCD`, vì thứ tự có thể thay đổi giữa các lần chạy.

Không nên dùng `forEachOrdered` chỉ để ép mọi bước tính toán phía trước chạy tuần tự; nó bảo đảm thứ tự của **action đầu ra**, không phải trình tự nội bộ của toàn pipeline.

## 6. Lazy evaluation và terminal operation

Tính **lazy** áp dụng cho các intermediate operations ở cả hai chế độ. Ví dụ:

```java
var pipeline = List.of(1, 2, 3, 4)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

// Ở đây pipeline chưa được tiêu thụ.
List<Integer> result = pipeline.toList(); // [20, 40]
```

Đây là mảnh mã có thể đặt trong phương thức, với `import java.util.List;`. Việc gọi `parallelStream()` hoặc khai báo `map` không tự khởi chạy mọi phép biến đổi. `toList()` mới kích hoạt pipeline.

Các terminal operations có thể **dừng sớm**:
- `anyMatch` có thể dừng khi đã tìm thấy phần tử thỏa điều kiện.
- `allMatch` có thể dừng khi đã tìm thấy phần tử không thỏa.
- `noneMatch` có thể dừng khi đã thấy một phần tử thỏa.
- `findFirst`, `findAny` có thể kết thúc khi tìm được kết quả phù hợp theo hợp đồng của chúng.

Trong parallel stream, có thể có nhiều phần tử đang được xử lý gần như đồng thời khi một thao tác quyết định dừng. Vì vậy **không hứa rằng các lambda trong `filter`, `map` hoặc `peek` sẽ được gọi đúng một lần cho từng phần tử nguồn**. Một số terminal operations cũng có thể tránh thực thi một số bước khi tối ưu hóa hợp lệ. Tránh side effect bắt buộc trong intermediate operations.

Đối với Stream rỗng, `anyMatch` là false; `allMatch` và `noneMatch` đều true. Quy tắc này không đổi khi chuyển sang parallel.

## 7. Reduce: phép gộp phải có tính kết hợp

Parallel stream thường cần **chia đầu vào, tính kết quả từng phần, rồi gộp kết quả**. Vì vậy các phép rút gọn như `reduce` cần một toán tử có các tính chất phù hợp:

- **Associative (kết hợp được):** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- **Identity (phần tử đơn vị):** `identity ⊕ x = x` và `x ⊕ identity = x`.
- Hành vi phải phù hợp tính **non-interfering** và **stateless** theo hợp đồng Stream để kết quả dự đoán được.

Đối với cộng số nguyên không tràn trong dữ liệu ví dụ, `0` là identity và phép cộng có tính kết hợp. Phép trừ thông thường **không** có tính kết hợp.

Mẫu an toàn:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 6)
        .parallel()
        .reduce(0, Integer::sum); // 21
```

Mẫu **không phù hợp để yêu cầu kết quả giống nhau giữa hai chế độ**:

```java
int value = java.util.stream.IntStream.rangeClosed(1, 6)
        .parallel()
        .reduce(0, (a, b) -> a - b);
```

Phép trừ không kết hợp được, nên các cách phân chia và ghép phần tử có thể dẫn tới kết quả khác với một chuỗi phép trừ tuần tự. Đừng đưa ra một giá trị stdout cố định cho biểu thức parallel ở đoạn này.

**Lưu ý về số thực:** phép cộng `double` theo IEEE 754 có sai số làm tròn; đổi cách nhóm phép cộng trong parallel có thể tạo chênh lệch nhỏ so với tuần tự. Khi cần tính số có yêu cầu độ chính xác/khả năng tái lập nghiêm ngặt, phải thiết kế phép tính và kiểm tra sai số phù hợp, không chỉ thêm `parallel()`.

## 8. Ví dụ Java 17: reduce và collect an toàn

Lưu thành **`ParallelReductionDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelReductionDemo {
    public static void main(String[] args) {
        int sequentialSum = IntStream.rangeClosed(1, 8)
                .sum();
        int parallelSum = IntStream.rangeClosed(1, 8)
                .parallel()
                .reduce(0, Integer::sum);

        List<Integer> evens = IntStream.rangeClosed(1, 8)
                .parallel()
                .filter(n -> n % 2 == 0)
                .boxed()
                .toList();

        List<String> names = List.of("a", "bb", "ccc", "dd", "eee");
        Map<Integer, Long> lengthCounts = names.parallelStream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()));

        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("evens=" + evens);
        System.out.println("lengthCounts=" + lengthCounts);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ParallelReductionDemo.java
java ParallelReductionDemo
```

**Stdout chính xác:**

```text
sequentialSum=36
parallelSum=36
evens=[2, 4, 6, 8]
lengthCounts={1=1, 2=2, 3=2}
```

Trong `parallelSum`, `Integer::sum` là toán tử cộng kết hợp được với identity 0 trên các đầu vào nhỏ này. `evens` giữ encounter order của `IntStream.rangeClosed` qua `filter` và `toList`. `groupingBy` dùng `TreeMap::new` để kết quả map được hiển thị theo thứ tự khóa số tăng dần; `Collectors.counting()` đếm phần tử thuộc mỗi nhóm độ dài.

Điểm đáng chú ý: **collector được thiết kế đúng** cho phép Stream framework quản lý các container trung gian và gộp kết quả. Không cần tự tạo một `ArrayList` chung rồi cho nhiều thread gọi `add` trong `forEach`.

## 9. Side effect và shared mutable state: nguyên nhân lỗi phổ biến

Đây là một đoạn code **không an toàn** nếu đổi sang parallel:

```java
List<Integer> output = new java.util.ArrayList<>();
java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(output::add); // KHÔNG AN TOÀN: ArrayList bị sửa đồng thời
```

Đoạn trên là mảnh mã cảnh báo: `ArrayList` không hỗ trợ nhiều thread đồng thời thêm phần tử mà không đồng bộ phù hợp. Có thể xảy ra lost updates, trạng thái sai, ngoại lệ hoặc kết quả không dự đoán được. Không dùng nó để benchmark và không giả định kết quả luôn có đúng 1.000 phần tử.

Cách viết đúng khi muốn một danh sách kết quả:

```java
List<Integer> output = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .toList();
```

Đây là mảnh mã độc lập với mảnh phía trên; nếu ghép vào cùng phương thức phải đổi tên một biến. `Stream.toList()` trả về danh sách **không sửa được qua API của nó**. Nếu cần kết quả mutable, dùng một collector phù hợp như `collect(Collectors.toCollection(ArrayList::new))` để framework quản lý việc tổng hợp.

### Vì sao synchronized không phải “thuốc tăng tốc”?

Đưa mọi thao tác vào một khóa đồng bộ có thể giúp một số cập nhật riêng lẻ an toàn, nhưng các thread sẽ tranh chấp và serialize phần việc quan trọng. Khi đó parallel stream có thể **chậm hơn** stream tuần tự. Ngoài ra, một phép cập nhật riêng lẻ an toàn chưa bảo đảm invariant của nhiều biến/cấu trúc.

Các hàm truyền vào `filter`, `map`, `reduce` nên ưu tiên:
- **Non-interfering:** không sửa nguồn dữ liệu đang được Stream duyệt.
- **Stateless:** kết quả không phụ thuộc vào trạng thái mutable thay đổi giữa các lần gọi.
- **Deterministic khi cần:** dùng các phép toán mà cùng đầu vào cho cùng kết quả, tránh reliance vào thread hoặc thứ tự lịch trình.

Đối với tác vụ ghi file, gọi mạng, cập nhật cơ sở dữ liệu hoặc phát sự kiện mà thứ tự rất quan trọng, hãy thiết kế API tác vụ/concurrency rõ ràng thay vì tin rằng `parallelStream().forEach` cung cấp ordering, retry, backpressure hoặc transaction semantics.

## 10. forEach, forEachOrdered, collect: chọn theo mục đích

Nếu muốn **tính ra dữ liệu**, ưu tiên `map` rồi terminal như `toList`, `collect`, `reduce`, `sum`. Nếu muốn **thực hiện action** cho từng phần tử, `forEach` phù hợp nhưng không bảo đảm thứ tự trên parallel stream.

```java
List<String> words = List.of("A", "B", "C");
words.parallelStream().forEachOrdered(System.out::print);
System.out.println(); // in ABC theo encounter order
```

Đoạn minh họa cần `import java.util.List;`. Nếu dùng `forEach` thay cho `forEachOrdered`, đừng viết test đòi log luôn có thứ tự `ABC`.

Điều cần nhớ: `forEachOrdered` có thể làm tốn thêm chi phí duy trì thứ tự, và không đồng nghĩa mọi bước `map`/ `filter` trước nó chỉ chạy trên một thread.

Với `collect`, framework có thể thu thập vào các container riêng rồi gộp kết quả theo collector. Dùng collector đúng thường tốt hơn một biến mutable bên ngoài pipeline. Những collector `CONCURRENT` có quy tắc riêng; **không phải collector nào cũng concurrent**, nhưng collector chuẩn như `toList` hoặc `groupingBy` vẫn có thể được framework dùng an toàn trong reduce song song phù hợp với hợp đồng của chúng.

## 11. findFirst, findAny và short-circuit

Với ordered stream, `findFirst()` có hợp đồng chọn **phần tử đầu tiên theo encounter order**. `findAny()` được phép chọn một phần tử bất kỳ, nên có thể hiệu quả hơn khi không cần phần tử đầu tiên trong chế độ song song.

```java
int first = List.of(10, 20, 30)
        .parallelStream()
        .findFirst()
        .orElse(-1); // 10
```

Đoạn minh họa này yêu cầu `import java.util.List;`. Nếu thay `findFirst` bằng `findAny`, không dựa vào việc chắc chắn trả 10 dù một vài lần chạy có thể quan sát được như vậy.

Các phép `anyMatch`, `allMatch`, `noneMatch`, `findAny` có thể **short-circuit**. Tuy nhiên khi pipeline chạy song song, có thể có công việc đang diễn ra trên những phần tử khác trước khi kết quả được xác định. Vì vậy không dùng side effect trong `peek` để suy luận một số lượng phần tử luôn được duyệt.

## 12. sorted, distinct, limit và unordered trong parallel stream

Một số intermediate operations có trạng thái (*stateful*) hoặc yêu cầu phối hợp:
- `sorted()` phải xác định thứ tự toàn bộ tập phần tử thích hợp.
- `distinct()` cần phát hiện phần tử trùng theo `equals`/`hashCode`; với ordered parallel stream, duy trì phép lấy phần tử gặp đầu tiên có thể làm tăng chi phí.
- `limit(n)` trên ordered parallel stream cần bảo toàn **n phần tử đầu tiên**, nên có thể đắt đỏ hơn khi không cần thứ tự.
- `unordered()` cho phép loại bỏ yêu cầu encounter order, giúp một số tác vụ không cần thứ tự có thể tối ưu tốt hơn.

**Không hiểu `unordered()` là “đảo thứ tự ngẫu nhiên”**. Nó chỉ tháo bỏ ràng buộc thứ tự của pipeline; kết quả có thể tình cờ giữ thứ tự cũ. Nếu output cần thứ tự ổn định, không thêm `unordered()` chỉ để tăng tốc.

`takeWhile` và `dropWhile` trên ordered streams cũng có ràng buộc giữ tiền tố theo encounter order; khi chạy song song, việc giữ đúng tiền tố có thể cần phối hợp tốn kém. Nếu thứ tự là yêu cầu nghiệp vụ, chấp nhận chi phí này hoặc dùng thuật toán khác thay vì bỏ bảo đảm đúng.

## 13. Khi nào parallel stream có thể nhanh hơn?

Parallel stream **không tự động là tối ưu hiệu năng**. Cân nhắc một số yếu tố:

| Yếu tố | Có thể thuận lợi cho parallel | Có thể bất lợi |
| --- | --- | --- |
| Số lượng phần tử | Dữ liệu lớn | Dữ liệu nhỏ, overhead chia/gộp lớn |
| Chi phí xử lý mỗi phần tử | CPU-bound, đủ nặng, độc lập | Phép tính rất nhẹ |
| Nguồn và khả năng chia | Mảng, `ArrayList`, `IntStream.range` thường dễ chia | Nguồn khó chia hoặc tốn chi phí duyệt |
| Ordering | Không cần bảo toàn thứ tự ở mọi bước | Cần `forEachOrdered`, `findFirst`, `limit` có thứ tự |
| Reduction | Associative, identity đúng, collector phù hợp | Side effect, phép gộp không kết hợp được |
| Trạng thái | Không chia sẻ mutable state | Lock contention, race conditions |
| Môi trường chạy | Có nhiều CPU cores và đủ tài nguyên | CPU đã bận, giới hạn tài nguyên, shared pool bị tranh chấp |

Parallel stream trong JDK thường sử dụng cơ chế thực thi dựa trên **Fork/Join** (thường là common pool trong các ngữ cảnh thông thường). Số thread, cách chia việc, thứ tự và lợi ích hiệu năng không phải hợp đồng cố định mà mã nên phụ thuộc. Khi các thread phải chờ I/O hoặc cùng tranh tài nguyên, parallel streams có thể không phù hợp; các kiến trúc bất đồng bộ hoặc executor được kiểm soát có thể rõ hơn.

Muốn đo đúng:
1. Đảm bảo thuật toán ở cả hai chế độ có cùng ý nghĩa và kết quả.
2. Dùng dữ liệu thực tế, số phần tử đủ lớn, môi trường và cấu hình tương ứng sản phẩm.
3. Làm nóng JIT, lặp nhiều lần và tránh đo một lần.
4. Dùng một công cụ benchmark nghiêm túc như **JMH** thay vì kết luận từ một phép `System.nanoTime()` đơn lẻ.
5. Quan sát CPU, garbage collection, allocation và contention, không chỉ thời gian tường.

**Ưu tiên stream tuần tự làm mặc định**, chỉ chuyển sang song song khi công việc độc lập, kết quả đúng và benchmark cho thấy lợi ích.

## 14. Các lỗi tư duy thường gặp

1. **“Parallel stream luôn chạy nhanh hơn.”** Sai; overhead và contention có thể vượt lợi ích.
2. **“parallel() lập tức chạy pipeline trên thread khác.”** Sai; pipeline vẫn lazy cho đến terminal operation và không hứa thread cụ thể.
3. **“toList() trên parallel luôn đảo thứ tự.”** Sai; với encounter order xác định, `toList` giữ thứ tự kết quả.
4. **“forEach() trên parallel luôn theo thứ tự nguồn.”** Sai; dùng `forEachOrdered` khi cần bảo đảm thứ tự action.
5. **“forEachOrdered làm mọi upstream tuần tự.”** Sai; nó chỉ ràng buộc thứ tự của terminal action.
6. **“findAny() luôn trả phần tử đầu.”** Sai; kết quả được phép là phần tử bất kỳ.
7. **“Dùng một ArrayList ngoài lambda để thu thập song song.”** Nguy hiểm vì nhiều thread sửa cùng collection.
8. **“Chỉ cần dùng synchronized là có tốc độ song song.”** Không; khóa có thể loại bỏ lợi ích chia việc.
9. **“Bất kỳ phép reduce nào cũng dùng được với parallel.”** Sai; cần tính kết hợp và identity hợp lệ.
10. **“Một Stream có thể chạy terminal nhiều lần.”** Sai; hãy tạo pipeline mới mỗi lần.
11. **“peek phù hợp để ghi nhận mọi phần tử chắc chắn được xử lý.”** Sai; tối ưu hóa và short-circuit có thể làm hành vi quan sát được khác mong đợi.
12. **“Số thực sẽ luôn cho bit kết quả y hệt tuần tự.”** Không bảo đảm với cách nhóm phép tính khác nhau.
13. **“unordered() xáo thứ tự ngẫu nhiên.”** Sai; nó chỉ loại yêu cầu bảo toàn encounter order.
14. **“Có nhiều core nghĩa là luôn nên parallel.”** Sai; nguồn khó chia, phép xử lý nhẹ hoặc pool bị bận có thể khiến hiệu năng kém hơn.
15. **“Chế độ song song thay thế thiết kế concurrency.”** Sai; không cung cấp transaction, retry, backpressure hay thread lifecycle rõ ràng.

## 15. Tự kiểm tra

**Câu 1.** Hai cách tạo Stream song song từ `List<Integer> values` là gì?

**Đáp án:** `values.parallelStream()` và `values.stream().parallel()`.

**Câu 2.** `values.parallelStream().map(x -> x * 2).toList()` có giữ encounter order của List không?

**Có.** Nếu nguồn List có encounter order, kết quả `toList()` giữ thứ tự ấy, dù các bước tính toán có thể thực hiện song song.

**Câu 3.** `forEach` hay `forEachOrdered` phù hợp khi muốn in đúng thứ tự phần tử của một List?

**Đáp án:** `forEachOrdered`. Chọn `forEach` khi thứ tự action không cần bảo đảm.

**Câu 4.** Vì sao `reduce(0, (a,b) -> a-b)` không nên dùng để mong kết quả như nhau giữa stream tuần tự và song song?

Vì phép trừ **không kết hợp được**; việc chia dữ liệu và gộp lại có thể thay đổi kết quả.

**Câu 5.** Có an toàn không nếu viết `new ArrayList<>()` ở bên ngoài rồi `parallelStream().forEach(list::add)`?

**Không.** `ArrayList` không an toàn cho nhiều thread đồng thời cập nhật. Dùng `toList()` hoặc collector thích hợp.

**Câu 6.** `parallel().sequential()` có tạo hai pha đầu song song rồi cuối tuần tự khi terminal chạy không?

**Không.** Các thao tác này đặt chế độ pipeline; chế độ cuối cùng là tuần tự, không phải “cắt” pipeline thành hai nửa thực thi riêng biệt.

**Câu 7.** Khi nào nên ưu tiên `findAny()` hơn `findFirst()`?

Khi chỉ cần **một phần tử bất kỳ** thỏa điều kiện, không cần bảo đảm phần tử đầu tiên; đặc biệt trong một pipeline song song có thứ tự.

**Câu 8.** Muốn biết parallel có thực sự có lợi cho chương trình của mình, nên làm gì?

Đảm bảo logic đúng và không có shared mutable state không kiểm soát, sau đó benchmark trên workload thực tế (ví dụ với JMH); không suy luận từ tên `parallel`.

**Ghi nhớ:** **Stream tuần tự** là lựa chọn đơn giản, dễ đoán và thường nên dùng mặc định. **Stream song song** phù hợp khi công việc độc lập, chia được, đủ lớn và được giảm/gộp bằng các phép toán hợp lệ. Đừng đánh đổi tính đúng đắn, encounter order cần thiết hoặc sự an toàn của dữ liệu để lấy một lời hứa tốc độ chưa được đo kiểm.
