# Quan sát mô hình: Định danh mô hình yêu cầu và mô hình thực tế phản hồi

## 1. Bài toán: một yêu cầu có thể mang hai định danh model

Trong một ứng dụng Spring AI, nhóm phát triển thường cấu hình một tên mô hình cho lời gọi chat, ví dụ `answer-model-prod`. Nhưng mô hình được **provider hoặc gateway báo trong phản hồi** có thể mang tên khác, ví dụ một tên phiên bản cụ thể. Nếu chỉ lưu tên cấu hình, dashboard có nguy cơ quy kết độ trễ, token và chi phí cho sai model.

Spring AI hỗ trợ quan sát **hai định danh riêng biệt** trong một thao tác `ChatModel`:

- `gen_ai.request.model` — tên mô hình mà yêu cầu được gửi tới, theo cách instrumentation ghi nhận.
- `gen_ai.response.model` — tên mô hình đã tạo phản hồi, **theo thông tin phía phản hồi cung cấp**.

Hai giá trị có thể bằng nhau, khác nhau hoặc một giá trị có thể không có. Sự khác nhau **không tự chứng minh** rằng nhà cung cấp đã âm thầm đổi model; alias, deployment, API gateway và cơ chế báo metadata đều có thể ảnh hưởng cách đặt tên.

Bài học này thuộc chương **Quan sát mô hình** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Trong module, việc chấm relevance, fact checking, kiểm thử RAG/tool calling cần được đối chiếu với metrics, traces, chi phí và độ trễ theo các phiên bản prompt, model và pipeline. Định danh đúng model là điều kiện nền tảng để các phép so sánh đó có ý nghĩa.

**Mục tiêu sau bài học:**

1. Phân biệt model **được yêu cầu** với model **được phản hồi báo về**, cùng vai trò của provider.
2. Đọc `gen_ai.request.model`, `gen_ai.response.model` trong observation và `ChatResponseMetadata.getModel()` trong Java.
3. Giải thích các trường hợp giống/khác/thiếu tên model mà không suy diễn vượt bằng chứng.
4. Thiết kế cách theo dõi alias, deployment, gateway, fallback, streaming và retry.
5. Viết mã Java, test kiểm tra metadata và truy vấn Prometheus phục vụ chẩn đoán.
6. Liên kết danh tính model với kết quả đánh giá và quản lý cardinality/bảo mật dữ liệu.

## 2. Vị trí của hai định danh trong Spring AI

Spring AI quan sát model call qua Micrometer. Với implementation được hỗ trợ, thao tác `ChatModel.call(...)` hoặc `stream(...)` tạo observation `gen_ai.client.operation`.

~~~mermaid
flowchart LR
    A["Ứng dụng / Evaluation suite"] --> O["ChatOptions / Prompt"]
    O --> M["ChatModel"]
    M --> R["Yêu cầu tới provider/gateway"]
    R --> P["Model được định tuyến"]
    P --> S["Phản hồi provider"]
    M -.->|request.model| OBS["gen_ai.client.operation"]
    S -.->|response.model| OBS
    S --> META["ChatResponseMetadata"]
    META -.->|getModel()| X["Kiểm tra ứng dụng"]
    OBS --> T["Metrics và traces"]
~~~

Sơ đồ phản ánh **dòng dữ liệu khái niệm**. Spring AI không trực tiếp chứng kiến mọi lựa chọn nội bộ của provider, nên `response.model` là danh tính **được báo cáo**, không phải chứng thực phần cứng hoặc binary model đã thực thi.

| Thuộc tính | Đến từ đâu | Câu hỏi trả lời | Giới hạn |
| --- | --- | --- | --- |
| `gen_ai.system` | ChatModel instrumentation | Provider nào nhận lời gọi? | Thường là định danh provider tích hợp, chưa chắc là backend cuối của gateway |
| `gen_ai.request.model` | Model/options của lời gọi theo instrumentation | Ứng dụng đã yêu cầu tên nào? | Có thể là alias hoặc deployment, không phải version thực |
| `gen_ai.response.model` | Metadata của response khi có | Phía phản hồi khai báo model nào đã tạo kết quả? | Có thể thiếu, chuẩn hóa, giữ nguyên alias hoặc do gateway ghi |
| `gen_ai.response.id` | Response ID khi provider báo | ID phản hồi nào cần truy vết? | **Không phải** tên model |
| `ChatResponseMetadata.getModel()` | Metadata của `ChatResponse` | Trong Java, phản hồi báo tên model nào? | Có thể `null`/rỗng và phụ thuộc provider |

Theo tài liệu Spring AI, bốn khóa `gen_ai.operation.name`, `gen_ai.system`, `gen_ai.request.model` và `gen_ai.response.model` được thiết kế là **low-cardinality keys** cho observation của `ChatModel`. Chúng có thể xuất trong cả metrics và traces với điều kiện instrumentation/provider thực sự cung cấp giá trị.

**Tránh nhầm tầng:** observation của `ChatClient` có `gen_ai.system=spring_ai` vì nó đo hoạt động framework. Để xem provider và tên model của cuộc gọi, cần nhìn `gen_ai.client.operation` ở **tầng ChatModel**.

## 3. Ba lớp tên model trong một hệ thống thực

Một hệ thống có thể có **ít nhất ba tên**:

1. **Logical model/role:** tên do ứng dụng tự đặt, như `answer-primary`, `judge-stable` hoặc `cheap-classifier`.
2. **Requested model:** giá trị thật được gửi trong yêu cầu API, như `production-chat-alias` hoặc tên deployment.
3. **Reported model:** `response.model` hoặc `ChatResponseMetadata.getModel()` được phía trả lời cung cấp.

