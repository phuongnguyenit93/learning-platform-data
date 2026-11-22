# Quản lý endpoint nhận dữ liệu, thông tin xác thực và chu kỳ xuất

## 1. Từ phép đo trong ứng dụng đến dữ liệu trên hệ thống giám sát

Một ứng dụng có thể đã ghi nhận số yêu cầu, thời gian xử lý và bộ nhớ JVM nhưng hệ thống giám sát vẫn chưa có dữ liệu. Việc **đo được** và **chuyển được kết quả đo ra ngoài** là hai phần khác nhau.

Trong Spring Boot Actuator, Micrometer cung cấp mô hình đo lường. Một **meter** là đối tượng biểu diễn phép đo, chẳng hạn bộ đếm; **registry** là thành phần quản lý các meter và kết nối với một hệ thống giám sát. Bài này tập trung vào ba câu hỏi vận hành:

- **Gửi đi đâu?** Địa chỉ nhận phải đúng hệ thống, giao thức, cổng và đường dẫn.
- **Được phép gửi bằng cách nào?** Bên gọi cần thông tin xác thực phù hợp với bên nhận.
- **Bao lâu gửi hoặc lấy một lần?** Chu kỳ phải phù hợp với nhu cầu quan sát và tải của hệ thống.

Trước tiên cần xác định **bên nào chủ động mở kết nối**:

| Mô hình | Bên chủ động | Địa chỉ cần quản lý | Nơi cấu hình chu kỳ |
| --- | --- | --- | --- |
| Đẩy dữ liệu (push), ví dụ Micrometer OTLP | Ứng dụng gửi metrics tới nơi nhận | URL của bộ thu hoặc dịch vụ nhận metrics | Cấu hình bộ xuất trong ứng dụng |
| Kéo dữ liệu (pull), ví dụ Prometheus scrape | Prometheus gọi ứng dụng để đọc metrics | Địa chỉ ứng dụng và đường dẫn xuất metrics | Cấu hình tác vụ thu thập của Prometheus |

OTLP là OpenTelemetry Protocol, giao thức trao đổi dữ liệu quan sát. Bộ thu OpenTelemetry Collector có thể nhận dữ liệu từ ứng dụng rồi chuyển tiếp tới nơi lưu trữ.

```text
Đẩy:
Ứng dụng -> Micrometer OTLP -> bộ thu -> hệ thống lưu trữ

Kéo:
Prometheus -> GET endpoint của ứng dụng -> dữ liệu metrics
```

Với mô hình đẩy, “endpoint nhận dữ liệu” nằm ở phía bộ thu. Với mô hình kéo, endpoint trong ứng dụng **phục vụ dữ liệu cho bên thu thập**. Nhầm chiều kết nối sẽ khiến cả địa chỉ, thông tin xác thực và nơi chỉnh chu kỳ đều bị đặt sai.

Spring Boot hỗ trợ các registry tương ứng và cung cấp endpoint Prometheus khi có điều kiện cấu hình phù hợp. Xem [tài liệu metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 2. Chuẩn bị registry trước khi chỉnh địa chỉ

Các đoạn Gradle dưới đây là phần bổ sung vào một ứng dụng **đã dùng Spring Boot 3.3.x và cơ chế quản lý dependency của Boot**; chúng không phải toàn bộ tệp build độc lập. Dùng JDK 21 cho môi trường học của bài.

Nếu chọn OTLP:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-otlp'
}
```

Nếu chọn Prometheus:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
```

Ứng dụng cần web starter nếu muốn sử dụng các endpoint Actuator qua HTTP. Riêng việc **đẩy OTLP không đòi hỏi mở endpoint Actuator HTTP**.

Không tự chọn phiên bản Micrometer khác với tập dependency của Boot chỉ để sao chép một ví dụ mới hơn. Các tùy chọn của thư viện hiện hành có thể chưa tồn tại trong nhánh đang học.

