# Bảo toàn khả năng so sánh với kết quả thí nghiệm trước

## 1. Vì sao kết quả thí nghiệm dễ mất khả năng so sánh?

Một ứng dụng Spring AI thường thay đổi theo nhiều trục: generation model, prompt, embedding model, chunking, retrieval top-k, reranker, tool schema, evaluator, judge model, rubric và cách tính điểm. Nếu mỗi lần chạy chỉ lưu một điểm tổng hợp hoặc một con số latency, nhóm phát triển rất khó xác định chất lượng thực sự tăng hay giảm sau nâng cấp.

Ví dụ, prompt mới làm answer relevance tăng từ 0,78 lên 0,84. Nhưng lần chạy mới đồng thời dùng dataset dễ hơn, judge model mới và rubric đã hạ threshold. Hai con số không còn đo cùng một thứ. Kết luận rằng prompt mới tốt hơn sẽ không có cơ sở.

Bài **“Bảo toàn khả năng so sánh với kết quả thí nghiệm trước”** thuộc chương **Nâng cấp** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module học đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua từng phiên bản prompt, model và pipeline.

Mục tiêu của bài là thiết lập một hợp đồng so sánh giữa các lần thí nghiệm, giữ lại dữ liệu và metadata đủ để tái phân tích, nhận diện yếu tố gây nhiễu và đưa ra quyết định nâng cấp có bằng chứng.

## 2. Phân biệt reproducibility và comparability

Hai khái niệm liên quan nhưng không giống nhau:

| Khái niệm | Câu hỏi | Điều kiện chính |
| --- | --- | --- |
| **Reproducibility** | Có thể chạy lại và tái tạo kết quả trước không? | Artifact, dữ liệu, cấu hình và môi trường được lưu đủ |
| **Comparability** | Có thể so kết quả hai lần chạy một cách công bằng không? | Định nghĩa metric, population, phương pháp đo và điều kiện đủ tương đồng |
| **Traceability** | Có thể giải thích một kết quả được tạo ra từ đâu không? | Provenance và version manifest đầy đủ |

Có thể không tái tạo chính xác output của một model hosted vì provider thay đổi implementation hoặc model alias. Tuy vậy, vẫn có thể giữ comparability bằng cách lưu model identity, request metadata, dataset cố định, judge/rubric cố định và thiết kế paired experiment.

Ngược lại, có thể tái chạy đúng một script nhưng không so sánh được với kết quả cũ nếu dataset, rubric hoặc metric semantics đã thay đổi.

## 3. Xác định câu hỏi thí nghiệm trước khi chạy

Mỗi experiment cần nêu rõ một giả thuyết và biến cần kiểm tra:

- Prompt mới có tăng groundedness mà không làm latency tăng quá budget không?
- Model mới có giảm false pass trên các câu hỏi cần trích dẫn không?
- Retrieval top-k mới có tăng recall nhưng làm token cost vượt ngân sách không?
- Instrumentation mới có tăng trace coverage mà không làm API p95 suy giảm đáng kể không?
- Evaluator/rubric mới có đồng thuận tốt hơn với human review không?

Ghi rõ:

1. **Treatment:** yếu tố được thay đổi, ví dụ prompt v12 sang v13.
2. **Control:** cấu hình tham chiếu, ví dụ prompt v12.
3. **Primary metric:** metric chính dùng để quyết định.
4. **Guardrail metrics:** latency, cost, error rate, false pass hoặc resource usage.
5. **Population:** dataset, cohort, language, tenant class hoặc operation.
6. **Decision rule:** mức cải thiện tối thiểu và regression tối đa có thể chấp nhận.

Không chọn metric sau khi đã nhìn thấy kết quả chỉ vì metric đó ủng hộ phiên bản mới. Chốt primary metric và guardrails trước khi chạy để hạn chế cherry-picking.

## 4. Các trục phải cố định hoặc ghi lại

Muốn so sánh hai lần chạy, cần kiểm soát các yếu tố sau:

