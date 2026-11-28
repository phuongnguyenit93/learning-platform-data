# Cấu hình ghi nội dung theo thành phần và môi trường

Một ứng dụng Spring AI thường có nhiều thành phần cùng ghi log: code nghiệp vụ, prompt assembly, ChatClient/ChatModel, VectorStore, tool callbacks, evaluator, SDK của nhà cung cấp model, HTTP client và tracing exporter. Mỗi thành phần có mức độ nhạy cảm khác nhau. Một cấu hình DEBUG rộng cho toàn bộ ứng dụng có thể làm lộ prompt, retrieved context, tool arguments hoặc response body dù code nghiệp vụ không hề chủ động ghi những dữ liệu đó.

Vì vậy, logging policy cần được cấu hình theo **thành phần** và **môi trường**. Developer cần quan sát metadata của toàn pipeline, nhưng quyền ghi raw content phải được kiểm soát riêng theo mục đích, data classification và quyền truy cập. Local development có thể dùng fixture giả để xem luồng xử lý; CI cần log ổn định để kiểm thử; staging cần dữ liệu đã được làm sạch; production mặc định chỉ ghi metadata và error details đã sanitize.

Bài học thuộc module **SPRING_AI_EVALUATION_OBSERVABILITY**. Nội dung tập trung thiết kế cấu hình Logback/Spring Boot, logger categories, Spring AI observations, provider SDK và HTTP wire logging; phân chia policy theo prompt, retrieval, model, tool và evaluator; quản lý cấu hình hiệu lực; kiểm thử cấu hình; và xử lý sự cố khi raw content vô tình xuất hiện trong log.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao logging policy cần được phân chia theo component và environment.
2. Phân biệt log level với quyền capture prompt/response content.
3. Xây dựng ma trận logging policy cho prompt, retrieval, model, tool, evaluator và error handling.
4. Cấu hình logger categories bằng Spring Boot và Logback.
5. Dùng logback-spring.xml để áp dụng cấu hình theo Spring profile.
6. Kiểm soát Spring AI observation content capture theo đúng phiên bản thư viện.
7. Nhận diện SDK debug logging và HTTP wire logging có thể ghi request/response body.
8. Thiết kế local, test, staging và production profiles với mức ghi phù hợp.
9. Quản lý cấu hình qua YAML, environment variables, config server và deployment overrides.
10. Tạo cơ chế chẩn đoán tạm thời có thời hạn, scope và audit.
11. Kiểm thử effective logging configuration và phát hiện raw content trong output.
12. Điều tra một sự cố lộ prompt/response và khôi phục cấu hình an toàn.

## 2. Vì sao phải cấu hình theo component và environment?

Một ứng dụng AI không có một logger duy nhất. Mỗi lớp có mục đích, volume và dữ liệu đầu vào khác nhau.

| Component | Dữ liệu thường xử lý | Metadata nên quan sát | Content cần kiểm soát |
| --- | --- | --- | --- |
| Request/API layer | User request, headers | request ID, route, status, duration | request body, cookies, authorization |
| Prompt assembly | System/user messages, memory | template version, message count, token estimate | rendered prompt và conversation |
| Retrieval | Query, chunks, filters | corpus/index, top-k, result count, latency | query text, chunk content, document title |
| ChatModel/provider | Prompt, response, usage | provider/model, duration, tokens, finish reason | request/response body |
| Tool execution | Arguments, backend result | tool name, schema version, authorization, status | arguments và result payload |
| Evaluator | Question, answer, reference | rubric/judge version, metric, verdict | answer, context, free-form feedback |
| Error handling | Exception, provider response | error code, type, retry disposition | exception body, headers, raw provider message |
| Tracing/observations | Span attributes/events | operation, status, timing, trace IDs | prompt/completion attributes nếu được bật |

Nếu chỉ cấu hình theo package tổng quát, nhóm có thể vô tình bật DEBUG cho cả thành phần xử lý dữ liệu nhạy cảm. Nếu chỉ cấu hình theo environment, một thành phần có rủi ro cao vẫn có thể ghi content không cần thiết.

Cần kết hợp hai chiều:

- Environment xác định baseline logging policy.
- Component xác định dữ liệu nào được phép ghi trong baseline đó.
- Content capture policy là quyết định riêng, không được suy ra từ log level.

## 3. Phân biệt log level, component policy và content capture

Ba khái niệm này không thay thế nhau.

| Cơ chế | Kiểm soát điều gì? | Ví dụ |
| --- | --- | --- |
| Log level | Mức chi tiết của diagnostic events | INFO, WARN, DEBUG |
| Component logger | Thành phần/package được phép phát event | com.example.ai.retrieval |
| Content capture policy | Có được persist raw/redacted prompt/response không | DENIED, REDACT_ONLY, ALLOWED |

Đặt logger của package ở DEBUG chỉ thay đổi mức log được phát. Nó không phải cơ chế cấp quyền lưu prompt. Ngược lại, một evidence capture policy có thể cho phép lưu một artifact theo purpose cụ thể mà không cần bật DEBUG toàn ứng dụng.

### 3.1. Quy tắc nền tảng

- Operational logs mặc định chỉ chứa allowlisted metadata.
- Raw prompt/response không được bật chỉ bằng thay đổi log level.
- Nếu cần capture content, phải đi qua evidence service với authorization, purpose, tenant scope, redaction và retention.
- Các SDK/provider/HTTP client logs phải được kiểm soát riêng.
- Cấu hình production phải có thể kiểm tra được sau khi mọi property sources đã được resolve.

