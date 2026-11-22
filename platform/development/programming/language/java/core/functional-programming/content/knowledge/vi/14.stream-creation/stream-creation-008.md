# Giới hạn nguồn vô hạn để pipeline có thể kết thúc trong Java Stream

Stream API trong Java có thể biểu diễn những dãy phần tử **không có điểm kết thúc tự nhiên**, chẳng hạn chuỗi số liên tiếp, dữ liệu cảm biến hoặc các giá trị sinh từ một `Supplier`. Nếu ta dùng thao tác kết thúc như `toList()`, `count()` hay `reduce()` mà không xác lập điều kiện dừng, pipeline có thể chạy vô hạn hoặc tiêu tốn hết tài nguyên.

Cách giải quyết là thiết kế một **điểm dừng hữu hạn có thể đạt tới**. Những công cụ chính gồm `limit(n)`, `takeWhile(predicate)`, `Stream.iterate(seed, hasNext, next)` và các terminal có thể dừng sớm như `findFirst()` hoặc `anyMatch()`. Tuy vậy, kết thúc hay không còn phụ thuộc **thứ tự các phép toán**, khả năng có phần tử thỏa điều kiện và những phép stateful ở phía trước.

Ví dụ đơn giản:

~~~java
List<Integer> numbers = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();
// [1, 2, 3, 4, 5]
~~~

Đoạn mã này cần import `java.util.List` và `java.util.stream.Stream`, và đặt bên trong một phương thức. Nguồn `iterate` có khả năng sinh tiếp 6, 7, 8..., nhưng `limit(5)` chỉ đưa tối đa năm phần tử xuống terminal `toList()`.

## 1. Nguồn hữu hạn và nguồn vô hạn

Một **nguồn hữu hạn** có số phần tử giới hạn: `List.stream()`, `Stream.of(...)`, `Arrays.stream(...)`, `IntStream.range(...)` hoặc một tập tin hữu hạn. Một nguồn **có khả năng vô hạn** là nơi có thể tạo các phần tử mới mà không có điểm dừng nội tại.

~~~java
Stream<Integer> ascending = Stream.iterate(1, n -> n + 1);
Stream<String> ticks = Stream.generate(() -> "tick");
~~~

`Stream.iterate(seed, next)` phát `seed` trước; sau đó tạo phần tử mới bằng cách gọi `next` trên phần tử trước. `Stream.generate(supplier)` lấy phần tử tiếp theo bằng `supplier.get()`. Cả hai overload trên không khai báo giới hạn số phần tử; `generate` còn mang đặc tính *unordered*, nên đừng dựa vào encounter order của các giá trị mà nó sinh.

**Stream là mô tả tính toán, không phải một collection chứa sẵn vô hạn phần tử.** Các phép trung gian thường lazy: xây dựng biểu thức không khiến nó tự động sinh vô số phần tử. Chỉ khi terminal cần kết quả, dữ liệu mới được duyệt. Lazy không đồng nghĩa có thể hoàn tất; nếu terminal cần biết toàn bộ dãy vô hạn, không có kết quả cuối cùng.

Một số nguồn nhìn giống vô hạn nhưng thực tế bị chi phối bởi miền dữ liệu hữu hạn hoặc giới hạn vật lý. Chẳng hạn `n -> n + 1` với kiểu `int` cuối cùng có thể tràn số, **không phải điều kiện dừng hợp lệ**. Nếu cần số tăng trong khoảng xác định, nên dùng `IntStream.range` hoặc `iterate` có điều kiện dừng rõ ràng.

## 2. `limit(n)` — đặt trần số phần tử

`limit(long maxSize)` là **intermediate operation** trả về stream có tối đa `maxSize` phần tử. Khi đặt ở vị trí hợp lý, nó cho phép terminal vốn cần hết đầu vào hoàn tất trên một đoạn hữu hạn của nguồn vô hạn.

~~~java
List<String> firstThree = Stream.generate(() -> "tick")
        .limit(3)
        .toList();
// [tick, tick, tick]
~~~

Những điều cần hiểu chính xác:

- `limit(0)` tạo stream không có phần tử, còn `limit(-1)` ném `IllegalArgumentException`.
- `limit(5)` giới hạn **số phần tử đi qua vị trí limit**, không nhất thiết giới hạn nguồn chỉ sinh đúng năm phần tử. Nếu có `filter` đứng trước, cần xem thêm phần tử cho tới khi tìm đủ năm kết quả.
- `limit` vẫn là phép trung gian; cần terminal như `toList()`, `count()`, `findFirst()` hoặc `forEach(...)` để yêu cầu xử lý.
- Nếu các phép đứng trước limit không bao giờ cung cấp đủ phần tử (chẳng hạn filter loại hết), terminal có thể không bao giờ hoàn tất.
- Với stream song song và ordered, yêu cầu lấy "n phần tử đầu tiên" có thể phát sinh chi phí phối hợp; không dựa vào số lần supplier/mapper chạy làm hợp đồng.

### `filter` trước và sau `limit`

Lấy **bốn số chẵn đầu tiên**:

~~~java
List<Integer> firstFourEvens = Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(4)
        .toList();
// [2, 4, 6, 8]
~~~

Nguồn phải sinh tới 8 để tìm đủ bốn giá trị qua filter. Đổi thứ tự:

~~~java
List<Integer> evensWithinFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .filter(n -> n % 2 == 0)
        .toList();
// [2, 4]
~~~

Cách thứ hai **chỉ xét năm phần tử đầu nguồn** trước khi lọc, vì thế có thể trả ít hơn số lượng mong muốn. Nếu yêu cầu "lấy N kết quả đạt điều kiện", thường đặt filter trước limit. Nếu yêu cầu "xét tối đa N mẫu rồi tìm giá trị đạt điều kiện", phải đặt limit trước filter. Khi filter có thể không bao giờ đạt điều kiện, ràng buộc trước filter giúp bảo đảm số mẫu khảo sát hữu hạn.

## 3. `takeWhile(predicate)` — dừng khi gặp phần tử đầu tiên sai

Từ Java 9, `takeWhile` trên **stream có encounter order** lấy đoạn tiền tố dài nhất mà các phần tử liên tiếp đều thỏa predicate, rồi dừng khi gặp phần tử đầu tiên sai:

~~~java
List<Integer> prefix = Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n < 6)
        .toList();
// [1, 2, 3, 4, 5]
~~~

Phần tử 6 làm predicate sai và không được đưa ra. Đặc tính này phù hợp với một chuỗi có thứ tự và điều kiện kiểm tra **chắc chắn sẽ sai sau hữu hạn bước**, chẳng hạn các mốc thời gian tăng đến một giới hạn.

Đừng nhầm `takeWhile` với `filter`:

~~~java
List<Integer> a = Stream.of(1, 2, 8, 3, 4)
        .filter(n -> n < 5)
        .toList(); // [1, 2, 3, 4]

List<Integer> b = Stream.of(1, 2, 8, 3, 4)
        .takeWhile(n -> n < 5)
        .toList(); // [1, 2]
~~~

`filter` có thể giữ các phần tử thỏa điều kiện xuất hiện sau một phần tử không thỏa. `takeWhile` dừng tại điểm **đầu tiên** không thỏa khi stream ordered. Nếu nguồn unordered, không nên coi `takeWhile` là một đoạn tiền tố xác định.

`takeWhile` không thể tự bảo đảm kết thúc nếu predicate luôn true:

~~~java
// Không chạy đoạn này: predicate luôn true trên nguồn toàn số 1.
// Stream.generate(() -> 1)
//       .takeWhile(n -> n < 6)
//       .toList();
~~~

Ngay cả nếu predicate cuối cùng có thể sai, nguồn sinh dữ liệu quá chậm hoặc điều kiện quá xa cũng khiến chương trình chạy lâu.

### `dropWhile` không phải giới hạn cho phần còn lại

`dropWhile(predicate)` bỏ đoạn tiền tố thỏa điều kiện rồi **đưa tất cả phần còn lại** xuống stream. Nguồn vô hạn vẫn có thể cho đầu ra vô hạn:

~~~java
Stream<Integer> remaining = Stream.iterate(1, n -> n + 1)
        .dropWhile(n -> n < 100);

List<Integer> sample = remaining.limit(3).toList();
// [100, 101, 102]
~~~

Không có `limit(3)`, `remaining.toList()` có thể không kết thúc.

## 4. `iterate(seed, hasNext, next)` — chặn ngay ở nguồn

Overload ba tham số từ Java 9 biểu diễn một dãy có điều kiện tiếp tục:

~~~java
Stream.iterate(seed, hasNext, next)
~~~