Đôi khi còn lớp thứ tư là **actual backend identity**: model phiên bản cụ thể mà gateway/provider thực sự thực thi. Lớp này chỉ có thể được xác minh qua thông tin kiểm toán đáng tin cậy của gateway/provider; tên được báo trong response có thể là bằng chứng, nhưng không nhất thiết là bằng chứng đầy đủ.

~~~mermaid
flowchart TD
    L["Vai trò: answer-primary"] --> C["Cấu hình: production-chat-alias"]
    C --> Q["Request: model = production-chat-alias"]
    Q --> G["Gateway / deployment router"]
    G --> V["Backend model thực thi"]
    V --> P["Response: reported model"]
    Q --> O["gen_ai.request.model"]
    P --> R["gen_ai.response.model"]
    G -.->|routing logs nếu có| A["Bằng chứng kiểm toán"]
    V -.->|backend identity| A
~~~

Ví dụ minh họa (không phải tên model hoặc bản ghi thực tế):

~~~text
workflow_role       = answer
configured_alias    = support-prod
requested_model     = support-prod
reported_model      = model-family-revision-B
gateway_route_id    = route-17
backend_deployment  = deployment-west-2
~~~

Một dashboard chỉ lưu `configured_alias=support-prod` sẽ bỏ lỡ khả năng cấu hình backend của alias đã thay đổi. Nhưng nếu dashboard chỉ lưu `reported_model`, có thể không biết người vận hành đã yêu cầu alias nào. Để phân tích đúng, **lưu cả hai**, kèm phiên bản routing/config nếu có.

### 3.1. Vì sao cùng tên vẫn chưa chắc cùng model?

Ngay cả khi:

~~~text
gen_ai.request.model  = support-prod
gen_ai.response.model = support-prod
~~~

thì hai chuỗi bằng nhau chỉ xác nhận **tên được yêu cầu và tên được báo trùng nhau**. Nếu `support-prod` là một alias thay đổi mục tiêu, backend có thể đã được nâng phiên bản mà hai nhãn không đổi.

Ngược lại, khi hai chuỗi khác nhau, đó là tín hiệu **cần điều tra**, không phải bằng chứng về hành vi sai của provider.

## 4. ChatOptions: xác định tên model được yêu cầu

Trong Spring AI, `ChatOptions.getModel()` thể hiện tên model trong options portable. Provider còn có options riêng, ví dụ `OpenAiChatOptions`. Cấu hình model có thể đặt khi khởi tạo bean hoặc ghi đè ở **lượt gọi cụ thể**.

### 4.1. Cấu hình mặc định lúc khởi động

Ví dụ `application.yml` cho ứng dụng dùng OpenAI Chat Model:

~~~yaml
spring:
  ai:
    model:
      chat: openai
    openai:
      chat:
        model: example-chat-model
~~~

`example-chat-model` là **giá trị minh họa**, phải đổi sang tên có thật và được provider tài khoản sử dụng hỗ trợ. Tên property có thể thay đổi theo major version của Spring AI; ví dụ dựa trên tài liệu Spring AI hiện hành, không phải cấu hình phổ quát cho mọi bản phát hành.

Nếu ứng dụng đang sử dụng một phiên bản Spring AI cũ có prefix `spring.ai.openai.chat.options.model`, hãy kiểm tra tài liệu **đúng phiên bản dependency**. Khi nâng cấp, không nên trộn thuộc tính cấu hình từ hai dòng version.

### 4.2. Ghi đè model trong một lời gọi

Một ví dụ Java có thể truyền options riêng cho `Prompt`:

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.openai.OpenAiChatOptions;

public final class ModelSelectionExample {

    private final ChatModel chatModel;

    public ModelSelectionExample(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    public ChatResponse ask(String text, String requestedModel) {
        if (requestedModel == null || requestedModel.isBlank()) {
            throw new IllegalArgumentException("Model name phải có giá trị");
        }

        Prompt prompt = new Prompt(
                text,
                OpenAiChatOptions.builder()
                        .model(requestedModel)
                        .build()
        );

        return chatModel.call(prompt);
    }
}
~~~

Đoạn này giả định `chatModel` là implementation **tương thích OpenAI ChatOptions**. Không truyền `OpenAiChatOptions` cho bất kỳ provider khác rồi coi đó là cách lựa chọn model portable.

Với gọi `ChatModel.call(...)` trực tiếp, tài liệu Spring AI lưu ý **runtime options trong `Prompt` có thể thay thế đầy đủ startup options**. Tránh truyền chỉ một phần options rồi mặc định tất cả giá trị startup khác vẫn được giữ. Với `ChatClient`, cấu hình `defaultOptions(...)` và options ở từng prompt có cơ chế hợp nhất riêng; hãy đối chiếu bản đang sử dụng.

### 4.3. Nên lưu requested model tại thời điểm nào?

Có ít nhất ba thời điểm khác nhau:

- Khi **deploy**, ứng dụng đọc tên model mặc định.
- Khi **xây request**, code có thể ghi đè model theo loại case, user tier hoặc experiment.
- Khi **provider nhận request**, SDK/gateway có thể chuẩn hóa các giá trị.

Để đo chính xác **lượt gọi cụ thể**, nên dùng `gen_ai.request.model` của observation hoặc ghi lại options **đã áp dụng sau khi quyết định cấu hình**. Chỉ lưu tên model mặc định trong YAML có thể sai khi có runtime override.

## 5. Đọc tên model thực tế được phản hồi báo trong Java

`ChatResponse` cung cấp `ChatResponseMetadata`, với getter `getModel()`.

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.prompt.Prompt;

public final class ResponseModelInspector {

