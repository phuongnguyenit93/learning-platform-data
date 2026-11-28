# Sampling trong staging và production

Trong một ứng dụng Spring Boot dùng **Spring Modulith**, tracing có thể cho thấy một request đi qua module `order`, gọi API của `inventory`, rồi phát application event để `billing` hoặc `notification` xử lý. Khi lưu mọi trace, mỗi request đều có thể tạo nhiều spans và làm tăng lưu lượng xuất telemetry, dung lượng backend và chi phí truy vấn. Nhưng nếu loại bỏ quá nhiều trace, nhóm vận hành có thể bỏ lỡ chính request gây lỗi hoặc chậm.

**Sampling** là cách chọn một phần trace để xử lý và xuất đi. Mục tiêu trong staging và production không giống nhau: staging cần đủ dữ liệu để kiểm chứng bản phát hành và tái hiện lỗi; production cần cân bằng độ bao phủ, khả năng điều tra, tải hệ thống và ngân sách. Bài này hướng dẫn chọn chiến lược, cấu hình Spring Boot, kết hợp head sampling với tail sampling tại OpenTelemetry Collector, và kiểm tra xem các module spans có được giữ lại đúng như dự kiến hay không.

Bài thuộc chương **Sampling** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Nội dung kết hợp module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng hành vi kiến trúc mô-đun khi ứng dụng vận hành.

> **Phạm vi phiên bản:** Các ví dụ Spring Boot 3.5.x dùng `management.tracing.sampling.probability`. Spring Boot 4.2.x có thêm cấu hình chọn OpenTelemetry sampler qua `management.opentelemetry.tracing.sampler`. Hãy đối chiếu đúng BOM và application properties của phiên bản dự án; không trộn prefix giữa các dòng.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích sampling, trace/span được sampled và không được sampled.
2. Phân biệt **head sampling** ở SDK với **tail sampling** sau khi Collector nhận trace.
3. Chọn sampling rate khác nhau cho local, staging và production theo traffic và mục tiêu vận hành.
4. Cấu hình sampling trong Spring Boot 3.5.x và chọn sampler trong Spring Boot 4.2.x.
5. Hiểu vai trò của parent-based sampling khi request đi qua nhiều ứng dụng hoặc application module.
6. Thiết kế tail-sampling policies để giữ trace có lỗi, độ trễ cao hoặc thuộc nhóm nghiệp vụ quan trọng.
7. Nhận biết giới hạn của tail sampling, đặc biệt về memory, decision wait, late spans và phân phối trace đến nhiều Collector.
8. Kiểm chứng sampling bằng metrics, Collector telemetry và truy vấn trace backend.
9. Phân biệt trace sampling với metrics, logs, audit records và Event Publication Registry.

## 2. Sampling là gì?

Một **trace** gồm các spans mô tả một lần thực thi. Sampling quyết định trace nào được giữ và xuất. Một trace được sampled khi sampler chọn trace đó để xử lý/xuất; trace không được sampled sẽ không được gửi tới backend tracing theo quyết định sampling.

Ví dụ, ứng dụng nhận 10.000 request trong một khoảng thời gian. Nếu tỷ lệ sampling là 10%, số trace kỳ vọng được chọn xấp xỉ 1.000. Đây là **giá trị kỳ vọng**, không phải quota chính xác: kết quả thực tế có thể cao hoặc thấp hơn.

Sampling giúp:

- Giảm số spans phải export, ingest, index và lưu trữ.
- Giảm băng thông giữa ứng dụng, Collector và backend.
- Tập trung dữ liệu vào một tập đại diện cho traffic bình thường, đồng thời dành chính sách riêng cho lỗi hoặc request chậm.
- Điều chỉnh mức chi tiết theo môi trường, service và nhóm traffic.

Sampling cũng có chi phí: nếu chọn sai, trace quan trọng có thể bị bỏ; tail sampling còn cần compute và memory để giữ dữ liệu chờ quyết định. Với hệ thống có traffic thấp, đôi khi lưu toàn bộ trace đơn giản và rẻ hơn vận hành một pipeline sampling phức tạp.

**Sampling chỉ điều khiển traces.** Nó không tự giảm số liệu Micrometer metrics, không xóa application logs và không thay thế dữ liệu audit hoặc trạng thái nghiệp vụ. Hãy dùng metrics để theo dõi tỷ lệ lỗi/độ trễ tổng thể trên toàn bộ traffic; dùng traces để điều tra đường đi của những lần thực thi được chọn.

