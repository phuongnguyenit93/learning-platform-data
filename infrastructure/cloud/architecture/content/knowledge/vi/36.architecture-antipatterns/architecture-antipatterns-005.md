# Retry không giới hạn, timeout thiếu nhất quán và lỗi dây chuyền

## 1. Bối cảnh: một lỗi nhỏ có thể trở thành sự cố toàn hệ thống

Một ứng dụng đám mây thường gồm nhiều thành phần gọi nhau: API Gateway chuyển yêu cầu đến dịch vụ nghiệp vụ; dịch vụ này gọi cơ sở dữ liệu, bộ nhớ đệm, hệ thống thanh toán và một hoặc nhiều API bên ngoài. Mạng không đáng tin cậy tuyệt đối: kết nối có thể bị ngắt, dịch vụ phụ thuộc có thể quá tải, quá trình truy vấn có thể chậm bất thường hoặc một instance có thể khởi động lại.

**Retry** (thử lại) và **timeout** (giới hạn thời gian chờ) là công cụ cần thiết để chịu lỗi tạm thời. Tuy nhiên, khi triển khai không có chính sách chung, chính hai công cụ này lại khuếch đại sự cố:

- **Retry không giới hạn:** một yêu cầu thất bại được thử lại liên tục, không xét thời hạn, số lượt thử hay sức khỏe của dịch vụ phía sau.
- **Timeout thiếu nhất quán:** mỗi tầng đặt thời gian chờ độc lập, có tầng không có timeout, hoặc tổng thời gian dành cho các lời gọi con vượt thời gian yêu cầu của người dùng.
- **Lỗi dây chuyền (*cascading failure*):** một thành phần chậm hoặc lỗi khiến các thành phần khỏe mạnh khác cạn tài nguyên, quá tải và lần lượt ngừng đáp ứng.

Trong chương **Phản mẫu kiến trúc** của module **CLOUD_ARCHITECTURE**, bài này hướng dẫn nhận diện ba vấn đề trên, mô tả cách chúng tương tác và thiết kế phương án thay thế từ **yêu cầu nghiệp vụ** đến **network, compute, dữ liệu và mô hình triển khai**. Việc lựa chọn phải cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy **Well-Architected**.

**Mục tiêu sau bài học:** giải thích được vì sao retry gây bão lưu lượng; thiết lập timeout theo ngân sách thời gian đầu-cuối; phân biệt lỗi nên và không nên retry; phối hợp backoff, jitter, circuit breaker, giới hạn đồng thời và cơ chế suy giảm có kiểm soát; đọc chỉ số để phát hiện và khoanh vùng lỗi dây chuyền.

> **Tư tưởng trung tâm:** Retry chỉ có ích khi nguyên nhân lỗi có khả năng tự hồi phục, một lần thử khác có cơ hội thành công, và hệ thống có đủ **thời gian lẫn tài nguyên** cho lần thử ấy. Nếu những điều kiện này không đúng, retry tiếp tục thường làm sự cố nặng hơn.

## 2. Ví dụ xuyên suốt: dịch vụ đặt hàng

Giả sử nền tảng bán hàng có chuỗi xử lý đồng bộ như sau:

~~~mermaid
flowchart LR
    C["Ứng dụng khách hàng"] --> G["API Gateway"]
    G --> O["Order API"]
    O --> I["Inventory Service"]
    O --> P["Payment Service"]
    P --> B[("Payment Provider")]
    O --> D[("Order Database")]
    I --> R[("Inventory Database")]
~~~

Yêu cầu nghiệp vụ giả định:

| Yêu cầu | Mục tiêu minh họa | Hệ quả thiết kế |
|---|---|---|
| Người dùng | Gửi yêu cầu đặt hàng và nhận phản hồi trong tối đa 2 giây ở phần lớn các trường hợp | Đặt **deadline đầu-cuối**; giới hạn công việc được phép nằm trong đường gọi đồng bộ |
| Tính đúng | Không tạo hai đơn hoặc thu tiền hai lần | Idempotency key, trạng thái nghiệp vụ, xử lý trạng thái kết quả không rõ |
| Độ tin cậy | Lỗi mạng ngắn không làm hỏng mọi giao dịch | Retry có điều kiện, giới hạn lần thử và tổng thời gian |
| Khi dịch vụ ngoài lỗi | Hệ thống tiếp tục cho phép xem giỏ hàng và lịch sử | Cách ly tài nguyên, trả lỗi có kiểm soát, giảm cấp chức năng |
| Vận hành | Phát hiện trước khi thread/connection pool cạn | Metrics ở từng hop, tracing, cảnh báo và giới hạn tải |

Đây là **giả định cho bài tập**, không phải SLO chung cho mọi dịch vụ. Thanh toán có side effect và yêu cầu chính xác về nghiệp vụ cao hơn nhiều so với thao tác đọc danh mục sản phẩm; chính sách retry phải khác nhau.

## 3. Retry không giới hạn phá hỏng điều gì?

### 3.1. Cơ chế khuếch đại tải

Khi dịch vụ thanh toán quá tải, độ trễ tăng và xuất hiện timeout. Nếu Order API lập tức retry tất cả yêu cầu thất bại, Payment Service nhận lưu lượng mới **cộng thêm** lưu lượng thử lại. Nhiều yêu cầu đang chờ đồng thời chiếm connection, memory, worker thread; dịch vụ thanh toán phải phục vụ nhiều việc hơn đúng lúc nó có ít năng lực hơn.

Với tốc độ yêu cầu gốc **100 request/giây**, nếu mỗi yêu cầu tạo **tối đa ba lần thử tổng cộng** và mọi lần đều thất bại, phía sau có thể nhận **300 attempt/giây** trước khi tính thêm retry tại các lớp khác. Nếu Gateway cũng thử lại ba lần đối với toàn bộ lời gọi Order API, một request ở biên có thể dẫn tới **9 attempt** ở Payment Service. Nếu một tầng nữa cũng thử ba lần, trường hợp cực đoan có thể lên tới **27 attempt**. Đây là số nhân lý thuyết khi toàn bộ nhánh lỗi kích hoạt retry, không phải hệ số tải cố định trong mọi hệ thống.

