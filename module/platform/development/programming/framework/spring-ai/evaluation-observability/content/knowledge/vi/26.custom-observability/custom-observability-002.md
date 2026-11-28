# Đăng ký convention để bổ sung thuộc tính phù hợp

> **Chương:** Quan sát tùy chỉnh
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ. Đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm chất lượng qua từng phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Các ví dụ sử dụng Micrometer Observation API. Hãy đối chiếu API extension point và dependency versions với BOM thực tế của ứng dụng trước khi tích hợp.

## 1. Vì sao cần ObservationConvention?

Một business Observation cho biết một tác vụ nghiệp vụ đang diễn ra. Nhưng để metrics và traces hữu ích, mỗi observation cần một bộ thuộc tính nhất quán.

Ví dụ, các workflow Spring AI có thể cần những thuộc tính như:

- workflow nào đang chạy;
- operation đang được thực hiện;
- scenario là RAG, tool calling hay no-context;
- model đang đóng vai trò generator, judge hay embedding;
- kết quả cuối là success, abstained, rejected hay error;
- prompt revision nào được dùng;
- evaluation run nào tạo ra trace.

Nếu mỗi service tự thêm tags theo cách riêng, hệ thống sẽ nhanh chóng xuất hiện nhiều tên key và value không thống nhất: flow, workflow_name, task_type, scenario_type, modelRole, model_role... Dashboard khó tổng hợp và query phải biết tất cả biến thể.

**ObservationConvention** là extension point của Micrometer Observation dùng để chuẩn hóa tên và thuộc tính của một loại Observation dựa trên context của nó. Convention tách chính sách metadata khỏi business code.

Thay vì để mọi nơi tự quyết định tags, application service cung cấp một context có kiểu rõ ràng; convention đọc context đó và trả về bộ low-cardinality/high-cardinality key-values theo quy tắc chung.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của ObservationConvention trong Micrometer.
2. Thiết kế custom Observation.Context cho một business task.
3. Viết convention để chuẩn hóa observation name và contextual name.
4. Bổ sung low-cardinality và high-cardinality key-values đúng mục đích.
5. Đăng ký convention vào ObservationRegistry hoặc gắn trực tiếp vào một observation.
6. Giới hạn convention chỉ áp dụng cho đúng context type.
7. Kết hợp convention với Spring Boot ObservationRegistryCustomizer.
8. Hiểu ranh giới giữa business convention và Spring AI built-in conventions.
9. Kiểm thử key-values, lifecycle và convention selection.
10. Tránh duplicate keys, high-cardinality metrics và dữ liệu nhạy cảm.

## 2. ObservationConvention làm gì trong lifecycle?

Micrometer Observation chia instrumentation thành hai phần:

- **Context:** dữ liệu của operation đang được quan sát.
- **Convention:** quy tắc diễn giải context thành tên và key-values.

Một convention thường cung cấp:

| Method | Mục đích |
|---|---|
| supportsContext(...) | Xác định convention có áp dụng cho context này không |
| getName() | Tên observation ổn định |
| getContextualName(context) | Tên dễ đọc cho span/operation nếu handler hỗ trợ |
| getLowCardinalityKeyValues(context) | Tags có tập giá trị hữu hạn để dùng cho metrics |
| getHighCardinalityKeyValues(context) | Attributes có giá trị biến thiên, chủ yếu phục vụ trace |

Convention không thực thi nghiệp vụ, không gọi model, không truy vấn database và không tự gửi telemetry. Nó chỉ cung cấp metadata khi Observation lifecycle được tạo và xử lý bởi registry/handlers.

### Luồng hoạt động

~~~text
Business application service
        |
        | tạo BusinessTaskContext
        v
Observation factory / ObservationRegistry
        |
        | chọn convention phù hợp
        v
ObservationConvention
        |
        | name + contextual name + key-values
        v
Observation lifecycle
        |
        +--------------------+
        |                    |
        v                    v
Meter handler          Tracing handler
        |                    |
        v                    v
Timer/counter           Span/trace
~~~

Convention được chọn dựa trên context và cơ chế đăng ký. Một convention chỉ nên nhận những context mà nó hiểu rõ.

## 3. Phân biệt context, convention và handler

Ba thành phần có trách nhiệm khác nhau:

| Thành phần | Câu hỏi nó trả lời |
|---|---|
| Context | Operation này đang mang dữ liệu gì? |
| Convention | Dữ liệu nào nên trở thành tên và attributes? |
| Handler | Khi observation start/error/stop, cần ghi nhận hoặc export gì? |