`seed` là phần tử ứng viên đầu; nếu `hasNext.test(seed)` true, nó được phát, sau đó `next.apply(seed)` tạo ứng viên tiếp theo. Quá trình tiếp tục tới ứng viên đầu tiên có `hasNext` false, và ứng viên đó **không xuất hiện trong đầu ra**.

~~~java
List<Integer> finite = Stream.iterate(
        1, n -> n <= 5, n -> n + 1)
        .toList();
// [1, 2, 3, 4, 5]
~~~

Cùng dãy có thể viết bằng `iterate(1, n -> n + 1).takeWhile(n -> n <= 5)` trên stream ordered, nhưng overload ba tham số diễn đạt ranh giới ngay từ nguồn.

| Nguồn/cách giới hạn | Ý nghĩa |
| --- | --- |
| `Stream.iterate(1, n -> n + 1)` | Có khả năng phát mãi |
| `Stream.iterate(1, n -> n + 1).limit(5)` | Lấy tối đa năm phần tử |
| `Stream.iterate(1, n -> n <= 5, n -> n + 1)` | Ngừng phát tại ứng viên đầu tiên lớn hơn 5 |
| `Stream.iterate(1, n -> n + 1).takeWhile(n -> n <= 5)` | Giữ đoạn tiền tố đạt điều kiện |

Overload ba tham số cũng có thể chạy vô hạn nếu `hasNext` không bao giờ false. Cần bảo đảm hàm `next` làm dữ liệu **tiến gần đến điều kiện dừng**, xử lý khả năng tràn số hoặc vòng lặp chu kỳ. Khi cần một khoảng số nguyên, `IntStream.range(1, 6)` hoặc `rangeClosed(1, 5)` thường còn rõ ràng hơn.

## 5. Terminal short-circuit — dừng khi đã đủ thông tin

Một số terminal không cần xem hết nguồn để xác định kết quả:

| Terminal | Điều kiện có thể dừng | Kiểu kết quả |
| --- | --- | --- |
| `findFirst()` | Đã có phần tử đầu tiên theo encounter order | `Optional<T>` |
| `findAny()` | Tìm được một phần tử bất kỳ | `Optional<T>` |
| `anyMatch(p)` | Gặp một phần tử mà `p` là true | `boolean` |
| `allMatch(p)` | Gặp một phần tử mà `p` là false | `boolean` |
| `noneMatch(p)` | Gặp một phần tử mà `p` là true | `boolean` |

Ví dụ nguồn vô hạn nhưng terminal sớm xác định được kết quả:

~~~java
boolean hasSeven = Stream.iterate(1, n -> n + 1)
        .anyMatch(n -> n == 7);
// true
~~~

Khi đến 7, không cần duyệt tiếp. Ngược lại, **short-circuit là khả năng, không phải lời hứa**. Những pipeline bên dưới không có điều kiện thoát có thể đạt tới:

~~~java
// Không bao giờ tìm được số 2:
// Stream.generate(() -> 1).anyMatch(n -> n == 2);

// Mọi phần tử đều vượt 0, không có trường hợp làm allMatch false:
// Stream.generate(() -> 1).allMatch(n -> n > 0);

// Không có phần tử đầu ra cho findFirst:
// Stream.generate(() -> 1)
//       .filter(n -> n == 2)
//       .findFirst();
~~~

Các dòng đã comment để tránh treo. `allMatch` trên nguồn vô hạn chỉ gồm giá trị thỏa predicate không thể chứng minh "mọi phần tử đều đúng" sau hữu hạn lần đọc. `noneMatch` tương tự nếu tất cả phần tử không thỏa. `findFirst` sau filter cần filter thực sự chuyển tiếp một phần tử.

Terminal như `toList()`, `forEach(...)`, `reduce(...)`, `sum()`, `collect(...)` thường phải tiêu thụ toàn bộ các phần tử còn lại. `count()` đôi khi tối ưu khi biết chính xác kích thước stream, nhưng đừng dựa vào tối ưu để giả định nguồn vô hạn có thể đếm xong. Muốn xử lý toàn bộ, hãy xác định một đoạn hữu hạn trước.

## 6. Tại sao `sorted` và `distinct` làm giới hạn không phát huy tác dụng?

Vị trí thao tác là một phần của hợp đồng pipeline. `sorted()` thường cần nhận toàn bộ đầu vào để xác định thứ tự; đặt `limit` sau sorted trên nguồn vô hạn có thể chờ vô hạn hoặc hết bộ nhớ:

~~~java
// Sai về tính kết thúc, cố ý không thực thi:
// Stream.iterate(1, n -> n + 1)
//       .sorted(Comparator.reverseOrder())
//       .limit(3)
//       .toList();
~~~

Nếu yêu cầu là **ba số lớn nhất trong 100 số đầu**, hãy tạo tập hữu hạn trước khi sắp xếp:

~~~java
List<Integer> topThree = Stream.iterate(1, n -> n + 1)
        .limit(100)
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();
// [100, 99, 98]
~~~

`limit(100)` xác định kích thước mẫu; `sorted(...)` có thể kết thúc vì đầu vào hữu hạn; `limit(3)` sau đó chọn ba phần tử. Nếu muốn "ba số lớn nhất trong toàn bộ dãy tăng vô hạn", yêu cầu toán học này không có ba phần tử lớn nhất — cần sửa phạm vi hoặc tiêu chí.

`distinct()` cũng có thể ngăn pipeline đạt đủ số lượng kết quả:

~~~java
// Không kết thúc: chỉ có một giá trị phân biệt.
// Stream.generate(() -> 1)
//       .distinct()
//       .limit(2)
//       .toList();
~~~

Sửa nếu nghiệp vụ là "loại trùng trong 10 mẫu đầu":

~~~java
List<Integer> uniqueFromTen = Stream.generate(() -> 1)
        .limit(10)
        .distinct()
        .toList();
// [1]
~~~

`skip(n)` chỉ bỏ một đoạn đầu, **không giới hạn đầu ra**; `Stream.generate(() -> 1).skip(100).toList()` vẫn không có điểm dừng. `filter` cũng không cam kết số phần tử sau lọc hữu hạn; nó là điều kiện chấp nhận từng phần tử, không phải điều kiện chấm dứt duyệt nguồn.

## 7. Chương trình Java 17+ hoàn chỉnh