~~~mermaid
flowchart TB
    A["1 yêu cầu người dùng"] --> G1["Gateway: thử 1"]
    A --> G2["Gateway: thử 2"]
    A --> G3["Gateway: thử 3"]
    G1 --> O1["Order API: 3 lần gọi"]
    G2 --> O2["Order API: 3 lần gọi"]
    G3 --> O3["Order API: 3 lần gọi"]
    O1 --> P["Payment: tối đa 9 lần gọi"]
    O2 --> P
    O3 --> P
~~~

Sơ đồ giả định mỗi lượt thử tại Gateway dẫn đến ba lượt thử tại Order API; các chuỗi retry nối tiếp nhau, không nhất thiết chạy song song. Khi service chậm chứ không trả lỗi nhanh, yêu cầu gốc có thể đã hết hạn trong khi nhiều lượt xử lý phía sau vẫn tiếp tục chạy.

### 3.2. Vì sao retry tức thì nguy hiểm?

Sau sự cố ngắn, hàng nghìn client cùng thử lại ở cùng mốc thời gian gây **thundering herd**: tải tăng vọt theo đợt. Retry **không có khoảng lùi** hoặc có khoảng lùi giống hệt nhau khiến các đợt thử lại đồng bộ, tạo dao động tải và làm dịch vụ khó phục hồi.

Retry liên tục cũng có thể gây:

- **Retry storm:** số request thử lại vượt xa request nghiệp vụ mới.
- **Tài nguyên bị giữ lâu:** thread, goroutine, connection pool, bộ nhớ và hàng chờ tăng theo số yêu cầu còn đang chạy.
- **Dữ liệu trùng hoặc sai:** thực hiện lại thao tác không idempotent như tạo đơn/thu tiền có thể tạo side effect thứ hai.
- **Chi phí tăng:** thêm request tới API trả phí, query, log, compute và lưu lượng giữa vùng/region.
- **Che giấu nguyên nhân:** metric cuối cùng chỉ ghi “thành công sau retry” dù hệ thống phía sau đã ở tình trạng bất ổn.

**Dấu hiệu rõ nhất của phản mẫu:** vòng lặp retry vô hạn, không giới hạn thời gian, không giới hạn lượt thử, không backoff, hoặc retry lỗi do xác thực, dữ liệu sai và logic nghiệp vụ như thể đó là lỗi hạ tầng.

## 4. Timeout thiếu nhất quán: hết hạn ở ngoài, vẫn chạy ở trong

### 4.1. Phân biệt các loại thời gian chờ

| Cơ chế | Giới hạn điều gì? | Ví dụ rủi ro nếu thiếu |
|---|---|---|
| **Connect timeout** | Thời gian thiết lập kết nối mạng | Kết nối đến một đích lỗi giữ socket quá lâu |
| **TLS handshake timeout** | Thời gian bắt tay TLS, nếu client hỗ trợ cấu hình riêng | Request kẹt trong bước thiết lập kết nối an toàn |
| **Read/response timeout** | Thời gian chờ dữ liệu/phản hồi, phụ thuộc semantics SDK | Đã kết nối nhưng server không gửi dữ liệu |
| **Per-attempt timeout** | Thời gian tối đa cho **một** lần thử | Một attempt chậm tiêu hết toàn bộ thời gian người dùng có thể chờ |
| **Overall timeout / deadline** | Thời hạn cho **tổng** công việc, bao gồm retry/backoff | Nhiều attempt liên tiếp vượt xa SLO đầu-cuối |
| **Queue/worker timeout** | Thời gian chờ và chạy xử lý nền | Công việc tồn tại vô hạn, bít worker hoặc queue |

Một số HTTP client định nghĩa *socket timeout* là **khoảng không có dữ liệu** giữa các lần đọc, không phải tổng thời gian nhận toàn bộ response. Không được xem một setting có chữ “timeout” là đã bảo vệ toàn bộ đường đi. Phải kiểm tra đúng semantics của HTTP client, SDK, proxy, gateway và service mesh đang dùng.

### 4.2. Ví dụ xung đột deadline

Giả sử:

~~~text
Gateway timeout                    = 2.0 giây
Order API timeout gọi Payment       = 3.0 giây / attempt
Payment SDK retry                   = 3 attempt
Khoảng backoff                       = 0.2 giây rồi 0.4 giây
Thời gian tối đa phía Payment       = 3 + 0.2 + 3 + 0.4 + 3 = 9.6 giây
~~~

Gateway đã ngừng đợi ở giây thứ 2, nhưng Order API có thể vẫn bận xử lý Payment gần 10 giây nếu không nhận và tôn trọng tín hiệu hủy. Người dùng thấy lỗi rồi bấm gửi lại; hệ thống có thể đang xử lý yêu cầu cũ và yêu cầu mới cùng lúc.

**Giải pháp chính:** gán **deadline tuyệt đối cho mỗi yêu cầu ở biên hệ thống**, sau đó truyền ngân sách thời gian còn lại xuống các tầng. Mỗi tầng phải trừ thời gian đã tiêu tốn; thời gian gọi downstream phải **nhỏ hơn hoặc bằng phần ngân sách còn lại**, chừa thời gian cho nghiệp vụ và tạo phản hồi. Khi deadline đã hết, không bắt đầu attempt mới.

Một cách minh họa:

~~~text
deadline của request = thời điểm nhận + 2_000 ms
thời gian đã dùng cho auth/DB = 350 ms
ngân sách còn lại = 1_650 ms
dành 150 ms để tổng hợp kết quả và trả response
ngân sách tối đa cho Payment = 1_500 ms, gồm cả retry và backoff
~~~

Không có “magic number” đúng cho mọi hệ thống: ngân sách cần dựa trên SLO, độ trễ phân vị cao của từng dependency, độ biến động và yêu cầu nghiệp vụ. Đồng hồ của các host có thể lệch; khi truyền **absolute deadline** qua mạng phải xét đồng bộ thời gian, còn code nội bộ nên dùng cơ chế đo thời gian đơn điệu (*monotonic clock*) cho duration khi nền tảng hỗ trợ.

### 4.3. Timeout không tự hủy việc ở downstream

Client ngừng chờ không đồng nghĩa server dừng tính toán hoặc transaction đã rollback. Muốn giảm lãng phí tài nguyên, cần:

1. Truyền **cancellation/deadline context** qua các API và thư viện có hỗ trợ.
2. Ở backend, dừng những công việc không còn cần thiết và giải phóng connection, thread, memory, lock.
3. Phân biệt tác vụ **có thể hủy** với side effect không được phép dừng giữa chừng, chẳng hạn lệnh thanh toán đã gửi.
4. Với kết quả không chắc chắn, **tra cứu trạng thái bằng request/idempotency key** hoặc chạy đối soát trước khi phát hành thao tác mới.

