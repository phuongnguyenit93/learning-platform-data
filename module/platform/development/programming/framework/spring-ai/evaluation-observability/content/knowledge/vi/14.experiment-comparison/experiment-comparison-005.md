# Cỡ mẫu, khoảng bất định và giới hạn của kết luận

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; kết hợp metrics, traces, chi phí và độ trễ để nhận diện suy giảm giữa các phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Các con số trong bài là ví dụ tổng hợp để học phương pháp, không phải benchmark của model/provider cụ thể.

## 1. Vì sao cỡ mẫu quyết định độ tin cậy của kết luận?

Một lần chạy evaluation báo candidate B đạt **92% PASS**, baseline A đạt **90%**. Nhìn qua, B có vẻ tốt hơn 2 điểm phần trăm. Nhưng nếu mỗi arm chỉ có 25 case, chênh lệch này có thể chỉ là dao động của mẫu. Nếu có 2.500 case đại diện và phép đo được kiểm soát tốt, cùng một chênh lệch có thể cung cấp bằng chứng mạnh hơn nhiều.

Một báo cáo evaluation cần trả lời:

- **Đang muốn suy luận cho tập nào?** Chỉ regression suite hiện tại, hay toàn bộ câu hỏi người dùng có thể đặt?
- **Có bao nhiêu đơn vị quan sát độc lập?** Bao nhiêu case khác nhau, bao nhiêu tài liệu/chủ đề, bao nhiêu run blocks?
- **Kết quả bất định bao nhiêu?** Confidence interval, variation qua runs và coverage ra sao?
- **Khác biệt có ý nghĩa thực tế không?** Hai điểm phần trăm có đủ lớn để thay đổi quyết định nghiệp vụ?
- **Có những sai lệch nào khoảng tin cậy không phản ánh?** Dataset không đại diện, judge bias, label errors, corpus drift hoặc thiếu verdict?

**Cỡ mẫu lớn không tự làm phép đo đúng.** Một triệu câu hỏi trùng lặp, cùng một tài liệu hoặc cùng một nguồn lỗi có thể tạo ra rất nhiều dòng dữ liệu nhưng rất ít thông tin độc lập.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Xác định population, sampling frame và đơn vị quan sát trước khi chọn cỡ mẫu.
2. Phân biệt số case, số attempts, số run blocks và số verdict hợp lệ.
3. Ước lượng cỡ mẫu cho một tỷ lệ PASS theo độ chính xác mong muốn.
4. Đọc Wilson interval và giới hạn của khoảng tin cậy khi có ít mẫu hoặc không có critical events.
5. Lập kế hoạch cỡ mẫu A/B cho tỷ lệ độc lập và cho paired comparison.
6. Điều chỉnh suy luận khi case được gom cụm theo tài liệu, domain hoặc người dùng.
7. Phân biệt sampling uncertainty, generator variance, judge variance và operational missingness.
8. Dùng bootstrap/paired analysis phù hợp với dữ liệu RAG và tool calling.
9. Kiểm soát multiple comparisons, optional stopping và lựa chọn kết quả sau khi xem dữ liệu.
10. Viết report nêu rõ phạm vi kết luận và những điều dữ liệu chưa chứng minh.

## 2. Xác định population trước khi tính cỡ mẫu

**Population** là tập tình huống mà kết luận muốn áp dụng. **Sampling frame** là nguồn thực tế có thể lấy mẫu. **Evaluation sample** là các case đã chọn và chạy.

Ví dụ với trợ lý RAG chính sách:

| Khái niệm | Ví dụ |
|---|---|
| Population | Các câu hỏi tiếng Việt về chính sách nội bộ mà trợ lý sẽ nhận trong giai đoạn triển khai |
| Sampling frame | Các nhóm chủ đề, loại tài liệu, câu hỏi tổng hợp và traffic sample đã được phép sử dụng |
| Unit of analysis | Một case ID đại diện một tình huống hỏi/đáp có ground truth |
| Cluster | Tài liệu chính sách, chủ đề, workflow hoặc nhóm nguồn chung |
| Evaluation sample | 300 case được chọn theo sampling plan |
| Metric | Fact-check pass rate, relevance, critical case rate, retrieval recall@k |

Nếu mục tiêu chỉ là kiểm tra **chính xác 120 case cố định trong regression suite**, hãy chạy cả 120 và báo kết quả mô tả trên suite đó. Không cần giả vờ 120 case là mẫu ngẫu nhiên của mọi câu hỏi người dùng.

Nếu muốn kết luận về **những tình huống tương lai**, phải giải thích 120 case được chọn như thế nào, chúng có đại diện cho domain, độ khó và traffic hay không, và phần nào chưa được bao phủ.

### Các đơn vị không được đánh đồng

| Đơn vị | Ý nghĩa | Có thể thay thế số case không? |
|---|---|---|
| Case ID duy nhất | Một tình huống đánh giá | Là đơn vị chính khi suy rộng qua các tình huống |
| Attempt | Một lần thực thi case, có thể là retry | Không; retry không tạo case mới |
| Run | Một lần chạy một arm trên dataset | Không; run giúp đo variation |
| Run block | Một block chứa A/B gần nhau về thời gian | Không; dùng để kiểm soát time/provider effects |
| Assessment | Một lần judge chấm một answer snapshot | Không; nhiều assessments trên cùng answer đo judge variance |
| Incident | Một lỗi được ghi nhận | Không; một case có thể chứa nhiều incidents |
| Document/topic cluster | Nhóm case có chung nguồn hoặc bối cảnh | Quan trọng vì các case trong cụm có thể tương quan |

**100 case × 5 runs không tự động thành 500 case độc lập.** Có thể có 500 verdicts, nhưng chỉ 100 tình huống khác nhau.

## 3. Bốn nguồn bất định trong evaluation

Nên tách ít nhất bốn nguồn:

1. **Sampling uncertainty:** nếu chọn một tập case khác từ cùng population, kết quả có thể khác.
2. **Generator/run variation:** cùng case/context, hosted model có thể tạo answer khác qua các lần gọi.
3. **Judge/measurement variation:** cùng answer/evidence, evaluator có thể đổi score hoặc verdict.
4. **Operational missingness:** timeout, 429, tool failure, skipped hoặc trace/usage bị thiếu làm mất một phần phép đo.

