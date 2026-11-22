# Lấy tiền tố thỏa điều kiện bằng takeWhile

## 1. Bài toán: lấy dữ liệu từ đầu cho đến khi điều kiện không còn đúng

Trong Java Stream API, `filter` thường được dùng để giữ **mọi phần tử** thỏa một điều kiện. Tuy nhiên, có những bài toán chỉ cần một đoạn dữ liệu liên tiếp **từ đầu nguồn**, và phải dừng ngay khi gặp phần tử đầu tiên không thỏa:

- Lấy các bản ghi thời gian trước 09:00 trong một nhật ký **đã sắp xếp tăng dần theo thời gian**.
- Đọc những dòng đầu của tệp cho đến dòng trống đầu tiên.
- Sinh những số liên tiếp cho đến khi đạt một ngưỡng.
- Lấy các mẫu đo đầu tiên trong một chuỗi cho đến khi xuất hiện tín hiệu vượt giới hạn.

Thao tác `takeWhile` được thiết kế để diễn tả yêu cầu này. Nó thuộc nhóm **thứ tự, loại trùng và cắt lát** (*ordering, deduplication and slicing*) vì kết quả phụ thuộc vào thứ tự gặp phần tử (*encounter order*).

Ví dụ mở đầu:

```java
import java.util.List;

List<Integer> measurements = List.of(2, 4, 6, 11, 3, 5);

List<Integer> prefix = measurements.stream()
        .takeWhile(n -> n < 10)
        .toList();

System.out.println(prefix); // [2, 4, 6]
```

Số `11` không thỏa điều kiện `n < 10`, vì vậy `takeWhile` dừng lấy phần tử tại đó. Các số `3` và `5` đứng sau `11` dù cũng nhỏ hơn 10 vẫn **không xuất hiện** trong kết quả.

**Mục tiêu sau bài học:** hiểu hợp đồng của `takeWhile`; phân biệt với `filter`, `dropWhile` và `limit`; sử dụng đúng trên Stream có và không có thứ tự; kết hợp với `map`, `sorted` và `collect`; nhận diện giới hạn của pipeline lazy, Stream vô hạn và xử lý song song.

> `takeWhile` được giới thiệu từ **Java 9** cho `Stream<T>`, `IntStream`, `LongStream` và `DoubleStream`. Các đoạn mã dùng `Stream.toList()` cần **Java 16+**; nếu chạy Java 9–15, có thể dùng `collect(Collectors.toList())` với Stream đối tượng.

## 2. Hợp đồng chính xác của takeWhile

Chữ ký trên `Stream<T>`:

```java
Stream<T> takeWhile(Predicate<? super T> predicate)
```

`takeWhile` là **thao tác trung gian có trạng thái và hỗ trợ dừng sớm** (*stateful short-circuiting intermediate operation*). Nó trả về một Stream mới có cùng kiểu phần tử; không tự thu thập kết quả hay sửa nguồn.

Với nguồn có encounter order, kết quả là **tiền tố dài nhất** mà mọi phần tử trong đó đều thỏa `predicate`.

Giả sử nguồn có thứ tự `x1, x2, ..., xn` và `k` là vị trí đầu tiên có `predicate(xk) == false`. Kết quả là các phần tử `x1, ..., x(k-1)`. Nếu tất cả phần tử đều thỏa, toàn bộ nguồn được giữ lại. Nếu ngay phần tử đầu tiên không thỏa, kết quả rỗng.

```text
Nguồn (theo encounter order):

 [2] -> [4] -> [6] -> [11] -> [3] -> [5]
   ✓      ✓      ✓       ✗      ✓      ✓
   |      |      |       |
   +------+------+-------+--- ranh giới dừng
   |      |      |
   v      v      v
   [2,    4,     6]              <- Stream sau takeWhile(n < 10)

Mọi phần tử kể từ phần tử sai đầu tiên đều bị loại khỏi tiền tố.
```

