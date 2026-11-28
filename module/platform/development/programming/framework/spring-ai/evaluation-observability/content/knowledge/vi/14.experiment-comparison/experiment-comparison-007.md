# Phân biệt cải thiện chất lượng với thay đổi độ trễ hoặc chi phí

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Số liệu trong bài là ví dụ giả lập để học phương pháp, không phải benchmark của một model/provider cụ thể.

## 1. Vì sao không thể chỉ nhìn một con số?

Một lần chạy evaluation báo:

| Phiên bản | Quality pass rate | p95 latency | Cost / eligible case |
|---|---:|---:|---:|
| A — baseline | 92% | 1,2 giây | 0,018 USD |
| B — candidate | 94% | 2,4 giây | 0,033 USD |

Candidate B tăng chất lượng 2 điểm phần trăm, nhưng p95 latency tăng gấp đôi và chi phí mỗi case tăng khoảng 83%. Nếu chỉ nhìn quality, ta có thể chọn B và làm trải nghiệm chậm hơn, tốn kém hơn. Nếu chỉ nhìn chi phí, ta có thể loại B dù phần cải thiện factuality có giá trị lớn với một workflow quan trọng.

Một thí nghiệm Spring AI cần trả lời ba câu hỏi riêng:

1. **Chất lượng:** câu trả lời có đúng, liên quan, grounded, an toàn và dùng tool đúng không?
2. **Hiệu năng:** người dùng phải chờ bao lâu, tail latency ra sao, hệ thống chịu tải thế nào?
3. **Chi phí:** một request/case thành công tiêu tốn bao nhiêu tiền và tài nguyên?

Các chỉ số này liên quan nhưng không thay thế nhau. Quality score không phải latency; token count không phải cost; p95 không phải average; và một điểm tổng hợp có trọng số tùy ý không thể tự quyết định trade-off phù hợp với nghiệp vụ.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Tách quality, latency, throughput, reliability và cost thành các trục đo riêng.
2. Xác định đơn vị đo và denominator cho từng metric.
3. Đo latency end-to-end và latency từng stage của RAG/tool pipeline.
4. Tính chi phí theo request, eligible case, completed case và successful case.
5. Phân biệt actual spend với normalized cost khi rate card thay đổi.
6. Nhận diện Pareto frontier và phương án bị dominated.
7. Thiết kế A/B có cùng case set, run blocks, concurrency và workload.
8. Đọc quality/latency/cost cùng uncertainty, coverage và critical failures.
9. Đặt quality floor, performance SLO, cost budget và critical veto.
10. Dùng Java 21 để tổng hợp efficiency report và kiểm tra release gate.

## 2. Tách các trục đo lường

| Trục | Câu hỏi | Ví dụ metric |
|---|---|---|
| Quality | Answer có đạt yêu cầu không? | Relevance, fact-check pass rate, groundedness, tool correctness |
| Latency | Request hoàn tất nhanh đến đâu? | p50, p95, p99, time-to-first-token |
| Throughput | Hệ thống xử lý được bao nhiêu request? | Requests/second, completed cases/minute |
| Reliability | Request có hoàn tất và có verdict không? | Availability, timeout rate, error rate, evaluation coverage |
| Cost | Tiêu tốn bao nhiêu để phục vụ workload? | USD/request, USD/eligible case, token/case |
| Resource | Hệ thống dùng bao nhiêu tài nguyên? | CPU, memory, connection pool, queue depth |

Không gộp các trục vào một composite score trước khi đặt yêu cầu sản phẩm. Ví dụ:
- Chất lượng phải đạt tối thiểu 90%.
- p95 latency phải dưới 2 giây.
- Cost phải dưới 0,025 USD/eligible case.
- Critical failure phải bằng 0 theo policy.
- Coverage phải đạt ít nhất 98%.

Đây là **constrained optimization**: trước hết hệ thống phải đáp ứng các điều kiện bắt buộc; sau đó mới chọn phương án có hiệu quả tốt nhất trong tập phương án đạt gate.

## 3. Chọn đơn vị đo và denominator trước khi chạy

Một con số cost hoặc latency sẽ khó diễn giải nếu không biết nó được tính trên đơn vị nào.

| Đơn vị | Định nghĩa |
|---|---|
| Model call | Một lần gọi ChatModel/EmbeddingModel |
| Tool call | Một lần thực thi tool |
| Request | Một request từ đầu vào đến response theo boundary đã chọn |
| Case | Một tình huống trong evaluation dataset |
| Attempt | Một lần thực thi case; retry là attempt mới |
| Eligible case | Case đủ điều kiện cho metric cụ thể |
| Completed case | Case có execution hoàn tất theo định nghĩa |
| Evaluated case | Case có verdict PASS/FAIL hợp lệ |
| Successful case | Case đạt quality threshold theo rubric |

Ví dụ một case RAG có thể tạo:
- 1 embedding call;
- 1 vector search;
- 1 generator call;
- 2 tool calls;
- 1 judge call;
- 1 retry generator.

Nếu chỉ đo cost của generator call đầu tiên, con số không đại diện cho toàn bộ pipeline. Nếu tính cả judge offline nhưng so với production cost của baseline, boundary hai bên cũng không nhất quán.

### Metric-specific denominator

- Quality pass rate: PASS / (PASS + FAIL).
- Evaluation coverage: (PASS + FAIL) / eligible cases.
- Timeout rate: timed-out requests / started requests.
- Cost per eligible case: total in-scope spend / eligible cases.
- Cost per completed case: total in-scope spend / completed cases.
- Cost per successful case: total in-scope spend / successful cases.
- p95 latency: percentile trên các request có latency observation, kèm latency coverage và timeout policy.

