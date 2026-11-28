# Hiển thị chi phí theo tính năng hoặc mô hình

## 1. Vì sao cần nhìn chi phí theo cả tính năng và mô hình?

Một ứng dụng AI có thể dùng cùng một model cho nhiều mục đích: trả lời chat, RAG, tóm tắt tài liệu, phân loại yêu cầu và chạy agent. Nếu dashboard chỉ hiển thị tổng tiền theo provider, đội sản phẩm không biết tính năng nào đang tiêu tốn ngân sách. Nếu chỉ nhóm theo tính năng, đội kỹ thuật lại khó biết model nào làm chi phí tăng sau một lần thay đổi routing.

Hãy hình dung trong một ngày:

| Tính năng | Model chính | Số tác vụ | Chi phí minh họa |
|---|---|---:|---:|
| Chat hỗ trợ | Model A | 20.000 | $18,00 |
| RAG hỏi đáp | Model A | 8.000 | $22,00 |
| Tóm tắt tài liệu | Model B | 3.000 | $9,00 |
| Agent xử lý yêu cầu | Model A + Model B | 1.000 | $16,00 |

Tổng chi phí là $65,00. Nhưng con số tổng không cho biết RAG tốn nhiều hơn chat dù có ít tác vụ hơn, hoặc agent dùng hai model trong một workflow.

Dashboard chi phí cần hỗ trợ ít nhất hai góc nhìn:

- **Theo tính năng (feature):** chi phí của chat, RAG, summarization, agent, classification hoặc chức năng nghiệp vụ khác.
- **Theo mô hình (model):** chi phí theo provider, model thực tế, loại token và modality.

Khi kết hợp hai chiều, bạn có thể trả lời: “RAG tốn bao nhiêu tiền trong tuần này?”, “Model B được dùng ở những tính năng nào?”, “Chi phí agent tăng do model hay do số vòng gọi?”, “Tính năng nào có cost per successful task cao nhất?”.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module học đánh giá ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

- Chuẩn hóa token usage và bảng giá theo từng provider/model.
- Tính chi phí cho từng model operation và tổng hợp theo feature.
- Gắn feature context vào model calls, kể cả khi có tool loop hoặc async execution.
- Phân biệt chi phí model với tool, vector database và hạ tầng.
- Thiết kế cost ledger có version bảng giá và chống ghi nhận trùng.
- Xuất metric có cardinality hữu hạn và xây dashboard hai chiều feature/model.
- Theo dõi budget, cost per task và chi phí trên mỗi tác vụ thành công.

## 2. Phân biệt usage, rate và cost

Ba khái niệm này cần được lưu riêng:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Usage | Tài nguyên thực tế đã tiêu thụ | 2.000 input tokens, 300 output tokens |
| Rate/price | Đơn giá áp dụng cho một đơn vị usage | USD trên một triệu tokens |
| Cost | Usage nhân với rate, cộng các khoản tính theo request hoặc modality | 0,0042 USD |

Một model call có usage nhưng chưa chắc đã có cost chính xác nếu chưa biết:

- Model billable thực tế.
- Provider và region.
- Bảng giá có hiệu lực tại thời điểm request.
- Input/output/cached tokens được tính giá thế nào.
- Service tier, batch mode hoặc discount.
- Các khoản phí theo request, image, audio hoặc modality khác.

Không hardcode một con số giá vào prompt hay dashboard. Hãy quản lý rate card có version, thời điểm hiệu lực và nguồn tham chiếu.

## 3. Các nguồn dữ liệu để tính chi phí

Một cost pipeline thường lấy dữ liệu từ bốn nơi:

| Nguồn | Dữ liệu | Vai trò |
|---|---|---|
| Spring AI / provider usage | Provider, model, input/output tokens, operation | Usage thực tế của model |
| Pricing catalog | Đơn giá, currency, effective date, billing unit | Rate áp dụng |
| Application context | Feature, task type, workflow, release | Phân bổ chi phí |
| Cost ledger / billing export | Operation ID, usage, price version, calculated amount | Đối soát và audit |

Spring AI cung cấp metric token usage theo thông tin provider báo cáo. Với Prometheus, metric stable là gen_ai_client_token_usage_total và tag gen_ai_token_type có input, output, total. Metric này hữu ích cho tổng hợp usage; để tính cost chính xác theo từng operation, ứng dụng nên ghi nhận usage metadata gắn với operation và lưu một cost event có thể truy vết.

Tài liệu: [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/).

## 4. Chuẩn hóa token usage trước khi tính tiền

Provider có thể trả usage metadata với tên trường và semantics khác nhau. Hãy chuẩn hóa thành các nhóm billable không chồng lấn.

Ví dụ normalized usage:

| Nhóm | Ý nghĩa |
|---|---|
| uncached input tokens | Input tokens bị tính theo giá input tiêu chuẩn |
| cached input tokens | Input tokens được provider báo riêng và có thể có giá khác |
| output tokens | Output tokens được tính theo quy tắc của provider/model |
| reasoning tokens | Có thể được tính trong output hoặc được báo riêng tùy provider |
| image/audio/video units | Đơn vị tính theo modality, ví dụ ảnh, giây audio hoặc frames |

