# `limit()` và `skip()` trong Java Stream

`limit(long maxSize)` và `skip(long n)` là hai **intermediate operation** dùng để chọn một đoạn phần tử của stream. Cả hai được khai báo trên `java.util.stream.Stream` (và có các phiên bản tương ứng trên `IntStream`, `LongStream`, `DoubleStream`). Chúng thường xuất hiện trong bài toán **lấy N phần tử đầu**, **bỏ qua N phần tử đầu**, **phân trang dữ liệu** hoặc **giới hạn một nguồn sinh dữ liệu liên tục**.

Điểm quan trọng là: “đầu tiên” được hiểu theo **encounter order** nếu stream có thứ tự gặp phần tử; kết quả còn phụ thuộc vào vị trí đặt `limit`/`skip` trong pipeline và cách stream được thực thi.

## 1. Hiểu chính xác hai phương thức

| Phương thức | Ý nghĩa | Số lượng phần tử có thể trả ra | Giá trị trả về |
| --- | --- | --- | --- |
| `limit(n)` | Giữ tối đa `n` phần tử đầu của stream tại vị trí thao tác | Từ 0 đến `n` (nếu upstream kết thúc) | Một stream mới chứa tối đa `n` phần tử |
| `skip(n)` | Bỏ qua `n` phần tử đầu của stream tại vị trí thao tác, lấy phần còn lại | 0 nếu nguồn không có đủ phần tử; nếu nguồn hữu hạn, tối đa `size - n` | Một stream mới đã bỏ qua prefix |

Cả hai có tham số kiểu `long`, phải **không âm**; truyền số âm sẽ ném `IllegalArgumentException`. `limit(0)` tạo stream rỗng, còn `skip(0)` giữ toàn bộ các phần tử về mặt logic. Giá trị `n` có thể lớn hơn số phần tử nguồn; `skip` khi đó trả về stream rỗng, còn `limit` chỉ trả về số phần tử thực sự tồn tại.

Ví dụ trực quan với stream có thứ tự `[10, 20, 30, 40, 50]`:

```text
Đầu vào:      10   20   30   40   50
limit(3):     10   20   30
skip(2):                30   40   50
skip(2)
  .limit(2):             30   40
```

`limit` và `skip` **không sửa collection nguồn**. Chúng tạo các bước xử lý của pipeline; việc tiêu thụ phần tử chỉ bắt đầu khi gọi terminal operation như `toList()`, `count()` hoặc `forEach()`. Một stream đã đi qua terminal operation không thể dùng lại.

### Hai thao tác là stateful intermediate operations

Để biết khi nào đã lấy đủ `n` hoặc đã bỏ qua đủ `n` phần tử, hệ thống phải theo dõi số lượng phần tử đã đi qua một đoạn pipeline. Vì vậy chúng được xem là các **stateful intermediate operations**. Điều này quan trọng với stream song song, đặc biệt khi phải giữ encounter order.

`limit` còn là một thao tác *short-circuiting*: ở nhiều pipeline, nó có thể khiến việc tiêu thụ nguồn dừng sau khi có đủ kết quả. Tuy nhiên không nên suy luận rằng mọi callback upstream luôn được gọi đúng `n` lần: `filter`, `distinct`, hoạt động song song và các tối ưu hóa có thể ảnh hưởng số lần đánh giá.

## 2. Ví dụ Java 17+ chạy được

Tạo tệp `LimitSkipDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class LimitSkipDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6, 7, 8);

        System.out.println("first3 = " + numbers.stream()
                .limit(3)
                .toList());

        System.out.println("after5 = " + numbers.stream()
                .skip(5)
                .toList());

        System.out.println("page = " + numbers.stream()
                .skip(2)
                .limit(3)
                .toList());

        System.out.println("evenPage = " + numbers.stream()
                .filter(n -> n % 2 == 0)
                .skip(1)
                .limit(2)
                .toList());

        System.out.println("empty = " + numbers.stream()
                .limit(0)
                .toList());

        System.out.println("tooFar = " + numbers.stream()
                .skip(100)
                .toList());

        System.out.println("infiniteSlice = " + Stream.iterate(1, n -> n + 1)
                .skip(5)
                .limit(3)
                .toList());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac LimitSkipDemo.java
java LimitSkipDemo
```

Stdout chính xác:

```text
first3 = [1, 2, 3]
after5 = [6, 7, 8]
page = [3, 4, 5]
evenPage = [4, 6]
empty = []
tooFar = []
infiniteSlice = [6, 7, 8]
```

Diễn giải:

1. `limit(3)` lấy ba phần tử đầu tiên theo thứ tự list: `1, 2, 3`.
2. `skip(5)` bỏ qua `1, 2, 3, 4, 5`, giữ `6, 7, 8`.
3. `skip(2).limit(3)` bỏ hai phần tử đầu, rồi chỉ lấy tối đa ba phần tử tiếp theo.
4. `filter` giữ các số chẵn `2, 4, 6, 8`; `skip(1)` bỏ `2`, và `limit(2)` giữ `4, 6`.
5. `limit(0)` rỗng; `skip(100)` bỏ quá số phần tử có trong list nên cũng rỗng.
6. `Stream.iterate(1, n -> n + 1)` sinh một stream không có điểm kết thúc từ chính nguồn. `skip(5).limit(3)` làm pipeline hữu hạn cho terminal `toList()`: lấy `6, 7, 8`.

Chương trình mỗi lần tạo một stream mới từ `numbers.stream()`. Đây là cách đúng; **không** tái sử dụng một đối tượng `Stream` sau khi đã gọi terminal operation.

## 3. Thứ tự viết các thao tác làm thay đổi kết quả

Trong pipeline, các operation chạy theo **ngữ nghĩa tổ hợp từ trái sang phải**, mặc dù thời điểm đánh giá thực tế là lazy và có thể được tối ưu hóa.

Ví dụ từ cùng danh sách:

```java
List<Integer> values = List.of(1, 2, 3, 4, 5, 6, 7, 8);

List<Integer> a = values.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();  // [2, 4]

List<Integer> b = values.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();  // [2]
```

Đoạn minh họa cần `import java.util.List;`. Ở `a`, stream **lọc trước** nên `limit(2)` lấy hai số chẵn đầu tiên. Ở `b`, stream **giới hạn trước** còn `[1, 2]` nên bước lọc chỉ giữ `[2]`.

Tương tự:

```java
List<Integer> c = values.stream()
        .skip(2)
        .limit(3)
        .toList();  // [3, 4, 5]

List<Integer> d = values.stream()
        .limit(3)
        .skip(2)
        .toList();  // [3]
```

- `skip(2).limit(3)`: bỏ hai phần tử đầu rồi chọn ba phần tử tiếp.
- `limit(3).skip(2)`: lấy ba phần tử đầu rồi bỏ hai trong ba phần tử vừa lấy.

Không được tùy tiện đổi chỗ `filter`, `sorted`, `distinct`, `skip`, `limit` vì có thể thay đổi tập dữ liệu hoặc thứ tự logic:

```java
List<Integer> values = List.of(8, 2, 7, 1, 9);

List<Integer> smallestTwo = values.stream()
        .sorted()
        .limit(2)
        .toList();  // [1, 2]

List<Integer> firstTwoSorted = values.stream()
        .limit(2)
        .sorted()
        .toList();  // [2, 8]
```

Đây cũng là đoạn minh họa cần `java.util.List`. `sorted().limit(2)` tìm hai phần tử nhỏ nhất **trong toàn bộ nguồn**, còn `limit(2).sorted()` chỉ sắp xếp hai phần tử đầu tiên.

### `distinct` cũng ảnh hưởng số lượng và ranh giới

```java
List<Integer> values = List.of(1, 1, 2, 2, 3);

List<Integer> uniqueFirstTwo = values.stream()
        .distinct()
        .limit(2)
        .toList(); // [1, 2]

List<Integer> dedupFirstTwo = values.stream()
        .limit(2)
        .distinct()
        .toList(); // [1]
```

Nếu đề bài là “hai giá trị khác nhau đầu tiên”, `distinct` phải xuất hiện **trước** `limit(2)`.

## 4. Phân trang với `skip` và `limit`

Một công thức thường gặp cho trang có chỉ số bắt đầu từ **0**:

```text
offset = pageIndex * pageSize
page   = stream.skip(offset).limit(pageSize)
```

Ví dụ list có tám phần tử, mỗi trang ba phần tử:

| `pageIndex` | `offset` | Kết quả |
| --- | ---: | --- |
| 0 | 0 | `[1, 2, 3]` |
| 1 | 3 | `[4, 5, 6]` |
| 2 | 6 | `[7, 8]` |
| 3 | 9 | `[]` |

Một helper phân trang cơ bản trong Java 17:

```java
import java.util.List;

public class Pages {
    public static <T> List<T> page(List<T> source,
                                   long pageIndex,
                                   long pageSize) {
        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException("Trang hoặc kích thước không hợp lệ");
        }

        long offset = Math.multiplyExact(pageIndex, pageSize);
        return source.stream()
                .skip(offset)
                .limit(pageSize)
                .toList();
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi", "Dung", "Em");
        System.out.println(page(names, 0, 2));
        System.out.println(page(names, 1, 2));
        System.out.println(page(names, 2, 2));
    }
}
```

Đây là **chương trình độc lập** lưu tên `Pages.java`, có thể biên dịch/chạy:

```bash
javac -encoding UTF-8 Pages.java
java Pages
```

Stdout:

```text
[An, Bình]
[Chi, Dung]
[Em]
```

Lưu ý:

- `pageSize > 0` giúp xác định ý nghĩa một trang; xét về API, `limit(0)` vẫn hợp lệ, nhưng ở ví dụ này trang kích thước 0 bị từ chối theo chính sách.
- `Math.multiplyExact(pageIndex, pageSize)` phát hiện `long` overflow bằng `ArithmeticException`. Với `long offset = pageIndex * pageSize` không kiểm tra, phép nhân có thể tràn và sinh giá trị sai.
- `Stream.toList()` tạo list **không thể sửa** từ Java 16. Khi cần list có thể sửa, dùng `new ArrayList<>(...)` hoặc collector được lựa chọn phù hợp.
- Nếu nguồn dữ liệu có thể thay đổi giữa hai lần phân trang, các trang theo `offset` có thể bỏ sót/lặp phần tử. Muốn kết quả ổn định cần một thứ tự sắp xếp xác định và chính sách snapshot/cursor khi cần.
- Đoạn helper trên phù hợp dữ liệu **đã nằm trong bộ nhớ**. Với bảng database lớn, nên để database thực hiện phân trang bằng truy vấn thích hợp; dùng `stream().skip(n)` sau khi tải toàn bộ bảng thường lãng phí bộ nhớ, băng thông và CPU.

## 5. Encounter order quyết định ý nghĩa “đầu tiên”

Với `List`, thứ tự phần tử đã được xác định. Vì thế:

```java
List<String> first = List.of("A", "B", "C", "D")
        .parallelStream()
        .skip(1)
        .limit(2)
        .toList();
// first == [B, C]
```

Dù các phần tử có thể được xử lý song song, `skip(1).limit(2)` trên ordered stream lấy đúng đoạn prefix sau khi bỏ một phần tử. Điều này **không có nghĩa callback trung gian nhất thiết được thực thi theo thứ tự**.

Nhưng với nguồn **không có encounter order bảo đảm**, chẳng hạn `HashSet`, “hai phần tử đầu” không có nghĩa nghiệp vụ ổn định:

```java
Set<Integer> numbers = new HashSet<>(List.of(10, 20, 30, 40));
List<Integer> chosen = numbers.stream()
        .limit(2)
        .toList();
```

Đây là đoạn minh họa cần import `java.util.HashSet`, `java.util.List`, `java.util.Set`. `chosen` có hai phần tử khi nguồn có ít nhất hai phần tử, nhưng **không cam kết** đó là cặp nào hoặc thứ tự nào.

Khi bài toán yêu cầu “N phần tử nhỏ nhất”, hãy xác định order bằng `sorted()`:

```java
List<Integer> smallest = numbers.stream()
        .sorted()
        .limit(2)
        .toList();
// smallest == [10, 20]
```

Việc `sorted()` phải sắp xếp toàn bộ hoặc phối hợp dữ liệu có thể tốn chi phí; yêu cầu ngữ nghĩa đúng quan trọng hơn việc đoán số nào sẽ xuất hiện đầu tiên từ `HashSet`.

## 6. `limit` trên stream vô hạn và thao tác dừng sớm

Với một nguồn sinh mãi không dừng, `limit` thường là điều kiện chặn cần thiết để phép thu thập hoàn tất.

```java
List<Long> powers = java.util.stream.Stream.iterate(1L, n -> n * 2)
        .limit(5)
        .toList();
// [1, 2, 4, 8, 16]
```

Đây là đoạn minh họa cần `import java.util.List;`. `Stream.iterate(seed, next)` dạng hai đối số sinh ra stream không có điểm kết thúc tự nhiên, nhưng `limit(5)` làm phép `toList()` có thể trả về năm giá trị.

Trái lại:

```java
// KHÔNG nên gọi toList() trên stream vô hạn không có bước giới hạn:
java.util.stream.Stream.iterate(1L, n -> n + 1)
        .skip(100)
        .toList();
```

