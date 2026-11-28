# Chọn counter, timer, distribution summary và gauge

Một ứng dụng Spring AI có thể trả lời chính xác nhưng quá chậm, chọn đúng công cụ nhưng gọi lặp nhiều lần, hoặc tạo câu trả lời RAG có vẻ phù hợp nhưng thiếu bằng chứng từ tài liệu. Khi triển khai đánh giá chất lượng, ta không thể nhìn vào một chỉ số duy nhất như “số request thành công” để biết nguyên nhân. Cần chọn đúng **loại metric**, **đơn vị**, **điểm quan sát** và **mẫu số** cho từng câu hỏi.

Chẳng hạn, “bao nhiêu lần đánh giá thất bại?” cần một phép **đếm sự kiện**; “p95 thời gian gọi công cụ là bao nhiêu?” cần một phép **đo thời lượng**; “mỗi lượt RAG truy xuất bao nhiêu tài liệu?” cần một phép **quan sát phân bố kích thước**; còn “hiện có bao nhiêu tác vụ đang xử lý?” cần một phép **đọc trạng thái tại thời điểm quan sát**. Bốn nhu cầu đó tương ứng với **counter**, **timer**, **distribution summary** và **gauge** của Micrometer.

Bài này thuộc chương **Thiết kế metric** trong module **SPRING_AI_EVALUATION_OBSERVABILITY**. Nội dung tập trung vào cách dùng metric để đánh giá tập dữ liệu, relevance, fact checking, luồng RAG và tool calling; đồng thời nối số liệu với traces, chi phí và độ trễ để phát hiện suy giảm chất lượng giữa các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn đúng loại **Counter**, **Timer**, **DistributionSummary** hoặc **Gauge** từ ý nghĩa của dữ liệu cần đo.
2. Giải thích vì sao counter chỉ tăng, timer đo thời lượng và có số lần, summary đo phân bố giá trị, còn gauge phản ánh trạng thái tức thời.
3. Thiết kế tên metric, đơn vị và tập tag có cardinality hữu hạn, không đưa dữ liệu nhạy cảm hoặc ID riêng lẻ vào nhãn.
4. Ghi nhận kết quả đánh giá Spring AI theo ca, đo độ trễ tool/RAG, lượng token, số tài liệu truy xuất và số tác vụ đang xử lý.
5. Dùng histogram, percentile, tỷ lệ và mẫu số đúng để phân tích chất lượng và p50/p95.
6. Viết một lớp Java dùng **Micrometer** để phát sinh bốn loại meter, tích hợp ở ranh giới quan sát của ứng dụng Spring AI.
7. Kết hợp metrics với traces, logs và oracle để giải thích lỗi hồi quy mà không suy diễn quá mức từ số liệu tổng hợp.

## 2. Bốn loại meter trả lời bốn câu hỏi khác nhau

| Loại meter | Câu hỏi điển hình | Giá trị đầu vào | Đặc điểm |
| --- | --- | --- | --- |
| **Counter** | Có bao nhiêu sự kiện xảy ra? | Lần tăng dương, thường là 1 | Chỉ tăng trong vòng đời meter; khi process restart có thể reset |
| **Timer** | Mỗi thao tác mất bao lâu? | Một khoảng thời gian không âm | Theo dõi số mẫu và tổng thời lượng; có thể cấu hình histogram/percentile |
| **DistributionSummary** | Phân bố kích thước/điểm số là gì? | Một giá trị số không âm | Theo dõi count, total amount, max tùy registry và cấu hình |
| **Gauge** | Hiện tại có bao nhiêu hoặc trạng thái tức thời là gì? | Giá trị đọc từ đối tượng đang thay đổi | Có thể tăng/giảm; chỉ quan sát ở thời điểm scrape/poll |

Ví dụ tương ứng trong một ứng dụng RAG:

| Sự kiện hoặc dữ liệu | Loại phù hợp | Tên metric gợi ý |
| --- | --- | --- |
| Số ca đánh giá được phân loại PASS, FAIL, INCONCLUSIVE | Counter gắn tag verdict | ai.eval.case.completed |
| Thời gian một lời gọi tool thực thi | Timer | ai.tool.execution.duration |
| Số đoạn/tài liệu trả về cho mỗi lần retrieval | DistributionSummary | ai.rag.documents.retrieved |
| Số truy vấn RAG đang xử lý tại thời điểm đọc | Gauge | ai.rag.inflight |
| Số token đầu vào mỗi lượt model | DistributionSummary | ai.model.input.tokens.per.request |
| Số lỗi backend đã xảy ra | Counter với error_class | ai.tool.execution.errors |
| Thời gian end-to-end đến câu trả lời | Timer | ai.request.duration |
| Điểm relevance của mỗi mẫu được chấm, trong khoảng 0–1 | DistributionSummary | ai.eval.relevance.score |
| Số tác vụ đang đợi trong hàng đợi đánh giá | Gauge | ai.eval.queue.depth |

**Tên trong bảng là đề xuất của hệ thống đánh giá**, không phải danh sách meter mặc định mà Spring AI bắt buộc phát ra. Khi tích hợp, cần kiểm tra những meter framework đã có để tránh ghi trùng.

### Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    A["Cần đo một đặc tính"] --> B{"Đó là trạng thái hiện tại?"}
    B -->|Có| G["Gauge: queue depth, in-flight"]
    B -->|Không| C{"Đó là thời gian thực thi?"}
    C -->|Có| T["Timer: model/tool/RAG latency"]
    C -->|Không| D{"Đó là số lần sự kiện xảy ra?"}
    D -->|Có| E["Counter: PASS/FAIL, errors, retries"]
    D -->|Không| F{"Đó là giá trị có phân bố theo mẫu?"}
    F -->|Có| S["DistributionSummary: token, số tài liệu, score"]
    F -->|Không| H["Định nghĩa lại đại lượng và đơn vị"]
~~~

Nếu muốn biết cả số lần, độ lớn và thời gian của một hành động, bạn có thể cần **nhiều góc nhìn**, nhưng không nên tạo các metric trùng chức năng nếu một meter đã cung cấp dữ liệu đó.

## 3. Counter — đếm các sự kiện đã xảy ra

**Counter** phù hợp với một sự kiện rời rạc có tính tích lũy, ví dụ:

- Một ca trong tập đánh giá đã được chấm PASS.
- Một ca được chấm FAIL do sai fact checking.
- Một tool call đã thất bại vì backend timeout.
- Một hành động bị từ chối do thiếu quyền.
- Một retry được thực hiện.

Counter có thể tăng thêm 1 hoặc một lượng dương. Không dùng nó để biểu diễn “hiện tại đang có 3 yêu cầu chờ”, vì trạng thái đó có thể giảm.

### 3.1. Dùng một metric với tag trạng thái

Thay vì tạo ba tên metric tách biệt, có thể dùng:

~~~text
ai.eval.case.completed{case_type="rag", verdict="pass"}          +1
ai.eval.case.completed{case_type="rag", verdict="fail"}          +1
ai.eval.case.completed{case_type="rag", verdict="inconclusive"}  +1
~~~

Với một bộ ca đã xác định, chỉ được tăng **một verdict cho mỗi lần chấm cuối cùng**. Nếu cùng một ca bị evaluator chấm lại, cần quyết định đó là **một lần chạy mới** hay **cập nhật kết quả cũ**; counter không có cơ chế xóa một sự kiện đã đếm.

Nếu cần sửa nhãn hậu kiểm cho một lần đánh giá cũ, nên lưu kết quả chuẩn ở bảng dữ liệu có thể truy vấn và **tái tổng hợp báo cáo**, thay vì âm thầm trừ counter. Counter dùng để theo dõi luồng sự kiện thời gian thực, không phải cơ sở dữ liệu có thể chỉnh sửa lịch sử.

### 3.2. Phân biệt count và rate

Counter tích lũy cho biết số sự kiện từ khi tiến trình/meter khởi tạo. Khi cần xem **tốc độ trong 5 phút**, hệ thống truy vấn metrics sẽ tính rate/increase trên một khoảng thời gian và xử lý việc reset counter.

Ví dụ, tổng số PASS sau 2 giờ không tự cho biết hệ thống vừa suy giảm trong 5 phút gần đây. So sánh PASS/FAIL theo cửa sổ thời gian và **cùng nhóm tác vụ** sẽ hữu ích hơn.

### 3.3. Không đếm trùng một hành động

Một Timer vốn đã ghi số mẫu hoàn tất. Nếu chỉ muốn biết “bao nhiêu lần tool hoàn tất” và “mất bao lâu”, Timer có thể đủ. Chỉ tạo Counter riêng nếu cần một **ngữ nghĩa nghiệp vụ khác**, ví dụ:

- Số lần model **đề nghị** tool — không bằng số lần handler thực thi.
- Số thao tác backend **được tiếp nhận** — không bằng số lần tool gọi.
- Số tác động **hoàn tất và được xác minh** — không bằng số HTTP 200.

Mỗi counter phải có **điểm tăng rõ ràng** để tránh double-counting do retry, xử lý song song hoặc instrumentation lặp.

## 4. Timer — đo thời gian và phân bố độ trễ

**Timer** được dùng để ghi thời lượng của một thao tác: một lần gọi model, một lần thực thi công cụ, một lượt retrieval, một vòng đánh giá hoặc thời gian trả lời end-to-end. Một Timer thường cung cấp **số lần quan sát**, **tổng thời lượng**, cùng các thống kê và histogram được cấu hình, tùy backend.

Ví dụ:

~~~text
Lời gọi tool search_internal_policy:
  duration = 120 ms
Lời gọi tool get_order_status:
  duration = 45 ms
Lời gọi model tổng hợp câu trả lời:
  duration = 800 ms
End-to-end:
  duration = 1090 ms
~~~

Không cộng máy móc 120 + 45 + 800 để cho ra end-to-end nếu có xử lý song song, network wait, memory loading hoặc thời gian chờ khác. Hãy **đo mỗi ranh giới bằng đồng hồ phù hợp**.

### 4.1. Chọn điểm bắt đầu và kết thúc

| Loại độ trễ | Bắt đầu | Kết thúc |
| --- | --- | --- |
| Model request latency | Gửi request đến model/provider | Nhận kết quả cuối của request theo hợp đồng |
| Tool execution latency | Dispatcher bắt đầu thực thi tool | Handler/backend trả kết quả hoặc lỗi |
| Retrieval latency | Bắt đầu truy xuất | Nhận xong danh sách tài liệu |
| Answer latency | Nhận yêu cầu người dùng | Phát xong phản hồi người dùng |
| Business completion latency | Backend chấp nhận yêu cầu nghiệp vụ | Trạng thái nghiệp vụ được xác minh hoàn tất |
| Evaluation latency | Bắt đầu chạy/chấm một ca | Ghi xong verdict của ca |

Đặc biệt với streaming, **time to first token** và **time to full response** khác nhau. Với tác vụ có hàng đợi, **ACCEPTED** và **COMPLETED** cũng khác nhau. Tên metric phải phản ánh ranh giới đo.

### 4.2. Đo cả trường hợp lỗi

Nếu chỉ gọi Timer khi thành công, p95 có thể trông rất đẹp vì những ca timeout chậm nhất bị loại khỏi phép đo. Cần ghi thời lượng trong nhánh **finally** và dùng một tập tag outcome được kiểm soát:

~~~text
ai.tool.execution.duration{tool_family="retrieval", outcome="success"}
ai.tool.execution.duration{tool_family="retrieval", outcome="error"}
ai.tool.execution.duration{tool_family="retrieval", outcome="timeout"}
~~~

Nếu thời gian bị hủy và không có sự kiện kết thúc, cần có chính sách riêng: ghi duration đến thời điểm hủy với nhãn **cancelled**, hoặc đánh dấu thiếu mẫu. Không tự biến một request treo không quan sát được thành mẫu 0 ms.

### 4.3. Trung bình, p50 và p95 trả lời các câu hỏi khác nhau

- **Mean latency:** tổng thời lượng / số mẫu; nhạy với ngoại lệ và đuôi dài.
- **p50:** khoảng giữa của phân bố; mô tả ca điển hình.
- **p95:** 95% mẫu có thời lượng không vượt quá mức đó (theo cách ước lượng percentile được cấu hình); phản ánh phần đuôi chậm.
- **Max:** thời lượng lớn nhất quan sát trong cửa sổ thống kê phù hợp; không mặc định là cực đại mọi thời đại.

Ví dụ giả định: chín yêu cầu mất 100 ms và một yêu cầu mất 4.000 ms. Mean là **490 ms**, nhưng ca thông thường vẫn quanh 100 ms. Phải xem cả phân bố/percentile nếu muốn biết trải nghiệm ở đuôi chậm; với tập chỉ 10 mẫu, ước lượng p95 có thể kém ổn định.

### 4.4. Histogram và khả năng tổng hợp nhiều instance

Khi cần tính p95 trên **nhiều instance**, histogram buckets có thể được cộng theo các chiều hợp lệ trước khi ước lượng quantile. Các percentile đã tính riêng trên từng instance **không thể lấy trung bình hoặc cộng trực tiếp** để ra p95 toàn hệ thống.

Việc bật histogram tăng số time series, chi phí lưu trữ và scrape. Chỉ bật cho những Timer quan trọng đối với SLO hoặc điều tra độ trễ, và thiết kế bucket/ranh giới giá trị phù hợp với miền đo.

## 5. DistributionSummary — phân bố độ lớn của mỗi mẫu

**DistributionSummary** phù hợp khi mỗi sự kiện tạo ra một **giá trị số không phải khoảng thời gian**, chẳng hạn:

- Số tài liệu hoặc đoạn được retriever trả về trong một lần truy xuất.
- Số token input/output được provider báo trên mỗi model request.
- Kích thước payload theo byte.
- Điểm relevance hoặc factual correctness đã chuẩn hóa thành một giá trị **không âm**, chẳng hạn 0–1.
- Số bước tool trên mỗi trajectory nếu mục tiêu là phân bố số bước.

Ví dụ:

~~~text
RAG retrieval #1 -> 3 documents
RAG retrieval #2 -> 8 documents
RAG retrieval #3 -> 2 documents
RAG retrieval #4 -> 7 documents
~~~

DistributionSummary cho phép xem **count**, **total**, **mean = total/count** và, khi được cấu hình, histogram hoặc percentile của số tài liệu. Một Counter chỉ đếm bốn lượt truy xuất sẽ không cho biết các lượt đó trả về bao nhiêu tài liệu.

### 5.1. Khi dùng summary cho điểm đánh giá

Giả sử một evaluator chấm relevance trên tập tài liệu:

~~~text
0.92, 0.85, 0.30, 0.75, 0.88
~~~

Ghi mỗi điểm vào một DistributionSummary có đơn vị/miền xác định. Sau đó có thể tính trung bình hoặc khảo sát phân bố điểm thấp. Nhưng cần thận trọng:

1. **Định nghĩa score:** 1.0 biểu thị gì, 0.0 biểu thị gì?
2. **Tính so sánh:** chỉ so các điểm dùng cùng rubric và phiên bản evaluator.
3. **Mẫu bị thiếu:** ca không thể chấm phải được đếm riêng; không ghi mặc định điểm 0 nếu đó không phải kết quả thật.
4. **Rủi ro bị che khuất:** điểm relevance cao không bảo đảm không có lỗi sai sự thật hoặc rò dữ liệu.
5. **Giá trị ngoài miền:** chặn/loại/ghi lỗi dữ liệu không hợp lệ, không âm thầm làm méo phân bố.

Một summary ghi điểm không tự quyết định PASS/FAIL. Nếu sản phẩm yêu cầu **relevance ≥ 0,80** và **không có sai fact checking nghiêm trọng**, oracle cần áp quy tắc này rồi **đếm verdict bằng Counter**.

### 5.2. Cumulative tokens và per-request tokens

Hai phép đo hợp lý nhưng trả lời câu hỏi khác:

| Câu hỏi | Loại metric gợi ý |
| --- | --- |
| Đã tiêu thụ tổng cộng bao nhiêu token đầu vào? | Counter tăng theo số token báo cáo, hoặc tổng từ Summary |
| Mỗi request dùng bao nhiêu token đầu vào? | DistributionSummary |
| Request hiện tại còn bao nhiêu token được phép? | Gauge chỉ khi có nguồn trạng thái thực; thường nên là quota telemetry riêng |
| Lượt gọi model mất bao lâu? | Timer |

Nếu cả Counter tổng token và Summary token/request được ghi, cần nêu lý do và bảo đảm hai điểm đo có cùng tập mẫu; nếu không, số liệu dễ mâu thuẫn do một luồng bị bỏ sót.

### 5.3. Phân biệt summary và timer

Timer xử lý **đơn vị thời gian** và phép đếm thời lượng. DistributionSummary xử lý **độ lớn giá trị không phải thời gian**. Không dùng Summary ghi milliseconds chỉ để né Timer; sẽ mất ý nghĩa đơn vị và tiện ích đo duration chuyên biệt.

## 6. Gauge — ảnh chụp trạng thái tức thời

**Gauge** phù hợp với giá trị có thể tăng hoặc giảm theo thời gian:

- Số request/tool call đang chạy.
- Độ sâu hàng đợi các ca đánh giá.
- Số phiên RAG đang xử lý.
- Số tác vụ bất đồng bộ đang PENDING, nếu có nguồn đáng tin.
- Một mức tài nguyên hiện tại, như tỷ lệ dùng bộ đệm, theo contract.

~~~text
09:00:00  in-flight tool calls = 2
09:00:05  in-flight tool calls = 6
09:00:10  in-flight tool calls = 1
~~~

Gauge **không** cho biết tổng cộng bao nhiêu request đã đến trong khoảng đó. Một burst rất ngắn có thể xảy ra giữa hai lần scrape và không bị ghi nhận. Muốn biết số lượt đã hoàn tất, dùng Counter hoặc số mẫu của Timer.

### 6.1. Gắn gauge vào đối tượng được giữ sống

Micrometer thường theo dõi đối tượng dùng để đọc gauge thông qua tham chiếu có thể bị thu gom nếu không được giữ sống đúng cách. Vì vậy:

- Giữ một **AtomicInteger/AtomicLong** hoặc đối tượng trạng thái có vòng đời đủ dài.
- Đăng ký gauge một lần, không đăng ký mới với mỗi request.
- Tăng khi bắt đầu và giảm trong **finally** khi tác vụ kết thúc.
- Với xử lý bất đồng bộ, giảm khi công việc thực sự kết thúc, không giảm ngay sau khi enqueue.

Nếu đối tượng gauge bị thu gom hoặc không được cập nhật đúng, số đo có thể mất hoặc sai.

### 6.2. Gauge không thay thế cho trạng thái lịch sử

Không nên đọc gauge **queue depth = 0** để kết luận toàn bộ yêu cầu trước đây thành công. Queue có thể rỗng vì tác vụ thất bại, bị hủy hoặc chưa bao giờ vào hàng. Cần Counter cho kết quả và, nếu cần, truy vấn nhật ký/source of truth của từng thao tác.

## 7. Ma trận chọn metric cho đánh giá Spring AI

Đối với module đánh giá chất lượng, nên tổ chức metric theo tầng:

| Tầng | Đại lượng | Meter khuyến nghị | Lưu ý |
| --- | --- | --- | --- |
| Dataset/evaluation | Số ca đã chấm theo PASS/FAIL/INCONCLUSIVE | Counter | Một verdict cuối cho mỗi ca chạy |
| Dataset/evaluation | Điểm relevance mỗi ca | DistributionSummary | Giữ cùng rubric, miền điểm |
| Dataset/evaluation | Thời gian chấm một ca | Timer | Ghi cả lỗi/chờ |
| Dataset/evaluation | Số ca đang chờ chấm | Gauge | Snapshot tức thời |
| Chat/model | Thời gian model phản hồi | Timer | Ranh giới first token/full output rõ |
| Chat/model | Token input/output mỗi request | DistributionSummary | Dùng usage thực, không tự giả định |
| Chat/model | Lỗi provider theo nhóm | Counter | Nhãn error_class hữu hạn |
| Tool calling | Thời gian thực thi tool | Timer | Không lẫn model tool request với thực thi |
| Tool calling | Số tool request bị chặn quyền | Counter | Ghi tại dispatcher |
| Tool calling | Số tool đang chạy | Gauge | Gia tăng/giảm đúng vòng đời |
| Tool calling | Số lần tool trên mỗi trajectory | DistributionSummary | Không đánh đồng nhiều call với lỗi |
| RAG | Số tài liệu trả về mỗi lần retrieval | DistributionSummary | Có thể là 0 |
| RAG | Thời gian retrieval | Timer | Nhóm theo loại retriever nếu cần |
| RAG | Số lần không có nguồn đủ điều kiện | Counter | Định nghĩa “không có nguồn” |
| RAG | Điểm groundedness/fact checking | DistributionSummary hoặc Counter verdict | Numeric score khác với tỷ lệ đạt |
| Nghiệp vụ | Số giao dịch hoàn tất đã xác minh | Counter | Không dựa duy nhất vào ACCEPTED |
| Nghiệp vụ | Thời gian đến kết quả hoàn tất | Timer | Có thể dài hơn thời gian model |
| Nghiệp vụ | Số operation còn PENDING | Gauge | Đọc từ nguồn trạng thái đáng tin |
| Chi phí | Chi phí ước tính cho mỗi request | DistributionSummary | Chỉ khi có đơn giá/usage tin cậy |

