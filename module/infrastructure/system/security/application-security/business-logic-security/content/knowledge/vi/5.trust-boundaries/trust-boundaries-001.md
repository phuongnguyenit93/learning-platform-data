# Ranh giới tin cậy từ trình duyệt đến ứng dụng — Browser to application boundary

## 1. Ranh giới xuất hiện khi một ý định trở thành yêu cầu gửi tới máy chủ

Trong chương **Trust Boundaries** của học phần **Business Logic Security**, một **ranh giới tin cậy** là nơi dữ liệu hoặc quyền đi qua giữa các thành phần có mức kiểm soát và giả định khác nhau.

Trình duyệt hiển thị sản phẩm, nhận lựa chọn và gửi yêu cầu. Ứng dụng phía máy chủ chịu trách nhiệm quyết định yêu cầu có được tạo tác động nghiệp vụ hay không. Khi request đi từ trình duyệt vào ứng dụng, dữ liệu do phía người dùng cung cấp phải được kiểm chứng trước khi trở thành căn cứ cho giá, quyền lợi, trạng thái hoặc quyền truy cập.

Điều này vẫn đúng khi:

- Người dùng đã đăng nhập.
- Trang được tải qua HTTPS.
- Giao diện do chính đội phát triển ứng dụng xây dựng.
- Request được gửi từ một nút bấm có kiểm tra dữ liệu.
- Giá trị nằm trong input ẩn, local storage hoặc một header do frontend tạo.
- API chỉ được gọi trong một trình tự màn hình được thiết kế sẵn.

Người dùng có thể gọi API bằng một client khác, sửa dữ liệu mà client kiểm soát, lặp lại hoặc thay đổi thứ tự thao tác. Vì vậy, trải nghiệm trên giao diện phải được chuyển thành điều kiện có thể thực thi tại máy chủ.

Sau bài này, bạn cần có khả năng:

- Chỉ ra những dữ kiện đi qua ranh giới trình duyệt–ứng dụng và mức thẩm quyền của chúng.
- Phân biệt kiểm tra cú pháp, xác thực, phân quyền, quy tắc nghiệp vụ và cơ chế nhất quán.
- Ngăn client tự đặt giá, chọn chủ thể, bỏ qua phê duyệt hoặc quyết định trạng thái.
- Thiết kế command, báo giá và quy trình checkout có ràng buộc rõ ràng.
- Kiểm thử trực tiếp tại API, bao gồm retry và request chạy đồng thời.

## 2. Máy chủ nhận đề nghị; thẩm quyền phụ thuộc từng trường dữ liệu

Có thể nhìn luồng cơ bản như sau:

~~~mermaid
flowchart LR
    subgraph CLIENT[Phía khách hàng]
        UI[Giao diện và JavaScript]
        STORE[Dữ liệu lưu phía client]
        REQUEST[Request được tạo]
        UI --> REQUEST
        STORE --> REQUEST
    end
    subgraph APP[Phía ứng dụng có thẩm quyền]
        ENTRY[Tiếp nhận và xác thực]
        AUTHZ[Kiểm tra actor và đối tượng]
        RULES[Đánh giá quy tắc nghiệp vụ]
        COMMIT[Ghi nhận nhất quán]
        ENTRY --> AUTHZ
        AUTHZ --> RULES
        RULES --> COMMIT
    end
    REQUEST -->|Ranh giới tin cậy| ENTRY
~~~

Máy chủ không phải từ chối mọi giá trị từ client. Khách cần chọn sản phẩm, nhập địa chỉ và đề nghị số lượng. Vấn đề là **một trường được dùng như lựa chọn hay được coi là sự thật có thẩm quyền**.

| Dữ liệu nhận từ trình duyệt | Có thể mang ý nghĩa gì? | Điều máy chủ cần xác định |
| --- | --- | --- |
| Mã sản phẩm | Đề nghị mua sản phẩm đó | Sản phẩm có tồn tại, được bán trong tenant và đủ điều kiện không? |
| Số lượng | Số lượng khách muốn mua | Có dương, trong giới hạn và còn đủ khả năng cấp không? |
| Mã ưu đãi | Đề nghị áp dụng chương trình | Có đúng chủ thể, thời hạn, phạm vi và hạn mức không? |
| Địa chỉ nhận hàng | Lựa chọn hoặc dữ liệu người dùng nhập | Người gọi có quyền dùng địa chỉ đã lưu, và điều kiện giao hàng là gì? |
| Tổng tiền | Giá trị frontend hiển thị hoặc dự kiến | Tổng có thẩm quyền được tính hoặc chốt ở đâu? |
| Mã đơn, hồ sơ hoặc payment | Đối tượng người dùng muốn thao tác | Có đúng tenant, quan hệ và hành động được phép không? |
| Trạng thái mong muốn | Ý định thực hiện một bước | Có chuyển trạng thái hợp lệ và đủ điều kiện không? |
| Thời gian phía client | Thông tin phục vụ tương tác | Thời gian có thẩm quyền để xét hạn là thời gian nào? |
| Khóa idempotency | Nhận diện ý định gửi lại theo hợp đồng API | Phạm vi, fingerprint và ràng buộc nghiệp vụ tương ứng là gì? |

Một request có JSON hợp lệ không chứng minh các giá trị có ý nghĩa đúng. Một request do chính người dùng chủ động gửi cũng không chứng minh họ có quyền tạo mọi kết quả được mô tả trong đó.

### 2.1. HTTPS bảo vệ đường truyền trong phạm vi của nó

HTTPS giúp bảo vệ việc truyền dữ liệu và xác thực đầu bên kia theo cơ chế TLS. Người dùng vẫn kiểm soát các lựa chọn và dữ liệu mà client của họ gửi.