Không lấy một denominator chung cho tất cả metric. Nếu missing usage hoặc missing latency, phải báo completeness; không tự coi missing là zero.

## 4. Quality không chỉ là một pass rate

Trong ứng dụng Spring AI, quality có nhiều thành phần:

| Thành phần | Câu hỏi đánh giá |
|---|---|
| Relevance | Answer có trả lời đúng câu hỏi không? |
| Factuality | Claims có đúng theo ground truth không? |
| Groundedness | Claims có được hỗ trợ bởi evidence đã truy xuất không? |
| Citation correctness | Citation có trỏ đúng tài liệu/đoạn hỗ trợ không? |
| Retrieval quality | Relevant documents có được retrieve không? |
| Tool correctness | Đúng tool, arguments và side effects không? |
| Abstention | Có từ chối/nêu thiếu dữ kiện đúng lúc không? |
| Safety/policy | Có lộ dữ liệu hoặc vượt policy không? |

Không để relevance tăng bù cho fact-check giảm. Một answer trôi chảy và đúng chủ đề nhưng sai điều kiện chính sách vẫn là regression. Critical failure phải có hard veto riêng.

Khi so sánh efficiency, cần giữ nguyên:
- dataset revision và case IDs;
- metric eligibility;
- judge model/prompt/rubric;
- thresholds và severity policy;
- cách chọn attempt/retry;
- context mode (frozen hay live retrieval).

Nếu đổi evaluator cùng lúc với generator, thay đổi pass rate có thể đến từ judge chứ không phải chất lượng answer.

## 5. Latency: đo đúng ranh giới request

**End-to-end latency** là thời gian từ điểm bắt đầu request đến điểm response được coi là hoàn tất theo trải nghiệm người dùng. Phải định nghĩa rõ điểm bắt đầu/kết thúc.

Với streaming:
- time-to-first-token (TTFT): từ request start đến token đầu tiên;
- time-to-last-token: từ request start đến token cuối;
- inter-token latency: khoảng cách giữa các token/chunks;
- total response duration: thời gian hoàn tất stream.

Một response có TTFT thấp nhưng stream rất chậm vẫn có thể tạo trải nghiệm kém. Với UI không stream, TTFT không phải metric chính.

### Latency theo stage

~~~text
HTTP request
  ├── prompt construction / history
  ├── retrieval
  │     ├── embedding
  │     ├── vector search
  │     └── reranking
  ├── context assembly
  ├── generator call
  ├── tool loop (0..N calls)
  ├── post-processing
  └── response serialization
~~~

Không cộng span cha và span con hai lần. Parent duration đã bao gồm child spans nếu chúng chạy tuần tự trong parent. Nếu tool calls chạy song song, tổng child duration có thể lớn hơn wall-clock duration.

### Latency phụ thuộc workload

Cần ghi:
- request mix và độ dài prompt;
- output token budget;
- số retrieved chunks và context size;
- tool call count;
- concurrency và arrival rate;
- cache state;
- warmup/cold start;
- timeout/retry policy;
- provider/model revision và region nếu có.

So sánh hai model trên prompt ngắn, concurrency thấp không chứng minh hiệu năng production với prompt dài và tool loop.

## 6. Vì sao p95 quan trọng hơn chỉ nhìn average?

Giả sử 100 requests:
- 95 requests hoàn tất trong 0,8–1,2 giây;
- 5 requests mất 8–12 giây.

Mean có thể vẫn trông chấp nhận được, nhưng 5% người dùng phải chờ rất lâu. p95/p99 giúp quan sát tail latency.

| Thống kê | Ý nghĩa |
|---|---|
| Mean | Tổng latency / số request; nhạy với outliers |
| Median / p50 | 50% requests hoàn tất không chậm hơn mức này |
| p90 | 90% requests hoàn tất không chậm hơn mức này |
| p95 | 95% requests hoàn tất không chậm hơn mức này |
| p99 | Tail sâu; cần sample lớn hơn để ổn định |
| Max | Request chậm nhất; nhạy với một outlier |

Percentile từ sample nhỏ rất bất ổn. Báo số lượng mẫu cùng percentile và không kết luận từ p99 của 20 requests.

### Histogram và aggregation

Histogram buckets cho phép tổng hợp latency qua nhiều instances. Summary quantiles thường được tính tại process và không thể cộng/gộp quantile giữa instances theo cách đơn giản. Chọn histogram buckets quanh SLO, ví dụ 250 ms, 500 ms, 1 s, 2 s, 4 s, 8 s.

Với evaluation report, lưu raw request duration hoặc histogram snapshots để có thể tính lại percentiles. Không chỉ lưu mỗi p95 nếu cần điều tra tail.

## 7. Cost: tính đủ các thành phần trong boundary

Cost của một request AI có thể gồm:

1. Generator input tokens.
2. Generator output tokens.
3. Cached input tokens nếu provider tính giá khác.
4. Reasoning tokens nếu được báo và tính phí riêng.
5. Judge/evaluator model calls.
6. Embedding calls.
7. Reranker/provider fees nếu tính theo request.
8. Tool/API fees.
9. Infrastructure cost nếu scope yêu cầu phân bổ.

Một công thức minh họa cho model call:

\[
C_{\mathrm{call}}=
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}.
\]

Nếu cached/reasoning tokens có rate riêng, tách chúng thành các term theo rate card thực tế. Không cộng total_tokens cùng input/output tokens vì sẽ double-count.

