# API tổng hợp, Backend for Frontend và giảm số lần gọi

Một màn hình trên web hoặc ứng dụng di động thường cần dữ liệu từ nhiều năng lực nghiệp vụ: thông tin tài khoản, danh sách sản phẩm, trạng thái đơn hàng, lịch trống, thanh toán và thông báo. Nếu client phải gọi từng API riêng lẻ, số lần trao đổi qua mạng tăng, logic ghép dữ liệu bị lặp ở nhiều nơi và trải nghiệm dễ bị ảnh hưởng khi một dịch vụ phản hồi chậm. **API aggregation** và **Backend for Frontend (BFF)** là hai mẫu kiến trúc giúp tổ chức việc lấy dữ liệu phù hợp với nhu cầu của client, đồng thời giảm số lần gọi và kiểm soát độ phức tạp phía trình duyệt/ứng dụng.

Bài học thuộc chương **Kiến trúc API** trong lộ trình **Cloud Architecture**. Trọng tâm là thiết kế API tổng hợp, chọn ranh giới BFF, kết hợp dữ liệu từ nhiều dịch vụ và giảm round trip mà vẫn giữ được quyền sở hữu nghiệp vụ, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành. Mục tiêu không phải gom mọi API vào một endpoint khổng lồ; mục tiêu là tạo ra hợp đồng phù hợp với một hành trình hoặc màn hình, có giới hạn rõ về dữ liệu, độ trễ và trách nhiệm.

Sau bài học, bạn có thể:

- Giải thích API aggregation, API composition và BFF, đồng thời phân biệt vai trò của chúng.
- Xác định khi nào nên tổng hợp ở API gateway, BFF, backend nghiệp vụ hoặc lớp query.
- Thiết kế BFF theo loại client và hành trình người dùng mà không nhân bản nghiệp vụ cốt lõi.
- Giảm round trip qua batching, projection, cache, pagination và endpoint phù hợp.
- Xử lý timeout, lỗi một phần, retry, concurrency và tính nhất quán khi tổng hợp nhiều nguồn.
- Bảo vệ quyền truy cập, dữ liệu cá nhân, tenant boundary và chống over-fetching.
- Đo hiệu quả bằng latency p95/p99, số request, payload, lỗi, chi phí và SLO đầu cuối.

## 1. Vấn đề của nhiều API nhỏ từ góc nhìn client

Giả sử trang chi tiết đơn thuê cần hiển thị:

- Thông tin cơ bản của đơn và trạng thái hiện tại.
- Tên khách hàng và thông tin liên hệ được phép hiển thị.
- Danh sách thiết bị, hình ảnh và khoảng thời gian thuê.
- Tổng tiền, trạng thái thanh toán và hóa đơn.
- Tiến trình giao nhận và thông báo mới nhất.

Nếu client gọi lần lượt năm API, mỗi API lại cần thêm một số request phụ, trang có thể chậm dù từng backend riêng lẻ đều phản hồi tương đối nhanh. Nếu client gọi song song, tổng thời gian có thể giảm nhưng client phải biết nhiều service, xử lý nhiều kiểu lỗi, xác thực và ghép dữ liệu.

Những vấn đề thường xuất hiện:

1. **Nhiều round trip:** mỗi request có độ trễ cố định của DNS, TLS, mạng, gateway và xử lý.
2. **Logic ghép dữ liệu bị lặp:** web, iOS và Android có thể tự gọi cùng nguồn rồi tự ghép.
3. **Coupling vào backend:** client cần biết tên service, endpoint, schema và quan hệ dữ liệu nội bộ.
4. **Over-fetching hoặc under-fetching:** API trả quá nhiều dữ liệu hoặc client phải gọi thêm chỉ để lấy vài trường.
5. **Quản lý lỗi phức tạp:** một phần dữ liệu không tải được, client phải quyết định hiển thị gì.
6. **Khó thay đổi hợp đồng:** backend refactor khiến nhiều client phải cập nhật cùng lúc.
7. **Bề mặt bảo mật rộng:** client phải tương tác với nhiều endpoint và có nguy cơ gọi nhầm API nội bộ.

API aggregation và BFF chuyển phần phối hợp phù hợp về phía backend để client nhận một hợp đồng gần với nhu cầu hiển thị hơn.

## 2. Phân biệt các mẫu kiến trúc

### 2.1. API aggregation

**API aggregation** là việc một endpoint hoặc thành phần backend gọi nhiều nguồn dữ liệu/dịch vụ, kết hợp kết quả và trả về một response. Aggregator che giấu số lượng backend phía sau và có thể thực hiện gọi song song, chuyển đổi schema hoặc áp dụng quy tắc trình bày.

Ví dụ: endpoint GET /rental-details/{id} gọi Booking, Inventory, Billing và Delivery, sau đó trả một response tổng hợp.

### 2.2. API composition

**API composition** thường mô tả một mẫu trong đó một thành phần truy vấn nhiều service rồi kết hợp dữ liệu thành kết quả cho caller. Thuật ngữ này thường gần nghĩa API aggregation, nhưng cách dùng trong từng tổ chức/framework có thể khác nhau. Điểm quan trọng là thành phần tổng hợp chịu trách nhiệm phối hợp truy vấn và định hình kết quả, còn quyền sở hữu dữ liệu vẫn thuộc các service nguồn.

### 2.3. Backend for Frontend

**Backend for Frontend (BFF)** là một backend được thiết kế quanh nhu cầu của một loại client hoặc trải nghiệm cụ thể. Ví dụ có BFF cho web, mobile và đối tác; mỗi BFF cung cấp hợp đồng thích hợp với khả năng, luồng tương tác, bảo mật và giới hạn của client đó.