### 3.2. Không tạo một cờ DEBUG_CONTENT toàn cục

Một biến như AI_DEBUG=true dễ bị dùng cho nhiều mục đích cùng lúc: tăng log level, bật wiretap, bật prompt capture và in response. Hãy tách cấu hình metadata diagnostics khỏi content capture. Content capture cần policy service hoặc cơ chế kiểm soát tương đương.

## 4. Ma trận logging policy theo component

Bắt đầu từ ma trận này rồi điều chỉnh theo dữ liệu và yêu cầu của service.

| Component | Local | Automated test/CI | Staging | Production |
| --- | --- | --- | --- | --- |
| API/request | Metadata DEBUG có giới hạn; synthetic fixtures | Metadata cần cho assertion | INFO metadata | INFO metadata |
| Prompt assembly | Version/count/token estimate; raw chỉ với fixture giả | Không raw content trừ fixture test | Metadata-only | Metadata-only |
| Retrieval | Result counts/rank summary; chunk text chỉ trong test fixture | Deterministic metadata | Metadata-only | Metadata-only |
| ChatModel | Provider/model/usage/timing | Stub/fake provider metadata | Metadata-only | Metadata-only |
| Provider SDK | WARN/INFO; debug có kiểm soát | Stub hoặc test logger | INFO/WARN | WARN/ERROR |
| HTTP client | Không wiretap body mặc định | Mock server; payload fixture | Body logging OFF | Body/header logging OFF |
| Tool | Name/schema/status; fixture arguments | Synthetic fixtures | Metadata-only | Metadata-only |
| Evaluator | Verdict/rubric; evidence refs | Fixture evidence | Metadata-only | Metadata-only |
| Trace/observations | Metadata-only; inspect exporter | In-memory test exporter | Metadata-only | Metadata-only |
| Error handling | Sanitized error details | Assert code/category | Sanitized details | Sanitized details |

Ma trận không có nghĩa local luôn được phép xem dữ liệu thật. Local development nên dùng synthetic data. Nếu developer cần kiểm tra một case production, hãy dùng workflow evidence access riêng và có audit; không sao chép raw content sang local log.

## 5. Cấu hình Spring Boot theo profile

Spring Boot hỗ trợ externalized configuration và profile-specific configuration. Có thể đặt baseline chung trong application.yml, rồi override bằng application-local.yml, application-test.yml, application-staging.yml và application-prod.yml.

Ví dụ baseline metadata-only:

~~~yaml
spring:
  application:
    name: support-assistant

  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false

logging:
  level:
    root: INFO
    com.example.support: INFO
    com.example.ai.prompt: INFO
    com.example.ai.retrieval: INFO
    com.example.ai.model: INFO
    com.example.ai.tool: INFO
    com.example.ai.evaluation: INFO
    org.springframework.ai: INFO
    reactor.netty.http.client: WARN
~~~

Các property observation minh họa theo naming convention của Spring AI ở những phiên bản có hỗ trợ. Hãy xác minh property names và default của đúng Spring AI version trong dự án. Không sao chép property từ phiên bản khác rồi giả định nó có hiệu lực.

### 5.1. Profile local

~~~yaml
# application-local.yml
logging:
  level:
    com.example.support: DEBUG
    com.example.ai.prompt: DEBUG
    com.example.ai.retrieval: DEBUG
    com.example.ai.model: INFO
    com.example.ai.tool: DEBUG
    com.example.ai.evaluation: DEBUG
    org.springframework.ai: INFO
    reactor.netty.http.client: WARN

spring:
  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false
~~~

DEBUG ở đây chỉ dành cho diagnostic metadata. Nếu cần xem raw prompt trong local, chỉ dùng synthetic fixture hoặc evidence capture đã được policy cho phép. Không bật HTTP wiretap body như một shortcut.

### 5.2. Profile test/CI

~~~yaml
# application-test.yml
logging:
  level:
    root: WARN
    com.example.support: INFO
    com.example.ai: INFO
    org.springframework.ai: WARN
    reactor.netty.http.client: WARN

spring:
  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false
~~~

CI nên dùng fake/stub provider hoặc deterministic test fixture nếu có thể. Test cần log đủ để tìm lỗi assertion và correlation, nhưng không cần prompt thật từ user.

### 5.3. Profile staging

~~~yaml
# application-staging.yml
logging:
  level:
    root: INFO
    com.example.support: INFO
    com.example.ai: INFO
    org.springframework.ai: INFO
    reactor.netty.http.client: WARN

spring:
  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false
~~~

Staging thường dùng để xác minh deployment và integration. Nếu staging có dữ liệu gần production, giữ metadata-only policy. Việc môi trường có tên staging không làm dữ liệu tự động trở thành non-sensitive.

### 5.4. Profile production

~~~yaml
# application-prod.yml
logging:
  level:
    root: INFO
    com.example.support: INFO
    com.example.ai: INFO
    org.springframework.ai: WARN
    reactor.netty.http.client: WARN

spring:
  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false
~~~

Production không bật raw prompt/completion capture trong observations. Không bật SDK debug hoặc HTTP body logging toàn cục. Nếu cần điều tra sâu, tăng metadata diagnostics cho một component cụ thể trong thời gian ngắn và theo change control.

## 6. Cấu hình logger theo package và component

Tổ chức package theo component giúp đặt policy rõ ràng:

