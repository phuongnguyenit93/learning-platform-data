# Xây dựng báo cáo bằng aggregation và kiểm chứng kết quả trong MongoDB

## 1. Bài toán thực hành tổng hợp

Một hệ thống thương mại điện tử lưu đơn hàng trong MongoDB. Bộ phận vận hành muốn có báo cáo **doanh số theo tháng và theo tenant**, bao gồm:

- Số đơn hợp lệ để tính doanh số.
- Giá trị hàng hóa trước giảm giá.
- Tổng tiền giảm giá.
- Doanh số sau giảm giá nhưng trước hoàn tiền.
- Số tiền đã hoàn.
- **Doanh thu thuần theo định nghĩa của bài**: giá trị đơn sau giảm giá trừ số tiền đã hoàn.
- Giá trị đơn hàng trung bình.

Yêu cầu quan trọng hơn việc viết được một pipeline là **chứng minh số liệu đúng**. Một báo cáo chạy rất nhanh, có bảng đẹp, nhưng tính cả đơn CANCELLED hoặc nhân doanh số lên khi dùng $unwind sai vẫn là báo cáo không đáng tin.

### 1.1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Chuyển yêu cầu kinh doanh thành **định nghĩa KPI có thể kiểm thử**.
2. Thiết kế dữ liệu orders có loại tiền, số lượng, giá, giảm giá, hoàn tiền và trạng thái.
3. Dùng các aggregation stages như **$match**, **$project**, **$set**, **$group**, **$sort**, **$facet**, **$unwind** và **$lookup** đúng ngữ cảnh.
4. Xác định khoảng thời gian theo **start inclusive / end exclusive** và timezone.
5. Tính doanh số bằng số nguyên đơn vị tiền hoặc Decimal128, tránh double gây sai số.
6. Tạo báo cáo theo tenant, tháng, sản phẩm và nhóm hàng mà không nhân đôi dữ liệu.
7. Kiểm tra đối chiếu bằng **kết quả tính tay**, các bất biến số học và một truy vấn độc lập.
8. Test điều kiện biên: đơn hủy, chờ xử lý, đã hoàn tiền, hoàn một phần, ranh giới tháng.
9. Sử dụng explain/index để tối ưu và xác định vấn đề tài nguyên của aggregation.
10. Gọi pipeline từ Java Sync Driver hoặc Spring Data MongoDB.
11. Thiết kế báo cáo có thể lặp lại, xuất CSV/JSON, theo dõi data quality và phát hiện regression.
12. Phân biệt **đúng logic tính toán**, **đúng tập dữ liệu**, **đúng thời điểm quan sát** và **đúng quyền truy cập**.

### 1.2. Sơ đồ tổng quan

~~~text
Business question + KPI contract
             |
             v
   Data types / sample fixtures
             |
             v
    $match scope + time + status
             |
             v
   $project / $set derived fields
             |
             v
   $group tenant + calendar month
             |
             v
     $sort / format / export
             |
             v
   Independent verification
     |        |         |
  Hand math  Invariants  Data quality
             |
             v
    explain / index / monitoring
~~~

**Nguyên tắc:** Không viết aggregation trước khi biết chính xác **dữ liệu nào được tính, công thức nào áp dụng, đơn vị nào dùng và khi nào một số liệu được coi là đúng**.

## 2. Chốt hợp đồng nghiệp vụ của báo cáo

### 2.1. Phạm vi dữ liệu

Trong bài, mỗi document tương ứng **một đơn hàng**. Mỗi đơn thuộc một **tenantId** và có **createdAt** là BSON Date.

Báo cáo chính lấy khoảng:

~~~text
2026-01-01T00:00:00.000Z
           <= createdAt <
2026-03-01T00:00:00.000Z
~~~

Tức là toàn bộ tháng 01 và tháng 02 năm 2026 **theo UTC**. Ngày 01/03 bị loại trừ.

Các trạng thái được tính:

~~~text
PAID
PARTIALLY_REFUNDED
REFUNDED
~~~

Các trạng thái bị loại:

~~~text
PENDING
CANCELLED
~~~

Một đơn đã hoàn tiền toàn bộ **vẫn được đếm trong orderCount** vì nó từng là đơn đã ghi nhận, nhưng phần thực thu sau hoàn tiền bằng 0. Đây là một **quy ước của báo cáo thực hành**, không phải quy tắc chung cho mọi hệ thống kế toán.

### 2.2. Công thức KPI cho một đơn

Đơn hàng có các fields:

| Field | Nghĩa | Kiểu lưu trong bài |
|---|---|---|
| **subtotalUnits** | Tổng số lượng × đơn giá của từng line item, trước giảm giá | BSON Int64 |
| **discountUnits** | Tổng giảm giá trên đơn, không âm | BSON Int64 |
| **totalUnits** | Giá trị đơn sau giảm giá, trước hoàn tiền | BSON Int64 |
| **refundUnits** | Số tiền đã hoàn của đơn | BSON Int64 |
| **realizedUnits** | Phần thuần sau hoàn tiền, tính trong pipeline | BSON numeric |

Các công thức:

\[
\text{subtotal}=\sum_{i=1}^{n}(\text{quantity}_i\times\text{unitPrice}_i)
\]

\[
\text{total}=\text{subtotal}-\text{discount}
\]

\[
\text{realized}=\text{total}-\text{refund}
\]

Giả định dữ liệu hợp lệ:

~~~text
0 <= discountUnits <= subtotalUnits
0 <= refundUnits <= totalUnits
quantity > 0
unitPriceUnits >= 0
~~~

Không dùng giá trị âm để biểu diễn một refund trong ví dụ: refundUnits là **số không âm được trừ khỏi total**. Một mô hình ledger thật có thể có entries âm/dương, settlement và fees; khi ấy cần đổi công thức theo contract chính thức.

### 2.3. Định nghĩa KPI của một nhóm báo cáo

Với tập đơn được chọn \(O\):

| KPI | Định nghĩa |
|---|---|
| **orderCount** | \(\lvert O\rvert\) |
| **grossUnits** | Tổng subtotalUnits |
| **discountUnits** | Tổng discountUnits |
| **netUnits** | Tổng totalUnits |
| **refundedUnits** | Tổng refundUnits |
| **realizedUnits** | Tổng (totalUnits − refundUnits) |
| **averageOrderValueUnits** | netUnits / orderCount |

Hai bất biến nhóm:

\[
\text{grossUnits}-\text{discountUnits}=\text{netUnits}
\]

\[
\text{netUnits}-\text{refundedUnits}=\text{realizedUnits}
\]

**Average order value** trong bài tính trên **netUnits**, không phải realizedUnits; vì vậy cần ghi tên và định nghĩa rõ. Khi chia ra số thập phân, AOV có thể là số xấp xỉ phục vụ hiển thị; không dùng floating-point result để hạch toán chính xác.

### 2.4. Đồng tiền và quyền tenant

Fixture dùng **VND**, tất cả giá trị là số nguyên theo đơn vị tiền đã được định nghĩa nhất quán. Không cộng USD, EUR và VND vào cùng một tổng nếu chưa có tỷ giá/thời điểm quy đổi.

Trong ứng dụng multi-tenant, **tenantId là ranh giới truy cập dữ liệu**. Một client thông thường phải được service cấp scope của tenant được phép; đừng tin tenantId do caller tự truyền để truy cập dữ liệu tenant khác. Báo cáo gộp tất cả tenant trong bài dành cho tài khoản phân tích có quyền tương ứng.

### 2.5. createdAt không luôn là thời điểm ghi nhận doanh thu

Doanh nghiệp thực tế có thể muốn nhóm theo:

- **createdAt**: ngày tạo đơn.
- **paidAt**: ngày thanh toán được xác nhận.
- **fulfilledAt**: ngày giao hàng.
- **refundAt**: ngày hoàn tiền.
- Ngày accounting/settlement theo kỳ kế toán.

Bài thực hành cố ý nhóm theo **createdAt**. Nếu doanh thu và refund được ghi nhận ở các kỳ khác nhau, cần mô hình events/ledger theo thời điểm phát sinh, không thể coi báo cáo createdAt là báo cáo kế toán chuẩn.

## 3. Thiết kế document và kiểu BSON

### 3.1. Một đơn hàng mẫu

~~~javascript
{
  _id: "A-001",
  tenantId: "tA",
  customerId: "c1",
  createdAt: ISODate("2026-01-05T10:00:00Z"),
  currency: "VND",
  status: "PAID",
  items: [
    {
      sku: "P1",
      category: "Accessories",
      qty: 2,
      unitPriceUnits: NumberLong("10000")
    },
    {
      sku: "P2",
      category: "Hardware",
      qty: 1,
      unitPriceUnits: NumberLong("20000")
    }
  ],
  subtotalUnits: NumberLong("40000"),
  discountUnits: NumberLong("0"),
  totalUnits: NumberLong("40000"),
  refundUnits: NumberLong("0")
}
~~~

Ở đây:

~~~text
subtotal = 2 * 10000 + 1 * 20000 = 40000
total    = 40000 - 0            = 40000
realized = 40000 - 0            = 40000
~~~

### 3.2. Vì sao lưu Int64?

Các số tiền mẫu được lưu bằng **BSON Int64 / NumberLong** nhằm tránh phép cộng tiền qua binary double. Khi làm việc trong Java có thể dùng **long** nếu domain giới hạn trong 64-bit và kiểm tra overflow.

Với tiền thập phân hoặc nhiều currency có scale khác nhau, **BigDecimal trong Java và BSON Decimal128** là một lựa chọn khác, kèm kiểm soát precision/exponent. Không chuyển Decimal128 sang double để xuất báo cáo tài chính rồi coi kết quả là tuyệt đối chính xác.

### 3.3. Giá trị gốc và giá trị dẫn xuất

Trong schema này, **subtotalUnits** và **totalUnits** là giá trị đã lưu. Khi tính báo cáo, ta còn có thể kiểm tra lại subtotal từ items, và total từ subtotal−discount.

Không xem dữ liệu đã lưu là đúng tuyệt đối: bug của writer cũ, sửa trực tiếp bằng mongosh hoặc migration có thể tạo document không tuân theo công thức.

### 3.4. Tránh báo cáo trên mảng items theo cách nhân đôi

Một đơn có hai items. Nếu dùng **$unwind: "$items"**, đơn đó trở thành hai pipeline documents. Nếu sau đó group và sum **"$totalUnits"**, total của cả đơn sẽ bị cộng **hai lần**.

~~~text
Order A-001: totalUnits=40000, 2 items

After $unwind:
  row P1 carries totalUnits=40000
  row P2 carries totalUnits=40000

Wrong $sum(totalUnits)=80000
Correct order total=40000
~~~

Vì vậy: **báo cáo theo đơn hàng không cần $unwind items**. Báo cáo theo SKU/category có thể $unwind, nhưng chỉ cộng **line value**, hoặc phân bổ discount/refund theo một quy tắc nghiệp vụ được định nghĩa rõ.

## 4. Chuẩn bị bộ dữ liệu cố định để kiểm chứng

Toàn bộ ví dụ dùng database **reporting_lab_460**. Đây là tên minh họa, chỉ sử dụng trong môi trường MongoDB lab được phép. **Không chạy các lệnh ghi, drop, delete hoặc migration trên database production**.

### 4.1. Helper tạo document mẫu

Trong mongosh, chọn một database test trống:

~~~javascript
const lab = db.getSiblingDB("reporting_lab_460");

function makeOrder(
  id, tenantId, isoDate, status, customerId,
  lines, subtotal, discount, refund
) {
  return {
    _id: id,
    tenantId,
    customerId,
    createdAt: ISODate(isoDate),
    currency: "VND",
    status,
    items: lines.map(([sku, category, qty, price]) => ({
      sku,
      category,
      qty,
      unitPriceUnits: NumberLong(String(price))
    })),
    subtotalUnits: NumberLong(String(subtotal)),
    discountUnits: NumberLong(String(discount)),
    totalUnits: NumberLong(String(subtotal - discount)),
    refundUnits: NumberLong(String(refund))
  };
}
~~~

Trong helper, **subtotal/discount/refund** là số nguyên JavaScript nhỏ, an toàn trong phạm vi ví dụ. Nếu seed dữ liệu có tiền lớn vượt giới hạn số nguyên chính xác của JavaScript Number, không tính bằng Number như helper; dùng **Long/Decimal128** và arithmetic phù hợp.

### 4.2. Mười hai đơn hàng minh họa

~~~javascript
lab.orders.insertMany([
  makeOrder(
    "A-001", "tA", "2026-01-05T10:00:00Z", "PAID", "c1",
    [
      ["P1", "Accessories", 2, 10000],
      ["P2", "Hardware", 1, 20000]
    ], 40000, 0, 0
  ),
  makeOrder(
    "A-002", "tA", "2026-01-12T11:00:00Z", "PAID", "c2",
    [
      ["P1", "Accessories", 1, 10000],
      ["P3", "Software", 1, 30000]
    ], 40000, 5000, 0
  ),
  makeOrder(
    "A-003", "tA", "2026-01-20T15:00:00Z", "REFUNDED", "c1",
    [
      ["P2", "Hardware", 1, 20000]
    ], 20000, 0, 20000
  ),
  makeOrder(
    "A-004", "tA", "2026-01-25T10:00:00Z", "CANCELLED", "c3",
    [
      ["P1", "Accessories", 1, 10000]
    ], 10000, 0, 0
  ),
  makeOrder(
    "A-005", "tA", "2026-02-03T08:00:00Z", "PAID", "c2",
    [
      ["P3", "Software", 2, 30000]
    ], 60000, 10000, 0
  ),
  makeOrder(
    "A-006", "tA", "2026-02-16T09:00:00Z",
    "PARTIALLY_REFUNDED", "c1",
    [
      ["P1", "Accessories", 3, 10000],
      ["P2", "Hardware", 1, 20000]
    ], 50000, 0, 10000
  ),
  makeOrder(
    "A-007", "tA", "2026-02-28T12:00:00Z", "PENDING", "c4",
    [
      ["P1", "Accessories", 1, 10000]
    ], 10000, 0, 0
  ),
  makeOrder(
    "A-008", "tA", "2026-03-01T00:00:00Z", "PAID", "c4",
    [
      ["P1", "Accessories", 1, 10000]
    ], 10000, 0, 0
  ),
  makeOrder(
    "B-001", "tB", "2026-01-09T10:00:00Z", "PAID", "c5",
    [
      ["P1", "Accessories", 4, 10000]
    ], 40000, 0, 0
  ),
  makeOrder(
    "B-002", "tB", "2026-01-23T11:00:00Z", "PAID", "c6",
    [
      ["P2", "Hardware", 2, 20000]
    ], 40000, 5000, 0
  ),
  makeOrder(
    "B-003", "tB", "2026-02-11T14:00:00Z", "REFUNDED", "c5",
    [
      ["P3", "Software", 1, 30000]
    ], 30000, 0, 30000
  ),
  makeOrder(
    "B-004", "tB", "2026-02-19T08:00:00Z", "PAID", "c6",
    [
      ["P2", "Hardware", 1, 20000],
      ["P3", "Software", 1, 30000]
    ], 50000, 0, 0
  )
]);
~~~

