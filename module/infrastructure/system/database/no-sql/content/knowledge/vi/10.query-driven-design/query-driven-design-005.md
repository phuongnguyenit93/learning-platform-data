# Chọn khóa phân vùng dựa trên phân phối và giới hạn truy cập

Trong NoSQL phân tán, **khóa phân vùng (partition key)** không chỉ giúp tìm một bản ghi. Nó ảnh hưởng trực tiếp đến **nơi dữ liệu được lưu, nơi yêu cầu đọc/ghi được xử lý, kích thước đơn vị lưu trữ và khả năng phân phối tải**. Một lựa chọn khóa tốt cần đồng thời đáp ứng hai mục tiêu có thể mâu thuẫn:

1. **Đưa dữ liệu thường được truy cập cùng nhau vào phạm vi truy cập phù hợp** để tránh quét toàn cụm hoặc gửi quá nhiều yêu cầu.
2. **Không dồn một lượng dữ liệu hoặc lưu lượng quá lớn vào một khóa/partition** khiến một phần cluster nghẽn trong khi các phần khác còn rảnh.

Ví dụ, phân vùng toàn bộ sự kiện theo **tenantId** giúp đọc dữ liệu một khách hàng thuận tiện. Nhưng nếu một khách hàng lớn chiếm 40% lượng ghi, partition của khách hàng đó có thể thành nút cổ chai. Ngược lại, phân vùng theo **eventId ngẫu nhiên** thường trải đều ghi, nhưng truy vấn “lấy 100 sự kiện mới nhất của khách hàng X” có thể phải đọc nhiều nơi hoặc cần một bảng dẫn xuất.

**Chọn khóa phân vùng là quyết định theo truy vấn và workload, không phải chỉ chọn trường có nhiều giá trị nhất.** Trong bài này, ta phân tích số liệu phân phối khóa, giới hạn truy cập, các kiểu phân vùng, ví dụ Cassandra/DynamoDB/HBase và phương pháp thử nghiệm trước khi chốt thiết kế.

> Các con số giới hạn throughput, latency, kích thước và số lượng bucket bên dưới là **giả định minh họa**. Những hệ NoSQL cụ thể có mô hình logical/physical partition, giới hạn, cơ chế split và tối ưu riêng; không được lấy ví dụ làm thông số mặc định của sản phẩm.

## 1. Phân biệt định danh, khóa chính, khóa phân vùng và khóa sắp xếp

Giả sử mỗi sự kiện của một hệ thống bán hàng có:

~~~json
{
  "eventId": "evt-6ef17",
  "tenantId": "shop-42",
  "orderId": "order-810",
  "eventTime": "2026-11-14T09:05:00Z",
  "type": "ORDER_PAID",
  "amountMinor": 249000
}
~~~

Có ít nhất bốn khái niệm liên quan đến khóa:

| Khái niệm | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Entity/event ID** | Định danh một thực thể hoặc sự kiện, nên ổn định qua retry và thay đổi nơi lưu trữ | eventId |
| **Primary key** | Xác định duy nhất một bản ghi theo hợp đồng database | eventId hoặc tổ hợp tenantId + eventTime + eventId |
| **Partition/shard key** | Quyết định nhóm dữ liệu hoặc đường định tuyến yêu cầu tới partition/shard | tenantId, (tenantId, day), hash(eventId) |
| **Sort/clustering key** | Sắp xếp các bản ghi trong một phạm vi khóa đã xác định | eventTime + eventId |

Ở **Cassandra**, primary key có thể gồm partition key và các clustering columns. Ở **DynamoDB**, bảng có thể dùng partition key đơn hoặc composite primary key gồm partition key + sort key. Với **MongoDB sharding**, shard key và _id/khóa duy nhất của tài liệu không nhất thiết đồng nhất. Ở **HBase**, row key được sắp theo byte và region được chia theo khoảng row key.

Vì vậy, từ **partition** có thể mang hai nghĩa cần tách:

- **Logical partition:** nhóm bản ghi cùng giá trị partition key, như tất cả sự kiện của (shop-42, ngày D).
- **Physical partition/shard/region:** đơn vị mà engine dùng để quản lý và phân bố dữ liệu trên máy; quan hệ giữa logical và physical partition tùy sản phẩm.

Nhiều logical key có thể cùng nằm trên một physical partition, hoặc một hệ có thể có khả năng chia/tái phân phối các phạm vi khóa. Tuy nhiên, không nên giả định rằng engine sẽ **tự chia mọi khóa nóng tùy ý** mà vẫn giữ nguyên hợp đồng truy vấn/ghi.

## 2. “Thiết kế theo truy vấn” bắt đầu từ những đường truy cập

Trước khi quyết định partition key, hãy ghi những yêu cầu thật sự cần phục vụ:

| API hoặc job | Bộ lọc có sẵn | Thứ tự/đầu ra | Tần suất dự kiến | Yêu cầu độ trễ |
| --- | --- | --- | --- | --- |
| Ghi sự kiện | tenantId, eventId, eventTime | Ghi chính xác một sự kiện logic | 12.000 lần/giây ở đỉnh | p99 dưới 200 ms |
| Tra một sự kiện | eventId; đôi khi biết tenantId | Một bản ghi | 3.000 lần/giây | p99 dưới 100 ms |
| Dòng thời gian khách hàng | tenantId | 100 sự kiện mới nhất | 2.000 lần/giây | p99 dưới 250 ms |
| Báo cáo trong ngày | tenantId, khoảng thời gian | Tổng theo loại sự kiện | 200 lần/giây | Có thể mất vài giây |
| Điều tra toàn hệ thống | type, khoảng thời gian | Nhiều tenant, truy vấn không định trước | Hiếm | Có thể chạy batch |

Các số là ví dụ cho bài học. Mục tiêu là **không coi mọi truy vấn quan trọng như nhau**. Một truy vấn batch hiếm có thể chuyển sang data lake hoặc read model khác để giữ cho đường ghi chính và API thời gian thực đơn giản.

### 2.1. Xác định “phạm vi truy cập” của một yêu cầu

Với từng truy vấn, cần hỏi:

- Có biết đầy đủ partition key **trước** khi gửi request không?
- Query cần **point lookup**, một khoảng thời gian, hay phải quét nhiều partition?
- Kết quả được sắp theo trường nào, và database có thể trả theo thứ tự ngay không?
- API phân trang theo keyset/cursor hay offset?
- Một request cần đọc bao nhiêu bản ghi/byte, không chỉ bao nhiêu bản ghi trả về?
- Nếu phải fan-out sang nhiều partition, **bao nhiêu nhánh** và chi phí merge/sort ra sao?
- Có điều kiện quyền truy cập theo tenant/user không? Khóa phân vùng có giúp giới hạn phạm vi dữ liệu cần truy vấn hay không?

Một truy vấn chỉ trả 20 bản ghi nhưng phải đọc hàng triệu bản ghi để tìm chúng vẫn là một thiết kế kém, dù số dòng trong response rất ít.

### 2.2. Workload không chỉ là RPS tổng

Tổng **12.000 writes/s** không cho biết 12.000 khóa khác nhau hay 10.000 lần cập nhật **cùng một khóa**. Cần các phân bố:

- **Request/s theo tenant, user, device, document, partition key.**
- **Số lượng key khác nhau** trong mỗi cửa sổ thời gian.
- **Tỷ trọng của top 1/top 10/top 1% key** và đường cong truy cập lệch (skew).
- **Kích thước bản ghi** trung bình, p95/p99; kích thước hàng/partition tích lũy theo ngày.
- **Tỉ lệ đọc/ghi**, thao tác điều kiện, retry và công việc nền.
- **Burst** trong vài giây, đỉnh duy trì 10 phút, đỉnh duy trì nhiều giờ.
- **Tăng trưởng** theo tenant, theo ngày, theo nhóm sản phẩm.

Nếu dữ liệu lịch sử chưa đủ, ghi rõ giả định rồi chạy nhiều kịch bản thay vì chỉ sinh khóa ngẫu nhiên đều.

## 3. Hai bài toán khác nhau: phân phối dung lượng và phân phối tải

Một partition key có thể tạo các nhóm dữ liệu gần bằng nhau nhưng vẫn gây mất cân bằng lưu lượng.

**Phân phối dung lượng:** Bao nhiêu bản ghi/byte được lưu dưới mỗi logical key? Một tenant có 10 triệu bản ghi, tenant khác chỉ 10 nghìn, thì cùng số tenant không có nghĩa cùng kích thước.

**Phân phối tải:** Có bao nhiêu request/s, byte/s, CPU hoặc thao tác đọc/ghi chạm vào mỗi key? Một khóa nhỏ nhưng bị cập nhật 5.000 lần/giây có thể nóng hơn một khóa lớn chỉ đọc vài lần mỗi giờ.

Ví dụ:

| Tenant | Số sự kiện đang lưu | Ghi/giây ở đỉnh | Đọc/giây ở đỉnh |
| --- | ---: | ---: | ---: |
| shop-01 | 30.000.000 | 4.800 | 1.500 |
| shop-02 | 3.000.000 | 200 | 120 |
| shop-03 | 9.000.000 | 300 | 180 |
| Các tenant khác | 50.000.000 tổng cộng | 6.700 tổng cộng | 4.200 tổng cộng |

Nếu phân vùng theo **tenantId** thuần túy, shop-01 có thể là hot logical partition dù các tenant còn lại trải rất đều. Nếu engine hash tenantId để chọn vị trí, hash tốt chỉ giúp trải **những tenant khác nhau**, không chia nhỏ 4.800 writes/s của **cùng shop-01**.

### 3.1. Công thức ước lượng tải cho khóa nóng

Giả sử có 16 physical partition với khả năng tương đương, tổng 16.000 request/s; **40% request đến đúng một giá trị partition key**, 60% còn lại phân đều. Nếu key nóng nằm trọn tại một partition và không có cơ chế chia nóng đặc biệt, tải ước lượng:

\[
L_{\text{hot}} \approx 0{,}40\times16.000 +
\frac{0{,}60\times16.000}{16}
=7.000\ \text{request/s}
\]

15 partition còn lại nhận khoảng **600 request/s** mỗi partition trong mô hình lý tưởng. Tải trung bình toàn cụm là **1.000 request/s/partition**, nên nhìn chỉ số trung bình có thể bỏ qua partition đang phải phục vụ gấp 7 lần mức trung bình.

Đây chỉ là mô hình minh họa: trong hệ thật, replica, giới hạn theo byte/giây, CPU/IO, hash slot, adaptive splitting và vị trí dữ liệu có thể làm kết quả khác. Ý quan trọng là **skew của tần suất truy cập** phải được đo độc lập với số key.

### 3.2. Cardinality cao chưa chắc phân phối tốt

Một trường **eventId** có hàng tỷ giá trị khác nhau. Nếu mỗi sự kiện được ghi một lần, dùng hash(eventId) có thể trải đều ghi. Nhưng nếu 90% số lần đọc chỉ vào **100 sự kiện mới nhất** của một tenant, việc phân vùng theo eventId vẫn có các điểm đọc nóng theo những giá trị đó, hoặc gây hàng trăm truy vấn để dựng một dòng thời gian.

Một trường **tenantId** có ít giá trị hơn, có vẻ kém phân phối hơn; đổi lại có thể hỗ trợ truy vấn theo tenant rất tốt. Vấn đề là chọn **mức độ chia vừa đủ cho throughput lẫn khả năng truy vấn**, không chỉ tối đa hóa số khóa.

## 4. Hash partition, range partition và hệ quả của khóa

### 4.1. Hash partition

Trong một mô hình hash đơn giản:

~~~text
partition = HASH(partitionKey) mod N
~~~

Hàm hash dùng để minh họa; các engine thực có token ring, hash slot, consistent hashing, adaptive partition hoặc thuật toán khác. Với nhiều partition key **khác nhau** được phân phối tốt, hash có thể giảm lệch vị trí giữa các node.

~~~mermaid
flowchart LR
    A["Các khóa logical khác nhau"] --> H["Hash / token routing"]
    H --> P1["Partition / node A"]
    H --> P2["Partition / node B"]
    H --> P3["Partition / node C"]
    H --> P4["Partition / node D"]
~~~

Nhưng:

- Một hot key thường đi theo cùng một tuyến định vị logic, nên hash **không tự rải yêu cầu đến cùng key**.
- Các lần đọc theo **khoảng partition key** không mặc nhiên liền nhau sau khi hash.
- Nếu dữ liệu được tổ chức theo **sort/clustering key trong một logical partition**, hash ngoài cùng không làm mất thứ tự bên trong phạm vi đó.
- Việc thêm node không nhất thiết chuyển đúng 1/N dữ liệu theo phép modulo; hãy xem cơ chế tái cân bằng thực tế của sản phẩm.

### 4.2. Range partition

Range partition chia các khóa vào những khoảng liên tiếp:

~~~text
Region A: [0000, 2000)
Region B: [2000, 5000)
Region C: [5000, 8000)
Region D: [8000, +∞)
~~~

Ưu điểm: scan theo **khoảng khóa** và truy vấn theo tiền tố có thể tận dụng tính cục bộ của dữ liệu. Nhược điểm: **ID hoặc timestamp tăng liên tục** có thể đẩy mọi ghi mới vào vùng cuối dải, tạo *moving hotspot*. Khi region cuối tách, điểm nóng có thể chuyển theo dải khóa mới nhất.

Điều này thường xuất hiện khi:

- Chọn timestamp hiện tại làm phần đầu row key.
- Chọn sequence tăng làm shard key dạng range.
- Mọi ghi mới của toàn hệ có cùng tiền tố ngày hiện tại.

Thêm bucket/salt hoặc đảo thứ tự thành phần khóa có thể cải thiện phân phối, nhưng thường làm phức tạp truy vấn range. Việc đảo timestamp để xem bản ghi mới trước **không tự giải quyết hotspot**.

### 4.3. Khóa ghép không đồng nghĩa engine hash mọi thành phần như nhau

Ví dụ khóa logic gồm:

~~~text
tenantId + dayBucket + eventTime + eventId
~~~

Khác biệt có thể rất lớn:

- **Cassandra:** partition key có thể là (tenantId, dayBucket), còn eventTime và eventId là clustering columns. Chỉ phần **partition key** đi vào định tuyến hash/token của partition.
- **DynamoDB:** partition key có thể là TENANT#42#DAY#20261114, còn sort key là TS#...#EVENT#...; sort key tổ chức các item cùng partition key.
- **HBase:** cả chuỗi row key tham gia thứ tự byte và định vị region; thứ tự các thành phần trong row key quyết định phạm vi scan/hot range.
- **MongoDB:** shard key có thể gồm nhiều trường hoặc hashed field theo những cấu hình được hỗ trợ; thứ tự và kiểu shard key ảnh hưởng định tuyến query và phân bố dữ liệu.

