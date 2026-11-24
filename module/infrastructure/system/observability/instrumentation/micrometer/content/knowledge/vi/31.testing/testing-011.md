# Kiểm thử nội dung scrape hoặc dữ liệu xuất thay vì chỉ đọc giá trị registry

Một test gọi `registry.get("...").counter().count()` chỉ chứng minh meter trong bộ nhớ đang giữ giá trị mong đợi. Nó chưa chứng minh registry có thể chuyển meter thành định dạng mà backend hiểu, tên metric và đơn vị được chuẩn hóa đúng, tag được xuất, histogram có bucket, endpoint HTTP hoạt động hoặc exporter gửi dữ liệu thành công.

Với module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, kiểm thử instrumentation cần đi qua đúng ranh giới mà hệ thống giám sát sử dụng. Nếu production dùng Prometheus, hãy kiểm tra Prometheus exposition hoặc endpoint `/actuator/prometheus`. Nếu production dùng OTLP, hãy kiểm tra payload mà Collector nhận và dữ liệu sau pipeline. Giá trị trong registry vẫn hữu ích cho unit test, nhưng không thay thế kiểm thử scrape/export.

## 1. Các tầng kiểm thử metrics

Có thể chia kiểm thử thành bốn tầng. Mỗi tầng trả lời một câu hỏi khác nhau:

| Tầng | Đối tượng kiểm tra | Bằng chứng nhận được |
| --- | --- | --- |
| Meter API | Counter, Timer, Gauge và source state | Giá trị trong registry, count, total time hoặc gauge value đúng. |
| Registry exposition | `PrometheusMeterRegistry.scrape()` hoặc API export tương ứng | Tên, type, unit, label, sample và bucket được serialize đúng. |
| HTTP endpoint | `/actuator/prometheus` hoặc endpoint management tương ứng | Endpoint được expose, trả status và body đúng định dạng. |
| Export pipeline | OTLP exporter, Collector, agent hoặc backend test | Dữ liệu thực sự đi qua transport và được receiver diễn giải đúng. |

Không phải mọi test đều cần chạy backend production. Unit test có thể kiểm tra registry exposition; integration test có thể chạy Collector hoặc receiver thử nghiệm. Điều quan trọng là chọn tầng đủ để xác minh hợp đồng mà ứng dụng đang phụ thuộc.

## 2. Vì sao chỉ đọc giá trị registry là chưa đủ?

Ví dụ:

```java
Counter counter = registry.counter("shop.orders.created", "channel", "web");
counter.increment(3.0);

assertThat(counter.count()).isEqualTo(3.0);
```

Assertion này không phát hiện các lỗi ở lớp export:

- Naming convention có thể đổi `shop.orders.created` thành tên khác trong Prometheus.
- Counter có thể được xuất với hậu tố `_total` hoặc quy tắc tên riêng của registry.
- Tag key/value có thể bị chuẩn hóa hoặc escape.
- Timer có thể được biểu diễn thành count, sum, max và histogram bucket.
- Unit thời gian có thể được chuyển sang giây khi xuất Prometheus.
- Meter có thể bị `MeterFilter` từ chối hoặc đổi ID.
- Endpoint có thể chưa được expose hoặc bị security chặn.
- Exporter có thể gửi sai endpoint, sai content type hoặc không gửi do lỗi kết nối.

Do đó, test đọc registry là test hữu ích ở tầng meter, nhưng cần thêm test nội dung exposition hoặc export để kiểm tra hành vi quan sát được từ bên ngoài.

## 3. Kiểm thử Prometheus exposition trực tiếp

Với Prometheus registry, `PrometheusMeterRegistry.scrape()` trả về nội dung exposition mà Prometheus có thể đọc. Đây là cách kiểm tra naming convention, type và label mà không cần khởi động HTTP server.