**Cần biết cấp độ quan sát:** một ca đánh giá có thể gồm nhiều model requests, nhiều tool calls và một kết quả cuối. Không thể dùng số model requests làm mẫu số trực tiếp cho tỷ lệ thành công của ca đánh giá.

### Ví dụ một hành trình RAG + tool calling

Người dùng hỏi: “Tra tình trạng đơn A123 và giải thích quy trình trả hàng theo chính sách hiện hành”.

Trong một lần chạy giả định:

1. Model đề nghị tra trạng thái A123.
2. Tool lấy đơn trong 65 ms, trạng thái SHIPPED.
3. RAG truy xuất 5 đoạn tài liệu trong 130 ms.
4. Evaluator chấm groundedness bằng 0,88.
5. Model trả câu trả lời hoàn chỉnh sau 1,1 giây tính từ lúc nhận yêu cầu.
6. Oracle xác minh nội dung và quyền, kết quả PASS.

Những meter thích hợp có thể ghi:

~~~text
Timer ai.tool.execution.duration{tool_family="order",outcome="success"}
  -> sample 65 ms

Timer ai.rag.retrieval.duration{source_family="policy",outcome="success"}
  -> sample 130 ms

DistributionSummary ai.rag.documents.retrieved{source_family="policy"}
  -> sample 5

DistributionSummary ai.eval.groundedness.score{case_type="rag"}
  -> sample 0.88

Counter ai.eval.case.completed{case_type="rag_tool",verdict="pass"}
  -> +1

Timer ai.request.duration{route_family="assistant",outcome="success"}
  -> sample 1100 ms
~~~

Không cộng các thời lượng trên rồi cho là end-to-end; các giai đoạn có thể xen kẽ hoặc chạy song song. Cũng không coi điểm 0,88 là PASS nếu chưa định nghĩa threshold và những bất biến khác.

## 8. Đặt tên metric, đơn vị và tags

Thiết kế meter gồm **tên + loại + đơn vị + tập tag + thời điểm ghi**. Nếu thiếu một thành phần, metric có thể rất khó đọc hoặc dễ gây hiểu lầm.

### 8.1. Tên nói rõ điều đang đo

Một số tên gợi ý:

~~~text
ai.eval.case.completed          Counter
ai.eval.relevance.score         DistributionSummary
ai.tool.execution.duration      Timer
ai.rag.documents.retrieved      DistributionSummary
ai.tool.inflight                Gauge
~~~

Micrometer có cơ chế **naming convention** theo backend. Ví dụ các tên dạng dấu chấm có thể được chuyển thành tên underscore trong Prometheus, và Timer có thể dùng hậu tố seconds. **Không dựa vào chuỗi tên xuất ra cố định** nếu chưa kiểm tra exporter và phiên bản thư viện.

Nên dùng đơn vị rõ:

- Duration: ghi bằng API Timer với kiểu **Duration** hoặc đơn vị thời gian do Timer quản lý.
- Token count: đơn vị **tokens**.
- Document count: đơn vị **documents** hoặc **items** tùy contract.
- Bytes: đơn vị **bytes**.
- Score 0–1: ghi rõ đây là **dimensionless score/range**, không phải phần trăm 0–100.
- Cost: ghi rõ currency, ví dụ USD; có thể dùng hai metric hoặc nhãn currency hữu hạn nếu cần nhiều đơn vị, không cộng tiền tệ khác nhau.

### 8.2. Tags phải hữu hạn và có ý nghĩa

Các tag có thể hữu ích:

| Tag | Ví dụ giá trị | Ý nghĩa |
| --- | --- | --- |
| case_type | rag, tool, multi_turn | Nhóm ca đánh giá |
| verdict | pass, fail, inconclusive | Kết quả oracle |
| tool_family | retrieval, order, payment, other | Nhóm công cụ |
| outcome | success, error, timeout | Kết quả thực thi |
| environment | test, staging, production | Môi trường |
| model_family | family_a, family_b | Nhóm model nếu có số giá trị quản lý được |
| error_class | auth, validation, transient, business | Nhóm lỗi hữu hạn |

**Không nên dùng trực tiếp:** user ID, order ID, conversation ID, tool call ID, raw prompt, document ID hoặc trace ID làm metric tag. Chúng có thể tạo ra hàng triệu tổ hợp và chứa thông tin nhạy cảm. Hãy đặt chúng trong trace/log có kiểm soát rồi liên kết bằng tham chiếu.

### 8.3. Cardinality có thể tăng theo tích số

Giả sử một Timer có:

- 5 giá trị tool_family.
- 4 giá trị model_family.
- 3 giá trị outcome.
- 2 môi trường.

Số tổ hợp tag có thể là **5 × 4 × 3 × 2 = 120** trước khi tính số chuỗi histogram hoặc các nhãn khác. Nếu thêm một tag **user_id** có 100.000 giá trị, hệ thống metrics có thể trở nên không kiểm soát được.

Trước khi thêm tag, cần hỏi: **“Có truy vấn vận hành cụ thể nào sẽ dùng chiều này không?”**. Nếu chỉ cần chẩn đoán một yêu cầu riêng lẻ, trace tốt hơn metric.

## 9. Ví dụ Java với Micrometer: dùng đủ bốn loại meter