| Nguồn | Cách khảo sát |
|---|---|
| Sampling | Chọn thêm case độc lập, phân tầng đúng population |
| Generator | Lặp generation trên cùng input và lưu từng attempt |
| Judge | Re-score cùng answer/evidence snapshots nhiều lần hoặc đối chiếu human labels |
| Operational | Chạy nhiều run blocks, theo dõi error rate/coverage và provider metadata |

Khoảng tin cậy của pass rate chỉ mô tả một phần bất định dưới các giả định thống kê. Nó **không tự bao gồm** judge bias, dataset selection bias hoặc model alias drift.

## 4. Lấy mẫu thế nào để kết quả có ý nghĩa?

### Simple random sample

Mỗi case trong sampling frame có xác suất được chọn như nhau. Cách này dễ diễn giải nếu frame đầy đủ và các case thực sự tương đương về quyền được chọn.

### Stratified sample

Chia trước theo nhóm nghiệp vụ/độ khó/risk rồi lấy mẫu trong từng nhóm:

| Slice | Population/traffic share | Evaluation sample |
|---|---:|---:|
| Policy / Easy | 40% | 60 |
| Policy / Hard | 10% | 60 |
| Orders / Medium | 25% | 60 |
| Tech support / Hard | 5% | 60 |
| Các nhóm khác | 20% | 60 |

Ví dụ này **oversample nhóm khó và rủi ro** để có đủ case phân tích. Khi tính điểm đại diện traffic, phải dùng weights theo sampling probabilities/traffic share đã đăng ký trước; không dùng raw micro average trên mẫu cân bằng rồi gọi đó là traffic accuracy.

### Cluster sampling

Chọn tài liệu/chủ đề trước, sau đó lấy nhiều câu hỏi trong mỗi tài liệu. Cách này thuận tiện khi xây RAG benchmark nhưng các câu cùng tài liệu có thể tương quan. Phải tính đến cluster effect khi ước lượng uncertainty.

### Convenience sample

Lấy các câu hỏi dễ có sẵn, câu hỏi do nhóm phát triển tự nghĩ hoặc các case đã biết model trả đúng. Cách này hữu ích cho smoke tests, nhưng không đủ để kết luận chất lượng tổng quát.

**Không có một sample size nào sửa được sampling bias.** Tăng 10.000 câu hỏi từ cùng một nhóm dễ vẫn có thể bỏ sót workflow khó và rủi ro cao.

## 5. Cỡ mẫu cho một tỷ lệ PASS: mục tiêu độ chính xác

Khi muốn ước lượng một tỷ lệ \(p\) với sai số biên \(E\) tại confidence level đã chọn, một công thức planning gần đúng cho simple random sample là:

\[
n_0=\frac{z_{1-\alpha/2}^{\,2}\,p(1-p)}{E^2}.
\]

Trong đó:

- \(p\): tỷ lệ dự kiến từ pilot hoặc dữ liệu trước;
- \(E\): half-width mong muốn, ví dụ 0,03 tương ứng ±3 điểm phần trăm;
- \(z_{1-\alpha/2}\): quantile chuẩn, khoảng 1,96 cho confidence 95%;
- \(n_0\): cỡ mẫu dự kiến trước khi làm tròn lên.

Nếu chưa biết \(p\), chọn \(p=0,5\) cho planning bảo thủ vì \(p(1-p)\) lớn nhất tại 0,5.

### Ví dụ ước lượng

Với confidence 95%, \(z=1,96\):

| Tỷ lệ planning | Sai số mục tiêu | Cỡ mẫu gần đúng | Cỡ mẫu sau làm tròn |
|---:|---:|---:|---:|
| 90% | ±5 pp | 138,3 | **139** |
| 90% | ±3 pp | 384,2 | **385** |
| 50% (chưa biết p) | ±3 pp | 1.067,1 | **1.068** |
| 50% (chưa biết p) | ±5 pp | 384,2 | **385** |

Ví dụ: nếu pilot cho thấy fact-check pass rate khoảng 90% và nhóm muốn sai số xấp xỉ ±3 pp, cần khoảng 385 **case độc lập đủ điều kiện** theo giả định simple random sample. Nếu có clustering, nonresponse/missingness hoặc phân tầng, phải điều chỉnh thiết kế.

### Hiệu chỉnh khi population hữu hạn

Nếu mục tiêu chỉ là ước lượng tỷ lệ trên một population hữu hạn có \(N\) phần tử và lấy mẫu ngẫu nhiên **không hoàn lại**, có thể dùng finite population correction:

\[
n_{\mathrm{FPC}}=
\frac{n_0}{1+\frac{n_0-1}{N}}.
\]

Ví dụ \(n_0=385\) và toàn bộ population có \(N=500\), cỡ mẫu điều chỉnh xấp xỉ 218. Chỉ dùng hiệu chỉnh này khi sampling design thật sự là lấy mẫu không hoàn lại từ population hữu hạn đang quan tâm. Nếu muốn suy rộng tới các câu hỏi tương lai ngoài frame hiện tại, không được dùng FPC chỉ vì dataset benchmark có số lượng hữu hạn.

### Đây là cỡ mẫu cho precision, không phải power A/B

Công thức trên trả lời: **ước lượng một tỷ lệ với khoảng sai số mong muốn cần bao nhiêu mẫu?**

Nó không trả lời: **cần bao nhiêu mẫu để phát hiện candidate tăng 2 điểm phần trăm so với baseline?** Câu hỏi thứ hai cần effect size, alpha, power và thiết kế paired/unpaired.

## 6. Wilson interval cho tỷ lệ nhị thức

Với \(x\) PASS trong \(n\) verdict hợp lệ:

\[
\hat p=\frac{x}{n}.
\]

Wilson score interval thường ổn định hơn Wald interval \(\hat p \pm z\sqrt{\hat p(1-\hat p)/n}\), đặc biệt khi tỷ lệ gần 0/1 hoặc cỡ mẫu nhỏ.

Đặt:

\[
d=1+\frac{z^2}{n},
\qquad
c=\frac{\hat p+\frac{z^2}{2n}}{d},
\]

\[
h=\frac{z}{d}
\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}.
\]

