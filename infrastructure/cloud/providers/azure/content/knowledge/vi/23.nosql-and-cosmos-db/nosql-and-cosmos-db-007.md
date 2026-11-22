# Index policy và tối ưu truy vấn Cosmos DB

Một API Java lưu hàng triệu đơn hàng dưới dạng JSON trong **Azure Cosmos DB**. Truy vấn theo mã đơn hàng chạy nhanh, nhưng trang liệt kê đơn mới nhất theo khách hàng lại tiêu tốn hàng trăm Request Units (RU), thường xuyên bị HTTP 429 và chậm hơn khi dữ liệu tăng. Nhóm phát triển định tăng RU/s gấp đôi. Đây có thể là giải pháp tạm thời, nhưng trước tiên cần hỏi: **request có biết partition key không, có thể dùng point read không, truy vấn có đi qua nhiều partitions không, index hiện tại có hỗ trợ FILTER và ORDER BY không, và kết quả có bị trả về quá nhiều trường không?**

**Index policy** quyết định các đường dẫn thuộc tính JSON nào được lập chỉ mục và bằng loại chỉ mục nào. Một chính sách hợp lý có thể giảm chi phí đọc, hạn chế chi phí ghi/index storage và hỗ trợ những mẫu truy vấn quan trọng. Ngược lại, một chính sách không phù hợp có thể khiến truy vấn quét nhiều dữ liệu, tăng RU, gây cạnh tranh tài nguyên hoặc thậm chí khiến một kiểu ORDER BY không thể thực thi nếu thiếu composite index cần thiết.

Bài thuộc chương **Dữ liệu NoSQL với Cosmos DB** trong module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, compute, lưu trữ và dữ liệu, kết hợp triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Chúng ta tập trung vào **Azure Cosmos DB for NoSQL (API for NoSQL, trước đây thường gọi Core/SQL API)**, nơi truy vấn sử dụng ngôn ngữ SQL-like cho JSON. Các API cho MongoDB, Cassandra, Gremlin hoặc Table có cơ chế indexing/cú pháp và giới hạn khác nhau; **không áp dụng nguyên văn JSON indexing policy này cho tất cả Cosmos DB APIs**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa **item JSON, container, partition key, logical/physical partition, RU và index**.
- Phân biệt **point read** với truy vấn SQL và **single-partition** với **cross-partition query**.
- Đọc và thiết kế **indexing policy** với includedPaths, excludedPaths, indexingMode, automatic, compositeIndexes và spatialIndexes.
- Hiểu **range index mặc định**, khi nào dùng **composite index** hoặc **spatial index**.
- Tối ưu filter, ORDER BY, TOP, pagination, projection, aggregates và truy vấn trên mảng.
- Viết truy vấn tham số hóa trong **Azure Cosmos DB Java SDK v4**, truyền partition key và đọc request charge.
- Đánh giá truy vấn bằng **RU, query metrics, index metrics, latency và số partitions**.
- Cập nhật index policy có kiểm soát và hiểu thời gian **index transformation**.
- Phát hiện **hot partition**, indexing overhead, high-cardinality query patterns và truy vấn tốn RU.
- Lập checklist benchmark, giám sát, bảo mật và ngân sách trước khi đưa thay đổi production.

## 2. Mô hình dữ liệu Cosmos DB for NoSQL

Các khái niệm nền:

| Khái niệm | Chức năng | Ví dụ |
|---|---|---|
| **Account** | Tài nguyên Cosmos DB cấp cao, quản lý API/regions/consistency | cosmos-commerce-prod |
| **Database** | Nhóm logical containers | commerce |
| **Container** | Ranh giới dữ liệu và cấu hình partition key/index policy, throughput tùy mô hình | orders |
| **Item** | Tài liệu JSON có trường id và partition key | Một đơn hàng |
| **Partition key path** | Đường dẫn xác định logical partition của item | /tenantId |
| **Logical partition** | Nhóm items cùng giá trị partition key | tenant-a |
| **Physical partition** | Đơn vị storage/throughput do dịch vụ quản lý, có thể chứa nhiều logical partitions | Do Cosmos DB phân bổ |
| **RU** | Đơn vị đo tài nguyên được tiêu thụ bởi thao tác | Điểm đọc, query, ghi, index work |
| **RU/s** | Throughput được cấp phát hoặc autoscale theo cấu hình | Container/database throughput |

Một container có thể chia dữ liệu ra nhiều physical partitions. Khi query không xác định được phạm vi logical partition, Cosmos DB có thể cần xử lý trên nhiều physical partitions và hợp nhất kết quả. Điều này thường tốn RU và latency hơn so với xử lý có định tuyến rõ ràng, tùy dữ liệu và câu truy vấn.

~~~text
Java Orders API
       |
       | Request có tenantId?
       v
Cosmos DB container: orders
  partition key path = /tenantId
       |
       +-- Logical partition tenant-a
       |       +-- order-101
       |       +-- order-102
       |
       +-- Logical partition tenant-b
       |       +-- order-501
       |       +-- order-502
       |
       +-- Logical partition tenant-c
               +-- order-900

Indexing policy áp dụng ở cấp container;
Query scope và RU còn phụ thuộc partition key và query shape.
~~~

**Không thể thay partition key của một container đang có dữ liệu bằng cách chỉ sửa trường indexingPolicy.** Nếu phân vùng sai, thường phải thiết kế container mới và lập kế hoạch migrate/cutover, với các ngoại lệ/tính năng chuyên biệt cần xác minh theo dịch vụ.

## 3. Tài liệu JSON mẫu cho bài học

Giả sử container **orders** có partition key **/tenantId**. Một item:

~~~json
{
  "id": "order-102",
  "tenantId": "tenant-a",
  "customerId": "customer-17",
  "status": "CONFIRMED",
  "createdAt": "2026-11-20T08:15:30Z",
  "totalAmount": 1250000,
  "currency": "VND",
  "region": "southeast-asia",
  "items": [
    {"sku": "SKU-123", "quantity": 2, "price": 500000},
    {"sku": "SKU-456", "quantity": 1, "price": 250000}
  ],
  "shipping": {
    "city": "Ho Chi Minh City",
    "method": "EXPRESS"
  },
  "largePayload": {
    "rawImportRecord": "A large audit/import payload not searched by the API"
  }
}
~~~

Các giá trị là **dữ liệu giả**. Không đưa thông tin khách hàng thật, token, secret hoặc số thẻ thanh toán vào ví dụ, log hoặc telemetry.

Các mẫu truy cập mong muốn:

| Mẫu | Đường truy cập | Độ quan trọng |
|---|---|---|
| Tra một order đã biết id + tenantId | **Point read** | Rất thường xuyên |
| Liệt kê 20 orders gần nhất theo tenant | WHERE tenantId, ORDER BY createdAt | Thường xuyên |
| Lọc orders theo status và ngày trong tenant | WHERE tenantId/status/date | Thường xuyên |
| Báo cáo số orders theo status, trong tenant | COUNT/GROUP BY | Theo lịch |
| Tìm SKU trong danh sách items | ARRAY_CONTAINS/EXISTS/JOIN tùy shape | Ít thường xuyên |
| Tìm mọi tenant theo một chuỗi tùy ý | Có thể cross-partition/scan | Cần xem lại thiết kế |

**Thiết kế index bắt đầu từ workload và query patterns**, không bắt đầu bằng cách lập tất cả chỉ mục có thể tạo. Mỗi index thêm vào có thể ảnh hưởng chi phí write, kích thước lưu trữ và quá trình cập nhật policy.

## 4. Request Unit (RU) là gì và vì sao query tốn RU?

Trong Cosmos DB, **RU** là thước đo tổng hợp cho tài nguyên xử lý một thao tác: CPU, memory và I/O theo mô hình dịch vụ. Mỗi request có mức tiêu thụ RU, có thể được trả qua header như **x-ms-request-charge**, SDK response hoặc metrics.

Một số yếu tố ảnh hưởng RU:

1. Kích thước item và dữ liệu trả về.
2. Số items được kiểm tra, index lookups và độ chọn lọc filter.
3. Có định tuyến đúng logical partition không.
4. Số physical partitions tham gia.
5. ORDER BY, DISTINCT, JOIN trên mảng, aggregates và độ phức tạp query.
6. Kiểu và số lượng chỉ mục duy trì khi ghi.
7. Consistency level/replica access theo điều kiện triển khai.

~~~text
Ví dụ minh họa, KHÔNG phải phép đo Cosmos DB:

Point read (id + partition key)   -> RU thấp, định tuyến trực tiếp
Query lọc trong một partition    -> RU phụ thuộc filter/index/result
Cross-partition query            -> Có thể tăng RU + latency đáng kể
Scan nhiều item / trả payload lớn-> Có thể tiêu tốn nhiều RU
~~~

Không có một mức RU cố định cho tất cả point reads hoặc queries. Một item lớn hơn, query khác, consistency khác và service configuration khác có thể tạo mức tiêu thụ khác.

### RU và RU/s khác nhau

**RU** đo lượng đã tiêu thụ cho một thao tác. **RU/s** là mức throughput được cấp phát hoặc autoscale. Nếu nhiều requests đồng thời đòi hỏi throughput vượt capacity trong một khoảng thời gian, Cosmos DB có thể trả **429 Too Many Requests** kèm thời gian retry gợi ý.

~~~text
Mức dự trù RU/s sơ bộ
= Tổng (mỗi loại request/giây × RU trung bình/loại)
+ headroom cho peak, background jobs và variation
~~~

Đây là công thức **ước lượng capacity**, không thay load test thực. **Tăng RU/s mà không sửa truy vấn/partition key sai** có thể chỉ tăng hóa đơn.

## 5. Index trong Cosmos DB hoạt động ở mức khái niệm

Cosmos DB for NoSQL có cơ chế indexing tự động theo **indexing policy** của container. Khi ghi item, các thuộc tính phù hợp policy được đưa vào chỉ mục. Query engine dùng index để tìm items thỏa điều kiện mà không phải duyệt từng document theo cách scan thuần túy.

~~~text
Orders JSON document
  |
  | Indexing policy
  +-- /tenantId
  +-- /status
  +-- /createdAt
  +-- /totalAmount
  +-- /items/[]/sku
  |
  v
