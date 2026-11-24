# Quyền xem giá theo khách hàng — Customer price visibility

## 1. Giá khách hàng được xem là một quyết định phân quyền

Trong chương **Pricing Rules**, customer price visibility là việc quyết định **ai được xem loại giá nào, của khách hàng nào, cho sản phẩm và ngữ cảnh nào**. Với giá hợp đồng, giá đại lý hoặc giá thương lượng, một con số có thể là dữ liệu riêng của một tài khoản khách hàng chứ không phải thuộc tính công khai của sản phẩm.

Ví dụ giả định cùng một sản phẩm:

| Dữ liệu giá | Giá trị minh họa | Đối tượng có thể được xem |
| --- | ---: | --- |
| Giá niêm yết công khai | 1.000.000 VND | Người xem danh mục công khai |
| Giá hợp đồng của khách A | 850.000 VND | Người được cấp quyền xem giá trong tài khoản A |
| Giá hợp đồng của khách B | 750.000 VND | Người được cấp quyền tương ứng trong tài khoản B |
| Giá vốn nội bộ | 600.000 VND | Vai trò nội bộ được phép xem giá vốn |

Khách A biết mã sản phẩm không có nghĩa họ được xem giá của B. Một nhân viên có quyền hỗ trợ đơn hàng cũng không tự có quyền xem giá vốn hay toàn bộ bảng giá của mọi khách hàng.

Lỗi nghiệp vụ thường xuất hiện khi hệ thống:

- Cho client truyền `customerId`, `priceListId` hoặc `tier` rồi dùng trực tiếp để lấy giá.
- Gửi tất cả giá về trình duyệt và chỉ ẩn những cột không được phép xem.
- Cache giá theo sản phẩm, làm khách sau nhận giá riêng của khách trước.
- Cho dùng một báo giá của tài khoản khác để đặt hàng với mức giá thấp hơn.
- Hiển thị giá hợp lệ khi xem nhưng không kiểm tra lại điều kiện lúc áp dụng.

Trong phạm vi bảo mật logic nghiệp vụ, bài học cần bảo vệ cả **tính bí mật của giá** và **tính đúng đắn khi sử dụng giá**. Giá đã nhìn thấy không mặc nhiên là giá được phép đặt hàng trong mọi tình huống.

## 2. Phân loại dữ liệu và tách các loại quyền

### 2.1. Không phải mọi trường liên quan đến giá đều có cùng độ công khai

| Nhóm dữ liệu | Ví dụ | Rủi ro nếu trả thừa |
| --- | --- | --- |
| Giá công khai | Giá niêm yết, khuyến mại được công bố | Có thể được phép trả rộng theo chính sách |
| Giá theo tài khoản | Giá hợp đồng, bảng giá đại lý | Lộ điều khoản thương mại riêng |
| Điều kiện hưởng giá | Hạng khách, mức chiết khấu, ngưỡng doanh số | Lộ thông tin đàm phán hoặc cho phép suy giá |
| Giá và chính sách nội bộ | Giá vốn, biên lợi nhuận, mức giảm tối đa | Lộ dữ liệu không thuộc nhu cầu của khách |
| Bản nháp | Giá đang chờ duyệt, chiến dịch chưa phát hành | Lộ kế hoạch hoặc dùng giá chưa được phê duyệt |
| Giá lịch sử | Giá trên báo giá, đơn hàng, chứng từ cũ | Truy cập sai khách hoặc diễn giải sai thời điểm |

Tên hợp đồng, ID bảng giá hoặc phần trăm chiết khấu cũng có thể nhạy cảm dù response không trả `unitPrice`. Nếu giá niêm yết công khai là 1.000.000 VND và API tiết lộ B được giảm 25%, người đọc đã có thể suy ra giá 750.000 VND.

### 2.2. Quyền xem, áp dụng và sửa giá phải tách biệt

| Hành động | Câu hỏi phân quyền |
| --- | --- |
| `VIEW_CUSTOMER_PRICE` | Người này được đọc giá của tài khoản này trong ngữ cảnh này không? |
| `CREATE_CUSTOMER_QUOTE` | Người này được tạo báo giá cho chủ thể mua này không? |
| `PLACE_ORDER` | Người này được chốt giao dịch theo báo giá và điều kiện hiện tại không? |
| `APPROVE_PRICE_OVERRIDE` | Người này được duyệt ngoại lệ giá ở phạm vi/hạn mức nào? |
| `EDIT_PRICE_POLICY` | Người này được thay cấu hình hoặc gán bảng giá cho ai? |
| `VIEW_INTERNAL_COST` | Người này được đọc giá vốn hoặc biên lợi nhuận không? |

Một người mua trong tổ chức có thể được xem giá và lập đề nghị nhưng không được duyệt đơn. Một nhân viên bán hàng có thể được xem giá trong danh mục khách được giao nhưng không được thay hạng khách để tự tạo chiết khấu.

Ẩn nút đặt hàng hoặc ẩn cột giá là hành vi giao diện. Các quyền tương ứng phải được kiểm tra ở server cho từng đối tượng và từng hành động.

## 3. Mô hình quyết định quyền xem

Một quyết định có thể được biểu diễn:

```text
CanViewPrice(actor, account, product, context, time)
  = actor đã được xác thực nếu chính sách yêu cầu
  AND actor được thao tác trong tenant của account
  AND actor có quan hệ/quyền còn hiệu lực với account
  AND sản phẩm và cửa hàng nằm trong phạm vi được phép
  AND nguồn giá được gán đúng account và ngữ cảnh
  AND phiên bản giá được phép công bố tại time
  AND các trường trả về thuộc quyền đọc của actor
```

