# Quantity parameter tampering — Chống sửa tham số số lượng để lạm dụng nghiệp vụ

## 1. Khi số lượng trở thành công cụ tấn công logic

**Quantity parameter tampering** là việc sửa, nhân bản hoặc tạo cách diễn giải khác nhau cho tham số số lượng nhằm làm hệ thống tính tiền, giữ tồn, áp quota, hoàn trả hoặc giao hàng trái quy tắc nghiệp vụ.

Không phải mọi thay đổi quantity đều là tấn công. Người dùng có thể hợp lệ khi đổi giỏ hàng từ 2 sang 3 sản phẩm. Lỗ hổng xuất hiện khi backend tin số lượng do client gửi mà không kiểm tra ý nghĩa, thẩm quyền, trạng thái và tính nhất quán qua toàn bộ quy trình.

Bài thuộc chương **Parameter Tampering** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`. Trọng tâm là giữ cùng một ý nghĩa số lượng từ request đến giá, reservation, đơn đã commit và tác dụng tiếp theo; đồng thời ngăn bypass bằng số âm, dòng trùng, replay hoặc xử lý đồng thời.

OWASP mô tả parameter tampering là thao túng các tham số trao đổi giữa client và server, trong đó giá và số lượng là những dữ liệu có thể bị sửa. Hidden field, cookie hoặc giá trị do JavaScript gửi không trở thành đáng tin chỉ vì người dùng bình thường không thấy ô nhập. [OWASP: Web Parameter Tampering](https://community.owasp.org/attacks/Web_Parameter_Tampering).

Ví dụ xuyên suốt là một giỏ hàng có các sản phẩm bán theo đơn vị nguyên:

- Chỉ cho sửa quantity khi cart ở `DRAFT`.
- API đặt quantity nhận giá trị tuyệt đối, không tự hiểu là cộng thêm.
- Quantity mỗi dòng trong `[1, 1000]`; xóa dòng dùng action riêng.
- Tổng cùng SKU chịu cap trên đơn, còn tổng mua trong một cửa sổ chịu quota riêng.
- Giá, quy cách đóng gói, warehouse và giá trị tồn có thẩm quyền do server xác định.
- Checkout chốt một tập nhu cầu duy nhất để tính giá, giữ tồn và tạo order.

Các giới hạn là policy minh họa, cần thay bằng quy tắc thực tế khi triển khai.

## 2. Những cách sửa quantity và hậu quả nghiệp vụ

| Cách sửa | Lỗi thiết kế có thể bị lợi dụng | Hậu quả |
| --- | --- | --- |
| Quantity âm | Chỉ kiểm tra cận trên hoặc trừ tồn trực tiếp | Tổng tiền âm, tăng tồn/quota thay vì tiêu thụ |
| Quantity bằng 0 | Dùng 0 như một nhánh đặc biệt không được định nghĩa | Nhận ưu đãi, reservation hoặc trạng thái không tương ứng |
| Số lẻ cho hàng bán theo cái | Ép kiểu hoặc làm tròn im lặng | Trả tiền một lượng, xử lý một lượng khác |
| Số rất lớn | Phép cộng/nhân tràn hoặc parser không có giới hạn | Tổng tiền sai, tốn tài nguyên, vượt cap |
| Tham số cùng tên xuất hiện nhiều lần | Các lớp lấy lần đầu/lần cuối khác nhau | Validator kiểm tra một số, nghiệp vụ dùng số khác |
| Nhiều dòng cùng SKU | Kiểm tra cap riêng từng dòng | Vượt giới hạn sản phẩm trên đơn |
| Hai request đồng thời | Đọc lượng còn lại rồi ghi tách rời | Bán hoặc dùng quota vượt mức |
| Retry một lệnh cộng quantity | Không có idempotency | Tăng quantity, giữ tồn hoặc tạo order nhiều lần |
| Đổi quantity sau khi chốt quote/phê duyệt | Không bind dữ liệu quyết định với nội dung thực thi | Dùng giá hoặc phê duyệt của lượng cũ cho lượng mới |
| Giả quantity ở action hủy/trả | Tin lượng client khai để hoàn tài nguyên | Hoàn nhiều hơn lượng thực sự đã giữ/mua |

Một ví dụ lỗi ngắn:

```java
long subtotal = trustedUnitPriceMinor * quantity;
stock.availableUnits -= quantity;
```

Nếu `quantity = -5` lọt vào, việc trừ tồn có thể thành cộng thêm tồn, còn subtotal có thể âm. Nếu hệ thống chỉ kiểm tra subtotal không vượt hạn mức, giá trị âm thậm chí còn qua kiểm tra đó.

Với nhiều dòng, tổng tiền cuối cùng vẫn dương chưa chứng minh từng quantity hợp lệ. Một dòng âm có thể bù một phần tiền của dòng dương và để lại nghĩa vụ giao hàng không tương ứng.

## 3. Định nghĩa rõ quantity có ý nghĩa gì

### 3.1. Giá trị tuyệt đối và delta là hai loại lệnh

```text
SetQuantity(5): quantity sau thao tác phải là 5.
AddQuantity(5): quantity sau thao tác bằng quantity cũ cộng 5.
RemoveLine: xóa dòng theo policy của cart.
```

Không để cùng endpoint lúc thì hiểu `quantity` là tổng mới, lúc lại là lượng tăng thêm. Một retry `AddQuantity(5)` có thể cộng lần nữa nếu không được nhận diện là cùng thao tác.

Ví dụ API đặt quantity:

```http
PUT /carts/{cartId}/lines/{lineId}/quantity
Idempotency-Key: set-line-quantity-01
Content-Type: application/json