Ví dụ kiểm tra một Counter:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class PrometheusScrapeTest {
    @Test
    void exportsCounterWithPrometheusNameAndLabels() {
        try (PrometheusMeterRegistry registry =
                     new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            Counter.builder("shop.orders.created")
                    .tag("channel", "web")
                    .tag("result", "success")
                    .register(registry)
                    .increment(3.0);

            String exposition = registry.scrape();

            assertThat(exposition)
                    .contains("# TYPE shop_orders_created_total counter");

            String sample = Arrays.stream(exposition.split("\n"))
                    .filter(line -> line.startsWith("shop_orders_created_total{"))
                    .findFirst()
                    .orElseThrow(AssertionError::new);

            assertThat(sample)
                    .contains("channel=\"web\"")
                    .contains("result=\"success\"")
                    .endsWith("3.0");
        }
    }
}
```

Đoạn code minh họa cho dòng Micrometer dùng package `io.micrometer.prometheusmetrics`. Một số phiên bản Micrometer cũ dùng package `io.micrometer.prometheus`; hãy dùng package và artifact phù hợp với phiên bản được Spring Boot quản lý. Tên sample trong test là hợp đồng của registry/version đã chọn, vì vậy cần điều chỉnh kỳ vọng có chủ đích khi nâng phiên bản.

Test này xác minh output thực tế từ `scrape()`: metric type, tên đã chuẩn hóa, label và giá trị sample. Nó kiểm tra nhiều hơn việc Counter trong registry đang bằng 3.

## 4. Kiểm thử Timer, unit và histogram

Timer có thể được xuất thành nhiều sample. Với Prometheus, một timer thường tạo count và sum; khi bật histogram, output còn có bucket. Thời lượng thường được chuẩn hóa sang giây.

```java
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

Timer.builder("shop.checkout.duration")
        .publishPercentileHistogram()
        .register(registry)
        .record(250, TimeUnit.MILLISECONDS);

String exposition = registry.scrape();
assertThat(exposition)
        .contains("shop_checkout_duration_seconds_count")
        .contains("shop_checkout_duration_seconds_sum")
        .contains("shop_checkout_duration_seconds_bucket");
```

Khi kiểm tra histogram, đừng chỉ khẳng định có một sample count. Hãy kiểm tra:

- Metric type được xuất là histogram theo convention của registry.
- Sample count tăng đúng số lần record.
- Sum phản ánh đơn vị đã chuẩn hóa, ví dụ 250 ms tương đương 0,25 giây.
- Bucket sample tồn tại nếu đã bật histogram.
- Tag set giống nhau trên các sample thuộc cùng meter.
- Không có bucket hoặc tag value ngoài dự kiến.

Bucket boundaries có thể thay đổi khi cấu hình percentile histogram hoặc registry version thay đổi. Nếu bucket là hợp đồng dashboard/alert, hãy kiểm tra các boundary quan trọng một cách tường minh; nếu không, chỉ kiểm tra histogram được xuất và count/sum đúng để tránh test phụ thuộc thứ tự hoặc toàn bộ chuỗi exposition.

## 5. Kiểm thử DistributionSummary và đơn vị

DistributionSummary thường dùng cho đại lượng không phải thời gian như byte, kích thước payload hoặc số item. Khai báo base unit rõ ràng và kiểm tra output sau export:

```java
import io.micrometer.core.instrument.DistributionSummary;

DistributionSummary payload = DistributionSummary.builder("app.payload.size")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .register(registry);
payload.record(4096);

String exposition = registry.scrape();
assertThat(exposition)
        .contains("app_payload_size_bytes_count")
        .contains("app_payload_size_bytes_sum");
```

Ví dụ tên có hậu tố `_bytes` phụ thuộc naming convention của Prometheus registry và phiên bản. Hãy xem output thật của registry dự án trước khi chốt expected name. Không tự đổi label đơn vị trong dashboard mà không chuyển đổi giá trị tương ứng.

## 6. Kiểm tra tag escaping và giá trị động

Tag value được serialize theo quy tắc của backend. Với Prometheus exposition, ký tự đặc biệt trong label value cần được escape. Test output có thể xác minh label value được giữ nguyên về mặt ngữ nghĩa và không làm hỏng cú pháp exposition.

Không nên tạo tag từ trace ID, user ID, order ID, URL đầy đủ hoặc exception message. Test nên có trường hợp chứng minh tag được chuẩn hóa về tập giá trị hữu hạn, chẳng hạn `route=/orders/{id}` và `result=error`.

Ví dụ test tag chuẩn hóa:

```java
Counter.builder("shop.http.requests")
        .tag("route", "/orders/{id}")
        .tag("result", "success")
        .register(registry)
        .increment();

String exposition = registry.scrape();
assertThat(exposition)
        .contains("route=\"/orders/{id}\"")
        .contains("result=\"success\"");