**Chỉ chạy insertMany một lần trên fixture trống**. Lần chạy lại cùng ID sẽ gặp duplicate key; nếu cần lặp lại bài, tạo database test mới hoặc dọn đúng các IDs test do bạn sở hữu bằng một quy trình riêng. Không tự động drop database chia sẻ.

### 4.3. Tại sao cố ý có đơn không được tính?

| Đơn | Tình huống | Kỳ vọng trong báo cáo tháng 1–2 |
|---|---|---|
| **A-004** | CANCELLED tháng 1 | Loại do trạng thái. |
| **A-007** | PENDING tháng 2 | Loại do trạng thái. |
| **A-008** | PAID đúng 00:00:00Z ngày 01/03 | Loại do ranh giới end-exclusive. |
| **A-003** | REFUNDED toàn bộ tháng 1 | Có trong orderCount, realized=0. |
| **A-006** | PARTIALLY_REFUNDED tháng 2 | Có trong orderCount, realized=40000. |
| **B-003** | REFUNDED toàn bộ tháng 2 | Có trong orderCount, realized=0. |

Những records này là **test cases có chủ đích**, không phải dữ liệu thừa.

### 4.4. Kiểm tra số lượng seed

~~~javascript
lab.orders.countDocuments({});
~~~

Kỳ vọng fixture có **12 documents**. Khi báo cáo lọc đúng phạm vi và trạng thái, chỉ có **9 đơn** tham gia aggregation.

Đếm số documents **không đủ để chứng minh KPI đúng**. Chúng ta sẽ đối chiếu cả số lượng, tổng tiền và identities ở các phần sau.

## 5. Lập bảng kiểm chứng bằng tính tay trước khi viết pipeline

### 5.1. Các đơn đủ điều kiện

| Tenant | Tháng UTC | Đơn | Subtotal | Discount | Total | Refund | Realized |
|---|---|---|---:|---:|---:|---:|---:|
| tA | 2026-01 | A-001 | 40.000 | 0 | 40.000 | 0 | 40.000 |
| tA | 2026-01 | A-002 | 40.000 | 5.000 | 35.000 | 0 | 35.000 |
| tA | 2026-01 | A-003 | 20.000 | 0 | 20.000 | 20.000 | 0 |
| tA | 2026-02 | A-005 | 60.000 | 10.000 | 50.000 | 0 | 50.000 |
| tA | 2026-02 | A-006 | 50.000 | 0 | 50.000 | 10.000 | 40.000 |
| tB | 2026-01 | B-001 | 40.000 | 0 | 40.000 | 0 | 40.000 |
| tB | 2026-01 | B-002 | 40.000 | 5.000 | 35.000 | 0 | 35.000 |
| tB | 2026-02 | B-003 | 30.000 | 0 | 30.000 | 30.000 | 0 |
| tB | 2026-02 | B-004 | 50.000 | 0 | 50.000 | 0 | 50.000 |

### 5.2. Đáp án tổng hợp theo tenant và tháng

<text>Đơn vị: VND theo fixture; các dấu chấm trong bảng là dấu phân tách hàng nghìn.</text>

| Tenant | Tháng | Order count | Gross | Discount | Net | Refunded | Realized |
|---|---|---:|---:|---:|---:|---:|---:|
| **tA** | 2026-01 | 3 | 100.000 | 5.000 | 95.000 | 20.000 | **75.000** |
| **tA** | 2026-02 | 2 | 110.000 | 10.000 | 100.000 | 10.000 | **90.000** |
| **tB** | 2026-01 | 2 | 80.000 | 5.000 | 75.000 | 0 | **75.000** |
| **tB** | 2026-02 | 2 | 80.000 | 0 | 80.000 | 30.000 | **50.000** |

Đây là **oracle** của bài: kết quả kỳ vọng đã được nêu trước khi chạy pipeline. Nếu output khác, phải điều tra nguyên nhân thay vì sửa đáp án theo output.

### 5.3. Đáp án tổng theo tháng và toàn kỳ

| Kỳ | Orders | Gross | Discount | Net | Refund | Realized |
|---|---:|---:|---:|---:|---:|---:|
| Tháng 1 | 5 | 180.000 | 10.000 | 170.000 | 20.000 | **150.000** |
| Tháng 2 | 4 | 190.000 | 10.000 | 180.000 | 40.000 | **140.000** |
| **Cả kỳ** | **9** | **370.000** | **20.000** | **350.000** | **60.000** | **290.000** |

Tự đối chiếu:

~~~text
Gross - Discount = Net
370000 - 20000  = 350000

Net - Refund = Realized
350000 - 60000 = 290000

Monthly realized
150000 + 140000 = 290000

Tenant realized
(75000 + 90000) + (75000 + 50000) = 290000
~~~

**Một invariant đúng không đảm bảo toàn bộ báo cáo đúng.** Ví dụ nếu cộng đôi mọi field do $unwind sai, cả hai phương trình vẫn có thể đúng nhưng tổng sẽ sai. Do đó cần thêm **oracle độc lập và kiểm tra số đơn/IDs**.

## 6. Xây dựng aggregation đầu tiên: theo tenant và tháng

### 6.1. Bước 1 — Đặt khoảng ngày và trạng thái

~~~javascript
const start = ISODate("2026-01-01T00:00:00.000Z");
const end = ISODate("2026-03-01T00:00:00.000Z");

const eligibleStates = [
  "PAID",
  "PARTIALLY_REFUNDED",
  "REFUNDED"
];
~~~

Lưu ý MongoDB so sánh **BSON Date là instant**, không phải chuỗi ngày hiển thị. Date objects ở đây chứa UTC instants.

### 6.2. Bước 2 — Lọc dữ liệu bằng $match

~~~javascript
{
  $match: {
    createdAt: { $gte: start, $lt: end },
    status: { $in: eligibleStates },
    currency: "VND"
  }
}
~~~

Giải thích:

- **$gte** tính cả đúng đầu kỳ.
- **$lt** không tính ngày đầu của kỳ tiếp theo.
- **$in** thể hiện chính xác ba trạng thái đủ điều kiện.
- **currency** ngăn cộng nhầm các đồng tiền khác nhau.

Nếu là báo cáo tenant-scoped, thêm **tenantId: authorizedTenantId** lấy từ authentication/authorization layer. Không nhận tenantId tùy ý từ người dùng rồi tin là đủ bảo mật.

### 6.3. Bước 3 — Chọn fields và tính realizedUnits

~~~javascript
{
  $project: {
    tenantId: 1,
    month: {
      $dateToString: {
        format: "%Y-%m",
        date: "$createdAt",
        timezone: "UTC"
      }
    },
    subtotalUnits: 1,
    discountUnits: 1,
    totalUnits: 1,
    refundUnits: 1,
    realizedUnits: {
      $subtract: ["$totalUnits", "$refundUnits"]
    }
  }
}
~~~

**$dateToString** tạo khóa tháng như **"2026-01"** theo UTC. Sử dụng timezone nhất quán để tránh một order gần nửa đêm bị đưa sang tháng khác khi chạy ở môi trường khác.

**$subtract** tính realizedUnits trên mỗi đơn trước khi group. Không trừ refund hai lần nếu upstream đã lưu **totalUnits sau refund**; đó là lý do hợp đồng dữ liệu cần rõ.

### 6.4. Bước 4 — Group và tính KPI

~~~javascript
{
  $group: {
    _id: {
      tenantId: "$tenantId",
      month: "$month"
    },
    orderCount: { $sum: 1 },
    grossUnits: { $sum: "$subtotalUnits" },
    discountUnits: { $sum: "$discountUnits" },
    netUnits: { $sum: "$totalUnits" },
    refundedUnits: { $sum: "$refundUnits" },
    realizedUnits: { $sum: "$realizedUnits" }
  }
}
~~~

**$group** gom documents theo **hai keys**: tenantId và tháng. Mỗi đơn đóng góp đúng một lần vì pipeline này **không unwind items**.

### 6.5. Bước 5 — Tính AOV và sắp xếp

~~~javascript
{
  $set: {
    averageOrderValueUnits: {
      $cond: [
        { $gt: ["$orderCount", 0] },
        { $divide: ["$netUnits", "$orderCount"] },
        null
      ]
    }
  }
}
~~~

Trong pipeline này, các groups thực tế đều có orderCount ≥ 1; **$cond** minh họa cách phòng chia cho 0 khi thay đổi logic.

Do **$divide** có thể tạo giá trị không nguyên, AOV là một metric trung bình có thể cần rounding khi hiển thị. Các tổng chính vẫn nên giữ numeric type chính xác. Chọn policy rounding và scale ở reporting/presentation layer; không dùng kết quả floating point để phát sinh transaction tiền.

### 6.6. Pipeline hoàn chỉnh có thể chạy

~~~javascript
const pipeline = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  {
    $project: {
      tenantId: 1,
      month: {
        $dateToString: {
          format: "%Y-%m",
          date: "$createdAt",
          timezone: "UTC"
        }
      },
      subtotalUnits: 1,
      discountUnits: 1,
      totalUnits: 1,
      refundUnits: 1,
      realizedUnits: {
        $subtract: ["$totalUnits", "$refundUnits"]
      }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        month: "$month"
      },
      orderCount: { $sum: 1 },
      grossUnits: { $sum: "$subtotalUnits" },
      discountUnits: { $sum: "$discountUnits" },
      netUnits: { $sum: "$totalUnits" },
      refundedUnits: { $sum: "$refundUnits" },
      realizedUnits: { $sum: "$realizedUnits" }
    }
  },
  {
    $set: {
      averageOrderValueUnits: {
        $cond: [
          { $gt: ["$orderCount", 0] },
          { $divide: ["$netUnits", "$orderCount"] },
          null
        ]
      }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.month": 1
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      month: "$_id.month",
      orderCount: 1,
      grossUnits: 1,
      discountUnits: 1,
      netUnits: 1,
      refundedUnits: 1,
      realizedUnits: 1,
      averageOrderValueUnits: 1
    }
  }
];

lab.orders.aggregate(pipeline).toArray();
~~~

Khi chạy một cell mongosh mới, phải có **lab, start, end, eligibleStates** đã khai báo ở các bước trước trong cùng session, hoặc khai báo lại các biến đó.

### 6.7. Kết quả kỳ vọng

Khi bỏ trường AOV để trình bày gọn, pipeline phải trả **bốn nhóm**:

~~~javascript
[
  {
    tenantId: "tA",
    month: "2026-01",
    orderCount: 3,
    grossUnits: NumberLong("100000"),
    discountUnits: NumberLong("5000"),
    netUnits: NumberLong("95000"),
    refundedUnits: NumberLong("20000"),
    realizedUnits: NumberLong("75000")
  },
  {
    tenantId: "tA",
    month: "2026-02",
    orderCount: 2,
    grossUnits: NumberLong("110000"),
    discountUnits: NumberLong("10000"),
    netUnits: NumberLong("100000"),
    refundedUnits: NumberLong("10000"),
    realizedUnits: NumberLong("90000")
  },
  {
    tenantId: "tB",
    month: "2026-01",
    orderCount: 2,
    grossUnits: NumberLong("80000"),
    discountUnits: NumberLong("5000"),
    netUnits: NumberLong("75000"),
    refundedUnits: NumberLong("0"),
    realizedUnits: NumberLong("75000")
  },
  {
    tenantId: "tB",
    month: "2026-02",
    orderCount: 2,
    grossUnits: NumberLong("80000"),
    discountUnits: NumberLong("0"),
    netUnits: NumberLong("80000"),
    refundedUnits: NumberLong("30000"),
    realizedUnits: NumberLong("50000")
  }
]
~~~

Đây là **dạng minh họa các fields KPI chính**, không phải dump nguyên văn: output thực tế còn có averageOrderValueUnits và cách mongosh hiển thị BSON Long phụ thuộc shell/version.

### 6.8. AOV kỳ vọng

| Tenant | Tháng | AOV = net / orders |
|---|---|---:|
| tA | 2026-01 | 95.000 / 3 ≈ **31.666,67** |
| tA | 2026-02 | 100.000 / 2 = **50.000** |
| tB | 2026-01 | 75.000 / 2 = **37.500** |
| tB | 2026-02 | 80.000 / 2 = **40.000** |

Nếu dashboard muốn AOV **sau hoàn tiền**, cần đặt tên khác, ví dụ realizedAverageUnits = realizedUnits / orderCount, thay vì thay đổi công thức dưới tên cũ.

### 6.9. $dateTrunc là một cách nhóm khác

Ở server version hỗ trợ (ví dụ MongoDB 5.0+), có thể dùng:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "month",
    timezone: "UTC"
  }
}
~~~

Khác với chuỗi **"2026-01"**, $dateTrunc trả **mốc Date** của bucket tháng. Điều này hữu ích cho time-series APIs và range operations. Chọn một output contract và giữ nhất quán; không ghép Date và String month keys trong cùng grouping khi chưa chuyển đổi.

## 7. Dùng $facet tạo nhiều góc nhìn từ cùng một tập dữ liệu

Bộ phận vận hành thường muốn một response gồm:

- Báo cáo theo **tenant + tháng**.
- Báo cáo **tất cả tenant gộp theo tháng**.
- Tổng cả kỳ.

Có thể gọi ba aggregations độc lập, nhưng khi các groups đều dùng cùng filter và KPI definitions, **$facet** cung cấp một cách tổ chức chung trong một pipeline.

### 7.1. Cấu trúc $facet

~~~text
orders
  |
  +-- $match date / states / currency
  |
  +-- $project month + derived values
  |
  +-- $facet
        |
        +-- byTenantMonth -> $group tenant/month
        |
        +-- byMonth       -> $group month
        |
        +-- overall       -> $group all
~~~

Đặt **$match trước $facet** giúp giảm tập đầu vào và cho phép MongoDB khai thác index ở giai đoạn lọc trong những trường hợp phù hợp.

### 7.2. Viết pipeline tái sử dụng các KPI

~~~javascript
const baseStages = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  {
    $project: {
      tenantId: 1,
      month: {
        $dateToString: {
          format: "%Y-%m",
          date: "$createdAt",
          timezone: "UTC"
        }
      },
      subtotalUnits: 1,
      discountUnits: 1,
      totalUnits: 1,
      refundUnits: 1,
      realizedUnits: {
        $subtract: ["$totalUnits", "$refundUnits"]
      }
    }
  }
];

const metricAccumulators = {
  orderCount: { $sum: 1 },
  grossUnits: { $sum: "$subtotalUnits" },
  discountUnits: { $sum: "$discountUnits" },
  netUnits: { $sum: "$totalUnits" },
  refundedUnits: { $sum: "$refundUnits" },
  realizedUnits: { $sum: "$realizedUnits" }
};

function groupMetrics(idExpression) {
  return {
    $group: {
      _id: idExpression,
      ...metricAccumulators
    }
  };
}

const facetPipeline = [
  ...baseStages,
  {
    $facet: {
      byTenantMonth: [
        groupMetrics({
          tenantId: "$tenantId",
          month: "$month"
        }),
        { $sort: { "_id.tenantId": 1, "_id.month": 1 } }
      ],
      byMonth: [
        groupMetrics("$month"),
        { $sort: { _id: 1 } }
      ],
      overall: [
        groupMetrics(null)
      ]
    }
  }
];

