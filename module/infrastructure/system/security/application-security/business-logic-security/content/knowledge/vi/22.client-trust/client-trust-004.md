# Untrusted hidden controls: không tin dữ liệu chỉ vì nó bị ẩn trên giao diện

## 1. Mục tiêu bài học

Trong chương **Client Trust** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **untrusted hidden controls** nhấn mạnh rằng dữ liệu đi qua client không trở thành có thẩm quyền chỉ vì người dùng bình thường không nhìn thấy hoặc không chỉnh trực tiếp trên form.

Một input ẩn có thể giữ orderId, giá, quyền, bước xử lý hoặc token. Các giá trị đó có vai trò khác nhau, nhưng đều phải được server diễn giải và kiểm chứng đúng hợp đồng khi nhận lại.

Nếu tin trực tiếp các field như unitPrice, approved, isPaid hoặc ownerId vì chúng “do server render vào hidden input”, hệ thống có thể bị sửa giá, nhảy bước phê duyệt, thao tác sai quyền hoặc xử lý trùng.

Sau bài học, bạn có thể:

- Phân biệt tính hiển thị của control với tính tin cậy của dữ liệu.
- Xác định field nào là lựa chọn người dùng, tham chiếu cần kiểm tra, giá trị do server quyết định hoặc token có mục đích riêng.
- Thiết kế backend không phụ thuộc việc nút bị ẩn, field bị khóa hay JavaScript đã validate.
- Dùng quote, CSRF token, version và idempotency key đúng vai trò.
- Kiểm thử request bị sửa trực tiếp và xác nhận không có hiệu ứng nghiệp vụ ngoài quyền.

## 2. Hidden là thuộc tính giao diện, không phải bằng chứng quyền

Ví dụ một form:

~~~html
<form method="post" action="/checkout/confirm">
  <input type="hidden" name="cartId" value="cart-31">
  <input type="hidden" name="unitPriceMinor" value="200000">
  <input type="hidden" name="discountPercent" value="0">
  <input type="hidden" name="requiresApproval" value="true">
  <button type="submit">Xác nhận</button>
</form>
~~~

Một browser thông thường không cho người dùng sửa hidden input bằng thao tác nhập liệu trực tiếp trên form. Nhưng caller có thể chỉnh DOM, thay dữ liệu trước khi gửi hoặc tự tạo request không đi qua trang này.

Server không có căn cứ để kết luận giá trị nhận được giống giá trị ban đầu chỉ vì tên field và endpoint không đổi.

### 2.1. Dữ liệu đã từng đúng vẫn có thể sai khi quay lại

~~~text
Server tạo dữ liệu tại thời điểm T1.
Dữ liệu được gửi ra client.
Client có thể giữ, sửa, bỏ hoặc gửi lại dữ liệu.
Server nhận request tại thời điểm T2.
~~~

Tại T2, cần xem dữ liệu là input theo hợp đồng. Nó có thể:

- Bị sửa.
- Thuộc đối tượng hoặc phiên khác.
- Đã hết hiệu lực.
- Không còn phù hợp trạng thái hiện tại.
- Được gửi lặp.
- Là giá trị hợp lệ về cú pháp nhưng ngoài quyền caller.

Việc server từng phát ra một giá trị không đủ bảo đảm tính toàn vẹn, hiệu lực và quyền sử dụng của mọi bản sao gửi lại.

### 2.2. Caller không bắt buộc dùng UI chính thức

API có thể được gọi từ browser, mobile, một client cũ hoặc công cụ gửi HTTP trực tiếp.

Ẩn nút Approve, khóa ô giá hoặc không hiển thị trường ownerId chỉ giúp trải nghiệm sử dụng bình thường. Endpoint thật vẫn phải kiểm tra actor, action, đối tượng, trạng thái và dữ liệu.

Không cần một tài khoản quản trị trên hệ thống mới có thể gửi thêm field vào request của chính mình.

## 3. Các dạng control dễ gây nhầm lẫn

| Cơ chế | Tác dụng ở client | Điều không được suy ra |
|---|---|---|
| input type=hidden | Mang dữ liệu nhưng không hiển thị như ô nhập | Giá trị không sửa được |
| readonly | Hạn chế sửa trực tiếp trên loại control có hỗ trợ | Server được tin giá trị nhận lại |
| disabled | Control thường không được gửi trong form submission thông thường | Caller không thể gửi cùng tên field bằng request khác |
| CSS ẩn hoặc thuộc tính hidden | Thay đổi việc hiển thị | Dữ liệu bí mật hoặc được bảo vệ khỏi thay đổi |
| data-* hoặc JavaScript state | Lưu dữ liệu phục vụ UI | Là nguồn quyền nghiệp vụ có thẩm quyền |
| Nút chỉ hiện theo role | Hướng dẫn hành động phù hợp | Endpoint có thể bỏ kiểm tra role/scope |
| Giá trị encode/mã khó đọc | Thay đổi cách biểu diễn | Có tính toàn vẹn hoặc quyền sử dụng |
| App mobile không có màn hình sửa field | Giới hạn UI chính thức | Payload của app không thể bị thay |

