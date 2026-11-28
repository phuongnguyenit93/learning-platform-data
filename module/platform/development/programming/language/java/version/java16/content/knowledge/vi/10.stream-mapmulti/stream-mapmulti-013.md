# IntStream.mapMulti và IntMapMultiConsumer

`IntStream.mapMulti` là phương thức của Stream chuyên biệt cho kiểu nguyên thủy `int`. Với mỗi số nguyên nguồn, mapper có thể phát không, một hoặc nhiều số nguyên vào Stream kết quả thông qua một `IntConsumer`. Phương thức này phù hợp khi cần mở rộng một số thành nhiều số, duyệt một nhóm giá trị nguyên hoặc phát kết quả bằng vòng lặp và điều kiện.

Điểm cần phân biệt là `IntStream.mapMulti` nhận đầu vào kiểu `int` và cũng tạo đầu ra kiểu `int`. Nếu nguồn là Stream đối tượng và muốn phát các số nguyên, hãy dùng `Stream<T>.mapMultiToInt`. Hai phương thức cùng tạo `IntStream`, nhưng kiểu nguồn và mapper khác nhau.

## 1. IntStream.mapMulti là gì?

`IntStream.mapMulti` được bổ sung trong Java 16. Đây là thao tác trung gian thay thế mỗi phần tử `int` nguồn bằng không, một hoặc nhiều phần tử `int` đầu ra.

Chữ ký phương thức:

```java
IntStream mapMulti(IntMapMultiConsumer mapper)
```

`IntMapMultiConsumer` là functional interface thuộc package `java.util.stream`. Phương thức trừu tượng của nó có dạng:

```java
void accept(int value, IntConsumer downstream)
```

Trong đó:

- `value` là số nguyên hiện tại của Stream nguồn.
- `downstream` là `IntConsumer` dùng để phát các số nguyên kết quả.
- Mỗi lần gọi `downstream.accept(result)` sẽ phát một phần tử `int`.
- Mapper không trả về giá trị; nó gửi kết quả qua Consumer.

Có thể đọc chữ ký này như một quy tắc: nhận một số nguyên và dùng Consumer để phát ra các số nguyên tương ứng.

## 2. Vai trò của IntMapMultiConsumer và IntConsumer

Hai interface có liên quan nhưng đảm nhiệm hai vai trò khác nhau:

| Thành phần | Package | Vai trò |
|---|---|---|
| `IntMapMultiConsumer` | `java.util.stream` | Mapper nhận một `int` nguồn và Consumer phát kết quả |
| `IntConsumer` | `java.util.function` | Nhận một giá trị `int` đầu ra qua `accept(int)` |

Một lambda tương ứng có dạng:

```java
(value, downstream) -> {
    downstream.accept(value);
}
```

Tham số thứ nhất là dữ liệu nguồn. Tham số thứ hai là kênh phát kết quả. Tên `downstream` chỉ là tên biến; có thể đặt là `emit`, `output` hoặc `consumer` nếu giúp mã dễ đọc hơn.

Vì cả đầu vào và đầu ra đều là `int`, không có tham số kiểu generic `R` như `Stream<T>.mapMulti`. Do đó, không cần type witness như `.<Integer>mapMulti` khi gọi `IntStream.mapMulti`.

## 3. Phát không, một hoặc nhiều số nguyên

Số lần gọi `accept` quyết định số phần tử đầu ra mà một phần tử nguồn đóng góp:

| Cách mapper xử lý | Kết quả |
|---|---|
| Không gọi `downstream.accept` | Không phát phần tử |
| Gọi `downstream.accept` một lần | Phát một phần tử |
| Gọi `downstream.accept` nhiều lần | Phát nhiều phần tử |

Ví dụ, chỉ phát các số chẵn:

```java
import java.util.stream.IntStream;

int[] evenNumbers = IntStream.of(1, 2, 3, 4, 5, 6)
    .mapMulti((number, emit) -> {
        if (number % 2 == 0) {
            emit.accept(number);
        }
    })
    .toArray();
```

Kết quả:

```text
[2, 4, 6]
```

Các số lẻ không gọi `emit.accept`, nên không xuất hiện trong Stream kết quả. Ví dụ này tương đương với việc lọc số chẵn bằng `filter`; nó minh họa cơ chế phát không hoặc một kết quả của `mapMulti`.

