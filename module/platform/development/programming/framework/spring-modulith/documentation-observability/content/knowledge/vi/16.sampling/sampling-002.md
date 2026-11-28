# Sampling probability và tỷ lệ thu thập

Trong ứng dụng Spring Boot, một request có thể tạo nhiều span: HTTP server span, module entry span của `orders`, span của `payments` và các span gọi database hoặc dịch vụ bên ngoài. Khi lưu mọi trace ở lưu lượng lớn, chi phí truyền, lưu trữ và truy vấn tăng nhanh. **Sampling** quyết định trace nào được giữ lại để xuất tới hệ thống tracing; **sampling probability** là xác suất/tỷ lệ mục tiêu của một bộ lấy mẫu xác suất.

Với Spring Boot, thuộc tính thường dùng là `management.tracing.sampling.probability`. Giá trị mặc định được tài liệu Spring Boot mô tả là **0.1 (10%)**. Nếu đặt `1.0`, các trace gốc đủ điều kiện được sampler chọn toàn bộ; nếu đặt `0.0`, sampler tỷ lệ không chọn trace gốc nào. Tuy nhiên, số trace thu được trong một cửa sổ quan sát **không nhất thiết bằng chính xác tỷ lệ cấu hình**, và quyết định của trace cha trong hệ thống phân tán có thể ảnh hưởng các span con.

Bài thuộc chương **Sampling**, trong mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mục tiêu của mô-đun là dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Bài này giải thích xác suất sampling, cách tính tỷ lệ thu thập, các sampler của OpenTelemetry và cách lựa chọn chính sách phù hợp.

> Ví dụ cấu hình chính dùng Spring Boot 4.2 và Spring Modulith 2.2 tương thích. Các thuộc tính tracing cơ bản cũng xuất hiện ở các nhánh Boot trước đó, nhưng danh sách sampler và tên starter phụ thuộc phiên bản. Đối chiếu tài liệu của BOM thực tế trước khi áp dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sampling, sampling probability, sampled trace và tỷ lệ thu thập thực tế.
2. Tính số trace kỳ vọng từ lưu lượng request và xác suất sampling.
3. Hiểu vì sao 10% sampling không có nghĩa cứ 10 request thì giữ đúng một trace.
4. Phân biệt head sampling và tail sampling.
5. Đọc hành vi của `parent-based-trace-id-ratio` và các sampler OpenTelemetry được Spring Boot hỗ trợ.
6. Cấu hình sampling probability trong `application.yml`.
7. Giải thích ảnh hưởng của sampled flag từ trace cha tới các service/module con.
8. Phân biệt sampling của tracing với metrics, logging, module graph và event publication registry.
9. Chọn sampling strategy phù hợp cho local development, staging và production.
10. Chẩn đoán trace thiếu, trace không đầy đủ hoặc tỷ lệ thu thập khác kỳ vọng.

## 2. Sampling là gì?

**Sampling** là chọn một phần trace/span để ghi nhận và gửi tới backend tracing. Khi lưu lượng tăng, sampling giúp giảm:

- Số lượng spans được xuất.
- Băng thông từ ứng dụng tới collector/backend.
- Dung lượng lưu trữ và chi phí ingest.
- Tải truy vấn và hiển thị trong Jaeger, Zipkin, Tempo hoặc hệ thống tương đương.

Một trace có thể chứa nhiều span. Với sampler **parent-based**, quyết định thường được đưa ra ở root span rồi được các span con tuân theo, nhờ đó trace được giữ nhất quán hơn giữa các service.

~~~mermaid
flowchart TD
    R["Request mới / root span"] --> S{"Sampling decision"}
    S -->|"sampled"| K["Ghi nhận spans"]
    S -->|"not sampled"| D["Không xuất trace spans"]
    K --> E["Exporter / Collector"]
    E --> B["Trace backend"]
    D -. "Context có thể vẫn được truyền<br/>với sampled flag = 0" .-> C["Service downstream"]
~~~

Việc **không xuất span** không nhất thiết có nghĩa trace ID bị xóa khỏi context; trace context vẫn có thể được truyền để downstream biết parent và trạng thái sampled.

### 2.1. Sampling không phải context propagation

| Cơ chế | Câu hỏi | Tác động |
| --- | --- | --- |
| **Sampling** | Có ghi và xuất trace này không? | Quyết định giữ/bỏ dữ liệu span |
| **Context propagation** | Hoạt động tiếp theo có biết trace/span cha không? | Truyền trace ID, parent context và sampled flag qua thread/service |
| **Instrumentation** | Operation nào được tạo span? | Xác định các HTTP, database, module entry hoặc custom operations được quan sát |
| **Exporter** | Dữ liệu đã ghi được gửi tới đâu? | Chuyển spans đến collector/backend |