Tác dụng chính xác của control còn phụ thuộc loại control và cơ chế gửi request. Dù UI gửi hay không gửi một field, server vẫn cần một hợp đồng đầu vào rõ ràng.

### 3.1. Bỏ field cũng có thể là một cách sửa input

Nếu disabled làm form bình thường không gửi discountPercent, handler không được coi thiếu field là một lệnh reset tùy ý hoặc một giá trị đặc quyền.

Tương tự, thiếu requiresApproval không được mặc định thành “không cần phê duyệt”. Các quyết định đó phải đến từ policy và dữ liệu phía server.

### 3.2. Bí mật không nên được bảo vệ bằng cách chỉ ẩn

Một giá trị đã gửi đến browser có thể được quan sát bởi chủ thể điều khiển client.

Không đưa một bí mật dùng để ký hoặc một credential nội bộ vào hidden input rồi dựa vào việc nó không xuất hiện trên trang. Token có thể được thiết kế để trao cho client sử dụng, nhưng đó phải là token có phạm vi và cơ chế kiểm chứng phù hợp, không phải bí mật máy chủ bị che bằng UI.

## 4. Phân loại từng field theo vai trò

| Nhóm | Ví dụ | Cách server xử lý |
|---|---|---|
| Lựa chọn người dùng | quantity, deliveryOptionId, couponCode | Kiểm tra kiểu, phạm vi, quyền và điều kiện sử dụng |
| Tham chiếu đối tượng | cartId, orderId, quoteId | Nạp trong đúng tenant/scope và xác minh quan hệ |
| Quyết định server | unitPrice, total, tax/fee result, requiresApproval | Lấy/tính từ nguồn có thẩm quyền; không nhận làm quyết định từ client |
| Danh tính/quyền | actorId, tenantId có thẩm quyền, role, isAdmin | Xác lập từ ngữ cảnh được kiểm chứng và policy |
| Trạng thái/bằng chứng workflow | approved, paid, completedStep | Kiểm tra state machine và bằng chứng phía server |
| Điều kiện concurrency | expectedVersion | So với dữ liệu hiện tại; không coi là quyền |
| Chống lặp | idempotencyKey | Nhận diện command và kết quả, không cấp quyền |
| Token của giao thức | CSRF token, quote token, invitation token | Xác minh theo đúng mục đích và ràng buộc |

Một field nằm trong hidden input có thể thuộc bất kỳ nhóm nào. Không nên cấm hoặc tin toàn bộ chỉ dựa trên cách hiển thị.

### 4.1. Tham chiếu được chấp nhận nhưng không tự tạo quyền

cartId do client gửi có thể là input cần thiết. Server vẫn phải xác minh actor được checkout cart đó.

Một người biết orderId không được hoàn tiền đơn đó. Một quoteId tồn tại cũng không có nghĩa caller được dùng quote cho cart hoặc tenant khác.

### 4.2. Token hợp lệ chỉ chứng minh điều mà giao thức định nghĩa

Một CSRF token hợp lệ có thể đáp ứng kiểm soát chống gửi request ngoài ý muốn theo cơ chế ứng dụng. Nó không chứng minh caller được duyệt, giá đúng hoặc tiền đã được thanh toán.

Một expectedVersion đúng chỉ cho thấy điều kiện version khớp. Nó không chứng minh quyền sở hữu.

Một idempotency key giúp chống hiệu ứng lặp. Nó không cho phép thực hiện một command ngoài quyền.

Giá trị token không được diễn giải rộng hơn mục đích mà server đã thiết kế và kiểm chứng.

## 5. Ví dụ checkout bị phụ thuộc vào hidden field

Giả sử backend nhận trực tiếp:

~~~json
{
  "cartId": "cart-31",
  "unitPriceMinor": 1,
  "discountPercent": 100,
  "shippingFeeMinor": 0,
  "requiresApproval": false,
  "isPaid": true
}
~~~

Nếu các giá trị này được dùng để tính tiền hoặc chọn trạng thái, caller đang điều khiển những sự thật phải do server xác lập.

Những lỗi thường gặp:

~~~text
Dùng unitPrice từ form để tạo dòng đơn.
Thấy couponValid=true nên áp ưu đãi.
Thấy requiresApproval=false nên bỏ bước duyệt.
Thấy isPaid=true nên mở giao hàng.
Tin ownerId để xác định ai sở hữu cart.
~~~

Việc hidden field từng chứa giá trị đúng không sửa được các lỗi đó.

### 5.1. Giá và tổng tiền cần nguồn có thẩm quyền

Server lấy giá từ catalog, hợp đồng hoặc snapshot báo giá phù hợp với nghiệp vụ. Số lượng là lựa chọn được kiểm tra, không phải quyền tự đặt giá.

Các thành phần như phí và ưu đãi được tính/đối chiếu theo chính sách đã xác định. Không chấp nhận một discountPercent do client tự gán chỉ vì form bình thường không cho sửa.

Cần xử lý số tiền bằng biểu diễn chính xác theo currency và kiểm tra tràn/giới hạn trong tính toán. Một giá trị kiểu số hợp lệ vẫn có thể âm, vượt giới hạn hoặc sai đơn vị.

### 5.2. Coupon là đề nghị áp dụng, không phải kết quả xác minh