Nếu client gửi `unitPrice=1` qua một kết nối HTTPS hợp lệ, kết nối được bảo vệ không biến số 1 thành giá bán được doanh nghiệp chấp nhận. Ứng dụng vẫn phải tính hoặc kiểm chứng giá từ nguồn có thẩm quyền.

### 2.2. Token và cookie cần được diễn giải sau khi xác minh

Một cookie hoặc token do máy chủ phát có thể chứa thông tin được bảo vệ. Máy chủ cần xác minh tính hợp lệ, ngữ cảnh, thời hạn và các điều kiện tương ứng trước khi dùng thông tin đó.

Không nên coi mọi byte đi từ trình duyệt là có thể sửa mà vẫn hợp lệ về mật mã. Ngược lại, cũng không coi một token hợp lệ là giấy phép cho mọi nghiệp vụ:

- Token có thể bị dùng lại trong phạm vi không phù hợp nếu ứng dụng bỏ kiểm tra đối tượng.
- Quyền hoặc quan hệ có thể đã thay đổi theo chính sách hiện hành.
- Token xác thực danh tính không tự xác nhận giá, ngân sách hoặc trạng thái đơn.
- Dữ liệu đã ký vẫn cần đúng chủ thể, tenant, mục đích và điều kiện sử dụng.

Tính hợp lệ của một bằng chứng chỉ có ý nghĩa trong phạm vi bằng chứng đó thực sự chứng minh.

## 3. Những gì giao diện không thể bảo đảm thay cho máy chủ

### 3.1. Ẩn, khóa hoặc vô hiệu hóa điều khiển

Ẩn nút “duyệt”, đặt input chỉ đọc hoặc vô hiệu hóa nút thanh toán giúp hướng dẫn tương tác. Một caller vẫn có thể gửi yêu cầu đến endpoint nếu biết giao thức.

Ví dụ, nút hủy đơn biến mất sau khi bắt đầu giao không bảo đảm endpoint hủy đã kiểm tra trạng thái. Điều kiện phải có trong thao tác nghiệp vụ phía máy chủ.

Không đưa bí mật, hạn mức đặc quyền hoặc credential dùng chung vào JavaScript rồi dựa vào việc người dùng ít khi đọc mã để bảo vệ chúng.

### 3.2. Kiểm tra dữ liệu chỉ ở frontend

Frontend có thể ngăn số lượng âm hoặc hiển thị lỗi sớm. Máy chủ vẫn cần kiểm tra kiểu dữ liệu, miền giá trị, độ dài và các quy tắc liên quan.

Ngoài ra, “số lượng dương” chưa đủ. Số lượng có thể vượt hạn mức của sản phẩm, ngân sách khuyến mãi hoặc lượng còn được trả từ giao dịch gốc.

Các lựa chọn hợp lệ trên giao diện thường là kết quả chụp tại một thời điểm. Khi người dùng gửi yêu cầu, sản phẩm, trạng thái hoặc quyền có thể đã đổi.

### 3.3. Trình tự màn hình

Một wizard có các bước:

~~~text
Nhập thông tin -> Kiểm tra -> Xác nhận -> Thực hiện
~~~

Nếu endpoint thực hiện chỉ cần `confirmed=true`, người gọi có thể bỏ qua mọi bước trước đó.

Máy chủ phải biết bước kiểm tra đã tạo quyết định gì, cho đối tượng và nội dung nào, còn hiệu lực không. Khi dữ liệu quan trọng đổi sau phê duyệt, quyết định cũ không được tự áp dụng cho nội dung mới.

### 3.4. Dữ liệu lưu phía trình duyệt

Local storage, session storage, state của ứng dụng và dữ liệu form có thể được dùng cho trải nghiệm. Chúng không tự trở thành nguồn quyết định số dư, quyền sở hữu hoặc trạng thái đã thanh toán.

Kể cả dữ liệu ban đầu do máy chủ gửi, khi được client gửi lại cần có cơ chế xác minh hoặc đối chiếu phù hợp. Không thể suy ra “máy chủ từng phát giá trị này” chỉ từ việc một trường trông giống phản hồi cũ.

Một trường có chữ ký hoặc token báo giá có thể giúp ràng buộc nội dung, nhưng cần thiết kế phạm vi và chống sử dụng lại; phần sau sẽ phân tích.

## 4. Ví dụ xuyên suốt: checkout với dữ liệu do client lựa chọn

Xét giỏ CART-42 của khách C42 trong tenant T1:

| Thành phần | Giá trị do máy chủ xác định |
| --- | ---: |
| Sản phẩm P1, giá 250.000 đồng, số lượng 2 | 500.000 VND |
| Giảm giá đủ điều kiện | -50.000 VND |
| Phí giao theo điều kiện đã chốt | +30.000 VND |
| Tổng cần thanh toán | 480.000 VND |

Một request nguy hiểm nếu ứng dụng tin trực tiếp các trường sau:

~~~json
{
  "cartId": "CART-42",
  "customerId": "C99",
  "unitPrice": 1,
  "discountAmount": 500000,
  "totalAmount": 2,
  "paymentStatus": "PAID",
  "approved": true
}
~~~

Các trường này thể hiện nhiều loại vượt ranh giới:

- Chọn khách hàng khác thay vì dùng ngữ cảnh đã xác minh.
- Chọn giá và quyền giảm giá.
- Tự kết luận đã thanh toán.
- Tự cấp một quyết định phê duyệt.

Không phải mọi API có trường tiền đều sai. Một API thanh toán có thể nhận số tiền dự kiến để so sánh hoặc một API nhân viên có thể cho đề nghị điều chỉnh. Điều quan trọng là máy chủ phải kiểm tra đúng thẩm quyền và không lấy số đó làm quyết định cuối cùng chỉ vì request có định dạng hợp lệ.