## 3. Hai cách lấy mẫu: head và tail

### Head sampling — quyết định ngay khi bắt đầu trace

Head sampling đưa ra quyết định sớm, thường ở SDK trong ứng dụng, khi root span được tạo. Với ratio sampling, sampler dùng trace ID và xác suất đã cấu hình để quyết định giữ hay bỏ trace.

~~~mermaid
flowchart LR
    Request["Request bắt đầu"] --> Sampler{"Head sampler"}
    Sampler -->|"Sampled"| Export["Các spans được export"]
    Sampler -->|"Not sampled"| Drop["Không export trace"]
    Export --> Collector["Collector / backend"]
~~~

Ưu điểm:

- Dễ cấu hình và ít trạng thái.
- Giảm lưu lượng ngay từ ứng dụng.
- Có thể áp dụng ở nhiều service trong distributed trace.

Giới hạn: tại thời điểm quyết định, sampler chưa biết toàn bộ trace sẽ kết thúc ra sao. Nó không thể bảo đảm giữ tất cả trace có exception hoặc tổng thời gian vượt ngưỡng, vì các dấu hiệu ấy có thể chỉ xuất hiện ở span sau.

### Tail sampling — quyết định sau khi đã nhận các spans

Tail sampling được thực hiện ở tầng nhận dữ liệu, thường là OpenTelemetry Collector. Collector tạm giữ spans theo trace ID, đợi đủ dữ liệu trong khoảng thời gian cấu hình, sau đó quyết định giữ hay bỏ trace dựa trên trạng thái, latency hoặc attributes.

~~~mermaid
flowchart LR
    App["Ứng dụng gửi spans"] --> Receiver["Collector nhận spans"]
    Receiver --> Buffer["Giữ spans theo trace ID"]
    Buffer --> Wait["Chờ đủ dữ liệu / decision wait"]
    Wait --> Policy{"Tail-sampling policies"}
    Policy -->|"Error / slow / rule match"| Keep["Export trace"]
    Policy -->|"Không match"| Drop["Drop trace"]
~~~

Tail sampling có thể giữ tất cả trace có lỗi, giữ trace chậm hơn ngưỡng, và chỉ giữ một tỷ lệ nhỏ của traffic bình thường. Nhưng nó cần memory, capacity và khả năng tập hợp **mọi spans của cùng một trace** về đúng nơi ra quyết định.

| Tiêu chí | Head sampling | Tail sampling |
| --- | --- | --- |
| Thời điểm quyết định | Khi trace/span bắt đầu | Sau khi Collector nhận một phần hoặc toàn bộ trace |
| Thành phần thường thực hiện | SDK/tracer trong ứng dụng | Collector hoặc tracing platform |
| Biết trace có lỗi ở cuối không? | Không thể dựa vào lỗi xảy ra sau quyết định | Có thể, nếu error span đến trước quyết định |
| Giảm lưu lượng từ ứng dụng | Có | Không; ứng dụng vẫn gửi spans đến Collector |
| Yêu cầu memory/state | Thấp | Cao hơn, giữ trace chờ quyết định |
| Vận hành nhiều replica | Đơn giản hơn | Phải định tuyến các spans cùng trace tới cùng sampler |
| Use case | Giảm tải sớm theo tỷ lệ | Giữ lỗi/trace chậm theo kết quả thực tế |

## 4. Parent-based sampling giữ tính nhất quán của distributed trace

Một request có thể đi từ gateway đến Spring Boot, gọi service khác rồi phát event. Nếu mỗi service tự lấy mẫu độc lập, một trace có thể bị thiếu spans ở giữa. **Parent-based sampling** sử dụng quyết định của parent span khi có parent; với trace mới không có parent, sampler gốc đưa ra quyết định theo chính sách đã cấu hình.

~~~mermaid
flowchart TB
    Root["Root request: trace ID A"]
    Root --> Decision{"Root sampler"}
    Decision -->|"Sampled"| Parent["Parent span sampled"]
    Decision -->|"Not sampled"| NoParent["Child spans theo quyết định not sampled"]
    Parent --> Order["order span"]
    Order --> Inventory["inventory span"]
    Inventory --> Billing["downstream span"]
~~~