```

Khi cần kiểm tra cardinality, có thể tạo nhiều input khác nhau nhưng cùng route template và xác minh registry chỉ có một meter identity cho nhóm đó. Đồng thời kiểm tra output không chứa ID cụ thể.

## 7. Kiểm thử MeterFilter trong nội dung export

`MeterFilter` có thể deny meter, đổi ID hoặc điều chỉnh cấu hình phân phối. Test chỉ đọc meter trước filter hoặc chỉ kiểm tra builder không đủ để xác minh output cuối cùng.

Ví dụ registry từ chối meter có prefix nội bộ:

```java
import io.micrometer.core.instrument.config.MeterFilter;

PrometheusMeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
registry.config().meterFilter(MeterFilter.denyNameStartsWith("internal."));

Counter.builder("internal.cache.refresh").register(registry).increment();
Counter.builder("shop.orders.created").register(registry).increment();

String exposition = registry.scrape();
assertThat(exposition).doesNotContain("internal_cache_refresh");
assertThat(exposition).contains("shop_orders_created_total");
```

Kết quả cần xác minh ở exposition cuối cùng. Hãy chú ý filter có thể được cấu hình trong application context hoặc registry cụ thể; test phải dùng đúng registry và thứ tự cấu hình gần production.

## 8. Kiểm thử endpoint /actuator/prometheus bằng Spring Boot

Unit test gọi `scrape()` không chứng minh endpoint HTTP được expose. Một integration test với Spring Boot có thể kiểm tra đường đi từ meter trong application context đến HTTP response.

Dependency cần có Actuator và Prometheus registry:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Expose endpoint trong test:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - prometheus
```

Ví dụ integration test:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.containsString;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties =
        "management.endpoints.web.exposure.include=prometheus")
@AutoConfigureMockMvc
class PrometheusEndpointTest {
    @Autowired MockMvc mockMvc;
    @Autowired MeterRegistry registry;

    @Test
    void exposesRegisteredMetricAsPrometheusText() throws Exception {
        registry.counter("test.export.visible", "kind", "sample").increment(2.0);

        mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("test_export_visible_total")))
                .andExpect(content().string(containsString("kind=\"sample\"")));
    }
}
```

Test này xác minh endpoint trả body có metric đã đăng ký. Nếu ứng dụng bật Spring Security, cấu hình test authentication hoặc security chain phù hợp. Nếu management server dùng port riêng, base path khác hoặc endpoint được bảo vệ ở network layer, cần test đúng cấu hình triển khai.

Không nên chỉ kiểm tra HTTP 200. Response có thể hợp lệ nhưng thiếu metric do meter bị filter, registry không đúng hoặc endpoint đang phục vụ registry khác. Hãy assert một metric có tên và label đặc trưng.

## 9. Kiểm thử OTLP qua Collector hoặc receiver thử nghiệm

OTLP là push protocol. Gọi `registry.get(...)` không xác minh payload OTLP, endpoint URL, content type, resource attributes, temporality hoặc việc Collector nhận được dữ liệu. Với OTLP, integration test nên kiểm tra một receiver thật hoặc receiver giả có thể ghi nhận request.

Một test pipeline có thể chạy OpenTelemetry Collector với OTLP/HTTP receiver và Prometheus exporter để kiểm tra dữ liệu sau khi Collector nhận và chuyển tiếp:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  prometheus:
    endpoint: 0.0.0.0:9464

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

Trong test profile, cấu hình OTLP registry gửi đến receiver này. Sau khi tạo meter và chờ chu kỳ export, scrape endpoint Prometheus do Collector mở và xác minh metric đã đến. Cách này kiểm tra được nhiều lớp: serialize OTLP, HTTP transport, receiver, pipeline và mapping sang exposition.

Ví dụ property thường dùng trong Spring Boot:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 1s
```

Tên property và cách cấu hình exporter cần được xác minh theo phiên bản Spring Boot/Micrometer của dự án. Chỉ dùng step ngắn trong test để giảm thời gian chờ; production cần chọn chu kỳ phù hợp với lưu lượng và chi phí. Dùng Awaitility hoặc cơ chế polling có timeout để đợi metric xuất hiện, không dựa vào một `Thread.sleep()` cố định.

### 9.1. Những gì cần kiểm tra trong OTLP pipeline

- Receiver nhận request tại đúng endpoint và trả status thành công.
- Content type và payload phù hợp với OTLP transport đã cấu hình.
- Resource attributes như `service.name` có mặt và đúng.
- Metric name, unit, type và attributes đúng kỳ vọng.
- Sum temporality là cumulative hoặc delta theo cấu hình.
- Histogram count, sum và bucket data được giữ sau pipeline.
- Collector không drop metric do processor/filter hoặc memory limiter.
- Exporter phía Collector chuyển tiếp dữ liệu đến backend test.

