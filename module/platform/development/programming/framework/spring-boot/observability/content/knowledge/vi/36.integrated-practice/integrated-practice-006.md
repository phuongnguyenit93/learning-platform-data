# Thiết lập sampling

Sampling quyết định những trace nào được giữ lại để điều tra. Trong một hệ thống Spring Boot có nhiều service, sampling cần cân bằng giữa khả năng tìm lỗi, độ chi tiết của trace, chi phí lưu trữ và tải lên collector. Nếu lấy mẫu quá thấp, trace lỗi có thể không còn; nếu lấy mẫu 100% trong production với lưu lượng lớn, chi phí và áp lực lên pipeline có thể tăng mạnh.

Bài thực hành này thiết lập sampling cho một luồng checkout gọi payment, sau đó kiểm tra trace context qua ranh giới service. Phần cuối mở rộng sang tail sampling tại OpenTelemetry Collector để ưu tiên trace có lỗi hoặc độ trễ cao.

## Mục tiêu

Sau khi hoàn thành, bạn có thể:

- Phân biệt head sampling và tail sampling.
- Cấu hình xác suất sampling trong Spring Boot bằng Micrometer Tracing.
- Chọn tỷ lệ khác nhau cho local, test và production.
- Xác minh service phía sau tuân theo sampling decision của trace cha.
- Hiểu vì sao sampling traces không đồng nghĩa với giảm metrics hoặc logs.
- Đánh giá trade-off về chi phí, độ bao phủ và khả năng điều tra.

## Bối cảnh thực hành

Giả sử hệ thống có hai service:

~~~text
Client
  |
  v
checkout-service
  |
  | HTTP + trace context
  v
payment-service
  |
  v
Payment provider
~~~

checkout-service nhận request, tạo server span, rồi gọi payment-service qua HTTP client đã được instrument. payment-service tạo server span thuộc cùng trace, sau đó có thể tạo span cho lời gọi tới payment provider.

Khi sampling được bật, quyết định giữ trace thường được đưa ra ở đầu trace. Các service phía sau phải tiếp tục context và tuân theo quyết định sampling được truyền trong trace context. Nếu mỗi service tự lấy mẫu độc lập, trace có thể chỉ còn một vài đoạn và rất khó phân tích.

## 1. Chuẩn bị tracing trong Spring Boot

Với Spring Boot 3.x, Micrometer Observation và Micrometer Tracing cung cấp điểm tích hợp cho tracing. Ứng dụng cần có Actuator, một tracing bridge và exporter phù hợp với backend.

Ví dụ Maven dependency cho hướng OpenTelemetry:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Dùng dependency management của Spring Boot để quản lý phiên bản tương thích. Nếu chọn Brave bridge thì dùng micrometer-tracing-bridge-brave thay cho OpenTelemetry bridge. Mỗi ứng dụng chỉ nên chọn một tracing bridge làm cơ chế tích hợp chính. Cách khai báo exporter cụ thể phụ thuộc phiên bản Spring Boot và pipeline đang sử dụng.

Việc thêm dependency chưa tự chứng minh rằng trace đã được export. Hãy xác nhận ứng dụng có exporter, endpoint collector và resource identity đúng trước khi đánh giá sampling.

## 2. Cấu hình head sampling bằng xác suất

Head sampling đưa ra quyết định khi trace bắt đầu. Với Micrometer Tracing được Spring Boot tự cấu hình, có thể đặt xác suất bằng management.tracing.sampling.probability.

~~~yaml
# application.yml
spring:
  application:
    name: checkout-service

management:
  tracing:
    sampling:
      probability: 0.10
~~~

Giá trị 0.10 có nghĩa là mục tiêu lấy khoảng 10% trace root theo sampler xác suất. Đây là giá trị minh họa để bắt đầu; tỷ lệ production phải dựa trên lưu lượng, số span mỗi trace, dung lượng exporter và yêu cầu điều tra.

