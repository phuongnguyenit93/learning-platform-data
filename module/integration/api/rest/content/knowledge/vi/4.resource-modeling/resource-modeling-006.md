# Aggregate và ranh giới thao tác nhất quán

## Mục tiêu bài học

Trong chương **Mô hình tài nguyên** của module **INTEGRATION_API_REST**, aggregate giúp trả lời một câu hỏi quan trọng khi thiết kế API: **những dữ liệu nào phải cùng hợp lệ sau mỗi thao tác thành công?** Câu trả lời quyết định nơi đặt quy tắc nghiệp vụ, phạm vi giao dịch và cách kiểm soát cập nhật đồng thời.

Sau bài học, bạn có thể:

- Phân biệt resource HTTP, entity, aggregate và aggregate root.
- Xác định ranh giới nhất quán từ các bất biến nghiệp vụ.
- Thiết kế URI, phương thức và phản hồi HTTP phù hợp với ranh giới đó.
- Giải thích khi nào cần một giao dịch cục bộ, kiểm soát phiên bản hoặc một quy trình liên tài nguyên có bù trừ.

Ví dụ xuyên suốt là API quản lý đơn hàng bằng Java/Spring hoặc công nghệ tương đương. Các quy tắc trong ví dụ được công bố rõ để bạn có thể thay đổi chúng cho miền nghiệp vụ của mình.

## 1. Aggregate là ranh giới bảo vệ bất biến

### 1.1. Bất biến là gì?

**Bất biến nghiệp vụ** là điều kiện phải đúng ở những thời điểm mà hệ thống cam kết dữ liệu đã hợp lệ, chẳng hạn ngay sau khi một giao dịch thay đổi đơn hàng được commit.

Giả sử hệ thống có các quy tắc:

1. Số lượng của mỗi dòng hàng phải là số nguyên từ 1 đến 99.
2. Một đơn chỉ sử dụng một loại tiền tệ.
3. Tổng tiền hàng bằng tổng `unitPrice × quantity` của các dòng. Ví dụ này chưa có thuế, phí giao hàng hoặc chiết khấu.
4. Chỉ được sửa dòng hàng khi đơn ở trạng thái `DRAFT`.
5. Chỉ được xác nhận đơn có ít nhất một dòng hàng.
6. Sau khi xác nhận, các dòng hàng và giá chốt của đơn không được sửa bằng API chỉnh sửa đơn nháp.

Đây là những quy tắc phải được kiểm tra ở phía máy chủ. Việc frontend vô hiệu hóa nút sửa chỉ cải thiện trải nghiệm; nó không bảo vệ dữ liệu khỏi client khác hoặc hai request chạy đồng thời.

### 1.2. Entity, aggregate và aggregate root

**Entity** là đối tượng có danh tính được duy trì qua thời gian. `Order` và `OrderLine` đều có thể là entity: dòng hàng vẫn là cùng một dòng khi số lượng thay đổi.

**Aggregate** là một cụm đối tượng có ranh giới nhất quán được bảo vệ qua một đầu mối. Trong ví dụ:

```text
Order aggregate
├── Order — aggregate root
│   ├── id, customerId, status, currency
│   ├── version, total
│   └── lines
│       ├── OrderLine L1
│       └── OrderLine L2
```

**Aggregate root** là entity làm đầu mối cho những thay đổi có thể ảnh hưởng đến các bất biến của cụm. Thay vì để bất kỳ đoạn code nào gọi `line.setQuantity(...)`, ứng dụng yêu cầu đơn hàng thực hiện thao tác như `order.changeLineQuantity(...)`. Đơn hàng biết trạng thái hiện tại và có thể từ chối thay đổi không hợp lệ.

Trong mô hình này, cập nhật một dòng và tính lại tổng tiền của đơn là một thao tác nghiệp vụ thống nhất. Nếu cập nhật dòng thành công nhưng tính tổng thất bại, toàn bộ thay đổi phải rollback.

### 1.3. Resource HTTP không đồng nghĩa với aggregate

Resource là thứ API cung cấp danh tính và biểu diễn qua HTTP. Aggregate là khái niệm mô hình miền, phục vụ tính đúng đắn khi thay đổi dữ liệu. Hai khái niệm thường liên quan nhưng không ánh xạ một-một bắt buộc.

| Khái niệm | Ví dụ | Ý nghĩa thiết kế |
|---|---|---|
| Resource HTTP | `/orders/O123` | Client có thể truy cập biểu diễn của một đơn |
| Resource con | `/orders/O123/lines/L1` | API có thể cung cấp địa chỉ riêng cho dòng hàng |
| Entity | `OrderLine` có ID `L1` | Dòng có danh tính trong mô hình miền |
| Aggregate root | `Order` | Đầu mối bảo vệ quy tắc sửa dòng, tổng tiền và trạng thái |
| Projection phục vụ đọc | `/customers/C7/order-summary` | Có thể kết hợp dữ liệu từ nhiều aggregate |

URI lồng nhau thể hiện quan hệ mà API muốn công bố, nhưng **không tự tạo giao dịch, khóa hay ranh giới aggregate**. Ngược lại, một endpoint trả về đơn, khách hàng và sản phẩm trong cùng JSON cũng không khiến ba đối tượng trở thành một aggregate.

Có thể cho phép ghi vào resource con, miễn là phần xử lý vẫn đi qua cơ chế bảo vệ bất biến của root. Điều cần kiểm soát là đường ghi dữ liệu, không phải số lượng endpoint.

## 2. Tìm ranh giới bằng câu hỏi nghiệp vụ

