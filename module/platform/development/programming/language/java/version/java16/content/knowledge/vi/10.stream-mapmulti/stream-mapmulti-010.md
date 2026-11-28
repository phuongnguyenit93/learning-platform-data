# mapMultiToInt và IntConsumer cho kết quả số nguyên

`Stream.mapMultiToInt` là biến thể chuyên biệt của `mapMulti` khi dữ liệu đầu ra là các giá trị `int`. Mapper nhận phần tử nguồn cùng một `IntConsumer`; mỗi lần gọi `accept(int)` sẽ phát một giá trị nguyên vào `IntStream` kết quả. Mapper có thể phát không, một hoặc nhiều số nguyên cho mỗi phần tử nguồn.

Phương thức này hữu ích khi cần duyệt một phần tử để trích xuất nhiều số nguyên, chẳng hạn lấy các chữ số từ mã, phát số lượng hợp lệ từ một bản ghi hoặc chuyển một đối tượng thành một vài chỉ số. Vì đầu ra là `IntStream`, pipeline có thể dùng trực tiếp các phép toán số học mà không cần chuyển từng kết quả thành `Integer`.

## 1. mapMultiToInt là gì?

`mapMultiToInt` là phương thức trên `Stream<T>`, được bổ sung trong Java 16. Nó nhận mapper có kiểu `BiConsumer` và trả về `IntStream`.

Chữ ký phương thức:

```java
IntStream mapMultiToInt(
    BiConsumer<? super T, ? super IntConsumer> mapper
)
```

Có thể hiểu các thành phần như sau:

- `T` là kiểu phần tử của Stream nguồn.
- Mapper nhận một phần tử nguồn kiểu `T`.
- Đối số thứ hai là `IntConsumer`, dùng để phát các giá trị `int`.
- Mỗi lần gọi `accept(int)` tạo một phần tử trong `IntStream` kết quả.
- Mapper không trả về số nguyên trực tiếp; nó phát số qua Consumer.

Ví dụ dạng tổng quát:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<String> source = Stream.of("alpha", "beta");

IntStream result = source.mapMultiToInt((element, emit) -> {
    emit.accept(10);
    emit.accept(20);
});
```

Mỗi phần tử nguồn sẽ phát hai số nguyên là `10` và `20`. Nếu mapper không gọi `emit.accept`, phần tử nguồn đó không đóng góp số nào vào kết quả.

## 2. IntConsumer và phương thức accept(int)

`IntConsumer` là functional interface trong `java.util.function`, dành riêng cho hành động nhận một giá trị kiểu nguyên thủy `int`.

```java
@FunctionalInterface
public interface IntConsumer {
    void accept(int value);
}
```

Trong mapper của `mapMultiToInt`, tham số thứ hai có kiểu `IntConsumer`. Ta thường đặt tên là `emit`, `output` hoặc `consumer`:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2);

int[] originalValues = numbers.stream()
    .mapMultiToInt((number, emit) -> {
        emit.accept(number);
    })
    .toArray();
```

Trong ví dụ này, `number` có kiểu `Integer`; Java tự unbox nó thành `int` khi truyền vào `IntConsumer.accept`. Có thể gọi `accept` nhiều lần trong cùng một lần mapper chạy:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2);

int[] expandedValues = numbers.stream()
    .mapMultiToInt((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2);
    })
    .toArray();
```

Nếu nguồn chứa `[1, 2]`, Stream kết quả là `[1, 2, 2, 4]`. Mỗi số nguồn phát chính nó và giá trị gấp đôi.

## 3. Phát không, một hoặc nhiều số nguyên

Số lần gọi `accept` quyết định số lượng đầu ra từ mỗi phần tử nguồn:

| Cách mapper xử lý | Số phần tử đầu ra |
|---|---:|
| Không gọi `emit.accept` | 0 |
| Gọi `emit.accept` một lần | 1 |
| Gọi `emit.accept` nhiều lần | Nhiều |

Ví dụ, một dòng hàng chỉ phát số lượng nếu số lượng dương:

```java
import java.util.List;

