# Khác biệt với filter, limit và skip

Trong Stream API, các thao tác `filter`, `limit` và `skip` đã có từ Java 8. Java 9 bổ sung `takeWhile` và `dropWhile` để xử lý một đoạn đầu (prefix) của stream dựa trên điều kiện.

Các thao tác này đều là intermediate operation: chúng tạo pipeline mới và chỉ thực thi khi có terminal operation như `toList()`, `count()` hoặc `forEach()`. Chúng không sửa collection nguồn. Điểm khác nhau nằm ở cách chọn phần tử: theo điều kiện trên toàn stream, theo vị trí, hay theo đoạn liên tiếp bắt đầu từ đầu stream.

## 1. Phân biệt năm thao tác

Giả sử stream có encounter order và chứa:

```java
List<Integer> values = List.of(3, 6, 2, 8, 4, 10, 1, 12);
Predicate<Integer> belowEight = value -> value < 8;
```

Các thao tác có ý nghĩa như sau:

| Thao tác | Quy tắc chọn phần tử | Gặp phần tử không thỏa điều kiện |
|---|---|---|
| `filter(p)` | Giữ mọi phần tử thỏa predicate ở bất kỳ vị trí nào | Bỏ phần tử đó và tiếp tục xét phần còn lại |
| `takeWhile(p)` | Giữ đoạn liên tiếp dài nhất từ đầu stream mà mọi phần tử đều thỏa predicate | Dừng lấy phần tử tại ranh giới đầu tiên; phần sau bị bỏ khỏi kết quả |
| `dropWhile(p)` | Bỏ đoạn liên tiếp dài nhất từ đầu stream mà mọi phần tử đều thỏa predicate | Bắt đầu giữ từ phần tử không thỏa đầu tiên, cùng toàn bộ phần còn lại |
| `limit(n)` | Giữ tối đa n phần tử đầu theo encounter order | Không kiểm tra predicate |
| `skip(n)` | Bỏ n phần tử đầu theo encounter order, giữ phần còn lại | Không kiểm tra predicate |

Có thể ghi nhớ:

- `filter` hỏi từng phần tử: “Phần tử này có đạt điều kiện không?”
- `takeWhile` hỏi: “Đoạn đầu stream còn tiếp tục đạt điều kiện đến đâu?”
- `dropWhile` hỏi: “Cần bỏ đoạn đầu đạt điều kiện đến đâu?”
- `limit` và `skip` chỉ đếm số phần tử theo vị trí.

`takeWhile` và `dropWhile` không phải cách viết khác của `filter`. Một phần tử nằm sau ranh giới đầu tiên có thể thỏa predicate nhưng vẫn bị `takeWhile` loại bỏ; ngược lại, `dropWhile` giữ phần tử đó.

## 2. Ví dụ trực tiếp

Với dữ liệu `[3, 6, 2, 8, 4, 10, 1, 12]` và điều kiện `value < 8`:

```java
import java.util.List;
import java.util.function.Predicate;

public class Main {
    public static void main(String[] args) {
        List<Integer> values = List.of(3, 6, 2, 8, 4, 10, 1, 12);
        Predicate<Integer> belowEight = value -> value < 8;

        System.out.println("filter: "
                + values.stream().filter(belowEight).toList());
        System.out.println("takeWhile: "
                + values.stream().takeWhile(belowEight).toList());
        System.out.println("dropWhile: "
                + values.stream().dropWhile(belowEight).toList());
        System.out.println("limit(4): "
                + values.stream().limit(4).toList());
        System.out.println("skip(2): "
                + values.stream().skip(2).toList());

        System.out.println("filter then limit: "
                + values.stream().filter(belowEight).limit(4).toList());
        System.out.println("limit then filter: "
                + values.stream().limit(4).filter(belowEight).toList());

        System.out.println("takeWhile first fails: "
                + List.of(9, 3, 6).stream().takeWhile(belowEight).toList());
        System.out.println("dropWhile first fails: "
                + List.of(9, 3, 6).stream().dropWhile(belowEight).toList());
    }
}
```