Vì thế, có thể **truyền trace context nhưng không xuất span** khi trace không được sampling. Ngược lại, nếu instrumentation hoặc exporter không hoạt động, đặt probability 1.0 cũng không tự tạo trace.

## 3. Sampling probability có nghĩa gì?

Trong cấu hình xác suất đơn giản, probability `p` nằm trong khoảng:

\[
0 \leq p \leq 1
\]

| Giá trị | Diễn giải |
| ---: | --- |
| `0.0` | Xác suất chọn trace gốc bằng 0% |
| `0.01` | Mục tiêu khoảng 1% trace gốc |
| `0.05` | Mục tiêu khoảng 5% |
| `0.1` | Mục tiêu khoảng 10%; mặc định Spring Boot được tài liệu hóa |
| `0.25` | Mục tiêu khoảng 25% |
| `0.5` | Mục tiêu khoảng 50% |
| `1.0` | Chọn 100% trace gốc đủ điều kiện theo sampler |

**Probability là tham số của sampler, không phải cam kết số lượng chính xác trên từng phút.** Nếu 100 request đến trong một cửa sổ nhỏ với p = 0.1, ta không thể đảm bảo chính xác 10 trace sẽ xuất hiện.

### 3.1. Số trace kỳ vọng

Nếu có `N` trace gốc độc lập và cùng xác suất sampling `p`, số trace được giữ kỳ vọng là:

\[
E[X] = N \times p
\]

| Trace gốc trong kỳ | Probability | Số trace kỳ vọng |
| ---: | ---: | ---: |
| 1.000 | 0.1 | 100 |
| 10.000 | 0.1 | 1.000 |
| 50.000 | 0.05 | 2.500 |
| 100.000 | 0.01 | 1.000 |
| 20.000 | 0.5 | 10.000 |

Đây là **giá trị kỳ vọng**, không phải kết quả bắt buộc của từng lần chạy.

### 3.2. Dao động quanh giá trị kỳ vọng

Với mô hình Bernoulli độc lập, độ lệch chuẩn của số trace được chọn là:

\[
\sigma = \sqrt{N p (1-p)}
\]

Ví dụ `N = 1.000`, `p = 0.1`:

\[
E[X] = 100,\qquad
\sigma = \sqrt{1000 \times 0.1 \times 0.9} \approx 9.49
\]

Trong mô hình xấp xỉ chuẩn khi số mẫu đủ lớn, khoảng `E[X] \pm 2\sigma` chứa phần lớn kết quả. Với ví dụ này, số trace thực tế quanh **81 đến 119** vẫn không bất thường.

Con số trên giúp hiểu dao động thống kê. Sampler ratio theo trace ID có thể dùng quyết định xác định từ ID/hash thay vì tung đồng xu độc lập mỗi request; với tập trace ID phân bố phù hợp, tỷ lệ tổng thể vẫn tiến gần probability mục tiêu khi số lượng đủ lớn.

### 3.3. Vì sao cửa sổ ngắn dễ lệch?

Giả sử p = 0.1:

- 10 trace gốc: có thể không có trace nào được chọn, hoặc có 1–3 trace.
- 100 trace gốc: kết quả thường gần 10 hơn, nhưng vẫn có dao động.
- 100.000 trace gốc: tỷ lệ tổng thể thường ổn định hơn nếu traffic và sampler đồng nhất.

Đừng kết luận sampler sai chỉ vì một phút có 7% hoặc 14% trace được thu thập. Hãy xem cửa sổ dài hơn, số lượng gốc đủ lớn và các service có đang dùng cùng chính sách hay không.

## 4. Cấu hình sampling trong Spring Boot

Spring Boot cung cấp thuộc tính `management.tracing.sampling.probability`. Giá trị mặc định được tài liệu hóa là `0.1`.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Đặt sampling 100% trong lab:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Hoặc tắt sampling của trace gốc bằng ratio sampler:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.0
~~~

**Lưu ý:** Ý nghĩa cuối cùng còn phụ thuộc sampler implementation. Với OpenTelemetry và sampler parent-based mặc định, probability áp dụng cho **root trace chưa có parent**; child spans sẽ tuân theo sampled decision của parent. Vì vậy, `1.0` ở một service không tự biến trace upstream đã đánh dấu unsampled thành sampled.

### 4.1. Dependency ví dụ với OpenTelemetry

Trong dự án Spring Boot 4.2 đã quản lý version qua BOM:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Cấu hình export OTLP/HTTP minh họa:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
~~~

Cần có collector/backend nhận dữ liệu ở endpoint đó. Probability chỉ quyết định trace có được sampler giữ hay không; nó không thay thế dependency tracer, instrumentation, exporter hoặc network.

