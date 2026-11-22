# NetworkTopologyStrategy và bố trí bản sao theo datacenter/rack

> **Chương:** Token và sao chép  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — tìm hiểu kiến trúc phân tán và mô hình wide-column của Apache Cassandra, từ khóa phân vùng và thiết kế bảng theo truy vấn đến tính nhất quán đọc/ghi, replication, repair và kết nối Java.

Trong Cassandra, **replication factor (RF)** trả lời “mỗi partition cần bao nhiêu bản sao?”, còn **replication strategy** quyết định “những bản sao ấy nằm ở đâu?”. Nếu chỉ đếm node mà bỏ qua vị trí vật lý của chúng, ba bản sao có thể cùng mất khi một rack, vùng hạ tầng hoặc datacenter gặp sự cố. `NetworkTopologyStrategy` (NTS) giải quyết bài toán đặt replica theo **datacenter** và cố gắng phân tán chúng giữa các **rack** bên trong datacenter.

Đây là chiến lược nên dùng cho keyspace phục vụ production, kể cả khi cluster mới có một datacenter. Bài học sử dụng token ring, ví dụ CQL và một cluster hai datacenter để giải thích thuật toán và kiểm chứng bằng công cụ vận hành.

**Mục tiêu học tập**

1. Giải thích vai trò của partition key, token, datacenter, rack, snitch và replication factor trong việc chọn replica.
2. Dự đoán cách NTS phân phối replica theo RF của từng datacenter và nhận ra giới hạn khi số rack/node không đủ.
3. Tạo keyspace bằng CQL, xác minh endpoints với `nodetool` và kiểm tra tình trạng replica theo topology.
4. Chọn `LOCAL_ONE`, `LOCAL_QUORUM`, `QUORUM` hoặc `EACH_QUORUM` phù hợp với yêu cầu đọc/ghi và kịch bản lỗi.
5. Lập kế hoạch thay đổi RF, mở rộng DC, thực hiện streaming/repair và kết nối ứng dụng Java theo DC cục bộ.

## 1. Những khái niệm cần tách bạch

### 1.1. Token ring quyết định vị trí logic, NTS quyết định số bản sao theo DC

Cassandra phân tán dữ liệu theo **partition key**. Với ví dụ:

~~~sql
CREATE TABLE readings_by_device (
    device_id uuid,
    observed_at timestamp,
    temperature double,
    PRIMARY KEY ((device_id), observed_at)
) WITH CLUSTERING ORDER BY (observed_at DESC);
~~~

`device_id` là partition key, `observed_at` là clustering column. Cassandra áp dụng partitioner (thông dụng là `Murmur3Partitioner`) để tạo **token** từ `device_id`. Hai hàng của cùng thiết bị nằm trong cùng partition và cùng có một tập replica; thứ tự `observed_at` không làm thay đổi vị trí token.

Token ring cho Cassandra biết những node vật lý nào đứng kế tiếp tại các vị trí trên vòng. Với **virtual nodes (vnodes)**, mỗi node vật lý có thể sở hữu nhiều khoảng token; vì vậy “đi tới token tiếp theo” không nhất thiết là “đi tới node vật lý mới”. Một node không thể được tính hai lần để đáp ứng RF.

| Khái niệm | Ý nghĩa trong NTS | Phạm vi |
|---|---|---|
| Partition key và token | Xác định vị trí bắt đầu khi tìm replica trên ring | Theo partition |
| Node vật lý | Nơi lưu một replica cụ thể | Theo cluster |
| Datacenter (DC) | Miền phân phối replica được khai báo trong keyspace | Theo topology/snitch |
| Rack | Miền lỗi nhỏ hơn bên trong DC; NTS ưu tiên trải replica qua rack khác nhau | Theo topology/snitch |
| RF của mỗi DC | Số node replica mong muốn trong DC tương ứng | Theo keyspace |
| Consistency level (CL) | Số/phạm vi replica cần xác nhận cho một thao tác | Theo yêu cầu đọc/ghi |

**Không đồng nhất RF với CL:** RF là mục tiêu bố trí bản sao; CL là điều kiện phản hồi của thao tác. Keyspace có thể RF = 3 ở mỗi DC nhưng một lệnh ghi `LOCAL_QUORUM` thường chỉ cần xác nhận từ hai replica **trong DC cục bộ**.

### 1.2. Snitch: Cassandra biết node thuộc DC/rack nào từ đâu?

NTS dựa vào thông tin topology do **endpoint snitch** của cluster cung cấp. Snitch ánh xạ địa chỉ node vào datacenter và rack. Một triển khai thường gặp là `GossipingPropertyFileSnitch` với khai báo dạng:

~~~properties
dc=dc1
rack=rack1
~~~

Đây chỉ là **minh họa cấu hình của một node**, không phải file cần sửa khi chạy truy vấn CQL. Mỗi node có giá trị tương ứng với vị trí triển khai của chính nó. Tên `dc1`, `dc2` hoặc `rack1` là định danh logic; chúng cần phản ánh đúng **miền lỗi vật lý** như availability zone/rack thực tế.

Kiểm tra topology mà Cassandra đang nhìn thấy:

~~~bash
nodetool status
~~~

Lệnh thường nhóm node theo `Datacenter` và có cột `Rack`, `Status/State` (ví dụ `UN` là Up/Normal), `Tokens` và dung lượng. Việc cùng ghi “rack1” ở hai DC **không** có nghĩa là một rack vật lý chung; NTS đánh giá rack trong phạm vi từng DC. Ngược lại, gán ba node trên cùng một rack vật lý thành ba tên rack khác nhau tạo cảm giác phân tán giả và không mang lại khả năng chống lỗi thực tế.

> **Cẩn trọng:** Không đổi tên datacenter/rack hoặc snitch tùy tiện trên cluster đang hoạt động. Những thay đổi topology có thể tác động đến tập replica và đòi hỏi quy trình vận hành riêng theo phiên bản Cassandra.

## 2. Thuật toán chọn replica của NetworkTopologyStrategy

### 2.1. Ý tưởng thuật toán

Với keyspace:

~~~sql
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 2
}
~~~

mỗi partition cần **ba replica trên ba node khác nhau ở `dc1`** và **hai replica trên hai node khác nhau ở `dc2`**, nếu có đủ node đáp ứng. Tổng cộng **năm replica**, không phải RF = 3 cho toàn cluster. Datacenter không khai báo trong map không được NTS yêu cầu lưu replica của keyspace này.

Nhìn ở mức khái niệm, NTS:

1. Tính token từ partition key và tìm vị trí bắt đầu trên token ring.
2. Duyệt các node ứng viên theo chiều tăng token, có quay vòng về đầu ring.
3. Với **mỗi DC được khai báo**, chọn node cho tới khi đạt RF của DC đó; một node vật lý chỉ tính một replica cho partition.
4. Trong từng DC, **ưu tiên những rack chưa có replica** trước khi lấy thêm node ở rack đã dùng, miễn topology cho phép.
5. Hoàn tất khi đã đáp ứng RF được khai báo cho từng DC hoặc đã đi qua các node phù hợp mà vẫn thiếu.

Điểm khác `SimpleStrategy`: NTS có chỉ tiêu **riêng theo datacenter** và có **ý thức về rack**. NTS không thể tạo ra miền lỗi độc lập nếu hạ tầng không cung cấp chúng; nó cũng không ép mỗi replica nằm trên một rack riêng khi `RF > số rack có node phù hợp`.

### 2.2. Ví dụ ring với hai datacenter

Để nhìn rõ cách chọn replica, giả sử sáu node, **mỗi node chỉ có một token**:

| Node | Token minh họa | Datacenter | Rack |
|---|---:|---|---|
| A | 10 | `dc1` | `r1` |
| B | 20 | `dc2` | `r1` |
| C | 30 | `dc1` | `r2` |
| D | 40 | `dc2` | `r2` |
| E | 50 | `dc1` | `r3` |
| F | 60 | `dc2` | `r3` |

~~~mermaid
flowchart LR
    A["A · 10 · dc1/r1"] --> B["B · 20 · dc2/r1"]
    B --> C["C · 30 · dc1/r2"]
    C --> D["D · 40 · dc2/r2"]
    D --> E["E · 50 · dc1/r3"]
    E --> F["F · 60 · dc2/r3"]
    F --> A
~~~

Với RF `dc1: 3, dc2: 2`:

| Token của partition | Các node được gặp khi đi theo ring | Replica trong `dc1` | Replica trong `dc2` |
|---:|---|---|---|
| 25 | C → D → E → F → A → B | C (`r2`), E (`r3`), A (`r1`) | D (`r2`), F (`r3`) |
| 55 | F → A → B → C → D → E | A (`r1`), C (`r2`), E (`r3`) | F (`r3`), B (`r1`) |

Một partition có token 25 bắt đầu ở node C, nhưng **C không phải bản sao duy nhất**. Tập replica còn bao gồm hai node khác trong `dc1` và hai node trong `dc2`. Các node của hai DC không nhất thiết nằm thành hai đoạn liền nhau trên vòng token.

