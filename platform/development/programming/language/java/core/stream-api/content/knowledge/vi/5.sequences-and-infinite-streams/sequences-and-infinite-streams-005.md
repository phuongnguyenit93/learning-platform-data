# Kết hợp nguồn vô hạn với limit, takeWhile và phép toán ngắn mạch

Một Stream **vô hạn** (*infinite stream*) có thể tiếp tục sinh phần tử mà không có điểm kết thúc tự nhiên. Java Stream API vẫn cho phép xử lý những nguồn như vậy nhờ cơ chế **đánh giá lười** (*lazy evaluation*): pipeline chỉ yêu cầu phần tử khi cần, và một số phép toán có thể dừng việc yêu cầu thêm dữ liệu sau khi đã đủ thông tin.

Bài học thuộc chương **Dãy số và Stream vô hạn** của module **JAVA_STREAM_API**. Đây là một ứng dụng quan trọng của mô hình xử lý dữ liệu khai báo bằng `filter`, `map`, `reduce` và `collect`: tạo một dãy theo quy tắc, giới hạn hoặc xác định điều kiện dừng, rồi lấy kết quả hữu hạn. Đồng thời, cần hiểu tác động của phép toán có trạng thái, xử lý song song, giới hạn tài nguyên và khả năng **không kết thúc** khi lựa chọn sai thứ tự pipeline.

## 1. Nguồn vô hạn thực chất hoạt động như thế nào?

Trong Java, `Stream.iterate` và `Stream.generate` thường được dùng để mô tả nguồn có thể sinh phần tử không giới hạn:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

// Dãy 1, 2, 3, 4, ... (về ý tưởng không có điểm kết thúc).
IntStream naturals = IntStream.iterate(1, n -> n + 1);

// Mỗi lần được yêu cầu sẽ lấy một giá trị từ Supplier.
Stream<String> repeated = Stream.generate(() -> "tick");
```

Các lời gọi trên **không tạo sẵn một tập vô hạn phần tử trong bộ nhớ**. Chúng thiết lập một nguồn được duyệt theo nhu cầu. Khi gọi terminal operation, các phần tử mới được tính toán và truyền qua các bước trung gian.

`Stream.iterate(seed, next)` (Java 8+) tạo Stream **tuần tự, có encounter order**, bắt đầu từ `seed`, rồi áp dụng hàm `next` để tính phần tử tiếp theo. `Stream.generate(supplier)` (Java 8+) tạo Stream **tuần tự, không có encounter order được bảo đảm**, gọi `supplier` để cung cấp phần tử theo nhu cầu.

| Cách tạo | Quy tắc tạo phần tử | Tính thứ tự | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `IntStream.iterate(1, n -> n + 1)` | Mỗi phần tử kế tiếp dựa trên phần tử trước | Có encounter order | Dãy chỉ số, số thứ tự, cấp số cộng |
| `Stream.iterate(seed, next)` | Phát triển trạng thái từ giá trị trước | Có encounter order | Dãy ngày, trạng thái bất biến, cấp số nhân |
| `Stream.generate(supplier)` | Supplier được gọi mỗi khi cần phần tử | Không có encounter order được bảo đảm | Tạo mẫu độc lập, sinh dữ liệu thử nghiệm |
| `Stream.iterate(seed, hasNext, next)` | Chỉ tiếp tục khi `hasNext` đúng | Có encounter order | Dãy có điều kiện dừng ngay tại nguồn (Java 9+) |

> **“Vô hạn” ở đây chỉ cách xây nguồn, không khẳng định chương trình thực tế chạy mãi.** Ví dụ `IntStream.iterate(1, n -> n + 1)` sử dụng `int`, nên nếu duyệt quá dài thì số nguyên có thể tràn. Khi cần dãy số lớn thực sự tăng mãi, hãy cân nhắc `BigInteger` hoặc miền dữ liệu phù hợp.

## 2. limit(n): chỉ lấy tối đa n phần tử

`limit(long maxSize)` là **phép toán trung gian có khả năng ngắn mạch** (*short-circuiting intermediate operation*). Nó chỉ cho tối đa `maxSize` phần tử đi tiếp từ vị trí được đặt trong pipeline.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> firstFive = IntStream.iterate(1, n -> n + 1)
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

System.out.println(firstFive); // [1, 2, 3, 4, 5]
```

