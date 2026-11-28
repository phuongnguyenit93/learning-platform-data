# Chất lượng khi vận hành: Phát hiện thay đổi phân bố câu hỏi và chất lượng theo thời gian

## 1. Vì sao cần theo dõi sự thay đổi theo thời gian?

Một ứng dụng Spring AI có thể vượt qua benchmark ở thời điểm phát hành nhưng chất lượng vẫn giảm dần sau khi đưa vào production. Người dùng bắt đầu hỏi những chủ đề mới, ngôn ngữ hoặc cách diễn đạt thay đổi, corpus RAG được cập nhật, tool phía sau thay đổi contract, model provider chuyển revision hoặc traffic chuyển sang một nhóm tác vụ khác.

Nếu chỉ theo dõi HTTP status và latency, hệ thống có thể vẫn hoạt động bình thường trong khi câu trả lời ngày càng ít liên quan hoặc thiếu căn cứ. Ngược lại, điểm evaluator giảm chưa chắc do model kém đi: phân bố câu hỏi có thể khó hơn, nhóm người dùng thay đổi hoặc retrieval index mới đưa ra context khác.

**Drift monitoring** theo dõi những thay đổi này theo thời gian, xác định tầng nào thay đổi và kiểm tra liệu thay đổi đó có đi kèm suy giảm chất lượng hay không.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt data drift, concept drift, prediction drift, retrieval drift và quality drift.
- Xây dựng baseline theo thời gian, cohort và phiên bản pipeline.
- Theo dõi thay đổi về intent, ngôn ngữ, độ dài câu hỏi, embedding và retrieval context.
- Chọn kiểm định thống kê phù hợp với dữ liệu số, phân loại và vector.
- Phân biệt thay đổi có ý nghĩa thống kê với thay đổi có ý nghĩa sản phẩm.
- Theo dõi quality labels trễ từ evaluator, human review và user feedback.
- Dùng confidence interval, EWMA, CUSUM và change-point analysis để phát hiện xu hướng.
- Kết nối drift signals với Spring AI observations, metrics, traces và evaluation datasets.
- Thiết kế cảnh báo, triage, canary và rollback dựa trên bằng chứng.

## 2. Drift là gì? Không phải mọi thay đổi đều là lỗi

Drift là sự thay đổi của phân bố dữ liệu, quan hệ giữa input và kết quả, hoặc hành vi đầu ra theo thời gian. Cần xác định **đại lượng nào đang thay đổi** trước khi chọn detector.

### 2.1. Data drift — phân bố input thay đổi

Data drift xảy ra khi phân bố câu hỏi hoặc các đặc trưng đầu vào thay đổi:

- Tỷ lệ câu hỏi về billing tăng, còn câu hỏi về onboarding giảm.
- Người dùng chuyển từ tiếng Anh sang tiếng Việt.
- Câu hỏi dài hơn, nhiều điều kiện hoặc nhiều thực thể hơn.
- Tỷ lệ câu hỏi có file đính kèm, bảng hoặc code tăng.
- Từ vựng và chủ đề mới xuất hiện.
- Một kênh traffic mới mang tới nhóm người dùng khác.

Data drift không tự chứng minh chất lượng giảm. Model có thể xử lý tốt phân bố mới; cũng có thể gặp những tác vụ chưa có trong benchmark.

### 2.2. Concept drift — quan hệ giữa input và kết quả mong muốn thay đổi

Concept drift xảy ra khi quan hệ giữa đặc trưng đầu vào X và nhãn/kết quả mong muốn Y thay đổi:

\[
P_t(Y \mid X) \ne P_{t+1}(Y \mid X)
\]

Ví dụ: chính sách hoàn tiền thay đổi nên câu trả lời đúng cho cùng một câu hỏi phụ thuộc phiên bản policy. Một workflow trước đây yêu cầu tool A, nhưng quy trình mới yêu cầu xác minh thêm bằng tool B.

Concept drift thường cần ground truth hoặc nhãn được adjudicate để xác nhận. Chỉ nhìn input distribution không đủ kết luận.

### 2.3. Prediction drift — phân bố đầu ra thay đổi

Prediction drift là thay đổi trong phân bố câu trả lời hoặc hành vi model:

- Tỷ lệ refusal tăng.
- Tỷ lệ tool call tăng hoặc giảm bất thường.
- Response length thay đổi mạnh.
- Tỷ lệ finish reason bị truncation tăng.
- Tỷ lệ output rỗng hoặc format invalid tăng.
- Confidence hoặc score do evaluator phát ra thay đổi.

Prediction drift có thể là phản ứng hợp lý với input mới, cũng có thể do model/prompt/provider thay đổi.

### 2.4. Retrieval drift — evidence RAG thay đổi

Trong RAG, cùng câu hỏi có thể nhận context khác theo thời gian vì:

- Corpus thêm, sửa hoặc xóa tài liệu.
- Index được rebuild với embedding model hoặc chunking khác.
- Retriever, topK, filter hoặc reranker được cập nhật.
- Tài liệu mới có score cao hơn tài liệu cũ.
- Quyền truy cập/tenant filter thay đổi.

Retrieval drift có thể làm relevance hoặc fact-check giảm dù model và prompt không đổi.

### 2.5. Quality drift — chất lượng quan sát được thay đổi

Quality drift là thay đổi của các outcome có ý nghĩa sản phẩm:

- Relevance pass rate giảm.
- Fact-check pass rate giảm.
- Human-reviewed defect rate tăng.
- Tool task completion giảm.
- User feedback negative tăng.
- Citation coverage hoặc retrieval evidence sufficiency giảm.

Đây là tín hiệu gần nhất với mục tiêu sản phẩm, nhưng labels thường đến trễ, không đầy đủ hoặc có selection bias.

### 2.6. Pipeline/configuration drift

Một thay đổi có chủ đích ở prompt, model, policy, retriever hoặc tool schema cũng làm phân bố và metrics thay đổi. Đây không nhất thiết là drift tự nhiên; đó là **configuration change** cần được ghi nhận để tách ảnh hưởng.

### 2.7. Label shift và covariate shift

Hai thuật ngữ thống kê thường gặp giúp mô tả data drift chính xác hơn:

- **Covariate shift:** phân bố input thay đổi, \(P(X)\) thay đổi, trong khi quan hệ mục tiêu \(P(Y\mid X)\) được giả định ổn định.
- **Label shift:** phân bố nhãn thay đổi, \(P(Y)\) thay đổi, trong khi phân bố input theo nhãn \(P(X\mid Y)\) được giả định ổn định.

Trong ứng dụng AI, tỷ lệ intent hoặc task family thay đổi có thể giống label shift nếu taxonomy đó là nhãn được gán cho input. Cần nói rõ biến nào là input feature và biến nào là label; không dùng hai thuật ngữ thay thế cho mọi loại drift.

| Loại thay đổi | Đại lượng theo dõi | Câu hỏi chẩn đoán |
| --- | --- | --- |
| Data drift | Phân bố câu hỏi/input features | Người dùng đang hỏi khác trước ở điểm nào? |
| Concept drift | Quan hệ input với ground truth | Tiêu chí đúng/sai hoặc quy trình nghiệp vụ đã đổi chưa? |
| Prediction drift | Phân bố output/model behavior | Model đang trả lời hoặc gọi tool khác trước ra sao? |
| Retrieval drift | Context, sources, ranks, scores | Evidence được đưa vào prompt có thay đổi không? |
| Quality drift | Relevance, factuality, task success | Chất lượng thực tế có suy giảm không? |
| Configuration drift | Prompt/model/index/tool versions | Có thay đổi triển khai nào trùng thời điểm không? |

Không gộp tất cả vào một metric tên drift. Mỗi detector phải chỉ rõ feature, reference window, current window, cohort và policy version.

## 3. Phân biệt thay đổi traffic với suy giảm chất lượng

Giả sử tháng trước traffic gồm 80% câu hỏi đơn giản và 20% câu hỏi cần RAG. Tháng này tỷ lệ chuyển thành 40% và 60%. Nếu nhóm RAG có điểm relevance thấp hơn, overall score có thể giảm dù chất lượng trong từng nhóm không đổi.

Đây là vấn đề **thay đổi task mix** và có thể dẫn đến Simpson's paradox.

Ví dụ minh họa:

| Cohort | Tháng trước: tỷ lệ traffic | Tháng trước: pass rate | Tháng này: tỷ lệ traffic | Tháng này: pass rate |
| --- | ---: | ---: | ---: | ---: |
| Direct chat | 80% | 95% | 40% | 95% |
| RAG | 20% | 80% | 60% | 80% |
| Overall | 100% | 92% | 100% | 86% |

Overall pass rate giảm từ 92% xuống 86%, nhưng từng cohort giữ nguyên chất lượng. Thay đổi đến từ tỷ trọng cohort.

Vì vậy dashboard cần hiển thị cả:

1. Phân bố traffic theo cohort.
2. Quality score bên trong từng cohort.
3. Overall score có điều chỉnh theo population mix khi cần.

Một cách so sánh là giữ cố định trọng số cohort theo baseline:

\[
Q_t^{standardized} = \sum_{g=1}^{G} w_g^{baseline} Q_{g,t}
\]

Trong đó \(Q_{g,t}\) là quality của cohort g tại thời điểm t và \(w_g^{baseline}\) là tỷ trọng cohort trong reference period. Đây là score chuẩn hóa theo task mix, giúp phân biệt thay đổi traffic với thay đổi trong từng nhóm.

Không chỉ xem standardized score. Hãy trình bày cả raw overall score và cohort scores để không che mất việc traffic thực tế đang chuyển sang nhóm khó hơn.

## 4. Thiết kế baseline và cửa sổ thời gian

Drift detector chỉ có ý nghĩa khi biết đang so sánh current data với reference nào.

### 4.1. Fixed baseline

Fixed baseline là phân bố của một giai đoạn chuẩn, ví dụ 14 ngày sau khi release được xác nhận ổn định.

Ưu điểm:

- Dễ so sánh dài hạn.
- Phát hiện thay đổi tích lũy.
- Giữ chuẩn đánh giá ổn định qua nhiều tháng.

Giới hạn:

- Có thể trở nên lỗi thời khi sản phẩm và người dùng thay đổi hợp lệ.
- Mùa vụ hoặc campaign có thể tạo drift lặp lại.

### 4.2. Rolling baseline

Rolling baseline là cửa sổ gần nhất, ví dụ 7 hoặc 28 ngày trước current window.

Ưu điểm:

- Theo sát traffic gần đây.
- Nhận ra thay đổi ngắn hạn.

Giới hạn:

- Có thể hấp thụ drift từ từ và coi trạng thái đã suy giảm là bình thường.
- Một đợt incident kéo dài có thể làm baseline bị nhiễm.

### 4.3. Dual baseline

Trong production, có thể dùng đồng thời:

- Fixed release baseline để giữ chuẩn dài hạn.
- Rolling baseline để phát hiện biến động gần đây.
- Optional seasonal baseline để so cùng thứ trong tuần hoặc cùng mùa.

Nếu current khác rolling nhưng gần fixed, có thể là dao động gần đây. Nếu current dần khác cả hai, cần điều tra thay đổi dài hạn.

### 4.4. Chọn cửa sổ theo traffic và chu kỳ

Không chọn window chỉ vì thuận tiện. Cân nhắc:

- Volume tối thiểu để thống kê ổn định.
- Chu kỳ theo giờ, ngày trong tuần, cuối tháng hoặc mùa vụ.
- Thời gian labels xuất hiện.
- Tốc độ thay đổi của sản phẩm.
- Độ trễ ingest và late-arriving events.

Ví dụ: một sản phẩm B2B có traffic thấp vào cuối tuần không nên so ngày thứ Hai với Chủ nhật. Có thể so cùng weekday hoặc dùng rolling window dài hơn.

### 4.5. Ghi rõ thời gian và version

Mỗi drift result nên lưu:

- Reference window start/end.
- Current window start/end.
- Timezone và event-time definition.
- Ingestion watermark hoặc completeness status.
- Prompt/model/retriever/index/tool versions.
- Detector name, parameters và version.
- Cohort dimensions.
- Sample count và missing-data rate.

Nếu pipeline có event đến trễ, đừng so một current window chưa đầy đủ với baseline đã hoàn chỉnh. Hiển thị trạng thái provisional hoặc chờ watermark trước khi kết luận.

## 5. Chọn feature nào để theo dõi?

Không cần lưu raw prompt để đo mọi thay đổi. Có thể tạo feature summary tại thời điểm xử lý, với schema có version và privacy review.

