# Đối chiếu cấu hình ghi nội dung và mặc định bảo vệ dữ liệu

Một nhóm vận hành bật tracing để tìm nguyên nhân RAG trả lời sai. Dashboard latency và token usage vẫn hoạt động, nhưng log bất ngờ chứa prompt có email khách hàng, kết quả vector search có đoạn hợp đồng nội bộ và tool result chứa mã đơn hàng. Một nhóm khác nâng Spring AI rồi không còn thấy prompt trong trace vì content observation đã chuyển sang logging handlers.

Bài này hướng dẫn **đối chiếu cấu hình ghi nội dung và mặc định bảo vệ dữ liệu khi nâng Spring AI**. Ta sẽ xác định dữ liệu nào được quan sát, property nào bật việc ghi prompt/completion/tool/vector/audio content, các tên cũ đã đổi ra sao, sự khác nhau giữa log và span, rồi thiết kế redaction, quyền truy cập, retention và kiểm thử để tránh phát tán dữ liệu nhạy cảm qua telemetry.

Bài thuộc chương **Nâng cấp** của mô-đun **SPRING_AI_EVALUATION_OBSERVABILITY**. Mô-đun đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool workflow; đồng thời đo metrics, traces, chi phí và độ trễ qua từng phiên bản prompt, model và pipeline. Những dữ liệu cần để debug có thể đồng thời chứa thông tin cá nhân, bí mật nghiệp vụ hoặc nội dung do người dùng cung cấp, vì vậy cấu hình observability phải được quản lý như một phần của data governance.

> **Nguyên tắc mặc định:** đo thời gian, số lần gọi, token usage và outcome; chỉ ghi raw content khi có mục đích cụ thể, phạm vi giới hạn, redaction và thời hạn lưu rõ ràng. Các property của Spring AI là công tắc ghi nội dung, không phải cơ chế phân loại hay tự động che dữ liệu.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt metadata quan sát với raw prompt, completion, tool arguments/result và vector documents.
2. Liệt kê property ghi nội dung cùng giá trị mặc định ở Spring AI 2.1.
3. Đối chiếu tên `include-*` cũ với `log-*` mới.
4. Phân biệt content được ghi vào application logs với attributes được export trong trace spans.
5. Hiểu các giới hạn của mặc định bảo vệ dữ liệu và những trường vẫn có thể xuất hiện trong trace.
6. Tạo cấu hình YAML giữ content logging ở trạng thái tắt.
7. Thiết kế profile debug có phạm vi nhỏ và thời gian tồn tại ngắn.
8. Áp dụng data minimization, redaction, access control và retention cho logs/traces.
9. Kiểm thử rằng raw content không xuất hiện ngoài ý muốn sau khi nâng cấp.
10. Lập migration checklist cho từng release line.

## 2. Phân biệt metadata và raw content

Observability không đồng nghĩa phải lưu toàn bộ nội dung request/response. Một operation có thể được theo dõi hữu ích bằng metadata mà không cần lưu text người dùng hoặc dữ liệu nghiệp vụ.

| Nhóm dữ liệu | Ví dụ | Mục đích | Rủi ro thường gặp |
|---|---|---|---|
| **Operation metadata** | operation name, provider, model, duration, outcome | Đo latency, throughput, lỗi | Thường thấp hơn raw content, nhưng vẫn có thể định danh nếu kết hợp nhiều tags |
| **Prompt content** | system/user messages, retrieved context, instructions | Debug prompt construction | PII, secrets, internal instructions, customer data |
| **Completion content** | câu trả lời, structured output, reasoning-like fields nếu provider trả | Debug output quality | PII, dữ liệu sai lệch, nội dung độc hại hoặc bí mật |
| **Tool arguments** | order ID, email, account reference, search filters | Debug tool routing/arguments | Business identifiers, credentials, personal data |
| **Tool result** | customer record, ticket, payment status | Debug tool response | Dữ liệu nghiệp vụ và thông tin cá nhân |
| **Vector query/response** | search query, metadata filter, retrieved documents | Debug retrieval | Tài liệu nội bộ, query của người dùng, quyền truy cập tài liệu |
| **Image/audio text** | image prompt, TTS input, transcription transcript | Debug multimodal pipeline | Nội dung riêng tư, giọng nói, thông tin sức khỏe/tài chính hoặc dữ liệu cá nhân |

Một trace chỉ có operation, model, duration và token usage vẫn có thể hữu ích để chẩn đoán vận hành. Raw content chỉ cần thiết cho một số trường hợp điều tra chất lượng, và nên được xử lý ở một luồng có kiểm soát riêng.

### 2.1. Đừng nhầm token usage với prompt logging

`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens` và metric `gen_ai.client.token.usage` là số liệu usage. Chúng không cần lưu prompt text để tính số token nếu provider cung cấp usage metadata.

