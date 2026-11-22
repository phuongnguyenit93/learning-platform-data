# Phân tích log có cấu trúc trong Java

## 1. Structured log analysis là gì?

**Phân tích log có cấu trúc** là việc lọc, truy vấn, tổng hợp và liên kết những sự kiện logging được biểu diễn bằng **các trường có tên, kiểu dữ liệu và ý nghĩa rõ ràng**. Thay vì chỉ dựa trên một chuỗi message tự do, ta có thể hỏi: service nào trả nhiều HTTP 5xx nhất, tỷ lệ lỗi theo thời gian là bao nhiêu, p95 latency của checkout ra sao, những sự kiện nào thuộc cùng một trace và tỷ lệ bản ghi bị lỗi schema là bao nhiêu.

Ví dụ log text:

~~~text
2026-11-09 08:00:01 ERROR checkout timeout; HTTP 503; 920 ms; trace=t-02
~~~

Cùng sự kiện dưới dạng JSON có cấu trúc:

~~~json
{
  "ts": "2026-11-09T08:00:01Z",
  "service": "checkout",
  "event": "http.request.completed",
  "level": "ERROR",
  "trace_id": "t-02",
  "status_code": 503,
  "duration_ms": 920,
  "error_type": "GatewayTimeout"
}
~~~

Từ record JSON, chương trình có thể lấy **status_code** dưới dạng số, **duration_ms** dưới dạng thời lượng và **trace_id** làm khóa liên kết mà không cần viết regex dựa vào câu văn. Khi câu message được đổi wording hay dịch sang tiếng Việt, schema vẫn có thể giữ nguyên.

Sau bài học, bạn sẽ:
- Phân biệt **structured event** và một dòng text được bọc trong JSON.
- Thiết kế schema, xác định field bắt buộc/tùy chọn và quản lý kiểu dữ liệu.
- Đọc và kiểm tra **NDJSON** (mỗi dòng là một JSON object).
- Lọc theo thời gian, service, event, severity, status, error_type, trace_id.
- Nhóm và thống kê counts, HTTP 5xx rate, latency distribution và p95.
- Nhận diện tình huống **đếm trùng** khi một lỗi được ghi ở nhiều service.
- Xử lý JSON hỏng, thiếu field, null, schema version và dữ liệu đến trễ.
- Chạy ví dụ Java 17+ dùng **Jackson** để phân tích dữ liệu thực sự.
- Hiểu giới hạn của logs khi làm SLI/SLO và cách bổ trợ với metrics/traces.

**Phạm vi:** Bài thuộc nhóm **Structured logging** của **Java Core Logging**, tập trung vào cách phân tích dữ liệu đã được cấu trúc. Ví dụ Java sử dụng Maven/Jackson để đọc JSON, không gắn chặt vào một công cụ log search hay backend thương mại.

## 2. JSON không tự động đồng nghĩa structured logging tốt

Một dòng như:

~~~json
{"message":"Payment failed, request req-42, after 920 ms"}
~~~

là JSON hợp lệ, nhưng service, outcome, request ID và duration vẫn chỉ nằm trong một chuỗi. Backend vẫn phải parse text và dễ hỏng khi message thay đổi.

Một record có giá trị phân tích hơn:

~~~json
{
  "event": "payment.authorization.failed",
  "service": "payment",
  "request_id": "req-42",
  "duration_ms": 920,
  "error_type": "GatewayTimeout",
  "message": "Payment authorization timed out"
}
~~~

Ở đây **message** dành cho người đọc, còn **event** và các attributes dành cho truy vấn. Một hệ thống có thể lưu dữ liệu cấu trúc trong định dạng khác JSON; JSON/NDJSON chỉ là format phổ biến để trao đổi.

Các nguyên tắc:
1. **Event code ổn định**: dùng payment.authorization.failed, không dùng toàn bộ câu dịch làm khóa.
2. **Kiểu dữ liệu ổn định**: duration_ms là số, status_code là số nguyên.
3. **Đơn vị rõ ràng**: trường duration_ms khác duration_seconds.
4. **Từ vựng thống nhất**: service, event, level, trace_id có cùng ý nghĩa giữa các producer.
5. **Không dùng thông tin người dùng làm tên field**: dữ liệu thay đổi nằm ở giá trị.
6. **Tách severity khỏi business status**: level=ERROR không tự suy ra HTTP 5xx.
7. **Lưu thông tin liên kết khi có**: trace_id, span_id hoặc request_id phù hợp.
8. **Kiểm soát data sensitivity**: cấu trúc hóa không làm token/password tự an toàn.

## 3. Schema đề xuất cho một HTTP completion event

| Field | Kiểu dữ liệu | Bắt buộc? | Vai trò |
| --- | --- | --- | --- |
| **ts** | String ISO 8601 có offset/Z | Có | Event timestamp |
| **service** | String | Có | Phân nhóm nguồn |
| **environment** | String | Theo deployment | Phân biệt dev/staging/prod |
| **event** | String chuẩn hóa | Có | Phân loại sự kiện |
| **level** | String severity | Có | Lọc severity |
| **trace_id** | String | Khi có tracing | Ghép sự kiện xuyên service |
| **span_id** | String | Khi có tracing | Định vị span cụ thể |
| **request_id** | String | Khi có request context | Theo dõi request tại boundary |
| **status_code** | Integer | Với HTTP completion | Nhóm HTTP status |
| **duration_ms** | Number không âm | Với completion | Tính duration |
| **error_type** | String | Chỉ khi lỗi | Thống kê loại lỗi |
| **route_template** | String | Khi phân tích HTTP route | Tránh high-cardinality raw URL |
| **schema_version** | Integer/string có contract | Nên có khi quản lý schema | Hỗ trợ thay đổi phiên bản |

Ví dụ record phong phú hơn:

~~~json
{
  "ts": "2026-11-09T08:00:01Z",
  "schema_version": 1,
  "service": "checkout",
  "environment": "development",
  "event": "http.request.completed",
  "level": "ERROR",
  "trace_id": "t-02",
  "request_id": "req-02",
  "http_method": "POST",
  "route_template": "/orders/{id}/checkout",
  "status_code": 503,
  "duration_ms": 920,
  "error_type": "GatewayTimeout"
}
~~~

Đây là schema học tập, **không phải danh sách field OpenTelemetry bắt buộc**. Nếu hệ thống dùng OpenTelemetry semantic conventions, hãy chọn quy ước tên thực tế của phiên bản đó và ánh xạ nhất quán giữa producer, collector và backend.

### 3.1. Bốn tình huống dữ liệu không tương đương

- **Thiếu field**: event không hề có error_type.
- **Null**: có error_type:null nhưng chưa có giá trị.
- **Chuỗi rỗng**: error_type:""; thường không phải loại lỗi hữu ích.
- **Sai kiểu**: error_type:503 khi contract mong đợi String.

Không tự gộp tất cả vào **unknown** rồi bỏ mất thông tin chất lượng nguồn. Validator nên phân biệt record thiếu field bắt buộc và record chứa field optional không áp dụng.

### 3.2. Schema evolution

Nếu phiên bản cũ dùng **duration_ms** và phiên bản mới dùng **latency_ms**, dashboard có thể mất dữ liệu. Cần quản lý:
- Tên và kiểu field trong schema version;
- thời gian chạy song song producer cũ/mới;
- mapping normalize tại collector/backend;
- test queries và alerts;
- số event thiếu field bắt buộc;
- kế hoạch migrate dữ liệu/công cụ phân tích.

Một thay đổi message wording không nhất thiết đổi event code. Nhưng nếu semantic của event thay đổi từ “đơn hàng được tạo” sang “đơn hàng đã thanh toán”, cần xem lại event code/version.

## 4. NDJSON và cách đưa event vào hệ phân tích

**NDJSON (newline-delimited JSON)** có một JSON object trên mỗi dòng. Dạng này thuận tiện cho log stream và một số collector:

~~~json
{"ts":"2026-11-09T08:00:00Z","service":"checkout","event":"http.request.completed","status_code":200,"duration_ms":80}
{"ts":"2026-11-09T08:00:01Z","service":"checkout","event":"http.request.completed","status_code":503,"duration_ms":920}
~~~

Đây là **hai document JSON độc lập trên hai dòng**, không phải một JSON document duy nhất. Muốn lưu một document JSON thông thường có nhiều event, có thể dùng array nhưng không còn cách stream line-by-line giống NDJSON.

Pipeline tiêu biểu:

~~~text
Java application
    |
    | emits event + typed fields
    v
Logging API / backend / JSON encoder
    |
    v
stdout / file / network
    |
    v
Collector: parse -> validate -> enrich -> redact -> route
    |
    v
Storage / search / analytics
    |
    +--> filter / aggregate / percentiles
    +--> dashboard / alert
    +--> trace correlation / investigation
~~~

**Không chỉ test output tại console.** Một event có thể đúng JSON ở producer nhưng bị collector đổi kiểu status_code thành String, bị cắt, bị drop, bị sampling hoặc bị nhận quá trễ.

### 4.1. Event time và ingest time

- **Event time** là khi application phát sự kiện, ví dụ 08:00:01Z.
- **Ingest time** là khi storage/collector nhận, có thể muộn hơn do buffer, queue, retry hoặc network.

Phân tích hành vi ứng dụng nên dùng event time đã chuẩn hóa và đủ timezone. Phân tích pipeline health dùng ingest time và ingestion lag. Một cửa sổ phân tích nên dùng quy tắc **[start, end)** để không đếm trùng event tại biên của hai cửa sổ liền nhau.

Nếu service log timestamp ở nhiều múi giờ/offset, phải parse thành Instant trước khi so sánh. Không so sánh chuỗi tùy ý khi các timestamp khác định dạng.

## 5. Lọc đúng dữ liệu trước khi tổng hợp

Trước khi tính toán cần trả lời:
- Phạm vi **thời gian** nào?
- **Service/environment** nào?
- Đếm **loại event** nào?
- Mỗi record biểu diễn **một event, request hay transaction**?
- Field nào phải có giá trị mới được đưa vào aggregation?

Ví dụ tập sự kiện HTTP checkout:

~~~text
ts >= 2026-11-09T08:00:00Z
ts <  2026-11-09T08:01:00Z
service = "checkout"
event = "http.request.completed"
~~~

Chỉ những completion events này mới làm mẫu số khi tính HTTP request error rate của checkout. Một request có thể tạo rất nhiều bản ghi: request.started, db.query, payment.retry, request.completed; **COUNT(all logs)** không phải số request.

### 5.1. Severity khác HTTP status

**level=ERROR** có thể là một logging decision ở bất cứ tầng nào. **status_code=503** là kết quả HTTP response. Chúng có thể liên quan, nhưng không đồng nghĩa:
- Một request 4xx có thể được ghi WARN hoặc INFO.
- Một dependency failure có thể được ghi ERROR nhưng request đã fallback thành công.
- Một request trả 503 có thể xuất thêm nhiều ERROR từ các lớp con.

**Muốn tính HTTP 5xx rate, hãy lọc status_code >= 500 trên completion events.** Không thay điều kiện đó bằng level="ERROR".

### 5.2. Full-text search khác exact field filter

Full-text search theo message có ích khi khám phá một câu cảnh báo hiếm hoặc message không có field. Nhưng dashboard cố định nên dựa vào event code và attributes:

~~~text
event="http.request.completed" AND status_code>=500
~~~

đáng tin hơn:

~~~text
message contains "request failed"
~~~