{
  "quantity": 3,
  "expected_cart_version": 12
}
```

Trong hợp đồng này, quantity là số nguyên dương tuyệt đối. `0` không tự trở thành xóa dòng; số âm không trở thành trả hàng. Nếu sản phẩm cho một quy ước khác, phải định nghĩa và kiểm tra riêng, không để từng adapter suy đoán.

### 3.2. Đơn vị và quy cách phải có nguồn tin cậy

`quantity = 2` có thể nghĩa là hai cái, hai hộp hoặc hai kilogram. Nếu quy cách hộp gồm 12 cái, client không được tự thay `pack_size` từ 12 xuống 1 để tính tiền ít nhưng warehouse vẫn giao hai hộp.

Ví dụ chính dùng đơn vị nguyên và một quy cách server đã xác định cho SKU. Nếu bán theo khối lượng, có thể chọn đơn vị nhỏ nhất như gram hoặc một decimal contract có scale rõ, rồi áp dụng thống nhất cho giá, cap và tồn. Không dùng phép ép từ `0.9` sang `0` làm bước chuẩn hóa.

Những trường như warehouse, đơn vị, hệ số quy đổi và lượng giao không được lấy tùy ý từ body để ghi đè dữ liệu sản phẩm/đơn đã xác minh.

### 3.3. Chọn khóa đúng để cộng dồn

Cap theo SKU phải cộng các dòng cùng SKU. Quota theo nhóm sản phẩm có thể còn phải cộng nhiều biến thể cùng nhóm, trong khi reservation có thể tách theo warehouse.

Vì vậy không có một phép group chung cho mọi giới hạn. Cần chỉ rõ:

- Khóa tổng hợp để tính cap theo đơn.
- Khóa quota theo chủ thể/tenant/cửa sổ.
- Khóa allocation theo SKU, đơn vị cơ sở và vị trí tồn.

Trong ví dụ đơn giản, một cart dùng warehouse được server chọn và quantity cùng SKU được tổng hợp trước khi checkout.

## 4. Một biểu diễn quantity được kiểm tra và sử dụng thống nhất

### 4.1. Từ chối đầu vào mơ hồ

Với hợp đồng JSON integer, cần xử lý rõ các trường hợp thiếu, null, số âm, quá lớn, số lẻ hoặc số dưới dạng chuỗi. Không trông chờ mỗi tầng tự ép kiểu về một giá trị “có vẻ hợp lý”.

Các ví dụ cần đưa vào kiểm thử:

```http
quantity=1&quantity=10000
```

```json
{
  "quantity": 1,
  "quantity": 10000
}
```

Hoặc URL khai quantity 1, body khai quantity 10. Nếu một lớp kiểm tra query còn lớp tính tiền dùng body, kết quả không còn được bảo vệ bởi lần validation đầu tiên.

Hợp đồng ví dụ chọn một nguồn duy nhất cho field quantity và từ chối giá trị lặp khi chỉ mong đợi một giá trị. OWASP WSTG nêu rủi ro parameter pollution khi các thành phần diễn giải cùng tham số lặp khác nhau; phải kiểm tra hành vi thực tế của stack, không giả định framework nào cũng giống nhau. [OWASP WSTG: HTTP Parameter Pollution](https://wstg.owasp.org/latest/11-Injection/03-HTTP_Parameter_Pollution/).

### 4.2. Không sửa giá trị sai để tiếp tục

Tránh các cách như:

```java
quantity = Math.abs(quantity);
quantity = Math.max(1, Math.min(quantity, maxQuantity));
quantity = (int) parsedDecimal;
```

Chúng có thể thay đổi ý định, che dữ liệu bất thường hoặc tạo chênh lệch giữa lớp hash idempotency, lớp tính giá và lớp giao hàng. Một giá trị vượt miền nên bị từ chối hoặc đi qua quy trình ngoại lệ đã định nghĩa.

Chuẩn hóa hợp lệ, nếu có, phải được quy định trước và cùng dùng một kết quả đã chuẩn hóa. Không decode, parse hoặc diễn giải lại raw parameter ở một service phía sau theo quy tắc khác.

### 4.3. Kiểm soát chi phí parse và kích thước request

Giới hạn body, độ dài số, số dòng và độ sâu object trước hoặc trong parse. Chặn một số hàng triệu chữ số sau khi parser đã tiêu tốn hết bộ nhớ là quá muộn.

Tránh regex hoặc chuyển đổi số không có giới hạn trên dữ liệu rất dài. Lỗi parse không được làm fallback quantity về 0 hoặc 1 rồi thực hiện đơn hàng.

## 5. Kiểm tra quyền trên cart và state trước khi đổi lượng

### 5.1. Line ID phải thuộc đúng cart và tenant

Một quantity hoàn toàn hợp lệ vẫn có thể nhắm tới dòng hàng của người khác. Backend cần xác minh tenant context, quyền thao tác cart và quan hệ line–cart trước khi ghi.

```sql
SELECT l.*
FROM cart_line l
JOIN cart c
  ON c.tenant_id = l.tenant_id
 AND c.id = l.cart_id