**Phạm vi của ví dụ:** những token 10/20/... chỉ là số giả định để luyện suy luận; token Murmur3 thực tế thuộc miền số nguyên 64-bit có dấu, còn hệ thống sản xuất thường có vnodes nên thứ tự ứng viên có thể khác.

### 2.3. Vì sao RF = 3 chưa chắc chịu được lỗi một rack?

Giả sử trong `dc1` chỉ có hai rack với ba node:

| Node | DC | Rack |
|---|---|---|
| A | `dc1` | `r1` |
| C | `dc1` | `r1` |
| E | `dc1` | `r2` |

NTS vẫn có thể đặt RF = 3 trên **A, C, E**, tức có hai replica cùng rack `r1`. Khi `r1` hỏng, trong DC này chỉ còn **một** replica, không đủ `LOCAL_QUORUM = 2`. Với RF = 3 và yêu cầu chịu được lỗi bất kỳ một rack mà vẫn đạt local quorum, bố trí **ít nhất ba rack độc lập**, mỗi rack có node chứa replica cho partition, là một thiết kế thuận lợi.

NTS ưu tiên khác rack nhưng không thể đảm bảo khả năng chịu lỗi nếu thiếu node/rack, thông tin rack sai hoặc nhiều rack logic nằm trong cùng một vùng mất điện/mạng. Việc “đặt replica khác rack” là kết quả của **cả chiến lược lẫn cách triển khai hạ tầng**.

## 3. Khai báo NTS bằng CQL và kiểm tra topology

### 3.1. Yêu cầu môi trường

Phòng thực hành đề xuất có **hai datacenter, mỗi DC ba node đang hoạt động**, bố trí theo ba rack riêng trong từng DC nếu có thể. Có quyền chạy `cqlsh` và `nodetool`. Không chạy thử nghiệm tắt node, thay RF hoặc đổi snitch trên cluster production.

Kiểm tra từ một node:

~~~bash
nodetool status
~~~

Ghi lại tên DC **chính xác** (có phân biệt chữ hoa/thường), rack và trạng thái từng node. Các tên dùng trong CQL bên dưới giả định snitch báo đúng `dc1` và `dc2`. Nếu cluster báo tên khác, thay **cả khóa map replication** cho khớp tên thật.

### 3.2. Tạo keyspace, bảng và dữ liệu mẫu

Trong `cqlsh`, cấu hình mỗi DC ba replica:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_nts
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;

USE lab_nts;

CREATE TABLE IF NOT EXISTS readings_by_device (
    device_id uuid,
    observed_at timestamp,
    temperature double,
    PRIMARY KEY ((device_id), observed_at)
) WITH CLUSTERING ORDER BY (observed_at DESC);

INSERT INTO readings_by_device (device_id, observed_at, temperature)
VALUES (a30b7134-4294-4b54-8765-2046c9e86055,
        '2026-11-21T09:00:00Z', 28.4);

INSERT INTO readings_by_device (device_id, observed_at, temperature)
VALUES (a30b7134-4294-4b54-8765-2046c9e86055,
        '2026-11-21T09:01:00Z', 28.8);

SELECT device_id, observed_at, temperature
FROM readings_by_device
WHERE device_id = a30b7134-4294-4b54-8765-2046c9e86055
ORDER BY observed_at DESC
LIMIT 10;
~~~

Hai hàng cùng `device_id` ở cùng partition nên được gán **cùng tập replica** trong hai DC. Thiết kế `PRIMARY KEY ((device_id), observed_at)` phục vụ truy vấn xem các số đo gần nhất của một thiết bị; nếu thiết bị ghi liên tục trong nhiều năm, cần cân nhắc bucket theo ngày/tháng để tránh partition quá lớn.

**Lưu ý:** `CREATE KEYSPACE IF NOT EXISTS` **không sửa** replication map của keyspace đã tồn tại. Nếu `lab_nts` đã tồn tại, xem schema trước khi thử, hoặc chọn tên keyspace lab khác. Không giả định RF vừa được đổi chỉ vì lệnh không báo lỗi.

### 3.3. Đọc metadata và tập replica thực tế

Trong `cqlsh`:

~~~text
DESCRIBE KEYSPACE lab_nts
~~~

Và có thể xem token của partition mẫu:

~~~sql
SELECT token(device_id) AS partition_token
FROM lab_nts.readings_by_device
WHERE device_id = a30b7134-4294-4b54-8765-2046c9e86055
LIMIT 1;
~~~

Trên một node dùng `nodetool`:

~~~bash
nodetool getendpoints lab_nts readings_by_device a30b7134-4294-4b54-8765-2046c9e86055
~~~