Điểm cần nhớ là **điều kiện không được kiểm tra để tìm mọi phần tử phù hợp trên toàn bộ nguồn như `filter`**. Với nguồn có thứ tự, `takeWhile` quan tâm đến một ranh giới bắt đầu từ đầu dãy.

### Ba trường hợp biên

```java
List<Integer> values = List.of(1, 3, 5);

System.out.println(values.stream()
        .takeWhile(n -> n < 10).toList()); // [1, 3, 5]: tất cả đều đạt

System.out.println(values.stream()
        .takeWhile(n -> n < 0).toList());  // []: phần tử đầu đã sai

System.out.println(values.stream()
        .takeWhile(n -> n < 4).toList());  // [1, 3]: dừng ở 5
```

Phần tử **đầu tiên làm predicate trả về `false` không nằm trong kết quả**. Nếu nghiệp vụ cần bao gồm cả phần tử đánh dấu kết thúc, `takeWhile` đơn thuần không diễn đạt trực tiếp yêu cầu đó; cân nhắc vòng lặp có điều kiện rõ ràng hoặc bộ xử lý có trạng thái được thiết kế riêng.

## 3. takeWhile khác filter, dropWhile và limit

Các thao tác đều có thể làm Stream ngắn lại, nhưng chúng cắt dữ liệu theo những tiêu chí khác nhau.

```java
List<Integer> data = List.of(3, 5, 9, 2, 11, 4);

List<Integer> take = data.stream()
        .takeWhile(n -> n < 8)
        .toList();

List<Integer> filtered = data.stream()
        .filter(n -> n < 8)
        .toList();

List<Integer> dropped = data.stream()
        .dropWhile(n -> n < 8)
        .toList();

List<Integer> limited = data.stream()
        .limit(2)
        .toList();

System.out.println(take);     // [3, 5]
System.out.println(filtered); // [3, 5, 2, 4]
System.out.println(dropped);  // [9, 2, 11, 4]
System.out.println(limited);  // [3, 5]
```

| Thao tác | Quy tắc với Stream có thứ tự | Trong ví dụ |
| --- | --- | --- |
| `takeWhile(p)` | Giữ các phần tử **liên tiếp từ đầu** khi `p` còn đúng; dừng ở phần tử sai đầu tiên. | `[3, 5]` |
| `filter(p)` | Giữ **mọi phần tử** thỏa `p` dù nằm trước hay sau phần tử không thỏa. | `[3, 5, 2, 4]` |
| `dropWhile(p)` | Bỏ tiền tố dài nhất thỏa `p`, sau đó giữ toàn bộ phần còn lại. | `[9, 2, 11, 4]` |
| `limit(n)` | Lấy tối đa `n` phần tử đầu tiên, không dùng predicate. | `[3, 5]` |

Trong một dãy có thứ tự cố định và predicate không trạng thái, `takeWhile(p)` và `dropWhile(p)` tạo ra hai phần liên tiếp tại cùng ranh giới. Đừng nhầm `dropWhile` với phép đảo predicate của `takeWhile`: `dropWhile` vẫn lấy cả phần tử thỏa điều kiện nằm **sau** ranh giới.

Mặc dù `takeWhile` và `limit` trong ví dụ đều cho `[3, 5]`, một bên giới hạn bằng **điều kiện nội dung**, bên kia bằng **số lượng**. Khi dữ liệu thay đổi, hai kết quả không còn nhất thiết giống nhau.

## 4. Encounter order quyết định ý nghĩa của tiền tố

### Nguồn có thứ tự

`List`, mảng, `IntStream.range` và các nguồn có encounter order xác định cho phép nói rõ phần tử nào là "đầu tiên".

```java
List<String> tokens = List.of("header", "row-1", "row-2", "END", "row-3");

List<String> beforeEnd = tokens.stream()
        .takeWhile(token -> !token.equals("END"))
        .toList();

System.out.println(beforeEnd); // [header, row-1, row-2]
```

Nếu thứ tự biểu diễn ý nghĩa nghiệp vụ (nhật ký theo thời gian, bước quy trình, dòng trong tệp), hãy bảo đảm nguồn thực sự giữ đúng thứ tự đó.