### 4.2. Chọn sampler OpenTelemetry

Với OpenTelemetry trong Spring Boot, có thể cấu hình sampler qua `management.opentelemetry.tracing.sampler`.

| Sampler | Hành vi |
| --- | --- |
| `always-on` | Sample mọi trace/span được sampler xử lý |
| `always-off` | Không sample trace/span |
| `trace-id-ratio` | Chọn một tỷ lệ theo trace ID và `management.tracing.sampling.probability` |
| `parent-based-always-on` | Nếu có parent, theo sampled decision của parent; nếu không có parent, luôn sample |
| `parent-based-always-off` | Nếu có parent, theo sampled decision của parent; nếu không có parent, không sample |
| `parent-based-trace-id-ratio` | Nếu có parent, theo sampled decision của parent; nếu không có parent, dùng tỷ lệ theo trace ID |

Sampler mặc định của Spring Boot khi dùng OpenTelemetry là **`parent-based-trace-id-ratio`**. Nếu không khai báo sampler, vẫn có thể điều chỉnh xác suất bằng `management.tracing.sampling.probability`.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Trong ví dụ, root trace được chọn theo tỷ lệ 10%; các child spans theo quyết định của parent. Đây là lựa chọn phù hợp cho distributed trace cần tính nhất quán qua nhiều service.

**Không áp dụng thuộc tính sampler OpenTelemetry này cho Brave một cách máy móc.** Với Brave, cách cấu hình sampler và exporter phụ thuộc tích hợp Micrometer Tracing/Boot tương ứng; hãy dùng tài liệu đúng bridge.

## 5. Head sampling và tail sampling

- **Head sampling:** quyết định ngay khi trace/span bắt đầu, trước khi biết toàn bộ kết quả của request.
- **Tail sampling:** đợi nhận được phần lớn hoặc toàn bộ trace rồi mới quyết định giữ/bỏ dựa trên dữ liệu đã quan sát.

~~~mermaid
flowchart TB
    subgraph H["Head sampling — SDK"]
        A["Root span bắt đầu"] --> B{"Sampler quyết định sớm"}
        B -->|"keep"| C["Gửi spans được sample"]
        B -->|"drop"| D["Không xuất spans"]
    end
    subgraph T["Tail sampling — Collector"]
        E["Collector nhận spans"] --> F["Buffer theo trace ID"]
        F --> G["Đánh giá status / latency / attributes"]
        G -->|"keep"| I["Export trace"]
        G -->|"drop"| J["Bỏ trace"]
    end
~~~

### 5.1. Head sampling

Ưu điểm:

- Quyết định sớm, đơn giản và chi phí thấp.
- Giảm dữ liệu ngay tại ứng dụng/SDK trước khi gửi qua mạng.
- Phù hợp hệ thống có lưu lượng lớn và cần tỷ lệ cố định.
- Dễ áp dụng parent-based để giữ trace nhất quán xuyên service.

Giới hạn quan trọng:

**Head sampler chưa biết kết quả tương lai.** Khi root span bắt đầu, nó chưa biết request sẽ trả 500, mất 5 giây hay đi qua một listener lỗi sau đó. Vì vậy, head sampling theo xác suất không thể bảo đảm “giữ 100% trace lỗi” chỉ dựa trên error xảy ra về sau.

Nếu p = 0.1 và một request lỗi rơi vào 90% bị loại, ứng dụng không thể khôi phục trace đã không ghi/gửi từ đầu bằng cách nhìn thấy lỗi ở cuối request.

### 5.2. Tail sampling

Tail sampler thường đặt trong **OpenTelemetry Collector**. Collector buffer spans theo trace ID, chờ một khoảng thời gian rồi áp dụng policy, ví dụ:

- Giữ trace có span status `ERROR`.
- Giữ trace có tổng duration vượt ngưỡng.
- Giữ trace có attribute cụ thể.
- Giữ một tỷ lệ xác suất của phần trace còn lại.

Ví dụ cấu hình rút gọn cho Collector Contrib:

~~~yaml
processors:
  tail_sampling:
    decision_wait: 10s
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
      - name: sample-rest
        type: probabilistic
        probabilistic:
          sampling_percentage: 5
~~~

Đây là **cấu hình phía Collector**, không phải `application.yml` của Spring Boot. Để tail sampling đánh giá được trace, Collector phải nhận được các spans liên quan trước khi quyết định. Cấu hình pipeline, phiên bản Collector Contrib, policy semantics và exporter cần được kiểm tra theo deployment thực tế.

### 5.3. Các điều kiện vận hành của tail sampling

