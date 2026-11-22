# Đánh giá truy vấn hiếm, báo cáo và thao tác quản trị

Khi thiết kế cơ sở dữ liệu NoSQL **theo truy vấn**, nhóm phát triển thường tập trung vào các thao tác xuất hiện hàng nghìn lần mỗi giây: đọc sản phẩm theo ID, lấy giỏ hàng, cập nhật trạng thái đơn hoặc ghi dữ liệu cảm biến. Nhưng một hệ thống thực tế còn có các truy vấn **ít khi chạy**: xuất báo cáo kế toán cuối tháng, kiểm toán thay đổi của một khách hàng, tìm đơn hàng để hỗ trợ khiếu nại, xóa dữ liệu đã hết hạn, sửa dữ liệu sai hoặc xây dựng lại chỉ mục.

Những thao tác này có thể hiếm nhưng **không hề ít quan trọng**. Một truy vấn báo cáo chỉ chạy mỗi ngày một lần vẫn có thể quét hàng chục triệu bản ghi, chiếm phần lớn I/O của cụm hoặc làm chậm checkout. Một tác vụ xóa dữ liệu theo yêu cầu hợp lệ có thể hiếm nhưng không thể bỏ qua. Ngược lại, nếu tạo một chỉ mục tốn kém chỉ để phục vụ một báo cáo chạy mỗi quý, tất cả những lần ghi hằng ngày có thể phải trả thêm chi phí duy trì chỉ mục đó.

Bài học này trình bày cách **phát hiện, phân loại, đánh giá và thiết kế phương án thực thi** cho ba nhóm workload dễ bị xem nhẹ:

1. **Truy vấn hiếm** (*infrequent/ad hoc queries*): tra cứu không thường xuyên, điều tra một trường hợp hoặc bộ lọc mới xuất hiện.
2. **Truy vấn báo cáo/phân tích** (*reporting/analytical queries*): tổng hợp, xuất dữ liệu, đối soát, phân tích lịch sử hoặc tạo số liệu định kỳ.
3. **Thao tác quản trị và bảo trì** (*administrative/maintenance operations*): tìm/sửa/xóa dữ liệu, migration, backfill, reindex, kiểm tra tính toàn vẹn và xử lý sự cố.

Mục tiêu không phải làm mọi truy vấn đều nhanh như đọc theo khóa chính. Mục tiêu là **đáp ứng yêu cầu nghiệp vụ với chi phí chấp nhận được, không gây rủi ro cho đường truy cập quan trọng hơn**.

## 1. “Hiếm” là một đặc tính tải, không phải một mức ưu tiên

Hai truy vấn cùng chạy một lần mỗi tháng nhưng có thể rất khác nhau:

| Trường hợp | Tần suất | Rủi ro khi không đáp ứng | Đặc điểm |
| --- | --- | --- | --- |
| Báo cáo doanh thu để chốt sổ | Hằng tháng | Cao | Cần số liệu đầy đủ, đúng thời hạn và có thể đối soát |
| Tìm một đơn hàng bằng số điện thoại khi có khiếu nại | Khi phát sinh | Trung bình đến cao | Cần kiểm tra quyền, có thể yêu cầu phản hồi trong vài giây |
| Truy vấn khám phá một thuộc tính sản phẩm ít dùng | Không đều | Thấp nếu có phương án khác | Có thể chấp nhận chạy chậm hoặc bất đồng bộ |
| Xóa dữ liệu theo chính sách lưu giữ | Theo lịch hoặc yêu cầu | Cao | Cần xác định phạm vi và bằng chứng hoàn thành |
| Tái tạo search index sau sự cố | Hiếm | Cao | Đọc lượng lớn dữ liệu và tránh phá tải giao dịch |

Vì vậy cần phân biệt ít nhất ba trục:

- **Tần suất:** bao nhiêu lần/giây, ngày, tháng, hoặc chỉ chạy khi sự cố?
- **Tính thiết yếu:** nếu không chạy được, người dùng, vận hành, tài chính hay nghĩa vụ dữ liệu bị ảnh hưởng ra sao?
- **Mức tiêu thụ tài nguyên:** mỗi lần chạy đọc/ghi bao nhiêu dữ liệu, kéo dài bao lâu, cần bao nhiêu CPU, I/O, mạng và bộ nhớ?

Một tác vụ có tần suất gần bằng 0 vẫn có thể cần được thiết kế trước vì khó bổ sung đường truy cập, quyền hoặc cơ chế khôi phục khi hệ thống đã gặp sự cố.

### Ví dụ về quyết định sai khi chỉ nhìn số request

Giả sử một collection có 50 triệu đơn hàng. Chỉ có một yêu cầu “thống kê số đơn theo trạng thái trong năm trước” mỗi đêm. Ta có thể:

1. Tạo nhiều secondary index để truy vấn trực tiếp collection giao dịch.
2. Quét dữ liệu theo lô vào ban đêm với giới hạn tài nguyên.
3. Cập nhật số liệu tổng hợp từng ngày từ sự kiện thay đổi đơn hàng.
4. Đồng bộ dữ liệu sang kho phân tích được thiết kế cho truy vấn quét và tổng hợp.

Phương án nào phù hợp phụ thuộc thời hạn hoàn thành, khả năng chịu tải, dữ liệu cần chính xác đến thời điểm nào, mức thay đổi lịch sử, chi phí duy trì và nhu cầu drill-down. **Không có công thức “hiếm thì scan” hoặc “báo cáo thì luôn tạo index”.**

## 2. Trước tiên, đưa truy vấn hiếm vào danh mục access patterns

Thiết kế theo truy vấn đòi hỏi kiểm kê cả **đường truy cập ít thường xuyên**, không chỉ các endpoint có lưu lượng cao. Một số nguồn nên khảo sát:

- **Đội hỗ trợ khách hàng:** tìm đơn theo email, số điện thoại, mã giao dịch, địa chỉ, khoảng ngày; xem lịch sử đổi trạng thái.
- **Tài chính/kế toán:** doanh thu, hoàn tiền, thuế, hóa đơn, đối soát với cổng thanh toán, xuất dữ liệu kỳ trước.
- **Phân tích sản phẩm:** nhóm theo thời gian, phân khúc, chiến dịch, phân tích cohort, tính các chỉ số.
- **Quản trị hệ thống:** danh sách tenant bất thường, phát hiện bản ghi thiếu trường, cập nhật dữ liệu lỗi, thay đổi chính sách.
- **Bảo mật/kiểm toán:** điều tra quyền truy cập, ghi nhận ai sửa gì và khi nào, xác minh yêu cầu xóa dữ liệu.
- **Kỹ thuật vận hành:** reindex, backfill, migration schema, xác minh dữ liệu nguồn–đích, phục hồi hoặc tạo lại projection.
- **Hệ thống tích hợp:** xuất dữ liệu sang đối tác, nhập lại dữ liệu bị gửi trễ, đồng bộ kho báo cáo.

Mỗi yêu cầu cần được diễn đạt như một **pattern cụ thể**, thay vì ghi một dòng chung chung “admin có thể truy vấn mọi trường”.

### Mẫu mô tả truy vấn

Một thẻ truy vấn hiếm có thể gồm:

~~~yaml
id: FIN-R-07
name: "Monthly paid-order reconciliation"
actor: "Finance batch service"
trigger: "After monthly accounting close"
operation: "Large range read + aggregate/export"
sourceOfTruth: "Order and Payment services"
inputs:
  - tenantId
  - periodStart
  - periodEnd
filters:
  - "tenantId equality"
  - "paidAt in [periodStart, periodEnd)"
  - "payment status in accepted statuses"
sortOrGroupBy:
  - "Business date, currency, payment provider"
result:
  - "Counts, amount totals, discrepancy rows"
frequency: "Once per month, with possible reruns"
deadline: "Agreed finance close time"
consistency: "Defined accounting cut-off and late-adjustment policy"
security: "Finance-authorized, tenant-scoped"
execution: "Scheduled/asynchronous"
retry: "Idempotent output generation"
openQuestions:
  - "Are late refunds attributed to original or refund period?"
  - "Which currency and rounding rules apply?"
~~~

Đây là ví dụ yêu cầu, không phải file cấu hình tự chạy. Điểm quan trọng là nêu rõ **nguồn có thẩm quyền, ngữ nghĩa số liệu, mốc thời gian, độ mới và khả năng chạy lại**; chỉ định một index không giải quyết được những câu hỏi này.

## 3. Phân loại theo nhu cầu nghiệp vụ và hình dạng truy cập

### 3.1. Tra cứu tình huống (*operational lookup*)

Ví dụ nhân viên hỗ trợ cần tìm đơn hàng theo mã đơn hoặc mã thanh toán:

~~~text
LookupOrder(orderId = "O-1042")
LookupOrderByPayment(paymentId = "P-77")
~~~

Hai thao tác khác nhau: truy cập bằng `orderId` có thể là đường đọc chính; truy cập bằng `paymentId` có thể cần secondary index, bảng tra cứu phụ hoặc dịch vụ nguồn thanh toán.