Index structures
  |
  +-- Filter / range / sort lookups
  +-- Composite ordering nếu được khai báo
  +-- Spatial lookups nếu có spatial index
~~~

Sơ đồ chỉ minh họa các paths, không mô tả chính xác layout nội bộ của index.

### Trade-off chỉ mục

| Nếu index nhiều thuộc tính | Nếu index có chọn lọc |
|---|---|
| Dễ đáp ứng nhiều truy vấn ad hoc | Tối ưu cho query patterns đã biết |
| Có thể tăng RU khi ghi và index storage | Có thể giảm chi phí ghi/storage |
| Ít nguy cơ thiếu đường index phổ biến | Phải quản trị khi query mới xuất hiện |
| Thường phù hợp giai đoạn tìm hiểu | Phù hợp workload ổn định/có benchmark |

**Không phải cứ ít index thì đọc sẽ nhanh**. Loại bỏ index cho thuộc tính hay lọc/sắp xếp có thể khiến query tốn RU hơn nhiều hoặc một số ORDER BY không thể chạy.

## 6. Index policy mặc định và thành phần JSON

Một policy mặc định trong Cosmos DB for NoSQL thường lập chỉ mục cho phần lớn các thuộc tính của item bằng **range index**, với các trường hệ thống/đường dẫn đặc biệt có thể được loại trừ theo chính sách mặc định của dịch vụ. Hãy **đọc policy thật của container**, không suy luận hoàn toàn từ ví dụ.

Ví dụ policy dạng tổng quát:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/*"}
  ],
  "excludedPaths": [
    {"path": "/\"_etag\"/?"}
  ],
  "compositeIndexes": [],
  "spatialIndexes": []
}
~~~

Đây là ví dụ phù hợp với cấu trúc policy của **API for NoSQL**; giá trị chính xác có thể thay đổi theo phiên bản SDK, cấu hình container hoặc tính năng chuyên biệt.

### Các trường

| Trường | Ý nghĩa |
|---|---|
| **indexingMode** | Cách duy trì index, thường là consistent; một số workload dùng none theo điều kiện |
| **automatic** | Có tự lập chỉ mục item mới theo policy hay không |
| **includedPaths** | Những đường dẫn được đưa vào index |
| **excludedPaths** | Những đường dẫn loại khỏi index |
| **compositeIndexes** | Những tổ hợp property và chiều sort cần index phối hợp |
| **spatialIndexes** | Index phục vụ truy vấn không gian với GeoJSON và spatial functions |

Trong một số tình huống, ngoài các trường này còn có cấu hình indexing cho **vector/full-text** hoặc tính năng mới theo khả năng tài khoản/API. **Không coi policy của các loại index chuyên biệt như một phần tự động của range index mặc định**.

## 7. Indexing mode: consistent và none

**Consistent indexing** là chế độ thông thường: index được duy trì khi dữ liệu được thay đổi, hỗ trợ queries sử dụng index theo consistency của dịch vụ. Nó phù hợp hầu hết ứng dụng cần truy vấn theo nhiều thuộc tính.

**None** tắt indexing theo policy cho container/workload tương ứng, có thể hữu ích trong một số kịch bản ingestion/bulk load đặc thù nhưng làm mất khả năng query sử dụng index như bình thường. Nó có thể khiến queries không được hỗ trợ/tăng chi phí hoặc phụ thuộc scan tùy cấu hình.

| Cấu hình | Khi cân nhắc | Rủi ro |
|---|---|---|
| **consistent** | API dùng filter, ORDER BY, report theo JSON | Ghi phải duy trì index, tăng RU so với không index |
| **none** | Một số batch ingestion/load/đọc chủ yếu theo id+PK | Truy vấn thuộc tính có thể rất tốn RU/không khả dụng |

**Không tắt indexing trên container production chỉ để giảm RU ghi** khi các APIs đang dựa vào query. Nếu có job nhập dữ liệu lớn, đánh giá phương án container riêng/bulk execution, kiểm tra khôi phục index, rồi benchmark đầy đủ.

### Automatic không đồng nghĩa không có giới hạn

**automatic: true** nghĩa Cosmos DB tự duy trì index cho các paths theo policy. Không có nghĩa index tự phát hiện và tạo **mọi composite index** theo thứ tự mà ứng dụng cần, cũng không tự sửa partition key xấu.

## 8. Ngữ pháp đường dẫn includedPaths và excludedPaths

Path dùng cú pháp dựa trên cấu trúc JSON:

| Pattern | Ý nghĩa khái niệm |
|---|---|
| Root wildcard: /* | Toàn bộ đường dẫn/con cháu theo wildcard |
| **/status/?** | Giá trị thuộc tính status tại vị trí chỉ định |
| **/shipping/city/?** | Một thuộc tính lồng nhau |
| Descendant wildcard: /largePayload/* | Nội dung con của đối tượng largePayload |
| **/items/[]/sku/?** | Giá trị sku trong các phần tử mảng items |

Trong JSON phải viết chính xác các chuỗi đường dẫn như /* và /largePayload/*, không có khoảng trắng. Ký tự **?** thường biểu diễn đường dẫn đến một giá trị và dấu sao (*) biểu diễn wildcard xuống các cấp con; cú pháp path/index kind cần tuân theo hướng dẫn API for NoSQL.

### Path có phân biệt chữ hoa/chữ thường

JSON property **createdAt** và **CreatedAt** là hai tên khác nhau. Nếu code đọc sai chữ hoa hoặc một số documents có trường thiếu/khác type, filter/sort có thể cho kết quả không như dự kiến.

### Quy tắc khi trùng included/excluded

Policy hỗ trợ các paths bao gồm/loại trừ, trong đó đường dẫn cụ thể có thể được ưu tiên so với wildcard theo quy tắc của dịch vụ. Nếu dùng wildcard root và một số ngoại lệ:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [
    {"path": "/largePayload/*"},
    {"path": "/\"_etag\"/?"}
  ]
}
~~~

Kết quả mong muốn: giữ index cho phần lớn thuộc tính nhưng không index các field con của **largePayload** (nếu chúng không dùng cho filter/sort), và loại trừ một path hệ thống được ví dụ. **Đừng loại trừ trường id, tenantId, status hoặc createdAt khi các API dùng query trên các trường này mà không đo lại.**

## 9. Chiến lược chỉ index các paths được truy vấn

Với workload cố định và payload lớn, có thể bắt đầu từ policy **không index wildcard root**, rồi thêm các paths thật sự cần query:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/tenantId/?"},
    {"path": "/status/?"},
    {"path": "/createdAt/?"},
    {"path": "/customerId/?"},
    {"path": "/items/[]/sku/?"}
  ],
  "excludedPaths": [
    {"path": "/*"}
  ]
}
~~~

Đây là **minh họa có chủ đích cho container chuyên dụng**, không phải phương án mặc định khuyến nghị. Một số đường dẫn hệ thống vẫn được xử lý đặc biệt theo API, và hành vi query khi property không index cần được xác minh. **Chuyển sang exclude-all trong production có thể làm queries cũ tăng RU hoặc không còn hoạt động như mong muốn.**

### Khi nào chọn index chọn lọc?

- Contract truy vấn ổn định, hầu hết APIs chỉ sử dụng một số fields.
- Item có nhiều metadata/largePayload không bao giờ dùng cho filter/sort.
- Workload ghi rất nhiều và indexing overhead trở thành chi phí đáng kể.
- Có thể chạy performance regression tests cho mọi query phổ biến.
- Có quy trình thay đổi policy, quan sát reindexing và rollback có kiểm soát.

Nếu sản phẩm đang giai đoạn khám phá với nhiều truy vấn ad hoc, **index mặc định** thường giúp tránh lỗi chức năng bất ngờ.

## 10. Composite indexes phục vụ những mẫu truy vấn nào?

**Composite index** khai báo **thứ tự các thuộc tính** và **chiều ascending/descending** để hỗ trợ những truy vấn yêu cầu nhiều điều kiện hoặc ORDER BY trên nhiều properties.

Ví dụ ứng dụng cần:

~~~sql
SELECT c.id, c.status, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.status ASC, c.createdAt DESC
~~~

Một **ORDER BY trên nhiều thuộc tính** của API for NoSQL thường cần composite index tương ứng. Chỉ có range index mặc định cho từng property **không nhất thiết** đáp ứng thứ tự sắp xếp nhiều cột.

Ví dụ khai báo trong indexing policy:

~~~json
{
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ]
}
~~~

Đây là **fragment**, phải được đặt bên trong policy hoàn chỉnh (gồm indexingMode, paths...) và thay đổi qua API/Portal. Không truyền fragment này thành toàn bộ indexing policy.

### Chiều sắp xếp quan trọng

Đối với query:

~~~sql
ORDER BY c.status ASC, c.createdAt DESC
~~~

Một composite index **status ASC, createdAt DESC** phù hợp mẫu. Thứ tự đường dẫn và hướng sort phải tương thích query theo quy tắc Cosmos DB. Với sự đảo chiều toàn bộ ORDER BY, một số cấu hình có thể dùng cùng index theo hướng ngược lại; **không suy luận mọi hoán vị ASC/DESC đều được tối ưu như nhau**.

### Filter equality kết hợp ORDER BY

Ví dụ:

~~~sql
SELECT c.id, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
ORDER BY c.createdAt DESC
~~~

Vì query có nhiều điều kiện và sắp xếp, một composite index liên quan **status + createdAt** (và trong một số workload có thể thêm thuộc tính khác) có thể giảm RU. Nhưng **không khẳng định composite index luôn cần thiết hoặc chắc chắn nhanh hơn**: single-property ORDER BY có thể dùng range index; điểm mấu chốt vẫn là **partition key được định tuyến đúng và query metrics đo được lợi ích**.

### Không tạo composite index vô hạn

Mỗi composite index thêm vào làm tăng khối lượng duy trì chỉ mục và có các giới hạn về số paths/index definitions. Chỉ tạo index cho nhóm query phổ biến/thật sự quan trọng, và đo tác động lên **write RU**, **query RU**, **index storage** và thời gian reindex.

## 11. Spatial index và truy vấn GeoJSON

Nếu item chứa vị trí dạng **GeoJSON** và ứng dụng cần tìm theo khu vực/khoảng cách, có thể dùng **spatial index** với spatial operators được Cosmos DB hỗ trợ.

Ví dụ item:

~~~json
{
  "id": "store-001",
  "tenantId": "tenant-a",
  "name": "Demo Store",
  "location": {
    "type": "Point",
    "coordinates": [106.70, 10.78]
  }
}
~~~

GeoJSON tọa độ thường theo thứ tự **longitude, latitude**; không đảo thành latitude, longitude. Các giá trị ví dụ chỉ dùng minh họa.

Một ví dụ fragment spatialIndexes:

~~~json
{
  "spatialIndexes": [
    {
      "path": "/location/*",
      "types": ["Point"]
    }
  ]
}
~~~

**Cần xác minh path syntax, loại hình học và khả năng index trong phiên bản API for NoSQL đang dùng trước khi apply.** Spatial index hỗ trợ truy vấn đặc thù như **ST_DISTANCE, ST_WITHIN, ST_INTERSECTS** theo cú pháp được hỗ trợ, không thay range/composite index cho các truy vấn đơn hàng thường.

Ví dụ kiểm tra khoảng cách (mét) theo dữ liệu/vị trí minh họa:

~~~sql
SELECT c.id, c.name
FROM c
WHERE ST_DISTANCE(
  c.location,
  {"type":"Point", "coordinates":[106.70,10.78]}
) < 5000
~~~

Không dùng truy vấn này để tuyên bố khoảng cách tuyến đường/thời gian lái xe; **spatial distance** không tương đương routing trên mạng đường phố.

## 12. Index policy không thay thế partition key

Mô hình phân vùng là một trong những quyết định ảnh hưởng RU nhất. Với container partition key **/tenantId**:

~~~sql
SELECT c.id, c.status
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

Khi SDK cung cấp **partition key = tenant-a** trong request options, query được giới hạn rõ logical partition. Điều này giúp giảm phạm vi so với query toàn bộ container.

Nhưng nếu partition key là **/tenantId** và có một tenant chiếm phần lớn lưu lượng/khối lượng, các truy vấn của tenant đó có thể gây **hot logical partition**. Composite indexes tốt không tự phân phối hot tenant sang nhiều logical partitions.

### Chọn partition key theo workload

Một partition key tốt cần cân bằng:

- **Phân phối giá trị cao và ổn định** để tránh tập trung dữ liệu/thông lượng vào một giá trị.
- Hầu hết requests có thể **biết partition key** tại thời điểm truy cập.
- Hợp đồng truy vấn và transaction thường nằm trong một logical partition.
- Không vượt các giới hạn logical partition của cấu hình thực tế.
- Đủ khả năng phát triển cùng số tenants/dữ liệu theo thời gian.

Với SaaS có tenant rất lớn, có thể cân nhắc **hierarchical partition keys** hoặc thiết kế key khác khi API/tài khoản hỗ trợ, nhưng cần nghiên cứu khả năng route truy vấn, transaction, SDK và migration. **Đừng đổi partition key chỉ để sửa một report query chậm** khi phần lớn point reads đang rất hiệu quả.

## 13. Point read: truy xuất rẻ trước khi dùng SQL query

Khi đã biết **id** và **partition key value**, hãy ưu tiên **point read**:

~~~text
Order ID     = order-102
Partition key= tenant-a

Cosmos SDK readItem(id, partitionKey)
       |
       v
Định tuyến trực tiếp tới logical partition và item
~~~

So sánh:

~~~sql
SELECT * FROM c
WHERE c.id = "order-102"
  AND c.tenantId = "tenant-a"
~~~

Truy vấn SQL nhìn có vẻ tương đương nhưng **không đồng nghĩa** với thao tác point read ở mức chi phí/đường thực thi. SDK **readItem(id, partitionKey)** thường hiệu quả hơn trong use case truy xuất đúng một item.

### Khi nào không thể point read?

- Chỉ biết email hoặc externalOrderId, không biết Cosmos **id**.
- Không biết partition key của item.
- Cần lọc, tổng hợp, sắp xếp hoặc tìm nhiều items.
- API cần tìm theo nhiều thuộc tính không phải key.

Nếu phần lớn truy cập tra theo **ExternalOrderId**, có thể cân nhắc thiết kế id tương ứng, xây lookup container/map, hoặc điều chỉnh data model với chi phí đồng bộ và idempotency rõ ràng. Đừng tạo truy vấn cross-partition cho mọi request chỉ vì chưa thiết kế đường truy cập chính.

## 14. Single-partition query và cross-partition query

Một query trên container **orders** có thể được định tuyến bằng partition key hoặc phải chạy qua nhiều partitions.

### Query hẹp

~~~sql
SELECT c.id, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
~~~

Nếu SDK cung cấp **PartitionKey(tenantId)** và policy/permissions phù hợp, Cosmos DB có thể giới hạn truy vấn vào logical partition tương ứng.

### Query rộng

~~~sql
SELECT c.id, c.tenantId, c.totalAmount
FROM c
WHERE c.status = "PENDING"
~~~

Thiếu partition key, yêu cầu có thể trải qua nhiều physical partitions, cộng RU/latency để query và hợp nhất. Với nhiều partitions, cùng một query có thể tốn thêm RU khi container phát triển dù số kết quả cuối chỉ là 10.

### Những trường hợp cross-partition hợp lý

- Báo cáo toàn hệ thống theo lịch.
- Quản trị cần tìm dữ liệu xuyên tenants với quyền đặc biệt.
- Analytics không có đường partition key tốt hơn, nhưng có thể xuất sang hệ phân tích riêng.

Khi cần báo cáo toàn cục thường xuyên, cân nhắc **materialized view/aggregate container, change feed** hoặc nền tảng phân tích phù hợp. Không cố nâng RU/s cho truy vấn toàn container hàng giây nếu use case có thể được phục vụ bằng mô hình dữ liệu đọc tối ưu.

### Lọc theo partition key chưa chắc tự biến mọi query thành cheap

Nếu truy vấn lọc đúng tenant nhưng:

- Scan hàng triệu items trong tenant;
- Trả về một trường largePayload rất lớn;
- ORDER BY trên nhiều fields thiếu composite index;
- Thực hiện JOIN trên mảng lớn;

thì RU vẫn có thể cao. **Partition routing là điều kiện quan trọng nhưng không thay thế query/index tuning.**

## 15. Lọc equality, range, IN và tham số hóa

Các mẫu query thường gặp:

~~~sql
-- Đúng một trạng thái trong tenant
SELECT c.id, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
~~~

~~~sql
-- Phạm vi thời gian đã chuẩn hóa UTC
SELECT c.id, c.status, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
  AND c.createdAt >= @fromUtc
  AND c.createdAt < @toUtc
~~~

~~~sql
-- Hai trạng thái nghiệp vụ
SELECT c.id, c.status
FROM c
WHERE c.tenantId = @tenantId
  AND c.status IN ("PENDING", "CONFIRMED")
~~~

**Tham số hóa** giúp code dễ tái sử dụng và tránh nối chuỗi dữ liệu người dùng trực tiếp vào SQL query. Với REST/JDBC-like mindset, đừng giả định Cosmos DB NoSQL query engine và SQL Server engine có cùng optimization plans hoặc isolation semantics.

### Kiểu dữ liệu quan trọng

- **createdAt** ISO 8601 UTC có format nhất quán có thể hỗ trợ so sánh/sort string theo thứ tự thời gian trong những điều kiện rõ ràng. Nếu có nhiều formats/timezones khác nhau, kết quả dễ sai.
- **totalAmount** nên lưu số với đơn vị rõ (ví dụ VND nguyên hoặc amountMinorUnits) theo nghiệp vụ, tránh sử dụng floating-point thiếu kiểm soát cho tiền.
- **status** dùng giá trị nhất quán (CONFIRMED khác confirmed).
- Trường thiếu và trường bằng **null** không đồng nghĩa; query logic/ORDER BY cần xét undefined/null.

Nếu truy vấn thường xuyên dùng giá trị ngày, hãy lưu **dạng chuẩn** và dùng cùng type thay vì gọi các hàm chuyển đổi phức tạp ở mỗi query.

## 16. ORDER BY một trường và nhiều trường

### Sắp xếp một trường

~~~sql
SELECT c.id, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
~~~

Range index trên **createdAt** thông thường hỗ trợ **ORDER BY một property**. Không cần thêm composite index chỉ vì sort một trường, trừ khi benchmark filter+sort cụ thể chứng minh lợi ích.

### Sắp xếp hai trường

~~~sql
SELECT c.id, c.status, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.status ASC, c.createdAt DESC
~~~

Query nhiều ORDER BY expressions cần composite index tương ứng theo các quy tắc API for NoSQL. Ví dụ:

~~~json
{
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ]
}
~~~

### Stable ordering và pagination

Nếu nhiều orders có **createdAt** bằng nhau, chỉ ORDER BY createdAt không tạo thứ tự duy nhất về mặt nghiệp vụ. Có thể bổ sung tie-breaker như id, nhưng điều này có thể đòi **composite index mới** và cần xác minh query/SDK/pagination.

Ví dụ:

~~~sql
SELECT c.id, c.createdAt, c.status
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC, c.id ASC
~~~

Với query này, cần đánh giá composite index **createdAt DESC, id ASC** và các rules hỗ trợ. **Không tự giả định kết quả trang 1 và trang 2 sẽ cố định trong lúc nhiều records đang được thêm/xóa**: ngay cả khi sort có tie-breaker, dữ liệu thay đổi giữa hai requests vẫn ảnh hưởng kết quả; xem tiếp phần continuation.

## 17. Projection: chỉ lấy những trường cần thiết

Hai query:

~~~sql
SELECT *
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

~~~sql
SELECT c.id, c.status, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

**SELECT \*** trả toàn bộ JSON item, có thể gồm items[], metadata, largePayload và các trường không cần hiển thị. **Projection** chỉ trả những trường frontend cần, có thể giảm payload, network transfer và một số chi phí xử lý; lợi ích RU cụ thể phụ thuộc query engine/index/documents và cần đo.

### Những tình huống nên tránh SELECT *

- API danh sách 20 đơn hàng nhưng chỉ cần 4 trường.
- Admin dashboard thống kê count/total, không cần toàn bộ payload.
- Một item có largePayload hoặc mảng items lớn.
- Data export cần schema được whitelist thay vì lộ trường mới.