Trình tự:

1. `iterate` mô tả nguồn có thể sinh liên tiếp các số.
2. `limit(5)` chỉ cho năm số đi qua và không yêu cầu số thứ sáu.
3. `boxed()` chuyển các giá trị `int` thành `Integer`.
4. `collect` tiêu thụ năm giá trị đó để tạo `List`.

`limit(0)` tạo pipeline không có phần tử đầu ra; `limit` với đối số âm ném `IllegalArgumentException`. Phép toán chỉ giới hạn **số phần tử đi qua nó**, không đặt giới hạn trực tiếp cho số lần đánh giá các bước trước.

### Vị trí limit thay đổi kết quả

Giả sử ta muốn lấy ba số chẵn đầu tiên từ dãy tự nhiên:

```java
List<Integer> firstThreeEven = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(3)
    .boxed()
    .collect(Collectors.toList());
// [2, 4, 6]
```

Pipeline phải xem lần lượt `1` đến `6` để tìm được ba số chẵn. Nếu chuyển `limit` lên trước:

```java
List<Integer> evenAmongFirstThree = IntStream.iterate(1, n -> n + 1)
    .limit(3)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.toList());
// [2]
```

Biểu thức thứ hai chỉ xét **ba số đầu tiên của nguồn**, sau đó mới lọc. Cả hai đều kết thúc, nhưng trả lời hai câu hỏi khác nhau.

### Có limit vẫn có thể không kết thúc

`limit(3)` không bảo đảm thành công nếu **bước trước nó không bao giờ cung cấp đủ ba phần tử**:

```java
// KHÔNG CHẠY: không có số âm nào trong dãy BigInteger dương này.
// Stream.iterate(BigInteger.ONE, n -> n.add(BigInteger.ONE))
//     .filter(n -> n.signum() < 0)
//     .limit(3)
//     .collect(Collectors.toList());
```

`filter` ở đây sẽ tiếp tục tìm kiếm vô hạn vì không có phần tử nào vượt qua. Đây là quy tắc quan trọng nhất khi kết hợp nguồn vô hạn với phép toán trung gian: **phải bảo đảm có đường đi đến điểm dừng, bao gồm đủ phần tử hoặc một điều kiện kết thúc khác**.

## 3. takeWhile(predicate): lấy phần đầu liên tiếp thỏa điều kiện

`takeWhile` được thêm từ **Java 9**. Với Stream **có encounter order**, nó cho ra *đoạn đầu dài nhất* gồm các phần tử liên tiếp thỏa predicate; ngay khi gặp phần tử đầu tiên không thỏa, nó ngừng lấy thêm phần tử của dãy theo cách duyệt tuần tự thông thường.

```java
import java.util.stream.IntStream;

List<Integer> belowSix = IntStream.iterate(1, n -> n + 1)
    .takeWhile(n -> n < 6)
    .boxed()
    .collect(Collectors.toList());
// [1, 2, 3, 4, 5]
```

Nếu `predicate` sai ngay ở phần tử đầu tiên, kết quả rỗng. Nếu `predicate` luôn đúng trên một nguồn vô hạn, `takeWhile` không tạo được điểm dừng cho terminal cần tất cả phần tử.

### takeWhile khác filter ở đâu?

Cho dãy hữu hạn `[1, 2, 3, 4, 5, 6]`:

```java
List<Integer> prefix = IntStream.rangeClosed(1, 6)
    .takeWhile(n -> n % 2 != 0)
    .boxed()
    .collect(Collectors.toList());
// [1] vì gặp số 2 thì dừng.

List<Integer> odds = IntStream.rangeClosed(1, 6)
    .filter(n -> n % 2 != 0)
    .boxed()
    .collect(Collectors.toList());
// [1, 3, 5] vì filter xem toàn bộ nguồn.
```