Ví dụ business task context chứa:
- workflow = support_answer;
- scenario = rag;
- model role = generator;
- prompt revision = support-v12.

Convention quyết định:
- observation name = app.ai.business.task;
- contextual name = support-answer;
- low-cardinality keys = workflow, scenario, model_role;
- high-cardinality keys = prompt revision hoặc opaque execution reference nếu policy cho phép.

Handler quyết định các thông tin đó được chuyển thành timer, span hoặc telemetry output nào.

Không nên đặt logic business trong convention hoặc logic export trong context.

## 4. Chọn context type riêng cho business Observation

Một convention có thể làm việc với một context type chuyên biệt. Điều này giúp tránh việc convention vô tình áp dụng cho mọi Observation trong ứng dụng.

Ví dụ, định nghĩa context cho một business task:

~~~java
package com.example.ai.observability;

import io.micrometer.observation.Observation;

public final class BusinessTaskContext extends Observation.Context {

    public enum Workflow {
        SUPPORT_ANSWER,
        ORDER_LOOKUP,
        POLICY_SUMMARY
    }

    public enum Scenario {
        RAG,
        TOOL,
        RAG_TOOL,
        NO_CONTEXT
    }

    public enum ModelRole {
        GENERATOR,
        JUDGE,
        EMBEDDING
    }

    private final Workflow workflow;
    private final Scenario scenario;
    private final ModelRole modelRole;
    private final String promptRevision;
    private final String executionReference;

    public BusinessTaskContext(
            Workflow workflow,
            Scenario scenario,
            ModelRole modelRole,
            String promptRevision,
            String executionReference) {
        this.workflow = require(workflow, "workflow");
        this.scenario = require(scenario, "scenario");
        this.modelRole = require(modelRole, "modelRole");
        this.promptRevision = requireText(promptRevision, "promptRevision");
        this.executionReference =
                requireText(executionReference, "executionReference");
    }

    public Workflow workflow() {
        return workflow;
    }

    public Scenario scenario() {
        return scenario;
    }

    public ModelRole modelRole() {
        return modelRole;
    }

    public String promptRevision() {
        return promptRevision;
    }

    public String executionReference() {
        return executionReference;
    }

    private static <T> T require(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value;
    }
}
~~~

Dùng enum cho các thuộc tính cần làm metric tags giúp tập giá trị được kiểm soát. Prompt revision và run reference là dữ liệu có thể thay đổi theo từng lần chạy, vì vậy ví dụ giữ chúng riêng để convention đưa vào high-cardinality values nếu được phép.

Không đưa raw prompt, user ID, email, order reference hoặc nội dung document vào context chỉ để convention xuất ra telemetry.

## 5. Viết BusinessTaskObservationConvention

Micrometer convention sử dụng context để tạo metadata. Ví dụ:

~~~java
package com.example.ai.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import java.util.Locale;

public final class BusinessTaskObservationConvention
        implements ObservationConvention<BusinessTaskContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof BusinessTaskContext;
    }

    @Override
    public String getName() {
        return "app.ai.business.task";
    }

    @Override
    public String getContextualName(BusinessTaskContext context) {
        return switch (context.workflow()) {
            case SUPPORT_ANSWER -> "support-answer";
            case ORDER_LOOKUP -> "order-lookup";
            case POLICY_SUMMARY -> "policy-summary";
        };
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            BusinessTaskContext context) {
        return KeyValues.of(
            KeyValue.of("workflow", context.workflow().name().toLowerCase(Locale.ROOT)),
            KeyValue.of("scenario", context.scenario().name().toLowerCase(Locale.ROOT)),
            KeyValue.of("model_role", context.modelRole().name().toLowerCase(Locale.ROOT))
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            BusinessTaskContext context) {
        return KeyValues.of(
            KeyValue.of("prompt.revision", context.promptRevision()),
            KeyValue.of("execution.reference", context.executionReference())
        );
    }
}
~~~

### Vì sao các method được thiết kế như vậy?

- supportsContext chỉ nhận BusinessTaskContext, không nhận mọi Observation.Context.
- getName trả về một tên ổn định cho loại business operation.
- getContextualName dùng mapping đóng, không ghép user input vào tên span.
- getLowCardinalityKeyValues chỉ trả enum values có tập hữu hạn.
- getHighCardinalityKeyValues giữ revision/reference để điều tra trace, không dùng làm Prometheus labels.

