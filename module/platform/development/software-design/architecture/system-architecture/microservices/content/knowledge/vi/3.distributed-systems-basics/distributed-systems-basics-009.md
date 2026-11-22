# Ngân sách độ trễ và độ sẵn sàng của chuỗi phụ thuộc trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Nền tảng phân tán.  
> **Mục tiêu:** Biết xác định ngân sách thời gian và mức độ tin cậy của một hành trình có nhiều dịch vụ, phân bổ cho các thành phần, tránh lỗi lan truyền và kiểm chứng bằng số liệu đo thực tế.

## 1. Vì sao phải thiết kế ngân sách toàn tuyến?

Microservices cho phép chia chức năng theo ranh giới nghiệp vụ, nhưng đưa thêm network hop, RPC, message broker, cache, database, reverse proxy và điểm lỗi vào một hành trình. Một request nhanh ở từng service chưa chắc nhanh khi đi qua nhiều service; mỗi service có SLO tốt cũng chưa chắc giúp hành trình người dùng đạt SLO.

Ví dụ người dùng xác nhận đơn hàng:

~~~text
Browser
  |
API Gateway
  |
Order Service
  |---------------------|
  |                     |
Pricing Service    Inventory Service
  |                     |
Pricing DB          Inventory DB
  |---------------------|
            |
      Payment Service
            |
     Payment Provider
            |
         Order DB
~~~

Nếu Order phải chờ cả Pricing, Inventory và Payment mới có thể trả kết quả đúng, các thành phần đó cùng tạo nên **critical path**. Khi một trong số chúng chậm hoặc hỏng, user có thể chờ lâu, nhận lỗi, hoặc gặp trạng thái chưa rõ.

Có hai ngân sách:

1. **Latency budget:** tổng thời gian một hành trình được phép tiêu thụ, phân bổ cho các bước bắt buộc, network và phần dự phòng.
2. **Availability budget:** tỷ lệ lỗi cho phép trong một kỳ đo lường và mức rủi ro mà từng dependency đem vào kết quả toàn tuyến.

Ngân sách hữu ích khi dẫn tới quyết định thực thi: timeout, deadline, retry, fallback, bulkhead, lựa chọn đồng bộ hay bất đồng bộ, SLI/SLO, alert và quy trình khôi phục.

## 2. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Latency** | Thời gian từ mốc bắt đầu đến mốc kết thúc đã định nghĩa | Gateway xử lý 430 ms |
| **End-to-end latency** | Thời gian thực tế qua toàn bộ hành trình đang đo | Browser gửi request đến khi có kết quả dùng được |
| **Latency SLI** | Chỉ số đo phân phối độ trễ | Tỷ lệ request dưới 500 ms |
| **Latency SLO** | Mục tiêu theo latency SLI và kỳ đánh giá | 99% request hợp lệ dưới 500 ms/30 ngày |
| **Timeout** | Khoảng chờ trước khi caller từ bỏ một thao tác | Pricing call timeout 120 ms |
| **Deadline** | Thời hạn cuối cùng của toàn tác vụ | Request còn 210 ms trước khi hết hạn |
| **Availability SLI** | Tỷ lệ request thành công theo hợp đồng nghiệp vụ | Request trả đúng trạng thái và đúng thời hạn |
| **Availability SLO** | Mục tiêu nội bộ của availability SLI | 99,9% request checkout hợp lệ thành công |
| **Error budget** | Phần không đạt SLO được phép trong kỳ | 0,1% request nếu SLO là 99,9% |
| **Critical path** | Đường quyết định tổng thời gian hoàn tất | Nhánh chậm nhất trong fork/join rồi tới Payment |
| **Dependency bắt buộc** | Thiếu nó thì không thể hoàn tất hành trình đúng hợp đồng | Authorize payment cho lệnh xác nhận đã thanh toán |
| **Dependency tùy chọn** | Thiếu nó vẫn có thể trả kết quả hợp lệ | Recommendation trên trang chi tiết sản phẩm |

**Timeout không phải latency SLO.** SLO p99 dưới 500 ms không có nghĩa mỗi lời gọi con được chờ 500 ms. Nếu ba lời gọi nối tiếp cùng có timeout 500 ms, tổng thời gian chờ có thể vượt 1,5 giây.

**HTTP thành công không đồng nghĩa nghiệp vụ thành công.** Một response 200 quá hạn, dữ liệu sai, ghi thanh toán trùng, hoặc trả trạng thái SUCCESS khi chưa biết kết quả provider có thể không đáp ứng SLI nghiệp vụ. Hãy định nghĩa tính đúng đắn, thời hạn và những trạng thái chấp nhận được.

## 3. Bắt đầu từ hành trình người dùng và định nghĩa SLI

Đừng đặt SLO chung cho toàn bộ dịch vụ trước khi biết request nào quan trọng. Đối với mỗi hành trình, ghi:

- **Đối tượng:** ví dụ checkout.confirm, search.products hoặc account.profile.
- **Tập request:** hợp lệ/không hợp lệ, vùng địa lý, khách hàng, phiên bản, loại thiết bị, traffic nội bộ hay bên ngoài.
- **Mốc thời gian:** gateway nhận request đến khi hoàn thành response; nếu mục tiêu là trải nghiệm browser, cần telemetry từ browser.
- **Thành công:** kết quả nào đáp ứng hợp đồng? Kết quả giảm cấp có chấp nhận không?
- **SLO:** tỉ lệ, độ trễ, cửa sổ quan sát, tần suất xem xét và owner.
- **Đường đi:** cache hit/miss, user mới/cũ, dependency đồng bộ/bất đồng bộ.
- **Giới hạn:** ngân sách kinh doanh, mức rủi ro dữ liệu và chi phí vận hành.

Ví dụ một API xem giỏ hàng có thể có:

~~~text
Latency SLO:
  99% request hợp lệ hoàn tất <= 400 ms trong 30 ngày.

Availability SLO:
  99.9% request hợp lệ trả nội dung giỏ hàng đúng hợp đồng.

