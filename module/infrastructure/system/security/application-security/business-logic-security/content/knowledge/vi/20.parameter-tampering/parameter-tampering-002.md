# Price parameter tampering: chống sửa tham số giá

## 1. Giá hiển thị trên trình duyệt không phải nguồn có thẩm quyền

Một trang checkout hiển thị hai sản phẩm, mỗi sản phẩm 100.000 VND. Bộ tính giá phía server xác định giảm giá 20.000, phí vận chuyển 15.000 và khoản thuế minh họa 10.000. Tổng cần thanh toán là:

```text
2 × 100.000 - 20.000 + 15.000 + 10.000 = 205.000 VND
```

Các con số chỉ minh họa công thức, không đại diện cho một quy định thuế cụ thể.

Trước khi gửi request, người dùng sửa `unitPrice`, `discount` hoặc `total` trong payload. Nếu backend dùng các giá trị đó để tạo đơn hoặc khởi tạo thanh toán, người gọi có thể mua hàng với số tiền thấp hơn mức nghiệp vụ cho phép.

**Price parameter tampering** là việc sửa tham số liên quan đến giá nhằm làm thay đổi giá trị được ghi nhận, thu, hoàn hoặc dùng làm căn cứ xử lý, vượt khỏi quyền mà hệ thống cấp cho người gọi.

Đầu vào có thể nằm trong JSON, form, query string, cookie, dữ liệu local storage được gửi lại, một price ID hoặc tham chiếu báo giá. Không cần phá mã hóa đường truyền để thực hiện: người dùng kiểm soát client của chính mình.

Mục tiêu phòng vệ là giữ các bất biến:

- Giá và các thành phần tiền được xác định từ nguồn mà server có thẩm quyền sử dụng.
- Người dùng chỉ được lựa chọn những đầu vào mà nghiệp vụ cho phép.
- Xác nhận, đơn hàng và payment operation cùng tham chiếu một căn cứ giá phù hợp.
- Thay đổi giỏ hàng hoặc điều kiện tính giá không được âm thầm giữ kết quả xác nhận cũ.
- Không giao hàng, ghi nhận đủ tiền hoặc hoàn tiền chỉ vì client khai một số tiền.

## 2. Nhận diện những tham số có thể làm đổi giá

Không chỉ `price` hoặc `total` mới là đầu vào nhạy cảm.

| Nhóm tham số | Ví dụ bị sửa | Hệ quả có thể xảy ra |
|---|---|---|
| Giá trực tiếp | `unitPrice`, `subtotal`, `total` | Thu thiếu hoặc ghi sai giá trị đơn |
| Số lượng và đơn vị | Quantity âm, phần lẻ sai đơn vị, chia nhiều dòng | Tổng tiền, hạn mức hoặc giá theo bậc bị tính sai |
| Ưu đãi | `discountAmount`, `discountPercent`, `isVip`, nhóm khách hàng | Nhận mức giảm không được phép |
| Phí và thuế | `shippingFee`, `taxIncluded`, `taxAmount`, phí thanh toán | Loại bỏ một phần nghĩa vụ thanh toán |
| Tiền tệ và đơn vị tiền | `currency`, `amountMinor`, hệ số quy đổi | Cùng một con số bị hiểu thành giá trị khác |
| Tham chiếu giá | `priceId`, `priceListId`, `quoteId`, hợp đồng | Dùng giá của sản phẩm, khách hàng hoặc tenant khác |
| Điều kiện tính giá | Biến thể, địa chỉ, phương thức giao, chu kỳ dịch vụ | Giữ giá rẻ cho một cấu hình đắt hơn |
| Quyết định đặc quyền | `manualPrice`, `overrideApproved`, `approvedBy` | Tự cấp giảm giá hoặc dùng approval giả |

### 2.1. Ví dụ payload dễ bị lạm dụng

```http
POST /checkout
Content-Type: application/json

{
  "cartId": "cart-17",
  "items": [
    {"productId": "sku-1", "quantity": 2, "unitPrice": 1}
  ],
  "discountAmount": 200000,
  "shippingFee": 0,
  "taxAmount": 0,
  "total": 1,
  "currency": "VND"
}
```

Vấn đề không nằm ở việc JSON có parse được hay không. Backend cần xác định trường nào là lựa chọn được phép và trường nào phải bỏ khỏi hợp đồng hoặc chỉ được dùng như điều kiện đối chiếu.