Đặt cấu hình tương ứng cho payment-service. Mỗi service có thể có resource identity riêng, nhưng sampling decision của một trace phải được truyền xuyên service. Khi dùng cơ chế parent-based sampler, service con tuân theo sampled flag của parent thay vì bốc thăm lại cho từng span.

Có thể tách tỷ lệ theo profile:

~~~yaml
# application-local.yml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

~~~yaml
# application-prod.yml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Trong local, 1.0 giúp quan sát đầy đủ các luồng thử nghiệm. Tỷ lệ 0.05 trong production chỉ là ví dụ; hãy điều chỉnh theo traffic, độ dài trace và ngân sách lưu trữ. Tránh đưa giá trị 1.0 lên production chỉ để thuận tiện debug.

Có thể dùng biến môi trường để điều khiển tỷ lệ khi deploy:

~~~text
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.05
~~~

Cần xác nhận profile đang hoạt động và giá trị cuối cùng mà Spring Boot nhận được. Một file profile không có tác dụng nếu profile đó không được kích hoạt.

### Hiểu sampled flag

Với W3C Trace Context, header traceparent chứa trace ID, parent span ID và trace flags. Bit sampled trong trace flags biểu thị quyết định lấy mẫu theo quy ước của W3C.

Ví dụ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Giá trị flags cuối là 01 trong ví dụ này, biểu thị trace được đánh dấu sampled. Service nhận request dùng propagator để extract context và tạo span con trong trace hiện tại. Không tự sửa traceparent bằng filter tùy tiện, cũng không tạo trace ID mới khi context hợp lệ đã tồn tại.

Nếu hệ thống dùng nhiều thư viện hoặc agent, kiểm tra rằng tất cả cùng dùng propagator và tracing pipeline tương thích. Tên header, trace ID và sampled flag cần được bảo toàn qua HTTP client, gateway và message broker.

## 3. Giữ sampling decision qua các service

Cấu hình tỷ lệ trên mỗi service chưa đủ. Cần xác minh cách sampler xử lý trace đã có parent context.

Với một request đi qua checkout-service và payment-service, kỳ vọng là:

- Nếu checkout tạo trace được sampled, payment tiếp tục trace đó và export span của nó.
- Nếu checkout tạo trace không được sampled, payment không tự tạo một trace độc lập cho cùng request chỉ vì tỷ lệ local của payment cao hơn.
- Nếu không có trace context hợp lệ, service nhận request có thể bắt đầu trace mới và áp dụng sampler root của chính nó.

Spring Boot auto-instrumentation cho các client được cấu hình đúng thường tự inject context. Ví dụ dùng RestClient.Builder do Spring Boot cung cấp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class PaymentClientConfiguration {

    @Bean
    RestClient paymentClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .build();
    }
}
~~~

Dùng builder được framework cấu hình để các customizer và instrumentation của ứng dụng có thể được áp dụng. Nếu tự tạo client độc lập hoặc dùng thư viện HTTP chưa được instrument, trace context có thể không được truyền. Với WebClient, RestTemplate hoặc client khác, kiểm tra tích hợp tương ứng với phiên bản đang chạy.

Với message broker, producer phải inject trace context vào message headers và consumer phải extract context trước khi xử lý. Nếu chuyển công việc sang executor hoặc scheduler, cần dùng cơ chế context propagation phù hợp; ThreadLocal không tự động bảo đảm context tồn tại sau khi đổi thread.

## 4. Xác minh sampling bằng một kịch bản kiểm thử

Không nên chỉ nhìn dashboard rồi kết luận tỷ lệ sampling đúng. Hãy chạy cùng một luồng request qua hai service và kiểm tra cả trace được giữ lẫn trace bị loại.

### Kiểm tra local với sampling 100%

1. Kích hoạt profile local trên cả checkout-service và payment-service.
2. Xác nhận cả hai service xuất telemetry đến cùng backend hoặc collector test.
3. Gửi một số request thử nghiệm đi qua checkout đến payment.
4. Mở trace trong backend và tìm hai server span cùng trace ID, cùng quan hệ parent-child hợp lý.
5. Xác minh span client của checkout mô tả lời gọi HTTP tới payment.
6. Kiểm tra resource service.name phân biệt checkout-service và payment-service.

