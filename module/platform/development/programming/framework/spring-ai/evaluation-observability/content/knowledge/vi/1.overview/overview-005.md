# Phân biệt đánh giá ngoại tuyến và theo dõi chất lượng khi vận hành

Một chatbot Spring AI có thể đạt 96% bài kiểm tra trên bộ câu hỏi nội bộ nhưng vẫn khiến người dùng production phàn nàn vì trả lời sai chính sách mới, không gọi được công cụ hoặc phản hồi chậm. Ngược lại, một dashboard cho thấy 99,9% HTTP request thành công và p95 latency thấp cũng chưa chứng minh câu trả lời đúng nội dung.

Hai kiểu đo lường giải quyết hai câu hỏi khác nhau:

- **Đánh giá ngoại tuyến (offline evaluation):** với tập tình huống và tiêu chí đã biết, phiên bản prompt/model/RAG/tool hiện tại *đạt chất lượng đến đâu* và có tốt hơn baseline không?
- **Theo dõi chất lượng khi vận hành (online quality monitoring):** với yêu cầu thực tế thay đổi theo thời gian, *người dùng đang nhận kết quả thế nào*, có suy giảm, lỗi mới hoặc biến động độ trễ/chi phí không?

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, hai cách tiếp cận cần kết hợp để đánh giá bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling, đồng thời theo dõi metrics, traces, chi phí và độ trễ giữa các phiên bản prompt, model, pipeline. Một hệ thống đủ tin cậy cần **offline evaluation để kiểm soát thay đổi** và **online monitoring để phát hiện hiện thực khác với giả định khi thiết kế**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa offline evaluation, online quality monitoring và phân biệt chúng với kiểm thử tải, canary hoặc A/B testing.
2. Giải thích lợi ích và giới hạn của dataset cố định so với dữ liệu thực tế trong production.
3. Thiết kế phép đo relevance, factual correctness, groundedness, retrieval và tool-calling cho môi trường offline lẫn online.
4. Tổ chức lấy mẫu, gắn nhãn, chấm tự động và kiểm duyệt của con người mà không đánh đồng mẫu đã chấm với toàn bộ lưu lượng.
5. Nhận diện thay đổi chất lượng do **hệ thống suy giảm**, **phân bố câu hỏi thay đổi** hoặc **cách đo thay đổi**.
6. Kết hợp quality metrics với traces, error rate, token usage, chi phí và latency để đưa ra giả thuyết nguyên nhân.
7. Thiết kế quy trình release gate, canary, cảnh báo, điều tra, cập nhật dataset và đánh giá hồi quy.

## 2. Điểm khác nhau cốt lõi

| Khía cạnh | Offline evaluation | Online quality monitoring |
| --- | --- | --- |
| Môi trường | Test harness, local, CI hoặc staging | Production hoặc canary với lưu lượng thật |
| Nguồn đầu vào | Dataset được chọn trước, có version và nhãn | Yêu cầu thực; phân bố thay đổi theo thời gian |
| Đáp án/tiêu chí | Thường có reference facts, expected tool behavior, rubric | Thường thiếu nhãn tức thời; phải lấy mẫu, chấm và xác minh |
| Mục đích | So sánh candidate với baseline, ngăn hồi quy trước phát hành | Phát hiện drift, vấn đề mới, tác động lên người dùng |
| Khả năng tái lập | Tương đối cao nếu đóng băng cấu hình, nguồn và judge | Thấp hơn vì tải, dữ liệu, thời điểm, người dùng thay đổi |
| Thời điểm | Trước deploy, sau khi đổi prompt/model/corpus/pipeline và định kỳ | Liên tục hoặc theo cửa sổ thời gian trong vận hành |
| Tín hiệu | Pass rate theo rubric, retrieval hit@k, tool contract pass, lỗi theo case | Error/latency/cost, quality pass trên mẫu có nhãn, feedback, cảnh báo |
| Ưu điểm | Dễ so cùng một bộ câu hỏi và phân tích từng case | Bao phủ tình huống thực, phát hiện vấn đề ngoài dataset |
| Hạn chế | Có thể bỏ sót dữ liệu thực, overfit vào bộ ca, nguồn bị lỗi thời | Nhãn thiếu/chậm, lệch mẫu, chi phí chấm, khó chứng minh nguyên nhân |

**Không có cách nào thay thế hoàn toàn cách kia.** Offline evaluation giúp trả lời “candidate đã qua bộ kiểm định chưa?”, còn online monitoring trả lời “sau khi sử dụng thật, chất lượng có còn như kỳ vọng không?”.

### 2.1. Minh họa hai luồng dữ liệu

~~~mermaid
flowchart LR
    subgraph OFF["Offline evaluation"]
        A["Dataset + nguồn chuẩn<br/>+ rubric"] --> B["Run candidate<br/>Spring AI"]
        B --> C["Answer / retrieved docs<br/>/ tool events"]
        C --> D["Evaluator + assertions"]
        D --> E["Baseline comparison<br/>+ release gate"]
    end

    subgraph ON["Online quality monitoring"]
        F["User requests<br/>production"] --> G["Spring AI service"]
        G --> H["Metrics / traces<br/>+ safe sampling"]
        H --> I["Labeling / judge / review"]
        I --> J["Quality trends<br/>+ alerts + investigation"]
    end

    J --> K["Curated failures<br/>with reviewed labels"]
    K --> A
    E --> G
~~~

Điểm nối hai luồng là **bộ ca hồi quy**. Một lỗi phát hiện trong production, sau khi được xác minh và loại bỏ dữ liệu nhạy cảm, có thể trở thành case offline. Khi đổi phiên bản, nhóm chạy lại case đó để ngăn lỗi tái diễn.

## 3. Offline evaluation: kiểm soát thay đổi trước khi phát hành

Offline evaluation chạy hệ thống trên những ca đã định nghĩa. Một ca thường gồm:

- `caseId` và câu hỏi hoặc ngữ cảnh hội thoại.
- Điều kiện đầu vào, quyền truy cập, trạng thái tool/backend được cố định.
- Dữ kiện bắt buộc, đáp án chuẩn, nguồn tham chiếu và phiên bản nguồn.
- Tài liệu RAG kỳ vọng truy xuất, hành vi công cụ kỳ vọng.
- Rubric, trọng số hoặc điều kiện PASS/FAIL.
- Phân loại ca: bình thường, thiếu bằng chứng, nguồn mâu thuẫn, tool timeout, đa ngôn ngữ, an toàn.

Ví dụ **chính sách giả định** của một doanh nghiệp: gói Pro cho phép yêu cầu hoàn phí trong 14 ngày tính từ ngày mua, theo tài liệu có hiệu lực `policy-v3`.

~~~json
{
  "datasetVersion": "refund-eval-v1",
  "caseId": "REFUND-PRO-001",
  "question": "Tôi mua gói Pro được 10 ngày, còn xin hoàn phí được không?",
  "referenceDocumentId": "policy-v3#refund",
  "expectedFacts": [
    "Gói Pro có thời hạn 14 ngày kể từ ngày mua",
    "Mua được 10 ngày vẫn nằm trong thời hạn"
  ],
  "forbiddenClaims": ["Thời hạn là 30 ngày"],
  "expectedRetrievalIds": ["policy-v3#refund"],
  "expectedBehavior": "Trả lời điều kiện áp dụng, không tự cam kết đã hoàn tiền",
  "tags": ["rag", "vi", "policy", "multi-fact"],
  "rubricVersion": "refund-rubric-v1"
}
~~~