BFF thường dùng API aggregation để lấy dữ liệu. Nhưng BFF còn có thể xử lý:

- Xác thực session/token và chuyển tiếp danh tính theo chuẩn.
- Chuyển đổi response cho đúng client và version.
- Áp dụng pagination, filtering và field projection phù hợp.
- Điều phối những bước đọc dữ liệu phục vụ màn hình.
- Quản lý cache hoặc request coalescing.
- Chuẩn hóa lỗi và cung cấp fallback cho dữ liệu không bắt buộc.

BFF không nên trở thành nơi chứa lại toàn bộ nghiệp vụ của các service nguồn. Quy tắc như “đơn thuê nào có thể hủy”, “tài sản nào được giữ” hoặc “khi nào hoàn tiền” phải do năng lực nghiệp vụ có thẩm quyền thực thi.

### 2.4. Bảng phân biệt

| Mẫu | Câu hỏi nó giải quyết | Phạm vi điển hình | Ví dụ |
| --- | --- | --- | --- |
| API aggregation | Làm sao kết hợp nhiều nguồn trong một response? | Một use case/query | Trang tổng quan đơn thuê |
| API composition | Làm sao truy vấn nhiều service và tạo kết quả? | Lớp phối hợp dữ liệu | Báo cáo trạng thái từ Booking và Billing |
| BFF | Client cụ thể cần hợp đồng nào? | Một trải nghiệm hoặc loại client | Web BFF, Mobile BFF |
| API gateway | Làm sao quản lý điểm vào chung? | Cross-cutting edge concerns | TLS, auth, routing, rate limit |
| GraphQL gateway/federation | Client cần chọn trường và kết hợp schema như thế nào? | Schema/query API | Query nhiều domain qua một graph |

Các mẫu có thể kết hợp. Một BFF có thể là API aggregator; API gateway đứng trước BFF để xử lý những chính sách biên chung. GraphQL có thể là cách công bố query, nhưng bản thân GraphQL không tự giải quyết ownership, authorization, N+1 hoặc giới hạn truy vấn.

## 3. Khi nào cần API aggregation?

Aggregation phù hợp khi có một use case rõ ràng cần dữ liệu từ nhiều nguồn và việc gọi trực tiếp các nguồn sẽ làm client phức tạp hoặc tăng độ trễ.

Các tín hiệu:

- Một màn hình thường xuyên cần 3 hoặc nhiều API từ các domain khác nhau.
- Nhiều client phải lặp lại cùng logic ghép dữ liệu.
- Cấu trúc dữ liệu backend không phù hợp với ngôn ngữ hiển thị.
- Có thể gọi các nguồn song song hoặc batch theo cách an toàn.
- Cần chuẩn hóa lỗi, timeout và fallback tại server.
- Có cơ hội giảm round trip mà không tạo coupling không kiểm soát.

Không nên aggregation chỉ để giảm số endpoint trên tài liệu. Nếu một màn hình chỉ cần một API nhanh và ổn định, thêm aggregator có thể tạo thêm hop, điểm lỗi và chi phí.

### 3.1. Ví dụ trước và sau

**Trước:** client lấy dữ liệu từ nhiều backend.

~~~mermaid
flowchart TB
    C["Web / Mobile client"]
    C --> B["Booking API"]
    C --> I["Inventory API"]
    C --> P["Payment API"]
    C --> D["Delivery API"]
    C --> N["Notification API"]
~~~

**Sau:** client gọi một endpoint tổng hợp.

~~~mermaid
flowchart TB
    C["Web / Mobile client"] --> A["Rental Details Aggregator"]
    A --> B["Booking API"]
    A --> I["Inventory API"]
    A --> P["Payment API"]
    A --> D["Delivery API"]
    A --> N["Notification API"]
    A --> R["Một response theo nhu cầu màn hình"]
~~~

Sơ đồ không có nghĩa aggregator thay thế các backend nguồn. Các service vẫn chịu trách nhiệm dữ liệu và nghiệp vụ của mình; aggregator chỉ phối hợp việc đọc và tạo response.

## 4. Xác định ranh giới BFF theo client và hành trình

Không nhất thiết mỗi ứng dụng hoặc mỗi màn hình có một BFF riêng. Ranh giới nên dựa trên sự khác biệt đủ lớn về nhu cầu, chu kỳ phát hành, giao thức, bảo mật hoặc trải nghiệm.

Ví dụ:

| Client | Nhu cầu đặc thù | Thiết kế response có thể phù hợp |
| --- | --- | --- |
| Web quản trị | Bảng nhiều cột, filter phong phú, thao tác hàng loạt | Pagination, sort/filter, dữ liệu quản trị theo quyền |
| Mobile khách hàng | Payload nhỏ, mạng biến động, màn hình gọn | Projection tối thiểu, ảnh thumbnail, cache phù hợp |
| Đối tác API | Hợp đồng ổn định, versioning và giới hạn rõ | Schema công bố, quota, idempotency với command |
| Thiết bị/kiosk | Giao tiếp hạn chế, chỉ cần một số trường | Compact response, timeout ngắn, cache cục bộ có TTL |

Một BFF cho Web và một BFF cho Mobile có thể hợp lý nếu response, tốc độ phát hành, bảo mật hoặc khả năng mạng khác nhau đáng kể. Nhưng nếu hai client gần như cùng nhu cầu và cùng owner, một BFF chung với projection hoặc API version có thể đơn giản hơn.

### 4.1. Câu hỏi xác định BFF

1. Client có cần cấu trúc dữ liệu khác nhau không?
2. Một client có giới hạn bandwidth, memory, pin hoặc khả năng kết nối đặc thù không?
3. Lịch phát hành và version compatibility có khác nhau không?
4. Có chính sách bảo mật, session hoặc authorization khác nhau không?
5. Aggregation có yêu cầu logic riêng cho trải nghiệm đó không?
6. Có đủ đội ngũ ownership và observability để vận hành thêm backend không?

