# Quyền sở hữu hành vi, dữ liệu và hợp đồng trong ranh giới microservices

## 1. Vấn đề kiến trúc: ranh giới service thực sự nằm ở đâu?

Trong kiến trúc microservices, một sơ đồ có nhiều ô mang tên Order Service, Payment Service và Inventory Service chưa chứng minh rằng hệ thống đã phân tách trách nhiệm tốt. Nếu Order vẫn sửa bảng thanh toán, Payment vẫn quyết định đơn hàng có được xác nhận hay không, và mọi thay đổi trường dữ liệu đều buộc các service triển khai cùng lúc, các ranh giới được vẽ ra chỉ tồn tại ở mức tiến trình.

Một ranh giới có ý nghĩa phải trả lời được ba câu hỏi liên kết với nhau:

1. **Ai sở hữu hành vi?** Service nào quyết định quy tắc, bất biến và kết quả nghiệp vụ?
2. **Ai sở hữu dữ liệu?** Service nào có quyền cập nhật trạng thái chuẩn và giải thích ý nghĩa của dữ liệu đó?
3. **Ai sở hữu hợp đồng?** Service nào công bố giao diện dùng để yêu cầu hành vi hoặc quan sát thông tin, đồng thời chịu trách nhiệm về ngữ nghĩa và khả năng tương thích của giao diện?

Ba quyền sở hữu này giúp biến một bản đồ năng lực nghiệp vụ thành các đơn vị có khả năng thay đổi độc lập. Chúng cũng là cơ sở để giải quyết tranh chấp khi một chức năng cần dữ liệu hoặc quy tắc của nhiều năng lực.

**Mục tiêu học tập:** Sau bài này, bạn có thể lập bản đồ quyền sở hữu của một hệ thống, phát hiện những phụ thuộc xuyên ranh giới, thiết kế API/sự kiện theo ngữ nghĩa nghiệp vụ, tách quyền đọc khỏi quyền ghi, đánh giá tác động của thay đổi hợp đồng, và lựa chọn cách xử lý một quy trình đi qua nhiều service.

**Phạm vi:** Bài xem xét quyền sở hữu **trong thiết kế phần mềm**. “Sở hữu dữ liệu” ở đây là quyền kiểm soát trạng thái nghiệp vụ và giao diện truy cập, không tự động đồng nghĩa với quyền sở hữu pháp lý, quyền riêng tư của khách hàng hay quyền quản trị toàn bộ hạ tầng vật lý.

## 2. Mô hình tư duy: một ranh giới có ba mặt

Hãy hình dung mỗi service như một đơn vị chịu trách nhiệm trước các service khác:

    Người gọi / hệ thống bên ngoài
                 |
                 | Command, Query, Event
                 v
        +-----------------------+
        | HỢP ĐỒNG CÔNG BỐ      |
        | API / event schema    |
        +-----------+-----------+
                    |
        +-----------v-----------+
        | HÀNH VI NGHIỆP VỤ     |
        | Quy tắc / bất biến    |
        | Quyết định / trạng thái|
        +-----------+-----------+
                    |
        +-----------v-----------+
        | DỮ LIỆU DO SERVICE    |
        | CÓ THẨM QUYỀN QUẢN LÝ |
        | Aggregate / state     |
        +-----------------------+

Service không nhất thiết sở hữu *mọi* dữ liệu mà nó đọc. Nó có thể nhận thông tin từ dịch vụ khác, lưu bản sao phục vụ truy vấn hoặc tính toán kết quả. Điều quan trọng là phải biết **giá trị nào có thẩm quyền**, **ai được phép thay đổi** và **hợp đồng nào cho phép người khác tác động hoặc quan sát**.

Ví dụ:
- Inventory quyết định có đủ số lượng để giữ chỗ và cập nhật lượng đã giữ.
- Order quyết định trạng thái đơn hàng dựa trên các kết quả nghiệp vụ đã nhận.
- Payment quyết định trạng thái một giao dịch thanh toán từ bằng chứng và quy tắc của hệ thanh toán.
- Notification quyết định trạng thái gửi thông báo, nhưng không được quyết định “thanh toán đã thành công” chỉ vì email gửi được.

Mỗi service cần một câu mô tả trách nhiệm ngắn và có thể kiểm thử. Nếu câu đó có nhiều động từ thuộc những lĩnh vực không liên quan, ranh giới có thể quá rộng. Nếu một quy tắc duy nhất phải hỏi năm service rồi mới trả lời được, ranh giới có thể bị chia quá nhỏ hoặc đặt sai chỗ.

### 2.1. Bounded context không phải tên công nghệ

Trong thiết kế hướng miền, **bounded context** là phạm vi mà một mô hình và bộ thuật ngữ có nghĩa nhất quán. Từ “Customer” có thể mang nghĩa khác nhau ở Billing, Marketing và Support; không cần ép cả ba dùng một thực thể hay một lớp Java chung.

Một bounded context là ứng viên cho ranh giới service, nhưng **không bắt buộc** một bounded context tương đương một microservice hoặc một repository. Tổ chức có thể thực hiện các ranh giới này dưới dạng module trong modular monolith trước, rồi tách tiến trình khi nhu cầu phát hành/vận hành thực sự xuất hiện.

### 2.2. Quyền sở hữu phải đi kèm quyền quyết định

Một service được gọi là “chủ sở hữu” khi nó có thẩm quyền:
- Xác thực yêu cầu và cho phép hoặc từ chối chuyển trạng thái.
- Bảo vệ những bất biến thuộc trách nhiệm của mình.
- Cập nhật trạng thái chuẩn qua transaction/đơn vị ghi do mình kiểm soát.
- Công bố hợp đồng và chính sách thay đổi tương thích cho người dùng hợp đồng đó.
- Quan sát, khắc phục, đối soát sự cố và giải thích vì sao trạng thái trở thành như hiện tại.

Nếu service khác có thể trực tiếp sửa dữ liệu, bỏ qua quyết định hoặc tự diễn giải quy tắc của chủ sở hữu, quyền sở hữu vẫn chưa được thực thi.

## 3. Sở hữu hành vi: nơi quy tắc nghiệp vụ được quyết định

### 3.1. Hành vi khác với CRUD

“Có bảng orders nên có Order Service” là cách đặt ranh giới theo dữ liệu. Cách đặt tốt hơn hỏi: **Order có trách nhiệm đưa ra những quyết định nghiệp vụ nào?**

Ví dụ một Order có thể chịu trách nhiệm:
- Nhận yêu cầu tạo đơn và kiểm tra hợp lệ theo quy tắc đặt hàng.
- Chuyển trạng thái từ DRAFT sang PENDING hoặc từ PENDING sang CONFIRMED khi đủ điều kiện.
- Ngăn các chuyển trạng thái trái phép, ví dụ xác nhận đơn đã hủy.
- Quản lý hạn chót xác nhận đơn và các tác động cần diễn ra khi hết hạn.
- Công bố kết quả chuyển trạng thái cho năng lực khác.

Các thao tác HTTP như POST, PATCH hay DELETE chỉ là cách vận chuyển yêu cầu. Hợp đồng nên thể hiện **ý định**: ConfirmOrder, CancelOrder hoặc ReserveInventory, thay vì cho mọi client quyền sửa tùy ý một trường status.

### 3.2. Bất biến nằm ở nơi có quyền bảo vệ

**Bất biến (invariant)** là điều bắt buộc đúng ở thời điểm quyết định quan trọng. Chẳng hạn:

- Một chỗ ngồi không được giữ cho hai đơn hợp lệ cùng lúc.
- Không được hoàn tiền vượt số tiền có thể hoàn.
- Đơn đã bị hủy cuối cùng không thể tự trở lại trạng thái đang xử lý chỉ vì một sự kiện cũ đến trễ.
- Một yêu cầu thu tiền có cùng idempotency key không được tạo hai khoản thu độc lập.

Nếu Inventory sở hữu lượng hàng khả dụng, Inventory phải kiểm tra và áp dụng quy tắc không bán vượt tại thời điểm giữ chỗ. Order không thể dùng số lượng đọc từ cache rồi tự trừ cột tồn kho tại một schema được chia sẻ.

Ví dụ thao tác tại nguồn tồn kho:

~~~sql
UPDATE inventory_stock
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE sku = :sku
  AND available >= :quantity;
~~~

Đây là minh họa về **ghi có điều kiện và tính nguyên tử** tại Inventory. Triển khai thực tế còn phải xác thực quantity dương, kiểm tra số hàng được cập nhật, xử lý retry, kiểm tra chỗ giữ còn hạn và quan hệ giữa tổng tồn/đã giữ. Nếu không cập nhật được hàng nào, Inventory trả kết quả hết hàng hoặc xung đột theo hợp đồng.

Quy tắc “không bán vượt” được bảo vệ ở **nơi sở hữu dữ liệu**. Một kết quả tìm kiếm cũ không thể thay thế quyết định này.

