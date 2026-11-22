# Chia cửa sổ cố định bằng `Gatherers.windowFixed`

Trong **Java Stream API**, các phép toán `filter`, `map`, `reduce` và `collect` thường xử lý từng phần tử hoặc tổng hợp toàn bộ nguồn. Nhưng nhiều tác vụ thực tế lại cần xử lý **từng lô gồm một số phần tử liên tiếp**: gửi dữ liệu theo batch, tính tổng sau mỗi ba giao dịch, đóng gói các dòng log để xuất báo cáo hoặc chia một dãy đo thành các nhóm không chồng lắp.

Từ **Java 24**, API **Stream Gatherers** cung cấp `Gatherers.windowFixed(windowSize)` để biểu diễn trực tiếp phép chia này. Gatherer là một dạng intermediate operation có thể giữ trạng thái; nó được đưa vào pipeline bằng `Stream.gather(...)`, và cho phép đầu ra là những **cửa sổ** chứa nhiều phần tử nguồn.

Bài học thuộc chương **Stream Gatherer** của mô-đun `JAVA_STREAM_API`. Chúng ta sẽ học cách chia cửa sổ cố định, xử lý cửa sổ cuối không đủ kích thước, phối hợp với `map`, `filter`, `collect`, phân biệt với cửa sổ trượt, và nhận diện các ràng buộc về thứ tự, bộ nhớ, tài nguyên và hiệu năng.

## 1. Cửa sổ cố định là gì?

Cho dãy có encounter order:

```text
Nguồn:  [1, 2, 3, 4, 5, 6, 7, 8]
                         windowSize = 3

Cửa sổ 1: [1, 2, 3]
Cửa sổ 2:          [4, 5, 6]
Cửa sổ 3:                   [7, 8]
```

Mỗi cửa sổ nhận **tối đa `windowSize` phần tử liên tiếp theo encounter order**. Các cửa sổ:

- **Không chồng lắp**: một phần tử nguồn thuộc một cửa sổ duy nhất.
- **Giữ thứ tự tương đối** của các phần tử trong cửa sổ.
- Được phát lần lượt từ trái sang phải đối với nguồn có encounter order.
- **Không bắt buộc đầy ở cuối**: nếu còn 1–2 phần tử khi `windowSize = 3`, chúng tạo thành cửa sổ cuối ngắn hơn.

Đây là **cửa sổ theo số lượng phần tử** (*count-based tumbling window*), không phải cửa sổ thời gian. `windowFixed(3)` nghĩa là ba phần tử, **không có nghĩa ba giây hoặc ba phút**.

Ký hiệu: nếu nguồn hữu hạn có `n` phần tử, kích thước cửa sổ `k > 0`, thì số cửa sổ là:

\[
\operatorname{windows}(n,k) =
\begin{cases}
0, & n=0 \\
\lceil n/k \rceil, & n>0
\end{cases}
\]

Mỗi cửa sổ đầy đủ có `k` phần tử. Cửa sổ cuối có phần dư `n % k` nếu phần dư khác 0; khi `n` chia hết cho `k`, **không tạo thêm cửa sổ rỗng**.

## 2. Phiên bản JDK và chữ ký API

`Gatherer`, `Gatherers` và `Stream.gather` là API chính thức từ **Java 24**. Các phiên bản Java 22 và 23 có Stream Gatherers ở trạng thái **preview**, phải bật preview và chú ý khác biệt giữa các bản. Bài này sử dụng cú pháp API ổn định của Java 24+.

Chữ ký của phương thức:

```java
public static <TR> Gatherer<TR, ?, List<TR>>
windowFixed(int windowSize);
```

Thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `TR` | Kiểu phần tử nguồn, đồng thời là kiểu phần tử trong mỗi cửa sổ. |
| `windowSize` | Số phần tử tối đa trong mỗi cửa sổ; phải **ít nhất là 1**. |
| `Gatherer<TR, ?, List<TR>>` | Một Gatherer nhận phần tử `TR` và phát `List<TR>`. |
| `Stream.gather(...)` | Đưa Gatherer vào pipeline như một intermediate operation. |

Ví dụ tối thiểu:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Sau `gather`, mỗi phần tử đi tiếp trong pipeline **không còn là `Integer`**, mà là **`List<Integer>`**. Do đó `map` ở phía sau xử lý **một cửa sổ**, chẳng hạn `map(List::size)` hoặc `map(batch -> batch.stream().mapToInt(...).sum())`.

### Khi `windowSize` không hợp lệ

```java
import java.util.stream.Gatherers;

Gatherers.windowFixed(1);   // Hợp lệ
Gatherers.windowFixed(20);  // Hợp lệ, kể cả nguồn chỉ có 3 phần tử

// Ném IllegalArgumentException:
// Gatherers.windowFixed(0);
// Gatherers.windowFixed(-3);
```

Điều kiện được kiểm tra trên **tham số kích thước**, không phụ thuộc nguồn có rỗng hay không. Không dùng `windowSize = 0` để biểu diễn một lô rỗng; nếu cần “không xử lý”, hãy giải quyết điều kiện đó trước khi tạo Gatherer.

## 3. Các trường hợp biên cần thuộc lòng

Đây là hành vi được mô tả trong API:

| Nguồn | `windowSize` | Kết quả |
| --- | ---: | --- |
| `[]` | 3 | `[]` |
| `[1]` | 3 | `[[1]]` |
| `[1,2]` | 3 | `[[1,2]]` |
| `[1,2,3]` | 3 | `[[1,2,3]]` |
| `[1,2,3,4]` | 3 | `[[1,2,3],[4]]` |
| `[1,2,3,4,5,6]` | 3 | `[[1,2,3],[4,5,6]]` |
| `[1,2,3]` | 1 | `[[1],[2],[3]]` |
| `[1,2,3]` | 10 | `[[1,2,3]]` |

Đặc biệt:

1. **Nguồn rỗng không tạo cửa sổ rỗng**. Kết quả là stream rỗng, nên `toList()` trả danh sách ngoài rỗng.
2. **Nguồn ngắn hơn kích thước cửa sổ vẫn tạo một cửa sổ**, nếu nguồn có ít nhất một phần tử.
3. **Không mất phần dư**. Cửa sổ cuối ngắn hơn là hành vi hợp lệ, không phải lỗi.
4. `windowSize = 1` biến mỗi phần tử thành một danh sách chỉ chứa chính phần tử đó; không phải công cụ tối ưu nếu mục tiêu chỉ là `map` từng phần tử.

Kiểm tra nhanh bằng Java 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<String>> empty = Stream.<String>empty()
    .gather(Gatherers.windowFixed(4))
    .toList();

List<List<String>> shortInput = Stream.of("A", "B")
    .gather(Gatherers.windowFixed(4))
    .toList();

System.out.println(empty);      // []
System.out.println(shortInput); // [[A, B]]
```

Nếu nghiệp vụ **chỉ chấp nhận lô đủ `k` phần tử**, đó là yêu cầu bổ sung của ứng dụng, không phải hợp đồng mặc định của `windowFixed`.

## 4. Ví dụ đầy đủ: tạo batch từ danh sách mã giao dịch

Giả sử hệ thống cần chia các mã giao dịch thành lô tối đa ba mã để hiển thị, đối soát hoặc gửi sang một bước xử lý khác.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Gatherers;

public class FixedWindowDemo {
    public static void main(String[] args) {
        List<String> transactionIds = Arrays.asList(
            "TX-001", "TX-002", "TX-003",
            "TX-004", "TX-005", "TX-006",
            "TX-007"
        );

        List<List<String>> batches = transactionIds.stream()
            .gather(Gatherers.windowFixed(3))
            .toList();

        for (List<String> batch : batches) {
            System.out.println(batch);
        }
    }
}
```

Kết quả:

```text
[TX-001, TX-002, TX-003]
[TX-004, TX-005, TX-006]
[TX-007]
```

Pipeline này là:

```text
List<String>
   |
   +--> stream()                 Stream<String>
   |
   +--> gather(windowFixed(3))   Stream<List<String>>
   |
   +--> toList()                 List<List<String>>
```

Vì nguồn là `List` có encounter order, thứ tự mã trong từng lô đúng theo thứ tự xuất hiện. Nếu mã giao dịch ban đầu chưa theo thứ tự nghiệp vụ (chẳng hạn chưa sắp theo thời điểm), `windowFixed` **không tự sắp xếp** chúng.

## 5. Cửa sổ trả về không sửa đổi được

Theo hợp đồng Java 24, **mỗi cửa sổ** do `windowFixed` phát ra là một `List` **không thể sửa đổi** (*unmodifiable*). Gọi phương thức thay đổi cấu trúc cửa sổ như `add`, `remove` hoặc `set` sẽ bị từ chối bằng `UnsupportedOperationException`.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> batches = Stream.of(10, 20, 30, 40)
    .gather(Gatherers.windowFixed(3))
    .toList();

List<Integer> first = batches.get(0);
System.out.println(first); // [10, 20, 30]

// first.add(99);     // UnsupportedOperationException
// first.set(0, 99);  // UnsupportedOperationException
// first.remove(0);   // UnsupportedOperationException
```

Hãy phân biệt:

- **Danh sách cửa sổ bên trong** được `windowFixed` bảo đảm là unmodifiable.
- **Danh sách bên ngoài** ở ví dụ cũng unmodifiable vì dùng `Stream.toList()` (Java 16+).
- **Các đối tượng phần tử bên trong** có thể vẫn mutable. Một cửa sổ không sửa đổi được **không tự sao chép sâu** từng phần tử.

Ví dụ, nếu cửa sổ giữ các `StringBuilder`, người dùng vẫn có thể gọi `append` trên một `StringBuilder` đã được phát:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

StringBuilder value = new StringBuilder("A");

List<List<StringBuilder>> batches = Stream.of(value)
    .gather(Gatherers.windowFixed(2))
    .toList();

value.append("B");
System.out.println(batches.get(0).get(0)); // AB
```

Nếu cần snapshot thực sự bất biến, hãy chuyển phần tử về kiểu giá trị bất biến hoặc sao chép các thuộc tính cần thiết **trước hoặc trong quá trình tạo batch**. Việc giữ một cửa sổ unmodifiable không bảo đảm dữ liệu phần tử có trạng thái cố định vĩnh viễn.

## 6. Xử lý từng cửa sổ bằng `map`, `filter` và `collect`

Điểm mạnh của `windowFixed` là nó trả về một **Stream của các cửa sổ**, nên vẫn có thể tiếp tục pipeline.