record LineItem(String sku, int quantity) {}

List<LineItem> items = List.of(
    new LineItem("BOOK-01", 2),
    new LineItem("PEN-02", 0),
    new LineItem("BAG-03", 4),
    new LineItem("NOTE-04", -1)
);

int[] quantities = items.stream()
    .mapMultiToInt((item, emit) -> {
        if (item.quantity() > 0) {
            emit.accept(item.quantity());
        }
    })
    .toArray();
```

Kết quả:

```text
[2, 4]
```

Hai dòng hàng có số lượng không dương không phát kết quả. Hai dòng còn lại phát lần lượt số nguyên `2` và `4`.

Nếu chỉ cần giữ hoặc loại một giá trị số nguyên đã có sẵn, `filter` trên `IntStream` (hoặc `filter` trước `mapToInt`) có thể phù hợp hơn. `mapMultiToInt` hữu ích khi một phần tử nguồn có thể tạo ra nhiều số hoặc cần duyệt dữ liệu con để phát số.

## 4. Ví dụ: trích xuất chữ số từ chuỗi

Một chuỗi mã có thể chứa nhiều chữ số. Ta có thể duyệt từng ký tự và phát các chữ số tìm được thành một `IntStream`:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305", "X9");

int[] digits = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char character = code.charAt(index);

            if (Character.isDigit(character)) {
                emit.accept(Character.digit(character, 10));
            }
        }
    })
    .toArray();
```

Kết quả:

```text
[1, 2, 3, 0, 5, 9]
```

Mỗi mã nguồn có thể phát không hoặc nhiều chữ số. Vòng lặp giữ thứ tự ký tự trong chuỗi, do đó các chữ số được phát theo thứ tự xuất hiện.

Có thể tính tổng trực tiếp trên `IntStream` mà không cần tạo mảng:

```java
int digitSum = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char character = code.charAt(index);

            if (Character.isDigit(character)) {
                emit.accept(Character.digit(character, 10));
            }
        }
    })
    .sum();
```

Với dữ liệu trên, `digitSum` bằng `20`.

## 5. Ví dụ: phát nhiều chỉ số từ một bản ghi

Một phép đo có thể có nhiều chỉ số nguyên cần đưa vào thống kê. Ta có thể phát các chỉ số thỏa điều kiện trong cùng mapper:

```java
import java.util.List;

record SensorReading(
    String sensorId,
    int temperature,
    int humidity,
    int batteryLevel
) {}

List<SensorReading> readings = List.of(
    new SensorReading("S-01", 24, 45, 90),
    new SensorReading("S-02", 82, 70, 20),
    new SensorReading("S-03", 31, 88, 75)
);

int[] highValues = readings.stream()
    .mapMultiToInt((reading, emit) -> {
        if (reading.temperature() >= 80) {
            emit.accept(reading.temperature());
        }

        if (reading.humidity() >= 80) {
            emit.accept(reading.humidity());
        }

        if (reading.batteryLevel() < 25) {
            emit.accept(reading.batteryLevel());
        }
    })
    .toArray();
```

Kết quả:

```text
[82, 20, 88]
```

Phép đo `S-02` phát nhiệt độ và mức pin; phép đo `S-03` phát độ ẩm. Phép đo `S-01` không thỏa điều kiện nào nên không tạo đầu ra.

Ví dụ cho thấy mapper có thể có nhiều nhánh độc lập. Một phần tử nguồn có thể phát nhiều số nguyên theo đúng thứ tự các nhánh được thực thi.

## 6. Tiếp tục xử lý bằng các phép toán của IntStream

`mapMultiToInt` trả về `IntStream`, vì vậy có thể sử dụng trực tiếp các thao tác chuyên biệt cho số nguyên:

| Thao tác | Công dụng |
|---|---|
| `sum()` | Tính tổng |
| `average()` | Tính trung bình, trả về `OptionalDouble` |
| `min()` / `max()` | Tìm giá trị nhỏ nhất hoặc lớn nhất, trả về `OptionalInt` |
| `count()` | Đếm số phần tử |
| `summaryStatistics()` | Lấy count, sum, min, max và average |
| `toArray()` | Thu kết quả vào `int[]` |
| `boxed()` | Chuyển thành `Stream<Integer>` khi API phía sau cần object |

Ví dụ thống kê các chữ số trong danh sách mã:

```java
import java.util.IntSummaryStatistics;
import java.util.List;

List<String> codes = List.of("A12", "B305", "X9");

IntSummaryStatistics statistics = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char character = code.charAt(index);

            if (Character.isDigit(character)) {
                emit.accept(Character.digit(character, 10));
            }
        }
    })
    .summaryStatistics();
```

Với dữ liệu trên, thống kê có:

- `count`: 6 chữ số.
- `sum`: 20.
- `min`: 0.
- `max`: 9.
- `average`: khoảng 3.33.

Nếu Stream không phát phần tử nào, `sum()` trả về `0`, còn `average()`, `min()` và `max()` trả về các Optional rỗng tương ứng. Hãy xử lý trường hợp rỗng khi nghiệp vụ cần phân biệt "không có dữ liệu" với kết quả số không.

`sum()` và các phép cộng trên `int` có thể tràn số nếu tổng vượt phạm vi của kiểu `int`. Nếu tổng hoặc từng giá trị có thể vượt giới hạn này, hãy dùng dữ liệu `long` và cân nhắc `mapMultiToLong`.

## 7. So sánh mapMultiToInt, mapMulti và mapToInt

Các phương thức có hình dạng đầu ra khác nhau:

| Phương thức | Mapper phát/trả về | Kiểu Stream kết quả |
|---|---|---|
| `mapMulti` | `Consumer<R>` nhận object kiểu `R` | `Stream<R>` |
| `mapMultiToInt` | `IntConsumer` nhận `int` | `IntStream` |
| `mapToInt` | Mapper trả về đúng một `int` | `IntStream` |

Dùng `mapToInt` khi mỗi phần tử nguồn tạo đúng một số nguyên:

Tiếp tục dùng `LineItem` và danh sách `items` đã khai báo ở mục 3:

```java
int[] quantities = items.stream()
    .mapToInt(LineItem::quantity)
    .toArray();
```

Dùng `mapMultiToInt` khi một phần tử nguồn có thể phát không hoặc nhiều số nguyên:

```java
int[] positiveQuantities = items.stream()
    .mapMultiToInt((item, emit) -> {
        if (item.quantity() > 0) {
            emit.accept(item.quantity());
        }
    })
    .toArray();
```

Nếu dùng `mapMulti` để phát các đối tượng `Integer`, kiểu đầu ra sẽ là `Stream<Integer>`:

```java
List<Integer> quantities = items.stream()
    .<Integer>mapMulti((item, emit) -> {
        if (item.quantity() > 0) {
            emit.accept(item.quantity());
        }
    })
    .toList();
```

Với dữ liệu số nguyên cần tiếp tục tính toán, `mapMultiToInt` thường diễn đạt đúng mục đích hơn vì giữ kết quả trong primitive stream.

## 8. So sánh với flatMapToInt

`flatMapToInt` phù hợp khi mapper tự nhiên trả về một `IntStream` cho mỗi phần tử nguồn. Ví dụ, mỗi mã chuỗi được chuyển thành một Stream các chữ số:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305", "X9");

int[] digits = codes.stream()
    .flatMapToInt(code ->
        code.chars()
            .filter(Character::isDigit)
            .map(character -> Character.digit(character, 10))
    )
    .toArray();
```

Cùng quy tắc có thể được viết bằng `mapMultiToInt`:

Tiếp tục dùng danh sách `codes` đã khai báo trong ví dụ trên:

```java
int[] digits = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char character = code.charAt(index);

            if (Character.isDigit(character)) {
                emit.accept(Character.digit(character, 10));
            }
        }
    })
    .toArray();
