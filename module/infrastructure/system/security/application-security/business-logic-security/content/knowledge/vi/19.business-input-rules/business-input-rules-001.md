# Domain input validation: kiểm tra đầu vào theo quy tắc nghiệp vụ

## 1. Đúng định dạng chưa chắc được phép thực hiện

Một API đặt hàng nhận `quantity = -3`, `unitPrice = 1` và `discount = 1000000`. Các giá trị đều là số hợp lệ về cú pháp. Nếu ứng dụng chỉ parse thành công rồi tính tổng, người gọi có thể làm tổng tiền âm, giảm giá tùy ý hoặc tăng tồn kho bằng một lệnh mua hàng có số lượng âm.

Một request khác có `quoteId` tồn tại nhưng thuộc khách hàng khác. Định danh đúng kiểu và bản ghi có thật vẫn không làm nó trở thành đầu vào hợp lệ cho đơn đang xử lý.

**Domain input validation** là việc kiểm tra dữ liệu đầu vào có mang ý nghĩa hợp lệ trong mô hình nghiệp vụ, đúng quan hệ, đúng trạng thái và đúng các điều kiện áp dụng hay không.

Trong bảo vệ logic nghiệp vụ, mục tiêu không dừng ở từ chối ký tự lạ. Hệ thống phải ngăn người gọi dùng dữ liệu có vẻ bình thường để sửa giá, đổi đối tượng đích, bỏ bước phê duyệt, vượt hạn mức hoặc thực hiện cùng một quyền lợi nhiều lần.

Một cách phân biệt hữu ích:

```text
Validation cú pháp:
    Dữ liệu có thể được đọc theo hợp đồng không?

Validation nghiệp vụ:
    Dữ liệu đó có ý nghĩa hợp lệ trong tình huống này không?

Authorization:
    Chủ thể này được thực hiện hành động trên đối tượng này không?

Kiểm soát đồng thời:
    Các điều kiện cần thiết còn đúng tới lúc ghi nhận hành động không?
```

Bốn nhóm bổ sung cho nhau. Không nhóm nào tự thay thế toàn bộ các nhóm còn lại.

## 2. Xác định ranh giới tin cậy của từng trường

Trước khi viết validator, hãy phân loại dữ liệu theo thẩm quyền.

| Loại dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Ý định do người dùng cung cấp | Sản phẩm muốn mua, số lượng, ghi chú | Kiểm tra cấu trúc, miền giá trị và quyền sử dụng |
| Giá trị do server quyết định | Giá có hiệu lực, thuế, mức ưu đãi, trạng thái đích | Tính hoặc nạp từ nguồn có thẩm quyền |
| Tham chiếu cần đối chiếu | Báo giá, tài khoản nhận, hợp đồng, basis | Kiểm tra đối tượng, tenant, quan hệ và hiệu lực |
| Điều kiện hiện hành | Tồn kho, hạn mức còn lại, membership, số lượt sử dụng | Kiểm tra với cơ chế nhất quán phù hợp |
| Dữ liệu lịch sử đã chốt | Nội dung được duyệt, giá đã cam kết, kết quả đã xảy ra | Giữ đúng snapshot và quy tắc sử dụng lại |

### 2.1. Không dùng body làm nguồn cho giá trị đặc quyền

Các trường sau thường không nên được áp dụng trực tiếp từ request thông thường:

```text
approvedBy
isApproved
isVip
effectiveUnitPrice
serverCalculatedTax
tenantId của aggregate
ownerId đặc quyền
trạng thái nội bộ
```

Có thể có lệnh đặc biệt được phép sửa giá hoặc chuyển owner, nhưng đó là hợp đồng có authorization và audit riêng. Không biến mọi endpoint cập nhật thành đường ghi các trường này.

### 2.2. Dữ liệu từng nhận từ server vẫn cần được đối chiếu

Client có thể gửi lại giá từng hiển thị hoặc một báo giá đã cũ. Hệ thống phải xác định đó là một đề nghị cần tính lại hay một tham chiếu tới snapshot được cam kết trong thời hạn.

