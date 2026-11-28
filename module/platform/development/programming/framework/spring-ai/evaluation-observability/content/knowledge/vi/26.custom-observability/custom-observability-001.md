# Tạo Observation cho toàn bộ tác vụ nghiệp vụ

> **Chương:** Quan sát tùy chỉnh
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ. Đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm chất lượng qua từng phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. API chi tiết có thể thay đổi theo dependency/BOM thực tế; ví dụ dưới đây dùng Micrometer Observation API và cần đối chiếu với phiên bản đang được project quản lý.

## 1. Vì sao cần Observation ở cấp tác vụ nghiệp vụ?

Một request hỏi đáp RAG có thể đi qua nhiều thành phần:

1. Nhận câu hỏi và xác định workflow.
2. Nạp lịch sử hội thoại và dựng prompt.
3. Tạo embedding cho query.
4. Tìm tài liệu trong VectorStore.
5. Lọc, rerank và ghép context.
6. Gọi ChatModel để tạo câu trả lời.
7. Gọi một hoặc nhiều tools.
8. Đọc kết quả tool và gọi model thêm lần nữa.
9. Kiểm tra citation, factuality hoặc policy.
10. Trả response về client.

Spring AI và các integration có thể tạo observation cho những lần gọi model, embedding, vector store hoặc tool đã được instrument. Những observation đó trả lời được câu hỏi như “ChatModel call mất bao lâu?” hoặc “VectorStore operation có lỗi không?”.

Nhưng người vận hành còn cần biết **toàn bộ tác vụ trả lời câu hỏi này đã diễn ra thế nào**:

- Workflow nào được thực thi?
- Tác vụ bắt đầu và kết thúc ở đâu?
- Tổng thời gian người dùng chờ là bao lâu?
- Có bao nhiêu lần retrieval, model call, tool call và retry?
- Lỗi xảy ra ở stage nào?
- Tác vụ hoàn thành, từ chối, timeout hay thất bại?
- Các stage con có liên hệ với cùng một business request không?

Đây là lý do cần một Observation bao quanh **ranh giới nghiệp vụ**. Observation cấp tác vụ đóng vai trò parent; những observation ở tầng framework/model/retrieval/tool là các operation con khi context được truyền đúng.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt Observation cấp business task với observation của từng model/tool operation.
2. Chọn ranh giới bắt đầu và kết thúc cho một tác vụ nghiệp vụ.
3. Tạo custom Observation bằng ObservationRegistry.
4. Tổ chức parent/child observations cho RAG và tool calling.
5. Đặt tên observation và low-cardinality tags có kiểm soát.
6. Phân biệt metric dimensions với trace-only attributes.
7. Ghi nhận exception, timeout và business outcome.
8. Truyền observation context qua executor, async và reactive flows.
9. Tích hợp custom observation với Spring AI instrumentation.
10. Kiểm thử observation lifecycle và phát hiện context bị mất.
11. Tránh duplicate spans, high-cardinality metrics và rò rỉ dữ liệu.
12. Dùng traces để điều tra một business task qua nhiều thành phần.

## 2. Observation, metric, span và trace khác nhau thế nào?

Các khái niệm này liên quan nhưng không đồng nghĩa.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Observation | Abstraction của Micrometer để ghi nhận một operation | app.ai.business.task |
| ObservationRegistry | Registry điều phối lifecycle, handlers, filters và conventions | Registry được Spring Boot cấu hình |
| Observation.Context | Context chứa metadata và trạng thái của operation | Workflow, error, key-values |
| ObservationHandler | Thành phần nhận lifecycle callbacks | Meter handler, tracing handler |
| Meter/metric | Số liệu tổng hợp theo thời gian | Count, duration, error rate |
| Span | Một operation có thời gian trong distributed trace | Business task hoặc model call |
| Trace | Cây/cấu trúc các spans liên quan | Một request RAG gồm retrieval, model và tools |

Micrometer Observation là lớp instrumentation thống nhất. Các handlers quyết định observation được xuất ra đâu và theo hình thức nào. Khi có tracing handler, một Observation có thể tạo span. Khi có meter handler, observation có thể đóng góp vào timer/counter.

Không phải mọi Observation đều tự động trở thành span hoặc metric. Điều đó phụ thuộc handlers, registry và cấu hình ứng dụng.

### Ví dụ cấu trúc

~~~text
Trace: support-answer request
└── app.ai.business.task
    ├── app.ai.history.load
    ├── app.ai.rag.retrieve
    │   ├── embedding operation
    │   └── vector store operation
    ├── chat model operation
    ├── app.ai.tool.workflow
    │   ├── tool execution
    │   └── chat model operation
    └── app.ai.answer.validate
