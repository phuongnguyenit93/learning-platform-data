# mapMultiToDouble và DoubleConsumer cho kết quả số thực

`Stream.mapMultiToDouble` là biến thể chuyên biệt của `mapMulti` khi các giá trị đầu ra có kiểu nguyên thủy `double`. Mapper nhận phần tử nguồn cùng một `DoubleConsumer`; mỗi lần gọi `accept(double)` sẽ phát một giá trị vào `DoubleStream` kết quả. Một phần tử nguồn có thể phát không, một hoặc nhiều giá trị số thực.

Phương thức này hữu ích khi cần trích xuất một vài đại lượng số từ mỗi đối tượng, duyệt một nhóm phép đo, phát các giá trị đã chuẩn hóa hoặc chọn các chỉ số thỏa điều kiện. Vì kết quả là `DoubleStream`, pipeline có thể tiếp tục bằng các phép toán số học chuyên biệt mà không cần đóng gói từng giá trị thành `Double`.

## 1. mapMultiToDouble là gì?

`mapMultiToDouble` là phương thức trên `Stream<T>`, được bổ sung trong Java 16. Phương thức nhận mapper kiểu `BiConsumer` và trả về `DoubleStream`.

Chữ ký tổng quát:

```java
DoubleStream mapMultiToDouble(
    BiConsumer<? super T, ? super DoubleConsumer> mapper
)
```

Các thành phần:

- `T` là kiểu phần tử của Stream nguồn.
- Mapper nhận phần tử nguồn kiểu `T` ở tham số thứ nhất.
- Tham số thứ hai là `DoubleConsumer`, dùng để phát các giá trị `double`.
- Mỗi lần gọi `accept(double)` tạo một phần tử trong `DoubleStream` kết quả.
- Mapper không trả về `double` trực tiếp; nó phát từng giá trị qua Consumer.

Ví dụ khung:

```java
import java.util.stream.DoubleStream;
import java.util.stream.Stream;

Stream<String> source = Stream.of("sensor-A", "sensor-B");

DoubleStream result = source.mapMultiToDouble((sensor, emit) -> {
    emit.accept(21.5);
    emit.accept(22.75);
});
```

Mỗi phần tử nguồn phát hai giá trị `double`. Nếu mapper không gọi `emit.accept`, phần tử nguồn hiện tại không đóng góp giá trị nào vào kết quả.

## 2. DoubleConsumer và phương thức accept(double)

`DoubleConsumer` là functional interface trong `java.util.function`, đại diện cho một hành động nhận một giá trị nguyên thủy kiểu `double`.

```java
@FunctionalInterface
public interface DoubleConsumer {
    void accept(double value);
}
```

Trong mapper của `mapMultiToDouble`, tham số thứ hai có kiểu `DoubleConsumer`. Ta thường đặt tên là `emit`, `output` hoặc `consumer`:

```java
import java.util.List;

List<String> measurements = List.of("morning", "afternoon");

double[] values = measurements.stream()
    .mapMultiToDouble((period, emit) -> {
        emit.accept(period.length() * 1.5);
    })
    .toArray();
```

Biểu thức `period.length() * 1.5` có kiểu `double` và được truyền trực tiếp vào `DoubleConsumer.accept`. Không cần tạo đối tượng `Double` để phát giá trị.

Có thể gọi `accept` nhiều lần trong cùng một lần mapper chạy:

```java
import java.util.List;

List<String> measurements = List.of("morning", "afternoon");

double[] values = measurements.stream()
    .mapMultiToDouble((period, emit) -> {
        emit.accept(period.length());
        emit.accept(period.length() / 2.0);
    })
    .toArray();
```

Mỗi phần tử nguồn phát hai số thực. Kết quả được thu vào mảng `double[]`.

## 3. Phát không, một hoặc nhiều giá trị double

Số lần gọi `accept` quyết định số phần tử đầu ra mà mỗi phần tử nguồn đóng góp:

| Cách mapper xử lý | Số phần tử đầu ra |
|---|---:|
| Không gọi `emit.accept` | 0 |
| Gọi `emit.accept` một lần | 1 |
| Gọi `emit.accept` nhiều lần | Nhiều |