Vì vậy, có thể theo dõi chi phí và mức sử dụng mà vẫn giữ `log-prompt=false` và `log-completion=false`.

### 2.2. Trace ID không làm dữ liệu trở nên vô danh

Trace ID giúp nối logs với spans và các service trong cùng một request. Nó không che nội dung, không thay thế pseudonymization và không giảm quyền truy cập cần thiết.

Nếu log có email hoặc tool result nhạy cảm, việc gắn trace ID chỉ giúp người có quyền tìm lại dữ liệu đó nhanh hơn.

## 3. Ma trận property ghi nội dung trong Spring AI 2.1

Các property dưới đây được tài liệu Spring AI 2.1.0 công bố. Giá trị mặc định đều là `false`.

| Loại nội dung | Property | Nội dung được ghi/xuất | Mặc định |
|---|---|---|---|
| ChatClient prompt | `spring.ai.chat.client.observations.log-prompt` | Prompt ở boundary ChatClient | `false` |
| ChatClient completion | `spring.ai.chat.client.observations.log-completion` | Completion ở boundary ChatClient | `false` |
| ChatModel prompt | `spring.ai.chat.observations.log-prompt` | Prompt ở boundary ChatModel | `false` |
| ChatModel completion | `spring.ai.chat.observations.log-completion` | Completion ở boundary ChatModel | `false` |
| Chat error logging | `spring.ai.chat.observations.include-error-logging` | Error logging trong observations | `false` |
| Tool arguments và result | `spring.ai.tools.observations.include-content` | Tool call arguments và execution result dưới dạng span attributes | `false` |
| Image prompt | `spring.ai.image.observations.log-prompt` | Text prompt gửi tới image model | `false` |
| Vector search response | `spring.ai.vectorstore.observations.log-query-response` | Nội dung documents trả về từ vector query | `false` |
| Text-to-speech input | `spring.ai.audio.speech.observations.log-text` | Text gửi tới TTS model | `false` |
| Transcription output | `spring.ai.audio.transcription.observations.log-transcript` | Transcript trả về từ transcription model | `false` |

Các cờ thuộc các boundary khác nhau. Ví dụ, bật `spring.ai.chat.client.observations.log-prompt` không có nghĩa đã bật prompt logging ở `ChatModel`; ngược lại cũng vậy. Hãy bật đúng boundary mà bạn cần điều tra.

### 3.1. ChatClient và ChatModel là hai lớp khác nhau

`ChatClient` là API cấp ứng dụng, có thể chạy advisors, memory, retrieval và tool calling. `ChatModel` là lớp gọi model. Cùng một nội dung có thể đi qua cả hai boundary.

Nếu bật cả prompt/completion logging ở cả hai lớp, logs có thể chứa cùng nội dung ở nhiều observation boundary. Hãy chọn lớp cần điều tra để giảm duplicate content và dung lượng lưu.

### 3.2. Tool content được export vào span attributes

Property `spring.ai.tools.observations.include-content` có ý nghĩa khác các property `log-*`: khi bật, arguments và result của tool được đưa vào observation dưới dạng span attributes. Chúng có thể được exporter chuyển tới trace backend.

Không coi property này là một cờ chỉ ghi application log. Nó làm tăng lượng dữ liệu trong trace spans, và mọi collector/exporter/backend nhận spans đó đều trở thành một phần của data flow cần kiểm soát.

### 3.3. Các loại audio có mặc định riêng

- TTS input text có thể chứa nội dung người dùng cung cấp; `log-text` mặc định `false`.
- Transcription transcript là personal data theo mô tả của Spring AI; `log-transcript` mặc định `false`.
- Audio input stream không được observation handler đọc; Spring AI không mô tả audio bằng file path.
- Audio output trả về từ TTS không được export theo observability reference.

Việc audio bytes không được đọc/export không có nghĩa transcript hoặc text đưa vào TTS cũng vô hại. Hai loại text đó có property logging riêng.

## 4. Các mặc định bảo vệ dữ liệu thực sự bảo vệ điều gì?

Spring AI mô tả prompt/completion, tool arguments/results, image prompt, vector response và audio text là dữ liệu có thể nhạy cảm; các nội dung này không được export mặc định.

Điều này có nghĩa các cờ content tương ứng ở trạng thái `false` sẽ không chủ động bật content logging/export theo các handlers được tài liệu hóa. Nó **không** có nghĩa toàn bộ telemetry của ứng dụng đã được ẩn danh hoặc không chứa dữ liệu.

