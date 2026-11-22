# Đơn hàng: bản chụp dữ liệu, trạng thái và ranh giới giao dịch

Một đơn hàng là lời cam kết tại **một thời điểm cụ thể**: khách đã chọn những sản phẩm nào, với số lượng bao nhiêu, giá và chương trình ưu đãi nào, giao đến đâu, điều kiện vận chuyển ra sao và sau đó đơn đã đi qua những trạng thái gì. Nếu ứng dụng chỉ lưu `productId`, `quantity` rồi mỗi lần hiển thị lại truy vấn thông tin sản phẩm hiện hành, hóa đơn của hôm qua có thể thay đổi khi người bán sửa tên, giá hoặc thuế hôm nay. Nếu hai tiến trình đồng thời đánh dấu đơn là `PAID` và `CANCELLED` mà không kiểm tra trạng thái trước đó, hệ thống có thể vừa hoàn tiền vừa giao hàng.

MongoDB document model rất phù hợp để **đóng gói những dữ liệu cùng thay đổi và cần được đọc như một đơn vị**, nhưng không có nghĩa phải đưa *mọi thứ* liên quan đơn hàng vào một document. Danh mục sản phẩm, tồn kho chung, giao dịch thanh toán từ cổng thanh toán, sổ cái kế toán, nhật ký tích hợp và luồng giao hàng đều có vòng đời và ranh giới nhất quán riêng.

Bài học **“Đơn hàng: bản chụp dữ liệu, trạng thái và ranh giới giao dịch”** thuộc chương **Thiết kế ứng dụng** của module **Database Engine Document MongoDB** sẽ xây dựng mô hình đơn hàng có khả năng giải thích lịch sử, chịu được yêu cầu đồng thời, phục hồi sau lỗi và tích hợp hệ thống bên ngoài một cách có kiểm soát.

Ba quyết định thiết kế quan trọng nhất:

1. **Snapshot gì, tham chiếu gì?** Những thông tin dùng để xác định cam kết thương mại của đơn cần giữ ở thời điểm chốt đơn; những thực thể có vòng đời độc lập thường được tham chiếu.
2. **Trạng thái thay đổi ra sao?** Không chỉ dùng một field `status` có thể bị ghi tùy ý; cần state machine, điều kiện chuyển trạng thái, version và audit.
3. **Ranh giới giao dịch nằm ở đâu?** Một update trên một MongoDB document là nguyên tử trong phạm vi document đó; nhiều documents cần transaction khi thật sự có invariant xuyên documents; cổng thanh toán và dịch vụ vận chuyển bên ngoài **không nằm trong transaction MongoDB**.

> **Quy tắc cốt lõi:** Đơn hàng đã chốt không được âm thầm thay đổi ý nghĩa vì catalog hoặc bảng giá thay đổi. Một trạng thái được công bố phải tương ứng với bằng chứng nghiệp vụ thật. Và một yêu cầu có thể retry phải tránh tạo thêm đơn, thu tiền hoặc trừ kho lần thứ hai.

---

## 1. Đơn hàng là aggregate nghiệp vụ, không chỉ là một bảng ghi

Một đơn hàng thường đi qua các pha:

```text
Giỏ hàng
    │
    ▼
Tạo đơn / chốt giá
    │
    ▼
Giữ chỗ hàng / xác nhận khả năng cung cấp
    │
    ▼
Thanh toán / xác nhận phương thức trả
    │
    ▼
Chuẩn bị hàng
    │
    ▼
Giao cho đơn vị vận chuyển
    │
    ▼
Hoàn tất / hủy / hoàn tiền / khiếu nại
```

Những bước này không có cùng chủ sở hữu và không hoàn thành cùng lúc. Một đơn hàng vì vậy cần cả:

- **Dữ liệu cam kết lúc chốt**: mặt hàng, mức giá, số lượng, thuế, ưu đãi, phí vận chuyển.
- **Trạng thái hiện tại**: đang chờ thanh toán, đã thanh toán, đã giao, đã hủy...
- **Dấu vết trạng thái**: ai, khi nào, bởi sự kiện nào và với kết quả gì.
- **Các định danh tham chiếu**: khách hàng, sản phẩm, warehouse, payment intent, shipments.
- **Phiên bản và tính đồng thời**: không để command cũ ghi đè trạng thái mới.
- **Ranh giới nhất quán**: những thay đổi phải cùng thành công, những thay đổi chỉ có thể phối hợp theo workflow.

### 1.1. Aggregate không đồng nghĩa một document chứa mọi thứ

Trong domain-driven design, một *aggregate* là ranh giới các quy tắc nhất quán. MongoDB có thể lưu các phần lớn của aggregate trong một document để tận dụng single-document atomicity, nhưng một đơn hàng gắn với nhiều thực thể như inventory, payment ledger và fulfillment không tự biến tất cả thành một transaction nhỏ.

### 1.2. Phân biệt các nguồn sự thật

| Dữ liệu | Nguồn sự thật đề xuất |
|---|---|
| Tên và mô tả sản phẩm hiện hành | Product catalog |
| Giá khách đã chấp nhận | Snapshot trong đơn |
| Tổng tiền đã xác định của đơn | Order pricing snapshot |
| Số lượng tồn kho khả dụng | Inventory service/collection |
| Khoản tiền đã capture/refund thực tế | Payment provider và payment/ledger records đối soát |
| Tiến độ vận chuyển thực tế | Shipping/fulfillment service |
| Trạng thái tổng hợp phục vụ người dùng | Order projection có bằng chứng |
| Log sự kiện đồng bộ/liên dịch vụ | Outbox/events với retention riêng |

Một `order.paymentStatus = "PAID"` không đủ làm bằng chứng tiền thực sự đã được cổng thanh toán capture nếu không có record giao dịch đối chiếu.

## 2. Bài toán ví dụ: hệ thống bán hàng đa tenant

Giả sử ứng dụng phục vụ nhiều cửa hàng (*tenants*). Mỗi tenant có:

- Sản phẩm và bảng giá riêng;
- Đơn hàng mang định danh riêng;
- Kho hàng ở nhiều vị trí;
- Phương thức thanh toán đa dạng;
- Có thể đổi tên/ảnh/giá sản phẩm theo thời gian.

Một order `ORD-2026-001` của tenant `TENANT-A` gồm hai dòng hàng, được thanh toán bằng cổng ngoài và có thể giao thành hai kiện.

Yêu cầu nghiệp vụ:

1. Khi đã chốt đơn, không sửa giá lịch sử vì catalog thay đổi.
2. Không tạo hai đơn cho một yêu cầu checkout được retry.
3. Không bán vượt tồn kho theo chính sách giữ chỗ.
4. Không chuyển `CANCELLED` sang `SHIPPED` do callback đến muộn.
5. Có thể đối soát số tiền, số lượng và luồng hoàn tiền.
6. Có thể phục hồi job bị crash giữa việc ghi DB và gọi dịch vụ ngoài.
7. Đọc trang lịch sử đơn nhanh mà không phải join lại toàn catalog.

## 3. Chọn ranh giới document

Một thiết kế phổ biến:

```text
orders
  └── Một document mỗi đơn
        ├── Order identity
        ├── Order lines (snapshots)
        ├── Totals and currency
        ├── Checkout snapshot
        ├── Current status + revision
        └── Small state summary

inventory
  └── Tồn kho theo SKU/warehouse

stock_reservations
  └── Reservation theo order/line/warehouse

payment_attempts
  └── Một hoặc nhiều thử thanh toán

payment_ledger
  └── Giao dịch thu/hoàn tiền, ưu tiên append-only

shipments
  └── Một hoặc nhiều kiện vận chuyển

outbox_events
  └── Sự kiện cần phát ra hệ ngoài
```

Những trường có cùng vòng đời và thường được đọc/ghi cùng nhau rất đáng **embed** trong `orders`. Những đối tượng có nhiều lần cập nhật, có quyền sở hữu độc lập, có thể tăng không giới hạn hoặc cần truy vấn xuyên nhiều đơn thường nên **reference**.

### 3.1. Embed `orderLines` vì sao phù hợp?

Phần lớn đơn có số dòng hàng nhỏ và hữu hạn. Khi đọc chi tiết đơn, người dùng cần tất cả dòng hàng ngay lập tức. Việc giữ `items` trong document đơn giúp đọc nhất quán trong một lần và cho phép cập nhật đơn nguyên tử trong phạm vi document.

### 3.2. Không embed toàn bộ catalog product

Một sản phẩm xuất hiện trong hàng triệu orders. Việc nhúng **toàn bộ product record và các dữ liệu vận hành hiện tại** làm document phình, chứa thông tin không cần thiết và khiến định nghĩa snapshot mơ hồ. Chỉ lưu những field xác định cam kết và hiển thị lịch sử.

### 3.3. Không embed payment event history vô hạn

Một order có thể nhận nhiều lần retry, webhook, ủy quyền thanh toán, capture và refund. Nếu append tất cả raw events vào `orders.events`, document có thể tăng vô hạn, chạm giới hạn BSON document và trở thành hotspot ghi. Sử dụng collection sự kiện/payment records riêng, chỉ giữ summary nhỏ trên order.

## 4. Document đơn hàng tham khảo

Ví dụ dữ liệu giả:

```javascript
{
  _id: "ORD-2026-001",
  tenantId: "TENANT-A",
  customerId: "CUS-102",

  orderNo: "2026-001",
  idempotencyKey: "checkout-8d2f...",
  schemaVersion: 3,
  revision: NumberLong("8"),

  placedAt: ISODate("2026-11-14T04:15:00Z"),
  currency: "VND",

  items: [
    {
      lineId: "L1",
      productId: "PROD-101",
      sku: "SHIRT-BLUE-M",
      snapshot: {
        name: "Áo sơ mi xanh size M",
        variantLabel: "Xanh / M",
        sellerName: "Cửa hàng A",
        catalogVersion: NumberLong("15")
      },
      quantity: NumberInt(2),
      unitPriceMinor: NumberLong("250000"),
      discountMinor: NumberLong("20000"),
      taxMinor: NumberLong("0"),
      lineTotalMinor: NumberLong("480000")
    },
    {
      lineId: "L2",
      productId: "PROD-202",
      sku: "CAP-BLACK",
      snapshot: {
        name: "Mũ đen",
        variantLabel: "Đen",
        sellerName: "Cửa hàng A",
        catalogVersion: NumberLong("3")
      },
      quantity: NumberInt(1),
      unitPriceMinor: NumberLong("150000"),
      discountMinor: NumberLong("0"),
      taxMinor: NumberLong("0"),
      lineTotalMinor: NumberLong("150000")
    }
  ],

  pricing: {
    itemsSubtotalMinor: NumberLong("650000"),
    discountsMinor: NumberLong("20000"),
    shippingMinor: NumberLong("30000"),
    taxMinor: NumberLong("0"),
    grandTotalMinor: NumberLong("660000"),
    pricingRuleVersion: "pricing-v7",
    calculatedAt: ISODate("2026-11-14T04:14:58Z")
  },

  deliverySnapshot: {
    recipientName: "Người nhận thử nghiệm",
    addressLine: "Địa chỉ đã ẩn danh",
    city: "Thành phố mẫu",
    countryCode: "VN",
    serviceCode: "STANDARD"
  },

  status: "PAID",
  paymentStatus: "CAPTURED",
  fulfillmentStatus: "NOT_STARTED",

  payment: {
    provider: "provider-x",
    paymentIntentId: "PAY-INTENT-001",
    capturedMinor: NumberLong("660000")
  },

  createdAt: ISODate("2026-11-14T04:15:00Z"),
  updatedAt: ISODate("2026-11-14T04:20:00Z")
}
```

Giá trị minh họa: `2 × 250000 + 150000 = 650000`; giảm giá `20000`, phí ship `30000`, thành tiền `660000` đơn vị nhỏ. Với VND, ứng dụng phải công bố quy ước lưu tiền và rounding; không tự hiểu hậu tố `Minor` có nghĩa “cent” của mọi tiền tệ.

### 4.1. `_id` có cần là ObjectId?

Không bắt buộc. Một hệ có thể dùng `ObjectId`, UUID BSON chuẩn, String order ID hoặc compound identity. Quan trọng là:

- Duy nhất theo quy tắc business;
- Tạo được ổn định khi retry;
- Không lộ thông tin nhạy cảm;
- Hỗ trợ shard key/index strategy;
- Dễ liên kết hệ payment/fulfillment.