### 4.1. Command theo ý định của khách hàng

Một command checkout có thể là:

~~~json
{
  "cartId": "CART-42",
  "expectedCartRevision": 8,
  "quoteId": "Q9",
  "shippingAddressId": "ADDR-7",
  "idempotencyKey": "one-key-for-this-checkout-intent"
}
~~~

Trong đó:

- Actor và tenant có hiệu lực đến từ ngữ cảnh xác thực cùng quan hệ đã kiểm chứng.
- `quoteId` tham chiếu báo giá do máy chủ phát.
- Địa chỉ phải có quan hệ được phép sử dụng và khớp điều kiện báo giá.
- Revision là điều kiện để phát hiện giỏ đã thay đổi.
- Khóa idempotency hỗ trợ nhận diện gửi lại, không cấp quyền thanh toán.

Máy chủ có thể chọn tính lại toàn bộ giá tại checkout thay vì phát báo giá trước. Cả hai thiết kế đều cần chính sách rõ về thời điểm chốt giá, thay đổi điều kiện và phản hồi khi giá không còn phù hợp.

## 5. Các lớp kiểm tra cần có tại điểm tiếp nhận

Một luồng xử lý có thể tổ chức theo các lớp sau. Thứ tự chi tiết tùy kiến trúc, nhưng không được bỏ lớp cần thiết chỉ vì lớp khác đã thành công.

| Lớp | Câu hỏi cần trả lời | Ví dụ lỗi nếu bỏ qua |
| --- | --- | --- |
| Cấu trúc và miền giá trị | Request có đúng schema, giới hạn kích thước và kiểu giá trị không? | Số lượng âm, chuỗi quá dài hoặc số gây tràn |
| Xác thực | Người gọi là ai theo bằng chứng được chấp nhận? | Giả danh bằng header tự khai |
| Ngữ cảnh actor | Người gọi đang hoạt động trong tenant và hồ sơ khách hàng nào? | Chọn tenant hoặc chủ thể không có quan hệ |
| Quyền theo đối tượng | Có được thực hiện hành động trên đối tượng cụ thể không? | Xem hoặc checkout giỏ của người khác |
| Quan hệ giữa đối tượng | Các ID có cùng một tổ hợp nghiệp vụ hợp lệ không? | Dùng báo giá của giỏ khác hoặc địa chỉ ngoài quyền |
| Quy tắc và trạng thái | Giá trị, quyền lợi và bước hiện tại có cho phép hành động không? | Dùng mã hết hạn hoặc bỏ qua phê duyệt |
| Nhất quán khi ghi | Điều kiện còn đúng dưới cạnh tranh và retry không? | Hai đơn cùng tiêu thụ một ưu đãi một lần |
| Phản hồi | Kết quả có mô tả đúng tác động đã hoàn tất không? | Báo đã trả tiền khi mới tạo lệnh thanh toán |

### 5.1. Validation cần đúng kiểu nghiệp vụ

Với số tiền, cần tiền tệ và đơn vị rõ ràng, dùng số nguyên theo đơn vị nhỏ nhất hoặc số thập phân chính xác theo chính sách. Không dùng số dấu phẩy động để quyết định tiền.

Với số lượng, ngoài giá trị dương còn có giới hạn theo sản phẩm, đơn, chủ thể hoặc tồn kho. Với ID, đúng định dạng chỉ giúp tiếp nhận; quyền truy cập vẫn phải được kiểm tra.

Với thuộc tính có nhiều cách biểu diễn, cần chuẩn hóa nhất quán trước khi đánh giá và tạo fingerprint. Tránh để các lớp diễn giải khác nhau về số thập phân, giá trị rỗng, trường trùng lặp hoặc kiểu dữ liệu.

Giới hạn kích thước request và chi phí xử lý cũng có ý nghĩa nghiệp vụ: một request chứa hàng nghìn dòng hàng có thể hợp lệ về JSON nhưng vượt khả năng hoặc chính sách xử lý.

### 5.2. Tránh cập nhật entity trực tiếp từ request

Nếu bind toàn bộ body vào entity đơn hàng, client có thể vô tình hoặc cố ý gửi thêm trường đặc quyền. Đây thường được mô tả là rủi ro gán thuộc tính vượt phạm vi dự kiến.

Command theo hành động giúp giới hạn bề mặt đầu vào. Cần cấu hình cách xử lý trường không hỗ trợ một cách chủ động: từ chối hoặc bỏ qua theo hợp đồng, đồng thời bảo đảm chúng không đi qua một đường ánh xạ khác rồi được ghi vào entity.

Danh sách trường cho phép không tự bảo đảm đúng nghiệp vụ. Chẳng hạn, `shippingAddressId` là trường hợp lệ nhưng vẫn phải đúng chủ thể và điều kiện giao hàng.

### 5.3. Header cũng cần nguồn tin cậy

Ứng dụng không được tin một header như `X-User-Id` chỉ vì tên của nó có vẻ nội bộ. Nếu một gateway xác thực rồi gắn danh tính cho backend, cần bảo vệ đường đi giữa chúng, xử lý header do client tự gửi và ngăn đường truy cập bỏ qua gateway.

Tương tự, header tenant chỉ là lựa chọn đầu vào cho đến khi quan hệ thành viên được kiểm tra. Thông tin địa chỉ mạng qua proxy cũng chỉ có ý nghĩa trong mô hình proxy được cấu hình tin cậy, không tự chứng minh danh tính hay quyền sở hữu.

Một ranh giới có nhiều hop phải xác định rõ thành phần nào được phát từng dữ kiện và backend dùng bằng chứng gì để tin thành phần đó.

## 6. Báo giá do máy chủ phát: ràng buộc nội dung và phạm vi

