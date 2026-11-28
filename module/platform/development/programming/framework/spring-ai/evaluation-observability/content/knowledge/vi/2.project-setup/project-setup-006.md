# Bổ sung Actuator, Micrometer và thành phần tracing phù hợp

> **Chương:** Thiết lập dự án
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI theo relevance, fact checking, RAG và tool calling; đồng thời đo metrics, traces, token usage, chi phí và độ trễ để nhận diện nguyên nhân suy giảm chất lượng qua từng phiên bản prompt, model, pipeline.
>
> **Bộ phiên bản tham chiếu:** Java 21, Spring Boot 4.2.0, Spring AI 2.1.0 (thời điểm biên soạn: 27/11/2026). Những lựa chọn về starter và thuộc tính export trong bài áp dụng cho **dòng Spring Boot 4.2**; khi dùng Boot 3.x/AI 1.x cần kiểm tra hướng dẫn của đúng dòng phát hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Spring Boot Actuator**, **Micrometer Metrics**, **Micrometer Observation**, **Micrometer Tracing**, **OpenTelemetry** và backend lưu trữ/hiển thị telemetry.
2. Thêm đúng dependency để xuất **health/metrics/Prometheus** và **traces OTLP** trong ứng dụng Spring AI.
3. Bật cấu hình quan sát an toàn, lựa chọn sampling và kiểm tra được dữ liệu đã tới backend.
4. Theo dõi các bước **ChatClient → advisor/retriever → ChatModel → tool → evaluator**, bao gồm độ trễ và token usage khi provider có trả.
5. Tự tạo observation/metric ở tầng evaluation để phân biệt `PASS`, `FAIL`, `EVALUATION_ERROR` và độ trễ từng giai đoạn.
6. Phân tích kết quả bằng Metrics API/PromQL/trace, tránh suy luận rằng ứng dụng trả HTTP 200 tức là câu trả lời AI đúng.

### Một sự cố minh họa

Trợ lý tài liệu hoạt động tốt ở bản A; sau khi đổi prompt và tăng top-k từ 5 lên 15 ở bản B, nhóm thấy **p95 chậm hơn** và **fact checking giảm**. Chỉ xem log cuối cùng sẽ khó biết lỗi do truy xuất chậm, context quá dài, model sinh thêm nội dung, tool retry hay mô hình đánh giá không ổn định.

Với Actuator + Micrometer + tracing, ta đo được **vận hành xảy ra ở đâu và mất bao lâu**. Với dataset và evaluator, ta đo được **câu trả lời có còn đúng tiêu chí hay không**. Hai nhóm tín hiệu bổ sung cho nhau, cùng được gắn với phiên bản prompt/model/pipeline.

## 2. Quan hệ giữa Actuator, Micrometer và tracing

| Thành phần | Chức năng trong Spring Boot/Spring AI | Đầu ra điển hình |
|---|---|---|
| **Spring Boot Actuator** | Tạo endpoint health, info, metrics, Prometheus và auto-configure nhiều thành phần quản trị | `/actuator/health`, `/actuator/metrics`, `/actuator/prometheus` |
| **Micrometer Metrics** | API `MeterRegistry`, `Timer`, `Counter`, `Gauge`, `DistributionSummary`; adapter cho monitoring systems | Số request, số lỗi, token counter, duration |
| **Micrometer Observation** | Một abstraction ghi nhận operation với low/high cardinality keys; có thể chuyển thành metrics và tracing | `ObservationRegistry`, observations của ChatClient/ChatModel/tool |
| **Micrometer Tracing** | Abstraction cho traces/spans, span context, sampling và propagation | Trace ID, span ID, quan hệ cha/con |
| **OpenTelemetry SDK/exporter** | Implementation của tracing và xuất span theo giao thức OTLP | OTLP/HTTP gửi đến collector/backend |
| **Prometheus** | Định kỳ **scrape metrics** từ app, lưu time series và cung cấp truy vấn | Time series, PromQL, cảnh báo |
| **Collector + Jaeger/Tempo/OTel backend** | Nhận, xử lý, lưu hoặc chuyển spans; giao diện phân tích traces tùy sản phẩm | Một trace gồm nhiều spans theo cùng request |
| **Evaluation runner** do ứng dụng viết | Chạy dataset, so expected/actual, gọi relevance/fact checking evaluator | PASS/FAIL/ERROR, retrieval recall, quality report |

**Observation** là điểm nối: khi có registry và handlers thích hợp, một observation hoàn tất có thể sinh metric duration; khi có tracer thích hợp, nó cũng có thể tạo span. **Actuator tự nó không phải một hệ thống lưu trữ traces**. Thêm OpenTelemetry starter cũng chưa đồng nghĩa có trace hiển thị nếu chưa có collector/backend, endpoint, sampling và request thực tế.

### Luồng tín hiệu

~~~mermaid
flowchart LR
  A["Spring AI / Evaluation Runner"] --> B["Micrometer ObservationRegistry"]
  B --> C["MeterRegistry"]
  B --> D["Micrometer Tracing"]
  C --> E["Actuator /actuator/prometheus"]
  E --> F["Prometheus / dashboards / alerts"]
  D --> G["OpenTelemetry OTLP exporter"]
  G --> H["OTel Collector / Tempo / Jaeger"]
  A --> I["Kết quả evaluation và run manifest"]
  I --> J["Báo cáo quality/regression"]
  F --> J
  H --> J
~~~

Kết quả `relevancePass` hay `factCheckPass` được **evaluation runner tự xác định** dựa trên rubric/dataset, không phải metric tự sinh khi chỉ thêm các starters.

## 3. Chọn bộ dependency tương thích

Ví dụ chính dùng **Spring Boot 4.2.0 + Spring AI 2.1.0 + Java 21**. Với dòng khác, tên starter và cấu hình exporter có thể khác.

| Dependency | Vì sao cần | Bỏ đi thì sao? |
|---|---|---|
| `spring-boot-starter-actuator` | Auto-configure health, metrics, ObservationRegistry và các actuator endpoints | Thiếu phần lớn hạ tầng quản trị/observability của Boot |
| `micrometer-registry-prometheus` | Expose định dạng metrics để Prometheus scrape | Không có Prometheus registry/endpoint theo cấu hình mẫu |
| `spring-boot-starter-opentelemetry` | Micrometer Tracing + OpenTelemetry + OTLP exporter trên Boot 4.2 | Có thể vẫn có metrics, nhưng không có đường OTLP tracing đã minh họa |
| `spring-ai-starter-model-openai` | Tạo model adapter để có AI calls cần quan sát | Không có OpenAI ChatModel auto-configured từ starter này |
| `spring-boot-starter-webmvc` | Tạo HTTP endpoint dùng trong smoke test | Không có REST handler Spring MVC cho ví dụ |
| `spring-boot-starter-test` | Test Spring/JUnit | Không có bộ test support Boot trong project ví dụ |