Chỉ tạo BFF mới khi lợi ích về trải nghiệm, quyền, thay đổi hoặc hiệu năng lớn hơn chi phí bổ sung service, pipeline, monitoring và on-call.

## 5. BFF nên làm gì và không nên làm gì?

BFF là lớp thích nghi giữa client và backend, không phải domain service mới cho tất cả nghiệp vụ.

**Nên làm:**

- Kết hợp dữ liệu phục vụ một trải nghiệm.
- Giảm hoặc chuẩn hóa payload.
- Ánh xạ DTO/backend schema sang client contract.
- Kiểm tra quyền ở biên và chuyển tiếp identity/context có kiểm soát.
- Chuẩn hóa pagination, error format và trace context.
- Cache dữ liệu đọc phù hợp và giới hạn request fan-out.
- Điều phối đọc dữ liệu; với command, gọi service có quyền thực hiện nghiệp vụ.

**Không nên:**

- Tạo bản sao quy tắc domain như tính giá, phê duyệt hoàn tiền hoặc quyết định tồn kho.
- Ghi trực tiếp vào database của service khác.
- Chia sẻ một service credential có quyền quá rộng cho mọi client.
- Trả toàn bộ dữ liệu nguồn rồi buộc client tự lọc.
- Trở thành điểm bắt buộc cho mọi luồng nội bộ dù không cần.
- Gộp workflow dài hoặc giao dịch nhiều bước vào một request aggregation đồng bộ.
- Bỏ qua giới hạn số backend call, timeout và payload.

Một cách tự kiểm tra: nếu thay đổi quy tắc nghiệp vụ cốt lõi cần sửa BFF để bảo đảm tính đúng, có khả năng quy tắc đó đang nằm sai lớp.

## 6. Thiết kế response theo use case

Response tổng hợp nên là một **read model** phù hợp với câu hỏi của client, không phải bản dump của tất cả backend.

Ví dụ response chi tiết đơn thuê:

~~~json
{
  "booking": {
    "id": "bk-100582",
    "status": "CONFIRMED",
    "startDate": "2026-12-03",
    "endDate": "2026-12-06"
  },
  "customer": {
    "displayName": "Nguyen A"
  },
  "items": [
    {
      "id": "asset-21",
      "name": "Camera kit",
      "thumbnailUrl": "/media/asset-21/thumb"
    }
  ],
  "payment": {
    "status": "PAID",
    "total": {
      "amount": 1250000,
      "currency": "VND"
    }
  },
  "delivery": {
    "status": "SCHEDULED",
    "estimatedAt": "2026-12-03T02:00:00Z"
  }
}
~~~

Các trường là dữ liệu minh họa. BFF cần chỉ trả trường client được quyền xem. Ví dụ khách không nhất thiết được xem thông tin kiểm toán nội bộ, ghi chú chống gian lận hay địa chỉ billing nhạy cảm.

### 6.1. Projection và field selection

Projection giúp client nhận đúng trường cần dùng. Có thể thiết kế endpoint riêng cho summary và detail:

| Endpoint | Trường dữ liệu | Mục đích |
| --- | --- | --- |
| GET /me/bookings | id, status, startDate, endDate, thumbnail | Danh sách nhẹ |
| GET /me/bookings/{id} | Chi tiết đơn, item, payment status, delivery summary | Màn hình chi tiết |
| GET /admin/bookings/{id} | Thông tin mở rộng theo quyền nhân viên | Quản trị |
 
Không phải cứ cho client chọn mọi field là tốt. Field selection tự do có thể làm query phức tạp, gây over-fetching từ backend hoặc cho phép truy xuất trường nhạy cảm. Nếu dùng GraphQL hoặc query language, cần allowlist field, depth/complexity limit, pagination và authorization theo field/object.

### 6.2. API chuyên theo màn hình hay API tài nguyên?

**API tài nguyên** như GET /bookings/{id} cung cấp biểu diễn của một tài nguyên và có thể dùng lại bởi nhiều client.

**API theo trải nghiệm** như GET /mobile/home-summary tổng hợp nhiều tài nguyên theo nhu cầu màn hình.

Hai kiểu không loại trừ nhau. API tài nguyên giúp hợp đồng domain rõ; API theo trải nghiệm giúp giảm số lượt gọi và payload. Tránh tạo một endpoint cho từng pixel/màn hình nếu dữ liệu và hành vi hầu như giống nhau.

## 7. Giảm số lần gọi: batching và fan-out có kiểm soát

Aggregation không phải lúc nào cũng giảm số request backend. Một aggregator gọi 10 backend trong một request client sẽ giảm round trip phía client nhưng có thể tăng fan-out nội bộ. Cần tối ưu cả hai lớp.

### 7.1. Batch nhiều định danh

Nếu client cần trạng thái của 20 booking, thay vì gọi một request cho mỗi booking, backend có thể cung cấp endpoint batch:

~~~http
POST /booking-status:batchGet
Content-Type: application/json

{
  "bookingIds": ["bk-1", "bk-2", "bk-3"]
}
~~~

Batch API cần giới hạn số item, xác định hành vi khi một phần ID không tồn tại hoặc không được phép truy cập, và chống lạm dụng payload lớn. Response nên trả kết quả theo ID để client ghép ổn định.

Batch không phải là gửi một mảng không giới hạn. Một request có 10.000 ID có thể gây truy vấn quá lớn, memory pressure và timeout. Cần pagination, maximum batch size và kiểm tra quota.