Một timeout sau khi gửi lệnh thanh toán là **kết quả chưa rõ**, không thể suy ra “thanh toán chưa diễn ra”. Retry thao tác có side effect cần idempotency được **phía nhận** bảo đảm, không chỉ bằng việc tạo một key ở phía gọi.

## 5. Lỗi dây chuyền xảy ra như thế nào?

~~~mermaid
flowchart TD
    A["Payment Provider chậm"] --> B["Payment Service giữ nhiều request"]
    B --> C["Connection / thread pool đầy"]
    C --> D["Request mới phải xếp hàng"]
    D --> E["Độ trễ và timeout tăng"]
    E --> F["Client, Gateway, Order API retry"]
    F --> G["Số attempt tới Payment tăng"]
    G --> B
    C --> H["Order API thiếu worker phục vụ yêu cầu khác"]
    H --> I["Chức năng không liên quan cũng chậm/lỗi"]
~~~

**Vòng phản hồi dương** làm lỗi tại một dependency lan sang cả dịch vụ gọi nó. Hàng đợi dài không có giới hạn có thể trì hoãn thông báo quá tải, nhưng không tạo thêm năng lực xử lý. Autoscaling cũng không cứu được hệ thống ngay nếu tốc độ tăng tải nhanh hơn thời gian khởi động instance, hoặc dependency chung như database vẫn là nút thắt cổ chai.

### Mô hình định lượng tối giản

Theo định luật Little, trong điều kiện ổn định:

\[
L = \lambda W
\]

Trong đó **L** là số request trung bình đang ở hệ thống, **λ** là throughput trung bình và **W** là thời gian trung bình một request tồn tại. Giả sử 200 request/giây có thời gian chờ tăng từ 0,1 giây lên 3 giây:

- Ban đầu: khoảng \(L = 200 \times 0{,}1 = 20\) yêu cầu đồng thời.
- Khi dependency chậm: khoảng \(L = 200 \times 3 = 600\) yêu cầu đồng thời, nếu lưu lượng được nhận và xử lý trong trạng thái ổn định.

Nếu pool chỉ chịu được 100 lời gọi đồng thời, phần vượt quá sẽ xếp hàng hoặc bị từ chối. Khi retry tiếp tục làm tăng tốc độ đến, hệ thống có thể **không còn trạng thái ổn định**; lúc đó không được áp dụng công thức trên để dự đoán chính xác queue vô hạn. Nó chỉ minh họa vì sao **độ trễ tăng gây áp lực concurrency** ngay cả trước khi có retry.

### Phân biệt lỗi cục bộ và lỗi lan truyền

| Mức độ | Biểu hiện | Ý nghĩa |
|---|---|---|
| **Lỗi cục bộ** | Payment Provider trả 503 cho một số lệnh | Một dependency đang lỗi, các dịch vụ khác có thể vẫn khỏe |
| **Suy giảm ở dịch vụ gọi** | Order API tăng latency, chạm giới hạn connection | Tài nguyên của Order API bị dependency kéo theo |
| **Lỗi dây chuyền** | Order API 503 hàng loạt; API giỏ hàng cũng chậm vì dùng chung pool | Phạm vi lỗi đã vượt khỏi tác vụ thanh toán |
| **Sự cố toàn vùng/hệ thống** | Nhiều instance/zone cùng quá tải do retry, backend chung hoặc chuyển vùng đồng loạt | Cần cô lập tải, failover có kiểm soát, bảo vệ dependency |

Đặc biệt nguy hiểm là **retry cùng một lỗi ở nhiều tầng** và **failover không có giới hạn**, ví dụ chuyển toàn bộ traffic sang một region dự phòng chưa được cấp đủ năng lực rồi lại retry tại đó.

## 6. Phân loại lỗi trước khi quyết định retry

Không phải lỗi nào cũng nên thử lại. **Khả năng retry còn phụ thuộc loại thao tác, tính idempotent, số lần thử trước đó, deadline và tín hiệu sức khỏe hiện tại**, không chỉ status code.

| Trường hợp | Retry? | Lý do và điều kiện |
|---|---|---|
| Lỗi kết nối thoáng qua trước khi request được gửi | Có thể | Hành vi phù hợp với thao tác an toàn, còn deadline và retry budget |
| HTTP 429 kèm **Retry-After** | Có điều kiện | Tôn trọng thời điểm đề nghị; chỉ thử nếu deadline còn đủ và chính sách cho phép |
| HTTP 503 hoặc 502 do lỗi tạm thời | Có điều kiện | Giới hạn lượt, dùng backoff+jitter; nếu service đang quá tải, giảm số attempt |
| HTTP 500 | Phụ thuộc | Có thể do bug bền vững; không mặc định retry mọi 500 |
| HTTP 400/401/403 do dữ liệu, quyền hoặc token không hợp lệ | Thường không | Cần sửa request/quyền, lặp lại không giúp; riêng 401 do token hết hạn có thể qua luồng làm mới credential được kiểm soát |
| HTTP 404 | Phụ thuộc ngữ cảnh | Không retry nếu tài nguyên chắc chắn không tồn tại; có thể retry ngắn nếu biết dữ liệu xuất hiện trễ theo eventual consistency |
| Lỗi validate dữ liệu, quota nghiệp vụ, hết tồn kho | Không | Lặp lại cùng yêu cầu khó làm thay đổi kết quả; xử lý ở tầng nghiệp vụ |
| Timeout sau khi gửi yêu cầu thanh toán | Không retry mù | Kết quả **unknown**; tra cứu giao dịch hoặc dùng idempotency key được provider hỗ trợ |
| Read-only GET, không gây side effect | Thường an toàn hơn | Vẫn cần tránh retry storm, giới hạn thời gian và tài nguyên |
| DELETE/PUT có semantics idempotent theo hợp đồng API | Có thể | Phải xác minh backend thực sự xử lý lặp an toàn |

Chú ý: **POST không mặc định an toàn để retry**. API dùng POST vẫn có thể an toàn khi tích hợp idempotency key với lưu trạng thái bền vững; ngược lại một số thao tác tưởng là read-only có thể gây tác động bên ngoài nếu API thiết kế không đúng.

## 7. Chính sách retry có giới hạn