vì câu văn có thể đổi theo ngôn ngữ, template, formatter và phiên bản ứng dụng.

## 6. COUNT, GROUP BY và error rate

Với bộ dữ liệu của ví dụ Java ở mục 11, sau validation có **8 events hợp lệ**:
- checkout: 6;
- inventory: 1;
- payment: 1.

Kết quả GROUP BY service:

~~~text
services={checkout=6, inventory=1, payment=1}
~~~

Đây là **số bản ghi log hợp lệ** theo service, không nhất thiết là số request/transaction.

### 6.1. HTTP 5xx rate

Có 6 record event=http.request.completed của checkout:
- 4 status 200;
- 1 status 503;
- 1 status 500.

Công thức:

\[
\text{HTTP 5xx rate} = \frac{\text{số completed requests có status >= 500}}{\text{tổng completed requests}} \times 100\%
\]

Do đó **2/6 × 100% = 33,33%** trong dữ liệu mẫu.

~~~text
checkout_requests=6 http_5xx=2 error_rate=33.33%
~~~

**Không suy rộng tỷ lệ của 6 request thử nghiệm sang production.** Khi traffic ít, thêm một record có thể thay đổi tỷ lệ rất mạnh.

### 6.2. SQL minh họa

Giả sử events đã được normalize thành bảng logs với các cột đúng kiểu:

~~~sql
SELECT service,
       COUNT(*) AS request_count,
       SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS error_5xx,
       100.0 * SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*), 0) AS error_rate_pct
FROM logs
WHERE event = 'http.request.completed'
  AND ts >= TIMESTAMP '2026-11-09 08:00:00'
  AND ts <  TIMESTAMP '2026-11-09 08:01:00'
GROUP BY service;
~~~

Đây là **SQL biểu đạt logic**, không bảo đảm chạy nguyên xi ở mọi engine: timezone/session, TIMESTAMP syntax, kiểu dữ liệu và hàm aggregate có thể khác. Nếu một request có nhiều completion events do retry hoặc log trùng, cần dedup theo **request_id và attempt_id** theo hợp đồng trước khi tính.

## 7. Phân tích latency và p95

Dữ liệu checkout có **duration_ms**:

~~~text
[80, 110, 120, 200, 450, 920]
~~~

Trung bình chỉ cho một bức tranh tổng quát, không cho biết rõ tail latency. **p95** thường dùng để xem tail, nhưng có nhiều định nghĩa percentile.

### 7.1. Nearest-rank được dùng trong demo

Sau khi sort dữ liệu tăng dần:

~~~text
n = 6
rank = ceil(0.95 * 6) = ceil(5.7) = 6
p95 = phần tử thứ 6, tính từ 1
p95 = 920 ms
~~~

Vì vậy:

~~~text
checkout_p95_nearest_rank_ms=920
~~~

**Cảnh báo:** Với tập mẫu nhỏ, p95 nearest-rank bằng phần tử lớn nhất và rất nhạy với outlier. Một số backend dùng **PERCENTILE_CONT** với nội suy, t-digest hoặc approximate quantiles, vì vậy giá trị có thể khác. Khi so sánh p95 giữa Java demo và công cụ storage, phải kiểm tra **thuật toán, thời gian, sampling và dữ liệu đầu vào**.

### 7.2. Phân nhóm đúng dimension

Không nên trộn checkout latency với inventory hoặc payment latency nếu chúng phản ánh thao tác khác nhau. Với hệ lớn, phân tích theo:
- service;
- environment;
- route_template;
- endpoint operation;
- release/service_version.

Nhưng tránh group theo raw URL có ID, trace_id, request_id hoặc một user identifier cho dashboard: mỗi giá trị duy nhất sẽ tạo nhóm riêng, dẫn đến high cardinality.

### 7.3. SQL percentiles không luôn cùng định nghĩa

Ví dụ engine hỗ trợ ordered-set aggregates:

~~~sql
SELECT service,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM logs
WHERE event = 'http.request.completed'
  AND duration_ms IS NOT NULL
GROUP BY service;
~~~

**PERCENTILE_CONT thường dùng nội suy**, khác công thức nearest-rank. Với một số engine, bạn cần dùng cú pháp khác hoặc approximation function. Không được tuyên bố công thức này sẽ trả 920 ms trên tập 6 số của ví dụ.

## 8. Phân tích error_type và tránh đếm trùng

Dữ liệu mẫu chứa ba event có error_type:
1. Checkout trả 503: GatewayTimeout, trace t-02.
2. Payment authorization failed: GatewayTimeout, trace t-02.
3. Checkout trả 500: NullPointerException, trace t-05.

Nếu GROUP BY error_type trên **mọi log records**:

~~~text
error_types_across_events={GatewayTimeout=2, NullPointerException=1}
~~~

Nhưng **GatewayTimeout xuất hiện hai lần không có nghĩa hai incident độc lập**. Cùng một failure từ payment có thể được ghi tại nơi phát sinh và thêm một record tại checkout khi trả HTTP 503.

**Phải chọn đơn vị đếm trước khi tính:**
- **Event count**: số log records.
- **Request failure count**: số request thất bại ở boundary đã chọn.
- **Attempt count**: số lần thử, kể cả retry.
- **Transaction failure count**: cần business transaction ID.
- **Trace count**: số trace IDs có đặc tính cần tìm, không đồng nghĩa số request hoặc số sự cố.

Dùng COUNT(DISTINCT trace_id) có thể giúp group theo trace, nhưng một trace có thể chứa nhiều lỗi; ngược lại, tracing/sampling có thể khiến một số events không có trace_id. **Không lấy DISTINCT trace_id làm chuẩn chung cho mọi phân tích.**

### 8.1. Event code và error type có chức năng khác nhau

