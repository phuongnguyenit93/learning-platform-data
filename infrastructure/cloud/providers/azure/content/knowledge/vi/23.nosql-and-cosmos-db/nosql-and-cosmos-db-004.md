# Request Unit, provisioned throughput, autoscale và serverless

Một ứng dụng thương mại điện tử lưu đơn hàng, giỏ hàng và lịch sử hoạt động vào **Azure Cosmos DB for NoSQL**. Ban ngày có vài trăm yêu cầu mỗi giây, khi khuyến mãi lượng truy cập tăng gấp mười, còn ban đêm gần như không có người dùng. Nếu nhóm chỉ biết số request HTTP mà không biết **mỗi thao tác tiêu thụ bao nhiêu Request Unit (RU)**, chi phí và khả năng chịu tải sẽ rất khó dự đoán. Cùng 1.000 request, việc đọc một document bằng `id` và partition key có thể rất khác truy vấn `ORDER BY` trên nhiều partition.

Azure Cosmos DB cho phép quản lý năng lực xử lý theo nhiều mô hình: **provisioned throughput cố định (manual)**, **autoscale provisioned throughput** và **serverless**. Chọn sai mô hình có thể dẫn tới cấp phát quá nhiều RU/s cho giờ thấp điểm, bị HTTP 429 khi traffic tăng hoặc trả phí theo từng request trong workload ổn định mà đáng lẽ nên mua công suất dành trước.

Bài học thuộc chương **Dữ liệu NoSQL với Cosmos DB** trong module **CLOUD_PROVIDERS_AZURE**, kết nối các kiến thức Azure subscription/resource group, Entra ID, networking, ứng dụng Java, dữ liệu, monitoring, security và cost management. Trọng tâm là hiểu, đo, tính toán và chọn đúng throughput model cho **Azure Cosmos DB for NoSQL**; không áp dụng máy móc mọi ví dụ sang API for MongoDB, Cassandra hoặc Gremlin vì giao diện, quota và cách kiểm tra có thể khác.

> **Lưu ý:** giá, quota, giới hạn tối thiểu RU/s, mô hình autoscale động, hỗ trợ region, account capabilities và cách thay đổi billing mode được Azure cập nhật theo thời điểm. Các phép tính là mô hình tư duy và ví dụ thực hành, **không phải báo giá, SLA hoặc cam kết throughput thực tế**. Trước khi triển khai production, kiểm tra khả năng của đúng account/API/region và mức giá trong Azure Pricing Calculator/Portal.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Request Unit (RU)** và **RU/s** khác nhau ra sao, điều gì quyết định `request charge`.
2. Phân biệt mức tính phí/tài nguyên của **manual provisioned throughput**, **autoscale** và **serverless**.
3. Hiểu mối liên hệ giữa **database, container, logical partition, physical partition** và throughput.
4. Ước lượng RU/s từ số thao tác, RU/op, thời điểm cao điểm và vùng địa lý.
5. Đo RU thực tế bằng Azure SDK for Java, response headers và Azure Monitor.
6. Thiết kế partition key để tránh **hot partition**, cùng giới hạn đọc/ghi, indexing và cross-partition queries.
7. Giải thích lỗi **HTTP 429 Too Many Requests**, retry-after, retry/backoff và các tác động đến latency.
8. Thiết kế consistency, indexing, TTL, bulk operations và data model phù hợp ngân sách RU.
9. Tính ví dụ chi phí theo manual/autoscale/serverless mà không nhầm **RU với RU/s**.
10. Lập kế hoạch benchmark, monitoring, autoscale alert, capacity và kiểm soát chi phí trước production.

## 2. Bức tranh tổng thể của Azure Cosmos DB

**Azure Cosmos DB** là dịch vụ cơ sở dữ liệu phân tán được quản lý. Với **API for NoSQL**, dữ liệu thường được lưu dưới dạng JSON items trong containers, được truy cập qua SDK/query API. Đơn vị tổ chức khái quát:

~~~text
Azure subscription
└── Resource group
    └── Azure Cosmos DB account (API for NoSQL)
        ├── Database: commerce
        │   ├── Container: orders      (partition key: /tenantId)
        │   ├── Container: carts       (partition key: /tenantId)
        │   └── Container: events      (partition key: /tenantId)
        └── Regions / consistency / network / identity
~~~

Các tài nguyên nằm trong account chịu ảnh hưởng của account settings, API type, region availability và mô hình capacity được chọn. **Database** và **container** có thể có cấu hình throughput riêng hoặc dùng throughput được chia sẻ trong những kiểu triển khai được hỗ trợ.

### Các cấp không được đánh đồng

| Cấp | Vai trò | Liên quan throughput |
|---|---|---|
| Account | Endpoint, regions, consistency, identity/network, capability | Chọn capability/billing mode, phân bố vùng |
| Database | Gom nhiều containers | Có thể cấu hình shared provisioned throughput khi hỗ trợ |
| Container | Chứa items và định nghĩa partition key/indexing | Có thể có throughput riêng hoặc dùng shared |
| Logical partition | Tập items có cùng giá trị partition key | Có giới hạn dung lượng và khả năng phân phối |
| Physical partition | Đơn vị hạ tầng phân bố lưu trữ/thông lượng | Có giới hạn và tỷ lệ throughput được phân bổ |
| Item | JSON document | Read/write/query tiêu thụ RU theo công việc |

Chọn throughput bao nhiêu RU/s không tự sửa được một **partition key phân bố kém**. Nếu mọi đơn hàng có partition key `"global"`, tải có thể tập trung ở một logical partition, gây nghẽn dù toàn container còn throughput.

## 3. Request Unit (RU) là gì?

**RU (Request Unit)** là đơn vị chuẩn hóa chi phí tài nguyên của một request trong Azure Cosmos DB, phản ánh công việc xử lý như CPU, bộ nhớ và I/O ở mức dịch vụ. RU giúp so sánh những thao tác dữ liệu khác nhau mà không buộc người phát triển trực tiếp cấu hình tài nguyên vật lý.

Những thao tác tiêu thụ RU gồm:

- Point read một item theo `id` **và partition key**.
- Tạo/upsert/replace/delete item.
- Query SQL-like qua một hoặc nhiều partitions.
- Đọc trang tiếp theo của query.
- Stored procedure/transactional batch hoặc bulk operations theo khả năng API.
- Những hoạt động nền như indexing/TTL deletion có thể ảnh hưởng tổng tài nguyên và cách tính charge theo cơ chế sản phẩm.

### RU khác RU/s

- **RU:** số đơn vị một request tiêu thụ, ví dụ point read tốn 1,2 RU hoặc một query tốn 45 RU.
- **RU/s:** ngân sách xử lý cấp phát **mỗi giây** cho throughput model, ví dụ 1.000 RU/s.
- **Consumed RU:** tổng RU từ nhiều requests trong một khoảng thời gian, ví dụ 720.000 RU trong giờ.
- **Provisioned RU/s:** công suất được dành sẵn và tính phí theo thời gian trong manual/autoscale, khác tổng RU thực tế đã dùng.

~~~text
1 operation:                      5 RU
200 operations trong một giây:    200 × 5 = 1.000 RU
Nhu cầu tại giây đó:              ~1.000 RU/s
~~~

Ví dụ trên giả định tất cả requests cùng chi phí 5 RU, phân bố đều theo các physical partitions, không có thêm overhead hoặc spike. Trong thực tế phải cộng headroom, peak skew, retries, query variation và bảo đảm partition distribution.

### Mốc tham chiếu 1 RU

Trong một cấu hình và điều kiện thường được dùng để giải thích, **point read của document JSON kích thước khoảng 1 KiB** có chi phí khoảng **1 RU**. Đây là **mốc tham chiếu**, không phải cam kết mọi point read/consistency level đều luôn là 1 RU. Item lớn hơn, consistency mạnh hơn hoặc cách truy cập khác có thể thay đổi chi phí.

**Không suy rằng 1 RU = một request.** Một request query nhiều partitions có thể tiêu thụ hàng chục, hàng trăm hoặc nhiều RU hơn; một request đọc nhỏ có thể xấp xỉ 1 RU.

## 4. Các yếu tố ảnh hưởng request charge