### Cost theo pipeline

\[
C_{\mathrm{case}}=
\sum_{\mathrm{generator\ calls}} C
+\sum_{\mathrm{judge\ calls}} C
+\sum_{\mathrm{embedding\ calls}} C
+\sum_{\mathrm{tools}} C
+C_{\mathrm{other}}.
\]

Nếu một case retry ba lần, cost của cả ba attempts vẫn phát sinh. Khi báo cost thực tế, không chỉ lấy attempt cuối cùng.

### Actual spend và normalized cost

- **Actual spend:** dùng rate card tại thời điểm chạy, phản ánh hóa đơn thực tế.
- **Normalized cost:** tính lại token/usage trên cùng một rate card để so sánh mức tiêu thụ giữa các phiên bản.

Nếu provider đổi giá giữa A và B, normalized cost giúp tách thay đổi do usage khỏi thay đổi do price. Report nên lưu rate-card revision và currency.

## 8. Cost per eligible, completed và successful case

Giả sử một batch có:
- tổng chi phí in-scope: 3,30 USD;
- 100 eligible cases;
- 96 completed cases;
- 94 successful cases.

Khi đó:

\[
C_{\mathrm{eligible}}=3,30/100=0,033\ \mathrm{USD}.
\]

\[
C_{\mathrm{completed}}=3,30/96\approx0,0344\ \mathrm{USD}.
\]

\[
C_{\mathrm{successful}}=3,30/94\approx0,0351\ \mathrm{USD}.
\]

Ba metric trả lời các câu hỏi khác nhau:
- Cost per eligible: chi phí cần để xử lý workload đã giao.
- Cost per completed: chi phí trên các execution hoàn tất.
- Cost per successful: chi phí để tạo ra một kết quả đạt yêu cầu.

Nếu candidate bỏ qua case khó, cost per completed có thể trông tốt hơn dù quality/coverage tệ hơn. Vì vậy, cost luôn phải đọc cùng quality và coverage.

**Không dùng cost per successful làm metric duy nhất.** Khi successful count bằng 0, metric không xác định; khi successful count rất thấp, tỷ lệ này biến động mạnh. Luôn báo total spend, eligible count, coverage và success count.

## 9. Pareto frontier: chất lượng, latency và cost

Một phương án A **dominates** B nếu A:
- quality không thấp hơn B;
- latency không cao hơn B;
- cost không cao hơn B;
- và ít nhất một trong ba trục tốt hơn nghiêm ngặt.

Phương án bị dominated thường không cần chọn nếu các điều kiện khác tương đương.

### Ví dụ ba phương án

| Variant | Quality pass rate | p95 latency | Cost / eligible case |
|---|---:|---:|---:|
| A | 92,0% | 1,2 s | $0,018 |
| B | 94,0% | 2,4 s | $0,033 |
| C | 91,5% | 0,9 s | $0,014 |
| D | 90,0% | 1,5 s | $0,020 |

- D bị A **dominate**: A quality cao hơn, nhanh hơn và rẻ hơn.
- A, B và C có thể nằm trên Pareto frontier: B chất lượng cao nhất nhưng chậm/đắt; C nhanh/rẻ nhất nhưng quality thấp hơn.
- Không có một phương án tốt nhất nếu chưa biết SLO, budget và mức quality tối thiểu.

### Minh họa mặt phẳng cost-latency

~~~text
Cost
 ^
 |                         B (quality 94%)
 |                    *
 |
 |          A *
 |
 |     C *
 +--------------------------------> p95 latency
       0.9s  1.2s          2.4s

C rẻ/nhanh nhất; B có quality cao nhất.
A là điểm cân bằng ở giữa.
~~~

Đây chỉ là hình minh họa hai trục cost-latency; quality là nhãn thứ ba. Trong report thực tế nên dùng scatter plot hoặc bảng có quality labels và uncertainty.

## 10. Không tạo một efficiency score tùy tiện

Một công thức như:

\[
Score=0,5\times Quality-0,3\times Latency-0,2\times Cost
\]

không có ý nghĩa nếu:
- các đại lượng khác đơn vị;
- weights chưa được domain owner phê duyệt;
- scale/normalization thay đổi theo dataset;
- critical failures có thể bị bù bởi cost thấp;
- weights được chọn sau khi nhìn kết quả.

Nếu nghiệp vụ thực sự cần một utility score, phải:
1. chuẩn hóa các biến theo định nghĩa công khai;
2. chọn weights trước;
3. giải thích utility/penalty theo business value;
4. đặt hard constraints cho safety, minimum quality, SLO và budget;
5. chạy sensitivity analysis khi weights thay đổi.

Thông thường, dễ kiểm tra hơn nếu dùng **quality floor + latency SLO + cost budget + critical veto**, rồi so Pareto frontier giữa những phương án vượt qua gate.

## 11. Ví dụ quyết định với quality floor, SLO và budget

Giả sử policy đã được phê duyệt:

- quality pass rate tối thiểu: 90%;
- p95 latency tối đa: 2,0 giây;
- cost per eligible case tối đa: $0,025;
- evaluation coverage tối thiểu: 98%;
- critical failures: 0.

Dùng bảng ở mục 9:

| Variant | Quality gate | Latency gate | Cost gate | Quyết định sơ bộ |
|---|---|---|---|---|
| A | Pass | Pass | Pass | Eligible |
| B | Pass | **Fail** | **Fail** | Reject theo operational budget |
| C | Pass | Pass | Pass | Eligible |
| D | Pass | Pass | **Fail** | Reject theo cost budget |