Nếu việc tìm theo `paymentId` chỉ xuất hiện trong vài yêu cầu hỗ trợ mỗi tuần, **vẫn phải quyết định trước** nhân viên có được dùng một công cụ tìm kiếm chậm hơn hay không. Nếu khi có tranh chấp cần trả kết quả trong vài giây, việc quét toàn bộ đơn hàng có thể không phù hợp.

### 3.2. Truy vấn phân tích tổng hợp

Ví dụ:

~~~text
RevenueByDay(tenantId, start, end)
OrdersByRegionAndStatus(period)
ConversionByCampaign(period)
~~~

Những truy vấn này thường:

- Đọc nhiều bản ghi hoặc một khoảng thời gian dài.
- Dùng các phép `COUNT`, `SUM`, `AVG`, `GROUP BY` hoặc tương đương.
- Trả số liệu tổng hợp nhỏ nhưng cần xử lý dữ liệu nguồn lớn.
- Có thể dùng **rollup**, materialized view hoặc kho phân tích.

Một kết quả chỉ có 20 dòng **không có nghĩa chi phí truy vấn thấp**: DBMS có thể phải duyệt hàng triệu bản ghi trước khi tính được 20 dòng đó.

### 3.3. Truy vấn xuất và kiểm toán

Ví dụ:

~~~text
ExportOrders(tenantId, [2026-01-01, 2027-01-01))
FindChanges(entityId, [start, end))
ReconcilePayments(batchDate)
~~~

Các truy vấn này cần **đầy đủ, ổn định và có thể tiếp tục sau lỗi**. Với export, phân trang và điểm tiếp tục quan trọng hơn việc trả tất cả bản ghi trong một request. Với kiểm toán, cần xác định lịch sử có được lưu thật không; index không thể tái tạo bản ghi cũ đã bị ghi đè hoặc xóa.

### 3.4. Truy vấn quản trị có tác dụng ghi

Ví dụ:

~~~text
NormalizeLegacyPhoneNumbers(tenantId)
BackfillMissingCategory(productRange)
MarkExpiredSessions(cutoff)
RebuildSearchProjection(version)
~~~

Đây không phải các `SELECT` chỉ đọc. Chúng có thể sửa nhiều bản ghi, làm phát sinh sự kiện, kích hoạt các hệ thống phụ hoặc gây tranh chấp với ghi online. Cần phân loại riêng **mức độ rủi ro tác động dữ liệu**.

## 4. Ma trận đánh giá: hiếm, nặng, thiết yếu và nhạy cảm

Một ma trận đơn giản giúp tránh kết luận theo tần suất đơn lẻ:

| Kiểu workload | Ví dụ | Hướng xử lý thường đáng xem xét |
| --- | --- | --- |
| **Hiếm, nhẹ, cần phản hồi nhanh** | Tra cứu đơn theo payment ID | Secondary index/bảng ánh xạ trực tiếp nếu chi phí duy trì phù hợp |
| **Hiếm, nặng, có deadline** | Báo cáo tài chính theo tháng | Batch phân trang, pre-aggregation hoặc kho phân tích |
| **Hiếm, nặng, không khẩn cấp** | Điều tra tất cả bản ghi thuộc kiểu schema cũ | Job bất đồng bộ, giới hạn tốc độ và giám sát |
| **Hiếm, rủi ro cao** | Xóa dữ liệu cá nhân theo yêu cầu hợp lệ | Quy trình được kiểm quyền, dry-run, audit, đối soát và xác nhận |
| **Thường xuyên, nhẹ** | Đọc giỏ theo cartId | Đường truy cập chính theo khóa |
| **Thường xuyên, nặng** | Dashboard yêu cầu thống kê nhiều chiều | Dữ liệu dẫn xuất, kho phân tích hoặc thiết kế lại truy vấn |

Đánh giá nên bổ sung **mức độ thay đổi dữ liệu**, **khả năng đưa vào cache**, **phạm vi nhiều tenant**, **chi phí đồng bộ chỉ mục** và **tác động khi thất bại**.

### Câu hỏi kiểm tra trước khi quyết định

1. Khi nào bắt buộc có kết quả: mili giây, vài giây, trong giờ hay trước sáng hôm sau?
2. Đầu vào có xác định **partition key hoặc khóa định danh** không?
3. Truy vấn đọc bao nhiêu bản ghi so với số bản ghi trả về?
4. Có cần xem bản gốc chính xác hay có thể dùng dữ liệu dẫn xuất?
5. Tài liệu/dữ liệu lịch sử có đủ để trả lời sau retention không?
6. Có được phép thực thi trên cụm đang phục vụ giao dịch không?
7. Nếu query/job thất bại giữa chừng, chạy lại có an toàn không?
8. Những ai được phép thực hiện và xem kết quả?

Từ câu trả lời, mới chọn chỉ mục, mô hình dữ liệu hoặc cách tách workload.

## 5. Vì sao một truy vấn hiếm vẫn có thể phá hiệu năng online?

Một request lấy hàng chục triệu bản ghi có thể chiếm I/O, CPU và bộ nhớ trong nhiều phút. Khi dùng chung cụm phục vụ checkout, tác động có thể là:

- **Cache bị đẩy dữ liệu nóng ra ngoài**, khiến request bình thường phải đọc dữ liệu từ đĩa nhiều hơn.
- **Compaction và ghi online cạnh tranh I/O** với các truy vấn scan.
- **Coordinator/worker xử lý quá nhiều partition**, làm hàng đợi và latency tăng.
- **Network traffic tăng**, đặc biệt nếu kéo dữ liệu lớn về ứng dụng để tổng hợp.
- **Garbage collection hoặc cấp phát bộ nhớ lớn** tăng chi phí cho các request khác.
- **Giao dịch cập nhật kéo dài** nếu job ghi hàng loạt hoặc giữ khóa theo cơ chế DBMS.
- **Tạo index trên tập dữ liệu lớn** có thể tạo tải nền đáng kể, ngay cả khi truy vấn sau này ít chạy.

Vì vậy không nên chấp nhận một truy vấn chỉ vì “mỗi ngày chạy đúng một lần”.

### Mô hình chi phí trực giác

Giả sử một collection có **20 triệu đơn hàng**, truy vấn quản trị trả về **1.000 đơn** nhưng phải kiểm tra toàn bộ collection do không có đường truy cập phù hợp.

~~~text
Rows scanned   ≈ 20.000.000
Rows returned  =      1.000
Scan / return  ≈     20.000
~~~

Một tỉ lệ quét/trả về cao là tín hiệu cần xem xét. Nhưng nó **không tự chứng minh index mới sẽ tốt hơn**: nếu toàn bộ job đọc tuần tự một lần vào ban đêm, scan có giới hạn và cô lập có thể hợp lý. Nếu cùng truy vấn cần phản hồi cho nhân viên hỗ trợ trong 2 giây, đường truy cập khác có thể cần thiết.

Chi phí không chỉ là số dòng quét: kích thước tài liệu, điều kiện lọc, nén, chỉ mục, độ trễ mạng, số partition và mức cạnh tranh đều ảnh hưởng.

## 6. Có nên tạo secondary index cho truy vấn ít chạy?

**Chỉ mục phụ** thường tăng tốc một đường đọc nhưng tạo thêm chi phí trên mỗi lần ghi hoặc cập nhật thuộc tính được lập chỉ mục. Với một truy vấn hiếm, cần cân bằng **lợi ích đọc** và **chi phí duy trì thường trực**.

Ví dụ:

~~~text
Collection products:
  5.000.000 tài liệu
  10.000 updates/giờ vào các trường sản phẩm

Admin query:
  Một lần/tháng tìm sản phẩm theo trường deprecatedField
~~~

Nếu tạo index cho `deprecatedField`, nó có thể tồn tại suốt tháng và cần bảo trì cùng dữ liệu, dù chỉ được sử dụng trong một vài phút.

### Những tiêu chí ra quyết định

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
| --- | --- | --- |
| Truy vấn cần tương tác nhanh? | Nhân viên phải thao tác trực tiếp, chờ vài giây | Index/read model có thể đáng giá |
| Truy vấn quan trọng khi sự cố? | Cần điều tra nhanh để phục hồi dịch vụ | Không thể chỉ dựa vào scan có thể kéo dài hàng giờ |
| Trường lọc có độ chọn lọc cao? | Chỉ vài bản ghi khớp trong hàng triệu | Index có cơ hội giảm đọc mạnh |
| Thuộc tính được cập nhật thường xuyên? | Có nhiều lần cập nhật mỗi giây | Index có chi phí ghi lớn hơn |
| Dữ liệu ngày càng tăng? | Scan hôm nay 5 phút, năm sau nhiều giờ | Cần đánh giá quy mô tương lai |
| Có thể chuyển sang batch/analytics? | Không yêu cầu trả về tức thời | Tránh thêm index giao dịch nếu không cần |
| Index có giới hạn theo phân vùng? | Truy vấn thiếu partition key | Cần hiểu fan-out và khả năng index thực tế |

