# Gatherers.windowSliding để xử lý cửa sổ trượt và dữ liệu liên tiếp

## 1. Cửa sổ trượt là gì?

Trong nhiều bài toán, một phần tử riêng lẻ chưa đủ để đưa ra quyết định. Ta cần xem một nhóm phần tử liên tiếp, tính giá trị tổng hợp của nhóm đó, rồi dịch nhóm đi một phần tử để tiếp tục phân tích.

Ví dụ, với dãy số `10, 12, 15, 13, 18` và kích thước cửa sổ là `3`, các cửa sổ trượt lần lượt là:

```text
[10, 12, 15]
     [12, 15, 13]
          [15, 13, 18]
```

Hai cửa sổ kế tiếp dùng chung hai phần tử. Mỗi lần dịch, phần tử cũ nhất bị loại bỏ và phần tử tiếp theo được thêm vào. Đây là cách tính trung bình trượt, so sánh các lần đo gần nhau, phát hiện xu hướng tăng giảm hoặc phân tích chuỗi sự kiện liên tiếp.

`Gatherers.windowSliding(int windowSize)` cung cấp thao tác này cho Stream API. Nó gom các phần tử theo encounter order thành các nhóm chồng lấn có kích thước được chỉ định.

## 2. Trạng thái API và cách sử dụng hiện nay

Stream Gatherers được giới thiệu ở Java 22 dưới dạng preview qua JEP 461, tiếp tục preview trong Java 23 qua JEP 473 và trở thành API chính thức trong Java 24 qua JEP 485. `Gatherers.windowSliding` hiện là API ổn định trong package `java.util.stream`.

Các ví dụ trong bài dùng Java 24 trở lên và không cần bật `--enable-preview`. Phần preview ở Java 22/23 chỉ là lịch sử phát triển, không phải cách cấu hình cần dùng cho dự án hiện đại.

## 3. Cú pháp cơ bản

`windowSliding` nhận một số nguyên dương là kích thước cửa sổ và trả về một `Gatherer`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class SlidingWindowExample {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(10, 12, 15, 13, 18)
                .gather(Gatherers.windowSliding(3))
                .toList();

        System.out.println(windows);
        // [[10, 12, 15], [12, 15, 13], [15, 13, 18]]
    }
}
```

`Stream.gather(...)` là intermediate operation nên kết quả vẫn là Stream. Có thể nối tiếp `map`, `filter`, `peek`, `limit`, `toList`, `forEach` hoặc các terminal operation khác.

Mỗi cửa sổ chứa các phần tử liên tiếp trong thứ tự gặp của Stream. Với Stream có encounter order như `List.stream()`, thứ tự này thường chính là thứ tự phần tử trong danh sách. Nếu dữ liệu cần phân tích theo thời gian, hãy bảo đảm nguồn đã được sắp theo thời gian trước khi tạo cửa sổ.

## 4. Cách cửa sổ dịch chuyển

Giả sử đầu vào có `N` phần tử và kích thước cửa sổ là `W`:

- Khi `N == 0`, không có cửa sổ nào được phát ra.
- Khi `0 < N < W`, chỉ có một cửa sổ chứa toàn bộ `N` phần tử.
- Khi `N >= W`, có `N - W + 1` cửa sổ, mỗi cửa sổ có đúng `W` phần tử.
- `W` phải lớn hơn hoặc bằng `1`; nếu `W < 1`, phương thức ném `IllegalArgumentException`.
- Khi `W == 1`, mỗi phần tử đầu vào tạo một cửa sổ chỉ chứa phần tử đó.

Ví dụ với tám phần tử:

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
        .gather(Gatherers.windowSliding(3))
        .toList();

// [1, 2, 3]
// [2, 3, 4]
// [3, 4, 5]
// [4, 5, 6]
// [5, 6, 7]
// [6, 7, 8]
```

Có sáu cửa sổ vì `8 - 3 + 1 = 6`. Phần tử đầu tiên chỉ xuất hiện ở cửa sổ đầu; phần tử cuối cùng chỉ xuất hiện ở cửa sổ cuối; các phần tử ở giữa có thể xuất hiện trong nhiều cửa sổ.

### 4.1. Khi Stream ngắn hơn kích thước cửa sổ

Khác với suy đoán thường gặp rằng cửa sổ chưa đủ kích thước sẽ bị bỏ qua, `windowSliding` phát ra một cửa sổ chứa tất cả phần tử nếu Stream không rỗng nhưng ngắn hơn `windowSize`:

```java
List<List<Integer>> windows = Stream.of(4, 5)
        .gather(Gatherers.windowSliding(4))
        .toList();

System.out.println(windows); // [[4, 5]]
```

Nếu Stream rỗng, kết quả là danh sách rỗng:

```java
List<List<Integer>> windows = Stream.<Integer>empty()
        .gather(Gatherers.windowSliding(4))
        .toList();

System.out.println(windows); // []
```

Điều này hữu ích khi xử lý tập dữ liệu nhỏ: chương trình vẫn có thể nhận một nhóm dữ liệu hiện có để phân tích. Tuy nhiên, nếu nghiệp vụ yêu cầu mỗi nhóm phải có đủ `W` mẫu, hãy kiểm tra `window.size() == W` trước khi tính toán.

### 4.2. Dùng với Stream vô hạn

Vì `gather` là intermediate operation, có thể nối `limit` ở downstream để chỉ lấy một số cửa sổ đầu tiên từ nguồn vô hạn:

```java
List<List<Integer>> firstWindows = Stream.iterate(1, n -> n + 1)
        .gather(Gatherers.windowSliding(3))
        .limit(4)
        .toList();

System.out.println(firstWindows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6]]
```

Với nguồn vô hạn, Gatherer phát cửa sổ đầu tiên sau khi nhận đủ ba phần tử, rồi phát thêm một cửa sổ sau mỗi phần tử mới. Không có cửa sổ ngắn ở cuối vì nguồn không kết thúc. Terminal operation `toList()` ở ví dụ chỉ nhận bốn cửa sổ nhờ `limit(4)`.

## 5. Khác biệt giữa `windowSliding` và `windowFixed`

Hai Gatherer đều gom nhiều phần tử thành một danh sách, nhưng quy tắc dịch chuyển khác nhau:

| Tiêu chí | `windowSliding(W)` | `windowFixed(W)` |
|---|---|---|
| Phần tử chung giữa hai nhóm liên tiếp | Có, tối đa `W - 1` phần tử | Không |
| Cách dịch | Mỗi lần thêm một phần tử mới | Mỗi lần gom đủ một nhóm mới |
| Số nhóm khi `N >= W` | `N - W + 1` | `ceil(N / W)` |
| Nhóm cuối | Đủ `W` phần tử khi `N >= W` | Có thể ngắn hơn `W` |
| Mục đích thường gặp | Moving average, phát hiện xu hướng, so sánh các sự kiện liền kề | Chia batch, gửi dữ liệu theo lô, xử lý trang |

Ví dụ cùng đầu vào `[1, 2, 3, 4, 5]` với kích thước `3`:

```java
var sliding = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

var fixed = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowFixed(3))
        .toList();

System.out.println(sliding); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
System.out.println(fixed);   // [[1, 2, 3], [4, 5]]
```

Chọn `windowSliding` khi cần so sánh các nhóm liền kề có phần tử chồng lấn. Chọn `windowFixed` khi cần chia dữ liệu thành các lô độc lập.

## 6. Tính trung bình trượt của dữ liệu đo

Một trường hợp phổ biến là tính trung bình của ba lần đo gần nhất để giảm ảnh hưởng của dao động tức thời.

```java
import java.time.Instant;
import java.util.List;
import java.util.stream.Gatherers;

record Measurement(Instant time, double temperature) {}

public class MovingAverageExample {
    public static void main(String[] args) {
        List<Measurement> measurements = List.of(
                new Measurement(Instant.parse("2026-01-01T00:00:00Z"), 20.0),
                new Measurement(Instant.parse("2026-01-01T00:01:00Z"), 21.0),
                new Measurement(Instant.parse("2026-01-01T00:02:00Z"), 23.0),
                new Measurement(Instant.parse("2026-01-01T00:03:00Z"), 22.0),
                new Measurement(Instant.parse("2026-01-01T00:04:00Z"), 24.0)
        );

        List<Double> averages = measurements.stream()
                .gather(Gatherers.windowSliding(3))
                .map(window -> window.stream()
                        .mapToDouble(Measurement::temperature)
                        .average()
                        .orElseThrow())
                .toList();

        System.out.println(averages); // [21.333..., 22.0, 23.0]
    }
}
```

Kết quả được tính theo ba nhóm:

| Cửa sổ | Nhiệt độ | Trung bình |
|---|---|---:|
| 1 | 20, 21, 23 | 21,33 |
| 2 | 21, 23, 22 | 22,00 |
| 3 | 23, 22, 24 | 23,00 |

