# Ghi lại đánh đổi giữa chi phí đọc, ghi, lưu trữ và độ phức tạp

## 1. Vì sao phải ghi lại đánh đổi khi thiết kế NoSQL?

Thiết kế cơ sở dữ liệu NoSQL thường bắt đầu từ **mẫu truy vấn (access pattern)**: ai đọc dữ liệu, lọc theo khóa nào, lấy bao nhiêu bản ghi, sắp xếp ra sao và cập nhật với tần suất nào. Từ các truy vấn đó, đội ngũ quyết định nhúng hay tham chiếu dữ liệu, tạo index nào, dùng một hay nhiều bảng/collection, phân vùng theo khóa gì và có nên duy trì bản sao phục vụ đọc hay không.

Mỗi lựa chọn thường cải thiện một mặt nhưng làm tăng chi phí ở mặt khác:

- **Đọc nhanh hơn** có thể đòi thêm index, bản sao dữ liệu hoặc bảng chuyên phục vụ truy vấn.
- **Ghi đơn giản hơn** có thể làm truy vấn đọc phải truy cập nhiều nguồn hoặc quét nhiều dữ liệu.
- **Lưu trữ ít hơn** có thể khiến hệ thống cần join/traversal hoặc tính toán khi đọc.
- **Một API đọc có vẻ đơn giản** có thể đẩy gánh nặng sang đồng bộ dữ liệu, xử lý lỗi hoặc vận hành nhiều pipeline.
- **Phân tán nhiều partition để giảm điểm nóng** có thể làm truy vấn lấy danh sách có thứ tự phải đọc nhiều partition rồi hợp nhất.

Nếu chỉ ghi câu “chọn denormalization để tăng hiệu năng”, người đọc sau này sẽ không biết **truy vấn nào được tăng tốc, tăng bao nhiêu, chi phí ghi/lưu trữ đổi thế nào, rủi ro nhất quán là gì và khi nào phải đổi lại**.

Vì vậy, một quyết định thiết kế tốt cần **ghi lại phương án, giả định, bằng chứng, đánh đổi, điều kiện chấp nhận và tiêu chí xem xét lại**. Bài học tập trung vào kỹ năng lập hồ sơ những đánh đổi đó một cách đo được và có thể sử dụng khi hệ thống phát triển.

### Mục tiêu học tập

Sau bài học, người đọc có thể:

1. Phân loại chi phí **đọc, ghi, lưu trữ và độ phức tạp** trong thiết kế NoSQL.
2. So sánh những phương án như **embedding, referencing, index bổ sung và materialized read model** dựa trên cùng một workload.
3. Lập bảng đánh đổi có số liệu, giả định và mức độ chắc chắn của bằng chứng.
4. Viết một **Architecture Decision Record (ADR)** có thể kiểm chứng và cập nhật.
5. Xác định **tín hiệu phải xem xét lại quyết định** khi lưu lượng, mẫu truy vấn hoặc yêu cầu nhất quán thay đổi.

---

## 2. Bốn loại chi phí cần ghi lại

### 2.1. Chi phí đọc (read cost)

Chi phí đọc không chỉ là thời gian chạy một câu truy vấn. Nó bao gồm:

- Số request tới DBMS và số vòng trao đổi qua mạng.
- Số document, row, partition, index entry hoặc byte phải đọc.
- CPU để lọc, giải mã, tổng hợp hoặc sắp xếp.
- Bộ nhớ dành cho sort, aggregation và các dữ liệu trung gian.
- I/O đĩa và tỷ lệ cache hit/miss.
- Số shard/replica tham gia; mức fan-out của truy vấn.
- Độ trễ **p50, p95, p99**, tỷ lệ timeout và mức tải khi cao điểm.
- Số byte gửi trả ứng dụng sau projection hoặc phân trang.

Ví dụ một màn hình cần đơn hàng và 20 dòng hàng: nếu dữ liệu được nhúng trong một document hợp lý, ứng dụng có thể tải một document thay vì nhiều request. Nhưng nếu document chứa mảng lịch sử cực lớn, một lần đọc có thể truyền nhiều dữ liệu thừa.

**Ghi lại:** “Q1 đọc một document ở p95 = 18 ms, trả 6 KB” hữu ích hơn “embedding đọc rất nhanh”.

### 2.2. Chi phí ghi (write cost)

Một thao tác ghi nghiệp vụ có thể tạo nhiều thao tác vật lý hoặc logic:

- Ghi document/bảng nguồn.
- Cập nhật index và secondary index.
- Duy trì bản sao cho các bảng đọc theo truy vấn khác nhau.
- Replication đến các bản sao theo chính sách của DBMS.
- Cập nhật cache hoặc gửi sự kiện đồng bộ.
- Ghi audit/outbox hoặc retry những thao tác thất bại.
- Xử lý transaction, khóa, xung đột và tính lặp an toàn (*idempotency*).

Ví dụ cập nhật giá của một sản phẩm. Trong mô hình tham chiếu, hệ thống chỉ cần sửa tài liệu sản phẩm hiện tại. Trong mô hình sao chép tên/giá hiện tại vào hàng triệu tài liệu khác, một cập nhật có thể kéo theo rất nhiều bản ghi phải đổi.

**Write amplification (khuếch đại ghi)** là hiện tượng một thay đổi logic tạo thêm các công việc ghi. Cần ghi rõ loại amplification đang nói đến: số bản ghi ứng dụng cập nhật, số index phải duy trì hay lượng I/O nội bộ do engine và compaction tạo ra. Các đại lượng này không tương đương.

### 2.3. Chi phí lưu trữ (storage cost)

Không thể chỉ tính tổng byte JSON hoặc số dòng nghiệp vụ. Chi phí lưu trữ có thể bao gồm:

- Dữ liệu chính đã mã hóa/lưu trữ.
- Các index và metadata.
- Bản sao dữ liệu hoặc read model được denormalize.
- Replication factor và bản sao liên vùng.
- Tombstone, version cũ, write-ahead log hoặc cấu trúc engine cần để vận hành.
- Backup, snapshot và chính sách giữ bản sao lịch sử.
- Chi phí lưu trữ nóng/lạnh và chi phí đọc/ghi phát sinh theo dịch vụ cloud.
- Dung lượng phát sinh tạm thời khi compaction, migration hay rebuild index.

Một dữ liệu gốc 100 GB với replication factor 3 **không tự có nghĩa hóa đơn đúng bằng 300 GB**: còn index, compression, snapshot, metadata, chính sách phân vùng, backup và chi phí dịch vụ. Nhưng phép nhân sơ bộ giúp nhận biết chi phí có thể tăng theo số bản sao.

### 2.4. Chi phí độ phức tạp (complexity cost)

Độ phức tạp thường khó quy đổi ngay thành tiền nhưng ảnh hưởng đến thời gian triển khai và xác suất lỗi.

Có thể chia thành bốn nhóm:

| Nhóm | Biểu hiện | Câu hỏi nên ghi lại |
|---|---|---|
| **Ứng dụng** | Nhiều đường đọc, fan-out, merge kết quả, cache invalidation | Cần bao nhiêu bước để trả một API? |
| **Nhất quán** | Nhiều bản sao phải đồng bộ, xử lý dữ liệu trễ, duplicate event | Nguồn sự thật ở đâu? Được phép lệch bao lâu? |
| **Vận hành** | Theo dõi pipeline, rebuild view, repair, backup và migration | Khi một bước thất bại, phát hiện và khôi phục thế nào? |
| **Con người/quy trình** | Nhiều công nghệ, kiến thức chuyên biệt, khó review và onboarding | Đội ngũ có vận hành an toàn trong ca trực sự cố không? |

Không nên gộp độ phức tạp thành một điểm “2/5” mà không giải thích. Có thể dùng điểm để trình bày nhanh, nhưng phải kèm **nguyên nhân cụ thể**, chẳng hạn “cần retry và đối soát hai collection”, “phải merge 16 bucket”, hay “phải xây quy trình backfill khi đổi schema”.

---

## 3. Đánh đổi là quan hệ nhiều chiều, không phải danh sách tốt/xấu

Bốn loại chi phí thường liên quan với nhau:

~~~mermaid
flowchart TD
    Q["Mẫu truy vấn và SLO"] --> D["Lựa chọn mô hình dữ liệu"]
    D --> R["Chi phí đọc"]
    D --> W["Chi phí ghi"]
    D --> S["Chi phí lưu trữ"]
    D --> C["Độ phức tạp"]
    R --> M["Đo đạc và quan sát"]
    W --> M
    S --> M
    C --> M
    M --> A["Ghi quyết định, điều kiện xem xét lại"]
~~~

Ví dụ:

- **Nhúng** địa chỉ giao hàng vào đơn có thể giảm chi phí đọc chi tiết đơn, không cần join, đồng thời làm document lớn hơn một chút.
- **Tạo index** cho bộ lọc trạng thái và thời gian có thể giảm quét lúc đọc, nhưng làm mỗi ghi và cập nhật trạng thái phải duy trì thêm index.
- **Bảng đọc riêng** giúp API đọc rất nhanh theo một truy vấn cụ thể, nhưng tạo lưu trữ lặp và quy trình đồng bộ.
- **Hash bucket** phân tán tải ghi của một tenant lớn nhưng khiến truy vấn dòng thời gian phải đọc nhiều bucket rồi hợp nhất.
- **Cache** giảm tải đọc DBMS ở những khóa thường dùng, nhưng thêm vấn đề invalidation, TTL, stale reads và khi cache bị lỗi.

**Không có phương án tối ưu tuyệt đối trên mọi trục.** Một lựa chọn hợp lý là lựa chọn đáp ứng các ràng buộc bắt buộc với chi phí tổng thể chấp nhận được theo workload dự kiến.

### 3.1. Phân biệt yêu cầu bắt buộc và điều có thể tối ưu

Ví dụ:

| Loại | Yêu cầu | Cách đánh giá |
|---|---|---|
| **Bắt buộc** | Một khách không được đọc đơn của tenant khác | Kiểm tra authorization và cách đặt phạm vi tenant |
| **Bắt buộc** | Không tạo hai đơn cho cùng một yêu cầu idempotent | Kiểm tra khóa idempotency và ghi nguyên tử/điều kiện |
| **Bắt buộc** | Không sai tổng tiền đã chốt | Ràng buộc nghiệp vụ và transaction trong phạm vi cần thiết |
| **Mục tiêu** | p95 API danh sách đơn dưới 120 ms ở tải thiết kế | Load test có phân bố dữ liệu đại diện |
| **Mục tiêu** | Tăng dung lượng index không quá 30% so với hiện tại | Đo index size tại quy mô dự kiến |
| **Mong muốn** | Ít pipeline đồng bộ để dễ vận hành | Ước tính số thành phần và các quy trình phục hồi |

Một phương án đọc nhanh nhất nhưng không thể bảo đảm quyền dữ liệu hoặc tính đúng đắn của nghiệp vụ **không thể được chọn** chỉ vì điểm hiệu năng cao.

---

## 4. Bắt đầu từ bảng mẫu truy vấn và thay đổi dữ liệu

Trước khi so sánh kiến trúc, cần biết hệ thống phải làm gì. Dùng một hệ bán hàng trực tuyến làm ví dụ.

### 4.1. Mẫu truy vấn đọc

| ID | Mẫu truy vấn | Điều kiện và thứ tự | Tần suất giả định | Yêu cầu |
|---|---|---|---:|---|
| Q1 | Xem chi tiết đơn hàng | `orderId = ?` | 40% lượt đọc | p95 dưới 100 ms |
| Q2 | Danh sách 20 đơn mới nhất của khách | `customerId`, `createdAt DESC`, tie-breaker `orderId` | 35% | p95 dưới 120 ms |
| Q3 | Xem thông tin sản phẩm hiện tại | `productId = ?` | 20% | p95 dưới 80 ms |
| Q4 | Báo cáo tổng doanh thu theo tháng | `tenantId, month`, tổng hợp | 5% | Có thể chạy bất đồng bộ |

Các tỷ lệ và thời gian là **giả định phục vụ thực hành**, không phải số liệu chuẩn của sản phẩm hay DBMS bất kỳ.

### 4.2. Mẫu thay đổi dữ liệu

| ID | Thao tác ghi | Tác động | Đặc tính |
|---|---|---|---|
| W1 | Tạo đơn | Ghi đơn, dòng hàng và thông tin giao tại lúc đặt | Không được mất dữ liệu; cần idempotency |
| W2 | Đổi trạng thái đơn | Đổi `status`, `updatedAt`, có thể phát sự kiện | Có tranh chấp khi nhiều tác nhân cập nhật |
| W3 | Đổi giá sản phẩm danh mục | Chỉ ảnh hưởng giá **hiện tại** | Không được sửa giá đã chốt của đơn cũ |
| W4 | Cập nhật địa chỉ mặc định | Cập nhật hồ sơ khách | Không được thay đổi snapshot đơn cũ |
| W5 | Tạo báo cáo tháng | Cập nhật read model/tổng hợp | Cho phép trễ có kiểm soát |

Nếu không ghi phần **ghi**, đội ngũ dễ chọn cấu trúc giúp Q1, Q2 nhanh nhưng làm W2 hoặc W3 quá đắt, dẫn tới nợ kỹ thuật và rủi ro nhất quán.

### 4.3. Quy mô và tăng trưởng cũng là một phần hợp đồng

Nên ghi:

~~~text
Giả định thực nghiệm:
- 1 triệu khách hàng đang hoạt động
- 20 triệu đơn đang được lưu
- 6 dòng hàng/đơn trung bình
- 50 dòng hàng/đơn ở nhóm hiếm có kích thước lớn
- 80% request đọc, 20% request ghi
- 5% khách hàng tạo ra 50% lượt truy vấn
- Đơn hàng và lịch sử cần lưu nhiều năm
- Đọc danh sách trả tối đa 20 đơn mỗi trang
~~~

Các con số được chọn để dễ so sánh. Trong hệ thật phải lấy từ metric, dự báo sản phẩm và ranh giới kinh doanh, đồng thời ghi nguồn và ngày đo. Quan trọng hơn con số trung bình là **phân bố lệch**, độ tăng trưởng và tải đỉnh.

---

## 5. Ba phương án lưu đơn hàng để so sánh

### 5.1. Phương án A: tham chiếu (reference) giữa đơn và dòng hàng

~~~text
orders
  orderId
  customerId
  status
  createdAt
  totalVnd

order_items
  itemId
  orderId
  productId
  productNameAtPurchase
  priceAtPurchase
  quantity
~~~

Ví dụ document:

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-42",
  "status": "PAID",
  "createdAt": "2026-11-14T08:15:27Z",
  "totalVnd": 1050000
}
~~~

~~~json
{
  "_id": "item-1",
  "orderId": "order-1001",
  "productId": "product-8",
  "productNameAtPurchase": "Chuột không dây",
  "priceAtPurchase": 450000,
  "quantity": 2
}
~~~

**Đọc Q1:** cần lấy đơn và các item liên quan, thông qua nhiều request hoặc aggregation/join nếu engine hỗ trợ.

**Ghi W1:** ghi đơn và dòng hàng ở những document riêng; nếu yêu cầu cùng thành công hoặc cùng thất bại, phải xét transaction hoặc cơ chế phối hợp tương ứng.

**Lưu trữ:** giảm một số rủi ro document tăng lớn, phù hợp khi số dòng rất lớn hoặc truy cập độc lập; có thêm index trên `orderId` ở tập item.

**Độ phức tạp:** cần bảo đảm không có “đơn thiếu dòng” hay “dòng không có đơn” trong trường hợp lỗi giữa các thao tác, đồng thời giải quyết phân trang nếu số dòng hàng lớn.

### 5.2. Phương án B: nhúng dòng hàng vào đơn

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-42",
  "status": "PAID",
  "createdAt": "2026-11-14T08:15:27Z",
  "shippingAddress": {
    "city": "Da Nang",
    "street": "12 Nguyen Van Linh"
  },
  "items": [
    {
      "lineId": "line-1",
      "productId": "product-8",
      "productNameAtPurchase": "Chuột không dây",
      "priceAtPurchase": 450000,
      "quantity": 2
    },
    {
      "lineId": "line-2",
      "productId": "product-21",
      "productNameAtPurchase": "Bàn di chuột",
      "priceAtPurchase": 150000,
      "quantity": 1
    }
  ],
  "totalVnd": 1050000
}
~~~

**Đọc Q1:** thường có thể lấy toàn bộ thông tin chi tiết trong một document.

**Ghi W1:** có thể ghi đơn và dòng hàng cùng một document, tận dụng tính nguyên tử cấp document nếu DBMS bảo đảm. Giao dịch thanh toán hoặc giữ tồn kho ở tài liệu/dịch vụ khác **không tự trở thành nguyên tử**.

**Lưu trữ:** dữ liệu item nằm trong document cha; có thêm một ít overhead của cấu trúc lồng nhau. Với tên/giá sản phẩm là snapshot, trùng lặp này là **có chủ ý** để giữ lịch sử giao dịch, không đồng bộ lại từ catalog sống.

**Độ phức tạp:** ứng dụng cần đặt giới hạn số item, kiểm soát kích thước document và xử lý cập nhật đồng thời trên một đơn. Nếu item có thể tăng không giới hạn, embedding toàn bộ dễ gây vấn đề.

Lưu ý: MongoDB có giới hạn 16 MiB cho một BSON document. Các document DBMS khác có giới hạn riêng. Không nên chọn ngưỡng kích thước một cách tùy tiện mà không kiểm tra sản phẩm và workload.

### 5.3. Phương án C: tài liệu nguồn + read model chuyên dụng

Phương án C giữ dữ liệu nghiệp vụ chính theo cách phù hợp cho ghi, đồng thời xây **bảng/collection đọc riêng** cho Q2 hoặc báo cáo:

~~~text
orders                (nguồn dữ liệu nghiệp vụ)
  orderId, customerId, status, ...

orders_by_customer    (read model)
  customerId, createdAt, orderId, status, totalVnd

monthly_sales         (read model tổng hợp)
  tenantId, month, totalVnd, orderCount
~~~

Ví dụ:

~~~json
{
  "_id": "customer-42#20261114T081527Z#order-1001",
  "customerId": "customer-42",
  "orderId": "order-1001",
  "createdAt": "2026-11-14T08:15:27Z",
  "status": "PAID",
  "totalVnd": 1050000
}
~~~

**Đọc Q2:** chỉ cần đọc dải phù hợp với khách hàng và thời gian trong read model nếu index/khóa được thiết kế đúng.

**Ghi W1/W2:** mỗi thay đổi có thể phải cập nhật cả nguồn và read model, đồng bộ trực tiếp hoặc qua sự kiện bất đồng bộ.

**Lưu trữ:** có bản sao cho các trường được chọn và index của read model.

**Độ phức tạp:** phải định nghĩa nơi nào là **source of truth**, cách xử lý dữ liệu trễ, lặp sự kiện, mất sự kiện, backfill/rebuild, chuyển phiên bản schema, cảnh báo khi read model lệch và quy trình phục hồi.

Read model không phải lúc nào cũng cần. Nếu Q2 đã được index trên tập dữ liệu nguồn đáp ứng SLO, thêm một collection đồng bộ là tăng chi phí mà chưa chắc có lợi.

---

## 6. Ma trận đánh đổi cần ghi, không chỉ chọn phương án thắng

Một ma trận đánh đổi nên sử dụng **cùng workload và cùng ràng buộc** cho mọi phương án.

| Tiêu chí | A — Tham chiếu | B — Nhúng | C — Read model riêng |
|---|---|---|---|
| Q1: chi tiết đơn | Có thể cần đọc/ghép đơn + item | Thường một lần đọc document | Phụ thuộc thiết kế nguồn; read model không nhất thiết giúp Q1 |
| Q2: danh sách đơn | Cần index/bảng theo khách và thời gian | Cần index, có thể projection trường | Có thể tối ưu khóa/index riêng cho Q2 |
| W1: tạo đơn | Nhiều document; phải phối hợp khi cần nguyên tử | Có thể một document cho đơn + item | Ghi nguồn và cập nhật thêm bản chiếu |
| W2: cập nhật trạng thái | Ghi đơn | Ghi đơn | Ghi nguồn và đồng bộ lại bản chiếu |
| Kích thước mỗi document | Đơn và dòng hàng tách | Đơn lớn dần theo số item | Phụ thuộc nguồn; read model riêng thường nhỏ |
| Dung lượng tổng | Chỉ mục liên kết giữa collection | Có thể thấp hơn nếu không tạo nhiều view, nhưng item vẫn được lưu | Tăng do nhân bản trường và index |
| Tính nhất quán đơn + item | Cần xét transaction qua document | Có thể theo tính nguyên tử document | Tính nhất quán của nguồn; bản chiếu có thể trễ |
| Khi sản phẩm đổi giá | Giữ snapshot lịch sử, không cập nhật đơn cũ | Giữ snapshot lịch sử, không cập nhật đơn cũ | Không đồng bộ lại snapshot lịch sử |
| Complexity vận hành | Join/phối hợp ghi, index | Giới hạn document, concurrency | Pipeline, retry, backfill, quan sát độ trễ |
| Điểm yếu đáng chú ý | Nhiều thao tác cho Q1 | Document lớn khi item tăng quá mức | Dữ liệu trễ và nhiều nơi có cùng thông tin |

**Không thể đánh giá C là “tốt nhất” chỉ vì Q2 nhanh hơn.** Nếu Q2 ít được dùng hoặc yêu cầu dữ liệu mới tuyệt đối, chi phí thêm pipeline và đồng bộ có thể lớn hơn lợi ích đọc.

### 6.1. Cần đặt bảng theo workload thay vì một cột “hiệu năng”

Một phương án có thể:

- Giảm p95 của Q1 từ 100 ms xuống 40 ms.
- Tăng p99 của W2 từ 25 ms lên 70 ms.
- Tăng 45% dung lượng lưu trữ vì các index/read model.
- Đòi thêm một pipeline xử lý sự kiện với độ trễ đồng bộ p99 là 2 giây.

Đây là ví dụ **số liệu giả định**. Nếu không ghi số liệu đo và ngưỡng chấp nhận, đánh đổi sẽ chỉ là cảm nhận.

### 6.2. Tách kết quả đo khỏi kỳ vọng

Trong tài liệu quyết định, mỗi kết luận nên kèm mức bằng chứng:

| Phát biểu | Loại bằng chứng | Mức tin cậy |
|---|---|---|
| “Q1 chỉ phải đọc một document” | Suy ra từ mô hình nhúng; cần xác thực code | Khá cao về số request logic |
| “Q1 p95 sẽ dưới 50 ms” | Dự đoán chưa benchmark | Thấp |
| “Index chiếm thêm 18 GB ở 20 triệu đơn” | Đo môi trường thử 5 triệu đơn, nội suy | Trung bình, cần xét tăng trưởng |
| “Read model chậm tối đa 2 giây” | Chỉ đo p99 trong giờ bình thường | Chưa đủ để khẳng định tối đa |
| “Không có bản ghi sai sau retry” | Thử lỗi, đối soát, unique constraint | Chỉ đúng trong phạm vi bài kiểm tra |

Ghi rõ **“giả định”**, **“ước tính”** và **“đã đo”**. Đây là cách giảm nguy cơ biến dự báo thành cam kết kỹ thuật sai.

---

## 7. Mô hình chi phí định lượng đơn giản

Không cần một mô hình tài chính hoàn chỉnh để bắt đầu. Có thể dùng một công thức khái niệm:

\[
C_{\text{total}}
= N_r C_r
+ N_w C_w
+ C_{\text{storage}}
+ C_{\text{operations}}
+ C_{\text{risk}}.
\]

Trong đó:

- \(N_r\): số thao tác đọc trong một khoảng thời gian.
- \(C_r\): chi phí bình quân của một thao tác đọc trong cùng loại workload.
- \(N_w\): số thao tác ghi trong khoảng thời gian.
- \(C_w\): chi phí bình quân của một thao tác ghi.
- \(C_{\text{storage}}\): chi phí dữ liệu, index, replica, backup và retention.
- \(C_{\text{operations}}\): chi phí vận hành, giám sát, migration, nhân lực.
- \(C_{\text{risk}}\): ước lượng hậu quả của sự cố, mất nhất quán hoặc vi phạm SLO.

Công thức này là **khung tư duy**, không phải công thức hóa đơn của bất kỳ cloud DBMS nào. Một số loại chi phí có thể đã nằm trong đơn giá đọc/ghi, vì vậy không được cộng trùng khi tính tiền thực tế.

### 7.1. Thử tính số thao tác đọc/ghi

Giả sử mỗi ngày có:

~~~text
2.000.000 lần xem chi tiết đơn (Q1)
300.000 lần tạo đơn (W1)
100.000 lần đổi trạng thái (W2)
~~~

Một phương án đọc chi tiết đơn có thể cần trung bình hai request DB, trong khi một phương án embedding chỉ cần một request. Nếu giữ nguyên giả định và không có caching:

~~~text
Tham chiếu: 2.000.000 × 2 = 4.000.000 request đọc/ngày
Nhúng:      2.000.000 × 1 = 2.000.000 request đọc/ngày
Khác biệt:                    2.000.000 request/ngày
~~~

Đây mới là **ước tính số request logic**, không có nghĩa chi phí I/O hoặc hóa đơn giảm đúng 50%. Một request trả document lớn hơn; một aggregation có thể thay cho nhiều request; cache và index cũng có thể làm thay đổi chi phí.

Nếu thêm read model khiến mỗi W1 và W2 có thêm một cập nhật đồng bộ:

~~~text
300.000 + 100.000 = 400.000 cập nhật bản chiếu/ngày
~~~

Con số này chưa tính retry, index, replication hoặc các lần cập nhật do schema sửa đổi. Nó giúp định lượng **gánh nặng đồng bộ**, nhưng không kết luận throughput sẽ đủ hay không.

### 7.2. Tính dung lượng bổ sung từ bản sao

Giả sử read model lưu thêm trung bình **500 byte/đơn** cho 20 triệu đơn:

~~~text
20.000.000 × 500 byte = 10.000.000.000 byte
                      ≈ 10 GB dữ liệu logic thô
~~~

Nếu có ba replica logic với cùng lượng bản sao, riêng phần dữ liệu nhân bản có thể tương ứng khoảng **30 GB** trước index, compression, metadata, backup và các yếu tố khác.

Cần cẩn thận với đơn vị: GB theo hệ thập phân khác GiB theo hệ nhị phân. Trong tài liệu chi phí nên ghi rõ đơn vị và cách đo.

### 7.3. Không cộng p95 như cộng số trung bình