| Phép toán | Trên nguồn có thứ tự | Ý nghĩa của điều kiện |
| --- | --- | --- |
| `filter(p)` | Kiểm tra từng phần tử trong phần nguồn được tiêu thụ; loại phần tử không đạt | “Giữ mọi phần tử thỏa `p`” |
| `takeWhile(p)` | Giữ đoạn đầu liên tiếp thỏa `p` và dừng tại lần sai đầu tiên | “Tiếp tục **chừng nào** `p` còn đúng” |
| `limit(n)` | Giữ tối đa `n` phần tử tại vị trí đó | “Chỉ lấy `n` phần tử đầu tiên” |

Vì vậy, `takeWhile(n -> n < 100)` trên dãy số **tăng dần** là một cách xác định ngưỡng dừng. Nếu dữ liệu dao động quanh ngưỡng, `takeWhile` dừng tại **lần vượt ngưỡng đầu tiên**, dù sau đó có thể lại xuất hiện giá trị hợp lệ. Với yêu cầu giữ mọi giá trị dưới ngưỡng, dùng `filter` và một điều kiện giới hạn phù hợp.

### Dùng BigInteger tránh tràn số trong dãy tăng

```java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<BigInteger> powersOfTwo = Stream
    .iterate(BigInteger.ONE, value -> value.shiftLeft(1))
    .takeWhile(value -> value.compareTo(BigInteger.valueOf(100)) < 0)
    .collect(Collectors.toList());

System.out.println(powersOfTwo);
// [1, 2, 4, 8, 16, 32, 64]
```

Mỗi lần tạo phần tử, giá trị gấp đôi phần tử trước. Khi giá trị đạt `128`, predicate sai và pipeline có thứ tự dừng. `BigInteger` tránh được vấn đề tràn `int`/`long` trong ví dụ này, nhưng vẫn phải chú ý bộ nhớ nếu yêu cầu giá trị hoặc số lượng phần tử quá lớn.

### Nguồn hữu hạn bằng iterate ba tham số

Java 9 còn hỗ trợ `Stream.iterate(seed, hasNext, next)` (và biến thể cho primitive Stream):

```java
List<Integer> values = IntStream
    .iterate(1, n -> n <= 5, n -> n + 1)
    .boxed()
    .collect(Collectors.toList());
// [1, 2, 3, 4, 5]
```

Điều kiện `hasNext` được kiểm tra trước khi phát phần tử tương ứng. Cách này diễn đạt điểm dừng ngay tại nguồn, hữu ích khi bản thân quy tắc sinh dãy đã có giới hạn. `takeWhile` lại hữu ích khi ta muốn **áp điều kiện dừng lên một Stream đã được xây dựng**.

## 4. Phép toán ngắn mạch ở terminal operation

Ngoài `limit` và `takeWhile` ở nhóm **trung gian**, Java còn có các **terminal operation ngắn mạch**: chúng có thể xác định kết quả mà không cần xem hết nguồn.

| Terminal | Dừng sớm khi nào? | Trên nguồn vô hạn |
| --- | --- | --- |
| `findFirst()` | Đã tìm được phần tử đầu tiên theo encounter order (nếu có) | Có thể kết thúc nhanh nếu phần tử phù hợp xuất hiện. |
| `findAny()` | Đã tìm được một phần tử bất kỳ | Thường phù hợp nếu không cần thứ tự, đặc biệt với parallel stream. |
| `anyMatch(p)` | Gặp một phần tử thỏa `p` | Trả về `true` khi tìm được bằng chứng; nếu không có, có thể không dừng. |
| `allMatch(p)` | Gặp một phần tử **không** thỏa `p` | Trả về `false` ngay khi có phản ví dụ; nếu tất cả đều thỏa, có thể không dừng. |
| `noneMatch(p)` | Gặp một phần tử thỏa `p` | Trả về `false` ngay khi có phản ví dụ; nếu không phần tử nào thỏa, có thể không dừng. |

Ví dụ:

```java
import java.util.stream.IntStream;

int firstMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 7 == 0)
    .findFirst()
    .orElse(-1);
// 7

boolean hasMultipleOfEleven = IntStream.iterate(1, n -> n + 1)
    .anyMatch(n -> n % 11 == 0);
// true: tìm thấy 11.

boolean allLessThanFive = IntStream.iterate(1, n -> n + 1)
    .allMatch(n -> n < 5);
// false: gặp 5.

boolean noMultipleOfFour = IntStream.iterate(1, n -> n + 1)
    .noneMatch(n -> n % 4 == 0);
// false: gặp 4.
```

Các ví dụ trên dùng Stream tuần tự để diễn giải số phần tử được kiểm tra. Khi xử lý song song, có thể có nhiều phần tử đang được xử lý trước khi tín hiệu ngắn mạch khiến công việc dừng lại.

### Vì sao kết quả đúng không luôn đồng nghĩa sẽ kết thúc?

Xét `Stream.generate(() -> 1).allMatch(n -> n == 1)`. Tất cả phần tử mà chương trình gặp đều bằng `1`, nhưng trên nguồn vô hạn, không có thời điểm nào terminal có thể chứng minh **mọi** phần tử còn lại cũng thỏa chỉ bằng cách duyệt hết nguồn. Nó không có điều kiện dừng.

Tương tự:

- `Stream.generate(() -> 1).anyMatch(n -> n == 2)` có thể chạy mãi vì không bao giờ gặp `2`.
- `Stream.generate(() -> 1).noneMatch(n -> n == 2)` có thể chạy mãi vì không thể xác nhận đã hết phần tử.
- `Stream.iterate(BigInteger.ONE, n -> n.add(BigInteger.ONE)).filter(n -> n.signum() < 0).findFirst()` không có phần tử phù hợp để trả về.

Với Stream **rỗng**, các quy tắc ngắn mạch vẫn đúng: `anyMatch` trả về `false`, `allMatch` và `noneMatch` đều trả về `true` mà không gọi predicate. Đây là hệ quả logic của việc không có phần tử phản ví dụ.

## 5. Thứ tự pipeline quyết định khả năng kết thúc

Một nguồn vô hạn thường an toàn để đưa vào terminal cần toàn bộ dữ liệu **chỉ sau khi pipeline đã trở thành hữu hạn**. Nhưng cần xét cả các bước đứng **trước** điểm giới hạn.

| Pipeline (bỏ qua cú pháp import) | Có kết thúc không? | Lý do |
| --- | --- | --- |
| `IntStream.iterate(1, n -> n + 1).limit(10).sum()` | Có | Chỉ mười phần tử được yêu cầu. |
| `IntStream.iterate(1, n -> n + 1).filter(n -> n % 2 == 0).limit(10).sum()` | Có | Bộ lọc tìm được đủ mười số chẵn. |
| `IntStream.iterate(1, n -> n + 1).takeWhile(n -> n <= 10).sum()` | Có | Điều kiện sai ở `11`. |
| `Stream.generate(() -> 1).filter(n -> n == 2).limit(3).count()` | Không kết thúc theo cách đánh giá thông thường | Bộ lọc không phát ra phần tử nào, nên `limit` không đủ ba phần tử. |
| `Stream.generate(() -> 1).distinct().limit(2).count()` | Không kết thúc theo cách đánh giá thông thường | Chỉ có một giá trị khác nhau, nên không thể tìm giá trị thứ hai. |
| `IntStream.iterate(1, n -> n + 1).sorted().limit(3).boxed().collect(Collectors.toList())` | Không kết thúc theo cách đánh giá thông thường | `sorted` cần nhận hết nguồn trước khi phát giá trị đầu tiên. |
| `IntStream.iterate(1, n -> n + 1).limit(3).sorted().boxed().collect(Collectors.toList())` | Có | `sorted` chỉ phải sắp xếp ba phần tử đầu. |

> Các kết luận “không kết thúc” mô tả **ngữ nghĩa và cách đánh giá thông thường**, không tính đến việc chương trình bị ngắt, hết tài nguyên hoặc ngoại lệ như tràn số. Không nên đưa các pipeline được đánh dấu không kết thúc vào ứng dụng thực tế chỉ để kiểm tra.