Kết luận cần dựa trên **workload tổng thể**. Một index rất hữu ích cho truy vấn hiếm nhưng thiết yếu có thể hợp lý. Một index chỉ để tiện cho query thử nghiệm có thể không đáng.

### Ví dụ MongoDB: truy vấn theo payment reference

Giả sử nhân viên cần tìm đơn theo mã tham chiếu thanh toán:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  paymentReference: 1
});

db.orders.find({
  tenantId: "T17",
  paymentReference: "PAY-8821"
}, {
  _id: 1,
  orderId: 1,
  status: 1,
  paymentReference: 1
}).limit(10);
~~~

Index trên `tenantId + paymentReference` có thể hỗ trợ lookup này và gắn phạm vi tenant với truy vấn. Nhưng trước khi tạo trong hệ thật, cần biết liệu `paymentReference` có duy nhất trong tenant hay không, có thể thiếu/null không, có thay đổi theo thời gian không và các yêu cầu uniqueness thực tế.

Với MongoDB có thể xem kế hoạch truy vấn đọc:

~~~javascript
db.orders.find({
  tenantId: "T17",
  paymentReference: "PAY-8821"
}).explain("executionStats");
~~~

`executionStats` có thể cho biết số tài liệu/key được xem xét và thời gian thực thi trong điều kiện cụ thể. **Kế hoạch truy vấn hiện tại không phải bảo đảm hiệu năng cho mọi dữ liệu, phiên bản hoặc mức tải**. Tạo index cũng có chi phí xây dựng, dung lượng và ghi; cần quản lý như một thay đổi hệ thống.

## 7. Truy vấn hiếm trong wide-column: không có partition key thì sao?

Trong Cassandra và những cách tổ chức wide-column hướng truy vấn, một bảng thường được tối ưu cho việc biết **partition key** và đọc theo **clustering columns**. Ví dụ:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    bucket_month text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, bucket_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Bảng này phục vụ câu hỏi:

> “Lấy các đơn hàng mới nhất của khách hàng C42 trong tháng 11.”

Nhưng nhân viên quản trị đôi khi muốn:

> “Tìm tất cả đơn hàng trạng thái FAILED trong ngày 14/11 của tenant T17.”

Truy vấn này không biết `customer_id`. Không thể mặc định DBMS tìm hiệu quả trên mọi partition chỉ nhờ có cột `status`. Dùng `ALLOW FILTERING` như một cách né thiết kế có thể dẫn tới quét rộng và độ trễ khó dự đoán khi dữ liệu lớn.

Các lựa chọn thường cần xem xét:

1. **Bảng đọc theo trạng thái/ngày/tenant** với partition key phù hợp và bucket giới hạn kích thước.
2. **Secondary indexing** theo khả năng thực tế của Cassandra phiên bản được triển khai, với đánh đổi phân tán và tải.
3. **Kho tìm kiếm/analytics** cho các điều kiện lọc linh hoạt và báo cáo.
4. **Batch scan có kiểm soát** khi truy vấn thật sự ít, dữ liệu có thể xử lý ngoài đường online.

Ví dụ một read model chuyên cho admin:

~~~text
orders_by_tenant_status_day
  partition key: (tenant_id, status, day_bucket[, optional shard])
  clustering: created_at, order_id
  query: Find orders of status X in one day
~~~

Đây là **phác thảo**, không phải bảng hoàn chỉnh. Trong triển khai, cần kiểm soát kích thước/hotness của partition, trạng thái thay đổi, fan-out qua bucket hoặc shard và nhất quán với đơn hàng nguồn. Khi trạng thái đơn chuyển từ `FAILED` sang `RETRIED`, bảng đọc phải cập nhật hoặc xóa mục cũ theo quy tắc, tránh kết quả quản trị bị sai.

### Không nhân bản toàn bộ dữ liệu chỉ vì một query hiếm

Một bảng mới tạo thêm ghi, lưu trữ, rủi ro đồng bộ và xử lý lỗi. Nếu truy vấn trạng thái FAILED chỉ chạy mỗi quý và không cần tương tác nhanh, một job phân tích theo ngày có thể đáng cân nhắc hơn. Nếu nhân viên hỗ trợ dùng nó mỗi khi có sự cố thanh toán, mức ưu tiên và thời hạn phản hồi có thể khiến việc chuẩn bị đường truy cập chuyên dụng hợp lý.

## 8. Báo cáo khác truy vấn giao dịch ở đâu?

**OLTP** (*online transaction processing*) và **OLAP** (*online analytical processing*) là hai kiểu workload; không phải hai nhãn tuyệt đối cho mọi DBMS.

| Khía cạnh | Truy vấn giao dịch/OLTP | Báo cáo/phân tích/OLAP |
| --- | --- | --- |
| Câu hỏi | “Đơn O-1042 hiện trạng thái gì?” | “Doanh thu theo ngày, shop, kênh trong quý?” |
| Tập dữ liệu đọc | Thường một hoặc ít bản ghi | Có thể hàng triệu bản ghi |
| Thao tác | Point read, cập nhật có điều kiện, giao dịch | Scan, filter, group, join/aggregate |
| Yêu cầu độ trễ | Thường cần thấp, đồng bộ | Có thể batch hoặc tương tác, tùy nghiệp vụ |
| Tính mới | Có thể cần đọc sau ghi hoặc nguồn có thẩm quyền | Có thể chấp nhận lag; cần định nghĩa rõ |
| Tối ưu lưu trữ | Theo khóa, partition, cập nhật | Quét theo cột, nén, partition pruning, materialization |
| Rủi ro chính | Vi phạm bất biến, tranh chấp ghi | Tốn tài nguyên, số liệu lệch, quét rộng |

Điều này giải thích vì sao một DBMS tối ưu đọc trạng thái đơn theo khóa có thể không phải nơi tốt nhất để chạy mọi báo cáo tổng hợp.

### Ví dụ báo cáo doanh thu theo ngày

Một báo cáo có thể được biểu diễn bằng SQL minh họa:

~~~sql
SELECT CAST(paid_at AS DATE) AS business_date,
       currency,
       COUNT(*) AS paid_order_count,
       SUM(paid_amount) AS paid_total
FROM payments
WHERE tenant_id = 'T17'
  AND paid_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND paid_at <  TIMESTAMP '2026-12-01 00:00:00'
  AND status = 'SUCCEEDED'
GROUP BY CAST(paid_at AS DATE), currency
ORDER BY business_date, currency;
~~~

Đây là **kiểu truy vấn báo cáo**, không phải bảo đảm rằng mọi NoSQL DBMS có thể chạy SQL trên hoặc có cùng khả năng `GROUP BY`. Thực tế phải xác định:

- `paid_at` là mốc thanh toán thành công hay mốc tạo payment?
- Ngày báo cáo theo UTC hay timezone kế toán?
- `paid_amount` là đơn vị nhỏ nhất, decimal hay giá trị đã làm tròn?
- Đơn bị refund được trừ ở ngày thanh toán hay ngày refund?
- Callback thanh toán lặp có bị đếm hai lần không?
- Có những khoản thanh toán đến trễ hoặc được điều chỉnh sau khi báo cáo chốt không?
- Kết quả có cần trạng thái cố định tại một cut-off đã công bố không?

Một báo cáo chạy nhanh nhưng sai các quy tắc này **không đạt yêu cầu**. Chọn kho phân tích và index chỉ là một phần của lời giải.

## 9. Năm phương án phục vụ báo cáo

### Phương án A — Truy vấn trực tiếp nguồn giao dịch

**Phù hợp khi:** dữ liệu nhỏ, báo cáo nhẹ, tần suất thấp, DBMS có hỗ trợ và tải online chấp nhận được.

**Ưu điểm:** ít thành phần, đọc dữ liệu nguồn ngay, không có pipeline đồng bộ báo cáo riêng.

**Nhược điểm:** báo cáo lớn có thể tranh chấp tài nguyên với giao dịch, chi phí tăng theo dữ liệu; khả năng tính tổng hợp tùy DBMS.

### Phương án B — Job batch theo trang hoặc phân vùng

**Phù hợp khi:** báo cáo không cần đồng bộ trong request, có lịch chạy rõ và có thể xử lý dữ liệu lớn theo đợt.

**Ưu điểm:** kiểm soát tốc độ, checkpoint, retry và lên lịch ngoài cao điểm.

**Nhược điểm:** kết quả không cập nhật tức thời, cần xử lý thiếu/trùng khi retry, dữ liệu thay đổi lúc batch đang đọc.

### Phương án C — Bảng tổng hợp/materialized view

**Phù hợp khi:** cùng chỉ số được đọc nhiều lần, phép tổng hợp ổn định và biết cách cập nhật.

~~~text
OrderPaid / OrderRefunded events
            │
            ▼
    Projection consumer
            │
            ▼
 daily_revenue_by_tenant
   (tenant_id, business_date, currency)
            │
            ▼
      Dashboard / Report
~~~

**Ưu điểm:** đọc báo cáo nhanh, tránh quét nguồn chi tiết mỗi lần.