1. Collector phải **buffer trace** trong lúc chờ quyết định; cần RAM và giới hạn `num_traces`.
2. `decision_wait` quá ngắn có thể ra quyết định trước khi span cuối cùng đến.
3. Các spans cùng trace ID phải được định tuyến tới **cùng một Collector instance/shard** để quyết định trên đủ dữ liệu.
4. Nếu SDK đã head-sample và loại 90% trace trước khi gửi, tail sampler chỉ thấy 10% còn lại; nó không thể khôi phục 90% đã bị loại.
5. Collector phải có khả năng chịu tải, theo dõi số trace bị drop do thiếu buffer và độ trễ quyết định.

Nếu mục tiêu là giữ trace lỗi theo status/latency, thường cần cấu hình SDK gửi đầy đủ dữ liệu cần thiết tới Collector (ví dụ sampler phù hợp như `always-on` ở đầu vào của pipeline tail sampling), sau đó để Collector quyết định. Phải thiết kế nhất quán ở các service tham gia trace; chỉ đổi một service có thể vẫn làm thiếu spans.

### 5.4. So sánh nhanh

| Tiêu chí | Head sampling | Tail sampling |
| --- | --- | --- |
| Thời điểm quyết định | Khi span/trace bắt đầu | Sau khi Collector nhận đủ dữ liệu theo chính sách |
| Biết lỗi/latency cuối cùng? | Không | Có thể, nếu span chứa thông tin và đến kịp |
| Giảm băng thông từ SDK? | Có, loại span trước export | Không nếu SDK gửi tất cả tới Collector |
| Nơi cấu hình | SDK / Spring Boot sampler | Collector processor |
| Tài nguyên chính | Ứng dụng/SDK và backend nhận | RAM/buffer/CPU của Collector |
| Giữ 100% trace lỗi? | Không thể chỉ bằng probability head sampling | Có thể theo policy, nếu Collector nhận đủ trace và policy được cấu hình đúng |

## 6. Parent-based sampling và trace phân tán

Một request có thể đi qua gateway, service orders và service payments. Mỗi service đều có sampler, nhưng để trace không bị cắt khúc, child service cần tôn trọng quyết định của parent theo trace context.

~~~mermaid
sequenceDiagram
    participant G as API Gateway
    participant O as orders
    participant P as payments
    G->>G: Root sampler quyết định
    G->>O: HTTP + traceparent
    Note over O: Parent-based sampler<br/>đọc sampled flag
    O->>P: HTTP + traceparent
    Note over P: Tiếp tục quyết định<br/>của parent
~~~

### 6.1. Traceparent và sampled flag

Với W3C Trace Context, header `traceparent` chứa trace ID, parent span ID và flags. Bit sampled thể hiện parent mong muốn trace được ghi nhận theo quyết định sampling trước đó.

- Parent sampled: parent-based sampler ở service con tiếp tục sample child.
- Parent not sampled: parent-based sampler thường không sample child.
- Không có parent: sampler quyết định như một root trace mới.

Điều này giúp các service không tự đưa ra những quyết định mâu thuẫn cho cùng trace. Các service cần tương thích về propagator và sampling policy.

### 6.2. Vì sao probability 1.0 vẫn có thể không thấy trace?

Một tình huống thường gặp:

- Gateway nhận request và quyết định `sampled=0`.
- Gateway truyền trace context unsampled sang `orders`.
- `orders` dùng `parent-based-trace-id-ratio` với probability 1.0.
- Sampler của `orders` tôn trọng parent unsampled nên child vẫn không được sample.

Do đó, **1.0 không phải lệnh cưỡng ép resample mọi trace đã bị upstream loại** khi dùng parent-based sampler. Nếu muốn đổi chính sách ở ranh giới dịch vụ, phải hiểu rõ semantics và tác động tới trace completeness; tránh tự ý bỏ parent decision làm trace bị chia đoạn hoặc duplicate.

### 6.3. Các service cấu hình khác nhau

| Service | Probability | Sampler |
| --- | ---: | --- |
| Gateway | 0.1 | parent-based ratio |
| Orders | 1.0 | parent-based ratio |
| Payments | 0.1 | parent-based ratio |

Với một root trace được gateway chọn, orders và payments tiếp tục sample theo parent. Với root trace bị gateway loại, các child thông thường không được sample. Vì vậy, không thể cộng riêng tỷ lệ của từng service để tính tỷ lệ toàn trace.

Nếu có service dùng sampler độc lập không tôn trọng parent, backend có thể nhận **một phần trace** hoặc các đoạn trace rời rạc. Khi điều tra, xem trace ID, parent span ID và sampled flags tại từng ranh giới.

## 7. Đo tỷ lệ thu thập thực tế