const report = lab.orders.aggregate(facetPipeline).toArray()[0];
printjson(report);
~~~

Đoạn code giả định **start, end, eligibleStates** đã khai báo. Mỗi nhánh của $facet xử lý tập documents sau baseStages; không phải mỗi nhánh đọc toàn collection lần nữa.

### 7.3. Kỳ vọng nhánh byMonth

~~~javascript
[
  {
    _id: "2026-01",
    orderCount: 5,
    grossUnits: NumberLong("180000"),
    discountUnits: NumberLong("10000"),
    netUnits: NumberLong("170000"),
    refundedUnits: NumberLong("20000"),
    realizedUnits: NumberLong("150000")
  },
  {
    _id: "2026-02",
    orderCount: 4,
    grossUnits: NumberLong("190000"),
    discountUnits: NumberLong("10000"),
    netUnits: NumberLong("180000"),
    refundedUnits: NumberLong("40000"),
    realizedUnits: NumberLong("140000")
  }
]
~~~

### 7.4. Kỳ vọng nhánh overall

~~~javascript
[
  {
    _id: null,
    orderCount: 9,
    grossUnits: NumberLong("370000"),
    discountUnits: NumberLong("20000"),
    netUnits: NumberLong("350000"),
    refundedUnits: NumberLong("60000"),
    realizedUnits: NumberLong("290000")
  }
]
~~~

### 7.5. Kiểm tra quan hệ giữa các cấp báo cáo

~~~text
sum(byTenantMonth.orderCount)
  = sum(byMonth.orderCount)
  = overall.orderCount
  = 9

sum(byTenantMonth.realizedUnits)
  = sum(byMonth.realizedUnits)
  = overall.realizedUnits
  = 290000
~~~

Nếu hai nhánh có filters khác nhau hoặc stage $unwind nằm trước $facet, các phép đối chiếu này có thể thất bại. Việc dùng cùng baseStages giúp giảm nguy cơ lệch filter.

### 7.6. Cần chú ý giới hạn $facet

$facet rất tiện cho một số report vừa phải, nhưng không có nghĩa nên trả hàng trăm nghìn groups trong một BSON response:

- Mỗi nhánh có chi phí memory/processing.
- Tài liệu kết quả phải tuân thủ BSON document size limit.
- $facet có những giới hạn bộ nhớ riêng; allowDiskUse không biến mọi giới hạn của $facet thành vô hạn.
- $sort/$group có thể cần tối ưu trước khi dùng trên tập lớn.
- Với report lớn, có thể dùng pipeline độc lập, pagination hoặc materialized results.

**Không dùng $facet chỉ vì muốn viết một lệnh thay cho ba lệnh** nếu kích thước/tài nguyên report vượt giới hạn hợp lý.

## 8. Báo cáo theo category: khi nào dùng $unwind?

Nếu câu hỏi là **nhóm hàng nào bán được nhiều giá trị hàng hóa trước giảm giá**, cần khai thác từng **items** trong đơn.

### 8.1. Tách mỗi line item

~~~javascript
{
  $unwind: "$items"
}
~~~

Sau stage này, một đơn có hai items đóng góp **hai pipeline rows**. Đây là điều đúng cho báo cáo dòng hàng, nhưng sai khi cộng toàn bộ total của đơn trên mỗi row.

### 8.2. Pipeline category gross sales

~~~javascript
const categoryPipeline = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.category",
      unitsSold: { $sum: "$items.qty" },
      lineGrossUnits: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceUnits"
          ]
        }
      },
      uniqueOrders: { $addToSet: "$_id" }
    }
  },
  {
    $project: {
      _id: 0,
      category: "$_id",
      unitsSold: 1,
      lineGrossUnits: 1,
      orderCount: { $size: "$uniqueOrders" }
    }
  },
  { $sort: { lineGrossUnits: -1, category: 1 } }
];

lab.orders.aggregate(categoryPipeline).toArray();
~~~

Ở đây **$multiply** dùng qty × unitPriceUnits để tạo gross amount cho từng item; **$addToSet** và **$size** đếm đơn duy nhất cho category, không đếm số dòng item.

### 8.3. Kỳ vọng theo category

| Category | Số lượng bán | Đơn khác nhau | Gross line value |
|---|---:|---:|---:|
| **Software** | 5 | 4 | **150.000** |
| **Hardware** | 6 | 5 | **120.000** |
| **Accessories** | 10 | 4 | **100.000** |
| **Tổng** | **21** | *Không cộng orderCount theo category* | **370.000** |

Tổng category gross:

~~~text
150000 + 120000 + 100000 = 370000
~~~

Phải bằng **overall.grossUnits** vì fixture có đúng một category cho mỗi line item và toàn bộ lines đã được tính.

**Không cộng orderCount giữa các category để suy tổng số orders**: một order có nhiều category sẽ được đếm ở nhiều nhóm. Ví dụ A-001 thuộc cả Accessories và Hardware.

### 8.4. Không gán toàn bộ discount/refund cho từng item

Một cách sai:

~~~javascript
[
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.category",
      wrongRefund: { $sum: "$refundUnits" }
    }
  }
]
~~~

Order A-006 có hai items và refundUnits=10000; nếu cộng nguyên refund trên từng line, tổng refund bị tính 20000 thay vì 10000.

Để báo cáo **net/realized theo category**, cần quy tắc **phân bổ giảm giá/hoàn tiền** (theo line refund thực, proportional allocation với rounding/remainder hoặc event-level ledger). Nếu chưa có rule đó, hãy đặt tên chính xác **category gross line value**, không gọi là doanh thu thuần theo category.

### 8.5. SKU report

Thay group category bằng SKU:

~~~javascript
{
  $group: {
    _id: "$items.sku",
    unitsSold: { $sum: "$items.qty" },
    grossUnits: {
      $sum: {
        $multiply: ["$items.qty", "$items.unitPriceUnits"]
      }
    }
  }
}
~~~

Các SKU P1/P2/P3 trong fixture tương ứng ba category, nên tổng SKU gross cũng bằng **370000**. Với production, một SKU có thể thuộc category khác theo thời gian; phải định nghĩa nhóm theo **snapshot category tại thời điểm order** hay catalog hiện tại.

## 9. $lookup: bổ sung tên sản phẩm cho báo cáo

Report theo SKU có thể cần **displayName** từ collection **products**. $lookup phù hợp khi dữ liệu tham chiếu ít hoặc có index và shape hợp lý.

### 9.1. Seed catalog lab

~~~javascript
lab.products.insertMany([
  { _id: "P1", displayName: "Travel pouch" },
  { _id: "P2", displayName: "USB hub" },
  { _id: "P3", displayName: "Software license" }
]);
~~~

Chỉ insert trên catalog lab trống, không chạy lặp với cùng IDs.

### 9.2. Join sau khi group để giảm số lần lookup

~~~javascript
const skuPipeline = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: { $sum: "$items.qty" },
      grossUnits: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceUnits"
          ]
        }
      }
    }
  },
  {
    $lookup: {
      from: "products",
      localField: "_id",
      foreignField: "_id",
      as: "product"
    }
  },
  {
    $set: {
      displayName: { $arrayElemAt: ["$product.displayName", 0] }
    }
  },
  {
    $project: {
      product: 0
    }
  },
  { $sort: { grossUnits: -1, _id: 1 } }
];

lab.orders.aggregate(skuPipeline).toArray();
~~~

Sau $group chỉ có ba SKU keys nên lookup chỉ cần bổ sung thông tin cho ba groups, thay vì join mọi line item trước khi aggregate.

### 9.3. Không để lookup thiếu làm mất doanh số

Nếu một SKU không còn trong products, **$lookup** trả mảng rỗng; displayName có thể null/missing nhưng dòng gross vẫn nên được giữ.

Nếu bạn thêm **$unwind: "$product"** không có **preserveNullAndEmptyArrays**, các nhóm SKU thiếu catalog có thể biến mất khỏi báo cáo. Điều đó gây thất thoát doanh số không được báo lỗi.

### 9.4. Category lịch sử và catalog hiện tại

Product P1 hôm nay có thể đổi category. Nếu báo cáo cần category tại thời điểm bán, dùng **items.category** là snapshot của order. Nếu báo cáo cần category hiện tại, $lookup sản phẩm rồi nhóm theo catalog. Hai báo cáo có thể cho kết quả khác mà không nhất thiết báo cáo nào sai; **định nghĩa nghiệp vụ mới quyết định**.

## 10. Kiểm chứng lớp 1 — đúng tập dữ liệu đầu vào

Trước khi kiểm tra phép tính $sum, hãy kiểm tra **những đơn hàng nào** được phép góp vào báo cáo.

### 10.1. Đếm số đơn đủ điều kiện

~~~javascript
const scope = {
  createdAt: { $gte: start, $lt: end },
  status: { $in: eligibleStates },
  currency: "VND"
};

lab.orders.countDocuments(scope);
~~~

Kỳ vọng: **9**.

### 10.2. So danh sách ID thay vì chỉ count

~~~javascript
const expectedIds = [
  "A-001", "A-002", "A-003",
  "A-005", "A-006",
  "B-001", "B-002", "B-003", "B-004"
].sort();

const actualIds = lab.orders
  .find(scope, { _id: 1 })
  .sort({ _id: 1 })
  .toArray()
  .map(order => order._id);

if (JSON.stringify(actualIds) !== JSON.stringify(expectedIds)) {
  throw new Error(
    "Selected order IDs differ from the fixture contract"
  );
}

print("Selected order IDs: PASS");
~~~

Đây là kiểm tra quan trọng: một filter sai có thể vẫn đếm được 9 đơn bằng cách bỏ nhầm một đơn và lấy nhầm một đơn khác. So IDs mới phát hiện được.

### 10.3. Kiểm tra riêng các đơn bị loại

~~~javascript
lab.orders.find(
  { _id: { $in: ["A-004", "A-007", "A-008"] } },
  { _id: 1, createdAt: 1, status: 1 }
).sort({ _id: 1 });
~~~

Giải thích kỳ vọng:

- A-004 bị loại vì **CANCELLED**.
- A-007 bị loại vì **PENDING**.
- A-008 bị loại vì **createdAt = end**, không phải vì trạng thái.

**Đừng sửa filter bằng cách thêm điều kiện ngoại lệ theo ID.** Các ID chỉ dùng làm oracle cho bộ test.

### 10.4. Kiểm tra từng tenant

~~~javascript
lab.orders.countDocuments({
  ...scope,
  tenantId: "tA"
});

lab.orders.countDocuments({
  ...scope,
  tenantId: "tB"
});
~~~

Kỳ vọng: **tA = 5**, **tB = 4**.

## 11. Kiểm chứng lớp 2 — so kết quả aggregation với oracle cố định

### 11.1. Bảng oracle dưới dạng dữ liệu test

Trong bài, các số tiền nhỏ nên có thể dùng các integer literals chính xác:

~~~javascript
const expectedGroups = new Map([
  ["tA|2026-01", {
    orders: 3, gross: 100000, discount: 5000,
    net: 95000, refund: 20000, realized: 75000
  }],
  ["tA|2026-02", {
    orders: 2, gross: 110000, discount: 10000,
    net: 100000, refund: 10000, realized: 90000
  }],
  ["tB|2026-01", {
    orders: 2, gross: 80000, discount: 5000,
    net: 75000, refund: 0, realized: 75000
  }],
  ["tB|2026-02", {
    orders: 2, gross: 80000, discount: 0,
    net: 80000, refund: 30000, realized: 50000
  }]
]);
~~~

### 11.2. Assertion không chuyển kết quả BSON Long qua double

~~~javascript
function asBigInt(value) {
  return BigInt(value.toString());
}

const actualGroups = lab.orders.aggregate(pipeline).toArray();

if (actualGroups.length !== expectedGroups.size) {
  throw new Error("Unexpected number of report groups");
}

for (const row of actualGroups) {
  const key = row.tenantId + "|" + row.month;
  const expected = expectedGroups.get(key);

  if (!expected) {
    throw new Error("Unexpected report group: " + key);
  }

  if (row.orderCount !== expected.orders
      || asBigInt(row.grossUnits) !== BigInt(expected.gross)
      || asBigInt(row.discountUnits) !== BigInt(expected.discount)
      || asBigInt(row.netUnits) !== BigInt(expected.net)
      || asBigInt(row.refundedUnits) !== BigInt(expected.refund)
      || asBigInt(row.realizedUnits) !== BigInt(expected.realized)) {
    throw new Error("KPI mismatch for " + key);
  }
}

print("Tenant/month report: PASS");
~~~

**BigInt** ở JavaScript giúp so sánh chính xác giá trị integer khi chuyển qua từ BSON Long; không dùng **Number(...)** cho những giá trị có thể vượt **Number.MAX_SAFE_INTEGER**.

Trong lab, expected integer literals nhỏ hơn giới hạn an toàn. Với oracle production-scale, dùng expected strings/BigInt hoặc Decimal128 được xử lý rõ ràng.

### 11.3. Tại sao không kiểm tra mỗi realizedUnits?

Hai errors có thể bù trừ:

~~~text
Gross report too high by 10000
Discount report too high by 10000
Net appears correct
~~~

Nếu chỉ kiểm tra net, bug ở gross/discount vẫn bị bỏ sót. Vì vậy cần so **mọi KPI quan trọng**, order counts và group keys.

### 11.4. Kiểm tra bất biến từng nhóm

~~~javascript
for (const row of actualGroups) {
  const gross = asBigInt(row.grossUnits);
  const discount = asBigInt(row.discountUnits);
  const net = asBigInt(row.netUnits);
  const refunded = asBigInt(row.refundedUnits);
  const realized = asBigInt(row.realizedUnits);

  if (gross - discount !== net) {
    throw new Error("Gross-discount != net");
  }
  if (net - refunded !== realized) {
    throw new Error("Net-refund != realized");
  }
}

print("Report invariants: PASS");
~~~

Đây là phép kiểm tra bổ sung, **không thay thế oracle**. Nếu mọi trường đều bị nhân đôi, invariants số học có thể vẫn đúng.

## 12. Kiểm chứng lớp 3 — tính độc lập ngoài aggregation

Một cách giảm rủi ro viết sai cùng một biểu thức ở hai chỗ là **đối chiếu bằng thuật toán khác**. Để minh họa, ta dùng cursor thông thường và cộng trực tiếp ở mongosh thay vì $group.

### 12.1. Independent fold qua find()

~~~javascript
const folded = new Map();

lab.orders.find(scope).forEach(order => {
  const month = order.createdAt.toISOString().slice(0, 7);
  const key = order.tenantId + "|" + month;

  if (!folded.has(key)) {
    folded.set(key, {
      count: 0,
      gross: 0n,
      discount: 0n,
      net: 0n,
      refund: 0n,
      realized: 0n
    });
  }

  const row = folded.get(key);
  const subtotal = asBigInt(order.subtotalUnits);
  const discount = asBigInt(order.discountUnits);
  const total = asBigInt(order.totalUnits);
  const refund = asBigInt(order.refundUnits);

  row.count += 1;
  row.gross += subtotal;
  row.discount += discount;
  row.net += total;
  row.refund += refund;
  row.realized += total - refund;
});