Không mặc định luôn dùng giá mới hoặc luôn giữ giá client gửi. Policy báo giá cần nói rõ nguồn, thời hạn, dữ liệu làm mất hiệu lực và thời điểm chốt.

Một `quoteId` chỉ hỗ trợ tra cứu báo giá đã lưu. Nó không tự chứng minh quyền sử dụng hoặc việc báo giá phù hợp với giỏ hàng hiện tại.

## 3. Các tầng kiểm tra và trách nhiệm

| Tầng | Điều kiện điển hình | Không nên mặc định nó đã làm gì? |
|---|---|---|
| Parser/hợp đồng dữ liệu | Kiểu, trường bắt buộc, kích thước, độ sâu, cấu trúc | Đã kiểm tra quyền hoặc ý nghĩa nghiệp vụ |
| Value object | Số lượng, đơn vị, miền số tiền, định danh có kiểu | Đã kiểm tra quan hệ với đối tượng khác |
| Aggregate/lệnh miền | Trạng thái nguồn, quan hệ giữa trường, quy tắc thay đổi | Đã bảo vệ mọi dữ liệu ngoài aggregate |
| Application service | Nạp dữ liệu có thẩm quyền, authorization, phối hợp transaction | Transaction tự loại bỏ mọi race |
| Cơ sở dữ liệu | Không null, khóa ngoại, uniqueness, điều kiện lưu được | Đã thực thi toàn bộ policy phức tạp |

### 3.1. Kiểm tra ở controller là chưa đủ

Import, worker, API nội bộ hoặc công cụ quản trị có thể không đi qua controller web. Quy tắc bất biến cần đặt ở lớp mà các đường tạo/thay đổi domain đều tuân thủ.

Một DTO được kiểm tra `quantity > 0` không bảo vệ được một constructor hay hàm import khác vẫn tạo domain object với số lượng âm.

Điều này không có nghĩa phải sao chép mọi rule ở mọi lớp. Mỗi lớp giữ trách nhiệm rõ; các hàng rào bổ sung cần có lý do, chẳng hạn constraint bảo vệ dữ liệu khi có đường ghi khác.

### 3.2. Dữ liệu đã lưu cũng có thể không còn đáng tin tuyệt đối

Dữ liệu cũ, import sai hoặc một đường ghi bị lỗi có thể tạo trạng thái không hợp lệ. Khi phát hiện, không được tiếp tục thực thi như thể đã qua validation chỉ vì bản ghi nằm trong DB.

Cần dừng thao tác cần dữ liệu đúng và xử lý lỗi dữ liệu theo quy trình phù hợp. Không âm thầm sửa số tiền, owner hoặc trạng thái để lệnh chạy tiếp mà không có thẩm quyền.

## 4. Kiểm tra miền giá trị, đơn vị và giới hạn tài nguyên

### 4.1. Số lượng phải phù hợp loại hành động

Với lệnh mua sản phẩm đếm theo chiếc, có thể quy định số lượng nguyên từ 1 tới một giới hạn. Với hàng cân theo khối lượng, cần đơn vị và độ chính xác khác.

Không áp dụng một quy tắc `quantity > 0` cho mọi đại lượng có tên quantity mà không hiểu nghiệp vụ. Tuy nhiên, cũng không dùng số âm trong lệnh mua chỉ để biểu diễn trả hàng nếu mô hình không chủ ý cho phép.

Một thiết kế rõ có thể dùng lệnh trả hàng riêng với số lượng trả dương, đối chiếu lượng đã mua/đã trả; dấu của bút toán được server xác định theo loại nghiệp vụ.

### 4.2. Value object giữ điều kiện cục bộ

Ví dụ Java dưới đây dành cho mặt hàng đếm theo chiếc. Giới hạn là chính sách minh họa, không phải con số chung cho mọi sản phẩm.

```java
record ItemQuantity(int value) {
    public ItemQuantity {
        if (value < 1 || value > 10_000) {
            throw new DomainInputException("INVALID_ITEM_QUANTITY");
        }
    }
}

record RequestedLine(UUID productId, ItemQuantity quantity) {
    public RequestedLine {
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(quantity, "quantity");
    }
}
```