Nếu context không phải BusinessTaskContext, convention không nên cố ép kiểu hoặc tự suy đoán thuộc tính.

### Không gắn terminal outcome vào convention khởi tạo parent span

Khi Observation bắt đầu, kết quả cuối cùng của workflow thường chưa tồn tại. Nếu tạo context với outcome mặc định là success, trace và timer có thể mang nhãn sai khi tác vụ sau đó timeout hoặc bị reject.

Convention của parent task nên chứa thuộc tính đã biết lúc bắt đầu như workflow, scenario, model role và prompt revision. Ghi terminal outcome bằng counter/event tại điểm kết thúc, hoặc dùng một completion record riêng có lifecycle ngắn. Exception vẫn được ghi qua Observation error lifecycle.

Ví dụ metric outcome có vocabulary đóng:

~~~text
app.ai.business.task.completed
  workflow=support_answer
  outcome=success|abstained|rejected|not_found|error|timeout
~~~

Không dùng raw exception message làm tag. Nếu cần outcome trong trace, cập nhật context theo lifecycle API được phiên bản Micrometer hỗ trợ và kiểm tra handler/exporter đọc giá trị ở thời điểm nào; đừng giả định convention sẽ tự tính lại tags sau khi start.

## 6. Low-cardinality và high-cardinality: quyết định trước khi thêm key

Đừng chọn cardinality dựa trên tên field. Hãy xem số lượng giá trị có thể xuất hiện và backend sẽ sử dụng field đó ra sao.

| Attribute | Phân loại đề xuất | Lý do |
|---|---|---|
| workflow | Low | Tập workflow đã đăng ký |
| scenario | Low | RAG/tool/no-context |
| model_role | Low | generator/judge/embedding |
| outcome | Low | Enum kết quả |
| environment | Low | dev/staging/prod |
| prompt revision | High hoặc trace metadata | Có thể tăng theo lần phát hành |
| model deployment revision | High hoặc trace metadata | Thay đổi theo rollout |
| evaluation run reference | High | Gần như mỗi run có một giá trị |
| case ID | High, nếu policy cho phép | Hữu ích cho trace drilldown nhưng có thể nhạy cảm |
| raw prompt | Không xuất | Nội dung người dùng |
| user/account ID | Không xuất trực tiếp | PII/identifier nhạy cảm |

High-cardinality không có nghĩa là được phép ghi mọi thứ. Trace storage cũng cần retention, access control và redaction.

### Một nguyên tắc hữu ích

- Metrics trả lời xu hướng tổng hợp, nên tags phải có tập giá trị nhỏ.
- Traces trả lời điều gì xảy ra trong một execution cụ thể, có thể mang một số attributes biến thiên.
- Business database lưu dữ liệu nghiệp vụ đầy đủ theo access policy riêng.

Đừng biến metrics backend thành nơi lưu dữ liệu từng request.

## 7. Đăng ký convention trực tiếp cho một Observation

Với custom business operation, có thể tạo observation bằng convention và context supplier:

~~~java
package com.example.ai.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;

import org.springframework.stereotype.Component;

@Component
public class BusinessTaskObservationFactory {

    private final ObservationRegistry registry;
    private final BusinessTaskObservationConvention convention;

    public BusinessTaskObservationFactory(
            ObservationRegistry registry,
            BusinessTaskObservationConvention convention) {
        this.registry = registry;
        this.convention = convention;
    }

    public <T> T observe(
            BusinessTaskContext context,
            Supplier<T> work) {

        Observation observation = Observation.createNotStarted(
                convention,
                () -> context,
                registry);

        return observation.observe(work);
    }
}
~~~

Cách này làm rõ convention áp dụng cho observation nào: caller cung cấp context đúng type và factory truyền convention tường minh.

Không tạo context khác với operation thực tế. Nếu outcome chỉ biết sau khi xử lý xong, ghi terminal outcome bằng counter/event riêng với vocabulary đóng.

Đừng tạo một Observation mới chỉ để ghi kết quả cuối rồi tính duration hai lần.

## 8. Đăng ký convention với ObservationRegistry

Khi muốn registry chọn convention dựa trên context, có thể đăng ký convention trong ObservationConfig. Trong Spring Boot, dùng ObservationRegistryCustomizer để áp dụng cấu hình cho registry do Boot quản lý.

~~~java
package com.example.ai.observability;

