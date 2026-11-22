# Backend for Frontend cho các nhóm trải nghiệm khác nhau

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Cổng API  
> **Trọng tâm:** Thiết kế Backend for Frontend (BFF) để phục vụ những hành trình và nhu cầu dữ liệu khác nhau của web, ứng dụng di động, trang quản trị, đối tác và các nhóm giao diện; hiểu ranh giới giữa BFF, API Gateway và các dịch vụ nghiệp vụ; kiểm soát bảo mật, hiệu năng, ownership và chi phí vận hành.

## 1. Vấn đề: một API chung có thể không tối ưu cho mọi trải nghiệm

Giả sử một nền tảng thương mại điện tử có các dịch vụ **Catalog**, **Pricing**, **Inventory**, **Cart**, **Ordering**, **Payments** và **Notifications**. Nền tảng phục vụ:

- **Ứng dụng web cho khách hàng:** cần trang sản phẩm giàu nội dung, nhiều bộ lọc, đánh giá và thông tin gợi ý.
- **Ứng dụng di động:** cần payload nhỏ, ít round trip, chịu được kết nối thất thường và có thể hiển thị dữ liệu theo từng giai đoạn.
- **Trang quản trị:** cần bảng dữ liệu, thao tác hàng loạt, quyền quản lý, lịch sử và báo cáo.
- **Giao diện đối tác:** cần hợp đồng ổn định, giới hạn truy cập và định dạng dữ liệu phù hợp kênh tích hợp.
- **Màn hình hỗ trợ khách hàng:** cần tìm kiếm đơn, xem tình trạng thanh toán và hành động hỗ trợ có audit.

Nếu tất cả client đều gọi trực tiếp từng microservice, một màn hình có thể tạo hàng chục request, lặp lại logic tổng hợp dữ liệu, gây phụ thuộc vào quá nhiều API nội bộ và khó tiến hóa trải nghiệm. Nếu dồn mọi yêu cầu vào **một backend API chung khổng lồ**, đội phát triển lại phải thương lượng một hợp đồng có nhiều trường tùy chọn, nhiều nhánh theo loại thiết bị và nhịp release khác nhau.

**Backend for Frontend (BFF)** là mẫu kiến trúc đặt một lớp backend chuyên phục vụ **một trải nghiệm frontend hoặc một nhóm trải nghiệm có nhu cầu tương đồng**. BFF điều chỉnh API, dữ liệu, phối hợp lời gọi và những nhu cầu ứng dụng cần thiết cho frontend được giao; các dịch vụ domain bên dưới vẫn sở hữu quy tắc và nguồn dữ liệu nghiệp vụ.

Mục đích của BFF không phải thêm một microservice cho mỗi màn hình. Mục đích là tạo **ranh giới tối ưu cho trải nghiệm người dùng và quyền thay đổi** mà không trộn lẫn logic nghiệp vụ cốt lõi vào giao diện.

### Kết quả học tập

Sau khi học, bạn có thể:

1. Giải thích BFF là gì, vì sao tồn tại và khác API Gateway, GraphQL gateway, domain service hay aggregator tổng quát ở điểm nào.
2. Xác định khi nào nên có BFF riêng cho web/mobile/admin/đối tác, khi nào một BFF chung đủ dùng và khi nào không cần BFF.
3. Thiết kế endpoint theo hành trình frontend, tổng hợp dữ liệu từ nhiều service và kiểm soát latency, lỗi một phần, caching, pagination.
4. Phân định quyền sở hữu giữa UI team, BFF team, platform API Gateway và các domain team.
5. Bảo vệ authentication, authorization, tenant isolation, token handling, dữ liệu nhạy cảm và chống lạm dụng.
6. Quản lý hợp đồng API, contract test, versioning, rollout, telemetry và vận hành nhiều BFF.
7. Chuyển dần một frontend gọi nhiều backend sang BFF có kiểm soát, tránh tạo distributed monolith mới.

## 2. BFF nằm ở đâu trong kiến trúc?

Một thiết kế tham khảo:

~~~text
                           Internet / Internal Network
                                      |
                               [Edge Gateway]
                         TLS, WAF, routing, rate limit
                                      |
                 +--------------------+-------------------+
                 |                    |                   |
                 v                    v                   v
             [Web BFF]          [Mobile BFF]         [Admin BFF]
                 |                    |                   |
                 +--------------------+-------------------+
                                      |
                         +------------+-------------+
                         |            |             |
                         v            v             v
                   [Catalog]       [Pricing]     [Ordering]
                         |            |             |
                         v            v             v
                   Domain data    Domain data    Domain data
~~~

Trên sơ đồ, BFF là **lớp API hướng trải nghiệm**, trong khi các dịch vụ phía dưới là **lớp sở hữu năng lực nghiệp vụ**.

Một request có thể đi như sau:

1. Người dùng mở trang sản phẩm trên web.
2. Trình duyệt gọi **Web BFF** với productId và ngữ cảnh phiên làm việc.
3. Web BFF gọi Catalog để lấy tên/ảnh/mô tả, Pricing để lấy giá hiển thị và Inventory để lấy tình trạng khả dụng.
4. BFF biến đổi, tổng hợp, phân quyền dữ liệu theo hợp đồng của trang web.
5. BFF trả một response tối ưu để frontend render.

Mobile BFF có thể lấy cùng các domain data nhưng trả ít trường hơn, nhóm thông tin khác và có cache policy khác. Admin BFF lại trả trường vận hành, audit hoặc trạng thái kho với quyền mạnh hơn.

**Điểm quan trọng:** không để BFF trở thành nguồn sự thật của sản phẩm, giá, tồn kho hoặc đơn hàng. BFF phục vụ cách hiển thị và điều phối yêu cầu; domain service quyết định ý nghĩa và tính đúng đắn của dữ liệu.

## 3. Phân biệt BFF, API Gateway, aggregator và domain service