### Nguồn không có thứ tự

Một nguồn như `HashSet` hoặc một pipeline đã gọi `unordered()` không cam kết encounter order. Khi **chỉ một phần** dữ liệu thỏa predicate, `takeWhile` được phép trả về **bất kỳ tập con nào** của các phần tử thỏa, kể cả tập rỗng. Vì không có "đầu" được định nghĩa, không thể dùng nó để lấy một tiền tố xác định.

```java
Set<Integer> values = new HashSet<>(List.of(1, 2, 3, 9, 10));

List<Integer> result = values.stream()
        .takeWhile(n -> n < 5)
        .toList();

// Không được giả định result == [1, 2, 3].
// Với nguồn unordered, kết quả là một tập con hợp lệ
// của các số thỏa n < 5, thứ tự cũng không được bảo đảm.
```

Trong trường hợp **mọi phần tử đều thỏa**, kết quả gồm toàn bộ phần tử; nếu **không phần tử nào thỏa**, kết quả rỗng. Tính không xác định của việc chọn tập con là điểm quan trọng khi có cả phần tử thỏa và không thỏa.

Nếu cần **mọi** phần tử thỏa từ một tập không có thứ tự, `filter` mới biểu đạt đúng yêu cầu. Nếu cần một tiền tố xác định, trước tiên phải xác lập thứ tự theo nghiệp vụ:

```java
List<Integer> orderedPrefix = values.stream()
        .sorted()
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(orderedPrefix); // [1, 2, 3]
```

`sorted()` xác lập encounter order theo phép so sánh cho Stream kết quả, nhưng đây là thao tác **có trạng thái**: nó thường cần quan sát và lưu trữ toàn bộ dữ liệu hữu hạn trước khi phát ra phần tử đã sắp xếp. Vì vậy, việc thêm `sorted` có thể đánh đổi khả năng dừng đọc sớm của nguồn để lấy tính đúng đắn về thứ tự.

## 5. Đặt takeWhile ở đâu trong chuỗi thao tác?

Thứ tự các thao tác Stream có thể làm thay đổi **ranh giới tiền tố**, vì mỗi thao tác trung gian tạo đầu vào cho bước sau.

### filter trước và sau takeWhile

```java
List<Integer> values = List.of(2, 7, 4, 1);

List<Integer> first = values.stream()
        .takeWhile(n -> n < 5)
        .filter(n -> n % 2 == 0)
        .toList();

List<Integer> second = values.stream()
        .filter(n -> n % 2 == 0)
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(first);  // [2]
System.out.println(second); // [2, 4]
```

Ở `first`, `7` kết thúc tiền tố ngay sau `2`. Ở `second`, `filter` loại `7` trước, khiến `4` trở thành phần tử tiếp theo mà `takeWhile` nhìn thấy. Vì vậy, **không tự ý hoán đổi thứ tự hai thao tác** khi điều kiện có ý nghĩa nghiệp vụ.

### map trước takeWhile

Khi ranh giới được xác định bằng **giá trị sau chuẩn hóa**, đặt `map` trước:

```java
List<String> raw = List.of("  An  ", " Bình ", "   ", " Chi ");

List<String> namesBeforeBlank = raw.stream()
        .map(String::strip)
        .takeWhile(name -> !name.isEmpty())
        .toList();

System.out.println(namesBeforeBlank); // [An, Bình]
```

Nếu yêu cầu dựa vào dữ liệu gốc và phép ánh xạ tốn kém, đặt `takeWhile` trước `map` có thể tiết kiệm việc biến đổi các phần tử ngoài tiền tố:

```java
List<String> labels = List.of(1, 2, 3, 20, 4).stream()
        .takeWhile(n -> n < 10)
        .map(n -> "Mã-" + n)
        .toList();

System.out.println(labels); // [Mã-1, Mã-2, Mã-3]
```

### sorted trước hoặc sau takeWhile

