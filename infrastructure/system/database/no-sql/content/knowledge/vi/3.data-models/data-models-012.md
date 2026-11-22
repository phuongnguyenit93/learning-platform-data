# Lựa chọn mô hình theo nhu cầu thay vì suy luận từ nhãn sản phẩm

Trong hệ sinh thái NoSQL, chúng ta thường nghe những nhận định như “document database linh hoạt”, “key–value nhanh”, “wide-column mở rộng tốt”, “graph database mạnh về quan hệ” hoặc “NoSQL không có transaction”. Mỗi nhận định có thể mô tả một đặc điểm thường gặp, nhưng **không đủ để quyết định cách lưu dữ liệu cho một ứng dụng cụ thể**. Hai cơ sở dữ liệu cùng mang nhãn *document* vẫn có thể khác nhau về chỉ mục, transaction, partition key, consistency, replication, giới hạn kích thước và chi phí. Ngược lại, một sản phẩm có thể hỗ trợ nhiều cách truy cập thường được gắn với các họ mô hình khác nhau.

Tư duy thiết kế hữu ích hơn là đi từ **nhu cầu của hệ thống**: người dùng thực hiện thao tác nào, dữ liệu liên hệ với nhau ra sao, bất biến nghiệp vụ nào phải giữ, truy vấn nào chiếm tải lớn nhất, dữ liệu tăng nhanh đến đâu và đội ngũ có khả năng vận hành những gì. Sau đó mới chọn **mô hình logic**, **cách biểu diễn vật lý**, **đường truy cập** và cuối cùng là **sản phẩm triển khai**.

Bài học này đặt trọng tâm vào phương pháp ra quyết định trong phạm vi Database No SQL, không xếp hạng các nhãn sản phẩm theo kiểu một mô hình “tốt nhất” cho mọi tình huống.

## 1. Đừng dùng nhãn sản phẩm thay cho yêu cầu

Giả sử nhóm phát triển xây một nền tảng bán hàng có các chức năng:

- Tra cứu chi tiết đơn hàng theo mã đơn.
- Hiển thị 20 đơn mới nhất của mỗi khách hàng.
- Giữ số lượng tồn kho chính xác khi nhiều người đồng thời đặt mua.
- Đề xuất sản phẩm dựa trên quan hệ giữa người dùng, sở thích và sản phẩm.
- Tạo báo cáo doanh thu theo thời gian.

Nếu bắt đầu bằng câu “cả hệ thống nên dùng document database” vì đơn hàng có cấu trúc JSON, ta chưa trả lời được nhiều vấn đề: truy vấn theo khách hàng cần chỉ mục gì, cập nhật kho có ranh giới nguyên tử nào, duyệt quan hệ đề xuất có hiệu quả hay không, và báo cáo tổng hợp có ảnh hưởng luồng giao dịch không.

Nếu bắt đầu bằng câu “graph database hỗ trợ quan hệ nên dùng cho tất cả”, ta cũng chưa biết các lần đọc đơn hàng theo khóa chính hay tính tổng doanh thu có hiệu quả và đơn giản hơn hay không.

**Tên họ cơ sở dữ liệu là một gợi ý về cách tư duy; nó không chứng minh hệ thống đáp ứng workload cụ thể.** Mỗi lựa chọn cần được kiểm chứng bằng đường truy cập và bảo đảm thực tế.

### 1.1. Bốn lớp quyết định khác nhau

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Mô hình nghiệp vụ** | Những thực thể, quan hệ và bất biến nào tồn tại? | Đơn hàng có các dòng hàng; sản phẩm có tồn kho; khách hàng thuộc tenant |
| **Mô hình dữ liệu** | Biểu diễn những thực thể đó bằng gì? | Document đơn hàng; key–value trạng thái phiên; đỉnh/cạnh trong graph |
| **Mô hình truy cập vật lý** | Bản ghi được định vị, sắp xếp, chỉ mục và phân vùng thế nào? | Khóa **tenantId + orderId**, chỉ mục **customerId + createdAt** |
| **Khả năng sản phẩm/hạ tầng** | Hệ cụ thể bảo đảm và giới hạn gì? | Điều kiện ghi, transaction nhiều mục, kiểu index, replication, throughput, backup |

Chọn “document” ở lớp mô hình dữ liệu **không tự động chọn** được index, isolation level hay khu vực lưu dữ liệu. Chọn một sản phẩm được quảng bá là “multi-model” cũng **không tự động bảo đảm** mọi mô hình và mọi truy vấn đều tối ưu như nhau.

### 1.2. Phân biệt cấu trúc dữ liệu, cách truy vấn và ràng buộc vận hành

Một đơn hàng có thể tự nhiên được trình bày như JSON, nhưng nhu cầu truy cập mới là yếu tố quyết định cách lưu:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-27",
  "createdAt": "2026-11-14T08:00:00Z",
  "items": [
    {"sku": "SKU-1", "quantity": 2, "unitPrice": 150000},
    {"sku": "SKU-7", "quantity": 1, "unitPrice": 230000}
  ],
  "total": 530000
}
~~~

Từ JSON đó chưa thể suy ra:

1. Người dùng chủ yếu đọc **cả đơn** hay chỉ cần một vài trường?
2. Danh sách **items** có giới hạn hay tăng không ngừng?
3. Hai tiến trình có thể cùng sửa **items** hoặc **total** không?
4. Truy vấn có thường tìm theo **customerId**, **status**, **createdAt**?
5. Khóa phân vùng có làm một khách hàng lớn trở thành điểm nóng không?
6. Có phải lấy dữ liệu từ nhiều khu vực địa lý, nhiều tenant hoặc nhiều hệ thống không?

Cấu trúc giống JSON chỉ nói về hình dạng của một bản ghi, chưa đủ để xác định **đường truy cập**, **transaction** và **khả năng vận hành**.

## 2. Bắt đầu bằng workload: người dùng và hệ thống thực sự làm gì?

**Workload** là tổng hợp các thao tác đọc/ghi, khối lượng dữ liệu, phân phối tải và các yêu cầu về độ trễ, nhất quán, tính sẵn sàng. Thiết kế dữ liệu cần diễn tả workload thành những câu hỏi có thể đo.

### 2.1. Viết access pattern trước khi chọn database

Một access pattern trả lời: **ai cần dữ liệu gì, biết khóa nào, lọc/sắp xếp theo gì, với tần suất và mức độ mới nào?**

Ví dụ:

| Mã | Thao tác | Dữ liệu đầu vào | Kết quả | Tần suất / yêu cầu |
|---|---|---|---|---|
| A1 | Xem chi tiết đơn | **tenantId, orderId** | Một đơn và các dòng hàng | Đọc nhiều, phản hồi nhanh |
| A2 | Xem lịch sử khách | **tenantId, customerId** | 20 đơn gần nhất, phân trang theo thời gian | Đọc nhiều, thứ tự ổn định |
| A3 | Giữ hàng | **sku, quantity, reservationId** | Giữ thành công hoặc hết hàng | Ghi cạnh tranh; không được giữ quá tồn |
| A4 | Xem danh sách chờ xử lý | **tenantId, status, time** | Các đơn theo trạng thái | Đọc và cập nhật theo lô |
| A5 | Gợi ý sản phẩm | **userId** cùng quan hệ hành vi | Tập sản phẩm liên quan, xếp hạng | Độ trễ có giới hạn; tính toán có thể tiền xử lý |
| A6 | Báo cáo theo tháng | Khoảng thời gian, tenant, kênh bán | Tổng hợp và phân nhóm | Khối lượng lớn; có thể bất đồng bộ |

Nếu chỉ mô tả “ứng dụng quản lý đơn hàng”, rất dễ lựa chọn theo cảm giác. Khi đã viết A1–A6, ta có thể đánh giá từng mô hình bằng **đường đi của chính những truy vấn đó**.

