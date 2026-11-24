# Price snapshot: chốt giá nhất quán và bảo vệ nội dung giao dịch

## 1. Vấn đề: cùng một đơn nhưng mỗi bước dùng một giá

Người dùng xem giỏ hàng có tổng phải trả 303.000 VND. Trước lúc thanh toán, giá sản phẩm thay đổi. Backend thanh toán đọc bảng giá mới, còn đơn hàng vẫn lưu tổng cũ. Webhook sau đó được đối chiếu với một giá trị khác nữa do chương trình giảm giá vừa cập nhật.

Không có quy tắc chốt giá rõ ràng, hệ thống khó trả lời: khách đã đồng ý trả bao nhiêu, cổng thanh toán được yêu cầu thu bao nhiêu và khoản nào phải hoàn nếu hủy hàng?

Kẻ tấn công còn có thể cố tình khai thác khoảng hở: giữ báo giá cũ, đổi sản phẩm sau khi được duyệt, dùng snapshot của người khác, gửi lại yêu cầu tạo đơn hoặc sửa tổng tiền trong payload.

*Price snapshot* là bản ghi bất biến của kết quả tính giá và các dữ kiện cần thiết để giải thích kết quả đó tại một thời điểm nghiệp vụ xác định. Snapshot giúp các bước sau dùng cùng một nội dung tài chính, thay vì liên tục tính lại từ dữ liệu đang thay đổi.

Trong bảo mật logic nghiệp vụ, snapshot bảo vệ mối liên hệ giữa **nội dung được tính giá, nội dung được chấp nhận và số tiền thực thi**. Nó cần kết hợp với quyền theo đối tượng, state machine, transaction, kiểm soát đồng thời và idempotency.

## 2. Phân biệt snapshot, báo giá, giữ chỗ và đơn hàng

Những khái niệm sau có thể liên kết nhưng không thay thế nhau:

| Khái niệm | Trách nhiệm |
|---|---|
| Dữ liệu giá hiện hành | Giá đang áp dụng trong catalog, bảng giá hoặc hệ thống định giá |
| Price snapshot | Kết quả tính giá bất biến cùng dữ kiện giải thích |
| Báo giá, hay quote | Quyền sử dụng một kết quả giá trong phạm vi, điều kiện và thời hạn xác định |
| Giữ chỗ tài nguyên | Giữ tồn kho, ngân sách khuyến mãi hoặc năng lực phục vụ |
| Đơn hàng | Cam kết nghiệp vụ đã được tạo, có trạng thái và nội dung tài chính được chốt |
| Lệnh thanh toán | Yêu cầu thu tiền dựa trên nội dung tài chính của đơn |

Snapshot tồn tại không có nghĩa là còn được dùng để tạo đơn. Quote hết hạn không có nghĩa là phải xóa snapshot lịch sử. Quote hợp lệ về giá cũng không chứng minh đã giữ được tồn kho hoặc ngân sách mã giảm giá.

Một mô hình hữu ích là:

```text
Catalog và chính sách có phiên bản
        -> tính giá
        -> snapshot bất biến
        -> quote có phạm vi và thời hạn
        -> chấp nhận quote trong transaction
        -> đơn giữ tham chiếu snapshot
        -> thanh toán và hoàn tiền theo dữ liệu đã chốt
```

Có thể lưu các thành phần này trong ít bảng hơn, nhưng cần giữ được sự khác biệt giữa dữ liệu giá bất biến và trạng thái được phép sử dụng báo giá.

## 3. Những invariant cần xác định

Giả sử hệ thống tạo quote dùng một lần cho một người mua trong một tenant. Các invariant chính là:

1. Snapshot được tạo từ dữ liệu backend có thẩm quyền, không lấy tổng tiền client gửi làm kết quả chốt.
2. Snapshot gắn với đúng tenant, người mua, nội dung giỏ và bối cảnh định giá.
3. Dữ liệu tài chính của snapshot không bị sửa sau khi tạo; tính lại giá tạo snapshot mới.
4. Quote chỉ được chấp nhận khi đúng quyền, đúng nội dung, chưa bị vô hiệu hóa và còn hiệu lực theo chính sách.
5. Một quote dùng một lần không tạo nhiều đơn vì hai request đồng thời hoặc vì đổi idempotency key.
6. Số tiền của đơn và lệnh thanh toán khớp snapshot được chấp nhận.
7. Hoàn tiền và điều chỉnh tham chiếu dữ liệu đã ghi nhận, không tự lấy giá hiện hành để thay lịch sử.
8. Việc chấp nhận quote, tạo đơn và cập nhật các quyền lợi dùng chung phải có cơ chế nhất quán phù hợp.

Các invariant có phạm vi khác nhau. Snapshot giúp giữ nguyên giá nhưng không tự chứng minh người gọi được mua cho tài khoản đó. Khóa duy nhất ngăn tạo hai đơn từ một quote nhưng không ngăn dùng giá sai tiền tệ nếu thiết kế liên kết thiếu kiểm tra.