Đối tượng này ngăn số lượng cục bộ không hợp lệ. Nó chưa chứng minh sản phẩm tồn tại, người mua được dùng, tồn kho đủ hoặc tổng số lượng mỗi sản phẩm trong giỏ không vượt hạn mức.

### 4.3. Giới hạn tổng hợp, không chỉ từng phần tử

Nếu mỗi dòng được mua tối đa 10 sản phẩm, người gọi có thể chia cùng sản phẩm thành 20 dòng. Cần xác định giới hạn áp dụng theo dòng, sản phẩm, đơn, khách hàng hay khoảng thời gian.

Trước khi kiểm tra giới hạn theo sản phẩm, có thể gộp các dòng cùng sản phẩm theo quy tắc đã định. Không để việc chia nhỏ hoặc đổi thứ tự dòng làm mất điều kiện nghiệp vụ.

Cũng cần giới hạn số dòng, kích thước chuỗi, số phần tử, độ sâu cấu trúc và dữ liệu lồng nhau. Một giá trị hợp lệ về nghĩa vẫn có thể làm cạn tài nguyên nếu kích thước không bị giới hạn.

### 4.4. Bảo vệ phép tính trung gian

Số lượng từng dòng có thể vừa kiểu dữ liệu nhưng tổng hoặc tích lại tràn. Kiểm tra biên đầu vào và dùng kiểu/phép toán có hành vi tràn được kiểm soát.

Ví dụ với số nguyên trong Java, `Math.addExact` hoặc `Math.multiplyExact` có thể giúp phát hiện tràn ở phần phù hợp. Điều đó không thay thế giới hạn nghiệp vụ hoặc việc chọn đúng đơn vị.

Không chỉ kiểm tra tổng cuối cùng sau khi một phép tính đã tràn thành số nhỏ hoặc âm.

## 5. Số tiền, loại tiền và công thức giữa các trường

### 5.1. Không tính tiền bằng giả định số thực nhị phân là chính xác thập phân

Có thể dùng số nguyên theo đơn vị nhỏ nhất hoặc biểu diễn thập phân có kiểm soát. Với `BigDecimal`, tạo từ chuỗi thập phân phù hợp thay vì tạo từ một `double` đã mang sai số.

```java
BigDecimal requestedAmount = new BigDecimal("1250.50");
```

Cần định nghĩa độ chính xác, giới hạn độ lớn, scale và quy tắc làm tròn cho từng loại đại lượng. Không mặc định mọi loại tiền đều có hai chữ số phần lẻ.

Nếu so giá trị số bằng `BigDecimal`, phân biệt so sánh giá trị với so sánh biểu diễn. Chẳng hạn, scale có thể làm `equals` khác nhau trong khi `compareTo` cho giá trị số bằng nhau; policy phải chọn ý nghĩa phù hợp.

### 5.2. Không làm tròn ngầm để chấp nhận đầu vào trái hợp đồng

Nếu một trường chỉ cho phép hai chữ số phần lẻ, cần quyết định từ chối phần lẻ vượt mức hay làm tròn theo hợp đồng. Không để thư viện tự chọn hành vi làm thay đổi ý định mà client không biết.

Việc kiểm tra đầu vào và việc làm tròn thuế/tổng tiền là hai quy tắc có thể khác nhau. Với đầu vào yêu cầu biểu diễn chính xác, có thể dùng kiểm tra không cho phép làm tròn; với tính toán nghiệp vụ, dùng quy tắc đã được xác định và nhất quán.

### 5.3. Giới hạn biểu diễn trước phép toán đắt

Một chuỗi số rất dài hoặc số mũ cực lớn có thể gây tiêu tốn bộ nhớ/tính toán. Kiểm tra độ dài, dạng biểu diễn, số chữ số và giới hạn cần thiết trước các phép chuyển đổi hoặc tính toán nặng.

Nếu hợp đồng chỉ chấp nhận dạng thập phân thông thường, không cần cho phép số mũ chỉ vì parser có thể đọc. Nếu cho phép, phải định nghĩa giới hạn tương ứng.

Với parser hoặc kiểu số có thể nhận giá trị không hữu hạn, các trường nghiệp vụ không cho phép chúng phải từ chối rõ ràng.