| Quan sát | Mặc định/đặc điểm | Điều cần kiểm tra thêm |
|---|---|---|
| Prompt/completion chat | Content logging tắt | Custom handlers, log statements, provider SDK logs |
| Tool arguments/result | Không export nếu `include-content=false` | Custom tool logging, HTTP client logging, exception messages |
| Tool definition schema/description | Là high-cardinality span attributes riêng | Schema có chứa ví dụ, tên field hoặc mô tả nội bộ không |
| Tool call ID | Attribute định danh một lần gọi | Không biến thành metric label; kiểm tra khả năng nối với request |
| Vector response documents | Response content logging tắt | `db.vector.query.content` và query filters là các trace attributes riêng |
| Vector query content | Được liệt kê như high-cardinality trace key | Kiểm tra span thực tế; `log-query-response=false` không phải công tắc tắt query content |
| Model parameters | Có thể xuất thành attributes | Tránh nhúng thông tin người dùng vào custom option values |
| Token usage | Metadata số lượng token | Có thể kết hợp với model/time/tenant tags để suy ra hành vi sử dụng |
| Application logs | Theo logging configuration của ứng dụng | Logback/Log4j appenders, stdout collector, SIEM và cloud log sink |

### 4.1. Lưu ý quan trọng với vector query

Spring AI liệt kê `db.vector.query.content` và `db.vector.query.filter` trong nhóm high-cardinality attributes của vector store observation. Property `spring.ai.vectorstore.observations.log-query-response` điều khiển việc ghi nội dung response documents; nó không được mô tả là công tắc tổng quát cho query content hoặc filters.

Do đó, nếu query/filter chứa PII, tenant identifier hoặc câu hỏi nội bộ, hãy kiểm tra spans được phát ra trên đúng version và provider. Không suy luận rằng `log-query-response=false` đã loại bỏ mọi nội dung truy vấn.

### 4.2. Các đường logging ngoài property của Spring AI

Ngay cả khi mọi content property đều `false`, raw content vẫn có thể bị ghi bởi:

- Code ứng dụng log `Prompt`, `Message`, request/response object hoặc tool argument;
- Custom `ObservationHandler`, `SpanProcessor`, interceptor hoặc HTTP logging;
- Provider SDK logging ở mức DEBUG;
- Exception message chứa URL, request body hoặc response body;
- Reverse proxy, API gateway hoặc service mesh;
- Frontend/backend debug log và message broker tracing.

Mặc định của Spring AI chỉ áp dụng cho content instrumentation mà Spring AI kiểm soát. Cần kiểm tra cả các lớp xung quanh.

## 5. Thay đổi tên property khi nâng cấp

Trong quá trình chuyển sang Spring AI 1.0.0-RC1/GA, upgrade notes ghi nhận việc đổi content observation từ tracing sang logging và thay các content observation filters bằng logging handlers có khả năng gắn thông tin trace.

Các property được đổi tên:

| Property cũ | Property mới |
|---|---|
| `spring.ai.chat.client.observations.include-prompt` | `spring.ai.chat.client.observations.log-prompt` |
| `spring.ai.chat.observations.include-prompt` | `spring.ai.chat.observations.log-prompt` |
| `spring.ai.chat.observations.include-completion` | `spring.ai.chat.observations.log-completion` |
| `spring.ai.image.observations.include-prompt` | `spring.ai.image.observations.log-prompt` |
| `spring.ai.vectorstore.observations.include-query-response` | `spring.ai.vectorstore.observations.log-query-response` |

Một property legacy khác:

| Property cũ | Trạng thái |
|---|---|
| `spring.ai.chat.client.observations.include-input` | Deprecated, thay bằng `spring.ai.chat.client.observations.log-prompt` |

Các property mới dùng tên `log-*` để thể hiện rõ rằng nội dung được ghi qua logging. Upgrade notes cũng ghi nhận:

- Content observation filters được thay bằng logging handlers;
- Có `TracingAwareLoggingObservationHandler` để logs có thể được correlate với trace khi tracing khả dụng;
- Event-based tracing cho content được thay bằng direct logging;
- Dependency bridge được đổi từ `micrometer-tracing-bridge-otel` sang `micrometer-tracing`;
- Các field cấu hình Java như `includePrompt` đổi thành `logPrompt`.

### 5.1. Không đổi nhầm include-content của tool

`spring.ai.tools.observations.include-content` là property riêng cho tool arguments/results. Tài liệu migration về các property prompt, completion và query response không chỉ ra một rename tương tự cho property này.

Không tự đổi `include-content` thành `log-content`; hai cách đặt tên có thể trông giống nhau nhưng property tool hiện hành vẫn là `include-content`.

### 5.2. Thay đổi observability theo version

| Dòng phiên bản | Hành vi cần lưu ý |
|---|---|
| Trước 1.0.0-RC1 | Một số content properties còn mang tên `include-*`; content observation dựa trên tracing filters |
| 1.0.0-RC1/1.0.x | Property chuyển sang `log-*`; content observation dùng logging handlers; `include-input` được đánh dấu deprecated trong reference 1.0.9 |
| 2.0.x | Giữ mô hình content logging; tool content vẫn là property `include-content`; upgrade notes tiếp tục ghi nhận logging handler refactor |
| 2.0.2 trở đi | Bổ sung observations cho một số TTS, transcription và image model; content logging handlers vẫn tắt mặc định |
| 2.1.0 | Reference hiện hành liệt kê các property chat/tool/image/vector/audio và các mặc định `false` như bảng ở mục 3 |