printjson(
  [...folded.entries()].map(([key, row]) => ({
    key,
    count: row.count,
    gross: row.gross.toString(),
    discount: row.discount.toString(),
    net: row.net.toString(),
    refund: row.refund.toString(),
    realized: row.realized.toString()
  }))
);
~~~

Ưu điểm:

- Nhóm tháng được xác định qua **Date.toISOString().slice(0,7)**, không qua $dateToString.
- Tính tổng bằng **BigInt** ở client, không phải $group.
- Có thể kiểm tra từng document khi có mismatch.

Hạn chế:

- Vẫn dùng **cùng dữ liệu và filter scope**. Nếu business contract sai ngay từ đầu, cả hai cách có thể cùng sai.
- Đọc tất cả matched documents về client không phù hợp cho dataset hàng triệu orders.
- Việc tính bằng mongosh ở đây chỉ dành cho **small deterministic fixture / debugging**. Production validation dùng batch sample, reconcile pipeline hoặc source-of-truth ledger thích hợp.

### 12.2. So independent fold với aggregation

~~~javascript
for (const row of actualGroups) {
  const key = row.tenantId + "|" + row.month;
  const independent = folded.get(key);

  if (!independent
      || independent.count !== row.orderCount
      || independent.gross !== asBigInt(row.grossUnits)
      || independent.discount !== asBigInt(row.discountUnits)
      || independent.net !== asBigInt(row.netUnits)
      || independent.refund !== asBigInt(row.refundedUnits)
      || independent.realized !== asBigInt(row.realizedUnits)) {
    throw new Error("Independent reconciliation failed: " + key);
  }
}

print("Independent fold reconciliation: PASS");
~~~

Khi so các nhóm, cần kiểm tra cả **số nhóm và IDs** để không bỏ sót một group mà vòng lặp không duyệt tới.

### 12.3. Đối chiếu ba nguồn bằng chứng

| Nguồn | Chứng minh | Không tự chứng minh |
|---|---|---|
| **Bảng tính tay** | Oracle độc lập cho fixture. | Tính đúng mọi dữ liệu production. |
| **Aggregation pipeline** | Kết quả của cách tính được triển khai trên MongoDB. | Business contract đúng. |
| **Client-side fold** | Một implementation độc lập cho cùng records. | Dữ liệu gốc không hỏng hoặc filter scope đúng. |

Kết hợp cả ba tốt hơn chỉ nhìn một output.

## 13. Kiểm chứng lớp 4 — chất lượng dữ liệu gốc

Aggregation có thể được viết đúng nhưng vẫn cho kết quả sai nếu một document có **totalUnits** sai, **refundUnits** vượt total hoặc kiểu tiền thay đổi thành String.

### 13.1. Kiểm tra công thức trên từng đơn

Một phép kiểm tra độc lập với reporting groups:

~~~javascript
const inconsistentTotals = lab.orders.aggregate([
  {
    $project: {
      _id: 1,
      subtotalUnits: 1,
      discountUnits: 1,
      totalUnits: 1,
      refundUnits: 1,
      recomputedTotalUnits: {
        $subtract: ["$subtotalUnits", "$discountUnits"]
      }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          {
            $ne: [
              "$totalUnits",
              "$recomputedTotalUnits"
            ]
          },
          { $lt: ["$discountUnits", 0] },
          { $gt: ["$discountUnits", "$subtotalUnits"] },
          { $lt: ["$refundUnits", 0] },
          { $gt: ["$refundUnits", "$totalUnits"] }
        ]
      }
    }
  }
]).toArray();

printjson(inconsistentTotals);
~~~

Kỳ vọng với fixture chuẩn: **mảng rỗng**. Nếu có bản ghi, không nên “sửa số cộng ở report” để che lỗi dữ liệu. Cần điều tra tại nguồn ghi/migration và có kế hoạch sửa dữ liệu được phê duyệt.

### 13.2. Tính lại subtotal từ items

~~~javascript
const badSubtotals = lab.orders.aggregate([
  {
    $project: {
      _id: 1,
      storedSubtotal: "$subtotalUnits",
      recomputedSubtotal: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.unitPriceUnits"
              ]
            }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: {
        $ne: ["$storedSubtotal", "$recomputedSubtotal"]
      }
    }
  }
]).toArray();

printjson(badSubtotals);
~~~

Với documents hợp lệ có items là mảng, **$map** tạo danh sách các line subtotals, **$sum** cộng chúng. Kỳ vọng: **không có mismatch**.

Nếu items null/missing hoặc không phải array, pipeline có thể báo lỗi hoặc mang semantics khác. Đó là lỗi schema cần kiểm tra **riêng**, không coi giá trị null/empty là một order hợp lệ có subtotal 0 theo mặc định.

### 13.3. Kiểm tra BSON types

Trong mongosh:

~~~javascript
lab.orders.aggregate([
  {
    $project: {
      _id: 1,
      createdAtType: { $type: "$createdAt" },
      subtotalType: { $type: "$subtotalUnits" },
      discountType: { $type: "$discountUnits" },
      totalType: { $type: "$totalUnits" },
      refundType: { $type: "$refundUnits" },
      itemsType: { $type: "$items" }
    }
  },
  {
    $match: {
      $or: [
        { createdAtType: { $ne: "date" } },
        { subtotalType: { $ne: "long" } },
        { discountType: { $ne: "long" } },
        { totalType: { $ne: "long" } },
        { refundType: { $ne: "long" } },
        { itemsType: { $ne: "array" } }
      ]
    }
  }
]);
~~~

Fixture yêu cầu **date**, **long** và **array** đúng như bảng schema. Một document amount **"40000"** kiểu String có thể bị $sum bỏ qua/diễn giải khác, làm report sai mà không phải lúc nào cũng phát lỗi.

### 13.4. Status values ngoài hợp đồng

~~~javascript
lab.orders.find(
  {
    status: {
      $nin: [
        "PAID",
        "PARTIALLY_REFUNDED",
        "REFUNDED",
        "PENDING",
        "CANCELLED"
      ]
    }
  },
  { _id: 1, status: 1 }
);
~~~

Nếu một writer đổi trạng thái thành **PAID_SUCCESS** mà aggregation vẫn dùng danh sách cũ, đơn hàng có thể bị loại khỏi báo cáo mà không có exception. Data quality monitoring phải phát hiện unknown values.

### 13.5. Kiểm tra quy tắc refund theo status

Ở fixture:

| Status | Refund policy của bài |
|---|---|
| PAID | refundUnits = 0 |
| PARTIALLY_REFUNDED | 0 < refundUnits < totalUnits |
| REFUNDED | refundUnits = totalUnits |
| PENDING / CANCELLED | Không tham gia báo cáo |

Trong production, refunds có thể được xử lý riêng theo events và trạng thái đơn hàng không bao quát hết lịch sử. **Không dùng status policy của fixture để sửa dữ liệu thật nếu domain contract khác.**

### 13.6. Ví dụ truy vấn tìm violation của trạng thái

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      $or: [
        {
          status: "PAID",
          $expr: { $ne: ["$refundUnits", 0] }
        },
        {
          status: "REFUNDED",
          $expr: { $ne: ["$refundUnits", "$totalUnits"] }
        },
        {
          status: "PARTIALLY_REFUNDED",
          $expr: {
            $or: [
              { $lte: ["$refundUnits", 0] },
              { $gte: ["$refundUnits", "$totalUnits"] }
            ]
          }
        }
      ]
    }
  },
  { $project: { _id: 1, status: 1, totalUnits: 1, refundUnits: 1 } }
]);
~~~

Kỳ vọng không trả record nào trong fixture. Với production, một chính sách kiểm chứng phải được version hóa và review cùng team nghiệp vụ.

### 13.7. Kiểm tra referential integrity

Document có **items.sku** nhưng product catalog không có SKU đó. MongoDB không tự cung cấp foreign key constraint tương đương RDBMS ở mọi schema.

Nếu báo cáo cần displayName:

- Kiểm tra missing products bằng $lookup.
- Không loại order/item khỏi doanh số chỉ vì catalog thiếu.
- Có fallback label như **Unknown SKU** nếu reporting contract cho phép.
- Lập danh sách data quality issues để sửa tại nguồn.

### 13.8. Validation tại nguồn ghi

Cân nhắc kết hợp:

- Schema validation (**$jsonSchema**) cho types và required fields.
- Application/domain validation cho formula/business rules.
- Unique indexes cho IDs/các ràng buộc thể hiện được.
- Data quality report định kỳ.
- Migration/backfill có audit khi schema thay đổi.

Không xem MongoDB collection validator là công cụ duy nhất bảo đảm công thức **sum(items) − discount = total** hoặc authorization; các điều kiện phức tạp vẫn cần logic ứng dụng và kiểm chứng.

## 14. Kiểm chứng thời gian, timezone và kỳ báo cáo

### 14.1. Tại sao dùng [start, end)?

Giả sử báo cáo tháng 1:

~~~text
2026-01-01T00:00:00Z <= createdAt
createdAt < 2026-02-01T00:00:00Z
~~~

Báo cáo tháng 2:

~~~text
2026-02-01T00:00:00Z <= createdAt
createdAt < 2026-03-01T00:00:00Z
~~~

Không có khoảng trống hoặc chồng lấn giữa hai kỳ. Nếu dùng **$lte end**, một order đúng 00:00 đầu tháng sau có thể bị tính **hai lần**.

### 14.2. Vì sao không dùng 23:59:59.999?

Một cách dễ sai:

~~~javascript
{
  createdAt: {
    $gte: ISODate("2026-01-01T00:00:00Z"),
    $lte: ISODate("2026-01-31T23:59:59Z")
  }
}
~~~

Truy vấn trên bỏ sót gần một giây cuối tháng (và dễ bị thay đổi do độ chính xác timestamp). Dùng **$lt đầu kỳ tiếp theo** dễ quản lý hơn.

### 14.3. Báo cáo theo Asia/Ho_Chi_Minh

Giả sử business calendar dùng UTC+07:00. Tháng 1–2 năm 2026 theo local timezone tương ứng với UTC bounds:

~~~text
Start local: 2026-01-01 00:00:00 +07
Start UTC:   2025-12-31 17:00:00Z

End local:   2026-03-01 00:00:00 +07
End UTC:     2026-02-28 17:00:00Z
~~~

Trong $match dùng **hai UTC instants đúng**. Trong $dateToString dùng:

~~~javascript
{
  $dateToString: {
    format: "%Y-%m",
    date: "$createdAt",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

**Không** giữ UTC bounds của ví dụ gốc rồi chỉ đổi timezone trong $dateToString: tập orders đầu vào có thể thiếu/ thừa ở ranh giới.

### 14.4. Một order gần nửa đêm

~~~text
createdAt = 2026-02-28T18:00:00Z
UTC calendar month = 2026-02
Ho Chi Minh City local = 2026-03-01 01:00
Local calendar month = 2026-03
~~~

Hai kết quả nhóm tháng khác nhau nhưng đều đúng nếu báo cáo khai báo timezone khác nhau. Một report không ghi timezone là **report có hợp đồng mơ hồ**.

### 14.5. Không chỉ dựa vào createdAt để ghi nhận refund

Một đơn ngày 20/01 được hoàn tiền ngày 10/02. Với dữ liệu model hiện tại, nếu chạy lại báo cáo **theo createdAt** vào tháng 3, realized của **tháng 1** sẽ giảm vì refundUnits của order đã thay đổi.

Nếu sản phẩm yêu cầu **refund tháng 2 chỉ ảnh hưởng tháng 2**, cần refund events có timestamp hoặc ledger entries và aggregation theo posting date.

### 14.6. As-of snapshot

Để báo cáo có thể đối chiếu sau nhiều tuần, ghi thêm:

~~~text
reportPeriodStart
reportPeriodEnd
timezone
statusPolicyVersion
metricDefinitionVersion
computedAt
dataWatermark / snapshot reference
sourceCollection
generationId
~~~

**computedAt không tự làm mọi query đọc snapshot đồng nhất.** Nếu data thay đổi liên tục, chọn read concern/snapshot strategy hoặc immutable data-cut/watermark theo khả năng deployment và yêu cầu nghiệp vụ.

## 15. Kiểm tra hiệu năng aggregation bằng explain

Aggregation đúng chưa đủ nếu sau sáu tháng collection có 300 triệu orders và pipeline vượt SLO. Cần quan sát **số documents quét, indexes, thời gian và bộ nhớ**.

### 15.1. Đẩy $match lên đầu

Tốt:

~~~text
$match(date, status, tenant, currency)
  -> $project
  -> $group
  -> $sort
~~~

Không tối ưu nếu:

~~~text
$unwind(items of all orders)
  -> $lookup(products for all rows)
  -> $group
  -> $match(date, status)
~~~

Trong ví dụ thứ hai, việc tạo hàng triệu intermediate rows trước khi lọc có thể rất đắt. MongoDB optimizer có thể đẩy một số predicates qua stages trong tình huống phù hợp, nhưng **không dựa vào suy đoán**, hãy xem explain.

### 15.2. Index cho báo cáo theo một tenant

Ví dụ một candidate index:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    currency: 1,
    status: 1,
    createdAt: 1
  },
  { name: "ix_tenant_currency_status_date" }
);
~~~

Phù hợp để **đánh giá** khi query luôn có tenantId/currency/status và khoảng createdAt. Không mặc định index này tốt nhất: thứ tự cột cần dựa trên selectivity, $in cardinality, truy vấn thực tế và write overhead.

### 15.3. Index cho báo cáo toàn tenant theo khoảng ngày

Một candidate khác:

~~~javascript
lab.orders.createIndex(
  {
    currency: 1,
    status: 1,
    createdAt: 1,
    tenantId: 1
  },
  { name: "ix_currency_status_date_tenant" }
);
~~~

Chỉ tạo indexes bổ sung khi workload có nhu cầu và chi phí maintenance hợp lý. Mỗi index tiêu tốn disk, memory/cache và làm inserts/updates đắt hơn.

### 15.4. Dùng explain

~~~javascript
lab.orders.explain("executionStats").aggregate(pipeline);
~~~

Những điểm quan sát:

- Winning query plan có **IXSCAN** hay **COLLSCAN** ở phần đọc đầu vào?
- **totalKeysExamined** và **totalDocsExamined** so với số đơn matched?
- Có blocking group/sort lớn hoặc spilled data không?
- Aggregation sử dụng thời gian ở giai đoạn nào?
- Có $lookup truy cập collection được index không?
- Trả bao nhiêu nhóm, thời gian thực thi bao lâu?

Hình dạng explain output khác nhau theo MongoDB version và query engine; không assume mọi field nằm ở một JSON path cố định. Với 12 documents trong lab, **COLLSCAN có thể là plan hợp lý** và execution time nhỏ không chứng minh query sẽ tốt ở quy mô production.

### 15.5. allowDiskUse và các giới hạn

~~~javascript
lab.orders.aggregate(
  pipeline,
  {
    allowDiskUse: true,
    maxTimeMS: 30000
  }
).toArray();
~~~

