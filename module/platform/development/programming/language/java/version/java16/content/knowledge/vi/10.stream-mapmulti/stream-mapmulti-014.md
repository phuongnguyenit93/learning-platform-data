# LongStream.mapMulti và LongMapMultiConsumer

`LongStream.mapMulti` là phương thức của Stream chuyên biệt cho kiểu nguyên thủy `long`. Với mỗi giá trị nguồn, mapper có thể phát không, một hoặc nhiều giá trị `long` vào Stream kết quả thông qua `LongConsumer`. Phương thức phù hợp khi cần mở rộng một số nguyên dài thành nhiều giá trị, duyệt dữ liệu số con hoặc phát kết quả theo vòng lặp và điều kiện.

Cần phân biệt `LongStream.mapMulti` với `Stream<T>.mapMultiToLong`. Cả hai đều tạo `LongStream`, nhưng phương thức thứ nhất nhận đầu vào đã là `long`; phương thức thứ hai nhận phần tử nguồn là object kiểu `T` rồi phát các giá trị `long`.

## 1. LongStream.mapMulti là gì?

`LongStream.mapMulti` được bổ sung trong Java 16. Đây là thao tác trung gian thay thế mỗi phần tử `long` nguồn bằng không, một hoặc nhiều phần tử `long` đầu ra.

Chữ ký phương thức:

```java
LongStream mapMulti(LongMapMultiConsumer mapper)
```

`LongMapMultiConsumer` là functional interface trong package `java.util.stream`. Phương thức trừu tượng của nó có dạng:

```java
void accept(long value, LongConsumer downstream)
```

Trong đó:

- `value` là giá trị `long` hiện tại của Stream nguồn.
- `downstream` là `LongConsumer` dùng để phát các giá trị `long` kết quả.
- Mỗi lần gọi `downstream.accept(result)` tạo một phần tử trong `LongStream` kết quả.
- Mapper không trả về giá trị; nó phát kết quả qua Consumer.

Có thể đọc chữ ký này như một quy tắc: nhận một số nguyên dài và dùng Consumer để phát các số nguyên dài tương ứng.

## 2. Vai trò của LongMapMultiConsumer và LongConsumer

Hai interface có liên quan nhưng đảm nhiệm hai vai trò khác nhau:

| Thành phần | Package | Vai trò |
|---|---|---|
| `LongMapMultiConsumer` | `java.util.stream` | Mapper nhận một `long` nguồn và Consumer phát kết quả |
| `LongConsumer` | `java.util.function` | Nhận một giá trị `long` đầu ra qua `accept(long)` |

Một lambda tương ứng có dạng:

```java
(value, downstream) -> {
    downstream.accept(value);
}
```

Tham số thứ nhất là dữ liệu nguồn. Tham số thứ hai là kênh phát kết quả. Tên `downstream` chỉ là tên biến; có thể đặt là `emit`, `output` hoặc `consumer`.

Vì đầu vào và đầu ra đều là `long`, `LongStream.mapMulti` không có tham số kiểu generic `R` như `Stream<T>.mapMulti`. Do đó, không cần type witness như `.<Long>mapMulti` khi gọi phương thức này.

## 3. Phát không, một hoặc nhiều giá trị long

Số lần gọi `accept` quyết định số phần tử đầu ra mà một phần tử nguồn đóng góp:

| Cách mapper xử lý | Kết quả |
|---|---|
| Không gọi `downstream.accept` | Không phát phần tử |
| Gọi `downstream.accept` một lần | Phát một phần tử |
| Gọi `downstream.accept` nhiều lần | Phát nhiều phần tử |

Ví dụ, chỉ phát các giá trị dương:

```java
import java.util.stream.LongStream;

long[] positives = LongStream.of(-5L, 0L, 12L, 30L, -2L)
    .mapMulti((number, emit) -> {
        if (number > 0) {
            emit.accept(number);
        }
    })
    .toArray();
```

Kết quả:

```text
[12, 30]
```

Các giá trị âm và số không không gọi `emit.accept`, nên không xuất hiện trong kết quả. Ví dụ này minh họa cơ chế phát không hoặc một giá trị từ mỗi phần tử nguồn.

Nếu mục tiêu duy nhất là giữ các giá trị dương, `filter` thường thể hiện ý định rõ hơn:

```java
import java.util.stream.LongStream;

long[] positives = LongStream.of(-5L, 0L, 12L, 30L, -2L)
    .filter(number -> number > 0)
    .toArray();
```

## 4. Một giá trị nguồn phát nhiều giá trị long

`LongStream.mapMulti` hữu ích khi mỗi giá trị nguồn cần được mở rộng thành một dãy số nguyên dài. Ví dụ, mỗi số dương `count` phát ra dãy từ 1 đến `count`:

```java
import java.util.stream.LongStream;

long[] expanded = LongStream.of(3L, 2L, 4L)
    .mapMulti((count, emit) -> {
        for (long value = 1L; value <= count; value++) {
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

Giá trị nguồn `3L` phát ba số, `2L` phát hai số và `4L` phát bốn số. Nếu `count` nhỏ hơn 1, vòng lặp không chạy nên mapper không phát kết quả.

Lệnh `break` sau khi phát giá trị cuối giúp vòng lặp kết thúc trước khi phép tăng tiếp theo có thể làm tràn biến đếm khi `count` bằng `Long.MAX_VALUE`. Trong ứng dụng thực tế, vẫn cần giới hạn số kết quả có thể phát để tránh tạo khối lượng dữ liệu quá lớn.

## 5. Phát kết quả theo nhiều điều kiện

Một giá trị nguồn có thể tạo ra nhiều kết quả theo các nhánh nghiệp vụ. Ví dụ, mỗi số dương phát chính nó; nếu giá trị đủ nhỏ để nhân đôi an toàn, phát thêm giá trị gấp đôi:

```java
import java.util.stream.LongStream;

long[] results = LongStream.of(-2L, 0L, 2L, 3L)
    .mapMulti((number, emit) -> {
        if (number > 0) {
            emit.accept(number);
        }

        if (number > 0 && number <= Long.MAX_VALUE / 2) {
            emit.accept(number * 2);
        }
    })
    .toArray();
```

Kết quả:

```text
[2, 4, 3, 6]
```

Các nhánh được kiểm tra độc lập. Với `2L`, mapper phát `2L` rồi `4L`; với `3L`, mapper phát `3L` rồi `6L`. Điều kiện giới hạn phép nhân để tránh tràn số có dấu.

Thứ tự kết quả trong mỗi nhóm tuân theo thứ tự gọi `emit.accept`. Nếu đổi thứ tự các lệnh phát, thứ tự đầu ra tương ứng cũng thay đổi.

## 6. Ví dụ: phát các ước số của từng số nguồn

Có thể mở rộng mỗi số thành các ước số của nó:

```java
import java.util.stream.LongStream;