Một chính sách thực tế có thể gồm sáu điều kiện:

1. **Giới hạn tổng số attempt** (ví dụ 2 hoặc 3, tính cả lần đầu).
2. **Giới hạn tổng thời gian** bằng deadline của request hoặc ngân sách con được cấp.
3. **Retry chỉ khi lỗi được phân loại là tạm thời và thao tác có thể lặp an toàn.**
4. **Exponential backoff có jitter** để phân tán thời điểm thử lại.
5. **Retry budget/token bucket** để chặn tổng lưu lượng retry khi tỷ lệ lỗi tăng mạnh.
6. **Chỉ định tầng sở hữu retry**, tránh các lớp cùng nhân số attempt ngoài ý muốn.

### Exponential backoff và jitter

Một dạng thường dùng:

\[
d_n \sim \operatorname{Uniform}(0,\ \min(d_{\max}, d_0 2^{n-1}))
\]

Với \(n\) là thứ tự **lần retry** (bắt đầu từ 1), \(d_0\) là khoảng nền và \(d_{\max}\) là trần. Đây là biến thể **full jitter**; công thức minh họa cách phân tán khoảng chờ chứ không bảo đảm loại bỏ hoàn toàn tải đỉnh.

Ví dụ \(d_0 = 100\) ms, \(d_{\max} = 800\) ms:

| Lần retry | Trần backoff | Khoảng chờ ngẫu nhiên |
|---|---:|---|
| 1 | 100 ms | 0–100 ms |
| 2 | 200 ms | 0–200 ms |
| 3 | 400 ms | 0–400 ms |
| 4 | 800 ms | 0–800 ms |
| 5+ | 800 ms | 0–800 ms |

**Không được ngủ đến hết backoff nếu deadline đã đến.** Nếu server cung cấp Retry-After, cần cân nhắc giá trị đó cùng ngân sách thời gian và giới hạn chính sách; một response 429 không có nghĩa được phép vượt deadline để retry.

### Retry budget

Retry budget là giới hạn lượng công việc retry được hệ thống chấp nhận trong một cửa sổ thời gian, ví dụ tỷ lệ retry tối đa so với request gốc hoặc một token bucket riêng. Đây là **cơ chế bảo vệ**, không phải mục tiêu phải tiêu hết.

Ví dụ minh họa: ứng dụng nhận 1.000 request mới/phút, quy định tối đa **100 retry attempt/phút** trên tuyến gọi dễ lỗi. Khi đã dùng hết budget, yêu cầu mới được trả lỗi hoặc chuyển sang luồng xử lý bền vững tùy nghiệp vụ, thay vì tiếp tục khuếch đại tải. Cần chọn ngưỡng bằng dữ liệu thực, không sao chép 10% cho mọi dependency.

### Quyền quyết định retry thuộc tầng nào?

Trong hệ thống đồng bộ nhiều hop, thường nên đặt một chính sách **ở nơi biết rõ ý nghĩa nghiệp vụ, deadline và idempotency**, sau đó cấu hình các SDK/proxy bên dưới để không retry độc lập vượt ngân sách. Có thể giữ retry ở tầng thấp đối với một lỗi kết nối đặc biệt, nhưng **tổng attempt phải được tính chung**.

Nếu retry có side effect lớn hoặc thời gian dài, hãy cân nhắc chuyển thành **job bất đồng bộ bền vững**, có ID và trạng thái, thay vì giữ kết nối HTTP trong nhiều phút. Queue có retry và DLQ cũng cần hạn mức để không tạo vòng lặp vô hạn.

## 8. Mẫu triển khai: deadline, retry và kết quả nghiệp vụ

Mã giả sau minh họa một thao tác đọc phụ thuộc có thể lặp an toàn. Đây là **pseudocode độc lập ngôn ngữ**, không phải đoạn mã chạy ngay trong một SDK cụ thể:

~~~text
function call_dependency(request, parent_deadline):
    MAX_ATTEMPTS = 3                   # tính cả lần gọi đầu
    PER_ATTEMPT_CAP = 500ms
    RESERVED_FOR_RESPONSE = 100ms
    MINIMUM_ATTEMPT_TIME = 50ms        # ngưỡng khởi chạy hữu ích, ví dụ

    for attempt in 1..MAX_ATTEMPTS:
        remaining = parent_deadline - monotonic_now()
        if remaining <= RESERVED_FOR_RESPONSE:
            return DEADLINE_EXCEEDED

        if circuit_breaker.is_open():
            return DEPENDENCY_UNAVAILABLE

        if not concurrency_limiter.try_acquire():
            return OVERLOADED

        try:
            attempt_timeout = min(
                PER_ATTEMPT_CAP,
                remaining - RESERVED_FOR_RESPONSE
            )
            result = dependency.call(
                request,
                timeout=attempt_timeout,
                cancellation=parent_deadline
            )
            record_attempt_success()
            return result
        catch error:
            record_attempt_failure(error)
            if not is_transient(error):
                raise error
            if attempt == MAX_ATTEMPTS:
                raise error
            if not retry_budget.try_consume_token():
                raise RETRY_BUDGET_EXHAUSTED
        finally:
            concurrency_limiter.release()

        backoff = full_jitter(base=100ms, cap=500ms, retry_no=attempt)
        if monotonic_now() + backoff + MINIMUM_ATTEMPT_TIME >=
           parent_deadline - RESERVED_FOR_RESPONSE:
            return DEADLINE_EXCEEDED
        sleep_cancellable(backoff, parent_deadline)

    return UNEXPECTED_STATE
~~~

Các quyết định quan trọng:

- **Timeout của từng attempt** không được vượt thời gian còn lại.
- **Giới hạn đồng thời** trả lỗi/giảm tải trước khi pool bị chiếm toàn bộ.
- **Retry budget** được kiểm tra trước lượt retry; cả lượt đầu và lượt retry đều bị deadline chi phối.
- **Sleep có thể hủy** khi client không còn chờ hoặc deadline đến.
- **Metric có phân biệt** lượt đầu, lượt retry và lý do dừng.
- **Cấu hình của SDK bên dưới** phải phối hợp để không có retry ẩn làm vượt MAX_ATTEMPTS.

Với thao tác thanh toán, luồng xử lý phải bổ sung idempotency key, ghi lại ý định thanh toán và bước **query/reconcile** trạng thái **UNKNOWN**. Nếu không có sự bảo đảm từ nhà cung cấp thanh toán, retry đơn giản như mã giả trên là không đủ an toàn.