Sampling probability là **cấu hình**. Tỷ lệ thu thập thực tế phải đo từ dữ liệu đầu vào và dữ liệu đã được sampler/exporter giữ lại.

\[
\text{Observed sampling ratio}
=
\frac{\text{Số trace được backend nhận}}
{\text{Số trace gốc đủ điều kiện}}
\]

Ví dụ trong một giờ:

- Gateway ghi nhận 10.000 root requests đủ điều kiện.
- Backend có 1.020 traces tương ứng.
- Tỷ lệ quan sát xấp xỉ:

\[
\frac{1\,020}{10\,000}=10.2\%
\]

Con số 10.2% gần mục tiêu 10%. Tuy nhiên, mẫu số phải được định nghĩa nhất quán: request nào tạo root trace, request loại health-check nào được loại trước, có upstream parent không, có retry hoặc nhiều root operation cho cùng một business transaction không.

### 7.1. Đừng lấy tổng span chia tổng request

Một trace có thể có 1 span hoặc 30 spans. Vì vậy, `số spans / số requests` không phải sampling ratio. Tỷ lệ cần tính theo **trace gốc/trace đủ điều kiện**, không phải số spans.

Cũng không nên lấy số trace trong UI chia số log lines: một trace có thể có hàng trăm log, hoặc không có log nào.

### 7.2. Tỷ lệ export khác tỷ lệ sampler

| Tỷ lệ | Ý nghĩa |
| --- | --- |
| **Sampler decision ratio** | Tỷ lệ root traces được sampler chọn |
| **Exporter delivery ratio** | Tỷ lệ spans/trace được export thành công tới collector |
| **Backend ingest ratio** | Tỷ lệ dữ liệu collector/backend thực sự nhận và lưu được |

Nếu sampler chọn 10% nhưng exporter lỗi hoặc collector drop dữ liệu, backend có thể nhận ít hơn 10%. Muốn chẩn đoán cần metrics/logs của SDK exporter, Collector và backend.

### 7.3. Thử nghiệm xác suất trong lab

1. Đặt `probability: 1.0`, gửi 1.000 request và xác nhận gần như toàn bộ trace đủ điều kiện được ghi/export.
2. Đặt `probability: 0.1`, gửi 10.000 request và đếm số root traces ở backend.
3. Lặp lại nhiều lần với cùng điều kiện.
4. So sánh observed ratio với 10%, không đòi mỗi lần đúng chính xác 10%.
5. Kiểm tra lỗi export, sampling ở gateway và các upstream parent trước khi kết luận.

Không dùng số liệu từ một tải thử nhỏ để suy ra tỷ lệ ổn định của production.

## 8. Sampling ảnh hưởng gì trong Spring Modulith?

Spring Modulith bổ sung quan sát ở ranh giới application module. Khi bật instrumentation, một request có thể tạo module entry spans với metadata như:

- `module.identifier`
- `module.name`
- `module.invocation-type`
- `module.method`

Nếu root trace được sample và các span con tuân theo parent, module entry spans có thể xuất hiện trong trace backend. Nếu root trace bị loại ở head sampling, module spans thường không được export như các trace spans được sample.

### 8.1. Sampling không tắt module instrumentation

Cần phân biệt:

- **Instrumentation:** framework tạo observation/span cho operation.
- **Sampling:** sampler quyết định có ghi/export span hay không.
- **Export:** exporter gửi span đã được ghi tới collector/backend.

Có thể instrumentation vẫn chạy nhưng span không được export vì sampling. Không thấy module span trong UI chưa chứng minh module không được gọi.

### 8.2. Sampling không làm giảm event publication metrics

Spring Modulith có các metric publication như `module.events.published`. Metrics được ghi qua `MeterRegistry`; tracing sampling quyết định trace nào được giữ. Hai pipeline này độc lập.

| Tín hiệu | Sau 1.000 lần publish event với trace sampling 10% |
| --- | --- |
| Event publication counter | Có thể tăng khoảng 1.000 nếu instrumentation và metric registry hoạt động đầy đủ |
| Root traces được sample | Kỳ vọng khoảng 100 trace nếu 1.000 root traces độc lập đủ điều kiện |
| Module entry spans được export | Phụ thuộc các trace chứa span, parent sampling, instrumentation và exporter |
| Listener completion | Cần Event Publication Registry hoặc metrics xử lý riêng |

**Không nhân `module.events.published` với 0.1 để ước lượng số event đã phát.** Metric publication không bị trace sampler giảm 90%.

### 8.3. Sampling không thay thế module graph hoặc Actuator

`GET /actuator/modulith` trả mô hình module/dependency. Module graph mô tả cấu trúc được nhận diện từ code; sampling không làm thay đổi đồ thị đó. Sampling chỉ tác động tới dữ liệu trace được thu thập.