long[] divisors = LongStream.of(6L, 10L, 7L)
    .mapMulti((number, emit) -> {
        if (number <= 0) {
            return;
        }

        for (long candidate = 1L; candidate <= number; candidate++) {
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

Mỗi số nguồn phát các ước số theo thứ tự tăng dần. Số `6L` phát bốn giá trị, số `10L` phát bốn giá trị và số nguyên tố `7L` phát hai giá trị là `1L` và `7L`.

Đây là ví dụ minh họa cơ chế phát nhiều phần tử bằng vòng lặp. Với số nguồn rất lớn, thử mọi ứng viên từ 1 đến số đó có thể tốn thời gian đáng kể. Hãy chọn thuật toán phù hợp với giới hạn dữ liệu và yêu cầu hiệu năng của ứng dụng.

## 7. So sánh LongStream.mapMulti với map, filter và flatMap

Các thao tác có hình dạng đầu ra khác nhau:

| Thao tác | Kết quả từ một phần tử nguồn | Mục đích |
|---|---:|---|
| `map` | Chính xác một `long` | Chuyển một số thành một số khác |
| `filter` | Không hoặc một `long` | Giữ hoặc loại số hiện tại |
| `flatMap` | Không, một hoặc nhiều `long` | Chuyển thành `LongStream` con rồi làm phẳng |
| `mapMulti` | Không, một hoặc nhiều `long` | Phát số trực tiếp qua `LongConsumer` |

Dùng `map` khi mỗi số luôn tạo đúng một số:

```java
import java.util.stream.LongStream;

long[] doubled = LongStream.of(1L, 2L, 3L)
    .map(number -> number * 2L)
    .toArray();
```

Dùng `filter` khi chỉ giữ số thỏa điều kiện:

```java
import java.util.stream.LongStream;

long[] largeValues = LongStream.of(10L, 500L, 2_000L, 8_000L)
    .filter(value -> value >= 1_000L)
    .toArray();
```

Dùng `flatMap` khi phép biến đổi tự nhiên trả về một `LongStream` con:

```java
import java.util.stream.LongStream;

long[] expanded = LongStream.of(2L, 3L)
    .flatMap(count -> LongStream.rangeClosed(1L, count))
    .toArray();
```

Cùng kết quả có thể viết bằng `mapMulti`:

```java
import java.util.stream.LongStream;

long[] expanded = LongStream.of(2L, 3L)
    .mapMulti((count, emit) -> {
        for (long value = 1L; value <= count; value++) {
            emit.accept(value);

            if (value == count) {
                break;
            }
        }
    })
    .toArray();
```

Chọn `flatMap` khi Stream con là cách biểu diễn tự nhiên và muốn kết hợp các thao tác Stream trên từng nhóm. Chọn `mapMulti` khi vòng lặp hoặc các nhánh điều kiện mô tả logic phát kết quả trực tiếp và dễ đọc hơn.

Không mặc định `mapMulti` luôn nhanh hơn `flatMap`. Hiệu năng phụ thuộc số lượng đầu ra, logic mapper, phiên bản JDK và các thao tác tiếp theo. Hãy chọn cách diễn đạt rõ ràng; chỉ tối ưu theo số đo đại diện khi có yêu cầu hiệu năng cụ thể.

## 8. Phân biệt LongStream.mapMulti và Stream.mapMultiToLong

Hai phương thức đều có thể tạo `LongStream`, nhưng dùng khi kiểu dữ liệu nguồn khác nhau:

| Phương thức | Kiểu nguồn | Mapper nhận | Kiểu kết quả |
|---|---|---|---|
| `LongStream.mapMulti` | `LongStream` | `long` và `LongConsumer` | `LongStream` |
| `Stream<T>.mapMultiToLong` | `Stream<T>` | `T` và `LongConsumer` | `LongStream` |

Ví dụ dùng `LongStream.mapMulti` khi nguồn đã là các số nguyên dài:

```java
import java.util.stream.LongStream;

long[] expanded = LongStream.of(10L, 20L)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value + 5L);
    })
    .toArray();
```

Ví dụ dùng `Stream<T>.mapMultiToLong` khi nguồn là các đối tượng:

```java
import java.util.List;

record StorageNode(String name, long usedBytes, long freeBytes) {}

List<StorageNode> nodes = List.of(
    new StorageNode("node-A", 5_000_000_000L, 3_000_000_000L),
    new StorageNode("node-B", 7_500_000_000L, 2_500_000_000L)
);

long[] capacities = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        emit.accept(node.usedBytes());
        emit.accept(node.freeBytes());
    })
    .toArray();
```

Ở ví dụ đầu, phần tử nguồn vốn là `long` nên dùng `LongStream.mapMulti`. Ở ví dụ sau, phần tử nguồn là `StorageNode` nên dùng `Stream<StorageNode>.mapMultiToLong` để phát các giá trị `long`. Cả hai đều có thể tiếp tục bằng `sum()`, `toArray()` hoặc các thao tác số nguyên dài khác.

## 9. LongStream và primitive specialization

`LongStream` làm việc trực tiếp với kiểu nguyên thủy `long`. Trong `LongStream.mapMulti`, Consumer đầu ra là `LongConsumer`, nên lời gọi `accept(long)` không cần đóng gói từng giá trị thành `Long`.

So sánh:

| Cách xử lý | Consumer | Kiểu Stream |
|---|---|---|
| `Stream<Long>.mapMulti` | `Consumer<Long>` | `Stream<Long>` |
| `LongStream.mapMulti` | `LongConsumer` | `LongStream` |

Ví dụ dùng Stream chứa wrapper:

```java
import java.util.List;

List<Long> values = List.of(1L, 2L, 3L);

List<Long> expanded = values.stream()
    .<Long>mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2L);
    })
    .toList();
```

Ví dụ dùng primitive stream:

```java
import java.util.stream.LongStream;

long[] expanded = LongStream.of(1L, 2L, 3L)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2L);
    })
    .toArray();
```

Primitive specialization có thể tránh boxing trong phần phát và xử lý các giá trị đầu ra. Tuy nhiên, nếu dữ liệu bắt đầu từ `List<Long>`, bước tạo `LongStream` có thể cần unbox; nếu kết quả cuối cùng cần `List<Long>`, bước `boxed()` sẽ tạo wrapper. Hãy xét toàn bộ pipeline thay vì chỉ một thao tác riêng lẻ.

## 10. Các phép toán có thể dùng sau mapMulti

Vì `LongStream.mapMulti` trả về `LongStream`, ta có thể tiếp tục với các thao tác số nguyên dài:

| Thao tác | Công dụng |
|---|---|
| `sum()` | Tính tổng và trả về `long` |
| `average()` | Tính trung bình và trả về `OptionalDouble` |
| `min()` / `max()` | Tìm giá trị nhỏ nhất/lớn nhất và trả về `OptionalLong` |
| `count()` | Đếm phần tử |
| `summaryStatistics()` | Thu thập count, sum, min, max và average |
| `toArray()` | Thu kết quả vào `long[]` |
| `boxed()` | Chuyển thành `Stream<Long>` khi API phía sau cần object |

Ví dụ tính tổng dung lượng đã sử dụng và còn trống:

```java
import java.util.List;

record StorageNode(String name, long usedBytes, long freeBytes) {}

List<StorageNode> nodes = List.of(
    new StorageNode("node-A", 5_000_000_000L, 3_000_000_000L),
    new StorageNode("node-B", 7_500_000_000L, 2_500_000_000L)
);

long totalBytes = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        emit.accept(node.usedBytes());
        emit.accept(node.freeBytes());
    })
    .sum();
```

Tổng của các giá trị được phát là `18_000_000_000L`. Không cần tạo `Long[]` hoặc `List<Long>` chỉ để cộng các giá trị.

Có thể lấy nhiều chỉ số cùng lúc bằng `summaryStatistics()`:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics statistics = LongStream.of(
        5_000_000_000L,
        3_000_000_000L,
        7_500_000_000L,
        2_500_000_000L
    )
    .summaryStatistics();
```

Thống kê có bốn phần tử, tổng `18_000_000_000`, nhỏ nhất `2_500_000_000` và lớn nhất `7_500_000_000`. Nếu Stream rỗng, `sum()` trả về `0L`, còn `average()`, `min()` và `max()` trả về các Optional rỗng tương ứng.

## 11. Chú ý tràn số khi tính toán long

Kiểu `long` có phạm vi lớn hơn `int`, nhưng vẫn có giới hạn. Các phép cộng, trừ và nhân trên `long` không tự kiểm tra overflow. Nếu kết quả vượt `Long.MAX_VALUE` hoặc nhỏ hơn `Long.MIN_VALUE`, giá trị có thể tràn theo biểu diễn số nguyên có dấu.

Ví dụ, `LongStream.sum()` cộng trên kiểu `long` và không tự ném ngoại lệ khi tổng vượt phạm vi biểu diễn. Nếu tổng cần chính xác vượt giới hạn này, hãy chuyển sang cách tính bằng `BigInteger`:

```java
import java.math.BigInteger;
import java.util.stream.LongStream;

BigInteger exactTotal = LongStream.of(Long.MAX_VALUE, 1L)
    .mapToObj(BigInteger::valueOf)
    .reduce(BigInteger.ZERO, BigInteger::add);
```

`BigInteger` giữ chính xác tổng lớn hơn `Long.MAX_VALUE`. Nếu từng giá trị nguồn vốn đã vượt phạm vi `long`, cần dùng kiểu dữ liệu phù hợp ngay từ đầu; `mapMultiToLong` không thể khôi phục độ chính xác đã mất khi ép kiểu.

Với các phép nhân, hãy kiểm tra giới hạn trước khi thực hiện nếu dữ liệu có thể lớn. Có thể dùng các phương thức như `Math.multiplyExact` hoặc `Math.addExact` khi muốn phát hiện overflow bằng `ArithmeticException` thay vì chấp nhận kết quả tràn.

## 12. So sánh với flatMapToLong

`flatMapToLong` phù hợp khi mapper tự nhiên trả về một `LongStream` cho mỗi phần tử nguồn. Với danh sách kích thước của các node, có thể viết:

```java
import java.util.List;

record StorageNode(String name, List<Long> objectSizes) {}

List<StorageNode> nodes = List.of(
    new StorageNode("node-A", List.of(4_000_000_000L, 2_500_000_000L)),
    new StorageNode("node-B", List.of(8_000_000_000L))
);

long[] allSizes = nodes.stream()
    .flatMapToLong(node ->
        node.objectSizes().stream().mapToLong(Long::longValue)
    )
    .toArray();
```

Cùng dữ liệu có thể được làm phẳng bằng `mapMultiToLong`:

```java
long[] allSizes = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .toArray();
```

Chọn `flatMapToLong` khi phép biến đổi tự nhiên tạo ra một `LongStream` và muốn kết hợp các thao tác trên Stream con. Chọn `mapMultiToLong` khi việc duyệt collection con bằng vòng lặp hoặc nhiều nhánh điều kiện thể hiện logic rõ ràng hơn.

Với `LongStream.mapMulti`, quy tắc tương tự áp dụng khi nguồn đã là `long`: chọn `flatMap` nếu có một `LongStream` con tự nhiên; chọn `mapMulti` nếu vòng lặp và Consumer diễn đạt phép phát trực tiếp tốt hơn.

`mapMulti` thường phù hợp với số lượng đầu ra nhỏ cho mỗi phần tử nguồn. Nếu một phần tử có thể phát lượng dữ liệu rất lớn hoặc không giới hạn, hãy cân nhắc một Stream con qua `flatMap`. Không mặc định một phương thức luôn nhanh hơn phương thức còn lại; hiệu năng phụ thuộc dữ liệu, mapper, JDK và các thao tác tiếp theo.

## 13. Chuyển từ LongStream sang object khi cần

Nếu các phép toán số học đã hoàn tất và bước tiếp theo cần object, có thể dùng `mapToObj` hoặc `boxed()`.

Ví dụ tạo nhãn cho từng giá trị:

```java
import java.util.stream.LongStream;

String[] labels = LongStream.of(4_000_000_000L, 8_000_000_000L)
    .mapMulti((size, emit) -> {
        emit.accept(size);
        emit.accept(size / 2L);
    })
    .mapToObj(size -> "bytes=" + size)
    .toArray(String[]::new);
```

Nếu chỉ cần danh sách `Long`, dùng `boxed()`:

```java
import java.util.List;
import java.util.stream.LongStream;

List<Long> boxedValues = LongStream.of(1L, 2L, 3L)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2L);
    })
    .boxed()
    .toList();
