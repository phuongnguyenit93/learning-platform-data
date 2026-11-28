# Tạo ứng dụng mẫu có kết quả thành công, sai và lỗi kỹ thuật

> **Chương:** Thiết lập dự án
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — thực hành đánh giá chất lượng bằng dataset, relevance, fact checking và các luồng RAG/tool calling; kết hợp metrics, traces, token usage, chi phí và độ trễ để nhận diện hồi quy giữa các phiên bản prompt, model và pipeline.
> **Mốc công nghệ:** Java 21, Spring Boot 4.2.0, Spring AI 2.1.0. Ví dụ dùng dữ liệu tổng hợp, không có thông tin người dùng thật.

## 1. Mục tiêu của ứng dụng mẫu

Một hệ thống quan sát AI không thể kiểm tra đầy đủ chỉ với những request thành công. Ta cần tái hiện **ba kết quả khác bản chất**:

1. **Thành công và đúng:** pipeline hoàn tất, trả nội dung được bằng chứng hỗ trợ.
2. **Hoàn tất nhưng sai:** HTTP/model call thành công, vẫn có câu trả lời, nhưng câu trả lời vi phạm ground truth hoặc rubric.
3. **Lỗi kỹ thuật:** pipeline không thể hoàn tất vì timeout, lỗi provider, cấu hình, hạ tầng hoặc tool; chưa có đủ câu trả lời hợp lệ để chấm.

Sau bài học, bạn sẽ biết cách:

- Tạo một ứng dụng Spring Boot mẫu chạy offline, có ba endpoint/case có kết quả **xác định**.
- Phân biệt **execution outcome** với **quality outcome** trong model, API, metrics và báo cáo.
- Viết tests chứng minh response đúng/sai đều có thể mang HTTP **200**, còn lỗi upstream được trả **503** theo policy minh họa.
- Gắn Micrometer `Counter` và `Timer` để quan sát cả ba nhánh.
- Bổ sung `ChatClient` và Spring AI Evaluators cho lần chạy thật mà không phá cơ chế baseline offline.
- Mở rộng sang dataset có tình huống RAG, tool calling, thiếu context và lỗi judge.

**Vì sao chọn fixture offline làm điểm bắt đầu?** Một LLM được gọi thật có thể trả lời khác nhau giữa các lần chạy; timeout hoặc lỗi provider không thể bảo đảm xảy ra đúng lúc. Với fixture, ta chủ động tạo được ca đúng, sai, lỗi kỹ thuật để kiểm thử instrumentation và trạng thái **trước khi** đánh giá độ tin cậy của model thật.

## 2. Tách hai trục trạng thái: kỹ thuật và chất lượng

Lỗi phổ biến nhất là coi mọi HTTP 200 là câu trả lời đúng hoặc coi mọi kết quả `FAIL` của judge là lỗi HTTP.

| Tình huống | HTTP | Execution outcome | Quality outcome | Có nội dung để chấm? |
|---|---:|---|---|---|
| Câu trả lời đúng theo rubric | 200 | `COMPLETED` | `PASS` | Có |
| Câu trả lời sai fact checking | 200 | `COMPLETED` | `FAIL` | Có |
| Provider/LLM timeout | 503 (policy demo) | `TECHNICAL_ERROR` | `NOT_EVALUATED` | Không |
| Câu hỏi không hợp lệ | 400 | `INVALID_REQUEST` | `NOT_EVALUATED` | Không |
| Không tồn tại mã case | 404 | `INVALID_REQUEST` | `NOT_EVALUATED` | Không |
| Judge timeout sau khi generator đã trả lời | Có thể vẫn 200 trong API người dùng | `COMPLETED` của generator | `EVALUATION_ERROR` của bước chấm | Có, nhưng chưa chấm hợp lệ |

**HTTP 503 là lựa chọn của API mẫu cho sự cố upstream**, không phải mã trạng thái bắt buộc cho mọi lỗi AI. Nếu ứng dụng bắt exception và trả câu trả lời fallback, HTTP có thể vẫn 200; lúc đó cần ghi nhận thêm `fallback_used`, degraded mode và failure cause.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Nhận request / chọn case"] --> B{"Case hợp lệ?"}
    B -->|Không| C["400 / 404 - INVALID_REQUEST"]
    B -->|Có| D["Gọi AnswerGenerator"]
    D --> E{"Có lỗi kỹ thuật?"}
    E -->|Có| F["503 - TECHNICAL_ERROR, NOT_EVALUATED"]
    E -->|Không| G["Có câu trả lời"]
    G --> H["Quality scorer / evaluator"]
    H --> I{"Đạt rubric?"}
    I -->|Có| J["200 - COMPLETED, PASS"]
    I -->|Không| K["200 - COMPLETED, FAIL"]
~~~

Sơ đồ trên dùng một **scorer xác định** để mô phỏng phép chấm nội dung. Khi dùng LLM-as-a-Judge thật, phải thêm nhánh `EVALUATION_ERROR`, `SKIPPED`, `NO_CONTEXT` và rubric/threshold theo policy đã được định nghĩa.

## 3. Đề bài nghiệp vụ và ba tình huống cố định

Ứng dụng hỏi đáp về một quy định giả lập:

> **Nguồn:** `policy-monthly-v1` — “Báo cáo tháng phải được nộp trước ngày 05 của tháng kế tiếp.”

| Mã case | Câu hỏi | Kết quả của generator giả lập | Kỳ vọng |
|---|---|---|---|
| `success` | “Hạn nộp báo cáo tháng là khi nào?” | “Báo cáo tháng phải được nộp trước ngày 05 của tháng kế tiếp.” | `COMPLETED + PASS` |
| `wrong` | Cùng câu hỏi và context | “Báo cáo tháng phải được nộp trước ngày 15 của tháng kế tiếp.” | `COMPLETED + FAIL` |
| `technical` | Cùng câu hỏi và context | Generator mô phỏng provider timeout, **không trả answer** | `TECHNICAL_ERROR + NOT_EVALUATED` |

Sự khác biệt giữa `success` và `wrong` **không nằm ở câu hỏi hay nguồn**, mà nằm ở nội dung câu trả lời được tạo. Như vậy, demo tránh trường hợp kết quả chấm khác chỉ vì hai case đọc hai nguồn bằng chứng khác nhau.