### 2.2. Các lớp bảo vệ khác không tự ngăn được sửa giá

TLS bảo vệ dữ liệu trên đường truyền nhưng không làm client trở thành nguồn giá đáng tin. Đăng nhập xác định chủ thể theo cơ chế xác thực, không cho chủ thể quyền đặt giá tùy ý.

Hidden field, nút bị khóa, mã JavaScript rút gọn hoặc tính tổng ở trình duyệt cũng không thay kiểm tra server. Một checksum do chính client tự tạo không chứng minh giá trị được nghiệp vụ chấp nhận.

## 3. Chốt bất biến và ranh giới tin cậy

### 3.1. Phân biệt lựa chọn của khách với giá trị server quyết định

| Dữ liệu | Client có thể đề nghị gì? | Server phải xác định gì? |
|---|---|---|
| Sản phẩm/biến thể | Muốn mua lựa chọn nào | Có tồn tại, được bán và đúng phạm vi không |
| Số lượng | Muốn mua bao nhiêu | Miền giá trị, đơn vị, giới hạn và giá theo bậc |
| Mã ưu đãi | Muốn dùng mã nào | Điều kiện, mức giảm, khả năng kết hợp và lượt dùng |
| Địa chỉ/phương thức giao | Chọn đầu vào được phép | Phí, điều kiện phục vụ và căn cứ tính liên quan |
| Báo giá | Chấp nhận quote/version nào | Quote có thuộc giỏ/chủ thể và còn dùng được không |
| Tổng dự kiến | Chấp nhận con số nào nếu API hỗ trợ | Tổng có thẩm quyền và việc có cần xác nhận lại không |

Một `expectedTotal` do client gửi có thể là điều kiện để tránh thu khác số họ đã thấy. Nó không được dùng để thay thế tổng server tính hoặc tổng snapshot đã được chấp nhận.

### 3.2. Không ghép nguồn tin cậy với thành phần tiền không tin cậy

Các cách sau vẫn dễ bị lạm dụng:

```text
Lấy đơn giá từ DB nhưng trừ discountAmount client gửi.
Tính tổng hàng phía server nhưng dùng shippingFee trong body.
Kiểm tra total không vượt giá chuẩn nhưng cho client chọn bất kỳ giá thấp hơn.
Dùng giá đúng nhưng nhân số lượng âm hoặc sai đơn vị.
```

Mỗi thành phần ảnh hưởng số tiền phải có nguồn và quy tắc rõ. Một phần được tính ở server không tự làm cả tổng trở nên đáng tin.

### 3.3. Giá bằng 0 và giá âm cần ngữ nghĩa riêng

Đơn miễn phí có thể hợp lệ nếu sản phẩm hoặc chương trình cho phép. Không mặc định mọi tổng bằng 0 đều là tấn công.

Tuy nhiên, thiếu giá, lỗi lookup hoặc lỗi bộ tính giá không được tự biến thành giá 0. Giá trị chưa xác định khác với một quyết định nghiệp vụ cho phép miễn phí.

Tổng âm trong lệnh mua thông thường thường cần bị chặn theo mô hình đó. Hoàn tiền, bù trừ hoặc tín dụng nên có lệnh và ledger phù hợp, không dùng một giỏ hàng âm để thực hiện trá hình.

## 4. Xác định giá từ nguồn có thẩm quyền

### 4.1. Giá phụ thuộc ngữ cảnh được phép

Nguồn giá có thể là catalog, bảng giá theo tenant, hợp đồng, chương trình ưu đãi hoặc một báo giá đã được chấp nhận. Server cần xác định đúng nguồn theo chủ thể và giao dịch.

Không cho client tự khai `customerTier = WHOLESALE`, `isEmployee = true` hoặc chọn bảng giá nội bộ chỉ vì biết ID. Tham chiếu tồn tại vẫn cần kiểm tra quyền và điều kiện sử dụng.

Với `priceId`, đối chiếu ít nhất những yếu tố mà mô hình yêu cầu: sản phẩm, biến thể, loại tiền, đơn vị/chu kỳ, khách hàng, tenant và thời hạn. Price ID của gói rẻ không được dùng để mua gói cao cấp.

### 4.2. Ưu đãi phải được tính lại hoặc chốt theo chính sách