Đoạn trên là **mã minh họa sai thiết kế**, có thể tiếp tục lấy phần tử vô hạn và tiêu tốn bộ nhớ. `skip(100)` chỉ loại 100 phần tử đầu; nó **không giới hạn** số phần tử còn lại. Dùng `skip(100).limit(10)` khi cần mười phần tử kế tiếp.

### `limit(n)` không đồng nghĩa “chỉ chạy n lần mọi hàm”

Ví dụ `filter` phải kiểm tra dữ liệu cho đến khi tìm đủ phần tử phù hợp:

```java
List<Integer> a = java.util.stream.IntStream.rangeClosed(1, 20)
        .boxed()
        .filter(n -> n % 5 == 0)
        .limit(2)
        .toList();
// [5, 10]
```

Ở ví dụ này, `filter` không thể chỉ nhìn hai số đầu `1, 2` mà biết được hai kết quả. Do đó không dùng `limit(2)` như một cách cam kết toàn pipeline chỉ xử lý hai phần tử upstream.

Với stream song song, việc xử lý phần tử không theo thứ tự và phối hợp kết quả càng khiến số lần gọi callback không nên được dùng như một hợp đồng nghiệp vụ.

## 7. `skip` và `limit` trên parallel stream: đúng nhưng có thể đắt

Một **ordered parallel stream** vẫn có thể trả chính xác đoạn yêu cầu, ví dụ:

```java
List<Integer> result = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .skip(3)
        .limit(4)
        .boxed()
        .toList();
// [4, 5, 6, 7]
```

Tuy nhiên, để biết đâu là ba phần tử đầu cần bỏ và bốn phần tử tiếp theo cần giữ, hệ thống có thể phải phối hợp giữa các nhánh xử lý. Với nguồn lớn, `skip`, `limit` và các stateful operation khác **có thể giảm lợi ích của xử lý song song** do yêu cầu giữ encounter order. Tác động thực tế tùy nguồn, spliterator, kích thước dữ liệu, pipeline và JVM.

Nếu **thứ tự không quan trọng về nghiệp vụ**, `unordered()` có thể nới lỏng ràng buộc:

```java
List<Integer> anyFour = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .unordered()
        .limit(4)
        .boxed()
        .toList();
```

`anyFour` có bốn phần tử từ nguồn, nhưng **không được giả định** luôn là `[1, 2, 3, 4]`. `unordered()` không có nghĩa xáo trộn ngẫu nhiên; nó chỉ cho phép pipeline bỏ qua ràng buộc encounter order nếu có.

Khi muốn phân trang mang tính xác định, đặc biệt trong UI hoặc API công khai, **không** dùng `unordered()` chỉ để hy vọng nhanh hơn.

## 8. Các bẫy thường gặp

1. **Dùng tham số âm:** `stream.limit(-1)` hoặc `stream.skip(-1)` ném `IllegalArgumentException`. Kiểm tra đầu vào phân trang trước.
2. **Đổi sai vị trí `filter`:** `limit(3).filter(p)` có thể trả ít hơn ba kết quả phù hợp, dù nguồn còn nhiều kết quả hợp lệ. Nếu cần tối đa ba phần tử khớp điều kiện, thường đặt `filter(p).limit(3)`.
3. **Đổi sai vị trí `skip` và `limit`:** `skip(10).limit(5)` lấy trang từ vị trí 10; `limit(5).skip(10)` chắc chắn rỗng với stream hữu hạn vì đã giới hạn tối đa năm phần tử.
4. **Dùng stream không ordered cho phân trang:** `HashSet.stream().skip(...).limit(...)` không có thứ tự xuất phát ổn định để người dùng di chuyển qua nhiều trang.
5. **Đưa side effect vào `peek` hoặc `map`:** `limit` có thể dừng sớm; JVM cũng có thể tối ưu pipeline. Không dựa vào callback để ghi DB, gửi email hoặc tăng bộ đếm bắt buộc.
6. **Tưởng `skip(n)` cho phép truy cập ngẫu nhiên tức thì:** trên nhiều nguồn, pipeline phải đi qua hoặc phối hợp việc bỏ qua một số lượng phần tử. Không mặc định `skip(1_000_000)` rẻ.
7. **Quên giới hạn stream vô hạn:** `skip` không khiến nguồn vô hạn trở thành hữu hạn; muốn thu thập một đoạn hữu hạn hãy thêm `limit`.
8. **Tái sử dụng `Stream`:** sau `toList()`, `count()` hoặc terminal operation khác, cần tạo một stream mới. Nếu cố dùng lại có thể nhận `IllegalStateException`.
9. **Tràn số khi tính offset:** `pageIndex * pageSize` ở `int` có thể tràn trước khi gán sang `long`; cân nhắc `Math.multiplyExact` với các đối số `long`.
10. **Nghĩ kết quả `toList()` luôn sửa được:** từ Java 16, list do `Stream.toList()` trả về là unmodifiable; nếu cần chỉnh sửa tiếp phải tạo bản sao phù hợp.