| Yếu tố | Tác động phổ biến | Cách tối ưu |
|---|---|---|
| Item size | Item lớn thường tốn RU hơn khi read/write | Chỉ lưu field cần, tách blob lớn |
| Point read vs query | Point read thường rẻ hơn query tìm cùng item | Dùng `id` + partition key khi đã biết |
| Number of returned items | Đọc nhiều documents cần thêm RU | Pagination, projection, giới hạn kết quả |
| Cross-partition query | Fan-out trên nhiều partitions có thể tăng RU/latency | Query theo partition key khi hợp lý |
| Indexing policy | Index cập nhật khi ghi có chi phí RU; query có thể được lợi | Chỉ index các paths cần query |
| Query complexity | `ORDER BY`, aggregate, filters hoặc joins có thể tăng công | Query plan/index, thiết kế model |
| Consistency | Một số consistency choices có chi phí đọc khác nhau | Chọn theo nghiệp vụ thay vì luôn mạnh nhất |
| Regions và replication | Throughput provisioned/ghi nhân bản ảnh hưởng tổng chi phí | Đo nhu cầu và thiết kế regional footprint |
| Hot partition | Một key chịu phần lớn traffic | Thiết kế key phân tán trước khi scale |
| Retry/429 | Extra attempts và latency khiến tải thực thay đổi | Retry policy, giới hạn concurrency, tối ưu RU/op |

Cùng một truy vấn có thể có charge thay đổi khi số items, indexing policy hoặc query plan thay đổi. Vì thế cần **benchmark trên dữ liệu và hình dạng workload gần production** thay vì dùng một con số RU/op lấy từ một item thử nghiệm nhỏ.

## 5. Quan sát RU trong response

Dịch vụ cung cấp thông tin **request charge** trong response metadata. Với HTTP protocol, một header thường thấy là:

~~~http
x-ms-request-charge: 3.14
~~~

Giá trị minh họa `3.14` là **RU tiêu thụ cho request đó**, không phải RU/s được cấp phát. Với SDK, có phương thức truy xuất charge mà không cần tự parse header.

Các thông tin nên ghi nhận ở **client/service instrumentation**:

- Operation type, container, route hoặc tên use case.
- Request charge RU và thời lượng operation.
- Partition key category (không log PII/raw key nếu vi phạm chính sách).
- HTTP status/substatus, retry count và retry-after khi lỗi.
- Query identifier hoặc normalized query text đã loại dữ liệu nhạy cảm.
- Region contacted, SDK diagnostics (được lọc và giới hạn truy cập).
- Số trang query và tổng RU theo operation nghiệp vụ.

**Tránh dùng một request charge đơn lẻ như số đo chi phí của cả pipeline** nếu SDK thực hiện nhiều requests/pages, prefetch hoặc retry. Đối với paginated query, cần cộng charge của những trang được đọc.

## 6. Ba mô hình tính năng lực: manual, autoscale, serverless

| Tiêu chí | Manual provisioned throughput | Autoscale provisioned throughput | Serverless |
|---|---|---|---|
| Cấp throughput | Cấu hình RU/s cố định | Cấu hình **maximum RU/s**, hệ thống scale trong khoảng hỗ trợ | Không provision RU/s trước |
| Chi phí throughput | Dựa trên RU/s đã provision theo thời gian | Dựa trên RU/s được autoscale provision theo các chu kỳ tính phí, có ngưỡng sàn | Dựa trên RU requests thực tiêu thụ |
| Khi không có requests | Vẫn trả phí công suất được cấp | Vẫn có chi phí tối thiểu cho công suất autoscale | Không có phí provision RU/s liên tục; storage và tài nguyên khác vẫn có thể tính phí |
| Traffic ổn định | Thường dễ tối ưu bằng manual | Có thể dư tính linh hoạt | Có thể kém kinh tế tùy RU volume |
| Traffic biến động | Dễ 429 nếu peak vượt RU/s | Scale theo tải trong giới hạn maximum | Trả phí per RU nhưng vẫn có giới hạn capacity |
| Cần quyết định | RU/s mục tiêu và partitioning | Maximum RU/s, mức tối thiểu/peak và chi phí theo giờ | Peak cần chịu, quota, chi phí RU consumption |
| Phân phối qua partitions | Có | Có | Dịch vụ quản lý, nhưng partition design vẫn quan trọng |
| Hỗ trợ database-shared throughput | Có trong mô hình phù hợp | Có trong mô hình phù hợp | Không hiểu như mua shared provisioned RU/s |
| Khả năng nâng/đổi mode | Theo thao tác và giới hạn account/container | Theo thao tác và giới hạn được hỗ trợ | Account capability/migration có ràng buộc riêng |

**Autoscale và serverless không phải một tính năng.** Autoscale là **provisioned capacity tự điều chỉnh** trong giới hạn; serverless là **thanh toán theo RU đã sử dụng**, không đặt một RU/s dành trước.

## 7. Manual provisioned throughput

Với **manual provisioned throughput**, bạn chọn một mức RU/s tại container hoặc database shared throughput theo khả năng của loại tài nguyên. Ví dụ:

~~~text
Container orders được provision: 2.000 RU/s

00:00-06:00:  traffic chỉ dùng ~100 RU/s
12:00-14:00:  traffic dùng ~1.200 RU/s
20:00-21:00:  peak ~2.400 RU/s
~~~

Ở giờ thấp điểm, phần RU/s không dùng **không phải tự động được hoàn tiền**. Tại đỉnh 2.400 RU/s, nếu nhu cầu tập trung và vượt mức capacity có thể phục vụ, một số requests có thể gặp 429/độ trễ retry. Điều này cũng phụ thuộc **partition distribution** chứ không chỉ tổng RU/s toàn container.

### Ưu điểm

- Dễ ước lượng chi phí provisioned throughput theo cấu hình và thời gian.
- Phù hợp tải ổn định, ít dao động.
- Có thể là lựa chọn đơn giản với pipeline hoạt động liên tục và đủ utilization.
- Có thể điều chỉnh thủ công theo lịch/công cụ nếu workload và tính năng cho phép.

### Nhược điểm

- Dư RU/s ở giờ thấp điểm vẫn bị tính phí.
- Cần dự báo peak và chủ động nâng throughput.
- Nếu chậm thay đổi cấu hình, spike có thể gây throttling.
- Dữ liệu/partition hot vẫn tạo 429 dù tổng throughput còn dư.

### Chọn RU/s thủ công

Giả sử một API có:

- 400 point reads/s × 1,5 RU/read = 600 RU/s.
- 80 writes/s × 7 RU/write = 560 RU/s.
- 10 queries/s × 18 RU/query = 180 RU/s.

Tổng nhu cầu trung bình trong giây được đo: **1.340 RU/s**. Nếu cần headroom 30% theo chính sách thử nghiệm: **1.742 RU/s**. Có thể đánh giá cấu hình **2.000 RU/s**, miễn đạt giới hạn tối thiểu/mức tăng cho container, partition distribution và latency SLO.

Đây là tính toán **mức tải đỉnh giả định và RU/op đã đo**, không phải công thức tự động đảm bảo container 2.000 RU/s luôn phục vụ 1.340 RU/s khi một logical partition quá nóng.

## 8. Autoscale provisioned throughput

Với **autoscale**, người vận hành khai báo một **maximum throughput** `Tmax` tính bằng RU/s. Azure Cosmos DB tự tăng/giảm lượng RU/s được cung cấp trong khoảng được hỗ trợ để đáp ứng nhu cầu.

Trong mô hình autoscale thông thường, dải công suất được mô tả từ **một tỷ lệ tối thiểu của `Tmax` (thường khoảng 10%)** đến `Tmax`; sản phẩm có các biến thể **dynamic autoscale** và tính năng điều chỉnh theo partition/region với hành vi tính phí khác nhau. Cần dùng thông tin hiện hành của account để xác nhận giới hạn và billing chính xác.

~~~text
Autoscale max throughput: 4.000 RU/s

Tải thấp       -> dịch vụ giảm công suất trong dải hỗ trợ
Tải vừa        -> dịch vụ tăng công suất theo nhu cầu
Tải tăng mạnh  -> lên tối đa 4.000 RU/s
Tải > 4.000    -> vẫn có thể 429 hoặc latency tăng
~~~

### Ý nghĩa quan trọng của Tmax

`Tmax` **không phải RU đã sử dụng**. Nó là **trần RU/s** được cung cấp theo chế độ autoscale. Nếu workload cần 7.000 RU/s mà Tmax chỉ 4.000 RU/s, autoscale không tự cấp lên 7.000 khi chưa nâng mức tối đa theo giới hạn cho phép.

### Cách tính phí tư duy

Ở các cấu hình autoscale thông thường, phí provisioned throughput theo giờ được xác định dựa trên mức RU/s cao nhất hệ thống cấp trong khoảng thời gian tính phí, với sàn tối thiểu liên quan Tmax. Ví dụ lý thuyết:

~~~text
Tmax:                      4.000 RU/s
Mức thấp minh họa:           400 RU/s
Một giờ có đỉnh 2.400 RU/s -> phí giờ dựa trên công suất autoscale ghi nhận
Một giờ không có tải       -> vẫn có sàn công suất được tính phí
~~~

Ví dụ không cố định mức giá hoặc quy tắc làm tròn. Với **dynamic autoscale**, cách xem cấp phát/billing theo partition/region và điều kiện sử dụng có thể khác autoscale cổ điển; cần kiểm tra metric thực tế và model billing hiện hành.

### Khi nào nên dùng autoscale?

- Peak biến động theo giờ/ngày nhưng vẫn cần throughput dự trù.
- Batch jobs theo lịch khiến traffic tăng ngắn hạn.
- Có mùa vụ/khuyến mãi và dự báo peak `Tmax` phù hợp.
- Cần khả năng scale mà không can thiệp tay ở mỗi spike.
- Đội vận hành muốn giữ provisioned model cho nhiều regions hoặc nhu cầu năng lực cao.

### Autoscale không thay partition key

Giả sử một `tenantId` tạo ra 90% requests. Nếu physical partition chứa tenant đó bị nghẽn, tăng `Tmax` không nhất thiết giúp tương xứng vì phân phối throughput theo physical partitions và giới hạn per-partition. Cần quan sát **normalized RU consumption theo partition** và xem lại data model.

## 9. Serverless: trả phí theo RU tiêu thụ

**Serverless** không yêu cầu khai báo một lượng RU/s dành trước. Người dùng trả phí theo **tổng RU operations thực tế** và chi phí lưu trữ/các tài nguyên liên quan theo biểu giá đang áp dụng. Mô hình phù hợp với:

- Ứng dụng phát triển/prototype có workload ít hoặc không đều.
- API nội bộ chỉ chạy theo những sự kiện hiếm.
- Thử nghiệm tính năng, tài liệu demo hoặc pipeline theo đợt ít yêu cầu.
- Môi trường có những khoảng nhàn rỗi dài và không cần đặt trước một công suất ổn định cao.

### Ví dụ

~~~text
Một ngày:
  10.000 point reads × 1 RU         = 10.000 RU
  1.000 writes × 8 RU               =  8.000 RU
  100 query pages × 40 RU           =  4.000 RU
Tổng ngày                            = 22.000 RU
~~~

Trong serverless, bạn ước tính **chi phí request dựa trên tổng RU tính phí**, không nhân `Tmax RU/s × thời gian` như provisioned model. Vẫn có chi phí storage, mạng/backup và các dịch vụ ứng dụng liên quan.

### Không có nghĩa scale vô hạn

Serverless vẫn có **giới hạn throughput/requests, storage/partition, vùng và tài khoản**, nên có thể gặp 429 nếu gửi burst vượt khả năng được hỗ trợ. Nếu thiết kế yêu cầu 100.000 RU/s ổn định, cần đánh giá provisioned throughput và account architecture thay vì mặc định serverless tự mở rộng không giới hạn.

### Quyết định account capability từ đầu

Serverless là **một loại cấu hình/account capability** có quy tắc tạo account và các ràng buộc về nâng cấp/chuyển đổi. Không mặc định một account serverless đang chạy có thể chuyển ngay sang manual/autoscale trong cùng account bằng một lệnh đơn giản, hoặc ngược lại. Nếu cấu hình hiện tại không hỗ trợ chuyển trực tiếp, cần **tạo account mới, di chuyển dữ liệu, đổi endpoint và kiểm thử** theo kế hoạch.

### Khi serverless có thể kém kinh tế

Workload chạy 24/7 với RU consumption cao có thể có tổng phí theo RU lớn hơn provisioned throughput được sử dụng hiệu quả. Vì vậy hãy **đo cost per business operation** và so sánh thực tế, không chỉ nhìn từ "không trả phí khi idle".

## 10. Bảng quyết định dựa trên workload

| Workload | Đặc điểm | Phương án đầu tiên nên đánh giá | Vì sao |
|---|---|---|---|
| Production API ổn định cả ngày | Tải đều, RU/op đo được | Manual provisioned | Tận dụng capacity cố định |
| API tăng mạnh theo chiến dịch | Peak cao, giờ thấp điểm giảm | Autoscale | Giảm nhu cầu thay RU/s thủ công |
| Test environment ít truy cập | Phần lớn thời gian nhàn rỗi | Serverless | Không mua provisioned RU/s liên tục |
| Batch import một giờ/ngày | Spike lớn ngắn hạn | Autoscale hoặc manual theo lịch | Cần tính giá/capacity giờ cao điểm |
| Event-driven nhỏ, sporadic | Số operations thấp | Serverless | Trả phí theo RU tiêu thụ |
| Hệ thống toàn cầu traffic cao | Multi-region, SLA nghiêm ngặt | Provisioned/manual hoặc autoscale theo khả năng | Kiểm soát throughput, replication, region capacity |
| Multi-tenant lệch tải | Một vài tenant cực nóng | **Sửa partitioning trước** rồi chọn model | Billing mode không trị được hot key |
| Kết hợp analytics và OLTP | Query fan-out làm ảnh hưởng point reads | Xem lại data/query architecture | Tối ưu RU và cô lập workload |

Đây là lựa chọn **để bắt đầu PoC**, không phải đáp án cố định cho mọi dự án. Một workload serverless ít hoạt động nhưng yêu cầu multi-region đặc biệt có thể bị hạn chế bởi account capabilities; một workload autoscale vẫn có thể 429 vì hot partition.

## 11. Chọn throughput tại database hay container?

Trong các tài khoản provisioned throughput hỗ trợ, throughput có thể được đặt ở:

1. **Container level:** mỗi container có mức manual/autoscale riêng.
2. **Database level (shared throughput):** các containers phù hợp trong database chia sẻ RU/s được provision; có thể có quy tắc phân bổ/giới hạn riêng.
3. **Mixed model:** một số containers dùng shared throughput, một số containers có throughput riêng theo khả năng dịch vụ.

### Container-level throughput

Ưu điểm:

- Dễ cô lập load/chi phí giữa `orders`, `carts`, `events`.
- Một container analytics nhiều truy vấn không trực tiếp dùng hết RU/s dành riêng của OLTP container khác.
- Dễ chọn SLA/công suất cụ thể cho workload quan trọng.

Đánh đổi: nhiều containers riêng, mỗi nơi có throughput tối thiểu/chi phí baseline riêng. Với hàng trăm container cực nhỏ, tổng baseline có thể cao.

### Database shared throughput

Phù hợp khi nhiều containers **tải nhỏ, không đồng đều** và có thể chia sẻ công suất. Rủi ro là một container hot dùng tỷ lệ lớn ngân sách khiến container khác bị throttling.

**Không tự hiểu shared throughput là mỗi container được bảo đảm toàn bộ RU/s.** Cần xem cơ chế phân bổ của dịch vụ và đo contention thật. Đối với business-critical container, cân nhắc dedicated throughput để tránh "noisy neighbor".

### Serverless không phải shared provisioned throughput

Serverless được tính theo RU tiêu thụ trong mô hình account tương ứng; không khai báo một pool `shared 4.000 RU/s` giống provisioned database throughput. Vẫn phải thiết kế partition key và giới hạn hoạt động.

## 12. Logical partition, physical partition và hot key

**Partition key** là một thuộc tính trong document, ví dụ `/tenantId`. Các documents cùng một giá trị khóa thuộc cùng **logical partition**. Hệ thống ánh xạ các logical partitions lên những **physical partitions** để phân tán lưu trữ và throughput.

~~~mermaid
flowchart TD
  C["Container orders: partition key /tenantId"] --> L1["tenant-A logical partition"]
  C --> L2["tenant-B logical partition"]
  C --> L3["tenant-C logical partition"]
  C --> L4["tenant-D ..."]
  L1 --> P1["Physical partition 1"]
  L2 --> P2["Physical partition 2"]
  L3 --> P2
  L4 --> P3["Physical partition 3"]
  P1 --> RU["Provisioned / autoscale RU/s phân bổ"]
  P2 --> RU
  P3 --> RU
~~~

Sơ đồ chỉ minh họa việc ánh xạ; physical partitions có thể tự chia khi dữ liệu/công suất thay đổi, và chi tiết phân bổ khác nhau theo throughput mode.

### Hot logical partition

Một tenant lớn tạo 80% requests, 20% còn lại chia giữa hàng nghìn tenants. Nếu mọi item của tenant lớn có `tenantId="enterprise-1"`, một logical partition có thể trở thành điểm nóng. **Không thể chia một logical partition đã chọn thành nhiều logical partitions chỉ bằng tăng RU/s** nếu không đổi partition strategy/data model.