WHERE c.tenant_id = :verified_tenant_id
  AND c.id = :cart_id
  AND l.id = :line_id;
```

Quan hệ dữ liệu đúng chưa thay thế quyền actor trên cart. SKU thực sự của line lấy từ dữ liệu server; request đổi quantity không được đồng thời đổi `sku_id`, tenant, owner hoặc giá.

### 5.2. Sửa quantity chỉ ở trạng thái cho phép

Policy ví dụ chỉ cho sửa cart ở `DRAFT`. Sau checkout, quantity đã trở thành một phần của order/reservation bất biến theo luồng này. Thay đổi sau đó phải qua action điều chỉnh/hủy/trả phù hợp.

Không để API generic update line tiếp tục hoạt động với một cart đã `CHECKED_OUT` chỉ vì user vẫn là owner. Owner hợp lệ không có quyền bỏ qua state machine.

### 5.3. Version chặn lệnh cũ ghi đè ngữ cảnh mới

Hai tab cùng sửa một line hoặc một request cũ tới trễ có thể làm quantity quay về dữ liệu đã lỗi thời. `expected_cart_version` giúp phát hiện client đang thao tác trên bản khác.

Mọi thay đổi line có ý nghĩa phải cùng tham gia quy tắc version của cart. Đổi quantity phải làm quote cũ mất hiệu lực hoặc không còn khớp version/hash; không giữ giá/phê duyệt cũ như thể nội dung chưa thay đổi.

## 6. Ví dụ Java cho action SetQuantity

### 6.1. DTO giới hạn những trường client được gửi

```java
public record SetQuantityInput(
    @NotNull @Min(1) @Max(1000) Integer quantity,
    @NotNull @Min(0) Long expectedCartVersion
) {}
```

Các annotation thuộc Jakarta Validation. Điểm vào phải thật sự chạy validation, có cấu hình parse theo hợp đồng và xử lý field thừa phù hợp. Annotation không tự bảo vệ lời gọi service/job bỏ qua cơ chế đó.

DTO không có `unit_price`, `line_total`, `reserved_quantity`, `fulfillment_quantity` hoặc `skip_stock_check`. Những dữ liệu này không được client đặt qua action sửa quantity.

### 6.2. Khung application service

Ví dụ dùng `TransactionTemplate` của Spring; các dependency là hợp đồng minh họa, chưa phải ứng dụng hoàn chỉnh.

```java
public QuantityReceipt setQuantity(
        SetQuantityCommand cmd, TrustedActor actor) {

    inputRules.requireValidSetQuantity(cmd);

    return transactions.execute(tx -> {
        VerifiedTenantContext tenant = tenantContexts.resolve(actor, cmd.tenantId());
        Cart cart = carts.lockByTenant(tenant, cmd.cartId());

        cartAccess.requireCanReadReceipt(actor, tenant, cart);

        IdempotencyClaim claim = idempotency.claim(
            tenant.id(), actor.principalId(), "SET_CART_QUANTITY",
            cmd.idempotencyKey(), fingerprints.setQuantity(cmd));

        if (claim.isCompleted()) {
            return claim.originalReceipt();
        }

        cartAccess.requireCanEdit(actor, tenant, cart);
        cart.requireDraftAndVersion(cmd.expectedCartVersion());

        CartLine line = lines.findByTenantCartAndId(
            tenant, cart.id(), cmd.lineId());

        long requested = cmd.quantity();
        List<CartLine> currentLines = lines.readForLockedCart(tenant, cart.id());

        quantityPolicy.requireAllowedReplacement(
            actor, cart, currentLines, line, requested);

        lines.setQuantityOrThrow(tenant, cart, line, requested);
        carts.advanceVersionAndInvalidateQuoteOrThrow(cart);

        QuantityReceipt receipt = audit.appendQuantityChanged(
            tenant, cart, line, actor, requested);

        outbox.appendCartQuantityChanged(receipt);
        idempotency.complete(claim, receipt);
        return receipt;
    });
}
```

Những giả định bắt buộc:

- `cmd.tenantId()` là selector, được resolver xác minh trước khi tạo context. Cart và line được truy vấn trong cùng tenant, cùng parent.
- `inputRules` chặn quantity sai miền và command không đúng cấu trúc; không chỉ kiểm tra ở frontend.
- `requireAllowedReplacement` tính trạng thái dự kiến sau khi **thay** quantity của line, không cộng quantity mới thêm vào quantity cũ nếu action là set. Nó xét cap theo SKU/đơn và các điều kiện ngữ cảnh phù hợp.
- Mọi writer thay cart line đều khóa cart trước, tăng version nhất quán và không bỏ qua state. Nếu hỗ trợ nhiều dòng cùng SKU, phép kiểm tra phải tổng hợp tất cả dòng; nếu cấm, schema cần ràng buộc tính duy nhất tương ứng.
- Giá/quote provisional nếu được trả về phải do server tính theo policy. Luồng ví dụ chưa giữ tồn khi sửa draft; kiểm tra cuối và reservation diễn ra ở checkout.
- Line, cart version, quote invalidation, audit, outbox và kết quả idempotency cùng commit hoặc cùng rollback.

Trong audit, line snapshot trước thay đổi và quantity mới phải được lấy đúng để không ghi sai before/after. Receipt replay là kết quả của lần set trước, không phải lời khẳng định quantity hiện tại không thể đã được thay bởi action khác.

## 7. Checkout phải dùng một tập nhu cầu có thẩm quyền

### 7.1. Không cho tính tiền một lượng, giữ tồn một lượng khác

Một request có thể cố gửi nhiều field tương tự:

```json
{
  "quantity": 1,
  "billing_quantity": 1,
  "fulfillment_quantity": 10,
  "reserved_quantity": 0
}
```

Action thông thường không được tự cho client điều khiển độc lập các lượng này. Nếu các loại quantity tồn tại hợp lệ, quan hệ giữa chúng phải được mô hình hóa; không chuyển raw body sang từng service để mỗi nơi chọn một field.

Trong mô hình checkout không backorder của bài, tạo một `Demand` chuẩn hóa từ cart đang khóa, gồm SKU, đơn vị cơ sở, vị trí tồn được server xác định và tổng quantity hợp lệ.

```text
Demand đã xác minh
    -> dữ liệu đầu vào tính giá
    -> cap và quota
    -> reservation
    -> order lines đã commit
    -> sự kiện dùng cho fulfillment.
