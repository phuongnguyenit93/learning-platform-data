# Sampling trace là gì

## Mục tiêu học tập

Trong học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, Spring Modulith giúp sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Bài này giải thích **trace sampling**: cách chọn một tập traces để lưu và phân tích, cân bằng giữa khả năng điều tra, tải hệ thống và chi phí lưu trữ.

Sau bài học, bạn có thể:

1. Giải thích trace sampling là gì, đơn vị được chọn là trace hay span và vì sao cần lấy mẫu.
2. Phân biệt **head-based sampling**, **parent-based sampling** và **tail-based sampling**.
3. Tính xác suất, số traces kỳ vọng và hiểu vì sao tỷ lệ 10% không có nghĩa cứ đúng 10 request thì giữ một.
4. Cấu hình sampling trong Spring Boot bằng Micrometer Tracing, bao gồm xác suất mặc định và các sampler OpenTelemetry được hỗ trợ.
5. Giải thích vì sao parent-based sampling giúp giữ tính nhất quán của trace qua nhiều service.
6. Hiểu cách dùng OpenTelemetry Collector tail sampling để ưu tiên traces có lỗi, chậm hoặc thuộc luồng quan trọng.
7. Phân biệt ảnh hưởng của sampling lên module spans với metrics, logs và module graph.
8. Thiết kế chính sách sampling theo môi trường, lưu lượng, mức độ quan trọng và ngân sách.
9. Kiểm tra trace bị thiếu mà không kết luận nhầm rằng code không chạy hoặc nghiệp vụ không được thực hiện.

**Bối cảnh:** Micrometer Observation tạo điểm instrument chung; Micrometer Tracing kết nối observations với spans; Spring Modulith bổ sung các module entry observations cho tương tác tại ranh giới application module; exporter chuyển spans tới Zipkin, OpenTelemetry Collector hoặc backend khác. Sampling quyết định **trace/span nào được giữ trong pipeline tracing**, không thay thế module verification, event metrics, transaction hoặc đối soát nghiệp vụ.