**Nhược điểm:** phải quản lý trùng sự kiện, sự kiện đến trễ, hoàn tiền, thay đổi quy tắc tổng hợp, lag và rebuild. Không được coi projection cập nhật bất đồng bộ là nguồn giao dịch chính nếu nghiệp vụ không cho phép.

### Phương án D — Đồng bộ sang kho phân tích chuyên dụng

**Phù hợp khi:** nhiều truy vấn quét, tổng hợp nhiều chiều, dataset lớn, phân tích linh hoạt hoặc nhu cầu dùng dữ liệu lịch sử rộng.

Hệ thống có thể đưa dữ liệu qua CDC, event stream hoặc batch export sang kho phân tích được tối ưu cho loại truy vấn đó.

**Ưu điểm:** tách tác vụ phân tích khỏi đường giao dịch, hỗ trợ công cụ phân tích và mở rộng độc lập.

**Nhược điểm:** thêm pipeline, độ trễ, chi phí lưu trữ, quản lý schema, quyền, dữ liệu nhạy cảm và kiểm tra đối soát nguồn–đích.

### Phương án E — Xuất snapshot rồi phân tích offline

**Phù hợp khi:** yêu cầu rất hiếm, có thể chấp nhận kết quả sau thời gian dài hơn, không cần lập hạ tầng phân tích thường trực.

Ví dụ, định kỳ xuất dữ liệu một khoảng thời gian ra định dạng phù hợp, ghi lại mốc snapshot và cho công cụ phân tích xử lý file xuất trong môi trường được kiểm soát.

**Nhược điểm:** snapshot có thể cũ, phải quản lý dữ liệu cá nhân/nhạy cảm, độ đầy đủ, thời gian tồn tại file xuất và việc xóa sau sử dụng.

| Tiêu chí | Trực tiếp | Batch | Rollup | Kho phân tích | Export offline |
| --- | --- | --- | --- | --- | --- |
| Số thành phần | Thấp | Trung bình | Trung bình | Cao hơn | Tùy quy trình |
| Tải lên DB nguồn | Có thể cao | Có thể giới hạn | Ghi/cập nhật projection | Theo pipeline đồng bộ | Cao trong lúc xuất |
| Độ mới | Theo dữ liệu nguồn | Theo đợt chạy | Theo tiến độ cập nhật | Theo lag pipeline | Theo snapshot |
| Truy vấn linh hoạt | Theo DBMS nguồn | Theo logic job | Theo chiều đã tổng hợp | Thường phù hợp hơn | Theo công cụ offline |
| Vận hành | Đơn giản ban đầu | Cần checkpoint/retry | Cần đối soát/rebuild | Cần vận hành pipeline và quyền | Cần quản lý file và bảo mật |

## 10. Báo cáo cần tính đúng theo thời gian, không chỉ đúng theo key

Những trường thời gian thường gặp:

- **Event time:** thời điểm nghiệp vụ thực sự xảy ra.
- **Ingestion time:** thời điểm hệ thống nhận được dữ liệu.
- **Processing time:** thời điểm job xử lý.
- **Business date:** ngày nghiệp vụ dùng để ghi nhận, có thể khác ngày UTC.
- **Cut-off/watermark:** giới hạn dữ liệu được coi là đã xử lý hoặc được chốt theo một chính sách.

Giả sử giao dịch thanh toán thành công lúc 23:55 ngày 30/11, nhưng sự kiện `PaymentSucceeded` được consumer xử lý vào 00:10 ngày 01/12:

~~~text
Event time:      2026-11-30T23:55:00Z
Processing time: 2026-12-01T00:10:00Z
~~~

Nếu báo cáo dựa theo **event time**, giao dịch có thể thuộc ngày 30/11; nếu dựa theo **processing time**, có thể xuất hiện trong ngày 01/12. Không có một lựa chọn đúng cho mọi nghiệp vụ; báo cáo phải nêu rõ quy tắc và xử lý dữ liệu đến trễ.

### Đối soát dữ liệu nguồn với báo cáo

Một projection tổng hợp có thể có lỗi do:

- Consumer xử lý một sự kiện hai lần.
- Sự kiện bị bỏ sót trong một khoảng downtime.
- Một khoản hoàn tiền đến sau báo cáo.
- Schema thay đổi làm pipeline hiểu sai một trường.
- Job backfill chạy lại và cộng số liệu thêm lần nữa.

Để quản lý, cần thiết kế:

1. **Event ID hoặc khóa nghiệp vụ chống trùng** theo phạm vi cần thiết.
2. **Mốc tiến độ xử lý** (offset, checkpoint, watermark) có ý nghĩa rõ.
3. **Quy tắc cập nhật/recompute** khi nguồn thay đổi.
4. **Đối soát định kỳ** số lượng và tổng tiền giữa nguồn với kết quả, theo đúng cut-off.
5. **Khả năng rebuild** projection từ nguồn có đủ retention.

“Eventual consistency” không có nghĩa cho phép số tiền tổng sai vĩnh viễn. Nó chỉ thừa nhận có khoảng trễ; hệ thống vẫn cần đảm bảo quy tắc hội tụ, phát hiện và sửa sai theo yêu cầu.

## 11. Export dữ liệu lớn: phân trang, checkpoint và tính nhất quán

Một tác vụ xuất hàng triệu bản ghi **không nên** tải toàn bộ kết quả vào RAM hay trả tất cả trong một HTTP response đồng bộ. Cần thiết kế như một **job có trạng thái**.

~~~text
Admin yêu cầu export
          │
          ▼
Xác thực quyền, kiểm tra phạm vi tenant
          │
          ▼
Tạo export job + thời điểm/cut-off
          │
          ▼
Worker đọc dữ liệu theo trang/bucket
          │
          ├── Ghi chunk đầu ra
          ├── Lưu checkpoint
          ├── Giới hạn tài nguyên
          └── Retry khi lỗi
          │
          ▼
Đối chiếu số bản ghi, trạng thái job
          │
          ▼
Trả kết quả qua kênh kiểm soát quyền
          │
          ▼
Xóa file tạm khi hết hạn
~~~

### Pagination phù hợp để xuất dữ liệu

Cần một thứ tự xác định, ví dụ theo `(createdAt, orderId)`, và một cursor hoặc cách đọc theo partition/bucket có thể tiếp tục sau lỗi.

~~~text
Input:
  tenantId = T17
  createdAt in [start, end)
  jobCutoff = time or snapshot identifier

Checkpoint:
  lastCreatedAt
  lastOrderId
  processedCount
  outputChunkNumber

Each batch:
  Read next N rows
  Write one output chunk safely
  Persist checkpoint after successful chunk write
~~~

Đây là **pseudocode thiết kế**, không phải thuật toán bảo đảm snapshot trên mọi DBMS.

Nếu bản ghi có thể được chèn hoặc sửa trong lúc export:

- Cursor theo sort key giúp tiếp tục hiệu quả, nhưng không tự bảo đảm một snapshot bất biến.
- Một giá trị cut-off đơn giản chỉ giới hạn thời gian của dữ liệu nếu các quy tắc ghi bảo đảm nó có ý nghĩa.
- Snapshot/transaction đọc nhất quán, versioned data hoặc cơ chế đóng băng dataset có thể cần cho export nghiêm ngặt.
- Batch có thể chạy lại; output nên có ID job và quy tắc ghi chunk idempotent để không nhân đôi dòng.

Một export về tài chính cần biết **“dữ liệu được chốt tại thời điểm nào”** và phương án đối phó với cập nhật muộn. Điều đó quan trọng không kém index.

### Ví dụ MongoDB: đọc theo khoảng được phân trang

Minh họa cú pháp trong môi trường có tập `orders` và chỉ mục phù hợp với mẫu lọc/sắp xếp:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: 1,
  _id: 1
});

const cursor = db.orders.find(
  {
    tenantId: "T17",
    createdAt: {
      $gte: ISODate("2026-11-01T00:00:00Z"),
      $lt: ISODate("2026-12-01T00:00:00Z")
    }
  },
  {
    _id: 1,
    orderId: 1,
    createdAt: 1,
    status: 1,
    totalVnd: 1
  }
).sort({ createdAt: 1, _id: 1 }).batchSize(500);

while (cursor.hasNext()) {
  const order = cursor.next();
  // Ghi một dòng vào output có checkpoint ở tầng job.
  // Không giữ toàn bộ các đơn trong một mảng bộ nhớ.
}
~~~

`batchSize` giúp điều chỉnh cách driver/shell nhận từng lô kết quả, **không tự tạo checkpoint bền vững**, không bảo đảm query chạy đúng một lần và không thay thế pagination trên API. Với dữ liệu lớn, việc duy trì một cursor mở lâu có giới hạn vận hành; job thực tế có thể cần phân chia dải khóa hoặc truy vấn theo trang, mỗi trang ghi checkpoint riêng.

Mẫu trên cố ý không chạy lệnh xuất dữ liệu nhạy cảm hay thao tác xóa. Trong hệ thật, đầu ra cần kiểm soát truy cập, mã hóa, retention và audit thích hợp.

## 12. Tách truy vấn báo cáo khỏi tải online bằng những cách nào?