~~~

Đây là cấu trúc khái niệm. Tên span con thực tế do Spring AI, provider integration và custom instrumentation quyết định.

## 3. Chọn đúng ranh giới của business task

Một Observation nghiệp vụ nên bao phủ một đơn vị công việc mà product owner hoặc operator hiểu được.

Ví dụ:
- answer_support_question: xử lý một câu hỏi hỗ trợ.
- resolve_order_status: tra cứu trạng thái đơn hàng.
- summarize_policy_document: tóm tắt tài liệu chính sách.
- evaluate_rag_case: chạy một case evaluation offline.
- execute_refund_workflow: xử lý một workflow hoàn tiền có tool side effect.

### Điểm bắt đầu

Bắt đầu khi ứng dụng chấp nhận responsibility cho tác vụ, thường tại application service/use-case boundary sau khi đã xác định request context.

### Điểm kết thúc

Kết thúc khi:
- response đã được tạo xong;
- workflow hoàn tất;
- workflow từ chối theo policy;
- lỗi không thể phục hồi được trả ra;
- timeout/deadline kết thúc tác vụ.

Nếu task có background continuation sau khi HTTP response đã trả về, cần quyết định đó là một task riêng có correlation/link tới request ban đầu, hay vẫn là một trace dài. Không kéo một span HTTP mở hàng phút chỉ vì một job hậu xử lý còn chạy.

### Đơn vị quan sát cần ổn định

Một business task ID nên đại diện cho một lần thực thi nghiệp vụ. Retry của cùng một task có thể là attempt/child operation riêng, nhưng không tạo ra một business task mới nếu semantics không thay đổi.

## 4. Thiết kế taxonomy cho custom observations

Tên observation phải ổn định, có cấu trúc và không chứa dữ liệu động.

Ví dụ:

| Observation name | Boundary |
|---|---|
| app.ai.business.task | Toàn bộ tác vụ AI nghiệp vụ |
| app.ai.prompt.prepare | Dựng prompt/history |
| app.ai.rag.retrieve | Retrieval pipeline |
| app.ai.rag.context.assemble | Ghép context |
| app.ai.answer.validate | Kiểm tra answer |
| app.ai.tool.workflow | Một bước điều phối tool ở cấp nghiệp vụ |
| app.ai.evaluation.case | Một case evaluation offline |

Không đặt tên như:
- answer_for_customer_123;
- retrieve_policy_2026_11_27;
- model_call_gpt_request_123.

Tên động làm cardinality tăng, khó tổng hợp metrics và có thể đưa dữ liệu nhạy cảm vào telemetry.

### Phân biệt name và contextual name

- Observation name là tên kỹ thuật ổn định dùng cho instrumentation.
- Contextual name là nhãn dễ đọc hơn cho trace/span nếu handler hỗ trợ.

Có thể giữ app.ai.business.task làm name và đặt contextual name answer-support-question. Không đưa câu hỏi thật hoặc user ID vào contextual name.

## 5. Low-cardinality và high-cardinality key-values

Đây là quyết định quan trọng khi thiết kế custom Observation.

### Low-cardinality

Dùng cho các dimension có tập giá trị hữu hạn, ổn định:

- workflow: support_answer, order_lookup, policy_summary;
- operation: answer, retrieve, validate;
- outcome: success, error, rejected, timeout;
- model_role: generator, judge, embedding;
- scenario: rag, tool, no_context;
- environment: dev, staging, prod.

Các giá trị này phù hợp để làm metric tags khi đã kiểm soát cardinality.

### High-cardinality

Dùng cho dữ liệu định danh phục vụ điều tra trace, khi policy cho phép:

- evaluation.run_id;
- case.reference;
- correlation.reference;
- prompt.revision;
- corpus.revision.

High-cardinality values có thể hữu ích trên trace nhưng không nên được xuất thành metric labels không giới hạn.

### Không đưa dữ liệu nhạy cảm vào telemetry

Không gắn:
- raw user prompt;
- email, số điện thoại, account ID;
- access token, API key, session cookie;
- tool arguments có thông tin cá nhân;
- toàn bộ retrieved document content;
- raw model response.

Nếu cần liên kết tới bản ghi nghiệp vụ, dùng opaque reference đã được policy cho phép và giữ dữ liệu gốc trong hệ thống có access control/retention riêng.

## 6. Tạo Observation bằng ObservationRegistry

Spring Boot có thể cung cấp ObservationRegistry đã được cấu hình cùng Actuator/Micrometer. Inject registry này vào application service.