### 3.3. Ai sở hữu hành vi khi cần nhiều năng lực?

Ví dụ “đặt hàng” bao gồm:
1. Order nhận yêu cầu và ghi đơn ở trạng thái đang xử lý.
2. Inventory xử lý việc giữ hàng.
3. Payment xử lý thu tiền.
4. Order xác nhận hoặc từ chối đơn dựa trên các kết quả.
5. Notification gửi thông báo.

Không service nào nên tự ý thực hiện công việc nội bộ của service khác. Một bộ điều phối quy trình (orchestrator) hoặc state machine có thể **sở hữu tiến trình phối hợp**, nhưng không tự nhận quyền quyết định “thanh toán thành công” hoặc “còn hàng” thay cho các service chuyên trách.

Cần phân biệt:
- **Sở hữu quyết định tại năng lực:** Payment chấp nhận, từ chối, hoàn tiền và giải thích trạng thái giao dịch.
- **Sở hữu quy trình xuyên năng lực:** Order hoặc workflow component quyết định bước nào gọi tiếp, thời điểm chờ, bù trừ và khi nào đơn được xác nhận.
- **Sở hữu trình bày:** BFF/UI kết hợp thông tin và quản lý trải nghiệm, nhưng không phải nơi đảm bảo các bất biến thanh toán hay tồn kho.

Một quy trình có thể được phối hợp theo lệnh trung tâm hoặc các bên phản ứng theo sự kiện (choreography). Chọn cơ chế theo độ phức tạp và khả năng quan sát; dù chọn cách nào, quyền quyết định tại mỗi năng lực vẫn cần rõ ràng.

### 3.4. Tránh đặt quy tắc ở client hoặc gateway

API gateway có thể xác thực danh tính, định tuyến, giới hạn tốc độ và thực thi chính sách truy cập chung. BFF có thể chuẩn bị dữ liệu dành cho giao diện. Nhưng nếu gateway chứa thuật toán định giá, hoặc client tự kết luận hoàn tiền được phép dựa trên dữ liệu cũ, quy tắc sẽ bị nhân bản và khó kiểm soát.

Bên gọi có thể kiểm tra sớm để cải thiện trải nghiệm; **service có thẩm quyền vẫn phải kiểm tra lại** trước khi thực hiện hành động.

## 4. Sở hữu dữ liệu: ai quyết định bản ghi nào có hiệu lực?

### 4.1. Sở hữu dữ liệu nghĩa là quyền ghi và diễn giải

Một mô hình thực hành hữu ích:
- Mỗi phần dữ liệu nghiệp vụ quan trọng có **một nguồn sự thật được chỉ định**.
- Service sở hữu là bên **duy nhất cấp quyền ghi hợp lệ** cho phần dữ liệu đó thông qua giao diện hoặc công việc nội bộ mà nó kiểm soát.
- Các service khác có thể đọc qua API, đăng ký sự kiện hoặc giữ **bản sao phục vụ đọc** theo hợp đồng.
- Thay đổi schema vật lý, ràng buộc, ý nghĩa và vòng đời dữ liệu thuộc trách nhiệm chủ sở hữu.

Không có nghĩa mỗi service bắt buộc có một máy database riêng. Hai service có thể đặt schema trong cùng một cụm database để giảm chi phí hạ tầng, nhưng vẫn phải có **quyền truy cập, migration và trách nhiệm logic tách biệt**. Nếu Order có quyền UPDATE trực tiếp bảng Payment, tách instance sau này cũng không tự khôi phục ranh giới.

### 4.2. Một bảng có thể có nhiều người đọc nhưng nên có một nơi ra quyết định ghi

Ví dụ:
- Customer sở hữu hồ sơ liên hệ hiện tại.
- Shipping cần địa chỉ giao nhận tại thời điểm giao.
- Billing cần địa chỉ xuất hóa đơn theo chứng từ.
- Order cần địa chỉ giao hàng được khách xác nhận khi đặt đơn.

Không nên suy ra tất cả chỉ được giữ một bản địa chỉ. Có khác biệt giữa **hồ sơ hiện tại** và **snapshot theo nghiệp vụ**. Order có thể sở hữu bản chụp địa chỉ khi tạo đơn vì đây là sự thật lịch sử của đơn, kể cả sau này Customer thay địa chỉ.

Một mô hình:

    Customer (thông tin liên hệ hiện tại)
         |
         | cung cấp thông tin / hợp đồng xác nhận
         v
    Order (snapshot địa chỉ đã chốt cho đơn)
         |
         +--> Shipping (địa chỉ dùng giao vận)
         +--> Billing  (địa chỉ theo chứng từ)

Việc có nhiều bản sao không trái với quyền sở hữu nếu:
- Mỗi bản sao có **mục đích và thời điểm hiệu lực** rõ ràng.
- Service không dùng bản sao để tùy tiện sửa trạng thái chuẩn của người khác.
- Có chính sách cập nhật hoặc giữ nguyên snapshot phù hợp với nghiệp vụ.

### 4.3. Data ownership không phải cấm mọi bản sao

Các trường hợp sao chép hợp lệ:
- **Read model:** Một service nhận sự kiện OrderConfirmed để lập bảng lịch sử đơn hàng phục vụ truy vấn.
- **Cache:** Giá hoặc thông tin sản phẩm được lưu tạm với thời hạn cụ thể.
- **Snapshot:** Đơn hàng giữ tên sản phẩm, đơn giá và địa chỉ tại thời điểm chốt.
- **Analytics:** Kho dữ liệu được nạp từ các nguồn nghiệp vụ cho báo cáo và phân tích.
- **Search index:** Chỉ mục được tạo lại từ dữ liệu sản phẩm và dữ liệu liên quan.

Điều cần xác định là **mức nhất quán** và khả năng truy xuất nguồn:
- Bản sao có thể trễ bao lâu?
- Dữ liệu nào có thể dùng để ra quyết định và dữ liệu nào chỉ để hiển thị?
- Làm sao xử lý sự kiện trùng, đến trễ, thiếu hoặc sai thứ tự?
- Khi có mâu thuẫn, nguồn nào được tin và cách đối soát?
- Khi có yêu cầu xóa hoặc thay đổi dữ liệu, các bản sao được cập nhật theo nghĩa vụ nào?

### 4.4. Không chia sẻ bảng để tiết kiệm một lời gọi API

Một lỗi thường gặp:

    order-service  ----\
                        +---- shared_db.orders + payments + stock
    payment-service ----/
    inventory-service--/

Đây là **chia sẻ dữ liệu ở mức triển khai nội bộ**. Những thay đổi tên cột, chỉ mục, ràng buộc hoặc transaction của một service có thể phá vỡ service khác. Nó cũng cho phép một service bỏ qua chính sách nghiệp vụ của chủ sở hữu.

Mô hình ranh giới rõ hơn:

    Order ---> Order DB / Order schema
      |
      +-- payment request --> Payment ---> Payment data
      |
      +-- reserve request --> Inventory --> Inventory data

Service có thể dùng cùng hạ tầng database vật lý, nhưng chỉ đi qua hợp đồng công bố khi tương tác xuyên ranh giới nghiệp vụ. Khi cần báo cáo tổng hợp, hãy xem xét read model, query composition hoặc kho phân tích, thay vì nối trực tiếp bảng nội bộ của nhiều service trong một truy vấn nghiệp vụ trực tuyến.

### 4.5. Tham chiếu xuyên service

Order cần biết customerId và skuId nhưng không nhất thiết sở hữu mọi chi tiết Customer hoặc Catalog. Thay vì foreign key vật lý xuyên database service, có thể dùng **tham chiếu định danh** cùng cơ chế xác thực nghiệp vụ:
- Khi tạo đơn, kiểm tra mã sản phẩm có thể giao dịch được theo quy tắc được công bố.
- Lưu những thuộc tính cần giữ làm snapshot.
- Chấp nhận rằng thông tin tham khảo có thể thay đổi sau.
- Thiết kế cách xử lý trường hợp bản ghi nguồn bị vô hiệu hóa hoặc không còn đọc được.

Không dùng “không có foreign key xuyên service” để bỏ qua tính đúng đắn. Bất biến liên quan vẫn phải có cơ chế kiểm tra phù hợp, ví dụ xác nhận tại thời điểm đặt hàng hoặc quy trình giữ chỗ.

## 5. Sở hữu hợp đồng: ai công bố cách tương tác?