Điểm quan trọng: không tự cộng các trường provider báo cáo nếu chúng là phần con của một trường tổng.

Ví dụ, nếu provider báo input tokens đã bao gồm cached input tokens, hãy tách:

\[
UncachedInput = TotalInput - CachedInput
\]

Sau đó tính giá uncached input và cached input riêng. Nếu provider đã báo uncached input độc lập, không trừ cached lần nữa.

Reasoning tokens cũng cần được xử lý theo pricing contract. Có provider tính reasoning tokens trong output tokens; provider khác có thể báo riêng. Adapter của từng provider phải chuyển dữ liệu về các nhóm billable không trùng nhau trước khi đưa vào calculator.

Không dùng tokenizer tự ước lượng thay cho usage provider khi provider có báo số billed tokens. Tokenizer có thể hữu ích cho dự toán trước request, nhưng cần đánh dấu là estimated.

## 5. Công thức tính chi phí token

Với bảng giá theo một triệu tokens:

\[
Cost_{tokens} =
\frac{InputTokens \times InputRate}{1,000,000}
+
\frac{OutputTokens \times OutputRate}{1,000,000}
\]

Nếu có cached input:

\[
Cost_{tokens} =
\frac{UncachedInput \times InputRate}{1,000,000}
+
\frac{CachedInput \times CachedInputRate}{1,000,000}
+
\frac{Output \times OutputRate}{1,000,000}
\]

Ví dụ minh họa, không phải giá hiện hành của một provider:

| Loại usage | Số tokens | Giá / 1M tokens | Thành tiền |
|---|---:|---:|---:|
| Uncached input | 12.000 | $2,00 | $0,024 |
| Cached input | 8.000 | $0,20 | $0,0016 |
| Output | 2.000 | $8,00 | $0,016 |
| **Tổng** | **22.000** | | **$0,0416** |

Tổng chi phí token của operation là $0,0416.

Nếu provider tính thêm phí theo request, image, audio duration, batch processing hoặc service tier, hãy cộng các khoản đó thành từng line item riêng. Không ép mọi modality về token nếu pricing contract không tính theo token.

## 6. Pricing catalog cần có những trường nào?

Một bảng giá đủ dùng nên có các trường:

| Trường | Mục đích |
|---|---|
| provider | Nhà cung cấp |
| model_id | Model ID billable chính xác |
| region | Khu vực áp dụng nếu giá khác nhau |
| service_tier | Standard, batch hoặc tier tương ứng |
| input_rate | Giá uncached input trên một đơn vị |
| cached_input_rate | Giá cached input nếu có |
| output_rate | Giá output |
| image_rate | Giá theo image hoặc đơn vị ảnh nếu áp dụng |
| audio_rate | Giá theo audio token/giây/phút nếu áp dụng |
| embedding_rate | Giá embedding theo token hoặc request |
| currency | USD, EUR hoặc currency hợp đồng |
| unit | Per 1M tokens, per image, per second, per request |
| effective_from | Thời điểm bắt đầu hiệu lực |
| effective_until | Thời điểm hết hiệu lực |
| pricing_version | Phiên bản bảng giá |
| source | URL/hợp đồng/nguồn giá đã xác minh |

Giá có thể thay đổi theo thời gian. Khi tính lại một operation lịch sử, phải dùng bảng giá có hiệu lực tại thời điểm operation phát sinh, trừ khi mục đích là mô phỏng giá mới.

Không dùng alias model như một định danh giá ổn định nếu alias có thể trỏ sang model khác. Lưu cả requested model và actual response model nếu provider báo được model thực tế.

## 7. Ví dụ cấu trúc bảng giá có version

Một catalog có thể lưu dạng YAML:

~~~yaml
pricing:
  - provider: provider-a
    modelId: model-a-2026-01
    region: global
    currency: USD
    unit: per_1m_tokens
    inputRate: 2.00
    cachedInputRate: 0.20
    outputRate: 8.00
    effectiveFrom: "2026-01-01T00:00:00Z"
    effectiveUntil: null
    version: price-2026-01
    source: "https://provider.example/pricing"
~~~

Các giá trị trong ví dụ là giả định để minh họa cấu trúc. URL example không phải nguồn giá thực tế. Trong production, lưu URL chính thức hoặc hợp đồng đã được bộ phận phụ trách xác nhận.

Nếu có nhiều region, service tier hoặc loại request, tạo rate card riêng theo tổ hợp provider/model/region/tier/unit. Tránh một dòng giá duy nhất áp dụng cho mọi tình huống.

## 8. Tính chi phí bằng BigDecimal trong Java

Tiền nên được tính bằng BigDecimal thay vì double để tránh sai số nhị phân khi cộng nhiều operation nhỏ.

Ví dụ domain model tối giản:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public record NormalizedTokenUsage(
    long uncachedInputTokens,
    long cachedInputTokens,
    long outputTokens
) {
    public NormalizedTokenUsage {
        if (uncachedInputTokens < 0
                || cachedInputTokens < 0
                || outputTokens < 0) {
            throw new IllegalArgumentException("Token usage must be non-negative");
        }
    }
}