Ví dụ tối thiểu:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class BusinessTaskObserver {

    private final ObservationRegistry observationRegistry;

    public BusinessTaskObserver(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public <T> T observe(
            String workflow,
            String operation,
            java.util.function.Supplier<T> work) {

        Observation observation = Observation
                .createNotStarted("app.ai.business.task", observationRegistry)
                .contextualName("ai-business-task")
                .lowCardinalityKeyValue("workflow", workflow)
                .lowCardinalityKeyValue("operation", operation);

        return observation.observe(work);
    }
}
~~~

Observation.createNotStarted(...) tạo observation gắn với registry. Các key-values được khai báo trước khi bắt đầu. observe(...) quản lý lifecycle start/scope/stop quanh supplier và cho phép exception đi qua lifecycle để handler ghi nhận lỗi.

### Quy tắc quan trọng

- Dùng registry do Spring quản lý trong ứng dụng.
- Không tự tạo ObservationRegistry.create() cho mỗi request.
- Không gọi start() mà quên stop().
- Không mở scope rồi quên đóng.
- Không dùng low-cardinality tag để chứa request ID.
- Không tạo observation tên động theo từng user/case.

Với tác vụ trả về void, có thể dùng overload nhận Runnable nếu phiên bản Micrometer đang dùng hỗ trợ; hoặc trả một giá trị đơn giản từ supplier.

## 7. Bao toàn bộ business use case bằng một Observation

Ví dụ sau minh họa một application service xử lý câu hỏi hỗ trợ bằng RAG.

### File SupportAnswerService.java

~~~java
package com.example.ai.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.document.Document;
import org.springframework.stereotype.Service;

@Service
public class SupportAnswerService {

    private final ObservationRegistry registry;
    private final PolicyRetriever policyRetriever;
    private final ChatClient chatClient;

    public SupportAnswerService(
            ObservationRegistry registry,
            PolicyRetriever policyRetriever,
            ChatClient.Builder chatClientBuilder) {
        this.registry = registry;
        this.policyRetriever = policyRetriever;
        this.chatClient = chatClientBuilder.build();
    }

    public String answer(String question) {
        Observation businessTask = Observation
                .createNotStarted("app.ai.business.task", registry)
                .contextualName("answer-support-question")
                .lowCardinalityKeyValue("workflow", "support_answer")
                .lowCardinalityKeyValue("operation", "answer")
                .lowCardinalityKeyValue("scenario", "rag");

        return businessTask.observe(() -> {
            List<Document> documents = Observation
                    .createNotStarted("app.ai.rag.retrieve", registry)
                    .contextualName("retrieve-policy-context")
                    .lowCardinalityKeyValue("retriever", "policy")
                    .observe(() -> policyRetriever.retrieve(question));

            String context = documents.stream()
                    .map(Document::getText)
                    .reduce("", (left, right) -> left + "\n" + right);

            return Observation
                    .createNotStarted("app.ai.answer.generate", registry)
                    .contextualName("generate-support-answer")
                    .lowCardinalityKeyValue("model_role", "generator")
                    .observe(() -> chatClient.prompt()
                            .system("""
                                Trả lời dựa trên context được cung cấp.
                                Nếu context không đủ, hãy nói rõ giới hạn.
                                """)
                            .user(user -> user.text("""
                                Câu hỏi:
                                {question}

                                Context:
                                {context}
                                """)
                                .param("question", question)
                                .param("context", context))
                            .call()
                            .content());
        });
    }
}
~~~

PolicyRetriever là abstraction của project, không phải class built-in. Đoạn code rút gọn phần prompt/context để làm rõ ranh giới observation.

Khi business observation đang active trong scope, những observations con được tạo trong cùng execution có thể kế thừa parent context qua tracing handler. Nếu asynchronous boundary không truyền context, span con có thể trở thành root hoặc trace khác; cần kiểm tra điều này ở phần context propagation.

Spring AI có thể đã instrument ChatClient/ChatModel/VectorStore. Không bọc lại cùng một operation bằng một custom span trùng tên chỉ để đo duration lần nữa. Hãy tạo business parent và giữ instrumentation có sẵn ở tầng component.

## 8. Tạo child observations cho từng stage

Một business task thường có nhiều stage. Chỉ cần tạo child observation cho stage có ý nghĩa vận hành hoặc cần phân tích riêng.

Ví dụ:

~~~java
List<Document> documents = Observation
        .createNotStarted("app.ai.rag.retrieve", registry)
        .lowCardinalityKeyValue("retriever", "policy")
        .observe(() -> retriever.retrieve(question));

String answer = Observation
        .createNotStarted("app.ai.answer.generate", registry)
        .lowCardinalityKeyValue("model_role", "generator")
        .observe(() -> generateAnswer(question, documents));

ValidationResult validation = Observation
        .createNotStarted("app.ai.answer.validate", registry)
        .lowCardinalityKeyValue("validator", "fact_check")
        .observe(() -> validator.validate(answer, documents));
~~~

Không cần tạo span cho từng phép nối chuỗi hoặc getter. Quá nhiều spans làm trace nặng, tăng chi phí export và khiến operator khó tìm stage quan trọng.

### Chọn child span theo câu hỏi vận hành

Tạo observation khi cần trả lời:
- Stage này có chậm hoặc lỗi độc lập không?
- Có retry riêng không?
- Có dependency/provider riêng không?
- Có cần đo duration/count theo workflow không?
- Có boundary bảo mật hoặc side effect cần audit không?

## 9. Observation cho RAG workflow

Một RAG task có thể gồm các custom stages:

| Stage | Thuộc tính hữu ích |
|---|---|
| Query preparation | query_mode, language |
| Embedding | model role, provider, result |
| Vector retrieval | store type, search mode, top-k bucket |
| Filtering | filter policy, candidate count bucket |
| Reranking | reranker role, candidate count bucket |
| Context assembly | chunk count bucket, token budget bucket |
| Answer generation | model role, prompt revision |
| Grounding validation | validator role, outcome |

### Ví dụ trace

~~~text
app.ai.business.task
  ├── app.ai.prompt.prepare
  ├── app.ai.rag.retrieve
  │     ├── Spring AI embedding observation
  │     └── Spring AI vector-store observation
  ├── app.ai.rag.context.assemble
  ├── Spring AI chat-model observation
  └── app.ai.answer.validate
~~~

Không đưa raw query, document text hoặc embedding vector vào span attributes. Nếu cần điều tra một case cụ thể, dùng opaque reference tới evaluation artifact đã được bảo vệ.

## 10. Observation cho tool calling và workflow nhiều bước

Tool calling có thể tạo side effects. Cần quan sát được:
- tool workflow bắt đầu từ yêu cầu nghiệp vụ nào;
- tool nào được chọn;
- tool execution thành công hay thất bại;
- retry có xảy ra không;
- tool output có được dùng để tạo answer không;
- workflow kết thúc ở trạng thái nào.

Không ghi raw tool arguments nếu chúng chứa dữ liệu nhạy cảm. Dùng tool name/schema revision và outcome classification có tập giá trị hữu hạn.

### Ví dụ

~~~java
public OrderStatus lookupOrder(String orderReference) {
    Observation observation = Observation
            .createNotStarted("app.ai.tool.workflow", registry)
            .contextualName("lookup-order")
            .lowCardinalityKeyValue("workflow", "order_lookup")
            .lowCardinalityKeyValue("tool", "order_status");

    return observation.observe(() -> orderTool.lookup(orderReference));
}
~~~

Nếu orderReference là mã định danh nhạy cảm, không đưa nó vào low/high-cardinality attributes. Hệ thống audit nghiệp vụ có thể lưu reference theo policy riêng.

### Tool loop

Một tool loop có thể gọi model nhiều lần. Business observation nên bao toàn bộ loop; mỗi model call và tool execution là child operation tương ứng. Tổng business duration sẽ bao gồm thời gian chờ tất cả calls, orchestration và retries.

## 11. Ghi nhận business outcome và exception

Observation lifecycle ghi nhận error khi operation ném exception qua observe(...). Điều này hữu ích cho exception metrics/traces, nhưng không phải mọi kết quả nghiệp vụ không thành công đều là exception.

Ví dụ:
- user không đủ quyền;
- context không có tài liệu phù hợp;
- model chủ động abstain;
- validation từ chối answer;
- tool trả trạng thái not found.

Đây có thể là outcome hợp lệ theo nghiệp vụ. Hãy phân biệt:
- success: workflow hoàn tất bình thường;
- rejected: bị policy từ chối;
- abstained: không đủ evidence;
- not_found: không có dữ liệu;
- error: execution exception;
- timeout: vượt deadline.

Dùng counter riêng hoặc custom context/handler để ghi business outcome. Đừng biến mọi rejected hoặc abstained thành exception chỉ để có error metric.

### Phân loại lỗi

Dùng nhóm lỗi có cardinality thấp:
- provider_timeout;
- rate_limited;
- retrieval_unavailable;
- tool_validation;
- tool_execution;
- judge_failure;
- unexpected.

Không dùng exception message làm metric tag. Message có thể chứa URL, query, IDs hoặc dữ liệu do user cung cấp.

## 12. Thời gian của business task và stage durations

Parent observation duration đo toàn bộ thời gian tác vụ theo boundary. Child observations đo thời gian từng stage.

Ví dụ:

| Observation | Duration |
|---|---:|
| Business task | 1.850 ms |
| Prompt preparation | 20 ms |
| RAG retrieval | 180 ms |
| ChatModel call 1 | 950 ms |
| Tool execution | 250 ms |
| ChatModel call 2 | 430 ms |
| Answer validation | 120 ms |

Tổng child duration không nhất thiết bằng parent duration:
- có orchestration và serialization chưa instrument;
- spans có thể overlap khi chạy song song;
- queue/scheduler delay có thể nằm ngoài child operation;
- parent có overhead và wait time.

Không cộng duration parent với duration child khi tính tổng latency. Parent đã bao gồm phần thời gian của child theo execution boundary.

## 13. Context propagation qua executor và thread pool

Observation scope thường gắn với execution context hiện tại. Khi code chuyển sang thread khác, ThreadLocal context không tự động được truyền trong mọi executor.

Hậu quả thường gặp:
- business parent kết thúc ở thread request;
- child model/tool operation chạy ở worker thread nhưng không có parent;
- trace bị tách thành root mới;
- correlation giữa log và span bị mất.

Spring Framework cung cấp ContextPropagatingTaskDecorator trong các phiên bản hỗ trợ Micrometer context propagation. Có thể dùng nó khi cấu hình executor.

### Ví dụ cấu hình

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AiExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor aiTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("ai-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Kiểm tra dependency context-propagation có trên classpath và executor thực sự được dùng bởi workflow. Chỉ khai báo decorator bean mà không gắn vào executor không tạo ra propagation.

ContextPropagatingTaskDecorator có overhead; phù hợp với task cần truyền observation/logging context. Không nên tạo hàng triệu task cực nhỏ chỉ để dùng decorator mà không đo overhead.

## 14. Context propagation trong CompletableFuture

Nếu dùng CompletableFuture, hãy submit task qua executor đã được cấu hình context propagation.

~~~java
CompletableFuture<Answer> future =
        CompletableFuture.supplyAsync(
                () -> answerService.answer(question),
                aiTaskExecutor);
~~~

Tránh:
- gọi CompletableFuture.supplyAsync(...) không truyền executor rồi giả định context sẽ tự động truyền;
- tạo thread thủ công trong service;
- giữ Observation scope mở qua một asynchronous boundary không được quản lý;
- đóng parent observation ngay sau khi submit task trong khi business task vẫn đang chạy.

Nếu business operation thực sự bất đồng bộ, parent lifecycle phải bao đúng thời gian công việc. Có thể dùng async orchestration phù hợp hoặc tạo một observation riêng cho background task và liên kết với request bằng correlation/trace link theo khả năng tracing backend.

## 15. Reactive flows: không stop Observation trước khi subscription hoàn tất

Một lỗi dễ gặp là gọi observation.observe(() -> mono/flux). Supplier chỉ trả về publisher rất nhanh; lifecycle observation có thể kết thúc trước khi publisher được subscribe và xử lý xong.

Với reactive stack:
- dùng integration Observation/Reactor do Spring Boot/Spring hỗ trợ;
- đảm bảo context được truyền qua Reactor Context;
- dùng instrumentation hỗ trợ reactive lifecycle thay vì bọc một publisher bằng synchronous observe;
- đặt observation boundary ở quanh subscription/terminal signal;
- kiểm tra cancellation, error và completion đều đóng lifecycle đúng cách.

Không gọi subscribe() bên trong service chỉ để observation được bắt đầu. Việc tự subscribe thường làm mất control flow, error handling và request context.

### Ba terminal signals cần phân biệt

| Signal | Ý nghĩa |
|---|---|
| onComplete | Publisher hoàn tất bình thường |
| onError | Publisher kết thúc do lỗi |
| cancel | Subscriber hủy trước khi hoàn tất |

Một request bị client cancel vẫn là một event vận hành có ý nghĩa. Nếu cần metric cancellation riêng, ghi outcome có cardinality thấp theo cơ chế phù hợp của reactive instrumentation.

## 16. ObservationConvention để chuẩn hóa metadata

Khi có nhiều use cases, việc mỗi service tự đặt tên/tag có thể dẫn đến taxonomy không nhất quán. ObservationConvention cho phép chuẩn hóa:
- observation name;
- contextual name;
- low-cardinality key-values;
- high-cardinality key-values;
- điều kiện convention áp dụng cho context.

Một convention phù hợp khi:
- nhiều module cùng dùng một business observation type;
- naming/tags phải theo schema chung;
- cần enforce tập tag được phép;
- muốn tách metadata policy khỏi business logic.

Với một vài observations đơn giản, tạo trực tiếp bằng Observation.createNotStarted(...) thường dễ đọc hơn. Đừng xây convention framework phức tạp khi chỉ có một use case.

### Nguyên tắc convention

- Tên cố định, có namespace.
- Low-cardinality values từ enum hoặc mapping đóng.
- Không tự đưa mọi field của request vào attributes.
- High-cardinality values chỉ được thêm khi có use case trace rõ ràng.
- Version convention nếu thay đổi semantics của metrics/tags.

## 17. ObservationHandler, ObservationFilter và ObservationPredicate

ObservationRegistry cho phép cấu hình lifecycle handlers và các điểm mở rộng.

| Extension | Vai trò |
|---|---|
| ObservationHandler | Nhận sự kiện start/error/stop/scope và xuất dữ liệu |
| ObservationFilter | Biến đổi hoặc bổ sung context trước khi xử lý tiếp theo |
| ObservationPredicate | Quyết định observation có được tạo/ghi nhận không |
| ObservationConvention | Chuẩn hóa name và key-values |

Trong ứng dụng Spring Boot, ưu tiên các auto-configured handlers và exporters đã được cấu hình. Chỉ thêm custom handler khi có yêu cầu rõ ràng như:
- đếm business outcome đặc thù;
- tích hợp với hệ thống telemetry nội bộ;
- chuẩn hóa metadata;
- kiểm thử lifecycle.

Không tạo handler gửi HTTP request đồng bộ trong onStop; điều đó có thể làm tăng latency của chính request đang được quan sát. Export telemetry nên dùng exporter/batching phù hợp.

## 18. Tích hợp custom business Observation với Spring AI

Spring AI có instrumentation cho một số thành phần framework. Khi bật đúng observability configuration, các operation như ChatClient, ChatModel, EmbeddingModel, VectorStore và tool execution có thể phát sinh observations.

Custom business observation bổ sung lớp ngữ nghĩa mà component instrumentation không biết:
- workflow=support_answer;
- scenario=rag_tool;
- operation=resolve_request;
- business-level terminal outcome.

### Không tạo hai spans cho cùng một operation

Ví dụ, nếu Spring AI đã tạo observation cho ChatModel call, không tạo thêm một custom observation cùng mô tả đúng ChatModel call đó chỉ để lấy duration. Thay vào đó:
- business parent bao workflow;
- custom child cho orchestration stage mà framework chưa instrument;
- giữ nguyên observation của Spring AI ở tầng model/tool/vector store.

### Kiểm tra cấu hình

- Actuator/Observation infrastructure có trên classpath.
- ObservationRegistry được Spring Boot quản lý.
- Các Spring AI observation được bật theo phiên bản và property tương ứng.
- Tracing bridge/exporter được cấu hình nếu cần distributed traces.
- Context propagation được bật cho executor/reactive flows.
- Kiểm tra trace thực tế để xác nhận parent-child relation.

Tên observation/property cụ thể có thể thay đổi theo phiên bản Spring AI. Đối chiếu reference đúng BOM của project thay vì copy tên property từ một phiên bản khác.

## 19. Metrics từ business observations

Một business observation có thể cung cấp timer/count và các low-cardinality tags cho metrics handler.

Ví dụ các dimension hữu ích:

| Metric concept | Tags |
|---|---|
| Business task duration | workflow, operation, environment |
| Business task count | workflow, outcome |
| Error count | workflow, error_type |
| Retrieval duration | retriever, scenario |
| Tool duration | tool, workflow, outcome |
| Validation duration | validator, workflow |

Tên metric thực tế phụ thuộc registry/handler và naming convention. Kiểm tra MeterRegistry hoặc metrics endpoint thay vì giả định tên metric sẽ giống hệt observation name.

### Cardinality budget

Nếu có:
- 5 workflows;
- 4 operations;
- 3 environments;
- 5 outcomes;

thì số tổ hợp tối đa theo các dimension này là \(5 \times 4 \times 3 \times 5 = 300\), trước khi tính các tags khác. Nếu thêm request ID với hàng triệu giá trị, cardinality tăng không kiểm soát.

Đặt allowlist cho keys/values và review khi thêm tag mới.

## 20. Traces để điều tra một business task

Khi nhận incident “câu trả lời policy mất 8 giây”, trace cấp business giúp tìm đúng stage.

### Quy trình điều tra

1. Tìm business task span theo service/workflow/time window.
2. Xác định total duration và terminal status.
3. Xem child spans theo timeline.
4. Tìm stage có duration cao hoặc exception.
5. Mở model/tool/retrieval span tương ứng.
6. Đối chiếu provider metadata, prompt revision và corpus/index revision.
7. Kiểm tra retries, timeout và context propagation.
8. Liên kết trace với evaluation case/report reference nếu được phép.

### Ví dụ

~~~text
app.ai.business.task             8.2 s
  ├── app.ai.prompt.prepare      0.1 s
  ├── app.ai.rag.retrieve        0.3 s
  ├── chat.model                 2.1 s
  ├── app.ai.tool.workflow       4.9 s
  │     ├── tool.execution       3.8 s
  │     └── chat.model           1.0 s
  └── app.ai.answer.validate     0.5 s
~~~

Trong ví dụ, tool workflow là nơi cần điều tra trước. Không suy ra rằng model chậm chỉ vì toàn bộ AI request mất 8.2 giây.

## 21. Cấu hình observability trong Spring Boot

Một cấu hình nền thường gồm Actuator và Micrometer registry/tracing bridge phù hợp với backend.

### Dependency minh họa

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <!-- Chọn registry/exporter phù hợp với hạ tầng thực tế. -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>

    <!-- Nếu dùng OpenTelemetry tracing qua Micrometer Tracing: -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
</dependencies>
~~~

Dùng dependency management/BOM của Spring Boot để chọn version tương thích. Không tự pin các version Micrometer riêng lẻ nếu Boot BOM đã quản lý.

### Cấu hình ví dụ

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  observations:
    key-values:
      application: support-assistant
  tracing:
    sampling:
      probability: 0.10
~~~

Đây là cấu hình minh họa; endpoint exposure, exporter và property cụ thể phải theo phiên bản Boot và policy triển khai. Sampling 10% không có nghĩa mọi business task đều xuất thành trace. Metrics và traces có sampling semantics khác nhau.

Không expose actuator endpoints công khai nếu chưa có network/auth controls. Chỉ bật endpoint cần thiết và bảo vệ access.

## 22. Kiểm thử custom Observation

Có thể tạo registry riêng trong unit test và đăng ký một handler ghi nhận lifecycle events.

### File BusinessObservationTest.java

~~~java
package com.example.ai.observability;

import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

class BusinessObservationTest {

    @Test
    void recordsBusinessObservationLifecycle() {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger started = new AtomicInteger();
        AtomicInteger stopped = new AtomicInteger();
        AtomicReference<String> currentName = new AtomicReference<>();

        registry.observationConfig().observationHandler(
            new ObservationHandler<Observation.Context>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onStart(Observation.Context context) {
                    started.incrementAndGet();
                    currentName.set(context.getName());
                }

                @Override
                public void onStop(Observation.Context context) {
                    stopped.incrementAndGet();
                }
            });

        String result = Observation
            .createNotStarted("app.ai.business.task", registry)
            .lowCardinalityKeyValue("workflow", "support_answer")
            .observe(() -> "done");

        assertEquals("done", result);
        assertEquals(1, started.get());
        assertEquals(1, stopped.get());
        assertEquals("app.ai.business.task", currentName.get());
    }

    @Test
    void errorDoesNotSkipObservationStop() {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger errors = new AtomicInteger();
        AtomicInteger stopped = new AtomicInteger();

        registry.observationConfig().observationHandler(
            new ObservationHandler<Observation.Context>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onError(Observation.Context context) {
                    errors.incrementAndGet();
                }

                @Override
                public void onStop(Observation.Context context) {
                    stopped.incrementAndGet();
                }
            });

        assertThrows(IllegalStateException.class, () ->
            Observation.createNotStarted("app.ai.business.task", registry)
                .observe(() -> {
                    throw new IllegalStateException("simulated failure");
                }));

        assertEquals(1, errors.get());
        assertEquals(1, stopped.get());
    }
}
~~~

