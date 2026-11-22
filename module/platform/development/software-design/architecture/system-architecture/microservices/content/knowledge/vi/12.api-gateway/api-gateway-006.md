# Quản lý timeout và suy giảm tính năng ở lớp biên

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Cổng API (API Gateway)

## 1. Vấn đề: lớp biên không được biến một sự cố nhỏ thành mất dịch vụ toàn hệ thống

Trong một hệ thống microservices, **lớp biên** là nơi nhiều yêu cầu từ bên ngoài đi vào: API Gateway, reverse proxy, ingress hoặc Backend for Frontend (BFF). Lớp này thường thực hiện định tuyến, xác thực, giới hạn lưu lượng, quản lý kết nối, truyền ngữ cảnh và đôi khi tổng hợp dữ liệu từ nhiều service.

Một request đơn giản nhìn từ client có thể phụ thuộc nhiều nhánh phía sau:

```text
Mobile / Browser
      |
      | GET /home
      v
API Gateway / BFF
      |
      +---> ProfileService          (bắt buộc)
      +---> OrderService            (bắt buộc)
      +---> RecommendationService   (tùy chọn)
      '---> PromotionService        (tùy chọn)
      |
      v
Phản hồi trang chủ
```

Giả sử RecommendationService chậm 8 giây, trong khi phần hồ sơ và đơn hàng chỉ cần 200 ms. Nếu gateway chờ mọi nhánh hoặc tự retry không giới hạn, người dùng có thể mất cả trang chủ vì một tính năng gợi ý không thiết yếu.

Ngược lại, nếu gateway cắt timeout quá ngắn hoặc thay mọi dữ liệu lỗi bằng giá trị mặc định, nó có thể hiển thị **số dư sai, trạng thái thanh toán sai hoặc quyền truy cập sai**. Một hệ thống phản hồi nhanh nhưng sai nghiệp vụ không phải một hệ thống đáng tin cậy.

Bài toán có hai mục tiêu gắn chặt với nhau:

1. **Quản lý thời gian chờ có chủ đích:** mỗi request và mỗi nhánh có ngân sách thời gian hữu hạn; chờ đúng phần cần chờ, hủy hoặc dừng phát sinh công việc khi deadline không còn.
2. **Suy giảm tính năng có kiểm soát (graceful degradation):** khi dependency lỗi, giữ lại những chức năng vẫn có thể cung cấp **đúng nghĩa, an toàn và minh bạch**, thay vì để một nhánh tùy chọn làm sập toàn bộ hành trình.

Nguyên tắc cốt lõi:

> Lớp biên phải bảo vệ **ngân sách thời gian, tài nguyên và hợp đồng phản hồi**. Fallback chỉ hợp lệ khi dữ liệu thay thế có ý nghĩa nghiệp vụ và được phép sử dụng.

## 2. API Gateway, BFF và backend: ai chịu trách nhiệm điều gì?

Không phải mọi cơ chế phục hồi đều nên đặt ở gateway.

| Thành phần | Trách nhiệm phù hợp | Điều không nên làm |
| --- | --- | --- |
| API Gateway / ingress | Routing, connection timeout, giới hạn tải, xác thực ban đầu, deadline, lỗi proxy, telemetry, có thể cache theo policy | Tự suy đoán trạng thái nghiệp vụ hoặc quyết định thanh toán |
| BFF / API composition | Tổng hợp dữ liệu cho một giao diện; phân loại required/optional; tạo partial response theo contract | Sao chép toàn bộ quy tắc domain của mọi service |
| Backend service | Bảo vệ invariant, validation nghiệp vụ, idempotency, transaction, quyết định authoritative | Phụ thuộc gateway để bảo đảm dữ liệu đúng |
| Client | Đặt timeout tổng cho trải nghiệm, hiển thị trạng thái tải/lỗi, retry hành vi an toàn, cho phép làm mới | Diễn giải timeout là “thao tác chắc chắn chưa thực hiện” |
| Hạ tầng network/proxy | Kết nối, service discovery, balancing, transport retry trong phạm vi an toàn | Bảo đảm tác dụng phụ nghiệp vụ đúng một lần |

Ví dụ, gateway có thể biết **PaymentService không phản hồi trong deadline**. Nó không nên kết luận “thanh toán thất bại” hoặc “thanh toán thành công”; đó là **trạng thái chưa xác định** nếu request có thể đã tới Payment và được thực hiện.

Ngược lại, BFF có thể quyết định một widget gợi ý sản phẩm là optional và trả trang chủ không có widget đó, vì hợp đồng giao diện đã định nghĩa cách hiển thị thông tin thiếu.

Phân tách trách nhiệm giúp fallback đúng chỗ và tránh tạo một gateway vừa phức tạp, vừa khó phát hành độc lập.

## 3. Năm khái niệm thời gian dễ nhầm lẫn

### 3.1. Connection timeout

Giới hạn thời gian thiết lập kết nối tới downstream, bao gồm những bước do thư viện client định nghĩa. Nó không nhất thiết bao gồm DNS, TLS và toàn bộ request theo cùng một cách ở mọi stack. Cần đọc chính xác nghĩa cấu hình trong HTTP client/proxy đang dùng.

Khi không mở được kết nối trong thời gian cho phép, request thất bại sớm thay vì chiếm tài nguyên vô hạn.

### 3.2. Read/response timeout

Giới hạn thời gian chờ phản hồi hoặc đọc dữ liệu theo chính sách của transport. Một số proxy dùng **idle timeout giữa các lần nhận byte**, không phải tổng thời gian cả response. Vì thế cấu hình `read_timeout=3s` không nhất thiết bảo đảm cả request kết thúc trong 3 giây.

### 3.3. Request timeout

Một giới hạn áp dụng cho một lời gọi cụ thể. Với một số HTTP client, request timeout gồm nhiều pha của lần gọi; với proxy khác cần kết hợp nhiều giá trị. Không nên suy ra tất cả timeout cùng tên có cùng semantics.

### 3.4. Deadline end-to-end

**Deadline** là thời điểm tuyệt đối mà toàn bộ hành trình cần kết thúc, ví dụ “trước 14:30:05.300 UTC”. Mọi bước downstream phải biết mình còn bao nhiêu thời gian hữu ích.

```text
Client deadline: T = 1000 ms

  Edge auth/routing    80 ms
  BFF orchestration    50 ms
  Downstream calls    650 ms
  Response/transport  120 ms
  Reserve              100 ms
                     --------
  Total               1000 ms
```

Các con số chỉ minh họa **phân bổ ngân sách**. Thời gian thực tế phải đo bằng latency và tải ở từng môi trường.

### 3.5. Timeout nghiệp vụ / thời hạn xử lý job

Một yêu cầu xuất báo cáo có thể có deadline HTTP 1 giây để **nhận job**, nhưng job được phép chạy nhiều phút. Một giao dịch thanh toán có thể trả PENDING sau timeout HTTP và tiếp tục đối soát với đối tác. Không gắn thời gian sống của nghiệp vụ vào một kết nối mạng ngắn một cách máy móc.

**Phân biệt:** Timeout của kết nối nói “tôi đã ngừng chờ”, không tự khẳng định “tác vụ đích đã ngừng” hay “transaction chưa commit”.

## 4. Mô hình ngân sách thời gian: tránh cộng dồn timeout qua nhiều tầng

Giả sử luồng:

```text
Client
  | deadline 1200 ms
  v
Gateway
  | gọi BFF
  v
BFF
  |---> OrderService
  '---> PaymentService
```

Một cấu hình nguy hiểm:

- Gateway chờ BFF 1200 ms.
- BFF chờ mỗi service 1200 ms.
- OrderService lại gọi database 1200 ms.
- Khi timeout, mỗi tầng có thêm nhiều lần retry.

Một request của người dùng có thể hết thời gian từ lâu nhưng các nhánh phía dưới vẫn giữ thread, connection và transaction. Số request vô ích tích tụ, gây tail latency cao và quá tải lan truyền.

### 4.1. Deadline giảm dần

Nếu request bắt đầu tại thời điểm `T0` với ngân sách 1200 ms, deadline cuối là `T0 + 1200 ms`. Khi gateway đã dùng 90 ms, BFF không nên nhận lại toàn bộ 1200 ms; nó chỉ còn tối đa khoảng 1110 ms, trừ buffer cho thời gian truyền và phản hồi.

Quy tắc khái niệm:

```text
remaining = endToEndDeadline - now

childBudget = min(
    remaining - safetyBuffer,
    downstreamPolicyMax
)

if childBudget <= 0:
    failFast("DEADLINE_EXCEEDED")
```

Dùng **đồng hồ monotonic** để tính thời gian trôi qua trong một tiến trình khi có thể. Nếu deadline được truyền qua máy khác bằng timestamp tuyệt đối, cần xét clock skew và định dạng/chuẩn thời gian; có thể truyền thời gian còn lại theo quy ước của giao thức. Trong gRPC có khái niệm deadline truyền qua ngữ cảnh; với HTTP có thể dùng header nội bộ riêng, nhưng phải định nghĩa bên nào được quyền đặt và giới hạn giá trị.

### 4.2. Chừa ngân sách cho response

Không dành toàn bộ deadline cho downstream. Gateway/BFF còn cần serialization, nén, ghi response, proxying, TLS hoặc network delay. Nếu downstream hoàn tất đúng lúc deadline hết, client vẫn có thể không nhận được trả lời hữu ích.

### 4.3. Timeout phải theo SLO thực tế

Một downstream có p99 400 ms không có nghĩa đặt timeout 400 ms chắc chắn chỉ mất 1% request: latency phân phối thay đổi theo tải, vùng địa lý và kích thước request. Cần xác định SLO end-to-end, lưu lượng và error budget; đo khi hệ thống khỏe lẫn khi lỗi để chọn ngưỡng.

Timeout quá **ngắn** tạo false timeout, retry và tải thừa. Timeout quá **dài** tăng số request đang chờ và làm chậm khả năng phục hồi. Không có một con số mặc định đúng cho tất cả endpoint.

## 5. Timeout tại mỗi tầng phải nhất quán

Ví dụ một hành trình GET /dashboard:

| Tầng | Chính sách minh họa | Vai trò |
| --- | --- | --- |
| Client | Deadline 1500 ms | Trải nghiệm người dùng |
| Edge | Tổng xử lý tối đa khoảng 1300 ms | Chừa thời gian nhận/trả qua mạng |
| BFF | Deadline còn lại từ edge | Điều phối các nhánh |
| OrderService | Giới hạn riêng 600 ms | Nhánh required |
| Recommendation | Giới hạn riêng 250 ms | Nhánh optional |
| DB query | Statement/query timeout phù hợp | Không giữ tài nguyên sau khi request vô ích |

Các giá trị không phải khuyến nghị dùng nguyên cho production. Chúng cho thấy sự cần thiết của **một ngân sách chung** và giới hạn cụ thể theo dependency.

Nếu gateway timeout ở 500 ms còn BFF tiếp tục gọi backend tới 5 giây, request mà client đã bỏ sẽ tiếp tục tiêu thụ tài nguyên. Ngược lại, nếu gateway cho phép 10 giây nhưng client ngắt sau 1 giây, cần có đường truyền cancellation phù hợp để giảm công việc không còn người nhận.

### 5.1. Hủy request không đồng nghĩa rollback

Ngay cả khi client đóng kết nối và proxy hủy upstream, backend có thể:

- Chưa nhận request.
- Đã nhận nhưng chưa bắt đầu xử lý.
- Đang xử lý một transaction.
- Đã commit và đang gửi response.
- Đã chuyển công việc sang queue/job.

Vì vậy không thể suy từ `TimeoutException` rằng thao tác chưa xảy ra. Đặc biệt với POST thanh toán, đặt hàng và hoàn tiền, client cần **idempotency key, trạng thái có thể tra cứu và cơ chế đối soát**.

## 6. Phân loại dependency trước khi thiết kế suy giảm

Một phản hồi tổng hợp không phải tập hợp các field có mức quan trọng như nhau.

| Loại dependency | Ví dụ | Chính sách phù hợp |
| --- | --- | --- |
| Bắt buộc để trả lời đúng | OrderService trong GET /orders/{id} | Nếu unavailable, trả lỗi rõ; không tự dựng đơn hàng giả |
| Bắt buộc cho quyết định nhạy cảm | Payment/Inventory trong xác nhận hoặc hoàn tiền | Không phê duyệt hành động khi trạng thái chưa biết |
| Tùy chọn để hiển thị | Gợi ý sản phẩm, banner marketing | Có thể ẩn widget hoặc trả trạng thái unavailable |
| Có thể dùng cache | Hình ảnh/tên sản phẩm với freshness được chấp nhận | Dùng stale cache có hạn và hiển thị độ mới phù hợp |
| Có thể xử lý sau | Email, analytics, tạo báo cáo | Trả trạng thái accepted/pending, xử lý qua worker |
| Có thể dùng dữ liệu dự phòng | Nội dung tĩnh, cấu hình hiển thị đã xác nhận | Dùng bản dự phòng nếu chính sách cho phép |
| Không được fallback sang trạng thái an toàn giả | Quyền truy cập, số dư, kết quả thu tiền | Fail closed hoặc trạng thái UNKNOWN theo contract |

Phân loại này phải gắn với **use case**, không chỉ tên service. Payment có thể optional trên trang tổng quan để xem lịch sử, nhưng là required trong hành động giải ngân. Một cache trạng thái đơn hàng có thể đủ cho màn hình đọc, nhưng không đủ để quyết định hủy đơn nếu trạng thái đã thay đổi.

**Chỉ suy giảm nếu có thể giữ đúng ngữ nghĩa.** Nếu không, trả lỗi hoặc trạng thái chưa chắc chắn là hành vi chính xác hơn.

## 7. Partial response: giữ phần có giá trị mà không nói dối

Một BFF lấy dữ liệu trang chủ từ Profile, Orders và Recommendations. Nếu Recommendations timeout, phản hồi có thể là:

```json
{
  "profile": {
    "id": "cust-42",
    "displayName": "Khách hàng"
  },
  "recentOrders": [
    { "orderId": "ord-91", "status": "CONFIRMED" }
  ],
  "recommendations": {
    "status": "UNAVAILABLE",
    "items": [],
    "reasonCode": "UPSTREAM_TIMEOUT"
  },
  "partial": true,
  "requestId": "req-18"
}
```

Điều kiện: hợp đồng endpoint **đã cho phép** `recommendations` có thể thiếu. `items: []` ở đây phải được hiểu cùng `status: UNAVAILABLE`; nếu chỉ trả mảng rỗng, client có thể hiểu sai là “không có đề xuất nào” thay vì “không lấy được dữ liệu”.

Một số phương án biểu diễn:

- Mỗi section có `status` và `data`.
- Danh sách `degradedComponents` ở cấp response.
- Trường `partial: true` và mô tả loại thành phần còn thiếu.
- Header hoặc metadata nội bộ báo nguồn cache và mức độ mới.

Lựa chọn nào cũng cần **schema và semantic thống nhất**; không nên cho từng endpoint tự đặt tên tùy hứng.

