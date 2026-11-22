# Xử lý nguồn dữ liệu không khả dụng và kết quả thiếu một phần

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Truy vấn liên dịch vụ  
> **Trọng tâm:** Thiết kế truy vấn tổng hợp từ nhiều dịch vụ khi một hoặc vài nguồn dữ liệu lỗi, chậm hoặc chỉ trả một phần kết quả; bảo đảm thông tin hiển thị không gây hiểu nhầm, không vi phạm bất biến nghiệp vụ và có thể được theo dõi, phục hồi, đối soát.

## 1. Bối cảnh: truy vấn một màn hình, phụ thuộc nhiều hệ thống

Một trang chi tiết sản phẩm có thể cần bốn nguồn:

- **Catalog:** tên, mô tả, hình ảnh và trạng thái xuất bản.
- **Pricing:** giá, tiền tệ, ưu đãi hợp lệ.
- **Inventory:** số lượng/tình trạng khả dụng.
- **Recommendations:** sản phẩm liên quan.

Một bảng điều hành có thể cần số liệu từ Orders, Payments, Fulfillment và Analytics. Một trang thông tin tài khoản có thể cần số dư, giao dịch gần nhất, hạn mức và thông báo.

Trong hệ thống phân tán, từng nguồn có vòng đời triển khai, database, quota và khả năng chịu lỗi riêng. Khi một nguồn lỗi, việc **cho toàn bộ truy vấn thất bại** đôi khi quá nghiêm khắc; nhưng **tự tạo một kết quả trông như đầy đủ** có thể nguy hiểm hơn nhiều.

Ví dụ:

- Recommendations lỗi: vẫn có thể hiển thị sản phẩm và ẩn khối gợi ý.
- Pricing lỗi: có thể hiển thị mô tả nhưng không nên tự cho phép mua bằng giá cũ chưa được xác nhận.
- Inventory lỗi: không được mặc định “còn hàng”.
- Payments lỗi trên dashboard: không được báo tổng doanh thu bằng cách ngầm coi mọi khoản thanh toán chưa đọc được là bằng 0.
- Account Balance lỗi: không được dùng số dư hôm trước như số dư hiện tại để cho phép chuyển tiền.

Mấu chốt của chủ đề này là **kết quả thiếu một phần có ngữ nghĩa**: hệ thống phải chỉ ra phần nào đã biết, phần nào chưa biết, dữ liệu còn mới đến đâu và hành động nào còn được phép.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt nguồn không khả dụng, dữ liệu không tồn tại, phản hồi rỗng và dữ liệu cũ.
2. Xác định dữ liệu bắt buộc, dữ liệu tùy chọn và dữ liệu có thể thay thế theo ngữ cảnh nghiệp vụ.
3. Thiết kế response thể hiện trạng thái từng thành phần, độ tin cậy và nguồn gốc dữ liệu.
4. Đặt deadline, timeout, retry budget, circuit breaker, bulkhead và fallback đúng chỗ.
5. Chọn giữa fail-fast, graceful degradation, stale cache và asynchronous materialized read model.
6. Xử lý fan-out, join, pagination, partial totals và consistency khi nhiều nguồn dữ liệu độc lập.
7. Thiết kế giao diện không nhầm “không có” với “không tải được”.
8. Kiểm thử sự cố, đặt SLO cho kết quả đầy đủ và kết quả có thể dùng được.

## 2. Phân biệt các trạng thái dữ liệu trước khi quyết định fallback

Một sai lầm phổ biến là gom mọi trường hợp vào null, false, 0 hoặc danh sách rỗng. Những biểu diễn này mang ý nghĩa khác nhau.

| Trạng thái | Diễn giải | Ví dụ | Cách xử lý |
| --- | --- | --- | --- |
| AVAILABLE | Đã truy vấn được dữ liệu đủ điều kiện | Giá hiện tại đã được Pricing xác nhận | Hiển thị/sử dụng theo contract |
| EMPTY | Truy vấn thành công, không có bản ghi | Không có sản phẩm gợi ý | Hiển thị trạng thái trống hợp lệ |
| NOT_FOUND | Thực thể được yêu cầu không tồn tại hoặc không được phép tiết lộ | Product ID không tồn tại | 404 hoặc chính sách tương ứng |
| UNAVAILABLE | Không thể truy cập nguồn | Service timeout, 503, network partition | Không giả định dữ liệu, chọn fallback có điều kiện |
| PARTIAL | Một số phần có kết quả, một số phần không | Có mô tả và ảnh, thiếu giá | Hiển thị rõ phần thiếu; khóa thao tác rủi ro |
| STALE | Có dữ liệu cũ nhưng chưa xác nhận lại | Tồn kho snapshot cách đây 5 phút | Ghi độ cũ, chỉ dùng nếu nghiệp vụ cho phép |
| INVALID | Dữ liệu trả về không qua được validation | Giá âm hoặc sai đơn vị tiền tệ | Coi là lỗi dữ liệu, không công bố như hợp lệ |
| CONFLICTING | Nhiều nguồn trả dữ liệu mâu thuẫn | Đơn đã hủy nhưng fulfillment báo đang giao | Cần chính sách source-of-truth/đối soát |
| UNKNOWN | Không có bằng chứng đủ để kết luận | Mất trạng thái thanh toán trong lúc timeout | Đặt trạng thái chưa xác định, không suy đoán |

Một yêu cầu trả HTTP 200 với danh sách rỗng không giống request timeout. Một giá trị 0 từ hệ thống có thẩm quyền không giống null do hệ thống đọc dữ liệu bị lỗi. Sự khác biệt phải tồn tại từ tầng adapter tới response và UI.

### 2.1. Ví dụ sai: biến lỗi thành giá trị hợp lệ

~~~java
// Anti-pattern: lỗi Inventory bị che thành "còn 0 hàng".
int stock;
try {
    stock = inventory.getAvailableQuantity(productId);
} catch (Exception e) {
    stock = 0;
}
~~~

Đoạn mã này đánh đồng ba tình huống: thật sự hết hàng, không có sản phẩm và không thể truy vấn kho. Điều đó có thể tạo kết luận sai, làm hỏng báo cáo hoặc khiến đội vận hành không nhận biết sự cố.

### 2.2. Cách biểu diễn có ngữ nghĩa

~~~java
sealed interface AvailabilityResult
    permits Available, OutOfStock, UnknownAvailability {}

record Available(int quantity, Instant checkedAt)
    implements AvailabilityResult {}

record OutOfStock(Instant checkedAt)
    implements AvailabilityResult {}

record UnknownAvailability(
    String reasonCode, Instant lastKnownAt)
    implements AvailabilityResult {}
~~~

Ví dụ dùng Java sealed types để trình bày trạng thái rõ hơn. Trong sản phẩm thật, data model cần phù hợp phiên bản Java, schema API và quy tắc miền. Một nguồn trả trạng thái UNKNOWN không được âm thầm chuyển thành AVAILABLE.

## 3. Đầu tiên phải hiểu “đầy đủ” nghĩa là gì đối với use case

Kết quả đầy đủ không đồng nghĩa “tất cả service đều trả thành công”. Một số service cung cấp dữ liệu tùy chọn, nên ứng dụng vẫn có thể hoàn thành use case dù chúng lỗi.

Xét trang sản phẩm:

| Thành phần | Mức quan trọng | Khi lỗi | Có thể hoàn tất trang? |
| --- | --- | --- | --- |
| Catalog product identity | Bắt buộc | Không biết sản phẩm nào | Thường không |
| Catalog images | Quan trọng nhưng có thể thay thế | Dùng ảnh placeholder nếu chính sách cho phép | Có thể |
| Pricing quote | Bắt buộc để cam kết giá mua | Ẩn/khóa CTA mua, báo không xác nhận được giá | Có thể xem, không thể đặt mua |
| Inventory availability | Bắt buộc để quyết định đặt/giữ hàng theo một số mô hình | Hiển thị UNKNOWN, khóa hoặc chuyển sang “kiểm tra lại” | Có thể xem, thao tác tùy quy tắc |
| Recommendations | Tùy chọn | Ẩn khối gợi ý | Có |
| Ratings/reviews | Tùy chọn | Ẩn hoặc báo tạm không tải được | Có |

Một dữ liệu có thể **không bắt buộc cho read view** nhưng **bắt buộc cho write command**. Giá hiển thị cũ có thể được dùng để minh họa nếu được gắn nhãn rõ; còn lúc tạo đơn, Pricing hoặc application service sở hữu checkout phải xác nhận điều kiện nghiệp vụ theo quy tắc chặt chẽ hơn.

### 3.1. Phân loại dữ liệu bằng chính sách nghiệp vụ

Có thể dùng ba lớp:

1. **Critical / required:** không thể thực hiện hành vi cốt lõi khi thiếu; phải fail closed hoặc chuyển trạng thái đang chờ.
2. **Degradable:** vẫn đáp ứng một phần giá trị với fallback cụ thể; phải bộc lộ sự suy giảm.
3. **Optional:** thiếu cũng không ảnh hưởng cốt lõi; có thể ẩn phần hiển thị, nhưng vẫn đo và báo lỗi vận hành.

Phân loại không cố định theo tên microservice. Một recommendation thông thường là optional nhưng có thể là critical trong một bài toán điều trị hoặc quyết định tín dụng nếu nó thực chất là một kiểm tra bắt buộc. Luôn hỏi domain owner.

### 3.2. Dependency matrix theo hành trình

Một hệ thống có thể có:

- Product Detail — Catalog critical, Pricing important, Inventory important, Recommendation optional.
- Checkout Preview — Pricing và Cart critical, Inventory cần theo chính sách; Recommendation optional.
- Submit Order — Ordering/application workflow critical; không chạy thay bằng kết quả cache tùy ý.
- Sales Dashboard — Orders critical cho số đơn; Payments critical cho số tiền đã thu; Analytics có thể optional nếu được ghi nhãn.
- Customer Support Screen — Order status critical, audit history quan trọng, chat suggestion optional.