Client có thể gửi couponCode nếu endpoint cho phép. Server phải kiểm tra:

- Coupon có áp dụng cho actor/cart/sản phẩm không.
- Thời hạn và trạng thái còn phù hợp không.
- Có còn lượt hoặc hạn mức không.
- Có được kết hợp với ưu đãi khác không.
- Giá trị ưu đãi thực sự được phép là bao nhiêu.

Flag couponValid hoặc một giá trị discount đã render ở client không thay các kiểm tra này.

Nếu số lượt có thể bị tranh chấp, việc kiểm tra/giữ hoặc tiêu thụ lượt phải dùng cơ chế nhất quán phù hợp. Không chỉ kiểm tra ở lúc UI hiển thị ưu đãi.

### 5.3. Expected amount có thể là điều kiện của caller

Một API có thể chủ ý nhận expectedTotal để bảo đảm người dùng chỉ tiếp tục với tổng họ đã nhìn thấy.

Trong trường hợp đó:

~~~text
Server tính/lấy authoritative total.
So expectedTotal với authoritative total.
Nếu không khớp, không tự đổi giá để khớp input.
Áp dụng quy trình cập nhật báo giá/xác nhận lại theo hợp đồng.
~~~

expectedTotal là điều kiện chấp nhận của caller, không là nguồn giá.

Không âm thầm chuyển sang một số tiền khác mà quy trình đồng ý thanh toán chưa cho phép.

## 6. Một form có hidden controls nhưng không dựa vào chúng để cấp quyền

Một thiết kế dùng báo giá lưu tại server có thể gửi:

~~~html
<form method="post" action="/checkout/confirm">
  <input type="hidden" name="cartId" value="cart-31">
  <input type="hidden" name="quoteId" value="quote-88">
  <input type="hidden" name="expectedCartRevision" value="7">
  <input type="hidden" name="idempotencyKey" value="command-501">
  <input type="hidden" name="csrfToken" value="server-issued-token">
  <button type="submit">Xác nhận báo giá</button>
</form>
~~~

Token là giá trị minh họa. Cơ chế CSRF áp dụng theo mô hình xác thực/giao thức của ứng dụng.

| Field | Điều server phải kiểm chứng |
|---|---|
| cartId | Đúng tenant và actor được checkout cart này |
| quoteId | Quote hợp lệ, đúng cart/revision và phạm vi được phép dùng |
| expectedCartRevision | Khớp dữ liệu hiện tại theo hợp đồng concurrency |
| idempotencyKey | Đúng scope, fingerprint command và kết quả trước nếu có |
| csrfToken | Hợp lệ theo cơ chế chống CSRF của endpoint khi cơ chế đó yêu cầu |

Các field vẫn có thể bị sửa. Tính an toàn đến từ việc sửa chúng không tạo thêm quyền hoặc tạo một hiệu ứng không được phép.

### 6.1. Không nhận lại mọi field trong read model

Trang có thể hiển thị giá, discount, trạng thái review và người sở hữu. Command confirm không cần nhận tất cả dữ liệu đó để ghi trở lại entity.

Một command hẹp có thể chỉ gồm cartId, quoteId, expectedCartRevision và idempotency key. Danh tính, tenant có thẩm quyền, giá và trạng thái do server lấy từ nguồn phù hợp.

Field lạ như isPaid, approvedBy hoặc skipApproval cần được từ chối hoặc xử lý theo hợp đồng không tạo hiệu ứng. Trong ví dụ này chọn từ chối rõ ràng.

### 6.2. Dữ liệu tạm ở client không thay trạng thái server

Local storage, biến JavaScript hoặc state của mobile có thể giúp khôi phục giao diện. Chúng không phải nguồn quyết định cart đã submit, yêu cầu đã được duyệt hay payment đã thành công.

Nếu client gửi lại một draft cũ, backend kiểm tra revision và trạng thái hiện tại. Không ghi đè một cart đã xác nhận chỉ vì form cũ có status=DRAFT.

## 7. Quote có trạng thái hoặc token được ký

### 7.1. Quote lưu ở server

Một quote có thể chứa:

~~~text
quoteId
tenantId, cartId, cartRevision
actor/customer scope theo chính sách
các dòng, số lượng và price snapshot
currency, phí và ưu đãi áp dụng
delivery/address snapshot cần thiết
expiresAt, status, pricingPolicyVersion
~~~

Client giữ quoteId. Server nạp quote và kiểm tra caller được dùng nó.

Nếu caller đổi quantity, product, phương thức giao hoặc các dữ kiện ảnh hưởng giá, quote phải được đối chiếu/tạo lại theo chính sách. Không dùng quote rẻ cho một cart khác chỉ vì ID quote tồn tại.

### 7.2. Token được ký cần ràng buộc đủ ngữ cảnh

Một quote token có thể giúp bảo vệ tính toàn vẹn của dữ liệu do server phát hành, nếu được thiết kế và xác minh đúng.

Nhưng chỉ ký unitPrice rồi cho client tùy đổi productId, currency hoặc quantity có thể không bảo vệ đúng giao dịch.

Những ràng buộc cần xác định có thể gồm:

~~~text
nguồn phát hành và mục đích sử dụng
tenant, cart và revision
người/nhóm được dùng quote theo chính sách
các thành phần giá và lựa chọn được chốt
thời hạn, nonce/trạng thái dùng nếu cần
điều kiện thu hồi hoặc kiểm tra lại
~~~

Không mặc định chữ ký có nghĩa giá còn hiệu lực mãi hoặc stock/quota đã được giữ. Chữ ký cũng không tự mã hóa dữ liệu thành bí mật.

Không đưa khóa ký vào client để “tự cập nhật” hidden field.

### 7.3. Quote cũ và giá hiện tại

Không phải mọi checkout phải bỏ giá đã chốt để tính theo giá mới nhất. Một quote có thể được giữ giá trong thời gian được chính sách cho phép.

Ngược lại, không giữ mãi giá cũ chỉ vì user còn một tab hoặc một token.

Server cần xác định quote còn được dùng không và điều gì làm quote mất hiệu lực. Khi cần thay đổi giá/điều kiện, phải đi qua luồng thông báo/xác nhận phù hợp.

Nếu command đã commit trước khi quote hết hạn nhưng response bị mất, replay kết quả cũ khác với tạo giao dịch mới bằng quote đã hết hạn.

## 8. Hidden field không chứng minh workflow đã hoàn tất

### 8.1. Bỏ bước bằng tham số

Caller có thể gửi:

~~~json
{
  "step": "FINAL",
  "previousStepCompleted": true,
  "approvalDone": true
}
~~~

Server không được dùng các flag đó làm bằng chứng các bước trước đã xảy ra.

Mỗi command cần có tiền điều kiện phía server, ví dụ:

~~~text
Chỉ submit nội dung hợp lệ.
Chỉ approve revision đang chờ và đúng thẩm quyền.
Chỉ mở chi trả sau phê duyệt hợp lệ.
Chỉ giao hàng sau bằng chứng thanh toán/tài nguyên phù hợp.
~~~

UI wizard là cách điều hướng; state machine và bằng chứng nghiệp vụ ở server mới quyết định bước nào được thực hiện.

### 8.2. Trang thanh toán trả về không phải bằng chứng đã thu tiền

Một redirect hoặc form của client có status=success, paid=true hoặc paymentId không tự chứng minh giao dịch thành công.

Server cần bằng chứng có thẩm quyền theo tích hợp thanh toán: nguồn được xác minh, operation/account đúng, số tiền/currency và trạng thái phù hợp.

Notification trùng hoặc đến muộn phải được xử lý theo state machine và idempotency. Không cho client mở giao hàng chỉ bằng việc tự dựng trang/response giống một màn hình thành công.

### 8.3. CSRF và authorization cần cùng tồn tại

Một actor đã đăng nhập hợp lệ và có CSRF token hợp lệ vẫn có thể gửi một command ngoài quyền hoặc sửa input của chính mình.

Kiểm soát CSRF không thay việc kiểm tra role, object scope, tenant, số tiền hoặc phê duyệt.

Ngược lại, chỉ có authorization cũng không mặc định đáp ứng kiểm soát CSRF mà giao thức của endpoint yêu cầu.

## 9. Java minh họa xác nhận checkout

Ví dụ dùng quote lưu ở server và chỉ cho dùng một lần theo chính sách đã chọn. Các lựa chọn sản phẩm, số lượng và giao hàng đã được gắn vào cart/quote trước lúc confirm.

Mã là phác thảo tầng ứng dụng với repository giả định, không phải chương trình checkout độc lập.

Giả định:

- Authentication, tenant resolution và kiểm soát CSRF khi áp dụng đã được thực hiện.
- Decoder chỉ nhận các field của command.
- Các repository, receipt, audit và outbox tham gia cùng transaction.
- Quy tắc giá, ưu đãi và tài nguyên liên quan được kiểm tra theo hợp đồng của hệ thống.
- Không gọi cổng thanh toán hoặc giao hàng trong transaction này.

~~~java
record ConfirmCheckoutCommand(
        CartId cartId,
        QuoteId quoteId,
        long expectedCartRevision,
        String idempotencyKey) {
}

CheckoutAccepted confirm(
        Actor actor, ConfirmCheckoutCommand command) {
    return transactions.required(() -> {
        var cart = carts.lockForUpdate(
                actor.tenantId(), command.cartId());
        access.requireCanAccessCart(actor, cart);

        var scope = CommandScope.of(
                actor, CHECKOUT_CONFIRM);
        var fingerprint = fingerprints.of(command);

        var oldReceipt = receipts.find(
                scope, command.idempotencyKey());
        if (oldReceipt.isPresent()) {
            requireSameFingerprint(
                    oldReceipt.get(), fingerprint);
            access.requireCanReadCheckoutResult(
                    actor, oldReceipt.get().result());
            return oldReceipt.get().result();
        }

        authorization.requirePermit(
                actor, CHECKOUT_CONFIRM, cart);
        requireState(cart, DRAFT);
        requireRevision(
                cart, command.expectedCartRevision());

        var quote = quotes.lockForUpdate(
                actor.tenantId(), command.quoteId());
        quoteRules.requireUsableFor(
                quote, cart, actor, clock.instant());

        eligibility.requireAndReserveLocalBenefits(
                actor, cart, quote);
        var review = approvalPolicy.evaluate(
                actor, cart, quote, serverFacts.forCheckout(cart));

        var checkout = checkoutFactory.fromValidatedSnapshot(
                cart, quote, review);
        checkouts.insert(checkout);
        quote.markConsumed(checkout.id());
        cart.markConfirmed(checkout.id());
        quotes.save(quote);
        carts.save(cart);

        if (review.required()) {
            outbox.insertReviewRequested(checkout);
        } else {
            var operation = paymentOperations.createFor(checkout);
            outbox.insertPaymentRequested(operation);
        }

        var result = CheckoutAccepted.from(checkout);
        audit.insertCheckoutAccepted(actor, checkout);
        receipts.insert(
                scope, command.idempotencyKey(),
                fingerprint, result);
        return result;
    });
}
~~~