### 7.1. Chọn HTTP status code cho partial response

Không có một status code HTTP chung bắt buộc cho mọi trường hợp “một phần dữ liệu tổng hợp”. Nếu endpoint vốn có hợp đồng trả thông tin optional, **200 OK kèm metadata partial** có thể hợp lý, vì response vẫn đáp ứng hợp đồng.

Không mặc định dùng **206 Partial Content** để diễn tả thiếu một widget: 206 chủ yếu gắn với cơ chế range request của HTTP. **207 Multi-Status** thuộc hệ sinh thái WebDAV và cũng không phải lựa chọn mặc định cho BFF. Nếu phần thiếu là bắt buộc khiến endpoint không còn đáp ứng yêu cầu, cần trả mã lỗi thích hợp.

### 7.2. Không trả partial ở các endpoint giao dịch quan trọng một cách vô điều kiện

Nếu endpoint có nghĩa “xác nhận khả năng giao hàng và thu tiền”, thiếu kết quả Payment hoặc Inventory có thể khiến kết quả **không đủ điều kiện xác nhận**. Không trả `200 { "confirmed": true, "payment": null }` để tránh lỗi UI. Tách hành động sang trạng thái PENDING hoặc từ chối với lý do có thể kiểm soát theo thiết kế nghiệp vụ.

## 8. Fallback: lựa chọn theo mức độ tin cậy của dữ liệu

Fallback là hành vi dự phòng khi đường gọi chính không thể hoàn tất trong chính sách.

| Fallback | Ví dụ | Điều kiện |
| --- | --- | --- |
| Bỏ tính năng tùy chọn | Không hiển thị gợi ý sản phẩm | UI biết section unavailable |
| Trả cache | Hiển thị thông tin sản phẩm đã cache | Có TTL, staleness và quyền truy cập phù hợp |
| Dùng bản sao đọc | Đọc projection của Orders | Độ trễ cập nhật được công bố; không dùng cho invariant mạnh |
| Dùng cấu hình dự phòng | Bộ banner hoặc thông điệp tĩnh cuối cùng hợp lệ | Dữ liệu đã xác minh và không ảnh hưởng bảo mật |
| Hàng đợi công việc | Tiếp nhận yêu cầu export và trả job ID | Job được ghi nhận bền vững, có trạng thái tra cứu |
| Chuyển vùng | Gửi sang region khác đã được chuẩn bị | Dữ liệu, quyền, quota và failover được kiểm chứng |
| Trả lỗi có cấu trúc | 503/504 hoặc lỗi domain hợp lệ | Không có kết quả thay thế đúng nghĩa |

Một cache `stale-if-error` có thể hợp lý cho dữ liệu công khai như mô tả sản phẩm. Nó có thể không chấp nhận được cho giá thanh toán cuối cùng, số lượng hàng có thể giữ hoặc trạng thái quyền truy cập.

### 8.1. Stale data không đồng nghĩa dữ liệu sai trong mọi ngữ cảnh

Một màn hình đọc lịch sử giao dịch có thể chấp nhận projection trễ vài giây nếu được trình bày rõ; một API đặt lệnh chuyển tiền thì không. Có thể cung cấp:

```json
{
  "accountSummary": {
    "data": {"displayBalance": "1200000", "currency": "VND"},
    "source": "CACHE",
    "asOf": "2026-11-11T08:58:00Z",
    "stale": true
  }
}
```

**Đây là ví dụ giao diện hiển thị**, không phải khuyến nghị dùng số dư cũ để phê duyệt chuyển tiền. Đặc biệt cần bảo vệ cache key theo tenant/user, kiểm tra authorization và tránh trộn dữ liệu của những người dùng khác nhau.

### 8.2. Fallback không được phát minh dữ liệu

Một kiểu lỗi nguy hiểm:

```java
try {
    return paymentClient.getStatus(paymentId);
} catch (TimeoutException ex) {
    return PaymentStatus.PAID; // SAI: Không biết kết quả.
}
```

Khi chưa có bằng chứng Payment đã thu tiền, fallback đúng có thể là trạng thái `UNKNOWN`, một lỗi có mã rõ ràng hoặc cơ chế hỏi lại nguồn authoritative. Việc “cho UI xanh” không thể quan trọng hơn tính đúng đắn của giao dịch.

## 9. Một gateway nên trả lỗi HTTP nào?

Trong thực tế phải xem điểm lỗi, hợp đồng, loại gateway và phương pháp proxying. Một bảng hướng dẫn thường gặp:

| Tình huống | Mã thường được cân nhắc | Lưu ý |
| --- | --- | --- |
| Client vượt rate limit do policy | **429 Too Many Requests** | Có thể kèm Retry-After khi phù hợp |
| Gateway không thể phục vụ do quá tải hoặc dependency unavailable | **503 Service Unavailable** | Có thể là tình trạng tạm thời, không bảo đảm sẽ tự phục hồi ngay |
| Gateway chờ upstream quá deadline | **504 Gateway Timeout** | Gateway/proxy đóng vai trò trung gian và không nhận response kịp |
| Gateway nhận response không hợp lệ hoặc lỗi giao tiếp từ upstream | **502 Bad Gateway** | Phụ thuộc trường hợp; không dùng cho mọi lỗi nghiệp vụ |
| Client không được xác thực | **401 Unauthorized** theo HTTP semantics | Không được fallback vượt qua auth |
| Client đã xác thực nhưng không có quyền | **403 Forbidden** | Không biến thành 200 hoặc dùng cache của người khác |
| Client yêu cầu resource không có | **404 Not Found** | Tùy chính sách bảo vệ thông tin |
| Trạng thái nghiệp vụ xung đột | **409 Conflict** ở nơi phù hợp | Không nên coi mọi 409 là lỗi mạng có thể retry |
| Công việc được ghi nhận để xử lý sau | **202 Accepted** | Không có nghĩa đã hoàn tất |

Những mã này không hoàn toàn thay thế **error code ở mức ứng dụng**, ví dụ `UPSTREAM_TIMEOUT`, `DEPENDENCY_UNAVAILABLE`, `REQUEST_DEADLINE_EXCEEDED` hoặc `PAYMENT_RESULT_UNKNOWN`.

Có một số gateway/log sử dụng mã **499** để diễn tả client đóng kết nối, nhưng 499 không phải HTTP status chuẩn để server tùy tiện trả như một hợp đồng phổ quát. Phải phân biệt metadata quan sát nội bộ với response thật sự mà client nhận.

### 9.1. Mẫu lỗi chuẩn hóa

```json
{
  "type": "https://api.example.test/problems/upstream-timeout",
  "title": "Dịch vụ tạm thời không phản hồi",
  "status": 504,
  "detail": "Không thể hoàn tất yêu cầu trong thời gian cho phép.",
  "code": "UPSTREAM_TIMEOUT",
  "requestId": "req-1828",
  "retryable": true
}
```

Ví dụ trên theo ý tưởng **Problem Details for HTTP APIs**; các trường mở rộng như `code`, `requestId`, `retryable` cần được định nghĩa trong contract. `retryable: true` không cho phép tự retry vô hạn hay gửi lại một thao tác có side effect không idempotent. Có thể chỉ trả retryable với những thao tác được thiết kế an toàn.

Với một endpoint thanh toán, nếu kết quả đang **UNKNOWN** thì cần dẫn client sang truy vấn trạng thái theo ID/idempotency key, không chỉ hiển thị thông báo “thử thanh toán lại”.

## 10. Circuit breaker: thất bại sớm khi downstream đang không khỏe