Mã giảm giá là đầu vào yêu cầu áp dụng. Mức giảm được xác định từ rule phía server:

- Sản phẩm, khách hàng và tenant nào đủ điều kiện.
- Số lượng, giá trị đơn và thời gian áp dụng.
- Giới hạn tổng, theo người dùng hoặc theo một kỳ.
- Có cho kết hợp với ưu đãi khác không.
- Cách phân bổ giảm giá cho dòng hàng khi cần hoàn tiền.

Không chỉ kiểm tra mã có tồn tại rồi chấp nhận số tiền giảm client tính.

Nếu báo giá cam kết giữ một ưu đãi có số lượt giới hạn, phải có cơ chế reservation hoặc quy tắc tương ứng. Việc phát quote không tự chứng minh đã giữ được lượt dùng cho khách.

### 4.3. Phí, thuế và quy đổi cần đúng căn cứ

Phí vận chuyển phải dựa trên lựa chọn hợp lệ và dữ liệu liên quan, không phải một số tiền tự khai. Thay địa chỉ, phương thức giao hoặc đặc tính hàng có thể cần tính lại.

Thuế, phí và tỷ giá cần được lấy theo nguồn/quy tắc của hệ thống. Không nhận một cờ như `taxIncluded = false` hoặc tỷ giá trong body rồi đổi nghĩa số tiền đã tính.

Tách ưu đãi giảm giá với phương tiện thanh toán như số dư/voucher thanh toán nếu mô hình coi chúng khác nhau. Nếu gộp nhầm, hệ thống có thể vừa giảm giá vừa ghi nhận đã thanh toán bằng cùng một quyền lợi.

## 5. Báo giá phía server và phiên bản căn cứ

### 5.1. Quote là lời chào giá có phạm vi, không phải tổng tiền trôi nổi

Một snapshot giá có thể cần giữ:

```text
quoteId + tenant + chủ thể/giỏ hàng được phép
+ cartRevision và cấu hình sản phẩm
+ dòng hàng, đơn vị, số lượng, đơn giá và phân bổ giảm
+ phí, thuế, tổng tiền, loại tiền và quy tắc biểu diễn
+ tham chiếu rule/bảng giá/ưu đãi đã dùng
+ validUntil và điều kiện làm mất hiệu lực
```

Định nghĩa cụ thể tùy nghiệp vụ. Điều bắt buộc là biết quote bao phủ đầu vào nào và được dùng cho hành động nào.

### 5.2. Giữ giá hay tính lại phải là chính sách rõ

Có hai cách thường gặp:

1. Server giữ snapshot giá trong thời hạn và điều kiện được cam kết.
2. Server yêu cầu tính lại trước xác nhận; nếu có thay đổi cần thiết, khách phải chấp nhận căn cứ mới.

Không luôn thay quote hợp lệ bằng giá catalog mới nếu nghiệp vụ đã cam kết giữ giá. Cũng không dùng quote cũ vô hạn chỉ vì client còn lưu ID.

Thay đổi giỏ hàng, địa chỉ, phương thức giao, tiền tệ hoặc điều kiện ưu đãi cần xử lý theo quan hệ phụ thuộc. Không để quote của một sản phẩm được dùng cho cấu hình khác.

### 5.3. Chữ ký không thay kiểm tra nghiệp vụ

Có thể lưu quote phía server hoặc dùng token có chữ ký để bảo vệ tính toàn vẹn của snapshot. Với token, vẫn cần kiểm tra nguồn ký, mục đích, tenant, chủ thể/giỏ, thời hạn và điều kiện dùng lại theo thiết kế.

Một token ký đúng cho giỏ của An không tự cho Bình sử dụng. Token chưa hết hạn cũng không tự cho phép đổi số lượng hoặc biến thể ngoài nội dung được ký.

Đặc biệt, một endpoint ký nguyên giá do client gửi mà không tính/kiểm tra có thẩm quyền chỉ làm giá giả mang chữ ký của hệ thống. Chữ ký bảo vệ nội dung đã ký, không làm nội dung ban đầu trở nên đúng.

### 5.4. Chống dùng lại ngoài hợp đồng

Nếu quote chỉ được dùng cho một đơn, cần cơ chế tiêu thụ hoặc ràng buộc duy nhất phù hợp, chẳng hạn theo tenant và quote. Nếu quote được tái sử dụng hợp lệ, vẫn cần ràng buộc đơn/operation để không tạo tác động trùng cho cùng ý định.

