# Phân biệt số nút, số token và số bản sao

## 1. Vì sao ba con số này dễ bị nhầm?

Khi triển khai Apache Cassandra, ta thường gặp các thông số như “cluster có **4 node**”, “mỗi node giữ **8 token**” và “keyspace dùng **replication factor 3**”. Ba con số đều liên quan đến phân phối dữ liệu nhưng trả lời ba câu hỏi **khác nhau**:

1. **Số nút (node count):** Có bao nhiêu tiến trình/máy Cassandra tham gia cluster, hoặc tham gia một data center?
2. **Số token (token count):** Có bao nhiêu vị trí token được gán trên vòng phân vùng dữ liệu, giúp chia phạm vi token thành những phần do các node phụ trách?
3. **Số bản sao (replica count):** Với **mỗi partition** trong một keyspace, có bao nhiêu **node khác nhau** được chọn để lưu bản sao dữ liệu?

Đối với mô hình **wide-column**, partition key quyết định partition nằm ở những node nào; số token ảnh hưởng cách chia và cân bằng các khoảng khóa; replication factor quyết định có bao nhiêu bản sao của partition. Phân biệt đúng ba con số là tiền đề để thiết kế bảng theo truy vấn, cấu hình replication/consistency level, đọc trace, xử lý sự cố, lên kế hoạch repair và kết nối an toàn từ Java.

**Phạm vi bài:** các *full replica* thông thường trong Cassandra dùng phân vùng dựa trên token (thường là `Murmur3Partitioner`). Không áp dụng phép đếm dưới đây để suy trực tiếp cơ chế transient replication hoặc tối ưu phân phối dữ liệu riêng của một phiên bản.

## 2. Định nghĩa: node, token, replica và RF

| Khái niệm | Đơn vị đếm | Được quyết định bởi | Điều **không** được suy ra |
| --- | --- | --- | --- |
| **Node** | Một Cassandra node (một thành viên cluster) | Số node triển khai và trạng thái tham gia cluster | Một node không tương đương một bản sao của *mọi* partition. |
| **Token** | Một giá trị/vị trí trong miền token, gắn với một node | Partitioner, việc phân bổ token và cấu hình như `num_tokens` | Một token không phải một hàng, một partition, một máy, hay một replica. |
| **Token range** | Khoảng giá trị token trên vòng | Các vị trí token liên tiếp | Một range không chỉ chứa đúng một partition; thường chứa rất nhiều partition. |
| **Replica** | Một node lưu bản sao của *một partition xác định* | Partition key → token, replication strategy, RF, topology DC/rack | Một node có nhiều token không được tính thành nhiều replica của cùng partition. |
| **Replication factor (RF)** | Số replica mục tiêu trên mỗi partition (theo data center nếu dùng `NetworkTopologyStrategy`) | Cấu hình replication của keyspace | RF không phải số node toàn cluster hay số token/node. |
| **Consistency level (CL)** | Ngưỡng phản hồi cần có cho một thao tác đọc/ghi | Tùy request/statement | CL không tăng hoặc giảm RF. |

Một node vật lý có thể giữ nhiều token (*virtual nodes*, thường gọi là **vnodes**); một node cũng có thể chứa dữ liệu của nhiều partition, nhưng đối với **một** partition, nó chỉ được tính là **một replica**. RF = 3 nghĩa là ba **node khác nhau** được chọn lưu partition khi topology đáp ứng được RF, bất kể mỗi node có một token hay hàng chục token.

Để tránh nhầm từ ngữ, bài này gọi **“số token”** là *số vị trí token được gán cho các node*. Trong trường hợp vnodes và phân bổ đều, tổng số vị trí token thường bằng:

\[
T = \sum_{i=1}^{N} T_i
\]

Trong đó `N` là số node, còn `T_i` là số token được gán cho node thứ `i`. Công thức chỉ đếm các token được gán, **không** đếm số giá trị token có thể được hàm băm sinh ra và cũng **không** đếm số bản sao dữ liệu.

## 3. Node count: quy mô cluster và từng data center