Registry có trên classpath là điều kiện quan trọng để Boot tự cấu hình bộ xuất. Chỉ thêm một khóa URL vào YAML không thay thế dependency. Nếu chủ động bật nhiều registry, ứng dụng có thể xuất tới nhiều nơi; khi đó phải quản lý từng đường xuất và chi phí tương ứng.

## 3. Cấu hình đúng địa chỉ nhận OTLP

### 3.1. Đọc URL theo từng thành phần

Ví dụ một địa chỉ:

```text
https://metrics-gateway.example.net:443/v1/metrics
|-----| |-------------------------| |-| |---------|
 scheme             host           port    path
```

Tên miền trên chỉ minh họa cấu trúc; phải thay bằng nơi nhận thực tế trước khi chạy.

Cần kiểm tra:

1. **Scheme:** nơi nhận dùng HTTP hay HTTPS?
2. **Host:** tiến trình ứng dụng có phân giải và truy cập được tên này không?
3. **Port:** cổng đó phục vụ giao thức nào?
4. **Path:** địa chỉ đó có thực sự nhận metrics không?
5. **Phạm vi mạng:** địa chỉ này hợp lệ từ máy ứng dụng hay chỉ từ máy người quản trị?

Với đường xuất Micrometer OTLP mặc định trong nhánh 1.13.x, dữ liệu được gửi bằng HTTP POST với nội dung protobuf. URL thường gặp của OTLP/HTTP metrics là `http://localhost:4318/v1/metrics`. Không dùng URL giao diện dashboard hoặc `/actuator/metrics` làm địa chỉ nhận OTLP. Hành vi gửi HTTP được thể hiện trong [mã nguồn OtlpMeterRegistry 1.13.15](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.15/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpMeterRegistry.java).