## 4. Snapshot cần lưu những gì?

### 4.1. Không chỉ lưu một con số tổng

Một tổng `303000` không đủ để giải thích đơn. Snapshot nên lưu hoặc tham chiếu đến dữ liệu bất biến đủ để tái dựng quyết định giá:

| Nhóm | Dữ liệu điển hình |
|---|---|
| Định danh và phạm vi | Snapshot ID, tenant, người mua, đơn hoặc giỏ liên quan |
| Nội dung hàng | Dòng ổn định, sản phẩm, biến thể, người bán, số lượng và thuộc tính ảnh hưởng giá |
| Thành phần tiền | Đơn giá, giá trị dòng, giảm giá, phí, thuế, tổng cuối và phân bổ cần thiết |
| Đơn vị | Tiền tệ, đơn vị nhỏ nhất và phiên bản quy tắc đơn vị nếu cần |
| Bối cảnh | Bảng giá, nhóm giá được xác minh, vùng giao hàng, phương thức vận chuyển và điều kiện liên quan |
| Chính sách | Phiên bản cách tính giá, khuyến mãi, thuế, phí và làm tròn |
| Nguồn | Phiên bản dữ liệu giá hoặc mã báo giá từ dịch vụ định giá |
| Thời gian | Thời điểm tính, thời điểm ghi nhận; thời hạn sử dụng được quản lý ở quote |

Không nhất thiết sao chép mọi dữ liệu catalog vào snapshot. Tên hiển thị và hình ảnh có thể có yêu cầu lưu lịch sử riêng; dữ kiện ảnh hưởng tiền phải đủ ổn định để giải thích kết quả.

Nếu chỉ giữ một ID trỏ đến chính sách có thể bị ghi đè, snapshot chưa đủ tự giải thích. Cần tham chiếu phiên bản bất biến hoặc lưu các tham số thực tế đã áp dụng.

### 4.2. Ví dụ cụ thể

Giả sử đơn dùng VND với đơn vị nguyên theo cấu hình sản phẩm. Có hai dòng, giảm 10% tiền hàng, phí giao hàng 15.000 VND. Thuế trong ví dụ được cấu hình bằng 0 để tập trung vào quan hệ giá; đây không phải quy tắc thuế cho mọi giao dịch.

| Thành phần | Giá trị |
|---|---:|
| Sản phẩm A: 2 × 120.000 | 240.000 VND |
| Sản phẩm B: 1 × 80.000 | 80.000 VND |
| Tổng tiền hàng | 320.000 VND |
| Giảm giá | 32.000 VND |
| Phí giao hàng | 15.000 VND |
| Thuế theo cấu hình ví dụ | 0 VND |
| Tổng phải trả | 303.000 VND |

Snapshot minh họa dưới đây biểu diễn tiền bằng chuỗi số nguyên để các bên không chuyển qua dấu phẩy động. Các định danh được rút gọn để dễ đọc.

```json
{
  "snapshot_id": "PS-003",
  "schema_version": 1,
  "tenant_id": "TENANT-A",
  "buyer_id": "BUYER-17",
  "cart_id": "CART-81",
  "cart_version": 6,
  "currency": "VND",
  "minor_unit_scale": 0,
  "pricing_policy_version": "retail-v8",
  "promotion_policy_version": "loyalty-10-v2",
  "catalog_revision": "catalog-r417",
  "lines": [
    {
      "line_id": "L1",
      "product_id": "PRODUCT-A",
      "variant_id": "VARIANT-A1",
      "quantity": 2,
      "unit_price_minor": "120000",
      "gross_minor": "240000",
      "discount_minor": "24000",
      "net_merchandise_minor": "216000"
    },
    {
      "line_id": "L2",
      "product_id": "PRODUCT-B",
      "variant_id": "VARIANT-B1",
      "quantity": 1,
      "unit_price_minor": "80000",
      "gross_minor": "80000",
      "discount_minor": "8000",
      "net_merchandise_minor": "72000"
    }
  ],
  "totals": {
    "merchandise_minor": "320000",
    "discount_minor": "32000",
    "shipping_minor": "15000",
    "tax_minor": "0",
    "payable_minor": "303000"
  },
  "created_at": "2026-11-22T03:00:00Z"
}
```

Ví dụ lược bớt bối cảnh giao hàng và các bằng chứng chính sách chi tiết. Hệ thống thật phải lưu hoặc liên kết các dữ kiện có ảnh hưởng đến kết quả. Không cộng lại khoản thuế hoặc phí ở cấp dòng và cấp đơn nếu chúng chỉ là hai cách biểu diễn cùng một thành phần.

### 4.3. Những điều kiện số học cần kiểm chứng

Với mô hình của ví dụ:

```text
gross_i = quantity_i × unit_price_i

net_merchandise_i = gross_i - discount_i

merchandise_total = Σ gross_i
discount_total   = Σ discount_i

payable = merchandise_total - discount_total + shipping + tax
```

Các công thức phải thay đổi nếu sản phẩm có cấu trúc giá khác như giá theo bậc, giá trọn gói hoặc giá đã gồm thuế. Không ép mọi nghiệp vụ vào `quantity × unit_price` nếu đơn giá chỉ là giá hiển thị suy ra từ gói.

Giữ phép toán tiền chính xác, kiểm tra tràn số và lưu cách làm tròn, phân bổ tương ứng. Snapshot hóa một phép tính sai chỉ làm cho kết quả sai được giữ ổn định hơn.

## 5. Tạo snapshot từ một kết quả giá nhất quán

### 5.1. Không tin tổng từ client

Client có thể gửi sản phẩm, biến thể, số lượng, mã ưu đãi hoặc phương thức giao hàng. Backend phải xác minh lựa chọn và tính hoặc lấy giá từ nguồn có thẩm quyền.

Không tạo snapshot bằng cách sao chép trực tiếp JSON có `unit_price`, `discount_total` và `payable` do trình duyệt gửi. Ký hoặc lưu JSON đó không làm nguồn dữ liệu trở nên đáng tin.

Nếu client có gửi tổng đang hiển thị, có thể dùng nó để phát hiện giao diện đã cũ và trả yêu cầu xác nhận giá mới. Nó không được quyết định số tiền thu.

### 5.2. Tránh ghép dữ liệu từ nhiều thời điểm không tương thích

Một lần tính có thể đọc giá A ở phiên bản cũ, khuyến mãi ở phiên bản mới và phí vận chuyển ở một bối cảnh khác. Snapshot cần đại diện cho một kết quả tính hợp lệ, không phải một tập giá trị ngẫu nhiên được gom vào cùng bản ghi.

Trong một database, có thể dùng transaction và mức cô lập phù hợp để đọc dữ liệu nhất quán. Nếu chính sách yêu cầu các phiên bản phải khớp, vẫn cần kiểm tra chúng; mức cô lập không tự chứng minh mọi tổ hợp cấu hình đều hợp lệ về nghiệp vụ.

Với nhiều dịch vụ, transaction cục bộ không làm các nguồn bên ngoài trở thành một ảnh chụp toàn cục. Có thể dùng dịch vụ định giá trả kết quả có phiên bản, bộ dữ liệu bất biến, token phiên bản hoặc cơ chế phát hiện và thử tính lại khi nguồn thay đổi.

Cần xác định ranh giới đảm bảo: nguồn nào cam kết giá, trong thời gian nào và điều kiện nào có thể làm kết quả bị thu hồi.

### 5.3. Tạo mới thay vì sửa bản cũ

Khi giỏ hoặc chính sách cần thay đổi, tạo snapshot mới, chẳng hạn `PS-004`. Giữ `PS-003` để giải thích báo giá hoặc đơn đã dùng nó.

Không thay dòng của snapshot cũ rồi vẫn dùng cùng ID. Hành vi đó làm cho một ID không còn chỉ một nội dung tài chính và có thể khiến phê duyệt cũ áp dụng cho giá trị mới.

Quan hệ từ quote đến snapshot cũng cần ổn định. Không âm thầm thay snapshot được một quote cũ tham chiếu rồi coi đó vẫn là nội dung người dùng đã chấp nhận.

## 6. Chọn rõ cam kết giá và thời điểm chốt

### 6.1. Hai chính sách phổ biến

| Chính sách | Hành vi khi giá catalog đổi |
|---|---|
| Quote cam kết giá trong thời hạn | Nếu quote còn hợp lệ theo điều kiện đã định, dùng snapshot cũ dù giá hiện hành thay đổi |
| Giá chỉ mang tính tham khảo trước xác nhận | Khi xác nhận phải tính lại hoặc xác minh phiên bản; nếu khác, tạo báo giá mới và xử lý việc chấp nhận theo luồng sản phẩm |

Không trộn hai chính sách. Nếu đã cam kết giữ giá, không tự thay tổng bằng giá mới ở bước thanh toán chỉ vì catalog đổi. Nếu giá chưa được cam kết, không trình bày snapshot như quyền mua vô thời hạn ở giá cũ.

Một số điều kiện có thể cần kiểm tra lại, như quyền truy cập hoặc tài nguyên chưa giữ chỗ. Điều kiện nào làm mất hiệu lực quote phải được mô hình hóa rõ; một snapshot không đóng băng mọi dữ kiện bên ngoài.

### 6.2. Ví dụ giữ giá có thời hạn

Giả sử quote Q-003 trỏ đến PS-003, được dùng đến `03:10:00Z` theo chính sách giữ giá. Lúc `03:03:00Z`, đơn giá A tăng từ 120.000 lên 150.000 VND. Với cùng phép giảm và phí của ví dụ, một snapshot tính mới sẽ có tổng 357.000 VND.