**Giới hạn quan trọng:** đây là ba fixture **có chủ đích**, không phải bằng chứng cho thấy một model thực tế có accuracy cụ thể. Không dùng tỷ lệ 2/3 từ ba case giả lập để đánh giá chất lượng sản phẩm.

## 4. Cấu trúc dự án

~~~text
ai-outcome-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/aioutcomes/
│   │   │   ├── AiOutcomeLabApplication.java
│   │   │   ├── DemoCase.java
│   │   │   ├── CaseCatalog.java
│   │   │   ├── AnswerGenerator.java
│   │   │   ├── FixtureAnswerGenerator.java
│   │   │   ├── LiveAnswerGenerator.java
│   │   │   ├── DemoUpstreamException.java
│   │   │   ├── ReferenceScorer.java
│   │   │   ├── DemoResponse.java
│   │   │   ├── DemoService.java
│   │   │   ├── DemoController.java
│   │   │   └── DemoExceptionHandler.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── application-live.yml
│   └── test/
│       ├── java/com/example/aioutcomes/
│       │   ├── ReferenceScorerTest.java
│       │   └── DemoHttpTest.java
│       └── resources/evaluation/
│           └── smoke-cases.jsonl
└── reports/                     # Kết quả thí nghiệm, không chứa secrets
~~~

Các tệp trên là **đường dẫn mẫu để người học tạo trong dự án thực hành**. Trong nhiệm vụ viết tài liệu này, chỉ file Markdown bài học và `status` của YAML được chỉnh sửa; không có mã Java hoặc build project khác được tạo trên workspace.

Để giữ trách nhiệm rõ ràng:

- `CaseCatalog` chỉ định nghĩa **input, evidence và đáp án tham chiếu**.
- `AnswerGenerator` chỉ tạo câu trả lời hoặc phát sinh lỗi kỹ thuật.
- `ReferenceScorer` chỉ chấm nội dung **khi có answer**, không quyết định HTTP status.
- `DemoService` điều phối và ghi metrics.
- `DemoController` chuyển kết quả thành HTTP response; `DemoExceptionHandler` ánh xạ exception thành mã lỗi an toàn.
- `LiveAnswerGenerator` là adapter tùy chọn cho provider thật, **không** dùng để tạo kết quả sai/timeout một cách xác định.

## 5. Cấu hình Maven: Spring Boot và Spring AI

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>ai-outcome-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>

        <!-- Sẵn sàng cho adapter live; fixture mode tắt model auto-config -->
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-starter-model-openai</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

**Vì sao có Spring AI starter dù chạy offline?** Bài sẽ cung cấp một adapter dùng `ChatClient` thật. Khi chạy fixture, ta chủ động đặt `spring.ai.model.chat=none` và `spring.ai.model.embedding=none`, nên không cần khóa OpenAI hoặc kết nối embedding. Maven vẫn phải tải dependency để biên dịch, nhưng **không gọi network provider lúc chạy fixture**.

**Lưu ý phiên bản:** Spring AI 2.1.x tương thích với Spring Boot 4.2.x; BOM Spring AI quản lý các module AI, còn Spring Boot parent quản lý Boot, Micrometer, Actuator và test starters. Spring Boot 4.2 có starter `spring-boot-starter-webmvc-test` dành cho kiểm thử MVC; không sao chép nguyên cách đặt package của test annotations từ Boot 3.x.

## 6. application.yml: mặc định chạy deterministic, không cần khóa API

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: ai-outcome-lab
  ai:
    model:
      chat: none
      embedding: none
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
      observations:
        log-prompt: false
        log-completion: false

app:
  demo:
    backend: fixture

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
~~~

Trong cấu hình này:

- `app.demo.backend: fixture` là **property ứng dụng tự định nghĩa**, dùng bởi `@ConditionalOnProperty`; nó không phải tên cấu hình built-in của Spring AI.
- `spring.ai.model.chat: none` tắt tự động tạo provider chat khi đang chạy offline; `embedding: none` ngăn việc vô ý khởi tạo embedding provider.
- Không có `OPENAI_API_KEY` trong YAML này.
- Actuator và Prometheus có thể phục vụ smoke test. Nếu mở endpoint `/actuator/prometheus` tại production, cần kiểm soát mạng và xác thực.

**src/main/resources/application-live.yml** — chỉ dùng khi có quyền gọi provider:

~~~yaml
spring:
  ai:
    model:
      chat: openai
    openai:
      api-key: ${OPENAI_API_KEY}
      chat:
        model: ${GENERATOR_MODEL:gpt-4o-mini}

app:
  demo:
    backend: live
~~~

Khi kích hoạt profile `live`, thuộc tính được ghi đè từ profile-specific file. Model ID là **ví dụ**, cần xác nhận quyền truy cập của tài khoản và giới hạn của provider. Không truyền credentials thật vào file Git, log, fixture hoặc bài chấm.

## 7. Khởi tạo Spring Boot application

**AiOutcomeLabApplication.java**

~~~java
package com.example.aioutcomes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AiOutcomeLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(AiOutcomeLabApplication.class, args);
    }
}
~~~

Vì annotation `@SpringBootApplication` nằm cùng package gốc với các classes còn lại nên Spring quét được controller, service, các generator beans và advice.

## 8. CaseCatalog: cố định input và ground truth

**DemoCase.java**

~~~java
package com.example.aioutcomes;

public record DemoCase(
        String id,
        String question,
        String sourceId,
        String evidence,
        String referenceAnswer) {}
~~~

**CaseCatalog.java**

~~~java
package com.example.aioutcomes;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class CaseCatalog {
    private static final String QUESTION =
        "Hạn nộp báo cáo tháng là khi nào?";
    private static final String SOURCE =
        "Báo cáo tháng phải được nộp trước ngày 05 của tháng kế tiếp.";

    private final Map<String, DemoCase> cases = Map.of(
        "success", new DemoCase("success", QUESTION,
            "policy-monthly-v1", SOURCE, SOURCE),
        "wrong", new DemoCase("wrong", QUESTION,
            "policy-monthly-v1", SOURCE, SOURCE),
        "technical", new DemoCase("technical", QUESTION,
            "policy-monthly-v1", SOURCE, SOURCE)
    );

    public DemoCase require(String id) {
        DemoCase found = cases.get(id);
        if (found == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Mã tình huống không tồn tại");
        }
        return found;
    }
}
~~~

