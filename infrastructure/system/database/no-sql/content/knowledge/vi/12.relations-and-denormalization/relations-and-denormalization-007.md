# Tổng hợp được lưu sẵn và cập nhật khi dữ liệu gốc thay đổi

Trong cơ sở dữ liệu NoSQL, một màn hình có thể cần hiển thị những kết quả **được tính từ nhiều bản ghi**: tổng số đơn hàng của một cửa hàng, doanh thu mỗi ngày, số sản phẩm trong từng danh mục, số bài viết của một tác giả, số lượt tương tác, điểm đánh giá trung bình hay danh sách top sản phẩm. Nếu mỗi request đều đọc toàn bộ dữ liệu gốc rồi tính lại, chi phí có thể tăng cùng lượng dữ liệu, ngay cả khi màn hình chỉ cần một vài con số.

Một hướng thiết kế phổ biến là lưu trước **kết quả tổng hợp** (*precomputed aggregate*) dưới dạng document, item, bảng hoặc khóa riêng; khi dữ liệu gốc thay đổi, hệ thống cập nhật kết quả này. Ví dụ, thay vì tính doanh thu bằng cách đọc hàng triệu đơn ở mỗi request, API đọc một bản ghi **daily_sales(tenant, store, day, currency)** có tổng tiền, số đơn và thời điểm cập nhật.

Đây là một dạng **lặp dữ liệu có chủ đích**: cùng thông tin được biểu diễn cả ở dữ liệu nguồn lẫn bản tổng hợp. Tối ưu được đường đọc, nhưng kéo theo nghĩa vụ giữ hai biểu diễn **đúng, đủ mới và có thể khôi phục**. Trong hệ NoSQL phân tán, thử thách không chỉ là viết lệnh tăng counter mà còn là xử lý **gửi sự kiện trùng, thay đổi trạng thái, hoàn tiền, sửa bản ghi cũ, chuyển nhóm, sự kiện đến muộn, mất kết nối và backfill**.

Bài học đi từ nguyên tắc thiết kế đến ví dụ chi tiết cho báo cáo doanh thu, điểm đánh giá và các công cụ như MongoDB, DynamoDB, Redis, Cassandra. Mục tiêu là xây được một **hợp đồng về dữ liệu, cập nhật và độ tươi**, không chỉ một cấu trúc lưu tổng.

## 1. Tổng hợp được lưu sẵn là gì?

Giả sử collection đơn hàng lưu dữ liệu nguồn:

~~~json
[
  {
    "orderId": "O-101",
    "tenantId": "T1",
    "storeId": "S1",
    "status": "PAID",
    "paidAt": "2026-11-14T03:00:00Z",
    "currency": "VND",
    "paidAmountMinor": 120000
  },
  {
    "orderId": "O-102",
    "tenantId": "T1",
    "storeId": "S1",
    "status": "PAID",
    "paidAt": "2026-11-14T04:00:00Z",
    "currency": "VND",
    "paidAmountMinor": 80000
  }
]
~~~

Một API báo cáo cần:

~~~text
GET /stores/S1/sales?date=2026-11-14

Kết quả:
    paidOrderCount = 2
    totalPaidMinor = 200000
    currency = VND
~~~

Có hai phương án:

**Tính khi đọc:** mỗi request tìm tất cả order thỏa điều kiện rồi thực hiện COUNT/SUM hoặc đọc một chỉ mục phù hợp. Cách này đơn giản về đồng bộ nếu truy vấn trực tiếp nguồn và hệ có cơ chế đọc đáp ứng hợp đồng, nhưng chi phí có thể lớn khi số order và tần suất xem báo cáo tăng.

**Tính khi ghi hoặc trước khi đọc:** tạo sẵn một bản tổng hợp:

~~~json
{
  "_id": "T1:S1:2026-11-14:VND",
  "tenantId": "T1",
  "storeId": "S1",
  "day": "2026-11-14",
  "currency": "VND",
  "paidOrderCount": 2,
  "totalPaidMinor": 200000,
  "computedAt": "2026-11-14T04:00:01Z",
  "sourceWatermark": "..."
}
~~~

Khi API cần báo cáo, nó đọc theo khóa tổng hợp. Thời gian đọc có thể gần như không phụ thuộc vào số đơn nguồn, nhưng lúc ghi **O-103** hoặc sửa **O-101**, hệ phải cập nhật bản tổng hợp.

### Bốn khái niệm dễ bị nhầm

| Khái niệm | Bản chất | Điểm cần nhớ |
| --- | --- | --- |
| **Aggregate theo nghĩa nghiệp vụ** | Nhóm dữ liệu có ranh giới bảo vệ bất biến, như đơn và các dòng đơn | Không đồng nghĩa với SUM/COUNT được lưu sẵn. |
| **Precomputed aggregate** | Kết quả SUM, COUNT, MIN/MAX, thống kê, xếp hạng... đã được tính trước | Cần cơ chế cập nhật hoặc xây lại khi nguồn thay đổi. |
| **Materialized view/read model** | Bản biểu diễn được lưu để phục vụ một kiểu truy vấn | Có thể là bản sao dữ liệu chi tiết, index hoặc tổng hợp; không phải lúc nào cũng là SUM/COUNT. |
| **Cache** | Bản dữ liệu phục vụ đọc nhanh, thường có TTL hoặc chính sách vô hiệu hóa | Không nhất thiết có cơ chế bảo trì giống một read model bền vững. |

Một **materialized view** của từng sản phẩm còn bán không tự động là một **bảng tổng số sản phẩm**; và tên tính năng “materialized view” ở các sản phẩm NoSQL có thể có khả năng rất khác nhau. Phải mô tả chính xác kết quả được lưu và cách duy trì nó.

## 2. Những nhóm truy vấn nên cân nhắc tổng hợp trước

| Nhóm truy vấn | Kết quả điển hình | Vì sao tiền tính có ích? |
| --- | --- | --- |
| **Counter** | Số bài viết của tác giả, số lượt xem | Tránh phải đếm mọi bản ghi nguồn khi tải đọc cao. |
| **Tổng theo nhóm** | Doanh thu theo cửa hàng/ngày/tiền tệ | Đọc vài bản tổng thay vì quét nhiều đơn. |
| **Trung bình/điểm đánh giá** | Điểm sao trung bình và số đánh giá | Giảm chi phí tổng hợp toàn bộ review. |
| **Histogram** | Số order theo trạng thái, số sản phẩm mỗi mức giá | Dashboard đọc nhóm kết quả cố định. |
| **Top-K/ranking** | Top sản phẩm bán chạy trong tuần | Tránh xếp hạng hàng triệu sản phẩm theo mỗi request. |
| **Chỉ số theo cửa sổ** | Request/phút, lỗi/giờ, người dùng hoạt động/ngày | Phục vụ monitoring hoặc phân tích thời gian. |
| **Số liệu theo tenant** | Tổng dung lượng sử dụng và số item | Có thể hỗ trợ quota, nhưng nếu dùng để quyết định ghi cần bảo đảm mạnh hơn thống kê. |

Không phải truy vấn tổng hợp nào cũng nên lưu sẵn. Nếu dữ liệu nhỏ, truy vấn hiếm, filter thay đổi tùy ý hoặc database có công cụ aggregate/index hiệu quả, **tính khi đọc** có thể đơn giản và kinh tế hơn. Đánh giá dựa trên **chi phí đọc, chi phí cập nhật, mức sai lệch được phép, khả năng xây lại và độ phức tạp vận hành**.

## 3. Đầu tiên phải định nghĩa công thức nghiệp vụ

Một bản tổng hợp nhìn đơn giản có thể sai nếu định nghĩa không rõ.

Ví dụ câu “doanh thu ngày 14/11” chưa cho biết:

- Đơn **PAID** hay **COMPLETED** mới được tính?
- Ghi nhận theo **paidAt**, createdAt hay thời điểm giao hàng?
- Đơn hoàn tiền một phần bị trừ vào ngày gốc hay ngày hoàn tiền?
- Tính doanh thu gộp, ròng, sau thuế hay trước phí?
- Nhiều đơn vị tiền tệ được giữ riêng hay chuyển đổi bằng tỷ giá nào?
- Ngày được tính theo UTC, múi giờ cửa hàng hay múi giờ pháp nhân?
- Một yêu cầu thanh toán retry hai lần tạo một hay hai đơn vị ghi nhận?
- Dữ liệu nguồn có thể sửa sau vài tháng không?
- Bộ đếm là số **đơn duy nhất**, số **thanh toán** hay số **dòng hàng**?

### Ví dụ một định nghĩa có thể kiểm chứng

~~~text
Chỉ số: paidOrderCount
Khóa nhóm: (tenantId, storeId, businessDay, currency)
Điều kiện: mỗi order có trạng thái PAID hoặc trạng thái
            khác được nghiệp vụ xác nhận tương đương PAID