Ví dụ sau có thể đặt tại **ranh giới quan sát của ứng dụng Spring AI**. Nó chỉ nhận sự kiện đã được xác minh hoặc các thao tác thực thi do ứng dụng cung cấp; nó không cần viết lại Tool Calling hay ChatMemory. Mã dùng API Micrometer quen thuộc và tránh tạo tag từ dữ liệu người dùng không kiểm soát.

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class AiEvaluationMeters {

    public enum Verdict {
        PASS, FAIL, INCONCLUSIVE
    }

    private final MeterRegistry registry;
    private final AtomicInteger inFlightToolCalls =
            new AtomicInteger(0);

    public AiEvaluationMeters(MeterRegistry registry) {
        this.registry = registry;

        // Gauge đọc trạng thái hiện tại; giữ đối tượng tham chiếu sống.
        Gauge.builder(
                    "ai.tool.inflight",
                    inFlightToolCalls,
                    AtomicInteger::get)
                .description("Number of executing tool calls")
                .register(registry);
    }

    // Chỉ nhận một tập tool family hữu hạn.
    private static String normalizeToolFamily(String family) {
        return switch (family) {
            case "retrieval", "order", "payment" -> family;
            default -> "other";
        };
    }

    private static String normalizeCaseType(String type) {
        return switch (type) {
            case "rag", "tool", "rag_tool", "multi_turn" -> type;
            default -> "other";
        };
    }

    // Bọc lời gọi tool đồng bộ để đo thời lượng và in-flight.
    public <T> T observeToolCall(
            String toolFamily,
            Callable<T> operation
    ) throws Exception {
        String family = normalizeToolFamily(toolFamily);
        Timer.Sample sample = Timer.start(registry);
        inFlightToolCalls.incrementAndGet();
        String outcome = "success";

        try {
            return operation.call();
        } catch (Exception ex) {
            outcome = "error";
            throw ex;
        } finally {
            // Timer vẫn ghi mẫu khi có exception.
            sample.stop(
                    Timer.builder("ai.tool.execution.duration")
                            .description("Executed tool latency")
                            .tag("tool_family", family)
                            .tag("outcome", outcome)
                            .publishPercentileHistogram()
                            .register(registry)
            );
            inFlightToolCalls.decrementAndGet();
        }
    }

    // Chỉ gọi khi kết quả chấm cuối của một ca đã được xác định.
    public void recordEvaluationResult(
            String caseType,
            Verdict verdict
    ) {
        Counter.builder("ai.eval.case.completed")
                .description("Completed evaluation cases by verdict")
                .tag("case_type", normalizeCaseType(caseType))
                .tag("verdict", verdict.name().toLowerCase(
                        java.util.Locale.ROOT))
                .register(registry)
                .increment();
    }

    // Ghi một điểm relevance hợp lệ trên miền [0, 1].
    public void recordRelevanceScore(
            String caseType,
            double score
    ) {
        if (!Double.isFinite(score)
                || score < 0.0
                || score > 1.0) {
            throw new IllegalArgumentException(
                    "Relevance score must be between 0 and 1");
        }

        DistributionSummary.builder("ai.eval.relevance.score")
                .description("Relevance score per evaluated sample")
                .tag("case_type", normalizeCaseType(caseType))
                .register(registry)
                .record(score);
    }

    // Ghi số tài liệu trả về mỗi lần retrieval.
    public void recordRetrievedDocuments(
            String sourceFamily,
            int documentCount
    ) {
        if (documentCount < 0) {
            throw new IllegalArgumentException(
                    "Document count must be non-negative");
        }
        String source = switch (sourceFamily) {
            case "policy", "orders", "knowledge" -> sourceFamily;
            default -> "other";
        };

        DistributionSummary.builder("ai.rag.documents.retrieved")
                .description("Documents returned per retrieval")
                .baseUnit("documents")
                .tag("source_family", source)
                .register(registry)
                .record(documentCount);
    }
}
~~~

### 9.1. Sử dụng với bộ đánh giá

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();
var meters = new AiEvaluationMeters(registry);

// Đây là tác vụ giả lập đã có trong ứng dụng.
String toolResult = meters.observeToolCall(
        "retrieval",
        () -> "Retrieved policy-v2026");

meters.recordRetrievedDocuments("policy", 5);
meters.recordRelevanceScore("rag", 0.88);

// Chỉ đánh PASS sau khi oracle xác minh điều kiện cần thiết.
meters.recordEvaluationResult(
        "rag", AiEvaluationMeters.Verdict.PASS);

System.out.println(toolResult);
System.out.println(
        registry.find("ai.eval.case.completed")
                .tag("case_type", "rag")
                .tag("verdict", "pass")
                .counter()
                .count()
);
~~~

Ví dụ sử dụng **SimpleMeterRegistry** để minh họa API trong một quá trình Java; nó không tự cấu hình exporter production. Trong Spring Boot, thông thường dùng **MeterRegistry** do ứng dụng cấu hình/tiêm vào. Spring AI và Spring Boot có thể đã phát một số metric model/tool; trước khi thêm meter riêng, phải kiểm tra có trùng ngữ nghĩa và tên không.

### 9.2. Những lựa chọn có chủ đích trong mã

- **Counter** chỉ tăng khi **một kết quả chấm cuối** được ghi; một ca chạy lại được coi là một lượt đánh giá mới và cần lưu run ID bên ngoài metrics.
- **Timer** ghi thời lượng cả khi thành công và lỗi, không chỉ khi return bình thường.
- **DistributionSummary** nhận điểm relevance 0–1 và số tài liệu của mỗi retrieval; không ghi dữ liệu ngoài miền.
- **Gauge** giữ **AtomicInteger** làm trạng thái số tool đồng bộ đang chạy; không đăng ký lại mỗi lần tool bắt đầu.
- **Tags** dùng danh mục hữu hạn, không lấy trực tiếp ID người dùng, câu hỏi hoặc tool name tùy ý làm nhãn.

### 9.3. Các giới hạn của ví dụ

1. Hàm bọc Timer chỉ minh họa **tool đồng bộ**; công việc bất đồng bộ phải đo cho đến khi Future/Publisher hoặc tác vụ thực sự kết thúc theo hợp đồng.
2. Nhãn outcome mới phân biệt success/error; có thể mở rộng thành timeout/cancelled bằng một bộ phân loại lỗi hữu hạn.
3. Ví dụ đặt histogram tại mọi tổ hợp tool_family/outcome; trong hệ thống thật phải cân nhắc chi phí, bucket và kích thước dữ liệu trước khi bật rộng.
4. Kết quả RETURN từ một handler không đồng nghĩa nghiệp vụ đã COMPLETED. Muốn đo thời gian hoàn tất nghiệp vụ phải có Timer khác và source of truth phù hợp.
5. Summary điểm relevance chỉ ghi phân bố giá trị; một oracle độc lập phải xác định PASS/FAIL/INCONCLUSIVE.
6. Bộ đo không tự cung cấp context, quyền, idempotency, đánh giá RAG hoặc kiểm chứng tool call; đó là trách nhiệm của các thành phần khác.

## 10. Cấu hình histogram, percentile và mục tiêu SLO

Không phải meter nào cũng cần phân bố chi tiết. Trước khi bật histogram, cần đặt câu hỏi:

1. Đang tối ưu **giá trị trung bình** hay một **ngưỡng ở đuôi** như p95?
2. Có cần tổng hợp qua nhiều instance/pod không?
3. Bucket nào thực sự hữu ích cho miền đo?
4. Cardinality từ tags và số bucket có nằm trong ngân sách lưu trữ không?

Ví dụ mức kỳ vọng cho tool execution:

~~~text
Mục tiêu vận hành minh họa:
  p95(tool duration) < 800 ms
  error rate          < 1%

Nhóm theo:
  tool_family = retrieval | order | payment | other
  outcome     = success | error | timeout
~~~

Các ngưỡng này chỉ là ví dụ, **không phải SLO mặc định của Spring AI**. Với tool payment, latency hoặc error budget hợp lý có thể hoàn toàn khác retrieval.

### Client-side percentile và histogram

Một số backend cho phép hệ thống phát **percentile trực tiếp tại client**; percentile này có thể hữu ích trên từng instance nhưng **không thể tổng hợp bằng phép cộng/trung bình**. Histogram buckets cho phép các hệ thống như Prometheus tính một ước lượng quantile từ số mẫu đã gộp.

Nếu phân bố bị thay đổi hoặc tăng request từ một nhóm rất chậm, p95 của toàn hệ thống có thể khác rất xa p95 riêng của từng instance. Đừng áp công thức trung bình hai percentile.

### Tính tỷ lệ từ counter

Giả sử một tập có 100 ca; kết quả:

- PASS = 70
- FAIL = 20
- INCONCLUSIVE = 10

Ta có:

\[
\text{Coverage} = \frac{70+20}{100} = 90\%
\]

\[
\text{Pass rate trên ca có thể chấm}
= \frac{70}{70+20} \approx 77{,}8\%
\]

\[
\text{Verified success trên toàn tập}
= \frac{70}{100} = 70\%
\]

Hai tỷ lệ thành công trả lời hai câu hỏi khác nhau; cần ghi **mẫu số và cách xử lý INCONCLUSIVE**. Nếu mọi ca INCONCLUSIVE bị loại khỏi denominator mà coverage giảm mạnh, pass rate có thể trông tăng giả.

Không dùng gauge “số ca hiện tại đang PASS” nếu thật ra muốn biết số kết quả đánh giá PASS đã xảy ra theo thời gian.

## 11. Ví dụ truy vấn số liệu

Trong môi trường dùng Prometheus, tên metric và hậu tố có thể được Micrometer chuyển đổi theo naming convention. Các biểu thức dưới đây **chỉ minh họa cách tư duy truy vấn**; cần xác minh tên series thực trên exporter của phiên bản đang triển khai.

### Tốc độ ca đánh giá PASS

~~~promql
sum(rate(ai_eval_case_completed_total{verdict="pass"}[5m]))
~~~

### Tỷ lệ PASS trên các ca có verdict quyết định được

~~~promql
sum(rate(ai_eval_case_completed_total{verdict="pass"}[5m]))
/
sum(rate(ai_eval_case_completed_total{verdict=~"pass|fail"}[5m]))
~~~

Phép chia cần xử lý **mẫu số bằng 0** và cần xem các chiều case_type, environment trước khi tổng hợp. Không so sánh tỷ lệ giữa hai lần chạy có phân bố ca khác nhau mà không chuẩn hóa.

### p95 độ trễ tool từ histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Biểu thức yêu cầu histogram buckets đã được bật và xuất ra. Đơn vị của kết quả trong ví dụ này là **giây**. Nếu không có các series bucket hoặc nhà cung cấp metric dùng quy ước khác, phải điều chỉnh truy vấn theo dữ liệu thực.

### Trung bình số tài liệu truy xuất mỗi lượt

~~~promql
sum(rate(ai_rag_documents_retrieved_documents_sum[5m]))
/
sum(rate(ai_rag_documents_retrieved_documents_count[5m]))
~~~

Tên series phụ thuộc cách exporter xử lý **baseUnit("documents")**. Nếu không chắc, kiểm tra trực tiếp các series đã xuất thay vì đoán tên. Summary phải có **đủ count và total amount** để tính giá trị trung bình.

### Tác vụ đang chạy

~~~promql
sum(ai_tool_inflight)
~~~

Gauge có thể không ghi nhận các burst rất ngắn giữa hai lần scrape. Không dùng tổng gauge theo thời gian như một counter; nếu cần số yêu cầu bắt đầu hoặc hoàn tất, thiết kế meter riêng phù hợp.

## 12. Liên hệ metrics với traces, logs và bằng chứng nghiệp vụ

**Metric** trả lời “có bao nhiêu, nhanh hay chậm, phân bố thế nào?”. **Trace** trả lời “một yêu cầu cụ thể đã đi qua những bước nào?”. **Log/audit** có thể cung cấp mã lỗi và sự kiện bền vững. **Oracle** xác định kết quả có đáp ứng hợp đồng nghiệp vụ hay không.

~~~mermaid
flowchart TD
    A["Ca đánh giá: case_id, run_id"] --> B["Spring AI model + tool/RAG"]
    B --> C["Metric events: counter/timer/summary/gauge"]
    B --> D["Trace: model turn, tool call, retrieval"]
    B --> E["Backend/source of truth"]
    E --> F["Oracle: PASS/FAIL/INCONCLUSIVE"]
    D --> G["Điều tra ca lỗi"]
    F --> G
    C --> H["Dashboard: quality, latency, usage"]
    G --> H
~~~

Ví dụ dashboard cho thấy **p95 tool retrieval tăng từ 300 ms lên 900 ms**, trong khi tỷ lệ PASS giảm. Số liệu này gợi ý có thể có một vấn đề ở retrieval, nhưng **chưa chứng minh quan hệ nhân quả**. Cần mở trace ca lỗi:

1. Model có chọn cùng công cụ và đối số đúng không?
2. Thời gian tăng nằm ở handler, database, vector store hay model?
3. Tài liệu truy xuất có đủ relevance và đúng phiên bản không?
4. Oracle FAIL vì thiếu bằng chứng hay vì model diễn giải sai kết quả?
5. Cấu hình prompt/model/index có thay đổi đồng thời không?

Traces có thể bị sampling, nên **thiếu span không đồng nghĩa không có hành động**. Khi sự kiện quan trọng không quan sát được, bộ đánh giá có thể cần nhãn **OBSERVABILITY_GAP/INCONCLUSIVE**.

### Tránh đưa dữ liệu riêng tư vào metrics

Tool arguments và tài liệu RAG có thể chứa thông tin nhạy cảm. Không đưa nguyên văn prompt, mã đơn, ID khách hàng, email hay nội dung chính sách nội bộ vào tags. Với trace chi tiết cần lưu, sử dụng quyền truy cập phù hợp, giảm dữ liệu, mã tham chiếu và thời hạn lưu. **Trace ID** dùng để liên kết riêng lẻ trong log/trace, không làm một metric tag cho mỗi yêu cầu.

## 13. Khi nào số liệu đánh giá có thể sai hoặc gây hiểu lầm?

### 13.1. Lấy dữ liệu đầu vào khác nhau để so hai phiên bản

Một phiên bản chạy nhiều câu hỏi RAG dễ, phiên bản khác chạy nhiều câu khó. Tỷ lệ PASS tổng không phản ánh khác biệt model.

