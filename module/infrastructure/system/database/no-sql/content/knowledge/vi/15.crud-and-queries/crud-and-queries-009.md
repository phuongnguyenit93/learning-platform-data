# Truy vấn tổng hợp, nhóm và giới hạn biểu đạt theo từng hệ

Trong ứng dụng sử dụng NoSQL, việc đọc một bản ghi theo khóa thường chỉ là điểm khởi đầu. Sản phẩm còn cần các câu hỏi như:

- Hôm nay mỗi cửa hàng có bao nhiêu đơn đang ở trạng thái `PAID`?
- Tổng giá trị các đơn này là bao nhiêu và giá trị trung bình mỗi đơn là bao nhiêu?
- Mỗi ngày có bao nhiêu thiết bị gửi sự kiện lỗi?
- Mỗi nhóm sản phẩm có bao nhiêu sản phẩm đang hoạt động?
- Mười tác giả nào có nhiều bài viết được người dùng theo dõi nhất?

Đây là các **truy vấn tổng hợp (aggregation)**: thay vì trả từng bản ghi, hệ thống tính toán một hoặc nhiều giá trị dựa trên **một tập dữ liệu**. Khi chia dữ liệu thành các nhóm, truy vấn còn cần **grouping**. Trong SQL quan hệ, người học thường gặp `GROUP BY`, `COUNT`, `SUM`, `AVG`. Nhưng trong NoSQL, **khả năng diễn đạt và chi phí thực thi những thao tác ấy khác nhau rất lớn giữa các hệ**.

MongoDB hỗ trợ pipeline tổng hợp linh hoạt trên document. Cassandra/CQL có các hàm aggregate và một dạng `GROUP BY` bị ràng buộc chặt bởi khóa dữ liệu. DynamoDB không cung cấp truy vấn `GROUP BY` tổng quát trên bảng; ứng dụng thường đọc dữ liệu theo khóa rồi tính hoặc duy trì bảng tổng hợp. Redis có lệnh đếm/tính toán trên cấu trúc dữ liệu đã chọn, nhưng không phải SQL engine có thể nhóm tùy ý. Hệ tìm kiếm hỗ trợ nhiều kiểu aggregation trên chỉ mục phân tán, còn graph database như Neo4j cho phép tổng hợp theo **mẫu quan hệ**.