Một lần chạy cần lưu answer, các đoạn tài liệu thực tế tìm được, tool calls và metadata cấu hình. Các mục này là **bằng chứng thực thi**, khác với `expectedFacts` và `expectedRetrievalIds`.

### 3.1. Đánh giá nhiều lớp, không chỉ câu trả lời cuối

| Lớp | Tiêu chí offline | Bằng chứng |
| --- | --- | --- |
| Retrieval | `hit@k`, `Recall@k`, lọc đúng tài liệu/tenant | IDs và versions của top-k documents |
| Generation | Relevance, groundedness, factual correctness, completeness | Câu trả lời, ngữ cảnh thật và nguồn chuẩn |
| Citation | Dẫn nguồn đúng, nguồn còn hiệu lực | Answer citations và tài liệu tương ứng |
| Tool calling | Chọn tool, đối số, số lần gọi, quyền và hậu điều kiện | Tool events, trạng thái môi trường test |
| Functional safety | Schema, authorization, không gây side effect trái phép | Unit/integration/contract assertions |
| Operations | Latency, tokens, chi phí ước tính trong điều kiện kiểm thử | Traces, metrics, provider usage |

**Groundedness** hỏi: “Những khẳng định trong câu trả lời có được **các tài liệu đã thực sự cung cấp cho model** hỗ trợ không?”. **Factual correctness** hỏi: “Những khẳng định đó có đúng với nguồn sự thật đã được xác minh và đang có hiệu lực không?”. Hai kết quả có thể khác nhau nếu retrieval lấy tài liệu cũ.

Spring AI có giao diện đánh giá và các evaluator như `RelevancyEvaluator` hoặc `FactCheckingEvaluator` để hỗ trợ chấm mức độ liên quan và căn cứ theo ngữ cảnh. Với kiểm tra xác định như quyền, đối số tool, JSON schema, đếm số lần giao dịch, nên dùng test Java/integration thay vì chỉ dựa vào một model chấm.

### 3.2. Giá trị của cùng một bộ dữ liệu

Khi nhóm muốn so prompt A với prompt B, giữ nguyên:

1. Bộ câu hỏi, nhãn và rubric.
2. Corpus/document versions và quyền truy xuất.
3. Cấu hình retrieval, model, tool, môi trường, trừ đúng biến muốn thử.
4. Judge configuration hoặc nêu rõ khi có thay đổi bộ chấm.
5. Cách tính metric, phân nhóm và mẫu số.

Nếu mô hình vẫn có tính ngẫu nhiên, nhiều lần chạy cùng cấu hình có thể cho đầu ra khác nhau. Có thể thực hiện repeated runs cho các ca rủi ro cao và công bố phạm vi biến động. Một lần chạy duy nhất không đủ để kết luận chênh lệch nhỏ có ý nghĩa.

### 3.3. Những gì offline evaluation không chứng minh được

Một candidate đạt hết 50 case chưa có nghĩa là đạt trên mọi câu người dùng sẽ hỏi. Dataset hữu hạn có thể thiếu từ ngữ địa phương, câu có lỗi chính tả, câu dài, trường hợp mới phát sinh và luồng tool bất thường.

Nếu cứ sửa prompt để qua cùng bộ ca, ứng dụng có thể **overfit** dataset. Nên duy trì tập phát triển, tập hồi quy cho lỗi cũ và tập đánh giá độc lập (held-out), hạn chế chỉnh trực tiếp trên bộ kiểm định độc lập.

Nếu phiên bản nguồn tham chiếu hết hiệu lực, điểm offline cao vẫn có thể phản ánh câu trả lời sai quy định mới. Dataset phải được bảo trì.

## 4. Online quality monitoring: xem người dùng thật đang nhận gì

Online quality monitoring tập trung vào kết quả và hành vi của hệ thống trong điều kiện sử dụng thực:

- Truy vấn và ý định của người dùng biến động theo thời điểm.
- Tài liệu nội bộ, backend tool, nhà cung cấp model hoặc giới hạn API có thể đổi.
- Tải đồng thời, độ trễ mạng, rate limit và lỗi retry xuất hiện khác môi trường test.
- Đa số câu hỏi không có sẵn đáp án được chuyên gia xác minh ngay tại thời điểm request.
- Một số người dùng chỉ gửi phản hồi khi rất hài lòng hoặc rất bất mãn, tạo **selection bias**.

Để theo dõi chất lượng, cần **ba lớp tín hiệu**:

| Nhóm tín hiệu | Ví dụ | Có chứng minh nội dung đúng không? |
| --- | --- | --- |
| **Vận hành tự động** | HTTP error rate, timeout, p95 latency, tokens, cost, retry, tool errors | Không |
| **Dấu hiệu chất lượng tự động** | Không có citation, tài liệu không hiệu lực, lỗi cấu trúc, evaluator trên mẫu | Chỉ trong phạm vi rubric và bằng chứng |
| **Chất lượng xác minh** | Chuyên gia kiểm tra câu trả lời, nguồn chuẩn, phản hồi đã được thẩm định | Đáng tin hơn cho ca đã xem nhưng vẫn có phạm vi mẫu |

**Online không có nghĩa mọi request đều được LLM judge chấm ngay lập tức.** Thực tế có thể lấy mẫu theo rủi ro, xử lý theo lô, xác minh sau một khoảng thời gian và đánh dấu ca chưa có nhãn. Việc chấm có thể tốn chi phí, có giới hạn riêng tư và có độ trễ.

### 4.1. Online technical health khác online answer quality

Ví dụ dashboard:

~~~text
Tổng request trong 1 giờ:                  10.000
Request HTTP thành công:                    9.980
p95 end-to-end latency:                     1,9 giây
Request được chọn để review:                  200
Request đã được xác minh nội dung:            150
Câu được xác minh là đạt rubric:              132
~~~

Số trên là **minh họa**. Ta có thể tính:

- Tỷ lệ thành công HTTP: `9.980 / 10.000 = 99,8%`.
- Tỷ lệ đạt chất lượng **trên 150 ca đã có nhãn**: `132 / 150 = 88%`.
- Có 50 ca được chọn nhưng chưa có kết luận chất lượng.

**Không được công bố “88% của toàn bộ 10.000 request production đạt”** khi chưa chứng minh 150 ca là mẫu đại diện và có xử lý sai lệch chọn mẫu/thiếu nhãn. Tỷ lệ HTTP thành công cũng không thay thế tỷ lệ trả lời chính xác.

### 4.2. Chất lượng có thể được xác nhận muộn

Một câu trả lời hướng dẫn quy trình có thể cần người có chuyên môn đọc nguồn; trạng thái đơn hàng có thể cần so với backend; kết quả tool có thể chỉ xác nhận sau khi giao dịch hoàn tất.

Nên có các trạng thái riêng:

- `PENDING_REVIEW`: đã chọn mẫu nhưng chờ đánh giá.
- `PASS` hoặc `FAIL`: có đánh giá và bằng chứng tương ứng.
- `NOT_EVALUATED`: không thể chấm vì thiếu dữ liệu hoặc evaluator lỗi.
- `NOT_APPLICABLE`: tiêu chí không áp dụng.
- `TECHNICAL_FAILURE`: hệ thống không tạo ra câu trả lời hợp lệ để chấm.

Khi tổng hợp, báo tỷ lệ kết quả theo **mẫu có nhãn**, **số chưa chấm** và **tỷ lệ hoàn tất end-to-end**. Tránh tự động coi những ca thiếu nhãn là PASS.

## 5. Offline evaluation, online monitoring, canary và A/B testing không đồng nghĩa

Những thuật ngữ này thường xuất hiện cạnh nhau nhưng đóng vai trò khác nhau.

| Khái niệm | Ý nghĩa | Câu hỏi chính |
| --- | --- | --- |
| **Offline evaluation** | Chạy ca có nhãn trong môi trường kiểm soát | Candidate vượt baseline trên dataset không? |
| **Online monitoring** | Theo dõi tín hiệu chất lượng và vận hành của traffic thực | Có hồi quy hoặc tình huống mới xuất hiện không? |
| **Canary rollout** | Phát hành version cho một phần traffic có kiểm soát | Có nên mở rộng version mới không? |
| **A/B experiment** | Phân nhóm traffic theo thiết kế thí nghiệm và so biến thể | Thay đổi nào tạo ra chênh lệch kết quả trong điều kiện thực? |
| **Load/stress testing** | Tạo tải có kiểm soát để đo sức chịu đựng | Hệ thống đáp ứng được tải yêu cầu không? |

Canary cần online monitoring để quyết định tiếp tục hay rollback; một canary **không tự động** là A/B test đáng tin vì cách chọn người dùng có thể không ngẫu nhiên. A/B test thường cần thiết kế phân nhóm, kiểm soát hiệu ứng thời gian, xác định metric trước thí nghiệm và xử lý sai lệch mẫu.

Một câu hỏi có thể được chấm offline trước deploy và tiếp tục được đưa vào bài smoke test sau deploy. Còn traffic production thực cần dữ liệu quan sát khác vì không thể mặc định có ground truth.

### 5.1. Online evaluation có thể là một phần của monitoring

Nếu một mẫu câu trả lời production được đưa qua evaluator, đánh giá trên mẫu đó là **online evaluation hoặc production-sample evaluation**. Khi tổng hợp điểm theo thời gian, nhóm dùng kết quả ấy cho **online quality monitoring**.

Sự khác biệt quan trọng nằm ở **dữ liệu đầu vào và cách diễn giải**:

- Offline: chọn trước ca, biết chuẩn chấm và có kiểm soát cấu hình.
- Online: lấy mẫu từ request thật, dữ liệu có thể thay đổi và nhãn có thể không đầy đủ.
- Monitoring: liên tục phát hiện tín hiệu hoặc xu hướng, không nhất thiết chấm từng câu.

## 6. Vấn đề khó nhất: lấy mẫu online sao cho có ý nghĩa

Đánh giá mọi request bằng model chấm hoặc chuyên gia thường không khả thi. Khi chọn mẫu, phải hiểu mẫu đó đại diện cho ai.

### 6.1. Các chiến lược lấy mẫu

**Lấy mẫu ngẫu nhiên:** cho cơ sở theo dõi xu hướng tương đối đại diện nếu thiết kế và tỷ lệ tham gia phù hợp. Cần lưu xác suất chọn mẫu, xử lý nhóm hiếm và các trường hợp thiếu dữ liệu.

**Lấy mẫu phân tầng:** chia theo nhóm nghiệp vụ hoặc đặc điểm an toàn, chẳng hạn “RAG thường”, “không đủ nguồn”, “tool calling”, “tiếng Việt”, “câu dài”; lấy một phần từ từng nhóm để không bỏ sót ca quan trọng. Nếu lấy tỷ lệ khác nhau giữa các tầng, khi ước tính tỷ lệ chung phải cân theo quy mô lưu lượng, không lấy trung bình cộng các tầng.

**Lấy mẫu theo rủi ro:** ưu tiên case không có trích dẫn, tool lỗi, câu trả lời về chính sách hoặc có phản hồi tiêu cực. Chiến lược này tốt cho **phát hiện lỗi** nhưng có thể **ước lượng sai tỷ lệ lỗi chung** nếu không tính đến cách chọn mẫu.

**Lấy mẫu dựa vào phản hồi:** chọn những cuộc hội thoại bị báo sai, đánh giá thấp hoặc mở ticket. Hữu ích để điều tra nhưng không đại diện cho toàn bộ traffic vì người dùng không phản hồi theo cách ngẫu nhiên.

### 6.2. Ví dụ về sai lệch chọn mẫu

Giả sử production có 90% câu hỏi thường và 10% câu hỏi thiếu tài liệu. Nhóm cố ý lấy 50/50 để thấy nhiều ca thiếu nguồn; đánh giá được:

| Nhóm | Tỷ trọng traffic thực | Tỷ trọng mẫu đánh giá | Tỷ lệ PASS trong nhóm |
| --- | ---: | ---: | ---: |
| Câu hỏi thường | 90% | 50% | 95% |
| Câu thiếu nguồn | 10% | 50% | 60% |

Tỷ lệ PASS *thô của mẫu*:

\[
0{,}5\times0{,}95+0{,}5\times0{,}60=77{,}5\%.
\]

Nếu tỷ trọng traffic thực nêu trên chính xác và mẫu đại diện trong từng tầng, tỷ lệ PASS *ước tính đã cân trọng số* là:

\[
0{,}9\times0{,}95+0{,}1\times0{,}60=91{,}5\%.
\]

Cả hai số đều có mục đích: 77,5% mô tả mẫu được chọn, còn 91,5% là **ước tính trên phân bố traffic giả định** với những điều kiện thống kê phù hợp. Không nên báo số thứ hai mà giấu cách phân tầng, trọng số hoặc mức bất định của phép ước tính.

### 6.3. Phân biệt traffic drift và quality regression

Giả sử hai loại câu hỏi có tỷ lệ đạt riêng ổn định:

- Câu thường: 90% PASS.
- Câu không có nguồn: 50% PASS.

Nếu offline dataset có 90% câu thường và 10% câu thiếu nguồn, điểm tổng dự kiến là:

\[
0{,}9\times90\%+0{,}1\times50\%=86\%.
\]

Nếu production chuyển thành 50% câu thường và 50% câu thiếu nguồn, tỷ lệ tổng là:

\[
0{,}5\times90\%+0{,}5\times50\%=70\%.
\]

**Điểm tổng giảm từ 86% xuống 70% dù khả năng xử lý trong mỗi nhóm không đổi.** Đây có thể là **input distribution shift (thay đổi cơ cấu yêu cầu)** chứ chưa chắc là regression của model. Cần so điểm theo nhóm và theo phân bố chuẩn trước khi kết luận.

Chiều ngược lại cũng có thể xảy ra: điểm tổng ổn định do traffic dễ hơn, trong khi chất lượng một nhóm rủi ro cao giảm. Vì vậy phải theo dõi **cả metric tổng hợp và metric theo phân khúc**.