Không thể nói một key gồm bốn trường sẽ chia tải thành bốn hướng. Phải biết **phần nào thực sự dùng để định tuyến**, phần nào chỉ giúp sắp xếp/uniqueness.

## 5. Giới hạn truy cập: throughput, dung lượng và fan-out

Chọn partition key cần bám vào các **giới hạn thực tế của đơn vị xử lý**, thay vì giả định “NoSQL scale ngang nên không có giới hạn”.

### 5.1. Giới hạn theo kích thước

Một logical partition lớn có thể làm:

- Tăng chi phí đọc và lưu trữ metadata.
- Tốn bộ nhớ/cache khi truy vấn hoặc compaction.
- Khó repair, rebuild, migration và backup.
- Khi xóa/TTL hàng loạt, tạo tombstone hoặc nhiều công việc nền.
- Chạm giới hạn kích thước hoặc giới hạn hiệu năng khuyến nghị của sản phẩm.

Ngược lại, chia quá nhỏ có thể khiến truy vấn cần đọc nhiều partition, tăng request overhead và chi phí quản lý.

### 5.2. Giới hạn theo tốc độ và kiểu thao tác

Hai partition cùng có 10.000 tài liệu có thể cần tài nguyên khác nhau:

- Đọc point lookup của tài liệu 500 byte khác truy vấn range trả 5 MB.
- Ghi có điều kiện hoặc giao dịch cần nhiều phối hợp hơn ghi thường.
- Một yêu cầu ghi có thể cập nhật secondary index hoặc projection.
- Retry sau timeout có thể khuếch đại tải.
- Một khóa có tranh chấp cập nhật khác nhiều khóa chỉ được chèn một lần.

Không nên biến một giới hạn theo **byte/s**, **capacity unit**, **IOPS**, **CPU** hoặc **ghi có điều kiện** thành một con số “request/s tối đa” chung. Đơn vị đo phải đúng với workload.

### 5.3. Giới hạn truy vấn qua nhiều phân vùng

Nếu một API phải đọc 16 bucket:

~~~text
API listEvents(tenantId)
   ├── bucket 00: newest K items
   ├── bucket 01: newest K items
   ├── ...
   └── bucket 15: newest K items
            ↓
       Merge theo thời gian + eventId
            ↓
       Trả K bản ghi toàn tenant
~~~

Tăng số bucket thường làm giảm ghi nóng, nhưng:

- Tăng số nhánh gọi và tổng công việc đọc.
- Tăng rủi ro request chậm do **nhánh chậm nhất**.
- Khó phân trang ổn định vì mỗi bucket có cursor riêng.
- Có thể tiêu tốn nhiều capacity dù chỉ trả K bản ghi cuối.
- Buộc ứng dụng xử lý timeout/retry của từng nhánh và tính nhất quán của snapshot nếu cần.

Giới hạn truy cập vì vậy bao gồm cả **số partition chạm vào mỗi request** chứ không chỉ giới hạn tài nguyên một partition.

### 5.4. Giới hạn phạm vi dữ liệu và phân quyền

Khóa theo tenant có thể giúp truy vấn chỉ đụng dữ liệu một tenant, giảm nguy cơ đọc nhầm phạm vi do lỗi lọc. Nhưng **partition key không phải cơ chế xác thực hoặc phân quyền**. Một API vẫn phải:

- Xác thực người gọi và xác định tenant được phép truy cập.
- Không tin tenantId do client tự khai nếu không đối chiếu quyền.
- Bảo vệ các đường truy cập phụ như query theo eventId, export và admin/reporting.
- Đặt điều kiện tenant thích hợp cả khi đọc, sửa, xóa và khi xử lý event bất đồng bộ.

Khi dùng cùng cụm cho nhiều tenant, cần xét **noisy neighbor**: một tenant nóng làm các tenant khác chậm. Phân vùng, quota/rate limiting theo tenant và cô lập tài nguyên có thể cần kết hợp; khóa tốt không tự bảo đảm cô lập tuyệt đối.

## 6. Ví dụ thiết kế xuyên suốt: dòng thời gian sự kiện theo tenant

Yêu cầu mẫu:

~~~text
12.000 events/s ở đỉnh.
40% sự kiện đến từ 1 tenant lớn.
Tra event theo eventId.
Hiển thị 100 event mới nhất theo tenant.
Lấy event theo tenant trong khoảng thời gian bất kỳ.
Giữ dữ liệu hoạt động 90 ngày.
Cho phép late event và retry.
~~~

Sẽ so sánh bốn phương án.

### 6.1. Phương án A: partition theo tenantId

~~~text
PK = tenantId
SK = eventTime#eventId
~~~

**Ưu điểm:** Truy vấn theo tenant rất tự nhiên; một truy vấn có thể đọc dải thời gian trong một partition logic nếu sản phẩm hỗ trợ. **Nhược điểm:** tenant lớn có thể tạo partition quá lớn và tập trung ghi. Thời gian lưu 90 ngày khiến partition tích lũy thêm dữ liệu mỗi ngày.

Đây thường là phương án hấp dẫn trên giấy vì fan-out nhỏ, nhưng phải chứng minh rằng **tenant lớn nhất** không chạm trần kích thước/tốc độ.

### 6.2. Phương án B: partition theo tenantId + ngày

~~~text
PK = tenantId#YYYYMMDD
SK = eventTime#eventId
~~~

**Ưu điểm:** Chặn tốc độ tăng kích thước của mỗi partition logic theo một bucket thời gian. Truy vấn một ngày có phạm vi rõ. **Nhược điểm:** Ngày hiện tại của tenant nóng vẫn có thể nhận phần lớn ghi; truy vấn qua 90 ngày có thể phải đọc tới 90 partition/ngày tùy chiến lược. Nếu lưu 30 ngày và đọc 90 ngày, cần một lớp lưu trữ hoặc chính sách đọc khác.

Một điểm hay bị bỏ sót: **bucket theo ngày chia dung lượng lịch sử, nhưng không nhất thiết chia tải ghi tức thời**. Tất cả sự kiện của tenant lớn trong ngày hôm nay vẫn cùng một partition key.

### 6.3. Phương án C: tenantId + ngày + bucket hash

~~~text
PK = tenantId#YYYYMMDD#bucket
SK = eventTime#eventId

bucket = stableHash(eventId) % 16
~~~

Mỗi event khác nhau được đưa vào một trong 16 bucket logic của cùng tenant/ngày.

**Ưu điểm:** Nếu eventId phân phối tốt, nhiều sự kiện có thể được ghi tới nhiều logical partition; tenant nóng không còn phụ thuộc vào một partition ngày duy nhất. **Nhược điểm:** Truy vấn tenant/ngày phải quét/hợp nhất 16 bucket, và nếu qua nhiều ngày có thể nhiều hơn; thay đổi số bucket cần quản lý phiên bản và di trú.

**Điều kiện quan trọng:** Dùng **stableHash** đồng nhất giữa service, phiên bản và ngôn ngữ. Không sử dụng hàm hash mặc định của runtime nếu kết quả có thể thay đổi theo phiên bản hoặc tiến trình. Nếu eventId đổi khi retry, cùng event logic có thể bị đưa vào bucket khác và gây trùng.