### Tính tổng của mỗi ba phần tử

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<Integer> totals = IntStream.rangeClosed(1, 8)
    .boxed()
    .gather(Gatherers.windowFixed(3))
    .map(batch -> batch.stream()
        .mapToInt(Integer::intValue)
        .sum())
    .toList();

System.out.println(totals); // [6, 15, 15]
```

Giải thích kết quả: `[1,2,3]` có tổng 6; `[4,5,6]` có tổng 15; `[7,8]` cũng có tổng 15. **Không tự đệm thêm số 0** vào lô cuối, trừ khi có quy tắc nghiệp vụ yêu cầu điều đó.

`IntStream` không có `gather` trực tiếp theo chữ ký `Stream<T>.gather` của Java 24. Vì vậy `.boxed()` ở ví dụ chuyển `IntStream` thành `Stream<Integer>` trước khi gọi `gather`. Cách này tạo các đối tượng `Integer`; với khối lượng số cực lớn và yêu cầu hiệu năng cao, nên đo chi phí boxing hoặc chọn giải pháp khác.

### Chỉ giữ những cửa sổ có tổng vượt ngưỡng

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> largeWindows = Stream.of(1, 2, 3, 8, 9, 10, 4)
    .gather(Gatherers.windowFixed(3))
    .filter(batch -> batch.stream()
        .mapToInt(Integer::intValue).sum() >= 20)
    .toList();

System.out.println(largeWindows); // [[8, 9, 10]]
```

Ở đây `filter` áp dụng **sau khi chia cửa sổ**, nghĩa là **loại cả cửa sổ** không đạt yêu cầu, chứ không loại các phần tử riêng lẻ trước khi chia.

### Đếm số cửa sổ, không phải số phần tử nguồn

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

long windowCount = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(2))
    .count();

System.out.println(windowCount); // 3
```

Sau `gather`, `count()` đếm **số danh sách được phát**, không đếm số phần tử ở bên trong các danh sách đó.

## 7. Vị trí `filter` thay đổi ranh giới cửa sổ

Hai pipeline trông giống nhau nhưng có ý nghĩa khác:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> filterFirst = Stream.of(1, 2, 3, 4, 5, 6)
    .filter(n -> n % 2 == 0)
    .gather(Gatherers.windowFixed(2))
    .toList();

List<List<Integer>> filterWindows = Stream.of(1, 2, 3, 4, 5, 6)
    .gather(Gatherers.windowFixed(2))
    .filter(batch -> batch.contains(2))
    .toList();

System.out.println(filterFirst);   // [[2, 4], [6]]
System.out.println(filterWindows); // [[1, 2]]
```

- **`filter` trước `gather`**: phần tử bị loại không chiếm vị trí trong cửa sổ; các phần tử còn lại được gom lại từ đầu theo thứ tự mới.
- **`filter` sau `gather`**: ranh giới đã xác định; predicate quyết định giữ hay bỏ **cả lô**.

Tương tự, nếu gọi `sorted()` trước `gather`, các cửa sổ được lập theo **thứ tự đã sắp xếp**; nếu gọi `distinct()` trước `gather`, số phần tử và ranh giới có thể thay đổi. Vì thế **vị trí các phép toán trung gian là một phần của yêu cầu nghiệp vụ**, không chỉ là chi tiết viết code.

## 8. `limit` trước và sau cửa sổ khác nhau thế nào?

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> firstFiveItems = IntStream.rangeClosed(1, 8)
    .boxed()
    .limit(5)
    .gather(Gatherers.windowFixed(3))
    .toList();

List<List<Integer>> firstTwoWindows = IntStream.rangeClosed(1, 8)
    .boxed()
    .gather(Gatherers.windowFixed(3))
    .limit(2)
    .toList();

System.out.println(firstFiveItems);  // [[1, 2, 3], [4, 5]]
System.out.println(firstTwoWindows); // [[1, 2, 3], [4, 5, 6]]
```

Ở pipeline đầu, `limit(5)` giới hạn **năm phần tử nguồn** rồi mới chia cửa sổ. Ở pipeline sau, `limit(2)` giới hạn **hai phần tử của stream cửa sổ** — tức là hai danh sách, tổng cộng sáu giá trị ở ví dụ.

Đây là một kiểu **short-circuiting**: terminal operation có thể kết thúc mà không cần đi hết nguồn, nếu downstream đã nhận đủ cửa sổ. Tuy nhiên, không nên dựa vào số lần mapper/`peek` được gọi để khẳng định hệ thống luôn đọc đúng bằng `2 * windowSize` phần tử: tối ưu, buffering và cách tiêu thụ có thể ảnh hưởng số thao tác quan sát được.

Với nguồn vô hạn, thường phải có điều kiện dừng:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> firstThreeBatches =
    Stream.iterate(1, n -> n + 1)
        .gather(Gatherers.windowFixed(4))
        .limit(3)
        .toList();

System.out.println(firstThreeBatches);
// [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
```

Không được gọi `toList()` trên toàn bộ cửa sổ của **một nguồn vô hạn không có giới hạn**, vì terminal operation không thể hoàn tất và việc giữ dữ liệu sẽ tiêu tốn tài nguyên không giới hạn.

## 9. Xử lý cửa sổ cuối không đủ kích thước

`windowFixed` **giữ phần dư**. Ứng dụng cần chọn một trong các chính sách sau:

| Chính sách | Khi áp dụng | Với `[1,2,3,4,5]`, `k=3` |
| --- | --- | --- |
| **Chấp nhận lô cuối ngắn** | Batch API cho phép số lượng từ 1 đến `k`. | `[[1,2,3],[4,5]]` |
| **Chỉ xử lý lô đầy** | Thuật toán bắt buộc đúng `k` giá trị. | `[[1,2,3]]`; phần dư phải được xử lý riêng nếu cần. |
| **Đệm tới đủ số phần tử** | Giao thức có giá trị đệm rõ nghĩa. | `[[1,2,3],[4,5,PAD]]` |
| **Từ chối đầu vào thiếu** | Toàn bộ dữ liệu phải có kích thước chia hết cho `k`. | Báo lỗi trước hoặc sau bước kiểm tra kích thước. |

### Chỉ giữ các lô đầy

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

int batchSize = 3;

List<List<Integer>> complete = IntStream.rangeClosed(1, 8)
    .boxed()
    .gather(Gatherers.windowFixed(batchSize))
    .filter(batch -> batch.size() == batchSize)
    .toList();

System.out.println(complete); // [[1, 2, 3], [4, 5, 6]]
```

Lựa chọn này **làm mất hai phần tử cuối** khỏi kết quả. Trong hệ thống giao dịch, xử lý thanh toán hoặc nhật ký quan trọng, **không được bỏ phần dư âm thầm**. Cần quyết định rõ phần dữ liệu còn lại sẽ được giữ cho lô sau, xử lý riêng, hay báo lỗi.

### Đệm phần dư bằng giá trị đại diện

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

int batchSize = 3;

List<List<String>> padded = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(batchSize))
    .map(batch -> {
        List<String> copy = new ArrayList<>(batch);
        while (copy.size() < batchSize) {
            copy.add("MISSING");
        }
        return List.copyOf(copy);
    })
    .toList();

System.out.println(padded);
// [[A, B, C], [D, E, MISSING]]
```

Phải **tạo bản sao** trước khi thêm phần tử, vì danh sách do `windowFixed` phát là unmodifiable. Trong ví dụ, `"MISSING"` chỉ là giá trị giả định; với dữ liệu thực tế, phải chắc chắn giá trị đệm không thể bị hiểu nhầm là một giao dịch hoặc số đo có thật.

## 10. `windowFixed` khác `windowSliding` thế nào?

Cả hai đều tạo cửa sổ theo số lượng phần tử, nhưng **quy tắc dịch cửa sổ** khác nhau:

```text
Nguồn:       [1, 2, 3, 4, 5, 6, 7]

Fixed(3):    [1, 2, 3]
                      [4, 5, 6]
                               [7]

Sliding(3):  [1, 2, 3]
                [2, 3, 4]
                   [3, 4, 5]
                      [4, 5, 6]
                         [5, 6, 7]
```

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<Integer> source = IntStream.rangeClosed(1, 7)
    .boxed()
    .toList();

List<List<Integer>> fixed = source.stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

List<List<Integer>> sliding = source.stream()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(fixed);
// [[1, 2, 3], [4, 5, 6], [7]]

System.out.println(sliding);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6], [5, 6, 7]]
```

| Thuộc tính | `windowFixed(k)` | `windowSliding(k)` |
| --- | --- | --- |
| Ranh giới | Chia thành các nhóm liên tiếp **không chồng lắp**. | Mỗi nhóm tiếp theo trượt **một phần tử**. |
| Phần tử xuất hiện ở mấy nhóm? | Tối đa một. | Có thể ở nhiều nhóm. |
| Kích thước nhóm cuối | Có thể ngắn hơn `k`. | Với nguồn có ít nhất `k` phần tử, các nhóm trượt đủ `k`; nếu nguồn ngắn hơn `k`, có một nhóm ngắn. |
| Số nhóm khi `n > 0` | `ceil(n / k)`. | `1` nếu `n < k`; nếu `n >= k`, có `n - k + 1` nhóm. |
| Phù hợp | Đóng gói batch, tổng hợp theo lô. | Trung bình trượt, so sánh chuỗi giá trị lân cận. |

Ví dụ một lần tính tổng cho các **lô ngày không giao nhau** nên dùng fixed window. Nếu cần tính **trung bình của ba phép đo liên tiếp tại mỗi vị trí**, sliding window phù hợp hơn. Đừng gọi `windowFixed` rồi kỳ vọng kết quả chồng lắp như rolling average.

## 11. Cửa sổ theo thứ tự phần tử, không phải phân nhóm theo khóa

`Collectors.groupingBy` phân loại các phần tử có **cùng khóa**. `Gatherers.windowFixed` phân chia theo **vị trí tương đối trong một chuỗi có thứ tự**.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<String> events = List.of("A", "B", "A", "B", "A");

List<List<String>> batches = events.stream()
    .gather(Gatherers.windowFixed(2))
    .toList();

Map<String, List<String>> byValue = events.stream()
    .collect(Collectors.groupingBy(value -> value));

System.out.println(batches); // [[A, B], [A, B], [A]]
System.out.println(byValue.get("A")); // [A, A, A]
```

Không thể thay `windowFixed(k)` bằng `groupingBy(value -> value)` nếu mục tiêu là mỗi batch có `k` phần tử liên tiếp. Tương tự, `partitioningBy` chia thành hai nhóm Boolean chứ không đóng gói theo số phần tử.