Đoạn mã giả định `measurements` đã ở đúng thứ tự thời gian. `windowSliding(3)` chỉ dựa vào encounter order; nó không tự đọc trường `time`, không sắp xếp timestamp và cũng không bảo đảm khoảng cách thời gian giữa hai mẫu bằng nhau.

## 7. Phát hiện dữ liệu liên tiếp tăng hoặc giảm

Vì mỗi cửa sổ chứa các phần tử kề nhau, có thể kiểm tra quy luật trên một chuỗi ngắn. Ví dụ, tìm ba lần đo liên tiếp có giá trị tăng nghiêm ngặt:

```java
record Reading(int sequence, double value) {}

static boolean hasThreeIncreasingValues(List<Reading> readings) {
    return readings.stream()
            .gather(Gatherers.windowSliding(3))
            .anyMatch(window ->
                    window.get(0).value() < window.get(1).value()
                    && window.get(1).value() < window.get(2).value());
}
```

`anyMatch` là terminal operation có short-circuit. Khi một cửa sổ thỏa điều kiện, Stream có thể dừng xử lý phần tử tiếp theo. Không cần tạo trước danh sách toàn bộ cửa sổ nếu chỉ cần biết có tồn tại một chuỗi phù hợp hay không.

Có thể dùng cùng cách để tìm ba lần đo giảm liên tiếp, hai trạng thái liên tiếp không hợp lệ hoặc một mẫu giao dịch đáng chú ý. Điều kiện bên trong `anyMatch` quyết định ý nghĩa nghiệp vụ; Gatherer chỉ tạo các nhóm liên tiếp.

## 8. Phân tích cặp sự kiện liền kề

Với `windowSize = 2`, mỗi cửa sổ biểu diễn một cặp sự kiện liền kề. Cách này phù hợp để tạo các chuyển trạng thái hoặc đo khoảng cách giữa các sự kiện:

```java
import java.time.Instant;
import java.time.Duration;
import java.util.List;

record Event(String name, Instant time) {}

static List<String> transitions(List<Event> events) {
    return events.stream()
            .gather(Gatherers.windowSliding(2))
            .map(pair -> pair.get(0).name() + " -> " + pair.get(1).name())
            .toList();
}

static List<Duration> gaps(List<Event> events) {
    return events.stream()
            .gather(Gatherers.windowSliding(2))
            .map(pair -> Duration.between(pair.get(0).time(), pair.get(1).time()))
            .toList();
}
```

Với các sự kiện `CREATED`, `PAID`, `SHIPPED`, kết quả chuyển trạng thái là `CREATED -> PAID` và `PAID -> SHIPPED`. Khi tính khoảng cách thời gian, dữ liệu đầu vào phải được sắp theo timestamp và cần quyết định cách xử lý timestamp trùng hoặc đi ngược.

## 9. Cửa sổ theo số lượng phần tử không phải cửa sổ theo thời gian

`windowSliding(W)` xác định cửa sổ bằng **số phần tử**, không phải khoảng thời gian. Ví dụ, với `windowSliding(5)`, mỗi cửa sổ chứa tối đa năm bản ghi liên tiếp dù năm bản ghi đó trải dài một giây hay một ngày.

Nếu yêu cầu là “trung bình trong 10 phút gần nhất” hoặc “gom tất cả sự kiện trong mỗi giờ”, chỉ dùng `windowSliding` là chưa đủ. Cần xác định thêm:

- Timestamp nào được dùng: thời gian sự kiện (*event time*) hay thời gian nhận dữ liệu (*processing time*).
- Cách xử lý dữ liệu đến trễ và timestamp không theo thứ tự.
- Cửa sổ có dịch từng giây, từng phút hay theo mỗi sự kiện mới.
- Cách xử lý phần tử nằm đúng ranh giới và khoảng thời gian không có dữ liệu.

Với dữ liệu hữu hạn đã sắp thời gian, có thể lọc theo một mốc thời gian rồi dùng Gatherer cho nhóm mẫu có số lượng cố định. Với luồng sự kiện liên tục, cửa sổ theo thời gian, watermark hoặc dữ liệu đến trễ cần logic chuyên biệt; hãy dùng một stream-processing framework hoặc tự triển khai Gatherer phù hợp với hợp đồng thời gian đó.

## 10. Encounter order, tính bất biến và chi phí bộ nhớ