### 9.1. Giá trị có thẩm quyền đến từ đâu?

quoteRules phải kiểm tra quote đúng tenant, cart, revision, scope sử dụng, trạng thái và thời hạn theo chính sách.

checkoutFactory sao chép giá trị đã được chấp nhận từ snapshot có thẩm quyền. Nó không đọc unitPrice, requiresApproval hoặc isPaid từ raw request.

approvalPolicy dùng dữ liệu thực và chính sách, không một flag của form. Nhánh cần review chỉ tạo ý định review, chưa mở chi trả.

paymentOperations.createFor phải lưu operation bền vững với định danh ổn định và số tiền/currency từ checkout. Worker xử lý operation đó, không dựng lại từ hidden controls.

### 9.2. Các helper vẫn phải có hợp đồng thực tế

eligibility trong ví dụ đại diện cho các điều kiện động và giữ lượt/quota cục bộ nếu nghiệp vụ yêu cầu. Những thay đổi cùng DB phải dùng transaction/cơ chế cạnh tranh phù hợp.

Nếu điều kiện ở dịch vụ ngoài, transaction này không tự biến hai hệ thống thành nguyên tử. Cần giao thức và trạng thái chờ/đối soát tương ứng; không mặc định một lần validate UI đã giải quyết được.

Các hàm require là validation bắt buộc, không dùng Java assert cho kiểm soát bảo mật.

### 9.3. Accepted chưa phải đã thanh toán

Kết quả trả về có thể biểu thị REVIEW_PENDING hoặc PAYMENT_PENDING theo chính sách. Không ghi PAID chỉ vì order đã tạo hoặc outbox đã commit.

Chỉ bước nhận/xác minh bằng chứng thanh toán phù hợp mới được chuyển trạng thái theo state machine.

Nếu transaction thất bại, các thay đổi cart, quote, operation, receipt, quota cục bộ, audit và outbox của lần đó phải rollback theo hợp đồng.

Unique constraint và quy tắc state/version vẫn cần để request cạnh tranh hoặc key khác không tiêu thụ cùng quote một cách trái chính sách.

## 10. Stale form, nhiều tab và xử lý đồng thời

### 10.1. UI không phải snapshot có hiệu lực vô hạn

Giả sử tab A hiển thị cart revision 7 và quote Q7. Tab B thay quantity, tạo revision 8.

Khi tab A gửi confirm:

~~~text
expectedCartRevision=7
quoteId=Q7
~~~

Server phải kiểm tra dữ liệu hiện tại và binding của quote. Không xác nhận cart revision 8 bằng giá chỉ phù hợp cho revision 7.

Caller sửa hidden expectedCartRevision thành 8 cũng không đủ, vì Q7 vẫn phải được đối chiếu với cart và nội dung được chốt.

### 10.2. Đọc giá rồi ghi sau vẫn có thể sai

Nếu không có bảo vệ concurrency:

~~~text
Đọc cart/quote và cho phép.
Một command khác thay nội dung hoặc tiêu thụ ưu đãi.
Command đầu tạo giao dịch từ các facts không còn phù hợp.
~~~

Cần khóa, version, cập nhật có điều kiện hoặc giao thức nhất quán phù hợp. Những dữ kiện nào ảnh hưởng quyết định phải được nhận diện và bảo vệ.

Không chỉ khóa cart nếu bất biến còn phụ thuộc quota dùng chung của coupon hoặc tài nguyên khác.

### 10.3. Hai lần click và retry sau timeout

Disable nút sau click có thể giảm thao tác lặp vô ý. Nó không chống được request gửi lại, nhiều tab hoặc mất response.

Cùng key và cùng command đã commit nên nhận kết quả được lưu theo quyền xem hiện tại, không tạo thêm checkout/payment operation.

Hai key khác nhau vẫn phải bị giới hạn bởi trạng thái cart và khả năng dùng quote. Idempotency không thay state machine.

Nếu timeout xảy ra sau khi hệ thống ngoài có thể đã tạo hiệu ứng, không coi timeout là bằng chứng thất bại rồi tạo giao dịch mới. Tiếp tục đúng operation và đối soát theo hợp đồng tích hợp.

## 11. Các cách bảo vệ dễ tạo cảm giác an toàn sai