Viết matrix này trước khi thêm retry/circuit breaker. Không thể chọn fallback có trách nhiệm nếu chưa biết một trường dữ liệu được dùng để đưa ra quyết định gì.

## 4. Truy vấn liên dịch vụ có nhiều hình thức

### 4.1. Synchronous fan-out / API composition

~~~text
                   +--> Catalog -----------+
                   |                       |
User --> BFF ------+--> Pricing -----------+--> Compose view
                   |                       |
                   +--> Inventory ---------+
                   |                       |
                   +--> Recommendations ---+
~~~

BFF/API aggregator gọi nhiều service, tổng hợp kết quả tại thời điểm request. Mô hình này đơn giản với số nguồn nhỏ nhưng bị chi phối bởi **tail latency**, khả năng lỗi từng nguồn và số lượng request downstream.

### 4.2. Sequential dependency chain

~~~text
User --> BFF --> Orders --> Payments --> Ledger
~~~

Nếu downstream chỉ có thể được gọi sau khi biết kết quả upstream, các timeout cộng dồn và lỗi có thể lan rộng. Cần đánh giá liệu logic đang thuộc một application service chuyên trách hơn, hay có thể tái cấu trúc truy vấn thành các bước song song độc lập.

### 4.3. Asynchronous projection / materialized read model

~~~text
Orders ---- OrderChanged -----+
                              |
Payments -- PaymentChanged ---+--> Projection builder --> Read DB
                              |
Shipping -- ShipmentChanged --+
                                                     |
User --> Query API --------------------------------> Read DB
~~~

Nếu một màn hình thường xuyên tổng hợp nhiều nguồn và cần latency ổn định, có thể xây **read model riêng cho truy vấn** từ event/CDC/contract được định nghĩa. Khi đó query không cần gọi mọi service mỗi lần, đổi lại phải giải quyết eventual consistency, freshness, replay và lỗi projection.

### 4.4. Federated query / query gateway

Một lớp truy vấn có thể phân rã câu hỏi thành các yêu cầu đến nhiều nguồn rồi join/aggregate. Linh hoạt nhưng dễ tạo N+1, truy vấn nặng, thiếu kiểm soát dung lượng và kết quả không có cùng snapshot. Truy vấn liên miền ở runtime không đồng nghĩa được phép truy cập trực tiếp database riêng của service khác.

### 4.5. Batch hoặc background report

Nếu báo cáo cần dữ liệu lớn hoặc nguồn chậm, có thể tạo **report job bất đồng bộ**, trả mã theo dõi, ghi trạng thái từng nguồn, kết quả cuối và danh sách phần chưa hoàn thành. Đây thường là lựa chọn tốt hơn giữ một HTTP request mở nhiều phút.

## 5. Các chính sách phản hồi khi một nguồn lỗi

### 5.1. Fail-fast

Nếu một nguồn bắt buộc thất bại, trả lỗi ngay và không tạo response nửa vời trông như hợp lệ.

Ví dụ: truy vấn để ra quyết định cho phép chuyển tiền cần xác minh số dư và quyền tài khoản. Nếu không thể xác nhận dữ liệu bắt buộc, hệ thống phải từ chối hoặc chuyển trạng thái chờ kiểm tra, thay vì dùng giá trị phỏng đoán.

**Ưu điểm:** rõ ràng, bảo vệ tính đúng đắn và dễ diễn giải.  
**Hạn chế:** toàn bộ use case có thể không khả dụng dù một số phần dữ liệu vẫn đọc được.

### 5.2. Partial success / graceful degradation

Trả về những phần đã được xác nhận, đánh dấu các phần không có dữ liệu do lỗi, và điều chỉnh khả năng tương tác.

Ví dụ:

~~~json
{
  "product": {
    "id": "p-101",
    "title": "Máy ảnh"
  },
  "purchase": {
    "status": "UNAVAILABLE",
    "price": null,
    "availability": "UNKNOWN",
    "canCheckout": false
  },
  "recommendations": {
    "status": "UNAVAILABLE",
    "items": []
  },
  "meta": {
    "completeness": "PARTIAL",
    "unavailableSources": ["pricing", "recommendations"]
  }
}
~~~

Danh sách items rỗng ở đây không có nghĩa “thật sự không có gợi ý”: chính trường status chỉ ra rằng phần dữ liệu này **không tải được**.

### 5.3. Stale-but-usable

Dùng dữ liệu đã cache trước đó khi nguồn mới không sẵn sàng, nhưng chỉ khi:

- Loại dữ liệu cho phép stale.
- Độ cũ nằm trong giới hạn đã thống nhất.
- Người dùng biết đây không phải dữ liệu mới nhất nếu việc đó ảnh hưởng quyết định.
- Hành động ghi sẽ được kiểm tra lại bằng nguồn có thẩm quyền.
- Trạng thái nguồn và tuổi dữ liệu có thể được quan sát.

Ví dụ banner, hình ảnh, mô tả công khai có thể chấp nhận dữ liệu cũ lâu hơn giá, tồn kho, quyền truy cập hoặc số dư.

### 5.4. Default value có căn cứ

Một giá trị mặc định chỉ an toàn khi **nó có ý nghĩa nghiệp vụ thực sự**. Ví dụ thiếu một khối “câu chuyện thương hiệu” tùy chọn thì có thể ẩn khối. Không nên tự gán giá bằng 0, trạng thái thanh toán là success hoặc số hàng tồn là 0 chỉ để tránh null.

### 5.5. Deferred result / pending

Với nguồn cần xác nhận nhưng không thể phản hồi ngay, có thể trả operation ID, trạng thái PENDING và khả năng kiểm tra sau. Điều này cần có workflow owner, state machine, thời hạn và xử lý lỗi rõ. PENDING khác SUCCEEDED.

### 5.6. Refuse to serve / maintenance mode

Nếu dữ liệu thiếu liên quan đến quyết định quan trọng, tài chính, pháp lý hoặc quyền truy cập, không có fallback an toàn. Hệ thống có thể trả 503, thông điệp bảo trì hoặc “vui lòng thử lại” phù hợp; đây là một thiết kế có trách nhiệm, không phải thất bại về UX.

## 6. Không nhầm HTTP success với business completeness

HTTP status diễn tả kết quả giao thức; độ đầy đủ nghiệp vụ cần được diễn đạt trong contract.

Các phương án thường gặp:

| Tình huống | Hướng xử lý HTTP | Payload |
| --- | --- | --- |
| Tất cả phần thiết yếu đầy đủ | 200 | Dữ liệu + trạng thái COMPLETE |
| Thiếu phần optional, core dùng được | Thường 200 theo contract | Dữ liệu + PARTIAL, unavailable sections |
| Nguồn critical không sẵn sàng | 503 hoặc mã thích hợp | Error code + retry guidance |
| Đầu vào yêu cầu không hợp lệ | 400/422 tùy quy ước | Validation error |
| Resource thực sự không tồn tại | 404 tùy chính sách | Not found có ngữ nghĩa rõ |
| Kết quả sẽ có sau | 202 nếu đã chấp nhận operation/job | Operation ID + status URL |
| Auth hoặc quyền không đủ | 401/403 tùy trường hợp | Không rò resource ngoài quyền |
| Nguồn trả dữ liệu không qua được schema | 502/500 hoặc mã được chuẩn hóa | Tránh trình bày dữ liệu không hợp lệ |

**Không mặc định HTTP 206 Partial Content** cho thiếu phần dữ liệu nghiệp vụ. 206 có ngữ nghĩa gắn với range request. HTTP 207 Multi-Status xuất phát từ bối cảnh WebDAV, chỉ nên dùng nếu contract và client thực sự hỗ trợ mô hình đó. Với API tổng hợp thông thường, 200 + biểu diễn completeness có thể rõ hơn, miễn phần bắt buộc còn đúng.

Cũng không nên đặt một status 200 cố định cho mọi lỗi rồi để frontend tự đoán từ trường error; điều này che lỗi và làm monitoring HTTP kém tin cậy.

### 6.1. Ví dụ response có trạng thái từng thành phần

~~~json
{
  "data": {
    "order": {
      "id": "o-742",
      "status": "SHIPPED"
    },
    "payment": null,
    "shipment": {
      "carrier": "Carrier A",
      "status": "IN_TRANSIT"
    }
  },
  "sections": {
    "order": {
      "status": "AVAILABLE",
      "asOf": "2026-11-11T08:35:20Z"
    },
    "payment": {
      "status": "UNAVAILABLE",
      "reasonCode": "PAYMENTS_TIMEOUT",
      "retryable": true
    },
    "shipment": {
      "status": "AVAILABLE",
      "asOf": "2026-11-11T08:34:58Z"
    }
  },
  "meta": {
    "completeness": "PARTIAL",
    "requestId": "req-c8e2"
  }
}
~~~

Thời gian trong ví dụ chỉ minh họa shape. Một timestamp asOf có thể thể hiện thời điểm dữ liệu nguồn được xác nhận, thời điểm projection ghi hoặc thời điểm tổng hợp; phải định nghĩa rõ trong API.

### 6.2. Một schema khó dùng

~~~json
{
  "orderId": "o-742",
  "paymentAmount": 0,
  "paymentStatus": null,
  "shipmentStatus": "",
  "errors": ["some service failed"]
}
~~~

Không biết số tiền 0 là thật hay fallback, chuỗi rỗng có nghĩa gì, dịch vụ nào lỗi, liệu có thể làm tiếp hay không. Nếu consumer tự đoán, các ứng dụng có thể đưa ra quyết định khác nhau với cùng kết quả.

## 7. Thiết kế mô hình kết quả cho từng nguồn

Một kiểu dữ liệu có cấu trúc giúp không che lỗi:

~~~text
SourceResult<T> =
  Available(value, asOf, sourceVersion)
  | Empty(asOf)
  | NotFound
  | Stale(value, asOf, maxAllowedAge)
  | Unavailable(errorCode, retryable, observedAt)
  | Invalid(reasonCode)
~~~

Đây là mô hình logic; không nhất thiết serialize toàn bộ fields ra public API. Tầng application có thể phân loại, sau đó BFF tạo view model phù hợp từng trải nghiệm.

### 7.1. SourceResult khác Result của toàn bộ request

Ví dụ:

- Catalog: Available.
- Pricing: Unavailable.
- Inventory: Available.
- Recommendations: Empty.

Response cuối có thể là Partial với **trang hiển thị được nhưng không cho checkout**. Không nên chọn tổng trạng thái dựa trên số lượng nguồn thành công 3/4; quan trọng là **mức thiết yếu và tác động của nguồn lỗi**.

### 7.2. Một ma trận tổng hợp

| Catalog | Pricing | Inventory | Recommendation | Diễn giải |
| --- | --- | --- | --- | --- |
| Available | Available | Available | Available | Trang đầy đủ |
| Available | Available | Available | Unavailable | Trang dùng được, ẩn gợi ý |
| Available | Unavailable | Available | Available | Cho xem sản phẩm, không cam kết giá |
| Available | Available | Unavailable | Available | Cho xem sản phẩm, trạng thái kho chưa biết |
| Unavailable | Available | Available | Available | Không đủ dữ liệu gốc để tạo trang |
| NotFound | Bất kỳ | Bất kỳ | Bất kỳ | Sản phẩm thực sự không tồn tại theo nguồn có thẩm quyền |
| Stale | Available | Available | Available | Chỉ dùng dữ liệu Catalog stale nếu policy cho phép |

Cần phân biệt **Catalog NotFound xác thực** với Catalog Unavailable. Không trả 404 vì Catalog timeout: một lần không tra được dữ liệu không chứng minh thực thể vắng mặt.

## 8. Ngân sách thời gian: tránh để nguồn chậm giữ cả màn hình

### 8.1. End-to-end deadline

Giả sử mục tiêu phản hồi của BFF là khoảng 800 ms. BFF cần dự trù thời gian cho gateway/network, xử lý tại BFF, downstream calls và serialization.

~~~text
Client -> Gateway/BFF: 100 ms
Auth + parsing:         70 ms
Downstream fan-out:    450 ms
Composition:            80 ms
Dự phòng:              100 ms
Tổng dự trù:           800 ms
~~~

Các giá trị chỉ là giả định để minh họa, không phải SLO chuẩn áp dụng cho mọi hệ thống.

Nếu Recommendations chưa trả sau deadline của phần optional, BFF có thể bỏ qua nó và trả kết quả cốt lõi. Nếu Pricing là critical, BFF có thể trả lỗi hoặc trạng thái không mua được. Dù thế nào, **không chờ vô hạn**.

### 8.2. Propagate deadline, không cộng timeout tùy ý

Nếu gateway chỉ còn 600 ms trước deadline mà BFF gọi ba dịch vụ tuần tự với timeout 1.000 ms mỗi lần, tổng thời gian có thể vượt xa kỳ vọng. Cần truyền hoặc suy ra remaining budget đến từng call.

~~~text
requestDeadline = thời điểm tuyệt đối hoặc budget còn lại

BFF:
  timeRemaining = deadline - now
  catalogTimeout = min(policyCatalog, timeRemaining)
  pricingTimeout = min(policyPricing, timeRemaining)
  recommendationsTimeout = min(policyOptional, timeRemaining)
~~~

Cần hiểu timeout ở connect, TLS handshake, read, per-attempt và tổng request; một timeout không phải lúc nào cũng bao trùm mọi giai đoạn.

### 8.3. Parallel calls cho nguồn độc lập

Nếu Catalog, Pricing và Inventory không phụ thuộc dữ liệu của nhau, chạy song song có thể giảm latency. Nhưng song song hóa nhiều call cũng có thể tăng tải đỉnh, connection usage và tail risk.

~~~text
                  +--> Catalog (180 ms) --------+
                  |                             |
Query -> BFF -----+--> Pricing (270 ms) --------+--> Compose
                  |                             |
                  +--> Inventory (220 ms) ------+
                  |                             |
                  +--> Recommendations (timeout)-+  optional
~~~

Khi deadline tới, BFF cần tổng hợp kết quả đã hoàn tất và trạng thái failure/timeout của những phần chưa xong. Đừng nhầm cancellation của future tại BFF với việc downstream request chắc chắn đã dừng.

## 9. Retry: chỉ thử lại khi có cơ hội thành công

Retry có thể giúp vượt network hiccup nhưng cũng gây thêm tải.

### 9.1. Khi nào retry có ý nghĩa?

- Lỗi tạm thời mà upstream thường phục hồi nhanh.
- Request đọc/idempotent, hoặc thao tác có side effect đã được bảo vệ chống trùng.
- Vẫn còn đủ thời gian trong deadline.
- Chưa vượt retry budget.
- Không có tín hiệu downstream đang quá tải nặng cần load shedding.

### 9.2. Khi nào không nên retry?

- Input sai/không hợp lệ.
- 403 và những từ chối quyền chắc chắn.
- Resource xác thực không tồn tại.
- Deadline đã hết.
- Một phần upstream đang sập trên diện rộng, retry chỉ làm nghẽn thêm.
- Lệnh không idempotent mà không có cơ chế chống trùng.

### 9.3. Retry amplification

Một request client được retry hai lần; gateway retry hai lần; BFF retry ba lần cho mỗi trong bốn downstream calls. Số attempt có thể nhân lên rất lớn dù không ai cố tình tạo tải xấu. Mô hình cần **retry budget end-to-end** và chọn lớp thực hiện retry có chủ đích.

### 9.4. Backoff và jitter

Với một số thao tác không quá nhạy độ trễ, exponential backoff và jitter giúp tránh các client retry đồng loạt. Với request UI có ngân sách 500 ms, một retry delay dài có thể không hữu ích; trả partial/error có thể an toàn hơn.

**Nguyên tắc:** không dùng retry để biến một dịch vụ hỏng lâu dài thành hàng nghìn truy vấn vô ích.

## 10. Circuit breaker và bulkhead

### 10.1. Circuit breaker

Circuit breaker có thể ngừng gọi tạm thời đến nguồn đang lỗi liên tiếp, giảm số request vô vọng và bảo vệ latency của BFF.

Trạng thái logic:

~~~text
CLOSED
  | nhiều lỗi vượt ngưỡng
  v
OPEN -- sau khoảng hồi phục --> HALF_OPEN
  ^                              |
  | thất bại                    | thử giới hạn call
  +------------------------------+
                                  |
                                  +-- thành công --> CLOSED
~~~

Trong trạng thái OPEN, adapter có thể trả Unavailable nhanh. Nhưng không đồng nhất “circuit open” với “không có dữ liệu”. Circuit breaker cũng có thể gây chập chờn nếu ngưỡng quá nhạy hoặc mọi client cùng mở/đóng theo nhịp giống nhau.

### 10.2. Bulkhead

Bulkhead tách giới hạn tài nguyên theo dependency. Nếu Reporting bị chậm, nó không nên chiếm hết thread/connection của các request Billing quan trọng. Có thể giới hạn concurrency, connection pool, queue capacity và execution isolation theo nhóm downstream.

~~~text
BFF worker capacity
   |
   +-- Pricing calls: max N concurrent
   +-- Inventory calls: max M concurrent
   +-- Recommendation calls: max K concurrent
~~~

Các N/M/K phải đo trên workload thật. Quá thấp gây lỗi giả khi tải tăng; quá cao làm downstream quá tải. Bulkhead không tự thay thế backpressure hoặc capacity planning.

### 10.3. Fallback sau khi breaker mở

Chính sách fallback phải giống khi nguồn Unavailable bình thường: optional section ẩn; read-only data có cache hợp lệ có thể dùng stale; dữ liệu critical thì từ chối/đặt UNKNOWN. Không để breaker trả default value hợp lệ giả.

## 11. Cache và dữ liệu cũ: dùng đúng mức rủi ro

Cache giúp giảm phụ thuộc thời gian thực vào nguồn. Nhưng cache dữ liệu cũ cũng có thể làm sai sự thật nghiệp vụ.

### 11.1. Các lựa chọn

| Chiến lược | Ý tưởng | Lưu ý |
| --- | --- | --- |
| Cache-aside | Query cache, miss mới gọi nguồn rồi ghi cache | Stampede, TTL, invalidation |
| Stale-while-revalidate | Trả dữ liệu cũ trong cửa sổ hợp lệ, làm mới sau | Cần giới hạn stale và thông báo phù hợp |
| Stale-if-error | Chỉ dùng bản cũ nếu nguồn lỗi | Phải ghi độ cũ và hợp đồng |
| Precomputed read model | Dựng kết quả từ event/CDC vào store truy vấn | Eventual consistency, lag, replay |
| Last-known-good snapshot | Giữ snapshot đã xác thực | Phù hợp một số dữ liệu ít biến động; không phải mọi miền |
| No cache | Luôn hỏi nguồn có thẩm quyền | Phù hợp dữ liệu cần mạnh, nhưng phải chịu lỗi rõ |

### 11.2. Data freshness budget

Ví dụ **minh họa**:

- Ảnh và nội dung marketing: có thể stale lâu nếu phiên bản nội dung đã công bố.
- Rating/recommendation: có thể chấp nhận stale vài phút tùy UX.
- Giá khuyến mãi: cần chính sách ngắn hơn và tái xác nhận trước thao tác ghi.
- Tồn kho: biến động nhanh, stale chỉ mang tính tham khảo nếu có hiển thị.
- Số dư khả dụng và quyền giao dịch: không dùng cache UI làm bằng chứng cho lệnh tiền tệ.
- Quyền truy cập: cache phải phù hợp chính sách revoke; không tự duy trì quyền đã bị thu hồi.