### 2.2. Các đại lượng quyết định khác biệt giữa mô hình

- **Số bản ghi và kích thước:** 100.000 hay 10 tỷ bản ghi, kích thước trung bình và bản ghi lớn nhất.
- **Phân phối khóa:** số lượng giá trị phân biệt của khóa (*cardinality*), tenant hoặc SKU nóng, độ lệch tải.
- **Tỷ lệ đọc/ghi:** đọc nhiều với cập nhật ít, hay ingest liên tục hàng triệu sự kiện?
- **Hình dạng truy vấn:** biết ID, lấy danh sách có thứ tự, lọc nhiều chiều, duyệt nhiều cấp quan hệ, tìm kiếm toàn văn, tổng hợp theo cột.
- **Độ trễ mục tiêu:** trung bình khác với p95/p99; một truy vấn nhanh trong thử nghiệm nhỏ có thể không đủ ở giờ cao điểm.
- **Độ mới của dữ liệu:** đọc phải thấy cập nhật vừa ghi hay có thể trễ vài giây/phút?
- **Cạnh tranh ghi:** bao nhiêu tiến trình sửa cùng thực thể, có bất biến cần bảo vệ nguyên tử không?
- **Vòng đời dữ liệu:** retention, TTL, xóa, archive, backfill, thay đổi schema.
- **Phạm vi tenant và địa lý:** dữ liệu được chia sẻ hay cô lập, lưu ở một hay nhiều vùng.
- **Khả năng vận hành:** kỹ năng đội ngũ, công cụ giám sát, backup/restore, chiến lược xử lý sự cố.

Quan trọng hơn **tổng throughput** là **throughput phân bố ra sao**. Một hệ có 20.000 request/giây nhưng phân tán trên hàng triệu khóa khác đáng kể với 20.000 request/giây liên tục tranh chấp một khóa.

### 2.3. Xác định bất biến trước khi nhân bản dữ liệu

Ví dụ bất biến:

1. Hai yêu cầu mua cùng một SKU không được làm **tồn khả dụng âm**.
2. Gửi lại request do timeout không được tạo hai đơn hoặc giữ kho hai lần.
3. Tổng tiền của đơn và các dòng hàng phải nhất quán theo quy tắc nghiệp vụ.
4. Một đơn chỉ được chuyển từ trạng thái này sang trạng thái khác theo sơ đồ hợp lệ.

Các bất biến này ảnh hưởng **ranh giới aggregate**, **transaction**, **conditional write**, **idempotency** và việc chọn mô hình. Một thiết kế đọc nhanh nhưng không có cách giữ những bất biến bắt buộc sẽ không phù hợp.

## 3. Đọc đúng ý nghĩa của từng họ mô hình

Các họ dưới đây nêu **đặc trưng thường gặp**, không phải giới hạn cứng của mọi sản phẩm. Một hệ có thể hỗ trợ nhiều hơn một cách biểu diễn và truy cập.

### 3.1. Key–value: truy cập trực tiếp khi biết khóa

**Ý tưởng:** mỗi khóa ánh xạ tới một giá trị. Giá trị có thể đơn giản hoặc là đối tượng phức tạp tùy công nghệ.

~~~text
key:   session:S-100
value: { "userId": "U-10", "expiresAt": "..." }

key:   inventory:SKU-1
value: { "available": 12, "version": 7 }
~~~

**Phù hợp khi:**

- Đa số thao tác biết chính xác khóa cần đọc/ghi.
- Dữ liệu có vòng đời đơn giản: session, cache, cờ cấu hình, tra cứu ID.
- Cần cập nhật một giá trị theo khóa, đôi khi kết hợp TTL hoặc điều kiện ghi nếu hệ hỗ trợ.

**Cần kiểm tra:**

- Có tìm theo thuộc tính nằm trong value được không?
- Có liệt kê theo thứ tự, phân trang hay chỉ lấy từng key?
- Một giá trị rất lớn có làm đọc/ghi tốn kém?
- Có thao tác nguyên tử, điều kiện ghi hoặc cập nhật increment theo khóa không?
- Khi cần danh sách “mọi session của một user”, phải tự duy trì cấu trúc phụ nào?

Không nên suy luận “key–value lúc nào cũng nhanh nhất”. Đọc bằng khóa có thể hiệu quả, nhưng nếu workload chính cần lọc nhiều thuộc tính mà hệ không có index thích hợp, ứng dụng phải bổ sung nhiều cấu trúc, lần đọc hoặc dịch vụ.

### 3.2. Document: làm việc với một nhóm thuộc tính có cấu trúc

**Ý tưởng:** một document giữ các trường, object lồng nhau và array; đơn vị đọc/ghi thường gắn với document.

~~~json
{
  "productId": "P-100",
  "name": "Bình nước",
  "attributes": {
    "material": "steel",
    "volumeMl": 500,
    "colors": ["blue", "black"]
  }
}
~~~

**Phù hợp khi:**

- Thuộc tính có cấu trúc lồng nhau, biến đổi theo loại đối tượng.
- Các phần của một thực thể thường được đọc hoặc cập nhật cùng nhau.
- Cần truy vấn một số trường trong document qua index mà hệ hỗ trợ.
- Các dữ liệu nhúng có kích thước và vòng đời được kiểm soát.

**Cần kiểm tra:**

- Chỉ mục cho nested field, array, composite filter và sort có đáp ứng truy vấn thật không?
- Giới hạn kích thước document và chi phí cập nhật document lớn là gì?
- Cập nhật nguyên tử trong một document và transaction nhiều document được bảo đảm đến đâu?
- Array có tăng không giới hạn hoặc trở thành điểm tranh chấp không?
- Thao tác kết hợp nhiều collection hoạt động và tốn chi phí thế nào?

**Nhúng không luôn tốt hơn tham chiếu.** Nhúng danh sách dòng hàng có kích thước hữu hạn thường thuận tiện; nhúng hàng triệu bình luận vào một document bài viết có thể làm kích thước, phân trang và cạnh tranh ghi trở thành vấn đề.

### 3.3. Wide-column / partitioned-row: nhóm dữ liệu theo khóa và thứ tự truy cập

**Ý tưởng:** thiết kế dữ liệu quanh partition key và clustering/sort key; các hàng được tổ chức để phục vụ truy vấn theo nhóm khóa và thứ tự.

~~~text
partition key: (tenantId, customerId, monthBucket)
sort key:      (createdAt DESC, orderId)
data:          orderId, status, total
~~~

**Phù hợp khi:**

- Tập truy vấn được xác định tương đối rõ.
- Cần lấy nhiều bản ghi liên quan theo một partition và thứ tự cụ thể.
- Dữ liệu ghi với lưu lượng lớn, có thể phân phối tốt theo partition key.
- Có thể thiết kế bảng hoặc bản sao riêng cho một số query pattern quan trọng.

**Cần kiểm tra:**

- Truy vấn không có partition key có được hỗ trợ hiệu quả không?
- Partition có thể tăng quá lớn hoặc quá nóng không?
- Có cần nhiều bảng theo cùng một dữ liệu cho nhiều đường truy cập không?
- Điều kiện ghi, transaction nhiều partition và chỉ mục phụ có giới hạn nào?
- Thêm bucket/shard giải quyết ghi nhưng khiến đọc nhiều partition khó ra sao?

Nhãn *wide-column* không bảo đảm mọi hệ có cùng cú pháp, mô hình transaction hay giới hạn partition. Đối với một số sản phẩm, cách tổ chức khóa quan trọng hơn tên họ mô hình.

### 3.4. Graph: quan hệ và phép duyệt là đối tượng truy cập chính

**Ý tưởng:** biểu diễn đỉnh, cạnh và thuộc tính; truy vấn quan tâm đến cách thực thể kết nối với nhau.