| Cách làm | Vì sao chưa giải quyết được |
|---|---|
| Dùng hidden input thay cho ô text | Chỉ đổi khả năng hiển thị |
| Đặt readonly/disabled | Không ngăn caller tự dựng request |
| Validate bằng JavaScript | Có thể không chạy hoặc bị bỏ qua |
| Obfuscate tên field hoặc mã JavaScript | Không tạo thẩm quyền server |
| Base64 giá trị | Không có bảo vệ toàn vẹn chỉ nhờ biểu diễn này |
| Có HTTPS nên tin payload | Bảo vệ kênh truyền không ngăn caller sửa dữ liệu trước khi gửi |
| Có CSRF token nên không kiểm tra quyền | Nhầm mục đích chống request ngoài ý muốn với authorization |
| Ký riêng giá nhưng không bind cart/product | Có thể áp dữ liệu hợp lệ vào sai ngữ cảnh |
| So sánh một checksum không có bí mật/nguồn tin cậy | Caller có thể tạo lại dữ liệu theo cách ứng dụng cho phép |
| Chỉ kiểm tra field ở endpoint mới | Endpoint cũ/form/import có thể vẫn tin hidden field |
| Hide nút Approve theo role | Endpoint approve vẫn cần kiểm tra actor và object scope |
| Tin state từ trang thành công | Client không xác nhận sự thật thanh toán |

Cơ chế mật mã hoặc token có thể là một phần thiết kế đúng khi được dùng theo giao thức có ràng buộc và nguồn thẩm quyền rõ. Không nên dùng một nhãn “đã mã hóa/đã ký” để bỏ các kiểm tra còn lại.

## 12. Decode và mapping phải nhất quán

### 12.1. Không có đường input phụ ghi đè sau kiểm tra

Nếu policy dùng cartId từ path nhưng handler lấy cartId khác từ body, việc kiểm tra có thể áp dụng cho sai đối tượng.

Nếu có field cùng ý nghĩa ở nhiều vị trí, hợp đồng phải xác định một nguồn target và cách xử lý mâu thuẫn. Tốt hơn là không tạo các bản sao không cần thiết.

Không để query, form và JSON có thứ tự ưu tiên khác nhau giữa các tầng.

### 12.2. Field trùng hoặc field lạ cần chính sách rõ

Với các giá trị nhạy cảm, parser/binder không được khiến validator nhìn một giá trị còn handler thực hiện một giá trị khác.

Có thể chọn decode nghiêm ngặt, từ chối key trùng và field ngoài command. Những route có định dạng khác phải giữ ý nghĩa tương ứng, không trở thành đường fallback permissive.

Nếu một field không được chấp nhận, đừng giữ raw payload rồi đưa lại vào mapper hoặc worker để “khôi phục” nó.

### 12.3. Không bind form vào toàn bộ entity

Một entity có thể chứa owner, tenant, approval, payment status và các field phục vụ lưu trữ. Chúng không tự là input được phép.

Dùng command theo action và phương thức domain có chủ đích. Chỉ việc một field từng xuất hiện trong response hoặc form không cấp quyền sửa field đó.

Các lựa chọn nested, collection và reference cũng cần kiểm tra scope; cấm isAdmin ở cấp gốc không đủ nếu một nhánh con còn có thể thay quan hệ quyền.

## 13. Kiểm thử bằng request bị sửa trực tiếp

### 13.1. Không chỉ kiểm thử form trên giao diện

Một test chỉ kiểm tra hidden input có đúng giá ban đầu hoặc nút Approve bị ẩn chưa chứng minh backend an toàn.

Cần tạo request ở ranh giới API thực tế, có thể thay, thêm, bỏ và gửi lại field, rồi quan sát dữ liệu đã commit.

Dùng fixture gồm:

~~~text
Actor A và actor B có cart riêng.
Hai tenant có dữ liệu tách biệt.
Cart C có revision và quote xác định.
Một policy yêu cầu review trong trường hợp được chọn.
Payment operation và outbox có thể kiểm tra.
~~~

Nếu endpoint yêu cầu CSRF theo mô hình xác thực đang dùng, chuẩn bị token hợp lệ cho những test muốn đi tới lớp authorization/nghiệp vụ. Điều đó giúp phát hiện lỗi nằm sau kiểm soát CSRF, thay vì mọi request đều bị chặn ở cùng một cổng đầu tiên.

### 13.2. Ma trận tình huống