Lưu mã trong `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
filter: [3, 6, 2, 4, 1]
takeWhile: [3, 6, 2]
dropWhile: [8, 4, 10, 1, 12]
limit(4): [3, 6, 2, 8]
skip(2): [2, 8, 4, 10, 1, 12]
filter then limit: [3, 6, 2, 4]
limit then filter: [3, 6, 2]
takeWhile first fails: []
dropWhile first fails: [9, 3, 6]
```

Phân tích kết quả:

1. `filter` giữ cả `4` và `1` vì chúng thỏa điều kiện, dù xuất hiện sau giá trị `8` và `10` không thỏa.
2. `takeWhile` chỉ lấy `3, 6, 2`. Khi gặp `8` lần đầu, nó kết thúc đoạn được lấy. `4` và `1` ở phía sau không được xét để đưa vào kết quả.
3. `dropWhile` bỏ `3, 6, 2` rồi giữ từ `8` đến hết. Phần còn lại vẫn có `4` và `1` dù chúng thỏa điều kiện.
4. `limit(4)` lấy bốn vị trí đầu, không quan tâm giá trị có nhỏ hơn 8 hay không.
5. `skip(2)` bỏ hai vị trí đầu và giữ từ phần tử thứ ba.
6. `filter(...).limit(4)` tìm phần tử đạt điều kiện trước, sau đó mới lấy tối đa bốn kết quả phù hợp. `limit(4).filter(...)` giới hạn bốn phần tử đầu trước rồi mới lọc; vì vậy kết quả khác nhau.
7. Nếu phần tử đầu tiên không thỏa predicate, `takeWhile` trả stream rỗng. `dropWhile` không có prefix nào để bỏ nên giữ nguyên toàn bộ stream có thứ tự.

## 3. Quy tắc prefix của takeWhile và dropWhile

Với ordered stream, prefix là đoạn phần tử liên tiếp tính từ đầu stream. Ranh giới xuất hiện tại phần tử đầu tiên không thỏa predicate.

Giả sử predicate là `p`:

```text
Nguồn:       A  B  C  D  E  F
Predicate:   ✓  ✓  ✓  ✗  ✓  ✗

takeWhile:   A  B  C
dropWhile:   ✗  ✗  ✗  D  E  F
filter:      A  B  C     E
```

Trong sơ đồ, các dấu ✓ và ✗ mô tả kết quả predicate. `takeWhile` chỉ giữ prefix trước ranh giới D. `dropWhile` bỏ prefix đó, giữ D và mọi phần tử sau D. `filter` tiếp tục giữ tất cả phần tử thỏa điều kiện ở cả hai phía ranh giới.

Các trường hợp biên:

| Dữ liệu theo encounter order | `takeWhile(p)` | `dropWhile(p)` |
|---|---|---|
| Stream rỗng | Rỗng | Rỗng |
| Mọi phần tử đều thỏa | Giữ tất cả | Rỗng |
| Không phần tử nào thỏa | Rỗng | Giữ tất cả |
| Phần tử đầu tiên không thỏa | Rỗng | Giữ tất cả |
| Một prefix thỏa, sau đó có phần tử không thỏa | Giữ prefix | Giữ từ phần tử không thỏa đầu tiên trở đi |

Predicate phải không null. Nếu truyền predicate null, thao tác ném `NullPointerException` khi xây dựng pipeline.

## 4. Khác biệt với filter

`filter` kiểm tra điều kiện trên từng phần tử mà pipeline xử lý. Nó không kết thúc việc chọn phần tử chỉ vì một phần tử không thỏa. Một phần tử phía sau vẫn có thể được giữ nếu thỏa predicate.

`takeWhile` và `dropWhile` chỉ có ý nghĩa prefix khi stream có encounter order. Chúng dùng vị trí xuất hiện của phần tử đầu tiên không thỏa để xác định ranh giới.

Ví dụ:

```java
List<Integer> values = List.of(2, 4, 9, 6, 8);
Predicate<Integer> even = value -> value % 2 == 0;

System.out.println(values.stream().filter(even).toList());
System.out.println(values.stream().takeWhile(even).toList());
System.out.println(values.stream().dropWhile(even).toList());
```