Không có lý do chọn 16 chỉ vì đó là số đẹp. Số bucket cần suy ra từ lưu lượng tenant nóng, giới hạn ghi thực tế mỗi partition, yêu cầu đọc tối đa và headroom.

### 6.4. Phương án D: partition theo eventId

~~~text
PK = eventId
attributes = tenantId, eventTime, type, amountMinor
~~~

**Ưu điểm:** Point lookup theo eventId và ghi nhiều ID khác nhau dễ phân phối khi định tuyến hash phù hợp. **Nhược điểm:** Dòng thời gian tenant không còn nằm trong một phạm vi đơn; cần một **index/read model** theo tenant/time hoặc truy vấn tốn kém trên nhiều shard.

Một hệ thống có thể chọn **D làm nguồn ghi chính**, còn **C làm read model** cho truy vấn theo tenant. Đổi lại, ứng dụng phải chấp nhận chi phí đồng bộ, đối soát, xử lý bản tin lặp và có thể có độ trễ đọc từ read model.

### 6.5. So sánh bốn phương án

| Tiêu chí | A: tenant | B: tenant + ngày | C: tenant + ngày + bucket | D: eventId |
| --- | --- | --- | --- | --- |
| Ghi của tenant rất nóng | Dễ nóng | Ngày hiện tại vẫn dễ nóng | Thường phân tán tốt hơn với nhiều event khác nhau | Thường trải đều nhiều ID |
| Kích thước partition logic | Tăng lâu dài | Giới hạn theo ngày | Giới hạn theo ngày và bucket | Thường nhỏ nếu mỗi event một key |
| Đọc 100 sự kiện mới nhất một tenant | Ít fan-out | Có thể phải đọc nhiều ngày | Đọc nhiều bucket và ngày, merge | Cần index/read model |
| Đọc eventId nếu không biết tenant | Không trực tiếp | Không trực tiếp | Không trực tiếp | Thuận tiện |
| Truy vấn range theo tenant | Thuận tiện trong phạm vi được hỗ trợ | Fan-out theo ngày | Fan-out theo ngày và bucket | Cần index/read model |
| Độ phức tạp vận hành | Thấp ban đầu, rủi ro hotspot | Trung bình | Cao hơn, có cursor/merge | Có thể cần đồng bộ dữ liệu dẫn xuất |

Phương án nên chọn không phải phương án “nhiều bucket nhất”. Phải xem **tải đọc và tải ghi cùng nhau**, đặc biệt với tenant lớn, query qua nhiều ngày và yêu cầu đọc theo ID.

## 7. Định lượng số bucket thay vì đoán

Giả định:

- Tenant lớn nhất có **4.800 writes/s** ở giờ cao điểm.
- Qua thử nghiệm, một logical partition trong cấu hình đang chọn chỉ nên nhận tối đa **800 writes/s** với SLO p99 đã đặt và đủ headroom.
- EventId của tenant lớn phân bố tương đối đều theo stable hash.

Số bucket tối thiểu theo phép chia tải lý tưởng:

\[
B_{\min} \ge \left\lceil\frac{4.800}{800}\right\rceil=6
\]

Nhưng **6 bucket không phải kết luận triển khai**:

- 800 writes/s là **ngưỡng vận hành thử nghiệm**, không phải giới hạn cố định của Cassandra/DynamoDB/HBase.
- Hash phân bố theo kỳ vọng, vẫn có dao động và hot event/key.
- Cần headroom cho spike, index phụ, retry, compaction và lỗi node.
- Số bucket tăng có thể khiến p99 đọc không đạt yêu cầu.
- Một hot key bị cập nhật lặp sẽ không được chia bằng hash(eventId).

Có thể khảo sát 8, 16 hoặc 32 bucket trong phép thử, rồi chọn cấu hình **nhỏ nhất vẫn đủ headroom**, đồng thời đáp ứng fan-out đọc. Với truy vấn chỉ cần một phần dữ liệu, bucket theo thời gian hoặc theo nhóm truy cập khác có thể hợp lý hơn hash ngẫu nhiên.

### 7.1. Bucket theo thời gian

Chia theo **ngày**, **giờ** hoặc **tháng** là cách khống chế dung lượng và phạm vi query:

~~~text
tenantId#20261114
tenantId#20261114T09
tenantId#202611
~~~

Bucket ngắn giảm dữ liệu tích lũy trong một partition nhưng làm tăng số partition phải đọc cho khoảng thời gian dài. Nếu mọi sự kiện đến **trong giờ hiện tại**, chia theo giờ **không tự phân tán ghi đồng thời**: tất cả vẫn trong một bucket giờ.

### 7.2. Bucket theo hash

~~~text
tenantId#day#(hash(eventId) % B)
~~~

Hash bucket làm nhiều sự kiện khác nhau phân tán ngay trong cùng thời điểm, phù hợp bài toán tenant nóng. Nó giảm tính cục bộ cho dòng thời gian và buộc merge nhiều nhánh.

### 7.3. Kết hợp thời gian và hash

~~~text
tenantId + dayBucket + hashBucket
sort by eventTime DESC + eventId DESC
~~~

Đây là cách cân bằng **kích thước lịch sử** và **tải tức thời**. Nhưng số bucket không nên thay đổi tùy ý trong một namespace khóa duy nhất. Có thể đưa phiên bản cấu trúc vào metadata để những reader biết các bucket cũ và mới cần đọc; nếu không, thay B từ 16 lên 32 sẽ làm hàm định tuyến cho dữ liệu lịch sử thay đổi và gây mất khả năng tìm bản ghi.

## 8. Truy vấn trên nhiều bucket và bài toán phân trang

Giả sử tenant-42 có dữ liệu trong 16 bucket, cần 100 event mới nhất toàn tenant.

Một chiến lược có thể làm:

1. Truy vấn **mỗi bucket** theo thứ tự (eventTime DESC, eventId DESC).
2. Lấy tối đa 100 event mới nhất ở mỗi nhánh.
3. Dùng **k-way merge** theo cùng cặp khóa để chọn 100 event mới nhất toàn tenant.
4. Lưu cursor cho từng bucket để tiếp tục trang sau.

Pseudocode:

~~~text
listLatest(tenantId, day, limit, cursors):
    streams = []
    for bucket in configuredBuckets(tenantId, day):
        stream = queryPartition(
            pk = tenantId + day + bucket,
            order = (eventTime DESC, eventId DESC),
            cursor = cursors[bucket],
            pageSize = limit
        )
        streams.add(stream)

    result, nextCursors = mergeTopK(streams, limit)
    return Page(result, nextCursors)
~~~

Đây là **logic khái niệm**, không phải một triển khai phân trang hoàn chỉnh. Khi merge cần xử lý:

- Trường hợp có nhiều event **cùng eventTime** → eventId là tie-breaker ổn định.
- Event mới xuất hiện giữa các lần tải trang → có thể làm thay đổi thứ tự nếu không dùng snapshot/cutoff.
- Cursor của nhánh nào đã đọc bao nhiêu mẫu và có sample chưa tiêu thụ.
- Kết quả từ một bucket bị timeout → trả lỗi, retry hay trả trang thiếu theo hợp đồng?
- Bản ghi đến muộn với eventTime cũ → có thể xuất hiện ở các trang lịch sử; cần quy tắc nhất quán.