### 4.2. `tenantId` không thể được xem là một field trang trí

Mọi query và write trong shared collection cần giữ tenant scope, trừ admin operation được cho phép. Kiểm tra authorization tại service boundary; chỉ có index chứa tenant không tự bảo vệ dữ liệu xuyên tenant.

## 5. Snapshot tại thời điểm đặt hàng là gì?

**Snapshot** là những thông tin thể hiện điều mà khách và người bán đã đồng ý tại thời điểm giao kết. Nó khác với *cache* của product hiện tại.

Ví dụ:

```text
Ngày 14/11:
  Áo tên "Áo sơ mi xanh"
  Giá 250000 VND
  Khách đặt 2 chiếc

Ngày 15/11:
  Seller đổi tên thành "Sơ mi premium"
  Giá niêm yết thành 320000 VND
```

Hóa đơn đơn cũ vẫn phải hiển thị tên/giá đã chấp nhận theo quy định nghiệp vụ, không hiển thị lại giá 320000 rồi tính lại tổng.

### 5.1. Những field thường nên snapshot

| Nhóm | Field ví dụ | Lý do |
|---|---|---|
| Product identity | Product ID, SKU, variant IDs | Truy vết |
| Display | Tên, biến thể, nhãn seller | Hiển thị lịch sử |
| Commercial | Unit price, discounts, tax, currency | Bằng chứng tiền |
| Fulfillment | Dịch vụ ship, phí, địa chỉ giao khi chốt | Giao hàng/đối soát |
| Rule references | Pricing/tax/promotion rule version | Giải thích phép tính |
| Contract | Terms/policy version hoặc hash khi cần | Kiểm toán |
| Timestamp | Thời điểm chốt theo UTC | Truy vết theo thời gian |

### 5.2. Những field thường giữ reference thay vì snapshot toàn phần

- Inventory hiện có;
- Giá hiện tại phục vụ mua mới;
- Các tùy chọn vận chuyển đang mở;
- Rating/review sản phẩm;
- Full customer profile;
- Payment provider secret/token;
- Raw webhook payload không giới hạn;
- Vòng đời shipment;
- Nhiều tập lịch sử event dài.

### 5.3. Snapshot không có nghĩa không bao giờ chỉnh sửa theo bất kỳ tình huống nào

Có trường hợp cần sửa **địa chỉ giao hàng sau khi đặt**, nhưng phải phân biệt:

- `deliverySnapshot` ban đầu;
- `deliveryCurrent` hoặc shipment destination đã được phê duyệt;
- Audit ai yêu cầu thay đổi, điều kiện được phép, thời điểm;
- Tác động phí ship/tax nếu có.

Không âm thầm ghi đè địa chỉ gốc và mất dấu cam kết trước đó.

## 6. `productId` là reference, snapshot là bằng chứng lịch sử

Một dòng hàng có thể lưu đồng thời:

```javascript
{
  productId: "PROD-101",
  sku: "SHIRT-BLUE-M",
  snapshot: {
    name: "Áo sơ mi xanh size M",
    unit: "piece",
    sellerName: "Shop A"
  },
  unitPriceMinor: NumberLong("250000")
}
```

`productId` cho phép liên kết lại catalog khi xem chi tiết hiện hành. `snapshot` giúp hiển thị lịch sử ngay cả khi product bị ẩn, đổi tên hoặc ngừng bán.

### 6.1. Nếu catalog đã xóa sản phẩm?

Order vẫn phải trả được những thông tin tối thiểu cần cho giao dịch/đối soát theo retention policy. UI có thể hiển thị “sản phẩm không còn bán” kèm tên snapshot.

### 6.2. Snapshot càng lớn càng tốt?

Không. Lưu quá nhiều dữ liệu sản phẩm tạo chi phí storage và tăng PII/IP exposure. Chọn field dựa trên điều cần chứng minh theo hợp đồng và vận hành, tránh copy mô tả HTML dài, hình ảnh nhị phân, secret nội bộ hoặc inventory metadata không cần thiết.

### 6.3. Nếu tên/mô tả vi phạm chính sách?

Có thể cần hide/redact hiển thị theo policy, trong khi record giao dịch cần được giữ theo cơ chế audit được bảo vệ. Tách nguyên tắc bảo toàn chứng cứ với việc phát nội dung ra UI.

## 7. Chụp giá tại đúng thời điểm và tránh TOCTOU

Một lỗi **time-of-check to time-of-use**:

```text
T1 API đọc giá hiện tại = 250000
T2 Seller đổi giá = 270000
T3 API tạo order nhưng lại lấy giá sản phẩm lần nữa
T4 Client được báo tổng khác lúc xác nhận
```

Một flow tốt:

```text
User chọn cart
      │
      ▼
Quote pricing v7 (có quoteId và expiry)
      │
      ▼
User xác nhận quote
      │
      ▼
Server xác minh quote còn hợp lệ
      │
      ▼
Create order with exact accepted snapshot
```

Quote có thể gắn với:

- Product/variant IDs;
- Quantities;
- Currency;
- Unit prices;
- Discounts;
- Tax/shipping;
- Expiration;
- Rule/version;
- Customer/tenant scope;
- Hash/signature hoặc server-stored immutable quote.

### 7.1. Không tin giá do frontend tự gửi

Frontend có thể gửi `unitPrice=1` bằng cách sửa request. Backend phải tính/kiểm chứng giá từ nguồn có thẩm quyền hoặc quote đã được server phát hành và ràng buộc identity/expiry.

### 7.2. Quote hết hạn phải làm gì?

Có thể yêu cầu tính lại và khách xác nhận giá mới. Không tự đổi tổng tiền sau khi người dùng bấm xác nhận mà không có quy tắc cho phép.

## 8. Tiền tệ, scale và độ chính xác

Hai mô hình phổ biến:

1. **Minor units với Int64:** `amountMinor: NumberLong("660000")`, cùng `currency`.
2. **Decimal128:** `amount: NumberDecimal("660000.00")`, cùng currency/scale policy.

Không dùng `double` cho số tiền cần chính xác theo decimal nếu không có chính sách rounding và kiểm chứng.

### 8.1. Minor units có nghĩa gì?

“Đơn vị nhỏ nhất” phụ thuộc currency. USD thường có đơn vị nhỏ cent; VND thường tính nguyên đồng trong hệ bán lẻ; có loại tiền có quy tắc khác. Hệ thống nên có quy định:

```text
currency = "VND"
amountMinor = 660000
scale = theo currency/config đã version hóa
```

Tránh cố định “mọi loại tiền đều có 2 chữ số thập phân”.

### 8.2. Không cộng tiền khác currency

```text
500000 VND + 20 USD
```

không phải tổng tiền hợp lệ. Nếu checkout đa currency, cần exchange-rate snapshot, currency conversion rule, rounding, rate source và audit.

### 8.3. Mọi phép tính phải có invariant

Ví dụ:

```text
itemsSubtotal = Σ(quantity × unitPrice)
discountsTotal = tổng discount áp dụng
taxTotal = tổng thuế theo quy tắc
shipping = phí vận chuyển đã chốt
grandTotal = itemsSubtotal - discountsTotal + taxTotal + shipping
```

Kiểm tra:

- Không âm ngoài trường hợp credit/refund có model riêng;
- Không overflow Int64;
- Currency thống nhất;
- Rounding đúng quy tắc;
- Discounts không vượt phạm vi;
- Tổng mỗi line và tổng order khớp.

### 8.4. Unit tests cho tổng tiền

```text
2 × 250000 = 500000
1 × 150000 = 150000
Subtotal = 650000
Discount = 20000
Shipping = 30000
Tax = 0
Grand total = 660000
```

Đơn giá sau chốt phải được đọc từ snapshot khi tính lại kiểm toán, không từ catalog hiện hành.

## 9. Thuế, ưu đãi và phí vận chuyển phải có phiên bản

Thuế, khuyến mãi và shipping rates có thể thay đổi theo thời gian.

Cần snapshot những đầu vào/đầu ra có ý nghĩa:

```javascript
pricing: {
  couponCode: "WELCOME",
  promotionRuleId: "PROMO-77",
  promotionRuleVersion: "v4",
  taxPolicyVersion: "tax-2026-11",
  shippingQuoteId: "SHIP-Q-919",
  itemsSubtotalMinor: NumberLong("650000"),
  discountsMinor: NumberLong("20000"),
  taxMinor: NumberLong("0"),
  shippingMinor: NumberLong("30000"),
  grandTotalMinor: NumberLong("660000")
}
```

### 9.1. Lưu `couponCode` có đủ không?

Không. Nếu chương trình khuyến mại hôm nay đổi từ 10% xuống 5%, truy vấn lại coupon hiện tại không thể tái dựng chính xác lý do giảm giá lịch sử. Lưu kết quả/phiên bản đã áp dụng và những dữ liệu kiểm toán cần thiết.

### 9.2. Phân bổ discount theo line

Khi hủy/hoàn một phần, cần biết giảm giá phân bổ cho từng line thế nào. Nếu chỉ lưu `discountTotal`, việc hoàn 1 trong 2 sản phẩm có thể thiếu dữ liệu để tính refund đúng.

### 9.3. Thuế theo jurisdiction

Địa chỉ, quốc gia, loại hàng và thời điểm có thể ảnh hưởng thuế. Không thay đổi thuế của đơn cũ khi tax config mới được triển khai, trừ khi có nghiệp vụ điều chỉnh với audit riêng.

## 10. Trạng thái đơn là một state machine

Một thiết kế tối thiểu có thể:

```text
          CREATED
             │
             ▼
      PENDING_PAYMENT
       │           │
   pay success     timeout/cancel
       │           │
       ▼           ▼
      PAID      CANCELLED
       │
       ▼
    PACKING
       │
       ▼
    SHIPPED
       │
       ▼
    DELIVERED
```

Nhưng thực tế có **payment failure, refund, returns, partial shipments**, nên chỉ một enum có thể quá tải.

### 10.1. Chia trạng thái theo lĩnh vực

Một mô hình:

```javascript
{
  status: "CONFIRMED",
  paymentStatus: "CAPTURED",
  fulfillmentStatus: "PARTIALLY_SHIPPED",
  refundStatus: "NONE"
}
```

`status` là trạng thái tổng hợp ở mức người dùng; các status phụ phản ánh miền độc lập.

### 10.2. Không tạo tích Descartes vô nghĩa

Nếu cho phép 7 trạng thái order × 6 payment × 6 fulfillment × 5 refund, có 1.260 tổ hợp lý thuyết, nhiều tổ hợp sai. Thiết kế **invariants giữa các status**, không xem mọi field hoàn toàn độc lập.

### 10.3. Tách lỗi kỹ thuật và trạng thái nghiệp vụ

`payment callback timeout` chưa chắc `PAYMENT_FAILED`: cổng thanh toán có thể đã capture nhưng webhook chưa về. Cần trạng thái `PAYMENT_UNKNOWN`/`RECONCILIATION_REQUIRED` khi phù hợp, không tự cancel hay charge lại.

## 11. Ma trận chuyển trạng thái

Một bảng quy tắc ví dụ:

| Trạng thái hiện tại | Command/event | Trạng thái mới | Điều kiện |
|---|---|---|---|
| `CREATED` | Submit checkout | `PENDING_PAYMENT` | Pricing snapshot valid |
| `PENDING_PAYMENT` | Payment captured | `PAID` | Verified provider event/amount |
| `PENDING_PAYMENT` | User cancel | `CANCELLED` | Chưa capture hoặc policy cho phép |
| `PENDING_PAYMENT` | Payment expired | `CANCELLED` | Không có capture chưa đối soát |
| `PAID` | Start packing | `PACKING` | Inventory committed |
| `PACKING` | Handoff to carrier | `SHIPPED` | Shipment created |
| `SHIPPED` | Delivery confirmed | `DELIVERED` | Carrier evidence |
| `PAID` | Approved cancellation | `CANCEL_PENDING_REFUND` | Chưa ship, approval |
| `CANCEL_PENDING_REFUND` | Refund confirmed | `CANCELLED` | Refund recorded |
| `DELIVERED` | Return approved | `RETURN_IN_PROGRESS` | Policy cho phép |
| `RETURN_IN_PROGRESS` | Refund complete | `REFUNDED` hoặc `CLOSED` | Return/refund reconciled |

Bảng chỉ là mô hình minh họa. Domain thực có thể có COD, marketplace split settlement, preorder, dịch vụ số hoặc giao nhiều chặng.