### 2.1. Bắt đầu từ thao tác và điều kiện phải cùng đúng

Với thao tác “đổi số lượng dòng L1”, hãy lần lượt hỏi:

1. Ai được sửa đơn này?
2. Trạng thái nào cho phép sửa?
3. Những giá trị nào phải được kiểm tra cùng nhau?
4. Nếu xử lý lỗi giữa chừng, phần nào phải quay về trạng thái cũ?
5. Nếu request khác đang xác nhận đơn, kết quả nào được chấp nhận?

Câu trả lời dẫn đến phạm vi thao tác: kiểm tra quyền, đọc trạng thái đơn, thay đổi số lượng, tính tổng và tăng phiên bản phải được phối hợp để không commit một trạng thái sai.

Không nên bắt đầu bằng quy tắc “mỗi bảng là một aggregate”. Một aggregate có thể dùng nhiều bảng. Một bảng cũng có thể chứa nhiều aggregate độc lập.

### 2.2. Ranh giới đề xuất cho ví dụ đơn hàng

| Dữ liệu | Thuộc `Order` aggregate? | Lý do trong ví dụ |
|---|---|---|
| Trạng thái đơn | Có | Chi phối thao tác chỉnh sửa và xác nhận |
| Dòng hàng và số lượng | Có | Phải nhất quán với trạng thái và tổng tiền |
| Đơn giá được chốt cho dòng | Có | Đơn cần giữ lại giá đã áp dụng |
| Tổng tiền hàng | Có | Phải khớp các dòng đã lưu |
| Hồ sơ khách hàng hiện tại | Không | Có vòng đời và thao tác cập nhật riêng |
| Danh mục sản phẩm hiện tại | Không | Sản phẩm có thể đổi tên hoặc đổi giá độc lập |
| Tồn kho của sản phẩm | Không | Nhiều đơn cùng cạnh tranh một nguồn tồn kho |
| Giao dịch thanh toán | Không | Có vòng đời, nhà cung cấp và lỗi riêng |

Đơn có thể giữ `customerId`, `productId` và các giá trị chụp tại thời điểm mua như tên hàng, đơn giá hoặc địa chỉ giao hàng. Tham chiếu theo ID không bắt buộc phải nạp toàn bộ aggregate khác mỗi lần sửa đơn.

Trong ví dụ, máy chủ chọn đơn giá và lưu nó vào dòng hàng; client không được tự ghi đè `unitPrice` hay `total`. Nếu nghiệp vụ yêu cầu áp dụng bảng giá mới khi xác nhận đơn, việc định giá lại phải được mô tả thành quy tắc riêng. Không thể mặc nhiên cho rằng giá chốt luôn bằng giá hiện tại trong danh mục.

### 2.3. Aggregate nên vừa đủ để giữ đúng quy tắc

Aggregate quá lớn gây nhiều tranh chấp khóa, tải dữ liệu nặng và tăng số request thất bại do cạnh tranh phiên bản. Ví dụ, gom khách hàng và toàn bộ lịch sử mua hàng thành một aggregate có thể khiến sửa số điện thoại cạnh tranh với thao tác tạo đơn mới.

Aggregate quá nhỏ lại đẩy quy tắc nhất quán ra nhiều nơi. Tách mỗi dòng thành một aggregate độc lập nhưng vẫn yêu cầu mọi lần sửa dòng phải đồng thời bảo đảm tổng tiền và trạng thái đơn sẽ tạo ra nhu cầu phối hợp phức tạp.

Hãy xem xét cả tần suất cập nhật, số lượng phần tử và mức cạnh tranh. Một đơn hàng giới hạn vài chục dòng có đặc điểm khác một danh sách có hàng triệu phần tử. Nếu mô hình tăng trưởng khiến việc kiểm tra bất biến quá đắt, cần xem lại cả ranh giới lẫn chính quy tắc nghiệp vụ, không chỉ đổi tên lớp.

## 3. Chuyển ranh giới miền thành hợp đồng REST

### 3.1. Endpoint phải làm rõ điều client được thay đổi

Một thiết kế có thể là:

| Thao tác | Endpoint | Hành vi và phản hồi minh họa |
|---|---|---|
| Đọc đơn | `GET /orders/{orderId}` | `200 OK`, biểu diễn đơn và `ETag` |
| Tạo đơn nháp | `POST /orders` | `201 Created`, `Location` trỏ tới đơn mới |
| Thêm dòng | `POST /orders/{orderId}/lines` | `201 Created`, `Location` trỏ tới dòng mới |
| Sửa số lượng dòng | `PATCH /orders/{orderId}/lines/{lineId}` | `204 No Content` sau khi commit |
| Xóa dòng | `DELETE /orders/{orderId}/lines/{lineId}` | `204 No Content` sau khi commit |
| Tạo xác nhận đơn | `POST /orders/{orderId}/confirmations` | `201 Created` nếu tạo một resource xác nhận bền vững |

Ở hàng cuối, `confirmation` phải thực sự có ý nghĩa trong hợp đồng: có danh tính, trạng thái hoặc thông tin xác nhận mà client có thể truy cập. Không nên thêm danh từ giả chỉ để che một lời gọi hàm.

Một API khác có thể biểu diễn chuyển trạng thái bằng cập nhật resource đơn. Khi đó cần định nghĩa rõ các chuyển trạng thái hợp lệ và trường nào client được gửi. Điều cốt lõi là chuyển trạng thái vẫn đi qua cùng cơ chế bảo vệ aggregate.

