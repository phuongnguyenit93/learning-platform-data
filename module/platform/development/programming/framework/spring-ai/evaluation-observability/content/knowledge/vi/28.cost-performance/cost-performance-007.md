# Tối ưu cache, batching và lượng ngữ cảnh dựa trên số liệu

## 1. Vì sao phải tối ưu từ số liệu?

Một ứng dụng Spring AI có thể tốn chi phí và phản hồi chậm vì cùng một nội dung được embedding nhiều lần, cùng một truy vấn lặp lại, model phải đọc lịch sử dài, retrieval trả quá nhiều chunks hoặc evaluator xử lý từng item riêng lẻ. Cache, batching và tối ưu context có thể giảm usage, latency và tải hạ tầng.

Nhưng tối ưu mù có thể làm chất lượng giảm: response cache trả dữ liệu cũ, semantic cache nhầm câu hỏi gần nghĩa, batching làm tăng thời gian chờ, context compression loại bỏ evidence quan trọng hoặc top-k thấp khiến RAG bỏ sót tài liệu.

Vì vậy, cần bắt đầu từ telemetry và evaluation:

- Xác định operation nào chiếm nhiều cost/latency.
- Đo tần suất lặp lại và khả năng tái sử dụng.
- Tách cache hit, cache miss và cache bypass.
- Đo batch size, queue wait, throughput và lỗi.
- Đo token count theo từng phần context.
- Kiểm tra quality, groundedness, factual correctness và task success sau mỗi thay đổi.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, mục tiêu là giảm cost per successful task và latency trong khi giữ các quality gates. Cache, batching và context budget cần được version hóa, quan sát và kiểm thử như một phần của pipeline.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt application response cache, semantic cache, embedding/retrieval cache và provider prompt cache.
2. Thiết kế cache key, TTL, versioning, invalidation và tenant isolation.
3. Đo cache hit rate, avoided cost, stale hit và cache correctness.
4. Tránh cache stampede, cache poisoning và trả dữ liệu cũ.
5. Thiết kế batching cho embedding, evaluation và provider batch APIs.
6. Cân bằng batch size, queue delay, throughput và partial failures.
7. Phân bổ context budget cho system prompt, history, tools, retrieval và output.
8. Tối ưu chunking, top-k, reranking, deduplication và history compression.
9. Thực hiện benchmark/ablation có quality guardrails trước rollout.

## 2. Ba đòn bẩy và tác động khác nhau

| Đòn bẩy | Giảm chủ yếu | Rủi ro chính |
|---|---|---|
| Cache | Tính toán/usage lặp lại, latency cho dữ liệu có thể tái sử dụng | Stale data, sai scope, cache miss/poisoning |
| Batching | Overhead request, scheduling và chi phí xử lý theo item | Queue delay, batch failure, memory spike |
| Context optimization | Input tokens, attention load và thời gian xử lý | Mất evidence, thiếu history, sai câu trả lời |

~~~mermaid
flowchart TD
    A["Observe cost, latency and quality"] --> B["Find repeated work"]
    B --> C["Cache eligible results"]
    A --> D["Find per-item overhead"]
    D --> E["Batch compatible operations"]
    A --> F["Measure context token breakdown"]
    F --> G["Reduce redundant context"]
    C --> H["Evaluate quality and task success"]
    E --> H
    G --> H
    H --> I{"Quality gates and SLO pass?"}
    I -->|Yes| J["Canary and monitor"]
    I -->|No| K["Rollback or refine"]
~~~

Không mặc định cả ba tối ưu cùng lúc. Thay đổi từng nhóm hoặc dùng ablation để biết cải thiện đến từ đâu và phát hiện trade-off.

## 3. Đo baseline trước khi thêm cache hoặc batching

Ghi baseline theo cùng dataset, workload và version:

| Nhóm | Chỉ số |
|---|---|
| Usage | Input/output/cached tokens, embedding tokens, model calls/task |
| Cost | Cost/attempt, cost/successful task, cost theo operation |
| Latency | End-to-end p50/p95/p99, TTFT, retrieval/model/tool latency |
| Cache | Hit/miss chưa có baseline thì đo tỷ lệ lặp lại tiềm năng |
| Batch | Items/request, batch wait, throughput và error rate |
| Context | System/tool/history/retrieval/output token budget |
| Quality | Relevance, groundedness, factual correctness, retrieval recall, tool correctness |

Đo theo cohort simple, RAG, tool, long-context và high-risk. Average toàn hệ thống có thể che giấu việc cache chỉ hữu ích cho một loại task hoặc context optimization làm hại nhóm long-context.

### Phân rã token theo nguồn

Ít nhất nên phân biệt:

- System/developer instructions.
- Tool definitions/schema.
- Conversation history.
- Retrieved documents/chunks.
- User input.
- Output allowance và actual output.

Nếu chỉ theo dõi tổng input tokens, không biết nên rút gọn history, tool schema hay retrieval context.

## 4. Phân biệt các loại cache

Từ “cache” thường chỉ nhiều cơ chế khác nhau. Chúng không có cùng semantics:

| Loại | Lưu gì? | Cache hit có bỏ qua model generation không? |
|---|---|---|
| Exact response cache | Kết quả hoàn chỉnh cho input/key giống nhau | Có |
| Semantic response cache | Kết quả cho câu hỏi đủ gần về ngữ nghĩa | Có, nếu policy cho phép |
| Embedding cache | Vector embedding của nội dung đã xử lý | Chỉ bỏ qua embedding call |
| Retrieval cache | Kết quả tìm kiếm/chunks cho query và filter | Chỉ bỏ qua retrieval tương ứng |
| Reranking cache | Thứ tự/chấm điểm tài liệu cho query-document set | Chỉ bỏ qua reranker |
| Tool result cache | Kết quả tool read-only có thể tái sử dụng | Bỏ qua tool call |
| Provider prompt cache | Prefix prompt provider đã lưu/tái sử dụng | Không; model vẫn generate |

Một request có thể dùng nhiều cache layers. Ghi layer nào hit và operation nào được bỏ qua để tính avoided cost đúng.

## 5. Exact response cache

Exact response cache trả lại output đã lưu khi request mới có cùng cache key. Phù hợp với:

- Câu hỏi FAQ có nội dung/version ổn định.
- Kết quả tra cứu công khai, ít thay đổi.
- Output deterministic hoặc được chấp nhận tái sử dụng.
- Evaluation fixture có input và candidate version cố định.

Không nên cache mọi câu trả lời chỉ dựa trên text câu hỏi. Kết quả có thể phụ thuộc tenant, authorization, thời gian, dữ liệu đơn hàng, locale, tool state hoặc prompt/model version.

### Điều kiện cache an toàn

- Input và mọi biến ảnh hưởng output đều nằm trong key hoặc version.
- User/tenant/permission scope được phân biệt.
- TTL phù hợp freshness của nguồn.
- Có invalidation khi dữ liệu hoặc policy thay đổi.
- Có thể bypass cache cho high-risk/current-state queries.
- Lưu cache metadata để audit version và hit/miss.