Ba case có **cùng nguồn và câu hỏi**. `referenceAnswer` dùng trong **scorer offline**, không đưa cho generator thật; một hệ thống production nên tách dataset reference khỏi inference API để ngăn làm lộ nhãn kiểm thử.

**Đừng đổi referenceAnswer theo nội dung model trả ra.** Ground truth phải được review và version hóa trước khi chạy evaluation. Với nhiều câu trả lời hợp lệ hoặc câu hỏi mở, exact string reference không đủ: cần rubric, nhiều expected claims hoặc người chấm.

## 9. AnswerGenerator và hai implementation

Giao diện không phụ thuộc HTTP, Micrometer hay evaluator:

**AnswerGenerator.java**

~~~java
package com.example.aioutcomes;

public interface AnswerGenerator {
    String generate(DemoCase scenario);
}
~~~

### 9.1. FixtureAnswerGenerator: kiểm thử ba nhánh xác định

**FixtureAnswerGenerator.java**

~~~java
package com.example.aioutcomes;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "app.demo",
    name = "backend",
    havingValue = "fixture",
    matchIfMissing = true
)
public class FixtureAnswerGenerator implements AnswerGenerator {

    @Override
    public String generate(DemoCase scenario) {
        return switch (scenario.id()) {
            case "success" -> scenario.referenceAnswer();
            case "wrong" ->
                "Báo cáo tháng phải được nộp trước ngày 15 của tháng kế tiếp.";
            case "technical" ->
                throw new DemoUpstreamException(
                    "FIXTURE_UPSTREAM_TIMEOUT");
            default -> throw new IllegalArgumentException(
                    "Fixture không được hỗ trợ");
        };
    }
}
~~~

**Lỗi kỹ thuật là một exception**, không phải text `"Error"`, `"TIMEOUT"` hoặc câu trả lời rỗng được chấm là `FAIL`. Việc tạo lỗi có chủ đích được giới hạn trong fixture mode và các case đã đăng ký, không được để người dùng production tùy ý kích hoạt.

**DemoUpstreamException.java**

~~~java
package com.example.aioutcomes;

public class DemoUpstreamException extends RuntimeException {
    public DemoUpstreamException(String code) {
        super(code);
    }

    public DemoUpstreamException(String code, Throwable cause) {
        super(code, cause);
    }
}
~~~

Một hệ thống thật cần **phân loại lỗi** chi tiết hơn: 429/rate limit, timeout, invalid API key, 5xx của provider, tool timeout, parse error và circuit breaker open. Không map mọi lỗi HTTP/Java thành `503` nếu nguyên nhân thuộc client validation hoặc lỗi lập trình nội bộ.

### 9.2. LiveAnswerGenerator: thay bằng ChatClient khi cần

**LiveAnswerGenerator.java**

~~~java
package com.example.aioutcomes;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "app.demo",
    name = "backend",
    havingValue = "live"
)
public class LiveAnswerGenerator implements AnswerGenerator {
    private final ChatClient client;

    public LiveAnswerGenerator(ChatClient.Builder builder) {
        this.client = builder.build();
    }

    @Override
    public String generate(DemoCase scenario) {
        try {
            return client.prompt()
                .system("""
                    Hãy trả lời bằng tiếng Việt. Chỉ dựa vào tài liệu
                    được cung cấp; nếu thiếu dữ liệu hãy nói không biết.
                    """)
                .user(u -> u.text("""
                        Tài liệu:
                        {context}

                        Câu hỏi:
                        {question}
                        """)
                    .param("context", scenario.evidence())
                    .param("question", scenario.question()))
                .call()
                .content();
        } catch (RuntimeException cause) {
            throw new DemoUpstreamException(
                "PROVIDER_CALL_FAILED", cause);
        }
    }
}
~~~

Đường `live` **không bảo đảm** `success` luôn pass, `wrong` luôn fail hoặc `technical` luôn lỗi: tất cả ba case lúc này đều dùng **một model thật** trên cùng evidence, và kết quả phụ thuộc model/provider. Dùng **fixture** để kiểm thử ba nhánh deterministic; dùng **live** để đo chất lượng thực. Trong các integration tests về lỗi provider, nên mock provider, dùng fault-injection proxy hoặc test double riêng.

Ví dụ chọn `ChatClient.Builder` do Boot/Spring AI tự cấu hình để giữ các customizers và observation settings. Với nhiều `ChatModel` beans, phải chọn builder/model chính xác, không giả định dependency injection sẽ tự biết đâu là generator.

## 10. ReferenceScorer: chấm nội dung khi thực thi hoàn tất

Để xác nhận ba nhánh ổn định mà không cần judge model, ta sử dụng một scorer **chỉ dành cho case demo**:

**ReferenceScorer.java**

~~~java
package com.example.aioutcomes;

import org.springframework.stereotype.Component;

@Component
public class ReferenceScorer {

    public boolean matchesReference(
            DemoCase scenario, String generatedAnswer) {

        return generatedAnswer != null
            && generatedAnswer.trim()
                 .equals(scenario.referenceAnswer());
    }
}
~~~

`matchesReference` chỉ kiểm tra **trùng exact reference** (bỏ khoảng trắng đầu/cuối). Đây là **smoke oracle**, hoàn toàn **không tương đương** đo semantic relevance, fact checking hoặc accuracy của một LLM. Một câu trả lời đúng nhưng diễn đạt lại bằng từ khác có thể bị chấm `FAIL`; nhiều claim sai tinh vi cũng không thể được phân tích bằng phép so chuỗi.

Trong ứng dụng thật, thay/ghép scorer bằng:

- **Deterministic assertions** cho retrieval document IDs, tool name/arguments, response schema và business rules.
- **RelevancyEvaluator** để xét câu trả lời có liên quan tới question/context.
- **FactCheckingEvaluator** để kiểm tra các phát biểu có được tài liệu nguồn hỗ trợ.
- **Rubric và human-labeled calibration** để hiểu tỷ lệ judge false pass/false fail.

**Thứ tự:** chỉ bắt đầu chấm chất lượng sau khi đã có câu trả lời hợp lệ. Nếu generator ném exception hoặc trả null/blank thì ưu tiên trạng thái **technical error**, không chấm fact checking là fail.

## 11. DemoService: tách execution, quality và telemetry

**DemoResponse.java**

~~~java
package com.example.aioutcomes;

public record DemoResponse(
        String caseId,
        String question,
        String answer,
        String executionStatus,
        String qualityStatus,
        String sourceId) {}
~~~