### 5.4. Kiểm tra quan hệ giữa các giá trị

Một tổng tiền đặt hàng có thể được xác định theo dạng:

```text
tổng cuối = tổng tiền dòng sau giảm giá dòng
          + phí vận chuyển + thuế
          - giảm giá cấp đơn
```

Công thức cụ thể, thứ tự làm tròn và cơ sở tính thuế phải do domain quy định. Không trộn các giá trị khác loại tiền hoặc đơn vị.

Ví dụ cần kiểm tra giảm giá không vượt phần được phép giảm, hoàn tiền không vượt số tiền còn có thể hoàn và thời điểm kết thúc không trước thời điểm bắt đầu. Một field đúng miền riêng lẻ vẫn có thể tạo tổ hợp vô nghĩa.

Giá trị tổng do client gửi có thể dùng để phát hiện khác biệt trong ý định xác nhận, nhưng không phải nguồn tính tổng có thẩm quyền.

## 6. Kiểm tra tham chiếu, quyền và trạng thái

### 6.1. Tồn tại chưa đủ

Với mỗi tham chiếu, cần biết nó có được phép dùng trong lệnh này không:

- Cùng tenant hoặc có quan hệ chia sẻ hợp lệ theo mô hình.
- Thuộc đúng hồ sơ, khách hàng, giỏ hàng hoặc vòng xử lý.
- Đúng loại và trạng thái hiệu lực.
- Chủ thể có quyền sử dụng theo hành động.
- Các thuộc tính như loại tiền, sản phẩm và số tiền tương thích.

Một `paymentMethodId` tồn tại nhưng không được phép dùng cho giao dịch này vẫn là đầu vào không hợp lệ trong ngữ cảnh. Một tài khoản nhận của giao dịch chuyển tiền có thể được phép thuộc bên ngoài; điều cần kiểm tra là quan hệ được loại giao dịch chấp nhận, không mặc định mọi bên đều phải thuộc người gọi.

### 6.2. Authorization trước khi trả lỗi làm lộ đối tượng

Có thể từ chối cấu trúc sai hoặc request quá lớn trước khi nạp dữ liệu. Nhưng thông báo như số dư, trạng thái phê duyệt, tên owner hoặc giá hợp đồng cần tuân thủ quyền tiết lộ.

Không dùng validator như một API dò xem ID người khác có tồn tại hay dữ liệu của họ đang ở trạng thái nào.

### 6.3. Trạng thái nguồn quyết định trường nào được thay đổi

Một giá trị hợp lệ trong `DRAFT` có thể không được sửa trong `APPROVED` hoặc `PAID`. Validation cần gắn với command và state machine.

Không cho client chọn trạng thái đích hoặc gán cờ duyệt rồi chỉ kiểm tra enum hợp lệ. `APPROVED` là một giá trị enum đúng nhưng không phải giá trị đầu vào hợp lệ của endpoint sửa bản nháp thông thường.

### 6.4. Thay căn cứ phải xử lý các quyết định phụ thuộc

Sửa số tiền, người nhận hoặc loại tiền có thể làm approval, báo giá hoặc bằng chứng xác nhận cũ không còn áp dụng. Cần tăng revision và vô hiệu hóa/duyệt lại đúng phần phụ thuộc theo policy.

Không coi request hợp lệ chỉ vì từng field qua validator trong khi hệ thống vẫn giữ một approval cho nội dung cũ.

## 7. Chuẩn hóa dữ liệu và hợp đồng PATCH

### 7.1. Chuẩn hóa theo ý nghĩa của trường

Khoảng trắng, chữ hoa/thường, Unicode và cách biểu diễn số có thể ảnh hưởng so sánh, uniqueness và fingerprint idempotency.

Chọn quy tắc phù hợp từng trường, rồi áp dụng nhất quán giữa validation, lưu trữ và so sánh. Không tùy tiện lowercase mọi định danh hoặc bỏ dấu tiếng Việt ở dữ liệu có ý nghĩa phân biệt.

Với chuỗi số theo hợp đồng chặt, có thể từ chối khoảng trắng hoặc dạng không được hỗ trợ thay vì âm thầm sửa. Với ghi chú tự do, khoảng trắng có thể là nội dung hợp lệ.