Một quote giá hợp lệ cũng không tự giữ tồn kho. Giá, ưu đãi, tồn kho và thanh toán cần các cơ chế riêng được phối hợp đúng workflow.

## 6. Hợp đồng đầu vào và biểu diễn số tiền

### 6.1. DTO xác nhận nên hẹp

Một API có thể nhận:

```http
POST /tenants/{tenantId}/carts/{cartId}/confirm-checkout
Content-Type: application/json
Idempotency-Key: client-command-key

{
  "quoteId": "quote-81",
  "expectedCartVersion": 12,
  "expectedQuoteVersion": 3
}
```

Không cần nhận đơn giá, mức giảm, phí và tổng tiền để tạo payment operation. Nếu có tổng dự kiến để xác nhận ý định, server chỉ đối chiếu nó với căn cứ có thẩm quyền.

Các trường đặc quyền ngoài hợp đồng nên được từ chối hoặc xử lý theo cấu hình rõ ràng, bảo đảm không lọt qua một lớp mapper khác để ghi entity. Không dựa vào việc UI không gửi chúng.

### 6.2. Chọn đơn vị và độ chính xác rõ ràng

Có thể dùng số nguyên theo đơn vị tiền nhỏ nhất hoặc số thập phân có kiểm soát. Luôn giữ loại tiền và định nghĩa đơn vị cùng số tiền.

Không mặc định mọi tiền tệ đều có hai chữ số phần lẻ, hoặc luôn nhân/chia 100 khi giao tiếp hệ thống ngoài. Adapter cần tuân theo hợp đồng đơn vị của chính bên nhận.

Với `BigDecimal`, tạo từ biểu diễn thập phân phù hợp, không qua `double` đã có sai số. Quy định giới hạn độ lớn, scale và làm tròn; kiểm tra cả phép tính trung gian nếu dùng số nguyên.

### 6.3. Từ chối biểu diễn mơ hồ và tốn tài nguyên

Các đầu vào như chuỗi quá dài, số mũ cực lớn, scale không được phép, dấu phân cách theo locale không phù hợp hoặc giá trị không hữu hạn cần được xử lý theo hợp đồng chặt.

`1.000` không nên lúc được hiểu là một nghìn, lúc là một đơn vị, tùy lớp parser. Không để validator và payment adapter diễn giải khác nhau.

Giới hạn kích thước/dạng biểu diễn trước các phép tính nặng. Phân biệt vắng mặt, `null` và giá trị 0; lỗi parse không được mặc định thành một đơn miễn phí.

### 6.4. Tham số trùng có thể tạo hai cách hiểu giá

Một request có hai field `total` hoặc cùng tham số ở query và body có thể bị các lớp chọn khác nhau. Tránh hợp đồng mơ hồ; với dữ liệu nhạy cảm, từ chối trường trùng hoặc bảo đảm một cách diễn giải được kiểm thử rõ ràng.

Nếu dùng chữ ký trên dữ liệu gốc, tuân thủ quy tắc xác minh của giao thức. Không normalize tùy ý rồi giả định nội dung được ký và nội dung dùng tính tiền vẫn là một.

## 7. Minh họa Java: tạo đơn và operation từ căn cứ giá được chấp nhận

Ví dụ sau dành cho checkout cần thanh toán với tổng dương. Một nhánh miễn phí hợp lệ cần policy và trạng thái phù hợp riêng, không được tạo bằng fallback giá 0.

Các dependency là hợp đồng minh họa của ứng dụng. Nhánh idempotency đã xác định đây là lệnh mới.