import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BusinessObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry>
    businessTaskConventionCustomizer(
            BusinessTaskObservationConvention convention) {

        return registry -> registry.observationConfig()
                .observationConvention(convention);
    }
}
~~~

Đăng ký registry-level phù hợp khi nhiều call sites cùng sử dụng context type và convention. Convention phải có supportsContext chính xác để không ảnh hưởng observations của Spring MVC, database, messaging hoặc Spring AI component khác.

API customizer và cách registry chọn convention có thể khác giữa các phiên bản Spring Boot/Micrometer. Nếu dependency version của ứng dụng không có method/overload trên, kiểm tra API đúng BOM và dùng factory truyền convention tường minh ở mục trước. Không tự tạo một registry riêng chỉ để né cấu hình của Spring Boot.

### Không đăng ký trùng lặp

Chọn một cách làm chủ đạo:
- factory truyền convention trực tiếp; hoặc
- registry-level convention selection cho custom context.

Không thêm cùng convention nhiều lần vào registry. Cũng không vừa đăng ký global vừa thêm convention lặp lại cho cùng một observation nếu không có chủ đích.

## 9. Convention selection và nhiều convention cùng tồn tại

Một ứng dụng có thể có nhiều convention:

- business task convention;
- convention cho evaluation case;
- convention cho một integration nội bộ;
- convention tùy chỉnh cho một component có sẵn.

Mỗi convention cần supportsContext cụ thể. Tránh một convention generic luôn trả true vì nó có thể chiếm các context không thuộc phạm vi của nó.

Ví dụ:

| Convention | Context type |
|---|---|
| BusinessTaskObservationConvention | BusinessTaskContext |
| EvaluationCaseObservationConvention | EvaluationCaseContext |
| InternalProviderObservationConvention | ProviderCallContext |

Nếu hai convention cùng support một context, việc lựa chọn phụ thuộc thứ tự/selection semantics của phiên bản registry. Hãy tránh overlap hoặc định nghĩa rõ precedence bằng cấu hình được hỗ trợ và integration test. Không dựa vào thứ tự đăng ký tình cờ.

## 10. Chuẩn hóa key names và value vocabulary

Một schema metadata tốt cần:
- key names thống nhất;
- vocabulary có tài liệu;
- value casing ổn định;
- mapping cho legacy values;
- owner cho từng key;
- revision khi semantics thay đổi.

Ví dụ schema:

| Key | Type | Allowed values / format | Cardinality |
|---|---|---|---|
| workflow | String | support_answer, order_lookup, policy_summary | Low |
| scenario | String | rag, tool, rag_tool, no_context | Low |
| model_role | String | generator, judge, embedding | Low |
| outcome | String | success, abstained, rejected, not_found, error, timeout | Low |
| prompt.revision | String | revision ID | High |
| evaluation.run.reference | String | opaque reference | High |

Đừng dùng cùng key model để lúc thì lưu provider, lúc thì lưu role, lúc thì lưu model ID. Tách:
- model.provider;
- model.role;
- model.family;
- model.revision.

Chỉ đưa các field cần thiết vào telemetry; không cần export toàn bộ manifest.

## 11. Tránh duplicate attributes và conflicting ownership

Khi application code, convention, ObservationFilter và handler cùng bổ sung key-values, một key có thể xuất hiện nhiều lần hoặc bị ghi đè tùy API/handler.

Quy định ownership:

| Metadata | Nơi chịu trách nhiệm |
|---|---|
| workflow/scenario | BusinessTaskContext + convention |
| prompt/model revision | Context + convention theo trace policy |
| trace/span IDs | Tracing handler |
| service.name/environment | Resource/registry configuration |
| exception type | Observation error lifecycle/handler |
| terminal business outcome | Application outcome policy |
| exporter-specific labels | Exporter configuration |

Không để mỗi layer tự đặt lại cùng một key. Nếu muốn thay semantics, version schema và cập nhật dashboard/alerts cùng lúc.

### ObservationFilter có thay thế convention không?

Không. Convention xác định metadata theo context type và observation kind. Filter phù hợp để áp dụng một biến đổi chung sau khi observation được tạo, chẳng hạn bổ sung một key chung hoặc chuẩn hóa context. Dùng convention cho taxonomy của loại operation; dùng filter cho cross-cutting transformation có phạm vi rõ.

## 12. Context nên chứa gì và không nên chứa gì?

