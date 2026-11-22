# Quản lý dữ liệu và lộ trình tách dần ngữ cảnh

Khi một hệ thống phát triển từ ứng dụng đơn khối thành nhiều bounded context hoặc dịch vụ độc lập hơn, một trong những phần khó nhất là dữ liệu. Code có thể được chia thành package hoặc module tương đối nhanh, nhưng dữ liệu thường đã gắn chặt với nhiều use case: nhiều module cùng đọc một bảng, một transaction cập nhật nhiều nhóm dữ liệu, báo cáo join xuyên nghiệp vụ và các khóa ngoại nối các bảng thuộc những vùng trách nhiệm khác nhau.

Trong Domain-Driven Design (DDD), mỗi bounded context sở hữu mô hình và quy tắc của mình. Quyền sở hữu đó cần được phản ánh trong cách hệ thống đọc, ghi, thay đổi và công bố dữ liệu. Nếu Sales, Inventory và Billing cùng ghi trực tiếp vào các bảng của nhau, việc đổi package hoặc triển khai thành nhiều service chưa tạo ra ranh giới thực sự.

Tách dữ liệu không nhất thiết bắt đầu bằng việc tạo một database server cho mỗi context. Nhóm có thể đi từng bước: xác định owner, cô lập đường ghi, tạo contract, tách schema hoặc quyền truy cập, chuyển dữ liệu, đồng bộ phần thay đổi mới, rồi mới cutover sang storage độc lập nếu cần. Lộ trình phải giữ được tính đúng đắn nghiệp vụ, khả năng truy vết và phương án phục hồi trong suốt thời gian chuyển đổi.

Bài học này trình bày cách quản lý dữ liệu theo bounded context, nhận diện shared database và shared schema, chọn mức cô lập phù hợp, thiết kế contract và read model, chuyển dữ liệu theo giai đoạn, sử dụng outbox hoặc change data capture khi cần, kiểm soát dual write, cutover và rollback, cũng như những kiểm tra cần có trước khi coi một context đã độc lập về dữ liệu.

## 1. Quyền sở hữu dữ liệu là nền tảng của ranh giới

Một bounded context nên là nơi có thẩm quyền thay đổi dữ liệu thuộc mô hình của nó. Context khác có thể cần thông tin, nhưng cần nhận thông tin qua contract được công bố thay vì tự sửa bảng nội bộ.

Ví dụ trong hệ thống thương mại điện tử:

- Sales sở hữu đơn hàng, dòng hàng, trạng thái thương mại và snapshot giá tại thời điểm đặt.
- Inventory sở hữu số lượng khả dụng, reservation và chính sách giữ hàng.
- Billing sở hữu invoice, payment authorization, capture và refund.
- Shipping sở hữu shipment, delivery window và trạng thái bàn giao.
- Identity sở hữu tài khoản đăng nhập, thông tin xác thực và quyền truy cập.

Các context có thể cùng nhắc đến một khách hàng hoặc một đơn hàng, nhưng mỗi context cần dữ liệu phục vụ trách nhiệm riêng. Billing có thể cần thông tin người trả tiền tại thời điểm phát hành hóa đơn; Shipping cần địa chỉ nhận hàng đã được xác nhận; Sales cần thông tin người mua và điều kiện thương mại. Không nhất thiết mọi context cùng đọc một bảng Customer hoặc Order.

### 1.1. Data ownership không chỉ là ai tạo bảng

Một context thực sự sở hữu dữ liệu khi nó quyết định:

- Ý nghĩa của các trường và trạng thái.
- Quy tắc hợp lệ khi tạo hoặc thay đổi.
- Các hành vi được phép.
- Cách dữ liệu được lưu và di chuyển.
- Cách công bố thông tin cho consumer.
- Cách xử lý dữ liệu lịch sử và thay đổi schema.

Nếu một module có bảng riêng nhưng module khác vẫn cập nhật trực tiếp bảng đó, ownership vẫn bị chia sẻ. Nếu một context chỉ có quyền đọc qua view nhưng không có quyền quyết định semantics, nó cũng chưa chắc là owner.

### 1.2. Một nguồn dữ liệu có thể có nhiều bản sao

Quyền sở hữu không có nghĩa chỉ được tồn tại một bản sao vật lý. Các context khác có thể giữ projection hoặc snapshot phục vụ nhu cầu của mình. Điểm quan trọng là xác định nguồn sự thật (source of truth), ai có quyền ghi và bản sao được cập nhật theo contract nào.

Ví dụ, Sales sở hữu Order. Shipping có thể lưu một shipment request chứa order reference, danh sách hàng và địa chỉ giao tại thời điểm yêu cầu. Bản sao này phục vụ vận chuyển; Shipping không trở thành owner của đơn hàng.

## 2. Bounded Context, module, service và database có ranh giới khác nhau

Không nên mặc định một bounded context luôn tương ứng một database server hoặc một microservice. Đây là các quyết định ở những cấp khác nhau:

| Khái niệm | Ranh giới chính | Câu hỏi |
| --- | --- | --- |
| Bounded Context | Mô hình và ngôn ngữ nghiệp vụ | Ai sở hữu khái niệm và quy tắc? |
| Module ứng dụng | Tổ chức code và dependency | Code nào được phép phụ thuộc vào code nào? |
| Deployable service | Đơn vị triển khai và vận hành | Thành phần nào có thể release/scale độc lập? |
| Database/schema | Storage và quyền truy cập dữ liệu | Ai được ghi và đọc cấu trúc lưu trữ nào? |

Một modular monolith có thể có nhiều bounded context, nhiều module code và một database vật lý. Điều đó vẫn có thể là thiết kế tốt nếu quyền sở hữu và dependency được kiểm soát. Ngược lại, tách thành nhiều microservice nhưng tất cả cùng ghi một schema có thể tạo ra distributed monolith.

### 2.1. Tách deployment trước khi tách ownership có thể làm vấn đề khó hơn

Nếu Sales và Billing đang cập nhật trực tiếp cùng bảng Order, tách chúng thành hai service sẽ biến dependency trong process thành dependency qua network hoặc shared database. Lỗi kết nối, transaction phân tán và thứ tự deploy sẽ xuất hiện trong khi ownership vẫn chưa rõ.

Thông thường nên làm rõ ranh giới và contract trước, cô lập quyền ghi tiếp theo, rồi mới quyết định tách deployment hoặc storage.

## 3. Các mức chia sẻ dữ liệu thường gặp