Ví dụ, mỗi phép đo có thể cung cấp nhiệt độ và độ ẩm. Ta chỉ phát các giá trị hợp lệ theo điều kiện nghiệp vụ:

```java
import java.util.List;

record ClimateSample(String station, double temperature, double humidity) {}

List<ClimateSample> samples = List.of(
    new ClimateSample("HCM-01", 31.5, 72.0),
    new ClimateSample("HCM-02", 34.0, -1.0),
    new ClimateSample("HCM-03", 28.5, 81.0)
);

double[] validReadings = samples.stream()
    .mapMultiToDouble((sample, emit) -> {
        if (Double.isFinite(sample.temperature())) {
            emit.accept(sample.temperature());
        }

        if (Double.isFinite(sample.humidity())
                && sample.humidity() >= 0.0
                && sample.humidity() <= 100.0) {
            emit.accept(sample.humidity());
        }
    })
    .toArray();
```

Kết quả:

```text
[31.5, 72.0, 34.0, 28.5, 81.0]
```

Mẫu `HCM-02` không phát độ ẩm vì giá trị không nằm trong khoảng hợp lệ. Các mẫu còn lại phát cả hai đại lượng. Ví dụ minh họa việc một phần tử nguồn có thể phát một hoặc nhiều giá trị tùy điều kiện.

Nếu chỉ cần giữ hoặc loại một giá trị số thực đã có sẵn, `filter` thường thể hiện ý định rõ hơn. `mapMultiToDouble` phù hợp khi một phần tử nguồn có thể tạo nhiều số thực hoặc cần duyệt dữ liệu con để phát chúng.

## 4. Ví dụ: phát nhiều chỉ số từ một đối tượng

Một phép đo thiết bị có thể có nhiều đại lượng cần đưa vào cùng một phép thống kê. Mapper có thể kiểm tra từng trường rồi phát các giá trị hợp lệ:

```java
import java.util.List;

record DeviceReading(
    String deviceId,
    double voltage,
    double current,
    double temperature
) {}

List<DeviceReading> readings = List.of(
    new DeviceReading("D-01", 12.4, 1.8, 35.0),
    new DeviceReading("D-02", 0.0, 2.1, 82.5),
    new DeviceReading("D-03", 11.9, 0.0, 29.5)
);

double[] metrics = readings.stream()
    .mapMultiToDouble((reading, emit) -> {
        if (reading.voltage() > 0.0) {
            emit.accept(reading.voltage());
        }

        if (reading.current() > 0.0) {
            emit.accept(reading.current());
        }

        if (reading.temperature() > 0.0) {
            emit.accept(reading.temperature());
        }
    })
    .toArray();
```

Mỗi thiết bị có thể phát tối đa ba giá trị. Các trường không thỏa điều kiện bị bỏ qua; thứ tự giá trị trong kết quả tuân theo thứ tự các lệnh gọi `emit.accept` trong mapper và thứ tự các phần tử nguồn khi Stream có encounter order.

Cần lưu ý rằng ví dụ gộp các đại lượng có đơn vị khác nhau vào cùng một `DoubleStream` chỉ để minh họa cơ chế phát nhiều số. Trong nghiệp vụ thực tế, không nên tính trung bình chung giữa volt, ampere và độ C vì chúng không cùng ý nghĩa hoặc đơn vị. Hãy tách pipeline theo loại đại lượng khi cần thống kê có ý nghĩa.

## 5. Làm phẳng danh sách các giá trị double

Một đối tượng có thể chứa danh sách các phép đo kiểu `Double`. Ta có thể làm phẳng các danh sách con thành một `DoubleStream`:

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

Nếu dữ liệu nguồn đã là một `DoubleStream` cho từng nhóm, `flatMapToDouble` có thể diễn đạt tự nhiên hơn. `mapMultiToDouble` phù hợp khi cần duyệt collection con bằng vòng lặp hoặc có điều kiện phát rõ ràng.

## 6. Các phép toán của DoubleStream

`mapMultiToDouble` trả về `DoubleStream`, vì vậy có thể dùng trực tiếp các thao tác chuyên biệt cho `double`:

| Thao tác | Công dụng |
|---|---|
| `sum()` | Tính tổng và trả về `double` |
| `average()` | Tính trung bình và trả về `OptionalDouble` |
| `min()` / `max()` | Tìm giá trị nhỏ nhất/lớn nhất và trả về `OptionalDouble` |
| `count()` | Đếm số phần tử |
| `summaryStatistics()` | Thu thập count, sum, min, max và average |
| `toArray()` | Thu kết quả vào `double[]` |
| `boxed()` | Chuyển thành `Stream<Double>` khi API phía sau cần object |

Ví dụ tính tổng và thống kê các phép đo nhiệt độ:

```java
import java.util.DoubleSummaryStatistics;
import java.util.List;

record TemperatureSample(String station, double temperature) {}

List<TemperatureSample> temperatures = List.of(
    new TemperatureSample("A", 24.5),
    new TemperatureSample("B", 28.0),
    new TemperatureSample("C", 26.5)
);

DoubleSummaryStatistics statistics = temperatures.stream()
    .mapMultiToDouble((sample, emit) -> {
        if (Double.isFinite(sample.temperature())) {
            emit.accept(sample.temperature());
        }
    })
    .summaryStatistics();
```

Với dữ liệu trên:

- `count`: 3.
- `sum`: 79.0.
- `min`: 24.5.
- `max`: 28.0.
- `average`: khoảng 26.33.

Nếu Stream rỗng, `sum()` trả về `0.0`, còn `average()`, `min()` và `max()` trả về `OptionalDouble.empty()`. Hãy xử lý trường hợp không có dữ liệu nếu nghiệp vụ cần phân biệt "không có phép đo" với kết quả trung bình bằng không.

## 7. Chú ý đặc tính của số thực double

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
- Không giả định thứ tự cộng các số thực có thể thay đổi mà vẫn cho cùng kết quả bit-for-bit.
- Khi cần độ chính xác thập phân chính xác, chẳng hạn tiền tệ, dùng `BigDecimal` với quy tắc scale và rounding phù hợp.

Ví dụ, tạo `BigDecimal` từ chuỗi thập phân để giữ đúng giá trị đầu vào:

```java
import java.math.BigDecimal;

BigDecimal total = new BigDecimal("0.10")
    .add(new BigDecimal("0.20"));
```

Kết quả là `0.30`. Tránh tạo `BigDecimal` từ một phép tính `double` đã có sai số nếu mục tiêu là giữ chính xác số thập phân ban đầu.

Ví dụ kiểm tra hai giá trị gần bằng:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-9;

boolean closeEnough = Math.abs(actual - expected) < tolerance;
```

Ngưỡng `tolerance` phải được chọn theo đơn vị và độ chính xác cần thiết của bài toán; không có một giá trị phù hợp cho mọi miền dữ liệu.

## 8. Xử lý NaN và vô cực

Kiểu `double` có thể chứa các giá trị đặc biệt:

- `Double.NaN`: kết quả không phải số, ví dụ một số phép toán không hợp lệ.
- `Double.POSITIVE_INFINITY`: dương vô cực.
- `Double.NEGATIVE_INFINITY`: âm vô cực.

Nếu nghiệp vụ chỉ chấp nhận giá trị hữu hạn, dùng `Double.isFinite(value)` trước khi phát. Phương thức này trả về `false` cho NaN và cả hai giá trị vô cực.

```java
import java.util.List;

List<Double> rawValues = List.of(
    12.5,
    Double.NaN,
    Double.POSITIVE_INFINITY,
    -3.75
);