Nếu nguồn là `HashSet` hay một stream không có encounter order, vị trí của phần tử không được bảo đảm ổn định theo thứ tự nghiệp vụ. **Cửa sổ cố định có ý nghĩa mạnh nhất trên nguồn có encounter order rõ ràng**, như `List` hoặc `Stream.of(...)`.

## 12. Dự án thực tế: lập báo cáo theo lô giao dịch

Giả sử mỗi giao dịch có mã và số tiền theo **đơn vị nguyên nhỏ nhất**. Cứ ba giao dịch liên tiếp tạo thành một lô; với mỗi lô, ta muốn biết số giao dịch và tổng tiền.

Đây là một chương trình Java 24+ hoàn chỉnh:

```java
import java.util.List;
import java.util.stream.Gatherers;

public class TransactionBatchReport {
    record Transaction(String id, long amountInMinorUnits) {}

    record BatchSummary(
        String firstTransaction,
        String lastTransaction,
        int transactionCount,
        long totalAmount
    ) {}

    static BatchSummary summarize(List<Transaction> batch) {
        long total = batch.stream()
            .mapToLong(Transaction::amountInMinorUnits)
            .sum();

        return new BatchSummary(
            batch.get(0).id(),
            batch.get(batch.size() - 1).id(),
            batch.size(),
            total
        );
    }

    public static void main(String[] args) {
        List<Transaction> data = List.of(
            new Transaction("T-01", 1200L),
            new Transaction("T-02", 1800L),
            new Transaction("T-03", 3000L),
            new Transaction("T-04",  500L),
            new Transaction("T-05",  700L),
            new Transaction("T-06", 1100L),
            new Transaction("T-07",  250L)
        );

        List<BatchSummary> report = data.stream()
            .gather(Gatherers.windowFixed(3))
            .map(TransactionBatchReport::summarize)
            .toList();

        report.forEach(System.out::println);
    }
}
```

Kết quả có ba dòng báo cáo, tương ứng các lô:

```text
BatchSummary[firstTransaction=T-01, lastTransaction=T-03,
             transactionCount=3, totalAmount=6000]
BatchSummary[firstTransaction=T-04, lastTransaction=T-06,
             transactionCount=3, totalAmount=2300]
BatchSummary[firstTransaction=T-07, lastTransaction=T-07,
             transactionCount=1, totalAmount=250]
```

Những điểm cần chú ý:

1. `data.stream()` có encounter order đúng theo danh sách giao dịch.
2. `gather(windowFixed(3))` phân chia thành ba lô, giữ cả giao dịch cuối.
3. `summarize(batch)` có thể gọi `get(0)` vì **không có cửa sổ rỗng**.
4. Mỗi kết quả `BatchSummary` là một record chỉ chứa `String` và các primitive, phù hợp để công bố dữ liệu không sửa đổi được.
5. Nếu số lượng giao dịch rất lớn, dùng `sum()` trên `long` vẫn có thể bị tràn. Hệ thống tài chính cần chính sách kiểm tra giới hạn, `Math.addExact` hoặc kiểu số thích hợp.

Chương trình dùng batch để **tổng hợp**, không thực sự gửi mạng hay ghi DB. Nếu thay `summarize` bằng một API có side effect, còn cần giới hạn đồng thời, retry, idempotency, timeout và xử lý lô gửi dở; `windowFixed` không tự cung cấp giao dịch nguyên tử hoặc bảo đảm gửi đúng một lần.

## 13. Tạo báo cáo mà không lưu mọi cửa sổ đến cuối

`toList()` trên stream các cửa sổ **lưu toàn bộ cửa sổ** vào một danh sách kết quả. Khi nguồn rất lớn, điều này có thể tốn nhiều bộ nhớ.

Nếu chỉ cần các số liệu cuối cùng, có thể tính trong `map` rồi thu một lượng kết quả nhỏ hơn, hoặc tổng hợp tiếp:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

LongSummaryStatistics sumsOfBatches = IntStream.rangeClosed(1, 1_000)
    .boxed()
    .gather(Gatherers.windowFixed(100))
    .mapToLong(batch -> batch.stream()
        .mapToLong(Integer::longValue)
        .sum())
    .summaryStatistics();

System.out.println(sumsOfBatches.getCount()); // 10 lô
System.out.println(sumsOfBatches.getSum());   // 500500
```

Ở đây, terminal operation trả về **một bộ thống kê của các tổng theo lô**, thay vì danh sách lồng chứa toàn bộ 1.000 giá trị. Nếu chỉ cần tổng toàn bộ nguồn, `IntStream.rangeClosed(1, 1_000).asLongStream().sum()` đơn giản hơn và không cần windowing.

### Với nguồn I/O như `Files.lines`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FileBatchSizes {
    public static List<Integer> countLinesPerBatch(Path path)
            throws IOException {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .gather(Gatherers.windowFixed(500))
                .map(List::size)
                .toList();
        }
    }
}
```

`Files.lines` giữ tài nguyên I/O nên cần `try-with-resources` để đóng stream. `collect`, `toList` hay `gather` **không thay thế trách nhiệm đóng nguồn**. Trong ví dụ này, đầu ra là danh sách **số dòng của mỗi batch**, không giữ toàn bộ nội dung tệp.