```java
record ConfirmCheckoutCommand(
        UUID quoteId,
        long expectedCartVersion,
        long expectedQuoteVersion) {}

CheckoutReceipt confirm(
        UUID tenantId,
        UUID cartId,
        ConfirmCheckoutCommand command) {

    ActorContext actor = identity.requireTenantActor(tenantId);
    validateShape(command);

    return transactions.required(() -> {
        Cart cart = carts.lockByTenantAndId(actor.tenantId(), cartId)
                .orElseThrow(NotFound::new);
        checkoutPolicy.requireCanConfirm(actor, cart);
        cart.requireVersion(command.expectedCartVersion());
        cart.requireOpenForCheckout();

        Quote quote = quotes
                .lockByTenantAndId(actor.tenantId(), command.quoteId())
                .orElseThrow(QuoteNotAvailable::new);

        AcceptedPriceBasis basis = quotePolicy.requireAcceptedBasis(
                actor, cart, quote,
                command.expectedQuoteVersion(), clock.instant());

        checkoutRules.requirePayableAndReady(actor, cart, basis);
        benefits.consumeOrConfirmReservations(cart, basis);

        Order order = orders.createPendingPayment(actor, cart, basis);
        PaymentOperation operation = payments.createForOrder(
                order, basis.totalInPaymentUnits(), basis.currency());

        quotes.consumeForOrder(quote, order);
        carts.markCheckoutStarted(cart, order);
        audit.appendCheckoutAccepted(actor, cart, basis, order, operation);
        outbox.appendPaymentRequested(actor.tenantId(), order, operation);

        return CheckoutReceipt.from(order, operation);
    });
}
```

Các hợp đồng cần được triển khai đúng:

- Quote được tra trong đúng tenant, gắn đúng giỏ/chủ thể, revision, cấu hình và version.
- `AcceptedPriceBasis` lấy từ dữ liệu server đã tính và kiểm chứng; không deserialize kiểu này từ body rồi tin nó.
- Basis giữ đầy đủ dòng hàng, phí/thuế/giảm giá, tổng và loại tiền theo policy. Không chỉ giữ một total không giải thích được nguồn.
- `requirePayableAndReady` kiểm tra điều kiện còn bắt buộc, gồm các guards liên quan của workflow; không thay bằng tổng client.
- Ví dụ giả định các ghi/reservation trong hàm cùng tham gia được transaction cục bộ. Nếu một nguồn ở service ngoài, phải dùng workflow/ủy nhiệm phù hợp thay vì giả định transaction bao trùm mạng.
- Tiêu thụ quote, tạo order và operation có điều kiện/constraint chống cạnh tranh theo mô hình; không chỉ insert tự do sau một lần kiểm tra.
- Các ghi bắt buộc cùng commit hoặc rollback; lỗi không được bị nuốt thành thành công.
- Payment operation được lưu cùng số tiền và loại tiền chốt. Worker dùng operation đó, không đọc lại một tổng tùy ý từ client hay giỏ mutable.
- Outbox lưu ý định gửi sau commit; nó không tự bảo đảm tác động ngoài hệ thống đúng một lần.

Code thể hiện hướng thiết kế. Nó không phải một triển khai checkout hoàn chỉnh cho mọi yêu cầu tồn kho, thanh toán hoặc vận hành.

## 8. Cạnh tranh, idempotency và sự thay đổi sau chốt giá

### 8.1. Đổi giỏ hàng trong lúc xác nhận

Một lịch chạy có thể là:

```text
T1: Đọc quote cho một sản phẩm, tổng 100.000.
T2: Thêm một sản phẩm hoặc đổi sang biến thể đắt hơn.
T1: Thu 100.000 nhưng tạo đơn từ giỏ mới.
```

Cần ràng buộc quote với revision/căn cứ giỏ đã chấp nhận và bảo vệ cập nhật. Đơn được thanh toán phải được tạo từ snapshot phù hợp, không từ bất kỳ trạng thái giỏ nào đang có lúc worker chạy.

Khóa cart không tự bảo vệ mọi bảng con nếu các đường sửa dòng hàng không tham gia cùng giao thức. Mọi thay đổi ảnh hưởng giá phải tăng version/revision hoặc có điều kiện đồng thời tương đương.

### 8.2. Dùng một ưu đãi nhiều lần đồng thời

Hai request có thể cùng thấy coupon chưa dùng. Kiểm tra bằng `exists` trước rồi ghi sau không tự ngăn lặp.

Cần reservation, constraint, ledger hoặc giao thức nguyên tử phù hợp phạm vi giới hạn. Nếu quote hứa giữ ưu đãi, việc tiêu thụ phải khớp reservation đã cấp; nếu không giữ, cần quy tắc xác nhận lại khi điều kiện đổi.

### 8.3. Replay không được tạo một khoản thu mới

Idempotency key cần scope và fingerprint theo hợp đồng, ví dụ tenant, chủ thể, giỏ/order, hành động và nội dung xác nhận. Cùng key nhưng khác quote phải bị phát hiện.