**Projection không tự biến query thành point read** và không loại bỏ RU cho việc tìm items/aggregation. Đừng dùng projection làm cớ bỏ authorization field-level khi dữ liệu nhạy cảm.

## 18. TOP, OFFSET LIMIT và continuation tokens

### TOP chỉ giới hạn kết quả, không tự sửa phạm vi query

~~~sql
SELECT TOP 20 c.id, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
~~~

TOP giới hạn số items trả theo cú pháp Cosmos DB; vẫn cần filter/index hiệu quả. Với cross-partition query, lấy TOP 20 có thể phải xử lý nhiều partitions để xác định 20 kết quả đúng.

### OFFSET LIMIT không phù hợp phân trang sâu

~~~sql
SELECT c.id, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
OFFSET 10000 LIMIT 20
~~~

OFFSET 10000 có thể yêu cầu engine bỏ qua số lượng lớn kết quả trước khi trả 20 items; **RU/latency thường tăng theo độ sâu**. Nó không phải giải pháp mặc định cho API có hàng trăm nghìn records.

### Continuation token

Cosmos DB query execution thường có **continuation tokens** để tiếp tục lấy trang kế tiếp. Java SDK trả paged iterable/flux và cho phép duyệt pages; một số API expose tokens để app quản lý. Ưu tiên **SDK paging/continuation** cho danh sách nhiều trang thay vì tăng OFFSET.

~~~text
GET /orders?limit=20
   |
   v
Query page 1 -> 20 items + continuation token
   |
   v
GET /orders?cursor=<OPAQUE_TOKEN>
   |
   v
Query page 2 -> 20 items + token kế tiếp
~~~

Token là một giá trị opaque chứa trạng thái query theo cơ chế SDK/service, **không nên parse hoặc sửa bằng tay**. Không dùng token làm user authorization; phải bảo vệ access tới tenant, query params và tránh log token nếu có nội dung nhạy cảm.

**Continuation token không bảo đảm snapshot nhất quán của mọi records trong một danh sách luôn thay đổi**. Cần mô hình khóa/timestamp/snapshot/cursor hợp đồng riêng nếu nghiệp vụ yêu cầu danh sách bất biến qua nhiều trang.

### Số lượng mục mỗi trang

Một query có thể trả ít hơn max page size vì thời gian/thông lượng/partition execution. Không suy ra "hết dữ liệu" khi trang hiện tại có 12/20 items nếu vẫn còn continuation token. Client cần dùng cơ chế continuation chính thức cho tới khi không còn token hoặc đạt mục tiêu.

## 19. Aggregations: COUNT, SUM, GROUP BY

Ví dụ đếm orders đã xác nhận:

~~~sql
SELECT VALUE COUNT(1)
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

Tính tổng:

~~~sql
SELECT VALUE SUM(c.totalAmount)
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

Thống kê theo trạng thái:

~~~sql
SELECT c.status, COUNT(1) AS orderCount
FROM c
WHERE c.tenantId = @tenantId
GROUP BY c.status
~~~

Một aggregation vẫn có chi phí xử lý số lượng items/index entries phù hợp với filter. **COUNT không mặc định là O(1)** như đọc một biến được cập nhật liên tục; một số truy vấn COUNT xuyên nhiều partitions có thể đắt.

### Khi nào nên duy trì aggregate riêng?

Nếu dashboard gọi COUNT/SUM trên hàng triệu orders mỗi vài giây, cân nhắc lưu aggregates theo tenant/status/date trong container đọc riêng, cập nhật bằng **change feed processing** hoặc event-driven workflow có idempotency.

Trade-off:

- Query dashboard rẻ và nhanh hơn.
- Có thêm độ trễ cập nhật và logic giữ consistency.
- Aggregates cần replay/reconciliation khi consumer lỗi.
- Phải quản lý quyền/partition key/index của container aggregate.

Không duy trì "total amount" bằng cách increment không an toàn khi event có thể retry/duplicate. Cần deduplication và kiểm tra tính nhất quán nghiệp vụ.

## 20. Query trên mảng và nested properties

Một item có danh sách **items**:

~~~json
{
  "id": "order-102",
  "tenantId": "tenant-a",
  "items": [
    {"sku": "SKU-123", "quantity": 2},
    {"sku": "SKU-456", "quantity": 1}
  ]
}
~~~

### EXISTS/JOIN tìm một SKU

~~~sql
SELECT c.id
FROM c
WHERE c.tenantId = @tenantId
  AND EXISTS (
    SELECT VALUE i
    FROM i IN c.items
    WHERE i.sku = @sku
  )
~~~

Hoặc dùng JOIN trong query phù hợp:

~~~sql
SELECT c.id, i.sku, i.quantity
FROM c
JOIN i IN c.items
WHERE c.tenantId = @tenantId
  AND i.sku = @sku
~~~

**JOIN trong Cosmos DB for NoSQL hoạt động trong phạm vi một item với dữ liệu mảng**, không phải relational JOIN giữa hai containers độc lập như Azure SQL. JOIN có thể làm tăng số intermediate/output rows khi mảng lớn.

### Index path cho mảng

Path minh họa:

~~~text
/items/[]/sku/?
~~~

Với includedPaths, có thể index các thuộc tính của mảng. Cần kiểm tra rằng policy không exclude đường này, truy vấn dùng đúng JSON property names/types và **query metrics** chứng minh chỉ mục có ích.

### Khi mảng quá lớn

Nếu một order có hàng nghìn item con, việc sửa một phần tử có thể kéo theo update item JSON lớn, chi phí ghi cao và giới hạn kích thước item. Có thể tách line items thành các documents khác cùng partition key để tận dụng transactional batch theo khả năng API, nhưng sẽ tăng số point reads/querys và độ phức tạp.

Thiết kế mô hình dữ liệu theo **aggregate boundaries và access patterns**, không bê nguyên dạng bảng quan hệ vào Cosmos DB bằng mọi giá.

## 21. Hàm chuỗi, expression và nguy cơ scan

Không phải mọi predicate có thể được tối ưu như so sánh equality trên một path có range index.

### Ví dụ tìm kiếm mơ hồ

~~~sql
SELECT c.id, c.customerId
FROM c
WHERE CONTAINS(c.customerName, @term, true)
~~~

Các hàm string và biểu thức tính toán có đặc điểm tận dụng index khác nhau theo query engine/phiên bản; một số trường hợp **CONTAINS** được tối ưu theo range index, nhưng vẫn có thể tốn nhiều RU khi pattern không chọn lọc hoặc truy vấn cross-partition. **Không mặc định mọi CONTAINS đều scan hoặc mọi CONTAINS đều rẻ.**

### Những anti-pattern cần đo kỹ

- Không giới hạn partition key cho tìm kiếm toàn bộ accounts.
- Áp dụng hàm biến đổi dữ liệu trên field của mọi item trong WHERE.
- Nối nhiều OR/IN quá rộng với kết quả ít nhưng index candidates lớn.
- Trả hàng nghìn items rồi lọc lại trong Java.
- Query liên tục trên thuộc tính đã excluded khỏi index.
- Dùng queries để tìm document theo id+partition key thay vì point read.

Nếu sản phẩm cần **full-text search, relevance ranking, typo tolerance hoặc vector similarity**, đánh giá tính năng tìm kiếm/index chuyên biệt của Cosmos DB và/hoặc Azure AI Search theo support matrix, latency/cost và consistency requirements. **Không dùng range index mặc định như một lời hứa thay thế công cụ search chuyên dụng.**

## 22. Java SDK v4: point read với partition key

**Azure Cosmos DB Java SDK v4** có namespace thường dùng **com.azure.cosmos**. Ví dụ ứng dụng lấy **CosmosContainer** đã được cấu hình bằng endpoint và credential an toàn:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

// container đã được khởi tạo từ CosmosClient có identity phù hợp.
String orderId = "order-102";
String tenantId = "tenant-a";

CosmosItemResponse<Order> response =
    container.readItem(orderId, new PartitionKey(tenantId), Order.class);

Order order = response.getItem();
double requestCharge = response.getRequestCharge();

System.out.println("RU for point read: " + requestCharge);
~~~

Đây là **đoạn code đặt trong phương thức đã có container và class Order**, chưa phải một chương trình Java hoàn chỉnh. Cần kết hợp với **CosmosClientBuilder**, connection settings, repository/service class và exception handling phù hợp.

### Tại sao phải truyền cả tenantId?

Cosmos DB cần **id + partition key** để định tuyến point read. Một **id** có thể trùng ở hai logical partitions nếu container và unique constraints cho phép. Nếu truyền sai partition key, bạn có thể nhận **404 Not Found** ngay cả khi item có id đó ở một partition khác.

### Client lifecycle

Trong Spring Boot, thường tạo và tái sử dụng **CosmosClient**/container reference theo vòng đời ứng dụng, không tạo client mới cho mỗi HTTP request. Kết hợp identity, connection mode, thread safety và timeout settings theo tài liệu SDK. Đóng client khi ứng dụng shutdown.

## 23. Java SDK: query có parameters và partition key

Ví dụ dùng **SqlQuerySpec** với params thay vì nối chuỗi SQL. Giả sử Order có các trường id, tenantId, status, createdAt và totalAmount.

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.FeedResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;
import com.azure.cosmos.util.CosmosPagedIterable;
import java.util.List;

String tenantId = "tenant-a";
String status = "CONFIRMED";

String sql = """
    SELECT c.id, c.tenantId, c.status, c.createdAt, c.totalAmount
    FROM c
    WHERE c.tenantId = @tenantId
      AND c.status = @status
    ORDER BY c.createdAt DESC
    """;

SqlQuerySpec query = new SqlQuerySpec(
    sql,
    List.of(
        new SqlParameter("@tenantId", tenantId),
        new SqlParameter("@status", status)
    )
);

CosmosQueryRequestOptions options = new CosmosQueryRequestOptions();
options.setPartitionKey(new PartitionKey(tenantId));
options.setPopulateQueryMetrics(true);

CosmosPagedIterable<Order> results =
    container.queryItems(query, options, Order.class);

for (FeedResponse<Order> page : results.iterableByPage(20)) {
    System.out.println("Page RU: " + page.getRequestCharge());
    for (Order order : page.getResults()) {
        System.out.println(order.id);
    }
}
~~~