Correctness requirement:
  Không nhầm giỏ hàng người khác, không hiển thị giá thanh toán sai.
~~~

Các con số này là minh họa. Hệ thống thực tế chọn ngưỡng từ trải nghiệm cần bảo vệ, baseline, rủi ro và năng lực triển khai. Bản đồ SLO của mỗi hành trình có thể khác nhau: trang gợi ý sản phẩm, đọc thông tin và xác nhận thanh toán không nên mặc nhiên dùng cùng ngưỡng.

### Percentile và phân phối

Trung bình không thể hiện đủ tail latency. Nếu 99 request xử lý trong 100 ms và một request mất 4 giây, thời gian trung bình gần 139 ms nhưng một nhóm người dùng vẫn gặp trải nghiệm rất chậm. Theo dõi p50/p95/p99, tỷ lệ vượt ngưỡng, histogram và kích thước mẫu.

Cần ghi nhớ: **p99 của tổng thời gian không bằng tổng p99 của từng service**. Các hạng mục có tương quan, phân phối khác nhau và thường được đo trên tập request khác nhau. Dùng trace và histogram end-to-end làm bằng chứng chính; ngân sách thành phần là công cụ lập kế hoạch và điều tra.

## 4. Lập đồ thị phụ thuộc cho đúng một hành trình

Không lấy tất cả service trong kiến trúc rồi cộng latency hoặc nhân availability. Một request chỉ đi qua những thành phần trong đường thực thi của nó.

Sơ đồ nên ghi:

- Nút: gateway, service, DB, cache, broker, provider và công việc nội bộ.
- Cạnh: lời gọi synchronous, kết quả từ queue, chia sẻ dữ liệu, phụ thuộc khi triển khai.
- Thứ tự: tuần tự, song song, có điều kiện, async.
- Tính bắt buộc: toàn bộ kết quả phải có hay có thể trả partial result?
- Điều kiện: cache miss, loại thanh toán, user mới, gọi vùng xa.
- Owner/failure domain: nhóm chịu trách nhiệm, database, cluster, zone, region, IAM hoặc upstream chung.

Ví dụ:

~~~text
Gateway [25 ms]
     |
Order [40 ms]
     |
     |--------------------------|
     v                          v
Pricing [90 ms]            Inventory [110 ms]
     |--------------------------|
              JOIN
               |
         Payment [170 ms]
               |
            Response
~~~

Nếu Pricing và Inventory độc lập về dữ liệu/logic, chúng có thể chạy song song. Nếu Inventory cần kết quả Pricing để thực hiện nghiệp vụ, phải nối tiếp. Không thay đổi thứ tự xử lý nếu làm hỏng tính đúng đắn chỉ để giảm số trên sơ đồ.

Một request có thể có nhiều đường: happy path, provider timeout, cache miss, throttled path hoặc failover. Hãy xác định đường nóng và các đường có khả năng tạo tail latency.

## 5. Mô hình ngân sách độ trễ

### 5.1. Chuỗi tuần tự

Với các bước nối tiếp trên một lần thực thi:

\[
T_{\mathrm{total}} =
T_{\mathrm{ingress}} + \sum_i T_i + T_{\mathrm{network}} +
T_{\mathrm{response}}.
\]

Đây là phép cộng thời gian quan sát hoặc dự toán của **một lần thực thi**, không phải quy tắc cộng p99.

Giả sử mục tiêu end-to-end là **500 ms**:

| Hạng mục | Ngân sách minh họa |
|---|---:|
| Gateway và ingress | 25 ms |
| Xử lý Order nội bộ | 40 ms |
| Pricing | 90 ms |
| Inventory | 110 ms |
| Payment | 170 ms |
| Network, proxy, serialization | 35 ms |
| Reserve cho biến động | 30 ms |
| **Tổng tuần tự** | **500 ms** |

Bảng này là phương án phân bổ, không tự động chứng minh p99 đạt 500 ms. Một sự kiện GC, quá tải connection pool hoặc lỗi mạng có thể làm các hạng mục vượt ngân sách. Thời gian dự phòng không được dùng làm “đệm ảo” cho kết quả trung bình quá lạc quan.

### 5.2. Chuỗi có lời gọi song song

Khi Pricing và Inventory chạy song song và đều bắt buộc, thời gian đoạn fork/join gần với nhánh chậm hơn cộng chi phí điều phối:

\[
T_{\mathrm{path}} \approx
T_{\mathrm{gateway}} + T_{\mathrm{order}} +
\max(T_{\mathrm{pricing}}, T_{\mathrm{inventory}}) +
T_{\mathrm{payment}} + T_{\mathrm{overhead}} + T_{\mathrm{reserve}}.
\]

Trong bảng ví dụ:

\[
25 + 40 + \max(90,110) +170+35+30 = 410\text{ ms}.
\]

So với 500 ms tuần tự, mô hình có thêm khoảng **90 ms** dư địa. Nhưng chạy song song thường tăng concurrency, connection và contention. Dư địa chỉ được chấp nhận sau khi đo under load và kiểm tra hai nhánh có phụ thuộc hạ tầng chung hay không.

### 5.3. Thành phần bất đồng bộ

Nếu gửi email xác nhận không cần hoàn tất trước response, có thể xử lý qua queue. Khi đó latency của email không ở critical path của HTTP response, nhưng vẫn phải đo **business completion latency** và độ bền xử lý message. Không chuyển xác nhận payment sang async rồi gọi response “PENDING” là “đã thanh toán thành công” nếu hợp đồng ban đầu yêu cầu kết quả cuối cùng.

### 5.4. Cách chia ngân sách thực tế

1. Đo latency end-to-end theo từng journey/route và tải đại diện.
2. Thu trace cho đường chậm; phân biệt xử lý CPU, pool wait, queue, TLS, network, DB, upstream.
3. Tìm các thành phần trên critical path và phân phối thời gian của chúng.
4. Dành phần reserve có lý do; không phân hết toàn bộ target vào thời gian trung bình.
5. Định nghĩa deadline toàn tuyến và maximum timeout theo dependency.
6. Kiểm chứng dưới tải cao, lỗi từng phần và sự cố hạ tầng.
7. Đo lại sau thay đổi lớn về traffic, logic hoặc dependency.

