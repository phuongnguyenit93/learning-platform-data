# DoubleStream.mapMulti và DoubleMapMultiConsumer

`DoubleStream.mapMulti` là phương thức của Stream chuyên biệt cho kiểu nguyên thủy `double`. Với mỗi giá trị nguồn, mapper có thể phát không, một hoặc nhiều giá trị `double` vào Stream kết quả thông qua `DoubleConsumer`. Phương thức phù hợp khi cần mở rộng một phép đo thành nhiều đại lượng số thực, duyệt một nhóm giá trị hoặc phát kết quả theo vòng lặp và điều kiện.

Cần phân biệt `DoubleStream.mapMulti` với `Stream<T>.mapMultiToDouble`. Cả hai đều tạo `DoubleStream`, nhưng phương thức thứ nhất nhận đầu vào đã là `double`; phương thức thứ hai nhận phần tử nguồn là object kiểu `T` rồi phát các giá trị `double`.

## 1. DoubleStream.mapMulti là gì?

`DoubleStream.mapMulti` được bổ sung trong Java 16. Đây là thao tác trung gian thay thế mỗi phần tử `double` nguồn bằng không, một hoặc nhiều phần tử `double` đầu ra.

Chữ ký phương thức:

```java
DoubleStream mapMulti(DoubleMapMultiConsumer mapper)
```

`DoubleMapMultiConsumer` là functional interface thuộc package `java.util.stream`. Phương thức trừu tượng của nó có dạng:

```java
void accept(double value, DoubleConsumer downstream)
```

Trong đó:

- `value` là giá trị `double` hiện tại của Stream nguồn.
- `downstream` là `DoubleConsumer` dùng để phát các giá trị `double` kết quả.
- Mỗi lần gọi `downstream.accept(result)` tạo một phần tử trong `DoubleStream` kết quả.
- Mapper không trả về giá trị; nó phát kết quả qua Consumer.

Có thể đọc chữ ký này như một quy tắc: nhận một số thực và dùng Consumer để phát ra các số thực tương ứng.

## 2. Vai trò của DoubleMapMultiConsumer và DoubleConsumer

Hai interface có liên quan nhưng đảm nhiệm hai vai trò khác nhau:

| Thành phần | Package | Vai trò |
|---|---|---|
| `DoubleMapMultiConsumer` | `java.util.stream` | Mapper nhận một `double` nguồn và Consumer phát kết quả |
| `DoubleConsumer` | `java.util.function` | Nhận một giá trị `double` đầu ra qua `accept(double)` |

Một lambda tương ứng có dạng:

```java
(value, downstream) -> {
    downstream.accept(value);
}
```

Tham số thứ nhất là dữ liệu nguồn. Tham số thứ hai là kênh phát kết quả. Tên `downstream` chỉ là tên biến; có thể đặt là `emit`, `output` hoặc `consumer`.

Vì đầu vào và đầu ra đều là `double`, `DoubleStream.mapMulti` không có tham số kiểu generic `R` như `Stream<T>.mapMulti`. Do đó, không cần type witness như `.<Double>mapMulti` khi gọi phương thức này.

## 3. Phát không, một hoặc nhiều giá trị double

Số lần gọi `accept` quyết định số phần tử đầu ra mà một phần tử nguồn đóng góp:

| Cách mapper xử lý | Kết quả |
|---|---|
| Không gọi `downstream.accept` | Không phát phần tử |
| Gọi `downstream.accept` một lần | Phát một phần tử |
| Gọi `downstream.accept` nhiều lần | Phát nhiều phần tử |

Ví dụ, chỉ phát các giá trị dương:

```java
import java.util.stream.DoubleStream;

double[] positives = DoubleStream.of(-2.5, 0.0, 1.25, 4.5, -0.75)
    .mapMulti((value, emit) -> {
        if (value > 0.0) {
            emit.accept(value);
        }
    })
    .toArray();
```

Kết quả:

```text
[1.25, 4.5]
```