Code dùng **Java text blocks** (JDK 15+) và giả định class Order có trường id dễ truy cập; trong thực tế thường dùng getter/record tùy cách serialize. Nếu dùng Java phiên bản thấp hơn, thay text block bằng chuỗi thông thường. **Dependency Azure Cosmos Java SDK v4**, API method signatures và query metrics accessors cần khớp phiên bản SDK đã pin trong dự án.

### Những điều cần chú ý

1. **SetPartitionKey** giới hạn query đúng tenant; đừng lấy tenantId từ client input chưa được authorization.
2. **SqlParameter** tránh nối dữ liệu vào query string; quyền dữ liệu vẫn cần kiểm tra riêng.
3. **Projection** chỉ lấy trường cần hiển thị; class mapping/serialization phải tương thích.
4. **iterableByPage(20)** xác định page-size hint, không phải giới hạn toàn bộ results.
5. **getRequestCharge()** là chi phí của **từng page**, nếu duyệt nhiều trang phải cộng RU.
6. **setPopulateQueryMetrics(true)** bật query diagnostics khi SDK hỗ trợ; log/đánh giá metrics an toàn.
7. Query kết quả có thể thay đổi trong lúc paging; không giả định một transaction snapshot cho toàn bộ danh sách.

### Không đưa khóa tài khoản vào code

Nếu có thể, dùng **Microsoft Entra ID/managed identity** để truy cập Cosmos DB data plane, với SDK/token credentials và role assignments phù hợp. Một đoạn khởi tạo client khái niệm:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;

CosmosClient client = new CosmosClientBuilder()
    .endpoint("https://<ACCOUNT_NAME>.documents.azure.com:443/")
    .credential(new DefaultAzureCredentialBuilder().build())
    .buildClient();

CosmosContainer container =
    client.getDatabase("commerce").getContainer("orders");
~~~

Cần xác minh Azure SDK dependencies, Cosmos data-plane roles, network và API hỗ trợ Entra authentication cho tài khoản hiện tại. **Azure RBAC Contributor trên Cosmos account không tự cấp quyền query dữ liệu**; Cosmos DB for NoSQL có các cơ chế data-plane RBAC riêng. Không đưa primary account key vào Git/Container image để bỏ qua lỗi identity.

## 24. Query metrics: đo gì trước khi thay index?

Portal Data Explorer, SDK diagnostics hoặc hệ thống quan sát có thể cung cấp **request charge**, **query metrics** và **index metrics** (tùy SDK/tool/configuration).

| Chỉ số | Câu hỏi |
|---|---|
| **Request charge (RU)** | Mỗi query/page dùng bao nhiêu tài nguyên? |
| **End-to-end latency** | Client nhận đủ dữ liệu trong bao lâu? |
| **Backend/query execution time** | Engine xử lý mất bao lâu? |
| **Retrieved document count** | Bao nhiêu documents/items được xử lý/đọc trong query? |
| **Output document count** | Bao nhiêu documents/items thật được trả? |
| **Index utilization / index metrics** | Index có được tận dụng, có đề xuất composite/path khác không? |
| **Partition count/fan-out** | Có bao nhiêu partitions tham gia? |
| **Throttled requests (429)** | Có vượt throughput hoặc hot partition không? |
| **Page count / continuation** | Truy vấn cần bao nhiêu requests để lấy hết? |

**Tên trường metric chính xác** có thể khác giữa Azure Portal, REST headers và SDK Java. Query metrics chỉ có giá trị khi bạn kiểm tra đúng truy vấn, dữ liệu, page và phiên bản công cụ. Đừng bịa một con số "index hit 100%" khi tool không hiển thị.

### RU thấp nhưng latency cao?

Có thể do:

- Client ở region rất xa Cosmos DB region.
- Network/proxy/DNS hoặc TLS handshake.
- Connection mode và SDK retry, resource contention trên app.
- Nhiều pages hoặc cross-region reads.

### RU cao nhưng latency chưa tăng?

Có thể truy vấn được cấp nhiều throughput RU/s nên vẫn nhanh ở hiện tại, nhưng chi phí cao và rủi ro 429 khi traffic tăng. **Tối ưu RU vẫn có giá trị ngay cả khi p95 latency đang đạt SLO.**

### Index metrics có phải câu trả lời tuyệt đối?

Không. Một query có thể sử dụng index tốt mà vẫn đắt do kết quả quá lớn, cross-partition, JOIN fan-out hoặc network payload. Cần đọc đồng thời **RU, items read/returned, index metrics, partitions, time range và query shape**.

## 25. Benchmark so sánh policy trước/sau

Thay policy chỉ sau khi có **baseline** và **test case reproducible**.

### Chuẩn bị

1. Chọn dataset đại diện về số items, phân bố tenants, nested arrays và kích thước payload.
2. Tạo **container lab riêng** hoặc clone/test environment được cho phép.
3. Ghi throughput model (manual/autoscale/serverless), RU/s max, region, consistency và SDK version.
4. Lưu **index policy hiện tại** và query templates/query params.
5. Có danh sách top N queries từ logs/telemetry, phân nhóm read/query/write.
6. Đặt đúng partition key trong SDK khi use case đã biết.
7. Kiểm tra permission/identity và không dùng dữ liệu nhạy cảm thật nếu không cần.

### Đo theo ma trận

| Test | Mẫu request | Đo |
|---|---|---|
| **P1** | Point read id+PK | RU, p50/p95 latency |
| **Q1** | Tenant + status equality | RU/page, retrieved/output |
| **Q2** | Tenant + createdAt range, ORDER BY | RU, latency |
| **Q3** | Multiple ORDER BY fields | Composite index support/RU |
| **Q4** | OFFSET sâu vs continuation paging | Tổng RU và duration |
| **Q5** | Aggregation theo tenant | RU, time, accuracy |
| **Q6** | Query SKU trong nested array | RU, index metrics |
| **W1** | Bulk writes cùng payload | RU/item, throughput |
| **W2** | Updates của largePayload | RU/write, index storage growth |
| **H1** | Peak traffic với hot tenant | 429, throttling, latency |

### Đảm bảo so sánh công bằng

- Dùng cùng dữ liệu/query parameters và tương đương throughput.
- Lấy đủ sample, tính trung vị/p95, đừng dùng một request duy nhất.
- Kiểm tra index transformation **đã hoàn tất** trước khi đo kết quả cuối.
- Cách ly batch load và queries không liên quan khi có thể.
- Tính **tổng RU cho toàn bộ tập kết quả**, không chỉ page đầu.
- Xem cả **query RU giảm** và **write RU/storage tăng**.

### Bảng đánh giá minh họa

| Query/operation | Policy A: RU trung bình | Policy B: RU trung bình | Kết luận |
|---|---:|---:|---|
| Q1 tenant+status | 8,0 | 5,5 | B có lợi cho query này |
| Q3 multi-order | Không phù hợp index | 12,0 | B hỗ trợ ORDER BY mới |
| W1 write item | 6,0 | 7,2 | B làm write đắt hơn |
| W2 update payload | 10,5 | 7,0 | Exclude payload có thể lợi |

**Tất cả con số là giả định để học cách so sánh**, không phải benchmark đo từ Cosmos DB hay mức RU được bảo đảm. Đánh giá policy theo trọng số **request frequency × RU/query** và chất lượng SLO, không chỉ RU của một query nổi bật.

## 26. Đọc policy và Query Metrics từ Azure Portal

Trên subscription lab được phép:

1. Vào [Azure Portal](https://portal.azure.com), mở **Azure Cosmos DB account**.
2. Chọn **Data Explorer**, database và container API for NoSQL đúng.
3. Xem **Indexing Policy** của container; ghi lại indexingMode, included/excluded, composite và spatial.
4. Chạy một query read-only có điều kiện partition key/parameters rõ.
5. Bật/xem **Query Stats, Query Metrics, Index Metrics** nếu Portal hiện hành cung cấp.
6. Ghi RU, latency, retrieved/output counts và partition/query plan observations.
7. So sánh query có/không có partition key trên **dữ liệu lab** theo policy/tài nguyên cho phép.
8. Không chỉnh production indexing policy để thử trước khi có benchmark/lệnh rollback.

Tên blade/menu của Portal có thể thay đổi, và **Data Explorer không phải lúc nào hiện mọi metric SDK**. Nếu thiếu metric, dùng SDK diagnostics hoặc Azure Monitor theo khả năng thay vì suy luận query không sử dụng index.

### Chú ý query permission

Azure control-plane **Reader** chưa chắc cho quyền thực thi query item trong Cosmos DB data plane. Cần database/container data-plane RBAC hoặc key auth theo chính sách, và network firewall/Private Endpoint phù hợp.

## 27. Một indexing policy hoàn chỉnh theo Orders API

Giả sử API cần:

- Đọc orders theo id + tenantId.
- Liệt kê orders theo createdAt.
- Lọc status và sắp xếp theo createdAt.
- Có report sắp xếp theo **status ASC, createdAt DESC**.
- Không query vào **largePayload**.

Một policy **minh họa để thảo luận**:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {
      "path": "/*"
    }
  ],
  "excludedPaths": [
    {
      "path": "/largePayload/*"
    },
    {
      "path": "/\"_etag\"/?"
    }
  ],
  "compositeIndexes": [
    [
      {
        "path": "/status",
        "order": "ascending"
      },
      {
        "path": "/createdAt",
        "order": "descending"
      }
    ]
  ],
  "spatialIndexes": []
}
~~~

### Vì sao chọn như vậy?