    private final ChatModel chatModel;

    public ResponseModelInspector(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    public String inspect(String question) {
        ChatResponse response = chatModel.call(new Prompt(question));

        if (response == null) {
            return "NO_RESPONSE";
        }

        ChatResponseMetadata metadata = response.getMetadata();

        if (metadata == null) {
            return "MODEL_METADATA_MISSING";
        }

        String reportedModel = metadata.getModel();

        if (reportedModel == null || reportedModel.isBlank()) {
            return "REPORTED_MODEL_MISSING";
        }

        return reportedModel;
    }
}
~~~

Đoạn code trả trạng thái thay thế để dễ đọc. Trong hệ thống thật, **không nên dùng** các chuỗi `NO_RESPONSE` hoặc `REPORTED_MODEL_MISSING` như thể chúng là tên model thật. Hãy giữ trường `reportedModel` là `null`/`Optional.empty()` và lưu trạng thái riêng để không làm méo biểu đồ.

Nếu cần cả **ID phản hồi** và **usage**:

~~~java
ChatResponse response = chatModel.call(prompt);

if (response != null && response.getMetadata() != null) {
    ChatResponseMetadata meta = response.getMetadata();
    String responseId = meta.getId();
    String reportedModel = meta.getModel();
    var usage = meta.getUsage();

    // responseId là ID của lần trả lời, KHÔNG phải model ID.
    // reportedModel là tên model được phía phản hồi báo về.
    // usage có thể thiếu, cần xử lý nullable.
}
~~~

**Không nhầm `response.getResult().getOutput().getText()` với metadata.** Lời gọi lấy nội dung văn bản (hoặc `ChatClient.call().content()`) không bảo đảm còn giữ đầy đủ thông tin response model cho lớp gọi.

### 5.1. Ví dụ: lưu cặp requested/reported dưới dạng record

~~~java
public record ModelIdentity(
        String requestedModel,
        String reportedModel,
        String responseId) {

    public boolean hasRequestedModel() {
        return requestedModel != null && !requestedModel.isBlank();
    }

    public boolean hasReportedModel() {
        return reportedModel != null && !reportedModel.isBlank();
    }

    public boolean differsByName() {
        return hasRequestedModel()
                && hasReportedModel()
                && !requestedModel.equals(reportedModel);
    }
}
~~~

`differsByName()` chỉ so sánh **chuỗi**. Nó **không tuyên bố backend đã chuyển model**. Nếu ứng dụng cần chuẩn hóa tên model, phải dùng một mapping có nguồn tin cậy và version; không tùy ý bỏ suffix phiên bản hoặc ép lowercase để che các khác biệt có ý nghĩa.

Ví dụ ghép dữ liệu:

~~~java
String requestedModel = "support-prod";

ChatResponse response = chatModel.call(
        new Prompt(
                "Thời hạn đổi trả đơn online là bao lâu?",
                OpenAiChatOptions.builder()
                        .model(requestedModel)
                        .build()
        )
);

String reportedModel = response != null
        && response.getMetadata() != null
        ? response.getMetadata().getModel()
        : null;

String responseId = response != null
        && response.getMetadata() != null
        ? response.getMetadata().getId()
        : null;

ModelIdentity identity =
        new ModelIdentity(requestedModel, reportedModel, responseId);

System.out.println("Different by name: "
        + identity.differsByName());
~~~

Code trên giả định import của `ChatModel`, `Prompt`, `ChatResponse` và `OpenAiChatOptions` đã có. Giá trị `support-prod` là **alias minh họa**: provider thật có thể từ chối nếu nó không được cấu hình.

## 6. Những tình huống khiến request.model và response.model khác nhau

| Tình huống | Ví dụ giả định | Cách giải thích hợp lý | Điều không thể kết luận ngay |
| --- | --- | --- | --- |
| **Alias được provider giải quyết** | Request `chat-prod`, response `chat-revision-7` | Provider báo bản thực thi cụ thể | Chưa chứng minh không đúng hợp đồng |
| **Gateway/router** | Request `balanced-chat`, response `model-B` | Gateway chọn backend theo rule | Không biết rule hoặc trọng số nếu không có gateway logs |
| **Azure deployment** | Request một deployment name, response một model name | Tên deployment có thể khác model nền | Không tự biết chính xác revision nếu response không báo |
| **Failover/fallback** | Request alias `primary`, response `backup-model` | Có thể đã đổi route hoặc retry sang provider khác | Không thể xác nhận fallback chỉ bằng hai chuỗi |
| **Custom ChatModel adapter** | Request `logical-X`, response `engine-Y` | Adapter ánh xạ tên nội bộ | Cần kiểm tra implementation |
| **Provider giữ nguyên alias** | Request `chat-prod`, response `chat-prod` | Có thể backend thực tế vẫn là revision khác | Hai tên bằng nhau không chứng minh binary model cố định |
| **Missing metadata** | Request `model-X`, response không có model | Provider/SDK thiếu trường hoặc call lỗi | Không có nghĩa provider chạy “model rỗng” |
| **Model override khi runtime** | Startup `model-A`, từng case chọn `model-B` | Request options thay thế model mặc định | Không nên dùng startup config làm nguồn chân lý cho từng call |

Tất cả giá trị trong bảng là **minh họa**, không phải trạng thái thực tế của những provider được nêu.

### 6.1. Azure OpenAI: deployment name không đồng nhất model name

Theo tài liệu Spring AI dành cho Azure OpenAI, `deployment-name` là tên deployment, **khác khái niệm** với tên model. Một deployment là cấu hình do người vận hành tạo, và backend có thể được quản lý riêng.

Vì vậy, trong dashboard:

- Lưu **tên deployment được yêu cầu** khi đó là giá trị cấu hình request.
- Lưu **tên model phía phản hồi** nếu metadata có.
- Nếu cần theo dõi revision hoặc khu vực triển khai thực sự, dùng thêm **metadata quản trị Azure/gateway có thẩm quyền**.
- Tránh đưa toàn bộ endpoint URL hoặc khóa bí mật vào metric labels.

### 6.2. Gateway có thể cung cấp routing audit độc lập

Một gateway do tổ chức kiểm soát có thể ghi:

~~~json
{
  "routeId": "route-2026-11-27-01",
  "logicalModel": "balanced-chat",
  "requestedModel": "balanced-chat",
  "resolvedBackend": "model-B-deployment-2",
  "reportedModel": "model-B",
  "reason": "capacity-routing"
}
~~~

Đây là **schema nhật ký giả định của gateway**, không phải output Spring AI tự sinh. Nếu bạn kiểm soát router, record này giúp kiểm chứng việc ánh xạ tên và phân biệt việc provider trả nhãn bất thường với việc router có chủ đích chuyển backend.

Đừng gắn route ID duy nhất vào **low-cardinality metric tag**. Dùng span/log có quản lý quyền để kết nối trace bằng ID; metric chỉ nên dùng các nhóm tên đã kiểm soát.

### 6.3. Response model khác không nhất thiết là error

Một thay đổi tên model phản hồi có thể là **bình thường** sau khi nâng deployment hoặc chuyển alias. Chỉ báo lỗi khi dự án có **hợp đồng rõ ràng**: ví dụ một bộ evaluation phải cố định đúng revision trong một đợt regression.

Ngay cả với hợp đồng nghiêm ngặt, cần kiểm tra provider metadata và nguồn audit trước khi kết luận. Một label mismatch có thể do chuẩn hóa ký tự, phiên bản SDK hoặc tên deployment, không phải thay đổi năng lực của mô hình.

## 7. Phân biệt mismatch, missing và lỗi gọi model

Một cách phân loại trạng thái ứng dụng:

| Trạng thái tự định nghĩa | Điều kiện | Hành động |
| --- | --- | --- |
| `MATCHED_BY_NAME` | Cả hai tên có và trùng chính xác | Ghi nhận; vẫn cần version/routing audit khi cần |
| `DIFFERENT_BY_NAME` | Hai tên có và khác chuỗi | Điều tra alias/deployment/gateway |
| `REQUESTED_NAME_MISSING` | Thiếu tên trong cấu hình/observation | Kiểm tra options và instrumentation |
| `REPORTED_NAME_MISSING` | Phản hồi không báo model | Kiểm tra metadata/provider, không tự điền 0 |
| `BOTH_NAMES_MISSING` | Cả hai cùng thiếu | Kiểm tra code path và telemetry |
| `MODEL_CALL_ERROR` | Timeout, rate limit, lỗi provider, exception | Ghi lỗi kỹ thuật riêng |
| `ROUTING_NOT_VERIFIED` | Cần xác minh backend nhưng thiếu audit | Không tuyên bố đã định danh backend |

Các trạng thái trên là **đề xuất của bài học**, không phải enum có sẵn của Spring AI. `MODEL_CALL_ERROR` có thể xảy ra ngay cả khi request model đã có, nhưng không có response model vì provider chưa hoàn tất.

### 7.1. Java: phân loại hai tên một cách quyết định

~~~java
public enum ModelNameStatus {
    MATCHED_BY_NAME,
    DIFFERENT_BY_NAME,
    REQUESTED_NAME_MISSING,
    REPORTED_NAME_MISSING,
    BOTH_NAMES_MISSING
}
~~~

~~~java
public final class ModelNameClassifier {