### Hot physical partition

Nhiều logical keys nhỏ có thể tình cờ tập trung một physical partition ở thời điểm nhất định. Khi metric normalized RU consumption của partition đó đạt gần 100%, có thể xảy ra 429 tại partition đó trong khi tổng account/container chưa dùng hết mức provisioned RU/s.

**Tổng RU/s còn dư không chứng minh mọi request đều có đủ RU/s.** Phải xem distribution và key-based load.

### Các câu hỏi chọn partition key

- Khóa có xuất hiện trong các point reads/queries thường gặp?
- Giá trị khóa có đủ nhiều và phân bố khá đều không?
- Một giá trị có thể tăng quá lớn về dung lượng hoặc RU/s không?
- Có thể tạo synthetic key/hierarchical partition key trong khả năng API/SDK không?
- Có cần transaction boundary trong cùng logical partition không?
- Query cross-partition có chấp nhận được không?

Thay partition key của container đang chạy **không phải một đổi tên trường đơn giản**; thường cần tạo container mới và di chuyển dữ liệu theo tính năng được hỗ trợ.

## 13. Partition key và thiết kế ứng dụng nhiều tenant

Ví dụ item:

~~~json
{
  "id": "order-1024",
  "tenantId": "tenant-A",
  "orderDate": "2026-11-20",
  "status": "PAID",
  "totalAmountMinor": 259000,
  "currency": "VND"
}
~~~

Với partition key `/tenantId`, có thể point read bằng `id` và `tenantId`:

~~~text
id = "order-1024"
partitionKey = "tenant-A"
~~~

Nếu người dùng chỉ gửi `orderId` mà ứng dụng không biết tenant, việc tìm kiếm có thể trở thành cross-partition query. Giải pháp là giữ tenant identity từ authentication/session hoặc mapping phù hợp; không tự xây query fan-out cho mọi GET.

### Tenant lớn quá nóng

Một số chiến lược cần đánh giá:

1. Thiết kế **synthetic partition key** như tenant + bucket có quy tắc truy vấn rõ ràng.
2. **Hierarchical partition keys** khi API/SDK và data model hỗ trợ, lưu ý thứ tự keys và pattern truy vấn.
3. Tách tenant đặc biệt sang container/account riêng nếu cần isolation và ngân sách.
4. Dùng queue/event processing để làm phẳng các burst writes.
5. Kiểm soát per-tenant rate limits và tránh noisy neighbor.

**Không thêm random suffix cho mọi key mà không giữ cách truy vấn**: nếu không thể biết bucket, point read có thể biến thành nhiều truy vấn, làm tăng RU và latency.

## 14. Throughput phân phối qua physical partitions

Provisioned throughput của container được phân phối trên các physical partitions theo cơ chế dịch vụ. Một physical partition có **khả năng tối đa hữu hạn**, nên throughput có thể không khả dụng đồng đều cho mọi logical key ở cùng giây.

Ví dụ tư duy:

~~~text
Provisioned throughput container: 12.000 RU/s
Giả sử chia qua 3 physical partitions
  Partition P1: 4.000 RU/s
  Partition P2: 4.000 RU/s
  Partition P3: 4.000 RU/s

Workload hiện tại:
  P1 dùng 4.300 RU/s -> có thể throttle
  P2 dùng 1.200 RU/s
  P3 dùng 1.100 RU/s

Tổng ứng dụng dùng 6.600 RU/s < 12.000 RU/s
Nhưng P1 vẫn có thể phát sinh 429
~~~

Các số chia đều chỉ để minh họa **hot partition**; số physical partitions, RU distribution, autoscale behavior và throttle thực tế phải xem từ Azure Monitor cho đúng tài nguyên.

### Physical partition split

Khi dữ liệu hoặc throughput tăng, Cosmos DB có thể chia physical partitions tự động. Việc chia không sửa semantic của logical partition key. Nếu một logical key chiếm phần lớn traffic, **split physical partition không đảm bảo giải quyết hot key**.

Theo dõi `Normalized RU Consumption` theo partition/region cùng request charge theo operation; đừng chỉ dùng tổng `Total Request Units`.

## 15. HTTP 429: khi request bị giới hạn throughput

**HTTP 429 Too Many Requests** trong Cosmos DB thường biểu thị request không được phục vụ ngay vì throughput/partition capacity tại thời điểm đó. Response có thể kèm thời gian cần chờ trước khi retry, ví dụ header:

~~~http
HTTP/1.1 429 Too Many Requests
x-ms-retry-after-ms: 25
~~~

`25` ở đây là **25 mili-giây minh họa**, không phải thời gian retry cố định. Cần tôn trọng thông tin retry-after và chính sách SDK; không tự retry ngay lập tức liên tục.

### 429 có luôn là incident không?

Không nhất thiết. Azure Cosmos DB SDK có cơ chế retry tự động với throttling theo các giới hạn được cấu hình. Một lượng 429 thấp có thể là dấu hiệu dịch vụ đang sử dụng gần capacity; **nhưng mức 429 cao hoặc retry kéo dài gây tăng p95/p99 latency và vi phạm SLO** phải được điều tra.

Cần phân biệt:

- `429` do thiếu RU/s tổng thể.
- `429` do hot partition dù tổng RU/s chưa hết.
- `429` do burst serverless chạm giới hạn.
- Retry đã được SDK xử lý thành công sau đó.
- API/business request bị timeout vì tổng thời gian retry.

### Điều không nên làm

- Không tạo vòng lặp `while(true) { retry(); }` không delay.
- Không tăng số threads vô hạn để "đẩy qua" 429.
- Không trả tất cả 429 thành HTTP 500 mà không ghi rõ nguyên nhân/thời điểm.
- Không tắt retry SDK khi chưa hiểu tác động.
- Không log toàn bộ Cosmos diagnostics chứa dữ liệu nhạy cảm.

### Cách xử lý từng bước

1. Kiểm tra latency/error rates ở ứng dụng, 429 rate và retry metrics.
2. Đo request charge RU/op của những thao tác nhiều nhất.
3. Kiểm tra normalized RU consumption **theo partition**.
4. Xác minh `Tmax` hoặc manual RU/s và mức sử dụng.
5. Điều tra query cross-partition/indexing hoặc items lớn.
6. Điều chỉnh concurrency/batch size/bulk ingestion theo SLO.
7. Scale throughput nếu phù hợp và vẫn không vượt giới hạn vật lý/hot key.
8. Thử lại với load test trước khi điều chỉnh production rộng rãi.

## 16. SDK retry, timeout và end-to-end latency

Khi một REST request tới Cosmos DB bị throttling, Java SDK có thể retry theo chính sách mặc định hoặc cấu hình. Việc ứng dụng thấy một operation thành công **không chứng minh không có retry/429** ở các attempts bên dưới.

Điều cần đo:

- Total elapsed time cho operation.
- Request charge của response và tổng tài nguyên tiêu thụ khi có nhiều pages/requests.
- Diagnostics: contacted region, retries, status/substatus.
- Số thao tác business hoàn tất.
- API timeout/deadline tổng thể.
- Latency percentiles của từng loại operation.

### Retry và idempotency

Với write/update/upsert, client có thể timeout sau khi server đã commit nhưng trước khi response đến. Khi retry, cần dùng `id`/partition key ổn định, `ETag`/optimistic concurrency hoặc business idempotency key phù hợp để không tạo duplicated invoices/orders.

**SDK retry cho 429 không thay thế business-level correctness.** Nó có thể giúp request vượt qua throttling tạm thời, nhưng không thể bảo đảm một external side effect chỉ diễn ra một lần.

### Đặt timeout budgets

Nếu API phải phản hồi trong 800 ms, không để một query có hàng chục pages và retry kéo dài nhiều giây trong HTTP request. Có thể thiết kế bất đồng bộ qua Azure Service Bus/Queue Storage/Functions cho tác vụ nặng, lưu job status rồi trả `202 Accepted`.

## 17. Tối ưu RU: point reads trước khi query

Một query kiểu:

~~~sql
SELECT * FROM c
WHERE c.id = "order-1024"
~~~

nếu không có partition key filter phù hợp **có thể quét nhiều logical/physical partitions**. Nếu đã biết `id` và `tenantId`, hãy dùng **point read** bằng SDK:

~~~text
container.readItem(
  id = "order-1024",
  partitionKey = "tenant-A"
)
~~~

Hai cách có thể trả về cùng item, nhưng RU charge và latency khác nhau đáng kể. Point read thường là cách tiết kiệm RU khi truy cập item đơn lẻ theo khóa.

### Query đúng partition

Khi phải query:

~~~sql
SELECT c.id, c.status, c.totalAmountMinor
FROM c
WHERE c.tenantId = "tenant-A"
  AND c.status = "PAID"
~~~

Cung cấp partition key qua **query request options** hoặc dùng điều kiện được hệ thống tối ưu phù hợp, kết hợp parameterized query để tránh SQL injection/data leakage. Không nối raw tenant ID từ request vào query string production.

### Projection và pagination

- Chỉ chọn fields cần thay vì luôn `SELECT *`.
- Dùng continuation tokens để đọc trang tiếp theo.
- Chỉ load trang cần thiết cho UI.
- Theo dõi RU **mỗi trang** và tổng RU của toàn bộ nghiệp vụ.
- Không coi một query returning 0 items là miễn phí RU.

## 18. Indexing policy ảnh hưởng RU thế nào?

Azure Cosmos DB for NoSQL tự động index theo **indexing policy** của container. Lợi ích là truy vấn linh hoạt, nhưng cập nhật indexes có chi phí khi write.

Ví dụ tình huống:

- Mỗi đơn hàng có 60 properties nhưng ứng dụng chỉ query theo `tenantId`, `status`, `createdAt`.
- Index toàn bộ paths có thể làm writes tốn RU hơn cần thiết.
- Bỏ index không cẩn thận có thể làm query chậm/tốn RU hoặc bị lỗi do index yêu cầu.

### Cách đánh giá

1. Thu query workload thực tế và plans/index utilization.
2. Đo RU charge của writes/queries trước khi thay.
3. Chọn include/exclude paths và composite indexes khi `ORDER BY`/query pattern yêu cầu.
4. Triển khai thay đổi vào môi trường thử nghiệm tương đương dữ liệu.
5. Theo dõi quá trình index transformation và chi phí/tác động.
6. Kiểm tra mọi query quan trọng sau migration.

### Indexing policy minh họa

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/tenantId/?"},
    {"path": "/status/?"},
    {"path": "/createdAt/?"}
  ],
  "excludedPaths": [
    {"path": "/*"}
  ]
}
~~~

Đây là ví dụ **hình thức policy để thảo luận**, không phải cấu hình an toàn để áp ngay cho mọi workload. Chọn include/exclude cụ thể phải xét **partition key behavior, hệ thống index mặc định, index paths và tất cả truy vấn của container**; cần xác nhận JSON syntax/tính năng hiện hành. Không thay policy production chỉ để tối ưu một query đơn lẻ khi những workload khác vẫn cần indexes.

## 19. Query patterns tốn RU và cách cải thiện

| Anti-pattern | Vì sao tốn RU / gây bottleneck | Thay đổi nên thử |
|---|---|---|
| Query toàn container khi đã biết id+key | Cross-partition fan-out | Point read |
| `SELECT *` ở mọi API | Trả về nhiều dữ liệu không cần | Projection |
| Query báo cáo toàn dữ liệu OLTP vào giờ cao điểm | Nhiều pages và consume throughput | Data pipeline/analytical store hoặc cô lập workload |
| `ORDER BY` phức tạp không có index phù hợp | Query có thể tốn RU hoặc không được hỗ trợ | Composite/index design |
| Item rất lớn chứa blob/text khổng lồ | Read/write charges tăng | Blob reference |
| Upsert toàn item cho một field nhỏ | Ghi lại document lớn | Patch operations nếu phù hợp |
| Partition key ít giá trị | Hot partitions | Key distribution/synthetic key |
| Polling dữ liệu với query liên tục | Repeated reads | Change feed/events nếu phù hợp |
| Không lưu continuation token | Đọc lại các trang trước | Proper pagination |
| Lặp lại write vì timeout | Extra RU + duplicate effects | Idempotency và concurrency control |

**Không tự khẳng định Patch luôn rẻ hơn Replace**: chi phí RU của patch phụ thuộc số path, indexing, item size và engine behavior. Đo `request charge` thực tế trước khi tối ưu.

## 20. Consistency level và RU

Cosmos DB cung cấp những lựa chọn **consistency** như Strong, Bounded Staleness, Session, Consistent Prefix và Eventual trong khả năng API/account/region tương ứng. Consistency ảnh hưởng:

- Ứng dụng nhìn thấy bản ghi mới nhanh và nhất quán đến mức nào.
- Trade-off latency/availability trong phân tán nhiều vùng.
- Một số cách tính RU read charge và triển khai replication.
- Yêu cầu session token, read-your-writes và conflict handling.

Ví dụ tư duy: các consistency level mạnh hơn có thể khiến **read cost khác** so với Session/Eventual, nhưng không nên áp một hệ số RU cố định cho mọi API/operation/region. Hãy đo cùng point reads/query trong cấu hình thật.

### Session consistency

Một ứng dụng người dùng tạo đơn hàng rồi đọc lại thường cân nhắc **Session** nếu đủ đáp ứng tính nhất quán cần thiết. SDK có thể quản lý session tokens phù hợp, nhưng khi chuyển session giữa requests/services cần hiểu boundary và khả năng token propagation.

### Khi cần Strong

Nếu nghiệp vụ cần read chắc chắn thấy ghi mới nhất theo mô hình nhất quán mạnh, cần đánh giá Strong cùng topology, latency, supported regions và chi phí. Không lựa chọn Strong mặc định nếu ứng dụng chỉ cần eventual convergence, nhưng cũng không hy sinh correctness chỉ để giảm RU.

## 21. Multi-region throughput, availability và phí

Azure Cosmos DB có khả năng phân phối dữ liệu qua nhiều regions theo account configuration, hỗ trợ nhiều kiểu write regions/failover trong giới hạn SKU và consistency.

### Điểm quan trọng

1. **Provisioned throughput** có thể liên quan tới tài nguyên/capacity tại từng region, không chỉ một con số toàn cầu trên slide.
2. Multi-region replication có thể tăng chi phí throughput/storage/network theo cấu hình và biểu giá.
3. Multi-write cần quản lý conflict semantics và quy tắc ứng dụng phù hợp.
4. Read/write latency phụ thuộc region client, routing và consistency.
5. Một lỗi region cần phương án failover, DNS/SDK endpoint discovery và business recovery.
6. Serverless có **ràng buộc account/region** cần kiểm tra trước khi thiết kế global app.

### Ví dụ thiếu sót chi phí

~~~text
Kế hoạch sai:
  "Container cần 4.000 RU/s, vậy trả đúng 4.000 RU/s toàn cầu"

Cần hỏi:
  Có bao nhiêu regions?
  Mỗi region nhận lượng đọc/ghi bao nhiêu?
  Manual hay autoscale?
  Multi-write hay single-write?
  Có multi-region throughput billing, storage replication?
  Có dedicated gateway/integrated cache hoặc dịch vụ phụ?
~~~

Không nhân một hệ số cố định cho mọi account/region mà không kiểm tra biểu giá thực tế.

### Private networking

Cosmos DB account có khả năng network control và Private Endpoint theo API/features được hỗ trợ. Khi client Java trong AKS/Container Apps/VM truy cập qua VNet/private endpoint:

- Xác nhận private DNS resolution tới địa chỉ đúng.
- Kiểm tra egress routing, NSG/firewall và endpoint policy.
- Cấu hình managed identity/RBAC phù hợp.
- Không nhầm lỗi HTTP 403 do quyền hoặc mạng với 429 do throughput.
- Kiểm tra SDK connection mode hỗ trợ đường mạng tương ứng.

## 22. Ước lượng RU/s bằng workload matrix

Bắt đầu từ **những use case thật**, không chỉ số concurrent users.

| Operation | Requests/s ở giờ cao điểm | RU/op đo thử | Nhu cầu RU/s |
|---|---:|---:|---:|
| Read cart point read | 800 | 1,2 | 960 |
| Update cart | 180 | 8 | 1.440 |
| Create order | 70 | 12 | 840 |
| Query order history | 40 | 20 | 800 |
| **Tổng** | | | **4.040** |

Giả sử nhu cầu tức thời 4.040 RU/s được phân bố tốt. Nếu dự trù 25% headroom cho biến động, target khoảng **5.050 RU/s**. Hãy chọn giá trị có thể cấu hình hợp lệ sau khi xét minimum throughput, partitions và max RU/s constraints; một phương án lab có thể đánh giá **manual ~6.000 RU/s hoặc autoscale Tmax ~8.000 RU/s**, chứ không có lời bảo đảm cứng về throughput/latency.

### Tại sao không lấy average requests/day?

Giả sử 1 triệu requests trong một ngày:

~~~text
Average QPS = 1.000.000 / 86.400 ≈ 11,57 requests/s
~~~

