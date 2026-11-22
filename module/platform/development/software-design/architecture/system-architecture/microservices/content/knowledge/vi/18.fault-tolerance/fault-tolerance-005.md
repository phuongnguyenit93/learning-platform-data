# Circuit Breaker và điều kiện kiểm tra phục hồi trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Khả năng chịu lỗi.
>
> **Trọng tâm:** Khi một dịch vụ phụ thuộc chậm hoặc hỏng, Circuit Breaker quyết định lúc nào ngừng gọi, lúc nào thử lại một lượng nhỏ lưu lượng và cần bằng chứng gì trước khi cho lưu lượng hoạt động bình thường trở lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao sự cố ở một service có thể lan sang thread pool, connection pool và những service còn khỏe.
2. Mô tả chính xác ba trạng thái **CLOSED**, **OPEN**, **HALF_OPEN** và sự kiện chuyển trạng thái.
3. Phân biệt lỗi kỹ thuật cần tính vào Circuit Breaker với lỗi nghiệp vụ dự kiến; hiểu ảnh hưởng của timeout, retry và slow call.
4. Xác định tiêu chí **mở mạch** từ cửa sổ quan sát và tiêu chí **phục hồi** từ những lời gọi thử nghiệm có kiểm soát.
5. Thiết kế fallback, giám sát, kiểm thử và vận hành Circuit Breaker cho một dependency trong hệ thống microservices.

Bài viết tập trung vào hành vi của một Circuit Breaker tại phía **client gọi downstream service**. Một dependency khác có đặc tính tải, yêu cầu chính xác và mức độ quan trọng khác có thể cần cấu hình khác.

## 2. Vấn đề: một service hỏng có thể kéo sập các service khác

Giả sử **Order Service** đồng bộ gọi **Inventory Service** để kiểm tra tồn kho:

~~~text
Client → API Gateway → Order Service → Inventory Service → Inventory DB
                           │
                           └→ Payment Service
~~~

Bình thường, Inventory trả lời sau 40–80 ms. Khi Inventory DB nghẽn, mỗi lời gọi có thể treo đến hết timeout hai giây. Nếu Order nhận 200 request/giây, nhiều request giữ thread, connection và bộ nhớ cùng lúc. Hàng đợi dài hơn khiến chính Order chậm, dù mã xử lý nghiệp vụ Order không có lỗi.

Nếu Order tự động retry hai lần ngay lập tức, một request của người dùng có thể biến thành ba request đến Inventory. Khi upstream đã quá tải, retry đồng loạt làm áp lực tăng thêm. Đây là một dạng **cascading failure**: sự cố ban đầu lan qua những lời gọi đồng bộ và tài nguyên dùng chung.

**Circuit Breaker (CB)** là cơ chế ra quyết định theo tình trạng gần đây của dependency:

- Khi đường gọi còn khỏe, cho lời gọi đi qua và ghi nhận kết quả.
- Khi tỷ lệ lỗi hoặc tỷ lệ gọi quá chậm vượt ngưỡng, **mở mạch** và từ chối nhanh những lời gọi tiếp theo.
- Sau khoảng nghỉ, cho một lượng nhỏ lời gọi thử nghiệm đi qua.
- Chỉ trở về chế độ bình thường khi dữ liệu từ giai đoạn thử đáp ứng điều kiện phục hồi.

CB làm giảm khối lượng lời gọi vô ích và giúp upstream giữ tài nguyên phục vụ công việc khác. CB **không sửa được** dependency, không thay timeout, không tự bảo đảm hệ thống sẽ sẵn sàng khi mở lại, cũng không thay thế việc xử lý lỗi ở cấp nghiệp vụ.

## 3. Mô hình trạng thái và các chuyển tiếp

### 3.1. CLOSED — hoạt động bình thường

Trong **CLOSED**, lời gọi đến dependency được cho phép. CB thu thập thống kê từ những lời gọi thực sự đi qua: thành công, thất bại, thời gian thực hiện và số lần chậm.

Khi đã có đủ mẫu quan sát, CB đánh giá ngưỡng. Nếu tỷ lệ lỗi hoặc tỷ lệ slow call chạm ngưỡng cấu hình thì chuyển sang **OPEN**.

Tên CLOSED dễ gây nhầm: *mạch đóng* có nghĩa đường gọi vẫn thông, không phải đang khóa.

### 3.2. OPEN — từ chối nhanh

Trong **OPEN**, CB không thực hiện lời gọi downstream thông thường. Caller nhận tín hiệu bị từ chối như **CallNotPermittedException** (trong Resilience4j), sau đó tầng ứng dụng có thể chọn fallback an toàn hoặc trả lỗi rõ nghĩa cho client.

Việc từ chối thường rất nhanh nên giảm nguy cơ giữ thread và connection chờ dependency đang hỏng. Các lời gọi bị từ chối **không phải** là một lần gọi downstream thất bại mới; cần theo dõi chúng bằng metric riêng.

CB giữ OPEN ít nhất một khoảng thời gian cấu hình. Hết thời gian này chỉ có nghĩa **đủ điều kiện bắt đầu kiểm tra**, chưa chứng minh dependency đã khỏe.

### 3.3. HALF_OPEN — kiểm tra phục hồi có giới hạn

Trong **HALF_OPEN**, CB cho phép một số lời gọi thử (probe) và chặn phần lưu lượng vượt giới hạn. Các probe vẫn dùng timeout và phân loại lỗi như lời gọi thực tế; không miễn trừ lỗi chỉ vì đang kiểm tra.

Sau khi thu đủ kết quả cần thiết theo cơ chế thư viện:

- Nếu tỷ lệ lỗi hoặc tỷ lệ gọi chậm vẫn vượt ngưỡng, chuyển về **OPEN**.
- Nếu dữ liệu thử đáp ứng các ngưỡng, chuyển sang **CLOSED** và bắt đầu quan sát lưu lượng bình thường.

Một số thư viện có thể quyết định sớm theo kết quả đã có hoặc có giới hạn thời gian chờ các probe hoàn tất. Vì vậy cần hiểu chính xác phiên bản thư viện và cấu hình đang dùng khi thiết kế kiểm thử.

~~~text
                  lỗi / slow call vượt ngưỡng
       ┌──────────────────────────────────────┐
       │                                      ▼
    CLOSED                                  OPEN
    cho gọi                              từ chối nhanh
       ▲                                      │
       │                    hết thời gian nghỉ và có
       │                    điều kiện kích hoạt probe
       │                                      ▼
       │                                  HALF_OPEN
       │                              cho N lời gọi thử
       │                                      │
       └───────────── probe đạt ngưỡng ───────┤
                                              │
                        probe không đạt ──────┘ → OPEN