    private ModelNameClassifier() {
    }

    public static ModelNameStatus classify(
            String requested, String reported) {

        boolean reqMissing =
                requested == null || requested.isBlank();
        boolean respMissing =
                reported == null || reported.isBlank();

        if (reqMissing && respMissing) {
            return ModelNameStatus.BOTH_NAMES_MISSING;
        }
        if (reqMissing) {
            return ModelNameStatus.REQUESTED_NAME_MISSING;
        }
        if (respMissing) {
            return ModelNameStatus.REPORTED_NAME_MISSING;
        }
        return requested.equals(reported)
                ? ModelNameStatus.MATCHED_BY_NAME
                : ModelNameStatus.DIFFERENT_BY_NAME;
    }
}
~~~

Classifier cố tình **không tự động chuẩn hóa alias**. Khi cần ánh xạ `deployment-name → model`, bạn phải dùng bảng mapping được tổ chức phê duyệt, ghi version mapping và ngày hiệu lực.

### 7.2. Unit test không cần provider

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ModelNameClassifierTest {

    @Test
    void matchedNamesAreRecognized() {
        assertThat(ModelNameClassifier.classify(
                "model-A", "model-A"))
                .isEqualTo(ModelNameStatus.MATCHED_BY_NAME);
    }

    @Test
    void differentNamesNeedInvestigation() {
        assertThat(ModelNameClassifier.classify(
                "chat-prod", "model-A-revision-2"))
                .isEqualTo(ModelNameStatus.DIFFERENT_BY_NAME);
    }

    @Test
    void missingMetadataIsNotTreatedAsMismatch() {
        assertThat(ModelNameClassifier.classify(
                "model-A", null))
                .isEqualTo(ModelNameStatus.REPORTED_NAME_MISSING);

        assertThat(ModelNameClassifier.classify(
                null, "model-A"))
                .isEqualTo(ModelNameStatus.REQUESTED_NAME_MISSING);

        assertThat(ModelNameClassifier.classify(
                "", "  "))
                .isEqualTo(ModelNameStatus.BOTH_NAMES_MISSING);
    }
}
~~~

Unit test này chỉ kiểm tra cách phân loại **metadata**, không chứng minh model thật ở phía provider hoặc gateway.

## 8. Metrics: xem request và response model trong Prometheus

Đối với `ChatModel`, Spring AI sử dụng observation `gen_ai.client.operation`. Khi Micrometer xuất sang Prometheus, tên metric/label thường được chuẩn hóa dấu chấm thành gạch dưới.

Ví dụ series **minh họa**:

~~~text
gen_ai_client_operation_seconds_count{
  gen_ai_operation_name="chat",
  gen_ai_system="openai",
  gen_ai_request_model="chat-prod",
  gen_ai_response_model="model-A-revision-2",
  error="none"
} 42
~~~

Giá trị `42`, alias và tên model đều là **dữ liệu giả lập**. Một provider khác hoặc phiên bản instrument khác có thể có nhãn thiếu hoặc tên khác. Hãy nhìn dữ liệu thực tại `/actuator/prometheus` trước khi viết quy tắc cảnh báo.

### 8.1. Đếm các cặp request/response model

~~~promql
sum by (
  gen_ai_system,
  gen_ai_request_model,
  gen_ai_response_model
) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

Biểu đồ này trả lời: “Từ requested name nào, response model name nào đang xuất hiện?” Nó **không tự chứng minh tuyến backend** vì nhãn phản hồi vẫn đến từ metadata của model implementation/provider.

### 8.2. Tìm cặp tên khác nhau

**PromQL không hỗ trợ so sánh trực tiếp giá trị của hai label trên cùng một sample.** Biểu thức dạng `gen_ai_request_model!=gen_ai_response_model` trong bộ lọc PromQL không so hai label với nhau; nó chỉ so một label với **chuỗi ký tự cố định**. Vì vậy không nên dùng để tính mismatch rate.

Cách đáng tin cậy là dùng `ModelNameClassifier` trong ứng dụng để phân loại từ hai giá trị metadata, sau đó ghi **metric riêng** `model_identity_checks_total` (counter) với tập nhãn giới hạn như provider, vai trò workflow và trạng thái:

~~~text
model_identity_checks_total{
  provider="openai",
  workflow_role="answer",
  status="DIFFERENT_BY_NAME"
} 5
~~~

Ví dụ PromQL hợp lệ cho **tỷ lệ cặp tên khác nhau trên các cặp có đủ hai tên**, theo provider và vai trò:

~~~promql
sum by (provider, workflow_role) (
  rate(model_identity_checks_total{
    status="DIFFERENT_BY_NAME"
  }[5m])
)
/
sum by (provider, workflow_role) (
  rate(model_identity_checks_total{
    status=~"MATCHED_BY_NAME|DIFFERENT_BY_NAME"
  }[5m])
)
~~~

Đây là **metric và label do ứng dụng tự thiết kế**, không phải metric Spring AI tạo mặc định. Khi không có cặp tên đầy đủ trong cửa sổ quan sát, mẫu số bằng 0 hoặc không có series; dashboard cần hiển thị “không đủ dữ liệu”, không hiển thị 0% một cách tùy tiện. Nhãn `status` có tập giá trị nhỏ, tránh bùng nổ cardinality.

### 8.3. Thống kê tên phản hồi không được báo

Prometheus có thể biểu diễn nhãn vắng mặt khác nhau theo exporter. Không nên dùng `gen_ai_response_model=""` rồi kết luận toàn bộ các cuộc gọi thiếu metadata, vì một số implementation dùng fallback value hoặc bỏ label. Để đo đáng tin cậy, hãy tạo counter `model_identity_checks_total{status="REPORTED_NAME_MISSING"}` ở lớp kiểm tra metadata.

**Lưu ý về mẫu số:** nếu `ChatResponseMetadata` không được trả vì exception, hãy tính `MODEL_CALL_ERROR` riêng; không nên gom mọi lỗi thành `REPORTED_NAME_MISSING`.

## 9. Không gán nhãn tùy tiện: cardinality và tính nhất quán

Theo Spring AI, `gen_ai.request.model` và `gen_ai.response.model` được thiết kế là **low-cardinality**. Điều đó giả định tên model đến từ một tập giới hạn, ví dụ một danh sách model/deployment đã cấu hình.

Nhưng trong ứng dụng có model name tùy ý từ request của người dùng hoặc alias được tạo động, tập giá trị có thể rất lớn. Khi ấy:

- Tránh gắn các biến không kiểm soát làm tag metric mới.
- Cân nhắc **allowlist** hoặc bucket model family khi thiết kế các metric **do ứng dụng tự thêm**.
- Giữ tên đầy đủ ở **traces/log có phân quyền** nếu thật sự cần điều tra.
- Không ghi API key, full prompt, raw response, email, IP hoặc order ID vào label.
- Không xóa toàn bộ khác biệt tên bằng cách chuẩn hóa mù quáng; có thể mất thông tin về revision.

Một bảng ánh xạ có version, ví dụ:

~~~text
alias           revision family        valid_from
chat-prod       family-A-revision-1    2026-10-01
chat-prod       family-A-revision-2    2026-11-15
judge-stable    family-B-revision-3    2026-11-01
~~~

là **dữ liệu ví dụ do hệ thống quản lý**, không phải Spring AI tự cung cấp. Ngày hiệu lực và owner của mapping phải do đội quản trị provider/gateway xác nhận.

## 10. Traces: kiểm tra một request cụ thể

Metrics cho biết tổng hợp theo model, còn trace giúp xem lịch sử xử lý một request có nhiều lời gọi.

~~~text
POST /api/ask                         traceId=abc...
  spring.ai.chat.client              1.45s
    spring.ai.advisor                0.22s
    gen_ai.client.operation          1.08s
      gen_ai.system: openai
      gen_ai.request.model: chat-prod
      gen_ai.response.model: model-A-revision-2
      gen_ai.response.id: resp-123
  quality.evaluation                 0.43s
    gen_ai.client.operation          0.39s
      gen_ai.system: anthropic
      gen_ai.request.model: judge-stable
      gen_ai.response.model: family-B-revision-3
~~~

Đây là **trace minh họa**, không phải trace đã thu thập. `quality.evaluation` là observation do ứng dụng tự định nghĩa. Quan hệ parent-child phụ thuộc tracing context thực tế, nhất là với streaming/async.

Khi phân tích:

1. Xác định `request.model` ở **model call tương ứng với answer**, không lấy nhầm judge.
2. Đọc `response.model` của **cùng span** để so sánh chính xác theo từng cuộc gọi.
3. Kiểm tra `gen_ai.response.id`, HTTP trace và log gateway nếu cần audit routing.
4. Xem các model calls do retry/tool calling; một request người dùng có thể có nhiều cặp tên.
5. Đọc lỗi, duration và token usage của từng lượt; đừng gộp chúng thành một model giả định.

### 10.1. Các lỗi phổ biến khi đọc trace

- **Model được yêu cầu ở ChatClient khác model trên ChatModel:** vì runtime options, advisor hoặc đoạn code khác có thể override; xem model call thực tế.
- **Có response model nhưng không có request model:** kiểm tra instrumentation/option và nguồn tag; không tự suy đoán.
- **Có model span nhưng thiếu HTTP child span:** provider SDK hoặc streaming có thể không giữ quan hệ cha-con.
- **Không thấy response model khi call lỗi:** một lỗi có thể xảy ra trước khi provider tạo metadata.
- **Model name trùng nhưng token/latency đổi:** gateway có thể nâng backend sau alias mà không đổi nhãn.

## 11. Streaming, retry và fallback làm bài toán phức tạp hơn

### 11.1. Streaming

Khi dùng `ChatModel.stream(...)`, dữ liệu đến theo nhiều phần. Không nên giả định **mọi chunk đều chứa model metadata đầy đủ** hoặc có một `ChatResponseMetadata` cuối cùng theo cùng cách như `call(...)`.

Với ứng dụng cần lưu reported model trong streaming:

- Dùng cơ chế gom/aggregator phản hồi được Spring AI hoặc ứng dụng hỗ trợ.
- Chỉ đọc tên model từ metadata thật sự xuất hiện.
- Nếu chưa nhận được hoặc stream bị hủy sớm, ghi `REPORTED_NAME_MISSING` hoặc `STREAM_INCOMPLETE` riêng.
- Không chọn bừa model ID từ một chunk không đại diện cho kết quả cuối.

Duration của `gen_ai.client.operation` trong streaming cũng không nhất thiết bằng **time to first token (TTFT)**. Nếu mục tiêu là so TTFT giữa provider, phải instrument sự kiện chunk đầu riêng.

### 11.2. Retry

Nếu một lần gọi provider lỗi rồi được retry, có thể có:

~~~text
attempt #1: requested=chat-prod, no response, error=timeout
attempt #2: requested=chat-prod, reported=model-A-revision-2, success
~~~

Không gộp thành một kết luận “tên model bị thiếu” ở lần thành công. Lưu rõ **attempt number**, lỗi và response metadata tương ứng. Không được dùng response của attempt #2 để gán cho request của attempt #1 khi kiểm toán.

### 11.3. Fallback

Nếu application hoặc gateway chuyển sang model dự phòng:

~~~text
attempt #1: requested=primary-model,  error=rate_limit
attempt #2: requested=backup-model,   reported=backup-model, success
~~~

Đây là **hai lượt gọi**, nên kết quả thuộc model dự phòng và chi phí cần tính theo lượt thành công. Nếu fallback diễn ra **bên trong gateway** sau một request mang alias chung, Spring AI có thể chỉ nhìn thấy requested alias và reported model; muốn kết luận có fallback, cần route logs hoặc metadata gateway xác thực.

### 11.4. Không dùng response model làm label chất lượng cuối cùng duy nhất

Một luồng agent/tool có thể gọi lần lượt model A rồi model B, hoặc một answer model và một judge model. Một case cuối có thể liên quan nhiều `gen_ai.client.operation`. Khi ghi kết quả `RelevancyEvaluator`, hãy giữ danh sách các cuộc gọi theo vai trò/attempt hoặc xác định **cuộc gọi tạo answer cuối**, chứ không gán tùy tiện model đầu hay cuối của trace cho toàn bộ case.

## 12. Tính chi phí và chất lượng theo đúng model

Tên model liên quan trực tiếp tới **định giá token** và **so sánh hiệu năng**. Ví dụ khi requested model là alias và reported model là tên revision:

~~~text
requested_model     = chat-prod
reported_model      = family-A-revision-2
input_tokens        = 1400
output_tokens       = 210
pricing_rule        = family-A, rate-version-2026-11
~~~

Đây là ví dụ logic tính phí. **Không lấy một tên model bất kỳ rồi áp giá**: provider có thể tính phí theo deployment, tài khoản, khu vực, API hoặc model thực tế, tùy hợp đồng. Cần đối chiếu hóa đơn và bảng giá có hiệu lực.

Công thức token cost đơn giản:

~~~text
estimated_cost =
    input_tokens / 1_000_000 * input_price_per_million
  + output_tokens / 1_000_000 * output_price_per_million
~~~

Đây chỉ là ước lượng. Cache usage, reasoning tokens, retry, gateway và gói dịch vụ có thể tạo các dòng chi phí khác. Khi `reportedModel` thiếu, không nên tự động chọn mức giá rẻ nhất hoặc kết luận chi phí bằng 0.

### 12.1. Một bảng kết quả regression cần lưu gì?

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| `caseId` | `rag-058` | Liên kết case với dữ liệu gốc |
| `datasetVersion` | `rag-set-v4` | Bảo đảm so sánh cùng dataset |
| `answerPromptVersion` | `answer-v7` | Kiểm soát thay đổi prompt |
| `requestedModel` | `chat-prod` | Biết cấu hình gọi của lượt answer |
| `reportedModel` | `family-A-revision-2` | Biết provider đã báo model nào |
| `provider` | `openai` | Phân tích theo nhà cung cấp |
| `judgeRequestedModel` | `judge-stable` | Không nhầm judge với answer |
| `judgeReportedModel` | `judge-revision-3` | Phát hiện thước đo thay đổi |
| `relevancePass` | `true` | Kết quả chất lượng theo rubric |
| `latencyMs` | `850` | Độ trễ lượt answer |
| `inputTokens` / `outputTokens` | `1400 / 210` | Ước lượng chi phí |
| `traceId` | `trace-123` | Truy vết request cụ thể |

Tất cả giá trị là **schema minh họa**. Spring AI không tự cung cấp một record đầy đủ đúng như bảng. Tùy hệ thống, `caseId`, trace ID và model phiên bản phải được quản lý ở tầng workflow.

### 12.2. Vì sao cần lưu model của judge?

Nếu answer model không đổi nhưng judge model được nâng phiên bản ẩn sau alias, tỷ lệ `PASS` của `RelevancyEvaluator` có thể biến động do **thước đo đã đổi**, không phải chatbot tốt/xấu hơn.

Đối với đánh giá so sánh A/B:

1. Cố định tập dữ liệu, answer input và ngữ cảnh nếu mục tiêu là so model trả lời.
2. Cố định judge model/rubric khi muốn so quality của answer model.
3. Ghi **request và response model** của cả answer lẫn judge.
4. Nếu phát hiện model khác dự kiến, ghi `EXPERIMENT_ENV_DRIFT` và điều tra trước khi gộp vào kết quả thống kê.
5. Đối chiếu một tập mẫu có nhãn con người để tách judge drift khỏi answer drift.

## 13. Bảo mật, tính riêng tư và khả năng tái hiện

Một trace chứa model name có thể trông vô hại, nhưng tên deployment nội bộ hoặc route metadata có thể tiết lộ cấu trúc vận hành. Vì vậy:

- Chỉ ghi **những định danh cần thiết** cho mục đích đo lường.
- Không đưa API key, bearer token, endpoint chứa thông tin bí mật vào tags.
- Không gắn user ID, session ID, email, nội dung prompt hoặc response vào low-cardinality labels.
- Dùng quyền truy cập và thời hạn lưu riêng cho dữ liệu kiểm toán gateway.
- Với đa tenant, không tiết lộ tên deployment của tenant này cho tenant khác qua dashboard.
- Nếu ứng dụng dùng alias xoay vòng, ghi mapping được quản trị theo version và ngày áp dụng.

Một pipeline cần tái hiện tốt nên lưu **version của routing policy**. Chỉ dựa vào `gen_ai.request.model` và `gen_ai.response.model` có thể không đủ khi backend được thay qua alias mà không cập nhật tên trong response.

## 14. Chẩn đoán sự cố

| Hiện tượng | Giả thuyết nên kiểm tra | Cách xác minh |
| --- | --- | --- |
| `request.model` khác `response.model` | Alias, deployment, gateway routing hoặc cách provider ghi metadata | Kiểm tra response metadata và routing docs/logs |
| `request.model` giống `response.model` nhưng chất lượng đổi | Backend thay dưới alias, prompt/data khác hoặc judge drift | Kiểm tra version, gateway audit, dataset và prompt |
| `response.model` trống | Provider không báo, SDK không map hoặc call lỗi | Đọc `ChatResponseMetadata.getModel()` và trace error |
| Dashboard chỉ có `gen_ai.system=spring_ai` | Đang đọc ChatClient observation, không phải ChatModel | Lọc `gen_ai.client.operation` |
| Model startup là A nhưng request tag là B | Có runtime override trong Prompt/ChatClient | Xem options của đúng lời gọi |
| Số lượt `model-A` tăng bất thường | Router thay rule hoặc traffic mix đổi | Xem routing policy và số request theo nhóm |
| Cost tăng mà model name không đổi | Token tăng, tool/retry nhiều hơn hoặc bảng giá thay | Kiểm tra usage, số call và rate version |
| Không có HTTP child span | Streaming/SDK thiếu propagation hoặc instrumentation | Xem trace provider và bản SDK |
| Traces đầy đủ nhưng Prometheus thiếu model tag | Metadata thiếu, meter convention hoặc version exporter | So observation với endpoint `/actuator/prometheus` |
| Tên model chứa hàng nghìn giá trị | Tên động/user-provided gây cardinality cao | Allowlist/mapping, đổi cách xuất metric custom |

### Quy trình điều tra khuyến nghị

1. **Đọc đúng operation:** `gen_ai.client.operation` thay vì `spring.ai.chat.client`.
2. **Xác định vai trò:** answer, judge, tool-assisted hoặc retry.
3. **Ghi hai tên:** requested và reported, không suy diễn khi thiếu.
4. **Đối chiếu model options:** startup config và runtime override.
5. **Đối chiếu provider/router:** alias, deployment, audit, quy tắc chọn model.
6. **Đối chiếu response metadata:** `getModel()`, `getId()`, usage nếu có.
7. **Xem traces và chi phí:** duration, error, token, số attempts.
8. **Xem quality:** kết quả relevance/fact checking theo dataset và judge đã cố định.
9. **Kết luận với mức chắc chắn phù hợp:** name mismatch là **tín hiệu**, backend verification cần bằng chứng khác.

## 15. Bài tập thực hành

### Bài 1. Ghi cặp model của một lời gọi

Trong một ứng dụng Spring AI đang hoạt động, gọi `ChatModel.call(...)` với model trong `ChatOptions`, sau đó đọc `ChatResponseMetadata.getModel()`. Ghi lại cả hai tên và provider; chú thích nếu response không báo model.

### Bài 2. Runtime override

Cấu hình model A làm mặc định, nhưng ở một case dùng `OpenAiChatOptions.builder().model("model-B")`. Kiểm tra `gen_ai.request.model` trong observation thực tế; không lấy startup config làm kết luận về model được yêu cầu.

### Bài 3. Tự phân loại trạng thái

Cài đặt `ModelNameClassifier` và chạy các test `MATCHED_BY_NAME`, `DIFFERENT_BY_NAME`, `REQUESTED_NAME_MISSING` và `REPORTED_NAME_MISSING`. Giải thích vì sao classifier không thể xác minh backend model.

### Bài 4. Dashboard request/response model

Xem `/actuator/prometheus` và xác định series `gen_ai_client_operation_seconds_count` cùng các label model. Viết PromQL tổng hợp theo cặp requested/reported. Thiết kế thêm một metric do ứng dụng tự ghi cho mismatch rate với các nhãn hữu hạn.

### Bài 5. Alias drift trong regression suite

Giả sử hai đợt đánh giá đều dùng requested model `chat-prod`, nhưng một đợt báo `model-A-revision-1` và đợt kia `model-A-revision-2`. Phân tích liệu có thể quy kết thay đổi pass rate cho prompt hay không. Xác định thông tin routing và judge model cần kiểm tra.

### Bài 6. Failover và chi phí

Mô phỏng hai attempts: model chính lỗi, model dự phòng trả lời. Lập bảng requested/reported model, status, tokens, duration và chi phí cho từng attempt. Giải thích tại sao không được gán response metadata của attempt thành công cho attempt lỗi.

## 16. Tổng kết

`gen_ai.request.model` và `gen_ai.response.model` là hai định danh có ý nghĩa khác nhau trong quan sát `ChatModel` của Spring AI. Một bên là **tên model được yêu cầu**, bên kia là **tên model được phía phản hồi báo về**. `ChatResponseMetadata.getModel()` cho phép đọc danh tính được báo ở tầng Java.

Chúng có thể khớp, khác hoặc thiếu vì alias, deployment, gateway, routing, runtime overrides, SDK hoặc lỗi gọi model. **Hai chuỗi khác nhau không tự chứng minh model bị chuyển sai; hai chuỗi trùng nhau cũng không bảo đảm backend không thay đổi**. Muốn biết model thật trong một hệ thống định tuyến phức tạp, cần kết hợp metadata với audit/routing evidence có thẩm quyền.

Khi đánh giá ứng dụng Spring AI qua dataset, RAG/tool calling, relevance và fact checking, hãy lưu đồng thời model **được yêu cầu** và model **được báo về** của cả answer và judge. Sau đó đối chiếu với traces, token usage, latency, chi phí, phiên bản prompt và pipeline để xác định nguyên nhân biến động chất lượng một cách có căn cứ.

## Tài liệu tham khảo

- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): `gen_ai.client.operation`, low-cardinality keys `gen_ai.request.model` và `gen_ai.response.model`, traces, token usage.
- [Spring AI Reference — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html): `ChatModel`, `ChatOptions.getModel()`, startup/runtime options và `ChatResponse`.
- [Spring AI Reference — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): `ChatResponseMetadata.getModel()`, `getId()` và `getUsage()`.
- [Spring AI Reference — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): cấu hình model và ghi đè bằng `OpenAiChatOptions.builder().model(...)`.
- [Spring AI Reference — Azure OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/azure-openai-chat.html): phân biệt deployment name với model name.
- [Spring AI Reference — Observability Metrics](https://docs.spring.io/spring-ai/reference/observability/index.html): Prometheus model operation và các khóa chung để quan sát provider.