### Cache key phải đại diện ngữ nghĩa đầy đủ

Ví dụ key logic:

~~~text
response-cache:v4:
  tenantScope:
  locale:
  normalizedInputHash:
  systemPromptVersion:
  modelDeployment:
  toolPolicyVersion:
  knowledgeSnapshot:
  responseSchemaVersion
~~~

Không đưa raw prompt hoặc PII trực tiếp vào key nếu không cần. Có thể dùng HMAC/hash có secret và canonicalization ổn định. Hash không thay thế encryption hoặc access control cho cached value.

## 6. Semantic cache

Semantic cache tìm kết quả cũ có embedding đủ gần với query mới. Nó hữu ích khi người dùng diễn đạt khác nhau nhưng intent và câu trả lời thực sự tương đương.

Ví dụ:

- “Giờ làm việc của bộ phận hỗ trợ là khi nào?”
- “Support team làm việc tới mấy giờ?”

Hai câu có thể dùng chung câu trả lời nếu policy, locale, tenant và thời điểm không làm thay đổi kết quả.

### Semantic similarity không chứng minh câu trả lời tương đương

Hai câu có embedding gần nhau nhưng có thể khác ở:

- Phủ định: “được hoàn tiền” và “không được hoàn tiền”.
- Entity: mã đơn hàng/tên khách hàng khác nhau.
- Thời gian: “hôm nay” và “hôm qua”.
- Quyền truy cập: cùng câu hỏi nhưng tenant/user khác.
- Số lượng/đơn vị: 10 ngày và 10 giờ.
- Trạng thái hiện tại: đơn hàng đã giao hay đang vận chuyển.

Vì vậy, semantic cache cần threshold được hiệu chuẩn trên tập dữ liệu, kiểm tra entity/slot, freshness và authorization. Với câu hỏi trạng thái cá nhân hoặc dữ liệu thay đổi nhanh, thường phải bypass hoặc revalidate qua source of truth.

### Policy cho semantic hit

1. Tạo query embedding bằng model/version được ghi nhận.
2. Tìm candidate cache entries trong đúng tenant/security scope.
3. Kiểm tra similarity threshold và các hard constraints.
4. Kiểm tra TTL, knowledge/prompt/policy version.
5. Nếu cần, xác minh slot/entity và freshness.
6. Chỉ trả cached answer khi policy cho phép; nếu không thì gọi pipeline bình thường.

Không chọn threshold chỉ để tăng hit rate. Tối ưu phải dựa trên false-hit rate và task success.

## 7. Embedding cache

Embedding cache lưu vector đã tính cho một nội dung. Có thể giảm chi phí và latency khi:

- Document được ingest lại nhưng content không đổi.
- Nhiều cases dùng chung query/template.
- Evaluation dataset lặp qua nhiều candidate.
- Batch ingestion bị retry.

Cache key nên bao gồm:

- Provider/model/deployment.
- Embedding dimensions và output format.
- Preprocessing/normalization version.
- Content hash.
- Tenant/data classification scope nếu vector chứa dữ liệu riêng.

Nếu đổi embedding model hoặc dimensions, vector cũ không thể mặc nhiên dùng lại. Nếu đổi chunking, content hash theo chunk sẽ thay đổi. Version key giúp tránh trộn vector space khác nhau.

### Cache document embedding theo content hash

~~~yaml
embeddingCacheEntry:
  keyVersion: embedding-v3
  provider: provider-a
  model: embedding-model-x
  dimensions: 1024
  preprocessingVersion: normalize-v2
  contentHash: sha256:example-hash
  vectorRef: vector-object-001
  createdAt: 2026-11-27T10:00:00Z
  expiresAt: null
~~~

Schema minh họa. Không lưu raw document trong cache metadata; vector store/data store phải có ACL, encryption và retention phù hợp.

## 8. Retrieval và reranking cache

Retrieval cache lưu kết quả tìm kiếm cho query/filter/index state cụ thể. Cache key cần xem xét:

- Tenant/ACL scope.
- Query hash hoặc query embedding version.
- Vector index/collection version.
- Metadata filters.
- Top-k và search mode.
- Embedding model/version.
- Reranker model/version và rerank parameters nếu cache kết quả rerank.
- Knowledge snapshot hoặc index generation.

Nếu ACL hoặc metadata filter bị bỏ khỏi key, cache có thể trả tài liệu tenant khác hoặc tài liệu người dùng không còn quyền xem.

### Invalidation khi index thay đổi

Khi ingest/update/delete tài liệu:

- Tăng index generation/version.
- Invalidate cache theo collection/tenant nếu cần.
- Hoặc dùng key có generation để cache cũ tự mất hiệu lực.
- Với deletion/permission revocation, invalidation phải đủ nhanh theo policy.

Không chỉ dựa vào TTL dài khi quyền truy cập hoặc nội dung có thể bị thu hồi.

## 9. Tool result cache

Tool result cache chỉ an toàn khi hiểu semantics của tool.

| Tool | Cache suitability |
|---|---|
| Lookup danh mục công khai | Có thể cache theo version/TTL |
| Đọc cấu hình ít thay đổi | Có thể cache với invalidation |
| Tra cứu tồn kho | TTL ngắn hoặc revalidate |
| Tra cứu số dư tài khoản | Thường cần dữ liệu mới và authorization |
| Tạo đơn hàng/gửi email | Không cache để bỏ qua side effect |
| Thanh toán/cập nhật trạng thái | Không cache execution result để replay như một write mới |

Với read tool, key cần gồm tenant, authorization scope, resource ID, filters và data version. Với write tool, dùng idempotency key để chống thực hiện trùng; đó là cơ chế idempotency, không phải response cache thay thế side effect.

## 10. Provider prompt caching

Một số provider hỗ trợ cache prompt prefix hoặc cached input tokens. Khi prefix ổn định được tái sử dụng, provider có thể tính cached input theo rate riêng hoặc giảm latency. Model vẫn thực hiện generation cho request hiện tại.

Phân biệt:

- Application response cache hit: trả output cũ, thường không gọi model.
- Provider prompt cache hit: vẫn gọi model và nhận output mới; chỉ một phần input được provider tái sử dụng/định giá khác.

### Tổ chức prompt để tăng khả năng cache

- Đặt system instructions và nội dung ổn định ở đầu nếu provider yêu cầu prefix matching.
- Giữ thứ tự prefix ổn định giữa requests.
- Đưa dữ liệu biến thiên như current user query, timestamp và request-specific facts về phần sau.
- Tránh chèn random IDs/timestamps vào phần prefix ổn định.
- Kiểm tra minimum prefix length, cache retention và provider-specific rules.

Prompt caching behavior khác nhau theo provider/model/API. Xác minh documentation và usage metadata của deployment thực tế; không giả định Spring AI tự động bật hoặc mọi provider dùng cùng semantics.

## 11. Cache key, canonicalization và versioning