public record TokenRate(
    BigDecimal inputUsdPerMillion,
    BigDecimal cachedInputUsdPerMillion,
    BigDecimal outputUsdPerMillion,
    String pricingVersion
) {}

public final class TokenCostCalculator {

    private static final BigDecimal ONE_MILLION =
        new BigDecimal("1000000");

    private static final int INTERNAL_SCALE = 12;

    public BigDecimal calculate(
            NormalizedTokenUsage usage,
            TokenRate rate) {

        BigDecimal inputCost = charge(
            usage.uncachedInputTokens(),
            rate.inputUsdPerMillion()
        );

        BigDecimal cachedCost = charge(
            usage.cachedInputTokens(),
            rate.cachedInputUsdPerMillion()
        );

        BigDecimal outputCost = charge(
            usage.outputTokens(),
            rate.outputUsdPerMillion()
        );

        return inputCost
            .add(cachedCost)
            .add(outputCost)
            .setScale(8, RoundingMode.HALF_UP);
    }

    private BigDecimal charge(long tokens, BigDecimal pricePerMillion) {
        return BigDecimal.valueOf(tokens)
            .multiply(pricePerMillion)
            .divide(ONE_MILLION, INTERNAL_SCALE, RoundingMode.HALF_UP);
    }
}
~~~

Calculator trên chỉ tính token charges theo USD. Production implementation cần kiểm tra null, currency, rate effective date, model/provider match và các khoản phí theo modality. Chỉ làm tròn ở bước cuối cùng của từng line item hoặc invoice theo quy tắc kế toán đã chọn; không làm tròn từng token.

## 9. Một model operation cần gắn với feature nào?

Chi phí chỉ có thể phân bổ theo feature nếu ứng dụng biết model operation phục vụ mục đích gì.

Ví dụ feature catalog:

| Feature key | Ý nghĩa |
|---|---|
| chat_support | Trả lời chat hỗ trợ |
| rag_answer | Trả lời dựa trên tài liệu truy xuất |
| document_summary | Tóm tắt tài liệu |
| ticket_classification | Phân loại ticket |
| agent_workflow | Điều phối agent và tools |
| evaluation_judge | Chạy evaluator/judge |
| embedding_ingestion | Tạo embeddings cho dữ liệu |

Feature key phải được gán ở application boundary, nơi đã biết use case. Không suy đoán feature bằng cách đọc prompt hoặc completion.

Một service có thể gọi nhiều model operations. Các operations này cần kế thừa feature của tác vụ gốc, đồng thời có thể thêm operation role như planner, answer, reranker hoặc judge để phân tích sâu hơn.

## 10. Truyền feature context qua advisor và model calls

Ví dụ service biết request đang thuộc tính năng RAG:

~~~java
public Answer answerQuestion(String question) {
    try (var scope = FeatureContext.open("rag_answer")) {
        return ragService.answer(question);
    }
}
~~~

FeatureContext là abstraction do ứng dụng định nghĩa. Nó cần hoạt động đúng trong thread pool, asynchronous callbacks và Reactor context nếu pipeline dùng reactive execution.

Khi ChatClient gọi ChatModel, cost instrumentation đọc feature context và gắn vào cost event. Nếu model call được phát sinh trong tool loop hoặc recursive advisor, context vẫn cần được truyền theo logical task.

Không chỉ dựa vào ThreadLocal nếu execution có thể chuyển thread. Dùng context propagation phù hợp với kiến trúc ứng dụng và kiểm thử các nhánh async/stream.

Nếu một model operation không có feature context, ghi feature là unknown/unattributed và tạo metric để phát hiện. Không tự gán toàn bộ operations thiếu context vào feature mặc định vì điều đó che mất lỗi instrumentation.

## 11. Phân biệt feature, operation role và model

Ba chiều này trả lời ba câu hỏi:

| Dimension | Câu hỏi | Ví dụ |
|---|---|---|
| Feature | Tính năng nghiệp vụ nào dùng tài nguyên? | rag_answer |
| Operation role | Model đang làm bước gì trong feature? | query_rewrite, answer, judge |
| Model | Model/provider nào được dùng? | provider-a / model-a |

Ví dụ một RAG request:

~~~text
feature = rag_answer
  operation role = query_rewrite
    model = model-small
  operation role = answer
    model = model-large
  operation role = rerank
    model = embedding-or-reranker-model
~~~

Dashboard theo feature cho thấy tổng chi phí RAG. Dashboard theo operation role cho biết bước nào trong pipeline tốn tiền. Dashboard theo model cho biết model nào tiêu thụ ngân sách.

Giữ ba chiều tách biệt. Không đặt tên model vào feature hoặc đặt operation role vào provider label.

## 12. Xử lý tool loop và nhiều model calls trong một tác vụ

Một agent task có thể gọi model nhiều lần:

~~~text
Một feature: agent_workflow
  Model operation #1: planner
  Tool execution: search_customer
  Model operation #2: tool_result_interpretation
  Tool execution: lookup_policy
  Model operation #3: final_answer
~~~

Mỗi model operation tạo một cost line item. Tổng chi phí của feature là tổng các line items thuộc task đó.

\[
FeatureCost(task) = \sum_{i=1}^{N} ModelOperationCost_i
\]

