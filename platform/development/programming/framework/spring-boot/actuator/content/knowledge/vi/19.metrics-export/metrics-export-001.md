## Phân biệt cơ chế kéo dữ liệu với cơ chế đẩy dữ liệu

Một ứng dụng có thể ghi cùng một số đo trong bộ nhớ nhưng đưa số đo đó ra ngoài theo hai cách. Với cơ chế kéo (pull), bên thu thập chủ động đến đọc. Với cơ chế đẩy (push), bộ xuất ở phía nguồn chủ động gửi đến nơi nhận. Hãy xác định **ai khởi tạo kết nối ở từng chặng**. Hai cơ chế đều chuyển giá trị metric từ nơi tạo số đo đến nơi thu thập.

### Bên nào kết nối và bên nào quyết định nhịp?

| Điểm cần xác định | Kéo trực tiếp bằng Prometheus | Đẩy bằng bộ xuất OTLP của Micrometer |
| --- | --- | --- |
| Bên mở kết nối | Prometheus gửi `GET` đến endpoint của ứng dụng. | Ứng dụng gửi `POST` có dữ liệu metrics đến bộ nhận OTLP/HTTP. |
| Bên đặt lịch | Prometheus đặt `scrape_interval` cho công việc thu thập. | Ứng dụng đặt `management.otlp.metrics.export.step` cho nhịp xuất. |
| Địa chỉ cần truy cập | Từ Prometheus đến từng target, chẳng hạn cổng quản trị của ứng dụng. | Từ ứng dụng đến Collector hoặc nơi nhận có hỗ trợ OTLP. |
| Tín hiệu khi có sự cố | Trạng thái target, lỗi lần thu thập gần nhất và metric `up`. | Lỗi gửi phía bộ xuất, số liệu phía bộ nhận và thời điểm nhận điểm dữ liệu mới nhất của nguồn. |

**Kéo.** Bộ đăng ký của Micrometer giữ các số đo trong ứng dụng. Khi nhận `GET /actuator/prometheus`, Actuator trả về các số đo ở định dạng thu thập của Prometheus. Prometheus lưu các mẫu theo lịch của nó. Một lần gọi thủ công bằng `curl` xác minh endpoint có dữ liệu, còn trang **Targets** và `up` cho biết Prometheus có thực sự đọc được endpoint qua đường mạng của nó hay không. `up=1` nói về lần thu thập thành công, còn việc dịch vụ có đáp ứng đúng nghiệp vụ cần được đo riêng.

**Đẩy.** Mã ứng dụng tiếp tục ghi số đo vào Micrometer. Bộ xuất OTLP gom và gửi các điểm dữ liệu theo nhịp cấu hình. Đích `/v1/metrics` là endpoint nhận OTLP/HTTP, thường dùng cổng `4318`. Với Collector, bộ nhận tiếp nhận payload rồi chuyển qua pipeline metrics đến một hoặc nhiều bộ xuất. Gửi được tới Collector mới xác minh chặng đầu. Muốn khẳng định hệ thống lưu trữ có dữ liệu, cần kiểm tra tiếp chặng từ Collector đến đích cuối.

Một lệnh `Counter.increment()` ghi nhận một lần xảy ra trong bộ đăng ký. Nó không tương ứng với một HTTP request xuất dữ liệu. Độ trễ trước khi nhìn thấy số đo phụ thuộc nhịp thu thập hoặc nhịp xuất, cùng các bước xử lý phía sau.

### So sánh trên cùng ứng dụng Spring Boot 3.3

Ví dụ dành cho môi trường thử nghiệm nơi ứng dụng, Prometheus và OpenTelemetry Collector chạy trực tiếp trên cùng một máy. Ứng dụng web chạy cổng `8080` và có `spring-boot-starter-actuator`. Thêm cả hai registry dưới đây để quan sát hai luồng từ cùng một nguồn số đo. Với Gradle dùng BOM của Spring Boot, thêm hai thư viện phụ thuộc sau.

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
runtimeOnly 'io.micrometer:micrometer-registry-otlp'
```

Cấu hình `application.yml` mở endpoint kéo và đặt địa chỉ đẩy. Hai nhịp đều được đặt 15 giây trong ví dụ để tiện quan sát. Chúng do hai tiến trình khác nhau quản lý và không nhất thiết đồng bộ.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  otlp:
    metrics:
      export:
        url: http://127.0.0.1:4318/v1/metrics
        step: 15s
        resource-attributes:
          "[service.name]": checkout
```

Cấu hình `prometheus.yml` xác định nơi Prometheus đến kéo dữ liệu.

```yaml
scrape_configs:
  - job_name: checkout
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["127.0.0.1:8080"]
```