### 3.2. DTO ghi dữ liệu phải hẹp hơn biểu diễn đọc

Ví dụ hợp đồng cho thao tác sửa dòng:

```http
PATCH /orders/O123/lines/L1 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "line-L1-v4"

{
  "quantity": 3
}
```

Với JSON Merge Patch, thuộc tính không xuất hiện được giữ nguyên; giá trị `null` mang ý nghĩa loại bỏ thuộc tính. API này quy định `quantity` là thuộc tính bắt buộc của dòng, vì vậy gửi `"quantity": null` bị từ chối. `status`, `unitPrice`, `total` và thuộc tính không được hỗ trợ cũng bị từ chối; không ánh xạ toàn bộ JSON vào entity bằng cơ chế gán thuộc tính tự động.

Trong ví dụ này, `If-Match` trên URI dòng dùng validator của **resource dòng**. Phần sau sẽ giải thích cách gắn validator đó với phiên bản aggregate để đồng thời bảo vệ trạng thái đơn.

Ví dụ biểu diễn đọc của đơn:

```json
{
  "id": "O123",
  "status": "DRAFT",
  "currency": "VND",
  "lines": [
    {
      "id": "L1",
      "productId": "P10",
      "quantity": 2,
      "unitPrice": 120000,
      "subtotal": 240000
    }
  ],
  "total": 240000
}
```

Phản hồi này chưa có phân trang dòng hàng. Nếu API phân trang một tập con của dòng, `total` phải được định nghĩa là tổng toàn đơn; không để client hiểu đó là tổng các dòng đang xuất hiện trên trang.

### 3.3. Ghi nhiều trường có quan hệ trong một thao tác

Nếu một quy tắc yêu cầu hai giá trị thay đổi đồng thời, hợp đồng phải có cách gửi chúng trong cùng thao tác nghiệp vụ. Ví dụ, thay đổi `shippingMethod` có thể yêu cầu tính lại phí và tổng thanh toán. Để client tự lần lượt ghi từng trường dễ tạo trạng thái trung gian không hợp lệ.

Một request có thể chứa nhiều thay đổi trong cùng aggregate và được xử lý nguyên tử. Tuy nhiên, một HTTP request chứa nhiều aggregate hoặc nhiều lệnh không tự bảo đảm nguyên tử; API phải công bố rõ phạm vi thành công hoặc thất bại.

## 4. Giao dịch cục bộ bảo vệ aggregate như thế nào?

### 4.1. Cùng một ranh giới commit

Với cơ sở dữ liệu quan hệ và ví dụ đơn hàng, một giao dịch cục bộ có thể bao gồm:

```text
Bắt đầu giao dịch
  → Tìm đơn trong phạm vi mà người gọi được phép truy cập
  → Khóa root hoặc thực hiện cơ chế kiểm tra phiên bản nguyên tử
  → Đọc trạng thái và các dòng cần thiết trong giao dịch
  → Kiểm tra tiền điều kiện và bất biến
  → Thay đổi dòng hàng
  → Tính lại tổng tiền
  → Ghi dữ liệu và phiên bản aggregate mới
Commit
  → Trả phản hồi thành công
```

Nếu một bước thất bại trước commit, các thay đổi phải rollback. API không được trả thành công khi mới sửa xong dòng mà chưa bảo đảm tổng tiền đã được lưu.

Giao dịch cũng cần một chiến lược xử lý cạnh tranh. Chỉ có `@Transactional` không đồng nghĩa hai request sẽ luôn được tuần tự hóa theo đúng quy tắc của miền; điều đó còn phụ thuộc vào cách đọc, khóa, kiểm tra phiên bản và mức cô lập.

### 4.2. Đặt quy tắc vào mô hình miền

Đoạn Java sau minh họa hành vi của root; các lớp lưu trữ, ngoại lệ và cấu hình tuần tự hóa được lược bỏ:

```java
// Trích đoạn minh họa bên trong Order.
// lines, status và total không có setter công khai cho tầng HTTP.
public void changeLineQuantity(String lineId, int quantity) {
    if (status != OrderStatus.DRAFT) {
        throw new OrderStateConflict("Chỉ được sửa đơn nháp");
    }
    if (quantity < 1 || quantity > 99) {
        throw new InvalidQuantity("Số lượng phải từ 1 đến 99");
    }

    OrderLine line = requireLine(lineId);
    line.changeQuantity(quantity);

    total = lines.stream()
        .map(item -> item.unitPrice().multiply(
            BigDecimal.valueOf(item.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
}

public void confirm() {
    if (status != OrderStatus.DRAFT) {
        throw new OrderStateConflict("Đơn không còn là đơn nháp");
    }
    if (lines.isEmpty()) {
        throw new OrderStateConflict("Không thể xác nhận đơn rỗng");
    }
    status = OrderStatus.CONFIRMED;
}
```

Số tiền được tính bằng `BigDecimal`, với quy ước tiền tệ và làm tròn do miền quy định. Ví dụ dùng VND và các giá trị nguyên để tập trung vào ranh giới nhất quán. Với miền có thuế hoặc chiết khấu, cần quy tắc làm tròn rõ cho từng dòng và tổng đơn.

Mô hình miền giúp tập trung các quy tắc, nhưng chưa tự giải quyết cạnh tranh trong cơ sở dữ liệu. Hai bản sao của cùng một `Order` trong hai request vẫn có thể cùng vượt qua kiểm tra `DRAFT` nếu không có phối hợp ở tầng giao dịch.

### 4.3. Một phương án triển khai dễ kiểm tra: khóa root

