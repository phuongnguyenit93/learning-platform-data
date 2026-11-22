# Đo hiệu năng endpoint tài liệu riêng với API nghiệp vụ

Springdoc-openapi cung cấp các endpoint tài liệu như /v3/api-docs và /v3/api-docs.yaml, bên cạnh những endpoint nghiệp vụ do ứng dụng Spring Boot công bố. Hai nhóm endpoint có mục đích và đặc điểm tải khác nhau: API nghiệp vụ thường được gọi liên tục để phục vụ người dùng, còn endpoint tài liệu thường trả về một document có thể lớn, chứa nhiều path, operation, schema và component.

Khi đo hiệu năng, cần tách endpoint tài liệu khỏi API nghiệp vụ để biết chi phí tạo và phục vụ OpenAPI document, thay vì gộp mọi request vào một con số latency chung. Sau khi có baseline riêng, mới chạy bài đo hỗn hợp để xem việc tải tài liệu có ảnh hưởng đến API nghiệp vụ hay không.

## 1. Vì sao cần đo riêng endpoint tài liệu?

Endpoint tài liệu và endpoint nghiệp vụ khác nhau ở cách xử lý, kích thước response và tần suất truy cập.

| Đặc điểm | Endpoint tài liệu | API nghiệp vụ |
|---|---|---|
| Ví dụ | /v3/api-docs, /v3/api-docs.yaml | /api/orders, /api/customers/{id} |
| Công việc chính | Tạo hoặc lấy OpenAPI document, serialize JSON/YAML | Xử lý nghiệp vụ, truy cập cache/database/service |
| Kích thước response | Có thể lớn theo số operation và schema | Thường phụ thuộc dữ liệu của request |
| Tần suất truy cập | Thường thấp, tập trung ở developer/tool/CI | Có thể cao và liên tục |
| Đặc điểm tải | Có thể tiêu tốn CPU, allocation và băng thông khi document lớn | Có thể bị giới hạn bởi database, downstream hoặc logic nghiệp vụ |
| Mục tiêu đo | Chi phí tạo, cache, serialize và truyền document | Latency, throughput và độ ổn định của nghiệp vụ |

Nếu chỉ đo một URL tổng quát hoặc trộn hai nhóm endpoint trong cùng một test, kết quả không cho biết nguyên nhân khi latency tăng. Tách riêng giúp trả lời các câu hỏi:

- Endpoint OpenAPI mất bao lâu để trả document lần đầu?
- Request lặp lại có nhanh hơn nhờ cache không?
- Document JSON và YAML có chi phí serialize/kích thước khác nhau ra sao?
- Khi số operation và schema tăng, CPU, memory và latency thay đổi thế nào?
- Tải tài liệu có cạnh tranh tài nguyên với API nghiệp vụ không?

## 2. Xác định endpoint cần đo

Với cấu hình mặc định, các endpoint thường dùng là:

| Endpoint | Nội dung |
|---|---|
| /v3/api-docs | OpenAPI JSON |
| /v3/api-docs.yaml | OpenAPI YAML |
| /v3/api-docs/{group} | OpenAPI JSON của group |
| /v3/api-docs.yaml/{group} | OpenAPI YAML của group |
| /swagger-ui.html | Trang vào Swagger UI |
| /v3/api-docs/swagger-config | Cấu hình Swagger UI |

Để đo chi phí document, ưu tiên gọi trực tiếp JSON/YAML endpoint. Không dùng thời gian tải /swagger-ui.html làm đại diện cho thời gian tạo OpenAPI document vì trang UI còn tải JavaScript, CSS, font và các tài nguyên khác.

Nếu ứng dụng đổi springdoc.api-docs.path, có context path hoặc đứng sau reverse proxy, hãy dùng URL thực tế sau khi cấu hình. Nếu có nhiều group, đo từng group cần quan tâm vì kích thước và số operation của mỗi document có thể khác nhau.

Chọn ít nhất một API nghiệp vụ đại diện để so sánh, ví dụ:

- Một GET đơn giản chỉ đọc dữ liệu.
- Một GET có truy vấn database hoặc trả danh sách.
- Một POST có validation và xử lý nghiệp vụ.

Không chọn API nghiệp vụ quá nhẹ nếu production chủ yếu xử lý truy vấn phức tạp, hoặc ngược lại. Endpoint đối chứng cần phản ánh workload thực tế.