### 7.2. Tránh hai lớp diễn giải cùng payload khác nhau

Các key trùng trong JSON, khác biệt tên field hoặc tham số lặp có thể bị parser, validator và lớp ánh xạ xử lý khác nhau. Với dữ liệu nhạy cảm, nên từ chối biểu diễn mơ hồ hoặc định nghĩa một hành vi nhất quán và kiểm thử nó.

Không để validator đọc giá trị đầu tiên nhưng domain lưu giá trị cuối cùng của cùng một field.

Nếu giao thức có chữ ký trên dữ liệu gốc, xác minh theo đúng quy tắc của giao thức. Không tự normalize payload làm thay đổi dữ liệu được ký rồi giả định chữ ký vẫn chứng minh cùng nội dung.

### 7.3. Vắng mặt, null, rỗng và số không là những ý nghĩa khác nhau

Trong PATCH:

```text
không có field → giữ nguyên hay dùng mặc định?
field = null   → xóa, từ chối hay không hỗ trợ?
field = ""     → giá trị rỗng có hợp lệ không?
field = 0      → giá trị thật hay bị tạo bởi ép kiểu/mặc định?
```

Cần hợp đồng rõ. Không dùng mặc định `0`, `false` hoặc danh sách rỗng làm vô tình xóa hạn mức, bỏ yêu cầu phê duyệt hay thay cấu trúc nghiệp vụ.

DTO theo lệnh cụ thể và mô hình biểu diễn field có mặt giúp kiểm soát tốt hơn một map cập nhật entity tùy ý.

### 7.4. Validation không thay thế bảo vệ theo ngữ cảnh khác

Kiểm tra nghiệp vụ không thay truy vấn tham số hóa hoặc mã hóa đầu ra theo ngữ cảnh hiển thị. Không cấm dấu nháy hoặc ký tự tiếng Việt một cách rộng rãi để thay cho các cơ chế đó.

Tương tự, một chuỗi đúng pattern không tự chứng minh định danh bên ngoài thuộc đúng người hay tài liệu đúng sự thật.

## 8. Kiểm tra điều kiện có thể thay đổi trong transaction

### 8.1. Đọc rồi kiểm tra chưa đủ với tồn kho và hạn mức

Hai request cùng thấy tồn kho còn 1 và cùng đặt 1 có thể đều qua validator. Nếu cập nhật không được bảo vệ, hệ thống bán vượt tồn.

Một cập nhật có điều kiện cho số lượng đã được server xác nhận có thể là:

```sql
UPDATE stock
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE tenant_id = :authorized_tenant_id
  AND product_id = :checked_product_id
  AND :quantity > 0
  AND available >= :quantity
  AND version = :expected_stock_version;
```

Phải kiểm tra số dòng cập nhật. Điều kiện này minh họa một phần kiểm soát tồn kho; kiểu dữ liệu, giới hạn phép tính và constraint cần phù hợp schema.

Không dùng số lượng chưa qua domain validation, và không coi `0` dòng cập nhật là đặt hàng thành công.

### 8.2. Điều kiện duy nhất cần được bảo vệ ở tầng phù hợp

Ưu đãi chỉ dùng một lần, một khoản hoàn tiền không vượt số đã thu hoặc một reservation không bị tạo trùng đều có thể cần khóa, version, constraint hay ledger phù hợp.

Kiểm tra `exists` rồi chèn không tự ngăn hai transaction cùng chèn. Nếu dùng constraint, phạm vi khóa duy nhất phải phản ánh đúng tenant, chủ thể, chiến dịch và kỳ áp dụng theo nghiệp vụ.

### 8.3. Tính nguyên tử và ranh giới hệ thống ngoài

Nếu một lệnh giữ tồn cho nhiều sản phẩm, cần quy tắc rollback hoặc workflow khi một phần không đủ. Không commit từng phần rồi báo như toàn bộ chưa thực hiện nếu hợp đồng không cho phép.