```

Chỉ chuyển sang object khi kiểu tham chiếu cần thiết cho API hoặc mô hình dữ liệu tiếp theo. Nếu pipeline chỉ tính toán số học, giữ `LongStream` sẽ tránh boxing không cần thiết.

## 14. Thứ tự phát và parallel Stream

Trong một lần mapper chạy, các lời gọi `emit.accept` được thực hiện theo thứ tự chương trình. Với Stream có encounter order, kết quả được kết hợp theo thứ tự phần tử nguồn và thứ tự gọi Consumer trong từng mapper.

Ví dụ:

```java
import java.util.stream.LongStream;

long[] values = LongStream.of(1L, 2L)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number + 10L);
    })
    .toArray();
```

Kết quả là `[1, 11, 2, 12]`.

Khi dùng parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Nếu nguồn có encounter order, các thao tác bảo toàn thứ tự như `toArray()` vẫn thu kết quả theo encounter order. Tuy nhiên, không dựa vào thời điểm mapper bắt đầu hoặc kết thúc để thực hiện tác dụng phụ theo thứ tự nghiệp vụ.

Tránh cập nhật một mảng hoặc collection mutable dùng chung bên trong mapper. Hãy phát số qua `LongConsumer` và để pipeline hoặc terminal operation thu thập kết quả. Nếu terminal operation là `forEach` trên parallel Stream, hành động có thể được gọi theo thứ tự bất kỳ; dùng `forEachOrdered` nếu cần thực hiện hành động cuối theo encounter order.

## 15. Lazy evaluation và phạm vi sử dụng Consumer

`LongStream.mapMulti` là thao tác trung gian. Mapper chỉ được thực thi khi terminal operation tiêu thụ pipeline, chẳng hạn `sum()`, `count()`, `toArray()` hoặc `summaryStatistics()`.

Terminal operation có thể dừng sớm, ví dụ `findFirst()` hoặc `anyMatch(...)`. Tuy nhiên, không nên giả định thao tác dừng sớm sẽ ngắt một vòng lặp phát nhiều giá trị ngay giữa lần gọi mapper hiện tại. Mapper gọi Consumer đồng bộ; hãy giữ số kết quả phát ra cho mỗi phần tử ở mức hợp lý.

Consumer được truyền vào mapper để phát kết quả trong lần gọi hiện tại. Gọi `accept` ngay trong callback; không lưu `LongConsumer` để gọi sau khi mapper kết thúc hoặc chuyển nó sang tác vụ bất đồng bộ.

Nếu một phần tử có thể phát lượng giá trị rất lớn hoặc không giới hạn, một `LongStream` con qua `flatMap` thường mô tả nguồn dữ liệu phù hợp hơn. Không dựa vào `limit()` phía sau để bảo đảm vòng lặp bên trong mapper sẽ tự dừng sau một số lần phát cố định.

## 16. Lỗi thường gặp

**Nhầm LongMapMultiConsumer với LongConsumer.** `LongMapMultiConsumer` là mapper nhận hai tham số; `LongConsumer` là Consumer nhận từng giá trị `long` đầu ra.

**Nghĩ rằng mapper phải return long.** Mapper là callback không trả về giá trị. Hãy gọi `downstream.accept(value)` để phát số.

**Dùng type witness như Stream generic.** `LongStream.mapMulti` không có tham số kiểu `R`, vì vậy không viết `.<Long>mapMulti`. Kiểu đầu vào và đầu ra đều là `long`.

**Dùng mapMulti khi chỉ cần lọc.** Nếu chỉ giữ hoặc loại giá trị hiện tại, `filter` thường ngắn gọn và dễ đọc hơn.

**Dùng mapMulti khi mỗi phần tử chỉ tạo đúng một số.** Nếu mỗi đầu vào luôn tạo một đầu ra, `map` thường diễn đạt rõ hơn.

**Bỏ qua overflow.** Các phép nhân và `sum()` trên `long` vẫn có thể tràn. Dùng `Math.addExact`, `Math.multiplyExact` hoặc `BigInteger` khi yêu cầu cần phát hiện hay tránh overflow.

**Boxing sớm rồi unbox lại.** Tránh chuyển sang `Stream<Long>` nếu các bước tiếp theo chỉ cần phép toán trên `LongStream`.

**Giả định mapMulti luôn nhanh hơn flatMap.** Hãy chọn theo cách biểu đạt phù hợp và benchmark trên dữ liệu thực tế khi cần tối ưu.

**Giữ Consumer để gọi sau callback.** Hãy phát kết quả ngay trong lần mapper chạy và không dùng Consumer như callback bất đồng bộ.

## 17. Ghi nhớ

- `LongStream.mapMulti` nhận `LongMapMultiConsumer` và trả về `LongStream`.
- `LongMapMultiConsumer.accept(long, LongConsumer)` nhận giá trị nguồn cùng Consumer phát giá trị đầu ra.
- Mỗi lần `LongConsumer.accept(long)` tạo một phần tử; không gọi để phát không phần tử; gọi nhiều lần để phát nhiều số.
- Dùng `LongStream.mapMulti` khi nguồn đã là `long` và logic mở rộng bằng vòng lặp hoặc nhánh điều kiện.
- Dùng `Stream<T>.mapMultiToLong` khi nguồn là object nhưng đầu ra là một hoặc nhiều giá trị `long`.
- Dùng `map` cho quan hệ một-một, `filter` cho lọc, `flatMap` khi mapper tự nhiên tạo `LongStream` con.
- `LongStream` giữ giá trị nguyên thủy và hỗ trợ các phép toán số học chuyên biệt.
- Chú ý overflow, lazy evaluation, encounter order và an toàn khi chạy song song.
- Dùng `BigInteger` nếu cần tính toán chính xác vượt phạm vi `long`; dùng `boxed()` hoặc `mapToObj` khi bước tiếp theo cần object.

Khi đầu vào và đầu ra đều là số nguyên dài, `LongStream.mapMulti` cùng `LongMapMultiConsumer` cung cấp cách phát không, một hoặc nhiều giá trị trực tiếp trong primitive Stream pipeline, giúp mã thể hiện rõ logic mở rộng dữ liệu mà không cần tạo Stream con cho từng phần tử.