## 3. Các chỉ số cần thu thập

Không nên chỉ ghi một giá trị thời gian trung bình. Tối thiểu cần theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Latency p50 | Một nửa request có thời gian nhỏ hơn hoặc bằng giá trị này |
| Latency p95 | 95% request hoàn tất trong hoặc trước thời gian này |
| Latency p99 | Phản ánh phần đuôi chậm của phân phối |
| Throughput | Số request hoàn tất trong một đơn vị thời gian, thường là requests/second |
| Error rate | Tỷ lệ request thất bại hoặc có status ngoài phạm vi mong đợi |
| Response size | Số byte JSON/YAML được truyền |
| CPU utilization | Mức sử dụng CPU của process/container |
| Heap và memory | Mức dùng heap, RSS hoặc memory limit của container |
| Allocation và GC | Lượng object được cấp phát, thời gian và tần suất garbage collection |
| Server-side duration | Thời gian xử lý bên trong server, nếu có instrumentation |

Latency đo từ máy tạo tải bao gồm cả mạng, DNS, TCP/TLS handshake và thời gian server xử lý. Nó là chỉ số quan trọng với client nhưng không đồng nghĩa với thời gian CPU hoặc thời gian sinh document bên trong ứng dụng.

Khi cần phân tích nguyên nhân, kết hợp client-side latency với server metrics, tracing hoặc profiling. Đừng kết luận springdoc chậm chỉ từ một phép đo curl chạy qua mạng không ổn định.

## 4. Phân biệt latency, TTFB và thời gian truyền response

Với document lớn, thời gian nhận byte đầu tiên và thời gian tải hết response có thể khác nhau đáng kể.

- Time to first byte (TTFB) phản ánh thời gian từ lúc client bắt đầu request đến khi nhận byte đầu tiên. Giá trị này còn chịu ảnh hưởng của kết nối và mạng.
- Total time là thời gian hoàn tất toàn bộ response.
- Download size cho biết lượng dữ liệu được truyền.

Nếu TTFB cao, cần xem server có mất nhiều thời gian trước khi bắt đầu ghi response hay không. Nếu TTFB thấp nhưng total time cao, document có thể lớn hoặc băng thông giữa client và server thấp.

Đối với endpoint OpenAPI, JSON và YAML có thể có kích thước khác nhau do serialization. Không so sánh latency mà bỏ qua response size và điều kiện nén HTTP.

## 5. Chuẩn bị môi trường đo có thể so sánh

Để kết quả có ý nghĩa, giữ các điều kiện sau giống nhau giữa lần đo endpoint tài liệu và API nghiệp vụ:

1. Cùng phiên bản ứng dụng, JDK và springdoc.
2. Cùng CPU/memory limit và cấu hình container.
3. Cùng số replica hoặc cùng một instance được cô lập.
4. Cùng network path, TLS termination và reverse proxy.
5. Cùng mức logging và instrumentation.
6. Cùng cấu hình security và cách gửi token.
7. Cùng trạng thái cache, trừ khi đang đo riêng cold/warm behavior.
8. Cùng công cụ tạo tải và vị trí chạy load generator.

Không chạy load generator trên chính container ứng dụng nếu mục tiêu là đo server. CPU cạnh tranh giữa client và server có thể làm sai lệch kết quả.

Nếu đo trên Kubernetes, ghi lại CPU request/limit, memory request/limit, số pod, node type và autoscaling policy. Nếu autoscaler thay đổi số replica giữa các lần chạy, throughput và latency không còn được so sánh trên cùng điều kiện.

## 6. Tách phép đo cold-start và warm-request

Một request đầu tiên sau khi ứng dụng khởi động có thể chịu ảnh hưởng của:

- JVM class loading và JIT compilation.
- Spring application context startup.
- Khởi tạo bean hoặc lazy initialization.
- Lần đầu springdoc phân tích mapping, model và annotations.
- Khởi tạo serializer hoặc cache.
- DNS, TCP và TLS handshake ở phía client.

Các request tiếp theo có thể nhanh hơn do JVM đã warm-up, kết nối được tái sử dụng hoặc OpenAPI document đã được cache. Vì vậy, không gộp request đầu tiên với các request steady-state trong cùng một thống kê.

Nên thực hiện hai phép đo riêng:

| Phép đo | Cách thực hiện | Mục tiêu |
|---|---|---|
| Cold/first-hit | Khởi động instance mới, chờ readiness rồi gọi docs lần đầu | Đo trải nghiệm lần truy cập đầu sau startup |
| Warm/steady-state | Gửi warm-up trước, sau đó mới thu thập mẫu | Đo hiệu năng ổn định khi ứng dụng đã hoạt động |

Lưu ý: cold-start của process và first-hit của endpoint không hoàn toàn giống nhau. Nếu readiness probe hoặc một thành phần khác đã gọi OpenAPI endpoint trước phép đo, request bạn xem là first-hit từ client nhưng không còn là first-hit của springdoc.

## 7. Hiểu vai trò của cache

Springdoc có cơ chế cache OpenAPI description trong các phiên bản hỗ trợ cấu hình tương ứng. Cache có thể làm request lặp lại nhanh hơn vì ứng dụng không phải thực hiện toàn bộ công việc tạo document ở mỗi lần gọi. Hành vi cụ thể phụ thuộc phiên bản, cấu hình và việc document có thay đổi theo request hay không.

Property thường gặp để điều khiển cache là:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

Đặt disabled: true có thể hữu ích khi muốn đo riêng chi phí tạo document mà không dùng cache, nhưng cần xác nhận property này trong tài liệu đúng phiên bản springdoc đang chạy. Không thay đổi cấu hình cache production chỉ để làm benchmark.

Nên đo tối thiểu hai trường hợp nếu ứng dụng cần hiểu rõ chi phí:

- Cấu hình cache giống production: đo trải nghiệm request bình thường.
- Cache bị vô hiệu hóa trong môi trường thử nghiệm: ước lượng chi phí tái tạo document.

Không nhầm cache của springdoc với cache HTTP ở reverse proxy, gateway hoặc CDN. Một proxy có thể trả response đã cache mà không gọi đến ứng dụng. Khi đó phép đo client không phản ánh tải thực tế của server.

## 8. Đo nhanh bằng curl

curl phù hợp để kiểm tra nhanh endpoint, status, kích thước response và thời gian. Ví dụ Bash:

~~~bash
DOCS_URL="http://localhost:8080/v3/api-docs"

curl -sS \
  -o /dev/null \
  -w "status=%{http_code} bytes=%{size_download} ttfb=%{time_starttransfer}s total=%{time_total}s\n" \
  "$DOCS_URL"
~~~

Lệnh này không ghi document ra file; nó chỉ in status, số byte, TTFB và total time. Dùng nhiều lần để quan sát độ dao động:

~~~bash
for i in $(seq 1 10); do
  curl -sS \
    -o /dev/null \
    -w "status=%{http_code} bytes=%{size_download} ttfb=%{time_starttransfer}s total=%{time_total}s\n" \
    "$DOCS_URL"
done
~~~

Đây là phép đo smoke/baseline, không phải load test. Mỗi tiến trình curl mới có thể tạo kết nối mới và chịu chi phí DNS/TCP/TLS. Muốn đo nhiều request với keep-alive và concurrency có kiểm soát, dùng công cụ load testing.

Trên Windows PowerShell, gọi rõ curl.exe nếu curl đang là alias:

~~~powershell
$Url = "http://localhost:8080/v3/api-docs"
curl.exe -sS -o NUL -w "status=%{http_code} bytes=%{size_download} ttfb=%{time_starttransfer}s total=%{time_total}s" $Url
~~~

## 9. Dùng k6 để đo riêng endpoint OpenAPI

k6 tạo tải lặp lại với số virtual users và thời gian xác định. Tạo file docs.js:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
};

export default function () {
  const headers = __ENV.OPENAPI_TOKEN
    ? { Authorization: 'Bearer ' + __ENV.OPENAPI_TOKEN }
    : {};

  const response = http.get(
    __ENV.BASE_URL + '/v3/api-docs',
    { headers }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'content type is JSON': (r) =>
      String(r.headers['Content-Type'] || '').includes('application/json'),
    'body contains OpenAPI version field': (r) =>
      r.body !== null && r.body.includes('"openapi"'),
  });

  sleep(1);
}
~~~

Chạy test:

~~~bash
k6 run -e BASE_URL=http://localhost:8080 docs.js
~~~

Nếu endpoint cần token, truyền token qua secret environment variable của máy chạy test:

~~~bash
k6 run -e BASE_URL=https://test.example.com -e OPENAPI_TOKEN="$OPENAPI_TOKEN" docs.js
~~~