- **event=payment.authorization.failed**: thao tác nào thất bại.
- **error_type=GatewayTimeout**: nhóm nguyên nhân/lỗi kỹ thuật.
- **reason_code=gateway_unavailable** nếu hệ thống có: mã lỗi nghiệp vụ/vận hành chuẩn hóa.
- **message**: lời giải thích cho người đọc.
- **trace_id**: giúp mở các event liên quan.

Không group theo toàn bộ exception message nếu message có ID, URL hoặc số biến động. Nó dễ tạo hàng nghìn bucket mà khó biết có bao nhiêu loại lỗi thực sự.

## 9. Tìm các log cùng trace và điều tra nguyên nhân

Khi filter theo **trace_id=t-02**, chương trình tìm:

~~~text
trace=t-02 events=[checkout:http.request.completed, payment:payment.authorization.failed]
~~~

Cả hai record cùng một trace, nhưng có service và event code khác nhau. Đây là mối liên hệ hữu ích để điều tra: payment lỗi, checkout trả 503.

**Trace ID không phải distributed tracing đầy đủ.** Tracing thực tế còn có span_id, parent span, context propagation qua network/async boundaries và span timeline. Structured logs chỉ liên kết qua ID đã có.

Một quy trình điều tra:
1. Phát hiện HTTP 5xx tăng từ aggregate/dashboard.
2. Chọn một completion event lỗi có trace_id.
3. Lấy toàn bộ events thuộc trace_id đó.
4. Sort theo event time, cân nhắc clock skew.
5. Xem error_type, dependency, span_id và thứ tự operations.
6. Đối chiếu với trace timeline, metrics và service version.
7. Kết luận nguyên nhân dựa trên bằng chứng, không chỉ vì hai records có cùng trace ID.

Nếu event time giữa các service không đồng bộ tuyệt đối, thứ tự timestamp không tự chứng minh quan hệ nhân-quả. Collector có thể nhận event khác thứ tự do buffering và retry.

## 10. Parse errors và schema validation

Log có cấu trúc chỉ hữu ích khi pipeline biết record nào **đủ hợp lệ để phân tích**.

### 10.1. Malformed JSON

Ví dụ:

~~~text
{not valid json}
~~~

Đây không phải JSON hợp lệ và Jackson không thể đọc thành object. Chương trình tăng **malformed_json**.

### 10.2. JSON hợp lệ nhưng schema sai

Ví dụ:

~~~json
{"ts":"2026-11-09T08:00:06Z","service":"checkout","level":"INFO","trace_id":"t-07"}
~~~

Đây là JSON hợp lệ nhưng thiếu field **event** bắt buộc. Chương trình tăng **schema_rejected**.

### 10.3. Quy tắc validation của ví dụ

Trong Java demo:
- **ts**, **service**, **event**, **level** phải là chuỗi không rỗng.
- **ts** phải parse được bằng **Instant.parse**.
- Với **http.request.completed**, **status_code** và **duration_ms** phải là số nguyên.
- **duration_ms >= 0**.
- Nếu JSON không parse được thì tính malformed_json.
- Nếu parse được nhưng vi phạm schema thì schema_rejected.

Đây là validation cơ bản cho mục đích học, **chưa phải schema contract production hoàn chỉnh**. Một hệ thật còn cần status_code trong dải HTTP hợp lệ, giới hạn kích thước record, timestamp range, field types, schema_version và chính sách optional/null rõ ràng.

### 10.4. Vì sao cần thống kê dữ liệu bị loại?

Nếu parser đột nhiên từ chối 20% events, error-rate dashboard dựa trên các events còn lại có thể trở nên sai lệch nghiêm trọng. Cần có:
- Tổng input count.
- Malformed JSON count/rate.
- Schema invalid count/rate.
- Ingestion lag.
- Pipeline drop/retry/queue metrics.
- Cơ chế quarantine theo quyền truy cập và retention.

**Giảm số dòng ERROR không tự chứng minh ứng dụng đã khỏe**: có thể collector vừa ngừng nhận logs hoặc schema mới không còn được truy vấn.

## 11. Ví dụ Java 17 + Maven + Jackson: phân tích NDJSON

Ví dụ dưới đây là **một chương trình Java chạy độc lập** với dependency **Jackson Databind 2.20.1**. Dữ liệu nằm trong Java text block để dễ tái hiện mà không cần file ngoài. Nó có **10 dòng input**, gồm 8 event hợp lệ, 1 JSON hỏng và 1 record thiếu field bắt buộc.

Chương trình:
- Parse thật bằng ObjectMapper.
- Validate schema.
- Group by service.
- Filter checkout completion events.
- Tính HTTP 5xx rate và p95 nearest-rank.
- Group error_type trên mọi event hợp lệ.
- Lấy events liên quan đến trace t-02.

### 11.1. Cấu trúc thư mục

~~~text
structured-log-analysis/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── analysis/
                    └── StructuredLogAnalysisDemo.java
~~~

### 11.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo.analysis</groupId><artifactId>structured-log-analysis</artifactId><version>1.0</version>
  <properties><maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding></properties>
  <dependencies>
    <dependency><groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId><version>2.20.1</version></dependency>
  </dependencies>
  <build><plugins><plugin><groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId><version>3.14.0</version>
    <configuration><release>17</release></configuration>
  </plugin></plugins></build>
</project>
~~~

**Jackson là thư viện ngoài JDK**, không phải JSON parser chuẩn được tích hợp sẵn trong Java SE 17. Maven Compiler Plugin trong pom được cấu hình **release=17**, tương đương yêu cầu biên dịch tới Java 17.

### 11.3. StructuredLogAnalysisDemo.java