Tuy nhiên, nếu tệp có dòng cực lớn hoặc số lượng lô rất nhiều, vẫn cần tính toán bộ nhớ tổng thể. Nếu nguồn đã có đặc điểm cần giữ tính nhất quán (tệp thay đổi lúc đang đọc), `windowFixed` không tự khóa hoặc chụp snapshot nguồn dữ liệu.

## 14. Cân nhắc bộ nhớ và kích thước cửa sổ

Theo tài liệu API của `Gatherers.windowFixed`, cửa sổ có thể được **cấp phát liên tục và sớm** để tối ưu hiệu quả. Điều này có một hệ quả đáng chú ý: chọn `windowSize` cực lớn cho nguồn rất ngắn có thể tiêu tốn bộ nhớ **không tương xứng với lượng dữ liệu thực tế**.

Ví dụ:

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

// Tránh làm theo thói quen: kích thước cửa sổ khổng lồ
// không tự trở nên rẻ chỉ vì nguồn có 2 phần tử.
var windows = Stream.of("A", "B")
    .gather(Gatherers.windowFixed(1_000_000));
```

Đoạn trên chỉ minh họa một **cấu hình có nguy cơ cấp phát lớn**, không khẳng định chính xác số byte hoặc thời điểm cấp phát trên mọi JDK. Nên chọn kích thước cửa sổ theo giới hạn tài nguyên, đặc điểm dữ liệu và yêu cầu xử lý thực tế.

Phân biệt hai tầng bộ nhớ:

- **Buffer của Gatherer**: giữ những phần tử cần thiết để lập một cửa sổ, chi phí liên quan tới `windowSize` và cách triển khai.
- **Kết quả terminal operation**: `toList()` giữ tất cả cửa sổ đã phát; nếu muốn xử lý dòng chảy theo lô mà không giữ toàn bộ, cần terminal operation/downstream phù hợp.

Lưu ý `windowFixed` có thể giúp **xử lý theo batch**, nhưng không tự giải quyết giới hạn bộ nhớ của tất cả các thao tác phía sau. Một `map(batch -> hugeObject)` rồi `toList()` vẫn có thể dùng rất nhiều bộ nhớ.

## 15. Thứ tự, song song và ngữ nghĩa xử lý

Cửa sổ cố định **phụ thuộc thứ tự**. Nếu có nguồn `[1,2,3,4,5,6]`, ta kỳ vọng `[[1,2,3],[4,5,6]]`, không phải các nhóm ngẫu nhiên chỉ vì có hai worker.

Những điều cần nhớ:

1. Trên nguồn có encounter order, cửa sổ giữ thứ tự các phần tử như hợp đồng API.
2. Nếu nguồn vốn **unordered** hoặc bị gọi `unordered()`, không nên kỳ vọng các phần tử cụ thể sẽ nằm trong batch nào theo thứ tự nghiệp vụ.
3. Thêm `parallel()` **không bảo đảm tăng tốc**. Windowing là phép toán trung gian có trạng thái và phụ thuộc ranh giới; cách thực thi còn phụ thuộc khả năng chia nguồn và triển khai Gatherer.
4. Không sửa một `ArrayList` nguồn ngay trong `map`/ `forEach` khi Stream đang duyệt. Hành vi các lambda nên *non-interfering* và, nếu có thể, *stateless*.
5. Không giả định `windowFixed` tự phân phối các lô tới một pool worker với số lượng tác vụ hoặc thứ tự thực thi cụ thể.

Nếu cần **xử lý đồng thời từng batch** sau khi đã chia cửa sổ, đó là một yêu cầu khác với việc **chia cửa sổ**. Java 24 còn có `Gatherers.mapConcurrent(maxConcurrency, mapper)` để xử lý phép ánh xạ với mức đồng thời được giới hạn và vẫn bảo toàn thứ tự đầu ra theo hợp đồng. Chỉ dùng nó khi mapper phù hợp, việc xử lý từng batch độc lập và bạn đã xác định cách xử lý lỗi hoặc side effect.

Ví dụ về **phép tính thuần**, không thực hiện I/O:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<Integer> totals = IntStream.rangeClosed(1, 12)
    .boxed()
    .gather(Gatherers.windowFixed(3))
    .gather(Gatherers.mapConcurrent(
        2,
        batch -> batch.stream().mapToInt(Integer::intValue).sum()
    ))
    .toList();

System.out.println(totals); // [6, 15, 24, 33]
```

Ví dụ này minh họa **hai Gatherer nối tiếp**. Nó không chứng minh cách dùng `mapConcurrent` nhanh hơn `map` thường; với phép cộng ba số, overhead đồng thời hầu như không đáng để lựa chọn trước khi đo đạc.

## 16. So sánh với cách chia List theo chỉ số trước Java 24

Trước Stream Gatherers, nếu nguồn đã là một `List` có chỉ số và bạn muốn chia theo vị trí, có thể dùng `IntStream.range` hoặc `subList`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> source = List.of(1, 2, 3, 4, 5, 6, 7, 8);
int batchSize = 3;

List<List<Integer>> batches = IntStream
    .range(0, (source.size() + batchSize - 1) / batchSize)
    .mapToObj(batchIndex -> {
        int from = batchIndex * batchSize;
        int to = Math.min(from + batchSize, source.size());
        return List.copyOf(source.subList(from, to));
    })
    .toList();