**Cách xử lý:** dùng cùng dataset, fixture và oracle; nếu tập ca khác, phân tầng theo case_type và báo sự thay đổi.

### 13.2. Mỗi lần retry lại ghi một verdict

Một ca thất bại tạm thời rồi retry thành công được đếm FAIL và PASS trong khi báo cáo yêu cầu **một kết quả cuối cho một run**.

**Cách xử lý:** đếm retry/tool attempt ở metric riêng, chỉ ghi kết quả cuối sau khi oracle quyết định.

### 13.3. Chỉ đo latency của ca thành công

Những request timeout dài bị loại, khiến p95 trông giảm dù người dùng trải nghiệm tệ hơn.

**Cách xử lý:** ghi Timer trong finally, phân biệt success/error/timeout và báo tỷ lệ lỗi.

### 13.4. Dùng gauge để đếm yêu cầu

Gauge in-flight giảm về 0 sau khi các request kết thúc; lấy đó làm “số request đã xử lý = 0” là sai.

**Cách xử lý:** dùng Counter hoặc số mẫu của Timer cho số sự kiện đã hoàn tất.

### 13.5. Dùng counter để ghi nhiệt độ một hàng đợi

Queue depth tăng rồi giảm, nhưng Counter chỉ tăng; không thể hiện trạng thái hiện tại.

**Cách xử lý:** dùng Gauge đọc số phần tử thực, duy trì đối tượng tham chiếu sống.

### 13.6. Ghi score không xác định thành 0

Evaluator không đủ nguồn để chấm relevance nhưng code ghi 0, khiến trung bình giảm dù vấn đề thực là thiếu quan sát.

**Cách xử lý:** không ghi sample score giả; tăng Counter verdict INCONCLUSIVE hoặc lỗi nguồn tương ứng.

### 13.7. Tạo tag theo mỗi prompt hoặc user

Mỗi câu hỏi tạo một tổ hợp time series mới, làm backend metrics tăng tải và có nguy cơ lộ dữ liệu.

**Cách xử lý:** phân nhóm hữu hạn bằng case_type, tool_family, outcome; dùng trace/log cho ID riêng lẻ.

### 13.8. Lấy trung bình p95 nhiều instance

Trung bình các p95 riêng lẻ không bằng p95 của toàn bộ mẫu.

**Cách xử lý:** cấu hình histogram và tổng hợp bucket trước khi ước lượng percentile, nếu hệ thống backend hỗ trợ.

### 13.9. Đánh đồng công cụ trả 200 với thành công nghiệp vụ

Tool trả HTTP 200 cho thao tác tạo yêu cầu hoàn tiền, nhưng tiền còn PENDING.

**Cách xử lý:** phân biệt Counter/Timer cho tool execution với Counter/Timer của **verified business outcome**.

## 14. Chọn metric theo câu hỏi điều tra hồi quy

| Câu hỏi | Metric cần xem trước | Cần bổ sung bằng chứng nào? |
| --- | --- | --- |
| Model mới gọi tool nhiều hơn? | Summary số tool calls/trajectory, Timer model/tool | Trace đường đi và stop oracle |
| Tool trở nên chậm? | Timer theo tool_family, p95 histogram | Span backend, lỗi, timeout |
| RAG trả ít nguồn hơn? | Summary documents/retrieval | Query, document IDs, relevance |
| Điểm relevance giảm? | Summary score, Counter verdict | Rubric evaluator, nguồn tài liệu, case mix |
| Tỷ lệ sai fact checking tăng? | Counter FAIL theo error_class | Evidence span và source of truth |
| Hệ thống đang bị nghẽn? | Gauge queue depth/in-flight, Timer duration | Queue events, capacity, retry |
| Chi phí tăng? | Summary tokens/request và cost/request | Provider usage, số model turns, bảng giá |
| Nhiều yêu cầu bị từ chối quyền? | Counter auth denied | Auth context và policy changes |
| Có lỗi tác động trùng? | Counter duplicate verified, Summary attempts | Operation ID, idempotency, ledger |
| Trả lời nhanh hơn nhưng chất lượng giảm? | Timer response và Counter evaluation verdict | Trace/response và oracle |

Metric chỉ là **điểm khởi đầu**. Không thể sửa lỗi fact checking chỉ bằng điều chỉnh histogram, hay kết luận model sai vì một gauge queue cao. Luôn tìm sự kiện đầu tiên lệch khỏi hợp đồng trong các trace và dữ liệu chuẩn.

## 15. Quy trình thiết kế bộ metric cho một module Spring AI

Một quy trình có thể dùng trong nhóm phát triển:

1. **Liệt kê mục tiêu chất lượng:** relevance, factual accuracy, correct tool use, outcome, latency, cost, an toàn.
2. **Chọn đơn vị quan sát:** ca đánh giá, model request, tool call, retrieval, conversation hay business operation.
3. **Viết định nghĩa và mẫu số:** thế nào là PASS, completed, timeout, pending; ca không xác minh được xử lý ra sao.
4. **Chọn loại meter:** counter cho số sự kiện, timer cho thời gian, summary cho phân bố giá trị, gauge cho trạng thái hiện tại.
5. **Xác định điểm ghi:** trước/sau tool, khi evaluator ra verdict, khi backend commit hoặc khi queue thay đổi.
6. **Thiết kế tên/đơn vị/tags:** hạn chế cardinality, bảo vệ thông tin nhạy cảm.
7. **Chọn histogram cho chỉ số cần p95:** không bật tràn lan mà không tính chi phí.
8. **Tách trace khỏi metric:** giữ ID riêng lẻ trong trace/log, không trong labels.
9. **Kiểm thử bằng fixture:** ca thành công, lỗi, timeout, no-tool, thiếu quyền và source unavailable.
10. **So sánh phiên bản trên cùng dataset:** lưu prompt/model/pipeline/evaluator version bên cạnh báo cáo.

### Một metric specification hoàn chỉnh

~~~yaml
name: ai.eval.case.completed
type: counter
description: Số ca được chấm verdict cuối cùng
unit: cases
event: Sau khi oracle kết thúc việc chấm một case-run
tags:
  case_type: [rag, tool, rag_tool, multi_turn, other]
  verdict: [pass, fail, inconclusive]
invariants:
  - Một kết quả cuối cho mỗi case-run
  - Không tăng lại khi retry một tool nội bộ
  - Không gắn case_id hoặc run_id thành metric tag
notes:
  - Mẫu số lấy từ tổng các verdict của cùng tập ca
  - Theo dõi coverage để tránh bias do thiếu bằng chứng
~~~

Đây là **tài liệu đặc tả tự thiết kế**, không phải một file cấu hình tự động được Micrometer đọc. Khi viết code, chuyển từng trường thành điểm ghi sự kiện và tag được quản lý rõ ràng.