```

Chọn `flatMapToInt` khi phép biến đổi tự nhiên tạo ra một `IntStream` và muốn kết hợp các thao tác trên Stream con. Chọn `mapMultiToInt` khi logic phát số được diễn đạt rõ bằng vòng lặp hoặc nhiều nhánh điều kiện.

`mapMultiToInt` phù hợp nhất khi mỗi phần tử nguồn phát ra số lượng kết quả nhỏ. Nếu một phần tử có thể tạo ra rất nhiều giá trị, hãy cân nhắc `flatMapToInt` với một `IntStream` con để mô tả nguồn dữ liệu đó.

Không nên giả định `mapMultiToInt` luôn nhanh hơn `flatMapToInt`. Hiệu năng phụ thuộc dữ liệu, số lượng giá trị phát ra, logic mapper, JDK và các thao tác sau đó. Hãy đo bằng workload thực tế nếu hiệu năng là yêu cầu cần tối ưu.

## 9. Vì sao dùng IntConsumer thay vì Consumer<Integer>?

`Consumer<Integer>` nhận object `Integer`, còn `IntConsumer` nhận trực tiếp giá trị nguyên thủy `int`.

| Đặc điểm | `Consumer<Integer>` | `IntConsumer` |
|---|---|---|
| Kiểu nhận | `Integer` | `int` |
| Giá trị phát | Object wrapper | Primitive |
| Có thể phát sinh boxing | Có, khi chuyển từ `int` sang `Integer` | Không cần boxing ở tham số nhận |
| Stream tương ứng | `Stream<Integer>` | `IntStream` |

Ví dụ dùng `Consumer<Integer>`:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> codes = List.of("A12", "B305");

Stream<Integer> boxed = codes.stream()
    .<Integer>mapMulti((code, emit) -> {
        emit.accept(code.length());
    });
```

Ví dụ dùng `IntConsumer`:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> codes = List.of("A12", "B305");

IntStream primitive = codes.stream()
    .mapMultiToInt((code, emit) -> {
        emit.accept(code.length());
    });
```

Ở phiên bản thứ hai, `code.length()` trả về `int` và được truyền trực tiếp đến `IntConsumer`. Không cần tạo `Integer` cho mỗi kết quả để chuyển qua Stream.

Primitive specialization có thể giảm boxing và unboxing trong pipeline số. Tuy nhiên, nếu dữ liệu đầu vào hoặc API cuối cùng cần object, việc chuyển đổi vẫn có thể xảy ra ở những ranh giới đó. Hãy chọn kiểu Stream phù hợp với phần xử lý tiếp theo.

## 10. Chuyển từ IntStream sang object khi cần

Đôi khi cần tính toán bằng primitive trước rồi chuyển kết quả thành object để dùng API khác. Có thể dùng `boxed()` hoặc `mapToObj`:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305");

List<String> labels = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char character = code.charAt(index);

            if (Character.isDigit(character)) {
                emit.accept(Character.digit(character, 10));
            }
        }
    })
    .mapToObj(number -> "digit=" + number)
    .toList();
```

Kết quả:

```text
[digit=1, digit=2, digit=3, digit=0, digit=5]
```

`mapToObj` chuyển mỗi số nguyên thành một đối tượng String. Nếu chỉ cần thu thập các số thành `List<Integer>`, có thể dùng `boxed()` rồi `toList()`. Chỉ chuyển sang object khi bước tiếp theo thực sự cần kiểu tham chiếu.

## 11. Các biến thể primitive liên quan

Stream API còn có hai phương thức chuyên biệt cùng mô hình:

- `mapMultiToLong` phát các giá trị `long` qua `LongConsumer` và trả về `LongStream`.
- `mapMultiToDouble` phát các giá trị `double` qua `DoubleConsumer` và trả về `DoubleStream`.