| Trục | Cách giữ comparability |
| --- | --- |
| Dataset | Cùng dataset version và case IDs |
| Expected labels | Giữ nguyên nhãn/human adjudication hoặc ghi version mới |
| Input | Cùng câu hỏi, metadata và conversation history |
| Context | Dùng snapshot context giống nhau khi chỉ thử judge/rubric |
| Generation model | Ghi provider, model ID/snapshot, parameters |
| Prompt | Ghi version và checksum |
| Retrieval | Ghi embedding, index, chunking, filter, top-k, reranker |
| Tool | Ghi tool schema, implementation và dependency version |
| Evaluator | Ghi evaluator implementation và configuration |
| Rubric/judge | Ghi rubric, judge prompt, model và scoring version |
| Sampling | Ghi sample policy, seed và lý do chọn case |
| Runtime | Ghi JDK, app build, region, concurrency và resource limits |
| Metrics | Giữ unit, aggregation, histogram buckets và semantics |

Không phải mọi thí nghiệm cần cố định tất cả các trục. Nếu mục tiêu là kiểm tra retrieval pipeline, retrieval chính là treatment. Nhưng các trục không thuộc treatment cần được giữ ổn định hoặc đo lường để có thể giải thích khác biệt.

## 5. Dùng immutable dataset và golden set có version

Golden dataset là điểm neo quan trọng cho các lần nâng cấp. Mỗi version nên có:

- dataset ID và version;
- case ID ổn định;
- input/question;
- context/document snapshot hoặc reference;
- expected behavior/label;
- category, language và difficulty;
- human review status;
- created/updated timestamp;
- checksum hoặc artifact digest.

Không sửa dataset version đã dùng trong báo cáo lịch sử. Khi sửa expected answer, loại case lỗi hoặc thêm case mới, tạo version mới và ghi changelog.

### Chia dataset theo mục đích

| Subset | Mục tiêu | Cách sử dụng |
| --- | --- | --- |
| Golden regression | So sánh qua release | Giữ cố định lâu dài |
| Calibration | Hiệu chỉnh judge/rubric | Có human labels đáng tin cậy |
| Challenge set | Case khó, edge case, adversarial | Kiểm tra failure mode |
| Fresh traffic sample | Phản ánh traffic gần đây | Đo drift, không thay golden set |
| Holdout | Kiểm tra độc lập | Không dùng để tune prompt/rubric |

Nếu liên tục tune prompt trên golden set, kết quả có thể overfit. Giữ một holdout riêng và quản lý quyền truy cập phù hợp.

## 6. Giữ context cố định khi so sánh evaluator hoặc rubric

Khi thay judge prompt hoặc rubric, muốn cô lập tác động của evaluator thì phải đưa cùng answer và cùng context cho cả hai phiên bản.

Ví dụ:

- Answer A được sinh từ prompt v12.
- Context snapshot C17 chứa ba tài liệu đã truy xuất.
- Rubric v4 và rubric v5 cùng chấm answer A với context C17.
- Judge profile được giữ nguyên nếu chỉ muốn đo rubric.

Nếu chạy retrieval lại trên index mới trước khi chấm, cả context lẫn rubric đã thay đổi. Khi đó kết quả phản ánh nhiều treatment cùng lúc.

Nên lưu context reference bất biến hoặc snapshot đã được quản lý an toàn. Nếu không thể lưu raw content, lưu document IDs/version, chunk IDs, retrieval score và content checksum để xác minh snapshot. Cần lưu ý rằng checksum chỉ chứng minh nội dung giống nhau khi có thể lấy lại artifact gốc.

## 7. Version manifest cho mỗi experiment run

Mỗi run cần có manifest ghi rõ cấu hình thực tế đã dùng. Ví dụ:

```yaml
experiment:
  id: rag-prompt-comparison-042
  runId: run-2026-11-27-a
  hypothesis: "Prompt v13 improves groundedness"
  treatment: "generation.prompt=v13"
  control: "generation.prompt=v12"
  dataset:
    id: rag-golden
    version: "2026-11-20"
    checksum: "sha256:example"
  generation:
    provider: provider-a
    modelProfile: generation-stable
    modelId: model-snapshot-17
    promptVersion: answer-v13
    temperature: 0
  retrieval:
    pipelineVersion: retrieval-v7
    indexSnapshot: index-2026-11-20
    topK: 5
  evaluation:
    evaluatorVersion: evaluator-v3
    rubricVersion: rag-rubric-v4
    judgeModelId: judge-snapshot-4
    scoringVersion: weighted-mean-v1
  runtime:
    applicationVersion: "2.8.1"
    jdk: "21"
    region: staging-a
    concurrency: 20
```

Đây là schema ứng dụng minh họa. Các giá trị phải được ghi từ cấu hình runtime thực tế, không điền theo giá trị mong muốn. Nếu provider không trả immutable model ID, ghi alias, provider, deployment revision và timestamp; đánh dấu model identity là chưa xác định hoàn toàn.

## 8. Lưu raw result, không chỉ lưu điểm tổng hợp

Một experiment result nên giữ:

- run ID, experiment ID, case ID;
- request/trace correlation reference;
- input/context artifact reference;
- generated answer reference hoặc secured payload;
- generation model/prompt/retrieval versions;
- evaluator/rubric/judge versions;
- raw criterion scores;
- aggregate score và scoring version;
- verdict/status riêng biệt;
- latency, token usage và cost;
- retry count, provider status và error code;
- timestamp và runtime metadata.

Điểm tổng hợp là dữ liệu dẫn xuất. Nếu chỉ lưu score cuối, khi đổi weight hoặc scoring algorithm sẽ không thể tính lại.

Không lưu prompt, answer hay context nhạy cảm ở dạng raw nếu không có nhu cầu, quyền truy cập và retention rõ ràng. Có thể lưu reference đến artifact đã được quản lý, kèm checksum và metadata đủ để truy nguyên.

## 9. Thiết kế paired experiment để giảm nhiễu

Khi có thể chạy hai cấu hình trên cùng input, paired comparison thường mạnh hơn việc chia traffic thành hai nhóm khác nhau.

Ví dụ, cùng 500 case được chạy qua:

- Control: prompt v12.
- Treatment: prompt v13.

Mỗi case có hai result được liên kết bằng experiment ID và case ID. So sánh hiệu số trên từng case:

```text
paired_difference_i = score_treatment_i - score_control_i

mean_paired_difference =
    sum(paired_difference_i) / number_of_pairs
```

Paired design giảm ảnh hưởng của độ khó khác nhau giữa các câu hỏi vì mỗi case đóng vai trò control cho chính nó.

Paired experiment phù hợp khi thay prompt, judge, rubric hoặc pipeline trên một bộ input cố định. Với generation có tính ngẫu nhiên, cần cố định seed nếu model hỗ trợ; nếu không, có thể chạy nhiều lần mỗi case và ghi run replicate.

## 10. Khi nào nên dùng cohort/A-B experiment?

Không phải lúc nào cũng có thể chạy hai cấu hình trên cùng một request. Với traffic production, có thể chia cohort theo hash ổn định hoặc feature flag.

Cần kiểm tra hai nhóm tương đương về:

- language;
- use case/operation;
- tenant tier;
- prompt length/context size;
- difficulty;
- traffic time window;
- model/provider;
- user/device/client mix nếu liên quan.

Nếu treatment nhận nhiều câu hỏi ngắn hơn control, pass rate có thể tăng dù chất lượng không đổi. Dùng stratification hoặc weighting để điều chỉnh population mix; công bố cả số liệu thô và adjusted metrics.

Không phân nhóm bằng cách chọn case theo kết quả sau khi chạy. Cohort assignment cần xác định trước và có thể tái tạo.

## 11. Judge drift và rubric drift

Khi judge model hoặc rubric thay đổi, điểm số có thể đổi ngay cả khi answer không đổi.

Phân biệt:

- **Rubric drift:** tiêu chí, weight, threshold hoặc cách diễn giải thay đổi.
- **Judge drift:** model/provider snapshot hoặc judge prompt thay đổi.
- **Scoring drift:** code chuẩn hóa hoặc aggregate score thay đổi.
- **Dataset drift:** population hoặc expected labels thay đổi.
- **Input drift:** answer/context thay đổi do generation/retrieval.