**Không thêm đồng thời nhiều bộ tracer một cách tùy tiện.** Spring Boot hỗ trợ hai hướng phổ biến: **OpenTelemetry + OTLP** qua `spring-boot-starter-opentelemetry`, hoặc **Brave + Zipkin** qua `spring-boot-starter-zipkin`. Bài này chọn **OpenTelemetry/OTLP** vì dễ nối với nhiều backend và collector; không cần gắn thêm Brave/Zipkin chỉ để có tracing.

### Ví dụ Maven đầy đủ

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>ai-observability-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>21</java.version>
        <spring-ai.version>2.1.0</spring-ai.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.ai</groupId>
                <artifactId>spring-ai-bom</artifactId>
                <version>${spring-ai.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-starter-model-openai</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-opentelemetry</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm cần hiểu:

1. **Spring Boot parent/BOM** quản lý phiên bản phần hạ tầng gồm Actuator, Micrometer và OpenTelemetry starter.
2. **Spring AI BOM** quản lý các module Spring AI, không tự thay phiên bản Boot hoặc JDK.
3. Không cần ghi `<version>` lên từng starter nếu phiên bản đã được quản lý.
4. Một starter Model chỉ tạo **khả năng gọi provider**; cần API key, model có quyền sử dụng và request thật để xuất metric về AI.
5. Các thư viện trên cho phép **nhìn thấy** request, không tự tạo dataset hay chấm relevance/factuality.

### Cấu hình Gradle tương đương

`build.gradle` dùng Gradle native platforms:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.2.0')
    implementation platform('org.springframework.ai:spring-ai-bom:2.1.0')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dự án Gradle có thể chọn plugin `io.spring.dependency-management` thay cho native platform, nhưng phải hiểu thứ tự import BOM và kiểm tra `dependencyInsight`. Sử dụng Gradle Wrapper phù hợp với dòng Boot; không pha API mẫu Boot 3/AI 1 với starter Boot 4/AI 2.

## 4. Thiết lập application.yml cho môi trường thực hành

Các property chính thức được Spring Boot và Spring AI tự đọc; riêng các trường `app.*` (nếu thêm ở phần sau) là cấu hình **do ứng dụng viết code để xử lý**.

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: ai-observability-lab
  ai:
    openai:
      api-key: ${OPENAI_API_KEY}
      chat:
        model: ${OPENAI_CHAT_MODEL:gpt-4o-mini}
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
      observations:
        log-prompt: false
        log-completion: false
    tools:
      observations:
        include-content: false
    vectorstore:
      observations:
        log-query-response: false

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0          # Lab có lưu lượng thấp; không áp dụng bừa vào production
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

**Giải thích từng khối:**

- `spring.application.name` giúp định danh dịch vụ trên dashboards/trace. Trong production nên tách bằng resource attributes hoặc tên service theo deployment cho phù hợp cách tổ chức telemetry.
- `spring.ai.openai.api-key` lấy từ environment/secrets manager. **Không** thay placeholder bằng khóa thật trong file được commit.
- `spring.ai.openai.chat.model` là dạng property của **Spring AI 2.1**; các hướng dẫn cũ dùng `spring.ai.openai.chat.options.model` thuộc dòng trước khi API properties được thay đổi. Trước khi nâng cấp phải đối chiếu release notes.
- Các cờ `log-prompt`, `log-completion`, `include-content` và `log-query-response` tắt việc chủ động xuất nội dung nhạy cảm của prompt/answer/tool/vector.
- `management.endpoints.web.exposure.include` chỉ phù hợp trong lab hoặc mạng giám sát được bảo vệ. Môi trường sản xuất nên hạn chế endpoints và kiểm soát truy cập/network.
- `management.tracing.sampling.probability: 1.0` giúp dễ quan sát **mọi trace trong lab**. Mặc định Boot lấy mẫu khoảng **10%**; sampling production phải cân bằng mục tiêu điều tra và chi phí.
- `management.opentelemetry.tracing.export.otlp.endpoint` là **URL trace-specific đầy đủ** cho OTLP/HTTP. Ví dụ `localhost:4318/v1/traces` chỉ hoạt động nếu collector đang chạy trên host nhìn thấy từ ứng dụng.

**Quan trọng về OTLP endpoint:**

| Cách cấu hình | Giá trị mẫu | Hành vi |
|---|---|---|
| Common endpoint `management.opentelemetry.otlp.endpoint` | `http://collector:4318` | Spring Boot thêm `/v1/traces` khi sử dụng làm fallback HTTP |
| Trace-specific `management.opentelemetry.tracing.export.otlp.endpoint` | `http://collector:4318/v1/traces` | Dùng nguyên URL; **không** tự nối path lần nữa |
| Environment `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://collector:4318` | Được map vào property chung nếu được bật; path theo signal |
| Environment `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://collector:4318/v1/traces` | Được map vào trace-specific; dùng nguyên URL |

Chọn **một quy ước endpoint rõ ràng** và kiểm tra khi triển khai trên Docker/Kubernetes: `localhost` trong container trỏ về **chính container đó**, không trỏ về collector ở container khác.

### Cấu hình theo môi trường

Ở staging và production, tách endpoint, project/provider credential và collector tenant. Ví dụ cấu hình rút gọn:

~~~yaml
# application-prod.yml - chỉ là mẫu tham khảo
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${PROD_TRACES_ENDPOINT}
spring:
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
~~~

Trong production, vẫn có thể scrape Prometheus qua management port/private ingress được kiểm soát, nhưng không cần mở công khai `/actuator/prometheus` trên API phục vụ người dùng. Bảo vệ metrics cũng quan trọng vì nhãn và số liệu có thể tiết lộ sơ đồ hệ thống, model đang dùng, lỗi hoặc tải vận hành.

## 5. Tạo một lời gọi AI để phát sinh metrics và traces

Chỉ thêm dependencies và khởi động Spring Boot sẽ tạo một số JVM/HTTP metrics, nhưng **chưa phát sinh metric ChatModel/tool/vector** nếu code chưa đi qua những component này.

Ví dụ Spring MVC tối thiểu:

~~~java
package com.example.observabilitylab;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AiObservabilityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(AiObservabilityLabApplication.class, args);
    }
}