A và C đều vượt gate. C rẻ hơn và nhanh hơn, nhưng quality thấp hơn A 0,5 pp. C có thể được chọn nếu confidence interval/non-inferiority policy cho phép và quality slices/critical guardrails đều đạt.

B có quality cao hơn 2 pp nhưng vượt cả latency và cost budget. Không tự động promote chỉ vì quality tăng. Nếu business owner muốn chấp nhận trade-off đó, phải thay đổi SLO/budget **trước một quyết định release mới**, ghi lý do và phạm vi rollout.

## 12. Phân biệt quality improvement với operational degradation

Một candidate có thể rơi vào các tình huống:

| Quality | Latency/cost | Diễn giải |
|---|---|---|
| Tăng | Ổn định | Cải thiện rõ nếu coverage/guardrails giữ nguyên |
| Tăng | Xấu đi | Trade-off; kiểm tra SLO/budget và giá trị của quality gain |
| Ổn định | Tốt hơn | Efficiency improvement; kiểm tra non-inferiority quality |
| Giảm | Tốt hơn | Không gọi là cải thiện tổng thể; cân nhắc nếu regression nằm trong margin được phê duyệt |
| Giảm | Xấu đi | Regression toàn diện |
| Không rõ do CI rộng | Bất kỳ | INCONCLUSIVE; cần thêm dữ liệu hoặc điều tra |
| Không có verdict/usage | Có vẻ tốt | Measurement BLOCKED nếu completeness không đạt |

Quality improvement cần evidence từ cùng rubric, same case set và uncertainty analysis. Latency/cost improvement cần workload và boundary giống nhau. Không suy ra nguyên nhân chỉ từ hai số tổng hợp.

## 13. Thiết kế A/B công bằng

Một thiết kế có thể dùng các run blocks ghép cặp:

| Block | Thứ tự | Baseline | Candidate |
|---|---|---|---|
| 01 | A → B | Run A01 | Run B01 |
| 02 | B → A | Run A02 | Run B02 |
| 03 | Randomized | Run A03 | Run B03 |
| 04 | B → A | Run A04 | Run B04 |
| 05 | A → B | Run A05 | Run B05 |

Trong mỗi block:
- cùng dataset revision và case IDs;
- cùng case order hoặc randomization policy;
- cùng concurrency, arrival rate và timeout;
- cùng warmup/cache policy;
- cùng judge/rubric/thresholds;
- interleave A/B để giảm time/provider confounding;
- lưu attempt, retries và provider metadata.

### Quality và performance có thể cần hai workload modes

1. **Quality evaluation mode:** concurrency thấp/kiểm soát để giảm load-induced errors; có thể dùng frozen context nếu mục tiêu so generator.
2. **Performance load mode:** concurrency và arrival rate đại diện production, đo latency/throughput/error/cost.

Không dùng quality run concurrency 1 để kết luận p95 production. Không dùng stress test quá tải để kết luận chất lượng model nếu errors chỉ do load ngoài SLO.

## 14. Tách serving cost khỏi evaluation cost

Trong CI, một candidate có thể tốn thêm judge calls để đánh giá. Nhưng production không nhất thiết chạy judge trên mọi request.

Báo hai boundary riêng:

| Cost scope | Thành phần |
|---|---|
| Serving cost | Generator, retrieval/embedding nếu online, tool/API fees, infrastructure allocation |
| Evaluation cost | Judge LLM, human review, offline embeddings, dataset preparation |
| Experiment cost | Serving + evaluation + load generation và repeated attempts |

Khi so sánh business economics, dùng serving cost per eligible request. Khi lập ngân sách thí nghiệm, dùng experiment cost. Không cộng evaluation judge cost vào production serving cost nếu judge chỉ chạy offline.

Nếu production có online verifier/judge/advisor, thành phần đó phải nằm trong serving boundary.

## 15. Phân tích cost drivers bằng token và call counts

Một case tốn tiền hơn có thể do:
- prompt dài hơn;
- retrieval trả nhiều chunks;
- output token nhiều hơn;
- tool loop gọi nhiều lần;
- retry tăng;
- judge chấm nhiều lần;
- embedding lại query/document;
- cache hit giảm.

| Metric | Cách diễn giải |
|---|---|
| Input tokens/case | Prompt, history và context size |
| Output tokens/case | Độ dài answer |
| Cached input tokens | Phần input được cache theo provider |
| Generator calls/case | Số lần gọi model chính |
| Tool calls/case | Số lần thực thi tool |
| Judge calls/case | Số lần đánh giá |
| Retry rate | Chi phí do lần chạy lại |
| Cost per eligible | Tác động lên workload tổng |
| Cost per successful | Hiệu quả tạo kết quả đạt yêu cầu |

Đừng mặc định output dài hơn là chất lượng cao hơn. Cần xem factuality, relevance và user value cùng với token usage.

## 16. Phân tích latency drivers bằng traces

Trace nên giúp trả lời:
- request chờ ở retrieval, model, tool hay queue?
- tool calls chạy tuần tự hay song song?
- model time tăng do prompt/context hay provider?
- retry nào làm tail latency tăng?
- judge latency có nằm trong user-facing request không?
- cache hit/miss ảnh hưởng ra sao?

Một trace tree minh họa:

~~~text
POST /assistant
  ├── prompt.prepare             8 ms
  ├── retrieval                  90 ms
  │     ├── embedding            25 ms
  │     └── vector.search        65 ms
  ├── chat.client              850 ms
  │     └── chat.model          820 ms
  ├── tool.execution           300 ms
  ├── chat.client              500 ms
  │     └── chat.model          480 ms
  └── response.serialize         5 ms
  Total wall-clock             ~1.75 s
~~~

Các số là ví dụ. Nếu tool execution và model call chạy song song, total wall-clock không bằng tổng số học tất cả spans. Hãy dùng parent span và timeline để đọc concurrency.

## 17. Spring AI Observability và Micrometer

Spring AI tích hợp Observation/Tracing để quan sát các thành phần như ChatClient, ChatModel, EmbeddingModel, VectorStore và tool execution tùy instrumentation được bật.

Các observation/metric convention có thể gặp tùy phiên bản và exporter:
- spring.ai.chat.client;
- spring.ai.advisor;
- gen_ai.client.operation;
- gen_ai.client.token.usage;
- db.vector.client.operation;
- spring.ai.tool.

Tên metric thực tế có thể được exporter chuẩn hóa, thêm suffix hoặc thay đổi theo phiên bản. Hãy kiểm tra MeterRegistry/OTel output của ứng dụng thay vì hardcode tên chưa xác minh.

### Custom low-cardinality metrics

Có thể thêm custom timers/counters:
- app.ai.request.duration;
- app.ai.evaluation.duration;
- app.ai.evaluation.outcome;
- app.ai.cost.usd;
- app.ai.retry.count.

Tags nên có tập giá trị hữu hạn:
- variant: baseline/candidate;
- role: generator/judge/retriever/tool;
- scenario: rag/tool/no_context;
- business_group: policy/orders/support;
- outcome: pass/fail/error.

Không dùng case_id, run_id, raw prompt, user ID hoặc document ID làm Prometheus labels vì cardinality tăng nhanh và có thể lộ dữ liệu. Đặt identifiers trong report store hoặc trace attributes theo retention/access policy.

## 18. Cache, batching và concurrency: cải thiện efficiency có thể đổi semantics

### Cache

Cache có thể giảm latency và cost, nhưng cần kiểm tra:
- cache key có chứa tenant/security scope không;
- stale data có thể làm RAG trả policy cũ không;
- prompt/model/index revision có invalidate cache không;
- hit rate khác nhau giữa A/B có làm comparison lệch không;
- cache warm/cold được đo riêng chưa.

Một cache hit nhanh nhưng trả evidence cũ là operational efficiency tăng, quality giảm.

### Batching

Batching embedding có thể giảm overhead/cost per item nhưng tăng latency chờ gom batch. Đo throughput và p95 cùng nhau.

### Concurrency

Tăng concurrency có thể tăng throughput đến một ngưỡng, sau đó queue, rate limit và tail latency tăng. Cần load test với arrival rate đại diện, không chỉ tăng số thread.

### Parallel tool calls

Parallel execution giảm wall-clock nếu các tools độc lập. Nhưng phải kiểm tra ordering, shared state, rate limits và side effects. Không parallel hóa tool mutation nếu workflow yêu cầu thứ tự.

## 19. Retries và timeout có thể làm số đo đẹp giả

Retry policy tác động đồng thời quality, latency, cost và reliability.

Ví dụ:
- attempt 1 timeout sau 3 giây;
- attempt 2 thành công sau 1 giây;
- user-facing latency có thể gần 4 giây;
- provider cost của cả hai calls vẫn phát sinh.

Nếu chỉ lưu attempt thành công, latency/cost bị đánh giá thấp. Nếu mỗi retry được tính như một case mới, denominator quality bị phóng đại.

Report cần:
- case ID ổn định;
- attempt ID riêng;
- tổng wall-clock request;
- total provider usage/cost của mọi attempts;
- retry reason;
- terminal outcome;
- policy chọn answer cuối.

Timeout là observation/censoring policy riêng. Không bỏ timeout khỏi latency report; nếu hệ thống ngừng chờ ở deadline, ghi duration đến timeout và timeout count.

## 20. Uncertainty: đừng kết luận từ một run

Một run có thể gặp provider load bất thường. Cần repeated run blocks và interval cho:
- quality pass rate/delta;
- p95 latency;
- cost per eligible case;
- error/timeout rates.

Với A/B paired theo case:
1. giữ case IDs và kết quả A/B thành cặp;
2. bootstrap case IDs để ước lượng uncertainty của quality delta;
3. nếu run blocks gây biến động theo thời gian, resample run blocks ở tầng riêng hoặc dùng hierarchical bootstrap;
4. báo số blocks, số cases, coverage và assumptions.

Với latency:
- bootstrap request/case durations hoặc run-level quantiles theo đúng sampling design;
- không coi hàng nghìn requests trong cùng một burst là độc lập nếu chúng cùng chịu một provider incident;
- báo distribution/histogram, sample count và timeout rate.

Với cost:
- cost per case thường có phân phối lệch phải; báo median, p90/p95 và mean/total spend;
- nếu muốn so cost delta, bootstrap paired case costs trên cùng case IDs;
- normalized cost phải dùng cùng rate card revision.

Một CI hẹp không sửa được workload không đại diện hoặc telemetry thiếu.

## 21. Java 21: tổng hợp quality, latency và cost

Ví dụ dưới đây nhận **một dòng đã tổng hợp cho mỗi eligible case/arm**. Runner chịu trách nhiệm:
- chọn attempt theo retry policy đã đăng ký;
- cộng toàn bộ cost của các attempts trong request boundary;
- tính end-to-end latency từ request start đến terminal state;
- xác thực case IDs và metric eligibility.