~~~text
(User U-10) --FOLLOWED_BY--> (User U-11)
(User U-11) --LIKES-------> (Product P-100)
(Product P-100) --IN_CATEGORY--> (Category C-2)
~~~

**Phù hợp khi:**

- Truy vấn quan trọng gồm duyệt quan hệ nhiều bước, ví dụ bạn của bạn, phát hiện cụm liên kết.
- Độ sâu hoặc hướng quan hệ thay đổi theo câu hỏi.
- Kết quả phụ thuộc cấu trúc kết nối, không chỉ lọc trường đơn giản.

**Cần kiểm tra:**

- Truy vấn duyệt bao nhiêu bước; mức độ phân nhánh lớn hay nhỏ?
- Những đỉnh có số cạnh cực lớn (*supernode*) có tạo điểm nóng không?
- Đồ thị được phân vùng ra sao, cần đi qua mạng giữa các nút bao nhiêu lần?
- Các yêu cầu tổng hợp và đọc theo ID có hiệu quả không?
- Có cần cập nhật nhiều đỉnh/cạnh với transaction không?

Đừng kết luận “ứng dụng có quan hệ giữa khách hàng và đơn hàng nên phải dùng graph”. Hầu hết ứng dụng có quan hệ; chỉ khi **duyệt quan hệ là workload trọng tâm** thì mô hình graph trở thành ứng viên đáng chú ý.

### 3.5. Các khả năng khác: search, time-series, vector, analytics

Nhiều workload không nằm trọn trong bốn nhãn phổ biến:

| Khả năng | Dạng truy vấn thường gặp | Điều cần xác minh |
|---|---|---|
| **Full-text search** | Tìm văn bản theo từ khóa, relevance, ranking | Tokenization, ngôn ngữ, cập nhật chỉ mục, filter theo tenant |
| **Time-series** | Đọc mẫu đo theo thiết bị và khoảng thời gian; downsampling | Ingest, retention, bucket, compression, query theo time range |
| **Vector / similarity search** | Lấy các item gần embedding đầu vào | Recall/latency, bộ lọc metadata, cập nhật embedding, version mô hình |
| **Columnar analytics / OLAP** | Quét nhiều dòng, nhóm theo thuộc tính, tổng hợp lớn | Scan, compression, batch/stream ingest, độ mới dữ liệu |
| **Spatial / geospatial** | Tìm điểm gần, trong polygon, khoảng cách | Index không gian, phân giải ô, lọc chính xác sau truy vấn |

Đây có thể là **công cụ lưu trữ riêng**, **mô hình dữ liệu chuyên biệt** hoặc **một tính năng của cơ sở dữ liệu đang dùng**. Cần phân biệt “cần phép truy vấn X” với “bắt buộc thêm một database mới có nhãn X”.

## 4. Tại sao nhãn không đủ: một sản phẩm có thể có nhiều năng lực

Có ba nguồn gây hiểu lầm khi chọn công nghệ từ nhãn:

1. **Họ mô hình chỉ mô tả trọng tâm thiết kế.** Một document database có thể có chỉ mục tìm kiếm, aggregation hoặc quan hệ tham chiếu. Một key–value store có thể hỗ trợ kiểu dữ liệu cấu trúc và thao tác nguyên tử. Khả năng cụ thể khác nhau giữa sản phẩm.
2. **Năng lực được quảng bá có phạm vi.** “Hỗ trợ transaction” có thể khác nhau về số bản ghi, isolation, region, giới hạn kích thước và chi phí. “Hỗ trợ index” chưa nói chỉ mục kết hợp filter/sort nào.
3. **Đường truy cập có thể quyết định dữ liệu vật lý.** Cùng nhãn document, một thiết kế truy vấn đúng khóa với index phù hợp có thể hoạt động tốt; một thiết kế phải quét phần lớn collection trên mỗi request có thể không phù hợp.

Ví dụ hai hệ đều được gọi là document database, nhưng khi muốn truy vấn:

~~~text
Lấy 20 đơn mới nhất của tenant T-1, customer C-7,
trạng thái CONFIRMED, phân trang sau mốc thời gian K
~~~

ta phải trả lời ở cấp sản phẩm cụ thể:

- Có index kết hợp các điều kiện và sort phù hợp?
- Thứ tự key trong index ảnh hưởng truy vấn và tính chọn lọc ra sao?
- Có truy vấn trên partition nào, hay bị fan-out sang nhiều partition?
- Cursor có giữ thứ tự ổn định khi nhiều đơn cùng timestamp?
- Một lần cập nhật status làm phát sinh thêm bao nhiêu ghi vào index?
- Có đọc dữ liệu mới nhất sau ghi hay replica/index cần thời gian đồng bộ?

Chỉ sau khi trả lời những câu hỏi này mới có cơ sở so sánh hai phương án.

**Đánh giá theo hành vi và giới hạn đã xác minh của hệ quản trị tại cấu hình triển khai**, thay vì chỉ dựa vào nhãn, marketing, hoặc ví dụ demo với vài bản ghi.

## 5. Mô hình hóa dữ liệu theo access pattern

### 5.1. Một thực thể nghiệp vụ có thể cần nhiều cách biểu diễn

Với đơn hàng, một mô hình nguồn có thẩm quyền có thể là:

~~~json
{
  "tenantId": "T-1",
  "orderId": "O-1042",
  "customerId": "C-7",
  "createdAt": "2026-11-14T08:00:00Z",
  "status": "CONFIRMED",
  "items": [
    {"sku": "SKU-1", "quantity": 2, "unitPrice": 150000},
    {"sku": "SKU-7", "quantity": 1, "unitPrice": 230000}
  ],
  "total": 530000,
  "version": 3
}
~~~

Nếu màn hình chi tiết biết **tenantId + orderId**, đọc một document theo khóa có thể là đường đi hợp lý. Nhưng để hiện **20 đơn mới nhất theo khách**, ứng dụng cần index hoặc một tập dữ liệu chuyên biệt:

~~~text
OrdersById
  key = (tenantId, orderId)
  value = fullOrder

OrdersByCustomer
  partition = (tenantId, customerId, monthBucket)
  sort = (createdAt DESC, orderId)
  value = { orderId, status, total }
~~~

**OrdersByCustomer** là một *read model* phục vụ truy vấn danh sách, không nhất thiết là nơi có thẩm quyền thay đổi trạng thái. Nếu trạng thái đơn thay đổi, bản sao này cũng phải được cập nhật bằng index nội bộ, transaction phù hợp hoặc pipeline sự kiện.

Đặt thêm bản sao giúp giảm chi phí đọc trong một số workload, đồng thời làm tăng:

- Dung lượng lưu trữ và chi phí ghi.
- Số nơi cần theo dõi dữ liệu cũ hoặc thiếu.
- Công việc migration, xóa dữ liệu và phục hồi.
- Rủi ro người dùng thấy trạng thái cũ nếu cập nhật bất đồng bộ.

**Mô hình dữ liệu tối ưu theo một truy vấn có thể phải trả chi phí ở các truy vấn và thao tác khác.**

### 5.2. Nhúng hay tham chiếu? Dựa trên vòng đời và ranh giới cập nhật

So sánh hai loại quan hệ:

**Đơn hàng → dòng hàng.** Dòng hàng thường được đọc cùng đơn, có kích thước được kiểm soát, giá phải giữ tại thời điểm mua. Nhúng vào document đơn có thể thuận tiện.

**Sản phẩm → hàng triệu lượt xem.** Lượt xem tăng liên tục, thường truy vấn theo thời gian hoặc phân tích, và không cần đọc tất cả mỗi lần xem sản phẩm. Nhúng toàn bộ lượt xem vào document sản phẩm sẽ làm document phình to và tạo cạnh tranh ghi. Dữ liệu sự kiện tách riêng theo khóa **productId + timeBucket + eventId** hoặc đưa vào hệ ingest/analytics có thể hợp lý hơn.