> **Phạm vi phiên bản:** Các ví dụ Spring Boot dùng property theo tài liệu hiện hành của Spring Boot 4.2. Một số dòng Boot 3.x có khác biệt về dependency/exporter, nhưng property xác suất sampling thường là \`management.tracing.sampling.probability\`. Với OpenTelemetry, sampler cụ thể được cấu hình thêm qua \`management.opentelemetry.tracing.sampler\` ở các phiên bản hỗ trợ. Luôn kiểm tra reference guide đúng release của dự án.

---

## 1. Trace sampling là gì?

**Trace sampling** là kỹ thuật chọn một phần traces để tiếp tục ghi nhận, xuất và lưu trữ, thay vì giữ toàn bộ traces được tạo ra. Quyết định sampling có thể dựa trên xác suất, trạng thái của parent span, thuộc tính trace, lỗi, độ trễ hoặc chính sách vận hành.

Giả sử ứng dụng \`shop-service\` nhận 100.000 request trong một giờ. Mỗi request có thể tạo nhiều spans:

- HTTP server span;
- module entry span khi gọi \`inventory\`;
- database span;
- event listener span trong \`payments\`;
- HTTP client span tới payment provider.

Nếu mỗi request tạo trung bình 8 spans, hệ thống có thể tạo khoảng 800.000 spans trong giờ đó. Lưu và truy vấn toàn bộ có thể làm tăng CPU, mạng, dung lượng lưu trữ và chi phí backend.

Nếu chọn 10% traces theo một sampler xác suất, số traces được giữ kỳ vọng khoảng 10.000 trong giờ đó. Số spans thực tế còn phụ thuộc số spans trung bình của từng trace.

**Sampling không làm giảm số lần nghiệp vụ được thực hiện.** Nó quyết định dữ liệu tracing nào được giữ để quan sát. Request vẫn được xử lý, event vẫn được publish và transaction vẫn chạy theo logic ứng dụng dù trace tương ứng không được sample.

### 1.1. Vì sao cần sampling?

| Vấn đề | Sampling giúp gì? |
| --- | --- |
| Lưu lượng lớn tạo quá nhiều spans | Giảm số traces được xuất và lưu trữ. |
| Backend tracing có giới hạn ingest | Điều tiết lượng dữ liệu gửi tới backend. |
| Phần lớn request hoạt động bình thường | Giữ một mẫu đại diện để quan sát baseline. |
| Cần ưu tiên request lỗi hoặc chậm | Tail sampling có thể giữ trace dựa trên kết quả toàn trace. |
| Chi phí truy vấn và retention cao | Giảm dữ liệu cần lập chỉ mục và lưu lâu dài. |
| Cần kiểm tra một luồng cụ thể | Có thể tăng sampling trong local/test hoặc dùng chính sách ưu tiên có kiểm soát. |

Sampling có chi phí riêng: thiết kế chính sách, vận hành collector, giám sát dữ liệu bị loại và nguy cơ bỏ lỡ sự cố hiếm. Không nên coi sampling là giải pháp tự động làm hệ thống quan sát rẻ hơn trong mọi trường hợp.

## 2. Sampling chọn trace hay chọn span?

Trong distributed tracing, một trace thường bao gồm nhiều spans có cùng trace ID. Nếu mỗi span bị chọn độc lập, backend có thể nhận được một trace thiếu các đoạn quan trọng. Ví dụ chỉ thấy span payment provider mà không thấy span orders gọi nó.

Vì vậy, các chiến lược phổ biến cố gắng đưa ra quyết định **nhất quán ở cấp trace**:

- Quyết định tại root span rồi truyền trạng thái sampled xuống các spans con.
- Hoặc đợi collector nhận đủ phần lớn spans rồi quyết định giữ hay loại toàn bộ trace.

Cần phân biệt thuật ngữ:

| Đối tượng | Ý nghĩa |
| --- | --- |
| **Trace** | Nhóm các spans có quan hệ trong một lần thực thi được theo dõi. |
| **Span** | Một đơn vị công việc trong trace. |
| **Trace sampling** | Chính sách giữ/bỏ một trace hoặc các spans thuộc trace đó. |
| **Span sampling** | Quyết định trên từng span; nếu không phối hợp cẩn thận có thể tạo trace không đầy đủ. |
| **Sampled flag** | Trạng thái trong trace context cho biết trace được đánh dấu để ghi/xuất theo cơ chế propagation đang dùng. |

Trong Micrometer Tracing và OpenTelemetry, sampler thường được gọi khi span được tạo. Parent-based sampler giúp child spans tuân theo quyết định của parent, tạo một trace nhất quán. Tail sampling lại hoạt động sau đó ở tầng collector, khi đã nhận các spans từ nhiều phần của trace.

## 3. Xác suất sampling và số traces kỳ vọng

Một sampler xác suất thường có tham số \(p\) nằm trong khoảng từ 0 đến 1:

- \(p=0\): không chọn trace mới theo sampler ratio;
- \(p=0.1\): xác suất chọn khoảng 10%;
- \(p=0.5\): xác suất chọn khoảng 50%;
- \(p=1\): chọn tất cả traces đủ điều kiện theo sampler.

Nếu có \(N\) traces độc lập và xác suất chọn mỗi trace là \(p\), số traces được giữ \(S\) có kỳ vọng:

\[
E[S] = N \times p
\]

Ví dụ có 20.000 root traces và \(p=0.1\):

\[
E[S] = 20.000 \times 0.1 = 2.000
\]

Đây là **giá trị kỳ vọng**, không phải cam kết chính xác rằng cứ 10 trace thì giữ đúng 1 trace. Trong một khoảng thời gian nhỏ, số lượng thực tế có thể thấp hoặc cao hơn.

### 3.1. Ví dụ quy đổi theo lưu lượng

| Lưu lượng root traces | Sampling probability | Số traces kỳ vọng |
| ---: | ---: | ---: |
| 100.000 | 1% | 1.000 |
| 100.000 | 5% | 5.000 |
| 100.000 | 10% | 10.000 |
| 100.000 | 25% | 25.000 |
| 100.000 | 100% | 100.000 |

Đây là phép tính cho **số root traces đủ điều kiện** trong phạm vi đã chọn. Nó không trực tiếp cho biết số spans, byte dữ liệu hoặc chi phí backend vì mỗi trace có kích thước khác nhau.

### 3.2. Sampling không nhất thiết đều theo loại request

Một sampler dựa trên trace ID ratio thường cố chọn mẫu xác suất đại diện theo tỷ lệ cấu hình. Tuy nhiên, nếu request traffic có nhiều nhóm khác nhau, mẫu nhỏ vẫn có thể thiếu một nhóm hiếm.

Ví dụ:

- 99% request là xem danh mục;
- 0,5% request là thanh toán;
- 0,5% request là hoàn tiền.

Với sampling 1%, số trace thanh toán/hoàn tiền có thể rất ít hoặc không xuất hiện trong một cửa sổ ngắn. Nếu cần quan sát các luồng có rủi ro cao, cần cân nhắc chính sách theo thuộc tính hoặc tail sampling, đồng thời kiểm tra chi phí.

### 3.3. Công thức ước lượng tải

Có thể ước lượng sơ bộ:

\[
\text{sampled traces/sec}
\approx
\text{root traces/sec} \times p
\]

\[
\text{sampled spans/sec}
\approx
\text{sampled traces/sec} \times
\text{average spans per sampled trace}
\]

Nếu ứng dụng nhận 500 root traces/giây, \(p=0.1\), và mỗi trace có trung bình 12 spans:

\[
500 \times 0.1 \times 12 = 600
\]

Kỳ vọng khoảng 600 spans/giây được giữ. Đây chỉ là ước lượng; trace size và sampling có thể khác theo loại request.

## 4. Head-based sampling là gì?

**Head-based sampling** đưa ra quyết định sớm, thường khi root span bắt đầu hoặc khi span được tạo. Sampler chưa nhìn thấy toàn bộ trace, vì vậy chỉ có thể dựa vào thông tin sẵn có tại thời điểm đó:

- trace ID hoặc giá trị ngẫu nhiên;
- parent sampling decision;
- service hoặc operation nếu đã biết;
- một số thuộc tính đầu vào có sẵn;
- cấu hình sampler.

Ví dụ sampler chọn 10% root traces theo trace ID ratio. Nếu trace được chọn, các spans con tiếp tục được ghi theo chính sách parent-based. Nếu trace bị loại ở đầu, các spans phía sau thường không được export trong trace đó.

~~~mermaid
sequenceDiagram
    participant A as orders
    participant S as Head sampler
    participant B as inventory
    participant C as payments
    participant X as Trace backend

    A->>S: Tạo root span
    S->>S: Quyết định sampled / not sampled
    alt Trace được chọn
        S-->>A: Record và export
        A->>B: Gọi module API
        B-->>X: Module span
        A->>C: Gọi payment flow
        C-->>X: Payment span
    else Trace bị loại
        S-->>A: Không ghi/export theo trace
        A->>B: Nghiệp vụ vẫn chạy
        B-->>A: Không có span được giữ
        A->>C: Nghiệp vụ vẫn chạy
    end
~~~

Sơ đồ minh họa quyết định sớm và việc nghiệp vụ vẫn tiếp tục khi trace không được sample. Chi tiết record-only hoặc xử lý span có thể khác theo tracer implementation.

### 4.1. Ưu điểm của head sampling

- Quyết định sớm, dễ cấu hình.
- Giảm chi phí tạo/ghi/xuất spans ở phía ứng dụng.
- Không cần giữ toàn bộ trace trong bộ nhớ collector để đợi quyết định.
- Có thể hoạt động ở từng service nếu trace context được truyền nhất quán.
- Dễ ước lượng lưu lượng theo xác suất.

### 4.2. Hạn chế của head sampling

Sampler chưa biết kết quả cuối nên không thể đảm bảo chọn tất cả trace lỗi hoặc chậm. Một request ban đầu trông bình thường có thể thất bại sau khi gọi payment provider; nếu bị loại ở đầu, backend không có trace đầy đủ để điều tra.

Head sampler cũng không nên được cấu hình độc lập tùy tiện ở mỗi service. Nếu các service tự đưa ra quyết định khác nhau mà không tôn trọng parent, một trace có thể bị thiếu spans hoặc bị chia thành nhiều phần.

## 5. Parent-based sampling là gì?

**Parent-based sampling** cho child span kế thừa quyết định sampling từ parent span khi có parent context hợp lệ. Với root trace, một root sampler quyết định xác suất; với child spans, parent-based sampler giữ tính nhất quán.

Ví dụ:

1. Service \`orders\` nhận request và root sampler chọn trace.
2. Trace context có trạng thái sampled được inject vào HTTP header khi gọi \`inventory\`.
3. Service \`inventory\` extract parent context.
4. Child/server span của inventory tuân theo quyết định parent.
5. Các lời gọi tiếp theo tiếp tục theo cùng trace decision.

Nếu root được sample, các service downstream có thể tiếp tục cùng trace. Nếu root không được sample, child spans thường không tự ý tạo một trace đầy đủ riêng biệt cho cùng request.

### 5.1. Vì sao parent-based quan trọng?

| Không nhất quán | Parent-based |
| --- | --- |
| Mỗi service có thể chọn/bỏ span riêng. | Child spans tuân theo quyết định của parent. |
| Trace có thể thiếu đoạn giữa. | Dễ giữ cấu trúc trace xuyên dịch vụ. |
| Tỷ lệ sample có thể khác không có chủ đích. | Root sampler quyết định tỷ lệ; downstream giữ quyết định. |
| Khó diễn giải trace bị phân mảnh. | Dễ truy nguyên hơn khi propagation hoạt động đúng. |

Parent-based sampling không tự khắc phục mọi lỗi propagation. Nếu client không inject context hoặc server không extract, dịch vụ đích có thể coi request là root mới và đưa ra quyết định độc lập.

### 5.2. Parent-based không phải tail sampling

Parent-based sampler quyết định dựa trên trạng thái của parent **trước khi toàn trace kết thúc**. Tail sampling đợi dữ liệu trace đến collector rồi mới đánh giá các spans, chẳng hạn kiểm tra có lỗi hoặc vượt ngưỡng latency hay không.

## 6. Tail-based sampling là gì?

**Tail-based sampling** đưa ra quyết định sau khi collector nhận được toàn bộ hoặc phần lớn spans của trace. Khi đó, hệ thống có thể xét kết quả cuối cùng:

- trace có span báo lỗi hay không;
- tổng thời gian trace có vượt ngưỡng hay không;
- có operation hoặc service quan trọng hay không;
- có thuộc nhóm người dùng/luồng được ưu tiên theo chính sách hay không;
- có thỏa tỷ lệ lấy mẫu nền cho các trace bình thường hay không.

Ví dụ chính sách:

- giữ 100% traces có lỗi;
- giữ 100% traces chậm hơn 1 giây;
- giữ 5% traces thành công và nhanh để có mẫu baseline.

~~~mermaid
flowchart TD
    A["Các service tạo spans"] --> B["OpenTelemetry Collector"]
    B --> C["Tập hợp spans theo trace ID"]
    C --> D["Chờ decision window"]
    D --> E{"Trace có lỗi?"}
    E -->|"Có"| K["Giữ trace"]
    E -->|"Không"| F{"Latency vượt ngưỡng?"}
    F -->|"Có"| K
    F -->|"Không"| G{"Nằm trong sample nền 5%?"}
    G -->|"Có"| K
    G -->|"Không"| H["Loại trace"]
    K --> I["Exporter"]
    I --> J["Tracing backend"]
~~~

Tail sampling có khả năng ưu tiên những trace có giá trị điều tra cao hơn head sampling, vì quyết định được đưa ra khi đã có thêm thông tin.

### 6.1. Ưu điểm của tail sampling

- Có thể giữ mọi trace có lỗi theo chính sách.
- Có thể ưu tiên trace vượt ngưỡng latency.
- Có thể xét thuộc tính xuất hiện ở các span cuối của workflow.
- Có thể kết hợp các chính sách: lỗi, chậm và một tỷ lệ nền của traffic bình thường.
- Phù hợp khi muốn giảm dữ liệu lưu trữ nhưng vẫn giữ trace bất thường.

### 6.2. Chi phí và hạn chế của tail sampling

- Collector phải giữ trạng thái và bộ nhớ cho các trace đang chờ quyết định.
- Phải đặt decision window; trace đến muộn có thể bị tách hoặc bỏ lỡ quyết định.
- Tăng độ phức tạp vận hành và cần theo dõi bộ nhớ, throughput, queue, dropped spans.
- Khi có nhiều collector, các spans cùng trace phải được định tuyến tới cùng nơi xử lý tail sampling.
- Tail sampling không thể khôi phục spans mà SDK hoặc một tầng upstream đã loại bỏ trước khi gửi tới collector.

**Điều kiện quan trọng:** Nếu muốn tail sampler giữ mọi trace có lỗi, SDK phải gửi đủ spans ứng viên đến collector. Nếu head sampler ở ứng dụng đã bỏ 90% traces, tail sampler chỉ có thể đánh giá 10% còn lại; nó không thể phát hiện lỗi trong 90% đã bị loại.

## 7. So sánh head, parent-based và tail sampling

| Tiêu chí | Head-based | Parent-based | Tail-based |
| --- | --- | --- | --- |
| Thời điểm quyết định | Khi span/root bắt đầu. | Khi tạo span con, dựa trên parent; root dùng root sampler. | Sau khi collector nhận đủ hoặc phần lớn trace. |
| Dữ liệu dùng để quyết định | Thông tin có ở đầu trace. | Sampling state của parent và root policy. | Kết quả/thuộc tính từ nhiều spans. |
| Giữ tất cả lỗi | Không đảm bảo. | Không đảm bảo nếu root đã bị loại. | Có thể theo policy nếu collector nhận trace đầy đủ. |
| Chi phí phía ứng dụng | Thường thấp hơn vì có thể loại sớm. | Thấp và giúp nhất quán trace. | Thường phải gửi nhiều dữ liệu tới collector trước khi loại. |
| Chi phí collector | Thấp hơn tương đối. | Thấp hơn tương đối. | Cao hơn do buffer, state và decision window. |
| Phù hợp | Traffic lớn, cần giảm tải đơn giản. | Distributed tracing cần tính nhất quán giữa services. | Cần ưu tiên lỗi/trace chậm theo kết quả toàn trace. |
| Rủi ro chính | Bỏ lỡ lỗi hiếm hoặc chậm nếu không được chọn. | Kế thừa quyết định không đúng khi propagation bị đứt. | Thiếu spans đến muộn, thiếu bộ nhớ hoặc routing sai trace. |

Parent-based thường là **cách tổ chức quyết định head sampling xuyên nhiều service**, không phải một lựa chọn loại trừ head sampling. Một cấu hình phổ biến là root trace dùng trace ID ratio sampler và child spans dùng parent-based sampler.

## 8. Cấu hình sampling trong Spring Boot

Spring Boot tích hợp Micrometer Tracing và cung cấp property:

\`management.tracing.sampling.probability\`

Giá trị nằm trong khoảng từ \`0.0\` đến \`1.0\`. Tài liệu Spring Boot hiện hành cho biết mặc định sampling khoảng **10% request**, nhằm tránh làm quá tải trace backend.

### 8.1. Cấu hình mặc định/production baseline

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 0.1
~~~

Với xác suất 0.1, root traces được chọn theo tỷ lệ kỳ vọng 10% khi sampler ratio được sử dụng. Cấu hình này không có nghĩa backend sẽ luôn nhận đúng 10 trace trên mỗi 100 request trong mọi cửa sổ nhỏ.

### 8.2. Sampling 100% trong local hoặc test

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Đặt 1.0 hữu ích khi phát triển và kiểm thử một kịch bản cụ thể vì dễ nhìn thấy đầy đủ các spans đã được instrument. Không mặc định dùng 100% trên production có traffic lớn nếu chưa đánh giá tài nguyên và chi phí.

### 8.3. Tắt sampling

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.0
~~~

Giá trị 0.0 loại các trace mới theo sampler xác suất. Đây không phải cách tắt metrics hoặc logs nói chung; tracing sampling và các pipeline tín hiệu khác có cấu hình riêng.

### 8.4. Cấu hình theo profile

Ví dụ local:

~~~yaml
# application-local.yml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Ví dụ production:

~~~yaml
# application-prod.yml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Các tỷ lệ trên chỉ là ví dụ. Tỷ lệ production cần dựa trên số spans/trace, lưu lượng, retention, ngân sách và mức độ rủi ro. Hãy xác minh profile được kích hoạt đúng và property hiệu lực sau khi deploy.

## 9. Sampler OpenTelemetry trong Spring Boot

Khi dùng OpenTelemetry với các phiên bản Spring Boot hỗ trợ, có thể chọn sampler qua:

\`management.opentelemetry.tracing.sampler\`

Các lựa chọn được tài liệu Spring Boot hiện hành mô tả gồm:

| Sampler | Ý nghĩa |
| --- | --- |
| \`always-on\` | Sample mọi trace. |
| \`always-off\` | Không sample trace. |
| \`trace-id-ratio\` | Sample theo tỷ lệ \`management.tracing.sampling.probability\`. |
| \`parent-based-always-on\` | Nếu có parent, theo quyết định của parent; nếu không có parent, luôn sample root. |
| \`parent-based-always-off\` | Nếu có parent, theo quyết định của parent; nếu không có parent, loại root. |
| \`parent-based-trace-id-ratio\` | Nếu có parent, theo quyết định của parent; nếu không có parent, sample root theo xác suất cấu hình. |

Trong tài liệu Spring Boot 4.2, \`parent-based-trace-id-ratio\` là sampler mặc định được mô tả cho OpenTelemetry.

Ví dụ cấu hình rõ ràng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Ở đây root trace được chọn theo xác suất 10%; child spans theo trạng thái parent. Property sampler này dành cho **OpenTelemetry integration** theo phiên bản hỗ trợ. Không áp dụng bảng sampler OpenTelemetry một cách máy móc cho Brave hoặc tracer implementation khác.

### 9.1. Khi nào chọn always-on?

\`always-on\` phù hợp khi:

- local/test cần toàn bộ trace trong một kịch bản;
- SDK phải gửi đầy đủ candidate spans tới collector để tail sampling quyết định;
- traffic nhỏ và backend có đủ khả năng nhận dữ liệu.

Nếu dùng \`always-on\` để tail sample, phải kiểm soát lưu lượng và bảo vệ collector; nếu không, toàn bộ dữ liệu sẽ được gửi qua pipeline trước khi collector quyết định giữ/bỏ.

## 10. Tail sampling với OpenTelemetry Collector

Spring Boot SDK sampler và Collector tail sampler nằm ở hai tầng khác nhau:

- **SDK sampler:** quyết định khi span được tạo trong ứng dụng.
- **Collector tail sampler:** quyết định sau khi nhận spans qua OTLP hoặc receiver tương ứng.

Một cấu hình processor minh họa:

~~~yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 2048

  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 500
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 1000

      - name: baseline-success
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

  batch:
    timeout: 5s

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp]
~~~

Đây là **một đoạn cấu hình minh họa** cho OpenTelemetry Collector; receiver/exporter \`otlp\` cần được khai báo ở các phần tương ứng trong file Collector hoàn chỉnh. Processor \`tail_sampling\` phải có trong distribution Collector đang dùng (thường từ distribution contrib hoặc bản build có processor này).

Theo chính sách ví dụ, trace được giữ nếu thỏa một trong các policy: có status ERROR, vượt 1 giây, hoặc được chọn ngẫu nhiên trong 5% baseline. Cần kiểm tra cú pháp và semantics của processor đúng phiên bản Collector trước khi triển khai.

### 10.1. Ý nghĩa các tham số

| Thuộc tính | Ý nghĩa |
| --- | --- |
| \`decision_wait\` | Khoảng thời gian collector chờ spans trước khi đưa ra quyết định. |
| \`num_traces\` | Số traces collector dự kiến giữ trạng thái trong bộ nhớ. |
| \`expected_new_traces_per_sec\` | Ước lượng tốc độ trace mới để processor chuẩn bị cấu trúc dữ liệu. |
| \`policies\` | Các điều kiện quyết định giữ trace. |
| \`status_code\` | Chọn trace theo trạng thái span, ví dụ ERROR. |
| \`latency\` | Chọn trace theo thời lượng. |
| \`probabilistic\` | Giữ một tỷ lệ trace làm baseline. |

Các giá trị trong ví dụ không phải sizing production. Cần tính số traces/giây, số spans/trace, kích thước attributes, decision window và bộ nhớ thực tế.

### 10.2. Vì sao tail sampling cần định tuyến theo trace ID?

Giả sử trace T có spans ở service orders, inventory và payments. Nếu collector A nhận span orders, collector B nhận span inventory, collector C nhận span payments, không collector nào nhìn thấy toàn bộ trace để quyết định chính xác.

Trong triển khai nhiều collector tail sampling, cần cơ chế định tuyến sao cho **các spans có cùng trace ID tới cùng tail-sampling worker**. OpenTelemetry Collector có thể kết hợp lớp load balancing/trace-ID routing phía trước tầng tail sampling. Cần giám sát phân phối tải và xử lý khi worker mất kết nối.

### 10.3. Tail sampling không phải phép màu khôi phục dữ liệu

Nếu SDK đã loại trace trước khi export, collector không nhận được spans đó. Tail sampler không thể giữ một trace lỗi mà nó chưa từng nhận.

Để giữ mọi trace có lỗi bằng policy collector, cần bảo đảm các spans ứng viên được gửi đến collector. Có thể dùng sampler SDK phù hợp (ví dụ always-on hoặc cấu hình record/export tương ứng) rồi để collector quyết định. Đổi lại, đường truyền tới collector phải chịu tải cao hơn.

## 11. Kết hợp head sampling và tail sampling

Một pipeline có thể sử dụng cả hai tầng:

1. SDK giảm dữ liệu ban đầu bằng một chính sách head sampling.
2. Collector nhận phần còn lại và áp dụng tail sampling để giữ các trace đáng chú ý trong tập đó.

Cách kết hợp này có thể tiết kiệm tài nguyên hơn, nhưng cần hiểu rõ giới hạn: **tail sampling chỉ xét được những traces đã tới collector**. Nếu head sampler loại 90% traces, tail sampler không thể bảo đảm giữ mọi lỗi nằm trong 90% đó.

Nếu yêu cầu là giữ toàn bộ trace có lỗi, cách triển khai cần đưa đầy đủ các candidate spans đến tail sampler, hoặc có một chiến lược khác bảo đảm không loại các trace cần giữ trước đó.

### 11.1. Khi nào hybrid hợp lý?

- Hệ thống có lưu lượng lớn và không đủ năng lực gửi toàn bộ spans tới tầng tail sampling.
- Có thể chấp nhận một số lỗi hiếm không xuất hiện trong tập đã qua head sampling.
- Cần thêm một lớp kiểm soát tải trước collector.
- Chính sách được mô tả rõ về độ bao phủ, không quảng bá sai rằng “100% error traces được giữ”.

### 11.2. Khi nào hybrid không phù hợp?

Nếu compliance hoặc yêu cầu điều tra quy định mọi lỗi trong một luồng cụ thể phải được lưu, một head sampler xác suất đặt trước tail sampler có thể vi phạm mục tiêu đó. Cần thiết kế pipeline bảo toàn các trace bắt buộc và có kiểm soát truy cập/retention tương ứng.

## 12. Sampling ảnh hưởng đến Spring Modulith như thế nào?

Spring Modulith có thể tạo module entry observations/spans cho các lời gọi qua API application module. Những spans này đi vào tracing pipeline và chịu sampling theo chính sách của tracer/SDK.

Ví dụ trace được sample:

~~~text
HTTP POST /orders
└── orders.place
    ├── inventory.reserve
    │   module.identifier=inventory
    │   module.invocation-type=bean
    └── payments.onOrderPlaced
        module.identifier=payments
        module.invocation-type=event listener
~~~

Nếu trace bị loại ở head sampler, các module spans thuộc trace đó có thể không xuất hiện trong backend. Điều đó **không chứng minh** lời gọi inventory hoặc listener payments không chạy.

### 12.1. Phân biệt module spans với module graph

| Module graph / Actuator | Module spans |
| --- | --- |
| Mô tả cấu trúc module và dependency được phát hiện. | Ghi nhận tương tác runtime đã được instrument. |
| Không phụ thuộc request có được sample hay không. | Chịu ảnh hưởng bởi tracing sampling và export. |
| Có thể liệt kê module chưa từng được gọi trong khoảng thời gian. | Chỉ xuất hiện khi điểm vào chạy, được instrument và được giữ. |
| Hỗ trợ review kiến trúc tĩnh. | Hỗ trợ điều tra một lần thực thi. |

Nếu module graph có 8 modules nhưng dashboard chỉ có spans từ 5 modules, có thể các module còn lại chưa được gọi, chưa được instrument hoặc trace của chúng không được sample/export. Hãy đối chiếu cùng thời gian, service và revision.

### 12.2. Event metrics không tự bị giảm theo trace sampling

Event publication metrics và tracing spans là hai tín hiệu khác nhau. Tracing sampling quyết định spans nào được giữ; nó không mặc nhiên áp dụng cùng tỷ lệ lên Micrometer counters/histograms. Nếu muốn giảm metrics, cần chính sách metrics riêng.

Ví dụ:

- Counter \`module.events.published\` có thể vẫn đếm publication theo instrumentation metrics.
- Module entry span của một lần gọi có thể không xuất hiện vì trace bị sampling.
- Do đó không dùng số spans đã sample để thay cho số event publications hoặc số request chính xác.

## 13. Sampling và tính đại diện của dữ liệu

Một mẫu 10% không nhất thiết đại diện tốt cho mọi nhóm traffic nếu:

- lưu lượng giữa các tenant/service/region khác nhau;
- lỗi hiếm và tập trung trong một endpoint;
- request dài có nhiều spans hơn request ngắn;
- traffic tăng đột biến trong một thời điểm;
- sampling policy phụ thuộc thuộc tính hoặc parent state.

### 13.1. Đừng so sánh số trace thô giữa các tỷ lệ sampling khác nhau

Giả sử tuần trước sample 10%, tuần này sample 50%. Nếu backend hiển thị 5.000 và 20.000 traces, không thể kết luận traffic chỉ tăng 4 lần; tỷ lệ sampling đã thay đổi.

Khi so sánh cần ghi nhận:

- sampling probability theo thời gian;
- phiên bản ứng dụng và sampler;
- số request từ metrics không sample theo tracing;
- chính sách tail sampling và tỷ lệ giữ trace theo từng policy;
- số spans trung bình trên mỗi trace.

### 13.2. Ước lượng traffic từ sample

Với xác suất sampling đồng nhất \(p\), một ước lượng sơ bộ số traces gốc là:

\[
\widehat{N} \approx \frac{S}{p}
\]

Trong đó \(S\) là số traces đã sample. Ví dụ có 1.000 traces sample với \(p=0.1\), ước lượng khoảng 10.000 traces gốc.

Đây là ước lượng thống kê, không thay thế metrics request counter. Không áp dụng công thức máy móc khi dùng tail sampling theo lỗi/latency, policy nhiều tầng hoặc xác suất khác nhau theo nhóm trace; mẫu khi đó có thể có thiên lệch.

### 13.3. Tail sampling tạo mẫu có chủ đích, không phải mẫu ngẫu nhiên

Nếu giữ 100% trace lỗi và 5% trace thành công, tập dữ liệu cố ý có nhiều lỗi hơn tỷ lệ thực tế. Đây là lựa chọn hữu ích để điều tra nhưng không thể dùng tỷ lệ lỗi trong tập traces được giữ để suy ra tỷ lệ lỗi toàn hệ thống nếu không tính đến chính sách chọn mẫu.

## 14. Chọn chính sách sampling theo môi trường

| Môi trường | Chính sách thường phù hợp | Mục tiêu |
| --- | --- | --- |
| **Local development** | 100% trong thời gian debug | Nhìn toàn bộ spans của kịch bản. |
| **CI/integration test** | 100% hoặc cấu hình test exporter/handler | Xác minh instrumentation và propagation. |
| **Staging** | Tỷ lệ cao hoặc tail sampling có giới hạn | Tìm vấn đề trước production. |
| **Production traffic thấp** | Có thể giữ tỷ lệ cao hơn | Dữ liệu đủ lớn để lưu và truy vấn. |
| **Production traffic cao** | Parent-based ratio sampling hoặc collector tail sampling | Kiểm soát tải, ưu tiên trace hữu ích. |
| **Luồng quan trọng như payment** | Policy ưu tiên theo lỗi/latency hoặc service/operation | Tăng độ bao phủ cho đường có rủi ro cao. |

Đây là gợi ý, không phải một bảng cấu hình bắt buộc. Luồng quan trọng có thể cần policy riêng nhưng phải tính tải và đảm bảo quyết định sampling nhất quán qua các service.

### 14.1. Một ví dụ chính sách tham khảo

Giả sử hệ thống có 2.000 request/giây:

- Local: 100% để phát triển.
- Staging: 50% để quan sát rộng.
- Production: head sampling 5% làm baseline, hoặc tail sampling giữ lỗi/chậm và 5% traffic bình thường.
- Payment: cân nhắc mức ưu tiên cao hơn dựa trên yêu cầu điều tra và ngân sách.

Không nên coi những tỷ lệ này là mặc định của Spring Boot. Chúng chỉ là ví dụ để thảo luận với nhóm vận hành.

## 15. Sampling, metrics và logs: ba chính sách riêng

| Tín hiệu | Sampling có tác động thế nào? | Nên dùng để |
| --- | --- | --- |
| **Traces** | Chọn trace/span được ghi và xuất. | Điều tra đường đi, latency, lỗi và quan hệ giữa thành phần. |
| **Metrics** | Thường có pipeline và cơ chế aggregation riêng; tracing sampler không tự giảm counter. | Thống kê tổng hợp request, event, error rate và latency. |
| **Logs** | Thường do log level, filter và appender quyết định; trace sampling không tự xóa log. | Nội dung sự kiện và chi tiết lỗi. |

Nếu chỉ dùng trace sampling để giảm chi phí nhưng logs vẫn ghi payload lớn hoặc metrics tạo cardinality cao, tổng chi phí observability vẫn có thể lớn.

Không nên đưa order ID hoặc trace ID vào metric tags để bù cho trace bị sample. Dùng log có cấu trúc hoặc trace attributes theo chính sách dữ liệu phù hợp.

## 16. Những sai lầm thường gặp

### 16.1. Nghĩ rằng 10% nghĩa là mỗi nhóm request đều có đúng 10%

Tỷ lệ là xác suất/kỳ vọng trên tập traces đủ điều kiện. Với nhóm hiếm, cửa sổ ngắn có thể không có trace nào được chọn. Nếu cần độ bao phủ theo nhóm, cần chính sách phù hợp và kiểm chứng.

### 16.2. Cấu hình mỗi service một tỷ lệ độc lập

Nếu child service tự lấy mẫu độc lập thay vì tuân theo parent, trace có thể bị thiếu spans. Dùng parent-based strategy và propagation tương thích để duy trì quyết định thống nhất.

### 16.3. Muốn tail sampling giữ mọi lỗi nhưng SDK đã drop phần lớn traces

Collector không thể đánh giá trace chưa được gửi tới nó. Muốn quyết định theo lỗi cuối trace, cần gửi candidate spans đầy đủ tới tầng tail sampler hoặc chấp nhận giới hạn của hybrid strategy.

### 16.4. Tăng sampling để sửa exporter

Nếu endpoint collector sai hoặc Zipkin không chạy, đặt sampling 1.0 chỉ làm tăng lượng dữ liệu cố gửi. Kiểm tra endpoint, network, exporter logs và backend trước.

### 16.5. Dùng số trace để báo cáo số request

Sampling và số spans trên mỗi trace làm số trace không bằng số request. Dùng request metrics không sample để báo cáo lưu lượng chính xác hơn.

### 16.6. Cho rằng trace không xuất hiện nghĩa là module không chạy

Module spans có thể bị sample, không được instrument hoặc bị mất trong exporter. Đối chiếu module graph, log, metrics và dữ liệu nghiệp vụ trước khi kết luận.

### 16.7. Tail sampling không có đủ memory hoặc decision window

Nếu collector nhận nhiều trace hơn sizing dự kiến, nó có thể thiếu bộ nhớ hoặc không theo kịp. Nếu decision window quá ngắn, spans đến muộn có thể bị bỏ khỏi trace đã quyết định. Cần giám sát processor và thử với traffic thực.

### 16.8. Dùng sampling như cơ chế bảo mật

Sampling không phải redaction. Trace được chọn vẫn có thể chứa dữ liệu nhạy cảm. Phải lọc/che dữ liệu ở nguồn hoặc processor phù hợp trước khi gửi/lưu; giới hạn quyền truy cập và retention.

## 17. Quy trình kiểm chứng sampling trong Spring Boot

Một phép thử có thể thực hiện trong môi trường local:

1. Bật tracing exporter tới backend test.
2. Đặt \`management.tracing.sampling.probability=1.0\`.
3. Gửi một nhóm request có thể nhận diện trong khoảng thời gian test.
4. Mở trace backend và xác minh các spans đã instrument xuất hiện.
5. Đổi sampling probability xuống 0.1 và chạy một tập request lớn hơn.
6. Đếm số root traces được giữ trong cửa sổ đủ rộng; kết quả nên gần kỳ vọng nhưng không cần khớp chính xác.
7. Xác minh child spans tuân theo parent decision và trace không bị chia do propagation.
8. Kiểm tra module spans của Spring Modulith có xuất hiện trong các traces được giữ.
9. So sánh event metrics/request metrics trước và sau khi đổi sampling; các counters không phụ thuộc tracing sampling nên không được tự giảm cùng tỷ lệ.
10. Nếu dùng tail sampling, gửi đầy đủ candidate spans tới Collector, thử policy lỗi/chậm/baseline và kiểm tra trace ID routing.

### 17.1. Kiểm tra không sample và sample

| Trường hợp | Kỳ vọng |
| --- | --- |
| Probability = 0 | Không có trace mới được giữ theo ratio sampler; request vẫn xử lý. |
| Probability = 1 | Tất cả traces đủ điều kiện được chọn; vẫn phụ thuộc instrumentation và exporter. |
| Probability = 0.1 | Số traces gần 10% trên tập đủ lớn; có dao động thống kê. |
| Parent sampled | Child spans theo quyết định parent khi dùng parent-based sampler và propagation hoạt động. |
| Parent not sampled | Child không tự tạo trace sampled mới cho cùng distributed operation theo parent-based policy. |
| Tail policy ERROR | Trace có span status ERROR được giữ nếu collector nhận đủ spans và policy được kích hoạt. |
| Tail policy latency | Trace vượt ngưỡng được giữ nếu collector nhận trace đủ để đánh giá. |

### 17.2. Kiểm tra cấu hình thực tế

Với Spring Boot, kiểm tra:

- property hiệu lực của profile đang chạy;
- tracer implementation thực sự trên classpath;
- sampler type (đặc biệt khi dùng OpenTelemetry);
- trace context headers được inject/extract;
- exporter có gửi spans;
- collector tail sampler có nhận đủ spans;
- backend có lưu và hiển thị dữ liệu.

Không dựa duy nhất vào file YAML; biến môi trường, command-line args hoặc config server có thể ghi đè property.

## 18. Tình huống thực tế: lỗi thanh toán hiếm bị bỏ lỡ

**Bối cảnh:** \`shop-service\` nhận 20.000 request mỗi phút. Phần lớn tạo đơn thành công; khoảng 0,1% request gặp timeout khi gọi payment provider.

Với head sampling 1%, số trace lỗi kỳ vọng chỉ là:

\[
20.000 \times 0.001 \times 0.01 = 0.2
\]

Nghĩa là trong một phút, trung bình chỉ 0,2 trace lỗi được chọn. Có nhiều phút liên tiếp không có trace lỗi nào, dù lỗi vẫn xảy ra.

### 18.1. Cách điều chỉnh

- Tăng tỷ lệ head sampling giúp tăng khả năng thấy lỗi nhưng cũng tăng dữ liệu bình thường.
- Tail sampling có thể giữ 100% traces có error và giữ 5% trace bình thường.
- Collector cần nhận đầy đủ candidate spans để đánh giá lỗi.
- Payment flow cần có instrumentation và status/error được ghi đúng trên span liên quan.
- Metrics riêng về payment timeout/error rate vẫn cần duy trì để đếm chính xác xu hướng lỗi.

### 18.2. Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    A["Lỗi payment hiếm"] --> B{"Chỉ dùng head sampling?"}
    B -->|"Có"| C["Có thể bỏ lỡ trace lỗi do quyết định sớm"]
    B -->|"Không"| D{"Collector nhận đủ candidate spans?"}
    D -->|"Không"| E["Tail sampling không thể phục hồi trace đã drop"]
    D -->|"Có"| F["Tail policy giữ trace có ERROR"]
    C --> G["Đánh giá tăng ratio hoặc dùng tail sampling"]
    E --> G
    F --> H["Giữ thêm baseline trace thành công"]
    G --> H
    H --> I["Theo dõi metrics lỗi và chi phí pipeline"]
~~~

**Điểm rút ra:** Sampling nên được thiết kế theo xác suất xuất hiện và giá trị điều tra của lỗi. Trace sampling không thay thế error metrics; hai loại tín hiệu bổ sung cho nhau.

## 19. Checklist thiết kế sampling

- [ ] Đã xác định số root traces/giây và số spans trung bình mỗi trace.
- [ ] Đã xác định mục tiêu: giảm tải, baseline, điều tra lỗi hay giữ trace chậm?
- [ ] Đã phân biệt head, parent-based và tail sampling.
- [ ] Parent/child sampling được cấu hình nhất quán qua các service.
- [ ] Đã chọn probability theo từng môi trường.
- [ ] Không dùng sampling 100% ở production nếu chưa đánh giá chi phí/tải.
- [ ] Nếu dùng tail sampling, SDK gửi đủ candidate spans tới Collector.
- [ ] Collector có đủ memory, decision window và throughput.
- [ ] Các spans cùng trace ID được định tuyến tới cùng tail-sampling worker khi chạy nhiều collector.
- [ ] Policy lỗi/latency/baseline có ý nghĩa và được kiểm thử.
- [ ] Đã theo dõi số traces/spans bị drop và nguyên nhân.
- [ ] Metrics request/event vẫn được dùng cho thống kê tổng hợp chính xác.
- [ ] Dashboard ghi rõ sampling ratio và chính sách đang áp dụng.
- [ ] Không dùng trace count làm request count.
- [ ] Sampling không được coi là biện pháp redaction dữ liệu.
- [ ] Module spans và context propagation được kiểm tra trong trace thực.
- [ ] Có phương án điều tra khi trace vắng mặt hoặc bị phân mảnh.

## 20. Bài tập tự luyện

1. **Khái niệm:** Trace sampling là gì? Nó có làm request không được sample ngừng xử lý không?
2. **Tính toán:** Một service nhận 80.000 root traces trong 10 phút, sampling probability là 5%. Tính số traces kỳ vọng được giữ.
3. **Head sampling:** Vì sao head sampler không thể đảm bảo giữ tất cả trace có lỗi xảy ra ở cuối workflow?
4. **Parent-based:** Service A sample trace, sau đó gọi service B. Vì sao service B nên tuân theo parent sampling decision?
5. **Tail sampling:** Collector có policy giữ trace status ERROR. Vì sao SDK không thể drop trace trước khi export?
6. **Sizing:** Một trace có trung bình 15 spans, hệ thống nhận 400 root traces/giây và sampling 10%. Ước lượng spans/giây được giữ.
7. **Spring Boot:** Property nào điều chỉnh xác suất sampling? Với OpenTelemetry, property nào chọn sampler type?
8. **Spring Modulith:** Vì sao module spans có thể vắng mặt trong Zipkin dù module method đã chạy?
9. **Metrics:** Tracing sampling giảm xuống 5% nhưng event publication counter vẫn tăng như cũ. Điều này có mâu thuẫn không?
10. **Hybrid:** Hệ thống head sample 10% rồi tail sample giữ mọi lỗi. Có thể khẳng định giữ 100% lỗi không? Giải thích.
11. **Collector:** Vì sao các spans cùng trace ID cần tới cùng tail-sampling worker?
12. **Thống kê:** Một backend có 1.000 traces sau khi sample 10%. Có thể kết luận chính xác đã có 10.000 request không? Nêu các giả định và giới hạn.
13. **Bảo mật:** Vì sao sampling không thay thế việc loại bỏ token hoặc PII khỏi span attributes?
14. **Thiết kế:** Đề xuất chính sách sampling cho local, staging và production của một hệ thống đặt hàng có luồng payment quan trọng.

## 21. Tổng kết

**Trace sampling là cơ chế chọn những traces được giữ để kiểm soát khối lượng dữ liệu tracing và tập trung vào thông tin có giá trị điều tra.**

Ba khái niệm cần phân biệt:

- **Head-based sampling:** quyết định sớm khi trace/span bắt đầu; hiệu quả và đơn giản nhưng chưa biết kết quả cuối.
- **Parent-based sampling:** child spans tuân theo quyết định sampling của parent, giúp giữ tính nhất quán của distributed trace.
- **Tail-based sampling:** collector quyết định sau khi nhận các spans, có thể ưu tiên trace lỗi hoặc chậm nhưng cần buffer, bộ nhớ, decision window và routing phù hợp.

Trong Spring Boot, \`management.tracing.sampling.probability\` điều chỉnh xác suất; tài liệu hiện hành mặc định khoảng 10%. Khi dùng OpenTelemetry, có thể chọn sampler như \`parent-based-trace-id-ratio\`, \`always-on\` hoặc \`always-off\` theo nhu cầu và phiên bản.

Trong Spring Modulith, sampling ảnh hưởng đến **module spans đã được tạo**, nhưng không thay đổi cấu trúc module graph và không mặc nhiên giảm event metrics. Trace không xuất hiện không chứng minh module không chạy; trace được giữ cũng không chứng minh transaction đã commit hoặc event được xử lý đúng một lần. Hãy kết hợp sampling với metrics, logs, module verification, context propagation, idempotency và đối soát để có bức tranh vận hành đáng tin cậy.

### Tài liệu tham khảo chính thức

1. [Spring Boot — Tracing: sampling probability và OpenTelemetry samplers](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
2. [Spring Boot — Common Application Properties: management.tracing.sampling.probability](https://docs.spring.io/spring-boot/appendix/application-properties/).
3. [OpenTelemetry — Sampling concepts: head sampling và tail sampling](https://opentelemetry.io/docs/concepts/sampling/).
4. [OpenTelemetry — Tail Sampling with the Collector: policies, decision window và processor](https://opentelemetry.io/blog/2022/tail-sampling/).
5. [OpenTelemetry Collector — Processors và pipeline configuration](https://opentelemetry.io/docs/collector/configuration/).
6. [Micrometer Tracing — Reference Documentation](https://docs.micrometer.io/tracing/reference/).
7. [Spring Modulith — Production-ready Features: Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