Với W3C Trace Context, trạng thái sampled được truyền cùng trace context qua header `traceparent`. Service downstream phải trích xuất context và sử dụng instrumentation/tracer tương thích. Trong Spring Boot, dùng các HTTP client builder được auto-configure (như `RestClient.Builder` hoặc `WebClient.Builder`) để trace context được truyền tự động; tự tạo client không dùng builder auto-configured có thể làm propagation không hoạt động.

Trong modular monolith, lời gọi giữa `order` và `inventory` có thể cùng nằm trong một trace/process. Nếu Spring Modulith tạo module spans, chúng thường theo quyết định sampling của trace đang hoạt động. Với `@ApplicationModuleListener` chạy bất đồng bộ sau commit, context cần được truyền qua executor nếu muốn listener tiếp tục trace gốc; nếu không, listener có thể tạo trace riêng hoặc không có trace context.

**Parent-based sampling không tự khắc phục context propagation bị mất.** Trước khi điều tra sampling, hãy xác minh parent span và trace context có thực sự đến được điểm instrument hay không.

## 5. Cấu hình sampling trong Spring Boot 3.5.x

Spring Boot 3.5.x cung cấp property:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Giá trị hợp lệ nằm trong khoảng từ `0.0` đến `1.0`:

| Giá trị | Ý nghĩa |
| ---: | --- |
| `0.0` | Không lấy mẫu trace mới |
| `0.01` | 1% trace mới |
| `0.05` | 5% trace mới |
| `0.1` | 10% trace mới; mặc định Spring Boot |
| `0.25` | 25% trace mới |
| `1.0` | 100% trace mới |

Spring Boot mặc định sample 10% request để tránh làm backend quá tải. Trong local, có thể nâng lên 100% để dễ quan sát. Trong staging/production, chọn rate theo lưu lượng và ngân sách thực tế, không sao chép 100% từ ví dụ local.

Ví dụ tách profile (các giá trị chỉ là **điểm khởi đầu minh họa**):

**application-local.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

**application-staging.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.25
~~~

**application-prod.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Nếu staging có ít traffic và cần kiểm tra một đợt release cụ thể, có thể nâng tỷ lệ lên 1.0 trong khoảng thử nghiệm có kiểm soát. Nếu staging chạy load test gần production, hãy đánh giá tải Collector/backend trước khi tăng.

## 6. Chọn OpenTelemetry sampler trong Spring Boot 4.2.x

Với OpenTelemetry, Spring Boot 4.2.x cho phép chọn sampler bằng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Các sampler được hỗ trợ:

| Sampler | Hành vi |
| --- | --- |
| `always-on` | Giữ mọi trace |
| `always-off` | Bỏ mọi trace |
| `trace-id-ratio` | Lấy một tỷ lệ trace dựa trên `management.tracing.sampling.probability` |
| `parent-based-always-on` | Có parent thì theo parent; không có parent thì luôn giữ |
| `parent-based-always-off` | Có parent thì theo parent; không có parent thì bỏ |
| `parent-based-trace-id-ratio` | Có parent thì theo parent; trace mới thì lấy mẫu theo tỷ lệ; là mặc định được tài liệu Spring Boot nêu |

Đối với hệ thống nhiều service, parent-based ratio thường là điểm bắt đầu hợp lý để các child spans theo quyết định của root trace. Nếu muốn Collector tail-sample theo lỗi/latency, ứng dụng phải gửi đủ các spans cần thiết tới Collector; phần 10 sẽ giải thích cấu hình tương ứng.

**Không dùng sampler `always-off` để “tắt tracing” trong khi vẫn mong tail sampler giữ lỗi.** Nếu SDK bỏ spans trước khi export, Collector không thể khôi phục dữ liệu đã bị bỏ.

## 7. Ước lượng lượng trace và xác suất bỏ lỡ một tình huống

Với head sampling tỷ lệ `p` và `N` trace mới, số trace kỳ vọng được giữ:

\[
E[\text{traces sampled}] = N \times p
\]

Ví dụ 100.000 trace mới/ngày ở mức 5% cho khoảng 5.000 trace/ngày theo kỳ vọng. Số thực tế dao động theo quyết định sampling.

Một điều quan trọng với staging/production là: **một lần lỗi hiếm có thể không xuất hiện trong trace đã sample**. Nếu mỗi request được chọn độc lập với xác suất 10%, xác suất không có trace nào được giữ trong 10 request là:

\[
P(\text{không trace nào được giữ}) = (1 - 0.1)^{10} \approx 34.9\%
\]