| Tiêu chí | Ưu tiên nhúng khi… | Ưu tiên tham chiếu/tách khi… |
|---|---|---|
| Cách đọc | Các phần gần như luôn được lấy cùng nhau | Đọc độc lập, lọc và phân trang từng phần |
| Kích thước | Có giới hạn nhỏ hoặc vừa | Tăng không giới hạn hoặc cực lớn |
| Cập nhật | Cùng vòng đời, cần thay đổi nguyên tử | Có nhiều writer độc lập |
| Quan hệ | Một phần thuộc một chủ thể rõ ràng | Nhiều chủ thể tham chiếu cùng dữ liệu |
| Nhân bản | Snapshot lịch sử cần giữ riêng | Dữ liệu gốc cập nhật chung, tránh lặp lớn |
| Tải | Ít tranh chấp một document | Ghi dồn vào một document nóng |

Không có một quy tắc “NoSQL thì nhúng tất cả” hay “luôn chuẩn hóa”. Quyết định là hệ quả của các thao tác thực tế.

### 5.3. Chọn partition key theo phân bố tải, không theo tên trường

Giả sử dữ liệu sự kiện dùng khóa:

~~~text
partition key = tenantId
sort key = timestamp
~~~

Với các tenant có tải đồng đều và lượng dữ liệu hữu hạn, việc truy vấn theo tenant rất thuận tiện. Nhưng nếu tenant lớn nhất chiếm 70% lưu lượng, khóa đó có thể thành điểm nóng.

Một phương án khác:

~~~text
partition key = (tenantId, dayBucket, shardNo)
sort key = (timestamp, eventId)
~~~

Thêm day bucket và shard có thể phân phối ghi, nhưng truy vấn lịch sử một tuần phải tìm nhiều bucket/shard rồi hợp nhất kết quả. Cần thiết kế cursor, thứ tự toàn cục và kế hoạch thay đổi số shard.

Vì vậy, lựa chọn mô hình không dừng ở “wide-column hay document”; ngay cả khi giữ nguyên sản phẩm, một **chiến lược partition key khác** có thể tạo ra sự khác biệt lớn hơn.

## 6. Bất biến nghiệp vụ và transaction quyết định ranh giới dữ liệu

Một lỗi thiết kế phổ biến là chọn nơi lưu cho mỗi thực thể xong mới nghĩ đến cập nhật nhiều thực thể cùng lúc.

### 6.1. Trường hợp tồn kho cạnh tranh

Giả sử **SKU-1** còn 5 đơn vị; hai người cùng đặt mua 4 và 3 đơn vị. Nếu cả hai tiến trình đều đọc “còn 5” và tự trừ ở ứng dụng, tổng số lượng có thể bị giữ vượt tồn.

Một thao tác giữ kho an toàn cần quy tắc:

~~~text
reserve(sku, quantity, reservationId):
    if reservationId has been processed:
        return priorResult

    atomically, if available >= quantity:
        available = available - quantity
        register reservationId and quantity
        return RESERVED

    return INSUFFICIENT_STOCK
~~~

Đây là **mã giả ở mức nghiệp vụ**, không phải API chung cho mọi database. Điều kiện kiểm tra và giảm tồn cần được bảo vệ trong phạm vi nguyên tử mà hệ quản trị thực sự hỗ trợ. Nếu reservation nằm ở mục khác, phải bảo đảm cơ chế phù hợp hoặc thay đổi cách biểu diễn.

Thao tác này có thể triển khai bằng các khả năng như **conditional update**, **compare-and-set**, transaction trong phạm vi được hỗ trợ hoặc cấu trúc sở hữu tồn kho khác. Điều cần quyết định trước là **bất biến** “không giữ quá tồn”, rồi đánh giá sản phẩm có cơ chế đáp ứng hay không.

### 6.2. Một document không phải lúc nào cũng là một nghiệp vụ trọn vẹn

Đơn hàng và tồn kho có thể nằm ở hai ranh giới:

~~~text
Order(O-1042)
    status = PENDING
    items = [...]

Inventory(SKU-1)
    available = 5
~~~

Tạo đơn và giữ kho là hai thao tác cần phối hợp. Không thể suy luận rằng **transaction trên một document** cũng bảo vệ cả **Order** và **Inventory**.

Các hướng xử lý gồm:

- **Transaction nhiều mục** nếu hệ quản trị hỗ trợ đúng phạm vi, mức cách ly và chi phí đáp ứng workload.
- **Saga** với các trạng thái PENDING, RESERVED, CONFIRMED, CANCELED; có hành động bù khi thất bại.
- **Outbox/event log** gắn một cách nguyên tử với cập nhật nguồn để phát công việc đáng tin cậy, kết hợp consumer idempotent.

Khi chọn saga, phải chấp nhận trạng thái trung gian, retry, timeout, đối soát và hành động bù. Một màn hình có thể thấy PENDING trong khi hệ thống đang giữ hàng; UI và API cần diễn đạt đúng trạng thái đó.

### 6.3. Nhất quán đọc không đồng nhất với nguyên tử ghi

Cần tách ba điều:

- **Atomicity:** các thay đổi trong phạm vi giao dịch diễn ra đầy đủ hoặc không diễn ra.
- **Isolation và kiểm soát cạnh tranh:** các ghi đồng thời có thể gây lost update, write skew hoặc những bất thường nào; cách chặn ra sao.
- **Read consistency:** truy vấn có đọc được dữ liệu mới ghi, một snapshot, hay dữ liệu chậm từ replica/index?

Một hệ có thao tác nguyên tử trên một khóa nhưng đọc từ replica chậm vẫn có thể cho kết quả cũ. Một hệ có transaction nhiều document nhưng không có index phù hợp vẫn có thể trả lời truy vấn danh sách quá chậm. **Mô hình phải đáp ứng cả tính đúng đắn và đường truy cập**.

### 6.4. Không có transaction “miễn phí”

Khi một thao tác chạm nhiều khóa hoặc nhiều phân vùng, cần hỏi:

1. Hệ có hỗ trợ transaction đúng phạm vi đó không?
2. Mức isolation và hành vi khi gặp conflict là gì?
3. Giới hạn số mục, kích thước, thời gian giao dịch?
4. Transaction xuyên region có khả thi và đáp ứng độ trễ không?
5. Khi client timeout, làm sao biết giao dịch đã commit hay chưa?
6. Retry có an toàn và tránh tác dụng phụ lặp không?

Không nên quyết định chỉ dựa trên checkbox “ACID” trong bảng tính năng. Các giới hạn cụ thể có thể ảnh hưởng trực tiếp đến cách chia aggregate và phân vùng.

## 7. So sánh mô hình theo các loại nhu cầu

Bảng sau là **ma trận định hướng đặt câu hỏi**, không phải bảng xếp hạng tuyệt đối. Một sản phẩm có chỉ mục, transaction, query engine hoặc phần mở rộng thích hợp có thể xử lý các pattern nằm ngoài thế mạnh điển hình của nhãn.

| Nhu cầu chủ đạo | Ứng viên đáng xem xét | Điểm cần chứng minh |
|---|---|---|
| Tra cứu theo khóa đã biết, latency ổn định | Key–value, document, hệ có primary-key lookup hiệu quả | p95/p99 theo kích thước value, hot key, TTL và consistency |
| Đọc/ghi một thực thể lồng nhau | Document hoặc aggregate phù hợp | Giới hạn document, atomic update, index, kích thước tăng |
| Danh sách có thứ tự theo một khóa nhóm | Wide-column/partitioned-row, document có compound index | Partition/sort key, cursor, phân trang, skew |
| Duyệt nhiều cấp quan hệ biến động | Graph hoặc projection quan hệ chuyên biệt | Độ sâu và độ rộng traversal, supernode, chi phí phân vùng |
| Ingest sự kiện theo thời gian | Time-series, wide-column, log/event store | Write rate, retention, bucket, scan theo time |
| Tìm kiếm tự do trong văn bản | Search engine/index hoặc hệ có full-text index | Relevance, ngôn ngữ, cập nhật index, filter quyền |
| Truy vấn tổng hợp lớn trên nhiều dòng | Analytical/columnar engine, projection tiền tính | Scan cost, ingest lag, backfill, độ mới cần thiết |
| Tìm hàng xóm gần embedding | Vector index/search | Recall, latency, metadata filter, cập nhật index |
| Truy vấn kết hợp nhiều điều kiện linh hoạt | Document/relational/search tùy index và planner | Index coverage, selectivity, sort, pagination, chi phí ghi |
| Giao dịch nhiều thực thể với bất biến chặt | Hệ có transaction phù hợp; mô hình lại aggregate | Isolation, transaction scope, contention và vận hành |