Đổi key không được tạo quyền thu thêm cho cùng nghĩa vụ. Trạng thái, quote consumption và logical operation vẫn cần bảo vệ lặp nghiệp vụ.

Khi trả kết quả cũ, kiểm tra quyền nhận kết quả hiện tại. Replay không thực hiện lại transition và không tự tính giá mới như một lần mua mới.

### 8.4. Không âm thầm thu theo căn cứ mới

Nếu giá phải đổi theo policy, trả kết quả yêu cầu làm mới/xác nhận lại phù hợp. Không tự chọn giá mới cao hơn sau khi người dùng chỉ chấp nhận giá cũ.

Ngược lại, báo giá đã chốt hợp lệ không tự mất ý nghĩa chỉ vì catalog cập nhật trong khi payment operation đang chờ. Tiếp tục giải quyết operation theo căn cứ đã tạo và quy trình của nó.

## 9. Thanh toán, callback, giao hàng và hoàn tiền

### 9.1. Cổng thanh toán không tự bảo vệ giá nghiệp vụ

Nếu backend tạo payment request từ `amount` client gửi, cổng thanh toán có thể thu đúng con số sai đó. Thanh toán thành công không chứng minh giá đã được nghiệp vụ xác định đúng.

Server phải tạo hoặc xác nhận payment operation bằng amount/currency từ căn cứ chốt. Nếu client chọn một price/plan ID của nhà cung cấp thanh toán, phải kiểm tra mapping sang sản phẩm, cấu hình và giá được phép.

### 9.2. Callback phải khớp operation đã lưu

Không đánh dấu đủ tiền chỉ vì nhận `status = success` hoặc một `orderId` trong payload.

Cần xác thực nguồn theo giao thức và đối chiếu:

- Tài khoản tích hợp/merchant và tenant đã liên kết.
- Payment operation và đơn hàng phía server.
- Số tiền, loại tiền và đơn vị tương ứng.
- Trạng thái thanh toán có ý nghĩa ở bước nghiệp vụ cần xác nhận.
- Sự kiện đã xử lý hay chưa.

Phân biệt số tiền khách thanh toán với số ròng merchant nhận sau phí, và phân biệt các giai đoạn như chấp thuận, thu tiền hoặc quyết toán theo hợp đồng tích hợp. Không so nhầm hai đại lượng rồi tự đánh dấu đủ/thiếu.

Nếu hỗ trợ trả một phần hoặc trả nhiều lần, mô hình hóa rõ cách cộng nhận và chống đếm trùng. Không để một callback thành công với số tiền nhỏ bất kỳ mở khóa toàn bộ đơn.

### 9.3. Giao hàng phải dùng nội dung đã được chấp nhận

Một lỗi nguy hiểm là thu tiền cho snapshot cũ rồi tạo fulfillment từ giỏ hàng mới. Người gọi có thể trả tiền một sản phẩm rẻ nhưng sửa giỏ thành sản phẩm đắt trước khi worker lấy dữ liệu.

Order/fulfillment cần ràng buộc dòng hàng, số lượng và căn cứ thanh toán tương ứng. Không chỉ giữ total rồi cho phép mọi thay đổi ở phần hàng hóa.

### 9.4. Hoàn tiền không tính từ giá client hoặc catalog hiện tại

Giá mua, mức giảm, phí và số tiền đã thanh toán/đã hoàn có thể khác giá hiện tại. Refund phải theo snapshot và ledger gốc cùng policy hoàn tiền.

Với hoàn một phần, cần quy tắc phân bổ giảm giá, thuế và phí nếu áp dụng. Số tiền yêu cầu có thể là ý định cần xét, không phải lệnh bắt buộc hoàn theo con số client khai.

Kiểm soát cả các refund đang chờ và đã hoàn để không vượt giới hạn trong hai request đồng thời. Thay giá catalog hoặc tạo giỏ âm không được làm tăng quyền hoàn tiền của một giao dịch cũ.

## 10. Sửa giá đặc biệt, lỗi và dấu vết kiểm toán

### 10.1. Quyền override giá phải tách khỏi checkout thông thường

Có thể có nhân viên được quyền đề nghị giá thương lượng hoặc giảm phí. Cần lệnh riêng với phạm vi, hạn mức, lý do và phê duyệt khi cần.

Nếu yêu cầu maker–checker, người đề nghị giá đặc biệt không được tự duyệt chỉ vì có cả hai role. Quyết định phải gắn với đúng sản phẩm, khách hàng, số lượng, tiền tệ và thời hạn cần thiết.