Nếu API cần **dòng thời gian nhất quán với một snapshot** trong suốt nhiều trang, yêu cầu đó có thể vượt khả năng phân trang theo nhiều partition không có snapshot chung; phải thiết kế hợp đồng rõ, ví dụ dùng cutoff thời gian, dữ liệu bất biến hoặc read model có thứ tự phù hợp.

### 8.1. Kết quả ít không đồng nghĩa request rẻ

Nếu cần top 100 từ 16 bucket, đọc 100 mỗi bucket có thể lấy tới **1.600 ứng viên** trước merge. Với 90 ngày × 16 bucket, không thể cứ đọc tất cả bucket/ngày trong một request mà không xem xét chi phí. Có thể:

- Đi từ các ngày mới nhất rồi dừng khi đã đủ kết quả và có thể chứng minh các ngày cũ không chứa dữ liệu mới hơn.
- Thiết kế summary/index theo ngày để tránh mở những ngày không có dữ liệu.
- Tạo read model “latest events by tenant” có giới hạn dung lượng riêng.
- Tách truy vấn thời gian thực khỏi báo cáo lịch sử và dùng hệ phân tích thích hợp.

Độ phức tạp bổ sung chỉ đáng giá nếu giải quyết đúng nút nghẽn đã đo.

## 9. Ví dụ Cassandra: partition theo tenant, ngày và bucket

Trong Cassandra, partition key và clustering columns được khai báo rõ qua CQL:

~~~sql
CREATE TABLE events_by_tenant_bucket (
  tenant_id text,
  event_day date,
  bucket smallint,
  event_time timestamp,
  event_id uuid,
  event_type text,
  amount_minor bigint,
  PRIMARY KEY (
    (tenant_id, event_day, bucket),
    event_time,
    event_id
  )
) WITH CLUSTERING ORDER BY (
  event_time DESC,
  event_id DESC
);
~~~

Trong bảng này:

- **(tenant_id, event_day, bucket)** là **partition key ghép** được dùng để định tuyến.
- **event_time** và **event_id** quyết định thứ tự và phân biệt hàng bên trong cùng partition.
- **bucket** được ứng dụng tính ổn định từ event_id; không tự tăng khi ngày trôi.
- Câu truy vấn hiệu quả cần cung cấp đầy đủ partition key.

~~~sql
SELECT event_time, event_id, event_type, amount_minor
FROM events_by_tenant_bucket
WHERE tenant_id = 'shop-42'
  AND event_day = '2026-11-14'
  AND bucket = 3
LIMIT 100;
~~~

Query trên đọc **một bucket**, không phải 100 sự kiện mới nhất của cả tenant. Ứng dụng phải gọi nhiều bucket và merge khi cần. Với truy vấn theo event_id đơn lẻ mà không biết tenant/day/bucket, cần lookup index/bảng khác.

### 9.1. Chú ý tới kích thước logical partition

Cassandra tổ chức dữ liệu quanh partition; một partition quá lớn hoặc có quá nhiều tombstone có thể ảnh hưởng đọc, compaction, streaming và repair. Không có một con số kích thước tối ưu chung cho mọi cụm; cần đặt giới hạn vận hành theo workload và đo.

Khi dữ liệu hết hạn bằng TTL, tombstone và compaction có thể làm thay đổi chi phí đọc/ghi. Chọn bucket rất dài chỉ vì muốn ít partition có thể tạo nợ vận hành lớn sau vài tháng.

### 9.2. Chú ý tính đúng khi retry

Cùng một event phải giữ **event_id** ổn định nếu ứng dụng muốn nhiều lần gửi được ánh xạ tới cùng khóa logic. Nếu client tạo UUID mới ở mỗi lần retry, các lần gửi sẽ trở thành các event khác nhau dù payload giống nhau.

Ghi lại cùng khóa có thể là idempotent theo một số cách sử dụng, nhưng phải hiểu semantics của update timestamp và các cột khác. Nếu cần **insert-if-not-exists** hoặc bất biến ghi có điều kiện, phải xét công cụ của engine (ví dụ lightweight transaction) và chi phí phối hợp, không xem một INSERT thông thường như giao dịch chống trùng tuyệt đối trong mọi trường hợp.

## 10. Ví dụ DynamoDB: PK/SK và giới hạn theo đường truy cập

Một thiết kế key-value/document với composite primary key có thể dùng:

~~~text
PK = TENANT#shop-42#DAY#20261114#BUCKET#03
SK = TS#2026-11-14T09:05:00.000Z#EVENT#evt-6ef17

Attributes:
  tenantId, eventId, type, amountMinor, payload...
~~~

Query theo **PK** và điều kiện trên **SK** có thể đọc sự kiện của một bucket trong khoảng thời gian. Bất biến eventId duy nhất toàn tenant có thể cần thêm cơ chế cấp ID, điều kiện ghi hoặc bảng tra cứu riêng, tùy schema thực.

Những vấn đề phải đo riêng trong DynamoDB:

- Khóa partition nóng có thể chạm giới hạn capacity/throttling trước khi bảng dùng hết capacity tổng.
- Kích thước item, đơn vị capacity và kiểu đọc nhất quán tác động số lượng thao tác thật sự tiêu thụ.
- **GSI** (global secondary index), nếu có, có partition key và mô hình phân bố riêng; nó có thể nóng dù bảng gốc đã cân bằng.
- Hệ có cơ chế **adaptive capacity**/tối ưu phân bố, nhưng không nên coi đó là bảo đảm sẽ tự chia mọi tổ hợp hot key, especially khi cấu trúc và điều kiện workload không cho phép.
- Tạo nhiều bucket giúp phân tán ghi nhưng làm Query theo tenant phức tạp và tăng số nhánh.

Một mẫu sai thường gặp:

~~~text
PK = DAY#20261114
SK = TENANT#...#EVENT#...
~~~

Nếu tất cả ghi trong ngày đều dùng chung một PK, **độ lớn của ngày hiện tại** và số ghi vào ngày đó có thể tạo hot key. Mẫu này còn bất lợi nếu truy vấn chính luôn theo tenant. Đừng bắt đầu từ “tôi cần dữ liệu theo ngày” rồi bỏ quên phân bố tenants và lượng ghi hiện tại.

**Lưu ý về quyền:** cấu trúc PK chứa tenantId không tự xác thực tenant. Nếu API nhận TENANT#... từ client, ứng dụng vẫn phải đối chiếu người gọi với tenant có quyền.

## 11. Ví dụ HBase: row key dạng range và salting

HBase sắp row key theo thứ tự byte và chia dữ liệu thành region theo dải. Với row key:

~~~text
tenantId#day#reverseTime#eventId
~~~

các sự kiện cùng tenant/ngày nằm cạnh nhau về thứ tự, thuận tiện cho scan. Nhưng những ghi mới của một tenant nóng có thể dồn vào một dải region.

Một cách phân tán:

~~~text
bucket#tenantId#day#reverseTime#eventId
bucket = stableHash(eventId) % 16
~~~

Khi đó các bucket khác nhau có prefix khác nhau, tạo khả năng phân phối giữa nhiều dải key/region. Cần nhớ:

- Prefix bucket phải được encode ổn định và có độ rộng phù hợp khi sắp theo byte.
- Nếu chọn bucket bằng hash(tenantId), tất cả sự kiện cùng tenant vẫn cùng prefix bucket; không giải quyết hot tenant.
- Dùng reverseTime để scan mới nhất trước chỉ hữu ích nếu encoder bảo toàn thứ tự mong muốn.
- Một scan theo tenant cần nhiều dải bucket và bước merge; HBase không tự biến nhiều scan thành một global sorted result.
- Region split/balancing có thể cải thiện phân phối, nhưng không thay thế phân tích moving hotspot.

Ở HBase, việc đặt thời gian vào **đầu** row key có thể thuận lợi cho truy vấn theo thời gian toàn hệ nhưng gây ghi dồn vào hiện tại. Đặt tenant vào đầu thường thuận lợi cho quét theo tenant. Cần chọn thứ tự các thành phần theo **đường đọc chính** và workload.

## 12. Ví dụ MongoDB sharding: shard key và query routing

Trong một collection MongoDB được sharding, **shard key** ảnh hưởng cách dữ liệu được phân vùng và cách router định tuyến truy vấn tới shard.

Các phương án cần khảo sát:

~~~text
Shard key theo tenantId (range hoặc hashed, nếu cấu hình hỗ trợ)
  + Query có tenantId: thường có cơ hội targeted routing
  + Tenant rất lớn/nóng: có thể tạo tập trung tải hoặc khó chia đúng yêu cầu

Shard key dựa trên eventId/hash(eventId)
  + Nhiều eventId khác nhau: có thể trải đều ghi
  + Query dòng thời gian tenant: thiếu khóa định tuyến phù hợp,
    có nguy cơ scatter-gather nếu không có cấu trúc truy cập khác

Shard key ghép tenantId + thành phần chia phù hợp
  + Cân bằng phạm vi truy vấn tenant với khả năng phân tán
  + Cần đánh giá tính đơn điệu, khả năng chia chunk, kiểu hash/range
~~~

Trong MongoDB, tính hữu ích của một shard key còn liên quan tới **cardinality, frequency, tính đơn điệu của giá trị khóa và cách phân bố truy vấn**. Không tự suy luận một compound shard key sẽ phân bố đều chỉ vì nó có nhiều trường. Quy tắc hỗ trợ hashed/compound, unique index, resharding và routing tùy phiên bản/thiết lập; cần xác nhận với cấu hình thật trước khi chọn.

Đặc biệt, **index có thể giúp lọc nhanh bên trong một shard nhưng không tự biến truy vấn thiếu shard key thành targeted query**. Nên đo routing fan-out và số shard được chạm, không chỉ xem query plan ở một node.

## 13. Khóa phân vùng có thể tác động tới những index khác

Một thiết kế bảng chính phân phối tốt chưa chắc hệ thống ghi tốt nếu mỗi event còn cập nhật:

- **Global secondary index** theo tenant/day.
- **Search index** theo loại sự kiện.
- **Counter/tổng hợp** theo tenant hoặc theo ngày.
- **Bảng đọc** chứa 100 event mới nhất.
- **Queue/outbox** phát thay đổi cho consumer.

Ví dụ primary table dùng **eventId** phân tán đẹp, nhưng GSI có partition key **DAY#20261114** cho tất cả event. Đường ghi có thể bị nghẽn ở GSI. Cần mô tả:

~~~text
Mỗi event
  ├── Ghi primary partition theo eventId
  ├── Cập nhật read model theo tenant + bucket
  ├── Cập nhật tổng hợp theo tenant + time bucket
  └── Gửi event vào stream cho hệ analytics
~~~

Một thao tác ghi của API có thể tạo **nhiều thao tác dữ liệu**. Vì thế việc chọn khóa phân vùng phải xét **toàn bộ đường ghi** và các giới hạn nhất quán/độ trễ của bản dẫn xuất.

Nếu tạo một counter theo tenantId, tenant nóng có thể dồn mọi cập nhật về một document/cell/counter dù bảng sự kiện đã được bucket. Có thể cần shard counter, batch aggregation hoặc stream aggregation; việc đổi khóa chỉ ở bảng chính không sửa được nút nghẽn phụ.

## 14. Cách đối phó các kiểu điểm nóng khác nhau

| Kiểu điểm nóng | Dấu hiệu | Giải pháp cần cân nhắc | Đánh đổi |
| --- | --- | --- | --- |
| **Hot tenant** | Một tenant chiếm phần lớn writes/s | Tenant + hash bucket, quota, tách tenant lớn | Fan-out đọc, nhiều partition |
| **Hot key read** | Một ID được đọc lặp liên tục | Cache, replica/read scaling tùy tính nhất quán, request coalescing | Độ mới, invalidation, fallback |
| **Hot key write** | Nhiều writer cập nhật cùng một item | Thay đơn vị ghi, shard counter/aggregation, queue/serialize | Nhất quán và độ trễ tổng hợp |
| **Moving hot spot** | Mọi key mới vào vùng tăng/giảm cuối dải | Hash/salt prefix, pre-split nếu hợp lý, thay cách chia | Giảm locality của scan range |
| **Oversized partition** | Một khóa tích lũy dữ liệu rất dài | Time bucketing, hash bucketing, retention | Truy vấn nhiều bucket |
| **Hot index phụ** | Bảng chính ổn nhưng GSI/projection chậm | Chia key của index, thiết kế read model khác | Chi phí đồng bộ, migration |
| **Hot time bucket** | Mọi ghi dùng một ngày/giờ hiện tại | Thêm tenant/nguồn/hash bucket | Truy vấn tổng hợp cần merge |
| **Noisy neighbor** | Một tenant làm tenant khác tăng p99 | Quota, admission control, tài nguyên/tier riêng | Chi phí cô lập và quản trị |

**Hot read** và **hot write** không giống nhau. Cache thường giúp đọc lặp, nhưng không giải quyết tranh chấp khi nhiều request muốn **ghi vào cùng một bản ghi có bất biến nghiệp vụ**. Không có một mẹo partition key nào bảo đảm hai giao dịch cập nhật cùng tài nguyên vừa độc lập hoàn toàn vừa nhất quán mạnh mà không phối hợp.

## 15. Dữ liệu thay đổi theo thời gian và khóa có tính ổn định

Một partition key tốt nên được chọn từ **thuộc tính ổn định** hoặc có kế hoạch xử lý khi thuộc tính thay đổi. Ví dụ:

~~~text
PK = customerRegion
~~~

Nếu khách hàng chuyển từ vùng A sang B, tất cả dữ liệu lịch sử có cần chuyển partition không? Nếu không, truy vấn “mọi đơn của khách hàng” phải biết cả region cũ và mới. Nếu có, migration có thể tốn kém và ảnh hưởng đường ghi.

Các trường dễ thay đổi gồm:

- Region, trạng thái, loại khách hàng, nhóm phân quyền.
- Danh mục sản phẩm, người quản lý, tuyến vận hành.
- Thuộc tính được chuẩn hóa lại từ dữ liệu người dùng.

Ngược lại, **tenantId** hoặc **eventId** thường ổn định hơn. Nếu phải thay partition key, tốt nhất giữ **entity ID độc lập** và quản lý vị trí lưu trữ qua cấu trúc định tuyến hoặc một kế hoạch chuyển đổi có phiên bản.

### 15.1. Sự kiện đến muộn