Mã giả ở tầng ứng dụng:

```java
@Transactional
public void changeQuantity(
        String orderId,
        String lineId,
        String ifMatch,
        int quantity,
        Actor actor) {

    // Khóa hàng root; tương đương SELECT ... FOR UPDATE.
    // Repository đồng thời giới hạn truy cập theo actor.
    Order order = orders.loadRootForUpdate(orderId, actor);

    // Đọc trạng thái các dòng hiện tại sau khi đã lấy khóa root.
    orders.loadLinesInto(order);
    OrderLine line = order.requireLine(lineId);

    // So sánh strong ETag của chính resource dòng hiện tại.
    // Ví dụ: "line-L1-v4", trong đó v4 là phiên bản của Order.
    preconditions.requireMatch(ifMatch, lineEtag(order, line));

    order.changeLineQuantity(lineId, quantity);
    order.advanceVersion();
    orders.save(order);
}
```

Đây là hợp đồng xử lý minh họa, không phải code Spring có thể chạy độc lập. `preconditions.requireMatch` cần thực hiện đúng ngữ nghĩa của header, không chỉ tách chuỗi rồi lấy số. Hợp đồng có thể yêu cầu một strong ETag cụ thể để bảo vệ cập nhật từ dữ liệu cũ và công bố rõ việc xử lý các dạng header khác.

Để cách khóa này có tác dụng:

- Mọi đường ghi dòng hàng hoặc trạng thái đơn phải khóa cùng root trước khi sửa.
- Các dòng cần dùng phải được đọc trong giao dịch theo trạng thái hiện tại, tránh dùng bản sao cũ đã lấy trước khi khóa.
- Dữ liệu dòng, tổng tiền và phiên bản root phải được lưu trong cùng giao dịch.
- Giao dịch phải bao phủ tới lúc commit; lỗi lưu hoặc lỗi commit phải làm thao tác thất bại.
- Không giữ khóa trong lúc chờ người dùng hoặc gọi dịch vụ thanh toán qua mạng.

Một script cập nhật trực tiếp bảng dòng hàng mà bỏ qua root có thể phá vỡ các bảo đảm này. Khóa root chỉ điều phối những đường ghi tuân theo cùng giao thức; các ràng buộc cơ sở dữ liệu vẫn cần được dùng khi phù hợp, như khóa ngoại và kiểm tra số lượng dương.

### 4.4. Phương án khác: kiểm tra phiên bản khi ghi

Với khóa lạc quan, thao tác ghi root thường có điều kiện kiểu:

```sql
UPDATE orders
SET total = :newTotal,
    version = version + 1
WHERE id = :orderId
  AND version = :expectedVersion;
```

Nếu không cập nhật được hàng nào, không được tiếp tục coi thao tác là thành công. Các thay đổi dòng liên quan phải nằm trong cùng giao dịch để có thể rollback khi phát hiện xung đột.

Khi dùng JPA, `@Version` trên root là một công cụ hữu ích nhưng phải kiểm tra hành vi ánh xạ thực tế: sửa entity con không bảo đảm trong mọi mô hình rằng phiên bản root sẽ tự tăng. Cần bảo đảm mọi thay đổi ảnh hưởng đến bất biến được tham gia kiểm tra phiên bản root, chẳng hạn cập nhật root một cách rõ ràng hoặc dùng cơ chế tăng phiên bản cưỡng bức phù hợp. Không chỉ kiểm tra phiên bản riêng của từng dòng rồi kết luận trạng thái đơn đã được bảo vệ.

Không trộn tùy tiện hai phương án. Nhóm phát triển nên chọn cơ chế nhất quán, biết thao tác nào lấy khóa hoặc kiểm tra phiên bản và kiểm chứng hành vi khi có hai giao dịch thật sự cạnh tranh.

## 5. Phiên bản aggregate, ETag và cập nhật đồng thời

### 5.1. Lost update và xung đột nghiệp vụ là hai vấn đề liên quan

Giả sử đơn `O123` đang ở phiên bản 4:

```text
A đọc đơn và dòng L1 ở phiên bản 4
B đọc đơn và dòng L1 ở phiên bản 4
A đổi số lượng thành 3, commit phiên bản 5
B đổi số lượng thành 8 từ dữ liệu đã đọc ở phiên bản 4
```

Nếu không kiểm tra phiên bản, thay đổi của A có thể bị B ghi đè mà B không nhận ra. Đó là một dạng lost update.

Một cuộc cạnh tranh khác:

```text
A muốn sửa dòng khi đơn đang DRAFT
B muốn xác nhận chính đơn đó
```

Dù A và B sửa các trường khác nhau, chúng vẫn cạnh tranh trên bất biến “không sửa dòng sau khi xác nhận”. Vì vậy chỉ khóa hoặc gắn phiên bản riêng cho dòng hàng là chưa đủ trong mô hình này.

### 5.2. Validator phải thuộc đúng resource đích

Ví dụ API cung cấp:

```http
GET /orders/O123

HTTP/1.1 200 OK
ETag: "order-O123-v4"
```

```http
GET /orders/O123/lines/L1

HTTP/1.1 200 OK
ETag: "line-L1-v4"
```

Hai validator trên khác nhau. Trong thiết kế minh họa, chúng cùng phụ thuộc phiên bản 4 của aggregate. Khi một thay đổi quan trọng của đơn commit, phiên bản root tăng; validator của các resource được bảo vệ theo phiên bản đó cũng thay đổi.

