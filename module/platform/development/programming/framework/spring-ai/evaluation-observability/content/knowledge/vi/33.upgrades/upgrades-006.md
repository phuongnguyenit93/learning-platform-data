# Nâng cấp: Đánh giá lại khi thay mô hình sinh, embedding hoặc tài liệu

## 1. Vì sao phải đánh giá lại sau mỗi thay đổi?

Một ứng dụng Spring AI thường có nhiều thành phần cùng quyết định chất lượng câu trả lời:

- Chat model tạo câu trả lời, chọn tool và xử lý context.
- Embedding model biến query và nội dung tài liệu thành vector để tìm kiếm ngữ nghĩa.
- Corpus chứa tài liệu, chính sách, dữ liệu nghiệp vụ và metadata được phép truy xuất.
- Document pipeline đọc nguồn, làm sạch, chia chunk, gắn metadata và lập chỉ mục.
- Retriever, filter, reranker và context assembler quyết định bằng chứng nào được đưa vào prompt.
- Prompt, advisor, tool và application policy quyết định model được yêu cầu làm gì với bằng chứng đó.

Thay một thành phần có thể làm thay đổi chất lượng ở những tầng khác. Một chat model mới có thể trả lời tự nhiên hơn nhưng bỏ sót điều kiện trong tài liệu. Một embedding model mới có thể tạo vector có cùng số chiều nhưng thuộc không gian ngữ nghĩa khác. Một bản tài liệu mới có thể sửa chính sách nhưng parser hoặc chunker lại bỏ mất đoạn quan trọng.

Vì vậy, việc nâng cấp cần được xem là một thay đổi của pipeline có thể đo lường. Trước khi mở rộng traffic, nhóm phải biết:

1. Thành phần nào đã thay đổi và thành phần nào được giữ cố định?
2. Bộ dữ liệu nào đại diện cho traffic thực?
3. Candidate cải thiện hoặc suy giảm ở dimension nào?
4. Các lỗi nghiêm trọng, tenant filter và tool behavior có còn an toàn?
5. Latency, token usage, chi phí và khả năng phục vụ thay đổi ra sao?
6. Có thể quay lại model, index và corpus version trước đó không?

**Nguyên tắc:** đánh giá lại đúng phạm vi chịu ảnh hưởng, giữ baseline có thể tái hiện và không trộn các vector space hoặc phiên bản corpus khác nhau trong cùng một lần so sánh.

Bài học thuộc chương **Nâng cấp** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG hoặc tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua từng phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt nâng cấp chat model, embedding model, corpus và document processing pipeline.
- Xây dựng manifest ghi lại phiên bản của toàn bộ pipeline.
- Thiết kế baseline và candidate comparison có kiểm soát.
- Đánh giá generation quality, retrieval quality, groundedness và task success.
- Re-embed corpus khi đổi embedding model hoặc cách tạo chunk.
- Triển khai index mới theo blue-green migration và có đường rollback.
- Dùng Spring AI 2.1.0 với EmbeddingModel, VectorStore.upsert và query-embedding search ở các vector store hỗ trợ.
- Kiểm tra document freshness, chunk coverage, metadata filter và tenant isolation.
- Kết hợp offline evaluation, shadow, canary và production monitoring.
- Quyết định promote, hold hoặc rollback dựa trên quality và operational guardrails.

## 2. Phân biệt ba loại thay đổi

Không phải thay đổi nào cũng cần cùng một quy trình. Trước tiên hãy xác định loại thay đổi.

| Thay đổi | Tác động trực tiếp | Thành phần nên giữ cố định khi đánh giá | Việc cần đánh giá lại |
| --- | --- | --- | --- |
| Chat/generative model | Cách hiểu prompt, reasoning, tool choice, response style | Corpus, embedding, index, retrieved context, prompt và tool contract nếu đang đo riêng model | Relevance, factuality, groundedness, completeness, refusal, tool behavior, latency, cost |
| Embedding model | Không gian vector và thứ tự retrieval | Corpus text, chunking, metadata, filters, retriever parameters | Recall@K, MRR, nDCG, evidence coverage, downstream answer quality |
| Tài liệu/corpus | Evidence, policy, freshness và coverage | Chat model, embedding, chunker, retriever và prompt | Source coverage, stale-content removal, retrieval quality, citation correctness, answer quality |
| Parser/chunker/metadata pipeline | Nội dung và đơn vị được index | Source snapshot, embedding model và query behavior | Chunk integrity, token coverage, retrieval metrics và downstream answer quality |
| Vector database/index configuration | Approximate search, filtering và ranking | Embedding vectors và corpus snapshot | Recall/latency, filter correctness, index recall, capacity |
| Nhiều thành phần cùng thay | Nhiều nguồn thay đổi tương tác | Giữ một baseline chung và tạo các candidate tách biệt | Đánh giá từng thay đổi trước, sau đó đánh giá tổ hợp |

### 2.1. Nâng cấp chat model

Nếu mục tiêu là biết model B có tốt hơn model A không, hãy đưa cùng input và cùng context snapshot cho cả hai model. Giữ nguyên prompt, tool definitions, output schema, advisor chain và evaluator.

Nếu vừa đổi model, prompt, retriever và corpus, một kết quả tốt hơn không cho biết yếu tố nào tạo ra cải thiện. Khi có thể, thay từng yếu tố trong các experiment riêng, sau đó mới kiểm tra tổ hợp.

### 2.2. Nâng cấp embedding model

Embedding model mới thường yêu cầu tạo lại vector cho toàn bộ corpus. Vector của model cũ và model mới không thể mặc nhiên so sánh với nhau, ngay cả khi cả hai có cùng số chiều.

Cần tạo một index hoặc collection mới cho candidate, embed lại document chunks bằng cùng embedding pipeline mà query side sẽ dùng, rồi đánh giá retrieval trên query set đã gắn nhãn.

### 2.3. Nâng cấp tài liệu

Nếu chỉ cập nhật một số source documents mà parser và chunking không đổi, có thể reprocess phần thay đổi theo source version. Nếu thay parser, normalization, metadata extraction hoặc chunking, cần xem đó là một thay đổi rộng hơn và đánh giá lại toàn bộ corpus đã xử lý.

Đặc biệt, khi source mới thay thế policy cũ, phải xác minh document cũ được cập nhật hoặc loại khỏi index. Chỉ thêm tài liệu mới có thể khiến retriever tiếp tục trả cả hai phiên bản.

## 3. Tách phiên bản ứng dụng, model và corpus

Một release manifest cần nhận diện được đúng pipeline đã phục vụ một interaction. Không dùng một chuỗi version chung như ai-v12 cho mọi thứ.