Các threshold trong ví dụ chỉ là giá trị minh họa để chỉ ra cách cấu hình. Hãy thay bằng SLO hoặc ngưỡng chấp nhận của hệ thống. Không lấy p95 một giây làm tiêu chuẩn chung cho mọi OpenAPI document.

## 10. Đo API nghiệp vụ bằng kịch bản riêng

Tạo file business.js dùng cùng cấu hình virtual users, thời gian chạy và load generator:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + '/api/orders'
  );

  check(response, {
    'business API returns 200': (r) => r.status === 200,
    'business response is JSON': (r) =>
      String(r.headers['Content-Type'] || '').includes('application/json'),
  });

  sleep(1);
}
~~~

Chạy riêng:

~~~bash
k6 run -e BASE_URL=http://localhost:8080 business.js
~~~

Ví dụ business endpoint cần xác thực, hãy bổ sung header tương ứng và dùng cùng chính sách token giữa các lần chạy. Nếu API là POST hoặc cần query parameter, thay request cho phù hợp và dùng payload xác định.

Chạy docs và business thành hai lượt độc lập trước. Giữ cùng số VU, duration, sleep, network và máy load generator để so sánh công bằng. Ngưỡng p95 của hai loại endpoint có thể khác nhau vì mục đích và SLO của chúng khác nhau.

## 11. Không trộn tải ngay từ phép đo đầu tiên

Một quy trình đo có thể gồm ba giai đoạn:

~~~mermaid
flowchart TD
    A[Chuẩn bị môi trường cố định] --> B[Đo riêng OpenAPI endpoint]
    B --> C[Đo riêng API nghiệp vụ]
    C --> D[So sánh baseline và response size]
    D --> E[Chạy workload hỗn hợp]
    E --> F[Quan sát ảnh hưởng chéo và tài nguyên]
~~~

Giai đoạn cuối mới chạy đồng thời docs và business để trả lời câu hỏi tải tài liệu có làm giảm chất lượng API nghiệp vụ không. Nếu bắt đầu bằng tải hỗn hợp, khó xác định endpoint nào tạo ra CPU, allocation hoặc network pressure.

Trong workload hỗn hợp, giữ tỷ lệ request gần với production. Nếu tài liệu chỉ được tải vài lần mỗi giờ, không nên tạo tỷ lệ docs request bằng business request trừ khi đang cố ý stress-test một tình huống cực đoan.

## 12. Đo JSON, YAML và từng group riêng

OpenAPI JSON và YAML có cùng ý nghĩa hợp đồng nhưng chi phí serialize và kích thước truyền có thể khác nhau. Đo riêng:

- /v3/api-docs
- /v3/api-docs.yaml
- /v3/api-docs/{group}
- /v3/api-docs.yaml/{group}

Nếu ứng dụng có nhiều group, một group nhỏ và một group lớn có thể có latency và response size khác nhau. Không lấy kết quả của group nhỏ đại diện cho toàn bộ tài liệu.

Để so sánh đúng:

1. Giữ cùng instance và trạng thái warm-up.
2. Gọi từng endpoint với cùng số request và cùng concurrency.
3. Ghi status, content type, response bytes và latency.
4. Xác minh proxy không cache một endpoint nhưng chuyển tiếp endpoint còn lại.
5. Lặp lại đủ lần để phân biệt dao động mạng với xu hướng ổn định.

## 13. Theo dõi metrics phía server bằng Micrometer

Spring Boot Actuator và Micrometer có thể cung cấp metrics HTTP server như http.server.requests. Các tag thường giúp phân biệt method, URI, status, outcome và exception. Dùng metrics phía server để xem endpoint docs có thực sự tạo thêm thời gian xử lý hoặc lỗi trong ứng dụng hay không.

Ví dụ cấu hình histogram cho HTTP request:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Tùy backend metrics, có thể cần cấu hình thêm percentile, histogram bucket hoặc scrape interval. Không phải mọi hệ thống metrics đều tính p95/p99 giống nhau.

Nếu Actuator metrics endpoint được bật, có thể truy vấn metric http.server.requests và lọc theo URI tag tương ứng. Ví dụ:

~~~text
/actuator/metrics/http.server.requests
~~~

Kiểm tra tag uri trong response metric để xác định giá trị thực tế cho /v3/api-docs. Không giả định tag luôn giữ nguyên URL đầy đủ; framework thường chuẩn hóa URI để tránh cardinality cao.