**DemoService.java**

~~~java
package com.example.aioutcomes;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class DemoService {
    private final CaseCatalog catalog;
    private final AnswerGenerator generator;
    private final ReferenceScorer scorer;
    private final MeterRegistry registry;

    public DemoService(
            CaseCatalog catalog,
            AnswerGenerator generator,
            ReferenceScorer scorer,
            MeterRegistry registry) {
        this.catalog = catalog;
        this.generator = generator;
        this.scorer = scorer;
        this.registry = registry;
    }

    public DemoResponse run(String caseId) {
        // 404 xảy ra trước khi ghi model outcome.
        DemoCase scenario = catalog.require(caseId);

        Timer.Sample sample = Timer.start(registry);
        String execution = "technical_error";
        String quality = "not_evaluated";

        try {
            String answer = generator.generate(scenario);
            if (answer == null || answer.isBlank()) {
                throw new DemoUpstreamException("EMPTY_MODEL_RESPONSE");
            }

            execution = "completed";
            quality = scorer.matchesReference(scenario, answer)
                    ? "pass" : "fail";

            return new DemoResponse(
                scenario.id(),
                scenario.question(),
                answer,
                execution.toUpperCase(),
                quality.toUpperCase(),
                scenario.sourceId());

        } finally {
            Counter.builder("app.ai.demo.requests")
                .tag("execution", execution)
                .tag("quality", quality)
                .register(registry)
                .increment();

            sample.stop(Timer.builder("app.ai.demo.duration")
                .tag("execution", execution)
                .tag("quality", quality)
                .register(registry));
        }
    }
}
~~~

**Điều đáng chú ý:**

- `catalog.require()` đặt **trước** timer. Request không có case là lỗi input, không bị đếm là provider/model technical failure.
- Biến `execution` mặc định là `technical_error` và `quality` mặc định `not_evaluated` để những exception bất ngờ trong luồng gọi model vẫn được ghi vào telemetry.
- Chỉ khi `generate()` có answer thì `execution=completed` và scorer mới chạy.
- `finally` vẫn ghi counter và timer ở cả nhánh có exception.
- Metric label **chỉ lấy từ tập giá trị đóng** trong code, không sử dụng `caseId`, `question` hoặc nội dung answer làm label.

Các `String` trong bài được dùng cho dễ đọc. Với code production, nên dùng `enum ExecutionStatus` và `enum QualityStatus`, một policy rõ ràng cho các trường hợp `EVALUATION_ERROR`, `SKIPPED`, `NO_CONTEXT` và **không** dùng `execution=completed` để ám chỉ `quality=pass`.

### Trường hợp lỗi phát sinh trong scorer

Mẫu demo định nghĩa scorer thuần, không gọi network và không thể ném lỗi dự kiến. Nếu sử dụng LLM judge thật, một exception từ judge xảy ra **sau khi generator đã hoàn tất** phải được phân loại thành `EVALUATION_ERROR`, không gộp với `GENERATION_ERROR`. Vì vậy trong hệ thống production nên tách riêng:

~~~text
generation.execute() -> ExecutionResult(COMPLETED, answer)
evaluation.assess(answer) -> Assessment(PASS | FAIL | EVALUATION_ERROR)
~~~

Không bao toàn bộ generator và evaluator trong một `try/catch` duy nhất rồi trả `UPSTREAM_UNAVAILABLE` khi judge timeout nếu yêu cầu của hệ thống là vẫn trả lời cho người dùng.

## 12. HTTP API và ánh xạ lỗi kỹ thuật

**DemoController.java**

~~~java
package com.example.aioutcomes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class DemoController {
    private final DemoService service;

    public DemoController(DemoService service) {
        this.service = service;
    }

    @GetMapping("/{caseId}")
    public DemoResponse run(@PathVariable String caseId) {
        return service.run(caseId);
    }
}
~~~

**DemoExceptionHandler.java**

~~~java
package com.example.aioutcomes;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DemoExceptionHandler {

    @ExceptionHandler(DemoUpstreamException.class)
    public ResponseEntity<DemoError> handleUpstream(
            DemoUpstreamException exception) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new DemoError(
                "UPSTREAM_UNAVAILABLE",
                "Không thể hoàn tất yêu cầu lúc này"));
    }

    public record DemoError(String code, String message) {}
}
~~~

Handler **không đưa nội dung exception/cause ra HTTP body**, tránh lộ API key, endpoint nội bộ hoặc metadata provider. Exception vẫn có thể được ghi ở nơi có quyền theo chính sách, nhưng tuyệt đối không dump prompt nhạy cảm hoặc secrets.

Ứng dụng trả `404` cho case không tồn tại nhờ `ResponseStatusException`. Tình huống `wrong` không ném exception nên trả `200` bình thường, dù `qualityStatus=FAIL`.

### Vì sao cố ý dùng GET cho demo?

Endpoint `GET /api/demo/{caseId}` chỉ chọn **một fixture có sẵn**, không tạo side effect và không nhận prompt tùy ý; tiện để kiểm thử. API tạo câu trả lời thật nên thường dùng **POST**, có kiểm tra input, giới hạn quyền, quota, timeout và quy tắc audit riêng. Không để HTTP endpoint production mở công khai một công tắc ép provider lỗi hoặc gọi tool có tác động.

## 13. Chạy ứng dụng và quan sát ba kết quả

Trong project thực hành, chạy:

~~~bash
java -version
./mvnw -version
./mvnw clean test
./mvnw spring-boot:run
~~~

Nếu project không có Maven Wrapper, cần tạo wrapper bằng quy trình build của đội hoặc dùng Maven tương thích. Các lệnh này dành cho **người học thực hành**, không phải kiểm thử đã được chạy trong tác vụ viết bài.

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/api/demo/success
curl -i http://localhost:8080/api/demo/wrong
curl -i http://localhost:8080/api/demo/technical
curl -i http://localhost:8080/api/demo/unknown
~~~

### 13.1. Thành công và đúng

<escape>Ví dụ response:</escape>

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"caseId":"success","question":"Hạn nộp báo cáo tháng là khi nào?","answer":"Báo cáo tháng phải được nộp trước ngày 05 của tháng kế tiếp.","executionStatus":"COMPLETED","qualityStatus":"PASS","sourceId":"policy-monthly-v1"}
~~~