Có nhiều mức cô lập. Không cần nhảy thẳng từ shared schema sang database server riêng nếu nhu cầu chưa đòi hỏi.

| Mức | Cách tổ chức | Mức độc lập |
| --- | --- | --- |
| 1. Shared tables, shared writes | Nhiều module cùng đọc và ghi các bảng | Rất thấp |
| 2. Shared database, ownership rõ | Mỗi context có owner; context khác không ghi bảng của owner | Tốt hơn, nhưng còn chung hạ tầng |
| 3. Separate schema trong cùng database | Mỗi context có schema riêng, quyền truy cập riêng | Cô lập logic rõ hơn |
| 4. Separate database trong cùng cluster/server | Mỗi context có database riêng, backup/permission riêng | Cô lập storage ở mức database |
| 5. Independent database/service | Mỗi context tự vận hành storage và deploy | Độc lập cao, chi phí phân tán lớn hơn |

### 3.1. Shared database có thể là bước trung gian hợp lý

Một database server duy nhất có thể chứa schema sales, inventory và billing. Các context vẫn dùng chung CPU, disk và một số giới hạn vận hành, nhưng quyền ghi và migration có thể tách biệt.

Đây là bước hữu ích để loại bỏ cross-context writes trước khi phát sinh chi phí vận hành nhiều database. Tuy nhiên, nếu ứng dụng vẫn join trực tiếp schema của context khác trong mọi query, coupling dữ liệu vẫn còn.

### 3.2. Database per service là nguyên tắc ownership, không nhất thiết là một máy chủ riêng

Mô hình database-per-service nhấn mạnh storage riêng thuộc quyền kiểm soát của service. Trong giai đoạn đầu, storage có thể là database hoặc schema riêng trên cùng một database cluster. Điều quan trọng là service khác không được truy cập trực tiếp bảng nội bộ và service owner có thể thay đổi schema theo nhu cầu của mình.

Khi yêu cầu scale, security, availability hoặc lifecycle khác nhau, có thể chuyển sang database instance hoặc storage engine riêng.

## 4. Nhận diện coupling dữ liệu trong hệ thống hiện tại

Trước khi tách dữ liệu, cần hiểu hệ thống đang phụ thuộc thế nào. Không nên chỉ nhìn sơ đồ bảng; cần tìm cả đường đọc, đường ghi và các transaction.

Những dấu hiệu cần điều tra:

- Nhiều module cùng insert/update/delete một bảng.
- Một repository được inject vào nhiều bounded context.
- SQL join trực tiếp các bảng thuộc nhiều vùng nghiệp vụ.
- Stored procedure thực hiện nghiệp vụ của nhiều context.
- Trigger cập nhật dữ liệu ở schema khác.
- Foreign key nối các bảng có owner khác nhau.
- Một transaction cập nhật Order, Inventory và Payment cùng lúc.
- Batch job hoặc báo cáo ghi vào bảng vận hành.
- ETL hoặc script thủ công sửa dữ liệu trực tiếp.

### 4.1. Lập bản đồ truy cập dữ liệu

Với mỗi bảng hoặc aggregate, ghi lại:

- Context owner dự kiến.
- Các thành phần đọc.
- Các thành phần ghi.
- Use case và transaction liên quan.
- Trigger, procedure, view và job phụ thuộc.
- Báo cáo hoặc tích hợp bên ngoài sử dụng dữ liệu.
- Mức độ quan trọng và tần suất truy cập.

Một bảng đơn giản:

| Bảng | Owner dự kiến | Reader | Writer | Vấn đề |
| --- | --- | --- | --- | --- |
| orders | Sales | Sales, Shipping, Billing, Reporting | Sales, Billing | Billing cập nhật trực tiếp trạng thái đơn |
| stock_items | Inventory | Inventory, Sales, Reporting | Inventory, Sales | Sales trừ tồn trực tiếp |
| payments | Billing | Billing, Sales, Reporting | Billing | Sales cập nhật payment status |
| shipments | Shipping | Shipping, Sales, Support | Shipping | Sales ghi tracking status |

Bảng trên chỉ là ví dụ. Việc đọc có thể được cho phép qua contract hoặc projection; việc ghi trực tiếp vào dữ liệu owner thường là dấu hiệu cần xử lý.

### 4.2. Dùng log và query telemetry để tìm dependency ẩn

Mã nguồn có thể bỏ sót SQL động, stored procedure, ETL, dashboard hoặc tác vụ vận hành. Query log, audit log, database activity và telemetry giúp phát hiện consumer thực tế. Cần giới hạn thời gian quan sát đủ bao phủ các job chạy theo ngày, tháng hoặc cuối kỳ.

### 4.3. Không thay đổi dữ liệu khi chưa biết ai đang dùng

Một bảng tưởng như chỉ có một consumer có thể đang được dùng bởi báo cáo tài chính hoặc đối tác. Trước khi chuyển schema hoặc ngừng cột, cần kiểm tra consumer chạy định kỳ và các tích hợp ngoài codebase.

## 5. Chọn nguồn sự thật cho từng khái niệm

Mỗi dữ liệu có ý nghĩa nghiệp vụ cần có nguồn sự thật được xác định. Một hệ thống có thể có nhiều bản sao nhưng không nên có nhiều nơi cùng tự quyết định giá trị chuẩn của cùng một khái niệm.

Ví dụ:

| Khái niệm | Source of truth | Bản sao hợp lệ |
| --- | --- | --- |
| Trạng thái thương mại của Order | Sales | Order summary cho Reporting; shipment reference cho Shipping |
| Số lượng tồn khả dụng | Inventory | Projection tồn kho cho Sales UI |
| Trạng thái thanh toán | Billing | Payment summary trong Sales |
| Trạng thái giao hàng | Shipping | Delivery summary cho Sales/Support |
| Thông tin đăng nhập | Identity | User reference hoặc claims cần thiết cho các context |

### 5.1. Snapshot khác với bản sao đồng bộ

Snapshot là dữ liệu được chụp tại một thời điểm để giữ ý nghĩa lịch sử. Ví dụ, hóa đơn lưu tên và địa chỉ thanh toán tại thời điểm phát hành. Thay đổi hồ sơ khách hàng sau này không nên làm thay đổi nội dung hóa đơn cũ.

Bản sao đồng bộ là dữ liệu được cập nhật để phản ánh trạng thái mới nhất từ owner. Ví dụ, Sales giữ payment status projection để hiển thị. Snapshot và projection có mục đích khác nhau; không nên cập nhật snapshot lịch sử như thể nó là cache hiện tại.