Các giá trị âm và số không không gọi `emit.accept`, nên không xuất hiện trong kết quả. Ví dụ này minh họa cơ chế phát không hoặc một giá trị từ mỗi phần tử nguồn.

Nếu mục tiêu duy nhất là giữ các giá trị dương, `filter` thường thể hiện ý định rõ hơn:

```java
import java.util.stream.DoubleStream;

double[] positives = DoubleStream.of(-2.5, 0.0, 1.25, 4.5, -0.75)
    .filter(value -> value > 0.0)
    .toArray();
```

## 4. Một giá trị nguồn phát nhiều giá trị double

`DoubleStream.mapMulti` hữu ích khi mỗi giá trị nguồn cần được mở rộng thành một nhóm số thực. Ví dụ, với mỗi giá trị dương, phát giá trị ban đầu và một nửa của nó:

```java
import java.util.stream.DoubleStream;

double[] expanded = DoubleStream.of(8.0, 5.0, 2.0)
    .mapMulti((value, emit) -> {
        if (value > 0.0) {
            emit.accept(value);
            emit.accept(value / 2.0);
        }
    })
    .toArray();
```

Kết quả:

```text
[8.0, 4.0, 5.0, 2.5, 2.0, 1.0]
```

Mỗi giá trị nguồn phát hai kết quả theo đúng thứ tự gọi `emit.accept`. Nếu giá trị nguồn không dương, mapper không phát phần tử nào.

Đây là dạng xử lý một-nhiều tự nhiên: mapper gọi Consumer trực tiếp thay vì tạo một `DoubleStream` con cho từng phần tử nguồn.

## 5. Phát kết quả theo nhiều điều kiện

Một giá trị nguồn có thể tạo ra các kết quả khác nhau tùy điều kiện. Ví dụ, với mỗi phép đo hợp lệ, phát giá trị Celsius và giá trị Fahrenheit tương ứng:

```java
import java.util.stream.DoubleStream;

double[] converted = DoubleStream.of(0.0, 20.0, 37.0, -300.0)
    .mapMulti((celsius, emit) -> {
        if (celsius >= -273.15) {
            emit.accept(celsius);

            double fahrenheit = celsius * 9.0 / 5.0 + 32.0;
            emit.accept(fahrenheit);
        }
    })
    .toArray();
```

Các nhánh phát kết quả theo thứ tự Celsius rồi Fahrenheit. Giá trị `-300.0` thấp hơn độ không tuyệt đối theo mô hình nhiệt độ Celsius nên không tạo kết quả.

Trong ứng dụng thực tế, cần xác định rõ đơn vị và quy tắc làm tròn theo yêu cầu nghiệp vụ. Ví dụ này minh họa cách một phần tử nguồn có thể phát nhiều giá trị khác nhau, không phải quy tắc định dạng nhiệt độ cho mọi hệ thống.

## 6. Ví dụ: trích xuất nhiều đại lượng từ một bản ghi

Một bản ghi phép đo có thể chứa nhiều đại lượng số thực. Mapper có thể kiểm tra từng trường rồi phát những giá trị hợp lệ:

```java
import java.util.List;

record SensorReading(
    String sensorId,
    double temperature,
    double pressure,
    double humidity
) {}

List<SensorReading> readings = List.of(
    new SensorReading("S-01", 25.5, 1.02, 65.0),
    new SensorReading("S-02", 82.0, 1.15, 72.5),
    new SensorReading("S-03", 28.0, Double.NaN, 88.0)
);

double[] validMeasurements = readings.stream()
    .mapMultiToDouble((reading, emit) -> {
        if (Double.isFinite(reading.temperature())) {
            emit.accept(reading.temperature());
        }

        if (Double.isFinite(reading.pressure())) {
            emit.accept(reading.pressure());
        }

        if (Double.isFinite(reading.humidity())) {
            emit.accept(reading.humidity());
        }
    })
    .toArray();
```

Mỗi cảm biến có thể phát tối đa ba giá trị. Giá trị áp suất `NaN` của cảm biến `S-03` bị bỏ qua; các giá trị hữu hạn còn lại được phát theo thứ tự các trường trong mapper.