Với sampling 1.0, các trace root trong phạm vi kiểm thử phải được giữ, trừ khi có một tầng khác đang lọc hoặc exporter bị lỗi. Nếu chỉ thấy span ở checkout, kiểm tra context propagation và cấu hình exporter của payment trước khi kết luận sampler sai.

### Kiểm tra sampling 0%

Tạm đặt probability về 0 trong môi trường local hoặc test, rồi gửi request mới. Không dùng lại một trace đã được tạo trước khi đổi cấu hình.

Kỳ vọng:

- Không có trace mới được export bởi sampler head với tỷ lệ 0.
- Request nghiệp vụ vẫn chạy bình thường.
- Metrics như request count và request duration vẫn được ghi nhận nếu meter pipeline đang bật.
- Logs vẫn được ghi theo cấu hình logging; log có thể mang trace ID nhưng backend không nhất thiết có trace tương ứng.

Sampling traces là quyết định cho pipeline tracing. Nó không tự động giảm metrics hay logs. Nếu metrics hoặc logs biến mất cùng trace, hãy kiểm tra cấu hình exporter và filter riêng của các signal đó.

### Kiểm tra propagation giữa các service

Có thể gửi request với traceparent hợp lệ đã biết và kiểm tra trace ID có được giữ qua checkout và payment hay không. Dùng một context được đánh dấu sampled và một context không sampled để kiểm tra cả hai nhánh.

Khi làm test, không chỉ so sánh số trace tổng thể. Hãy xác minh:

- Trace ID ở checkout và payment giống nhau.
- Span ID khác nhau giữa các span.
- Parent span ID của server span ở payment liên kết đúng với client span từ checkout theo mô hình instrumentation.
- Sampled decision được tuân thủ.
- Không có trace mới tách rời cho cùng một request.
- Request không bị lỗi chỉ vì trace bị drop.

Tỷ lệ xác suất không bảo đảm chính xác từng nhóm nhỏ. Nếu gửi 10 request ở tỷ lệ 10%, kết quả có thể là 0, 1, 2 hoặc nhiều trace được giữ. Hãy dùng số lượng request đủ lớn để quan sát xu hướng và kiểm tra deterministic behavior bằng các test context đã biết.

## 5. Chọn tỷ lệ theo lưu lượng và chi phí

Một cách ước lượng ban đầu là:

~~~text
Số trace được giữ mỗi giây
    = Số trace root mỗi giây x Sampling probability

Số span được gửi mỗi giây
    = Số trace được giữ mỗi giây x Số span trung bình mỗi trace
~~~

Ví dụ hệ thống có 200 request root mỗi giây, mỗi trace trung bình có 8 span:

| Sampling probability | Trace giữ lại mỗi giây | Span gửi mỗi giây |
|---:|---:|---:|
| 1.00 (100%) | 200 | 1.600 |
| 0.10 (10%) | 20 | 160 |
| 0.05 (5%) | 10 | 80 |
| 0.01 (1%) | 2 | 16 |

Đây là ước lượng đơn giản, giả định mỗi request tạo một trace root và số span trung bình không đổi. Retry, fan-out, message consumer và trace dài có thể làm số span thực tế lớn hơn. Cũng cần tính kích thước span, batching, queue và thời gian lưu trữ.

Khi chọn tỷ lệ, hãy cân nhắc:

- Lưu lượng request giờ cao điểm và số service trong mỗi trace.
- Tỷ lệ lỗi và khả năng tái hiện lỗi.
- Dung lượng mạng, collector, backend và retention.
- Mức độ chi tiết cần thiết để điều tra latency.
- Dữ liệu nhạy cảm và yêu cầu kiểm soát truy cập.
- Khả năng tăng sampling có kiểm soát khi sự cố xảy ra.