`sorted` là phép toán trung gian **có trạng thái**, thường cần đệm toàn bộ đầu vào trước khi trả ra phần tử đã sắp xếp. Vì vậy, giới hạn sau `sorted` không cứu được pipeline sử dụng nguồn vô hạn. `distinct` cũng có trạng thái, nhưng có thể phát giá trị mới dần; nó chỉ kết thúc với `limit(k)` nếu thật sự gặp đủ `k` giá trị khác nhau.

**Quy tắc thiết kế:** đặt bước giới hạn trước thao tác phải nhìn toàn bộ dữ liệu, nếu yêu cầu nghiệp vụ cho phép. Ví dụ “sắp xếp 100 phần tử đầu tiên” là `limit(100).sorted()`; còn “lấy 100 phần tử nhỏ nhất trong toàn bộ dãy vô hạn” thường không phải bài toán có thể giải bằng `sorted().limit(100)`.

## 6. Kết hợp limit và takeWhile để có hai ranh giới

Trong thực tế có thể đặt **cả giới hạn số lượng và điều kiện giá trị**, giúp tránh việc thu thập dữ liệu quá nhiều nếu quy tắc sinh dãy thay đổi:

```java
List<Integer> bounded = IntStream.iterate(1, n -> n + 1)
    .takeWhile(n -> n <= 100)
    .limit(10)
    .boxed()
    .collect(Collectors.toList());
// [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

Ở đây, `limit(10)` quyết định điểm kết thúc trước, nên pipeline không cần chờ `takeWhile` gặp `101`. Nếu đổi `limit(10)` thành `limit(200)`, `takeWhile` sẽ dừng tại `101` và kết quả chứa 100 số.

Có thể đảo thứ tự hai phép toán trong một số bài toán đơn giản mà vẫn giữ kết quả, nhưng **không nên mặc định mọi phép toán trung gian có thể đổi chỗ**. Với `filter`, `sorted`, `skip` hoặc điều kiện có tác dụng phụ, ý nghĩa và chi phí có thể thay đổi rõ rệt.

Ví dụ thực tế: tạo dãy thời gian cách nhau 15 phút, chỉ lấy các mốc trước 12 giờ và tối đa sáu mốc:

```java
import java.time.LocalTime;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<LocalTime> slots = Stream
    .iterate(LocalTime.of(9, 0), t -> t.plusMinutes(15))
    .takeWhile(t -> t.isBefore(LocalTime.NOON))
    .limit(6)
    .collect(Collectors.toList());