Cache key là hợp đồng xác định khi nào hai computations được xem là có thể dùng chung kết quả. Key thiếu một input ảnh hưởng output sẽ tạo false hit; key chứa quá nhiều giá trị không ổn định sẽ làm cache miss liên tục.

### Canonicalization

Trước khi hash:

- Chuẩn hóa encoding và Unicode theo một policy nhất quán.
- Chuẩn hóa whitespace nếu whitespace không ảnh hưởng semantics.
- Giữ nguyên phân biệt chữ hoa/thường nếu nghiệp vụ yêu cầu.
- Sắp xếp map/filter fields theo thứ tự xác định.
- Chuẩn hóa số, ngày giờ và locale.
- Không xóa dấu câu hoặc stop words một cách tùy tiện vì có thể đổi nghĩa.

Canonicalization phải được version hóa. Khi thuật toán normalize thay đổi, tăng key version để tránh đọc entries được tạo theo semantics cũ.

### Cache key không phải authorization

Key có tenant ID giúp phân tách namespace nhưng không chứng minh caller hiện tại có quyền đọc value. Khi cache hit, vẫn phải thực hiện authorization theo request hiện tại hoặc chỉ truy cập namespace đã được bảo vệ bằng ACL phù hợp.

Không tin tenant ID/role do client tự gửi nếu chưa xác thực ở server. Không dùng cache key để thay thế access control.

## 12. TTL, invalidation và freshness

TTL là giới hạn tuổi tối đa của cache entry. TTL phù hợp phụ thuộc tốc độ thay đổi và hậu quả khi trả dữ liệu cũ.

| Dữ liệu | TTL/policy gợi ý |
|---|---|
| Public FAQ theo version | Dài hơn, invalidate khi publish nội dung |
| Product catalog | Theo catalog version hoặc TTL ngắn |
| Query embedding | Có thể dài nếu model/preprocessing không đổi |
| Retrieval result | Ngắn hơn, phụ thuộc index freshness và ACL |
| Inventory/status | Rất ngắn hoặc revalidate |
| Account balance/permissions | Tránh stale cache; kiểm tra source of truth |
| Tool write operation | Không dùng cache để bỏ qua thực thi |

TTL là safety net, không phải invalidation strategy đầy đủ. Khi có content update, deletion hoặc permission revocation, event-driven invalidation hoặc generation version có thể cần thiết.

### TTL jitter

Nếu hàng nghìn entries cùng được tạo lúc deploy và cùng hết hạn, cache có thể tạo expiry storm. Thêm jitter ngẫu nhiên có giới hạn vào TTL giúp phân tán refresh.

### Stale-while-revalidate

Với dữ liệu cho phép stale trong một khoảng ngắn:

1. Trả entry còn trong stale window.
2. Chỉ một worker refresh entry ở background.
3. Lưu bản mới sau khi validate.
4. Dừng dùng stale entry khi vượt max stale age.

Không áp dụng cho authorization, số dư, thanh toán hoặc trạng thái có hậu quả cao nếu nghiệp vụ yêu cầu freshness tuyệt đối.

## 13. Cache stampede, single-flight và negative caching

Cache stampede xảy ra khi một key phổ biến hết hạn và nhiều requests cùng lúc gọi nguồn gốc để tính lại. Hệ quả là model/provider/database nhận burst tải đúng lúc cache không còn bảo vệ.

Biện pháp:

- Single-flight: chỉ một computation cho một key đang được refresh; requests khác chờ cùng kết quả.
- Distributed lock/lease nếu nhiều instances cùng refresh.
- TTL jitter để tránh hết hạn đồng thời.
- Pre-warm các keys phổ biến khi deploy nếu an toàn.
- Stale-while-revalidate cho dữ liệu cho phép stale.
- Bounded refresh concurrency và timeout.

### Negative caching

Có thể cache kết quả “không tìm thấy” trong thời gian ngắn để tránh lặp truy vấn không tồn tại. Nhưng negative cache cần TTL ngắn và invalidation khi resource được tạo.

Không cache lỗi transient, timeout, 429 hoặc authorization failure như thể đó là kết quả hợp lệ. Nếu cache error, một sự cố tạm thời có thể bị kéo dài sau khi provider đã phục hồi.

### Phân biệt cache miss với source failure

Ghi rõ:

- Miss: key chưa có entry.
- Expired: entry quá TTL.
- Invalidated: entry bị vô hiệu hóa.
- Bypass: policy không cho cache.
- Load error: nguồn gốc không trả được dữ liệu.
- Serialization error: không đọc/ghi được cache value.

Không gộp mọi trường hợp thành cache miss vì sẽ khó nhận diện cache backend đang lỗi.

## 14. Đo hiệu quả cache

Hit rate cơ bản:

\[
\mathrm{Hit\ rate} =
\frac{\mathrm{cache\ hits}}
{\mathrm{hits}+\mathrm{misses}}
\]

Hit rate cao chưa chắc tốt. Nếu cache hit trả dữ liệu sai hoặc cũ, tối ưu đã thất bại.

Theo dõi thêm:

| Metric | Ý nghĩa |
|---|---|
| Hit rate theo cache layer | Biết layer nào có lợi |
| Miss reason | cold, expired, invalidated, bypass |
| Hit latency | Thời gian lấy value |
| Origin latency avoided | Latency nguồn gốc đã tránh |
| Avoided tokens/calls | Model/embedding/tool calls được bỏ qua |
| Avoided cost | Cost ước tính đã tránh |
| Stale hit rate | Tỷ lệ trả entry stale trong policy |
| False-hit/correction rate | Cache hit bị phát hiện sai |
| Eviction rate | Entries bị loại do memory/size |
| Refresh failures | Không cập nhật được entry |

### Tính avoided cost

Nếu response cache hit thay thế một pipeline có cost trung bình C_origin:

\[
C_{\mathrm{avoided}} =
N_{\mathrm{valid\ hits}} \times C_{\mathrm{origin}}
\]

Trừ chi phí cache infrastructure và refresh:

\[
\mathrm{Net\ savings} =
C_{\mathrm{avoided}} -
C_{\mathrm{cache\ infra}} -
C_{\mathrm{refresh}}
\]

Đây là estimate; cần dùng usage/cost ledger để đo chính xác các operation đã bỏ qua. Provider prompt cache có cách tính khác: vẫn có generation cost, chỉ bucket cached input có rate khác.

## 15. Ví dụ cache economics

Giả sử một cohort có 100.000 requests/ngày. Response cache hit hợp lệ 30%; mỗi origin pipeline trung bình 0,004 USD; cache infrastructure và refresh cost 20 USD/ngày.

Requests được phục vụ từ cache:

\[
100{,}000 \times 0.30 = 30{,}000
\]

Origin cost tránh được:

\[
30{,}000 \times 0.004 = 120\ \mathrm{USD/day}
\]

Net saving ước tính:

\[
120 - 20 = 100\ \mathrm{USD/day}
\]

Nếu false-hit rate là 0,5%, có thể có khoảng 150 responses sai trong 30.000 hits. Với workflow rủi ro cao, chi phí chất lượng này có thể lớn hơn 100 USD savings. Vì vậy, cần đo false-hit/correction và quality gates song song với hit rate.