~~~java
package demo.analysis;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class StructuredLogAnalysisDemo {
    private static final String NDJSON = """
            {"ts":"2026-11-09T08:00:00Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-01","status_code":200,"duration_ms":80}
            {"ts":"2026-11-09T08:00:01Z","service":"checkout","event":"http.request.completed","level":"ERROR","trace_id":"t-02","status_code":503,"duration_ms":920,"error_type":"GatewayTimeout"}
            {"ts":"2026-11-09T08:00:01Z","service":"payment","event":"payment.authorization.failed","level":"ERROR","trace_id":"t-02","error_type":"GatewayTimeout"}
            {"ts":"2026-11-09T08:00:02Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-03","status_code":200,"duration_ms":110}
            {"ts":"2026-11-09T08:00:03Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-04","status_code":200,"duration_ms":120}
            {"ts":"2026-11-09T08:00:04Z","service":"checkout","event":"http.request.completed","level":"ERROR","trace_id":"t-05","status_code":500,"duration_ms":450,"error_type":"NullPointerException"}
            {"ts":"2026-11-09T08:00:05Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-06","status_code":200,"duration_ms":200}
            {"ts":"2026-11-09T08:00:05Z","service":"inventory","event":"inventory.reserved","level":"INFO","trace_id":"t-06"}
            {"ts":"2026-11-09T08:00:06Z","service":"checkout","level":"INFO","trace_id":"t-07"}
            {not valid json}
            """;

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        List<JsonNode> events = new ArrayList<>();
        int inputLines = 0;
        int malformed = 0;
        int rejectedSchema = 0;
        for (String line : NDJSON.split("\\R")) {
            if (line.isBlank()) continue;
            inputLines++;
            try {
                JsonNode node = mapper.readTree(line);
                if (!valid(node)) {
                    rejectedSchema++;
                    continue;
                }
                events.add(node);
            } catch (JsonProcessingException ex) {
                malformed++;
            }
        }

        Map<String, Long> services = events.stream().collect(
                Collectors.groupingBy(n -> n.get("service").asText(), TreeMap::new,
                        Collectors.counting()));
        List<JsonNode> checkout = events.stream()
                .filter(n -> n.get("service").asText().equals("checkout"))
                .filter(n -> n.get("event").asText().equals("http.request.completed"))
                .toList();
        long errors = checkout.stream()
                .filter(n -> n.get("status_code").asInt() >= 500).count();
        List<Long> latencies = new ArrayList<>();
        checkout.forEach(n -> latencies.add(n.get("duration_ms").asLong()));
        Collections.sort(latencies);
        long p95 = latencies.get((int) Math.ceil(0.95 * latencies.size()) - 1);

        Map<String, Long> errorTypes = events.stream()
                .filter(n -> n.hasNonNull("error_type"))
                .collect(Collectors.groupingBy(n -> n.get("error_type").asText(),
                        TreeMap::new, Collectors.counting()));
        List<String> traceEvents = events.stream()
                .filter(n -> n.path("trace_id").asText().equals("t-02"))
                .map(n -> n.get("service").asText() + ":" + n.get("event").asText())
                .toList();

        System.out.printf("input_lines=%d accepted=%d malformed_json=%d schema_rejected=%d%n",
                inputLines, events.size(), malformed, rejectedSchema);
        System.out.println("services=" + services);
        System.out.printf(Locale.ROOT,
                "checkout_requests=%d http_5xx=%d error_rate=%.2f%%%n",
                checkout.size(), errors, 100.0 * errors / checkout.size());
        System.out.println("checkout_latencies_ms=" + latencies);
        System.out.println("checkout_p95_nearest_rank_ms=" + p95);
        System.out.println("error_types_across_events=" + errorTypes);
        System.out.println("trace=t-02 events=" + traceEvents);
    }

    private static boolean valid(JsonNode n) {
        if (n == null || !n.isObject()) return false;
        for (String name : List.of("ts", "service", "event", "level")) {
            if (!n.hasNonNull(name) || !n.get(name).isTextual()
                    || n.get(name).asText().isBlank()) return false;
        }
        try { Instant.parse(n.get("ts").asText()); }
        catch (RuntimeException ex) { return false; }
        if (n.get("event").asText().equals("http.request.completed")) {
            return n.path("status_code").isIntegralNumber()
                    && n.path("duration_ms").isIntegralNumber()
                    && n.get("duration_ms").asLong() >= 0;
        }
        return true;
    }
}
~~~

Đây là **chương trình runnable đầy đủ** với pom.xml đã cung cấp. Nó dùng Java text block, Stream.toList và java.time.Instant nên yêu cầu Java 17 phù hợp. Các sự kiện mẫu không chứa dữ liệu cá nhân thực.

### 11.4. Build và chạy

Từ thư mục chứa pom.xml:

~~~bash
mvn -q -B package dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Sau khi Maven tải dependencies và compile, chạy bằng một JVM Java 17 trở lên.

**Linux/macOS:**

~~~bash
java -cp "target/classes:$(cat classpath.txt)" demo.analysis.StructuredLogAnalysisDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content .\classpath.txt -Raw).Trim()
java -cp "target\classes;$deps" demo.analysis.StructuredLogAnalysisDemo
~~~

**Classpath separator:** thường dùng **:** trên Unix và **;** trên Windows. Đừng trộn cú pháp shell giữa PowerShell và Bash. Để chạy với javac trực tiếp, cũng cần cấp Jackson dependencies trên compile/runtime classpath; Maven giúp giải quyết việc này.

### 11.5. stdout đã kiểm chứng

Chương trình đã được biên dịch và chạy thành công:

~~~text
input_lines=10 accepted=8 malformed_json=1 schema_rejected=1
services={checkout=6, inventory=1, payment=1}
checkout_requests=6 http_5xx=2 error_rate=33.33%
checkout_latencies_ms=[80, 110, 120, 200, 450, 920]
checkout_p95_nearest_rank_ms=920
error_types_across_events={GatewayTimeout=2, NullPointerException=1}
trace=t-02 events=[checkout:http.request.completed, payment:payment.authorization.failed]
~~~