Không nên chọn một tỷ lệ chỉ dựa vào số request ở môi trường phát triển. Production cần được đo tải và theo dõi số span bị drop.

## 6. Khi nào cần tail sampling?

Head sampling quyết định sớm, trước khi biết request có lỗi hoặc chậm hay không. Vì vậy, một trace có lỗi có thể bị loại nếu quyết định root ban đầu không sampled.

Tail sampling trì hoãn quyết định cho đến khi collector đã nhận các span của trace. Collector có thể giữ trace theo điều kiện như:

- Trace có span status ERROR.
- Trace có latency vượt ngưỡng.
- Một số thao tác quan trọng cần được quan sát thường xuyên.
- Một tỷ lệ nhỏ trace bình thường để làm baseline.

Tail sampling phù hợp khi cần ưu tiên trace có giá trị điều tra cao. Đổi lại, collector phải giữ trạng thái trace trong bộ nhớ trong thời gian chờ, nhận được các span liên quan và được cấp đủ tài nguyên.

### Ví dụ cấu hình tail sampling ở OpenTelemetry Collector

Đoạn cấu hình sau minh họa một pipeline traces đơn giản. Tên component và khả năng của processor phụ thuộc bản phân phối OpenTelemetry Collector đang dùng; hãy xác minh processor tail_sampling có trong bản build.

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      - name: keep-slow-traces
        type: latency
        latency:
          threshold_ms: 1000

      - name: keep-baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

  batch:

exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp]
~~~

Các con số trên chỉ là ví dụ cho môi trường thử nghiệm. num_traces, expected_new_traces_per_sec và decision_wait phải được tính theo tốc độ trace, số span, kích thước dữ liệu và thời gian hoàn tất của request. TLS insecure chỉ phù hợp với ví dụ lab trong mạng kiểm thử; môi trường thật cần TLS và xác thực phù hợp.

Trong ví dụ này, chính sách giữ trace lỗi, trace chậm và một tỷ lệ trace nền. Tail sampling không thể giữ lại trace mà collector chưa từng nhận được. Nếu SDK ở ứng dụng đã head-sample loại trace đó, collector không thể khôi phục các span đã bị loại. Khi muốn dùng tail sampling để lựa chọn dựa trên lỗi hoặc latency, cần cấu hình upstream để gửi đủ trace tới collector; điều này có thể làm tăng lưu lượng giữa ứng dụng và collector.

Trong cụm collector, tất cả span của cùng một trace phải được định tuyến đến cùng một tail sampler instance. Nếu span của một trace bị chia ra nhiều collector độc lập, mỗi nơi chỉ thấy một phần trace và có thể ra quyết định sai. Kiến trúc nhiều collector thường cần tầng load balancing định tuyến theo trace ID và cơ chế xử lý khi instance lỗi.

Tail sampling cũng không thay thế head sampling trong mọi trường hợp. Nó phù hợp khi có đủ năng lực collector và cần lựa chọn theo kết quả cuối cùng; head sampling phù hợp khi cần giảm tải sớm và đơn giản hóa pipeline.

## 7. Giữ metrics và logs hữu ích khi giảm trace

Sampling trace không nên làm mất khả năng theo dõi sức khỏe tổng thể của service. Metrics thường vẫn ghi nhận mọi request theo cấu hình meter, bất kể trace có được sampled hay không. Vì vậy dashboard latency, throughput và error rate vẫn có thể phản ánh tổng thể traffic.

Logs cũng là pipeline riêng. Một log trong trace không sampled có thể vẫn chứa trace ID và span ID hiện hành. Khi tìm log theo trace ID mà không tìm thấy trace, cần hiểu rằng trace có thể đã bị sampling loại hoặc bị drop ở exporter/collector. Hãy phân biệt hai tình huống này bằng cách theo dõi trạng thái sampler và pipeline.

Không đưa trace ID vào metric label để bù cho sampling; cách đó tạo cardinality rất cao. Nếu backend hỗ trợ exemplars, có thể dùng exemplar để liên kết một quan sát metric với trace mẫu.