Đơn vị: số orderId duy nhất thỏa điều kiện
Thời gian nhóm: businessDay tính từ paidAt theo timezone
                 đã được cố định cho cửa hàng
Độ tươi: read model có thể trễ không quá ngưỡng đã thống nhất
Nguồn sự thật: order/ledger thanh toán đã commit
~~~

Với **totalNetSales**, công thức phức tạp hơn nếu cho phép refund và phí. Có thể chọn biểu diễn bằng **ledger các nghiệp vụ tài chính đã ghi nhận** thay vì chỉ dựa vào status hiện tại của order; quyết định này phải thống nhất với người sở hữu nghiệp vụ.

### Tách tiền tệ và kiểu số

Không cộng trực tiếp 100 USD với 100 VND rồi ghi **total = 200**. Khóa nhóm phải bao gồm **currency**, hoặc tổng đã chuyển đổi phải có tỷ giá, thời điểm và cách làm tròn được xác định.

Với tiền, tránh dùng số thực dấu phẩy động nhị phân tùy tiện. Có thể dùng **số nguyên ở đơn vị nhỏ nhất theo currency** khi thích hợp, hoặc decimal có độ chính xác đã quy định. Không được mặc định mọi đồng tiền đều có hai chữ số thập phân.

## 4. Chọn cấu trúc khóa cho bản tổng hợp

Đường đọc phải quyết định cấu trúc trước khi chọn công nghệ.

### 4.1. Tổng doanh thu theo cửa hàng/ngày

~~~text
Key = SALES#tenantId#storeId#businessDay#currency

Value:
    paidOrderCount
    grossMinor
    refundMinor
    netMinor
    sourceVersion / sourceWatermark
    updatedAt
~~~

Nếu API thường đọc một cửa hàng trong một ngày, key trên cho lookup trực tiếp. Nếu API còn đọc **tổng toàn tenant theo ngày**, có thể cần thêm nhóm tổng hợp riêng hoặc cộng một số nhóm cửa hàng. Đừng tạo key **SALES#ALL#DAY** rồi cho mọi transaction ghi vào đó khi nó trở thành hot key mà không đánh giá tải và rủi ro contention.

### 4.2. MongoDB document

~~~json
{
  "_id": "T1:S1:2026-11-14:VND",
  "tenantId": "T1",
  "storeId": "S1",
  "businessDay": "2026-11-14",
  "currency": "VND",
  "paidOrderCount": 25,
  "grossMinor": 2500000,
  "refundMinor": 300000,
  "netMinor": 2200000,
  "updatedAt": "2026-11-14T10:00:00Z",
  "sourceWatermark": "..."
}
~~~

Bản tổng hợp phải có **khóa duy nhất** theo các chiều nhóm. Nếu dùng một tập document lớn, có thể tạo compound index phục vụ truy vấn theo tenant, cửa hàng, ngày tùy workload. Chỉ mục tăng chi phí ghi; không nên tạo tùy ý mọi tổ hợp.

### 4.3. CQL table trong wide-column

~~~sql
CREATE TABLE sales_by_store_day (
    tenant_id text,
    store_id text,
    business_day date,
    currency text,
    paid_order_count bigint,
    gross_minor bigint,
    refund_minor bigint,
    net_minor bigint,
    updated_at timestamp,
    PRIMARY KEY (
        (tenant_id, store_id),
        business_day,
        currency
    )
) WITH CLUSTERING ORDER BY (
    business_day DESC,
    currency ASC
);
~~~

Ví dụ này phù hợp khi thường đọc **nhiều ngày** của một cửa hàng. Nhưng partition theo tenant/store có thể lớn dần nhiều năm; có thể cần chia tiếp theo **year** hoặc bucket thời gian nếu dữ liệu lớn. Quan trọng hơn: **cột bigint thông thường không tự cung cấp phép cộng an toàn** khi nhiều writer cùng read–modify–write. Phải chọn cách cập nhật có điều kiện, cơ chế đồng bộ hoặc mô hình khác phù hợp với sản phẩm/phiên bản.

### 4.4. DynamoDB item và Redis key

DynamoDB có thể biểu diễn:

~~~text
PK = TENANT#T1#STORE#S1
SK = SALES#2026-11-14#VND

paidOrderCount = 25
grossMinor = 2500000
refundMinor = 300000
netMinor = 2200000
~~~

Redis có thể dùng một hash:

~~~redis
HSET sales:T1:S1:2026-11-14:VND paidOrderCount 25 grossMinor 2500000 refundMinor 300000 netMinor 2200000
HGETALL sales:T1:S1:2026-11-14:VND
~~~

Lựa chọn cấu trúc không chỉ dựa vào đọc nhanh. Cần biết bản tổng **có phải dữ liệu bền vững** hay chỉ là cache có thể xây lại, cách ghi chống trùng, TTL, replica/failover và ai giữ nguồn sự thật.

## 5. Ba phương thức duy trì tổng hợp

### 5.1. Tính lại khi đọc (*on-demand aggregation*)

~~~text
Client -> API -> đọc nhiều order nguồn -> SUM/COUNT -> response
~~~

Ưu điểm: một nguồn dữ liệu, ít cấu trúc phụ để đồng bộ. Nhược điểm: chi phí query tăng theo số bản ghi/chiều lọc; dễ không phù hợp với dashboard QPS cao. Nếu có index/query engine hiệu quả và tập dữ liệu vừa phải, vẫn có thể là lựa chọn tốt.

### 5.2. Cập nhật đồng bộ với thao tác nguồn

~~~text
Request ghi Order
    -> Transaction:
         cập nhật Order
         cập nhật sales_daily
       COMMIT
    -> trả thành công
~~~

Ưu điểm: nếu **transaction thực sự bao phủ cả nguồn và tổng hợp** với isolation đủ mạnh, kết quả sau commit có thể nhất quán theo phạm vi và cách đọc của hệ. Nhược điểm: mỗi nghiệp vụ ghi chạm thêm item/partition, làm tăng write contention, độ trễ và nguy cơ abort. Nếu hai nơi thuộc hai database hoặc hai dịch vụ khác nhau, transaction cục bộ không bao phủ cả hai.

**Không được coi “hai API write chạy liền nhau” là cập nhật đồng bộ có tính nguyên tử.** Nếu bước đầu thành công và bước sau thất bại, tổng hợp sẽ lệch trừ khi có cơ chế phục hồi.

### 5.3. Cập nhật bất đồng bộ qua sự kiện hoặc CDC

~~~text
Request ghi Order
    -> Nguồn Order commit
    -> Outbox / CDC / change stream
    -> Consumer tính ảnh hưởng
    -> Cập nhật sales_daily
    -> API đọc bản tổng hợp
~~~

Ưu điểm: giảm công việc đồng bộ nằm trên đường request, dễ tạo nhiều read model chuyên biệt và hỗ trợ rebuild/replay. Nhược điểm: kết quả có thể **chậm hội tụ**, cần xử lý event trùng, sai thứ tự, consumer bị lỗi, backlog và backfill dữ liệu lịch sử.

### 5.4. Tái tính định kỳ theo lô (*periodic rebuild*)

~~~text
Hằng giờ hoặc cuối ngày:
    đọc dữ liệu nguồn theo phạm vi rõ
    -> tính lại các group
    -> ghi đè/đổi phiên bản bản tổng
~~~

Phù hợp báo cáo có thể chậm cập nhật, kiểm tra đối soát hoặc sửa dữ liệu tổng bị lệch. Không nên mặc định việc tính lại trên toàn bộ hệ mỗi phút là rẻ; cần chia phạm vi ngày/store, dùng snapshot/watermark và kiểm soát lúc dữ liệu vẫn đang thay đổi.

| Cách duy trì | Độ tươi thường gặp | Chi phí chính | Câu hỏi cần chốt |
| --- | --- | --- | --- |
| Tính khi đọc | Tùy read consistency của nguồn | Đọc/compute mỗi request | Query có mở rộng theo dữ liệu không? |
| Transaction đồng bộ | Có thể cùng commit theo phạm vi transaction | Ghi thêm, contention, latency | Transaction/isolation có bao phủ đủ không? |
| CDC/event bất đồng bộ | Có độ trễ xử lý và replica | Pipeline, idempotency, replay | Tối đa cho phép trễ bao nhiêu? |
| Batch rebuild | Theo chu kỳ | Quét nguồn, compute, cutover | Có thể chậm một giờ/ngày không? |

Trong thực tế có thể kết hợp: **incremental async để gần thời gian thực**, cộng **reconciliation định kỳ** để kiểm chứng và sửa sai.

## 6. Phép cập nhật tăng dần: delta thay vì cộng lại toàn bộ

Với chỉ số cộng được như COUNT hoặc SUM, khi một bản ghi mới đóng góp giá trị **c**, có thể chỉ cập nhật tổng bằng delta:

\[
A_{\text{new}} = A_{\text{old}} + \Delta
\]

Ví dụ đơn mới được thanh toán với số tiền 120.000 (theo đơn vị đã chọn):

~~~text
Before:
    totalPaid = 200000
    paidOrderCount = 2

New contribution:
    amount = 120000
    count = 1

After:
    totalPaid = 320000
    paidOrderCount = 3
~~~

Nhưng phép cộng luôn **+1, +amount** chỉ đúng nếu mỗi nghiệp vụ mới thực sự đóng góp một lần, và không có sửa đổi hoặc hoàn tác.

### 6.1. Định nghĩa contribution trên từng bản ghi nguồn

Một phương pháp tổng quát là định nghĩa hàm **C(r)** mô tả phần đóng góp của bản ghi nguồn r vào từng nhóm.

~~~text
C(order):
    Nếu order chưa thanh toán:
        paidOrderCount = 0
        paidAmount = 0

    Nếu order thanh toán thành công:
        paidOrderCount = 1
        paidAmount = số tiền được ghi nhận

    Nếu order bị hoàn toàn bộ:
        contribution thay đổi theo chính sách báo cáo đã chọn
~~~

Với một thay đổi từ trạng thái cũ sang trạng thái mới, delta chính xác là:

\[
\Delta = C(r_{\text{new}}) - C(r_{\text{old}})
\]

Ví dụ:

| Thay đổi của order | Contribution trước | Contribution sau | Delta phải áp dụng |
| --- | --- | --- | --- |
| PENDING → PAID 120.000 | count 0, amount 0 | count 1, amount 120.000 | count +1, amount +120.000 |
| PAID 120.000 → PAID 130.000 | count 1, amount 120.000 | count 1, amount 130.000 | count 0, amount +10.000 |
| PAID → CANCELLED có hoàn tiền đủ | Theo chính sách cũ | Theo chính sách mới | Có thể count -1, amount -120.000 nếu metric là net eligible paid orders |
| Đổi ngày ghi nhận | Group ngày A | Group ngày B | Trừ ở A, cộng ở B |
| Chuyển cửa hàng | Group store X | Group store Y | Trừ ở X, cộng ở Y |

Lưu ý: chính sách tài chính thực tế thường tách **gross sales** và **refunds** thành các sự kiện ledger riêng; không nhất thiết sửa ngược doanh thu ngày gốc. Bảng chỉ cho thấy **cách tính delta nếu metric được định nghĩa theo trạng thái hiện tại**, chứ không áp đặt một chuẩn kế toán.

### 6.2. Khi group key thay đổi

Giả sử order trước thuộc ngày 13, sau được sửa sang ngày 14. **Không thể chỉ cộng vào ngày mới.**

~~~text
Old group: (T1, S1, 2026-11-13, VND)
New group: (T1, S1, 2026-11-14, VND)

Bước logic:
    old group -= old contribution
    new group += new contribution
~~~

Nếu hai group nằm ở hai partition hoặc hai dịch vụ và không có transaction chung, có thể tồn tại khoảng trống hai nhóm chưa khớp. Cần transaction có phạm vi phù hợp hoặc workflow versioned có thể retry/reconcile. Không được cho rằng delta vào hai key khác nhau tự atomic toàn cục.

### 6.3. Không phải hàm tổng hợp nào cũng có delta đơn giản

| Hàm | Cập nhật thêm bản ghi | Khi sửa/xóa bản ghi |
| --- | --- | --- |
| COUNT | Có thể +1 | Có thể -1 nếu biết đóng góp cũ |
| SUM | Có thể +amount | Delta old/new nếu biết cả hai |
| AVG | Giữ **sum + count**, tính sum/count khi đọc | Cập nhật cả sum và count theo đóng góp cũ/mới |
| MIN/MAX | Có thể so sánh và thay min/max | Xóa phần tử đang là min/max có thể phải tra cứu hoặc tính lại |
| DISTINCT COUNT | Không được chỉ +1 cho mỗi event nếu giá trị trùng | Cần tập định danh/reference count hoặc cấu trúc xấp xỉ |
| MEDIAN/PERCENTILE | Không có một scalar delta tổng quát đơn giản | Cần cấu trúc dữ liệu, sketch phù hợp hoặc tái tính |
| TOP-K | Có thể cập nhật xếp hạng ứng viên | Khi phần tử rời top, cần biết ứng viên kế tiếp |
| APPROXIMATE UNIQUE | Sketch như HyperLogLog phù hợp một số bài toán | Xóa hoặc sửa dữ liệu thường khó đảo trực tiếp, có thể phải xây lại |

Chọn **biểu diễn nội bộ** theo phép cập nhật sẽ xảy ra, không chỉ theo kết quả hiển thị. Ví dụ cần **averageRating** thì thường lưu cả **ratingSum** và **ratingCount**; chỉ lưu một số average làm việc sửa hoặc xóa review phức tạp và dễ sai.

## 7. Ví dụ: điểm đánh giá trung bình của sản phẩm

Giả sử sản phẩm P-100 có ba review điểm 5, 4, 3.

~~~text
ratingCount = 3
ratingSum   = 12
ratingAvg   = ratingSum / ratingCount = 4.0
~~~

Một review mới điểm 5:

~~~text
ratingCount += 1
ratingSum   += 5
ratingAvg    = 17 / 4 = 4.25
~~~

Nếu review của user U đổi từ 5 xuống 2, delta **không phải +2** mà là:

~~~text
ratingCount += 0
ratingSum   += (2 - 5) = -3
~~~

Nếu một review hợp lệ bị xóa:

~~~text
ratingCount -= 1
ratingSum   -= oldRating
~~~

### Vấn đề trùng đánh giá

Nếu quy tắc là “mỗi user chỉ có một review trên một product”, tổng hợp phải dựa trên **review được định danh duy nhất bởi (productId, userId)** hoặc reviewId có uniqueness phù hợp.

Nếu consumer nhận hai lần sự kiện review đã tạo, cộng +5 hai lần sẽ tạo **ratingSum sai dù từng phép +5 nguyên tử**. Muốn cập nhật chính xác, phải xác định trạng thái/contribution trước đó của review và bảo vệ việc áp dụng delta theo version/event ID.

### Đường đọc và đường ghi

~~~text
Nguồn:
    reviews(productId, userId, rating, version)

Bản tổng:
    product_rating(productId):
        ratingCount
        ratingSum
        updatedAt
        sourceWatermark

Đường đọc:
    GET product_rating
    -> ratingAvg = ratingSum / ratingCount
~~~

Không nhất thiết lưu thêm ratingAvg nếu đã có sum và count; lưu trung bình làm field có thể tăng rủi ro lệch khi một bước cập nhật dở dang. Nếu cần cache average để phục vụ truy vấn nhanh, phải quy định nó được tính từ đâu và khi nào.

## 8. Thách thức lớn nhất: event đến trùng và chưa rõ kết quả ghi

Một pipeline **at-least-once delivery** có thể phát một event nhiều lần:

~~~text
Order O-101 chuyển sang PAID.
Event E-101 được phát.

Consumer:
    +1 paidOrderCount
    +120000 totalPaid
    [crash trước khi ACK event]

Broker:
    phát lại E-101

Consumer:
    +1 paidOrderCount
    +120000 totalPaid một lần nữa
~~~

Từng phép tăng có thể **atomic trên một key**, nhưng kết quả tổng vẫn sai.

### 8.1. Vì sao đánh dấu đã xử lý riêng rẽ vẫn có lỗ hổng?

Cách chưa đủ an toàn:

~~~text
IF eventId chưa có trong processedEvents:
    INCREMENT dailySales
    INSERT processedEvents(eventId)
~~~

Hai consumer có thể cùng thấy event chưa xử lý. Nếu chỉ một consumer, vẫn có thể crash **sau increment, trước khi ghi processedEvents** và lần retry cộng thêm lần nữa.

Đổi thứ tự cũng không đủ:

~~~text
INSERT processedEvents(eventId)
INCREMENT dailySales
~~~

Nếu crash sau khi ghi processedEvents, event đã được đánh dấu nhưng tổng chưa cộng. Một lần retry có thể bỏ qua event và **mất đóng góp**.

**Cần tính nguyên tử giữa việc ghi nhận đã xử lý và việc áp dụng tác động**, hoặc một thiết kế đảm bảo có thể phát hiện/khôi phục chính xác phần việc còn thiếu.

### 8.2. Những chiến lược chống trùng

**Chiến lược A — Transaction bao phủ aggregate và dedup record.**

~~~text
TRANSACTION:
    nếu eventId đã tồn tại trong processedEvents:
        bỏ qua hoặc trả kết quả đã xử lý
    nếu chưa:
        cập nhật bản tổng
        ghi processedEvents(eventId)