## 9. Thiết kế timeout theo ngân sách đầu-cuối

### Bắt đầu từ SLO thay vì copy một con số

Giả sử mục tiêu minh họa là **phản hồi trong 2 giây** cho đường tạo đơn đồng bộ. Một phương án phân bổ sơ bộ:

| Bước trên đường đồng bộ | Ngân sách tối đa minh họa |
|---|---:|
| Gateway, xác thực và routing | 150 ms |
| Kiểm tra dữ liệu và đọc tồn kho | 300 ms |
| Xử lý Payment, gồm retry/backoff | 1.000 ms |
| Ghi trạng thái Order DB | 250 ms |
| Dự phòng cho jitter, serialization và mạng | 300 ms |
| **Tổng** | **2.000 ms** |

Bảng là **ngân sách tuần tự để minh họa cách tính**, không phải phép cộng cố định cho mọi luồng. Nếu thực hiện các bước **song song**, thời gian nhánh song song chịu chi phối bởi nhánh chậm nhất cộng chi phí phối hợp; nếu các bước có nhiều nhánh điều kiện, cần phân bổ cho đường đi thực tế. Một request đã dùng 500 ms trước khi gọi Payment chỉ còn 1.500 ms tổng, ngay cả khi cấu hình Payment bình thường cho phép 1.000 ms.

### Cấu hình tại nhiều tầng

~~~mermaid
flowchart LR
    U["Client deadline: 2.0s"] --> G["Gateway: 1.9s còn lại"]
    G --> O["Order API: 1.7s còn lại"]
    O --> P["Payment call: <= 1.0s"]
    P --> X["Provider attempt: <= 0.5s"]
~~~

Các con số trong sơ đồ là ví dụ **ngân sách còn lại**, không phải các timeout độc lập có thể cộng lại. Tầng sau phải biết deadline cấp trên hoặc được cấp timeout nhỏ hơn. Cần tính cả thời gian xếp hàng trong ingress, service mesh, proxy và connection pool; một timeout chỉ bắt đầu khi request được gửi đi có thể bỏ sót thời gian đã đợi trước đó.

**Nguyên tắc thiết kế:**

1. Định nghĩa SLO người dùng cần, rồi lựa chọn **overall deadline** ở biên.
2. Phân bổ ngân sách theo hành trình xử lý và độ trễ thực tế của dependency.
3. Đặt **connect timeout ngắn hợp lý**, **per-attempt timeout** và **overall deadline** riêng.
4. Truyền deadline/cancellation qua RPC, HTTP, async job khi giao thức hỗ trợ.
5. Không mở retry sau khi tổng thời gian còn lại không đủ cho một attempt có ích.
6. Cẩn trọng với kết quả nghiệp vụ không rõ khi timeout xảy ra sau side effect.

Nếu cần đảm bảo giao dịch dài hơn khả năng chờ của người dùng, đổi hợp đồng API sang **202 Accepted + operationId** (nếu phù hợp chuẩn giao thức) và tra cứu/trả thông báo trạng thái, thay vì cố tăng mọi timeout.

## 10. Các cơ chế cô lập để chặn lỗi dây chuyền

### 10.1. Circuit breaker

Circuit breaker theo dõi tình trạng lỗi/chậm của dependency. Khi vượt ngưỡng, chuyển từ **CLOSED** (cho request đi qua) sang **OPEN** (từ chối nhanh), sau thời gian nhất định chuyển sang **HALF_OPEN** để cho một số request kiểm tra khả năng phục hồi.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Lỗi/timeout vượt ngưỡng
    OPEN --> HALF_OPEN: Hết thời gian chờ mở mạch
    HALF_OPEN --> CLOSED: Số lần thử kiểm tra thành công
    HALF_OPEN --> OPEN: Thử kiểm tra thất bại
~~~

Circuit breaker tránh gửi thêm request vào dependency đang không đáp ứng. **Nó không tự sửa lỗi** và ngưỡng quá nhạy có thể làm dịch vụ bị từ chối quá mức. Phải tách mạch cho các dependency có hành vi khác nhau, ghi metrics và tránh để mọi instance cùng half-open một lúc tạo đợt probe lớn.

### 10.2. Bulkhead và giới hạn đồng thời

Mẫu **bulkhead** chia tài nguyên (thread pool, connection pool, worker slots hoặc semaphore) theo nhóm chức năng/dependency. Ví dụ Payment chỉ được chiếm tối đa 40 trong 100 slot xử lý, để các API xem giỏ hàng và tra cứu lịch sử còn năng lực phục vụ.

**Concurrency limit** bảo vệ tài nguyên hữu hạn; **rate limit** hạn chế lượng yêu cầu theo thời gian. Hai cơ chế bổ trợ nhau, không thay thế nhau. Khi không đủ slot, trả lỗi nhanh hoặc đưa vào hàng đợi **có giới hạn**; queue vô hạn chỉ chuyển vấn đề từ pool sang memory/latency.

### 10.3. Load shedding và backpressure

Khi nhu cầu vượt năng lực, hệ thống cần **từ chối một phần tải** có kiểm soát, ưu tiên giao dịch quan trọng hoặc đề nghị client thử lại sau. Nút nghẽn phải có cách truyền tín hiệu ngược về upstream: 429/503 có ý nghĩa, thông tin Retry-After nếu phù hợp, hạn mức từ Gateway, hoặc giảm tốc độ consumer đọc queue.

Không nên phản hồi 200/202 cho công việc chưa được lưu bền vững nếu hệ thống không có khả năng thực hiện và truy xuất trạng thái. Điều này chuyển lỗi từ rõ ràng sang âm thầm.

### 10.4. Fallback và suy giảm chức năng

Khi Payment lỗi, hệ thống có thể vẫn cho phép người dùng **xem sản phẩm và giỏ hàng**. Một số nghiệp vụ cho phép lưu đơn ở trạng thái **PENDING_PAYMENT** để xử lý sau; nhưng chỉ làm vậy khi hợp đồng nghiệp vụ, khả năng dự trữ tồn kho, chống trùng và thời hạn giao dịch cho phép. **Không được giả thành công thanh toán** chỉ để cải thiện tỷ lệ phản hồi HTTP 200.