Nếu người mua chấp nhận Q-003 lúc `03:04:00Z` và các điều kiện khác còn hợp lệ, chính sách giữ giá phải cho đơn dùng 303.000 VND. Việc giá mới là 357.000 VND không tự sửa nội dung PS-003.

Nếu Q-003 hết hạn trước khi chấp nhận, backend từ chối dùng nó và có thể cung cấp quote mới. Không tự chuyển sang 357.000 VND rồi thu tiền nếu luồng yêu cầu người dùng xác nhận số tiền mới.

### 6.3. Thời hạn quote khác thời hạn thanh toán đơn

Một quote có thể được chấp nhận trước khi hết hạn và tạo đơn đang chờ thanh toán. Sau đó, việc xử lý đơn tuân theo thời hạn thanh toán và state machine của đơn.

Quote hết hạn sau khi đã được chấp nhận không tự khiến tổng đơn thay đổi. Ngược lại, nếu đơn đã bị hủy hoặc quá thời hạn thanh toán, một callback thành công đến muộn cần quy trình riêng, như xác minh và hoàn tiền hoặc xử lý ngoại lệ theo chính sách.

Không xử lý tình huống đó bằng cách lấy giá catalog hiện tại để sửa số tiền của một giao dịch bên ngoài đã xảy ra.

## 7. Ràng buộc snapshot với người mua và nội dung

### 7.1. Có ID không đồng nghĩa có quyền sử dụng

Kẻ tấn công có thể thay `quote_id` hoặc `snapshot_id` bằng ID từ một phiên khác, tài khoản khác hoặc tenant khác. Backend phải kiểm tra quyền với đối tượng được tham chiếu, kể cả khi ID là UUID khó đoán.

Ngữ cảnh tenant và người mua phải được xác minh từ danh tính, quan hệ tài khoản và chính sách quyền. Nếu người dùng được mua thay cho một tổ chức, phải kiểm tra quyền đại diện; không đơn giản coi trường `buyer_id` trong JSON là danh tính thật.

Quote nên ràng buộc được các dữ kiện ảnh hưởng ý nghĩa giá, như:

- Tenant, người mua và giỏ được định giá.
- Phiên bản giỏ và nội dung hàng, biến thể, số lượng.
- Tiền tệ, bảng giá hoặc nhóm giá đã được xác minh.
- Mã ưu đãi và các điều kiện phạm vi liên quan.
- Phương thức giao hàng và dữ kiện địa điểm có ảnh hưởng phí hoặc thuế.

Không nhất thiết lưu toàn bộ địa chỉ cá nhân trong fingerprint; chỉ dùng các dữ kiện cần thiết theo chính sách và quản lý dữ liệu nhạy cảm phù hợp.

### 7.2. Fingerprint nội dung không phải tổng client gửi

Có thể dùng phiên bản giỏ hoặc fingerprint chuẩn hóa để kiểm tra nội dung không bị thay. Quy tắc chuẩn hóa cần có schema version, thứ tự dòng ổn định và đơn vị số rõ ràng.

Backend phải tạo hoặc xác minh fingerprint từ dữ liệu có thẩm quyền. Nếu client tự gửi hash của một giỏ đã sửa và backend chỉ so với một hash client khác, không có bảo vệ thực chất.

Ví dụ, đổi từ biến thể A1 giá thấp sang A2 giá cao sau khi có snapshot phải làm mất sự khớp nội dung. Chỉ kiểm tra tổng số lượng hoặc tổng tiền không phát hiện được việc thay sản phẩm.

### 7.3. Snapshot không đóng băng thẩm quyền

Một người từng được phép dùng bảng giá nội bộ có thể bị thu hồi quyền. Cần xác định chính sách với quote đã cấp: giữ cam kết trong thời hạn hay vô hiệu hóa khi quyền thay đổi.

Dù chọn cách nào, snapshot tự nó không thực thi việc thu hồi. Nếu phải vô hiệu hóa, quote cần trạng thái hoặc cơ chế kiểm tra quyền được cập nhật và đồng bộ với bước chấp nhận.

Tương tự, quyền dùng mã của khách hàng khác không trở nên hợp lệ chỉ vì khoản giảm đã xuất hiện trong một snapshot.

## 8. Chấp nhận quote một lần bằng transaction

### 8.1. Tách nội dung bất biến khỏi trạng thái sử dụng

Giả sử mô hình có:

- `price_snapshots`: dữ liệu giá bất biến cùng tenant và người mua.
- `checkout_quotes`: ràng buộc snapshot, giỏ, phiên bản, fingerprint, thời hạn và trạng thái.
- `orders`: giữ quote và snapshot đã chấp nhận cùng nội dung tài chính.

State machine quote có thể biểu diễn:

```text
OPEN -> CONSUMED
OPEN -> VOID
OPEN -> EXPIRED
```

`EXPIRED` có thể được thể hiện bằng trạng thái hoặc suy ra từ `expires_at`. Nếu job chưa kịp đổi trạng thái, một hàng còn `OPEN` vẫn phải bị từ chối khi quá hạn.

Trong ví dụ, quote dùng một lần. Những sản phẩm cố ý cho phép dùng nhiều lần cần quota và state machine khác, không bỏ điều kiện dùng một lần mà không có mô hình thay thế.

### 8.2. Kiểm tra điều kiện và tiêu thụ quote trong cùng thao tác

Đoạn SQL minh họa dùng PostgreSQL và named parameter. Giả định các cột tương ứng đã có, `context_fingerprint` được backend tính hoặc xác minh, và quyền của actor với người mua đã được kiểm tra. Với JDBC, dùng bind parameter, không nối chuỗi đầu vào.

```sql
BEGIN;

UPDATE checkout_quotes
SET state = 'CONSUMED',
    consumed_at = statement_timestamp(),
    version = version + 1
WHERE tenant_id = :verified_tenant_id
  AND buyer_id = :verified_buyer_id
  AND id = :requested_quote_id
  AND cart_id = :verified_cart_id
  AND cart_version = :verified_cart_version
  AND context_fingerprint = :verified_context_fingerprint
  AND version = :expected_quote_version
  AND state = 'OPEN'
  AND expires_at > statement_timestamp()
RETURNING snapshot_id;

-- Backend phải nhận đúng một hàng.
-- Không có hàng: ROLLBACK và dừng, không tiếp tục tạo đơn.

INSERT INTO orders (
    tenant_id,
    id,
    buyer_id,
    quote_id,
    price_snapshot_id,
    currency,
    total_minor,
    status
)
SELECT
    s.tenant_id,
    :new_order_id,
    s.buyer_id,
    :requested_quote_id,
    s.id,
    s.currency,
    s.total_minor,
    'PAYMENT_PENDING'
FROM price_snapshots AS s
WHERE s.tenant_id = :verified_tenant_id
  AND s.buyer_id = :verified_buyer_id
  AND s.id = :snapshot_id_returned_above;

-- Backend phải kiểm tra INSERT tạo đúng một đơn.
-- Ghi các dữ liệu bắt buộc, audit và outbox trước COMMIT.

COMMIT;
```

Điều khiển dừng sau mỗi câu lệnh thuộc ứng dụng; một file SQL không tự dừng chỉ vì `UPDATE RETURNING` hoặc `INSERT SELECT` trả về không hàng nào.

Ví dụ thể hiện phần nhận quote và lấy giá từ snapshot. Nó chưa bao gồm giữ tồn kho, ngân sách ưu đãi, kiểm tra mọi nguồn quyền hay schema constraint đầy đủ; các phần đó phải được phối hợp theo ranh giới nhất quán của hệ thống.

### 8.3. Định nghĩa chính xác thời điểm xét hết hạn

Ví dụ dùng `statement_timestamp()` để xét quote tại thời điểm bắt đầu câu lệnh tiêu thụ quote. Trong PostgreSQL, `CURRENT_TIMESTAMP` thể hiện thời điểm bắt đầu transaction, nên có thể không phù hợp nếu transaction mở lâu trước bước chấp nhận.

Chính sách ở đây cho phép một quote được chấp nhận tại bước đó, rồi transaction hoàn tất sau. Không khẳng định quote phải còn hiệu lực đến từng thời điểm sau hoặc đúng lúc commit.

Nếu sản phẩm cần điều kiện thời gian khác, phải thiết kế lại điểm kiểm tra và xử lý chờ khóa tương ứng. Cần dùng đồng hồ tin cậy phía server/database, không dùng timestamp client khai báo để kéo dài thời hạn.

### 8.4. Constraint và rollback

Nên có ràng buộc duy nhất như `UNIQUE (tenant_id, quote_id)` trên đơn trong mô hình quote dùng một lần. Khóa ngoại và các khóa ghép cần bảo vệ việc đơn, quote và snapshot có cùng tenant, người mua và quan hệ tham chiếu đã định.

Ví dụ có thể dùng khóa tham chiếu ghép để bảo đảm cặp quote/snapshot trên đơn đúng là cặp đã được cấp, thay vì chỉ chứng minh hai ID tồn tại độc lập. Quyền actor vẫn phải được kiểm tra riêng.

Nếu bước tạo đơn hoặc ghi dữ liệu bắt buộc thất bại, rollback toàn transaction phải trả thao tác tiêu thụ quote về trạng thái trước đó. Không commit quote đã tiêu thụ rồi mới tạo đơn ở một transaction không có cơ chế phục hồi.

Sau khi đã commit thành công, không tự đổi quote về `OPEN` chỉ vì thanh toán chưa xong. Khi cần thử lại hoặc hủy, phải theo state machine của đơn và các giữ chỗ liên quan.