Vì vậy, gửi 10 request lỗi trong khi chỉ sample 10% không đảm bảo sẽ có trace để xem. Với nhiều request hơn, xác suất bỏ lỡ tất cả giảm, nhưng không bằng không.

Sampling dựa trên trace ID thường mang tính xác định cho một trace ID cụ thể, nên retry cùng trace context có thể tiếp tục cùng quyết định. Không coi xác suất là một quota chính xác theo phút hoặc theo tenant.

### Đừng dùng trace sample để thay metrics cho SLO

Nếu cần tỷ lệ lỗi hoặc p95 latency đáng tin cậy cho toàn bộ request, hãy dùng metrics được instrument cho toàn traffic. Trace sampling tạo một tập con; percentile tính trên tập con có thể hữu ích để điều tra nhưng không phải lúc nào cũng tương đương percentile toàn bộ traffic. Với những quyết định SLA, billing hoặc compliance, dùng nguồn dữ liệu chuyên dụng theo yêu cầu nghiệp vụ.

## 8. Chiến lược cho staging

Staging thường phục vụ kiểm thử tích hợp, kiểm tra release candidate, smoke test và load test. Mục tiêu là thu đủ trace để phát hiện thay đổi trong đường đi module mà không để môi trường test tạo ra tải telemetry không cần thiết.

Một chiến lược thực tế:

| Loại hoạt động staging | Sampling gợi ý | Lý do |
| --- | --- | --- |
| Smoke test sau deploy | 100% trong cửa sổ test ngắn | Dễ xác nhận trace mới xuất hiện và module spans đúng |
| Regression test có traffic vừa phải | 25–100% tùy dung lượng | Có đủ mẫu để so sánh release |
| Load test gần production | Tỷ lệ đã định trước, có giới hạn ngân sách | Tránh làm chính backend observability trở thành nút nghẽn |
| Kiểm tra event listener | Giữ trace theo test ID/correlation trong môi trường kiểm soát hoặc dùng tail policy | Cần nhìn cả nhánh sau commit |
| Chạy staging liên tục với traffic lớn | Sampling ratio thấp hơn hoặc tail sampling | Kiểm soát chi phí dài hạn |

Không nên luôn để 100% trong staging chỉ vì “đó là môi trường test”. Một load test lớn có thể tạo nhiều spans hơn production bình thường và gây quá tải Collector. Ngược lại, tỷ lệ quá thấp có thể khiến test nhỏ không có trace để so sánh.

### Kiểm tra staging sau mỗi lần deploy

1. Gửi một request đại diện qua module `order` tới `inventory`.
2. Nếu có event, kiểm tra listener `@ApplicationModuleListener` và context propagation.
3. Tra trace theo `service.name` và thời gian; kiểm tra HTTP span, module spans và event listener span nếu đã instrument.
4. Ghi lại sampling probability và số request gửi so với số trace nhận.
5. So sánh cùng kịch bản giữa release trước và release mới.

Với smoke test nhỏ, dùng 100% trong một cửa sổ ngắn sẽ cho kết quả lặp lại rõ ràng hơn sampling thấp. Khi test kết thúc, khôi phục tỷ lệ staging đã định.

## 9. Chiến lược cho production

Production cần cân bằng ba mục tiêu:

- **Độ bao phủ:** đủ trace để nhận diện đường đi bất thường và sự cố.
- **Chi phí/tải:** không làm ứng dụng, Collector và backend quá tải.
- **Khả năng điều tra:** ưu tiên các trace có lỗi, chậm hoặc thuộc luồng nghiệp vụ quan trọng.

Một cách bắt đầu là ratio-based head sampling ở mức phù hợp với traffic, ví dụ 5% hoặc 10%, rồi theo dõi volume và chất lượng dữ liệu. Với hệ thống có traffic lớn, cần phân tích trace/giây, kích thước trung bình mỗi trace, số spans/trace, retention và năng lực backend trước khi chọn tỷ lệ.

| Tình huống production | Chiến lược cần cân nhắc |
| --- | --- |
| Traffic vừa, trace volume nằm trong ngân sách | Parent-based ratio sampling |
| Traffic lớn, phần lớn request khỏe và tương tự nhau | Head sampling tỷ lệ thấp hơn, dựa trên trace ID |
| Cần giữ gần như toàn bộ trace có lỗi | Tail sampling tại Collector, nhận đủ candidate spans |
| Cần giữ request chậm và lỗi theo module/route | Tail policies theo status/latency/attributes ổn định |
| Cần điều tra sự cố ngắn hạn | Tăng sampling có thời hạn và theo dõi tác động tài nguyên |
| Có yêu cầu lưu bằng chứng đầy đủ | Không dựa vào sampled traces; dùng audit/business records theo chính sách |