Không phải mọi dự án đều cần một cụm analytics riêng. Có thể chọn mức tách theo độ lớn và yêu cầu:

1. **Lên lịch ngoài cao điểm:** đơn giản nhất, nhưng không có bảo đảm khi traffic thực tế tăng hoặc khi chạy nhiều job.
2. **Giới hạn số job đồng thời và tốc độ đọc:** giảm nguy cơ chiếm tài nguyên, đổi lại hoàn thành chậm hơn.
3. **Chạy trên bản sao đọc** khi DBMS và topology hỗ trợ, với hiểu biết về replication lag và tác động lên hạ tầng.
4. **Dùng bảng/projection phục vụ báo cáo:** giảm đọc nguồn, tăng công việc đồng bộ.
5. **Đẩy dữ liệu sang kho analytics:** tách đường OLTP và OLAP rõ hơn.
6. **Xuất snapshot ra hệ thống offline** khi truy vấn rất hiếm và không cần phản hồi nhanh.

### Bản sao đọc có phải miễn phí?

Không. Bản sao vẫn cần nhận thay đổi và tiêu tốn CPU, I/O, mạng, bộ nhớ và dung lượng. Một truy vấn scan dài có thể tăng lag hoặc tranh chấp tài nguyên trên replica. Trong hệ phân tán có các mức nhất quán khác nhau, kết quả từ replica có thể chậm hơn nguồn chính.

**Tách nơi chạy** chỉ là một phần. Cần quy định **độ cũ chấp nhận được**, độ ưu tiên khi tài nguyên thiếu và cách tránh báo cáo làm hỏng mục tiêu phục vụ người dùng.

### Gợi ý điều khiển job

~~~text
Job policy:
  concurrency: maximum 2 report jobs per tenant (illustrative)
  batchSize: bounded and configurable
  rateLimit: adjust by observed system load
  timeout: finite, with safe resume
  checkpoint: persisted after committed output chunk
  retry: bounded with backoff
  scheduling: outside peak when possible
  cancellation: supported and audited
  observability: rows scanned, rows written, lag, error
~~~

Các giá trị là ví dụ, không phải giới hạn được khuyến nghị chung cho mọi hệ. Hạn mức thực tế phải xác định bằng kiểm thử và số liệu vận hành.

## 13. Thao tác quản trị: phân biệt đọc để quan sát với ghi để thay đổi

Một tác vụ admin có thể chỉ đọc một bản ghi, nhưng cũng có thể sửa toàn bộ dữ liệu của tenant. Vì thế nên phân loại theo **mức tác động**:

| Loại | Ví dụ | Rủi ro chính |
| --- | --- | --- |
| **Quan sát chỉ đọc** | Tìm bản ghi sai schema, kiểm tra trạng thái | Truy vấn quá rộng, lộ dữ liệu |
| **Điều tra/đối soát** | So nguồn–đích, tìm payment thiếu order | Dữ liệu chưa đồng bộ, false positive |
| **Sửa một thực thể** | Sửa trạng thái đơn có phê duyệt | Sai quy tắc nghiệp vụ, thiếu audit |
| **Sửa hàng loạt** | Chuẩn hóa mã vùng điện thoại | Ghi đè thay đổi mới, sai phạm vi tenant |
| **Migration** | Chuyển từ schema v1 sang v2 | Client cũ không đọc được, cập nhật đồng thời |
| **Rebuild dữ liệu dẫn xuất** | Xây lại search index | Double-write, lag, kết quả thiếu trong lúc đổi |
| **Xóa/retention** | Xóa session, xóa dữ liệu theo yêu cầu | Xóa quá rộng, còn dữ liệu trong backup/index |
| **Phục hồi** | Khôi phục từ bản sao/backup | Mất thay đổi mới, tính nhất quán sau khôi phục |

**Một tác vụ chạy ít lần không được phép bỏ qua tính an toàn.** Trái lại, vì ít chạy, nó có thể ít được thực tế kiểm chứng hơn thao tác hằng ngày.

### Quy trình quản trị an toàn

Một quy trình phù hợp với các tác vụ có tác dụng ghi:

~~~text
1. Xác định ticket, mục đích, người yêu cầu và người phê duyệt (nếu cần).
2. Xác thực người thực hiện, phạm vi tenant/tài nguyên.
3. Mô tả điều kiện chọn bản ghi và điều kiện tiền kiểm.
4. Dry-run/preview: kiểm tra count + sample + phạm vi tác động.
5. Tạo backup/snapshot hoặc phương án khôi phục khi phù hợp.
6. Thực thi theo batch có giới hạn, với điều kiện ghi an toàn.
7. Ghi audit: ai, khi nào, vì sao, đã thay đổi bao nhiêu.
8. Đối soát số lượng và trạng thái sau khi chạy.
9. Ghi nhận lỗi, phần còn dang dở, checkpoint và cách retry.
10. Kết thúc job sau khi đủ bằng chứng hoàn thành.
~~~

**Dry-run không tự bảo đảm an toàn** nếu dữ liệu thay đổi giữa lúc xem trước và lúc thực thi. Cần đánh giá concurrency, khóa/phiên bản, ranh giới giao dịch và điều kiện ghi ở thời điểm thực hiện.

## 14. Ví dụ quản trị: cập nhật tài liệu cũ có điều kiện

Giả sử một số sản phẩm MongoDB còn trường `schemaVersion = 1` với giá dưới `priceVnd`. Ứng dụng mới sử dụng:

~~~json
{
  "schemaVersion": 2,
  "price": {
    "amount": 150000,
    "currency": "VND"
  }
}
~~~

Ta cần chuyển dữ liệu nhưng không được ghi đè một bản ghi vừa được nhân viên cập nhật trong lúc batch đang chạy.

### Trước tiên: quan sát và giới hạn đúng tập

~~~javascript
db.products.countDocuments({
  tenantId: "T17",
  schemaVersion: 1,
  priceVnd: { $type: "number" }
});

db.products.find({
  tenantId: "T17",
  schemaVersion: 1
}, {
  _id: 1,
  schemaVersion: 1,
  priceVnd: 1,
  revision: 1
}).limit(20);
~~~

Mục tiêu là xác định số lượng và các trường hợp ngoại lệ: dữ liệu thiếu giá, giá âm không hợp lệ, chuỗi thay vì số, hoặc các phiên bản khác nhau. Không nên tự gán giá `0` khi không đọc được chỉ để job “chạy hết”.

### Tiếp theo: cập nhật từng bản ghi có điều kiện

Pseudocode:

~~~text
For each eligible product:
  Read product with _id, tenantId, schemaVersion, revision, priceVnd
  Validate priceVnd and business rules
  Compute new price object
  Update only if:
       _id matches
       tenantId matches
       schemaVersion is still 1
       revision is still the expected revision
  Set new price and schemaVersion = 2
  Increment revision
  Record outcome and checkpoint
~~~

Trong MongoDB, một lệnh cập nhật trên một document có thể minh họa:

~~~javascript
db.products.updateOne(
  {
    _id: "P-1001",
    tenantId: "T17",
    schemaVersion: 1,
    revision: 7,
    priceVnd: 150000
  },
  {
    $set: {
      price: { amount: 150000, currency: "VND" },
      schemaVersion: 2
    },
    $inc: {
      revision: 1
    },
    $unset: {
      priceVnd: ""
    }
  }
);
~~~

**Đây là ví dụ với giá trị cố định**, không phải script migration chạy trên toàn bộ dữ liệu. Ứng dụng phải lấy `priceVnd` từ từng tài liệu và validate trước khi tạo lệnh. `matchedCount = 0` có thể nghĩa bản ghi không còn đúng trạng thái dự kiến, đã đổi phiên bản, bị xóa hoặc có dữ liệu khác; cần ghi nhận để xử lý, không tự coi là thành công.

Nếu hệ thống còn reader v1, việc `$unset priceVnd` ngay có thể làm chúng lỗi. Quy trình triển khai thường cần reader hiểu v1/v2, chuyển writer, backfill rồi mới bỏ hỗ trợ trường cũ.

### Vì sao không mặc định chạy một lệnh update toàn bộ?

Một lệnh mass update khó kiểm soát từng lỗi dữ liệu, có thể tạo tải ghi lớn và thiếu checkpoint theo từng batch. Với migration nhiều triệu bản ghi, cần xét:

- Giới hạn throughput.
- Tiến độ để tiếp tục sau khi job dừng.
- Xử lý xung đột với ghi online.
- Cách phát hiện và sửa tài liệu không hợp lệ.
- Khả năng rollback bằng dữ liệu đã chuẩn bị.
- Tác động tới secondary index, CDC và consumers.

Điều này không có nghĩa mọi update hàng loạt đều xấu; các tác vụ nhỏ và được kiểm soát có thể dùng API bulk/update phù hợp. Quan trọng là **độ an toàn và khả năng vận hành đã được đánh giá trước khi chạy**.

## 15. Xóa dữ liệu và retention là access pattern riêng