### 8.5. Idempotency và quote dùng một lần bổ sung cho nhau

Idempotency key nhận diện retry của cùng hành động tạo đơn. Quote dùng một lần ngăn nhiều hành động khác nhau cùng dùng lại một báo giá chỉ dành cho một đơn.

Luồng đầy đủ cần nhận diện idempotency trước khi coi một quote đã tiêu thụ là lỗi. Nếu request đầu đã commit nhưng phản hồi bị mất, retry đúng key và nội dung phải quy về đơn đã tạo, sau khi kiểm tra quyền đọc kết quả.

Cùng key nhưng khác quote hoặc nội dung nghiệp vụ phải bị từ chối theo hợp đồng. Đổi key không được tạo đơn thứ hai từ quote đã dùng. Bản ghi idempotency, đơn và việc tiêu thụ quote cần có cơ chế ghi nhất quán.

## 9. Thanh toán và hoàn tiền theo số đã chốt

### 9.1. Lệnh thanh toán lấy từ đơn

Sau khi tạo đơn, worker hoặc API thanh toán phải lấy tiền tệ và số tiền từ nội dung tài chính đã chốt của đơn. Không đọc lại giá hiện hành của sản phẩm để tính số gửi cổng thanh toán.

Với ví dụ, lệnh thanh toán cho đơn từ PS-003 là 303.000 VND, dù catalog đã thay đổi. Lệnh cần mã nghiệp vụ ổn định và cơ chế chống trùng phù hợp với nhà cung cấp.

Nếu API phía client gửi `amount` khi mở thanh toán, backend phải bỏ qua vai trò quyết định giá của trường đó hoặc so khớp như một điều kiện phát hiện giao diện cũ. Trường này không được ghi đè tổng đơn.

Với đơn hợp lệ có tổng bằng 0, cần luồng hoàn tất riêng theo chính sách và vẫn kiểm tra quyền, ưu đãi, tồn kho, trạng thái, idempotency. Không mặc định cổng thanh toán chấp nhận khoản 0.

### 9.2. Đối chiếu callback với nội dung đã chốt

Webhook hoặc kết quả truy vấn phải được xác minh nguồn và liên kết đến đúng giao dịch, tài khoản nhà cung cấp và đơn. So khớp số tiền, tiền tệ theo đúng đơn vị API của nhà cung cấp.

Không đánh dấu đã thanh toán chỉ vì callback có cùng `order_id`. Số tiền thiếu, tiền tệ khác hoặc tham chiếu không đúng phải đi qua quy trình xử lý sai lệch.

Webhook trùng hoặc sự kiện đến muộn không được ghi nhận tài chính lần hai hay làm trạng thái lùi trái quy tắc. Snapshot ổn định giúp có số tiền để đối chiếu, nhưng không tự thực hiện chống trùng thông điệp.

### 9.3. Hoàn tiền cần số thực thu và phân bổ gốc

Snapshot giúp biết giá, giảm giá và phân bổ tại thời điểm đơn được chốt. Tuy nhiên, số được hoàn còn phụ thuộc khoản đã thực thu, các lần hoàn trước, trạng thái và chính sách hoàn.

Không tính hoàn bằng giá hiện tại của sản phẩm. Nếu phần tiền sau giảm đã được phân bổ về dòng, dùng dữ liệu lịch sử đó theo chính sách thay vì tính lại phần trăm rồi làm tròn độc lập.

Cần bảo vệ tổng hoàn thành công cộng phần đang giữ hạn mức không vượt số được phép hoàn, kể cả khi có nhiều request đồng thời. Việc snapshot bất biến không tự ngăn hoàn hai lần cùng một khoản.

### 9.4. Điều chỉnh tạo bản ghi mới

Nếu cần thay đổi giá sau khi đơn đã chốt, dùng quy trình điều chỉnh, sửa đơn có phiên bản, phụ thu hoặc hoàn tiền tương ứng với sản phẩm. Ghi mối liên hệ đến snapshot và hiệu lực tiền gốc.

Không sửa PS-003 thành một tổng mới rồi giữ nguyên mọi tham chiếu thanh toán. Khi đó, lịch sử sẽ không còn giải thích số đã thu và nội dung đã được chấp nhận.

## 10. Bảo vệ snapshot khỏi sửa đổi và phát lại

### 10.1. Snapshot lưu ở server

Với snapshot trong database, hạn chế cập nhật hoặc xóa nội dung tài chính qua tài khoản runtime. Mọi đường ghi như import, job nền và công cụ quản trị phải tuân theo quy tắc tạo bản mới.

Một cột hash có thể giúp phát hiện dữ liệu thay đổi ngoài dự kiến khi có mốc kiểm chứng đáng tin cậy. Nếu kẻ tấn công có thể sửa cả nội dung và hash, hash không tự tạo bảo vệ chống sửa.