Các số liệu trên là giả định để minh họa, không phải provider pricing.

## 16. Spring caching và cache abstraction

Trong ứng dụng Spring, có thể dùng Spring Cache abstraction để tách business logic khỏi cache provider. Cache backend có thể là Caffeine, Redis hoặc implementation khác tùy kiến trúc.

Ví dụ một service cache kết quả tra cứu danh mục công khai:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class PublicCatalogService {

    private final CatalogRepository repository;

    PublicCatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "public-catalog",
            key = "#catalogVersion + ':' + #locale")
    CatalogView load(String catalogVersion, String locale) {
        return repository.load(catalogVersion, locale);
    }
}
~~~

Đây là ví dụ minh họa. Cần cấu hình CacheManager, TTL, serialization, eviction và metrics theo backend. Với method có side effects hoặc phụ thuộc security context không nằm trong key, không dùng annotation cache một cách máy móc.

### Cache configuration

~~~yaml
spring:
  cache:
    type: caffeine
~~~

Property và behavior cụ thể phụ thuộc Spring Boot/Spring Framework version cùng cache provider. Cấu hình production cần giới hạn maximum size/weight, expiration, serialization compatibility và observability.

### Lưu ý về proxy

Spring caching annotation thường được áp dụng qua proxy. Self-invocation trong cùng bean có thể không đi qua proxy nên cache advice không chạy như mong đợi. Kiểm tra invocation path và integration tests thay vì chỉ thấy annotation rồi kết luận cache đang hoạt động.

## 17. Batching là gì và khi nào nên dùng?

Batching gom nhiều items tương thích thành một operation để giảm request overhead hoặc tận dụng API batch của provider.

Phù hợp với:

- Document embeddings khi ingest nhiều chunks.
- Evaluation cases có cùng evaluator/configuration.
- Reranking nhiều query-document pairs nếu API hỗ trợ batch.
- Database/vector writes theo batch.
- Provider batch API cho workload offline chấp nhận latency cao hơn.

Không gom nhiều câu hỏi độc lập vào một prompt chỉ để giảm số HTTP requests nếu điều đó làm thay đổi semantics, privacy boundary hoặc khả năng đánh giá từng output.

### Lợi ích và trade-off

| Lợi ích | Trade-off |
|---|---|
| Ít request overhead hơn | Chờ gom batch làm tăng latency |
| Throughput cao hơn | Memory/buffer lớn hơn |
| Tận dụng provider batch pricing | Batch API có thể xử lý async/chậm |
| Ít scheduling/connection overhead | Một batch lỗi có thể ảnh hưởng nhiều items |
| Vector store write hiệu quả | Retry/partial result phức tạp hơn |

Batch size phải được đo trên workload thực tế. Batch lớn nhất không nhất thiết tối ưu.

## 18. Micro-batching và batch window

Micro-batching gom items trong một cửa sổ ngắn hoặc tới khi đạt batch size:

- Flush khi đạt max items.
- Flush khi đạt max tokens/bytes.
- Flush khi batch window hết.
- Flush sớm khi deadline của item gần đến.

~~~mermaid
flowchart TD
    A["Incoming items"] --> B["Bounded batch buffer"]
    B --> C{"Max items/tokens reached?"}
    C -->|Yes| E["Dispatch batch"]
    C -->|No| D{"Batch window expired?"}
    D -->|Yes| E
    D -->|No| B
    E --> F["Provider / VectorStore"]
    F --> G["Map results to item IDs"]
    G --> H["Persist per-item outcome"]
~~~

### Batch window ảnh hưởng latency

Batch window dài tăng cơ hội gom đủ items nhưng làm item đầu tiên chờ lâu nhất. Với online user-facing requests, window thường phải rất ngắn hoặc chỉ batch operation có deadline đủ rộng. Với offline embedding/evaluation, có thể chấp nhận batch window dài hơn.

Ghi queue wait riêng với provider processing time. Nếu chỉ đo total batch latency, không biết thời gian tăng đến từ chờ gom batch hay từ provider.

## 19. Embedding batching

Embedding là ứng viên batching phổ biến vì nhiều documents/chunks độc lập có thể được xử lý trong một request batch nếu provider hỗ trợ.

Trước khi batch:

- Kiểm tra max inputs per request.
- Kiểm tra max tokens per input và tổng batch.
- Chuẩn hóa text và metadata.
- Gắn stable item ID để map output đúng document/chunk.
- Tách items thuộc tenant/security domains khác nhau nếu policy yêu cầu.
- Deduplicate theo content hash trước khi gọi provider.

### Không nhầm batch size với concurrency

Batch size là số items trong một request. Concurrency là số batch requests đang in-flight. Nếu batch size = 100 và concurrency = 10, có thể có 1.000 items đang được xử lý.

Giới hạn cả:

- Max items/batch.
- Max tokens/batch.
- Max batches in-flight.
- Max total tokens in-flight.
- Max buffer bytes và queue wait.

### Partial failures

Nếu provider trả lỗi cho toàn batch, retry cả batch có thể tính lại items đã xử lý ở provider. Nếu API trả kết quả từng item, lưu outcome theo item và chỉ retry phần lỗi. Dùng idempotency/request IDs nếu provider hỗ trợ.

## 20. Batching evaluation và judge

Evaluation cases có thể batch khi evaluator API hỗ trợ nhiều inputs độc lập. Lợi ích là giảm overhead và tăng throughput, nhưng cần bảo đảm:

- Output vẫn map được về từng case ID.
- Một case lỗi không làm mất kết quả các case khác nếu API hỗ trợ partial result.
- Context của case này không rò sang case khác.
- Prompt/rubric/evaluator version giống nhau trong một batch.
- Output schema có validation cho từng item.
- Judge không bị ảnh hưởng bởi việc nhìn thấy câu trả lời của case khác.

Với LLM judge dùng một prompt chứa nhiều cases, kiểm tra nguy cơ cross-case contamination. Nếu judge trả JSON array, validate item count, unique IDs và schema trước khi ghi kết quả.

### Batch API offline

Một số provider có batch API bất đồng bộ, phù hợp evaluation/offline workloads:

- Chi phí có thể khác synchronous API.
- Completion time có thể lâu hơn.
- Job có thể cần polling hoặc webhook.
- Cancellation và partial failures có semantics riêng.
- Kết quả có thể đến muộn sau deadline của run.

Chỉ dùng khi latency SLA của evaluation cho phép. Không chuyển user-facing synchronous request sang batch API mà không thay đổi product contract.

## 21. Đo hiệu quả batching

Không chỉ đo số items trong batch. Theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Batch size | Số items thực tế mỗi batch |
| Batch fill ratio | Batch size / configured maximum |
| Batch wait | Thời gian item chờ được gom |
| Provider processing time | Thời gian provider xử lý batch |
| Throughput | Items hoàn tất mỗi giây/phút |
| Cost per item | Tổng cost chia số items hợp lệ |
| Partial failure rate | Tỷ lệ items lỗi trong batch |
| Retry amplification | Số operations phát sinh do retry |
| Memory/buffer utilization | Bộ nhớ dùng cho pending batch |