Khoảng Wilson:

\[
[\max(0,c-h),\ \min(1,c+h)].
\]

### Ví dụ: cùng 90% nhưng cỡ mẫu khác

| Kết quả | PASS rate | Wilson 95% CI (xấp xỉ) |
|---|---:|---:|
| 9/10 | 90% | 59,6%–98,2% |
| 90/100 | 90% | 82,6%–94,5% |
| 900/1.000 | 90% | 87,98%–91,71% |

Cùng point estimate 90%, nhưng độ bất định giảm khi có nhiều quan sát độc lập hơn. **Đừng chỉ đưa point estimate mà bỏ interval và N.**

### Diễn giải 95% confidence interval

Theo cách diễn giải frequentist, nếu lặp lại quy trình lấy mẫu và xây interval rất nhiều lần dưới cùng assumptions, khoảng 95% các interval được tạo sẽ chứa parameter cố định.

Không nên diễn giải một cách máy móc rằng “có 95% xác suất parameter nằm trong khoảng này” sau khi interval đã được tính. Đó là cách diễn giải thuộc khuôn khổ Bayesian với prior/model riêng, không phải định nghĩa frequentist.

## 7. Không có critical failure trong mẫu không chứng minh rủi ro bằng 0

Đây là một giới hạn đặc biệt quan trọng với ứng dụng AI có thể đưa ra khuyến nghị nghiệp vụ, gọi tool hoặc truy cập dữ liệu.

Nếu quan sát **0 critical events trong n case độc lập**, upper bound một phía 95% cho xác suất sự kiện xấp xỉ:

\[
p_{\mathrm{upper}}=1-0,05^{1/n}\approx\frac{3}{n}.
\]

Quy tắc gần đúng này thường gọi là *rule of three*.

| Số case độc lập, không thấy critical | Upper bound 95% xấp xỉ |
|---:|---:|
| 30 | 10% |
| 100 | 3% |
| 500 | 0,6% |
| 1.000 | 0,3% |
| 3.000 | 0,1% |

Vì vậy, **0 critical trên 100 case không chứng minh critical risk bằng 0**. Nó chỉ cho thấy chưa quan sát được event trong mẫu đó; upper bound vẫn có thể ở mức vài phần trăm theo mô hình đơn giản.

Để đặt mục tiêu upper bound dưới 0,1% khi không thấy event, cần khoảng 3.000 case độc lập theo rule of three. Với event hiếm, clustering hoặc sampling bias, cần thiết kế lớn hơn/khác và phải đánh giá assumptions.

**Critical failure còn có thể là một class nhiều loại lỗi.** Nếu benchmark không có tình huống prompt injection, unauthorized tool use hoặc dữ liệu nhạy cảm, zero critical trong benchmark đó không chứng minh hệ thống an toàn trước các tình huống chưa được đưa vào.

## 8. Cỡ mẫu cho A/B với hai tỷ lệ độc lập

Nếu A và B được đánh giá trên hai nhóm case **khác nhau, độc lập**, một công thức planning gần đúng với allocation bằng nhau là:

\[
n_{\mathrm{per\ arm}}\approx
\frac{2(z_{1-\alpha/2}+z_{1-\beta})^2\bar p(1-\bar p)}
{\delta^2}.
\]

Trong đó:

- \(\delta\): mức chênh lệch tối thiểu muốn phát hiện;
- \(\bar p\): tỷ lệ trung bình dự kiến giữa hai arms;
- \(\alpha\): type-I error rate;
- \(1-\beta\): statistical power.

### Ví dụ

Giả sử:

- baseline khoảng 90%;
- candidate cần phát hiện mức tăng lên 93% (delta 3 pp);
- alpha hai phía 5%;
- power 80%;
- allocation A/B bằng nhau.

Với \(z_{0,975}\approx1,96\), \(z_{0,8}\approx0,84\), \(\bar p\approx0,915\), công thức gần đúng cho khoảng **1.356 case mỗi arm**.

Đây là planning estimate đơn giản. Công thức chính xác hơn có thể dùng \(p_A,p_B\), continuity correction hoặc phương pháp chuyên dụng. Nếu A/B dùng cùng case IDs, nên thiết kế paired comparison thay vì dùng công thức độc lập này.

### Mức chênh lệch tối thiểu có ý nghĩa (MDE)

MDE không nên chỉ được chọn vì “dễ đạt ý nghĩa thống kê”. Nó cần phản ánh mức cải thiện đáng để thay đổi prompt/model/pipeline sau khi xét:

- hậu quả của lỗi hiện tại;
- chi phí inference/judge;
- latency và trải nghiệm;
- rủi ro hồi quy ở critical slices;
- công sức vận hành và rollback.

Một thay đổi +0,2 pp có thể có p-value nhỏ với hàng triệu case nhưng không có ý nghĩa thực tế. Ngược lại, một cải thiện 5 pp trên nhóm an toàn quan trọng có thể rất đáng giá dù benchmark nhỏ và CI còn rộng; khi đó cần nói rõ mức độ bất định.

## 9. Cỡ mẫu cho paired A/B

Trong evaluation, A và B thường chạy trên **cùng case IDs**. Khi đó kết quả có tương quan và không nên dùng công thức hai mẫu độc lập như thể hai nhóm hoàn toàn tách biệt.

Với từng case, có hai loại cặp bất đồng:

- \(b\): A PASS, B FAIL (*regression*);
- \(c\): A FAIL, B PASS (*improvement*).

Trong **công thức planning**, \(b\) và \(c\) là xác suất/tỷ lệ của hai loại cặp trên toàn bộ paired cases, không phải số đếm thô. Khi báo bảng bốn ô sau khi chạy, nếu có \(B\) cặp hợp lệ thì dùng \(\hat b=N_{A\text{-only}}/B\) và \(\hat c=N_{B\text{-only}}/B\).

Khi đó \(q=b+c\) là tỷ lệ discordant pairs và \(\delta=c-b\) là paired pass-rate difference theo đơn vị tỷ lệ.

Một công thức planning xấp xỉ cho số **paired cases**:

\[
n\approx
\frac{(z_{1-\alpha/2}+z_{1-\beta})^2(q-\delta^2)}
{\delta^2}.
\]