Hệ thống có thể lưu session 30 phút, log kỹ thuật 30 ngày, đơn hàng theo thời hạn nghiệp vụ hoặc báo cáo dài hạn. Những cơ chế dọn dữ liệu này cần được thiết kế từ đầu.

### TTL không đồng nghĩa với “xóa mọi bản sao”

Một DBMS có thể hỗ trợ TTL để bản ghi tự hết hạn theo thời gian. Nhưng dữ liệu có thể còn tồn tại ở:

- Bản sao đọc/replica theo cơ chế hệ quản trị.
- Search index, cache hoặc read model dẫn xuất.
- Pipeline sự kiện và kho phân tích.
- Snapshot, bản sao lưu và hệ thống lưu trữ xuất file.

Vì vậy, một yêu cầu “xóa dữ liệu người dùng” **không thể mặc định chỉ cần DELETE một document**. Cần có sơ đồ dòng dữ liệu, phạm vi quyền và chính sách lưu giữ/xóa phù hợp, kể cả với dữ liệu dẫn xuất và backup.

### Xóa dữ liệu trong wide-column có chi phí riêng

Ở những hệ như Cassandra, delete/TTL thường liên quan đến **tombstone** và cơ chế compaction, chứ không nhất thiết giải phóng dung lượng vật lý ngay lập tức. Quét qua nhiều tombstone có thể làm truy vấn kém hiệu quả nếu chính sách lưu giữ, cách phân vùng và compaction không phù hợp.

Nếu dữ liệu được chia **bucket theo thời gian**, có thể dễ xác định phạm vi lịch sử cần xử lý hơn, nhưng bản thân bucket **không tự xóa dữ liệu**. Cơ chế xóa thực tế, khôi phục và bảo đảm retention phụ thuộc DBMS và cấu hình.

### Việc xóa cần có truy vấn xác định đối tượng

Ví dụ tác vụ xóa toàn bộ dữ liệu của tenant phải biết cách định vị:

~~~text
Authoritative store: orders, customers, addresses
Derived stores: search index, cached read models
Event/log systems: subject to retention and legal policy
Backups: deletion/expiration policy as applicable
Exports: previously generated files and access paths
~~~

Truy vấn tìm tất cả bản ghi thuộc tenant có thể là **một access pattern quan trọng**, dù chưa từng xuất hiện trong màn hình người dùng. Nếu thiết kế ban đầu không cho phép xác định dữ liệu theo tenant, thao tác quản trị và xóa dữ liệu có thể rất khó thực hiện an toàn.

## 16. Reindex và backfill: đọc nhiều, ghi nhiều, có thể chạy lại

Một thao tác **xây lại search index** thường gồm:

~~~text
Nguồn có thẩm quyền
       │
       ├── Đọc snapshot/danh sách dữ liệu ban đầu
       │          │
       │          ▼
       │    Lập chỉ mục mới
       │
       └── Nhận thay đổi phát sinh trong lúc backfill
                  │
                  ▼
          Bắt kịp dữ liệu mới
                  │
                  ▼
          Đối soát và chuyển reader
~~~

Những câu hỏi cần trả lời:

1. Job đọc dữ liệu theo thứ tự gì để có thể checkpoint?
2. Khi một tài liệu bị cập nhật **sau snapshot nhưng trước khi index xong**, có nguy cơ index ghi giá trị cũ đè giá trị mới không?
3. Có định danh/phiên bản bản ghi để xử lý lại idempotent không?
4. Khi index xây xong, làm sao xác nhận dữ liệu đã bắt kịp thay đổi?
5. Có thể chuyển reader sang index mới theo cách kiểm soát được và quay lại khi lỗi không?
6. Job có làm chậm đường đọc/ghi online không?

**Không nên** chỉ đọc tất cả dữ liệu rồi công bố index hoàn thành ngay nếu hệ thống nguồn liên tục có cập nhật. Cần một cơ chế đồng bộ trong thời gian backfill, chẳng hạn CDC, event log hoặc giao thức versioned writes phù hợp.

Một yêu cầu khôi phục index hiếm khi chạy vẫn cần mô tả trong access-pattern inventory vì nó tác động mạnh đến partition scan, throughput và tính nhất quán giữa các kho.

## 17. Truy vấn quản trị phải được kiểm soát quyền và phạm vi

Quyền của nhân viên hỗ trợ, kế toán, quản trị dữ liệu và dịch vụ batch nên khác nhau. Một tài khoản có khả năng truy vấn tất cả dữ liệu của mọi tenant chỉ để xử lý vài trường hợp hiếm sẽ tạo rủi ro lớn.

Các nguyên tắc cần cân nhắc:

- **Quyền tối thiểu:** tài khoản chỉ đọc khi chỉ cần đọc; cập nhật/xóa dùng vai trò riêng và phạm vi hạn chế.
- **Giới hạn theo tenant và mục đích:** không dựa duy nhất vào prefix khóa hoặc tham số do client gửi.
- **Không xuất thông tin nhạy cảm không cần thiết:** ẩn hoặc loại bỏ trường mà tác vụ không cần.
- **Audit:** lưu ai chạy tác vụ, lúc nào, phạm vi dữ liệu, kết quả, lý do và phê duyệt nếu yêu cầu.
- **Hạn mức:** giới hạn số dòng, tốc độ, thời gian chạy, số job đồng thời, dung lượng xuất.
- **Bảo vệ dữ liệu xuất:** nơi lưu, mã hóa, quyền truy cập, thời gian giữ và cách xóa file tạm.
- **Tách môi trường:** công cụ thử nghiệm hoặc script debug không nên mặc định có quyền production.

Khi một công cụ admin cho phép nhập điều kiện lọc, phải **kiểm soát các trường/toán tử được phép** và sử dụng tham số hóa theo API của DBMS. Không ghép truy vấn tùy ý từ dữ liệu nhập, không mở một endpoint cho phép thực thi trực tiếp query ngẫu nhiên với quyền quản trị.

### Ví dụ về hai thao tác cùng tên nhưng quyền khác nhau

~~~text
Customer:
  GetOrder(orderId)
  Scope: own orders within authenticated tenant

SupportAgent:
  FindOrdersByContact(phoneNumber, dateRange)
  Scope: assigned tenant, authorized support purpose
  Audit: search reason and operator

FinanceJob:
  ExportPaidOrders(tenantId, month)
  Scope: approved financial dataset and cut-off
  Output: protected export artifact
~~~

Không nên gộp ba thao tác này vào một API `searchOrders(query)` quyền rộng rồi coi phần quyền là vấn đề có thể bổ sung sau.

## 18. Khi dữ liệu rất ít nhưng truy vấn lại quá phức tạp

Thiết kế query-driven không có nghĩa phải tạo hạ tầng phân tích cho mọi tính năng. Nếu một cửa hàng có vài nghìn đơn hàng, truy vấn thống kê một lần/tuần có thể thực thi trực tiếp với index đơn giản và giới hạn tài nguyên.

Điều cần tránh là **dùng giải pháp lớn nhất ngay từ đầu** hoặc ngược lại **mặc định dữ liệu sẽ luôn nhỏ**. Có thể thiết kế theo lộ trình:

~~~text
Giai đoạn đầu:
  DBMS chính + index thiết yếu + batch đơn giản

Khi tăng trưởng:
  Đo p95/p99, scan volume, report runtime, write cost
      │
      ├── Nếu chưa có vấn đề → giữ giải pháp
      ├── Nếu báo cáo lặp lại → thử rollup/materialized view
      └── Nếu phân tích rộng và tranh tài nguyên → tách analytics
~~~

Điều kiện là **phải có khả năng di chuyển**: ID ổn định, dữ liệu có thể export, schema có version hoặc hợp đồng rõ, và pipeline có thể được xây dựng lại khi cần.

## 19. Ưu tiên tác vụ hiếm theo rủi ro và deadline

Một cách phân loại:

| Mức | Đặc trưng | Ví dụ |
| --- | --- | --- |
| **Critical** | Không chạy được hoặc chạy sai sẽ ảnh hưởng nghiêm trọng đến tài chính, bảo mật, vận hành | Đối soát thanh toán, phục hồi dữ liệu, xóa đúng phạm vi |
| **Time-bound** | Phải hoàn thành trước thời điểm cụ thể | Chốt báo cáo cuối tháng, xuất dữ liệu trước audit |
| **Interactive** | Người thao tác cần phản hồi trực tiếp | Tra cứu support theo mã giao dịch |
| **Flexible** | Có thể chạy offline/chậm hơn mà không ảnh hưởng dịch vụ chính | Phân tích thử nghiệm, export phục vụ điều tra |

Một tác vụ có thể thuộc nhiều nhóm: **báo cáo chốt sổ** vừa critical vừa time-bound. Vì vậy đây là **các nhãn bổ sung**, không phải nhóm loại trừ nhau.

Đánh giá theo trục:

~~~text
Business risk         → What happens if incorrect or unavailable?
Deadline              → How soon must it finish?
Interactive latency   → How fast must a user receive the answer?
Data volume           → How many rows/bytes are touched?
Online interference   → Can it slow normal operations?
Security scope        → Who may run it and see outputs?
Recovery              → Can it safely resume or rerun?
~~~