~~~

### 3.4. Trạng thái đặc biệt

Một số implementation, chẳng hạn Resilience4j, còn có chế độ **FORCED_OPEN**, **DISABLED**, **METRICS_ONLY**. Chúng phục vụ vận hành hoặc quan sát và có hành vi riêng đối với lời gọi/metrics. Không nên đồng nhất chúng với chu trình tự động CLOSED → OPEN → HALF_OPEN.

## 4. Circuit Breaker đo những gì?

Một CB không nên mở chỉ vì “có một request lỗi”. Nó cần **thước đo**, **cửa sổ quan sát** và **số lượng mẫu tối thiểu**.

| Tham số | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Sliding window | Phạm vi các lời gọi gần đây được dùng để tính thống kê | Quan sát 20 lời gọi hay 30 giây gần nhất? |
| Minimum number of calls | Số mẫu tối thiểu trước khi xét mở mạch ở CLOSED | Có đủ dữ liệu để tránh phản ứng từ một lỗi lẻ? |
| Failure rate | Số lời gọi được tính là thất bại / số lời gọi đã xét | Dependency đang lỗi với tỷ lệ bao nhiêu? |
| Slow-call rate | Số lời gọi lâu hơn ngưỡng chậm / số lời gọi đã xét | Dependency có đang suy giảm dù chưa timeout? |
| Slow-call duration threshold | Mốc thời gian để gọi là slow | 700 ms có đủ chậm so với ngân sách latency? |
| Wait duration in OPEN | Khoảng nghỉ trước cơ hội kiểm tra tiếp | Khi nào có thể cho probe? |
| Permitted calls in HALF_OPEN | Giới hạn số lời gọi thử | Cho bao nhiêu request để đánh giá phục hồi? |

**Cửa sổ theo số lượng (COUNT_BASED):** giữ kết quả N lời gọi đã ghi nhận gần nhất. Phù hợp khi muốn số mẫu cố định, nhưng 20 lời gọi có thể diễn ra trong vài mili giây ở giờ cao điểm hoặc vài phút khi lưu lượng thấp.

**Cửa sổ theo thời gian (TIME_BASED):** giữ kết quả trong khoảng thời gian gần đây. Phù hợp khi độ mới theo thời gian quan trọng, nhưng ở lưu lượng thấp vẫn cần số mẫu tối thiểu để tránh kết luận quá sớm.

Ví dụ cấu hình minh họa:

- Cửa sổ 20 lời gọi, tối thiểu 10 lời gọi.
- Failure-rate threshold 50%.
- Slow-call threshold 700 ms và slow-call-rate threshold 70%.

Nếu chỉ có 4 lời gọi, trong đó 3 lỗi, CB chưa nên kết luận từ cửa sổ CLOSED theo cấu hình tối thiểu 10 mẫu. Khi đã có 10 lời gọi và 5 lời gọi được phân loại là failure, tỷ lệ 50% đạt ngưỡng mở mạch. Nếu 10 lời gọi đều thành công nhưng 7 lời gọi mất hơn 700 ms, slow-call rate 70% cũng có thể làm mở mạch.

**Lưu ý:** Một lời gọi có thể vừa **slow** vừa **failed**. Đây là hai phân loại trên cùng mẫu, không phải hai lời gọi riêng. Số liệu không nên bị cộng đúp khi trình bày tổng request.

## 5. Định nghĩa chính xác “lỗi” trước khi bật CB

CB chỉ hữu ích khi thống kê phản ánh **sức khỏe dependency**. Không phải mọi exception đều chứng minh dependency hỏng.

| Tín hiệu | Có nên tính là lỗi CB? | Lý do |
| --- | --- | --- |
| Connection refused, lỗi DNS/transport, mất kết nối | Thường có | Không thiết lập được đường giao tiếp đến dependency |
| Timeout từ dependency | Thường có | Dependency không đáp ứng trong latency budget |
| HTTP 500, 502, 503, 504 | Thường có | Dịch vụ/chuỗi downstream gặp lỗi kỹ thuật |
| HTTP 429 | Tùy hợp đồng API | Có thể là bảo vệ quá tải, nhưng cũng có thể là quota dành riêng cho caller |
| HTTP 404 khi sản phẩm không tồn tại | Thường không | Đây có thể là kết quả nghiệp vụ hợp lệ |
| HTTP 400 do đầu vào sai, 401/403 do quyền truy cập | Thường không | Việc gửi request sai không cho thấy downstream tạm thời suy sụp |
| “Hết hàng”, “không đủ hạn mức” | Không, nếu là kết quả nghiệp vụ mong đợi | Không nên mở mạch khi dependency trả lời đúng |
| Dữ liệu trả về sai schema hoặc không giải mã được | Tùy bối cảnh | Có thể là lỗi tích hợp cần giám sát riêng; phân loại theo hợp đồng |

Quy tắc quan trọng: **phân biệt lỗi ở ranh giới tích hợp và lỗi trong nghiệp vụ của caller**. Ví dụ, Inventory trả về “SKU không tồn tại” là một phản hồi thành công về mặt vận hành, dù Order không thể tạo đơn hàng.

Với HTTP client, cần bảo đảm 5xx thực sự được ánh xạ thành exception hoặc kết quả mà CB ghi nhận là lỗi. Một client trả về đối tượng response bình thường cho mọi HTTP status có thể khiến CB đếm HTTP 503 là *success* nếu không có logic phân loại.

Có ba cách phân loại thường gặp:

1. Gắn **record exception** cho transport failure, timeout và lỗi server.
2. Gắn **ignore exception** cho lỗi nghiệp vụ đã dự kiến.
3. Với client trả đối tượng kết quả, dùng predicate đánh giá result hoặc chuyển các trạng thái lỗi kỹ thuật thành exception trước khi CB ghi nhận.

Không nên bỏ qua lỗi hàng loạt chỉ để làm tỷ lệ failure đẹp hơn. Ngược lại, đếm mọi 4xx sẽ mở mạch sai khi client liên tục gửi request không hợp lệ.

## 6. Timeout, Retry, Circuit Breaker và Bulkhead phối hợp thế nào?

Các cơ chế resilience giải quyết những câu hỏi khác nhau:

| Cơ chế | Vai trò | Không giải quyết được |
| --- | --- | --- |
| **Timeout** | Giới hạn thời gian chờ một lời gọi | Không tự ngăn các lời gọi mới liên tục vào dependency đang lỗi |
| **Retry** | Thử lại lỗi có khả năng thoáng qua | Có thể tạo retry storm khi dependency đang quá tải |
| **Circuit Breaker** | Quyết định có cho phép lời gọi downstream dựa trên số liệu gần đây | Không giới hạn trực tiếp số request đồng thời khi CLOSED |
| **Bulkhead** | Giới hạn tài nguyên/concurrency dành cho dependency | Không tự biết dependency đã hồi phục |
| **Rate limit** | Giới hạn tần suất request theo chính sách | Không suy ra được tình trạng thực của dependency |
| **Fallback** | Cung cấp hành vi thay thế sau lỗi/từ chối | Không thể biến dữ liệu cũ thành dữ liệu chính xác |

**Thứ tự bao bọc có ý nghĩa.** Ví dụ, retry đặt *bên trong* Circuit Breaker có thể khiến một request người dùng được CB nhìn là một lần gọi sau nhiều lần retry; retry đặt *bên ngoài* có thể khiến CB ghi nhận từng lần thử. Ngoài ra, retry các lỗi “circuit OPEN” là vô nghĩa và có thể làm tăng tải lên caller.

Một chính sách thực dụng cho đọc dữ liệu:

- Đặt connect timeout, response timeout theo latency budget.
- Chỉ retry lỗi thoáng qua khi request an toàn và còn thời gian trong budget; dùng exponential backoff có jitter, số lần nhỏ.
- Không retry khi CB từ chối vì OPEN.
- Dùng Bulkhead cho dependency có nguy cơ làm cạn thread/connection.
- Đặt fallback theo tính chất nghiệp vụ, không theo mong muốn “luôn trả 200”.

Đối với thao tác thanh toán hoặc tạo đơn, retry chỉ an toàn khi có **idempotency key** và hợp đồng xử lý trùng lặp. Một timeout không chứng minh yêu cầu ở phía downstream chưa được thực hiện.

## 7. Điều kiện mở mạch: chính sách nhận diện suy giảm

Hãy định nghĩa quyết định mở mạch bằng tiêu chí rõ ràng, có thể đo và có thể kiểm thử:

**Ví dụ đối với lời gọi đọc tồn kho**:

- Quan sát 20 lời gọi gần nhất.
- Chờ tối thiểu 10 lời gọi trước khi áp dụng thống kê ở CLOSED.
- Mở nếu failure rate đạt ít nhất 50%.
- Mở nếu slow-call rate đạt ít nhất 70%, trong đó “slow” nghĩa là lâu hơn 700 ms.
- Chỉ tính transport, timeout, server failure; bỏ qua lỗi SKU không tồn tại đã được xử lý theo hợp đồng.

Ví dụ chuỗi dữ liệu:

| Mốc quan sát | Số mẫu | Failure | Slow | Quyết định |
| --- | ---: | ---: | ---: | --- |
| A | 6 | 4 | 4 | Chưa đủ minimumNumberOfCalls |
| B | 10 | 3 (30%) | 4 (40%) | Tiếp tục CLOSED |
| C | 10 | 5 (50%) | 6 (60%) | Chuyển OPEN do failure rate |
| D | 10 | 1 (10%) | 7 (70%) | Chuyển OPEN do slow-call rate |

Các dòng là **kịch bản độc lập** nhằm minh họa cách quyết định; không phải chuỗi event thực tế trên cùng một cửa sổ trượt.

CB không là hệ thống phát hiện mọi outage. Một dependency ít lưu lượng có thể không đủ mẫu để mở mạch nhanh. Ngược lại, cửa sổ quá nhỏ và threshold quá nhạy dễ tạo **flapping**: mở/đóng liên tục vì vài request ngẫu nhiên.

## 8. Điều kiện kiểm tra phục hồi: OPEN không tự có nghĩa là khỏe

Đây là phần quan trọng nhất của thiết kế. Từ **OPEN** chuyển sang **HALF_OPEN** không có nghĩa đã phục hồi; chỉ có nghĩa đến lúc **kiểm tra giả thuyết dependency đã phục hồi**.

### 8.1. Điều kiện 1 — đã qua thời gian nghỉ

Thời gian OPEN giúp dependency giảm tải, restart, scale, hoặc khôi phục connection pool. Ví dụ đặt **waitDurationInOpenState = 20 giây**.

Sau 20 giây:

- Nếu chế độ chuyển tự động đang tắt, thông thường lời gọi đủ điều kiện kế tiếp có thể kích hoạt bước sang HALF_OPEN.
- Nếu thư viện hỗ trợ chuyển tự động và tính năng đó đang bật, trạng thái có thể chuyển theo lịch nội bộ, nhưng vẫn cần lời gọi thử để có bằng chứng phục hồi.
- Nếu không có traffic, đừng suy diễn rằng CB đã kiểm tra sức khỏe thành công.

Đây là **backoff giữa các lượt đánh giá** chứ không phải lời cam kết “sau 20 giây dependency phải hoạt động”.

### 8.2. Điều kiện 2 — giới hạn probe để không tái tạo sự cố

HALF_OPEN chỉ cho **N** lời gọi thử đồng thời hoặc trong một đợt theo cơ chế implementation. Với N = 4, những request được phép thử có thể dùng lưu lượng người dùng thật hoặc một cơ chế kiểm tra được thiết kế riêng. Request vượt số permit phải bị từ chối nhanh.

Probe tốt cần:

- Đi qua **đúng đường kết nối** đang được bảo vệ; một health endpoint “UP” không đủ chứng minh truy vấn nghiệp vụ thành công.
- Có timeout và tiêu chí thành công rõ.
- Đủ nhẹ, đại diện cho loại workload đã hỏng.
- An toàn nếu gọi lại; ưu tiên read-only hoặc thao tác có idempotency.
- Không tạo đột biến tải đúng lúc hệ thống đang hồi phục.

Đừng dùng một lệnh “tạo thanh toán thử” có side effect làm probe. Với Payment, nên dùng health/authorization check có hợp đồng riêng, hoặc quan sát một lượng nhỏ request thật được bảo vệ an toàn.

### 8.3. Điều kiện 3 — kết quả probe đáp ứng chính sách

Giả sử cấu hình:

- Permitted calls in HALF_OPEN: **4**.
- Failure-rate threshold: **50%**.
- Slow-call-rate threshold: **70%**.
- Slow-call duration threshold: **700 ms**.

Các kết quả minh họa:

| Kết quả 4 probe | Failure rate | Slow-call rate | Quyết định |
| --- | ---: | ---: | --- |
| 4 thành công, đều nhanh | 0% | 0% | Đủ điều kiện CLOSED |
| 3 thành công, 1 lỗi, đều nhanh | 25% | 0% | Có thể CLOSED theo threshold 50% |
| 2 thành công, 2 lỗi | 50% | Tùy latency | OPEN lại |
| 4 thành công, 3 lời gọi quá chậm | 0% | 75% | OPEN lại do latency |

Điểm dễ bỏ sót: **“CLOSED trở lại” không nhất thiết đồng nghĩa tất cả probe thành công.** Nếu chính sách là tỷ lệ lỗi nhỏ hơn 50%, 1/4 lỗi có thể vẫn được chấp nhận. Nếu nghiệp vụ yêu cầu *không có lỗi nào* ở giai đoạn thử, phải định nghĩa và cấu hình chính sách khác một cách tường minh; đừng mặc định thư viện bảo đảm 100% success.

Trong Resilience4j, số probe HALF_OPEN được cấu hình riêng với **minimumNumberOfCalls** dùng cho cửa sổ CLOSED; không dùng minimum của CLOSED để đoán rằng HALF_OPEN cần cùng số mẫu.

### 8.4. Điều kiện 4 — trả lưu lượng một cách có trách nhiệm

CLOSED nghĩa là CB lại cho phép gọi bình thường. Tuy nhiên việc phục hồi có thể còn mong manh nếu:

- Nhiều instance của Order cùng thoát OPEN gần như đồng thời.
- Inventory vừa restart và cache/connection pool chưa ấm.
- Backlog được xả dồn, gây spike.
- DB vừa phục hồi nhưng latency còn cao.

CB mặc định không phải hệ thống **traffic ramp-up**. Nếu dependency nhạy với tải, kết hợp thêm rate limit, concurrency limit, queue control, gradual rollout hoặc điều phối ở service mesh/gateway. Không tự xem một đợt probe thành công là bằng chứng dependency chịu được toàn bộ peak traffic.

### 8.5. Nếu probe thất bại thì sao?

Khi kiểm tra không đạt, CB trở lại OPEN. Có thể tiếp tục thời gian nghỉ cố định hoặc áp dụng chính sách tăng thời gian nghỉ cho các đợt thất bại liên tiếp, tùy thư viện/cách tổ chức. Backoff có giới hạn và jitter có thể giúp các instance không cùng thử lại vào đúng một thời điểm.

Tránh để OPEN vô thời hạn vì **không có probe** hoặc vì cấu hình vận hành bị ép FORCED_OPEN mà đội vận hành không nhận biết. Giám sát thời gian giữ trạng thái, lần chuyển gần nhất và số probe là cần thiết.

## 9. Ví dụ đầy đủ: Inventory phục hồi sau 503

Giả sử Order đang gọi Inventory 100 request/giây:

**Giai đoạn A — bình thường.** Circuit Breaker CLOSED; latency p95 110 ms; failure rate 0–1%.

**Giai đoạn B — suy giảm.** Inventory DB thiếu connection, HTTP 503 và timeout tăng; trong 10 mẫu đủ điều kiện có 6 thất bại, tỷ lệ 60%. CB chuyển OPEN.

**Giai đoạn C — bảo vệ.** Trong 20 giây tiếp theo, lời gọi đến Inventory bị từ chối nhanh. Order chọn hành vi nghiệp vụ phù hợp: hiển thị “chưa xác nhận tồn kho” khi đây là màn hình tham khảo, nhưng **không xác nhận đơn hàng** bằng dữ liệu tồn kho cũ nếu yêu cầu phải giữ hàng thật.

**Giai đoạn D — thử phục hồi.** Hết 20 giây, các lời gọi phù hợp đầu tiên kích hoạt HALF_OPEN. Bốn lời gọi được cho qua theo số permit, các lời gọi khác nhận fallback/temporary unavailable.

**Giai đoạn E — đánh giá.** Nếu cả bốn probe chạy nhanh và không lỗi, chuyển CLOSED. Nếu hai probe gặp 503, failure rate 50% khiến chuyển OPEN lại.

**Giai đoạn F — giám sát sau phục hồi.** Theo dõi tỷ lệ lỗi, p95/p99 latency, số request bị chặn và mức tải của Inventory. Nếu CLOSED rồi lại OPEN liên tục, đây có thể là dấu hiệu tải quay lại quá nhanh hoặc dependency chưa phục hồi bền vững.

Một timeline minh họa (thời gian và số liệu giả định, không phải mặc định của thư viện):

~~~text
t=00s    CLOSED    Inventory bắt đầu trả 503
t=03s    OPEN      tỷ lệ lỗi trong cửa sổ chạm ngưỡng
t=03–23s OPEN      downstream requests bị từ chối nhanh
t≈23s    HALF_OPEN lời gọi đủ điều kiện đầu tiên bắt đầu đợt probe
t≈24s    CLOSED    đủ probe hợp lệ, ngưỡng lỗi/chậm không bị vượt
t>24s    CLOSED    theo dõi vì tải thật đã quay lại
~~~

Nếu không có request ở t≈23s thì quá trình kiểm tra có thể bắt đầu muộn hơn. Không nên coi mốc thời gian trên là SLA chính xác.

## 10. Cấu hình minh họa với Spring Boot và Resilience4j

Một cách triển khai phổ biến là dùng Resilience4j trong service Java. Ví dụ này đặt các thông số có chủ đích để dễ diễn giải; giá trị thật phải được chọn theo SLO, lưu lượng và đặc tính dependency.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 700ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 4
        automaticTransitionFromOpenToHalfOpenEnabled: false
~~~

Ý nghĩa thực tế:

- **inventoryRead** là tên breaker cho một nhóm lời gọi có cùng hợp đồng resilience. Không gộp lẫn đọc tồn kho và thanh toán chỉ vì cả hai là HTTP.
- **slidingWindowType/Size** quy định mẫu để tính tỷ lệ ở CLOSED.
- **minimumNumberOfCalls** tránh mở quá sớm khi ít traffic.
- **failureRateThreshold** và **slowCallRateThreshold** là hai đường dẫn độc lập để mở mạch.
- **slowCallDurationThreshold** phải gắn với yêu cầu latency của lời gọi cụ thể.
- **waitDurationInOpenState** chỉ điều khiển lúc có thể bắt đầu thử lại.
- **permittedNumberOfCallsInHalfOpenState** giới hạn probe; kết quả probe quyết định trở về CLOSED hay OPEN.
- **automaticTransition... = false** nghĩa là không chủ động chuyển sang HALF_OPEN theo lịch khi không có lời gọi kích hoạt.