### 7.2. DataLoader và N+1

Trong GraphQL hoặc resolver composition, lỗi N+1 xảy ra khi resolver của mỗi item gọi backend riêng. Một trang có 100 booking có thể tạo 1 query danh sách và 100 query khách hàng.

Batch loader có thể gom các ID trong một khoảng thực thi thành một batch query:

~~~text
for each booking in page:
    customer = loadCustomer(booking.customerId)

DataLoader groups customer IDs:
    customerService.getByIds([id1, id2, ...])
~~~

DataLoader cần được dùng đúng scope; cache cấp request thường an toàn hơn cache toàn process nếu dữ liệu và quyền phụ thuộc caller/tenant. Không để kết quả của user A bị tái sử dụng cho user B.

### 7.3. Gọi song song

Nếu các backend query độc lập, aggregator có thể gọi song song thay vì nối tiếp. Nếu mỗi backend mất lần lượt 80, 120 và 150 ms, gọi nối tiếp có thể mất khoảng 350 ms cộng overhead; gọi song song có thời gian gần với backend chậm nhất cộng overhead. Đây là phép tính minh họa, thực tế phụ thuộc mạng, pool, queue và độ trễ phân vị.

Không tạo concurrency vô hạn. Cần giới hạn fan-out, connection pool và số lời gọi trên mỗi request; dùng timeout riêng cho từng dependency, circuit breaker hoặc bulkhead phù hợp; tránh một user gửi nhiều request khiến backend bị quá tải.

## 8. Mô hình tổng hợp dữ liệu và tính nhất quán

Khi aggregator gọi nhiều service, các response có thể được đọc ở những thời điểm khác nhau. Ví dụ Booking đã chuyển sang CONFIRMED nhưng Payment API vẫn trả trạng thái cũ do cập nhật bất đồng bộ. Response tổng hợp khi đó có thể phản ánh snapshot không đồng thời.

Cần quyết định mức nhất quán:

- Với thông tin hiển thị ít rủi ro như ảnh thumbnail hoặc tên sản phẩm, eventual consistency thường có thể chấp nhận.
- Với số tiền phải thu, trạng thái hoàn tiền hoặc quyền thao tác, cần lấy từ nguồn có thẩm quyền và không suy ra từ bản cache cũ.
- Với thông tin cần tương quan phiên bản, có thể trả lastUpdated/version hoặc trạng thái đang cập nhật.
- Với giao dịch cần nguyên tử, aggregator không thay thế transaction/workflow của service sở hữu nghiệp vụ.

### 8.1. Partial response

Không phải mọi nguồn đều quan trọng ngang nhau. Có thể chia:

| Dữ liệu | Mức bắt buộc | Hành vi khi nguồn lỗi |
| --- | --- | --- |
| Booking status | Bắt buộc | Trả lỗi nếu không thể xác định |
| Payment status | Bắt buộc cho thao tác thanh toán | Không cho phép hành động nhạy cảm dựa trên dữ liệu thiếu |
| Thumbnail | Không bắt buộc | Placeholder hoặc bỏ trường |
| Delivery estimate | Có thể không bắt buộc với trang summary | Trả trạng thái unavailable cùng metadata |
| Notification preview | Không bắt buộc | Bỏ hoặc trả danh sách rỗng nếu contract định nghĩa |

Nếu response cho phép dữ liệu một phần, phải thể hiện trạng thái từng section; không trả giá trị mặc định gây hiểu lầm, ví dụ payment status = PAID khi API thanh toán timeout.

Ví dụ cấu trúc một response một phần:

~~~json
{
  "booking": {
    "id": "bk-100582",
    "status": "CONFIRMED"
  },
  "payment": {
    "status": "UNAVAILABLE",
    "updatedAt": null
  },
  "delivery": {
    "status": "SCHEDULED"
  },
  "meta": {
    "partial": true,
    "unavailableSections": ["payment"]
  }
}
~~~

Ví dụ này chỉ dùng khi sản phẩm và hợp đồng API định nghĩa rõ cách client xử lý trạng thái unavailable. Với hành động thu tiền/hủy/hoàn, backend phải yêu cầu kiểm tra authoritative state trước khi thực thi.

## 9. Timeout, retry và lỗi một phần

Aggregator là một nút phối hợp nên có thể khuếch đại lỗi backend. Nếu request tổng hợp gọi 8 service và bất kỳ service nào cũng được phép chờ 3 giây, thời gian phản hồi có thể vượt SLO của client.

Thiết kế nên:

- Đặt deadline tổng và phân bổ budget theo dependency.
- Dừng lời gọi không còn hữu ích khi caller đã timeout/hủy request nếu nền tảng hỗ trợ.
- Retry chỉ lỗi tạm thời, với số lần nhỏ và backoff; không retry lỗi business hoặc validation.
- Tránh retry đồng loạt vào backend đang quá tải.
- Dùng circuit breaker/bulkhead hoặc concurrency limit khi cần.
- Phân loại dependency critical và optional.
- Trả lỗi rõ và có correlation ID cho support.
- Không che lỗi bằng dữ liệu cũ mà không đánh dấu freshness.

### 9.1. Budget độ trễ ví dụ

Giả sử màn hình cần response trong p95 = 500 ms. Có thể phân bổ budget tham khảo:

| Thành phần | Budget mục tiêu |
| --- | ---: |
| Client → API edge và auth | 70 ms |
| Aggregator xử lý/serialize | 40 ms |
| Booking backend | 120 ms |
| Payment summary | 100 ms |
| Delivery summary | 100 ms |
| Buffer cho network/variance | 70 ms |
| Tổng | 500 ms |