Nếu mục tiêu duy nhất là lọc, `filter` thường rõ ý định hơn:

```java
import java.util.stream.IntStream;

int[] evenNumbers = IntStream.of(1, 2, 3, 4, 5, 6)
    .filter(number -> number % 2 == 0)
    .toArray();
```

## 4. Một số nguyên nguồn phát nhiều số nguyên

`IntStream.mapMulti` hữu ích khi mỗi giá trị nguồn cần được mở rộng thành một nhóm số nguyên. Ví dụ, mỗi số dương `n` phát ra dãy từ 1 đến `n`:

```java
import java.util.stream.IntStream;

int[] expanded = IntStream.of(3, 2, 4)
    .mapMulti((count, emit) -> {
        for (int value = 1; value <= count; value++) {
            emit.accept(value);
            if (value == count) {
                break;
            }
        }
    })
    .toArray();
```

Kết quả:

```text
[1, 2, 3, 1, 2, 1, 2, 3, 4]
```

Số nguồn `3` phát ba số, số nguồn `2` phát hai số và số nguồn `4` phát bốn số. Vòng lặp gọi Consumer theo thứ tự tăng dần nên từng nhóm kết quả giữ thứ tự đó.

Đây là dạng xử lý một-nhiều tự nhiên: mapper dùng một vòng lặp ngắn để phát các giá trị thay vì tạo một Stream con cho từng số nguồn.

## 5. Phát kết quả theo nhiều điều kiện

Một số nguyên có thể tạo ra các kết quả khác nhau tùy thuộc vào điều kiện. Ví dụ, với mỗi số, phát chính nó nếu là số dương và phát thêm số bình phương nếu nó lớn hơn một:

```java
import java.util.stream.IntStream;

int[] results = IntStream.of(-2, 0, 2, 3)
    .mapMulti((number, emit) -> {
        if (number > 0) {
            emit.accept(number);
        }

        if (number > 1) {
            emit.accept(number * number);
        }
    })
    .toArray();
```

Kết quả:

```text
[2, 4, 3, 9]
```

Các nhánh được kiểm tra độc lập. Với số `2`, mapper phát `2` rồi `4`; với số `3`, mapper phát `3` rồi `9`. Các số âm và số không không tạo kết quả.

Thứ tự đầu ra trong mỗi nhóm tuân theo thứ tự gọi `emit.accept`. Nếu đổi thứ tự hai câu lệnh phát, thứ tự kết quả tương ứng cũng đổi.

## 6. Ví dụ: phát các ước số của từng số nguồn

Một ứng dụng thực tế khác là mở rộng mỗi số thành danh sách các ước số của nó:

```java
import java.util.stream.IntStream;

int[] divisors = IntStream.of(6, 10, 7)
    .mapMulti((number, emit) -> {
        for (int candidate = 1; candidate <= number; candidate++) {
            if (number % candidate == 0) {
                emit.accept(candidate);
            }
            if (candidate == number) {
                break;
            }
        }
    })
    .toArray();
```

Kết quả:

```text
[1, 2, 3, 6, 1, 2, 5, 10, 1, 7]
```

Mỗi số nguồn phát các ước số theo thứ tự tăng dần. Số `6` phát bốn giá trị, số `10` phát bốn giá trị và số nguyên tố `7` phát hai giá trị là `1` và `7`.

Ví dụ này dùng vòng lặp đơn giản để dễ thấy cơ chế phát nhiều phần tử. Nếu số nguồn có thể rất lớn, cách thử mọi số từ `1` đến `number` có thể tốn thời gian; cần chọn thuật toán phù hợp với giới hạn dữ liệu của ứng dụng.

## 7. So sánh IntStream.mapMulti với map, filter và flatMap

Các thao tác có hình dạng đầu ra khác nhau:

| Thao tác | Kết quả từ một phần tử nguồn | Mục đích |
|---|---:|---|
| `map` | Chính xác một `int` | Chuyển một số thành một số khác |
| `filter` | Không hoặc một `int` | Giữ hoặc loại số hiện tại |
| `flatMap` | Không, một hoặc nhiều `int` | Chuyển thành `IntStream` con rồi làm phẳng |
| `mapMulti` | Không, một hoặc nhiều `int` | Phát số trực tiếp qua `IntConsumer` |

Dùng `map` khi mỗi số luôn tạo đúng một số:

```java
import java.util.stream.IntStream;

int[] doubled = IntStream.of(1, 2, 3)
    .map(number -> number * 2)
    .toArray();
```

Dùng `filter` khi chỉ giữ số thỏa điều kiện:

```java
import java.util.stream.IntStream;

int[] positives = IntStream.of(-2, 0, 3, 5)
    .filter(number -> number > 0)
    .toArray();
```

Dùng `flatMap` khi phép biến đổi tự nhiên trả về một `IntStream` con:

```java
import java.util.stream.IntStream;

int[] expanded = IntStream.of(2, 3)
    .flatMap(number -> IntStream.rangeClosed(1, number))
    .toArray();
```

Cùng kết quả có thể viết bằng `mapMulti`:

```java
import java.util.stream.IntStream;

int[] expanded = IntStream.of(2, 3)
    .mapMulti((number, emit) -> {
        for (int value = 1; value <= number; value++) {
            emit.accept(value);
        }
    })
    .toArray();
```

Chọn `flatMap` khi Stream con là cách biểu diễn tự nhiên và muốn kết hợp các thao tác Stream trên từng nhóm. Chọn `mapMulti` khi vòng lặp hoặc các nhánh điều kiện mô tả logic phát kết quả trực tiếp và dễ đọc hơn.

Không mặc định `mapMulti` luôn nhanh hơn `flatMap`. Hiệu năng còn phụ thuộc số lượng đầu ra, logic mapper, JDK và các thao tác tiếp theo. Hãy chọn cách diễn đạt rõ ràng; chỉ tối ưu theo số đo đại diện khi có yêu cầu hiệu năng cụ thể.

## 8. Phân biệt IntStream.mapMulti và Stream.mapMultiToInt

Hai phương thức có thể cùng tạo `IntStream`, nhưng dùng khi kiểu dữ liệu nguồn khác nhau:

| Phương thức | Kiểu nguồn | Mapper nhận | Kiểu kết quả |
|---|---|---|---|
| `IntStream.mapMulti` | `IntStream` | `int` và `IntConsumer` | `IntStream` |
| `Stream<T>.mapMultiToInt` | `Stream<T>` | `T` và `IntConsumer` | `IntStream` |

Ví dụ dùng `IntStream.mapMulti` khi nguồn đã là các số nguyên:

```java
import java.util.stream.IntStream;

int[] digits = IntStream.of(12, 305)
    .mapMulti((number, emit) -> {
        for (int digit = number; digit > 0; digit /= 10) {
            emit.accept(digit % 10);
        }
    })
    .toArray();
```

Ví dụ dùng `Stream<T>.mapMultiToInt` khi nguồn là các đối tượng:

```java
import java.util.List;

record OrderLine(String sku, int quantity) {}

List<OrderLine> lines = List.of(
    new OrderLine("BOOK-01", 2),
    new OrderLine("PEN-02", 3)
);

int[] quantities = lines.stream()
    .mapMultiToInt((line, emit) -> {
        for (int i = 0; i < line.quantity(); i++) {
            emit.accept(1);
        }
    })
    .toArray();
```

Ở ví dụ đầu, phần tử nguồn vốn là `int`, nên dùng `IntStream.mapMulti`. Ở ví dụ sau, phần tử nguồn là `OrderLine`, nên dùng `Stream<OrderLine>.mapMultiToInt` để phát các số nguyên. Cả hai đều tạo `IntStream` và có thể tiếp tục bằng `sum()`, `toArray()` hoặc các thao tác số nguyên khác.

Lưu ý ví dụ trích chữ số ở trên phát chữ số theo thứ tự từ phải sang trái vì dùng phép chia liên tiếp. Nếu cần thứ tự trái sang phải, hãy duyệt chuỗi biểu diễn hoặc lưu các chữ số rồi phát theo thứ tự mong muốn.

## 9. IntStream và primitive specialization

`IntStream` làm việc trực tiếp với kiểu nguyên thủy `int`. Trong `IntStream.mapMulti`, Consumer đầu ra là `IntConsumer`, nên lời gọi `accept(int)` không cần đóng gói từng giá trị thành `Integer`.

So sánh:

| Cách xử lý | Consumer | Kiểu Stream |
|---|---|---|
| `Stream<Integer>.mapMulti` | `Consumer<Integer>` | `Stream<Integer>` |
| `IntStream.mapMulti` | `IntConsumer` | `IntStream` |

