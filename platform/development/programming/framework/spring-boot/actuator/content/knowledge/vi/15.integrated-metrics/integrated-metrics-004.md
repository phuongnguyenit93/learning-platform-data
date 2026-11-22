# Quan sát HTTP server: số yêu cầu, độ trễ, mã phản hồi và mẫu URI

## 1. Một yêu cầu HTTP cần được nhìn từ bốn góc

Khi một API chậm hoặc báo lỗi, bốn câu hỏi ban đầu thường là:

1. Có bao nhiêu yêu cầu đi qua, tốc độ thay đổi ra sao?
2. Những yêu cầu đã kết thúc mất bao lâu ở phía server?
3. Server trả những mã phản hồi nào?
4. Yêu cầu thuộc nhóm đường dẫn nào, chẳng hạn `/api/items/{id}`?

Một tổng số request không trả lời được độ trễ. Một trung bình độ trễ không cho biết đang lỗi ở API nào. Một URL đầy đủ chứa từng ID lại có thể tạo quá nhiều chuỗi dữ liệu để giám sát.

Spring Boot Actuator tích hợp Micrometer để cung cấp phép đo HTTP có sẵn. Bài này dùng Spring MVC trên Spring Boot 3.3.13, tập trung vào `http.server.requests` và cách đọc bốn góc nhìn trên.

Ví dụ có cả mã ứng dụng và kiểm chứng MockMvc. Không tự tạo một bộ đếm thay cho phép đo có sẵn của Spring.

## 2. http.server.requests là Timer, không chỉ là một Counter