### 5.2. Định nghĩa semantics và thời điểm

Một trường tên status có thể có nghĩa khác giữa các context. Sales OrderStatus không nhất thiết bằng Shipping DeliveryStatus. Contract cần nói rõ trạng thái thuộc quy trình nào, được xác nhận tại thời điểm nào và có thể thay đổi ra sao.

## 6. Ngăn cross-context writes

Một trong những bước quan trọng nhất là đảm bảo chỉ owner được thay đổi dữ liệu nghiệp vụ của mình.

Ví dụ, không nên để Sales thực hiện:

~~~sql
UPDATE inventory.stock_items
SET available_quantity = available_quantity - 2
WHERE product_id = :productId;
~~~

Sales không sở hữu invariant tồn kho. Nó nên gửi command ReserveStock đến Inventory hoặc phát event để Inventory xử lý theo mô hình tích hợp đã chọn.

Tương tự:

- Sales không tự cập nhật Payment status.
- Billing không tự sửa Order status trong bảng Sales.
- Shipping không tự sửa dữ liệu tồn kho.
- Reporting không ghi ngược vào bảng vận hành để sửa số liệu.

### 6.1. Tách quyền database

Có thể tạo database user hoặc role riêng cho từng context. User của Sales chỉ có quyền ghi schema sales và quyền đọc giới hạn đối với các view/contract cần thiết. User của Inventory không được cập nhật bảng sales.

Phân quyền database không thay thế domain model, nhưng là một lớp bảo vệ hữu ích: nếu developer vô tình tạo SQL cross-context write, database có thể từ chối.

### 6.2. Kiểm soát migration ownership

Mỗi context nên sở hữu script migration cho schema của mình. Không để một module migration tùy tiện đổi bảng nội bộ của module khác. Các thay đổi cross-context cần được thống nhất qua contract và kế hoạch phối hợp.

### 6.3. Không chia sẻ repository nội bộ

Context khác không nên import JPA repository hoặc entity nội bộ chỉ vì chúng cùng nằm trong một codebase. Hãy công bố query contract, application port hoặc integration event. Consumer chuyển dữ liệu ngoài thành mô hình của mình qua adapter/ACL.

## 7. Đọc dữ liệu từ context khác

Đọc dữ liệu xuyên context có nhiều cách. Lựa chọn phụ thuộc vào độ tươi dữ liệu, khối lượng truy vấn, mức độc lập và nhu cầu vận hành.

| Cách | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| Query API của owner | Consumer gọi owner để lấy thông tin | Cần dữ liệu tương đối mới và số lần gọi có thể kiểm soát |
| Integration event + local projection | Consumer giữ bản sao được cập nhật từ event | Cần đọc nhanh, nhiều query hoặc chấp nhận eventual consistency |
| Snapshot trong transaction nghiệp vụ | Lưu thông tin tại thời điểm xảy ra hành động | Cần giữ nghĩa lịch sử |
| Shared read view có kiểm soát | Owner công bố view hoặc read contract | Giai đoạn chuyển tiếp hoặc môi trường triển khai chung |
| Direct table access | Consumer truy vấn bảng nội bộ của owner | Thường tạo coupling; chỉ nên là ngoại lệ có quản trị rõ |

### 7.1. Query API

Sales có thể hỏi Inventory về khả năng giữ hàng. Tuy nhiên, một query “còn 5 sản phẩm” không đảm bảo 5 sản phẩm vẫn còn khi command đặt hàng đến sau đó. Nếu cần đảm bảo, Sales phải gửi command ReserveStock và chờ kết quả; query chỉ cung cấp thông tin tham khảo.

### 7.2. Local projection

Sales có thể tiêu thụ InventoryChanged hoặc StockReservation events để cập nhật một projection phục vụ UI. Projection này có thể trễ và không nên được dùng như nguồn quyết định cuối cùng cho reservation.

### 7.3. Tránh join xuyên database như một hợp đồng

Nếu Reporting cần kết hợp Sales, Billing và Shipping, nên tạo reporting model hoặc data warehouse từ các contract được công bố. Join trực tiếp các bảng vận hành khiến báo cáo phụ thuộc schema nội bộ và cản trở việc tách storage.

## 8. Contract dữ liệu giữa các Bounded Context

Một contract dữ liệu cần định nghĩa rõ:

- Ý nghĩa của message hoặc query.
- Producer/owner và consumer.
- ID nghiệp vụ và correlation.
- Trường bắt buộc, tùy chọn, nullable.
- Đơn vị tiền tệ, thời gian và measurement.
- Semantics của trạng thái.
- Version và quy tắc tương thích.
- Cách xử lý message trùng, đến muộn hoặc sai thứ tự.
- Chính sách dữ liệu nhạy cảm và retention.

Ví dụ integration event OrderPlaced:

~~~json
{
  "eventId": "evt-901",
  "eventType": "sales.order-placed.v1",
  "occurredAt": "2026-11-18T03:00:00Z",
  "orderId": "ord-501",
  "buyerReference": "buyer-81",
  "currency": "VND",
  "lines": [
    {
      "productReference": "sku-101",
      "quantity": 2
    }
  ],
  "shippingAddress": {
    "recipient": "Nguyen Van A",
    "postalCode": "700000"
  }
}
~~~

Đây là payload minh họa; dữ liệu cá nhân cần được giới hạn theo mục đích và chính sách bảo vệ dữ liệu. Shipping chỉ nhận các trường cần cho việc vận chuyển, không nhận toàn bộ Sales Order aggregate.

### 8.1. Contract không nên phơi bày schema database

Không gửi tên bảng, column nội bộ hoặc ORM entity làm integration contract. Nếu producer đổi cách lưu dữ liệu mà ý nghĩa công bố không đổi, consumer không cần thay đổi.

### 8.2. Version hóa và tiến hóa contract

Thêm trường optional có thể tương thích nếu consumer bỏ qua trường chưa biết và producer có default phù hợp. Đổi tên trường, đổi kiểu hoặc đổi semantics thường là breaking change. Hãy dùng versioning, deprecation và contract test theo chiến lược đã thống nhất.

### 8.3. Contract có thể là query interface hoặc event schema

Không phải mọi tương tác đều cần event. Một số dữ liệu cần query đồng bộ; một số fact cần công bố bất đồng bộ. Chọn cách theo yêu cầu nghiệp vụ, không dùng message broker chỉ vì kiến trúc đang tách context.