Đối với I/O đồng bộ, phải cấu hình **connect timeout và response/read timeout** tại HTTP client. Chỉ khai báo Circuit Breaker không bảo đảm request sẽ bị ngắt đúng hạn. Với tác vụ bất đồng bộ/Reactive, cần chọn TimeLimiter, timeout operator và cách hủy công việc phù hợp.

Phần dependency cụ thể (starter của Spring Boot, module core, AOP hoặc Reactor adapter) phụ thuộc stack và phiên bản dự án. Hãy kiểm tra tài liệu API của phiên bản đang dùng khi áp dụng YAML hoặc annotation; ví dụ ở đây tập trung vào contract của CB.

### 10.1. Mẫu Java đặt CB tại ranh giới gọi downstream

Giả sử có interface InventoryClient đã xử lý HTTP status và timeout, trả StockView cho kết quả hợp lệ, ném exception đối với lỗi tích hợp. Ví dụ Java dưới đây dùng API core dạng Supplier để minh họa phạm vi ghi nhận lời gọi:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import java.util.Optional;
import java.util.function.Supplier;

record StockView(String sku, Integer available, boolean estimated) {}

interface InventoryClient {
    StockView fetch(String sku); // timeout + ánh xạ HTTP 5xx phải nằm trong client
}

interface StockCache {
    Optional<StockView> findRecent(String sku);
}

public final class InventoryGateway {
    private final InventoryClient client;
    private final StockCache cache;
    private final CircuitBreaker breaker;

    public InventoryGateway(
            InventoryClient client,
            StockCache cache,
            CircuitBreaker breaker) {
        this.client = client;
        this.cache = cache;
        this.breaker = breaker;
    }

    public StockView lookup(String sku) {
        Supplier<StockView> protectedCall =
                CircuitBreaker.decorateSupplier(
                        breaker,
                        () -> client.fetch(sku));

        try {
            return protectedCall.get();
        } catch (CallNotPermittedException openCircuit) {
            // Chỉ dùng dữ liệu cache khi hợp đồng cho phép hiển thị ước lượng.
            return cache.findRecent(sku)
                    .map(x -> new StockView(x.sku(), x.available(), true))
                    .orElse(new StockView(sku, null, true));
        }
    }
}
~~~

Ở đây:

1. CB bao quanh **đúng lời gọi external**; mã bên ngoài không tự bị đếm như một failure downstream.
2. Khi CB OPEN hoặc HALF_OPEN đã hết permit, **CallNotPermittedException** được xử lý riêng.
3. Nếu client thật sự lỗi trong lời gọi được cho phép, lỗi tiếp tục truyền ra để tầng nghiệp vụ/HTTP mapper xử lý. CB vẫn ghi nhận kết quả theo chính sách phân loại.
4. Cache fallback trả **estimated=true** và có thể trả available=null để biểu đạt “không rõ”. Không được dùng dữ liệu này thay cho giao dịch giữ hàng có yêu cầu tính chính xác.
5. Instance **breaker** phải đến từ registry/config của ứng dụng theo tên đã định nghĩa, không tạo mới ở mỗi request. Một CB mới trên từng request sẽ mất toàn bộ lịch sử thống kê.

Code là minh họa cách phân chia trách nhiệm; InventoryClient, cache, ánh xạ lỗi và chiến lược response cần được hiện thực theo hệ thống thật. Nếu dùng annotation **@CircuitBreaker**, cần lưu ý Spring proxy/AOP: lời gọi nội bộ trong cùng object có thể không đi qua proxy, dẫn đến bảo vệ không hoạt động như dự kiến.

### 10.2. Phân loại lỗi ở tầng HTTP client

Hợp đồng nên viết rõ:

~~~text
HTTP 200 + stock hợp lệ  → StockView → CB ghi nhận success
HTTP 404 SKU không có    → Domain NotFound → CB ignore/không tính failure
HTTP 503/504             → UpstreamUnavailable → CB ghi nhận failure
Connect timeout          → Timeout/Transport exception → CB ghi nhận failure
CB OPEN                  → CallNotPermitted → không gọi HTTP client
~~~

Nếu thư viện HTTP tự động retry, cần biết retry đã diễn ra **trước hay bên trong** phạm vi CB, vì điều đó làm thay đổi thống kê và số request thực gửi đi.

## 11. Phục hồi ở mức hệ thống: một health check có đủ không?

**Không đủ.** Health check thường xác nhận process có thể trả lời request cơ bản; một service có thể UP nhưng truy vấn nghiệp vụ vẫn hỏng vì DB pool, partition, cache, quota hoặc dependency khác.

Phân biệt ba loại tín hiệu:

| Loại kiểm tra | Chứng minh | Giới hạn |
| --- | --- | --- |
| Liveness | Process chưa chết/hung | Không đảm bảo nghiệp vụ chạy được |
| Readiness | Instance tuyên bố sẵn sàng nhận traffic theo policy | Có thể không bao phủ đúng downstream path |
| Probe của Circuit Breaker | Lời gọi đã cho phép qua CB đáp ứng tiêu chí lỗi/latency | Mẫu nhỏ, chưa đảm bảo chịu được toàn bộ tải |

Nếu thiết kế probe riêng, cần có quyền truy cập, side-effect safety và latency budget rõ. Một probe trực tiếp gọi endpoint admin có thể bỏ qua auth, routing, connection pool hoặc logic nghiệp vụ nên cho kết luận sai.

Với dependency có thao tác ghi có side effect, thay vì “tạo dữ liệu thật để thử”, có thể đánh giá endpoint read-only đại diện cộng với các request hợp lệ có idempotency hoặc yêu cầu vận hành xác nhận trước khi nới tải. Bất kỳ cơ chế nào cũng phải ghi rõ **điều được chứng minh** và **điều chưa được chứng minh**.

## 12. Multi-instance và vấn đề khôi phục đồng loạt

Trong triển khai nhiều replica:

~~~text
                  ┌─ Order A ─ CB A ─┐