Các tỷ lệ như 5%/10% chỉ là ví dụ. **Không có một sampling rate production đúng cho mọi ứng dụng.** Hãy đặt ngân sách, đo lượng trace thực tế và điều chỉnh theo bằng chứng.

## 10. Tail sampling để giữ trace có lỗi hoặc chậm

Nếu yêu cầu là “giữ tất cả trace có lỗi và trace chậm hơn một giây, còn traffic bình thường chỉ lấy 5%”, head sampling ratio đơn thuần không thể đáp ứng đầy đủ. Lý do: head sampler quyết định trước khi biết request có lỗi hoặc chậm ở cuối hay không.

Có thể dùng OpenTelemetry Collector tail-sampling processor:

1. Ứng dụng export candidate spans đến Collector.
2. Collector gom spans theo trace ID.
3. Tail sampler chờ trong `decision_wait` để nhận các spans đến muộn.
4. Policy kiểm tra status, latency hoặc attributes.
5. Trace phù hợp được chuyển tiếp tới backend; trace không phù hợp bị loại.

**Điều kiện quan trọng:** nếu head sampling trong ứng dụng đã loại 95% trace, tail sampler chỉ nhìn thấy 5% còn lại. Nó không thể bảo đảm giữ tất cả lỗi nằm trong 95% đã bị bỏ. Nếu muốn tail sampling quyết định cuối cùng, cần gửi đủ candidate traces tới Collector (ví dụ dùng sampling 100% ở SDK/parent root), rồi để Collector giảm volume trước backend.

Ví dụ cấu hình phía ứng dụng khi Collector chịu trách nhiệm ra quyết định cuối:

**Spring Boot 3.5.x**

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

**Spring Boot 4.2.x với OpenTelemetry**

~~~yaml
management:
  opentelemetry:
    tracing:
      sampler: parent-based-always-on
~~~

Với parent-based sampler, các root traces mới được giữ; child spans tiếp tục theo quyết định của parent. Các gateway/service đứng trước ứng dụng cũng phải truyền trace context và không loại trace trước khi chúng đến Collector. Nếu một upstream đã đánh dấu trace là không sampled, downstream parent-based sampler sẽ tiếp tục tôn trọng quyết định đó.

### Ví dụ Collector Contrib tail-sampling pipeline

Tail Sampling Processor được phân phối trong Collector Contrib/Kubernetes distribution tương ứng; hãy kiểm tra component có trong binary đang triển khai. Ví dụ sau minh họa giữ tất cả trace có status `ERROR`, giữ trace có duration trên 1.000 ms và lấy mẫu xác suất 5% cho phần còn lại:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 75
    spike_limit_percentage: 15

  tail_sampling:
    decision_wait: 15s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 1000
      - name: sample-healthy-baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

  batch:
    timeout: 1s

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [debug]
~~~

Đây là cấu hình minh họa cho local/staging, dùng `debug` exporter để xem trace đã được giữ. Trong production, thay bằng exporter tới tracing backend có TLS/auth và sizing phù hợp. Các giá trị `decision_wait`, `num_traces`, `expected_new_traces_per_sec` và memory limit **không phải cấu hình production dùng chung**; cần đo theo traffic và kích thước trace.

### Ý nghĩa các policies

| Policy | Điều kiện | Mục đích |
| --- | --- | --- |
| `keep-errors` | Trace có span status `ERROR` | Giữ dấu vết sự cố |
| `keep-slow` | Duration trace vượt 1.000 ms | Giữ request chậm |
| `sample-healthy-baseline` | Lấy mẫu 5% theo xác suất | Có mẫu đại diện cho traffic bình thường |

Trong ví dụ, các policy giữ dương tính được kết hợp để trace phù hợp ít nhất một điều kiện được giữ. Cần kiểm tra semantics policy và thứ tự/drop rules của đúng phiên bản processor nếu thêm điều kiện loại trừ.

**Policy lỗi chỉ hoạt động nếu spans thực sự mang error status.** Một exception đã bị bắt và chuyển thành response bình thường có thể không tạo span status `ERROR` theo cách bạn mong đợi. Hãy kiểm tra instrumentation, status và attributes trên trace thật trước khi dựa vào policy.