Nếu model fallback từ A sang B, hãy ghi model thực tế đã xử lý operation. Nếu một tác vụ gọi cả generator và judge model, phân bổ judge cost vào feature evaluation hoặc operation role judge theo chính sách kế toán của sản phẩm.

Không tính một model operation nhiều lần chỉ vì có nhiều spans hoặc advisors cùng quan sát nó. Cost event phải gắn với ranh giới ChatModel operation và có operation ID duy nhất.

## 13. Phân bổ chi phí khi một operation phục vụ nhiều feature

Trường hợp phổ biến nhất là một operation phục vụ một feature. Nếu một operation dùng chung cho nhiều feature, cần quy tắc allocation rõ ràng.

Có ba cách:

1. **Single owner:** gán toàn bộ cost cho feature khởi tạo operation.
2. **Weighted allocation:** chia theo tỷ trọng được tính từ workload hoặc business rule có thể kiểm chứng.
3. **Shared platform bucket:** đưa chi phí vào nhóm shared và phân bổ sau theo kỳ.

Ví dụ một batch summarization xử lý tài liệu của ba tính năng. Nếu batch có 60%, 30%, 10% tokens thuộc từng feature, có thể phân bổ cost theo tỷ lệ đó nếu token usage per item đo được đáng tin cậy.

Không ghi toàn bộ cost vào cả ba feature rồi cộng lại. Cách đó làm tổng cost bị nhân lên. Tổng cost sau allocation phải bằng tổng cost gốc, sai khác chỉ do rounding theo quy tắc đã định.

## 14. Chi phí model khác chi phí toàn bộ tính năng

Một feature có thể phát sinh nhiều loại chi phí:

| Cost category | Ví dụ |
|---|---|
| Model inference | Input/output tokens, image/audio usage |
| Embedding | Tokens hoặc requests tạo embeddings |
| Vector database | Query, storage, indexing |
| Tool/service | API bên ngoài, search, CRM, geocoding |
| Compute | CPU/GPU, memory, worker runtime |
| Storage/network | Object storage, data transfer |
| Human review | Chi phí reviewer hoặc moderation workflow |

Để dashboard dễ hiểu, hãy hiển thị model cost riêng và feature total cost riêng.

\[
FeatureTotalCost =
ModelCost + ToolCost + RetrievalCost + AllocatedInfrastructureCost
\]

Chỉ cộng những thành phần đã có cách đo và allocation hợp lệ. Nếu chưa có số liệu compute/storage, ghi rõ dashboard đang hiển thị model spend thay vì total cost.

## 15. Ghi cost ledger cho từng model operation

Metric tổng hợp tốt cho dashboard, nhưng không đủ cho audit hoặc tính lại theo bảng giá mới. Nên có cost ledger hoặc event store ghi một bản ghi cho mỗi model operation đã hoàn tất.

Ví dụ:

~~~json
{
  "operationId": "model-op-0192",
  "taskId": "task-771",
  "feature": "rag_answer",
  "operationRole": "answer",
  "provider": "provider-a",
  "requestedModel": "model-alias",
  "responseModel": "model-a-2026-01",
  "usage": {
    "uncachedInputTokens": 12000,
    "cachedInputTokens": 8000,
    "outputTokens": 2000
  },
  "pricingVersion": "price-2026-01",
  "currency": "USD",
  "modelCost": "0.04160000",
  "usageSource": "provider",
  "costStatus": "calculated"
}
~~~

Đây là schema ứng dụng đề xuất, không phải payload mặc định của Spring AI.

Cost ledger giúp:

- Truy ngược một khoản chi phí đến model operation.
- Tính lại theo rate card mới mà không thay dữ liệu usage gốc.
- Phân tích theo feature, model, provider, release và operation role.
- Đối soát với provider invoice.
- Phát hiện operation trùng hoặc thiếu usage.

Không lưu prompt, completion hoặc dữ liệu người dùng trong cost ledger nếu không có nhu cầu rõ ràng. Các trường định danh phải tuân theo retention và access control của hệ thống.

## 16. Idempotency và tránh ghi nhận trùng

Một model operation có thể được retry ở tầng transport, provider SDK hoặc application. Mỗi attempt thực sự được billing phải được phân biệt theo usage event và provider response.

Nguyên tắc:

- Tạo operation ID ổn định cho một model operation.
- Nếu provider retry tạo ra request billable mới, ghi attempt ID riêng.
- Dùng unique key để chống consumer xử lý lặp cùng cost event.
- Không tạo cost event cho từng streaming chunk.
- Nếu stream chỉ trả usage ở final chunk, ghi một event sau khi nhận usage cuối.
- Nếu stream bị cancel và provider không trả usage, đánh dấu usage incomplete/estimated thay vì zero.
- Giữ raw usage metadata cần thiết để audit, đã loại bỏ dữ liệu nhạy cảm.

Không gộp các lần retry billable thành một operation nếu provider tính tiền từng attempt. Ngược lại, không ghi hai lần cùng một usage report chỉ vì callback được phát lại.

## 17. Đối soát với hóa đơn provider