## 7. Tín hiệu chất lượng online đến từ đâu?

### 7.1. Kiểm tra xác định, ít tốn chi phí

Một số vi phạm có thể phát hiện tự động từ metadata:

- Model trả JSON không khớp schema đã công bố.
- Câu trả lời RAG bắt buộc có citation nhưng không có citation.
- Trích dẫn tới document ID không có trong tập kết quả được phép.
- Tool được gọi sai tên hoặc sai kiểu đối số.
- Tool bị từ chối nhưng chatbot tuyên bố thao tác đã thành công.
- Câu trả lời chứa định dạng hoặc thành phần bị cấm theo yêu cầu nghiệp vụ.

Tuy nhiên, **có citation không chứng minh citation đúng**. Không có citation trong một câu hỏi chung cũng không nhất thiết là lỗi nếu rubric không yêu cầu. Chỉ báo dựa trên quy tắc phải phù hợp loại tác vụ.

### 7.2. LLM-as-a-judge trên mẫu

Một evaluator có thể chấm:

- Relevance: nội dung có giải quyết câu hỏi không?
- Groundedness: khẳng định có được context thực sự đưa vào model hỗ trợ không?
- Completeness: các phần yêu cầu có được giải quyết đầy đủ không?
- Correct refusal: ứng dụng có thừa nhận thiếu bằng chứng trong ca tương ứng không?

LLM-as-a-judge không tự biết nguồn sự thật nào là hiện hành. Để chấm **factual correctness**, cần có nguồn tham chiếu độc lập đã được xác minh. Nếu context retrieval cũ nhưng model diễn giải đúng context cũ, groundedness có thể PASS trong khi factual correctness FAIL.

Model chấm có thể mắc lỗi, thiên lệch theo cách diễn đạt, nhạy với prompt chấm và chi phí cao. Trong hệ thống production, nên kiểm tra một mẫu đã được chuyên gia gắn nhãn để ước lượng độ nhất quán và false positive/false negative của judge.

### 7.3. Phản hồi người dùng

Các tín hiệu như đánh giá sao, “hữu ích/không hữu ích”, mở lại câu hỏi hoặc chuyển sang nhân viên hỗ trợ **có thể gợi ý vấn đề**. Không nên coi chúng là nhãn chính xác tuyệt đối:

- Người dùng có thể không hài lòng khi chatbot từ chối một yêu cầu sai.
- Nhiều người dùng không bấm phản hồi khi kết quả ổn.
- Người phản hồi thường là nhóm có cảm xúc mạnh hoặc gặp tình huống cụ thể.
- Số lượng tương tác chưa chắc tương ứng với mức chính xác sự thật.

Kết hợp feedback với review có rubric và nguồn đã xác minh giúp hiểu nguyên nhân thay vì chỉ biết mức độ hài lòng.

## 8. Theo dõi riêng RAG và tool calling khi vận hành

Trong Spring AI, pipeline có thể gồm `ChatClient`, `Advisors`, `VectorStore`, `ChatModel` và các tools. Một answer-quality metric chung không cho biết lỗi đến từ bước nào.

### 8.1. RAG: theo dõi cả truy xuất và sinh

~~~mermaid
flowchart LR
    U["User question"] --> R["Retrieval"]
    R --> D["Retrieved documents<br/>ID, version, rank"]
    D --> C["Context assembly"]
    C --> M["Model response"]
    M --> A["Answer + citations"]
    R -.-> X["Retrieval signals"]
    C -.-> X
    A -.-> Y["Answer quality sample"]
    X --> Z["Quality + traces<br/>for investigation"]
    Y --> Z
~~~

Khi có nguồn chuẩn cho một ca, có thể chấm **retrieval hit@k** hoặc **Recall@k**. Nhưng phần lớn production request thiếu nhãn “tất cả tài liệu liên quan”, nên không thể suy ra Recall@k đáng tin cho toàn traffic chỉ từ similarity scores.

Để phát hiện vấn đề khi thiếu nhãn, có thể theo dõi **chỉ báo proxy**: số tài liệu trả về, tỷ lệ truy vấn không có kết quả, tỷ lệ citation không hợp lệ, phiên bản tài liệu, tỷ lệ lỗi VectorStore, sự thay đổi độ dài context. Những chỉ báo này hữu ích để điều tra, nhưng **không đồng nghĩa với chất lượng câu trả lời**.

Khi chấm groundedness online, giữ lại tham chiếu tới **context thực sự đưa vào model**. Tài liệu retrieved nhưng bị cắt trước khi ghép prompt có thể không phải bằng chứng model đã thấy.

### 8.2. Tool calling: theo dõi quyết định và hậu điều kiện

Với một yêu cầu “Kiểm tra trạng thái đơn DH-123”, cần phân biệt:

1. **Expected tool behavior:** ứng dụng phải gọi `getOrderStatus` khi người dùng có quyền.
2. **Actual tool event:** tool nào được gọi, đối số, status, latency và kết quả.
3. **Answer quality:** model có dùng đúng kết quả trả về hay không.
4. **Security/business correctness:** quyền được xác thực ở backend, trạng thái được phép tiết lộ.
5. **Operational health:** tool timeout, retry, rate limit hay tăng độ trễ.

Nếu tool trả `403 Forbidden` nhưng model nói “đơn đang giao”, đây là lỗi nội dung và xử lý kết quả tool; HTTP endpoint bên ngoài vẫn có thể trả 200. Một trace có `tool invocation` chỉ chứng minh thao tác được gọi, **không chứng minh giao dịch có tác dụng phụ đã hoàn tất**. Với các hành động như hoàn phí, cần kiểm tra hậu điều kiện và idempotency tại backend.

## 9. Observability trong Spring AI giúp điều tra chất lượng online

Spring AI tích hợp cơ chế observation của hệ sinh thái Spring/Micrometer; tùy phiên bản, provider và cấu hình, có thể thu metrics/traces cho `ChatClient`, `ChatModel`, `VectorStore`, `Advisors` và tool calling. Spring Boot Actuator cung cấp khả năng quan sát ứng dụng, còn các registry/exporter và tracing backend đảm nhiệm lưu trữ, phân tích.

**Ba lớp dữ liệu cần dùng đúng mục đích:**

| Dữ liệu | Trả lời tốt câu hỏi | Không tự trả lời được |
| --- | --- | --- |
| Metrics | p95 latency, error rate, request count, token trends tăng/giảm ra sao? | Câu trả lời có đúng nguồn không? |
| Traces | Request chậm/hỏng ở span retrieval, model hay tool? Có retry? | Đáp án có đúng chính sách không? |
| Quality labels/evidence | Những ca đã chấm có grounded, relevant, factually correct không? | Hệ thống có đủ tài nguyên phục vụ toàn traffic không? |

### 9.1. Một trace mẫu

~~~text
POST /ask                                  2900 ms
└── ChatClient                             2700 ms
    ├── RAG advisor
    │   └── VectorStore query               450 ms
    ├── ChatModel call #1                   1100 ms
    ├── getOrderStatus tool                  250 ms
    └── ChatModel call #2                    900 ms
~~~