### 11.1. Không cho chuyển trạng thái bằng arbitrary `$set`

Một API:

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $set: { status: request.body.status } }
);
```

là nguy hiểm nếu không kiểm tra authorization và transition rules. Caller có thể đưa đơn từ `CANCELLED` sang `DELIVERED` mà không có giao hàng.

### 11.2. Trạng thái nên có nguyên nhân

Lưu:

```text
commandType
actor/system
eventId
sourceRevision
timestamp
reasonCode
evidenceReference
```

Đây là dữ liệu phục vụ audit/reconciliation, không phải buộc mọi status field thành một event-sourced system đầy đủ.

## 12. Những invariant quan trọng

Ví dụ:

1. `grandTotalMinor` bằng công thức đã cam kết.
2. `items` không rỗng khi chốt đơn bán hàng thông thường.
3. Mỗi line có `quantity > 0`.
4. Currency thống nhất.
5. Mỗi `(tenantId, orderNo)` unique.
6. Một idempotency key chỉ tạo tối đa một order theo phạm vi được định nghĩa.
7. `capturedMinor` không vượt số cho phép theo payment contract.
8. `refundedMinor` không vượt captured amount tương ứng.
9. Không `SHIPPED` nếu chưa có fulfillment evidence.
10. Không `CANCELLED` đã ship trừ khi domain mô tả return/recall khác.
11. Không giao trùng cùng một line/quantity.
12. Không oversell nếu inventory policy cấm.
13. Mọi mutation có revision/audit.
14. Một provider event ID không tạo hiệu ứng nghiệp vụ hai lần.

**Business invariant** quyết định ranh giới nhất quán. Không chọn transaction chỉ dựa vào việc dữ liệu nằm ở bao nhiêu collections.

## 13. Một MongoDB document được cập nhật nguyên tử

MongoDB hỗ trợ atomicity của thao tác ghi trên **một document** theo semantics server, kể cả khi đổi nhiều field trong cùng update.

Ví dụ:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    status: "PENDING_PAYMENT"
  },
  {
    $set: {
      status: "PAID",
      paymentStatus: "CAPTURED",
      "payment.capturedMinor": NumberLong("660000"),
      updatedAt: new Date()
    },
    $inc: { revision: NumberLong("1") }
  }
);
```

Nếu filter match, các field được thay đổi trong một thao tác document-level atomic. Nếu không match, không có chuyện chỉ cập nhật `status` mà bỏ `paymentStatus`.

### 13.1. Atomic update không đồng nghĩa command hợp lệ về nghiệp vụ

Nếu code chưa kiểm chứng payment event, database vẫn có thể cập nhật `PAID`. MongoDB cung cấp atomicity, còn service phải xác nhận **được phép** và **có bằng chứng** để thực hiện.

### 13.2. Kiểm tra `matchedCount`

```javascript
const r = db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    status: "PENDING_PAYMENT"
  },
  {
    $set: { status: "PAID" },
    $inc: { revision: NumberLong("1") }
  }
);

printjson({
  matched: r.matchedCount,
  modified: r.modifiedCount
});
```

Nếu `matchedCount = 0`, có thể order không tồn tại, tenant sai, hoặc trạng thái đã thay đổi. Không tự coi đây là “MongoDB lỗi nên retry vô hạn”.

## 14. Optimistic concurrency control với `revision`

Một cách bảo vệ khỏi ghi đè:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    revision: NumberLong("8"),
    status: "PAID"
  },
  {
    $set: {
      status: "PACKING",
      updatedAt: new Date()
    },
    $inc: {
      revision: NumberLong("1")
    }
  }
);
```

Worker đọc revision 8 rồi dùng chính revision đó làm điều kiện. Nếu worker khác đã cập nhật lên 9, filter không còn match.

### 14.1. Ví dụ race

```text
T1 Worker A đọc PAID, rev=8
T2 Worker B đọc PAID, rev=8
T3 A cập nhật PACKING, rev=9 → success
T4 B cập nhật CANCELLED với rev=8 → matchedCount=0
```

Worker B phải **đọc lại và quyết định theo quy tắc trạng thái mới**, không tự bỏ filter revision và ghi đè.

### 14.2. Có cần cả `status` và `revision`?

Nhiều trường hợp nên có cả hai:

- `revision`: đảm bảo không bị ghi đè bởi bất cứ thay đổi nào.
- `status`: diễn đạt điều kiện nghiệp vụ trực tiếp.

Nếu business chỉ cần transition từ status cụ thể, CAS theo status có thể đủ. Nếu nhiều fields thay đổi ảnh hưởng quyết định, revision giúp phát hiện mutation khác.

### 14.3. Revision không phải timestamp

Không dùng `updatedAt` làm version chỉ vì dễ hiển thị. Clock skew, độ phân giải thời gian và nhiều writers có thể khiến việc so sánh timestamp không đủ an toàn; counter hoặc token phiên bản rõ ràng thường dễ quản lý hơn.

## 15. Ví dụ Java Sync Driver cập nhật trạng thái an toàn

Ví dụ dùng MongoDB Java Sync Driver:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class OrderTransitions {

    public static boolean markPacking(
        MongoCollection<Document> orders,
        String tenantId,
        String orderId,
        long expectedRevision
    ) {
        Bson filter = and(
            eq("_id", orderId),
            eq("tenantId", tenantId),
            eq("status", "PAID"),
            eq("revision", expectedRevision)
        );

        Bson update = combine(
            set("status", "PACKING"),
            currentDate("updatedAt"),
            inc("revision", 1L)
        );

        UpdateResult result = orders.updateOne(filter, update);
        return result.getMatchedCount() == 1;
    }
}
```

Đoạn code giả định `revision` được lưu dưới dạng BSON Int64. Ở những records legacy có revision Int32/missing, cần migration và test mapping trước. Dùng Java `long` nhất quán cho revision mới.

### 15.1. Trả kết quả có ý nghĩa

`false` không có nghĩa nhất thiết là lỗi server; service cần đọc lại theo tenant scope và trả về một trong:

- Order không tồn tại;
- Không có quyền;
- State transition không hợp lệ;
- Version conflict;
- Already processed.

Không tiết lộ sự tồn tại của order tenant khác khi người gọi không có quyền.

### 15.2. Khi nào dùng `findOneAndUpdate`?

Khi cần nhận **document sau cập nhật** trong một thao tác, dùng `findOneAndUpdate` với `ReturnDocument.AFTER`, filter và options phù hợp.

```java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Document after = orders.findOneAndUpdate(
    filter,
    update,
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
);
```

Nếu `after == null`, filter không match. Đây không phải transaction xuyên collections.

## 16. Chuyển trạng thái cần kiểm tra nhiều điều kiện

Ví dụ muốn `PACKING → SHIPPED` khi:

- Có shipment reference;
- Các line đủ điều kiện đã được bàn giao;
- Payment state thỏa chính sách;
- Không có cancellation đang xử lý.

Có thể filter:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    status: "PACKING",
    paymentStatus: "CAPTURED",
    "fulfillmentStatus": "READY_FOR_HANDOFF"
  },
  {
    $set: {
      status: "SHIPPED",
      fulfillmentStatus: "SHIPPED",
      updatedAt: new Date()
    },
    $inc: { revision: NumberLong("1") }
  }
);
```

Nhưng shipment record là một thực thể khác. Nếu business invariant yêu cầu **order status và shipment creation cùng commit**, cần transaction hoặc thiết kế event/saga có trạng thái trung gian.

### 16.1. Không hứa “đã giao cho carrier” chỉ vì ghi thành công

Sự kiện từ carrier phải được xác minh bằng API/webhook/reference có thể đối soát. Một update DB không tự tạo giao hàng vật lý.

## 17. Hủy đơn và cuộc đua với thanh toán

Một trong những race phổ biến:

```text
T1 User bấm Hủy đơn
T2 Payment provider capture thành công
T3 Cancel service đổi status = CANCELLED
T4 Webhook service đổi status = PAID
```

Nếu chỉ `$set` theo `_id`, kết quả phụ thuộc thông điệp nào đến cuối cùng.

### 17.1. Thiết kế trạng thái trung gian

Một phương án:

```text
PENDING_PAYMENT
      │
      ├── Request cancel → CANCEL_REQUESTED
      │                         │
      │                         ├── Verify no capture → CANCELLED
      │                         └── Capture found → REFUND_REQUIRED
      │
      └── Capture confirmed → PAID
```

### 17.2. Cần giao tiếp với payment provider

Nếu provider hỗ trợ cancel payment intent, có thể yêu cầu hủy. Tuy nhiên network timeout khiến kết quả không chắc chắn, nên phải query provider hoặc reconcile bằng event ID/intent ID.

### 17.3. Không tự động hoàn tiền nhiều lần

Refund command phải có idempotency key và kiểm tra số tiền đã refund. Webhook duplicate không được trigger thêm một refund khác.

## 18. Thanh toán: tách trạng thái order và payment records

Một cấu trúc:

```javascript
// payment_attempts
{
  _id: "PAY-ATTEMPT-001",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  provider: "provider-x",
  providerIntentId: "PI-0001",
  status: "CAPTURED",
  authorizedMinor: NumberLong("660000"),
  capturedMinor: NumberLong("660000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T04:16:00Z"),
  capturedAt: ISODate("2026-11-14T04:20:00Z")
}
```

Order chỉ giữ **summary/reference**:

```javascript
payment: {
  provider: "provider-x",
  paymentIntentId: "PI-0001",
  capturedMinor: NumberLong("660000")
}
```

Payment attempt và ledger cần lưu thêm provider event IDs, operation IDs, method/authorization status và reconciliation metadata theo chính sách bảo mật.

### 18.1. Không lưu card data tùy ý

Không sao chép PAN/CVV/payment secrets vào MongoDB chỉ vì “muốn snapshot”. Sử dụng provider token/reference theo chuẩn bảo mật và quy định áp dụng.

### 18.2. Provider là nguồn đối chiếu cho tiền

`paymentStatus` trên order nên được đồng bộ theo **provider-confirmed event/reconciliation** và payment records, không theo redirect URL thành công ở frontend.

## 19. Ranh giới giao dịch số 1: chỉ có document đơn hàng

Nếu business command chỉ cần đổi các field trong một order:

```text
Mark order PACKING
  status
  fulfillmentStatus
  revision
  updatedAt
```

Single-document atomic update thường là đủ. Không cần mở multi-document transaction chỉ vì muốn nghe an toàn hơn.

Ưu điểm:

- Ít round trips;
- Khả năng chịu tải tốt;
- Giảm timeouts/conflicts;
- Ít code retry transaction;
- Ranh giới invariant rõ.

Điều kiện là tất cả những dữ liệu **phải** đổi cùng nhau được lưu trong một document và đã có authorization/validation tương ứng.

## 20. Ranh giới giao dịch số 2: nhiều document cùng MongoDB

Ví dụ:

- Tạo order document;
- Tạo reservation document;
- Giảm available inventory ở một stock document;
- Ghi outbox event.

Nếu nghiệp vụ yêu cầu không có trạng thái “order đã tạo nhưng inventory chưa giữ chỗ”, có thể cần **multi-document transaction** trên deployment hỗ trợ.

```text
MongoDB transaction
   ├── Insert order
   ├── Decrement available stock (conditional)
   ├── Insert stock reservation
   └── Insert outbox event
Commit / Abort
```

### 20.1. Transaction áp dụng khi nào?

- Invariant thực sự trải qua nhiều documents;
- Tất cả dữ liệu nằm trong MongoDB deployment/topology hỗ trợ transaction;
- Thời gian transaction ngắn;
- Tải phù hợp;
- Có retry logic cho transient conflicts và ambiguous commit;
- Không kèm HTTP call chậm tới bên ngoài khi giữ transaction.

### 20.2. Transaction không là giải pháp cho mọi workflow

Một đơn hàng có thể sống nhiều ngày; không thể mở transaction từ lúc khách đặt đến khi giao hàng. Transaction chỉ phù hợp các bước **ngắn** và có điều kiện commit rõ ràng.

## 21. Ví dụ Java transaction với session

Cấu trúc minh họa:

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;

import org.bson.Document;

public void createOrderAndOutbox(
    MongoClient client,
    MongoCollection<Document> orders,
    MongoCollection<Document> outbox,
    Document order,
    Document event
) {
    try (ClientSession session = client.startSession()) {
        session.startTransaction();

        try {
            orders.insertOne(session, order);
            outbox.insertOne(session, event);
            session.commitTransaction();
        } catch (RuntimeException ex) {
            session.abortTransaction();
            throw ex;
        }
    }
}
```