Fallback sang dữ liệu cache cũ phù hợp hơn với danh mục/giá tham khảo, cần hiển thị tuổi dữ liệu nếu có rủi ro; không được lấy số dư, hạn mức tín dụng hay kết quả thu tiền từ cache cũ mà không có quy định nghiệp vụ rõ ràng.

### 10.5. Chuyển công việc dài sang bất đồng bộ

Với tác vụ có thể xử lý sau (gửi email, tạo báo cáo, đồng bộ chỉ mục), dùng **queue bền vững + worker + DLQ** để tách tốc độ nhận và xử lý. Cần idempotency, giới hạn retry, timeout mỗi job, giới hạn độ tuổi công việc và cơ chế đối soát. **Hàng đợi không loại bỏ lỗi**, mà cung cấp khoảng đệm và cơ chế phục hồi có kiểm soát.

## 11. Network, compute, dữ liệu và triển khai: đánh đổi cụ thể

| Quyết định kiến trúc | Lợi ích | Rủi ro/đánh đổi cần đo |
|---|---|---|
| Tách traffic có ưu tiên bằng gateway/rate limiting | Bảo vệ API quan trọng trước traffic thấp ưu tiên | Chính sách sai có thể chặn người dùng hợp lệ |
| Bật timeout và retry ở service mesh/proxy | Thiết lập thống nhất tại biên kết nối, dễ quan sát | Retry ẩn nhân với retry SDK; proxy không hiểu idempotency nghiệp vụ |
| Tách pool cho Payment, Inventory và chức năng đọc | Giảm blast radius giữa dependency | Tăng chi phí/mức phức tạp cấu hình và capacity planning |
| Autoscale compute theo request/concurrency hoặc queue age | Đáp ứng tăng tải | Khởi động chậm, quota và dependency chung vẫn có thể nghẽn |
| Dùng cache cho thao tác đọc phù hợp | Giảm số lần gọi DB hoặc dịch vụ phụ thuộc | Dữ liệu cũ; cache miss đồng loạt gây stampede |
| Tách database/connection pool cho workload khác nhau | Giảm cạnh tranh tài nguyên | Dữ liệu và consistency phức tạp hơn; thêm chi phí |
| Async job cho việc không bắt buộc hoàn tất đồng bộ | Giảm thời gian giữ HTTP connection, hấp thụ spike | Trạng thái eventual consistency và quy trình xử lý lỗi phức tạp |
| Multi-zone hoặc multi-region failover | Khả năng chống một vùng lỗi | Rủi ro chuyển tải dồn vào vùng còn lại; chi phí, dữ liệu và quyền truy cập |

**Góc nhìn network:** đặt timeout ở cả tầng ứng dụng và thành phần mạng thích hợp; bảo đảm proxy/load balancer không có chính sách mâu thuẫn với deadline. Timeout kết nối trong mạng riêng, qua NAT, DNS, TLS hay load balancer có thể biểu hiện khác nhau. Tách network zone giúp kiểm soát truy cập, nhưng không bảo vệ khỏi retry storm nếu mọi dịch vụ vẫn sử dụng chung một dependency.

**Góc nhìn compute:** theo dõi giới hạn concurrent requests, số worker, connection pool và thời gian khởi động autoscaling. Tăng số instance Order API trong khi Payment là nút thắt có thể chỉ làm Payment quá tải nhanh hơn.

**Góc nhìn dữ liệu:** giao dịch DB, lock, connection pool và cơ chế cấp khóa idempotency phải được thiết kế cho request có thể lặp. Nếu một transaction đã commit nhưng client timeout trước khi nhận response, hệ thống cần trả lại **kết quả đã lưu** khi nhận cùng idempotency key.

**Góc nhìn triển khai:** cấu hình retry/timeout phải có chủ sở hữu rõ ràng và được kiểm thử cùng SDK, ingress, mesh, load balancer và worker. Một thay đổi nhỏ trong default của client thư viện có thể làm số attempt thực tế tăng đáng kể.

## 12. Cách triển khai tính đúng cho thao tác có side effect

Một nguy cơ đặc biệt của timeout là **kết quả không xác định** (*ambiguous outcome*): client không nhận được phản hồi, nhưng server đã có thể hoàn thành.

Ví dụ:

~~~text
Client gửi POST /payments với idempotencyKey = order-824
Payment Service nhận và bắt đầu thu tiền
Provider xác nhận thành công, Payment Service lưu kết quả
Kết nối phản hồi bị ngắt trước khi Client nhận HTTP 200
Client thấy timeout và gửi lại yêu cầu cùng idempotencyKey
Server tìm thấy kết quả đã ghi và trả lại kết quả tương ứng
~~~

Một mô hình thực thi:

1. Backend kiểm tra quyền người gọi, nội dung request và **idempotency key**.
2. Tạo bản ghi bền vững có unique constraint cho key trong phạm vi tenant/nghiệp vụ; lưu fingerprint của payload. Với cùng key nhưng payload khác, **trả lỗi xung đột**.
3. Khi retry cùng key, nếu yêu cầu trước **đã hoàn thành**, trả lại kết quả lưu; nếu **đang xử lý**, trả trạng thái chờ hoặc hướng dẫn tra cứu thay vì thực hiện side effect mới.
4. Với kết quả provider **không rõ**, truy vấn bằng correlation/reference ID và chạy reconciliation trước khi quyết định gửi lệnh khác.
5. Định nghĩa retention cho idempotency record đủ dài theo vòng đời retry và giao dịch; không xóa quá sớm.

**Unique constraint ở DB của mình không tự bảo đảm chính xác một lần thu tiền ở provider.** Nếu provider hỗ trợ idempotency key, phải dùng đúng hợp đồng của họ; nếu không, thiết kế bước đối soát và quy trình xử lý thủ công khi không thể kết luận. Tính chất “exactly once” xuyên qua nhiều hệ thống không xuất hiện tự động từ retry, timeout hay transaction cục bộ.

## 13. Phân tích một sự cố giả định theo thời gian

Đây là ví dụ mô phỏng nhằm luyện cách chẩn đoán, không phải nhật ký từ hệ thống thật.