### Batch fill ratio

\[
\mathrm{Fill\ ratio} =
\frac{\mathrm{actual\ items\ in\ batch}}
{\mathrm{configured\ max\ items}}
\]

Fill ratio thấp có thể do batch window quá ngắn hoặc traffic phân tán. Fill ratio cao chưa chắc tốt nếu queue wait và tail latency tăng.

### So sánh batch size

Chạy thử nhiều batch sizes, ví dụ 8, 16, 32, 64 items, cùng workload và provider tier. So throughput, p95 wait, cost/item, error rate và memory. Chọn operating point đáp ứng latency/SLO, không nhất thiết batch lớn nhất.

## 22. Xử lý lỗi và retry trong batch

Batch có thể thất bại ở nhiều cấp:

- Request-level failure: toàn batch không được xử lý.
- Item-level failure: một số items lỗi, số còn lại thành công.
- Partial response: thiếu một số item IDs hoặc output không hợp lệ.
- Timeout/unknown: không biết provider đã xử lý bao nhiêu.
- Persistence failure: provider trả kết quả nhưng app không ghi được.

### Quy tắc retry

1. Lưu batch ID và danh sách item IDs trước khi dispatch.
2. Lưu provider request/job ID.
3. Parse và validate kết quả từng item.
4. Đánh dấu success/failure/pending riêng cho mỗi item.
5. Retry chỉ phần retryable khi provider semantics cho phép.
6. Không retry write operations nếu chưa có idempotency key.
7. Reconcile unknown outcomes trước khi tạo batch mới nếu có thể bị tính phí hai lần.

Nếu provider chỉ hỗ trợ all-or-nothing, retry cả batch có thể cần thiết nhưng phải dùng idempotency/job status API nếu có. Đừng giả định batch request bị timeout là chưa được provider xử lý.

### Batch size và blast radius

Batch càng lớn, một request-level failure có thể ảnh hưởng càng nhiều items. Với workflow quan trọng, có thể dùng batch nhỏ hơn hoặc checkpoint theo sub-batches để giới hạn blast radius.

## 23. Phân bổ context window

Context window là giới hạn tổng token mà model có thể xử lý cho một request, theo semantics của model/API. Không được dùng toàn bộ context window cho input vì còn cần output allowance và có thể có token/metadata overhead.

Một budget tổng quát:

\[
T_{\mathrm{input\ budget}} =
T_{\mathrm{context\ limit}}
- T_{\mathrm{output\ reserve}}
- T_{\mathrm{provider\ overhead}}
- T_{\mathrm{safety\ margin}}
\]

Input budget được phân bổ:

\[
T_{\mathrm{input}} =
T_{\mathrm{system}} +
T_{\mathrm{tools}} +
T_{\mathrm{history}} +
T_{\mathrm{retrieval}} +
T_{\mathrm{user}}
\]

Các thành phần cần được đo bằng tokenizer phù hợp với model hoặc usage metadata sau request. Character count không phải token count chính xác.

### Ví dụ

Giả sử model context limit 32.000 tokens, output reserve 2.000, provider overhead 500 và safety margin 1.500:

\[
T_{\mathrm{input\ budget}} =
32{,}000 - 2{,}000 - 500 - 1{,}500
= 28{,}000
\]

Nếu system/tool definitions dùng 3.000 tokens và user input dùng 1.000, còn 24.000 tokens cho history và retrieval. Đây là budget minh họa; giới hạn thật phải lấy theo model/deployment/API.

## 24. Đo token breakdown theo từng phần

Ghi token estimate trước khi gọi model và actual usage sau response:

| Thành phần | Chỉ số |
|---|---|
| System/developer prompt | Tokens và version |
| Tool schemas | Tokens, số tools và schema version |
| Conversation history | Tokens trước/sau compression |
| Retrieved context | Tokens, chunks, documents, source IDs |
| User input | Tokens |
| Output | Reserved và actual output tokens |
| Total | Estimated input, actual input/output |

So estimated và actual usage để hiệu chỉnh tokenizer/counter. Một số provider có hidden/system overhead hoặc cách đếm tool schema riêng; ghi rõ nguồn usage.

### Token budget phải có policy theo task

Simple answer có thể không cần retrieval. RAG có thể dành phần lớn budget cho evidence. Tool workflow cần dành token cho tool schemas và tool results. Không dùng một phân bổ cố định cho mọi task type.

## 25. Tối ưu retrieval context bằng số liệu

Retrieval context thường là phần input tăng nhanh khi top-k lớn hoặc chunks chồng lặp. Đo:

- Number of retrieved documents/chunks.
- Tokens per chunk và total retrieval tokens.
- Recall@k/expected evidence recall.
- Context precision/relevance.
- Duplicate/overlap ratio.
- Reranker score distribution.
- Groundedness/factual correctness.
- Retrieval latency và reranking latency.

### Chọn top-k bằng quality-cost curve

Chạy cùng dataset với k = 2, 4, 6, 8, 12 hoặc các giá trị phù hợp. Với mỗi k, đo evidence recall, groundedness, answer correctness, input tokens, cost và latency.

Không giảm k chỉ vì input tokens giảm. Chọn k nhỏ nhất vẫn đáp ứng retrieval/quality gates cho từng cohort. Một số task cần nhiều evidence hơn các task khác.

### Dynamic top-k

Có thể điều chỉnh k theo:

- Retrieval confidence và score gap.
- Số evidence sources cần thiết.
- Query/task type.
- Risk level.
- Context budget còn lại.

Nếu confidence thấp, có thể mở rộng retrieval hoặc hỏi clarification. Không tự động tăng k vô hạn; đặt max chunks/tokens và deadline.

## 26. Chunking và overlap

Chunking ảnh hưởng cả recall lẫn context cost:

- Chunk quá nhỏ: thiếu ngữ cảnh, tăng số chunks và metadata overhead.
- Chunk quá lớn: nhiều nội dung không liên quan, token cost cao.
- Overlap quá lớn: lặp nội dung, tăng context tokens.
- Overlap quá nhỏ: mất quan hệ giữa câu/đoạn ở ranh giới.

### Đánh giá chunking bằng dataset

Tạo các candidate chunking configs:

- Chunk size theo token.
- Overlap theo token hoặc tỷ lệ.
- Boundary theo paragraph/heading/semantic sections.
- Metadata fields.
- Parent-child retrieval strategy.

Đo:

- Expected evidence recall.
- Context precision.
- Number of chunks/query.
- Total retrieved tokens.
- Duplicate token ratio.
- Answer groundedness/correctness.
- Index size và ingestion cost.

Không chọn chunk size theo một con số phổ biến mà không benchmark trên tài liệu thật. Code, bảng, policy và văn bản tự nhiên có cấu trúc khác nhau.

### Parent-child retrieval