Chọn phương thức theo kiểu nguyên thủy của kết quả. Ví dụ, mã định danh hoặc số đếm có thể cần `long` khi phạm vi giá trị vượt giới hạn của `int`; dữ liệu đo lường có thể cần `double`.

Không chuyển dữ liệu sang `int` chỉ để dùng `mapMultiToInt` nếu việc chuyển đổi có thể làm mất phần dữ liệu quan trọng hoặc gây tràn số.

## 12. Đặc tính lazy và lưu ý khi sử dụng

`mapMultiToInt` là thao tác trung gian. Mapper chỉ chạy khi terminal operation tiêu thụ pipeline, chẳng hạn `sum()`, `toArray()`, `count()` hoặc `summaryStatistics()`.

Nếu terminal operation có thể dừng sớm, pipeline có thể không xử lý mọi phần tử nguồn. Không nên dùng mapper để thực hiện tác dụng phụ bắt buộc phải xảy ra đúng một lần cho mỗi phần tử.

Với parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Hãy giữ việc phát số độc lập theo từng phần tử, không cập nhật một mảng hoặc collection mutable dùng chung từ mapper. Gọi `emit.accept` ngay trong callback; không lưu `IntConsumer` để gọi sau khi mapper kết thúc hoặc từ một tác vụ bất đồng bộ.

## 13. Lỗi thường gặp

**Dùng Consumer<Integer> khi cần IntConsumer.** `mapMultiToInt` yêu cầu `IntConsumer`. Hãy gọi `emit.accept(intValue)` với giá trị nguyên thủy.

**Nghĩ rằng mapper phải trả về int.** Mapper là `BiConsumer`, không trả về kết quả. Mỗi số phải được gửi qua `emit.accept`.

**Chỉ gọi accept một lần dù cần phát nhiều số.** Một phần tử nguồn có thể gọi `accept` nhiều lần. Hãy đặt lời gọi trong vòng lặp hoặc các nhánh tương ứng.

**Dùng mapMultiToInt cho phép biến đổi một-một đơn giản.** Nếu mỗi phần tử luôn tạo đúng một số nguyên, `mapToInt` thường ngắn và dễ hiểu hơn.

**Dùng mapMultiToInt khi mapper tự nhiên tạo IntStream.** Nếu đã có một Stream con phù hợp, `flatMapToInt` có thể thể hiện ý định rõ hơn.

**Boxing sớm rồi unbox lại.** Tránh chuyển sang `Stream<Integer>` nếu pipeline tiếp theo chỉ cần phép toán số học trên `IntStream`.

**Giả định mapMultiToInt luôn nhanh hơn flatMapToInt.** Hãy đo trên dữ liệu và môi trường thực tế khi cần tối ưu.

## 14. Ghi nhớ

- `mapMultiToInt` nhận mapper có kiểu `BiConsumer<? super T, ? super IntConsumer>`.
- `IntConsumer.accept(int)` phát một số nguyên vào `IntStream`.
- Không gọi `accept` để phần tử nguồn không tạo kết quả; gọi nhiều lần để phát nhiều số.
- Dùng `mapMultiToInt` khi logic phát số bằng vòng lặp hoặc nhiều nhánh là tự nhiên.
- Dùng `mapToInt` cho phép biến đổi một-một; dùng `flatMapToInt` khi mapper tự nhiên tạo một `IntStream`.
- `IntStream` hỗ trợ các phép toán như `sum`, `average`, `min`, `max` và `summaryStatistics`.
- `IntConsumer` giúp phát `int` mà không cần đóng gói mỗi giá trị thành `Integer` ở đầu ra.
- `mapMultiToLong` và `mapMultiToDouble` là các biến thể tương ứng cho kiểu nguyên thủy khác.

Khi kết quả cần là các số nguyên và mỗi phần tử nguồn có thể phát không, một hoặc nhiều giá trị, `mapMultiToInt` kết hợp với `IntConsumer` tạo nên một pipeline rõ ràng, tận dụng được các phép toán của `IntStream` và hạn chế boxing không cần thiết.