Cần tách quyền quản trị, theo dõi điều chỉnh và lưu audit đủ để liên kết snapshot với người yêu cầu, chính sách, quote, đơn và giao dịch tiền.

### 10.2. Snapshot hoặc quote mang theo ở client

Nếu hệ thống trả một token chứa dữ liệu báo giá để client mang lại, token cần được xác minh tính toàn vẹn và nguồn phát bằng giao thức đã thiết kế, như chữ ký hoặc MAC phù hợp.

Nội dung cần ràng buộc đúng phạm vi: người mua, tenant, nội dung giỏ, tiền tệ, chính sách, thời hạn, mục đích sử dụng và định danh chống phát lại theo mô hình. Cần chuẩn hóa dữ liệu ký, quản lý phiên bản và khóa xác minh.

Chữ ký không tự bảo đảm:

- Người gọi hiện tại có quyền dùng token đó.
- Quote chưa bị thu hồi hoặc tiêu thụ.
- Tồn kho hoặc ngân sách đã được giữ.
- Một token chưa bị phát lại đồng thời để tạo hai đơn.
- Dữ liệu bên trong được giữ bí mật.

Một token hợp lệ về chữ ký vẫn có thể hết hạn, sai người dùng hoặc đã dùng. Nếu quote chỉ được dùng một lần, cần cơ chế trạng thái hoặc ghi nhận tiêu thụ có tính nhất quán; chỉ kiểm tra chữ ký ở từng request là chưa đủ.

### 10.3. Không dùng snapshot làm kho bí mật

Snapshot có thể chứa giá nội bộ, nhóm khách hàng hoặc điều kiện thương mại nhạy cảm. Chỉ trả về các trường người dùng được phép xem; bản nội bộ và bản hiển thị có thể khác nhau.

Không đưa access token, thông tin thanh toán bí mật hoặc toàn bộ dữ liệu cá nhân vào snapshot chỉ để tiện truy vết. Tham chiếu dữ liệu và lưu bằng chứng theo đúng nhu cầu, quyền truy cập và chính sách lưu giữ.

## 11. Xử lý lỗi và audit có ý nghĩa

Khi quote không dùng được, backend cần phân biệt nguyên nhân nội bộ như hết hạn, thay đổi nội dung, đã tiêu thụ, bị vô hiệu hóa hoặc sai quyền. Phản hồi cho client phải tuân theo chính sách không làm lộ tài nguyên ngoài quyền.

Ví dụ một phản hồi tổng quát cho báo giá cần tính lại:

```json
{
  "code": "QUOTE_NOT_USABLE",
  "message": "Báo giá không còn phù hợp. Vui lòng xác nhận báo giá mới."
}
```

Không trả báo giá mới chứa dữ liệu của người mua khác chỉ vì client biết một quote ID. Retry của request đã tạo đơn thành công cần trả về kết quả idempotency hợp lệ, thay vì luôn biến thành lỗi “đã dùng”.

Audit nên ghi các sự kiện riêng biệt như tạo snapshot, cấp quote, chấp nhận quote, từ chối vì nội dung thay đổi và tạo lệnh thanh toán. Không ghi `PAYMENT_SUCCEEDED` ngay khi chỉ mới chốt giá.

Các dữ kiện hữu ích gồm snapshot ID, quote ID, đơn, tenant, actor, phiên bản giỏ, phiên bản chính sách, số tiền chuẩn và lý do chuyển trạng thái. Ghi bằng chứng thành công bắt buộc cùng cơ chế nhất quán với hành động nghiệp vụ; nếu transaction rollback, không mô tả nó là đã chấp nhận.

Theo dõi các mẫu đáng ngờ như thử nhiều quote ID, liên tục dùng quote hết hạn hoặc đổi nội dung sau khi được giá ưu đãi. Audit hỗ trợ phát hiện, còn quyền và invariant vẫn phải chặn tác dụng ngay tại bước ghi.

## 12. Kiểm thử theo tình huống tấn công logic

### 12.1. Ma trận quyền, nội dung và giá

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Sửa `payable` hoặc `unit_price` trong request | Không thay đổi giá có thẩm quyền ở backend |
| Dùng snapshot hoặc quote của người mua khác | Bị kiểm tra quyền và phạm vi |
| Dùng quote ở tenant khác | Không tạo đơn chéo tenant |
| Đổi biến thể, sản phẩm hoặc số lượng sau định giá | Không chấp nhận như nội dung cũ |
| Đổi vùng giao hàng hoặc phương thức ảnh hưởng giá | Được kiểm tra theo binding và chính sách |
| Dùng đúng tổng nhưng thay món hàng | Vẫn phát hiện khác nội dung |
| Catalog đổi khi quote giữ giá còn hợp lệ | Đơn dùng snapshot theo cam kết, không tự đổi tổng |
| Catalog đổi với giá chỉ tham khảo | Tính lại hoặc xác minh và xử lý chấp nhận giá mới theo chính sách |
| Quote hết hạn nhưng hàng vẫn ghi `OPEN` | Bị điều kiện thời gian chặn |
| Thay policy hoặc sửa bảng giá lịch sử | Đơn cũ vẫn giải thích được bằng dữ liệu bất biến |
| Token bị sửa hoặc sai mục đích | Không được xác minh và áp dụng như quote hợp lệ |
| Token đúng chữ ký nhưng đã dùng | Không được tạo thêm đơn trong mô hình dùng một lần |