Ví dụ này dùng `Stream<SensorReading>.mapMultiToDouble` vì nguồn là các đối tượng `SensorReading`, còn đầu ra là các giá trị nguyên thủy `double`. Nếu nguồn đã là `DoubleStream`, dùng `DoubleStream.mapMulti`.

## 7. Làm phẳng danh sách các giá trị double

Một đối tượng có thể chứa danh sách các phép đo. Ta có thể làm phẳng các danh sách con thành một `DoubleStream`:

```java
import java.util.List;

record SensorGroup(String name, List<Double> readings) {}

List<SensorGroup> groups = List.of(
    new SensorGroup("north", List.of(21.5, 22.0)),
    new SensorGroup("south", List.of(25.25, 24.75)),
    new SensorGroup("empty", List.of())
);

double[] allReadings = groups.stream()
    .mapMultiToDouble((group, emit) -> {
        for (Double reading : group.readings()) {
            if (reading != null && Double.isFinite(reading)) {
                emit.accept(reading);
            }
        }
    })
    .toArray();
```

Kết quả:

```text
[21.5, 22.0, 25.25, 24.75]
```

Vòng lặp duyệt các giá trị trong từng nhóm và phát giá trị hữu hạn. Nhóm rỗng không phát phần tử nào. Vì collection chứa `Double`, ví dụ kiểm tra null trước khi gọi `emit.accept`; giá trị `Double` được unbox thành `double` khi truyền vào `DoubleConsumer`.

Nếu mỗi phần tử nguồn đã là một `DoubleStream` con, `flatMap` có thể diễn đạt tự nhiên hơn. `mapMulti` phù hợp khi việc duyệt collection con bằng vòng lặp hoặc có điều kiện phát rõ ràng.

## 8. Các phép toán của DoubleStream

`DoubleStream.mapMulti` trả về `DoubleStream`, vì vậy có thể dùng trực tiếp các thao tác chuyên biệt cho `double`:

| Thao tác | Công dụng |
|---|---|
| `sum()` | Tính tổng và trả về `double` |
| `average()` | Tính trung bình và trả về `OptionalDouble` |
| `min()` / `max()` | Tìm giá trị nhỏ nhất/lớn nhất và trả về `OptionalDouble` |
| `count()` | Đếm số phần tử |
| `summaryStatistics()` | Thu thập count, sum, min, max và average |
| `toArray()` | Thu kết quả vào `double[]` |
| `boxed()` | Chuyển thành `Stream<Double>` khi API phía sau cần object |

Ví dụ thống kê các giá trị nhiệt độ:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics statistics = DoubleStream.of(24.5, 28.0, 26.5)
    .summaryStatistics();
```

Với dữ liệu trên:

- `count`: 3.
- `sum`: 79.0.
- `min`: 24.5.
- `max`: 28.0.
- `average`: khoảng 26.33.

Nếu Stream rỗng, `sum()` trả về `0.0`, còn `average()`, `min()` và `max()` trả về `OptionalDouble.empty()`. Hãy xử lý trường hợp không có dữ liệu nếu nghiệp vụ cần phân biệt "không có phép đo" với kết quả trung bình bằng không.

Có thể dùng `summaryStatistics()` ngay sau `mapMulti` để thống kê các giá trị được phát:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics statistics = DoubleStream.of(1.5, 2.5, 3.5)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value * 2.0);
    })
    .summaryStatistics();
```

Mỗi giá trị nguồn phát hai số, sau đó `DoubleSummaryStatistics` thu thập các chỉ số tổng hợp trong một lần duyệt.

## 9. Đặc tính số thực double và sai số làm tròn

`double` là kiểu dấu phẩy động 64-bit theo chuẩn IEEE 754. Nhiều số thập phân không thể biểu diễn chính xác bằng dạng nhị phân, vì vậy phép tính có thể có sai số làm tròn.

Ví dụ:

```java
double total = 0.1 + 0.2;
System.out.println(total);
```