1. **includedPaths: /*:** ưu tiên tương thích nhiều query patterns đã biết/chưa biết.
2. **excludedPaths: /largePayload/*:** giảm indexing cho vùng dữ liệu không được filter/sort theo giả định.
3. **Composite status + createdAt:** phục vụ mẫu multi-property ORDER BY thật.
4. **Không có spatialIndexes:** Orders API không truy vấn GeoJSON.
5. **Consistent/automatic:** app vẫn dựa vào index khi query.

**Policy này không nhất thiết tối ưu nhất**: nếu 99% writes cập nhật các thuộc tính lớn mà chỉ 3 fields được query, includedPaths chọn lọc có thể rẻ hơn. Nếu API tìm theo largePayload ở một điểm khác, exclude path trên sẽ phản tác dụng. Mỗi lựa chọn phải chứng minh qua benchmark và regression tests.

### Đừng quên index cho read models khác

Một container **orders** nên tập trung vào transactional/order access patterns. Nếu dashboard cần thống kê theo ngày, vùng và SKU toàn quốc với thời gian dài, có thể tạo **projection/aggregate container** hoặc export sang analytics thay vì lấp đầy container transactional với hàng chục composite indexes.

## 28. Thay đổi indexing policy và quá trình index transformation

Thay policy không giống sửa câu query Java. Cosmos DB có thể cần xây dựng/cập nhật lại index cho **items hiện có**. Quá trình này gọi là **index transformation** và có thể kéo dài theo kích thước dữ liệu, throughput và loại thay đổi.

~~~text
Current policy: A
        |
        v
Create proposed policy B
        |
        v
Benchmark on representative lab container
        |
        v
Backup/revision + change approval
        |
        v
Update container indexing policy
        |
        v
Index transformation in progress
        |
        v
Monitor progress, RU, 429 and live queries
        |
        v
Transformation complete -> production acceptance tests
~~~

### Tại sao không sửa trực tiếp trên production?

- Reindexing có thể **tiêu tốn throughput** trong thời gian chuyển đổi.
- Query plan/khả năng index có thể khác khi transformation chưa hoàn tất.
- Thay included/excluded paths có thể làm một query cũ chậm hoặc không đáp ứng yêu cầu.
- Chi phí write RU/index storage và RU/s capacity có thể thay đổi.
- Quá trình lâu trên container lớn làm việc rollback không chỉ là bấm nút quay lại.

### Runbook đổi policy

1. Lưu **indexing policy A** và các query metrics làm baseline.
2. Xác nhận partition key, throughput model, regions và consistency.
3. Clone/mô phỏng dataset đủ đại diện vào môi trường lab.
4. Áp policy B trên lab, đợi transformation hoàn tất.
5. Benchmark top queries + writes + cross-partition reports.
6. Review chức năng bị ảnh hưởng và kế hoạch dừng/rollback.
7. Apply B vào production qua quy trình change được phê duyệt.
8. Theo dõi index transformation progress qua Portal/SDK/headers phù hợp.
9. Đánh giá p95 latency, RU, 429, index storage và application error.
10. Chỉ kết luận thành công sau khi transformation hoàn tất và có số liệu production.

### Nếu policy B làm truy vấn lỗi?

Có thể cần **khôi phục policy A** qua management plane và chờ index transformation mới theo hành vi dịch vụ, đồng thời giảm tải hoặc tạm thay query để bảo vệ hệ thống. Không hứa rollback ngay lập tức chỉ vì policy JSON được lưu trong Git.

### Khía cạnh giao dịch

Thay policy không giống xóa/đổi partition key và thường không đòi tự di chuyển data thủ công, nhưng **không phải lý do bỏ kiểm thử tính đúng đắn và vận hành**. Đặc biệt khi loại trừ paths, phải xem lại mọi query dựa vào đường dẫn đó.

## 29. Quan sát index transformation và query regression

Một bảng theo dõi trong cửa sổ thay đổi:

| Chỉ số | Trước | Trong transformation | Sau |
|---|---|---|---|
| Index transformation progress | Không áp dụng | Theo tiến độ thực tế | Hoàn tất |
| Read/query RU | Baseline | Có thể biến động | Đo lại |
| Write RU | Baseline | Có thể biến động | Đo lại |
| 429 throttling | Baseline | Theo dõi sát | Không vượt SLO |
| p95 API latency | Baseline | Cảnh báo nếu tăng | Đạt SLO |
| Index storage | Baseline | Thay đổi theo index work | Mức cuối |
| Application errors | Baseline | Theo dõi 4xx/5xx | Đạt tiêu chí |

Khi đo:

- Tách error do **Cosmos DB query** và error do **app authorization/network**.
- Phân nhóm từng query pattern, không chỉ nhìn tổng RU của account.
- Nếu throughput manual/autoscale thay đổi đồng thời, ghi lại để không kết luận sai do indexing policy.
- Theo dõi từng region và partition heat nếu ứng dụng đa region.

**Đừng tăng request rates để stress test ngay trong lúc production đang reindexing** nếu chưa có công suất và change window phù hợp.

## 30. Tối ưu truy vấn có ảnh hưởng tới write RU

Một item được ghi hoặc thay đổi phải duy trì các index entries theo policy. Với item nhiều thuộc tính/mảng, write RU có thể đáng kể.

### Ví dụ trade-off

Item JSON gồm:

~~~json
{
  "id": "order-103",
  "tenantId": "tenant-a",
  "status": "PENDING",
  "createdAt": "2026-11-20T09:00:00Z",
  "largePayload": {
    "rawImportFields": "many fields here",
    "debugContext": "large transient metadata"
  }
}
~~~

Nếu **largePayload** không dùng để query, exclude nó có thể giảm index entries/write RU/index storage. Tuy nhiên, nếu **largePayload** vẫn làm item JSON lớn, bạn vẫn phải trả chi phí lưu/đọc/ghi dữ liệu payload; exclude khỏi index **không làm biến mất payload khỏi item**.

### Khi dữ liệu rất lớn

- Tách blob/tài liệu raw lớn sang **Azure Blob Storage** với reference được bảo vệ nếu phù hợp.
- Chỉ giữ metadata searchable/transactional trong Cosmos DB.
- Dùng TTL/retention nếu dữ liệu có thể hết hạn theo chính sách.
- Cẩn trọng với Change Feed/ETL vì thay nhiều phần tử có thể phát sinh nhiều writes.

**Không chia item ra nhiều containers chỉ để giảm một vài RU** mà bỏ qua consistency, atomicity, query complexity và security. Tối ưu data model phải phản ánh access patterns và giao dịch thực.

## 31. Throughput, autoscale, 429 và hot partitions

Azure Cosmos DB có thể cung cấp throughput ở cấp **database** hoặc **container**, tùy cấu hình; có các mô hình như **manual provisioned throughput**, **autoscale** và một số hình thức serverless theo tài khoản/khả năng hỗ trợ.

### 429 Too Many Requests

HTTP 429 thường biểu thị request đang bị throttled do throughput hoặc giới hạn dịch vụ. SDK có thể retry tự động theo **Retry-After**, nhưng:

- Không tăng retries vô hạn, vì latency người dùng sẽ tăng.
- Đánh giá request volume, RU/query và RU/s capacity thực.
- Tìm **hot logical partition**, không chỉ tổng account utilization.
- Kiểm tra autoscale max throughput và burst patterns.
- Giới hạn concurrency/batch writes khi cần.

### Hot partition

~~~text
Container throughput phân phối trên physical partitions

Tenant A: 80% traffic  ---> một logical partition rất nóng
Tenant B: 10% traffic
Tenant C: 10% traffic

Kết quả:
  Tổng RU/s container có thể chưa cao nhất
  nhưng tenant A vẫn có thể bị throttled.
~~~

**Không giải quyết hoàn toàn hot partition bằng cách thêm composite index**. Bạn có thể giảm RU cho từng query, nhưng nếu một partition key value tập trung hầu hết writes/reads, cần xem lại phân vùng, caching, rate scheduling, hierarchy/synthetic partition key hoặc tách workload.

### Autoscale không phải miễn phí

Autoscale có thể điều chỉnh provisioned throughput trong khoảng cấu hình theo nhu cầu và quy tắc billing. Một query đắt làm traffic spike có thể đẩy autoscale lên mức cao hơn, tăng chi phí mà chưa cải thiện data model.

**Trước khi nâng RU/s**, tính: RU/query × QPS, phân bố theo tenant, 429, p95 latency, retry overhead và dự báo peak.

## 32. Consistency và truy vấn đa region

Cosmos DB hỗ trợ nhiều consistency levels như **Strong, Bounded Staleness, Session, Consistent Prefix, Eventual** tùy tài khoản/region settings và API. Mức consistency ảnh hưởng cách ứng dụng đọc dữ liệu và có thể ảnh hưởng latency/RU tùy topology.

### Những điều cần hiểu

- **Session consistency** thường phù hợp nhiều ứng dụng yêu cầu read-your-writes trong phạm vi session token được xử lý đúng.
- **Eventual consistency** có thể thấy dữ liệu cũ trong thời gian nhất định.
- **Strong consistency** có giới hạn/topology và trade-off theo cấu hình dịch vụ.
- Multi-region reads/writes cần xem replication, conflict resolution, network latency và availability.

**Indexing policy không quyết định consistency level**, và việc query dùng index đúng **không bảo đảm** replica vùng khác đã nhận write mới nhất.

### Session token và pagination

Nếu một user tạo order rồi lập tức query từ region khác, cần kiểm tra session behavior và SDK request context để đảm bảo trải nghiệm đúng. Không nên đơn giản quy mọi kết quả "không thấy order mới" cho lỗi indexing.

### Tránh khẳng định RPO/RTO từ index metrics

Index metrics đo query/index sử dụng. RTO/RPO là bài toán DR/replication/cutover, cần thiết kế và diễn tập riêng. Không dùng “index đã cập nhật” làm bằng chứng data replication multi-region đã hoàn tất.

## 33. Bảo mật dữ liệu và query diagnostics

Cosmos DB metrics/logs có thể mang tên container, partition values, query text, IDs hoặc thông tin ứng dụng.

Những nguyên tắc quan trọng:

1. **Không log account primary keys, connection strings hoặc Bearer tokens.**
2. Tránh log toàn bộ query params nếu chứa email, customerId, PII hoặc business secrets.
3. Giới hạn quyền Data Explorer/Query data bằng data-plane RBAC đúng scope.
4. Với Managed Identity, xác minh **Cosmos data-plane role**, không chỉ Azure resource Contributor.
5. Bật network restrictions và **Private Endpoint/Private DNS** khi kiến trúc yêu cầu.
6. Mã hóa dữ liệu theo tính năng dịch vụ và quy trình key management phù hợp.
7. Có audit/retention cho những thay đổi indexing policy, throughput và container settings.
8. Đảm bảo query luôn lọc tenant từ principal đã được authorization, không tin query string tenantId tự nhập.
9. Không dùng queries cross-tenant trong API client không có quyền quản trị.
10. Dùng synthetic data khi benchmark để tránh sao chép PII sang lab.

### Bảo vệ multi-tenant bằng application authorization

Cosmos DB NoSQL **không tự tạo SQL-style Row-Level Security giống Azure SQL Database** cho mọi query tùy ý. Một container shared-tenant thường cần kiểm soát tenant tại **app/service layer, identity, resource tokens/roles, data model và API tests**. Không suy luận việc có partition key = tenantId đã đủ để chặn client xấu nếu backend cho phép truyền tenantId bất kỳ.

### Query parameterization không thay authorization

Tham số hóa giúp query text đúng và giảm nguy cơ query injection, nhưng không xác minh user có quyền xem tenant-a. Backend phải ràng buộc tenantId với token/claims đáng tin và kiểm tra dữ liệu trước khi trả response.

## 34. Tình huống A: query liệt kê orders tốn RU sau khi số tenants tăng

**Bối cảnh:** ban đầu container có 100.000 orders và 10 tenants. Sau một năm có 20 triệu orders và 1.000 tenants. Endpoint:

~~~sql
SELECT TOP 50 c.id, c.createdAt, c.status
FROM c
WHERE c.status = "PENDING"
ORDER BY c.createdAt DESC
~~~

Không cung cấp tenantId, nên query có thể chạy trên nhiều partitions rồi hợp nhất kết quả. RU tăng theo workload/dữ liệu.

### Chẩn đoán

1. Đọc RU/query, query metrics, partitions và số items retrieved.
2. Xác định endpoint có đang phục vụ **một tenant** hay thật sự yêu cầu dữ liệu toàn hệ thống.
3. Nếu một tenant, dùng **WHERE c.tenantId=@tenantId** và SDK PartitionKey.
4. Kiểm tra range index createdAt, filter status và composite index theo benchmark.
5. Giảm response projection, dùng continuation token thay OFFSET sâu.
6. Nếu bắt buộc dashboard toàn hệ thống, cân nhắc aggregate/read model.

### Điều không nên làm

Không cấp thêm RU/s gấp 10 ngay khi query chưa biết partition key. **Cùng một functional requirement có thể thay đổi query shape/data model để rẻ hơn nhiều**, dù RU cần đo lại trên dataset thực.

## 35. Tình huống B: ORDER BY hai cột không có composite index

**Bối cảnh:** product manager yêu cầu sắp xếp theo trạng thái và ngày:

~~~sql
SELECT c.id, c.status, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.status ASC, c.createdAt DESC
~~~

Ứng dụng trước đây chỉ sắp xếp một cột; khi bật feature, query có thể báo lỗi yêu cầu composite index tương ứng hoặc không chạy theo mong muốn.

### Cách xử lý

1. Xác nhận query thật, property names/types và chiều ORDER BY.
2. Đọc indexing policy hiện tại có composite tương ứng chưa.
3. Tạo proposed composite index **status ASC, createdAt DESC** trên lab.
4. Chờ index transformation hoàn tất trước khi benchmark.
5. Test query correctness, RU, latency và write cost.
6. Triển khai **index policy trước**, rồi mới bật feature/query mới trong app.
7. Theo dõi performance sau release và giữ policy A để rollback nếu cần.

**Không bật query trong production trước khi index đã sẵn sàng** nếu thiếu index làm query không thể thực thi. Một feature flag hoặc release sequencing giúp tránh outage.

## 36. Tình huống C: Exclude largePayload giảm write RU nhưng report lỗi

**Bối cảnh:** nhóm muốn giảm chi phí ghi nên exclude đường dẫn /largePayload/*. Ứng dụng chính chỉ query status, nhưng một batch report cũ vẫn lọc theo:

~~~sql
SELECT c.id
FROM c
WHERE c.largePayload.rawImportRecord = @value
~~~

Sau thay đổi, report tốn RU hơn hoặc không còn thực hiện hiệu quả theo path index.

### Chẩn đoán và sửa

1. Kiểm tra lịch sử các query patterns thật, không chỉ API chính.
2. Xem chính sách exclude path có phù hợp report không.
3. Đo RU/query/latency/index metrics trước và sau.
4. Nếu report quan trọng, cân nhắc giữ index cho property cần thiết, dùng **lookup/read model** hoặc đưa raw data sang hệ phân tích có phù hợp.
5. Kiểm thử lại write cost để bảo đảm tổng chi phí tối ưu.
6. Nếu cần rollback policy, chuẩn bị thời gian index transformation và quy trình release.

**Một chính sách tối ưu cho write-heavy API có thể gây hại cho read-heavy reporting.** Hãy xác định sở hữu và lifecycle của mọi consumers.

## 37. Tình huống D: 429 dù tổng RU/s còn dư

**Bối cảnh:** Autoscale container chưa dùng hết max RU/s, nhưng các requests của tenant-a nhận 429, trong khi tenant-b/c vẫn hoạt động.

### Giả thuyết

- Tenant-a tạo **hot logical partition**.
- Một physical partition bị giới hạn cục bộ.
- Query đắt hoặc nhiều writes cùng lúc dồn vào một partition key value.
- Retries đồng thời làm tải thêm.

### Runbook

1. Kiểm tra 429 theo tenant/partition key và SDK diagnostics an toàn.
2. Tính RU/request, QPS của tenant-a và độ phân bố traffic.
3. Xem query có point read hay cross-partition không.
4. Giảm RU/query bằng projection/index/query shape.
5. Giới hạn concurrency/backpressure và retry có jitter.
6. Nếu key skew kéo dài, đánh giá **partitioning redesign**, synthetic/hierarchical keys hoặc tách tenant lớn sang container riêng.
7. Kiểm tra migration/cutover không ảnh hưởng consistency/transaction boundaries.

**Không giả định autoscale sẽ tự chia một logical partition nóng thành vô hạn throughput**. Partition key choice là quyết định data model, cần thiết kế từ đầu.

## 38. Tình huống E: dashboard COUNT toàn account quá đắt

**Bối cảnh:** dashboard quản trị cập nhật mỗi 5 giây:

~~~sql
SELECT VALUE COUNT(1)
FROM c
WHERE c.status = "CONFIRMED"
~~~

Query không lọc tenant/region, chạy qua toàn container, mỗi lần trả một số nhưng vẫn tốn RU.

### Phương án

- Giảm refresh interval theo nhu cầu thực.
- Nếu chỉ cần số liệu tenant, truyền partition key.
- Duy trì **daily/status aggregate documents** bằng change feed processing.
- Đưa analytics dài hạn sang hệ phân tích khi phù hợp.
- Dùng cache có TTL và mô tả độ trễ.
- Quan sát cost của reads và writes phát sinh bởi aggregate pipeline.

**Trả về một số đếm không có nghĩa chi phí xử lý là một RU**. Nếu cần thống kê kế toán/tài chính, đảm bảo reconciliation và chính sách correction thay vì chỉ cộng dồn events không idempotent.

## 39. Bài thực hành: tối ưu Orders API trong Cosmos DB lab

### Mục tiêu

Thiết kế và đánh giá indexing policy cho container **orders** với partition key **/tenantId**, chỉ sử dụng **Cosmos DB account/container lab đã được phép dùng**. Nếu chưa có subscription, bạn vẫn có thể hoàn thành phần thiết kế và phân tích chi phí giả định mà không tạo tài nguyên thật.