| Thành phần | Ví dụ định danh | Thông tin cần lưu |
| --- | --- | --- |
| Application | build-2026.11.27.4 | Commit, dependency lock, runtime config |
| Spring AI | 2.1.0 | Artifact version, Spring Boot compatibility |
| Chat model | provider/model-revision | Provider, model ID, deployment revision, parameters |
| Prompt | support-prompt-v18 | Template hash, variables schema, system instruction version |
| Embedding | embedder-v7 | Provider/model revision, dimensions, input type, preprocessing |
| Corpus | policy-corpus-2026-11-27 | Source snapshot, effective dates, document versions |
| Parser | pdf-parser-v4 | Reader, extraction rules, OCR version |
| Chunker | chunker-v6 | Splitter, size, overlap, normalization |
| Index | support-index-embed-v7-corpus-2026-11 | Vector dimensions, distance metric, index settings |
| Retriever | retriever-v9 | Top K, threshold, metadata filters, reranker |
| Evaluator | judge-v5-rubric-v8 | Judge model, prompt, rubric và calibration dataset |

### 3.1. Pipeline fingerprint

Có thể tạo fingerprint từ manifest đã canonicalize:

~~~json
{
  "applicationBuild": "build-2026.11.27.4",
  "springAiVersion": "2.1.0",
  "chat": {
    "provider": "provider-a",
    "model": "chat-model-b",
    "revision": "revision-42",
    "promptVersion": "support-prompt-v18",
    "temperature": 0.1,
    "maxOutputTokens": 1200
  },
  "embedding": {
    "provider": "provider-a",
    "model": "embedding-model-c",
    "revision": "revision-7",
    "dimensions": 1024,
    "documentInputMode": "DOCUMENT",
    "queryInputMode": "QUERY"
  },
  "corpus": {
    "snapshot": "policy-corpus-2026-11-27",
    "parserVersion": "pdf-parser-v4",
    "chunkerVersion": "chunker-v6",
    "chunkSize": 700,
    "chunkOverlap": 80
  },
  "retrieval": {
    "indexVersion": "support-index-v7",
    "topK": 8,
    "rerankerVersion": "reranker-v3"
  },
  "evaluation": {
    "datasetVersion": "support-golden-v12",
    "rubricVersion": "quality-v8",
    "judgeVersion": "judge-v5"
  }
}
~~~

Các giá trị trên chỉ là ví dụ. Fingerprint giúp nối kết quả benchmark, traces và release decision với cấu hình thực tế. Không đưa secrets, API keys hoặc raw user data vào manifest.

### 3.2. Pin version trong từng lần đánh giá

Mỗi evaluation run nên ghi:

- Run ID, timestamp và environment.
- Baseline fingerprint và candidate fingerprint.
- Dataset version và case versions.
- Evaluator/rubric version.
- Random seed hoặc sampling configuration nếu provider hỗ trợ.
- Run order, số lần lặp và retry policy.
- Kết quả theo case, dimension và task family.
- Model usage, latency và estimated cost.

Nếu evaluator hoặc rubric đổi giữa hai lần chạy, score difference có thể đến từ evaluator chứ không phải candidate. Khi cần nâng cấp judge, tạo một calibration experiment riêng.

## 4. Thiết kế baseline và candidate comparison

Baseline là phiên bản đang được chấp nhận. Candidate là cấu hình chuẩn bị nâng cấp.

Một baseline tốt phải:

- Có manifest đầy đủ.
- Có dataset version và labels đã xác minh.
- Có các critical regression cases.
- Có retrieval snapshots hoặc source snapshots cần thiết.
- Có operational baseline về latency, error rate, token usage và cost.
- Có decision record cho các threshold đang áp dụng.

Không lấy một run ngẫu nhiên gần nhất làm baseline nếu run đó thiếu coverage hoặc evaluator version khác.

### 4.1. Paired evaluation

Khi so sánh hai model hoặc hai retriever, chạy cùng một test case trên cả baseline và candidate. Như vậy, khác biệt của input được kiểm soát và có thể phân tích delta theo case.

Với generation model có sampling, có thể chạy nhiều lần trên cùng case và randomize thứ tự gọi baseline/candidate để giảm ảnh hưởng của thời điểm, provider load hoặc quota. Ghi mọi attempt, không chỉ lần chạy có kết quả đẹp.

### 4.2. Giữ evaluator ổn định

Trong một experiment:

- Dùng cùng evaluator model, prompt và rubric.
- Dùng cùng normalization trước khi đánh giá.
- Không để evaluator biết candidate nào đang được ưu tiên nếu có thể blind variant.
- Có human-reviewed sample để kiểm tra judge drift.
- Đánh dấu INCONCLUSIVE khi thiếu evidence hoặc evaluator không đủ chắc chắn.

Nếu đổi judge cùng lúc với chat model, kết quả quality không còn so sánh trực tiếp. Chạy một calibration set độc lập để xác định judge mới có giữ được agreement với human labels không.

### 4.3. Phân tầng theo task family

Overall score có thể che giấu regression ở một nhóm nhỏ. Phân tích riêng:

- RAG question answering.
- Direct chat không cần retrieval.
- Câu hỏi cần nhiều tài liệu.
- Câu hỏi thiếu evidence.
- Tool calling.
- Structured output.
- Tiếng Việt, tiếng Anh và các locale đang hỗ trợ.
- Tài liệu mới, cũ, dài, scan/OCR hoặc có bảng.
- Các nhóm tenant hoặc permission scope theo policy.

Giữ các strata đã định nghĩa trước khi chạy. Không chỉ báo cáo subgroup có kết quả tốt.

## 5. Đánh giá chất lượng theo từng dimension

Không kết luận nâng cấp tốt chỉ dựa vào một điểm tổng hợp.

| Dimension | Câu hỏi đánh giá | Metric hoặc oracle |
| --- | --- | --- |
| Relevance | Response có trả lời đúng intent? | Relevance pass rate/score |
| Factuality | Claim có đúng theo evidence? | Fact-check defect rate |
| Groundedness | Claim có được context hỗ trợ? | Supported-claim rate |
| Completeness | Có bỏ sót điều kiện hoặc bước cần thiết? | Rubric score, required-fact coverage |
| Citation | Nguồn trích dẫn có hỗ trợ claim? | Citation precision/coverage |
| Abstention | Có từ chối suy đoán khi thiếu evidence? | Correct abstention rate |
| Tool correctness | Chọn đúng tool và arguments? | Tool selection/argument pass rate |
| Safety | Có vi phạm policy hoặc permission? | Critical violation count |
| Task success | Người dùng có hoàn thành mục tiêu? | Verified task success rate |
| Latency | Thời gian phản hồi thay đổi ra sao? | p50/p95/p99, TTFT |
| Reliability | Timeout, error, rate limit có tăng? | Error/timeout rate |
| Cost | Chi phí cho mỗi task thành công? | Cost/request và cost/success |