Context nên chứa dữ liệu cần thiết để mô tả operation, không phải một bản sao của request.

Nên có:
- enum workflow/scenario/role/outcome;
- revision IDs cần cho trace;
- operation mode;
- retry classification;
- bounded numeric buckets;
- opaque correlation reference đã được phê duyệt.

Không nên có:
- raw prompt;
- toàn bộ conversation history;
- document content;
- embedding vector;
- credentials/secrets;
- full tool arguments;
- user profile;
- dữ liệu thanh toán/đơn hàng.

Một context nhỏ dễ kiểm thử, ít rủi ro và ổn định hơn khi schema thay đổi.

## 13. Bổ sung attributes cho RAG workflow

Một RAG business task có thể cần các thuộc tính:

| Stage | Low-cardinality | Trace metadata |
|---|---|---|
| Retrieval | retriever_type, search_mode | index revision |
| Reranking | reranker_type | reranker revision |
| Context assembly | context_mode, truncation_outcome | context reference |
| Generation | model_role, response_mode | prompt revision |
| Validation | validator_type, validation_outcome | rubric revision |

Ví dụ convention có thể bổ sung:
- scenario=rag;
- retrieval.mode=hybrid;
- context.outcome=truncated.

retrieval.mode và context.outcome chỉ nên là low-cardinality nếu chúng đến từ enum/configuration có tập giá trị hữu hạn. Nếu giá trị được lấy trực tiếp từ query/filter expression, không đưa vào metric tags.

Không gắn document IDs hoặc raw search query thành low-cardinality keys.

## 14. Bổ sung attributes cho tool workflow

Tool calling cần phân biệt:
- tool được chọn;
- tool execution có thành công không;
- validation arguments có pass không;
- tool result có được dùng để trả lời không;
- workflow có side effect hay read-only.

Một schema gợi ý:

| Key | Example | Cardinality |
|---|---|---|
| tool.name | order_status | Low nếu allowlist |
| tool.mode | read_only / mutation | Low |
| tool.outcome | success / rejected / error | Low |
| tool.schema.revision | v4 | Trace metadata |
| tool.execution.reference | opaque reference | High |
| tool.argument.validation | valid / invalid | Low |

Nếu có hàng trăm dynamic tool names do plugin/user tạo, không mặc định coi tool.name là low-cardinality. Phải kiểm tra số lượng tool và policy trước.

Không lưu raw arguments vào attributes. Với mutation, lưu audit event trong hệ thống nghiệp vụ theo policy, rồi chỉ giữ reference đã bảo vệ trong trace.

## 15. Bổ sung attributes cho evaluation observations

Evaluation case thường cần metadata khác serving request:

- evaluation suite;
- dataset revision;
- metric name;
- evaluator role;
- judge revision;
- rubric revision;
- outcome;
- severity.

Ví dụ:

~~~text
app.ai.evaluation.case
  low-cardinality:
    suite=support_regression
    metric=fact_check
    evaluator_role=judge
    outcome=fail
  high-cardinality:
    dataset.revision=support-v6
    evaluation.run.reference=run-opaque-042
    case.reference=case-opaque-013
~~~

Dataset revision có thể có tập giá trị tương đối nhỏ nhưng thay đổi theo thời gian. Quyết định low/high phải theo backend và cardinality budget thực tế. Nếu cần lọc theo revision trong dashboard, có thể dùng bounded release label hoặc report store thay vì gắn mọi revision vào metric series vĩnh viễn.

## 16. Spring AI built-in observations có convention riêng

Custom business convention không tự động sửa metadata của mọi observation do Spring AI tạo.

Phân biệt hai phạm vi:

1. **Business Observation:** do ứng dụng tạo, mô tả workflow tổng thể.
2. **Spring AI component Observation:** do framework tạo cho ChatClient, ChatModel, EmbeddingModel, VectorStore, tool hoặc advisor tùy component/version.

Nếu muốn bổ sung metadata cho component observation:
- kiểm tra extension point/convention interface mà đúng phiên bản Spring AI cung cấp;
- sử dụng convention type tương ứng của component;
- xác minh supportsContext và attributes được exporter nhận;
- không thay convention mặc định bằng một convention generic không tương thích;
- kiểm tra việc auto-configuration có còn áp dụng convention mong muốn.

Không giả định một BusinessTaskObservationConvention có thể nhận ChatModelObservationContext. Nó được thiết kế cho BusinessTaskContext; hai context có trách nhiệm riêng.