Kết quả thường được hiển thị gần với:

```text
0.30000000000000004
```

Vì vậy:

- Không so sánh hai giá trị `double` được tính toán bằng phép `==` nếu nghiệp vụ cần kiểm tra gần bằng.
- Có thể so sánh sai số tuyệt đối với một ngưỡng phù hợp khi bài toán cho phép.
- Không giả định đổi thứ tự cộng các số thực sẽ luôn cho cùng kết quả bit-for-bit.
- Với tiền tệ hoặc dữ liệu cần độ chính xác thập phân, ưu tiên `BigDecimal` và quy tắc scale/rounding phù hợp.

Ví dụ kiểm tra hai giá trị gần bằng:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-9;

boolean closeEnough = Math.abs(actual - expected) < tolerance;
```

Ngưỡng `tolerance` phải được chọn theo đơn vị và độ chính xác của bài toán; không có một giá trị phù hợp cho mọi miền dữ liệu.

Nếu cần phép tính thập phân chính xác, hãy giữ dữ liệu ở dạng `BigDecimal` từ lúc đọc đầu vào:

```java
import java.math.BigDecimal;

BigDecimal total = new BigDecimal("0.10")
    .add(new BigDecimal("0.20"));
```

Kết quả là `0.30`. Tránh tạo `BigDecimal` từ một phép tính `double` đã có sai số nếu mục tiêu là giữ chính xác số thập phân ban đầu.

## 10. Xử lý NaN và vô cực

Kiểu `double` có thể chứa các giá trị đặc biệt:

- `Double.NaN`: kết quả không phải số, chẳng hạn từ một phép toán không hợp lệ.
- `Double.POSITIVE_INFINITY`: dương vô cực.
- `Double.NEGATIVE_INFINITY`: âm vô cực.

Nếu nghiệp vụ chỉ chấp nhận giá trị hữu hạn, dùng `Double.isFinite(value)` trước khi phát. Phương thức trả về `false` cho NaN và cả hai giá trị vô cực.

```java
import java.util.stream.DoubleStream;

double[] finiteValues = DoubleStream.of(
        12.5,
        Double.NaN,
        Double.POSITIVE_INFINITY,
        -3.75
    )
    .mapMulti((value, emit) -> {
        if (Double.isFinite(value)) {
            emit.accept(value);
        }
    })
    .toArray();
```

Kết quả:

```text
[12.5, -3.75]
```

Nếu NaN hoặc vô cực có ý nghĩa nghiệp vụ, đừng tự động loại bỏ chúng. Hãy xác định rõ cách xử lý các giá trị này trước khi tính thống kê. NaN có thể biểu thị phép đo không hợp lệ; vô cực có thể là dấu hiệu tràn hoặc trạng thái đặc biệt cần ghi nhận.

## 11. So sánh DoubleStream.mapMulti với map, filter và flatMap

Các thao tác có hình dạng đầu ra khác nhau:

| Thao tác | Kết quả từ một phần tử nguồn | Mục đích |
|---|---:|---|
| `map` | Chính xác một `double` | Chuyển một số thành một số khác |
| `filter` | Không hoặc một `double` | Giữ hoặc loại số hiện tại |
| `flatMap` | Không, một hoặc nhiều `double` | Chuyển thành `DoubleStream` con rồi làm phẳng |
| `mapMulti` | Không, một hoặc nhiều `double` | Phát số trực tiếp qua `DoubleConsumer` |

Dùng `map` khi mỗi giá trị luôn tạo đúng một giá trị:

```java
import java.util.stream.DoubleStream;

double[] doubled = DoubleStream.of(1.5, 2.0, 3.25)
    .map(value -> value * 2.0)
    .toArray();
```

Dùng `filter` khi chỉ giữ giá trị thỏa điều kiện:

```java
import java.util.stream.DoubleStream;

double[] positive = DoubleStream.of(-1.5, 0.0, 2.5, 4.0)
    .filter(value -> value > 0.0)
    .toArray();