| Mốc | Sự kiện | Tác động |
|---|---|---|
| 10:00 | Payment Provider tăng latency p95 từ 200 ms lên 2.500 ms | Một số lời gọi Payment timeout |
| 10:01 | SDK Payment retry 3 lần; Order API cũng retry 3 lần | Số attempt phía Payment tăng; request giữ connection lâu |
| 10:02 | Pool Payment đầy, hàng chờ Order API dài | p99 Order API vượt SLO |
| 10:03 | Gateway retry thêm; người dùng bấm “Thanh toán” lần nữa | Tải lặp mạnh, nguy cơ double charge nếu thiếu idempotency |
| 10:04 | Order API dùng chung thread pool cho Cart API | Cart API bắt đầu 5xx dù database giỏ hàng vẫn khỏe |
| 10:05 | Autoscaling tăng Order API nhưng Provider chưa phục hồi | Lưu lượng bị đẩy thêm vào nút nghẽn |
| 10:07 | Tắt retry tầng Gateway, giới hạn concurrency Payment, mở circuit breaker | Tải tới Provider giảm; Cart API bắt đầu hồi phục |
| 10:12 | Provider phục hồi, circuit breaker thăm dò theo ngưỡng | Cho traffic tăng có kiểm soát, theo dõi lỗi và latency |

### Tìm nguyên nhân gốc

Không chỉ dừng ở kết luận “Provider bị chậm”. Provider chậm là **tác nhân kích hoạt**; nguyên nhân kiến trúc khiến thành sự cố rộng hơn là **retry chồng tầng**, **timeout vượt deadline**, **không cô lập pool** và **không giới hạn tải**. Việc xử lý sau sự cố nên sửa các điều kiện khuếch đại đó.

Một báo cáo postmortem hữu ích cần phân biệt:

- **Trigger:** dependency nào chậm/lỗi trước, bắt đầu lúc nào?
- **Amplifier:** SDK, proxy và service nào retry, mỗi tầng tối đa bao nhiêu attempt?
- **Propagation:** tài nguyên chung nào khiến chức năng khác bị kéo theo?
- **Detection:** chỉ số/alert nào báo sớm nhất, chỉ số nào phát hiện quá muộn?
- **Containment:** thay đổi giới hạn tải, timeout, circuit breaker hoặc failover nào làm sự cố giảm?
- **Prevention:** kiểm thử, mặc định cấu hình, kiểm tra deploy và runbook nào giúp tránh lặp?

## 14. Quan sát và thử nghiệm khả năng chịu lỗi

### Chỉ số và trace cần có

| Tín hiệu | Cần đo | Gợi ý diễn giải |
|---|---|---|
| **End-to-end latency p50/p95/p99** | Từ biên người dùng đến response/trạng thái cuối | SLO có bị vi phạm không? |
| **Downstream latency theo dependency** | DNS/connect/TLS, xếp hàng, request/response nếu đo được | Điểm nghẽn nằm ở đâu? |
| **Retry attempt rate** | Retry attempt / request gốc, phân theo lý do | Retry có đang khuếch đại tải không? |
| **Timeout và cancellation count** | Theo tầng, request, dependency | Deadline có được truyền và thực thi không? |
| **In-flight requests, pool utilization** | Thread/connection/semaphore đang dùng | Có gần chạm giới hạn đồng thời không? |
| **Queue depth/oldest item age** | Ở request queue hoặc async job | Tắc nghẽn kéo dài hay chỉ spike ngắn? |
| **Circuit breaker state, rejected probes** | Open/half-open, số request bị chặn | Có cô lập đúng dependency không? |
| **429/503/load shedding rate** | Theo upstream và tenant nếu phù hợp | Chính sách bảo vệ có đang tác động người dùng? |
| **Idempotency hit/conflict** | Số lần lặp key, payload mismatch | Có retry duplicate hoặc người dùng bấm nhiều lần không? |
| **Chi phí request/compute/egress** | Theo dependency và dạng lỗi | Retry có làm tăng chi phí bất thường không? |

Một trace của request nên thể hiện **deadline, từng attempt, thời gian backoff, dependency, status và idempotency/correlation ID** ở mức có thể quan sát. Tránh log token, dữ liệu thanh toán và payload nhạy cảm; hạn chế cardinality cao của metric theo request ID.

### Thử nghiệm có kiểm soát

Thực hành *fault injection* ở môi trường kiểm thử hoặc một nhóm traffic được phép:

1. **Inject 2 giây latency** vào Payment Provider mock, giữ tải gốc ổn định.
2. **So sánh** cấu hình retry chồng tầng với retry giới hạn một tầng, có jitter và retry budget.
3. **Quan sát** số attempt/request, pool sử dụng, latency p95/p99, hàng chờ và tỷ lệ lỗi của Cart API.
4. **Cắt kết nối sau khi provider đã ghi giao dịch** để xem cơ chế idempotency và xử lý trạng thái UNKNOWN.
5. **Phục hồi dependency** và kiểm tra circuit breaker half-open, tốc độ tăng traffic trở lại và khả năng phục hồi SLO.

**Tiêu chí đạt:** một dependency chậm không khiến chức năng không liên quan cùng ngừng phục vụ; số attempt bị giới hạn; request hết deadline không tiếp tục tạo công việc vô nghĩa; giao dịch không bị nhân đôi; hệ thống có tín hiệu rõ để vận hành can thiệp.

Không chạy fault injection trên giao dịch thanh toán thật nếu chưa có phân vùng thử nghiệm, dữ liệu giả và biện pháp bảo vệ phù hợp.

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cần trả lời | Lựa chọn giúp cải thiện |
|---|---|---|
| **Operational Excellence** | Ai sở hữu retry policy? Khi circuit breaker mở, người trực vận hành biết làm gì? | Cấu hình chuẩn, tracing, dashboard, alert và runbook |
| **Security** | Retry có tái gửi token/payload nhạy cảm hoặc vượt quota truy cập không? | Token scope phù hợp, log được lọc, rate limit và kiểm tra quyền mỗi request |
| **Reliability** | Dependency lỗi có kéo sập chức năng khác không? Timeout có khiến side effect trùng? | Deadline, idempotency, bulkhead, circuit breaker, queue bền vững khi cần |
| **Performance Efficiency** | Worker/connection pool có bị giữ bởi những request không còn ích lợi? | Cancellation, giới hạn đồng thời, phân bổ timeout bằng latency thực |
| **Cost Optimization** | Retry có làm nhân chi phí API, DB, egress và log? | Retry budget, phân loại lỗi, backoff+jitter, cân đối autoscaling |
| **Sustainability** | Bao nhiêu compute bị tiêu tốn cho thao tác retry chắc chắn không thành công? | Dừng khi hết deadline, giảm xử lý thừa, right-size năng lực |