Từ 2.0.2, các model TTS/transcription và Stability AI image được bổ sung observations trong một số provider implementation. Nếu trước đây hệ thống không có các spans đó, sau nâng cấp bạn có thể thấy thêm operation metrics/traces. Nội dung vẫn không tự bật: content logging handlers được ghi rõ là off by default.

### 5.3. Kiểm tra cấu hình cũ sau migration

Không giả định mọi property cũ vẫn được hỗ trợ như alias. Hãy tìm trong `application*.yml`, `application*.properties`, Helm values, ConfigMap, environment variables và secret/config store.

Ví dụ tìm các tên legacy trong repository:

~~~bash
rg -n "include-prompt|include-completion|include-query-response|include-input" .
~~~

Sau đó thay bằng property mới theo đúng boundary và xóa cấu hình cũ sau khi đã kiểm tra startup/config binding. Không giữ cả hai tên với kỳ vọng chúng cùng điều khiển một handler.

## 6. Cấu hình mặc định an toàn

Một cấu hình rõ ràng giúp reviewer nhận biết ứng dụng chủ ý giữ raw content logging tắt, thay vì dựa vào default ngầm định.

Ví dụ `application.yml`:

~~~yaml
spring:
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
      observations:
        log-prompt: false
        log-completion: false
        include-error-logging: false
    tools:
      observations:
        include-content: false
    image:
      observations:
        log-prompt: false
    vectorstore:
      observations:
        log-query-response: false
    audio:
      speech:
        observations:
          log-text: false
      transcription:
        observations:
          log-transcript: false
~~~

Đây là cấu hình explicit cho các property được tài liệu Spring AI 2.1 liệt kê. Nếu ứng dụng không sử dụng ImageModel, TTS, TranscriptionModel hoặc VectorStore thì các dòng tương ứng không tạo thêm capability; chúng chỉ ghi rõ policy cấu hình cho các component có mặt.

### 6.1. Chỉ bật ở profile local với dữ liệu giả

Nếu cần xem prompt để debug, tạo profile local riêng và dùng sample không chứa dữ liệu thật:

~~~yaml
# application-local.yml
spring:
  ai:
    chat:
      client:
        observations:
          log-prompt: true
          log-completion: true
      observations:
        log-prompt: true
        log-completion: true
~~~

Không đưa profile này vào production deployment. Cần kiểm tra profile đang active khi chạy, vì biến môi trường hoặc deployment manifest có thể vô tình bật profile local.

### 6.2. Bật đúng một boundary

Nếu lỗi nằm ở prompt augmentation của advisors, có thể cần quan sát ChatClient prompt. Nếu lỗi nằm ở model adapter, có thể cần ChatModel prompt/completion. Nếu lỗi nằm ở tool mapping, cần arguments/result trong tool span.

Chọn một boundary trước, bật trên một môi trường hoặc instance kiểm thử, dùng synthetic sample, xác nhận kết quả rồi tắt lại. Không bật toàn bộ content flags cùng lúc chỉ để “xem có gì”.

### 6.3. Đừng dùng DEBUG thay thế content policy

`logging.level.org.springframework.ai=DEBUG` làm tăng log output của các operation Spring AI. Nó không thay thế các property `log-*` và cũng không phải một policy redaction.

Khi bật DEBUG, hãy kiểm tra log thực tế để biết SDK, framework và custom components đang ghi gì. Không coi việc các cờ content là `false` là bảo đảm rằng mọi logger ở DEBUG không thể ghi raw content.
## 7. Logging và tracing sau khi nâng cấp

Một thay đổi quan trọng trong upgrade notes của Spring AI là content observation chuyển từ tracing sang logging:

- Content observation filters được thay bằng logging handlers;
- Các property include-prompt, include-completion, include-query-response đổi thành log-prompt, log-completion, log-query-response;
- Spring AI bổ sung TracingAwareLoggingObservationHandler để log có trace context khi tracing khả dụng;
- Event-based tracing cho content được thay bằng direct logging.

### 7.1. Hai đường dữ liệu khác nhau

| Cấu hình | Đường dữ liệu | Đích thường gặp |
|---|---|---|
| spring.ai.chat.*.observations.log-* | Logging handler ghi content | Application log appenders, stdout collector, log backend |
| spring.ai.tools.observations.include-content=true | Content trở thành span attributes | Tracing bridge, OTLP exporter, trace backend |
| Các low-cardinality observation keys | Meter tags và span attributes | Metrics registry và trace backend |
| High-cardinality observation keys | Span attributes | Trace backend |

Khi tracing khả dụng, logging handler có thể thêm trace information vào log để correlate. Điều này không biến log record thành span và cũng không có nghĩa raw prompt được đưa trở lại trace attributes.