Báo giá là một cách chốt các điều kiện giao dịch để khách xem và xác nhận. Trong ví dụ, Q9 có thể chứa hoặc tham chiếu:

~~~text
quoteId: Q9
tenant: T1
customer: C42
cartId: CART-42
cartContentRevision: 8
shippingAddressId: ADDR-7
shippingAddressRevision: 3
currency: VND
itemsSubtotal: 500000
discount: 50000
shippingFee: 30000
total: 480000
pricingPolicyVersion: một phiên bản xác định
validUntil: thời điểm theo chính sách máy chủ
usage: một lần checkout trong phạm vi đã định
~~~

Đây là dữ liệu có thẩm quyền được lưu hoặc bảo vệ theo thiết kế. Trình duyệt có thể hiển thị nó, nhưng không được tùy ý thay nội dung rồi yêu cầu máy chủ coi đó là Q9.

### 6.1. Báo giá phải khớp đối tượng hiện tại

Khi checkout, cần kiểm tra:

- Đúng tenant và khách hàng hoặc quan hệ được phép.
- Đúng giỏ và phiên bản nội dung có ảnh hưởng giá.
- Đúng địa chỉ hoặc snapshot điều kiện giao liên quan.
- Cùng tiền tệ và các điều kiện sản phẩm.
- Còn hiệu lực theo thời điểm đánh giá được quy định.
- Chưa bị thu hồi hoặc sử dụng ngoài phạm vi cho phép.

Nếu đổi số lượng, sản phẩm, điều kiện giao hoặc ưu đãi, báo giá cũ có thể không còn áp dụng. Chính sách phải xác định trường thay đổi nào yêu cầu báo giá mới.

Nếu giá thị trường thay đổi sau khi phát, hệ thống có thể công nhận báo giá trong hạn hoặc yêu cầu tính lại theo chính sách đã công bố. Không để kết quả phụ thuộc ngẫu nhiên vào việc một service đọc cache giá cũ hay mới.

### 6.2. Báo giá không tự giữ mọi tài nguyên

Giữ giá không đồng nghĩa đã giữ tồn kho hoặc lượt dùng mã. Nếu báo giá không bao gồm việc giữ các quyền lợi đó, checkout phải giành chúng nguyên tử tại nơi có thẩm quyền.

Nếu có khoản giữ hoặc token đặt chỗ, cần kiểm tra nó thuộc đúng giao dịch, còn hiệu lực và chưa được sử dụng vượt giới hạn. Không cộng thêm quyền lợi chỉ vì khách gửi lại một token cũ còn đọc được.

### 6.3. Báo giá ký hoặc token chỉ giải quyết một phần

Có thể dùng dữ liệu đã ký hoặc MAC thay cho một phần tra cứu trạng thái. Khóa bí mật phải thuộc ranh giới được kiểm soát của máy chủ; đưa khóa dùng chung vào frontend sẽ làm mất ý nghĩa bảo vệ.

Bên nhận cần xác minh nội dung và phạm vi: chủ thể, tenant, giỏ, phiên bản, tiền tệ, thời hạn và mục đích sử dụng. Hash thuần túy của JSON do client tự tạo không chứng minh đó là báo giá máy chủ đã phát.

Một token hợp lệ vẫn có thể bị gửi lại. Cần trạng thái tiêu thụ, tính duy nhất hoặc ngân sách phù hợp nếu token cấp một quyền lợi có giới hạn. Chữ ký không tự giữ được tồn kho và không thay thế idempotency.

## 7. Minh họa Java: checkout qua một command có giới hạn

Đoạn mã sau là **mã khung kiến trúc**, chưa phải ứng dụng chạy độc lập. Nó minh họa mô hình các dữ liệu liên quan cùng tham gia transaction cục bộ. Nếu tồn kho hoặc ưu đãi nằm ở dịch vụ khác, cần giao thức giữ và xác nhận riêng, không được giả định transaction này bao trùm lời gọi mạng.

~~~java
record CheckoutCommand(
        String cartId,
        long expectedCartRevision,
        String quoteId,
        String shippingAddressId,
        String idempotencyKey) {}

record CheckoutReceipt(
        String orderId,
        String status) {}

public CheckoutReceipt checkout(
        CustomerActor actor,
        CheckoutCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var cart = carts.lockByTenantAndCustomer(
                actor.tenantId(),
                actor.customerId(),
                command.cartId());

        permissions.requireCurrentCheckoutCapability(actor, cart);

        var scope = new IdempotencyScope(
                actor.tenantId(),
                actor.subjectId(),
                actor.customerId(),
                "CHECKOUT");

        var fingerprint = fingerprints.forCheckout(command);
        var replay = idempotency.claimOrReplay(
                scope, command.idempotencyKey(), fingerprint);

        if (replay.isPresent()) {
            return replay.get();
        }

        cart.requireOpen();
        cart.requireContentRevision(command.expectedCartRevision());

        var quote = quotes.lockIssuedQuote(
                actor.tenantId(), command.quoteId());
        var address = addresses.lockUsableCustomerAddress(
                actor, command.shippingAddressId());

        quote.requireUsableFor(
                actor, cart, address, serverClock.instant());

        benefits.reserveForCheckout(actor, cart, quote);
        inventory.reserveAllForCheckout(cart, quote);

        var order = orders.createUniqueForCheckout(
                cart.checkoutCycleId(),
                actor.customerId(),
                quote.amounts(),
                address.snapshot());

        quote.markConsumedBy(order.id());
        cart.markCheckedOut(order.id());
        quotes.save(quote);
        carts.save(cart);
        outbox.appendOrderAwaitingPayment(order.id());

        var result = new CheckoutReceipt(
                order.id(), "AWAITING_PAYMENT");

        idempotency.complete(scope, command.idempotencyKey(), result);
        return result;
    });
}
~~~