Con số này **không cho biết đỉnh**. Nếu 500.000 requests dồn trong 10 phút, peak QPS khoảng 833 requests/s; nhu cầu RU/s theo từng operation có thể cao gấp nhiều lần mức trung bình.

### Thêm batch/background traffic

Khi có nightly ETL, TTL deletion, change feed processors và report queries, thêm workload của chúng vào sizing hoặc cách ly container/workload. Không chỉ tính user-facing API.

## 23. Ví dụ so sánh chi phí bằng biến số

Để tránh nhầm giá không còn đúng, dùng biến:

- `P_manual`: đơn giá cho một đơn vị provisioned RU/s theo một chu kỳ giờ trong region/tier cụ thể.
- `P_auto`: đơn giá tương ứng với autoscale provisioned RU/s trong chu kỳ giờ.
- `P_serverless`: đơn giá cho một triệu RU đã tiêu thụ trong serverless.
- `S`: storage và các phí ngoài throughput, xét riêng.

### Manual

~~~text
Manual RU/s: 2.000
Số giờ tháng ví dụ: 730

Throughput cost ≈ 2.000 × 730 × P_manual
Tổng ≈ throughput cost + S + network/monitoring/other costs
~~~

### Autoscale

Giả sử `Tmax = 4.000 RU/s` và có thống kê công suất tính phí ở từng giờ:

~~~text
Giờ 00-05: công suất được tính phí theo mức tối thiểu/observed
Giờ 06-18: công suất theo workload biến động
Giờ 19-23: công suất theo peak và mức sàn

Throughput cost ≈ tổng theo giờ (billable autoscaled RU/s × P_auto)
~~~

Công thức biểu diễn khái niệm; **dynamic autoscale** và vùng/partition có thể có cách xác định billable RU/s khác nhau. Lấy hóa đơn/metrics thật để kiểm chứng.

### Serverless

~~~text
Monthly consumed RU: 120.000.000 RU

Request charge cost ≈ (120.000.000 / 1.000.000) × P_serverless
Tổng ≈ request cost + S + network/monitoring/other costs
~~~

Ở ví dụ này **120 triệu RU/tháng không phải 120 triệu RU/s**, cũng không cần chia cho 730 giờ để tính chi phí per-million-RU. Đây là một trong những lỗi tính giá phổ biến nhất.

### Break-even

Bạn có thể đặt hai biểu thức chi phí cạnh nhau với cùng traffic profile và dữ liệu storage. Nhưng nên dùng **request charge đã đo**, phân bố giờ/region, số physical partitions, thực tế retries và SKU/account capability. Không quyết định chỉ theo số lượng requests; 1 triệu point reads có thể rẻ/đắt khác hẳn 1 triệu cross-partition queries.

## 24. Azure CLI: xem account và throughput hiện tại

Các ví dụ dành cho **Azure Cloud Shell Bash** hoặc máy có Azure CLI đã đăng nhập. Không cần tạo resource mới để bắt đầu đọc và đánh giá. Thay placeholders bằng tên resource đã được cấp quyền.

### Bước 1 — Xem subscription

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table
~~~

### Bước 2 — Đọc account configuration

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="<COSMOS_ACCOUNT>"
DB="commerce"
CONTAINER="orders"

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,location:location,kind:kind,capabilities:capabilities,locations:locations,consistencyPolicy:consistencyPolicy}" \
  --output json
~~~

Kiểm tra API type, regions, consistency và capabilities như serverless nếu hiện trong output. Các field/format phụ thuộc ARM API/CLI; không kết luận account ở mode nào chỉ từ một field vắng mặt.

### Bước 3 — Throughput container

~~~bash
az cosmosdb sql container throughput show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --output json
~~~

Nếu container dùng **database shared throughput**, thao tác đọc throughput riêng có thể không trả kết quả theo cách bạn chờ. Khi đó xem database-level:

~~~bash
az cosmosdb sql database throughput show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --name "$DB" \
  --output json
~~~

Với **serverless**, không có provisioned RU/s như manual/autoscale để truy vấn theo cách trên. Lệnh không trả throughput vì vậy có thể là **không có throughput dedicated**, serverless hoặc một lỗi quyền/cú pháp; cần đối chiếu account capability và resource properties.

### Bước 4 — Xem container partition key/indexing

~~~bash
az cosmosdb sql container show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --query "{id:resource.id,partitionKey:resource.partitionKey,indexingPolicy:resource.indexingPolicy}" \
  --output json
~~~

Khi Azure CLI version trả JSON shape khác, đọc các property được phép theo schema của resource. Không gửi toàn bộ account keys, connection strings hoặc access credentials vào báo cáo.

## 25. Azure CLI: tạo container có throughput cố định hoặc autoscale

**Đây là ví dụ thay đổi tài nguyên, có thể phát sinh chi phí.** Chỉ chạy khi đã có resource group, Cosmos DB for NoSQL account và database phù hợp trong lab, với quyền quản trị được phê duyệt. Các tên container dưới đây **độc lập** để không tạo xung đột.

### Manual provisioned throughput

~~~bash
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "orders-manual-lab" \
  --partition-key-path "/tenantId" \
  --throughput 1000
~~~

### Autoscale provisioned throughput

~~~bash
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "orders-auto-lab" \
  --partition-key-path "/tenantId" \
  --max-throughput 4000
~~~

Kiểm tra các tham số và **mức tối thiểu được tài khoản chấp nhận** bằng `az cosmosdb sql container create --help` và cấu hình live. Không dùng cả `--throughput` và `--max-throughput` như thể đang muốn hai chế độ cùng lúc; chúng đại diện các mô hình throughput khác nhau.

### Serverless

Serverless không khai báo `--throughput` hoặc `--max-throughput` khi tạo container trong account serverless được hỗ trợ. **Không tạo một account production mới chỉ để thử rồi kỳ vọng chuyển billing mode tùy ý**. Hãy dùng account lab được chỉ định hoặc tạo theo quy trình IaC/Portal đã phê duyệt, kiểm tra account capability và giới hạn của region.

### Thay đổi throughput hiện có

Các chức năng update/migrate throughput mode có ràng buộc theo account/container, mức tối thiểu, partition state và API version. Trước khi nâng throughput trên production:

1. Lấy **current provisioned RU/s, autoscale max RU/s, storage size, physical partition state**.
2. Xem cost impact dự kiến và khả năng giảm throughput về sau.
3. Kiểm tra operation có cần migration/manual-to-autoscale theo cú pháp hỗ trợ không.
4. Thử ở staging, quan sát 429/latency.
5. Ghi lại thay đổi cấu hình, chủ sở hữu, thời gian và rollback logic.

**Không chạy lệnh update throughput mơ hồ** khi chưa biết container dùng shared database throughput hay dedicated throughput.

## 26. Azure SDK for Java: đo RU bằng point read

Dùng Maven dependency theo phiên bản được tổ chức phê duyệt:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
    <version>${azure.cosmos.version}</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>${azure.identity.version}</version>
  </dependency>
</dependencies>
~~~

Đây là **mảnh POM**, phải khai báo version properties hoặc Azure SDK BOM/phương pháp dependency management tương thích. Đoạn Java giả định account dùng **Azure Cosmos DB for NoSQL** và có Microsoft Entra data-plane RBAC phù hợp.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class CosmosRuDemo {

    public static final class Order {
        public String id;
        public String tenantId;
        public String status;
    }

    public static void main(String[] args) {
        String endpoint = System.getenv("COSMOS_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("Missing COSMOS_ENDPOINT");
        }

        try (CosmosClient client = new CosmosClientBuilder()
                .endpoint(endpoint)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient()) {

            CosmosContainer container = client
                .getDatabase("commerce")
                .getContainer("orders");

            CosmosItemResponse<Order> response = container.readItem(
                "order-1024",
                new PartitionKey("tenant-A"),
                Order.class
            );

            System.out.printf("RU charge: %.2f%n",
                response.getRequestCharge());
            System.out.println("Order status: "
                + response.getItem().status);
        }
    }
}
~~~

### Lưu ý khi chạy thật

- `COSMOS_ENDPOINT` có dạng `https://<account>.documents.azure.com:443/` tùy endpoint được cung cấp, **không chứa key**.
- `DefaultAzureCredential` sẽ dùng developer identity ở local hoặc managed identity/workload identity tùy môi trường; xác nhận credential thực.
- Role **control-plane** có thể không đồng nghĩa quyền đọc items; cần Cosmos DB **data-plane RBAC** đúng phạm vi khi dùng Entra authentication.
- Item `order-1024` với partition key `tenant-A` phải tồn tại trong lab.
- Tên database/container phải khớp resource đã có.
- Nếu Java SDK version có API khác, kiểm tra SDK/JDK compatibility.
- `getRequestCharge()` trả RU của lần đọc item, **không** phải throughput RU/s.
- Không log toàn document nếu có dữ liệu nhạy cảm.