```

Dùng `flatMap` khi phép biến đổi tự nhiên trả về một `DoubleStream` con:

```java
import java.util.stream.DoubleStream;

double[] expanded = DoubleStream.of(2.0, 3.0)
    .flatMap(value -> DoubleStream.of(value, value / 2.0))
    .toArray();
```

Cùng kết quả có thể viết bằng `mapMulti`:

```java
import java.util.stream.DoubleStream;

double[] expanded = DoubleStream.of(2.0, 3.0)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value / 2.0);
    })
    .toArray();
```

Chọn `flatMap` khi Stream con là cách biểu diễn tự nhiên và muốn kết hợp các thao tác Stream trên từng nhóm. Chọn `mapMulti` khi vòng lặp hoặc các nhánh điều kiện mô tả logic phát kết quả trực tiếp và dễ đọc hơn.

Không mặc định `mapMulti` luôn nhanh hơn `flatMap`. Hiệu năng phụ thuộc số lượng đầu ra, logic mapper, phiên bản JDK và các thao tác tiếp theo. Hãy chọn cách diễn đạt rõ ràng; chỉ tối ưu theo số đo đại diện khi có yêu cầu hiệu năng cụ thể.

## 12. Phân biệt DoubleStream.mapMulti và Stream.mapMultiToDouble

Hai phương thức đều có thể tạo `DoubleStream`, nhưng dùng khi kiểu dữ liệu nguồn khác nhau:

| Phương thức | Kiểu nguồn | Mapper nhận | Kiểu kết quả |
|---|---|---|---|
| `DoubleStream.mapMulti` | `DoubleStream` | `double` và `DoubleConsumer` | `DoubleStream` |
| `Stream<T>.mapMultiToDouble` | `Stream<T>` | `T` và `DoubleConsumer` | `DoubleStream` |

Ví dụ dùng `DoubleStream.mapMulti` khi nguồn đã là các số thực:

```java
import java.util.stream.DoubleStream;

double[] expanded = DoubleStream.of(10.0, 20.0)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value + 0.5);
    })
    .toArray();
```

Ví dụ dùng `Stream<T>.mapMultiToDouble` khi nguồn là các đối tượng:

```java
import java.util.List;

record Product(String sku, double price, double discountRate) {}

List<Product> products = List.of(
    new Product("A-01", 100.0, 0.10),
    new Product("B-02", 80.0, 0.05)
);

double[] prices = products.stream()
    .mapMultiToDouble((product, emit) -> {
        emit.accept(product.price());
        emit.accept(product.price() * (1.0 - product.discountRate()));
    })
    .toArray();
```

Ở ví dụ đầu, phần tử nguồn vốn là `double` nên dùng `DoubleStream.mapMulti`. Ở ví dụ sau, phần tử nguồn là `Product` nên dùng `Stream<Product>.mapMultiToDouble` để phát các giá trị `double`. Cả hai đều có thể tiếp tục bằng `sum()`, `average()`, `toArray()` hoặc các thao tác số thực khác.

## 13. DoubleStream và primitive specialization

`DoubleStream` làm việc trực tiếp với kiểu nguyên thủy `double`. Trong `DoubleStream.mapMulti`, Consumer đầu ra là `DoubleConsumer`, nên lời gọi `accept(double)` không cần đóng gói từng giá trị thành `Double`.

So sánh:

| Cách xử lý | Consumer | Kiểu Stream |
|---|---|---|
| `Stream<Double>.mapMulti` | `Consumer<Double>` | `Stream<Double>` |
| `DoubleStream.mapMulti` | `DoubleConsumer` | `DoubleStream` |

Ví dụ dùng Stream chứa wrapper:

```java
import java.util.List;

List<Double> values = List.of(1.5, 2.5, 3.5);

List<Double> expanded = values.stream()
    .<Double>mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2.0);
    })
    .toList();
```

Ví dụ dùng primitive stream:

```java
import java.util.stream.DoubleStream;

double[] expanded = DoubleStream.of(1.5, 2.5, 3.5)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2.0);
    })
    .toArray();