Payload protobuf không nên được so sánh bằng chuỗi byte cố định. Hãy decode thành OTLP data model hoặc xác minh ở receiver/exported exposition để test tập trung vào semantics.

## 10. Kiểm tra chu kỳ export và dữ liệu bất đồng bộ

Với push registry, meter có thể chưa xuất ngay khi `increment()` hoặc `record()` vừa chạy. Registry có thể gom dữ liệu theo step và gửi ở chu kỳ tiếp theo. Test cần tính đến thời gian này.

Các nguyên tắc:

- Cấu hình step test ngắn nhưng đủ để pipeline xử lý.
- Chờ theo điều kiện dữ liệu xuất hiện với timeout hữu hạn.
- Dừng registry hoặc application context đúng lifecycle để scheduler không rò rỉ.
- Không giả định gọi `close()` luôn flush dữ liệu theo cùng cách ở mọi registry; kiểm tra hợp đồng exporter đang dùng.
- Phân biệt thời điểm ghi meter với thời điểm exporter gửi và backend ingest.
- Nếu test dùng queue/batch processor, chờ batch được xử lý trước khi assert.

Với pull registry như Prometheus, scrape đọc snapshot hiện tại nên thường không cần đợi step push. Tuy vậy, meter phải được đăng ký và cập nhật trước khi endpoint được gọi.

## 11. Kiểm tra nội dung export theo hợp đồng, tránh snapshot quá mong manh

Toàn bộ exposition có thể thay đổi thứ tự metric, comment, HELP text hoặc sample khi nâng phiên bản registry. Một snapshot nguyên văn của toàn bộ endpoint thường dễ hỏng dù semantics không đổi.

Nên assert các phần thuộc hợp đồng của ứng dụng:

- Metric name sau naming convention đã chọn.
- Metric type quan trọng như counter hoặc histogram.
- Label key/value cần thiết cho query và alert.
- Unit và scale của sample.
- Count/sum hoặc sample value đã biết.
- Bucket hoặc percentile data nếu dashboard phụ thuộc.
- Resource attributes và temporality khi test OTLP.

Tránh assert thứ tự toàn bộ dòng hoặc thời gian chính xác của timer. Với duration, kiểm tra trong một khoảng hợp lý hoặc chỉ xác minh count và unit nếu giá trị thời gian không ổn định.

## 12. Kiểm tra không xuất dữ liệu không mong muốn

Export test cũng nên kiểm tra những thứ không được xuất:

- Không có user ID, email, order ID hoặc trace ID trong metric labels.
- Không có URL chứa path ID hoặc query string động.
- Không có exception message hoặc nội dung payload làm label.
- Meter bị deny bởi filter không xuất hiện trong exposition.
- Tag value ngoài allowlist được chuẩn hóa về `other` hoặc bị loại theo policy.
- Không có resource attribute nhạy cảm trong OTLP payload.

Các kiểm tra này bảo vệ cardinality và tránh vô tình đưa dữ liệu nhạy cảm vào hệ thống metrics. Đừng chỉ test rằng metric mong muốn xuất hiện; hãy test cả các ràng buộc về dữ liệu bị cấm.

## 13. Kiểm tra nhiều registry và composite registry

Spring Boot có thể cấu hình một `CompositeMeterRegistry` chứa một hoặc nhiều registry con. Một test chỉ inject `MeterRegistry` rồi đọc giá trị có thể đang kiểm tra composite registry trong bộ nhớ, không chứng minh registry con thực sự export.

Khi dùng composite registry:

1. Xác minh registry con của backend mong muốn có mặt trong application context.
2. Tạo meter qua registry được inject theo đúng cách production sử dụng.
3. Kiểm tra exposition hoặc receiver của registry con.
4. Xác minh filter được gắn vào đúng registry và không chỉ vào một registry khác.
5. Kiểm tra hành vi khi registry con bị lỗi hoặc bị loại khỏi composite.

Không dùng `SimpleMeterRegistry` để thay cho Prometheus hoặc OTLP registry trong test export. Simple registry hữu ích cho unit test giá trị, nhưng không thực hiện protocol export.

## 14. Tách unit test và export integration test