Cấu hình `otelcol.yaml` cho Collector nhận OTLP/HTTP và ghi chi tiết số đo ra log để dễ kiểm tra. Bộ xuất `debug` trong ví dụ dùng để quan sát đầu vào, còn một pipeline vận hành cần bộ xuất đến nơi lưu trữ phù hợp.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "127.0.0.1:4318"
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [debug]
```

Khởi động Collector với `otelcol --config=otelcol.yaml` và Prometheus với `prometheus --config.file=prometheus.yml` trong hai cửa sổ lệnh, sau đó khởi động ứng dụng. Tên lệnh Collector có thể khác theo bản phân phối, chẳng hạn `otelcol-contrib`. Nếu chuyển các tiến trình sang container riêng, dùng địa chỉ mà tiến trình mở kết nối phân giải và truy cập được. `127.0.0.1` trong mỗi container trỏ về chính container đó.

**Kiểm tra đường kéo.** Đọc endpoint ứng dụng, rồi kiểm tra Prometheus có lấy được dữ liệu theo lịch.

```bash
curl -fsS 'http://127.0.0.1:8080/actuator/prometheus'
curl -fsS -G 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=up{job="checkout"}'
```

Khi ứng dụng đã lên và Prometheus thu thập thành công, kết quả kỳ vọng là `up{job="checkout",instance="127.0.0.1:8080"} = 1`. Có thể tìm họ `jvm_memory_used_bytes` trong nội dung scrape. Giá trị bộ nhớ phụ thuộc tiến trình.

**Kiểm tra đường đẩy.** Đợi Collector nhận dữ liệu sau một hoặc vài kỳ xuất 15 giây. Trong log `debug`, tìm thuộc tính tài nguyên `service.name=checkout` và các điểm metrics JVM. Nếu không thấy dữ liệu, kiểm tra log ứng dụng, cổng OTLP/HTTP, đường dẫn `/v1/metrics` và việc receiver đã được gắn vào `service.pipelines.metrics`. Gọi `GET` tới `/v1/metrics` không kiểm tra được thao tác gửi OTLP, vì bộ nhận chờ `POST` có payload OTLP.

Trong môi trường thử nghiệm, tạm dừng Prometheus nhưng để ứng dụng và Collector chạy. Collector vẫn có thể nhận và ghi log các kỳ xuất mới. Khởi động lại Prometheus, rồi tạm dừng Collector. Sau một lần thu thập thành công, Prometheus vẫn báo `up=1` dù bộ xuất OTLP có thể báo lỗi kết nối. Hai phép thử giúp xác định mỗi luồng phụ thuộc vào bên nào.

### Chọn cơ chế theo môi trường và vòng đời tiến trình

Với dịch vụ chạy lâu, có địa chỉ thu thập mà Prometheus truy cập được và cần theo dõi từng bản sao, cơ chế kéo cho phép quản lý lịch thu thập tập trung và dùng `up` để kiểm tra đích. Nếu dịch vụ chỉ cho phép kết nối đi ra và đã có Collector nhận OTLP, cơ chế đẩy phù hợp với hướng mạng đó. Với cả hai cách, hãy xác định nguồn nào được mong đợi và khoảng thời gian tối đa chấp nhận được trước khi xem dữ liệu là quá cũ.

Nếu bỏ lỡ một lần kéo, mẫu tại thời điểm đó bị thiếu. Lần thu thập tiếp theo có thể thấy giá trị counter đã tăng nếu tiến trình chưa đặt lại counter. Nếu gửi OTLP thất bại, khả năng gửi lại phụ thuộc bộ xuất, bộ đệm và cấu hình. Khi nguồn chạy ngắn hơn chu kỳ thu thập hoặc xuất, cần kiểm tra xem nó có cơ hội được đọc hoặc gửi thành công trước khi thoát. Việc bật một bộ xuất định kỳ tự nó chưa xác nhận dữ liệu đến đích.

Hai ví dụ nhiều chặng thường gặp:

- **Pushgateway.** Tác vụ đẩy số đo sang Pushgateway. Prometheus sau đó kéo từ Pushgateway. Cách này thường dùng để ghi nhận kết quả của tác vụ theo lô ngắn ở cấp dịch vụ. Số đo trong gateway có thể còn sau khi tác vụ kết thúc, nên cần xóa các nhóm số đo đã cũ theo vòng đời của tác vụ. `up` ở chặng kéo phản ánh khả năng đọc gateway. Trong Spring Boot 3.3, cấu hình tự động Pushgateway gắn với registry `micrometer-registry-prometheus-simpleclient` cũ, còn ví dụ trên dùng `micrometer-registry-prometheus`.
- **Prometheus remote write.** Prometheus có thể kéo mẫu từ ứng dụng rồi đẩy các mẫu đã thu thập tới nơi lưu trữ từ xa. `remote_write` thuộc chặng từ Prometheus đi ra. Chặng từ ứng dụng vào Prometheus vẫn dùng lịch kéo nếu cấu hình thu thập là scrape.

Nếu bật đồng thời nhiều registry cho cùng nguồn, kiểm tra các luồng đi tới đâu. Khi hai luồng cùng đến một nơi lưu trữ, cần xác định cách phân biệt hoặc loại trùng trước khi cộng số liệu của chúng.

### Tài liệu tham khảo

- [Spring Boot 3.3 Actuator — xuất metrics bằng OTLP và Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — địa chỉ, nhịp xuất và cấu hình OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp)
- [OpenTelemetry — cấu hình receiver, exporter và pipeline của Collector](https://opentelemetry.io/docs/collector/configuration/)
- [Prometheus — trường hợp dùng Pushgateway](https://prometheus.io/docs/practices/pushing/)
- [Prometheus — giao thức remote write](https://prometheus.io/docs/specs/prw/remote_write_spec/)