Clients → Gateway ┼─ Order B ─ CB B ─┼→ Inventory
                  └─ Order C ─ CB C ─┘
~~~

Một CB cục bộ thường chỉ có dữ liệu của một process. Order A có thể OPEN trong khi Order B vẫn CLOSED; điều này không nhất thiết là lỗi cấu hình. Mỗi instance nhận traffic và thống kê khác nhau.

Các rủi ro:

- Mọi instance cùng đặt wait duration 20 giây, nên cùng thử lại sau khi outage kết thúc.
- Tổng số probe trên hệ thống bằng tổng permit của các CB, có thể vẫn quá lớn.
- Instance ít traffic không đủ mẫu để thay đổi trạng thái.
- Restart service làm lịch sử CB cục bộ mất đi nếu không có giải pháp lưu trạng thái riêng.

Biện pháp phối hợp: giới hạn concurrency, jitter trong backoff phù hợp, cân bằng tải, cảnh báo theo service/dependency và quy trình khôi phục từng phần. Không chia sẻ trạng thái breaker toàn cụm một cách tùy tiện: trạng thái cục bộ có thể hữu ích khi lỗi chỉ xảy ra với một vùng mạng, một pod hoặc một routing path.

## 13. Fallback phải trung thực với mức độ chắc chắn của dữ liệu

Thiết kế fallback theo ý nghĩa nghiệp vụ, không phải chỉ để tránh HTTP 5xx.

| Chức năng | Fallback có thể chấp nhận | Điều cần tránh |
| --- | --- | --- |
| Danh sách gợi ý sản phẩm | Cache có TTL + nhãn “dữ liệu có thể chưa cập nhật” | Che giấu dữ liệu cũ như dữ liệu thời gian thực |
| Hiển thị tồn kho tham khảo | “Chưa thể xác nhận”, cache có cờ estimated nếu được phép | Khẳng định chắc chắn còn hàng từ cache stale |
| Xác nhận giữ hàng | Từ chối tạm thời, đưa vào quy trình bù trừ nếu có hợp đồng | Tự coi giữ hàng thành công khi Inventory unavailable |
| Thanh toán | Trạng thái “đang xác minh/không rõ”, kiểm tra transaction bằng idempotency key | Tự động phát sinh thanh toán lần hai vì timeout |
| Tìm kiếm tài liệu | Kết quả cache hoặc chế độ tìm kiếm hạn chế | Trả kết quả rỗng giả làm “không có tài liệu” |

Một fallback thành công về HTTP chưa chắc là thành công nghiệp vụ. Với response đã suy giảm chất lượng, nên có field/metadata biểu thị estimated/stale/degraded và metric riêng để product lẫn operations có thể nhận biết.

## 14. Quan sát và cảnh báo Circuit Breaker

Ít nhất cần quan sát theo **tên breaker**, **dependency**, **service gọi**, **instance**, và trong phạm vi cho phép là operation.

| Tín hiệu | Dùng để biết điều gì |
| --- | --- |
| Trạng thái CLOSED/OPEN/HALF_OPEN theo thời gian | Đang bảo vệ hay đang thử phục hồi |
| Số lần chuyển trạng thái | Có flapping hoặc mở kéo dài không |
| Failed / slow / successful calls | Vì sao breaker mở |
| Not permitted calls | Bao nhiêu traffic bị từ chối nhanh |
| Thời gian và kết quả từng đợt probe | Phục hồi có qua thử nghiệm không |
| Dependency latency p50/p95/p99 và error rate | Tình trạng thực ngoài breaker |
| Fallback count, cache age, degraded responses | Người dùng bị ảnh hưởng ở mức nào |
| Bulkhead concurrency/queue, timeout, retry count | Có nguy cơ quá tải dây chuyền không |

Trong hệ thống dùng Micrometer/Resilience4j, có thể xuất các metric như **resilience4j.circuitbreaker.state**, **resilience4j.circuitbreaker.calls** và những metric tương ứng về buffered calls/failure rate khi được bật. Khi xuất sang Prometheus, tên thường được chuẩn hóa thành dạng dấu gạch dưới. **Tên và nhãn thực tế phụ thuộc phiên bản/instrumentation**, cần kiểm tra ngay từ endpoint metrics của ứng dụng.

Cảnh báo hữu ích:

- Breaker OPEN kéo dài hơn khoảng thời gian cho phép của SLO.
- OPEN ↔ HALF_OPEN lặp lại nhiều lần mà không về CLOSED ổn định.
- Tỷ lệ not-permitted/fallback cao làm ảnh hưởng request người dùng.
- Breaker CLOSED nhưng dependency p95/p99 latency tăng mạnh: dấu hiệu sớm trước khi mở mạch.
- Một số replica luôn OPEN còn số khác khỏe: khả năng lỗi mạng/route/instance cục bộ.

Đừng chỉ alert khi “breaker chuyển OPEN”. Một breaker chuyển OPEN đúng lúc có thể là **cơ chế bảo vệ đang hoạt động chính xác**; nguyên nhân cần xử lý nằm ở dependency hoặc ngưỡng cấu hình không phù hợp.

## 15. Kiểm thử điều kiện chuyển trạng thái và phục hồi

Kiểm thử nên điều khiển kết quả downstream một cách xác định (fake client, MockWebServer, WireMock hoặc cơ chế tương đương) và quan sát trạng thái, số lời gọi HTTP thật, kết quả fallback. Không dùng sleep dài, thời gian ngẫu nhiên và môi trường mạng công cộng làm nguồn kỳ vọng chính.

### Ma trận kiểm thử đề xuất

| Ca | Thiết lập | Kỳ vọng kỹ thuật |
| --- | --- | --- |
| Hoạt động khỏe | Các lời gọi success trong CLOSED | Cho phép traffic; CB vẫn CLOSED |
| Chưa đủ mẫu | 4 lỗi trong 6 request, minCalls=10 | Chưa mở theo ngưỡng failure rate CLOSED |
| Vượt failure threshold | 5 lỗi/10 mẫu với threshold 50% | Chuyển OPEN |
| Vượt slow-call threshold | 7 slow/10 mẫu với threshold 70% | Chuyển OPEN dù có thể không lỗi |
| OPEN chặn traffic | Gửi thêm request ngay sau khi mở | Downstream không nhận request; caller nhận từ chối/fallback |
| Chưa hết wait duration | Thử trước mốc nghỉ | Chưa cho probe |
| Bắt đầu HALF_OPEN | Đủ thời gian, có request kích hoạt | Chỉ cấp số permit cấu hình |
| HALF_OPEN phục hồi | Probe có kết quả dưới các ngưỡng | Chuyển CLOSED; lưu lượng bình thường được phép |
| HALF_OPEN thất bại | Probe chạm failure/slow threshold | Trở về OPEN; chặn traffic tiếp |
| Lỗi nghiệp vụ | HTTP 404 hợp lệ/domain exception | Không bị tính sai thành lỗi sức khỏe |
| Timeout | Dependency treo quá latency budget | Ghi nhận failure theo classifier; request không treo vô hạn |
| Fallback | CB OPEN, cache có/không có | Trả degraded/unknown đúng hợp đồng |
| Nhiều replica | Hai breaker độc lập | Trạng thái được tính theo từng instance |