```java
List<Integer> samples = List.of(4, 1, 7, 2, 3);

List<Integer> a = samples.stream()
        .takeWhile(n -> n < 5)
        .sorted()
        .toList();

List<Integer> b = samples.stream()
        .sorted()
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(a); // [1, 4]
System.out.println(b); // [1, 2, 3, 4]
```

Với `a`, tiền tố dừng ở `7` trước khi sắp xếp. Với `b`, toàn bộ dãy được sắp xếp rồi mới xét ranh giới. Đây là hai câu hỏi nghiệp vụ khác nhau.

## 6. Lazy, short-circuiting và số lần gọi predicate

`takeWhile` thuộc pipeline xử lý **lazy**. Việc tạo pipeline không duyệt toàn bộ dữ liệu:

```java
Stream<Integer> pipeline = List.of(2, 4, 9, 1).stream()
        .takeWhile(n -> n < 5);

// Chưa có terminal operation, nên chưa thu được danh sách kết quả.
List<Integer> result = pipeline.toList();
System.out.println(result); // [2, 4]
```

Khi terminal operation yêu cầu các phần tử, `takeWhile` có thể ngừng phát phần tử từ nguồn sau ranh giới thay vì duyệt hết toàn bộ danh sách. Đây là lợi ích của **short-circuiting** đối với nguồn có thứ tự và pipeline phù hợp.

Tuy nhiên, không được biến predicate thành nơi đặt tác dụng phụ bắt buộc:

```java
List<Integer> result = List.of(2, 4, 9, 1).stream()
        .takeWhile(n -> {
            System.out.println("Kiểm tra: " + n); // Chỉ nên dùng để quan sát/debug
            return n < 5;
        })
        .toList();
```

Một pipeline tuần tự đơn giản như trên thường kiểm tra các giá trị `2`, `4` và `9`, nhưng ứng dụng không nên dựa vào một **số lần gọi predicate chính xác**. Tối ưu của Stream, thao tác kết thúc và xử lý song song có thể làm thay đổi cách đánh giá các phần tử. Hợp đồng cần dựa vào **kết quả của pipeline**, không dựa vào số lượt in log hay hiệu ứng ngoài.

Predicate được cung cấp phải **không can thiệp vào nguồn** (*non-interfering*) và **không phụ thuộc trạng thái thay đổi giữa các phần tử** (*stateless*). Bản thân thao tác `takeWhile` có trạng thái nội bộ để xác định ranh giới; đó là trạng thái do thư viện quản lý, khác với việc lambda tự dùng biến đếm chia sẻ.

## 7. Stream vô hạn: takeWhile xác lập điểm dừng theo điều kiện

Một số Stream là **vô hạn**, ví dụ `IntStream.iterate` không có điều kiện kết thúc. `takeWhile` đặc biệt hữu ích khi biết điều kiện dừng theo dữ liệu:

```java
import java.util.stream.IntStream;

List<Integer> firstSquaresBelow100 = IntStream.iterate(1, n -> n + 1)
        .map(n -> n * n)
        .takeWhile(square -> square < 100)
        .boxed()
        .toList();

System.out.println(firstSquaresBelow100);
// [1, 4, 9, 16, 25, 36, 49, 64, 81]
```

Nguồn sinh `1, 2, 3, ...`, bước `map` tạo bình phương, và `takeWhile` dừng lấy dữ liệu trước giá trị `100`. Phần tử đầu tiên làm điều kiện sai **không được đưa vào kết quả**.

Java 9 còn bổ sung overload ba tham số của `iterate`, cho phép gắn điều kiện kết thúc ngay ở **nguồn**:

```java
List<Integer> numbers = IntStream.iterate(
                1,
                n -> n <= 5,
                n -> n + 1
        )
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

Lựa chọn dựa trên vị trí điều kiện: nếu muốn sinh dãy hữu hạn theo điều kiện nguồn, overload `iterate(seed, hasNext, next)` rất rõ ràng; nếu cần xét **giá trị sau các bước ánh xạ** hoặc sau một nguồn khác, `takeWhile` phù hợp.

**Chú ý:** với Stream vô hạn, nếu predicate **không bao giờ trả về `false`** và terminal operation cần tiêu thụ toàn bộ kết quả (như `toList`), thao tác đó có thể không bao giờ kết thúc. Đừng giả định mọi pipeline có `takeWhile` đều hữu hạn.

## 8. Primitive stream và xử lý số liệu

Không cần boxing các số trước khi dùng `takeWhile`. Các stream chuyên biệt có cùng phương thức:

```java
int sumBeforeThreshold = IntStream.of(3, 5, 7, 20, 2)
        .takeWhile(n -> n < 10)
        .sum();

System.out.println(sumBeforeThreshold); // 15
```

Tương tự, `LongStream.takeWhile(LongPredicate)` và `DoubleStream.takeWhile(DoublePredicate)` xử lý dữ liệu số nguyên dài hoặc số thực.

Ví dụ cắt một dãy đo rồi tính trung bình:

```java
double average = java.util.stream.DoubleStream
        .of(2.5, 3.0, 3.5, 9.0, 2.0)
        .takeWhile(value -> value < 8.0)
        .average()
        .orElse(0.0);

System.out.println(average); // 3.0
```

`average()` trả về `OptionalDouble` vì dữ liệu sau cắt lát có thể rỗng. Cần chọn giá trị mặc định hoặc xử lý trường hợp không có mẫu hợp lệ theo nghiệp vụ.

## 9. null, ngoại lệ và các trường hợp dữ liệu thiếu

Với Stream chứa `null`, cách viết predicate quyết định hành vi:

```java
import java.util.Arrays;
import java.util.Objects;

List<String> rows = Arrays.asList("header", "row-1", null, "row-2");

List<String> beforeNull = rows.stream()
        .takeWhile(Objects::nonNull)
        .toList();

System.out.println(beforeNull); // [header, row-1]
```

Ở đây `null` được dùng như **dấu mốc kết thúc**. Nếu dùng `filter(Objects::nonNull)` thì `row-2` vẫn được giữ lại, vì `filter` chỉ bỏ `null` và tiếp tục xét những phần tử phía sau.

Ngược lại, với predicate như `text -> !text.isBlank()`, gặp `null` sẽ ném `NullPointerException`. Hãy quyết định rõ `null` có nghĩa là "dừng", "bỏ qua" hay "dữ liệu lỗi" rồi chọn chiến lược tương ứng.

Predicate gây ngoại lệ trong quá trình duyệt sẽ khiến terminal operation thất bại; `takeWhile` không tự bắt ngoại lệ hoặc tiếp tục bằng cách bỏ qua phần tử lỗi.

## 10. Ví dụ đọc tệp đến dòng trống đầu tiên

Giả sử một tệp văn bản có phần tiêu đề và dữ liệu, kết thúc phần cần đọc bằng một dòng trống. `Files.lines` cung cấp Stream theo thứ tự dòng tệp, phù hợp với `takeWhile`:

```text
SACH,3
BUT,8
VO,2

GHI_CHU,khong_xu_ly
```

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("inventory.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstSection = lines
            .takeWhile(line -> !line.isBlank())
            .toList();

    System.out.println(firstSection);
    // [SACH,3, BUT,8, VO,2]
} catch (IOException exception) {
    System.err.println("Không đọc được tệp: " + exception.getMessage());
}
```

Đoạn mã minh họa nằm trong một phương thức có thể xử lý ngoại lệ. `isBlank()` có từ Java 11; nó kiểm tra cả các chuỗi chỉ gồm khoảng trắng. `try-with-resources` bảo đảm Stream và tài nguyên tệp được đóng sau khi sử dụng, kể cả khi việc duyệt dừng sớm. Các lỗi I/O xảy ra **trong quá trình duyệt** có thể được bọc thành `UncheckedIOException` và cũng cần được xử lý nếu ứng dụng muốn phục hồi.