## 9. Lộ trình tách dần từ Shared Database

Tách dữ liệu nên diễn ra theo từng bước có thể kiểm chứng. Một lộ trình tổng quát:

~~~mermaid
flowchart TD
    A[Shared tables and cross-context writes] --> B[Identify data owners]
    B --> C[Define contracts and stop new cross-writes]
    C --> D[Isolate schemas and permissions]
    D --> E[Create target storage and schema]
    E --> F[Backfill historical data]
    F --> G[Replicate ongoing changes]
    G --> H[Reconcile and validate]
    H --> I[Cut over reads and writes]
    I --> J[Observe and retire old access]
~~~

Các bước có thể chồng lấn theo kế hoạch, nhưng không nên bỏ qua việc xác định owner và kiểm tra dữ liệu trước cutover.

### 9.1. Bước 1: Chọn một context và một lát dữ liệu

Không tách toàn bộ database trong một lần. Chọn context có ownership rõ, ít cross-write hoặc có thể cô lập trước. Xác định aggregate/bảng nào thuộc phạm vi migration.

### 9.2. Bước 2: Chặn thêm dependency mới

Trước khi di chuyển dữ liệu, tạo architecture rule, database permission hoặc code review rule để không xuất hiện thêm cross-context writes. Nếu dependency tiếp tục tăng trong lúc migration, phạm vi sẽ liên tục thay đổi.

### 9.3. Bước 3: Công bố contract

Định nghĩa query/API/event mà consumer cần. Thay direct repository/table access bằng adapter hoặc contract. Có thể bắt đầu với implementation đọc từ database cũ để giữ hành vi hiện tại.

### 9.4. Bước 4: Tách schema hoặc storage

Tạo schema mới hoặc database đích. Xác định owner của migration script, ID strategy, index, constraint, retention và backup.

### 9.5. Bước 5: Backfill dữ liệu lịch sử

Copy dữ liệu hiện có theo batch có thể chạy lại. Ghi nhận watermark/checkpoint, số lượng bản ghi và lỗi. Không giả định một lệnh copy duy nhất sẽ luôn hoàn tất.

### 9.6. Bước 6: Đồng bộ các thay đổi phát sinh trong lúc backfill

Trong khi copy lịch sử, dữ liệu nguồn vẫn có thể thay đổi. Cần một cơ chế bắt thay đổi mới như outbox, CDC hoặc một cửa sổ freeze có kiểm soát. Nếu không, target có thể thiếu hoặc ghi đè những cập nhật xảy ra sau snapshot ban đầu.

### 9.7. Bước 7: Đối soát

So sánh count, key, checksum hoặc các chỉ số nghiệp vụ giữa nguồn và đích. Kiểm tra các quan hệ và trạng thái quan trọng, không chỉ xác nhận tổng số hàng.

### 9.8. Bước 8: Cutover có kiểm soát

Chuyển read traffic hoặc write traffic theo kế hoạch. Có thể dùng feature flag, routing hoặc một thời điểm maintenance. Theo dõi lỗi, latency, lag và sai lệch sau chuyển đổi.

### 9.9. Bước 9: Ngừng quyền truy cập cũ

Chỉ sau khi xác nhận mọi consumer đã chuyển, thu hồi quyền ghi cũ, bỏ adapter chuyển tiếp và lên lịch xóa dữ liệu cũ theo chính sách. Giữ backup và bằng chứng đối soát theo yêu cầu vận hành.

## 10. Backfill dữ liệu lịch sử

Backfill là quá trình chuyển dữ liệu đã tồn tại sang storage hoặc read model mới. Nó cần có thể tiếp tục sau lỗi và không tạo tải quá mức lên hệ thống nguồn.

Một quy trình backfill nên xác định:

- Phạm vi bảng/aggregate và thời điểm snapshot.
- Khóa phân trang ổn định.
- Batch size và giới hạn tốc độ.
- Checkpoint/watermark.
- Quy tắc chuyển đổi schema và dữ liệu legacy.
- Cách xử lý bản ghi lỗi hoặc thiếu tham chiếu.
- Số lượng và checksum để đối soát.
- Cách chạy lại an toàn.

### 10.1. Idempotent backfill

Nếu một batch chạy lại, nó không nên tạo bản ghi trùng hoặc ghi đè dữ liệu mới hơn. Có thể dùng upsert theo business ID, version hoặc migration key, nhưng cần xác định rõ nguồn nào thắng khi source và target cùng thay đổi.

### 10.2. Giữ identity

Nếu consumer đã lưu Order ID hoặc Payment ID, migration thường cần giữ nguyên business identity để các reference không bị đứt. Nếu đổi ID format, phải có mapping và thời gian tương thích cho consumer cũ.

### 10.3. Xử lý dữ liệu không hợp lệ

Dữ liệu cũ có thể vi phạm invariant mới. Không nên âm thầm loại bỏ hoặc tự gán default. Hãy phân loại:

- Dữ liệu cần sửa bằng migration có quy tắc.
- Dữ liệu cần giữ dưới dạng legacy và xử lý riêng.
- Dữ liệu trùng cần quyết định hợp nhất.
- Dữ liệu thiếu reference cần reconciliation.
- Dữ liệu không thể chuyển cần báo cáo và có người chịu trách nhiệm.

## 11. Đồng bộ thay đổi trong giai đoạn chuyển tiếp

Backfill chỉ sao chép trạng thái tại một thời điểm. Nếu hệ thống nguồn tiếp tục ghi, cần chuyển tiếp các thay đổi phát sinh sau snapshot.

Các cách thường gặp:

| Cơ chế | Cách hoạt động | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| Transactional Outbox | Ghi thay đổi và event vào cùng transaction; publisher chuyển event | Gắn với nghiệp vụ, có thể mang semantics rõ | Cần inbox/idempotency ở consumer |
| Change Data Capture (CDC) | Đọc transaction log/database change stream | Bắt thay đổi ở tầng database | Consumer phải hiểu schema và semantics; cần quản lý offset |
| Dual write trong application | Ứng dụng ghi cả nguồn và đích | Dễ hình dung ban đầu | Có thể một bên thành công, bên kia thất bại |
| Scheduled delta sync | Job định kỳ tìm bản ghi thay đổi sau watermark | Đơn giản cho một số hệ thống | Có độ trễ, cần xử lý update/delete và thứ tự |
| Freeze window | Tạm ngừng ghi trong thời gian cutover | Dễ đạt snapshot nhất quán | Ảnh hưởng hoạt động và cần lịch rõ |