**Hợp đồng (contract)** là cam kết mà bên gọi có thể dựa vào khi tương tác với một service. Nó gồm nhiều hơn hình dạng JSON:
- Ý nghĩa nghiệp vụ của lệnh, kết quả và trạng thái.
- Trường dữ liệu, kiểu, đơn vị đo, giá trị hợp lệ, ý nghĩa thiếu/null.
- Mã lỗi và khả năng thử lại.
- Quy tắc xác thực và phân quyền.
- Idempotency, thứ tự, độ trễ, phân trang, timeout và giới hạn tải khi có cam kết.
- Phiên bản và cách thay đổi tương thích.
- Với sự kiện: thời điểm sự kiện được coi là xảy ra, chủ thể phát, cách đọc phiên bản, khả năng gửi trùng hoặc phát lại.

Một API trả HTTP 200 vẫn có thể vi phạm hợp đồng nếu nó trả “đã thanh toán” khi mới chỉ tiếp nhận yêu cầu từ nhà cung cấp thanh toán.

### 5.1. Hợp đồng lệnh khác hợp đồng truy vấn

**Command:** Yêu cầu một service *thử thực hiện hành vi*.

~~~http
POST /inventory/reservations
Idempotency-Key: reserve-order-ord-123

{
  "orderId": "ord-123",
  "items": [
    { "sku": "SKU-7", "quantity": 2 }
  ]
}
~~~

Ví dụ phản hồi thành công:

~~~json
{
  "reservationId": "res-456",
  "status": "RESERVED",
  "expiresAt": "2026-11-12T10:00:00Z"
}
~~~

Ý nghĩa: Inventory đã áp dụng các điều kiện nghiệp vụ và thực hiện giữ chỗ theo chính sách, không chỉ nhận JSON hợp lệ. Idempotency key ngăn cùng một yêu cầu được thử lại tạo ra hai lần giữ chỗ không chủ ý, **trong phạm vi chính sách lưu giữ và nhận diện request mà API công bố**.

**Query:** Yêu cầu xem dữ liệu đã biết, có thể qua read model.

~~~http
GET /orders/ord-123/summary
~~~

~~~json
{
  "orderId": "ord-123",
  "status": "CONFIRMED",
  "sourceVersion": 12,
  "projectionUpdatedAt": "2026-11-12T09:58:00Z"
}
~~~

Nếu summary là projection bất đồng bộ, hợp đồng phải chỉ rõ độ trễ có thể xảy ra. Việc Query trả giá trị cũ **không cấp quyền** cho bên gọi tự sửa trạng thái chuẩn để “làm cho khớp”.

### 5.2. Event contract mô tả sự thật đã xảy ra

Sự kiện miền (domain event) nên diễn đạt một điều đã xảy ra dưới thẩm quyền service sở hữu:

~~~json
{
  "eventId": "evt-9f1",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "aggregateId": "res-456",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-12T09:57:00Z",
  "data": {
    "orderId": "ord-123",
    "reservationId": "res-456"
  }
}
~~~

Inventory có quyền công bố InventoryReserved vì chính nó quyết định việc giữ hàng. Order có thể nhận sự kiện để tiếp tục quy trình, nhưng không nên diễn giải nó thành “PaymentSucceeded”.

**Sự kiện khác lệnh:** InventoryReserved nói việc giữ hàng đã xảy ra; ReserveInventory là yêu cầu để việc đó xảy ra. Trộn lẫn hai ý nghĩa khiến consumer khó biết có được phép từ chối hay cần tự thực hiện thao tác nào.

Một sự kiện integration không cần công bố toàn bộ model nội bộ. Trường dữ liệu nên đủ cho mục đích hợp đồng, tránh lộ chi tiết bảng, khóa nội bộ không cần thiết hoặc dữ liệu nhạy cảm.

### 5.3. Chủ sở hữu hợp đồng chịu trách nhiệm gì?

Với API/sự kiện do service công bố, đội sở hữu:
- Viết tài liệu mô tả ngữ nghĩa thay vì chỉ liệt kê trường.
- Định nghĩa lỗi, trạng thái trung gian và điều kiện hoàn tất.
- Duy trì phiên bản/hướng tiến hóa tương thích trong thời gian thỏa thuận.
- Xây dựng kiểm thử hợp đồng với những cách sử dụng đã biết.
- Công bố kế hoạch bỏ tính năng, thời hạn và đường chuyển đổi.
- Theo dõi sự cố hợp đồng, tăng độ trễ và thay đổi hành vi.
- Phối hợp người tiêu thụ hợp đồng khi có thay đổi phá vỡ tương thích.

**Người tiêu thụ cũng có trách nhiệm:** Dùng trường theo nghĩa đã công bố, chịu được trường không liên quan nếu định dạng cho phép, công bố những kỳ vọng quan trọng và kiểm thử các luồng của mình. Quyền sở hữu contract không có nghĩa bên cung cấp được đổi tùy ý không thông báo.

## 6. Ba quyền sở hữu phải ăn khớp nhau

Một thiết kế có thể mắc lỗi ngay cả khi từng mặt nhìn riêng có vẻ hợp lý.

| Tình huống | Quyền sở hữu nào đang lệch? | Hệ quả |
|---|---|---|
| Order gửi UPDATE trực tiếp vào bảng Inventory | Dữ liệu và hành vi | Bỏ qua quy tắc giữ chỗ, khó thay schema |
| Payment trả trường rawGatewayStatus, client tự kết luận giao dịch hoàn tất | Hợp đồng và hành vi | Mỗi consumer hiểu trạng thái theo cách khác |
| Hai service cùng có endpoint SetCustomerStatus, cùng ghi một bảng | Hành vi và dữ liệu | Không có nơi giải quyết xung đột có thẩm quyền |
| Inventory phát event ProductPriceChanged dù không quản lý giá | Hợp đồng và trách nhiệm nghiệp vụ | Người nhận tin nhầm nguồn sự thật |
| Catalog sở hữu giá, Checkout lưu đơn giá đã chốt | Có thể đúng nếu phân biệt snapshot | Mỗi dữ liệu có thời điểm và nghĩa riêng |
| BFF tập hợp thông tin Order, Payment, Inventory để trình bày | Có thể đúng nếu chỉ là đọc | BFF không được tự quyết định bất biến |
| Order điều phối giữ hàng và thanh toán | Có thể đúng nếu Order chỉ sở hữu quy trình | Mỗi service vẫn kiểm tra lệnh của mình |

Một câu hỏi kiểm tra nhanh: **Nếu đổi quy tắc nghiệp vụ này, ai phải sửa code? Nếu đổi cách lưu dữ liệu, ai phải deploy? Nếu đổi định dạng hợp đồng, ai cần được thông báo?** Nếu câu trả lời mặc định luôn là “mọi service”, ranh giới có vấn đề.

## 7. Ví dụ xuyên suốt: đặt hàng, thanh toán và tồn kho

Giả sử một hệ thống thương mại điện tử gồm Catalog, Pricing, Order, Inventory, Payment và Notification.

### 7.1. Bản đồ trách nhiệm

| Năng lực | Hành vi sở hữu | Dữ liệu có thẩm quyền | Hợp đồng công bố |
|---|---|---|---|
| Catalog | Quản lý thông tin danh mục và trạng thái công bố sản phẩm | Product, category, mô tả hiện tại | ProductPublished, GetProduct |
| Pricing | Định giá và áp dụng chính sách giá tại thời điểm được yêu cầu | Price rule, price list, version | QuotePrice, PriceChanged |
| Order | Tạo, quản lý vòng đời và xác nhận đơn theo kết quả nghiệp vụ | Order, order lines, trạng thái đơn, snapshot đã chốt | CreateOrder, CancelOrder, OrderConfirmed |
| Inventory | Quyết định lượng khả dụng và giữ/giải phóng hàng | Stock, reservation, movement | ReserveStock, ReleaseReservation, InventoryReserved |
| Payment | Thu tiền, lưu trạng thái giao dịch và hoàn tiền | PaymentAttempt, transaction, refund | ChargePayment, RefundPayment, PaymentSucceeded |
| Notification | Gửi thông báo, quản lý template và trạng thái giao | Message, delivery attempt, template | SendNotification, MessageDelivered |

Bảng trên chỉ là **một cách phân ranh giới**. Một tổ chức có thể kết hợp Catalog và Pricing nếu quy tắc liên quan chặt và nhịp thay đổi giống nhau. Điều quan trọng là bảo đảm một quyết định không bị tách thành nhiều nơi cùng có quyền sửa.

### 7.2. Giá hiển thị và giá chốt đơn

Khách xem giá 100.000 đồng từ danh mục. Sau đó Pricing cập nhật giá còn 95.000 đồng. Khi tạo đơn, Order không nên lấy “giá hiện trên trình duyệt” làm thẩm quyền cuối cùng nếu chính sách buộc xác minh giá tại thời điểm chốt.

Luồng có thể là:

    Client -- CreateOrder(items) --> Order
                                     |
                                     +-- QuotePrice --> Pricing
                                     |     price + version + expiry
                                     |
                                     +-- ReserveStock --> Inventory
                                     |     reservationId
                                     |
                                     +-- Commit Order(snapshot price)
                                           |
                                           +-- Proceed Payment