Vì vậy, bài học không chỉ hỏi **“viết câu lệnh tổng hợp thế nào?”** mà còn hỏi **“dữ liệu phải được tổ chức ra sao để câu hỏi đó chạy đúng, nhanh và có thể mở rộng?”**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **lọc**, **nhóm**, **tổng hợp**, **sắp xếp** và **giới hạn kết quả**.
2. Định nghĩa chính xác ý nghĩa của các chỉ số `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `DISTINCT` và thống kê theo thời gian.
3. Viết ví dụ aggregation phù hợp với **MongoDB**, **Cassandra/CQL**, **DynamoDB**, **Redis**, **Neo4j/Cypher** và hệ tìm kiếm.
4. Hiểu tại sao một câu lệnh nhìn ngắn có thể phải **quét nhiều dữ liệu hoặc gom kết quả qua nhiều shard**.
5. Quyết định khi nào tổng hợp **ngay lúc đọc** và khi nào tạo **bảng tổng hợp được duy trì sẵn** (*pre-aggregation/materialized summary*).
6. Xử lý bản ghi thay đổi, sự kiện lặp, dữ liệu đến muộn, cập nhật đồng thời, phân trang nhóm và độ mới của báo cáo.
7. Thiết kế benchmark và quy trình đối soát để không nhầm **đúng cú pháp** với **đúng nghiệp vụ**.

## 2. Bài toán xuyên suốt: thống kê đơn hàng theo cửa hàng và ngày

Giả sử nền tảng bán hàng có nhiều tenant. Một bản ghi đơn gồm:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O101",
  "shopId": "shop-12",
  "createdAt": "2026-11-14T08:10:00.000Z",
  "status": "PAID",
  "totalVnd": 120000,
  "version": 3
}
~~~

Ta có sáu đơn mẫu:

| orderId | shopId | createdAt (UTC) | status hiện tại | totalVnd |
| --- | --- | --- | --- | ---: |
| O101 | shop-12 | 14/11 08:10 | PAID | 120.000 |
| O102 | shop-12 | 14/11 09:10 | PAID | 230.000 |
| O103 | shop-12 | 14/11 11:00 | CREATED | 50.000 |
| O201 | shop-21 | 14/11 08:30 | PAID | 310.000 |
| O202 | shop-21 | 14/11 12:45 | REFUNDED | 90.000 |
| O104 | shop-12 | 15/11 01:00 | PAID | 150.000 |

Tất cả sáu đơn thuộc `tenantId = merchant-a`. Ngày trong bảng được hiểu theo **UTC** để tránh nhập nhằng ranh giới. Dữ liệu minh họa đã được cố định ở **một ảnh chụp logic** của trạng thái hiện tại.

Yêu cầu **Q1**:

> Với tenant `merchant-a`, đếm số đơn có **trạng thái hiện tại bằng `PAID`**, tính **tổng giá trị đơn** và **giá trị trung bình**, nhóm theo **cửa hàng và ngày tạo UTC**, trong hai ngày 14–15/11/2026.

Kết quả kỳ vọng:

| dayUtc | shopId | paidOrderCount | paidOrderTotalVnd | avgPaidOrderVnd |
| --- | --- | ---: | ---: | ---: |
| 2026-11-14 | shop-12 | 2 | 350.000 | 175.000 |
| 2026-11-14 | shop-21 | 1 | 310.000 | 310.000 |
| 2026-11-15 | shop-12 | 1 | 150.000 | 150.000 |

**Lưu ý về định nghĩa KPI:** Q1 đếm các đơn **đang có trạng thái PAID tại thời điểm đọc**. Nó **không phải doanh thu thực nhận trong ngày**. Khi đơn chuyển `PAID -> SHIPPED` hoặc `REFUNDED`, kết quả Q1 có thể thay đổi. Để báo cáo doanh thu kế toán, cần xác định **sự kiện thanh toán/capture, hoàn tiền, thời điểm ghi nhận và nguồn có thẩm quyền**, thay vì suy doanh thu từ một trạng thái đơn hiện tại.

Chính sự khác biệt giữa “đơn đang PAID” và “tiền đã thu” cho thấy việc xác định **ngữ nghĩa số liệu** quan trọng không kém cú pháp tổng hợp.

### 2.1. Các bước logic của truy vấn Q1

~~~mermaid
flowchart LR
    A["Tập đơn hàng"] --> B["Lọc tenant và khoảng ngày"]
    B --> C["Lọc status = PAID"]
    C --> D["Tính dayUtc từ createdAt"]
    D --> E["Nhóm theo dayUtc + shopId"]
    E --> F["COUNT / SUM / AVG"]
    F --> G["Sắp xếp và trả kết quả"]
~~~

Viết dưới dạng pseudocode không phụ thuộc database:

~~~text
eligible = orders WHERE
    tenantId = "merchant-a"
    AND createdAt >= 2026-11-14T00:00:00Z
    AND createdAt <  2026-11-16T00:00:00Z
    AND status = "PAID"

GROUP eligible BY (UTC_DATE(createdAt), shopId)
CALCULATE:
    paidOrderCount = COUNT(*)
    paidOrderTotalVnd = SUM(totalVnd)
    avgPaidOrderVnd = SUM(totalVnd) / COUNT(*)
ORDER BY dayUtc, shopId
~~~

Đây là **đặc tả kết quả**, chưa nói hệ lưu trữ nào có thể thực thi trực tiếp bằng một lệnh.

## 3. Phân biệt các thao tác trong truy vấn tổng hợp

| Thao tác | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Filter** | Chọn bản ghi đủ điều kiện | `status = PAID` |
| **Projection** | Chọn trường hoặc tính trường mới | Lấy `shopId`, `dayUtc` |
| **Group** | Chia bản ghi thành các nhóm theo khóa | `(shopId, dayUtc)` |
| **Aggregate** | Tính một giá trị từ các bản ghi trong nhóm | `SUM(totalVnd)` |
| **Sort** | Xếp nhóm hoặc bản ghi theo tiêu chí | Tổng giá trị giảm dần |
| **Limit** | Chỉ lấy một số kết quả | Top 10 cửa hàng |
| **Having / post-group filter** | Lọc nhóm theo kết quả đã tính | Chỉ nhóm có ít nhất 10 đơn |
| **Distinct** | Xác định các giá trị khác nhau | Đếm số khách duy nhất |

### 3.1. COUNT không phải lúc nào cũng đếm cùng đối tượng

Hãy phân biệt:

- `COUNT(*)`: số bản ghi/hàng thỏa bộ lọc trong một ngữ nghĩa truy vấn cụ thể.
- `COUNT(field)`: thường phụ thuộc hệ và cách xử lý giá trị thiếu/null.
- `COUNT(DISTINCT customerId)`: số khách duy nhất, **không phải số đơn**.
- `COUNT(*)` sau một phép join/traversal có thể đếm **số dòng khớp hoặc số đường đi**, không còn bằng số entity gốc.

Nếu một đơn có ba dòng sản phẩm, kết hợp đơn với dòng sản phẩm rồi `COUNT(*)` có thể ra **3**, dù chỉ có **1 đơn**. Người viết query phải chọn đơn vị đếm phù hợp với câu hỏi.

### 3.2. SUM và AVG phải xác định chính sách giá trị rỗng

Với một nhóm có giá trị `120000`, `230000` và một dòng thiếu `totalVnd`, cần định nghĩa:

- Dòng thiếu trường bị loại khỏi phép tính hay coi là 0?
- Số đơn vẫn tính 3 hay chỉ 2?
- `AVG` được tính trên tất cả đơn hay chỉ trên giá trị hợp lệ?

Hành vi của `null`, missing và giá trị không phải số **có thể khác giữa engine hoặc phép toán**. Một hệ thống báo cáo nên chuẩn hóa schema và dữ kiện thiếu trước khi tổng hợp, thay vì để kết quả phụ thuộc ngầm vào quy tắc engine.

### 3.3. Tổng tiền cần chọn kiểu số phù hợp

Với đơn vị **VND nguyên**, có thể lưu `totalVnd` dưới dạng số nguyên 64-bit và cộng bằng kiểu đủ lớn. Với tiền có phần lẻ, nên dùng **decimal/fixed-point hoặc số nguyên theo đơn vị nhỏ nhất**, tránh dùng Float32/Float64 rồi kỳ vọng tổng tài chính luôn chính xác đến từng đơn vị.

Nếu số đơn và giá trị mỗi đơn lớn, tổng có thể vượt phạm vi kiểu số. Cần kiểm tra kiểu accumulator, kết quả serialization và khả năng overflow của engine. **Kiểu dữ liệu trên hàng và kiểu dữ liệu khi SUM không luôn giống nhau**.

### 3.4. Ngày lịch và khoảng thời gian

Khoảng Q1 được định nghĩa là:

~~~text
[2026-11-14T00:00:00Z, 2026-11-16T00:00:00Z)
~~~

Tức là **bao gồm mốc bắt đầu, loại trừ mốc kết thúc**. Khi nhóm theo ngày của cửa hàng, phải tính ranh giới bằng **IANA time zone** của cửa hàng trước; không thể dùng UTC midnight thay thế mọi ngày địa phương, nhất là ở vùng có DST.

## 4. Truy vấn tổng hợp có thể tốn kém dù đầu ra rất nhỏ

Một truy vấn trả đúng ba hàng kết quả **không có nghĩa** nó chỉ đọc ba hàng. Nếu phải đọc 30 triệu đơn rồi gộp thành ba nhóm, chi phí vẫn có thể rất lớn.

Một phép tổng hợp thường trải qua:

~~~text
1. Xác định tập dữ liệu có khả năng khớp (index/partition/scan).
2. Đọc và lọc các bản ghi.
3. Tính khóa nhóm.
4. Duy trì trạng thái accumulator của mỗi nhóm.
5. Khi chạy phân tán: hợp nhất kết quả từ các node/shard.
6. Sort, limit, serialize kết quả.
~~~

### 4.1. Độ phức tạp khái niệm

Nếu `N` bản ghi cần xét và `G` nhóm:

- Đọc/lọc có thể cần xét tới `N` bản ghi nếu không có đường truy cập giúp thu hẹp.
- Hash aggregation thường giữ trạng thái theo số nhóm `G`, ảnh hưởng đến RAM.
- Sort toàn bộ `G` nhóm có thể cần khoảng `O(G log G)` trong một mô hình thuật toán thông thường.
- Trong hệ phân tán còn có **truyền dữ liệu và hợp nhất partial aggregates** giữa các node.

Đây là mô hình để lý giải chi phí, **không phải bảo đảm thuật toán hoặc độ phức tạp của mọi database**. Một engine có thể dùng streaming aggregation khi dữ liệu đã sắp theo khóa nhóm, hoặc dùng cấu trúc index/partial aggregation khác.

### 4.2. Hai hướng thực hiện

~~~mermaid
flowchart TD
    Q["Cần số liệu theo shop/ngày"] --> D{"Cách tính"}
    D -->|Tính lúc đọc| A["Query dữ liệu gốc"]
    A --> B["Lọc + group + aggregate"]
    B --> R["Kết quả"]
    D -->|Tính trước| E["Ghi đơn / sự kiện thay đổi"]
    E --> F["Cập nhật bảng summary"]
    F --> G["Đọc theo khóa shop/ngày"]
    G --> R
~~~

**Tính khi đọc (on-demand):** ít phải duy trì bản tổng hợp riêng, linh hoạt cho các câu hỏi thay đổi; nhưng chi phí đọc phụ thuộc số bản ghi.

**Tính trước (pre-aggregation):** truy vấn dashboard nhanh, nhưng tốn thêm ghi, lưu trữ, đồng bộ, xử lý event lặp/sai thứ tự và khả năng sửa lệch.

Lựa chọn phù hợp phụ thuộc **QPS, dữ liệu nguồn, kiểu nhóm, độ mới và ngân sách hệ thống**, không chỉ phụ thuộc tên NoSQL.

## 5. MongoDB: aggregation pipeline trực tiếp trên document

MongoDB hỗ trợ **aggregation pipeline**: dữ liệu đi qua các stage như `$match`, `$project`, `$group`, `$sort`, `$limit`, `$lookup`, `$facet`.

Giả sử collection `orders` có các trường:

~~~javascript
{
  tenantId: "merchant-a",
  orderId: "O101",
  shopId: "shop-12",
  createdAt: ISODate("2026-11-14T08:10:00Z"),
  status: "PAID",
  totalVnd: NumberLong("120000")
}
~~~

### 5.1. Q1 bằng pipeline

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "merchant-a",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-14T00:00:00Z"),
        $lt: ISODate("2026-11-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        shopId: "$shopId",
        dayUtc: {
          $dateTrunc: {
            date: "$createdAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      paidOrderCount: { $sum: 1 },
      paidOrderTotalVnd: { $sum: "$totalVnd" },
      avgPaidOrderVnd: { $avg: "$totalVnd" }
    }
  },
  {
    $project: {
      _id: 0,
      dayUtc: "$_id.dayUtc",
      shopId: "$_id.shopId",
      paidOrderCount: 1,
      paidOrderTotalVnd: 1,
      avgPaidOrderVnd: 1
    }
  },
  { $sort: { dayUtc: 1, shopId: 1 } }
]);
~~~

Các stage:

| Stage | Vai trò |
| --- | --- |
| `$match` | Chọn tenant, trạng thái và khoảng tạo đơn |
| `$dateTrunc` | Tính đầu ngày UTC để tạo khóa nhóm |
| `$group` | Gom những order có cùng `shopId + dayUtc` |
| `$sum: 1` | Đếm từng document trong nhóm |
| `$sum: "$totalVnd"` | Cộng giá trị các đơn |
| `$avg` | Tính giá trị trung bình trên các giá trị số hợp lệ |
| `$project` | Định dạng đầu ra và bỏ khóa `_id` kỹ thuật |
| `$sort` | Trả kết quả theo ngày và cửa hàng |

Kết quả phản ánh bảng kỳ vọng ở mục 2, nếu dữ liệu tương ứng đã được lưu bằng **kiểu Date và Number thích hợp**.

### 5.2. Vì sao lọc trước khi nhóm?

Nếu đặt nhóm toàn collection rồi mới tìm ngày và tenant, hệ thống có thể phải giữ rất nhiều nhóm/giá trị trung gian không cần thiết. Thực hành thường là **thu hẹp tập dữ liệu càng sớm càng phù hợp**.

Tuy nhiên `$match` chỉ tối ưu nếu index và kế hoạch thực thi cho phép. Một stage `$group` vẫn có thể phải đọc **tất cả document thỏa `$match`** để cộng chính xác, chứ không được phép dừng sau 20 document chỉ vì dashboard cần 20 nhóm.

### 5.3. Index cho bộ lọc

Một phương án cần đánh giá:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1,
  shopId: 1
});
~~~

Trong Q1, `tenantId` và `status` là điều kiện bằng nhau, `createdAt` là khoảng. Index ghép như trên có thể giúp định vị nhanh tập document cần xét; vị trí trường tối ưu còn phụ thuộc **phân bố giá trị, selectivity, loại truy vấn và phiên bản engine**.

**Có index hỗ trợ `$match` không có nghĩa `$group` được trả lời mà không đọc dữ liệu.** Cần dùng `explain` và metric thực tế để biết có bao nhiêu document/index key được xét.

### 5.4. Filter theo nhóm sau khi aggregate

Nếu yêu cầu chỉ hiển thị những nhóm có ít nhất hai đơn `PAID`, thêm `$match` **sau** `$group`:

~~~javascript
{
  $match: {
    paidOrderCount: { $gte: 2 }
  }
}
~~~

Đây là ý tưởng tương đương **HAVING** trong SQL. Nó lọc **nhóm đã tính xong**, không phải lọc document gốc.

### 5.5. Đếm khách duy nhất

Giả sử muốn đếm bao nhiêu `customerId` duy nhất trong từng nhóm. MongoDB có thể dùng:

~~~javascript
{
  $group: {
    _id: {
      shopId: "$shopId",
      dayUtc: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "UTC"
        }
      }
    },
    customerIds: { $addToSet: "$customerId" }
  }
}
~~~

Sau đó dùng `$size` trên mảng `customerIds` để lấy số lượng, nhưng **giữ toàn bộ ID khách trong một nhóm có thể tiêu tốn bộ nhớ lớn**, đặc biệt ở cửa hàng rất đông khách. Với cardinality cao hoặc cần thống kê gần đúng, nên đánh giá chiến lược khác, chẳng hạn job tổng hợp phân tán hoặc thuật toán ước lượng distinct khi nghiệp vụ cho phép.

### 5.6. Join bằng `$lookup` có giới hạn chi phí

`$lookup` hỗ trợ kết hợp dữ liệu từ collection khác theo những quy tắc của MongoDB. Đây là khả năng mạnh, nhưng không nên hiểu rằng join với toàn bộ bảng lớn luôn có chi phí như một phép đọc theo khóa.

Ví dụ, nếu mỗi order ghép tới nhiều order line, kết quả có thể **nhân số dòng** trước khi `$group`. Khi cần đếm số đơn, hãy xác định có dùng `orderId` duy nhất hoặc nhóm trở lại theo order trước khi cộng hay không.

### 5.7. Giới hạn bộ nhớ và sharding

`$group` và `$sort` có thể là các **blocking stages**: chúng phải xử lý nhiều đầu vào trước khi cho ra đầu ra. Ở quy mô lớn, pipeline có thể dùng nhiều RAM hoặc cơ chế ghi tạm ra đĩa theo khả năng và cấu hình phiên bản.

Nếu collection được **shard**, engine có thể thực hiện một phần aggregation trên shard rồi hợp nhất kết quả. Chi phí bao gồm cả **network, merge, memory và khả năng phải phân phối lại dữ liệu**.

Các yếu tố cần đo:

- Số document được đọc sau `$match`.
- Số nhóm tạo ra và cardinality của khóa nhóm.
- Kích thước stage `$group`, `$sort`.
- Tỷ lệ dùng disk spill, nếu có.
- Thời gian tổng hợp theo tenant lớn/nhỏ.
- Tài nguyên và độ trễ khi query chạy đồng thời.

**Kết luận về MongoDB:** có thể diễn đạt Q1 trực tiếp bằng pipeline khá rõ ràng, nhưng khả năng biểu đạt **không bảo đảm chi phí luôn thấp**.

## 6. MongoDB: nhóm theo ngày địa phương khác ngày UTC

Một shop ở `Asia/Ho_Chi_Minh` yêu cầu “ngày bán hàng của shop”. Khi đó khóa nhóm theo UTC có thể không đúng nghiệp vụ.

Ví dụ document:

~~~text
createdAt = 2026-11-13T18:00:00Z
Giờ Việt Nam = 2026-11-14T01:00:00+07:00
~~~

Đối với ngày UTC, event thuộc **13/11**. Đối với ngày của cửa hàng, nó thuộc **14/11**.

MongoDB có thể tính đầu ngày theo timezone:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Nhưng để lọc trước bằng index, cũng cần chuyển **ranh giới ngày địa phương** sang các instant UTC chính xác. Không chỉ thay timezone của `$dateTrunc` rồi vẫn lọc dữ liệu theo hai mốc `00:00Z` nếu nghiệp vụ là ngày local.

Trong hệ nhiều shop có timezone khác nhau, còn phải quyết định:

- Lưu zone ở shop hiện hành hay snapshot zone tại thời điểm tạo đơn?
- Nếu shop đổi timezone, dữ liệu lịch sử được nhóm lại hay giữ theo quy tắc cũ?
- Có yêu cầu thống kê theo “ngày vận hành” riêng, ví dụ bắt đầu lúc 06:00 không?
- Khi DST làm ngày dài 23 hoặc 25 giờ, phải dùng ranh giới lịch, không cộng cứng 24 giờ.

**Định nghĩa nhóm theo thời gian là một phần của API/report contract, không phải chi tiết trang trí của câu query.**

## 7. Cassandra/CQL: aggregate có, GROUP BY bị ràng buộc bởi khóa

Cassandra được thiết kế để đọc/ghi hiệu quả theo **partition key** và **clustering order**. Nó hỗ trợ một số hàm tổng hợp như `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, nhưng **không phải một analytical SQL engine cho mọi kiểu nhóm trên mọi thuộc tính**.