### Bridge set để nối hai thang đo

Khi bắt buộc đổi judge/rubric, tạo một bridge set gồm các answer/context cố định được chấm bởi cả hệ thống cũ và mới. So sánh:

- criterion-level score;
- pass/fail disagreement;
- false pass/false fail so với human labels;
- phân bố score và calibration;
- kết quả theo language/use case/difficulty.

Bridge set giúp ước lượng mức lệch giữa hai hệ thống chấm. Nó không biến hai rubric khác semantics thành cùng một thước đo. Nếu rubric mới đánh giá thêm citation hoặc safety, cần báo cáo tiêu chí mới riêng thay vì ép aggregate score vào cùng scale.

## 12. Không chuẩn hóa score để che giấu thay đổi semantics

Có thể cần chuẩn hóa score khi judge model có xu hướng chấm cao/thấp khác nhau, nhưng phải công bố phương pháp và giữ raw score.

Các cách có thể dùng:

- calibration mapping trên human-labeled bridge set;
- z-score trong một population đã định nghĩa;
- phân vị (percentile) trong cùng cohort;
- tách báo cáo theo rubric/criterion version.

Không so z-score từ hai population khác nhau như thể cùng một thước đo. Không dùng min-max scaling trên từng run nếu mỗi run có phân bố khác nhau; cách đó có thể làm mất thay đổi thật.

Khi semantics rubric thay đổi, báo cáo raw criterion scores và version-specific pass rate. Nếu không có calibration bridge đủ tin cậy, đánh dấu score series là không so sánh trực tiếp.

## 13. So sánh metric telemetry qua các phiên bản

Metrics cũng cần comparability contract:

- tên và type (counter, gauge, histogram);
- unit;
- aggregation;
- histogram bucket boundaries;
- label dimensions;
- reset behavior;
- sampling semantics;
- scope (per request, per operation, per token).

Ví dụ, p95 latency từ histogram có bucket khác nhau hoặc từ client-side timer khác nhau có thể không so sánh trực tiếp. Metric cũ tính thời gian toàn request, metric mới chỉ tính model call; cùng tên không có nghĩa cùng semantics.

Khi đổi metric contract:

1. Tạo metric mới hoặc schema version mới nếu meaning thay đổi.
2. Dual-publish/dual-read trong giai đoạn chuyển tiếp nếu cần.
3. Ghi rõ unit và aggregation.
4. Cập nhật dashboard/alert.
5. So sánh hai series trong một cửa sổ overlap.
6. Ngừng series cũ sau khi xác nhận consumer đã chuyển.

Không thay đổi unit tại chỗ hoặc cộng các counter đã reset mà không xử lý reset semantics.

## 14. Latency phải so trong điều kiện tải tương đương

Latency phụ thuộc concurrency, queueing, cache, network, provider region và token count. Khi so hai model/prompt:

- giữ concurrency và request mix tương đương;
- tách cold start khỏi steady state;
- ghi cache hit/miss;
- ghi input/output token counts;
- ghi time-to-first-token và full response duration riêng;
- đo p50/p95/p99;
- chạy cùng region/network path nếu có thể;
- ghi provider throttling và retry;
- tách queue wait khỏi service time.

Không so p95 của một run tải 10 request đồng thời với run khác tải 200 request đồng thời rồi quy chênh lệch cho model.

Với streaming, so time-to-first-token và inter-token latency riêng. Full completion duration có thể tăng chỉ vì treatment sinh câu trả lời dài hơn; chuẩn hóa theo token count có thể hữu ích nhưng phải báo cả latency thực tế người dùng cảm nhận.

## 15. Cost và token usage cũng cần cùng định nghĩa

Khi so chi phí, ghi:

- provider/model ID và price schedule version;
- input/output token usage;
- cached input token semantics;
- embedding token/request usage;
- judge calls và retries;
- tool/API charges nếu có;
- currency và thời điểm quy đổi;
- cost per request, cost per evaluated case và cost per successful outcome.