**Các đánh đổi cần ghi trong quyết định kiến trúc:** timeout ngắn giúp giải phóng tài nguyên sớm nhưng có thể tăng lỗi giả khi dependency biến động; retry tăng xác suất thành công của lỗi tạm thời nhưng tiêu thời gian và tải; circuit breaker giúp cô lập nhưng có thể từ chối request ngay cả khi dịch vụ vừa phục hồi; bulkhead giữ năng lực cho tuyến quan trọng nhưng thêm giới hạn và chi phí quản lý.

Một **Architecture Decision Record (ADR)** cho chính sách retry có thể ghi: SLO và loại thao tác; chủ sở hữu retry; tổng attempt; deadline; loại lỗi retry được; backoff+jitter; retry budget; idempotency; limit concurrency; cách kiểm thử và metric đánh giá. Không chọn số bằng thói quen mà thiếu bằng chứng.

## 16. Bài tập thực hành và phương án tham khảo

### Bài tập A — Tìm lỗi cấu hình

Hệ thống có:

~~~text
Client deadline                  = 1.500 ms
Gateway retry                   = 2 attempt
Order API retry tới Inventory   = 3 attempt
Inventory SDK retry tới DB      = 3 attempt
Timeout mỗi lần Inventory call = 1.200 ms
Timeout mỗi DB query            = 800 ms
Không có cancellation, jitter hay concurrency limit
~~~

Trả lời:

1. Trong trường hợp tất cả nhánh đều thất bại và retry, số **DB attempt tối đa theo mô hình nhân tầng** là bao nhiêu?
2. Vì sao timeout 800 ms cho query DB không đảm bảo request kết thúc trong 1.500 ms?
3. Đề xuất chính sách giới hạn attempt, deadline và bảo vệ tài nguyên.

**Phương án tham khảo:** số DB attempt tối đa lý thuyết là \(2 \times 3 \times 3 = 18\) cho mỗi yêu cầu biên, giả sử mọi attempt đều dẫn đến các lần gọi bên dưới. Con số thực tế tùy điểm thất bại, khả năng cancellation và trạng thái dependency. Timeout DB chỉ giới hạn **mỗi query**; chưa tính retry, queue, network, backoff và tổng thời gian các tầng. Giải pháp gồm một deadline được truyền dọc; chỉ định tầng retry phù hợp thay vì nhân tầng; giới hạn tổng attempt theo latency budget; backoff+jitter; retry budget; cap concurrency và alert theo request age.

### Bài tập B — Thiết kế khi Payment Provider không ổn định

Một cổng bán hàng xử lý **300 yêu cầu thanh toán/giây** ở giờ cao điểm. Provider tăng latency p99 lên 4 giây, còn ngân sách chờ đồng bộ của người dùng là 2 giây. Người dùng có thể bấm thanh toán lại nếu giao diện báo timeout.

Hãy đề xuất hợp đồng API, idempotency key, xử lý kết quả không rõ, hạn mức retry và fallback cho các chức năng không phụ thuộc Payment.

**Phương án tham khảo:**

- Đường thanh toán dùng **paymentIntentId/idempotency key** có phạm vi nghiệp vụ và ghi bền vững trước khi gửi lệnh. Với timeout sau khi gửi, trả trạng thái **PENDING/UNKNOWN** và cho phép kiểm tra tình trạng, đối soát với provider; tránh tuyên bố thất bại cuối cùng khi chưa xác minh.
- Đặt **deadline tổng 2 giây** cho đường gọi đồng bộ. Nếu kết quả khó có trong hạn này, cung cấp API tạo ý định thanh toán và luồng **bất đồng bộ** để khách hàng xem trạng thái. Chỉ retry khi provider hỗ trợ lặp an toàn và còn đủ budget; có concurrency cap, backoff+jitter và circuit breaker.
- Tách pool/giới hạn tài nguyên của Payment khỏi danh mục, giỏ hàng và lịch sử. Các chức năng này phục vụ bình thường hoặc suy giảm theo chính sách riêng; không lấy trạng thái thanh toán từ cache cũ để báo thành công.
- Theo dõi **attempt rate, p95/p99 latency, UNKNOWN count, duplicate key count, in-flight Payment, circuit breaker state và tỷ lệ vi phạm SLO**. Kiểm thử tình huống response mất sau khi provider đã hoàn tất, bảo đảm không thu tiền lần hai.

## 17. Checklist rà soát trước khi triển khai

- [ ] Định nghĩa **SLO và deadline đầu-cuối** cho từng loại yêu cầu.
- [ ] Biết chính xác retry được bật ở **SDK, service, proxy, gateway và mesh** nào; tổng attempt được khống chế.
- [ ] Phân loại lỗi retry được, không retry được và **kết quả chưa rõ** theo nghiệp vụ.
- [ ] Mọi retry có **giới hạn số lần, tổng thời gian, backoff, jitter và retry budget**.
- [ ] Timeout kết nối, per-attempt và overall phù hợp; deadline và cancellation được truyền xuống.
- [ ] Side effect có **idempotency** và quy trình tra cứu/đối soát sau timeout.
- [ ] Có **concurrency limit, bulkhead, rate limiting/load shedding** để cô lập dependency.
- [ ] Circuit breaker có ngưỡng, probe, metric và runbook rõ ràng.
- [ ] Queue, nếu dùng, có giới hạn retry, độ tuổi công việc, DLQ và khôi phục.
- [ ] Đo **attempt/request, timeout, p95/p99, in-flight, queue age, fallback và chi phí**.
- [ ] Kiểm thử dependency chậm, lỗi thoáng qua, lỗi kéo dài, mất kết nối sau side effect và hồi phục sau sự cố.
- [ ] Ghi lại các đánh đổi về tin cậy, bảo mật, hiệu năng, chi phí, vận hành và bền vững theo Well-Architected.

**Kết luận:** Retry không giới hạn và timeout thiếu nhất quán là **phản mẫu** vì làm mất kiểm soát số công việc được tạo và thời gian chúng chiếm tài nguyên. Kiến trúc chịu lỗi tốt giới hạn tổng công việc theo deadline, ưu tiên tính đúng của nghiệp vụ, cô lập dependency không khỏe và cho hệ thống khả năng **từ chối hoặc suy giảm có kiểm soát** khi quá tải. Mục tiêu là giữ hệ thống còn phục vụ được phần quan trọng trong lúc chờ thành phần lỗi phục hồi.