Nếu API phải gọi hai truy vấn có p95 lần lượt là 40 ms và 30 ms, **không thể khẳng định p95 của API là 70 ms** chỉ bằng phép cộng. Độ trễ tail phụ thuộc phân bố, tính tương quan, mức song song, mạng và xử lý ứng dụng.

Vì thế, mô hình chi phí giúp so sánh sơ bộ, còn **latency p95/p99 phải đo end-to-end** với tải và phân bố đại diện.

---

## 8. Đánh đổi thứ nhất: index cải thiện đọc nhưng tăng chi phí ghi và lưu trữ

Giả sử collection MongoDB `orders` có truy vấn:

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    status: "PAID"
  },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Một compound index có thể phục vụ truy vấn:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Điều kiện bằng trước, các trường sắp xếp sau là một hướng tổ chức hữu ích cho truy vấn này. Nhưng nó không mặc nhiên phục vụ mọi biến thể, ví dụ danh sách tất cả trạng thái của khách hàng sắp theo thời gian có thể cần index khác.

### 8.1. Ghi đánh đổi của index

| Trục | Tác động mong đợi |
|---|---|
| Đọc | Ít quét hơn nếu planner dùng index, có thể tránh sort riêng |
| Ghi | Insert/delete/update các trường index làm tăng công việc bảo trì index |
| Lưu trữ | Tốn thêm index entries và metadata; có thể cần thêm dung lượng khi rebuild |
| Độ phức tạp | Cần theo dõi index hữu dụng, build/migration, giới hạn tổ hợp filter |
| Tính đúng đắn | Index tăng tốc truy vấn, không thay thế authorization hay kiểm tra trạng thái |

Ví dụ ghi trong ADR:

> Giữ index ghép trên `(tenantId, customerId, status, createdAt, _id)` vì Q2 theo trạng thái chiếm 60% truy vấn danh sách. Dự kiến cải thiện p95; sẽ đo `keysExamined`, `docsExamined`, index size và latency insert/update dưới tải cao điểm. Xem xét loại bỏ hoặc thay index nếu Q2 giảm dưới 5% traffic trong ba tháng hoặc index cost vượt ngân sách đã thống nhất.

Số tỷ lệ ở đây là ví dụ về cách đặt **điều kiện kiểm tra**, không phải mức phổ quát.

### 8.2. Đo bằng kế hoạch truy vấn

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  customerId: "customer-42",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Điều nên ghi lại khi thử nghiệm:

- Số mục index được xét.
- Số document thực tế được đọc.
- Có bước sort lớn hay không.
- Query p95/p99 dưới tải thực tế.
- Kích thước index tăng bao nhiêu.
- Ghi mới và đổi `status` bị ảnh hưởng thế nào.

Tên trường trong execution plan phụ thuộc phiên bản. Không nên chỉ nhìn một query có `LIMIT 20` mà kết luận engine đọc đúng 20 mục dữ liệu.

---

## 9. Đánh đổi thứ hai: nhúng dữ liệu và tham chiếu

### 9.1. Khi nhúng thường có lợi

Nhúng phù hợp nếu dữ liệu con:

- Có cùng vòng đời với tài liệu cha.
- Thường được đọc cùng cha.
- Có số lượng và kích thước được giới hạn.
- Ít khi phải cập nhật độc lập bởi nhiều tác nhân.
- Có thể hưởng lợi từ một lần ghi nguyên tử cấp document.

Ví dụ dữ liệu địa chỉ giao hàng **tại thời điểm đặt** và các dòng hàng của đơn bán lẻ nhỏ thường là ứng viên nhúng.

### 9.2. Khi tham chiếu thường có lợi

Tham chiếu phù hợp nếu dữ liệu con:

- Có vòng đời riêng hoặc được nhiều cha dùng chung.
- Có số lượng tăng không giới hạn.
- Được phân trang/truy vấn độc lập.
- Có nhu cầu ghi thường xuyên hoặc retention khác cha.
- Có yêu cầu phân quyền, chỉ mục hoặc khả năng mở rộng riêng.

Ví dụ hàng triệu bình luận của một bài viết không nên nhúng tất cả vào một document bài viết; có thể tách bình luận và chỉ giữ vài bản xem trước được giới hạn nếu cần.

### 9.3. Ghi rõ “dữ liệu trùng” thuộc loại nào

Hai trường hợp dễ nhầm:

1. **Snapshot lịch sử:** tên và giá sản phẩm được nhúng vào đơn, **không sửa theo catalog**. Đây là bản sao có ngữ nghĩa cố định.
2. **Bản chiếu trạng thái hiện tại:** tên sản phẩm được nhân bản vào feed danh sách để đọc nhanh, **cần đồng bộ khi catalog đổi tên**. Đây là bản sao dẫn tới chi phí duy trì nhất quán.

Mặc dù cả hai đều là denormalization, đánh đổi ghi và độ phức tạp khác nhau hoàn toàn. Trong quyết định phải ghi **bản sao nào bất biến, bản sao nào cần cập nhật và nguồn sự thật là gì**.

---

## 10. Đánh đổi thứ ba: nhiều bảng đọc theo truy vấn