record QuestionRequest(String question) {}
record AnswerResponse(String answer) {}

@RestController
@RequestMapping("/api")
class AskController {
    private final ChatClient chatClient;

    AskController(ChatClient.Builder builder) {
        this.chatClient = builder.build();
    }

    @PostMapping("/ask")
    AnswerResponse ask(@RequestBody QuestionRequest request) {
        if (request == null || request.question() == null ||
                request.question().isBlank()) {
            throw new IllegalArgumentException("Câu hỏi không được để trống");
        }

        String answer = chatClient.prompt()
                .user(request.question())
                .call()
                .content();
        return new AnswerResponse(answer);
    }
}
~~~

Đoạn minh họa giả định có **một ChatModel thích hợp**, provider đã cấu hình và network/API key hợp lệ. Với nhiều ChatModel beans, cần chọn rõ model và builder phù hợp trước khi inject.

**Dùng `ChatClient.Builder` do Spring Boot/Spring AI auto-configure** giúp giữ các customizers và observation configuration. Việc tự gọi `ChatClient.builder(model)` bằng một builder hoàn toàn mới có thể bỏ qua các `ChatClientBuilderCustomizer` và một phần observability đã cấu hình.

Ở môi trường thật cần thêm input validation, timeout, error handler và giới hạn kích thước request. Mã ví dụ ưu tiên minh họa trace từ một lời gọi mô hình; chưa phải hệ thống RAG hay chấm điểm.

### Smoke test bằng lệnh

~~~bash
java -version
./mvnw -version
./mvnw clean verify
./mvnw spring-boot:run
~~~

Trong terminal thứ hai:

~~~bash
curl http://localhost:8080/actuator/health

curl -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hãy giải thích RAG trong một câu."}'

curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

Trên Windows có thể dùng `mvnw.cmd` và `Invoke-RestMethod` hoặc `curl.exe` thay các lệnh Unix. Nếu `/api/ask` báo **401/403 từ provider**, hãy phân biệt lỗi credential/quota với lỗi metrics/tracing. Nếu trả 200 nhưng không có dấu vết trên trace backend, kiểm tra exporter/collector/sampling trước khi quy về Spring AI.

## 6. Metrics nào Spring AI phát ra?

Spring AI 2.1 dùng Micrometer để ghi nhận một số operation. Quan hệ tên **observation/metric logic** và tên **time series Prometheus** cần được hiểu đúng:

| Thành phần | Observation hoặc metric logic | Dữ liệu hữu ích |
|---|---|---|
| ChatClient | `spring.ai.chat.client` | Duration toàn bộ `call()`/`stream()`, có thể gồm advisor overhead |
| Advisor | `spring.ai.advisor` | Thời gian/đường đi của advisors khi thực sự chạy |
| ChatModel và EmbeddingModel được hỗ trợ | `gen_ai.client.operation` | Độ trễ gọi model; provider, operation và model labels |
| Token usage | `gen_ai.client.token.usage` | Số input/output/total tokens khi provider trả usage |
| Tool calling | `spring.ai.tool` | Tên tool, execution duration, kết quả/lỗi |
| VectorStore | `db.vector.client.operation` | `query/add/upsert/delete`, DB, duration |
| HTTP Server (Boot) | `http.server.requests` | HTTP response time, status, route và lỗi |
| Custom evaluation | `app.ai.evaluation.case` (tự đặt) | Thời gian chạy một case/rubric và loại outcome |

**Metric không xuất hiện nếu component tương ứng chưa chạy.** Một câu chat thuần có thể không tạo bất kỳ observation nào về VectorStore hoặc tool.

### Ví dụ tên Prometheus

~~~text
gen_ai_client_operation_seconds_count
gen_ai_client_operation_seconds_sum
gen_ai_client_token_usage_total
db_vector_client_operation_seconds_count
db_vector_client_operation_seconds_sum
gen_ai_chat_client_operation_seconds_count
~~~

Tên thực tế phụ thuộc tên meter, version và naming convention của exporter. `/actuator/metrics` dùng **tên logic** (chẳng hạn `gen_ai.client.operation`), còn `/actuator/prometheus` xuất tên được chuyển đổi sang dấu gạch dưới, hậu tố counter/timer và labels.

### Không cộng đôi token

Spring AI có metric logic `gen_ai.client.token.usage`, xuất thành counter `gen_ai_client_token_usage_total`. Series thường có nhãn `gen_ai_token_type` là `input`, `output` hoặc `total`.

Nếu tính token tổng, chọn:

- `input + output` **hoặc**
- chỉ `total`,

không cộng cả ba loại vì sẽ đếm hai lần cùng lượng token.

Với model/provider không cung cấp usage, **counter có thể không tăng**. Việc không có mẫu token không có nghĩa request dùng 0 token; cần ghi trạng thái `USAGE_MISSING` trong report hoặc tính ước lượng với nguồn xác định.

## 7. Từ Prometheus metrics sang latency, throughput và error

### Mean latency của model call

PromQL minh họa:

~~~promql
sum(rate(gen_ai_client_operation_seconds_sum[5m]))
/
sum(rate(gen_ai_client_operation_seconds_count[5m]))
~~~

Kết quả là độ trễ trung bình theo **giây**, không phải p95. Cần xác định filter theo `gen_ai_system`, `gen_ai_request_model` hoặc `gen_ai_operation_name` nếu có nhiều provider/mô hình trong cùng ứng dụng.

### Số lời gọi model trên giây

~~~promql
sum by (gen_ai_request_model) (
  rate(gen_ai_client_operation_seconds_count[5m])
)
~~~

Chỉ số này đo số **operation đã hoàn tất** trong cửa sổ thời gian, không phải request người dùng duy nhất. Một HTTP request có thể gọi model nhiều lần do tool loop, retry, generator và judge.

### Token input/output theo model

~~~promql
sum by (gen_ai_request_model, gen_ai_token_type) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_token_type!="total"
  }[5m])
) * 60
~~~

Đây là **token/phút** từ các series input/output, không nhân với giá tiền. Để tính chi phí, phải biết đơn giá của model, kiểu token/cache và khoảng thời gian.

### p95 cần histogram

Một **timer** thường xuất `_seconds_count`, `_seconds_sum` và `_seconds_max`. Chúng **chưa đủ** để tính p95 đúng cho cả cụm.