### 11.6. Giải thích kết quả

**input_lines=10:** chương trình đọc 10 dòng không rỗng.

**accepted=8:** tám dòng là JSON object với schema hợp lệ theo quy tắc đã khai báo.

**malformed_json=1:** dòng **{not valid json}** lỗi cú pháp, bị catch dưới dạng JsonProcessingException.

**schema_rejected=1:** một JSON object hợp lệ nhưng thiếu field **event**.

**services:** GROUP BY service đếm các events hợp lệ, không tự tương đương số request.

**checkout_requests=6:** chỉ lọc service checkout và event=http.request.completed. Hai status thuộc lớp 5xx, nên error rate = 33.33%.

**checkout_latencies_ms:** danh sách sáu durations được sort tăng dần.

**checkout_p95_nearest_rank_ms=920:** thứ hạng p95 = 6/6 trong thuật toán nearest-rank.

**error_types_across_events:** đếm occurrence của error_type trên tất cả events, trong đó GatewayTimeout có thể được ghi ở hai service thuộc cùng trace.

**trace=t-02:** xuất ra hai event liên quan từ checkout và payment.

### 11.7. Giới hạn cố ý của demo

Ví dụ phục vụ học tập, chưa là pipeline production:
- Dữ liệu NDJSON nằm trong memory, không stream file lớn.
- Không giới hạn maximum record size, nesting depth hay field count.
- Chưa validate status_code trong dải 100–599 hoặc schema_version.
- Nếu không có checkout completion events, công thức tính p95 và error-rate cần nhánh xử lý tập rỗng.
- Chưa lọc event theo time window bằng code; dữ liệu mẫu đều ở một khoảng ngắn.
- Chưa dedup bằng event_id/request_id.
- Chưa xử lý sampling, late arrivals, clock skew hay distributed storage.
- Không áp dụng policy kiểm toán, quyền truy cập hay dữ liệu nhạy cảm.

Dùng mẫu này để hiểu nguyên lý, sau đó xây dựng validation và pipeline theo contract của ứng dụng thực.

## 12. Dashboard, alerts và truy vấn cho điều tra

Các phép phân tích thường cần:

| Mục đích | Metric / query | Điều phải cảnh giác |
| --- | --- | --- |
| Request throughput | COUNT completion event mỗi phút | Log sampling/drop sẽ làm thiếu |
| HTTP 5xx rate | 5xx completions / all completions | Đúng mẫu số và time window |
| Tail latency | p95/p99 duration_ms | Kiểu số, đơn vị, percentile algorithm |
| Top error types | COUNT by error_type | Một incident có thể nhiều records |
| Tình trạng parser | malformed/schema_rejected rate | Không bỏ record lỗi im lặng |
| Ingestion health | ingest lag, received/dropped | Thiếu log không đồng nghĩa không có lỗi |
| Trace investigation | filter trace_id | Có thể nhiều service, không tự chứng minh nhân quả |
| Deployment comparison | compare versions/windows | Phải kiểm soát traffic mix |

### 12.1. Điều kiện cảnh báo cần đủ dữ liệu

Ví dụ error-rate 5xx vượt ngưỡng chỉ nên xét khi:
- Có đủ số requests trong time window theo policy.
- Có ingestion data tương đối đầy đủ.
- Không có schema migration làm thay đổi query.
- Cửa sổ thời gian và sample size thống nhất.
- Tín hiệu kéo dài đủ để tránh báo động chỉ vì một request.

Đối với SLI/SLO cần độ chính xác cao, metrics counters và histograms thường đáng tin hơn logs được sampling/rate-limit. Logs hỗ trợ **đi sâu vào nguyên nhân**, không tự động đảm bảo coverage của mọi request.

### 12.2. So sánh trước và sau deployment

Chọn cùng route_template, service, environment và khoảng thời gian đủ mẫu trước/sau. So sánh throughput, 5xx, p95 và error_type; sau đó mở traces đại diện. Nếu traffic mix hoặc dependency thay đổi, không nên kết luận nguyên nhân chỉ từ timestamp deploy.

### 12.3. Kiểm tra ingestion pipeline song song

Nếu số lỗi log giảm về 0 vì collector dừng hoạt động, dashboard có thể tạo cảm giác hệ thống đã hồi phục. Hãy theo dõi log ingestion volume, rejected count, data freshness, retry, queue và collector health.

## 13. Cardinality, chi phí và khả năng mở rộng

**Cardinality** là số giá trị phân biệt của field:
- service: thường thấp;
- event: thường vừa phải nếu chuẩn hóa;
- route_template: ổn định hơn raw_url;
- error_type: dùng tên chuẩn hóa để tránh nhiều biến thể;
- trace_id, request_id: thường rất cao.

Trong log storage có thể giữ trace_id để tìm một request cụ thể. Nhưng **group by trace_id** trên dashboard có thể tạo hàng triệu buckets, tốn bộ nhớ/tài nguyên. Với metrics, dùng trace ID làm label thường là anti-pattern high-cardinality.

Ví dụ:

~~~text
raw_url = /orders/ORD-42/items/IT-001
route_template = /orders/{orderId}/items/{itemId}
~~~

Route template giúp nhóm theo endpoint chức năng, không tạo một giá trị mới cho từng order. Tuy nhiên phải kiểm tra route metadata từ framework thay vì tự parse raw URLs chứa thông tin nhạy cảm.

### 13.1. Field indexing

Không phải field nào cũng cần index giống nhau. Hãy xem workload:
- service, event, ts, status_code, environment, error_type thường truy vấn nhiều;
- request_id/trace_id dùng drill-down;
- message có thể cần full-text search;
- các field hiếm hoặc kích thước lớn có thể có retention/index policy riêng.