Đây là **khung minh họa**, chưa đủ cho production:

- Cần handler cho lỗi transient transaction;
- Có thể phải retry toàn transaction bằng API phù hợp;
- Khi commit outcome không rõ, phải phân biệt retry commit và retry business command;
- Có write concern/read concern phù hợp;
- Chống duplicate order/event bằng stable IDs/unique indexes;
- Không mutate/reuse dữ liệu có side effects ngoài DB bên trong callback retry.

MongoDB Java Driver có transaction callback/helper theo version, thường nên ưu tiên để giảm lỗi retry boilerplate.

### 21.1. `commitTransaction()` timeout không chứng minh abort

Nếu server đã commit nhưng response mất trên mạng, client có thể chưa biết kết quả. Không tạo lại order với ID mới trước khi kiểm tra stable identity/idempotency contract.

### 21.2. Không gắn HTTP call vào transaction

Sai về kiến trúc:

```text
start MongoDB transaction
  insert order
  call payment gateway over HTTP
  wait 30 seconds
  insert payment log
commit
```

Nếu HTTP timeout hoặc transaction hết thời gian, external payment có thể đã thành công mà transaction MongoDB lại abort. Không có atomicity end-to-end.

## 22. Inventory là một ranh giới độc lập

Mỗi SKU/warehouse có lượng tồn kho hữu hạn, được tranh chấp bởi **nhiều orders khác nhau**.

```javascript
// inventory
{
  _id: {
    tenantId: "TENANT-A",
    warehouseId: "WH-01",
    sku: "SHIRT-BLUE-M"
  },
  available: NumberLong("10"),
  reserved: NumberLong("0"),
  sold: NumberLong("0"),
  revision: NumberLong("20")
}
```

Dữ liệu tồn kho không nên embed toàn bộ vào order vì mỗi order không sở hữu inventory riêng.

### 22.1. Đọc rồi ghi là sai khi có cạnh tranh

```text
Order A đọc available = 1
Order B đọc available = 1
Order A tạo đơn 1 sản phẩm
Order B tạo đơn 1 sản phẩm
```

Nếu cả hai chỉ đọc và update sau, có thể oversell.

### 22.2. Cập nhật có điều kiện trên một stock document

```javascript
const r = db.inventory.updateOne(
  {
    _id: {
      tenantId: "TENANT-A",
      warehouseId: "WH-01",
      sku: "SHIRT-BLUE-M"
    },
    available: { $gte: NumberLong("2") }
  },
  {
    $inc: {
      available: NumberLong("-2"),
      reserved: NumberLong("2"),
      revision: NumberLong("1")
    }
  }
);

if (r.matchedCount !== 1) {
  print("Không đủ tồn kho hoặc stock record không tồn tại");
}
```

Filter và `$inc` được thực hiện nguyên tử trên **stock document này**, ngăn hai commands cùng sử dụng một lượng `available` đã hết theo điều kiện filter.

### 22.3. Stock document thành hotspot

Nếu hàng nghìn orders cùng tranh một SKU phổ biến, một stock document có thể bị write contention. Có thể cần allocation theo warehouse/bucket, queue, reservation service hoặc thiết kế khác, nhưng phải bảo toàn tổng invariant và điều kiện oversell.

## 23. Reservation tách biệt giúp giải quyết hết hạn và hoàn trả

Một reservation record:

```javascript
{
  _id: "RES-ORD-2026-001-L1-WH01",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  lineId: "L1",
  warehouseId: "WH-01",
  sku: "SHIRT-BLUE-M",
  quantity: NumberLong("2"),
  status: "HELD",
  expiresAt: ISODate("2026-11-14T04:30:00Z")
}
```

Các trạng thái reservation:

```text
HELD → COMMITTED
  │
  └── RELEASED / EXPIRED
```

### 23.1. Một reservation là một cam kết tạm thời

Nó giữ chỗ hàng cho đơn chưa hoàn tất thanh toán theo policy, không đồng nghĩa hàng đã bán và giao.

### 23.2. Khi nào giải phóng?

- Checkout bị hủy;
- Payment intent timeout được xác minh;
- User không hoàn tất checkout;
- Fraud review từ chối;
- Order chuyển trạng thái được phép thả reservation.

### 23.3. Release phải idempotent

Nếu webhook hủy đến hai lần, không được cộng lại `available` hai lần. Dùng reservation state guard:

```text
HELD → RELEASED : release stock exactly once
RELEASED → RELEASED : no-op
COMMITTED → RELEASED : chỉ theo nghiệp vụ được phép
```

Với reservation và stock ở hai documents, cần transaction hoặc cơ chế ledger/outbox/reconciliation để tránh trạng thái release một bên nhưng chưa cập nhật bên kia.

## 24. TTL không tự hoàn trả tồn kho

Một lỗi phổ biến:

```javascript
db.stock_reservations.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

rồi giả định MongoDB xóa reservation tức thì và tự cộng lại `inventory.available`.

TTL chỉ thực hiện **xóa document đủ điều kiện theo cơ chế nền**; nó không tự cập nhật stock document. Nếu reservation bị xóa, còn có thể mất bằng chứng để hoàn trả tồn kho.

### 24.1. Thiết kế tốt hơn

- Giữ reservation record với status/expiry;
- Scheduler hoặc worker claim reservation đã hết hạn;
- Chuyển `HELD → EXPIRED` có điều kiện;
- Trong cùng transaction phù hợp, hoàn trả stock và ghi event;
- Chỉ dọn records lịch sử sau retention period riêng.

TTL có thể áp dụng cho **records đã kết thúc** và không còn cần cho reconciliation, theo compliance policy.

### 24.2. Time-based expiration không chính xác từng millisecond

Không dùng TTL monitor như đồng hồ để đảm bảo release tức thì. Business logic phải kiểm tra `expiresAt` ở thời điểm xử lý nếu cần.

## 25. Ranh giới giao dịch số 3: MongoDB và payment provider

Một payment provider không tham gia transaction MongoDB của ứng dụng:

```text
MongoDB order update ──────┐
                           ├── Không có distributed atomic commit mặc định
External payment capture ─┘
```

Các kịch bản:

1. DB commit thành công, HTTP payment fail.
2. HTTP payment thành công, DB update fail.
3. Cả hai thành công nhưng process crash trước ACK.
4. Provider gửi webhook hai lần.
5. Webhook đến trước HTTP response.
6. User cancel trong lúc capture đang xử lý.

Muốn đúng phải dựa trên **orchestration, idempotency, durable events và reconciliation**, không dựa vào một database transaction tưởng tượng bao trùm tất cả.

## 26. Saga: workflow có hành động bù trừ

Một saga đơn giản:

```text
Create PENDING_PAYMENT order
           │
           ▼
Reserve inventory
           │
           ▼
Request payment authorization/capture
      ┌────┴─────┐
   Success      Failure
      │            │
      ▼            ▼
 Mark PAID      Release reservation
      │            │
      ▼            ▼
 Confirm stock  Mark failed/cancelled
```

Nếu payment đã capture nhưng stock không còn, saga có thể phải **refund** chứ không thể “rollback” external payment bằng MongoDB abort.

### 26.1. Compensation không phải transaction rollback

Compensation là hành động nghiệp vụ mới:

- Payment capture → refund;
- Inventory hold → release;
- Shipment label created → cancel shipment (nếu provider cho phép);
- User notification sent → không thể “thu hồi” hoàn toàn, cần gửi thông báo điều chỉnh.

Không giả định mọi tác động ngoài DB đều có bù trừ hoàn hảo.

### 26.2. Saga phải có durable state

Lưu workflow ID, current step, command/event IDs, attempt count, deadline và last error. Nếu process crash, worker khác có thể resume theo trạng thái đã commit.

### 26.3. Không retry vô hạn bước thất bại vĩnh viễn

Ví dụ invalid payment credentials hoặc đơn bị fraud reject cần trạng thái lỗi rõ. Timeout tạm thời có thể retry giới hạn kèm backoff và kiểm tra kết quả trước khi gửi yêu cầu mới.

## 27. Transactional outbox: nối DB transaction và message delivery

Một anti-pattern:

```text
1. orders.insertOne()
2. messageBroker.publish("OrderCreated")
```

Nếu process chết sau bước 1, event có thể không được phát. Nếu broker nhận event nhưng response mất, app retry có thể phát trùng.

**Transactional outbox** lưu event vào MongoDB trong cùng transaction với thay đổi business, sau đó một dispatcher gửi tới broker.

```text
MongoDB transaction
     ├── Insert/Update order
     └── Insert outbox event
             │
          COMMIT
             │
             ▼
       Outbox dispatcher
             │
             ▼
       Message broker / service
             │
             ▼
       Consumer idempotency
```

### 27.1. Ví dụ outbox document

```javascript
{
  _id: "evt-ORD-2026-001-paid-v8",
  tenantId: "TENANT-A",
  aggregateType: "Order",
  aggregateId: "ORD-2026-001",
  aggregateRevision: NumberLong("8"),
  eventType: "OrderPaid",
  eventVersion: 2,
  occurredAt: ISODate("2026-11-14T04:20:00Z"),
  payload: {
    orderId: "ORD-2026-001",
    amountMinor: NumberLong("660000"),
    currency: "VND"
  },
  state: "PENDING",
  attempts: 0
}
```

Không copy toàn bộ order snapshot chứa địa chỉ/PII vào event nếu downstream chỉ cần order ID và amount.

### 27.2. Outbox không tự exactly-once toàn hệ

Dispatcher có thể publish thành công rồi crash trước khi đánh dấu `SENT`; khi chạy lại nó có thể publish event lần nữa. Consumers cần deduplicate theo event ID hoặc xử lý idempotent.

### 27.3. Outbox lifecycle

```text
PENDING → CLAIMED → SENT
             │
             └── RETRY / DEAD_LETTER
```

Cần claim lease/ownership, retry limit, backoff, alert, cleanup retention và metrics.

## 28. Ví dụ transaction order + outbox

Cấu trúc Java Sync Driver:

```java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        UpdateResult transition = orders.updateOne(
            session,
            Filters.and(
                Filters.eq("_id", orderId),
                Filters.eq("tenantId", tenantId),
                Filters.eq("status", "PENDING_PAYMENT"),
                Filters.eq("revision", expectedRevision)
            ),
            Updates.combine(
                Updates.set("status", "PAID"),
                Updates.inc("revision", 1L),
                Updates.currentDate("updatedAt")
            )
        );

        if (transition.getMatchedCount() != 1) {
            throw new IllegalStateException("Order transition conflict");
        }

        outbox.insertOne(
            session,
            new Document("_id", eventId)
                .append("tenantId", tenantId)
                .append("aggregateId", orderId)
                .append("eventType", "OrderPaid")
                .append("aggregateRevision", expectedRevision + 1)
                .append("state", "PENDING")
                .append("createdAt", new java.util.Date())
        );

        session.commitTransaction();
    } catch (RuntimeException ex) {
        session.abortTransaction();
        throw ex;
    }
}
```

`client`, `orders`, `outbox`, `orderId`, `tenantId`, `expectedRevision`, `eventId` là biến ứng dụng được khởi tạo và validate từ trước; cần session/transaction retry logic phù hợp, không dùng trực tiếp như chương trình hoàn chỉnh.

### 28.1. Cần transaction không?

Nếu order update và event insert **bắt buộc** cùng commit, transaction là cách rõ ràng trong cùng MongoDB deployment có hỗ trợ. Một lựa chọn khác là embed một outbox marker nhỏ trong order document rồi dispatcher trích xuất, nhưng phải kiểm soát size, ordering và lifecycle.

### 28.2. Không gửi message trong callback được tự retry

Nếu transaction helper retry callback, gọi payment provider/message broker ngay trong callback có thể gửi trùng tác động bên ngoài. Callback nên chỉ thao tác DB có thể retry an toàn.

## 29. Change streams có vai trò gì?

MongoDB change streams cho phép consumer nhận events về những thay đổi được commit theo semantics và topology hỗ trợ.

Có thể dùng để:

- Cập nhật read models;
- Đồng bộ search;
- Phát hiện order status changes;
- Triển khai một số dạng CDC;
- Hỗ trợ outbox dispatch.

Nhưng:

- Change stream events có thể được xử lý lặp trong retry/resume;
- Resume token cần được lưu sau khi downstream apply thành công;
- Oplog window/retention giới hạn khả năng resume;
- Không đồng nghĩa durable business event log vô hạn;
- Consumer có thể cần initial snapshot và reconciliation;
- Không tự cung cấp exactly-once end-to-end.

### 29.1. Outbox và change streams bổ sung nhau

Một thiết kế có thể:

```text
MongoDB transaction → outbox collection
                           │
                      change stream
                           │
                       dispatcher
                           │
                       message broker