### 5.5. Một ràng buộc xác suất bảo thủ

Đối với một path tuần tự có các hạng mục \(T_i\), nếu chọn ngưỡng \(b_i\) thỏa:

\[
P(T_i>b_i)\leq \epsilon_i
\quad\text{và}\quad
\sum_i\epsilon_i\leq\epsilon,
\]

thì theo bất đẳng thức hợp:

\[
P\left(\sum_i T_i>\sum_i b_i\right)
\leq \sum_i P(T_i>b_i)\leq\epsilon.
\]

Cách này **không cần giả định các thời gian độc lập**, nhưng có thể bảo thủ. Nó chỉ áp dụng đúng khi đã mô hình hóa các hạng mục cộng vào tổng trên path, bao gồm overhead. Với fork/join cần phân tích nhánh max. Trong mọi trường hợp, percentile end-to-end đo thực tế vẫn là nguồn xác nhận SLO.

## 6. Deadline toàn tuyến và timeout từng lời gọi

Deadline là **phần thời gian còn lại của tác vụ**, giảm dần qua các bước. Timeout từng call là một giới hạn nhỏ hơn deadline, phải tính đến công việc còn lại.

Ví dụ Order chỉ còn 180 ms trước deadline nhưng gọi Payment với timeout 500 ms. Client có thể đã bỏ cuộc khi Payment vẫn giữ connection/thread và tiếp tục tạo side effect. Khi nhiều request như vậy xảy ra, tài nguyên bị chiếm lâu, gây lỗi dây chuyền.

Một chính sách phân bổ:

~~~text
remaining = deadline - elapsed

available_for_call = remaining
                   - followup_required_time
                   - safety_margin

call_timeout = min(available_for_call, configured_dependency_cap)

if call_timeout <= 0:
    fail_fast_or_valid_fallback()
~~~

**Các lưu ý triển khai:**

- Connect timeout, read timeout, idle timeout và overall request deadline là những khái niệm khác nhau. Read timeout được reset khi đọc thêm dữ liệu có thể khiến tổng thời gian vượt dự kiến.
- Khi một call bị hủy, không được giả định downstream đã ngừng hoặc rollback side effect.
- Dùng đồng hồ monotonic để đo thời gian trong một tiến trình. Không gửi timestamp dựa trên System.nanoTime của máy A sang máy B để so sánh trực tiếp.
- Truyền **remaining budget** qua HTTP/RPC metadata nội bộ hoặc cơ chế deadline chuẩn của RPC; giới hạn theo maximum local policy.
- Đừng cho caller bên ngoài tự đặt thời hạn vô hạn bằng một header không được kiểm soát.
- Deadline phải bao gồm thời gian lấy connection, chờ pool, retry, backoff và serialization.

Ví dụ request ban đầu có deadline 500 ms. Khi đến Order, đã qua 70 ms nên còn 430 ms. Nếu còn cần 40 ms xử lý sau Payment và 30 ms reserve thì:

~~~text
remaining:           430 ms
future local work:    40 ms
safety reserve:       30 ms
available for call:  360 ms
Payment hard cap:    180 ms

actual call timeout: min(360, 180) = 180 ms
~~~

Không nên tự nâng hard cap từ 180 lên 360 chỉ vì còn thời gian; con số 180 có thể được chọn từ lịch sử latency hoặc chính sách bảo vệ provider.

## 7. Retry tiêu tốn cả thời gian và tài nguyên

Retry có thể giúp vượt qua lỗi thoáng qua. Nhưng nó tạo thêm request, backoff và độ trễ. Với n lần thử và các khoảng đợi:

\[
T_{\mathrm{retry\ sequence}} =
\sum_{i=1}^{n} T_{\mathrm{attempt},i} + \sum_j T_{\mathrm{backoff},j}.
\]

Phần này phải nằm **trong deadline toàn tác vụ**. Nếu còn 120 ms mà một lần thử thường mất 100 ms, thêm một retry 100 ms không thể đáp ứng deadline, còn tăng tải lúc upstream đã suy yếu.

### Khuếch đại retry nhiều tầng

Nếu Gateway, Service A và Service B đều thực hiện tối đa **3 attempts** cho một thao tác, trường hợp xấu có thể tạo **3 × 3 × 3 = 27** lần gọi đến dependency cuối. Đây là dạng retry amplification.

Các quy tắc cần thiết:

- Chỉ retry lỗi được hợp đồng xem là có thể phục hồi; không retry mọi 4xx, mọi timeout và mọi business error.
- Chọn một lớp sở hữu retry chính, giới hạn tổng attempts, đồng thời có retry budget hoặc rate limiter.
- Dùng exponential backoff có jitter; tránh request retry đồng loạt.
- Mỗi attempt phải tính **remaining deadline** và phần reserve, không tự mở một deadline mới.
- Với side effect, dùng idempotency key ổn định, deduplication hoặc phương thức tra cứu kết quả.
- Quan sát attempts, retry reason, backoff, outcome và lưu lượng dư do retry.

### Ví dụ budget retry

Dependency Inventory còn tổng ngân sách 170 ms, per-attempt cap 70 ms, backoff tối thiểu 20 ms, giữ 20 ms cho bước sau. Lần đầu timeout ở 70 ms → còn 100 ms; trừ backoff 20 ms và phần dự phòng 20 ms → lần hai tối đa 60 ms. Nếu 60 ms không đủ khả năng hoàn thành có ý nghĩa, bỏ retry để tránh vừa tăng tải vừa chắc chắn lỡ deadline.

**Timeout của một lệnh Payment không chứng minh thanh toán chưa xảy ra.** Provider có thể đã xử lý thành công nhưng response bị mất. Phải dùng idempotency, tra cứu trạng thái và reconciliation trước khi quyết định retry thao tác có tác dụng ghi.

## 8. Mô hình độ sẵn sàng của chuỗi