### 5.1. Không gộp các lỗi nghiêm trọng vào điểm trung bình

Một candidate có thể tăng relevance nhưng đồng thời tạo một cross-tenant leak. Điểm relevance cao không bù được lỗi an toàn.

Các critical assertions nên là hard gates:

- Không trả dữ liệu của tenant khác.
- Không thực thi tool khi thiếu quyền hoặc confirmation.
- Không tuyên bố một giao dịch hoàn tất khi tool chưa xác nhận.
- Không biến nội dung không tin cậy trong retrieved document thành system instruction.
- Không tiết lộ secrets hoặc dữ liệu bị cấm.

### 5.2. Retrieval metrics

Với query có tập relevant documents đã gắn nhãn:

\[
Recall@K = \frac{|Relevant \cap Retrieved_K|}{|Relevant|}
\]

MRR đo vị trí của kết quả relevant đầu tiên:

\[
MRR = \frac{1}{N}\sum_{i=1}^{N}\frac{1}{rank_i}
\]

nDCG đánh giá chất lượng ranking khi relevance có nhiều mức:

\[
DCG@K = \sum_{i=1}^{K}\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

\[
nDCG@K = \frac{DCG@K}{IDCG@K}
\]

Không tính retrieval recall từ một answer judge không có expected document labels. Cần query set có relevance judgments hoặc evidence references đã xác minh.

### 5.3. End-to-end quality

Sau khi retrieval được đánh giá riêng, chạy RAG end-to-end với cùng chat model/prompt để đo ảnh hưởng thực tế lên câu trả lời. Retrieval tốt hơn chưa chắc answer tốt hơn nếu context bị nhiễu, dài hoặc chứa tài liệu mâu thuẫn.

## 6. Nâng cấp chat/generative model

Chat model quyết định cách diễn giải câu hỏi, sử dụng context, tạo câu trả lời và chọn tool. Khi thay model, hãy tách kiểm tra generation khỏi retrieval.

### 6.1. Giữ context giống nhau

Với mỗi case, tạo một immutable context snapshot. Gửi cùng:

- User query.
- Conversation history.
- Retrieved documents và thứ tự.
- Tool definitions và tool fixture results.
- System/developer prompt.
- Output schema và generation constraints.

Chỉ đổi chat model. Điều này giúp xác định model mới có sử dụng cùng evidence tốt hơn hay không.

### 6.2. Những behavior cần kiểm tra

- Response có đúng ngôn ngữ và tone không?
- Có giữ các điều kiện, số liệu và ngoại lệ quan trọng không?
- Có tạo claim ngoài context không?
- Có biết abstain khi evidence thiếu hoặc mâu thuẫn không?
- Có tuân thủ structured output schema không?
- Có chọn đúng tool và arguments không?
- Có xử lý tool error/timeout đúng không?
- Có thay đổi refusal behavior hoặc safety behavior không?
- Có giữ streaming và finish reason phù hợp không?
- Có đáp ứng context window và output token budget không?

Một model mới có thể có context window lớn hơn, nhưng không nên tự động tăng lượng context gửi vào. Context dài hơn có thể tăng chi phí và đưa thêm thông tin nhiễu.

### 6.3. So sánh cùng một prompt

Ví dụ tạo hai ChatClient từ hai ChatModel:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ModelComparisonConfiguration {

    @Bean
    @Qualifier("baselineChatClient")
    ChatClient baselineChatClient(
            @Qualifier("baselineChatModel") ChatModel model) {
        return ChatClient.builder(model).build();
    }

    @Bean
    @Qualifier("candidateChatClient")
    ChatClient candidateChatClient(
            @Qualifier("candidateChatModel") ChatModel model) {
        return ChatClient.builder(model).build();
    }
}
~~~

Một runner có thể đưa cùng rendered input/context vào hai client:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Qualifier;

import java.util.List;

public record ModelOutput(
        String variant,
        String answer) {
}

public class PairedGenerationRunner {

    private final ChatClient baseline;
    private final ChatClient candidate;

    public PairedGenerationRunner(
            @Qualifier("baselineChatClient") ChatClient baseline,
            @Qualifier("candidateChatClient") ChatClient candidate) {
        this.baseline = baseline;
        this.candidate = candidate;
    }

    public List<ModelOutput> compare(EvaluationCase testCase) {
        String baselineAnswer = invoke(baseline, testCase);
        String candidateAnswer = invoke(candidate, testCase);

        return List.of(
                new ModelOutput("baseline", baselineAnswer),
                new ModelOutput("candidate", candidateAnswer));
    }

    private String invoke(ChatClient client, EvaluationCase testCase) {
        return client.prompt()
                .system(testCase.systemPrompt())
                .user(testCase.renderedUserMessageWithPinnedContext())
                .call()
                .content();
    }
}
~~~

Đây là skeleton minh họa. EvaluationCase và cách render context do ứng dụng định nghĩa. Khi dùng advisors, bảo đảm cả hai client nhận cùng context snapshot và cùng advisor configuration. Nếu cần so sánh tool calling, dùng tool fixtures có kết quả xác định và ghi tool invocations riêng.

### 6.4. Đánh giá tool behavior độc lập

So sánh:

- Tool name được đề xuất.
- Arguments sau validation.
- Authorization decision.
- Số lần gọi và retry.
- Tool result/error.
- Final answer sau tool result.

Không chỉ so final answer. Model có thể tạo câu trả lời đúng tình cờ dù đã gọi nhầm tool hoặc dùng sai tenant scope.

### 6.5. Theo dõi token usage và chi phí

Ghi token input/output, cache usage nếu provider cung cấp, số lần model call trong tool loop, latency và rate limit metadata. Một câu trả lời ngắn hơn không nhất thiết rẻ hơn nếu model cần nhiều vòng tool hoặc retry hơn.

Spring AI cung cấp ChatResponse metadata và Usage cho những provider có trả usage. Với multi-step tool flow, usage có thể được cộng dồn qua các lần gọi model; khi cần phân tích chi tiết từng lần gọi, ghi observations ở model-call boundary.

## 7. Nâng cấp embedding model: điều gì thay đổi?

Embedding model ánh xạ text sang vector. Thay model có thể làm thay đổi:

- Vector dimensions.
- Vector space và phân bố khoảng cách.
- Cách hiểu ngữ nghĩa đa ngôn ngữ.
- Cách xử lý query và document input.
- Prefix/instruction cho query và document.
- Normalization.
- Tokenization và giới hạn input.
- Metadata được đưa vào nội dung embedding.
- Batch size, rate limit, latency và cost.

### 7.1. Dimension giống nhau không có nghĩa là tương thích

Hai model có thể cùng trả vector 1024 chiều nhưng mỗi tọa độ biểu diễn một không gian khác. Nếu ghi vector từ model B vào index đang chứa vector model A, hệ thống có thể vẫn nhận dữ liệu vì độ dài khớp, nhưng similarity search sẽ trả kết quả vô nghĩa.

Một index nên chứa vector từ một embedding space version nhất quán. Không trộn embedding của hai model chỉ vì database không báo lỗi.

### 7.2. Document encoder và query encoder phải tương thích

Nếu provider dùng cấu hình riêng cho document và query, phải dùng đúng input mode tương ứng. Query vector cần cùng embedding space với document vectors đã index.

Manifest nên ghi:

- Embedding model và immutable revision nếu provider hỗ trợ.
- Dimensions.
- Document input type/prefix.
- Query input type/prefix.
- Metadata mode.
- Text normalization.
- Truncation/batching policy.
- Vector normalization và distance metric.

### 7.3. Re-embed toàn bộ corpus

Khi thay embedding model, quy trình thông thường là:

1. Chốt source/corpus snapshot.
2. Tạo collection/index mới có dimensions và metric phù hợp.
3. Chạy cùng parser/chunker hiện tại để tạo document chunks.
4. Embed toàn bộ chunks bằng candidate model.
5. Ghi vector và metadata vào candidate index.
6. Tạo query embeddings bằng chính candidate embedding pipeline.
7. Đánh giá retrieval và end-to-end RAG.
8. Shadow query và so kết quả.
9. Chuyển traffic sang index mới khi đạt gate.

Không cập nhật một phần index bằng embedding model mới trong khi phần còn lại vẫn là vector cũ, trừ khi kiến trúc có partition/vector-space routing được kiểm soát rõ ràng.

## 8. EmbeddingModel và vector-store API trong Spring AI 2.1.0

Spring AI 2.1.0 cung cấp API để ứng dụng tự tính vector và ghi/search vector đã tính trước ở các vector store có hỗ trợ.

### 8.1. EmbeddingModel

Các phương thức thường dùng:

~~~java
float[] documentVector = embeddingModel.embed(document);
float[] queryVector = embeddingModel.embed(queryText);
int dimensions = embeddingModel.dimensions();
~~~

Lưu ý: dimensions() mặc định có thể embed một test string để suy ra chiều vector. Nếu model/provider có latency hoặc tính phí cho embedding call, đừng gọi method này lặp lại trong request path. Có thể pin dimensions trong manifest hoặc override/cấu hình theo implementation đã xác minh.

Batched embedding có thể sử dụng EmbeddingModel và BatchingStrategy để chia batch theo giới hạn API. Kiểm tra thứ tự vector trả về phải khớp thứ tự documents trước khi ghép từng vector với document tương ứng.

### 8.2. VectorStore.upsert với vector đã tính

Spring AI 2.1.0 định nghĩa EmbeddedDocument để ghép Document với vector:

~~~java
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.EmbeddedDocument;
import org.springframework.ai.vectorstore.VectorStore;

import java.util.List;

public class CandidateIndexer {

    private final EmbeddingModel candidateEmbeddingModel;
    private final VectorStore candidateVectorStore;

    public CandidateIndexer(
            EmbeddingModel candidateEmbeddingModel,
            VectorStore candidateVectorStore) {
        this.candidateEmbeddingModel = candidateEmbeddingModel;
        this.candidateVectorStore = candidateVectorStore;
    }

    public void index(List<Document> documents) {
        List<EmbeddedDocument> entries = documents.stream()
                .map(document -> new EmbeddedDocument(
                        document,
                        candidateEmbeddingModel.embed(document)))
                .toList();

        candidateVectorStore.upsert(entries);
    }
}
~~~

Đây là ví dụ cho vector store có hỗ trợ upsert. API này opt-in theo implementation; kiểm tra store đang dùng trước khi thiết kế migration. Stable document IDs giúp một lần chạy lại thay thế row tương ứng thay vì tạo duplicate. Nếu một batch upsert ném exception, coi trạng thái batch là chưa xác định vì backend có thể đã ghi một phần; retry toàn batch chỉ an toàn khi giữ nguyên IDs và replace-by-id semantics.

### 8.3. Search bằng query embedding

Khi index đã được ghi bằng candidate vectors, query cũng phải được embed bằng candidate model:

~~~java
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;

float[] queryVector = candidateEmbeddingModel.embed(queryText);

SearchRequest request = SearchRequest.builder()
        .topK(8)
        .similarityThreshold(0.65)
        .filterExpression("tenant == 'tenant-fixture-a'")
        .build();

List<Document> results =
        candidateVectorStore.similaritySearch(queryVector, request);
~~~

Ví dụ dùng filter fixture. Trong ứng dụng thực, tenant filter phải được tạo từ authenticated security context và filter builder phù hợp; không nối trực tiếp input người dùng vào filter expression.

Query-embedding search cũng opt-in theo vector store. Nếu store không hỗ trợ, dùng đường search text mặc định với EmbeddingModel được cấu hình đúng cho candidate index.

### 8.4. Kiểm tra width và vector space

Spring AI/vector store có thể kiểm tra vector width khi index biết dimension. Tuy nhiên, width đúng không chứng minh vector thuộc cùng embedding space. Lưu embedding model/version trong metadata hoặc index manifest để audit.

Một vector store có thể chuẩn hóa vector khi lưu, vì vậy không nhất thiết đọc lại native vector sẽ nhận đúng các số float ban đầu. Điều cần kiểm tra là model/space, dimension, metric và retrieval behavior.

## 9. Đánh giá retrieval khi đổi embedding model

Dùng query set có labels về tài liệu hoặc chunks cần tìm. Với mỗi query, chạy baseline và candidate trên cùng corpus snapshot.

### 9.1. Retrieval parity dataset

Một query case nên giữ:

- Query text và locale.
- Tenant/security scope.
- Relevant document/chunk IDs.
- Forbidden/stale document IDs.
- Expected metadata filters.
- Task family.
- Source version và valid time.
- Expected evidence requirements.

Có các case cho query ngắn, query dài, synonym, paraphrase, typo, đa ngôn ngữ, câu hỏi nhiều ý và câu hỏi không có tài liệu hỗ trợ.

### 9.2. So sánh top K

Báo cáo:

- Recall@K.
- MRR.
- nDCG@K.
- Precision@K nếu có labels phù hợp.
- Empty retrieval rate.
- Stale/forbidden document rate.
- Required evidence coverage.
- Duplicate chunk rate.
- Latency p50/p95/p99.
- Cost và embedding tokens/query.

Không chỉ xem overlap giữa top K của hai model. Hai model có thể trả hai tập khác nhau nhưng cả hai đều relevant; cũng có thể trả cùng kết quả sai. Ground-truth relevance labels mới là oracle chính.

### 9.3. Đánh giá end-to-end sau retrieval

Sau retrieval benchmark, dùng candidate retriever context để chạy cùng chat model/prompt. Đo relevance, groundedness, factuality, completeness, citation và abstention.

Nếu retrieval metric tăng nhưng answer quality giảm, kiểm tra context noise, chunk size, ordering, reranker và prompt context budget.

## 10. Nâng cấp tài liệu/corpus

Thay corpus có thể là thêm tài liệu, cập nhật nội dung, xóa nguồn cũ hoặc thay đổi cách đọc dữ liệu.

### 10.1. Phân loại thay đổi nguồn

| Thay đổi | Cách xử lý |
| --- | --- |
| Thêm source mới | Parse, chunk, embed và index source mới; kiểm tra quyền truy cập |
| Sửa nội dung source | Tạo source version mới, reprocess chunks và cập nhật index |
| Xóa/thu hồi source | Ghi tombstone/delete và xác minh không còn kết quả retrieval |
| Chính sách đổi ngày hiệu lực | Lưu validFrom/validTo, kiểm tra câu hỏi theo thời điểm |
| Parser/OCR đổi | Reprocess tài liệu chịu ảnh hưởng hoặc toàn bộ corpus theo phạm vi parser |
| Chunking/overlap đổi | Re-chunk và re-embed toàn bộ corpus thuộc pipeline mới |
| Metadata/filter schema đổi | Backfill metadata, kiểm tra filter parity và authorization |
| Thay source owner/trust level | Revalidate provenance và quyết định có được dùng làm evidence không |

### 10.2. Giữ document identity và source version

Một document nên có stable source identity và source version riêng. Chunk ID có thể được tạo từ source ID, source version, chunking version và chunk position/content hash.

Khi source đổi, không để chunk cũ tiếp tục xuất hiện như thể thuộc version mới. Khi số chunks giảm, phải xóa các chunk dư đã không còn trong manifest candidate.

### 10.3. Metadata là một phần của retrieval contract

Metadata thường quyết định:

- Tenant isolation.
- Product/region/language scope.
- Document type.
- Source owner/trust.
- Effective dates.
- Access permissions.
- Document version.
- Citation references.

Khi thay metadata schema, kiểm tra cả dữ liệu cũ và mới. Một filter không tương thích có thể trả thiếu evidence hoặc vượt quyền dù embedding vẫn đúng.

## 11. Nâng cấp parser, chunker và context assembly

Một corpus tốt có thể bị giảm chất lượng nếu document processing pipeline thay đổi.

### 11.1. Parser và extraction

Kiểm tra:

- PDF scan/OCR có bị mất bảng hoặc tiêu đề không?
- HTML boilerplate có bị đưa vào chunks không?
- Markdown heading hierarchy có được giữ?
- Code blocks, tables và numbered clauses có bị cắt giữa nội dung không?
- Encoding, Unicode và tiếng Việt có bị chuẩn hóa sai?
- Page/section references có được giữ trong metadata?
- Document reader có giới hạn kích thước hoặc truncation không?

### 11.2. Chunking

Chunk size và overlap ảnh hưởng đến:

- Khả năng giữ nguyên ý nghĩa.
- Số lượng vector và chi phí indexing.
- Context length.
- Duplicate retrieval.
- Recall của các điều kiện nằm sát ranh giới chunk.

Khi đổi chunk size hoặc overlap, tạo index version mới và đánh giá lại retrieval. Spring AI 2.1.0 hỗ trợ opt-in chunk overlap trong TokenTextSplitter; overlap làm tăng lượng nội dung lặp và cần đo chi phí, không nên bật chỉ vì nó có sẵn.

### 11.3. Metadata mode và embedding content

EmbeddingModel.getEmbeddingContent(Document) quyết định nội dung được gửi vào embedding model. Một số implementation hỗ trợ MetadataMode và có thể đưa metadata vào formatted content. Nếu metadata mode thay đổi, vector cũng thay đổi dù document text không đổi.

Ghi rõ mode và formatter trong manifest. Tránh đưa các metadata không ổn định như timestamp crawl hoặc internal ID vào embedding text nếu chúng không có ý nghĩa ngữ nghĩa.

## 12. Blue-green migration cho embedding/index mới

Khi đổi embedding model hoặc thay đổi rộng corpus pipeline, xây candidate index riêng giúp rollback rõ ràng.

~~~mermaid
flowchart TD
    A["Freeze baseline manifest and corpus snapshot"] --> B["Create candidate collection/index"]
    B --> C["Re-parse / re-chunk / re-embed"]
    C --> D["Backfill candidate index"]
    D --> E["Validate count, dimensions, metadata and ACL"]
    E --> F["Replay labeled retrieval queries"]
    F --> G{"Quality and operational gates pass?"}
    G -->|No| H["Fix candidate or abandon"]
    G -->|Yes| I["Shadow query against candidate"]
    I --> J["Compare results and latency"]
    J --> K{"Shadow gates pass?"}
    K -->|No| H
    K -->|Yes| L["Switch alias or routing flag"]
    L --> M["Canary traffic"]
    M --> N{"Production guardrails pass?"}
    N -->|No| O["Route back to baseline index"]
    N -->|Yes| P["Promote candidate and retain old index"]
~~~

### 12.1. Các bước migration

1. Chốt corpus snapshot và watermark của source change log.
2. Tạo candidate collection/index với dimension, distance metric và metadata schema mới.
3. Chạy parser/chunker/embedding pipeline theo manifest candidate.
4. Ghi toàn bộ candidate documents và vectors.
5. Đồng bộ các source changes phát sinh sau watermark.
6. Kiểm tra document count, chunk count, vector width, null/NaN, duplicate IDs và metadata.
7. Chạy retrieval benchmark và security/filter tests.
8. Shadow query bằng candidate retriever.
9. So sánh quality, latency, empty retrieval và cost.
10. Chuyển alias hoặc routing configuration sang candidate.
11. Canary theo tenant/cohort/traffic percentage.
12. Giữ index cũ đủ lâu để rollback và hoàn tất release review.

Nếu vector database không hỗ trợ alias, dùng routing layer hoặc feature flag để chọn collection. Việc chuyển route phải nhất quán cho cả query embedding và index tương ứng.

### 12.2. Không trộn vector space trong một index

Không dual-write vector cũ và mới vào cùng một collection rồi để query chọn một model bất kỳ. Cùng dimension không có nghĩa tương thích. Nếu cần dual-write, mỗi embedding version phải ghi vào collection/partition riêng có contract riêng.

### 12.3. Đồng bộ thay đổi trong lúc backfill

Nếu corpus tiếp tục thay đổi trong khi reindex, candidate có thể thiếu cập nhật mới. Dùng source event log, CDC hoặc một cơ chế watermark để:

- Backfill snapshot tại thời điểm T0.
- Phát lại các changes sau T0.
- Xử lý update/delete idempotently.
- Xác minh candidate đã bắt kịp trước cutover.

Không chuyển traffic khi candidate chưa đồng bộ tới watermark được chấp nhận.

### 12.4. Stable IDs và retry

Dùng deterministic IDs để một lần upsert retry không tạo duplicate. Ghi checkpoint theo batch và source version. Với document bị chia lại thành số chunks khác, reconcile danh sách chunk IDs cũ/mới và xóa những IDs không còn tồn tại trong candidate.

## 13. Shadow evaluation và canary

Offline evaluation không phản ánh đầy đủ query distribution và serving conditions production. Sau khi candidate đạt offline gates, có thể dùng shadow và canary.

### 13.1. Shadow cho chat model

Gửi cùng input/context snapshot tới candidate model nhưng chỉ baseline response được trả cho user. Lưu candidate response trong secure evidence store và đánh giá async.

Shadow candidate cần dùng cùng tool fixtures hoặc tắt tool execution. Không để candidate gửi email, thanh toán hoặc cập nhật hồ sơ thật chỉ để so sánh output.

### 13.2. Shadow cho embedding/retrieval

Chạy query qua baseline và candidate index trong cùng request path hoặc async copy. So document IDs, ranks, scores, filters, latency và empty retrieval. Candidate retrieval không được thay đổi response user cho đến khi được promote.

Giữ cùng tenant filter và permission context cho cả hai index. Không được dùng shadow để truy vấn rộng hơn quyền của request gốc.

### 13.3. Canary

Sau shadow, route một cohort nhỏ tới candidate. Gán cohort ổn định theo session/user/tenant tùy state và memory requirements. Theo dõi:

- Quality labels hoặc calibrated proxy.
- Retrieval coverage và citation correctness.
- Error/timeout/fallback.
- p95 latency và TTFT.
- Token usage và cost per successful task.
- Tool failures và safety violations.
- Subgroup regressions.

Không tăng traffic chỉ vì không có alert. Cần đủ exposure và label maturity theo experiment plan.

## 14. Đặt acceptance gates

Mỗi migration cần threshold được phê duyệt trước khi chạy. Ví dụ dưới đây chỉ minh họa cách viết policy, không phải threshold mặc định.

| Gate | Ví dụ điều kiện | Hành động nếu fail |
| --- | --- | --- |
| Critical safety | Không có cross-tenant leak hoặc unauthorized side effect | Block ngay |
| Factuality | Không tăng critical unsupported claim | Block hoặc review |
| Retrieval recall | Lower confidence bound không thấp hơn baseline quá margin đã định | Giữ candidate |
| Relevance | Không giảm quá non-inferiority margin | Giữ candidate |
| Citation | Required citations vẫn trỏ đúng source | Block nếu lỗi critical |
| Latency | p95 không vượt budget | Tối ưu hoặc rollback |
| Cost | Cost/success không vượt budget đã duyệt | Review business case |
| Reliability | Timeout/error rate không vượt error budget | Pause rollout |
| Coverage | Đủ sample và labels mature | Chờ thêm dữ liệu |

### 14.1. Non-inferiority

Nếu mục tiêu là thay model mà không làm chất lượng giảm đáng kể, đặt margin trước experiment.

Gọi delta là candidate score trừ baseline score. Với metric càng cao càng tốt, chỉ promote khi lower confidence bound của delta lớn hơn mức âm cho phép:

\[
LCB(\Delta) > -\delta_{NI}
\]

Trong đó delta NI là non-inferiority margin do product/domain owner phê duyệt. Với metric càng thấp càng tốt như error rate hoặc latency, đảo chiều phép so sánh.

### 14.2. Sample size và confidence

Không kết luận từ vài chục case nếu metric có variance lớn. Sample size phụ thuộc baseline, minimum detectable effect, alpha, power, allocation và clustering. Với nhiều interactions từ cùng user, cần tính dependency hoặc phân tích theo assignment unit.

Nếu sample chưa đủ, trạng thái là INCONCLUSIVE. Không đổi thành PASS chỉ vì candidate score hiện tại cao hơn.

### 14.3. Subgroup gates

Một candidate có thể cải thiện tiếng Anh nhưng suy giảm tiếng Việt, hoặc cải thiện câu hỏi đơn giản nhưng lỗi ở multi-document queries. Báo cáo theo các strata có ý nghĩa nghiệp vụ và đặt critical subgroup gates trước khi chạy.

## 15. Đo latency, cost và capacity sau nâng cấp

Quality improvement có thể đi kèm latency hoặc cost tăng. Đo cả per-call và per-successful-task.

### 15.1. Latency

Theo dõi:

- Embedding query latency.
- Vector search latency.
- Reranking latency.
- Chat model first-token latency.
- Total generation latency.
- Tool call latency.
- End-to-end request latency.
- Queueing và retry time.

Đừng so latency của một model call với latency toàn bộ RAG pipeline. Định nghĩa rõ boundary và dùng cùng load profile.

### 15.2. Cost

Một công thức đơn giản:

\[
Cost_{task} =
Cost_{embedding} +
Cost_{retrieval} +
Cost_{reranking} +
Cost_{generation} +
Cost_{tools} +
Cost_{retry}
\]

Đối với embedding migration, tính cả chi phí backfill/indexing và chi phí serving query trong khoảng thời gian dự kiến. Có thể amortize migration cost theo số query dự kiến, nhưng phải báo riêng one-time migration cost.

### 15.3. Cost per successful task

\[
CostPerSuccess = \frac{TotalCost}{SuccessfulTasks}
\]

Một model rẻ hơn trên mỗi call có thể đắt hơn trên mỗi task thành công nếu phải retry nhiều hoặc trả lời sai khiến người dùng hỏi lại.

## 16. Observability trong Spring AI

Spring AI cung cấp observations/metrics cho ChatClient, ChatModel, EmbeddingModel và VectorStore. Khi so sánh candidate, bổ sung pipeline version vào application-level telemetry theo cardinality phù hợp.

### 16.1. Ghi version và operation

Ghi các thuộc tính:

- Model/provider revision.
- Embedding version.
- Corpus/index version.
- Retriever configuration.
- Prompt version.
- Evaluation run/dataset version.
- Operation type và outcome.
- Latency, tokens và estimated cost.

Dùng metric labels có cardinality thấp như model family, deployment cohort, index version đang active và operation. Các ID duy nhất như trace ID, interaction ID, raw query và prompt content thuộc trace/evidence store có kiểm soát, không đưa vào metric labels.

### 16.2. Spring AI observations

Observations có thể giúp điều tra thời gian ChatClient, ChatModel, EmbeddingModel và VectorStore. Prompt/completion content không được export mặc định vì có thể chứa dữ liệu nhạy cảm. Chỉ bật content logging trong phạm vi debug được kiểm soát và có retention/access policy.

### 16.3. Metrics gợi ý

| Metric | Mục đích |
| --- | --- |
| ai_upgrade_requests_total | Traffic theo baseline/candidate |
| ai_upgrade_evaluated_total | Số interaction có evaluation result |
| ai_upgrade_retrieval_recall | Retrieval quality từ evaluation runs |
| ai_upgrade_relevance_pass_total | Số case relevance pass |
| ai_upgrade_groundedness_fail_total | Số groundedness failures |
| ai_upgrade_empty_retrieval_total | Query không có evidence |
| ai_upgrade_embedding_duration_seconds | Embedding latency |
| ai_upgrade_vector_search_duration_seconds | Vector search latency |
| ai_upgrade_generation_duration_seconds | Generation latency |
| ai_upgrade_tokens_total | Token usage |
| ai_upgrade_cost_estimated_total | Estimated cost |
| ai_upgrade_fallback_total | Candidate fallback |
| ai_upgrade_critical_violation_total | Critical safety/tool violations |

Các metric trên là custom application metrics. Không xem chúng là tên metric mặc định của Spring AI.

### 16.4. So sánh bằng PromQL

Request rate theo variant:

~~~promql
sum by (variant) (
  rate(ai_upgrade_requests_total[15m])
)
~~~

Candidate request share:

~~~promql
sum(rate(ai_upgrade_requests_total{variant="candidate"}[15m]))
/
sum(rate(ai_upgrade_requests_total[15m]))
~~~

Embedding p95 theo variant:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, variant) (
    rate(ai_upgrade_embedding_duration_seconds_bucket[15m])
  )
)
~~~