**Circuit breaker** quan sát các lời gọi tới dependency và hạn chế gọi khi tỷ lệ lỗi hoặc độ trễ vượt ngưỡng theo chính sách.

```text
                lỗi/slow calls vượt ngưỡng
    CLOSED --------------------------------> OPEN
      ^                                       |
      |                                       | hết thời gian chờ
      |                                       v
      '------------- HALF_OPEN <------------'
               thử số lời gọi có giới hạn
```

- **CLOSED:** cho phép lời gọi bình thường; ghi nhận lỗi/độ trễ.
- **OPEN:** từ chối nhanh các lời gọi mới, tránh tạo thêm tải vào dependency đã được đánh giá không khỏe.
- **HALF_OPEN:** cho phép lượng nhỏ request thử; nếu phục hồi thì đóng, nếu vẫn lỗi thì lại mở theo policy.

Circuit breaker **không phải** là cơ chế kiểm soát thời gian của từng request. Một request có thể bị treo ngay cả khi breaker còn CLOSED nếu transport không có timeout hữu hạn. Ngược lại, breaker OPEN cần chính sách fallback hoặc error đúng hợp đồng.

### 10.1. Đặt breaker theo dependency và loại operation

Nếu gateway có Catalog, Payment và Recommendation, không nên dùng một breaker chung tới mức lỗi Recommendation làm khóa Payment. Tách theo downstream, thậm chí theo operation quan trọng khi đủ căn cứ.

Không nên cấu hình breaker chỉ đếm mọi mã 4xx như lỗi dependency: một 400 do client gửi request sai không có nghĩa service đang không khỏe. Phải phân loại lỗi có thể phục hồi, lỗi business và lỗi cấu hình.

### 10.2. Tránh dao động khi nhiều instance cùng thử phục hồi

Nếu hàng chục gateway cùng HALF_OPEN một thời điểm, request thử có thể lại làm quá tải upstream. Các biện pháp như giới hạn probe, jitter và rate limit giúp giảm đồng bộ hóa khởi động lại. Nên quan sát số circuit đang OPEN/HALF_OPEN, không chỉ tỷ lệ request thành công.

## 11. Bulkhead: không để một nhánh chiếm hết tài nguyên

**Bulkhead** cô lập tài nguyên giữa các nhóm lời gọi. Ví dụ một BFF sử dụng chung executor có 20 worker. Nếu 20 request tới Recommendation chậm chiếm toàn bộ worker, ngay cả OrderService khỏe cũng không được gọi. Một bulkhead theo dependency giúp giới hạn số tác vụ in-flight.

```text
BFF / Gateway
  |
  +--> Orders:          max 30 in-flight
  +--> Payment:         max 12 in-flight
  '--> Recommendations: max 10 in-flight
```

Các số minh họa, không phải cấu hình mặc định. Giới hạn có thể là semaphore, executor hữu hạn, connection pool hoặc queue bounded tùy stack. **Rate limit** (request trên một khoảng thời gian) khác **concurrency limit** (request đang hoạt động). Cần dùng đúng công cụ cho vấn đề đang gặp.

### 11.1. Quá tải cần phản hồi rõ, không xếp hàng vô hạn

Nếu queue nội bộ vô hạn, gateway có thể nhận request với tốc độ cao hơn tốc độ xử lý trong thời gian dài, tăng memory, queue wait và timeout. Khi sát giới hạn, nên có admission control, queue hữu hạn và từ chối có mã/metrics rõ ràng thay vì nhận mọi việc rồi để hết deadline.

### 11.2. Tính giới hạn trên toàn cụm

Semaphore 20 permits **trên mỗi replica** không tương đương 20 permits toàn hệ thống. Với 8 gateway replicas, tổng mức đồng thời tới cùng downstream có thể cao hơn rất nhiều. Cần phối hợp quota của upstream, autoscaling, connection pools và số replica.

## 12. Retry: chỉ hữu ích khi có ngân sách và có lý do

Retry giúp vượt qua một số lỗi tạm thời: kết nối vừa reset, một backend vừa rút khỏi load balancer, lỗi 503 nhất thời. Nhưng retry cũng **khuếch đại lưu lượng**.

Giả sử có ba tầng gateway → BFF → service client, mỗi tầng thử tối đa ba lần (1 lần đầu + 2 retry). Ở kịch bản xấu nhất, một yêu cầu ban đầu có thể nhân lên tới (3 	imes 3 	imes 3 = 27) lần thử ở downstream cuối nếu mọi tầng lồng retry tương ứng. Điều này có thể làm dependency đang quá tải trở nên tồi tệ hơn.

### 12.1. Quy tắc retry có kiểm soát

1. Chọn **một tầng chịu trách nhiệm retry chính** cho một thao tác, tránh retry chồng tầng.
2. Chỉ retry lỗi được phân loại là tạm thời và có thể hồi phục.
3. Giới hạn số lần, backoff theo hàm tăng và jitter.
4. Tôn trọng deadline end-to-end; nếu hết ngân sách thì không retry.
5. Dùng **retry budget** để giới hạn tỷ lệ lưu lượng do retry tạo ra.
6. Kiểm tra idempotency trước khi retry request có side effect.
7. Theo dõi attempt count, reason và outcome, thay vì chỉ xem request thành công sau retry.

### 12.2. Không retry thao tác nhạy cảm một cách mù quáng

```text
Client --> Gateway --> PaymentService
                    |
                    | xử lý thành công, đã commit
                    |
           response bị mất / timeout
                    |
                    v
                Client thấy lỗi
```

Nếu gateway tự retry POST thanh toán với một transaction ID mới, có thể thu tiền hai lần. Một thiết kế an toàn hơn dùng **idempotency key ổn định**, PaymentService lưu trạng thái theo khóa đó và cung cấp API tra cứu kết quả khi response chưa rõ.

Ngay cả với phương thức HTTP thường được coi là idempotent, cần xác minh implementation và proxy logic có thực sự bảo toàn semantics. Retry không tự làm operation trở thành idempotent.

### 12.3. Hedged requests không phải mặc định

Gửi lời gọi đồng thời tới nhiều replica để lấy response đầu tiên (hedging) có thể giảm tail latency cho một số truy vấn chỉ đọc. Tuy nhiên nó làm tăng tải, có thể tạo side effect trùng và gây bất lợi khi downstream đã quá tải. Không nên áp dụng toàn cục tại gateway mà không đo kết quả, giới hạn số bản sao và phân loại operation rõ ràng.

## 13. Fallback ở lớp biên khác với fallback trong domain

Một API Gateway có thể biết endpoint đang không reachable, nhưng chỉ domain owner mới định nghĩa được:

- Tồn kho “không rõ” có cho phép tiếp tục đặt hàng hay không?
- Payment PENDING có thể cho khách rời màn hình không?
- Một chương trình ưu đãi đã hết hạn có được dùng cache stale không?
- Khi xác thực thất bại vì identity provider unavailable, có được dùng phiên đăng nhập hiện hữu không, và trong phạm vi nào?

### 13.1. Fail-open và fail-closed

- **Fail-open:** khi một kiểm soát gặp lỗi, cho phép hành vi tiếp tục. Chỉ phù hợp nếu đã đánh giá và được chấp thuận cho một số thành phần không nhạy cảm.
- **Fail-closed:** khi không thể xác minh điều kiện bảo mật/cho phép, không cấp quyền dựa trên suy đoán.

Không tự động “fail-open cho tính sẵn sàng cao” với authentication, authorization, chống gian lận hoặc quyết định chuyển tiền. Những trường hợp đó phải ưu tiên bảo vệ tài sản và dữ liệu, có chính sách rủi ro do chủ domain/security quyết định.