Order lưu snapshot đơn giá có hiệu lực cho đơn đã được chấp nhận, còn Pricing vẫn sở hữu chính sách tính giá hiện tại. Khi Pricing đổi cách tính thuế, khuyến mãi hay bảng giá, Order không nên sao chép toàn bộ thuật toán ấy vào code để tránh lời gọi API.

Nếu nghiệp vụ cho phép báo giá có thời hạn, hợp đồng QuotePrice cần nói rõ:
- Giá trị, đơn vị tiền tệ, thuế/phí đã gồm hay chưa.
- Thời điểm hết hiệu lực hoặc điều kiện thay đổi.
- Định danh/version để xác minh hoặc ghi vào đơn.
- Cách xử lý khi mã khuyến mãi không còn hợp lệ.
- Một đơn nhiều mặt hàng cần tính nhất quán tổng thể ra sao.

### 7.3. Inventory không có quyền thu tiền

Sau khi giữ hàng, Order có thể yêu cầu Payment thực hiện thu tiền. Payment phải bảo vệ idempotency, theo dõi trạng thái tại nhà cung cấp và xử lý trường hợp timeout không rõ đã thu hay chưa.

Nếu Payment trả trạng thái PENDING, Order không được tự suy ra FAILED và thử thu tiền mới bằng khóa khác ngay lập tức. Cần theo dõi hoặc đối soát theo hợp đồng. PaymentSucceeded chỉ được công bố khi Payment có bằng chứng đủ theo chính sách của mình.

Khi Payment thất bại, Order điều phối việc giải phóng tồn kho. Nhưng Order không cập nhật trực tiếp inventory_reservation thành RELEASED. Nó gửi yêu cầu phù hợp cho Inventory; Inventory thực hiện chuyển trạng thái và công bố kết quả.

### 7.4. Notification không kiểm soát trạng thái đơn

Một consumer nhận OrderConfirmed để gửi email xác nhận. Nó có thể retry, dùng template và cập nhật delivery log. Nếu email thất bại, tùy chính sách, đơn vẫn có thể giữ CONFIRMED. Gửi email không thành công không đủ để tự hủy một đơn đã hoàn tất nghiệp vụ.

Tách bạch này tránh tình trạng lỗi nhà cung cấp email lan truyền thành lỗi đặt hàng.

## 8. Đặt ranh giới theo quy tắc và sự thay đổi

Không có thuật toán duy nhất chọn đúng microservice. Có thể tiến hành theo các bước:

### Bước 1 — Xác định năng lực và ngôn ngữ nghiệp vụ

Phỏng vấn người làm sản phẩm và chuyên gia miền: đâu là các sự kiện quan trọng, quyết định có hậu quả, dữ liệu và điều kiện thành công? Ghi thuật ngữ theo ngữ cảnh. Ví dụ “trạng thái thanh toán” ở Payment có thể có AUTHORIZED, CAPTURED, REFUNDED; ở Order có thể chỉ cần AWAITING_PAYMENT, PAID hoặc FAILED theo nghĩa quản lý đơn.

Tránh cố dùng một enum trạng thái toàn công ty khi các ngữ cảnh có nghĩa khác nhau.

### Bước 2 — Gom các quy tắc cần cùng thay đổi

Xem lịch sử thay đổi và tình huống nghiệp vụ. Những quy tắc thường phải thay cùng nhau, cùng bảo vệ một bất biến và cùng dùng một ngôn ngữ miền có thể nên ở cùng ranh giới.

Các gợi ý:
- Quy tắc chuyển trạng thái và dữ liệu aggregate nên gần nhau.
- Những chức năng chỉ gắn với nhau do màn hình UI chưa chắc thuộc một service.
- Những dữ liệu cùng nằm trong một database cũ chưa chắc có cùng chủ sở hữu miền.
- Một nhóm kỹ sư sở hữu nhiều năng lực chưa có nghĩa cần gộp hết thành một service.

### Bước 3 — Vẽ bảng quyền quyết định

Với từng hành vi, ghi:
- Ai nhận command?
- Ai có quyền đồng ý/từ chối và tại sao?
- Bất biến nào phải luôn đúng?
- Dữ liệu chuẩn nào cần đọc/ghi trong quyết định?
- Ai phát sự kiện xác nhận đã xảy ra?
- Service nào chỉ quan sát/kết hợp thông tin?

Nếu một hàng có hai service đều mang vai trò quyết định cuối cùng, cần tìm nguyên nhân. Có thể đó là hai quyết định khác nhau đang dùng cùng tên; cũng có thể ranh giới chưa xác định rõ.

### Bước 4 — Liệt kê phụ thuộc xuyên ranh giới

Phân biệt:
- **Phụ thuộc tại thời điểm quyết định:** Order phải biết Inventory có thể giữ hàng không.
- **Phụ thuộc dữ liệu:** Reporting cần tổng hợp Order và Payment.
- **Phụ thuộc sự kiện:** Notification cần biết khi OrderConfirmed.
- **Phụ thuộc phát hành:** Một đổi schema Order luôn buộc Payment triển khai cùng lúc.
- **Phụ thuộc quy trình:** Hai service phải phối hợp để hoàn thành một công việc có nhiều bước.

Mỗi loại có giải pháp khác nhau: hợp đồng đồng bộ, read model, sự kiện, thay đổi tương thích theo giai đoạn hoặc workflow/state machine. Không nên xử lý mọi phụ thuộc bằng cách nối thêm API đồng bộ.

### Bước 5 — Thử một thay đổi nghiệp vụ

Chọn ví dụ: “Thêm chính sách giữ hàng 15 phút cho đơn chưa thanh toán”. Hỏi:
- Có sửa mỗi Inventory và phần điều phối ở Order theo hợp đồng đã có không?
- Payment có cần đổi schema vì lý do không liên quan không?
- Có service nào truy cập trực tiếp trường expires_at của Inventory rồi phụ thuộc cách lưu nội bộ?
- Có thể thử nghiệm và triển khai thay đổi theo giai đoạn mà consumer phiên bản cũ vẫn hoạt động?

Một ranh giới tốt làm cho thay đổi có liên quan **tập trung ở nơi chịu trách nhiệm**, và ảnh hưởng lên phần còn lại được kiểm soát qua hợp đồng.

## 9. Thiết kế API để giữ quyền sở hữu hành vi

### 9.1. Công bố ý định, không mở cổng sửa bảng

API kiểu:

~~~http
PATCH /inventory/items/SKU-7
{ "available": 100 }
~~~

cho phép client áp một giá trị có thể bỏ qua quy tắc nghiệp vụ. Với phần mềm chỉ dành cho quản trị kho có kiểm soát, API như vậy có thể hợp lý nếu quy tắc được thực thi phía server. Nhưng với consumer nghiệp vụ như Order, API sau thường rõ ý hơn:

~~~http
POST /inventory/reservations
{
  "orderId": "ord-123",
  "sku": "SKU-7",
  "quantity": 2
}
~~~

Ý định “giữ 2 đơn vị” cho phép Inventory thực hiện kiểm tra tồn, xung đột đồng thời, hạn giữ, tồn bị khóa, quy tắc phân bổ và audit. API không cần để lộ cách lưu bảng tồn kho.

### 9.2. Hợp đồng lỗi là một phần của quyền quyết định

Ví dụ ReserveStock có thể trả:
- **RESERVED:** Giữ hàng thành công; có reservationId và hạn giữ.
- **INSUFFICIENT_STOCK:** Quy tắc nghiệp vụ từ chối, thử lại ngay với cùng điều kiện thường không hữu ích.
- **CONFLICT:** Trạng thái thay đổi đồng thời, có thể thử lại sau khi đọc/đánh giá lại.
- **PENDING:** Hệ thống đã nhận yêu cầu nhưng chưa hoàn thành; client cần tra trạng thái theo requestId.
- **UNAVAILABLE:** Không thể quyết định tại thời điểm này; không được tự suy thành hết hàng hoặc đã giữ hàng.

Mã HTTP, error body và semantics phải được cụ thể hóa. Không nên để client dựa vào chuỗi thông báo tiếng Anh rồi suy ra quyết định giao dịch.

### 9.3. Tính lặp an toàn và giới hạn hiệu lực

Khi mạng lỗi, client có thể gửi cùng lệnh nhiều lần. Chủ sở hữu command cần quyết định idempotency:
- Khóa định danh yêu cầu theo caller/tenant/phạm vi phù hợp.
- Cùng khóa với cùng nội dung trả về kết quả cũ hoặc trạng thái tương ứng.
- Cùng khóa nhưng payload khác phải được xử lý theo chính sách xung đột.
- Có thời hạn lưu khóa được công bố khi cần.
- Tác động phụ như gửi thông điệp hoặc gọi payment provider cũng phải được bảo vệ theo ranh giới tương ứng.

