# Theo dõi chất lượng, hiệu năng và chi phí suy luận AI

Trong chương **AI và học máy trên OCI** của module **Oracle Cloud Infrastructure**, triển khai endpoint mới chỉ là điểm bắt đầu của vận hành AI. Hệ thống cần trả lời ba câu hỏi cùng lúc:

1. **Chất lượng:** kết quả có đáp ứng yêu cầu nghiệp vụ và sử dụng dữ liệu được phép hay không?
2. **Hiệu năng:** người dùng phải chờ bao lâu, hệ thống xử lý được bao nhiêu yêu cầu và có phục hồi được khi lỗi không?
3. **Chi phí:** một yêu cầu, một luồng xử lý và một kết quả đạt yêu cầu tiêu tốn bao nhiêu?

API trả HTTP 200 không chứng minh câu trả lời đúng. Chi phí mỗi lượt gọi thấp cũng chưa chứng minh hệ thống hiệu quả nếu phải gọi lại nhiều lần hoặc phần lớn kết quả cần sửa thủ công.

Bài học trình bày cách kết hợp OCI Monitoring, Logging, thông tin sử dụng dịch vụ, dữ liệu đánh giá và công cụ chi phí để quan sát toàn bộ luồng suy luận. Các sơ đồ, schema và ngưỡng minh họa là thiết kế của ứng dụng, không phải cấu hình mặc định hoặc cam kết SLA của OCI.

## 1. Xác định đúng đơn vị cần theo dõi

### 1.1. Yêu cầu nghiệp vụ khác với một lần gọi model

Một câu hỏi của người dùng có thể dẫn đến nhiều bước: xác thực, truy xuất dữ liệu trong Oracle Database, tạo embedding, gọi model, retry, kiểm tra kết quả và trả lời.

Cần phân biệt các đơn vị sau:

| Đơn vị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Logical request** | Một yêu cầu nghiệp vụ cần hoàn tất | Người dùng hỏi về điều kiện bảo hành |
| **Model call** | Một tác vụ sử dụng model trong luồng | Tạo embedding hoặc sinh câu trả lời |
| **Attempt** | Một lần thử gọi API cho tác vụ đó | Lần đầu timeout, lần thứ hai thành công |
| **Final response** | Đầu ra thực sự được ứng dụng trả cho người dùng | Câu trả lời sau kiểm tra và xử lý fallback |
| **Evaluation** | Kết quả đánh giá một đầu ra cụ thể | Người duyệt xác nhận câu trả lời có căn cứ |

Nếu một logical request gọi hai model và mỗi tác vụ có retry, số attempt có thể lớn hơn nhiều số yêu cầu người dùng. Đếm tất cả attempt là “người dùng được phục vụ” sẽ làm sai cả tỷ lệ thành công lẫn chi phí đơn vị.

### 1.2. Dùng ba tầng chỉ số

| Tầng | Câu hỏi | Chỉ số minh họa |
| --- | --- | --- |
| **Hạ tầng và dịch vụ** | Endpoint, máy phục vụ và phụ thuộc có hoạt động không? | CPU/GPU, RAM, lỗi dịch vụ, độ trễ API |
| **Luồng ứng dụng** | Một yêu cầu hoàn tất ra sao? | Độ trễ toàn luồng, retry, timeout, cache, token |
| **Nghiệp vụ và chất lượng** | Kết quả có sử dụng được không? | Độ đúng, mức có căn cứ, tỷ lệ đạt yêu cầu, chi phí cho kết quả đạt |

Metric ở tầng dưới hỗ trợ giải thích tầng trên nhưng không thay thế được nó. GPU sử dụng thấp có thể là lãng phí công suất, nhưng cũng có thể do ứng dụng đang chờ database. Câu trả lời sai có thể bắt nguồn từ dữ liệu truy xuất cũ dù model hoạt động bình thường.

## 2. Thiết kế luồng quan sát trên OCI

Một kiến trúc minh họa cho ứng dụng hỏi đáp nội bộ có thể gồm:

~~~mermaid
flowchart TD
    U["Yêu cầu người dùng"] --> A["Backend: quyền truy cập và logical request ID"]
    A --> R["Truy xuất: Oracle Database hoặc kho tri thức"]
    R --> M["OCI Generative AI hoặc Data Science Model Deployment"]
    M --> V["Kiểm tra đầu ra và trả lời"]
    A --> T["Telemetry của ứng dụng"]
    R --> T
    M --> T
    V --> T
    M --> N["Metric dịch vụ OCI"]
    T --> L["OCI Logging: sự kiện và liên kết truy vết"]
    T --> C["OCI Monitoring: custom metrics"]
    N --> C
    V --> E["Kho đánh giá và phản hồi có kiểm soát"]
    E --> Q["Tổng hợp chất lượng theo phiên bản và nhóm dữ liệu"]
    Q --> C
    C --> AL["Dashboard, Alarm và Notifications"]
    B["Cost Analysis và Cost Reports"] --> D["Đối soát và phân bổ chi phí"]
    T --> D
    E --> D
~~~

Mỗi mũi tên là một tích hợp cần triển khai. OCI không tự suy ra tiêu chí nghiệp vụ, tự nối nhãn đến muộn hay tự phân bổ chi phí chung cho từng cuộc hội thoại.

Nên có hai nhịp xử lý:

- **Gần thời gian thực:** lỗi, độ trễ, lượng gọi, token, retry và bất thường chi tiêu ước tính.
- **Theo lô hoặc khi có nhãn:** độ đúng nghiệp vụ, đánh giá có căn cứ, kết quả cuối cùng và đối soát chi phí.

Một job đánh giá định kỳ có thể tổng hợp kết quả, nhưng phải biết rõ nó đang đánh giá những yêu cầu của khoảng thời gian nào.

## 3. Xác định SLI, SLO và tiêu chí chất lượng

**SLI** là chỉ số đo; **SLO** là mục tiêu nội bộ đặt cho chỉ số đó. Cần mô tả cả tử số, mẫu số, cửa sổ thời gian và trường hợp loại trừ.

Ví dụ mục tiêu **giả lập** cho một ứng dụng hỗ trợ khách hàng:

| Mục tiêu | Cách đo | Điều kiện diễn giải |
| --- | --- | --- |
| Hoàn tất kỹ thuật ít nhất 99% | Yêu cầu hợp lệ hoàn tất / tổng yêu cầu hợp lệ trong 30 ngày | Timeout và throttling làm thất bại yêu cầu vẫn phải được tính |
| p95 toàn luồng không quá 4 giây | Phân bố thời gian từ nhận yêu cầu đến kết thúc tại backend | Báo riêng thành công, lỗi và timeout |
| Ít nhất 95% câu trả lời được đánh giá đạt rubric | Số đầu ra đạt / số đầu ra áp dụng rubric đã được đánh giá | Ghi cỡ mẫu, phạm vi và độ trễ đánh giá |
| Chi phí trong ngân sách nghiệp vụ | Chi phí được quy về cùng tập yêu cầu và khoảng thời gian | Phân biệt ước tính với chi phí đã đối soát |

Các ngưỡng này chỉ minh họa cách viết mục tiêu. Mục tiêu thực tế phải xuất phát từ yêu cầu người dùng, mức rủi ro và ngân sách của hệ thống.

### 3.1. Không che lỗi bằng cách sửa mẫu số

Một request sai định dạng có thể nằm ngoài tập “yêu cầu hợp lệ”, nhưng vẫn cần thống kê riêng. Không loại toàn bộ 429 hoặc timeout khỏi mẫu số chỉ vì dịch vụ không trả kết quả.

Tương tự, từ chối đúng một yêu cầu không được phép có thể là hành vi chất lượng tốt. Tuy nhiên, từ chối mọi câu hỏi cũng không đáp ứng một hệ thống hỏi đáp. Cần đo riêng độ đúng khi từ chối, khả năng trả lời và mức hoàn thành tác vụ.

### 3.2. Tách mục tiêu trải nghiệm và mục tiêu mô hình

Một model có thể hoàn thành trong 1 giây nhưng người dùng chờ 6 giây vì truy xuất và retry. SLO trải nghiệm cần đo tại ranh giới ứng dụng, không lấy độ trễ model làm đại diện cho toàn luồng.

Với suy luận bất đồng bộ, tách thời gian nhận job, thời gian chờ và thời gian đến khi có kết quả sử dụng được. API chấp nhận job thành công chưa đồng nghĩa tác vụ đã hoàn tất.

## 4. Đo chất lượng theo loại bài toán

### 4.1. AI Services chuyên biệt và mô hình dự đoán

Chọn chỉ số phù hợp với đầu ra:

| Bài toán | Chỉ số chất lượng minh họa | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Phân loại ticket hoặc ảnh | Precision, recall, F1 theo nhãn | Lớp hiếm và chi phí phân loại sai |
| Dự đoán rủi ro | Chất lượng phân biệt, precision/recall tại ngưỡng sử dụng | Hiệu chỉnh điểm và chi phí cảnh báo sai |
| Dự đoán số | MAE hoặc thước đo sai số phù hợp | Đơn vị, nhóm có sai số lớn và ngoại lệ |
| Trích xuất hóa đơn | Độ đúng từng trường và tỷ lệ tài liệu đạt toàn bộ trường bắt buộc | Số tiền, ngày và quan hệ dòng hàng |
| Chép lời | Lỗi từ hoặc ký tự theo cách đánh giá được xác định | Ngôn ngữ, giọng nói, nhiễu và thuật ngữ |

Không dùng accuracy chung để che hiệu quả kém ở một lớp quan trọng. Với 1% yêu cầu thuộc lớp hiếm, mô hình luôn trả lớp phổ biến có thể có accuracy cao nhưng không phát hiện được đối tượng cần xử lý.

Confidence score hoặc điểm mô hình không tự chứng minh xác suất đúng. Muốn dùng score để quyết định tự động, cần đánh giá điểm đó trên dữ liệu đại diện và tại ngưỡng thực tế.

### 4.2. Generative AI: kiểm tra nhiều tiêu chí độc lập

Với câu trả lời sinh bởi model, rubric có thể bao gồm:

- **Đúng nội dung:** phát biểu phù hợp với dữ liệu có thẩm quyền.
- **Có căn cứ:** các nhận định cần bằng chứng được hỗ trợ bởi nguồn đã cung cấp.
- **Đúng nguồn:** trích dẫn dẫn đến đúng tài liệu và hỗ trợ nhận định tương ứng.
- **Đủ thông tin:** trả lời được những phần cần thiết của yêu cầu.
- **Đúng cấu trúc:** đáp ứng schema hoặc định dạng ứng dụng cần.
- **Đúng phạm vi quyền và chính sách:** sử dụng dữ liệu được phép, xử lý đúng yêu cầu phải từ chối.

JSON hợp lệ có thể chứa số liệu sai. Trích dẫn tồn tại cũng chưa chắc chứng minh câu trả lời có căn cứ.

Có thể định nghĩa **task pass** là đạt tất cả tiêu chí bắt buộc của tác vụ. Một vi phạm nghiêm trọng không nên bị “bù điểm” bằng văn phong tốt hoặc câu trả lời ngắn.

### 4.3. RAG cần đo cả truy xuất lẫn sinh câu trả lời

Một luồng retrieval-augmented generation cần tách ít nhất:

1. Nguồn có được cập nhật và người hỏi có quyền đọc không?
2. Bước truy xuất có tìm được đoạn liên quan không?
3. Ngữ cảnh chuyển cho model có bị cắt mất thông tin cần thiết không?
4. Câu trả lời có sử dụng đúng bằng chứng không?

Nếu có tập câu hỏi kèm tài liệu liên quan được gán nhãn, có thể đo recall@k hoặc chất lượng xếp hạng. Định nghĩa “liên quan” và tập nguồn chuẩn phải được ghi rõ.

Khi retrieval không tìm được bằng chứng, model bịa thêm câu trả lời là một lỗi khác với model từ chối đúng. Dashboard cần phân biệt hai trường hợp để đội ngũ sửa đúng bước.

### 4.4. Kết hợp đánh giá tự động với kiểm tra của con người

Các kiểm tra schema, miền giá trị hoặc phép tính nghiệp vụ có thể tự động hóa trực tiếp. Với nội dung mở, có thể sử dụng người đánh giá hoặc model hỗ trợ chấm, nhưng cần kiểm tra độ đồng thuận và sai lệch của cách chấm.