**Lưu ý:** SQL/relational cũng là ứng viên hợp lệ khi workload yêu cầu join linh hoạt, ràng buộc nhiều thực thể hoặc transaction phức tạp. Việc học NoSQL không có nghĩa mọi bài toán đều phải dùng NoSQL. Thỉnh thoảng giải pháp ít phức tạp nhất là giữ một hệ đang đáp ứng yêu cầu.

## 8. Case study: cùng một ứng dụng, các workload khác nhau

Ta quay lại nền tảng bán hàng. Hệ thống cần xử lý **đơn hàng, sản phẩm, lịch sử hành vi, đề xuất và báo cáo**. Thay vì chọn một nhãn từ đầu, ta phân tích từng workload.

### 8.1. Đơn hàng: aggregate theo orderId

**Nhu cầu:** đọc chi tiết đơn nhanh; các dòng hàng và tổng tiền phải nhất quán khi tạo đơn; lưu giá tại thời điểm mua.

**Thiết kế ứng viên:** một document đơn hàng chứa dòng hàng; khóa **tenantId + orderId**. Màn hình chi tiết truy cập trực tiếp. Có thể dùng index hoặc read model **OrdersByCustomer** cho danh sách.

**Điều cần kiểm chứng:** document có thể vượt giới hạn kích thước không, cập nhật đơn đồng thời bảo vệ version thế nào, index danh sách có phù hợp sort/pagination không.

**Vì sao không chọn chỉ vì JSON:** nếu danh sách dòng hàng tăng vô hạn hoặc truy vấn liên tục cần cập nhật độc lập trên từng dòng, mô hình document nhúng toàn bộ có thể không còn hợp lý.

### 8.2. Giữ tồn kho: ranh giới ghi nguyên tử theo SKU

**Nhu cầu:** hai người cùng mua không làm số lượng tồn bị âm; request retry không trừ hai lần.

**Thiết kế ứng viên:** một bản ghi tồn kho có thẩm quyền theo SKU, conditional update và reservationId idempotent; hoặc transaction phù hợp khi nhiều SKU phải được giữ cùng lúc.

**Điều cần kiểm chứng:** contention khi flash sale, throughput của SKU nóng, cơ chế chống lặp, trạng thái quá hạn và khả năng đối soát.

**Vì sao không chọn theo nhãn:** key–value, document hoặc mô hình khác đều có thể đáp ứng nếu cơ chế ghi đúng phạm vi. Điều quyết định là bảo đảm cập nhật cạnh tranh thực tế.

### 8.3. Lịch sử hành vi: phân vùng theo thời gian và retention

**Nhu cầu:** ghi liên tục sự kiện **view**, **click**, **add_to_cart**; truy vấn gần đây theo user; xử lý tổng hợp theo ngày; xóa hoặc archive sau thời gian giữ.

**Thiết kế ứng viên:**

~~~text
Event:
  tenantId
  eventId
  userId
  eventType
  timestamp
  productId

Partition / access path candidate:
  (tenantId, userId, dayBucket) + (timestamp, eventId)
~~~

Nếu workload chủ yếu là báo cáo toàn hệ thống và ingest cực lớn, có thể cần luồng sự kiện kèm kho phân tích thay vì dùng cùng đường giao dịch như đơn hàng.

**Điều cần kiểm chứng:** tốc độ ghi đỉnh, hot user/tenant, tỷ lệ scan, retention, nén, backfill và chi phí index.

### 8.4. Đề xuất sản phẩm: quan hệ, tính toán trước và truy vấn trực tuyến

**Nhu cầu:** gợi ý sản phẩm tương tự hoặc sản phẩm thường mua cùng; có thể dùng các quan hệ:

~~~text
User --> VIEWED --> Product
User --> BOUGHT --> Product
Product --> IN_CATEGORY --> Category
Product --> SIMILAR_TO --> Product
~~~

Có ít nhất ba hướng:

1. Tính gợi ý theo lô và lưu **RecommendationsByUser(userId)** để API đọc nhanh bằng khóa.
2. Dùng graph khi nghiệp vụ cần duyệt quan hệ nhiều bước linh hoạt.
3. Dùng vector similarity nếu quan hệ ngữ nghĩa từ embedding là yếu tố chính, kết hợp filter quyền và metadata.

Cùng chức năng “đề xuất” có thể dùng nhiều mô hình khác nhau. Nếu mục tiêu API chỉ là trả 10 gợi ý đã tính sẵn trong vài mili giây, một key–value/document read model có thể là đường phục vụ tốt, dù thuật toán gợi ý phía sau dùng graph hoặc vector.

**Điều cần kiểm chứng:** số bước tính toán online, thời gian cập nhật gợi ý, recall/chất lượng kết quả, quota tenant và khả năng vận hành pipeline.

### 8.5. Báo cáo: truy vấn phân tích nên tách khỏi luồng giao dịch khi cần

**Nhu cầu:** tổng doanh thu tháng theo khu vực, kênh bán, trạng thái; đọc nhiều tháng dữ liệu.

Nếu mỗi báo cáo quét hàng triệu document giao dịch, đọc toàn bộ nội dung rồi tính tổng tại ứng dụng, có thể gây tải lớn và làm chậm checkout.

Các hướng gồm:

- Bảng tổng hợp theo ngày và tenant được cập nhật từ sự kiện đơn hàng.
- Kho phân tích/columnar engine chuyên cho scan và aggregate.
- Materialized view nếu DB hỗ trợ và mức độ mới phù hợp.

Đây không có nghĩa mọi ứng dụng nhỏ phải thêm data warehouse. Với quy mô nhỏ, một aggregation trên index phù hợp có thể đủ. **Quy mô và SLO quyết định khi nào cần tách**.

### 8.6. Sơ đồ luồng dữ liệu theo nhu cầu

~~~mermaid
flowchart TD
    API["API giao dịch"]
    API --> O["OrdersById<br/>Chi tiết đơn"]
    API --> I["InventoryBySku<br/>Conditional update"]
    O --> EVT["Sự kiện thay đổi có cơ chế phát bền vững"]
    EVT --> OC["OrdersByCustomer<br/>Danh sách đơn"]
    EVT --> AN["Phân tích / tổng hợp<br/>Doanh thu"]
    EVT --> BE["Sự kiện hành vi / đề xuất"]
    BE --> REC["RecommendationsByUser<br/>Phục vụ đọc nhanh"]
    API --> OC
    API --> REC
~~~

Sơ đồ mô tả các **vai trò dữ liệu**, không bắt buộc là sáu sản phẩm riêng. Một hệ có thể cung cấp nhiều vai trò; nhiều hệ cũng có thể cùng tham gia. Nếu sự kiện phải phát sau khi dữ liệu nguồn đã commit, cần thiết kế outbox, CDC hoặc cơ chế tương đương phù hợp thay vì tin rằng hai lệnh ghi độc lập luôn thành công cùng nhau.

## 9. Chi phí thực của một lựa chọn mô hình