Có thể retrieve chunk nhỏ để định vị chính xác, sau đó lấy parent section hoặc neighboring chunks để bổ sung ngữ cảnh. Phải giới hạn tổng tokens và deduplicate nội dung. Giữ source IDs/offsets để citation và audit.

## 27. Reranking, deduplication và context compression

Một pipeline thường:

1. Retrieve candidate chunks với recall đủ rộng.
2. Rerank theo query relevance.
3. Deduplicate các chunks trùng/overlap.
4. Chọn chunks theo token budget và evidence coverage.
5. Có thể compress/summarize nếu rubric cho phép.

### Reranking

Reranker có thể tăng precision ở top-k nhưng thêm latency/cost. Đo gain về evidence recall/answer correctness trên từng cohort và chi phí reranker. Không rerank nếu retrieval đơn giản đã đủ hoặc latency budget quá chặt.

### Deduplication

Có thể deduplicate theo document ID, chunk ID, content hash hoặc overlap similarity. Không gộp các đoạn giống chữ nhưng thuộc phiên bản/tenant/nguồn khác nhau nếu provenance khác nhau.

### Context compression

Compression có thể:

- Bỏ boilerplate/navigation.
- Trích các đoạn liên quan với source reference.
- Tóm tắt history dài.
- Nén nội dung tài liệu có cấu trúc.

Compression bằng model có thể tạo hallucination hoặc loại bỏ điều kiện/ngoại lệ. Lưu original source reference và kiểm tra claims sau compression. Với high-risk workflows, dùng extractive selection hoặc giữ nguyên evidence cần thiết.

## 28. Quản lý conversation history

History dài làm tăng input tokens và có thể đưa thông tin lỗi thời vào context. Không nên chỉ giữ N messages gần nhất nếu các messages cũ chứa constraints hoặc facts vẫn còn hiệu lực.

Các chiến lược:

- Sliding window theo tokens thay vì số messages.
- Summary có cấu trúc theo facts, decisions, unresolved questions.
- Entity/state store cho thông tin cần cập nhật.
- Loại bỏ tool outputs đã được xử lý hoặc có thể truy xuất lại.
- Giữ system instructions và safety constraints ở vị trí ổn định.
- Đánh dấu timestamp/source cho facts có thể thay đổi.

### Summary không phải source of truth

Conversation summary có thể mất chi tiết hoặc ghi sai. Với dữ liệu quan trọng như order status, account balance, permissions hoặc policy version, truy xuất lại source of truth thay vì tin summary cũ.

### Đo history compression

So:

- Tokens trước/sau.
- Fact retention và constraint retention.
- Contradiction rate.
- Task success và user correction.
- Latency/cost.

Nếu summary ngắn hơn nhưng làm mất deadline, negation, entity ID hoặc exception, tối ưu đã gây regression.

## 29. Prompt structure và cache-friendly context

Nếu provider prompt caching dựa trên prefix, tổ chức prompt theo vùng ổn định và vùng biến thiên:

1. System instructions/version cố định.
2. Tool definitions/schema version ổn định.
3. Stable policy/reference instructions.
4. Conversation summary/history biến thiên.
5. Retrieved context biến thiên.
6. Current user input.

Thứ tự thực tế phải tuân theo API/provider semantics và prompt design. Không chuyển dữ liệu nhạy cảm hoặc tool results sang shared prefix chỉ để tăng cache hit.

### Đo provider prompt cache

Theo dõi:

- Cached input tokens và uncached input tokens.
- Cache hit/creation metadata nếu provider trả.
- Cached input price và standard input price.
- Prefix length/eligibility.
- Cost per request và latency.

Provider cache có thể yêu cầu prefix tối thiểu, TTL hoặc cache-control marker. Kiểm tra docs và response metadata của provider; không suy luận cache hit chỉ từ prompt giống nhau.

## 30. Kết hợp cache và context budget

Cache có thể giảm chi phí cho các thành phần context:

- Embedding cache tránh embed lại query/document.
- Retrieval cache tránh vector search lặp lại trong cùng index/ACL state.
- Summary cache tránh summarize lại cùng history snapshot.
- Provider prompt cache có thể giảm rate cho stable prefix.

Nhưng context budget vẫn cần được áp dụng sau cache. Một retrieval cache hit có thể trả nhiều chunks hơn budget hiện tại nếu top-k/config đã đổi; phải validate size và version trước khi đưa vào prompt.

### Tránh cache làm cố định một context tệ

Nếu cache retrieval result được tạo với top-k lớn hoặc ranking kém, cache sẽ lặp lại lỗi đó. Key cần gồm retriever/reranker version và retrieval parameters. Sau khi tối ưu, bump version hoặc invalidate entries cũ.

## 31. Ví dụ Java: gom embedding items theo batch

Đoạn code minh họa batching ở application layer. API embedding cụ thể phụ thuộc Spring AI/provider version; adapter nên map output về đúng item ID.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record EmbeddingInput(String id, String text) {}
record EmbeddedItem(String id, float[] vector) {}

interface EmbeddingBatchClient {
    List<float[]> embed(List<String> texts);
}

final class EmbeddingBatchService {

    private final EmbeddingBatchClient client;

    EmbeddingBatchService(EmbeddingBatchClient client) {
        this.client = client;
    }

    Map<String, float[]> embedBatch(List<EmbeddingInput> items) {
        List<String> texts = items.stream()
                .map(EmbeddingInput::text)
                .toList();

        List<float[]> vectors = client.embed(texts);
        if (vectors.size() != items.size()) {
            throw new IllegalStateException("embedding result count mismatch");
        }

        return java.util.stream.IntStream.range(0, items.size())
                .boxed()
                .collect(Collectors.toMap(
                        i -> items.get(i).id(),
                        vectors::get));
    }
}
~~~

Production code cần kiểm tra max batch items/tokens, empty input, null vectors, provider partial errors, retry theo item, timeout và cancellation. Với batch lớn, chia thành bounded sub-batches thay vì giữ toàn bộ documents trong memory.

## 32. Ví dụ cấu hình cache và batch policy

Schema minh họa cho một pipeline:

~~~yaml
optimizationPolicy:
  version: rag-optimization-v4
  cache:
    embedding:
      enabled: true
      keyVersion: embedding-v3
      maxEntries: 100000
    retrieval:
      enabled: true
      ttlSeconds: 60
      includeTenantAndAcl: true
      indexVersionRequired: true
    response:
      enabled: false
      bypassForHighRisk: true
  batching:
    embedding:
      maxItems: 64
      maxTokens: 20000
      maxWaitMillis: 50
      maxConcurrentBatches: 2
  context:
    maxInputTokens: 24000
    outputReserveTokens: 2000
    maxRetrievedChunks: 8
    deduplicate: true
    compression: extractive
~~~

Các giá trị là ví dụ, không phải defaults của Spring AI. Validate giới hạn provider/model và task SLO trước khi áp dụng.

## 33. Đo context quality sau mỗi lần tối ưu

Context ngắn hơn không đồng nghĩa tốt hơn. Mỗi thay đổi cần được đánh giá trên cùng dataset và rubric:

| Thay đổi | Quality cần kiểm tra |
|---|---|
| Giảm top-k | Evidence recall, groundedness, factual correctness |
| Giảm chunk size | Context precision, boundary evidence recall |
| Tăng chunk size | Irrelevant context, answer completeness |
| Deduplicate | Evidence coverage, provenance và source diversity |
| Rerank | Recall ở top-k cuối, ranking quality, latency |
| Compress documents | Claim preservation, conditions/exceptions retained |
| Summarize history | Entity, negation, constraints, unresolved tasks |
| Semantic cache | False-hit, freshness, authorization và task success |
| Response cache | Stale answer, tenant isolation, correctness |

### Quality gates cho cache

- Cache hit không được bypass authorization.
- High-risk/current-state queries phải tuân theo bypass/revalidation policy.
- False-hit rate phải dưới ngưỡng được phê duyệt.
- Cache result phải thuộc đúng prompt/model/index/policy version.
- User correction hoặc source mismatch phải có đường ghi nhận và điều tra.

### Quality gates cho context

- Evidence cần thiết vẫn xuất hiện trong context.
- Required facts/constraints không bị compression loại bỏ.
- Groundedness và factual correctness không suy giảm quá tolerance.
- Critical cases không bị mất source citation/provenance.
- Task success giữ trong confidence bounds đã định.

Không dùng average score để cho phép critical case fail.

## 34. Thiết kế experiment cho cache, batch và context

Một experiment nên thay đổi ít yếu tố để biết nguyên nhân:

1. Baseline: cache off, batch hiện tại, context config hiện tại.
2. Cache experiment: chỉ bật một cache layer với key/TTL policy rõ.
3. Batch experiment: chỉ thay batch size/window/concurrency.
4. Context experiment: thay một tham số như top-k hoặc history budget.
5. Combined experiment: chỉ kết hợp các thay đổi đã được xác nhận riêng.

### Experiment manifest

~~~yaml
optimizationExperiment:
  experimentId: rag-cache-batch-context-v4
  datasetVersion: rag-tool-regression-v4
  rubricVersion: quality-rubric-v4
  candidateVersion: answer-pipeline-18
  optimizationPolicyVersion: rag-optimization-v4
  cache:
    response: disabled
    embedding: enabled
    retrieval: enabled
    semantic: disabled
  batching:
    embeddingMaxItems: 64
    embeddingMaxWaitMillis: 50
  context:
    maxInputTokens: 24000
    maxRetrievedChunks: 8
    historyStrategy: token-window
  pricingVersion: provider-catalog-2026-11-v2
  startedAt: 2026-11-27T12:00:00Z
~~~

Schema chỉ minh họa. Ghi checksum/config reference nếu cần tái lập chính xác; không lưu secrets hoặc raw customer prompts trong manifest.

### So sánh paired

Chạy cùng cases trên baseline và candidate. Giữ task type, tenant scope test, cache warm/cold mode, region, concurrency và price catalog tương đương. Báo:

- Quality delta theo dimension.
- Cost per successful task.
- Input tokens/request và model calls/task.
- Cache hit/false-hit/stale-hit.
- Batch fill ratio và queue wait.
- End-to-end p50/p95/p99 và TTFT.
- Failure, retry và timeout rates.

Nếu cache làm kết quả phụ thuộc thứ tự chạy (cold/warm), cần báo hai điều kiện riêng.

## 35. Ablation và phân tích lợi ích thực

Ablation giúp tách tác động của từng tối ưu:

| Run | Response cache | Embedding cache | Batch | Context compression |
|---|---|---|---|---|
| Baseline | Off | Off | Off | Off |
| A | On | Off | Off | Off |
| B | Off | On | Off | Off |
| C | Off | Off | On | Off |
| D | Off | Off | Off | On |
| Combined | On | On | On | On |

Không nhất thiết phải chạy mọi tổ hợp nếu cost lớn. Chọn ablation theo giả thuyết từ baseline telemetry.

### Đo net savings

\[
\mathrm{Net\ savings} =
\mathrm{Baseline\ cost}
- \mathrm{Candidate\ cost}
- \mathrm{Optimization\ overhead}
\]

Candidate cost cần cùng scope và cùng số successful tasks. Nếu candidate có ít successes hơn, cost tổng thấp hơn có thể chỉ do xử lý ít việc thành công.

### Cost per successful task

\[
C_{\mathrm{success}} =
\frac{\mathrm{Total\ cost\ of\ cohort}}
{\mathrm{Successful\ tasks}}
\]

Tính cả failed attempts, retries và operation bị provider tính phí. Nếu không có successful tasks, metric không xác định.

## 36. Ví dụ đo lợi ích sau tối ưu

Giả sử cùng 10.000 RAG tasks:

| Metric | Baseline | Optimized |
|---|---:|---:|
| Successful tasks | 9.600 | 9.620 |
| Total candidate cost | 48 USD | 39 USD |
| Embedding calls | 10.000 | 2.000 |
| Average retrieved tokens | 5.000 | 3.600 |
| End-to-end p95 | 3,2 s | 2,5 s |
| Groundedness pass | 97,5% | 97,7% |
| Factual correctness | 98,2% | 98,1% |

Cost per successful task:

\[
C_{\mathrm{baseline}} = 48/9600 = 0.005\ \mathrm{USD}
\]

\[
C_{\mathrm{optimized}} = 39/9620
\approx 0.00405\ \mathrm{USD}
\]

Candidate optimized giảm cost per success khoảng 19%, p95 giảm và groundedness tăng nhẹ. Factual correctness giảm 0,1 điểm phần trăm; cần kiểm tra confidence interval và hard-gate cohorts trước khi kết luận không có regression.

Các số liệu là giả định để minh họa cách đọc kết quả, không phải benchmark Spring AI hoặc provider pricing.

## 37. Dashboard và telemetry cho cache/batch/context

Dashboard nên phân biệt từng layer và giữ dimension cardinality có kiểm soát.

### Cache

- Cache requests/hits/misses/bypass.
- Hit rate theo layer và cohort.
- Cache load latency.
- Evictions, expirations và refresh failures.
- Stale/false-hit/correction events.
- Estimated avoided model calls/tokens/cost.

### Batching

- Items per batch và fill ratio.
- Batch queue wait và provider duration.
- Batches in-flight.
- Items success/partial failure.
- Retry amplification.
- Buffer size và rejected items.

### Context

- Tokens theo system/tools/history/retrieval/user.
- Retrieved chunks và duplicate ratio.
- Context compression ratio.
- Evidence recall/groundedness.
- Output tokens và context-window headroom.

### Metric names gợi ý

Đây là tên metric do ứng dụng tự thiết kế:

- ai_cache_requests_total với labels cache_layer và outcome.
- ai_cache_load_duration_seconds.
- ai_cache_false_hit_total.
- ai_cache_avoided_cost_usd.
- ai_batch_items.
- ai_batch_wait_seconds.
- ai_batch_processing_seconds.
- ai_context_input_tokens với labels context_section và model_family.
- ai_context_compression_ratio.
- ai_retrieval_chunks_per_query.
- ai_retrieval_duplicate_ratio.