```

Các bước dùng cùng Demand hoặc bản ghi bất biến tương ứng. Không tính tổng từ list A rồi giữ tồn bằng list B vẫn lấy từ payload client.

### 7.2. Dòng trùng không được né cap

Nếu cap của SKU P là 100, hai dòng 60 và 60 phải bị từ chối hoặc được hợp nhất thành 120 rồi từ chối. Việc mỗi dòng qua giới hạn 1.000 không đủ.

Nếu schema chọn một dòng mỗi SKU/cart, unique constraint `(tenant_id, cart_id, sku_id)` hỗ trợ invariant. API add line vẫn phải xử lý cạnh tranh và semantics khi SKU đã có, không bắt lỗi unique rồi tự cộng một lượng không được kiểm tra.

Cap có thể áp dụng cho cả nhóm biến thể hoặc principal trong nhiều order. Chỉ deduplicate dòng trong một cart không giải quyết quota cộng dồn hoặc hành vi tạo nhiều cart/key khác nhau.

### 7.3. Quote hoặc phê duyệt phải bind đúng quantity

Quote cần gắn với tenant, cart, version/nội dung nhu cầu, currency, dữ liệu giá/policy, điều kiện hiệu lực và các tham chiếu cần thiết. Một chữ ký bảo vệ quote không ngăn dùng nó sai object hoặc replay nếu backend không kiểm tra binding/state.

Checkout có thể chỉ nhận cart ID, quote ID và version kỳ vọng, rồi đọc quantity từ cart đã khóa. Nếu vẫn nhận quantity trong command, phải có hợp đồng đối chiếu rõ; không ưu tiên một bản tùy service.

Khi quantity làm thay đổi hạn mức hoặc nội dung đã được duyệt, kết quả phê duyệt cũ không tự áp dụng. Phải xét đúng snapshot/version hoặc đưa đơn qua quy trình lại theo policy.

### 7.4. Khung checkout thể hiện nguồn dữ liệu duy nhất

```java
return transactions.execute(tx -> {
    Cart cart = carts.lockByTenant(tenant, cmd.cartId());
    checkoutAccess.requireAllowed(actor, tenant, cart);

    IdempotencyClaim claim = idempotency.claim(
        tenant.id(), actor.principalId(), "CHECKOUT_CART",
        cmd.idempotencyKey(), fingerprints.checkout(cmd));

    if (claim.isCompleted()) {
        return claim.originalCheckoutResult();
    }

    cart.requireDraftAndVersion(cmd.expectedCartVersion());
    Demand demand = quantityPolicy.fromPersistedLines(
        tenant, cart, lines.readForLockedCart(tenant, cart.id()));

    VerifiedQuote quote = quotes.requireMatchingCurrentDemand(
        tenant, actor, cart, demand, cmd.quoteId());

    allocation.lockAndReserveOrThrow(tenant, actor, cart, demand);
    Order order = orders.createFromVerifiedDemand(tenant, actor, cart, demand, quote);

    reservations.attachToOrderOrThrow(tenant, cart, order, demand);
    carts.markCheckedOutOrThrow(cart, order.id());

    CheckoutResult result = audit.appendCheckoutCommitted(order, demand);
    outbox.appendOrderReadyForFulfillment(order, demand);
    idempotency.complete(claim, result);
    return result;
});
```

Đây là khung minh họa, không phải một implementation allocation hoàn chỉnh. `allocation` phải áp cap/quota và giữ tồn đúng transaction, theo thứ tự khóa thống nhất. Các bản ghi reservation tạm trong transaction được gắn order hoặc rollback; không để reservation không có chủ thể nghiệp vụ sau commit.

Mô hình một order trên một cart còn có thể dùng unique constraint `(tenant_id, cart_id)` ở bảng order để chặn tạo đơn trùng. Consumer fulfillment đọc quantity đã commit hoặc event tạo từ dữ liệu đó, không dùng một bản request gốc chưa được xác minh.

## 8. Giữ tồn nguyên tử và bảo vệ các thao tác đồng thời

### 8.1. “Còn đủ” phải đúng tại lần ghi

Nếu tồn khả dụng là 8 và hai checkout cùng mua 6, hai phép đọc riêng đều có thể thấy 8. Không được chỉ kiểm tra trong Java rồi tăng reservation bằng lệnh không có điều kiện.

Ví dụ bảng tồn:

```sql
CREATE TABLE inventory_stock (
    tenant_id      uuid NOT NULL,
    warehouse_id   uuid NOT NULL,
    sku_id         uuid NOT NULL,
    on_hand_units  bigint NOT NULL,
    reserved_units bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, warehouse_id, sku_id),
    CHECK (on_hand_units >= 0),
    CHECK (reserved_units >= 0 AND reserved_units <= on_hand_units)
);
```

Update giữ tồn:

```sql
UPDATE inventory_stock
SET reserved_units = reserved_units + :verified_quantity
WHERE tenant_id = :verified_tenant_id
  AND warehouse_id = :server_warehouse_id
  AND sku_id = :verified_sku_id
  AND :verified_quantity > 0
  AND :verified_quantity <= on_hand_units - reserved_units;