## 17. Convention và Spring Boot configuration

Spring Boot có thể tự cấu hình ObservationRegistry, handlers và tracing bridge khi dependency phù hợp có mặt. Ứng dụng nên dùng registry do container quản lý.

Một cấu hình có thể có:
- ObservationRegistryCustomizer;
- convention beans;
- observation handlers;
- observation filters/predicates;
- MeterRegistry và tracing exporter.

Convention là metadata policy, không phải exporter. Nếu muốn gửi trace tới backend, cần tracing bridge/exporter. Nếu muốn có metrics, cần meter registry/exporter tương ứng.

### Cấu hình cần xác minh

- Actuator/Observation infrastructure có trên classpath.
- Convention bean được tạo và đăng ký đúng registry.
- Custom context supplier thực sự được dùng.
- Convention support context type mong đợi.
- Low/high cardinality values xuất hiện ở đúng backend.
- Không có duplicate key/span.
- Sampling và retention policy phù hợp.

Không expose metrics/tracing configuration hoặc actuator endpoints ra public network nếu chưa có authentication/network controls.

## 18. Convention trong async và reactive workflows

Convention chỉ tạo metadata từ context. Nó không tự giải quyết context propagation.

Khi task chuyển qua executor:
- context phải được truyền qua Micrometer Context Propagation;
- child observations phải được tạo trong propagated scope;
- không dùng convention để nhét parent span ID thủ công.

Với CompletableFuture, dùng executor có ContextPropagatingTaskDecorator hoặc cơ chế propagation tương thích.

Với Reactor:
- giữ observation/tracing context trong Reactor Context;
- dùng reactive instrumentation hỗ trợ subscription lifecycle;
- không dùng synchronous Observation wrapper quanh publisher rồi nghĩ convention sẽ sửa lifecycle.

Convention có thể thêm workflow/scenario attributes cho các operation sau khi context được khôi phục; nó không thể tự nối hai trace đã mất parent context.

## 19. Kiểm thử convention độc lập

Convention là một class Java thuần, nên có thể test trực tiếp:
- context type được support;
- observation name ổn định;
- contextual name đúng mapping;
- low-cardinality values chỉ chứa enum vocabulary;
- high-cardinality keys đúng schema;
- không có prompt, PII hoặc raw IDs;
- null/invalid context bị từ chối từ constructor.

### File BusinessTaskObservationConventionTest.java

~~~java
package com.example.ai.observability;

import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import org.junit.jupiter.api.Test;

class BusinessTaskObservationConventionTest {

    private final BusinessTaskObservationConvention convention =
            new BusinessTaskObservationConvention();

    private BusinessTaskContext context() {
        return new BusinessTaskContext(
                BusinessTaskContext.Workflow.SUPPORT_ANSWER,
                BusinessTaskContext.Scenario.RAG,
                BusinessTaskContext.ModelRole.GENERATOR,
                "prompt-v12",
                "run-ref-042");
    }

    @Test
    void supportsOnlyBusinessTaskContext() {
        assertTrue(convention.supportsContext(context()));
        assertFalse(convention.supportsContext(new Observation.Context()));
    }

    @Test
    void providesStableNameAndContextualName() {
        assertEquals("app.ai.business.task", convention.getName());
        assertEquals("support-answer",
                convention.getContextualName(context()));
    }

    @Test
    void addsOnlyBoundedBusinessDimensionsToLowCardinalityValues() {
        KeyValues expected = KeyValues.of(
            KeyValue.of("workflow", "support_answer"),
            KeyValue.of("scenario", "rag"),
            KeyValue.of("model_role", "generator")
        );

        assertEquals(expected,
                convention.getLowCardinalityKeyValues(context()));
    }

    @Test
    void keepsRevisionAndExecutionReferenceInHighCardinalityValues() {
        KeyValues expected = KeyValues.of(
            KeyValue.of("prompt.revision", "prompt-v12"),
            KeyValue.of("execution.reference", "run-ref-042")
        );

        assertEquals(expected,
                convention.getHighCardinalityKeyValues(context()));
    }
}
~~~

Test trên xác minh convention output. Nó chưa chứng minh registry/tracing exporter thực sự áp dụng convention; phần đó cần integration test.

## 20. Kiểm thử convention được áp dụng qua ObservationRegistry

Một integration-style unit test có thể tạo registry, đăng ký convention và kiểm tra observation context được chọn.

~~~java
package com.example.ai.observability;

import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