Chỉ expose metrics endpoint trên mạng quản trị hoặc bảo vệ bằng cơ chế xác thực phù hợp. Không mở toàn bộ Actuator ra Internet chỉ để phục vụ benchmark.

## 14. Đo CPU, heap, allocation và garbage collection

Khi OpenAPI document lớn hoặc được tạo lại nhiều lần, CPU và allocation có thể tăng. Các nguồn chi phí có thể gồm:

- Phân tích mapping và annotation.
- Xây dựng model OpenAPI và schema.
- Áp dụng customizer, filter và group configuration.
- Serialize object thành JSON/YAML.
- Nén response hoặc truyền lượng dữ liệu lớn.

Theo dõi CPU, heap, allocation rate, GC pause và RSS trong cùng khoảng thời gian với load test. Nếu latency tăng đồng thời CPU tăng, cần xem profile để tìm method tiêu tốn CPU. Nếu heap tăng mạnh hoặc GC dày, kiểm tra object allocation và kích thước document.

Java Flight Recorder (JFR) có thể thu thập profile khi ứng dụng chạy trên JVM:

~~~bash
jcmd <pid> JFR.start name=OpenApiDocs settings=profile duration=60s filename=openapi-docs.jfr
~~~

Phân tích file JFR bằng Java Mission Control hoặc công cụ tương thích. Chụp profile riêng khi chỉ tải docs và khi chỉ tải business để dễ phân biệt hot method của hai workload.

JFR là công cụ chẩn đoán; không bật profile nặng hơn cần thiết trong phép đo latency chuẩn nếu overhead của profiler làm thay đổi kết quả.

## 15. Phân tích response size và độ phức tạp document

Document OpenAPI có thể lớn dần khi module API tăng số lượng:

- Path và operation.
- Request/response schema.
- Component dùng chung.
- Example và mô tả dài.
- Security scheme và group.
- External documentation hoặc extension.

Ghi response size cùng với số path, số operation và số component schema. Điều này giúp phân biệt document chậm vì tạo schema phức tạp với document chậm vì truyền nhiều byte.

Nếu JSON/YAML lớn, kiểm tra HTTP compression ở server/proxy và client có hỗ trợ gzip hay không. Đo cả response size sau nén trên mạng và kích thước document chưa nén nếu cần đánh giá chi phí serialize. Không so sánh số byte của một lần đo đã nén với lần khác chưa nén.

## 16. Phân biệt chi phí ứng dụng và chi phí mạng

Các phép đo client-side thường bao gồm:

- DNS lookup.
- TCP connection.
- TLS handshake.
- Reverse proxy/gateway.
- Server processing.
- Response transfer.

Nếu cần đo endpoint trực tiếp, chạy load generator gần server hoặc trong cùng network zone và ghi rõ vị trí. Nếu cần đo trải nghiệm client, dùng URL public qua đúng proxy/TLS như production.

Nên có hai góc nhìn:

| Góc nhìn | Cách đo | Trả lời câu hỏi |
|---|---|---|
| Client perspective | k6/curl gọi URL public | Người dùng/tool mất bao lâu để nhận document? |
| Server perspective | Micrometer, tracing, JFR | Ứng dụng mất tài nguyên và thời gian xử lý bao nhiêu? |

Không lấy hiệu số giữa hai số đo khác công cụ hoặc khác thời điểm để suy ra chính xác network latency. Muốn tách thời gian cần tracing hoặc instrumentation đồng bộ.

## 17. Kiểm soát concurrency và mức tải

Tăng virtual users theo từng nấc để quan sát điểm bắt đầu suy giảm:

| Mức | Ví dụ số VU | Mục đích |
|---|---:|---|
| Smoke | 1 | Xác nhận endpoint và test script |
| Low | 2–5 | Baseline với tải nhỏ |
| Medium | 10–20 | Quan sát xử lý request đồng thời |
| High | 50 trở lên | Tìm giới hạn trong môi trường thử nghiệm có kiểm soát |

Đây chỉ là mức tham khảo. Chọn concurrency theo số client dự kiến và năng lực môi trường. Không tăng tải trực tiếp trên production nếu chưa có kế hoạch, giới hạn và giám sát phù hợp.