```

Kiểm tra đúng một hàng cập nhật. Không có hàng hoặc thiếu tồn không có nghĩa được bỏ qua reservation. Quantity truyền vào là lượng đã xác minh từ Demand, không phải field giữ tồn riêng do client khai.

Trong PostgreSQL `READ COMMITTED`, khi một update phải chờ transaction khác sửa cùng hàng, điều kiện được đánh giá lại trên bản cập nhật phù hợp trước khi tiếp tục. Đây là cơ sở để lệnh có điều kiện như trên bảo vệ hàng tồn cùng với các constraint và giao thức transaction. [PostgreSQL: Read Committed](https://www.postgresql.org/docs/current/transaction-iso.html#XACT-READ-COMMITTED).

### 8.2. Nhiều SKU và quota cần cùng một ranh giới

Khóa/cập nhật các bucket theo thứ tự xác định; mọi đường giữ, tiêu thụ và hoàn trả cùng tài nguyên cần tuân giao thức tương thích. Một SKU thất bại phải rollback các phần đã giữ trước đó nếu API cam kết checkout nguyên tử.

Quota theo buyer, tenant hoặc cửa sổ cũng phải cập nhật có điều kiện hoặc dưới khóa phù hợp. Tách nhiều cart hoặc dùng key khác nhau không làm quota được nhân lên.

Nếu kho ở service khác, transaction database cục bộ không tự giữ được nguyên tử xuyên service. Cần reservation protocol, idempotency và xử lý thất bại/bù trừ phù hợp; không gọi hai hệ thống liên tiếp rồi coi không còn cửa sổ lỗi.

### 8.3. Cộng, nhân và quy đổi phải không tràn

Quantity dương rất lớn có thể làm phép tính tiền hoặc số đơn vị cơ sở bị wrap. Dùng kiểu có giới hạn được định nghĩa, kiểm tra cả kết quả và phép toán exact khi cần:

```java
long baseUnits = Math.multiplyExact(packageCount, serverUnitsPerPackage);
long lineGross = Math.multiplyExact(serverUnitPriceMinor, baseUnits);
long orderGross = Math.addExact(previousGross, lineGross);
```

Kiểm tra operand hợp lệ trước, xử lý overflow bằng không thực hiện operation; không thay bằng 0 hoặc số mặc định. Chính sách giá theo bậc phải được server tính từ đúng Demand, không từ một quantity do client gửi ở request báo giá khác.

## 9. Hủy, trả hàng và fulfillment không được tin lại quantity client

### 9.1. Hủy toàn bộ reservation dùng lượng đã lưu

Giả sử một reservation thật sự giữ 2 đơn vị. Client gọi cancel kèm `quantity = 200` không được làm hệ thống trả 200 đơn vị về kho.

Action hủy toàn bộ nên lấy lượng từ reservation có thẩm quyền. Trong cùng transaction, chuyển reservation từ trạng thái còn hiệu lực sang đã giải phóng và cập nhật tồn tương ứng đúng một lần.

Nếu message cancel được giao lại, state/version hoặc deduplication ngăn giải phóng lần nữa. Không chỉ kiểm tra rằng reservation ID có tồn tại rồi cộng tài nguyên mỗi lần nhận lệnh.

### 9.2. Điều chỉnh hoặc hủy một phần có invariant riêng

Nếu hỗ trợ partial cancellation/return, lượng đề nghị vẫn là số dương trong action riêng và phải không vượt lượng còn đủ điều kiện. Cần kiểm tra tổng tích lũy đã hủy, đã giao, đã trả hoặc đang xử lý dưới concurrency.

Không dùng quantity âm ở endpoint mua hàng như shortcut cho hoàn trả. Quyền, trạng thái, nguồn giá và tác dụng tiền/tồn của các action này khác nhau.

### 9.3. Giữ được phương trình bảo toàn số lượng

Trong một mô hình đơn giản không backorder, với mọi lượng được theo dõi cùng đơn vị và chưa xét return:

```text
ordered_quantity
    = open_reserved_quantity
      + shipped_quantity
      + cancelled_quantity.