~~~text
com.example.support.api
com.example.ai.prompt
com.example.ai.retrieval
com.example.ai.model
com.example.ai.tool
com.example.ai.evaluation
com.example.ai.evidence
com.example.ai.error
~~~

Tên package chỉ là ví dụ. Dự án có thể dùng package khác, nhưng cần logger categories nhất quán.

### 6.1. Tránh bật DEBUG ở root

Không nên:

~~~yaml
logging:
  level:
    root: DEBUG
~~~

Cấu hình này có thể mở rộng log volume và bật nhiều thư viện phụ thuộc cùng lúc. Thay vào đó, chỉ bật DEBUG cho package cụ thể và thời gian có giới hạn.

### 6.2. Không bật DEBUG cho toàn bộ Spring AI chỉ để xem một stage

Ví dụ cần kiểm tra retrieval orchestration. Có thể tăng logger của adapter retrieval trong code ứng dụng, nhưng giữ provider SDK và HTTP client ở INFO/WARN. Điều tra model call thì tăng metadata logger của model adapter, không tăng mọi package.

### 6.3. Tạo logger riêng cho content diagnostics?

Tốt nhất không tạo logger có nhiệm vụ in raw prompt/response. Nếu có logger chuyên biệt cho capture diagnostics, nó chỉ ghi capture decision, artifact ID, policy version và failure code. Raw content được gửi trực tiếp tới evidence service, không qua logger.

## 7. Dùng logback-spring.xml cho profile-specific appenders

Khi cần cấu hình appender hoặc logger theo Spring profile, dùng logback-spring.xml để Spring Boot xử lý các profile extensions.

Ví dụ:

~~~xml
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <logger name="com.example.ai.prompt" level="INFO"/>
    <logger name="com.example.ai.retrieval" level="INFO"/>
    <logger name="com.example.ai.model" level="INFO"/>
    <logger name="com.example.ai.tool" level="INFO"/>
    <logger name="com.example.ai.evaluation" level="INFO"/>

    <springProfile name="local">
        <logger name="com.example.ai.prompt" level="DEBUG"/>
        <logger name="com.example.ai.retrieval" level="DEBUG"/>
        <logger name="com.example.ai.evaluation" level="DEBUG"/>
    </springProfile>

    <springProfile name="test">
        <logger name="com.example.ai" level="INFO"/>
    </springProfile>

    <springProfile name="staging">
        <logger name="com.example.ai" level="INFO"/>
        <logger name="org.springframework.ai" level="INFO"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="com.example.ai" level="INFO"/>
        <logger name="org.springframework.ai" level="WARN"/>
        <logger name="reactor.netty.http.client" level="WARN"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là cấu hình minh họa cho log metadata; LogstashEncoder cần được thêm dependency tương ứng và kiểm thử theo phiên bản Logback đang dùng. JSON encoder không tự bảo đảm redaction. Với structured logs, chỉ đưa allowlisted fields vào event và giữ cùng policy component/profile.

### 7.1. Tại sao là logback-spring.xml?

Spring Boot hỗ trợ các phần mở rộng như springProfile và springProperty trong logback-spring.xml. Logback thuần không biết Spring Environment nếu khởi tạo trước Spring. Đặt tên file đúng để tránh nhầm cơ chế.

### 7.2. Kiểm tra logger additivity

Một logger có thể gửi event lên parent/root logger. Nếu gắn nhiều appender, một event có thể xuất hiện nhiều lần hoặc đi tới sink có retention/quyền khác. Kiểm tra additivity và appender routing khi tạo dedicated logger.

### 7.3. Appender không phải content policy

Chuyển sang file riêng, index riêng hoặc appender riêng không tự làm raw content an toàn. Mỗi sink vẫn cần ACL, encryption, retention, export policy và audit.

## 8. Cấu hình Spring AI observations

Spring AI cung cấp observability integration dựa trên Micrometer. Observation có thể giúp theo dõi operation và trace context của ChatClient/ChatModel, VectorStore hoặc tool tùy thành phần và phiên bản.

Một số phiên bản cung cấp property để điều khiển việc đưa prompt/completion vào observation metadata. Các tên thường gặp trong cấu hình chat observation là:

~~~yaml
spring:
  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false
~~~

Hãy kiểm tra reference của đúng version đang dùng, vì API, property name, default và instrumentation scope có thể thay đổi. Việc property xuất hiện trong YAML không chứng minh nó được bind hoặc component đang dùng nó.

### 8.1. Metadata-only là baseline

Với production và dữ liệu thật, đặt prompt/completion capture OFF. Observation vẫn có thể ghi operation name, model/provider metadata, duration, error và tracing correlation nếu instrumentation hỗ trợ.

### 8.2. Không bật content chỉ để cải thiện trace

Trace backend có thể được chia sẻ rộng, sampling và retention khác evidence store. Nếu reviewer cần xem prompt/answer, dùng evidence artifact có access control thay vì đưa content vào span attributes.

### 8.3. Kiểm tra exporter thực tế

Kiểm tra span attributes ở exporter/backend, không chỉ nhìn property file. Custom ObservationConvention, advisor, SDK instrumentation hoặc instrumentation khác có thể thêm field riêng.

### 8.4. Quan sát theo component

Tạo test/integration test cho từng operation:

- ChatClient/ChatModel: không có prompt/completion text.
- VectorStore/retrieval: không có query hoặc chunk body nếu policy cấm.
- Tool: không có arguments/result payload.
- Evaluator: không có answer/reference body.
- HTTP client: không có request/response body hoặc sensitive headers.