## 8. Vận hành và thay đổi sampling an toàn

Sampling là một cấu hình vận hành có ảnh hưởng trực tiếp đến chi phí và khả năng điều tra. Khi thay đổi tỷ lệ, hãy:

1. Ghi lại tỷ lệ hiện tại theo môi trường và service.
2. Ước lượng số trace/span sẽ gửi với traffic giờ cao điểm.
3. Thay đổi ở môi trường thử nghiệm trước và xác minh propagation.
4. Triển khai theo từng service hoặc từng nhóm traffic nếu kiến trúc cho phép.
5. Theo dõi queue exporter, collector memory, export errors và dropped spans.
6. So sánh trace coverage trước/sau thay đổi.
7. Ghi lại thời điểm, lý do, người chịu trách nhiệm và cách rollback.

Không thay đổi sampling một cách đột ngột trên toàn hệ thống khi chưa biết collector chịu được lưu lượng tăng hay không. Nếu cần tăng sampling trong lúc incident, đặt thời hạn và điều kiện đưa tỷ lệ về mức bình thường sau khi điều tra xong.

Các chỉ số cần theo dõi gồm số span được tạo, số span được export, số span bị drop, queue utilization, export failure, collector memory và latency của pipeline telemetry. Tên metric cụ thể phụ thuộc SDK, exporter và collector; hãy dùng metrics thực tế của phiên bản triển khai.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thấy trace nào | Probability bằng 0, exporter chưa cấu hình hoặc endpoint sai | Kiểm tra profile, property cuối cùng, exporter và collector logs |
| Chỉ thấy span ở service đầu | Client không inject context hoặc service sau không extract | Kiểm tra builder, instrumentation và traceparent |
| Trace bị tách thành nhiều trace ID | Context bị mất hoặc bị thay mới ở ranh giới | Kiểm tra HTTP headers, message headers và async context |
| Service con không theo sampled flag | Sampler hoặc bridge không xử lý parent context như dự kiến | Kiểm tra loại bridge, sampler và cấu hình parent-based |
| Trace lỗi không xuất hiện | Head sampling đã loại trace trước khi lỗi xảy ra | Cân nhắc tail sampling và cách gửi trace tới collector |
| Metrics giảm cùng traces | Có filter hoặc pipeline coupling ngoài dự kiến | Kiểm tra meter registry và exporter metrics độc lập |
| Collector drop span | Queue đầy, memory thiếu hoặc tail sampler quá tải | Kiểm tra throughput, queue, memory và decision wait |
| Trace thiếu span khi dùng tail sampling cluster | Span cùng trace đi đến nhiều collector khác nhau | Kiểm tra load balancing theo trace ID |

## Bài tập tự kiểm tra

1. Đặt sampling 1.0 cho local. Gửi một request qua hai service và xác minh các span nằm trong cùng trace.
2. Đặt sampling 0.0. Gửi request mới và xác minh metrics vẫn tăng trong khi trace mới không được export.
3. Đặt sampling 0.1. Gửi một lượng request đủ lớn và so sánh tỷ lệ trace được giữ với kỳ vọng thống kê.
4. Gửi một traceparent đã biết với sampled flag bật và tắt. Xác minh service phía sau tuân theo parent context.
5. Bật tail sampling trong collector test. Tạo một request lỗi, một request chậm và nhiều request bình thường; xác minh policy giữ đúng các trace mong muốn.
6. Tắt collector trong thời gian ngắn. Xác minh request nghiệp vụ vẫn hoạt động và exporter/collector thể hiện tình trạng lỗi hoặc drop.

Một cấu hình sampling đạt yêu cầu khi quyết định được truyền nhất quán qua các service, trace được giữ đúng chính sách, metrics và logs vẫn có giá trị độc lập, và pipeline có đủ năng lực xử lý lưu lượng telemetry. Hãy ghi rõ tỷ lệ theo môi trường, người sở hữu cấu hình và quy trình tăng/giảm sampling để việc điều tra production có thể thực hiện có kiểm soát.