Không nên tuyên bố “exactly once” toàn hệ thống chỉ vì message broker hỗ trợ một tính năng tên tương tự. Tác động qua nhiều datastore, HTTP và nhà cung cấp bên ngoài cần thiết kế chống trùng và đối soát.

### 9.4. Ngữ nghĩa hợp đồng quan trọng hơn DTO

Một DTO chứa trường status, amount hoặc version vẫn chưa đủ. Người dùng API cần biết:
- amount tính theo đơn vị nhỏ nhất hay đơn vị tiền tệ thông thường?
- status đã xác nhận cuối cùng hay mới được xử lý cục bộ?
- createdAt do client hay server quyết định?
- Có thể thấy bản ghi vừa tạo trên endpoint query lập tức không?
- Quy trình có thể kết thúc bằng trạng thái chưa xác định không?
- Điều gì xảy ra khi nhận nhiều lệnh hủy cùng một giao dịch?

Tài liệu OpenAPI, AsyncAPI hoặc schema registry giúp diễn tả cấu trúc; quy tắc nghiệp vụ vẫn cần mô tả và kiểm thử bằng trường hợp cụ thể.

## 10. Hợp đồng sự kiện và quyền sở hữu dữ liệu phát sinh

### 10.1. Event không nên là bản sao nguyên bảng

Một lỗi thiết kế là dùng sự kiện như cơ chế nhân bản mọi cột của bảng nội bộ: mỗi lần thay schema cần cập nhật hàng loạt consumer. Event nên cho consumer biết **sự thật nghiệp vụ có ích** và dữ liệu tối thiểu mà hợp đồng cho phép phụ thuộc.

Ví dụ OrderConfirmed có thể gồm orderId, version, thời điểm, tham chiếu khách hàng và những dữ liệu cần thiết cho use case đã thống nhất. Những trường nhạy cảm hoặc cấu trúc nội bộ không liên quan nên được loại trừ; consumer cần thêm dữ liệu có thể yêu cầu qua hợp đồng khác hoặc được bổ sung có kiểm soát.

### 10.2. Ai có quyền phát sự kiện?

Quy tắc hữu ích: service nào có thẩm quyền kết luận một sự thật thì service đó nên là **nguồn công bố đáng tin cậy** cho sự thật ấy.

- Payment phát PaymentCaptured sau khi trạng thái giao dịch đủ điều kiện.
- Inventory phát StockReserved khi quyền giữ chỗ được cấp.
- Order phát OrderConfirmed khi đơn đạt điều kiện xác nhận.
- Notification phát NotificationDelivered khi bằng chứng gửi thông báo đủ theo định nghĩa hợp đồng.

Một service trung gian có thể chuyển tiếp, kết hợp hoặc biến đổi sự kiện cho mục đích integration, nhưng cần định danh rõ **sự kiện nguồn**, **thẩm quyền** và quy tắc biến đổi. Tránh “event tên giống nhau” do nhiều service tự công bố từ các phỏng đoán khác nhau.

### 10.3. Đồng bộ transaction và phát thông điệp

Nếu một service ghi OrderConfirmed vào database rồi gọi broker như hai thao tác độc lập, có nguy cơ commit thành công nhưng sự kiện không phát được. Một cách giảm rủi ro là **transactional outbox**:

~~~text
Transaction của Order:
  1. Kiểm tra trạng thái và bất biến của Order.
  2. Chuyển trạng thái hợp lệ.
  3. Ghi bản ghi outbox với eventId và payload hợp đồng.
  4. Commit cùng một transaction.

Publisher:
  5. Đọc outbox và chuyển sự kiện sang broker.
  6. Đánh dấu đã phát theo cơ chế khôi phục.
~~~

Publisher có thể gửi trùng khi crash sau broker ACK. Consumer phải nhận diện trùng và cập nhật read model an toàn. Outbox giải quyết sự nhất quán giữa trạng thái cục bộ và ý định phát thông điệp trong phạm vi transaction; không tự bảo đảm mọi consumer đã xử lý đúng.

### 10.4. Đừng để thứ tự đến quyết định ý nghĩa nghiệp vụ

Ví dụ PaymentSucceeded có version 8 đến trước PaymentPending version 7; consumer không được làm đơn “quay ngược”. Hợp đồng nên có aggregateId và version hoặc cơ chế thứ tự phù hợp. Nếu event biểu diễn **snapshot trạng thái đầy đủ**, consumer có thể bỏ qua version thấp hơn. Nếu event là **delta** phụ thuộc chuỗi trước, consumer phải đảm bảo replay đầy đủ hoặc thiết kế lại cách áp dụng.

Đồng thời, cần phân biệt sự kiện của **hai aggregate khác nhau**: không nên kỳ vọng thứ tự toàn cục nếu broker chỉ đảm bảo thứ tự trong một key/partition.

## 11. Tiến hóa hợp đồng mà không buộc triển khai đồng bộ

Quyền sở hữu hợp đồng chỉ đem lại quyền tự chủ khi API/event có đường tiến hóa cho phép client và server chạy khác phiên bản trong một khoảng chuyển đổi.

### 11.1. Thay đổi thường tương thích

Tùy hợp đồng và cách parse của consumer, ví dụ:
- Bổ sung trường tùy chọn có mặc định/ngữ nghĩa rõ ràng.
- Bổ sung endpoint mới mà không thay đổi endpoint cũ.
- Bổ sung phiên bản schema/event mới có cơ chế consumer chuyển tiếp.
- Giữ hành vi cũ trong lúc giới thiệu một lệnh mới.

Nhưng “thêm trường” không phải lúc nào cũng vô hại. Consumer dùng parser nghiêm ngặt, switch exhaustive trên enum, signature checking hoặc kiểm tra kích thước payload có thể bị ảnh hưởng. **Tương thích phải được xác nhận theo consumer thực tế**, không dựa trên một quy tắc chung mơ hồ.

### 11.2. Thay đổi có thể phá vỡ

Ví dụ:
- Đổi tên hoặc xóa trường mà client đang dùng.
- Thay kiểu number thành string hoặc đổi đơn vị tiền tệ.
- Đổi ý nghĩa status từ “đã nhận yêu cầu” sang “đã hoàn tất”.
- Thêm giá trị enum mà consumer coi là không hợp lệ.
- Biến endpoint từng có tính idempotent thành tạo nhiều tác động.
- Thay thứ tự hoặc ý nghĩa sự kiện mà consumer phụ thuộc.

Đây là các thay đổi ở **hợp đồng quan sát**, ngay cả khi schema JSON vẫn hợp lệ.

### 11.3. Quy trình expand – migrate – contract

Với thay đổi làm ảnh hưởng consumer:
1. **Expand:** Service cung cấp hỗ trợ đồng thời cũ/mới, hoặc bổ sung trường/endpoint mới.
2. **Migrate:** Consumer chuyển dần; có kiểm thử hợp đồng, canary và giám sát thực tế.
3. **Contract:** Chỉ bỏ đường cũ sau khi đáp ứng thời hạn và chứng minh consumer liên quan đã chuyển.

Ví dụ đổi displayName sang legalName và preferredName:
- Giai đoạn đầu tiếp tục trả displayName như trước, bổ sung hai trường mới.
- Các consumer cập nhật để hiểu hai trường mới.
- Theo dõi nơi còn sử dụng displayName.
- Xóa field cũ khi hợp đồng và thời điểm ngừng hỗ trợ đã được thống nhất.

Đối với database schema nội bộ, cũng cần phương án tương thích giữa code và schema khi rollout/rollback. Chủ sở hữu dữ liệu quyết định migration; consumer không được viết migration trực tiếp vào schema của service khác.

### 11.4. Consumer-driven contract tests

Một consumer có thể công bố kỳ vọng như:
- Với ReserveStock số lượng 2 còn đủ, phản hồi chứa reservationId và trạng thái RESERVED.
- Với khóa request đã xử lý, gửi lại không tạo thêm reservation.
- Trong giai đoạn schema mới, field cũ vẫn giữ ý nghĩa đã công bố.

Provider kiểm thử những kỳ vọng được chấp nhận trong pipeline. Đây là công cụ kiểm chứng **mức giao diện**; không thay thế kiểm thử quy tắc nghiệp vụ, thử tương tác thực tế hoặc quan sát sự cố khi triển khai.

## 12. Khi dịch vụ cần dữ liệu của nhau

### 12.1. Gọi API đồng bộ khi cần quyết định tức thời

Order có thể cần một báo giá chắc chắn trước khi nhận đơn. Gọi Pricing để lấy quote là hợp lý nếu nghiệp vụ cần kết quả tức thời và hệ thống có chính sách timeout/fallback rõ.

Tuy nhiên, hãy tránh chuỗi:

    API -> Order -> Pricing -> Customer -> Loyalty -> Promotion -> Tax -> Inventory