Với hành trình cần **tất cả** n thành phần và giả định chúng sẵn sàng **độc lập**, availability theo xác suất thành công:

\[
A_{\mathrm{chain}} = \prod_{i=1}^{n} A_i.
\]

Giả sử bốn dependency bắt buộc đều có availability 99,9% và độc lập:

\[
A_{\mathrm{chain}} = 0.999^4 \approx 0.996006 = 99.6006\%.
\]

Dù mỗi thành phần đều đạt 99,9%, toàn hành trình chỉ khoảng 99,60% theo mô hình đó. Nếu quy đổi tương đương theo thời gian 30 ngày, mức không sẵn sàng khoảng 0,3994% là **172,5 phút**. Đây là minh họa toán học, không phải dự báo downtime của hệ thống thực.

### Suy ngược yêu cầu cho từng dependency

Nếu n dependency độc lập, cùng availability \(a\), và mục tiêu toàn tuyến là \(A_{\mathrm{target}}\):

\[
a \geq A_{\mathrm{target}}^{1/n}.
\]

Với SLO end-to-end 99,9% và bốn dependency bắt buộc, mỗi thành phần cần khoảng **99,975%** trong mô hình lý tưởng. Khi vận hành thực còn phải tính gateway, network, failure domains, khác biệt phân phối tải và phương pháp đo SLI.

### Khi các dependency có tương quan

Trong Microservices, nhiều service cùng sử dụng database, DNS, cloud region, IAM, load balancer, service mesh hoặc cấu hình deployment. Tương quan lỗi phá giả định độc lập.

Với hai thành phần:

\[
P(A\cap B) = P(A)\times P(B\mid A).
\]

Không biết xác suất có điều kiện thì không thể nhân SLA của các service một cách chắc chắn. Sự cố chung có thể làm các thành phần cùng sập và cùng phục hồi; xác suất end-to-end phải được **đo từ hành trình thực tế**, đồng thời kiểm kê các failure domain chung.

### Dependency dạng AND, OR và fallback

- **AND:** tất cả bắt buộc. Một phần hỏng khiến toàn hành trình thất bại; trong mô hình độc lập có thể dùng tích availability.
- **OR:** chỉ cần một đường độc lập phục vụ được đầy đủ. Với các đường thật sự độc lập, availability là \(1-\prod_i(1-A_i)\).
- **Optional dependency:** Recommendation hỏng nhưng trang vẫn hiển thị đúng thông tin bắt buộc; có thể coi request xem trang thành công, đồng thời đo riêng chất lượng gợi ý.
- **Fallback không hợp lệ:** dùng giá cache đã hết hạn để chốt thanh toán khi yêu cầu giá chính xác. Không tăng availability bằng kết quả sai.

SLA nhà cung cấp, SLO service và SLO hành trình có thể dùng mẫu số, kỳ đo hoặc điều kiện thành công khác nhau. Không cộng/nhân chúng mà bỏ qua định nghĩa.

## 9. Error budget và tốc độ đốt ngân sách

Với availability SLO 99,9% trong 30 ngày:

\[
\text{Allowed error fraction}=1-0.999=0.001=0.1\%.
\]

Nếu trong kỳ có 10 triệu request hợp lệ, budget là **10.000 request không đạt**. Nếu định nghĩa đo availability theo thời gian, 0,1% của 30 ngày tương đương **43,2 phút**. Không coi hai con số có thể chuyển đổi trực tiếp khi traffic theo giờ biến động mạnh.

**Burn rate** là tỷ lệ tiêu thụ so với mức lỗi được phép. Nếu SLO cho phép 0,1% lỗi, nhưng một cửa sổ có 0,5% lỗi, burn rate là **5×**. Cảnh báo nhiều cửa sổ giúp nhận biết sự cố đột ngột và suy giảm kéo dài. Error budget dùng để cân đối tốc độ phát triển và độ tin cậy: khi đốt quá nhanh, cần ưu tiên xử lý nguyên nhân, giảm rollout rủi ro cao hoặc tăng capacity phù hợp.

Không nên tối ưu để “dùng hết” error budget. Mục đích của budget là hỗ trợ ra quyết định có chứng cứ.

## 10. Fan-out và tail latency

Khi một request đồng thời gọi n shard và **cần đủ tất cả**, thời gian hoàn tất gần với shard chậm nhất. Xác suất “có ít nhất một shard chậm/hỏng” tăng theo số nhánh.

Nếu mỗi shard độc lập đạt đúng hạn với xác suất 99%, toàn bộ 20 shard cùng đúng hạn với xác suất:

\[
0.99^{20}\approx81.79\%.
\]

Nếu mỗi shard có availability 99,9% và cả 20 bắt buộc, tỷ lệ tất cả sẵn sàng theo mô hình độc lập là:

\[
0.999^{20}\approx98.02\%.
\]

Đây là mô hình minh họa, không thay thế measurement của fan-out thực tế. Các shard thường có chung broker, database, network và điều kiện tải.

Cách giảm rủi ro:

1. Batch hoặc gộp các thao tác để giảm số call trên hot path.
2. Dùng cache/read model nếu yêu cầu consistency cho phép.
3. Cho phép partial result với điều kiện nghiệp vụ và nhãn dữ liệu thiếu rõ ràng.
4. Giới hạn fan-out concurrency; không cho số request con tăng vô hạn.
5. Áp deadline cho cả fork/join và từng nhánh, bỏ kết quả không còn giá trị khi hết hạn.
6. Cân nhắc hedged reads có kiểm soát khi an toàn và có số liệu chứng minh giảm tail latency hơn chi phí tải bổ sung.
7. Theo dõi slowest branch, số nhánh lỗi, tỷ lệ kết quả thiếu và mức tải downstream.

Khi chỉ một nhánh lỗi, retry toàn bộ 20 nhánh có thể khuếch đại tải mạnh. Nên thiết kế retry theo điều kiện và scope cần thiết.

## 11. Các cơ chế chặn cascading failure

### Timeout