### 11.1. Outbox khi thay đổi có ý nghĩa nghiệp vụ

Nếu Sales cần công bố OrderPlaced, application có thể lưu Order và outbox event trong cùng transaction. Publisher gửi event sau commit. Consumer Inventory hoặc Shipping cập nhật dữ liệu của mình theo contract.

Outbox giúp tránh tình huống database commit thành công nhưng publish message thất bại trước khi ghi nhận. Tuy nhiên, publisher có thể gửi lại; consumer vẫn cần idempotency.

### 11.2. CDC khi cần chuyển đổi dữ liệu ở tầng storage

CDC có thể đọc log transaction để chuyển các insert/update/delete sang target. Nó hữu ích khi cần đồng bộ bảng hiện có mà chưa thể thay đổi mọi code path để phát domain event.

CDC phản ánh thay đổi database, không tự cung cấp semantics nghiệp vụ. Một update cột status không cho biết vì sao trạng thái thay đổi hoặc quy tắc nào đã được áp dụng. Khi consumer cần ý nghĩa nghiệp vụ, integration event thường phù hợp hơn.

### 11.3. Dual write cần được kiểm soát chặt

Nếu ứng dụng ghi database cũ rồi ghi database mới, một lần ghi có thể thành công trong khi lần kia thất bại. Không có transaction ACID thông thường bao trùm hai database độc lập. Retry có thể tạo trùng hoặc ghi đè sai thứ tự.

Nếu buộc phải dùng dual write trong giai đoạn ngắn, cần operation ID, idempotency, reconciliation, giám sát sai lệch và quy tắc xác định source of truth. Không coi dual write là cơ chế đồng bộ đáng tin cậy mặc định.

## 12. Expand–Migrate–Contract cho schema và ownership

Một cách an toàn để thay đổi schema khi nhiều phiên bản ứng dụng cùng hoạt động là Expand–Migrate–Contract.

Ví dụ, bảng orders ban đầu nằm trong schema chung; nhóm muốn chuyển quyền sở hữu sang Sales schema và thay cấu trúc cột.

### 12.1. Expand

- Tạo schema hoặc bảng mới ở target.
- Thêm cột/index/constraint mới mà code cũ vẫn có thể chạy.
- Triển khai adapter có thể đọc nguồn cũ hoặc target theo feature flag.
- Nếu cần, ghi outbox hoặc CDC để đồng bộ thay đổi.
- Giữ schema cũ trong thời gian chuyển tiếp.

### 12.2. Migrate

- Backfill dữ liệu lịch sử.
- Đồng bộ delta liên tục.
- Chuyển dần read path sang target.
- Đối soát dữ liệu và nghiệp vụ.
- Chuyển write ownership theo một thời điểm hoặc theo partition có kiểm soát.
- Theo dõi mọi write còn phát sinh ở nguồn cũ.

### 12.3. Contract

- Xác nhận không còn consumer đọc/ghi schema cũ.
- Thu hồi quyền truy cập cũ.
- Ngừng đồng bộ chuyển tiếp.
- Xóa adapter và schema cũ sau thời gian an toàn.
- Cập nhật tài liệu vận hành và ownership.

### 12.4. Tách read và write cutover nếu cần

Có thể chuyển read trước để kiểm tra dữ liệu đích, sau đó chuyển write khi đã sẵn sàng. Nhưng cần xác định cách tránh read từ target trong khi target chưa nhận đủ cập nhật. Nếu read và write chuyển ở thời điểm khác nhau, consistency model phải được công bố và kiểm thử.

## 13. Cutover và phương án rollback

Cutover là thời điểm một luồng đọc/ghi chuyển sang nguồn mới. Đây là bước có rủi ro cao vì hệ thống bắt đầu tạo dữ liệu có thể không còn được phản ánh ở nguồn cũ.

Trước cutover cần:

- Xác định chính xác điều kiện bắt đầu.
- Có snapshot/backup đã kiểm tra khả năng restore.
- Đảm bảo backfill và delta sync đã đạt watermark.
- Đối soát count, checksum và nghiệp vụ.
- Có dashboard latency, error rate, replication lag và write failure.
- Có người chịu trách nhiệm quyết định tiếp tục hoặc rollback.
- Xác định rõ source of truth tại từng thời điểm.

### 13.1. Rollback trước và sau khi có write mới

Rollback dễ hơn nếu target chưa nhận write độc quyền. Sau khi target đã nhận write mới, quay lại nguồn cũ có thể làm mất dữ liệu hoặc tạo split-brain nếu cả hai bên cùng nhận write.

Vì vậy, kế hoạch rollback cần nói rõ:

- Có thể chuyển traffic về nguồn cũ trong điều kiện nào?
- Những write đã xảy ra ở target sẽ được chuyển ngược bằng cách nào?
- Có cần freeze writes trước khi rollback không?
- Có thể replay outbox/CDC theo chiều ngược không, hay cần một migration bù riêng?
- Ai xác nhận dữ liệu đã đối soát?

Không nên hứa rollback một nút nếu dữ liệu mới đã được ghi ở storage đích mà chưa có replication ngược hoặc kế hoạch reconciliation.

### 13.2. Roll-forward đôi khi an toàn hơn rollback

Nếu schema mới đã nhận dữ liệu và không có đường đồng bộ ngược đáng tin cậy, có thể cần sửa lỗi tại target và tiếp tục tiến lên. Đây là quyết định cần dựa trên backup, tính chất dữ liệu và khả năng phục hồi.

### 13.3. Dùng feature flag có kiểm soát

Feature flag giúp chuyển một phần traffic hoặc tenant sang target. Cần tránh trạng thái một request đọc nguồn A nhưng ghi nguồn B mà không có semantics rõ. Flag phải có owner, thời hạn và log quyết định chuyển đổi.

## 14. Quản lý foreign key và quan hệ xuyên context

Foreign key là công cụ tốt để bảo vệ referential integrity trong một schema/database. Nhưng foreign key giữa các bounded context có thể làm chúng bị ràng buộc vào cùng storage và thứ tự migration.

Khi tách dữ liệu:

- Foreign key nội bộ một context thường nên được giữ.
- Reference sang context khác có thể trở thành external ID.
- Consumer cần xử lý trường hợp reference chưa có hoặc context kia chưa đồng bộ.
- Nếu cần đảm bảo sự tồn tại, dùng contract/command hoặc workflow phù hợp thay vì dựa vào foreign key xuyên storage.