Nếu yêu cầu là **bỏ qua mọi dòng trống nhưng tiếp tục đọc phần sau**, hãy dùng `filter(line -> !line.isBlank())`. Việc chọn `takeWhile` có nghĩa là dòng trống đầu tiên mang ý nghĩa **kết thúc phân đoạn**.

## 11. Ví dụ nghiệp vụ hoàn chỉnh: thống kê giao dịch trước mốc giờ

Giả sử dữ liệu giao dịch đã được ghi theo thứ tự thời gian tăng dần. Cần thống kê tổng số lượng theo khách hàng từ đầu danh sách **cho đến trước 09:00**, đồng thời giữ lại các giao dịch thuộc tiền tố đó để kiểm tra.

Ví dụ hoàn chỉnh sau dùng Java 17+:

```java
import java.time.LocalTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TakeWhileDemo {
    record Transaction(
            String id,
            LocalTime time,
            String customer,
            int quantity
    ) {}

    public static void main(String[] args) {
        List<Transaction> chronological = List.of(
                new Transaction("T01", LocalTime.of(8, 10), "AN", 3),
                new Transaction("T02", LocalTime.of(8, 40), "BINH", 5),
                new Transaction("T03", LocalTime.of(8, 50), "AN", 2),
                new Transaction("T04", LocalTime.of(9, 0), "CHI", 7),
                new Transaction("T05", LocalTime.of(9, 15), "BINH", 4)
        );

        LocalTime cutoff = LocalTime.of(9, 0);

        List<Transaction> beforeCutoff = chronological.stream()
                .takeWhile(tx -> tx.time().isBefore(cutoff))
                .toList();

        Map<String, Integer> quantityByCustomer = beforeCutoff.stream()
                .collect(Collectors.groupingBy(
                        Transaction::customer,
                        LinkedHashMap::new,
                        Collectors.summingInt(Transaction::quantity)
                ));

        System.out.println(
                beforeCutoff.stream().map(Transaction::id).toList()
        ); // [T01, T02, T03]

        System.out.println(quantityByCustomer);
        // {AN=5, BINH=5}
    }
}
```

Phân tích:

1. `chronological` có encounter order đúng với thời gian tăng dần.
2. `takeWhile(tx -> tx.time().isBefore(cutoff))` giữ `T01`, `T02`, `T03` và dừng trước `T04` lúc 09:00.
3. `toList()` tạo danh sách mới; nguồn không bị thay đổi.
4. `groupingBy` và `summingInt` tổng hợp trên kết quả đã cắt lát, với `LinkedHashMap` giữ thứ tự lần đầu xuất hiện của các nhóm trong Stream tuần tự.

**Điều kiện tiên quyết quan trọng:** nếu danh sách **không được sắp theo thời gian**, một giao dịch có giờ trước 09:00 nhưng nằm sau bản ghi lúc 09:00 sẽ bị loại khỏi tiền tố. Khi muốn lấy **mọi giao dịch trước 09:00 bất kể vị trí**, dùng:

```java
List<Transaction> allBeforeCutoff = chronological.stream()
        .filter(tx -> tx.time().isBefore(cutoff))
        .toList();
```

Nếu nghiệp vụ cần tiền tố sau khi **xếp lại** theo thời gian, có thể sắp trước khi cắt:

```java
List<Transaction> sortedPrefix = chronological.stream()
        .sorted(java.util.Comparator
                .comparing(Transaction::time)
                .thenComparing(Transaction::id))
        .takeWhile(tx -> tx.time().isBefore(cutoff))
        .toList();
```

`sorted` cần xử lý tập dữ liệu hữu hạn trước khi trả ra tiền tố; vì vậy, đừng dùng cách này với một nguồn vô hạn chưa được giới hạn. Với nhật ký đã có thứ tự đúng, `takeWhile` trực tiếp có thể tiết kiệm nhiều thao tác hơn.

## 12. Hiệu năng, song song và hợp đồng về trạng thái

### Stream tuần tự có thứ tự