Ví dụ test kiểm tra lifecycle cơ bản của Observation API. Khi tích hợp với tracing exporter thật, cần có integration test để xác minh trace ID, parent span và context propagation. Không dùng unit test registry đơn giản để kết luận exporter/backend đã nhận trace.

## 23. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ instrument ChatModel | Không thấy tổng workflow | Thêm business parent |
| Tạo Observation tên động | Metric cardinality tăng | Dùng taxonomy tên cố định |
| Gắn request ID vào low-cardinality tag | Metrics bùng cardinality | Chỉ dùng trace attribute khi được phép |
| Gắn raw prompt vào span | Rò rỉ dữ liệu | Dùng reference đã bảo vệ |
| Không truyền context sang executor | Trace bị tách | Context propagation decorator |
| Bọc Mono bằng synchronous observe | Observation kết thúc trước subscription | Dùng reactive instrumentation |
| Tạo custom span trùng Spring AI span | Double-count duration | Chỉ thêm business/stage spans còn thiếu |
| Quên stop observation | Span/timer không hoàn tất | Dùng observe hoặc try/finally |
| Gửi telemetry đồng bộ trong handler | Tăng latency | Dùng exporter/batching |
| Ghi mọi business rejection thành error | Error rate sai | Tách business outcome và exception |
| Sampling quá thấp khi điều tra incident | Thiếu trace | Tail sampling/temporary policy theo hạ tầng |
| Không ghi version metadata | Khó so sánh run | Lưu prompt/model/corpus/policy revision |