Span cha có thể bao gồm thời gian con; không cộng trùng các thời lượng lồng nhau. Với ứng dụng streaming, nên phân biệt **time to first token (TTFT)** và thời gian hoàn tất toàn bộ response nếu trải nghiệm người dùng phụ thuộc token đầu tiên.

### 9.2. Token và cost là tín hiệu hiệu quả, không phải điểm chất lượng

Giả sử candidate tăng retrieval `top-k` khiến input tokens tăng từ 1.200 lên 2.100 trên mỗi request, trong khi relevance gần như không đổi. Điều này gợi ý cần xem độ dài context, duplicate chunks, reranking và số lượt gọi model.

Với bảng giá giả định USD/triệu token, mô hình ước tính đơn giản:

\[
\mathrm{modelCost} =
\frac{\mathrm{inputTokens}\times \mathrm{inputPricePerMillion}}{10^6}
+
\frac{\mathrm{outputTokens}\times \mathrm{outputPricePerMillion}}{10^6}.
\]

Nếu request tiêu thụ 2.000 input tokens với giá giả định 2 USD/triệu và 500 output tokens với giá giả định 8 USD/triệu, chi phí ước tính là:

\[
(2000\times2+500\times8)/10^6=0{,}008\ \mathrm{USD}.
\]

Cần cộng mọi lần gọi model và tính thêm embedding, reranking, tool, hạ tầng, cache/retry và chi phí judge nếu có. Giá thực thay đổi theo nhà cung cấp; dữ liệu usage cũng phụ thuộc provider và cách xuất telemetry. **Cost/request thấp không đồng nghĩa cost/successful-task thấp** nếu câu trả lời sai phải xử lý lại.

### 9.3. Kết nối online quality label với trace

Một record tối thiểu có thể có:

~~~json
{
  "releaseVersion": "assistant-v2",
  "requestRef": "redacted-or-internal-reference",
  "traceId": "trace-example-7",
  "samplePolicy": "stratified-v1",
  "sampleProbability": 0.1,
  "taskGroup": "policy-rag",
  "responseStatus": "COMPLETED",
  "qualityReview": {
    "status": "FAIL",
    "metric": "groundedness",
    "rubricVersion": "policy-rubric-v1",
    "judgeVersion": "judge-v1",
    "evidenceRefs": ["safe-context-ref", "safe-answer-ref"]
  },
  "observability": {
    "totalLatencyMs": 1820,
    "inputTokens": 1600,
    "outputTokens": 120,
    "toolError": false
  }
}
~~~

Đây là **schema do ứng dụng tự thiết kế để minh họa**, không phải JSON Spring AI tự sinh. `traceId` giúp điều tra request cụ thể, còn `samplePolicy` và `sampleProbability` giúp hiểu mẫu được lấy ra sao. Tránh sử dụng dữ liệu cá nhân hoặc nguyên văn prompt làm nhãn metric.

## 10. Mẫu số, độ trễ nhãn và độ không chắc chắn

Một dashboard theo dõi chất lượng phải ghi rõ **chỉ số tính trên tập nào**.

Ví dụ:

- 10.000 request hợp lệ trong ngày.
- 9.900 request hoàn tất về kỹ thuật.
- 300 completion được chọn để chấm theo chính sách mẫu.
- 240 completion đã được chấm.
- 216 trong số đã chấm đạt rubric.

Có ít nhất ba tỷ lệ khác nhau:

\[
\mathrm{TechnicalCompletion}=\frac{9900}{10000}=99\%.
\]

\[
\mathrm{ReviewedQualityPassRate}=\frac{216}{240}=90\%.
\]

\[
\mathrm{ReviewCompletion}=\frac{240}{300}=80\%.
\]

Không nên lấy 90% nhân với 99% rồi tự coi đó là “tỷ lệ nhiệm vụ thực sự đúng” khi không có cơ sở chứng minh các mẫu và trạng thái độc lập/đại diện. Muốn tính end-to-end task success trên toàn traffic, cần thiết kế đo có đủ nhãn hoặc phương pháp ước lượng và giả định rõ ràng.

### 10.1. Số mẫu nhỏ tạo biến động lớn

Nếu mẫu có 20 case, chỉ một ca đổi verdict đã làm pass rate thay đổi 5 điểm phần trăm. Chênh lệch 95% so với 90% trên cỡ mẫu này chưa đủ để mặc định đã có sự suy giảm chắc chắn.

Báo cáo nên kèm:

- `n` của từng nhóm và khoảng thời gian.
- Cách chọn mẫu, tỷ lệ được chấm, lý do thiếu nhãn.
- Khoảng tin cậy hoặc ước lượng bất định khi so sánh tỷ lệ.
- Phiên bản rubric/judge, độ nhất quán của đánh giá.
- Thay đổi cơ cấu traffic qua thời gian.

Một cảnh báo cần được thiết kế theo mức rủi ro: lỗi phân quyền hoặc tool có tác dụng phụ có thể cần phản ứng từ **một ca xác minh đáng tin**, trong khi dao động nhỏ của pass rate ngữ nghĩa thường cần thêm mẫu.

### 10.2. Chấm lại bằng bộ judge mới

Nếu cùng answer và context nhưng đổi từ `judge-v1` sang `judge-v2`, quality score có thể thay đổi dù ứng dụng không đổi. Phải lưu `judgeVersion` và, khi cần, **chấm lại cùng một tập evidence bằng cả hai bộ chấm** để ước lượng tác động phương pháp.

Đừng quy mọi thay đổi điểm cho prompt/model khi dataset, nguồn chuẩn, rubric hoặc judge cũng thay đổi.

## 11. Quy trình triển khai: offline gate → canary → production monitoring

Đây là cách kết nối hai lớp đo:

~~~mermaid
flowchart TD
    D["Candidate prompt/model/pipeline"] --> O["Offline eval<br/>fixed dataset + rubric"]
    O --> G{"Qua quality + functional<br/>+ operational gates?"}
    G -- "Không" --> F["Phân tích case FAIL<br/>và sửa"]
    F --> O
    G -- "Có" --> C["Canary rollout"]
    C --> M["Online signals<br/>metrics / traces / samples"]
    M --> H{"Có lỗi nghiêm trọng<br/>hoặc hồi quy đáng tin?"}
    H -- "Có" --> R["Dừng rollout / rollback<br/>+ điều tra"]
    H -- "Không" --> P["Mở rộng traffic có kiểm soát"]
    P --> M
    R --> N["Ca lỗi đã xác minh<br/>bổ sung regression"]
    N --> O
~~~

### 11.1. Offline release gate

Một bộ gate **minh họa**, không phải chuẩn bắt buộc của Spring AI:

~~~yaml
candidate: assistant-v2
offlineGates:
  datasetVersion: support-eval-v3
  rubricVersion: support-rubric-v2
  functional:
    authorizationTests: must-pass
    toolContractTests: must-pass
  aiQuality:
    groundednessPassRate: ">= 0.95"
    factualCorrectnessPassRate: ">= 0.98"
    criticalNoEvidenceCases: must-pass
  operations:
    p95LatencyMs: "<= 2500"
    modelCostUsdPerRequest: "<= 0.01"
~~~