Trong đó \(q\) phải được ước lượng từ pilot hoặc giả định bảo thủ. Với số discordant nhỏ, nên dùng exact McNemar power hoặc mô phỏng thay cho xấp xỉ chuẩn.

### Ví dụ paired planning

Giả sử pilot cho thấy khoảng 10% cặp có verdict khác nhau (\(q=0,10\)), muốn phát hiện paired delta 3 pp (\(\delta=0,03\)), alpha 5%, power 80%:

\[
n\approx
\frac{(1,96+0,84)^2(0,10-0,03^2)}{0,03^2}
\approx864\ \text{paired cases}.
\]

Con số này là **ước lượng gần đúng** phụ thuộc q. Nếu discordance thấp hơn, số cặp cần có thể giảm; nếu cao hơn hoặc hiệu ứng nhỏ hơn, số mẫu cần tăng.

### Sau khi chạy: bảng bốn ô và McNemar

| | B PASS | B FAIL |
|---|---:|---:|
| A PASS | Both pass | A-only pass = b |
| A FAIL | B-only pass = c | Both fail |

McNemar kiểm tra sự cân bằng giữa \(b\) và \(c\), không phải so hai tỷ lệ độc lập. Khi \(b+c\) nhỏ, dùng exact test. Confidence interval của paired delta nên được xây từ paired data (ví dụ paired bootstrap hoặc phương pháp phù hợp), không lấy hiệu hai Wilson intervals độc lập.

## 10. Clustering: nhiều câu hỏi từ cùng tài liệu không độc lập

Trong RAG, 50 câu hỏi có thể cùng dựa vào một chính sách. Nếu tài liệu có lỗi hoặc index bỏ chunk, cả 50 câu có thể cùng FAIL. Đếm chúng như 50 quan sát độc lập sẽ làm khoảng tin cậy hẹp giả tạo.

Một công thức đơn giản ước lượng design effect cho cluster có kích thước trung bình \(m\) và intraclass correlation \(\rho\):

\[
DEFF=1+(m-1)\rho.
\]

Effective sample size gần đúng:

\[
n_{\mathrm{eff}}\approx\frac{n}{DEFF}.
\]

### Ví dụ

Có 100 câu hỏi, mỗi 10 câu cùng một tài liệu (\(m=10\)), và tương quan nội cụm \(\rho=0,5\):

\[
DEFF=1+9(0,5)=5,5.
\]

\[
n_{\mathrm{eff}}\approx100/5,5\approx18,2.
\]

100 dòng verdict chỉ tương đương khoảng 18 quan sát độc lập theo xấp xỉ này. Đây là minh họa cho thấy **thêm nhiều câu cùng một nguồn không thay thế việc lấy thêm nguồn độc lập**.

### Cách giảm cluster bias

- Lấy mẫu nhiều documents/topics độc lập hơn.
- Giới hạn số case từ một tài liệu nếu mục tiêu là tổng quát hóa qua tài liệu.
- Lưu `cluster_id` trong dataset/report (không dùng làm metric label nếu cardinality cao).
- Dùng cluster bootstrap hoặc mô hình có random effects khi cần inference.
- Nếu mục tiêu là kiểm thử một corpus cố định, báo rõ kết luận chỉ áp dụng cho corpus snapshot đó.

Design effect trên giả định cluster size gần bằng nhau. Nếu cluster sizes khác nhiều, ICC phức tạp hoặc có nhiều tầng (document → topic → user), cần phương pháp phù hợp hơn; không dùng công thức đơn giản như hiệu chỉnh chính xác.

## 11. Lặp runs không thay thế việc tăng số case

Giả sử có:

- 20 case khác nhau;
- mỗi case chạy 10 lần;
- tổng cộng 200 verdicts.

10 lần lặp giúp ước lượng **stochastic variation của 20 case đó** tốt hơn. Nhưng không tự biến benchmark thành 200 case đại diện cho population. Độ bất định về case population vẫn chủ yếu dựa trên 20 tình huống.

### Hai câu hỏi khác nhau

| Mục tiêu | Nên tăng |
|---|---|
| Model có trả lời ổn định cho cùng tình huống? | Số lần generation repeats trên case |
| Judge có nhất quán trên cùng answer? | Số lần judge repeats trên answer snapshot |
| Chất lượng có tổng quát hóa qua câu hỏi mới? | Số case độc lập và độ đa dạng của sampling frame |
| Provider có biến động theo thời gian? | Số run blocks trải qua các time windows |
| A/B có cải thiện ổn định qua các lần chạy? | Paired run blocks và paired cases |

### Cấu trúc phân cấp

~~~text
Population of cases
  └── Sampled case IDs
        ├── Run block 1
        │     ├── Generator attempt
        │     └── Judge assessment
        ├── Run block 2
        │     ├── Generator attempt
        │     └── Judge assessment
        └── ...
~~~

Khi phân tích, phải giữ liên kết `case_id`, `run_block_id`, `run_id`, `attempt_id` và `assessment_id`. Không flatten tất cả thành một danh sách verdict rồi chạy công thức nhị thức đơn giản mà bỏ qua dependency.

## 12. Confidence interval cho score và metric không nhị phân

Pass/fail là nhị phân; score 0–4, relevance score liên tục hoặc latency là các loại dữ liệu khác.

### Score ordinal 0–4

- Báo count ở từng mức score.
- Báo median và IQR.
- Có thể bootstrap median/mean nếu resampling unit được chọn đúng.
- Không diễn giải score ordinal như khoảng cách tuyệt đối nếu rubric không đảm bảo điều đó.
- Khi rubric thay đổi, re-score cùng snapshots bằng một rubric chung hoặc phát hành revision mới.

### Latency

- Báo phân phối, p50/p90/p95, số mẫu và timeout rate.
- Với latency thường lệch phải, mean có thể bị kéo bởi tail.
- Bootstrap percentile cần đủ observations và phải resample theo case/run block phù hợp.
- Histogram buckets phải đủ độ phân giải quanh ngưỡng SLO.

### Cost

- Báo mean/median cost per eligible case và per completed case nếu cả hai hữu ích.
- Missing usage phải là trạng thái riêng, không tự gán cost bằng 0.
- Tách generator, judge, embedding và tool costs.
- Nếu rate card thay đổi, báo actual spend và normalized cost theo cùng price revision.