```

Primitive specialization có thể tránh boxing trong phần phát và xử lý các giá trị đầu ra. Tuy nhiên, nếu dữ liệu bắt đầu từ `List<Double>`, bước tạo `DoubleStream` có thể cần unbox; nếu kết quả cuối cùng cần `List<Double>`, bước `boxed()` sẽ tạo wrapper. Hãy xét toàn bộ pipeline thay vì chỉ một thao tác riêng lẻ.

## 14. Chuyển từ DoubleStream sang object khi cần

Nếu các phép toán số học đã hoàn tất và bước tiếp theo cần object, có thể dùng `mapToObj` hoặc `boxed()`.

Ví dụ tạo nhãn cho từng giá trị:

```java
import java.util.stream.DoubleStream;

String[] labels = DoubleStream.of(21.5, 24.0)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value + 0.5);
    })
    .mapToObj(value -> "reading=" + value)
    .toArray(String[]::new);
```

Nếu chỉ cần danh sách `Double`, dùng `boxed()`:

```java
import java.util.List;
import java.util.stream.DoubleStream;

List<Double> boxedValues = DoubleStream.of(1.5, 2.5, 3.5)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value * 2.0);
    })
    .boxed()
    .toList();
```

Chỉ chuyển sang object khi kiểu tham chiếu cần thiết cho API hoặc mô hình dữ liệu tiếp theo. Nếu pipeline chỉ tính toán số học, giữ `DoubleStream` sẽ tránh boxing không cần thiết.

## 15. Thứ tự phát và parallel Stream

Trong một lần mapper chạy, các lời gọi `emit.accept` được thực hiện theo thứ tự chương trình. Với Stream có encounter order, kết quả được kết hợp theo thứ tự phần tử nguồn và thứ tự gọi Consumer trong từng mapper.

Ví dụ:

```java
import java.util.stream.DoubleStream;

double[] values = DoubleStream.of(1.0, 2.0)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number + 10.0);
    })
    .toArray();