Ví dụ banner quảng cáo lỗi có thể bỏ qua. Dịch vụ kiểm tra quyền xem hồ sơ khách khác lỗi thì không được trả hồ sơ từ cache không kiểm tra quyền.

## 14. API composition: song song nhưng giới hạn số nhánh

Một BFF có thể bắt đầu các lời gọi độc lập cùng lúc để giảm thời gian, nhưng phải quản lý deadline và concurrency:

```text
                       +--> Profile (required, 300 ms)
Client --> Gateway ---> +--> Orders  (required, 500 ms) ---> Combine
                       +--> Promo   (optional, 150 ms)
                       '--> Recs    (optional, 220 ms)
```

Nếu lấy lần lượt Profile 150 ms, Orders 280 ms, Promo 100 ms, Recs 210 ms thì tổng thời gian gần 740 ms, chưa tính overhead. Nếu các nhánh độc lập và được phát đồng thời, độ trễ lý tưởng gần nhánh chậm nhất là 280 ms cộng overhead. Nhưng như vậy lượng outbound in-flight cao hơn, nên cần giới hạn theo request và theo dependency.

### 14.1. Tránh `allOf` cho mọi nhánh với cùng mức bắt buộc

Nếu một phần optional timeout, không nên tự động hủy toàn bộ response nếu còn phần required đủ dữ liệu. Ngược lại, không nên coi một lời gọi required bị lỗi là optional chỉ để trả 200.

Một kế hoạch:

1. Xác định các nhánh bắt buộc từ contract trước.
2. Xác định deadline và budget riêng từng nhánh.
3. Phát song song trong giới hạn concurrency.
4. Khi nhánh optional lỗi, ghi nhận lý do và xây partial response.
5. Khi nhánh required lỗi, quyết định fail-fast hoặc trạng thái nghiệp vụ chưa rõ.
6. Hủy hoặc ngừng phát công việc vô ích khi deadline hết, trong phạm vi client/transport hỗ trợ.
7. Ghi telemetry cho từng nhánh và tình trạng partial.

### 14.2. Nếu fan-out quá lớn, xem lại thiết kế

Đừng chỉ tăng số thread. Có thể:

- Dùng bulk API thay cho N+1 calls.
- Dùng read projection/CQRS cho màn hình tổng hợp.
- Cache dữ liệu hiển thị có chính sách freshness.
- Giảm số trường được tải mặc định.
- Tách widget có thể tải sau trên client.
- Chuyển hậu xử lý không cần phản hồi ngay sang queue/job.

Mục tiêu là **giảm số dependency bắt buộc trên critical path**, không phải che phủ một thiết kế quá nhiều lời gọi bằng timeout.

## 15. Cách dùng HTTP 202 và job status để suy giảm hợp lý

Một tác vụ có thể chạy lâu hơn thời gian người dùng muốn giữ kết nối, ví dụ tạo báo cáo hoặc tải dữ liệu phân tích. Thay vì cấu hình gateway timeout 5 phút:

```http
POST /report-exports
Content-Type: application/json

{"period":"2026-10"}
```

Response:

```http
HTTP/1.1 202 Accepted
Location: /report-exports/job-91
Content-Type: application/json

{"jobId":"job-91","status":"PENDING"}
```

Client có thể:

```http
GET /report-exports/job-91
```

và nhận trạng thái `PENDING`, `RUNNING`, `COMPLETED` hoặc `FAILED` theo contract. Khi hoàn tất, kết quả có thể được truy cập qua đường dẫn tải được phân quyền và có thời hạn.

**202 chỉ có nghĩa yêu cầu đã được tiếp nhận theo hợp đồng**, không nói job chắc chắn sẽ hoàn tất. Hệ thống cần lưu job bền vững, truy vấn trạng thái, idempotency nếu client gửi lại, giới hạn số job, retry và quản lý lỗi.

Đây là một phương pháp chuyển **thời gian xử lý nghiệp vụ dài** ra khỏi **timeout HTTP ngắn**, không phải cơ chế để che giấu lỗi bắt buộc.

## 16. Ví dụ cấu hình gateway: timeout không phải tất cả đều giống nhau

Nhiều gateway hỗ trợ các cấu hình tên gần giống:

```text
connect timeout
read/response timeout
send/write timeout
idle timeout
request processing timeout
upstream timeout
retry attempts / retry budget
max pending requests / connections
circuit breaker / outlier detection
```

Tên và nghĩa chính xác thay đổi theo NGINX, Envoy, Spring Cloud Gateway, ingress controller, API management platform và phiên bản cụ thể. Không sao chép một bộ số giữa các hệ thống nếu chưa hiểu semantics.

Ví dụ khái niệm với NGINX reverse proxy:

```nginx
location /api/catalog/ {
    proxy_pass http://catalog_upstream;

    proxy_connect_timeout 1s;
    proxy_read_timeout    3s;
    proxy_send_timeout    3s;
}
```

Các giá trị chỉ minh họa. **`proxy_read_timeout` thường giới hạn khoảng thời gian giữa các lần đọc từ upstream**, không phải deadline tổng của cả response; `proxy_send_timeout` cũng có semantics liên quan tới khoảng cách giữa các thao tác ghi. Vì vậy muốn enforce **deadline toàn hành trình** cần xem thêm timeout tổng ở tầng phù hợp, hành vi client và propagation tới backend.

Ngoài ra cần kiểm tra:

- Gateway sẽ trả response gì khi không có upstream hoặc upstream chậm?
- Retry có được bật mặc định không, và có retry POST không?
- Proxy có tự buffer request/response không?
- Bắt đầu gửi response cho client rồi mà upstream lỗi thì còn đổi HTTP status được không?
- Có hỗ trợ stream, WebSocket, SSE hoặc gRPC với semantics timeout riêng không?
- Thay đổi cấu hình có áp dụng giống nhau cho tất cả route, tenant và zone không?

Không phải mọi yêu cầu nên đi qua một timeout đồng nhất. API truy vấn nhẹ, download file, upload lớn, stream dài và command không đồng bộ có **hợp đồng thời gian khác nhau**.

## 17. Ví dụ Java/BFF: truyền deadline và fallback theo contract

Pseudocode sau nhấn mạnh **trình tự tư duy**, không phụ thuộc một framework cụ thể:

```java
Summary getHomeSummary(Request req) {
    Deadline deadline = Deadline.afterMillis(1200);

    Future<Profile> profile = boundedCall(
        () -> profileClient.getProfile(
            req.userId(), deadline.childMaxMillis(450)));

    Future<List<Order>> orders = boundedCall(
        () -> orderClient.recentOrders(
            req.userId(), deadline.childMaxMillis(650)));

    Future<List<Product>> recs = boundedCall(
        () -> recommendationClient.forUser(
            req.userId(), deadline.childMaxMillis(250)));

    // Profile/Orders là required theo hợp đồng.
    Profile p = awaitRequired(profile, deadline);
    List<Order> o = awaitRequired(orders, deadline);

    // Recommendation được phép không có dữ liệu.
    Optional<List<Product>> r = awaitOptional(recs, deadline);

    return Summary.builder()
        .profile(p)
        .recentOrders(o)
        .recommendations(r.orElse(List.of()))
        .recommendationsStatus(
            r.isPresent() ? "AVAILABLE" : "UNAVAILABLE")
        .partial(r.isEmpty())
        .build();
}
```

Ở đây `Deadline`, `boundedCall`, `awaitRequired`, `awaitOptional` là **các abstraction giả định**; ví dụ không nhằm biên dịch nguyên văn. Trong triển khai thật:

- `boundedCall` phải giới hạn in-flight và queue, không tạo thread vô hạn.
- `childMaxMillis` không được cấp ngân sách lớn hơn thời gian còn lại thực.
- HTTP client phải có connect/request/response timeout phù hợp ở transport.
- Hủy `Future` không tự đảm bảo request mạng đã dừng hoặc transaction rollback.
- `awaitOptional` cần phân biệt lỗi timeout, unauthorized và lỗi schema; không chuyển mọi lỗi thành “danh sách rỗng”.
- Không đợi nhánh optional quá deadline chỉ vì nhánh required đã hoàn thành.
- Response contract cần mô tả trạng thái partial để client không hiểu sai.

### 17.1. Java CompletableFuture không tự tạo deadline end-to-end

`CompletableFuture.orTimeout(...)` có thể làm future hoàn tất ngoại lệ sau thời gian chờ, nhưng không mặc nhiên chấm dứt HTTP request đang chạy bên dưới. Nếu dùng blocking client trong executor, thread có thể vẫn bị giữ. Cần timeout ở client transport và có thể cấu hình cancellation/connection close theo khả năng thực.

### 17.2. Reactive và virtual threads cũng cần giới hạn

Reactive/non-blocking I/O hoặc Java virtual threads có thể giảm chi phí giữ thread khi nhiều I/O, nhưng **không tăng sức chịu tải của upstream vô hạn**. Vẫn phải áp concurrency limits, queue/backpressure, deadline, rate limit và giảm tải khi downstream saturation.

## 18. Failure mode: chờ quá lâu, retry storm và cascading failure

Một sự cố nhỏ có thể khuếch đại:

```text
Payment chậm
    |
    v
Gateway đợi lâu hơn
    |
    v
Nhiều request đang bay tăng
    |
    v
Thread/connection pool bão hòa
    |
    v
Các route khác cùng chậm
    |
    v
Client timeout và retry
    |
    v
Tải tăng thêm lên Payment và Gateway
```

Đây là dạng **cascading failure**. Cách cắt vòng lặp:

1. Giữ timeout và deadline hữu hạn.
2. Giới hạn request đang bay và queue.
3. Có bulkhead theo dependency/route quan trọng.
4. Dùng circuit breaker có phân loại lỗi đúng.
5. Retry hữu hạn, có budget và không lồng tầng.
6. Chọn partial/fallback chỉ khi hợp đồng cho phép.
7. Giảm tải ở lớp biên bằng admission control/rate limit.
8. Quan sát độ trễ phần đuôi và saturation, không chỉ latency trung bình.
9. Khi cần, chuyển công việc dài ra khỏi request đồng bộ.
10. Bảo vệ các thao tác giao dịch bằng idempotency và tra cứu trạng thái.

**Sự phục hồi thường bắt đầu từ việc ngừng tạo thêm công việc vô ích**, thay vì liên tục retry để cố giữ mọi request thành công.

## 19. Tính toán một ví dụ fan-out và chi phí tài nguyên

Giả sử gateway nhận 400 request/giây tới trang tổng hợp, mỗi request tạo 4 downstream calls:

```text
Outbound calls/giây = 400 × 4 = 1.600
```

Nếu downstream trung bình mất 0,15 giây, lượng outbound in-flight trung bình theo trực giác Little's Law trong trạng thái ổn định có thể khoảng:

```text
1.600 × 0,15 = 240 in-flight calls
```

Khi nhiều downstream chậm lên 0,8 giây mà arrival rate vẫn như cũ:

```text
1.600 × 0,8 = 1.280 in-flight calls
```

Những con số trên là **ước lượng trung bình với giả định minh họa**, không phải số connection thực tế hay kích thước executor phải dùng. Fan-out có thể phân bố không đều giữa service, connection HTTP/2 có multiplexing và có nhiều lớp queue. Chọn cấu hình phải dựa trên p95/p99, số replica, quota và thí nghiệm tải.

Nó cho thấy vì sao timeout và concurrency có quan hệ nhân quả: thời gian chờ dài làm tăng công việc đang tồn tại, trong khi retry còn làm tăng số request mới. Một BFF “chỉ ghép dữ liệu” vẫn có thể trở thành điểm khuếch đại tải của toàn hệ thống.

## 20. Streaming, download và kết nối dài: không áp cùng timeout

Không phải mọi phản hồi phải hoàn tất trong 1–2 giây:

- **File download:** có thể truyền dữ liệu trong thời gian dài; cần phân biệt idle timeout với total timeout, hỗ trợ range/resume nếu phù hợp.
- **Server-Sent Events:** giữ kết nối để đẩy dữ liệu một chiều, cần heartbeat/reconnect và giới hạn số kết nối.
- **WebSocket:** có cơ chế keepalive/idle riêng, cần xử lý client disconnect và quá tải.
- **gRPC streaming:** có deadline, flow control, stream lifetime và cancellation; không dùng chính sách unary RPC máy móc.
- **Long polling:** mỗi request chờ một khoảng có chủ đích; gateway phải hỗ trợ thời hạn đó, nhưng vẫn cần giới hạn số kết nối.
- **Upload lớn:** có thể cần giới hạn kích thước, idle timeout, streaming và cơ chế lưu tạm phù hợp.

**Không tăng timeout toàn bộ gateway chỉ để cứu một endpoint streaming.** Nên cấu hình policy theo route/operation và giới hạn tài nguyên theo loại lưu lượng.

## 21. Bảo mật khi suy giảm tính năng

Suy giảm chức năng không có nghĩa bỏ những điều kiện bắt buộc:

1. Không bỏ xác thực chỉ vì Identity Provider chậm, trừ một policy đã được đánh giá và kiểm soát rõ cho loại request cụ thể.
2. Không trả cache của người dùng khác vì cache key thiếu tenant/subject.
3. Không fallback sang backend không mã hóa hoặc không kiểm tra chứng chỉ chỉ vì TLS handshake lỗi.
4. Không cho phép giao dịch nếu hệ thống chống gian lận hoặc kiểm soát hạn mức không đưa ra quyết định bắt buộc.
5. Không phát raw downstream error chứa token, connection string hoặc PII ra client.
6. Không để header deadline/correlation từ bên ngoài được dùng để gây quá tải hoặc vượt quá giới hạn tài nguyên nội bộ.
7. Không ghi log toàn bộ payload nhạy cảm chỉ để debug timeout.
8. Bảo vệ retry, circuit-breaker reset và các endpoint quản trị bằng quyền truy cập phù hợp.

Một gateway có thể chọn **ẩn tính năng không nhạy cảm** khi dependency lỗi, nhưng không được “suy giảm chính sách bảo mật” thành cấp quyền mặc định.

## 22. Quan sát và metrics để biết chính sách có hiệu quả không

Không chỉ nhìn 5xx của gateway. Một fallback có thể làm 200 tăng lên trong khi dữ liệu thiếu nhiều hơn; nếu chỉ xem HTTP success rate, người vận hành sẽ bỏ lỡ sự suy giảm trải nghiệm.

| Nhóm chỉ số | Ví dụ |
| --- | --- |
| End-to-end | Request rate, p50/p95/p99 latency, tỉ lệ timeout, error rate theo route |
| Downstream | Latency, success/error rate, connect/read timeout theo từng service |
| Degradation | Partial-response rate, fallback rate, cache-stale rate, component-unavailable count |
| Retry | Attempts/request, retry rate, retry-success, retry-exhausted, amplification |
| Circuit breaker | OPEN/HALF_OPEN transitions, rejected-by-breaker |
| Bulkhead | In-flight, permit usage, queue wait, queue depth, rejection count |
| Pool và network | Active connections, pool wait, connection reset, TLS handshake failures |
| Client | Client cancellation, deadline exceeded, mobile/network context nếu được phép |
| Business | Đơn bị trì hoãn, thanh toán kết quả UNKNOWN, số lượng thao tác trùng, sai lệch dữ liệu |
| Saturation | CPU, memory, executor queue, downstream connection limit, quota usage |