Giả sử event đo lúc 23:58 ngày 14 nhưng tới server lúc 00:05 ngày 15. Nếu **day bucket** lấy từ eventTime, nó nằm ở partition ngày 14. Nếu lấy từ ingestionTime, nó nằm ở ngày 15. Hai lựa chọn trả lời hai bài toán khác nhau.

Trước khi chọn khóa theo thời gian, xác định:

- Báo cáo cần theo **ngày xảy ra sự kiện** hay **ngày nhận**?
- Có yêu cầu truy vấn “mọi event nhận trong ngày” không?
- Retention tính từ timestamp nào?
- Một sự kiện bị gửi lại có giữ cùng bucket không?
- Nếu eventTime từ client sai hoặc bị can thiệp, key và việc xóa dữ liệu có bị ảnh hưởng không?

Thường nên lưu cả **eventTime** và **serverAcceptedAt**. Việc chọn trường nào vào partition key phải dựa trên truy vấn và nguồn thời gian có thẩm quyền, không mặc định timestamp nào “đúng hơn”.

## 16. Thay đổi partition key: không phải đổi tên một field

Khi hệ thống đã có dữ liệu, chuyển từ **PK = tenantId** sang **PK = tenantId#day#bucket** là một thay đổi lớn:

1. Xác định dữ liệu cũ ở đâu và cách tính khóa mới cho từng bản ghi.
2. Phát hành reader biết đọc phiên bản cũ và mới trong thời kỳ chuyển đổi.
3. Ghi mới theo cấu trúc mới; nếu dual-write, phải quản lý idempotency và tính đúng giữa hai đường.
4. Backfill dữ liệu cũ theo batch, có checkpoint, rate limit và đối soát số lượng/checksum.
5. Kiểm tra kết quả truy vấn, sắp xếp, phân trang, quyền tenant và tính nhất quán khi backfill đang chạy.
6. Chuyển traffic đọc theo tỷ lệ có kiểm soát rồi ngừng đường ghi cũ.
7. Chỉ dọn dữ liệu cũ sau khi chứng minh không còn reader/consumer phụ thuộc.

Một số sản phẩm có công cụ đổi shard key/resharding, nhưng chi phí, giới hạn và cách hoạt động khác nhau. Không giả định rằng việc chọn sai khóa có thể sửa bằng một lệnh ALTER TABLE đơn giản mà không cần di trú dữ liệu.

### 16.1. Version hóa quy tắc tính bucket

Ví dụ:

~~~text
V1: bucket = stableHash(eventId) % 8
V2: bucket = stableHash(eventId) % 32
~~~

Nếu reader chỉ dùng V2, nó có thể **không tìm thấy** event cũ của V1. Một số cách xử lý:

- Giữ quy tắc theo khoảng ngày/phiên bản và biết dữ liệu nào thuộc V1/V2.
- Giữ metadata chuyển đổi để reader thử đúng khóa cũ hoặc khóa mới.
- Backfill/move dữ liệu sang không gian khóa mới rồi chuyển reader.
- Dùng bảng tra cứu eventId → vị trí partition khi point lookup là yêu cầu quan trọng.

Không dùng một biến môi trường **BUCKET_COUNT** thay đổi đột ngột ở mọi service mà không có kế hoạch đọc dữ liệu cũ.

## 17. Thử nghiệm khóa phân vùng bằng workload đại diện

Chọn khóa chỉ dựa trên giấy rất rủi ro. Một benchmark hữu ích phải tái hiện **phân bố tenant, thời gian, kích thước và các đường truy vấn**, không chỉ chạy random inserts trên khóa đều.

### 17.1. Đặc tả một phép thử

~~~yaml
scenario: partition-key-selection
dataset:
  activeTenants: 10000
  totalEvents: 100000000
  avgPayloadBytes: 1200
  largeEventPercent: 5
workload:
  peakWritesPerSecond: 12000
  readsPerSecond: 5000
  hottestTenantWriteSharePercent: 40
  oneHotEventReadSharePercent: 10
  lateEventsPercent: 8
  retriesPercent: 2
queries:
  - pointLookupByEventId
  - latest100ByTenant
  - listByTenantAndTimeRange
  - aggregateByTenantAndDay
candidates:
  - tenantOnly
  - tenantDay
  - tenantDayHashBucket8
  - tenantDayHashBucket16
  - eventIdPlusReadModel
measure:
  - "offered / achieved RPS"
  - "p50/p95/p99 API và database latency"
  - "error rate, timeout, retry, throttling"
  - "hottest logical/physical partition load"
  - "partition bytes/items, compaction/index pressure"
  - "fan-out count, scanned bytes, pages per request"
  - "CPU, memory, disk I/O, network, cost"
  - "correctness: duplicate, stale result, lost update"
~~~

Các số chỉ để xây **kịch bản mẫu**, không phải cấu hình chạy trực tiếp. Cần mô tả topology, replica, consistency level, index phụ, phiên bản database/driver, loại máy/disk, network và bộ phát tải.

### 17.2. Ma trận kịch bản

| Kịch bản | Thay đổi | Cần quan sát |
| --- | --- | --- |
| **Uniform** | Tenant/request phân bố gần đều | Baseline, chi phí khi không có điểm nóng |
| **Skew** | 40% ghi đến một tenant | Hot partition, p99, throttling |
| **Hot item** | Một event/item bị đọc hoặc ghi lặp | Hash bucket có giúp hay không? |
| **Burst** | Tải tăng gấp 3 trong một phút | Queue, khả năng hấp thụ spike, fallback |
| **Data growth** | Tăng từ 1× lên 10× số event | Partition size, latency range, maintenance |
| **Multi-day** | Query qua 1/7/90 ngày | Fan-out, merge, scan bytes |
| **Bucket variants** | So sánh B=8/16/32 | Đánh đổi ghi cân bằng với đọc nhiều nhánh |
| **Secondary index** | Bật/tắt index cần thiết | Nút nghẽn chuyển sang index phụ không? |
| **TTL/delete** | Dữ liệu hết hạn/được xóa dồn | Compaction, tombstone, storage lag |
| **Failure/rebalance** | Lỗi node hoặc thay topology trong môi trường thử | Headroom và p99 khi mất năng lực |
| **Late/retry** | Sự kiện đến muộn, gửi trùng | Tìm đúng bucket và không tạo trùng logic |

Đo cả **offered throughput** lẫn **achieved throughput**. Nếu bộ phát tải giảm tốc khi database chậm, số request ít đi có thể khiến p99 trông tốt giả tạo. Khi hệ thống timeout, phải tính cả request thất bại chứ không chỉ các thao tác thành công.

### 17.3. Kết quả minh họa và quyết định

Giả sử một phép thử có tải đỉnh **12.000 writes/s**, trong đó 40% từ shop-01:

| Phương án | p99 ghi | Tải logical partition nóng nhất | p99 truy vấn latest100 | Kết luận sơ bộ |
| --- | ---: | ---: | ---: | --- |
| tenantOnly | 910 ms | 4.800 writes/s | 65 ms | Đọc tốt, nhưng ghi nóng nghiêm trọng |
| tenantDay | 650 ms | 4.800 writes/s trong ngày hiện tại | 85 ms | Giảm kích thước lịch sử, chưa hết nóng ghi |
| tenantDayBucket8 | 220 ms | khoảng 600 writes/s ở các bucket của shop-01 | 170 ms | Ghi cải thiện, đọc tốn fan-out |
| tenantDayBucket16 | 155 ms | khoảng 300 writes/s ở các bucket của shop-01 | 260 ms | Ghi tốt hơn nhưng đọc gần ngưỡng |
| eventId + read model | 145 ms | Nhiều key khác nhau | 110 ms nếu read model theo kịp | Tốn pipeline; cần đo lag và đối soát |