Các kiểm tra quan trọng:

**A. Đếm lời gọi thực:** Dùng counter ở fake downstream để xác minh khi OPEN không phát sinh thêm HTTP request. Chỉ assert exception ở caller là chưa đủ.

**B. Kiểm tra theo state transition:** Quan sát CLOSED → OPEN → HALF_OPEN → CLOSED hoặc HALF_OPEN → OPEN. Với timeout và scheduler, ưu tiên fake clock/timer hoặc cơ chế kiểm soát thời gian mà phiên bản thư viện hỗ trợ.

**C. Kiểm tra phân loại:** Một domain validation exception không làm tỷ lệ failure vượt ngưỡng; timeout và HTTP 503 được tính đúng. Nếu client nuốt exception và trả DTO lỗi như success, bài test phải phát hiện sự sai lệch.

**D. Kiểm tra permit:** HALF_OPEN không cho quá số phép đồng thời/đợt đã cấu hình. Kiểm tra xử lý lời gọi đang chạy lâu để tránh trạng thái treo mãi.

**E. Kiểm tra tích hợp:** Cấu hình Spring thật phải tạo đúng CB có tên **inventoryRead**; gateway phải dùng instance này, không dùng object mới sinh mỗi request hoặc bỏ qua proxy vì self-invocation.

**F. Kiểm tra nghiệp vụ:** Order không xác nhận giữ hàng khi chỉ có cache stale; Payment không phát sinh giao dịch trùng qua retry; response cho người dùng phản ánh đúng trạng thái degraded.

Những bài test trên kiểm tra **cơ chế resilience và contract nghiệp vụ**. Một bộ load test riêng mới chứng minh được hệ thống chịu mức tải kỳ vọng sau khi traffic quay lại.

## 16. Chọn thông số theo SLO thay vì sao chép cấu hình

Không có một bộ threshold tốt cho mọi endpoint. Khi thiết kế, hãy trả lời:

1. **Latency budget của caller là bao nhiêu?** Nếu Order chỉ có 800 ms cho tổng xử lý, timeout Inventory 2 giây là không phù hợp.
2. **Tải bình thường là bao nhiêu?** Cửa sổ 20 request ở 100 RPS chỉ phản ánh thời gian rất ngắn; ở 1 RPM lại phản ánh thời gian dài.
3. **Một lỗi có nghiêm trọng không?** Hệ thống kiểm soát thanh toán có thể yêu cầu xử lý khác hệ thống gợi ý sản phẩm.
4. **Downtime thường kéo dài bao lâu?** Open wait 20 giây có thể quá ngắn với restart database, quá dài với một lỗi mạng thoáng qua.
5. **Probe có gây side effect không?** Nếu có, phải dùng request idempotent hoặc đổi cách kiểm tra.
6. **Khi phục hồi tải có tăng đột ngột không?** Phải xét concurrency, retry và nhiều instance, không chỉ mỗi breaker.
7. **Có fallback nào đúng nghiệp vụ không?** Nếu không, ưu tiên lỗi rõ ràng và bảo vệ tài nguyên.

Một quy trình hiệu chỉnh:

- Bắt đầu từ SLO và latency/error baseline của dependency.
- Đặt timeout để request có giới hạn hoàn thành.
- Chọn classifier chính xác cho các loại lỗi.
- Chọn cửa sổ và minimum calls đủ giảm nhiễu.
- Chọn failure/slow threshold và open wait dựa trên dạng failure thực tế.
- Mô phỏng outage, recovery và peak load trong môi trường kiểm thử.
- Theo dõi việc mở nhầm, mở quá muộn, flapping và thời gian degraded trên production.
- Điều chỉnh bằng thay đổi cấu hình có thể truy vết; mỗi lần đổi nên gắn với số liệu trước/sau.

Đặc biệt với lưu lượng thấp, chỉ dùng failure percentage có thể không đủ. Có thể bổ sung timeout, readiness, synthetic monitoring, manual intervention hoặc policy riêng, nhưng không nên dùng chúng như bằng chứng thay thế vô điều kiện cho probe nghiệp vụ.

## 17. Playbook vận hành khi breaker liên tục OPEN

Khi thấy hệ thống ghi nhận **Inventory breaker OPEN**:

1. **Đo ảnh hưởng phía người dùng:** tỷ lệ order không thể xác nhận, số fallback, thời gian chờ và các chức năng liên quan.
2. **Kiểm tra nguyên nhân mở:** failure rate, slow-call rate, timeout, loại exception, downstream status. Xác định lỗi thực hay classifier/config sai.
3. **Kiểm tra dependency:** CPU, memory, thread pool, connection pool, DB, queue, deployment và các dependency sâu hơn.
4. **Giữ biện pháp bảo vệ đang hiệu quả:** tránh ép CB CLOSED nếu Inventory còn nghẽn; điều đó có thể phát tán outage.
5. **Quan sát đợt HALF_OPEN:** số probe được phép, latency, lỗi và thời gian giữ trạng thái. Nếu liên tục thất bại, xử lý nguyên nhân trước khi tăng tải.
6. **Nếu CLOSED rồi OPEN ngay:** kiểm tra retry storm, load spike, cache warm-up, autoscaling và tổng số instance cùng khôi phục. Có thể cần hạ/ramp traffic.
7. **Xác minh khôi phục nghiệp vụ:** request thật qua được, thông tin trạng thái đúng, không có duplicate side effect, backlog được xử lý.
8. **Ghi nhận sự cố:** thời điểm mở/đóng, chính sách quyết định, tác động tới SLO và thay đổi cần thử nghiệm.

**Không ép mở/đóng mạch thủ công** mà không xác định phạm vi và thời hạn áp dụng. Một trạng thái **FORCED_OPEN** bị quên có thể khiến hệ thống tiếp tục từ chối traffic dù downstream đã phục hồi.