### Kiểm thử loại meter

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Ba ca PASS liên tiếp | Counter PASS tăng ba đơn vị |
| Một ca FAIL được retry nội bộ rồi chấm PASS | Một verdict cuối cho case-run; attempts được đo riêng |
| Một tool mất 200 ms rồi trả lỗi | Timer thêm một mẫu 200 ms với outcome error |
| Một lượt retrieval trả 0 tài liệu | Summary thêm một mẫu giá trị 0 nếu retrieval thực sự diễn ra |
| Hai tool bắt đầu, một tool kết thúc | Gauge in-flight đổi 0 → 2 → 1 |
| Relevance score bị thiếu | Không tạo score=0; ghi INCONCLUSIVE/thiếu dữ liệu |
| Thêm một orderId mới | Không tạo một metric time series mới theo orderId |
| Worker/process restart | Counter có thể reset; truy vấn rate phải xét reset |

## 16. Bài thực hành

**Bối cảnh:** Trợ lý Spring AI có công cụ tra trạng thái đơn và RAG truy xuất chính sách. Bạn cần quan sát cả chất lượng lẫn hiệu suất trong một bộ thử.

### Phần A — Phân loại đại lượng

Chọn loại meter phù hợp cho từng câu hỏi:

1. Có bao nhiêu ca fact checking bị đánh FAIL?
2. Một tool mất bao lâu từ khi được dispatch đến khi trả kết quả?
3. Mỗi lượt RAG đưa bao nhiêu đoạn tài liệu vào prompt?
4. Hiện có bao nhiêu model requests đang xử lý?
5. Mỗi lượt model tiêu thụ bao nhiêu output tokens?
6. Có bao nhiêu lần retry vì rate limit?
7. Điểm relevance phân bố ra sao giữa các câu hỏi?
8. Hiện còn bao nhiêu yêu cầu hoàn tiền đang PENDING?

Đáp án gợi ý theo thứ tự: **Counter, Timer, DistributionSummary, Gauge, DistributionSummary, Counter, DistributionSummary, Gauge**. Với câu cuối, gauge chỉ phù hợp nếu đọc được một nguồn trạng thái hiện tại có thẩm quyền.

### Phần B — Chạy ví dụ Micrometer

1. Tạo lớp **AiEvaluationMeters** như ví dụ.
2. Gọi một số tool giả lập có thành công và lỗi; kiểm tra cả hai nhánh có ghi Timer.
3. Ghi kết quả PASS/FAIL/INCONCLUSIVE và so sánh số lượng với kết quả oracle.
4. Ghi số tài liệu 0, 2, 5, 8 và điểm relevance 0,25; 0,65; 0,90.
5. Đọc các meter từ SimpleMeterRegistry để kiểm tra số mẫu và tổng; không cần kết nối hệ thống production.
6. Viết một ca có exception để xác minh Gauge in-flight được giảm trong finally.

### Phần C — Thiết kế dashboard hồi quy

1. Chọn một tập ca RAG + tool calling ổn định, có ca cần tool, no-tool và nguồn RAG không đủ.
2. Báo pass rate kèm coverage, Timer p50/p95, số tài liệu mỗi lượt, token mỗi request và số lời gọi thừa.
3. Chạy hai phiên bản prompt với cùng dataset và cùng source snapshot.
4. Nếu p95 tăng, chọn trace của ca chậm để xem model, tool, retrieval hay backend chịu trách nhiệm.
5. Nếu relevance giảm, phân biệt thay đổi retriever, dataset và evaluator rubric trước khi quy lỗi cho model.
6. Xác định ngưỡng cảnh báo riêng cho **suy giảm chất lượng** và **suy giảm vận hành**; không để một metric tốt che lấp lỗi quyền hoặc fact checking nghiêm trọng.

### Câu hỏi tự kiểm tra

- Vì sao không thể dùng Counter để lưu số request đang chạy?
- Vì sao Timer thường đã đủ đếm số lời gọi tool hoàn tất?
- Sự khác nhau giữa số token tổng và phân bố token trên mỗi request là gì?
- Vì sao cần ghi thời lượng của cả ca lỗi?
- Vì sao không thể lấy trung bình p95 của từng instance để tính p95 chung?
- Điều gì xảy ra nếu dùng raw user_id hoặc prompt làm tag?
- Một điểm groundedness 0,9 có chứng minh câu trả lời đúng sự thật hiện hành không?
- Vì sao tăng Counter PASS hai lần cho một ca retry sẽ làm sai mẫu số?
- Khi nào nên chấm INCONCLUSIVE thay vì ghi điểm relevance 0?
- Vì sao metrics cần liên kết với trace và oracle để tìm nguyên nhân hồi quy?

## 17. Tổng kết

1. **Counter đếm sự kiện**, phù hợp với PASS/FAIL, lỗi và retry; không biểu diễn trạng thái giảm được.
2. **Timer đo thời lượng**, đồng thời đếm số mẫu; phù hợp với latency model, tool, retrieval và kết quả nghiệp vụ có ranh giới rõ.
3. **DistributionSummary đo phân bố độ lớn của mỗi mẫu**, như token, số tài liệu hoặc điểm relevance đã chuẩn hóa.
4. **Gauge đọc trạng thái tức thời**, như in-flight hoặc backlog; không phải tổng số sự kiện trong quá khứ.
5. **Chọn metric theo ý nghĩa và mẫu số**, không dựa trên tên API hay dashboard có sẵn. Đơn vị, tags và thời điểm ghi phải được đặc tả.
6. **Không để metric gây hiểu lầm:** chấm verdict đúng một lần, phân biệt PENDING với COMPLETED, ghi cả lỗi, không biến thiếu dữ liệu thành score 0.
7. **Giới hạn cardinality và bảo vệ dữ liệu riêng tư.** Dùng tag hữu hạn cho tổng hợp, trace/log cho thông tin riêng lẻ.
8. **Đánh giá chất lượng cùng vận hành.** Metrics, traces, nguồn sự thật, token, chi phí và p95 giúp xác định tại sao phiên bản prompt/model/pipeline mới tốt hoặc tệ hơn.

## Tài liệu tham khảo

- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): cách sử dụng counter và mối quan hệ với timer.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration, thống kê và giới hạn.
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): đo phân bố các giá trị số.
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): trạng thái tức thời và vòng đời đối tượng được quan sát.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): cách xuất histogram và percentile.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): dữ liệu quan sát của các thành phần Spring AI.
- [Spring AI Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): tài liệu tham khảo về cách tiếp cận kiểm thử/đánh giá trong Spring AI; đường dẫn và nội dung cần đối chiếu phiên bản đang sử dụng.

**Lưu ý phiên bản:** khả năng cấu hình histogram, tên metric được exporter tạo ra, dữ liệu token usage và instrumentation của ChatClient/model/tool có thể khác nhau theo phiên bản Spring AI, Micrometer, Spring Boot và backend metrics. Trước khi triển khai, kiểm tra tài liệu và series thực tế của đúng bộ thư viện đang dùng; các metric và dataset trong bài là ví dụ do dự án tự định nghĩa, không phải cấu hình tự động có sẵn.