Đừng chọn TTL chỉ theo khả năng kỹ thuật. TTL phải gắn với **mức độ sai số hoặc độ cũ được nghiệp vụ chấp nhận**.

### 11.3. Timestamps và nguồn gốc

Một response stale nên có các dữ kiện:

~~~json
{
  "value": {
    "estimatedStock": 12
  },
  "status": "STALE",
  "source": "inventory-projection",
  "dataAsOf": "2026-11-11T08:00:00Z",
  "servedAt": "2026-11-11T08:05:00Z",
  "ageSeconds": 300,
  "isAuthoritativeForCheckout": false
}
~~~

Timestamp cần có ý nghĩa rõ: thời điểm event xảy ra, projection cập nhật hay hệ thống thực sự đọc. Nếu service upstream đưa timestamp từ đồng hồ không đồng bộ, không nên dùng để kết luận precision tuyệt đối.

### 11.4. Cache stampede

Khi cache hết hạn cho một key phổ biến và nguồn đang lỗi, hàng nghìn request có thể cùng gọi upstream. Có thể dùng request coalescing/single flight, jitter TTL, giới hạn refresh concurrency và fallback stale có kiểm soát. Không để cơ chế cache làm sự cố downstream nặng hơn.

### 11.5. Negative caching

NotFound từ nguồn có thẩm quyền có thể được cache ngắn trong một số trường hợp. Nhưng lỗi timeout/503 không nên bị lưu như “resource không tồn tại”. Cần phân biệt cache entry valid-empty/valid-not-found với cache error.

## 12. Join dữ liệu liên dịch vụ khi một phía thiếu

Truy vấn tổng hợp thường join dữ liệu qua ID, ví dụ Order + Payment + Shipment. Những lựa chọn join có ý nghĩa nghiệp vụ khác nhau.

### 12.1. Inner join là lựa chọn nguy hiểm nếu nguồn lỗi

Giả sử có 100 đơn hàng; Payments tạm không phản hồi cho 30 đơn. Nếu aggregator chỉ giữ các đơn có đủ Payment, UI có thể hiển thị 70 đơn và báo “Tổng đơn: 70”. Người dùng có thể tin 30 đơn đã biến mất. Đây là **mất dữ liệu do thiết kế truy vấn**, không phải thật sự chỉ có 70 đơn.

### 12.2. Left join với trạng thái nguồn

Có thể lấy Orders làm tập gốc có thẩm quyền, rồi đính thêm Payment và Shipment khi truy vấn được:

~~~text
Order o-1: payment AVAILABLE, shipment AVAILABLE
Order o-2: payment UNAVAILABLE, shipment AVAILABLE
Order o-3: payment AVAILABLE, shipment EMPTY
~~~

Nhưng “Payment EMPTY” chỉ được dùng nếu Payments xác nhận thật sự không có bản ghi theo contract. Nếu nó timeout, phải là UNKNOWN/UNAVAILABLE.

### 12.3. Tập kết quả gốc có thể cũng thiếu

Nếu chính Orders query trả không đủ dữ liệu do timeout/phân trang/chỉ trả được một shard, một left join không cứu được. Response phải cho biết **base set incomplete** và không nên công bố tổng số đơn như một thống kê đầy đủ.

### 12.4. Khóa và tính đúng của join

- Dùng ID nghiệp vụ có contract ổn định, không dựa vào tên hiển thị.
- Phân biệt ID xuyên tenant để không join nhầm dữ liệu của hai khách hàng khác nhau.
- Hiểu quan hệ one-to-many để tránh nhân dòng làm tổng tiền tăng.
- Kiểm tra currency và đơn vị đo trước khi aggregate.
- Dùng version/effective time nếu các nguồn phản ánh thời điểm khác nhau.
- Không xóa mặc định bản ghi thiếu quan hệ mà chưa xác minh đó là kết quả hợp lệ.

## 13. Tổng hợp số liệu khi kết quả thiếu một phần

Đây là vấn đề đặc biệt nghiêm trọng với dashboard và báo cáo.

### 13.1. Không âm thầm coi nguồn lỗi là số 0

Giả sử một dashboard phải tính doanh thu từ ba vùng:

| Vùng | Kết quả | Giá trị |
| --- | --- | ---: |
| Region A | AVAILABLE | 400 triệu |
| Region B | AVAILABLE | 300 triệu |
| Region C | UNAVAILABLE | Chưa biết |

Nếu hiển thị “Doanh thu toàn hệ thống: 700 triệu” mà không ghi chú, người dùng dễ hiểu đây là tổng đầy đủ. Cách biểu diễn đúng hơn:

~~~json
{
  "metric": "recognizedRevenue",
  "value": 700000000,
  "currency": "VND",
  "scope": "KNOWN_REGIONS_ONLY",
  "completeness": "PARTIAL",
  "regionsIncluded": ["A", "B"],
  "regionsUnavailable": ["C"],
  "displayAsFinalTotal": false
}
~~~

Con số 700 triệu là **tổng tạm của các vùng đã biết**, không phải tổng toàn hệ thống. Nếu thiếu vùng quan trọng, có thể không hiển thị con số tổng nào và thay bằng trạng thái unavailable.

### 13.2. Partial count và pagination

Nếu một truy vấn trả 50 bản ghi từ hai shard, shard thứ ba lỗi:

- Trường totalCount từ hai shard không phải totalCount toàn hệ thống.
- Next page cursor có thể thiếu phần dữ liệu và không còn tương thích khi shard phục hồi.
- Sort toàn cục có thể không chính xác nếu thiếu shard chứa bản ghi mới nhất.
- Client có thể bỏ lỡ bản ghi nếu chỉ tiếp tục theo cursor của kết quả không đầy đủ.

Cần công bố completeness của trang và contract về cursor; có thể chọn trả lỗi thay vì partial pagination cho những màn hình đòi đầy đủ và thứ tự chính xác.

### 13.3. Ước lượng khác số liệu thực

Trong hệ phân tích, có thể hiển thị estimate với confidence interval theo mô hình đã phê duyệt. Nhưng không được biến missing data thành ước lượng tùy tiện. Nếu có ước lượng, phải phân biệt estimate, observed total, phương pháp tính và phạm vi tin cậy.

### 13.4. Ảnh hưởng tới quyết định tự động

Một dashboard người dùng đọc có thể cho phép hiển thị partial. Một hệ tự động ra quyết định tín dụng, tính thuế hoặc thanh toán có thể không được phép dùng partial. Chính sách cần ràng buộc theo consumer; không chỉ theo producer.

## 14. Tính nhất quán: các nguồn cùng đúng nhưng khác thời điểm

Ngay cả khi mọi service hoạt động, một truy vấn liên dịch vụ vẫn có thể lấy dữ liệu **không cùng một snapshot**.

Ví dụ:

1. Orders trả đơn “PAID” ở 10:00:01.
2. Payments trả trạng thái “REFUNDED” ở 10:00:03.
3. Shipping trả “DELIVERED” ở 10:00:05.

Ba kết quả có thể đều đúng tại thời điểm riêng nhưng không tạo thành một snapshot giao dịch nhất quán. Nếu BFF tự suy ra “đơn chắc chắn đã thanh toán và chưa hoàn tiền”, kết luận sai.

### 14.1. Các mức yêu cầu về consistency

- **Best-effort view:** nhiều nguồn đọc gần thời điểm hiện tại; cho phép thông tin cập nhật lệch vài giây.
- **Snapshot as-of:** query dữ liệu đã đồng bộ đến một watermark hoặc snapshot version.
- **Read-your-writes:** người dùng vừa cập nhật thì phải thấy kết quả mới nhất theo contract.
- **Strong consistency for critical decision:** quyết định quan trọng được thực hiện tại một domain owner có cơ chế kiểm tra giao dịch phù hợp.
- **Eventual consistency projection:** read model cập nhật sau event, có lag và trạng thái freshness được quản lý.

Không thể đạt strong cross-service snapshot chỉ bằng cách gọi nhiều HTTP API “cùng lúc”. Phải có cơ chế phiên bản, watermark, snapshot hoặc tập trung quyết định ở đúng bounded context.

### 14.2. Watermark và độ trễ projection

Một read model có thể ghi:

~~~json
{
  "projectionVersion": "v4",
  "lastAppliedEventTime": "2026-11-11T08:28:00Z",
  "lastAppliedSequence": 745821,
  "status": "LAGGING"
}
~~~

Đây là dữ liệu minh họa. LastAppliedEventTime chịu ảnh hưởng event-time và đồng hồ nguồn; offset/sequence thường có ý nghĩa trong phạm vi partition/stream. Không dùng một sequence tùy ý để tuyên bố đã đồng bộ toàn bộ các dịch vụ.

### 14.3. Mâu thuẫn dữ liệu không tự biến mất sau retry

Nếu Orders và Payments trả hai trạng thái khác nhau, có thể có event trễ, race, hoặc bug nghiệp vụ. Retry thêm một vài lần đôi khi chỉ đổi trạng thái hiển thị và tăng tải. Cần biết hệ thống nào là source of truth và quy trình đối soát.

## 15. API Gateway, BFF, query aggregator và domain owner

### 15.1. BFF/aggregator có thể tổng hợp, không tự sở hữu sự thật

BFF phục vụ màn hình, chọn dữ liệu cần hiển thị, điều phối read-only calls và map trạng thái unavailable. Nhưng nó không nên:

- Tính lại số dư ngân hàng bằng công thức riêng trái domain contract.
- Xác nhận thanh toán từ trạng thái cache chưa được Payments phê duyệt.
- Ghi trực tiếp database của các microservice để làm shortcut.
- Đưa ra business invariant mà không có một domain service sở hữu.
- Tự giải quyết mọi mâu thuẫn giữa các bounded context mà thiếu hợp đồng.