```

Outbox giữ durable event state/retry metadata, còn change stream hỗ trợ phát hiện thay đổi gần thời gian thực. Cần kế hoạch hồi phục khi consumer rơi ngoài oplog window.

## 30. Idempotency của checkout và tạo đơn

Người dùng bấm “Đặt hàng” hai lần hoặc HTTP request bị retry.

Nếu mỗi request tạo `_id` mới:

```text
Request 1 → Order A
Request 2 → Order B
```

có thể tạo đơn trùng, giữ kho trùng và gọi payment hai lần.

### 30.1. Stable idempotency key

Client gửi key duy nhất theo một lần checkout; server gắn nó với:

- Tenant/customer;
- Request fingerprint/canonical payload;
- Order ID;
- Processing state;
- Expiry/retention;
- Result reference.

Ví dụ:

```javascript
{
  tenantId: "TENANT-A",
  idempotencyKey: "checkout-8d2f...",
  orderId: "ORD-2026-001",
  payloadHash: "sha256:...",
  status: "COMPLETED"
}
```

### 30.2. Unique constraint

Nếu dùng collection `checkout_requests`:

```javascript
db.checkout_requests.createIndex(
  { tenantId: 1, idempotencyKey: 1 },
  { unique: true, name: "uq_tenant_checkout_key" }
);
```

Không tự tin rằng hai requests cùng check “chưa tồn tại” rồi insert là an toàn. Unique constraint giúp chống race ở database.

### 30.3. Same key, different payload

Nếu idempotency key đã được dùng cho một cart khác, service không được trả “thành công” cho nội dung mới. Kiểm tra canonical payload hash và trả conflict theo contract.

### 30.4. Retention phải đủ dài

Một idempotency record hết hạn quá sớm có thể cho phép request cũ được tạo lại. Thời hạn tùy payment/provider retry windows, business policy và retention.

## 31. Idempotency của webhook

Payment provider thường gửi lại webhook nếu chưa nhận ACK, và events có thể tới không theo thứ tự như kỳ vọng.

Một event record:

```javascript
{
  _id: "provider-x:event-0001",
  tenantId: "TENANT-A",
  provider: "provider-x",
  eventType: "payment.captured",
  providerIntentId: "PI-0001",
  receivedAt: ISODate("2026-11-14T04:20:01Z"),
  processingStatus: "PROCESSED"
}
```

### 31.1. Xác minh event trước khi ghi

- Verify signature từ provider;
- Kiểm tra timestamp/replay window theo API provider;
- Kiểm tra tenant/account mapping;
- Đối chiếu order/payment intent;
- Kiểm tra amount/currency;
- Lưu event ID/deduplication key;
- Chuyển trạng thái có điều kiện;
- Trả ACK theo protocol sau khi lưu state đủ bền.

### 31.2. Duplicate event không làm tăng captured amount lần nữa

Một cách không an toàn:

```javascript
{ $inc: { "payment.capturedMinor": amount } }
```

nếu mỗi webhook duplicate đều thực hiện lại. Nên lấy payment records/operation IDs có uniqueness hoặc cập nhật tới trạng thái xác nhận được, với idempotency.

### 31.3. Event out of order

Nếu event “refunded” đến trước “captured” vì delivery delay, không bắt buộc phải từ chối vĩnh viễn. Có thể giữ pending reconciliation và query provider theo nguồn sự thật, không ghi đè trạng thái bằng “event mới nhất tới mạng”.

## 32. Sổ cái kế toán và audit khác trạng thái đơn

Một order có thể:

- Capture 660000;
- Refund 100000;
- Refund tiếp 560000;
- Có phí và các khoản settlement riêng.

Chỉ `paymentStatus = "REFUNDED"` không đủ để giải thích tất cả movements.

Một cấu trúc append-only ledger:

```javascript
{
  _id: "LEDGER-0001",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  paymentAttemptId: "PAY-ATTEMPT-001",
  providerOperationId: "CAPTURE-001",
  entryType: "CAPTURE",
  amountMinor: NumberLong("660000"),
  currency: "VND",
  recordedAt: ISODate("2026-11-14T04:20:00Z")
}
```

Một refund:

```javascript
{
  _id: "LEDGER-0002",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  providerOperationId: "REFUND-001",
  entryType: "REFUND",
  amountMinor: NumberLong("100000"),
  currency: "VND",
  recordedAt: ISODate("2026-11-15T02:00:00Z")
}
```

### 32.1. Không cập nhật lịch sử tiền tùy ý

Nếu cần sửa, ghi bút toán điều chỉnh/bù trừ theo chính sách và lưu audit. Ledger chính thức có thể cần quy tắc kế toán kép, đối soát, bất biến và quyền truy cập mạnh hơn ví dụ.

### 32.2. Tổng tiền snapshot khác tổng tiền thực thu

```text
Order grandTotal: 660000
Captured: 660000
Refunded: 100000
Net captured: 560000
```

Ba con số đều có giá trị riêng; không ghi đè `grandTotal` thành 560000 sau refund, vì làm mất cam kết gốc.

## 33. Hoàn tiền một phần

Khi chỉ hoàn một line hoặc một quantity, cần xác định:

- Line ID và quantity được refund;
- Unit price snapshot;
- Phân bổ discount và tax;
- Shipping refund policy;
- Captured amount còn được phép refund;
- Previous refunds;
- Provider refund ID;
- Return/quality checks.

### 33.1. Đừng tính refund từ catalog hiện hành

Nếu giá sản phẩm đã tăng, refund theo giá hiện tại là sai. Cần dùng order snapshot và chính sách refund tại thời điểm áp dụng.

### 33.2. Chống refund vượt tổng capture

Một invariant:

\[
\sum \text{refundSuccessfulMinor} \leq \text{capturedMinor}
\]

Trong hệ concurrent refunds, nếu kiểm tra trong Java rồi gọi provider riêng lẻ, hai yêu cầu có thể cùng vượt mức. Cần reservation/authorization refund amount với CAS/transaction và idempotency provider, đồng thời đối soát provider.

### 33.3. Refund không đồng nghĩa cancel order

Một đơn đã delivered có thể được refund một phần trong return workflow. Không ép toàn bộ trạng thái order về `CANCELLED` khi chỉ có một line được hoàn.

## 34. Giao hàng một phần

Một order có hai lines, một line đã ship, một line chưa đủ hàng.

Nếu chỉ có:

```javascript
fulfillmentStatus: "SHIPPED"
```

có thể gây hiểu nhầm.

Thiết kế:

```text
NOT_STARTED
ALLOCATED
PARTIALLY_SHIPPED
SHIPPED
PARTIALLY_DELIVERED
DELIVERED
RETURN_IN_PROGRESS
```

Và shipment records:

```javascript
{
  _id: "SHIP-001",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  lines: [
    { lineId: "L1", shippedQuantity: 1 }
  ],
  carrierCode: "CARRIER-X",
  trackingReference: "TRACK-001",
  status: "IN_TRANSIT"
}
```

### 34.1. Invariant theo line

```text
shippedQuantity(line) <= orderedQuantity(line) - cancelledQuantity(line)
```

Nếu có reshipment, lost shipment hoặc returns, phải mở rộng model thay vì tự cộng trừ thiếu bối cảnh.

### 34.2. Shipment events có thể trễ/trùng

Carrier webhook phải dedupe theo event ID, không cho trạng thái giao hàng lùi từ `DELIVERED` về `IN_TRANSIT` nếu một event cũ đến muộn.

## 35. Lưu lịch sử chuyển trạng thái thế nào?

Có ba lựa chọn phổ biến.

### 35.1. Chỉ giữ trạng thái hiện tại

```javascript
{
  status: "PAID",
  updatedAt: ISODate("...")
}
```

Đơn giản, nhưng khó audit khi cần biết trước đó là gì và ai chuyển.

### 35.2. Embed lịch sử nhỏ có giới hạn

```javascript
{
  status: "PAID",
  recentTransitions: [
    {
      from: "CREATED",
      to: "PENDING_PAYMENT",
      eventId: "E1",
      at: ISODate("...")
    },
    {
      from: "PENDING_PAYMENT",
      to: "PAID",
      eventId: "E2",
      at: ISODate("...")
    }
  ]
}
```

Phù hợp khi chỉ cần một số event gần nhất. Không append vô hạn: document có giới hạn BSON và mỗi update vào một document hot có chi phí.

### 35.3. Collection events riêng

```javascript
{
  _id: "ORD-2026-001:REV-8",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  revision: NumberLong("8"),
  fromStatus: "PENDING_PAYMENT",
  toStatus: "PAID",
  causeEventId: "provider-x:event-0001",
  occurredAt: ISODate("...")
}
```

Có thể ghi trong transaction cùng order update để giữ consistency giữa summary và history khi invariant yêu cầu.

### 35.4. Event sourcing không bắt buộc

Lưu event history không có nghĩa bắt buộc dùng event sourcing full. Event sourcing đòi event log là nguồn sự thật, projection replay/versioning và migration của event schemas. Với nhiều sản phẩm, order document + audit/outbox là lựa chọn dễ vận hành hơn.

## 36. Document size và arrays không giới hạn

MongoDB có giới hạn kích thước một BSON document (thông thường 16 MiB trong những phiên bản phổ biến); một order có 10 dòng hàng khác một order có 100.000 dòng.

Cần xem:

- Số line items tối đa theo business;
- Kích thước snapshot mỗi line;
- Gift messages/comments;
- Audit entries;
- Discount allocations;
- Fulfillment events;
- Payloads từ providers;
- Images/blobs.

### 36.1. Tránh embed dữ liệu bất tận

Những arrays tăng không giới hạn như `paymentAttempts`, `webhookEvents`, `statusHistory`, `trackingEvents` nên có collection riêng hoặc cơ chế bounded summary.

### 36.2. Giới hạn order lines theo domain

Nếu đơn marketplace có hàng trăm nghìn dòng, có thể cần tách `order_lines` riêng và chấp nhận transaction/read model khác. Đừng chỉ trông chờ giới hạn MongoDB cho biết mô hình đã sai.

### 36.3. Không lưu hình ảnh file nhị phân trong order snapshot

Lưu một identifier/URL đã kiểm soát hoặc immutable asset reference, tránh làm đơn phình và phụ thuộc vào URL ngắn hạn hết hạn.

## 37. Đọc đơn hàng: projection và data access patterns

Một trang list orders thường cần:

```text
orderId
placedAt
status
grandTotal
currency
itemCount
preview items (1–2 dòng)
```

Không cần toàn bộ shipping address, payment attempts hay audit events.

### 37.1. Projection trong `mongosh`

```javascript
db.orders.find(
  {
    tenantId: "TENANT-A",
    customerId: "CUS-102"
  },
  {
    orderNo: 1,
    placedAt: 1,
    status: 1,
    currency: 1,
    "pricing.grandTotalMinor": 1,
    "items.snapshot.name": 1
  }
)
.sort({ placedAt: -1, _id: -1 })
.limit(20);
```

Với items lớn, cân nhắc projection `$slice` hoặc lưu summary field phục vụ list thay vì đọc mọi line names.

### 37.2. Detail view

Detail order có thể đọc toàn snapshot, nhưng những dữ liệu ngoài aggregate như shipment tracking/payment attempts nên lấy qua service/repository riêng có quyền phù hợp.

### 37.3. Không join catalog để tái tạo lịch sử

Có thể query catalog để hiển thị sản phẩm hiện có hoặc link mua lại, nhưng giá/tên trong chứng từ đơn phải lấy từ snapshot theo contract.

## 38. Indexes cho order workload

Các query phổ biến:

```javascript
// Tìm một đơn của tenant
db.orders.findOne({
  tenantId: "TENANT-A",
  _id: "ORD-2026-001"
});

// Lịch sử theo khách hàng
db.orders.find({
  tenantId: "TENANT-A",
  customerId: "CUS-102"
}).sort({ placedAt: -1, _id: -1 }).limit(20);