Trước deploy, chọn ngưỡng dựa trên yêu cầu thực tế và cỡ mẫu đáng tin. Đặc biệt, không gộp điểm chất lượng tốt với lỗi phân quyền trong cùng một điểm bình quân: sai quyền có thể phải chặn ngay cả khi các metric khác đẹp.

### 11.2. Canary monitoring

Trong canary, theo dõi riêng từng version:

- Error rate, tool timeout, retry, rate limit, p95/p99 latency.
- Input/output tokens và chi phí ước tính theo nhóm tác vụ.
- Quality pass theo các mẫu tương đương hoặc có điều chỉnh phân bố.
- Các ca nguy cơ cao: sai nguồn chính sách, sai quyền tool, bịa trạng thái giao dịch.
- Dấu hiệu traffic shift và phần trăm nhãn chưa sẵn sàng.

**Canary ổn định về vận hành chưa đủ để chứng minh quality đạt.** Nếu chưa đủ mẫu chất lượng cho kết luận, có thể giữ traffic ở mức kiểm soát và tiếp tục điều tra theo quy trình được xác định; không cần bịa kết luận “đạt” khi thiếu dữ liệu.

### 11.3. A/B để kiểm tra tác động thật

Khi muốn biết prompt B có cải thiện tác vụ so với A ở production hay không, một thí nghiệm A/B có thể phân nhóm traffic một cách có thiết kế. Cần:

1. Xác định trước metric chính, guardrail và thời gian thí nghiệm.
2. Phân nhóm phù hợp để tránh một user nhận nhiều phiên bản gây nhiễu nếu tính nhất quán hội thoại quan trọng.
3. Kiểm tra hai nhánh có loại yêu cầu và quyền truy xuất tương đương.
4. Theo dõi kỹ thuật và chất lượng trên mẫu được gắn nhãn theo cùng rubric.
5. Dừng hoặc rollback theo điều kiện rủi ro; không đợi “đủ thống kê” trước lỗi nghiêm trọng.
6. Phân tích kích thước hiệu ứng và bất định, không chỉ so phần trăm thô.

Không phải mọi thay đổi đều thích hợp chạy A/B trên người dùng thật, nhất là thay đổi liên quan quyền hoặc hành động không thể đảo ngược. Những trường hợp đó phải được đảm bảo bằng kiểm thử xác định và cơ chế bảo vệ backend trước.

## 12. Kịch bản điều tra: offline đạt nhưng production giảm chất lượng

Một chatbot trả lời chính sách có baseline offline đạt groundedness 96% trên dataset `policy-eval-v1`. Sau khi deploy `assistant-v2`, hệ thống giám sát thấy groundedness của mẫu đã chấm giảm.

**Tình huống giả định:**

| Tín hiệu | Trước rollout | Sau rollout |
| --- | ---: | ---: |
| Offline groundedness | 96% | 97% |
| Online groundedness trên mẫu đã chấm | 94% | 82% |
| p95 latency | 2,0 s | 2,1 s |
| Tỷ lệ truy xuất không có kết quả | 2% | 11% |
| Tỷ lệ câu hỏi về chính sách vừa cập nhật | 5% | 30% |

Điểm offline nhích lên nhưng production giảm mạnh. Có ít nhất ba giả thuyết:

1. **Traffic drift:** người dùng đang hỏi nhiều hơn về chính sách mới, vốn không có trong dataset cũ.
2. **Corpus/index stale:** VectorStore chưa chứa bản chính sách hiện hành hoặc bộ lọc loại mất tài liệu.
3. **Sai lệch lấy mẫu/chấm:** thay chính sách sampling, rubric hay evaluator; những mẫu được chấm sau rollout có thể khó hơn hoặc khác nhóm.

### 12.1. Các bước kiểm chứng

**Bước 1 — Xác minh tín hiệu.** Kiểm tra số mẫu, cách chọn mẫu, tỷ lệ nhãn chậm, cùng `judgeVersion` và rubric hay không. Chia nhỏ theo nhóm câu hỏi; phân biệt giảm ở mọi nhóm với thay đổi tỷ trọng nhóm.

**Bước 2 — So phiên bản dữ liệu.** Kiểm tra thời điểm cập nhật chính sách, `corpusVersion`, `indexVersion` và metadata hiệu lực của document. Nếu chính sách mới chưa được index, đây là hướng điều tra ưu tiên.

**Bước 3 — Theo trace của case lỗi.** Dùng `traceId` tìm request cụ thể, đối chiếu documents thực tế trả về, prompt được ghép (trong phạm vi an toàn cho phép), lời gọi model/tool và status. Trace không cần chứa raw nội dung nhạy cảm; có thể chứa tham chiếu tới evidence store phân quyền.

**Bước 4 — Tạo case hồi quy mới.** Chuyên gia xác minh câu hỏi, nguồn chuẩn, expected behavior. Thêm case đã xử lý dữ liệu riêng tư vào regression set và chạy candidate fix.

**Bước 5 — Đánh giá toàn bộ ảnh hưởng.** Sửa index/filter có thể tăng hit@k nhưng làm query chậm. Chạy offline eval, kiểm thử quyền tài liệu, đo latency/cost rồi phát hành có kiểm soát.

Nếu nguồn và cách chấm không đổi, còn tỷ lệ truy xuất không có kết quả tăng rõ ở nhóm chính sách mới, giả thuyết lỗi corpus/index có thêm bằng chứng. Tuy vậy cần xác minh bằng chính những ca thất bại; **không kết luận nguyên nhân chỉ từ một tương quan trên dashboard**.

## 13. Bản thiết kế triển khai trong Spring AI

### 13.1. Phân tách hai pipeline

**Offline runner** có thể tái sử dụng chính service của ứng dụng Spring AI nhưng chạy trên dataset có kiểm soát:

~~~text
for each case in versionedDataset:
    configure isolated test context + fixed tool fixtures
    execute application pipeline
    capture answer, retrievedDocs, toolEvents, traceRef
    evaluate deterministic assertions
    evaluate relevance / groundedness / factual correctness
    save verdict + rubricVersion + evidenceRefs
aggregate by case group and compare with baseline
~~~

**Production monitoring pipeline** dùng quan sát và lấy mẫu có quy định:

~~~text
for each eligible production request:
    run application and emit safe technical telemetry
    if selected by configured sample policy:
        create redacted review record + evidence references
        queue evaluation or human review where permitted
    store review result with version and review status

periodically:
    aggregate labeled-sample quality by segment and release
    report pending/unlabeled counts and sampling method
    correlate shifts with errors, traces, latency and cost
    investigate confirmed failures and update regression set
~~~

Các đoạn trên là **pseudocode mô tả thiết kế**, không phải API được Spring AI cung cấp nguyên dạng.

### 13.2. Một ví dụ Java đo duration riêng của ứng dụng

Với Spring Boot, ta có thể thêm metric riêng bên cạnh metrics framework đã cung cấp, miễn tránh đếm trùng khi tổng hợp và giữ tag có cardinality hữu hạn.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

@Service
public class SupportAssistant {

    private final ChatClient chatClient;
    private final MeterRegistry registry;

    public SupportAssistant(ChatClient chatClient, MeterRegistry registry) {
        this.chatClient = chatClient;
        this.registry = registry;
    }