Client sửa dòng bằng `If-Match: "line-L1-v4"` trên URI dòng. Không lấy `ETag` của URI đơn rồi mặc nhiên gửi nó làm điều kiện cho URI dòng. Nếu chỉ muốn công bố validator của root, có thể thiết kế thao tác cập nhật vào chính resource đơn thay vì yêu cầu client đoán validator của resource con.

API dùng **strong ETag** cho điều kiện `If-Match`. Chuỗi có tiền tố `W/` là weak ETag và không đáp ứng phép so sánh mạnh của điều kiện này. Giá trị ETag là token opaque đối với client: client lưu và gửi lại token nhận được, không tự tăng số phiên bản hay suy ra token mới.

Việc lấy phiên bản cơ sở dữ liệu làm strong ETag chỉ đúng nếu thiết kế bảo đảm validator đổi khi biểu diễn tương ứng thay đổi, đồng thời xử lý thích hợp các biến thể biểu diễn. Nếu response nhúng tên khách hàng hoặc giá sản phẩm đang thay đổi độc lập, chỉ dùng phiên bản đơn có thể không đủ. Có thể giới hạn dữ liệu biểu diễn vào snapshot được quản lý theo phiên bản, hoặc dùng cách tạo validator bao phủ mọi dữ liệu có ảnh hưởng.

Một validator đổi dù JSON của dòng chưa đổi vẫn có thể hợp lệ. Đó là lựa chọn kiểm soát xung đột bảo thủ: sửa dòng L2 có thể làm request sửa L1 từ phiên bản cũ bị từ chối. Cần cân nhắc mức cạnh tranh này trước khi cố tối ưu phiên bản riêng cho từng dòng, vì tối ưu phải tiếp tục bảo vệ bất biến của cả đơn.

### 5.3. Kiểm tra điều kiện và thay đổi phải gắn với nhau

Cách làm sai:

```text
Đọc phiên bản → so sánh trong controller → chờ → cập nhật không điều kiện
```

Giữa lúc so sánh và cập nhật, request khác vẫn có thể commit. Kiểm tra phiên bản phải gắn với thao tác ghi nguyên tử, hoặc được thực hiện trong phạm vi khóa phù hợp như mã giả ở trên.

Để minh họa hai thao tác có điều kiện, bảng sau dùng biến thể xác nhận bằng `PATCH /orders/O123`, với `If-Match` lấy từ `GET /orders/O123`. Nếu dùng `POST /orders/O123/confirmations`, không mặc nhiên áp dụng ETag của đơn lên URI đó; hợp đồng cần cơ chế kiểm soát tương ứng, trong khi khóa và bất biến của root vẫn phải được bảo vệ.

Một kết quả hợp lệ khi hai request cùng xuất phát từ phiên bản 4:

| Request thắng trước | Trạng thái sau commit | Request còn lại |
|---|---|---|
| Sửa dòng | Đơn vẫn `DRAFT`, phiên bản 5 | Xác nhận với validator cũ bị từ chối; client đọc lại rồi quyết định |
| Xác nhận | Đơn `CONFIRMED`, phiên bản 5 | Sửa dòng với validator cũ bị từ chối; sau khi đọc lại vẫn không được sửa đơn đã xác nhận |

Nếu lỗi `If-Match` được phát hiện, dùng `412 Precondition Failed`. Nếu client gửi điều kiện hiện tại nhưng thao tác vi phạm trạng thái nghiệp vụ, dùng `409 Conflict` theo hợp đồng của ví dụ. Những kiểm tra thông thường như xác thực, quyền truy cập và sự tồn tại của resource vẫn phải được áp dụng; không dùng bảng này để bỏ qua chúng.

### 5.4. Mã trạng thái và hợp đồng lỗi

| Tình huống | Phản hồi đề xuất |
|---|---|
| JSON hoặc cú pháp request không hợp lệ | `400 Bad Request` |
| Media type của bản vá không được hỗ trợ | `415 Unsupported Media Type` |
| Số lượng ngoài 1–99 hoặc yêu cầu bỏ thuộc tính bắt buộc | `422 Unprocessable Content` |
| Thiếu điều kiện trong thao tác mà API bắt buộc `If-Match` | `428 Precondition Required` |
| Điều kiện `If-Match` không khớp resource hiện tại | `412 Precondition Failed` |
| Đơn đã xác nhận hoặc xác nhận một đơn rỗng | `409 Conflict` |
| Chưa xác thực | `401 Unauthorized`, kèm challenge phù hợp |
| Không được phép thao tác | `403 Forbidden`, hoặc `404` theo chính sách che giấu sự tồn tại |
| Resource không tồn tại trong phạm vi truy cập | `404 Not Found` |

Đây là một hợp đồng minh họa. API cần thống nhất chính sách lỗi và ghi nó trong OpenAPI; không để mỗi controller tự chọn mã khác nhau cho cùng tình huống.