### 13.2. Thành công kỹ thuật nhưng sai nội dung

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"caseId":"wrong","question":"Hạn nộp báo cáo tháng là khi nào?","answer":"Báo cáo tháng phải được nộp trước ngày 15 của tháng kế tiếp.","executionStatus":"COMPLETED","qualityStatus":"FAIL","sourceId":"policy-monthly-v1"}
~~~

**HTTP 200 là đúng trong tình huống này:** server đã xử lý request và trả một câu trả lời. Việc sai sự thật cần được ghi vào quality signal/evaluation report, không nên tự đổi mọi câu trả lời sai thành HTTP 500.

### 13.3. Lỗi kỹ thuật

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"UPSTREAM_UNAVAILABLE","message":"Không thể hoàn tất yêu cầu lúc này"}
~~~

Ở nhánh này không có `answer`, cũng không có `qualityStatus=FAIL`. Trong tầng báo cáo evaluation, ánh xạ `execution=TECHNICAL_ERROR` và `quality=NOT_EVALUATED`. HTTP body chỉ mang lỗi an toàn cho client; **bản ghi telemetry** giữ mã lỗi đã phân loại riêng.

Nếu gọi một mã case không có trong catalog, ứng dụng trả `404`. Đây là **invalid request**, không phải lỗi sinh câu trả lời.

### Bảng kết quả sau một lượt gọi mỗi case

| Case | HTTP status | Execution | Quality | Kết quả cần thấy |
|---|---:|---|---|---|
| `success` | 200 | COMPLETED | PASS | Có answer đúng |
| `wrong` | 200 | COMPLETED | FAIL | Có answer sai nhưng request hoàn tất |
| `technical` | 503 | TECHNICAL_ERROR | NOT_EVALUATED | Không có answer hợp lệ |
| `unknown` | 404 | INVALID_REQUEST | NOT_EVALUATED | Không đếm là lỗi provider |

## 14. Unit test và HTTP integration test

### Test scorer không cần network

**ReferenceScorerTest.java**

~~~java
package com.example.aioutcomes;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ReferenceScorerTest {
    private final ReferenceScorer scorer = new ReferenceScorer();

    private final DemoCase scenario = new DemoCase(
        "test",
        "Hạn nộp báo cáo tháng?",
        "policy-monthly-v1",
        "Hạn nộp trước ngày 05.",
        "Hạn nộp trước ngày 05.");

    @Test
    void passesExactReferenceAnswer() {
        assertTrue(scorer.matchesReference(
            scenario, "Hạn nộp trước ngày 05."));
    }

    @Test
    void rejectsIncorrectAnswer() {
        assertFalse(scorer.matchesReference(
            scenario, "Hạn nộp trước ngày 15."));
    }

    @Test
    void rejectsMissingAnswer() {
        assertFalse(scorer.matchesReference(scenario, null));
    }
}
~~~

### Test HTTP với MockMvc (Spring Boot 4)

**DemoHttpTest.java**