### 7.1. Bảng theo đường truy cập

Nếu Q1 thường được xem theo từng shop và ngày, ta có thể tạo bảng:

~~~sql
CREATE TABLE orders_by_shop_day (
    tenant_id text,
    shop_id text,
    day_utc date,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, day_utc),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Một partition chứa **các đơn của một shop trong một ngày UTC**. Query theo khóa định vị:

~~~sql
SELECT order_id, status, total_vnd
FROM orders_by_shop_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND day_utc = '2026-11-14';
~~~

Những hàng được đọc thuộc **một nhóm cửa hàng/ngày** đã xác định bởi partition key. Nếu ứng dụng lọc `status = PAID` ở phía client, nó phải đọc dữ liệu của partition rồi lọc; với partition lớn, cách này có thể đắt.

### 7.2. COUNT không miễn phí

~~~sql
SELECT COUNT(*)
FROM orders_by_shop_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND day_utc = '2026-11-14';
~~~

Câu lệnh đếm **số hàng trong partition thỏa query**, không tự cung cấp thống kê có sẵn tức thì giống một counter ứng dụng. Để trả kết quả chính xác, engine vẫn cần đọc/xét dữ liệu liên quan. Nếu partition có hàng triệu đơn hoặc nhiều tombstone, việc đếm có thể tốn đáng kể tài nguyên.

Với bảng này, `COUNT(*)` **chưa phải Q1**, vì nó đếm cả `CREATED`, `REFUNDED` và trạng thái khác. Không được dùng con số đó rồi gọi là `paidOrderCount`.

### 7.3. Cách thiết kế bảng lọc theo trạng thái

Một đường đọc khác:

~~~sql
CREATE TABLE orders_by_shop_status_day (
    tenant_id text,
    shop_id text,
    status text,
    day_utc date,
    created_at timestamp,
    order_id text,
    total_vnd bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, status, day_utc),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Khi query đúng khóa:

~~~sql
SELECT COUNT(*), SUM(total_vnd), AVG(total_vnd)
FROM orders_by_shop_status_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND status = 'PAID'
  AND day_utc = '2026-11-14';
~~~

Ta có thể lấy aggregate cho **một nhóm đã được định vị bởi partition key**, theo các hàm CQL mà phiên bản Cassandra tương ứng hỗ trợ. Dù vậy, query vẫn có thể phải xét **tất cả hàng của partition**. Thêm bảng mới giúp thu hẹp đường đọc theo trạng thái, **không biến SUM/AVG thành phép tra cứu hằng số thời gian**.

**Cảnh báo khi trạng thái đổi:** nếu order chuyển `PAID -> SHIPPED`, hệ thống phải **xóa hàng khỏi partition PAID và thêm sang partition SHIPPED** hoặc dùng mô hình quản lý tương đương. Nếu chỉ thêm vào trạng thái mới, số liệu PAID bị giữ thừa. Việc xóa/cập nhật qua partition còn gây chi phí tombstone, đồng bộ và nhất quán.

### 7.4. GROUP BY trong CQL không giống GROUP BY của SQL tổng quát

CQL có `GROUP BY` trong những ngữ cảnh được hỗ trợ, nhưng **chỉ có thể nhóm theo các cột primary key với thứ tự và những giới hạn do CQL quy định**, thay vì tùy ý dùng mọi biểu thức.

Ví dụ không được coi là truy vấn Cassandra hợp lệ chỉ vì trông giống SQL:

~~~sql
-- MINH HỌA Ý TƯỞNG, KHÔNG PHẢI CQL TỔNG QUÁT HỢP LỆ
SELECT date_trunc('day', created_at),
       status,
       COUNT(*),
       SUM(total_vnd)
FROM orders_by_id
GROUP BY date_trunc('day', created_at), status;
~~~

Những hạn chế cơ bản cần ghi nhớ:

- Không có cơ chế join và grouped expression linh hoạt như trong nhiều hệ SQL phân tích.
- `GROUP BY` bị ràng buộc bởi **primary-key layout**, không phải mọi thuộc tính của bảng.
- Đọc nhiều partition để nhóm xuyên toàn cluster có thể cần một tầng xử lý khác; Cassandra không tự biến một yêu cầu toàn tenant thành phép tổng hợp rẻ.
- Aggregate và `LIMIT` vẫn có thể phải duyệt nhiều hàng, tùy đường truy cập và cú pháp.
- Các chi tiết CQL về grouping, filtering và aggregate có thể thay đổi theo phiên bản; **cần kiểm tra cú pháp và giới hạn ở engine thực tế**.

Trong nhiều bài toán dashboard, giải pháp phù hợp là **thiết kế bảng tổng hợp theo khóa truy vấn** và cập nhật nó khi nguồn thay đổi.

### 7.5. Cassandra counters: có ích nhưng cần hiểu giới hạn

Cassandra cung cấp **counter columns** cho một số kiểu đếm phân tán. Tuy nhiên:

- Counter update có ngữ nghĩa và giới hạn khác cột dữ liệu thường.
- Không thể coi một counter increment là **idempotent** khi request timeout rồi retry.
- Không tự giải quyết việc giảm counter khi order rời trạng thái `PAID`.
- Không tự phối hợp nguyên tử với mọi mutation trên các partition nguồn.
- Không nên dùng một counter chỉ vì query `COUNT(*)` chậm mà chưa có cơ chế kiểm soát retry, duplicate và đối soát.

Nếu nghiệp vụ cần tổng có độ đúng cao, hãy thiết kế **đường ghi có eventId/version và reconciliation**, hoặc chọn storage/transaction phù hợp hơn cho phép cập nhật.

**Kết luận về Cassandra:** truy vấn nhóm hiệu quả thường bắt đầu từ **khóa đã thiết kế sẵn**. Với nhóm toàn cục, nhóm tùy ý hoặc aggregate thường xuyên trên nhiều partition, cần cân nhắc read model/OLAP.

## 8. DynamoDB: Query hiệu quả theo khóa, không có GROUP BY tùy ý

DynamoDB cung cấp các thao tác như **GetItem**, **Query** và **Scan**, cùng điều kiện key/filter và lựa chọn projection. Nó không cho phép một câu `GROUP BY shopId, date` rồi `SUM(totalVnd)` trên toàn table theo kiểu SQL phân tích.

### 8.1. Truy vấn một tập item theo partition key

Giả sử item trong bảng:

~~~text
PK = TENANT#merchant-a#SHOP#shop-12#DAY#2026-11-14
SK = ORDER#2026-11-14T08:10:00.000Z#O101

status   = PAID
totalVnd = 120000
~~~

Các item cùng partition có thể được lấy bằng `Query`. Nếu đã chọn sort key phù hợp, chúng còn có thứ tự dựa trên key.

**Nhưng `Query` trả item, không trả phép SUM trên những item đó.** Ứng dụng hoặc một pipeline xử lý phải tính tổng, hoặc kết quả được duy trì sẵn ở item summary.

### 8.2. `Count` không có nghĩa tổng hợp toàn bảng không tốn đọc

Trong một yêu cầu Query hoặc Scan, `Select = COUNT` có thể cho biết số item phù hợp trong **phần kết quả của request/trang** theo ngữ nghĩa API. Nhưng:

- DynamoDB vẫn cần đọc/xét các item và tiêu thụ tài nguyên đọc.
- Có giới hạn dữ liệu được xử lý trong một request; cần tiếp tục từ **`LastEvaluatedKey`** để duyệt các trang còn lại.
- Một `FilterExpression` được áp sau khi đọc dữ liệu phù hợp với key/scan, nên không tự làm giảm lượng dữ liệu đã phải đọc tương ứng.
- Không thể suy ra “có đúng 20 item” chỉ vì đã gọi một request `COUNT` hoặc `Limit = 20`.

Do đó, để tính Q1 bằng cách duyệt item, client phải query tất cả partition ngày/shop liên quan, phân trang đầy đủ rồi tự cộng/đếm.

### 8.3. GSI giúp tìm theo khóa khác, không tự tạo tổng

Một **Global Secondary Index (GSI)** có thể phục vụ truy vấn theo `tenantId + status + shopId + day` hoặc một đường truy cập khác mà bảng chính không có. Nhưng GSI vẫn là **đường truy cập item**:

- Nó không mặc nhiên giữ một `SUM(totalVnd)` đã tính sẵn.
- Nó có chi phí lưu trữ và cập nhật index.
- Truy vấn GSI có đặc điểm nhất quán đọc và projection khác bảng chính.
- Với dữ liệu chia thành nhiều partition/bucket, phải fan-out và gộp kết quả ở tầng phù hợp.

Khi Q1 được gọi liên tục, duy trì item summary theo ngày/shop thường là phương án đáng cân nhắc.

### 8.4. Item tổng hợp theo khóa truy vấn

Ví dụ:

~~~json
{
  "PK": "TENANT#merchant-a#SHOP#shop-12",
  "SK": "PAID_SUMMARY#2026-11-14",
  "paidOrderCount": 2,
  "paidOrderTotalVnd": 350000,
  "summaryVersion": 18
}
~~~