Trong `application.properties` của môi trường đo:

~~~properties
management.metrics.distribution.percentiles-histogram.gen_ai.client.operation=true
~~~

Sau khi bật histogram và có đủ mẫu, Prometheus có thêm series `_seconds_bucket` dùng cho truy vấn:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, gen_ai_request_model) (
    rate(gen_ai_client_operation_seconds_bucket[5m])
  )
)
~~~

Một số nơi chỉ cần percentile/timer riêng với SLO buckets; hãy xem Micrometer/Boot docs và số lượng buckets để kiểm soát **cardinality và chi phí lưu trữ**. Không suy p95 từ `max` hoặc trung bình; p95 trên vài request cũng không đủ tin cậy để kết luận hồi quy.

### Lỗi AI không tương đương lỗi HTTP

Một request trả HTTP 200 vẫn có thể:

- Trả lời sai fact checking.
- Gọi nhầm tool hoặc dùng tham số sai nhưng được bắt lỗi.
- Retrieving sai tài liệu rồi dựng câu trả lời trôi chảy.
- Judge timeout nhưng ứng dụng vẫn trả answer cho người dùng.

Vì thế, metrics HTTP/model/tool chỉ cho biết **vận hành**; **quality outcome** phải đến từ evaluation dataset, deterministic assertions và judge được hiệu chuẩn.

## 8. Tạo custom observation cho evaluation runner

Framework chưa biết một case đang chấm `relevance`, `fact_check`, `tool` hay `rag`, cũng không hiểu quy tắc PASS/FAIL của dự án. Ta bổ sung một observation ở tầng chạy evaluation.

Ví dụ dùng `ObservationRegistry` được Boot cấu hình:

~~~java
package com.example.observabilitylab;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class EvaluationObservation {

    private final ObservationRegistry registry;

    public EvaluationObservation(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T recordCase(String scenario, Supplier<T> operation) {
        String safeScenario = switch (scenario) {
            case "rag", "tool", "no_context" -> scenario;
            default -> "other";
        };

        return Observation.createNotStarted(
                "app.ai.evaluation.case", registry)
            .lowCardinalityKeyValue("scenario", safeScenario)
            .observe(operation::get);
    }
}
~~~

`recordCase(...)` tạo một observation bao quanh **công việc thực sự nằm trong Supplier**. Nếu Supplier chỉ gọi evaluator, metric sẽ đo **judge latency**, không đo toàn bộ pipeline. Muốn đo end-to-end phải bao cả retrieval, generation, judging và report write.

### Outcome của bài đánh giá là metric riêng

Với kết quả từ runner, dùng counter với số lượng nhãn giới hạn:

~~~java
package com.example.observabilitylab;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class EvaluationOutcomeMetrics {
    private final MeterRegistry registry;

    public EvaluationOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(String scenario, String outcome) {
        // Caller chỉ truyền các giá trị từ enum/allowlist;
        // không truyền câu hỏi, case ID hoặc thông báo lỗi tự do.
        Counter.builder("app.ai.evaluation.outcome")
            .tag("scenario", scenario)
            .tag("outcome", outcome)
            .register(registry)
            .increment();
    }
}
~~~

Ở tầng gọi, giới hạn `scenario` trong `rag/tool/no_context`; giới hạn `outcome` trong `pass/fail/evaluation_error/generation_error/skipped`. Nên chuyển `record(String, String)` thành enums hoặc validate tập giá trị trước khi gọi để tránh hàng triệu series mới.

Một case có thể có **nhiều trạng thái khác nhau**: retrieval PASS, fact checking FAIL và tool assertion NOT_APPLICABLE. Cần định nghĩa metric per-check/per-rubric hoặc kết quả cuối theo policy đã được version hóa, tránh gộp mù các nhóm lỗi.

### Vì sao low cardinality và high cardinality khác nhau?

| Thuộc tính | Metric label? | Trace attribute hoặc report? |
|---|---|---|
| `environment=staging` | Có | Có |
| `scenario=rag` | Có | Có |
| `role=generator/judge` | Có | Có |
| `outcome=pass/fail/error` | Có | Có |
| `gen_ai.request.model` | Có nếu tập model được kiểm soát | Có |
| `run_id`, `case_id` | **Không** | Chỉ lưu ở hệ thống được phép, có retention |
| User ID/order ID/request ID duy nhất | **Không** | Hạn chế tối đa; cân nhắc redaction/pseudonymization |
| Full prompt, raw document, tool arguments | **Không** | Mặc định không xuất; chỉ trong hệ thống bảo vệ theo chính sách |
| API key/password/token | **Không** | **Không bao giờ** ghi vào telemetry |

Micrometer dùng **low-cardinality key-values** trong metrics và traces; **high-cardinality** chỉ có trên traces. Việc một trường được gọi là high-cardinality **không có nghĩa được phép chứa dữ liệu nhạy cảm**.

## 9. Distributed tracing: quan sát đường đi của RAG và tool calling

**Trace** là tập các **span** có quan hệ cha/con hoặc liên kết, thường mang một trace ID. Mỗi span ghi tên operation, thời điểm bắt đầu, thời gian, status và các attributes an toàn.

Một luồng kỳ vọng của ứng dụng có RAG:

~~~text
HTTP POST /api/ask
└─ ChatClient call
   ├─ Advisor A
   │  └─ VectorStore query
   │     └─ EmbeddingModel call (nếu embed câu hỏi trong request)
   ├─ ChatModel call (generator)
   │  └─ Tool execution (nếu model thực sự yêu cầu)
   └─ ChatClient completion
~~~

Một evaluation job có thể bổ sung:

~~~text
Evaluation case (custom Observation)
├─ Retrieval / generator workflow
├─ Relevance judge (ChatModel call)
├─ Fact-check judge (ChatModel call)
└─ Report write
~~~

**Đây là sơ đồ logic**. Cây span thực tế phụ thuộc vào advisor, vị trí tạo observations, request đồng bộ/stream, context propagation và provider. Không giả định tất cả thao tác cùng nằm trong một parent span nếu các tác vụ async/queue chưa truyền trace context.

### Spring AI ghi nhận các bước nào?

- `spring.ai.chat.client`: khi gọi `ChatClient.call()` hoặc `stream()`.
- `spring.ai.advisor`: khi advisor thực sự được thực thi.
- `gen_ai.client.operation`: khi gọi ChatModel hoặc EmbeddingModel được hỗ trợ.
- `spring.ai.tool`: khi tool calling được thực thi trong lời gọi model.
- `db.vector.client.operation`: khi thực sự tương tác với VectorStore (query/add/upsert/delete).

Nếu câu hỏi được trả lời bằng LLM **không truy xuất RAG**, không thấy span vector là hành vi đúng. Nếu model quyết định không dùng tool, không thấy span tool cũng không phải lỗi exporter.

### Tracing xuyên qua service và HTTP client

Nếu tool service được gọi qua HTTP, sử dụng `RestClient.Builder` hoặc `WebClient.Builder` **được Spring Boot auto-configure** để nhận instrumentation/trace propagation. Tạo HTTP client thủ công từ một builder không được cấu hình có thể làm mất `traceparent` và khiến backend không ghép được spans giữa hai service.

Với ứng dụng dùng `@Async`, thread pool, Reactor, queue hoặc custom executor, cần kiểm tra propagation của observation/trace context qua ranh giới bất đồng bộ. Một số span rời rạc không đồng nghĩa mô hình AI tự chia thành các lần chạy khác nhau.

**Giới hạn cụ thể của Spring AI 2.1:** với một số đường streaming OpenAI sử dụng async SDK, HTTP span có thể **không còn là span con** của ChatModel do việc chuyển thread trong SDK; tài liệu chính thức lưu ý sự khác biệt này. Không dùng riêng cấu trúc cha/con của HTTP span để kết luận code của mình sai nếu đang gặp đúng tình huống này.

## 10. Quan sát traces qua Collector/Jaeger/Tempo

Traces đi theo tuyến:

`Spring Boot → OTLP exporter → Collector/Backend → UI tìm theo service/trace ID`.

Tối thiểu phải có:

1. App có `spring-boot-starter-opentelemetry`.
2. Endpoint OTLP/HTTP hoặc OTLP/gRPC phù hợp với collector và protocol cấu hình.
3. Collector/backend reachable, nhận đúng credentials và TLS nếu yêu cầu.
4. Sampling rate đủ để quan sát request kiểm thử.
5. Một request **đã thực sự chạy**.

### Collector tối thiểu cho local lab

Đoạn cấu hình OpenTelemetry Collector minh họa chỉ để **kiểm chứng local**. Debug exporter ghi thông tin spans vào logs collector; chỉ dùng dữ liệu tổng hợp/giả lập.

~~~yaml
# otel-collector-config.yml (tạo trong dự án lab riêng)
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

**Không dùng debug exporter để ghi toàn bộ prompt, answer hoặc source content trong production.** Để xem traces trên giao diện, thay/nối exporter tương ứng với Jaeger, Tempo hoặc nền tảng OpenTelemetry trong môi trường có phân quyền. Mỗi bản Collector có thể thay đổi cấu hình exporter; nên kiểm tra version và startup logs.

Trong Kubernetes, dùng service DNS của Collector thay cho `localhost`, ví dụ `http://otel-collector.monitoring.svc:4318/v1/traces` nếu hạ tầng nội bộ được thiết lập đúng; đây chỉ là **địa chỉ minh họa**, không phải một service đang tồn tại.

### Đọc một trace để tìm bottleneck

Giả sử ví dụ giả lập:

| Span | Duration | Gợi ý điều tra |
|---|---:|---|
| HTTP `/api/ask` | 3.8 s | User-facing latency |
| Vector query | 0.9 s | Index, DB connection, filter/top-k |
| ChatModel generator | 2.5 s | Input tokens, model, network/provider |
| Tool call | 0.2 s | External API hoặc retry nếu có |

Đây là các **số giả lập**. Không cộng tất cả durations để ra thời gian end-to-end nếu spans có quan hệ lồng nhau: thời gian của span cha **đã bao gồm** thời gian các span con. Khi truy tìm nguyên nhân, xem **critical path**, parent-child relationship và mức độ trùng lặp thời gian.

## 11. Sampling, volume và độ tin cậy của số liệu

Spring Boot mặc định lấy mẫu một phần request (khoảng 10%) cho tracing. Trong lab:

~~~properties
management.tracing.sampling.probability=1.0
~~~

Trong môi trường nhiều traffic:

~~~properties
management.tracing.sampling.probability=0.10
~~~

Một số hệ thống dùng **head-based sampling** nên có những trace lỗi bị bỏ qua. Nếu muốn quan sát lỗi hiếm hoặc slow requests, cân nhắc chính sách sampling ở SDK/collector/backend, có thể tail sampling tùy hạ tầng; phải đo chi phí và tỷ lệ trace thất lạc.

Phân biệt:

- **Metrics:** thường tổng hợp mọi lời gọi đã instrument và được cập nhật theo meter, **không phụ thuộc việc trace được lấy mẫu**.
- **Traces:** chỉ một phần request được lưu nếu sampling thấp.
- **Logs:** phụ thuộc logging level và pipeline, không tự động dùng cùng chính sách sampling.
- **Evaluation data:** dataset/case reports có thể ghi đủ kết quả ngay cả khi chỉ giữ một phần traces.

**Không suy tỷ lệ lỗi/chất lượng tuyệt đối từ một tập traces bị sampling thiên lệch**. Tính tỷ lệ quality theo dataset hoặc số liệu tổng hợp có mẫu số, còn traces dùng để điều tra chi tiết từng đường thực thi.

### Histogram cũng có chi phí

Mỗi nhãn `model × scenario × environment × outcome` và mỗi histogram bucket tạo thêm time series. Đặt nhãn ít giá trị, bật histogram cho các timer quan trọng và giới hạn độ dài/tập giá trị model IDs. Việc xuất full request ID hoặc `case_id` lên Prometheus có thể khiến hệ thống giám sát tăng chi phí rất nhanh.

## 12. Phân biệt quality, latency và chi phí

Spring AI Evaluation & Observability cần ít nhất hai nhóm phép đo.

**Chất lượng theo dataset:**

- `answer_relevance_pass_rate`: tỷ lệ câu trả lời liên quan theo rubric.
- `fact_check_pass_rate`: tỷ lệ phát biểu được context hỗ trợ.
- `retrieval_recall@k`: tỷ lệ tài liệu liên quan tìm thấy trong top-k, nếu có ground truth IDs.
- `tool_argument_success_rate`: tỷ lệ gọi đúng tool và arguments.
- `evaluation_coverage`: tỷ lệ mẫu được chấm hợp lệ; tách `EVALUATION_ERROR`.

**Vận hành từ metrics và traces:**

- `p50/p95/p99` latency HTTP, retrieval, generator, judge và tool.
- Input/output tokens, retries, timeouts và 429/5xx.
- Concurrency, queue/wait time, số lần tool call.
- Chi phí ước tính theo provider/model, rate card và thời điểm.

| Tình huống | Quality | Observability | Cách diễn giải |
|---|---|---|---|
| Answer đúng nhưng p95 tăng | Đạt | Suy giảm | Điều tra bottleneck trước khi tối ưu prompt/index |
| Latency giảm nhưng fact check giảm | Suy giảm | Cải thiện | Không được đánh đổi độ đúng mà không có policy |
| Traces ổn nhưng relevance thấp | Suy giảm | Bình thường | Xem prompt, model, context, dataset/rubric |
| Nhiều `EVALUATION_ERROR` | Chưa đủ kết luận | Judge/quota/timeout có vấn đề | Sửa hạ tầng chấm trước khi kết luận generator giảm chất lượng |
| Token tăng cùng top-k | Chưa rõ | Chi phí tăng | So ảnh chụp context, chunking và mức độ cải thiện chất lượng |

### Chi phí không tự suy ra từ một metric token

Với giá theo **một triệu token**:

\[
C_{\text{model call}}
= \frac{T_{\text{input}}}{10^6}P_{\text{input}}
+ \frac{T_{\text{output}}}{10^6}P_{\text{output}}
\]

Với một case có generator và hai judges:

\[
C_{\text{case}}
= C_{\text{generator}}
+ C_{\text{judge,relevance}}
+ C_{\text{judge,fact}}
+ C_{\text{embedding/retrieval/tools}}
\]

Giá cho cached tokens, reasoning tokens, batch mode hoặc provider thay đổi theo thời gian. Dữ liệu usage có thể thiếu hoặc phải tách categories. Cần giữ **model ID, bảng giá áp dụng, ngày, loại token, retries** và trường `usage_status` trong report; không tự điền chi phí 0 cho request không báo usage.

### Tránh tính đúp thời gian và token

- `ChatClient` duration có thể bao gồm advisor và ChatModel calls; đừng cộng thẳng duration cha/con.
- Generator, relevance judge và fact-check judge có thể là **ba model calls**; chi phí của judge nên tách khỏi user-facing generator cost.
- Khi có metric token với `input`, `output` và `total`, dùng một phương án đếm tổng để tránh gấp đôi.
- Chi phí tool/API/database thường tính theo cơ chế riêng, không nằm trong `gen_ai.client.token.usage`.

## 13. Điều tra hồi quy qua các phiên bản prompt/model/pipeline

Không thể so đúng nếu chỉ lưu biểu đồ latency mà không biết cấu hình nào đã chạy. Mỗi lần benchmark/evaluation nên có một **run manifest**:

~~~yaml
run_id: "eval-staging-2026-11-27-001"
environment: "staging"
git_commit: "example-commit"
java_version: "21"
spring_boot_version: "4.2.0"
spring_ai_version: "2.1.0"
generator_model: "generator-model-id"
judge_model: "judge-model-id"
prompt_revision: "prompt-v3"
judge_rubric_revision: "rubric-v2"
dataset_revision: "qa-cases-v5"
corpus_revision: "documents-v7"
index_revision: "vector-index-v7"
retrieval:
  top_k: 5
observability:
  collector: "staging-collector"
  tracing_sampling_probability: 1.0
  metric_schema_revision: "metrics-v1"
~~~

Đây là **metadata giả lập**. Không lưu secrets, full prompts, private documents hoặc user identifiers trong manifest; giữ bản nội dung gốc ở kho có quyền phù hợp nếu thực sự cần tái hiện.

### Hai lần chạy so sánh

| Biến | Baseline A | Candidate B |
|---|---|---|
| Dataset / rubric | `qa-v5` / `rubric-v2` | Giữ nguyên |
| Model generator | Model X | Giữ nguyên |
| Retrieval top-k | 5 | 15 |
| Prompt revision | `prompt-v3` | Giữ nguyên |
| Observation/trace config | Sampling 100% trong lab | Giữ nguyên |
| Đo | Recall@k, factuality, tokens, p95 | Cùng cách đo |

Ở ví dụ này chỉ thay top-k. Nếu retrieval latency tăng và input tokens tăng nhưng factuality không tăng, có cơ sở cân nhắc giảm top-k hoặc cải thiện reranking; vẫn cần đối chiếu số lượng mẫu và trace thực tế trước khi kết luận.

### Hướng điều tra theo dấu hiệu

| Dấu hiệu | Ưu tiên xem |
|---|---|
| `db.vector.client.operation` chậm | Database/index, filter/top-k, connection pooling, embedding |
| `gen_ai.client.operation` chậm, token input tăng | Prompt/context length, model, provider, rate limit |
| `spring.ai.tool` nhiều hoặc lỗi | Tool selection, arguments, downstream API, retry/timeout |
| Fact checking giảm nhưng metrics ổn | Evidence snapshot, answer, model, rubric, judge calibration |
| Tỷ lệ error chấm tăng | Judge endpoint, quota, timeout, output parsing |
| Missing traces, metrics vẫn đầy đủ | Sampling/collector/OTLP endpoint/context propagation |
| Thiếu token counter nhưng model trả lời | Provider usage semantics, streaming response, version instrumentation |

## 14. Cấu hình bảo vệ dữ liệu quan sát

Traces và logs có thể nhạy cảm như câu trả lời AI, nhất là ở ứng dụng RAG dùng tài liệu nội bộ. Mặc định Spring AI **không chủ động xuất toàn bộ** prompt/completion/tool arguments hoặc vector response; duy trì cấu hình tắt nếu không có mục đích và quyền rõ ràng.

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
    vectorstore:
      observations:
        log-query-response: false
~~~

Cần kiểm soát thêm:

1. **Secrets** (provider key, OTLP bearer, DB password) chỉ ở environment/secret manager; không log headers hay in tất cả Spring properties.
2. **Prompt injection** từ RAG/tool response có thể làm model sinh hoặc ghi nội dung trái policy; xử lý dữ liệu truy xuất như dữ liệu không đáng tin.
3. **Metric tags** có danh sách giá trị giới hạn; không thêm `case_id`, `user_id`, prompt hoặc raw document.
4. **Trace backend** có RBAC, mã hóa đường truyền, retention và tách tenant theo môi trường.
5. **Actuator endpoints** chỉ mở cho hạ tầng giám sát được phép; không expose `env`, `configprops`, `heapdump` rộng rãi.
6. **Judge data** chỉ gửi tài liệu/câu hỏi được phép đến provider đánh giá; không giả định mọi dữ liệu production đều được phép dùng cho offline evaluation.

**High cardinality chỉ là phân loại kỹ thuật.** Một `highCardinalityKeyValue("userId", "...")` có thể không thành Prometheus label nhưng vẫn có thể tới tracing backend; muốn giữ riêng tư phải **không gửi** hoặc áp dụng chính sách redaction và kiểm soát truy cập thực tế.

## 15. Kiểm chứng theo từng tầng

Kiểm chứng có thứ tự giúp xác định chính xác lớp nào bị lỗi.

| Bước | Kiểm tra | Tiêu chí đạt |
|---|---|---|
| 1. Dependency | Maven dependency tree/Gradle dependencyInsight | Boot 4.2 + AI 2.1 đồng dòng, tracing/registry có trên runtime classpath |
| 2. Startup | Spring context và health | App khởi động; health có trạng thái phù hợp |
| 3. Metrics nền | `/actuator/metrics`, `/actuator/prometheus` | Có JVM/HTTP hoặc actuator metrics, Prometheus registry hoạt động |
| 4. Model call | `POST /api/ask` dùng provider test | Có ChatClient/ChatModel operations sau request |
| 5. Trace export | Collector logs/backend UI | Trace được nhận; trace ID và operation đúng |
| 6. RAG/tool | Một case có vector query/tool thực tế | Có span/metric tương ứng khi nhánh thực thi |
| 7. Evaluation | Runner chạy dataset có nhãn | Có PASS/FAIL/ERROR, thời gian, coverage, version |
| 8. Regression | Cố định dataset/rubric và đổi một tham số | Report liên kết quality với metrics/traces đúng run |

**Lưu ý:** worker của bước viết kiến thức này chỉ tạo Markdown/YAML theo hướng dẫn. Các lệnh kiểm thử trong bài là chỉ dẫn để người học chạy trên **dự án thực hành có dependency và provider** phù hợp; chưa phải kết quả build được thực thi tại đây.

### Smoke test với fake model và integration thật

Trong unit tests nên dùng fake/mock cho `ChatModel` và kiểm tra tự động logic evaluator, tool assertions, dataset loading. Một integration test riêng có quyền test provider nên thực hiện **một ít lời gọi thật**, xác nhận instrumentation và policy của environment. Không bắt mọi pull request gọi model tốn tiền chỉ để xem một meter.

## 16. Lỗi phổ biến khi bổ sung Actuator và tracing

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `/actuator/health` 404 | Chưa thêm Actuator, sai base path hoặc chưa enable web endpoint | Kiểm tra runtime dependencies và endpoint mapping |
| `/actuator/prometheus` 404 | Thiếu registry hoặc chưa expose `prometheus` | Thêm `micrometer-registry-prometheus`, kiểm tra `management.endpoints.web.exposure.include` |
| Metrics có nhưng không có traces | Thiếu tracing starter, sampling thấp hoặc OTLP không kết nối | Kiểm tra `spring-boot-starter-opentelemetry`, exporter endpoint và collector logs |
| OTLP exporter trả 404 | Trace-specific URL thiếu/sai `/v1/traces` hoặc sai giao thức | Phân biệt common vs trace-specific endpoint; kiểm tra HTTP/gRPC |
| App gọi model được nhưng không có token usage | Provider/streaming không trả usage | Xem model response metadata; không mặc định 0 token |
| Không có vector/tool span | Không đi qua VectorStore/tool instrumented | Gọi một ca RAG/tool thật, xác nhận nhánh được thực thi |
| Traces bị tách rời | Tự tạo HTTP client, async executor hoặc queue không propagate context | Dùng auto-configured builders và cơ chế context propagation |
| Prometheus không có `_bucket` | Chưa bật histogram cho timer | Cấu hình distribution histogram; gửi đủ request sau khi bật |
| p95 không ổn định | Quá ít mẫu, nhãn phân mảnh, nhiều cold starts | Dùng workload đủ mẫu, nhóm labels hợp lý và so cùng cửa sổ |
| Dashboard tăng cost nhưng quality không tăng | Top-k/context dài hơn hoặc retry tăng | So token input/output, model/corpus/index, run manifest |
| Mất quan sát sau nâng Spring AI | Tên observations/labels thay đổi hoặc API builder khác | Đọc release notes, kiểm tra metric thực và cập nhật dashboard |
| Trace chứa dữ liệu nhạy cảm | Đã bật prompt/tool/vector content export hoặc SDK logs riêng | Tắt nội dung, kiểm tra mọi export pipeline và retention |
| Metric series tăng cực lớn | Thêm case ID/user ID/prompt vào low cardinality keys | Chuẩn hóa enum labels, giới hạn model IDs và review meter tags |

### Cách phân biệt “không có metric” với “metric bằng 0”

Với Micrometer, nhiều meter chỉ được tạo **sau lần operation đầu tiên**. Nếu gọi `/actuator/metrics` trước mọi lời gọi AI, tên `gen_ai.client.operation` có thể chưa xuất hiện. Nếu provider không trả token usage, counter token cũng có thể không được ghi. Cần thực hiện một case đủ điều kiện rồi mới kiểm tra lần nữa.

## 17. Thực hành có hướng dẫn

### Bài A — Xác nhận hạ tầng quan sát

1. Thêm Actuator, Prometheus registry và Spring Boot OpenTelemetry starter theo Maven/Gradle.
2. Khởi động app bằng **test provider credentials**, cấu hình sampling 1.0 và local OTLP collector.
3. Gọi `/actuator/health`, `/actuator/metrics` và `/actuator/prometheus`.
4. Gửi một `POST /api/ask` hợp lệ; xác nhận có metric ChatModel và một trace được collector nhận.
5. Ngắt collector rồi gọi lại: nhận diện exporter warning và kiểm tra app có còn trả lời tùy policy (không coi xuất trace là điều kiện phải thành công của request).

**Kết quả cần ghi:** service name, JDK/Boot/AI versions, model ID, exporter URL **không chứa secret**, trace ID test, danh sách metric names quan sát được.

### Bài B — Tìm latency theo từng thành phần

Tạo một luồng RAG giả lập trên môi trường test:

1. Retriever trả về tài liệu tổng hợp có IDs.
2. Generator nhận đúng context.
3. Judge chấm relevance và fact checking bằng model test, hoặc mock nếu muốn test chỉ metrics.
4. Thêm custom observation cho mỗi case và metric outcome.
5. Kiểm tra span duration: retrieval, ChatModel generator và judge.

**Kết quả cần ghi:** số mẫu, p50/p95 (nếu đủ mẫu), input/output tokens nếu có, quality PASS/FAIL và `EVALUATION_ERROR` riêng. Không dùng time series metrics để lưu từng câu hỏi.

### Bài C — Bật histogram và viết một PromQL

1. Bật histogram cho `gen_ai.client.operation` ở môi trường lab.
2. Gửi đủ request để có phân phối latency không rỗng.
3. Kiểm tra Prometheus có `gen_ai_client_operation_seconds_bucket`.
4. Tính p95 bằng `histogram_quantile`, rồi so với `mean` tính từ sum/count.
5. Giải thích vì sao p95 và mean khác nhau khi có vài request chậm bất thường.

### Bài D — Phát hiện hồi quy giả lập

Giữ nguyên dataset, judge/rubric, model và prompt, tăng top-k từ 5 lên 15 trong staging:

- So quality (`retrieval_recall@k`, relevance, fact checking) và coverage.
- So `db.vector.client.operation`, `gen_ai.client.operation`, token input và p95.
- Đọc trace của ca chậm nhất; chỉ ra vị trí tăng thời gian có bằng chứng.
- Viết một đoạn giải thích thay đổi và giới hạn kết luận; nếu judge có sai số, cần human review hoặc chạy lặp lại.

**Mục tiêu:** chứng minh khả năng truy nguyên nguyên nhân theo **dữ liệu quality + observability** thay vì chỉ nói “AI chậm hơn”.

### Câu hỏi tự kiểm tra

1. Thêm `spring-boot-starter-actuator` đã đủ tạo và lưu distributed traces chưa? Vì sao?
2. Điều kiện nào khiến `/actuator/prometheus` xuất hiện?
3. Vì sao **spring.ai.chat.client** duration khác **gen_ai.client.operation** duration?
4. Nếu request chat không gọi tool, có nên xuất `spring.ai.tool` metric không?
5. Khi nào `gen_ai.client.token.usage` không có dữ liệu? Tại sao không nên ghi 0?
6. `_seconds_sum / _seconds_count` có phải p95 không?
7. Tại sao cần histogram buckets trước khi tính p95 bằng `histogram_quantile`?
8. `run_id`, `case_id` nên đặt ở đâu để liên kết report với tracing mà không tăng metric cardinality?
9. Vì sao hai môi trường dev và prod nên dùng OTLP tenant/retention riêng?
10. Một lần nâng judge làm pass rate giảm, nhưng generator/inputs không đổi. Cần điều tra gì?

**Gợi ý:** (1) cần tracing starter, SDK/exporter, collector, sampling; (2) Actuator, Prometheus registry và web exposure; (3) ChatClient có advisor overhead; (4) không nếu tool chưa thực thi; (5) provider không trả usage; (6) chỉ là mean; (7) percentile cần phân phối; (8) report store/trace attributes có quyền, không metric labels; (9) cách ly quyền và dữ liệu; (10) judge/rubric drift và calibration với human labels.

## 18. Checklist trước khi kết thúc bước thiết lập

- [ ] Đã chọn đúng bộ phiên bản Java, Spring Boot và Spring AI.
- [ ] Có `spring-boot-starter-actuator` và Prometheus registry nếu cần Prometheus.
- [ ] Có **một** bộ tracing phù hợp, ví dụ `spring-boot-starter-opentelemetry` cho OTLP.
- [ ] Cấu hình OTLP endpoint đúng signal/protocol/path; collector/backend thực sự hoạt động.
- [ ] Actuator endpoints được expose có chủ đích và bảo vệ theo môi trường.
- [ ] Đã kiểm tra `health`, `metrics`, `prometheus` sau ít nhất một request AI thật.
- [ ] Có metric ChatClient/ChatModel, token usage khi provider trả, VectorStore/tool khi nhánh chạy.
- [ ] Có trace end-to-end với context propagation phù hợp; hiểu trường hợp streaming/async.
- [ ] Sampling phù hợp, không dùng 100% trên production chỉ vì cần debug.
- [ ] Metric labels có cardinality thấp, không chứa dữ liệu cá nhân, secret hoặc raw prompts.
- [ ] Có observation riêng cho evaluation runner và trạng thái lỗi được phân biệt.
- [ ] Đã bật histogram nếu dashboard thực sự cần percentiles tổng hợp.
- [ ] Lưu manifest: dataset, rubric, prompt, model, index, framework, telemetry version.
- [ ] Báo cáo luôn trình bày quality **cùng** latency, token, cost và coverage.

## 19. Tài liệu tham khảo chính thức

1. [Spring Boot 4.2 — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health, exposure, điều kiện endpoint Prometheus và access controls.
2. [Spring Boot 4.2 — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registries, Prometheus, meter names và histogram distribution properties.
3. [Spring Boot 4.2 — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): OpenTelemetry/OTLP starter, Zipkin alternative, sampling và trace propagation.
4. [Spring Boot 4.2 — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): `ObservationRegistry`, resource attributes và common/signal-specific OTLP configuration.
5. [Spring AI 2.1 — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, Advisor, ChatModel, EmbeddingModel, tool, VectorStore, token metrics và quy định nội dung nhạy cảm.
6. [Spring AI 2.1 — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): Prometheus time series, token types và ví dụ PromQL.
7. [Spring AI 2.x — Upgrade Notes](https://docs.spring.io/spring-ai/reference/2.0/upgrade-notes.html): thay đổi cách đặt configuration properties và observability ở dòng 2.x.
8. [Micrometer — Observation Concepts](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): low/high cardinality, lifecycle của observation và handlers.
9. [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): nhận OTLP, processors và exporters.
10. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): tính percentile từ histogram và những giới hạn của mean/max.

> **Ghi nhớ:** **Actuator** mở giao diện quản trị, **Micrometer** thu metrics/observations, **tracing + OTLP** nối các bước xử lý thành traces. Để phát hiện suy giảm chất lượng Spring AI cần liên kết các tín hiệu vận hành đó với **dataset, relevance/fact checking, tool assertions và các phiên bản prompt/model/pipeline**; không có một bộ starter nào tự thay thế việc đánh giá câu trả lời.