Usage trong application telemetry là cơ sở ước tính. Provider invoice mới là nguồn đối soát tiền phải trả.

Một quy trình đối soát:

1. Tổng hợp cost ledger theo provider, model và ngày billing.
2. Lấy usage/billing export chính thức của provider.
3. Chuẩn hóa timezone, currency, model ID, region và billing unit.
4. So sánh input/output/cached usage nếu provider cung cấp.
5. Phân tích chênh lệch do pricing tier, discount, retries, rounding, taxes hoặc usage chưa được ghi.
6. Cập nhật rate card version và ghi nhận adjustment có audit trail.
7. Không sửa/xóa usage event gốc; tạo adjustment event riêng.

Ví dụ:

| Provider | Ledger estimate | Invoice | Chênh lệch |
|---|---:|---:|---:|
| Provider A | $420,00 | $428,50 | +$8,50 |
| Provider B | $180,00 | $176,00 | -$4,00 |

Các con số minh họa. Chênh lệch không nhất thiết là bug trong calculator; có thể do discount, cached token billing, batch pricing hoặc các khoản phí chưa được mô hình hóa.

## 18. Thiết kế cost metrics cho dashboard

Không dùng một metric chung cho mọi đơn vị. Một schema metric có thể gồm:

~~~text
app_ai_model_cost_usd_total{feature,provider,model_family,usage_type}
app_ai_model_tokens_total{feature,provider,model_family,token_type}
app_ai_feature_tasks_total{feature,outcome}
app_ai_unpriced_model_operations_total{provider,model_family}
app_ai_cost_adjustments_usd_total{provider,adjustment_type}
~~~

Ý nghĩa:

- app_ai_model_cost_usd_total: counter cộng số tiền đã tính cho model operation.
- app_ai_model_tokens_total: counter usage theo token category.
- app_ai_feature_tasks_total: counter số tác vụ theo outcome.
- app_ai_unpriced_model_operations_total: operation chưa tìm được rate card.
- app_ai_cost_adjustments_usd_total: khoản điều chỉnh khi đối soát invoice.

Feature, provider, model family, usage type và outcome phải có danh mục hữu hạn. Không dùng task ID, operation ID, conversation ID, trace ID hoặc user ID làm labels.

Pricing version có thể được lưu trong ledger. Chỉ đưa vào metric label nếu số phiên bản hữu hạn và có nhu cầu so sánh trực tiếp; nếu không, hãy dùng deployment annotation hoặc cost ledger.

Với app_ai_model_tokens_total, hãy dùng các token categories không chồng lấn như input_uncached, input_cached và output. Nếu xuất thêm total, dashboard phải loại total khỏi phép cộng để tránh double count.

## 19. Xuất cost counter bằng Micrometer

Ví dụ đơn giản khi cost calculator đã trả về số tiền USD:

~~~java
import java.math.BigDecimal;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class ModelCostMetrics {

    private final MeterRegistry registry;

    public ModelCostMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String feature,
            String provider,
            String modelFamily,
            String usageType,
            BigDecimal amountUsd) {

        if (amountUsd.signum() < 0) {
            throw new IllegalArgumentException("Cost must not be negative");
        }
        if (amountUsd.signum() == 0) {
            return;
        }

        Counter.builder("app.ai.model.cost.usd")
            .tag("feature", feature)
            .tag("provider", provider)
            .tag("model_family", modelFamily)
            .tag("usage_type", usageType)
            .register(registry)
            .increment(amountUsd.doubleValue());
    }
}
~~~

Micrometer Counter nhận một giá trị increment dương. Trong Prometheus, metric thường được xuất với hậu tố _total. Hãy xác nhận tên cuối cùng trong /actuator/prometheus.

Đây là ví dụ instrumentation cho dashboard. Cost ledger vẫn nên là nơi lưu line item có operation ID và pricing version để xử lý idempotency, audit và reconciliation. Không dùng một Counter trong bộ nhớ làm sổ kế toán duy nhất vì process có thể restart và metric có thể bị mất trước khi scrape.

Counter của Micrometer dùng số thực cho increment. Giá trị tổng hợp trên dashboard có thể có sai số biểu diễn nhỏ, đặc biệt với nhiều khoản rất nhỏ. Dùng BigDecimal và cost ledger làm nguồn số liệu kế toán; dùng metric counter để theo dõi xu hướng và cảnh báo.

## 20. Dashboard chi phí theo feature

Dashboard feature nên trả lời tính năng nào đang tiêu ngân sách và chi phí có tạo ra kết quả hay không.

Các panel đề xuất:

| Panel | Cách nhóm | Câu hỏi |
|---|---|---|
| Daily cost by feature | feature | Tính năng nào tốn nhiều nhất hôm nay? |
| Cost share | feature / total | Tỷ trọng chi phí của từng tính năng? |
| Cost per task | feature | Một tác vụ trung bình tốn bao nhiêu? |
| Cost per successful task | feature | Chi phí để hoàn thành một tác vụ đạt tiêu chí? |
| Token usage by feature | feature, token_type | Feature nào dùng nhiều input/output? |
| Model operations per task | feature | Có nhiều model rounds hơn không? |
| Budget vs actual | feature | Feature nào sắp vượt ngân sách? |
| Quality vs cost | feature, criterion | Chi phí tăng có cải thiện chất lượng không? |