## 11. Những giới hạn vận hành của tail sampling

Tail sampling mạnh hơn khi cần quyết định dựa trên kết quả cuối, nhưng không phải bật processor là xong:

- **Stateful:** Collector giữ spans trong bộ nhớ trước khi ra quyết định. Tăng traffic hoặc decision wait sẽ tăng yêu cầu memory.
- **Decision wait:** quá ngắn có thể ra quyết định trước khi các spans cuối đến; quá dài làm tăng thời gian chờ và memory.
- **Late spans:** spans đến sau quyết định có thể bị bỏ hoặc không làm thay đổi quyết định đã đưa ra.
- **Trace affinity:** mọi spans của cùng trace phải được gửi đến **cùng một Collector instance** để tail sampler có đủ dữ liệu. Khi scale nhiều Collector, cần định tuyến theo trace ID (sticky/hash routing), không round-robin ngẫu nhiên.
- **Processor distribution:** tail sampling processor thường cần Collector Contrib hoặc distribution có đóng gói component này; không giả định mọi Collector binary đều có.
- **Giám sát chính sampler:** theo dõi số trace đang giữ, sampling decision latency, dropped/late spans, memory và queue. Nếu sampler quá tải, dữ liệu có thể bị mất trước backend.

Khi thêm processor phụ thuộc context/resource (ví dụ Kubernetes attributes), đặt nó trước tail sampling nếu processor cần context gốc. Tail sampling có thể gom lại batches và làm mất context ban đầu.

Tail sampling nên được thử nghiệm bằng load test gần với traffic thực tế, có cả trace dài, trace lỗi và spans đến trễ. Không đưa ngay policy phức tạp vào production khi chưa xác minh khả năng chịu tải.

## 12. Spring Modulith: sampling ảnh hưởng module spans và event listener ra sao?

Giả sử request tạo đơn đi qua:

~~~text
HTTP POST /orders
  └─ order module
       ├─ inventory module call
       └─ publish OrderPlaced
              └─ billing listener (async, after commit)
~~~

Khi trace được sample, các spans được instrument trong cùng context có thể được export cùng nhau. Khi trace bị head-sampling bỏ, module spans theo parent-based sampling thường cũng không được xuất. Điều này không có nghĩa các module không chạy; chỉ là trace không được chọn.

Với `@ApplicationModuleListener`:

- Listener chạy bất đồng bộ sau commit và transaction riêng.
- Nếu context propagation qua executor hoạt động, listener span có thể tiếp tục trace gốc và tail sampler nhìn thấy cả nhánh.
- Nếu context bị mất, listener có thể bắt đầu trace mới hoặc không có parent; chính sách sampling cho root trace mới có thể khác.
- Nếu publication được retry sau restart, trace context ban đầu có thể không còn; correlation/event ID và publication state giúp liên hệ nghiệp vụ.

**Không dùng sampling để đếm event chính xác.** Event publication metrics và consumer metrics cần ghi cho toàn bộ event theo thiết kế. Trace sampling chỉ quyết định trace nào được lưu để điều tra.

## 13. Sampling và dữ liệu nhạy cảm

Trace có thể chứa URL, exception, module names, tenant attributes hoặc metadata nghiệp vụ. Sampling không phải cơ chế bảo vệ dữ liệu: một trace được giữ vẫn có thể làm lộ thông tin nếu instrumentation ghi sai attributes.

Trước khi triển khai:

1. Không gắn password, access token, session cookie hoặc thông tin thanh toán vào spans.
2. Tránh đưa email, tenant ID, order ID hoặc dữ liệu cá nhân vào trace nếu không có nhu cầu và chính sách rõ ràng.
3. Dùng redaction/filtering trước khi export hoặc ở Collector khi phù hợp.
4. Hạn chế quyền truy cập backend và thời gian retention.
5. Với yêu cầu audit/compliance phải lưu đủ, dùng audit log hoặc business record chuyên biệt; không dựa vào tỷ lệ sampled traces.
6. Kiểm tra policy theo route/module không vô tình giữ dữ liệu nhạy cảm ngoài dự kiến.

## 14. Xác minh sampling trong staging và production

### Kiểm tra ở ứng dụng

Với Spring Boot Actuator và tracing đã cấu hình, gửi một lượng request có thể kiểm soát. Ghi nhận:

- Số request thực tế theo HTTP metrics.
- Sampling probability/sampler đang hoạt động theo profile.
- Số trace/span Collector nhận được.
- Số trace backend lưu được.
- Số lỗi export, queue/drop và trạng thái Collector.