Groundedness failure rate:

~~~promql
sum by (variant) (
  rate(ai_upgrade_groundedness_fail_total[1h])
)
/
sum by (variant) (
  rate(ai_upgrade_evaluated_total[1h])
)
~~~

Nếu denominator bằng 0 hoặc label coverage chưa đủ, hiển thị no data/insufficient sample thay vì coi là tỷ lệ 0.

## 17. Ví dụ end-to-end: đổi embedding model cho kho tài liệu hỗ trợ

Giả sử baseline dùng embedding-v1 và index support-v1. Nhóm muốn chuyển sang embedding-v2 để cải thiện truy xuất câu hỏi tiếng Việt và câu hỏi diễn đạt lại.

### 17.1. Baseline

- Chat model và prompt hiện tại.
- Corpus snapshot support-docs-v42.
- Parser/chunker version giữ nguyên.
- Index support-v1.
- Retrieval top K = 8.
- Golden query set có labels theo task family và locale.

### 17.2. Candidate

- Embedding-v2.
- Tạo index support-v2 với dimensions theo model mới.
- Re-embed toàn bộ chunks từ cùng corpus snapshot.
- Dùng query embedding từ embedding-v2.
- Giữ chat model, prompt, retriever parameters và evaluator cố định.

### 17.3. Offline retrieval