Đây là các điều kiện đồng thời, không phải các lựa chọn thay thế. Kiểm tra “đã đăng nhập” hoặc “cùng tenant” chỉ đáp ứng một phần. Trong một tenant vẫn có thể có nhiều tài khoản mua hàng với các hợp đồng riêng.

Ngữ cảnh ảnh hưởng đến giá có thể gồm cửa hàng, kênh bán, SKU/biến thể, số lượng, currency, vùng giao hàng được xác minh, đơn vị tính và thời điểm. Chỉ dùng những chiều mà chính sách thật sự định nghĩa; mỗi chiều cần nguồn có thẩm quyền hoặc kiểm tra phù hợp.

### 3.1. Quyền theo đối tượng

Request sau có một định danh do client chọn:

```http
GET /accounts/account-B/products/product-17/price
```

Server phải kiểm tra actor có quyền xem giá trong `account-B`, không chỉ kiểm tra họ được gọi endpoint `/price`. ID ngẫu nhiên hoặc UUID không thay thế kiểm tra quyền.

OWASP mô tả việc thay ID để truy cập đối tượng không thuộc quyền là Broken Object Level Authorization. Cơ chế kiểm tra phải áp dụng cho đúng đối tượng và hành động được yêu cầu. Xem [OWASP API1:2023 — Broken Object Level Authorization](https://github.com/OWASP/API-Security/blob/master/editions/2023/en/0xa1-broken-object-level-authorization.md).

Trong mô hình B2B, so `actor.userId == accountId` thường không đúng: một người có thể đại diện nhiều tổ chức, và một tổ chức có nhiều người mua. Phải kiểm tra quan hệ thành viên, ủy quyền hoặc phạm vi quản lý thực tế.

### 3.2. Quyền theo thuộc tính

Một người có quyền xem sản phẩm vẫn có thể không được xem `contractPrice`, `costPrice`, `margin` hoặc thông tin giá của các khách khác. DTO cần phản ánh quyền ở cấp trường.

OWASP API3 đề cập việc trả hoặc cho sửa các thuộc tính mà người dùng không có quyền, đồng thời khuyến nghị chọn rõ các trường cần công bố thay vì serialize toàn bộ đối tượng. Xem [OWASP API3:2023 — Broken Object Property Level Authorization](https://github.com/OWASP/API-Security/blob/master/editions/2023/en/0xa3-broken-object-property-level-authorization.md).

### 3.3. Các bất biến cần giữ

1. Không có giá hoặc thông tin suy ra giá riêng của chủ thể khác trong response, cache, lỗi hoặc kênh xuất dữ liệu không được cấp quyền.
2. Bảng giá/hạng khách được chọn từ quan hệ có thẩm quyền, không do caller tự khai.
3. Mọi đường đọc cùng áp dụng chính sách đối tượng và thuộc tính.
4. Một kết quả giá luôn gắn đúng account, sản phẩm, số lượng, currency và phiên bản.
5. Không có quyền hoặc chưa có giá không được biểu diễn ngầm thành giá bằng 0.
6. Quyền áp dụng giá được kiểm tra riêng tại bước có hiệu ứng nghiệp vụ.

## 4. Thiết kế API chỉ công bố dữ liệu được phép

### 4.1. Client đề nghị ngữ cảnh, server xác định quyền

Một API đọc giá theo tài khoản có thể nhận:

```http
GET /accounts/account-A/products/product-17/price
    ?storeId=store-1&quantity=2&currency=VND
```

`accountId`, `storeId`, sản phẩm, số lượng và currency đều là dữ liệu chưa tin cậy cần kiểm tra. Server lấy actor từ danh tính đã xác thực, xác minh quyền trên account/store, rồi suy bảng giá và điều kiện được hưởng.

Không mở các tham số như `tier=VIP`, `priceListId=contract-B` hoặc `includeInternalCost=true` cho client thường rồi coi chúng là cấu hình đã được duyệt. Nếu có API nội bộ hỗ trợ chọn bảng giá, quyền chọn phải được kiểm tra riêng theo phạm vi và mục đích.

Quy trình đọc điển hình:

```text
Xác thực danh tính và phạm vi tenant
  → Xác minh actor được xem giá cho account được chọn
  → Kiểm tra ngữ cảnh sản phẩm/cửa hàng/số lượng/currency
  → Suy nguồn giá đã công bố từ cấu hình có thẩm quyền
  → Đọc/tính projection cho đúng khách và phiên bản
  → Chọn các trường được phép trả
  → Áp chính sách cache và trả kết quả
```

### 4.2. Response có ý nghĩa rõ ràng

Một response minh họa cho giá dòng hàng, chưa gồm vận chuyển và các khoản được tính ở bước sau:

```json
{
  "accountId": "account-A",
  "productId": "product-17",
  "quantity": 2,
  "status": "AVAILABLE",
  "price": {
    "amountMinor": "1700000",
    "currency": "VND",
    "unitScale": 0,
    "basis": "ITEMS_ONLY"
  },
  "priceVersion": "customer-price-v8",
  "validUntil": "2026-12-01T00:00:00Z"
}
```

Thời điểm trên là dữ liệu minh họa cho một phiên bản có hiệu lực, không phải lời hứa rằng mọi quyền sẽ được giữ đến ngày đó. Quyền truy cập và khả năng dùng giá còn phải theo chính sách của từng bước.

Response không cần chứa giá của B, toàn bộ bậc giá nội bộ, giá vốn, biên lợi nhuận hoặc lý do xếp hạng khách nếu những thông tin đó không thuộc hợp đồng API. Trường `basis` giúp người xem biết đây là giá hàng hóa hay tổng thanh toán hoàn chỉnh.

Nếu nghiệp vụ không công bố giá, có thể trả trạng thái như `REQUEST_QUOTE` cho đối tượng vốn được phép xem thông tin đó. Nếu caller không có quyền đối tượng, dùng phản hồi từ chối/không tìm thấy theo chính sách API mà không tiết lộ giá hoặc sự tồn tại của hợp đồng riêng.

Không dùng `amountMinor="0"` cho “không có quyền”, “chưa có bảng giá” hoặc “pricing service lỗi”. Giá miễn phí hợp lệ phải là một kết quả giá được tính và công bố rõ ràng, không phải giá trị mặc định khi thiếu dữ liệu.

### 4.3. Giới hạn dữ liệu từ nguồn đến đầu ra

Nếu có thể, query/repository chỉ đọc projection cần cho response trong phạm vi đã được kiểm tra. Việc load toàn bộ giá rồi lọc trước khi serialize làm tăng nguy cơ dữ liệu thừa đi vào log, cache hoặc nhánh lỗi.

Lọc ở repository không thay thế quyền thuộc tính ở tầng công bố. Ngược lại, DTO an toàn cũng không sửa được một query dùng sai account. Hai lớp cần có hợp đồng nhất quán.

## 5. Ví dụ Java: đọc giá qua phạm vi đã được cấp quyền

Ví dụ Java 17 dưới đây minh họa ranh giới giữa phân quyền, nguồn giá và DTO công bố. Các interface là hợp đồng cần được triển khai theo mô hình thành viên/ủy quyền của hệ thống; không có phép so sánh ID đơn lẻ nào thay thế toàn bộ chính sách.

```java
import java.math.BigInteger;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

final class CustomerPriceReadService {
    record Actor(UUID actorId, UUID tenantId) {}

    record Query(
        UUID accountId, UUID storeId, UUID productId,
        int quantity, String currency
    ) {}

    record ReadScope(
        UUID tenantId, UUID accountId, UUID storeId,
        String assignmentVersion, String permissionVersion
    ) {}

    record PriceProjection(
        BigInteger amountMinor, String currency, int unitScale,
        String priceVersion, Instant validUntil
    ) {}

    record MoneyView(
        String amountMinor, String currency, int unitScale, String basis
    ) {}

    record PriceView(
        UUID accountId, UUID productId, int quantity, String status,
        MoneyView price, String priceVersion, Instant validUntil
    ) {}

    interface AccessPolicy {
        ReadScope requirePriceRead(Actor actor, Query query, Instant asOf);
    }

    interface PriceRepository {
        PriceProjection resolvePublished(
            ReadScope scope, UUID productId,
            int quantity, String currency, Instant asOf
        );
    }

    private final AccessPolicy access;
    private final PriceRepository prices;
    private final Clock clock;

    CustomerPriceReadService(
        AccessPolicy access, PriceRepository prices, Clock clock
    ) {
        this.access = Objects.requireNonNull(access);
        this.prices = Objects.requireNonNull(prices);
        this.clock = Objects.requireNonNull(clock);
    }

    PriceView read(Actor actor, Query query) {
        Objects.requireNonNull(actor);
        Objects.requireNonNull(query);
        Objects.requireNonNull(query.accountId());
        Objects.requireNonNull(query.storeId());
        Objects.requireNonNull(query.productId());
        if (query.quantity() < 1 || query.quantity() > 1000
                || query.currency() == null
                || !query.currency().matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("INVALID_PRICE_QUERY");
        }

        Instant asOf = clock.instant();
        ReadScope scope = access.requirePriceRead(actor, query, asOf);
        if (!scope.tenantId().equals(actor.tenantId())
                || !scope.accountId().equals(query.accountId())
                || !scope.storeId().equals(query.storeId())) {
            throw new IllegalStateException("INVALID_AUTHORIZED_SCOPE");
        }

        PriceProjection price = prices.resolvePublished(
            scope, query.productId(), query.quantity(), query.currency(), asOf
        );
        if (price == null) {
            throw new IllegalStateException("PRICE_UNAVAILABLE");
        }
        if (!query.currency().equals(price.currency())
                || price.amountMinor().signum() < 0
                || price.amountMinor().toString().length() > 30
                || price.unitScale() < 0 || price.unitScale() > 9
                || !price.validUntil().isAfter(asOf)) {
            throw new IllegalStateException("INVALID_PRICE_PROJECTION");
        }

        return new PriceView(
            scope.accountId(), query.productId(), query.quantity(), "AVAILABLE",
            new MoneyView(
                price.amountMinor().toString(), price.currency(),
                price.unitScale(), "ITEMS_ONLY"
            ),
            price.priceVersion(), price.validUntil()
        );
    }
}
```

Các tiền điều kiện phải được giữ khi áp dụng:

- `Actor` được tạo từ danh tính đã xác thực và ngữ cảnh tenant đã được kiểm tra. Không bind record này trực tiếp từ JSON hoặc header tùy ý.
- `requirePriceRead` kiểm tra quan hệ hiện hành, quyền xem giá, phạm vi cửa hàng và điều kiện cần thiết. Nó suy assignment từ nguồn tin cậy.
- `resolvePublished` dùng toàn bộ scope để chọn giá đã công bố và còn hiệu lực. Không tìm theo một `productId` rồi lấy giá đầu tiên trong bảng.
- Giới hạn số lượng, scale và độ dài là lựa chọn cho ví dụ. Production phải thống nhất với sản phẩm và hợp đồng tiền.
- Projection không chứa giá vốn hoặc giá của khách khác. DTO không serialize entity nội bộ và không công bố assignment/permission version chỉ vì chúng có trong scope.
- Giá bằng 0 có thể là giá miễn phí hợp lệ; trường hợp thiếu dữ liệu đi qua nhánh lỗi riêng, không bị đổi thành 0.
- Cơ chế ánh xạ lỗi HTTP phải giữ chính sách không tiết lộ dữ liệu. `IllegalStateException` trong ví dụ không phải một response lỗi hoàn chỉnh.

`ReadScope` là kiểu nội bộ biểu diễn kết quả phân quyền; việc có một record không tự tạo ranh giới bảo mật nếu code khác cho client tự xây scope. Những đường đọc khác cũng phải đi qua chính sách tương ứng.

Ví dụ chỉ trả giá xem trước của dòng hàng. Nó chưa tạo một báo giá có quyền sử dụng, giữ hạn mức khuyến mại, đặt hàng hoặc bảo đảm tính nguyên tử với một thao tác mua sau đó.

## 6. Áp chính sách ở mọi đường truy cập

### 6.1. Query cần giữ đầy đủ phạm vi

Một bảng giá theo khách có thể cần khóa logic gồm tenant, account hoặc assignment, cửa hàng/kênh, sản phẩm, currency, đơn vị tính, bậc số lượng và phiên bản hiệu lực. Query thiếu một chiều có thể trả một hàng có số tiền hợp lệ nhưng thuộc khách khác.

Không giải quyết nhiều giá khớp bằng `LIMIT 1` hoặc “giá thấp nhất” nếu chính sách không định nghĩa như vậy. Cần thứ tự ưu tiên rõ ràng giữa giá công khai, hợp đồng, chương trình và ngoại lệ; dữ liệu mâu thuẫn phải được phát hiện thay vì vô tình chọn giá thuận lợi nhất.

Nếu dùng row-level security ở DB, cần cấu hình đúng vai trò và phạm vi phiên kết nối. Nó có thể hỗ trợ giới hạn hàng nhưng không tự loại bỏ trường nhạy cảm hoặc kiểm tra đầy đủ điều kiện áp dụng giá. Service vẫn cần hợp đồng phân quyền và projection.

### 6.2. Thành viên nhiều tài khoản và người được ủy quyền

Người dùng được chọn tài khoản mua hàng nếu họ có quyền tương ứng, nhưng lựa chọn đó chỉ là đề nghị ngữ cảnh. Server phải xác minh quan hệ còn hiệu lực với account đã chọn.

Nhân viên hỗ trợ hoặc người bán thao tác thay khách cần quyền ủy quyền có phạm vi. Audit nên giữ cả actor thực và account/chủ thể được đại diện. Không thay toàn bộ danh tính actor bằng khách rồi làm mất dấu vết ai đã đọc hoặc tạo báo giá.

Một quyền quản trị sản phẩm không tự bao gồm quyền xem mọi hợp đồng khách. Nếu có chức năng hỗ trợ đặc quyền hoặc truy cập ngoại lệ, nó cần mục đích, phạm vi và ghi nhận riêng; không dùng cờ `isInternal=true` do request gửi.

### 6.3. Danh sách, batch và GraphQL

Endpoint lấy nhiều sản phẩm hoặc nhiều account phải kiểm tra từng phạm vi. Một phần tử hợp lệ trong request không cấp quyền cho các phần tử còn lại.

Có thể chọn trả toàn bộ lỗi hoặc kết quả từng phần theo hợp đồng API, nhưng phần bị từ chối không được mang theo giá, contract ID hoặc thông tin phân biệt khách khác. Tổng số dòng, tổng tiền hoặc thứ tự xếp hạng cũng không được vô tình phản ánh các giá bị lọc.

Trong GraphQL, resolver cho giá và trường nhạy cảm cần chính sách riêng. Một người có quyền đọc `Product.name` không tự được đọc `Product.customerPrices`. Alias, truy vấn lồng hoặc DataLoader không được làm mất account/tenant của từng phần tử; loader cache chỉ theo product ID có thể trả nhầm giá.

API export, ứng dụng mobile và endpoint cũ cũng là các đường công bố. Chỉ sửa một màn hình web không đóng được các đường đọc còn lại.

## 7. Cache, CDN và chuyển tài khoản

### 7.1. Phân biệt cache tính giá với cache response

Có hai loại dữ liệu khác nhau:

| Loại cache | Có thể chứa | Điều kiện an toàn |
| --- | --- | --- |
| Cache dữ liệu/quy tắc nội bộ | Bảng giá đã công bố, phiên bản quy tắc | Không tự cấp quyền đọc; lookup giữ phạm vi và hiệu lực |
| Cache kết quả tính | Giá theo assignment và toàn bộ ngữ cảnh ảnh hưởng | Cùng ngữ cảnh thật sự, không tái dùng khi điều kiện thay đổi |
| Cache response cho khách | Giá, account ID và metadata đã công bố | Ràng buộc đối tượng được đọc và kiểm tra quyền trước khi trả |

Hai khách có thể tình cờ nhận cùng số tiền nhưng không có nghĩa được dùng chung response. Body có thể chứa account ID, điều kiện hoặc nguồn giá riêng; quyền vẫn cần được kiểm tra.

Khóa cache phải bao gồm các chiều quyết định kết quả, chẳng hạn tenant, account/assignment, product, quantity tier, store/channel, currency, phiên bản giá và quy tắc hiệu lực. Nếu cache cả quyết định quyền, cần xử lý phiên bản quyền, thu hồi và thời hạn chấp nhận rõ ràng.

Bỏ sót một chiều có thể là lỗi bảo mật: cache theo `productId` làm giá A rơi vào response cho B; cache theo `accountId` mà thiếu store/currency có thể khiến giá được áp sai điều kiện.

### 7.2. HTTP cache cần cấu hình chủ động

Một endpoint giá riêng có thể chọn chính sách không lưu response ở cache HTTP:

```http
Cache-Control: private, no-store
```

Theo RFC 9111, `private` không cho shared cache lưu response khi dùng dạng không liệt kê trường; `no-store` yêu cầu cache không lưu response theo quy tắc của chỉ thị. Các header này không thay thế phân quyền hoặc bảo đảm dữ liệu đã bị sao chép sẽ biến mất. Xem [RFC 9111: Cache-Control response directives](https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2).

Nếu sản phẩm chủ động cho cache riêng ở client hoặc có thiết kế CDN cá nhân hóa, cần một mô hình cô lập và thu hồi phù hợp. Không bật `public`/`s-maxage` cho response có giá riêng chỉ vì muốn giảm tải. Đăng nhập bằng cookie cũng không tự biến mọi cấu hình CDN thành an toàn.

`Vary` có thể giúp phân biệt representation theo header, nhưng không tự kiểm tra quan hệ người dùng với account. `Vary: Accept-Language` không cô lập giá hợp đồng; một khóa cache có nhiều biến thể vẫn có thể cấp dữ liệu sai quyền.

Nếu dùng ETag/conditional request, origin phải kiểm tra quyền trước khi trả nội dung hoặc xác nhận tái sử dụng bản riêng. Không dùng cùng một validator cho những representation khác phạm vi rồi để client tái dùng body không phù hợp.

### 7.3. Cache ứng dụng và trạng thái frontend

HTTP header không tự dọn query cache, local storage, service worker hoặc cache tùy biến trong ứng dụng. Các thành phần này cần chính sách theo danh tính/account và xử lý logout/chuyển tài khoản.

Một cuộc đua thường gặp:

```text
+ Người dùng đang xem account A, request giá A chưa trả về
+ Người dùng chuyển sang account B
+ Response giá A trả về muộn
+ Giao diện B hiển thị giá A nếu chỉ lưu state theo productId
```

Frontend nên gắn request và response với ngữ cảnh account/version hiện hành, bỏ qua response cũ và cập nhật đồng thời nhãn account, giá, currency cùng các hành động. Hủy request cũ có thể hỗ trợ, nhưng vẫn cần kiểm tra ngữ cảnh khi nhận response.

Khi thoát hoặc mất quyền, xóa các dữ liệu riêng trong state do ứng dụng kiểm soát theo chính sách. Việc này giảm trả nhầm dữ liệu trên client; server vẫn phải kiểm tra lại quyền cho request mới. Không thể thu hồi triệt để một mức giá đã được người có quyền đọc và tự sao chép trước đó.

## 8. Từ quyền xem giá đến quyền áp dụng giá

### 8.1. Đọc giá không cấp một quyền sử dụng vô hạn

Một kết quả xem trước có thể phụ thuộc số lượng, cửa hàng, currency và thời điểm. Người dùng không được giữ con số đó rồi áp cho SKU khác, số lượng khác hoặc tài khoản khác.

Một báo giá có thể lưu:

```text
+ tenant / account / chủ thể được phép sử dụng
+ sản phẩm, biến thể, số lượng và đơn vị tính
+ currency, amount và các thành phần có ý nghĩa
+ nguồn giá, phiên bản chính sách và điều kiện áp dụng
+ cửa hàng/kênh và các điều kiện giao dịch liên quan
+ hạn dùng, trạng thái và quy tắc số lần sử dụng
```

Biết `quoteId` không mặc nhiên là quyền đọc hoặc dùng báo giá. Nếu có chức năng chia sẻ bằng bearer link, đó phải là một cơ chế cấp quyền được thiết kế rõ về phạm vi và thời hạn; không suy quyền chỉ từ việc URL chứa UUID khó đoán.

### 8.2. Luồng chốt đơn cần kiểm tra lại bất biến

Một API đặt hàng hẹp có thể nhận:

```http
POST /accounts/account-A/orders
Idempotency-Key: order-command-key
Content-Type: application/json

{
  "quoteId": "quote-A-17",
  "expectedQuoteVersion": 3
}
```

Server không lấy `unitPrice`, `tier`, `discountPercent` hoặc `approved=true` từ request để thay thế dữ liệu đã chốt.

```text
+ Xác thực actor và phạm vi account
+ BEGIN
+   Claim idempotency key hoặc trả kết quả cũ sau kiểm tra quyền
+   Khóa/kiểm soát phiên bản quote và đối tượng nguồn cần thiết
+   Kiểm tra quyền đặt hàng cho account, không chỉ quyền xem giá
+   Kiểm tra quote thuộc đúng chủ thể được sử dụng
+   Kiểm tra trạng thái, hạn dùng, sản phẩm, số lượng và currency
+   Kiểm tra điều kiện hợp đồng/giá theo chính sách tại lúc chốt
+   Kiểm tra phê duyệt hoặc hạn mức nếu nghiệp vụ yêu cầu
+   Giữ/tiêu thụ quyền lợi có hạn mức bằng thao tác nguyên tử
+   Tạo order từ money snapshot được chấp nhận
+   Ghi kết quả idempotency và outbox nếu cần
+ COMMIT
```

Quy tắc cho báo giá còn hiệu lực sau khi bảng giá thay đổi phải được định nghĩa: giữ snapshot đã cam kết hoặc yêu cầu báo giá/xác nhận mới. Không âm thầm dùng một giá khác với nội dung được xác nhận.

Nếu chính sách yêu cầu chặn ngay khi quyền mua bị thu hồi, quyết định chốt cần tham chiếu quyền hiện hành tại ranh giới có thẩm quyền. Chỉ lưu một `permissionVersion` trong quote không tự ngăn cuộc đua với thao tác thu hồi.

### 8.3. Idempotency và giới hạn sử dụng

Idempotency key cần có phạm vi phù hợp với tenant/account/loại thao tác và fingerprint của command. Cùng key nhưng đổi account hoặc quote phải bị từ chối, không trả kết quả đơn của chủ thể khác.

Ngoài khóa request, cần ràng buộc số lần dùng quote hoặc quyền lợi theo hợp đồng. Một quote được thiết kế dùng một lần phải được consume nguyên tử; đổi key không được tạo thêm đơn. Nếu quote cho phép nhiều lần dùng, vẫn cần kiểm soát hạn mức và điều kiện mỗi lần.

Luồng xem giá hoặc tải lại trang không được tự tiêu thụ coupon, ngân sách chiết khấu hoặc số lần dùng báo giá. Các hiệu ứng này thuộc thao tác nghiệp vụ được xác định; việc ghi audit đọc không nên bị nhầm với việc thực hiện mua hàng.

Ẩn giá khỏi UI cũng không đủ ngăn người dùng đoán và gửi giá thấp. Hàng rào toàn vẹn là server tự chọn giá hợp lệ và so khớp đối tượng nguồn khi tạo đơn.

## 9. Vòng đời giá, quyền và phê duyệt

### 9.1. Chỉ công bố phiên bản được phép

Một vòng đời giá minh họa:

```text
+DRAFT → IN_REVIEW → APPROVED → PUBLISHED → RETIRED
+```

Những vai trò được xem giá đang duyệt có thể khác người mua được xem giá đã phát hành. Endpoint khách hàng không được mở bản nháp bằng một tham số như `preview=true` nếu không có quyền preview riêng.

Các thay đổi gán bảng giá, đưa giá riêng thành công khai, nâng hạng khách hoặc thêm sản phẩm vào hợp đồng đều có ảnh hưởng quyền lợi và bí mật thương mại. Cần kiểm tra quyền sửa theo đúng phạm vi; khi có phê duyệt, phải gắn phê duyệt với nội dung/phiên bản cụ thể.

Không chỉ bảo vệ cột amount. Một nhân viên không được sửa giá nhưng sửa `customerTier=VIP` hoặc gán account vào bảng giá tốt hơn vẫn có thể tạo cùng hiệu ứng giảm giá.

### 9.2. Thu hồi quyền và thay đổi quan hệ

Một membership có thể bị tạm dừng, hết hạn hoặc thu hồi trong khi cache còn nóng. Một hợp đồng có thể ngừng áp dụng cho giao dịch mới nhưng chứng từ cũ vẫn cần chính sách đọc riêng.

Cần xác định:

- Quyền nào chấm dứt cho request mới và từ thời điểm nào.
- Báo giá đã phát hành còn được dùng theo điều kiện nào.
- Job export đang chờ có tiếp tục được chạy hoặc tải về không.
- Cache quyết định quyền được vô hiệu hóa hoặc kiểm tra phiên bản ra sao.
- Quyền đọc đơn hàng/chứng từ lịch sử được đánh giá theo chính sách nào.

Đọc quyền từ cache có TTL ngắn vẫn có khoảng trễ. Nếu cam kết thu hồi tại một ranh giới chặt, phải có giao thức kiểm tra/đồng bộ đủ mạnh ở ranh giới đó; không mô tả một cơ chế nhất quán cuối cùng như thể quyền đã biến mất ngay trên mọi bản sao.

Thu hồi ngăn những lần truy cập tiếp theo theo chính sách, không xóa được kiến thức mà người trước đó có quyền đã nhận. Vì vậy cần giảm dữ liệu trả về ngay từ đầu, đồng thời kiểm soát các kênh xuất/sao chép do hệ thống cung cấp.

### 9.3. Khi pricing service hoặc cấu hình không sẵn sàng

Không có được một quyết định giá riêng đáng tin cậy không đồng nghĩa với được chọn giá thấp nhất, giá của khách trước hoặc giá bằng 0.

Nếu sản phẩm cho phép hiển thị giá công khai như một lựa chọn riêng, phải lấy nó từ nguồn công khai được phép và gắn nhãn đúng vai trò. Không giả làm giá hợp đồng của account đang xem. Việc có được đặt hàng theo giá công khai hay cần lấy lại báo giá phải theo luồng áp dụng giá.

Nếu không thể xác định đúng quyền hoặc nguồn giá, dừng công bố phần riêng và trả trạng thái/lỗi phù hợp. Khả năng sẵn sàng không được đạt bằng cách mở quyền đọc dữ liệu của khách khác.

## 10. Những đường rò rỉ ngoài response giá chính

### 10.1. HTML, dữ liệu khởi tạo và tài nguyên công khai

Không gửi tất cả giá trong HTML rồi dùng CSS/JavaScript ẩn cột riêng. Người nhận có thể đọc source, hydration state, network response hoặc biến JavaScript.

Với server-side rendering, dữ liệu dùng để dựng trang cũng phải là projection đã được phân quyền. Cache trang hoặc payload khởi tạo phải giữ ngữ cảnh tương ứng. Không nhúng bảng giá hợp đồng thật vào bundle frontend hoặc dữ liệu mẫu được phát công khai.

Structured data cho công cụ tìm kiếm, thẻ social preview và feed sản phẩm chỉ nên chứa dữ liệu được phép công khai. `robots.txt` hoặc `noindex` có thể tác động việc khám phá/lập chỉ mục nhưng không phải kiểm soát quyền truy cập giá riêng.

### 10.2. Tìm kiếm, lọc, sắp xếp và thống kê

Có thể không trả giá trực tiếp nhưng vẫn làm lộ nó qua các phép hỏi:

```text
+ Sản phẩm có giá của account B thấp hơn 800.000 không?
+ Sắp xếp toàn bộ khách theo mức chiết khấu rồi trả tên/ID
+ Tính min/max giá hợp đồng trên những tài khoản không được đọc
+ Trả số lượng khách thuộc một khoảng giá hẹp
```

Bộ lọc, thứ tự và thống kê cũng là đầu ra của dữ liệu. Phải giới hạn tập dữ liệu được xét hoặc có chính sách công bố tổng hợp riêng. Không chỉ xóa trường `price` sau khi đã dùng giá bí mật để xếp hạng response.

Chặn dò hàng loạt, giới hạn truy vấn và theo dõi hành vi có thể hỗ trợ, nhưng quyền đúng cho một request vẫn là điều kiện đầu tiên. Rate limit không hợp thức hóa một lần tiết lộ giá B cho A.

### 10.3. Export và file tải về

Job export cần gắn actor, phạm vi account, tập trường và điều kiện quyền phù hợp. Phải có quy tắc kiểm tra lúc tạo job, lúc chạy và lúc tải file; không dùng một tài khoản dịch vụ quyền rộng rồi bỏ mất phạm vi người yêu cầu.

File kết quả phải nằm trong nơi có kiểm soát truy cập hoặc cơ chế chia sẻ có thời hạn được định nghĩa. Một URL tải file có ID khó đoán không tự giải quyết thu hồi quyền. File nhiều khách hoặc chứa trường nội bộ chỉ được tạo cho đối tượng được cấp quyền tương ứng.

### 10.4. Lỗi, log và dữ liệu phân tích

Lỗi từ chối không nên kèm câu như “Giá hợp đồng B là 750.000 nhưng bạn chỉ được dùng 850.000”. Các mã lỗi, đường dẫn và thông tin trace cũng không nên lộ toàn bộ điều kiện giá riêng.

Không đưa entity giá đầy đủ vào log debug hoặc error tracker. Hệ thống phân tích, session replay và dữ liệu hỗ trợ cần được xem như kênh công bố có đối tượng đọc riêng; chỉ gửi các trường cần thiết và có chính sách che/giới hạn phù hợp.

Audit nghiệp vụ có thể lưu actor, account, hành động, kết quả, phiên bản quyền/giá và nguồn quyết định để điều tra. Giá trị nhạy cảm chỉ được lưu ở nơi có quyền và thời hạn phù hợp, không mặc định lặp lại trong mọi access log.

## 11. Kiểm thử tình huống lạm dụng

### 11.1. Ma trận quyền và đường đọc

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Guest xem sản phẩm có giá công khai | Chỉ nhận dữ liệu công khai theo chính sách |
| Người dùng chưa có quyền giá nhưng được xem catalog | Không nhận số tiền riêng; không dùng 0 làm placeholder |
| Khách A thay account ID thành B trong cùng tenant | Không xem được giá/điều kiện hợp đồng của B |
| Thay tenant hoặc store thuộc phạm vi khác | Bị từ chối theo quyền đối tượng |
| Dùng UUID quote/price list của khách khác | Không được đọc hoặc dùng chỉ nhờ biết ID |
| Tự gửi `tier=VIP`, `includeCost=true` hoặc assignment khác | Không thay được phạm vi công bố hoặc nguồn giá |
| Người được ủy quyền trong phạm vi hợp lệ | Nhận đúng dữ liệu; audit giữ actor thực và account được đại diện |
| Quyền ủy quyền hết hạn hoặc bị thu hồi | Request mới bị xử lý theo chính sách quyền hiện hành |
| Người được xem giá nhưng không được đặt hàng | Xem được projection, không vượt quyền tạo đơn |
| Giá nháp/chờ duyệt hoặc chương trình chưa phát hành | Không hiện ở endpoint khách hàng thường |
| Chỉ được xem giá bán | Response không có giá vốn, margin, bảng giá khách khác hoặc điều kiện suy ra chúng |
| Batch trộn phần tử được phép và không được phép | Không rò dữ liệu phần bị từ chối qua body, tổng, count hoặc lỗi |
| GraphQL alias, resolver lồng hoặc DataLoader dùng cache | Từng giá vẫn giữ scope đúng; không trả thừa thuộc tính |
| Endpoint cũ, mobile hoặc export | Cùng thực thi chính sách đọc tương ứng |
| Cache đã được làm nóng bởi A rồi B đọc cùng sản phẩm | B không nhận giá/metadata riêng của A |
| Cache hết hiệu lực giá hoặc quyền trong khi có request mới | Không dùng lại quyết định ngoài chính sách hiệu lực |
| Conditional request với ETag từ tài khoản khác | Không dùng validator để tái sử dụng body riêng sai quyền |
| Logout/chuyển account trong lúc response cũ đang về | Không hiển thị giá cũ trong ngữ cảnh account mới |
| Đọc HTML, hydration state, JSON-LD, script hoặc feed | Không có dữ liệu riêng bị ẩn bằng giao diện |
| Tìm kiếm/sắp xếp/lọc theo giá không được phép đọc | Không suy được giá bí mật từ kết quả |
| Pricing service lỗi hoặc không có assignment hợp lệ | Không fallback thành 0 hoặc giá của người trước |
| Giá miễn phí được cấu hình hợp lệ | Được phân biệt rõ với thiếu giá/không có quyền |
| Chuyển SKU, số lượng hoặc currency sau khi xem giá | Không áp giá cũ ngoài điều kiện đã chốt |
| Dùng quote A để tạo đơn cho account B | Bị từ chối; không có đơn hoặc hiệu ứng tiền sai |
| Đổi giá/điều kiện sau phê duyệt | Cần phiên bản và quy trình xác nhận/phê duyệt phù hợp |
| Hai lần consume một quote dùng một lần, key khác nhau | Chỉ một lần được chấp nhận theo ràng buộc nghiệp vụ |
| Retry sau khi tạo đơn commit nhưng mất response | Trả kết quả cũ sau kiểm tra quyền, không tạo thêm đơn |
| Xem trước/tải lại giá nhiều lần | Không tiêu thụ quota/coupon hoặc thực hiện đặt hàng |
| Export được tạo trước khi mất quyền nhưng tải sau đó | Kết quả đúng chính sách quyền ở các giai đoạn được định nghĩa |
| Đọc chứng từ lịch sử khi hợp đồng bán mới hết hiệu lực | Được đánh giá bằng chính sách lịch sử, không tự mở mọi giá hiện tại |

Kiểm thử phải quan sát response thô và các side effect, không chỉ phần nhìn thấy trên UI. Với lỗi trả thừa thuộc tính, một test frontend không thấy cột giá vốn vẫn có thể bỏ sót `costPrice` trong JSON.

Kiểm thử cache nên chạy hai chủ thể theo cả hai thứ tự làm nóng và các ngữ cảnh khác currency/store/quantity. Kiểm thử chuyển tài khoản cần tạo response về ngược thứ tự. Những cuộc đua về thu hồi quyền hoặc consume quote cần điểm đồng bộ và cơ chế DB tương ứng.

### 11.2. Tính chất cần giữ

Trong mô hình các bảng giá khách độc lập, có thể kiểm tra:

```text
+ Đổi giá riêng của B không làm thay response dành cho A
+ khi dữ liệu A được phép đọc và điều kiện của A giữ nguyên.
+
+ Không có quyền đọc một trường thì trường đó và dữ liệu tương đương
+ không xuất hiện qua serializer, error, export hoặc thống kê không được cấp quyền.
+
+ Cùng product nhưng khác account không mặc nhiên dùng chung response.
+
+ Quyền xem giá không làm phát sinh quyền sửa hoặc quyền đặt hàng.
+
+ Replay một command không tạo thêm lần sử dụng quyền lợi hoặc thêm đơn.
+```

Không cần chỉ dựa vào danh sách field cấm như `costPrice`: đổi tên thành `baseCost` vẫn có thể rò cùng dữ liệu. Nên xác định schema field được phép và kiểm tra nguồn/ngữ nghĩa của từng trường nhạy cảm.

Đối với từ chối truy cập, kiểm tra không có số tiền, contract ID hoặc thông tin khác biệt không cần thiết trong body và header. Có thể xem xét dấu hiệu suy luận qua số lượng, mã lỗi và thời gian xử lý theo mức độ nhạy cảm, nhưng không tuyên bố một response “404 giống nhau” đã loại bỏ mọi kênh suy luận.

## 12. Những thiết kế cần xem lại

| Dấu hiệu | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Giá là trường luôn đi kèm Product entity | Mọi API sản phẩm có thể trả thừa giá riêng | Projection theo đối tượng, mục đích và quyền thuộc tính |
| Client chọn customer tier hoặc price list trực tiếp | Tự chọn giá tốt hơn hoặc đọc hợp đồng khác | Server suy assignment từ quan hệ được kiểm tra |
| Chỉ kiểm tra cùng tenant | Lộ giá giữa các account trong một tổ chức lớn | Kiểm tra quyền theo account và hành động |
| Load mọi giá rồi ẩn bằng CSS | Dữ liệu đã tới người không có quyền | Không công bố dữ liệu ngoài projection cho phép |
| Cache theo product ID | Trả giá khách trước cho khách sau | Khóa cache theo toàn bộ ngữ cảnh và phạm vi |
| Giá lỗi được trả bằng 0 | Hiểu thành miễn phí và có thể tạo đơn sai | Trạng thái/lỗi riêng cho thiếu giá và thiếu quyền |
| Có quyền xem thì được dùng mọi quote | Dùng giá khác khách hoặc khác điều kiện | Phân quyền áp dụng và binding quote khi chốt |
| API thường an toàn nhưng export dùng tài khoản dịch vụ toàn quyền | Lộ dữ liệu qua file tải về | Truyền và kiểm tra phạm vi người yêu cầu suốt luồng |
| Sửa hạng khách không qua kiểm soát giá | Thay giá gián tiếp mà không sửa amount | Bảo vệ mọi dữ liệu tạo quyền hưởng giá |
| Bảng giá được duyệt nhưng assignment đổi tùy ý | Giá hợp lệ được cấp sai chủ thể | Phê duyệt và quyền sửa cho nội dung/phạm vi gán |

Một cơ chế customer price visibility đạt yêu cầu khi giải thích được **ai đang xem, đại diện cho account nào, được thấy những trường nào, nguồn giá nào được phép dùng và điều kiện nào còn phải kiểm tra khi đặt hàng**. Những quyết định đó phải được giữ xuyên suốt query, serializer, cache và mọi kênh công bố dữ liệu.