// Đơn chờ xử lý
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
}).sort({ placedAt: 1 }).limit(100);
```

Các index ứng viên:

```javascript
db.orders.createIndex(
  { tenantId: 1, customerId: 1, placedAt: -1, _id: -1 },
  { name: "idx_tenant_customer_recent_orders" }
);

db.orders.createIndex(
  { tenantId: 1, status: 1, placedAt: 1 },
  { name: "idx_tenant_status_queue" }
);

db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_order_no" }
);
```

Không tạo tất cả chỉ vì ví dụ có; phải dùng `explain("executionStats")`, đo p95/p99, index size và write maintenance cost.

### 38.1. `_id` index đã có

MongoDB mặc định có index trên `_id`. Nếu ID unique toàn cục, lookup `_id` rất hiệu quả, nhưng application vẫn phải xác minh tenant/authorization. Có thể không cần thêm index `{tenantId,_id}` nếu workload và sharding constraints không yêu cầu.

### 38.2. Queue index có thể dùng partial

Nếu phần lớn orders đã hoàn tất, worker chỉ đọc `status: "PAID"`, một partial index có thể giảm footprint:

```javascript
db.orders.createIndex(
  { tenantId: 1, placedAt: 1 },
  {
    name: "idx_paid_order_queue",
    partialFilterExpression: { status: "PAID" }
  }
);
```

Query phải hàm ý filter của partial index để planner có thể dùng đúng mà không làm thiếu results.

### 38.3. Index unique là business contract

Không nên chỉ dựa vào code `existsByOrderNo` rồi insert, vì requests đồng thời có thể cùng vượt qua check. Unique constraint cùng idempotency giúp chặn duplicates ở database.

## 39. Sharding: chọn khóa theo truy vấn và phân phối

Nếu số orders rất lớn, có thể cần sharding. Phải xét:

- Query chủ yếu theo tenant và order ID;
- Số tenant ít hay nhiều;
- Một tenant khổng lồ hay phân bố đều;
- Write rate theo thời gian;
- Mẫu truy vấn lịch sử/sắp xếp;
- Unique orderNo/idempotency constraints;
- Transaction cross-shard cost;
- TTL/archive policy.

### 39.1. Không mặc định shard key `{tenantId:1}`

Nếu một tenant rất lớn, mọi orders của tenant đó có thể tạo hotspot hoặc không phân phối theo cách mong muốn. Nếu shard theo `createdAt` tăng dần, có thể có hotspot ở shard nhận thời điểm mới. Cần phân tích phân phối và query targeting.

### 39.2. Unique indexes và shard key

MongoDB sharded collections có **ràng buộc đặc thù đối với unique indexes và shard key**. Không giả định mọi index `{tenantId,orderNo}` có thể được tạo unique trên mọi shard key. Kiểm tra docs của MongoDB Server version và phương án dữ liệu cụ thể.

### 39.3. Cross-shard transactions có chi phí

Một transaction cập nhật order ở shard A và stock ở shard B có thể tốn coordination và tài nguyên hơn single-shard/single-document. Không thiết kế shard keys làm mọi checkout thành distributed transaction khi có thể tránh được mà không phá model.

### 39.4. Đừng tối ưu chỉ cho inserts

Orders còn được đọc theo customer, status queue, refunds, audits. Chọn shard key phải cân bằng write distribution, query targeting, growth và hoạt động quản trị.

## 40. Schema validation cho order document

MongoDB có collection validator dựa trên `$jsonSchema` giúp ngăn một số dữ liệu sai kiểu/hình dạng.

Ví dụ khái niệm:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "status",
      "currency",
      "items",
      "pricing",
      "revision"
    ],
    properties: {
      tenantId: { bsonType: "string" },
      status: {
        enum: [
          "CREATED",
          "PENDING_PAYMENT",
          "PAID",
          "PACKING",
          "SHIPPED",
          "DELIVERED",
          "CANCELLED",
          "CANCEL_PENDING_REFUND",
          "REFUNDED"
        ]
      },
      currency: { bsonType: "string" },
      items: {
        bsonType: "array",
        minItems: 1
      },
      revision: { bsonType: "long" },
      pricing: {
        bsonType: "object",
        required: ["grandTotalMinor"],
        properties: {
          grandTotalMinor: { bsonType: "long" }
        }
      }
    }
  }
}
```

Đây là ví dụ schema shape, chưa bao phủ mọi status khác đã đề cập. Khi triển khai cần chọn **enum nhất quán với state machine thật**, version hóa schema và test.

### 40.1. Validator không thay workflow rules

MongoDB `$jsonSchema` có thể kiểm `status` thuộc enum, nhưng không tự biết từ `SHIPPED` có được sang `CANCELLED` không. Cần CAS/transaction/service domain logic.

### 40.2. Strict schema có thể ảnh hưởng legacy records

Nếu dữ liệu cũ lưu `revision` Int32 hoặc không có `pricing`, bật strict có thể khiến updates bị từ chối. Dùng expand-and-contract, backfill và staged validator rollout.

### 40.3. Đừng dùng validator thay authorization

Validator không đảm bảo người dùng tenant A không ghi order tenant B. Quyền/tenant context phải được enforce ở service/database access boundary.

## 41. Quyền truy cập và dữ liệu nhạy cảm

Order thường chứa:

- Tên/địa chỉ người nhận;
- Số điện thoại;
- Thông tin khách hàng;
- Giá trị giao dịch;
- Thông tin hàng hóa cá nhân;
- Tracking references;
- Ghi chú giao hàng.

### 41.1. Phân tách view theo vai trò

| Vai trò | Thông tin thường được xem |
|---|---|
| Người mua | Đơn của chính mình |
| Người bán | Dòng hàng thuộc quyền xử lý |
| Kho | SKU, số lượng, địa chỉ/nhãn cần thiết |
| Carrier | Thông tin vận chuyển tối thiểu |
| Kế toán | Amount, tax, payment/ledger references |
| Chăm sóc khách hàng | Trạng thái và phần dữ liệu cần cho ticket |
| Admin vận hành | Audit theo quyền, không mặc định mọi PII |

Với marketplace nhiều seller, một order có dòng của nhiều seller. Không trả toàn bộ địa chỉ/payment data hoặc dòng hàng seller khác nếu policy không cho phép.

### 41.2. Snapshot và retention mâu thuẫn tiềm ẩn

Một số thông tin phải giữ để đối soát/hóa đơn, nhưng PII phải được xóa/ẩn theo luật và chính sách khi hết mục đích. Thiết kế field-level encryption, retention, pseudonymization hoặc tách encrypted address document/reference khi phù hợp.

### 41.3. Không log toàn bộ order

Một log an toàn hơn:

```text
traceId
tenant scope (theo policy)
orderId
transitionFrom
transitionTo
revision
paymentEventId
errorCode
elapsedMs
```

Tránh raw recipient address, payment token, API credentials hoặc full webhook body.

## 42. TTL và xóa đơn hàng

Không nên gắn TTL index trực tiếp vào `orders.placedAt` chỉ vì “muốn dọn dữ liệu cũ” mà chưa có retention policy.

TTL trên order có thể xóa:

- Chứng từ cần lưu;
- Dữ liệu phục vụ refund/chargeback;
- Audit nghiệp vụ;
- Records còn dispute;
- Dữ liệu đối chiếu sổ cái.

Một chiến lược:

```text
Active orders
     │
     ▼
Closed + retention eligible
     │
     ▼
Archive/export under policy
     │
     ▼
Integrity/audit confirmation
     │
     ▼
Delete or anonymize according to requirements
```

### 42.1. TTL phù hợp hơn với dữ liệu tạm

Quote hết hạn, deduplication cache hoặc temporary checkout sessions có thể dùng TTL khi thật sự có policy xóa và không ảnh hưởng correctness. TTL deletion **bất đồng bộ**, nên business expiration phải được kiểm trong logic.

## 43. CQRS và materialized read models

Nếu reporting cần tổng đơn theo ngày/tenant/status, không nhất thiết query toàn bộ orders mỗi lần.

Có thể có read model:

```javascript
{
  _id: {
    tenantId: "TENANT-A",
    day: "2026-11-14",
    status: "PAID"
  },
  orderCount: NumberLong("1000"),
  grossMinor: NumberLong("660000000"),
  computedAt: ISODate("...")
}
```

### 43.1. Read model không là nguồn truth cho thanh toán

Đây là projection có thể lag và có thể rebuild từ orders/ledger/events theo contract. Không dùng tổng báo cáo từ read model để tự kết luận provider đã settle đúng tiền.

### 43.2. Rebuild cần idempotency

Nếu consumer replay event hai lần, `$inc` tổng số đơn có thể tăng hai lần. Cần event dedupe hoặc rebuild bằng recompute và `$set` tới trạng thái được kiểm chứng.

### 43.3. Eventual consistency là một quyết định

Ứng dụng phải biết phần nào chấp nhận lag vài giây và phần nào cần đọc ngay từ source of truth, ví dụ trạng thái thanh toán trước giao hàng.

## 44. Tính đúng đắn khi retry và unknown outcomes

Các tình huống khó:

| Tình huống | Rủi ro | Biện pháp |
|---|---|---|
| Client timeout sau insert order | Tạo order lần hai | Stable order/idempotency key |
| MongoDB commit success, response lost | Retry business action trùng | Read-after-retry/reconcile |
| Payment capture success, callback lost | Đơn vẫn pending | Provider reconciliation |
| Webhook duplicate | PAID hai lần/ledger trùng | Unique provider event/operation ID |
| Inventory release retried | Hoàn stock hai lần | Reservation state transition guard |
| Outbox publish success, marker failed | Event gửi lại | Consumer deduplication |
| Shipment webhook out of order | Trạng thái lùi | Version/event-time state rules |
| Refund timeout | Refund trùng | Provider idempotency + ledger reconciliation |
| Partial stock allocation | Đơn giữ một phần | Transaction hoặc compensation |
| Order snapshot write error | Giá có thể bị tính lại | Immutable quote ID và retry contract |

### 44.1. Retryable writes không đồng nghĩa exactly-once business

MongoDB Driver có retryable writes cho những operations đủ điều kiện theo giao thức. Nhưng retry ở tầng HTTP hoặc job với request ID mới có thể tạo tác động mới. Business-level idempotency vẫn cần thiết.

### 44.2. Không biến timeout thành “thất bại” khi chưa rõ

Một timeout là **unknown outcome** nếu command/provider có thể đã xử lý. Cần trạng thái đối soát và request/event identity ổn định.

## 45. Sự cố `PAID` nhưng kho chưa giữ được

Một luồng sai:

```text
1. Capture payment
2. Create order
3. Decrement inventory
4. Inventory insufficient
```

Lúc này đã có tiền nhưng không có hàng.

### 45.1. Một workflow thay thế

```text
1. Validate quote
2. Create PENDING_PAYMENT order + reserve stock
3. Request payment
4. On verified success, commit reservation
5. On failure/expiry, release stock
```

Workflow này giảm rủi ro nhưng không loại bỏ mọi vấn đề: payment có thể thành công sau expiration hoặc reservation release. Saga cần policy hoàn tiền/backorder và reconciliation.

### 45.2. Không đặt stock reservation trong một MongoDB transaction kéo dài trong lúc chờ thanh toán

Transaction có timeout và chi phí, không phù hợp kéo dài đến khi khách hoàn tất OTP hay provider callback. Lưu reservation bền vững **sau một transaction ngắn**, rồi xử lý payment bất đồng bộ.

## 46. Sự cố `CANCELLED` nhưng payment callback đến sau

Điều tra:

1. Payment provider đã authorize/capture chưa?
2. Order transition nào commit trước?
3. Cancel path có request hủy provider không?
4. Refund có được tạo/idempotent không?
5. Reservation được release theo trạng thái nào?
6. Event IDs và sequence/watermarks ra sao?
7. Customer notification có đúng không?

Một giải pháp tùy domain:

```text
CANCELLED + capture confirmed
       │
       ▼
REFUND_REQUIRED
       │
       ▼
Provider refund request with stable key
       │
       ▼
REFUND_CONFIRMED
       │
       ▼
CLOSED
```

Không chuyển đơn về `PAID` chỉ vì webhook capture đến cuối cùng; có thể cần một trạng thái bù trừ khác.

## 47. Sự cố giá lịch sử thay đổi

Triệu chứng: trang xem đơn hàng cũ hiển thị tổng khác invoice đã phát hành.

Nguyên nhân điển hình:

- UI join catalog và đọc `product.price` hiện hành;
- Backend recompute pricing từ promotions hiện tại;
- Snapshot chưa lưu tax/shipping allocation;
- Dữ liệu money bị convert sai kiểu;
- Refund làm ghi đè original grand total;
- Cập nhật item embedded không giới hạn theo status;
- Query projection trả thiếu một phần snapshot.

### 47.1. Cách xử lý

- Dừng việc hiển thị/tính lại từ catalog nếu sai contract;
- Giữ dữ liệu gốc/hóa đơn đã xác nhận;
- Đối soát snapshot với payment/ledger;
- Sửa read path, không sửa ngẫu nhiên orders lịch sử;
- Nếu snapshot thiếu, cần recovery from source/evidence có căn cứ;
- Thêm test “đổi giá catalog sau khi chốt đơn không đổi order”.

## 48. Version hóa schema và migration

Một order có thể tồn tại nhiều năm trong khi ứng dụng đổi schema.

Ví dụ:

```text
Schema v1:
  amountTotal: double

Schema v2:
  grandTotalMinor: long
  currency: string

Schema v3:
  pricing: { subtotal, tax, discount, grandTotal }
```

### 48.1. Không giả định mọi version đều có field mới

Đọc cần:

- Schema version;
- Mapper tương thích;
- Default values chỉ khi có căn cứ;
- Migration rõ ràng;
- Data backfill;
- Tests với historical fixtures.

### 48.2. Expand-and-contract

```text
Add new fields (backward compatible)
      │
Deploy dual-readable code
      │
Backfill existing orders
      │
Reconcile amounts
      │
Switch reads to new schema
      │
Remove old fields after rollback window
```

Với dữ liệu thương mại, không chuyển Double sang decimal mà tuyên bố đã phục hồi độ chính xác nếu nguồn Double đã bị làm tròn từ trước.

### 48.3. Không sửa snapshot vì thay tên sản phẩm

Schema migration có thể đổi cấu trúc field từ `snapshot.productName` sang `snapshot.name`, nhưng **không đổi nội dung kinh tế** của snapshot.

## 49. Kiểm thử single-document atomic transitions

Một kịch bản staging:

```text
Order status = PAID, revision=8

Worker A:
  PACKING if PAID and rev=8

Worker B:
  CANCEL_REQUESTED if PAID and rev=8
```

Expected:

- Tối đa một transition match revision 8;
- Revision sau thành công = 9;
- Worker còn lại nhận conflict;
- Worker còn lại re-read và xử lý theo state machine;
- Không có `status` và payment/fulfillment fields bất nhất.

### 49.1. Tests cần concurrency thật

Một unit test đơn luồng không phát hiện race. Dùng integration test trên MongoDB test deployment, chạy nhiều concurrent requests với cùng revision và kiểm tra invariants.

### 49.2. Test trường hợp retries

- Same command ID gửi hai lần;
- Timeout sau commit;
- Duplicate webhook;
- Worker restart;
- Network disconnect;
- Primary election trong môi trường thử;
- Out-of-order carrier events.

## 50. Kiểm thử ranh giới transaction

Một test cho order + reservation + stock + outbox:

1. Chụp trạng thái trước.
2. Tạo đủ stock.
3. Chạy transaction thành công.
4. Xác minh order, reservation, stock và event cùng xuất hiện.
5. Chủ động gây lỗi giữa các thao tác trong staging.
6. Xác minh transaction abort không để trạng thái nửa vời.
7. Thử transient error/retry.
8. Thử commit outcome unknown theo khả năng test harness.
9. Xác minh idempotency và unique constraints.

### 50.1. Không test bằng cách xóa production data

Fault injection cần môi trường cô lập, fixture giả và quyền phù hợp.

### 50.2. Đừng bỏ quên external effects

MongoDB transaction test không chứng minh payment provider không double charge. Phải test saga/payment idempotency riêng bằng sandbox provider hoặc mock có mô hình timeout/duplicate.

## 51. Kiểm thử tổng tiền và snapshot bất biến

Các test nên bao gồm:

- Giá catalog đổi sau order;
- Product bị xóa/ẩn sau order;
- Discount kết thúc;
- Tax policy thay đổi;
- Shipping quote hết hạn;
- Số lượng lớn và Int64 overflow;
- Currency khác nhau;
- Refund một phần;
- Cancel một line;
- Decimal/rounding;
- Dữ liệu legacy thiếu allocation;
- Sản phẩm cùng SKU nhưng khác variant;
- Multi-tenant same orderNo.

Expected: historical order vẫn phản ánh **accepted quote/snapshot** và các điều chỉnh phải có dấu vết riêng.

## 52. Test load và contention

Một đơn hàng thường được đọc nhiều và cập nhật ít, trong khi stock hot SKU có thể được cập nhật rất nhiều.

Metrics:

```text
Checkout success rate
Order creation p95/p99
State transition conflict rate
Payment reconciliation lag
Reservation expiry backlog
Oversell anomaly count
Order duplicate count
Outbox pending age
CDC lag
MongoDB transaction abort/retry count
Stock document write contention
CPU/IO/cache/replication lag
```

### 52.1. Quản lý hot key

Nếu tất cả orders của một flash sale cùng tranh một stock document, CAS ngăn oversell nhưng có thể tăng write latency/contended retries. Điều đó cần capacity planning, queue/throttling, inventory partitioning hoặc thay chính sách giữ chỗ.

### 52.2. Đừng tăng batch và concurrency vô hạn

Một background worker xử lý 100.000 refunds/tracking updates cùng lúc có thể gây pool contention và ảnh hưởng checkout p99. Bounded queue và rate limits giúp giữ SLO.

## 53. Một flow checkout end-to-end

Sơ đồ:

```text
Client
  │
  ├── 1. GET quote
  │       └── Server calculates totals
  │
  └── 2. POST checkout + idempotencyKey
             │
             ▼
       Validate quote/tenant
             │
             ▼
       MongoDB short transaction
         ├── Claim/create checkout request
         ├── Create PENDING_PAYMENT order (snapshot)
         ├── Conditionally reserve inventory
         └── Write outbox PaymentRequested
             │
             ▼
       Commit
             │
             ▼
       Worker calls payment provider (outside transaction)
             │
             ▼
       Provider webhook/response
             │
             ▼
       Verify + dedupe + reconcile
             │
             ▼
       MongoDB short transaction
         ├── Update order with CAS
         ├── Record payment attempt/ledger
         ├── Commit reservation as applicable
         └── Outbox OrderPaid / PaymentFailed
             │
             ▼
       Fulfillment consumes event
             │
             ▼
       Shipment with own state and retries
```

### 53.1. Có thể tách đặt reservation sang saga riêng

Trong một số deployment có nhiều warehouses hoặc inventory service độc lập, bước reserve không nằm cùng MongoDB transaction với order. Khi đó cần outbox/saga và compensation/timeout. Không ép các service khác cluster cùng tham gia một MongoDB transaction.

### 53.2. Idempotency request và provider request khác nhau

Phải có IDs ổn định ở cả hai lớp:

```text
checkout idempotency key
order ID
stock reservation ID
payment provider idempotency key
payment attempt ID
webhook provider event ID
outbox event ID
shipment request ID
refund request ID
```

Mỗi ID bảo vệ một loại retry/concurrency khác nhau.

## 54. Một flow hủy đơn có thanh toán chưa rõ

```text
User asks cancel
       │
       ▼
CAS order → CANCEL_REQUESTED
       │
       ▼
Check payment provider state
       │
       ├── Not captured
       │     └── Cancel payment intent
       │           └── Release reservation
       │                 └── CANCELLED
       │
       ├── Captured
       │     └── Request refund with stable key
       │           └── REFUND_PENDING
       │                 └── On confirmed refund → CANCELLED/CLOSED
       │
       └── Unknown
             └── RECONCILIATION_REQUIRED
                    └── Query/retry safely
```

Không trả cho người dùng “Đã hủy và tiền hoàn về” khi chưa có bằng chứng từ provider. UI có thể hiển thị “Đang xử lý hủy/hoàn tiền” theo domain contract.

## 55. Bảng quyết định thiết kế

| Câu hỏi | Cách chọn thường phù hợp |
|---|---|
| Chi tiết sản phẩm trong đơn lấy ở đâu? | Snapshot đã chốt trên order |
| Thông tin sản phẩm hiện tại? | Reference catalog |
| Giá và currency? | Snapshot, đơn vị và rounding rõ |
| Một đơn có ít line items? | Embed items |
| Hàng nghìn line items và updates độc lập? | Cân nhắc order_lines riêng |
| Chuyển một status trên một order? | Atomic conditional update/CAS |
| Order và outbox phải cùng commit? | MongoDB transaction hoặc single-document design |
| Order và stock cùng MongoDB? | Transaction nếu có invariant xuyên docs |
| Gọi cổng thanh toán? | Saga/outbox/idempotency, không giữ MongoDB tx |
| Tồn kho chung? | Collection/service độc lập, conditional decrement |
| Reservation hết hạn? | Expiry worker + idempotent release; không phụ thuộc TTL |
| Webhook bị lặp? | Verify/dedupe provider event ID |
| Hoàn tiền nhiều lần? | Refund ledger + provider idempotency |
| Cần audit dài hạn? | Event/ledger collection riêng |
| Query lịch sử nhiều? | Compound index/read model |
| Nhiều tenants? | Tenant-scoped auth, IDs/index/sharding |
| Document lớn? | Bounded embedded data, references |
| Schema đổi theo thời gian? | Versioned migration + backward compatibility |

## 56. Anti-patterns thường gặp

| Anti-pattern | Tác hại | Hướng sửa |
|---|---|---|
| Order chỉ lưu `productId`, xem lại giá catalog | Đơn cũ đổi giá | Snapshot price/name/variant |
| Frontend tự gửi giá phải thu | Price tampering | Server-side quote verification |
| Dùng `double` cho tiền không kiểm chứng | Rounding | Int64 minor units/Decimal128 |
| Không lưu currency | Cộng sai đơn vị | Currency ở order và payment |
| Chỉ một `status` cho mọi luồng | State explosion | Substates + invariants |
| `$set` status tùy ý | Race, chuyển trái phép | FSM + conditional update |
| Không dùng revision | Lost update | Optimistic concurrency |
| `matchedCount=0` thì retry không điều kiện | Ghi đè status mới | Re-read và quyết định |
| Đọc stock rồi trừ sau | Oversell | Atomic conditional `$inc` |
| TTL reservation nghĩa tự hoàn kho | Mất stock | Expiry workflow + release |
| Payment HTTP trong MongoDB transaction | Long tx, không atomic external | Saga/outbox |
| DB commit rồi publish không durable | Lost event | Transactional outbox |
| Outbox nghĩa exactly-once | Duplicate downstream | Consumer idempotency |
| Webhook nào đến cuối thì thắng | State regression | Event verification + state rules |
| Retry refund không key | Double refund | Stable provider idempotency |
| Refund làm sửa grand total | Mất lịch sử | Separate refund/ledger records |
| Embed toàn bộ raw webhook events | Document quá lớn | Separate bounded event store |
| Lưu thẻ/token bí mật trong snapshot | Rủi ro bảo mật | Provider references |
| Unique orderNo bằng app check | Duplicate race | Unique index |
| Không tenant scope trong update | Cross-tenant corruption | Auth + tenant-scoped filter |
| Không xác minh shard key/unique | Constraint lỗi | Version-specific sharding design |
| Schema validation thay FSM | Không ngăn chuyển sai | Domain guards |
| Restore old backup mà app không đọc được | Mapping error | Schema version/compat tests |
| Xóa orders bằng TTL tùy tiện | Mất chứng từ | Retention/archival policy |
| Chỉ test happy path | Lỗi ở retry/failover | Concurrency/fault tests |
| UI hiển thị PAID theo redirect | Sai thanh toán | Provider-confirmed status |

## 57. Bài tập thực hành

### Bài 1 — Phân loại snapshot và reference

Với các field: `productId`, `productName`, `currentProductPrice`, `unitPriceAtCheckout`, `sellerId`, `inventoryAvailable`, `shippingAddress`, `paymentIntentId`, `providerSecret`, `trackingEvents`, hãy quyết định field nào được snapshot trong order, field nào tham chiếu collection/service khác và field nào không được lưu.

### Bài 2 — Thiết kế order document

Viết một document MongoDB có:

- Tenant và order identity;
- Hai line items;
- Product snapshot;
- Int64 monetary fields và currency;
- Discount, tax, shipping;
- Delivery snapshot;
- Status và revision;
- Payment reference.

Kiểm tra công thức total.

### Bài 3 — Giá đổi sau chốt

Ngày T0 khách đặt product P giá 200000; ngày T1 catalog đổi 260000.

1. Trang lịch sử phải hiển thị giá nào?
2. `productId` còn dùng làm gì?
3. Nếu product bị xóa thì sao?
4. Khi hoàn tiền tính trên dữ liệu nào?
5. Test nào phát hiện lỗi truy lại current price?

### Bài 4 — State machine

Thiết kế chuyển trạng thái:

```text
CREATED, PENDING_PAYMENT, PAID, PACKING,
SHIPPED, DELIVERED, CANCEL_REQUESTED, CANCELLED
```

Viết ma trận các chuyển hợp lệ/không hợp lệ và nguyên nhân.

### Bài 5 — CAS

Hai workers đồng thời đọc `PAID`, `revision=8`.

1. Viết `updateOne` cho worker chuẩn bị hàng.
2. Viết `updateOne` cho worker hủy.
3. Chứng minh tối đa một lệnh match revision 8.
4. Worker thất bại cần làm gì?
5. Vì sao không update theo `_id` đơn thuần?

### Bài 6 — Đọc kết quả sau cập nhật

Viết Java Sync Driver `findOneAndUpdate` dùng `ReturnDocument.AFTER` để chuyển `PAID→PACKING`, yêu cầu tenant scope và revision. Xử lý trường hợp trả `null`.

### Bài 7 — Giữ chỗ tồn kho

Một stock record `available=1`; hai khách cùng đặt mỗi người 1.

1. Vì sao read-then-write có thể oversell?
2. Viết conditional `$inc`.
3. Tại sao `matchedCount=0` không phải lỗi mạng?
4. Reservation cần fields nào?
5. Release khi hủy như thế nào để không cộng hai lần?

### Bài 8 — TTL reservation

Reservation hết hạn sau 15 phút.

1. TTL có tự cập nhật `inventory.available` không?
2. Viết trạng thái `HELD→EXPIRED`.
3. Cần transaction hay compensation ở đâu?
4. Nếu worker xử lý hai lần?
5. Khi nào xóa reservation history?

### Bài 9 — Ranh giới transaction

Phân loại những cặp thao tác:

- Đổi `status` và `revision` trong một order;
- Insert order và insert outbox;
- Giảm stock và tạo reservation;
- Ghi MongoDB và gọi payment gateway;
- Tạo shipment record và gọi carrier;
- Ghi payment ledger và cập nhật order summary.

Giải thích khi nào dùng single-document atomicity, multi-document transaction hoặc saga.

### Bài 10 — Transaction lỗi giữa chừng

Trong staging, tạo order và reservation trong transaction; gây lỗi trước commit. Kiểm tra expected DB state, rồi thử commit unknown và idempotency.

### Bài 11 — Payment callback duplicate

Provider gửi sự kiện capture 660000 hai lần.

1. Unique key nào?
2. Có nên dùng `$inc` captured amount không?
3. Khi event đã xử lý, làm gì?
4. Khi provider và order status mâu thuẫn?
5. Reconciliation job cần dữ liệu nào?

### Bài 12 — Cancel/capture race

Tái hiện hai luồng cancel và capture.

1. Chọn trạng thái trung gian.
2. CAS filter là gì?
3. Khi capture đã xảy ra mà order cancel thì sao?
4. Refund cần idempotency thế nào?
5. UI nên hiển thị gì khi chưa rõ kết quả?

### Bài 13 — Outbox

Thiết kế `OrderPaid` outbox event:

- Event ID;
- Aggregate ID/revision;
- Tenant;
- Payload tối thiểu;
- Status/attempt/lease;
- Timestamp.

Giải thích vì sao dispatcher có thể publish trùng và consumer chống trùng ra sao.

### Bài 14 — Refund một phần

Order 660000 đã capture, refund 100000.

1. `grandTotal` có đổi không?
2. `capturedMinor` và `refundedMinor` là gì?
3. Chống refund > captured thế nào?
4. Giá catalog hiện tại có liên quan?
5. Audit/ledger record cần gì?

### Bài 15 — Fulfillment từng phần

Order có line L1 quantity 3, shipment A giao 1, shipment B giao 2.

1. `fulfillmentStatus` cần gì?
2. Kiểm tra shippedQuantity ≤ orderedQuantity.
3. Webhook lặp xử lý ra sao?
4. Có nên embed mọi tracking event không?
5. Carrier và order status khác nhau thế nào?

### Bài 16 — Indexes

Thiết kế indexes cho:

- Lịch sử đơn của khách;
- Orders queue `PAID`;
- Unique `(tenantId,orderNo)`;
- Checkout idempotency.

Giải thích trade-off read/write/storage và ràng buộc sharding nếu áp dụng.

### Bài 17 — Bảo mật multi-tenant

Tenant A thử truy cập order của tenant B.

1. Auth boundary ở đâu?
2. Update filter gồm fields nào?
3. Làm sao tránh leak trong logs?
4. Người bán có thể xem những line nào?
5. Dữ liệu địa chỉ nên lưu/retention ra sao?

### Bài 18 — Kiểm thử recovery

Giả lập:

```text
Order DB commit success
Payment provider captured success
Webhook lost
Worker crashed
```

Thiết kế cơ chế resume/reconciliation đảm bảo không tạo đơn thứ hai hoặc thu tiền lần nữa.

### Bài 19 — Schema migration

Chuyển từ `total: double` sang `pricing.grandTotalMinor: long`.

1. Viết plan expand-and-contract.
2. Khi nào không thể khôi phục decimal precision gốc?
3. Backfill có cần kiểm chứng theo ledger không?
4. Bao giờ bật strict schema validator?
5. Khi nào được xóa field cũ?

### Bài 20 — Review thiết kế

Một đội đề xuất:

```text
orders:
  items reference catalog only
  paymentStatus string
  status modified by any service
  inventoryAvailable embedded
  all webhook events embedded
  retry on every error
```

Liệt kê các rủi ro về lịch sử giá, concurrency, oversell, document growth, idempotency và bảo mật. Đề xuất thay thế có ranh giới rõ ràng.

## 58. Checklist trước khi phát hành tính năng đơn hàng

### Snapshot và tiền

- [ ] Snapshot tên/variant/SKU/giá theo thời điểm xác nhận.
- [ ] Catalog reference còn dùng cho chức năng hiện tại, không thay lịch sử.
- [ ] Quote/pricing được backend xác thực.
- [ ] Monetary type, currency và scale được định nghĩa.
- [ ] Công thức subtotal/discount/tax/shipping/total được test.
- [ ] Rounding và discount allocation có quy tắc.
- [ ] Snapshot không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] Giá lịch sử không đổi khi seller cập nhật catalog.

### Trạng thái và đồng thời

- [ ] Có state machine và transition matrix.
- [ ] Có invariants giữa order/payment/fulfillment/refund.
- [ ] Critical updates dùng filter status/revision.
- [ ] Xử lý `matchedCount=0` như conflict/condition, không retry mù.
- [ ] Status transitions được audit.
- [ ] Không có arrays lịch sử tăng vô hạn.
- [ ] Có tests cho cancel/capture, payment/shipping races.
- [ ] Có idempotency keys cho checkout và provider operations.

### Transaction và tích hợp

- [ ] Single-document atomicity được tận dụng đúng.
- [ ] Multi-document transaction chỉ dùng khi invariant yêu cầu.
- [ ] Transaction đủ ngắn, không gọi HTTP service ngoài trong transaction.
- [ ] Có workflow saga/compensation cho payment/fulfillment.
- [ ] Inventory reservation chống oversell.
- [ ] Release stock idempotent, không phụ thuộc TTL tự hoàn stock.
- [ ] Outbox/event delivery bền vững và consumer dedupe.
- [ ] Có kế hoạch reconcile unknown payment outcomes.
- [ ] Refund/ledger operations có unique IDs và amount checks.

### Vận hành và dữ liệu

- [ ] Indexes dựa trên query shapes thực.
- [ ] Unique constraints phù hợp tenant/shard key.
- [ ] Schema validator có version/migration.
- [ ] Có monitoring p95/p99, conflicts, payment/CDC lag.
- [ ] Backup/restore và schema backward compatibility được thử.
- [ ] PII có RBAC/encryption/retention thích hợp.
- [ ] Có runbook cho payment captured nhưng order chưa PAID.
- [ ] Có runbook cho order cancelled sau capture.
- [ ] Có đủ capacity cho peak SKU/hot inventory.
- [ ] Có kiểm thử lỗi mạng, duplicate events và process crash.

## 59. Runbook xử lý bất nhất đơn hàng

Một mẫu:

```text
INCIDENT ID:
START TIME:
TENANT / ORDER SCOPE:
BUSINESS IMPACT:
OWNER:

SYMPTOM:
  Order status:
  Payment provider status:
  Reservation status:
  Shipment status:

EVIDENCE:
  Order _id / revision:
  Checkout idempotency key:
  Payment intent / event IDs:
  Reservation IDs:
  Outbox event IDs:
  Redacted logs / traces:

CLASSIFICATION:
  Duplicate request
  Lost/late webhook
  Unknown payment outcome
  Inventory oversell
  Invalid transition
  Schema migration issue
  External service outage

CONTAINMENT:
  Pause offending worker?
  Restrict duplicate retries?
  Alert support/payment operations?

RECOVERY:
  Read provider authoritative result
  Reconcile ledger
  CAS order state transition
  Refund or release stock as needed
  Replay/dedupe outbox
  Validate fulfillment state

POSTCONDITIONS:
  No duplicate charge/refund
  No oversell
  Financial amounts reconcile
  Snapshot unchanged
  All transitions authorized
  Audit complete

DECISION:
  GO / HOLD / RECOVER / ESCALATE
```

Không tự sửa production bằng `$set:{status:"PAID"}` khi chưa xác minh tiền thật, provider event identity và các invariant liên quan.

## 60. Tài liệu tham khảo

Khi triển khai thực tế, đối chiếu **MongoDB Server, Java Driver và topology** đang dùng:

- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Embedded Data vs References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB `findAndModify`](https://www.mongodb.com/docs/manual/reference/command/findAndModify/)
- [MongoDB `updateOne`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB `$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/)
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Atlas Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)

## Kết luận

Thiết kế đơn hàng trong MongoDB đòi hỏi nhiều hơn một collection có các field `items`, `total` và `status`. Một đơn hàng là **bản ghi cam kết thương mại và tiến trình thực hiện cam kết đó**.

**Bản chụp dữ liệu** giữ giá, số lượng, discount, tax, shipping và thông tin hiển thị cần thiết tại thời điểm xác nhận. Nhờ đó, đơn và hóa đơn lịch sử không bị thay đổi bởi catalog, bảng giá hay chương trình ưu đãi về sau. Reference tới product/customer vẫn hữu ích nhưng không thể thay snapshot.

**Trạng thái** phải được quản lý bằng state machine, invariants và cập nhật có điều kiện trên `_id`/tenant/status/revision. MongoDB giúp thay đổi nhiều field trong một document một cách nguyên tử, nhưng tính hợp lệ của chuyển trạng thái vẫn do domain logic và bằng chứng nghiệp vụ quyết định.

**Ranh giới giao dịch** cần dựa trên những gì thực sự phải cùng commit. Trong một document, dùng single-document atomicity. Với nhiều documents MongoDB cần cùng nhất quán, dùng transaction ngắn khi phù hợp. Với payment provider, carrier hoặc hệ bên ngoài, dùng saga, outbox, idempotency, compensation và reconciliation — không kỳ vọng một MongoDB transaction tự bao trùm các cuộc gọi HTTP.

Cuối cùng, cần thiết kế cả những trường hợp khó: checkout retry, hai workers cùng đổi trạng thái, payment thành công nhưng callback mất, stock reservation hết hạn, refund một phần, shipment phân lô, webhook lặp, dữ liệu lịch sử cần giữ và schema migration. Chính những tình huống đó quyết định mô hình có an toàn khi vận hành thật hay không.

**Một thiết kế đơn hàng tốt giữ được sự thật của thời điểm đặt hàng, bảo vệ được các quy tắc chuyển trạng thái và biết rõ lúc nào phải dùng atomic update, transaction hoặc một workflow bù trừ có thể phục hồi.**