So sánh Recall@8, MRR, nDCG, empty retrieval và stale document rate. Phân tích riêng tiếng Việt, tiếng Anh, typo, paraphrase và multi-document questions.

### 17.4. End-to-end RAG

Chạy cùng chat model trên context từ support-v1 và support-v2. So relevance, groundedness, factuality, citation coverage và correct abstention. Nếu retrieval tăng nhưng factuality giảm, kiểm tra candidate có trả thêm tài liệu cũ hoặc tài liệu mâu thuẫn không.

### 17.5. Shadow và canary

Shadow query candidate index cho một sample traffic đã được phép. Sau khi đạt gates, route 5% cohort ổn định tới support-v2. Tăng dần sau khi đủ exposure và label maturity.

### 17.6. Rollback

Nếu candidate có empty retrieval tăng hoặc tenant filter sai, chuyển routing flag về support-v1. Giữ index v2 và manifest để điều tra. Không xóa index cũ cho đến khi rollback window kết thúc và release owner xác nhận.

## 18. Các lỗi thường gặp khi nâng cấp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Đổi chat model và prompt cùng lúc | Không biết thay đổi nào tạo kết quả | Tách experiment |
| Chỉ so exact response text | False failure khi wording khác nhưng đúng | Assertion theo semantic dimensions |
| Dùng evaluator mới cho candidate | Judge drift bị hiểu thành quality delta | Pin judge hoặc calibration riêng |
| Reuse vector index sau khi đổi embedding | Vector space bị trộn | Re-embed vào index mới |
| Chỉ kiểm tra dimensions | Cùng width nhưng khác vector space | Version model và test retrieval |
| Chỉ re-embed query, không re-embed documents | Query và corpus không tương thích | Dùng cùng embedding space |
| Chỉ thêm document mới, không xóa bản cũ | Retrieval trả policy stale | Version/tombstone/delete |
| Thay chunker nhưng giữ vector cũ | Embedding không đại diện content mới | Re-chunk và re-embed |
| Bỏ metadata trong migration | Filter/citation/ACL sai | Metadata parity checks |
| Đánh giá chỉ trên overall score | Subgroup regression bị che | Stratified reports |
| Không pin corpus snapshot | Benchmark không tái hiện được | Immutable source manifest |
| Shadow candidate thực thi tool thật | Side effect lặp | Disable/mock/sandbox |
| Cutover trước khi catch up changes | Candidate thiếu document mới | Watermark/CDC validation |
| Xóa baseline index ngay | Không thể rollback nhanh | Retain old index |
| Dùng raw IDs làm metric labels | Cardinality tăng và lộ dữ liệu | Bounded labels và trace references |