Trong hệ wide-column như Cassandra, tổ chức khóa thường gắn chặt với câu truy vấn. Ví dụ bảng đơn theo khách:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id text,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_vnd bigint,
    PRIMARY KEY (
        (customer_id, order_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Truy vấn đọc danh sách một khách trong một tháng:

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer_month
WHERE customer_id = 'customer-42'
  AND order_month = '2026-11'
LIMIT 20;
~~~

Một bảng khác có thể được thiết kế cho “đơn PAID trong tháng”:

~~~sql
CREATE TABLE orders_by_customer_status_month (
    customer_id text,
    status text,
    order_month text,
    created_at timestamp,
    order_id uuid,
    total_vnd bigint,
    PRIMARY KEY (
        (customer_id, status, order_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Phương án này cho phép các truy vấn có mẫu lọc khác nhau dùng partition key tương ứng. Nhưng một lần cập nhật `status` có thể phải **xóa dữ liệu khỏi nhóm trạng thái cũ và ghi vào nhóm mới**; việc này không thể coi là tự động nguyên tử trên tất cả bảng.

### 10.1. Đánh đổi cụ thể

| Trục | Một bảng theo khách | Hai bảng theo khách và theo trạng thái |
|---|---|---|
| Đọc lịch sử tất cả trạng thái | Tự nhiên trong một tháng | Vẫn dùng bảng thứ nhất |
| Đọc PAID mới nhất | Có thể cần lọc nhiều hoặc thiết kế khác | Truy vấn đúng nhóm PAID |
| Ghi đơn | Một đường ghi chính | Phải duy trì ít nhất hai bảng đọc nếu cả hai cần cập nhật |
| Đổi trạng thái | Một cập nhật theo thiết kế | Có thể cần chuyển hàng từ partition cũ sang mới |
| Dung lượng | Ít bản sao hơn | Tăng dữ liệu/index và replica tương ứng |
| Độ phức tạp | Đường đọc trạng thái có thể khó | Đồng bộ, đối soát, migration và phục hồi phức tạp hơn |

**Câu quyết định phải ghi:** “Chúng ta sẵn sàng trả thêm chi phí W2 và lưu trữ để bảo đảm Q2 lọc theo trạng thái dưới SLO, và chấp nhận read model cập nhật trễ tối đa bao lâu?”

### 10.2. Thêm bucket không tự miễn phí

Nếu một khách hàng có quá nhiều đơn mỗi tháng, có thể chia theo ngày hoặc thêm bucket. Nhưng query “20 đơn mới nhất trên toàn tháng” phải đọc nhiều partition rồi hợp nhất kết quả.

Ghi đánh đổi:

- **Lợi ích ghi:** giảm kích thước/tải từng partition.
- **Chi phí đọc:** fan-out và merge, nhiều cursor hoặc paging state.
- **Chi phí lưu trữ:** tăng metadata của nhiều partition nhỏ.
- **Độ phức tạp:** bộ định tuyến bucket phải ổn định; thay số bucket về sau cần kế hoạch migration.

---

## 11. Đánh đổi thứ tư: cache và sự đánh đổi giữa tốc độ với độ tươi

Một cache có thể giảm số lượt đọc DBMS cho Q3 (thông tin sản phẩm) nếu nhiều người đọc cùng sản phẩm. Nhưng cache đặt ra câu hỏi:

- Dữ liệu nào được cache: giá, tên, tồn kho hay mô tả?
- Mỗi khóa có TTL bao lâu?
- Khi cập nhật nguồn, làm sao làm mất hiệu lực bản cache?
- Có chấp nhận hiển thị dữ liệu cũ trong vài giây không?
- Nếu cache bị lỗi hoặc bị xóa đồng loạt, DBMS có chịu được lượt đọc dồn về không?
- Có cần chống cache stampede với khóa rất phổ biến không?

### 11.1. Phân loại dữ liệu theo mức chấp nhận trễ

| Dữ liệu | Có thể chấp nhận stale? | Cân nhắc |
|---|---|---|
| Mô tả sản phẩm | Có thể vài giây/phút tùy sản phẩm | Cache TTL tương đối thuận tiện |
| Giá hiển thị | Tùy nghiệp vụ và quy định thông báo | Cần chính sách làm mới/đối chiếu tại checkout |
| Tồn kho để quyết định bán | Không được dùng stale value để bán vượt số lượng | Cần nguồn xác nhận giao dịch đáng tin |
| Hồ sơ hiển thị | Có thể ngắn hạn | Cần invalidation khi đổi |
| Quyền truy cập | Không nên dựa vào cache cũ nếu gây cấp quyền sai | Kiểm tra chính sách bảo mật và freshness chặt |

Cache là một phần của **thiết kế truy vấn**, không chỉ là phép tối ưu bổ sung. Nếu dùng cache, ADR phải nêu **trường nào có thể stale, stale tối đa theo hợp đồng nào và cách xử lý khi cache không đáng tin**.

### 11.2. Mô hình read-through và invalidation

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Cache as Cache
    participant DB as DB nguồn
    App->>Cache: Đọc product-8
    alt Cache hit
        Cache-->>App: Giá trị đang lưu
    else Cache miss
        App->>DB: Đọc product-8
        DB-->>App: Giá trị hiện tại
        App->>Cache: Ghi cache với TTL
        App-->>App: Sử dụng giá trị từ DB
    end
~~~

Sơ đồ chỉ minh họa đường đọc. Còn đường cập nhật phải được thiết kế riêng; chỉ cache dữ liệu một lần rồi quên invalidation có thể khiến bản sao không phản ánh trạng thái nguồn.

---

## 12. Độ phức tạp cần được viết dưới dạng kịch bản lỗi

Một cách ghi “phức tạp hơn 3 điểm” không giúp người trực sự cố. Nên nêu những câu hỏi cụ thể:

### 12.1. Thao tác hai nơi: một nơi thành công, một nơi thất bại

Giả sử hệ ghi đơn thành công nhưng cập nhật `orders_by_customer` thất bại.

**Phương án đồng bộ trực tiếp:** có thể phải dùng transaction nếu DBMS hỗ trợ trong phạm vi cần thiết, hoặc thiết kế retry/compensation. Không thể mặc định hai ghi vào hai hệ thống tự nguyên tử.

**Phương án bất đồng bộ:** có thể ghi nguồn và outbox trong một transaction phù hợp, sau đó worker phát sự kiện để cập nhật read model. Consumer phải **idempotent**, biết retry, phát hiện lỗi và có khả năng rebuild/backfill.

### 12.2. Sự kiện bị gửi lại

Một sự kiện `OrderPaid` có thể được xử lý hai lần do retry hoặc at-least-once delivery. Nếu cập nhật read model bằng phép **tăng doanh thu** hai lần, tổng có thể sai.

Phải xác định:

- Event ID hoặc version dùng để chống xử lý lặp.
- Cách phân biệt cập nhật mới với cập nhật cũ.
- Khi một event thiếu, pipeline phát hiện và bù thế nào.
- Khi build lại, trạng thái được tính từ nguồn nào.
- Quy trình đối soát tổng tiền hoặc số hàng.

**At-least-once delivery** không tự bảo đảm *exactly-once business effect*. Đây là phần chi phí độ phức tạp phải được ghi khi chọn kiến trúc có event.

### 12.3. Dữ liệu đọc được trước khi bản chiếu cập nhật

Nếu API đọc read model ngay sau khi client tạo đơn, có thể chưa thấy đơn mới. Cần chọn hợp đồng:

- **Read-your-writes** bằng cách đọc nguồn sau ghi hoặc phối hợp trạng thái client.
- Trả trạng thái “đang xử lý”, chờ bản chiếu cập nhật trong ngân sách nhất định.
- Cho phép eventual consistency có giới hạn được mô tả rõ trong UX.

Lựa chọn này ảnh hưởng cả ứng dụng lẫn kỳ vọng người dùng. Không được chỉ ghi “eventually consistent” rồi bỏ qua thời gian trễ và hành vi UI.

### 12.4. Migration khi đổi khóa hoặc index

Nếu partition key hiện tại không còn phù hợp, thường phải:

1. Tạo bảng/index mới.
2. Backfill dữ liệu lịch sử.
3. Đồng bộ thay đổi phát sinh trong lúc chuyển.
4. Đối soát độ đầy đủ và phiên bản dữ liệu.
5. Chuyển đường đọc.
6. Ngừng đường cũ khi tiêu chí an toàn đã đạt.

Chi phí migration phải được tính vào độ phức tạp **ngay từ lúc quyết định**, không chỉ sau khi hệ gặp vấn đề.

---

## 13. Viết Architecture Decision Record (ADR)

**Architecture Decision Record (ADR)** là bản ghi ngắn gọn nhưng đủ thông tin để người khác hiểu một quyết định kiến trúc. Mục tiêu không phải làm văn bản thật dài, mà giữ những dữ kiện có thể kiểm chứng và giúp xem xét lại khi giả định thay đổi.

Một ADR cho NoSQL nên có:

1. **Tiêu đề, ID, ngày, chủ sở hữu và trạng thái**: đề xuất, chấp nhận, thay thế hoặc hủy.
2. **Bối cảnh:** vấn đề hiện tại, dữ liệu, mẫu truy vấn, quy mô và ràng buộc.
3. **Mục tiêu và tiêu chí quyết định:** SLO, tính đúng đắn, chi phí, giới hạn dung lượng và đội ngũ vận hành.
4. **Các phương án:** bao gồm phương án giữ nguyên trạng và ít nhất một phương án thay thế đáng cân nhắc.
5. **Bằng chứng:** benchmark, `explain`, kích thước index, ước tính chi phí, ngày đo, cấu hình thử nghiệm.
6. **Đánh đổi đọc/ghi/lưu trữ/độ phức tạp:** giải thích chiều hướng và mức ảnh hưởng.
7. **Quyết định và lý do:** phương án được chọn cùng những bất lợi chấp nhận.
8. **Hệ quả:** công việc phát sinh, điều kiện nhất quán, monitoring và kế hoạch phục hồi.
9. **Điều kiện xem xét lại:** ngưỡng/tín hiệu làm quyết định có thể không còn phù hợp.
10. **Liên kết tới tài liệu triển khai hoặc issue** khi có; không đưa bí mật, mật khẩu hoặc thông tin nhạy cảm vào ADR.

### 13.1. Một mẫu ADR có thể dùng ngay

~~~markdown
# ADR-027: Cấu trúc đọc đơn hàng theo khách hàng

- Ngày: 2026-11-14
- Trạng thái: Accepted
- Chủ sở hữu: Nhóm Orders
- Phạm vi: API danh sách đơn hàng
- Thay thế: Chưa có
- Ngày xem xét lại: 2027-02-14

## Bối cảnh

Q1: GET /orders/{id}
Q2: GET /customers/{id}/orders?status=PAID&limit=20
W1: Tạo đơn
W2: Đổi trạng thái đơn

Quy mô: 20 triệu đơn, tăng 300.000 đơn/ngày (giả định).
SLO: Q2 p95 < 120 ms khi tải thiết kế.
Không chấp nhận sai trạng thái thanh toán nguồn.

## Các phương án

A. Một collection nguồn + compound index.
B. Một collection nguồn + read model theo customer/status.
C. Một bảng theo customer/status trong wide-column DB.

## Đánh đổi

| Tiêu chí | A | B | C |
|---|---|---|---|
| Đọc Q2 | ... | ... | ... |
| Ghi W2 | ... | ... | ... |
| Lưu trữ | ... | ... | ... |
| Nhất quán | ... | ... | ... |
| Vận hành | ... | ... | ... |

## Bằng chứng

- Dataset: phiên bản, số bản ghi, phân bố tenant và trạng thái.
- Cấu hình: DBMS, phiên bản, số node, replica, index.
- Tải: QPS, tỷ lệ đọc/ghi, thời gian warm-up.
- Kết quả: p50/p95/p99, keys/docs examined, throughput.
- Chi phí: data/index size, write cost, estimated monthly cost.

## Quyết định

Chọn A ở giai đoạn này vì ... (dẫn số đo).
Chấp nhận ... (bất lợi).
Không chọn B vì ...
Không chọn C vì ...

## Hệ quả và rủi ro

- Những chỉ mục mới cần tạo.
- Migration/rollback và giám sát.
- Đường cập nhật trạng thái.
- Rủi ro tenant lớn, khi số bản ghi tăng.

## Xem xét lại nếu

- p95 Q2 > 120 ms trong khoảng đã định,
- index size vượt ngân sách,
- truy vấn status chiếm phần lớn tải,
- tenant lớn gây hotspot,
- hoặc yêu cầu nhất quán của API thay đổi.
~~~

Mẫu trên là **khung điền dữ liệu**; không nên giữ những dấu ba chấm khi phát hành ADR thực tế. Phần “Quyết định” phải có đủ lý do và bằng chứng để người khác hiểu tại sao các phương án bị loại.

### 13.2. Trạng thái của ADR có ý nghĩa gì?

- **Proposed:** đang xem xét, số liệu và phương án có thể thay đổi.
- **Accepted:** đã chọn, có chủ sở hữu và việc triển khai phù hợp.
- **Superseded:** bị một quyết định mới thay thế; vẫn giữ lịch sử.
- **Deprecated/Rejected:** không còn được khuyến nghị hoặc đã bị loại với lý do.

Không nên xóa ADR cũ khi đổi chiến lược. Giữ lịch sử giúp tránh lặp lại tranh luận đã từng có hoặc quên những ràng buộc khiến quyết định cũ hợp lý ở thời điểm đó.

---

## 14. Ví dụ ADR hoàn chỉnh với số liệu thực nghiệm giả định

Giả sử nhóm Orders đã có collection nguồn và cân nhắc tạo read model riêng vì Q2 lọc theo trạng thái chậm.

### 14.1. Bối cảnh thử nghiệm

Các số liệu dưới đây **hoàn toàn giả định để minh họa cách ghi quyết định**:

~~~text
Dữ liệu thử:       5.000.000 đơn
Phân bố:           5% khách tạo 45% truy vấn
Trạng thái PAID:   65% tổng đơn
Đọc/ghi:           80% / 20%
Replica:           cấu hình cố định giữa các lần đo
Truy vấn Q2:       customerId + status + createdAt DESC
SLO Q2:            p95 < 120 ms
Quy tắc tài chính: nguồn trạng thái đơn là authoritative
~~~

Các phương án:

- **A:** collection nguồn với compound index tối ưu Q2.
- **B:** nguồn + read model được cập nhật qua sự kiện, cho phép trễ.
- **C:** không thêm index; ứng dụng lấy danh sách theo khách rồi lọc/sắp xếp.

### 14.2. Bảng kết quả minh họa

| Chỉ số | A — Compound index | B — Read model | C — Lọc sau khi đọc |
|---|---:|---:|---:|
| Q2 p95 | 55 ms | 30 ms | 310 ms |
| Q2 p99 | 95 ms | 65 ms | 780 ms |
| W2 p95 | 42 ms | 48 ms ở nguồn, chưa tính cập nhật bản chiếu | 31 ms |
| Dung lượng bổ sung | 12 GB index | 26 GB data + index | 0 GB theo mục đang xét |
| Độ trễ bản chiếu p99 | Không có read model riêng | 1,8 giây | Không có read model riêng |
| Đường đồng bộ thêm | Không | Consumer, retry, backfill, reconciliation | Không |
| Khả năng thỏa Q2 SLO | Có trong điều kiện thử | Có | Không |

*Lưu ý về W2:* con số 48 ms của phương án B chỉ mô tả thời gian xác nhận thao tác ở **nguồn**, không phải thời gian dữ liệu xuất hiện trong read model. Không nên so sánh nó như thể B luôn đồng bộ ngay.

### 14.3. Quyết định minh họa

**Chọn A — compound index**, với lý do:

- Q2 p95 55 ms nhỏ hơn SLO 120 ms và có khoảng dự phòng trong điều kiện thử.
- Q2 p99 95 ms cho thấy độ trễ cao nhất trong phân vị được đo vẫn chấp nhận được theo ngân sách thử.
- Dung lượng index bổ sung 12 GB nhỏ hơn 26 GB của phương án B.
- Không cần vận hành consumer/backfill và chưa phải chấp nhận bản chiếu trễ tới vài giây.
- Phương án C không đáp ứng SLO nên bị loại dù ghi đơn nhanh hơn.

**Bất lợi chấp nhận:** duy trì thêm index làm tăng chi phí ghi so với C, và cần theo dõi tác động khi dữ liệu lớn dần. Nếu traffic tăng mạnh hoặc tập truy vấn thay đổi, có thể xem xét B ở giai đoạn sau.

### 14.4. Điều kiện xem xét lại

ADR ghi:

- Nếu Q2 p95 vượt 100 ms liên tục ở tải bình thường trong một khoảng thời gian đã định, cần điều tra trước khi chạm ngưỡng SLO 120 ms.
- Nếu tỷ lệ timeout hoặc p99 tăng đáng kể trên nhóm khách hàng rất lớn, cần đánh giá phân bố và index.
- Nếu nhu cầu báo cáo theo nhiều thuộc tính làm tăng index không kiểm soát, xem xét read model/analytics riêng.
- Nếu chi phí ghi do index trở thành nút thắt chính, đo lại A và B.
- Nếu khả năng chấp nhận dữ liệu trễ thay đổi, đánh giá lại trade-off về nhất quán trước khi chuyển kiến trúc.

Đây là cách ghi quyết định **có thời điểm và điều kiện sống**, không phải tuyên bố “A luôn tốt hơn B”.

---

## 15. Đo thế nào để bằng chứng có giá trị?

Một benchmark không ghi cấu hình và phân bố workload khó tái tạo. Hai phương án phải được so sánh **trong cùng điều kiện có thể đối chiếu**.

### 15.1. Tập dữ liệu đại diện

Nên có:

- Quy mô gần với dự báo production hoặc nhiều mức kích thước để nội suy.
- Phân bố tenant/customer lệch, bao gồm khách hàng cực lớn.
- Tỷ lệ trạng thái, bản ghi cũ/mới và trường tùy chọn như thực tế.
- Document có kích thước khác nhau, không chỉ document nhỏ đồng đều.
- Cùng độ trễ mạng và cấu hình replica khi so sánh.
- Dữ liệu có thể lặp lại giữa các lần chạy bằng seed hoặc snapshot thích hợp.

Không nên chọn chỉ 1.000 document nhỏ và kết luận index nào cũng đủ nhanh cho 100 triệu document.

### 15.2. Tải thử thực tế

Một kịch bản:

~~~text
Giai đoạn 1: Warm-up theo tải nhẹ.
Giai đoạn 2: Tải trung bình trong khoảng đủ dài.
Giai đoạn 3: Tải cao điểm với cùng tỷ lệ Q1/Q2/Q3/W1/W2.
Giai đoạn 4: Tải lệch: một tenant chiếm 40% request.
Giai đoạn 5: Mô phỏng thay đổi trạng thái liên tục.
Giai đoạn 6: Tải hỗn hợp trong khi rebuild index hoặc backfill.
~~~

Nếu phép thử có cache, phải ghi rõ warm/cold cache và cách reset giữa các lần đo. Cũng cần tách đo **DB latency** và **end-to-end API latency**; một query nhanh ở DBMS vẫn có thể dẫn tới API chậm vì serialization, network hoặc fan-out.

### 15.3. Chỉ số nên thu thập

| Mục tiêu | Metric | Cách diễn giải |
|---|---|---|
| Đọc nhanh | p50/p95/p99, errors, timeouts | Tail latency có nằm trong ngân sách? |
| Đọc hiệu quả | index keys/docs examined, rows/partition touched | Có quét nhiều hơn số kết quả cần trả không? |
| Ghi chịu tải | throughput, p95/p99 write, conflict/retry | Index/view bổ sung có làm write path nghẽn không? |
| Lưu trữ bền vững | bytes data/index, replica, backup, tăng trưởng/ngày | Chi phí tháng và headroom còn bao nhiêu? |
| Nhất quán read model | lag p50/p95/p99, backlog, stale records | Độ trễ có phù hợp hợp đồng đọc? |
| Vận hành | rebuild duration, repair, recovery, failures | Khi hỏng có thể phục hồi trong mục tiêu RTO/RPO không? |
| Độ phức tạp thay đổi | số thành phần/pipeline, thời gian release/migration | Thay đổi schema có tác động bao nhiêu hệ? |

**Không dùng một chỉ số để đại diện tất cả.** Ví dụ phương án B có Q2 p95 tốt nhưng read model p99 lag cao; người dùng vừa tạo đơn có thể không thấy đơn ngay.

### 15.4. Không đánh tráo thứ tự các phép đo

Khi tạo index mới, cache/compaction có thể làm hiệu năng thay đổi tạm thời. Nếu thử A khi cache đã ấm, B khi cache lạnh, kết quả sẽ thiên lệch. Nên định nghĩa quy trình thử, chạy nhiều lần có kiểm soát và lưu dữ liệu thô để phân tích sau.

---

## 16. Độ phức tạp dưới góc nhìn chi phí dài hạn

### 16.1. Chi phí hiện tại khác chi phí ba năm sau

Một cách thiết kế có thể rẻ ở ngày đầu nhưng đắt về sau:

- Bảng không có time bucket dễ bắt đầu nhưng partition tăng không giới hạn.
- Một collection có hàng chục index giúp thêm tính năng nhanh, nhưng mỗi insert tốn nhiều công việc và migration phức tạp.
- Mỗi màn hình có read model riêng giúp mỗi API đơn giản, nhưng toàn hệ có quá nhiều pipeline khó đối soát.
- Một document nhúng mọi phần tử dễ đọc trong năm đầu nhưng quá lớn khi số lượng tăng gấp 100 lần.

ADR cần có **horizon**: quyết định đang nhắm tới ba tháng, một năm hay nhiều năm; mức tăng trưởng và thời gian chuyển đổi dự kiến thế nào.

### 16.2. Đánh giá rủi ro khóa nhà cung cấp

Khi tận dụng feature chuyên biệt như secondary index, transaction đa document, materialized view, stream hoặc query language riêng, công sức chuyển DBMS trong tương lai có thể tăng.

Không cần tránh mọi tính năng riêng, nhưng nên ghi:

- Dữ liệu export/import được không?
- Query và schema có phụ thuộc tính năng chỉ nhà cung cấp đó hỗ trợ?
- Nếu cần chuyển, có phải viết lại bao nhiêu đường truy vấn?
- Khả năng thay đổi cấu hình, quota và đơn giá cloud ảnh hưởng ra sao?

Đây là chi phí **quyền linh hoạt trong tương lai**, một thành phần của complexity/risk.

### 16.3. Đừng tối ưu cục bộ làm hỏng hệ thống

Một index giúp một API nhanh hơn nhưng khiến ghi đơn chậm đi có thể tác động nhiều người dùng hơn lợi ích nó mang lại.

Tương tự, cache sản phẩm giảm DB reads, nhưng nếu cache invalidation sai khiến giá hiển thị cũ, hệ thống có thể gặp sự cố nghiệp vụ nghiêm trọng.

Các quyết định cần xét **toàn bộ luồng nghiệp vụ**, không chỉ microbenchmark của một câu truy vấn.

---

## 17. Ma trận quyết định có trọng số: dùng thế nào cho đúng?

Một nhóm có thể dùng điểm để so sánh phương án, nhưng điểm chỉ là công cụ hỗ trợ thảo luận.

Ví dụ trọng số giả định:

| Tiêu chí | Trọng số |
|---|---:|
| Hiệu năng đọc Q2 | 35% |
| Chi phí ghi W1/W2 | 25% |
| Chi phí lưu trữ | 15% |
| Độ phức tạp vận hành | 25% |

Giả sử chấm từ 1 (kém) đến 5 (tốt), với **định nghĩa ngưỡng điểm được công bố trước**:

| Phương án | Đọc | Ghi | Lưu trữ | Vận hành |
|---|---:|---:|---:|---:|
| A: index nguồn | 4 | 3 | 4 | 4 |
| B: read model | 5 | 2 | 2 | 2 |
| C: lọc phía ứng dụng | 1 | 5 | 5 | 4 |

Công thức:

\[
S = 0.35R + 0.25W + 0.15S_t + 0.25C.
\]

Trong đó \(R\) là điểm đọc, \(W\) là điểm ghi, \(S_t\) là điểm lưu trữ, \(C\) là điểm độ phức tạp.

Với điểm minh họa:

~~~text
A = 0,35×4 + 0,25×3 + 0,15×4 + 0,25×4 = 3,75
B = 0,35×5 + 0,25×2 + 0,15×2 + 0,25×2 = 3,05
C = 0,35×1 + 0,25×5 + 0,15×5 + 0,25×4 = 3,35
~~~

Phương án A có điểm cao nhất trong giả định này. **Nhưng nếu C không đáp ứng SLO bắt buộc thì phải loại trước**, không được đưa C thành lựa chọn hợp lệ chỉ vì tổng điểm vẫn cao.

### 17.1. Hạn chế của bảng điểm

- Trọng số là lựa chọn chủ quan của nhóm.
- Điểm 1–5 có thể che giấu khác biệt thực tế giữa 80 ms và 800 ms.
- Hai phương án có tổng điểm gần nhau nhưng rủi ro hoàn toàn khác.
- Không phản ánh được ràng buộc cứng như tính đúng đắn, bảo mật hoặc giới hạn pháp lý.
- Các chỉ số có thể tương quan, nên cộng điểm có nguy cơ đếm trùng lợi ích.

Vì thế **ma trận có trọng số là phần bổ trợ**, không thay thế benchmark, hợp đồng nhất quán và lý do định tính.

### 17.2. Kiểm tra độ nhạy của quyết định

Hãy thử thay trọng số đọc từ 35% lên 50% trong khi giảm các phần khác tương ứng. Nếu phương án được chọn thay đổi chỉ vì trọng số chênh vài điểm, quyết định còn nhạy và cần thảo luận thêm về ưu tiên nghiệp vụ.

Tương tự, nếu data growth tăng 10 lần hoặc tỷ lệ đọc/ghi đảo từ 80/20 sang 20/80, cần xem các phép đo và kết luận còn đúng không.

ADR nên ghi **giả định nào có ảnh hưởng lớn nhất tới kết quả**. Đó là những giả định cần theo dõi thường xuyên.

---

## 18. Điều kiện xem xét lại (revisit triggers)

Một quyết định được ghi lại tốt luôn cho phép người kế nhiệm biết **khi nào nó hết hiệu lực**.

Ví dụ:

| Tín hiệu | Ngưỡng minh họa | Hành động |
|---|---|---|
| Đọc Q2 chậm | p95 vượt 100 ms liên tục trong cửa sổ xác định | Điều tra index, skew và capacity trước khi vi phạm SLO |
| Write path bị ảnh hưởng | p99 W2 tăng quá 30% sau thêm index | So sánh lợi ích đọc với giá ghi; cân nhắc index khác |
| Index phình to | Tổng index vượt ngân sách dung lượng | Rà soát index ít dùng, retention và mô hình khác |
| Read model trễ | Lag p99 vượt 3 giây theo hợp đồng | Kiểm tra consumer/backlog/retry, có thể đổi đường đọc |
| Số partition quá lớn | Số partition/request tăng theo số bucket không kiểm soát | Thiết kế lại bucket và pagination |
| Thay đổi yêu cầu sản phẩm | API cần lọc theo nhiều trường mới | Cập nhật access-pattern table và so sánh phương án |
| Thay đổi bảo đảm nhất quán | “Đọc ngay sau ghi” trở thành bắt buộc | Xem lại đồng bộ bất đồng bộ và đường đọc nguồn |
| Hạ tầng thay đổi | Nút/replica/giá/phiên bản DBMS đổi | Đo lại, không dùng benchmark cũ làm kết luận mới |

Ngưỡng ở bảng là **ví dụ**. Trong sản phẩm thật phải gắn với SLO, kế hoạch capacity, chi phí và khả năng phản ứng của nhóm.

### 18.1. Chủ sở hữu và thời hạn cập nhật

Mỗi ADR nên có owner/team và kỳ kiểm tra. Không có owner, một chỉ số có thể vượt ngưỡng nhiều tháng mà không ai biết cần xem lại thiết kế.

### 18.2. Ghi thay đổi theo bằng chứng mới

Khi quyết định thay đổi, nên tạo ADR mới với lý do và đánh dấu ADR cũ là **superseded**. Đừng âm thầm sửa nội dung quyết định cũ khiến lịch sử biến mất.

---

## 19. Mẫu nhật ký đánh đổi ngắn cho mỗi truy vấn

Không phải mọi điều chỉnh index đều cần một ADR dài. Với thay đổi nhỏ, có thể lưu một bảng ngắn gần tài liệu kiến trúc.

| Trường | Nội dung ví dụ |
|---|---|
| **Mã quyết định** | DM-2026-014 |
| **Ngày/owner** | 2026-11-14 / Orders Team |
| **Truy vấn liên quan** | Q2: 20 đơn PAID mới nhất của khách |
| **Thay đổi đề xuất** | Thêm index `(tenantId, customerId, status, createdAt DESC, _id DESC)` |
| **Lợi ích đọc dự kiến** | Giảm quét và tránh sort lớn |
| **Chi phí ghi dự kiến** | Insert, delete và thay status phải duy trì index |
| **Chi phí lưu trữ dự kiến** | Tăng index size; cần đo bytes |
| **Độ phức tạp** | Theo dõi index usage, lên kế hoạch build và rollback |
| **Số liệu hiện tại** | p95 Q2, docs examined, W2 p99, index bytes |
| **Tiêu chí thành công** | p95 Q2 dưới SLO, W2 không vượt ngân sách |
| **Rủi ro** | Khách hàng lớn, dữ liệu lệch, các truy vấn bỏ filter status |
| **Rollback** | Có kế hoạch loại index sau khi xác nhận query không phụ thuộc |
| **Ngày xem xét lại** | Sau rollout và theo kỳ được thống nhất |

Bản ghi ngắn vẫn cần rõ **lợi ích, chi phí, bằng chứng và điều kiện phản hồi**. Không nhất thiết nhồi đủ mọi thuật ngữ vào quyết định nhỏ.

---

## 20. Những lỗi thường gặp khi ghi lại đánh đổi

| Lỗi | Vì sao nguy hiểm | Cách làm tốt hơn |
|---|---|---|
| “NoSQL nhanh hơn SQL” | Kết luận không gắn truy vấn/workload | Ghi query, index, dữ liệu, phiên bản và phép đo |
| Chỉ so latency đọc | Bỏ chi phí ghi, index và đồng bộ | Đo cả W1/W2, storage và vận hành |
| Dùng dữ liệu trung bình | Che khuất hot tenant hoặc document lớn | Ghi phân bố và trường hợp cực đại |
| Chỉ ghi “đọc nhanh/ghi chậm” | Không biết mức nào là chấp nhận | Ghi p95/p99, throughput và SLO |
| Xem bản sao dữ liệu là miễn phí | Quên write amplification, lag và đối soát | Liệt kê từng đường cập nhật và source of truth |
| Không nêu nhất quán | Dễ tạo lỗi nghiệp vụ khi view stale | Ghi staleness budget, fallback và idempotency |
| Không liệt kê phương án bị loại | Nhóm sau có thể lặp lại tranh luận cũ | Ghi lý do cụ thể và bằng chứng |
| Trộn số đo với ước tính | Dự báo bị hiểu là sự thật | Gắn nhãn observed/estimated/assumed |
| Dùng một benchmark trên data nhỏ | Không đại diện workload production | Đo nhiều quy mô, skew và tải hỗn hợp |
| Tính chi phí lưu trữ chỉ bằng kích thước JSON | Bỏ replica, index, backup, compaction | Tính đầy đủ phạm vi theo sản phẩm |
| Chấm điểm mà không có ràng buộc cứng | Phương án sai nghiệp vụ có thể “thắng” | Kiểm tra invariant/security trước khi xếp hạng |
| Không có owner và revisit trigger | Quyết định lỗi thời nhưng không được nhận biết | Chỉ định người chịu trách nhiệm và metric theo dõi |
| Xóa ADR cũ | Mất lịch sử lý do thiết kế | Tạo ADR thay thế, giữ lại bản cũ |

---

## 21. Bài tập thực hành: thiết kế bảng tin và lịch sử tương tác

Một mạng xã hội chuyên học tập có các yêu cầu:

- **Q1:** xem 30 bài mới nhất của những người đang theo dõi, p95 dưới 150 ms.
- **Q2:** xem tất cả bài của một tác giả, 20 bài mỗi trang.
- **Q3:** xem chi tiết một bài và 10 bình luận gần nhất.
- **W1:** một tác giả đăng bài; có thể được hàng trăm nghìn người theo dõi.
- **W2:** người dùng bình luận, số bình luận một bài có thể rất lớn.
- **W3:** tác giả sửa hoặc xóa bài; cần đáp ứng quyền xóa dữ liệu.
- **Retention:** bài viết và bình luận có yêu cầu lưu giữ, xóa và kiểm toán riêng.

Ba phương án cho feed:

**A — Fan-out on read:** khi mở feed, đọc bài từ các tác giả được theo dõi rồi hợp nhất theo thời gian.

**B — Fan-out on write:** khi tác giả đăng bài, ghi thêm item feed vào danh sách mỗi người theo dõi.

**C — Hybrid:** dùng B cho tác giả thường, dùng A hoặc mô hình khác cho tác giả có cực nhiều người theo dõi.

### 21.1. Lập ma trận cho ba phương án

| Tiêu chí | A: Fan-out khi đọc | B: Fan-out khi ghi | C: Hybrid |
|---|---|---|---|
| Chi phí đọc Q1 | Nhiều nguồn cần merge | Feed theo người dùng có thể đọc trực tiếp | Tùy số tác giả đặc biệt phải ghép |
| Chi phí ghi W1 | Ghi bài nguồn | Ghi bài + có thể rất nhiều feed entry | Tối ưu theo nhóm tác giả |
| Lưu trữ | Ít bản sao feed hơn | Nhiều entry feed được nhân bản | Trung gian, tùy tỷ lệ người nổi tiếng |
| Độ phức tạp | Fan-out, pagination, lọc và sort | Queue, retry, consistency, dọn/xóa entry | Cần hai đường xử lý và hợp nhất |
| Dữ liệu cũ | Đọc từ nguồn khi query | Feed có thể trễ/đã cũ | Cần quy tắc thống nhất |
| Tình huống cực đoan | Người theo dõi rất nhiều tác giả | Tác giả có lượng follower cực lớn | Có thể phân loại để giảm cực đoan |

**Không có đáp án luôn đúng.** Tỷ lệ đọc/ghi, số lượng follower, độ dài feed, yêu cầu xóa và SLO sẽ quyết định. Đặc biệt, nếu một bài bị xóa, những bản sao trong feed cần được vô hiệu hóa hoặc không còn trả về theo chính sách.

### 21.2. Yêu cầu bài làm

1. Ghi ba query chính và ba thao tác ghi vào access-pattern table.
2. Đề xuất khóa lọc và sort key cho Q1/Q2/Q3, bao gồm tie-breaker để phân trang.
3. Ước lượng số entry feed bổ sung nếu một tác giả có 200.000 follower đăng 3 bài/ngày; phân biệt số **entry logic** và byte lưu trữ.
4. Chỉ ra chi phí của việc người dùng theo dõi 3.000 tác giả nếu dùng fan-out on read.
5. Nêu source of truth và cách xử lý sự kiện đăng bài/xóa bài bị gửi lại.
6. Chọn một phương án cho giai đoạn ban đầu và ghi ADR với tiêu chí xem xét lại.
7. Lập kế hoạch benchmark khi số người dùng tăng gấp 10 và tỷ lệ đọc/ghi thay đổi.

### 21.3. Gợi ý định lượng

Với **200.000 người theo dõi** và **3 bài/ngày**, nếu fan-out on write tạo một entry cho mỗi follower mỗi bài:

~~~text
200.000 follower × 3 bài/ngày
= 600.000 feed entries/ngày cho riêng tác giả này.
~~~

Đây là số entry **logic**, không phải số ghi vật lý thực tế sau replication, index, retry hay nén. Nếu entry trung bình 150 byte:

~~~text
600.000 × 150 byte = 90.000.000 byte/ngày
                   ≈ 90 MB/ngày dữ liệu entry thô
~~~

Chưa tính replica, index, backup và dọn dữ liệu. Nếu chỉ một tác giả đã tạo lượng bản sao lớn, kiến trúc phải cân nhắc tác giả nổi tiếng và đường xử lý riêng.

### 21.4. Gợi ý ADR cho bài tập

Ví dụ lựa chọn C — Hybrid, với điều kiện:

- Phần lớn tác giả có ít follower nên fan-out on write làm Q1 rẻ.
- Tác giả có rất nhiều follower được xử lý bằng một đường khác để hạn chế write amplification.
- Chấp nhận độ trễ hiển thị có ngưỡng rõ ràng.
- Có cách hợp nhất feed từ hai nguồn, xử lý bài bị xóa và sự kiện lặp.
- Có metric Q1 p95/p99, backlog, số entry sinh/bài, dung lượng feed, chi phí dọn dữ liệu và tỷ lệ đề xuất stale.

Trong ADR, phải ghi rõ **ngưỡng phân loại tác giả và cơ sở chọn ngưỡng**, thay vì chỉ viết “nổi tiếng thì đọc trực tiếp”. Ngưỡng có thể dựa trên benchmark và giới hạn write throughput của hệ.

---

## 22. Tổng kết

**Ghi lại đánh đổi** là một phần của thiết kế NoSQL theo truy vấn, không phải công việc giấy tờ làm sau triển khai. Một quyết định hữu ích trả lời được:

- **Truy vấn nào được tối ưu?** Filter, sort, limit, SLO và tần suất cụ thể.
- **Đọc thay đổi thế nào?** Số lần truy cập, lượng dữ liệu quét, p95/p99, fan-out và payload.
- **Ghi phải trả giá gì?** Index, bản sao, transaction, retry và write amplification.
- **Lưu trữ tăng hoặc giảm thế nào?** Dữ liệu chính, index, replication, backup, retention và tốc độ tăng trưởng.
- **Độ phức tạp chuyển về đâu?** Đồng bộ, source of truth, stale reads, migration, vận hành và kỹ năng đội ngũ.
- **Có bằng chứng nào?** Số đo, giả định, phép ước lượng, điều kiện thử và mức tin cậy.
- **Khi nào cần xem lại?** SLO xấu đi, workload đổi, chi phí vượt ngân sách hoặc yêu cầu nhất quán thay đổi.

Khi so sánh phương án, hãy **loại những thiết kế vi phạm ràng buộc bắt buộc trước**, rồi dùng ma trận đánh đổi và số liệu để chọn giải pháp có chi phí tổng thể hợp lý. Giữ quyết định trong ADR hoặc nhật ký kỹ thuật có owner, ngày đo, phương án bị loại và tín hiệu xem xét lại để người kế nhiệm có thể điều chỉnh kiến trúc mà không phải đoán lý do ban đầu.

**Thiết kế NoSQL tốt không phải thiết kế không có đánh đổi; đó là thiết kế nhận diện, định lượng, chấp nhận và theo dõi đúng những đánh đổi phục vụ nhu cầu của hệ thống.**