Ví dụ, Sales lưu customerId như reference. Khi Customer thuộc Identity/Customer context ở storage riêng, Sales không thể dùng foreign key database đến bảng khách hàng. Sales có thể lưu external ID và kiểm tra thông tin cần thiết qua contract khi tạo đơn.

### 14.1. External ID không tự bảo đảm đối tượng còn tồn tại

Khi dùng reference ID, đối tượng ở context khác có thể bị đóng, ẩn danh hoặc xóa theo chính sách. Consumer cần xác định semantics: snapshot lịch sử, trạng thái hiện tại hay reference có thể không còn resolve được.

### 14.2. Tránh distributed foreign key

Không cố mô phỏng foreign key giữa hai database bằng các truy vấn đồng bộ trong mọi lần đọc. Điều đó tạo coupling và tăng latency. Hãy xác định chỗ nào cần snapshot, chỗ nào cần query owner và chỗ nào cần xử lý bất đồng bộ.

## 15. Transaction và consistency sau khi tách dữ liệu

Trong một database, một transaction có thể cập nhật nhiều bảng cùng lúc. Khi dữ liệu được tách thành nhiều storage, không còn một transaction ACID đơn giản bao trùm tất cả.

Nhóm cần xác định:

- Invariant nào phải được bảo vệ ngay trong một aggregate/context?
- Hành động nào có thể được xử lý bất đồng bộ?
- Khi một bước thất bại, có cần compensation không?
- Consumer chấp nhận dữ liệu trễ bao lâu?
- Trạng thái trung gian nào cần hiển thị?
- Quy trình nào cần Process Manager/Saga?

### 15.1. Giữ invariant bên trong owner

Inventory phải bảo vệ reservation và số lượng tồn trong transaction của Inventory. Sales không thể đảm bảo tồn kho bằng cách đọc số lượng trước rồi tự giảm ở database khác. Nó gửi command ReserveStock; Inventory trả kết quả đã được xác nhận.

### 15.2. Dùng eventual consistency có chủ đích

Sales có thể nhận PaymentAuthorized sau khi Billing commit. Trong khoảng chờ, đơn có thể ở trạng thái AWAITING_PAYMENT. Đây là trạng thái nghiệp vụ được mô hình hóa, không phải lỗi nếu quy trình cho phép.

Không nên để UI hoặc báo cáo giả định mọi projection đều cập nhật ngay sau một command bất đồng bộ.

### 15.3. Saga và compensation

Nếu một quy trình gồm nhiều context và cần hành động bù, Process Manager/Saga có thể điều phối. Ví dụ, giữ hàng thành công nhưng thanh toán bị từ chối thì yêu cầu Inventory giải phóng reservation. Compensation là hành vi mới, không phải rollback transaction cũ.

## 16. Reporting, analytics và dữ liệu tổng hợp

Một lý do thường khiến nhiều context cùng đọc bảng của nhau là báo cáo. Dashboard muốn join Order, Payment, Shipment và Customer trong một query.

Giải pháp bền vững hơn là tạo read model dành cho reporting:

- Nhận integration event hoặc extract từ các owner.
- Lưu projection phù hợp với nhu cầu phân tích.
- Cho phép join/aggregate trong kho báo cáo.
- Xác định độ trễ và thời điểm dữ liệu được cập nhật.
- Không dùng reporting store làm nguồn ghi cho nghiệp vụ vận hành.

### 16.1. Operational query khác analytical query

Operational query phục vụ một hành động hoặc màn hình tương tác cần dữ liệu tương đối mới. Analytical query phục vụ tổng hợp lịch sử, phân tích xu hướng và báo cáo nặng. Hai loại workload có thể cần storage và tối ưu khác nhau.

### 16.2. Không biến reporting thành một bounded context sở hữu mọi dữ liệu

Reporting có thể sở hữu projection và mô hình phân tích của mình, nhưng không sở hữu các quy tắc gốc của Sales, Billing hay Inventory. Nó không nên ghi ngược kết quả phân tích vào aggregate nguồn.

### 16.3. Xác định snapshot và thời điểm dữ liệu

Báo cáo cần biết dữ liệu là current state hay snapshot tại một thời điểm. Ví dụ, doanh thu theo ngày có thể được tính theo thời điểm capture, invoice issue hoặc order placement. Đây là semantics nghiệp vụ cần thống nhất.

## 17. Migration dữ liệu và thay đổi mô hình

Khi tách context, schema mới có thể không giống schema cũ. Một bảng cũ có thể chứa trường thuộc nhiều khái niệm hoặc trạng thái đã bị dùng sai.

Migration cần phân biệt:

- **Schema migration:** thay đổi bảng, cột, index, constraint.
- **Data migration:** chuyển đổi giá trị và cấu trúc dữ liệu.
- **Domain migration:** thay đổi cách diễn giải khái niệm nghiệp vụ.
- **Ownership migration:** chuyển quyền ghi và trách nhiệm dữ liệu sang context khác.

### 17.1. Chuyển đổi semantics cần được review

Ví dụ, cột status cũ có các giá trị NEW, PAID, DONE. Sau khi tách, Sales có OrderStatus, Billing có PaymentStatus và Shipping có ShipmentStatus. Không nên sao chép nguyên cột status sang cả ba context. Cần phân tích lịch sử để ánh xạ từng fact vào đúng mô hình.

### 17.2. Lưu mapping khi ID hoặc semantics thay đổi

Nếu cần chuyển ID, tạo bảng mapping hoặc contract resolve có thời hạn. Giữ khả năng truy vết từ ID cũ sang ID mới để hỗ trợ log, audit, đối tác và các reference lịch sử.

### 17.3. Migration phải có thể kiểm tra và chạy lại

Script nên có checkpoint, log số bản ghi, kiểm tra precondition và postcondition. Tránh script không idempotent khiến lần chạy lại nhân đôi dữ liệu hoặc làm mất dữ liệu đã cập nhật.

## 18. Triển khai độc lập và quản lý schema

Khi một context được tách thành deployable service, nó cần quản lý schema và migration của mình.

Những nguyên tắc hữu ích:

- Mỗi service có migration history riêng.
- Chỉ service owner chạy migration cho schema của mình.
- Migration phải tương thích với rolling deployment khi cần.
- Không dùng startup migration để thay đổi schema của context khác.
- Có backup, restore và kiểm tra migration trên môi trường tương đương.
- Theo dõi migration duration, lock và ảnh hưởng đến traffic.