Không dùng một CI method cho mọi loại metric. Chọn theo sampling design, phân phối, pairing và câu hỏi nghiên cứu.

## 13. Bootstrap đúng đơn vị lấy mẫu

Bootstrap là kỹ thuật lấy mẫu lại từ dữ liệu quan sát để ước lượng phân phối của statistic. Trong evaluation, điều quan trọng nhất là **resample đúng unit**.

| Câu hỏi | Resampling unit gợi ý |
|---|---|
| Pass rate trên các case độc lập | Case IDs |
| Paired A/B delta | Case ID và giữ cặp A/B cùng nhau |
| Nhiều câu trong cùng document | Document/topic clusters |
| Dao động qua time blocks | Run blocks |
| Generator + judge repeats | Giữ hierarchy case → generation → assessment |

### Paired bootstrap

1. Lấy mẫu lại case IDs có hoàn lại.
2. Với mỗi case được chọn, giữ verdict A và B cùng nhau.
3. Tính lại paired delta.
4. Lặp đủ số bootstrap replicates đã đăng ký.
5. Dùng percentile/BCa interval phù hợp và ghi seed, số replicates, resampling unit.

Không bootstrap A và B độc lập nếu thiết kế là paired. Làm vậy sẽ phá cấu trúc tương quan.

### Cluster bootstrap

Nếu các câu hỏi cùng document/topic tương quan, lấy mẫu lại **cluster** trước rồi giữ các case trong cluster. Nếu resample từng case độc lập, interval có thể quá hẹp.

### Bootstrap không chữa được bias

Nếu sampling frame thiếu nhóm câu hỏi quan trọng, bootstrap từ chính frame đó không tạo ra những nhóm bị thiếu. Bootstrap phản ánh variation trong dữ liệu quan sát dưới resampling design; nó không tự sửa dataset selection bias, judge bias hoặc ground-truth errors.
## 14. Power, alpha, beta và MDE

Khi kiểm định một giả thuyết A/B:

- **Alpha (\(\alpha\))**: xác suất type-I error theo thiết kế kiểm định — kết luận có khác biệt khi null hypothesis đúng.
- **Beta (\(\beta\))**: xác suất type-II error tại effect size được giả định.
- **Power = \(1-\beta\)**: khả năng phát hiện effect size đã định nếu effect đó thực sự tồn tại, theo assumptions.
- **MDE**: mức effect nhỏ nhất mà thiết kế muốn phát hiện.

Ví dụ alpha 5%, power 80%, MDE 3 pp. Điều đó không có nghĩa mọi chênh lệch 3 pp sẽ được phát hiện chắc chắn; power 80% là xác suất có điều kiện theo mô hình và assumptions.

### Statistical significance không phải practical significance

| Kết quả | Diễn giải |
|---|---|
| Delta +0,2 pp, CI hẹp, p nhỏ | Có thể khác biệt thống kê nhưng chưa đáng thay đổi sản phẩm |
| Delta +5 pp, CI rộng | Hiệu ứng tiềm năng lớn nhưng bằng chứng chưa chắc |
| Delta +1 pp, critical cases tăng | Không thể bỏ qua critical regression vì điểm trung bình |
| Delta gần 0, CI nằm trong biên tương đương đã đăng ký | Có thể hỗ trợ kết luận non-inferiority/equivalence theo thiết kế phù hợp |

Không dùng “p > 0,05” để tuyên bố A và B tương đương. Muốn kết luận equivalence hoặc non-inferiority, phải định nghĩa margin và dùng test/CI tương ứng.

## 15. Multiple comparisons: càng nhiều slice càng dễ thấy kết quả tình cờ

Một report có thể kiểm tra:

- 3 business groups;
- 3 difficulty levels;
- 4 scenarios;
- 5 metrics;
- nhiều model/prompt versions.

Nếu thử hàng chục/hàng trăm giả thuyết và chỉ chọn slice có p-value đẹp, nguy cơ false positives tăng.

### Cách quản lý

1. Chọn trước **primary metric** và một số **critical slices**.
2. Phân biệt confirmatory analysis với exploratory analysis.
3. Với nhiều kiểm định khẳng định, cân nhắc Holm/Bonferroni để kiểm soát family-wise error hoặc Benjamini–Hochberg khi mục tiêu là false discovery rate.
4. Công bố toàn bộ slices đã kiểm tra, không chỉ các slice có kết quả thuận lợi.
5. Không tự đổi primary metric sau khi thấy kết quả.

Hiệu chỉnh multiple comparisons có thể giảm power; đây là trade-off phải tính trong sample-size planning.

## 16. Optional stopping và peeking vào kết quả

Một lỗi thường gặp:

1. Chạy 50 case, thấy B đang thắng.
2. Chạy thêm 50 case, thấy delta giảm.
3. Chạy tiếp đến khi p-value nhỏ hơn 0,05.
4. Dừng và công bố kết quả như thể chỉ kiểm định một lần.

Việc xem kết quả liên tục rồi dừng khi đạt ngưỡng có thể làm tăng type-I error nếu không dùng thiết kế sequential phù hợp.

### Quy tắc dừng

- Đăng ký sample size/run blocks trước.
- Định nghĩa điều kiện dừng vì quota, safety incident hoặc lỗi hệ thống.
- Nếu muốn interim analyses, dùng group-sequential design, alpha-spending hoặc confidence sequences phù hợp.
- Không xóa các runs đã thực hiện khi thay đổi kế hoạch.
- Ghi mọi deviation và phân tích exploratory riêng.

**Không phải mọi repeated monitoring đều sai.** Monitoring production cần cảnh báo liên tục; điều quan trọng là phân biệt operational alerting với một kiểm định giả thuyết có alpha/stopping rule.

## 17. Judge và ground truth tạo thêm giới hạn đo lường

Một confidence interval hẹp không có nghĩa answer đúng nếu:

- expected claims bị sai;
- dataset labels lỗi;
- judge ưu tiên câu trả lời dài;
- judge có self-preference hoặc position bias;
- context có prompt injection;
- rubric chưa định nghĩa ngoại lệ nghiệp vụ;
- cùng một judge vừa tạo ground truth vừa đánh giá answer.