Thông tin này giúp quyết định mức đầu tư cho index, pipeline, quan sát và bảo vệ tác vụ.

## 20. Mẫu kiểm kê hoàn chỉnh cho hệ thống thương mại điện tử

Giả sử nguồn chính gồm đơn hàng, sản phẩm, thanh toán và khách hàng; có thêm search index và báo cáo doanh thu.

| ID | Access pattern | Tần suất | Hình dạng truy cập | Yêu cầu đặc biệt | Hướng khảo sát |
| --- | --- | --- | --- | --- | --- |
| **SUP-R-01** | Tìm đơn theo payment ID | Ít | Exact lookup + tenant | Phản hồi nhanh, kiểm quyền | Secondary index hoặc payment lookup |
| **SUP-R-02** | Tìm đơn theo điện thoại và ngày | Ít | Secondary lookup + date range | Hạn chế truy cập dữ liệu cá nhân | Read model/tìm kiếm quản trị |
| **FIN-R-01** | Doanh thu theo ngày/tháng | Hằng ngày/tháng | Group/aggregate trên dữ liệu lớn | Cut-off, refund, currency | Rollup hoặc analytics |
| **FIN-R-02** | Đối soát payment–order | Hằng ngày | So khớp hai tập dữ liệu | Chính xác, có thể chạy lại | Batch job có checkpoint |
| **AUD-R-01** | Lịch sử đổi trạng thái | Khi kiểm toán | Entity ID + thời gian | Lịch sử đủ và audit trail | Event history/snapshot có index |
| **OPS-R-01** | Xuất đơn theo tenant/năm | Ít | Range scan toàn bộ | Phân trang, snapshot, bảo mật file | Export batch có giới hạn |
| **OPS-W-01** | Migration schema v1→v2 | Theo đợt | Scan + conditional update | OCC, retry, không ghi đè thay đổi mới | Batch migration |
| **OPS-W-02** | Rebuild search index | Khi cần | Full scan + derived writes | Catch-up cập nhật, cutover | Backfill + CDC/event |
| **OPS-W-03** | Xóa dữ liệu quá hạn | Theo lịch | Range lookup + delete/expire | Retention, replica, index, audit | TTL/partition lifecycle + workflow |
| **ANL-R-01** | Phân tích nhóm khách theo hành vi | Định kỳ/khám phá | Nhiều chiều, scan/tổng hợp | Không làm chậm checkout | Analytical store |

### Phân tích ba yêu cầu tiêu biểu

**SUP-R-01 — Ít nhưng cần tương tác:** Một secondary index trên `tenantId + paymentId` có thể có giá trị vì nhân viên cần tìm đúng đơn nhanh khi xử lý khiếu nại. Không nên đòi nhân viên chờ một batch vài giờ chỉ vì tần suất thấp.

**FIN-R-01 — Ít nhưng nặng:** Nếu báo cáo chạy một lần/ngày và mỗi lần đọc 50 triệu giao dịch, cần xem pre-aggregation hoặc analytics, kể cả khi không có SLO phản hồi tính bằng mili giây.

**OPS-W-02 — Hiếm nhưng ảnh hưởng toàn hệ:** Reindex có thể chỉ xảy ra khi nâng cấp schema hoặc sửa sự cố. Vẫn phải có phương án chạy lại và cách tránh để job quét dữ liệu nguồn làm giảm chất lượng dịch vụ khách hàng.

## 21. Bản quyết định kiến trúc cho từng mẫu truy cập

Sau khi kiểm kê, có thể dùng bảng ra quyết định:

| Điều kiện | Chọn hướng nào để khảo sát trước? | Điều cần xác nhận |
| --- | --- | --- |
| Tìm đúng một thực thể theo ID | Đường truy cập chính | ID có chuẩn/duy nhất và kiểm quyền đúng không? |
| Tra cứu thứ cấp hiếm nhưng cần vài giây | Secondary index/lookup | Index cost và độ chọn lọc |
| Truy vấn rất hiếm, không gấp, đọc nhiều | Batch/asynchronous export | Giới hạn tải, checkpoint, thời hạn |
| Báo cáo cùng số liệu được xem nhiều lần | Rollup/materialized view | Lag, độ đúng, refund và rebuild |
| Báo cáo tùy ý nhiều chiều, dataset lớn | Kho phân tích tách biệt | Pipeline sync, dữ liệu nhạy cảm, chi phí |
| Quản trị sửa nhiều bản ghi | Batch conditional updates | Preview, OCC, audit, retry |
| Xóa theo tenant/thời gian | Retention/delete workflow | Xác định đúng phạm vi và các bản sao |
| Khôi phục chỉ mục sau lỗi | Backfill + catch-up | Idempotency, consistency và cutover |

Không có hàng nào tự ra quyết định chỉ từ chữ “hiếm”. Hướng đề xuất phải được kiểm chứng qua **quy mô dữ liệu, yêu cầu nghiệp vụ và năng lực của DBMS cụ thể**.

### Nếu chưa biết dùng SQL, document, wide-column hay graph

Những câu hỏi định hướng có thể là:

- **Key–value:** query đã biết key chưa? Nếu không, có cấu trúc tra cứu phụ hay cách export an toàn?
- **Document:** có index phù hợp với bộ lọc hiếm không, trường có nằm trong mảng/lồng nhau, schema có đồng nhất?
- **Wide-column:** có biết partition key không, query có buộc fan-out qua nhiều partition/bucket, có read model riêng không?
- **Graph:** truy vấn quản trị cần tìm node theo property hay duyệt một mạng liên kết sâu, mức phân nhánh ra sao?
- **RDBMS:** có thể dùng index/JOIN/aggregate và replica theo yêu cầu mà không gây quá tải không?
- **Analytics/search:** loại query có phù hợp tính năng full-text/columnar aggregation và độ trễ đồng bộ không?

Đây là những câu hỏi về **access pattern**, không phải quy tắc ánh xạ cứng một loại workload tới một sản phẩm.

## 22. Quan sát và kiểm thử truy vấn hiếm

Với một truy vấn chạy một lần mỗi tháng, khó đo hiệu năng thông qua đồ thị traffic hằng ngày. Cần có cơ chế **kiểm thử trước trên dữ liệu có hình dạng đại diện** và theo dõi khi tác vụ chạy thật.

### Các chỉ số hữu ích

| Chỉ số | Điều cho biết |
| --- | --- |
| Rows/documents examined | Lượng dữ liệu cần xem xét |
| Rows returned | Lượng kết quả hữu ích |
| Partitions/shards touched | Mức độ fan-out phân tán |
| Bytes read/written | Chi phí I/O và mạng |
| p95/p99 latency cho tác vụ tương tác | Độ trễ người dùng gặp |
| Job elapsed time | Thời gian hoàn thành tác vụ batch |
| CPU, disk, memory, network during job | Tài nguyên bị chiếm |
| Online request latency during job | Mức ảnh hưởng tới đường giao dịch |
| Retry count, failures, checkpoint progress | Khả năng hoàn thành và phục hồi |
| Reconciliation mismatch count | Độ đúng của báo cáo hoặc projection |
| Replica/consumer lag | Độ mới dữ liệu đã đồng bộ |

### Ví dụ quy trình đánh giá trước triển khai

~~~text
1. Chọn query shape và dữ liệu đại diện.
2. Ghi mục tiêu: interactive latency hoặc batch deadline.
3. Xem query plan/trace trên DBMS thích hợp.
4. Đo số bản ghi/partition phải đọc, lượng I/O.
5. Đo tác động lên request online trong thời gian job chạy.
6. Thử khi dữ liệu tăng hoặc phân bố lệch.
7. Thử lỗi/tạm dừng/retry/cancel theo cách an toàn.
8. Chốt đường thực thi và giới hạn vận hành.
~~~

`EXPLAIN`, profiler hoặc tracing cho biết cách DBMS dự kiến/thực hiện query ở một cấu hình cụ thể. Không nên tự chạy các lệnh ghi hoặc lệnh profiling có tác dụng ghi trên production chỉ để đo; có thể cần môi trường thử nghiệm, dữ liệu ẩn danh và quy trình phê duyệt phù hợp.

## 23. Những nhận định dễ gây sai lầm

**“Truy vấn ít chạy nên không cần thiết kế.”** Sai: nó có thể quét toàn cụm hoặc là thao tác bắt buộc để phục hồi dịch vụ.

**“Chỉ mục nào giúp query nhanh thì cứ tạo.”** Sai: index tăng chi phí lưu, ghi, cập nhật và vận hành. Cần cân bằng với tần suất và mức thiết yếu.

**“Đã có read replica thì mọi báo cáo chạy trên đó đều không ảnh hưởng online.”** Không chắc: replica vẫn cạnh tranh tài nguyên và có thể tăng lag.

**“Báo cáo chỉ trả 10 dòng nên rất nhẹ.”** Không nhất thiết: có thể phải quét hàng triệu bản ghi để tổng hợp 10 dòng.