Một số backend dùng inverted index; một số dùng columnar storage hoặc scan theo partitions. **Không tự áp một thiết kế index cho mọi backend**; chi phí lưu trữ/truy vấn phụ thuộc engine và retention.

## 14. Mối liên hệ với Java logging framework

Phân tích log có cấu trúc ở phía sau pipeline **không phụ thuộc bắt buộc** vào một API phát log duy nhất.

**JUL:** java.util.logging.Logger tạo LogRecord. ConsoleHandler/SimpleFormatter mặc định thường xuất text, không tự tạo schema JSON với các field như ví dụ. Muốn structured output cần Formatter/Handler hoặc collector transform được thiết kế đúng.

**SLF4J:** là facade; parameterized logging như logger.info("id={}", id) có thể chỉ tạo message text, không bảo đảm có trường JSON id riêng. Cần encoder/provider hoặc structured arguments phù hợp.

**Log4j2:** hỗ trợ Message, ThreadContext, Layout và Appender. Để tạo event JSON có schema, chọn JSON Template Layout hoặc phương án structured output tương thích, đặt tên field đúng, bảo toàn exception/context và kiểm thử trên backend.

**OpenTelemetry:** có mô hình log record riêng gồm timestamp, observed timestamp, severity, body, attributes, Resource/Instrumentation Scope và có thể gắn trace/span IDs. Schema của ví dụ dùng tên học tập như **ts, status_code, duration_ms**; không tự coi chúng là toàn bộ quy ước OTel.

Dù producer dùng API nào, mục tiêu phân tích là có **schema thống nhất** tại nơi truy vấn. Nhiều service khác nhau có thể được normalize tại collector nếu có quy tắc rõ và quan sát lỗi chuyển đổi.

## 15. Bảo mật dữ liệu trong structured logs

Dữ liệu có cấu trúc càng dễ tìm kiếm, vì vậy càng cần kiểm soát những gì được đưa vào:
- Không ghi password, OTP, session cookie, API keys, private keys, access/refresh tokens.
- Không log toàn bộ thẻ thanh toán hoặc payload nhạy cảm.
- Không để exception message và raw URL query làm rò secrets.
- Dùng allowlist fields, masking/redaction, retention và quyền truy cập theo policy.
- JSON encoder phải escape quote, newline, backslash và ký tự điều khiển để tránh log injection.
- Không dùng input của người dùng làm tên field/key tùy ý.
- Test dữ liệu Unicode/tiếng Việt qua serializer và collector.

Ví dụ **không nên dùng**:

~~~java
// Minh họa anti-pattern trong một phương thức có biến rawInput.
String line = "{\"userInput\":\"" + rawInput + "\"}";
~~~

Đoạn này chưa phải chương trình độc lập. rawInput có quote/newline có thể phá JSON hoặc tạo record giả. Hãy dùng JSON serializer như Jackson hoặc logging encoder chuyên dụng và kiểm tra dữ liệu được phép ghi trước.

### 15.1. Retention và audit

Structured logs không tự bảo đảm độ bền, thứ tự tuyệt đối, tính không thể sửa hoặc retention bắt buộc. Nếu một loại event là audit/security evidence, cần hệ lưu trữ, truy cập, integrity, delivery và chính sách riêng; không coi một Console Appender hoặc một collector thông thường là bằng chứng bảo toàn.

## 16. Những lỗi phân tích thường gặp

**Lỗi 1 — Đếm tất cả dòng ERROR rồi gọi là request error rate.** Một request có thể tạo nhiều ERROR. Chọn completion event và mẫu số.

**Lỗi 2 — status_code là chuỗi ở một service, số ở service khác.** Mapping/aggregation có thể hỏng. Chuẩn hóa types và validate.

**Lỗi 3 — Trộn duration seconds với milliseconds.** Percentile có thể sai hàng nghìn lần. Gắn đơn vị ở field name hoặc contract và test biên.

**Lỗi 4 — Bỏ malformed records im lặng.** Cần thống kê parser/schema rejection, quarantine phù hợp và cảnh báo data quality.

**Lỗi 5 — Dùng COUNT error_type để suy ra số incident.** Cùng một lỗi có thể được ghi ở checkout và payment, như trace t-02.

**Lỗi 6 — So sánh p95 các hệ có thuật toán khác nhau.** Nearest-rank, interpolation và approximation không luôn trùng. Chú thích phương pháp.

**Lỗi 7 — Dùng log đã sampling làm counter tuyệt đối.** Có thể thiếu events; cần biết tỷ lệ sampling hoặc dùng metrics.

**Lỗi 8 — Nhầm event time và ingest time.** Late arrivals và clock skew làm số liệu theo cửa sổ sai nếu không có policy.

**Lỗi 9 — Đổi field name mà không migrate dashboard.** Schema evolution phải đi cùng truy vấn và test.

**Lỗi 10 — Group by raw_url hoặc trace_id trên toàn hệ.** High cardinality gây nhiều buckets và chi phí lớn.

**Lỗi 11 — Coi hai events cùng trace là quan hệ nhân quả chắc chắn.** Correlation chỉ hỗ trợ điều tra, không thay trace timeline hoặc proof.

**Lỗi 12 — JSON hóa message nhưng vẫn parse bằng regex.** Cần typed fields thực, không chỉ một object có field message.

**Lỗi 13 — Coi level=ERROR là HTTP 500.** Severity là policy logging; HTTP status là outcome của request.

**Lỗi 14 — Coi số log lỗi giảm là ứng dụng đã hồi phục.** Kiểm tra ingestion health/sampling/parser và metrics.

## 17. Bài thực hành

### Bài A — Thêm request thành công