Transaction cục bộ không đóng băng kho quyền, giá hoặc thanh toán ở hệ thống ngoài. Với các ranh giới đó, cần snapshot/ủy nhiệm có điều kiện, reservation, đối soát hoặc workflow phù hợp; không gọi một lần `validate` rồi tuyên bố mọi nguồn được bảo vệ tới commit.

### 8.4. Retry không được thay người dùng chấp nhận dữ liệu mới

Nếu báo giá hoặc căn cứ đổi, tự đọc version mới rồi tiếp tục có thể khiến người dùng chấp nhận giá hay người nhận chưa từng thấy. Có thể cần trả xung đột và yêu cầu xác nhận lại.

Idempotency giúp nhận diện cùng ý định, không cho phép bỏ qua validation của lệnh mới hoặc dùng key để vượt quyền.

## 9. Ví dụ Java: đặt hàng từ báo giá có thẩm quyền

Ví dụ dưới đây dùng báo giá đã lưu phía server, gắn với giỏ hàng và revision cụ thể. `PLACED` trong ví dụ là đã ghi nhận đặt hàng và reservation theo hợp đồng, không tự có nghĩa đã thanh toán.

Các dependency là thành phần của ứng dụng. Nhánh idempotency đã xác định đây là lệnh mới.

```java
record PlaceOrderCommand(
        UUID quoteId,
        long expectedOrderVersion,
        long expectedQuoteVersion) {}

OrderReceipt placeOrder(
        UUID tenantId,
        UUID orderId,
        PlaceOrderCommand command) {

    ActorContext actor = identity.requireTenantActor(tenantId);
    validateShape(command);

    return transactions.required(() -> {
        OrderDraft order = orders
                .lockByTenantAndId(actor.tenantId(), orderId)
                .orElseThrow(NotFound::new);

        orderPolicy.requireCanPlace(actor, order);
        order.requireState(OrderState.DRAFT);
        order.requireVersion(command.expectedOrderVersion());

        Quote quote = quotes
                .lockByTenantAndId(actor.tenantId(), command.quoteId())
                .orElseThrow(QuoteNotAvailable::new);

        quoteRules.requireUsableFor(
                actor, order, quote,
                command.expectedQuoteVersion(), clock.instant());

        ValidatedOrderBasis basis = orderRules.validateAndBuildBasis(
                order, quote);

        inventory.reserveAllInCurrentTransaction(
                actor.tenantId(), order.id(), basis.quantitiesByProduct());

        int changed = orders.markPlaced(
                actor.tenantId(), order.id(), order.version(), basis);
        if (changed != 1) {
            throw new Conflict("CONCURRENT_MODIFICATION");
        }

        OrderReceipt result = OrderReceipt.from(order, basis);
        audit.appendOrderPlaced(actor, order, basis, result);
        outbox.appendOrderPlaced(actor.tenantId(), order, basis);
        return result;
    });
}
```

Các hợp đồng quan trọng:

- `requireUsableFor` kiểm tra báo giá thuộc đúng đối tượng/khách hàng được phép, khớp revision giỏ hàng, version và thời hạn theo policy.
- `validateAndBuildBasis` dùng giá trị có thẩm quyền, kiểm tra công thức, loại tiền và số lượng tổng hợp; không chỉ sao chép tổng tiền client.
- `quantitiesByProduct` phản ánh số lượng cần giữ theo đúng đơn vị và giới hạn, không để tách dòng vượt kiểm tra.
- Ví dụ giả định inventory và order có thể cùng tham gia transaction đó. Nếu inventory là service ngoài, phải dùng hợp đồng/workflow khác, không giữ nguyên tên hàm rồi giả định nguyên tử.
- `markPlaced` ràng buộc trạng thái và version; kiểm tra kết quả cập nhật.
- Các ghi bắt buộc cần cùng commit hoặc rollback theo thiết kế.
- Không gọi cổng thanh toán rồi mong rollback cơ sở dữ liệu hoàn tác tiền đã chuyển.

Việc tạo kiểu `ValidatedOrderBasis` giúp giữ ranh giới trong code, nhưng kiểu đó chỉ có giá trị khi được xây qua các kiểm tra đúng và không bị deserialize trực tiếp từ body như dữ liệu đã được tin cậy.