## 19. Quy trình quyết định promote hoặc rollback

Một quyết định release cần có bằng chứng:

1. Baseline và candidate fingerprints đã được pin.
2. Dataset coverage đủ cho các task families quan trọng.
3. Retrieval quality đạt ngưỡng nếu embedding/corpus thay đổi.
4. Generation quality đạt ngưỡng nếu chat model thay đổi.
5. Critical safety, tool và tenant assertions không có regression.
6. Latency, reliability và cost trong budget.
7. Human audit và judge calibration không phát hiện bias mới.
8. Shadow/canary có đủ exposure và label maturity.
9. Rollback route, capacity và index cũ đã sẵn sàng.
10. Owner ghi decision và release version.

| Kết quả | Quyết định |
| --- | --- |
| Quality tăng, guardrails đạt, sample đủ | Promote |
| Quality không giảm quá margin, chi phí hợp lý | Promote theo mục tiêu non-inferiority |
| Quality giảm ở critical subgroup | Hold hoặc rollback |
| Retrieval tốt hơn nhưng answer quality kém hơn | Điều tra context/reranker/prompt |
| Judge hoặc data coverage không đủ | Inconclusive, chưa promote |
| Critical safety/tool/tenant violation | Abort ngay |
| Operational metrics vượt budget | Pause, tối ưu hoặc rollback |