    public String answer(String question) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return chatClient.prompt()
                    .user(question)
                    .call()
                    .content();
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(Timer.builder("app.ai.answer.duration")
                    .description("End-to-end assistant duration")
                    .tag("operation", "answer")
                    .tag("outcome", outcome)
                    .register(registry));
        }
    }
}
~~~

Đoạn mã minh họa timer của **toàn phương thức**. Nó không đo chất lượng câu trả lời, không lưu dữ liệu RAG và không tự tạo dataset. Nếu model trả lời sai nhưng không ném exception, `outcome=success` là **thành công về mặt kỹ thuật của lời gọi**, không phải chất lượng PASS.

Bản production nên áp dụng giới hạn input, timeout, xử lý ngoại lệ, phân quyền và các chính sách nghiệp vụ phù hợp. Spring AI và Actuator cũng có observations/metrics sẵn; kiểm tra tên metric và cấu hình ở phiên bản dự án để tránh tạo dashboard trùng hoặc diễn giải sai.

### 13.3. Kết nối điểm chấm với metadata

Một record báo cáo offline:

~~~json
{
  "runId": "offline-candidate-v2",
  "caseId": "REFUND-PRO-001",
  "attemptId": "offline-candidate-v2-REFUND-PRO-001-1",
  "datasetVersion": "refund-eval-v1",
  "promptVersion": "prompt-v4",
  "modelVersion": "model-candidate",
  "pipelineVersion": "rag-v2",
  "rubricVersion": "refund-rubric-v1",
  "evaluation": {
    "relevance": "PASS",
    "groundedness": "FAIL",
    "factualCorrectness": "FAIL"
  },
  "evidence": {
    "retrievedDocumentIds": ["policy-v2#refund"],
    "traceId": "test-trace-001"
  }
}
~~~

Một record production có thể không có reference answer được xác minh tại thời điểm request. Thay vì tự điền `PASS`, hãy lưu `PENDING_REVIEW` hoặc `NOT_EVALUATED` kèm tình trạng và lý do, sau đó bổ sung kết quả khi có cơ sở.

**Khóa liên kết là quan trọng:** `caseId` chỉ định ca offline; `attemptId` chỉ định một lần chạy; `traceId` trỏ tới dấu vết thực thi. Không dùng `traceId` để thay cho nhãn chất lượng hoặc kỳ vọng từ dataset.

## 14. Thiết kế dashboard chất lượng có trách nhiệm

Một dashboard hữu ích nên hiển thị nhiều chiều nhưng phân biệt rõ nguồn đo:

| Panel | Dữ liệu | Cách diễn giải |
| --- | --- | --- |
| Request count / technical success | Tất cả request hợp lệ trong phạm vi đo | Nền tảng phục vụ và lỗi |
| p50/p95/p99 latency, TTFT nếu streaming | Metrics/traces có ranh giới đo rõ | Trải nghiệm tốc độ và nhóm chậm |
| Token usage / cost per request | Provider usage, mô hình giá | Hiệu quả tài nguyên và biến động |
| Tool errors/denials | Trạng thái tool/backend | Lỗi tích hợp và rủi ro quyền |
| Citation/retrieval proxies | IDs, metadata tài liệu, events | Chỉ báo điều tra, không trực tiếp là factual correctness |
| Quality pass trên mẫu có nhãn | Offline/online evaluator + review | Chất lượng trong phạm vi tập được chấm |
| Review coverage / pending | Số đã chọn, đã chấm, chưa chấm | Độ đầy đủ và độ trễ của nhãn |
| Quality theo nhóm và release | Kết quả phân tầng | Phân biệt regression với traffic shift |
| Ca nghiêm trọng đã xác minh | Case records và evidence | Ưu tiên xử lý, cập nhật regression |

Nên hiển thị phiên bản prompt/model/pipeline/corpus, thời điểm deploy và thay đổi cách sampling/judge trên trục thời gian khi có thể. Một đồ thị pass rate không gắn thông tin đổi rubric rất dễ dẫn tới kết luận sai.

### 14.1. Cảnh báo tự động nên phản ánh tính chất tín hiệu

- **Lỗi kỹ thuật rõ ràng:** error rate hoặc timeout tăng mạnh có thể kích hoạt cảnh báo tức thời.
- **Lỗi quyền/tool nghiêm trọng đã xác minh:** xử lý ngay theo mức độ ảnh hưởng, ngay cả khi số mẫu nhỏ.
- **Chất lượng trên mẫu:** cân nhắc cỡ mẫu tối thiểu, sự khác biệt phân nhóm, thời gian chờ nhãn và sai số judge.
- **Drift đầu vào:** biến động tỷ trọng intent hoặc tỷ lệ câu hỏi không có nguồn có thể là cảnh báo điều tra, chưa phải kết luận model suy giảm.

Khi hệ thống không đủ dữ liệu, hiển thị **insufficient evidence** thay vì tô trạng thái “healthy” bằng giả định.

## 15. Quyền riêng tư và an toàn khi đưa dữ liệu production vào evaluation

Lấy hội thoại thực để chấm có thể phát sinh rủi ro về thông tin cá nhân, dữ liệu nội bộ, kết quả tool và bản quyền tài liệu. Những nguyên tắc cần thiết:

1. **Chỉ thu dữ liệu phục vụ mục tiêu đo.** Metadata thông thường đủ cho latency và error; không cần raw prompt.
2. **Che/loại dữ liệu định danh.** Đặc biệt với ID đơn hàng, email, thông tin tài chính và dữ liệu nhạy cảm.
3. **Giới hạn quyền đọc evidence.** Reviewer chỉ xem nội dung cần thiết, có audit và thời hạn lưu.
4. **Tách dữ liệu kiểm thử khỏi production.** Với tool có side effect, dùng sandbox/test double để tái hiện lỗi khi có thể.
5. **Quản lý data retention và việc gửi dữ liệu cho external judge.** Đánh giá với provider khác có thể là một luồng chia sẻ dữ liệu riêng cần kiểm soát.
6. **Không bật log raw prompt/completion bừa bãi.** Dùng trace ID và tham chiếu an toàn, chỉ bật thu nội dung trong tình huống được quản trị.

Nếu vì quyền riêng tư không thể thu bằng chứng nội dung, phải nói rõ metric nào **không thể đánh giá**; tránh suy diễn độ đúng từ metadata hoạt động.

## 16. Những sai lầm thường gặp

**Sai lầm 1 — Offline PASS nghĩa là production chắc chắn tốt.** Dataset hữu hạn không thể đại diện mọi request mới, tải thật và nguồn dữ liệu đổi theo thời gian.

**Sai lầm 2 — HTTP 200 hoặc p95 đẹp là chất lượng cao.** Đây là thông tin sức khỏe kỹ thuật, không chứng minh câu trả lời có căn cứ.

**Sai lầm 3 — Chấm mọi request như nhau nhưng bỏ qua phân bố.** Một nhóm ca thiếu nguồn ít gặp có thể chứa hầu hết lỗi quan trọng; cần phân nhóm và cách lấy mẫu phù hợp.