### 7.2. Kiểm tra collector sau migration

Một hệ thống cũ có thể tìm prompt bằng cách query span attribute gen_ai.prompt. Sau migration, nội dung có thể nằm trong logs thay vì spans. Cần kiểm tra:

- Dashboard/trace query có đang đọc gen_ai.prompt hoặc gen_ai.completion không;
- Log pipeline có nhận các content logs mới không;
- Trace ID/span ID có được giữ trong log record khi tracing khả dụng không;
- Log retention và access policy có phù hợp với dữ liệu raw content không;
- Không vô tình bật cả log content và một custom span processor ghi cùng dữ liệu.

Spring AI 1.0.9 reference có liệt kê gen_ai.prompt như high-cardinality key tùy chọn ở một số observation tables. Reference stable 2.1 mô tả content logging qua các property log-* và không liệt kê gen_ai.prompt trong bảng ChatClient keys hiện hành. Khi nâng cấp, đừng giả định content vẫn nằm cùng một backend hoặc cùng schema.

### 7.3. Không dùng log level để thay thế property

Property log-prompt/log-completion điều khiển việc ghi content theo observation handlers. Log level như DEBUG điều khiển mức log của logger. Hai cơ chế khác nhau:

- Tắt content property không tự ngăn code riêng của ứng dụng log prompt;
- Bật DEBUG không phải là cách cấu hình chính thức để bật prompt logging;
- Log level cao hơn có thể làm xuất hiện nhiều thông tin framework/SDK hơn, cần kiểm tra output thực tế.

## 8. Xây dựng data protection policy cho telemetry

Trước khi bật một content property, hãy ghi lại mục đích và phạm vi xử lý. Một quyết định tốt có thể trả lời được dữ liệu nào cần xem, ai được xem, lưu ở đâu và xóa khi nào.

### 8.1. Phân loại nội dung

| Mức dữ liệu | Ví dụ | Cách xử lý đề xuất |
|---|---|---|
| Public | Prompt synthetic, public documentation | Có thể dùng trong test/debug theo policy chung |
| Internal | Tên advisor, tool schema nội bộ, model config | Hạn chế quyền truy cập theo team/service |
| Confidential | Prompt khách hàng, retrieved documents, ticket/order data | Redact hoặc chỉ lưu sample được duyệt; access có audit |
| Restricted | API key, password, access token, payment credential, secret key | Không ghi raw content; loại bỏ trước telemetry |

Phân loại theo nội dung thực tế, không chỉ theo tên property. Một tool result có thể là public trong môi trường test nhưng restricted trong production.

### 8.2. Data minimization

Trước khi ghi content, hãy tự hỏi:

1. Có thể trả lời câu hỏi debug bằng latency, model, token count, tool name và outcome không?
2. Có cần toàn bộ prompt hay chỉ một đoạn template đã loại dữ liệu cá nhân?
3. Có cần toàn bộ tool result hay chỉ normalized status và effect reference?
4. Có cần retrieved document body hay chỉ document IDs, source type và retrieval score?
5. Có cần log cho tất cả requests hay chỉ một test cohort được kiểm soát?

Ưu tiên safe projection: ghi tool=lookup_order, outcome=NOT_FOUND, duration_ms=120 và reference đã pseudonymize thay vì toàn bộ arguments/result.

### 8.3. Redaction trước khi dữ liệu được lưu

Các property log-* và include-content là công tắc bật/tắt. Không nên giả định chúng tự động che email, phone, access token, địa chỉ hoặc dữ liệu tenant.

Nếu cần lưu content để điều tra, thiết kế đường xử lý có redaction trước khi persistence:

- Mask/remove Authorization headers, API keys, cookies, passwords và bearer tokens;
- Thay email, phone, customer IDs, order IDs bằng token giả hoặc keyed pseudonym khi cần nối nhiều event;
- Loại bỏ field không phục vụ tiêu chí điều tra;
- Giới hạn độ dài nội dung và số lượng documents;
- Không log binary payload, encoded media hoặc raw provider response;
- Đánh dấu source và trust level của tool-originated content.

Không dùng plain hash cho identifier có miền giá trị nhỏ như số điện thoại hoặc mã đơn hàng tuần tự. Nếu cần correlation ổn định, dùng keyed HMAC hoặc tokenization service được quản lý; giữ mapping ở nơi có quyền truy cập riêng.

### 8.4. Tách tenant và quyền truy cập

- Không đưa tenant ID, user ID hoặc conversation ID vào metric labels;
- Nếu trace cần tenant context, dùng field đã được phân loại và chỉ cho phép truy cập theo tenant policy;
- Không cho mọi developer truy cập toàn bộ production logs có raw content;
- Dùng RBAC, audit trail và break-glass access có thời hạn;
- Kiểm tra quyền ở log backend, trace backend, object storage, export bucket và backup.

### 8.5. Retention và xóa dữ liệu