## 20. Checklist kiểm thử migration

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Chat model thay đổi | Cùng prompt/context/evaluator được dùng trong paired run |
| Model trả model revision khác yêu cầu | Actual model được ghi và điều tra |
| Embedding model thay đổi | Candidate index được re-embed đầy đủ |
| Hai model có cùng dimensions | Vẫn được coi là embedding space khác cho đến khi compatibility được chứng minh |
| Query embedding mới | Search cùng candidate index/vector space |
| Upsert retry | Stable ID không tạo duplicate |
| Vector width mismatch | Migration fail trước khi cutover |
| Candidate index có missing chunks | Coverage/count validation phát hiện |
| Corpus source bị xóa | Tombstone/delete được áp dụng |
| Parser/chunker thay đổi | Reprocess và re-embed theo pipeline version |
| Metadata/filter schema thay đổi | Tenant/ACL/filter parity tests pass |
| Document stale vẫn được retrieve | Candidate bị giữ lại |
| Shadow traffic | Không tạo tool side effects hoặc vượt quyền |
| Candidate canary | Assignment ổn định và metrics tách theo variant |
| Candidate latency tăng | p95/TTFT guardrail phát hiện |
| Candidate cost tăng | Cost per successful task được tính |
| Critical safety violation | Kill switch/rollback được kích hoạt |
| Rollback | Baseline model, prompt và index hoạt động lại |
| Migration kết thúc | Manifest, decision log và retention được lưu |