Đánh giá chỉ dựa trên tốc độ một truy vấn là chưa đủ. Nhiều phương án đổi chi phí đọc thành ghi, dung lượng, sự phức tạp hoặc rủi ro dữ liệu cũ.

### 9.1. Read amplification và write amplification

**Read amplification**: để trả lời một request, hệ phải đọc bao nhiêu bản ghi, bao nhiêu index entry, bao nhiêu partition và gọi qua mạng bao nhiêu lần.

Ví dụ tìm 20 đơn mới nhất:

- Index đúng khóa và thứ tự: có thể đọc một khoảng index hẹp và các document cần thiết.
- Không có index thích hợp: có thể phải scan rất nhiều đơn rồi lọc và sắp xếp.
- Dữ liệu bị shard: có thể cần đọc nhiều shard, merge và phân trang.

**Write amplification**: một thay đổi nghiệp vụ phát sinh bao nhiêu lần ghi thực tế.

Một lần xác nhận đơn có thể cập nhật nguồn, index theo trạng thái, index theo khách hàng, event log và read model. Nếu không đo, thiết kế “đọc siêu nhanh” có thể làm write throughput và hóa đơn tăng mạnh.

### 9.2. Một công thức chi phí ở mức tư duy

~~~text
Tổng chi phí vận hành xấp xỉ
  chi phí đọc và tính toán truy vấn
  + chi phí ghi và cập nhật chỉ mục
  + dung lượng bản gốc, bản sao, index
  + truyền dữ liệu và replication
  + backup, restore, monitoring
  + công xử lý đồng bộ, migration, sự cố
~~~

Đây là cấu trúc để so sánh, không phải công thức giá cụ thể của nhà cung cấp. Mô hình dữ liệu phải được đánh giá trên **chi phí toàn hệ thống**, không chỉ trên tốc độ đọc cục bộ.

### 9.3. Hot key, hot partition và dữ liệu lệch

Ví dụ một tenant chiếm 70% ghi, mọi sự kiện của tenant dồn vào một partition key. Dù cluster còn tổng tài nguyên, một phân vùng nóng có thể bị giới hạn throughput hoặc tăng latency.

Giải pháp có thể là thêm time bucket, shard hoặc chuyển tenant lớn sang nhóm tài nguyên riêng. Nhưng mỗi thay đổi tạo đánh đổi: truy vấn toàn tenant phải hợp nhất nhiều partition, migration dữ liệu và logic phân trang phức tạp hơn.

Do đó, mô hình phù hợp phải được đánh giá với **phân phối tải thật**, không chỉ tổng request/giây.

### 9.4. Consistency và dữ liệu nhân bản

Nếu danh sách đơn được duy trì bất đồng bộ từ nguồn, một người dùng có thể vừa tạo đơn thành công nhưng chưa thấy đơn trong lịch sử. Đây có thể là **projection lag**, không nhất thiết là mất dữ liệu.

Cần xác định:

- Màn hình nào yêu cầu **read-your-writes**?
- Dữ liệu nào có thể trễ và trễ tối đa bao lâu?
- Cách phát hiện read model bị thiếu dữ liệu?
- Nếu sự kiện được giao lặp hoặc khác thứ tự, consumer có idempotent/version check không?
- Khi restore từ backup, có cơ chế rebuild projection không?

Sự nhất quán của read model là **yêu cầu sản phẩm và vận hành** chứ không chỉ là đặc tính của nhãn NoSQL.

## 10. Kỹ năng và vận hành cũng là tiêu chí chọn mô hình

Một mô hình có thể phù hợp lý thuyết nhưng không phù hợp với khả năng triển khai của đội ngũ. Ví dụ chọn một graph database riêng cho một báo cáo quan hệ ít dùng có thể làm tăng thêm công việc về bảo mật, backup, giám sát, CI/CD, nâng cấp và on-call.

Các câu hỏi thực tế:

| Khía cạnh | Cần xác định |
|---|---|
| **Vận hành** | Managed hay tự vận hành; khả năng xử lý failover, nâng cấp, mở rộng |
| **Độ tin cậy** | Backup/restore, RPO/RTO, replication, kiểm thử khi mất node/region |
| **Bảo mật và tenant** | Quyền theo tenant, kiểm soát dữ liệu ở index, cache, export |
| **Khả năng quan sát** | p95/p99, hot partitions, throttling, conflict, index lag |
| **Thay đổi schema** | Backfill, versioning, tăng kích thước document, đổi partition key |
| **Vị trí dữ liệu** | Region được phép, replica, log, backup, chính sách retention |
| **Chi phí và nhân sự** | Mức độ hiểu công nghệ, tài liệu, đào tạo và bảo trì dài hạn |

Nếu cùng một workload có thể đáp ứng bằng index của database hiện có, điều đó có thể đơn giản hơn việc thêm một cơ sở dữ liệu chuyên biệt. Ngược lại, nếu workload chính không thể đạt SLO một cách bền vững trên hệ hiện có, tách một read model hoặc dịch vụ lưu trữ chuyên biệt có thể đem lại lợi ích rõ ràng.

### 10.1. Tránh dùng một database cho mọi thứ theo quán tính

Chỉ dùng một công nghệ có lợi về vận hành: ít kết nối, ít hệ thống phải giám sát, giảm nhu cầu đồng bộ. Nhưng cố ép search, analytics, graph traversal và OLTP vào một đường truy cập có thể làm mô hình khó tối ưu.

**Polyglot persistence** là dùng nhiều hệ lưu trữ theo nhu cầu; nó cũng mang chi phí:

- Đồng bộ và xử lý dữ liệu thiếu hoặc trễ.
- Phân định nguồn dữ liệu có thẩm quyền.
- Xóa/đổi dữ liệu ở tất cả projection.
- Kiểm soát quyền tenant và dữ liệu nhạy cảm giữa các hệ.
- Vận hành nhiều công nghệ, backup và version.

Không nên dùng polyglot persistence chỉ vì có nhiều nhãn mới. Mỗi hệ thêm vào phải phục vụ nhu cầu đủ quan trọng để bù chi phí phối hợp.

## 11. Quy trình lựa chọn có thể áp dụng cho dự án thực tế

### Bước 1: Lập danh sách access pattern và mức ưu tiên

Từ người dùng, API và luồng nền, mô tả từng thao tác theo:

~~~text
Operation:
Input keys:
Filter / sort / pagination:
Result size:
Read or write frequency:
Peak and skew:
Consistency requirement:
Latency SLO:
Data growth / retention:
~~~

Không chỉ liệt kê API. Job nhập dữ liệu, đồng bộ, tìm kiếm, báo cáo và cleanup có thể chiếm phần lớn tải.

### Bước 2: Vẽ dữ liệu và bất biến

Xác định thực thể, quan hệ, khóa và nơi dữ liệu có thẩm quyền; ghi rõ những thay đổi cần nguyên tử. Đánh dấu quan hệ một-nhiều có giới hạn, một-nhiều không giới hạn và nhiều-nhiều.

Ví dụ:

~~~text
Order --contains--> OrderItem (thường có giới hạn)
Customer --places--> Order (có thể tăng không giới hạn)
OrderItem --references--> Product (dùng chung)
Inventory --tracks--> SKU (cập nhật cạnh tranh)
User --interactsWith--> Product (sự kiện nhiều, tăng nhanh)
~~~

Đây là mô hình nghiệp vụ; chưa cần cam kết dùng document, graph hay wide-column.

### Bước 3: Đề xuất hai hoặc ba phương án dữ liệu vật lý

Không cần mô phỏng mọi sản phẩm. Với mỗi candidate, vẽ:

- Khóa chính, partition key, sort key.
- Index và read model.
- Số nơi cần ghi khi tạo/sửa/xóa một bản ghi.
- Bất biến được giữ bằng thao tác nguyên tử hoặc workflow nào.
- Các truy vấn phải scan/fan-out/duyệt nhiều bước.
- Cách phân vùng tenant, retention và phục hồi.