Nếu mọi service phải sẵn sàng mới trả được một response, latency và khả năng lỗi tăng theo các phụ thuộc. Cần xem lại liệu một số quy tắc cùng thuộc một năng lực, có thể được gom vào quote, dùng snapshot hợp lệ hoặc xử lý theo trạng thái đang chờ.

### 12.2. Read model để ghép dữ liệu khi hiển thị

Trang “Đơn hàng của tôi” có thể cần Order status, Payment status và thông tin giao vận. Có ba lựa chọn điển hình:
- **API composition:** BFF/query service gọi các service liên quan rồi ghép kết quả tại thời điểm truy vấn.
- **Materialized view:** Consumer xây bảng đọc riêng từ sự kiện do các chủ sở hữu phát.
- **Hybrid:** Một số dữ liệu được sao chép, một số được truy vấn khi cần xác nhận.

Lựa chọn phụ thuộc yêu cầu độ tươi, độ trễ, quy mô truy vấn và khả năng chịu lỗi. BFF có thể sở hữu **trải nghiệm kết hợp**, nhưng không vì thế sở hữu bất biến của Payment.

### 12.3. Snapshot cho ngữ nghĩa lịch sử

Một đơn được chốt với giá, tên sản phẩm hoặc điều khoản vận chuyển tại thời điểm đặt hàng. Khi Catalog hoặc Pricing đổi, bản ghi đơn cũ không nên tự thay đổi nếu hợp đồng nghiệp vụ yêu cầu giữ lịch sử. Order sở hữu **snapshot đơn đã xác nhận**, còn Catalog/Pricing sở hữu trạng thái hiện tại và quy tắc định giá.

Việc sao chép này hợp lệ khi được diễn giải theo thời điểm. Nếu consumer coi snapshot là nguồn giá hiện tại cho mọi đơn tương lai, đó là lẫn lộn quyền sở hữu.

## 13. Quy trình nhiều service: trách nhiệm, lỗi và bù trừ

Một nghiệp vụ xuyên service không có transaction ACID tự động. Khi mỗi service sở hữu dữ liệu, quy trình thường dùng nhiều transaction cục bộ kết hợp trạng thái trung gian.

Ví dụ đơn hàng:

    NEW
      |
      v
    PENDING_STOCK --InventoryRejected--> REJECTED
      |
      | InventoryReserved
      v
    PENDING_PAYMENT --PaymentFailed--> CANCELLING
      |                                |
      | PaymentSucceeded               +-- ReleaseStock --> CANCELLED
      v
    CONFIRMED

Order điều phối tiến trình nhưng Inventory vẫn là nơi duy nhất cấp/giải phóng reservation; Payment vẫn là nơi quyết định kết quả thu tiền. Sự kiện cũ đến sau phải được chặn bằng version và trạng thái chuyển hợp lệ.

### 13.1. Bù trừ không luôn đảo ngược hoàn hảo

Nếu Payment đã thu tiền nhưng Order không thể xác nhận, hành động phù hợp có thể là yêu cầu refund. **Refund** là một nghiệp vụ mới với trạng thái và tác động riêng, không phải xóa transaction cũ. Nếu email đã gửi, không thể “unsend” một cách đảm bảo. Vì vậy cần thiết kế trạng thái có thể đối soát và cách xử lý thủ công.

### 13.2. Không nhầm lỗi mạng với từ chối nghiệp vụ

Timeout khi gọi Payment có thể có nghĩa:
- Lệnh chưa được nhận.
- Lệnh đã nhận nhưng đang xử lý.
- Đã thu tiền nhưng phản hồi bị mất.
- Provider chưa xác nhận kết quả.

Không nên tự cho timeout là PaymentFailed. Chủ sở hữu Payment cần cung cấp cách kiểm tra trạng thái theo paymentAttemptId hoặc idempotency key và chính sách thử lại an toàn.

### 13.3. Ai sở hữu sự thật cuối cùng của quy trình?

Sự thật “PaymentCaptured” thuộc Payment. Sự thật “OrderConfirmed” thuộc Order sau khi kết hợp những điều kiện nghiệp vụ cần thiết. Những sự thật này có thể được ghi ở những thời điểm khác nhau; nếu màn hình tổng hợp chưa nhận event, nó có thể chậm hơn. API phải diễn đạt trạng thái đủ chính xác để người dùng không bị hứa sai.

## 14. Tách service khỏi database hoặc monolith cũ

Khi bắt đầu từ monolith, dữ liệu và hành vi thường đan xen; tách tiến trình ngay có thể tạo các lời gọi vòng quanh database chung. Nên dùng cách chuyển đổi theo giai đoạn.

### 14.1. Xác định vùng sở hữu trước

Lập danh mục hành vi và bảng:
- Bảng nào có một owner nghiệp vụ rõ ràng?
- Bảng nào nhiều module đang ghi?
- Rule nào được lặp trong controller, job, trigger hoặc stored procedure?
- Những transaction nào kéo qua nhiều phần nghiệp vụ?
- Những truy vấn join nào phục vụ nghiệp vụ tức thời, những truy vấn nào chỉ để báo cáo?

Mục tiêu là hiểu **vì sao** mã phụ thuộc, không chỉ đếm số bảng.

### 14.2. Dựng giao diện trước khi chuyển dữ liệu

Đưa hành vi qua một module/API sở hữu trong cùng codebase. Ví dụ thay các chỗ sửa trực tiếp cột tồn kho bằng ReserveStock tại module Inventory. Tại giai đoạn này có thể vẫn là một deployment và một database, nhưng ranh giới quyền ghi đã rõ hơn.

Có thể dùng **anti-corruption layer** để dịch mô hình bên ngoài sang thuật ngữ của miền hiện tại, tránh để model của hệ legacy lan vào service mới. Đây là lớp chuyển đổi có mục tiêu, không phải nơi chứa toàn bộ logic nghiệp vụ mới.

### 14.3. Chuyển nguồn ghi và bản sao đọc có kiểm soát

Một lộ trình minh họa:
1. Chuẩn hóa command và hợp đồng đọc của năng lực.
2. Xác định source of truth và thực thi quyền ghi qua owner.
3. Đưa schema/migration dưới trách nhiệm owner và thu hồi đường ghi chéo.
4. Khi cần, tạo projection/CDC cho những consumer từng đọc bảng trực tiếp.
5. So sánh kết quả cũ/mới bằng đối soát và log trong giai đoạn chuyển đổi.
6. Chuyển traffic từng phần bằng feature flag, route hoặc strangler pattern.
7. Chỉ loại bỏ đường cũ sau khi không còn consumer phụ thuộc và có phương án phục hồi.

Cần thận trọng với dual write ở giai đoạn chuyển đổi: ghi cùng một thay đổi vào hai database theo hai lệnh độc lập có thể gây lệch trạng thái. Ưu tiên một nguồn ghi chuẩn và cơ chế sao chép/đồng bộ có khả năng replay/đối soát. Khi phải dùng dual write, cần chính sách xung đột và phục hồi được thiết kế rõ.

### 14.4. Không lấy tách hạ tầng làm thước đo duy nhất

Sau khi tách, các dấu hiệu quyền sở hữu thực sự là:
- Không có cập nhật trực tiếp vào schema của service khác.
- Quy tắc miền và state transition nằm tại nơi có thẩm quyền.
- API/event được quản trị và thay đổi tương thích.
- Service có thể triển khai thay đổi bình thường mà không buộc consumer nâng cấp cùng một lúc.
- Lỗi, bản sao chậm và quy trình dài được quan sát và khôi phục có chủ sở hữu.

Một database riêng mà vẫn chia sẻ Java entity/domain library và buộc synchronized deployment chưa phải ranh giới tốt.

## 15. Quyền sở hữu trong tổ chức và phân quyền hạ tầng

### 15.1. Đội chịu trách nhiệm sản phẩm và vận hành

Ngoài mô hình code, cần chỉ định đội/người chịu trách nhiệm:
- Sự chính xác của quy tắc nghiệp vụ và trạng thái.
- Khả năng hoạt động của API/event đã cam kết.
- Thời gian phản hồi, sức chứa, bảo mật và xử lý sự cố.
- Lịch migration, deprecation và thông báo đến consumer.
- Runbook khôi phục, backfill và đối soát dữ liệu.

Một đội có thể sở hữu nhiều service; một service có thể cần nhiều chuyên gia phối hợp. Nhưng **quyền quyết định cuối cùng** cho một thay đổi và người nhận cảnh báo phải rõ ràng. Tránh mô hình “tất cả cùng sở hữu” khiến không ai có trách nhiệm cuối.

### 15.2. Ownership là quyền kiểm soát, không phải quyền truy cập vô hạn