Với **hai DC có đủ ba node** và RF = 3 cho từng DC, kỳ vọng có **sáu endpoint vật lý khác nhau**, gồm ba ở `dc1` và ba ở `dc2`. Đối chiếu từng IP trong kết quả `getendpoints` với DC/rack trên `nodetool status`. Nếu có nhiều node trong mỗi DC, cần kiểm tra ba replica được chọn có trải ra các rack phù hợp hay không.

| Kiểm tra | Kết quả mong đợi | Khi sai cần xem gì? |
|---|---|---|
| `DESCRIBE KEYSPACE` | `NetworkTopologyStrategy`, `dc1: 3`, `dc2: 3` | Có dùng lại keyspace cũ không? Tên DC có đúng không? |
| `nodetool status` | Node `UN`, thông tin DC/rack đúng | Snitch, cấu hình node, mạng, lỗi membership |
| `getendpoints` | 3 endpoint mỗi DC; mỗi node chỉ tính một lần | RF/keyspace, phân bố token, số node khả dụng trong DC |
| Truy vấn theo `device_id` | Trả hai hàng dữ liệu mẫu | Keyspace/bảng, thời điểm ghi, CL, replica khả dụng |

**Giới hạn quan sát:** `getendpoints` cho biết **những node mà metadata chọn làm replica**, không chứng minh dữ liệu lịch sử trên tất cả các node đã đồng bộ hoặc những node đó hiện đang Up. Cần xem trạng thái cluster, thử đọc/ghi theo CL phù hợp và thực hiện repair nếu vừa thay đổi topology/RF.

## 4. Nhất quán đọc ghi khi có nhiều datacenter

### 4.1. Cách tính LOCAL_QUORUM, QUORUM và EACH_QUORUM

Giả sử keyspace `lab_nts` có `dc1: 3` và `dc2: 3`, tổng cộng sáu full replica cho mỗi partition.

| Consistency level | Điều kiện phản hồi trong ví dụ RF 3 + 3 | Ghi chú |
|---|---|---|
| `LOCAL_ONE` | 1 replica thuộc DC cục bộ | Ưu tiên độ trễ/khả dụng; có thể đọc replica chưa cập nhật |
| `LOCAL_QUORUM` | 2 replica trong DC cục bộ | `floor(3/2)+1 = 2` |
| `ONE` | 1 replica bất kỳ trong các DC | Không bảo đảm phản hồi phải ở DC cục bộ |
| `QUORUM` | 4 replica trên toàn cluster | `floor(6/2)+1 = 4` |
| `ALL` | Cả 6 replica | Không chịu được replica nào không phản hồi |
| `EACH_QUORUM` | **Khi ghi:** 2 replica trong `dc1` **và** 2 trong `dc2` | Dùng cho write; không phải CL đọc CQL thông thường |

Ở trên, **DC cục bộ** là DC của coordinator thực hiện yêu cầu (với driver Java thường được kiểm soát bằng local datacenter và chính sách định tuyến). `LOCAL_QUORUM` ở `dc1` và `LOCAL_QUORUM` ở `dc2` có thể yêu cầu cùng một số phản hồi nhưng từ **những tập replica khác nhau**.

Với RF riêng theo DC là `n`, local quorum của DC ấy là:

\[
Q_{\mathrm{local}} = \left\lfloor\frac{n}{2}\right\rfloor + 1
\]

Với tổng số full replica trên tất cả DC là `N`, quorum toàn cluster là:

\[
Q_{\mathrm{global}} = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

Ví dụ nếu `dc1: 3`, `dc2: 2` thì `LOCAL_QUORUM` tại `dc1` cần 2, tại `dc2` cũng cần **2**, còn `QUORUM` toàn cluster cần `floor(5/2)+1 = 3`. Do đó không nên nói “LOCAL_QUORUM luôn cần hai replica” khi RF có thể khác.

### 4.2. Chọn CL dựa trên yêu cầu ứng dụng

Đối với ứng dụng Java đặt ở `dc1`, cặp **ghi `LOCAL_QUORUM` và đọc `LOCAL_QUORUM` trong cùng DC** với RF = 3 giúp quorum của hai thao tác giao nhau (`2 + 2 > 3`) trong DC đó. Đây là cơ sở để đọc thấy các ghi đã được xác nhận theo quorum khi không có ghi cạnh tranh và không có các yếu tố khác làm phức tạp lịch sử cập nhật.

Tuy nhiên:

- **LOCAL_QUORUM không đồng nghĩa mọi DC đều đã thấy dữ liệu mới nhất ngay tức thì.** Ghi ở `dc1` có thể được xác nhận trước khi các replica `dc2` phản hồi; ứng dụng đọc ngay tại `dc2` phải xét độ trễ truyền dữ liệu, lỗi mạng và CL được dùng ở cả hai phía.
- **LOCAL_QUORUM không đảm bảo linearizability cho mọi truy cập.** Cần phân biệt timestamp, ghi đồng thời, last-write-wins, retry, xung đột và các phép toán có điều kiện (LWT).
- **QUORUM toàn cluster** yêu cầu đủ số replica trên các DC; với hai DC RF 3 + 3, mất trọn một DC chỉ còn ba replica, không đạt mức yêu cầu bốn phản hồi.
- **EACH_QUORUM cho ghi** giúp yêu cầu xác nhận quorum từ **từng DC** nhưng có độ trễ và độ phụ thuộc liên DC cao hơn; mất hẳn một DC sẽ khiến thao tác không đủ mức nhất quán đó.

Không có CL “tốt nhất” cho tất cả tình huống. Hãy xác định **phạm vi dữ liệu cần được đọc sau khi ghi**, độ trễ liên DC và khả năng chịu lỗi mong muốn trước khi chọn CL.

### 4.3. Thực hành CQL ở từng DC

Kết nối `cqlsh` vào node thuộc `dc1`, chạy:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

Sau đó thực hiện:

~~~sql
SELECT observed_at, temperature
FROM lab_nts.readings_by_device
WHERE device_id = a30b7134-4294-4b54-8765-2046c9e86055
LIMIT 10;
~~~

Lệnh `CONSISTENCY` trên là **lệnh riêng của cqlsh**, đặt CL cho những yêu cầu tiếp theo trong phiên. Kết nối một phiên `cqlsh` khác tới node thuộc `dc2` và lặp lại với `LOCAL_QUORUM`; tập replica cần xác nhận sẽ nằm ở `dc2`. Khi muốn đo sự khác biệt, chạy riêng ở `LOCAL_ONE`, `QUORUM` và ghi nhận kết quả, độ trễ, node/coordinator, tình trạng mạng.

Đọc ra cùng dữ liệu khi mọi node Up **không đủ** để chứng minh local quorum chịu được lỗi. Muốn kiểm tra điều này cần một lab cô lập và một kịch bản lỗi được kiểm soát.

## 5. Kịch bản lỗi: mất node, mất rack và mất datacenter

Giả định có hai DC, **mỗi DC ba replica trên ba rack độc lập**, RF 3 + 3. Ứng dụng có thể kết nối tới một DC còn hoạt động và chuyển hướng khi cần.

| Sự cố | `LOCAL_QUORUM` trong DC bị ảnh hưởng | `LOCAL_QUORUM` ở DC còn khỏe | `QUORUM` toàn cluster |
|---|---|---|---|
| Một replica/node ở `dc1` Down | Vẫn có thể đạt 2/3 | Vẫn có thể đạt 2/3 | Vẫn có thể đạt 4/6 nếu 5 replica còn hoạt động |
| Một rack ở `dc1` Down, mỗi rack giữ một replica | Vẫn có thể đạt 2/3 | Vẫn có thể đạt 2/3 | Vẫn có thể đạt 4/6 |
| Mất toàn bộ `dc1` | Không thể đạt từ coordinator ở `dc1` | Có thể đạt 2/3 tại `dc2` | Không đạt 4/6 |
| Mất kết nối liên DC nhưng các node trong mỗi DC vẫn hoạt động | Có thể đạt 2/3 cục bộ | Có thể đạt 2/3 cục bộ | Có thể không đạt 4/6 từ một phía mạng bị cô lập |

Đây là **kỳ vọng lý thuyết về số replica phản hồi**, không phải cam kết thao tác luôn thành công: coordinator, mạng client, thời gian phát hiện lỗi, timeout, dữ liệu còn đồng bộ và mức tải đều ảnh hưởng thực tế. Nếu một rack giữ **hai** replica trong cùng DC, mất rack đó chỉ còn 1/3 và local quorum **không đủ**.

### 5.1. Quy trình thử lỗi an toàn trong lab

1. Xác nhận cả hai DC có đủ node `UN`; sao lưu dữ liệu lab cần giữ.
2. Ghi dữ liệu mẫu và đo đọc/ghi với `LOCAL_QUORUM` tại `dc1`.
3. Dừng **một node** `dc1` bằng hệ thống quản lý lab; đợi cluster nhìn thấy tình trạng Down.
4. Thử đọc/ghi `LOCAL_QUORUM` ở `dc1`, sau đó thử ở `dc2`; ghi kết quả và thời gian phản hồi.
5. Khởi động lại node, đợi nó ổn định; xác nhận sự đồng bộ/repair theo quy trình phòng lab.
6. Chỉ nếu lab cho phép và đã kiểm tra cách khôi phục, thử mô phỏng lỗi rack/DC theo phạm vi đã thiết kế; không tác động production.

**Không nhầm tính sẵn sàng với tính nhất quán:** khi tách mạng, hai DC có thể tiếp tục chấp nhận ghi tại `LOCAL_QUORUM` của từng DC. Nếu nhiều nơi cùng sửa một partition, phải hiểu cơ chế timestamp và giải quyết xung đột; kết quả sau khi mạng hồi phục không có nghĩa mọi lịch sử ghi đều được bảo toàn theo thứ tự người dùng mong muốn.

## 6. Chọn topology/RF và mở rộng hệ thống

### 6.1. Quy tắc thiết kế thực tế

| Bài toán | Lựa chọn gợi ý | Điều cần xác minh |
|---|---|---|
| Production một DC, ba node trên ba rack độc lập | NTS với RF `dc1: 3` | Snitch báo đúng DC/rack, dung lượng dự phòng khi mất node |
| Hai DC cần đọc/ghi cục bộ độc lập | NTS với RF riêng từng DC, thường 3 mỗi DC nếu đủ hạ tầng | Driver gắn với DC cục bộ, chiến lược failover và đồng bộ |
| DC thứ hai chỉ phục vụ thử nghiệm/DR | RF của `dc2` theo mục tiêu RPO/RTO và tài nguyên | Không mặc định RF = 1 đáp ứng quorum hay sẵn sàng khi lỗi |
| RF = 3 nhưng mỗi DC có hai rack | NTS vẫn dùng được | Một rack có thể chứa hai replica; cân nhắc thêm rack hoặc thay đổi yêu cầu chịu lỗi |
| Muốn chỉ lưu replica trong một DC | Chỉ khai báo RF cho DC đó | Xác minh đường truy cập và các bản sao cũ sau khi đổi schema |

Chọn RF dựa trên miền lỗi cần chịu, năng lực lưu trữ, chi phí mạng và mục tiêu CL. Với hai DC RF 3 + 3, **mỗi partition có sáu replica**, nghĩa là chi phí lưu trữ và lưu lượng replication đáng kể so với một bản dữ liệu; các con số này chưa tính overhead compaction, index và metadata.

NTS quản lý **vị trí replica**. Nếu có yêu cầu nghiêm ngặt về data residency, phải xét thêm coordinator, truy vấn, log, backup, snapshot, giám sát và nơi ứng dụng xử lý dữ liệu; khai báo replication map riêng không phải một chính sách tuân thủ đầy đủ.

### 6.2. Thay đổi RF trong một DC

Ví dụ tăng RF của `dc1` từ 2 lên 3 trong một keyspace đang dùng NTS:

~~~sql
ALTER KEYSPACE lab_nts
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

**Điều kiện:** CQL trên chỉ là ví dụ nếu trạng thái hiện tại thật sự là `dc1: 2, dc2: 3`. Không chạy nó như một bước “sửa” không có kế hoạch. `ALTER KEYSPACE` thay đổi **metadata về replica mong muốn**; các replica mới chưa chắc đã có dữ liệu lịch sử ngay.

Quy trình vận hành điển hình:

1. Kiểm tra RF hiện tại, snitch, DC/rack/node, dung lượng đĩa, phiên bản Cassandra, nhu cầu backup và CL ứng dụng.
2. Bảo đảm đã có đủ **node và rack thực tế** để đáp ứng mục tiêu; nếu cần thêm node, hoàn thành việc join/bootstrap/streaming theo hướng dẫn vận hành phù hợp.
3. Thực hiện thay đổi schema và chờ schema agreement; xác nhận bằng `DESCRIBE KEYSPACE` và `nodetool getendpoints` cho các partition mẫu.
4. Lập kế hoạch **full repair** trên các node liên quan để dữ liệu lịch sử được đưa tới các replica mới được chỉ định; theo dõi mạng, đĩa, compaction, timeout.
5. Chỉ chuyển CL hoặc tăng tải sản xuất khi đã xác minh bố trí và dữ liệu cần thiết.

Ví dụ một lệnh repair trên node nằm trong phạm vi thao tác:

~~~bash
nodetool repair --full lab_nts
~~~

Full repair tiêu tốn tài nguyên; **phạm vi node, thứ tự chạy và tham số repair** cần được quyết định theo phiên bản và runbook thực tế. Không chạy full repair đồng loạt trên toàn cluster nếu chưa tính tải.

### 6.3. Thêm datacenter mới

Giả sử `dc2` chưa có replica của keyspace cũ và cần được đưa vào hoạt động. Việc thêm `'dc2': 3` vào map replication **không tự bảo đảm dữ liệu cũ có mặt ở `dc2`**. Cần một chuỗi công việc gồm triển khai node và snitch, bootstrap hoặc rebuild/streaming từ DC nguồn theo runbook, xác minh dữ liệu và repair thích hợp, sau đó mới chuyển traffic ứng dụng và chọn CL địa phương.

Trong giai đoạn chuyển đổi, tránh vội yêu cầu `LOCAL_QUORUM` tại DC mới khi dữ liệu và replica chưa hoàn tất đồng bộ. Với thao tác giảm RF hoặc loại DC, các bản dữ liệu dư có thể còn trên đĩa; cần kế hoạch cleanup sau khi chắc chắn dữ liệu đã có nơi sở hữu hợp lệ và có thể khôi phục khi lỗi.

**Repair khác compaction:** repair trao đổi dữ liệu/khác biệt giữa replica để khắc phục lệch trạng thái; compaction hợp nhất SSTable **trong một node** và không thay cho quá trình truyền dữ liệu tới replica mới. Hinted handoff có thể giúp khi replica tạm thời Down nhưng không thay thế repair định kỳ.

## 7. Java Driver: định tuyến đến DC cục bộ và đặt CL

Trong ứng dụng Java, **replication strategy và RF được lưu trong schema của Cassandra**; Java Driver chọn coordinator, thực hiện routing và đặt consistency cho từng câu lệnh. Với DataStax/Apache Cassandra Java Driver 4.x, ví dụ đơn giản:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetSocketAddress;
import java.util.UUID;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.0.1.11", 9042))
        .withLocalDatacenter("dc1")
        .build()) {

    PreparedStatement prepared = session.prepare(
        "SELECT observed_at, temperature " +
        "FROM lab_nts.readings_by_device " +
        "WHERE device_id = ? LIMIT 10");

    BoundStatement statement = prepared
        .bind(UUID.fromString("a30b7134-4294-4b54-8765-2046c9e86055"))
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    session.execute(statement).forEach(row ->
        System.out.println(row.getInstant("observed_at") + " : " +
                           row.getDouble("temperature")));
}
~~~