Dashboard đọc một item/nhóm thay vì đọc hàng nghìn order để SUM mỗi lần. Để tính trung bình:

\[
\operatorname{AVG} =
\frac{\text{paidOrderTotalVnd}}{\text{paidOrderCount}}
\]

chỉ khi `paidOrderCount > 0`. Giữ **sum và count** thường linh hoạt hơn việc chỉ giữ AVG: có thể gộp nhiều ngày/shop bằng cách cộng sum và count rồi chia, không lấy **trung bình của các trung bình** một cách sai trọng số.

### 8.5. Cập nhật số đếm không tự an toàn khi retry

DynamoDB có thể hỗ trợ thao tác **cập nhật nguyên tử trên một item**, ví dụ tăng hai thuộc tính bằng `ADD` hay một biểu thức cập nhật thích hợp. Nhưng nếu service:

~~~text
1. Ghi Order O101
2. Tăng paidOrderCount thêm 1
3. Tăng paidOrderTotalVnd thêm 120000
~~~

rồi timeout và retry, tổng có thể tăng hai lần trừ khi quy trình ghi/đánh dấu event đã áp dụng có biện pháp chống lặp thích hợp.

Một **transaction có điều kiện** trong phạm vi DynamoDB hỗ trợ có thể giúp phối hợp mutation và dấu vết idempotency; pipeline từ stream có thể vẫn được phát nhiều lần và cần consumer xử lý idempotent.

Đặc biệt khi order chuyển từ PAID sang trạng thái khác, phải xác định **delta cần trừ**, không chỉ có logic cộng khi đơn mới xuất hiện.

### 8.6. Hot summary key

Nếu mọi đơn của một shop lớn đều cập nhật cùng item:

~~~text
TENANT#merchant-a#SHOP#shop-12
SK=PAID_SUMMARY#2026-11-14
~~~

thì item ấy có thể thành **điểm nóng khi ghi**. Một kỹ thuật là chia summary thành nhiều shard theo hash orderId:

~~~text
PAID_SUMMARY#2026-11-14#SHARD#0
PAID_SUMMARY#2026-11-14#SHARD#1
...
PAID_SUMMARY#2026-11-14#SHARD#7
~~~

Mỗi sự kiện cập nhật một shard ổn định; khi đọc, ứng dụng cộng cả 8 shard. Đây là đổi **fan-out đọc** để giảm cạnh tranh **ghi vào một item**. Số shard, khóa idempotency và việc đổi số shard phải được thiết kế có phiên bản rõ.

**Kết luận về DynamoDB:** lựa chọn key/GSI giúp thu hẹp những item cần đọc; tổng hợp nhiều item thường được thực hiện ở ứng dụng, pipeline hoặc **bảng summary**, không phải một lệnh GROUP BY tùy ý.

## 9. Redis: tổng hợp theo cấu trúc dữ liệu đã chọn

Redis cung cấp nhiều cấu trúc như **String**, **Hash**, **Set**, **Sorted Set** và **Stream**. Có thể đếm/cộng rất nhanh khi dữ liệu đã được biểu diễn đúng dạng, nhưng Redis truyền thống không phải một SQL engine nhóm bất kỳ trường nào trong các JSON value.

### 9.1. Counter theo shop/ngày

Ví dụ một hash chứa summary:

~~~text
HINCRBY summary:merchant-a:shop-12:2026-11-14 paid_count 1
HINCRBY summary:merchant-a:shop-12:2026-11-14 paid_total_vnd 120000

HGETALL summary:merchant-a:shop-12:2026-11-14
~~~

`HINCRBY` thay đổi giá trị số nguyên trên một field một cách nguyên tử cho lệnh tương ứng. **Hai lệnh `HINCRBY` độc lập không tạo một cập nhật nhiều field nguyên tử** nếu có lỗi ở giữa.

Muốn cập nhật nhiều field cùng một bước có thể dùng **Lua script hoặc transaction Redis** tùy ranh giới mong muốn. Tuy nhiên, một script cập nhật hash **không tự giao dịch chung** với bản ghi nguồn ở database khác.

### 9.2. Nhóm sẵn theo key

Khi key đã chứa:

~~~text
tenantId + shopId + dayUtc
~~~

thì “group by shop/day” phần lớn được thực hiện **lúc ghi**. Khi đọc, ứng dụng chỉ truy vấn những key summary cần thiết.

Nếu dashboard muốn thống kê theo **loại sản phẩm, khu vực, giờ hoặc nhóm khách**, Redis không tự suy ra mọi group từ hàng triệu value đã lưu. Cần tạo các summary tương ứng hoặc dùng một engine phân tích phù hợp.

### 9.3. Sorted Set hỗ trợ đếm theo score

Giả sử lưu eventId trong sorted set với score là **epoch milliseconds**:

~~~text
ZADD events:merchant-a:shop-12 1794623400123 evt-9001
ZADD events:merchant-a:shop-12 1794623460000 evt-9002
ZCOUNT events:merchant-a:shop-12 1794623400000 1794623500000
~~~

`ZCOUNT` đếm phần tử có score trong khoảng chỉ định. Nó **không tự tính `SUM(totalVnd)`**, cũng không biết `status=PAID` nếu bạn chưa biểu diễn điều kiện bằng key/cấu trúc khác.

Nếu dùng timestamp làm score, cần:

- Thống nhất **đơn vị epoch** (seconds/ms).
- Cẩn thận khi cần biên khoảng **[from, to)**; cú pháp khoảng score có quy tắc inclusive/exclusive riêng.
- Biết rằng score Redis là **double**; epoch nano giây hiện đại không được biểu diễn chính xác đến từng đơn vị.
- Dùng ID duy nhất vì hai sự kiện có thể có cùng timestamp.

### 9.4. Stream và worker tổng hợp

Redis Streams có thể làm nguồn event/luồng xử lý trong những thiết kế tương ứng:

~~~text
XADD orders:events * orderId O101 status PAID totalVnd 120000
~~~

Consumer đọc event và cập nhật summary. Nhưng event có thể được xử lý lại sau lỗi hoặc chuyển ownership giữa worker, nên cập nhật counter cần **idempotency và đối soát**. Không nên nghĩ stream tự bảo đảm một event chỉ tác động đúng một lần lên mọi hệ downstream.

### 9.5. Redis Search hoặc module bổ sung

Một triển khai Redis có cài **mô-đun tìm kiếm/tổng hợp** có thể cung cấp khả năng truy vấn khác Redis core. Khi so sánh tính năng, cần nói rõ sản phẩm, module và phiên bản; không đồng nhất mọi API bổ sung với lệnh Redis core.

**Kết luận về Redis:** rất tốt cho những **counter/summary được định nghĩa trước và truy cập nhanh**; các truy vấn nhóm ngẫu hứng theo mọi thuộc tính cần mô hình dữ liệu hoặc công cụ khác.

## 10. Neo4j/Cypher: nhóm theo node và mẫu quan hệ

Trong graph database, tổng hợp thường gắn với kết quả của một **graph pattern**.

Giả sử:

~~~text
(Customer)-[:PLACED]->(Order)
(Order)-[:BELONGS_TO]->(Shop)
~~~

Một số bản ghi mẫu:

~~~cypher
MERGE (shop12:Shop {id: 'shop-12'})
MERGE (shop21:Shop {id: 'shop-21'})

MERGE (o101:Order {id: 'O101'})
SET o101.status = 'PAID', o101.totalVnd = 120000
MERGE (o101)-[:BELONGS_TO]->(shop12)

MERGE (o102:Order {id: 'O102'})
SET o102.status = 'PAID', o102.totalVnd = 230000
MERGE (o102)-[:BELONGS_TO]->(shop12)

MERGE (o201:Order {id: 'O201'})
SET o201.status = 'PAID', o201.totalVnd = 310000
MERGE (o201)-[:BELONGS_TO]->(shop21);
~~~

Để đếm và cộng giá trị đơn đang PAID theo shop:

~~~cypher
MATCH (o:Order)-[:BELONGS_TO]->(shop:Shop)
WHERE o.status = 'PAID'
RETURN shop.id AS shopId,
       count(o) AS paidOrderCount,
       sum(o.totalVnd) AS paidOrderTotalVnd,
       avg(o.totalVnd) AS avgPaidOrderVnd
ORDER BY shopId;
~~~

Trong Cypher, các biểu thức **không aggregate** trong `RETURN` hoặc `WITH` đóng vai trò khóa nhóm theo quy tắc của ngôn ngữ, thay vì một mệnh đề `GROUP BY` riêng giống SQL.

### 10.1. Tại sao COUNT(*) trên graph có thể đếm sai entity?

Giả sử một Order nối tới 3 node Product qua 3 relationship:

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(item:OrderItem)
RETURN o.id, count(*) AS rows;
~~~

Nếu O101 có ba dòng hàng, `count(*)` tương ứng có thể là **3 dòng khớp**, không phải một đơn.

Nếu câu hỏi là số order duy nhất:

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(item:OrderItem)
RETURN count(DISTINCT o) AS distinctOrders;
~~~

**Duyệt nhiều cạnh, cạnh song song và variable-length path** có thể nhân số hàng trung gian rất mạnh. Với mỗi metric, phải xác định đang đếm node, relationship, path, hay tuple kết quả.

### 10.2. Chi phí traversal ảnh hưởng aggregate

Một query `MATCH (user)-[:FOLLOWS*1..5]->(p)` rồi `count(p)` có thể phải mở rộng số đường đi rất lớn, kể cả khi kết quả cuối là một số duy nhất. Cần:

- Neo điểm bắt đầu bằng ID có index.
- Giới hạn **độ sâu và kiểu/hướng relationship**.
- Phân biệt `count(p)` với `count(DISTINCT p)`.
- Quan sát `EXPLAIN`/`PROFILE`.
- Cân nhắc precompute với số liệu được đọc rất thường xuyên.

**Kết luận về graph:** có thể diễn đạt aggregate rất tự nhiên trên **mẫu quan hệ**, nhưng chi phí phụ thuộc kích thước đồ thị khớp và số đường mở rộng.

## 11. Elasticsearch/OpenSearch: bucket aggregation trên search index

Một hệ tìm kiếm thường cung cấp **bucket aggregations** như `terms`, `date_histogram` và **metric aggregations** như `sum`, `avg`, `min`, `max`, `cardinality`.

Giả sử index `orders-search` chứa các field đã được ánh xạ phù hợp:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O101",
  "shopId": "shop-12",
  "createdAt": "2026-11-14T08:10:00Z",
  "status": "PAID",
  "totalVnd": 120000
}
~~~

### 11.1. Q1 bằng date_histogram và terms