### 5.1. Input/query features

Các feature hữu ích:

| Feature | Ví dụ cách biểu diễn | Phát hiện |
| --- | --- | --- |
| Language | language code | Thay đổi ngôn ngữ |
| Intent/task family | enum hữu hạn | Thay đổi nhu cầu |
| Input length | token count hoặc character bucket | Câu hỏi dài/ngắn bất thường |
| Message count | số lượt trong context | Hội thoại phức tạp hơn |
| Entity count | số thực thể được nhận diện | Câu hỏi nhiều đối tượng |
| Attachment type | enum: PDF, image, CSV, none | Thay đổi modality |
| Code/table presence | boolean hoặc bounded category | Nhiều code hoặc bảng hơn |
| Query embedding | vector hoặc secure reference | Chủ đề/semantic distribution thay đổi |
| OOD score | score từ detector có version | Input xa phân bố đã biết |

Không dùng raw prompt, tên người, email hoặc mã khách hàng làm feature label hay metric dimension.

### 5.2. RAG features

Theo dõi:

- Retrieval result count.
- TopK thực tế và số chunk sau filter.
- Top-1 score, score distribution và score gap.
- Tỷ lệ empty retrieval.
- Document source/type và freshness bucket.
- Rank distribution của evidence.
- Reranker score và version.
- Context token count.
- Tỷ lệ answer claims có citation/evidence.
- Tỷ lệ source không còn tồn tại hoặc version mismatch.

Điểm similarity không phải xác suất relevance. Không so trực tiếp score giữa hai embedding model hoặc index version khác nhau nếu chưa hiệu chỉnh.

### 5.3. Output/runtime features

Có thể theo dõi:

- Response token count và character length.
- Refusal/filtered rate.
- Finish reason category.
- JSON/schema validation result.
- Tool-call rate và tool error rate.
- Retry count.
- Latency, TTFT và stream duration.
- Input/output usage cùng usage coverage status.
- Estimated cost theo role.

Các feature này giúp phát hiện behavior shift, nhưng không thay thế đánh giá nội dung.

### 5.4. Quality labels

Tạo các outcome riêng:

- Relevance pass/fail hoặc score.
- Fact-check pass/fail/inconclusive.
- Groundedness/citation coverage.
- Tool task completion.
- Human reviewer verdict.
- User feedback reason.
- Business outcome nếu có.

Lưu evaluator model, rubric version, human review status và label timestamp. Không gộp evaluator output và user feedback thành một nhãn duy nhất.

## 6. Đo drift của feature phân loại

Với feature dạng category như language, task family, attachment type hoặc finish reason, trước hết so sánh tỷ lệ từng category.

Ví dụ:

| Intent | Reference | Current | Delta |
| --- | ---: | ---: | ---: |
| BILLING | 35% | 52% | +17 pp |
| ACCOUNT | 30% | 22% | -8 pp |
| TECHNICAL | 25% | 18% | -7 pp |
| OTHER | 10% | 8% | -2 pp |

Đây là mô tả shift, chưa nói shift có xấu hay không.

### 6.1. Chi-square test

Chi-square test of independence/homogeneity có thể kiểm tra liệu phân bố category giữa hai cửa sổ có khác nhau đáng kể hay không.

\[
\chi^2 = \sum_i \frac{(O_i-E_i)^2}{E_i}
\]

Trong đó \(O_i\) là observed counts và \(E_i\) là expected counts theo giả thuyết phân bố không đổi; với phép so sánh hai cửa sổ, chỉ số i chạy qua các ô của bảng chéo window × category.

Lưu ý:

- Dùng counts, không chỉ dùng tỷ lệ đã làm tròn.
- Kiểm tra expected cell counts; category rất hiếm có thể cần gộp có lý do hoặc dùng exact/Monte Carlo method.
- Nếu nhiều request đến từ cùng một user hoặc session, quan sát có thể không độc lập.
- Với volume rất lớn, khác biệt rất nhỏ cũng có thể có p-value thấp.

### 6.2. Population Stability Index (PSI)

PSI đo thay đổi tỷ trọng giữa các bins/categories:

\[
PSI = \sum_i (P_i-Q_i)\ln\left(\frac{P_i}{Q_i}\right)
\]

Trong đó P là reference proportion và Q là current proportion.

PSI thường được dùng với bins của feature số hoặc categories. Một số đội dùng mốc tham khảo 0,1 và 0,25 để phân loại thay đổi nhỏ/lớn, nhưng đây **không phải ngưỡng phổ quát**. Cần hiệu chỉnh theo feature, volume, baseline và tác động thực tế.

Nếu một bin có tỷ lệ 0, log ratio có thể không xác định. Dùng smoothing/pseudocount có định nghĩa rõ và ghi vào detector config; không âm thầm thay zero bằng một số tùy ý.

### 6.3. Jensen-Shannon divergence

Jensen-Shannon divergence so sánh hai phân bố xác suất, đối xứng và có giá trị hữu hạn khi dùng log base phù hợp:

\[
JSD(P,Q) =
\frac{1}{2}D_{KL}(P\|M) +
\frac{1}{2}D_{KL}(Q\|M)
\]

với \(M=(P+Q)/2\).

JSD hữu ích để so sánh category distribution. Phải dùng cùng taxonomy và cách xử lý category mới/unknown giữa reference và current.

### 6.4. Không chỉ báo p-value hoặc một drift score

Báo cáo cần có:

- Reference và current proportions.
- Absolute percentage-point delta.
- Relative change.
- Sample count.
- Drift score và test version.
- Confidence interval hoặc uncertainty nếu phù hợp.
- Business impact/cohort liên quan.

Một category tăng từ 0,01% lên 0,02% là tăng 100% tương đối nhưng chỉ tăng 0,01 điểm phần trăm. Chỉ nhìn relative change có thể gây alarm không cần thiết.

## 7. Đo drift của feature số

Với input length, context tokens, latency, retrieval score hoặc response length, có thể dùng nhiều phương pháp.

### 7.1. Kolmogorov-Smirnov test

KS test so sánh empirical cumulative distribution functions của hai mẫu liên tục:

\[
D = \sup_x |F_{reference}(x)-F_{current}(x)|
\]

D càng lớn, hai empirical distributions càng khác. KS test phù hợp với feature liên tục và phân bố có đủ độ phân giải; cần thận trọng với dữ liệu rời rạc nhiều ties, dữ liệu phụ thuộc và sample size lớn.