Các thành phần không âm;
một đơn vị không đồng thời vừa được giao vừa được hủy.
```

Nếu có backorder, partial fulfillment hoặc return, bổ sung các trạng thái/ledger phù hợp. Return không được xóa sự thật lịch sử rằng hàng từng được giao; cần lượng trả và hiệu lực tài nguyên riêng.

Sự kiện cho warehouse phải xuất phát từ order/allocation đã commit. Quantity trên shipping label hoặc callback không tự có quyền thay quantity đã đặt; chênh lệch phải được xác minh và xử lý theo workflow rõ.

## 10. Replay, idempotency và quote cũ

### 10.1. Ba loại lặp không giống nhau

| Loại lặp | Bảo vệ cần có |
| --- | --- |
| Gửi lại cùng command sau khi mất response | Idempotency key có fingerprint và kết quả bền vững |
| Gửi command mới/key mới nhắm cùng cart | State/version và ràng buộc một order trên cart theo mô hình |
| Broker giao lại event giữ/hủy/giao hàng | Consumer idempotency và transition reservation/order có điều kiện |

Absolute SetQuantity giảm rủi ro cộng dồn so với một lệnh delta khi bị gửi lại, nhưng vẫn có thể tạo thêm version, audit hoặc repricing nếu implementation xử lý như command mới. Cần hợp đồng replay rõ, không chỉ dựa vào tên HTTP method.

### 10.2. Cùng key nhưng đổi quantity phải bị phát hiện

Fingerprint cần chứa quantity hoặc binding nội dung tương đương, cart/line, version và các trường nghiệp vụ liên quan. Key đã dùng cho quantity 1 không được lấy lại cho quantity 10 rồi nhận một kết quả mơ hồ.

Namespace idempotency cần giữ tenant, principal và action phù hợp. Không trả receipt của cart/người khác chỉ vì cùng key.

### 10.3. Chữ ký không thay thế state và quyền hiện tại

Một quote đúng chữ ký có thể đã hết hạn, thuộc cart khác, dùng quantity khác hoặc đã được tiêu thụ theo policy. Kiểm tra integrity là cần thiết khi dùng token/quote được bảo vệ, nhưng không tự giải quyết replay hay chuyển trạng thái.

Sau quantity change, quote cũ phải không còn được dùng cho checkout nếu không khớp nội dung hiện tại. Không cho một field `reuse_quote = true` từ client bỏ qua kiểm tra này.

## 11. Phát hiện, ghi log và phản hồi đúng ngữ cảnh

Các tín hiệu đáng theo dõi gồm quantity ngoài miền, duplicate field, nhiều line trùng nhằm vượt cap, nhiều cart/key cùng nhắm quota, sửa quantity sau quote hoặc yêu cầu hủy vượt lượng đã giữ.

Một request lỗi có thể do client cũ hoặc thao tác không tương thích, chưa phải bằng chứng chắc chắn của tấn công. Kết hợp tần suất, actor, tài nguyên và chuỗi hành vi để đánh giá.

Log có thể giữ action, principal/tenant đã xác minh, cart/line/SKU, version, lượng trước và lượng đề nghị trong giới hạn cho phép, lượng chuẩn hóa, reason code và policy version. Không ghi nguyên một chuỗi số hoặc payload cực lớn để gây chi phí lần hai.

Chỉ trả giới hạn/tồn/quota mà caller được phép biết. Người không có quyền trên SKU hoặc tenant không nên nhận thông báo chứa tồn kho chi tiết chỉ vì quantity policy được gọi trước authorization.

Request bị từ chối không được tạo order, trừ/hoàn tồn hoặc phát fulfillment event. Attempt audit có thể được lưu theo thiết kế riêng. Audit thành công phải phản ánh state và quantity đã commit, không chỉ dữ liệu đã nhận từ client.

## 12. Kiểm thử từ payload đến tác dụng cuối

### 12.1. Lập baseline rồi thay từng giả định

Bắt đầu với một cart hợp lệ, giá server rõ, tồn/quota biết trước và một checkout có thể đối soát. Sau đó thay quantity hoặc cách biểu diễn và so sánh response, dữ liệu đã lưu, reservation, order và công việc nền.

OWASP WSTG nhấn mạnh kiểm tra dữ liệu có vẻ đúng hình thức nhưng không hợp lệ về nghiệp vụ, gồm dấu, range và những thay đổi trực tiếp ngoài điều frontend thường gửi. [OWASP WSTG: Business Logic Data Validation](https://wstg.owasp.org/latest/14-Business_Logic/01-Business_Logic_Data_Validation/).

### 12.2. Ma trận tình huống

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Quantity `-1`, giá trị âm nhỏ nhất của kiểu | Không tạo tổng âm hoặc tăng tài nguyên |
| Quantity `0` tại SetQuantity của mô hình | Bị từ chối, không ngầm remove hoặc nhận ưu đãi |
| Quantity `1`, `1000` và ngoài cận | Đúng hard range, còn kiểm tra cap thấp hơn theo ngữ cảnh |
| Số lẻ, chuỗi số, exponent khi hợp đồng không cho | Không bị coercion/truncate làm sai ý nghĩa |
| Số vượt kiểu, số quá dài hoặc array quá lớn | Bị chặn mà không có side effect hoặc chi phí không kiểm soát |
| Query/form có quantity lặp, thứ tự đảo ngược | Không có parser differential cho phép bypass |
| JSON trùng key hoặc query/body mâu thuẫn | Bị xử lý đúng một hợp đồng rõ |
| Product bán theo hộp với pack size tự khai | Không đổi đơn vị server để tính/giao sai |
| Hai dòng cùng SKU mỗi dòng dưới cap nhưng tổng vượt | Bị từ chối theo tổng nhu cầu |
| Nhiều biến thể cùng quota group | Không né quota nhóm qua khóa quá hẹp |
| Cùng SKU nhiều line tạo đồng thời | Không vượt policy uniqueness/tổng hợp |
| Line ID của cart hoặc tenant khác | Không đọc/ghi ngoài quyền |
| SetQuantity bị hiểu nhầm thành AddQuantity | Kết quả đúng semantics tuyệt đối đã công bố |
| Hai tab sửa với cùng expected version | Phát hiện stale/conflict theo policy, không ghi ngữ cảnh cũ |
| Quantity đổi sau quote hoặc phê duyệt | Quote/approval cũ không được dùng sai nội dung |
| Tính tiền 1 nhưng cố yêu cầu giao/giữ 10 | Một Demand có thẩm quyền chi phối các tác dụng |
| Hai checkout cùng tranh lượng tồn còn lại | Tổng reservation commit không vượt on hand |
| Hai key/cart cùng tranh quota người mua | Tổng tác dụng không vượt quota |
| Retry SetQuantity/checkout cùng key | Trả kết quả cũ, không cộng lượng hoặc tạo order mới |
| Cùng key nhưng quantity khác | Từ chối xung đột |
| Lỗi sau khi giữ SKU đầu, SKU sau thất bại | Rollback checkout nguyên tử và phần đã giữ |
| Hủy giữ 2 nhưng client khai hoàn 200 | Chỉ dùng lượng reservation có thẩm quyền |
| Message hủy/giao hàng được giao lại | Không hoàn hoặc tiêu thụ cùng lượng hai lần |
| Partial cancel/return đồng thời | Lượng tích lũy không vượt phần còn đủ điều kiện |
| Job fulfillment nhận raw payload khác order | Không dùng payload chưa xác minh để thay lượng đã commit |

### 12.3. Các tính chất giúp phát hiện lỗi rộng hơn

Trong phạm vi mô hình đã chọn, có thể kiểm tra:

- Tách/gộp cùng SKU không làm thay đổi quyết định cap theo tổng SKU.
- Tất cả lượng ở order, reservation và fulfillment có cùng đơn vị được định nghĩa.
- `0 <= reserved_units <= on_hand_units` luôn đúng với trạng thái đã commit.
- Thay đổi quantity hợp lệ làm quote nội dung cũ không còn được chấp nhận.
- Một request bị từ chối không đổi tổng tiền, state, reservation hoặc outbox nghiệp vụ.
- Cùng một command được gửi lại chỉ có một hiệu ứng nghiệp vụ.

Với race condition, dùng hai connection/transaction thật cùng tranh chấp cart, quota hoặc hàng tồn. Đọc kết quả commit bằng connection khác và đối soát nhiều bảng; chỉ gọi hai lần tuần tự hoặc kiểm tra mock validator không chứng minh được invariant đồng thời.

Các khung Java, DDL và tình huống trong bài mang tính thiết kế; chúng chưa được chạy như một ứng dụng hoàn chỉnh.

## 13. Bài tập áp dụng

Một cart có cap 100 cho SKU P và dùng quote của quantity 1. Client gửi hai dòng P, mỗi dòng 60; một adapter còn nhận `billing_quantity = 1` và `fulfillment_quantity = 120`. Sau một checkout bị timeout, client retry bằng key mới. Khi hủy, client khai quantity 200 dù reservation thực tế nhỏ hơn.

Hãy thiết kế:

1. Những field nào được phép nhận và field nào phải lấy/tính từ server?
2. Một Demand chuẩn hóa cần chứa những khóa, lượng và đơn vị nào?
3. Đường SetQuantity và AddQuantity được phân biệt, version và deduplicate như thế nào?
4. Quote phải bind dữ liệu gì để không được dùng cho quantity khác?
5. Tồn/quota, reservation, order và outbox được commit/rollback theo giao thức nào?
6. Hủy hoặc trả một phần dùng lượng có thẩm quyền và state nào để không hoàn thừa/lặp?
7. Những phép đối soát và kiểm thử nào chứng minh quantity được dùng thống nhất đến fulfillment?

Chống quantity tampering cần bảo vệ cả giá trị đầu vào lẫn ý nghĩa của nó qua các bước nghiệp vụ. Hệ thống chỉ an toàn khi lượng đã xác minh, quyền trên đối tượng, snapshot giá/phê duyệt, reservation và tác dụng cuối cùng cùng tuân một mô hình nhất quán, kể cả khi có request trùng hoặc xử lý đồng thời.