### Bối cảnh

Ứng dụng có:

- 10 tenants giả lập với các mức lưu lượng khác nhau.
- Orders từ vài tháng, gồm status, createdAt, totalAmount và items[].
- Một nhóm item có **largePayload** không bao giờ tìm kiếm trong API.
- Ba endpoints: **GET /orders/{id}**, **GET /orders?status=...**, **GET /orders/recent**.
- Một dashboard đếm orders theo status, refresh mỗi phút.

### Phần A: dựng access pattern matrix

| Truy cập | Parameter/input | Cosmos operation | Cần index gì? |
|---|---|---|---|
| Đọc đúng order | id + tenantId | Point read | Không đòi SQL query index tùy biến |
| Orders theo trạng thái | tenantId + status | Query có PartitionKey | Range path status |
| Orders mới nhất | tenantId + createdAt | Query + ORDER BY createdAt | Range path createdAt |
| Sort status rồi ngày | tenantId + status/date | Multi-property ORDER BY | Composite phù hợp |
| Count theo tenant/status | tenantId + status | Aggregate query | Query metrics đánh giá |
| Search SKU | tenantId + sku | EXISTS/JOIN trên items[] | Array path phù hợp |
| Report tổng hợp toàn account | status/date | Có thể cross-partition | Cân nhắc read model/analytics |

### Phần B: chuẩn bị dữ liệu giả

Trong container lab đúng partition key, tạo nhiều orders giống ví dụ:

~~~json
{
  "id": "order-lab-0001",
  "tenantId": "tenant-lab-a",
  "status": "PENDING",
  "createdAt": "2026-11-20T08:00:00Z",
  "customerId": "customer-lab-001",
  "totalAmount": 50000,
  "items": [
    {"sku": "SKU-LAB-01", "quantity": 1}
  ],
  "largePayload": {
    "rawImportRecord": "synthetic test data"
  }
}
~~~

**Không tạo hàng triệu items để học nếu không có budget và capacity plan.** Bắt đầu với tập nhỏ, sau đó chỉ tăng kích thước khi bài lab được cấp đủ tài nguyên và có phương án cleanup.

### Phần C: chạy baseline queries

1. Point read bằng **id + partition key**.
2. Query **WHERE tenantId/status**, chỉ trả id/status.
3. Query **ORDER BY createdAt DESC** trong tenant.
4. Query **ORDER BY status ASC, createdAt DESC**.
5. Query COUNT theo status trong tenant.
6. Query số liệu toàn container chỉ khi được phép.

Đối với mỗi query, ghi **RU/page**, p50/p95 latency khi có đủ samples, output count và index/query metrics nếu có.

### Phần D: đưa ra policy B

Chọn một trong hai hướng:

**Hướng 1 — giữ wildcard include, exclude largePayload và thêm composite index**:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [
    {"path": "/largePayload/*"},
    {"path": "/\"_etag\"/?"}
  ],
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ],
  "spatialIndexes": []
}
~~~