Nếu gọi ba backend song song, thời gian không cộng trực tiếp như bảng; mỗi dependency vẫn cần timeout riêng và deadline tổng. Phải đo phân vị end-to-end, vì tổng p95 của nhiều thành phần không thể suy ra chính xác chỉ bằng cách cộng các p95.

## 10. Cache, request coalescing và dữ liệu đọc

Aggregation có thể tăng tải backend nếu mỗi client request làm nhiều truy vấn. Cache và request coalescing giảm công việc lặp nhưng phải phù hợp freshness và quyền.

### 10.1. Những lớp cache

| Vị trí | Lợi ích | Rủi ro |
| --- | --- | --- |
| Client cache | Giảm request và cải thiện UX khi mạng yếu | Dữ liệu cũ, dữ liệu nhạy cảm còn trên thiết bị |
| CDN/edge cache | Hữu ích cho dữ liệu công khai hoặc ít đổi | Cache nhầm dữ liệu cá nhân/tenant |
| BFF response cache | Tái sử dụng response cho cùng context | Key thiếu user/tenant/permission gây lộ dữ liệu |
| Backend/domain cache | Giảm query nguồn, dùng chung cho nhiều consumer | Invalidation và consistency phức tạp |
| Request-scoped memoization | Tránh truy vấn trùng trong cùng request | Chỉ có hiệu lực trong request hiện tại |

Cache key cần phản ánh những yếu tố làm thay đổi kết quả: tenant, user scope, locale, currency, permissions, query parameters và version khi phù hợp. Không dùng chung response cache cho dữ liệu cá nhân nếu chưa chứng minh cách cô lập.

### 10.2. Time to live và invalidation

TTL dài giúp tăng cache hit nhưng tăng thời gian dữ liệu cũ. Với product catalog, TTL vài phút có thể hợp lý; với payment status cần freshness cao hơn. Những giá trị này phải dựa trên nghiệp vụ, không áp một TTL cho mọi resource.

Có thể dùng:

- TTL ngắn với stale-while-revalidate cho dữ liệu summary ít rủi ro.
- Event invalidation khi domain phát ra sự kiện thay đổi.
- ETag/conditional request để giảm payload khi dữ liệu không đổi.
- Request coalescing để nhiều request đồng thời cùng chờ một lần fetch backend.
- Không cache lỗi nhạy cảm hoặc trạng thái thanh toán theo mặc định.

### 10.3. Cache không thay thế nguồn có thẩm quyền

Nếu khách nhấn nút hoàn tiền, BFF không nên kiểm tra cache trạng thái đơn rồi quyết định. Nó phải chuyển command đến service sở hữu nghiệp vụ; service đó kiểm tra trạng thái hiện tại và invariant tại thời điểm ghi.

## 11. Pagination, filtering và payload shaping

Một endpoint tổng hợp dễ vô tình trả quá nhiều bản ghi. Nếu trang chi tiết tải toàn bộ lịch sử giao dịch, tất cả thông báo và toàn bộ danh sách sản phẩm, payload có thể tăng rất nhanh.

Thiết kế cần:

- Pagination ở nguồn phù hợp và trả continuation token/cursor an toàn.
- Giới hạn page size; không tin giá trị do client gửi mà không kiểm tra.
- Filtering/sorting chỉ trên trường được phép.
- Projection theo use case để bỏ các trường không cần.
- Giới hạn payload và kích thước danh sách lồng nhau.
- Không lấy page đầu từ service A và page tiếp theo từ service B nếu cursor không có semantics chung.
- Với aggregate nhiều nguồn, định nghĩa rõ cách pagination được áp dụng cho từng collection.

Nếu kết hợp nhiều danh sách độc lập, response nên trả cursor/nextPage riêng cho từng section hoặc tách endpoint khi cần cuộn độc lập. Một cursor chung chỉ hợp lý khi backend có read model hoặc query plan bảo đảm thứ tự và tính nhất quán chung.

## 12. Bảo mật và quyền truy cập trong BFF

BFF nằm gần client, nhận đầu vào không đáng tin cậy và tổng hợp dữ liệu từ nhiều domain. Nếu authorization chỉ được thực hiện ở API gateway dựa trên đăng nhập, có thể xảy ra lỗi **Broken Object Level Authorization (BOLA)**: người dùng đã đăng nhập nhưng yêu cầu bookingId của người khác.

Các nguyên tắc:

1. **Xác thực caller:** xác minh token/session, issuer, audience, expiry và chữ ký.
2. **Xác thực đối tượng:** kiểm tra caller có quyền xem resource cụ thể, không chỉ có role chung.
3. **Tenant isolation:** tenant context phải được ràng buộc từ identity đã xác thực, không tin tenantId client tự gửi.
4. **Least privilege service-to-service:** BFF chỉ gọi operation cần thiết; không dùng credential quản trị toàn hệ thống.
5. **Data minimization:** không chuyển trường backend không cần cho UI.
6. **Output encoding và validation:** tránh đưa dữ liệu độc hại vào UI hoặc query downstream.
7. **Rate limiting:** hạn chế fan-out abuse, brute force ID và request quá lớn.
8. **Audit:** ghi nhận truy cập nhạy cảm và hành động quản trị theo chính sách.

### 12.1. User context và service identity

BFF có thể dùng service identity để gọi backend, đồng thời truyền user context được ký/ủy quyền để backend thực hiện authorization nghiệp vụ. Mô hình cụ thể tùy hệ thống: token exchange, on-behalf-of flow hoặc service-to-service auth kết hợp claims đã xác thực.

Không nên truyền raw bearer token của client tới mọi backend nếu không cần, cũng không nên bỏ user context rồi để backend tin mọi yêu cầu từ BFF. Cần có ranh giới tin cậy và kiểm tra token audience/scope.