### 12.2. Kiểm thử race condition và retry

Các kịch bản quan trọng gồm:

1. Hai request khác key cùng tiêu thụ một quote: tối đa một đơn được tạo.
2. Hai request cùng key và cùng nội dung: quy về cùng hiệu lực nghiệp vụ.
3. Request đầu commit nhưng mất phản hồi: retry lấy đúng đơn cũ và không tiêu quyền lợi lần nữa.
4. Bước tạo đơn hoặc audit bắt buộc thất bại sau thao tác tiêu thụ: rollback không để quote bị dùng dở.
5. Quote bị vô hiệu hóa đồng thời với chấp nhận: kết quả tuân theo giao thức khóa, phiên bản và thời điểm quyền đã chọn.
6. Giỏ đổi đồng thời: không ghép snapshot cũ với dòng hàng mới.
7. Hai đơn cạnh tranh tồn kho hoặc ngân sách mã: quote hợp lệ không làm vượt tài nguyên chưa được giữ.
8. Quote hết hạn gần bước chấp nhận: kết quả đúng theo định nghĩa thời điểm xét hạn, kể cả khi phải chờ khóa.

Dùng hai kết nối và điểm đồng bộ để điều khiển lịch thực thi thay vì chỉ thêm thời gian ngủ. Kiểm tra cả dữ liệu cuối sau commit và các giữ chỗ, bản ghi idempotency, outbox liên quan.

### 12.3. Kiểm thử luồng tài chính sau đó

- Lệnh thanh toán lấy đúng số tiền và tiền tệ đã chốt, dù catalog đổi.
- Webhook sai số tiền hoặc tiền tệ không được coi là thanh toán hợp lệ chỉ nhờ đúng order ID.
- Webhook trùng không tạo hiệu lực tiền lặp.
- Thanh toán đến muộn cho đơn đã hết hạn được xử lý theo state machine riêng.
- Hoàn một phần dùng dữ liệu và giới hạn lịch sử phù hợp, không lấy giá hiện hành.
- Đơn tổng 0 vẫn không bỏ qua quyền, ưu đãi, tồn kho hoặc chống trùng.

### 12.4. Thuộc tính có thể kiểm tra trên nhiều dữ liệu

```text
Đơn đã chấp nhận -> snapshot tham chiếu tồn tại và đúng phạm vi.

Cùng snapshot bất biến -> cùng nội dung tài chính đã chốt.

Giá catalog thay đổi -> không làm đổi dữ liệu snapshot cũ.

Quote dùng một lần -> không có hai đơn commit từ cùng quote.

Số tiền yêu cầu thanh toán = số tiền đã chốt của đơn, theo đúng đơn vị.

Mọi điều chỉnh sau chốt -> có bản ghi liên kết và bằng chứng riêng.
```

Các thuộc tính phải phản ánh chính sách thực tế. Không đặt điều kiện “snapshot luôn còn được dùng” hoặc “quote luôn giữ được hàng”, vì chúng vượt quá trách nhiệm của bản ghi giá.

## 13. Những quyết định cần chốt trước khi triển khai

- Snapshot được tạo từ nguồn giá nào và kết quả có nhất quán về phiên bản không?
- Quote cam kết giá hay chỉ mang tính tham khảo, và điều kiện nào có thể vô hiệu hóa nó?
- Giá được chốt ở bước nào, thời hạn quote được xét tại thời điểm nào?
- Snapshot gắn với người mua, nội dung giỏ và bối cảnh phí/thuế thế nào?
- Cách tiêu thụ quote, tạo đơn và giữ quyền lợi có an toàn khi chạy đồng thời không?
- Retry có trả lại cùng đơn mà vẫn kiểm tra đúng quyền không?
- Thanh toán, hoàn tiền và audit có cùng tham chiếu dữ liệu đã chốt không?
- Điều chỉnh tạo phiên bản và hiệu lực mới hay đang sửa mất lịch sử?

Một price snapshot có giá trị bảo mật khi nó là bằng chứng ổn định về nội dung tài chính đã được xác định, đồng thời được sử dụng trong một quy trình có kiểm soát quyền và trạng thái. Khi đó, thay đổi giá, sửa payload hay retry không thể tùy tiện biến nội dung được chấp nhận thành một giao dịch tiền khác.