### Calibration

1. Tạo human-labeled calibration set gồm answer đúng/sai, paraphrase, thiếu evidence, distractors và safety cases.
2. So judge với human labels: agreement, false pass, false fail và critical false negatives.
3. Khóa judge model/prompt/rubric revision trong A/B.
4. Nếu đổi judge, chấm lại answer/evidence snapshots của cả hai arms bằng judge mới.
5. Human review các critical failures và những bất đồng có rủi ro cao.

### Lỗi phân loại verdict

Giả sử judge có sensitivity/specificity chưa hoàn hảo. Khi đó pass rate đo được là kết quả của **hệ thống + phép đo**, không chỉ generator. Tăng số case làm giảm sampling error nhưng không loại bỏ systematic judge bias.

Với critical events hiếm, false negative của judge đặc biệt nguy hiểm. Cần human audit có chủ đích trên các case rủi ro, không chỉ dựa vào random sample.

## 18. Missingness, coverage và cỡ mẫu thực tế

Nếu muốn có \(n\) verdict hợp lệ và dự kiến tỷ lệ coverage \(c\), số case cần giao chạy sơ bộ:

\[
N_{\mathrm{assigned}}\approx\frac{n}{c}.
\]

Ví dụ cần 385 verdict hợp lệ, coverage dự kiến 95%:

\[
N_{\mathrm{assigned}}\approx385/0,95\approx406.
\]

Đây chỉ là điều chỉnh dự phòng đơn giản. Nếu missingness phụ thuộc vào độ khó hoặc loại case, tăng sample size không tự sửa bias.

### Phân biệt missingness

| Trạng thái | Cách xử lý |
|---|---|
| Generation error | Ghi execution error; không tính như quality FAIL nếu không có answer |
| Evaluation error | Ghi judge error; không tính vào pass denominator |
| Tool error | Ghi tool operational error; chỉ chấm answer nếu rubric có evidence đủ |
| Skipped | Báo skipped và nguyên nhân |
| Missing row | Coverage giảm; tìm case/run bị mất |
| Not applicable | Loại khỏi metric eligibility theo policy |

Không dùng denominator của một metric cho metric khác. Fact checking, retrieval recall, tool correctness và abstention có thể có tập eligible khác nhau.

### Missingness có thể gây selection bias

Nếu candidate B timeout chủ yếu trên case hard, pass rate trên những case còn được chấm có thể trông rất tốt. Phải báo coverage theo arm, slice và nguyên nhân; measurement gate có thể chặn kết luận khi coverage không đạt.

## 19. Kết luận nào được phép rút ra?

Một report nên chia thành ba tầng:

### Descriptive — mô tả dữ liệu đã chạy

Ví dụ:

> Trên 400 case được đánh giá trong regression suite revision v5, B có 360 PASS/380 verdict hợp lệ, pass rate 94,7%, coverage 95%.

Đây là mô tả số liệu đã quan sát, chưa tự suy rộng ra mọi người dùng.

### Inferential — suy luận trong phạm vi assumptions

Ví dụ:

> Theo sampling plan và Wilson interval đã chọn, pass rate trên population mà sampling frame đại diện được ước lượng trong khoảng ...

Phải nói rõ sampling frame, independence/clustering assumptions, judge calibration và khoảng bất định.

### Causal — kết luận thay đổi X gây ra Y

Muốn kết luận prompt mới **gây ra** cải thiện, cần kiểm soát các biến khác, phân bổ A/B phù hợp, run blocks/interleaving và không có thay đổi đồng thời về model/index/judge. Nếu cùng lúc đổi prompt, model, retriever và corpus, chỉ kết luận được bundle mới có kết quả khác; không quy riêng cho prompt.

### Những giới hạn phải công bố

- Dataset không bao phủ ngôn ngữ, domain, độ khó hoặc user intents nào?
- Có bao nhiêu case/cluster độc lập?
- Có bao nhiêu attempts/runs và cách xử lý retry?
- Coverage/error rates có khác giữa A/B không?
- Judge có human calibration không?
- Provider resolved model revision có biết không?
- Các critical failures đã được review chưa?
- Có multiple comparisons/optional stopping không?
- CI mô tả uncertainty nào và bỏ sót uncertainty nào?

## 20. Java 21: tính Wilson interval và cỡ mẫu planning

Đoạn code thuần JDK dưới đây cung cấp:

- Wilson confidence interval cho một tỷ lệ;
- cỡ mẫu xấp xỉ cho precision mục tiêu;
- upper bound một phía khi không quan sát event nào.

### File `ProportionPlanning.java`

~~~java
package com.example.aiquality.statistics;

public final class ProportionPlanning {
    private ProportionPlanning() {}

    public record Interval(double lower, double upper) {}

    public static Interval wilson(
            int successes, int trials, double z) {
        if (trials <= 0 || successes < 0 || successes > trials
                || !Double.isFinite(z) || z <= 0) {
            throw new IllegalArgumentException("Tham số Wilson không hợp lệ");
        }

        double n = trials;
        double p = successes / n;
        double z2 = z * z;
        double denominator = 1.0 + z2 / n;
        double center = (p + z2 / (2.0 * n)) / denominator;
        double halfWidth = z / denominator
                * Math.sqrt(p * (1.0 - p) / n
                    + z2 / (4.0 * n * n));

        return new Interval(
                Math.max(0.0, center - halfWidth),
                Math.min(1.0, center + halfWidth));
    }

    public static long requiredSampleSize(
            double expectedRate,
            double marginOfError,
            double z) {
        if (!Double.isFinite(expectedRate) || expectedRate <= 0
                || expectedRate >= 1
                || !Double.isFinite(marginOfError)
                || marginOfError <= 0 || marginOfError >= 1
                || !Double.isFinite(z) || z <= 0) {
            throw new IllegalArgumentException("Tham số planning không hợp lệ");
        }

        double estimate = z * z * expectedRate
                * (1.0 - expectedRate)
                / (marginOfError * marginOfError);
        if (estimate > Long.MAX_VALUE) {
            throw new IllegalArgumentException("Cỡ mẫu vượt giới hạn");
        }
        return (long) Math.ceil(estimate);
    }