### 12.2. Bảo vệ response tổng hợp

Một response chứa nhiều domain có nguy cơ gom quá nhiều dữ liệu nhạy cảm vào một endpoint. Nếu log toàn bộ response, cache thiếu phân biệt hoặc BFF trả object nội bộ, phạm vi rò rỉ tăng. Cần schema allowlist, field-level authorization khi cần, log metadata thay vì payload và kiểm tra cache isolation.

## 13. Thiết kế BFF cho nhiều phiên bản client

Web có thể cập nhật tức thì trong khi mobile app cũ tiếp tục tồn tại nhiều tháng. BFF cần quản lý contract và khả năng tương thích.

- Có thể version endpoint hoặc version theo header/content negotiation nếu phù hợp.
- Thêm field optional thường ít phá vỡ hơn đổi tên/xóa field.
- Không trả giá trị mới với ý nghĩa khác cho field cũ.
- Có khoảng thời gian deprecation, đo adoption và thông báo rõ cho client owner.
- Với app cũ, BFF có thể chuyển đổi backend schema mới về contract cũ.
- Tránh duy trì nhiều nhánh legacy vô hạn; có chính sách hỗ trợ version.

BFF làm lớp thích nghi có thể giảm tốc độ lan truyền thay đổi backend tới client, nhưng chính BFF cũng trở thành contract cần version, test và ownership.

## 14. Aggregation, CQRS và read model

Nếu màn hình tổng hợp thường xuyên kết hợp nhiều nguồn và yêu cầu latency thấp, gọi tuần tự hoặc song song nhiều domain service ở mỗi request có thể trở thành nút thắt. **CQRS (Command Query Responsibility Segregation)** và **read model/projection** là lựa chọn khi có nhu cầu đọc tổng hợp ổn định, tải cao hoặc cấu trúc query khác biệt đáng kể với mô hình giao dịch.

Trong mô hình này:

- Domain services tiếp tục sở hữu việc ghi và quy tắc nghiệp vụ.
- Khi domain state thay đổi, service phát sự kiện bền vững theo cơ chế phù hợp.
- Consumer xây read model chứa các trường cần để hiển thị một use case.
- BFF đọc từ read model thay vì fan-out hàng loạt mỗi lần.
- Read model có thể eventual consistent; UI và hành động nhạy cảm cần xử lý freshness đúng.

~~~mermaid
flowchart TB
    B["Booking service"] --> E["Domain events"]
    P["Payment service"] --> E
    D["Delivery service"] --> E
    E --> PROJ["Projection consumer"]
    PROJ --> RM[("Rental details read model")]
    C["Client"] --> BFF["BFF / API"]
    BFF --> RM
~~~

Read model giảm số lần gọi và tăng khả năng tối ưu query, nhưng thêm pipeline đồng bộ, schema, storage, replay và xử lý lag. Không nên tạo projection riêng cho mỗi màn hình nếu các nhu cầu có thể dùng chung một mô hình đọc ổn định.

### 14.1. Khi nào vẫn nên gọi trực tiếp?

Một trang quản trị ít traffic, cần dữ liệu luôn mới và chỉ tổng hợp hai nguồn có thể dùng aggregator trực tiếp. Một dashboard đọc nhiều, tổng hợp hàng chục nguồn và cần latency thấp có thể hợp với projection. Chọn theo **tải, freshness, chi phí, khả năng chấp nhận eventual consistency và độ phức tạp đồng bộ**.

## 15. Tránh N+1 và fan-out tăng theo số phần tử

Một aggregator có thể vô tình tạo N+1: lấy danh sách 50 booking rồi gọi Payment API một lần cho từng booking. Dù client chỉ thực hiện một request, BFF vẫn tạo 51 backend calls.

Cách khắc phục:

- Dùng batch endpoint theo danh sách ID có giới hạn.
- Dùng read model chứa các trường summary thường xuyên hiển thị.
- Cung cấp API list trả đủ trường summary nếu domain owner chấp thuận.
- Áp DataLoader/request cache để gom ID và loại truy vấn trùng.
- Đặt giới hạn fan-out và cảnh báo khi số upstream calls/request tăng bất thường.

Nên đo **upstream calls per client request** như một chỉ số quan trọng. Số request ở edge giảm chưa chắc tổng tải hệ thống giảm.

## 16. Chiến lược lỗi và partial availability

Khi tổng hợp nhiều backend, khả năng hoàn thành phụ thuộc vào những dependency bắt buộc. Nếu một dependency optional lỗi, BFF có thể trả response một phần; nếu dependency critical lỗi, trả lỗi phù hợp.

Phân loại:

| Loại dependency | Hành vi |
| --- | --- |
| Critical cho toàn bộ use case | Fail request có thông tin lỗi và correlation ID |
| Critical chỉ cho thao tác nhạy cảm | Cho phép xem phần khác nhưng disable action hoặc yêu cầu refresh |
| Optional presentation | Trả partial response, placeholder hoặc bỏ section |
| Có cache hợp lệ | Có thể trả stale data nếu contract thể hiện freshness và nghiệp vụ cho phép |

Không trả HTTP 200 với response thiếu dữ liệu quan trọng mà không có metadata. Ngược lại, không làm cả trang lỗi chỉ vì thumbnail không tải được nếu phần đó không bắt buộc.

### 16.1. Retry có chọn lọc

- Không retry lỗi validation, 401/403 hoặc resource not found trừ khi có lý do cụ thể.
- Retry timeout/503/429 theo deadline còn lại và retry policy của dependency.
- Với read request idempotent, retry có thể phù hợp nhưng phải giới hạn.
- Không retry command tạo giao dịch nếu chưa có idempotency key.
- Không cho nhiều lớp (client, BFF, gateway, SDK) retry đồng thời không giới hạn vì có thể nhân số lần gọi.
- Khi downstream quá tải, ưu tiên load shedding và trả lỗi nhanh hơn là tiếp tục fan-out.