Do vậy:

- Dùng module graph/Actuator để biết module và dependency.
- Dùng event metrics để đếm publication.
- Dùng tracing/module entry spans để phân tích các lần thực thi được sample.
- Dùng Event Publication Registry/logs để xem trạng thái xử lý event cụ thể.

## 9. Chọn probability theo môi trường

Không có một tỷ lệ tối ưu cho mọi ứng dụng. Hãy cân nhắc lưu lượng, độ quan trọng nghiệp vụ, chi phí lưu trữ, mục tiêu điều tra và khả năng tail sampling.

| Môi trường | Cách tiếp cận thường dùng | Mục tiêu |
| --- | --- | --- |
| Local development | `1.0` trong thời gian debug | Dễ quan sát mọi request trong lab |
| Integration test | Tỷ lệ cao hoặc `1.0` cho test cần assert trace | Tái hiện và kiểm tra quan hệ span |
| Staging | Tỷ lệ đủ lớn để quan sát tải đại diện; có thể bật 100% trong test ngắn | Phát hiện regression mà không tạo tải dữ liệu quá lớn |
| Production lưu lượng thấp | Có thể chọn tỷ lệ cao hơn | Trace đủ chi tiết với chi phí vừa phải |
| Production lưu lượng lớn | Chọn tỷ lệ theo ngân sách, có thể kết hợp tail sampling | Giới hạn ingest nhưng giữ trace có giá trị điều tra |

Các dòng trên là **hướng dẫn quyết định**, không phải tỷ lệ khuyến nghị cố định. Trước khi tăng sampling ở production, cần xem dung lượng backend, ingest quotas, retention, độ nhạy dữ liệu và lưu lượng đỉnh.

### 9.1. Tăng sampling có chi phí

Nếu hệ thống tạo 100.000 root traces mỗi giờ:

| Probability | Số trace kỳ vọng mỗi giờ |
| ---: | ---: |
| 1.0 | 100.000 |
| 0.5 | 50.000 |
| 0.1 | 10.000 |
| 0.05 | 5.000 |
| 0.01 | 1.000 |

Đây mới là số trace; số span và dung lượng bytes phụ thuộc số operation, attributes, events, resource metadata và payload span. Một trace dài với nhiều span có thể tốn hơn trace ngắn nhiều lần.

### 9.2. Không hạ sampling chỉ để sửa exporter lỗi

Nếu backend nhận thiếu trace vì Collector quá tải, exporter timeout, network chập chờn, Collector drop do thiếu buffer hoặc backend vượt ingest quota, hạ probability có thể giảm áp lực nhưng cần đo đúng nơi drop. Đừng coi tỷ lệ sampler là nguyên nhân duy nhất khi exporter delivery hoặc backend ingestion mới là nút thắt.

## 10. Cấu hình minh họa theo mục tiêu

### 10.1. Local lab: thu thập tối đa trace gốc

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Dùng khi debug ngắn hạn, với lưu lượng thấp và kiểm soát được upstream parent. Nếu parent từ bên ngoài đã unsampled, parent-based sampler vẫn có thể không tạo trace đầy đủ ở service này.

### 10.2. Production: ratio 5%

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Với root traces mới, mục tiêu khoảng 5%; child spans tôn trọng parent. Đánh giá số trace thực tế, chi phí ingest và khả năng điều tra trước khi chọn tỷ lệ dài hạn.

### 10.3. Không ghi trace ở SDK

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.0
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Với root trace mới, sampler ratio chọn 0. Không dùng cấu hình này nếu vẫn cần trace để điều tra; metrics/logging có thể vẫn hoạt động nhưng không thay thế trace spans.

### 10.4. Collector tail sampling cho lỗi và trace chậm

~~~text
Spring Boot services
  SDK gửi spans cần thiết
        |
        v
OpenTelemetry Collector
  tail_sampling processor
    - giữ trace có ERROR
    - giữ trace latency > ngưỡng
    - sample xác suất phần còn lại
        |
        v
Trace backend
~~~

Ở đầu vào, SDK phải gửi đủ dữ liệu để Collector có thể đánh giá. Với OpenTelemetry, có thể chọn sampler phù hợp như `always-on` cho pipeline được tail-sample; nhưng cần kiểm soát lưu lượng đến Collector và cấu hình nhất quán giữa các service. Tail sampling có thể giảm dữ liệu ở bước Collector → backend, nhưng không giảm lượng span SDK gửi đến Collector.