Endpoint docs có thể không được thiết kế để chịu cùng throughput với API nghiệp vụ. Mục tiêu của phép đo là biết khả năng hiện tại và ảnh hưởng của nó, không ép hai endpoint phải có cùng RPS.

## 18. Xem xét cache HTTP và cache của springdoc

Khi đo qua reverse proxy, CDN hoặc gateway, response có thể được cache ở ngoài ứng dụng. Để xác định request có chạm đến server:

- Theo dõi request count phía server.
- Kiểm tra response headers như Age, Via, Cache-Control hoặc header riêng của proxy nếu có.
- So sánh URL public với URL nội bộ trong môi trường thử nghiệm.
- Dùng cấu hình cache giống production cho benchmark trải nghiệm thực tế.

Không tự ý thêm cache policy dài hạn cho tài liệu chỉ để giảm latency. OpenAPI document có thể thay đổi sau deploy, có thể khác theo group, profile, hostname hoặc security context. Nếu cache HTTP được dùng, cần xác định TTL và invalidation phù hợp để client không nhận tài liệu cũ.

Cache của springdoc và cache HTTP giải quyết hai lớp khác nhau:

| Lớp cache | Tác động |
|---|---|
| Cache trong ứng dụng | Giảm công việc tạo OpenAPI document trong process |
| Cache HTTP/proxy | Có thể trả response mà không gọi đến process ứng dụng |

Đo và báo cáo hai trường hợp riêng khi chúng cùng tồn tại.

## 19. Cách đọc kết quả khi docs chậm

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| First-hit chậm, request sau nhanh | Warm-up, lazy initialization hoặc cache |
| TTFB cao, response size nhỏ | Server xử lý trước khi ghi response |
| TTFB thấp, total time cao | Document lớn, nén hoặc network throughput |
| CPU tăng mạnh khi tải docs | Tạo model, customizer, reflection hoặc serialize |
| Heap/allocation tăng và GC dày | Document lớn hoặc tạo object lặp lại |
| JSON nhanh hơn YAML rõ rệt | Chi phí serializer hoặc cấu hình YAML |
| Docs chậm nhưng business ổn định | Chi phí riêng của tài liệu, chưa gây contention đáng kể |
| Business p95 tăng khi docs chạy đồng thời | Hai workload đang cạnh tranh CPU, heap, connection hoặc network |
| Client latency cao nhưng server duration thấp | Mạng, proxy, TLS hoặc load generator |
| Server request count thấp hơn client request count | Có thể proxy cache, request bị chặn hoặc metrics filter không khớp |

Đây là các giả thuyết để điều tra, không phải kết luận tự động. Hãy xác nhận bằng server metrics, tracing hoặc profile trước khi thay đổi cấu hình.

## 20. Những sai lầm làm sai lệch benchmark

- Đo Swagger UI thay vì endpoint JSON/YAML.
- Chỉ đo một request rồi xem đó là latency ổn định.
- Gộp cold-start với steady-state.
- Chạy docs và business đồng thời ngay từ baseline đầu tiên.
- Dùng máy load generator quá yếu hoặc chạy cùng máy với server.
- So sánh hai môi trường có CPU/memory limit khác nhau.
- Không ghi response size hoặc tình trạng gzip.
- Để proxy cache một lần đo nhưng bypass cache ở lần khác.
- Không kiểm tra HTTP status; response 401/403/500 vẫn bị tính như một mẫu latency.
- Đặt concurrency vượt xa workload thực tế rồi dùng kết quả để dự đoán trải nghiệm bình thường.
- Chỉ dùng average mà bỏ qua p95/p99 và error rate.
- Thay đổi cache, logging hoặc instrumentation giữa hai lượt đo.

## 21. Quy trình benchmark có thể lặp lại

1. Ghi lại phiên bản ứng dụng, JDK, springdoc, CPU/memory limit và cấu hình proxy.
2. Chọn endpoint docs JSON/YAML và một API nghiệp vụ đại diện.
3. Xác nhận cả hai endpoint trả đúng status, content type và payload.
4. Chạy smoke test bằng curl.
5. Khởi động instance mới và đo first-hit riêng.
6. Warm-up JVM và endpoint, sau đó đo steady-state docs.
7. Chạy business endpoint với cùng load profile và thời lượng.
8. Ghi p50, p95, p99, RPS, error rate và response size.
9. Thu thập CPU, heap, allocation, GC và server-side HTTP metrics.
10. Chạy JSON, YAML và group riêng nếu cần.
11. Chạy workload hỗn hợp theo tỷ lệ gần production.
12. Lặp lại phép đo để kiểm tra độ ổn định và lưu cấu hình/script cùng kết quả.