System.out.println(batches); // [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Đây là một lựa chọn phù hợp khi bạn đã có danh sách **truy cập theo chỉ số**. Mẫu này dùng `List.copyOf` (Java 10+) để tạo danh sách cửa sổ không sửa đổi được, nhưng không sao chép sâu các phần tử. Nếu phần tử có thể `null`, `List.copyOf` sẽ từ chối `null`, nên cần chính sách dữ liệu trước khi áp dụng.

Một điểm khác: `source.subList(from, to)` **thường là view** liên kết với danh sách gốc, không phải snapshot độc lập. Trả trực tiếp các `subList` có thể khiến sửa đổi nguồn ảnh hưởng kết quả hoặc làm view không còn hợp lệ. Tạo bản sao tránh phụ thuộc cấu trúc danh sách gốc, dù vẫn chỉ sao chép tham chiếu tới phần tử.

`windowFixed` không yêu cầu nguồn phải là `List` có chỉ số; nó làm việc với một `Stream<T>` và giữ tính khai báo của pipeline. Khi dữ liệu vốn từ iterator, file hoặc một stream đã qua nhiều bước chuyển đổi, đây có thể là API dễ diễn đạt ý định hơn.

## 17. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi `windowFixed` với `k = 0` hoặc số âm | `IllegalArgumentException`. | Bắt buộc `k >= 1`. |
| Mong lô cuối luôn có đúng `k` phần tử | Có thể xử lý sai bản ghi cuối. | Chấp nhận, đệm, từ chối hoặc giữ phần dư theo chính sách. |
| Nghĩ `windowFixed(3)` là ba giây | Nhầm cửa sổ theo số lượng với cửa sổ theo thời gian. | Dùng đúng loại công cụ xử lý thời gian nếu cần. |
| Truyền trực tiếp `IntStream` vào `gather` | API `gather` dành cho `Stream<T>` tham chiếu. | Dùng `boxed()` hoặc lựa chọn xử lý primitive khác. |
| Gọi `window.add(...)` trên cửa sổ kết quả | `UnsupportedOperationException`. | Sao chép sang collection mutable nếu cần sửa. |
| Đặt `filter` sai vị trí | Ranh giới cửa sổ thay đổi hoặc bị loại cả lô. | Xác định muốn lọc phần tử hay lọc cửa sổ. |
| Dùng `limit(2)` sau `gather` và tưởng chỉ lấy 2 phần tử | Thực tế lấy tối đa **2 cửa sổ**. | Đặt `limit` theo đúng mức dữ liệu cần giới hạn. |
| Dùng cửa sổ rất lớn trên nguồn ngắn | Có nguy cơ cấp phát bộ nhớ quá mức. | Chọn `windowSize` hữu hạn, hợp lý theo tài nguyên. |
| Dùng `toList()` để giữ tất cả lô của nguồn khổng lồ | Đầu ra chiếm nhiều bộ nhớ. | Tổng hợp hoặc tiêu thụ từng lô khi phù hợp. |
| Dùng nguồn unordered rồi kỳ vọng nhóm ổn định | Mất ý nghĩa vị trí theo thứ tự nghiệp vụ. | Cấp encounter order rõ ràng trước khi chia. |
| Gửi batch tới API từ `forEach` rồi coi là giao dịch nguyên tử | Có thể gửi một phần trước khi lỗi xảy ra. | Thiết kế retry, idempotency, giới hạn concurrency và giám sát riêng. |
| So `windowFixed` với `windowSliding` mà bỏ qua chồng lắp | Sai số lô và tổng hợp. | Chọn đúng quy tắc cửa sổ theo yêu cầu. |

## 18. Kiểm thử ranh giới cửa sổ