## 11. Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Probability 0.1 nghĩa cứ 10 request giữ đúng một.” | Đây là xác suất/tỷ lệ mục tiêu; kết quả cửa sổ nhỏ dao động. |
| “1.0 bảo đảm service luôn có trace.” | Chỉ đúng với trace gốc đủ điều kiện, sampler phù hợp, instrumentation/exporter hoạt động và parent policy không loại trace. |
| “Không thấy module span nghĩa module không được gọi.” | Có thể trace bị sampling bỏ hoặc span không được export. |
| “Sampling giảm 90% event metrics.” | Không; event publication metrics là pipeline khác với trace sampling. |
| “Tất cả spans được lấy mẫu độc lập.” | Parent-based sampler thường làm child theo quyết định parent để giữ trace nhất quán. |
| “Head sampling có thể giữ mọi trace có ERROR.” | Head sampler không biết lỗi tương lai khi quyết định root span. |
| “Tail sampling có thể khôi phục trace SDK đã drop.” | Không; Collector chỉ đánh giá spans đã nhận. |
| “Tail sampling chỉ cần thêm processor là xong.” | Cần buffer, decision wait, routing theo trace ID, sizing và giám sát Collector. |
| “Mỗi service có thể chọn tỷ lệ tùy ý mà trace vẫn đầy đủ.” | Khác biệt sampler/propagator có thể làm trace bị chia hoặc thiếu spans. |
| “Sampling probability là tỷ lệ backend ingest.” | Còn exporter delivery, collector drop, tail policy và backend ingest. |
| “Giảm sampling là cách duy nhất giảm chi phí.” | Có thể tối ưu attributes, span volume, retention, collector policies và instrumentation. |
| “Sampling và context propagation là một.” | Sampling chọn dữ liệu; propagation truyền trace context và quan hệ parent. |

## 12. Quy trình chẩn đoán khi tỷ lệ thu thập sai kỳ vọng

Khi probability cấu hình 10% nhưng backend chỉ thấy 2% hoặc 30%, hãy kiểm tra theo lớp:

1. **Xác định mẫu số:** đang đếm root requests, traces, spans hay business transactions?
2. **Xem sampler:** `management.tracing.sampling.probability` có được bind đúng profile/environment không?
3. **Xem sampler type:** OTel đang dùng `parent-based-trace-id-ratio`, `trace-id-ratio` hay sampler khác?
4. **Kiểm tra parent sampled flag:** upstream có truyền trace context unsampled không?
5. **Kiểm tra instrumentation:** có phải mọi request đều tạo root span? Có filter bỏ health-check hoặc route đặc biệt?
6. **Kiểm tra exporter:** spans được sample có gửi thành công tới collector không?
7. **Kiểm tra Collector:** tail policy, memory limit, `decision_wait`, routing theo trace ID và dropped traces.
8. **Kiểm tra backend:** ingest quotas, retention, query time range và service name filter.
9. **So sánh cửa sổ đủ lớn:** traffic nhỏ có thể dao động; đừng kết luận từ một vài request.

### 12.1. Triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Probability 1.0 nhưng không có trace | Upstream parent unsampled, tracer/exporter không hoạt động | Kiểm tra parent context, sampler, dependency, collector |
| Probability 0.1 nhưng backend gần 0% | Exporter/Collector drop, profile override, parent unsampled | Kiểm tra config runtime và pipeline |
| Probability 0.1 nhưng backend >10% | Đếm span thay trace, có nhiều root traces, upstream policy khác, tail sampling | Chuẩn hóa mẫu số và xem sampler ở từng tầng |
| Trace thiếu span module con | Child instrumentation/propagation khác, sampled flag không nhất quán, exporter drop | Kiểm tra service con, parent span, exporter |
| Trace lỗi không xuất hiện | Head sampling bỏ trước khi lỗi xảy ra | Xem tail sampling hoặc targeted debug policy |
| Metrics event vẫn tăng nhưng trace ít | Trace sampling thấp là hành vi bình thường | Phân biệt metrics với tracing |
| Trace ID có trong log nhưng backend không có trace | Log context được tạo nhưng trace bị drop hoặc export lỗi | Kiểm tra sampled decision và exporter |
| Collector tail sampler thiếu spans | `decision_wait` quá ngắn, routing không gom cùng trace, buffer đầy | Kiểm tra trace-aware load balancing và Collector metrics |

## 13. Bài thực hành

### Bài 1 — Tính kỳ vọng sampling

Một ứng dụng nhận 20.000 root traces trong một giờ. Tính số trace kỳ vọng ở `p = 1.0`, `p = 0.25`, `p = 0.1` và `p = 0.01`.

**Đáp án định hướng:** 20.000; 5.000; 2.000; 200. Đây là kỳ vọng, không phải số đếm chính xác của mọi giờ.

### Bài 2 — Quan sát dao động