Service Order có thể được phép **đọc thông tin tối thiểu** từ Customer nhưng không được truy cập mọi thông tin cá nhân. Payment có thể cần token thanh toán nhưng không vì thế cho Order quyền đọc secret hoặc dữ liệu thẻ. Các service phải có quyền hệ thống theo nguyên tắc cần đến đâu cấp đến đó.

Biện pháp thực thi có thể gồm:
- Credential riêng theo service, hạn chế SELECT/UPDATE/DDL theo schema.
- Authentication và authorization giữa các service.
- Kiểm tra phạm vi tenant và quyền người dùng khi xử lý command.
- Audit log cho hành động nhạy cảm.
- Mã hóa, lưu giữ và xóa dữ liệu theo yêu cầu áp dụng.

Ranh giới dữ liệu chỉ đáng tin khi quyền truy cập kỹ thuật không cho phép các đường vòng vô tình.

### 15.3. Platform team không thay thế business owner

Đội nền tảng có thể sở hữu Kubernetes, CI/CD, observability, quản lý secret và hướng dẫn triển khai. Nhưng việc một pipeline do platform team vận hành không khiến họ sở hữu quy tắc hoàn tiền, hợp đồng Order API hay việc giao hàng.

Phân tách **quyền sở hữu năng lực** với **dịch vụ hạ tầng dùng chung** giúp tránh tranh chấp trong vận hành.

## 16. Ma trận đánh giá ranh giới dịch vụ

Có thể dùng bảng này trong cuộc họp kiến trúc hoặc khi review một proposal:

| Câu hỏi | Dấu hiệu ranh giới rõ | Dấu hiệu cần xem lại |
|---|---|---|
| Ai quyết định nghiệp vụ? | Một service có authority cho từng bất biến quan trọng | Nhiều service cùng quyết định một trạng thái |
| Ai ghi dữ liệu chuẩn? | Chỉ owner có quyền ghi logic | Người khác UPDATE bảng trực tiếp |
| Dữ liệu đọc từ đâu? | Có nguồn và mức nhất quán rõ | Các consumer đọc schema nội bộ tùy ý |
| API công bố điều gì? | Command/query có ngữ nghĩa, lỗi và kết quả cụ thể | Chỉ phơi CRUD theo cột bảng |
| Ai phát event? | Chủ sự thật công bố sự kiện đã xảy ra | Nhiều bên tự suy đoán và phát cùng event |
| Thay hợp đồng thế nào? | Có kiểm thử tương thích và giai đoạn chuyển tiếp | Phải deploy đồng loạt mọi consumer |
| Ai chịu sự cố? | Có owner, metric, alert, runbook | Không đội nào nhận trách nhiệm |
| Bảo vệ bất biến khi mạng lỗi? | Có state machine, timeout, retry và đối soát | Timeout bị xem là kết quả nghiệp vụ |
| Reporting kết hợp dữ liệu ra sao? | Projection/API composition có độ tươi rõ | Reporting sửa thẳng dữ liệu nguồn |
| Có cần tách vật lý ngay? | Nhu cầu phát hành/vận hành được chứng minh | Tách theo số bảng hoặc theo team chart |

Đừng dùng số lượng endpoint, bảng, class hoặc repository làm điểm đánh giá trực tiếp. Hãy dùng **khả năng giải thích quyền quyết định và cách thay đổi độc lập**.

## 17. Những lỗi thiết kế thường gặp

### 17.1. “Database per service” nhưng schema vẫn dùng chung

Mỗi service có một database riêng trên sơ đồ, song mọi service cùng dùng một thư viện entity JPA hoặc cùng phải thêm cột theo một lần release. Dữ liệu có thể nằm khác máy nhưng **hợp đồng đã rò rỉ thành cấu trúc nội bộ**.

Hướng xử lý: Dùng contract DTO/event rõ, tránh chia sẻ domain model giữa các service, migration từng bước và kiểm soát tương thích.

### 17.2. Shared kernel quá rộng

Một thư viện chứa chung Customer, Order, PaymentStatus, PricingRules và tất cả enum có vẻ giúp tránh trùng code. Trên thực tế nó khiến từng service mất tự chủ thay đổi.

Chỉ chia sẻ phần thật sự ổn định, ví dụ tiện ích kỹ thuật chung hoặc giao thức được thống nhất. Không bắt buộc các bounded context dùng một model nghiệp vụ duy nhất. Chấp nhận **lặp lại biểu diễn có chủ đích** khi hai miền có nghĩa khác nhau.

### 17.3. Service “chuyển tiếp” không có trách nhiệm rõ

Một service chỉ gọi sang ba service khác rồi trả kết quả, không sở hữu quy tắc, dữ liệu hay hợp đồng có nghĩa riêng, có thể chỉ làm tăng network hop. Tuy nhiên một BFF hoặc workflow orchestrator vẫn hợp lý nếu nó sở hữu một trách nhiệm rõ như trải nghiệm khách hàng hoặc trạng thái phối hợp.

Hãy hỏi: **Nếu bỏ service này, quyết định nghiệp vụ hay trách nhiệm nào sẽ bị mất?** Nếu không có, xem lại sự cần thiết.

### 17.4. Consumer tự tính lại quy tắc của provider

Order tự nhân số lượng với giá được cache, bỏ qua chính sách Pricing; hoặc Shipping tự suy “đơn đã trả tiền” dựa trên cột tổng tiền dương. Khi quy tắc đổi, hai bên bất đồng và dữ liệu không nhất quán.

Hướng xử lý: Chủ sở hữu cung cấp quote, authorization, reservation hoặc event kết quả với ngữ nghĩa đủ để consumer sử dụng.

### 17.5. Event như RPC trá hình

Service A phát DoPaymentNow và xem đó là “PaymentSucceeded”, hoặc dùng một topic với hàng loạt lệnh tùy ý để điều khiển logic nội bộ Payment. Không phải mọi message đều là event. Phân biệt lệnh yêu cầu hành động với sự kiện nói rằng một sự thật đã xảy ra.

### 17.6. Tách quá nhỏ quanh mỗi endpoint

Mỗi controller hoặc bảng trở thành một service. Một đơn giản hóa “cập nhật tên” có thể đi qua nhiều network call vì các quy tắc thuộc cùng aggregate bị phân mảnh.

Hướng xử lý: Nhóm hành vi theo bất biến và mô hình miền; dùng module nội bộ khi chưa có nhu cầu triển khai độc lập.

### 17.7. Mặc định “một nguồn sự thật” nghĩa là mọi bản sao luôn giống nhau

Một read model nhận sự kiện sau 2 giây là bình thường nếu hợp đồng cho phép. Sai là dùng read model đó làm nguồn quyết định nơi đòi thông tin mới nhất hoặc không có cách nhận biết/đối soát khi bản sao kẹt.

### 17.8. Contract version chỉ là số trong URL

Đặt /v2 không bảo đảm tương thích nếu ý nghĩa nghiệp vụ đổi ngầm, lỗi khác hoặc consumer không có cửa sổ chuyển đổi. Cần quản trị **hành vi quan sát được** cùng với schema và phiên bản.

### 17.9. Một quyết định có hai người sở hữu ngang nhau

Khi Inventory và Order đều có quyền “xác nhận còn hàng”, kết quả có thể xung đột. Phân biệt **kiểm tra sơ bộ để hiển thị** với **quyết định giữ chỗ có hiệu lực**. Chỉ một nơi có thẩm quyền đối với cùng một bất biến trong cùng phạm vi.

## 18. Kiểm chứng quyền sở hữu bằng tình huống thay đổi

Để xác minh ranh giới, thử một số thay đổi có kết quả quan sát được.

**Tình huống A — Thêm lý do từ chối giữ chỗ:** Inventory cần báo thêm STOCK_RESTRICTED. Kiểm tra service nào sửa quy tắc, thêm trường/hợp đồng theo cách tương thích, và consumer xử lý lý do mới thế nào. Nếu Order phải biết cách truy vấn cột nội bộ restricted_stock, ranh giới dữ liệu bị rò rỉ.

**Tình huống B — Thay phương thức thanh toán:** Payment thêm cổng thanh toán mới. Nếu Order chỉ phụ thuộc ChargePayment/PaymentSucceeded và các trạng thái đã thỏa thuận, Order không cần hiểu mọi trạng thái riêng của provider.

**Tình huống C — Đổi tên sản phẩm:** Catalog đổi displayName, nhưng Order cũ giữ snapshot tên khi chốt; việc hiển thị hóa đơn lịch sử không nên tự biến theo thay đổi Catalog nếu nghiệp vụ yêu cầu snapshot.

**Tình huống D — Triển khai hai phiên bản:** Provider triển khai field mới trong khi consumer cũ vẫn chạy. Kiểm thử hợp đồng xác nhận consumer cũ hoạt động đến khi hết giai đoạn chuyển đổi.

**Tình huống E — Consumer kẹt sự kiện:** OrderConfirmed đã ghi ở nguồn nhưng projection chưa xử lý. Phải có alert, retry, theo dõi lag và cách đối soát; việc trễ projection không làm Notification được quyền sửa status của Order.