**“Chạy một script update hàng loạt một lần là không đáng lo.”** Sai: tác vụ hiếm có thể gây lỗi dữ liệu nghiêm trọng nếu sai điều kiện, thiếu bảo vệ concurrency hoặc không có checkpoint.

**“Cứ thêm ALLOW FILTERING là Cassandra tìm được mọi thứ hiệu quả.”** Không đúng: khả năng chạy một truy vấn không bảo đảm độ phức tạp hoặc latency chấp nhận được khi dữ liệu lớn.

**“Có TTL là đã xóa mọi dữ liệu liên quan.”** Không: phải xem bản sao, cache, search index, export, backup và chính sách retention.

**“Materialized view luôn chính xác ngay lúc nguồn commit.”** Không được mặc định: cơ chế đồng bộ và độ trễ phụ thuộc kiến trúc/DBMS.

**“Một batch đã chạy xong là số liệu chắc chắn đúng.”** Không: phải đối chiếu ngữ nghĩa nghiệp vụ, xử lý duplicate, late data và xác nhận cut-off.

**“Admin có quyền cao nên không cần kiểm quyền theo tenant.”** Sai: truy cập quản trị thường cần giám sát, giới hạn mục đích và audit chặt hơn thao tác thông thường.

## 24. Bài tập thực hành

### Bài 1 — Truy vấn hiếm có nên tạo index?

Một collection có 8 triệu tài liệu sản phẩm. Mỗi ngày có 50.000 thao tác cập nhật giá. Nhân viên quản trị mỗi tháng chạy một truy vấn tìm mọi sản phẩm có thuộc tính `legacyCode = 'X'` và chấp nhận chờ tối đa 30 phút.

Hãy liệt kê những thông tin cần thu thập trước khi tạo secondary index và đề xuất ít nhất hai hướng khác nhau.

**Gợi ý:** cần số bản ghi phù hợp, tần suất cập nhật `legacyCode`, thời gian scan hiện tại, tác động lên online, mức tăng trưởng, độ trễ yêu cầu và liệu có batch/analytics đang có sẵn. Có thể cân nhắc index hoặc batch có giới hạn; không được quyết định chỉ từ tần suất.

### Bài 2 — Báo cáo doanh thu không trùng

Hệ thống nhận sự kiện `OrderPaid` theo cơ chế có thể phát lại. Báo cáo đang cộng `amount` mỗi khi nhận sự kiện. Sau một lần restart, một số sự kiện được gửi lại khiến doanh thu tăng sai.

Hãy mô tả nguyên nhân và đề xuất cơ chế cập nhật projection an toàn.

**Gợi ý:** cần định danh event/giao dịch và xử lý idempotent; duy trì tiến độ, kiểm tra trùng trong phạm vi phù hợp, đối soát với dữ liệu có thẩm quyền và khả năng rebuild.

### Bài 3 — Truy vấn quản trị thiếu partition key

Bảng Cassandra `orders_by_customer_month` phân vùng theo `tenantId + customerId + month`. Một nhân viên cần tìm tất cả đơn trạng thái FAILED trong một ngày của tenant.

Vì sao không thể cho rằng query này sẽ hiệu quả chỉ vì có cột `status`? Hãy nêu ít nhất ba hướng giải quyết và đánh đổi của mỗi hướng.

**Gợi ý:** partition key truy vấn không xác định; xem bảng đọc theo tenant–status–day, secondary index tương thích hoặc batch/search/analytics, cùng chi phí đồng bộ và fan-out.

### Bài 4 — Export giữa lúc dữ liệu đang ghi

Một export đọc các đơn hàng trong tháng theo từng trang. Trong lúc chạy, có thêm đơn được backdate và một số đơn đổi trạng thái. Chỉ dùng cursor theo `createdAt` có đủ bảo đảm bản export phản ánh một snapshot bất biến không?

**Gợi ý:** chưa chắc. Cần quy định snapshot/cut-off, cách xử lý backdated writes, versioned data và khả năng đối soát hoặc xuất lại nếu yêu cầu tài chính nghiêm ngặt.

### Bài 5 — Migration giữa lúc người dùng sửa dữ liệu

Một migration đọc tài liệu `revision = 7` và định ghi lại `schemaVersion = 2`. Trước khi ghi, người dùng đã cập nhật tài liệu thành `revision = 8`. Migration nên làm gì?

**Gợi ý:** ghi có điều kiện theo revision, phát hiện xung đột, đọc lại và xử lý theo quy tắc hoặc đưa vào hàng xử lý; không ghi đè toàn bộ từ snapshot cũ.

### Bài 6 — Phân loại mức độ quan trọng

Xếp các tình huống theo **tần suất, mức tài nguyên, mức rủi ro và deadline**:

~~~text
A. Support tìm một đơn theo payment ID.
B. Báo cáo đối soát thanh toán cuối tháng.
C. Dashboard tổng doanh thu cập nhật mỗi phút.
D. Reindex toàn bộ sản phẩm sau sự cố.
E. Xóa dữ liệu khách hàng theo yêu cầu hợp lệ.
~~~

**Gợi ý:** A hiếm và cần tương tác; B ít nhưng critical/time-bound; C thường xuyên, có thể dùng projection; D hiếm và nặng; E có thể hiếm nhưng rủi ro cao và cần audit/phạm vi chính xác.

### Bài 7 — Thiết kế phương án bảo vệ đường checkout

Một job phân tích chạy lúc 1 giờ sáng nhưng khi có chiến dịch khuyến mãi, traffic checkout vẫn cao. Job làm disk I/O tăng khiến p99 checkout xấu đi. Hãy đề xuất các cơ chế giảm ảnh hưởng, cách đo tác động và điều kiện tạm dừng job.

**Gợi ý:** concurrency/rate limit, scheduling linh hoạt, phân trang nhỏ, tách read replica/analytics nếu phù hợp, giám sát p99 và queue depth, hỗ trợ cancel/resume.

## 25. Mẫu đặc tả cho một truy vấn hiếm hoặc job quản trị

Một nhóm có thể thống nhất mẫu:

~~~yaml
id: OPS-W-09
name: "Rebuild product search index"
purpose: "Recover or upgrade search projection"
requester: "Search operations team"
approvalPolicy: "According to environment and data risk"
frequency: "On demand"
operationType: "Bulk read + derived writes"
sourceOfTruth: "Product service"
scope:
  tenant: "One tenant or authorized all-tenant scope"
  dataRange: "Explicitly selected"
dataVolume:
  estimatedRows: "TBD"
  peakSize: "TBD"
consistency:
  sourceCutoff: "Defined by job"
  catchUpChanges: "Required before cutover"
idempotency:
  key: "Stable entity ID and source version"
execution:
  mode: "Async job"
  concurrencyLimit: "Set from workload tests"
  checkpoint: "Persisted"
  cancellation: "Supported"
  retry: "Bounded and resumable"
security:
  role: "Restricted operator/service"
  audit: "Job ID, actor, scope, start/end, outcome"
validation:
  compareCounts: true
  compareRepresentativeRecords: true
  checkConsumerLag: true
rollback:
  approach: "Switch readers back to previous valid index if possible"
impactMonitoring:
  - online_p95_p99
  - bytes_read
  - database_cpu_io
  - search_index_lag
  - job_error_rate
~~~

Đây là **tài liệu yêu cầu minh họa**, không phải cấu hình chạy tự động. Các trường `TBD` phải được xác minh; không nên đưa job vào production khi các ràng buộc sống còn còn chưa rõ.

## 26. Kết luận: tối ưu đúng mức, bảo vệ đúng thứ

Khi đánh giá truy vấn hiếm, báo cáo và thao tác quản trị trong thiết kế NoSQL theo truy vấn, hãy nhớ ba nguyên tắc:

1. **Tần suất thấp không đồng nghĩa giá trị thấp.** Truy vấn hỗ trợ, đối soát, phục hồi và xóa dữ liệu có thể ít chạy nhưng rất quan trọng về nghiệp vụ, pháp lý hoặc an toàn vận hành.
2. **Không tối ưu riêng một câu truy vấn mà quên toàn bộ workload.** Secondary index, bảng đọc phụ và kho analytics có chi phí duy trì; batch scan cũng có thể chiếm tài nguyên và làm chậm đường giao dịch.
3. **Bảo đảm đúng đắn và khả năng phục hồi trước khi tối ưu tốc độ.** Với báo cáo phải xác định cut-off, trùng/đến trễ, chính sách hoàn tiền và đối soát; với admin phải có giới hạn phạm vi, quyền, dry-run, audit, checkpoint và phương án xử lý lỗi.

Một quyết định thiết kế tốt sẽ ghi rõ **access pattern**, **nguồn dữ liệu có thẩm quyền**, **độ trễ/deadline**, **tài nguyên cần dùng**, **độ mới/nhất quán**, **phân quyền** và **cách khôi phục khi thất bại**. Khi những yêu cầu đó đã rõ, ta mới chọn được giữa **truy vấn trực tiếp, secondary index, batch, read model, rollup hay kho phân tích tách biệt** với mức đầu tư phù hợp cho cả hệ thống.