`10.0.1.11` chỉ là contact point **minh họa**; thay bằng địa chỉ node thật ở `dc1`. Ứng dụng triển khai thực tế cần cấu hình xác thực/TLS nếu cluster yêu cầu và xem lại timeout, retry, idempotence. `withLocalDatacenter("dc1")` định hướng driver sử dụng DC cục bộ cho routing; nó **không** sửa replication map. `LOCAL_QUORUM` đặt yêu cầu xác nhận đối với thao tác cụ thể, không phải thay đổi RF.

Khi failover sang `dc2`, cần định hướng session/client tới DC phục vụ mới và đảm bảo RF, dữ liệu cùng mức nhất quán ở DC đó đáp ứng yêu cầu nghiệp vụ. Không chỉ đổi một chuỗi `dc1` thành `dc2` rồi giả định mọi partition đã đồng bộ, đặc biệt sau khi thêm DC hoặc vừa thay đổi RF.

## 8. Chẩn đoán hiện tượng thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng điều tra |
|---|---|---|
| `LOCAL_QUORUM` lỗi dù nhiều node cluster vẫn Up | DC cục bộ không đủ replica; nhiều node cùng rack/đường mạng lỗi; RF khác dự kiến | Xem DC của coordinator, `nodetool status`, keyspace RF, endpoints |
| `QUORUM` lỗi khi mất nguyên một DC với RF 3 + 3 | Chỉ còn 3/6 replica, thấp hơn global quorum = 4 | Chọn CL theo yêu cầu ứng dụng; xem phương án định tuyến tới DC còn khỏe |
| `getendpoints` hiển thị node ở rack không mong muốn | Snitch/rack cấu hình không phản ánh topology, token ring hoặc không đủ rack | Xác minh DC/rack thực tế, kế hoạch triển khai và số node |
| Lệnh `ALTER KEYSPACE` thành công nhưng dữ liệu cũ đọc lỗi ở DC mới | Metadata đã đổi, replica mới chưa đồng bộ/streaming/repair hoàn tất | Kiểm tra tiến độ bootstrap, rebuild/streaming, repair, trạng thái node |
| Java truy vấn qua DC xa và tăng độ trễ | Local DC/routing/contact points hoặc failover chưa phù hợp | Kiểm tra driver local datacenter, đường mạng, coordinator và metrics |
| Sau mất mạng, hai DC có kết quả khác nhau | Ghi đồng thời, CL cục bộ, timestamp và việc truyền dữ liệu bị chậm | Xem consistency của cả read/write, timestamp, retry và repair |