### 7.2. Wasserstein distance

Wasserstein distance đo chi phí biến đổi một phân bố thành phân bố khác. Với one-dimensional distributions, nó phản ánh khoảng cách dịch chuyển theo đơn vị feature.

Ưu điểm: có thể diễn giải theo đơn vị gốc. Ví dụ Wasserstein distance của query length có đơn vị token. Nhưng phải chuẩn hóa hoặc đặt ngưỡng theo feature; không so trực tiếp khoảng cách của milliseconds với token counts.

### 7.3. Quantile shift

So sánh median, P75, P90 và P99 có thể dễ hiểu cho vận hành:

- Input query P90 tăng từ 60 lên 110 tokens.
- Retrieval context P95 tăng từ 2.000 lên 3.500 tokens.
- Latency P95 tăng từ 1,8s lên 3,1s.
- Response length P50 giảm từ 220 xuống 90 tokens.

Quantile shift giúp nhận ra tail behavior mà mean có thể che khuất.

### 7.4. Tỷ lệ zero, missing và outlier

Theo dõi riêng:

- Null/missing rate.
- Zero rate.
- Clipped/capped values.
- Invalid numeric values.
- Outlier rate theo rule đã version hóa.

Missingness tự nó có thể là drift. Ví dụ provider mới không còn trả token usage; token counter giảm có thể là thay đổi metadata coverage chứ không phải model dùng ít token.

## 8. Theo dõi semantic drift bằng embeddings

Intent taxonomy có thể không bắt kịp chủ đề mới. Embeddings giúp biểu diễn câu hỏi theo ngữ nghĩa để so sánh các nhóm câu hỏi.

Một số cách:

1. **Centroid shift:** so khoảng cách giữa vector trung bình của reference và current.
2. **Cluster share:** cố định clustering model/centroids, đo tỷ lệ traffic rơi vào từng cluster.
3. **Nearest-neighbor distance:** theo dõi khoảng cách tới tập reference hoặc prototype đã biết.
4. **MMD:** so sánh hai phân bố vector thông qua kernel-based maximum mean discrepancy.
5. **Human topic review:** lấy mẫu các cluster hoặc outlier để đặt tên chủ đề mới.

### 8.1. Giữ embedding space ổn định

Không so embeddings được tạo bởi hai embedding models khác nhau như thể chúng cùng một hệ tọa độ. Khi đổi embedding model, dimensions, normalization hoặc preprocessing, drift score có thể thay đổi chỉ vì representation thay đổi.

Để so sánh theo thời gian:

- Giữ cùng embedding model/version trong một reference series.
- Lưu model version và preprocessing version.
- Nếu nâng model, chạy shadow embedding cho một khoảng traffic hoặc re-embed baseline có kiểm soát.
- Tạo baseline mới sau khi xác nhận model representation mới.
- Không trộn vectors từ hai không gian embedding khác nhau vào một detector.

### 8.2. Semantic drift không đồng nghĩa model quality drift

Một cluster mới có thể chỉ phản ánh một chủ đề mới đang thịnh hành. Cần xem các câu hỏi mẫu đã redaction, xác định task family và đánh giá quality trên cohort đó. Nếu semantic cluster mới có relevance/fact-check thấp, đó mới là bằng chứng cần ưu tiên điều tra.

## 9. Retrieval drift trong pipeline RAG

Retrieval có thể thay đổi dù input distribution giữ nguyên. Vì vậy nên kiểm tra cùng một tập query đại diện qua từng index/retriever version.

Các chỉ số gợi ý:

| Chỉ số | Điều phát hiện |
| --- | --- |
| Retrieval count | Số chunk trả về có giảm không? |
| Empty retrieval rate | Bao nhiêu query không có context? |
| Top-1 score distribution | Mức độ tương đồng có thay đổi không? |
| Score gap top1-top2 | Kết quả đầu có tách biệt hay không? |
| Source distribution | Tỷ lệ tài liệu từ nguồn nào tăng/giảm? |
| Document freshness | Context có cũ hoặc hết hiệu lực không? |
| Recall@K trên labeled set | Evidence đúng có nằm trong top K không? |
| Citation coverage | Claims có nguồn hỗ trợ không? |
| Context length | Prompt nhận quá ít hoặc quá nhiều context không? |

### 9.1. Tách corpus change khỏi retriever change

Khi retrieval score giảm, kiểm tra lần lượt:

1. Corpus có thêm, sửa hoặc xóa tài liệu không?
2. Index có được rebuild không?
3. Embedding model hoặc chunking có thay đổi không?
4. Query rewrite có đổi không?
5. Filter, tenant scope, topK hoặc reranker có đổi không?
6. Tool hoặc metadata source có bị lỗi không?

Lưu corpus snapshot/version, index version, embedding model, retriever config và reranker version. Nếu chỉ lưu tên retriever, rất khó tái hiện kết quả cũ.

### 9.2. Replay cùng queries

Một cách cô lập retrieval drift là chạy một bộ query cố định qua reference index và current index. So sánh:

- Document/chunk IDs.
- Rank và score.
- Recall@K trên ground-truth evidence.
- Context token count.
- Tỷ lệ empty retrieval.
- Latency.

Đây là replay evaluation có kiểm soát; kết quả cần được tách khỏi traffic mix production.

## 10. Đo quality drift khi labels đến trễ

Input drift thường có thể tính ngay khi nhận request. Quality labels thường đến muộn:

- LLM judge chạy sau response.
- Human reviewer kiểm tra sau vài giờ hoặc vài ngày.
- User feedback chỉ có ở một phần traffic.
- Business outcome chỉ được xác nhận sau khi workflow kết thúc.

Vì vậy, current window cần có **label completeness**. So sánh một tuần đã đủ nhãn với một ngày mới chỉ có 20% nhãn sẽ tạo kết luận sai.

### 10.1. Theo dõi label maturity

Lưu các timestamp riêng:

- interaction completed time.
- evaluator completed time.
- human review time.
- user feedback received time.
- business outcome time.

Tính tỷ lệ interactions đã có label theo age cohort, ví dụ sau 1 giờ, 24 giờ và 7 ngày. Chỉ so quality rates ở cùng maturity horizon hoặc hiệu chỉnh cho censoring/delayed labels.