Không suy từ việc ChatModel observation an toàn rằng toàn bộ pipeline cũng an toàn.

## 9. Provider SDK và HTTP client logging

Đây là một trong những nguồn lộ content dễ bị bỏ qua. Application logger có thể metadata-only nhưng SDK hoặc HTTP transport vẫn ghi request body.

### 9.1. SDK logger categories

Kiểm tra tài liệu của provider SDK để biết logger names và mức log. Không bật DEBUG cho toàn bộ package SDK trong production nếu chưa xác minh output. Một số SDK ghi request IDs và status; một số khác có thể ghi body hoặc headers.

### 9.2. HTTP wire logging

HTTP wiretap/debug có thể ghi:

- Request URL và query parameters.
- Authorization/API key headers.
- Request body chứa prompt, context và tool definitions.
- Response body chứa model output.
- Retry request/response lặp lại payload.

Giữ body/header logging OFF trong production. Nếu cần debug protocol, dùng mock server và synthetic fixtures hoặc cơ chế redacted capture đã kiểm thử.

### 9.3. Reactor Netty

Chỉ đặt logger level của reactor.netty.http.client không nhất thiết bật wiretap body logging; wiretap còn phụ thuộc cấu hình HttpClient. Tuy nhiên, khi bật wiretap hoặc logging handler, phải kiểm tra output thực tế vì request/response bytes có thể xuất hiện.

Không cấu hình wiretap chỉ bằng một biến debug dùng chung. Nếu thật sự cần, phải có scope, environment, expiry, synthetic payload hoặc approval và kiểm tra không có secrets.

### 9.4. RestClient/WebClient/Apache HttpClient

Mỗi HTTP stack có cơ chế logging riêng. Tìm interceptor, filter, request logger, wiretap, observation convention và SDK diagnostics. Một service có thể dùng nhiều HTTP client khác nhau cho model provider, VectorStore và internal APIs.

### 9.5. Exception body

Provider exception có thể chứa response body, URL, headers hoặc serialized request. Error mapper phải trích xuất status/error code an toàn; không log nguyên exception message nếu chưa kiểm tra.

## 10. Policy theo từng thành phần Spring AI

### 10.1. Prompt assembly

Nên ghi:

- prompt template version/digest.
- message count và role counts.
- token estimate.
- advisor/memory policy version.
- capture status và evidence reference.

Không ghi rendered prompt hoặc conversation body vào operational logs.

### 10.2. Retrieval

Nên ghi:

- VectorStore/index/corpus version.
- top-k, result count, selected count.
- filter/reranker version.
- latency và error code.
- retrieval evidence reference nếu có.

Không ghi chunk text hoặc document title nhạy cảm. Query text cũng là content và có thể chứa PII.

### 10.3. Model

Nên ghi provider, requested/resolved model ID, operation, safe generation parameters, usage, finish reason, latency, retry count và status.

Không ghi request/response body. Provider request ID chỉ ghi khi policy cho phép.

### 10.4. Tool

Nên ghi tool name/schema version, validation result, authorization decision, backend operation reference, duration và execution status.

Không ghi arguments/result object nguyên trạng. Nếu cần audit, capture qua evidence store hoặc audit store riêng.

### 10.5. Evaluator

Nên ghi evaluation ID, metric name, verdict, score (nếu phù hợp), rubric/judge version, duration và evidence refs.

Không ghi full answer, reference document hoặc free-form judge feedback vào operational log mặc định.

### 10.6. Evidence service

Nên ghi capture decision, artifact type, policy version, classification, redaction status, storage result và opaque artifact ID.

Không ghi bytes, raw content, signed URL hoặc secret. Evidence service phải có access audit riêng.

## 11. Profile không phải cơ chế authorization

Spring profile là cách chọn cấu hình khi ứng dụng khởi động. Nó không tự chứng minh người bật profile có quyền đọc dữ liệu hoặc có lý do hợp lệ để capture content.

Ví dụ:

~~~text
SPRING_PROFILES_ACTIVE=local
~~~

Không nên suy ra local profile có quyền ghi raw prompt của khách hàng. Nếu cần xem content, evidence service phải xác minh policy độc lập.

### 11.1. Tránh nhiều profile mâu thuẫn

Một deployment có thể bật nhiều profile cùng lúc. Property resolution có thể làm giá trị cuối khác với file mà developer đang xem. Cần biết active profiles và effective properties sau precedence.

### 11.2. Không dùng profile để bật raw content ở staging

Staging thường có integration với provider thật hoặc dataset gần production. Giữ content capture OFF trừ workflow đã được phê duyệt và dữ liệu được phép.

### 11.3. Production guard

Có thể thêm startup validation: nếu environment là prod mà include-prompt/include-completion hoặc wire logging body được bật, ứng dụng fail startup hoặc phát security configuration error theo policy. Guard phải kiểm tra effective configuration, không chỉ file mặc định.

## 12. Quản lý cấu hình qua environment variables

Spring Boot hỗ trợ relaxed binding từ environment variables. Ví dụ property:

~~~yaml
logging:
  level:
    com.example.ai.retrieval: INFO

spring:
  ai:
    chat:
      observations:
        include-prompt: false
        include-completion: false
~~~

Có thể override qua biến môi trường theo naming convention tương ứng, ví dụ:

~~~text
LOGGING_LEVEL_COM_EXAMPLE_AI_RETRIEVAL=DEBUG
SPRING_AI_CHAT_OBSERVATIONS_INCLUDE_PROMPT=false
SPRING_AI_CHAT_OBSERVATIONS_INCLUDE_COMPLETION=false
~~~