**Sai lầm 4 — Tỷ lệ PASS trên mẫu có nhãn được gọi là tỷ lệ PASS toàn production.** Phải báo mẫu số và cơ chế lấy mẫu, tỷ lệ chưa được chấm và sai lệch có thể có.

**Sai lầm 5 — Judge PASS là ground truth.** LLM-as-a-judge có thể sai; dùng nhãn chuyên gia/kiểm tra xác định ở ca quan trọng và theo dõi judge version.

**Sai lầm 6 — Dùng tài liệu chuẩn làm tài liệu truy xuất khi chấm groundedness.** Việc này che giấu lỗi retrieval, tạo điểm số quá tốt so với pipeline thực.

**Sai lầm 7 — Điểm online giảm đồng nghĩa model bị thoái hóa.** Có thể do traffic shift, corpus cũ, thay rubric, lỗi bộ chấm hoặc thời gian chờ nhãn.

**Sai lầm 8 — Chỉ tối ưu relevance.** RAG còn cần factual correctness, groundedness, citation và quyền tài liệu; tool calling còn cần hành vi và hậu điều kiện đúng.

**Sai lầm 9 — Chỉ so chi phí model trên request thành công.** Retry, token, embedding, tool, judge và tỷ lệ phải xử lý lại đều ảnh hưởng chi phí thực.

**Sai lầm 10 — Đưa nguyên văn dữ liệu nhạy cảm vào trace/metric.** Không nên dùng prompt hay user ID làm metric tag; evidence cần chính sách bảo vệ riêng.

## 17. Bài thực hành: xây dựng vòng lặp offline–online cho chatbot chính sách

**Bối cảnh:** Một ứng dụng Spring AI tra cứu chính sách giả định từ VectorStore, trả lời có citation và sử dụng tool `getOrderStatus` để đọc thông tin đơn hàng có quyền. Mục tiêu là hiểu cách một thay đổi prompt hoặc retrieval xuất hiện trong offline eval và tiếp tục được theo dõi trong production giả lập.

### Phần A — Chuẩn bị offline dataset

Tạo 20 ca kiểm thử:

- 8 ca có nguồn rõ ràng.
- 4 ca nhiều điều kiện hoặc nguồn mâu thuẫn.
- 4 ca không có đủ dữ liệu, cần từ chối suy đoán.
- 4 ca phải gọi tool, gồm một ca timeout và một ca truy cập trái quyền.

Mỗi ca cần `caseId`, source/expected facts, expected tool behavior và rubric. Chạy `baseline-v1` rồi `candidate-v2` trên cùng dataset. Lưu câu trả lời, retrieved document IDs, tool events, verdict và trace ID.

### Phần B — Tạo tín hiệu production giả lập

Tạo 200 request ở hai nhóm: hỏi chính sách bình thường và hỏi những ngoại lệ chưa có nguồn. Gắn `releaseVersion`. Cho phép lỗi/độ trễ giả lập có kiểm soát; **không dùng dữ liệu khách hàng thật**.

Lấy mẫu 40 request để chấm, trong đó cố ý chọn nhiều ca rủi ro để quan sát lỗi. Lưu cả `samplePolicy` và tỷ trọng của từng nhóm trong traffic. Một số ca giữ trạng thái `PENDING_REVIEW` để thực hành cách tính mẫu số.

### Phần C — Phân tích chất lượng và vận hành

Xây báo cáo:

| Câu hỏi | Bằng chứng cần dùng |
| --- | --- |
| Candidate vượt baseline trên bộ ca cố định không? | PASS/FAIL theo case và rubric, regression |
| Production có bị sai nhiều ở nhóm thiếu nguồn không? | Quality labels theo phân tầng |
| Điểm tổng giảm do traffic đổi hay chất lượng trong nhóm giảm? | Tỷ trọng nhóm và PASS rate từng nhóm |
| Request chậm ở bước nào? | Traces retrieval/model/tool |
| Chi phí có tăng? | Usage, số lần gọi model, giá áp dụng |
| Tool nào gây lỗi? | Tool events và backend status |
| Có đủ cơ sở để khẳng định chất lượng production? | Cỡ mẫu, nhãn chờ, cách sampling và độ bất định |

### Phần D — Tạo ca hồi quy từ sự cố

Chọn một request online có verdict FAIL đã được xác minh. Loại dữ liệu nhạy cảm, xác nhận nguồn đúng và đưa nó vào regression set. Sửa một yếu tố (ví dụ bộ lọc tài liệu còn hiệu lực), chạy lại và xem candidate có xử lý được lỗi mà không làm tăng latency quá ngưỡng hay không.

**Tiêu chí hoàn thành:** báo cáo phân biệt rõ kết quả trên dataset offline và kết quả trên mẫu traffic production; nêu được tình trạng chưa chấm, tỷ trọng nhóm, phiên bản cấu hình và ít nhất một trace/evidence link phục vụ giải thích lỗi.

### Câu hỏi tự kiểm tra

1. Vì sao offline dataset đạt 100% vẫn không chứng minh tỷ lệ đúng 100% trong production?
2. Một chatbot có error rate 0,1% nhưng trả lời sai 20% câu hỏi đã được chuyên gia xác minh. Nên báo hai kết quả ấy thế nào?
3. Khi tăng `top-k`, recall offline tăng nhưng p95 latency và input tokens online cũng tăng. Cần dựa vào gì để quyết định giữ phiên bản mới?
4. Nếu những người bấm “không hài lòng” chủ yếu đến từ một nhóm khó, tỷ lệ lỗi trên các phản hồi đó có đại diện cho toàn bộ traffic không?
5. Vì sao cần ghi `samplePolicy`, `rubricVersion` và `judgeVersion` khi xem biểu đồ quality theo thời gian?
6. Sự khác nhau giữa một quality regression và traffic distribution shift là gì?
7. Có thể chấm factual correctness chỉ dựa trên một trace báo “VectorStore SUCCESS” không?
8. Một tool hoàn phí trả `SUCCESS` nhưng backend chưa hoàn tất giao dịch. Cần thêm bằng chứng nào?
9. Trong 300 ca được lấy mẫu chỉ 240 ca đã chấm, nên công bố tỷ lệ chất lượng với mẫu số nào? Cần báo thêm gì?
10. Khi không được phép lưu raw prompt, có thể điều tra độ trễ và tool errors bằng dữ liệu nào?

## 18. Kết luận

**Offline evaluation** cung cấp một môi trường kiểm soát để chấm chất lượng, so sánh prompt/model/pipeline và ngăn lỗi hồi quy bằng dataset có phiên bản. **Online quality monitoring** quan sát trải nghiệm thật qua thời gian, phát hiện tình huống mới, thay đổi phân bố yêu cầu và các vấn đề về chất lượng, lỗi, độ trễ hoặc chi phí.

Hai cách tiếp cận cần liên kết bằng **rubric, nhãn, phiên bản cấu hình, evidence và trace ID**. Kết quả online đáng tin sau khi được xác minh trở thành ca hồi quy offline; thay đổi qua offline gate được theo dõi tiếp trong canary và production. Đó là vòng phản hồi giúp cải thiện Spring AI dựa trên bằng chứng thay vì chỉ một điểm số hoặc một vài lời đáp có vẻ hay.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html)