## 18. Các sai lầm thường gặp

**Sai lầm 1 — mở mạch theo mọi HTTP 4xx.** Request sai do client gây ra không phải bằng chứng dependency mất khả dụng; classifier phải dựa trên hợp đồng.

**Sai lầm 2 — không có timeout.** Breaker ở CLOSED vẫn có thể giữ request vô hạn; ở HALF_OPEN, probe treo làm chậm quá trình đánh giá.

**Sai lầm 3 — retry vô hạn trước khi báo lỗi.** Retry có thể tạo tải nhiều lần so với traffic gốc và khiến cả timeout lẫn metrics bị hiểu sai.

**Sai lầm 4 — xem thời gian OPEN là dấu hiệu hồi phục.** Đây chỉ là cơ hội thử lại; phải đánh giá dữ liệu probe.

**Sai lầm 5 — coi một health endpoint UP là đủ.** Đường nghiệp vụ cần DB, network hoặc service khác có thể vẫn lỗi.

**Sai lầm 6 — tạo CB mới mỗi lần gọi.** Không có lịch sử sliding window, nên ngưỡng không hoạt động như mong muốn.

**Sai lầm 7 — dùng chung một CB cho mọi dependency.** Một upstream lỗi có thể chặn nhầm service khác; thiết kế breaker theo failure domain và operation.

**Sai lầm 8 — biến fallback thành dữ liệu “thành công” giả.** Cache cũ không được phép xác nhận thanh toán, giữ hàng hay tồn kho thời gian thực.

**Sai lầm 9 — bỏ qua multi-instance.** Hàng chục breaker phục hồi cùng lúc có thể tạo tổng tải probe đáng kể.

**Sai lầm 10 — chỉ kiểm tra rằng code không ném exception.** Cần xác nhận downstream thật sự không được gọi khi OPEN, số permit ở HALF_OPEN, trạng thái và chính sách nghiệp vụ.

## 19. Bài tập suy luận

### Bài tập A: đo failure rate

Một Circuit Breaker dùng COUNT_BASED window 20, minimum 10, failure threshold 50%. Sau 10 lời gọi, có 4 lỗi transport, 1 HTTP 404 hợp lệ được cấu hình ignore, 5 thành công. Có mở mạch không?

**Gợi ý:** Xác định lời gọi bị ignore được tính như thế nào trong tập mẫu đo của implementation, rồi tính lại mẫu hợp lệ và so sánh số lượng tối thiểu. Không tự coi HTTP 404 là failure.

### Bài tập B: thiết kế phục hồi

Một service kiểm tra giá có peak 1.000 RPS, CB OPEN 15 giây, HALF_OPEN cho 3 probe. Cả 3 probe thành công; sau khi CLOSED, toàn bộ traffic quay lại làm downstream quá tải.

**Câu hỏi:** Phần nào CB đã thực hiện đúng? Cần bổ sung cơ chế gì để bảo vệ giai đoạn ramp-up?

**Hướng giải:** CB đã hoàn thành kiểm tra ở quy mô nhỏ. Cần giới hạn concurrency/rate, backpressure hoặc rollout lưu lượng tăng dần và quan sát latency/error trong khi tăng tải.

### Bài tập C: side effect

Payment Service timeout sau khi caller gửi yêu cầu thanh toán. CB ghi nhận failure và chuyển OPEN. Caller không biết tiền đã bị trừ hay chưa.

**Câu hỏi:** Có nên retry ngay khi HALF_OPEN? Fallback “payment failed” có đúng không?

**Hướng giải:** Timeout tạo trạng thái **không xác định**. Cần idempotency key, truy vấn trạng thái giao dịch theo transaction ID và quy trình reconciliation; không tự động kết luận thất bại hay tạo giao dịch mới.

### Bài tập D: lựa chọn threshold

Giữa một endpoint phân tích nội bộ gọi 2 lần/phút và một endpoint đọc catalog gọi 200 lần/giây, có nên dùng cùng cửa sổ COUNT_BASED 20 request và wait OPEN 20 giây không?

**Hướng giải:** Không nhất thiết. 20 mẫu đại diện cho những khoảng thời gian rất khác nhau; cần cân nhắc độ mới, độ nhiễu, minimum samples, latency budget và số request phục hồi.

## 20. Checklist thiết kế trước khi đưa vào production

- [ ] Breaker gắn với dependency/operation có cùng failure domain.
- [ ] Timeout ở HTTP/network client được đặt theo ngân sách thời gian của caller.
- [ ] Có danh sách rõ ràng lỗi nào được count, ignore hoặc chuyển thành result failure.
- [ ] Sliding window, minimum calls, failure và slow-call thresholds có căn cứ từ traffic/SLO.
- [ ] Thời gian OPEN được hiểu là khoảng nghỉ trước thử lại, không là chứng nhận phục hồi.
- [ ] HALF_OPEN có số permit hạn chế và probe đại diện, ít side effect.
- [ ] Kết quả probe quyết định OPEN/CLOSED theo điều kiện đo lường cụ thể.
- [ ] Retry có giới hạn, backoff/jitter hợp lý và idempotency cho thao tác ghi.
- [ ] Fallback đúng nghiệp vụ, thể hiện rõ dữ liệu ước lượng/không chắc chắn.
- [ ] Có metrics trạng thái, failed/slow/not-permitted calls, fallback và downstream latency.
- [ ] Đã thử các đường CLOSED → OPEN → HALF_OPEN → CLOSED và HALF_OPEN → OPEN.
- [ ] Đã xét đa replica, tổng tải khi phục hồi, alerting và playbook vận hành.

## 21. Ghi nhớ

Circuit Breaker bảo vệ ranh giới gọi giữa các microservice bằng quyết định **cho gọi, từ chối nhanh hoặc thử phục hồi có giới hạn**. Điều kiện mở mạch cần dựa trên lỗi và độ chậm được phân loại chính xác. Điều kiện phục hồi phải có **thời gian nghỉ, lượng probe giới hạn và tiêu chí đánh giá kết quả**; một đồng hồ hết hạn hay một health check xanh không đủ chứng minh hệ thống đã khỏe. Khi kết hợp đúng timeout, retry có kiểm soát, bulkhead, fallback trung thực và quan sát vận hành, CB giúp cô lập lỗi và giảm nguy cơ một dependency suy sụp kéo cả hệ thống đi theo.