Ví dụ lỗi theo cấu trúc Problem Details:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-editable",
  "title": "Đơn hàng không cho phép chỉnh sửa",
  "status": 409,
  "detail": "Đơn O123 đã được xác nhận.",
  "instance": "/orders/O123/lines/L1",
  "code": "ORDER_NOT_EDITABLE"
}
```

`code` là trường mở rộng để client xử lý ổn định. Thông báo lỗi không nên lộ thông tin đơn hàng trước khi người gọi được xác định là có quyền truy cập.

### 5.5. ETag còn liên quan đến đọc và cache

`If-Match` giúp bảo vệ thao tác ghi có điều kiện. Với thao tác đọc, client có thể dùng `If-None-Match` để xác thực bản cache; nếu biểu diễn chưa đổi, server có thể trả `304 Not Modified`.

Kiểm soát cạnh tranh không thay thế chính sách cache. API đơn hàng có dữ liệu riêng tư nên phải công bố `Cache-Control` phù hợp, chẳng hạn cho phép cache riêng với việc xác thực lại, hoặc `no-store` khi chính sách yêu cầu không lưu. Sau một thay đổi ở URI dòng, không được giả định mọi cache của URI đơn sẽ tự bị vô hiệu hóa; client và hạ tầng cần chính sách làm mới phù hợp. ETag giúp phát hiện dữ liệu cũ khi có lần xác thực lại, không chủ động đẩy dữ liệu mới đến mọi cache.

## 6. Khi thao tác vượt qua một aggregate

### 6.1. Xác nhận đơn không tự bảo đảm tồn kho và thanh toán

Trong các phần trước, `confirm()` chỉ bảo vệ quy tắc nội bộ của đơn: đơn phải còn là nháp và có dòng hàng. Nó chưa chứng minh tồn kho đã được giữ hoặc thanh toán đã thành công.

Nếu nghiệp vụ yêu cầu cả hai điều kiện đó trước khi công bố đơn đã xác nhận, cần bổ sung quy trình rõ ràng. Không được trả `CONFIRMED` rồi ngầm hy vọng các bước còn lại sẽ thành công.

Một quy trình có thể là:

```text
DRAFT
  → PENDING_CONFIRMATION
      → Giữ hàng thành công
      → Ủy quyền thanh toán thành công
      → CONFIRMED

Nếu một bước thất bại:
  → Ghi nhận bước thất bại
  → Bù trừ các bước đã thành công, nếu cần
  → REJECTED hoặc trạng thái đang chờ xử lý bù trừ
```

Trong thiết kế này, `PENDING_CONFIRMATION` cũng không cho sửa dòng. Giá và số lượng cần được cố định hoặc được quản lý bằng một quy tắc thay đổi riêng để các bước sau không thanh toán một phiên bản khác với phiên bản đã giữ hàng.

### 6.2. Mỗi aggregate bảo vệ phần trách nhiệm của mình

| Aggregate hoặc thành phần | Điều phải tự bảo vệ |
|---|---|
| Đơn hàng | Chuyển trạng thái hợp lệ; nội dung đơn không bị sửa ngoài quy tắc |
| Tồn kho | Việc giữ hàng không vượt lượng khả dụng theo chính sách của hệ thống |
| Thanh toán | Không tạo nhiều giao dịch ngoài ý muốn cho cùng yêu cầu nghiệp vụ |
| Bộ điều phối | Theo dõi các bước, retry, timeout và bù trừ |

Đọc “còn 5 sản phẩm” rồi tạo đơn mua 5 sản phẩm không bảo đảm còn đủ hàng khi có đơn khác đồng thời. Chính thao tác giữ hàng ở phía quản lý tồn kho phải kiểm tra và cập nhật khả dụng một cách nguyên tử.

Nếu tất cả dữ liệu nằm trong một cơ sở dữ liệu và yêu cầu thực sự là nguyên tử tức thời, một giao dịch cục bộ chạm nhiều aggregate có thể là lựa chọn có chủ đích. Nó tạo sự phụ thuộc và phạm vi tranh chấp lớn hơn, cần được cân nhắc. Ranh giới aggregate không phải một giới hạn kỹ thuật cấm mọi giao dịch qua nhiều root.

Khi dữ liệu nằm ở các dịch vụ và kho lưu trữ độc lập, `@Transactional` trong dịch vụ đơn hàng không tự bao phủ lời gọi HTTP sang dịch vụ tồn kho hoặc nhà cung cấp thanh toán. Cần chọn cơ chế phối hợp phù hợp; một lựa chọn phổ biến là saga với các bước cục bộ và hành động bù trừ.

Bù trừ là một thao tác nghiệp vụ mới, chẳng hạn giải phóng một lần giữ hàng hoặc hoàn tiền. Nó có thể thất bại, cần retry và có thể không đảo ngược hoàn toàn tác động đã xảy ra. Không mô tả saga như một lệnh rollback cơ sở dữ liệu xuyên dịch vụ.

### 6.3. Công bố trạng thái trung gian qua API

Nếu xác nhận cần xử lý bất đồng bộ, API có thể trả:

```http
HTTP/1.1 202 Accepted
Location: /operations/OP789
Content-Type: application/json