class BusinessConventionRegistryTest {

    @Test
    void registeredConventionAppliesToMatchingContext() {
        ObservationRegistry registry = ObservationRegistry.create();
        BusinessTaskObservationConvention convention =
                new BusinessTaskObservationConvention();

        registry.observationConfig().observationConvention(convention);

        AtomicReference<Observation.Context> observedContext =
                new AtomicReference<>();
        registry.observationConfig().observationHandler(
            new ObservationHandler<Observation.Context>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onStart(Observation.Context context) {
                    observedContext.set(context);
                }
            });

        BusinessTaskContext context = new BusinessTaskContext(
                BusinessTaskContext.Workflow.ORDER_LOOKUP,
                BusinessTaskContext.Scenario.TOOL,
                BusinessTaskContext.ModelRole.GENERATOR,
                "prompt-v5",
                "run-ref-043");

        Observation.createNotStarted(
                "app.ai.business.task",
                () -> context,
                registry)
            .observe(() -> "done");

        assertNotNull(observedContext.get());
        assertEquals("app.ai.business.task", observedContext.get().getName());
        assertEquals(
            KeyValues.of(
                KeyValue.of("workflow", "order_lookup"),
                KeyValue.of("scenario", "tool"),
                KeyValue.of("model_role", "generator")
            ),
            observedContext.get().getLowCardinalityKeyValues());
        assertEquals(
            KeyValues.of(
                KeyValue.of("prompt.revision", "prompt-v5"),
                KeyValue.of("execution.reference", "run-ref-043")
            ),
            observedContext.get().getHighCardinalityKeyValues());
    }
}
~~~

API registry-level convention selection và overload nhận context supplier phải được xác nhận với Micrometer version trong BOM. Nếu version đang dùng không có overload đó, dùng Observation.createNotStarted(convention, () -> context, registry) để gắn convention tường minh; giữ test selection phù hợp API thực tế.

## 21. Convention versioning và migration

Khi thêm, đổi hoặc bỏ một key, dashboard/alert có thể bị ảnh hưởng.

Ví dụ:
- v1 dùng workflow=support;
- v2 đổi thành workflow=support_answer;
- v1 dùng modelRole;
- v2 chuẩn hóa thành model_role.

Không đổi semantics âm thầm. Hãy:
1. ghi schema revision;
2. cập nhật convention;
3. cập nhật dashboard/alerts;
4. xác định thời gian dual-read/dual-write nếu cần;
5. kiểm tra cardinality mới;
6. bỏ key cũ sau migration window.

Không tạo key mới cho cùng một ý nghĩa chỉ vì một team muốn naming riêng.

## 22. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Convention supportsContext luôn true | Áp dụng nhầm observation | Check custom context type |
| Đưa request ID vào low-cardinality | Cardinality tăng không giới hạn | Chỉ dùng trace reference có kiểm soát |
| Ghi raw prompt vào high-cardinality | Rò rỉ dữ liệu và storage tăng | Không export prompt |
| Trả dynamic observation name | Metrics bị phân mảnh | Name ổn định, contextual name từ enum |
| Dùng một key cho nhiều nghĩa | Dashboard không nhất quán | Schema ownership và key riêng |
| Đăng ký convention nhiều lần | Metadata lặp hoặc selection khó hiểu | Một registration path rõ ràng |
| Convention cố gọi provider | Tăng latency, side effect | Convention chỉ map context |
| Nhầm convention với handler | Không export được telemetry | Cấu hình handlers/exporters riêng |
| Nghĩ business convention sửa Spring AI spans | Component metadata vẫn giữ convention riêng | Dùng extension point đúng component |
| Đưa prompt revision vào metric labels vô hạn | Time-series tăng theo release | Trace metadata hoặc bounded release dimension |
| Thay key mà không version | Alert/dashboard hỏng | Convention/schema migration |
| Không test context type | Convention áp dụng ngoài ý muốn | Unit + registry integration tests |

## 23. Bài thực hành: convention cho business task và RAG evaluation

Xây hai context/convention:
1. BusinessTaskContext + BusinessTaskObservationConvention.
2. EvaluationCaseContext + EvaluationCaseObservationConvention.

### Yêu cầu