**Tình huống F — Database từ chối truy cập chéo:** Vô hiệu quyền ghi schema Payment đối với credential Order. Nếu chức năng đặt hàng bình thường vẫn hoạt động qua hợp đồng, quyền sở hữu dữ liệu được thực thi tốt hơn.

## 19. Gợi ý cấu trúc mã cho một service Java

Ví dụ một ranh giới Inventory trong ứng dụng Spring có thể chia theo trách nhiệm:

~~~text
inventory/
  api/
    InventoryReservationController.java
    ReserveInventoryRequest.java
    InventoryReservationResponse.java
  application/
    ReserveInventoryUseCase.java
    ReleaseReservationUseCase.java
  domain/
    StockAggregate.java
    Reservation.java
    InventoryPolicy.java
  infrastructure/
    InventoryRepositoryAdapter.java
    OutboxPublisher.java
    InventoryPersistenceEntity.java
  contract/
    InventoryReservedEvent.java
~~~

Tên thư mục và lớp chỉ để minh họa. Điểm chính:
- **api:** Chuyển request/response thành command và trả lỗi theo hợp đồng; không tự quyết định tồn kho.
- **application:** Điều phối một use case, transaction cục bộ và các adapter cần thiết.
- **domain:** Bảo vệ các quy tắc và trạng thái thuộc năng lực.
- **infrastructure:** Lưu dữ liệu, nói chuyện với broker và triển khai các giao tiếp kỹ thuật.
- **contract:** Định nghĩa nội dung được phép phụ thuộc từ bên ngoài; không công bố entity persistence như API chung.

Trong Java, không nên để Payment import trực tiếp lớp InventoryPersistenceEntity rồi dùng nó làm nguồn tạo bảng hoặc schema. Nếu hai service cùng dùng một thư viện kỹ thuật, cần chắc chắn thư viện đó không buộc mô hình miền thay đổi đồng loạt.

### 19.1. Mã giả use case theo quyền sở hữu

~~~java
public ReservationResult reserve(ReserveInventory command) {
    // Kiểm tra quyền và dữ liệu đầu vào theo chính sách.
    // Tìm request đã xử lý theo idempotency key nếu có.

    return transaction.execute(() -> {
        StockAggregate stock = stockRepository.loadForUpdate(command.sku());

        Reservation reservation = stock.reserve(
            command.orderId(),
            command.quantity(),
            command.expiresAt()
        );

        stockRepository.save(stock);
        outboxRepository.append(
            InventoryReservedEvent.from(reservation)
        );

        return ReservationResult.from(reservation);
    });
}
~~~

Đây là mã giả Java nhằm cho thấy trách nhiệm, không phải một phương thức Spring/JPA hoàn chỉnh để copy chạy ngay. Điều kiện race, transaction isolation, unique constraint, bảo vệ idempotency, clock, policy hết hạn và lỗi giao dịch phải được triển khai theo datastore và nghiệp vụ thực tế.

Service Order chỉ dùng command/result công bố; nó không gọi trực tiếp repository của Inventory và không tự quyết định quantity có thể giữ.

## 20. Bài thực hành: thiết kế ranh giới cho nền tảng học trực tuyến

Một nền tảng có ba nhóm chức năng:
- **Enrollment:** Ghi danh học viên vào khóa học và giữ chỗ.
- **Billing:** Tính tiền, tạo hóa đơn, thu và hoàn tiền.
- **LearningProgress:** Ghi nhận tiến độ học và điều kiện hoàn thành.

Hiện tại cả ba dùng chung bảng student, course, enrollment, invoice và progress. Nhóm frontend gọi trực tiếp một API PATCH /students/{id} để đổi nhiều trường. Khi khách trả tiền, hệ thống đồng thời đổi invoice.status, enrollment.status và student.active trong một transaction.

### Yêu cầu

1. Viết một câu mô tả hành vi mà mỗi service phải sở hữu. Nêu ít nhất một bất biến cho từng năng lực.
2. Phân công chủ sở hữu cho từng dữ liệu: hồ sơ học viên, số chỗ khóa học, bản ghi ghi danh, hóa đơn, trạng thái thanh toán và tiến độ. Nếu có hai chủ sở hữu cho dữ liệu tưởng như cùng tên, giải thích khác biệt ngữ nghĩa.
3. Thiết kế command/event giữa Enrollment và Billing. Chỉ rõ ai phát PaymentSucceeded, ai quyết định EnrollmentActivated và trạng thái khi thanh toán đang chờ.
4. Đề xuất cách thay API PATCH chung bằng các hợp đồng thể hiện ý định, tránh cho frontend tự sửa các trường trạng thái không thuộc quyền.
5. Xác định cách hiển thị dashboard “Khóa học của tôi” có thể dùng read model mà vẫn thông báo trạng thái đang đồng bộ.
6. Đề xuất các bước tách dần từ database chung đến quyền ghi riêng, xử lý vấn đề dữ liệu chuyển đổi và giai đoạn triển khai tương thích.
7. Viết tối thiểu ba phép thử chứng minh service không còn phụ thuộc vào bảng nội bộ của nhau.

### Một hướng tiếp cận

Enrollment có thể sở hữu trạng thái ghi danh, giới hạn số chỗ và điều kiện kích hoạt, còn Billing sở hữu yêu cầu thu tiền và hóa đơn. Khi Billing xác nhận thanh toán thành công, Enrollment xử lý sự kiện/kết quả và quyết định kích hoạt ghi danh theo quy tắc của mình; nó không tự ghi invoice. LearningProgress nhận thông tin rằng học viên đủ điều kiện tham gia và quản lý tiến độ, nhưng không tự đảo ngược giao dịch thanh toán.

Một bảng dashboard có thể là read model từ Enrollment và LearningProgress; bản sao trễ không cấp quyền dùng trạng thái hiển thị để bỏ qua kiểm tra truy cập lúc học viên mở một nội dung yêu cầu điều kiện cụ thể.

## 21. Mẫu ghi nhận quyết định kiến trúc (ADR)

Dùng một mẫu ngắn cho từng ranh giới quan trọng:

~~~text
ADR: Quyền sở hữu của <năng lực>

Bối cảnh:
- Quy tắc nghiệp vụ và tình huống thay đổi:
- Những hệ thống/các nhóm liên quan:

Quyền sở hữu hành vi:
- Các command và quyết định:
- Bất biến:
- Những điều KHÔNG thuộc service này:

Quyền sở hữu dữ liệu:
- Source of truth, aggregate/schema:
- Ai được phép ghi:
- Snapshot/read models/replicas:
- Mức nhất quán và chính sách đối soát:

Hợp đồng:
- API commands và queries:
- Events công bố / events tiêu thụ:
- Ý nghĩa trạng thái, lỗi, idempotency và ordering:
- Chính sách versioning/deprecation:

Phụ thuộc:
- Các lời gọi đồng bộ cần thiết:
- Các bước bất đồng bộ:
- Khi timeout, retry, trùng event hoặc mất mạng:

Vận hành:
- Owner, alerts và runbooks:
- Chiến lược thử nghiệm và chuyển đổi:
- Tiêu chí kiểm tra độc lập phát hành:

Phương án thay thế và lý do chưa chọn:
Rủi ro, giả định và thời điểm đánh giá lại:
~~~

## 22. Những nguyên tắc cần nhớ

- **Hành vi có chủ sở hữu:** Quy tắc và bất biến cần được quyết định ở nơi có thẩm quyền, không nằm rải rác trong client, gateway hoặc các service tiêu thụ.
- **Dữ liệu có chủ sở hữu:** Xác định nơi ghi trạng thái chuẩn, còn bản sao, snapshot và projection phục vụ mục đích cụ thể với hợp đồng độ tươi phù hợp.
- **Hợp đồng có chủ sở hữu:** API và event phải diễn tả ý nghĩa nghiệp vụ, trạng thái và lỗi; thay đổi cần có đường tương thích, không chỉ cập nhật DTO.
- **Phối hợp không phải chiếm quyền:** Orchestrator có thể quản lý tiến trình nhưng các service con vẫn quyết định phần nghiệp vụ và dữ liệu của mình.
- **Bản sao không phải nguồn quyết định mặc định:** Hiển thị có thể trễ; bất biến phải được bảo vệ ở điểm thực hiện hành động.
- **Độc lập có thể kiểm chứng:** Thay quy tắc, chuyển schema, triển khai một phiên bản mới hoặc làm consumer trễ đều là bài thử để phát hiện ranh giới đang rò rỉ.
- **Ranh giới tiến hóa theo nhu cầu:** Có thể bắt đầu bằng các module có quyền sở hữu rõ trong modular monolith, rồi tách service khi lợi ích và năng lực vận hành đủ vững.