Khi cần bảo đảm **không mất và không lặp phần tử**, nên kiểm thử trên nhiều kích thước đầu vào. Ví dụ Java 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class WindowFixedCheck {
    static void check(int n, int size) {
        List<Integer> source = IntStream.range(0, n)
            .boxed()
            .toList();

        List<List<Integer>> windows = source.stream()
            .gather(Gatherers.windowFixed(size))
            .toList();

        List<Integer> flattened = windows.stream()
            .flatMap(List::stream)
            .toList();

        if (!flattened.equals(source)) {
            throw new AssertionError("Mất, lặp hoặc đảo phần tử");
        }

        int expectedWindows = n == 0
            ? 0
            : 1 + (n - 1) / size;
        if (windows.size() != expectedWindows) {
            throw new AssertionError("Sai số cửa sổ");
        }

        for (int i = 0; i < windows.size(); i++) {
            int expectedSize = Math.min(size, n - i * size);
            if (windows.get(i).size() != expectedSize) {
                throw new AssertionError("Sai kích thước cửa sổ " + i);
            }
        }
    }

    public static void main(String[] args) {
        for (int k : new int[] {1, 2, 3, 8}) {
            for (int n = 0; n <= 30; n++) {
                check(n, k);
            }
        }
        System.out.println("Các kiểm tra cửa sổ đã đạt");
    }
}
```

Một số bất biến đáng kiểm tra:

- **Toàn vẹn phần tử**: ghép phẳng các cửa sổ của một nguồn có thứ tự phải được chính dãy nguồn (khi không có `filter` hoặc biến đổi làm đổi số phần tử).
- **Số cửa sổ**: `0` nếu nguồn rỗng; nếu không, bằng `ceil(n/k)`.
- **Kích thước**: mọi cửa sổ trừ cửa sổ cuối có đúng `k` phần tử; cửa sổ cuối có từ 1 đến `k`.
- **Không sửa đổi được**: gọi phương thức mutator trên một cửa sổ kết quả phải bị từ chối.
- **Không mất dữ liệu ở ranh giới**: kiểm tra riêng `n = k - 1`, `n = k`, `n = k + 1`, `n = 2k`, `n = 2k + 1`.

Các kiểm tra trên chứng minh hành vi đối với những đầu vào đã thử; chưa phải phép đo hiệu năng hoặc kiểm chứng mọi trường hợp nguồn concurrent/unordered.

## 19. Bài tập thực hành

**Bài 1 — Cửa sổ cơ bản.** Từ `Stream.of(10,20,30,40,50,60,70)`, dùng `windowFixed(3)` và dự đoán ba danh sách kết quả. Giải thích vì sao cửa sổ cuối chỉ có một phần tử.

**Bài 2 — Lọc đúng vị trí.** Với nguồn `[1,2,3,4,5,6]` và `k=2`, so sánh `filter(n -> n % 2 == 0)` trước `gather` với `filter(batch -> batch.contains(2))` sau `gather`. Viết rõ khác biệt về số lượng và nội dung cửa sổ.

**Bài 3 — Giữ hoặc bỏ phần dư.** Cho tám mã giao dịch và `k=3`. Thu tất cả lô trước; sau đó chỉ giữ lô có đúng ba phần tử. Có bao nhiêu giao dịch bị loại? Nếu đó là giao dịch tài chính, hãy đề xuất chính sách không mất dữ liệu.

**Bài 4 — Tổng theo lô.** Dùng `IntStream.rangeClosed(1, 10).boxed()`, chia `windowFixed(4)` rồi tính tổng trong mỗi lô. Kết quả dự kiến là `[10,26,19]`.

**Bài 5 — So sánh sliding.** Với `[1,2,3,4,5]`, hãy viết kết quả của `windowFixed(3)` và `windowSliding(3)`. Vì sao việc cộng tổng các cửa sổ trượt sẽ đếm nhiều phần tử hơn một lần?

**Bài 6 — Memory và API.** Vì sao `windowFixed(1_000_000)` trên một stream chỉ có hai phần tử vẫn có thể gây áp lực bộ nhớ? Vì sao `toList()` chứa mọi cửa sổ của nguồn khổng lồ không phải một pipeline tiết kiệm bộ nhớ?

**Bài 7 — Kiểm thử bất biến.** Viết hàm `check(n,k)` để xác minh: không mất/lặp phần tử; kích thước từng cửa sổ hợp lệ; số lượng cửa sổ đúng; cửa sổ trả về không sửa đổi được. Chạy trên nguồn rỗng và các kích thước ngay trước/sau bội của `k`.

**Bài 8 — Báo cáo lô.** Từ `Stream<Transaction>`, tạo báo cáo chứa count, tổng tiền và mã đầu/cuối của từng batch, theo `windowFixed(100)`. Nếu bổ sung việc gửi API thật, hãy mô tả cách tránh gửi lặp, giới hạn tác vụ đang chạy và xử lý lỗi chỉ xảy ra ở một batch.

## 20. Checklist áp dụng

- [ ] Dự án sử dụng Java 24+ cho Stream Gatherers API chính thức.
- [ ] Nguồn có encounter order nếu việc giữ thứ tự theo batch là bắt buộc.
- [ ] `windowSize` được xác thực lớn hơn 0 và có giới hạn hợp lý.
- [ ] Quy tắc xử lý phần dư cuối được viết thành yêu cầu nghiệp vụ.
- [ ] Đã phân biệt `filter` trên phần tử với `filter` trên cửa sổ.
- [ ] Đã phân biệt `limit` phần tử nguồn và `limit` số cửa sổ.
- [ ] Không gọi `add`, `remove`, `set` trên cửa sổ do Gatherer trả về.
- [ ] Đã kiểm tra tính mutable của các đối tượng phần tử nếu cần snapshot dữ liệu.
- [ ] Không dùng `windowFixed` thay cho cửa sổ thời gian hoặc cửa sổ trượt.
- [ ] Không giữ mọi cửa sổ trong bộ nhớ nếu đầu vào lớn và không cần lưu lại.
- [ ] Đã cân nhắc tài nguyên và việc đóng stream cho nguồn I/O.
- [ ] Không giả định song song hóa hoặc tối ưu hiệu năng nếu chưa đo.
- [ ] Nếu xử lý batch có side effect, có chính sách retry, idempotency và báo lỗi riêng.
- [ ] Đã kiểm tra nguồn rỗng, `k=1`, `n<k`, `n=k` và `n=k+1`.

**Ghi nhớ:** `Gatherers.windowFixed(k)` chia một `Stream<T>` có thứ tự thành `Stream<List<T>>` gồm các nhóm **liên tiếp, không chồng lắp**, mỗi nhóm tối đa `k` phần tử. Nguồn rỗng không có cửa sổ; cửa sổ cuối có thể ngắn; mỗi cửa sổ được bảo đảm **không sửa đổi được**. Đặt `map`, `filter`, `limit` đúng vị trí, chọn kích thước batch phù hợp tài nguyên và chỉ sử dụng windowing khi bài toán thực sự cần xử lý theo lô.

**Tài liệu chính thức:** [Gatherers.windowFixed — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html#windowFixed(int)); [Stream Gatherers — Oracle Java 24 Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html); [Stream.gather — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)).