Timeout ngăn chờ vô hạn nhưng phải phù hợp phân phối latency, SLO và deadline. Timeout quá ngắn gây false timeout và retry storm; quá dài giữ thread/connection và làm lỡ deadline toàn tuyến.

### Circuit breaker

Khi dependency hỏng nhiều hoặc phản hồi quá chậm, breaker có thể tạm ngừng gửi call, fail fast hoặc kích hoạt fallback. Nó cần window, threshold, half-open và telemetry rõ. Với dependency bắt buộc, fail fast vẫn là thất bại nghiệp vụ; giá trị của breaker là bảo vệ tài nguyên và giảm tác động dây chuyền.

### Bulkhead

Tách hoặc giới hạn concurrency cho từng dependency, tránh một provider chậm làm cạn toàn bộ connection pool, thread hay queue. Một ứng dụng CPU thấp vẫn có thể không phục vụ được request nếu tất cả connection đều đang chờ một API bị treo.

### Backpressure và load shedding

Khi tốc độ đến vượt năng lực xử lý, nên giới hạn queue, truyền tín hiệu giảm tải hoặc từ chối có kiểm soát, thay vì nhận vô hạn rồi timeout mọi request. Những request đã hết deadline trong queue không nên tiếp tục tiêu tốn tài nguyên.

### Cache

Cache giảm latency và có thể giảm số dependency sync. Cần xác định TTL, invalidation, protection against stampede, mức chấp nhận stale data và quyền truy cập. Stale-while-revalidate phù hợp một số read path, nhưng không phải chính sách mặc định cho thanh toán và ghi số dư.

### Failover

Đường dự phòng chỉ có tác dụng khi đủ capacity, có dữ liệu phù hợp và thật sự khác failure domain. Hai replica cùng zone dùng chung DB không bảo đảm độc lập khi DB hoặc zone hỏng. Failover cũng tiêu thụ thời gian, cần có budget riêng trong deadline.

## 12. Queueing, pool wait và độ trễ dưới tải

Một service có xử lý thuần 20 ms nhưng phải chờ connection pool 300 ms sẽ có latency lớn hơn 300 ms. Khi tải tiến gần năng lực phục vụ, queue wait có thể tăng nhanh và p99 xấu đi dù code không thay đổi.

Trong trạng thái ổn định, định luật Little:

\[
L=\lambda W,
\]

với \(L\) là số công việc trung bình trong hệ thống, \(\lambda\) là throughput trung bình và \(W\) là thời gian trung bình trong hệ thống. Ví dụ 200 request/s với thời gian trung bình 0,25 s ứng với khoảng **50 request đồng thời** trung bình dưới các giả định phù hợp.

Định luật này không tự tính được p99 hoặc capacity cần thiết trước burst. Hãy đo:

- Queue wait và queue depth tại ingress, executor, broker.
- Thời gian lấy connection, connect, TLS, server processing, serialization và response transfer.
- In-flight request, số connection đang dùng/chờ, retry concurrency.
- CPU, memory, GC, lock contention và I/O saturation.
- Hit ratio của cache, giới hạn tài nguyên và autoscaling.
- Độ trễ cao nhất của fan-out trong lúc tải tăng.

Đừng chỉ tăng timeout để che một pool đang bão hòa. Nếu 250 ms bị tiêu ở pool wait và 30 ms ở database, tối ưu một câu SQL thêm 5 ms không xử lý nguyên nhân chính.

## 13. Đồng bộ, bất đồng bộ và ranh giới consistency

| Cách giao tiếp | Latency | Availability và trade-off |
|---|---|---|
| HTTP/gRPC đồng bộ | Caller chờ; nằm trên critical path | Dependency có thể là điều kiện bắt buộc của request |
| Queue/event lưu bền | API có thể trả ACCEPTED/PENDING sớm | Cần idempotency, lag SLO, retry, DLQ/reconciliation |
| Cache/read model | Giảm RPC đồng bộ lúc đọc | Dữ liệu có thể cũ, cần hợp đồng freshness |
| Materialized view | Đọc nhanh | Pipeline cập nhật có thể trễ hoặc lỗi |
| Failover replica | Thêm đường đáp ứng | Cần independent failure domain và kiểm soát consistency |
| Fire-and-forget không xác nhận | Response ngắn nhưng không chứng minh tác vụ đã nhận | Có nguy cơ mất công việc; không phù hợp side effect cần bảo đảm |

Phân biệt **request acceptance latency** và **business completion latency**. Ví dụ nhận đơn mất 120 ms rồi trả PENDING, nhưng hoàn tất thanh toán mất 3 giây. Không thể công bố “thanh toán hoàn tất trong 120 ms”. Cần SLO riêng cho thời gian nhận yêu cầu, thời gian hoàn tất, queue age, kết quả thất bại và đối soát.

Không chuyển một dependency bắt buộc thành optional chỉ bằng cách bỏ qua response nếu điều đó làm mất tính đúng đắn nghiệp vụ.

## 14. Trạng thái chưa xác định khi request timeout

Đối với thao tác có side effect, kết quả có thể là:

1. **CONFIRMED_SUCCESS:** chắc chắn giao dịch đã thành công.
2. **CONFIRMED_FAILURE:** chắc chắn giao dịch không thực hiện theo hợp đồng.
3. **UNKNOWN/PENDING:** mất response hoặc timeout nên chưa biết side effect đã xảy ra hay chưa.

Ví dụ:

~~~text
POST /payments
Idempotency-Key: order-48392-attempt-1

Request reaches provider, payment is captured.
Response is lost on the network.
Caller times out.
~~~

Caller không được tự hiểu timeout thành PAYMENT_FAILED và tạo một payment khác ngay. Hệ thống cần stable idempotency key, API tra cứu trạng thái, reconciliation, log theo business operation ID, retry có điều kiện và cơ chế cập nhật trạng thái cho người dùng.

**Độ sẵn sàng đo bằng phản hồi nhanh nhưng sai dữ liệu là độ sẵn sàng giả.** Không sử dụng fallback để che unknown result của tài chính, đặt chỗ, tồn kho hoặc side effect quan trọng nếu không có hợp đồng nghiệp vụ rõ ràng.