Spring Boot tự cấu hình đo yêu cầu do Spring MVC xử lý, với tên mặc định `http.server.requests`. Trong nhánh Boot này, cơ chế được tích hợp qua Micrometer Observation và bộ lọc HTTP của framework. Xem [Spring Boot: Spring MVC Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

Đường xử lý khái quát:

```text
Yêu cầu đi vào phần được instrument của server
    -> bắt đầu observation
    -> chọn handler, xử lý yêu cầu và tạo phản hồi
    -> observation kết thúc
    -> Timer ghi count và khoảng thời gian cùng các tag
    -> Actuator/backend đọc những số liệu đã ghi
```

Với Timer:

| Thống kê | Ý nghĩa |
| --- | --- |
| `COUNT` | Số mẫu yêu cầu đã kết thúc và được ghi nhận |
| `TOTAL_TIME` | Tổng thời gian của những mẫu đó |
| `MAX` | Thời gian lớn nhất theo cửa sổ thống kê của cách hiện thực |
| Histogram/phân vị | Thông tin bổ sung khi được cấu hình và backend hỗ trợ |

Do đã có count trong Timer, không cần thêm một Counter để đếm lại đúng cùng các yêu cầu đó chỉ vì tên metric có chữ “requests”.

Một yêu cầu vẫn đang chạy chưa tự có mẫu thời gian hoàn chỉnh trong Timer này. Count không phải số kết nối hiện tại hoặc số yêu cầu đang xử lý. Muốn quan sát công việc đang chạy cần phép đo active hoặc hạ tầng server phù hợp.

## 3. Các tag biến một tổng số thành những nhóm có thể phân tích

Trong cấu hình được kiểm chứng ở bài, các nhóm thông tin quan trọng là:

| Tag | Ví dụ | Dùng để trả lời |
| --- | --- | --- |
| `method` | `GET`, `POST` | Phương thức nào tạo lưu lượng? |
| `status` | `200`, `201`, `404`, `503` | Server trả mã nào? |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Nhóm kết quả theo họ mã phản hồi |
| `uri` | `/api/items/{id}` | Mẫu đường dẫn/nhóm handler nào? |
| `error`, `exception` | `none` hoặc tên loại lỗi được ghi | Observation có được gắn lỗi hay không? |

Tên và chi tiết tag có thể thay đổi theo phiên bản, stack và convention tùy chỉnh. Bản Boot 3.3.13 được chạy trong bài có cả `error` và `exception`; hãy kiểm tra tag thực tế thay vì áp nguyên danh sách của một bản Spring khác.

Một tên `http.server.requests` có thể có nhiều Timer: mỗi tổ hợp tag tạo một danh tính meter khác nhau. Hai request cùng mẫu URI nhưng khác status vẫn thuộc hai nhóm thống kê.

Ví dụ:

```text
method=GET, uri=/api/items/{id}, status=200
method=GET, uri=/api/items/{id}, status=404
method=POST, uri=/api/items, status=201
```

Chỉ lọc URI chưa chắc đã chọn đúng một Timer. Khi cần phân tích riêng một nhánh, hãy lọc thêm method, status hoặc các tag liên quan.

## 4. Số yêu cầu và tốc độ: đừng nhầm HTTP với nghiệp vụ

Count của Timer cho biết số yêu cầu được phép đo ghi nhận. Khi tiến trình khởi động lại hoặc danh tính chuỗi thay đổi, số tích lũy có thể bắt đầu lại.

Một người bấm “Thanh toán” có thể tạo nhiều HTTP request do tải dữ liệu, kiểm tra trạng thái hoặc thử lại. Một request có thể thất bại trước khi giao dịch nghiệp vụ được tạo. Do đó:

```text
HTTP request count != số người dùng
HTTP request count != số đơn hàng thành công
HTTP request count != số giao dịch nghiệp vụ duy nhất
```

Với biểu đồ và cảnh báo, thường cần tốc độ theo thời gian, chẳng hạn request/giây, theo cùng tập tag. Không so hai tổng số tích lũy của hai tiến trình có tuổi khác nhau rồi kết luận máy nào đang chịu tải cao hơn.

Cũng cần xác định tập yêu cầu: có tính endpoint giám sát, health check, static resource và yêu cầu không khớp API không? Một tổng số không lọc có thể bao gồm những nhóm đó.

Nếu đổi bộ lọc, phải ghi rõ ý nghĩa của số đếm mới. Không gọi mọi request được đếm là “request nghiệp vụ thành công”.

## 5. Độ trễ: đơn vị, phạm vi và phân bố

### 5.1. Timer server không phải đồng hồ đầu-cuối của người dùng

`http.server.requests` đo thời gian xử lý trao đổi HTTP ở phạm vi framework/server được instrument. Nó không tự bao gồm toàn bộ thời gian DNS, TLS, mạng, hàng đợi ở proxy và xử lý trên trình duyệt.

Đây cũng không đơn thuần là thời gian bên trong một phương thức controller. Biên đo nằm ở hạ tầng HTTP, có thể bao gồm các bước khác trong phạm vi đó. Với xử lý bất đồng bộ hoặc streaming, cần kiểm tra vòng đời observation của stack đang dùng.

Nếu proxy trả timeout trong khi ứng dụng tiếp tục xử lý, dữ liệu ở proxy và ứng dụng có thể khác nhau. Phải đối chiếu đúng góc nhìn.

### 5.2. Trung bình dùng tổng thời gian chia số mẫu tương ứng

Ví dụ số học: ba yêu cầu cùng nhóm mất 100 ms, 300 ms và 500 ms:

```text
COUNT      = 3
TOTAL_TIME = 900 ms
mean       = 900 / 3 = 300 ms
```

Đây là số liệu minh họa phép tính, không phải độ trễ cố định của bộ kiểm chứng bên dưới.

Đọc `baseUnit` khi xem Actuator. Với cấu hình trong bài, đơn vị thời gian trả về là giây; Prometheus cũng xuất các chuỗi với hậu tố `seconds`. Không lấy một giá trị giây rồi gắn nhãn mili giây.

Khi tổng hợp nhiều instance hoặc nhiều nhóm, hãy cộng các tổng thời gian và cộng count tương ứng rồi chia. Không lấy trung bình đơn giản của các giá trị trung bình có số mẫu khác nhau.

### 5.3. Trung bình, max và p95 trả lời những câu khác nhau

Một số ít yêu cầu rất chậm có thể bị che bởi trung bình thấp. Max cho biết một giá trị cực đại trong phạm vi thống kê, nhưng không mô tả phân bố của tất cả yêu cầu.

p95 cần dữ liệu phân vị/histogram phù hợp. Nó không tự có chỉ vì đã có Timer, và không thể suy ra từ count cộng tổng thời gian.

Max của Timer cơ bản có thể hết hạn theo cửa sổ; không phải kỷ lục trọn đời. Không cộng hoặc lấy trung bình các p95 của nhiều máy để gọi đó là p95 chung. Xem [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 6. Mã phản hồi, outcome và ngoại lệ không đồng nghĩa

Các nhóm outcome thường gắn với họ mã HTTP:

| Họ mã | Outcome | Ví dụ |
| --- | --- | --- |
| 1xx | `INFORMATIONAL` | Phản hồi thông tin |
| 2xx | `SUCCESS` | `200`, `201`, `204` |
| 3xx | `REDIRECTION` | `302` |
| 4xx | `CLIENT_ERROR` | `400`, `401`, `404`, `429` |
| 5xx | `SERVER_ERROR` | `500`, `503` |

Tên nhóm mô tả họ mã HTTP, không tự chứng minh bên nào gây ra nguyên nhân cuối cùng. Chẳng hạn 429 có thể phản ánh giới hạn tải, còn 404 có thể là yêu cầu dò đường dẫn hoặc một lỗi URL từ client của chính hệ thống.

Một controller trả `ResponseEntity.status(503)` có thể không ném ngoại lệ. Khi đó status=503 và outcome=SERVER_ERROR nhưng error/exception vẫn có thể bằng none.

Ngược lại, một ngoại lệ đã được `@ExceptionHandler` xử lý không phải lúc nào cũng tự được gắn vào observation. Đường ghi lỗi cần được cấu hình/đánh dấu đúng nếu ứng dụng muốn giữ thông tin đó. Spring Boot có nêu giới hạn này trong [hướng dẫn HTTP server metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

Vì vậy:

- Theo dõi tỷ lệ 5xx bằng status/outcome nếu mục tiêu là phản hồi HTTP 5xx.
- Không dùng riêng `exception != none` để thay cho mọi lỗi HTTP.
- Không coi status=200 là bằng chứng mọi điều kiện thành công nghiệp vụ đã đúng.
- Khi điều tra nguyên nhân, kết hợp metrics với log hoặc trace; các tag tổng hợp không chứa toàn bộ lỗi chi tiết.

## 7. Mẫu URI: gộp đúng nhóm mà không tạo vô hạn chuỗi

### 7.1. Template khác đường dẫn đã thay ID

Ba yêu cầu:

```text
GET /api/items/101
GET /api/items/202
GET /api/items/303
```

có thể cùng khớp mapping:

```text
GET /api/items/{id}
```

Metric nên giữ mẫu URI để nhìn cả API như một nhóm. Nếu gắn mỗi ID vào tag, số chuỗi tăng theo số ID từng truy cập. Đó là vấn đề **cardinality**, tức số tổ hợp nhãn tạo ra.

Cần giữ tag ở tập giá trị có kiểm soát. Không đưa query string, token, mã yêu cầu hoặc ID người dùng vào tag metrics để thay cho log/trace. Micrometer cảnh báo về số lượng tag tăng theo đầu vào người dùng tại [Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Trong cơ chế Observation của Boot, thông tin có cardinality cao có thể thuộc đường traces; không tự biến nó thành tag metrics. Xem [Spring Boot: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 7.2. Cùng template vẫn có nhiều nhóm status/method

Hai request trả 200 và một request trả 404 trên `/api/items/{id}` có thể tạo hai Timer theo status, dù vẫn cùng mẫu URI.

Query parameter như `source=dashboard` không tự tạo một mẫu URI mới trong convention mặc định của ví dụ. Tuy nhiên, nếu tham số làm ứng dụng chọn nhánh khác hoặc trả status khác, các kết quả đo có thể khác vì lý do đó.

### 7.3. 404 không phải lúc nào cũng có uri=NOT_FOUND

Phải phân biệt:

1. Đã khớp `/api/items/{id}` nhưng tài nguyên không tồn tại: URI có thể vẫn là template đó.
2. Không có controller tương ứng nhưng request được resource handler tiếp nhận: một pattern như `/**` có thể được dùng.
3. Không có pattern thích hợp: convention có thể dùng các giá trị đại diện như `NOT_FOUND` hoặc `UNKNOWN` tùy tình huống.

Trong cấu hình MVC mặc định của bài, `/api/not-mapped` đi vào resource handler, trả 404 và được ghi `uri=/**`. Bộ kiểm chứng xác nhận đúng trường hợp này.

Không đổi mọi 404 thành đường dẫn thô để “xem cho rõ”. Một đợt truy cập vào hàng nghìn URL không tồn tại có thể làm số chuỗi tăng không kiểm soát. Muốn biết URL chi tiết, dùng dữ liệu điều tra phù hợp và giữ tag tổng hợp ổn định.

## 8. Thực hành: một ứng dụng và một kiểm chứng có thể chạy lại

Dùng JDK 21 và Maven 3.6.3+. Mã ứng dụng biên dịch với đích Java 17; các phiên bản được cố định bởi Spring Boot 3.3.13 để kết quả tag của bài có bối cảnh rõ ràng.

Bài có hai cách dùng:

- Chạy MockMvc để kiểm chứng mapping, status, tag, count và định dạng xuất Prometheus mà không mở cổng mạng.
- Đóng gói và chạy ứng dụng web để thử lệnh HTTP trong môi trường cục bộ.

MockMvc không đo được độ trễ mạng, TLS hay hành vi qua reverse proxy. Các thời gian tuyệt đối không được viết thành hằng số trong kiểm chứng.

### 8.1. Cấu trúc và phụ thuộc

```text
http-server-metrics-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── HttpMetricsApplication.java
    │   │   └── ItemController.java
    │   └── resources/application.properties
    └── test/java/demo/HttpServerMetricsTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>http-server-metrics-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Starter web cung cấp MVC, Actuator cung cấp hạ tầng metrics, registry Prometheus cung cấp định dạng xuất, và starter test dùng cho kiểm chứng. Không có Counter hoặc Timer HTTP tự viết.

### 8.2. Điểm vào ứng dụng

Tệp `src/main/java/demo/HttpMetricsApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpMetricsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpMetricsApplication.class, args);
    }
}
```

### 8.3. Controller tạo những kết quả cần quan sát

Tệp `src/main/java/demo/ItemController.java`:

```java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.Map;

@RestController
public class ItemController {
    @GetMapping("/api/items/{id}")
    ResponseEntity<Item> item(@PathVariable String id) {
        if (id.equals("404")) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, "demo"));
    }

    @PostMapping("/api/items")
    ResponseEntity<Item> create() {
        return ResponseEntity.created(URI.create("/api/items/303"))
                .body(new Item("303", "created"));
    }

    @GetMapping("/api/reports")
    ResponseEntity<Map<String, String>> report() {
        return ResponseEntity.status(503)
                .body(Map.of("message", "temporarily unavailable"));
    }

    public record Item(String id, String name) {}
}
```

Đây là API học thử để tạo các tình huống HTTP:

- Hai ID khác nhau vẫn đi qua cùng mapping GET.
- ID `404` được controller chủ động trả 404.
- POST trả 201.
- API báo cáo chủ động trả 503 mà không ném ngoại lệ.

Không có CSDL hoặc nghiệp vụ lưu trữ trong ví dụ; mã phản hồi là dữ liệu phục vụ phép thử quan sát.

### 8.4. Cấu hình cục bộ

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18090
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Ứng dụng chỉ bind vào loopback. Ví dụ không cấu hình xác thực và chỉ dùng trong môi trường học thử. Đường truy cập Actuator trong một hệ thống vận hành cần được bảo vệ theo cấu hình quản trị của hệ thống.

Không cần đăng ký thêm `ServerHttpObservationFilter` thủ công trong ứng dụng Boot này khi auto-configuration đang hoạt động.

### 8.5. Bảy yêu cầu và kết quả dự đoán

| Yêu cầu mẫu | Status | Mẫu URI trong cấu hình bài |
| --- | --- | --- |
| GET `/api/items/101` | 200 | `/api/items/{id}` |
| GET `/api/items/202` | 200 | `/api/items/{id}` |
| GET `/api/items/404` | 404 | `/api/items/{id}` |
| POST `/api/items` | 201 | `/api/items` |
| GET `/api/reports` | 503 | `/api/reports` |
| GET `/api/not-mapped` | 404 | `/**` |
| GET `/api/items/101?source=dashboard` | 200 | `/api/items/{id}` |

Với các tag mặc định không đổi khác, bảy request này được gộp thành năm chuỗi Timer hoàn tất:

```text
GET  /api/items/{id}  200 -> count 3
GET  /api/items/{id}  404 -> count 1
POST /api/items       201 -> count 1
GET  /api/reports     503 -> count 1
GET  /**             404 -> count 1
```

### 8.6. Kiểm chứng đầy đủ

Tệp `src/test/java/demo/HttpServerMetricsTest.java`:

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.stream.StreamSupport;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = HttpMetricsApplication.class)
@AutoConfigureMockMvc
@AutoConfigureObservability
class HttpServerMetricsTest {
    @Autowired MockMvc mvc;
    @Autowired MeterRegistry registry;
    @Autowired ObjectMapper json;
    @Autowired PrometheusMeterRegistry prometheus;

    @Test
    void observeHttpRequests() throws Exception {
        mvc.perform(get("/api/items/101")).andExpect(status().isOk());
        mvc.perform(get("/api/items/202")).andExpect(status().isOk());
        mvc.perform(get("/api/items/404")).andExpect(status().isNotFound());
        mvc.perform(post("/api/items")).andExpect(status().isCreated());
        mvc.perform(get("/api/reports")).andExpect(status().isServiceUnavailable());
        mvc.perform(get("/api/not-mapped")).andExpect(status().isNotFound());
        mvc.perform(get("/api/items/101").param("source", "dashboard"))
                .andExpect(status().isOk());

        Timer ok = timer("GET", "/api/items/{id}", "200");
        Timer missingItem = timer("GET", "/api/items/{id}", "404");
        Timer report = timer("GET", "/api/reports", "503");
        Timer created = timer("POST", "/api/items", "201");
        Timer unknown = registry.find("http.server.requests")
                .tag("status", "404").timers().stream()
                .filter(t -> !"/api/items/{id}".equals(t.getId().getTag("uri")))
                .findFirst().orElseThrow();

        List<Timer> all = List.copyOf(
                registry.find("http.server.requests").timers());
        long count = all.stream().mapToLong(Timer::count).sum();
        assertThat(count).isEqualTo(7);
        assertThat(ok.count()).isEqualTo(3);
        assertThat(missingItem.count()).isEqualTo(1);
        assertThat(created.count()).isEqualTo(1);
        assertThat(report.count()).isEqualTo(1);
        assertThat(report.getId().getTag("outcome")).isEqualTo("SERVER_ERROR");
        assertThat(report.getId().getTag("exception")).isEqualTo("none");
        assertThat(report.getId().getTag("error")).isEqualTo("none");
        assertThat(unknown.getId().getTag("uri")).isEqualTo("/**");
        assertThat(all).hasSize(5);
        boolean rawUriTagged = all.stream().anyMatch(t ->
                List.of("/api/items/101", "/api/items/202", "/api/items/404")
                        .contains(t.getId().getTag("uri")));
        assertThat(rawUriTagged).isFalse();
        assertThat(all).allMatch(t -> t.totalTime(TimeUnit.NANOSECONDS) > 0);

        String scrape = prometheus.scrape();
        assertThat(scrape).contains("http_server_requests_seconds_count");
        assertThat(scrape).contains("http_server_requests_seconds_sum");

        System.out.println("CHECK business.count=" + count);
        System.out.println("CHECK items.GET.200.count=" + ok.count());
        System.out.println("CHECK items.GET.404.count=" + missingItem.count());
        System.out.println("CHECK items.POST.201.count=" + created.count());
        System.out.println("CHECK report.status=" + report.getId().getTag("status"));
        System.out.println("CHECK report.outcome=" + report.getId().getTag("outcome"));
        System.out.println("CHECK report.exception=" + report.getId().getTag("exception"));
        System.out.println("CHECK report.error=" + report.getId().getTag("error"));
        System.out.println("CHECK unknown.uri=" + unknown.getId().getTag("uri"));
        System.out.println("CHECK completed.series=" + all.size());
        System.out.println("CHECK raw.uri.tagged=" + rawUriTagged);

        String body = mvc.perform(get("/actuator/metrics/http.server.requests")
                        .param("tag", "uri:/api/items/{id}", "method:GET", "status:200"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode measurements = json.readTree(body).path("measurements");
        double filteredCount = StreamSupport.stream(measurements.spliterator(), false)
                .filter(m -> m.path("statistic").asText().equals("COUNT"))
                .mapToDouble(m -> m.path("value").asDouble())
                .findFirst().orElseThrow();
        assertThat(filteredCount).isEqualTo(3.0);
        System.out.println("CHECK metrics.filtered.count=" + (long) filteredCount);

        long afterMetricsQuery = registry.find("http.server.requests")
                .timers().stream().mapToLong(Timer::count).sum();
        assertThat(afterMetricsQuery).isEqualTo(8);
        System.out.println("CHECK after.metrics.query.count=" + afterMetricsQuery);
    }

    private Timer timer(String method, String uri, String status) {
        return registry.get("http.server.requests")
                .tags("method", method, "uri", uri, "status", status).timer();
    }
}
```

Kiểm chứng chạy trong một application context mới, gửi bảy yêu cầu mẫu rồi gửi thêm một truy vấn Actuator đã lọc.

`@AutoConfigureObservability` bật phần cần thiết cho kiểm chứng observability/registry trong bối cảnh test. Không giả định mọi test slice hoặc `@SpringBootTest` tự khởi tạo mọi exporter giống môi trường chạy thật. Xem [Spring Boot: Using Metrics in Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.metrics).

Đứng ở thư mục dự án và chạy:

```powershell
mvn -q test
```

Ngoài log khởi động Spring và thông tin của công cụ chạy test, các dòng `CHECK` do bài kiểm chứng in ra khớp chính xác:

```text
CHECK business.count=7
CHECK items.GET.200.count=3
CHECK items.GET.404.count=1
CHECK items.POST.201.count=1
CHECK report.status=503
CHECK report.outcome=SERVER_ERROR
CHECK report.exception=none
CHECK report.error=none
CHECK unknown.uri=/**
CHECK completed.series=5
CHECK raw.uri.tagged=false
CHECK metrics.filtered.count=3
CHECK after.metrics.query.count=8
```

Điểm cần chú ý:

1. `business.count` là nhãn trong bài test cho bảy yêu cầu mẫu, không phải số giao dịch nghiệp vụ thành công.
2. Hai ID và một query parameter vẫn góp vào một nhóm GET/200 của template.
3. Một 404 đã khớp controller khác với một 404 của resource handler.
4. Status 503 không tự tạo error/exception khác none.
5. Truy vấn `metrics` trả COUNT=3 cho tập tag đã lọc.
6. Sau chính truy vấn chẩn đoán, tổng Timer tăng từ 7 lên 8 trong cấu hình này. Yêu cầu quản trị cũng có thể được đo như các yêu cầu HTTP khác.
7. Thời gian chỉ được kiểm tra là đã ghi nhận; không bịa một tổng mili giây cố định cho mọi máy.
8. Nội dung xuất thật từ registry Prometheus được kiểm tra có các chuỗi count/sum tương ứng.

## 9. Chạy web và đọc metric bằng HTTP

Sau khi kiểm chứng đạt, có thể đóng gói và chạy:

```powershell
mvn -q -DskipTests package
java -jar target/http-server-metrics-lab-1.0.0.jar
```

Ứng dụng dùng cổng 18090 theo cấu hình. Đợi server khởi động xong rồi dùng một terminal khác. Nhấn `Ctrl+C` ở terminal Java để kết thúc sau khi học.

Các lệnh sau dùng `curl.exe` trên Windows; trên Linux/macOS thay bằng `curl`:

```powershell
curl.exe --include "http://127.0.0.1:18090/api/items/101"
curl.exe --include "http://127.0.0.1:18090/api/items/202"
curl.exe --include "http://127.0.0.1:18090/api/items/404"
curl.exe --include --request POST "http://127.0.0.1:18090/api/items"
curl.exe --include "http://127.0.0.1:18090/api/reports"
curl.exe --include "http://127.0.0.1:18090/api/not-mapped"
curl.exe --include "http://127.0.0.1:18090/api/items/101?source=dashboard"
```

Đây là cách tạo lại bộ yêu cầu mẫu. Count tích lũy của một server đang chạy còn phụ thuộc những request đã gửi trước đó, kể cả trình duyệt hoặc endpoint quản trị. Muốn so chính xác với bộ test, dùng tiến trình mới và kiểm soát lưu lượng.

### 9.1. Khám phá tên, đơn vị và tag

```powershell
curl.exe --silent --show-error "http://127.0.0.1:18090/actuator/metrics"
curl.exe --silent --show-error "http://127.0.0.1:18090/actuator/metrics/http.server.requests"
```

Đọc:

- `baseUnit` để biết đơn vị.
- `measurements` để phân biệt COUNT, TOTAL_TIME, MAX.
- `availableTags` để biết tập tag/giá trị đang có.

Một truy vấn không lọc có thể gộp nhiều Timer. Không coi tổng đó là độ trễ của riêng một route.

### 9.2. Lọc theo template, method và status

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18090/actuator/metrics/http.server.requests" --data-urlencode "tag=uri:/api/items/{id}" --data-urlencode "tag=method:GET" --data-urlencode "tag=status:200"
```

Mỗi `tag` là một điều kiện `tên:giá trị`. Khi muốn xem nhóm API, dùng template đã quan sát, không dùng đường dẫn sau khi thay ID.

`--data-urlencode` giúp giữ dấu ngoặc nhọn và các ký tự trong tham số. Với một tập request mới đúng như test, nhóm lọc có COUNT=3; thời gian thực tế thay đổi theo lần chạy.

Endpoint `metrics` dùng để chẩn đoán giá trị đang đăng ký. Nó không tự lưu lịch sử và không nên được dùng làm backend/scrape endpoint production. Xem [Spring Boot: Metrics endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 9.3. Xem định dạng xuất Prometheus

```powershell
curl.exe --silent --show-error "http://127.0.0.1:18090/actuator/prometheus"
```

Với registry trong bài, các tên đã kiểm chứng gồm:

```text
http_server_requests_seconds_count
http_server_requests_seconds_sum
```

Tên dùng ở `/actuator/metrics` vẫn là `http.server.requests`. Không đem tên đã đổi sang dạng Prometheus đặt vào đường dẫn endpoint metrics rồi kết luận meter bị mất.

Một điểm đọc trực tiếp cho biết trạng thái hiện tại; muốn biểu đồ theo thời gian, cần hệ thống giám sát thu thập và lưu lịch sử.

## 10. Các truy vấn giám sát cần giữ đúng tập dữ liệu

Các biểu thức dưới là ví dụ PromQL khi dữ liệu đã được Prometheus thu. Giả sử tập dữ liệu của ứng dụng được gắn `job="http-lab"`; khi triển khai, chọn đúng job/service thực tế và chính sách lọc của hệ thống.

### 10.1. Tốc độ theo URI và method

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{job="http-lab"}[5m])
)
```

Kết quả có đơn vị yêu cầu/giây. `[5m]` là cửa sổ tính tốc độ, không phải độ trễ từng yêu cầu và không tự đặt chu kỳ scrape.

Hàm rate có xử lý reset và ngoại suy theo dữ liệu quan sát. Với nhiều instance, tính rate trên từng chuỗi rồi mới cộng để tránh làm mất dấu reset của từng tiến trình. Xem [Prometheus: rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

### 10.2. Độ trễ trung bình theo cùng cửa sổ

```promql
1000 *
sum by (uri, method) (
  rate(http_server_requests_seconds_sum{job="http-lab"}[5m])
)
/
sum by (uri, method) (
  rate(http_server_requests_seconds_count{job="http-lab"}[5m])
)
```

Nhân 1000 để biểu diễn mili giây. Tử số và mẫu số phải có cùng tập lọc và nhóm. Nếu không có đủ dữ liệu hoặc không có yêu cầu trong cửa sổ, không tự suy diễn rằng độ trễ bằng 0.

Tổng duration không phải thời gian CPU. Nhiều request có thể chồng lấn và cùng chờ tài nguyên.

### 10.3. Tỷ lệ phản hồi 5xx

```promql
100 *
sum(
  rate(http_server_requests_seconds_count{
    job="http-lab",status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{job="http-lab"}[5m])
)
```

Biểu thức này mô tả tỷ lệ 5xx trong tập yêu cầu đang chọn, không phải mọi loại thất bại nghiệp vụ. Nếu giữ cả endpoint quản trị trong mẫu số, cần biết chúng cũng ảnh hưởng tỷ lệ.

Nếu chính sách loại health/management hoặc chỉ xét một số route, áp dụng tập lọc phù hợp cho cả tử và mẫu. Không thay mẫu số bằng lưu lượng của một nhóm khác.

Cũng cần phân biệt thiếu chuỗi 5xx, giá trị lỗi bằng 0 và không có lưu lượng. Cách hiển thị/cảnh báo phải xử lý rõ các trường hợp đó, thay vì coi mọi điểm thiếu là “khỏe”.

## 11. Khi cần p95 và ngưỡng độ trễ

Để xuất histogram cho Timer HTTP, một cấu hình bổ sung có thể là:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,500ms,1s
```

Đây là phần mở rộng, không nằm trong cấu hình mặc định của bộ kiểm chứng. Khởi động lại với cấu hình phù hợp, tạo lưu lượng và xác minh dữ liệu bucket thực tế trước khi dùng truy vấn phân vị.

Ví dụ tính p95 từ classic histogram khi những bucket tương ứng đã tồn tại:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri, method) (
    rate(http_server_requests_seconds_bucket{job="http-lab"}[5m])
  )
)
```

Kết quả này có đơn vị giây. Chọn bộ lọc status có chủ đích: p95 của yêu cầu thành công và p95 của mọi phản hồi có thể khác nhau, nhất là khi lỗi bị trả rất nhanh.

Histogram tăng số chuỗi theo số bucket và tổ hợp tag. Không bật mọi thống kê trên một không gian tag đã chứa ID không giới hạn. Phân vị ước lượng cũng không có nghĩa từng request dưới một ngưỡng tuyệt đối.

Các thuộc tính per-meter được mô tả trong [Spring Boot: Per-meter Properties](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

## 12. Điều tra và lỗi thường gặp

Đi từ một câu hỏi cụ thể như “GET item đang chậm” hoặc “tỷ lệ 503 tăng”, rồi kiểm tra:

1. **Phạm vi đo:** đúng server, đúng instance, đúng metric chưa; có đang nhầm HTTP client metrics không?
2. **Lưu lượng:** count/rate có tăng thật hay dữ liệu đang thiếu, tiến trình vừa restart?
3. **Nhóm kết quả:** status/outcome nào tăng, có phụ thuộc một method/URI không?
4. **Độ trễ:** đang xem mean, max hay phân vị; cùng cửa sổ và tập request không?
5. **Mẫu URI:** đang dùng template, wildcard của resource handler hay giá trị đại diện?
6. **Chi tiết nguyên nhân:** cần log/trace, trạng thái GC, pool kết nối hoặc lỗi downstream nào để giải thích tiếp?

Những lỗi dễ mắc:

| Cách làm | Vấn đề |
| --- | --- |
| Tạo Counter riêng cho cùng toàn bộ HTTP request đã được đo | Trùng ngữ nghĩa, có thể lệch do điểm cập nhật khác nhau |
| Coi count là số request đang chạy | Timer thông thường ghi các lần hoàn tất |
| Coi tổng thời gian là trung bình | Thiếu phép chia theo count tương ứng |
| Coi độ trễ server là độ trễ đầu-cuối của client | Khác phạm vi mạng/proxy và xử lý phía client |
| Lọc lỗi chỉ bằng exception | Có 5xx không ném ngoại lệ hoặc ngoại lệ đã được xử lý |
| Đưa URL chứa từng ID vào tag | Cardinality tăng theo đầu vào |
| Coi mọi 404 có cùng URI đại diện | Mapping/resource handler/convention có thể khác |
| Gửi nhiều truy vấn metrics rồi mong tổng HTTP không đổi | Chính các truy vấn quản trị có thể được đo |
| Lấy trung bình p95 của các instance | Không tạo được p95 chung đúng từ các phân vị đó |
| Dùng các thuộc tính/cách tùy chỉnh của một bản Boot cũ mà không kiểm tra | Hạ tầng Observation và contract tag có thể đã thay đổi |

Trong Boot 3.3, nếu thật sự cần thay đổi cách lấy tag, sử dụng contract observation convention tương ứng và giữ nguyên ý nghĩa những tag mặc định cần thiết. Không đổi `uri` thành raw URL để phục vụ một nhu cầu điều tra tạm thời.

Metrics là dữ liệu tổng hợp; log và trace giúp giải thích từng lần xử lý. Một đợt 503 tăng cần tìm nguyên nhân như giới hạn tài nguyên, downstream hoặc nhánh trả lỗi chủ động, không chỉ đổi màu đường biểu đồ.

## 13. Tự kiểm tra

**Bài tập 1:** Gửi 100 request GET với 100 ID khác nhau, cùng khớp `/api/items/{id}`, đều trả 200 và các tag khác giống nhau. Có bắt buộc tạo 100 Timer không?

**Đáp án:** không. Theo template và các tag đó, chúng có thể góp vào cùng một Timer với count tăng 100. Gắn raw ID vào tag mới gây tăng nhóm không cần thiết.

**Bài tập 2:** Controller trả 503 nhưng không ném ngoại lệ. `exception=none` có phủ nhận lỗi HTTP không?

**Đáp án:** không. Status/outcome mô tả phản hồi HTTP; exception/error mô tả thông tin lỗi được observation ghi. Trong ví dụ, 503 đi cùng SERVER_ERROR và none.

**Bài tập 3:** Một Timer có COUNT=4, TOTAL_TIME=0,8 giây. Trung bình là bao nhiêu?

**Đáp án:** 0,2 giây, tức 200 ms, nếu hai thống kê thuộc cùng tập mẫu. Không gọi 0,8 giây là độ trễ trung bình.

**Bài tập 4:** Bộ test có 7 request mẫu nhưng sau một lần đọc Actuator tổng count là 8. Có chắc đã đếm đôi một request nghiệp vụ không?

**Đáp án:** không. Trong cấu hình bài, chính yêu cầu chẩn đoán cũng được đo. Cần kiểm tra URI/tag của lần tăng thêm.

**Bài tập 5:** Một 404 được ghi `uri=/**` thay vì NOT_FOUND. Có chắc raw URL đã bị đưa vào tag không?

**Đáp án:** không. Trong cấu hình đã kiểm chứng, đó là pattern của resource handler. Phải đọc mapping và convention thực tế; `/**` không phải một ID cụ thể.

**Bài tập 6:** Đã có count và sum. Có thể tính p95 chính xác chỉ từ hai số đó không?

**Đáp án:** không. Cần thông tin phân bố phù hợp như histogram, cùng quy tắc tổng hợp/cửa sổ của backend.

Khi quan sát HTTP server, hãy giữ bốn yếu tố đi cùng nhau: lượng yêu cầu, thời gian xử lý, mã phản hồi và mẫu URI. Một kết luận tốt phải chỉ rõ nhóm request nào được đo, trong khoảng nào và từ góc nhìn của thành phần nào.