Ví dụ cost per successful task:

\[
CostPerSuccessfulTask(feature) =
\frac{TotalModelCost(feature)}
{SuccessfulTasks(feature)}
\]

Mẫu số phải là số tác vụ hoàn tất theo business contract, không phải số model calls. Với RAG, có thể định nghĩa success là câu trả lời đạt quality gate; với classification, success có thể dựa trên expected label hoặc human-reviewed outcome.

## 21. Dashboard chi phí theo model

Dashboard model giúp đội kỹ thuật tối ưu routing và lựa chọn model.

| Panel | Cách nhóm | Câu hỏi |
|---|---|---|
| Daily cost by model | provider, model_family | Model nào tiêu nhiều nhất? |
| Input vs output cost | model, usage_type | Chi phí đến từ prompt hay generation? |
| Cached input savings | model | Cache giảm được bao nhiêu tiền? |
| Cost per model operation | model | Mỗi lần gọi tốn trung bình bao nhiêu? |
| Tokens per operation | model, token_type | Model nào dùng context dài? |
| Model mix | feature, model_family | Feature đang dùng model nào? |
| Fallback cost | requested/actual model | Fallback có làm chi phí tăng không? |
| Quality by model | model, criterion | Model nào đạt quality tốt trên cùng dataset? |

Nếu model alias có thể thay đổi đích, hãy giữ response model thực tế trong ledger. Dashboard tổng hợp có thể dùng model family để giữ cardinality ổn định; audit cần model ID thực tế.

## 22. PromQL: chi phí theo feature

Giả sử metric counter được xuất thành:

~~~text
app_ai_model_cost_usd_total{feature,provider,model_family,usage_type}
~~~

Chi phí theo feature trong 24 giờ:

~~~promql
sum by (feature) (
  increase(app_ai_model_cost_usd_total[24h])
)
~~~

Chi phí theo feature và model:

~~~promql
sum by (feature, model_family) (
  increase(app_ai_model_cost_usd_total[24h])
)
~~~

Chi phí theo model/provider:

~~~promql
sum by (provider, model_family) (
  increase(app_ai_model_cost_usd_total[24h])
)
~~~

Các query dùng increase() trên counter để tính lượng tăng trong cửa sổ. Với môi trường có nhiều instance, Prometheus xử lý counter reset theo từng series trước khi tổng hợp.

## 23. PromQL: cost rate và cost share

Cost rate theo feature, quy đổi thành USD/giờ:

~~~promql
sum by (feature) (
  rate(app_ai_model_cost_usd_total[5m])
) * 3600
~~~

Tỷ trọng chi phí theo feature trong 24 giờ:

~~~promql
100 *
sum by (feature) (
  increase(app_ai_model_cost_usd_total[24h])
)
/
scalar(
  sum(increase(app_ai_model_cost_usd_total[24h]))
)
~~~

Nếu tổng cost bằng zero hoặc không có sample, panel có thể không có dữ liệu. Dashboard nên xử lý trường hợp này thay vì hiển thị một tỷ lệ giả.

Cost rate hữu ích để quan sát xu hướng ngắn hạn. Cost share hữu ích để xem cơ cấu chi phí. Không dùng cost rate trong 5 phút để suy ra invoice chính xác của cả tháng nếu traffic biến động mạnh.

## 24. PromQL: cost per successful task

Metric tác vụ:

~~~text
app_ai_feature_tasks_total{feature,outcome}
~~~

Cost per successful task trong 24 giờ:

~~~promql
sum by (feature) (
  increase(app_ai_model_cost_usd_total[24h])
)
/
sum by (feature) (
  increase(app_ai_feature_tasks_total{outcome="success"}[24h])
)
~~~

Query này giả định cost counter và task counter dùng cùng feature key, cùng khoảng thời gian và cùng phạm vi traffic.

Nếu denominator bằng zero, kết quả không xác định. Hãy hiển thị no data hoặc N/A thay vì zero USD/task.

Có thể tạo thêm cost per 1.000 tasks:

~~~promql
1000 *
sum by (feature) (
  increase(app_ai_model_cost_usd_total[24h])
)
/
sum by (feature) (
  increase(app_ai_feature_tasks_total[24h])
)
~~~

Chỉ số này bao gồm cả successful và unsuccessful tasks nếu denominator không lọc outcome. Đặt tên panel đúng với mẫu số đang dùng.

## 25. PromQL: input và output cost

Nếu metric có usage_type là input_uncached, input_cached và output:

~~~promql
sum by (feature, usage_type) (
  increase(app_ai_model_cost_usd_total[24h])
)
~~~

Query cho phép nhìn chi phí prompt/context so với generation. Nếu input cost tăng, kiểm tra system prompt, conversation history, RAG context size và tool definitions. Nếu output cost tăng, kiểm tra độ dài response, stop conditions và số lần model được gọi.

Không suy ra input cost bằng cách cộng token counters nếu rate input và cached input khác nhau. Hãy tính cost ở calculator rồi xuất cost counter theo usage type.

## 26. Đặt budget và cảnh báo vượt ngân sách