// [09:00, 09:15, 09:30, 09:45, 10:00, 10:15]
```

Lưu ý: `LocalTime.plusMinutes` quay về đầu ngày sau nửa đêm. Nếu cần mô hình thời gian không quay vòng trên nhiều ngày, hãy dùng `LocalDateTime` hoặc `Instant` và điều kiện dừng thích hợp; ví dụ trên chỉ lấy sáu mốc trước trưa trong cùng buổi.

## 7. Encounter order, parallel stream và takeWhile

`Stream.iterate` trả về Stream có encounter order, còn `Stream.generate` không bảo đảm encounter order. Sự khác nhau này đặc biệt quan trọng với `takeWhile`:

- Trên nguồn **có thứ tự**, `takeWhile(p)` lấy đoạn đầu dài nhất gồm các phần tử liên tiếp thỏa `p`.
- Trên nguồn **không có thứ tự**, `takeWhile(p)` được phép chọn một tập con phù hợp của các phần tử thỏa `p`; không có khái niệm “đoạn đầu tiên” đáng tin cậy.
- Trên Stream song song có thứ tự, `limit`, `takeWhile` và `findFirst` vẫn tuân theo hợp đồng thứ tự đầu ra, nhưng chi phí phối hợp và duy trì thứ tự có thể đáng kể. Việc thực thi predicate có thể xảy ra trên các phần tử bổ sung trước khi toàn bộ tác vụ dừng.

Nếu bài toán cần “dừng ở **lần vượt ngưỡng đầu tiên**” của một chuỗi tăng theo thời gian, hãy **giữ encounter order**. Không gọi `unordered()` chỉ để mong tăng tốc, vì điều đó làm thay đổi ý nghĩa của `takeWhile`.

Ngược lại, `findAny` không hứa lấy phần tử đầu tiên. Với bài toán “tìm một phần tử phù hợp bất kỳ”, nó có thể cho phép triển khai song song hiệu quả hơn `findFirst`.

Không dùng các lệnh ghi log trong `peek` hay tác dụng phụ bên trong `map` làm cơ sở để kết luận chính xác số lần phần tử đã được xét. Java Stream có quyền tối ưu hóa, bỏ qua một số bước hoặc đánh giá thêm phần tử khi xử lý song song, miễn tuân thủ hợp đồng kết quả.

## 8. Rủi ro về tài nguyên và cách phòng tránh

Tính lười giúp **không phải lưu toàn bộ nguồn trong bộ nhớ**, nhưng không tự bảo vệ chương trình khỏi pipeline kéo dài vô hạn. Một terminal cần hết dữ liệu, như `collect(toList())`, `toArray()`, `reduce(...)` hay `sum()`, có thể không trả về nếu đầu vào vẫn vô hạn.

Các nguyên tắc thực hành:

1. **Xác định điểm dừng trước khi chạy:** giới hạn số lượng bằng `limit`, ngưỡng đơn điệu bằng `takeWhile` hoặc điều kiện nguồn bằng `iterate(seed, hasNext, next)`.
2. **Kiểm tra bước phía trước giới hạn:** `filter` có thực sự cho đủ kết quả? `distinct` có đủ giá trị khác nhau? `sorted` có bị đặt trước giới hạn không?
3. **Không nhầm lẫn giới hạn phần tử với giới hạn thời gian:** `limit(10)` vẫn có thể chờ mãi nếu nguồn chặn khi lấy phần tử. Để có timeout thật sự cần cơ chế điều khiển/hủy ở tầng phù hợp; `limit` không tự cung cấp timeout.
4. **Chú ý phép toán tích lũy:** tránh sưu tập lượng dữ liệu quá lớn vào `List`; có thể dùng `forEach` với xử lý phù hợp, nhưng vẫn phải có cơ chế dừng và quản lý tác dụng phụ.
5. **Tránh tràn số và quay vòng trạng thái:** `int`, `long`, `LocalTime` đều có miền giá trị hữu hạn; một điều kiện tưởng như chắc chắn đổi từ đúng sang sai có thể không đổi do tràn hoặc quay vòng.
6. **Cân nhắc song song:** chia một dãy sinh phụ thuộc vào phần tử trước không nhất thiết đem lại hiệu năng tốt; `parallel()` không bảo đảm nhanh hơn và không thay thế yêu cầu lambda không có trạng thái chia sẻ.
7. **Quản lý nguồn tài nguyên:** `Stream.generate` với supplier đọc mạng/tệp vẫn cần cơ chế đóng tài nguyên liên quan; terminal kết thúc không có nghĩa mọi tài nguyên bên ngoài tự động được giải phóng.

Với pipeline cần lặp dãy cho nhiều phép tính, tạo Stream **mới** cho mỗi terminal. Stream Java chỉ được tiêu thụ một lần.

## 9. Ví dụ tổng hợp chạy được với Java 9+

Chương trình sau cho thấy ba cách tạo kết quả hữu hạn từ nguồn vô hạn. Chỉ cần JDK 9 trở lên, không dùng thư viện ngoài:

```java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class InfiniteStreamDemo {
    public static void main(String[] args) {
        List<Integer> evenNumbers = IntStream.iterate(1, n -> n + 1)
            .filter(n -> n % 2 == 0)
            .limit(5)
            .boxed()
            .collect(Collectors.toList());

        List<BigInteger> powersOfTwo = Stream
            .iterate(BigInteger.ONE, n -> n.shiftLeft(1))
            .takeWhile(n -> n.compareTo(BigInteger.valueOf(20)) < 0)
            .collect(Collectors.toList());

        boolean hasMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
            .anyMatch(n -> n % 7 == 0);

        System.out.println("Năm số chẵn: " + evenNumbers);
        System.out.println("Lũy thừa của hai dưới 20: " + powersOfTwo);
        System.out.println("Có bội số của 7: " + hasMultipleOfSeven);
    }
}
```

Kết quả:

```text
Năm số chẵn: [2, 4, 6, 8, 10]
Lũy thừa của hai dưới 20: [1, 2, 4, 8, 16]
Có bội số của 7: true
```

Trong ví dụ, `filter().limit(5)` cần tìm đủ năm số chẵn; `takeWhile` dừng khi giá trị đầu tiên không nhỏ hơn 20 là `32`; `anyMatch` dừng khi thấy bội số đầu tiên của 7.

## 10. Tự kiểm tra

**Câu 1.** Dự đoán kết quả hai pipeline:

```java
// A
IntStream.iterate(1, n -> n + 1).limit(6)
    .filter(n -> n % 2 == 0).boxed()
    .collect(Collectors.toList());