### Khi nào SDK dùng key auth?

Một số môi trường hiện hữu có Cosmos DB account keys/connection strings. Nếu dùng, phải quản lý trong Key Vault/secrets, rotate, hạn chế scope và không commit vào repo. Với ứng dụng mới, ưu tiên Microsoft Entra identity/RBAC nếu API/SDK/tính năng hỗ trợ.

## 27. Java SDK: query có partition key và tổng RU theo page

Để đo chi phí truy vấn nhiều trang, sử dụng `CosmosPagedIterable` và `FeedResponse` theo SDK tương thích. Ví dụ minh họa:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.FeedResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.util.CosmosPagedIterable;

CosmosQueryRequestOptions options = new CosmosQueryRequestOptions()
    .setPartitionKey(new PartitionKey("tenant-A"));

String query = "SELECT * FROM c WHERE c.status = 'PAID'";

CosmosPagedIterable<CosmosRuDemo.Order> results =
    container.queryItems(query, options, CosmosRuDemo.Order.class);

double totalRu = 0.0;
long count = 0;

for (FeedResponse<CosmosRuDemo.Order> page :
        results.iterableByPage()) {
    totalRu += page.getRequestCharge();
    count += page.getResults().size();
}

System.out.printf("Items=%d, total query RU=%.2f%n", count, totalRu);
~~~

Đoạn code là **snippet** bên trong method đã có biến `container`. Phải bổ sung class/imports/schema và phiên bản SDK phù hợp. Khi query dữ liệu người dùng, dùng **parameterized query**; giá trị `PAID` cố định chỉ để minh họa.

### Đọc một trang không đại diện toàn query

Nếu kết quả có 50 trang, request charge trang đầu không phản ánh toàn bộ chi phí của báo cáo. Ngược lại, không đọc hết pages nếu UI chỉ cần trang đầu; continuation tokens giúp phân trang theo nhu cầu.

### Diagnostics

Khi có 429 hoặc latency cao, SDK diagnostics có thể cho biết thông tin về retries, transport, partition routing, contacted region và request timeline. **Chỉ xuất những trường cần thiết đã được phê duyệt**, vì diagnostics có thể chứa URI, partition metadata hoặc thông tin ứng dụng nhạy cảm.

## 28. Theo dõi bằng Azure Monitor, metrics và cảnh báo

Các tín hiệu quan trọng:

| Tín hiệu | Mục tiêu |
|---|---|
| Total Request Units | Tổng RU tiêu thụ theo thời gian |
| Normalized RU Consumption | Mức dùng RU đã chuẩn hóa theo resource/partition/region |
| Throttled requests / 429 count | Tần suất bị giới hạn năng lực |
| Request count và status codes | Mẫu traffic và lỗi |
| Server-side latency | Độ trễ xử lý ở dịch vụ |
| Client-side p95/p99 latency | Trải nghiệm end-to-end, bao gồm retry/network |
| Data storage | Dung lượng items/index và tốc độ tăng |
| Provisioned/autoscale throughput | Capacity cấp phát hoặc maximum configured |
| Physical partition distribution | Phát hiện hot partition |
| Region availability/failover | Kiểm tra continuity và latency theo vùng |
| Cost by meter | Kiểm tra provisioned/serverless/storage/network/backup |

Các metric names/ dimensions và mức hỗ trợ khác nhau theo loại tài khoản và API. Trong Azure Portal, mở Cosmos DB account → **Metrics** và lọc theo database, container, partition/region theo khả năng. Không tự giả định mọi metric xuất sẵn granularity 1 giây hoặc cho mọi account.

### Azure CLI xem metric definitions

~~~bash
ACCOUNT_ID=$(az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query id -o tsv)

az monitor metrics list-definitions \
  --resource "$ACCOUNT_ID" \
  --output table
~~~

Sau khi biết tên metric thực tế được công bố, có thể dùng `az monitor metrics list` với metric name và time range phù hợp. Không gọi một tên metric tưởng tượng rồi suy diễn `0` là không có RU.

### Alert nên gắn với SLO

1. 429 vượt baseline trong một cửa sổ, **kèm p95 latency** hoặc request failure thực.
2. Normalized RU Consumption gần 100% ở một/một số partitions trong nhiều phút.
3. RU/op của query quan trọng tăng sau deployment.
4. Total Request Units hoặc serverless usage tăng bất thường.
5. Autoscale thường xuyên chạm `Tmax`.
6. Data storage/backup costs vượt ngân sách.
7. Private networking/authorization errors tăng, phân biệt với throttling.
8. Region/failover health bất thường.

**Một giá trị 429 đơn lẻ không tự động là sự cố nghiêm trọng.** Chọn alert theo hậu quả người dùng, throughput saturation, retry time và SLA của ứng dụng.

## 29. Mô hình benchmark để chọn throughput mode

Một benchmark có ích phải tạo **một workload đại diện**, không chỉ chạy point read 1 KiB trên container rỗng.

### Chuẩn bị

- Dữ liệu đủ lớn và partition key distribution gần thực tế.
- Item sizes/fields/index policy tương đương production.
- Tỷ lệ reads/writes/queries/delete thực tế.
- Client regions, network mode và consistency tương ứng.
- Tải peak theo giây/phút, không chỉ average QPS.
- Thời gian chạy đủ qua các pha warm-up/burst/recovery.
- Retry policy, concurrency và connection settings có giới hạn.

### Thu thập

| Phép đo | Đơn vị | Vì sao |
|---|---|---|
| Business operations/s | ops/s | Thông lượng hoàn tất |
| Consumed RU/s | RU/s | Nhu cầu thực |
| RU/op theo use case | RU | Tối ưu từng đường truy cập |
| 429 ratio | % attempts | Throttle/saturation |
| Client p50/p95/p99 | ms | User SLO |
| Normalized RU by partition | % | Phát hiện hot key |
| Physical partition count/distribution | count | Xem ảnh hưởng scale |
| Autoscale capacity/billable peak | RU/s | Kiểm chứng cost |
| Total serverless RU consumed | RU | Tính chi phí pay-per-request |
| Storage, index and network | GB, requests | Chi phí phụ |

### Chạy ba kịch bản

1. **Tải nền:** liên tục trong vài giờ, đo manual utilization và chi phí baseline.
2. **Đỉnh ngắn:** tăng nhanh lên gấp nhiều lần; quan sát autoscale response và serverless 429.
3. **Tải lệch key:** 80% requests vào một tenant; xem partition saturation.

Chỉ khi cả ba đạt SLO với chi phí hợp lý mới chọn model. **Không tối ưu chỉ dựa trên giá mỗi triệu RU** mà bỏ qua 429 và latency.

## 30. Case study: hệ thống bán hàng nhiều tenant

### Bối cảnh

Một nền tảng SaaS lưu đơn hàng cho 3.000 tenants trên Azure Cosmos DB for NoSQL. Giả sử:

- 95% thời gian chỉ tiêu thụ khoảng 350 RU/s.
- Giờ cao điểm tăng tới 4.000 RU/s, một số đợt 7.000 RU/s.
- Một tenant lớn chiếm 40% writes trong giờ khuyến mãi.
- Ứng dụng Java chạy trên Azure Container Apps.
- Dữ liệu được truy cập từ một region chính; DR có yêu cầu riêng.
- SLA nội bộ của API yêu cầu p95 nhỏ hơn một ngưỡng đã được đội xác định.

### Lựa chọn ban đầu

**Manual 8.000 RU/s:** có headroom cho peak trong trường hợp phân bố tốt, nhưng trả tiền capacity cả ngày; cần so chi phí với giá trị SLO.

**Autoscale Tmax khoảng 8.000 RU/s:** có thể phù hợp nếu peak đã đo, nhưng chi phí theo provisioned autoscale và giờ cao điểm phải được tính. Nếu hot tenant tập trung một logical partition, vẫn có thể 429 dù max lớn.

**Serverless:** tiết kiệm phí provisioned khi ít traffic, nhưng cần xác minh throughput limits/region/account capabilities và chi phí RU thực tế ở các peak. Không tự chọn serverless nếu burst/SLI không được đáp ứng.

### Kế hoạch xử lý tenant nóng