| Thay đổi ở client/request | Điều phải kiểm chứng |
|---|---|
| Sửa hidden unitPrice/total/discount | Không dùng làm giá có thẩm quyền; đúng chính sách field của endpoint |
| Gửi thủ công một field vốn disabled | Không có thêm quyền chỉ vì form bình thường không gửi |
| Sửa readonly quantity tại endpoint cho phép chọn số lượng | Server vẫn kiểm tra số lượng và tính giá hợp lệ |
| Bỏ requiresApproval hoặc gửi false | Không tắt bước review do server yêu cầu |
| Gửi approvalDone=true hoặc step=FINAL | Không bỏ qua tiền điều kiện/state machine |
| Gửi isPaid=true hoặc status=success từ trang quay về | Không mở giao hàng hay ghi PAID chỉ từ client |
| Đổi cartId sang cart của B | Không truy cập/checkout ngoài scope |
| Đổi tenantId/ownerId/role trong payload | Không thay danh tính hoặc quyền có thẩm quyền |
| Dùng quote của cart/người/tenant khác | Không áp dữ liệu hợp lệ vào sai ngữ cảnh |
| Dùng quote hết hạn cho command mới | Không tạo giao dịch ngoài chính sách hiệu lực |
| Sửa dữ liệu của quote token được ký, nếu có dùng | Xác minh thất bại theo giao thức |
| Token hợp lệ nhưng sai purpose/action | Không dùng thay token của một hành động khác |
| CSRF token hợp lệ kèm field quyền/giá bị giả | CSRF không làm các field đó đáng tin cậy |
| Thiếu/sai CSRF token ở endpoint yêu cầu nó | Bị chặn theo cơ chế CSRF, không có hiệu ứng |
| Form revision cũ sau khi cart thay đổi | Không xác nhận nội dung mới bằng quote/sự đồng ý cũ |
| Hai request confirm cùng key | Một hiệu ứng, replay đúng kết quả nếu đã commit |
| Hai key khác nhau cùng cart/quote một lần | Không tạo hai checkout/payment operation trái chính sách |
| Same key nhưng đổi cart hoặc quote | Phát hiện xung đột command |
| Người khác biết idempotency key | Không đọc receipt ngoài quyền |
| Client tự gửi couponValid=true | Eligibility và hạn mức vẫn do server kiểm tra |
| Endpoint cũ nhận hidden fields rộng hơn | Không trở thành đường bypass endpoint mới |
| Duplicate key/query-body mâu thuẫn | Không có hai cách hiểu dẫn tới authorize và execute khác nhau |
| Lỗi khi ghi audit/outbox bắt buộc | Không để lại checkout/quote consumed/operation một phần |
| Consumer nhận message trùng | Không tạo thêm hiệu ứng chỉ nhờ một lần click bị lặp ở client |

Các kỳ vọng cụ thể cần theo hợp đồng endpoint. Trong ví dụ command hẹp, các field giá/trạng thái ngoài command bị từ chối rõ ràng.

### 13.3. Bất biến nên kiểm tra sau khi request kết thúc

~~~text
Payment amount/currency đến từ snapshot có thẩm quyền.
Có review bắt buộc thì confirm chưa phát ý định chi trả.
PAID cần bằng chứng thanh toán phù hợp.
Một quote dùng một lần không tạo nhiều checkout độc lập.
Cart/resource thuộc đúng actor scope và tenant.
Request bị chặn không tạo thay đổi nghiệp vụ của hành động đó.
~~~

Một rule ở UI không phải bằng chứng cho các bất biến này.

### 13.4. Đọc lại dữ liệu thay vì chỉ nhìn response

Với request bị từ chối, đọc lại bằng transaction mới:

~~~text
cart/quote giữ trạng thái đúng trước lần thử
không có checkout thành công ngoài ý định
không có payment operation hoặc fulfillment job trái phép
không tiêu thụ thêm lượt ưu đãi
không có audit/outbox thành công của command bị chặn
không có dữ liệu của cart người khác trong response
~~~

Security event về lần thử có thể được ghi. Nó khác với audit xác nhận nghiệp vụ thành công.

Một response 403/400 không đủ nếu handler đã tạo job trước khi trả lỗi.

### 13.5. Kiểm thử policy review độc lập với field client

Chuẩn bị một cart/quote mà policy server bắt buộc review.

Thực hiện hai request:

~~~text
Request A:
  thêm requiresApproval=false và approvalDone=true.
  Kỳ vọng bị từ chối theo schema command nghiêm ngặt.

Request B:
  chỉ có các field command hợp lệ.
  Kỳ vọng REVIEW_PENDING theo policy server.
~~~

Xác nhận Request B không tạo PAYMENT_REQUESTED hoặc payment operation để chi trả trước review. Đây là ca phát hiện việc handler vô tình mặc định “không cần review” khi flag không được gửi.

### 13.6. Kiểm thử stale form và cạnh tranh

Dùng hai transaction/kết nối hoặc request được điều phối:

1. A đọc cart revision 7 và quote Q7.
2. B thực hiện thay đổi hợp lệ để cart thành revision 8.
3. A confirm bằng dữ liệu cũ.
4. Thử cả trường hợp A tự sửa expected revision nhưng vẫn giữ quote cũ.

Không trường hợp nào được dùng Q7 cho nội dung ngoài binding của nó.

Nếu confirm và cart update chạy đồng thời, kết quả phải tương ứng với một thứ tự hợp lệ hoặc xung đột được phát hiện. Không được có checkout chứa số lượng mới nhưng giá/xác nhận thuộc nội dung cũ.

### 13.7. Kiểm thử rollback tại ranh giới bắt buộc

Gây lỗi có kiểm soát sau khi tạo checkout nhưng trước khi transaction hoàn tất, ví dụ insert outbox bắt buộc.

Sau đó kiểm tra checkout, cart state, quote consumption, operation, receipt và quota cục bộ cùng rollback theo hợp đồng.