```

Kết quả là `[1.0, 11.0, 2.0, 12.0]`.

Khi dùng parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Nếu nguồn có encounter order, các thao tác bảo toàn thứ tự như `toArray()` vẫn thu kết quả theo encounter order. Tuy nhiên, không dựa vào thời điểm mapper bắt đầu hoặc kết thúc để thực hiện tác dụng phụ theo thứ tự nghiệp vụ.

Tránh cập nhật một mảng hoặc collection mutable dùng chung bên trong mapper. Hãy phát số qua `DoubleConsumer` và để pipeline hoặc terminal operation thu thập kết quả. Nếu terminal operation là `forEach` trên parallel Stream, hành động có thể được gọi theo thứ tự bất kỳ; dùng `forEachOrdered` nếu cần thực hiện hành động cuối theo encounter order.

Với phép cộng số thực, thứ tự cộng có thể ảnh hưởng đến sai số làm tròn. Khi chuyển pipeline sang parallel, không giả định tổng luôn có cùng kết quả bit-for-bit với xử lý tuần tự.

## 16. Lazy evaluation và phạm vi sử dụng Consumer

`DoubleStream.mapMulti` là thao tác trung gian. Mapper chỉ được thực thi khi terminal operation tiêu thụ pipeline, chẳng hạn `sum()`, `average()`, `toArray()` hoặc `summaryStatistics()`.

Terminal operation có thể dừng sớm, ví dụ `findFirst()` hoặc `anyMatch(...)`. Tuy nhiên, không nên giả định thao tác dừng sớm sẽ ngắt một vòng lặp phát nhiều giá trị ngay giữa lần gọi mapper hiện tại. Mapper gọi Consumer đồng bộ; hãy giữ số kết quả phát ra cho mỗi phần tử ở mức hợp lý.

Consumer được truyền vào mapper để phát kết quả trong lần gọi hiện tại. Gọi `accept` ngay trong callback; không lưu `DoubleConsumer` để gọi sau khi mapper kết thúc hoặc chuyển nó sang tác vụ bất đồng bộ.

Nếu một phần tử có thể phát lượng giá trị rất lớn hoặc không giới hạn, một `DoubleStream` con qua `flatMap` thường mô tả nguồn dữ liệu phù hợp hơn. Không dựa vào `limit()` phía sau để bảo đảm vòng lặp bên trong mapper sẽ tự dừng sau một số lần phát cố định.

## 17. Lỗi thường gặp

**Nhầm DoubleMapMultiConsumer với DoubleConsumer.** `DoubleMapMultiConsumer` là mapper nhận hai tham số; `DoubleConsumer` là Consumer nhận từng giá trị `double` đầu ra.

**Nghĩ rằng mapper phải return double.** Mapper là callback không trả về giá trị. Hãy gọi `downstream.accept(value)` để phát số.

**Dùng type witness như Stream generic.** `DoubleStream.mapMulti` không có tham số kiểu `R`, vì vậy không viết `.<Double>mapMulti`. Kiểu đầu vào và đầu ra đều là `double`.

**Dùng mapMulti khi chỉ cần lọc.** Nếu chỉ giữ hoặc loại giá trị hiện tại, `filter` thường ngắn gọn và dễ đọc hơn.

**Dùng mapMulti khi mỗi phần tử chỉ tạo đúng một số.** Nếu mỗi đầu vào luôn tạo một đầu ra, `map` thường diễn đạt rõ hơn.

**Giả định double biểu diễn chính xác mọi số thập phân.** Kiểu `double` có sai số nhị phân; dùng `BigDecimal` khi cần độ chính xác thập phân theo quy tắc nghiệp vụ.

**Bỏ qua NaN hoặc vô cực mà không xác định quy tắc.** Hãy quyết định các giá trị đặc biệt là dữ liệu hợp lệ, cần loại bỏ hay cần xử lý riêng.

**Boxing sớm rồi unbox lại.** Tránh chuyển sang `Stream<Double>` nếu các bước tiếp theo chỉ cần phép toán trên `DoubleStream`.

**Giả định mapMulti luôn nhanh hơn flatMap.** Hãy chọn theo cách biểu đạt phù hợp và benchmark trên dữ liệu thực tế khi cần tối ưu.

**Giữ Consumer để gọi sau callback.** Hãy phát kết quả ngay trong lần mapper chạy và không dùng Consumer như callback bất đồng bộ.

## 18. Ghi nhớ

- `DoubleStream.mapMulti` nhận `DoubleMapMultiConsumer` và trả về `DoubleStream`.
- `DoubleMapMultiConsumer.accept(double, DoubleConsumer)` nhận giá trị nguồn cùng Consumer phát giá trị đầu ra.
- Mỗi lần `DoubleConsumer.accept(double)` tạo một phần tử; không gọi để phát không phần tử; gọi nhiều lần để phát nhiều số.
- Dùng `DoubleStream.mapMulti` khi nguồn đã là `double` và logic mở rộng bằng vòng lặp hoặc nhánh điều kiện.
- Dùng `Stream<T>.mapMultiToDouble` khi nguồn là object nhưng đầu ra là một hoặc nhiều giá trị `double`.
- Dùng `map` cho quan hệ một-một, `filter` cho lọc, `flatMap` khi mapper tự nhiên tạo `DoubleStream` con.
- `DoubleStream` giữ giá trị nguyên thủy và hỗ trợ các phép toán số học chuyên biệt.
- Chú ý sai số dấu phẩy động, NaN, vô cực, lazy evaluation, encounter order và an toàn khi chạy song song.
- Dùng `BigDecimal` khi cần số thập phân chính xác; dùng `boxed()` hoặc `mapToObj` khi bước tiếp theo cần object.

Khi đầu vào và đầu ra đều là số thực, `DoubleStream.mapMulti` cùng `DoubleMapMultiConsumer` cung cấp cách phát không, một hoặc nhiều giá trị trực tiếp trong primitive Stream pipeline, giúp mã thể hiện rõ logic mở rộng dữ liệu mà không cần tạo Stream con cho từng phần tử.