Node là thành viên thực hiện lưu trữ và xử lý request trong cluster Cassandra. Cluster thường có nhiều **data center (DC)** và các node trong DC được đặt ở những **rack** nhằm hỗ trợ lựa chọn replica chịu lỗi tốt hơn.

Ví dụ topology:

~~~text
Cluster webshop
├── dc1
│   ├── N1
│   ├── N2
│   ├── N3
│   └── N4
└── dc2
    ├── N5
    ├── N6
    └── N7
~~~

- Tổng số node của cluster: **7**.
- Số node ở `dc1`: **4**; ở `dc2`: **3**.
- Các con số trên chỉ mô tả **quy mô triển khai**; chưa cho biết một partition được sao chép mấy lần.

Một node có thể làm **coordinator** cho request do client gửi tới dù không phải replica của partition đó. Coordinator là **vai trò xử lý request**, còn replica là **vai trò lưu bản sao theo partition**. Số coordinator khả dụng không phải là RF của keyspace.

## 4. Token count: các vị trí trên vòng và virtual nodes

### 4.1. Từ partition key đến token

Cassandra đưa giá trị partition key qua *partitioner* để tính token. Với `Murmur3Partitioner`, token là một số nguyên có dấu 64-bit; ví dụ trong sơ đồ bên dưới chỉ dùng các số nhỏ để dễ đọc và **không phải giá trị băm thực tế**.

Các node nhận trách nhiệm với những **khoảng token**. Trong cách hình dung vòng token cổ điển, token gán cho node đánh dấu điểm kết thúc của một khoảng `(token trước, token hiện tại]`, theo chiều kim đồng hồ. Khoảng cuối nối vòng về token đầu tiên.

~~~mermaid
flowchart LR
    P["Partition key: account_id = 'a-42'"] --> H["Partitioner tính token"]
    H --> T["Token của partition"]
    T --> O["Xác định khoảng token chứa giá trị đó"]
    O --> R["Chọn các node replica theo RF và topology"]
~~~

Token **không phải** một mã số cấp phát mới cho mỗi bản ghi. Nhiều partition có thể rơi vào cùng một khoảng token, và bản thân miền token có số giá trị rất lớn so với số token được gán cho các node.

### 4.2. Một node có thể giữ nhiều token

Với cách bố trí **một token trên mỗi node**, 4 node tương ứng 4 vị trí token, chia vòng thành 4 khoảng. Với **vnodes**, mỗi node được gán nhiều vị trí token khác nhau; chẳng hạn `num_tokens = 8` cho 4 node thì có khoảng **32 vị trí token** nếu cả 4 node đều được phân bổ 8 token.

~~~text
Ví dụ vnodes: 4 node, mỗi node 2 token (8 token trên vòng)

Vị trí tăng dần:  -90    -60    -30      0      30      60      90     120
Node giữ token:   N1     N2     N3     N4      N1      N2      N3      N4
                   └──────────────────────────────────────────────────────┘
                         Vòng nối từ token cuối về token đầu
~~~

Trong ví dụ, N1 vừa sở hữu vị trí token `-90`, vừa sở hữu `30`. Điều này giúp N1 phụ trách **nhiều khoảng token rời nhau** trên vòng, thay vì một khoảng liên tục. Tổng số node vẫn là **4**. Nếu RF của keyspace là 3, một partition vẫn có **3 replica**, không trở thành 6 hay 8 replica chỉ vì node có nhiều token.

Token count cao hơn thường làm việc phân phối/phân bổ tải linh hoạt hơn nhưng có thêm chi phí metadata, streaming, repair và vận hành; số token phù hợp phụ thuộc phiên bản, topology, loại workload và kế hoạch mở rộng. Không nên xem “càng nhiều token càng tốt” là quy tắc chung.

> Khi thêm node, Cassandra có thể phân bổ lại token range và stream dữ liệu để phân phối tải. Việc có thêm token hoặc node **không tự động làm tăng RF** của keyspace.

## 5. Replica count: mỗi partition được lưu trên bao nhiêu node?

Replica được xác định cho từng partition bằng **token của partition**, **replication strategy** và **topology**. Với keyspace production dùng `NetworkTopologyStrategy`, RF thường được cấu hình **riêng cho từng data center**.