Test trên cơ chế lưu trữ thật phù hợp mới phát hiện việc commit riêng lẻ hoặc ghi ngoài transaction. Chỉ mock một helper validateHiddenFields không chứng minh toàn bộ hành vi.

## 14. Tình huống thực hành: token đúng nhưng nghiệp vụ sai

Một tài khoản A được phép mua hàng và có CSRF token hợp lệ. Cart hiện tại thuộc chính A, quote còn hiệu lực, nhưng policy yêu cầu review trước khi chi trả.

UI gửi các hidden field cũ:

~~~text
unitPriceMinor = giá hiển thị
requiresApproval = true
isPaid = false
~~~

A tự dựng request với:

~~~text
unitPriceMinor = 1
requiresApproval = false
approvalDone = true
isPaid = true
~~~

Các điều sau có thể đồng thời đúng:

- A đã đăng nhập thật.
- Request có token chống CSRF hợp lệ.
- A sở hữu cart.
- Quote có tồn tại.
- Request vẫn không có thẩm quyền quyết định giá, review hoặc trạng thái thanh toán.

Backend phù hợp phải chặn các field không được nhận hoặc hoàn toàn không cho chúng tạo hiệu ứng theo hợp đồng. Với command hợp lệ, giá vẫn từ quote, review vẫn do policy và trạng thái thanh toán vẫn chờ bằng chứng.

Nếu A gọi trực tiếp endpoint bước sau, endpoint đó vẫn kiểm tra action, state và proof cần thiết. Việc đã đi qua một form hợp lệ không tạo quyền cho mọi bước tiếp theo.

### 14.1. Điều cần giải thích khi xử lý lỗi thực tế

Khi điều tra một giá trị sai, hãy nối:

~~~text
Client đã đề nghị gì?
Decoder thực sự nhận field nào?
Handler lấy dữ liệu có thẩm quyền từ đâu?
Policy dùng facts/revision nào?
Domain và worker thực hiện snapshot nào?
Những thay đổi nào đã commit?
~~~

Nếu backend vẫn lấy giá từ hidden field, chỉ thêm JavaScript kiểm tra hoặc khóa control mạnh hơn không giải quyết nguyên nhân.

## 15. Audit và phản hồi cho client

Có thể lưu actor, tenant, action, cart/quote/revision, policy version, operationId và kết quả command.

Nếu cần ghi nhận field trái hợp đồng, nên dùng tên field/reason code an toàn và thông tin giới hạn, không dump nguyên form có token hoặc dữ liệu thanh toán.

Requested amount hoặc client-declared status phải được phân biệt với giá/trạng thái có thẩm quyền. Một log total=1 lấy từ input không được làm báo cáo hiểu đó là giá đã được chấp nhận.

Response có thể yêu cầu tải lại quote hoặc xác nhận lại khi dữ liệu cũ. Không tiết lộ quote, quyền hoặc dữ liệu của actor/tenant khác để giải thích vì sao một ID không dùng được.

Thông báo “yêu cầu đã nhận” phải phân biệt với “đã thanh toán”. Cách đặt trạng thái trên UI cũng phải phản ánh đúng sự thật mà server đã xác nhận.

## 16. Khung rà soát hidden controls

Với mỗi field client gửi lại, hãy ghi rõ:

~~~text
Tên field và action sử dụng:
UI đang hiển thị/ẩn/khóa field ra sao:
Ý nghĩa thực sự: choice / reference / precondition / token / server decision:

Nguồn có thẩm quyền:
Caller được thay phần nào:
Kiểm tra type, scope, quan hệ và trạng thái:
Binding với actor, tenant, object và revision:
Thời hạn/thu hồi/replay nếu có:

Field thiếu, null, trùng hoặc ngoài hợp đồng được xử lý thế nào:
Cách backend tính/lấy lại giá trị:
Ảnh hưởng transaction và hiệu ứng ngoài:
Lỗi an toàn, audit và các test sửa request trực tiếp:
~~~

Đánh giá theo ý nghĩa của dữ liệu và điểm sử dụng, không chỉ theo tên input hay cách CSS hiển thị.

## 17. Câu hỏi tự kiểm tra

1. Vì sao hidden field do server render vẫn phải kiểm chứng khi nhận lại?
2. Một field disabled có thể được caller gửi thủ công theo cách nào về mặt giao thức?
3. CSRF token hợp lệ không chứng minh những điều nghiệp vụ nào?
4. Khi nào expectedTotal là input hợp lệ nhưng không phải nguồn giá?
5. Quote của bạn được ràng buộc với cart, revision, người dùng và lựa chọn nào?
6. Hidden step hoặc paid flag đang được đối chiếu với bằng chứng server nào?
7. Nếu một tab cũ gửi lại request, state/version/idempotency bảo vệ ra sao?
8. Các endpoint cũ, worker và công cụ nội bộ có còn tin những field mà UI đã ẩn không?
9. Test nào chứng minh request bị chặn không tạo job hoặc hiệu ứng tài chính trước khi trả lỗi?

Điểm cần giữ là **client có thể mang lựa chọn, tham chiếu và token, nhưng quyền và sự thật nghiệp vụ phải được server kiểm chứng theo đúng mục đích**. Ẩn hoặc khóa control không thay đổi ranh giới đó.