Giá provider có thể thay đổi theo thời gian. Báo cáo nên phân biệt:
- **Observed spend:** chi phí thực tế theo invoice/usage provider.
- **Estimated cost:** usage nhân với price schedule đã version.
- **Normalized cost:** chi phí quy về cùng bảng giá tham chiếu để so hiệu quả model.

Không ghi đè giá lịch sử khi provider thay đổi bảng giá. Lưu price schedule version để có thể tái tính normalized cost.

## 16. Đo độ không chắc chắn, không chỉ so trung bình

Một khác biệt điểm số nhỏ có thể chỉ là nhiễu lấy mẫu. Báo cáo nên có:

- số case và số cặp hợp lệ;
- mean/median;
- standard deviation hoặc IQR;
- confidence interval;
- pass/fail count;
- missing/error/skipped count;
- phân tích theo nhóm quan trọng.

Với paired score, bootstrap trên các cặp case có thể ước lượng confidence interval cho mean/median paired difference. Với pass/fail paired, McNemar test có thể phù hợp khi thiết kế và điều kiện của kiểm định được đáp ứng. Với hai cohort độc lập, dùng phương pháp phù hợp với dữ liệu độc lập và phân bố thực tế.

Không diễn giải p-value như xác suất treatment tốt hơn. Báo cáo cả effect size, confidence interval và mức cải thiện tối thiểu có ý nghĩa nghiệp vụ. Nếu sample nhỏ, kết luận nên là chưa đủ bằng chứng thay vì khẳng định không có khác biệt.

## 17. Kiểm soát missing data và lỗi evaluator

Khi evaluator timeout, provider trả 429 hoặc parser lỗi, result không phải score 0.

Phân biệt rõ:

| Status | Ý nghĩa | Xử lý khi tổng hợp |
| --- | --- | --- |
| PASS | Đạt tiêu chí | Tính vào mẫu hợp lệ |
| FAIL | Đã chấm và không đạt | Tính vào mẫu hợp lệ |
| ERROR | Không chấm được do lỗi kỹ thuật | Báo riêng, không tính như FAIL |
| UNKNOWN | Không đủ bằng chứng hoặc trạng thái không rõ | Báo riêng |
| SKIPPED | Không được chọn/chạy theo policy | Báo coverage |
| EXPIRED | Quá deadline | Báo riêng |

Báo cáo pass rate cần nêu mẫu số. Ví dụ 90 PASS trong 100 job tạo ra không có nghĩa pass rate 90% nếu 10 job còn lại chưa hoàn tất. Có thể báo:
- completed verdict rate = (PASS + FAIL) / eligible jobs;
- pass rate = PASS / (PASS + FAIL);
- evaluation coverage = evaluated jobs / eligible jobs.

Giữ các tỷ lệ riêng để không che lấp lỗi evaluator hoặc backlog.

## 18. So sánh theo nhiều tiêu chí thay vì một score tổng

Một phiên bản có thể tăng relevance nhưng giảm groundedness hoặc tăng cost. Bảng so sánh nên có các tiêu chí:

| Dimension | Control | Treatment | Delta | Guardrail |
| --- | ---: | ---: | ---: | --- |
| Relevance | 0.82 | 0.86 | +0.04 | Không giảm |
| Groundedness | 0.88 | 0.87 | -0.01 | Giảm tối đa 0.02 |
| Citation correctness | 0.91 | 0.93 | +0.02 | Không giảm |
| p95 latency | 1.2 s | 1.3 s | +0.1 s | Tăng tối đa 10% |
| Cost/case | $0.014 | $0.016 | +14.3% | Tăng tối đa 15% |

Các số liệu giả định. Cần ghi định nghĩa score, số mẫu và confidence interval. Một score tổng có thể che giấu regression ở nhóm case quan trọng; luôn xem criterion-level và segment-level results.

## 19. Experiment registry và lịch sử bất biến