COMMIT
~~~

Chỉ đúng nếu transaction có **isolation và uniqueness** đủ ngăn hai consumer xử lý cùng event đồng thời và bao phủ tất cả bản ghi được cập nhật. Nếu event ảnh hưởng nhiều group, transaction phải bao phủ đầy đủ các group cần nhất quán theo hợp đồng.

**Chiến lược B — Projection dựa trên contribution hiện tại của từng entity.**

~~~text
contributionByOrder:
    orderId -> {version, groupKey, amount, count}

Nhận order version v:
    đọc contribution đã áp dụng trước
    nếu v <= version đã áp dụng: bỏ qua
    nếu v mới hơn:
        delta = contribution mới - contribution cũ
        cập nhật group liên quan
        ghi contribution version v
~~~

Ý tưởng này hữu ích khi bản ghi nguồn có thể thay đổi. Nhưng **đọc contribution, cập nhật group và ghi version** vẫn cần một ranh giới transaction/điều phối hoặc workflow bù trừ. Chỉ có version trên record mà không bảo vệ delta không tự loại race.

**Chiến lược C — Xây lại từ nguồn chuẩn.**

Nếu không thể bảo đảm chính xác mọi delta ở đường cập nhật trực tuyến, có thể chạy định kỳ để so sánh và **ghi lại tổng được tính từ nguồn**, với snapshot/watermark và cơ chế cutover đúng. Cách này thường phù hợp thống kê và là lớp phục hồi cần thiết ngay cả khi đã có transaction.

### 8.3. Idempotency ở mức hiệu ứng

“Consumer có thể nhận event nhiều lần” không có nghĩa “business effect phải tăng nhiều lần”. Thiết kế cần hướng tới:

~~~text
Cùng eventId + cùng source version
    -> cùng một hiệu ứng lên bản tổng, dù message được gửi lại.

Event có version mới hơn
    -> chỉ delta giữa contribution mới và đã áp dụng.
~~~

Một event ID ngẫu nhiên khác cho cùng một nghiệp vụ **không thể tự được nhận diện là trùng** nếu hệ không có **business id/orderId/reviewId** để gắn hai event với cùng một sự thay đổi. Nên ghi rõ danh tính sự kiện và danh tính nghiệp vụ.

## 9. Sự kiện đến sai thứ tự và cập nhật bị lùi phiên bản

Giả sử order O-101 có các trạng thái:

~~~text
version 8: PENDING
version 9: PAID
version 10: REFUNDED
~~~

Trong hệ bất đồng bộ, consumer có thể nhận:

~~~text
v9 -> v10 -> v9 (message cũ phát lại)
~~~

Nếu mỗi event chỉ nói **status mới** và consumer ghi đè không điều kiện, bản tổng có thể quay ngược trạng thái hoặc cộng lại lượng đã bị trừ.

### Quy tắc version đơn điệu

Lưu version đã áp dụng cho từng order:

~~~text
projectionState[orderId] = {
    lastAppliedVersion: 10,
    contribution: ...
}
~~~

Khi thấy event version **9**, consumer bỏ qua vì đã áp dụng version 10. Khi thấy version 11, tính lại contribution mới và delta tương ứng.

Tuy nhiên, **không được giả định event 11 mang đủ dữ liệu** để tính delta nếu nó chỉ chứa một thay đổi nhỏ phụ thuộc vào event 10 bị mất. Có hai kiểu event:

- **Full-state event:** chứa trạng thái mới đủ để tính contribution; có thể giúp đồng bộ từ version mới nhất nếu chính sách cho phép.
- **Delta event:** chỉ chứa thay đổi, ví dụ “+5”; phải có thứ tự hoặc khả năng phát hiện gap và nạp lại từ nguồn.

Nếu phát hiện gap version 8 → 10 trong một luồng delta cần tính nối tiếp, cần **replay v9 hoặc đọc trạng thái nguồn**. Không được cộng bừa v10 mà không biết nó dựa trên trạng thái nào.

### Thứ tự giữa nhiều entity

Có thể bảo đảm thứ tự theo từng order nhưng không có một thứ tự toàn cục duy nhất giữa tất cả order. Với tổng theo ngày, đôi khi có thể chấp nhận áp dụng các order độc lập ở thứ tự bất kỳ vì phép cộng giao hoán; nhưng yêu cầu về **đọc nhất quán, watermark, xóa/cập nhật group và snapshot** vẫn cần mô hình rõ ràng.

## 10. CDC, change stream và transactional outbox

Một pipeline duy trì bản tổng có thể đọc sự kiện từ **Change Data Capture (CDC)**, change stream hoặc outbox.

~~~mermaid
flowchart LR
    API[API thay đổi nguồn] --> SRC[Order / Review source of truth]
    SRC --> CH[CDC / Outbox / Change log]
    CH --> Q[Broker hoặc hàng đợi]
    Q --> W[Consumer tính contribution và delta]
    W --> AGG[Precomputed aggregate]
    AGG --> READ[Dashboard / API đọc]
    SRC --> RECON[Rebuild / Reconciliation]
    RECON --> AGG
~~~

### 10.1. Nguy cơ dual write

Mã giả dễ gặp:

~~~text
UPDATE orders SET status = PAID ...
PUBLISH OrderPaid(eventId, orderId, amount) to broker
~~~

Nếu cập nhật nguồn thành công nhưng ứng dụng chết trước PUBLISH, event không được phát. Nếu publish trước và nguồn ghi thất bại, consumer có thể cập nhật tổng cho nghiệp vụ chưa commit.

### 10.2. Transactional outbox

Nếu database hỗ trợ transaction trong phạm vi nguồn, ghi cả thay đổi nghiệp vụ và bản ghi outbox trong **cùng transaction cục bộ**:

~~~text
TRANSACTION trong Order DB:
    UPDATE order ...
    INSERT outbox(
        eventId,
        aggregateId = orderId,
        version,
        payload,
        status = NEW
    )
COMMIT

Outbox publisher:
    đọc event NEW
    gửi broker
    ghi checkpoint/đánh dấu đã chuyển
~~~

Outbox giúp tránh khoảng trống giữa commit nguồn và ghi dấu ý định phát sự kiện. **Nó không tự bảo đảm exactly-once delivery**: publisher có thể gửi xong rồi mất ACK, dẫn đến gửi lại. Consumer vẫn cần xử lý duplicate.

### 10.3. CDC không tự bảo đảm đúng nghiệp vụ

CDC là cách quan sát thay đổi nguồn, nhưng muốn xây aggregate đúng còn phải:

- Xác định nguồn log và thời điểm một thay đổi được coi là commit.
- Xác định trước/sau (*before/after image*) có sẵn không.
- Có **primary key và version** đủ để suy ra contribution.
- Xử lý insert, update, delete, TTL, transaction nhiều bản ghi.
- Quản lý checkpoint và thứ tự theo partition/stream.
- Khi stream hết retention hoặc consumer mất checkpoint, có phương án snapshot/backfill.
- Chịu được việc event bị phát lại, đến trễ và cập nhật nhiều lần.

CDC có thể tự động hóa việc *phát hiện thay đổi*, nhưng **không thay thế định nghĩa COUNT/SUM, rollback, idempotency hay consistency**.

## 11. Ví dụ MongoDB: tính lại theo lô và cập nhật tăng dần

### 11.1. Backfill bằng aggregation pipeline