Đây là trường hợp tự nhiên nhất của `takeWhile`: với pipeline phù hợp, việc cắt ở phần tử sai đầu tiên có thể tránh phải xử lý phần còn lại của nguồn. Hiệu quả thực tế còn phụ thuộc các bước trước nó: `sorted`, một số phép gom trạng thái hoặc nguồn khó chia tách có thể yêu cầu công việc bổ sung.

### Stream song song có thứ tự

`takeWhile` vẫn phải cung cấp **tiền tố dài nhất theo encounter order**. Tuy nhiên, việc phối hợp giữa nhiều nhánh để nhận biết ranh giới có thể tốn chi phí đáng kể. Không thể giả định cứ dùng `parallelStream()` là nhanh hơn:

```java
List<Integer> original = List.of(1, 2, 3, 9, 1, 2);

List<Integer> prefix = original.parallelStream()
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(prefix); // [1, 2, 3]
```

Kết quả có thứ tự vẫn là `[1, 2, 3]`. Điều **không được bảo đảm** là trình tự thực thi predicate trên các thread, số lượt đánh giá hoặc lợi ích tốc độ so với tuần tự.

### Khi có thể bỏ encounter order

Nếu yêu cầu **không cần tiền tố xác định**, việc gọi `unordered()` có thể giúp giảm một số chi phí phối hợp:

```java
List<Integer> subset = original.parallelStream()
        .unordered()
        .takeWhile(n -> n < 5)
        .toList();
```

Nhưng ngữ nghĩa đã đổi: `subset` có thể là **bất kỳ tập con nào** của các phần tử thỏa `n < 5`, kể cả rỗng, và không có thứ tự cam kết. Không dùng cách này để tối ưu bài toán buộc phải lấy "đến phần tử đầu tiên sai" theo thứ tự nguồn. Khi cần **tất cả** phần tử thỏa từ nguồn unordered, `filter` phù hợp hơn.

### Non-interference và stateless predicate

`takeWhile` không hợp thức hóa việc sửa nguồn ngay trong predicate:

```java
List<Integer> mutable = new java.util.ArrayList<>(List.of(1, 2, 3, 10));

// SAI: thay đổi chính nguồn khi đang duyệt.
List<Integer> invalid = mutable.stream()
        .takeWhile(n -> {
            if (n == 2) {
                mutable.add(99);
            }
            return n < 5;
        })
        .toList();
```

Cách viết này vi phạm **non-interference**; có thể xuất hiện `ConcurrentModificationException` hoặc hành vi không thể dự đoán theo nguồn. Hãy dùng predicate chỉ đọc dữ liệu, tạo kết quả từ Stream, rồi cập nhật nguồn trong một giai đoạn riêng sau terminal operation.

Tương tự, tránh predicate phụ thuộc biến đếm dùng chung:

```java
java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

// Không nên: ranh giới phụ thuộc số lần/lịch thực thi predicate.
List<Integer> unstable = original.parallelStream()
        .takeWhile(n -> calls.incrementAndGet() <= 3)
        .toList();
```

`AtomicInteger` chỉ giúp cập nhật số đếm theo cách nguyên tử; nó **không đảm bảo** phần tử nào được xét trước trong pipeline song song. Nếu mục tiêu là lấy ba phần tử đầu tiên từ nguồn có thứ tự, dùng `limit(3)`.