Ví dụ DSL minh họa:

~~~json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "merchant-a" } },
        { "term": { "status": "PAID" } },
        {
          "range": {
            "createdAt": {
              "gte": "2026-11-14T00:00:00Z",
              "lt": "2026-11-16T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "by_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "UTC"
      },
      "aggs": {
        "by_shop": {
          "terms": {
            "field": "shopId",
            "size": 100
          },
          "aggs": {
            "paid_total_vnd": { "sum": { "field": "totalVnd" } },
            "paid_avg_vnd": { "avg": { "field": "totalVnd" } }
          }
        }
      }
    }
  }
}
~~~

Các field `tenantId`, `status`, `shopId` cần được ánh xạ dạng phù hợp cho **exact term/bucket** (thường là kiểu `keyword` hoặc tương đương). Nếu chúng là `text` được phân tích từ ngữ, query term và aggregation có thể khác kỳ vọng.

`doc_count` trên từng bucket thể hiện **số document khớp**, nhưng chỉ bằng số đơn nếu index bảo đảm **mỗi order hiện tại ứng với đúng một document**. Nếu hệ thống index thêm bản sao hoặc lịch sử nhiều phiên bản của cùng order, cần điều chỉnh định nghĩa đếm.

### 11.2. Aggregation phân tán có chi phí và sai số

Trong cluster phân tán, `terms` aggregation thường thu thập ứng viên bucket từ từng shard rồi hợp nhất. Với **cardinality cao**, lựa chọn `size`, `shard_size` và cách sắp xếp có thể ảnh hưởng độ chính xác/tính đầy đủ của những bucket được trả.

Nếu mục tiêu là **liệt kê đầy đủ mọi shop** thay vì top bucket, cần đánh giá **composite aggregation** và phân trang theo khóa nhóm, thay vì tăng `terms.size` tùy tiện đến một số rất lớn.

Các phép **cardinality** cho số giá trị duy nhất có thể sử dụng thuật toán xấp xỉ, tùy engine và tham số. Một số metric `sum` trên giá trị số thực cũng có sai số số học. Vì vậy cần biết chính xác số liệu nào là **exact**, số liệu nào là **approximate** trong cấu hình đang chạy.

### 11.3. Ngày theo lịch và timezone

`date_histogram` theo `calendar_interval: day` và `time_zone` tạo bucket theo ngày lịch của zone. Khi nguồn dữ liệu đến từ nhiều quốc gia, phải xác định báo cáo là:

- Ngày UTC toàn nền tảng.
- Ngày địa phương của tenant/shop.
- Một timezone hiển thị cố định do người dùng chọn.

Một aggregation theo UTC không thể tự được gọi là “doanh số ngày của cửa hàng” nếu cửa hàng thuộc zone khác.

### 11.4. Search index là bản chiếu, không mặc nhiên là nguồn chuẩn

Nếu order chuyển trạng thái nhưng pipeline index chưa cập nhật, search aggregation có thể phản ánh trạng thái cũ. Khi tổng hợp phục vụ mục đích có yêu cầu tài chính/kiểm toán, cần:

- Xác định dữ liệu nguồn có thẩm quyền.
- Đo **indexing lag**.
- Dùng đối soát hoặc một hệ phân tích có cơ chế snapshot phù hợp.
- Kiểm tra liệu danh sách search index có bị thiếu, trùng hoặc còn document đã xóa.

**Kết luận về search:** có bộ công cụ aggregation phong phú cho bucket, thời gian và nhiều filter, nhưng phải hiểu **distributed aggregation, kết quả xấp xỉ và độ mới của index**.

## 12. So sánh khả năng biểu đạt theo từng hệ

| Hệ / mô hình | Tổng hợp/nhóm trực tiếp | Điểm mạnh | Giới hạn và điều kiện cần nhớ |
| --- | --- | --- | --- |
| **MongoDB document** | Pipeline `$match/$group/$sum/$avg` và nhiều stage khác | Query theo trường linh hoạt, nhóm nhiều chiều | Bộ nhớ, scan, spill, join và merge trên shard |
| **Cassandra wide-column** | Aggregate CQL; `GROUP BY` có ràng buộc primary key | Đọc theo partition/clustering key hiệu quả | Không phải arbitrary GROUP BY/OLAP; đếm/sum có thể quét nhiều hàng |
| **DynamoDB key–value/document** | Không có GROUP BY tùy ý trong Query/Scan | Get/Query theo key, GSI và item summary | Query trả item, COUNT có phân trang/chi phí đọc; phải tự tổng hợp |
| **Redis core** | Counter, Hash, Set, Sorted Set, Stream theo cấu trúc | Tổng hợp đã tính sẵn rất nhanh | Không tự group bất kỳ field trong value; phải xử lý retry/idempotency |
| **Neo4j graph** | Cypher aggregate theo mẫu MATCH | Tổng hợp theo quan hệ | Path expansion làm tăng số hàng; DISTINCT và depth limit quan trọng |
| **Elasticsearch/OpenSearch** | Bucket và metric aggregations | Nhiều kiểu nhóm theo search/filter/time | Shard merge, bucket limit, approximate cardinality/terms và indexing lag |
| **OLAP/columnar engine** | SQL aggregate/grouping/window phong phú tùy sản phẩm | Phù hợp dashboard phân tích khối lượng lớn | Thêm pipeline, độ trễ ingest, quản lý nguồn dữ liệu và chi phí |

**Không dùng bảng này như tuyên bố mọi phiên bản đều có cùng cú pháp.** Kiểm tra phiên bản, driver, module, kiểu index và cấu hình triển khai trước khi áp dụng. Điều quan trọng là hiểu **họ khả năng** của mỗi hệ và **chi phí của đường truy cập thực tế**.

## 13. Khi nào cần bảng tổng hợp được tính trước?

Giả sử một tenant có **20 triệu đơn**. Dashboard hiển thị 30 ngày gần nhất của 200 cửa hàng, được tải lại rất thường xuyên.

Nếu mỗi request:

~~~text
Scan hàng triệu đơn
-> lọc trạng thái
-> nhóm 200 × 30 bucket
-> trả một số nghìn dòng
~~~

thì đầu ra có thể nhỏ nhưng đầu vào rất lớn. Một **read model theo shop/ngày** có thể giảm mạnh chi phí đọc bằng cách chuyển công việc sang lúc nguồn thay đổi.

### 13.1. Mô hình summary

~~~text
shop_paid_daily_summary

Key: (tenantId, shopId, dayUtc)
Fields:
  paidOrderCount
  paidOrderTotalVnd
  lastProjectedVersionOrCheckpoint
  updatedAt
~~~

Ví dụ:

~~~json
{
  "tenantId": "merchant-a",
  "shopId": "shop-12",
  "dayUtc": "2026-11-14",
  "paidOrderCount": 2,
  "paidOrderTotalVnd": 350000,
  "lastReconciledAt": "2026-11-14T14:00:00Z"
}
~~~

Đây là một **snapshot aggregate** theo định nghĩa “order hiện đang PAID”. Nó là bản chiếu có thể thay đổi khi nguồn đổi; không phải chứng cứ tài chính bất biến.

### 13.2. Pipeline tổng hợp theo thay đổi

~~~mermaid
flowchart LR
    A["Order service"] --> B["Nguồn sự thật Order"]
    B --> C["CDC / Outbox / Change stream"]
    C --> D["Projector theo orderId"]
    D --> E["Xác định old và new contribution"]
    E --> F["Cập nhật shop/day summary"]
    F --> G["Dashboard đọc vài key"]
    D --> H["Projection progress / dedup ledger"]
~~~

Một event có thể mô tả:

~~~json
{
  "eventId": "O101-v4",
  "tenantId": "merchant-a",
  "orderId": "O101",
  "sourceVersion": 4,
  "before": {
    "shopId": "shop-12",
    "createdAt": "2026-11-14T08:10:00Z",
    "status": "PAID",
    "totalVnd": 120000
  },
  "after": {
    "shopId": "shop-12",
    "createdAt": "2026-11-14T08:10:00Z",
    "status": "SHIPPED",
    "totalVnd": 120000
  }
}
~~~

Với Q1, event này làm **giảm count 1 và giảm total 120.000** trong nhóm `(merchant-a, shop-12, 2026-11-14)`.

### 13.3. Hàm đóng góp của một Order

Định nghĩa:

\[
c(o) =
\begin{cases}
(1,\ \operatorname{totalVnd}(o)), & \text{nếu } o.status=\mathrm{PAID}\\
(0,\ 0), & \text{nếu không}
\end{cases}
\]

Với chuyển trạng thái `old -> new`:

\[
\Delta = c(new) - c(old)
\]

Theo từng khóa nhóm:

- Nếu `old` và `new` cùng một shop/ngày, cập nhật bằng chênh lệch.
- Nếu `shopId` hoặc ngày nhóm thay đổi, **trừ đóng góp khỏi nhóm cũ rồi cộng vào nhóm mới**.
- Khi xóa Order khỏi nguồn theo chính sách, phải xử lý đóng góp đang có trước khi loại bản chiếu.

Ví dụ:

| Thay đổi | Delta count nhóm cũ | Delta total nhóm cũ | Delta nhóm mới |
| --- | ---: | ---: | --- |
| CREATED → PAID, 120.000 | 0 | 0 | +1, +120.000 |
| PAID → SHIPPED, 120.000 | -1 | -120.000 | Không còn đóng góp |
| PAID 120.000 → PAID 130.000 | 0 | +10.000 (cùng nhóm) | Cùng nhóm |
| PAID chuyển shop-12 → shop-21 | -1 | -120.000 | +1, +120.000 |

Trong dòng đầu, “nhóm cũ” được hiểu **không có đóng góp PAID**; cột delta = 0 và nhóm mới nhận phần đóng góp. Trong thực tế cần tính riêng khóa nhóm của trước/sau để tránh cộng và trừ nhầm.

### 13.4. Vì sao không chỉ giữ AVG?

Nếu ngày thứ nhất có 1 đơn giá 500.000, ngày thứ hai có 9 đơn giá 100.000, trung bình đúng qua hai ngày là:

\[
\frac{1\times500000 + 9\times100000}{1+9} = 140000
\]

Trong khi lấy trung bình đơn giản của **hai trung bình ngày**:

\[
\frac{500000 + 100000}{2} = 300000
\]

là sai. Vì vậy read model cần giữ **SUM và COUNT**, sau đó tính AVG có trọng số khi gộp nhiều nhóm.

### 13.5. Cần gì để có số liệu chính xác?

Một summary được cập nhật bằng sự kiện **không tự động đúng** nếu:

- Có event trùng.
- Event đến sai thứ tự.
- Đường ghi nguồn và đường cập nhật summary không nguyên tử.
- Một event bị bỏ sót.
- Backfill ghi bản cũ đè lên trạng thái mới.
- Summary key quá nóng khiến update thất bại hoặc timeout.
- Các trạng thái/định nghĩa KPI thay đổi mà projector chưa nâng cấp.

Vì vậy thiết kế summary phải đi cùng **idempotency, version, checkpoint, replay và reconciliation**.

## 14. Vì sao at-least-once delivery có thể làm sai SUM?

Giả sử Order O101 chuyển `CREATED -> PAID` với `totalVnd = 120000`.

Projector nhận cùng event hai lần:

~~~text
Nhận lần 1:
  count += 1
  total += 120000

Nhận lại lần 2:
  count += 1
  total += 120000
~~~

Summary sai: hai đơn và 240.000, trong khi nguồn chỉ có một đơn 120.000.

### 14.1. Dedup theo ID/version

Một projector có thể lưu:

~~~text
ProjectionProgress[(tenantId, orderId)] = {
    lastAppliedVersion: 3,
    lastAppliedGroupKey: (shop-12, 2026-11-14),
    lastAppliedContribution: (count=1, total=120000)
}
~~~

Khi nhận v3 lần nữa, nó không được cộng lại. Khi nhận v4, nó tính **delta từ trạng thái đã chiếu** sang trạng thái mới nếu v4 hợp lệ.

**Nhưng** chỉ lưu `lastAppliedVersion` ở một nơi không đủ nếu việc cập nhật summary và ledger là hai thao tác không có giao dịch chung. Process có thể chết sau khi tăng tổng nhưng trước khi ghi tiến độ, rồi retry lại tăng lần nữa.

### 14.2. Transaction hoặc thuật toán có khả năng phục hồi

Một số cách giải quyết, tùy engine:

1. Dùng **transaction có điều kiện** bao phủ việc ghi tiến độ và cập nhật summary, nếu hệ quản trị và phạm vi transaction hỗ trợ.
2. Giữ **contribution per order** có version, tính lại tổng từ tập contribution được quản lý theo partition/batch phù hợp.
3. Định tuyến sự kiện theo `orderId` và áp từng entity tuần tự, kết hợp progress bền vững.
4. Duy trì summary eventual-consistent nhưng có **job reconciliation** định kỳ từ nguồn chuẩn.

Không gọi một hệ thống là “exactly once” chỉ vì consumer nhận event một lần trong test; tính đúng cần xét **toàn bộ chuỗi đọc event, ghi summary, ghi checkpoint và crash**.

### 14.3. Event đến sai thứ tự

~~~text
v3: O101 -> PAID
v4: O101 -> SHIPPED

Projector xử lý v4 trước rồi nhận lại v3.
~~~

Nếu chỉ áp `status` từng event mà không xét version, v3 có thể cộng lại đóng góp PAID sau khi v4 đã xóa. Cần một cơ chế xử lý theo version hoặc đọc trạng thái nguồn, và cần biết **phiên bản cao nhất đã áp dụng kể cả khi contribution hiện tại bằng 0**.

### 14.4. Backfill và live updates

Một bảng summary mới phải tính cho **dữ liệu đã có**, đồng thời không bỏ những cập nhật phát sinh trong lúc build:

~~~text
1. Bắt đầu thu thay đổi từ checkpoint/mốc bền vững W.
2. Backfill dữ liệu nguồn theo một snapshot hoặc quy tắc version rõ.
3. Xây contribution/summary từ dữ liệu nền.
4. Replay các thay đổi sau W có version-gating.
5. Đối soát với nguồn ở một mốc xác định.
6. Bật read model khi đạt freshness và độ đúng yêu cầu.
~~~

Nếu engine không cung cấp snapshot nhất quán gắn với CDC position, cần thiết kế **reconciliation và cách chống snapshot cũ đè lên update mới**. Không có thuật toán “quét một vòng rồi coi như xong” bảo đảm đúng trong mọi hệ đang ghi liên tục.

## 15. Một lựa chọn khác: tổng hợp từ sự kiện bất biến

Q1 cố ý đếm **trạng thái hiện tại của Order**. Đối với thống kê **dòng tiền**, cách tiếp cận đáng tin cậy thường khác.

Ví dụ một ledger thanh toán có các sự kiện:

~~~text
PAYMENT_CAPTURED:
  paymentId, orderId, capturedAt, amountVnd

PAYMENT_REFUNDED:
  refundId, paymentId, refundedAt, amountVnd
~~~

Nếu KPI là **tiền capture trong ngày**, nhóm theo `capturedAt` và cộng `amountVnd` của các sự kiện capture hợp lệ. Nếu KPI là **dòng tiền ròng**, cần xác định cách tính khoản hoàn tiền, thời điểm ghi nhận, thuế/phí và những điều chỉnh khác.

Điểm khác biệt:

| KPI | Dữ liệu nguồn | Nhóm theo thời điểm nào? |
| --- | --- | --- |
| Số đơn **đang PAID** | Trạng thái Order hiện tại | `Order.createdAt` nếu Q1 định nghĩa vậy |
| Số đơn **đã chuyển PAID trong ngày** | Lịch sử state transition được xác nhận | `paidAt` hoặc thời điểm chuyển trạng thái |
| Tổng tiền **capture trong ngày** | Payment/ledger được xác nhận | `capturedAt` |
| Tổng tiền **hoàn trong ngày** | Refund events/ledger | `refundedAt` |
| Số sản phẩm **đang active** | Catalog hiện tại | Snapshot “as of” lúc đọc |

Các câu hỏi có thể cùng dùng `SUM` và `COUNT` nhưng **không thể thay thế nguồn và khóa thời gian** của nhau.

## 16. Chỉ số gần đúng: distinct, percentile và top-k

Không phải aggregate nào cũng là phép cộng số nguyên đơn giản.

### 16.1. COUNT(DISTINCT) có thể đắt

Giả sử cần “số khách duy nhất ghé shop trong tháng”. Muốn chính xác, hệ thống phải quản lý **tập định danh khách** hoặc thuật toán thay thế bảo đảm cùng kết quả. Trên tập dữ liệu lớn, lưu mọi ID duy nhất trong một accumulator có thể tốn nhiều RAM.

Khi nghiệp vụ chấp nhận ước lượng, có thể dùng một thuật toán kiểu **HyperLogLog** hoặc sketch khác để ước lượng cardinality, tùy sản phẩm hỗ trợ. Đổi lại phải giải thích:

- Sai số kỳ vọng.
- Cách gộp các tập và tính distinct xuyên bucket.
- Có hỗ trợ xóa hoặc điều chỉnh đóng góp khi dữ liệu thay đổi không.
- Một báo cáo tài chính/kiểm toán có chấp nhận giá trị ước lượng không.

Không được dán nhãn “số khách chính xác” lên một kết quả approximate.

### 16.2. Percentile và histogram

“p95 thời gian giao hàng” không thể suy ra chỉ từ tổng thời gian và số đơn. Cần phân bố/quan sát hoặc **cấu trúc xấp xỉ** như histogram/t-digest phù hợp.

Ví dụ:

~~~text
Ngày A: 100 đơn giao trong 1 giờ.
Ngày B: 1 đơn giao trong 20 giờ.
~~~

Trung bình có thể cho một con số, nhưng p95, maximum và phân bố tail sẽ kể câu chuyện khác.

### 16.3. Top-k theo tổng nhóm

Để tìm 10 shop có `paidOrderTotalVnd` lớn nhất:

~~~text
1. Tính tổng cho tất cả nhóm shop thỏa điều kiện.
2. Sắp xếp nhóm theo total giảm dần.
3. Lấy 10 nhóm đầu.
~~~

`LIMIT 10` trên **đơn hàng đầu vào trước khi GROUP** sẽ trả số liệu sai. `LIMIT 10` sau nhóm giảm số nhóm trả về, **không bảo đảm giảm công việc cần làm để biết top-10 thật**.

Trong hệ phân tán, việc sắp xếp top-k theo tổng có thể cần hợp nhất partial aggregates từ nhiều shard, không chỉ lấy top-10 cục bộ của mỗi shard trong mọi trường hợp.

## 17. Phân trang kết quả nhóm

Với một query có 10.000 nhóm, API có thể muốn trả 100 nhóm/trang. Nhưng phân trang aggregate khác phân trang từng document theo khóa.

### 17.1. Offset pagination

Một số engine có thể:

~~~text
GROUP dữ liệu
-> SORT kết quả
-> SKIP 1000
-> LIMIT 100
~~~

Nó có thể phải **tính và sắp xếp nhiều hoặc toàn bộ nhóm** trước khi bỏ qua 1.000 nhóm đầu. Offset lớn không tự khiến phép tổng hợp rẻ hơn.

### 17.2. Cursor theo khóa nhóm

Nếu khóa nhóm có thứ tự ổn định, cursor có thể chứa:

~~~json
{
  "lastDayUtc": "2026-11-14",
  "lastShopId": "shop-21",
  "snapshotId": "aggregation-snapshot-42"
}
~~~

Khi kết quả được tính **trên snapshot hoặc summary đã cố định**, cursor theo `(dayUtc, shopId)` giúp tiếp tục ổn định. Nếu tổng được cập nhật trong lúc người dùng xem trang tiếp theo, thứ tự nhóm hoặc số liệu có thể đổi; cần công bố **tính nhất quán giữa các trang**.

Hệ tìm kiếm có thể hỗ trợ **composite aggregation** để phân trang bucket theo khóa. Với read model dạng item theo day/shop, có thể dùng paging của từng DB rồi merge theo khóa.

### 17.3. Phân trang top nhóm theo giá trị tổng

Khi sort theo `SUM(totalVnd) DESC`, giá trị nhóm có thể thay đổi liên tục. Cursor chỉ chứa `shopId` không đủ để giữ vị trí trong bảng xếp hạng. Có thể:

- Chốt snapshot/timestamp báo cáo.
- Lưu kết quả xếp hạng đã tính trước.
- Chấp nhận dữ liệu thay đổi và giải thích khả năng trùng/bỏ nhóm.

Không có một cursor “hoàn hảo” cho bảng xếp hạng thay đổi liên tục nếu không có tiêu chí nhất quán đã xác định.

## 18. Dùng Python để kiểm chứng ý nghĩa của phép nhóm

Một ví dụ thuần Python giúp xác định **kết quả đúng của Q1** trước khi đưa sang từng engine. Nó không phải benchmark hiệu năng hay thay thế driver database.