Không nhận `overrideApproved = true` hay `approvedBy` từ client để thay quyết định đã lưu. Cũng không mở field override cho mọi service chỉ vì chúng nằm trong mạng nội bộ.

### 10.2. Phân loại lỗi mà không làm lộ dữ liệu

Payload sai hợp đồng có thể nhận `400`; vi phạm domain có thể là `400` hoặc `422`; version/báo giá xung đột có thể là `409` theo API. Với quote ngoài quyền, dùng `403` hoặc `404` theo chính sách tiết lộ.

Lỗi nguồn giá không được biến thành miễn phí hoặc chấp nhận giá client. Trả lỗi dịch vụ phù hợp và không bắt đầu tác động khi chưa đủ căn cứ.

Không trả bảng giá hợp đồng, ưu đãi riêng hoặc thông tin khách hàng khác vào message để giải thích quote không dùng được.

### 10.3. Audit liên kết được căn cứ giá tới khoản thu

Thông tin hữu ích gồm quote/basis, cart revision, order, payment operation, currency/unit, breakdown, phiên bản policy/bảng giá và chủ thể thực hiện hoặc override.

Không cần log token, secret, dữ liệu thanh toán nhạy cảm hoặc toàn bộ payload gốc. Ghi tham chiếu và dữ liệu tối thiểu phục vụ đối soát trong phạm vi được phép.

Audit từ chối phải được lưu bằng cơ chế phù hợp nếu transaction nghiệp vụ rollback. Một lỗi log không được làm hành động sửa giá trái phép đi qua.

### 10.4. Những cách sửa chưa đủ

| Cách làm | Vì sao chưa đủ? |
|---|---|
| Chỉ tính tổng trên frontend | Người dùng kiểm soát request |
| Lấy giá DB nhưng dùng giảm giá/phí client gửi | Một thành phần không đáng tin vẫn làm sai tổng |
| Chỉ kiểm tra total dương | Vẫn có thể thu 1 thay vì 205.000 |
| Chấp nhận giá thấp hơn giá chuẩn | Cho phép chính hành vi giảm giá trái quyền |
| Ký payload giá trước khi xác minh nguồn | Hệ thống ký cho giá sai do client chọn |
| Kiểm tra chữ ký quote nhưng không kiểm tra giỏ/chủ thể | Quote hợp lệ bị dùng sai ngữ cảnh |
| Chỉ kiểm tra thanh toán success | Số tiền, currency hoặc operation có thể không khớp |
| Sửa checkout nhưng bỏ đường PATCH/import/admin | Còn đường thay căn cứ giá ngoài kiểm soát |
| Chỉ dùng idempotency key để chống mọi lặp | Đổi key có thể tạo ý định trùng nếu thiếu bất biến nghiệp vụ |

## 11. Kiểm thử tình huống sửa giá

### 11.1. Ma trận kiểm thử

| Tình huống | Kỳ vọng |
|---|---|
| Thêm/sửa `unitPrice`, `total`, phí hoặc thuế | Xử lý theo DTO; không thay số tiền có thẩm quyền |
| Khai VIP, bảng giá hoặc nhóm khách hàng không được phép | Không nhận giá đặc quyền |
| Price ID của sản phẩm/biến thể/chu kỳ khác | Không dùng cho cấu hình hiện tại |
| Coupon đúng mã nhưng sai người, sản phẩm hoặc thời hạn | Không tự áp dụng quyền lợi |
| Giảm giá vượt mức hoặc kết hợp ưu đãi bị cấm | Không tạo tổng trái rule |
| Quantity âm, bằng 0 sai policy, tràn hoặc chia nhỏ vượt bậc | Không làm sai giá/hạn mức |
| Currency, scale hoặc đơn vị tiền bị đổi | Không tạo khoản thu bị diễn giải sai |
| Số mũ, chuỗi quá dài, null hoặc parse lỗi | Không fallback giá 0 hoặc tốn tài nguyên không giới hạn |
| Quote hợp lệ của người/tenant/giỏ khác | Không được dùng ngoài phạm vi |
| Chữ ký quote đúng nhưng đầu vào giỏ đã đổi | Không coi chữ ký là đủ |
| Catalog đổi khi quote còn được cam kết hợp lệ | Giữ hoặc xử lý đúng chính sách quote, không tùy tiện tính lại |
| Quote hết hạn hoặc revision không khớp | Yêu cầu xử lý lại/xác nhận theo hợp đồng |
| Đổi địa chỉ/phương thức giao sau quote | Phí/thuế và xác nhận phụ thuộc không bị giữ sai |
| Hai checkout tranh cùng coupon hoặc quote một lần | Không tiêu thụ vượt quyền lợi |
| Gửi lại sau commit hoặc đổi key liên tục | Không thu thêm cho cùng nghĩa vụ trái policy |
| Callback success nhưng sai số tiền/currency/operation | Không mở khóa đơn như đã trả đủ |
| Sửa giỏ sau thanh toán trước fulfillment | Không giao nội dung mới chưa được chấp nhận |
| Refund sau khi catalog đổi hoặc hai refund đồng thời | Theo giao dịch gốc, không vượt số được hoàn |
| Đơn miễn phí hợp lệ và ưu đãi hợp lệ | Thành công, không chặn mọi giá 0 hoặc mọi giảm giá |