Các hợp đồng quan trọng của mã khung:

1. `CustomerActor` được tạo từ cơ chế xác thực và quan hệ đã kiểm chứng. Không nhận trực tiếp từ JSON.
2. Repository giỏ giới hạn tenant, khách hàng và khóa đúng dữ liệu. Mọi đường sửa giỏ phải dùng cơ chế cạnh tranh tương thích.
3. Kiểm tra quyền trước replay bảo đảm actor được đọc kết quả. Điều kiện tạo checkout mới, như giỏ đang mở, được kiểm tra sau replay để lần gửi lại không thất bại chỉ vì lần đầu đã đóng giỏ.
4. `claimOrReplay` dùng lưu trữ có ràng buộc duy nhất, kiểm tra fingerprint và xử lý cạnh tranh. Khóa request không bao gồm quyền tùy ý đọc kết quả của người khác.
5. `requireUsableFor` so khớp báo giá với actor, giỏ, nội dung và địa chỉ có hiệu lực. Snapshot địa chỉ dùng cho đơn không được thay đổi sau đó chỉ vì hồ sơ địa chỉ được cập nhật.
6. Giữ ưu đãi và tồn kho là thao tác nguyên tử trên ngân sách hoặc lượng dùng chung. Thất bại ở bất kỳ bước nào phải rollback các thay đổi cục bộ liên quan.
7. `checkoutCycleId` là định danh nghiệp vụ ổn định cho một lần checkout của giỏ. Nó cùng các ràng buộc trạng thái và duy nhất ngăn khóa request mới tạo thêm đơn từ cùng quyền checkout.
8. Tiền trong `quote.amounts()` do máy chủ chốt với đơn vị và cách làm tròn rõ ràng; không được thay bằng tổng tiền client gửi.
9. Đơn, khoản giữ, trạng thái tiêu thụ báo giá, outbox và kết quả idempotency cùng commit hoặc rollback trong mô hình này.
10. Kết quả `AWAITING_PAYMENT` chỉ xác nhận tạo đơn chờ thanh toán. Nó không xác nhận tiền đã được thu.

Nếu hai request tạo cùng bản ghi idempotency gây xung đột làm transaction bị hủy, tầng điều phối cần kết thúc transaction đó trước khi đọc lại hoặc retry. Không tiếp tục dùng một transaction đã thất bại.

Mã khung chưa triển khai khởi tạo thanh toán, xử lý kết quả hay giải phóng khoản giữ. Các luồng đó phải bảo vệ trạng thái và chống tác động trùng theo hợp đồng của chúng.

## 8. Cạnh tranh và retry đều vượt qua những gì giao diện nhìn thấy

### 8.1. Vô hiệu hóa nút bấm không ngăn request song song

Người dùng có thể mở hai tab, client có thể retry do mất phản hồi hoặc hai thiết bị có thể gửi gần nhau. Một tác vụ khác cũng có thể sửa giỏ hoặc tiêu thụ ưu đãi trong lúc checkout.

Do đó, kiểm tra và giành quyền thay đổi phải gắn với cơ chế nhất quán. Chỉ bọc mã trong transaction mặc định chưa chứng minh mọi invariant được giữ nếu các transaction vẫn đọc cùng trạng thái cũ.

Với khóa nhiều bản ghi, cần thứ tự khóa thống nhất để giảm deadlock. Nếu dùng optimistic locking hoặc isolation có thể báo xung đột, retry có giới hạn phải giữ nguyên ý nghĩa và không tạo thêm tác động.

### 8.2. Idempotency cần phạm vi và fingerprint

Cùng khóa, phạm vi và nội dung: trả kết quả đã lưu hoặc trạng thái đang xử lý theo hợp đồng.

Cùng khóa nhưng khác giỏ, báo giá hoặc địa chỉ có ý nghĩa nghiệp vụ: xử lý xung đột, không âm thầm trả kết quả cũ cho nội dung mới.

Đổi khóa không cấp thêm tồn kho, lượt ưu đãi hoặc quyền checkout. Cần tính duy nhất nghiệp vụ và ngân sách tổng bên cạnh idempotency.

Nếu kết quả được cache ở một tầng gần trình duyệt hoặc gateway, khóa và chính sách cache phải tránh trả dữ liệu của actor khác. Cache idempotency ngắn hạn cũng không thay thế ràng buộc tồn tại lâu hơn ở nơi tạo quyền lợi.

## 9. Kết quả thanh toán đi qua trình duyệt cần được kiểm chứng

Sau khi khách thanh toán ở bên ngoài, trình duyệt có thể quay về ứng dụng với một URL chứa mã giao dịch hoặc trạng thái hiển thị.

Không cập nhật `PAID` chỉ vì nhận:

~~~text
/checkout/return?orderId=O810&status=success
~~~

Ứng dụng cần một kết quả có thẩm quyền theo hợp đồng thanh toán: phản hồi đã xác minh, sự kiện đã kiểm tra hoặc truy vấn trạng thái thích hợp. Đồng thời đối chiếu đúng đơn, bên nhận, số tiền, tiền tệ và tác động đã ghi nhận.

Một callback được xác thực đúng nhưng mang dữ liệu không khớp giao dịch vẫn không được tự động hoàn tất đơn. Một sự kiện đến trùng cũng không được cộng tiền hoặc giao hàng hai lần.

Trang quay về có thể hiển thị “đang xác minh” và gọi API đọc trạng thái do máy chủ quản lý. Trạng thái trên giao diện nên phản ánh điều hệ thống biết, không tự tạo sự thật tài chính.