## 15. Ví dụ Java: tính remaining deadline trong tiến trình

Đoạn code dưới đây minh họa ngân sách thời gian trong **một tiến trình Java**, tách khỏi HTTP client và framework cụ thể.

~~~java
import java.time.Duration;

public final class RequestDeadline {
    private final long startedAtNanos;
    private final long totalBudgetNanos;

    public RequestDeadline(Duration totalBudget) {
        if (totalBudget.isZero() || totalBudget.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        this.startedAtNanos = System.nanoTime();
        this.totalBudgetNanos = totalBudget.toNanos();
    }

    public Duration remaining() {
        long elapsed = System.nanoTime() - startedAtNanos;
        long available = Math.max(0L, totalBudgetNanos - elapsed);
        return Duration.ofNanos(available);
    }

    public Duration budgetForCall(Duration configuredCap,
                                  Duration requiredAfterCall,
                                  Duration safety) {
        Duration available = remaining()
                .minus(requiredAfterCall)
                .minus(safety);
        if (available.isZero() || available.isNegative()) {
            throw new IllegalStateException("Deadline exhausted");
        }
        return available.compareTo(configuredCap) < 0
                ? available
                : configuredCap;
    }
}
~~~

Cách dùng:

~~~java
RequestDeadline deadline =
        new RequestDeadline(Duration.ofMillis(500));

Duration paymentCallBudget = deadline.budgetForCall(
        Duration.ofMillis(180), // Payment configured hard cap
        Duration.ofMillis(40),  // Required local work after call
        Duration.ofMillis(30)   // Safety reserve
);

PaymentResult result =
        paymentClient.authorize(command, paymentCallBudget);
~~~

**Giới hạn của ví dụ:**

- Tạo một Duration chưa đủ để áp timeout; HTTP/RPC client phải thực thi deadline đúng ở tầng kết nối, yêu cầu và hủy.
- System.nanoTime phù hợp đo elapsed time trong cùng tiến trình, không phải timestamp tuyệt đối truyền qua nhiều máy.
- Không tự động giải quyết cancellation, retry, queue wait, idempotency hoặc phân biệt unknown outcome.
- Một production abstraction cần gắn trace/correlation ID, error classification và giới hạn cấu hình theo endpoint.
- Server mới nhận request phải tính remaining budget hợp lý; không được tự cấp lại 500 ms từ đầu.

### Pseudocode retry theo remaining budget

~~~text
for attempt in 1..MAX_ATTEMPTS:
    remaining = deadline.remaining()
    allowed = min(perAttemptCap, remaining - followupReserve)

    if allowed <= 0:
        return DEADLINE_EXCEEDED

    result = dependency.call(timeout=allowed,
                             idempotencyKey=stableKey)

    if result.success:
        return result
    if not isRetryable(result):
        return result

    backoff = jitteredBackoff(attempt)
    if deadline.remaining() <= backoff + followupReserve:
        return RETRY_BUDGET_EXHAUSTED