Trong MongoDB, một pipeline có thể nhóm các đơn đã thanh toán theo tenant, store, currency và ngày UTC. Ví dụ sử dụng cú pháp tương ứng phiên bản hỗ trợ **$dateTrunc** và **$merge**:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      paidAt: { $exists: true }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        storeId: "$storeId",
        currency: "$currency",
        businessDay: {
          $dateTrunc: {
            date: "$paidAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      paidOrderCount: { $sum: 1 },
      totalPaidMinor: { $sum: "$paidAmountMinor" }
    }
  },
  {
    $merge: {
      into: "daily_sales",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

Ở đây **$merge** ghi kết quả vào collection đích. Pipeline minh họa **batch rebuild/refresh** trên phạm vi dữ liệu có chọn lọc; nó **không làm collection daily_sales tự cập nhật mãi mãi** sau lần chạy này.

Khi dùng trên hệ thật, cần thêm:

- Múi giờ nghiệp vụ, đồng tiền và định nghĩa điều kiện PAID.
- Index phù hợp trên nguồn để giảm chi phí tính lại.
- Điều kiện xử lý những group **không còn bản ghi nguồn nào**: pipeline không tự xóa mọi document nhóm cũ đã biến mất.
- Cách tính lại đồng thời với các thay đổi mới: snapshot/watermark và không ghi đè kết quả realtime mới bằng kết quả batch cũ.
- Quy trình đổi phiên bản/cutover khi backfill toàn bộ aggregate.

Đặc biệt, một lệnh $merge theo từng document kết quả không tự bảo đảm toàn bộ tập aggregate được thay thế như một snapshot atomic duy nhất.

### 11.2. Incremental update bằng $inc

Nếu một event thực sự đã được dedup an toàn và đóng góp là +1 order, +120.000 tiền:

~~~javascript
db.daily_sales.updateOne(
  { _id: "T1:S1:2026-11-14:VND" },
  {
    $inc: {
      paidOrderCount: 1,
      totalPaidMinor: 120000
    },
    $set: { updatedAt: new Date() }
  },
  { upsert: true }
);
~~~

Cả hai field được cập nhật trong **một document update atomic**. Điều này tránh trường hợp có hai consumer cùng đọc tổng rồi ghi đè nhau bằng thao tác SET vô điều kiện.

Nhưng **$inc không idempotent**. Nếu event gửi lại, tổng sẽ tăng lần nữa. Để bảo đảm chính xác phải kết hợp với dedup/projection state trong transaction phù hợp, hoặc một thiết kế reconciliation có độ chính xác được chấp nhận. Ngoài ra, nếu order đổi trạng thái, phải tính **delta cũ/mới** chứ không mặc định mỗi lần update đều cộng.

## 12. Ví dụ DynamoDB: item tổng hợp và conditional write

DynamoDB có thể lưu daily aggregate như một item:

~~~text
PK = TENANT#T1#STORE#S1
SK = DAY#2026-11-14#VND

paidOrderCount = 25
totalPaidMinor = 2500000
~~~

Với một event chưa từng được xử lý, thao tác kiểu **UpdateItem** có thể cập nhật hai thuộc tính số:

~~~text
UpdateExpression:
    SET #count = if_not_exists(#count, :zero) + :one,
        #total = if_not_exists(#total, :zero) + :amount

ExpressionAttributeNames:
    #count = paidOrderCount
    #total = totalPaidMinor

ExpressionAttributeValues:
    :zero = 0
    :one = 1
    :amount = 120000
~~~

UpdateItem thay đổi các thuộc tính trong **một item** theo bảo đảm atomic của API. Nếu nhiều event cùng cập nhật một item, cách tính server-side này tránh lost update của mô hình GET → cộng ở client → PUT.

Nhưng vấn đề vẫn là **event trùng** và **aggregate khác item với order**:

- Nếu chỉ gọi UpdateItem hai lần với cùng event, item sẽ cộng hai lần.
- Nếu muốn transaction ghi **dedup record và aggregate item**, cần xem **TransactWriteItems** và các giới hạn trên số item, vùng và khả năng điều kiện ghi theo phiên bản.
- Nếu một order chuyển sang nhóm ngày/cửa hàng khác, việc trừ nhóm cũ và cộng nhóm mới có thể cần cùng transaction hoặc một workflow bù trừ.
- Nếu item tổng của một store rất nóng, một key duy nhất có thể giới hạn throughput và tạo contention; có thể phải phân mảnh aggregate nếu nghiệp vụ cho phép.

**GSI không phải aggregate SUM/COUNT tự động.** GSI là đường truy cập index phụ đối với item, không thay thế consumer tính tổng.

## 13. Ví dụ Redis: counter và hash phục vụ dashboard

Redis cung cấp thao tác số học trên key/hash:

~~~redis
HINCRBY sales:T1:S1:2026-11-14:VND paidOrderCount 1
HINCRBY sales:T1:S1:2026-11-14:VND totalPaidMinor 120000
HGETALL sales:T1:S1:2026-11-14:VND
~~~

**Mỗi HINCRBY** là một thao tác nguyên tử theo ngữ nghĩa của Redis primary. Nhưng hai lệnh riêng **không phải một đơn vị atomic chung**; nếu ứng dụng chết sau lệnh đầu, số đơn và tổng tiền có thể lệch. Có thể gom hai phép cập nhật vào **Lua script** hoặc transaction phù hợp phạm vi Redis để tránh lệnh khác xen vào giữa các cập nhật trên server.

Ví dụ script nhận một key, delta count và delta amount:

~~~lua
-- KEYS[1]: hash của một group
-- ARGV[1]: delta count, ARGV[2]: delta amount
local count = tonumber(ARGV[1])
local amount = tonumber(ARGV[2])
if not count or not amount then
    return redis.error_reply('invalid delta')
end

redis.call('HINCRBY', KEYS[1], 'paidOrderCount', count)
redis.call('HINCRBY', KEYS[1], 'totalPaidMinor', amount)
return 1
~~~

Script minh họa cách cập nhật nhất quán **hai field trong một key**, nhưng không kèm dedup hoặc transaction với dữ liệu nguồn. Nếu script bị chạy lại sau timeout, nó lại cộng lần nữa. Hơn nữa, Redis có các lựa chọn persistence/replication/failover; không được coi một hash là ledger tài chính duy nhất nếu bảo đảm durability không phù hợp.

Một kiến trúc thường gặp:

~~~text
Nguồn đơn/ledger bền vững
    -> event pipeline idempotent
    -> aggregate store bền vững hoặc snapshot
    -> Redis cache cho dashboard
~~~

Nếu Redis chỉ là cache, khi key hết hạn hay cache mất dữ liệu phải có cách **tái tạo từ nguồn chuẩn**. TTL cần bám theo retention; không được để key tự reset gây mất số liệu nếu dashboard coi đó là dữ liệu vĩnh viễn.

## 14. Cột rộng: bảng tổng hợp và cẩn trọng với counter

Trong Cassandra/ScyllaDB, có thể tạo bảng tổng hợp theo partition và thời gian để đọc nhanh. Tuy nhiên, **tổng hợp được lưu sẵn không tự đồng nghĩa với MATERIALIZED VIEW của CQL**. Materialized view theo CQL chủ yếu biểu diễn dữ liệu theo khóa truy cập khác; nó không phải một cơ chế tự động SUM/COUNT bất kỳ giống một view tổng hợp của SQL analytics.

### 14.1. Bảng theo query

~~~sql
CREATE TABLE daily_sales_by_store (
    tenant_id text,
    store_id text,
    year_bucket int,
    business_day date,
    currency text,
    paid_order_count bigint,
    total_paid_minor bigint,
    updated_at timestamp,
    PRIMARY KEY (
        (tenant_id, store_id, year_bucket),
        business_day,
        currency
    )
);
~~~

Đường đọc:

~~~sql
SELECT business_day, currency, paid_order_count, total_paid_minor
FROM daily_sales_by_store
WHERE tenant_id = ?
  AND store_id = ?
  AND year_bucket = ?;
~~~

**year_bucket** chỉ là một ví dụ chống partition tăng vô hạn. Nếu mỗi cửa hàng có ít ngày dữ liệu, thêm bucket quá nhỏ sẽ tăng overhead. Nếu aggregate theo từng giờ, loại sản phẩm hay nhiều dimension, số dòng mỗi partition thay đổi mạnh; cần ước lượng theo workload.

### 14.2. Counter column có hạn chế riêng

Cassandra cung cấp **counter column** với cú pháp tăng/giảm, ví dụ:

~~~sql
UPDATE page_views_by_day
SET view_count = view_count + 1
WHERE page_id = ? AND business_day = ?;
~~~

Mẫu trên giả định bảng đã được thiết kế đúng cho counter. Counter có **quy tắc schema, consistency và retry riêng** theo Cassandra. Khi client gửi increment, server thực thi nhưng phản hồi bị mất, retry có thể làm tăng lần nữa. Không được dùng counter thuần làm cơ chế duy nhất bảo vệ “mỗi thanh toán chỉ ghi nhận một lần” nếu thiếu idempotency và reconciliation.

Muốn có **đúng một đóng góp theo event** có thể cần mô hình ledger/dedup và pipeline tổng hợp có thể dựng lại, thay vì mặc định counter giải quyết mọi thứ. Batch CQL cũng không tự tạo transaction có rollback và isolation tổng quát xuyên nhiều partition.

## 15. Các chiến lược xây lại tổng và đối soát

Dù đã có xử lý delta, hệ thống vận hành dài hạn vẫn có thể lệch do lỗi code, mất event quá thời gian retention, nhập dữ liệu từ hệ cũ hoặc migration không đầy đủ. Cần xem **rebuild/reconciliation** là một phần của thiết kế, không phải nhiệm vụ khẩn cấp chỉ làm khi số liệu sai.

### 15.1. Reconciliation theo group

~~~text
Chọn group:
    (tenant T1, store S1, ngày D, currency VND)

Tính expected từ nguồn chuẩn:
    expectedCount
    expectedTotal

Đọc aggregate hiện tại:
    actualCount
    actualTotal

So sánh:
    mismatchCount = expectedCount - actualCount
    mismatchTotal = expectedTotal - actualTotal

Nếu lệch:
    ghi nhận và sửa bằng cơ chế có version/snapshot an toàn.
~~~

Chỉ so sánh trực tiếp **expected tính lúc T0** với **actual đọc lúc T1** có thể báo lệch giả nếu nguồn vẫn đang thay đổi. Cần dùng **snapshot, watermark, trạng thái kết thúc kỳ hoặc quy tắc xử lý concurrent updates**.

### 15.2. Rebuild sang bản mới rồi đổi phiên bản

Một mẫu an toàn hơn việc ghi đè từng group trực tiếp khi đang phục vụ:

~~~text
Aggregate version V1 -> đang phục vụ API.

Rebuild:
    chốt nguồn/snapshot hoặc watermark W
    đọc nguồn và tính toàn bộ group cho V2
    áp dụng/đối soát thay đổi phát sinh sau W
    xác minh V2 đã bắt kịp
    chuyển đường đọc từ V1 sang V2
    giữ V1 để rollback trong một khoảng phù hợp
~~~

Cách cutover cụ thể tùy database. Khi không có snapshot toàn cục hoặc CDC nhất quán, việc nạp dữ liệu và replay có thể khó hơn nhiều: phải thiết kế checkpoint và dedup để **không bỏ sót cũng không đếm trùng** giữa phần backfill và phần realtime.

### 15.3. Rebuild chỉ các group bị ảnh hưởng

Nếu có thể xác định order nào sửa đổi, hệ không cần tái tính tất cả group mỗi lần. Có thể:

1. Ghi các group bị đánh dấu **dirty**.
2. Batch đọc lại nguồn cho những group đó.
3. Ghi kết quả mới kèm version/watermark.
4. Đảm bảo không ghi đè kết quả mới hơn.
5. Đo backlog và thời gian từ lúc dirty đến lúc repaired.

Cách này đặc biệt hữu ích với **MIN/MAX**, top-K hoặc số lượng distinct chính xác, khi một thay đổi có thể khiến cần tìm lại ứng viên khác.

## 16. Sự kiện muộn, ngày nghiệp vụ và cửa sổ thời gian

Những tổng hợp theo ngày/giờ có hai loại thời gian:

- **Event time:** thời điểm nghiệp vụ xảy ra, ví dụ paidAt.
- **Processing time:** lúc consumer nhận và xử lý event.

Giả sử thanh toán thực tế diễn ra lúc 23:59 ngày 13/11 theo UTC, nhưng event đến consumer lúc 00:02 ngày 14/11. Nếu nhóm theo **processing time**, số liệu vào ngày 14; nếu nhóm theo **paidAt**, số liệu thuộc ngày 13. Không có đáp án chung; phải chọn theo định nghĩa báo cáo.

### Múi giờ cửa hàng

~~~text
paidAt UTC: 2026-11-14T17:30:00Z

Tại UTC+7:
    thời gian địa phương = 2026-11-15 00:30
    businessDay = 2026-11-15 nếu dùng timezone đó.
~~~

Nếu cửa hàng đổi timezone trong cấu hình, có thể ảnh hưởng cách tính các đơn lịch sử. Nên định nghĩa chính sách: timezone được cố định theo thời điểm giao dịch hay dùng cấu hình hiện hành khi tính lại? Dữ liệu cần lưu đủ ngữ cảnh để rebuild không làm thay đổi ngày ngoài ý muốn.

### Watermark không phải lý do bỏ mọi sự kiện trễ

Trong stream processing, watermark thường được dùng để ước lượng mức hoàn tất dữ liệu theo event time. Sự kiện đến sau watermark cần có **late-event policy**: cập nhật lại group cũ, đẩy vào kênh correction, đưa vào báo cáo điều chỉnh hoặc bỏ qua có ghi nhận nếu nghiệp vụ chấp thuận.

Không được âm thầm loại thanh toán hoặc hoàn tiền đến muộn chỉ để dashboard “đã chốt” nhanh hơn. Nếu kỳ báo cáo có giai đoạn **preliminary → final → adjusted**, phải làm rõ thời điểm và ai được quyền sửa kỳ đã chốt.

## 17. Trường hợp nhiều nhóm tổng và một thay đổi nguồn

Một đơn có thể đóng góp đồng thời vào:

~~~text
sales_by_store_day
sales_by_tenant_day
sales_by_product_day
paid_orders_by_customer
orders_by_status
~~~

Nếu một order đổi trạng thái hoặc số tiền, event có thể làm thay đổi **nhiều bản tổng**. Khi tất cả các read model cập nhật bất đồng bộ, chúng có thể tạm thời không đồng nhất:

~~~text
10:00:00  Order O-101 commit PAID.
10:00:01  sales_by_store_day cập nhật xong.
10:00:03  sales_by_tenant_day cập nhật xong.
10:00:05  orders_by_status cập nhật xong.
~~~

Điều này có thể hợp lệ nếu từng API có **freshness SLO** riêng. Nhưng nếu một màn hình cùng lúc hiển thị doanh thu theo store và tổng tenant và yêu cầu chúng luôn cộng khớp ở mọi thời điểm, hai bản chiếu cập nhật độc lập có thể không đáp ứng. Có thể:

- Tính tổng tenant từ các group cửa hàng **cùng snapshot/watermark** khi đọc.
- Ghi nhiều group trong một transaction nếu phạm vi/chi phí cho phép.
- Chụp một **snapshot version** và chỉ công bố khi tất cả group đã bắt kịp.
- Cho phép sai lệch tạm thời nhưng hiển thị thời điểm cập nhật và trạng thái “đang đồng bộ”.

**Không có một mô hình bất đồng bộ miễn phí vừa cập nhật tức thì vừa bảo đảm các bản tổng đồng nhất trên mọi đường đọc.** Phải quyết định theo yêu cầu nghiệp vụ.

## 18. Hot key và sharded counter

Một tổng duy nhất cho toàn hệ có thể trở thành điểm nóng:

~~~text
sales:all-stores:today
     ^  ^  ^  ^  ^
   mọi payment đều cập nhật
~~~

Nếu throughput cao, hàng nghìn writer cùng sửa một key/item có thể tạo tranh chấp và giới hạn khả năng mở rộng. Một phương án cho chỉ số thống kê là chia tổng thành nhiều shard:

~~~text
sales:today:shard:0 = 120000
sales:today:shard:1 =  95000
sales:today:shard:2 = 130000
sales:today:shard:3 = 105000

Total khi đọc = 450000
~~~

### Đánh đổi

- Ghi được phân tán hơn, nhưng đọc tổng phải lấy nhiều shard và cộng.
- Các shard có thể được đọc tại những thời điểm khác nhau; không tự có snapshot nhất quán toàn cục.
- Nếu giữ thêm một tổng cache, phải giải quyết quá trình cache chậm hoặc sai.
- Thay số shard cần quy tắc version/routing để không bỏ sót dữ liệu cũ.
- Một event gửi lại vẫn có thể cộng trùng, kể cả khi hash đến cùng shard.
- Khi có xóa/correction, cần biết shard nào đã nhận contribution trước đó.

Sharded counter phù hợp hơn với thống kê có thể **chấp nhận độ trễ hội tụ hoặc dựng lại**. Nếu tổng là nguồn quyết định **không được vượt quota toàn cục**, việc chia shard độc lập không đủ; cần **phân bổ hạn mức (escrow)** hoặc một cơ chế điều phối bảo vệ bất biến tổng.

## 19. Định nghĩa freshness và trạng thái kết quả

Một API đọc aggregate phải nói rõ dữ liệu được cập nhật gần đến đâu.

Ví dụ:

~~~json
{
  "tenantId": "T1",
  "storeId": "S1",
  "businessDay": "2026-11-14",
  "currency": "VND",
  "paidOrderCount": 250,
  "totalPaidMinor": 25300000,
  "computedAt": "2026-11-14T10:00:08Z",
  "sourceWatermark": "orders-change-stream:partition-3:offset-90123",
  "completeness": "PROVISIONAL"
}
~~~

**computedAt** là thời điểm record được tính/ghi; nó không nhất thiết đồng nghĩa mọi sự kiện nghiệp vụ trước thời điểm đó đều đã được xử lý. **sourceWatermark** hoặc thông tin checkpoint đáng tin cậy sẽ có ích hơn để mô tả phạm vi nguồn đã xử lý. Nếu dữ liệu đến từ nhiều partition/stream, một offset duy nhất không nhất thiết đại diện cho mức hoàn tất toàn bộ nguồn.

### Các trạng thái hữu ích

| Trạng thái | Ý nghĩa |
| --- | --- |
| **PROVISIONAL** | Tổng có thể còn thay đổi vì event trong kỳ chưa đến đủ. |
| **UP_TO_DATE** | Đã xử lý nguồn đến watermark/điều kiện đồng bộ được công bố. |
| **STALE** | Độ trễ hoặc backlog vượt ngưỡng cho phép. |
| **REBUILDING** | Đang tính lại, có thể phục vụ bản trước theo chính sách. |
| **FINALIZED** | Kỳ đã chốt theo quy định nghiệp vụ, có quy tắc điều chỉnh về sau. |
| **UNKNOWN** | Không xác định được trạng thái mới do lỗi nguồn/consumer. |

Không tự gắn **UP_TO_DATE** chỉ vì consumer đang chạy. Cần đo consumer lag và khả năng hoàn tất theo từng partition, cùng xử lý late event/replica lag.

### SLI độ tươi

Một cách định nghĩa:

~~~text
aggregationLag(event):
    = thời điểm read model thể hiện đúng đóng góp của event
      - thời điểm event nguồn được commit theo hợp đồng

Freshness SLO:
    p99(aggregationLag) <= ngưỡng đã thống nhất
~~~

Khi event chưa xuất hiện trong thời hạn đo, phải tính là vi phạm/timeout theo định nghĩa, không loại khỏi mẫu. Ngoài percentile, có thể cần **max lag và age của backlog** để phát hiện một partition bị kẹt nhiều giờ dù đa số event xử lý nhanh.

## 20. Khóa idempotency và retention của lịch sử xử lý

Một dedup table không thể tăng mãi mãi mà không có kế hoạch dung lượng. Nhưng xóa eventId quá sớm lại mở cửa sổ cho message cũ được phát lại rồi cộng lần nữa.

Khi chọn retention:

- Broker có thể replay event cũ tối đa bao lâu?
- Có batch backfill hoặc reprocess dữ liệu nhiều năm không?
- Một payment dispute có thể làm sửa bản ghi cũ sau bao lâu?
- Projection state theo **entity version** có giúp bỏ qua event cũ dù dedup eventId đã hết hạn không?
- Khi xóa/khôi phục entity, version/token có bị tái sử dụng gây lỗi ABA không?
- Snapshot/rebuild có reset bảng processedEvents theo một generation mới không?

Một chiến lược bền vững là lưu **contribution state/version theo entity** cho các nhóm phải chính xác, nhưng chi phí có thể lớn gần tương đương số entity nguồn. Nếu chấp nhận thống kê gần đúng, có thể chọn pipeline ít trạng thái hơn kết hợp reconciliation định kỳ. Đây là đánh đổi **storage + write cost để đổi lấy khả năng chống trùng và sửa đổi chính xác**.

## 21. Khi tổng hợp được dùng để ra quyết định nghiệp vụ

Cùng một trường **remainingQuota** có thể dùng cho dashboard và để quyết định cho phép request. Nếu nó chỉ là aggregate bất đồng bộ, hai request đồng thời có thể cùng đọc quota còn 1 và cùng được chấp nhận, gây vượt quota.

~~~text
Dashboard:
    số lượt sử dụng ngày hôm nay cập nhật sau vài giây
    -> có thể chấp nhận theo hợp đồng.

Quyết định:
    còn suất cuối cùng, hai request tranh suất
    -> cần primitive atomic/conditional hoặc escrow.
~~~

Không nên lấy một số liệu báo cáo để bảo vệ bất biến giao dịch trừ khi **nơi ghi tổng thực sự có ranh giới atomic và nhất quán phù hợp**. Nếu muốn vừa nhanh vừa bảo vệ quota, có thể tách:

1. **Nguồn quyết định quota:** cập nhật có điều kiện, transaction hoặc token/escrow.
2. **Bản tổng hiển thị:** projection có thể hội tụ sau, cập nhật từ sự kiện nguồn.

Tương tự, doanh thu trên dashboard không nên là ledger thanh toán duy nhất. Ledger nguồn và audit trail thường cần mức bảo đảm riêng để đáp ứng điều chỉnh và đối soát.

## 22. Tránh các lỗi thiết kế thường gặp

**“COUNT lưu sẵn cứ cộng một khi nhận event.”** Không đúng khi có event trùng, update/xóa, chuyển group hoặc nhiều trạng thái không được tính. Cần contribution old/new và idempotency.

**“Có atomic increment là đã exactly-once.”** Atomic chỉ bảo vệ một lần cập nhật cụ thể. Retry sau timeout có thể thực thi lần thứ hai.

**“Cứ ghi processedEvent trước rồi cập nhật tổng.”** Crash giữa hai bước có thể làm mất contribution. Đổi thứ tự cũng có thể gây cộng trùng. Cần transaction hoặc recovery protocol.

**“Đã có CDC thì aggregate luôn chính xác.”** CDC cung cấp thay đổi nguồn, nhưng consumer vẫn phải định nghĩa filter, group, delta, version, xóa và replay.

**“Cùng một ngày là cùng một key, không cần timezone.”** Một timestamp gần nửa đêm có thể thuộc ngày khác theo timezone cửa hàng; thiếu quy tắc sẽ làm số liệu biến động khi rebuild.

**“AVG chỉ cần lưu trung bình.”** Khi thêm, sửa hoặc xóa review, thiếu sum và count khiến cập nhật khó đúng.

**“Materialized view của mọi NoSQL đều biết GROUP BY SUM.”** Tên tính năng khác nhau theo sản phẩm; CQL materialized view, DynamoDB GSI và một bảng aggregate ứng dụng tự duy trì là ba cơ chế khác nhau.

**“$merge chạy một lần nghĩa là collection tổng cập nhật tự động.”** Một pipeline batch không tự biến thành subscription với mọi thay đổi về sau.

**“Có tổng tenant và tổng store riêng, chắc chắn lúc nào cũng khớp.”** Những bản chiếu độc lập có thể chậm khác nhau; cần version/snapshot hoặc hợp đồng chấp nhận lag.

**“Tổng đúng trong test nhỏ sẽ đúng khi có 100 consumer.”** Đồng thời, crash giữa bước, retry và reordering là nơi lỗi tổng hợp bộc lộ.

**“Sau khi backfill xong có thể chuyển traffic ngay.”** Cần đảm bảo thay đổi xảy ra trong khi backfill không bị bỏ sót hoặc cộng hai lần, và index/projection đã đạt watermark cần thiết.

## 23. Kế hoạch kiểm thử cho bản tổng hợp

### 23.1. Kiểm thử kết quả số học

Chuẩn bị tập đơn nhỏ có thể tính độc lập:

~~~text
O1: PAID, 120000
O2: PAID,  80000
O3: PENDING, 50000
Expected:
    paidOrderCount = 2
    totalPaid = 200000
~~~

Sau đó đổi O2 từ 80.000 thành 90.000 theo chính sách cho phép:

~~~text
Expected:
    paidOrderCount = 2
    totalPaid = 210000
~~~

Xóa/hủy O1 theo quy tắc chỉ số đã định nghĩa thì expected phải điều chỉnh tương ứng. Kiểm tra cả giá trị âm, số bằng 0, đồng tiền khác và các bản ghi không đủ field.

### 23.2. Kiểm thử duplicate delivery

Gửi cùng eventId 10 lần, từ nhiều consumer song song. Sau mọi lần, tổng vẫn bằng **một hiệu ứng nghiệp vụ**. Không chỉ kiểm tra response 200; phải đối soát record tổng và lịch sử contribution.

### 23.3. Kiểm thử out-of-order

Gửi order version 8, 10 rồi 9. Kết quả cuối phải tương ứng version 10 hoặc consumer phải phát hiện gap và phục hồi theo hợp đồng; không được quay về version 9.

### 23.4. Kiểm thử lỗi giữa các bước

Tiêm lỗi:

~~~text
Sau ghi aggregate nhưng trước ghi dedup.
Sau ghi dedup nhưng trước ghi aggregate.
Sau commit nguồn nhưng trước publish.
Sau publish nhưng trước ACK broker.
Sau trừ group cũ nhưng trước cộng group mới.
Trong lúc rebuild và có event mới.
~~~

Kỳ vọng phụ thuộc kiến trúc: transaction làm cả hai cùng commit/hủy, hoặc workflow có thể phát hiện và sửa sai. Không được để sai lệch vĩnh viễn mà không có chỉ số/cách khôi phục.

### 23.5. Kiểm thử thời gian

Dùng event thực hiện ở sát ranh giới ngày theo timezone cửa hàng. Thử sự kiện đến trễ nhiều giờ, hoàn tiền của kỳ cũ, thay đổi businessDay và lần rebuild sau khi kỳ đã chốt.

### 23.6. Kiểm thử hot key và scalability

Cho một store nổi tiếng tạo hàng nghìn payment mỗi giây trong khi các store khác ít tải. Đo latency cập nhật aggregate, contention, retries, CPU node nóng, backlog consumer và khả năng phân shard. Không chỉ dùng số RPS tổng đều khắp các group.

### 23.7. Kiểm thử rebuild và cutover

Cho consumer realtime vẫn nhận dữ liệu, bắt đầu rebuild bản mới từ snapshot rồi replay delta, chuyển đường đọc khi bắt kịp. Kiểm chứng không mất event, không đếm trùng, có đường rollback và kết quả so với nguồn chuẩn.

## 24. Ma trận nghiệm thu minh họa

Giả sử màn hình doanh thu theo ngày phục vụ nội bộ và được phép trễ vài giây. Các số sau **chỉ là ví dụ**, không phải khuyến nghị cố định:

| Mã | Điều kiện | Cách đo |
| --- | --- | --- |
| AC-01 | COUNT/SUM đúng trên tập dữ liệu có insert/update/delete/refund | So kết quả với nguồn chuẩn |
| AC-02 | Replay cùng event không tăng tổng lần hai | Tiêm duplicate và đối soát |
| AC-03 | Event đảo thứ tự không làm giảm version đã áp dụng | Kiểm thử v8/v10/v9 |
| AC-04 | p99 độ trễ từ commit nguồn đến aggregate đúng ≤ 5 giây | Gắn eventId và đo timestamp/watermark |
| AC-05 | API đọc aggregate p95 ≤ 120 ms ở tải quy định | Load test end-to-end |
| AC-06 | Có thể xử lý ít nhất 3 lần tải event đỉnh giả định trong thời gian phục hồi | Stress/backlog drain |
| AC-07 | Rebuild tạo kết quả khớp nguồn và cutover không mất event | Snapshot + replay + reconciliation |
| AC-08 | Sai lệch nguồn–aggregate được phát hiện/cảnh báo | Mismatch count, age, correction log |
| AC-09 | Không cộng chéo tiền tệ hoặc sai ngày theo timezone | Bộ case ranh giới |
| AC-10 | Hot group không làm nghẽn vô hạn toàn pipeline | CPU, queue age, retry và throughput theo group |

Với số liệu tài chính, tiêu chí **tính đúng và khả năng đối soát** là điều kiện bắt buộc; không được lấy p95 tốt để bù cho tiền bị cộng trùng. Nếu nhóm muốn SLO freshness dài hạn, một lần load test ngắn chưa đủ để chứng minh mọi kỳ vận hành đều đáp ứng.

### Các metric nên có

~~~text
aggregate_updates_total
aggregate_update_failures_total
duplicate_events_ignored_total
out_of_order_events_total
version_gaps_detected_total
consumer_backlog_messages
oldest_unprocessed_event_age_seconds
aggregation_freshness_seconds
rebuild_duration_seconds
rebuild_catchup_lag_seconds
reconciliation_mismatch_groups
reconciliation_amount_difference_minor
hot_aggregate_key_write_latency_p99
~~~

Tên metric là gợi ý; giá trị thực phụ thuộc hệ thống observability và cách định nghĩa sự kiện nguồn. Theo dõi **age của event chưa xử lý lâu nhất** giúp phát hiện một partition mắc kẹt mà tốc độ xử lý trung bình có thể che giấu.

## 25. Mẫu thiết kế tổng hợp có thể dùng trong dự án

~~~yaml
aggregate:
  name: daily_sales_by_store
  purpose: "Hiển thị doanh thu theo ngày của từng cửa hàng"
  sourceOfTruth: "Orders/Payments ledger đã commit"
  groupKey:
    - tenantId
    - storeId
    - businessDay
    - currency
  businessDayRule: "Ngày của giao dịch theo timezone đã chốt"
  metrics:
    paidOrderCount: "Số order đủ điều kiện, duy nhất theo orderId"
    totalPaidMinor: "Tổng giá trị thanh toán theo đơn vị tiền nhỏ"
    refundedMinor: "Tổng refund theo chính sách ghi nhận"
    netMinor: "totalPaidMinor - refundedMinor"
  contributionIdentity: orderId
  sourceVersionField: version
  updateMode: "CDC/event -> consumer tính delta"
  deduplication: "eventId hoặc contribution state/version"
  atomicityBoundary: "Cần điền cụ thể theo database"
  consistency:
    mode: "Eventually consistent read model"
    freshnessSlo: "p99 <= ngưỡng được duyệt"
  lateEventPolicy: "Reopen/correct group theo quy định báo cáo"
  rebuild:
    sourceSnapshot: "Snapshot/watermark nhất quán"
    catchUp: "Replay delta sau watermark, chống lặp"
    reconciliation: "So với nguồn chuẩn theo group"
  observability:
    - "Consumer lag"
    - "Oldest unprocessed event"
    - "Reconciliation mismatch"
    - "Aggregate write latency"
  retention:
    source: "Theo chính sách dữ liệu"
    dedupRecords: "Đủ cho cửa sổ replay và sửa lịch sử"
    aggregate: "Theo thời hạn báo cáo"
~~~

Khi áp dụng, phải thay những đoạn mô tả chung như “cần điền cụ thể” bằng **API, transaction scope, topology, version và ngưỡng số cụ thể**. Mẫu này đóng vai trò hợp đồng giữa backend, data engineering, SRE và người dùng báo cáo.

## 26. Quy trình thiết kế từng bước

~~~mermaid
flowchart TD
    A[Liệt kê query và công thức metric] --> B[Chọn nguồn sự thật, khóa nhóm, timezone]
    B --> C{Tính khi đọc có đạt SLO?}
    C -->|Có| D[Ưu tiên query trực tiếp nếu chi phí hợp lý]
    C -->|Không| E[Thiết kế precomputed aggregate]
    E --> F[Chọn sync transaction, event/CDC hoặc batch]
    F --> G[Định nghĩa contribution old/new và group movement]
    G --> H[Idempotency, ordering, version và xử lý lỗi]
    H --> I[Backfill/rebuild và reconciliation]
    I --> J[Benchmark tải, hot key, freshness, correctness]
    J --> K[Rollout theo version và theo dõi vận hành]
    D --> K
~~~

Một trình tự thực hiện cụ thể:

1. **Viết công thức chính xác:** COUNT gì, SUM gì, nhóm theo thuộc tính nào, timezone và currency nào, khi nào một record đủ điều kiện?
2. **Xác định nguồn sự thật:** aggregate được dựng từ dữ liệu nào có khả năng audit/replay?
3. **Ước lượng chi phí tính khi đọc:** tập bản ghi, độ chọn lọc và QPS có thật sự đòi lưu trước không?
4. **Thiết kế key/schema:** chọn chiều nhóm tối thiểu đủ cho API; tránh nhóm toàn cục quá nóng và partition không giới hạn.
5. **Chọn chế độ cập nhật:** transaction đồng bộ, CDC/outbox hoặc batch; ghi rõ độ trễ được phép.
6. **Mô tả delta:** insert, update, delete, chuyển group, refund và event muộn tác động thế nào?
7. **Thiết kế chống trùng:** eventId, business ID, source version, transaction cùng aggregate hoặc giao thức phục hồi.
8. **Định nghĩa đường đọc:** dữ liệu nào được coi là tươi, khi nào hiển thị stale/rebuilding/finalized?
9. **Chuẩn bị rebuild:** snapshot, watermark, catch-up, đối soát và cutover.
10. **Thử tải và lỗi:** cạnh tranh một hot key, duplicate, out-of-order, crash tại mọi ranh giới và failover.
11. **Bổ sung metric và vận hành:** consumer lag, mismatch, alert, retention, ownership và quy trình khắc phục.

## Kết luận

**Tổng hợp được lưu sẵn** là một kỹ thuật lặp dữ liệu có chủ đích để phục vụ truy vấn COUNT, SUM, AVG, bảng xếp hạng hoặc thống kê theo nhóm với chi phí đọc ổn định hơn. Nó đặc biệt hữu ích khi NoSQL được thiết kế theo khóa truy cập và việc quét dữ liệu nguồn cho mỗi request quá tốn kém.

Nhưng **đọc nhanh hơn đồng nghĩa phải chịu trách nhiệm cập nhật đúng hơn**: phân biệt nguồn và bản chiếu, định nghĩa contribution cũ/mới, xử lý dữ liệu đổi trạng thái hoặc đổi nhóm, chống event trùng/sai thứ tự, xác định mức nhất quán và độ tươi, đồng thời luôn có cách rebuild/đối soát. Không được suy từ atomic increment ra exactly-once, từ CDC ra số liệu đúng tuyệt đối hay từ materialized view của một sản phẩm ra cơ chế aggregate có sẵn của mọi NoSQL.

Một thiết kế đáng tin cậy trả lời trọn vẹn bốn câu hỏi: **Tổng hợp biểu diễn điều gì? Nó được cập nhật từ nguồn nào và bằng giao thức nào? Khi sai hoặc chậm thì phát hiện và sửa ra sao? Đã có bằng chứng rằng nó đúng dưới retry, cạnh tranh và sự cố chưa?**