Ví dụ dùng Stream chứa wrapper:

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

List<Integer> expanded = values.stream()
    .<Integer>mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2);
    })
    .toList();
```

Ví dụ dùng primitive stream:

```java
import java.util.stream.IntStream;

int[] expanded = IntStream.of(1, 2, 3)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2);
    })
    .toArray();
```

Primitive specialization có thể tránh boxing trong phần phát và xử lý các giá trị đầu ra. Tuy nhiên, nếu dữ liệu bắt đầu từ `List<Integer>`, bước tạo `IntStream` có thể cần unbox; nếu kết quả cuối cùng cần `List<Integer>`, bước `boxed()` sẽ tạo wrapper. Hãy xét toàn bộ pipeline thay vì chỉ một thao tác riêng lẻ.

## 10. Các phép toán có thể dùng sau mapMulti

Vì `IntStream.mapMulti` trả về `IntStream`, ta có thể tiếp tục với các thao tác số nguyên:

| Thao tác | Công dụng |
|---|---|
| `sum()` | Tính tổng và trả về `int` |
| `average()` | Tính trung bình và trả về `OptionalDouble` |
| `min()` / `max()` | Tìm giá trị nhỏ nhất/lớn nhất và trả về `OptionalInt` |
| `count()` | Đếm phần tử |
| `summaryStatistics()` | Thu thập count, sum, min, max và average |
| `toArray()` | Thu kết quả vào `int[]` |
| `boxed()` | Chuyển thành `Stream<Integer>` khi API phía sau cần object |

Ví dụ tính tổng các ước số của nhiều số:

```java
import java.util.stream.IntStream;

int divisorSum = IntStream.of(6, 10, 7)
    .mapMulti((number, emit) -> {
        for (int candidate = 1; candidate <= number; candidate++) {
            if (number % candidate == 0) {
                emit.accept(candidate);
            }
        }
    })
    .sum();
```

Với đầu vào trên, tổng các ước số được phát là `12 + 18 + 8 = 38`. Không cần chuyển các giá trị thành `Integer` chỉ để tính tổng.

Lưu ý `IntStream.sum()` thực hiện phép cộng trên kiểu `int`. Nếu tổng có thể vượt `Integer.MAX_VALUE` hoặc nhỏ hơn `Integer.MIN_VALUE`, kết quả có thể tràn. Khi cần phạm vi lớn hơn, hãy chuyển sang `long` bằng `asLongStream()` trước khi cộng, hoặc dùng `mapMultiToLong` nếu ngay từ đầu kết quả nên là `long`.

## 11. Chuyển đổi sang kiểu khác khi cần

Nếu cần chuyển các số nguyên đã phát thành object, có thể dùng `mapToObj` hoặc `boxed()`:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.of(2, 4, 6)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 10);
    })
    .mapToObj(number -> "value=" + number)
    .toList();
```

Nếu cần `Stream<Integer>`, dùng `boxed()`:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.of(1, 2, 3)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2);
    })
    .boxed()
    .toList();
```

Chỉ chuyển sang object khi API hoặc mô hình dữ liệu tiếp theo cần kiểu tham chiếu. Nếu các bước tiếp theo vẫn là tính toán số học, giữ `IntStream` thường phù hợp hơn.

## 12. Thứ tự phát và parallel Stream

Trong một lần mapper chạy, các lời gọi `emit.accept` được thực hiện theo thứ tự chương trình. Với Stream có encounter order, kết quả được phát theo thứ tự phần tử nguồn và thứ tự gọi Consumer trong từng mapper.

Ví dụ:

```java
import java.util.stream.IntStream;

int[] values = IntStream.of(1, 2)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number + 10);
    })
    .toArray();