### 11.2. Kiểm tra tác động thay vì chỉ nhìn mã lỗi

Sau request bị chặn, xác nhận không có order/payment operation hoặc event mang căn cứ giá sai. Nếu operation cũ đã tồn tại, không được âm thầm đổi amount/currency của nó bằng payload mới.

Với lệnh thành công, đối chiếu breakdown, tổng, currency/unit và nội dung hàng giữa quote, order, operation và fulfillment. Một API trả tổng đúng nhưng gửi amount sai sang payment adapter vẫn là lỗi.

### 11.3. Kiểm thử có điều khiển ở ranh giới quan trọng

Điều khiển lịch chạy để sửa cart hoặc tiêu thụ coupon giữa đọc và ghi. Với transaction và constraint, kiểm thử trên loại cơ sở dữ liệu triển khai khi cần.

Dùng fake/điểm quan sát ở payment adapter để kiểm tra số tiền thực sự được gửi. Phân biệt lần truyền lại cùng operation với một khoản thu nghiệp vụ mới; nhiều lần gửi vật lý không nhất thiết là nhiều khoản thu nếu giao thức chống trùng đúng.

### 11.4. Kỳ vọng phải độc lập với implementation

Dùng ví dụ tính độc lập theo rule đã thống nhất, giá trị biên và bất biến để làm expected. Không gọi cùng một hàm tính tổng đang kiểm thử để tạo cả kết quả mong đợi lẫn thực tế.

Thêm regression ở đúng đường gây lỗi: nếu lỗi là payment adapter nhân sai đơn vị, một unit test chỉ kiểm tra DTO không ngăn lỗi quay lại. Nếu lỗi là endpoint tổng quát cho sửa giá, test phải đi qua endpoint đó.

## 12. Tự rà soát thiết kế chống sửa giá

Trước khi cho một con số ảnh hưởng đơn hoặc khoản thanh toán, hãy trả lời:

1. Thành phần giá này đến từ nguồn nào và ai được quyền thay đổi?
2. Client có thể sửa một thành phần phụ như phí, thuế, ưu đãi hoặc tỷ giá để làm sai tổng không?
3. Tham chiếu price/quote có gắn đúng sản phẩm, khách hàng, tenant và cấu hình không?
4. Quote giữ giá đến đâu, điều gì làm mất hiệu lực và khi nào cần xác nhận lại?
5. Số tiền có cùng loại tiền, đơn vị và quy tắc làm tròn qua mọi lớp không?
6. Đơn hàng và payment operation có cùng một căn cứ giá bất biến không?
7. Race, replay và thay cart sau chốt có thể tạo khoản thu hoặc hàng hóa không khớp không?
8. Callback và refund có đối chiếu giao dịch gốc thay vì tin amount client không?
9. Override giá có thẩm quyền, phạm vi và dấu vết riêng không?
10. Test có kiểm tra số tiền ở ranh giới tác động thực tế, cùng các luồng hợp lệ không?

Chống price parameter tampering nghĩa là không để dữ liệu do người gọi kiểm soát trở thành quyền quyết định giá ngoài hợp đồng. Server phải giữ được mối liên kết giữa nguồn giá, căn cứ được chấp nhận, nội dung đơn và tác động thanh toán qua toàn bộ workflow.