### 15.2. Gateway không phải nơi giải mọi partial failure

Gateway phù hợp TLS, routing, rate limit và các policy tầng biên. Một số gateway có plugin aggregate, nhưng logic “thiếu giá thì khóa nút mua, thiếu gợi ý thì vẫn cho xem” là tri thức của trải nghiệm/domain. Đặt mọi quy tắc đó trong cấu hình gateway lớn làm khó kiểm thử, quan sát và ownership.

### 15.3. Query service/read model riêng

Khi nhiều consumer cần cùng một mô hình đọc ổn định như OrderOverview, có thể tạo query service có owner và dữ liệu projection riêng, nhận sự kiện từ nguồn. Nó không được trở thành một service “đọc trộm” database của toàn hệ thống. Phải có hợp đồng dữ liệu, schema evolution, event completeness và trách nhiệm xử lý lag.

### 15.4. Khi nào cần workflow thay vì truy vấn tổng hợp?

Nếu người dùng cần tạo ra trạng thái mới qua nhiều service (đặt hàng, hoàn tiền, cấp quyền), việc gọi nhiều nguồn rồi tổng hợp dữ liệu không đủ. Cần application/workflow owner chịu trách nhiệm retry, idempotency, compensation và trạng thái nghiệp vụ. **Query-time graceful degradation** không được dùng để che thất bại của command.

## 16. GraphQL và lỗi một phần

GraphQL thường có khả năng trả **data và errors** trong cùng response cho lỗi field resolution. Điều này thuận lợi nhưng cũng dễ làm client nhầm null với “không có giá trị” nếu schema không thiết kế phù hợp.

Ví dụ:

~~~json
{
  "data": {
    "product": {
      "id": "p-101",
      "title": "Máy ảnh",
      "price": null,
      "reviews": []
    }
  },
  "errors": [
    {
      "message": "Pricing temporarily unavailable",
      "path": ["product", "price"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
~~~

Ở đây price=null vì lỗi resolver, khác với giá không tồn tại một cách hợp lệ. Cần định nghĩa nullability và error codes sao cho client hành xử đúng. Với trường non-null, cơ chế error propagation của GraphQL có thể khiến null lan lên parent; phải cân nhắc thiết kế schema để không làm sập toàn bộ query khi field optional lỗi.

### 16.1. DataLoader và N+1

Một query GraphQL lấy 50 đơn hàng và với mỗi đơn gọi Payments riêng sẽ tạo 50 downstream requests. Khi Payments chậm, fan-out có thể làm cả query timeout. Dùng batching, caching theo request hoặc read model phù hợp. Nhưng DataLoader không giải quyết bài toán partial totals và consistency nếu dữ liệu nền đã thiếu.

### 16.2. Không lấy “HTTP 200” làm thước đo thành công duy nhất

Một GraphQL operation có thể trả HTTP 200 nhưng có errors cho các field thiết yếu. Monitoring phải ghi completion và critical-field error rate, không chỉ HTTP status.

### 16.3. Đừng dùng toàn bộ nullable schema để né lỗi

Để mọi field nullable khiến client phải đoán null là không có, không được phép xem hay lỗi hạ tầng. Có thể thêm typed result/status rõ khi dữ liệu thiếu có ý nghĩa đối với sản phẩm.

## 17. Bảo mật khi truy vấn liên dịch vụ bị thiếu

### 17.1. Permission denied không phải nguồn không khả dụng

Nếu user không đủ quyền đọc Payment, aggregator không nên tự thử một account khác hoặc chuyển sang cache chung. Trạng thái có thể là FORBIDDEN/REDACTED theo contract. Public API có thể chọn không tiết lộ resource có tồn tại hay không, nhưng nội bộ phải phân loại đúng để không retry mù.

### 17.2. Không để cache fallback rò tenant

Nếu một BFF lưu OrderOverview theo orderId mà không phân biệt tenant/owner, khi nguồn trực tiếp lỗi nó có thể trả dữ liệu đã cache của người khác. Cache key và kiểm tra quyền phải áp dụng cả khi không gọi upstream.

### 17.3. Dữ liệu stale có thể chứa quyền cũ

Một quyền truy cập đã bị thu hồi nhưng projection chưa cập nhật là rủi ro. Trường dữ liệu phục vụ authorization phải có contract đủ mạnh; không lấy cached role/ownership quá hạn chỉ vì nguồn IAM không khả dụng.

### 17.4. Phân quyền trên từng thành phần

Một response tổng hợp có thể chứa Catalog công khai, giá theo nhóm khách hàng, tồn kho nội bộ và lịch sử thanh toán nhạy cảm. Cần kiểm soát quyền theo field/section, không chỉ bảo vệ endpoint tổng hợp ở mức rộng.

### 17.5. Tránh lộ chi tiết hạ tầng trong thông báo lỗi

Trong response có thể trả reasonCode ổn định như PRICE_TEMPORARILY_UNAVAILABLE. Log nội bộ giữ upstream name, status, traceId, timeout, attempt. Không đưa internal hostname, token, stack trace hoặc query database cho client.

## 18. Ví dụ xuyên suốt: trang chi tiết đơn hàng

Bối cảnh: người dùng mở trang chi tiết đơn. Hệ thống có ba nguồn:

- Orders: danh tính đơn, trạng thái và các dòng hàng.
- Payments: thông tin khoản thanh toán.
- Shipping: vị trí/tiến độ giao hàng.

### 18.1. Hợp đồng yêu cầu

~~~http
GET /v1/orders/o-742/overview
Authorization: Bearer <token>
Accept: application/json
~~~

Giả sử Orders thành công, Payments timeout, Shipping thành công. Một response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "order": {
    "id": "o-742",
    "status": "CONFIRMED",
    "items": [
      {"sku": "SKU-10", "quantity": 2}
    ]
  },
  "payment": {
    "status": "UNAVAILABLE",
    "details": null,
    "retryable": true
  },
  "shipment": {
    "status": "AVAILABLE",
    "trackingState": "IN_TRANSIT",
    "lastUpdatedAt": "2026-11-11T08:30:00Z"
  },
  "meta": {
    "completeness": "PARTIAL",
    "requestId": "req-519",
    "unavailableSections": ["payment"]
  }
}
~~~

Đây là hợp đồng minh họa cho màn hình **đọc thông tin**. Nó không xác nhận rằng đơn đã thanh toán thành công. Nút “Hoàn tiền” hoặc “Giao hàng” nếu tồn tại phải kiểm tra điều kiện tại domain command owner.

### 18.2. UI khi thiếu Payments

~~~text
Đơn hàng #o-742
Trạng thái đơn: Đã xác nhận
Giao hàng: Đang vận chuyển

Thanh toán:
[Chưa thể tải trạng thái thanh toán]
Vui lòng thử làm mới sau.

[Xem lại thanh toán]    [Liên hệ hỗ trợ]
~~~

Nếu dữ liệu payment thật sự EMPTY, UI có thể hiển thị “Chưa có giao dịch thanh toán” **chỉ khi Payments xác nhận**. Nếu Payments timeout, UI không được tự ghi “Chưa thanh toán”.

### 18.3. Nếu Orders thất bại

Orders là nguồn gốc của việc xác định resource và quyền. BFF có thể trả lỗi 503 hoặc trang lỗi tương ứng, không ghép ngẫu nhiên payment/shipping và tuyên bố tìm thấy đơn. Một số môi trường có read model đủ quyền và dữ liệu được phê duyệt cho failover, nhưng đó phải là **thiết kế riêng**, không phải fallback tự phát.

### 18.4. Nếu Shipping có bản ghi cũ

BFF có thể hiển thị “Cập nhật lúc 15:30” với nhãn “Thông tin có thể chậm” nếu chính sách cho phép. Nhưng nếu đang quyết định “đơn đã được giao để giải ngân tiền”, hệ thống phải sử dụng nguồn và điều kiện có thẩm quyền, không dùng dữ liệu UI stale.

## 19. Ví dụ thứ hai: dashboard tổng doanh thu nhiều vùng

Giả sử Dashboard gọi ba nguồn RegionA, RegionB, RegionC để tính doanh thu.

~~~text
                    +-- RegionA: 400 triệu --+
Dashboard Query ----+-- RegionB: 300 triệu --+--> Aggregator
                    +-- RegionC: timeout ----+
~~~

Nếu yêu cầu là **thông tin tham khảo theo vùng**, có thể trả:

~~~json
{
  "regions": [
    {"id": "A", "status": "AVAILABLE", "revenue": 400000000},
    {"id": "B", "status": "AVAILABLE", "revenue": 300000000},
    {"id": "C", "status": "UNAVAILABLE", "revenue": null}
  ],
  "knownSubtotal": 700000000,
  "overallTotal": null,
  "currency": "VND",
  "completeness": "PARTIAL"
}
~~~

Nếu báo cáo dùng để **khóa sổ tài chính**, có thể phải từ chối xuất báo cáo hoàn chỉnh và giữ job ở trạng thái FAILED/PENDING_RECONCILIATION cho tới khi đủ dữ liệu. Cùng một lỗi nguồn nhưng chính sách phản hồi phụ thuộc mục đích sử dụng.

### 19.1. Không cộng tiền khác currency

Nếu RegionB trả USD còn A trả VND, không thể cộng số trực tiếp. Khi một nguồn tỷ giá không khả dụng, có thể phải trả tổng theo từng currency hoặc báo không đủ dữ liệu. Lỗi không chỉ nằm ở endpoint timeout; **schema/đơn vị** cũng là điều kiện hợp lệ.

### 19.2. Không đánh đồng thiếu vùng với zero sales

Trong dashboard, số 0 có nghĩa “đã đo được và không có doanh thu”. UNAVAILABLE có nghĩa “không biết”. Đây là sự khác biệt sống còn đối với cảnh báo kinh doanh.

## 20. Ví dụ Java: phân loại kết quả nguồn thay vì nuốt exception

### 20.1. Định nghĩa SourceResult

~~~java
public sealed interface SourceResult<T>
    permits SourceResult.Available, SourceResult.Empty,
            SourceResult.Unavailable {

    record Available<T>(T value, Instant asOf)
        implements SourceResult<T> {}

    record Empty<T>(Instant asOf)
        implements SourceResult<T> {}

    record Unavailable<T>(String code, boolean retryable)
        implements SourceResult<T> {}
}
~~~

Dạng trên minh họa ba trạng thái chính. Hệ thống thật có thể cần NotFound, Forbidden, Invalid và Stale; dùng generic/record theo phiên bản Java phù hợp.

### 20.2. Adapter phân loại lỗi

~~~java
public final class PricingAdapter {
    private final PricingHttpClient client;

    public SourceResult<Price> readPrice(String productId) {
        try {
            Price price = client.fetchPrice(productId);
            if (price == null) {
                // Chỉ dùng Empty nếu contract thật sự định nghĩa như vậy.
                return new SourceResult.Empty<>(Instant.now());
            }
            return new SourceResult.Available<>(
                price, price.observedAt());

        } catch (UpstreamTimeoutException ex) {
            return new SourceResult.Unavailable<>(
                "PRICING_TIMEOUT", true);

        } catch (UpstreamServiceException ex) {
            return new SourceResult.Unavailable<>(
                "PRICING_UNAVAILABLE", ex.isRetryable());
        }
    }
}
~~~

Không bắt Exception chung để mọi lỗi đều được coi là timeout; lỗi mapping/schema/authorization phải được phân loại riêng. Adapter cần thực hiện connection timeout, read timeout, authentication và tracing ở tầng infrastructure.

### 20.3. Composer có quy tắc nhất quán

~~~java
public final class ProductPageComposer {
    public ProductPageView compose(
            SourceResult<Product> catalog,
            SourceResult<Price> pricing,
            SourceResult<Availability> inventory,
            SourceResult<List<Product>> recommendations) {

        if (!(catalog instanceof SourceResult.Available<Product> c)) {
            throw new RequiredSourceUnavailableException("catalog");
        }

        boolean hasValidPrice =
            pricing instanceof SourceResult.Available<Price>;
        boolean hasValidStock =
            inventory instanceof SourceResult.Available<Availability>;

        PurchaseView purchase = new PurchaseView(
            hasValidPrice && hasValidStock
                ? PurchaseState.CHECK_REQUIRED
                : PurchaseState.UNAVAILABLE);

        return ProductPageView.of(
            c.value(),
            purchase,
            mapPrice(pricing),
            mapStock(inventory),
            mapRecommendations(recommendations),
            completenessOf(pricing, inventory, recommendations));
    }
}
~~~

**Lưu ý:** các type và method hỗ trợ là pseudo-code, không phải source hoàn chỉnh có thể biên dịch độc lập. Ngay cả khi price và availability trả AVAILABLE, thao tác checkout vẫn cần kiểm tra lại invariant tại domain command owner. Không dùng kết quả đọc BFF như giấy phép mua hàng không cần xác thực.

### 20.4. Dùng CompletableFuture cho các nguồn độc lập

~~~java
var catalogFuture = fetchAsync(() -> catalog.readProduct(id));
var pricingFuture = fetchAsync(() -> pricing.readPrice(id));
var inventoryFuture = fetchAsync(() -> inventory.readStock(id));
var recommendationsFuture =
    fetchAsync(() -> recommendations.readFor(id));

awaitWithinSharedDeadline(
    catalogFuture,
    pricingFuture,
    inventoryFuture,
    recommendationsFuture);

var product = resultOrUnavailable(catalogFuture);
var price = resultOrUnavailable(pricingFuture);
var stock = resultOrUnavailable(inventoryFuture);
var suggestions = resultOrUnavailable(recommendationsFuture);

return composer.compose(product, price, stock, suggestions);
~~~

Đây là pseudo-code mô tả ý tưởng. Một triển khai Java thật cần thread pool phù hợp, deadline propagation, cancellation semantics, xử lý exception, context propagation, giới hạn concurrency và policy khi có nguồn timeout. Không tự tạo thread vô hạn trên mỗi HTTP request.

### 20.5. Request scope context

Mỗi thao tác tổng hợp cần correlation ID, tenant, user identity, deadline và request metadata có kiểm soát. Khi chạy async tasks, đừng để security context và trace context bị mất hoặc dùng nhầm giữa các request do thread reuse. Không truyền raw token vào log.

## 21. Thiết kế theo domain: fail open hay fail closed?

“Fail open” và “fail closed” không phải lựa chọn toàn cục. Chúng phụ thuộc việc hệ thống đang **đọc để hiển thị** hay **quyết định quyền/hành động**.

### 21.1. Hiển thị gợi ý sản phẩm

Khi Recommendations lỗi, fail open cho trang chính: trả sản phẩm đầy đủ và ẩn gợi ý. Không có nguy cơ đáng kể đối với bất biến nghiệp vụ.

### 21.2. Bán sản phẩm với tình trạng kho chưa biết

Khi Inventory lỗi, có thể cho phép người dùng xem thông tin, nhưng không nên cho phép checkout theo giả định “chắc còn hàng”. Có thể đưa vào giỏ với nhãn chưa kiểm tra, tùy business policy; khi đặt đơn, hệ thống phải xác nhận tại owner.

### 21.3. Kiểm soát gian lận

Nếu fraud scoring là điều kiện bắt buộc, mất nguồn có thể yêu cầu chặn/giữ giao dịch để xem xét thay vì “cho qua”. Nếu hệ thống có chính sách giới hạn rủi ro và fallback được phê duyệt, phải nêu rõ loại giao dịch, hạn mức, audit và người chịu trách nhiệm.

### 21.4. Bảo mật và quyền truy cập

Khi authorization source không sẵn sàng, không tự cấp quyền dựa trên việc người dùng đã đăng nhập. Có thể dùng quyền được cache theo chính sách có cam kết mạnh và thời hạn ngắn nếu hệ thống cho phép, nhưng không xem đó là default.

### 21.5. Khác nhau giữa UX fallback và business fallback

Một UI có thể hiển thị “thông tin tạm thời chưa tải được” để không bỏ trống trang, nhưng business command phải dựa trên kết quả có thẩm quyền. Đây là nguyên tắc ngăn graceful degradation biến thành hành vi kinh doanh sai.

## 22. Chuyển từ fan-out đồng bộ sang read model

Nếu một màn hình truy vấn 12 service và thường xuyên bị partial failure, có thể cần thay đổi kiến trúc thay vì tăng timeout mãi.

### 22.1. Trước khi tạo read model

Hỏi:

- Có bao nhiêu nguồn thực sự cần cho một use case?
- Có thể gom các API đọc trong bounded context owner không?
- Có thể gọi song song/batch không?
- Nguồn nào có cache hợp lệ?
- Nhiều màn hình có thật sự dùng cùng mô hình dữ liệu?
- Một số dữ liệu có thể được tạo sẵn qua event/CDC không?
- Mức stale cho phép là bao lâu?
- Có thể định nghĩa tính đầy đủ qua version hoặc watermark không?

### 22.2. Read model từ sự kiện

~~~text
OrderCreated / OrderUpdated ----+
                                |
PaymentCaptured / Refunded -----+--> Projection updater --> OrderOverview DB
                                |
ShipmentCreated / Delivered ----+
                                                       |
User --> Overview Query ------------------------------+
~~~

Read model cho phép một query latency thấp và tránh fan-out runtime. Nhưng khi event pipeline trễ hoặc mất:

- Projection có thể thiếu phần Payment hoặc Shipping.
- Sự kiện có thể lặp hoặc đến sai thứ tự.
- Replay phải chịu được schema cũ và side effect.
- Retention có thể không đủ để xây từ đầu.
- Phải có cơ chế rebuild, checkpoint và đối soát.

Một read model không tự động luôn đầy đủ; chỉ chuyển nơi giải quyết partial failure từ request time sang projection pipeline.

### 22.3. Watermark và completeness

Có thể theo dõi watermark riêng cho từng nguồn:

~~~json
{
  "sourceWatermarks": {
    "orders": "2026-11-11T08:30:00Z",
    "payments": "2026-11-11T08:29:45Z",
    "shipping": "2026-11-11T08:29:10Z"
  },
  "projectionStatus": "LAGGING",
  "completeForRequestedSnapshot": false
}
~~~

Cần xác định watermark có nghĩa chính xác gì; không coi ba timestamp đơn giản là bằng chứng transactionally consistent snapshot. Với stream nhiều partition, cần chiến lược theo dõi tiến độ đủ cho từng partition/nguồn.

## 23. Thiết kế API xử lý kết quả thiếu và bất biến payload

### 23.1. Mô hình câu trả lời có metadata

Một hướng triển khai:

~~~json
{
  "data": {
    "customer": {
      "id": "c-1",
      "displayName": "Nguyễn A"
    },
    "recentOrders": {
      "items": [],
      "status": "UNAVAILABLE"
    }
  },
  "meta": {
    "completeness": "PARTIAL",
    "generatedAt": "2026-11-11T08:35:00Z",
    "requestId": "req-4c71"
  }
}
~~~

Giá trị items=[] khi status=UNAVAILABLE không được UI dùng để kết luận “khách không có đơn hàng”. Tốt hơn có thể chọn items=null ở trạng thái không xác định; quan trọng là contract rõ, client không phải suy đoán.

### 23.2. Partial sources với chỉ báo độc lập

Có thể dùng:

~~~json
{
  "sections": {
    "customer": {
      "status": "AVAILABLE",
      "data": {"id": "c-1"}
    },
    "recentOrders": {
      "status": "UNAVAILABLE",
      "data": null,
      "reason": "ORDERS_TIMEOUT"
    }
  }
}
~~~

Mô hình này ít nhầm hơn khi có nhiều phần độc lập. Đổi lại payload dài hơn và frontend cần map trạng thái rõ.

### 23.3. Schema evolution

Khi thêm một nguồn mới, phải quyết định nó optional hay required. Nếu một client cũ không hiểu trường mới, completeness của toàn response có thể thay đổi theo cách khó lường. Nên version hóa hợp đồng hoặc giữ semantics tương thích, test consumer và phân loại từng section.

### 23.4. Error code và retry hint

Error code cần ổn định hơn câu message tự do; client dựa vào code để hiển thị hoặc retry. Retryable=true là gợi ý dựa trên loại lỗi; vẫn cần giới hạn số lần, backoff và quyền người dùng chủ động thử lại. Không gửi internal exception class như public error code.

## 24. Observability: đo kết quả dùng được, không chỉ HTTP 200

### 24.1. Metric của API tổng hợp

- Request count, p50/p95/p99 latency, 4xx/5xx.
- Tỷ lệ **COMPLETE/PARTIAL/UNAVAILABLE** theo endpoint/use case.
- Tỷ lệ thiếu từng section: pricing, inventory, recommendations.
- Tỷ lệ response dùng stale cache và phân phối tuổi dữ liệu.
- Tỷ lệ bị disable business action do nguồn critical lỗi.
- Fan-out call count, concurrency và connection pool saturation.
- Tổng số attempt downstream, retry amplification ratio.
- Số request kết thúc sau deadline hoặc hủy giữa chừng.

### 24.2. Metric theo nguồn

| Metric | Ý nghĩa |
| --- | --- |
| Upstream p50/p95/p99 | Phân phối latency của nguồn |
| Timeout rate | Bao nhiêu call vượt deadline |
| 5xx rate / error code | Nguồn lỗi hạ tầng |
| Circuit breaker state | Đang chặn request hay đang thử phục hồi |
| Cache hit rate / stale rate | Tỷ lệ phải gọi nguồn và dữ liệu cũ |
| Bulkhead rejection rate | Có vượt giới hạn concurrency không |
| Data validation errors | Dữ liệu trả về sai schema/semantics |
| Projection lag | Độ chậm read model so với sự kiện |
| Reconciliation mismatches | Sự khác biệt với source of truth |

### 24.3. Log và tracing

Một trace có thể gồm:

~~~text
GET /orders/o-742/overview (requestId=req-519)
 |
 +--> Orders GET /orders/o-742             82 ms SUCCESS
 +--> Payments GET /payments?order=o-742  300 ms TIMEOUT
 +--> Shipping GET /shipments?order=o-742 104 ms SUCCESS
 |
 +--> compose PARTIAL  -> 200
~~~

Log nên ghi logical source, error code, retry attempts, deadline còn lại và completeness. Không log chi tiết payment card, credential hoặc PII không cần thiết.

### 24.4. Cảnh báo dựa trên trải nghiệm

Một endpoint có 99,9% HTTP 200 nhưng 40% responses ở trạng thái PARTIAL do Pricing lỗi vẫn là một sự cố. Alert nên dựa trên tỷ lệ kết quả thiếu critical fields và số người dùng bị ảnh hưởng, không chỉ HTTP 5xx.

### 24.5. SLO ví dụ

Các mục tiêu minh họa cần được kiểm chứng theo sản phẩm:

- 99% product detail requests có Catalog đầy đủ.
- 99% checkout preview requests có thông tin giá được xác minh trong latency budget.
- Không quá 2% product details thiếu Recommendations trong thời gian bình thường.
- 95% order overview requests trả đầy đủ các phần quan trọng dưới 500 ms.
- Stale data hiển thị chỉ trong khoảng freshness policy cho phép.

Một SLO “latency rất nhanh” không đủ khi tốc độ cao đạt được bằng cách bỏ qua nguồn dữ liệu quan trọng.

## 25. Testing theo ma trận lỗi

### 25.1. Đừng chỉ test happy path

Cần có bộ test cho:

1. Tất cả nguồn trả Available.
2. Optional source timeout.
3. Critical source timeout.
4. Nguồn trả Empty hợp lệ.
5. Nguồn trả NotFound.
6. Nguồn trả 403.
7. Dữ liệu trả về sai schema.
8. Stale cache nằm trong giới hạn.
9. Stale cache vượt giới hạn.
10. Hai nguồn trả dữ liệu mâu thuẫn.
11. Hai upstream cùng lỗi.
12. Toàn bộ deadline request sắp hết.
13. Một nguồn phục hồi sau circuit open.
14. Retry dẫn tới duplicate response/attempt.
15. Partial pagination và missing shard.
16. Client cũ nhận response có thêm section.
17. Tenant A yêu cầu dữ liệu của tenant B.
18. Read model trễ hoặc không cập nhật.
19. Một nguồn trả kết quả rất chậm nhưng không lỗi.
20. Cache stampede khi một key phổ biến hết hạn.

### 25.2. Contract tests

Các dịch vụ nguồn phải có contract ổn định: NotFound, Empty, Forbidden, Retryable, timestamps, units và schema. Nếu adapter của BFF mong 404 là “không có giá” nhưng Pricing đổi semantics thành 204 hoặc body rỗng, rất dễ làm UI sai. Test contract giúp phát hiện thay đổi trước deploy.

### 25.3. Fault injection

Có thể dùng test doubles hoặc môi trường staging có kiểm soát để tiêm timeout, 503, delayed response và corrupted payload. Không nên thử phá một dependency quan trọng trên production khi chưa có phạm vi, runbook và phương án rollback.

### 25.4. Property-based/contract invariants

Một số bất biến kiểm thử tốt:

- Nếu Pricing không AVAILABLE, canCheckout không được true chỉ vì Catalog vẫn khỏe.
- Nếu source status UNAVAILABLE, không diễn giải empty list là “không có bản ghi”.
- Nếu partialTotal=true, response không được mang nhãn overallTotalFinal.
- Nếu cache age vượt maxAge, source không được trả AVAILABLE_FRESH.
- Nếu unauthorized, không được fallback cache để lộ resource.
- Một source có status INVALID không được tham gia tổng hợp tiền.

Đây là những điều kiện có thể kiểm tra tự động, không phụ thuộc một tập dữ liệu cụ thể.

## 26. Kế hoạch xử lý sự cố nguồn không khả dụng

Một runbook thực tế nên có:

### Bước 1: Phân loại mức độ ảnh hưởng

- Nguồn nào đang lỗi?
- Các use case phụ thuộc vào nó có critical hay optional?
- Có bao nhiêu request/tenant/user bị ảnh hưởng?
- API trả partial hay lỗi hoàn toàn?
- Có dữ liệu stale đang được dùng quá ngưỡng không?
- Có nguy cơ business action đã thực thi sai không?

### Bước 2: Ổn định đường gọi

- Giới hạn retry và request fan-out.
- Bật/điều chỉnh circuit breaker theo policy đã kiểm thử.
- Điều chỉnh concurrency hoặc load shedding nếu backend bão hòa.
- Cô lập tính năng tùy chọn khi có thể.
- Tránh cache stampede và flood upstream.
- Nếu cần, tắt tạm các thao tác không thể xác nhận an toàn.

### Bước 3: Xác minh sự thật nghiệp vụ

- Kiểm tra tình trạng nguồn có thẩm quyền.
- Đối chiếu dữ liệu đã hiển thị/đã tạo và các command quan trọng.
- Xác định có quyết định nào dựa trên partial/stale gây sai không.
- Nếu có, kích hoạt quy trình khắc phục nghiệp vụ và audit theo owner.

### Bước 4: Khôi phục có kiểm soát

- Khi nguồn hồi phục, giảm circuit open và retry theo cơ chế thử giới hạn.
- Theo dõi liệu backlog/caches/projections có được làm mới không.
- Tránh cho toàn bộ request refresh cùng lúc.
- Kiểm tra completeness và freshness trước khi tuyên bố hết sự cố.

### Bước 5: Hậu kiểm

- Điều gì khiến lỗi lan rộng?
- Response có che giấu UNKNOWN thành một giá trị hợp lệ không?
- Alert có phát hiện tỷ lệ PARTIAL không?
- Deadline/retry/circuit policy có gây quá tải?
- Cần thay fan-out runtime bằng read model hoặc tối ưu domain API không?

## 27. Những anti-pattern phổ biến

| Anti-pattern | Hậu quả | Thiết kế phù hợp hơn |
| --- | --- | --- |
| Catch all rồi trả null/0/false | Dữ liệu lỗi thành kết luận hợp lệ | Typed result có trạng thái |
| Bất kỳ nguồn nào lỗi thì mọi trang đều 500 | Mất toàn bộ trải nghiệm dù phần phụ trợ lỗi | Phân loại critical/optional |
| Mọi nguồn lỗi đều trả 200 “thành công” | Monitoring và UI không nhận ra sự cố | Completeness/error code rõ |
| Coi timeout là NotFound | Resource tồn tại bị ẩn hoặc xử lý sai | Phân biệt 404 xác thực với unavailable |
| Hiển thị tổng của phần đã biết như tổng toàn bộ | Dashboard sai và quyết định sai | Partial total/scope và unknown |
| Trả cache stale vô hạn | Dữ liệu cũ gây quyết định sai | Freshness budget và fallback policy |
| Chỉ kiểm tra quyền ở truy vấn live, không ở cache | Lộ dữ liệu giữa tenant/user | Authorization trên mọi đường trả dữ liệu |
| Retry mọi lỗi liên tục | Thêm tải, tăng latency, retry storm | Retry budget và phân loại lỗi |
| Nối tiếp tất cả upstream calls | Tail latency lớn và lỗi lan | Parallel/batch khi độc lập |
| Tạo hàng trăm call cho một page | N+1 và fan-out explosion | Read model/batch API/pagination |
| Dùng một timeout rất dài | Giữ connection/thread, UX treo | Deadline end-to-end |
| Dùng 206 cho mọi partial payload | Sai kỳ vọng giao thức | Contract có completeness rõ |
| Chỉ đo HTTP error rate | Không thấy core data bị thiếu | Metrics về completeness và stale |
| Join inner rồi bỏ bản ghi thiếu | Mất dòng dữ liệu khỏi báo cáo | Left join có status hoặc fail |
| Để BFF quyết định business invariant | Logic trùng, thiếu source of truth | Domain/application owner |
| Read model không có watermark | Không biết dữ liệu còn thiếu | Lag/freshness/completeness metadata |
| Không có chủ sở hữu lỗi từng section | Incident không ai xử lý | Owner, SLO, runbook và escalation |
| Test chỉ happy path | Lỗi partial gây hậu quả mới biết | Failure matrix, contract, fault injection |

## 28. Bài tập thực hành A — trang sản phẩm đa nguồn

**Bối cảnh:** BFF gọi Catalog, Pricing, Inventory, Reviews và Recommendations. Catalog trả sau 60 ms, Pricing timeout ở 250 ms, Inventory trả “UNKNOWN” sau 120 ms, Reviews thành công, Recommendations 503.

Hãy thiết kế:

1. Một dependency matrix cho trang chi tiết và nút mua.
2. Response JSON đầy đủ gồm data, status từng section và completeness.
3. HTTP status cho trang thông tin và cho endpoint tính quote trước checkout.
4. UI message khi Pricing timeout, không bịa giá hoặc tồn kho.
5. Deadline 400 ms và timeout budget cho các dependency.
6. Chính sách retry nếu Pricing có lỗi 503 tạm thời.
7. Tính năng nào có thể cache stale và giới hạn freshness.
8. Metric/alert phân biệt Pricing critical với Recommendations optional.
9. Hai test cases ngăn việc hiển thị “hết hàng” khi Inventory lỗi.
10. Phương án giảm fan-out nếu page đang gọi 20 service.

**Gợi ý phân tích:** Catalog và Reviews có thể hiển thị; giá và tồn kho phải được đánh dấu chưa xác nhận, nút checkout bị khóa hoặc chuyển sang kiểm tra lại theo policy. Recommendations có thể ẩn. Request phục vụ trang có thể dùng partial 200; command thực hiện mua phải xác nhận điều kiện trong domain owner. Bất kỳ fallback nào cũng phải có contract rõ.

## 29. Bài tập thực hành B — báo cáo số liệu tài chính liên vùng

**Bối cảnh:** một dashboard nhận số liệu từ năm vùng. Bốn vùng trả kết quả, vùng cuối không phản hồi. Một nguồn trong bốn vùng trả số tiền USD, các vùng khác trả VND. Hệ thống đang có logic biến nguồn lỗi thành 0 và trả “Tổng doanh thu toàn hệ thống”.

Yêu cầu:

1. Chỉ ra những kết luận nào không được phép rút ra từ dữ liệu hiện có.
2. Thiết kế schema cho observed subtotal, overall total, completeness, currency và unavailable regions.
3. Giải thích cách xử lý khác nhau giữa dashboard tham khảo và báo cáo khóa sổ.
4. Đề xuất nơi quản lý tỷ giá, thời điểm áp dụng và quy tắc làm tròn.
5. Thiết kế cách đối soát dữ liệu sau khi vùng lỗi phục hồi.
6. Nếu báo cáo tốn 10 phút, phân biệt API request trực tiếp và report job.
7. Đề xuất SLO theo completeness và deadline, không chỉ HTTP 200.
8. Viết hai cảnh báo: missing source và stale source.
9. Xác định cách kiểm tra không để data từ hai tenant bị trộn.
10. Thiết kế test với một vùng có amount=0 thật và một vùng unavailable.

**Gợi ý:** tổng tạm có thể được hiển thị cùng phạm vi rõ, còn overallTotal nên là null/unknown nếu thiếu vùng thiết yếu. Không cộng tiền khác đơn vị. Báo cáo có yêu cầu pháp lý hoặc quyết định tài chính cần hoàn tất/đối soát theo contract; không chốt bằng dữ liệu ước đoán.

## 30. ADR mẫu — Graceful degradation cho Order Overview

~~~markdown
# ADR: Partial Response cho Order Overview

## Bối cảnh
Order Overview cần Orders, Payments, Shipping.
Orders là nguồn nhận dạng và phân quyền đơn hàng.
Payments có thể lỗi tạm thời, Shipping có thể trễ.

## Quyết định
- Truy vấn Orders là bắt buộc; thất bại trả lỗi phù hợp.
- Payments và Shipping được hiển thị trạng thái AVAILABLE,
  EMPTY, UNAVAILABLE hoặc STALE theo contract.
- Nếu Payments UNAVAILABLE, vẫn hiển thị đơn nhưng
  không suy ra trạng thái đã/chưa thanh toán.
- Nếu Shipping STALE, chỉ hiển thị khi tuổi dữ liệu nằm
  trong giới hạn được phê duyệt và ghi thời điểm cập nhật.
- Mọi write command nhạy cảm xác minh tại domain owner.
- BFF áp dụng deadline chung, giới hạn retry và tracing.
- Theo dõi completeness/critical section errors.

## Phương án cân nhắc
A. Fail toàn trang khi bất kỳ nguồn lỗi.
B. Luôn trả 200 và mọi trường lỗi thành null.
C. Partial response có trạng thái từng section.
D. Dùng read model cho tất cả nguồn.

## Hệ quả
- UI phải xử lý trạng thái nguồn rõ ràng.
- API phức tạp hơn nhưng tránh thông tin sai.
- Cần metrics và contract tests cho partial data.
- Có thể cân nhắc read model nếu fan-out trở nên tốn kém.

## Kiểm chứng
- Test Pricing/Payments timeout, 403, 404, Empty, Stale.
- Test không coi null/timeout thành kết quả nghiệp vụ.
- Test tenant isolation ở cả cache và upstream.
- Đo p95/p99, partial response rate và freshness.

## Điều kiện xem lại
- Tỷ lệ partial vượt SLO.
- Nhiều consumer cần cùng dữ liệu tổng hợp.
- Query latency và fan-out khó kiểm soát.
~~~

## 31. Checklist thiết kế trước khi triển khai

**Hợp đồng dữ liệu**

- [ ] Phân biệt Empty, NotFound, Unavailable, Invalid, Stale và Conflict.
- [ ] Xác định nguồn nào là source of truth cho từng trường.
- [ ] Phân loại critical/optional/degradable theo use case.
- [ ] Mô tả response completeness và section status rõ ràng.
- [ ] Không dùng null, 0 hoặc danh sách rỗng để che lỗi.
- [ ] Trường tổng hợp có scope, đơn vị và trạng thái đầy đủ.
- [ ] Có policy xử lý dữ liệu mâu thuẫn và khác thời điểm.

**Độ tin cậy**

- [ ] Có deadline end-to-end và timeout mỗi nguồn.
- [ ] Gọi song song các nguồn độc lập có giới hạn concurrency.
- [ ] Retry có điều kiện, giới hạn số lần và tránh bão retry.
- [ ] Circuit breaker/bulkhead có owner và thông số được đo.
- [ ] Fallback cache có max stale age và rule không làm sai nghiệp vụ.
- [ ] Không biến lỗi permission thành lỗi hạ tầng rồi retry vô hạn.
- [ ] Có hành vi rõ khi tất cả nguồn hoặc nguồn critical lỗi.

**Bảo mật và vận hành**

- [ ] Tenant/user authorization áp dụng cả đường cache fallback.
- [ ] Response không rò nội bộ, secret hay dữ liệu ngoài quyền.
- [ ] Có metrics COMPLETE/PARTIAL/UNAVAILABLE và section errors.
- [ ] Có trace/log cho source, deadline, retry, cache và requestId.
- [ ] Alert theo business usefulness, không chỉ HTTP status.
- [ ] Có runbook khi nguồn lỗi, khi projection lag và khi khôi phục.
- [ ] Có test fault injection, contract, partial join/pagination.
- [ ] Có người sở hữu tính đúng đắn và đối soát dữ liệu.

## 32. Tổng kết

Trong **truy vấn liên dịch vụ**, nguồn dữ liệu không khả dụng là trạng thái bình thường cần thiết kế trước, chứ không chỉ là exception để bắt cho hết. Mấu chốt không phải lúc nào cũng trả một trang “đẹp”, mà là trả **sự thật mà hệ thống thực sự biết**, chỉ rõ phần không biết và ngăn các hành động nguy hiểm dựa trên dữ liệu thiếu.

Một thiết kế bền vững thực hiện đồng thời bốn việc:

1. **Đúng ngữ nghĩa:** phân biệt kết quả rỗng, không tồn tại, lỗi truy vấn và dữ liệu cũ.
2. **Đúng mức độ quan trọng:** phần optional có thể suy giảm, phần critical phải bảo vệ invariant.
3. **Đúng kỹ thuật:** deadline, retry budget, circuit breaker, bulkhead, cache/read model và backpressure phù hợp.
4. **Đúng khả năng quan sát:** biết nguồn nào thiếu, nguồn nào stale, tác động tới use case nào, ai chịu trách nhiệm và đã phục hồi hoàn toàn chưa.

Khi thực hiện đúng, hệ thống có thể tiếp tục cung cấp giá trị trong các sự cố cục bộ mà không biến **kết quả thiếu một phần** thành **thông tin hoàn chỉnh giả tạo**.