**allowDiskUse** cho phép những blocking stages được hỗ trợ sử dụng temporary disk khi cần theo server/version configuration. Nó **không** sửa data model sai, query không có index hoặc mọi giới hạn memory của $facet.

**maxTimeMS** đặt giới hạn thời gian thực thi server-side ở mức command, không thay thế mọi client/network/request deadlines. Chọn theo SLO, không copy 30000 ms cho mọi use case.

### 15.6. Rủi ro $group và $addToSet trên tập lớn

Trong category report, dùng:

~~~javascript
uniqueOrders: { $addToSet: "$_id" }
~~~

để đếm số orders khác nhau. Với hàng triệu order IDs trong một category, mảng set có thể tiêu thụ nhiều memory.

Một cách khác là **hai tầng group**:

~~~javascript
[
  { $match: scope },
  { $unwind: "$items" },
  {
    $group: {
      _id: {
        category: "$items.category",
        orderId: "$_id"
      },
      unitsPerOrder: { $sum: "$items.qty" },
      grossPerOrder: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceUnits"
          ]
        }
      }
    }
  },
  {
    $group: {
      _id: "$_id.category",
      orderCount: { $sum: 1 },
      unitsSold: { $sum: "$unitsPerOrder" },
      grossUnits: { $sum: "$grossPerOrder" }
    }
  }
]
~~~

Tầng thứ nhất mỗi **order/category** có một dòng, tầng thứ hai đếm số dòng. Cách này tránh giữ một $addToSet gồm toàn bộ order IDs trong một output group, nhưng vẫn có chi phí tạo nhiều intermediate groups; cần đo trên dataset thực tế.

### 15.7. $lookup trên collection lớn

Với product join:

- Join theo **products._id** đã có unique index.
- Nên **group trước rồi lookup** nếu chỉ cần metadata cho một số SKU.
- Dùng projection để giảm fields trả về.
- Xử lý SKU không tìm thấy mà không làm mất gross value.
- Xem sharding/lookup limitations theo deployment/version.

Không thực hiện one-to-many join rồi group order totals mà không kiểm soát row multiplication.

### 15.8. Giới hạn thời gian và size của report

Một report sản xuất nên có:

~~~text
Max requested date range
Authorized tenant scope
Query timeout and retry policy
Expected number of groups
Pagination/materialization strategy
Resource budget
Observability
~~~

Không để endpoint công khai cho phép tùy ý aggregation trên 10 năm dữ liệu của mọi tenant mà không có access control và giới hạn tải.

## 16. Materialize báo cáo khi tính toán lặp lại

Một dashboard được mở hàng nghìn lần/ngày không nhất thiết phải aggregate toàn bộ orders mỗi lần. Có thể dùng **materialized reporting collection**.

### 16.1. Lược đồ kết quả

~~~javascript
{
  tenantId: "tA",
  month: "2026-01",
  reportVersion: "v1",
  orderCount: 3,
  grossUnits: NumberLong("100000"),
  discountUnits: NumberLong("5000"),
  netUnits: NumberLong("95000"),
  refundedUnits: NumberLong("20000"),
  realizedUnits: NumberLong("75000"),
  computedAt: ISODate("2026-03-02T00:00:00Z")
}
~~~

Ghi rõ reportVersion, kỳ và computedAt để consumer biết kết quả được tính theo công thức nào và lúc nào.

### 16.2. Tạo unique key cho $merge

Trong database test:

~~~javascript
lab.monthly_order_reports.createIndex(
  { tenantId: 1, month: 1, reportVersion: 1 },
  {
    name: "uq_tenant_month_report_version",
    unique: true
  }
);
~~~

Các fields dùng trong mảng **on** của $merge cần có unique index phù hợp và tuân thủ các giới hạn theo version/deployment. Không tạo index trên một collection production có dữ liệu trùng chưa khảo sát.

### 16.3. Ghi report bằng $merge

~~~javascript
const reportGeneratedAt = new Date();

const materializePipeline = [
  ...pipeline,
  {
    $set: {
      reportVersion: "v1",
      computedAt: reportGeneratedAt
    }
  },
  {
    $merge: {
      into: "monthly_order_reports",
      on: ["tenantId", "month", "reportVersion"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
];

lab.orders.aggregate(materializePipeline).toArray();
~~~

Pipeline gốc đã tạo **tenantId** và **month** thành fields ở cuối, nên $merge có các keys cần thiết. $merge là **write stage**: khác một report chỉ đọc, nó đòi hỏi quyền ghi và cần chạy như một scheduled/reporting job được kiểm soát.

### 16.4. $merge không tự xóa nhóm đã biến mất

Ví dụ trước đó tA có hai nhóm, nhưng sau thay đổi business filter không còn đơn hợp lệ trong tháng 1. $merge chỉ ghi những output documents hiện có; một document report cũ cho tA tháng 1 có thể **vẫn còn**.

Vì vậy refresh strategy cần:

- Xác định đầy đủ **phạm vi refresh**.
- Có cách xóa/mark obsolete những groups không còn tồn tại.
- Dùng **generationId/staging collection** khi cần chuyển phiên bản report atomically ở ứng dụng.
- Ghi trạng thái report job: RUNNING, VALIDATED, PUBLISHED, FAILED.
- Chỉ publish sau khi đối chiếu totals và số groups.

### 16.5. Tính idempotency cho reporting job

Một job có thể chạy lại vì timeout. Nếu dùng **$merge whenMatched:"replace"** với cùng tenant/month/reportVersion, dữ liệu kết quả được thay bằng latest calculation thay vì chèn nhóm trùng. Tuy nhiên:

- computedAt có thể thay đổi theo run.
- Kết quả có thể thay đổi nếu nguồn orders thay đổi.
- Nhóm không còn output cần cleanup riêng.
- $merge không tự tạo atomic snapshot cho toàn bộ báo cáo nhiều groups.

Muốn một generation bất biến, ghi **generationId** trong mỗi output, đối chiếu rồi chuyển active generation pointer theo quy trình.

### 16.6. $merge và transaction

Một pipeline dùng $merge hoặc $out có các giới hạn sử dụng trong transaction theo MongoDB version; không giả định có thể đặt tất cả thao tác materialization trong một multi-document transaction rồi có atomic replacement cho cả report.

Nếu cần atomic publication cho người đọc, thiết kế **staging generation + published pointer** hoặc một cơ chế snapshot phù hợp deployment.

### 16.7. Refresh full so với incremental

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Full recompute kỳ | Dễ hiểu và đối chiếu. | Quét dữ liệu nhiều, chi phí cao. |
| Incremental theo order changes | Có thể giảm chi phí. | Phức tạp khi status/refund đổi, event replay, duplicates. |
| Batch theo daily partition | Cân bằng chi phí và reconciliation. | Cần xử lý late-arriving/corrected data. |
| Ledger/event-based accounting | Theo posting date và audit. | Cần schema và reconciliation chuyên biệt. |

Đặc biệt với **refund sau nhiều tháng**, chỉ cộng doanh số của orders mới hôm nay sẽ không cập nhật các báo cáo tháng cũ. Phải có late-update handling, affected-period reprocessing hoặc event model phù hợp.

## 17. Tăng tính tái lập cho báo cáo

Một aggregation chạy hôm nay và ngày mai có thể trả hai kết quả khác nếu orders/refunds được sửa sau khi báo cáo lần đầu. Việc ghi bản báo cáo cần trả lời:

1. **Data cut:** dữ liệu đến thời điểm nào?
2. **Timezone:** kỳ được chia theo múi giờ nào?
3. **KPI definitions:** phiên bản nào xác định PAID/REFUNDED?
4. **Currency:** tất cả giá trị dùng cùng đơn vị chưa?
5. **Schema version:** các thay đổi field/type đã được xử lý chưa?
6. **Inputs:** dùng collection/snapshot/event ledger nào?
7. **Computation:** driver/server version, pipeline version và generationId?
8. **Verification:** kết quả có đối chiếu oracle/ledger/tổng kỳ không?

### 17.1. Snapshot và consistency

Trong lúc aggregation chạy, orders có thể đang được cập nhật. **Một lệnh aggregate thông thường không nên được mô tả như một snapshot kế toán bất biến theo mặc định**; read concern, deployment và thời điểm mutation có ý nghĩa.

Nếu báo cáo đòi hỏi reproducibility/audit mạnh:

- Xem khả năng **readConcern: snapshot** / snapshot reads được hỗ trợ cho operation/topology/version phù hợp.
- Hoặc dùng immutable ledger/event dataset với **watermark/closing period**.
- Hoặc đưa dữ liệu vào dedicated reporting snapshot.
- Ghi rõ kỳ đã chốt hay còn có thể điều chỉnh.

Không giữ transaction khổng lồ chỉ để scan hàng trăm triệu records; xét các giới hạn snapshot/resource/lifetime.

### 17.2. Giữ report generation metadata

~~~javascript
{
  generationId: "sales-v1-2026-03-02-run-001",
  reportName: "monthly-sales",
  timezone: "UTC",
  periodStart: ISODate("2026-01-01T00:00:00Z"),
  periodEnd: ISODate("2026-03-01T00:00:00Z"),
  metricVersion: "v1",
  statusPolicy: [
    "PAID", "PARTIALLY_REFUNDED", "REFUNDED"
  ],
  currency: "VND",
  status: "VALIDATED",
  computedAt: ISODate("2026-03-02T00:00:00Z")
}
~~~

Đây là metadata minh họa, không phải MongoDB built-in report format.

### 17.3. Lưu validation outcome

~~~text
sourceDocumentCount = 12
eligibleOrderCount = 9
tenantMonthGroupCount = 4
overallNetUnits = 350000
overallRefundedUnits = 60000
overallRealizedUnits = 290000
validationStatus = PASS
~~~

Không coi việc pipeline chạy không lỗi là validationStatus=PASS. Validation phải là **một bước tường minh** theo report contract.

### 17.4. Report schema thay đổi theo phiên bản

Giả sử phiên bản 2 thêm phí giao dịch và định nghĩa:

~~~text
realized = total - refund - platformFee
~~~

Đây là thay đổi định nghĩa KPI, không chỉ thêm cột. Đặt **metricVersion: "v2"**, tài liệu hóa tính khác biệt và không âm thầm ghi đè số liệu v1 nếu downstream dashboards/auditors cần so sánh.

### 17.5. Backfill và late data

Nếu sau ngày chốt một hệ thống nguồn cập nhật đơn tháng cũ:

- Cần biết có cho phép restatement kỳ đã chốt hay không.
- Ghi **adjustment events** nếu kế toán yêu cầu không sửa lịch sử.
- Có version/generation mới cho report được chỉnh.
- Cung cấp diff giữa report cũ và mới.

Không xóa số liệu cũ chỉ vì pipeline chạy lại cho kết quả khác mà không có audit.

## 18. Dùng aggregation từ Java Sync Driver

Trong service Java, không nên nối chuỗi JSON tùy tiện từ user input để tạo pipeline. Dùng **Filters/Aggregates** hoặc BSON Document được xây từ **tham số đã kiểm soát**, và buộc tenant scope từ authorization layer.

### 18.1. Ví dụ Java 17+ chạy báo cáo của một tenant

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public final class TenantSalesReport {

    private final MongoCollection<Document> orders;

    public TenantSalesReport(MongoClient client) {
        this.orders = client.getDatabase("reporting_lab_460")
                .getCollection("orders");
    }

    public List<Document> run(String authorizedTenantId) {
        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Authorized tenant is required");
        }

        Date start = Date.from(
                Instant.parse("2026-01-01T00:00:00Z"));
        Date end = Date.from(
                Instant.parse("2026-03-01T00:00:00Z"));

        Bson filter = Filters.and(
                Filters.eq("tenantId", authorizedTenantId),
                Filters.eq("currency", "VND"),
                Filters.in("status",
                        "PAID", "PARTIALLY_REFUNDED", "REFUNDED"),
                Filters.gte("createdAt", start),
                Filters.lt("createdAt", end)
        );

        Document month = new Document("$dateToString",
                new Document("format", "%Y-%m")
                        .append("date", "$createdAt")
                        .append("timezone", "UTC"));

        Document projected = new Document("tenantId", 1)
                .append("month", month)
                .append("subtotalUnits", 1)
                .append("discountUnits", 1)
                .append("totalUnits", 1)
                .append("refundUnits", 1)
                .append("realizedUnits",
                        new Document("$subtract",
                                List.of(
                                        "$totalUnits",
                                        "$refundUnits")));

        Document groupId = new Document(
                "tenantId", "$tenantId")
                .append("month", "$month");

        Document grouped = new Document("_id", groupId)
                .append("orderCount", new Document("$sum", 1))
                .append("grossUnits",
                        new Document("$sum", "$subtotalUnits"))
                .append("discountUnits",
                        new Document("$sum", "$discountUnits"))
                .append("netUnits",
                        new Document("$sum", "$totalUnits"))
                .append("refundedUnits",
                        new Document("$sum", "$refundUnits"))
                .append("realizedUnits",
                        new Document("$sum", "$realizedUnits"));

        List<Bson> stages = List.of(
                Aggregates.match(filter),
                new Document("$project", projected),
                new Document("$group", grouped),
                new Document("$sort",
                        new Document("_id.month", 1))
        );

        return orders.aggregate(stages)
                .into(new ArrayList<>());
    }
}
~~~

**Đoạn code minh họa** lấy tenant ID đã được xác thực ở service layer. Nếu caller có thể chọn bất kỳ authorizedTenantId mà không được kiểm tra quyền, vẫn có nguy cơ **cross-tenant data exposure**.

### 18.2. Đọc số tiền từ Document

~~~java
Document row = reportRows.get(0);

Object amount = row.get("realizedUnits");
if (!(amount instanceof Number number)) {
    throw new IllegalStateException(
            "Expected integer monetary report field");
}

long realizedUnits = number.longValue();
~~~

Với report này, expected type là integer numeric trong phạm vi **long**. Nếu schema chuyển sang Decimal128 hoặc tổng vượt long, cần thay data contract và adapter tương ứng; không dùng doubleValue() làm bước chuyển ngầm rồi xuất báo cáo tài chính.

### 18.3. Kiểm tra số nhóm theo tenant

Trong lab:

~~~text
run("tA") -> 2 groups:
  2026-01: realized 75000
  2026-02: realized 90000

run("tB") -> 2 groups:
  2026-01: realized 75000
  2026-02: realized 50000
~~~

Một integration test nên so group keys và mọi KPI, không chỉ results.size().

### 18.4. Không tạo MongoClient mỗi lần chạy

MongoClient được thiết kế để tái sử dụng và quản lý connection pool. Tạo/đóng MongoClient mỗi request gây overhead connection discovery, TLS và pool initialization. Sử dụng MongoClient theo application lifecycle.

### 18.5. Java driver phải dùng cùng metric contract

~~~text
mongosh pipeline:
  status IN ["PAID","PARTIALLY_REFUNDED","REFUNDED"]

Java endpoint accidentally:
  status == "PAID"
~~~

Kết quả sẽ lệch dù hai đoạn code đều chạy. Cần một **metric definition registry** hoặc integration tests đối chiếu contract xuyên các entry points.

## 19. Tích hợp Spring Data MongoDB

Spring Data MongoDB có **MongoTemplate**, **Aggregation**, **AggregationOperation** và typed aggregation APIs. Khi cần pipeline raw BSON tương ứng với ví dụ mongosh, có thể tạo stages từ **Document**.

### 19.1. Ví dụ gọn với AggregationOperation

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;

import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class SpringMonthlyReport {
    private final MongoTemplate template;

    public SpringMonthlyReport(MongoTemplate template) {
        this.template = template;
    }

    public List<Document> byTenant(String authorizedTenantId) {
        Date start = Date.from(
                Instant.parse("2026-01-01T00:00:00Z"));
        Date end = Date.from(
                Instant.parse("2026-03-01T00:00:00Z"));

        AggregationOperation matchStage = context ->
                new Document("$match",
                        new Document("tenantId", authorizedTenantId)
                                .append("currency", "VND")
                                .append("status",
                                        new Document("$in", List.of(
                                                "PAID",
                                                "PARTIALLY_REFUNDED",
                                                "REFUNDED")))
                                .append("createdAt",
                                        new Document("$gte", start)
                                                .append("$lt", end)));

        AggregationOperation projectStage = context ->
                new Document("$project",
                        new Document("tenantId", 1)
                                .append("month",
                                        new Document("$dateToString",
                                                new Document("format", "%Y-%m")
                                                        .append("date", "$createdAt")
                                                        .append("timezone", "UTC")))
                                .append("totalUnits", 1)
                                .append("refundUnits", 1)
                                .append("realizedUnits",
                                        new Document("$subtract",
                                                List.of(
                                                        "$totalUnits",
                                                        "$refundUnits"))));

        AggregationOperation groupStage = context ->
                new Document("$group",
                        new Document("_id",
                                new Document("tenantId", "$tenantId")
                                        .append("month", "$month"))
                                .append("orderCount", new Document("$sum", 1))
                                .append("netUnits",
                                        new Document("$sum", "$totalUnits"))
                                .append("refundedUnits",
                                        new Document("$sum", "$refundUnits"))
                                .append("realizedUnits",
                                        new Document("$sum", "$realizedUnits")));

        Aggregation aggregation = Aggregation.newAggregation(
                matchStage,
                projectStage,
                groupStage
        );

        AggregationResults<Document> results = template.aggregate(
                aggregation,
                "orders",
                Document.class
        );
        return results.getMappedResults();
    }
}
~~~

Đây là phiên bản **rút gọn KPI** tập trung vào cách đăng ký stages trong Spring; nếu dashboard cần gross/discount/AOV, bổ sung vào project/group như pipeline chính.

Với **raw Document stages**, field names là tên BSON đã lưu. Nếu entity có **@Field** aliases hoặc custom converters, cần đảm bảo pipeline dùng đúng persisted field paths. Các typed Aggregation APIs của Spring Data có tiện ích mapping theo version, nhưng không được suy rằng mọi raw stage tự đổi tên theo entity.

### 19.2. Spring Data projection/DTO

Đừng trả trực tiếp aggregation Document chứa **_id composite** và numeric types cho REST API mà không có output contract.

~~~java
public record MonthlySalesDto(
        String tenantId,
        String month,
        long orderCount,
        long netUnits,
        long refundedUnits,
        long realizedUnits
) {}
~~~

Tạo mapper có kiểm tra types, missing fields và overflow. Với Decimal128 hoặc optional groups, đổi DTO/schema có chủ đích. Không silently map null monetary fields thành 0 nếu null là lỗi dữ liệu.

### 19.3. Repository find rồi cộng trong Java

Một method **findByTenantIdAndStatusIn** rồi lấy mọi orders về Java để cộng có thể phù hợp dữ liệu nhỏ, nhưng ở quy mô lớn sẽ truyền nhiều documents và tăng memory/GC.

Aggregation giúp push filter/group tới MongoDB. Ngược lại, application-side fold lại rất hữu ích để **kiểm chứng độc lập trên fixture nhỏ**.

### 19.4. Reactive MongoDB

Với ReactiveMongoTemplate, aggregation trả reactive publisher. Tránh collect hàng triệu groups vào một list vô hạn và tránh blocking operations trong Reactor pipeline. Cân nhắc materialization, backpressure và timeouts.

## 20. Xuất báo cáo cho dashboard hoặc CSV

### 20.1. Chuẩn hóa output schema

Một output đầy đủ nên nêu currency, timezone và version:

~~~json
{
  "tenantId": "tA",
  "month": "2026-01",
  "timezone": "UTC",
  "currency": "VND",
  "orderCount": 3,
  "grossUnits": "100000",
  "discountUnits": "5000",
  "netUnits": "95000",
  "refundedUnits": "20000",
  "realizedUnits": "75000",
  "metricVersion": "v1"
}
~~~

Monetary values dạng **decimal strings** trong JSON ví dụ để tránh giới hạn số nguyên chính xác của JavaScript clients. Nếu frontend chấp nhận safe integers và API contract quy định rõ, có thể dùng JSON numbers trong phạm vi đã kiểm soát.

### 20.2. CSV với thứ tự ổn định

~~~csv
tenantId,month,currency,orderCount,grossUnits,discountUnits,netUnits,refundedUnits,realizedUnits
tA,2026-01,VND,3,100000,5000,95000,20000,75000
tA,2026-02,VND,2,110000,10000,100000,10000,90000
tB,2026-01,VND,2,80000,5000,75000,0,75000
tB,2026-02,VND,2,80000,0,80000,30000,50000
~~~

Khi xuất CSV production:

- Dùng UTF-8, column order và delimiter rõ.
- Escape dấu phẩy/nháy kép/newline trong các text fields.
- Giữ số nguyên chính xác/canonical decimal strings.
- Đính kèm timezone, currency, metricVersion và generationId.
- Không trộn locale number formatting với dữ liệu numeric canonical.
- Không tự coi CSV là audit trail nếu không có snapshot/version metadata.

### 20.3. JSON precision loss

BSON Long có thể chứa số lớn hơn **Number.MAX_SAFE_INTEGER** của JavaScript. Nếu serializer chuyển Long thành Number rồi xuất JSON, số tiền có thể bị sai.

Khi cần BSON round-trip, cân nhắc **Extended JSON canonical**; khi xây API, dùng monetary integer/decimal string hoặc thư viện decimal chính xác theo hợp đồng dữ liệu.

### 20.4. An toàn multi-tenant

Báo cáo có thể làm lộ doanh số nhạy cảm. API cần:

1. Xác thực caller.
2. Suy tenant scope từ quyền, không chỉ query parameter.
3. Áp dụng $match tenantId sớm.
4. Không cho caller tự thêm $lookup sang collection tenant khác.
5. Kiểm tra report cache keys gồm tenantId, currency, period và metricVersion.
6. Audit quyền truy cập/report export khi cần.

Nếu products catalog là tenant-specific, $lookup cần join theo **sku + tenantId**, không chỉ sku, trừ khi sku là global unique và được phép chia sẻ.

## 21. Mở rộng: so sánh tăng trưởng tháng trước bằng $setWindowFields

Ngoài tổng doanh số, dashboard có thể cần **month-over-month growth**. Đầu tiên phải quyết định metric nào được so: netUnits hay realizedUnits. Ví dụ này dùng **realizedUnits** theo contract bài.

### 21.1. Công thức

\[
\text{MoM growth \%}
=
\frac{\text{realized}_{t}-\text{realized}_{t-1}}
{\text{realized}_{t-1}}\times100
\]

Nếu tháng trước bằng 0 hoặc không tồn tại, không chia 0. Trả **null / N/A** theo reporting contract, không tự ghi +100%.

### 21.2. Window function

Trên MongoDB version hỗ trợ **$setWindowFields** và **$shift** (các operators có sẵn từ MongoDB 5.0):

~~~javascript
const growthPipeline = [
  ...pipeline,
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: { month: 1 },
      output: {
        previousRealizedUnits: {
          $shift: {
            output: "$realizedUnits",
            by: -1,
            default: null
          }
        }
      }
    }
  },
  {
    $set: {
      monthOverMonthPercent: {
        $cond: [
          {
            $or: [
              { $eq: ["$previousRealizedUnits", null] },
              { $eq: ["$previousRealizedUnits", 0] }
            ]
          },
          null,
          {
            $multiply: [
              {
                $divide: [
                  {
                    $subtract: [
                      "$realizedUnits",
                      "$previousRealizedUnits"
                    ]
                  },
                  "$previousRealizedUnits"
                ]
              },
              100
            ]
          }
        ]
      }
    }
  },
  { $sort: { tenantId: 1, month: 1 } }
];