| Test | Nên dùng | Không chứng minh được |
| --- | --- | --- |
| Kiểm tra logic gọi increment/record | `SimpleMeterRegistry` | Naming convention hoặc transport. |
| Kiểm tra Prometheus serialization | `PrometheusMeterRegistry.scrape()` | HTTP endpoint và scrape network. |
| Kiểm tra Actuator endpoint | `MockMvc` hoặc `WebTestClient` | Prometheus server bên ngoài đã ingest. |
| Kiểm tra OTLP transport | Receiver giả hoặc Collector test | Backend production đang khỏe. |
| Kiểm tra end-to-end | Collector/backend trong môi trường test | Không thay thế quan sát vận hành production. |

Giữ unit test nhanh và ổn định. Chạy export integration test khi thay registry, naming convention, filter, histogram configuration, exporter hoặc Spring Boot Actuator setup.

## 15. Troubleshooting khi scrape/export test thất bại

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Registry value đúng nhưng scrape thiếu metric | Meter bị filter hoặc registry exposition khác | Kiểm tra filter và gọi `scrape()` trên đúng registry. |
| Tên sample khác expected | Naming convention hoặc version thay đổi | In output và xác minh convention của registry. |
| Label bị thiếu | Tag không được gắn hoặc bị filter | Kiểm tra meter ID và output exposition. |
| Timer thiếu bucket | Chưa bật histogram hoặc registry không hỗ trợ cấu hình đó | Kiểm tra distribution config và output type. |
| Endpoint trả 404 | Actuator chưa expose hoặc thiếu Prometheus registry | Kiểm tra dependency và management exposure. |
| Endpoint trả 401/403 | Security policy chặn | Cấu hình test authentication và quyền truy cập. |
| OTLP receiver không nhận dữ liệu | Sai endpoint, protocol hoặc export step chưa đến | Kiểm tra URL, log exporter và chờ theo điều kiện. |
| OTLP có dữ liệu nhưng unit khác | Unit conversion hoặc mapping của Collector/backend | Kiểm tra payload và data model sau pipeline. |
| Metric không xuất sau khi dùng composite registry | Registry con không được cấu hình hoặc filter khác nhau | Kiểm tra child registry và export riêng. |

Khi lỗi, hãy lần theo đường đi theo thứ tự: meter đã được ghi nhận chưa, registry nào đang sở hữu meter, exposition có chứa sample không, endpoint có trả body đó không, exporter có gửi không và receiver có nhận không. Cách này khoanh vùng được tầng lỗi mà không nhầm một giá trị registry đúng với một lần export thành công.

## 16. Checklist kiểm thử nội dung scrape hoặc dữ liệu xuất

- [ ] Unit test xác minh logic ghi Counter, Gauge, Timer và DistributionSummary.
- [ ] Dùng registry đúng backend để kiểm tra serialization.
- [ ] Gọi `scrape()` hoặc API export thực tế, không chỉ đọc meter value.
- [ ] Xác minh tên metric sau naming convention.
- [ ] Xác minh metric type, unit, label và sample value.
- [ ] Kiểm tra count/sum/bucket khi dùng Timer hoặc DistributionSummary histogram.
- [ ] Kiểm tra MeterFilter tác động lên output cuối cùng.
- [ ] Integration test endpoint Actuator nếu production scrape qua HTTP.
- [ ] Với OTLP, xác minh receiver nhận payload và pipeline giữ đúng resource, unit, attributes, temporality.
- [ ] Chờ push/export theo step bằng điều kiện có timeout.
- [ ] Kiểm tra dữ liệu không mong muốn và cardinality.
- [ ] Tránh snapshot toàn bộ exposition nếu thứ tự hoặc comment không phải hợp đồng.
- [ ] Chạy export test khi thay registry, exporter, filter hoặc cấu hình histogram.

Kiểm thử scrape/export cần xác minh điều backend thực sự nhận. `SimpleMeterRegistry` và các assertion trên `registry.get(...)` vẫn quan trọng cho unit test, nhưng không phát hiện lỗi serialize, naming convention, unit, label, histogram, endpoint hay transport. Hãy dùng Prometheus registry để kiểm tra exposition, Actuator integration test để kiểm tra HTTP scrape và Collector/receiver thử nghiệm để xác minh OTLP. Khi test theo hợp đồng dữ liệu thay vì snapshot dễ vỡ, ứng dụng có thể thay đổi implementation mà vẫn giữ metric output tương thích với dashboard và alert.
