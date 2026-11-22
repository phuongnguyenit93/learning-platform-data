# Kiểm soát chi phí tag, histogram, trace sampling và tần suất probe

## 1. Chi phí quan sát hệ thống phát sinh từ đâu?

Một ứng dụng có thể xử lý tốt nghiệp vụ nhưng tốn nhiều tài nguyên chỉ để ghi nhận, xuất và lưu số liệu vận hành. Chi phí này không nằm ở một nơi duy nhất:

- **Trong ứng dụng:** bộ nhớ lưu meter, cập nhật bộ đếm/bucket, tạo thông tin trace, chạy health check và dựng phản hồi.
- **Trên đường truyền:** dữ liệu scrape, span được gửi và các lần kiểm tra từ bên ngoài.
- **Trong hệ thống quan sát:** tiếp nhận, lập chỉ mục, lưu giữ và truy vấn dữ liệu.
- **Trong vận hành:** duy trì cấu hình, tìm sự cố giữa quá nhiều dữ liệu hoặc thiếu dữ liệu cần thiết.

Mục tiêu là **giữ đủ thông tin để phát hiện và điều tra sự cố với chi phí đã kiểm soát**. Giảm số liệu đến mức dashboard không còn phản ánh đúng dịch vụ không phải là một kết quả tốt.

Bốn cơ chế trong bài tác động lên những phần khác nhau:

| Cơ chế | Đại lượng cần kiểm soát | Khi điều chỉnh sai có thể mất gì? |
| --- | --- | --- |
| Tag của metric | Số tổ hợp nhãn và tốc độ tạo tổ hợp mới | Phân nhóm hữu ích hoặc toàn bộ metric vượt giới hạn |
| Histogram | Số bucket, số meter có histogram và bộ nhớ thống kê | Độ phân giải của phân bố độ trễ |
| Trace sampling | Số trace/span được ghi nhận và xuất | Chi tiết đường đi của một yêu cầu cụ thể |
| Tần suất probe | Số lần kiểm tra và chi phí mỗi lần | Tốc độ phát hiện trạng thái không phục vụ được |

Bài này dùng cấu hình **Spring Boot 3.3.x**. Các giá trị ngưỡng, tỷ lệ và chu kỳ là ví dụ thiết kế, cần đo trên dịch vụ thực tế trước khi áp dụng.

## 2. Lập một mô hình chi phí trước khi thay cấu hình

### 2.1. Đếm tổ hợp nhãn, không chỉ đếm tên metric

Một tên metric có thể tương ứng với rất nhiều chuỗi thời gian. Ví dụ, bộ đếm yêu cầu HTTP có các nhãn route, method, status và instance.

Giả sử có:

- 40 mẫu route.
- 4 phương thức HTTP.
- 5 giá trị status thực sự được dùng trong mô hình.
- 6 instance.
- Mỗi tổ hợp xuất một histogram cổ điển với 20 bucket hữu hạn.

Số tổ hợp tối đa theo giả định:

```text
Tổ hợp nhãn = 40 × 4 × 5 × 6 = 4.800
```