### Vì sao có lúc `peek` không được gọi như dự kiến?

```java
long count = List.of(1, 2, 3, 4)
        .stream()
        .limit(2)
        .peek(System.out::println)
        .count();
// count == 2, nhưng không nên cam kết có hai dòng được in.
```

Đây là đoạn minh họa bên trong phương thức có `import java.util.List;`. Với nguồn đã biết kích thước và pipeline giữ được thông tin kích thước, một triển khai có thể tính `count()` mà không đi qua `peek`. Vì vậy `peek` không thích hợp cho tác dụng phụ bắt buộc. Nếu cần thực thi hành động trên kết quả đã chọn, hãy xây dựng kết quả rồi duyệt với chính sách rõ ràng.

## 9. Chọn cách viết phù hợp

| Yêu cầu | Pipeline |
| --- | --- |
| Lấy tối đa 10 phần tử đầu từ ordered stream | `stream.limit(10)` |
| Bỏ qua 10 phần tử đầu | `stream.skip(10)` |
| Lấy phần tử ở vị trí 10 đến 19 (chỉ số 0-based) | `stream.skip(10).limit(10)` |
| Tìm ba phần tử đầu **thỏa** predicate | `stream.filter(p).limit(3)` |
| Lấy ba phần tử nhỏ nhất từ nguồn | `stream.sorted().limit(3)` |
| Chọn 10 giá trị phân biệt đầu tiên | `stream.distinct().limit(10)` |
| Chọn năm phần tử bất kỳ khi không cần thứ tự | `stream.unordered().limit(5)` |
| Lấy một đoạn hữu hạn từ stream vô hạn | `stream.skip(offset).limit(size)` |

Các pipeline trên mô tả **ý nghĩa** của kết quả; việc nhanh hay chậm phải đánh giá theo nguồn thực tế. Với các danh sách trong bộ nhớ nhỏ, cách viết `skip/limit` dễ hiểu. Với dữ liệu rất lớn, có thể cân nhắc thao tác trực tiếp trên index/list (khi cần và có thể) hoặc chuyển phân trang xuống nguồn dữ liệu.

## 10. Tự kiểm tra kiến thức

1. `List.of(1,2,3,4,5).stream().skip(2).limit(2).toList()` trả gì? **`[3,4]`**, vì bỏ hai phần tử rồi chọn hai phần tiếp theo.
2. `List.of(1,2,3,4).stream().limit(2).skip(2).toList()` trả gì? **`[]`**, vì ban đầu chỉ còn hai phần tử rồi bỏ cả hai.
3. `filter(n -> n % 2 == 0).limit(2)` khác `limit(2).filter(n -> n % 2 == 0)` thế nào? Cách đầu tìm **tối đa hai số chẵn đầu**, cách sau chỉ lọc trong **hai phần tử đầu của nguồn**.
4. Có thể dùng `skip(50)` một mình để kết thúc một stream vô hạn không? **Không**, vì vẫn còn vô hạn phần tử sau khi bỏ 50 phần tử.
5. `parallelStream().skip(2).limit(3).toList()` có giữ ba phần tử đúng vị trí trên `List` không? **Có**, vì nguồn list có encounter order và pipeline vẫn ordered; nhưng callback có thể thực thi song song.
6. `unordered().limit(3)` có bảo đảm lấy ba phần tử đầu không? **Không**, vì đã bỏ ràng buộc thứ tự.

## Ghi nhớ

- **`limit(n)` = giữ tối đa n phần tử đầu của stream ở vị trí thao tác.**
- **`skip(n)` = bỏ n phần tử đầu, giữ phần còn lại.**
- Cả hai đều **lazy intermediate operations**, yêu cầu `n >= 0`, không sửa nguồn và phụ thuộc vào encounter order để định nghĩa “đầu tiên”.
- `filter`, `distinct`, `sorted`, `skip`, `limit` **không hoán đổi tùy tiện** vì thứ tự pipeline làm thay đổi kết quả.
- Trong phân trang: `skip(offset).limit(pageSize)`, kiểm tra offset và giữ một thứ tự dữ liệu ổn định.
- Với stream vô hạn, `limit` giúp giới hạn kết quả; với parallel stream, giữ thứ tự có thể phát sinh chi phí phối hợp.