## 13. Dấu hiệu lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Kết quả thiếu phần tử thỏa nằm ở giữa/cuối nguồn | `takeWhile` dừng ở phần tử không thỏa đầu tiên. | Dùng `filter` nếu cần mọi phần tử thỏa. |
| Kết quả khác nhau từ `HashSet` | Nguồn không có encounter order. | Dùng `filter` hoặc xác lập thứ tự với `sorted`. |
| Dừng sớm hơn dự kiến | Đầu vào chưa sắp theo tiêu chí của predicate. | Sắp dữ liệu trước, hoặc thay bằng `filter` tùy ý nghĩa. |
| Đã lọc trước, tiền tố dài hơn bất ngờ | `filter` loại phần tử gây dừng trước khi `takeWhile` thấy nó. | Xét lại thứ tự các bước. |
| Bị `NullPointerException` trong predicate | Predicate gọi phương thức trên phần tử `null`. | Quy định rõ `null` là mốc dừng, bỏ qua hay lỗi. |
| Pipeline trên nguồn vô hạn chạy mãi | Predicate luôn đúng, terminal operation đòi duyệt hết. | Đưa vào điều kiện dừng chắc chắn hoặc giới hạn hữu hạn. |
| `parallelStream` chậm hơn | Chi phí phối hợp giữ tiền tố theo thứ tự. | Đo hiệu năng, cân nhắc Stream tuần tự. |
| Dùng `unordered()` rồi mất kết quả ổn định | Đã bỏ cam kết encounter order. | Giữ thứ tự nếu yêu cầu tiền tố xác định. |
| Tác dụng phụ chạy số lần khó đoán | Predicate dùng biến trạng thái/log để điều khiển nghiệp vụ. | Viết predicate stateless; dùng `limit` khi giới hạn số lượng. |

## 14. Bài tập thực hành

Cho danh sách nhiệt độ theo thứ tự đo:

```java
List<Double> temperatures = List.of(22.5, 24.0, 26.5, 32.0, 23.0, 25.0);
```

**Yêu cầu:**

1. Dùng `takeWhile` lấy các nhiệt độ liên tiếp từ đầu **nhỏ hơn 30°C**.
2. Dùng `filter` lấy **tất cả** nhiệt độ nhỏ hơn 30°C.
3. Dùng `dropWhile` lấy phần dữ liệu kể từ nhiệt độ **đầu tiên từ 30°C trở lên**.
4. Tính trung bình của tiền tố ở câu 1 với `mapToDouble`.
5. Giải thích vì sao hai giá trị `23.0` và `25.0` không xuất hiện trong câu 1.

**Lời giải tham khảo:**

```java
List<Double> beforeFirstHigh = temperatures.stream()
        .takeWhile(t -> t < 30.0)
        .toList();
// [22.5, 24.0, 26.5]

List<Double> allBelow30 = temperatures.stream()
        .filter(t -> t < 30.0)
        .toList();
// [22.5, 24.0, 26.5, 23.0, 25.0]

List<Double> fromFirstHigh = temperatures.stream()
        .dropWhile(t -> t < 30.0)
        .toList();
// [32.0, 23.0, 25.0]

double average = temperatures.stream()
        .takeWhile(t -> t < 30.0)
        .mapToDouble(Double::doubleValue)
        .average()
        .orElse(Double.NaN);

System.out.println(average); // 24.333333333333332 (xấp xỉ 24.33)
```

**Tự mở rộng:** Thêm một nhiệt độ `21.0` ở **đầu danh sách**; thêm cùng nhiệt độ ấy ở **cuối danh sách**. So sánh tiền tố sau mỗi thay đổi. Bài tập nhấn mạnh rằng kết quả `takeWhile` bị chi phối bởi **vị trí của phần tử đầu tiên làm predicate sai**, không chỉ bởi giá trị từng phần tử.

## Ghi nhớ

`takeWhile(predicate)` lấy **tiền tố dài nhất thỏa điều kiện** từ Stream có encounter order; phần tử đầu tiên không thỏa và mọi phần tử phía sau đều không xuất hiện. `filter` chọn mọi phần tử thỏa, `dropWhile` bỏ tiền tố thỏa, còn `limit` giới hạn theo số lượng. Nếu thứ tự nguồn không được xác định, `takeWhile` không bảo đảm tiền tố hay tập phần tử cố định. Đây là thao tác trung gian lazy, có trạng thái và hỗ trợ dừng sớm; predicate nên stateless, không can thiệp nguồn. Dùng trên dữ liệu đã sắp đúng theo ranh giới nghiệp vụ, cân nhắc nguồn vô hạn và chi phí của xử lý song song trước khi áp dụng.