## 17. Đo hiệu quả aggregation và BFF

Trước khi tối ưu, cần baseline và mục tiêu.

| Chỉ số | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| Client round trips | Số request client phải gửi cho một use case | Đo giảm tải và độ phức tạp phía client |
| Upstream calls/request | Số request BFF tạo tới backend | Phát hiện fan-out hoặc N+1 |
| End-to-end latency p50/p95/p99 | Trải nghiệm người dùng | So sánh trước/sau aggregation |
| Payload size | Số byte response | Đo over-fetching và chi phí mạng |
| Error/partial response rate | Tỷ lệ use case thiếu dữ liệu/lỗi | Đánh giá độ tin cậy và dependency |
| Cache hit/staleness | Hiệu quả cache và độ cũ dữ liệu | Điều chỉnh TTL và invalidation |
| Cost per successful use case | Chi phí để hoàn thành một hành trình | Bao gồm BFF, backend, cache, log và transfer |
| CPU/memory/concurrency | Năng lực BFF | Định cỡ và autoscale |

Ví dụ mục tiêu sản phẩm giả định: trang chi tiết đơn thuê giảm từ 6 client requests còn 1, p95 từ 900 ms xuống dưới 500 ms và payload dưới 150 KB. Đây chỉ là mục tiêu minh họa; phải kiểm tra số liệu trước/sau ở cùng loại tải và thiết bị.

Không dùng số request client làm thước đo duy nhất. Nếu BFF giảm client round trip từ 6 xuống 1 nhưng tạo 20 upstream calls, tăng payload gấp đôi và thêm một điểm lỗi, thiết kế có thể không cải thiện hệ thống.

## 18. Ví dụ thiết kế: màn hình tổng quan khách hàng

Giả sử trang chủ mobile cần tên hiển thị, 3 booking sắp tới, trạng thái payment tổng quát, tổng số thông báo chưa đọc và một số sản phẩm gợi ý.

### 18.1. Hợp đồng theo nhu cầu client

Endpoint có thể là GET /mobile/home-summary. Response chỉ gồm:

- Customer display name.
- Tối đa 3 booking sắp tới với trạng thái và thời gian.
- Payment summary cần hiển thị.
- Unread notification count.
- Một danh sách gợi ý giới hạn.
- Metadata về freshness/partial sections nếu có.

Không trả toàn bộ lịch sử booking, dữ liệu thanh toán nhạy cảm, profile đầy đủ hoặc toàn bộ catalog.

### 18.2. Luồng tổng hợp

~~~mermaid
flowchart LR
    M["Mobile app"] --> BFF["Mobile BFF"]
    BFF --> C["Customer summary"]
    BFF --> BK["Upcoming bookings query"]
    BFF --> PY["Payment summary"]
    BFF --> N["Unread notifications"]
    BFF --> R["Recommendation query"]
    BFF --> RESP["Compact mobile response"]
~~~

BFF có thể gọi các query độc lập song song, đặt deadline theo từng nguồn và quy định dữ liệu nào optional. Nếu recommendation lỗi, vẫn trả trang chủ; nếu booking status không lấy được, có thể đánh dấu section unavailable hoặc yêu cầu tải lại tùy yêu cầu sản phẩm.

### 18.3. Tối ưu thêm khi tải tăng

Nếu endpoint này trở thành một trong những API được gọi nhiều nhất, có thể tạo HomeSummary read model cập nhật từ domain events. BFF chỉ đọc một projection và bổ sung dữ liệu biến động cao bằng request riêng nếu cần. Cần theo dõi projection lag và thể hiện freshness trong UI.

### 18.4. Ranh giới command và query

GET home-summary chỉ đọc và tổng hợp. Khi người dùng bấm “Hủy đơn”, BFF chuyển command tới Booking service; Booking kiểm tra quyền, chính sách hủy, trạng thái thanh toán và thực hiện workflow cần thiết. Không để BFF tự ghi vào database Booking chỉ để giảm một lần gọi.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Một endpoint aggregation trả mọi dữ liệu cho mọi client | Payload lớn, quyền rộng, contract khó thay đổi | Tách theo use case hoặc BFF khi có khác biệt thật |
| BFF chứa logic nghiệp vụ cốt lõi | Quy tắc bị nhân bản, kết quả không nhất quán | Để domain service sở hữu invariant và command |
| Chuyển mọi request qua BFF duy nhất | BFF trở thành bottleneck và blast radius lớn | Chọn BFF theo client/ownership, scale và isolate phù hợp |
| Gọi backend tuần tự không cần thiết | Latency cộng dồn | Gọi song song khi độc lập và có concurrency limit |
| Fan-out một call cho mỗi item | N+1, tăng load backend | Batch, projection, DataLoader |
| Response một phần nhưng không đánh dấu | Client hiểu thiếu dữ liệu là dữ liệu rỗng/hợp lệ | Partial metadata và state rõ |
| Cache key bỏ qua tenant/user | Rò rỉ dữ liệu giữa người dùng | Key theo security context và test isolation |
| Cache dữ liệu nhạy cảm quá lâu | Quyết định dựa trên trạng thái cũ | TTL/invalidation theo risk, kiểm tra authoritative state |
| Retry mọi upstream lỗi | Khuếch đại sự cố và tăng chi phí | Deadline, retry budget, load shedding |
| Một cursor dùng cho nhiều nguồn độc lập | Pagination sai hoặc thiếu bản ghi | Cursor riêng hoặc read model có thứ tự chung |
| Chỉ tối ưu số call từ client | Upstream fan-out có thể tăng mạnh | Đo calls per request, latency và cost toàn luồng |
| Không version BFF contract | App cũ hỏng khi backend đổi schema | Compatibility policy, deprecation và adoption metrics |
| Log toàn bộ aggregate response | Rò rỉ nhiều loại dữ liệu cùng lúc | Structured metadata, masking và data minimization |