// B
IntStream.iterate(1, n -> n + 1).filter(n -> n % 2 == 0)
    .limit(6).boxed().collect(Collectors.toList());
```

**Đáp án:** A là `[2, 4, 6]` vì chỉ lọc sáu giá trị đầu nguồn. B là `[2, 4, 6, 8, 10, 12]` vì `limit(6)` chỉ đếm phần tử đã vượt qua bộ lọc.

**Câu 2.** `Stream.generate(() -> 10).distinct().limit(2).collect(Collectors.toList())` có kết thúc không?

**Đáp án:** Không kết thúc theo cách đánh giá thông thường: sau phần tử `10` đầu tiên, `distinct` sẽ loại mọi phần tử `10` tiếp theo. `limit(2)` không bao giờ nhận đủ hai phần tử.

**Câu 3.** Với dãy `[3, 4, 3, 2, 1]`, `takeWhile(n -> n >= 3)` khác `filter(n -> n >= 3)` thế nào?

**Đáp án:** `takeWhile` cho `[3, 4, 3]`, dừng ở `2`; `filter` cũng cho `[3, 4, 3]` trong **dữ liệu cụ thể này**, nhưng vẫn xét hết `1`. Thay dãy thành `[3, 2, 4, 3, 1]` sẽ thấy khác biệt rõ: `takeWhile` cho `[3]`, còn `filter` cho `[3, 4, 3]`.

**Câu 4.** Vì sao `Stream.generate(() -> 1).allMatch(n -> n == 1)` không trả về `true` sau một số lần gọi predicate?

**Đáp án:** Không có phần tử nào bác bỏ điều kiện nên `allMatch` chưa đủ thông tin để dừng; nguồn lại không có kết thúc tự nhiên. Muốn kiểm tra một **mẫu hữu hạn**, hãy dùng `limit(n)` trước `allMatch`.

**Câu 5.** Muốn kiểm tra liệu có số chia hết cho 7 trong 100 số tự nhiên đầu tiên, nên giới hạn ở đâu?

```java
boolean found = IntStream.iterate(1, n -> n + 1)
    .limit(100)
    .anyMatch(n -> n % 7 == 0);
// true
```

**Giải thích:** `limit(100)` xác định tập cần kiểm tra; `anyMatch` có thể dừng sớm khi tìm được `7`. Nếu yêu cầu kiểm tra toàn bộ đúng 100 phần tử, dùng một terminal khác hoặc phép tính phù hợp với mục tiêu thay vì `anyMatch`.

## Ghi nhớ

Khi làm việc với Stream vô hạn trong **JAVA_STREAM_API**, điều quan trọng không chỉ là tạo nguồn bằng `iterate` hay `generate`, mà còn là **chứng minh pipeline có thể dừng**. `limit` giới hạn số phần tử đầu ra; `takeWhile` (Java 9+) lấy đoạn đầu liên tiếp thỏa điều kiện trên nguồn có thứ tự; `findFirst`, `findAny`, `anyMatch`, `allMatch` và `noneMatch` có thể kết thúc ngay khi đủ bằng chứng. Một `filter` không cho phần tử nào đi qua, `distinct` không tìm đủ phần tử mới hoặc `sorted` đứng trước giới hạn có thể khiến pipeline chạy mãi. Hãy kết hợp đúng thứ tự thao tác, kiểm soát tài nguyên và giữ ngữ nghĩa encounter order khi cần điểm dừng chính xác.
