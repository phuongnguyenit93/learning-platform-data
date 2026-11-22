# Truy vấn metrics theo tên và tag, tránh hiểu nhầm kết quả đã tổng hợp

Một lần đọc `COUNT=15` chưa nói rằng một nhóm cụ thể đã xử lý 15 lần. Có thể con số đó đã gộp nhiều kênh, nhiều kết quả hoặc nhiều đối tượng cùng mang một tên meter. Muốn hiểu kết quả, cần biết **đã chọn những meter nào và đã gộp các số đo của chúng ra sao**.

Trong Spring Boot Actuator, endpoint `metrics` giúp kiểm tra tên, giá trị và các tag đang có. Bài này đi từ chọn tên, lọc tag đến diễn giải từng thống kê, rồi kiểm chứng bằng chương trình dùng Spring Boot 3.3.0 và Micrometer 1.13.0. Mã dùng Java 17 và chạy được trên JDK 21.

## 1. Mô hình đọc một truy vấn

Một truy vấn có thể được hiểu qua ba bước:

```text
Tên logic
    -> chọn các meter có tên phù hợp
    -> lọc theo các cặp khóa–giá trị tag
    -> gộp các thống kê của những meter còn khớp
    -> trả measurements và các tag có thể lọc tiếp
```

Ví dụ một họ counter `store.orders` đếm các lần ghi nhận kết quả xử lý đơn hàng:

| Tên | channel | result | COUNT |
| --- | --- | --- | --- |
| `store.orders` | `web` | `success` | 8 |
| `store.orders` | `web` | `failure` | 2 |
| `store.orders` | `api` | `success` | 5 |

Đây là ba meter theo ba tổ hợp tag, dù có cùng một tên logic. Bộ dữ liệu chưa có tổ hợp `channel=api, result=failure`.

Từ bảng đó:

- Chỉ chọn tên `store.orders`: gộp cả ba nhóm, được 15.
- Thêm `channel=web`: gộp hai nhóm web, được 10.
- Thêm tiếp `result=success`: chỉ còn nhóm web thành công, được 8.

Số 15 không phải một danh sách 15 đối tượng đơn hàng và cũng không tự chứng minh có 15 đơn duy nhất. Ý nghĩa đếm phụ thuộc quy tắc ghi nhận đã chọn. Nếu mỗi lần thử lại đều được đếm, số liệu phản ánh những lần ghi nhận đó.

## 2. Chọn đúng tên logic

### 2.1. Danh sách tên không phải danh sách mọi tổ hợp tag

Trong ứng dụng web có endpoint được cho phép truy cập, bắt đầu bằng:

```http
GET /actuator/metrics
```

Danh sách `names` cho biết các tên metrics đang được biết đến. Tên `store.orders` chỉ cần xuất hiện một lần dù registry đang có ba nhóm tag ở bảng trên.

Muốn xem chi tiết một họ số liệu:

```http
GET /actuator/metrics/store.orders
```