**Tất cả số liệu là giả định để luyện phân tích**, không phải benchmark Cassandra/DynamoDB. Không thể kết luận bucket16 là tốt nhất vì p99 ghi thấp nếu SLO đọc latest100 yêu cầu dưới 200 ms. Cũng không thể kết luận read model tốt nhất nếu nghiệp vụ cần đọc đồng bộ ngay sau ghi nhưng projection có độ trễ vượt hợp đồng.

Quyết định cần ghi rõ **SLO, mức tải, giả định skew, phương án đã thử, giới hạn còn lại và điều kiện phải kiểm chứng lại**.

## 18. Một số quy tắc thực hành

1. **Bắt đầu từ top truy vấn và điều kiện lọc thật.** Nếu một query không có partition key, dự tính rõ chỉ mục, fan-out hoặc read model sẽ phục vụ nó.
2. **Đo top hot keys, không chỉ đếm số giá trị duy nhất.** Cardinality cao không đảm bảo tải đều.
3. **Đánh giá kích thước và tải riêng.** Một key có dữ liệu nhỏ vẫn có thể rất nóng; một key lớn chưa chắc hot.
4. **Đừng mong time bucket tự chia tải hiện tại.** Nếu mọi ghi đều vào “hôm nay”, cần xem hash bucket hoặc cơ chế khác.
5. **Đừng hash mọi thứ vô điều kiện.** Hash có thể làm mất locality của các query range quan trọng.
6. **Nếu bucketing, thiết kế đường đọc và cursor cùng lúc.** Một chiến lược chỉ tối ưu ghi thường chuyển chi phí sang đọc.
7. **Xem cả secondary index và tổng hợp dẫn xuất.** Hotspot có thể nằm ở đường cập nhật phụ.
8. **Giữ ID thực thể ổn định và độc lập với cấu trúc lưu trữ khi cần.** Điều này giúp migration và idempotency.
9. **Không xem partition key là cơ chế phân quyền.** TenantId trong khóa chỉ là thành phần định tuyến; phải kiểm tra quyền thực sự.
10. **Kiểm chứng giới hạn trên cấu hình sản phẩm cụ thể.** Số node, consistency, item size, index và storage engine quyết định năng lực thực tế.
11. **Dự trù sự kiện đến muộn và retry.** Key phải được tính nhất quán từ dữ liệu có thẩm quyền.
12. **Để headroom và quy trình đổi khóa.** Một thiết kế đạt tại tải hôm nay vẫn cần quan sát và có kế hoạch khi top tenant tăng gấp nhiều lần.

## 19. Bài tập thực hành: lựa chọn khóa cho ứng dụng đặt xe

Một dịch vụ đặt xe có:

- 80.000 tài xế và 4.000.000 chuyến lịch sử.
- Dữ liệu chuyến tăng 100.000 chuyến/ngày.
- Một thành phố lớn phát sinh 65% yêu cầu đặt xe tại giờ cao điểm.
- Khách hàng cần **lịch sử 20 chuyến mới nhất của mình**, tài xế cần **lịch sử chuyến theo ngày**.
- Bộ phận vận hành cần truy vấn **các chuyến đang hoạt động trong một khu vực**, độ mới dưới vài giây.
- Tranh chấp điều phối không được phân công cùng một tài xế cho hai chuyến cùng lúc.
- Trong đợt khuyến mãi, lưu lượng một khu vực có thể tăng gấp 5 lần.

Hãy khảo sát các phương án:

~~~text
A. PK = cityId
   SK = createdAt#rideId

B. PK = riderId
   SK = createdAt#rideId

C. PK = driverId#day
   SK = createdAt#rideId

D. PK = cityId#day#bucket
   SK = createdAt#rideId
   bucket = stableHash(rideId) % 16

E. PK = rideId
   + các read model theo rider/driver/active-city
~~~

### Yêu cầu 1 — Phân phối và giới hạn

Với mỗi phương án, hãy dự đoán:

- Partition nào có thể lớn nhất và nóng nhất?
- Thông tin nào cần đo thêm để xác định quy mô vấn đề?
- Nếu 65% requests đến một cityId, hash(cityId) có làm tải của thành phố đó tự phân phối trên nhiều node không?
- Bucket theo day có chia tải của thành phố trong giờ hiện tại không?
- Khi chọn D, một truy vấn theo city/ngày cần bao nhiêu nhánh và merge như thế nào?

### Yêu cầu 2 — Các đường truy vấn

Đề xuất bảng/đường truy cập phục vụ:

- **20 chuyến mới nhất của một rider**.
- **Lịch sử một driver trong 7 ngày**.
- **Chuyến đang hoạt động theo vùng**, yêu cầu độ mới dưới vài giây.
- **Tìm một chuyến theo rideId**.

Giải thích tại sao một bảng duy nhất có partition key tối ưu cho một truy vấn không nhất thiết tối ưu cho ba truy vấn còn lại. Nếu cần nhiều read model, hãy ghi rõ nguồn chính, độ trễ đồng bộ và xử lý event lặp.

### Yêu cầu 3 — Tính đúng khi cập nhật đồng thời

Giả sử hai yêu cầu cùng cố gắng gán một tài xế đang rảnh cho hai chuyến. Vì sao việc chia dữ liệu chuyến thành nhiều partition **không giải quyết bất biến tài xế chỉ nhận một chuyến hoạt động**? Hãy đề xuất một điểm quyết định có điều kiện nguyên tử theo driver hoặc một cơ chế phối hợp khác, kèm xử lý retry và thất bại.

### Yêu cầu 4 — Đặt thử nghiệm

Lập ít nhất bốn kịch bản: phân bố đều, thành phố nóng, tải gấp 5 lần, và một tài xế/rideId bị cập nhật lặp. Đo **p99 đọc/ghi, hot partition, số nhánh đọc, lỗi, retry, dung lượng partition và tính đúng khi tranh chấp**.

### Gợi ý hướng giải

Không nên lưu tất cả chuyến dưới **cityId** nếu city nóng chiếm phần lớn ghi. Một bảng chính theo **rideId** có thể giúp tra cứu chuyến và phân tán tạo mới, còn các **read model** phục vụ rider/driver theo thời gian và active rides theo khu vực. Nếu bảng đọc theo city cần ghi rất lớn, phải cân nhắc **city + time bucket + hash bucket**, rồi đo chi phí fan-out. Quyết định gán tài xế phải có **đường ghi nguyên tử/nhất quán theo tài xế hoặc dịch vụ điều phối có thẩm quyền**, không được suy ra từ việc các bản ghi chuyến đã được phân tán.

**Kết luận:** Khóa phân vùng tốt không đơn giản là khóa phân biệt nhiều bản ghi. Nó là lựa chọn cân bằng giữa **tính chọn lọc của truy vấn**, **độ lệch phân bố khóa**, **kích thước và throughput mỗi partition**, **số nhánh phải đọc**, **các bất biến nghiệp vụ** và **chi phí thay đổi về sau**. Hãy đưa tất cả điều này vào hồ sơ workload và phép thử có thể bác bỏ giả định trước khi khóa thiết kế NoSQL.