Nếu nhà cung cấp đã thực hiện nhưng ứng dụng mất phản hồi, giữ mã lệnh ổn định và đối soát theo hợp đồng. Transaction cục bộ không thu hồi được tác động đã xảy ra bên ngoài chỉ bằng rollback.

## 10. Các cơ chế bảo vệ trình duyệt giải quyết những lớp khác nhau

Các cơ chế kỹ thuật ở tầng web rất cần thiết, nhưng mỗi cơ chế có phạm vi riêng.

| Cơ chế | Phần giúp bảo vệ | Điều vẫn phải kiểm tra ở nghiệp vụ |
| --- | --- | --- |
| HTTPS | Đường truyền và xác thực đầu bên kia trong mô hình TLS | Giá, quyền, trạng thái, ngân sách |
| Xác thực phiên hoặc token | Danh tính theo cơ chế đã chọn | Quyền trên từng đối tượng và hành động |
| CORS | Quy tắc truy cập tài nguyên giữa các origin trong trình duyệt | Caller ngoài trình duyệt và quyền nghiệp vụ |
| Chống CSRF | Hạn chế yêu cầu giả mạo dựa vào credential tự động được gửi | Request do chính người dùng chủ động tạo để lạm dụng |
| Giảm thiểu XSS | Hạn chế mã không mong muốn chạy trong ngữ cảnh trang | Invariant phía máy chủ với mọi request hợp lệ về xác thực |
| Validation đầu vào | Cấu trúc, miền giá trị và giới hạn đã khai báo | Quan hệ đối tượng, tổng quyền lợi và cạnh tranh |

### 10.1. CORS không phải danh sách người được thực hiện nghiệp vụ

CORS được trình duyệt thực thi theo mô hình origin. Nó không ngăn một client ngoài trình duyệt gọi API và không thay thế xác thực hoặc phân quyền.

Một số loại request có thể được gửi dù script không được phép đọc response. Vì vậy, cấu hình CORS không nên được coi là bảo vệ duy nhất cho thao tác dùng cookie phiên.

Header `Origin` có thể hữu ích trong một chính sách kiểm tra nguồn yêu cầu. Nó vẫn không tự chứng minh người gọi sở hữu giỏ hàng hoặc được đặt giá giao dịch. Client ngoài trình duyệt không chịu cùng cơ chế thực thi origin như trình duyệt.

### 10.2. CSRF và lạm dụng bởi chủ tài khoản là hai tình huống khác nhau

Nếu credential được trình duyệt gửi tự động, một trang khác có thể tìm cách khiến trình duyệt phát yêu cầu không mong muốn. Ứng dụng cần cơ chế chống CSRF phù hợp, như token và kiểm tra nguồn theo kiến trúc, cùng cấu hình cookie tương ứng.

Không dùng request đọc như GET để tạo tác động nghiệp vụ trái với ngữ nghĩa của nó. Cấu hình thuộc tính cookie cần xét cách ứng dụng hoạt động giữa các site; không suy ra một cấu hình đơn lẻ đã giải quyết mọi tình huống.

Ngay cả khi request vượt qua kiểm tra CSRF đúng cách, chính khách hàng vẫn có thể gửi giá sai hoặc yêu cầu lặp. Cần các kiểm tra quyền, giá, trạng thái và tính duy nhất như các phần trước.

### 10.3. XSS ảnh hưởng ranh giới nhưng không phải lý do bỏ kiểm tra máy chủ

Mã chạy trong ngữ cảnh trang có thể thao tác theo quyền mà trang và phiên hiện có cho phép. Giảm thiểu XSS bảo vệ người dùng và ngữ cảnh trình duyệt.

Các kiểm tra phía máy chủ vẫn cần để giới hạn tác động theo nghiệp vụ: mã chạy được trên trang không được tự biến thành quyền duyệt hoàn tiền hoặc quyền chọn giá. Một ứng dụng cũng không nên coi mọi request cùng origin là một quyết định nghiệp vụ đã được phê duyệt.

## 11. Response quay lại trình duyệt cũng cần đúng ý nghĩa

### 11.1. Dữ liệu hỗ trợ giao diện chỉ là thông tin tại thời điểm trả về

Response có thể chứa:

~~~json
{
  "orderId": "O810",
  "state": "CONFIRMED",
  "canRequestCancellation": true
}
~~~

Frontend dùng thông tin để hiển thị nút hủy. Khi request hủy đến, máy chủ vẫn phải kiểm tra quyền và trạng thái hiện tại. Một worker có thể đã bắt đầu giao sau lúc response được tạo.

Không để client gửi ngược `canRequestCancellation=true` rồi coi đó là bằng chứng. Nếu thực sự muốn cấp một quyền dùng sau, cần một cơ chế quyết định có ràng buộc, thời hạn và cách tiêu thụ rõ ràng.

### 11.2. Chỉ trả dữ liệu trong phạm vi được phép

Response phục vụ khách hàng không nên vô tình kèm credential tích hợp, dữ liệu khách hàng khác hoặc thuộc tính quản trị vì dùng chung entity serialization.

Endpoint danh sách, tìm kiếm, file tải và API đọc trạng thái đều cần cùng phạm vi quyền phù hợp. Chỉ bảo vệ checkout mà để endpoint đọc trả báo giá của mọi người vẫn gây mất dữ liệu và có thể hỗ trợ lạm dụng.

Thông báo lỗi cần hữu ích nhưng không tiết lộ chi tiết đối tượng ngoài quyền. Dấu vết nội bộ có thể ghi lý do cụ thể hơn dưới cơ chế truy cập riêng.

### 11.3. Cache phải giữ ranh giới actor

Một response cá nhân hóa được cache không đúng phạm vi có thể trả dữ liệu cho người khác. Khóa và chính sách cache cần phản ánh tenant, actor hoặc các điều kiện làm response khác nhau theo thiết kế.