```

Kết quả là `[1, 11, 2, 12]`.

Khi dùng parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Nếu nguồn có encounter order, các thao tác có bảo toàn thứ tự như `toArray()` vẫn thu kết quả theo encounter order. Tuy nhiên, không dựa vào thời điểm mapper bắt đầu hoặc kết thúc để thực hiện tác dụng phụ theo thứ tự nghiệp vụ.

Tránh cập nhật một mảng hoặc collection mutable dùng chung bên trong mapper. Hãy phát số qua `IntConsumer` và để pipeline hoặc terminal operation thu thập kết quả.

## 13. Lazy evaluation và phạm vi sử dụng Consumer

`mapMulti` là thao tác trung gian. Mapper chỉ được thực thi khi terminal operation bắt đầu tiêu thụ dữ liệu, chẳng hạn `sum()`, `count()`, `toArray()` hoặc `summaryStatistics()`.

Terminal operation có thể dừng sớm, ví dụ `findFirst()` hoặc `anyMatch(...)`. Khi đó pipeline có thể không cần xử lý mọi phần tử nguồn. Không dùng mapper để thực hiện tác dụng phụ bắt buộc phải xảy ra đúng một lần cho tất cả phần tử.

Consumer được truyền vào mapper để phát kết quả trong lần gọi hiện tại. Hãy gọi `accept` ngay trong callback; không lưu `IntConsumer` để gọi sau khi mapper kết thúc hoặc chuyển nó sang tác vụ bất đồng bộ.

Nếu vòng lặp bên trong mapper tạo ra rất nhiều số hoặc không có giới hạn, `mapMulti` có thể không phù hợp. Trong trường hợp đó, một `IntStream` con qua `flatMap` có thể diễn đạt nguồn dữ liệu tốt hơn. Không giả định rằng `limit()` phía sau luôn dừng được một vòng lặp phát dữ liệu đang chạy bên trong mapper.

## 14. Lỗi thường gặp

**Nhầm IntMapMultiConsumer với IntConsumer.** `IntMapMultiConsumer` là mapper nhận hai tham số; `IntConsumer` là Consumer nhận từng số đầu ra.

**Nghĩ rằng mapper phải return int.** Mapper là callback không trả về giá trị. Hãy gọi `downstream.accept(value)` để phát số.

**Dùng type witness như Stream generic.** `IntStream.mapMulti` không có tham số kiểu `R`, vì vậy không viết `.<Integer>mapMulti`. Kiểu đầu vào và đầu ra đều là `int`.

**Dùng mapMulti khi chỉ cần lọc.** Nếu chỉ giữ hoặc loại số hiện tại, `filter` thường ngắn gọn và dễ đọc hơn.

**Dùng mapMulti khi mỗi phần tử chỉ tạo đúng một số.** Nếu mỗi đầu vào luôn tạo một đầu ra, `map` thường diễn đạt rõ hơn.

**Giữ Consumer để gọi sau callback.** Hãy phát kết quả ngay trong lần mapper chạy và không dùng Consumer như callback bất đồng bộ.

**Giả định mapMulti luôn nhanh hơn flatMap.** Hãy chọn theo cách biểu đạt phù hợp và benchmark khi có yêu cầu hiệu năng cụ thể.

**Bỏ qua tràn số.** Các phép nhân, bình phương và `sum()` trên `int` vẫn có thể tràn. Dùng `long` hoặc kiểu số lớn hơn nếu miền dữ liệu yêu cầu.

## 15. Ghi nhớ

- `IntStream.mapMulti` nhận `IntMapMultiConsumer` và trả về `IntStream`.
- `IntMapMultiConsumer.accept(int, IntConsumer)` nhận số nguồn cùng Consumer phát số đầu ra.
- Mỗi lần `IntConsumer.accept(int)` tạo một phần tử; không gọi để phát không phần tử; gọi nhiều lần để phát nhiều số.
- Dùng `IntStream.mapMulti` khi nguồn đã là `int` và logic mở rộng bằng vòng lặp hoặc nhánh điều kiện.
- Dùng `Stream<T>.mapMultiToInt` khi nguồn là object nhưng đầu ra là một hoặc nhiều số nguyên.
- Dùng `map` cho quan hệ một-một, `filter` cho lọc, `flatMap` khi mapper tự nhiên tạo `IntStream` con.
- `IntStream` giữ giá trị nguyên thủy và hỗ trợ các phép toán số học chuyên biệt.
- Chú ý tràn số, lazy evaluation, encounter order và an toàn khi chạy song song.

Khi đầu vào và đầu ra đều là số nguyên, `IntStream.mapMulti` cùng `IntMapMultiConsumer` cung cấp cách phát không, một hoặc nhiều giá trị trực tiếp trong primitive Stream pipeline, giúp mã thể hiện rõ logic mở rộng dữ liệu mà không cần tạo Stream con cho từng phần tử.