Kết quả:

```text
[2, 4, 6, 8]
[2, 4]
[9, 6, 8]
```

Sau `9`, `filter` vẫn giữ `6` và `8`. `takeWhile` dừng tại `9`. `dropWhile` giữ `9` và phần còn lại, kể cả những số chẵn phía sau.

Dùng `filter` khi cần lọc mọi phần tử theo điều kiện. Dùng `takeWhile` khi cần lấy một đoạn đầu còn thỏa điều kiện. Dùng `dropWhile` khi cần bỏ đoạn đầu thỏa điều kiện và xử lý phần còn lại.

## 5. Khác biệt với limit và skip

`limit(n)` và `skip(n)` dựa trên số lượng phần tử, không dựa trên điều kiện. Với ordered stream, `limit(3)` lấy ba phần tử đầu và `skip(3)` bỏ ba phần tử đầu.

`takeWhile(p)` có số phần tử đầu ra phụ thuộc dữ liệu và predicate. Nó có thể trả về 0, 1 hoặc nhiều phần tử. `dropWhile(p)` cũng không nhận số lượng cố định; vị trí bắt đầu phần còn lại phụ thuộc vào lần đầu predicate không thỏa.

Ví dụ với cùng nguồn:

```java
List<Integer> values = List.of(3, 6, 2, 8, 4, 10, 1, 12);
Predicate<Integer> belowEight = value -> value < 8;

List<Integer> prefix = values.stream()
        .takeWhile(belowEight)
        .toList();

List<Integer> firstFour = values.stream()
        .limit(4)
        .toList();

List<Integer> suffix = values.stream()
        .dropWhile(belowEight)
        .toList();

List<Integer> afterTwo = values.stream()
        .skip(2)
        .toList();
```

`prefix` là `[3, 6, 2]` vì điều kiện dừng tại `8`. `firstFour` là `[3, 6, 2, 8]` vì lấy đúng bốn vị trí đầu. `suffix` là `[8, 4, 10, 1, 12]` vì bỏ ba phần tử đầu thỏa điều kiện. `afterTwo` là `[2, 8, 4, 10, 1, 12]` vì bỏ đúng hai vị trí đầu.

Cần lưu ý thứ tự kết hợp thao tác. `filter(p).limit(n)` có nghĩa là lọc trước rồi lấy tối đa n phần tử phù hợp. `limit(n).filter(p)` chỉ lọc trong n phần tử đầu. Hai pipeline không nhất thiết cho cùng kết quả.

Tương tự, `filter(p).skip(n)` bỏ n phần tử trong tập kết quả đã lọc, còn `skip(n).filter(p)` bỏ n phần tử nguồn trước khi lọc.

`limit` nhận số lượng không âm; `skip` cũng nhận số lượng không âm. Truyền số âm cho một trong hai thao tác sẽ ném `IllegalArgumentException`. Với `limit(0)`, kết quả rỗng; `skip(0)` giữ nguyên tất cả phần tử.

## 6. Encounter order, unordered stream và parallel stream

Các quy tắc prefix ở trên áp dụng trực tiếp cho stream có encounter order, ví dụ `List.stream()`. Encounter order là thứ tự mà nguồn stream cam kết cung cấp phần tử; nó không nhất thiết là thứ tự tăng dần hay giảm dần.

Khi stream là unordered, không có khái niệm prefix ổn định. Theo hợp đồng Stream API:

- `takeWhile` được phép lấy bất kỳ tập con nào của các phần tử thỏa predicate, kể cả tập rỗng. Nếu mọi phần tử đều thỏa, nó lấy tất cả; nếu không phần tử nào thỏa, nó lấy rỗng.
- `dropWhile` được phép bỏ bất kỳ tập con nào của các phần tử thỏa predicate, kể cả tập rỗng. Nếu mọi phần tử đều thỏa, nó bỏ tất cả; nếu không phần tử nào thỏa, nó không bỏ phần tử nào.
- `filter` vẫn giữ mọi phần tử thỏa predicate; thứ tự kết quả không được bảo đảm khi nguồn không có encounter order.
- `limit` và `skip` cũng không cam kết chọn/bỏ những phần tử cụ thể theo thứ tự ban đầu khi stream unordered.