### 22.1. Trace một request qua nhiều service

Một distributed trace nên thể hiện:

```text
GET /home                       total 540 ms
  ├─ Gateway auth               35 ms
  ├─ BFF compose                470 ms
  │    ├─ ProfileService        110 ms  OK
  │    ├─ OrderService          420 ms  OK
  │    └─ Recommendation        250 ms  TIMEOUT -> fallback
  └─ Response write             35 ms
```

Các con số minh họa. Trace giúp nhận ra nhánh nào là critical path và fallback đã kích hoạt. Nên ghi request/correlation ID, deadline còn lại, route, retry attempt và outcome, nhưng kiểm soát độ nhạy cảm và cardinality của attribute.

### 22.2. SLO phải kể cả chất lượng partial

Một hệ thống chỉ báo “99,95% request trả 200” có thể vẫn kém nếu 40% trang chủ thiếu đơn hàng. Cân nhắc phân biệt:

- **Full-success:** đủ dữ liệu bắt buộc và tùy chọn theo mục tiêu trải nghiệm.
- **Useful partial:** đủ phần cốt lõi; có thành phần tùy chọn bị thiếu.
- **Hard failure:** không đáp ứng được hợp đồng.
- **Incorrect success:** HTTP 200 nhưng dữ liệu nghiệp vụ sai.

Không thể thay thế việc đo tính đúng đắn bằng status code. Với partial hợp lệ, có thể xác định SLO riêng về tỷ lệ xuất hiện và thời gian phục hồi của từng widget.

## 23. Kiểm thử timeout và graceful degradation có kiểm soát

Chạy thử trên môi trường có các giới hạn rõ, không gây ảnh hưởng production ngoài kế hoạch.

### 23.1. Kịch bản kiểm thử thiết yếu

1. **Downstream chậm hơn budget:** gateway/BFF phải kết thúc theo deadline, không giữ tài nguyên vô hạn.
2. **Downstream không có endpoint:** trả lỗi hoặc fallback đúng, tránh retry storm.
3. **Một optional dependency lỗi:** phần required vẫn hoạt động, response khai báo partial.
4. **Một required dependency lỗi:** không trả dữ liệu giả để tạo thành công.
5. **Lỗi sau khi backend đã commit:** client nhận trạng thái chưa chắc chắn và có cách tra cứu/idempotency.
6. **Circuit breaker OPEN:** request thất bại nhanh, không tràn sang service khỏe.
7. **Pool/queue đầy:** từ chối theo policy, không tạo queue vô hạn.
8. **Nhiều lớp cùng retry:** số downstream attempts nằm trong giới hạn đã định.
9. **Cache stale:** dữ liệu có metadata thời gian, không vi phạm quyền truy cập hoặc business freshness.
10. **Client hủy request:** kiểm tra backend có ngừng công việc khi có thể và không rơi vào trạng thái sai.
11. **Rolling update backend:** connection reset ngắn không dẫn tới tỷ lệ lỗi kéo dài; retry chỉ khi an toàn.
12. **SSE/WebSocket/download:** route dài sống theo timeout phù hợp, không ảnh hưởng route HTTP thông thường.

### 23.2. Failure injection và latency injection

Có thể tiêm delay, 503, connection reset, DNS failure hoặc tạm cắt một downstream để quan sát hành vi. Khi dùng chaos engineering, phải định nghĩa phạm vi, giới hạn và tiêu chí dừng; không biến bài thử thành một sự cố thật.

Ghi lại trước và sau: p99, tỉ lệ fallback, circuit state, số retry, resource saturation và business outcome. Một thay đổi khiến mean latency giảm nhưng p99, lượng lỗi hoặc số giao dịch chưa rõ tăng có thể không đáng áp dụng.

## 24. Case study: trang chủ hoạt động khi RecommendationService mất kết nối

### 24.1. Yêu cầu

Một ứng dụng bán hàng hiển thị:

- Hồ sơ khách hàng (required).
- Đơn gần đây (required).
- Gợi ý sản phẩm (optional).
- Banner khuyến mãi (optional).

Mục tiêu trải nghiệm là phần dữ liệu chính xuất hiện trong khoảng 1 giây ở điều kiện phục vụ bình thường. Hệ thống không được hiển thị thông tin khách khác hoặc kết luận sai tình trạng đơn.

### 24.2. Thiết kế tuyến dữ liệu

```text
Mobile
  |
  | GET /home
  v
Gateway: auth + route + deadline
  |
  v
HomeBFF (bounded concurrency)
  |
  +--> ProfileService --------- required
  +--> OrderService ----------- required
  +--> RecommendationService -- optional, deadline ngắn
  '--> PromotionService ------- optional, cache nếu được phép
```

### 24.3. Khi Recommendation timeout

BFF không đợi vô thời hạn và không retry liên tục. Nó trả `recommendations.status=UNAVAILABLE`, cho phép client ẩn widget và giữ phần dữ liệu chính. Metrics tăng `partial_response_count` và `recommendation_timeout_count`; tracing ghi rõ nhánh thiếu.

### 24.4. Khi OrderService timeout

Nếu dữ liệu đơn hàng là required, BFF không thể trả 200 và dùng danh sách rỗng như thể khách không có đơn. Một lựa chọn là trả lỗi có cấu trúc và client hiển thị trạng thái không tải được, hoặc nếu hợp đồng đã thiết kế để tách phần hồ sơ khỏi đơn hàng thì trả partial theo thiết kế đó.

Cách chọn phụ thuộc hợp đồng cụ thể, không phải “đã bật graceful degradation nên mọi lỗi đều có thể bỏ qua”.

### 24.5. Khi ProfileService trả 403

Gateway/BFF không fallback sang cache không kiểm tra quyền. Lỗi phân quyền phải được xử lý đúng chính sách bảo mật. Circuit breaker và retry không được làm thay đổi quyết định từ 403 thành 200.

### 24.6. Khi gateway mất kết nối với mọi downstream

Đây là hard failure hoặc có thể là tình trạng quá tải của tuyến mạng. Trả mã lỗi tương ứng và request ID để điều tra. Nếu vẫn có nội dung công khai được cache hợp lệ, có thể phục vụ theo policy riêng, nhưng không ngụy trang những endpoint cá nhân hóa thành dữ liệu đã xác thực.

## 25. Case study: thanh toán timeout sau khi đã xử lý

### 25.1. Chuỗi sự kiện

```text
Client             Gateway          Payment
  | POST /pay         |                |
  |------------------>|---------------->
  |                   |             xử lý/commit
  |                   |                |
  |                   |<--- response ---X  (mất gói)
  |<--- timeout ------|
  |
  | Người dùng thấy chưa có kết quả
```

Nếu client/gateway diễn giải timeout là thất bại chắc chắn và gửi một POST mới với ID khác, có thể tạo tác dụng phụ trùng.

### 25.2. Thiết kế đáng tin cậy hơn

- Client tạo `Idempotency-Key` ổn định cho **một ý định giao dịch**.
- Gateway truyền khóa tới Payment, không tự tạo khóa mới trên mỗi attempt.
- Payment lưu kết quả theo khóa cùng logic nghiệp vụ phù hợp.
- Khi timeout, client truy vấn `GET /payments/by-idempotency-key/... ` hoặc một endpoint/status resource tương đương đã được bảo mật.
- Nếu không thể xác định kết quả ngay, trạng thái là `PENDING` hoặc `UNKNOWN` theo contract, không tự chọn `FAILED`.
- Retry chỉ được phép theo policy và khả năng chống lặp của Payment; khi cần, dùng reconciliation với đối tác thanh toán.