    sleep(backoff)
~~~

Retry chỉ có ý nghĩa nếu thao tác được phép thử lại và attempt tiếp theo còn khả năng hoàn thành trước deadline. Với Payment timeout cần kiểm tra trạng thái giao dịch thay vì retry mù.

## 16. Quan sát ngân sách bằng metrics và tracing

Một dashboard CPU không cho biết ngân sách bị tiêu ở đâu. Cần kết nối luồng request với service, pool, database, broker, upstream.

| Metric hoặc tín hiệu | Ý nghĩa |
|---|---|
| End-to-end duration histogram | Đo latency SLI và p95/p99 |
| Request success/error fraction | Đo availability SLI theo hợp đồng |
| Downstream call duration | Tìm dependency tiêu tốn ngân sách |
| Timeout, cancellation, deadline exceeded | Phát hiện call vượt giới hạn |
| Retry attempts, backoff, result | Kiểm soát amplification |
| In-flight request, queue depth/wait | Phát hiện overload hoặc saturation |
| Connection pool wait | Phân biệt chờ resource với latency downstream |
| Circuit breaker open/half-open | Nhận diện fail fast và phục hồi |
| Cache hit/miss | Phân tích đường chạy khác nhau |
| Fan-out slowest branch | Tìm nhánh chi phối critical path |
| Partial/degraded response | Tách success đầy đủ và giảm cấp |
| Message queue lag, oldest age | Đo business completion latency |

Trace có span cho gateway, gọi service, chờ pool, DB, broker và upstream sẽ giúp tìm critical path. Ví dụ:

~~~text
checkout.request                  484 ms
  gateway.auth                     24 ms
  order.logic                      39 ms
  pricing.rpc                      72 ms  (parallel)
  inventory.rpc                   155 ms  (parallel, critical)
      pool.wait                    98 ms
      db.query                     30 ms
  payment.rpc                     181 ms
  response.write                   19 ms
~~~

Nếu Inventory mất 155 ms nhưng DB thực xử lý 30 ms và pool wait 98 ms, nguyên nhân chính có thể là contention hoặc pool saturation. Tăng timeout cho DB không giải quyết bottleneck.

Cần lấy mẫu trace phù hợp để kiểm soát chi phí và dữ liệu nhạy cảm. Đừng dùng tập trace được sample không đại diện để suy ra chính xác tỷ lệ lỗi hay p99; SLI cần nguồn metrics và mẫu số đáng tin cậy.

## 17. Kịch bản thiết kế end-to-end: checkout 500 ms

Giả sử hệ thống có mục tiêu request checkout **p99 không quá 500 ms** và availability SLO **99,9%**. Có hai phương án.

### Phương án A: tuần tự

~~~text
Gateway 25
Order 40
Pricing 90
Inventory 110
Payment 170
Network + serialization 35
Reserve 30
----------------------------
Total budget 500 ms
~~~

Phương án này dùng hết ngân sách dự toán ngoài reserve. Nếu một dependency phải retry hoặc pool wait cao, khả năng lỡ deadline tăng.

### Phương án B: Pricing và Inventory song song

~~~text
Gateway 25
Order 40
max(Pricing 90, Inventory 110) = 110
Payment 170
Network + serialization 35
Reserve 30
----------------------------
Critical path budget 410 ms
~~~

Theo dự toán có 90 ms dư địa so với 500 ms. Tuy nhiên số liệu của từng bước phải được đo ở cùng bối cảnh tải, và phải kiểm tra shared DB contention khi tăng concurrency.

### Phân tích availability

Nếu trên một đường bắt buộc có bốn thành phần với availability 99,9% và giả định độc lập, toàn đường chỉ khoảng 99,6006%. Do đó “tất cả service đều đạt 99,9%” không bảo đảm checkout đạt 99,9%.

Có thể cải thiện bằng cách: giảm dependency bắt buộc, tăng khả năng sẵn sàng của những thành phần trọng yếu, cache/fallback hợp lệ, failover thật sự độc lập hoặc xử lý bất đồng bộ theo hợp đồng mới. Mọi thay đổi đều cần đo end-to-end SLI.

### Quyết định khi Payment timeout

Nếu Payment nhận lệnh nhưng mất response, hệ thống trả kết quả theo hợp đồng PENDING/UNKNOWN, tạo hoặc sử dụng stable operation ID để tra cứu và đối soát. Không tự xác nhận FAILED nếu không chắc chắn, cũng không tính PENDING thành thanh toán thành công. Phân biệt kết quả trả về cho người dùng với trạng thái cuối của giao dịch.

## 18. Kiểm thử dưới tải và lỗi từng phần

**Baseline:** đo p50/p95/p99, throughput, error rate, queue, pool, retry, cache hit, resource usage trong tải đại diện. Ghi version, cấu hình, loại request và thời điểm để so sánh công bằng.

**Dependency chậm:** tăng latency có kiểm soát ở một dependency trong môi trường thử. Quan sát deadline propagation, số request còn chờ sau khi client bỏ cuộc, retry traffic, circuit breaker và tác động lên endpoint khác.

**Dependency mất hoàn toàn:** mô phỏng unavailable, kiểm tra mandatory/optional classification, fallback hợp lệ, thời gian fail fast, khả năng phục hồi và mức tiêu thụ error budget.

**Pool saturation:** tạo tải tăng dần để xem queue wait, max in-flight và quá tải có lan sang service khác không. Giới hạn concurrency và load shedding trước khi hàng đợi trở nên vô hạn.

**Fan-out:** tăng số branch/shard, đo slowest branch và tỷ lệ partial result; kiểm tra có lỡ SLO vì một nhánh chậm không.

**Timeout có side effect:** giả lập provider xử lý thanh toán thành công nhưng chặn response. Kiểm tra idempotency, trạng thái PENDING, tra cứu và reconciliation.

**Failover:** thử mất zone/replica trong môi trường an toàn, kiểm tra đường dự phòng có đủ capacity, chính sách dữ liệu và thời gian chuyển đổi nằm trong budget không.

Thí nghiệm cần giả thuyết, phạm vi kiểm soát, điều kiện dừng, telemetry và tiêu chí so với SLO. Không nhất thiết gây lỗi trong production để học những giới hạn của thiết kế.

## 19. Các lỗi thường gặp khi xây dựng ngân sách

1. **Cộng p99 từng bước để ra p99 toàn tuyến.** Percentile không cộng tuyến tính; đo toàn tuyến.
2. **Đặt mọi timeout bằng deadline ngoài cùng.** Chuỗi gọi có thể vượt mục tiêu nhiều lần.
3. **Cho mỗi layer retry riêng.** Một request sinh nhiều call cấp số nhân.
4. **Retry lệnh ghi sau timeout mà không có idempotency.** Có thể tạo giao dịch trùng.
5. **Nhân SLA của toàn bộ service trong hệ thống.** Chỉ dependency bắt buộc trên hành trình, với giả định xác suất phù hợp, mới tham gia mô hình.
6. **Tin replica luôn độc lập.** Shared region/DB/IAM vẫn có thể hỏng cùng nhau.
7. **Chỉ đếm HTTP 200.** Response quá hạn hoặc kết quả nghiệp vụ sai cũng có thể là lỗi.
8. **Đưa Payment sang queue rồi gọi ACCEPTED là thanh toán thành công.** Phải đo business completion riêng.
9. **Chỉ đo CPU mà bỏ qua pool wait.** Thời gian chờ tài nguyên thường chi phối tail latency.
10. **Không để reserve.** Một biến động nhỏ khiến request vượt SLO.
11. **Không phân biệt optional và mandatory.** Dịch vụ phụ có thể làm hỏng nghiệp vụ chính không cần thiết.
12. **Chỉ có SLO từng service.** Người dùng đánh giá hành trình, không đánh giá sơ đồ service.
13. **Không xét traffic theo vùng/giờ.** Một outage nhỏ lúc cao điểm có thể gây rất nhiều request lỗi.
14. **Không diễn tập recovery.** Failover và rollback chưa kiểm chứng chỉ là giả thuyết.

## 20. Mẫu tài liệu ngân sách có thể áp dụng

| Hạng mục | Cần điền |
|---|---|
| Journey/endpoint | checkout.confirm |
| Product owner / tech owner | Người quyết định nghiệp vụ và triển khai |
| Latency SLO | Tỷ lệ, ngưỡng, kỳ đo, phạm vi request |
| Availability SLO | Định nghĩa thành công và error budget |
| Critical path | Bản đồ dependency theo điều kiện |
| Các hạng mục thời gian | Ngân sách từng bước, overhead, reserve |
| Deadline/timeout | Propagation, per-call cap, cancellation |
| Retry | Layer chủ trì, attempts, backoff, idempotency |
| Mandatory dependency | Service nào phải có kết quả |
| Optional dependency | Fallback và degraded result được chấp thuận |
| Failure domain | Shared DB, region, provider, IAM |
| Baseline | Histogram SLI, trace, error, queue/pool wait |
| Rủi ro cần đóng | Nguyên nhân, owner, mốc hoàn tất |
| Ngày đánh giá lại | Sau pilot, sau thay đổi tải hoặc dependency |

Ví dụ ngắn:

~~~text
Journey: checkout.confirm
SLO latency: 99% <= 500 ms
SLO availability: 99.9% request hợp lệ thành công
Critical path:
  Gateway 25 ms
  Order 40 ms
  Parallel Pricing 90 ms / Inventory 110 ms -> max 110 ms
  Payment 170 ms
  Network overhead 35 ms
  Reserve 30 ms
Budgeted path: 410 ms

Verification:
  End-to-end histogram
  Downstream traces and retry rate
  Circuit state and pool wait
  Business correctness and Payment unknown-state rate
~~~

Dùng ADR hoặc tài liệu thiết kế có version, để thay đổi timeout và số lần retry không diễn ra ngẫu nhiên ở từng repository.

## 21. Bài tập tự kiểm tra

**Đề bài:** một API Aggregation có deadline 300 ms. Gateway mất 20 ms; logic đầu 30 ms; sau fork/join cần 25 ms; network overhead 15 ms; reserve 30 ms. API gọi song song A và B, cả hai bắt buộc. A dự kiến 80 ms; B dự kiến 120 ms. Availability A và B đều 99,95%, giả định độc lập; tạm bỏ qua lỗi của các thành phần khác.

**Câu 1: fan-out còn bao nhiêu thời gian?**

\[
300 - 20 - 30 - 25 - 15 - 30 = 180\text{ ms}.
\]

Hai nhánh chạy song song, thời gian dự toán là max(80,120)=120 ms nên còn 60 ms trong budget của đoạn fan-out. Nếu gọi tuần tự, tổng 200 ms và vượt 20 ms. Đây là dự toán, phải đo tại tải thực tế.

**Câu 2: availability của hành trình?**

\[
A = 0.9995^2 = 0.99900025 \approx 99.900025\%.
\]

Tuyến chỉ vừa sát 99,9% theo mô hình lý tưởng, chưa tính gateway, aggregation, network và lỗi chung. Cần đo actual end-to-end SLI trước khi kết luận đạt.

**Câu 3: B timeout ở 150 ms?**

Vì B bắt buộc, không được trả thành công đầy đủ khi thiếu B. Có thể fail fast và trả kết quả đúng hợp đồng; tránh tiếp tục chờ đến deadline 300 ms nếu biết chắc không còn khả năng thành công. Nếu B được Product chấp nhận là optional, có thể trả partial result nhưng phải nêu rõ độ thiếu hụt.

**Câu 4: A và B dùng chung database?**

Giả định availability độc lập không còn đủ tin cậy. Parallel calls có thể tăng pool wait và lock contention. Cần đo dưới tải, phân tích shared failure domain, và cân nhắc giảm dependency hoặc điều chỉnh concurrency.

**Câu 5: B có side effect và timeout sau khi xử lý?**

Dùng idempotency key và quy trình xác minh trạng thái, không tự retry lệnh ghi nếu chưa bảo đảm hành vi trùng lặp được kiểm soát.

## 22. Checklist trước khi đưa kiến trúc vào production

### Latency

- [ ] SLO latency xác định đúng request, mốc đo và kỳ.
- [ ] Có baseline end-to-end p50/p95/p99 và tỷ lệ vượt ngưỡng.
- [ ] Đã vẽ critical path, phân biệt tuần tự/song song/conditional/async.
- [ ] Budget bao gồm pool wait, network, serialization, overhead và reserve.
- [ ] Có deadline toàn tuyến; downstream không tự làm mới ngân sách.
- [ ] Timeout áp dụng đúng ở client; cancellation và lỗi hết hạn được xử lý.
- [ ] Retry có giới hạn, backoff/jitter và tuân thủ deadline.
- [ ] Đã kiểm thử cache miss, fan-out, tải cao và dependency chậm.

### Availability

- [ ] Success SLI phản ánh hợp đồng nghiệp vụ, không chỉ mã HTTP.
- [ ] Phân loại mandatory/optional dependency và fallback.
- [ ] Có bảng failure domain, nhận diện lỗi chung.
- [ ] Có error budget và cảnh báo burn rate.
- [ ] Side effect có idempotency/tra cứu/reconciliation khi timeout.
- [ ] Có bulkhead, circuit breaker và giới hạn tải nơi phù hợp.
- [ ] Failover được kiểm thử capacity, consistency và thời gian phục hồi.
- [ ] Mỗi dependency quan trọng có owner và runbook.

### Ra quyết định

- [ ] Có trace/metrics cho latency, timeout, retry và pool wait.
- [ ] Không suy percentile toàn tuyến bằng cộng p99 từng service.
- [ ] Không suy availability thực tế chỉ bằng nhân SLA nhà cung cấp.
- [ ] Đã kiểm tra correctness khi retry, timeout và partial failure.
- [ ] Product xác nhận các trạng thái giảm cấp được phép.
- [ ] Ngân sách được quản lý như một giả thuyết thiết kế và đo lại sau thay đổi.

## 23. Kết luận thực hành

Ngân sách độ trễ là giới hạn trên **critical path** và cần được thực thi bằng deadline, timeout, capacity, retry policy và observability. Ngân sách độ sẵn sàng là giới hạn lỗi của **hành trình người dùng**, bị ảnh hưởng bởi số dependency bắt buộc, fan-out, correlation và khả năng fallback đúng nghiệp vụ.

Thay vì tăng timeout hoặc thêm retry một cách đồng loạt, hãy giảm dependency sync khi có thể, phân loại đúng tác vụ bắt buộc, cấp budget theo dữ liệu đo, bảo vệ tài nguyên và xử lý chính xác trạng thái không xác định. Công thức giúp hiểu xu hướng; SLI end-to-end, trace, load test và fault injection có kiểm soát mới chứng minh thiết kế đạt mục tiêu.