Nếu dùng cache kết quả quyền hoặc trạng thái, phải biết độ cũ được chấp nhận. Bản sao hiển thị không nên tự trở thành nguồn quyết định cho một thao tác tài chính cần dữ liệu hiện hành.

## 12. Kiểm thử trực tiếp tại ranh giới trình duyệt–ứng dụng

Thực hiện trong môi trường và phạm vi kiểm thử được cho phép. Cần gọi API trực tiếp, không chỉ thao tác qua những đường mà giao diện đang mở.

| Tình huống | Thao tác kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Sửa giá | Gửi tổng tiền, đơn giá hoặc giảm giá do client chọn | Máy chủ không dùng chúng để mở rộng quyền lợi |
| Sửa chủ thể | Thêm hoặc thay `customerId`, tenant, vai trò | Context có thẩm quyền không bị thay thế |
| ID của người khác | Dùng giỏ, đơn, báo giá hoặc địa chỉ ngoài quyền | Không có tác động hoặc dữ liệu trái quyền |
| Ghép sai quan hệ | Báo giá của giỏ A đi với giỏ B, hoặc địa chỉ khác điều kiện | Binding bị phát hiện không khớp |
| Bỏ qua bước | Gọi endpoint cuối khi chưa có quyết định cần thiết | Không chuyển trạng thái trái quy trình |
| Trạng thái tự khai | Gửi `PAID`, `approved=true` hoặc cờ hoàn tất | Không tạo trạng thái có thẩm quyền từ client |
| Sửa sau báo giá | Đổi số lượng hoặc địa chỉ rồi dùng Q9 cũ | Áp dụng đúng chính sách yêu cầu báo giá lại |
| Hết hạn hoặc dùng lại báo giá | Gửi token hoặc quote hợp lệ về cấu trúc nhưng mất hiệu lực | Không dùng ngoài phạm vi |
| Giá trị biên | Số lượng âm, cực lớn, số tiền sai scale hoặc gây tràn | Không tạo tác động hoặc tính toán sai |
| Request trùng | Gửi lại cùng khóa và nội dung sau mất phản hồi | Không nhân đơn, khoản giữ hoặc lệnh tiền |
| Cùng khóa khác nội dung | Đổi quote hoặc địa chỉ trong cùng phạm vi khóa | Xử lý xung đột theo hợp đồng |
| Khóa mới | Gửi nhiều khóa cho cùng một lần checkout | Không mở rộng quyền checkout hoặc lượt ưu đãi |
| Cạnh tranh tài nguyên | Hai checkout dùng chung lượng tồn hoặc ưu đãi cuối | Chỉ chấp nhận trong ngân sách hợp lệ |
| Header giả | Tự gửi header danh tính hoặc bỏ qua gateway nếu có đường thử được phép | Backend không tin nguồn chưa được xác minh |
| Quay về từ thanh toán | Gọi URL success trước khi có kết quả có thẩm quyền | Không đánh dấu đã thu tiền |
| Đường API phụ | Gọi phiên bản cũ, batch hoặc endpoint khác cùng tác động | Invariant không bị bỏ qua |
| Quyền đã thay đổi | Giữ phiên hoặc response cũ sau khi mất quan hệ cần thiết | Áp dụng đúng chính sách hiệu lực |
| Giả mạo yêu cầu web | Kiểm thử CSRF theo cơ chế credential thực tế | Chặn nguồn yêu cầu không được phép mà vẫn giữ kiểm tra nghiệp vụ |

Với kiểm thử cạnh tranh, đồng bộ các luồng để chúng thật sự cùng tranh chấp. Hai lần gọi tuần tự không chứng minh được điều kiện nguyên tử. Mock repository không đủ kiểm chứng khóa, uniqueness hoặc rollback.

Sau mỗi tình huống, kiểm tra nhiều hơn mã HTTP:

- Có bao nhiêu đơn, quyết định và bản ghi outbox?
- Giỏ, báo giá, tồn kho và lượt ưu đãi đã đổi thế nào?
- Tổng tiền và snapshot địa chỉ trong đơn có đúng không?
- Actor và tenant được ghi nhận có khớp ngữ cảnh đã xác minh không?
- Có lệnh bên ngoài nào đã được phát, nhận trùng hoặc chưa rõ kết quả không?

Có thể bổ sung kiểm thử sinh chuỗi: sửa giỏ, lấy báo giá, đổi địa chỉ, checkout, retry, hết hạn, nhận callback. Sau mỗi transaction đã commit, các invariant về giá, quyền, trạng thái và tổng quyền lợi vẫn phải đúng.

Không cần bắt đầu bằng một payload khai thác phức tạp. Thường chỉ cần hỏi: “Nếu bỏ giao diện và gửi một yêu cầu khác về thứ tự, đối tượng hoặc giá trị, điều gì đang bảo đảm kết quả vẫn hợp lệ?”

## 13. Dấu vết để theo dõi việc dữ liệu được nâng thành quyết định

Một chuỗi tương quan hữu ích:

~~~text
requestId
  -> actor context reference
  -> cartId + cartContentRevision
  -> quoteId
  -> orderId
  -> paymentExecutionId
  -> externalTransactionId
~~~

Dấu vết cần thể hiện những gì client đề nghị và những gì máy chủ quyết định, nhưng không sao chép toàn bộ request nếu chứa dữ liệu nhạy cảm.

Có thể ghi mã lý do cho:

- Sai quan hệ hoặc tenant.
- Báo giá không khớp hoặc hết hạn.
- Giỏ thay đổi phiên bản.
- Ưu đãi hoặc tồn kho không còn đủ.
- Khóa idempotency xung đột.
- Chuyển trạng thái bị từ chối.
- Kết quả thanh toán không khớp hoặc đang chờ xác minh.