## 20. Quy trình thiết kế và triển khai

1. **Bắt đầu từ hành trình:** xác định màn hình/use case, client, dữ liệu cần, tần suất và SLO.
2. **Lập dependency map:** các backend nguồn, owner dữ liệu, quyền và latency.
3. **Phân loại critical/optional:** quyết định dependency nào bắt buộc và hành vi lỗi từng phần.
4. **Chọn mẫu:** endpoint aggregation, BFF riêng, gateway composition hay read model/CQRS.
5. **Thiết kế contract:** schema response, projection, pagination, error và version.
6. **Thiết kế bảo mật:** user/tenant context, authorization object-level, service identity và cache isolation.
7. **Tối ưu luồng:** batch, parallelism, request coalescing, cache và giới hạn fan-out.
8. **Đặt timeout/deadline:** budget tổng và từng upstream, retry có chọn lọc, circuit breaker khi cần.
9. **Triển khai IaC/CI/CD:** contract test, compatibility test, rollout và rollback.
10. **Đo lường:** round trip, upstream calls, payload, p95/p99, partial response, cost và SLO.
11. **Tái đánh giá:** chuyển sang read model khi query fan-out/tải/freshness chứng minh cần thiết.

### Checklist nghiệm thu

- [ ] Có use case/client cụ thể biện minh cho endpoint tổng hợp hoặc BFF.
- [ ] Mỗi dữ liệu có nguồn sở hữu và endpoint truy vấn được xác định.
- [ ] Response chỉ chứa trường cần cho client và quyền của caller.
- [ ] Command vẫn được xử lý bởi domain service sở hữu nghiệp vụ.
- [ ] Fan-out, N+1, batch size và concurrency có giới hạn.
- [ ] Timeout/deadline và retry policy được kiểm thử.
- [ ] Partial response có semantics rõ, không biến lỗi thành dữ liệu hợp lệ giả.
- [ ] Cache key bao gồm security context; TTL/freshness phù hợp.
- [ ] Pagination/cursor được xác định cho từng collection.
- [ ] BFF contract có versioning và tương thích client cũ.
- [ ] Trace/correlation bao phủ toàn bộ upstream calls.
- [ ] Đo được latency, payload, upstream calls, lỗi, cache và chi phí toàn use case.

## 21. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Dependency critical/optional đã rõ? Timeout, partial response, fallback và retry có kiểm soát? BFF lỗi có ảnh hưởng nhiều client không? |
| **Bảo mật** | Authorization theo object/tenant có thực hiện? Cache và response có rò dữ liệu? BFF có quyền tối thiểu? |
| **Hiệu quả hiệu năng** | Giảm được round trip thực sự? Upstream fan-out, N+1, payload và p95/p99 có cải thiện? |
| **Tối ưu chi phí** | Có giảm tổng số truy vấn và cost per successful use case? Cache, projection và BFF có chi phí vận hành hợp lý? |
| **Khả năng vận hành** | Có trace theo correlation ID, upstream latency/error, version adoption, partial response và runbook? |

## 22. Bài tập áp dụng

Một ứng dụng thuê xe có màn hình dashboard hiển thị thông tin người dùng, ba chuyến gần nhất, hóa đơn chưa thanh toán, lịch bảo dưỡng và thông báo. Web admin cần thêm dữ liệu kiểm toán; mobile chỉ cần summary nhỏ và có thể hoạt động trên mạng chậm. Payment service đôi khi chậm 1 giây; ảnh phương tiện có thể cache 10 phút.

Hãy thiết kế:

1. Nên dùng một aggregator chung, web BFF và mobile BFF, hay thêm read model? Nêu lý do.
2. Trường dữ liệu nào là critical để render dashboard và trường nào có thể partial?
3. Những call nào có thể song song, call nào phải kiểm tra authoritative state?
4. Cache key và TTL cho ảnh, thông báo, payment summary và dữ liệu chuyến đi nên khác nhau thế nào?
5. Làm sao tránh N+1 khi hiển thị ba chuyến cùng dữ liệu phương tiện và hóa đơn?
6. Bảo vệ dữ liệu kiểm toán để mobile không thể truy cập dù biết endpoint.
7. Đo những chỉ số nào để chứng minh kiến trúc mới giảm latency và tổng tải?

Một phương án có cơ sở có thể dùng BFF riêng khi web/mobile thật sự có nhu cầu khác biệt, batch hoặc projection cho dữ liệu chuyến đi, cache ảnh với TTL, và không đưa payment vào cache dài hạn. Hành động thanh toán hoặc hủy chuyến luôn phải được service nghiệp vụ kiểm tra lại trạng thái mới nhất.

**Điểm cốt lõi:** API aggregation giảm độ phức tạp gọi nhiều nguồn bằng cách tổng hợp dữ liệu cho một use case; BFF định hình hợp đồng theo nhu cầu của client; batching, projection, cache và giới hạn fan-out giúp giảm round trip và tải. Chúng chỉ có hiệu quả khi giữ đúng quyền sở hữu nghiệp vụ, authorization, semantics lỗi và freshness dữ liệu. Một API ít request hơn chưa chắc là một hệ thống tốt hơn; cần đo toàn bộ hành trình từ client tới các nguồn dữ liệu, bao gồm latency, lỗi, payload, chi phí và khả năng vận hành.