Các lỗi `UnavailableException` thường cho thấy không đủ replica được coi là sẵn sàng để thỏa CL; `ReadTimeoutException`/`WriteTimeoutException` cho thấy yêu cầu không đạt đủ phản hồi trước timeout. Đừng suy ra rằng dữ liệu đã bị mất hoặc một ghi chắc chắn không được thực hiện chỉ từ timeout: kiểm tra logs/metrics và xử lý retry an toàn, đặc biệt khi thao tác có tác dụng phụ.

## 9. Bài tập áp dụng

**Bài 1 — tính số replica và quorum.** Keyspace khai báo `dc1: 3, dc2: 2`. Một partition có bao nhiêu replica? `LOCAL_QUORUM` cần mấy phản hồi khi coordinator ở `dc1` và khi ở `dc2`? `QUORUM` toàn cluster cần mấy phản hồi?

<details>
<summary>Gợi ý đáp án</summary>

Tổng có **5 replica**. Local quorum ở `dc1` là **2/3**, ở `dc2` là **2/2**; quorum toàn cluster là **3/5**. Bởi vậy `dc2` không chịu được một replica Down nếu vẫn yêu cầu `LOCAL_QUORUM`.
</details>

**Bài 2 — mất rack.** Trong `dc1`, RF = 3 được đặt trên A (rack r1), C (rack r1), E (rack r2). Điều gì xảy ra với `LOCAL_QUORUM` khi rack r1 mất hoàn toàn?