lab.orders.aggregate(growthPipeline).toArray();
~~~

### 21.3. Kỳ vọng

| Tenant | Tháng | Realized | Tháng trước | Growth |
|---|---|---:|---:|---:|
| tA | 2026-01 | 75.000 | N/A | N/A |
| tA | 2026-02 | 90.000 | 75.000 | **+20%** |
| tB | 2026-01 | 75.000 | N/A | N/A |
| tB | 2026-02 | 50.000 | 75.000 | **−33,33%** |

**Lưu ý:** $shift lấy dòng trước trong tập đã sort, không nhất thiết là **tháng lịch liền trước** nếu có tháng không có đơn. Với dữ liệu nhiều kỳ, cần sinh calendar buckets hoặc kiểm tra khoảng cách tháng, không gọi tăng trưởng so với tháng liền trước khi thực tế đang so với kỳ có dữ liệu gần nhất.

### 21.4. AOV không tính bằng trung bình các AOV nhóm

Toàn kỳ:

~~~text
Net = 350000
Orders = 9
Overall AOV = 350000 / 9 ≈ 38888.89
~~~

Không lấy trung bình không trọng số của bốn AOV nhóm:

~~~text
(31666.67 + 50000 + 37500 + 40000) / 4
~~~

vì mỗi nhóm có số orders khác nhau. Tổng AOV phải là **total net / total orders**, hoặc trung bình có trọng số theo orderCount.

## 22. Kiểm thử hồi quy cho báo cáo

Một test chạy lại khi thay aggregation code nên kiểm tra **kết quả và hợp đồng**, không chỉ pipeline không bị syntax error.

### 22.1. Test matrix

| Test | Dữ liệu/điều kiện | Kỳ vọng |
|---|---|---|
| Happy path | 12 fixture orders | 9 eligible, 4 tenant/month groups. |
| Cancelled | A-004 | Không tham gia KPI. |
| Pending | A-007 | Không tham gia KPI. |
| End-exclusive | A-008 đúng 01/03 00:00Z | Bị loại khỏi Jan–Feb. |
| Full refund | A-003, B-003 | Có trong orderCount, realized=0. |
| Partial refund | A-006 | realized=40000. |
| Tenant isolation | Scope tA | Không có dòng tB. |
| Scope tB | Query riêng tB | Chỉ hai nhóm, realized cả kỳ 125000. |
| Gross/net/refund | Cả kỳ | 370000/350000/60000. |
| Totals invariant | Mỗi nhóm | gross−discount=net; net−refund=realized. |
| Category gross | Eligible items | Tổng category gross=370000. |
| Unique category order count | A-001 có hai categories | Không cộng category orderCount thành total orders. |
| Missing catalog | Một SKU không join được | Không làm mất line gross. |
| Wrong amount type | subtotalUnits String | Data quality check phát hiện. |
| Wrong total | total != subtotal−discount | Data quality check phát hiện. |
| Refund over total | refund > total | Data quality check phát hiện. |
| Unknown status | Một order có status mới | Báo data contract/schema issue. |
| Local timezone | Boundary gần nửa đêm UTC | Bucket theo local policy đúng. |
| No eligible orders | Kỳ trống | Không xuất group giả có doanh số. |
| Retry report job | Cùng generation/key | Không tạo group trùng. |
| Report version | Thay KPI formula | Phân biệt v1/v2, không overwrite âm thầm. |

### 22.2. Empty result là một case phải định nghĩa

Nếu chọn tháng không có đơn:

~~~javascript
lab.orders.aggregate([
  { $match: { createdAt: {
      $gte: ISODate("2030-01-01T00:00:00Z"),
      $lt: ISODate("2030-02-01T00:00:00Z")
  } } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
~~~

Không có group nào, kết quả sẽ là **mảng rỗng**, không tự có dòng total 0 cho từng tenant. UI muốn hiển thị tháng thiếu dữ liệu dưới dạng 0 cần **calendar/tenant dimension** và quyết định phân biệt zero sales với missing data.

### 22.3. Golden dataset

Fixture của bài là một **golden dataset**:

- Input documents được định nghĩa cố định.
- Oracle outputs được tính tay.
- Report engine phải giữ cùng kết quả trừ khi version KPI thay đổi.
- Test chạy trong database riêng, không phụ thuộc data ngẫu nhiên.
- Các thay đổi schema/status policy phải cập nhật test contract có review.

Golden tests rất hữu ích để bắt lỗi $unwind gây nhân đôi, đổi timezone, bỏ nhầm refund hoặc quên tenant scope.

### 22.4. Property-based hoặc metamorphic tests

Ngoài fixture, có thể tạo các assertions tổng quát:

1. Thêm một order **CANCELLED** không đổi KPI.
2. Thêm một order **PAID** hợp lệ làm orderCount tăng 1 và tổng KPI tăng đúng giá trị.
3. Chuyển một order từ PAID sang REFUNDED với refund=total làm realized giảm bằng total, nhưng orderCount không đổi.
4. Chia một item thành hai lines giống SKU/category với tổng quantity không đổi thì gross phải không đổi.
5. Hoán đổi thứ tự các orders không đổi kết quả sau group.
6. Thêm một tenant mới không đổi KPI của tenant tA.
7. Đổi report timezone có thể ảnh hưởng nhóm tháng nhưng không làm mất orders nếu filter bounds được chuyển đổi tương ứng.

Những tính chất này giúp bắt lỗi trên dữ liệu rộng hơn bốn groups của fixture.

### 22.5. Tự động hóa so sánh KPI

Khi QA nội bộ xây test suite, có thể lưu expected outputs làm fixtures rồi so bằng test framework (JUnit/Testcontainers hoặc tool phù hợp). Với numeric BSON types, so theo **numeric semantics và expected type**; không dựa vào cách shell format NumberLong.

**Bài viết chỉ cung cấp hướng dẫn và mẫu test**, không mặc định các snippets đã được chạy hoặc được xác thực trên một MongoDB instance thực tế.

## 23. Các lỗi thường gặp khi viết aggregation report

### 23.1. Đếm đơn bằng số line items sau $unwind

Sai:

~~~javascript
[
  { $unwind: "$items" },
  {
    $group: {
      _id: "$tenantId",
      orderCount: { $sum: 1 }
    }
  }
]
~~~

Đoạn này đếm **số dòng items**, không phải số đơn. Một order có 3 lines được đếm 3 lần. Với báo cáo cấp đơn, group trước unwind; nếu cần distinct sau unwind, dùng **unique order IDs** hoặc hai tầng group.

### 23.2. Cộng totalUnits sau $unwind

~~~text
Order with 2 items:
  totalUnits = 40000

After unwind:
  row 1 has totalUnits = 40000
  row 2 has totalUnits = 40000

Wrong sum = 80000
~~~

Chỉ cộng line value khi đang ở cấp item; không phân bổ discounts/refunds nếu chưa có rule.

### 23.3. Dùng $avg của các AOV nhóm

Nếu nhóm có số orders khác nhau, trung bình của các AOV không trọng số không bằng AOV cả kỳ. Đúng:

~~~text
Overall AOV = overall netUnits / overall orderCount
~~~

### 23.4. Tính cả PENDING và CANCELLED

Nếu chỉ filter createdAt mà không filter status, report sẽ lấy thêm các order chưa phát sinh doanh số theo contract. Fixture cố ý có A-004 và A-007 để phát hiện lỗi này.

### 23.5. Bỏ qua REFUNDED

Một số report chỉ tính PAID, làm giảm orderCount hoặc bỏ qua lịch sử đơn đã thanh toán rồi hoàn tiền. Contract bài này **có tính REFUNDED** nhưng realized=0; nếu business muốn refunded orderCount tách riêng, phải định nghĩa metric bổ sung.

### 23.6. Trừ refund hai lần

Nếu totalUnits thực sự đã trừ refund ở upstream nhưng pipeline tiếp tục tính total−refund, realized sẽ bị giảm hai lần. Kiểm tra schema contract và nguồn dữ liệu.

### 23.7. Hoàn tiền phát sinh ở kỳ sau

Một order tháng 1 được hoàn trong tháng 2 có thể làm báo cáo tháng 1 thay đổi khi group theo createdAt. Nếu team kế toán muốn refund được ghi nhận vào tháng 2, dùng refund events có timestamp/ledger thay vì chỉ đọc current cumulative refundUnits trên order.

### 23.8. Trộn currency

~~~text
100 USD + 100 VND = 200 (meaningless as financial amount)
~~~

Report phải group/filter currency hoặc quy đổi theo tỷ giá được định nghĩa với thời điểm, nguồn và audit.

### 23.9. Dùng double cho tổng tiền

Double gây sai số thập phân. Dùng integer units/Int64 hoặc Decimal128 phù hợp, và kiểm tra overflow/precision khi cộng dữ liệu quy mô lớn.

### 23.10. Amount bị lưu thành String

Một writer migration có thể đổi:

~~~javascript
totalUnits: NumberLong("35000")
~~~

thành:

~~~javascript
totalUnits: "35000"
~~~

$sum không cho ra semantics mong muốn như khi mọi values đều numeric. Bắt lỗi bằng kiểm tra **$type**, không dùng $toDouble tự động để che data contract drift.

### 23.11. Đặt $ifNull mặc định 0 tùy tiện

~~~javascript
{ $ifNull: ["$refundUnits", 0] }
~~~

có thể có ích nếu **legacy schema chính thức định nghĩa thiếu field là refund 0**. Nếu missing là corruption, default 0 khiến báo cáo trông hợp lệ nhưng sai. Chỉ dùng default khi được ghi trong metric/data contract.

### 23.12. Sai timezone

Group theo Asia/Ho_Chi_Minh nhưng $match dùng ranh giới UTC của tháng, khiến orders gần nửa đêm được tính vào kỳ không nhất quán. Chuyển cả bounds và bucket timezone theo cùng business calendar.

### 23.13. Dùng $lte cuối kỳ

Dùng $lte startOfNextMonth khiến một document đúng ranh giới được tính hai kỳ. Ưu tiên **start inclusive, end exclusive**.

### 23.14. Join product trước khi lọc

$lookup toàn collection rồi mới $match có thể làm tải lớn, đặc biệt nếu catalog nhiều rows hoặc join không có index. Filter trước, group khi có thể, sau đó enrich metadata.

### 23.15. $lookup làm mất SKU không có catalog

Nếu sau $lookup dùng $unwind mà không preserve empty arrays, SKU thiếu catalog có thể bị loại khỏi report. Điều này làm total giảm mà không có lỗi.

### 23.16. Category theo catalog hiện tại thay cho snapshot

Khi product đổi category, báo cáo lịch sử có thể tự thay đổi. Cần quyết định snapshot category trên order hay current catalog category.

### 23.17. Không kiểm tra bảng expected theo group keys

Chỉ so tổng 290000 có thể bỏ sót lỗi gán doanh số tA sang tB hoặc tháng 1 sang tháng 2. Kiểm tra **tenant/month keys** và từng KPI.

### 23.18. Tổng KPI vẫn đúng dù tất cả bị nhân đôi

Nếu gross, discount, net và refund đều bị nhân hai, bất biến gross−discount=net vẫn có thể đúng. Cần oracle, IDs và số orders độc lập.

### 23.19. Mất đơn có items rỗng sau $unwind

Một pipeline report cấp line items sẽ bỏ các orders có items:[] nếu dùng $unwind mặc định. Nếu schema không cho phép empty items, hãy xem đó là data quality error; nếu cho phép, quy định cách đếm/biểu diễn rõ.

### 23.20. Truy vấn quá nhiều dữ liệu ở production

Không dùng một report với 12 documents để kết luận aggregation sẽ tốt trên hàng trăm triệu documents. Xem explain, working set, indexes, memory/spilling và peak read load.

### 23.21. Materialized report bị stale

$merge không tự xóa nhóm cũ khi kỳ không còn documents đủ điều kiện. Cần full-generation refresh/cleanup hoặc marker cho obsolete groups.

### 23.22. Cache nhầm tenant

Nếu cache key chỉ có month, response của tA có thể được trả cho tB. Cache key phải gồm tenant scope, metric version, currency, period/timezone và quyền truy cập phù hợp.

### 23.23. Để caller tự xây aggregation pipeline

Không cho user đưa raw pipeline với $lookup/$merge tùy ý vào service mà không kiểm soát, vì có thể quét dữ liệu ngoài quyền hoặc tạo write stages nguy hiểm. Dùng approved report templates và whitelist parameters.

### 23.24. Xuất JSON Number vượt safe integer

Số BSON Long lớn có thể bị mất precision nếu chuyển sang JavaScript Number. Dùng string/decimal library và assertion về numeric type.

### 23.25. Không đóng kỳ hoặc snapshot

Report chạy ngày 01/03 và 10/03 cho tháng 1 có thể khác nếu refund/late data thay đổi. Gắn metadata as-of/watermark và định nghĩa restatement policy.

## 24. Runbook khi kết quả báo cáo không khớp

### 24.1. Bước 1 — Kiểm tra scope

Nếu expected 9 đơn nhưng pipeline chỉ đếm 8:

~~~javascript
lab.orders.find(
  scope,
  { _id: 1, tenantId: 1, createdAt: 1, status: 1 }
).sort({ _id: 1 });
~~~

So danh sách ID với oracle. Kiểm tra date bounds, status list, currency, tenant scope và timezone.

### 24.2. Bước 2 — Kiểm tra dữ liệu từng đơn

Nếu IDs đúng nhưng net/refund khác:

~~~javascript
lab.orders.find(
  scope,
  {
    _id: 1,
    tenantId: 1,
    subtotalUnits: 1,
    discountUnits: 1,
    totalUnits: 1,
    refundUnits: 1
  }
).sort({ _id: 1 });
~~~

Đối chiếu kiểu BSON và arithmetic per-order. Không sửa group trước khi biết từng order đúng.

### 24.3. Bước 3 — Kiểm tra các stages tạo nhiều rows

Nếu count và tiền đều lớn bất thường:

- Có $unwind items không?
- Có $lookup one-to-many không?
- Có $group lại theo order ID trước khi group tenant/month không?
- Có sum nguyên order total ở dòng item không?

Đặt debug pipeline dừng sau từng stage để đếm số rows và xem shape. Làm trên fixture/representative sample; đừng dump dữ liệu nhạy cảm production.

### 24.4. Bước 4 — Xác định timezone

Nếu tổng toàn kỳ đúng nhưng sai giữa hai tháng, xem createdAt type và time boundaries. Đối chiếu UTC với timezone business, đặc biệt các orders gần 00:00 đầu tháng.

### 24.5. Bước 5 — So bằng independent fold

Nếu MongoDB output vẫn khác bảng oracle, dùng thuật toán BigInt ở phần 12 để đối chiếu từng document/group, rồi quyết định lỗi thuộc filter, data hay logic group.

### 24.6. Bước 6 — Phân biệt report stale với source changed

Nếu aggregation trực tiếp đúng nhưng collection monthly_order_reports sai:

- Generation/reportVersion có đúng không?
- Scheduled refresh chạy thành công không?
- Có nhóm stale chưa được cleanup không?
- Có late refunds hoặc corrected orders không?
- Materialization có dùng cùng scope/timezone/status policy không?

### 24.7. Bước 7 — Chỉ sau khi đúng mới tối ưu

Nếu kết quả đúng nhưng chậm:

1. Xem explain.
2. Xác định keys/docs examined.
3. Kiểm tra $match pushdown và indexes.
4. Xem $group/$sort memory/spill và $lookup.
5. Xem client-side materialization/network overhead.
6. Đo p95/p99, CPU, I/O và concurrency.

Không bỏ kiểm chứng chỉ vì đã thêm index hoặc tăng tài nguyên.

## 25. Bài thực hành từ cơ bản đến nâng cao

Các bài dưới đây dành cho **database reporting_lab_460 trên MongoDB lab**, không chạy trên production. Nếu muốn thử trường hợp dữ liệu lỗi, hãy tạo **bản sao fixture riêng** thay vì sửa dữ liệu gốc.

### Bài 1 — Đọc schema

Liệt kê các fields và BSON types của một order. Phân biệt dữ liệu cấp order với items[]. Giải thích vì sao giá và tổng được lưu bằng integer units.

### Bài 2 — Seed dữ liệu

Dùng makeOrder tạo 12 documents. Vì sao insertMany lần thứ hai trên cùng IDs có thể gặp duplicate key? Làm sao chạy lại an toàn trên fixture mới?

### Bài 3 — Filter eligible

Viết $match cho hai tháng 01–02/2026 theo UTC, currency VND và statuses PAID, PARTIALLY_REFUNDED, REFUNDED.

### Bài 4 — Ranh giới ngày

So $lt end với $lte end. Với A-008 có createdAt đúng 01/03 00:00Z, cách nào khiến đơn có thể bị tính trùng ở hai kỳ?

### Bài 5 — Danh sách ID

Viết countDocuments cho eligible orders (kỳ vọng **9**), sau đó so danh sách _id với expectedIds. Vì sao count đúng chưa đủ?

### Bài 6 — Công thức từng order

Tính gross/discount/net/refund/realized cho A-002, A-003 và A-006 bằng tay. Giải thích vì sao A-003 được đếm nhưng realized=0.

### Bài 7 — Bucket tháng

Tạo month dạng YYYY-MM với $dateToString và timezone UTC. So kiểu chuỗi month với BSON Date trả bởi $dateTrunc.

### Bài 8 — $group

Viết $group có _id gồm tenantId và month. Tính orderCount, grossUnits, discountUnits, netUnits, refundedUnits và realizedUnits.

### Bài 9 — Output schema

Dùng $project cuối pipeline chuyển các trường nằm trong _id thành tenantId/month top-level; $sort theo tenantId, month để output ổn định.

### Bài 10 — Đối chiếu oracle

So bốn nhóm với bảng expected: tA Jan 75000; tA Feb 90000; tB Jan 75000; tB Feb 50000 realizedUnits. Nếu một nhóm sai, điều tra gì trước?

### Bài 11 — Tổng kỳ

Tính orderCount=9, gross=370000, discount=20000, net=350000, refunded=60000, realized=290000 bằng $group với _id:null.

### Bài 12 — $facet

Tạo ba nhánh byTenantMonth, byMonth và overall. Đối chiếu tổng realized và orderCount giữa các nhánh.

### Bài 13 — AOV

Tính AOV theo nhóm và toàn kỳ. Vì sao không lấy trung bình không trọng số của bốn AOV nhóm để suy AOV toàn kỳ?

### Bài 14 — Sai số $unwind

Cố tình $unwind items rồi cộng totalUnits theo từng row. Quan sát A-001 có hai items. Giải thích kết quả sai và sửa pipeline.

### Bài 15 — Gross theo category

Viết $unwind + $group theo items.category. Kỳ vọng Software=150000, Hardware=120000, Accessories=100000.

### Bài 16 — Units sold

Tính tổng qty theo category. Kỳ vọng Software=5, Hardware=6, Accessories=10. Vì sao không suy số đơn từ unitsSold?

### Bài 17 — Unique orders

Dùng $addToSet order _id và $size. Vì sao cộng orderCount của ba categories được 13 chứ không phải 9?

### Bài 18 — Hai tầng group

Thay $addToSet bằng nhóm category+orderId rồi nhóm lại category. Thảo luận trade-off memory và số intermediate groups.

### Bài 19 — Refund theo item

Với A-006 có hai items và refund=10000, chứng minh cộng nguyên refund sau unwind thành 20000. Đề xuất quy tắc phân bổ hoặc giữ báo cáo ở cấp gross.

### Bài 20 — $lookup products

Tạo catalog P1/P2/P3, join displayName cho SKU report sau khi group. Nếu catalog thiếu một SKU, làm sao không loại mất gross của SKU đó?

### Bài 21 — Recompute subtotal

Dùng $map và $sum tính lại subtotal từ qty × unitPriceUnits. So với subtotalUnits đã lưu và liệt kê IDs bị sai.

### Bài 22 — Bất biến tiền

Viết phép kiểm tra total=subtotal−discount và realized=total−refund. Vì sao tất cả KPI bị nhân đôi vẫn có thể vượt qua kiểm tra bất biến?

### Bài 23 — BSON type mismatch

Trong fixture copy, đổi totalUnits thành String. Dùng $type để phát hiện. Vì sao không nên tự convert String sang double khi chưa có migration policy?

### Bài 24 — Hoàn tiền vượt total

Tạo một test document riêng có refundUnits > totalUnits. Viết data quality aggregation phát hiện vi phạm.

### Bài 25 — Unknown status

Tạo status "PAYMENT_CONFIRMED" trong fixture copy. Report hiện tại có tính order không? Data quality monitoring cần báo gì?

### Bài 26 — Timezone local

Đổi báo cáo sang Asia/Ho_Chi_Minh. Tính UTC start/end từ local boundaries và chỉnh timezone trong $dateToString. Khi nào một order đổi tháng?

### Bài 27 — Kỳ không có dữ liệu

Chạy aggregation trong tháng 01/2030. Pipeline trả group 0 hay mảng rỗng? Nếu UI cần hiển thị 0 cho từng tenant thì phải có thêm dimension gì?

### Bài 28 — Month-over-month

Dùng $setWindowFields/$shift tính tăng trưởng realized theo tenant. Kỳ vọng tA +20%, tB khoảng −33,33% ở tháng 2.

### Bài 29 — Missing month

Giả sử tenant tC chỉ có order tháng 1 và tháng 4. $shift lấy kỳ trước có dữ liệu, không hẳn tháng liền trước. Đề xuất calendar dimension để tránh sai tên metric MoM.

### Bài 30 — explain/index

Đề xuất index cho tenant-scoped report. Dùng explain("executionStats") để phân tích scan count và query plan. Vì sao COLLSCAN trên 12 records có thể hợp lý?

### Bài 31 — $facet memory

Một report có 300.000 tenants × 120 tháng. Ước lượng số nhóm tối đa theo mô hình đơn giản, giải thích nguy cơ output BSON quá lớn và đề xuất materialization.

### Bài 32 — Java Sync Driver

Viết Java service dùng MongoCollection.aggregate, Filters và Document stages, có filter tenantId dựa trên authorization. Thêm integration assertions cho tA Jan/Feb.

### Bài 33 — Spring Data MongoDB

Viết MongoTemplate aggregation bằng AggregationOperation. Cần lưu ý gì khi entity dùng @Field aliases nhưng raw stages trỏ BSON field names?

### Bài 34 — Precision khi xuất JSON

Giải thích vì sao BSON Long lớn bị làm tròn nếu chuyển sang JavaScript Number. Đề xuất DTO/API nhận số tiền dạng strings hoặc decimal-safe type.

### Bài 35 — CSV có metadata

Xuất bốn groups tenant/month theo thứ tự ổn định, kèm currency, timezone và metricVersion trong export manifest. Vì sao phải phân biệt dấu phân cách số hiển thị với dữ liệu numeric?

### Bài 36 — Materialize bằng $merge

Tạo monthly_order_reports và unique index theo tenantId/month/reportVersion. Ghi kết quả bằng whenMatched replace, rồi đọc lại bốn nhóm.

### Bài 37 — Stale report

Nếu một tháng trước có sales nhưng sau thay đổi filter không còn eligible order, vì sao $merge không tự xóa group cũ? Thiết kế generationId hoặc cleanup.

### Bài 38 — Refund xảy ra muộn

Đơn tạo tháng 1, refund tháng 2. So báo cáo theo createdAt với báo cáo refund theo posting date. Data model/event nào cần để có audit lịch sử?

### Bài 39 — Multi-tenant authorization

Caller muốn báo cáo tB nhưng token chỉ được phép tA. Query parameter tenantId có đủ để cấp quyền không? Thiết kế auth check và cache key đúng.

### Bài 40 — Thiết kế report production

Soạn một design note gồm:

~~~text
Business questions and stakeholders
KPI definitions and status rules
Currency and timezone contract
Input BSON schema and data quality assumptions
Aggregation pipeline and result contract
Hand-calculated golden fixtures
Independent reconciliation and invariants
Index/explain and resource budget
Materialization, snapshots, late data
Access control, observability and export formats
Incident runbook and ownership
~~~

Một báo cáo đạt yêu cầu phải **đúng số, giải thích được số, kiểm tra lại được số và tái lập được quá trình sinh số**, chứ không chỉ tạo bảng đẹp.

## 26. Câu hỏi ôn tập

1. Vì sao phải định nghĩa KPI trước khi viết aggregation?
2. Những yếu tố nào quyết định order được tính vào báo cáo?
3. Tại sao cần ghi rõ currency khi cộng doanh số?
4. Vì sao bài dùng BSON Int64 thay cho double để lưu tiền?
5. GrossUnits, netUnits và realizedUnits khác nhau như thế nào?
6. Tại sao một order REFUNDED có thể được đếm trong orderCount nhưng realized bằng 0?
7. AOV trong bài lấy net hay realized làm tử số?
8. Công thức nào kiểm tra gross−discount=net?
9. Công thức nào kiểm tra net−refund=realized?
10. Tại sao bất biến số học đúng vẫn chưa chứng minh totals đúng?
11. Vì sao start inclusive/end exclusive tránh tính trùng ranh giới?
12. MongoDB BSON Date và chuỗi YYYY-MM khác nhau thế nào?
13. $dateToString dùng timezone để giải quyết vấn đề gì?
14. Vì sao đổi timezone bucket mà không đổi bounds có thể làm sai kỳ?
15. $dateTrunc khác $dateToString ở kiểu kết quả nào?
16. Trong pipeline chính, $match nên được đặt ở đâu và vì sao?
17. $project giúp giới hạn fields và tính realizedUnits ra sao?
18. _id composite trong $group dùng để nhóm tenant/month như thế nào?
19. Vì sao phải $sort trước khi xuất báo cáo?
20. Vì sao $group theo order không cần $unwind items?
21. $unwind một order hai items tạo bao nhiêu rows?
22. Nếu cộng order total sau $unwind, lỗi xảy ra thế nào?
23. Có thể dùng $addToSet để đếm distinct orders theo category như thế nào?
24. Vì sao không cộng category orderCount để suy overall orderCount?
25. Category gross và category realized khác nhau về yêu cầu dữ liệu gì?
26. $lookup thiếu product có thể gây mất dòng nếu $unwind không preserve empty arrays như thế nào?
27. Vì sao join SKU sau khi group có thể giảm chi phí?
28. $facet giúp gì cho báo cáo nhiều góc nhìn?
29. Những giới hạn memory và BSON result size nào cần nhớ khi dùng $facet?
30. Oracle tính tay khác kiểm tra invariant ở điểm nào?
31. Vì sao cần đối chiếu danh sách order IDs, không chỉ count?
32. Một independent fold bằng BigInt có ưu điểm gì so với chỉ gọi lại cùng aggregation?
33. Tại sao independent fold vẫn không chứng minh business contract đúng nếu scope sai?
34. Data quality check nên bắt những kiểu lỗi nào về BSON numeric?
35. Vì sao không tự thay missing refund bằng 0 nếu schema không quy định?
36. Khi refund xảy ra ở tháng sau, báo cáo theo createdAt có thể thay đổi thế nào?
37. Khi nào cần ledger/posting-date data model?
38. $merge khiMatched replace giải quyết phần nào của idempotent refresh?
39. $merge có tự xóa các group không còn trong output không?
40. Tại sao cần generationId/metricVersion khi publish báo cáo?
41. Explain executionStats giúp đánh giá những tài nguyên gì?
42. Tại sao COLLSCAN ở 12 records không phản ánh hiệu năng trên hàng triệu records?
43. Index cho tenant-scoped report khác index cho global report ở đâu?
44. allowDiskUse có khắc phục được mọi giới hạn $facet không?
45. JSON Number làm mất độ chính xác của BSON Long trong trường hợp nào?
46. Vì sao phải kiểm soát tenant scope trước khi chạy aggregation?
47. Báo cáo từ live orders có thể cần snapshot/watermark ra sao?
48. Vì sao overall AOV phải tính từ net/total orders thay vì trung bình các AOV nhóm?
49. $setWindowFields/$shift có điểm gì cần lưu ý nếu thiếu một tháng trong dữ liệu?
50. Một báo cáo production đáng tin cần bằng chứng gì ngoài việc pipeline chạy không lỗi?

## 27. Checklist hoàn thiện một báo cáo MongoDB

### 27.1. Yêu cầu và định nghĩa

- [ ] Mục đích báo cáo và người sử dụng đã được xác định.
- [ ] KPI có công thức, đơn vị và ý nghĩa được phê duyệt.
- [ ] Status inclusion/exclusion được ghi rõ.
- [ ] Currency/denomination thống nhất.
- [ ] Date field, timezone và period bounds được quy định.
- [ ] Refund/return/discount semantics được xác nhận.
- [ ] Tenant/authorization scope rõ và được kiểm soát.
- [ ] Định nghĩa của kỳ đã chốt/được phép restate rõ.

### 27.2. Dữ liệu gốc

- [ ] BSON field types được kiểm tra.
- [ ] Required fields không thiếu hoặc có policy rõ.
- [ ] Quantity và unit price hợp lệ.
- [ ] Subtotal khớp tổng line values.
- [ ] Total khớp subtotal−discount.
- [ ] Refund không vượt total theo business rule.
- [ ] Không có unknown status/currency không được xử lý.
- [ ] Product catalog missing không âm thầm loại dữ liệu.
- [ ] Schema versions cũ được migrate hoặc có compatibility policy.

### 27.3. Aggregation

- [ ] $match lọc đúng tenant, dates, statuses và currency.
- [ ] Dùng start inclusive/end exclusive.
- [ ] Grouping month dùng đúng timezone.
- [ ] KPI values cộng theo đúng document grain.
- [ ] $unwind chỉ dùng khi cần item-level data.
- [ ] Không sum nguyên order total nhiều lần sau unwind.
- [ ] $lookup không tạo duplicate hoặc mất rows.
- [ ] $group, $facet, $sort có expected output schema.
- [ ] Empty-period và missing-group behavior được xác định.
- [ ] Output có sorting ổn định.

### 27.4. Kiểm chứng số liệu

- [ ] Có deterministic fixture và hand-calculated oracle.
- [ ] Eligible document count đúng.
- [ ] Eligible order IDs đúng.
- [ ] Số groups và group keys đúng.
- [ ] Mọi KPI được so với oracle, không chỉ một tổng.
- [ ] Gross−discount=net và net−refund=realized.
- [ ] Tenant/month sums bằng overall sums.
- [ ] Category line gross tổng bằng order gross.
- [ ] Có cách tính độc lập để reconcile khi mismatch.
- [ ] Các boundary, refund, cancelled và partially refunded được test.
- [ ] Có test chống lỗi $unwind row multiplication.

### 27.5. Hiệu năng và vận hành

- [ ] Explain được xem trên representative dataset.
- [ ] Index candidates được benchmark theo workload thực tế.
- [ ] Có timeouts và resource limits hợp lý.
- [ ] $facet và $group memory usage được xem xét.
- [ ] $lookup/cross-collection join không vượt budget.
- [ ] Có monitoring latency, success/failure và data freshness.
- [ ] Có plan cho large reports, pagination hoặc materialization.
- [ ] Backfill/late refunds được xử lý.
- [ ] Report refresh có idempotency và cleanup stale outputs.

### 27.6. Publish và bảo mật

- [ ] Output contract nêu tenant, period, currency, timezone và metricVersion.
- [ ] Numeric values không mất precision khi sang JSON/CSV.
- [ ] Cache key chứa tenant scope và report version.
- [ ] Không cho user thực thi aggregation stages tùy ý.
- [ ] Có audit cho report export/access khi cần.
- [ ] Mỗi generation có computedAt và data watermark/snapshot reference.
- [ ] Có validation status trước khi publish.
- [ ] Có runbook xử lý số liệu sai và người chịu trách nhiệm.

## 28. Tổng kết

Xây một báo cáo aggregation có hai phần cần được thực hiện nghiêm túc như nhau: **tính toán** và **chứng minh kết quả**.

### 28.1. Pipeline hợp lý

~~~text
Define KPI / scope / timezone / currency
                |
                v
       Verify source data contract
                |
                v
            $match
                |
                v
        $project / $set
                |
                v
             $group
                |
                v
        $sort / $facet
                |
                v
      Validate IDs and totals
                |
                v
   Independent fold / golden oracle
                |
                v
        explain / optimize
                |
                v
   Export or materialize versioned report
~~~

### 28.2. Các nguyên tắc quan trọng nhất

1. **Viết hợp đồng KPI trước code**: report đúng theo định nghĩa sai vẫn là report sai nghiệp vụ.
2. **Giữ grain rõ ràng**: order-level totals khác item-level totals; $unwind có thể nhân đôi.
3. **Lọc scope trước khi group**: status, tenant, currency, thời gian.
4. **Dùng đúng timezone và [start, end)**, không hard-code cuối ngày bằng 23:59:59.
5. **Giữ numeric precision** bằng Int64/Decimal128 phù hợp, không âm thầm đổi sang double.
6. **Có oracle tính tay** đủ đơn giản để độc lập với pipeline.
7. **So IDs, số nhóm và tất cả KPI**, không chỉ kết quả tổng.
8. **Kiểm tra data quality riêng**, vì $sum không phải công cụ phát hiện mọi dữ liệu hỏng.
9. **Đối chiếu bằng cách khác**: một independent fold trên fixture giúp bắt lỗi biểu thức.
10. **Không dùng $lookup/$facet/$unwind vô điều kiện**; xem output cardinality và giới hạn tài nguyên.
11. **Dùng explain và representative workload** trước khi tối ưu indexes/capacity.
12. **Materialization phải xử lý stale groups, late data và generations**.
13. **Duy trì traceability**: metricVersion, timezone, computedAt và data watermark.
14. **Bảo vệ tenant data** ở application authorization và report queries.
15. **Report production không chỉ là con số cuối cùng**; nó là một phép tính có nguồn gốc, giả định, bằng chứng và khả năng tái lập.

### 28.3. Bảng kết quả trọng tâm cần nhớ

| Kiểm tra | Kỳ vọng fixture |
|---|---:|
| Tổng documents được seed | 12 |
| Eligible documents tháng 1–2 | 9 |
| Số nhóm tenant/month | 4 |
| GrossUnits | 370.000 |
| DiscountUnits | 20.000 |
| NetUnits | 350.000 |
| RefundedUnits | 60.000 |
| RealizedUnits | **290.000** |
| Category gross tổng | 370.000 |
| tA realized cả kỳ | 165.000 |
| tB realized cả kỳ | 125.000 |

Nếu chạy lại báo cáo trên fixture đã định nghĩa mà ra số khác, cần kiểm tra **schema, filter, timezone, $unwind/$lookup, công thức KPI hoặc dữ liệu đã bị sửa**, không chấp nhận kết quả mới chỉ vì aggregation không báo lỗi.

### 28.4. Tài liệu tham khảo chính thức

- [MongoDB Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — khái niệm pipeline, stages và tối ưu.
- [MongoDB Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/) — danh mục các stages.
- [MongoDB $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) — lọc documents.
- [MongoDB $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) — chọn và biến đổi fields.
- [MongoDB $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — aggregation theo nhóm.
- [MongoDB $unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — mở mảng thành dòng.
- [MongoDB $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/) — nhiều nhánh aggregation.
- [MongoDB $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — join giữa collections.
- [MongoDB $dateToString](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateToString/) — format ngày theo timezone.
- [MongoDB $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/) — bucket theo calendar/time unit.
- [MongoDB $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/) — window computations.
- [MongoDB $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — materialize kết quả.
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query planner/execution stats.
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Long, Decimal128, Date và các kiểu lưu trữ.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — driver APIs và aggregation.
- [Spring Data MongoDB Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — Aggregation API trong Spring.

Các APIs, tối ưu hóa và giới hạn của $facet/$group/$merge có thể thay đổi giữa MongoDB server/driver/Spring Data versions. Khi dùng ngoài lab, đối chiếu tài liệu đúng phiên bản và triển khai thử trên representative dataset.

**Kết luận:** Một báo cáo MongoDB đáng tin phải trả lời được không chỉ **“doanh thu bao nhiêu?”**, mà còn **“những đơn nào được tính, phép tính nào được áp dụng, vì sao kết quả đúng và liệu có tái tạo lại được không?”**. Aggregation cung cấp các công cụ mạnh để tổng hợp dữ liệu; **golden fixture, đối chiếu độc lập, kiểm tra dữ liệu gốc, kiểm soát timezone và snapshot/report version** mới giúp những con số đó sử dụng được trong quyết định nghiệp vụ.