Có thể bỏ ràng buộc thứ tự bằng `unordered()` khi nghiệp vụ không phụ thuộc vào thứ tự:

```java
List<Integer> selected = values.parallelStream()
        .unordered()
        .filter(value -> value < 8)
        .toList();
```

Không gọi `unordered()` chỉ để tối ưu nếu kết quả cần giữ đúng thứ tự nguồn hoặc cần prefix chính xác. Bỏ encounter order làm thay đổi ngữ nghĩa của những thao tác phụ thuộc thứ tự.

Với ordered parallel stream, `takeWhile` và `dropWhile` có thể tốn chi phí đáng kể vì runtime phải xác định ranh giới prefix theo encounter order. `limit` và `skip` cũng có thể cần phối hợp để bảo toàn đúng các vị trí đầu stream. Khi thứ tự không có ý nghĩa với bài toán, stream unordered có thể cho phép xử lý song song hiệu quả hơn; hãy đo hiệu năng và xác minh rằng thay đổi ngữ nghĩa là chấp nhận được.

## 7. Tính lazy, short-circuiting và sử dụng stream

Các intermediate operation chỉ mô tả pipeline. Predicate hoặc thao tác chọn phần tử được thực thi khi terminal operation bắt đầu tiêu thụ stream.

- `filter` là stateless intermediate operation. Nó không giữ một prefix hoặc bộ đếm vị trí.
- `takeWhile` là stateful và short-circuiting intermediate operation: với ordered stream, khi đã xác định phần tử đầu tiên không thỏa, không có phần tử sau nó được đưa vào kết quả.
- `dropWhile` là stateful intermediate operation: nó cần xác định ranh giới trước khi phát ra phần suffix.
- `limit` là stateful và short-circuiting; `skip` là stateful vì phải bỏ qua số phần tử đầu theo yêu cầu.

Short-circuiting của `takeWhile` hoặc `limit` không có nghĩa mọi predicate invocation trong parallel pipeline sẽ dừng tức thì tại đúng thời điểm một thread tìm thấy ranh giới. Các tác vụ đã được thực hiện song song có thể đã xử lý thêm phần tử. Không dựa vào số lần gọi predicate hoặc side effect bên trong predicate để điều khiển nghiệp vụ.

Một stream cũng chỉ được tiêu thụ một lần. Nếu cần so sánh nhiều thao tác như ví dụ trên, hãy tạo stream mới từ nguồn cho mỗi pipeline; không gọi nhiều terminal operation trên cùng một stream đã tiêu thụ.

## 8. Bảng chọn thao tác

| Nhu cầu | Chọn |
|---|---|
| Lấy tất cả phần tử thỏa điều kiện, kể cả sau các phần tử không thỏa | `filter` |
| Lấy đoạn đầu liên tiếp cho đến khi gặp phần tử đầu tiên không thỏa | `takeWhile` |
| Bỏ đoạn đầu liên tiếp thỏa điều kiện, giữ phần còn lại | `dropWhile` |
| Lấy tối đa n phần tử đầu theo encounter order | `limit` |
| Bỏ n phần tử đầu theo encounter order | `skip` |

Trước khi chọn, hãy tự hỏi điều kiện của bài toán là theo từng phần tử hay theo ranh giới của đoạn đầu, và số lượng cần xử lý có cố định hay phụ thuộc vào predicate. Câu trả lời sẽ xác định thao tác phù hợp.

`takeWhile` và `dropWhile` bổ sung khả năng xử lý prefix cho Stream API từ Java 9. Chúng giải quyết một yêu cầu khác với `filter`, `limit` và `skip`: xác định ranh giới đầu tiên theo predicate trên stream có thứ tự. Hiểu rõ encounter order, thứ tự kết hợp pipeline và hành vi của unordered/parallel stream giúp viết pipeline đúng kết quả và tránh giả định sai về hiệu năng.