Tên biến observation cần được xác nhận theo property thực tế của version đang chạy. Environment variable là config input, không phải authorization mechanism.

### 12.1. Kiểm soát ai được thay đổi biến môi trường

Deployment manifests, Helm values, container definitions và secret/config stores đều có thể override property. Review quyền sửa các nguồn này; ghi deployment/config snapshot ID và changed keys.

### 12.2. Không in toàn bộ environment

Không dùng lệnh dump environment vào log hoặc ticket. Environment có thể chứa credentials, tokens, database URLs và secrets. Chỉ log active profiles và safe config snapshot đã allowlist.

### 12.3. Không để default production mở content

Giá trị default trong application.yml nên metadata-only. Profile local có thể tăng diagnostic metadata; không đặt default raw capture là true rồi trông chờ production override false.

## 13. Desired configuration và effective configuration

Configuration file cho biết giá trị được khai báo. Effective configuration là kết quả sau khi Spring resolve property sources, profile, environment variables, command-line args, config server, defaults và runtime overrides.

Một config snapshot có thể ghi:

~~~json
{
  "configSnapshotId": "support-assistant-prod-cfg-42",
  "environment": "prod",
  "activeProfiles": ["prod"],
  "loggingPolicyVersion": "metadata-only-v3",
  "components": {
    "prompt": "METADATA_ONLY",
    "retrieval": "METADATA_ONLY",
    "model": "METADATA_ONLY",
    "tool": "METADATA_ONLY",
    "evaluator": "METADATA_ONLY",
    "providerSdk": "WARN_ONLY",
    "httpWireBody": "DISABLED",
    "observationsPrompt": false,
    "observationsCompletion": false
  },
  "sourceSummary": [
    "application-defaults",
    "application-prod",
    "deployment-environment"
  ],
  "fingerprint": "sha256:..."
}
~~~

### 13.1. Snapshot chỉ chứa safe fields

Không serialize toàn bộ Environment hoặc Actuator configprops. Dùng allowlist các property đã được duyệt. Với secret, chỉ lưu logical reference/version nếu cần và được phép.

### 13.2. Config fingerprint

Canonicalize safe snapshot rồi hash để so sánh deployment. Không hash secret values hoặc dữ liệu có entropy thấp. Fingerprint không thể thay thế snapshot và không chứng minh cấu hình đã được áp dụng nếu không ghi effective state.

### 13.3. Config drift

Nếu desired logging policy là metadata-only nhưng effective configuration bật wire logging, phát configuration drift event và alert. Không chờ tới khi phát hiện prompt trong log.

## 14. Chẩn đoán tạm thời có kiểm soát

Đôi khi cần tăng logging để xử lý incident. Việc này cần quy trình rõ ràng.

Một diagnostic change nên có:

- Component/logger cụ thể.
- Environment và instance/tenant scope.
- Mục đích và incident/ticket reference.
- Log level mới.
- Danh sách field được phép xuất.
- Thời gian bắt đầu và expiry.
- Người yêu cầu/phê duyệt.
- Rollback value.
- Xác nhận content capture vẫn OFF.
- Kiểm tra output sau khi thay đổi.

### 14.1. Ví dụ change record

~~~json
{
  "changeId": "diag-2026-0518-17",
  "environment": "staging",
  "component": "com.example.ai.retrieval",
  "previousLevel": "INFO",
  "temporaryLevel": "DEBUG",
  "purpose": "Investigate retrieval filter regression",
  "incidentRef": "INC-2041",
  "allowedFields": [
    "corpus.version",
    "top_k",
    "result.count",
    "duration.ms",
    "error.code"
  ],
  "contentCapture": "DISABLED",
  "expiresAt": "2026-05-18T11:00:00Z",
  "rollbackLevel": "INFO"
}
~~~

### 14.2. Tăng level không đồng nghĩa mở content

Diagnostic logger phải chỉ ghi metadata. Nếu code hiện tại ghi raw prompt ở DEBUG, không bật logger đó. Trước khi tăng level, kiểm tra logger category và message templates.

### 14.3. Tự động rollback

Dynamic logging control nên có expiry hoặc automation quay về level trước. Nếu thay đổi được áp dụng bằng redeploy, change record cần nêu rõ release/rollback plan. Không để DEBUG tồn tại vô thời hạn.

### 14.4. Content capture là quy trình khác

Nếu điều tra cần raw prompt/response, tạo evidence capture request có purpose, approval, tenant scope, redaction, expiry và access audit. Không thay đổi Logback level để thực hiện capture.

## 15. Cấu hình động và refresh

Một số hệ thống hỗ trợ thay đổi log level khi runtime thông qua logging management endpoint hoặc control plane. Cần kiểm soát quyền và ghi audit.

### 15.1. Actuator loggers endpoint

Spring Boot Actuator có thể cung cấp endpoint để xem/thay đổi logger levels khi endpoint được expose và bảo vệ đúng cách. Endpoint này có thể hữu ích cho diagnostics nhưng là quyền quản trị nhạy cảm.

- Không expose công khai.
- Bảo vệ bằng authentication/authorization và network policy.
- Chỉ cho phép role vận hành được phê duyệt.
- Ghi audit event cho mỗi thay đổi.
- Giới hạn component allowlist.
- Áp dụng expiry/rollback.
- Không cung cấp endpoint để bật raw content capture.