`windowSliding` tạo các nhóm theo encounter order. Vì vậy, tính “liên tiếp” chỉ có ý nghĩa khi thứ tự nguồn dữ liệu có ý nghĩa. Không nên gọi `unordered()` trước Gatherer nếu kết quả phụ thuộc vào phần tử trước và sau.

Mỗi danh sách cửa sổ được phát ra là *unmodifiable*. Các thao tác sửa như `add`, `remove`, `set` sẽ ném `UnsupportedOperationException`:

```java
var firstWindow = Stream.of(1, 2, 3, 4)
        .gather(Gatherers.windowSliding(3))
        .findFirst()
        .orElseThrow();

// firstWindow.add(99); // UnsupportedOperationException

var editableCopy = new java.util.ArrayList<>(firstWindow);
editableCopy.add(99); // Có thể sửa bản sao.
```

Unmodifiable chỉ áp dụng cho cấu trúc danh sách cửa sổ, không biến các đối tượng bên trong thành immutable. Nếu cửa sổ chứa object mutable, các object đó vẫn có thể bị thay đổi qua tham chiếu khác. Danh sách cửa sổ cũng không bảo đảm một implementation type hoặc khả năng serialization cụ thể.

Javadoc lưu ý các cửa sổ có thể được cấp phát liền kề và sớm để tăng hiệu quả. Do đó, `windowSize` lớn có thể dùng nhiều bộ nhớ trong lúc đánh giá. Nếu sau đó gọi `toList()` để giữ tất cả cửa sổ, ứng dụng còn giữ lại toàn bộ kết quả; với dữ liệu lớn, hãy cân nhắc xử lý từng cửa sổ bằng `map` rồi tổng hợp hoặc dùng terminal operation phù hợp thay vì lưu mọi danh sách.

Ví dụ chỉ giữ lại trung bình của mỗi cửa sổ:

```java
List<Double> averages = values.stream()
        .gather(Gatherers.windowSliding(100))
        .map(window -> window.stream()
                .mapToDouble(Integer::doubleValue)
                .average()
                .orElseThrow())
        .toList();
```

Kết quả chỉ lưu một số thực cho mỗi cửa sổ, thay vì giữ toàn bộ danh sách các cửa sổ trong kết quả cuối.

## 11. Giới hạn và trường hợp nên dùng Gatherer khác

`windowSliding` phù hợp khi mọi cửa sổ có cùng kích thước và mỗi cửa sổ mới dịch đúng một phần tử. Hãy cân nhắc giải pháp khác nếu nghiệp vụ yêu cầu:

- Cửa sổ không chồng lấn: dùng `Gatherers.windowFixed`.
- Bước dịch chuyển lớn hơn một phần tử: tự viết Gatherer hoặc lọc các cửa sổ theo chỉ số sau khi tạo, tùy chi phí và ý nghĩa dữ liệu.
- Kích thước cửa sổ thay đổi theo dữ liệu: tự viết Gatherer có state.
- Cửa sổ theo thời gian hoặc theo điều kiện kết thúc: tự xây dựng logic stateful có xét timestamp/điều kiện, hoặc dùng framework xử lý luồng chuyên dụng.
- Chỉ cần so sánh hai phần tử kế tiếp: `windowSliding(2)` là lựa chọn ngắn gọn; nếu chỉ cần ánh xạ từng phần tử độc lập, `map` vẫn phù hợp hơn.

Ngoài ra, `windowSize` phải lớn hơn 0. Kiểm tra tham số trước khi tạo pipeline nếu kích thước đến từ cấu hình hoặc người dùng:

```java
static <T> List<List<T>> slidingWindows(List<T> input, int windowSize) {
    if (windowSize < 1) {
        throw new IllegalArgumentException("windowSize phải lớn hơn 0");
    }

    return input.stream()
            .gather(Gatherers.windowSliding(windowSize))
            .toList();
}
```

## 12. Tài liệu tham khảo

- [Java SE 26 API: Gatherers.windowSliding](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherers.html#windowSliding(int)) — quy tắc cửa sổ, trường hợp Stream rỗng/ngắn, kích thước hợp lệ và tính unmodifiable của từng danh sách.
- [Java SE 26 API: Stream.gather](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)) — vị trí của Gatherer trong Stream pipeline.
- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — trạng thái hoàn thiện API trong Java 24.
- [JEP 461: Stream Gatherers (Preview)](https://openjdk.org/jeps/461) — lịch sử giới thiệu tính năng ở Java 22.