Đây là ví dụ cho thấy **timeout là vấn đề về sự không chắc chắn trong giao tiếp**, không chỉ là độ trễ. Fallback phải bảo toàn invariant “không thu tiền hai lần”.

## 26. Checklist cấu hình trước production

### 26.1. Ranh giới và hợp đồng

- Endpoint nào là query, command, upload, download, stream hoặc job initiation?
- Những downstream nào required, optional, có thể cache hoặc xử lý sau?
- Partial response có schema/semantic rõ ràng và client có hiểu nó không?
- Timeout có được diễn giải thành UNKNOWN khi kết quả nghiệp vụ chưa xác định?
- Có idempotency key cho thao tác có side effect khi client/proxy retry không?

### 26.2. Thời gian và tài nguyên

- Có deadline end-to-end và cách truyền time budget giữa các tầng không?
- Connect/read/write/request/idle timeout của stack thật có nghĩa chính xác gì?
- Có chừa buffer cho serialization và trả response không?
- Có giới hạn concurrency, queue, connection pool, body size và rate limit theo route không?
- Có ngăn retry nhiều tầng và đảm bảo retry không vượt deadline không?
- Nếu client hủy request, có đường giảm công việc vô ích khi khả thi không?

### 26.3. Fallback và bảo mật

- Mỗi fallback có được domain owner chấp thuận và phù hợp với freshness không?
- Cache key có bao gồm tenant/user/authorization context cần thiết không?
- Có tránh tạo trạng thái `PAID`, `AVAILABLE`, `AUTHORIZED` giả từ lỗi mạng không?
- Khi authz không xác minh được, hệ thống có fail closed theo policy không?
- Lỗi gửi ra client có tránh lộ thông tin nhạy cảm và có request ID không?

### 26.4. Quan sát và vận hành

- Có metrics tách full-success, partial-success và hard failure không?
- Có phân biệt timeout gateway, BFF, HTTP client, DB và downstream không?
- Có đo retry amplification, breaker state, queue wait và rejected requests không?
- Có trace qua các nhánh song song và tên dependency không?
- Có load test và failure injection cho trường hợp optional/required hỏng không?
- Có chính sách rollback khi một thay đổi timeout làm tăng lỗi thật không?

## 27. Bài tập thực hành

Một API Gateway cung cấp `GET /account-overview` gồm:

| Nguồn | Latency một lần đo | Mức cần thiết |
| --- | ---: | --- |
| Identity | 100 ms | Xác thực/phân quyền bắt buộc |
| Profile | 130 ms | Bắt buộc |
| Balance | 240 ms | Bắt buộc để hiển thị số dư có thẩm quyền |
| Offers | 700 ms | Tùy chọn |
| RecentActivity | 280 ms | Tùy chọn nếu contract cho phép |

Client đặt deadline 900 ms. Gateway có overhead xác thực/định tuyến 70 ms và thời gian serialization/transport dự kiến 100 ms.

Hãy phân tích:

1. Có bao nhiêu thời gian lý thuyết còn lại dành cho các nhánh downstream nếu cần thêm buffer?
2. Nếu gọi nối tiếp toàn bộ nhánh, giới hạn thời gian nào dễ bị vượt?
3. Nếu gọi song song, vì sao nhánh Offers 700 ms vẫn có thể làm tổng response chậm quá mức?
4. Có nên trả offers trống khi Offers timeout? Contract cần thông tin gì để không bị hiểu sai?
5. Nếu Balance timeout, có nên dùng số dư cache 10 phút để quyết định cho phép chuyển tiền không?
6. Nếu Identity không phản hồi, tại sao fail-open có thể nguy hiểm?
7. Nếu 1.000 client cùng retry sau 504, có những cơ chế nào cắt retry storm?
8. Nếu backend xử lý xong một POST nhưng response mất, vì sao timeout không cho phép kết luận thao tác thất bại?
9. Những metrics nào giúp phân biệt gateway quá tải, pool chờ và downstream chậm?
10. Hãy đề xuất một cách thử nghiệm khi RecentActivity tắt hoàn toàn nhưng Profile/Balance vẫn khỏe.

**Gợi ý:** Thời gian còn lại theo phép trừ đơn giản là 900 − 70 − 100 = 730 ms trước khi trừ buffer khác. Đó là **giới hạn ngân sách**, không phải thời gian phải cấp hết cho mỗi nhánh. Offers nên có budget ngắn hơn nếu không phải thành phần cốt lõi; Identity và Balance đòi xử lý an toàn, không được “thành công giả”.

## 28. Những ngộ nhận cần tránh

1. **“Timeout nghĩa là request chắc chắn chưa chạy.”** Sai; tác dụng phụ có thể đã được commit.
2. **“Cấu hình read timeout là đã giới hạn tổng request.”** Không luôn đúng; nhiều transport dùng idle timeout.
3. **“Càng retry nhiều càng tăng độ tin cậy.”** Có thể gây amplification và cascading failure.
4. **“200 OK nghĩa là đủ dữ liệu.”** Chỉ đúng nếu hợp đồng khẳng định như vậy; partial cần được biểu diễn rõ.
5. **“Mọi lỗi đều có thể trả cache.”** Sai đối với quyền truy cập, thanh toán hoặc dữ liệu phải nhất quán mạnh.
6. **“Circuit breaker thay thế timeout.”** Sai; breaker và timeout bảo vệ các chiều khác nhau.
7. **“Một semaphore trên gateway giới hạn toàn cụm.”** Sai khi có nhiều replica.
8. **“Gateway phải tự giải quyết mọi lỗi nghiệp vụ.”** Không; domain owner quyết định semantic và invariant.
9. **“Dùng reactive/virtual threads thì không cần giới hạn số request.”** Sai; downstream vẫn có năng lực hữu hạn.
10. **“Timeout chung 30 giây là đủ cho mọi route.”** Streaming, job, query và giao dịch có yêu cầu khác nhau.
11. **“Giảm 5xx bằng cách luôn trả dữ liệu mặc định là cải thiện SLO.”** Có thể chỉ che giấu lỗi và tạo dữ liệu sai.
12. **“Khi client hủy, các downstream tự động hủy theo.”** Cần hỗ trợ và truyền cancellation thực tế.

## 29. Kết luận

**Timeout** đặt giới hạn cho sự chờ đợi; **deadline** kết nối ngân sách thời gian giữa các tầng; **bulkhead, admission control và circuit breaker** hạn chế mức độ lan truyền của lỗi; **retry có kiểm soát** chỉ giúp khi thao tác an toàn và còn đủ thời gian; **graceful degradation** giữ trải nghiệm hữu ích khi những thành phần không bắt buộc gặp sự cố.

Ở lớp biên, thiết kế tốt không chỉ là chọn giá trị `timeout=3000`. Nó là một cam kết rõ giữa client, gateway/BFF và service: đâu là dữ liệu bắt buộc, đâu có thể thiếu, khi nào được dùng cache, lỗi nào được retry, thao tác nào cần trạng thái UNKNOWN, và bằng chứng nào chứng minh hệ thống đã xử lý đúng.

Mục tiêu cuối cùng là **phản hồi đúng trong thời gian hữu ích và chịu lỗi có giới hạn**, chứ không phải tối đa số lượng response 200 hoặc che giấu mọi dấu hiệu downstream gặp sự cố.