Actuator metrics phản ánh toàn traffic nếu meter không bị sampling riêng; trace backend chỉ chứa phần được chọn. Không so số trace với số request như hai con số phải bằng nhau.

### Kiểm tra theo từng chặng

~~~mermaid
flowchart TD
    A["Xác nhận profile và sampler"] --> B["Gửi traffic kiểm soát"]
    B --> C{"Ứng dụng tạo/export spans?"}
    C -->|"Không"| D["Kiểm tra instrumentation, parent context, sampling"]
    C -->|"Có"| E{"Collector nhận đủ candidate spans?"}
    E -->|"Không"| F["Kiểm tra endpoint, network, exporter và head sampling"]
    E -->|"Có"| G{"Tail policy giữ trace mong muốn?"}
    G -->|"Không"| H["Kiểm tra status, latency, attributes, decision_wait"]
    G -->|"Có"| I["Xác minh backend, service.name và trace IDs"]
~~~

### Kiểm tra policy lỗi và độ trễ

Trong staging:

1. Gọi một endpoint thành công, một endpoint chậm có kiểm soát và một endpoint tạo lỗi có kiểm soát.
2. Với head ratio thấp, ghi nhận có thể không thấy từng trace riêng lẻ.
3. Với tail sampling, xác nhận Collector nhận candidate spans và giữ trace error/slow theo policies.
4. Kiểm tra status code/status của spans, không chỉ HTTP response.
5. Kiểm tra module spans của `order`/`inventory` nếu integration đã instrument.
6. Xác nhận listener async vẫn được liên kết đúng trace nếu context propagation đã bật.

Trong production, quan sát theo cửa sổ thời gian đủ dài và so với metrics toàn traffic. Một trace cụ thể không xuất hiện có thể do sampling, exporter failure, tail policy hoặc query sai; không kết luận ngay module không chạy.

## 15. Bảng xử lý sự cố sampling

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Request thành công nhưng không tìm thấy trace | Head sampler không chọn trace | Xem probability và parent sampled flag |
| Child service thiếu span | Parent context không được truyền hoặc child sampler không theo parent | Kiểm tra traceparent, client builder và sampler |
| Trace error không xuất hiện dù tail policy giữ ERROR | SDK đã head-drop trước Collector, hoặc span không có status ERROR | Kiểm tra SDK ratio, Collector input và span status |
| Có trace trong Collector debug nhưng backend không thấy | Exporter/pipeline/backend lỗi | Kiểm tra Collector exporter logs, auth/TLS và query |
| Trace thiếu spans cuối | Decision wait quá ngắn hoặc spans đến muộn | Theo dõi late spans, tăng wait và kiểm tra mạng |
| Tail sampler tăng memory mạnh | Traffic, trace size, num_traces hoặc decision_wait quá cao | Sizing, memory limiter, shard/routing và load test |
| Một trace bị chia qua nhiều Collector | Routing không theo trace ID | Dùng trace-aware load balancing/sticky routing |
| Staging test không tái hiện trace | Tỷ lệ sampling thấp và lượng request ít | Tăng sampling tạm thời trong cửa sổ test |
| Trace module không thấy nhưng HTTP span có | Module instrumentation chưa chạy hoặc module span không được giữ | Kiểm tra Insight, module graph và trace tree |
| Event listener không nằm trong trace gốc | Context propagation bị mất hoặc listener retry sau restart | Kiểm tra executor, trace context, correlation/event ID |
| Error rate trên dashboard khác trace backend | Metrics đo toàn traffic, traces chỉ là sample | Đây là khác biệt kỳ vọng; không suy tỷ lệ lỗi từ số trace thô |
| Production chi phí tăng sau deploy | Sampling rate, span count hoặc attributes tăng | So sánh volume/trace, spans per trace, backend ingestion |

## 16. Bài thực hành: xây sampling policy cho staging và production

Chuẩn bị ứng dụng Spring Boot/Modulith có module `order` và `inventory`, tracing exporter và một OpenTelemetry Collector thử nghiệm.