Nên lưu experiment/run metadata trong một registry hoặc result store. Mỗi lần chạy tạo record mới, không ghi đè kết quả cũ.

Ví dụ schema SQL tham khảo:

```sql
CREATE TABLE experiment_run (
    run_id UUID PRIMARY KEY,
    experiment_id VARCHAR(128) NOT NULL,
    run_label VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    dataset_version VARCHAR(128) NOT NULL,
    dataset_checksum VARCHAR(96),
    application_version VARCHAR(64),
    prompt_version VARCHAR(64),
    model_id VARCHAR(128),
    retrieval_version VARCHAR(64),
    evaluator_version VARCHAR(64),
    rubric_version VARCHAR(64),
    judge_model_id VARCHAR(128),
    scoring_version VARCHAR(64),
    metric_schema_version VARCHAR(64),
    sampling_policy_version VARCHAR(64),
    environment VARCHAR(64),
    status VARCHAR(32) NOT NULL
);

CREATE TABLE experiment_case_result (
    run_id UUID NOT NULL REFERENCES experiment_run(run_id),
    case_id VARCHAR(128) NOT NULL,
    pair_key VARCHAR(128),
    result_status VARCHAR(32) NOT NULL,
    raw_scores JSONB,
    aggregate_score NUMERIC(10, 6),
    latency_ms BIGINT,
    input_tokens BIGINT,
    output_tokens BIGINT,
    estimated_cost NUMERIC(18, 8),
    trace_reference VARCHAR(256),
    PRIMARY KEY (run_id, case_id)
);
```

Schema là ví dụ. Có thể tách model/config manifest, artifacts và metric observations thành bảng riêng. Không đưa prompt/context nhạy cảm vào JSONB mặc định; lưu secured artifact reference nếu cần.

## 20. Quy trình nâng cấp mà vẫn giữ comparability

Một quy trình thực tế:

1. **Freeze baseline:** chốt dataset, artifact, rubric, judge, metric semantics và manifest của control.
2. **Define treatment:** chỉ rõ biến cần thay đổi.
3. **Validate artifacts:** checksum, schema, dataset completeness và config snapshot.
4. **Run control:** chạy baseline trong cùng cửa sổ hoặc lưu output cố định.
5. **Run treatment:** dùng cùng input/pair keys, giữ các yếu tố khác ổn định.
6. **Re-evaluate bridge set:** nếu judge/rubric thay đổi, chấm lại cùng output bằng hệ thống cũ và mới.
7. **Analyze:** paired/cohort, confidence interval, subgroup và guardrails.
8. **Review missingness:** kiểm tra ERROR/UNKNOWN/SKIPPED và coverage.
9. **Decide:** accept, reject hoặc inconclusive theo decision rule đã định.
10. **Archive:** lưu manifest, raw results, report, query và artifact checksum.

Nếu model provider thay đổi âm thầm, đánh dấu run có model identity uncertainty. Không loại bỏ dữ liệu này; vẫn lưu và ghi rõ giới hạn comparability.

## 21. Quyết định nâng cấp theo bằng chứng

Có thể phân loại quyết định:

| Kết luận | Khi nào dùng |
| --- | --- |
| ACCEPT | Primary metric đạt mức cải thiện có ý nghĩa và guardrails không vi phạm |
| REJECT | Có regression đáng kể hoặc vi phạm guardrail |
| INCONCLUSIVE | Sample chưa đủ, confidence interval rộng hoặc comparability không đạt |
| NEEDS_CALIBRATION | Judge/rubric mới chưa được nối thang đo với baseline |
| NEEDS_MORE_DATA | Một subgroup quan trọng chưa đủ coverage |

Không ép mọi experiment thành accept/reject. Inconclusive là kết quả hợp lệ nếu dữ liệu chưa đủ.

Khi treatment thay đổi nhiều thành phần cùng lúc, kết luận chỉ nên nói toàn bộ bundle tốt/xấu hơn. Muốn biết thành phần nào tạo tác động, cần thí nghiệm tách biến hoặc factorial design phù hợp.

## 22. Checklist trước khi công bố so sánh