{
  "operationId": "OP789",
  "orderId": "O123",
  "status": "PENDING"
}
```

`202 Accepted` cho biết yêu cầu đã được tiếp nhận, chưa phải cam kết rằng đơn đã được xác nhận. Client đọc resource thao tác hoặc đơn hàng để biết kết quả cuối cùng.

Hợp đồng phải nêu trạng thái trung gian, thời gian hết hạn giữ hàng, cách theo dõi lỗi và việc client có thể thử lại hay hủy yêu cầu. Quy trình cuối cùng dùng `201` cho một xác nhận đã tạo xong hay `202` cho xử lý đang chờ phải được công bố rõ; đây là hai biến thể xử lý khác nhau.

### 6.4. Ghi trạng thái và phát sự kiện không được tạo khoảng trống

Một lỗi thường gặp:

```text
Commit đơn sang PENDING_CONFIRMATION
→ Tiến trình chết trước khi gửi sự kiện giữ hàng
→ Đơn bị mắc kẹt vì không có sự kiện để xử lý tiếp
```

Với transactional outbox, dịch vụ ghi trạng thái đơn và bản ghi sự kiện vào cùng giao dịch cục bộ. Một tiến trình khác đọc outbox và phát sự kiện.

Outbox giảm nguy cơ mất sự kiện do ghi hai nơi riêng rẽ, nhưng sự kiện vẫn có thể được gửi lặp. Consumer cần cơ chế khử trùng lặp hoặc xử lý idempotent. Việc đánh dấu đã xử lý sự kiện và tác động dữ liệu cục bộ cũng cần được phối hợp để một lần crash không làm tác động bị áp dụng hai lần.

## 7. Retry và idempotency thuộc hợp đồng thao tác

Client có thể bị timeout sau khi server đã commit. Khi đó client không biết thao tác thất bại hay chỉ mất phản hồi.

Hai cơ chế giải quyết hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi được giải quyết |
|---|---|
| Phiên bản hoặc `If-Match` | Tôi có đang sửa từ trạng thái đã cũ không? |
| Idempotency của yêu cầu | Yêu cầu nghiệp vụ này đã được tiếp nhận hoặc thực hiện chưa? |

Đặt số lượng thành 3 có thể cho cùng kết quả nghiệp vụ khi lặp lại, nhưng phương thức `PATCH` nói chung không mặc nhiên idempotent; bản vá “tăng thêm 1” có đặc điểm khác. Thêm dòng bằng `POST` hoặc tạo yêu cầu thanh toán cần được thiết kế rõ cho tình huống retry.

Ví dụ một quy ước của API:

```http
POST /orders/O123/confirmations HTTP/1.1
Idempotency-Key: 7e548c1b-06be-41f8-a596-d1d43d258dcb
Content-Type: application/json

{}
```

Để quy ước này có tác dụng, server cần:

1. Xác định phạm vi khóa, chẳng hạn tenant hoặc người dùng, loại thao tác và đơn hàng.
2. Lưu dấu vân tay nội dung yêu cầu cùng trạng thái xử lý và kết quả hoặc ID resource thao tác.
3. Chặn hai request cùng khóa đồng thời cùng tạo hai quy trình; có thể dùng ràng buộc duy nhất và bản ghi tiếp nhận trong giao dịch cục bộ.
4. Khi khóa được gửi lại với cùng nội dung, trả kết quả đã lưu hoặc cùng resource đang xử lý theo hợp đồng.
5. Khi cùng khóa đi kèm nội dung khác, từ chối bằng lỗi đã công bố, chẳng hạn `409 Conflict`.
6. Công bố thời hạn giữ khóa và hành vi sau khi khóa hết hạn.

`Idempotency-Key` ở đây là quy ước hợp đồng được API hỗ trợ; client không thể chỉ tự thêm header rồi giả định mọi server sẽ khử trùng lặp. Khóa này không thay thế xác thực, phân quyền hoặc kiểm tra trạng thái đơn.

Nếu thao tác có tác động bên ngoài, chỉ lưu kết quả trong cơ sở dữ liệu đơn hàng chưa đủ bảo đảm không thanh toán hai lần. Cần truyền một định danh ổn định sang nhà cung cấp hỗ trợ idempotency, đồng thời có cơ chế đối soát và xử lý kết quả chưa rõ. Không hứa bảo đảm “thực thi đúng một lần” chỉ vì đã có outbox hoặc một header.

## 8. Ghi ranh giới thao tác trong OpenAPI

OpenAPI cần mô tả dữ liệu được phép ghi, điều kiện bắt buộc và các lỗi mà client có thể xử lý. Đoạn trích sau minh họa thao tác sửa dòng; đây là một phần hợp đồng, chưa phải tài liệu OpenAPI đầy đủ:

```yaml
paths:
  /orders/{orderId}/lines/{lineId}:
    patch:
      summary: Sửa số lượng một dòng của đơn nháp
      description: >-
        Thay đổi dòng, tổng tiền và phiên bản đơn trong một giao dịch.
        If-Match phải dùng strong ETag lấy từ resource dòng.
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
        - in: path
          name: lineId
          required: true
          schema:
            type: string
        - in: header
          name: If-Match
          required: true
          schema:
            type: string
          example: '"line-L1-v4"'
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              additionalProperties: false
              properties:
                quantity:
                  type: integer
                  minimum: 1
                  maximum: 99
      responses:
        '204':
          description: Đã commit thay đổi; không có nội dung phản hồi
        '409':
          description: Trạng thái đơn không cho phép thay đổi
        '412':
          description: If-Match không khớp resource hiện tại
        '422':
          description: Nội dung bản vá vi phạm ràng buộc dữ liệu
        '428':
          description: Thiếu If-Match theo yêu cầu của API