Raw content logs thường cần retention ngắn hơn metrics tổng hợp. Đặt retention theo mục đích điều tra và nghĩa vụ lưu trữ của tổ chức, không dùng mặc định dài nhất của log platform.

Cần xác định:

- TTL riêng cho content logs;
- TTL cho spans có tool arguments/result;
- Chính sách xóa trong hot storage, archive và backup;
- Ai phê duyệt export content ra ngoài hệ thống;
- Quy trình xử lý khi phát hiện secret/PII đã bị ghi nhầm.

### 8.6. Sampling không phải redaction

Sampling có thể giảm số lượng traces được lưu nhưng không đảm bảo dữ liệu nhạy cảm không bị ghi. Một request được sample vẫn có thể mang raw content. Hãy tắt content trước, rồi mới áp dụng sampling cho telemetry metadata theo mục tiêu vận hành.

## 9. Quy trình debug có kiểm soát

Khi cần bật content logging để điều tra một lỗi, thực hiện theo một quy trình ngắn, có chủ sở hữu và điểm kết thúc.

1. **Mở incident/debug task:** ghi câu hỏi kỹ thuật cần trả lời và người chịu trách nhiệm.
2. **Chọn boundary:** ChatClient, ChatModel, tool, vector store, image, TTS hoặc transcription.
3. **Chọn môi trường:** ưu tiên local/staging với synthetic hoặc sanitized fixture.
4. **Chọn phạm vi:** một service, một instance hoặc một cohort nhỏ nếu hệ thống cho phép.
5. **Bật đúng property:** chỉ bật loại content cần thiết.
6. **Giới hạn thời gian:** xác định giờ bật, giờ tắt và người chịu trách nhiệm tắt.
7. **Kiểm tra log/trace:** xác nhận dữ liệu thực sự cần thiết đã xuất hiện và không có field ngoài dự kiến.
8. **Redact và review:** loại bỏ nội dung không cần thiết trước khi chia sẻ ticket hoặc tài liệu.
9. **Tắt property:** deploy lại cấu hình an toàn và xác minh runtime config.
10. **Dọn dữ liệu tạm:** xóa export/sample có raw content theo retention policy.

Không để cờ content logging tồn tại vô thời hạn chỉ vì “có thể cần debug sau này”.

## 10. Kiểm thử mặc định và migration

Tạo integration tests với synthetic sentinel strings như SYNTHETIC_EMAIL_001, SYNTHETIC_SECRET_001 và SYNTHETIC_ORDER_001. Các chuỗi này giúp phát hiện content bị ghi ngoài dự kiến mà không sử dụng dữ liệu thật.

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| **TC01 — ChatClient prompt off** | log-prompt=false | Prompt sentinel không xuất hiện trong content logs |
| **TC02 — ChatClient completion off** | log-completion=false | Completion sentinel không xuất hiện trong content logs |
| **TC03 — ChatModel prompt off** | ChatModel log-prompt=false | Không có prompt content log ở model boundary |
| **TC04 — ChatModel completion off** | ChatModel log-completion=false | Không có completion content log ở model boundary |
| **TC05 — Error logging off** | include-error-logging=false | Không bật error logging qua observation property |
| **TC06 — Tool content off** | include-content=false | Arguments/result sentinel không nằm trong tool span attributes |
| **TC07 — Tool content on** | Bật trong fixture synthetic | Arguments/result xuất hiện theo contract |
| **TC08 — Image prompt off** | log-prompt=false | Image prompt sentinel không xuất hiện |
| **TC09 — Vector response off** | log-query-response=false | Response document body không được log theo handler này |
| **TC10 — Vector query attribute** | Thực hiện query synthetic | Kiểm tra riêng db.vector.query.content và filters trong span |
| **TC11 — TTS text off** | log-text=false | TTS input sentinel không xuất hiện |
| **TC12 — Transcript off** | log-transcript=false | Transcript sentinel không xuất hiện |
| **TC13 — Audio bytes** | Gửi audio stream | Observation handler không đọc audio payload |
| **TC14 — Trace correlation** | Bật tracing, content logging ở test | Log có trace correlation khi tracing khả dụng |
| **TC15 — No trace content assumption** | Bật log-prompt nhưng không bật tool content | Prompt logs không bị nhầm thành tool span attributes |
| **TC16 — Legacy property scan** | Cấu hình có include-prompt cũ | CI/config review phát hiện legacy key |
| **TC17 — Profile isolation** | Profile local bật prompt logging | Production profile vẫn giữ false |
| **TC18 — Redaction** | Fixture có synthetic secret | Secret không xuất hiện trong persisted log |
| **TC19 — Retention** | Content record quá TTL | Record bị xóa theo policy |
| **TC20 — Access control** | User không có quyền mở content logs | Backend từ chối truy cập và ghi audit |
| **TC21 — Tenant isolation** | Hai tenant dùng sample khác nhau | Không thể đọc content tenant còn lại |
| **TC22 — Duplicate boundaries** | Cùng request đi qua ChatClient và ChatModel | Xác định rõ boundary nào log, không duplicate ngoài ý muốn |
| **TC23 — Provider DEBUG logs** | Bật DEBUG trong test | Kiểm tra SDK không ghi raw request/response ngoài policy |
| **TC24 — Exporter path** | Export OTLP/log collector | Không có content ngoài các field đã được duyệt |