1. **Baseline local:** đặt sampling 100%, gọi endpoint qua hai module, xác nhận HTTP và module spans.
2. **Staging ratio:** đặt tỷ lệ 25%, gửi một lượng request đã biết; so số trace kỳ vọng với số nhận được qua cửa sổ đủ dài.
3. **Staging smoke test:** tạm tăng lên 100% trong cửa sổ release verification, xác nhận trace cho từng kịch bản, sau đó khôi phục cấu hình.
4. **Production ratio:** chọn một tỷ lệ ban đầu dựa trên traces/giây, kích thước trace và retention; ghi lại ngân sách trước khi deploy.
5. **Tail policy:** cấu hình giữ trace status ERROR, giữ trace vượt ngưỡng latency và sample baseline một tỷ lệ nhỏ.
6. **Head/tail interaction:** xác nhận SDK gửi đủ candidate traces nếu mục tiêu là giữ tất cả lỗi; không để ratio head sampling loại bỏ trace trước Collector.
7. **Distributed consistency:** gọi downstream service và xác nhận parent-based sampling giữ nhất quán toàn trace.
8. **Async listener:** phát `OrderPlaced`, kiểm tra context propagation qua executor và listener spans.
9. **Collector capacity:** tạo load test, quan sát memory, pending traces, decision latency và late spans.
10. **Kiểm chứng dữ liệu:** so metrics toàn traffic với số trace sample, và xác nhận audit/business state không phụ thuộc trace sampling.

Mẫu ghi quyết định:

| Môi trường | Head sampler/rate | Tail policies | Mục tiêu | Bằng chứng sau triển khai |
| --- | --- | --- | --- | --- |
| Local | always-on / 100% | Không cần hoặc thử nghiệm | Debug dễ tái hiện | … |
| Staging | 25% thường trực; 100% khi smoke test có thời hạn | Giữ error/slow nếu đã dựng Collector | Kiểm chứng release | … |
| Production | Parent-based ratio theo ngân sách | Giữ error/slow và baseline sample nếu đủ năng lực | Điều tra sự cố với chi phí kiểm soát | … |

Các giá trị trong bảng là **ví dụ thiết kế**, cần điều chỉnh theo workload và backend của dự án.

### Câu hỏi tự kiểm tra

1. Head sampling đưa ra quyết định vào thời điểm nào, và vì sao không thể biết request sẽ lỗi ở cuối?
2. Tail sampling cần giữ những dữ liệu nào trước khi quyết định?
3. Vì sao đặt SDK sampling 5% làm tail sampler không thể bảo đảm giữ tất cả trace lỗi?
4. Parent-based ratio sampling giúp gì khi request đi qua nhiều service?
5. Vì sao 10 request với tỷ lệ 10% có thể không tạo trace nào trong backend?
6. Tại sao metrics lỗi toàn traffic vẫn cần thiết khi traces đã được sample?
7. Nếu `@ApplicationModuleListener` chạy async mà trace context bị mất, tail sampler có thể nhìn thấy nhánh listener như thế nào?
8. Vì sao mọi span của một trace phải đến cùng Collector instance khi dùng tail sampling?
9. Decision wait quá ngắn và quá dài có những tác động gì?
10. Sampling trace có thể thay thế audit record hoặc Event Publication Registry không? Vì sao?

## 17. Tổng kết

**Sampling trong staging và production là quyết định vận hành**, không chỉ là một con số trong YAML. Spring Boot cho phép cấu hình tỷ lệ trace bằng `management.tracing.sampling.probability`; các phiên bản mới với OpenTelemetry còn cho phép chọn sampler như `parent-based-trace-id-ratio`. Staging có thể nâng sampling trong cửa sổ kiểm thử để kiểm chứng release; production cần tỷ lệ dựa trên traffic, SLO, dung lượng và ngân sách.

Head sampling giảm lưu lượng ngay tại ứng dụng nhưng không thể chọn trace dựa trên lỗi hoặc latency xuất hiện sau quyết định. Tail sampling tại Collector có thể giữ trace lỗi/chậm, nhưng cần nhận đủ candidate spans, chờ dữ liệu, cấp đủ memory và định tuyến mọi span cùng trace đến cùng sampler. Với Spring Modulith, hãy xác minh module spans và event listener context trước khi kết luận một nhánh không được quan sát. Cuối cùng, dùng metrics cho thống kê toàn traffic, traces cho điều tra các lần thực thi được chọn, và audit/business records cho bằng chứng nghiệp vụ cần lưu đầy đủ.

## Tài liệu tham khảo

- [Spring Boot — Tracing và Sampling](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [OpenTelemetry — Sampling Concepts](https://opentelemetry.io/docs/concepts/sampling/).
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/).
- [OpenTelemetry Collector Contrib — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md).