### 10.2. Wilson confidence interval cho tỷ lệ pass

Nếu có n cases đã được đánh giá và x cases pass, tỷ lệ quan sát là \(\hat p=x/n\). Wilson interval cho confidence level z:

\[
CI =
\frac{
\hat p+\frac{z^2}{2n}
\pm
z\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}
}{
1+\frac{z^2}{n}
}
\]

Khoảng tin cậy giúp tránh diễn giải quá mức khi sample nhỏ. Nếu dùng stratified/risk sample với inclusion probability khác nhau, cần dùng phương pháp variance phù hợp thiết kế mẫu; không áp dụng Wilson interval như thể đó là simple random sample.

### 10.3. Giữ evaluator và human labels riêng

LLM judge có thể thay đổi theo model hoặc rubric version. Khi evaluator được nâng cấp, điểm quality có thể dịch chuyển do chính judge, dù answer model không đổi.

Lưu evaluator model, prompt/rubric version và calibration status. Nếu cần so sánh dài hạn, giữ một fixed calibration set được human review để phát hiện evaluator drift.

User feedback cũng có selection bias. Tỷ lệ negative trên những người đã gửi feedback không phải defect rate trên toàn traffic. Hãy báo feedback coverage, sample design và human adjudication.

## 11. Theo dõi xu hướng và phát hiện change point

Một snapshot so reference/current dễ phát hiện shift lớn, nhưng có thể bỏ lỡ thay đổi chậm. Time-series detectors giúp theo dõi xu hướng.

### 11.1. EWMA

Exponentially Weighted Moving Average làm mượt biến động:

\[
Z_t = \lambda X_t + (1-\lambda)Z_{t-1}
\]

Trong đó X_t là giá trị hiện tại, Z_t là EWMA và λ nằm trong khoảng (0,1]. λ nhỏ làm đường xu hướng mượt hơn nhưng phản ứng chậm hơn.

Dùng EWMA cho tỷ lệ pass, latency hoặc empty retrieval rate khi baseline tương đối ổn định. Chọn λ và control limits bằng dữ liệu lịch sử, không dùng một giá trị mặc định cho mọi metric.

### 11.2. CUSUM

CUSUM tích lũy độ lệch khỏi target để phát hiện thay đổi nhỏ kéo dài:

\[
S_t = \max(0, S_{t-1} + X_t - \mu_0 - k)
\]

Trong đó μ0 là baseline và k là allowance/slack. Cảnh báo khi S_t vượt ngưỡng h đã hiệu chỉnh.

Nếu metric là defect rate hoặc pass rate, có thể dùng biến đổi phù hợp với Bernoulli/binomial process thay vì áp công thức số liên tục một cách máy móc.

### 11.3. ADWIN — adaptive windowing

ADWIN duy trì một cửa sổ dữ liệu có kích thước thay đổi. Detector chia cửa sổ thành các phần con, so sánh thống kê của chúng và loại phần cũ khi có bằng chứng về thay đổi. Cách này phù hợp với stream có tốc độ drift không biết trước và không cần cố định một window length cho mọi giai đoạn.

ADWIN chỉ phát hiện thay đổi của tín hiệu mà bạn đưa vào detector, thường là một giá trị số hoặc outcome đã tổng hợp. Nếu đưa relevance pass/fail vào, cần chú ý label delay và sample design; nếu đưa query length vào, detector báo thay đổi độ dài chứ không tự kết luận quality giảm. Tham số confidence và giới hạn bộ nhớ cần được hiệu chỉnh bằng traffic lịch sử.

### 11.4. Change-point detection

Change-point detector tìm thời điểm phân bố hoặc tham số chuỗi thay đổi. Có thể dùng để xác định một đợt shift bắt đầu sau:

- Model/provider rollout.
- Prompt release.
- Index rebuild.
- Policy update.
- Traffic campaign.
- Một sự kiện nghiệp vụ.

Change point cho biết thời điểm thay đổi, không tự giải thích nguyên nhân. Cần đối chiếu deployment timeline và cohort metrics.

### 11.5. Nhiều detector tạo nhiều false alarms

Nếu theo dõi hàng trăm features mỗi giờ, một số detector sẽ báo drift chỉ do ngẫu nhiên. Cần:

- Giới hạn feature có ý nghĩa sản phẩm.
- Dùng correction hoặc kiểm soát false discovery khi chạy nhiều kiểm định.
- Kết hợp statistical significance với effect size và sample count.
- Dùng persistence windows hoặc hysteresis để tránh alert bật/tắt liên tục.
- Đặt severity theo impact và confidence.
- Kiểm tra một alert bằng metric liên quan trước khi tạo incident.

## 12. Nối drift monitoring với Spring AI

Spring AI Observability cung cấp observations cho ChatClient, Advisor, ChatModel, EmbeddingModel và VectorStore. Những observations có thể giúp liên kết thời gian, provider/model metadata và execution path. Tuy nhiên, Spring AI không tự cung cấp một hệ thống drift detector hoàn chỉnh.

Một pipeline thực tế có thể gồm:

~~~mermaid
flowchart TD
    APP["Spring AI application"] --> OBS["Micrometer observations / metrics"]
    APP --> FEATURES["Versioned feature envelope"]
    OBS --> TELEMETRY["OTel / metrics backend"]
    FEATURES --> STREAM["Event stream / feature store"]
    STREAM --> AGG["Window aggregation by cohort"]
    AGG --> DETECT["Drift and quality detectors"]
    DETECT --> ALERT["Dashboard / alert / incident"]
    DETECT --> REVIEW["Sample review / evaluator"]
    REVIEW --> DATASET["Versioned evaluation dataset"]
    DATASET --> REPLAY["Prompt / model / RAG replay"]
    REPLAY --> DECISION["Canary, rollback or accept"]
~~~

### 12.1. Metadata nên gắn với mỗi interaction

Tạo feature envelope ở tầng application, ví dụ:

~~~java
public record InteractionFeatures(
        String interactionId,
        String taskFamily,
        String language,
        String provider,
        String modelFamily,
        String promptVersion,
        String retrieverVersion,
        String indexVersion,
        int inputTokenCount,
        int contextTokenCount,
        int outputTokenCount,
        boolean retrievalEmpty,
        boolean toolUsed,
        boolean toolFailed,
        String finishReasonCategory,
        String usageStatus) {
}
~~~