Ví dụ:

~~~sql
CREATE KEYSPACE IF NOT EXISTS webshop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 2
};
~~~

Nếu topology có đủ node phù hợp:

- **Mỗi partition** của keyspace `webshop` có **3 full replica ở `dc1`** và **2 full replica ở `dc2`**.
- Tổng cộng có **5 full replica trên 5 node khác nhau** cho partition đó, không phải 7 bản sao (7 là tổng số node cluster).
- Những partition khác có thể có **bộ replica khác nhau**, dù vẫn giữ số lượng 3 + 2.
- Replica được đặt dựa trên token và quy tắc lựa chọn DC/rack; không phải chọn tùy ý từ bất kỳ node nào.

Nếu ký hiệu `RF_dc` là RF của một DC, số bản sao mục tiêu trong một keyspace đa DC là:

\[
R_{\text{total}} = \sum_{dc} RF_{dc}
\]

Công thức giả định các DC có đủ node hợp lệ để thỏa RF và chỉ đếm full replica. Nếu cấu hình yêu cầu RF lớn hơn số node hiện có trong một DC, **không thể có đủ số replica trên các node khác nhau** của DC đó; đây là lỗi hoạch định topology, không thể bù bằng cách tăng số token.

### Một token không đồng nghĩa với một replica

Quay lại vòng token minh họa ở mục 4: 4 node N1–N4, mỗi node có 2 token. Giả sử một partition có token **15**:

1. Đi theo chiều tăng trên vòng, token được gán đầu tiên lớn hơn hoặc bằng 15 là **30**, thuộc N1: đây là điểm bắt đầu tìm replica.
2. Trong mô hình **đơn giản hóa** dùng `SimpleStrategy` với RF = 3, tiếp tục đi trên vòng và chọn các **node khác nhau**: N1, N2, N3.
3. Khi gặp thêm một token thuộc node đã được chọn, Cassandra không đếm node đó lần thứ hai để tăng RF.

~~~mermaid
flowchart LR
    K["Partition có token = 15"] --> A["Token 30 → N1"]
    A --> B["Token 60 → N2"]
    B --> C["Token 90 → N3"]
    C --> D["3 replica: N1, N2, N3"]
~~~

Ví dụ này chỉ để nhìn rõ **nguyên tắc chọn các node phân biệt trên vòng**. `SimpleStrategy` không thích hợp cho triển khai production đa rack/đa DC; `NetworkTopologyStrategy` còn xét DC/rack khi chọn replica nên tập node thực tế có thể khác chuỗi minh họa trên.

## 6. Đặt ba con số cạnh nhau

Giả sử cluster có **4 node trong một DC**, mỗi node được gán **8 token** và keyspace cấu hình **RF = 3**:

| Câu hỏi | Kết quả |
| --- | --- |
| Cluster có bao nhiêu node? | **4 node** |
| Mỗi node có bao nhiêu token được gán? | **8 token/node** |
| Tổng token được gán là bao nhiêu? | **4 × 8 = 32 token** |
| Có bao nhiêu replica cho một partition của keyspace? | **3 replica**, trên 3 node khác nhau |
| Một partition có bao nhiêu bản sao khi 1 node không phải replica? | **Vẫn là 3**; node thứ tư không giữ partition đó |
| RF = 3 có nghĩa tất cả 4 node đều lưu mọi partition không? | **Không** |
| Tăng token/node từ 8 lên 16 có làm RF tăng lên 6? | **Không**, RF vẫn là 3 nếu không thay cấu hình keyspace |

### Sơ đồ tư duy: ba lớp quyết định

~~~mermaid
flowchart TD
    N["4 node Cassandra"] --> V["Mỗi node 8 token → 32 vị trí token"]
    PK["Partition key của bảng"] --> H["Hash → 1 giá trị token cho partition"]
    H --> M["Tìm khoảng token và vị trí trên vòng"]
    V --> M
    RF["Keyspace RF = 3, replication strategy"] --> S["Chọn 3 node khác nhau làm replica"]
    M --> S
    S --> A["Partition có 3 bản sao"]
~~~