Nếu dùng model chấm:

- Giữ phiên bản model chấm, prompt và rubric.
- Xem nội dung được chấm là dữ liệu không đáng tin cậy; không cấp công cụ hoặc quyền ngoài nhu cầu chấm.
- Đối chiếu một phần kết quả với người đánh giá.
- Theo dõi chi phí và độ trễ của chính quá trình đánh giá.

Điểm do model chấm là một phép đo có sai số, không phải nhãn chân lý mặc định.

## 5. Thu thập nhãn, phản hồi và phát hiện thay đổi chất lượng

### 5.1. Nối đánh giá với đúng đầu ra đã phục vụ

Nhãn có thể đến sau nhiều giờ hoặc nhiều ngày. Cần lưu liên kết giữa:

~~~text
logical request ID
    -> final response ID hoặc phiên bản đầu ra
    -> model, prompt, dữ liệu và cấu hình đã dùng
    -> nhãn hoặc đánh giá
    -> thời điểm có nhãn và phiên bản rubric
~~~

Không tạo lại câu trả lời bằng model hiện tại rồi coi đánh giá đó là đánh giá cho câu trả lời cũ. Nếu đầu ra đã được chỉnh sửa sau phản hồi, cần xác định người đánh giá đang chấm phiên bản nào.

Với dự đoán giao trễ, yêu cầu mới chưa có kết quả giao không được mặc định là “dự đoán đúng”. Chỉ tính các trường hợp đã đủ điều kiện xác định nhãn theo quy tắc.

### 5.2. Báo cả chất lượng và độ bao phủ đánh giá

Hai tỷ lệ có ý nghĩa khác nhau:

~~~text
Tỷ lệ đạt trên tập đã đánh giá =
    số kết quả đạt / số kết quả được đánh giá hợp lệ

Độ bao phủ đánh giá =
    số kết quả được đánh giá / số kết quả thuộc tập cần theo dõi
~~~

Nếu đánh giá 100 câu dễ trong 10.000 yêu cầu rồi báo “chất lượng 99%”, kết luận có thể không đại diện cho toàn bộ lưu lượng.

Mẫu đánh giá nên có thiết kế rõ: ngẫu nhiên, phân tầng theo ngôn ngữ, loại yêu cầu, model hoặc mức rủi ro. Nếu tăng tỷ lệ lấy mẫu ở nhóm lỗi, lưu cách chọn mẫu để không dùng kết quả như một tỷ lệ chung chưa hiệu chỉnh.

Phản hồi tự nguyện có thể thiên về người rất hài lòng hoặc rất không hài lòng. Nó là nguồn tín hiệu hữu ích nhưng không thay thế hoàn toàn mẫu đánh giá đại diện.

### 5.3. Theo dõi theo nhóm và phiên bản

Phân tách chất lượng theo những nhóm có ý nghĩa như:

- Model, deployment, prompt template và phiên bản kho tri thức.
- Ngôn ngữ, loại tài liệu, route nghiệp vụ hoặc nhóm độ dài đầu vào.
- Cache hit/miss, fallback và phương thức phục vụ.
- Khoảng thời gian yêu cầu phát sinh và khoảng thời gian nhãn được ghi nhận.

Độ dài đầu vào, tỷ lệ thiếu dữ liệu hoặc phân bố nhãn thay đổi là tín hiệu **drift** cần điều tra. Drift không tự chứng minh mô hình đã giảm chất lượng; ngược lại, chất lượng có thể giảm dù chỉ số phân bố tổng quát chưa báo động.

Với cỡ mẫu nhỏ, nên báo số lượng và mức bất định thay vì chỉ đưa một tỷ lệ có nhiều chữ số thập phân.

## 6. Đo hiệu năng từ góc nhìn người dùng

### 6.1. Các mốc thời gian cần xác định

| Chỉ số | Ranh giới đo gợi ý |
| --- | --- |
| **End-to-end latency** | Backend nhận logical request đến khi trả kết quả hoặc kết thúc lỗi |
| **Queue time** | Công việc vào hàng đợi đến khi được thực thi |
| **Retrieval latency** | Bắt đầu truy xuất đến khi có ngữ cảnh |
| **Provider round-trip latency** | Bắt đầu gửi một attempt đến khi nhận kết quả hoặc lỗi |
| **Time to first token — TTFT** | Mốc bắt đầu đã quy định đến token nội dung đầu tiên trong luồng streaming |
| **Generation duration** | Token nội dung đầu tiên đến khi kết thúc sinh |
| **Post-processing latency** | Kiểm tra, chuẩn hóa và hoàn tất đầu ra |

Ghi rõ TTFT được đo tại model hay tại ứng dụng. Thời điểm nhận một gói metadata hoặc header chưa chắc là thời điểm người dùng nhận token nội dung đầu tiên.