Mỗi tổ hợp histogram có các bucket hữu hạn, bucket +Inf, sum và count. Với B bucket hữu hạn, phần đó có B + 3 chuỗi. [Cấu trúc histogram Prometheus](https://prometheus.io/docs/practices/histograms/)

Do đó:

```text
Chuỗi của phần histogram = 4.800 × (20 + 3) = 110.400
```

Đây là mô hình cho những tổ hợp được giả định tồn tại, không phải mọi hệ thống đều sinh đủ tích Descartes. Nếu có thêm nhãn exception, region hoặc tên đối tác, phải tính các tổ hợp thực tế của chúng.

Con số cũng chưa bao gồm các chuỗi bổ sung như max của timer, các meter khác, dữ liệu scrape và bản sao lưu của hệ thống quan sát. Timer có thể xuất thêm thống kê tùy backend. [Timer của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

### 2.2. Tần suất thu thập nhân tiếp vào số mẫu

Nếu 110.400 chuỗi đang hoạt động đều được scrape mỗi 15 giây:

```text
Mẫu/giây ≈ 110.400 / 15 = 7.360
Mẫu/ngày ≈ 7.360 × 86.400 = 635.904.000
```

Đó là số mẫu lý thuyết trong một ngày ổn định. Không đổi trực tiếp số mẫu này thành một số tiền hay dung lượng đĩa cố định: định dạng, nén, chỉ mục, retention, replication và cách tính phí khác nhau.

Thời gian lưu giữ dài hơn làm tăng lượng dữ liệu cần lưu. Prometheus mô tả các yếu tố dung lượng và lưu giữ trong tài liệu storage. [Lưu trữ Prometheus](https://prometheus.io/docs/prometheus/latest/storage/)

Ngoài số chuỗi đang hoạt động, theo dõi **tốc độ xuất hiện chuỗi mới**. Một nhãn chỉ có ít giá trị tại một thời điểm nhưng đổi liên tục theo phiên triển khai vẫn có thể làm số chuỗi lịch sử tăng nhanh.

## 3. Kiểm soát tag ngay tại nơi tạo metric

### 3.1. Chọn nhãn theo câu hỏi cần trả lời

Tag trong Micrometer thường được xuất thành label ở Prometheus. Mỗi tổ hợp nhãn tạo một chuỗi riêng. [Quy ước nhãn Prometheus](https://prometheus.io/docs/practices/naming/)

Trước khi thêm một tag, trả lời:

1. Dashboard hoặc cảnh báo nào cần phân nhóm bằng tag này?
2. Có bao nhiêu giá trị khác nhau?
3. Giá trị có tăng theo người dùng, yêu cầu hoặc thời gian không?
4. Có dữ liệu nhạy cảm hay định danh cá nhân không?
5. Có thể trả lời câu hỏi đó bằng log/trace của một yêu cầu thay vì metric không?

| Giá trị dự kiến | Quyết định thường phù hợp |
| --- | --- |
| Phương thức HTTP, nhóm kết quả hữu hạn | Dùng khi cần phân nhóm |
| Mẫu route như /orders/{id} | Phù hợp hơn từng mã đơn hàng |
| Môi trường, vùng triển khai có tập giá trị quản lý được | Cân nhắc theo phạm vi vận hành |
| userId, orderId, requestId, traceId | Không dùng làm nhãn metric theo từng thực thể |
| Chuỗi truy vấn URL hoặc nội dung lỗi tự do | Chuẩn hóa hoặc bỏ khỏi nhãn |
| Phiên bản phát hành | Chỉ dùng khi có nhu cầu; đánh giá số phiên bản và chuỗi lịch sử |

Một nhãn có 10.000 giá trị thường nguy hiểm hơn một nhãn có ba giá trị, nhưng không thể đánh giá tag riêng lẻ mà bỏ qua phép nhân với những tag còn lại.

Không chuyển requestId thành tên metric động. Việc đổi từ nhãn động sang tên động vẫn tạo lượng meter không giới hạn.

### 3.2. Chuẩn hóa thành tập hữu hạn

Với API có đường dẫn như:

```text
/orders/18401
/orders/18402
/orders/18403
```

Mục tiêu là một mẫu route:

```text
/orders/{id}
```

Nếu tự ghi metric, lấy giá trị từ một tập đã xác định, ví dụ channel chỉ có web, mobile, partner. Đừng gán trực tiếp header do bên ngoài gửi vào làm channel.

Nếu cần một nhóm OTHER, phải quy định từ đầu ý nghĩa nhóm và cách ánh xạ. Cắt ngắn chuỗi, băm ID hoặc lấy vài ký tự đầu không tự làm số giá trị trở thành hữu hạn.

Nhãn dạng common tag được thêm vào nhiều meter, nên một nhãn tăng không giới hạn ở đó có phạm vi ảnh hưởng rộng. Thêm nhãn vào mọi meter chỉ vì có sẵn dữ liệu là một lựa chọn cần tránh.

### 3.3. Dùng giới hạn như một hàng bảo vệ

Spring Boot 3.3 có giới hạn số giá trị URI cho số liệu HTTP:

```yaml
management:
  metrics:
    web:
      server:
        max-uri-tags: 100
      client:
        max-uri-tags: 100
```

Trong phiên bản này, mặc định của hai thuộc tính là 100; ví dụ ghi rõ để thể hiện chính sách. Khi vượt giới hạn, metric có giá trị URI mới bị từ chối bởi filter. [Thuộc tính URI tag của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Phải hiểu đúng hệ quả:

- Nó không giới hạn số yêu cầu HTTP mà ứng dụng được nhận.
- Nó không tự gom mọi URI còn lại thành một nhóm OTHER.
- Nó không giới hạn tag khác như customerId hoặc partner.
- Việc bớt metric sau khi chạm trần có thể khiến tổng lưu lượng hoặc lỗi trên dashboard bị thiếu.

Ưu tiên sửa nguồn sinh nhãn. Khi chạm giới hạn, cần có cách phát hiện qua cảnh báo/log được thư viện cung cấp hoặc phép đối chiếu có chủ đích với số liệu tại gateway và nguồn độc lập. Không mặc định mọi phiên bản đều có một counter riêng đếm số meter bị từ chối.

### 3.4. Giới hạn tag cho metric tự định nghĩa

Ví dụ sau là lớp cấu hình bổ sung trong ứng dụng Spring Boot có Micrometer; nó không phải chương trình Java độc lập:

```java
package example.observability;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricTagBudgetConfiguration {
    @Bean
    MeterFilter checkoutChannelLimit() {
        return MeterFilter.maximumAllowableTags(
                "checkout.operations",
                "channel",
                3,
                MeterFilter.deny());
    }
}
```

Filter áp dụng cho tên meter có tiền tố tương ứng. Nếu chỉ muốn ba giá trị channel đã được phê duyệt, vẫn cần kiểm tra giá trị trước khi ghi; giới hạn số lượng không phải danh sách cho phép theo tên.

Với nhánh deny, Micrometer dùng meter không ghi nhận dữ liệu cho đăng ký bị từ chối. [MeterFilter và cơ chế deny](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)

Đăng ký filter trước khi các meter liên quan được tạo. Không coi việc thêm filter muộn là cách sửa hoàn toàn số liệu và bộ nhớ đã phát sinh. Khi giảm tag, kiểm tra cả phép gộp và ý nghĩa số đo; việc xóa nhãn của hai gauge khác nhau không tự tạo một tổng gauge đúng.

## 4. Chọn histogram theo quyết định cần đưa ra

### 4.1. Có cần toàn bộ đường phân bố hay chỉ vài mốc SLO?

Hai nhu cầu khác nhau:

- Cần khảo sát p95/p99 trong một khoảng độ trễ đủ rộng.
- Chỉ cần biết tỷ lệ yêu cầu đáp ứng các mốc như 100 ms, 300 ms, 1 s.

Không nhất thiết phải bật cùng một số bucket cho mọi timer. Chọn những meter ảnh hưởng tới trải nghiệm hoặc mục tiêu vận hành.

Micrometer phân biệt histogram có thể gộp bucket với percentile tính sẵn tại từng meter; percentile tính sẵn không gộp được bằng trung bình cộng giữa các instance. [Histogram và percentile Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)

### 4.2. Phương án A: cần histogram để khảo sát percentile

Đây là cấu hình bổ sung cho Spring Boot 3.3:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      minimum-expected-value:
        "http.server.requests": 5ms
      maximum-expected-value:
        "http.server.requests": 5s
      slo:
        "http.server.requests": 100ms,300ms,1s
```

Khoảng expected value giới hạn phạm vi bucket tự sinh và ảnh hưởng tài nguyên thống kê. Các mốc SLO có thể bổ sung bucket cần thiết. Không coi 5 s là timeout của yêu cầu hoặc lệnh cắt mọi thời gian xử lý lớn hơn 5 s. [Cấu hình distribution của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties)

Đo bucket thực tế trong endpoint sau khi cấu hình; không lấy số bucket mặc định của một phiên bản khác làm kết quả chắc chắn.

### 4.3. Phương án B: chỉ giữ các mốc SLO cần thiết

Phương án này **thay thế phương án A**, không ghép hai khối YAML trùng khóa:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "http.server.requests": false
      slo:
        "http.server.requests": 100ms,300ms,1s
```

Trong mô hình histogram Prometheus đang xét, vẫn có bucket SLO dù không bật bộ bucket percentile tự sinh. Không diễn giải percentiles-histogram=false thành “không còn bucket nào”. [Bucket do service level objectives tạo ra](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)

Với ba bucket hữu hạn, phần histogram của ví dụ 4.800 tổ hợp là:

```text
4.800 × (3 + 3) = 28.800 chuỗi
28.800 / 15 × 86.400 = 165.888.000 mẫu/ngày
```

So với 110.400 chuỗi ban đầu, phần mô hình này giảm khoảng 73,9%. Đây không phải lời hứa tổng hệ thống giảm đúng 73,9%: còn các meter và chi phí khác.

Đổi lại, phân bố ít bucket có độ phân giải thấp hơn. Không tiếp tục trình bày p99 như thể vẫn có cùng độ chính xác; cập nhật dashboard và phép nghiệm thu tương ứng.

### 4.4. Những thao tác không thay thế cho nhau

- Giảm trace sampling không làm ít bucket metric hơn.
- Giảm số bucket không giảm số tổ hợp nhãn của count/sum.
- Giảm tần suất scrape không làm mất chi phí cập nhật histogram trong từng yêu cầu.
- Bỏ chuỗi ở Prometheus không tự xóa meter và bộ nhớ thống kê trong JVM.
- Giảm thời gian lưu giữ ở backend không chữa được nhãn không giới hạn tại ứng dụng.

Giảm chi phí ở lớp nào thì phải đo kết quả ở lớp đó.

## 5. Trace sampling: giảm dữ liệu nhưng hiểu thông tin bị bỏ

### 5.1. Tỷ lệ sampling là một quyết định xác suất

Với hệ thống tracing đã có bridge, exporter và backend phù hợp, cấu hình:

```yaml
management:
  tracing:
    sampling:
      probability: 0.02
```

Spring Boot 3.3 mặc định dùng tỷ lệ 0,1; giá trị trên chọn tỷ lệ 0,02 cho sampling do cấu hình tương ứng điều khiển. Chỉ thêm thuộc tính không tự cài toàn bộ hệ thống tracing. [Tracing của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)

Không hiểu 2% là cứ đúng 100 yêu cầu thì có chính xác hai trace, cũng không hiểu đó là trần cố định số span mỗi giây.

Trong triển khai OpenTelemetry mặc định của Spring Boot 3.3, sampler cho trace gốc dựa trên tỷ lệ và được bọc bằng parent-based sampler. Ngữ cảnh cha đã có quyết định sampling ảnh hưởng đến quyết định của span con. [Mã cấu hình sampler Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/OpenTelemetryAutoConfiguration.java)

Vì vậy, đặt tỷ lệ thấp tại một dịch vụ phía sau không nhất thiết giảm các trace đã được chọn từ phía trước. Kiểm tra cả nơi tạo trace gốc, propagation, sampler tùy biến và cấu hình agent nếu có.

### 5.2. Ước lượng lượng span và dữ liệu

Giả sử tại nơi tạo trace gốc có:

```text
Lưu lượng = 2.000 yêu cầu/giây
Tỷ lệ chọn = 0,02
Trung bình = 8 span/trace được chọn
Trung bình = 500 byte/span trong mô hình
```

Ước lượng:

```text
Trace được chọn/giây ≈ 2.000 × 0,02 = 40
Span/giây ≈ 40 × 8 = 320
Dữ liệu/giây ≈ 320 × 500 = 160.000 byte
Dữ liệu/ngày ≈ 13.824.000.000 byte ≈ 13,824 GB
```

GB ở đây là 10^9 byte. Mô hình chưa tính nén, giao thức, retry, indexing, replication hoặc khác biệt số span giữa trace nhanh và trace lỗi.

Phải đo riêng kích thước span và số span mỗi trace. Lưu lượng không tăng nhưng một thư viện mới tạo thêm nhiều span vẫn có thể làm tổng dữ liệu tăng.

Tỷ lệ sampling không đồng nghĩa với phần trăm CPU giảm tương ứng. Một phần chi phí quan sát, truyền ngữ cảnh hoặc cập nhật metric vẫn còn.

### 5.3. Head sampling không bảo đảm giữ lỗi hiếm

Head sampling quyết định sớm, trước khi biết đầy đủ kết quả của trace. Nó không thể một mình bảo đảm giữ mọi trace lỗi xảy ra về sau. [Head sampling và giới hạn của nó](https://opentelemetry.io/docs/concepts/sampling/#head-sampling)

Giả sử có 10 trace lỗi riêng biệt và mỗi trace được chọn độc lập với xác suất 2%. Khả năng giữ được ít nhất một trace lỗi là:

```text
1 - (1 - 0,02)^10 ≈ 18,3%
```

Đây là minh họa theo giả định xác suất, không dự báo chắc chắn cho mọi sampler. Nó cho thấy giảm tỷ lệ mạnh có thể làm mất bằng chứng điều tra lỗi hiếm.

Metric lỗi vẫn cần đếm đầy đủ theo phạm vi đã xác định; không lấy số trace lỗi được giữ làm tổng số lỗi của hệ thống. Nếu metric cũng đang bị filter bỏ do tag vượt giới hạn, phải xử lý vấn đề đó riêng.

### 5.4. Khi cần quyết định sau khi có kết quả

Tail sampling xem dữ liệu trace đã được thu thập để chọn theo các điều kiện như lỗi hoặc độ trễ. Nó đổi bài toán chi phí: cần nhận dữ liệu, giữ trạng thái và chờ quyết định. [Tail sampling của OpenTelemetry](https://opentelemetry.io/docs/concepts/sampling/#tail-sampling)

Các span của một trace phải đến đúng nơi ra quyết định; cấu hình chờ, khả năng giữ trace và xử lý span đến muộn ảnh hưởng kết quả. [Tail sampling processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md)

Không thể khôi phục những span đã bị bỏ trước đó tại ứng dụng. Nếu đầu nguồn chỉ tạo/xuất 2% trace, tầng sau không thể bảo đảm giữ 100% lỗi của toàn hệ thống.

Chính sách hợp lý cần ghi rõ:

- Sampling ở đâu và áp dụng cho trace gốc hay trace đã có cha.
- Có ưu tiên lỗi, yêu cầu chậm hoặc dịch vụ ít lưu lượng không.
- Ngân sách span/giây, byte/giây và hàng đợi.
- Cách theo dõi dữ liệu bị từ chối, exporter lỗi hoặc queue đầy.
- Cách tăng thu thập có thời hạn khi điều tra và cách hoàn nguyên.

Không đưa ID người dùng thành tag metric để bù trace bị thiếu. Thuộc tính trace và log cũng cần giới hạn kích thước, dữ liệu nhạy cảm và chi phí truy vấn.

## 6. Tần suất probe: kiểm tra sức khỏe cũng là một dạng tải

### 6.1. Đếm mọi nơi đang gọi kiểm tra

Một dịch vụ có thể đồng thời được kiểm tra bởi kubelet, load balancer, hệ thống uptime, bộ kiểm tra triển khai và công cụ của người vận hành.

Ước lượng nhịp gọi khi hệ thống ổn định:

```text
QPS probe ≈ số instance × tổng(1 / chu kỳ của từng loại probe)
```

Ví dụ có 120 instance, liveness mỗi 10 giây và readiness mỗi 5 giây:

```text
120 × (1/10 + 1/5) = 36 lần kiểm tra/giây
36 × 86.400 = 3.110.400 lần/ngày
```

Chưa tính startup, nguồn kiểm tra khác hoặc nhịp gọi thay đổi khi chưa sẵn sàng. Đây là ước lượng để lập ngân sách; cần đo tần suất thực tế.

Nếu mỗi lần kiểm tra giữ một kết nối cơ sở dữ liệu trong 40 ms, mô hình trên tương ứng trung bình khoảng 1,44 kết nối đang phục vụ probe trên toàn hệ thống. Đó là lượng thời gian chiếm kết nối, không phải 1,44 giây CPU mỗi giây.

Giảm chi phí mỗi lần kiểm tra đôi khi hiệu quả hơn chỉ kéo dài chu kỳ.

### 6.2. Giữ đúng ý nghĩa liveness và readiness

Liveness hỗ trợ quyết định khởi động lại; readiness hỗ trợ quyết định có tiếp tục gửi lưu lượng tới container hay không. Startup probe dành cho giai đoạn khởi động. [Các loại probe Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)

Trong Spring Boot, không đưa hệ thống ngoài vào liveness. Một cơ sở dữ liệu dùng chung bị lỗi không phải lý do để mọi bản sao đồng loạt khởi động lại. Việc đưa hệ thống ngoài vào readiness cần quyết định theo khả năng phục vụ và cơ chế dự phòng của dịch vụ. [Phạm vi health probe Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

Cấu hình ví dụ chỉ dùng trạng thái availability nội bộ cho hai nhóm:

```yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: [livenessState]
        readiness:
          include: [readinessState]
```

Additional paths đưa các nhóm ra `/livez` và `/readyz` trên cổng ứng dụng. [Đường dẫn probe Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Ví dụ này không chứng minh ứng dụng vẫn phục vụ mọi chức năng khi một hệ thống phụ thuộc lỗi. Cần có quan sát lỗi nghiệp vụ và chính sách readiness phù hợp; không đổi health thành luôn UP để giảm tải kiểm tra.

Nếu đã có health group bổ sung, rà soát ý nghĩa trước khi thay danh sách include. Thay bằng cấu hình mẫu một cách máy móc có thể bỏ mất điều kiện đang cần.

### 6.3. Chọn chu kỳ cùng ngưỡng phát hiện

Đoạn dưới nằm trong một phần tử containers[] của manifest Kubernetes, giả định cổng ứng dụng 8080 và các đường dẫn probe đã được phép gọi:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 2
```

periodSeconds, timeoutSeconds và failureThreshold phải được xét cùng nhau. Startup probe trì hoãn việc chạy liveness/readiness cho đến khi kiểm tra khởi động thành công. [Cấu hình probe Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Với 120 instance, hai probe ổn định trong cấu hình này có nhịp danh nghĩa:

```text
120 × (1/10 + 1/10) = 24 lần/giây
```

So với 36 lần/giây, giảm khoảng một phần ba. Đổi lại, một số thay đổi readiness có thể được phát hiện chậm hơn. Phải nghiệm thu thời gian ngừng nhận lưu lượng khi ứng dụng không sẵn sàng.

Không lấy phép nhân chu kỳ × số lần thất bại làm một cam kết thời gian chính xác. Thời điểm lỗi xuất hiện trong chu kỳ, timeout và lịch thực thi đều ảnh hưởng; readiness khi chưa sẵn sàng còn có thể được kiểm tra thường hơn chu kỳ danh nghĩa.

### 6.4. Giới hạn chi phí trong một lần kiểm tra

Health check nên có công việc nhỏ, có giới hạn, không tạo side effect nghiệp vụ và không thực hiện toàn bộ giao dịch của người dùng.

Nếu phải gọi hệ thống ngoài, đặt timeout ở client thực hiện lời gọi đó. Timeout của bên gọi probe không bảo đảm mọi công việc phía server đã tự bị hủy.

Thuộc tính slow-indicator-threshold của Spring Boot là ngưỡng ghi cảnh báo khi indicator chậm, không phải timeout để hủy indicator. [Cảnh báo health indicator chậm](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

Chỉ cache kết quả khi đã định nghĩa độ cũ được chấp nhận và kiểm thử thời gian phản ánh lỗi. Không cache tùy ý trạng thái sống/sẵn sàng chỉ để làm biểu đồ chi phí đẹp hơn.

## 7. Tách nhịp scrape khỏi nhịp probe

Probe dẫn tới quyết định điều phối; scrape lấy số liệu phục vụ quan sát. Chúng có thể cùng đi qua HTTP nhưng không thay thế nhau.

Nếu tăng scrape interval từ 15 lên 60 giây, lượng mẫu của một tập chuỗi ổn định giảm xấp xỉ bốn lần. Tuy nhiên:

- Meter vẫn được cập nhật trong ứng dụng theo hoạt động phát sinh.
- Gauge có thể bỏ lỡ những đỉnh ngắn nằm giữa hai lần lấy mẫu.
- Truy vấn rate cần cửa sổ có đủ số mẫu.
- Cảnh báo và dashboard phải được kiểm thử lại với nhịp dữ liệu mới.
- Nhịp liveness/readiness không tự đổi theo scrape interval.

Tương tự, giảm nhịp probe không làm ít span hoặc ít chuỗi metric hơn. Đừng dùng một nút điều chỉnh để giải quyết chi phí ở lớp khác.

Nếu dùng metric relabeling để bỏ dữ liệu tại Prometheus, dữ liệu đã được lấy từ ứng dụng trước khi bị loại ở bước ingestion. Nó có thể giảm lượng lưu ở backend nhưng không loại hết công việc tạo và truyền phản hồi. [Vị trí của metric relabeling](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#metric_relabel_configs)

Không xóa nhãn một cách mù quáng ở tầng sau: phải bảo đảm các chuỗi vẫn có định danh và ý nghĩa đúng sau biến đổi. Đặt giới hạn ingestion cũng cần có cách báo khi scrape thất bại, thay vì coi đó là cơ chế lấy một phần dữ liệu an toàn.

## 8. Đo trước và sau bằng dữ liệu thực tế

### 8.1. Theo dõi số chuỗi và chi phí scrape

Ví dụ các truy vấn sau giả định job orders có nhãn môi trường prod ở target; thay bằng nhãn đã xác minh của hệ thống:

```promql
sum(scrape_samples_scraped{job="orders", environment="prod"})
```

```promql
sum(scrape_samples_post_metric_relabeling{job="orders", environment="prod"})
```

```promql
scrape_duration_seconds{job="orders", environment="prod"}
```

Đây là các chuỗi Prometheus tạo cho mỗi target scrape. [Số liệu scrape tự sinh](https://prometheus.io/docs/concepts/jobs_instances/)

Để xem những tên metric có nhiều chuỗi nhất trong phạm vi đó:

```promql
topk(
  10,
  count by (__name__) (
    {job="orders", environment="prod"}
  )
)
```

Để kiểm tra số giá trị URI hiện có của count HTTP:

```promql
count(
  count by (uri) (
    http_server_requests_seconds_count{
      job="orders",
      environment="prod"
    }
  )
)
```

Truy vấn quan sát số chuỗi cũng có chi phí. Chạy trong phạm vi hẹp, không đặt một truy vấn quét toàn bộ hệ thống làm panel tự làm mới quá nhanh.

Số chuỗi đã ingest không cho biết chính xác số meter hay bộ nhớ JVM. Khi cần, đo thêm heap, CPU ứng dụng và thống kê registry bằng công cụ phù hợp. Số mẫu sau relabeling giảm nhưng phản hồi scrape vẫn lớn là tín hiệu chi phí mới chỉ giảm ở tầng sau.

### 8.2. Theo dõi trace và probe ngoài các con số cấu hình

Với tracing, đo số span được tạo/xuất/nhận, byte truyền, queue, retry và dữ liệu bị bỏ. Tên metric cụ thể phụ thuộc exporter/collector; đọc dữ liệu thực tế thay vì giả định mọi thư viện có cùng tên.

Với probe, đo số lần gọi, thời gian xử lý, timeout, trạng thái chuyển đổi và lượng restart. Dùng số liệu HTTP hoặc access log thích hợp; nếu health request không đi qua instrumentation đang dùng, bổ sung nguồn đo phù hợp.

Phân biệt bốn loại mất dữ liệu:

1. Không được chọn bởi sampling có chủ đích.
2. Meter bị từ chối do giới hạn tag.
3. Queue/exporter/collector làm rơi dữ liệu ngoài ý muốn.
4. Scrape hoặc ingestion thất bại.

Bốn loại này có ý nghĩa khác nhau. Chỉ nhìn số lượng dữ liệu giảm không đủ để biết hệ thống đã tối ưu thành công.

## 9. Quy trình thay đổi và bài thực hành

### 9.1. Thay một yếu tố và có tiêu chí hoàn nguyên

1. Ghi mức tải, số instance, cấu hình và khoảng đo ban đầu.
2. Đặt câu hỏi cần trả lời và mức dữ liệu tối thiểu phải giữ.
3. Chọn một thay đổi: chuẩn hóa tag, đổi bucket, đổi sampling hoặc đổi probe.
4. Thử ở môi trường phù hợp với cùng dạng tải.
5. So sánh chi phí tại ứng dụng, đường truyền và backend.
6. Gây tình huống lỗi có kiểm soát để kiểm tra khả năng phát hiện/điều tra.
7. Triển khai có giới hạn, theo dõi và hoàn nguyên nếu mất tín hiệu cần thiết.

Không so “trước” ở giờ cao điểm với “sau” ở giờ ít tải rồi quy mọi chênh lệch cho cấu hình mới. Khi chuẩn hóa theo yêu cầu hoặc instance, vẫn giữ số tuyệt đối để không bỏ qua một cuộc tăng tải thực sự.

### 9.2. Tiêu chí nghiệm thu cho từng thay đổi

| Thay đổi | Bằng chứng chi phí | Bằng chứng vẫn quan sát được |
| --- | --- | --- |
| Chuẩn hóa URI | Số giá trị URI/chuỗi mới giảm | Các API quan trọng vẫn có count, lỗi và độ trễ |
| Giảm bucket | Số bucket và mẫu scrape giảm | Các mốc SLO vẫn truy vấn được; mức phân giải mới được ghi rõ |
| Giảm sampling | Span/byte giảm theo mô hình thực tế | Trace liên dịch vụ còn nhất quán; giới hạn điều tra lỗi hiếm được chấp nhận |
| Đổi chu kỳ probe | Số lần gọi và chi phí kiểm tra giảm | Thời gian rút khỏi phục vụ và phát hiện treo vẫn đạt yêu cầu |
| Bỏ dữ liệu ở backend | Lượng ingest/lưu giảm | Không làm mất cảnh báo hoặc tạo xung đột chuỗi sau biến đổi |

### 9.3. Bài thực hành có kết quả kiểm chứng được

Một dịch vụ có 40 route, 4 method, 5 status và 6 instance; giả sử có đủ các tổ hợp. Nó đang xuất 20 bucket hữu hạn, scrape mỗi 15 giây. Hệ thống tạo 2.000 trace gốc/giây, chọn 2%, trung bình 8 span/trace và 500 byte/span. Cụm có 120 instance, liveness 10 giây và readiness 5 giây.

Hãy lập bảng ngân sách và kiểm tra các kết quả:

- 4.800 tổ hợp nhãn.
- 110.400 chuỗi cho phần histogram đã mô hình hóa.
- 635.904.000 mẫu/ngày của phần đó.
- Nếu chuyển thành ba bucket hữu hạn: 28.800 chuỗi, 165.888.000 mẫu/ngày.
- Khoảng 320 span/giây, tương ứng 13,824 GB/ngày trong giả định kích thước.
- Nhịp probe danh nghĩa 36 lần/giây; nếu readiness chuyển sang 10 giây thì còn 24 lần/giây.

Tiếp theo, giải thích thông tin nào có thể mất và phép thử nào cần thực hiện cho mỗi thay đổi. Không chấp nhận một phương án chỉ ghi “chi phí giảm” mà không chỉ ra khả năng quan sát còn được giữ lại.

Một chính sách vận hành nên có người sở hữu, ngân sách, cách đo, dấu hiệu chạm giới hạn và cách hoàn nguyên. Khi các yếu tố này rõ ràng, chi phí quan sát trở thành quyết định kỹ thuật có thể kiểm chứng thay vì một tập thuộc tính được sao chép theo thói quen.