double[] finiteValues = rawValues.stream()
    .mapMultiToDouble((value, emit) -> {
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

Nếu NaN hoặc vô cực có ý nghĩa nghiệp vụ, đừng tự động loại bỏ chúng. Hãy xác định rõ cách các giá trị này được xử lý trước khi tính thống kê. Ví dụ, NaN có thể biểu thị phép đo không hợp lệ; vô cực có thể là dấu hiệu tràn hoặc một trạng thái đặc biệt cần ghi nhận.

## 9. So sánh mapMultiToDouble, mapMulti và mapToDouble

Các phương thức này có hình dạng đầu ra khác nhau:

| Phương thức | Mapper phát/trả về | Kiểu Stream kết quả |
|---|---|---|
| `mapMulti` | `Consumer<R>` nhận object kiểu `R` | `Stream<R>` |
| `mapMultiToDouble` | `DoubleConsumer` nhận `double` | `DoubleStream` |
| `mapToDouble` | Mapper trả về đúng một `double` | `DoubleStream` |

Dùng `mapToDouble` khi mỗi phần tử nguồn luôn tạo đúng một số thực:

Tiếp tục dùng `TemperatureSample` và danh sách `temperatures` đã khai báo ở mục 6:

```java
double[] values = temperatures.stream()
    .mapToDouble(TemperatureSample::temperature)
    .toArray();
```

Dùng `mapMultiToDouble` khi một phần tử nguồn có thể phát không hoặc nhiều số thực:

```java
double[] validValues = temperatures.stream()
    .mapMultiToDouble((sample, emit) -> {
        if (Double.isFinite(sample.temperature())
                && sample.temperature() >= 0.0) {
            emit.accept(sample.temperature());
        }
    })
    .toArray();
```

Nếu dùng `mapMulti` để phát các đối tượng `Double`, kiểu đầu ra là `Stream<Double>`:

```java
List<Double> values = temperatures.stream()
    .<Double>mapMulti((sample, emit) -> {
        emit.accept(sample.temperature());
    })
    .toList();
```

Khi các bước tiếp theo là tính tổng, trung bình hoặc thống kê số học, `mapMultiToDouble` thường phù hợp hơn vì giữ kết quả trong `DoubleStream`. Nếu API đích cần object `Double`, có thể dùng `mapMulti` hoặc chuyển từ `DoubleStream` bằng `boxed()`.

## 10. So sánh với flatMapToDouble

`flatMapToDouble` phù hợp khi mapper tự nhiên trả về một `DoubleStream` cho mỗi phần tử nguồn. Với các nhóm cảm biến, có thể viết:

```java
import java.util.List;

record SensorGroup(String name, List<Double> readings) {}

List<SensorGroup> groups = List.of(
    new SensorGroup("north", List.of(21.5, 22.0)),
    new SensorGroup("south", List.of(25.25, 24.75))
);

double[] allReadings = groups.stream()
    .flatMapToDouble(group ->
        group.readings().stream()
            .filter(value -> value != null && Double.isFinite(value))
            .mapToDouble(Double::doubleValue)
    )
    .toArray();
```

Cùng logic có thể viết bằng `mapMultiToDouble`:

```java
double[] allReadings = groups.stream()
    .mapMultiToDouble((group, emit) -> {
        for (Double value : group.readings()) {
            if (value != null && Double.isFinite(value)) {
                emit.accept(value);
            }
        }
    })
    .toArray();
```

Chọn `flatMapToDouble` khi phép biến đổi tự nhiên tạo ra một `DoubleStream` và muốn kết hợp các thao tác trên Stream con. Chọn `mapMultiToDouble` khi việc duyệt collection con bằng vòng lặp hoặc nhiều nhánh điều kiện thể hiện logic rõ ràng hơn.

`mapMultiToDouble` thường phù hợp với số lượng đầu ra nhỏ cho mỗi phần tử nguồn. Nếu một phần tử có thể phát một lượng rất lớn hoặc không giới hạn giá trị, hãy cân nhắc `flatMapToDouble` với một Stream con. Không mặc định rằng một phương thức luôn nhanh hơn phương thức còn lại; hiệu năng phụ thuộc dữ liệu, mapper, JDK và các thao tác tiếp theo.

## 11. Vì sao dùng DoubleConsumer thay vì Consumer<Double>?

`Consumer<Double>` nhận object wrapper `Double`, trong khi `DoubleConsumer` nhận trực tiếp giá trị nguyên thủy `double`.

| Đặc điểm | `Consumer<Double>` | `DoubleConsumer` |
|---|---|---|
| Kiểu nhận | `Double` | `double` |
| Kiểu Stream tương ứng | `Stream<Double>` | `DoubleStream` |
| Boxing ở đầu ra | Có thể phát sinh khi chuyển `double` thành `Double` | Không cần boxing để gọi `accept(double)` |
| Phép toán số học chuyên biệt | Cần chuyển đổi hoặc unbox | Có sẵn trên `DoubleStream` |

Ví dụ dùng `Consumer<Double>`:

```java
import java.util.List;

List<String> labels = List.of("low", "high");

List<Double> scores = labels.stream()
    .<Double>mapMulti((label, emit) -> {
        if ("low".equals(label)) {
            emit.accept(0.25);
        } else {
            emit.accept(0.95);
        }
    })
    .toList();
```

Ví dụ dùng `DoubleConsumer`:

```java
import java.util.List;
import java.util.stream.DoubleStream;

List<String> labels = List.of("low", "high");

DoubleStream scores = labels.stream()
    .mapMultiToDouble((label, emit) -> {
        if ("low".equals(label)) {
            emit.accept(0.25);
        } else {
            emit.accept(0.95);
        }
    });
```

Primitive specialization có thể giảm boxing và unboxing trong pipeline. Tuy nhiên, nếu terminal operation yêu cầu `List<Double>`, bước `boxed()` sẽ tạo wrapper; nếu dữ liệu nguồn vốn là collection `Double`, việc đọc phần tử cũng có thể cần unbox. Hãy xét toàn bộ pipeline thay vì chỉ một thao tác riêng lẻ.

## 12. Chuyển từ DoubleStream sang object khi cần

Nếu các phép toán số học đã hoàn tất và bước tiếp theo cần object, có thể dùng `mapToObj` hoặc `boxed()`.

Ví dụ tạo nhãn cho từng giá trị:

Tiếp tục dùng `TemperatureSample` và danh sách `temperatures` đã khai báo ở mục 6:

```java
import java.util.List;

List<String> labels = temperatures.stream()
    .mapMultiToDouble((sample, emit) -> {
        if (Double.isFinite(sample.temperature())) {
            emit.accept(sample.temperature());
        }
    })
    .mapToObj(value -> "temperature=" + value)
    .toList();
```

Nếu chỉ cần danh sách `Double`, dùng `boxed()`:

```java
List<Double> boxedValues = temperatures.stream()
    .mapMultiToDouble((sample, emit) -> {
        if (Double.isFinite(sample.temperature())) {
            emit.accept(sample.temperature());
        }
    })
    .boxed()
    .toList();
```

Chỉ chuyển sang object khi kiểu tham chiếu cần thiết cho API hoặc mô hình dữ liệu tiếp theo. Nếu pipeline chỉ tính toán số học, giữ `DoubleStream` sẽ tránh boxing không cần thiết.

## 13. Các biến thể primitive liên quan

Stream API có ba phương thức chuyên biệt cùng mô hình:

- `mapMultiToInt` dùng `IntConsumer` và trả về `IntStream`.
- `mapMultiToLong` dùng `LongConsumer` và trả về `LongStream`.
- `mapMultiToDouble` dùng `DoubleConsumer` và trả về `DoubleStream`.

Hãy chọn kiểu theo bản chất dữ liệu:

- Dùng `int` cho số nguyên trong phạm vi 32-bit.
- Dùng `long` cho số nguyên có thể vượt giới hạn của `int`.
- Dùng `double` cho đại lượng dấu phẩy động khi độ chính xác nhị phân của kiểu này đáp ứng yêu cầu.

Không chuyển một giá trị sang `double` chỉ để dùng `mapMultiToDouble` nếu cần bảo toàn chính xác số nguyên lớn hoặc số thập phân tài chính. Với số nguyên lớn hơn miền biểu diễn chính xác của `double`, hoặc tiền tệ cần quy tắc thập phân chính xác, hãy chọn kiểu dữ liệu phù hợp như `long` theo đơn vị nhỏ nhất hoặc `BigDecimal`.

## 14. Đặc tính lazy và lưu ý khi sử dụng

`mapMultiToDouble` là thao tác trung gian. Mapper chỉ được thực thi khi terminal operation tiêu thụ pipeline, chẳng hạn `sum()`, `average()`, `toArray()`, `count()` hoặc `summaryStatistics()`.

Nếu terminal operation có khả năng dừng sớm, pipeline có thể không xử lý toàn bộ phần tử nguồn. Không dựa vào mapper để thực hiện tác dụng phụ bắt buộc phải xảy ra đúng một lần cho mọi phần tử.

Với parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Hãy phát kết quả độc lập theo từng phần tử, không cập nhật một mảng hoặc collection mutable dùng chung từ mapper. Gọi `emit.accept` ngay trong callback; không lưu `DoubleConsumer` để gọi sau khi mapper kết thúc hoặc từ một tác vụ bất đồng bộ.

Các phép cộng số thực có thể chịu ảnh hưởng của thứ tự cộng do sai số dấu phẩy động. Khi chuyển pipeline sang parallel, không giả định tổng hoặc trung bình luôn có cùng kết quả bit-for-bit với xử lý tuần tự.

## 15. Lỗi thường gặp

**Dùng Consumer<Double> khi cần DoubleConsumer.** `mapMultiToDouble` yêu cầu `DoubleConsumer`. Gọi `emit.accept(doubleValue)` với giá trị nguyên thủy.

**Nghĩ rằng mapper phải trả về double.** Mapper là `BiConsumer`, không trả về kết quả. Mỗi giá trị phải được phát qua `emit.accept`.

**Chỉ gọi accept một lần dù cần phát nhiều giá trị.** Một phần tử nguồn có thể gọi `accept` nhiều lần. Đặt lời gọi trong vòng lặp hoặc các nhánh tương ứng.

**Dùng mapMultiToDouble cho phép biến đổi một-một đơn giản.** Nếu mỗi phần tử luôn tạo đúng một số thực, `mapToDouble` thường ngắn gọn hơn.

**Dùng mapMultiToDouble khi mapper tự nhiên tạo DoubleStream.** Nếu đã có một Stream con phù hợp, `flatMapToDouble` có thể thể hiện ý định rõ hơn.

**Giả định double biểu diễn chính xác mọi số thập phân.** Kiểu `double` có sai số nhị phân; dùng `BigDecimal` khi cần độ chính xác thập phân theo quy tắc nghiệp vụ.

**Bỏ qua NaN hoặc vô cực mà không xác định quy tắc.** Hãy quyết định các giá trị đặc biệt là dữ liệu hợp lệ, cần loại bỏ hay cần xử lý riêng.

**Boxing sớm rồi unbox lại.** Tránh chuyển sang `Stream<Double>` nếu các bước tiếp theo chỉ cần phép toán trên `DoubleStream`.

**Giả định mapMultiToDouble luôn nhanh hơn flatMapToDouble.** Hãy đo trên dữ liệu và môi trường thực tế khi cần tối ưu.

## 16. Ghi nhớ

- `mapMultiToDouble` nhận mapper có kiểu `BiConsumer<? super T, ? super DoubleConsumer>`.
- `DoubleConsumer.accept(double)` phát một giá trị nguyên thủy `double` vào `DoubleStream`.
- Không gọi `accept` để phần tử nguồn không tạo kết quả; gọi nhiều lần để phát nhiều giá trị.
- Dùng `mapMultiToDouble` khi logic phát số thực bằng vòng lặp hoặc nhiều nhánh là tự nhiên và số kết quả trên mỗi phần tử ở mức nhỏ.
- Dùng `mapToDouble` cho phép biến đổi một-một; dùng `flatMapToDouble` khi mapper tự nhiên tạo một `DoubleStream`.
- `DoubleStream` hỗ trợ `sum`, `average`, `min`, `max`, `count` và `summaryStatistics`.
- `DoubleConsumer` giúp phát `double` mà không cần đóng gói mỗi giá trị thành `Double` ở đầu ra.
- Kiểm tra `NaN`, vô cực và sai số dấu phẩy động theo yêu cầu nghiệp vụ.
- Dùng `boxed()` hoặc `mapToObj` khi bước tiếp theo cần object; dùng `BigDecimal` khi cần số thập phân chính xác.

Khi dữ liệu đầu ra là số thực và mỗi phần tử nguồn có thể phát không, một hoặc nhiều giá trị, `mapMultiToDouble` kết hợp với `DoubleConsumer` tạo nên pipeline rõ ràng, tận dụng các phép toán của `DoubleStream` và hạn chế boxing không cần thiết.