### File: EfficiencySummary.java

~~~java
package com.example.aiquality.efficiency;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.OptionalDouble;
import java.util.Set;

public final class EfficiencySummary {
    private EfficiencySummary() {}

    public enum Outcome {
        PASS, FAIL, GENERATION_ERROR, EVALUATION_ERROR, SKIPPED
    }

    public record CaseMeasurement(
            String caseId,
            Outcome outcome,
            Long endToEndLatencyMs,
            Double totalCostUsd,
            boolean criticalFailure) {

        public CaseMeasurement {
            if (caseId == null || caseId.isBlank()
                    || outcome == null
                    || (endToEndLatencyMs != null && endToEndLatencyMs < 0)
                    || (totalCostUsd != null
                        && (!Double.isFinite(totalCostUsd)
                            || totalCostUsd < 0.0))
                    || (criticalFailure && outcome != Outcome.FAIL)) {
                throw new IllegalArgumentException(
                    "CaseMeasurement không hợp lệ");
            }
        }
    }

    public record Summary(
            int eligible,
            int observed,
            int evaluated,
            int passed,
            int failed,
            int generationErrors,
            int evaluationErrors,
            int skipped,
            int missing,
            int criticalCases,
            int costKnownCases,
            OptionalDouble qualityPassRate,
            OptionalDouble evaluationCoverage,
            OptionalDouble latencyCoverage,
            OptionalDouble p95LatencyMs,
            OptionalDouble totalCostUsd,
            OptionalDouble costCompleteness,
            OptionalDouble costPerEligibleUsd,
            OptionalDouble costPerCompletedUsd,
            OptionalDouble costPerSuccessfulUsd) {}

    public static Summary summarize(
            Set<String> expectedCaseIds,
            List<CaseMeasurement> measurements) {

        if (expectedCaseIds == null || expectedCaseIds.isEmpty()
                || expectedCaseIds.contains(null)
                || measurements == null) {
            throw new IllegalArgumentException(
                "Expected cases/measurements không hợp lệ");
        }

        Set<String> expected = Set.copyOf(expectedCaseIds);
        Set<String> seen = new HashSet<>();
        List<Long> latencies = new ArrayList<>();

        int pass = 0, fail = 0, genError = 0, evalError = 0, skipped = 0;
        int critical = 0, costKnown = 0;
        double totalCost = 0.0;

        for (CaseMeasurement row : measurements) {
            if (row == null || !expected.contains(row.caseId())
                    || !seen.add(row.caseId())) {
                throw new IllegalArgumentException(
                    "Case không thuộc expected set hoặc bị duplicate");
            }

            if (row.endToEndLatencyMs() != null) {
                latencies.add(row.endToEndLatencyMs());
            }
            switch (row.outcome()) {
                case PASS -> pass++;
                case FAIL -> fail++;
                case GENERATION_ERROR -> genError++;
                case EVALUATION_ERROR -> evalError++;
                case SKIPPED -> skipped++;
            }

            if (row.criticalFailure()) critical++;

            if (row.totalCostUsd() != null) {
                totalCost += row.totalCostUsd();
                costKnown++;
            }
        }

        int eligible = expected.size();
        int observed = measurements.size();
        int evaluated = pass + fail;
        int completed = pass + fail + genError + evalError;
        int missing = eligible - observed;

        OptionalDouble quality = ratio(pass, evaluated);
        OptionalDouble coverage = ratio(evaluated, eligible);
        OptionalDouble latencyCoverage = ratio(latencies.size(), eligible);
        OptionalDouble completeness = ratio(costKnown, eligible);

        OptionalDouble p95 = latencies.isEmpty()
                ? OptionalDouble.empty()
                : OptionalDouble.of(nearestRank(latencies, 0.95));

        // Chỉ công bố total và unit costs khi đủ cost cho mọi eligible case.
        boolean completeCost = costKnown == eligible && missing == 0;
        OptionalDouble total = completeCost
                ? OptionalDouble.of(totalCost)
                : OptionalDouble.empty();
        OptionalDouble perEligible = completeCost
                ? ratio(totalCost, eligible)
                : OptionalDouble.empty();
        OptionalDouble perCompleted = completeCost
                ? ratio(totalCost, completed)
                : OptionalDouble.empty();
        OptionalDouble perSuccessful = completeCost
                ? ratio(totalCost, pass)
                : OptionalDouble.empty();

        return new Summary(
            eligible, observed, evaluated, pass, fail,
            genError, evalError, skipped, missing, critical, costKnown,
            quality, coverage, latencyCoverage, p95,
            total, completeness, perEligible, perCompleted, perSuccessful);
    }

    private static long nearestRank(List<Long> values, double percentile) {
        List<Long> sorted = values.stream().sorted().toList();
        int index = (int) Math.ceil(percentile * sorted.size()) - 1;
        return sorted.get(Math.max(0, Math.min(index, sorted.size() - 1)));
    }

    private static OptionalDouble ratio(double numerator, double denominator) {
        return denominator == 0.0
                ? OptionalDouble.empty()
                : OptionalDouble.of(numerator / denominator);
    }
}
~~~

### Cách đọc Summary