### 15.2. Không để logger endpoint thay đổi root logger tùy tiện

Một thao tác đặt root=DEBUG có thể làm tăng log volume trên toàn service và thư viện. Chỉ cho phép logger categories đã đăng ký và mức log được phép.

### 15.3. Dynamic refresh cần quan sát được

Ghi requested level, effective level, actor/service, scope, change ID, timestamp, expiry và kết quả. Kiểm tra tất cả replicas có nhận thay đổi hay chỉ một instance.

## 16. Structured logging và appender routing

Sau khi chọn field, cần đảm bảo log được serialize và route đúng sink.

### 16.1. JSON output

Dùng JSON encoder phù hợp để key-value pairs thành field. Không giả định pattern encoder tự tạo structured JSON. Kiểm tra output thực tế có timestamp, level, logger, event name, correlation IDs và numeric types đúng.

### 16.2. Tách appender theo mục đích

Có thể route operational logs và security/audit logs tới sink khác nhau. Nhưng không tạo appender raw-content chỉ để debug. Nếu content evidence được capture, gửi thẳng tới evidence store với encryption/ACL; logger chỉ ghi reference.

### 16.3. Additivity và duplicate events

Logger con có thể propagate event lên root. Khi gắn nhiều appender, có thể tạo duplicate records. Kiểm tra additivity, routing rules và collector behavior.

### 16.4. Collector redaction là lớp phòng thủ phụ

Redaction ở collector có thể giúp giảm rủi ro, nhưng dữ liệu đã rời ứng dụng và có thể được copy trước khi xử lý. Redaction phải diễn ra ở source boundary; collector filtering không thay thế allowlist.

## 17. Kiểm thử logging configuration

Không chỉ review file YAML/XML. Cần kiểm tra effective logger levels, observation attributes và log output thực tế.

### 17.1. Test profile matrix

Chạy application context theo từng profile và assert:

- Root level.
- Logger levels của từng component.
- Observation prompt/completion capture flags.
- HTTP wire logging state.
- Content capture policy default.
- Effective configuration snapshot.
- Không có secret trong startup config event.

### 17.2. Test raw content sentinel

Tạo prompt fixture chứa một chuỗi sentinel duy nhất, ví dụ:

~~~text
RAW_PROMPT_SENTINEL_9F7C2
RAW_RESPONSE_SENTINEL_4A1D8
RAW_SECRET_SENTINEL_6B3E0
~~~

Chạy pipeline test qua logger, SDK stub, HTTP mock, observations và exporter. Quét tất cả captured logs/spans để bảo đảm các sentinel không xuất hiện. Với test capture được phép, chỉ evidence store mới được chứa sentinel theo policy.

### 17.3. Test configuration precedence

Thiết lập application.yml, profile file và environment override có giá trị khác nhau. Xác nhận effective configuration đúng theo precedence đã dự kiến. Kiểm production guard từ effective values.

### 17.4. Test dynamic logger change

Nếu dùng Actuator/control plane, kiểm tra authentication, authorization, allowlisted logger names, expiry và rollback. Xác nhận một operator không thể bật root DEBUG hoặc content capture ngoài scope.

## 18. Java: kiểm tra policy trước khi ghi content

Ví dụ policy gate đơn giản minh họa rằng log level không tham gia quyết định capture.

~~~java
public enum ContentLogMode {
    METADATA_ONLY,
    REDACTED_EVIDENCE_ONLY,
    DENIED
}

public record ComponentLoggingPolicy(
        String component,
        String environment,
        ContentLogMode contentMode,
        String policyVersion) {}

public final class ContentLoggingGuard {

    public boolean mayPersistContent(
            ComponentLoggingPolicy policy,
            boolean authorizedPurpose,
            boolean tenantAllowed,
            boolean withinExpiry) {

        if (policy == null) return false;
        if (!authorizedPurpose || !tenantAllowed || !withinExpiry) {
            return false;
        }

        return policy.contentMode()
                == ContentLogMode.REDACTED_EVIDENCE_ONLY;
    }
}
~~~

Đây là ví dụ policy gate, không phải logger. Trong production, ALLOW phải dẫn tới evidence service có redactor/store/ACL; không được dùng kết quả boolean này để gọi logger với raw content.

### 18.1. Policy theo component

Mỗi component có policy riêng. Prompt assembly có thể không được capture; evaluator có thể được phép lưu redacted answer trong một evaluation suite; tool backend có thể chỉ lưu operation reference. Không dùng một boolean toàn cục cho tất cả.

### 18.2. Policy theo environment

Production policy có thể cấm raw content tuyệt đối. Local policy chỉ cho phép synthetic fixture. Staging policy có thể cho phép redacted test data. Policy engine cần kiểm cả component, environment, tenant và purpose.

## 19. JUnit: kiểm policy và cấu hình an toàn

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ContentLoggingGuardTest {

    private final ContentLoggingGuard guard =
            new ContentLoggingGuard();

    @Test
    void metadataOnlyNeverAllowsContentPersistence() {
        var policy = new ComponentLoggingPolicy(
                "prompt", "prod",
                ContentLogMode.METADATA_ONLY, "v3");

        assertFalse(guard.mayPersistContent(
                policy, true, true, true));
    }

    @Test
    void redactedEvidenceRequiresAllPolicyConditions() {
        var policy = new ComponentLoggingPolicy(
                "evaluator", "staging",
                ContentLogMode.REDACTED_EVIDENCE_ONLY, "v3");

        assertTrue(guard.mayPersistContent(
                policy, true, true, true));
        assertFalse(guard.mayPersistContent(
                policy, false, true, true));
        assertFalse(guard.mayPersistContent(
                policy, true, false, true));
        assertFalse(guard.mayPersistContent(
                policy, true, true, false));
    }

    @Test
    void deniedPolicyAlwaysRejectsContent() {
        var policy = new ComponentLoggingPolicy(
                "model", "prod",
                ContentLogMode.DENIED, "v3");

        assertFalse(guard.mayPersistContent(
                policy, true, true, true));
    }

    @Test
    void missingPolicyFailsClosed() {
        assertFalse(guard.mayPersistContent(
                null, true, true, true));
    }
}
~~~