## 10. Lỗi validation và phản hồi an toàn

| Nhóm vấn đề | Phản hồi thường dùng | Lưu ý |
|---|---|---|
| Cú pháp/kiểu/cấu trúc sai | `400` | Không để parser chấp nhận mơ hồ ngoài hợp đồng |
| Dữ liệu không đạt rule nghiệp vụ | `400` hoặc `422` theo API | Mã lỗi rõ, chi tiết field chỉ trong phạm vi được phép |
| Thiếu quyền | `403`, hoặc `404` để che sự tồn tại | Không giả thành lỗi format rồi lộ đối tượng |
| Version hoặc trạng thái xung đột | `409` | Có thể cần đọc lại và xác nhận lại |
| Nguồn bắt buộc không khả dụng | Lỗi dịch vụ phù hợp | Không coi chưa kiểm tra được là đã hợp lệ |

Ví dụ lỗi có thể chỉ ra `quantity` nằm ngoài giới hạn hoặc báo giá cần làm mới. Không trả stack trace, truy vấn, số dư hay dữ liệu của chủ thể khác vào message.

### 10.1. Không chấp nhận một phần âm thầm

Nếu một field không hợp lệ, không tự bỏ field đó rồi báo toàn bộ lệnh thành công trừ khi hợp đồng chủ động cho phép và phản ánh outcome rõ.

Nếu API cho xử lý từng phần của batch, cần outcome từng phần tử và idempotency phù hợp. Nếu yêu cầu nguyên tử, không để các phần đầu đã commit rồi trả lỗi như thể toàn bộ chưa có tác động.

### 10.2. Ghi nhận từ chối không phải chấp nhận nghiệp vụ

Hệ thống có thể lưu audit hoặc kết quả kiểm tra thất bại theo thiết kế. Điều cần ngăn là trạng thái chấp nhận, reservation, approval hoặc tác động trái với các điều kiện bắt buộc.

Không log nguyên payload nhạy cảm chỉ để phân tích validation. Dùng mã rule, tham chiếu, correlation ID và dữ liệu tối thiểu cần thiết.

### 10.3. Quy tắc thay đổi cần phiên bản và lộ trình

Khi giới hạn hoặc cách tính đổi, xác định nó áp dụng cho lệnh mới, bản nháp cũ, báo giá đã cam kết và quyết định đã chốt ra sao. Không áp một rule mới bằng cách tự sửa lịch sử đã hoàn tất.

Ngược lại, dữ liệu cũ không mặc định được miễn mọi kiểm tra hiện hành khi bắt đầu một hành động mới. Cần chính sách chuyển tiếp rõ.

## 11. Kiểm thử theo biên và tình huống lạm dụng

### 11.1. Ma trận tối thiểu

| Tình huống | Kỳ vọng |
|---|---|
| Quantity bằng 0, âm, vượt giới hạn hoặc tràn kiểu | Bị xử lý đúng rule của command, không tạo tác động sai |
| Cùng sản phẩm bị tách thành nhiều dòng | Giới hạn theo sản phẩm/khách hàng không bị vượt |
| Chuỗi số rất dài, scale hoặc số mũ vượt hợp đồng | Bị chặn trước phép tính nặng không cần thiết |
| Tiền khác loại hoặc đơn vị không khớp | Không cộng/so sánh như cùng đơn vị |
| Client sửa giá, tổng tiền, ưu đãi hoặc cờ quyền lợi | Không thay nguồn có thẩm quyền |
| Giảm giá hoặc hoàn tiền vượt phần được phép | Không tạo tổng/ledger trái bất biến |
| Tham chiếu tồn tại nhưng thuộc đối tượng/tenant khác | Không dùng chỉ vì lookup thành công |
| Báo giá hết hạn hoặc sai revision | Không áp dụng ngoài hợp đồng, yêu cầu xử lý lại phù hợp |
| Sửa căn cứ sau approval | Không giữ hiệu lực duyệt cho nội dung mới trái policy |
| PATCH thiếu, null, rỗng hoặc zero | Phân biệt đúng ý nghĩa đã công bố |
| Payload có key/tham số trùng mơ hồ | Parser, validator và lớp ghi không diễn giải khác nhau |
| Hai request cùng tranh tồn kho/hạn mức/ưu đãi | Không cùng tiêu thụ vượt phần cho phép |
| Một phần reservation hoặc ghi bắt buộc thất bại | Rollback/workflow đúng hợp đồng, không thành công giả |
| Import/worker bỏ qua controller | Domain invariants vẫn được bảo vệ |
| Dữ liệu hợp lệ ở biên cho phép | Thành công, không chặn quá mức |