~~~java
package com.example.aioutcomes;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "app.demo.backend=fixture")
@AutoConfigureMockMvc
class DemoHttpTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void successReturns200AndQualityPass() throws Exception {
        mvc.perform(get("/api/demo/success"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.executionStatus").value("COMPLETED"))
            .andExpect(jsonPath("$.qualityStatus").value("PASS"));
    }

    @Test
    void wrongStillReturns200ButQualityFail() throws Exception {
        mvc.perform(get("/api/demo/wrong"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.executionStatus").value("COMPLETED"))
            .andExpect(jsonPath("$.qualityStatus").value("FAIL"));
    }

    @Test
    void technicalErrorReturns503() throws Exception {
        mvc.perform(get("/api/demo/technical"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"));
    }

    @Test
    void unknownCaseReturns404() throws Exception {
        mvc.perform(get("/api/demo/unknown"))
            .andExpect(status().isNotFound());
    }
}
~~~

Test trên cần `spring-boot-starter-webmvc-test` test dependency tương ứng Boot 4.2. Với một hệ thống có Spring Security hoặc các filters tùy chỉnh, kiểm thử còn cần mock identity/permissions phù hợp. Việc `@SpringBootTest` pass không tự chứng minh provider thật hoạt động; trong **fixture mode** không có lời gọi model nào được thực hiện.

### Test không nên phụ thuộc kết quả ngẫu nhiên của model

Nếu thay fixture bằng model thật, test `wrongReturns200AndFail` không còn deterministic. Hãy chia thành:

- **Unit/component tests offline:** fixture/fake, chạy mọi commit.
- **Live smoke tests:** dùng provider test credentials, xác nhận integration, API/trace/usage.
- **Dataset regression tests:** đủ số lượng case và judge đã hiệu chuẩn, có quota, cho phép sai số.
- **Fault-injection tests:** mô phỏng timeout, 429/5xx, tool failure mà không phụ thuộc sự cố thật.

## 15. Dùng metrics để nhìn thấy cả ba nhánh

`DemoService` ghi hai meter logic:

| Meter | Loại | Dùng để làm gì? |
|---|---|---|
| `app.ai.demo.requests` | Counter | Đếm số case đã chạy theo `execution` và `quality` |
| `app.ai.demo.duration` | Timer | Thời gian đo từ lúc vào `DemoService` tới khi trả/throw |

Chạy ba case trước, sau đó kiểm tra:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/app.ai.demo.requests
curl http://localhost:8080/actuator/metrics/app.ai.demo.duration
curl http://localhost:8080/actuator/prometheus
~~~

Nếu Prometheus registry đã hoạt động, counter có thể xuất dưới tên đã chuẩn hóa `app_ai_demo_requests_total`, và timer dưới `app_ai_demo_duration_seconds_count` / `..._seconds_sum` cùng các nhãn như `execution="completed"`, `quality="fail"`.

**Đây là metric tùy biến của demo**, không phải metrics tự tạo của Spring AI. Kết quả từ fixture **không** phát sinh `gen_ai.client.operation` hoặc `gen_ai.client.token.usage`, vì không có ChatModel call thật. Khi bật adapter live, Spring AI mới có thể phát sinh các observations/metrics đó.

### PromQL kiểm tra số case sai nhưng không lỗi kỹ thuật

~~~promql
sum(increase(app_ai_demo_requests_total{
  execution="completed",quality="fail"
}[30m]))
~~~

### PromQL kiểm tra lỗi kỹ thuật

~~~promql
sum(increase(app_ai_demo_requests_total{
  execution="technical_error"
}[30m]))
~~~

Nếu gọi mỗi case đúng một lần, kết quả lý tưởng là **một request completed+pass**, **một completed+fail** và **một technical_error+not_evaluated**, chưa kể các lần test hoặc request từ người khác. Prometheus `increase` trên dữ liệu scrape thưa, counter ngắn đời hoặc một cửa sổ chưa đủ samples có thể cho kết quả xấp xỉ khác số nguyên; hãy xem cả raw meter/labels trong smoke test.

### Tính pass rate phải công khai mẫu số

Giả sử có 100 case, trong đó 70 pass, 20 fail, 10 technical error:

\[
\text{pass rate trên case đã chấm}
= \frac{70}{70+20} \approx 77.8\%
\]

\[
\text{coverage}
= \frac{70+20}{100} = 90\%
\]

\[
\text{technical error rate}
= \frac{10}{100} = 10\%
\]

**77,8% không phải tỷ lệ pass của toàn bộ 100 case.** Nếu 10 case lỗi bị bỏ khỏi mẫu số mà không báo coverage, báo cáo có thể che giấu sự cố hạ tầng nghiêm trọng.

## 16. Dùng Spring AI Evaluators thay scorer giả lập

Sau khi ba nhánh vận hành đã ổn định, chạy một bộ RAG có context và dùng judge model riêng để đo chất lượng thực.

### EvaluationRequest cần đúng nguồn evidence

Spring AI 2.1 có API:

~~~java
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

EvaluationRequest request = new EvaluationRequest(
    originalQuestion,
    List.of(new Document(retrievedContext)),
    generatedAnswer);
~~~

**Khi chuyển sang RAG thật:** `retrievedContext` phải là **tài liệu đã thực sự được đưa vào generator** sau lọc/reranking/truncation, không tự fetch lại nguồn khác cho judge.

### Cấu hình evaluator theo judge model

Ví dụ fragment bean configuration (chỉ kích hoạt trong môi trường có ChatModel thật và judge credentials):

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JudgeConfiguration {
    @Bean
    RelevancyEvaluator relevanceEvaluator(ChatClient.Builder builder) {
        return new RelevancyEvaluator(builder);
    }

    @Bean
    FactCheckingEvaluator factCheckingEvaluator(
            ChatClient.Builder builder) {
        return FactCheckingEvaluator.builder(builder).build();
    }
}
~~~

Đây là **fragment minh họa**, không được thả trực tiếp vào fixture mode mà không đặt điều kiện bật/tắt: trong fixture mode `spring.ai.model.chat=none`, không có ChatClient.Builder dựa trên model. Để cấu hình generator/judge khác model hoặc khác API key, cần khởi tạo **đúng builder/model cho từng vai trò**, dùng `@Qualifier`, conditional configuration hoặc tách evaluation worker. Hai `ChatClient` dùng cùng auto-configured `ChatModel` có thể vẫn chia sẻ provider credentials.

Ở Spring AI 2.1, `RelevancyEvaluator` và `FactCheckingEvaluator` trả `EvaluationResponse` với `isPass()`. Một ví dụ dùng:

~~~java
var relevanceResult = relevanceEvaluator.evaluate(request);
var factualityResult = factCheckingEvaluator.evaluate(request);

boolean relevancePass = relevanceResult.isPass();
boolean factCheckPass = factualityResult.isPass();
~~~

Đánh giá **relevance** khác **fact checking**:

- Câu “báo cáo nộp trước ngày 15” vẫn **liên quan** đến câu hỏi thời hạn nộp, nên relevance có thể pass.
- Nhưng câu đó **mâu thuẫn** với nguồn “trước ngày 05”, nên fact checking/groundedness phải fail theo rubric của bài.
- Lỗi timeout của judge sau khi generator trả answer phải là `EVALUATION_ERROR`; không ép câu trả lời thành `FAIL` vì hạ tầng chấm lỗi.

Không giả định mọi judge sẽ luôn cho kết quả như mong đợi; cần dùng bộ dữ liệu có nhãn người và hiệu chuẩn độ chính xác của judge.

## 17. Mở rộng sang RAG và tool calling

Ba outcome của ví dụ có thể áp dụng cho cả retrieval và tool:

| Bước | Thành công | Sai chất lượng/hành vi | Lỗi kỹ thuật |
|---|---|---|---|
| Retriever | Có document đúng, recall@k đạt | Trả document khác/thiếu nguồn, vẫn hoạt động | Vector DB không kết nối, timeout |
| ChatModel | Answer đúng bằng chứng | Answer bịa hoặc sai dữ kiện, request hoàn tất | 429, 503, timeout, invalid response |
| Tool calling | Chọn đúng tool, arguments đúng, kết quả được dùng đúng | Gọi sai tool hoặc tham số nhưng không có exception | Tool trả 5xx/timeout, schema parse failure |
| Evaluator | Chấm đúng, rubric nhất quán | Judge cho false pass/false fail | Judge timeout/429/không parse được verdict |

### Dữ liệu case có thể tái lập

`src/test/resources/evaluation/smoke-cases.jsonl` (mẫu schema):

~~~jsonl
{"id":"success","scenario":"rag","question":"Hạn nộp báo cáo tháng là khi nào?","sourceIds":["policy-monthly-v1"],"expectedClaim":"trước ngày 05 của tháng kế tiếp","expectedExecution":"COMPLETED","expectedQuality":"PASS"}
{"id":"wrong","scenario":"rag","question":"Hạn nộp báo cáo tháng là khi nào?","sourceIds":["policy-monthly-v1"],"expectedClaim":"trước ngày 05 của tháng kế tiếp","expectedExecution":"COMPLETED","expectedQuality":"FAIL"}
{"id":"technical","scenario":"rag","question":"Hạn nộp báo cáo tháng là khi nào?","sourceIds":["policy-monthly-v1"],"expectedClaim":"trước ngày 05 của tháng kế tiếp","expectedExecution":"TECHNICAL_ERROR","expectedQuality":"NOT_EVALUATED"}
~~~

**Quan trọng:** JSONL này là dữ liệu tham khảo cho test harness, **chưa được `CaseCatalog` của ví dụ tự động load**. Một bước mở rộng là viết `CaseRepository` đọc và validate JSONL, quản lý `dataset_revision`/hash và đưa các case vào generator/test runner.

### Ví dụ tool calling

Giả sử fixture về đơn hàng:

~~~json
{
  "question": "Đơn TEST-104 đang ở trạng thái nào?",
  "expectedTool": {
    "name": "getOrderStatus",
    "arguments": {"orderId": "TEST-104"}
  },
  "toolFixture": {"status": "IN_TRANSIT"},
  "expectedAnswerClaim": "Đang vận chuyển"
}
~~~

**Sai chất lượng/hành vi:** tool có thể chạy và trả HTTP 200, nhưng assistant gọi `getOrderStatus` với ID sai hoặc kết luận “đã giao hàng” khi tool trả `IN_TRANSIT`. Kiểm tra **tool name/arguments bằng assertion xác định** trước khi dùng judge chấm ngôn ngữ. **Lỗi kỹ thuật:** tool timeout hoặc trả 5xx; ghi `TECHNICAL_ERROR` riêng. Chỉ chạy tool test có side effect trên sandbox/mocks.

## 18. Bổ sung traces và tách chi phí

Để theo dõi luồng ứng dụng thật, có thể thêm dependency Boot 4.2:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Khi có OTLP collector và quyền export phù hợp, cấu hình:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0           # Chỉ cho lab lưu lượng thấp
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

Các span/observation đại diện khi chạy AI thật có thể gồm `spring.ai.chat.client`, `gen_ai.client.operation`, `spring.ai.tool`, `db.vector.client.operation`; metric token có tên logic `gen_ai.client.token.usage` **chỉ tăng khi provider trả usage**. Với fixture trong bài, chỉ thấy **custom demo metrics** và HTTP/JVM metrics; không tạo AI model metrics “giả” rồi diễn giải như usage từ provider.

### Hai loại độ trễ

- **User-facing latency:** request gửi vào API đến khi trả answer hoặc lỗi.
- **Evaluation latency:** thời gian chạy generator, retrieval, relevance judge, fact-check judge và ghi report; có thể chạy offline.

Không cộng duration của span cha và span con như hai lần độc lập. Với tracing, cần kiểm tra critical path của request, retry và propagation sang async tasks.

### Hai loại chi phí

\[
C_{\text{model}} =
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+ \frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}
\]

\[
C_{\text{case}} =
C_{\text{generator}} +
C_{\text{judge,relevance}} +
C_{\text{judge,fact}} +
C_{\text{retrieval/tool}}
\]

Đơn giá theo một triệu token phải lấy từ provider/model ở thời điểm chạy, có thể khác với cached/reasoning tokens. **BOM Spring AI không chứa bảng giá**. Khi usage thiếu, để `usage_status=MISSING`, không tự đặt cost bằng 0.

## 19. Report một lần chạy: lưu điều gì?

Một báo cáo có ý nghĩa phải ghép **status, context, rubric và config versions**.

~~~json
{
  "runId": "demo-fixture-001",
  "environment": "test",
  "mode": "fixture",
  "generatorModel": "none",
  "judgeModel": "none",
  "datasetRevision": "smoke-v1",
  "promptRevision": "fixture-v1",
  "rubricRevision": "reference-exact-v1",
  "cases": [
    {
      "caseId": "success",
      "execution": "COMPLETED",
      "quality": "PASS",
      "httpStatus": 200
    },
    {
      "caseId": "wrong",
      "execution": "COMPLETED",
      "quality": "FAIL",
      "httpStatus": 200
    },
    {
      "caseId": "technical",
      "execution": "TECHNICAL_ERROR",
      "quality": "NOT_EVALUATED",
      "httpStatus": 503
    }
  ]
}
~~~

Đây là **mẫu đầu ra** cần người học xây report writer nếu muốn tự động lưu, không phải file mà code `DemoService` đã sinh. Nếu chạy lại với model thật, bổ sung `generator_model`, `judge_model`, `dataset/corpus/index revision`, `prompt/rubric version`, commit, latency, token usage, chi phí và các error codes.

### Trạng thái nên bổ sung khi phát triển tiếp

| Trạng thái | Ý nghĩa |
|---|---|
| `NO_CONTEXT` | Retriever không có evidence đủ để trả lời; có thể cần chấm abstention |
| `EVALUATION_ERROR` | Model judge hoặc bộ parse verdict lỗi |
| `GENERATION_ERROR` | ChatModel trả response lỗi/không hợp lệ |
| `TOOL_ERROR` | Tool không khả dụng hoặc trả lỗi |
| `SKIPPED` | Case không chạy vì quota/policy/điều kiện dữ liệu |

Định nghĩa riêng **tỷ lệ case có verdict hợp lệ** và **tỷ lệ lỗi vận hành**. Không coi trường thiếu kết quả là PASS; cũng không làm giảm tỷ lệ chất lượng generator chỉ vì judge backend gặp lỗi.

## 20. Cách phân biệt sai AI với lỗi hạ tầng khi debug

| Dấu hiệu | Phân loại ban đầu | Bằng chứng nên xem |
|---|---|---|
| HTTP 200, answer có “ngày 15” | Sai chất lượng | Evidence “ngày 05”, expected claims, fact-check verdict |
| HTTP 200, answer đúng, judge trả 429 | Generator hoàn tất; lỗi chấm | Judge trace, quota/retry, `EVALUATION_ERROR` |
| HTTP 503, provider timeout | Lỗi kỹ thuật | Provider/HTTP spans, timeout, retry, circuit breaker |
| HTTP 200, gọi tool sai tên | Sai hành vi ứng dụng | Tool recorder, tool schema và expected arguments |
| HTTP 500, null pointer ở Java | Lỗi kỹ thuật do code | Exception class, code path, test, không quy cho mô hình |
| HTTP 200, retrieval không thấy tài liệu | Có thể lỗi retrieval/quality | `recall@k`, top-k, vector query trace |
| HTTP 200, model từ chối đúng khi thiếu nguồn | Chất lượng theo policy riêng | `expectAbstention`, context, rubric |
| HTTP 200, usage token không có | Chưa đủ dữ liệu chi phí | Response metadata/provider support, không tự ghi 0 |

**Mô hình không đúng** là kết luận thuộc nghiệp vụ/quality. **Request lỗi** là kết luận thuộc tầng vận hành. Có thể cùng tồn tại nhiều vấn đề trong một run nhưng không nên đánh đồng chúng.

## 21. Bài thực hành mở rộng

### Bài A — Khẳng định ba outcome không nhập nhằng

1. Chạy fixture mode không cần API key.
2. Gọi ba endpoint đã đăng ký.
3. Ghi lại HTTP code và hai cột `executionStatus`, `qualityStatus`.
4. Kiểm tra metric counter và timer.
5. Chạy MockMvc tests; cố ý thay case `wrong` thành `qualityStatus=PASS` để thấy test thất bại.

**Điều kiện đạt:** cả ba kết quả xác định đúng như bảng; việc cố tình thay sai classification bị test phát hiện.

### Bài B — Thử ca “đúng nhưng khác câu chữ”

Giữ evidence “trước ngày 05”, thay fixture answer thành: “Nộp trước mùng 5 tháng sau.” `ReferenceScorer` so exact string có thể cho FAIL mặc dù ý nghĩa đúng.

**Nhiệm vụ:** giải thích vì sao exact match không đại diện semantic quality; viết thêm một nhánh chấm bằng expected claims/rules hoặc evaluator thật và hiệu chuẩn với nhãn con người. Không tự xem một kết quả YES từ judge là bằng chứng đúng tuyệt đối.

### Bài C — Thử lỗi judge riêng

Giả lập generator đã trả đúng answer nhưng evaluator ném timeout. Báo cáo:

~~~text
generator.execution = COMPLETED
generator.answer = available
evaluation.status = EVALUATION_ERROR
evaluation.quality = NOT_EVALUATED
http.user_response = 200 (nếu chạy judge offline)
~~~

Kiểm tra các chỉ số `evaluation_coverage` và `evaluation_error_rate` thay đổi, nhưng `generator_error_rate` không tăng.

### Bài D — Chuyển sang ChatClient thật

1. Tạo một bộ synthetic RAG dataset có quyền sử dụng, dùng profile `live` và **provider test key**.
2. Chạy 5–10 case có source IDs và ground truth.
3. Ghi lại context được cấp đúng cho generator, answer, model, prompt version và token usage.
4. Chạy relevance/fact checking bằng judge có rubric/version rõ ràng.
5. So `PASS/FAIL/ERROR` với các HTTP/model/tool/VectorStore spans và counters.

**Lưu ý:** việc chạy lời gọi live tốn tiền và kết quả có thể ngẫu nhiên; cần quota, timeout, retry limits, giám sát chi phí và điều kiện dữ liệu cho phép.

### Câu hỏi tự kiểm tra

1. Vì sao case `wrong` trả HTTP 200 là hợp lý?
2. Khi nào `qualityStatus` phải là `NOT_EVALUATED` thay vì `FAIL`?
3. Reference exact match bỏ sót những trường hợp đúng nào?
4. Tại sao `success` và `wrong` nên chia sẻ cùng câu hỏi/evidence khi so sánh?
5. Vì sao `FixtureAnswerGenerator` không tạo `gen_ai.client.token.usage`?
6. Sự khác nhau giữa `TECHNICAL_ERROR` của generator và `EVALUATION_ERROR` của judge?
7. Tại sao case ID không nên là Prometheus metric label?
8. Những trường nào cần được lưu để xác định một hồi quy sau khi đổi prompt/model?

**Gợi ý:** (1) HTTP đo kết quả xử lý request, không đo tính đúng của answer; (2) chưa có câu trả lời hoặc judge không chấm hợp lệ; (3) paraphrase hợp lệ; (4) cô lập biến thay đổi; (5) không có provider call; (6) lỗi ở hai giai đoạn khác nhau; (7) cardinality cao; (8) dataset, corpus/index, model, prompt, rubric, judge, framework, dependency, telemetry và thời gian.

## 22. Checklist trước khi coi demo đạt

- [ ] Ứng dụng khởi động ở fixture mode **không cần provider API key**.
- [ ] `success` trả HTTP 200, `COMPLETED` và `PASS`.
- [ ] `wrong` trả HTTP 200, `COMPLETED` và `FAIL`.
- [ ] `technical` trả HTTP 503, không có answer và không bị chấm quality FAIL.
- [ ] Case không tồn tại trả 404, không bị ghi thành model technical failure.
- [ ] Unit test và MockMvc test chứng minh các nhánh ổn định.
- [ ] Counter và timer tạo nhãn execution/quality có danh sách giá trị giới hạn.
- [ ] Metric báo cáo có **coverage, pass rate và technical error rate** riêng.
- [ ] Đã ghi rõ exact-match scorer là **smoke oracle**, không phải LLM factuality evaluator.
- [ ] Nếu bật live model, cấu hình ChatClient/credentials/quotas riêng; fixture outcomes không được giả định vẫn cố định.
- [ ] EvaluationRequest dùng đúng câu hỏi, answer và context thực tế của generator.
- [ ] Khi judge lỗi, giữ `EVALUATION_ERROR`, không quy sai lỗi cho generator.
- [ ] Không xuất prompt, secrets, PII và case IDs có cardinality cao vào metrics.
- [ ] Có run manifest ghi dataset, prompt, model, rubric, index và version code.

## Tài liệu tham khảo chính thức

1. [Spring AI 2.1 — Project Setup](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html): Spring AI BOM, phiên bản tương thích Spring Boot 4.2 và Java.
2. [Spring AI 2.1 — OpenAI Chat](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/integrations/models/openai/chat.html): `spring.ai.model.chat=none`, `ChatClient` và cấu hình provider.
3. [Spring AI 2.1 — Evaluators](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): `EvaluationRequest`, `RelevancyEvaluator`, `FactCheckingEvaluator`, verdict pass/fail.
4. [Spring AI 2.1 — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): `gen_ai.client.operation`, token usage, tool/vector operation metrics.
5. [Spring Boot 4.2 — Testing Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc` và các module MVC test của Boot 4.
6. [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): `spring-boot-starter-webmvc` và `spring-boot-starter-webmvc-test`.
7. [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer `MeterRegistry`, counter/timer và endpoint metrics.
8. [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): OpenTelemetry tracing starter, sampling và propagating traces.
9. [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): counters, timers, tags, dữ liệu đo.

> **Ghi nhớ:** **Thành công kỹ thuật không đồng nghĩa đúng nội dung.** Hãy xây ba tình huống có thể tái hiện — đúng, sai và lỗi kỹ thuật — rồi đo riêng **execution, quality và observability**. Khi chuyển từ fixture sang Spring AI thật, giữ nguyên sự phân tách ấy để tránh biến lỗi provider hoặc judge thành kết luận sai về relevance và fact checking.