1. Đo `RU/op` của writes tenant đó.
2. Kiểm tra normalized RU theo partition.
3. Đánh giá chia workload thành bucket/hierarchical key nếu semantics cho phép.
4. Dùng API rate limits per tenant và queue smoothing cho batch writes.
5. Xem container dedicated/tenant isolation nếu noise ảnh hưởng toàn hệ thống.
6. Benchmark lại trước khi nâng provisioned RU/s.
7. Theo dõi chi phí và quyền truy cập tenants, không log raw sensitive keys.

### Sơ đồ

~~~mermaid
flowchart LR
  C["Clients nhiều tenants"] --> API["Java API / Container Apps"]
  API --> CACHE["Cache theo yêu cầu"]
  API --> DB["Cosmos DB for NoSQL"]
  DB --> P1["Physical partition A"]
  DB --> P2["Physical partition B"]
  DB --> P3["Physical partition C"]
  API --> Q["Service Bus / Queue cho writes batch"]
  Q --> W["Idempotent workers"]
  W --> DB
  DB --> MON["Azure Monitor: RU, 429, partition"]
~~~

Cache có thể giảm reads nhưng cũng tạo bài toán **cache invalidation, consistency và chi phí**. Queue smoothing giúp điều tiết burst chứ không tăng throughput vật lý của một hot logical partition. Cần đo từng biện pháp.

## 31. Bài thực hành lab: đo RU và chọn model

> **An toàn:** các lệnh tạo account/container, tăng RU/s hoặc chạy load test có thể phát sinh chi phí và gây throttling. Chỉ dùng resource group và account lab được phép; không làm trên production hoặc account chia sẻ mà chưa được phê duyệt.

### Phần A — Quan sát và phân loại

1. Dùng `az account show` xác nhận subscription.
2. Dùng `az cosmosdb show` xác nhận account type, capability, regions và consistency.
3. Kiểm tra database/container throughput. Phân biệt dedicated với shared.
4. Ghi partition key và indexing policy của một container lab.
5. Xác định account thuộc manual, autoscale hay serverless qua resource properties/portal.
6. Ghi các metric hiện có trong Azure Monitor và phân biệt RU/s với total RU.

### Phần B — Dữ liệu và Java SDK

1. Chuẩn bị dataset JSON có `id`, `tenantId`, `status`, `totalAmountMinor`.
2. Ghi 100–1.000 items bằng script/SDK được chấp thuận trong container lab.
3. Đọc từng item bằng `id` + `tenantId`, ghi RU charge.
4. Query đúng partition và đo tổng RU qua từng page.
5. Query không giới hạn partition trong lab để so sánh RU/latency (chỉ ở tải nhỏ được phép).
6. Tạo item với size lớn hơn để xem write RU thay đổi.
7. Thử một query có `ORDER BY`, kiểm tra policy/index phù hợp trước và sau.
8. Thu client latency, status, diagnostic retry count mà không log payload nhạy cảm.

### Phần C — So sánh mode theo công thức

Giả sử 100.000 reads/ngày, trung bình 1,2 RU/read; 20.000 writes/ngày, trung bình 7 RU/write; 2.000 query pages/ngày, trung bình 18 RU/page.

1. Tính **daily RU consumed**.
2. Tính **monthly RU consumed** theo số ngày giả định.
3. Với traffic dồn vào 5 phút/ngày, tính RU/s peak xấp xỉ.
4. Đề xuất manual RU/s có headroom khi partition phân bố tốt.
5. Đề xuất autoscale `Tmax` dựa trên peak và có buffer.
6. Tính biểu thức chi phí serverless theo `P_serverless`.
7. Tính biểu thức chi phí manual/autoscale theo giá giả định và capacity billed, **không dùng giá không kiểm chứng**.
8. Giải thích vì sao hai workloads có cùng tổng RU/tháng vẫn khác nhau về nhu cầu RU/s/peak.
9. Đánh giá trường hợp tenant hot nhận 90% requests; throughput tổng có giải quyết hoàn toàn không?
10. Kết luận mô hình nào phù hợp và rủi ro còn lại cần kiểm thử.

### Phần D — Monitoring và sự cố 429

1. Tạo dashboard tổng RU, 429, latency, normalized RU theo partitions và cost.
2. Trong giới hạn lab, tăng traffic có kiểm soát để quan sát throttling.
3. Tìm `x-ms-retry-after-ms`/SDK diagnostics khi có 429.
4. Kiểm tra retry tự động và client latency p95.
5. Giảm concurrency hoặc tối ưu một truy vấn tốn RU, đo sự thay đổi.
6. Nếu cần, điều chỉnh throughput theo quy trình lab rồi kiểm tra chi phí.
7. Ghi runbook xử lý khi serverless/ autoscale đạt giới hạn.
8. Xóa tài nguyên lab riêng theo quyền được cấp; kiểm tra disk/storage/backup/monitoring vẫn có thể tính phí.

### Câu hỏi tự kiểm tra

**Câu 1.** RU và RU/s khác nhau thế nào? Có thể suy ra 1 RU = 1 request mọi lúc không?

**Câu 2.** Vì sao đọc item theo `id` và partition key có thể tiết kiệm RU hơn query tìm cùng item?

**Câu 3.** Manual provisioned throughput trả phí theo tổng RU thực tế hay RU/s được cấp theo thời gian?

**Câu 4.** Autoscale `Tmax` là tối đa RU/s hay tổng RU đã tiêu thụ trong ngày?

**Câu 5.** Serverless có bảo đảm không bao giờ bị 429 và không có giới hạn burst không?

**Câu 6.** Vì sao normalized RU Consumption của một physical partition có thể đạt 100% dù tổng container chưa dùng hết RU/s?

**Câu 7.** Database shared throughput khác dedicated container throughput thế nào trong bài toán noisy neighbor?

**Câu 8.** Vì sao serverless không đơn giản là autoscale có `Tmax=0` khi idle?

**Câu 9.** `x-ms-request-charge` và `x-ms-retry-after-ms` biểu thị hai điều gì?

**Câu 10.** Nếu query trả về 20 trang, chỉ đo RU của trang đầu có đủ để tính chi phí báo cáo không?

**Câu 11.** Thêm nhiều indexes có thể giúp reads nhưng ảnh hưởng writes ra sao?

**Câu 12.** Một tenant có hot logical partition; tăng RU/s tổng container có luôn giải quyết được không?

**Câu 13.** Khi SDK tự retry sau 429, vì sao API p95 latency vẫn có thể tăng dù cuối cùng operation thành công?

**Câu 14.** Thay đổi consistency level có thể tác động đến RU, latency và correctness thế nào?

**Câu 15.** Với multi-region, vì sao cần kiểm tra throughput/cost theo region thay vì dùng một con số RU/s trên slide?

**Câu 16.** Nếu account đang ở serverless nhưng yêu cầu multi-region throughput cao hơn, nên kiểm tra những hạn chế/migration path nào?

**Câu 17.** Khi dùng managed identity, vì sao quyền Contributor ở resource group chưa chắc cấp đủ quyền đọc item?

**Câu 18.** Metric nào quan trọng để phân biệt thiếu tổng RU/s với hot partition?

**Câu 19.** Vì sao `count()` request trong ứng dụng không đủ để ước lượng chi phí nếu RU/op biến động nhiều?

**Câu 20.** Làm thế nào tính gần đúng điểm hòa vốn của manual/autoscale/serverless mà không cần bịa đơn giá?

**Tiêu chí hoàn thành:** người học giải thích chính xác RU/RU/s, chọn manual/autoscale/serverless có cơ sở, tính workload matrix, biết đo charge trong Java SDK, kiểm tra throughput bằng CLI, phát hiện hot partition và 429, cùng phương án giám sát/chi phí.

## Kết luận

**Request Unit** là thước đo quan trọng để hiểu chi phí và năng lực xử lý của Azure Cosmos DB for NoSQL, nhưng **RU cho một request** không đồng nghĩa **RU/s được provision** hay tổng RU tiêu thụ theo tháng. Muốn thiết kế đúng, hãy đo `request charge` theo use case, kết hợp số thao tác mỗi giây, peak distribution và partition key.

**Manual provisioned throughput** phù hợp với tải ổn định và có thể dự báo; **autoscale** phù hợp workload biến động nhưng vẫn có trần công suất và mức phí provisioned; **serverless** phù hợp khi traffic ít/gián đoạn và thanh toán theo RU thực sự tiêu thụ, trong những giới hạn account/region được hỗ trợ. Dù chọn mode nào, một **partition key tốt, truy vấn tối ưu, indexing/consistency có chủ đích, retry 429 an toàn, monitoring RU/latency/partition và ngân sách rõ ràng** mới giúp hệ thống Azure vừa mở rộng đáng tin cậy vừa kiểm soát chi phí.