Nếu một truy vấn không có đường truy cập rõ ràng, đó là dấu hiệu cần điều chỉnh mô hình trước khi benchmark.

### Bước 4: Lập ma trận đánh đổi

Ví dụ cho chức năng “lịch sử đơn hàng theo khách”:

| Tiêu chí | A: Document + index | B: Bảng/read model theo khách | C: Chỉ tra khóa đơn và quét |
|---|---|---|---|
| Truy vấn mới nhất theo khách | Phụ thuộc index/filter/sort | Có thể tối ưu theo khóa và thứ tự | Có thể phải quét nhiều dữ liệu |
| Chi phí thêm khi ghi đơn | Duy trì index | Ghi thêm bản sao/projection | Ít ghi phụ |
| Độ mới danh sách | Phụ thuộc semantics index | Đồng bộ hoặc bất đồng bộ tùy thiết kế | Đọc trực tiếp nguồn |
| Tăng trưởng và tenant nóng | Kiểm tra phân vùng/index | Thiết kế bucket/shard và fan-out | Chi phí scan tăng nhanh |
| Công vận hành | Quản lý index | Quản lý sự kiện/rebuild/đối soát | Đơn giản ban đầu, rủi ro khi tải tăng |

Bảng này không tuyên bố A hay B luôn thắng. Nó chỉ đưa ra giả thuyết để thử nghiệm.

### Bước 5: Kiểm chứng năng lực của hệ quản trị cụ thể

Đọc tài liệu kỹ thuật cho **đúng phiên bản, cấu hình và hình thức triển khai**. Các điểm cần xác nhận có thể gồm:

1. Query/index có thực sự hỗ trợ filter, sort và pagination cần thiết?
2. Giới hạn kích thước bản ghi, partition, transaction và throughput?
3. Consistency sau ghi, cơ chế replica, index update và failover?
4. Atomic conditional update, compare-and-set, isolation khi concurrency?
5. Cơ chế partitioning, auto-scaling, throttling và hot partition?
6. Backup/restore, schema change, data export và migration?
7. Region/data placement, bảo mật, cách tính chi phí?

**Không viết thiết kế dựa trên một tính năng chưa xác minh của sản phẩm.** Cùng tên tính năng có thể có điều kiện rất khác nhau.

### Bước 6: Làm proof of concept với tải đại diện

Một PoC tối thiểu nên dùng các thao tác A1–A6, dữ liệu có kích thước và phân phối gần thực tế:

- Tạo số tenant và số record đủ lớn để lộ vấn đề index/partition.
- Mô phỏng người dùng hoặc SKU nóng, không chỉ random key phân phối đều.
- Đọc theo khóa, truy vấn danh sách phân trang và cập nhật cạnh tranh cùng lúc.
- Đo **p50, p95, p99**, throughput, lỗi/throttle, CPU/I/O, request units hoặc các chỉ số tương đương.
- Thử retry, timeout, duplicate request, failover/replica lag theo yêu cầu.
- Ước lượng dung lượng và write amplification do index, read model, backup.

Một benchmark chỉ tạo 1.000 bản ghi, đọc một ID và báo “2 ms” chưa thể kết luận phù hợp với hàng trăm triệu bản ghi và nhiều tenant.

### Bước 7: Ghi lại quyết định có điều kiện thay đổi

Ví dụ:

~~~text
Quyết định:
  Dùng document Order theo khóa (tenantId, orderId);
  dùng read model theo (tenantId, customerId, createdAt)
  nếu index hiện có không đáp ứng SLO A2.

Giả định:
  Mỗi đơn có số dòng hàng được giới hạn.
  Hệ hỗ trợ thao tác nguyên tử trong ranh giới Order.
  Lịch sử đơn được phép trễ tối đa theo mức đã thỏa thuận.

Điểm theo dõi:
  p99 chi tiết đơn, p99 danh sách, index/projection lag,
  write conflict, tenant nóng và chi phí ghi.

Điều kiện xem lại:
  SLO vi phạm, một tenant vượt ngưỡng tải,
  thay đổi về giao dịch hoặc yêu cầu lưu trữ.
~~~

Một quyết định tốt là quyết định nêu rõ **vì sao đúng trong hiện tại và khi nào cần đánh giá lại**, thay vì một kết luận vĩnh viễn từ nhãn công nghệ.

## 12. Cây tư duy lựa chọn: bắt đầu từ câu hỏi

Sơ đồ sau giúp đặt các câu hỏi theo nhu cầu. Nó **không thay thế so sánh sản phẩm**, vì một hệ có thể đáp ứng nhiều nhánh.

~~~mermaid
flowchart TD
    W["Workload nào quan trọng nhất?"] --> Q{"Truy vấn chủ đạo?"}
    Q -->|Biết khóa chính| KV["Kiểm tra key–value / primary-key lookup"]
    Q -->|Đọc aggregate lồng nhau| DOC["Kiểm tra document / aggregate"]
    Q -->|Danh sách theo nhóm và thời gian| COL["Kiểm tra partition + sort/index"]
    Q -->|Duyệt liên kết nhiều cấp| GRAPH["Kiểm tra graph/traversal"]
    Q -->|Tìm kiếm, vector, tổng hợp lớn| SPEC["Kiểm tra index hoặc engine chuyên biệt"]
    KV --> C["Kiểm tra bất biến, consistency, partition, SLO"]
    DOC --> C
    COL --> C
    GRAPH --> C
    SPEC --> C
    C --> P{"Có đáp ứng giới hạn thực tế?"}
    P -->|Có| TEST["PoC với tải và lỗi đại diện"]
    P -->|Chưa| ALT["Đổi đường truy cập, mô hình hoặc ứng viên"]
    ALT --> Q
    TEST --> DEC["Chọn phương án có chi phí/vận hành chấp nhận được"]
~~~

Trong thực tế, một hệ có thể có **nhiều truy vấn quan trọng ngang nhau**. Khi đó hãy áp dụng quy trình cho từng workload rồi quyết định dùng một hệ với nhiều index/read model hay nhiều hệ chuyên biệt.

## 13. Các sai lầm thường gặp khi chọn theo nhãn

### 13.1. “Có JSON thì phải chọn document”

JSON là định dạng biểu diễn phổ biến của API, không phải yêu cầu lưu trữ. Cùng JSON có thể được lưu trong document, value của key–value, nhiều hàng quan hệ hoặc được biến đổi thành các sự kiện. Cần quan tâm **cách đọc/ghi** và bất biến hơn hình thức payload.

### 13.2. “Có quan hệ thì phải chọn graph”

Mọi nghiệp vụ đều có quan hệ. Graph hữu ích khi **truy vấn liên kết** là trọng tâm; việc lấy đơn theo customerId có thể đơn giản hơn với index hoặc phân vùng theo khóa.

### 13.3. “Wide-column là cứ thêm máy sẽ mở rộng mãi”

Khả năng phân tán còn phụ thuộc partition key, phân phối ghi, giới hạn nút, replication và query pattern. Một khóa nóng có thể bị giới hạn dù cụm còn tài nguyên.

### 13.4. “Document là không có schema”

Ứng dụng vẫn có contract dữ liệu, validation, index và yêu cầu tương thích. Khi thêm trường hoặc đổi cấu trúc, bản ghi cũ và mới có thể cùng tồn tại; cần chiến lược migration và backfill.

### 13.5. “NoSQL luôn không có transaction”

Năng lực transaction khác nhau giữa sản phẩm và cấu hình. Một số hệ hỗ trợ transaction nhiều record; một số nhấn mạnh thao tác nguyên tử trên một record/partition. Cần kiểm tra phạm vi và semantics cụ thể.

### 13.6. “Chọn công nghệ được gọi là multi-model sẽ giải quyết tất cả”