### 10.1. Test không chỉ assert property binding

Property binding thành công không chứng minh dữ liệu đã được bảo vệ. Cần kiểm tra output thực tế ở các lớp:

- Captured application logs;
- In-memory span exporter hoặc test trace backend;
- Prometheus exposition nếu metric tags được tạo;
- Log collector/OTLP collector sau processor;
- Persisted test store nếu có archive pipeline.

Test phải chứng minh cả hai điều: content cần tắt không xuất hiện; content được bật trong fixture chỉ xuất hiện ở đúng destination dự kiến.

## 11. Quy trình nâng cấp trong CI/CD

1. **Inventory:** liệt kê content properties hiện tại và nơi cấu hình chúng.
2. **Đối chiếu version:** xác định Spring AI, Spring Boot, Micrometer, tracing bridge và exporter đang resolve.
3. **Tìm legacy keys:** quét include-prompt, include-completion, include-query-response, include-input.
4. **Lập data map:** ghi prompt/completion/tool/vector/audio content đi vào log hay span.
5. **Chuyển property:** thay tên cũ bằng log-* tương ứng; giữ tool include-content theo đúng contract.
6. **Kiểm tra boundary mới:** đặc biệt TTS/transcription/image observations có thể xuất hiện sau khi nâng provider/module.
7. **Kiểm tra query content:** xác minh vector query/filter attributes độc lập với response logging.
8. **Chạy synthetic tests:** dùng sentinel strings, capture logs và spans.
9. **Kiểm tra redaction/access/retention:** xác nhận các sink downstream có policy tương ứng.
10. **Review profile:** đảm bảo debug flags không bị kế thừa vào production.
11. **Phát hành canary:** kiểm tra log volume, trace volume và content exposure trước khi rollout toàn bộ.
12. **Lưu evidence:** ghi version, property snapshot, test results và người phê duyệt.

### Checklist trước khi merge

- [ ] ChatClient prompt/completion logging đều false trong production.
- [ ] ChatModel prompt/completion logging đều false trong production.
- [ ] include-error-logging được đặt theo policy.
- [ ] Tool include-content false trừ khi có exception được duyệt.
- [ ] Image prompt, vector response, TTS text và transcript flags false.
- [ ] Legacy include-* keys đã được tìm và thay thế.
- [ ] Không nhầm tool include-content với các property log-*.
- [ ] Vector query content/filter attributes đã được kiểm tra riêng.
- [ ] Logs và spans có redaction trước persistence khi content được phép ghi.
- [ ] RBAC, audit, encryption và retention áp dụng cho mọi sink.
- [ ] Debug profile không được nạp trong production.
- [ ] Synthetic tests xác nhận content không rò sang logs/traces ngoài dự kiến.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Bật prompt logging để đo token | Lưu raw prompt không cần thiết | Dùng token usage metrics |
| Nghĩ log-prompt đưa content vào trace | Query trace không thấy content hoặc team log sai nơi | Kiểm tra logging handler và log backend |
| Nghĩ include-content của tool chỉ ghi log | Tool args/result xuất hiện trên spans | Kiểm tra trace exporter và backend |
| Tắt log-query-response rồi cho rằng vector query đã sạch | Query/filter content có thể vẫn là trace attributes | Kiểm tra db.vector.query.content và filters |
| Giữ property include-* cũ | Cấu hình cũ không còn điều khiển handler như mong đợi | Dùng property log-* theo release |
| Bật tất cả content flags | Tăng exposure và log volume | Bật đúng boundary cần điều tra |
| Chỉ kiểm application.yml | Environment variables/ConfigMap ghi đè cấu hình | Kiểm tra effective runtime configuration |
| Dựa vào sampling để bảo vệ PII | Sampled trace vẫn chứa raw data | Redact/minimize trước export |
| Đưa tool call ID vào metric tags | Cardinality tăng mạnh | Giữ ID ở trace/log có kiểm soát |
| Dùng DEBUG production dài hạn | Log volume và data exposure tăng | Giới hạn scope/thời gian, kiểm tra output và tắt sau debug |

## 13. Bài luyện tập

### Bài 1 — Prompt không còn xuất hiện trong trace

Sau khi nâng từ Spring AI 1.0.x, dashboard trace không còn thấy gen_ai.prompt, nhưng logs có thể correlate bằng trace ID. Hãy giải thích thay đổi content observation và nơi cần kiểm tra.

### Bài 2 — Chọn property cho ChatClient