Lưu chương trình dưới tên **`InfiniteStreamLimitDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class InfiniteStreamLimitDemo {
    public static void main(String[] args) {
        List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
                .limit(5)
                .toList();
        List<String> ticks = Stream.generate(() -> "tick")
                .limit(3)
                .toList();
        List<Integer> finiteByPredicate = Stream.iterate(
                1, n -> n <= 5, n -> n + 1).toList();
        List<Integer> firstFourEvens = Stream.iterate(1, n -> n + 1)
                .filter(n -> n % 2 == 0)
                .limit(4)
                .toList();
        List<Integer> boundBeforeFilter = Stream.iterate(1, n -> n + 1)
                .limit(5)
                .filter(n -> n % 2 == 0)
                .toList();
        List<Integer> prefix = Stream.iterate(1, n -> n + 1)
                .takeWhile(n -> n < 6)
                .toList();
        boolean hasSeven = Stream.iterate(1, n -> n + 1)
                .anyMatch(n -> n == 7);
        List<Integer> highestThreeFromHundred = Stream.iterate(1, n -> n + 1)
                .limit(100)
                .sorted(Comparator.reverseOrder())
                .limit(3)
                .toList();
        List<Integer> primitive = IntStream.iterate(0, n -> n + 2)
                .limit(4)
                .boxed()
                .toList();
        System.out.println("firstFive=" + firstFive);
        System.out.println("ticks=" + ticks);
        System.out.println("finiteByPredicate=" + finiteByPredicate);
        System.out.println("firstFourEvens=" + firstFourEvens);
        System.out.println("boundBeforeFilter=" + boundBeforeFilter);
        System.out.println("prefix=" + prefix);
        System.out.println("hasSeven=" + hasSeven);
        System.out.println("highestThreeFromHundred=" + highestThreeFromHundred);
        System.out.println("primitive=" + primitive);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac InfiniteStreamLimitDemo.java
java InfiniteStreamLimitDemo
~~~

Đầu ra chính xác:

~~~text
firstFive=[1, 2, 3, 4, 5]
ticks=[tick, tick, tick]
finiteByPredicate=[1, 2, 3, 4, 5]
firstFourEvens=[2, 4, 6, 8]
boundBeforeFilter=[2, 4]
prefix=[1, 2, 3, 4, 5]
hasSeven=true
highestThreeFromHundred=[100, 99, 98]
primitive=[0, 2, 4, 6]
~~~

Giải thích từng kết quả:

1. `firstFive` giới hạn dãy tăng không có biên bằng `limit(5)`.
2. `ticks` chặn nguồn `generate` sau ba kết quả giống nhau.
3. `finiteByPredicate` dùng overload `iterate` ba tham số dừng từ nguồn khi ứng viên là 6.
4. `firstFourEvens` áp filter trước limit để có đủ bốn số chẵn.
5. `boundBeforeFilter` giới hạn trước filter nên chỉ xét năm phần tử đầu nguồn.
6. `prefix` dùng `takeWhile` và ngừng khi không còn thỏa `n < 6`.
7. `hasSeven` dùng terminal `anyMatch` tìm thấy 7 và dừng sớm.
8. `highestThreeFromHundred` tạo mẫu hữu hạn 100 phần tử, sắp xếp giảm dần và chỉ giữ ba số đầu.
9. `primitive` biểu diễn pipeline bằng `IntStream` và `boxed()` trước khi tạo `List<Integer>`.

Mã này đã được biên dịch với `javac --release 17` và chạy kiểm chứng đúng stdout bên trên. Những trường hợp cố ý không có điểm dừng ở các mục khác được để dưới dạng comment, không chạy chung với chương trình.

## 8. Parallel stream, tính thứ tự và hiệu năng

Với stream **ordered** như `List.stream()`, `limit(n)` lấy tối đa n phần tử đầu theo encounter order; khi song song, việc xác định "n phần tử đầu" có thể đòi hỏi phối hợp, ảnh hưởng tốc độ. Với nguồn **unordered**, Java có nhiều quyền tự do lựa chọn tập n phần tử; không thể dựa vào một thứ tự xác định nếu nguồn không có encounter order.

Tương tự, `takeWhile` trên ordered stream có nghĩa "lấy đoạn tiền tố", nhưng trên unordered stream, tập phần tử thỏa điều kiện có thể không là một đoạn tiền tố cố định. Đừng thay đổi sang `unordered()` chỉ để nhanh hơn nếu yêu cầu nghiệp vụ phụ thuộc thứ tự.

Một số pipeline song song có thể thực thi supplier, mapper hoặc predicate cho nhiều phần tử hơn số phần tử cuối cùng, vì kết quả giữa các task được phối hợp. Tránh phụ thuộc vào **số lần callback được gọi** hoặc các side effect bên trong `peek`, `map` hay `filter`; kiểm thử dựa trên giá trị kết quả. Với nguồn vô hạn, khởi đầu bằng cách viết pipeline tuần tự có điều kiện dừng rõ ràng thường dễ kiểm chứng hơn.

## 9. Giới hạn số phần tử khác với giới hạn thời gian và tài nguyên

Dù đã có `limit(10)`, pipeline vẫn có thể không hoàn thành nếu một lần đọc nguồn bị chặn bởi I/O hoặc một predicate đứng trước limit chạy mãi. Những điểm cần cân nhắc:

- **Đối số quá lớn:** `limit(Long.MAX_VALUE)` có giới hạn lý thuyết, nhưng thu thập nhiều phần tử đến mức này thường không khả thi.
- **Nguồn blocking:** `Supplier.get()` có thể chờ mạng, queue hoặc thiết bị. `limit(n)` không cung cấp timeout để ép supplier trả dữ liệu.
- **Điều kiện không đạt:** `filter(p).limit(1)` vẫn chờ mãi nếu không có phần tử nào thỏa `p`.
- **Stateful operation:** `sorted` cần thấy đủ đầu vào; `distinct` có thể phải giữ nhiều giá trị trong bộ nhớ.
- **Hủy tác vụ:** `Stream` đồng bộ không thay thế cơ chế cancellation và backpressure chuyên biệt cho luồng sự kiện không giới hạn.
- **Nguồn có tài nguyên:** terminal không tự bảo đảm đóng tài nguyên I/O; `limit` chỉ giới hạn số phần tử, không thay cơ chế `close`.

Ví dụ đọc tối đa mười dòng từ tập tin:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    List<String> firstTen = lines.limit(10).toList();
    System.out.println(firstTen);
}
~~~

Đây là **đoạn mã minh họa** đặt trong phương thức có `Path path` hợp lệ, cần import `java.nio.file.Files`, `java.nio.file.Path`, `java.util.List`, `java.util.stream.Stream` và khai báo hoặc xử lý `IOException`. `try-with-resources` đóng stream/file ngay cả khi chỉ đọc một phần nguồn.

## 10. Các lỗi thường gặp

**Gọi terminal tiêu thụ toàn bộ nguồn vô hạn:**

~~~java
// Không thực thi: không có giới hạn đầu ra.
// Stream.iterate(1, n -> n + 1).toList();
~~~

Dùng `limit`, `takeWhile` hoặc `iterate` ba tham số để định nghĩa điểm dừng.

**Đặt `limit` sau bộ lọc không có kết quả:**

~~~java
// Không thực thi: chỉ sinh số 1, nên filter không bao giờ phát số 2.
// Stream.generate(() -> 1).filter(n -> n == 2)
//       .limit(1).toList();
~~~

Nếu cần kiểm tra **tối đa 100 phần tử nguồn**, viết:

~~~java
List<Integer> matches = Stream.generate(() -> 1)
        .limit(100)
        .filter(n -> n == 2)
        .toList();
// []
~~~

Kết quả empty lúc này có nghĩa "không tìm thấy trong 100 phần tử được khảo sát", không chứng minh giá trị đó không xuất hiện ở phần còn lại của một nguồn bất kỳ.

**Đặt `limit` sau `sorted`:** có thể không xử lý xong vì `sorted` cần thấy mọi phần tử đầu vào. Khi mục tiêu là xếp hạng một tập mẫu hữu hạn, giới hạn nguồn trước khi sắp xếp.

**Cho rằng `anyMatch` luôn kết thúc:** nó chỉ short-circuit nếu gặp phần tử phù hợp. Nếu không biết phần tử có tồn tại không, đặt giới hạn số phần tử được phép kiểm tra hoặc có cơ chế hủy/thời gian chờ.

**Dùng `takeWhile` với predicate không bao giờ sai:** đây vẫn có thể là pipeline vô hạn. Kiểm tra ý nghĩa và khả năng tiến triển của điều kiện.

**Tưởng `skip(n)` chặn số kết quả:** `skip` chỉ bỏ đoạn đầu; nó không làm phần sau hữu hạn.

**Dùng lại stream đã tiêu thụ:**

~~~java
Stream<Integer> once = Stream.iterate(1, n -> n + 1).limit(3);
List<Integer> first = once.toList();
// Sai nếu bỏ comment: stream đã tiêu thụ.
// long count = once.count();
~~~

Stream là **single-use**; muốn chạy một terminal mới, tạo Stream mới từ nguồn hoặc cung cấp `Supplier<Stream<T>>` tạo pipeline mới.

## 11. Checklist lựa chọn

| Nhu cầu | Cách làm | Điều cần bảo đảm |
| --- | --- | --- |
| Lấy tối đa N phần tử | `source.limit(N)` | Các bước trước limit phải có khả năng cung cấp đủ phần tử |
| Chỉ khảo sát tối đa N phần tử rồi lọc | `source.limit(N).filter(p)` | Có thể thu được ít hơn N kết quả |
| Lấy N kết quả hợp lệ đầu tiên | `source.filter(p).limit(N)` | Predicate phải có khả năng cho đủ N kết quả |
| Sinh dãy đến một mốc | `Stream.iterate(seed, hasNext, next)` | `hasNext` phải trở thành false sau hữu hạn bước |
| Lấy đoạn tiền tố đúng điều kiện | `orderedStream.takeWhile(p)` | Phải gặp phần tử đầu tiên làm `p` false |
| Tìm phần tử phù hợp | `source.anyMatch(p)` | Phải có phần tử phù hợp hoặc thêm giới hạn quét |
| Xếp hạng N phần tử trong M phần tử đầu | `source.limit(M).sorted(...).limit(N)` | M hữu hạn trước `sorted` |
| Loại trùng trong một tập mẫu | `source.limit(M).distinct()` | M là số mẫu, không phải số kết quả phân biệt |
| Đọc một phần tệp | `Files.lines(path).limit(N)` | Đóng stream và xử lý I/O exception |

Để biết pipeline có thể kết thúc không, hãy kiểm tra lần lượt: **(1) terminal cần bao nhiêu phần tử để cho kết quả, (2) điều kiện dừng có thể xảy ra sau hữu hạn lần lấy phần tử không, (3) có phép toán nào đứng trước điểm dừng cần tiêu thụ toàn bộ nguồn không, và (4) nguồn có thể bị block hoặc gặp giới hạn tài nguyên không**. Chỉ khi các điều kiện đó được tính đến, giới hạn nguồn mới bảo đảm hành vi có thể dự đoán và kiểm thử được.