Cổng 4317 thường được dùng cho OTLP/gRPC, còn 4318 thường được dùng cho OTLP/HTTP. Đây là các cổng mặc định trong [đặc tả OTLP](https://opentelemetry.io/docs/specs/otlp/); hợp đồng thực tế của nơi nhận mới quyết định. Đổi số cổng trong URL không biến bộ gửi HTTP thành bộ gửi gRPC.

Khi khai báo `management.otlp.metrics.export.url`, hãy cung cấp **URL nhận metrics đầy đủ** theo yêu cầu của nơi nhận. Không dựa vào giả định rằng mọi cách cấu hình đều tự thêm `/v1/metrics`.

### 3.2. Cấu hình OTLP cơ sở

Trong `application.yml`:

```yaml
management:
  otlp:
    metrics:
      export:
        enabled: true
        url: "${METRICS_OTLP_URL}"
        headers:
          Authorization: "Bearer ${METRICS_OTLP_TOKEN}"
        step: 30s
        connect-timeout: 2s
        read-timeout: 5s
```

Đây là cấu hình cho **nơi nhận yêu cầu Bearer token**. Tên biến `METRICS_OTLP_URL` và `METRICS_OTLP_TOKEN` do ứng dụng quy ước, rồi tham chiếu qua placeholder của Spring; chúng không phải các biến chuẩn bắt buộc của OTLP.

| Thuộc tính dưới `management.otlp.metrics.export` | Vai trò |
| --- | --- |
| `enabled` | Bật hoặc tắt đường xuất này |
| `url` | Đích nhận metrics |
| `headers` | Các HTTP header nơi nhận yêu cầu |
| `step` | Chu kỳ xuất |
| `connect-timeout` | Thời gian chờ thiết lập kết nối |
| `read-timeout` | Thời gian chờ đọc phản hồi |

Nhánh Boot 3.3 có các thuộc tính này; mặc định tương ứng của `step`, `connect-timeout` và `read-timeout` là `1m`, `1s` và `10s`. Hai timeout không phải cam kết về tổng thời gian hoàn tất toàn bộ một chu kỳ. Đối chiếu [danh mục thuộc tính Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 3.3. Tránh nhầm namespace

Trong Boot 3.3:

```properties
management.otlp.metrics.export.url=https://metrics-gateway.example.net/v1/metrics
```

khác với:

```properties
management.otlp.tracing.endpoint=https://trace-gateway.example.net/v1/traces
```

Một thuộc tính cấu hình metrics; thuộc tính còn lại cấu hình tracing. Chỉ chỉnh tracing không làm đường xuất metrics tự đổi địa chỉ. Tương tự, không sao chép tiền tố `management.metrics.export...` từ ví dụ Boot cũ rồi cho rằng mọi khóa vẫn bind đúng trong Boot 3.3.

### 3.4. Hiểu đúng localhost

`localhost` luôn được diễn giải từ môi trường của **tiến trình đang kết nối**:

- Ứng dụng chạy trực tiếp trên máy: `localhost` là chính máy đó.
- Ứng dụng chạy trong container: `localhost` là container ứng dụng.
- Prometheus chạy trong container: target `localhost:8080` trỏ về container Prometheus, trừ khi có thiết lập mạng đặc biệt.

Nếu ứng dụng và Collector là hai service riêng trong cùng mạng container, địa chỉ có thể là `http://otel-collector:4318/v1/metrics`, với điều kiện `otel-collector` là tên service thật và receiver đã được bật. Việc truy cập thành công từ trình duyệt trên máy cá nhân chưa chứng minh ứng dụng trong container truy cập được.

## 4. Quản lý thông tin xác thực theo đúng chiều kết nối

### 4.1. Phân biệt hai cặp danh tính

Trong đường đẩy:

```text
Ứng dụng -- thông tin xác thực A --> bộ thu
Bộ thu   -- thông tin xác thực B --> hệ thống lưu trữ
```

Token A và token B có thể khác nhau. Cấp quyền gửi vào bộ thu không mặc nhiên cấp quyền truy vấn dashboard hoặc gửi trực tiếp vào dịch vụ lưu trữ.

Trong đường kéo:

```text
Prometheus -- thông tin xác thực --> endpoint metrics của ứng dụng
```

Thông tin xác thực được đặt ở phía Prometheus và được xác minh bởi ứng dụng hoặc cổng bảo vệ trước ứng dụng. Token dùng cho OTLP outbound không bảo vệ endpoint Actuator inbound.

### 4.2. Header phải theo hợp đồng của nơi nhận

Bearer token chỉ là một cơ chế. Nếu nơi nhận yêu cầu API key trong header khác, cấu hình phải phản ánh đúng hợp đồng đó, ví dụ:

```yaml
management:
  otlp:
    metrics:
      export:
        headers:
          X-API-Key: "${METRICS_API_KEY}"
```

Đoạn này là **phương án thay thế cho phần headers**, không phải hướng dẫn gửi đồng thời mọi kiểu xác thực. Không tự thêm tiền tố `Bearer` vào API key nếu nơi nhận yêu cầu giá trị thô. Với cơ chế Basic, mTLS hoặc OAuth2 cần lấy token động, phải dùng cách tích hợp phù hợp; một chuỗi header tĩnh không tự thực hiện quá trình cấp và gia hạn token.

HTTPS bảo vệ dữ liệu trên đường truyền và xác minh máy chủ theo cấu hình tin cậy. Việc có token không làm HTTP thuần trở thành kênh mã hóa. Ngược lại, dùng HTTPS không tự cấp quyền ghi metrics.

### 4.3. Tách cấu hình thông thường khỏi bí mật

Có thể đưa URL và chu kỳ vào cấu hình triển khai. Token nên được cấp qua cơ chế bí mật của môi trường chạy, chẳng hạn secret mount hoặc biến môi trường được hệ thống triển khai cấp.

Với placeholder không có giá trị mặc định:

```yaml
url: "${METRICS_OTLP_URL}"
headers:
  Authorization: "Bearer ${METRICS_OTLP_TOKEN}"
```

môi trường bật exporter phải cung cấp các giá trị cần thiết. Không dùng token dự phòng “cho chạy được” khi thiếu cấu hình. Nếu môi trường không cần xuất metrics, tắt đường xuất bằng cấu hình riêng và bỏ phần xác thực không cần thiết.

Một lựa chọn khác là config tree:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${metrics.otlp.token}"
```

Trong ví dụ Linux/container này, hệ thống triển khai gắn tệp `/run/secrets/metrics.otlp.token`; nội dung tệp là token. Cấu hình không chứa token. Đây là phần thay thế cách cấp token, cần ghép vào cấu hình OTLP đầy đủ. Không đánh dấu import là `optional:` nếu việc thiếu thư mục secret phải được phát hiện ngay. Cơ chế config tree và placeholder được mô tả trong [Externalized Configuration của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Không đặt token vào URL, tag metrics hoặc log kiểm tra cấu hình. Tag sẽ đi theo chuỗi thời gian và có thể được lưu giữ lâu. Không công khai endpoint cấu hình chỉ để xem token đã được bind hay chưa.

### 4.4. Đổi và thu hồi token

Một lần xoay vòng token có thể thực hiện theo trình tự:

1. Tạo token mới với quyền gửi metrics phù hợp cho đúng môi trường.
2. Cập nhật secret mà các instance sẽ đọc.
3. Khởi động lại hoặc triển khai lần lượt các instance nếu ứng dụng không có cơ chế nạp lại đã được kiểm chứng.
4. Kiểm tra việc gửi của từng instance với token mới.
5. Thu hồi token cũ sau khi xác nhận không còn instance sử dụng nó.

Sửa giá trị trong secret store không bảo đảm một exporter đang chạy lập tức dùng giá trị mới. Cấu hình thông thường của Boot được đọc khi ứng dụng khởi tạo; muốn đổi động phải thiết kế và kiểm chứng riêng.

Nếu nơi nhận không cho hai token cùng tồn tại, cần tính đến khoảng gián đoạn thay vì giả định luôn xoay vòng không mất dữ liệu.

## 5. Chọn chu kỳ xuất mà không nhầm với chu kỳ đo

### 5.1. Step điều khiển việc công bố theo chu kỳ

Với OTLP, `step: 30s` yêu cầu registry xuất theo chu kỳ 30 giây. Điều đó không có nghĩa:

- Ứng dụng chỉ ghi nhận sự kiện một lần mỗi 30 giây.
- Mỗi HTTP request nghiệp vụ sẽ gửi ngay một HTTP request OTLP.
- Dashboard chắc chắn cập nhật sau đúng 30 giây.
- Bộ thu phải giữ dữ liệu đúng 30 giây.

Meter tiếp nhận phép đo theo hoạt động của ứng dụng. Lịch xuất chuyển biểu diễn tổng hợp của các phép đo ra ngoài. Với gauge, giá trị được quan sát khi đo/xuất không phải toàn bộ lịch sử biến động giữa hai lần; giảm chu kỳ có thể cho nhiều điểm quan sát hơn nhưng không tái dựng dữ liệu chưa từng được ghi.

OTLP còn có cách biểu diễn tổng cộng dồn hoặc phần tăng theo cửa sổ thời gian, thường gọi là `cumulative` và `delta`. Chu kỳ xuất và cách biểu diễn này liên quan nhưng không phải cùng một cấu hình. Không giả định mọi counter đều bị đặt lại sau mỗi lần gửi; cũng không tự đổi cách biểu diễn khi nơi nhận chưa được kiểm tra tương thích.

Mặc định và cách xác định chu kỳ trong nhánh Micrometer 1.13 được thể hiện ở [OtlpConfig 1.13.15](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.15/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpConfig.java).

### 5.2. Độ trễ nhìn thấy có nhiều thành phần

Có thể hình dung:

```text
Độ trễ quan sát xấp xỉ =
chờ lần xuất/thu thập kế tiếp
+ truyền và xử lý dữ liệu
+ độ trễ nhập dữ liệu của hệ thống lưu trữ
+ chu kỳ truy vấn/làm mới của dashboard
```

Đây là mô hình suy luận, không phải công thức bảo đảm độ trễ. Việc giảm `step` từ 60s xuống 10s sẽ không có nhiều tác dụng nếu dashboard chỉ làm mới mỗi vài phút.

Khi kiểm tra một thay đổi, đợi qua vài chu kỳ hoàn chỉnh và kiểm tra thời gian dữ liệu thực tế. Không kết luận hỏng chỉ vì chưa thấy dữ liệu ngay sau khi ứng dụng vừa khởi động.

### 5.3. Ước lượng tải trước khi giảm chu kỳ

Giả sử một instance gửi một lô dữ liệu cho mỗi chu kỳ và chưa tính gửi lại:

```text
Số lần gửi trong một phút ≈ số instance × 60 / step_tính_bằng_giây
```

Với 400 instance:

| Chu kỳ giả định | Số lần gửi ước tính/phút |
| --- | ---: |
| 60s | 400 |
| 30s | 800 |
| 5s | 4.800 |

Đây là tính toán minh họa theo giả định một lô; thực tế một lần công bố có thể chia thành nhiều yêu cầu nếu số meter lớn. Số chuỗi thời gian, histogram, số tag và kích thước payload còn ảnh hưởng lưu lượng và chi phí. Giảm chu kỳ không giải quyết vấn đề quá nhiều tổ hợp tag.

Cách lựa chọn hợp lý là bắt đầu từ nhu cầu phát hiện sự cố, xem độ phân giải hệ thống lưu trữ hỗ trợ, thử nghiệm với số instance gần thực tế, rồi đo chi phí trước và sau thay đổi. Không có một giá trị tối ưu dùng chung cho mọi ứng dụng.

### 5.4. Timeout và lỗi gửi

`connect-timeout` và `read-timeout` giới hạn những phần chờ mạng; chúng không thay thế `step`. Đặt chu kỳ rất ngắn trong khi việc gửi thường xuyên chậm có thể làm lịch xuất không đáp ứng kỳ vọng.

Không coi registry trong tiến trình ứng dụng là một hàng đợi bền vững. Khi có lỗi mạng hoặc nơi nhận từ chối yêu cầu, phải quan sát lỗi xuất và khoảng trống dữ liệu. Không suy ra rằng mọi lô thất bại sẽ được lưu trên đĩa rồi gửi lại đầy đủ. Nếu yêu cầu chịu gián đoạn cao hơn, cần xem xét bộ thu trung gian có khả năng đệm/gửi lại được cấu hình rõ ràng.

## 6. Quản lý theo môi trường và nhiều instance

Một bảng cấu hình triển khai nên tách rõ các giá trị sau:

| Thành phần | Môi trường phát triển | Môi trường vận hành |
| --- | --- | --- |
| Đích nhận | Bộ thu thử nghiệm, truy cập được từ nơi chạy ứng dụng | Đích được quản lý cho môi trường thật |
| Thông tin xác thực | Danh tính thử nghiệm | Danh tính có quyền gửi đúng phạm vi |
| Chu kỳ | Thuận tiện cho thí nghiệm | Đã đánh giá độ trễ và tải |
| Nhận dạng dữ liệu | Tên dịch vụ/môi trường thử nghiệm | Dịch vụ, môi trường và định danh instance phù hợp |
| Thay đổi cấu hình | Khởi động lại có kiểm soát | Triển khai và kiểm chứng từng đợt |

Không đưa dữ liệu thử nghiệm vào cùng không gian dữ liệu với production chỉ vì hai môi trường có cùng tên ứng dụng. Hãy kiểm tra nơi nhận và metadata nhận dạng theo hệ thống thực tế; tag hoặc resource attribute dùng để phân biệt, không mang bí mật hay mã định danh người dùng.

Đối với ứng dụng nhiều instance:

- Đường đẩy cần xác nhận từng instance có thể kết nối và được cấp quyền.
- Đường kéo cần cấu hình discovery/target để thu thập từng instance. Scrape một địa chỉ cân bằng tải có thể luân phiên đọc các tiến trình khác nhau và làm sai cách hiểu chuỗi thời gian.
- Khi thay đổi chu kỳ, cần biết instance nào đã nhận cấu hình mới; không đánh giá chỉ từ một pod hoặc một dòng log khởi động.

Boot có nhiều nguồn cấu hình. Một giá trị trong YAML có thể bị nguồn có độ ưu tiên cao hơn thay thế. Khi thấy cấu hình “không có tác dụng”, kiểm tra profile, biến môi trường, tham số khởi động và nguồn cấu hình ngoài; chỉ thu thập các giá trị không nhạy cảm cần cho chẩn đoán.

## 7. Với Prometheus, đặt địa chỉ và chu kỳ ở phía thu thập

### 7.1. Ứng dụng phục vụ dữ liệu

Với dependency Prometheus và ứng dụng HTTP, phần cấu hình ứng dụng có thể là:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
```

Ví dụ này cho phép công bố endpoint theo cấu hình exposure; **nó không định nghĩa cơ chế xác thực**. Nếu ứng dụng có Spring Security, cần đối chiếu quy tắc bảo vệ endpoint hiện hữu. Nếu có proxy phía trước, proxy và ứng dụng cần thống nhất đường dẫn và quyền truy cập. Trong môi trường vận hành, chỉ bên giám sát cần được phép đọc.

Mặc định đường dẫn thường dùng là `/actuator/prometheus`, nhưng port, context path và base path tùy cấu hình có thể làm URL thực tế thay đổi. Xem [cơ chế exposure và bảo vệ endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 7.2. Prometheus gọi ứng dụng

Ví dụ `prometheus.yml` dưới đây giả định:

- `orders-mgmt.internal:9443` là địa chỉ HTTPS thực, truy cập được từ tiến trình Prometheus.
- Endpoint đã được bảo vệ bằng Bearer token ở ứng dụng hoặc gateway.
- Tệp token và CA được gắn vào môi trường Prometheus.

```yaml
scrape_configs:
  - job_name: "orders"
    scheme: https
    metrics_path: /actuator/prometheus
    scrape_interval: 30s
    scrape_timeout: 5s
    authorization:
      type: Bearer
      credentials_file: /run/secrets/orders-scrape-token
    tls_config:
      ca_file: /etc/prometheus/certs/internal-ca.pem
    static_configs:
      - targets:
          - "orders-mgmt.internal:9443"
```

Phải thay địa chỉ và tệp theo môi trường thật; đoạn này không tự tạo DNS, chứng chỉ hoặc bộ xác minh token. Tệp `orders-scrape-token` chỉ chứa token; Prometheus thêm kiểu xác thực theo `type`.

Nếu phía server dùng Basic, thay khối `authorization` bằng cơ chế tương ứng:

```yaml
basic_auth:
  username: metrics_reader
  password_file: /run/secrets/orders-scrape-password
```

Không cấu hình đồng thời các cơ chế xác thực xung đột cho cùng tác vụ. `scrape_timeout` không được lớn hơn `scrape_interval`. Các trường địa chỉ, timeout, xác thực và TLS trên được mô tả trong [cấu hình Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

`management.prometheus.metrics.export.step` không điều khiển lịch Prometheus mở kết nối thu thập. Muốn thay tần suất lấy dữ liệu, đổi `scrape_interval` ở Prometheus. Cũng cần phân biệt với `evaluation_interval` dùng cho lịch đánh giá rule, và cơ chế Pushgateway vốn có đường đẩy riêng.

Sau khi sửa `prometheus.yml`, xác thực và nạp lại cấu hình bằng cơ chế vận hành của Prometheus. Việc chỉ sửa tệp không chứng minh tiến trình đã áp dụng cấu hình mới.

## 8. Kiểm chứng theo từng lớp

Không bắt đầu bằng câu hỏi “dashboard có hiện số chưa?”. Hãy lần theo đường đi dữ liệu.

### 8.1. Kiểm tra phép đo tồn tại trong ứng dụng

Nếu cần chẩn đoán cục bộ, có thể tạm cho phép endpoint `metrics` trong môi trường thử nghiệm có kiểm soát:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
```

Giả sử ứng dụng đang phục vụ HTTP cục bộ ở cổng 8080, dùng lệnh sau trên PowerShell có `curl.exe`:

```powershell
curl.exe --fail --silent --show-error http://localhost:8080/actuator/metrics/jvm.memory.used
```

Nếu endpoint được bảo vệ, dùng phương thức xác thực đã thiết lập; ví dụ không tự vô hiệu hóa bảo vệ. Phản hồi thành công phải có dữ liệu của meter `jvm.memory.used`. Các số đo và tag phụ thuộc JVM, vì vậy không có một JSON số liệu cố định dùng cho mọi lần chạy.

Bằng chứng này chỉ xác nhận ứng dụng đang có phép đo và endpoint chẩn đoán trả lời. Nó chưa xác nhận bộ xuất OTLP đã kết nối thành công.

### 8.2. Kiểm chứng đường đẩy OTLP

Thực hiện từ đúng môi trường chạy ứng dụng:

1. Xác nhận registry OTLP có trong runtime classpath và đường xuất được bật.
2. Kiểm tra URL thực tế không nhạy cảm: scheme, host, port, path; kiểm tra DNS và đường mạng.
3. Kiểm tra cấu hình chứng chỉ tin cậy và cơ chế xác thực của nơi nhận.
4. Chờ vài chu kỳ; đọc lỗi xuất ở ứng dụng và trạng thái tiếp nhận của Collector hoặc nơi nhận.
5. Kiểm tra nơi lưu trữ có chuỗi dữ liệu đúng dịch vụ, môi trường, instance và khoảng thời gian.

Không dùng một HTTP GET tới `/v1/metrics` làm phép thử cuối cùng. Đường nhận OTLP cần yêu cầu đúng phương thức và payload; GET có thể bị từ chối dù exporter hợp lệ vẫn gửi được. Ngược lại, HTTP 200 của một trang web tại cùng host không chứng minh đường nhập metrics hoạt động.

Phản hồi chấp nhận ở bộ thu chỉ chứng minh lớp nhận đó đã xử lý yêu cầu theo hợp đồng của nó. Nếu bộ thu còn chuyển tiếp sang nơi khác, cần kiểm tra tiếp đường chuyển tiếp và dữ liệu lưu trữ.

### 8.3. Kiểm chứng đường kéo Prometheus

1. Xác nhận endpoint trả về định dạng metrics, không phải HTML đăng nhập.
2. Kiểm tra target tương ứng trong Prometheus và lỗi thu thập gần nhất.
3. Truy vấn `up{job="orders"}` để xem tình trạng scrape; giá trị 1 cho biết lần thu thập thành công của target, không bảo đảm mọi metric nghiệp vụ đều đúng.
4. Truy vấn một metric mong đợi và đối chiếu nhãn instance cùng timestamp.
5. Đổi `scrape_interval`, nạp lại cấu hình và quan sát khoảng cách mẫu mới.

Nếu chỉ một target thành công nhưng còn nhiều instance, chưa đủ bằng chứng toàn bộ ứng dụng đã được thu thập.

## 9. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Kiểm tra trước | Kết luận cần tránh |
| --- | --- | --- |
| Không phân giải được host | DNS từ môi trường của bên gọi | Token sai |
| Kết nối bị từ chối | Receiver có chạy và lắng nghe đúng cổng không | Cứ tăng read-timeout sẽ hết |
| Kết nối chờ quá lâu | Route, firewall, chính sách mạng, tải nơi nhận | Giảm step là giải pháp |
| Lỗi chứng chỉ TLS | CA, tên máy chủ, thời hạn, đồng hồ hệ thống | Bỏ xác minh TLS để vận hành |
| HTTP 401 | Cơ chế xác thực, token thiếu/hết hạn/sai | Meter chưa được tạo |
| HTTP 403 | Quyền của danh tính, phạm vi hoặc chính sách gateway | Chỉ cần đổi URL |
| HTTP 404 | Path, route proxy, endpoint exposure | Registry chắc chắn không hoạt động |
| HTTP 405 hoặc 415 | Phương thức, giao thức, định dạng payload | Host không tồn tại |
| HTTP 429 | Giới hạn nơi nhận, tần suất và tải tổng | Gửi nhanh hơn để bù |
| HTTP 5xx | Trạng thái nơi nhận và đường chuyển tiếp | Ứng dụng nghiệp vụ chắc chắn lỗi |
| Ứng dụng khởi động bình thường nhưng không có dữ liệu ngoài | Exporter, log xuất, receiver và nơi lưu trữ | Khởi động thành công đồng nghĩa xuất thành công |
| Có dữ liệu nhưng thấy chậm | Chu kỳ xuất/scrape, hàng đợi xử lý, ingest và dashboard | Chỉ có một nút step quyết định độ trễ |

Mã HTTP có thể do proxy/gateway trả về; cần xác định thành phần tạo phản hồi trước khi kết luận. Một lỗi xuất metrics thường cần được xử lý riêng với trạng thái phục vụ nghiệp vụ. Không mặc định endpoint health chuẩn đã phản ánh khả năng gửi metrics.

## 10. Thực hành có kiểm soát

Trên môi trường thử nghiệm, chọn một đường xuất và ghi lại bằng chứng trước/sau cho ba thay đổi:

1. **Địa chỉ:** dùng URL đúng, rồi cố ý đổi path sang một path không nhận metrics. Quan sát lỗi, khôi phục URL và xác nhận dữ liệu mới xuất hiện.
2. **Xác thực:** khi nơi nhận đã yêu cầu xác thực, thử danh tính không hợp lệ rồi khôi phục secret đúng. Phân biệt bị từ chối xác thực với bị từ chối quyền; không in token vào báo cáo.
3. **Chu kỳ:** đổi OTLP step từ 30s sang 10s, hoặc đổi Prometheus scrape_interval từ 30s sang 10s. Áp dụng cấu hình bằng đúng cơ chế rồi quan sát vài chu kỳ.

Với đường đẩy, dùng thời điểm nhận ở Collector; với đường kéo, dùng dữ liệu scrape của Prometheus. Không đếm số lần dashboard vẽ lại để suy ra số lần truyền metrics.

Sau mỗi thay đổi, chỉ chuyển sang phép thử tiếp theo khi đã khôi phục cấu hình hoạt động. So sánh các yếu tố: lỗi kết nối, kết quả xác thực, khoảng cách dữ liệu, số lần truyền và dữ liệu tới nơi lưu trữ.

Tự kiểm tra khả năng giải thích:

- Vì sao ứng dụng gọi Collector được từ máy cá nhân nhưng thất bại khi chạy trong container?
- Vì sao đổi `management.otlp.tracing.endpoint` không sửa được lỗi gửi metrics?
- Vì sao đã có token vẫn cần kiểm tra quyền và TLS?
- Muốn Prometheus lấy mỗi 10 giây thì cần đổi cấu hình ở tiến trình nào?
- Vì sao giảm chu kỳ xuất chưa chắc làm dashboard cập nhật nhanh hơn?
- Những bằng chứng nào cần có trước khi kết luận đường xuất metrics của mọi instance đã hoạt động?

Một cấu hình hoàn chỉnh cần thống nhất **địa chỉ đúng, danh tính đúng, chu kỳ phù hợp và bằng chứng dữ liệu đi hết đường**. Hãy quản lý chúng theo từng môi trường và kiểm chứng sau mỗi lần thay đổi.