## 21. Bài tập thực hành

### Bài 1. Lập manifest cho ba pipeline

Tạo manifest cho baseline, candidate chat model và candidate embedding model. Đảm bảo chỉ đúng thành phần dự kiến thay đổi trong từng experiment.

### Bài 2. Paired generation evaluation

Tạo 50 evaluation cases có pinned context. Chạy hai ChatClient với cùng prompt, dùng cùng evaluator/rubric và báo delta theo relevance, groundedness, factuality và latency.

### Bài 3. Re-embed corpus

Tạo một corpus fixture nhỏ. Dùng candidate EmbeddingModel tạo vector và ghi vào candidate VectorStore bằng upsert. Kiểm tra dimensions, stable IDs và document metadata.

### Bài 4. Query embedding parity

Tạo query vector từ candidate model và search candidate index. Thử dùng query vector baseline trên candidate index để quan sát vì sao width đúng vẫn chưa chứng minh vector space tương thích.

### Bài 5. Document migration

Cập nhật một policy document, tạo source version mới, re-chunk, xóa chunk cũ và xác minh retrieval không trả nội dung hết hiệu lực.

### Bài 6. Retrieval metrics

Tạo query set có relevant document IDs. Tính Recall@K, MRR và nDCG cho hai embedding versions; phân tích riêng locale và task family.

### Bài 7. Blue-green index

Tạo baseline và candidate collections. Backfill candidate, mô phỏng source update trong lúc backfill, catch up bằng watermark rồi chuyển alias/routing flag.

### Bài 8. Release gate

Thiết kế non-inferiority margin, sample size, critical assertions, p95 latency budget và cost budget. Mô phỏng candidate tăng overall relevance nhưng giảm chất lượng một subgroup.

### Bài 9. Rollback drill

Mô phỏng candidate index bị thiếu document hoặc query embedding mismatch. Kích hoạt rollback, xác minh baseline route hoạt động và giữ evidence để điều tra.

## 22. Tổng kết

Đánh giá lại sau khi thay chat model, embedding hoặc tài liệu là một phần của quản lý chất lượng pipeline:

- Tách loại thay đổi và giữ cố định các thành phần không thuộc experiment.
- Version hóa model, prompt, embedding, corpus, parser, chunker, index, retriever và evaluator.
- Dùng paired evaluation trên cùng dataset và context snapshot.
- Đánh giá generation quality theo relevance, factuality, groundedness, completeness, citation, tool correctness và safety.
- Đánh giá embedding bằng retrieval labels như Recall@K, MRR và nDCG, sau đó kiểm tra end-to-end RAG.
- Khi đổi embedding model, re-embed corpus và query trong cùng vector space; dimension giống nhau không chứng minh tương thích.
- Khi đổi corpus/parser/chunker, kiểm tra source freshness, chunk coverage, metadata, filters và stale documents.
- Spring AI 2.1.0 hỗ trợ upsert và query-embedding search ở các vector stores có triển khai; cần kiểm tra capability của store cụ thể.
- Blue-green index, watermark catch-up, shadow, canary và rollback giúp migration có thể kiểm soát.
- Theo dõi quality cùng latency, reliability, tokens và cost per successful task.
- Chỉ promote khi đủ sample, subgroup gates, critical assertions và rollback readiness.

Một nâng cấp chỉ nên được coi là thành công khi pipeline candidate cải thiện hoặc duy trì chất lượng trên dữ liệu đại diện, không phá vỡ các điều kiện an toàn và có chi phí vận hành được chấp nhận. Manifest, dataset, index version và decision log giúp nhóm giải thích chính xác điều gì đã thay đổi và vì sao release được promote.

## Tài liệu tham khảo

- [Spring AI 2.1.0 GA — Release announcement](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/): baseline Spring Boot 4.2, user-supplied embeddings, vector-store upsert và query-embedding search.
- [Spring AI 2.1.0 — Embeddings Model API](https://docs.spring.io/spring-ai/reference/api/embeddings.html): EmbeddingModel, embed, dimensions, document content và batch embeddings.
- [Spring AI 2.1.0 — Vector Databases](https://docs.spring.io/spring-ai/reference/api/vectordbs.html): VectorStore, EmbeddedDocument, upsert, vector dimensions, vector-space compatibility, query-embedding search và metadata filters.
- [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatClient, ChatModel, EmbeddingModel và VectorStore observations, metrics và traces.
- [Spring AI 2.1.0 — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): ChatResponseMetadata, Usage, rate limits và cumulative usage trong multi-step flows.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): thay đổi API và dependency cần kiểm tra khi nâng cấp framework.