Thêm một record checkout status 200, duration_ms=90 vào NDJSON. Tính lại tỷ lệ 5xx và p95 nearest-rank. Giải thích vì sao với ít samples, p95 có thể vẫn bằng cực đại.

### Bài B — Thay service filter

Đổi bộ lọc checkout sang payment. Payment không có event=http.request.completed trong dataset. Bổ sung nhánh xử lý **zero records** trước khi tính p95/error rate để không truy cập danh sách rỗng.

### Bài C — Time window

Chọn [08:00:00Z, 08:00:03Z) và [08:00:03Z, 08:00:06Z), parse ts bằng Instant để lọc. Kiểm tra sự kiện ở biên chỉ thuộc một cửa sổ.

### Bài D — Kiểm tra parser/schema

Thêm một JSON string sai cú pháp và một event duration_ms="450" (String). Xác nhận malformed_json và schema_rejected được tăng đúng.

### Bài E — Trace correlation

Thêm một inventory event mang trace_id=t-02 và field span_id; filter và sort events theo ts. So sánh grouping theo trace_id, request_id và service.

### Bài F — SQL theo status

Viết query GROUP BY service,status_code trên event=http.request.completed. Kiểm tra 200, 500, 503 và chứng minh COUNT(all ERROR records) không bằng số HTTP requests thất bại.

### Bài G — Schema review

Thiết kế event **job.completed** với duration, outcome, retry_count, dependency, request_id và schema_version. Nêu field bắt buộc, tùy chọn, loại số và cách xử lý khi một service chưa có version mới.

### Bài H — Chẩn đoán dashboard thiếu dữ liệu

Một bản deploy đổi duration_ms thành latency_ms. Xác định vì sao p95 dashboard giảm về null/0, đề xuất migration và test coverage.

### Bài I — Redaction và cardinality

Một team log raw URL chứa token và group by userId. Hãy đề xuất route_template, cách chọn field được phép, retention và truy vấn điều tra riêng có kiểm soát.

## 18. Câu hỏi tự đánh giá và đáp án

**1. Một JSON object chỉ có field message đã đủ để thống kê duration chưa?**  
Không. Nếu duration nằm trong message text, vẫn cần parse chuỗi dễ vỡ; cần field số riêng.

**2. NDJSON khác JSON array thế nào?**  
NDJSON có một JSON object mỗi dòng, thuận tiện streaming; nhiều dòng không phải một JSON document đơn lẻ.

**3. Khi tính HTTP 5xx rate, tại sao chỉ lấy request completion events?**  
Để mẫu số là các HTTP requests đã có outcome, không phải mọi logging event.

**4. Trong ví dụ, tỷ lệ 5xx checkout là bao nhiêu?**  
**2/6 × 100% = 33.33%.**

**5. P95 nearest-rank của [80,110,120,200,450,920] là gì?**  
**920 ms**, vì ceil(0.95 × 6) = 6. Backend dùng interpolation có thể trả giá trị khác.

**6. GatewayTimeout xuất hiện 2 lần có nghĩa có 2 incident không?**  
Không chắc. Checkout và payment cùng ghi lỗi thuộc trace t-02.

**7. Phân biệt malformed_json và schema_rejected?**  
Malformed không parse được JSON; schema rejected là JSON hợp lệ nhưng thiếu/sai field theo contract.

**8. trace_id có tự tạo distributed trace đầy đủ không?**  
Không. Nó chỉ là khóa liên kết; tracing cần span/instrumentation/context propagation.

**9. Có thể dùng log count đã sampling làm SLI chính xác không?**  
Không mặc định. Sampling/drop làm thiếu dữ liệu; cần biết weights hoặc dùng metrics thích hợp.

**10. Vì sao status_code nên là số?**  
Để lọc so sánh và aggregation đúng; tránh parse text và mapping conflict.

**11. Có nên group by request_id để làm dashboard tổng quan?**  
Thường không vì high cardinality. Dùng ID khi drill-down, còn dashboard group theo service/event/route_template.

**12. Thay schema mà không cập nhật dashboard gây gì?**  
Truy vấn thiếu dữ liệu hoặc sai kiểu, khiến metrics/alerts lệch.

**13. Level ERROR và HTTP status >=500 có giống nhau không?**  
Không. Một cái là logging severity, một cái là kết quả protocol.

**14. Vì sao cần giám sát malformed records?**  
Vì pipeline có thể drop events sai, làm các biểu đồ lỗi thấp giả tạo.

## 19. Tài liệu tham khảo

- Java 17 Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Java 17 Streams: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
- Jackson Databind: https://github.com/FasterXML/jackson-databind
- JSON Lines: https://jsonlines.org/
- OpenTelemetry Log Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry Semantic Conventions: https://opentelemetry.io/docs/specs/semconv/
- Apache Log4j2 JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html

Khi triển khai, chọn phiên bản Java/Jackson/backend và quy ước field theo runtime thực tế; schema trong bài chỉ là một ví dụ học tập có thể tái lập.

## 20. Ghi nhớ cốt lõi

**Structured log analysis không bắt đầu từ một câu query mà bắt đầu từ event schema đúng.** Có schema ổn định, typed fields và correlation IDs, ta có thể lọc, nhóm và đo error rate/p95 mà không phụ thuộc câu message tự do. Nhưng mọi kết quả đều phải chỉ rõ **đơn vị đếm, mẫu số, thuật toán percentile, time window và chất lượng dữ liệu**.

Trong ví dụ Java 17, pipeline nhỏ xử lý **10 dòng input → 8 event hợp lệ → phát hiện 2 loại lỗi dữ liệu → GROUP BY service → 5xx rate → p95 nearest-rank → error_type → trace correlation**. Trong production, hãy kết hợp log analysis với metrics/traces, theo dõi ingestion health, quản lý schema evolution, sampling, cardinality và bảo mật dữ liệu để có kết luận vận hành đáng tin cậy.