**Cách đọc:** node count cho biết số thành viên có thể nhận việc; token count ảnh hưởng việc chia phạm vi trách nhiệm; RF và chiến lược replication quyết định số node giữ từng partition. Ba biến có mối liên hệ nhưng **không thay thế nhau**.

## 7. Tác động đến dung lượng, tốc độ và tính sẵn sàng

### 7.1. Dung lượng lưu trữ

Nếu dữ liệu gốc của một keyspace chiếm khoảng `D` đơn vị và có RF = 3 trong một DC, thì riêng **dữ liệu được sao chép** về mặt trực giác chiếm khoảng `3D` trên các node. Thực tế còn overhead từ commit log, memtable, SSTable metadata, tombstone, compaction, snapshot và việc phân phối không đều.

Với 4 node và RF = 3, nếu dữ liệu được phân phối cân bằng thì mức lưu trữ dữ liệu được sao chép **trung bình** trên mỗi node gần:

\[
\frac{D \times RF}{N} = \frac{3D}{4}
\]

Đây chỉ là **ước lượng để lập kế hoạch**, không phải cam kết dung lượng của từng node. Token count tác động đến độ mịn khi chia tải, còn RF mới là hệ số chính quyết định lượng dữ liệu được sao chép trong mô hình trên.

### 7.2. Khi node lỗi

Ở **một DC có 4 node, RF = 3**, nếu thao tác dùng `LOCAL_QUORUM`, coordinator cần phản hồi từ **2 trong 3 replica của partition**:

| Trạng thái các replica của partition | Số replica còn hoạt động | Ghi/đọc `LOCAL_QUORUM` |
| --- | ---: | --- |
| Cả 3 replica hoạt động | 3 | Có thể thành công |
| 1 replica lỗi, 2 replica hoạt động | 2 | Vẫn có thể thành công |
| 2 replica lỗi, 1 replica hoạt động | 1 | Không đáp ứng CL |

Nếu node thứ tư **không phải** replica của partition đang xét vẫn hoạt động, nó có thể làm coordinator nhưng **không được tính là một ACK replica bổ sung**. Thêm nhiều token cho node đó cũng không biến nó thành bản sao thứ tư.

Với RF = 3 trong cùng DC, `LOCAL_ONE` cần một replica phản hồi, `LOCAL_QUORUM` cần hai, `ALL` cần ba. Với nhiều DC, `LOCAL_QUORUM` lấy quorum theo **RF của DC cục bộ**, trong khi `QUORUM` tính theo **tổng RF** của keyspace. RF kiểm soát số bản sao; CL kiểm soát số phản hồi tối thiểu trước khi request thành công.

### 7.3. Khi cần tăng khả năng chịu lỗi hoặc mở rộng tải

| Mục tiêu | Thay đổi cần cân nhắc | Điều không được nhầm |
| --- | --- | --- |
| Có thêm tài nguyên CPU/RAM/disk, chia tải | Thêm node, cân bằng token ranges, theo dõi phân phối dữ liệu | Thêm node không tự làm RF tăng. |
| Tăng số bản sao cho mỗi partition | Đổi replication factor của keyspace, đảm bảo đủ node và đồng bộ dữ liệu mới | Thêm token không tăng bản sao. |
| Phân phối khoảng khóa mịn hơn | Đánh giá số vnode/token trên node theo phiên bản và workload | Không tùy tiện thay `num_tokens` của node đang chạy như một thao tác vô hại. |
| Giảm phụ thuộc DC khác khi đọc/ghi | Chọn RF theo DC và CL phù hợp, chẳng hạn `LOCAL_QUORUM` | Tăng số node toàn cluster không tự sửa yêu cầu ACK của CL. |

Khi thay đổi topology, Cassandra cần di chuyển/stream dữ liệu theo phân bố mới. Khi thay đổi RF, dữ liệu lịch sử cần được đồng bộ đến bộ replica mới bằng quy trình vận hành/repair phù hợp. Compaction trên một node không thay thế repair giữa các replica.

## 8. Thực hành: xác định từng con số bằng công cụ Cassandra

### 8.1. Kiểm tra số node và số token/node

Chạy trên máy có quyền dùng `nodetool`:

~~~bash
nodetool status
~~~