### 18.1. Expand–Migrate–Contract trong rolling deployment

Nếu code cũ và mới cùng chạy, schema cần hỗ trợ cả hai trong giai đoạn chuyển tiếp. Ví dụ, thêm cột mới trước, triển khai code đọc/ghi tương thích, backfill, chuyển code sang cột mới rồi mới bỏ cột cũ.

### 18.2. Migration lớn cần chia nhỏ

Thay đổi cột lớn, rewrite hàng triệu bản ghi hoặc thêm constraint có thể gây lock. Có thể cần backfill theo batch, tạo index theo cách online/concurrently nếu database hỗ trợ, rồi xác nhận constraint sau khi dữ liệu sạch.

Không có một cú pháp migration chung cho mọi database; phải kiểm tra behavior của engine thực tế.

## 19. Bảo mật và quyền truy cập dữ liệu

Khi có nhiều context, quyền truy cập cần phản ánh ownership và nguyên tắc least privilege.

- Service chỉ có quyền ghi storage do nó sở hữu.
- Consumer chỉ đọc contract hoặc projection cần thiết.
- Credential của service khác nhau theo môi trường và vai trò.
- Dữ liệu cá nhân/tài chính chỉ được công bố theo mục đích.
- Log, event và outbox không chứa secret hoặc payload nhạy cảm không cần thiết.
- Backup và bản sao dữ liệu cũng phải theo retention/access policy.
- Quyền vận hành thủ công cần audit.

Tách database nhưng dùng chung một credential có quyền ghi mọi schema sẽ làm giảm đáng kể giá trị cô lập. Cần quản lý cả identity của ứng dụng lẫn permission ở storage.

## 20. Quan sát và đối soát sau khi tách

Sau cutover, cần xác nhận không chỉ service chạy mà dữ liệu và nghiệp vụ vẫn đúng.

Metrics và log hữu ích:

- Số lượng bản ghi nguồn/đích theo loại.
- Replication lag hoặc outbox backlog.
- Tỷ lệ message lỗi và dead-letter.
- Số cross-context writes còn lại.
- Tỷ lệ query vẫn truy cập schema cũ.
- Số lỗi reference không resolve được.
- Chênh lệch tổng tiền, số lượng hoặc trạng thái nghiệp vụ.
- Latency và error rate trước/sau cutover.

### 20.1. Đối soát theo nghiệp vụ

Count và checksum là cần thiết nhưng chưa đủ. Có thể cần so sánh:

- Tổng số đơn theo ngày và trạng thái.
- Tổng tiền theo currency.
- Số reservation đang active.
- Số payment đã capture/refund.
- Số shipment chưa hoàn tất.
- Quan hệ giữa order, payment và shipment.

Các phép đối soát phải dùng cùng định nghĩa nghiệp vụ và cùng mốc thời gian. Nếu không, hai hệ thống có thể khác số liệu chỉ vì dùng thời điểm ghi nhận khác nhau.

### 20.2. Có quy trình xử lý mismatch

Khi phát hiện chênh lệch, không sửa trực tiếp database bằng SQL tùy tiện. Cần xác định owner, nguyên nhân, dữ liệu nguồn, cách sửa có audit và liệu có cần phát event điều chỉnh.

## 21. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Cho rằng mỗi bounded context phải có database server riêng ngay lập tức | Tăng chi phí vận hành và distributed complexity | Tách ownership trước, storage theo nhu cầu |
| Tách service nhưng vẫn cho ghi shared tables | Distributed monolith và coupling schema | Cô lập quyền ghi và công bố contract |
| Chỉ chia schema nhưng vẫn join trực tiếp tùy ý | Consumer phụ thuộc cấu trúc nội bộ | Dùng API, event hoặc read model |
| Không lập bản đồ reader/writer | Bỏ sót batch, report hoặc đối tác | Dùng source search, query telemetry và inventory |
| Dual write không có idempotency | Dữ liệu hai nơi lệch nhau | Outbox/CDC, operation ID và reconciliation |
| Backfill một lần rồi cutover ngay | Mất thay đổi phát sinh trong lúc copy | Snapshot, delta sync và watermark |
| Chỉ so sánh row count | Bỏ sót sai semantics hoặc quan hệ | Đối soát key, checksum và chỉ số nghiệp vụ |
| Dùng CDC như domain event | Consumer nhận thay đổi kỹ thuật không có semantics | Chuyển đổi thành contract phù hợp khi cần |
| Dùng foreign key xuyên database như trước | Tạo dependency vận hành khó duy trì | External ID và contract consistency |
| Coi snapshot là cache hiện tại | Làm thay đổi lịch sử ngoài ý muốn | Phân biệt snapshot với projection |
| Không có rollback sau cutover | Không biết phục hồi khi lỗi | Lập kế hoạch rollback/roll-forward trước |
| Cả hai storage cùng nhận write không kiểm soát | Split-brain và mất dữ liệu | Chỉ định source of truth theo từng giai đoạn |
| Một module chạy migration schema của module khác | Ownership schema không rõ | Migration history và quyền riêng |
| Không kiểm tra consumer định kỳ | Job cuối tháng có thể hỏng sau khi xóa schema | Theo dõi đủ chu kỳ nghiệp vụ |

## 22. Quy trình thiết kế lộ trình tách dữ liệu

Khi cần tách một bounded context khỏi shared database hoặc giảm coupling dữ liệu, nhóm có thể đi theo các bước:

### Bước 1: Xác định context và dữ liệu thuộc phạm vi

Chốt bounded context, aggregate, bảng, event và dữ liệu lịch sử liên quan. Xác nhận owner với chuyên gia nghiệp vụ và các nhóm kỹ thuật.

### Bước 2: Lập bản đồ mọi reader và writer

Tìm code, SQL, procedure, trigger, report, ETL, job và tích hợp ngoài. Phân biệt đọc, ghi và dependency transaction.

### Bước 3: Xác định source of truth

Với từng khái niệm, chỉ định owner và phân biệt current state, snapshot, cache và projection. Ghi rõ semantics và thời điểm.

### Bước 4: Thiết kế contract thay cho truy cập trực tiếp

Chọn query API, command, integration event hoặc projection. Định nghĩa version, idempotency, ordering và consistency.

### Bước 5: Ngăn cross-context writes mới

Thay repository/SQL trực tiếp bằng contract. Thêm database permission và architecture test để ngăn dependency quay lại.

### Bước 6: Chọn mức storage isolation