Không ghi credential, token đầy đủ, bí mật tích hợp hoặc thông tin thanh toán không cần thiết vào log. Nếu cần đối chiếu token báo giá, ưu tiên định danh hoặc tham chiếu phù hợp.

Các tín hiệu như nhiều lần thử ID ngoài quyền, nhiều khóa cho cùng giỏ hoặc nhiều callback không khớp hỗ trợ điều tra. Chúng không thay thế việc chặn invariant tại nơi ghi và không tự chứng minh gian lận.

## 14. Những cách sửa dễ để lại đường vượt ranh giới

| Cách sửa | Phần còn thiếu | Hướng hoàn thiện |
| --- | --- | --- |
| Đổi input giá thành hidden hoặc readonly | Giá vẫn do client gửi | Tính hoặc kiểm chứng giá ở máy chủ |
| Chỉ cho frontend hiển thị nút hợp lệ | Caller khác vẫn gọi được API | Thực thi quyền và state machine tại nghiệp vụ |
| Thêm validation số dương | Số dương vẫn có thể sai quyền hoặc sai tổng | Kiểm tra nguồn giá trị và invariant liên quan |
| Bật HTTPS rồi tin toàn bộ request | Đường truyền đúng không chứng minh nội dung được phép | Xác định thẩm quyền cho từng trường |
| Cấu hình CORS để chỉ có website nhà | Không bao phủ mọi caller hoặc CSRF | Xác thực, chống giả mạo yêu cầu và phân quyền đúng lớp |
| Ký báo giá rồi bỏ mọi trạng thái | Token vẫn có thể sai phạm vi hoặc bị dùng lại | Binding, hiệu lực, tiêu thụ và ngân sách |
| Dùng idempotency nhưng không có unique nghiệp vụ | Khóa mới có thể tạo thêm quyền lợi | Ràng buộc ổn định theo ý định và tài sản |
| Tin header từ mọi đường vào | Caller có thể giả nguồn danh tính | Bảo vệ hop tin cậy và chặn đường bỏ qua |
| Coi URL success là bằng chứng đã trả tiền | Trình duyệt có thể gọi hoặc phát lại URL | Xác minh kết quả có thẩm quyền và đối chiếu giao dịch |
| Kiểm tra ở một controller duy nhất | Đường cũ, job hoặc endpoint khác có thể bỏ qua | Giữ invariant tại ranh giới nghiệp vụ và dữ liệu |

## 15. Bài tập tự kiểm tra

### Bài 1: giá được máy chủ trả về trước đó

Frontend nhận giá 250.000 đồng, lưu trong state rồi gửi lại khi checkout. Backend chấp nhận vì “giá này vốn do backend trả”.

**Gợi ý trả lời:** request mới không tự chứng minh nguồn gốc hoặc hiệu lực của giá. Cần tính lại từ nguồn có thẩm quyền hoặc dùng một báo giá được bảo vệ, ràng buộc với đúng nội dung, chủ thể và thời hạn.

### Bài 2: báo giá đã ký nhưng bị gửi từ tài khoản khác

Một token báo giá có chữ ký hợp lệ chứa tổng tiền và thời hạn nhưng không ràng buộc khách hàng, giỏ hoặc phạm vi sử dụng. Người khác dùng token đó cho giỏ của mình.

**Gợi ý trả lời:** chữ ký chỉ bảo vệ nội dung được ký. Nội dung thiếu binding nên không chứng minh quyền áp dụng cho giao dịch mới. Cần xác định và kiểm tra đúng phạm vi, cùng điều kiện tiêu thụ và quyền lợi liên quan.

### Bài 3: CSRF đã đúng thì có cần tính lại giá không?

Một request có phiên hợp lệ và vượt kiểm tra CSRF, nhưng người dùng đã sửa tổng tiền trước khi gửi.

**Gợi ý trả lời:** có. Chống CSRF giải quyết việc một nguồn khác lợi dụng credential tự động được gửi; nó không ngăn chủ tài khoản cố ý gửi giá trị có lợi. Giá và quyền lợi vẫn phải do máy chủ xác định hoặc kiểm chứng.

### Bài 4: callback thành công hiển thị trong trình duyệt

Trang quay về có `status=success`. Backend tạo đơn `PAID` ngay, không truy vấn hoặc xác minh kết quả thanh toán.

**Gợi ý trả lời:** trạng thái phía trình duyệt chưa phải bằng chứng có thẩm quyền. Cần kiểm tra kết quả theo hợp đồng tích hợp, đối chiếu giao dịch và chống áp dụng trùng. Giao diện có thể hiển thị đang xác minh khi chưa có kết quả chắc chắn.

## 16. Các điểm cần ghi nhớ

Ranh giới trình duyệt–ứng dụng là nơi một đề nghị từ môi trường phía người dùng đi vào hệ thống có quyền tạo tác động. Mỗi dữ kiện phải được dùng đúng vai trò: lựa chọn của khách hàng, bằng chứng cần xác minh hoặc giá trị do máy chủ quyết định.

Một thiết kế có thể kiểm chứng cần xác thực actor, kiểm tra quyền và quan hệ đối tượng, ràng buộc giá hoặc phê duyệt với đúng nội dung, thực thi state machine và giữ invariant khi có cạnh tranh hoặc retry. Các cơ chế web và bảo vệ đường truyền hỗ trợ những lớp riêng của mô hình này.

Câu hỏi cốt lõi là: **Dữ liệu nào đang được nâng từ lời khai của client thành quyết định nghiệp vụ, và cơ chế nào chứng minh việc nâng thẩm quyền đó là hợp lệ?**