**Hướng 2 — chỉ index paths phục vụ các queries chính**, nếu học viên có đủ bộ regression tests cho những truy vấn khác:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/tenantId/?"},
    {"path": "/status/?"},
    {"path": "/createdAt/?"},
    {"path": "/items/[]/sku/?"}
  ],
  "excludedPaths": [{"path": "/*"}],
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ]
}
~~~

**Chỉ áp dụng trên container lab** và xác minh schema/path syntax của API for NoSQL. Hai policies không mặc định có cùng kết quả với mọi query. Trước khi so sánh, chờ index transformation hoàn tất.

### Phần E: benchmark lại

| Mục | Policy A | Policy B | Đạt? |
|---|---|---|---|
| Point read RU | Ghi số đo | Ghi số đo | Đánh giá |
| Query tenant + status RU | Ghi số đo | Ghi số đo | Đánh giá |
| Multi ORDER BY hoạt động | Có/không | Có/không | Đúng chức năng |
| Write RU/item | Ghi số đo | Ghi số đo | Không vượt ngân sách |
| Index storage | Ghi số đo | Ghi số đo | Theo kỳ vọng |
| 429 trong peak lab | Ghi số đo | Ghi số đo | Không gây outage |
| API p95 latency | Ghi số đo | Ghi số đo | Đạt SLO lab |

Nếu policy B tiết kiệm 5 RU/query nhưng tăng 3 RU/write, hãy tính theo tần suất thực:

~~~text
Giả định:
  100 queries/giây x tiết kiệm 5 RU = tiết kiệm 500 RU/giây
  200 writes/giây x tăng 3 RU      = tốn thêm 600 RU/giây

Chênh lệch thuần ước tính:
  500 - 600 = -100 RU/giây
~~~

Kết quả minh họa cho thấy policy B **chưa chắc tiết kiệm** nếu write volume cao; chưa kể latency, storage và 429. Dùng dữ liệu thật của workload để quyết định.

### Phần F: chuẩn bị production change runbook

Viết một trang gồm:

1. Thời gian triển khai, owner và người phê duyệt.
2. Policy A/B lưu version và khác biệt.
3. Danh sách queries/consumers chịu ảnh hưởng.
4. Thời gian dự trù index transformation và cách theo dõi tiến độ.
5. Thông số RU/latency/429 trước thay đổi.
6. Tiêu chí stop/rollback và fallback API khi queries tăng lỗi.
7. Dự toán chi phí reindexing/throughput tạm thời nếu cần.
8. Kiểm tra sau khi index hoàn tất và khoảng giám sát tiếp theo.

Không thay đổi indexing policy production trong bài lab nếu chưa được Prime/chủ tài nguyên phê duyệt riêng. Chỉ viết **bài học và hướng dẫn**, không tạo/sửa Cosmos DB resources thực.

## 40. Checklist trước khi đưa index policy vào production

- [ ] Đã xác nhận account thực sự là **Azure Cosmos DB for NoSQL**.
- [ ] Có access pattern matrix từ APIs, reports, batch jobs và management queries.
- [ ] Đã chọn partition key theo phân bố dữ liệu/thông lượng và query routing.
- [ ] Phân biệt point read id+PK với SQL query tìm một item.
- [ ] Có baseline RU, p95 latency, output count, 429 và query metrics.
- [ ] Các paths quan trọng dùng đúng tên thuộc tính, type và chữ hoa/thường.
- [ ] Included/excluded paths có lý do rõ; không exclude field vẫn được query.
- [ ] Multi-property ORDER BY có composite index cần thiết.
- [ ] Spatial index chỉ có khi có GeoJSON/spatial query cần thiết.
- [ ] Các queries dùng partition key khi có thể; admin cross-partition queries được quản trị riêng.
- [ ] Projection giới hạn field; tránh SELECT * với payload lớn không cần thiết.
- [ ] Phân trang bằng continuation token khi phù hợp; tránh OFFSET sâu.
- [ ] Aggregations lớn được đo RU và cân nhắc read model/change feed.
- [ ] Java SDK sử dụng query parameters, managed identity và client pooling.
- [ ] Không đưa Cosmos keys, secrets, PII vào source hoặc query diagnostics.
- [ ] Policy mới đã được áp vào lab và **index transformation hoàn tất** trước benchmark.
- [ ] Đã đo read/write RU, index storage, query latency và peak 429.
- [ ] Có cách phát hiện hot partitions và kế hoạch giảm skew.
- [ ] Autoscale/manual throughput được sizing theo thực tế, không dùng để che query anti-pattern.
- [ ] Multi-region consistency/session behavior được kiểm tra cho use case.
- [ ] Có change approval, bản policy cũ và rollback plan tính cả thời gian reindex.
- [ ] Có dashboard/alerts theo tenant, container, region và request types khi được hỗ trợ.
- [ ] Có ngân sách, tags/owner và cleanup policy cho các bản sao lab.

## 41. Câu hỏi tự kiểm tra

1. Index policy trong Cosmos DB được thiết lập ở account hay container level?
2. Azure Cosmos DB for NoSQL khác Azure SQL Database ở query language/indexing như thế nào?
3. RU khác RU/s ở điểm nào?
4. Vì sao point read cần id và partition key?
5. Khi nào query có thể chạy cross-partition?
6. Tại sao cross-partition query trả 10 items vẫn có thể tốn RU cao?
7. IndexingMode consistent khác none như thế nào?
8. Automatic indexing có tự tạo mọi composite index không?
9. includedPaths /* và excludedPaths /largePayload/* tác động ra sao?
10. Dùng /status/? khác /items/[]/sku/? ở cấu trúc JSON như thế nào?
11. Composite index cần thiết khi nào với ORDER BY nhiều properties?
12. Thứ tự và chiều ASC/DESC của composite index có quan trọng không?
13. Khi nào dùng spatial index và GeoJSON?
14. Index theo nhiều paths làm write RU/index storage thay đổi thế nào?
15. Vì sao không nên tắt index trên container production chỉ để giảm write RU?
16. Partition key xấu có thể được chữa hoàn toàn bằng composite index không?
17. Nếu có 50 AKS pods đồng thời query Cosmos DB, cần đo những chỉ số gì?
18. SELECT * gây ảnh hưởng gì với item có largePayload?
19. Tại sao OFFSET 10000 LIMIT 20 thường không phù hợp pagination sâu?
20. Continuation token có bảo đảm snapshot bất biến không?
21. COUNT trên hàng triệu items có mặc định O(1) không?
22. JOIN trong API for NoSQL khác SQL relational JOIN ở điểm nào?
23. Khi nào cân nhắc read model/aggregate container?
24. Java SDK cần cấu hình partition key và SQL parameters thế nào?
25. Vì sao phải cộng RU qua **mọi pages** thay vì chỉ đọc page đầu?
26. Query metrics/index metrics giúp gì ngoài nhìn latency?
27. Vì sao benchmark policy mới phải chờ index transformation hoàn tất?
28. Lợi ích của exclude largePayload có bị giảm nếu raw JSON vẫn rất lớn không?
29. Hot partition gây 429 như thế nào dù tổng RU/s còn dư?
30. Autoscale có tự sửa lỗi partition key skew không?
31. Consistency level ảnh hưởng khả năng thấy writes mới từ region khác ra sao?
32. Vì sao tenantId phải được ràng buộc với principal đã xác thực?
33. Khi nào nên chọn API for NoSQL indexes thay vì công cụ full-text/vector search riêng?
34. Nếu query RU giảm nhưng write RU tăng mạnh, quyết định policy theo tiêu chí nào?

## 42. Tài liệu tham khảo

- [Azure Cosmos DB indexing overview](https://learn.microsoft.com/azure/cosmos-db/index-overview) — kiến trúc/indexing fundamentals cho API for NoSQL.
- [Indexing policies in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/index-policy) — JSON policy, paths, composite/spatial indexes.
- [Composite indexes for Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/index-policy#composite-indexes) — các mẫu truy vấn cần index nhiều properties.
- [Optimize query cost in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/optimize-cost-reads-writes) — RU, queries và chiến lược tối ưu.
- [Optimize query cost with indexing and query metrics](https://learn.microsoft.com/azure/cosmos-db/optimize-cost-reads-writes#optimizing-queries) — đo query/query plan và chi phí.
- [Partitioning and horizontal scaling](https://learn.microsoft.com/azure/cosmos-db/partitioning-overview) — logical/physical partitions và partition key.
- [Request Units in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/request-units) — RU/RU/s và mô hình chi phí.
- [Azure Cosmos DB for NoSQL SQL query language](https://learn.microsoft.com/azure/cosmos-db/nosql/query/) — SELECT, WHERE, ORDER BY và functions.
- [Pagination in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/query/pagination) — continuation tokens, page size.
- [Index metrics for Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/index-metrics) — kiểm tra hiệu quả index.
- [Azure Cosmos DB Java SDK v4](https://learn.microsoft.com/azure/cosmos-db/nosql/quickstart-java) — Java client, point reads và queries.
- [Microsoft Entra RBAC for Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access) — data-plane identity và scope.
- [Autoscale provisioned throughput](https://learn.microsoft.com/azure/cosmos-db/provision-throughput-autoscale) — throughput khi lưu lượng biến động.
- [Monitor Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/monitor) — metrics, diagnostics và alerts.
- [Azure Cosmos DB pricing](https://azure.microsoft.com/pricing/details/cosmos-db/autoscale-provisioned/) — mô hình tính giá; cần chọn region/tier hiện hành.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước lượng chi phí môi trường lab và production.

**Kết luận:** Tối ưu truy vấn Cosmos DB không chỉ là bật hoặc tắt một chỉ mục. Hãy bắt đầu từ **access patterns và partition key**, ưu tiên **point reads**, giới hạn phạm vi query, chọn projection/pagination phù hợp và tạo **composite/spatial indexes khi có nhu cầu thực**. Mọi thay đổi indexing policy cần đo **RU, latency, retrieved/output items, write overhead, index storage và 429** trên dataset đại diện, đồng thời theo dõi index transformation đến khi hoàn tất. Khi đo đạc trước, triển khai có kiểm soát và thiết kế đúng dữ liệu/mạng/quyền, bạn mới tối ưu được cả hiệu năng, độ tin cậy và chi phí của ứng dụng Azure.