## 24. Bài thực hành: instrument một workflow RAG có tool

Tạo workflow resolve-support-request gồm:
1. Nhận câu hỏi.
2. Retrieve policy documents.
3. Generate answer.
4. Nếu cần, gọi order_status tool.
5. Generate final answer.
6. Validate factuality/citation.
7. Trả response.

### Yêu cầu

- Một parent observation app.ai.business.task.
- Child observations cho retrieval, context assembly, validation và business tool workflow.
- Spring AI auto observations giữ nguyên cho ChatModel/EmbeddingModel/VectorStore/tool operations.
- Low-cardinality tags gồm workflow, scenario, operation và outcome theo allowlist.
- Không đưa raw prompt, document text, order reference hay user ID vào metrics/traces.
- Error, abstention, not-found và timeout có outcome riêng.
- Async executor truyền được context.
- Unit test kiểm tra lifecycle; integration test xác nhận parent-child trace.

### Kết quả mong đợi

~~~text
app.ai.business.task
  ├── app.ai.rag.retrieve
  ├── app.ai.rag.context.assemble
  ├── Spring AI chat model
  ├── app.ai.tool.workflow
  │     ├── Spring AI tool observation
  │     └── Spring AI chat model
  └── app.ai.answer.validate
~~~

### Tiêu chí hoàn thành