Oracle sử dụng các thước đo như TTFT, request latency và throughput trong benchmark Generative AI. Hiệu năng phụ thuộc mức đồng thời và phân bố token đầu vào, đầu ra. Không dùng kết quả benchmark như bảo đảm cho một luồng ứng dụng khác. [Dedicated AI Cluster Performance Benchmarks](https://docs.oracle.com/en-us/iaas/Content/generative-ai/performance.htm).

### 6.2. Dùng phân vị và phân bố phù hợp

- **p50** mô tả trải nghiệm ở giữa phân bố.
- **p95/p99** giúp nhìn các yêu cầu chậm ở phần đuôi.
- **Mean** hữu ích cho một số phân tích nhưng có thể che các yêu cầu rất chậm.

Không cộng p95 của retrieval với p95 của model rồi gọi đó là p95 toàn luồng. Cần đo tổng thời gian trên từng logical request rồi tính phân vị.

Cũng không lấy trung bình p95 của nhiều instance để suy ra p95 chung. Muốn tổng hợp đúng, cần dữ liệu phân bố hoặc cách gộp thích hợp.

Ghi riêng thời gian của yêu cầu lỗi và timeout. Timeout cho biết ứng dụng đã dừng chờ tại mốc đó; nó không cho biết chính xác model đã tính toán xong lúc nào.

### 6.3. Throughput, concurrency và độ dài đầu ra

Requests/second mô tả số yêu cầu theo thời gian; concurrency mô tả số yêu cầu đang đồng thời xử lý. Với LLM, token/second còn phụ thuộc việc đang đo tốc độ của một yêu cầu hay tổng lưu lượng của hệ thống.

Hai hệ thống cùng đạt 10 request/second có thể có tải rất khác nếu một bên sinh 30 token và bên kia sinh 1.000 token mỗi câu trả lời.

Khi thử tải, giữ lại phân bố đầu vào/đầu ra, tỷ lệ cache, burst và mức đồng thời giống mục tiêu. Theo dõi cả số yêu cầu đến, số được chấp nhận, số hoàn tất và độ dài hàng đợi; chỉ đo các yêu cầu thành công có thể che tình trạng quá tải.

## 7. Sử dụng metric và log gốc của OCI đúng phạm vi

### 7.1. OCI Data Science Model Deployment

Metric model deployment được phát trong namespace **oci_datascience_modeldeploy**; tài liệu Oracle nêu các metric này tự có cho tài nguyên model deployment được tạo. [Model Deployment Metrics](https://docs.oracle.com/en-us/iaas/Content/data-science/using/metrics-model-deploy.htm).

| Metric tiêu biểu | Nội dung cần quan sát |
| --- | --- |
| **PredictRequestCount** | Lượng gọi predict |
| **PredictLatency** | Độ trễ predict, đơn vị milliseconds |
| **CpuUtilization / MemoryUtilization** | Áp lực CPU và bộ nhớ |
| **GPUCoreUtilization / GPUMemoryUtilization** | Mức sử dụng GPU khi cấu hình có hỗ trợ |
| **PredictBandwidth** | Mức sử dụng băng thông của deployment |

Lọc theo **resourceId** để quan sát đúng deployment; một số metric có thêm dimension như kết quả hoặc instance. Không giả định mọi metric cùng hỗ trợ mọi dimension.

Các metric hạ tầng giúp xác định nút thắt, nhưng không tự cung cấp precision, recall hay độ đúng nghiệp vụ của model. Các nhóm tài nguyên Data Science có tập metric khác nhau. [Data Science Metrics](https://docs.oracle.com/en-us/iaas/Content/data-science/using/metrics.htm).

### 7.2. OCI Generative AI

Tài liệu metric của Generative AI mô tả tài nguyên hosting dedicated AI cluster và endpoint, với các metric như:

| Metric | Ý nghĩa |
| --- | --- |
| **TotalInvocationCount** | Lượt gọi |
| **InvocationLatency** | Thời gian xử lý lượt gọi |
| **InputTokenCount / OutputTokenCount** | Token đầu vào và đầu ra được xử lý |
| **ClientErrorCount / ServerErrorCount** | Lỗi phía client hoặc dịch vụ |

Các tên metric được Oracle liệt kê trong [Metric Details in Generative AI](https://docs.oracle.com/en-us/iaas/Content/generative-ai/metric-details.htm). Namespace dùng cho các truy vấn được mô tả là **oci_generativeai**. [Creating a Query for Generative AI Metrics](https://docs.oracle.com/en-us/iaas/Content/generative-ai/create-query.htm).

Phải kiểm tra metric thực tế của mode, model và tài nguyên đang sử dụng. Không mặc định mọi on-demand call có cùng metric hoặc dimension như một dedicated endpoint. Telemetry ứng dụng vẫn cần thiết để quan sát logical request và đường đi qua nhiều dịch vụ.

Với các AI Service chuyên biệt khác, tìm tài liệu metric của chính dịch vụ đó; không dùng namespace của Generative AI để truy vấn tất cả dịch vụ AI.

### 7.3. Logging cần cấu hình và có vòng đời riêng

Tích hợp Logging của Data Science là tùy chọn. Model deployment có access log với metadata như thời gian, trạng thái, độ trễ model và request ID; predict log xuất phát từ mã trong artifact. [Data Science Logs](https://docs.oracle.com/en-us/iaas/Content/data-science/using/log-about.htm).

Access log hữu ích để nối một request với lỗi endpoint. Nó không tự trở thành bộ dữ liệu đánh giá đúng/sai. Predict log cũng không có thông tin chất lượng nếu mã ứng dụng chưa phát thông tin cần thiết.

Phân biệt ba nguồn:

- **Metric:** tổng hợp nhanh, phục vụ biểu đồ và alarm.
- **Log:** sự kiện chi tiết để tìm nguyên nhân.
- **Trace hoặc liên kết truy vết:** nối các bước của cùng logical request qua nhiều thành phần.

Không cần ghi toàn bộ prompt và phản hồi vào log chung chỉ để đếm lượt gọi hoặc đo độ trễ.

## 8. Thiết kế telemetry ứng dụng

### 8.1. Giữ thông tin đủ để nối ba chiều

Một sự kiện cho một attempt có thể chứa:

~~~json
{
  "eventType": "inference_attempt_completed",
  "eventId": "event-demo-0042-02",
  "logicalRequestId": "request-demo-0042",
  "modelCallId": "call-demo-0042-generation",
  "attemptId": "attempt-02",
  "timestamp": "2026-11-21T02:15:00Z",
  "environment": "prod",
  "route": "support-rag",
  "modelId": "MODEL_DA_PHE_DUYET",
  "promptVersion": "support-v5",
  "knowledgeVersion": "kb-r12",
  "providerRequestId": "REQUEST_ID_TU_DICH_VU",
  "outcome": "SUCCESS",
  "httpStatus": 200,
  "providerRoundTripMs": 1400,
  "inputTokens": 900,
  "outputTokens": 200,
  "usageStatus": "PROVIDER_REPORTED",
  "priceVersion": "pricing-reference-v3",
  "qualityStatus": "PENDING"
}
~~~

Đây là schema minh họa do ứng dụng thiết kế, không phải phản hồi API OCI. Số liệu và định danh đều giả lập.

Sự kiện hoàn tất logical request được ghi riêng, với tổng thời gian, số attempt, trạng thái cuối, cache/fallback và final response ID. Đánh giá đến sau nối vào final response ID đó.

Nếu một attempt timeout mà không có thông tin token, ghi trạng thái sử dụng **chưa biết** hoặc ước tính có nhãn. Không biến phần chưa biết thành 0 rồi báo tổng chi phí chắc chắn.

### 8.2. Đo bằng đồng hồ thích hợp và ghi cả lỗi

Mã giả:

~~~text
khi nhận logical request:
    tạo logical request ID
    ghi mốc bắt đầu bằng đồng hồ đo khoảng thời gian
    xác thực và kiểm tra dữ liệu

    cho mỗi model call cần thiết:
        thực hiện các attempt trong giới hạn retry và thời gian
        với từng attempt:
            đo thời gian
            thu usage nếu dịch vụ cung cấp
            ghi kết quả hoặc lỗi đã lọc thông tin nhạy cảm
            giữ request ID do dịch vụ trả về khi có

    kiểm tra đầu ra và chọn kết quả cuối
    trong bước kết thúc luôn ghi:
        trạng thái logical request
        thời gian toàn luồng
        số lần gọi, retry, cache và fallback
        định danh đầu ra để nhận đánh giá sau
~~~

Timestamp UTC giúp liên kết sự kiện; đồng hồ đơn điệu phù hợp đo khoảng thời gian trong một tiến trình. Không dựa hoàn toàn vào chênh lệch giờ hệ thống giữa hai máy để đo độ trễ.

Bộ phát telemetry cũng cần kiểm soát lỗi và backpressure. Không để việc ghi log chậm làm treo đường trả lời, đồng thời phải theo dõi số sự kiện bị mất hoặc chưa gửi được.

### 8.3. Kiểm soát dimension và dữ liệu nhạy cảm

Dimension metric nên có tập giá trị được quản lý, chẳng hạn môi trường, route, model hoặc nhóm kết quả. Logical request ID, email, số điện thoại và prompt đầy đủ không phù hợp làm dimension.

Mỗi tổ hợp dimension có thể tạo thêm chuỗi metric. Dùng ID chi tiết trong log hoặc kho sự kiện có kiểm soát; chỉ đưa nhóm tổng hợp cần thiết lên Monitoring.

Custom namespace không được dùng tiền tố dành riêng **oci_** hoặc **oracle_**. Ví dụ có thể chọn **aiapp_inference** cho metric của ứng dụng. [Publishing Custom Metrics](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/publishingcustommetrics.htm).

Nội dung đánh giá chi tiết nên được lưu ở nơi phân quyền và có thời hạn giữ phù hợp. Redaction, mã hóa hoặc thay ID không tự loại bỏ mọi rủi ro tái nhận diện.

## 9. Truy vấn metric và tránh tổng hợp sai

### 9.1. Ví dụ truy vấn MQL

Trong Metrics Explorer, chọn đúng region, compartment và namespace trước khi chạy truy vấn.

Ví dụ cho namespace **oci_datascience_modeldeploy**:

~~~text
PredictLatency[5m]{resourceId = "THAY_BANG_OCID_DEPLOYMENT", result = "Success"}.mean()
~~~

Truy vấn minh họa độ trễ predict trung bình của các điểm dữ liệu phù hợp trong khoảng 5 phút. Nó không phải p95 trải nghiệm người dùng.

Với custom namespace **aiapp_inference**, giả sử ứng dụng phát **AppLatencyMs** dưới dạng quan sát độ trễ từng logical request được lấy mẫu đúng cách:

~~~text
AppLatencyMs[5m]{environment = "prod", route = "support-rag"}.percentile(0.95)
~~~

Nếu ứng dụng phát **LogicalRequestCount** với giá trị 1 cho mỗi sự kiện hoàn tất duy nhất:

~~~text
LogicalRequestCount[5m]{environment = "prod", route = "support-rag"}.sum()
~~~

Cú pháp khoảng thời gian, statistic và dimension được mô tả trong [Monitoring Query Language Reference](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Reference/mql.htm).

### 9.2. Count, sum và percentile không thay thế nhau

- **count()** đếm số quan sát nhận được trong khoảng.
- **sum()** cộng giá trị các quan sát.
- **percentile()** ước lượng phân vị trên những dữ liệu thực sự được cung cấp.

Nếu mỗi điểm đã là tổng số request của một phút, count() chỉ đếm điểm dữ liệu, không phải số request. Nếu metric là counter tích lũy, cộng trực tiếp các giá trị tích lũy cũng không cho lượng phát sinh đúng.

Tương tự, nếu mỗi điểm đã là p95 của một cửa sổ, tính percentile tiếp trên các điểm đó không khôi phục p95 của toàn bộ request. Cần thiết kế cách lưu phân bố hoặc phép tổng hợp phù hợp từ đầu.

Với số liệu lấy mẫu, cỡ mẫu và cách lấy mẫu ảnh hưởng kết quả. Ở quy mô lớn, cân nhắc cơ chế thu thập phân bố và kho phân tích phù hợp thay vì bỏ ngẫu nhiên dữ liệu khi quá tải.

### 9.3. Dữ liệu chất lượng đến muộn cần xử lý khác

Monitoring có ràng buộc về thời điểm của datapoint khi publish. Không giả định có thể gửi nhãn đến sau nhiều ngày bằng timestamp gốc của request. [Publishing Custom Metrics — Considerations](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/publishingcustommetrics.htm).

Có thể lưu lịch sử nhãn trong kho đánh giá rồi phát metric tổng hợp tại thời điểm tính toán hiện tại. Báo cáo phải ghi rõ cohort request, mức hoàn tất nhãn và thời điểm đánh giá. Không trộn “chất lượng của request hôm nay” với “nhãn mới ghi nhận hôm nay”.

## 10. Tính chi phí suy luận theo toàn bộ luồng

### 10.1. Phân biệt ước tính vận hành và số liệu chi phí đối soát

| Nguồn | Mục đích |
| --- | --- |
| Usage hoặc token của từng attempt | Ước tính nhanh, phát hiện luồng gọi bất thường |
| Cấu hình công suất và thời gian sử dụng | Ước tính chi phí hạ tầng dành riêng |
| Cost Analysis | Quan sát chi phí theo dịch vụ, compartment hoặc tag |
| Cost Reports | Đối soát tiêu thụ, giá và chi phí ở mức chi tiết được cung cấp |

Cost Analysis hỗ trợ lọc và nhóm dữ liệu chi phí; các bản ghi chi phí có độ trễ nên không phù hợp làm công tắc chặn tức thời từng request. [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

OCI cung cấp Cost Reports theo định dạng riêng và FOCUS; khi đối soát cần lưu ý dữ liệu đến muộn hoặc các dòng điều chỉnh. Không chỉ cộng lặp tất cả file đã tải mà bỏ qua định danh dòng và điều chỉnh. [Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Không gọi cost estimate từ ứng dụng là số tiền hóa đơn chính xác. Cần gắn phiên bản biểu giá, tiền tệ, đơn vị tính và quy tắc chiết khấu hoặc phân bổ đang áp dụng.

### 10.2. Công thức theo token chỉ áp dụng khi đúng cơ chế tính phí

Nếu model có giá riêng cho một triệu input token và output token:

~~~text
C_generation =
    input_tokens / 1.000.000 × P_input
  + output_tokens / 1.000.000 × P_output
~~~

Ví dụ có 8 triệu input token và 2 triệu output token:

~~~text
C_generation = 8 × P_input + 2 × P_output
~~~

Đây là công thức minh họa, không phải biểu giá OCI. Cần kiểm tra model và SKU thực tế, kể cả các loại token, cache hoặc đơn vị tính khác nếu có.

Không lấy số ký tự chia cho một hằng số cố định để quyết toán token tiếng Việt. Ưu tiên usage mà API cung cấp; phép đếm cục bộ cần tokenizer phù hợp và được ghi rõ là ước tính khi chưa đối soát.

### 10.3. Dedicated hoặc model tự triển khai có chi phí công suất

Với tài nguyên phục vụ dành riêng, chi phí có thể gắn với công suất và thời gian thuê thay vì chỉ lượt gọi:

~~~text
Chi phí hạ tầng được phân bổ cho một yêu cầu =
    chi phí công suất trong kỳ / số yêu cầu được quy về công suất đó
~~~

Phải xác định cách phân bổ khi nhiều ứng dụng dùng chung: theo token, thời gian GPU, tài nguyên sử dụng hoặc một quy tắc nội bộ được thống nhất. Số phân bổ không tự trở thành chi phí biên của một request mới.

Một request cache hit có thể không gọi model nhưng vẫn sử dụng backend, cache, lưu trữ và mạng. Một deployment nhàn vẫn có thể phát sinh phí công suất. Tránh tính hai lần cùng một khoản khi đã phân bổ chi phí cluster.

### 10.4. Bao gồm retry và các bước phụ

Chi phí luồng có thể gồm:

~~~text
C_total =
    C_model
  + C_retrieval
  + C_backend
  + C_storage_and_network
  + C_observability
  + C_evaluation
~~~

Đây là các nhóm chi phí cần phân định để tránh trùng lặp. Embedding, rerank, retry, công cụ do agent gọi hoặc model chấm có thể tạo thêm tiêu thụ.

Với yêu cầu bị hủy hoặc timeout, không mặc định công việc ở phía dịch vụ đã dừng và không phát sinh phí. Thu thập bằng chứng sử dụng khi có, giữ phần chưa rõ để đối soát.

## 11. Theo dõi chi phí trên một kết quả đạt yêu cầu

### 11.1. Hai mẫu số tạo ra hai kết luận khác nhau

~~~text
Chi phí trên logical request =
    chi phí của tập yêu cầu / tổng logical request trong tập đó

Chi phí trên kết quả đạt =
    chi phí của tập yêu cầu / số kết quả đạt yêu cầu trong cùng tập
~~~

Cần đưa chi phí của cả yêu cầu thất bại và kết quả không đạt vào tử số nếu chúng thuộc cùng tập công việc. Nếu không, hệ thống kém chất lượng có thể trông rẻ hơn vì bỏ sót phần tiêu thụ không tạo giá trị.

Nếu số kết quả đạt bằng 0, chỉ số không xác định; không hiển thị 0 như thể hệ thống không tốn chi phí.

### 11.2. Ví dụ so sánh hai cấu hình

Bảng dưới đây dùng dữ liệu giả lập, chi phí tính bằng **đơn vị tiền giả định**, đã phân bổ cùng phạm vi. Toàn bộ 10.000 yêu cầu của mỗi cấu hình đều đã được đánh giá theo cùng rubric.

| Chỉ số | Cấu hình A | Cấu hình B |
| --- | ---: | ---: |
| Logical request | 10.000 | 10.000 |
| Hoàn tất kỹ thuật | 9.600 | 9.800 |
| Kết quả đạt nghiệp vụ | 8.640 | 7.000 |
| Tổng chi phí | 120 | 100 |
| Chi phí / logical request | 0,012 | 0,010 |
| Chi phí / 1.000 kết quả đạt | Khoảng 13,89 | Khoảng 14,29 |

B có chi phí mỗi request thấp hơn nhưng chi phí cho 1.000 kết quả đạt cao hơn. Lựa chọn còn cần xét SLO hiệu năng, tiêu chí chất lượng tối thiểu và nhóm lỗi quan trọng.

Nếu chỉ chấm một mẫu nhỏ, không lấy tổng chi phí toàn hệ thống chia cho số kết quả đạt trong mẫu rồi gọi đó là chi phí chung. Hoặc báo chỉ số trong cùng mẫu với cách phân bổ phù hợp, hoặc ước lượng toàn bộ với phương pháp và mức bất định được công bố.

### 11.3. Gắn chi phí với chủ sở hữu

Có thể dùng compartment và defined tag để quy chi phí tài nguyên về dự án, môi trường hoặc nhóm phụ trách. Tag không nên chứa dữ liệu cá nhân. [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Tag của một tài nguyên dùng chung không tự phân tách được chi phí từng người dùng. Phần đó cần telemetry và quy tắc phân bổ của ứng dụng.

Khi đối soát, dùng cùng cửa sổ thời gian, quy ước UTC, region, tiền tệ và phạm vi dịch vụ. Phân biệt chi phí vận hành suy luận với huấn luyện, thử nghiệm hoặc đánh giá nếu đang làm báo cáo theo mục đích.

## 12. Dashboard và alarm phải dẫn đến hành động

### 12.1. Một dashboard nên nối ba chiều

| Nhóm hiển thị | Nội dung |
| --- | --- |
| Lưu lượng và tình trạng | Logical request, attempt, lỗi, timeout, throttling, hàng đợi |
| Trải nghiệm | p50/p95/p99 toàn luồng, TTFT nếu có, phân bố theo độ dài |
| Tài nguyên | CPU/GPU, RAM, băng thông, số instance hoặc công suất |
| Chất lượng | Tỷ lệ đạt, loại lỗi, cỡ mẫu, coverage, độ trễ nhãn |
| Chi phí | Token, ước tính gần thời gian thực, chi phí đã đối soát, chi phí/kết quả đạt |
| Phiên bản | Model, prompt, dữ liệu, cấu hình và mốc rollout |

Có thể đặt biểu đồ theo cùng trục thời gian và đánh dấu các lần thay model, tăng lưu lượng hoặc cập nhật kho tri thức. Khi chất lượng giảm sau một thay đổi, cần đối chiếu thêm nhóm dữ liệu và độ bao phủ đánh giá trước khi kết luận nguyên nhân.

### 12.2. Alarm cần cửa sổ, cỡ mẫu và người chịu trách nhiệm

| Tín hiệu | Điều kiện nên làm rõ | Hành động gợi ý |
| --- | --- | --- |
| Độ trễ tăng | Kéo dài bao lâu, nhóm nào bị ảnh hưởng | Xem hàng đợi, retrieval, token và tài nguyên |
| Lỗi hoặc 429 tăng | Lỗi theo attempt hay logical request | Giới hạn retry, kiểm tra quota/công suất và fallback |
| Chất lượng giảm | Đủ mẫu, cùng rubric, nhãn đã hoàn tất chưa | Điều tra dữ liệu và phiên bản; cân nhắc rollback |
| Token tăng đột ngột | Do lưu lượng hay token/request | Kiểm tra vòng lặp, prompt và số bước gọi |
| Chi phí đơn vị tăng | Cùng phạm vi phân bổ và chất lượng chưa | Tìm retry, công suất nhàn hoặc tỷ lệ không đạt |
| Telemetry biến mất | Có lưu lượng hoặc heartbeat được kỳ vọng không | Kiểm tra exporter, IAM, mạng và pipeline thu thập |

Các điều kiện định lượng cần dựa trên baseline. Một lỗi nghiêm trọng như lộ dữ liệu cần xử lý riêng theo mức độ, không chờ tích lũy đủ mẫu để tính tỷ lệ.

Monitoring hỗ trợ absence alarm để phát hiện metric không được phát trong khoảng kỳ vọng. Cần phân biệt việc không có request với mất đường quan sát. [Creating an Absence Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-absence.htm).

Sau khi tạo alarm, kiểm tra tuyến Notifications và người nhận trong môi trường phù hợp. Một alarm ở trạng thái firing nhưng không đến được người phụ trách chưa tạo ra khả năng phản ứng.

### 12.3. Budget không tự ngắt chi tiêu

OCI Budgets đặt ngưỡng mềm và phát cảnh báo trên chi phí; đó không phải cơ chế chặn tức thời một API call hoặc tự dừng cluster. [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

Để kiểm soát nhanh hơn, ứng dụng có thể áp dụng:

- Giới hạn độ dài đầu vào và đầu ra.
- Giới hạn số model call, retry và thời gian cho mỗi logical request.
- Hạn mức sử dụng theo nhóm hoặc route.
- Kiểm soát quyền tạo hoặc tăng tài nguyên.
- Cơ chế chuyển sang chức năng ít tốn tài nguyên hoặc hàng đợi khi đạt ngưỡng đã thống nhất.

Hạn mức dịch vụ hoặc quota không mặc định tương đương một mức tiền tối đa. Tài nguyên đã cấp và dữ liệu giữ lại có thể tiếp tục phát sinh phí.

## 13. Tối ưu mà vẫn giữ chất lượng và tính sẵn sàng

| Thay đổi | Lợi ích kỳ vọng | Điều phải đo lại |
| --- | --- | --- |
| Rút gọn ngữ cảnh | Giảm token và thời gian xử lý | Có mất bằng chứng hoặc thông tin bắt buộc không |
| Dùng model nhỏ hơn cho một số route | Giảm tiêu thụ hoặc độ trễ | Chất lượng theo từng nhóm và chi phí/kết quả đạt |
| Cache | Giảm gọi lặp | Độ mới, ranh giới quyền và lỗi dùng lại kết quả |
| Rerank trước khi sinh | Chọn ngữ cảnh liên quan hơn | Chi phí bước thêm và chất lượng cuối |
| Batch | Tăng hiệu quả cho tác vụ nền | Thời gian chờ và deadline nghiệp vụ |
| Tăng công suất hoặc scale | Giảm hàng đợi khi quá tải | Độ trễ, công suất nhàn và chi phí phân bổ |
| Giảm retry | Hạn chế khuếch đại tải | Khả năng hoàn tất trước deadline |
| Fallback | Duy trì chức năng khi lỗi | Chất lượng và tính nhất quán giữa các đường phục vụ |

Cache phải bao gồm những yếu tố quyết định kết quả như quyền, phiên bản dữ liệu và model/prompt khi cần. Không dùng chung câu trả lời có dữ liệu riêng giữa những người không có cùng quyền truy cập.

Retry cần có giới hạn và backoff phù hợp. Retry không giới hạn khi 429 tăng có thể làm cả chi phí lẫn độ trễ xấu hơn.

Khi rollout một cấu hình mới, so sánh trên nhóm tương đương, giữ phiên bản kiểm soát và đặt điều kiện rollback theo cả chất lượng, hiệu năng và chi phí. Nếu thử shadow, tính cả lượng gọi và chi phí phát sinh mà chưa trả kết quả cho người dùng.

Đừng chuyển region chỉ để giảm độ trễ hoặc tìm công suất mà bỏ qua quyền chuyển dữ liệu, khả năng cung cấp model và phụ thuộc của ứng dụng.

## 14. IAM, mạng và vòng đời dữ liệu quan sát

Người xem metric, người đọc nội dung đánh giá, workload phát metric và người thay đổi alarm có nhu cầu quyền khác nhau.

Ví dụ policy đọc metric trong một compartment:

~~~text
Allow group AiObservers to read metrics in compartment ai-prod
~~~

Quyền này không tự cấp quyền đọc prompt, nội dung log, bucket đánh giá hoặc quản lý endpoint. Có thể giới hạn namespace theo trường hợp cần thiết; chính sách Monitoring được mô tả trong [Securing Monitoring](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/monitoring_security.htm).

Workload phát custom metrics cần được xác thực và cấp đúng quyền. Nếu dùng instance principal hoặc resource principal, giới hạn dynamic group theo workload và môi trường; không nhúng API key cá nhân vào mã chỉ để gửi telemetry.

Kiểm tra riêng đường mạng tới Monitoring ingestion, Logging, kho đánh giá và dịch vụ model. Một workload trong private subnet phải có tuyến kết nối phù hợp cho từng đích.

Thiết kế vòng đời dữ liệu quan sát cần xác định:

- Trường nào được lưu trong log chung, trường nào chỉ nằm trong kho đánh giá hạn chế.
- Ai được xem nội dung, ai chỉ xem số tổng hợp.
- Thời hạn lưu prompt, phản hồi, nguồn truy xuất và nhãn.
- Cách xóa bản sao phát sinh trong log, object, báo cáo và bản sao lưu theo chính sách.
- Chi phí của log, metric, trace và các lần gọi đánh giá.

Giữ đủ bằng chứng cho việc điều tra mà không mặc định lưu mọi payload vô thời hạn.

## 15. Quy trình điều tra một bất thường

Ví dụ: dashboard báo chi phí trên kết quả đạt tăng trong hai ngày gần đây.

1. **Xác nhận phép đo:** cùng kỳ dữ liệu, tiền tệ, cách phân bổ, rubric và độ hoàn tất nhãn hay chưa?
2. **Tách lưu lượng với đơn vị tiêu thụ:** request tăng hay token/request tăng?
3. **Kiểm tra khuếch đại:** attempt/request, retry, số bước agent và cache hit thay đổi thế nào?
4. **Đối chiếu chất lượng:** số kết quả không đạt tăng ở route, ngôn ngữ hoặc nhóm đầu vào nào?
5. **Kiểm tra phiên bản:** model, prompt, knowledge base và cấu hình có đổi không?
6. **Xem hiệu năng và tài nguyên:** hàng đợi, timeout, độ trễ database, CPU/GPU và công suất nhàn.
7. **Kiểm tra chi phí đối soát:** có dữ liệu đến muộn, điều chỉnh hoặc khoản tài nguyên mới được phân bổ không?
8. **Thực hiện thay đổi có kiểm soát:** sửa nguồn lỗi, giới hạn khuếch đại, rollback hoặc điều chỉnh công suất theo bằng chứng.
9. **Xác nhận sau thay đổi:** cả chất lượng, hiệu năng và chi phí có trở về mục tiêu không?

Ví dụ, prompt mới đưa toàn bộ lịch sử hội thoại vào mỗi lần gọi có thể làm token tăng và độ trễ tăng. Cắt lịch sử tùy tiện có thể làm chất lượng giảm. Hướng sửa cần giữ phần ngữ cảnh hữu ích và đánh giá lại trên dữ liệu đại diện.

## 16. Thực hành xây một bộ theo dõi tối thiểu

Thực hành trong compartment học tập, bằng dữ liệu giả lập hoặc đã được cho phép. Các bước dưới đây là hướng dẫn cho người học, không phải thao tác đã được thực hiện trên tenancy.

### 16.1. Chọn tác vụ và định nghĩa phép đo

1. Chọn một endpoint Data Science hoặc một luồng dùng Generative AI được hỗ trợ.
2. Xác định logical request, model call, attempt và final response.
3. Viết rubric ngắn với tiêu chí bắt buộc.
4. Chọn SLI về hoàn tất, độ trễ, chất lượng và chi phí.
5. Ghi cách tính, đơn vị, mẫu số và cửa sổ của từng chỉ số.

### 16.2. Thu thập và liên kết dữ liệu

1. Quan sát metric gốc của tài nguyên trong đúng namespace, region và compartment.
2. Cấu hình log phù hợp và phát telemetry ứng dụng không chứa bí mật.
3. Gửi một tập yêu cầu đại diện với ID liên kết.
4. Ghi cả trường hợp thành công, lỗi có kiểm soát, retry và fallback.
5. Nối đánh giá vào đúng đầu ra cuối cùng.
6. Đối chiếu một số request từ bản ghi ứng dụng tới request ID của dịch vụ khi có.

### 16.3. Tạo dashboard và kiểm tra cảnh báo

1. Hiển thị logical request và attempt cạnh nhau.
2. Hiển thị độ trễ toàn luồng cạnh độ trễ dịch vụ.
3. Hiển thị tỷ lệ đạt cùng số mẫu và độ bao phủ.
4. Hiển thị token, chi phí ước tính và trạng thái đối soát.
5. Tạo alarm trong môi trường thử với điều kiện có thể kiểm chứng.
6. Kiểm tra cả thông báo tới người phụ trách và tình huống telemetry bị mất.

### 16.4. Đối soát và so sánh một thay đổi

1. Dùng cùng tập yêu cầu hoặc cách phân nhóm tương đương để so sánh hai cấu hình.
2. Ghi lại model, prompt và phiên bản dữ liệu.
3. Tính chi phí trên request và trên kết quả đạt trong cùng phạm vi.
4. So sánh hiệu năng, chất lượng và nhóm lỗi quan trọng.
5. Ghi rõ số liệu nào là ước tính, số liệu nào đã đối soát.
6. Kiểm tra tài nguyên và vòng đời log sau khi kết thúc thực hành.

Bộ theo dõi có giá trị khi giúp giải thích được **đầu ra nào suy giảm, bước nào gây chậm, khoản tiêu thụ nào tăng và thay đổi nào khôi phục mục tiêu**. Đó là cơ sở vận hành suy luận AI trên OCI với chất lượng, tính sẵn sàng và chi phí có thể kiểm soát.