- [ ] Có experiment ID và giả thuyết rõ ràng.
- [ ] Primary metric và guardrails được chốt trước.
- [ ] Dataset version/checksum được ghi.
- [ ] Control và treatment dùng cùng input/pair keys khi phù hợp.
- [ ] Prompt/model/retrieval/tool/evaluator/rubric versions được ghi.
- [ ] Judge drift đã được kiểm soát hoặc calibration bridge được chạy.
- [ ] Metric names, units, histogram và aggregation tương thích.
- [ ] Latency được đo dưới tải và môi trường tương đương.
- [ ] Cost dùng cùng price schedule hoặc báo observed/normalized riêng.
- [ ] ERROR/UNKNOWN/SKIPPED được tách khỏi PASS/FAIL.
- [ ] Có sample size, confidence interval và effect size.
- [ ] Có phân tích subgroup quan trọng.
- [ ] Raw result và manifest được lưu bất biến.
- [ ] Giới hạn comparability được công bố rõ.

## 23. Bài tập thực hành

1. **Confounders:** prompt v13 có score cao hơn v12 nhưng dataset, judge và rubric đều đổi. Liệt kê các yếu tố gây nhiễu.
2. **Paired design:** thiết kế paired experiment cho 300 câu hỏi RAG với cùng context snapshot.
3. **Cohort design:** chia traffic A/B nhưng hai nhóm khác ngôn ngữ. Cách stratify?
4. **Judge bridge:** thiết kế bridge set để chuyển từ judge model A sang B.
5. **Rubric change:** rubric mới thêm citation criterion. Vì sao aggregate score không còn trực tiếp comparable?
6. **Metric schema:** histogram bucket boundaries thay đổi. Điều gì xảy ra với p95 lịch sử?
7. **Cost:** so observed spend và normalized cost khi provider đổi giá.
8. **Missing data:** 100 jobs gồm 70 PASS, 10 FAIL, 10 ERROR và 10 PENDING. Tính pass rate và coverage đúng mẫu số.
9. **Confidence interval:** chọn phương pháp ước lượng uncertainty cho paired score difference.
10. **Dataset drift:** fresh traffic sample có phân bố khác golden set. Báo cáo hai loại kết quả ra sao?
11. **Latency:** hai model có output token count khác nhau. So time-to-first-token và full duration thế nào?
12. **Experiment registry:** xác định fields tối thiểu để tái truy nguyên một run sau sáu tháng.
13. **Decision rule:** đặt điều kiện ACCEPT/REJECT/INCONCLUSIVE cho prompt mới.
14. **Multi-factor change:** thiết kế thí nghiệm tách prompt effect và retrieval effect.
15. **Audit:** kiểm tra một báo cáo cũ có đủ provenance để so với release hiện tại không.

## Tài liệu tham khảo

- [Spring AI – Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, EvaluationRequest, EvaluationResponse, RelevancyEvaluator và FactCheckingEvaluator.
- [Spring AI – Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): model observations, metrics và traces.
- [OpenTelemetry – Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): semantics và schema của telemetry.
- [Prometheus – Metric and Label Naming](https://prometheus.io/docs/practices/naming/): metric type, unit, naming và label.
- [Google SRE Workbook – Experimentation](https://sre.google/workbook/): phương pháp đánh giá thay đổi và đo lường hệ thống.
- [NIST – Statistical Methods](https://www.itl.nist.gov/div898/handbook/): phân tích biến thiên, thiết kế thí nghiệm và khoảng tin cậy.
- [PostgreSQL – JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): lưu metadata/result payload có cấu trúc.

> **Ghi chú triển khai:** Experiment manifest, SQL schema, metric names và decision categories trong bài là thiết kế tham khảo của ứng dụng, không phải schema mặc định của Spring AI. Hãy ghi metadata từ runtime thực tế, giữ artifact bất biến, kiểm tra semantics của metric và công bố giới hạn khi model provider không cung cấp identity cố định. Bài viết là hướng dẫn thiết kế comparability, chưa phải kết quả benchmark hoặc phân tích thống kê trên hệ thống thực tế.