- Mỗi convention có observation name riêng.
- supportsContext chỉ nhận đúng context type.
- Workflow/scenario là low-cardinality enum của business task; outcome là low-cardinality value cho completion event sau khi đã có kết quả.
- Dataset revision, prompt revision và run reference được phân loại có chủ đích.
- Không đưa raw prompt, case text, PII hoặc tool arguments vào telemetry.
- Convention được đăng ký qua registry hoặc factory rõ ràng.
- Có unit test cho key-values.
- Có registry test để xác nhận convention selection.
- Có integration trace để xác minh attributes xuất hiện đúng span.
- Có cardinality review trước khi bật trên production traffic.

### Ví dụ kết quả mong đợi

~~~text
app.ai.business.task
  low-cardinality:
    workflow=support_answer
    scenario=rag_tool
    model_role=generator
  high-cardinality:
    prompt.revision=prompt-v12

app.ai.business.task.completed
  workflow=support_answer
  outcome=success

app.ai.evaluation.case
  low-cardinality:
    suite=support_regression
    metric=fact_check
    evaluator_role=judge
    outcome=fail
  high-cardinality:
    dataset.revision=support-v6
    evaluation.run.reference=run-opaque-042
    case.reference=case-opaque-013
~~~

Các giá trị trên là minh họa. Terminal outcome được ghi trong completion event sau khi tác vụ kết thúc; case.reference hoặc run reference chỉ xuất vào trace khi policy cho phép và cần có retention phù hợp.

## 24. Quy trình review convention trước khi merge

1. Xác định context type và owner.
2. Liệt kê mọi key-value mà convention trả về.
3. Phân loại low/high cardinality.
4. Kiểm tra vocabulary và số lượng giá trị tối đa.
5. Kiểm tra dữ liệu nhạy cảm.
6. Xác nhận convention chỉ support context mong đợi.
7. Kiểm tra registry/factory registration.
8. Chạy unit tests và integration trace tests.
9. Xem thử metric series count và trace attributes ở staging.
10. Review dashboard/alert impact.
11. Ghi schema revision và migration plan.
12. Chỉ bật production sau khi owner chấp thuận.

### Review questions

- Mỗi key trả lời câu hỏi vận hành nào?
- Ai sở hữu semantics của key?
- Giá trị có bị lấy trực tiếp từ user input không?
- Số lượng series tối đa có thể phát sinh là bao nhiêu?
- Key có chứa PII, secret hoặc business data không?
- Convention có áp dụng nhầm component observations không?
- Khi đổi value vocabulary, dashboard cũ xử lý ra sao?

## 25. Checklist trước khi đăng ký convention

- [ ] Có context type riêng và constructor validation.
- [ ] supportsContext kiểm tra đúng context type.
- [ ] Observation name ổn định.
- [ ] Contextual name dùng mapping có kiểm soát.
- [ ] Low-cardinality keys chỉ chứa vocabulary hữu hạn.
- [ ] High-cardinality keys có use case trace và retention rõ.
- [ ] Không export raw prompt, PII, secrets, document text hoặc raw tool arguments.
- [ ] Key names có schema/owner thống nhất.
- [ ] Không duplicate attributes giữa context, convention và filter.
- [ ] Convention không chứa business logic hoặc network calls.
- [ ] Convention được đăng ký một lần theo cơ chế rõ ràng.
- [ ] Business convention không vô tình thay Spring AI built-in conventions.
- [ ] Async/reactive context propagation được kiểm tra riêng.
- [ ] Unit tests kiểm tra name, contextual name và KeyValues.
- [ ] Registry/integration tests xác nhận convention được chọn.
- [ ] Cardinality được review ở staging.
- [ ] Dashboard/alerts có kế hoạch migration khi schema thay đổi.
- [ ] Observation handlers/exporters được cấu hình riêng và an toàn.
- [ ] Có tài liệu mô tả semantics cho từng key.

## Tài liệu tham khảo

1. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation lifecycle, context, conventions và handlers.
2. [Micrometer Observation API](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html): tạo Observation và sử dụng ObservationConvention.
3. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, customizers, metrics và tracing.
4. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): instrumentation và observations trong Spring AI.
5. [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): truyền context qua ThreadLocal và reactive contexts.
6. [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/): span context, attributes và trace lifecycle.
7. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong telemetry/logging.

> **Ghi nhớ:** Context lưu dữ liệu của operation; ObservationConvention quyết định dữ liệu nào trở thành tên và attributes; handler quyết định cách ghi nhận và export. Hãy dùng context có kiểu rõ ràng, convention có phạm vi hẹp, low-cardinality tags có vocabulary cố định và trace attributes được kiểm soát.