Test trên kiểm logic policy tối thiểu. Integration test cần xác minh evidence store chỉ nhận content sau redaction, logger không nhận raw payload và property binding thực sự đưa đúng profile values vào application context.

## 20. Quy trình xử lý khi cấu hình ghi content sai

Nếu phát hiện raw prompt/response xuất hiện trong log:

1. Xác định component/logger/appender/SDK/HTTP client phát nội dung.
2. Tắt nguồn capture hoặc wire logging ngay theo incident procedure.
3. Giữ lại metadata cần cho điều tra nhưng giới hạn quyền đọc các index liên quan.
4. Xác định environment, tenant, thời gian, replicas và sink bị ảnh hưởng.
5. Kiểm tra log collector, search index, archive, export và backup.
6. Phân loại prompt/response/context/tool data đã lộ.
7. Rotate/revoke secret nếu có khả năng bị ghi.
8. Thực hiện deletion/retention hold theo security/privacy policy.
9. Sửa cấu hình ở source boundary và kiểm tra effective configuration.
10. Chạy sentinel tests qua toàn bộ pipeline.
11. Ghi incident closure, root cause và guardrail mới.

Không xóa dữ liệu tùy tiện nếu có yêu cầu bảo toàn evidence của incident. Thực hiện containment và deletion theo policy của tổ chức.

## 21. Điều tra một regression bằng component-specific logs

Giả sử factual correctness giảm sau khi cập nhật prompt.

- Run summary cho biết dataset/rubric và số verdict FAIL.
- Prompt metadata cho biết template version/digest và token estimate.
- Retrieval metadata cho biết corpus, top-k, selected count và latency.
- Model metadata cho biết provider/model, usage, finish reason và duration.
- Tool metadata cho biết schema, authorization và execution status.
- Evaluator metadata cho biết judge/rubric version và verdict.
- Trace spans giúp tìm stage gây latency.
- Evidence store cung cấp actual prompt/context/answer nếu policy cho phép.

Không cần bật raw logging cho mọi component. Hãy xác định câu hỏi chưa trả lời, bật metadata diagnostics ở đúng component và dùng evidence access riêng nếu nội dung thực tế là bắt buộc.

### 21.1. Ví dụ

| Component | Baseline | Candidate | Cách điều tra |
| --- | --- | --- | --- |
| Prompt | v6, 1.500 token | v7, 1.620 token | So template/digest và evidence nếu được phép |
| Retrieval | 5 results, 3 selected | 5 results, 1 selected | Kiểm filter/reranker metadata |
| Model | 790 ms | 820 ms | So provider/model/usage |
| Tool | Không gọi | Không gọi | Không liên quan case |
| Evaluator | PASS | FAIL | So rubric/judge và reference evidence |

Bảng chỉ định hướng. Không kết luận prompt là nguyên nhân chỉ vì version thay đổi trước regression.

## 22. Anti-pattern thường gặp

**Root logger DEBUG ở production.** Mở rộng log volume và các thư viện cùng lúc.

**Một cờ debug bật cả prompt, response và HTTP wire logs.** Trộn diagnostic verbosity với content authorization.

**Chỉ cấu hình application logger.** SDK và HTTP client vẫn có thể ghi body/headers.

**Cho rằng Spring profile là quyền truy cập.** Profile chỉ chọn cấu hình, không thay thế authorization.

**Đặt include-prompt true trong file mặc định rồi override ở prod.** Một profile bị thiếu có thể bật content ngoài dự kiến.

**Chỉ kiểm tra YAML/XML.** Effective config có thể bị environment/config server override.

**Bật wiretap để điều tra model call.** Có thể ghi prompt và completion body.

**Tạo appender riêng cho raw content.** Sink riêng vẫn cần ACL/retention và không thay evidence service.

**Không đặt expiry cho DEBUG.** Diagnostic setting có thể tồn tại lâu sau incident.

**Chỉ kiểm logger của ChatModel.** Retrieval, tool, evaluator và exception cũng có thể chứa content.

**Dùng collector redaction làm lớp bảo vệ duy nhất.** Dữ liệu đã rời source trước khi được redact.

**Không test observation exporter.** Prompt/completion có thể nằm trong span attributes dù log sạch.

**Không có startup guard.** Production có thể khởi động với cấu hình capture không hợp lệ.

## 23. Bài thực hành: cấu hình logging theo component và environment

**Bối cảnh:** một chatbot Spring AI dùng RAG, model provider và tool getOrderStatus. Nhóm cần metadata logs cho toàn pipeline, chỉ capture evidence cho test case được phép và ngăn raw prompt/response xuất hiện trong production logs.

### Phần A — Lập component inventory

Liệt kê API, prompt assembly, retrieval, ChatModel, provider SDK, HTTP client, tool, evaluator, evidence service và tracing exporter. Ghi logger category, payload sensitivity, metadata fields và owner.