Các thành phần này đôi khi cùng thực hiện HTTP routing, nhưng mục tiêu thiết kế khác nhau.

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| **Edge/API Gateway** | Cổng vào chung, TLS, routing, giới hạn lưu lượng, bảo vệ biên, một số chức năng xác thực | Chuyển /mobile/* tới Mobile BFF |
| **BFF** | API gắn với hành trình của một nhóm frontend; tổng hợp, chuyển đổi và chuẩn bị dữ liệu cho UI | GET /mobile/home tổng hợp sản phẩm, giá, banner |
| **API Aggregator chung** | Kết hợp kết quả nhiều API cho nhiều consumer theo contract tương đối tổng quát | API dựng catalog view cho nhiều hệ |
| **Domain service** | Sở hữu quy tắc, mô hình, bất biến và dữ liệu nghiệp vụ | Pricing quyết định báo giá hợp lệ |
| **GraphQL layer** | Cơ chế/schema truy vấn để client chọn trường và mối quan hệ | GraphQL API cho web hoặc mobile |
| **Orchestrator/Workflow** | Sở hữu tiến trình nghiệp vụ dài, trạng thái và bù trừ | Saga đặt hàng giữ kho–thanh toán–giao hàng |

Một BFF có thể được triển khai bằng REST, GraphQL hoặc giao thức khác. **GraphQL không tự động là BFF**, vì một schema có thể phục vụ rất nhiều nhóm client; và BFF không buộc dùng GraphQL.

API Gateway có thể làm một số phép biến đổi nhẹ hoặc routing nâng cao, nhưng không nên chứa hàng loạt quyết định hiển thị từng màn hình. Ngược lại, BFF không nên tự xây một hệ thống WAF, tenant-wide rate limiting, quản lý chứng chỉ hay network policy nếu nền tảng đã cung cấp chức năng ấy.

### 3.1. Ranh giới theo “trải nghiệm”, không theo công nghệ frontend

Tên “Web BFF” và “Mobile BFF” tiện để minh họa, nhưng một hệ thống không nhất thiết phải có một BFF cho từng nền tảng:

- Web và tablet cùng hành trình, cùng hợp đồng và cùng nhịp phát hành có thể dùng **một BFF**.
- Hai ứng dụng web của hai sản phẩm nghiệp vụ khác nhau có thể cần **hai BFF**.
- Ứng dụng iOS và Android có thể dùng chung Mobile BFF nếu nhu cầu đủ giống.
- Trang admin với quyền và quy trình khác biệt thường là ứng viên cho ranh giới riêng.
- Đối tác tích hợp qua API ổn định có thể cần **Partner API** chuyên biệt, không nhất thiết gọi nó là BFF nếu không gắn với một trải nghiệm frontend cụ thể.

Đơn vị thiết kế hữu ích thường là **một nhóm hành trình, tốc độ thay đổi, quyền sở hữu và hợp đồng dữ liệu tương đồng**.

## 4. Vì sao một backend duy nhất cho mọi frontend thường khó phát triển?

### 4.1. “One size fits all” gây payload không phù hợp

Ví dụ web cần:

~~~json
{
  "productId": "p-101",
  "title": "Áo khoác",
  "description": "...",
  "gallery": ["..."],
  "relatedProducts": ["..."],
  "reviews": ["..."],
  "price": "...",
  "inventory": "..."
}
~~~

Mobile trên mạng yếu có thể chỉ cần ảnh đại diện, tên ngắn, giá, tình trạng còn hàng và CTA. Admin cần SKU, lịch sử cập nhật giá, tồn theo kho, người chỉnh sửa và cờ kiểm duyệt. Nếu một endpoint cố trả tất cả rồi đặt hàng chục query flag, hợp đồng dễ trở nên khó hiểu và chứa trường không đúng quyền.

### 4.2. Chênh lệch về hành trình

Web có thể mở trang chi tiết; mobile có thể cần danh sách ngắn tải trước; admin cần bảng có sort/filter mạnh. Cùng một domain data nhưng **shape**, mức chi tiết và cách phân trang khác nhau.

### 4.3. Chênh lệch về release cadence

Ứng dụng web thường được cập nhật tức thì; ứng dụng mobile có thể tồn tại nhiều phiên bản cũ trong nhiều tuần hoặc tháng. BFF riêng giúp quản lý tương thích và chính sách thay đổi phù hợp mà không ép mọi client cùng tốc độ.

### 4.4. Chênh lệch về ownership

Nếu đội Mobile cần chờ đội API chung sửa một trường hiển thị nhỏ, lead time có thể tăng. Một Mobile BFF do nhóm Mobile sở hữu giúp phát triển API phù hợp hành trình nhanh hơn, nhưng vẫn phải tôn trọng hợp đồng domain và chuẩn an toàn của tổ chức.

### 4.5. Chênh lệch về giới hạn tài nguyên và độ trễ

Mobile có thể tối ưu số round trip và kích thước payload; admin ưu tiên độ đầy đủ của dữ liệu và kiểm soát truy vấn nặng. Gộp hai loại request vào một lớp không giới hạn có thể khiến báo cáo admin chậm làm hỏng latency của giao diện khách hàng.

## 5. Khi nào nên dùng BFF và khi nào không?

### Tín hiệu nên cân nhắc

- Một màn hình gọi trực tiếp nhiều API nội bộ, logic ghép dữ liệu được lặp ở các client.
- Web/mobile/admin có những representation khác nhau đáng kể.
- Frontend cần dữ liệu tổng hợp theo màn hình mà domain service không nên sở hữu.
- Client mobile bị ảnh hưởng đáng kể bởi network round trip hoặc payload thừa.
- Đội giao diện cần triển khai/tiến hóa contract theo nhịp riêng.
- Các thông tin từ nhiều nguồn cần được tổng hợp kèm trạng thái lỗi từng phần.
- Cần che topology của microservices khỏi frontend và tránh đưa credential nội bộ tới browser/app.
- Có yêu cầu bảo mật hoặc dữ liệu theo nhóm người dùng khiến contract nên được cô lập.

### Tín hiệu chưa đủ để tạo BFF

- Chỉ có một frontend đơn giản và một backend phù hợp.
- Một màn hình cần gọi thêm đúng một endpoint.
- Dữ liệu và lifecycle của các kênh gần như giống nhau.
- Vấn đề thực là domain service chậm hoặc API contract sai; thêm BFF chỉ giấu vấn đề.
- Đội không có khả năng sở hữu, triển khai và on-call lớp backend mới.
- Gateway hiện tại đã cung cấp mọi định tuyến cần thiết và không có logic tổng hợp đáng kể.

### Một số phương án thay thế

| Phương án | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| Client gọi domain APIs trực tiếp | Ứng dụng nhỏ, hợp đồng ổn định, ít dependency | Nhiều round trip và lộ topology |
| API Gateway + một API chung | Nhiều client có nhu cầu tương đồng | Hợp đồng có thể dần cồng kềnh |
| BFF chuyên cho nhóm trải nghiệm | Nhu cầu, nhịp release hoặc ownership khác nhau | Thêm deployable, contract và vận hành |
| GraphQL API chung | Client cần chọn trường linh hoạt và có governance schema | Chi phí resolver, N+1, giới hạn truy vấn |
| Domain read model/projection | Nhiều consumer cần cùng một mô hình đọc nghiệp vụ ổn định | Cần quản lý consistency và nguồn dữ liệu |
| Server-side rendering/full-stack app | Frontend và backend chặt về vòng đời, UI một nền tảng | Có thể khó tách khi nhiều client ra đời |

BFF là một **tối ưu kiến trúc có giá**. Nên chọn khi lợi ích về trải nghiệm, tốc độ thay đổi và quyền sở hữu vượt chi phí lớp trung gian.

## 6. Xác định số lượng và ranh giới BFF

### 6.1. Phân nhóm theo hành trình và ownership

Hãy lập ma trận:

| Nhóm client | Hành trình chính | Dữ liệu cần | Quyền | Nhịp release |
| --- | --- | --- | --- | --- |
| Customer Web | Tìm sản phẩm, giỏ, đặt đơn | Catalog, price, cart | Customer | Nhanh, mỗi ngày |
| Customer Mobile | Trang chủ, tìm nhanh, đặt đơn | Payload cô đọng, cache | Customer | Version cũ tồn tại lâu |
| Admin Portal | Quản lý sản phẩm, tồn kho, audit | Bảng, lịch sử, thao tác batch | Operator/Admin | Theo lịch vận hành |
| Support Console | Tra đơn, hoàn tiền theo quyền | Order, payment, customer history | Support scopes | Có kiểm soát |
| Partner Client | Đồng bộ đơn, tồn, giá | Contract ổn định, pagination | Partner scopes | Cam kết dài hạn |

Nếu hai hàng gần giống về hành trình, contract, data shape và đội sở hữu, không nhất thiết tách hai BFF. Nếu khác hẳn về quyền, tải, SLO hoặc logic trình bày, tách có thể giảm coupling.

### 6.2. BFF per frontend hay per experience?

“BFF cho mobile” là một khởi điểm dễ hiểu; không nên biến thành quy tắc bất biến. Một app mobile lớn có thể có nhiều **feature teams** với các trải nghiệm và ownership riêng, nhưng tạo một BFF cho mỗi feature cũng có thể gây phân mảnh.

Các lựa chọn:

1. Một BFF chung cho web và mobile, các API có field selection/version rõ.
2. Hai BFF cho Customer Web và Customer Mobile.
3. Một Customer Experience BFF và một Admin BFF.
4. BFF theo product/experience domain thay vì hệ điều hành; mỗi frontend gọi một hoặc vài BFF theo capability rõ ràng.

Chọn phương án làm **đường đi thay đổi** đơn giản nhất mà không tạo nhiều hop hoặc quyền sở hữu chồng chéo.

### 6.3. Không phân tách chỉ vì sơ đồ tổ chức hiện tại

Nếu tổ chức vừa đổi tên team, không cần lập tức đổi topology service. Ranh giới BFF nên dựa trên hành trình, contract và độ độc lập thực tế, sau đó thiết lập owner tương ứng. Tạo một BFF cho mỗi squad nhưng squad nào cũng gọi nhau sẽ tái tạo vấn đề microservice phân mảnh.

## 7. BFF nên làm gì và không nên làm gì?

### Trách nhiệm phù hợp

- **API composition:** gọi nhiều service, tổng hợp kết quả cho một hành trình.
- **DTO/view-model mapping:** đổi cấu trúc dữ liệu cho UI, đặt tên trường và format hợp đồng.
- **Client-specific filtering:** ẩn thông tin không cần trong contract và thực thi truy cập theo quyền.
- **Request orchestration ngắn:** phối hợp các API đọc/ghi trong một tương tác, không giữ trạng thái workflow dài.
- **Performance optimization:** parallel calls, batching, cache phù hợp, giảm payload.
- **Error translation:** đổi lỗi nội bộ thành thông báo ổn định, có lỗi từng phần khi nghiệp vụ cho phép.
- **Session/token handling:** một số mô hình BFF giữ phiên phía server để giảm token phơi lộ ở browser.
- **Feature exposure:** ẩn/hiện một số trường theo version client hoặc feature flag hợp lệ.
- **Observability theo hành trình:** trace end-to-end từ một tương tác frontend tới các backend liên quan.

### Trách nhiệm nên đặt ở domain/service khác

- Tính giá, áp mã giảm, xác nhận tồn kho, hạch toán và bất biến nghiệp vụ.
- Source of truth của Order, Payment, Inventory, Customer.
- Transaction xuyên nhiều bước/giờ; saga hoặc workflow có owner rõ.
- Quy tắc bảo mật cốt lõi của domain chỉ kiểm tra một lần ở BFF.
- Truy vấn trực tiếp bảng dữ liệu của các service khác chỉ để giảm số API call.
- Phát event nghiệp vụ thay cho service sở hữu sự thật.
- Tạo một kho cache mà mọi service phụ thuộc như database trung tâm mới.

**Quy tắc thực dụng:** Nếu logic vẫn cần tồn tại khi thay frontend hoàn toàn, hãy xem nó có thuộc domain/application service thay vì BFF không. Có ngoại lệ đối với hợp đồng tích hợp, nhưng câu hỏi này giúp phát hiện business logic đặt sai chỗ.

## 8. Ví dụ: ba trải nghiệm dùng cùng domain services

Giả sử hệ thống có Catalog, Pricing, Inventory và Recommendations.

### 8.1. Web BFF — trang chi tiết sản phẩm

Một endpoint hướng giao diện:

~~~http
GET /web/v1/products/p-101/page
Authorization: Bearer <session-or-token>
~~~

Response minh họa:

~~~json
{
  "product": {
    "id": "p-101",
    "title": "Áo khoác",
    "description": "Mô tả dành cho trang web",
    "gallery": [
      {"src": "/images/p-101-front.webp", "alt": "Mặt trước"},
      {"src": "/images/p-101-back.webp", "alt": "Mặt sau"}
    ]
  },
  "purchase": {
    "displayPrice": "350.000 ₫",
    "currency": "VND",
    "availability": "IN_STOCK",
    "canAddToCart": true
  },
  "recommendations": [
    {"productId": "p-203", "label": "Bạn có thể thích"}
  ],
  "sections": {
    "reviewsAvailable": true,
    "recommendationsAvailable": true
  }
}
~~~

Web BFF có thể gọi các dịch vụ song song và điều chỉnh presentation fields. Tuy nhiên, giá cuối cùng để thanh toán phải được backend nghiệp vụ xác nhận lại khi đặt đơn. Trường displayPrice chỉ phục vụ trải nghiệm tại một thời điểm, không phải nguồn giá bất biến.

### 8.2. Mobile BFF — thẻ sản phẩm gọn nhẹ

~~~http
GET /mobile/v2/products/p-101/card
X-App-Version: 5.4.0
~~~

~~~json
{
  "id": "p-101",
  "name": "Áo khoác",
  "thumbnail": "/images/p-101-small.webp",
  "priceText": "350.000 ₫",
  "available": true,
  "primaryAction": "ADD_TO_CART",
  "cacheTtlSeconds": 30
}
~~~

Mobile không cần gallery đầy đủ hoặc reviews để render thẻ sản phẩm. BFF có thể trả payload nhỏ, hỗ trợ version cũ, nhưng không nên tin X-App-Version do client tự khai như nguồn quyền hoặc bảo mật.

### 8.3. Admin BFF — bảng vận hành

~~~http
GET /admin/v1/products?status=ACTIVE&page=1&pageSize=20&sort=updatedAt:desc
~~~

~~~json
{
  "rows": [
    {
      "productId": "p-101",
      "sku": "JK-001",
      "title": "Áo khoác",
      "status": "ACTIVE",
      "stockByWarehouse": [
        {"warehouseId": "wh-1", "available": 120},
        {"warehouseId": "wh-2", "available": 40}
      ],
      "lastEditedBy": "operator-18",
      "updatedAt": "2026-11-11T07:20:00Z"
    }
  ],
  "page": 1,
  "pageSize": 20,
  "totalElements": 235
}
~~~

Admin BFF có thể trả thông tin vận hành và hỗ trợ thao tác batch. Nhưng **quyền được xem/sửa sản phẩm** phải được xác thực, phân quyền rõ ở BFF và được domain service kiểm soát ở ranh giới tin cậy của chính nó.

### 8.4. Ba response khác nhau không có nghĩa ba bản sao nghiệp vụ

BFF chỉ định hình payload. Catalog vẫn quyết định sản phẩm có thể bán không, Pricing quyết định giá, Inventory sở hữu tồn kho. Nếu Web BFF tính một kiểu giảm giá còn Mobile BFF tính một kiểu khác, đó là tín hiệu logic nghiệp vụ đã bị đặt sai tầng.

## 9. Thiết kế API theo hành trình thay vì sao chép các microservice

Một cách phân biệt:

~~~text
API theo domain service:
  GET /catalog/products/{id}
  GET /pricing/prices?productId=...
  GET /inventory/availability?productId=...
  GET /reviews?productId=...

API theo trải nghiệm:
  GET /web/products/{id}/page
  GET /mobile/products/{id}/card
~~~

BFF có thể tổng hợp kết quả trong một request, giúp frontend không biết topology nội bộ và giảm số kết nối mạng từ thiết bị tới nhiều dịch vụ.

### 9.1. Không nhất thiết một endpoint cho mỗi màn hình

Tạo endpoint /screen/1, /screen/2 cho mọi màn hình có thể dẫn tới backend chặt với từng layout nhỏ. Một API trải nghiệm tốt nên tập trung vào **use case có ngữ nghĩa**: homepage, product summary, checkout preview, order timeline. Trường hợp nhiều giao diện cùng dùng dữ liệu, có thể cung cấp view-model hoặc fragment API được quản lý rõ.

### 9.2. Phân biệt read composition và write command

- **Read composition:** thường dễ tổng hợp, song song hóa và chấp nhận một số phần dữ liệu thiếu nếu UI có degradation policy.
- **Write command:** cần một owner nghiệp vụ, kiểm tra tính hợp lệ, idempotency và kết quả đúng. BFF nên gọi một application/domain operation phù hợp hơn là tự đóng vai coordinator cho nhiều service mà không có transaction/workflow được thiết kế.

Ví dụ, BFF không nên gọi Pricing để đọc giá, Inventory để trừ kho và Payments để thu tiền trong ba lời gọi riêng lẻ rồi tự kết luận “Đặt hàng thành công”. Đây là luồng nghiệp vụ cần một application/service hoặc workflow owner chịu trách nhiệm trạng thái và bù trừ.

## 10. API composition, fan-out và ngân sách độ trễ

### 10.1. Fan-out nối tiếp có thể làm UI chậm

Giả sử BFF cần Catalog, Pricing, Inventory và Recommendations.

~~~text
Sequential:
  Catalog 60 ms --> Pricing 80 ms --> Inventory 50 ms
       --> Recommendations 100 ms --> mapping 10 ms

Tổng khoảng 300 ms chưa tính overhead.
~~~

Nếu các nguồn không phụ thuộc nhau, BFF có thể gọi song song:

~~~text
Parallel:
   +--> Catalog 60 ms ----------+
   +--> Pricing 80 ms ----------+
   +--> Inventory 50 ms --------+--> map response
   +--> Recommendations 100 ms -+
~~~

Trong một trường hợp lý tưởng, độ trễ phần downstream có thể xấp xỉ bước chậm nhất cộng overhead, thay vì tổng các bước. Nhưng thực tế bị ảnh hưởng bởi connection pool, tài nguyên, tail latency, giới hạn đồng thời, cache và các dependency không thể chạy song song.

**Không cộng đơn giản các p95 service để dự đoán p95 end-to-end**; nên đo trace thực và phân phối latency.

### 10.2. Tính latency budget

Ví dụ giả định:

| Phần | Mức dự trù |
| --- | ---: |
| Network từ client tới edge | 100 ms |
| Gateway + auth | 40 ms |
| BFF xử lý + serialization | 40 ms |
| Downstream fan-out | 180 ms |
| Dự phòng | 40 ms |
| **Tổng mục tiêu** | **400 ms** |

Mục tiêu chỉ để minh họa. Mỗi lời gọi cần deadline/timeout nằm trong ngân sách còn lại; không dùng timeout 5 giây cho mọi service nếu UX chỉ cho phép chờ 400 ms.

### 10.3. Giới hạn concurrency và bulkhead

Nếu một request BFF gọi bốn backend, 1.000 request đồng thời có thể tạo hàng nghìn downstream calls. Không nên scale BFF chỉ dựa vào số request đến mà bỏ qua **fan-out factor** và capacity backend.

Cần cân nhắc:

- Giới hạn concurrent in-flight calls cho từng downstream.
- Connection pool, keep-alive và HTTP/2 multiplexing phù hợp.
- Bulkhead riêng cho dependency chậm hoặc tính năng tùy chọn.
- Admission control/backpressure khi downstream đã bão hòa.
- Batching khi nhiều item cùng cần truy vấn một capability.
- Circuit breaker và lỗi ổn định khi dependency mất khả dụng.
- Cache phù hợp để tránh lặp lại dữ liệu tham chiếu.

### 10.4. Retry có thể khuếch đại tải

Nếu client retry một lần, BFF retry hai lần và gateway cũng retry, một thao tác có thể tạo nhiều attempt hơn dự kiến. Đặt retry policy ở lớp phù hợp, giới hạn retry budget toàn đường đi, dùng backoff/jitter khi cần và tránh retry tự động các thao tác có tác dụng phụ khi không có idempotency.

## 11. Xử lý lỗi một phần và trải nghiệm suy giảm có kiểm soát

Không phải nguồn dữ liệu nào cũng có mức quan trọng như nhau.

Ví dụ trang sản phẩm:

- **Catalog** không có dữ liệu: không thể hiển thị sản phẩm, nên trả lỗi hoặc Not Found theo contract.
- **Pricing** không trả giá: có thể hiển thị thông tin sản phẩm nhưng vô hiệu hóa mua hàng, không tự bịa giá.
- **Inventory** không phản hồi: có thể hiển thị “Chưa xác định tồn kho” và khóa thao tác giữ hàng theo chính sách.
- **Recommendations** lỗi: có thể ẩn khối gợi ý mà không làm hỏng trang.

Một response có thể biểu diễn trạng thái từng phần:

~~~json
{
  "product": {"id": "p-101", "title": "Áo khoác"},
  "purchase": {
    "status": "UNAVAILABLE",
    "message": "Chưa thể xác nhận giá hoặc tồn kho."
  },
  "recommendations": [],
  "meta": {
    "degraded": true,
    "unavailableSections": ["recommendations"]
  }
}
~~~

Nếu chỉ Recommendations lỗi, BFF có thể trả HTTP 200 với dữ liệu cốt lõi còn đúng. Nếu Pricing lỗi khiến thao tác mua không an toàn, phải chuyển UX sang trạng thái phù hợp. HTTP status cho kết quả hỗn hợp tùy hợp đồng; không phải mọi partial failure đều bắt buộc dùng 206 hoặc 207.

**Quy tắc:** degrade chỉ được phép khi không tạo ra lời hứa sai về nghiệp vụ. BFF không được tự đặt “còn hàng” hoặc “thanh toán thành công” chỉ để UI không lỗi.

### 11.1. Fallback data

Cache dữ liệu cũ có thể hợp lý cho ảnh, mô tả hoặc danh sách gợi ý. Với giá, tồn kho hay hạn mức, cần quy tắc freshness, version và việc hiển thị “chỉ tham khảo” nếu nghiệp vụ cho phép. Một cache stale vô hạn có thể gây hậu quả nghiêm trọng.

### 11.2. Phân biệt lỗi user-facing và lỗi nội bộ

Client nên nhận error code ổn định, message dễ hiểu, requestId và hướng xử lý. BFF/trace nội bộ giữ dependency, status, retry count và stack trace. Không trả trực tiếp địa chỉ nội bộ, token hoặc thông tin nhạy cảm từ downstream.

## 12. BFF và bảo mật: không chỉ là “proxy có token”

### 12.1. Authentication và authorization là hai trách nhiệm khác nhau

- **Authentication:** ai đang gọi? Session/cookie/token có hợp lệ không?
- **Authorization:** người đó được làm gì trên resource nào?
- **Tenant isolation:** resource thuộc tenant nào, có thể đọc/ghi bởi chủ thể nào?

Gateway có thể xác minh một số token hoặc chính sách biên. BFF có thể kiểm tra quyền theo trải nghiệm và tránh trả trường nhạy cảm. Nhưng domain service vẫn phải bảo vệ tài nguyên, không mặc định rằng mọi request từ BFF đều đáng tin.

Ví dụ Admin BFF không nên chỉ ẩn nút “Hoàn tiền” trên giao diện; API xử lý refund phải thực thi authorization phía server, và Payments cần bảo vệ command tại ranh giới của mình.

### 12.2. Browser BFF và session

Một mẫu kiến trúc với ứng dụng web là BFF giữ access token phía server và trình duyệt chỉ giữ session cookie có thuộc tính phù hợp như Secure, HttpOnly, SameSite tùy use case. Điều này có thể giảm việc lộ OAuth token trực tiếp trong JavaScript.

~~~text
Browser
  |
  | session cookie
  v
Web BFF
  |
  | backend credential / delegated token
  v
Domain APIs
~~~

BFF phải bảo vệ CSRF khi dùng cookie, session fixation, logout, rotation, thời hạn phiên, storage, quy tắc CORS và redirect. Không coi HttpOnly cookie là lời giải cho mọi rủi ro XSS hay CSRF.

### 12.3. Mobile BFF và token-based flows

Ứng dụng mobile thường dùng token lưu trong cơ chế bảo vệ phù hợp thiết bị, gọi API qua TLS và có vòng đời refresh/token rotation theo chuẩn của hệ thống. BFF cần xác thực token, bảo vệ quyền và có thể đổi token/định danh sang dạng phù hợp cho downstream, nhưng không nên lưu long-lived user credential trong message hoặc log.

### 12.4. Downstream authorization

Có vài phương án, tùy trust model:

- BFF chuyển tiếp token người dùng nếu phù hợp audience/scope của dịch vụ đích.
- BFF dùng token exchange hoặc delegated credential phù hợp.
- BFF dùng workload identity cùng claims đã được xác thực, downstream kiểm tra quyền theo resource.
- BFF dùng service credential cho thao tác nội bộ được giới hạn, không thay thế quyền người dùng khi quyết định nhạy cảm.

Không truyền nguyên một “isAdmin=true” do client cung cấp rồi để downstream tin ngay. Cần phân biệt danh tính dịch vụ và danh tính người dùng cuối, có trace/audit phù hợp.

### 12.5. Các rủi ro đặc thù của BFF

- **Over-fetching dữ liệu nhạy cảm:** lấy toàn bộ Customer object rồi vô tình serialize sang mobile.
- **Confused deputy:** BFF có quyền rộng thay mặt người dùng không đủ quyền.
- **SSRF:** BFF nhận URL từ client rồi fetch tới internal network.
- **Mass assignment:** UI gửi các trường admin mà BFF forward nguyên vẹn sang domain command.
- **Cache leakage:** cache response cá nhân nhưng key không bao gồm principal/tenant.
- **Cross-tenant aggregation:** ghép dữ liệu của nhiều nguồn mà bỏ qua tenant filter.
- **Excessive fan-out:** attacker dùng một request rẻ để tạo hàng trăm downstream calls.
- **Debug leakage:** log token, cookie hoặc toàn bộ response chứa PII.

BFF cần input validation, explicit DTO, authorization, rate limiting, response filtering và cache isolation.

## 13. Caching, dữ liệu hiển thị và tính nhất quán

BFF có thể cache để tối ưu trải nghiệm, nhưng cache phải phù hợp với **ngữ nghĩa dữ liệu**.

| Dữ liệu | Định hướng cache | Điều cần kiểm soát |
| --- | --- | --- |
| Danh mục, ảnh, văn bản tĩnh | CDN/edge cache, TTL tương đối dài | Version, invalidation |
| Gợi ý sản phẩm không cá nhân hóa | TTL ngắn/trung bình | Freshness, kích thước cache |
| Giá hiển thị | Cache ngắn khi được domain chấp nhận | Campaign/version, không dùng để thu tiền |
| Tồn kho | Rất thận trọng hoặc cache ngắn | Race với đặt hàng, trạng thái “tham khảo” |
| Giỏ hàng cá nhân | Cache theo user/session, khi cần | Không rò giữa các user, write consistency |
| Thông tin admin/audit | Thường yêu cầu freshness/quyền rõ | Tenant, permission, dữ liệu nhạy cảm |
| Báo cáo lịch sử | Có thể dùng result store/cache | Dữ liệu tại thời điểm tạo báo cáo |

Cache key cần xem xét locale, currency, tenant, user segment, authorization scope và version. Không phải mọi tham số đều nên nhét vào key: phải cân đối rủi ro rò dữ liệu và cardinality.

### 13.1. Cache ở đâu?

Có thể cache tại CDN, edge, BFF memory, distributed cache hoặc domain/read model. Đặt cache ở BFF khi BFF biết rõ representation và nhu cầu trải nghiệm; đặt ở domain khi cache thuộc sự thật nghiệp vụ hoặc nhiều consumer có thể chia sẻ chính sách.

Nếu một dữ liệu quan trọng được cache ở cả gateway, BFF và domain mà không có quy tắc version/invalidation, việc debug dữ liệu cũ rất khó.

### 13.2. Read-your-writes

Người dùng vừa cập nhật địa chỉ, chuyển sang màn hình xem chi tiết và thấy địa chỉ cũ từ projection/cache. BFF cần hiển thị trạng thái đang đồng bộ hoặc đọc từ nguồn có cam kết thích hợp, nếu hành trình cần read-your-writes. Không tự “vá” dữ liệu bằng cách giữ state bí mật trong BFF lâu dài nếu domain owner chưa xác định consistency contract.

## 14. BFF và GraphQL

Một GraphQL BFF có thể cho frontend chọn trường cụ thể:

~~~graphql
query ProductPage($id: ID!) {
  product(id: $id) {
    id
    title
    displayPrice
    availability
    recommendations {
      id
      title
    }
  }
}
~~~

Resolvers có thể gọi Catalog, Pricing, Inventory và Recommendations. GraphQL giúp client chọn shape, nhưng không tự giảm số request downstream hoặc đảm bảo performance. Nếu mỗi recommendation gọi Pricing riêng, có thể xuất hiện **N+1 requests**.

### 14.1. Các điểm cần thiết kế

- Batching/DataLoader cho truy vấn lặp.
- Query depth và complexity limit.
- Pagination/cursor và giới hạn dữ liệu.
- Authentication/authorization tới từng field nhạy cảm.
- Persisted queries và schema governance.
- Cache và response/error semantics.
- Federation nếu có nhiều graph owner, nhưng phải quản lý coupling và boundary rõ.

### 14.2. Khi nào REST BFF đủ tốt?

Nếu trải nghiệm có một số use case ổn định như homepage, cart summary, checkout preview, REST endpoint hướng màn hình có thể đơn giản hơn. Chọn GraphQL khi client thật sự cần linh hoạt shape và team có khả năng vận hành resolver/schema; không dùng GraphQL chỉ để gọi hệ thống “hiện đại”.

## 15. BFF với frontend server-side rendering

Các ứng dụng web hiện đại có thể kết hợp routing, server components hoặc server-side rendering (SSR) trong cùng runtime. Logic phục vụ frontend ở server đôi khi đã thực hiện các vai trò tương tự BFF: kiểm tra session, gọi domain APIs và tạo view model.

Câu hỏi cần trả lời:

- Đây là **BFF logic** nằm chung deployable với web hay là một service riêng?
- Có bao nhiêu client cùng cần API này?
- Chia lifecycle giúp release độc lập hay chỉ tăng network hop?
- Có nhu cầu version hợp đồng ổn định ngoài SSR app không?
- Ai sở hữu route, authorization, caching, tracing và deployment?

Một BFF không nhất thiết phải là microservice riêng. Với một frontend nhỏ, **frontend server + server-side API layer** có thể là đơn vị phù hợp nhất. Với ứng dụng mobile và partner dùng API chung, một BFF độc lập có thể có lợi hơn.

## 16. Ownership và cấu trúc nhóm phát triển

Một mục tiêu quan trọng của BFF là giảm sự phụ thuộc thay đổi giữa frontend và domain.

### Mô hình ownership tham khảo

| Thành phần | Owner chính | Trách nhiệm |
| --- | --- | --- |
| Customer Web UI + Web BFF | Web experience team | UX, view contract, client latency |
| Mobile UI + Mobile BFF | Mobile experience team | App version compatibility, payload, mobile UX |
| Admin UI + Admin BFF | Operations product team | Admin workflows, scopes, audit UX |
| Edge Gateway/platform | Platform/security team | TLS, routing chung, network controls |
| Catalog/Pricing/Ordering | Domain teams | Domain API, invariant, data ownership |

BFF và frontend có thể cùng backlog, acceptance criteria và release planning. Nhưng việc gọi domain APIs phải tuân theo hợp đồng công khai, không bypass vì “cùng công ty”.

### 16.1. Dấu hiệu ownership chưa ổn

- Thay đổi một trường giao diện phải chờ nhiều team vì BFF chung quá lớn.
- Mọi business rule được sao chép vào nhiều BFF.
- BFF có DB riêng chứa bản sao trạng thái nghiệp vụ nhưng không có data owner rõ.
- Không biết ai trực incident khi UI lỗi do một upstream chậm.
- Cùng một đội phải deploy năm BFF mỗi khi có thay đổi contract nhỏ.
- Không có governance cho phiên bản mobile cũ hoặc consumer ngoài tổ chức.

Có thể cần hợp nhất BFF, chuyển logic về domain service hoặc xây shared client library nhỏ. **Tái sử dụng logic kỹ thuật** qua thư viện không có nghĩa chia sẻ một “shared-BFF monolith” khổng lồ.

## 17. Thiết kế domain API để nhiều BFF cùng sử dụng

Nếu Pricing chỉ phục vụ Web BFF, Mobile BFF có thể phải gọi một endpoint quá gắn với web. Domain API nên biểu diễn **khả năng nghiệp vụ**, không phải layout một client.

~~~text
Pricing domain capability:
  POST /v1/quotes
  GET  /v1/products/{id}/current-price

Web BFF:
  GET /web/products/{id}/page

Mobile BFF:
  GET /mobile/products/{id}/card
~~~

Domain contract nên ổn định theo quy tắc business; BFF contract có thể thay đổi theo trải nghiệm với tính tương thích cần thiết.

### 17.1. Không tạo “BFF gọi BFF” thành chuỗi mặc định

~~~text
Không mong muốn:
Mobile --> Mobile BFF --> Web BFF --> Generic BFF
                               --> Pricing
~~~

Chuỗi này làm tăng latency, ownership lẫn lộn và release coupling. Hai BFF nên cùng dùng domain APIs hoặc một application service/read model có trách nhiệm rõ nếu logic tổng hợp thực sự tái sử dụng.

### 17.2. Phần tổng hợp nào nên chia sẻ?

Nếu hai BFF đều xây **cùng một khái niệm nghiệp vụ** như “eligible promotion for cart”, cần xem nên đưa vào Pricing/Promotions application API. Nếu chỉ cùng format tiền theo locale, có thể chia sẻ thư viện chuẩn hoặc utility nhỏ. Nếu cả hai cùng cần danh sách sản phẩm đã chuẩn hóa từ nhiều nguồn, cân nhắc read model/aggregator với owner độc lập khi có giá trị thực.

Đừng chuyển mọi thứ thành shared library nặng khiến BFF phải nâng cấp đồng loạt; tái sử dụng cũng có chi phí.

## 18. Ví dụ Java/Spring: Web BFF tổng hợp dữ liệu

Ví dụ dưới đây minh họa kiến trúc và cách tư duy, không phải một dự án production-ready.

### 18.1. Các interface adapter

~~~java
public interface CatalogGateway {
    ProductDetails getProduct(String productId);
}

public interface PricingGateway {
    ProductPrice getPrice(String productId, String currency);
}

public interface InventoryGateway {
    Availability getAvailability(String productId);
}

public interface RecommendationGateway {
    List<Recommendation> suggest(String productId);
}
~~~

Cách này tách API BFF khỏi HTTP client cụ thể và giúp test độc lập. Adapter có trách nhiệm authentication, timeout, error mapping, tracing và không truy cập bảng dữ liệu riêng của downstream.

### 18.2. Application service tổng hợp read-only

~~~java
public final class ProductPageFacade {
    private final CatalogGateway catalog;
    private final PricingGateway pricing;
    private final InventoryGateway inventory;
    private final RecommendationGateway recommendations;

    public ProductPageFacade(
            CatalogGateway catalog,
            PricingGateway pricing,
            InventoryGateway inventory,
            RecommendationGateway recommendations) {
        this.catalog = catalog;
        this.pricing = pricing;
        this.inventory = inventory;
        this.recommendations = recommendations;
    }

    public ProductPageView build(String productId, String currency) {
        // Ví dụ giản lược. Production nên xem xét gọi song song
        // với deadline, bulkhead và cancellation phù hợp.
        ProductDetails product = catalog.getProduct(productId);
        ProductPrice price = pricing.getPrice(productId, currency);
        Availability stock = inventory.getAvailability(productId);

        List<Recommendation> related;
        try {
            related = recommendations.suggest(productId);
        } catch (RecommendationsUnavailableException ex) {
            // Cho phép degraded mode vì recommendations là tùy chọn.
            related = List.of();
        }

        return ProductPageView.from(product, price, stock, related);
    }
}
~~~

Không bắt mọi lỗi thành “trả danh sách rỗng”; ví dụ chỉ degrade Recommendations đã được xác định là thành phần tùy chọn. Nếu Catalog/Pricing lỗi, phải map sang trạng thái phù hợp. Việc bắt Exception quá rộng hoặc nuốt lỗi sẽ che sự cố thực.

### 18.3. API controller

~~~java
@RestController
@RequestMapping("/web/v1/products")
public final class ProductPageController {
    private final ProductPageFacade facade;

    @GetMapping("/{productId}/page")
    public ProductPageView getPage(
            @PathVariable String productId,
            @RequestParam(defaultValue = "VND") String currency) {
        return facade.build(productId, currency);
    }
}
~~~

Trong một BFF thật, cần có security filter/middleware, request validation, input length limits, localization, rate limit và correlation ID. Chỉ vì endpoint chạy được không có nghĩa nó an toàn.

### 18.4. Gọi song song với deadline

Có thể dùng CompletableFuture, reactive client hoặc structured concurrency tùy Java/runtime, nhưng cần bảo đảm:

- Tổng thời gian chờ có deadline.
- Mỗi downstream call có timeout riêng.
- Không tạo thread không giới hạn cho mỗi request.
- Future bị hủy không đồng nghĩa remote request đã dừng.
- Context tracing/security được truyền đúng.
- Không dùng một global executor chung cho workload có mức ưu tiên quá khác.
- Retry không nhân cấp số attempt ở nhiều lớp.

Pseudo-code:

~~~java
var productFuture = async(() -> catalog.getProduct(productId));
var priceFuture   = async(() -> pricing.getPrice(productId, currency));
var stockFuture   = async(() -> inventory.getAvailability(productId));

awaitAllWithinDeadline(productFuture, priceFuture, stockFuture);
return mapView(productFuture, priceFuture, stockFuture);
~~~

Đây là **pseudo-code** để diễn tả pattern, không phải API Java chuẩn. Trong code thật cần đóng vòng đời task, propagate lỗi có phân loại, cancel đúng cách và đo performance.

## 19. Versioning khi web và mobile thay đổi khác nhịp

### 19.1. Web BFF có thể tiến hóa nhanh hơn

Nếu web bundle và Web BFF cùng được triển khai, có thể phối hợp feature release hoặc dùng expand-contract: thêm field mới trước, chuyển UI, sau đó xóa field cũ khi không còn consumer. Kể cả cùng team, CDN cache và browser tab cũ vẫn có thể tồn tại; không nên mặc định “web không cần backward compatibility”.

### 19.2. Mobile cần hỗ trợ client cũ

App đã phát hành có thể tồn tại ngoài cửa hàng ứng dụng lâu hơn backend. Có thể cần:

- API version theo path/header hoặc contract version được quản lý.
- Thời hạn hỗ trợ và số phiên bản đang dùng.
- Feature negotiation và default cho field tùy chọn.
- Cơ chế buộc cập nhật chỉ khi thật sự cần và có thông điệp rõ.
- Telemetry phân bổ lưu lượng theo phiên bản để quyết định sunset.

Không thiết kế BFF có hàng trăm nhánh if theo appVersion mà không có kế hoạch dọn. Chọn version boundary phù hợp, adapter theo compatibility layer và hợp đồng được kiểm thử.

### 19.3. Domain API version và BFF API version không bắt buộc trùng nhau

~~~text
Mobile app 5.x --> Mobile BFF v2 --> Pricing API v3
Web app latest --> Web BFF v1   --> Pricing API v3
~~~

BFF có thể che một phần thay đổi nội bộ với client nhưng không nên che những thay đổi ngữ nghĩa nghiệp vụ bằng cách trả dữ liệu sai hoặc ngầm chuyển đơn vị tiền tệ.

## 20. Testing: kiểm thử contract và hành trình

### 20.1. Các lớp kiểm thử

| Lớp | Mục đích | Ví dụ |
| --- | --- | --- |
| Unit test | Mapping/branching ở BFF | Pricing unavailable khiến nút mua bị vô hiệu |
| Contract test (frontend–BFF) | Hợp đồng client mong đợi | Các trường bắt buộc của product card |
| Contract test (BFF–domain) | Gọi đúng API upstream | Phiên bản quote response |
| Integration test | Nhiều adapter và security chạy cùng | Request qua gateway/BFF/test doubles |
| E2E | Hành trình người dùng thực tế | Mở trang sản phẩm → giỏ → checkout |
| Load/performance | Latency, fan-out và giới hạn tài nguyên | 1.000 requests đồng thời tới product page |
| Fault injection | Degraded mode và resilience | Recommendations timeout, Pricing 503 |
| Security test | AuthZ, tenant isolation, cache leakage | User khác không được xem đơn hàng |
| Compatibility test | Mobile/web version cũ | App 5.2 vẫn đọc response hợp lệ |

Không nên chỉ test API 200 OK. Cần test **business semantics của UI**, ví dụ sản phẩm thiếu giá thì nút mua có trạng thái an toàn.

### 20.2. Consumer-driven contract tests

Frontend team có thể mô tả các field/mã lỗi cần từ BFF; BFF có contract tương ứng với domain services. Những thay đổi phá hợp đồng phải được phát hiện sớm trong CI. Tuy nhiên, contract test không thay performance test hoặc thử nghiệm với dữ liệu nghiệp vụ thật.

### 20.3. Mock và test doubles

Khi test Web BFF, có thể stub downstream Catalog/Pricing. Nhưng nếu mock phản ánh API cũ, test BFF vẫn xanh trong khi production lỗi. Do đó cần contract test với schema thật và một số integration test xuyên ranh giới.

## 21. Observability theo từng trải nghiệm

Một BFF thêm hop nhưng cũng tạo điểm thuận lợi để đo **hành trình frontend**, miễn không chỉ theo dõi HTTP success.

### 21.1. Metrics nên có

- Latency p50/p95/p99 theo BFF route và client version.
- Tỷ lệ 4xx/5xx, phân biệt invalid input, auth và upstream failure.
- Tỷ lệ degraded response theo phần dữ liệu.
- Tần suất call downstream, fan-out count, timeout, retry attempt.
- Cache hit/miss và stale response rate nếu đo được.
- Throughput, CPU, memory, connection pool saturation.
- Payload response size, compression ratio và số round trip từ client.
- Thời gian trang web/mobile đạt trạng thái tương tác mong muốn.
- Tỷ lệ API version cũ để phục vụ kế hoạch sunset.

### 21.2. Distributed tracing

~~~text
Trace: GET /web/products/p-101/page
   |
   +-- Edge Gateway
   +-- Web BFF /page
         |
         +-- Catalog GET product
         +-- Pricing GET current price
         +-- Inventory GET availability
         +-- Recommendations GET related
   |
   +-- Compose response
~~~

Một trace hữu ích phải cho biết route nào tốn thời gian, backend nào lỗi và BFF đã degrade ra sao. Gắn correlation ID từ client tới downstream theo chuẩn telemetry, đồng thời tránh ghi token, cookie và PII trong span attributes.

### 21.3. SLO riêng cho từng BFF

Ví dụ minh họa, không phải mặc định:

- Web Product Page: 95% BFF requests hoàn tất dưới 300 ms.
- Mobile Home: 99% payload dưới mức dung lượng đã xác định cho thiết bị/mạng mục tiêu.
- Admin Search: 95% bảng tìm kiếm phản hồi dưới 1,5 giây với query hợp lệ.
- Tỷ lệ fallback do Recommendations không vượt ngưỡng đã thống nhất.
- Các route có tác vụ ghi không được tuyên bố thành công khi domain command chưa được xác nhận.

Không gộp mọi route vào một SLO duy nhất: một màn hình admin truy vấn báo cáo lớn có đặc tính rất khác card sản phẩm trên mobile.

## 22. Triển khai, mở rộng và fault isolation

### 22.1. Scale BFF theo profile tải

Web BFF có thể có traffic lớn với nhiều đọc cache; Mobile BFF có payload nhỏ nhưng nhiều phiên bản app; Admin BFF có ít request hơn nhưng truy vấn nặng. Nếu deploy riêng, từng BFF có thể scale và giới hạn tài nguyên theo profile thực.

Nhưng càng nhiều BFF thì càng nhiều pipeline, secret, dashboard, on-call, deployment policy và chi phí khởi tạo. Có thể dùng template/platform chung thay vì sao chép cấu hình thủ công.

### 22.2. Đừng coi BFF là chỗ giữ trạng thái người dùng không giới hạn

Nếu BFF giữ session/token phía server, cần một chiến lược session persistence/replication phù hợp. Business workflow trạng thái dài nên thuộc service có data owner rõ. BFF nên stateless trong chừng mực có thể, hoặc giữ trạng thái session có chủ đích và SLA rõ.

### 22.3. Multi-region và network placement

Đặt BFF gần frontend hoặc gần domain services phụ thuộc có thể tạo trade-off khác nhau:

- Gần client giảm RTT ngoài internet, nhưng có thể tăng cross-region calls tới domain.
- Gần backend giảm latency tổng hợp nhưng client phải đi xa hơn.
- Edge cache phù hợp cho asset/public data, không thay logic riêng tư cần auth.
- Data residency/tenant routing có thể giới hạn nơi BFF được xử lý.
- Multi-region failover cần dữ liệu, identity và capacity, không chỉ DNS.

Đo latency end-to-end trước khi quyết định vị trí đặt BFF.

### 22.4. Chọn một hay nhiều deployable

Một repo có thể chứa nhiều BFF module; một BFF có thể chạy trong cùng runtime SSR app; một số BFF có thể chia shared infrastructure. Quyết định quan trọng là **đơn vị triển khai và trách nhiệm thay đổi có hữu ích hay không**, chứ không phải số repo.

## 23. Anti-pattern cần tránh

| Anti-pattern | Vấn đề | Cách tránh |
| --- | --- | --- |
| **God BFF** phục vụ mọi frontend | Contract cồng kềnh, team phụ thuộc | Nhóm theo trải nghiệm và ownership thực |
| **Một BFF mỗi màn hình** | Bùng nổ deployable và hop | Gom use case cùng vòng đời, tái sử dụng hợp lý |
| **BFF làm business service** | Quy tắc bị nhân bản, dữ liệu sai | Chuyển invariant/source of truth về domain |
| **BFF gọi BFF** thành chuỗi | Latency và release coupling | BFF gọi shared domain capability/read model |
| **Gateway chứa logic UI** | Routing config thành application phức tạp | Tách infrastructure policy khỏi view mapping |
| **BFF truy cập DB domain trực tiếp** | Phá ownership, khó schema evolution | Dùng domain API/event/read model có contract |
| **Quá nhiều fan-out không kiểm soát** | Tail latency và cascade failure | Batch, parallel với deadline, cache, bulkhead |
| **Lạm dụng retry** | Retry storm, side effect trùng | Retry budget, idempotency và telemetry |
| **BFF trả 200 với dữ liệu sai** | UI hiển thị thành công giả | Chỉ degrade phần tùy chọn; giữ business invariant |
| **Một cache cho mọi tenant** | Rò dữ liệu và permission bypass | Key isolation, ACL và TTL đúng |
| **Không quản lý mobile version** | App cũ lỗi sau release BFF | Contract compatibility và sunset policy |
| **Copy toàn bộ DTO domain sang client** | Lộ dữ liệu và coupling model | Explicit view DTO và field filtering |
| **Team BFF không on-call** | Sự cố khó quy trách nhiệm | Owner, SLO, runbook và escalation rõ |
| **Dùng BFF để che API domain kém** | Technical debt tích tụ | Sửa contract/capability ở nơi sở hữu |
| **Không giới hạn request phức tạp** | Một request tạo nhiều backend calls | Rate limit, query complexity, concurrency caps |
| **Không có tracing xuyên hop** | Debug không biết lỗi ở đâu | Correlation, distributed tracing và metrics |

## 24. Kế hoạch migration: từ frontend gọi trực tiếp nhiều service sang BFF

### Giai đoạn 1 — Đo hiện trạng

Thu thập:

1. Danh sách client, màn hình/hành trình và API đang gọi.
2. Số request tới backend cho mỗi tương tác và dung lượng payload.
3. Latency theo mạng, thiết bị, vùng địa lý và client version.
4. Lỗi phụ thuộc, retry, timeout và trải nghiệm khi một service lỗi.
5. Các token/secret đang có trong client và rủi ro quyền truy cập.
6. Owner của từng endpoint và contract, những consumer ngoài phạm vi frontend.
7. Chi phí vận hành hiện tại và thời gian từ yêu cầu UI tới production.

Phát biểu vấn đề bằng bằng chứng, ví dụ: “Trang chi tiết mobile cần tám request tuần tự; trên mạng yếu thời gian tải tăng; client phải hiểu ba service nội bộ”.

### Giai đoạn 2 — Chọn ranh giới và contract

Vẽ target API theo hành trình, ví dụ:

~~~text
Mobile:
   GET /mobile/v1/home
   GET /mobile/v1/products/{id}/card
   POST /mobile/v1/cart/items

Web:
   GET /web/v1/products/{id}/page
   GET /web/v1/cart/summary

Admin:
   GET /admin/v1/products
   PATCH /admin/v1/products/{id}/status
~~~

Chỉ dùng path làm ví dụ; naming convention phải thống nhất với nền tảng. Ghi schema request/response, mã lỗi, pagination, cache và compatibility.

### Giai đoạn 3 — Đặt security và ownership

- Định danh người dùng, session/token, scope và tenant.
- Downstream delegated auth và workload identity.
- Bảo vệ field nhạy cảm và cache key.
- API Gateway routing, TLS, WAF/rate limit.
- Team trực và owner của domain command.

Không nên triển khai BFF như một open proxy có quyền rộng chỉ để nhanh chóng gom call.

### Giai đoạn 4 — Xây một vertical slice

Chọn một màn hình đọc ít rủi ro như product detail. BFF tổng hợp Catalog + Pricing + Inventory với deadline, metric, lỗi từng phần. Frontend có feature flag chuyển qua BFF; đường cũ chưa xóa ngay.

### Giai đoạn 5 — Đối chiếu hiệu năng và hành vi

- So sánh output đúng dữ liệu/permission.
- Đo payload, latency client, BFF và downstream.
- Thử timeout/retry, mất Pricing/Inventory/Recommendations.
- Test mobile version cũ và vùng mạng chậm.
- Đảm bảo cache không lộ dữ liệu người dùng.
- Dùng canary nhỏ và theo dõi SLO.

### Giai đoạn 6 — Chuyển traffic và decommission

Chuyển thêm màn hình theo ưu tiên, không bắt buộc big-bang. Theo dõi client còn gọi API cũ, thống nhất deadline sunset và thông báo tác động. Chỉ gỡ endpoint cũ sau khi xác nhận consumer đã di chuyển, đặc biệt với mobile và partner clients có vòng đời dài.

### Giai đoạn 7 — Cải tiến sau migration

Đánh giá lại ranh giới: có BFF nào trùng quá nhiều logic? API domain nào thiếu một capability dùng chung? Tính năng nào tạo fan-out lớn? Có thực sự cần hai deployable? Kiến trúc nên tiến hóa dựa trên số liệu, không cố giữ mẫu “mỗi frontend một BFF” mãi mãi.

## 25. ADR mẫu cho lựa chọn Web BFF và Mobile BFF

~~~markdown
# ADR: Tách Web BFF và Mobile BFF cho Customer Experience

## Bối cảnh
- Web và mobile cùng dùng Catalog, Pricing, Inventory.
- Mobile cần payload nhỏ và compatibility với nhiều app version.
- Web cần nội dung giàu chi tiết và release nhanh.
- Frontend hiện gọi nhiều API trực tiếp, lặp mapping và auth handling.

## Quyết định
- Duy trì Customer domain APIs làm nguồn dữ liệu/logic nghiệp vụ.
- Tạo Web BFF và Mobile BFF theo hai hợp đồng trải nghiệm.
- API Gateway tiếp tục đảm nhiệm TLS, routing và policy biên.
- BFF tổng hợp dữ liệu, mapping DTO, session/auth đúng phạm vi.
- Không chuyển price calculation, stock reservation hay payment sang BFF.

## Phương án cân nhắc
A. Giữ frontend gọi trực tiếp domain APIs.
B. Một Customer BFF phục vụ cả hai kênh.
C. Hai BFF theo trải nghiệm: Web và Mobile.

## Lợi ích kỳ vọng
- Giảm round trip và payload cho mobile.
- Cải thiện độc lập thay đổi, compatibility và ownership.
- Tránh lộ topology/credential nội bộ cho client.

## Hệ quả
- Tăng số deployable, pipeline, dashboard và hợp đồng.
- Có nguy cơ trùng mapping/logic nếu quản lý kém.
- Cần per-client observability và retry/timeout discipline.

## SLO và kiểm chứng
- Đo latency trên thiết bị và mạng mục tiêu.
- Theo dõi payload size, fan-out, p95/p99, degraded mode.
- Không làm thay đổi business invariant của checkout.
- Contract tests bảo vệ mobile versions đang được hỗ trợ.

## Điều kiện xem lại
- Hai BFF bắt đầu có hợp đồng và release cadence gần như giống nhau.
- Chi phí vận hành lớn hơn lợi ích đã đo.
- Một số composition trở thành domain capability được nhiều consumer cần.
~~~

ADR nên ghi rõ giả định và mất mát khi chọn phương án; đây là bằng chứng giúp đội khác hiểu vì sao lớp BFF tồn tại.

## 26. Bài tập thực hành: BFF cho ứng dụng ngân hàng số

**Bối cảnh:** nền tảng ngân hàng có Account, Transaction, Card, Notification và Fraud services. Người dùng có web và mobile; nhân viên có Operations Portal.

Nhu cầu:

- Mobile Home hiển thị số dư, ba giao dịch gần nhất, trạng thái thẻ và thông báo.
- Web Statement cần lọc giao dịch theo thời gian, xuất file và tra cứu chi tiết.
- Operations Portal cần quyền truy vấn/audit nội bộ và thao tác khóa thẻ được phê duyệt.
- Số dư là dữ liệu cần đúng theo semantics của Account service.
- Tạo statement PDF lớn có thể mất vài phút.
- App mobile cũ phải được hỗ trợ trong một khoảng thời gian đã thỏa thuận.

**Câu hỏi:**

1. Hãy đề xuất số BFF cần thiết và giải thích bằng sự khác biệt hành trình/ownership, không chỉ dựa vào tên thiết bị.
2. Vẽ sơ đồ Mobile Home request, các downstream calls và nguồn dữ liệu nào cần được xem là thiết yếu.
3. Những gì thuộc BFF, những gì vẫn phải thuộc Account/Card/Fraud?
4. Nếu Notification service timeout, Mobile Home có được trả 200 và ẩn thông báo không? Vì sao?
5. Nếu Account service timeout, BFF có được dùng cache số dư của hôm qua không?
6. Thiết kế contract để Operations Portal khóa thẻ mà không chuyển business command trực tiếp tới Card service từ browser.
7. Nêu cách authorize nhân viên theo role, resource và tenant, đồng thời giữ audit trail.
8. Tạo một async job để xuất statement; BFF trả trạng thái nào khi job vừa được nhận?
9. Liệt kê tối thiểu sáu metric đo trải nghiệm mobile và ba metric backend cần theo dõi.
10. Nếu cùng một mapping currency/locale xuất hiện ở nhiều BFF, nên chia sẻ ở đâu để không tạo vòng phụ thuộc?

### Một hướng giải

Một phương án có thể là Mobile Experience BFF, Web Experience BFF và Operations BFF nếu quyền, contract và lifecycle thực sự khác nhau. Mobile Home có thể gọi Account/Transaction/Card song song, Notifications là phần có thể suy giảm, nhưng dữ liệu số dư và quyền truy cập phải được hiển thị đúng chính sách. Operations BFF không được tự quyết định trạng thái khóa thẻ; nó gửi command được xác thực tới Card application service, nơi thực thi quy tắc và audit. Xuất statement lớn có thể trả 202 Accepted với job ID, cho người dùng theo dõi và tải về khi thành công.

Không thể kết luận “mỗi màn hình đều cần BFF riêng”. Cần so sánh phương án một BFF chung với phân tách theo trải nghiệm và chi phí vận hành thực tế.

## 27. Bài tập phân tích ranh giới: BFF hay domain service?

Với mỗi trường hợp dưới đây, xác định logic nên thuộc BFF, domain service, API Gateway hay thành phần khác:

| Tình huống | Gợi ý phân tích |
| --- | --- |
| Format ngày theo locale trên thẻ sản phẩm | View mapping/BFF hoặc frontend tùy hợp đồng |
| Kiểm tra voucher có được áp dụng không | Domain Pricing/Promotions |
| Giới hạn request từ một IP độc hại | Edge/API Gateway/security controls |
| Gộp tên sản phẩm, giá hiển thị, thumbnail vào card | BFF |
| Giữ slot kho trong 10 phút | Inventory/Ordering workflow |
| Ghi lịch sử thao tác hoàn tiền | Payments + Audit owner |
| Chọn version app mobile cũ tương thích | Mobile BFF compatibility layer |
| Gửi thông báo sau khi đơn thành công | Event consumer/Notifications |
| Lấy 20 bản ghi giao dịch để hiển thị | BFF gọi Transaction API và map view |
| Chuyển thời gian tạo báo cáo dài thành job | Reporting application service; BFF trình bày job status |

Điểm rèn luyện là **phân tách ý nghĩa nghiệp vụ khỏi cách trình bày và tương tác**. Một BFF tốt chỉ cần biết đủ về domain để hiển thị và phối hợp yêu cầu, không được tự tạo một mô hình nghiệp vụ song song không có owner.

## 28. Checklist triển khai BFF trong dự án

**Xác định nhu cầu**

- [ ] Có sự khác biệt rõ về hành trình, dữ liệu hoặc nhịp release giữa các nhóm client.
- [ ] Đã so sánh BFF với API Gateway, API chung, GraphQL và read model.
- [ ] Số BFF được chọn dựa trên lợi ích độc lập và chi phí vận hành.
- [ ] BFF không trùng vai trò sở hữu data/invariant với domain services.

**API và hiệu năng**

- [ ] Endpoint/DTO mô tả use case của frontend, không chỉ proxy 1:1 máy móc.
- [ ] Có timeout/deadline end-to-end, fan-out limit và retry budget.
- [ ] Parallel/batch downstream call khi có cơ sở; không tạo N+1 mới.
- [ ] Mỗi dependency có lỗi/fallback policy theo mức quan trọng nghiệp vụ.
- [ ] Cache TTL, key, invalidation và freshness phù hợp loại dữ liệu.
- [ ] Có pagination, payload limit và hỗ trợ phiên bản client cần thiết.

**Bảo mật**

- [ ] AuthN/AuthZ ở đúng ranh giới, domain service không tin mù BFF.
- [ ] Không lộ token, credential, internal URL hoặc PII không cần.
- [ ] Tenant isolation và cache key đã được kiểm thử.
- [ ] Có bảo vệ CSRF/session nếu dùng cookie và giới hạn CORS phù hợp.
- [ ] Có rate limit, quota và chống fan-out abuse.
- [ ] Các command nhạy cảm có audit và idempotency.

**Chất lượng vận hành**

- [ ] Có contract tests giữa UI–BFF và BFF–domain.
- [ ] Có thử nghiệm hiệu năng trên thiết bị/mạng mục tiêu.
- [ ] Có metric route, downstream dependency, latency, degraded mode.
- [ ] Có trace/correlation và runbook cho timeout/fallback.
- [ ] BFF có team owner, on-call, deploy/rollback procedure.
- [ ] Có chiến lược mobile compatibility và decommission API cũ.

## 29. Ghi nhớ

**Backend for Frontend** đặt một lớp backend gần nhu cầu của **một nhóm trải nghiệm frontend**, giúp frontend nhận dữ liệu đúng hình dạng, giảm số round trip, che topology nội bộ và tiến hóa contract theo nhịp phù hợp. BFF thường hiệu quả khi web, mobile, admin hoặc các nhóm sản phẩm khác biệt đáng kể về hành trình, quyền, dữ liệu, SLO và ownership.

BFF **không** thay API Gateway, domain service hay workflow engine. Nó có thể tổng hợp và điều chỉnh dữ liệu, nhưng không sở hữu nguồn sự thật về giá, đơn hàng, tồn kho hoặc thanh toán. Khi thiết kế, phải bảo vệ hợp đồng, phân quyền, ngân sách độ trễ, cache, lỗi một phần và khả năng quan sát.

Thước đo thành công không phải “đã có ba BFF” mà là **trải nghiệm tốt hơn, thay đổi nhanh hơn, ít coupling hơn và chi phí vận hành hợp lý hơn**, trong khi tính đúng đắn của nghiệp vụ vẫn được bảo toàn.