Bạn cần kiểm tra prompt sau khi advisor đã bổ sung retrieved context. Property nào phù hợp? Vì sao ChatModel prompt logging có thể quan sát boundary khác?

### Bài 3 — Tool arguments chứa email

Một tool nhận email và order ID. Property nào bật arguments/result span attributes? Vì sao không nên bật rộng trong production?

### Bài 4 — Vector response đã tắt nhưng query vẫn nhạy cảm

log-query-response=false nhưng query content vẫn xuất hiện trên span. Giải thích vì sao và đề xuất xử lý.

### Bài 5 — Đổi property cũ

Dự án đang dùng spring.ai.chat.observations.include-prompt. Hãy nêu property mới và cách xác minh sau migration.

### Bài 6 — Theo dõi chi phí mà không log prompt

Bạn cần token usage theo model và operation. Có cần bật log-prompt không? Nêu metric/attributes nên dùng.

### Bài 7 — Transcription

Ứng dụng mới bật transcription model sau khi nâng lên 2.0.2. Dữ liệu nào được observation handler đọc? Property nào điều khiển transcript logging?

### Bài 8 — Hai boundary cùng ghi

ChatClient và ChatModel cùng bật prompt/completion logging. Rủi ro nào phát sinh? Làm sao giảm trùng lặp?

### Bài 9 — Profile debug

Thiết kế cách bật prompt logging cho local fixture synthetic, đảm bảo không bị bật trong production.

### Bài 10 — Data incident

Một tool result có secret đã xuất hiện trong trace backend. Hãy nêu các bước containment, xác định scope, xử lý bản lưu và ngăn tái diễn.

### Gợi ý đáp án

1. Content observation được chuyển từ tracing filters sang logging handlers; kiểm tra application log sink và trace-aware correlation thay vì chỉ query span attribute.
2. Dùng spring.ai.chat.client.observations.log-prompt; ChatModel boundary nằm ở model call, còn ChatClient boundary có thể bao gồm prompt đã được advisor augment.
3. Dùng spring.ai.tools.observations.include-content=true; property này đưa arguments/result vào span attributes, nên exporter và trace backend có thể nhận PII.
4. log-query-response điều khiển response documents, không phải công tắc tổng quát cho query content/filter attributes. Kiểm tra db.vector.query.content và áp dụng redaction/custom handling.
5. Đổi thành spring.ai.chat.observations.log-prompt; kiểm tra effective config và captured logs với sentinel fixture.
6. Không cần. Dùng gen_ai.client.token.usage, model/provider và operation metadata.
7. Audio input stream không được observation handler đọc; transcript output có thể được log bằng spring.ai.audio.transcription.observations.log-transcript, mặc định false.
8. Cùng content có thể được ghi ở nhiều boundary. Chọn một boundary theo mục tiêu debug và tắt cờ ở boundary còn lại.
9. Đặt flags trong application-local.yml, chỉ dùng synthetic data, xác minh profile production không load local và thêm CI test.
10. Tắt content export, khóa quyền truy cập, xác định trace IDs/time range/sinks/backup, xử lý retention/deletion theo incident policy, rotate secret nếu cần, thêm test để ngăn lặp lại.

## Tài liệu tham khảo

- [Spring AI 1.0.9 — Observability](https://docs.spring.io/spring-ai/reference/1.0/observability/index.html): property log-prompt, include-input deprecated, high-cardinality attributes và vector response logging.
- [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): content logging properties/defaults cho ChatClient, ChatModel, tool, image, vector, TTS và transcription.
- [Spring AI — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): chuyển content observation từ tracing sang logging, property renames và TracingAwareLoggingObservationHandler.
- [Spring AI 2.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/2.0/upgrade-notes.html): thay đổi observability trong quá trình nâng cấp.
- [Spring AI 2.0.2 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): bổ sung observations cho TTS, transcription và Stability AI image; content handlers mặc định off.
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): tool arguments/result có thể export dưới dạng span attributes; include-content mặc định false.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging configuration và log output của ứng dụng.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): trace propagation và correlation trong Spring ecosystem.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation lifecycle, handlers và context.
- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): cân nhắc xử lý dữ liệu nhạy cảm trong telemetry pipeline.

**Kết luận:** Spring AI giữ các content logging switches ở trạng thái false theo mặc định, nhưng mỗi boundary có property riêng: ChatClient, ChatModel, tool, image, vector response, TTS và transcription. Khi nâng cấp, cần đổi các property include-* cũ sang log-*, hiểu rằng prompt/completion content đã chuyển sang logging handlers, và kiểm tra tool arguments/result được export vào spans khi include-content=true. Đặc biệt, không suy luận log-query-response=false đã loại bỏ vector query/filter attributes. Hãy giữ raw content tắt trong production, chỉ bật đúng boundary cho fixture đã sanitise, redaction trước persistence và áp dụng access/retention cho mọi log và trace sink.