- Một trace cho thấy toàn bộ business task.
- Có thể xác định stage gây chậm hoặc lỗi.
- Metrics tổng hợp theo workflow mà không chứa request IDs.
- Tool side effects có trace/audit reference phù hợp.
- Không có duplicate span cho cùng operation.
- Test xác nhận exception vẫn kết thúc lifecycle.

## 25. Checklist trước khi đưa custom observations vào production

- [ ] Business task boundary có start/end rõ ràng.
- [ ] Tên observation cố định và có namespace.
- [ ] Parent observation bao đúng toàn bộ workflow.
- [ ] Child observations chỉ được thêm cho stage có ý nghĩa.
- [ ] Spring AI built-in observations không bị duplicate.
- [ ] ObservationRegistry được inject từ Spring container.
- [ ] Lifecycle start/stop/error được quản lý an toàn.
- [ ] Low-cardinality tags có allowlist và budget.
- [ ] High-cardinality attributes chỉ phục vụ trace use case được phê duyệt.
- [ ] Không ghi raw prompt, PII, secrets, document text hoặc tool arguments nhạy cảm.
- [ ] Business outcome được phân biệt với exception.
- [ ] Executor/CompletableFuture truyền context đúng cách.
- [ ] Reactive lifecycle gắn với subscription và terminal signals.
- [ ] ObservationConvention/Handler chỉ được thêm khi có nhu cầu rõ.
- [ ] Exporter không block request thread.
- [ ] Sampling policy được hiểu và kiểm soát.
- [ ] Metrics và traces được bảo vệ bằng access/retention policy.
- [ ] Unit test xác minh start/error/stop.
- [ ] Integration test xác minh trace parent-child và context propagation.
- [ ] Có dashboard/trace query phục vụ câu hỏi vận hành cụ thể.

## Tài liệu tham khảo

1. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation lifecycle, registry, conventions và handlers.
2. [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): truyền context qua ThreadLocal và reactive contexts.
3. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Observation, tracing, metrics và context propagation.
4. [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html): observability và propagation trong Spring.
5. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): built-in observations cho ChatClient, model, tools và vector store.
6. [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/): span, context, parent-child và trace lifecycle.
7. [OpenTelemetry — Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): attributes cho GenAI operations.
8. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong logs và telemetry.

> **Ghi nhớ:** Component observations cho biết từng model, retriever hoặc tool đã làm gì. Business Observation kết nối các operation đó thành một tác vụ mà người vận hành hiểu được. Hãy đặt parent ở application boundary, truyền context qua mọi execution boundary, giữ tags có cardinality thấp và bảo vệ dữ liệu trước khi export telemetry.