Budget có thể được quản lý theo feature, model hoặc toàn hệ thống.

Ví dụ budget gauge:

~~~text
app_ai_feature_daily_budget_usd{feature}
app_ai_global_daily_budget_usd
~~~

Query cảnh báo feature vượt budget ngày:

~~~promql
sum by (feature) (
  increase(app_ai_model_cost_usd_total[24h])
)
>
on (feature)
app_ai_feature_daily_budget_usd
~~~

Đây là ví dụ so sánh với gauge budget do ứng dụng/configuration pipeline xuất ra. Hãy đảm bảo budget gauge chỉ có một series cho mỗi feature trong scope query.

Một cảnh báo sớm có thể dự báo chi phí cuối ngày nếu tốc độ hiện tại tiếp tục:

~~~promql
sum by (feature) (
  rate(app_ai_model_cost_usd_total[1h])
) * 86400
>
on (feature)
app_ai_feature_daily_budget_usd
~~~

Forecast tuyến tính giả định cost rate hiện tại giữ nguyên trong ngày. Với traffic theo giờ có tính chu kỳ, hãy so với baseline cùng khung giờ hoặc dùng budget burn model tốt hơn.

Alert cần phân biệt:

- Warning khi dự báo có nguy cơ vượt budget.
- Page/incident khi chi phí tăng bất thường do lỗi vận hành hoặc nguy cơ vượt hard limit.
- Release gate khi candidate prompt/model làm cost per successful task vượt ngưỡng.

## 27. Theo dõi pricing coverage và unknown cost

Không được coi operation không tìm thấy bảng giá là cost bằng zero.

Metric gợi ý:

~~~text
app_ai_unpriced_model_operations_total{provider,model_family}
app_ai_usage_missing_total{provider,model_family}
app_ai_cost_calculation_errors_total{reason}
~~~

Dashboard cần hiển thị:

- Tỷ lệ model operations có usage metadata.
- Tỷ lệ operations có rate card khớp.
- Số operations chưa được định giá.
- Số operations có usage ước tính thay vì actual provider usage.
- Thời điểm pricing catalog được cập nhật gần nhất.

Nếu unknown cost tăng, hãy kiểm tra model ID mới, alias thay đổi, provider mới, region/service tier chưa có rate card hoặc pricing catalog đã hết hiệu lực.

Tổng cost đã tính chỉ là phần có rate card. Nếu có unpriced operations, hiển thị trạng thái incomplete và số lượng tương ứng; không báo tổng đó là toàn bộ spend.

## 28. Kiểm thử cost calculator và attribution

Một bộ test nên kiểm tra:

| Scenario | Kết quả mong đợi |
|---|---|
| Input/output đơn giản | Cost đúng theo rate card |
| Cached input | Dùng cached rate, không tính hai lần |
| Provider báo total input đã gồm cache | Adapter tách uncached/cached đúng |
| Model alias đổi response model | Chọn rate theo billable model thực tế |
| Rate card thay đổi theo ngày | Operation lịch sử dùng effective rate đúng |
| Currency khác USD | Chuyển đổi theo FX rate versioned hoặc giữ currency riêng |
| Model không có rate | Mark unpriced, không coi là zero |
| Retry billable | Ghi từng billed attempt theo ID riêng |
| Consumer nhận event hai lần | Idempotency ngăn cost event trùng |
| Stream không có usage cuối | Mark incomplete/estimated |
| Một operation có nhiều feature | Allocation theo rule, tổng không đổi |
| Feature context mất ở async path | Ghi unknown và tăng diagnostic counter |

Ví dụ test calculator:

~~~java
@Test
void calculatesCachedAndUncachedInputSeparately() {
    var usage = new NormalizedTokenUsage(
        12_000,
        8_000,
        2_000
    );

    var rate = new TokenRate(
        new BigDecimal("2.00"),
        new BigDecimal("0.20"),
        new BigDecimal("8.00"),
        "price-2026-01"
    );

    var actual = new TokenCostCalculator().calculate(usage, rate);

    assertThat(actual).isEqualByComparingTo("0.04160000");
}
~~~

Bộ test thực tế nên bổ sung effective-date resolution, currency, rounding policy và provider-specific usage normalization.

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ xem tổng tiền theo provider | Không biết feature nào gây cost | Gắn feature context |
| Chỉ nhóm theo feature | Không biết model nào làm cost tăng | Dashboard feature/model cross-tab |
| Dùng token count làm cost | Bỏ qua rate khác nhau giữa models | Áp dụng pricing catalog |
| Dùng giá hiện tại cho usage lịch sử | Báo cáo lịch sử sai | Effective date và pricing version |
| Coi unknown model cost là zero | Under-report spend | Ghi unpriced operations |
| Cộng input, cached input và total input | Double count | Chuẩn hóa billable categories |
| Dùng double cho tiền | Sai số tích lũy | BigDecimal và rounding policy |
| Ghi cost cho mỗi stream chunk | Chi phí bị nhân lên | Ghi một event theo final usage |
| Không có operation ID | Retry consumer tạo cost trùng | Idempotent ledger |
| Dùng user/task ID làm metric label | Cardinality cao | Dùng ledger/traces cho chi tiết |
| Gán cost một operation cho nhiều feature | Tổng cost bị nhân | Single owner hoặc weighted allocation |
| Chỉ đo model spend nhưng gọi là total cost | Bỏ qua tool/infra/storage | Tách model cost và feature total cost |
| Không đối soát invoice | Không phát hiện lệch billing | Reconciliation định kỳ |
| Không đo quality theo cost | Tối ưu tiền nhưng giảm chất lượng | Cost per successful task và evaluation |