Không đổi nhiều biến cùng lúc. Nếu muốn so sánh cache bật/tắt, chạy hai lượt riêng với cùng workload và cùng môi trường.

## 22. Mẫu bảng báo cáo kết quả

Có thể lưu kết quả theo bảng sau:

| Môi trường | Endpoint | Cache | VU | p50 | p95 | p99 | RPS | Error rate | Bytes |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Test | /v3/api-docs | On | 5 | — | — | — | — | — | — |
| Test | /v3/api-docs.yaml | On | 5 | — | — | — | — | — | — |
| Test | /api/orders | On | 5 | — | — | — | — | — | — |
| Test | Mixed workload | On | Theo profile | — | — | — | — | — | — |

Ghi thêm:

- Commit/build ID.
- Spring Boot, springdoc và JDK version.
- CPU/memory limit, replica count.
- URL public hay upstream.
- Compression và cache proxy.
- Warm-up duration và test duration.
- Vị trí load generator.
- Thời điểm và ghi chú bất thường.

Không điền số đo giả định vào báo cáo. Chỉ điền kết quả lấy từ môi trường benchmark thực tế.

## 23. Lựa chọn tối ưu sau khi đo

Chỉ tối ưu khi đã xác định bottleneck:

- Nếu first-hit là vấn đề, xem xét startup/readiness và thời điểm tài liệu được truy cập.
- Nếu request lặp lại vẫn tốn CPU, kiểm tra cache của springdoc và customizer có chạy lại không.
- Nếu document quá lớn, xem xét group, schema/example và mô tả dư thừa; không xóa nội dung hợp đồng chỉ để giảm byte.
- Nếu network transfer chiếm phần lớn, đánh giá compression và đường truyền.
- Nếu business p95 tăng khi docs chạy đồng thời, xem xét giới hạn tần suất tải docs, tài nguyên instance hoặc cách phân phối artifact.
- Nếu proxy trả document cũ, rà soát cache TTL và invalidation sau deploy.

Mỗi thay đổi cần benchmark lại cả docs endpoint và API nghiệp vụ. Một tối ưu làm docs nhanh hơn nhưng tăng CPU hoặc làm business p95 xấu đi có thể không phải cải thiện tổng thể.

## 24. Nguyên tắc thiết kế

- Đo /v3/api-docs và /v3/api-docs.yaml riêng với API nghiệp vụ.
- Tách first-hit, cold-start và warm steady-state.
- Ghi p50/p95/p99, throughput, error rate và response size.
- Kết hợp client-side latency với server metrics và profiling.
- Đo từng group nếu kích thước document khác nhau.
- Giữ nguyên điều kiện môi trường, cache, compression và network giữa các lượt so sánh.
- Đo workload hỗn hợp sau khi đã có baseline riêng.
- Không dùng Swagger UI load time làm đại diện cho OpenAPI document generation.
- Không dùng WebTestClient integration test làm công cụ load testing.
- Chỉ tối ưu sau khi đã xác định bottleneck bằng metrics hoặc profile.
- Lưu script, cấu hình và build ID để có thể lặp lại benchmark.

## Kết luận

Endpoint tài liệu và API nghiệp vụ có đặc điểm tải khác nhau, vì vậy cần có baseline riêng trước khi đánh giá tác động tổng thể. Đo trực tiếp JSON/YAML endpoint bằng curl cho smoke test và dùng k6 hoặc công cụ load testing cho concurrency; tách first-hit khỏi warm steady-state, ghi latency percentile, throughput, error rate và response size. Kết hợp Micrometer/Actuator, CPU, heap, GC và JFR để phân biệt chi phí xử lý trong ứng dụng với chi phí mạng. Sau cùng mới chạy workload hỗn hợp để xác định việc tải OpenAPI document có ảnh hưởng đến API nghiệp vụ hay không.

## Tài liệu tham khảo

- [springdoc-openapi documentation](https://springdoc.org/)
- [Spring Boot Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [k6: Test types and load testing](https://grafana.com/docs/k6/latest/testing-guides/test-types/)
- [k6: Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
- [curl: Write-out variables](https://curl.se/docs/manpage.html#-w)
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/using-jdk-flight-recorder.html)