~~~python
from collections import defaultdict
from datetime import datetime, timezone

orders = [
    ("O101", "shop-12", "2026-11-14T08:10:00+00:00", "PAID", 120000),
    ("O102", "shop-12", "2026-11-14T09:10:00+00:00", "PAID", 230000),
    ("O103", "shop-12", "2026-11-14T11:00:00+00:00", "CREATED", 50000),
    ("O201", "shop-21", "2026-11-14T08:30:00+00:00", "PAID", 310000),
    ("O202", "shop-21", "2026-11-14T12:45:00+00:00", "REFUNDED", 90000),
    ("O104", "shop-12", "2026-11-15T01:00:00+00:00", "PAID", 150000),
]

from_time = datetime(2026, 11, 14, tzinfo=timezone.utc)
to_time = datetime(2026, 11, 16, tzinfo=timezone.utc)

# Accumulator nhóm: [count, total].
groups = defaultdict(lambda: [0, 0])

for order_id, shop_id, iso_time, status, total_vnd in orders:
    created_at = datetime.fromisoformat(iso_time)
    if status != "PAID":
        continue
    if not (from_time <= created_at < to_time):
        continue

    day_utc = created_at.astimezone(timezone.utc).date().isoformat()
    count_and_sum = groups[(day_utc, shop_id)]
    count_and_sum[0] += 1
    count_and_sum[1] += total_vnd

for (day, shop), (count, total) in sorted(groups.items()):
    avg = total / count if count else None
    print(day, shop, count, total, avg)
~~~

Đầu ra:

~~~text
2026-11-14 shop-12 2 350000 175000.0
2026-11-14 shop-21 1 310000 310000.0
2026-11-15 shop-12 1 150000 150000.0
~~~

Ở đây phép chia dùng `float` của Python chỉ để minh họa giá trị trung bình. Trong báo cáo tiền thực tế có phần lẻ, dùng `Decimal` hoặc quy tắc làm tròn bằng số nguyên phù hợp để tránh sai số.

### 18.1. Vì sao đây là phép kiểm chứng quan trọng?

Nếu MongoDB, DynamoDB read model và search index trả kết quả khác nhau trên cùng bộ sáu order, cần xem:

1. Có đúng cùng thời điểm snapshot không?
2. Bộ lọc `status=PAID` áp dụng trước hay sau tổng hợp?
3. Có cùng ranh giới ngày và timezone không?
4. Có document trùng hoặc event cũ còn trong index không?
5. Có bản ghi `totalVnd` bị thiếu hoặc sai kiểu không?
6. Phép tính trung bình có dùng đúng count không?

Không nên kết luận ngay “engine A cộng sai” khi các nguồn dữ liệu và ngữ nghĩa truy vấn chưa đồng nhất.

## 19. Tối ưu theo workload, không chỉ theo cú pháp

Khi thiết kế giải pháp tổng hợp NoSQL, hãy viết rõ **query contract**:

~~~yaml
queryName: paidOrdersByShopAndDay
sourceOfTruth: Orders
tenantScope: authenticatedTenant
filters:
  status: PAID
  createdAt:
    fromInclusive: "2026-11-14T00:00:00Z"
    toExclusive: "2026-11-16T00:00:00Z"
groupBy:
  - UTC_DATE(createdAt)
  - shopId
metrics:
  - paidOrderCount
  - paidOrderTotalVnd
  - avgPaidOrderVnd
consistency: "snapshot or explicitly bounded projection staleness"
requiredSort:
  - dayUtc ASC
  - shopId ASC
~~~

Đây là YAML mô tả nghiệp vụ, không phải cấu hình bắt buộc của một NoSQL cụ thể. Nếu có nhiều kiểu thống kê, nên ghi riêng:

- Đếm **đơn** hay **dòng sản phẩm**?
- Đếm trạng thái hiện hành hay **sự kiện chuyển trạng thái**?
- Nhóm theo ngày **UTC**, ngày tenant hay ngày cửa hàng?
- Dữ liệu đã đến muộn có làm thay đổi nhóm quá khứ không?
- Có gồm dữ liệu bị xóa/cancel/refund không?
- Báo cáo cần **đúng tại snapshot** hay chấp nhận projection trễ?
- Số liệu có được phép **xấp xỉ** không?

### 19.1. Kiểm tra quy mô dữ liệu đầu vào

Ví dụ một tenant:

~~~text
100 cửa hàng
5.000 đơn/ngày/cửa hàng
30 ngày

Tổng đơn cần xét nếu không thu hẹp được = 15.000.000
Số nhóm shop/ngày dự kiến tối đa = 3.000
~~~

Một truy vấn trả **3.000 nhóm** có thể cần đọc **15 triệu order**. Nếu dashboard bị tải lại mỗi phút, cần cân nhắc rõ liệu query-time aggregation trên primary DB có phù hợp hay không.

### 19.2. Ước lượng read và write amplification

Với summary:

~~~text
Mỗi Order được tạo/cập nhật:
  + ghi nguồn nghiệp vụ
  + ghi sự kiện hoặc change log
  + cập nhật một hoặc nhiều summary

Mỗi lần đọc dashboard:
  + đọc vài trăm/nghìn summary nhỏ
  - không phải quét hàng triệu order
~~~

Với nhiều chiều phân nhóm khác nhau, số summary có thể tăng rất nhanh. Nếu mọi report phát sinh một bảng mới, **write amplification, chi phí đồng bộ và sửa lỗi** có thể vượt lợi ích đọc.

### 19.3. Khi nào nên dùng OLAP thay vì nhiều read model?

Nếu sản phẩm liên tục thêm nhóm theo:

~~~text
shop, region, paymentMethod, category,
day, week, hour, customerSegment, channel, campaign...
~~~

và người dùng có thể tổ hợp tùy ý, một **hệ thống phân tích dạng columnar/OLAP** có thể phù hợp hơn so với duy trì hàng trăm bảng summary ở OLTP NoSQL.

Phải chấp nhận một pipeline dữ liệu và độ mới phù hợp, cùng cơ chế đối soát với nguồn. Không nên ép primary key-value store trả lời mọi truy vấn ad hoc trên toàn dữ liệu.

## 20. Quan sát và benchmark đúng

Một benchmark aggregation cần đo **chất lượng số liệu lẫn chi phí thực thi**.

| Nhóm | Chỉ số / câu hỏi |
| --- | --- |
| Correctness | Số nhóm, count, sum, avg có khớp dữ liệu chuẩn? |
| Snapshot | Các số liệu có được tính trên cùng trạng thái logic? |
| Latency | p50/p95/p99 cho query theo tenant nhỏ/lớn |
| Input work | Số item/document/row/index key đã xét |
| Resource | CPU, RAM, disk spill, I/O, network cross-shard |
| Cardinality | Số nhóm và số distinct key |
| Throughput | Bao nhiêu query/s tại concurrency dự kiến |
| Projection freshness | Event tới summary trễ bao lâu? |
| Write amplification | Một Order mutation cập nhật bao nhiêu index/summary |
| Reconciliation | Tỷ lệ thiếu/thừa/double-count |
| Recovery | Thời gian rebuild/backfill sau lỗi |
| Cost | Dung lượng dữ liệu phụ, backup, compaction, vận hành |

### 20.1. Thử nhiều dạng phân bố dữ liệu

Không chỉ thử một tenant có mỗi shop cùng số đơn. Cần ít nhất:

- Tenant rất lớn và tenant rất nhỏ.
- Một shop chiếm 60–90% số đơn (*skew*).
- Nhóm có cardinality cao.
- Nhiều order cập nhật status liên tục.
- Event duplicate và đến muộn.
- Một số trường bị thiếu hoặc bất thường.
- Query theo một ngày, 30 ngày và nhiều tháng.
- Query cùng lúc từ nhiều dashboard.

Tính đúng của tổng hợp thường sai ở **trường hợp biên** như order chuyển trạng thái giữa hai lần đọc, không phải trong dữ liệu tĩnh sáu dòng.

### 20.2. Cần đo đúng chỗ phát sinh công việc

Ví dụ:

~~~text
End-to-end latency =
  API/auth + network + database query
  + merge/aggregation + serialization + cache
~~~

Độ trễ `Query` của DynamoDB hay một stage MongoDB riêng không tự đại diện cho thời gian trả toàn bộ dashboard. Nếu cần một KPI nhóm sau 12 network round trips để đọc 12 partition, hãy đo **tổng đường đi**.

### 20.3. Kiểm chứng kế hoạch thực thi

- MongoDB: sử dụng `explain`/pipeline metrics để biết index được dùng và tài nguyên grouping.
- Cassandra: quan sát tracing, số partition, rows/tombstones đọc và query latency; không coi `COUNT` là O(1).
- DynamoDB: quan sát consumed capacity, phân trang, số item được đọc/được trả, GSI và hot key.
- Redis: xem lệnh có chạy trên một key hay phải duyệt nhiều key, chi phí script và contention.
- Neo4j: dùng `EXPLAIN`/`PROFILE` để thấy cardinality khi expand quan hệ.
- Search: quan sát query profile, shard load, bucket count, merge cost, indexing lag.

Những công cụ cụ thể khác nhau theo phiên bản và cấu hình; mục tiêu là **xác minh bằng số liệu**, không chỉ nhìn câu lệnh.