## 30. Bài tập tự kiểm tra

### Bài 1 — Tính cost theo token

Một model operation dùng 10.000 uncached input tokens, 5.000 cached input tokens và 1.000 output tokens. Giá lần lượt là $1,00, $0,10 và $4,00 trên một triệu tokens. Cost là bao nhiêu?

**Đáp án:** Input thường là $0,01; cached input là $0,0005; output là $0,004. Tổng là $0,0145.

### Bài 2 — Chi phí theo feature

RAG có 2.000 tasks và cost $12; chat có 10.000 tasks và cost $20. Feature nào có cost per task cao hơn?

**Đáp án:** RAG là $0,006/task; chat là $0,002/task. RAG có cost per task cao gấp ba.

### Bài 3 — Model fallback

Feature agent dùng model A cho planner và model B cho final answer. Dashboard theo model cần ghi model nào?

**Đáp án:** Ghi từng model operation theo model thực tế đã xử lý. Tổng feature cost là tổng cost của cả hai operations.

### Bài 4 — Unknown pricing

Một model mới tạo 1.000 operations nhưng chưa có rate card. Có nên ghi cost là zero không?

**Đáp án:** Không. Đánh dấu unpriced, theo dõi số operations và làm rõ rate card. Tổng cost đang incomplete.

### Bài 5 — Cached tokens

Provider báo input total 20.000 tokens, trong đó 8.000 cached tokens. Calculator cần tính uncached input bao nhiêu?

**Đáp án:** 12.000 tokens nếu provider xác nhận cached là tập con của total input. Không trừ lần nữa nếu adapter đã nhận uncached input riêng.

### Bài 6 — Một event được xử lý lại

Cost event bị message broker gửi lại hai lần. Làm sao tránh cộng cost hai lần?

**Đáp án:** Dùng operation/event ID duy nhất và idempotent upsert hoặc unique constraint trong ledger trước khi phát metric aggregate.

### Bài 7 — Cost tăng sau release

Cost/feature tăng 40%, nhưng task volume cũng tăng 40%. Có thể kết luận hiệu quả chi phí giảm không?

**Đáp án:** Chưa. So cost per task hoặc cost per successful task. Nếu hai tỷ lệ ổn định, spend tăng có thể chỉ do workload tăng.

### Bài 8 — Cost giảm nhưng factuality giảm

Một prompt mới giảm cost/task 20% nhưng factuality pass rate giảm từ 96% xuống 88%. Có nên promote?

**Đáp án:** Không nên quyết định chỉ từ cost. Áp dụng quality gate theo rủi ro nghiệp vụ, review failed cases và so trade-off trên cùng dataset.

## 31. Checklist trước khi phát hành dashboard chi phí

- [ ] Mỗi model operation có provider và model thực tế?
- [ ] Usage đã được chuẩn hóa theo billable categories không chồng lấn?
- [ ] Có feature context ở application boundary?
- [ ] Feature context được truyền qua async, streaming và tool loops?
- [ ] Có operation role để phân tích từng bước pipeline?
- [ ] Pricing catalog có version, effective date, currency và source?
- [ ] Có giá input, cached input, output và modality phù hợp?
- [ ] Unknown pricing được đánh dấu riêng?
- [ ] Cost calculator dùng BigDecimal và rounding policy?
- [ ] Cost ledger có operation ID và idempotency?
- [ ] Stream usage chỉ được ghi nhận một lần?
- [ ] Có reconciliation với provider invoice?
- [ ] Metric labels có cardinality hữu hạn?
- [ ] Có dashboard theo feature và model?
- [ ] Có cost per task và cost per successful task?
- [ ] Có budget, forecast và cảnh báo pricing coverage?
- [ ] Có phân biệt model spend với total feature cost?
- [ ] Cost được đối chiếu với relevance, factuality và business success?

## 32. Tài liệu tham khảo

1. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, ChatModel observations, token usage metrics và tags.
2. [Spring AI — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html): ChatResponse metadata và usage information theo provider.
3. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer counters, gauges, timers, tags và Actuator endpoints.
4. [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm event và increment amount.
5. [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): metric names, labels, counters và cardinality.
6. [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): selectors, range vectors, rate và increase.
7. [OpenTelemetry — Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): model identity, provider attributes và token usage conventions.

*Các giá và số liệu trong bài chỉ là ví dụ giả định. Pricing catalog production phải lấy từ nguồn chính thức hoặc hợp đồng của từng provider, lưu thời điểm hiệu lực và được đối soát với invoice. Tên metric/tag cần xác nhận trên registry thực tế; cost ledger là nguồn audit, còn Prometheus/Grafana phục vụ tổng hợp và cảnh báo.*