Ví dụ này chỉ là schema minh họa. Các giá trị như taskFamily và language nên được chuẩn hóa thành taxonomy hữu hạn; interactionId chỉ dùng để nối event store, không dùng làm metric label.

Không bắt buộc lưu raw prompt để theo dõi query length, language hoặc task family. Feature extraction cần version hóa và đánh giá lỗi phân loại; nếu classifier đổi, feature distribution có thể drift vì extractor thay đổi.

### 12.2. Ghi metrics với tags có cardinality thấp

Có thể dùng Micrometer để ghi feature distributions hoặc outcome counters:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.DistributionSummary;

public final class InteractionMetrics {

    private final MeterRegistry registry;

    public InteractionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordInputLength(
            String taskFamily,
            String modelFamily,
            int tokenCount) {

        DistributionSummary.builder("ai.interaction.input.tokens")
                .tags(Tags.of(
                        "task_family", taskFamily,
                        "model_family", modelFamily))
                .register(registry)
                .record(tokenCount);
    }

    public void recordRetrievalOutcome(
            String taskFamily,
            boolean empty) {

        registry.counter(
                "ai.interaction.retrieval.empty",
                "task_family", taskFamily,
                "empty", Boolean.toString(empty))
                .increment();
    }
}
~~~

Đây là ví dụ Micrometer; trong production cần bảo đảm taxonomy labels được kiểm soát và meter được tái sử dụng hiệu quả. Không thêm prompt, user ID, interactionId, document ID hoặc arbitrary model alias vào tags.

DistributionSummary/Timer histogram cần cấu hình buckets phù hợp nếu muốn tính quantiles hoặc histogram-based drift. Không suy ra P95 chính xác từ một summary chỉ có count và sum.

### 12.3. Gắn version vào telemetry

Các chiều hữu ích:

- provider và model family.
- prompt family/version ở mức hữu hạn.
- retriever/index version.
- task family và language.
- pipeline release hoặc deployment cohort.
- outcome status.

Nếu version thay đổi quá thường xuyên hoặc có nhiều giá trị, không đưa tất cả thành metric labels. Có thể lưu version chi tiết trong event store và dùng dashboard filter/tracing link để drill down.

## 13. Tính drift score ngoài request path

Không nên chạy các kiểm định phân bố nặng trong luồng trả lời người dùng. Thu feature event nhẹ trong request, sau đó tính drift trong stream processor hoặc scheduled batch.

Một detector job có thể thực hiện:

1. Đọc reference/current windows đã đủ dữ liệu.
2. Chọn cùng feature schema và cùng cohort definition.
3. Kiểm tra sample count, missing rate và event-time completeness.
4. Tính effect size và statistical test.
5. Tính quality metrics trên labels đã mature.
6. So sánh với deployment/configuration timeline.
7. Lưu drift result với detector version.
8. Gửi alert hoặc tạo review case theo severity.

### 13.1. Drift result schema

~~~json
{
  "detector": "intent-distribution-psi",
  "detectorVersion": "3",
  "feature": "task_family",
  "cohort": "RAG_QA",
  "referenceWindow": {
    "start": "2026-11-01T00:00:00Z",
    "end": "2026-11-14T00:00:00Z"
  },
  "currentWindow": {
    "start": "2026-11-15T00:00:00Z",
    "end": "2026-11-28T00:00:00Z"
  },
  "referenceCount": 18200,
  "currentCount": 19440,
  "driftScore": 0.18,
  "pValue": 0.002,
  "effectSize": 0.14,
  "status": "REVIEW",
  "policyVersion": "drift-policy-v5"
}
~~~

Số liệu chỉ minh họa. Không đặt một threshold toàn cục cho mọi feature. Drift result cần chứa enough metadata để reviewer tái hiện phép so sánh và biết score đến từ detector nào.

### 13.2. Không để drift detector tự sửa model

Detector chỉ tạo tín hiệu. Không tự động thay prompt, retriever, model hoặc threshold chỉ vì drift score vượt ngưỡng. Thay đổi production cần qua quy trình đánh giá, canary và rollback policy phù hợp.

## 14. Prometheus metrics và alert examples

Các metric dưới đây là ví dụ do ứng dụng hoặc drift pipeline tự định nghĩa, không phải tên metric mặc định của Spring AI:

| Metric | Ý nghĩa |
| --- | --- |
| ai_drift_feature_psi | PSI theo feature/cohort/window |
| ai_drift_feature_jsd | Jensen-Shannon divergence |
| ai_drift_feature_ks_statistic | KS statistic cho feature số |
| ai_drift_feature_missing_ratio | Tỷ lệ feature thiếu |
| ai_quality_relevance_pass_ratio | Relevance pass ratio |
| ai_quality_factcheck_pass_ratio | Fact-check pass ratio |
| ai_quality_relevance_pass_total | Counter số evaluation pass relevance |
| ai_quality_evaluated_total | Counter số evaluation cases có kết quả relevance |
| ai_quality_inconclusive_ratio | Tỷ lệ evaluator không đủ evidence |
| ai_quality_label_coverage | Tỷ lệ interaction đã có quality label |
| ai_retrieval_empty_ratio | Tỷ lệ retrieval không có context |
| ai_output_refusal_ratio | Tỷ lệ refusal |
| ai_tool_failure_ratio | Tỷ lệ tool failure |

Chỉ dùng labels có cardinality hữu hạn như feature name, task family, provider, model family, pipeline cohort và detector version đã kiểm soát. Không dùng raw values hoặc unique IDs.

### 14.1. Theo dõi PSI theo feature

~~~promql
max by (feature, task_family) (
  ai_drift_feature_psi
)
~~~

Đây là drift score đã được tính và export bởi detector. Prometheus không tự tính PSI từ raw prompt hoặc distributions.

### 14.2. Theo dõi quality pass ratio

~~~promql
sum by (task_family, model_family) (
  rate(ai_quality_relevance_pass_total[1h])
)
/
sum by (task_family, model_family) (
  rate(ai_quality_evaluated_total[1h])
)
~~~

Chỉ so sánh khi labels có cùng evaluator/rubric version và label maturity. Nếu evaluation sample có inclusion probability khác nhau, cần weighted estimator trong analytics pipeline thay vì dùng raw counter ratio như population estimate.

### 14.3. Alert cần kết hợp drift và quality

Ví dụ rule khái niệm:

~~~yaml
groups:
  - name: ai-quality-drift
    rules:
      - alert: AIInputDistributionShift
        expr: ai_drift_feature_psi > 0.2
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Input distribution changed"
          description: "Review cohort, task mix and quality metrics."

      - alert: AIQualityRegression
        expr: ai_quality_relevance_pass_ratio < 0.85 and increase(ai_quality_evaluated_total[1h]) > 100
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Relevance quality below guardrail"
          description: "Check mature labels, cohort mix and recent releases."
~~~

Các ngưỡng trên chỉ để minh họa cú pháp. Cần hiệu chỉnh theo baseline, minimum sample count, cohort và business impact. Một input shift không nên tự động trở thành critical incident nếu quality vẫn ổn định.

## 15. Phân loại alert theo mức độ ảnh hưởng

Một ma trận phản ứng giúp tránh xử lý mọi drift alert như nhau:

| Input drift | Quality drift | Diễn giải | Hành động |
| --- | --- | --- | --- |
| Không | Không | Phân bố và chất lượng ổn định | Tiếp tục theo dõi |
| Có | Không | Traffic thay đổi nhưng quality chưa giảm | Review chủ đề mới, cập nhật dataset nếu cần |
| Không | Có | Chất lượng giảm dù input mix ổn định | Điều tra model, prompt, retrieval, tools hoặc evaluator |
| Có | Có | Input thay đổi và quality giảm | Ưu tiên cohort mới/shifted, chạy targeted evaluation |
| Retrieval drift | Fact-check giảm | Evidence thay đổi hoặc thiếu | Replay retrieval, kiểm tra corpus/index |
| Prediction drift | Quality ổn định | Behavior đổi nhưng chưa có tác động xấu rõ | Kiểm tra output policy, cost và user experience |
| Missingness drift | Token usage/quality thiếu dữ liệu | Telemetry contract hoặc pipeline thay đổi | Kiểm tra adapter, exporter, ingestion |

Cần xem thêm deployment timeline. Nếu quality giảm đúng sau khi đổi prompt, model hoặc index, đây là giả thuyết điều tra mạnh nhưng vẫn cần xác minh bằng replay hoặc canary.

## 16. Quy trình triage khi phát hiện drift

~~~mermaid
flowchart TD
    ALERT["Drift alert"] --> VALID{"Data complete and detector valid?"}
    VALID -->|No| DATA["Fix ingestion / schema / missingness"]
    VALID -->|Yes| COHORT["Identify affected cohorts"]
    COHORT --> CONFIG["Compare prompt/model/index/tool versions"]
    CONFIG --> QUALITY["Check mature quality labels"]
    QUALITY --> RETRIEVAL["Inspect retrieval and tool traces"]
    RETRIEVAL --> REPLAY["Replay representative cases"]
    REPLAY --> DECIDE{"Regression confirmed?"}
    DECIDE -->|No| BASELINE["Document benign shift / update reference by policy"]
    DECIDE -->|Yes| MITIGATE["Canary, rollback or fix"]
    MITIGATE --> VERIFY["Verify recovery on same cohorts"]
~~~

Các bước thực tế:

1. **Kiểm tra dữ liệu:** event volume, late arrivals, missingness, feature schema và timezone.
2. **Xác định cohort:** ngôn ngữ, task family, pipeline, provider, model và channel.
3. **Đo mức ảnh hưởng:** absolute delta, effect size, sample count và confidence interval.
4. **Kiểm tra quality labels:** cùng evaluator/rubric version, cùng maturity horizon và đúng sampling weights.
5. **Đối chiếu thay đổi:** prompt, model, retriever, index, corpus, tool schema, policy và deployment.
6. **Mở trace/evidence:** kiểm tra retrieval ranks, tool errors, finish reason, latency và usage.
7. **Replay case:** chạy lại representative cases trên baseline và candidate versions.
8. **Mitigate:** rollback, tắt feature, đổi route hoặc cập nhật pipeline sau khi có bằng chứng.
9. **Xác minh:** theo dõi cùng cohort và cùng metrics sau mitigation.
10. **Cập nhật dataset:** thêm confirmed failure cases vào evaluation suite có provenance.

## 17. Canary và release guardrails

Khi thay prompt/model/index, có thể triển khai canary trên một phần traffic. Canary giúp so sánh candidate và control trong cùng khoảng thời gian.

Thiết kế:

- Chia traffic theo user/session hoặc interaction unit ổn định.
- Giữ cohort assignment nhất quán trong conversation.
- Dùng cùng evaluator/rubric và label maturity.
- So sánh theo task family, language và pipeline.
- Theo dõi relevance, fact-check, latency, cost, refusal, tool success và retrieval coverage.
- Đặt minimum sample count và guardrail trước khi tăng traffic.
- Có rollback trigger và owner rõ ràng.

Không để canary candidate nhận toàn bộ nhóm tác vụ khó còn control nhận tác vụ dễ. Nếu assignment không ngẫu nhiên, cần điều chỉnh hoặc giới hạn kết luận.

### 17.1. Shadow evaluation

Shadow mode chạy candidate model/prompt trên một bản sao input hoặc selected traffic mà không trả candidate response cho người dùng. Có thể so candidate output với production output qua evaluator hoặc human review.

Shadow mode cần tính thêm chi phí và kiểm soát dữ liệu. Không thực thi tool side effects lần thứ hai chỉ để shadow; tool calls cần mock, replay an toàn hoặc chỉ quan sát plan.

### 17.2. Rollback không xóa bằng chứng

Khi rollback, giữ drift result, deployment version, sample references và reviewer notes. Chúng giúp xác định regression và ngăn lỗi lặp lại trong release sau.

## 18. Bảo vệ dữ liệu khi theo dõi distribution

Drift monitoring không cần trở thành kho raw prompts.

- Ưu tiên feature summary, bounded categories, aggregate counts và embeddings đã được kiểm soát.
- Không dùng raw prompt, completion, user ID, email, document text hoặc tool arguments làm metric labels.
- Nếu cần semantic review, lấy mẫu có giới hạn và lưu evidence trong kho riêng có mã hóa, access control, audit và TTL.
- Redact PII và secrets trước khi đưa evidence vào review tools.
- Giữ tenant isolation khi tạo cohort và aggregate.
- Đặt retention cho raw evidence, feature events và aggregate riêng biệt.
- Version hóa feature extractor; thay đổi extractor có thể tạo artificial drift.
- Không truyền dữ liệu nhạy cảm qua trace baggage.
- Kiểm tra quyền sử dụng dữ liệu cho mục đích evaluation, analytics và model improvement.