Đặt `p = 0.1`, gửi 100 request trong ba lần chạy. Ghi số trace backend nhận được. Giải thích vì sao ba kết quả có thể khác nhau dù cấu hình không đổi.

### Bài 3 — Parent-based sampling

Mô phỏng gateway, orders và payments. Cho gateway chọn root trace unsampled, rồi gửi trace context tới orders. Đặt orders probability = 1.0 với sampler `parent-based-trace-id-ratio`. Dự đoán child có được sample không và giải thích dựa trên parent sampled flag.

### Bài 4 — Head sampling và error

Đặt head sampling probability = 0.1. Tạo một endpoint lỗi có xác suất 100% trả 500. Giải thích vì sao backend không thấy tất cả các trace lỗi dù mọi request đều lỗi. Đề xuất cách giữ trace lỗi bằng tail sampling và các điều kiện cần có.

### Bài 5 — Phân biệt metric với trace

Gửi 1.000 domain events với trace sampling 10%. Kiểm tra `module.events.published` tăng bao nhiêu và backend nhận khoảng bao nhiêu root traces. Có thể suy số listener thành công từ hai con số đó không? Giải thích vai trò của Event Publication Registry nếu cần xác định completion.

### Bài 6 — Đo pipeline

Tạo bảng ghi số lượng ở bốn điểm: root traces đủ điều kiện, traces sampler chọn, spans exporter gửi thành công và traces backend ingest. Tìm tầng có tỷ lệ giảm lớn nhất; không gộp các tỷ lệ này thành một con số không rõ mẫu số.

## 14. Câu hỏi ôn tập

1. `management.tracing.sampling.probability` nhận giá trị trong khoảng nào?
2. Giá trị mặc định Spring Boot được tài liệu hóa là bao nhiêu?
3. Với 10.000 root traces và p = 0.1, số trace kỳ vọng là bao nhiêu?
4. Vì sao số trace thực tế không nhất thiết bằng số kỳ vọng?
5. `parent-based-trace-id-ratio` quyết định thế nào khi có parent và khi không có parent?
6. Vì sao service đặt p = 1.0 vẫn có thể không sample trace từ parent unsampled?
7. Head sampling khác tail sampling ở thời điểm ra quyết định nào?
8. Vì sao head sampling không thể bảo đảm giữ mọi trace có lỗi phát sinh về sau?
9. Tail sampling cần những điều kiện nào ở Collector?
10. Vì sao Collector không thể khôi phục span đã bị SDK drop?
11. Sampling có làm giảm `module.events.published` không?
12. Tỷ lệ sampler, exporter delivery và backend ingest khác nhau thế nào?
13. Vì sao không dùng tổng số spans chia tổng request để tính sampling ratio?
14. Khi module entry span không xuất hiện, cần kiểm tra những lớp nào trước khi kết luận module không chạy?

## 15. Ghi nhớ

**Sampling probability là xác suất/tỷ lệ mục tiêu để sampler chọn trace, không phải cam kết số lượng chính xác trên từng cửa sổ thời gian.** Spring Boot mặc định lấy mẫu 10% request theo tài liệu tracing; `management.tracing.sampling.probability` điều chỉnh giá trị từ 0.0 đến 1.0.

Với OpenTelemetry, sampler mặc định `parent-based-trace-id-ratio` chọn root trace theo tỷ lệ và để child spans tuân theo quyết định của parent. **Head sampling** giảm dữ liệu ngay ở SDK nhưng không thể dựa vào lỗi/latency xuất hiện sau đó; **tail sampling** có thể chọn theo kết quả tại Collector, đổi lại cần buffer, routing và tài nguyên phù hợp.

Trong Spring Modulith, sampling tác động đến module entry spans được xuất, **không làm giảm event publication metrics hay thay đổi module graph**. Để chẩn đoán đúng, hãy phân biệt sampler decision, context propagation, exporter delivery và backend ingest; đồng thời dùng metrics/registry cho các câu hỏi không thể trả lời từ trace đã lấy mẫu.

### Tài liệu tham khảo

- [Spring Boot 4.2 — Tracing: Sampling, probability và OpenTelemetry samplers](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Common Application Properties: management.tracing.sampling.probability](https://docs.spring.io/spring-boot/appendix/application-properties/index.html).
- [OpenTelemetry — Sampling concepts: Head sampling và Tail sampling](https://opentelemetry.io/docs/concepts/sampling/).
- [OpenTelemetry Collector Contrib — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor).
- [OpenTelemetry — Trace API and sampling specification](https://opentelemetry.io/docs/specs/otel/trace/sdk/).
- [Spring Modulith — Production-ready Features: Observing Application Modules và event metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html).