    public static double zeroEventUpperBound(
            int trials, double alpha) {
        if (trials <= 0 || !Double.isFinite(alpha)
                || alpha <= 0 || alpha >= 1) {
            throw new IllegalArgumentException("Tham số zero-event không hợp lệ");
        }
        return 1.0 - Math.pow(alpha, 1.0 / trials);
    }
}
~~~

### Cách gọi

~~~java
double z95 = 1.959963984540054;

var interval = ProportionPlanning.wilson(90, 100, z95);
long n = ProportionPlanning.requiredSampleSize(0.90, 0.03, z95);
double criticalUpper = ProportionPlanning.zeroEventUpperBound(100, 0.05);

System.out.printf("Wilson: %.3f - %.3f%n",
        interval.lower(), interval.upper());
System.out.printf("Required n: %d%n", n);
System.out.printf("Zero-event upper bound: %.3f%n", criticalUpper);
~~~

Hàm `zeroEventUpperBound` tính exact one-sided binomial upper bound khi số event quan sát bằng 0 dưới mô hình Bernoulli độc lập; rule of three là xấp xỉ. Nó không xử lý clustering hoặc bias trong event detection.

## 21. JUnit 5 cho phép tính và kiểm tra biên

### File `ProportionPlanningTest.java`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import com.example.aiquality.statistics.ProportionPlanning;

class ProportionPlanningTest {

    private static final double Z_95 = 1.959963984540054;

    @Test
    void wilsonIntervalContainsObservedRate() {
        var ci = ProportionPlanning.wilson(90, 100, Z_95);

        assertTrue(ci.lower() < 0.90);
        assertTrue(ci.upper() > 0.90);
        assertTrue(ci.lower() >= 0.0);
        assertTrue(ci.upper() <= 1.0);
        assertTrue(ci.lower() < ci.upper());
    }

    @Test
    void largerSampleProducesNarrowerWilsonInterval() {
        var small = ProportionPlanning.wilson(9, 10, Z_95);
        var large = ProportionPlanning.wilson(900, 1000, Z_95);

        double smallWidth = small.upper() - small.lower();
        double largeWidth = large.upper() - large.lower();
        assertTrue(largeWidth < smallWidth);
    }

    @Test
    void calculatesPlanningSampleSize() {
        assertEquals(385,
            ProportionPlanning.requiredSampleSize(0.90, 0.03, Z_95));
        assertEquals(1068,
            ProportionPlanning.requiredSampleSize(0.50, 0.03, Z_95));
    }

    @Test
    void zeroEventUpperBoundShrinksAsSampleGrows() {
        double hundred = ProportionPlanning.zeroEventUpperBound(100, 0.05);
        double thousand = ProportionPlanning.zeroEventUpperBound(1000, 0.05);

        assertTrue(hundred > 0.02 && hundred < 0.04);
        assertTrue(thousand < hundred);
    }

    @Test
    void rejectsInvalidInputs() {
        assertThrows(IllegalArgumentException.class,
            () -> ProportionPlanning.wilson(11, 10, Z_95));
        assertThrows(IllegalArgumentException.class,
            () -> ProportionPlanning.requiredSampleSize(0.9, 0.0, Z_95));
        assertThrows(IllegalArgumentException.class,
            () -> ProportionPlanning.zeroEventUpperBound(0, 0.05));
    }
}
~~~

Đây là **mã hướng dẫn**, chưa được build hoặc chạy trong phạm vi viết bài. Nó không thay thế thư viện thống kê đã được kiểm chứng cho exact tests, paired CI, power analysis hoặc complex survey design. Với báo cáo release quan trọng, hãy kiểm tra kết quả bằng một implementation thống kê độc lập và review assumptions.

## 22. Quy trình lập kế hoạch cỡ mẫu cho một experiment

~~~mermaid
flowchart TD
  A["Xác định population và quyết định cần hỗ trợ"] --> B["Chọn metric, eligibility và đơn vị quan sát"]
  B --> C["Thiết kế sampling frame và strata/clusters"]
  C --> D["Pilot: ước lượng p, variance, discordance, coverage"]
  D --> E["Chọn precision hoặc MDE/power"]
  E --> F["Tính n và điều chỉnh design effect/missingness"]
  F --> G["Đăng ký run count, stopping rule, primary slices"]
  G --> H["Chạy A/B hoặc repeated runs, lưu mọi attempts"]
  H --> I["Kiểm coverage, judge calibration, manifest"]
  I --> J["CI/paired analysis/cluster bootstrap"]
  J --> K["Đánh giá critical failures và giới hạn kết luận"]
  K --> L["PROMOTE / REJECT / INCONCLUSIVE"]
~~~

### Bản kế hoạch mẫu

~~~yaml
experiment_id: "rag-sample-size-001"
question: "Prompt B có cải thiện fact-check pass rate không?"
population: "Câu hỏi tiếng Việt thuộc các policy domains trong scope"
sampling_frame_revision: "policy-frame-v3"
sampling_design:
  type: "stratified_by_business_and_difficulty"
  cluster_unit: "source_document"
primary_metric:
  id: "fact_check_pass_rate"
  eligibility_revision: "fact-check-eligible-v2"
  minimum_effect_pp: 3.0
  alpha_two_sided: 0.05
  power: 0.80
comparison:
  design: "paired_case_ids"
  planning_discordance_rate: 0.10
  estimated_paired_cases: 864
  run_blocks: 5
guardrails:
  minimum_paired_coverage: 0.98
  maximum_critical_cases: 0
  maximum_generation_error_rate: 0.02
  maximum_evaluation_error_rate: 0.01
stopping:
  type: "fixed_sample"
  no_unplanned_peeking: true
judge:
  model_revision: "judge-model-revision"
  rubric_revision: "fact-check-v2"
  human_calibration_revision: "human-labels-v3"
~~~

Đây là ví dụ schema do project tự định nghĩa. `estimated_paired_cases` phải được tính từ pilot/assumptions thật; con số 864 chỉ khớp với ví dụ \(q=0,10\), delta 3 pp, alpha 5%, power 80% ở mục 9.

## 23. Report: trình bày kết quả và giới hạn cùng nhau

Một report có thể dùng cấu trúc:

| Thành phần | Nội dung bắt buộc |
|---|---|
| Research question | Câu hỏi và quyết định muốn hỗ trợ |
| Target population | Phạm vi domain, language, workflow và thời gian |
| Sampling design | Frame, strata, clusters, weights và exclusions |
| Sample size | Planned N, observed N, unique cases, run blocks, attempts |
| Metric definitions | Eligibility, denominator, scoring policy, threshold |
| Estimates | Pass rate, score distribution, critical case count |
| Uncertainty | CI, paired delta interval, run variation, cluster method |
| Coverage | Missing, generation/evaluation/tool errors theo slice |
| Calibration | Judge/human agreement, false pass/false fail |
| Operations | Latency, tokens, cost, provider/model metadata |
| Limitations | Selection bias, small slices, unknown model revision, drift |
| Decision | PROMOTE/REJECT/INCONCLUSIVE và lý do |

### Ví dụ cách viết kết luận có giới hạn

> Trên 400 case được lấy mẫu phân tầng từ sampling frame policy-v3, candidate B có fact-check pass rate 93% trên 392 verdict hợp lệ; paired coverage là 98%. Paired delta ước lượng +2,1 điểm phần trăm, nhưng interval vẫn bao gồm mức cải thiện rất nhỏ. Không quan sát critical failure trong mẫu; điều này không chứng minh critical risk bằng 0. Kết luận chỉ áp dụng cho các policy domains và corpus revision đã đưa vào sampling frame. Cần mở rộng mẫu hard cases trước khi triển khai rộng.

Đây là **mẫu diễn đạt giả lập**, không phải kết quả thật. Cách viết này tách estimate, uncertainty, coverage và phạm vi generalization.

## 24. Những giới hạn mà tăng cỡ mẫu không giải quyết được

| Giới hạn | Vì sao thêm case chưa đủ | Cần làm gì |
|---|---|---|
| Sampling bias | Mẫu không đại diện | Cải thiện frame và stratification |
| Ground-truth errors | Nhãn sai có hệ thống | Domain review và version labels |
| Judge bias | Evaluator sai theo hướng nhất quán | Human calibration, blind review |
| Model alias drift | Backend thay đổi không được ghi | Resolved revision/metadata nếu provider hỗ trợ |
| Corpus/index drift | Evidence đầu vào thay đổi | Snapshot và manifest |
| Tool fixture thiếu thực tế | Benchmark không phản ánh side effects thật | Sandbox fixtures có coverage |
| Prompt injection chưa có trong dataset | Không đo được threat chưa thử | Threat-model-driven test cases |
| Cluster dependence | Effective N thấp hơn raw N | Cluster-aware analysis |
| Missing not at random | Case khó bị mất verdict nhiều hơn | Coverage analysis và sensitivity analysis |
| Multiple testing | Tăng nguy cơ false discoveries | Pre-registration và correction |
| Optional stopping | Sai lệch alpha khi peeking | Fixed/sequential design phù hợp |
| External validity | Kết quả không tự chuyển sang domain khác | Validation trên target population mới |

Một khoảng tin cậy rất hẹp vẫn có thể **đo chính xác một benchmark không đại diện**. Statistical precision và validity là hai vấn đề riêng.

## 25. Checklist trước khi công bố kết luận

- [ ] Population và quyết định cần hỗ trợ được nêu rõ.
- [ ] Sampling frame, exclusions và cách chọn case được version hóa.
- [ ] Đơn vị quan sát phân biệt case, cluster, run, attempt và assessment.
- [ ] Cỡ mẫu được planning theo precision hoặc MDE/power trước khi chạy.
- [ ] Nếu chưa biết tỷ lệ dự kiến, giả định planning bảo thủ được giải thích.
- [ ] Với paired A/B, dùng paired design và tính đến discordant-pair rate.
- [ ] Có điều chỉnh clustering/stratification khi case phụ thuộc.
- [ ] Số case độc lập không bị nhầm với N×R repeated verdicts.
- [ ] Báo point estimate, N, CI và phương pháp tính.
- [ ] Critical zero-event được diễn giải bằng upper bound, không tuyên bố rủi ro bằng 0.
- [ ] Generator variance và judge variance được đo riêng khi cần.
- [ ] Coverage/errors/missingness được báo theo arm và slice.
- [ ] Judge calibration, label quality và evidence snapshots được kiểm tra.
- [ ] Multiple comparisons và stopping rule đã được đăng ký.
- [ ] Statistical significance được phân biệt với practical significance.
- [ ] Kết luận causal chỉ đưa ra khi thiết kế kiểm soát được confounders.
- [ ] Report nêu rõ phạm vi generalization và các domain chưa được kiểm thử.
- [ ] Critical failures có human review và veto policy phù hợp.
- [ ] Latency/token/cost được tính trên metric scope và rate card rõ ràng.

## Tài liệu tham khảo

1. [NIST Engineering Statistics Handbook — Proportions](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm): ước lượng tỷ lệ và khoảng tin cậy.
2. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): sample design, precision, hypothesis testing và experimental design.
3. [Cochran, Sampling Techniques](https://www.wiley.com/en-us/Sampling+Techniques%2C+3rd+Edition-p-9780471162407): stratified/cluster sampling và sample-size planning.
4. [SciPy — Proportion Confidence Intervals](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html): các phương pháp interval cho tỷ lệ nhị thức.
5. [SciPy — Bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html): bootstrap confidence intervals.
6. [Spring AI — Evaluation](https://docs.spring.io/spring-ai/reference/api/testing.html): evaluator và evaluation request trong kiểm thử AI.
7. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations, traces và token usage.
8. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics, timers và histograms.
9. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile và histogram buckets.
10. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong logs/telemetry.

> **Ghi nhớ:** Cỡ mẫu không phải con số trang trí trong report. Nó phải bắt đầu từ population, đơn vị quan sát, metric, độ chính xác hoặc effect size cần phát hiện và cấu trúc phụ thuộc của dữ liệu. Hãy báo cả khoảng bất định, coverage, judge calibration và giới hạn sampling. Một benchmark lớn nhưng thiên lệch vẫn có thể dẫn đến kết luận sai; một benchmark nhỏ nhưng được mô tả trung thực có thể giúp nhóm biết chính xác điều gì cần kiểm tra tiếp.