Một sản phẩm có nhiều tính năng chưa chắc tối ưu mọi đường truy cập. Cần benchmark riêng graph traversal, full-text search, aggregation hoặc transaction theo dữ liệu thật.

### 13.7. “Thêm index không có mặt trái”

Index tăng chi phí ghi, dung lượng và công việc bảo trì; có thể ảnh hưởng đến bulk import hoặc cập nhật thường xuyên. Một index ít tính chọn lọc đôi khi không giải quyết được truy vấn.

### 13.8. “Một workload đã nhanh thì toàn hệ thống sẽ nhanh”

Đọc theo ID có thể xuất sắc nhưng đọc danh sách sắp xếp, phân trang, xử lý SKU nóng hoặc báo cáo tổng hợp vẫn có thể là nút thắt. Phải đánh giá các đường đọc/ghi cạnh nhau dưới tải.

### 13.9. “Chỉ quan tâm truy vấn, sau này tính vận hành”

Một mô hình tạo quá nhiều projection có thể khó đối soát và phục hồi. Một mô hình dùng nhiều region có thể tạo conflict, tăng chi phí replication hoặc vượt chính sách lưu dữ liệu. Vận hành là một phần của quyết định dữ liệu.

### 13.10. “Đã chọn database thì không cần xem lại mô hình”

Workload thay đổi theo quy mô và tính năng mới. Sự tăng trưởng của một tenant hoặc sự xuất hiện của truy vấn mới có thể đòi hỏi đổi partition key, thêm projection, tách workload hoặc thậm chí đổi hệ lưu trữ. Quyết định nên có điều kiện đánh giá lại.

## 14. Bài tập thực hành

### Bài 1. Bình luận dưới bài viết

Một nền tảng có nhiều bài viết, một số bài nhận hàng triệu bình luận. Người dùng thường xem 20 bình luận mới nhất; tác giả có thể xóa từng bình luận. Ban đầu nhóm đề xuất nhúng tất cả bình luận vào một document bài viết vì “document phù hợp dữ liệu lồng nhau”.

Hãy:

1. Liệt kê access pattern và rủi ro tăng kích thước document.
2. Đề xuất khóa phân vùng/sắp xếp để phân trang bình luận.
3. Nêu tác động của việc bài viết quá nổi tiếng tạo hot key.
4. Phân biệt tính đúng đắn khi xóa bình luận và độ trễ của bộ đếm bình luận.

### Bài 2. Đề xuất bạn bè

Ứng dụng mạng xã hội muốn tìm “bạn của bạn chưa kết bạn với người dùng hiện tại”, ưu tiên người có nhiều bạn chung. Người dùng trung bình có vài trăm kết nối, nhưng một số tài khoản có hàng triệu người theo dõi.

Hãy:

1. Đánh giá ưu/nhược của graph traversal và việc tính trước tập gợi ý.
2. Mô tả supernode ảnh hưởng đến truy vấn thế nào.
3. Xác định khi nào truy vấn bằng bảng/index quan hệ cũng đáp ứng đủ.
4. Đề xuất benchmark về độ sâu duyệt và fan-out.

### Bài 3. Session và tìm kiếm theo thuộc tính

Hệ lưu session theo khóa **sessionId** nhưng đội vận hành đòi hỏi “tìm mọi session hết hạn của một user”, phân trang theo thời gian. Nhóm đề xuất key–value vì “đọc rất nhanh”.

Hãy:

1. Xác định đường truy cập chính và đường truy cập mới.
2. Đề xuất index, tập khóa phụ hoặc cơ chế TTL phù hợp từng yêu cầu.
3. Nêu cách dọn dữ liệu phụ khi session hết hạn hoặc bị hủy.
4. Làm rõ vì sao tốc độ truy cập theo sessionId không giải quyết tự động truy vấn theo userId.

### Bài 4. Flash sale

Ứng dụng bán vé có một sự kiện duy nhất với hàng chục nghìn request/giây, tồn vé có giới hạn. Nhóm đề xuất chia ngẫu nhiên dữ liệu tồn thành nhiều shard để “NoSQL phân tán sẽ tự xử lý”.

Hãy:

1. Xác định bất biến tổng số vé giữ không vượt số vé thật.
2. Đề xuất cơ chế quota hoặc cấp phát theo bucket có kiểm soát.
3. Xác định vấn đề retry/idempotency và refund khi giữ vé hết hạn.
4. Mô tả cách đo throughput, conflict rate và độ chính xác trước khi triển khai.

### Bài 5. Báo cáo trên database giao dịch

Hệ thống lưu 500 triệu đơn; công việc cuối ngày yêu cầu tổng doanh thu theo khu vực, danh mục và kênh bán. Một truy vấn tổng hợp chạy trực tiếp trên hệ phục vụ checkout làm p99 checkout tăng mạnh.

Hãy:

1. Phân biệt workload OLTP và OLAP trong tình huống này.
2. Đề xuất aggregation tiền tính, read model hoặc hệ phân tích chuyên biệt.
3. Nêu cách đồng bộ thay đổi, backfill và đối soát số liệu.
4. Xác định mức độ mới dữ liệu thực sự cần có để quyết định batch hay stream.

### Bài 6. Đọc bảng tính năng sản phẩm

Hai nhà cung cấp đều quảng bá “document model”, “ACID transaction”, “global replication” và “automatic scaling”. Hãy xây bảng câu hỏi kỹ thuật cần hỏi từng nhà cung cấp về: phạm vi transaction, isolation, consistency của replica, chỉ mục kết hợp filter/sort, hot partition, kích thước bản ghi, backup, data residency và chi phí.

Đừng trả lời bằng cảm giác “nhãn nào tốt hơn”. Với mỗi đề xuất hãy nói rõ **query sẽ đi theo đường nào**, **bất biến được bảo vệ bằng cơ chế nào**, **tải nóng có thể phát sinh ở đâu**, và **sẽ đo kết quả bằng chỉ số gì**.

## 15. Checklist trước khi chốt một mô hình NoSQL

| Câu hỏi | Minh chứng mong đợi |
|---|---|
| Workload chủ đạo đã được mô tả chưa? | Danh sách access pattern có khóa, tần suất, p95/p99 và dữ liệu trả về |
| Các bất biến nghiệp vụ đã rõ chưa? | Ranh giới transaction, concurrent update và idempotency |
| Có đường truy cập cho từng truy vấn quan trọng chưa? | Primary key, partition/sort key, index, read model hoặc traversal |
| Phân bố dữ liệu có làm khóa nóng không? | Dữ liệu mẫu và đo skew theo tenant/user/SKU |
| Chi phí ghi và lưu trữ phụ đã được tính chưa? | Index, projection, replica, log và backup |
| Yêu cầu về độ mới dữ liệu đã được thống nhất chưa? | Read-your-writes, replica/index lag, SLA/SLO của projection |
| Khả năng của sản phẩm đã được xác minh chưa? | Tài liệu đúng phiên bản và PoC các giới hạn quan trọng |
| Có thể phục hồi và chuyển đổi dữ liệu không? | Backup/restore drill, rebuild projection, migration plan |
| Vận hành theo tenant và vùng đã được tính chưa? | Quota, phân quyền, data placement, metrics và runbook |
| Quyết định có thời điểm đánh giá lại chưa? | Các ngưỡng SLO, tải, chi phí hoặc yêu cầu nghiệp vụ thay đổi |

---

**Kết luận:** Một lựa chọn mô hình NoSQL có cơ sở phải bắt đầu từ **workload, bất biến, đường truy cập và khả năng vận hành**, rồi mới đối chiếu những bảo đảm và giới hạn cụ thể của sản phẩm. Key–value, document, wide-column, graph và các mô hình chuyên biệt đều là công cụ để giải quyết từng nhóm nhu cầu; tên gọi của chúng không thay thế được việc thiết kế khóa, đo tải, bảo vệ tính đúng đắn và thử nghiệm trên dữ liệu đại diện.