## 21. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách tiếp cận đúng hơn |
| --- | --- | --- |
| Coi mọi NoSQL có SQL `GROUP BY` như nhau | Khả năng nhóm khác nhau giữa MongoDB, CQL, DynamoDB, Redis | Chọn cơ chế đúng theo engine |
| Nghĩ `COUNT(*)` trên Cassandra là counter sẵn | Có thể phải đọc nhiều hàng/tombstone | Đo chi phí hoặc duy trì summary |
| Dùng `DynamoDB Query Select=COUNT` và bỏ qua phân trang | Chỉ đếm phạm vi request và vẫn tốn tài nguyên đọc | Duyệt trang đúng hoặc pre-aggregate |
| `LIMIT 20` trước `GROUP` để làm dashboard nhanh | Kết quả tổng có thể thiếu dữ liệu | Lọc đúng rồi group; limit kết quả nhóm |
| Dùng `AVG` của các AVG ngày để gộp tháng | Bỏ qua số đơn mỗi ngày | Cộng SUM và COUNT rồi chia |
| Đếm order sau khi join 3 line bằng `COUNT(*)` | Nhân số hàng theo line/path | Đếm entity theo ID hoặc DISTINCT |
| Gọi trạng thái PAID là doanh thu đã ghi nhận | State hiện tại khác payment ledger | Định nghĩa KPI và nguồn nghiệp vụ |
| Trộn UTC day và local day | Dồn đơn vào bucket sai | Quy định timezone và ranh giới rõ |
| Dùng số thực thiếu kiểm soát cho tiền | Có thể sai số khi cộng/làm tròn | Decimal/fixed-point hoặc số nguyên |
| Bật GSI rồi nghĩ SUM tự có | GSI là access path, không phải summary | Aggregate ở ứng dụng hoặc giữ item summary |
| Tăng counter khi event được retry | Double-count | Idempotency/version và atomic progress |
| Projector chỉ cộng khi PAID, không trừ khi SHIPPED | Summary trạng thái hiện tại bị thừa | Tính delta từ before/after |
| Bỏ qua event đến muộn | Số liệu ngày cũ có thể sai | Policy event time, version và reconciliation |
| Chọn `terms` size nhỏ nhưng gọi là “mọi nhóm” | Có thể chỉ lấy bucket đứng đầu từ shard | Dùng composite/pagination khi cần đầy đủ |
| Gọi cardinality xấp xỉ là số tuyệt đối | Có sai số ước lượng | Công bố sai số và chọn cách đếm phù hợp |
| Tin cache/search là nguồn chuẩn tài chính | Projection có lag hoặc thiếu/đúp record | Dùng nguồn có thẩm quyền và đối soát |
| Dựa vào một benchmark sáu document | Không đại diện dữ liệu lớn/skew/tải đồng thời | Test workload và dữ liệu thật |

## 22. Bài tập thực hành

### Bài 1 — Tính tay Q1

Từ sáu Order ở mục 2:

1. Liệt kê những Order đi qua bộ lọc.
2. Tính `paidOrderCount`, `paidOrderTotalVnd` và trung bình cho `shop-12` ngày 14/11.
3. Giải thích vì sao `O103` và `O202` không được tính.
4. Nếu `O101` chuyển sang `SHIPPED`, giá trị Q1 thay đổi thế nào?

### Bài 2 — Viết pipeline MongoDB

Từ Q1:

1. Viết `$match` cho tenant, trạng thái và khoảng ngày.
2. `$group` theo `shopId` và ngày UTC.
3. Tính `count`, `sum`, `avg`.
4. Thêm điều kiện sau nhóm `paidOrderCount >= 2`.
5. Chuyển báo cáo sang ngày `Asia/Ho_Chi_Minh` và giải thích phải đổi ranh giới bộ lọc như thế nào.

### Bài 3 — Thiết kế CQL theo truy vấn

Nền tảng Cassandra cần Q1 cho một shop mỗi ngày.

- Đề xuất partition key/clustering key.
- Nêu điều gì xảy ra khi order chuyển `PAID -> SHIPPED`.
- Vì sao `COUNT(*)` trên partition không tự O(1)?
- Khi nào cần bảng summary và pipeline event?
- Phân tích chi phí tombstone khi trạng thái đổi nhiều.

### Bài 4 — DynamoDB và phân trang

Một partition của DynamoDB chứa 50.000 Order; API cần đếm các item PAID. Một yêu cầu `Query` chỉ đọc một phần dữ liệu.

1. Giải thích vai trò `LastEvaluatedKey`.
2. Vì sao `FilterExpression` không tương đương index riêng theo status?
3. So sánh query hết các trang với summary item.
4. Thiết kế cách tránh tăng đếm hai lần khi consumer nhận cùng event.

### Bài 5 — Redis counter và retry

Service dùng:

~~~text
HINCRBY summary:shop-12:2026-11-14 count 1
HINCRBY summary:shop-12:2026-11-14 total 120000
~~~

Giả sử worker chết giữa hai lệnh, rồi retry cả hai.

- Chỉ ra ít nhất hai kiểu sai số có thể xảy ra.
- Đề xuất cập nhật cùng key atomically bằng script/transaction.
- Giải thích vì sao cập nhật atomically trong Redis vẫn chưa tự đồng bộ với source DB.
- Mô tả ledger và reconciliation cần thiết.

### Bài 6 — Graph DISTINCT

Một Order có 4 relationship tới OrderItem và được kết hợp với Customer. Hãy viết truy vấn Cypher đếm **số đơn duy nhất** theo Customer, tránh đếm thành 4 đơn. Nếu cùng Customer có nhiều đường nối tới Order do mô hình dữ liệu bất thường, cần sửa gì ở query hoặc ràng buộc schema?

### Bài 7 — Search aggregation

Một index có 20.000 shop, nhưng `terms.size = 100`.

- Kết quả có biểu diễn tất cả shop không?
- Sự khác nhau giữa top bucket và phân trang đầy đủ mọi bucket?
- Khi nào `composite` aggregation phù hợp?
- Vì sao cần theo dõi indexing lag nếu số liệu xuất hiện trên dashboard?

### Bài 8 — Tính summary theo delta

Order O101 có các phiên bản:

~~~text
v1: CREATED, totalVnd=120000
v2: PAID, totalVnd=120000
v3: PAID, totalVnd=130000
v4: SHIPPED, totalVnd=130000
~~~

Hãy viết delta `(count, total)` cho Q1 ở mỗi lần chuyển, rồi mô tả:

1. Kết quả cuối cùng của contribution cho O101.
2. Cách xử lý v2 được nhận lại sau v4.
3. Cách tránh mất/cộng trùng delta khi worker chết giữa summary và checkpoint.

### Bài 9 — KPI doanh thu khác KPI trạng thái

Một Order đã capture 1.000.000 VND ngày 14/11, chuyển SHIPPED ngày 15/11 và hoàn 300.000 VND ngày 16/11.

Hãy xác định số liệu nào có thể được tính từ:

- Snapshot `Order.status`.
- Lịch sử `PAYMENT_CAPTURED`.
- Lịch sử `PAYMENT_REFUNDED`.

Đề xuất tên KPI rõ để tránh gọi nhầm `SUM(totalVnd) WHERE status=PAID` thành doanh thu ròng.

### Bài 10 — Chọn kiến trúc theo quy mô

Tình huống:

~~~text
200 cửa hàng
10.000 đơn/ngày/cửa hàng
90 ngày dữ liệu
Dashboard được mở mỗi 5 giây bởi nhiều người dùng
Cho phép summary trễ tối đa 10 giây
~~~

Hãy:

1. Ước lượng số Order trong 90 ngày.
2. Tính số nhóm shop/ngày tối đa.
3. So sánh đọc toàn bộ Order mỗi lần với summary được cập nhật trước.
4. Chọn cơ chế ingest/replay và idempotency.
5. Đề xuất metric kiểm chứng độ mới và tính đúng.

## 23. Quy trình ra quyết định khi gặp một yêu cầu tổng hợp mới

~~~mermaid
flowchart TD
    A["Yêu cầu aggregate/group mới"] --> B["Viết định nghĩa KPI + source + timezone"]
    B --> C["Xác định filter, group key, metric, độ mới"]
    C --> D{"Engine biểu đạt trực tiếp phù hợp?"}
    D -->|Có| E["Thử query và EXPLAIN/PROFILE"]
    D -->|Không| F["Chọn materialized summary / OLAP"]
    E --> G{"Đạt SLA tại tải thật?"}
    G -->|Có| H["Dùng query-time aggregate"]
    G -->|Không| F
    F --> I["Thiết kế update, retry, version, backfill"]
    I --> J["Đối soát số liệu và rollout"]
    H --> K["Theo dõi correctness + latency"]
    J --> K
~~~

Một quy trình thực tế:

1. **Xác định đúng KPI:** “đếm order đang PAID” hay “tổng tiền capture”, “ngày UTC” hay “ngày shop”.
2. **Xác định tập dữ liệu hợp lệ:** tenant, quyền truy cập, trạng thái, thời gian và snapshot.
3. **Chọn khóa nhóm và loại aggregate:** count, sum, average, distinct, percentile, top-k.
4. **Kiểm tra khả năng engine:** nhóm trực tiếp, khóa index, yêu cầu nhiều partition/shard và giới hạn API.
5. **Đo trực tiếp trên dữ liệu đại diện:** số đầu vào được đọc, số nhóm, p95/p99, CPU, RAM và I/O.
6. **Chọn precompute khi cần:** biết nguồn chuẩn, version, idempotency, thay đổi trạng thái và khả năng rebuild.
7. **Đối soát và kiểm tra độ mới:** số liệu có đúng không, được cập nhật trễ bao lâu, replay có gây đúp không.
8. **Lưu lại định nghĩa:** tên metric, filter, thời gian, precision, quyền, ngoại lệ và tính xấp xỉ nếu có.

## Kết luận

**Truy vấn tổng hợp trong NoSQL không có một ngôn ngữ hoặc mô hình thực thi chung.** MongoDB cho phép pipeline `$group` linh hoạt; Cassandra có aggregate và nhóm bị ràng buộc bởi primary key; DynamoDB tập trung vào Get/Query theo key và thường cần summary khi muốn nhóm; Redis mạnh về counter/cấu trúc đã mô hình hóa; Neo4j tổng hợp kết quả khớp quan hệ; hệ tìm kiếm cung cấp bucket aggregation nhưng phải xét sharding và độ chính xác.

Những nguyên tắc cần giữ:

- **Đúng nghiệp vụ trước, đúng cú pháp sau:** xác định đơn vị đếm, nguồn dữ liệu, trạng thái, thời điểm và timezone trước khi viết `COUNT/SUM/GROUP`.
- **Đầu ra nhỏ không có nghĩa chi phí nhỏ:** một nhóm có thể được tính từ hàng triệu bản ghi.
- **Index giúp thu hẹp tập đọc, không tự tạo tổng:** Query/GSI và COUNT nhiều khi vẫn phải đọc hoặc tổng hợp các item.
- **Pre-aggregation đổi chi phí đọc lấy chi phí ghi và đồng bộ:** cần tính delta theo trạng thái, xử lý event lặp/sai thứ tự, backfill và reconciliation.
- **Không lấy AVG của AVG nếu không có trọng số:** giữ `sum` và `count` để gộp đúng.
- **Biết kết quả nào là xấp xỉ:** distinct, top bucket và thống kê phân tán có thể có sai số theo khả năng engine.
- **Đo và kiểm chứng từ dữ liệu thật:** query plan, số hàng xét, QPS, p95/p99, projection lag và sự phù hợp với nguồn chuẩn.

Một giải pháp tổng hợp NoSQL tốt là giải pháp **diễn đạt đúng câu hỏi nghiệp vụ, chọn đường truy cập phù hợp với từng hệ và duy trì số liệu đúng trong mức độ mới và chi phí mà sản phẩm có thể cam kết**.