Nếu embeddings có thể tiết lộ nội dung hoặc nhận diện dữ liệu cá nhân trong bối cảnh sản phẩm, áp dụng cùng mức bảo vệ phù hợp với dữ liệu nguồn. Embedding không tự động là dữ liệu ẩn danh.

## 19. Các lỗi diễn giải thường gặp

| Triệu chứng | Kết luận vội vàng | Kiểm tra đúng |
| --- | --- | --- |
| PSI cao ở task family | Model quality giảm | Kiểm tra task mix và quality trong từng cohort |
| P-value rất nhỏ | Drift có impact lớn | Xem effect size và sample count |
| Relevance overall giảm | Model mới kém | Chuẩn hóa task mix và so cohort |
| Token usage giảm | Prompt ngắn hơn | Kiểm tra usage coverage, adapter và missingness |
| Embedding centroid dịch chuyển | Chủ đề mới xuất hiện | Kiểm tra embedding model/preprocessing version |
| Retrieval score giảm | Corpus kém | Kiểm tra embedding/index/query rewrite/reranker |
| User negative rate tăng | Accuracy giảm cùng mức | Kiểm tra feedback coverage và self-selection bias |
| Judge score giảm | Generation quality giảm | Kiểm tra evaluator model/rubric calibration |
| Không có defect trong sample | Không có lỗi | Xem sample size, inclusion probability và confidence interval |
| Alert liên tục bật/tắt | Nhiều incident | Kiểm tra seasonality, hysteresis và minimum volume |
| Quality labels chưa đủ | Chất lượng giảm | Chờ label maturity hoặc báo provisional |
| Input drift nhưng quality ổn | Cần rollback | Review chủ đề mới và tiếp tục theo dõi |

## 20. Bài tập thực hành

### Bài 1. Theo dõi task mix

Tạo feature envelope với language và task family. So sánh phân bố theo ngày và theo weekday. Tính PSI hoặc JSD và giải thích thay đổi nào có ý nghĩa sản phẩm.

### Bài 2. Tách data drift và quality drift

Tạo hai cohort direct chat và RAG. Theo dõi input distribution và relevance pass rate riêng. Tạo tình huống task mix thay đổi nhưng pass rate trong từng cohort không đổi; giải thích vì sao overall score giảm.

### Bài 3. Retrieval drift

Chạy cùng bộ query cố định qua hai index versions. So document IDs, rank, score, Recall@K, empty retrieval rate và context token count. Xác định thay đổi đến từ corpus hay retriever config.

### Bài 4. Semantic drift

Tạo embeddings bằng cùng một embedding model version cho reference và current windows. So cluster share và nearest-neighbor distance. Lấy mẫu các query thuộc cluster mới để reviewer đặt tên chủ đề.

### Bài 5. Quality labels trễ

Tạo dashboard thể hiện label coverage sau 1 giờ, 24 giờ và 7 ngày. So sánh pass rate trên cùng maturity horizon. Không coi case chưa có label là fail hoặc pass.

### Bài 6. EWMA/CUSUM

Tạo chuỗi relevance pass ratio giả lập, thêm một thay đổi nhỏ kéo dài. So sánh raw threshold với EWMA hoặc CUSUM; đo thời gian phát hiện và false alarms.

### Bài 7. Canary model/prompt

Chia traffic ổn định giữa control và candidate. So relevance, fact-check, latency, token usage, tool success theo cùng cohort. Đặt minimum sample count và rollback guardrail.

### Bài 8. Drift triage

Tạo một alert input PSI cao nhưng quality ổn định, và một alert quality giảm trong khi input mix ổn định. Viết triage notes, kiểm tra trace/evidence và đề xuất hành động khác nhau cho hai trường hợp.

## 21. Tổng kết

Phát hiện thay đổi phân bố câu hỏi và chất lượng theo thời gian cần theo dõi nhiều tầng:

- Data drift cho biết input và task mix thay đổi.
- Concept drift cho biết quan hệ giữa input và kết quả mong muốn thay đổi.
- Prediction drift cho biết model behavior/output distribution thay đổi.
- Retrieval drift cho biết evidence RAG thay đổi.
- Quality drift cho biết outcome như relevance, fact checking hoặc task success suy giảm.
- Fixed, rolling và seasonal baselines giúp phân biệt thay đổi ngắn hạn, dài hạn và mùa vụ.
- Chi-square, PSI, JSD, KS, Wasserstein và embedding-based methods phù hợp với các loại feature khác nhau; luôn xem effect size và sample count.
- Cohort analysis và standardized quality score giúp tránh kết luận sai do task mix thay đổi.
- Labels trễ cần maturity tracking; evaluator và human labels phải có version/provenance.
- EWMA, CUSUM, ADWIN và change-point detection giúp nhận ra xu hướng nhưng cần kiểm soát false alarms.
- Spring AI cung cấp observations/metrics/traces; drift detection và feature pipeline cần được ứng dụng xây dựng riêng.
- Alert phải dẫn tới triage, replay, canary hoặc rollback có kiểm chứng.

Mục tiêu của drift monitoring là phát hiện sớm điều kiện production đã khác baseline, tìm cohort bị ảnh hưởng và xác minh chất lượng bằng evidence. Khi kết hợp feature distributions, RAG traces, evaluator results và deployment versions, nhóm phát triển có thể phân biệt traffic shift hợp lệ với regression thực sự.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatClient, ChatModel, EmbeddingModel, VectorStore observations, metrics và traces.
- [Evidently AI — Data Drift](https://docs.evidentlyai.com/metrics/explainer_drift): cách đo data drift bằng feature distributions và lựa chọn phương pháp thống kê.
- [Evidently AI — Data Drift Presets](https://docs.evidentlyai.com/metrics/preset_data_drift): drift reports, feature-level metrics và threshold configuration.
- [River — ADWIN](https://riverml.xyz/latest/api/drift/ADWIN/): adaptive windowing để phát hiện thay đổi trong data streams.
- [SciPy — Kolmogorov-Smirnov two-sample test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html): kiểm định hai empirical distributions.
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): khái niệm metrics, aggregation và time series.