- **qualityPassRate:** PASS / (PASS + FAIL), không gộp execution errors vào FAIL.
- **evaluationCoverage:** verdict hợp lệ / eligible.
- **latencyCoverage:** số case có duration / eligible; duration bị thiếu được giữ là missing, không thay bằng 0.
- **p95LatencyMs:** nearest-rank p95 trên các case có measurement; đọc cùng latency coverage.
- **costCompleteness:** case có cost / eligible.
- **totalCostUsd** và unit costs chỉ có giá trị khi cost đã biết cho mọi eligible case và không thiếu row.
- **costPerCompletedUsd:** tổng cost chia số execution có terminal outcome (PASS, FAIL, GENERATION_ERROR hoặc EVALUATION_ERROR); SKIPPED và missing không nằm trong denominator.
- **costPerSuccessfulUsd** không xác định khi không có PASS.
- **criticalCases** đếm unique case có critical failure, không phải tổng số incidents.

Đây là ví dụ tổng hợp cho một lần chạy/arm. Trong production, hãy giữ raw call-level usage và trace references để có thể kiểm tra cách tính total cost.

## 22. JUnit 5: kiểm tra quality/cost/latency riêng biệt

### File: EfficiencySummaryTest.java

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import com.example.aiquality.efficiency.EfficiencySummary;
import com.example.aiquality.efficiency.EfficiencySummary.*;

class EfficiencySummaryTest {

    @Test
    void reportsQualityLatencyAndCostAsSeparateDimensions() {
        var rows = List.of(
            new CaseMeasurement("c1", Outcome.PASS, 800, 0.02, false),
            new CaseMeasurement("c2", Outcome.PASS, 900, 0.03, false),
            new CaseMeasurement("c3", Outcome.FAIL, 1200, 0.04, false),
            new CaseMeasurement("c4", Outcome.PASS, 2400, 0.05, false));

        var report = EfficiencySummary.summarize(
            Set.of("c1", "c2", "c3", "c4"), rows);

        assertEquals(0.75,
                report.qualityPassRate().orElseThrow(), 0.000001);
        assertEquals(1.0,
                report.evaluationCoverage().orElseThrow(), 0.000001);
        assertEquals(2400.0,
                report.p95LatencyMs().orElseThrow(), 0.000001);
        assertEquals(0.14,
                report.totalCostUsd().orElseThrow(), 0.000001);
        assertEquals(0.035,
                report.costPerEligibleUsd().orElseThrow(), 0.000001);
        assertEquals(0.14 / 3.0,
                report.costPerSuccessfulUsd().orElseThrow(), 0.000001);
    }

    @Test
    void missingCasePreventsCompleteCostTotal() {
        var report = EfficiencySummary.summarize(
            Set.of("c1", "c2"),
            List.of(new CaseMeasurement(
                "c1", Outcome.PASS, 800, 0.02, false)));

        assertEquals(1, report.missing());
        assertEquals(0.5,
                report.latencyCoverage().orElseThrow(), 0.000001);
        assertTrue(report.totalCostUsd().isEmpty());
        assertTrue(report.costPerEligibleUsd().isEmpty());
    }

    @Test
    void missingLatencyReducesLatencyCoverageInsteadOfBecomingZero() {
        var report = EfficiencySummary.summarize(
            Set.of("c1", "c2"),
            List.of(
                new CaseMeasurement("c1", Outcome.PASS, 800L, 0.02, false),
                new CaseMeasurement("c2", Outcome.FAIL, null, 0.03, false)));

        assertEquals(0.5,
                report.latencyCoverage().orElseThrow(), 0.000001);
        assertEquals(800.0,
                report.p95LatencyMs().orElseThrow(), 0.000001);
    }

    @Test
    void noVerdictDoesNotBecomeQualityFail() {
        var report = EfficiencySummary.summarize(
            Set.of("c1", "c2"),
            List.of(
                new CaseMeasurement("c1", Outcome.PASS, 800, 0.02, false),
                new CaseMeasurement(
                    "c2", Outcome.GENERATION_ERROR, 2000, 0.03, false)));

        assertEquals(1, report.passed());
        assertEquals(0, report.failed());
        assertEquals(1, report.generationErrors());
        assertEquals(1.0,
                report.qualityPassRate().orElseThrow(), 0.000001);
        assertEquals(0.5,
                report.evaluationCoverage().orElseThrow(), 0.000001);
        assertEquals(0.025,
                report.costPerCompletedUsd().orElseThrow(), 0.000001);
    }

    @Test
    void criticalFailureIsCountedSeparately() {
        var report = EfficiencySummary.summarize(
            Set.of("c1", "c2"),
            List.of(
                new CaseMeasurement("c1", Outcome.PASS, 800, 0.02, false),
                new CaseMeasurement("c2", Outcome.FAIL, 900, 0.03, true)));

        assertEquals(1, report.criticalCases());
        assertEquals(0.5,
                report.qualityPassRate().orElseThrow(), 0.000001);
    }

    @Test
    void rejectsDuplicateOrUnexpectedCaseIds() {
        assertThrows(IllegalArgumentException.class, () ->
            EfficiencySummary.summarize(
                Set.of("c1"),
                List.of(
                    new CaseMeasurement("c1", Outcome.PASS, 800, 0.02, false),
                    new CaseMeasurement("c1", Outcome.FAIL, 900, 0.03, false))));
    }
}
~~~

Đây là **code hướng dẫn**, chưa được compile hoặc chạy trong phạm vi viết bài. Khi đưa vào project, đặt đúng package, thêm JUnit 5 và bổ sung test cho zero-cost, no-successful-case, missing usage và timeout policy.

## 23. Release gate cho quality, latency và cost

Một policy minh họa:

~~~yaml
efficiency_gate:
  revision: "quality-latency-cost-v2"
  measurement:
    minimum_evaluation_coverage: 0.98
    minimum_latency_coverage: 0.99
    minimum_cost_completeness: 0.99
  quality:
    minimum_pass_rate: 0.90
    maximum_regression_vs_baseline_pp: 1.0
    critical_failure_max_unique_cases: 0
  performance:
    maximum_p95_latency_ms: 2000
    maximum_timeout_rate: 0.01
  cost:
    maximum_cost_per_eligible_case_usd: 0.025
    rate_card_revision: "provider-price-2026-11"
  decision:
    critical_failure_veto: true
    insufficient_measurement: "BLOCKED"
    insufficient_sample: "INCONCLUSIVE"
~~~

Ngưỡng trên là ví dụ; không phải default của Spring AI. Domain owner phải chọn quality floor, regression tolerance, SLO và budget theo risk/traffic. Đăng ký gate trước khi xem kết quả.

### Thứ tự quyết định

1. Critical failure đã xác minh và có veto → **REJECT**.
2. Dataset/manifest/coverage/usage completeness không đạt → **BLOCKED**.
3. Sample hoặc uncertainty chưa đủ để kết luận → **INCONCLUSIVE**.
4. Quality floor hoặc maximum regression bị vi phạm → **REJECT**.
5. p95/timeout/cost vượt budget → **REJECT** hoặc yêu cầu phê duyệt trade-off theo quy trình đã định.
6. Tất cả điều kiện đạt → **PROMOTE**.

Không cho cost thấp bù critical failure. Không cho latency tốt bù fact-check regression vượt ngưỡng. Nếu business muốn thay đổi trade-off, cập nhật policy và chạy lại phép so sánh theo kế hoạch mới.

## 24. Report A/B: trình bày cả ba trục

Ví dụ report:

| Metric | A — baseline | B — candidate | Delta | Gate |
|---|---:|---:|---:|---|
| Quality pass rate | 92,0% | 94,0% | +2,0 pp | Floor 90% |
| Evaluation coverage | 100% | 100% | 0 pp | Min 98% |
| Critical cases | 0 | 0 | 0 | Must be 0 |
| p50 latency | 0,75 s | 1,30 s | +73% | Descriptive |
| p95 latency | 1,20 s | 2,40 s | +100% | Max 2,00 s |
| Cost / eligible case | $0,018 | $0,033 | +83% | Max $0,025 |
| Cost / successful case | $0,0196 | $0,0351 | +79% | Descriptive |

B cải thiện quality nhưng vi phạm p95 và cost gates. Kết luận phù hợp là **REJECT theo policy hiện tại**, hoặc yêu cầu business owner phê duyệt một policy mới nếu quality gain có giá trị cao hơn chi phí/latency.

### Kết luận phải có uncertainty

Báo cáo thực tế cần thêm:
- case count và run blocks;
- quality CI/paired delta CI;
- p95 sample count hoặc bootstrap interval;
- timeout/error rates;
- cost completeness;
- normalized rate card;
- per-slice quality/latency/cost;
- critical case IDs và review outcome.

Không kết luận quality tăng 2 pp có ý nghĩa nếu CI quá rộng hoặc judge chưa được calibration.

## 25. Checklist trước khi kết luận trade-off

- [ ] Quality, latency, throughput, reliability và cost được báo riêng.
- [ ] Mỗi metric có unit of analysis, boundary và denominator rõ.
- [ ] Quality dùng cùng dataset, eligibility, judge và rubric.
- [ ] Critical failure có hard veto.
- [ ] Latency có p50/p95/p99, sample count và timeout policy.
- [ ] Streaming có TTFT/time-to-last-token khi phù hợp.
- [ ] Latency stage không cộng trùng parent/child spans.
- [ ] Workload, concurrency, cache, warmup và arrival rate được kiểm soát.
- [ ] Cost gồm mọi calls/retries trong serving boundary.
- [ ] Judge/offline evaluation cost được tách khỏi serving cost.
- [ ] Actual spend và normalized cost có rate-card revision.
- [ ] Cost per eligible/completed/successful được phân biệt.
- [ ] Missing latency/usage không bị gán bằng zero.
- [ ] A/B được interleave hoặc paired theo run blocks khi phù hợp.
- [ ] Repeated runs đủ để quan sát variation.
- [ ] Quality delta và performance/cost delta có uncertainty.
- [ ] Pareto-dominated options được nhận diện.
- [ ] Quality floor, SLO và budget được đăng ký trước.
- [ ] Per-slice guardrails không bị overall che.
- [ ] Quyết định PROMOTE/REJECT/BLOCKED/INCONCLUSIVE có lý do.

## Tài liệu tham khảo

1. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): Observation, tracing và token usage trong các thành phần Spring AI.
2. [Spring AI — Evaluation](https://docs.spring.io/spring-ai/reference/api/testing.html): evaluator và evaluation request.
3. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics, timers và histograms.
4. [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): histogram buckets, percentile histograms và quantiles.
5. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile và aggregation của histogram.
6. [OpenTelemetry — Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): conventions cho model calls và token usage.
7. [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): SLO, latency và reliability.
8. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong logs và telemetry.

> **Ghi nhớ:** Chất lượng, độ trễ và chi phí là ba trục riêng. Hãy giữ quality floor và critical veto, đo latency theo trải nghiệm thực, tính đủ cost của mọi calls/retries, rồi so các phương án trên cùng workload và cùng boundary. Một candidate chỉ thực sự phù hợp khi trade-off của nó đáp ứng yêu cầu nghiệp vụ đã được đăng ký trước.