Không đưa raw query, document ID, tenant ID, request ID hoặc cache key vào metric labels. Dùng trace/log có phân quyền để drill down.

## 38. Runbook khi cache hoặc batching gây regression

### Cache hit tăng nhưng quality giảm

1. Tạm bypass cache ở cohort bị ảnh hưởng.
2. Kiểm tra key có thiếu tenant/ACL/entity/time/version không.
3. Kiểm tra TTL và invalidation events.
4. Kiểm tra semantic threshold/false-hit examples.
5. Kiểm tra cache entries có trộn prompt/model/index versions không.
6. Xác minh nguồn gốc và authorization.
7. Invalidate affected namespace và chạy regression cases.

### Cache hit thấp hoặc origin load tăng

1. Phân loại miss: cold, expired, invalidated, key mismatch, bypass.
2. Kiểm tra canonicalization và key version.
3. Kiểm tra TTL quá ngắn hoặc entries bị eviction.
4. Kiểm tra stampede/refresh concurrency.
5. Kiểm tra traffic mix và reuse potential.
6. Chỉ tăng TTL sau khi đánh giá freshness risk.

### Batch throughput tăng nhưng latency xấu

1. Tách batch wait khỏi provider processing time.
2. Giảm batch window hoặc batch size.
3. Kiểm tra queue backlog và memory pressure.
4. Kiểm tra provider max items/tokens và throttling.
5. Kiểm tra partial failures và retry cả batch.
6. Chạy lại benchmark theo online/offline SLO.

### Context tokens giảm nhưng answer quality giảm

1. So expected evidence recall và retrieved chunks.
2. Kiểm tra chunk boundary, top-k và reranker.
3. Kiểm tra deduplication loại nhầm source.
4. So sánh original/compressed context trên failure cases.
5. Bổ sung source-preserving compression hoặc tăng budget có chọn lọc.

## 39. Bài thực hành: tối ưu pipeline RAG bằng số liệu

Chuẩn bị:

- Dataset RAG có expected evidence và factual correctness labels.
- Pipeline Spring AI có EmbeddingModel, VectorStore, ChatModel và evaluator.
- Usage/cost ledger, traces và cache metrics.
- Baseline với cache disabled và batch size hiện tại.
- Cấu hình candidate có thể thay top-k, chunking, history budget và reranker.

Thực hiện:

1. Chạy baseline và lưu dataset/rubric/model/price versions.
2. Đo repeated query/document rate để xác định embedding cache potential.
3. Bật embedding cache với key chứa model/dimensions/preprocessing/content hash.
4. Kiểm tra tenant/ACL và invalidation cho retrieval cache.
5. Chạy embedding micro-batching với nhiều batch sizes và windows.
6. Đo batch fill ratio, queue wait, throughput, partial failure và cost/item.
7. Phân rã input tokens theo system/tools/history/retrieval/user.
8. Chạy top-k/chunking/reranking ablation trên cùng cases.
9. Thử history compression trên long-context cohort.
10. So quality gates, cost per successful task, p95 và false-hit rate.
11. Inject content update/ACL revoke để test cache invalidation.
12. Inject provider 429/timeout để test batch retry và idempotency.
13. Canary policy mới trên traffic nhỏ với rollback thresholds.
14. Ghi lại kết quả và cập nhật regression cases nếu phát hiện lỗi.

### Câu hỏi tự kiểm

**Câu 1:** Provider prompt cache hit có nghĩa model không chạy generation không?

Không. Provider có thể tái sử dụng prefix/cached input, nhưng request vẫn chạy generation và trả output mới.

**Câu 2:** Semantic cache có similarity cao. Có thể bỏ qua tenant/ACL check không?

Không. Similarity không chứng minh quyền truy cập hoặc freshness; authorization vẫn phải được áp dụng.

**Câu 3:** Batch size tăng gấp đôi nhưng p95 tăng. Cần xem metric nào?

Tách batch wait, provider processing time, queue backlog, memory và partial failure; throughput riêng không đủ.

**Câu 4:** Top-k giảm làm token cost giảm nhưng groundedness cũng giảm. Có thể rollout không?

Chỉ khi quality gates vẫn đạt trong từng cohort và risk policy cho phép. Nếu hard gate fail thì rollback/refine.

**Câu 5:** Embedding cache key có cần model version và dimensions không?

Có. Vector spaces khác nhau không thể trộn an toàn; preprocessing và content version cũng ảnh hưởng vector.

## 40. Checklist trước khi rollout tối ưu

- [ ] Baseline cost, latency, quality và usage đã được đo theo cohort.
- [ ] Cache layer và operation được bỏ qua đã được xác định.
- [ ] Cache key chứa mọi dimension ảnh hưởng semantics, tenant và version.
- [ ] Authorization được kiểm tra độc lập với cache key.
- [ ] TTL, invalidation, freshness và deletion policy được định nghĩa.
- [ ] Semantic cache threshold được hiệu chuẩn bằng false-hit examples.
- [ ] Cache stampede, negative caching và refresh failure được xử lý.
- [ ] Cache hit/miss/bypass/eviction/stale/false-hit được đo.
- [ ] Provider prompt caching được phân biệt với application response cache.
- [ ] Batch size, max tokens, concurrency và batch window có giới hạn.
- [ ] Queue wait được đo riêng với provider processing time.
- [ ] Partial failures, retries và idempotency được kiểm tra.
- [ ] Context window có output reserve và safety margin.
- [ ] Token breakdown theo system/tools/history/retrieval/user được ghi.
- [ ] Top-k/chunking/reranking/dedup được benchmark với evidence recall.
- [ ] History/document compression giữ facts, constraints và provenance.
- [ ] Quality gates không suy giảm ngoài tolerance đã duyệt.
- [ ] Cost per successful task và p95/p99 đáp ứng mục tiêu.
- [ ] Cache/batch/context policy có version và experiment manifest.
- [ ] Có canary, rollback và runbook cho regression.
- [ ] Privacy, tenant isolation, retention và data deletion được kiểm tra.

### Tài liệu chính thức để triển khai

- Spring Framework Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring AI Embeddings: https://docs.spring.io/spring-ai/reference/api/embeddings.html
- Spring AI Vector Databases: https://docs.spring.io/spring-ai/reference/api/vectordbs.html
- Spring AI Chat Models: https://docs.spring.io/spring-ai/reference/api/chatmodel.html
- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

**Kết luận:** cache, batching và context optimization chỉ có giá trị khi giảm cost/latency mà vẫn giữ quality gates. Đo baseline theo cohort, version hóa policy, bảo vệ tenant/ACL và freshness, kiểm soát queue/retry, rồi benchmark từng thay đổi trên cùng dataset. Theo dõi hit quality, batch wait, token breakdown và cost per successful task để quyết định rollout bằng bằng chứng thay vì chỉ nhìn hit rate hoặc throughput.