**Đầu ra:** component logging matrix.

### Phần B — Xây profile matrix

Tạo application.yml và các profile local/test/staging/prod. Đặt root level hợp lý, logger levels theo component, Spring AI observation content flags và HTTP wire logging OFF.

**Đầu ra:** profile configuration files và effective config snapshot.

### Phần C — Cấu hình Logback

Tạo logback-spring.xml với springProfile, appender JSON và logger categories cụ thể. Kiểm additivity và tránh duplicate events. Không tạo logger in raw prompt/response.

**Đầu ra:** structured logs theo profile.

### Phần D — Kiểm provider/HTTP instrumentation

Kiểm SDK logger categories, Reactor Netty wiretap hoặc HTTP client interceptors. Đảm bảo request/response body và sensitive headers không xuất hiện. Dùng mock provider và synthetic payload.

**Đầu ra:** instrumentation inventory và test output.

### Phần E — Diagnostic change có thời hạn

Tạo change record để tăng DEBUG cho retrieval metadata trong staging trong 30 phút. Ghi purpose, incident ref, allowed fields, expiry và rollback. Xác nhận content capture vẫn DISABLED.

**Đầu ra:** diagnostic change/audit record và rollback test.

### Phần F — Sentinel integration tests

Chạy prompt/response fixture chứa unique sentinel qua ChatClient, retrieval, tool, evaluator, logger và observation exporter. Quét logs/spans; chỉ evidence store được chứa content khi policy cho phép.

**Đầu ra:** test report và security guardrail.

### Checklist nghiệm thu

- [ ] Có component inventory và data classification.
- [ ] Log level tách khỏi content capture policy.
- [ ] Root logger không bật DEBUG rộng.
- [ ] Mỗi component có logger category và mức log phù hợp.
- [ ] Local dùng synthetic data.
- [ ] CI dùng fake/stub provider hoặc fixture.
- [ ] Staging/production mặc định metadata-only.
- [ ] Spring AI observation prompt/completion capture OFF theo đúng version.
- [ ] SDK debug logging được kiểm soát.
- [ ] HTTP wire body/header logging OFF.
- [ ] Retrieval/tool/evaluator không log raw payload.
- [ ] logback-spring.xml dùng profile đúng.
- [ ] Appender/additivity không tạo duplicate hoặc leak sink.
- [ ] Effective configuration được snapshot và kiểm tra.
- [ ] Production guard chặn content capture ngoài policy.
- [ ] Diagnostic changes có scope, approval, expiry và rollback.
- [ ] Actuator logger control được bảo vệ.
- [ ] Sentinel tests kiểm logs, SDK output và spans.
- [ ] Evidence capture dùng secure store riêng.
- [ ] Incident runbook có containment và deletion workflow.

### Câu hỏi tự kiểm tra

1. Vì sao logging policy phải phân chia theo component và environment?
2. Log level khác content capture policy như thế nào?
3. Vì sao không nên bật root DEBUG trong production?
4. Prompt assembly cần metadata nào để điều tra mà không ghi prompt body?
5. Retrieval query và chunks có phải content không?
6. Provider SDK có thể ghi những dữ liệu gì?
7. HTTP wire logging khác application logging ở đâu?
8. Spring AI observation content flags cần được kiểm tra theo phiên bản thế nào?
9. Vì sao profile local không tự cho phép ghi dữ liệu production?
10. Effective configuration khác file YAML như thế nào?
11. Vì sao không dump toàn bộ Spring Environment?
12. Khi nào nên dùng logback-spring.xml?
13. Logger additivity có thể tạo rủi ro gì?
14. Một diagnostic change cần những trường nào?
15. Vì sao DEBUG cần expiry và rollback?
16. Actuator loggers endpoint cần bảo vệ ra sao?
17. Vì sao collector redaction không đủ?
18. Sentinel integration test nên quét những output nào?
19. Khi raw prompt lọt vào log, cần containment bước nào?
20. Làm sao điều tra regression mà không bật raw logging toàn pipeline?

## 24. Tổng kết

Logging policy cho ứng dụng Spring AI cần được thiết kế theo cả component và environment. Prompt assembly, retrieval, model, tool, evaluator, provider SDK, HTTP client và tracing exporter có thể tiếp xúc với những loại content khác nhau. Vì vậy, một mức log chung hoặc một cờ DEBUG toàn cục không đủ để kiểm soát dữ liệu.

Hãy đặt metadata-only làm baseline cho mọi môi trường có dữ liệu thật. Dùng Spring profiles và logger categories để tăng diagnostic detail đúng component; kiểm soát Spring AI observations, SDK logging và HTTP wiretap riêng; xác minh effective configuration sau precedence. Raw prompt/response chỉ được capture qua evidence service có purpose, authorization, redaction, encryption, access audit và retention. Không bật content bằng cách đổi log level.

Mọi diagnostic change cần scope, owner, incident reference, expiry và rollback. Kiểm thử bằng synthetic sentinels xuyên suốt application logs, SDK, HTTP client và exported spans. Khi cấu hình ghi content sai, containment phải bắt đầu ở source, đồng thời kiểm tra các sink và bản sao downstream. Cách làm này giữ khả năng điều tra quality, latency và cost mà vẫn giới hạn nội dung nhạy cảm ở đúng nơi được phép.

### Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — Actuator Loggers](https://docs.spring.io/spring-boot/reference/actuator/loggers.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/specs/otel/logs/)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
