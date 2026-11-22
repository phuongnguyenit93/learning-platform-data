# Đọc các phép đo COUNT, TOTAL_TIME, MAX và VALUE đúng ngữ cảnh

## 1. Một con số cần đi cùng ngữ cảnh đo

Khi mở `/actuator/metrics/...`, bạn thường gặp các cặp như `COUNT=3`, `TOTAL_TIME=1.3`, `MAX=0.9` hoặc `VALUE=7`. Chúng là những thống kê (statistic) mô tả các khía cạnh khác nhau của một công cụ đo. Chỉ đọc số rồi gắn ngay ý nghĩa “số request”, “mili giây” hay “giá trị hiện tại” có thể dẫn tới kết luận sai.

Để diễn giải một phép đo, cần ghép **tên metric → loại meter → tập tags → statistic → đơn vị → phạm vi thời gian và nguồn registry**. Ví dụ, `COUNT` của bộ đếm số mặt hàng khác `COUNT` của timer xử lý yêu cầu; `MAX` của timer đo thời lượng, còn `MAX` của một phép thống kê kích thước có thể đo byte.

Bài dùng Micrometer **1.13.0** và API Actuator **Spring Boot 3.3.0** để kiểm chứng cơ chế bằng Java 17+. Các quy tắc đọc luôn cần đối chiếu với loại meter và cách registry thực tế lưu/xuất dữ liệu; không lấy một thí nghiệm với kho tích lũy làm kết luận cho mọi hệ thống giám sát.

| Statistic | Ngữ cảnh thường gặp | Ý nghĩa phải xác minh | Cách hiểu dễ sai |
| --- | --- | --- | --- |
| `COUNT` | `Counter`, `Timer`, `DistributionSummary` | Lượng đã được đếm hoặc số mẫu đã ghi, theo cơ chế registry | Luôn là số request mỗi giây |
| `TOTAL_TIME` | `Timer` | Tổng thời lượng của các mẫu được ghi trong phạm vi báo cáo | Thời lượng trung bình, thời gian chạy ứng dụng hoặc thời gian CPU |
| `MAX` | Timer, thống kê phân phối | Giá trị lớn nhất theo cơ chế lưu thống kê, thường có cửa sổ thời gian | Đỉnh cao nhất từ lúc khởi động hoặc p99 |
| `VALUE` | `Gauge` | Giá trị mà hàm quan sát trả về tại lần đọc/lấy mẫu | Tổng số sự kiện đã xảy ra hoặc mọi giá trị giữa hai lần đọc |

Không phải meter nào cũng có cả bốn statistic. Một counter thường chỉ có `COUNT`; một timer cung cấp `COUNT`, `TOTAL_TIME`, `MAX`; một gauge thường có `VALUE`. Các loại khác có thể thêm thống kê khác. Không điền 0 cho trường không có rồi coi đó là phép đo thực sự.

## 2. COUNT: đang đếm lượng gì?

### 2.1. Counter đếm lượng tăng được ghi nhận

Với `Counter`, `COUNT` phản ánh lượng được tăng qua API counter theo cách registry cung cấp. Gọi `increment(2)` rồi `increment(3)` cho lượng đếm 5 trong một registry tích lũy, mặc dù chỉ có hai lần gọi Java.

```java
Counter processed = Counter.builder("demo.items.processed")
    .baseUnit("items")
    .register(registry);

processed.increment(2);
processed.increment(3);
// Với SimpleMeterRegistry mặc định: count() bằng 5.0.
```