Endpoint là công cụ chẩn đoán số liệu đang được đăng ký trong ứng dụng; nó cung cấp tên, các số đo và khả năng lọc theo tag. [REST API metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 2.2. Dùng tên trong mã, không suy từ tên đã xuất

Actuator nhận tên logic dùng để đăng ký meter trong Java, chẳng hạn `store.orders` hoặc `store.checkout.duration`. Tên trên một hệ thống giám sát bên ngoài có thể đã được chuẩn hóa theo quy ước riêng.

Vì vậy, tên có dấu gạch dưới hoặc hậu tố thấy ở đầu ra của một exporter không mặc nhiên là tên cần đặt sau `/actuator/metrics/`. Khi chưa chắc, kiểm tra danh sách `names` và điểm đăng ký trong mã. [Hướng dẫn metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 2.3. Một tên chưa xuất hiện không đồng nghĩa giá trị bằng 0

Meter có thể chỉ được tạo khi một nhánh nghiệp vụ chạy lần đầu. Tên chưa có cũng có thể do filter, sai registry, sai instance hoặc sai tên logic.

Phân biệt:

- Meter tồn tại và số đo bằng 0.
- Meter chưa tồn tại hoặc không còn nhóm nào khớp điều kiện.
- Endpoint hoặc ứng dụng chưa truy cập được.

Ba trường hợp đó không nên được chuyển hết thành một số 0 rồi diễn giải như nhau.

## 3. Lọc theo tag bằng các điều kiện rõ ràng

Tag truyền qua tham số `tag` ở dạng `khóa:giá_trị`:

```http
GET /actuator/metrics/store.orders?tag=channel:web
GET /actuator/metrics/store.orders?tag=channel:web&tag=result:success
```

Ở truy vấn thứ hai, meter phải khớp **cả** `channel=web` **và** `result=success`. Các cặp tag khác khóa kết hợp như điều kiện AND.

| Điều kiện | Nhóm được chọn trong bộ dữ liệu | COUNT |
| --- | --- | --- |
| Không có tag | Web thành công, web thất bại, API thành công | 15 |
| `channel=web` | Hai nhóm web | 10 |
| `result=success` | Web thành công và API thành công | 13 |
| `channel=web`, `result=success` | Web thành công | 8 |
| `channel=api`, `result=failure` | Không có tổ hợp khớp | Không có số đo cho lựa chọn này |

### 3.1. Điều kiện lọc chưa chọn phải được hiểu là còn gộp

Truy vấn chỉ lọc `channel=web` vẫn còn cả thành công và thất bại. Con số 10 không phải số thành công của web.

Tương tự, lọc `result=success` vẫn còn nhiều kênh. Con số 13 không phải riêng số thành công của API hay web. Một điều kiện lọc được bỏ qua thường là một chiều chưa được phân tách trong kết quả tổng hợp.

Điều này đặc biệt quan trọng với các tag như vùng chạy, tên pool kết nối, loại cache, trạng thái hoặc đường dẫn HTTP. Cùng một tên có thể bao gồm nhiều nhóm cần được xem riêng.

### 3.2. Không mặc định tham số lặp lại là OR

Nhiều tham số `tag` được dùng để biểu diễn các cặp khóa–giá trị cần lọc. Không suy ra rằng lặp cùng một khóa với hai giá trị sẽ chọn một phép OR như ngôn ngữ truy vấn của hệ thống giám sát.

Nếu cần gộp hai giá trị cùng một khóa, hãy chọn đúng phạm vi tổng hợp, truy vấn từng nhóm để kiểm tra hoặc dùng một công cụ truy vấn hỗ trợ phép chọn đó rõ ràng. Giữ mỗi khóa trong một yêu cầu có một ý nghĩa cụ thể.

### 3.3. Chú ý giá trị và mã hóa URL

`channel=api` và `channel=API` không khớp cùng giá trị trong bộ dữ liệu này. Chỉ dùng những khóa và giá trị đúng với hợp đồng của meter.

Giá trị tag có khoảng trắng hoặc ký tự đặc biệt cần được mã hóa URL. Khi dùng shell, dấu `&` trong URL cũng cần được giữ như dữ liệu của đối số, không bị shell hiểu thành một thao tác khác.

Ví dụ dùng curl để mã hóa các giá trị và giữ URL gọn:

```shell
curl --get "http://localhost:8080/actuator/metrics/store.orders" --data-urlencode "tag=channel:web" --data-urlencode "tag=result:success"
```

Trên Windows, nếu tên `curl` đang trỏ tới lệnh khác thay vì chương trình curl, dùng `curl.exe` với các đối số tương ứng.

## 4. Đọc phản hồi và availableTags

Một phản hồi có các nhóm thông tin:

| Trường | Cách sử dụng | Không nên suy ra |
| --- | --- | --- |
| `name` | Xác nhận họ số liệu đang đọc | Không khẳng định chỉ có một meter theo tag |
| `description` | Hiểu ý nghĩa đã khai báo | Không thay thế việc kiểm tra cách ghi và gộp |
| `baseUnit` | Đọc đơn vị của số liệu | Không tự chuyển mọi số thành tốc độ hoặc giá trị trung bình |
| `measurements` | Đọc từng thống kê theo tên `statistic` | Không cộng các thống kê khác đơn vị vào nhau |
| `availableTags` | Tìm các chiều và giá trị có thể dùng để lọc tiếp | Không khẳng định mọi tổ hợp giá trị đều tồn tại |

Với bộ counter ở phần 1, phản hồi theo tên có nội dung tương đương ví dụ JSON sau; thứ tự các mục có thể khác:

```json
{
  "name": "store.orders",
  "description": "Recorded order outcomes",
  "baseUnit": "orders",
  "measurements": [
    { "statistic": "COUNT", "value": 15.0 }
  ],
  "availableTags": [
    { "tag": "channel", "values": ["api", "web"] },
    { "tag": "result", "values": ["failure", "success"] }
  ]
}
```

Đây là dữ liệu minh họa được dựng cho bài học. Tên trường và cấu trúc theo REST API Actuator; chương trình ở phần 7 tạo các descriptor tương ứng để kiểm chứng trực tiếp.

### 4.1. availableTags không phải bảng các tổ hợp

Thấy `channel` có `api`, `web` và `result` có `failure`, `success` chưa đủ để kết luận tồn tại cả bốn tổ hợp.

Trong dữ liệu đang xét, failure chỉ có ở web. Vì vậy, lựa chọn `api + failure` không có meter khớp dù từng giá trị riêng lẻ đều có trong `availableTags` của truy vấn rộng.

Muốn kiểm tra một tổ hợp, hãy lọc từng chiều và đọc tiếp các khả năng còn lại. Sau khi chọn `channel=api`, tag `result` còn giá trị `success` trong dữ liệu mẫu.

### 4.2. Điều kiện đã chọn làm hẹp khả năng lọc tiếp

Trong implementation dùng ở ví dụ, `availableTags` được tính từ các meter còn khớp; khóa đã dùng để lọc không còn được đưa ra như một chiều chưa chọn.

Sau `channel=web`, kết quả có thể lọc tiếp theo hai giá trị của `result`. Sau khi chọn cả `channel=web` và `result=success`, không còn chiều chưa chọn trong bộ counter đơn giản này.

Do đó, tag biến mất khỏi danh sách gợi ý sau khi đã lọc không nhất thiết là dữ liệu bị mất. Cần phân biệt điều kiện đã được áp dụng với chiều còn có thể chọn tiếp.

## 5. Gộp measurements đúng theo loại thống kê

Không chỉ hỏi “đã gộp bao nhiêu meter”; còn phải hỏi “trường thống kê này được gộp bằng phép toán nào?”.

Đối với các loại được kiểm chứng trong Spring Boot 3.3.0:

| Loại meter và thống kê | Cách endpoint gộp các nhóm khớp trong ví dụ | Cách đọc |
| --- | --- | --- |
| Counter – `COUNT` | Cộng các giá trị đếm | Tổng lượng ghi nhận của những nhóm đã chọn |
| Gauge – `VALUE` | Cộng các giá trị quan sát | Chỉ có nghĩa khi các trạng thái có thể cộng theo cùng câu hỏi |
| Timer – `COUNT` | Cộng số lần ghi | Tổng số mẫu thời gian đã ghi |
| Timer – `TOTAL_TIME` | Cộng tổng thời gian | Tổng thời gian của những mẫu đã ghi, theo đơn vị phản hồi |
| Timer – `MAX` | Lấy giá trị lớn nhất giữa các giá trị max của nhóm | Không phải cộng các max và không tự là max toàn bộ lịch sử |

**Lưu ý theo phiên bản:** mô tả tổng quát rằng endpoint “cộng các thống kê” không nên được áp dụng máy móc cho mọi `statistic`. Ví dụ chạy với Spring Boot 3.3.0 xác nhận `MAX` dùng giá trị lớn nhất. Khi kiểm tra hành vi cụ thể, cần đối chiếu implementation và phiên bản đang chạy.

### 5.1. Tổng gauge chỉ hữu ích khi phép cộng có nghĩa

Giả sử hai gauge độc lập biểu diễn hàng đợi web có 4 công việc và hàng đợi API có 7 công việc. Tổng 11 có nghĩa nếu cần xem số công việc chờ trong cả hai hàng đợi rời nhau.

Nếu hai gauge cùng quan sát một hàng đợi chia sẻ, cộng hai giá trị có thể đếm cùng dữ liệu hai lần. Nếu gauge biểu diễn tỷ lệ hoặc phần trăm, phép cộng thường còn cần xem ý nghĩa và mẫu số; không coi mọi tổng `VALUE` là một chỉ số tổng thể hợp lý.

Endpoint thực hiện phép gộp theo dữ liệu và thống kê. Nó không biết đầy đủ ý nghĩa nghiệp vụ để bảo đảm rằng cách bạn chọn nhóm đã tạo ra một đại lượng hữu ích.

### 5.2. Đọc Timer bằng số lần, tổng thời gian và đơn vị

Bộ dữ liệu timer dùng trong bài:

| channel | Các lần ghi thời gian | COUNT | TOTAL_TIME | MAX trước khi cửa sổ max hết hạn |
| --- | --- | --- | --- | --- |
| `web` | 100, 200, 300 ms | 3 | 0,6 giây | 0,3 giây |
| `api` | 900 ms | 1 | 0,9 giây | 0,9 giây |
| Gộp hai nhóm | Bốn lần ghi | 4 | 1,5 giây | 0,9 giây |

Thời gian trung bình của bốn mẫu là:

```text
Tổng thời gian / tổng số lần = 1,5 giây / 4 = 0,375 giây = 375 ms
```

Không lấy trung bình cộng của hai trung bình nhóm: web trung bình 200 ms, API trung bình 900 ms, nhưng `(200 + 900) / 2 = 550 ms` không phải trung bình của bốn mẫu. Hai nhóm có số mẫu khác nhau.

Khi `COUNT=0`, phép chia không tạo được một thời gian trung bình có nghĩa; không tự thay kết quả thành một số rồi coi đó là độ trễ đã đo.

Timer cung cấp ít nhất số lần và tổng thời gian; đơn vị cơ sở phụ thuộc registry. Giá trị max của các implementation cơ bản có cơ sở cửa sổ thời gian và có thể hết hạn khi không có ghi mới. [Timer trong Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

Do đó, max có thể về 0 trong khi count tích lũy vẫn giữ bốn lần của ví dụ. Không kết luận rằng các lần ghi cũ chưa từng có hoặc độ trễ cả vòng đời ứng dụng đã luôn bằng 0.

### 5.3. Các số tổng hợp không phục hồi được mọi chi tiết

`COUNT`, `TOTAL_TIME` và `MAX` không đủ để dựng lại toàn bộ phân bố thời gian. Không suy ra p95, p99 hoặc từng mẫu ban đầu chỉ từ ba con số đó.

Tương tự, một tổng counter theo tên không phục hồi được cách chia thành các tag nếu đã bỏ qua các nhóm. Hãy lọc lại đúng chiều cần phân tích hoặc dùng nguồn lưu trữ và truy vấn phù hợp.

## 6. Chuẩn bị truy cập qua HTTP trong ứng dụng web

Phần này dành cho một ứng dụng Spring Boot web đã có Actuator và đã ghi các meter. Có thể mở phạm vi endpoint cần cho môi trường học, chẳng hạn trong `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Cấu hình exposure cho phép cung cấp endpoint; nó không tự tạo dữ liệu nghiệp vụ và không thay thế cấu hình quyền truy cập. Địa chỉ, cổng và base path cũng có thể khác giá trị mặc định của các ví dụ.

Quy trình đọc lần lượt:

```shell
curl "http://localhost:8080/actuator/metrics"
curl "http://localhost:8080/actuator/metrics/store.orders"
curl "http://localhost:8080/actuator/metrics/store.orders?tag=channel:web"
curl "http://localhost:8080/actuator/metrics/store.orders?tag=channel:web&tag=result:success"
```

Nếu dùng một ứng dụng đang có lưu lượng thật, các giá trị có thể đổi giữa những lần gọi. Không áp đặt rằng tổng ở thời điểm trước phải bằng tổng các nhóm được đọc ở nhiều thời điểm sau.

Chương trình độc lập tiếp theo dùng cùng lớp `MetricsEndpoint` để kiểm chứng các phép chọn và gộp, nhưng không chạy web server. Muốn thử curl cần đưa các meter vào một ứng dụng web đang hoạt động; chỉ chạy chương trình dòng lệnh không mở cổng 8080.

## 7. Ví dụ Java đầy đủ và stdout có thể đối chiếu

Chương trình dựng ba nhóm counter, hai nhóm timer và hai gauge. Dữ liệu timer và gauge được tạo độc lập để minh họa phép gộp của từng loại; không giả định bốn lần timer là toàn bộ các lần ghi nhận counter.

### 7.1. Tệp dự án

Tạo thư mục thử nghiệm riêng:

```text
metric-query-demo/
├── pom.xml
└── MetricQueryDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>metric-query-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
```

Parent quản lý phiên bản thư viện theo Spring Boot 3.3.0. Ví dụ gọi API trực tiếp, nên không cần plugin đóng gói ứng dụng web để chạy phần kiểm chứng.

### 7.2. Mã nguồn

`MetricQueryDemo.java`:

```java
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.boot.actuate.metrics.MetricsEndpoint;

public class MetricQueryDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicInteger webQueue = new AtomicInteger(4);
        AtomicInteger apiQueue = new AtomicInteger(7);
        try {
            addOrders(registry, "web", "success", 8);
            addOrders(registry, "web", "failure", 2);
            addOrders(registry, "api", "success", 5);

            Timer web = registry.timer("store.checkout.duration", "channel", "web");
            web.record(Duration.ofMillis(100));
            web.record(Duration.ofMillis(200));
            web.record(Duration.ofMillis(300));
            Timer api = registry.timer("store.checkout.duration", "channel", "api");
            api.record(Duration.ofMillis(900));

            Gauge.builder("store.queue.depth", webQueue, AtomicInteger::get)
                    .tag("channel", "web").register(registry);
            Gauge.builder("store.queue.depth", apiQueue, AtomicInteger::get)
                    .tag("channel", "api").register(registry);

            MetricsEndpoint endpoint = new MetricsEndpoint(registry);
            System.out.println("knownCounterName="
                    + endpoint.listNames().getNames().contains("store.orders"));
            printCount("all", endpoint.metric("store.orders", null));
            printCount("web", endpoint.metric(
                    "store.orders", List.of("channel:web")));
            printCount("success", endpoint.metric(
                    "store.orders", List.of("result:success")));
            printCount("webSuccess", endpoint.metric(
                    "store.orders", List.of("channel:web", "result:success")));
            System.out.println("apiFailure="
                    + (endpoint.metric("store.orders",
                    List.of("channel:api", "result:failure")) == null
                    ? "NO_MATCH" : "MATCH"));

            var allOrders = endpoint.metric("store.orders", null);
            printTagValues(allOrders, "channel");
            printTagValues(allOrders, "result");

            var duration = endpoint.metric("store.checkout.duration", null);
            double count = measurement(duration, Statistic.COUNT);
            double total = measurement(duration, Statistic.TOTAL_TIME);
            double max = measurement(duration, Statistic.MAX);
            System.out.printf(Locale.ROOT,
                    "timerCount=%.0f totalSeconds=%.3f maxSeconds=%.3f meanMs=%.3f%n",
                    count, total, max, total / count * 1000);

            var queues = endpoint.metric("store.queue.depth", null);
            System.out.printf(Locale.ROOT, "queueValue=%.0f%n",
                    measurement(queues, Statistic.VALUE));
            System.out.println("queueSources="
                    + webQueue.get() + "+" + apiQueue.get());
        } finally {
            registry.close();
        }
    }

    private static void addOrders(SimpleMeterRegistry registry,
                                  String channel, String result, int amount) {
        Counter.builder("store.orders")
                .description("Recorded order outcomes")
                .baseUnit("orders")
                .tags("channel", channel, "result", result)
                .register(registry)
                .increment(amount);
    }

    static double measurement(
            MetricsEndpoint.MetricDescriptor descriptor, Statistic statistic) {
        return descriptor.getMeasurements().stream()
                .filter(sample -> sample.getStatistic() == statistic)
                .findFirst().orElseThrow().getValue();
    }

    private static void printCount(
            String label, MetricsEndpoint.MetricDescriptor descriptor) {
        System.out.printf(Locale.ROOT, "%s.count=%.0f%n",
                label, measurement(descriptor, Statistic.COUNT));
    }

    private static void printTagValues(
            MetricsEndpoint.MetricDescriptor descriptor, String tagName) {
        var tag = descriptor.getAvailableTags().stream()
                .filter(candidate -> candidate.getTag().equals(tagName))
                .findFirst().orElseThrow();
        System.out.println(tagName + "Values=" + new TreeSet<>(tag.getValues()));
    }
}
```

Các điểm cần quan sát trong mã:

1. `addOrders(...)` tạo các meter cùng tên nhưng khác tổ hợp tag, rồi tăng lượng tương ứng.
2. `MetricsEndpoint` nhận registry chứa dữ liệu. Lời gọi `metric(name, filters)` chọn và gộp số liệu như phần xử lý của endpoint.
3. Danh sách chuỗi `channel:web`, `result:success` là các điều kiện dùng cho lời gọi API trực tiếp; chúng tương ứng các tham số `tag` trong truy vấn HTTP.
4. `measurement(...)` chọn theo `Statistic`, không dựa vào vị trí của phần tử trong mảng `measurements`.
5. `apiFailure` kiểm tra trường hợp không có tổ hợp khớp. Lời gọi trực tiếp trả `null`; chương trình phân biệt nó với một descriptor có `COUNT=0`.
6. `TreeSet` chỉ sắp xếp giá trị tag khi in để stdout ổn định. Nó không thay đổi cách lọc của endpoint.
7. Hai đối tượng trạng thái gauge được giữ đến cuối phần quan sát. Registry được đóng trong `finally` theo vòng đời của chương trình độc lập.

### 7.3. Biên dịch và chạy

Cần Maven và JDK 17 trở lên; ví dụ đã dùng mức Java 17 và có thể chạy bằng JDK 21. Tải các phụ thuộc runtime:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricQueryDemo.java
java -cp "out;lib/*" MetricQueryDemo
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricQueryDemo.java
java -cp "out:lib/*" MetricQueryDemo
```

Classpath dùng dấu `;` trên Windows và `:` trên Linux/macOS. Lần tải đầu cần truy cập kho Maven nếu máy chưa có phụ thuộc.

Stdout:

```text
knownCounterName=true
all.count=15
web.count=10
success.count=13
webSuccess.count=8
apiFailure=NO_MATCH
channelValues=[api, web]
resultValues=[failure, success]
timerCount=4 totalSeconds=1.500 maxSeconds=0.900 meanMs=375.000
queueValue=11
queueSources=4+7
```

Đầu ra timer dùng giây cho registry của ví dụ, rồi chuyển sang mili giây khi tính trung bình. `Locale.ROOT` giữ dấu thập phân ổn định. Không lấy số `1.500` mà bỏ qua nhãn `totalSeconds` rồi coi đó là 1,5 ms.

## 8. Phân biệt truy vấn Actuator và tra cứu meter trong Java

Lời gọi đơn sau không có nghĩa là cộng mọi counter cùng tên:

```java
Counter one = registry.get("store.orders").counter();
```

Đây là đoạn trích cho registry đã có dữ liệu. Khi có nhiều nhóm tag, đừng dựa vào một phép lấy meter đơn để suy ra tổng và cũng đừng dựa vào thứ tự nhóm được chọn.

Muốn chọn đúng nhóm:

```java
Counter webSuccess = registry.get("store.orders")
        .tags("channel", "web", "result", "success")
        .counter();
```

Muốn chủ động cộng các counter trong một phạm vi:

```java
double webTotal = registry.find("store.orders")
        .tag("channel", "web")
        .counters()
        .stream()
        .mapToDouble(Counter::count)
        .sum();
```

Cần import `io.micrometer.core.instrument.Counter` và có biến `registry` phù hợp. Với bộ dữ liệu mẫu, `webTotal` là `10.0`.

Đây là phép tổng hợp do mã của bạn thực hiện trên những meter khớp. Nó khác với `counter()` trả một đối tượng và khác với `MetricsEndpoint` dựng descriptor theo các thống kê.

Chọn rõ mục đích của từng thao tác:

| Mục đích | Cách tiếp cận |
| --- | --- |
| Kiểm tra tên và các chiều có thể lọc | `MetricsEndpoint` hoặc endpoint HTTP `metrics` |
| Lấy một meter đã biết chính xác tên và tag | Tra cứu đơn với điều kiện đầy đủ |
| Tính tổng một tập counter trong Java | Lấy tập kết quả rồi cộng theo ý nghĩa mong muốn |
| Truy vấn lịch sử, tốc độ và cảnh báo qua nhiều lần thu thập | Nguồn lưu trữ và công cụ giám sát phù hợp |

## 9. Giới hạn cần giữ khi diễn giải kết quả

### 9.1. Phạm vi ứng dụng và instance

Endpoint trên một instance không tự trở thành kết quả của toàn bộ cụm dịch vụ. Khi chạy nhiều instance, xác định yêu cầu đang đi tới instance nào, nhất là khi truy cập qua bộ cân bằng tải.

Một lần gọi đi tới instance A và lần sau đi tới B có thể cho số khác nhau mà không có lỗi lọc. Muốn tổng hợp toàn cụm cần nguồn dữ liệu có nhận diện instance và quy tắc gộp đúng.

### 9.2. Snapshot không tự trở thành lịch sử hay tốc độ

`COUNT=15` trong counter tích lũy của ví dụ là lượng đã ghi nhận, không phải “15 đơn/giây”. Muốn có tốc độ cần mốc thời gian và lịch sử phù hợp, đồng thời hiểu cách registry xuất số liệu.

Endpoint `metrics` phục vụ việc kiểm tra, không thay vai trò một kho giám sát lịch sử. Việc bấm gọi lại vài lần để chẩn đoán không biến API này thành một backend lưu chuỗi thời gian.

### 9.3. Đơn vị và schema phải tương thích

Trước khi gộp, các nhóm cùng tên phải còn mô tả cùng đại lượng và có hợp đồng đơn vị nhất quán. Một nhóm ghi byte, nhóm khác ghi KiB nhưng dùng chung tên và metadata không được endpoint tự chữa thành dữ liệu đúng.

`description` và `baseUnit` trong phản hồi là thông tin mô tả, không phải bằng chứng rằng mọi điểm ghi đã tuân thủ hợp đồng. Cần kiểm tra ở nơi đăng ký và ghi số liệu khi kết quả có dấu hiệu sai.

Tag có ở họ counter cũng không tự tồn tại ở họ timer. Trong ví dụ, counter dùng `result`, còn timer chỉ dùng `channel`; không dùng danh sách tag của một tên để mặc định truy vấn mọi tên khác.

### 9.4. Kết quả có thể đổi trong lúc quan sát

Các lần ghi có thể diễn ra đồng thời với các phép đọc. Một descriptor hoặc nhiều yêu cầu liên tiếp không phải mặc nhiên là giao dịch đọc nguyên tử của toàn bộ trạng thái nghiệp vụ.

Khi cần kiểm chứng giá trị chính xác, dùng dữ liệu được kiểm soát như chương trình mẫu. Với hệ thống đang chạy, chọn bằng chứng phù hợp và tính tới độ mới, vòng đời instance cùng các cửa sổ thống kê.

## 10. Chẩn đoán khi kết quả khác dự đoán

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Có tên nhưng lọc một tổ hợp không có dữ liệu | Tổ hợp có thực sự tồn tại không, hay chỉ từng giá trị riêng có trong `availableTags`? |
| Counter theo tên cao hơn nhóm đang quan tâm | Có tag nào chưa lọc nên vẫn đang gộp nhiều nhóm? |
| Không tìm thấy tên sao chép từ exporter | Tên logic trong registry có khác tên đã chuẩn hóa không? |
| `availableTags` hẹp đi sau một bộ lọc | Những nhóm nào còn khớp và khóa nào đã được chọn? |
| Tổng gauge gây khó hiểu | Các trạng thái có rời nhau và phép cộng có đúng ý nghĩa không? |
| Trung bình timer lệch dự đoán | Có dùng tổng thời gian chia tổng số lần hay đang lấy trung bình của các trung bình nhóm? |
| MAX không bằng tổng các max nhóm | Thống kê này dùng phép lấy lớn nhất trong implementation đã kiểm chứng |
| MAX về 0 nhưng COUNT vẫn còn | Cửa sổ max có hết hạn trong khi count vẫn tích lũy không? |
| Hai lần gọi cùng URL khác số | Có ghi mới, đổi instance hoặc cửa sổ thống kê đã dịch chuyển không? |
| Không có số liệu nhưng giao diện hiển thị 0 | Có đang gộp trường hợp không có kết quả vào trường hợp giá trị thật bằng 0 không? |

Trình tự kiểm tra hữu ích là: xác nhận instance và truy cập endpoint, tên logic, tập tag, phạm vi còn khớp, loại thống kê, đơn vị và cơ sở thời gian. Khi từng lớp đều rõ, việc diễn giải một con số tổng hợp sẽ có căn cứ hơn.

## 11. Thực hành

Thay đổi từng phần trên một lần chạy mới và dự đoán đầu ra:

1. Thêm `addOrders(registry, "api", "failure", 4)`. Tổng counter thành 19; web vẫn 10; success vẫn 13; tổ hợp API thất bại lúc này có dữ liệu. Hãy kiểm tra lại `availableTags` sau khi lọc API.
2. Chỉ giữ bộ lọc `channel:web` trong truy vấn `webSuccess`. Kết quả trở thành 10 vì vẫn còn cả hai kết quả của web; tên biến không tự thêm điều kiện.
3. Thêm một mẫu timer 400 ms cho web. Tổng timer thành 5 mẫu và 1,9 giây; trung bình là 380 ms, max hiện tại vẫn là 900 ms.
4. Đổi giá trị tag truy vấn từ `api` sang `API`. So sánh trường hợp không có nhóm khớp với trường hợp counter thực sự có giá trị 0.
5. Đọc `registry.get("store.orders").counter()` rồi so sánh với tổng của tập `counters()`. Giải thích vì sao một phép lấy đối tượng đơn không phải phép tổng hợp.
6. Lọc counter theo một kênh, đọc các tag còn lại rồi chọn tiếp. Không suy ra mọi tổ hợp từ danh sách giá trị của truy vấn rộng.

Khi ghi lại kết quả, mô tả đủ phạm vi: “COUNT của tất cả kết quả đơn hàng”, “COUNT của web”, hoặc “COUNT của web thành công”. Với timer, ghi cả thống kê và đơn vị, chẳng hạn “tổng thời gian 1,5 giây của bốn mẫu” thay vì chỉ nêu một số chưa có ngữ cảnh.