Quyết định dùng schema riêng, database riêng trong cùng cluster hay storage độc lập. Cân nhắc backup, security, scale, latency và vận hành.

### Bước 7: Chuẩn bị migration

Thiết kế schema đích, data transformation, ID mapping, backfill, checkpoint và xử lý legacy data.

### Bước 8: Chọn cơ chế delta sync

Chọn outbox, CDC, scheduled sync hoặc freeze window. Tránh dual write tùy tiện; xác định source of truth trong từng giai đoạn.

### Bước 9: Backfill và đối soát

Chạy theo batch, kiểm tra count/checksum/relationships và chỉ số nghiệp vụ. Xử lý mismatch trước cutover.

### Bước 10: Cutover có kiểm soát

Chuyển read/write theo feature flag hoặc cửa sổ triển khai. Theo dõi lag, lỗi, latency và cross-access.

### Bước 11: Rollback hoặc roll-forward theo điều kiện

Xác định trước cách xử lý write mới, freeze, reverse sync hoặc migration bù. Không dựa vào một nút chuyển traffic nếu dữ liệu đã phân nhánh.

### Bước 12: Thu hồi đường cũ và xác nhận ownership

Thu hồi quyền, ngừng consumer cũ, xóa adapter/schema cũ khi an toàn. Xác nhận context mới tự quản lý migration, backup, observability và contract.

## 23. Tiêu chí hoàn tất việc tách một context

Không nên đánh giá việc tách chỉ bằng việc service mới đã chạy hoặc database mới đã có dữ liệu. Có thể dùng các tiêu chí sau:

- Có owner và source of truth được xác định.
- Chỉ owner có quyền ghi dữ liệu nghiệp vụ.
- Consumer không phụ thuộc schema nội bộ.
- Contract đọc/ghi/event được tài liệu hóa và kiểm thử.
- Backfill và delta sync đã được đối soát.
- ID và reference lịch sử vẫn resolve theo semantics đã định.
- Các transaction liên context đã được thay bằng workflow/consistency phù hợp.
- Có backup, restore, migration và rollback/roll-forward plan.
- Có metrics cho lag, lỗi, mismatch và cross-access.
- Không còn reader/writer cũ chưa được phê duyệt.
- Quy trình vận hành và quyền truy cập đã được cập nhật.

Nếu một trong các điều kiện này chưa đạt, có thể xem đây là giai đoạn chuyển tiếp thay vì tuyên bố context đã độc lập hoàn toàn.

## 24. Nguyên tắc thực hành

Khi quản lý dữ liệu và tách dần bounded context, nhóm nên nhớ:

- **Xác định owner trước khi tách storage.** Ownership là quyết định nghiệp vụ và kiến trúc.
- **Một source of truth cho mỗi khái niệm.** Bản sao phục vụ đọc cần có semantics rõ.
- **Shared database không tự động là thiết kế sai.** Điều quan trọng là quyền ghi và dependency.
- **Ngăn cross-context writes.** Context khác gửi command hoặc tiêu thụ contract.
- **Không dùng schema nội bộ làm integration contract.** Công bố DTO, query API hoặc event có version.
- **Phân biệt snapshot, cache và projection.** Chúng có thời điểm và quy tắc cập nhật khác nhau.
- **Tách theo từng lát nhỏ.** Backfill, delta sync, đối soát và cutover cần có checkpoint.
- **Ưu tiên outbox/CDC có kiểm soát khi cần đồng bộ.** Dual write luôn cần xử lý partial failure và reconciliation.
- **Không giả định foreign key xuyên storage còn tồn tại.** Dùng external ID và quy trình kiểm tra phù hợp.
- **Chọn consistency theo nghiệp vụ.** Invariant cần được bảo vệ tại owner; quy trình liên context có thể cần Saga.
- **Có kế hoạch rollback trước cutover.** Sau khi target nhận write mới, rollback có thể cần đồng bộ ngược hoặc roll-forward.
- **Đối soát theo semantics nghiệp vụ.** Row count không chứng minh dữ liệu đúng.
- **Quản lý migration và quyền riêng.** Mỗi context sở hữu schema và lifecycle dữ liệu của mình.
- **Chỉ tách hạ tầng khi có lý do.** Database/service độc lập đem lại autonomy nhưng tăng chi phí vận hành.

Quản lý dữ liệu theo bounded context là quá trình chuyển quyền sở hữu từ mơ hồ sang rõ ràng. Một context cần có quyền quyết định mô hình, invariant, schema và cách công bố dữ liệu; các context khác tiêu thụ thông tin qua contract hoặc projection. Có thể bắt đầu trong shared database bằng cách cô lập đường ghi và dependency, sau đó tách schema/storage theo từng giai đoạn. Backfill, delta sync, đối soát, cutover và rollback cần được thiết kế như một phần của lộ trình, để việc tách ngữ cảnh không làm mất dữ liệu hoặc làm sai semantics nghiệp vụ.

## 25. Câu hỏi tự kiểm tra

1. Vì sao quyền sở hữu dữ liệu là một phần của ranh giới Bounded Context?
2. Phân biệt Bounded Context, module ứng dụng, deployable service và database/schema.
3. Vì sao shared database có thể chấp nhận được trong một modular monolith?
4. Những dấu hiệu nào cho thấy hệ thống đang có cross-context writes hoặc coupling dữ liệu?
5. Phân biệt source of truth, snapshot, cache và read projection.
6. Khi nào nên dùng query API, integration event hoặc local projection để đọc dữ liệu context khác?
7. Vì sao Sales không nên tự giảm tồn kho bằng SQL trực tiếp?
8. Backfill cần checkpoint, idempotency và delta sync để tránh những rủi ro nào?
9. So sánh Transactional Outbox, CDC, dual write và scheduled delta sync.
10. Expand–Migrate–Contract giúp triển khai thay đổi schema trong rolling deployment như thế nào?
11. Vì sao foreign key xuyên database thường được thay bằng external ID và contract?
12. Khi nào một quy trình liên context cần eventual consistency, Process Manager hoặc compensation?
13. Vì sao rollback sau khi target đã nhận write mới phức tạp hơn rollback trước cutover?
14. Những chỉ số nghiệp vụ nào cần đối soát sau khi chuyển dữ liệu?
15. Hãy chọn một bounded context trong hệ thống của bạn, lập bản đồ reader/writer, xác định source of truth và thiết kế lộ trình tách dữ liệu có backfill, delta sync, cutover và rollback.