Đây là đoạn minh họa trong phương thức đã có biến `registry`. Tên và đơn vị nói rằng đang đếm **mặt hàng**, không phải số lần gọi `increment()`. Counter cũng không nên được dùng để biểu diễn một giá trị tăng rồi giảm như số công việc đang chờ; trạng thái đó phù hợp với gauge. [Counter trong Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

### 2.2. Timer đếm số mẫu thời lượng đã ghi

Với `Timer`, `COUNT` là số mẫu được ghi vào timer, không phải tổng số mili giây. Ghi ba mẫu 100 ms, 300 ms và 900 ms tạo `COUNT=3`, không phải 1.300.

Trong một phép đo HTTP thông thường, số mẫu thường gắn với các yêu cầu đã đi đến điểm kết thúc được quan sát. Yêu cầu đang chạy chưa hoàn tất có thể chưa nằm trong count của timer đó. Muốn quan sát công việc đang chạy, cần meter/cơ chế phù hợp như `LongTaskTimer`, thay vì tự xem `Timer.COUNT` là số tác vụ đang hoạt động.

Count còn phụ thuộc điều kiện ghi: timer có tính cả kết thúc bằng lỗi không, có chỉ đo một nhánh nghiệp vụ không, có ghi hai lần không? Hai timer tên khác nhau không mặc nhiên đo cùng tập sự kiện.

### 2.3. COUNT không tự có đơn vị “mỗi giây”

Với số đếm tích lũy của cùng một chuỗi dữ liệu, có thể ước lượng tốc độ trên một khoảng:

```text
tốc độ trung bình = (COUNT tại t1 - COUNT tại t0) / (t1 - t0)
```

Ví dụ count tăng từ 100 lên 120 trong 10 giây cho tốc độ trung bình 2 sự kiện/giây, nếu mỗi đơn vị tăng thật sự tương ứng một sự kiện và không có lần khởi động lại/đổi nguồn dữ liệu. Một ảnh chụp `COUNT=120` duy nhất không đủ để suy ra 120 sự kiện/giây.

Không áp dụng phép trừ này máy móc cho registry báo cáo theo từng khoảng (step) hoặc cho dữ liệu đã được hệ thống giám sát chuyển thành tốc độ. Cần biết giá trị đang đọc là tích lũy, giá trị theo khoảng, hay kết quả một truy vấn đã biến đổi. Nếu tiến trình khởi động lại và số đếm về thấp hơn, hiệu âm không có nghĩa có “lưu lượng âm”.

## 3. TOTAL_TIME: tổng thời lượng của các mẫu

### 3.1. Đơn vị phải đọc từ nguồn thực tế

Timer có API ghi và đọc với đơn vị tường minh, chẳng hạn `record(100, TimeUnit.MILLISECONDS)` và `totalTime(TimeUnit.SECONDS)`. Khi đi qua `measure()`, thời lượng được đưa ra theo đơn vị thời gian cơ sở của registry.

Trong `SimpleMeterRegistry` của ví dụ, đơn vị này là giây. Vì vậy ba mẫu 100 ms, 300 ms và 900 ms được đọc thành:

```text
COUNT      = 3
TOTAL_TIME = 1.3 seconds
MAX        = 0.9 seconds  (trước khi mẫu cực đại hết cửa sổ)
```

Không phải vì đầu vào ghi bằng mili giây mà JSON luôn trả mili giây. Ngược lại, không được áp đặt giây cho mọi API/exporter: hãy đọc `baseUnit` hoặc chỉ rõ `TimeUnit` khi dùng Java. [API Timer và đơn vị cơ sở](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Timer.java), [đơn vị của SimpleMeterRegistry 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/simple/SimpleMeterRegistry.java).

`baseUnit="seconds"` ở cấp metric không biến `COUNT=3` thành 3 giây. Nó diễn giải các thống kê thời lượng của timer như `TOTAL_TIME` và `MAX`; `COUNT` vẫn là số mẫu.

### 3.2. Trung bình là tổng chia số mẫu, khi hai vế cùng phạm vi

```text
thời lượng trung bình = TOTAL_TIME / COUNT
                      = 1.3 / 3 seconds
                      ≈ 0.433333 seconds
                      ≈ 433.333 milliseconds
```

Phép chia hợp lệ khi tổng thời lượng và số mẫu thuộc cùng timer hoặc cùng tập meter được tổng hợp tương thích, cùng nguồn dữ liệu và cùng phạm vi báo cáo. Với `COUNT=0`, không có mẫu để suy ra độ trễ trung bình; đừng kết luận tác vụ mất 0 ms chỉ vì thư viện hoặc biểu đồ biểu diễn một giá trị mặc định.

Timer đã có count nên không cần thêm counter chỉ để đếm lại đúng cùng các lần được timer ghi. Nếu vẫn có counter nghiệp vụ riêng, phải nêu rõ ranh giới sự kiện khác nhau để tránh đếm lặp hoặc so sánh hai tập mẫu khác nhau.

### 3.3. Tổng thời lượng không phải thời gian trôi qua trên đồng hồ

Hai yêu cầu chạy đồng thời, mỗi yêu cầu mất 1 giây, có thể làm `TOTAL_TIME` tăng 2 giây dù chỉ khoảng 1 giây thực tế trôi qua. Tổng thời lượng cộng độ dài từng mẫu, không tính độ dài hợp của các khoảng chúng chạy.

Nó cũng không tự là thời gian CPU. Nếu thao tác được đo bao gồm chờ mạng hoặc chờ cơ sở dữ liệu, thời lượng có thể chứa cả thời gian chờ. Và nếu timer được ghi bằng một thời lượng có sẵn, ý nghĩa dữ liệu phụ thuộc chính giá trị nguồn đã ghi.

### 3.4. Trung bình toàn bộ lịch sử khác trung bình trong khoảng đang điều tra

Với timer tích lũy, giả sử đọc cùng một chuỗi tại hai thời điểm cách nhau 10 giây:

| Thời điểm | COUNT | TOTAL_TIME |
| --- | --- | --- |
| t0 | 100 | 20 giây |
| t1 | 120 | 26 giây |

Trong khoảng t0→t1 có thêm 20 mẫu với tổng thời lượng 6 giây, nên thời lượng trung bình của **các mẫu mới** là 300 ms. Trong khi đó `26 / 120 ≈ 216.667 ms` là trung bình của toàn bộ 120 mẫu đang được tích lũy. Hai câu trả lời khác nhau vì phạm vi khác nhau, không phải dữ liệu tự mâu thuẫn.

Các phép lấy hiệu cần cùng nhãn, cùng instance, cùng đơn vị, không bị reset và phù hợp cơ chế xuất dữ liệu. Khi có nhiều instance, hệ thống giám sát cần xử lý các chuỗi và các lần reset đúng cách; không lấy hai lần gọi qua bộ cân bằng tải rồi giả định đó là hai ảnh chụp của cùng tiến trình.

## 4. MAX: cực đại nào, trong khoảng nào?

### 4.1. Cực đại của timer thường là cực đại theo cửa sổ

Trong các timer cơ bản như `CumulativeTimer` và `StepTimer`, Micrometer dùng cực đại theo cửa sổ thời gian (`TimeWindowMax`). Giá trị lớn nhất cũ sẽ hết hiệu lực sau các vòng lưu thống kê. Nếu không có mẫu mới trong đủ thời gian, max có thể trở về 0.

Cấu hình liên quan gồm `expiry` và `bufferLength`; thời gian để dữ liệu hết hạn hoàn toàn gắn với tích của chúng. Đó là cơ chế các vùng lưu luân phiên, không nên mặc định mọi lần đọc là cực đại của một khoảng trượt chính xác do bạn tự chọn. [Cửa sổ MAX trong tài liệu Timer](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

Ví dụ trong chương trình bên dưới đặt thời gian hết hạn mỗi vùng là 10 giây và số vùng là 2. Sau khi dịch đồng hồ thêm 21 giây mà không ghi mẫu mới, max 900 ms đã hết hiệu lực. Tuy nhiên, count và tổng thời lượng của timer tích lũy vẫn còn:

```text
COUNT      = 3
TOTAL_TIME = 1.3 seconds
MAX        = 0.0 seconds
```

**Không diễn giải kết quả này là ba thao tác đã mất 0 ms.** COUNT/TOTAL_TIME đang giữ dữ liệu tích lũy, trong khi MAX đã hết cửa sổ. Vì phạm vi thời gian khác nhau, trung bình tính từ tổng tích lũy thậm chí có thể lớn hơn MAX hiện tại. Không áp dụng bất đẳng thức “trung bình luôn ≤ max” khi hai vế không cùng tập mẫu.

### 4.2. MAX không phải percentile

`MAX=0.9 seconds` không có nghĩa 99% yêu cầu mất không quá 0,9 giây. Nó chỉ nói về cực đại theo cơ chế/cửa sổ đang đọc. Muốn kết luận về p95/p99, cần dữ liệu phân phối và cấu hình/truy vấn thích hợp.

Chỉ có COUNT, TOTAL_TIME và MAX không đủ tái tạo phân phối thời lượng: nhiều tập mẫu khác nhau có thể có cùng số lượng, cùng tổng và cùng cực đại nhưng percentile khác nhau. Cũng không lấy MAX trừ trung bình để suy ra số lượng yêu cầu chậm.

### 4.3. MAX không phải lúc nào cũng đo thời gian

`DistributionSummary` có thể cung cấp `COUNT`, `TOTAL`, `MAX` cho độ lớn các mẫu, chẳng hạn kích thước thông điệp. Khi đơn vị là byte, MAX là kích thước lớn nhất theo cơ chế thống kê tương ứng, không phải số giây. Hãy phân biệt `TOTAL` của độ lớn với `TOTAL_TIME` của thời lượng.

## 5. VALUE: giá trị được quan sát tại lần đọc

Gauge gọi một hàm để lấy giá trị của trạng thái đang được theo dõi. Chẳng hạn `demo.queue.depth` đọc số công việc đang chờ và dùng đơn vị `items`:

```java
AtomicInteger queued = new AtomicInteger(7);
Gauge queue = Gauge.builder("demo.queue.depth", queued,
        AtomicInteger::doubleValue)
    .baseUnit("items")
    .register(registry);

queued.set(99);
queued.set(2);
// Lần đọc sau hai thay đổi này quan sát VALUE=2, không phải 7+99+2.
```

Đây là đoạn minh họa trong thành phần có `registry` và giữ tham chiếu tới `queued`. Một lần đọc sau cùng không cho biết có bao nhiêu công việc đã vào/ra hàng đợi, và cũng không cho biết đã có lúc hàng đợi đạt 99 nếu không ai lấy mẫu tại thời điểm đó.

Gauge phản ánh trạng thái hiện tại theo hàm đo, không lưu mọi biến động trung gian. Muốn biết lưu lượng vào/ra có thể cần counter riêng; muốn quan sát các đỉnh rất ngắn cần chọn cơ chế đo/lấy mẫu phù hợp. Tăng tần suất truy vấn không biến gauge thành một nhật ký đầy đủ.

Đơn vị của VALUE phụ thuộc metric: độ sâu hàng đợi là số phần tử, bộ nhớ có thể là byte, một tỉ lệ có thể không có đơn vị. `VALUE=0.75` chỉ được trình bày là 75% khi hợp đồng metric thực sự là tỉ lệ 0..1. Không nhân 100 cho mọi gauge.

Với gauge theo dõi đối tượng bằng tham chiếu yếu, ứng dụng cần giữ tham chiếu mạnh tới đối tượng trạng thái; nếu đối tượng bị thu gom, có thể thấy NaN hoặc không còn dữ liệu tùy registry. “Không có phép đo”, NaN và giá trị 0 là ba trường hợp cần phân biệt. [Cách lấy mẫu và vòng đời trạng thái của Gauge](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

## 6. Đọc phản hồi metrics của Actuator

### 6.1. Đọc tên, đơn vị và từng statistic

Trong một ứng dụng web Boot đã có các meter tương ứng, phản hồi có thể có cấu trúc như ví dụ sau. Đây là JSON minh họa cho một timer đã lọc theo kết quả thành công; chương trình độc lập ở mục sau gọi trực tiếp API endpoint, không mở HTTP server:

```json
{
  "name": "demo.operation",
  "baseUnit": "seconds",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3
    },
    {
      "statistic": "TOTAL_TIME",
      "value": 1.3
    },
    {
      "statistic": "MAX",
      "value": 0.9
    }
  ],
  "availableTags": []
}
```

Đọc thành câu: “Trong phạm vi dữ liệu của timer `demo.operation` và bộ lọc hiện tại có 3 mẫu, tổng thời lượng 1,3 giây; cực đại đang còn hiệu lực là 0,9 giây.” Không đọc thành “3 request/giây, độ trễ 1,3 ms, p99 bằng 0,9 ms”.

Trường `description` có thể xuất hiện nếu meter có mô tả. Thứ tự phần tử trong `measurements` không phải lý do để gắn ý nghĩa theo vị trí: hãy đọc khóa `statistic`. `availableTags` giúp biết các chiều còn có thể lọc; nó không phải số lượng sự kiện hay phân phối dữ liệu.

### 6.2. Cùng tên chưa chắc là một meter

Cùng tên `demo.operation` có thể có nhiều meter: `result=success`, `result=failure`, hoặc các phương thức/đường dẫn khác. Trong Boot 3.3.0, endpoint lấy các meter phù hợp rồi gộp phép đo theo statistic: **MAX lấy giá trị lớn nhất; các statistic khác được cộng**. [Triển khai MetricsEndpoint 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java).

Giả sử có hai timer cùng tên, cùng đơn vị nhưng tags kết quả khác nhau:

| Nhóm | COUNT | TOTAL_TIME | MAX đang còn hiệu lực |
| --- | --- | --- | --- |
| `result=success` | 3 | 1,3 giây | 0,9 giây |
| `result=failure` | 1 | 2,0 giây | 2,0 giây |
| Không lọc kết quả | 4 | 3,3 giây | 2,0 giây |

COUNT và TOTAL_TIME được cộng vì đây là các nhóm mẫu tách biệt và tương thích trong ví dụ. MAX là 2,0, không phải 0,9 + 2,0 = 2,9 giây.

Trung bình chung là `3,3 / 4 = 0,825 giây`. Không lấy trung bình đơn giản của hai giá trị trung bình nhóm `(1,3/3 + 2,0/1)/2`, vì hai nhóm có số mẫu khác nhau. Cách gộp đúng dùng tổng thời lượng và tổng số mẫu, tương đương trung bình có trọng số theo số mẫu.

Với gauge, việc endpoint cộng VALUE không bảo đảm tổng đó có ý nghĩa nghiệp vụ. Tổng số phần tử của các hàng đợi tách biệt có thể có ích; tổng các tỉ lệ có mẫu số/quy mô khác nhau thường không thể đọc thành tỉ lệ chung. Quy tắc gộp của endpoint không thay cho việc hiểu đơn vị và tính cộng được của dữ liệu.

### 6.3. Lọc tags để xác định đúng phạm vi

Trong ứng dụng Boot web, liệt kê tên metric bằng `GET /actuator/metrics`, rồi dùng tên Micrometer chính xác. Nếu đã đăng ký `demo.operation` như ví dụ và đã cho phép endpoint qua HTTP:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/demo.operation --data-urlencode "tag=result:success"
```

Có thể lặp tham số `tag` để thu hẹp nhiều chiều. Ví dụ với metric HTTP đã được ứng dụng ghi nhận:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/http.server.requests --data-urlencode "tag=method:GET" --data-urlencode "tag=status:200"
```

Các tag được dùng đồng thời để lọc, không phải lấy hợp hai nhóm độc lập. Phải xác minh tên metric và giá trị tags thực tế; không giả định dữ liệu luôn có sẵn trước khi một yêu cầu tương ứng được ghi nhận. [API metrics và tham số tag của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Nếu endpoint chưa được đưa ra HTTP, cấu hình liên quan trong một ứng dụng Boot là `management.endpoints.web.exposure.include=health,metrics`; quyền truy cập vẫn theo cấu hình bảo mật của ứng dụng. Trên PowerShell có alias `curl`, dùng `curl.exe`. Các lệnh HTTP này không áp dụng trực tiếp cho chương trình độc lập không mở cổng bên dưới.

Kết quả đọc endpoint có thể chỉ thuộc một instance mà yêu cầu được chuyển tới. Nó không tự là tổng của toàn bộ hệ thống nhiều instance. Việc một trường hiện có trong JSON cũng không chứng minh dữ liệu đã được xuất và lưu lịch sử ở một hệ thống giám sát.

Các thống kê đang cập nhật không nhất thiết được chụp nguyên tử tại đúng cùng một thời điểm. Khi có tải đồng thời, hãy coi đây là dữ liệu quan sát vận hành, tránh dùng một lần đọc làm bảng đối soát giao dịch yêu cầu tính chính xác tuyệt đối.

## 7. Chương trình kiểm chứng bằng Java 17+

Chương trình tạo counter, hai timer, một gauge và gọi trực tiếp `MetricsEndpoint`. Đồng hồ được điều khiển bằng mã để kiểm tra MAX hết cửa sổ mà không phải `Thread.sleep()` hoặc phụ thuộc tốc độ máy. Các thời lượng là dữ liệu thí nghiệm được ghi rõ, không phải kết quả đo hiệu năng thật.

Tạo dự án Gradle có wrapper và JDK 17 khả dụng:

```text
measurement-context-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/MeasurementContextDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'measurement-context-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
    implementation 'org.springframework.boot:spring-boot-actuator:3.3.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'MeasurementContextDemo'
}
```

Hai phiên bản được cố định để tái hiện API đã kiểm chứng, không phải chỉ dẫn chọn bản vá triển khai. Dự án Boot hiện có nên dùng cơ chế quản lý phụ thuộc của Boot thay vì tự nâng/hạ Micrometer riêng lẻ.

`src/main/java/MeasurementContextDemo.java`:

```java
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.boot.actuate.metrics.MetricsEndpoint;

public class MeasurementContextDemo {

    public static void main(String[] args) {
        ManualClock clock = new ManualClock();
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        AtomicInteger queued = new AtomicInteger(7);

        try {
            Counter items = Counter.builder("demo.items.processed")
                .baseUnit("items")
                .register(registry);
            items.increment(2);
            items.increment(3);
            printMeter("counter", items);

            Timer success = operationTimer(registry, "success");
            Timer failure = operationTimer(registry, "failure");
            success.record(100, TimeUnit.MILLISECONDS);
            success.record(300, TimeUnit.MILLISECONDS);
            success.record(900, TimeUnit.MILLISECONDS);
            failure.record(2000, TimeUnit.MILLISECONDS);

            printMeter("timer.success", success);
            System.out.printf(Locale.ROOT, "timer.success.meanMs=%.3f%n",
                success.mean(TimeUnit.MILLISECONDS));

            Gauge queue = Gauge.builder("demo.queue.depth", queued,
                    AtomicInteger::doubleValue)
                .baseUnit("items")
                .register(registry);
            printMeter("gauge.before", queue);
            queued.set(99);
            queued.set(2);
            printMeter("gauge.after", queue);

            MetricsEndpoint endpoint = new MetricsEndpoint(registry);
            printMetric("endpoint.all",
                endpoint.metric("demo.operation", null));
            printMetric("endpoint.success",
                endpoint.metric("demo.operation", List.of("result:success")));

            clock.advance(Duration.ofSeconds(21));
            printMeter("timer.afterIdle", success);

            success.record(500, TimeUnit.MILLISECONDS);
            printMeter("timer.afterNewSample", success);
        }
        finally {
            java.lang.ref.Reference.reachabilityFence(queued);
            registry.close();
        }
    }

    private static Timer operationTimer(SimpleMeterRegistry registry,
            String result) {
        return Timer.builder("demo.operation")
            .tag("result", result)
            .distributionStatisticExpiry(Duration.ofSeconds(10))
            .distributionStatisticBufferLength(2)
            .register(registry);
    }

    private static void printMeter(String label, Meter meter) {
        System.out.println(label + ".unit=" + meter.getId().getBaseUnit());
        for (var sample : meter.measure()) {
            System.out.printf(Locale.ROOT, "%s.%s=%.3f%n",
                label, sample.getStatistic(), sample.getValue());
        }
    }

    private static void printMetric(String label,
            MetricsEndpoint.MetricDescriptor metric) {
        if (metric == null) {
            throw new IllegalStateException("Expected metric");
        }
        System.out.println(label + ".unit=" + metric.getBaseUnit());
        for (var sample : metric.getMeasurements()) {
            System.out.printf(Locale.ROOT, "%s.%s=%.3f%n",
                label, sample.getStatistic(), sample.getValue());
        }
    }

    private static final class ManualClock implements Clock {
        private long milliseconds = 1000;

        @Override
        public long wallTime() {
            return milliseconds;
        }

        @Override
        public long monotonicTime() {
            return TimeUnit.MILLISECONDS.toNanos(milliseconds);
        }

        void advance(Duration duration) {
            milliseconds += duration.toMillis();
        }
    }
}
```

Chạy tại thư mục dự án:

```bash
./gradlew -q run --console=plain
```

Trên Windows PowerShell dùng `.\gradlew.bat -q run --console=plain`. Gradle giải quyết phụ thuộc, biên dịch và chạy `main`. Nếu chạy trực tiếp bằng `javac`/`java`, phải đưa toàn bộ JAR phụ thuộc đã giải quyết vào classpath ở cả hai bước; tệp Java này không chỉ dùng thư viện chuẩn JDK.

Đầu ra của chương trình:

```text
counter.unit=items
counter.COUNT=5.000
timer.success.unit=seconds
timer.success.COUNT=3.000
timer.success.TOTAL_TIME=1.300
timer.success.MAX=0.900
timer.success.meanMs=433.333
gauge.before.unit=items
gauge.before.VALUE=7.000
gauge.after.unit=items
gauge.after.VALUE=2.000
endpoint.all.unit=seconds
endpoint.all.COUNT=4.000
endpoint.all.TOTAL_TIME=3.300
endpoint.all.MAX=2.000
endpoint.success.unit=seconds
endpoint.success.COUNT=3.000
endpoint.success.TOTAL_TIME=1.300
endpoint.success.MAX=0.900
timer.afterIdle.unit=seconds
timer.afterIdle.COUNT=3.000
timer.afterIdle.TOTAL_TIME=1.300
timer.afterIdle.MAX=0.000
timer.afterNewSample.unit=seconds
timer.afterNewSample.COUNT=4.000
timer.afterNewSample.TOTAL_TIME=1.800
timer.afterNewSample.MAX=0.500
```

### 7.1. Đọc kết quả theo từng thí nghiệm

- **Counter:** hai lần tăng 2 và 3 cho COUNT bằng 5 mặt hàng, không phải 2 lần gọi.
- **Timer thành công:** ba mẫu cho COUNT bằng 3; tổng 1,3 giây, max hiện tại 0,9 giây; trung bình xấp xỉ 433,333 ms.
- **Gauge:** đọc được 7 rồi 2; trạng thái trung gian 99 không được gauge giữ lại để kể lại ở lần đọc sau.
- **Endpoint không lọc:** gộp hai nhóm thành COUNT bằng 4, tổng 3,3 giây và max bằng 2 giây.
- **Endpoint lọc thành công:** chỉ còn ba mẫu của nhóm thành công.
- **Sau 21 giây không có mẫu mới:** COUNT/TOTAL_TIME tích lũy vẫn là 3/1,3, nhưng MAX đã về 0.
- **Sau mẫu mới 500 ms:** COUNT thành 4 và tổng thành 1,8 giây; MAX thành 0,5 giây, không khôi phục đỉnh 0,9 giây đã hết cửa sổ.

`ManualClock` chỉ phục vụ thí nghiệm đơn luồng và cung cấp thời gian cho registry. Lệnh `clock.advance(...)` không làm tiến trình thực sự chờ 21 giây. Trong ứng dụng chạy thật, registry dùng đồng hồ phù hợp do hạ tầng quản lý.

`Reference.reachabilityFence(queued)` giữ đối tượng trạng thái gauge còn sống tới cuối vùng thí nghiệm. Registry được đóng trong `finally` vì chương trình tự tạo và sở hữu nó; một service trong Spring không tự đóng registry dùng chung được tiêm vào.

## 8. Phân biệt ảnh chụp hiện tại với dữ liệu trong hệ thống giám sát

Registry tích lũy có thể giữ count và tổng từ khi meter được tạo trong tiến trình hiện tại. Registry theo khoảng có cách báo cáo khác, còn hệ thống giám sát có thể tính tốc độ hoặc chuyển đổi các tổng thành dữ liệu theo khoảng. Vì vậy “COUNT trên JSON”, “đường biểu diễn request/giây” và “số sự kiện trong 5 phút” không mặc nhiên là cùng một đại lượng.

Khi so sánh endpoint với dashboard, cần xác minh cùng tập tags/instance, cùng đơn vị, cùng cửa sổ truy vấn và cùng cách chuyển đổi. Tên metric xuất ra còn có thể được đổi theo quy ước của hệ thống đích; không đối chiếu chỉ bằng phần giống nhau của tên.

`/actuator/metrics` phục vụ chẩn đoán các metric hiện có; nó không phải cơ sở dữ liệu lịch sử hay endpoint thu thập thay cho một hệ thống giám sát sản xuất. Một ảnh chụp hiện tại không cho biết các giá trị đã bị bỏ lỡ giữa hai lần lấy mẫu, và MAX hiện tại không đại diện mọi đỉnh của ngày hôm qua. [Mục đích endpoint metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Không trộn COUNT/TOTAL_TIME của cả vòng đời tiến trình với MAX/p99 theo một cửa sổ ngắn rồi yêu cầu chúng thỏa các quan hệ thống kê của cùng một tập mẫu. Muốn so sánh, hãy làm rõ các đại lượng nào thực sự dùng chung phạm vi.

## 9. Quy trình đọc một metric chưa quen

1. **Đọc tên và mô tả:** thao tác, tài nguyên hay trạng thái nào đang được đo?
2. **Xác định loại meter:** counter, timer, gauge hay loại khác; không đoán chỉ từ tên statistic.
3. **Chốt tập tags và instance:** một nhóm, nhiều nhóm được gộp, hay một tiến trình trong hệ thống nhiều instance?
4. **Đọc đơn vị:** COUNT đếm lượng gì, các trường thời lượng đang là giây hay đơn vị khác, VALUE có phải tỉ lệ không?
5. **Xác định phạm vi thời gian:** tích lũy, theo khoảng, cực đại theo cửa sổ hay quan sát tại lần đọc?
6. **Chỉ tính toán khi các phạm vi tương thích:** trung bình cần tổng và số mẫu tương ứng; tốc độ cần khoảng thời gian và cách xử lý reset.
7. **Ghi kết luận đúng mức:** nêu đại lượng, phạm vi, đơn vị và giới hạn; không suy p99, nguyên nhân lỗi hoặc lịch sử đầy đủ từ một ảnh chụp.

Ví dụ kết luận có đủ ngữ cảnh: “Timer của nhóm `result=success` có 3 mẫu đã ghi trong kho tích lũy hiện tại, tổng 1,3 giây; cực đại còn hiệu lực là 0,9 giây. Chưa có dữ liệu để kết luận p95 hoặc tốc độ theo giây.”

## 10. Những lỗi diễn giải thường gặp

| Nhìn thấy | Kết luận sai | Cách diễn giải/kiểm tra |
| --- | --- | --- |
| `COUNT=500` | Có 500 request mỗi giây | Xác minh lượng đang đếm và cơ chế tích lũy/theo khoảng; cần thời gian để tính tốc độ |
| Counter tăng thêm 10 sau một lời gọi | Có 10 lần gọi Java | Counter có thể tăng theo một lượng lớn hơn 1 |
| Timer `TOTAL_TIME=12`, đơn vị giây | Một yêu cầu mất 12 giây | Đó là tổng thời lượng của các mẫu thuộc phạm vi báo cáo |
| Đầu vào ghi bằng ms | Mọi trường thời lượng trả về là ms | Đọc đơn vị của nguồn xuất hoặc dùng TimeUnit tường minh |
| `baseUnit=seconds`, `COUNT=4` | COUNT là 4 giây | COUNT của timer là số mẫu |
| MAX giảm hoặc về 0 | Đã xóa toàn bộ count/tổng | Kiểm tra cửa sổ cực đại và thời gian hết hạn |
| MAX bằng 2 giây | p99 bằng 2 giây | Không suy percentile từ cực đại |
| VALUE hàng đợi bằng 0 | Chưa có công việc nào từng vào hàng đợi | Nó chỉ phản ánh trạng thái lúc quan sát |
| Một gauge tỉ lệ có nhiều tags | Cộng các VALUE là tỉ lệ chung | Cần mẫu số và ý nghĩa cộng được; endpoint cộng số học chưa đủ |
| COUNT giảm sau khi đọc lại | Lưu lượng giảm một lượng âm | Kiểm tra reset, registry theo khoảng và việc đổi instance/tags |
| Không có statistic hoặc thấy NaN | Đại lượng bằng 0 | Phân biệt không có meter, trạng thái gauge đã mất và giá trị đo hợp lệ |
| Trung bình tích lũy lớn hơn MAX hiện tại | Timer chắc chắn hỏng | Có thể hai thống kê có cửa sổ khác nhau |

## 11. Tự kiểm tra

1. Một counter gọi `increment(4)` một lần và `increment()` một lần. Với registry tích lũy, COUNT là bao nhiêu và đang đếm điều gì?
2. Timer ghi 100 ms, 300 ms, 900 ms và xuất theo giây. Viết COUNT, TOTAL_TIME, MAX trước khi hết cửa sổ và trung bình theo ms.
3. Sau đủ thời gian không có mẫu mới, MAX về 0 nhưng COUNT/TOTAL_TIME không đổi. Giải thích vì sao không thể nói các thao tác trước đó mất 0 ms.
4. Thêm nhóm lỗi có một mẫu 2 giây. Tính COUNT, TOTAL_TIME, MAX và trung bình khi không lọc kết quả; giải thích vì sao không lấy trung bình đơn giản của hai trung bình nhóm.
5. Hàng đợi tăng 2→100→2 giữa hai lần lấy mẫu. VALUE cuối bằng 2 cho phép kết luận gì và chưa cho phép kết luận gì?
6. Hai ảnh chụp cùng timer tích lũy cách nhau 10 giây có COUNT 100→120 và TOTAL_TIME 20→26 giây. Tính tốc độ ghi mẫu và thời lượng trung bình của các mẫu mới; nêu điều kiện để phép tính hợp lệ.
7. Một JSON có COUNT, TOTAL_TIME và MAX. Nêu các thông tin còn thiếu trước khi kết luận về p95, dữ liệu của toàn cụm hoặc nguyên nhân hệ thống chậm.

Đọc đúng các statistic là diễn giải được **cái gì đã được đo, trên tập dữ liệu nào, theo đơn vị và thời gian nào**; các công thức chỉ có giá trị sau khi những ranh giới đó đã rõ.