<details>
<summary>Gợi ý đáp án</summary>

Chỉ còn E, tức **1/3**, trong khi local quorum cần **2/3** nên thao tác không thỏa CL. Cần topology có nhiều rack độc lập hơn hoặc điều chỉnh mục tiêu khả dụng.
</details>

**Bài 3 — mất DC.** Cluster RF 3 + 3 mất toàn bộ `dc1`. Ứng dụng đã chuyển coordinator sang `dc2`. `LOCAL_QUORUM` và `QUORUM` toàn cluster có còn khả dụng về mặt số lượng replica không?

<details>
<summary>Gợi ý đáp án</summary>

`LOCAL_QUORUM` tại `dc2` có thể đạt **2/3** nếu DC2 khỏe và dữ liệu sẵn sàng; `QUORUM` toàn cluster cần **4/6** nên không đạt khi chỉ còn ba replica ở `dc2`.
</details>

**Bài 4 — mở rộng DC.** Một keyspace từ lâu chỉ có `dc1: 3`. Nhóm vận hành thêm `dc2: 3` vào CQL, sau đó ứng dụng ở `dc2` lập tức chọn `LOCAL_QUORUM`. Có thể khẳng định mọi dữ liệu lịch sử đã có ở DC2 không?

<details>
<summary>Gợi ý đáp án</summary>

**Không.** Thay đổi schema chỉ khai báo nơi replica phải nằm. DC mới cần tiến trình bootstrap/rebuild/streaming và repair thích hợp, kèm kiểm chứng dữ liệu trước khi nhận traffic chính thức.
</details>

### Checklist tự kiểm tra

- [ ] Phân biệt được token ring, datacenter, rack, RF và CL.
- [ ] Hiểu NTS chọn replica theo RF của **từng** DC và ưu tiên phân tán rack.
- [ ] Tạo được keyspace NTS bằng CQL và đối chiếu replica với `nodetool getendpoints`.
- [ ] Tính được `LOCAL_QUORUM` và `QUORUM` cho nhiều giá trị RF khác nhau.
- [ ] Dự đoán ảnh hưởng của lỗi node, rack và datacenter đến khả năng đáp ứng CL.
- [ ] Biết vì sao đổi RF/thêm DC cần streaming hoặc repair và kiểm chứng dữ liệu.
- [ ] Cấu hình được local datacenter và consistency theo request trong Java Driver.

## Tài liệu đọc thêm

1. Apache Cassandra Documentation — [Dynamo: Partitioning và Replication Strategy](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html).
2. Apache Cassandra Documentation — [CQL Data Definition: CREATE/ALTER KEYSPACE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
3. Apache Cassandra Documentation — [nodetool getendpoints](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/getendpoints.html).
4. Apache Cassandra Documentation — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html).