### 11.2. Kiểm thử tính chất và biến đổi

Các tính chất có thể kiểm tra gồm không bán vượt tồn theo mô hình đã chọn, không hoàn vượt số tiền còn được hoàn và không nhận tổng tiền từ dữ liệu không có thẩm quyền.

Tách một sản phẩm thành nhiều dòng không được làm vượt giới hạn vốn áp dụng theo tổng sản phẩm. Đổi cách biểu diễn một giá trị tương đương chỉ được giữ cùng kết quả nếu hợp đồng coi chúng tương đương; không bỏ qua quy tắc chữ ký hoặc định dạng vì giả định đó.

Khi thứ tự dòng không mang ý nghĩa trong rule đang xét, đổi thứ tự không được làm mất kiểm tra tương ứng. Nếu chính sách phí/ưu đãi thực sự phụ thuộc thứ tự, phải mô hình hóa và kiểm thử theo chính sách đó.

### 11.3. Kiểm tra tác động sau lỗi

Không chỉ assert có lỗi. Kiểm tra state/basis, tồn kho, coupon, approval, operation và outbox không bị thay đổi trái hợp đồng.

Audit từ chối có thể được ghi hợp lệ. So business projection cần bảo vệ thay vì đòi toàn bộ hệ thống không có ghi nào.

Kiểm thử cạnh tranh nên điều khiển thời điểm đọc/ghi bằng cơ chế đồng bộ, không dựa vào sleep ngẫu nhiên. Kiểm tra khóa, transaction và constraint trên loại cơ sở dữ liệu triển khai khi cần; unit test không chứng minh được toàn bộ hành vi đó.

### 11.4. Test không được lặp nguyên implementation làm oracle

Kỳ vọng nên đến từ công thức, bảng rule và bất biến được thống nhất. Nếu test gọi cùng hàm tính tổng đang được kiểm thử để tạo expected total, cả hai có thể cùng sai.

Kết hợp ví dụ được tính độc lập, giá trị biên, dữ liệu sinh theo thuộc tính và regression cho các đường bypass thực tế. Không chỉ kiểm tra một hàm mang tên `validate` đã được gọi.

## 12. Tự rà soát domain input validation

Trước khi chấp nhận một command, hãy trả lời:

1. Field nào là ý định người dùng, field nào bắt buộc do server quyết định?
2. Kiểu, đơn vị, miền giá trị, độ chính xác và kích thước được giới hạn thế nào?
3. Các rule giữa nhiều field, dòng và đối tượng đã được biểu đạt chưa?
4. Tham chiếu có đúng tenant, chủ thể, quan hệ và trạng thái được phép không?
5. Validation có gắn với action và state machine thay vì cập nhật entity tùy ý không?
6. Chuẩn hóa, PATCH và fingerprint có cùng hiểu một ý nghĩa dữ liệu không?
7. Điều kiện thay đổi như tồn kho, hạn mức và ưu đãi được bảo vệ tới lúc ghi bằng cách nào?
8. Mọi đường tạo/sửa domain, gồm import và worker, có giữ cùng bất biến không?
9. Lỗi có dừng tác động không hợp lệ và chỉ tiết lộ dữ liệu được phép không?
10. Test có chứng minh cả giá trị hợp lệ được chấp nhận và các cách lạm dụng bị chặn không?

Đầu vào hợp lệ theo domain là dữ liệu có đúng ý nghĩa trong ngữ cảnh nghiệp vụ đang thực hiện, được đối chiếu với nguồn có thẩm quyền và được bảo vệ trước thay đổi đồng thời cần thiết. Parse thành công hoặc vượt qua vài annotation không đủ để kết luận một hành động an toàn.