```

Schema không bắt buộc `quantity` xuất hiện, phù hợp ngữ nghĩa bản vá: `{}` không yêu cầu thay đổi thuộc tính nào. `null` không thuộc kiểu `integer` nên bị từ chối. Trước khi xử lý cả bản vá rỗng, server vẫn áp dụng xác thực, phân quyền và tiền điều kiện được yêu cầu. Hợp đồng cũng cần nói rõ chính sách thao tác trên đơn đã xác nhận.

Bản OpenAPI hoàn chỉnh cần bổ sung security scheme, các phản hồi còn lại trong bảng lỗi, schema Problem Details và endpoint đọc trả ETag. Mô tả “trong một giao dịch” là cam kết hành vi cần được triển khai và kiểm chứng; riêng tài liệu OpenAPI không tạo ra giao dịch.

## 9. Kiểm thử theo bất biến và tình huống cạnh tranh

Những trường hợp sau là tiêu chí thiết kế kiểm thử cho API, không chỉ là kiểm tra controller có trả đúng mã HTTP hay không:

| Tình huống | Điều cần quan sát |
|---|---|
| Đổi số lượng hợp lệ | Dòng và tổng tiền cùng đổi; phiên bản tăng theo chính sách |
| Số lượng bằng 0 hoặc 100 | Request bị từ chối; dữ liệu không thay đổi |
| Sửa dòng của đơn đã xác nhận | Không thay đổi dòng hoặc tổng tiền |
| Lỗi sau khi ghi dòng nhưng trước khi lưu tổng | Giao dịch rollback toàn bộ |
| Hai request dùng cùng validator cũ | Trong tình huống cùng sửa từ một phiên bản, chỉ một thao tác commit; request còn lại nhận lỗi tiền điều kiện hoặc xung đột đã được ánh xạ đúng |
| Một request sửa dòng, một request xác nhận | Không có kết quả đã commit mà đơn xác nhận lại chứa thay đổi được áp dụng trái quy tắc |
| Người dùng thay `orderId` hoặc `lineId` | Không đọc hoặc sửa được đơn của người khác; dòng phải thực sự thuộc đơn trên URI |
| Retry sau khi mất phản hồi xác nhận | Không tạo thêm quy trình cho cùng idempotency key hợp lệ |
| Consumer nhận lại cùng sự kiện giữ hàng | Không tạo thêm tác động giữ hàng ngoài ý muốn |
| Một bước bên ngoài thất bại | Trạng thái thao tác thể hiện lỗi hoặc đang bù trừ; không báo xác nhận thành công sai |

Kiểm thử cạnh tranh cần cho hai giao dịch thực sự chồng lấp, có điểm đồng bộ để điều khiển thứ tự. Chạy lần lượt hai request không chứng minh cơ chế xử lý cạnh tranh hoạt động. Với Java/Spring, kiểm thử tích hợp nên dùng hệ cơ sở dữ liệu có hành vi khóa và cô lập tương thích môi trường chạy thực tế; mock repository không kiểm chứng được điều này.

Với lỗi rollback, hãy chủ động tạo lỗi sau một bước ghi để kiểm tra trạng thái cuối cùng của cả root và dòng. Với outbox và idempotency, cần mô phỏng mất phản hồi hoặc tiến trình dừng ở ranh giới quan trọng, vì đường thành công thông thường không bộc lộ lỗi ghi hai nơi.

## 10. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách sửa thiết kế |
|---|---|
| Mỗi entity hoặc mỗi bảng phải có một API CRUD độc lập | Chọn thao tác từ nghiệp vụ; mọi đường ghi phải bảo vệ bất biến |
| URI nằm dưới đơn hàng nghĩa là tự có giao dịch chung | Triển khai giao dịch và cơ chế cạnh tranh rõ ràng ở máy chủ |
| Có `@Transactional` là đủ chống mọi race condition | Kiểm chứng khóa, phiên bản, mức cô lập và tất cả đường ghi |
| `@Version` ở dòng đủ bảo vệ trạng thái đơn | Phối hợp cả bất biến phụ thuộc root |
| Dùng ETag của đơn cho mọi URI con | Dùng validator của resource đích hoặc chuyển thao tác về đúng resource có validator |
| Cho client gửi `total` để đỡ tính ở server | Máy chủ tính các giá trị dẫn xuất theo quy tắc miền |
| Đã đọc tồn kho nên chắc chắn mua được hàng | Phải có thao tác giữ hàng nguyên tử tại nơi quản lý tồn kho |
| Có một request HTTP thì mọi tác động đều rollback cùng nhau | Công bố ranh giới giao dịch và quy trình phối hợp giữa các thành phần |
| Sự kiện rồi sẽ đến nên không cần trạng thái trung gian | Biểu diễn đang xử lý, thất bại, timeout và bù trừ trong hợp đồng |

## 11. Bài tập vận dụng

Một API đặt lịch có `Appointment`, các `Participant`, tài nguyên phòng họp và yêu cầu thanh toán phí đặt phòng. Hãy xác định:

1. Quy tắc nào phải đúng ngay khi chỉnh danh sách người tham dự thành công?
2. Có nên đưa phòng họp, mọi lịch đặt phòng và thanh toán vào cùng aggregate không?
3. Hai request đồng thời đổi giờ và xác nhận lịch cần được điều phối thế nào?
4. Khi giữ được phòng nhưng thanh toán thất bại, client quan sát trạng thái gì và hệ thống bù trừ ra sao?
5. Retry sau timeout có thể tạo lịch hoặc thanh toán trùng ở đâu?

Gợi ý: có thể để lịch hẹn bảo vệ trạng thái và danh sách người tham dự, còn nơi quản lý lịch phòng bảo vệ việc không đặt trùng khung giờ. Một kiểm tra số người so với sức chứa phòng chỉ đủ chắc chắn nếu dữ liệu sức chứa và quy tắc thay đổi phòng đã được xác định rõ. Việc giữ phòng phải nguyên tử tại thành phần quản lý tài nguyên; đọc thấy phòng trống không phải một cam kết giữ chỗ.

Khi giải bài tập, hãy viết ít nhất một bất biến, một endpoint thay đổi dữ liệu, một tình huống cạnh tranh và một trạng thái thất bại mà client có thể hiểu. Mỗi lựa chọn ranh giới phải giải thích được dữ liệu nào cùng commit và dữ liệu nào cần phối hợp qua quy trình.