Trong output, quan sát **Data center**, trạng thái `UN` (*Up/Normal*), **Tokens** và **Rack**. Ví dụ minh họa (lược bỏ IP/UUID và thông số không liên quan):

~~~text
Datacenter: dc1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address   Tokens  Rack
UN  node1     8       rack1
UN  node2     8       rack2
UN  node3     8       rack3
UN  node4     8       rack1
~~~

Trong output này có **4 node** ở `dc1`, mỗi node được gán **8 token**, tổng cộng **32 token**. `nodetool status` còn có cột `Owns` hoặc `Owns (effective)`; tỷ lệ ownership phụ thuộc keyspace/RF và không nên đọc nó như số replica hay số token.

Để quan sát các token và khoảng trên vòng, có thể dùng:

~~~bash
nodetool ring
~~~

Lệnh trên cho thấy các token endpoint và giúp kiểm tra việc phân bổ token thực tế. Với nhiều vnode, một node có thể xuất hiện ở nhiều vị trí. Không suy trực tiếp replica từ số dòng của `nodetool ring`.

### 8.2. Tạo keyspace và bảng theo partition key

Giả sử lab chỉ có **một DC tên `dc1` với ít nhất ba node**, chạy:

~~~sql
CREATE KEYSPACE IF NOT EXISTS orders_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS orders_lab.orders_by_customer (
  customer_id text,
  ordered_at timestamp,
  order_id uuid,
  total decimal,
  PRIMARY KEY ((customer_id), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
~~~

`customer_id` là **partition key**; `ordered_at` và `order_id` là clustering columns. Cách thiết kế này phù hợp truy vấn “lịch sử đơn hàng của một khách hàng” bằng partition key cụ thể:

~~~sql
INSERT INTO orders_lab.orders_by_customer
  (customer_id, ordered_at, order_id, total)
VALUES
  ('customer-17', '2026-11-21T03:00:00Z',
   123e4567-e89b-42d3-a456-426614174000, 129.50);

SELECT ordered_at, order_id, total
FROM orders_lab.orders_by_customer
WHERE customer_id = 'customer-17'
LIMIT 10;
~~~

Số **hàng** của khách hàng có thể nhiều, nhưng mọi hàng có cùng `customer_id` ở chung **một partition** và có cùng nhóm replica. RF = 3 vẫn có nghĩa ba node giữ bản sao partition này; không phải “mỗi hàng có ba token”.

### 8.3. Kiểm tra các node replica của một partition

Trên máy có `nodetool`, dùng partition key đơn `customer_id` của ví dụ:

~~~bash
nodetool getendpoints orders_lab orders_by_customer customer-17
~~~

Lệnh giúp liệt kê endpoint chịu trách nhiệm cho **partition key cụ thể** trong keyspace/bảng. Với lab một DC, RF = 3 và topology đáp ứng RF, kỳ vọng có **ba endpoint trên ba node khác nhau**. Đổi `customer_id` có thể thấy tập endpoint khác; các kết quả này không phụ thuộc vào việc Java client kết nối đến node coordinator nào.

Trong `cqlsh`, có thể quan sát CL yêu cầu mà không làm đổi RF:

~~~sql
CONSISTENCY LOCAL_QUORUM;
SELECT ordered_at, order_id, total
FROM orders_lab.orders_by_customer
WHERE customer_id = 'customer-17'
LIMIT 10;
~~~

`CONSISTENCY` là lệnh của **cqlsh**, không phải câu CQL gửi nguyên văn từ Java. Trong ứng dụng Java dùng Cassandra Java Driver 4.x, `BoundStatement.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)` để yêu cầu mức nhất quán tương đương.

**Lưu ý quan sát:** Nếu topology, trạng thái replica hoặc tên data center thực tế khác ví dụ, output có thể khác. Cần dùng tên DC thật khi tạo keyspace và cấu hình `local datacenter` cho driver Java.

## 9. Những nhầm lẫn điển hình

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Cluster có 6 node nên mỗi partition có 6 bản sao.” | **Sai** | Số replica phụ thuộc RF của keyspace, không bằng tổng node mặc định. |
| “Node có 16 token nên giữ 16 replica của mỗi partition.” | **Sai** | Nhiều token giúp node sở hữu nhiều range; với một partition, node đó tối đa là một replica. |
| “RF = 3 nghĩa là mọi ghi phải chờ cả 3 ACK.” | **Sai** | Ngưỡng ACK còn tùy CL. `LOCAL_QUORUM` ở DC có RF 3 cần hai. |
| “Thêm node từ 4 lên 5 thì dữ liệu của mỗi partition tự có thêm một bản sao.” | **Sai** | Replica được tái phân phối; **số replica mục tiêu** không đổi khi RF không đổi. |
| “Tăng `num_tokens` có thể sửa lỗi thiếu node khi RF = 3.” | **Sai** | Cần ba node khác nhau phù hợp trong DC để tạo ba full replica. |
| “Hai partition khác nhau có thể dùng cùng một nhóm replica.” | **Đúng** | Nhiều token/partition range có thể được ánh xạ tới cùng nhóm node replica. |
| “Một node vừa có thể làm coordinator, vừa là replica.” | **Đúng** | Hai vai trò xác định theo request và partition, không loại trừ nhau. |

## 10. Bài tập tự kiểm tra có đáp án

**Bài 1.** Một DC có 5 node, mỗi node được gán 16 token, RF = 3. Hỏi tổng token được gán và số bản sao mục tiêu của một partition?

**Đáp án:** `5 × 16 = 80` vị trí token; **3 replica** trên ba node khác nhau. Không suy ra 80 bản sao.

**Bài 2.** Cluster có `dc1`: 4 node và `dc2`: 3 node; mỗi node 8 token. Keyspace cấu hình `NetworkTopologyStrategy` với RF `dc1 = 3`, `dc2 = 2`. Hỏi số node cluster, số vị trí token và số bản sao của một partition?

**Đáp án:** **7 node**, `7 × 8 = 56` token được gán và **5 replica** của mỗi partition (3 ở dc1, 2 ở dc2), khi cluster đáp ứng topology.

**Bài 3.** Một partition có ba replica N1/N2/N3, còn N4 không giữ partition đó. N1 và N2 đang hoạt động, N3 lỗi. Request `LOCAL_QUORUM` đến N4 có thể thành công không?

**Đáp án:** **Có thể**, nếu N1 và N2 thuộc DC cục bộ, trả phản hồi đúng hạn và không có lỗi khác. N4 điều phối request nhưng không là ACK replica thứ ba.

**Bài 4.** Đội vận hành muốn tăng mức chịu lỗi cho dữ liệu nhưng chỉ tăng `num_tokens` từ 8 lên 32, giữ nguyên số node và RF = 2. Kết quả là gì?

**Đáp án:** Số vị trí token/node có thể tăng nếu được thay đổi theo quy trình hợp lệ, nhưng **mỗi partition vẫn chỉ có hai replica**. Muốn tăng bản sao cần cân nhắc tăng RF và đảm bảo đủ node, sau đó đồng bộ dữ liệu theo quy trình phù hợp.

## 11. Bảng ghi nhớ cuối bài

| Muốn biết… | Hãy kiểm tra… |
| --- | --- |
| **Có bao nhiêu máy Cassandra?** | Số node theo DC/rack qua topology và `nodetool status`. |
| **Một node sở hữu bao nhiêu vị trí trên vòng?** | Danh sách token của node, `Tokens` trong `nodetool status`, hoặc `nodetool ring`. |
| **Một partition có bao nhiêu bản sao?** | RF của keyspace theo DC và các endpoint thực tế của partition. |
| **Một read/write cần chờ bao nhiêu phản hồi?** | Consistency level **của request** và RF tại phạm vi tương ứng. |
| **Vì sao thêm node mà RF không đổi?** | Node và token quyết định khả năng phân bổ tải; RF được khai báo ở keyspace. |

**Chuỗi suy luận cần nhớ:** *partition key → token → token range → tập replica theo replication strategy và topology → số phản hồi phải chờ theo consistency level*. Đây là cách đọc chính xác ba con số **số nút, số token, số bản sao** khi thiết kế và vận hành Cassandra.
