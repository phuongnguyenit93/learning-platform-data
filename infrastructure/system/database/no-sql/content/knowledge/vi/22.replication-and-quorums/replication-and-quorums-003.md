# Replication factor và vị trí đặt bản sao theo nút/rack/datacenter

Trong cơ sở dữ liệu NoSQL phân tán, lưu một bản ghi ở **một máy** khiến dữ liệu và khả năng phục vụ phụ thuộc vào máy đó. Khi máy hỏng, ổ đĩa lỗi hoặc mạng tới máy bị ngắt, ứng dụng có thể không đọc hoặc ghi được nữa. Một phương án phổ biến là **replication**: duy trì nhiều bản sao của dữ liệu trên các máy khác nhau.

Tuy nhiên, **ba bản sao không tự đồng nghĩa với chịu được mọi sự cố**. Nếu ba node nằm cùng một rack và cùng dùng một switch, mất nguồn hoặc mạng của rack có thể ảnh hưởng đồng thời cả ba. Nếu chúng nằm trên ba rack nhưng cùng một datacenter, một sự cố toàn datacenter vẫn có thể làm tất cả mất khả năng phục vụ.

Vì vậy, thiết kế replication phải trả lời **hai câu hỏi gắn chặt với nhau**:

1. **Replication factor (RF) là bao nhiêu?** Mỗi phần dữ liệu có bao nhiêu bản sao dự kiến trong một phạm vi?
2. **Replica được đặt ở đâu?** Các bản sao phân bố ra những node, rack, availability zone, datacenter hoặc region nào?

Câu hỏi thứ ba nối chủ đề này với **quorum**: **một lần đọc/ghi cần bao nhiêu replica xác nhận hoặc tham gia để trả kết quả?**

Bài học trình bày cách tính RF và quorum, lý do cần placement theo failure domain, ví dụ cấu hình Apache Cassandra, so sánh với MongoDB và managed NoSQL, cách thay đổi RF, phục hồi replica, quy hoạch dung lượng và các bài tập thiết kế chịu lỗi.

> **Lưu ý về phạm vi:** thuật ngữ `RF`, `rack`, `datacenter` và thuật toán đặt replica có ý nghĩa cụ thể trong từng DBMS. Cassandra cho phép cấu hình RF theo datacenter trong `NetworkTopologyStrategy`; nhiều dịch vụ fully managed không cho người dùng chọn trực tiếp node/rack hoặc khai RF bằng cùng API. Luôn xác định sản phẩm và phạm vi trước khi kết luận.

## 1. Replica là gì?

Giả sử có document:

~~~json
{
  "orderId": "O-801",
  "customerId": "C-42",
  "status": "PAID",
  "totalMinor": 275000
}
~~~

Nếu chỉ được lưu trên Node A:

~~~text
Client → Node A → order:O-801
              │
              X  Node A hỏng
       Không còn bản sao trực tuyến
~~~

Nếu được sao ra ba node:

~~~text
                        Client
                          │
                      Coordinator
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
          Node A        Node B        Node C
          copy 1        copy 2        copy 3
          O-801         O-801         O-801
~~~

Một node hỏng **không nhất thiết** làm mất khả năng phục vụ, **nếu** các node còn lại chứa dữ liệu cần thiết, có thể liên lạc, và consistency/commit protocol cho phép thao tác tiếp tục.

### Các bản sao không nhất thiết giống nhau ngay lập tức

~~~text
Node A: status=SHIPPED, version=12
Node B: status=PAID,    version=11
Node C: status=SHIPPED, version=12
~~~

Nếu replication bất đồng bộ, B có thể đang chậm. Hệ cần có cơ chế quyết định:

- Phiên bản nào được xem là hợp lệ.
- Read được phép trả bản cũ trong trường hợp nào.
- Write được ACK ở mốc nào.
- Replica chậm sẽ bắt kịp bằng cách nào.
- Xử lý hai write đồng thời/xung đột ra sao.

**Replication làm tăng số bản sao; nó không tự tạo ra một mô hình nhất quán, durability và xử lý xung đột hoàn chỉnh.**

## 2. Replication factor (RF) là số gì?

**Replication factor** thường là số replica dự kiến cho một phần dữ liệu **theo phạm vi của replication strategy**.

~~~text
RF=1: mỗi partition có một bản sao.
RF=2: mỗi partition có hai bản sao.
RF=3: mỗi partition có ba bản sao.
~~~

Với Apache Cassandra và `NetworkTopologyStrategy`:

~~~text
dc_hcm: RF=3
dc_hn:  RF=3

Mục tiêu:
  3 bản sao mỗi partition ở dc_hcm
  3 bản sao mỗi partition ở dc_hn
  Tổng dự kiến: 6 bản sao mỗi partition qua hai DC
~~~

Đừng nói “RF của cả cluster là 3” nếu cấu hình cho **mỗi DC** là 3.

### Configured RF khác số bản sao đang sử dụng được

Khi cấu hình RF=3:

~~~text
Assigned replicas: A, B, C
Current health:     A=UP, B=UP, C=DOWN
~~~

RF vẫn là 3 trong metadata; **chỉ có hai bản sao đang reachable**. Ngay cả khi C trở lại và health check báo UP, C có thể còn lag.

Phải phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Configured RF** | Mục tiêu số replica theo chiến lược |
| **Assigned replica set** | Các node mà topology chọn cho một partition/token range |
| **Reachable replicas** | Những node có thể giao tiếp được |
| **Healthy replicas** | Những node đạt điều kiện vận hành |
| **Up-to-date replicas** | Những bản sao có trạng thái/phiên bản phù hợp |

Một dashboard chỉ hiện số node UP không cho biết chắc mọi replica đã đồng bộ đầy đủ.

## 3. Node, rack, availability zone, datacenter và region

Khi nói “đặt bản sao ở máy khác”, cần hỏi **máy khác có thực sự độc lập về hạ tầng không?**

| Failure domain | Diễn giải | Ví dụ lỗi tương quan |
| --- | --- | --- |
| **Process** | Một tiến trình DBMS | Process crash, out-of-memory |
| **Disk/volume** | Thiết bị/volume lưu trữ | Lỗi disk, volume mất |
| **Node/host/VM** | Máy/instance chạy DBMS | Kernel panic, reboot, lỗi host |
| **Rack** | Nhóm máy chia sẻ một số thiết bị nguồn/mạng | Mất nguồn rack, ToR switch lỗi |
| **Availability zone (AZ)** | Miền lỗi của cloud provider | Sự cố hạ tầng ở AZ |
| **Datacenter (DC)** | Trung tâm hoặc topology domain được DBMS định danh | Mất mạng/nguồn toàn DC |
| **Region** | Vùng hạ tầng địa lý/quản trị | Sự cố quy mô vùng, mất kết nối liên vùng |

### Rack không luôn bằng AZ

Một rack vật lý là tủ máy. Một cloud AZ có thể bao gồm nhiều rack và các thành phần hạ tầng khác. Tuy nhiên, trong một số DBMS, operator có thể **gán nhãn rack logic theo AZ** để replication strategy phân tán replica trên các AZ:

~~~text
Cloud region X:
  AZ-1 → rack-label "az1"
  AZ-2 → rack-label "az2"
  AZ-3 → rack-label "az3"
~~~

Đó là **quy ước ánh xạ topology**, không phải khẳng định một AZ chỉ có một rack.

### DC trong DBMS là một đơn vị cấu hình

Trong Cassandra, tên `dc_hcm` có thể là một **datacenter logic** được gắn bởi snitch. Tên đó cần ánh xạ chính xác tới hạ tầng thực:

~~~text
Cassandra DC: dc_hcm
  Rack/zone A → Nodes a1, a2
  Rack/zone B → Nodes b1, b2
  Rack/zone C → Nodes c1, c2
~~~

Đừng tự suy rằng tên DC trong DBMS luôn là đúng một tòa nhà hoặc luôn trùng với một cloud region. **Ngữ nghĩa và ranh giới phải được ghi trong tài liệu topology.**

## 4. Failure domain và lỗi tương quan

Xét hai cách đặt ba replica:

~~~text
Phương án A — cùng rack
  Rack R1:
    Node A → copy 1
    Node B → copy 2
    Node C → copy 3

Phương án B — ba rack
  Rack R1: Node A → copy 1
  Rack R2: Node B → copy 2
  Rack R3: Node C → copy 3
~~~

Nếu một node hỏng, cả A và B có thể còn hai replica. Nhưng nếu **Rack R1 mất nguồn**:

- Phương án A có thể mất khả năng truy cập cả ba bản sao.
- Phương án B có thể vẫn còn bản sao ở R2 và R3.

Đây là sự khác biệt giữa **lỗi độc lập** và **lỗi có tương quan**.

### Anti-affinity là gì?

**Anti-affinity** là chính sách cố gắng hoặc bắt buộc đặt replica của **cùng dữ liệu** ở các failure domain khác nhau.

~~~text
Partition P
   ├── Replica 1 → rack-a
   ├── Replica 2 → rack-b
   └── Replica 3 → rack-c
~~~

Mục tiêu:

1. Tránh mất nhiều replica vì một lỗi rack/zone.
2. Tăng cơ hội còn đủ quorum.
3. Giảm ảnh hưởng của bảo trì một failure domain.
4. Phân bố một phần I/O/đường khôi phục trên nhiều vị trí.

Nếu chỉ có **hai rack** trong DC nhưng RF=3, không thể có ba replica **mỗi replica ở một rack riêng**. Hệ có thể phải bố trí trùng rack hoặc xử lý theo giới hạn thuật toán; **không được coi RF=3 là bằng chứng chịu lỗi mất mọi rack**.

## 5. Replica placement dùng dữ liệu đầu vào nào?

Một storage engine phân tán có thể xác định replica qua:

~~~text
Partition key
    │
    ▼
Hash/token hoặc range mapping
    │
    ▼
Danh sách node và token ownership
    │
    ▼
Replication strategy + RF + topology labels
    │
    ▼
Replica set cho partition/token range
~~~

Ví dụ:

~~~text
Partition = (tenant:T17, customer:C42)
Token = hash(partition key)

Placement theo topology:
  Node A1 / dc_hcm / rack-a
  Node B2 / dc_hcm / rack-b
  Node C1 / dc_hcm / rack-c
~~~

Đây là **minh họa kết quả**, không phải mapping cố định cho mọi partition. Những partition khác có thể chọn node khác tùy token range và thuật toán.

### Phân biệt vai trò

- **Replica:** nơi lưu bản sao.
- **Leader/primary:** nơi điều phối/nhận ghi có quyền theo một số giao thức.
- **Coordinator:** node tiếp nhận request, phối hợp các replica.
- **Token owner:** node gắn với một hay nhiều phạm vi token.

Không dùng các khái niệm trên thay nhau khi so sánh Cassandra, MongoDB hoặc dịch vụ managed.

## 6. RF và khả năng chịu mất node

Giả sử RF=3, ba replica nằm trên ba node:

~~~text
Ban đầu: A=UP, B=UP, C=UP
Sau lỗi: A=DOWN, B=UP, C=UP
~~~

Về **số bản sao còn lại**, hệ có hai. Nhưng request có thành công hay không còn phụ thuộc:

- Read/write consistency level.
- Quorum/commit protocol.
- Network connectivity.
- Dữ liệu của các replica còn sống.
- Leader/epoch/transaction status.

Không được đồng nhất **RF** với **số ACK bắt buộc**.

### Majority quorum

Trong một nhóm `N` replica, số phiếu tối thiểu cho **strict majority** là:

\[
Q(N)=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

| Số replica N | Majority Q(N) | Số replica lỗi tối đa còn đủ majority, giả sử những node còn lại liên lạc và có quyền |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

Đây là **bảng toán học về số lượng**, chưa xét lỗi rack/DC tương quan. Chưa thể suy từ bảng rằng một DBMS chắc chắn phục vụ thành công vì giao thức có thể yêu cầu thêm điều kiện.

### Vì sao RF chẵn không tự tăng số lỗi majority chịu được?

~~~text
RF=3 → majority=2 → chịu được mất 1 replica theo số đếm
RF=4 → majority=3 → chịu được mất 1 replica theo số đếm
RF=5 → majority=3 → chịu được mất 2 replica theo số đếm
~~~

Tăng RF từ 3 lên 4 trong giao thức strict majority **không tăng số replica được phép mất**. Nhưng không nên kết luận RF chẵn luôn vô ích: loại replica, topology, mục tiêu đọc, multi-DC và consistency options có thể có lý do riêng.

## 7. R, W, N: quorum đọc/ghi liên hệ với RF

Một cách phân tích trong hệ replication là:

- `N`: số replica trong tập đang xét.
- `R`: số replica cần tham gia read.
- `W`: số replica cần xác nhận write.

Điều kiện thường gặp:

\[
R+W>N
\]

nói rằng **một tập đọc R node và một tập ghi W node cố định** trong cùng nhóm N node phải có ít nhất một thành viên giao nhau.

Ví dụ:

~~~text
N=3, W=2, R=2

Write x=1 được A và B xác nhận:
  A: x=1
  B: x=1
  C: x=0

Read từ B và C:
  B trả 1
  C trả 0
~~~

Nếu giao thức có quy tắc version đúng, read có thể dùng thông tin từ B để biết có giá trị mới.

**Điều quan trọng:** `R+W>N` **không tự chứng minh linearizability**. Phải xét concurrent writes, version order, partial writes, sloppy quorum, membership change, commit semantics và conflict resolution. Một quorum set giao nhau chỉ là một thành phần của protocol.

## 8. RF khác quorum và khác durability

~~~text
Configured RF = 3

Write ACK policy = ONE, QUORUM hoặc ALL tùy hệ
Read policy      = ONE, QUORUM, STRONG... tùy hệ
~~~

RF xác định **số nơi dự kiến có dữ liệu**. Consistency/write concern xác định **khi nào được trả kết quả**.

Nếu một write chỉ cần một replica trả ACK, nó có thể có độ trễ thấp hơn, nhưng mức chịu lỗi trước khi dữ liệu được đưa tới những replica khác có thể khác write cần majority/ALL.

### Durability là một trục khác

Ngay cả khi một replica báo đã nhận write, cần hỏi:

- Đã ghi WAL/commit log theo mốc durable chưa?
- Có cần flush/sync thiết bị không?
- Những replica ACK đã ghi bền đến mức nào?
- Nếu node hỏng vật lý trước replication, bản nào còn?

**Replication factor không quyết định tự động chính sách WAL, ACK hay khả năng khôi phục dữ liệu.**

## 9. Cassandra: RF được cấu hình theo keyspace

Apache Cassandra cho phép cấu hình replication strategy trong **keyspace**, không phải bắt ứng dụng viết cùng record nhiều lần.

Ví dụ:

~~~sql
CREATE KEYSPACE ecommerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hcm': 3,
    'dc_hn': 3
}
AND durable_writes = true;
~~~

Ý nghĩa:

~~~text
Keyspace ecommerce

Trong dc_hcm:
  target RF=3 cho mỗi partition

Trong dc_hn:
  target RF=3 cho mỗi partition
~~~

**Tên datacenter phải khớp đúng với topology mà các node trong cluster khai báo**. Nếu tên DC khác, không được coi đoạn cấu hình minh họa có thể áp dụng nguyên xi.

### Một bảng dùng keyspace đó

~~~sql
CREATE TABLE ecommerce.orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, customer_id),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Partition key là `(tenant_id, customer_id)`. Token/replication strategy quyết định những replica lưu partition của từng khách hàng.

Ứng dụng chỉ thực hiện mutation logic vào bảng; Cassandra phân phối mutation tới những node replica theo protocol.

## 10. NetworkTopologyStrategy và rack-aware placement

Một DC minh họa:

~~~text
dc_hcm
  rack-a: node-a1, node-a2
  rack-b: node-b1, node-b2
  rack-c: node-c1, node-c2

Replication factor: 3
~~~

`NetworkTopologyStrategy` dùng topology/tokens để chọn replica và **cố gắng phân bố qua rack khác nhau khi điều kiện cho phép**, theo chi tiết thuật toán phiên bản.

Một partition có thể được đặt:

~~~text
Partition P
  node-a1 / rack-a
  node-b2 / rack-b
  node-c1 / rack-c
~~~

Một partition khác có thể nằm trên các node khác. Không nên ghi tĩnh “mọi dữ liệu ở a1, b2, c1” khi chưa xem token map.

### Nếu số rack nhỏ hơn RF?

~~~text
RF=3
Available distinct racks=2
~~~

Không thể có ba rack duy nhất cho ba replica trong cùng DC. Placement engine có thể chọn theo khả năng thực tế, làm giảm khả năng chống lỗi rack so với mục tiêu mong muốn.

**Thiết kế nên bắt đầu từ số failure domain độc lập**, không chỉ đếm node.

## 11. Snitch: topology đúng mới có placement đúng

Trong Cassandra, **snitch** là cơ chế thông báo hoặc xác định node thuộc datacenter/rack nào. Replication/routing sử dụng thông tin đó.

Ví dụ hợp lý:

~~~text
node-a1 → dc_hcm / rack-a
node-b1 → dc_hcm / rack-b
node-c1 → dc_hcm / rack-c
~~~

Ví dụ có nguy cơ:

~~~text
node-a1 → dc_hcm / rack-default
node-b1 → dc_hcm / rack-default
node-c1 → dc_hcm / rack-default
~~~

Nếu chúng thực ra nằm ở ba AZ khác nhau nhưng đều được gán chung rack, placement policy **không thấy đúng sự phân biệt mà đội vận hành kỳ vọng**.

Ngược lại, nếu cả ba host cùng switch/nguồn nhưng bị gán thành ba rack, metadata tạo ra **ảo tưởng failure-domain independence**.

### Checklist thông tin topology

1. Mỗi node có DC/rack label đúng với hạ tầng thực.
2. Tên DC được dùng đúng trong keyspace replication map.
3. Các labels đủ độc lập để đạt mục tiêu chống lỗi.
4. Có đủ node và rack để thuật toán chọn bản sao.
5. Thay DC/rack labels được thực hiện theo quy trình migration của DBMS, không chỉ sửa text tùy ý trên production.
6. Replica map thực tế được quan sát, không suy đoán từ schema.

## 12. Token ring và virtual nodes (vnodes)

Trong Cassandra, partition key được biến thành **token**. Các node sở hữu những miền token; replication strategy dùng token ownership và topology để chọn replica.

~~~text
Partition key
     │
     ▼
Partitioner → token
     │
     ▼
Token range / owners
     │
     ▼
Replica placement
~~~

**Virtual nodes (vnodes)** cho phép một node sở hữu nhiều token ranges, góp phần giúp phân bố và rebalance. Nhưng:

- Vnodes không biến RF=3 thành dữ liệu nằm trên tất cả node.
- Vnodes không bảo đảm mọi partition cùng kích thước.
- Hot key/hot partition vẫn có thể tạo skew.
- Việc thay node có thể cần streaming nhiều token ranges.

Đo data bytes/node, token ownership, hot partitions, compaction/repair backlog và network load khi đánh giá placement.

## 13. LOCAL_QUORUM trong Cassandra nhiều DC

Xét:

~~~text
dc_hcm: RF=3
dc_hn:  RF=3
~~~

### LOCAL_QUORUM

Với ba replica thuộc **DC local**, ngưỡng majority theo số học là:

\[
Q_{local}(3)=2
\]

Vì vậy `LOCAL_QUORUM` trong DC có RF=3 đòi hỏi điều kiện xác nhận tương ứng của **hai replica ở DC local**, chứ không mặc định chờ 4/6 replica của cả hai DC.

### QUORUM

Nếu xét tổng `N=6` replica cho key trong cấu hình trên, majority toàn nhóm là:

\[
Q(6)=4
\]

Ngữ nghĩa của `QUORUM` và lựa chọn replica cụ thể thuộc Cassandra protocol. Không thay nó bằng một vòng lặp giả định “lấy bốn ACK từ bất kỳ node nào” rồi coi là cách triển khai đúng.

### EACH_QUORUM

Trong các thao tác mà Cassandra hỗ trợ mức `EACH_QUORUM`, yêu cầu được xét **theo từng DC**. Với RF=3 ở mỗi DC, ngưỡng majority là hai replica ở mỗi DC. Đây là hướng ghi có thể phụ thuộc vào cả WAN và mức sẵn sàng của các DC.

**Tính năng và operation hỗ trợ mức consistency cần đối chiếu theo Cassandra version/driver.** Không suy từ tên mức mà cho rằng read và write đều hỗ trợ y hệt nhau.

| Cấu hình | Phạm vi số học | Majority |
| --- | --- | ---: |
| RF=3, một DC | 3 local replicas | 2 |
| RF=5, một DC | 5 local replicas | 3 |
| RF=3+3, toàn hai DC | 6 total replicas | 4 |
| RF=3+3, từng DC | 3 replica ở mỗi DC | 2 ở mỗi DC |

## 14. Placement quyết định còn đủ LOCAL_QUORUM khi mất rack hay không

**Cách bố trí 1 — một replica mỗi rack:**

~~~text
DC HCM, RF=3

Rack A: Replica A
Rack B: Replica B
Rack C: Replica C

Mất Rack A → còn B,C → 2 replicas
~~~

Nếu B,C reachable và protocol cho phép, chúng còn đủ ngưỡng local majority 2/3.

**Cách bố trí 2 — hai replica chung rack:**

~~~text
DC HCM, RF=3

Rack A: Replica A, Replica B
Rack B: Replica C
Rack C: không có replica P

Mất Rack A → còn C → 1 replica
~~~

Khi ấy không còn local majority.

**RF=3 không thể bảo vệ khỏi lỗi rack nếu placement tạo ra hai replica chung failure domain.**

## 15. RF theo mục tiêu chịu lỗi: tính từ kịch bản

Thay vì chọn RF=3 vì đây là con số phổ biến, hãy làm:

1. Xác định lỗi phải chịu: một host, rack, AZ, DC hay region.
2. Xác định loại thao tác phải còn hoạt động: read catalog, strong read, write inventory, transaction.
3. Xác định quorum/commit rule của giao thức.
4. Đặt replica trên đủ failure domains độc lập.
5. Kiểm tra sau mỗi lỗi còn bao nhiêu replica có thể phối hợp.
6. Tính storage, traffic, latency và thời gian repair/rebuild.

### Ví dụ chịu một rack

~~~text
Goal: mất một rack vẫn đáp ứng strong operations theo majority.
Placement: RF=3 ở ba rack độc lập.
Quorum: 2/3.

Mất một rack → còn hai replica.
~~~

Kết luận **có thể** tiếp tục nếu các điều kiện khác (network, leader, dữ liệu, protocol) đúng.

### Ví dụ chịu hai rack

Nếu RF=3 ở ba rack, mất hai rack để lại một replica — không đủ majority. Một thiết kế sơ bộ như RF=5 ở **năm failure domains độc lập**, majority=3, có thể chịu tối đa hai replica/failure domains lỗi theo số học. Nhưng cần kiểm tra thuật toán placement và loại failure domain thực tế.

Chỉ tăng RF lên 5 trong **ba rack** không tạo ra năm failure domains.

## 16. Công thức xác suất chỉ đúng dưới giả định độc lập

Nếu mỗi replica có xác suất hỏng `p` độc lập trong một khoảng thời gian, xác suất **tất cả N replica hỏng** là:

\[
P(\text{all replicas fail})=p^N
\]

Ví dụ `p=0.01` và `N=3`:

\[
0.01^3=0.000001
\]

Đây là phép tính minh họa, **không phải SLA thực tế**. Nếu cả ba replica chung rack, một lỗi nguồn/switch có thể làm cả ba cùng mất khả năng truy cập; giả định độc lập bị phá.

### Xác suất mất majority trong RF=3

Với majority=2, mất quorum khi ít nhất hai replica lỗi. Dưới giả định lỗi độc lập:

\[
P(\text{no majority})
=3p^2(1-p)+p^3
\]

Nếu `p=0.01`:

\[
P(\text{no majority})=0.000298
\]

Tương đương khoảng **0,0298% trong mô hình toán học đơn giản**.

Không dùng công thức này để dự đoán uptime production nếu chưa tính network partition, lỗi tương quan, sửa chữa, thời gian bảo trì, sự cố operator và cơ chế failover.

## 17. RF hai datacenter và mất cả DC

Giả sử:

~~~text
dc_hcm: RF=3
dc_hn:  RF=3
~~~

Mất toàn DC HCM:

~~~text
dc_hcm: X X X
dc_hn:  UP UP UP
~~~

Về mặt thiết kế bản sao, mỗi partition có các replica tại DC HN. Nhưng câu hỏi **dịch vụ có tiếp tục được không?** còn phụ thuộc:

1. Client/router có thể chuyển sang DC HN không?
2. Dữ liệu đã được đồng bộ tới HN đến mốc nào?
3. Write trước đây ACK bằng local quorum hay yêu cầu liên DC?
4. Read/write sau failover có đổi consistency level không?
5. Leader/quorum/state machine có quyền commit an toàn tại HN không?
6. Những phụ thuộc DNS, auth, secrets, payment, search, backup có còn hoạt động không?

### RPO và RTO

- **RPO (Recovery Point Objective):** mức mất dữ liệu có thể chấp nhận khi phục hồi.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

RF trên hai DC hỗ trợ chiến lược dự phòng nhưng **không tự đảm bảo RPO=0, RTO=0**. Nếu replication xuyên vùng bất đồng bộ, một số ghi đã ACK tại nguồn có thể chưa đến vùng dự phòng khi nguồn hỏng.

## 18. Local writes, cross-DC writes và WAN latency

Ghi chỉ yêu cầu điều kiện local:

~~~text
Client HCM
   │
   ▼
DC HCM quorum → ACK
   │
   └── Replication tới DC HN theo giao thức
~~~

có thể tránh phải chờ mọi round trip liên vùng trước khi phản hồi. Đổi lại, read ở DC HN có thể tạm stale theo mô hình.

Ghi yêu cầu điều kiện cả hai DC:

~~~text
Client HCM
   │
   ├── Local replicas HCM
   └── Remote replicas HN qua WAN
            │
     Đợi điều kiện commit
            ▼
           ACK
~~~

có thể đưa WAN latency và availability của DC HN vào đường ghi.

**Không có lựa chọn đúng cho mọi tính năng.**

- Dashboard có thể chấp nhận dữ liệu tới muộn.
- Giỏ hàng có thể chấp nhận hội tụ/merge.
- Cấp quyền sở hữu duy nhất có thể cần một điểm quyết định chặt.
- Thanh toán cần idempotency và giao thức đảm bảo số dư/trạng thái.

Lựa chọn phụ thuộc **hợp đồng nghiệp vụ** chứ không chỉ tối ưu latency trung bình.

## 19. Data residency và tuân thủ

Đặt bản sao sang DC/region khác có thể chịu các giới hạn:

- Chính sách khách hàng/tenant.
- Quy định về vị trí lưu dữ liệu cá nhân.
- Hợp đồng chia sẻ dữ liệu.
- Yêu cầu mã hóa và quản lý khóa.
- Quyền truy cập của nhân sự vận hành vùng khác.

Ngoài replica của bảng chính, cần kiểm tra:

~~~text
Backups/snapshots
Search indexes
CDC / event stream
Logs chứa payload
Temporary export
DR staging
Analytics warehouse
~~~

Không được chỉ nhìn CQL RF rồi khẳng định dữ liệu chắc chắn không rời một vùng.

## 20. Capacity planning: sao chép tốn dung lượng thế nào?

Một ước lượng đơn giản:

\[
\text{Replicated data size}
\approx \text{Logical live data size}\times RF
\]

Ví dụ dataset logic **2 TiB**, RF=3 trong một DC:

\[
2\ \text{TiB}\times 3=6\ \text{TiB}
\]

Nếu DC có 6 node, trung bình theo số học:

\[
6\ \text{TiB}/6=1\ \text{TiB/node}
\]

Nhưng đây **không phải mức disk thực tế tối đa** vì còn:

- Index và metadata.
- WAL/commit log.
- Tombstones, versions, compaction temporary space.
- Snapshot/backup.
- Compression và block overhead.
- Disk/data skew, hot partitions.
- Headroom khi rebuild hoặc thay node.

Một cụm có tổng dung lượng vừa bằng dữ liệu replicated có thể không đủ chỗ **compaction/streaming để phục hồi sau lỗi**. Dự phòng capacity và băng thông là phần của fault tolerance.

## 21. Tăng RF không có nghĩa latency tăng tuyến tính

Một logical write có thể được gửi song song:

~~~text
                   Coordinator
                  /     |     \
               Node A Node B Node C
~~~

RF tăng thường tăng **tổng lượng dữ liệu/traffic/I/O** mà cụm phải xử lý. Nhưng latency request phụ thuộc:

- Số replica cần ACK.
- Có chờ WAN hay không.
- Disk/WAL latency.
- Network RTT.
- Compaction/backpressure.
- Contention trên key.

Vì vậy không có định luật “RF=3 thì mỗi write chậm đúng ba lần RF=1”. Phải đo throughput bền vững và p95/p99 dưới workload thực, đồng thời kiểm tra lượng dữ liệu lưu.

## 22. Repair, hint và replica chậm

Giả sử:

~~~text
T0: A/B/C đều version=10
T1: C offline
T2: A/B nhận nhiều write tới version=14
T3: C online, vẫn version=10
~~~

Node C không tự thành version 14 chỉ vì health check chuyển sang UP. Các cơ chế tùy DBMS có thể gồm:

- Streaming/log catch-up.
- Hinted handoff.
- Read repair trong những trường hợp hỗ trợ.
- Anti-entropy repair.
- Rebuild/replace node.

### Hinted handoff không thay thế repair

Trong Cassandra, hinted handoff có thể lưu lại thông tin mutation cho replica tạm offline trong điều kiện/giới hạn nhất định, rồi gửi lại. Nhưng hints có giới hạn thời gian/lưu trữ/điều kiện và không thay thế đầy đủ anti-entropy repair.

Nếu replica offline lâu, **vẫn cần quy trình sửa đồng bộ phù hợp**, đặc biệt với delete/tombstone.

### Tombstone và dữ liệu đã xóa

Một replica bỏ lỡ tombstone có thể còn value cũ. Nếu tombstone ở những nơi khác bị garbage-collect trước khi các bản sao cần thiết được sửa an toàn, có nguy cơ dữ liệu cũ tái xuất hiện trong một số lịch phục hồi.

Do đó, chính sách repair và vòng đời tombstone là một phần của replication correctness. Không tùy ý giảm grace period/dọn tombstone chỉ để tiết kiệm disk.

## 23. Bootstrap và decommission thay đổi replica map

Trước khi thêm node:

~~~text
Partition P → A, B, C
~~~

Sau khi mở rộng cluster, token ownership/placement có thể đổi:

~~~text
Partition P → A, C, D
~~~

Nhưng node D cần **nhận dữ liệu của P** trước khi được xem là bản sao hoàn chỉnh cho mục tiêu chịu lỗi.

Một quy trình thay topology ở mức khái niệm:

1. Xác minh cluster khỏe, RF, topology labels và repair status.
2. Kiểm tra capacity cho streaming và temporary compaction.
3. Thực hiện bootstrap/decommission theo công cụ và phiên bản được hỗ trợ.
4. Theo dõi network, disk, streaming, timeouts và latency.
5. Kiểm tra token/replica map và dữ liệu đã đồng bộ.
6. Chạy các bước xác minh/repair phù hợp.
7. Cập nhật monitoring, tài liệu DR và backup.

Đây **không phải checklist lệnh production**; từng DBMS có những thao tác và hạn chế riêng.

## 24. Thay RF trong Cassandra: metadata khác dữ liệu

Ví dụ đổi RF từ 2 lên 3:

~~~sql
ALTER KEYSPACE ecommerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hcm': 3,
    'dc_hn': 3
};
~~~

Sau câu lệnh:

~~~text
Mục tiêu replica có thể thay đổi trong schema/metadata.

Nhưng:
  New replica node chưa chắc đã có dữ liệu cũ.
~~~

Cần quy trình **repair/streaming và verification** theo Cassandra version để replica mới thực sự chứa dữ liệu cần thiết. Khi giảm RF cũng phải xem quy tắc ownership, cleanup và rủi ro giảm redundancy.

Phân biệt:

1. RF trong schema đã đổi.
2. Placement map đã được tính theo topology mới.
3. Bản sao mới **đã có dữ liệu đầy đủ và an toàn**.

Không báo “đã tăng resilience” chỉ vì bước 1 thành công.

## 25. Mất rack hoặc switch có thể làm nhiều replica không truy cập được

Topology:

~~~text
            Switch S1
             /  |  \
            A   B   C

RF=3, replicas ở A/B/C
~~~

Khi Switch S1 lỗi:

~~~text
A/B/C có thể vẫn chạy nhưng mất kết nối tới coordinator.
~~~

Đây là ví dụ **network failure domain**. Không phải mọi lỗi nguy hiểm đều là crash node. Phân bố replica trên ba máy nhưng chung switch/rack/nguồn có thể không bảo vệ được dịch vụ khỏi sự cố mạng đó.

Nếu đã trải trên nhiều rack, vẫn cần xét thiết bị mạng thượng tầng, gateway, DNS, authentication và những dependency có thể trở thành **single point of failure** của toàn dịch vụ.

## 26. Locality: replica gần chưa chắc mới nhất

Một read từ DC HCM có thể có RTT thấp hơn read xuyên DC. Nhưng nếu write mới nhất được ACK ở một vùng khác trước khi lan tới HCM, **replica local** có thể đang stale:

~~~text
DC HCM: x version=11
DC HN:  x version=12
~~~

Vì vậy:

- **Locality** tối ưu đường mạng/độ gần.
- **Consistency** quy định dữ liệu được phép đọc.
- **Session guarantees** như read-your-writes cần ngữ nghĩa riêng.

Khi thiết kế driver routing:

1. DC local của client/coordinator là gì?
2. Query dùng consistency level nào?
3. Có session token/version watermark không?
4. Failover sang DC khác khi local không còn phục vụ được ra sao?
5. Sau failover, request nào được phép đọc dữ liệu cũ?

Đừng để một thư viện tự route sang replica khác rồi vô tình làm người dùng thấy dữ liệu đi lùi.

## 27. MongoDB: replica set và vị trí data-bearing members

MongoDB có cơ chế **replica set** với primary/secondary và các quy tắc election/commit. Một topology ba availability zone:

~~~text
AZ-1: Primary P    (data-bearing)
AZ-2: Secondary S1 (data-bearing)
AZ-3: Secondary S2 (data-bearing)
~~~

Placement trên các failure domains độc lập có thể giúp duy trì những bản sao dữ liệu và điều kiện bầu primary/failover theo quy tắc MongoDB.

### Voting members không luôn là data replicas

Một **arbiter** có thể bỏ phiếu trong replica set nhưng **không lưu bản sao dữ liệu người dùng**.

~~~text
AZ-1: Primary       → có data
AZ-2: Secondary     → có data
AZ-3: Arbiter       → không có user data
~~~

Vì thế **ba members không nhất thiết bằng ba bản sao dữ liệu**.

Nếu AZ-1 và AZ-2 cùng hỏng, arbiter không thể phục hồi documents. Phải phân biệt:

- Số **data-bearing replicas**.
- Số **voting members**.
- Election majority.
- Write concern và durability.
- Read concern/read preference.

Không thể chuyển công thức RF của Cassandra sang MongoDB chỉ bằng cách đếm các thành viên.

## 28. DynamoDB: managed placement không giống RF tự cấu hình

Ở một dịch vụ NoSQL fully managed như DynamoDB, nhà cung cấp quản lý replication và placement trong phạm vi dịch vụ. Người dùng không tự gán:

~~~text
RF=3
Replica 1→rack-a
Replica 2→rack-b
Replica 3→rack-c
~~~

qua cùng cơ chế cấu hình Cassandra.

Thay vào đó, cần xem **bảo đảm và API chính thức** của dịch vụ:

- Phạm vi các failure domains được nhà cung cấp quản lý.
- Consistency options cho base table/index.
- Replication qua AWS Regions/global tables theo chế độ được sử dụng.
- Failover và routing của ứng dụng.
- Backup/PITR và residency.

Trong DynamoDB, GSI và các đường sao chép khác có ngữ nghĩa cập nhật riêng; không được suy ra “bảng nguồn đã commit thì mọi GSI ở mọi nơi đọc strong ngay”.

**Bài học chung:** managed service có thể cung cấp replication tốt nhưng mức **điều khiển số RF/vị trí node** của khách hàng không giống hệ tự vận hành.

## 29. RF không thay thế backup

Một lỗi thường gặp:

> “Chúng ta đã có ba bản sao, vậy không cần backup.”

Nhưng:

~~~text
Admin xóa nhầm bản ghi.
        │
        ▼
Delete được replication tới mọi replica.
        │
        ▼
Các bản sao đều phản ánh trạng thái đã xóa.
~~~

Replication bảo vệ **khả năng có bản sao trực tuyến**, không tự giữ phiên bản lịch sử trước mọi thao tác sai.

| Cơ chế | Vai trò |
| --- | --- |
| **Replication** | Phục vụ và chịu lỗi node/failure domain |
| **Repair/anti-entropy** | Đưa các bản sao về trạng thái phù hợp |
| **Backup/snapshot** | Phục hồi từ phiên bản độc lập khi xóa nhầm/corruption |
| **Restore drill** | Xác minh backup thực sự sử dụng được |
| **Audit/event log** | Truy vết và hỗ trợ một số quy trình đối soát |

Replication cũng có thể đồng bộ một thao tác sai sang mọi replica rất nhanh. **Backup độc lập và kiểm thử khôi phục là yêu cầu riêng.**

## 30. Active-active qua hai DC cần giải quyết xung đột

Giả sử người dùng ở hai DC đều ghi được cùng một document:

~~~text
DC-HCM                        DC-HN
address = "Da Nang"          address = "Da Nang"
     │                            │
write "Ha Noi"               write "Hue"
     │                            │
     └──── WAN partition ─────────┘
~~~

Sau khi mạng phục hồi, hệ phải quyết định:

- Giá trị nào được chọn?
- Có giữ lại cả hai version không?
- Dùng last-write-wins với metadata đáng tin?
- Merge theo field, theo operation hoặc cho người dùng giải quyết?
- Có audit log thể hiện thay đổi bị ghi đè?

**RF=3 mỗi DC không tự quy định conflict resolution**.

Với dữ liệu giỏ hàng, có thể merge các thao tác thêm sản phẩm. Với quota hoặc số dư, tự động last-write-wins có thể làm mất hiệu ứng nghiệp vụ. Nếu cần một quyền sở hữu duy nhất, phải dùng coordination/conditional write hoặc cơ chế cấp quyền thích hợp.

## 31. Failure matrix cho RF=3 trên ba rack

Giả sử một DC có RF=3, mỗi partition một replica trên mỗi rack, và một loại thao tác yêu cầu majority=2.

| Sự cố | Replica còn | Đủ majority theo số học? | Ghi chú |
| --- | --- | --- | --- |
| Một node hỏng | 2/3 | Có | Nếu hai replica khác reachable và protocol cho phép |
| Một rack hỏng | 2/3 | Có | Vì mỗi rack chỉ có một replica |
| Hai rack hỏng | 1/3 | Không | Có thể không phục vụ strong operations |
| Cả DC hỏng | 0/3 | Không tại DC đó | Cần DC dự phòng/DR |
| Mạng chia 2–1 | Nhóm 2 có hai | Có ở phía đủ quorum | Phía 1 không tự được commit trong giao thức majority mạnh |
| Một replica UP nhưng stale | Có 3 node | Phụ thuộc protocol | UP không nghĩa version mới |
| Vừa tăng RF nhưng chưa stream | Target 3, thực chưa đủ | Không suy ra | Phải xác minh dữ liệu |

Đây là **ma trận mô hình majorities**, không phải kết quả chắc chắn của mọi Cassandra CL hoặc MongoDB deployment.

## 32. Java: mô phỏng anti-affinity theo rack

Đoạn Java sau là **mô hình giáo dục** chọn tối đa một node trên mỗi rack trong một DC, rồi kiểm tra số replica còn sống sau lỗi rack. Nó **không phải thuật toán placement/token ring của Cassandra** và không triển khai quorum/replication thật.

Tạo file `ReplicaPlacementDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class ReplicaPlacementDemo {
    static final class Node {
        final String name;
        final String dc;
        final String rack;
        boolean up = true;

        Node(String name, String dc, String rack) {
            this.name = name;
            this.dc = dc;
            this.rack = rack;
        }
    }

    static List<Node> selectDistinctRacks(
            List<Node> nodes, String dc, int rf) {
        if (rf < 1) {
            throw new IllegalArgumentException("RF must be positive");
        }

        List<Node> selected = new ArrayList<>();
        Set<String> racks = new HashSet<>();

        for (Node node : nodes) {
            if (!dc.equals(node.dc)) {
                continue;
            }
            if (racks.add(node.rack)) {
                selected.add(node);
            }
            if (selected.size() == rf) {
                return selected;
            }
        }

        throw new IllegalStateException(
                "Not enough distinct racks for RF=" + rf);
    }

    static int majority(int rf) {
        return rf / 2 + 1;
    }

    static int reachableCount(List<Node> replicas) {
        int total = 0;
        for (Node node : replicas) {
            if (node.up) {
                total++;
            }
        }
        return total;
    }

    public static void main(String[] args) {
        List<Node> nodes = Arrays.asList(
                new Node("a1", "dc_hcm", "rack-a"),
                new Node("a2", "dc_hcm", "rack-a"),
                new Node("b1", "dc_hcm", "rack-b"),
                new Node("c1", "dc_hcm", "rack-c"),
                new Node("d1", "dc_hn", "rack-a")
        );

        int rf = 3;
        List<Node> replicas =
                selectDistinctRacks(nodes, "dc_hcm", rf);

        for (Node node : replicas) {
            System.out.println(node.name + " / " + node.rack);
        }
        System.out.println("Required majority=" + majority(rf));

        // Giả lập toàn rack-a mất khả năng phục vụ.
        for (Node node : replicas) {
            if ("rack-a".equals(node.rack)) {
                node.up = false;
            }
        }

        int reachable = reachableCount(replicas);
        System.out.println("Remaining replicas=" + reachable);
        System.out.println(
                "Enough by count=" + (reachable >= majority(rf)));
    }
}
~~~

Chạy trong một thư mục lab riêng:

~~~bash
javac ReplicaPlacementDemo.java
java ReplicaPlacementDemo
~~~

Output dự kiến:

~~~text
a1 / rack-a
b1 / rack-b
c1 / rack-c
Required majority=2
Remaining replicas=2
Enough by count=true
~~~

### Giới hạn ví dụ

- Không mô phỏng token ownership/vnodes.
- Không mô phỏng replica version hay WAL.
- Không mô phỏng network partition bất đối xứng.
- Không mô phỏng leader election, LWT, quorum protocol.
- Không xem disk usage, streaming hoặc data skew.

Kết quả “đủ theo số đếm” **không đồng nghĩa DBMS thực tế chắc chắn chấp nhận write**.

## 33. Tăng RF từ 3 lên 4 trên ba rack có thể không giúp chịu lỗi

Ban đầu:

~~~text
Rack A: replica A
Rack B: replica B
Rack C: replica C
RF=3, majority=2
~~~

Mất Rack A còn hai replica, đủ majority theo số học.

Nếu chỉ thêm một replica thứ tư vào Rack A:

~~~text
Rack A: replica A1, replica A2
Rack B: replica B
Rack C: replica C
RF=4, majority=3
~~~

Mất Rack A còn **hai**, không đủ majority 3/4.

Đây là **phản ví dụ khái niệm** cho suy nghĩ “tăng RF chắc chắn tăng resilience”. Nó không mô tả Cassandra chắc chắn chọn node A2; điều quan trọng là **quorum và placement phải được xét cùng nhau**.

## 34. Checklist trước khi chọn RF hoặc thêm DC

Hãy ghi rõ trong tài liệu kiến trúc:

1. **Partition/dataset nào cần replication?** Tất cả keyspace hay một tập?
2. **RF là per-DC hay per-cluster?** Theo semantics sản phẩm.
3. **Failure domain phải chịu là gì?** Host, rack, AZ, DC, region.
4. **Có bao nhiêu rack/AZ độc lập thực tế?** Topology labels có đúng không?
5. **Một partition được đặt trên những node nào?** Có replica map thật không?
6. **Mất một rack còn đủ quorum cho thao tác quan trọng?**
7. **Read/write ACK policy là gì?** Local/overall quorum, majority, strong...
8. **Nếu WAN partition, bên nào được commit?** Có conflict rules không?
9. **Các read từ DC khác có yêu cầu read-your-writes không?**
10. **RPO/RTO khi mất cả DC là gì?** Đã chạy DR drill chưa?
11. **Dung lượng, compaction, streaming và băng thông dự phòng đủ không?**
12. **Replica offline lâu được repair bằng cách nào?**
13. **Thay RF/topology có bước dữ liệu nào sau metadata change?**
14. **Backup/restore có tồn tại độc lập với replication không?**
15. **Data residency/backup/CDC có tuân thủ yêu cầu không?**
16. **Các dependency như DNS, auth, KMS có failure domain phù hợp không?**
17. **Có metrics cho lag, repair, node/rack health và p99 không?**
18. **Có fault injection cho node/rack/DC failure và partition không?**

Một con số RF đẹp trên sơ đồ chưa đủ; cần biến nó thành **hợp đồng chịu lỗi có thể kiểm chứng**.

## 35. Những nhận định sai thường gặp

| Nhận định | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “RF=3 chịu được ba node hỏng.” | Mất cả ba replica thì không còn bản sao; majority=2 chỉ chịu một replica lỗi theo số đếm | Tính quorum và số replica còn |
| “RF=3 chắc chắn ba rack.” | Topology có thể chỉ có hai rack hoặc metadata sai | Kiểm placement thực |
| “Ba node khác nhau chống được mất DC.” | Cả ba có thể nằm trong một DC | Đặt replica ở các DC thích hợp |
| “Node UP nghĩa là version mới.” | Replica có thể stale/chưa repair | Theo dõi freshness |
| “RF quyết định số ACK.” | Write/read concern cấu hình riêng | Xác định consistency level |
| “R+W>N tự chứng minh linearizability.” | Thiếu protocol xử lý concurrency, membership | Đánh giá toàn giao thức |
| “LOCAL_QUORUM của DC RF=3+3 cần 4.” | LOCAL_QUORUM theo một DC RF=3 cần 2 | Phân biệt local và overall |
| “ALTER RF là dữ liệu đã có ở node mới.” | Metadata có thể thay trước streaming | Repair/verification |
| “Hint thay thế repair.” | Hint có giới hạn | Lập repair policy |
| “RF=4 luôn tốt hơn RF=3 cho majority.” | Cả hai thường chỉ chịu một replica lỗi | Xét failure domains |
| “MongoDB 3 voting members có 3 bản sao.” | Arbiter không lưu user data | Đếm data-bearing members |
| “Managed NoSQL có cùng API RF/rack như Cassandra.” | Placement có thể do provider quản lý | Dùng hợp đồng tính năng thực |
| “RF nhiều DC nghĩa RPO=0.” | Cross-DC replication có thể async | Kiểm ACK, replication lag, DR |
| “RF thay thế backup.” | Xóa nhầm có thể nhân tới mọi bản sao | Backup và restore drill |
| “Nhiều replica loại mọi SPOF.” | Load balancer/auth/network có thể chung | Review toàn dependency graph |

## 36. Bài tập thực hành

### Bài 1 — Tính số bản sao theo DC

Keyspace Cassandra có:

~~~text
dc_hcm RF=3
dc_hn  RF=2
~~~

Mỗi partition có bao nhiêu bản sao dự kiến ở từng DC và tổng? Vì sao không gọi tổng này là “RF=3”?

**Gợi ý:** HCM 3, HN 2, tổng 5; RF được định nghĩa theo DC trong NetworkTopologyStrategy.

### Bài 2 — Placement trên ba rack

DC có `R1: N1,N2`, `R2: N3,N4`, `R3: N5,N6`. Chọn một bố trí RF=3 nhằm chịu mất một rack. Vì sao chọn N1,N2,N3 kém hơn?

**Gợi ý:** một replica ở mỗi rack, ví dụ N1,N3,N5.

### Bài 3 — Majority quorum

Tính `Q(N)` cho N=1,2,3,4,5,6,7. Với mỗi N, còn được phép mất mấy replica trước khi không đủ majority?

**Gợi ý:** `floor(N/2)+1`, nhưng phải giả định các replica còn sống liên lạc được.

### Bài 4 — RF chẵn và rack failure

RF=4, placement 2–1–1 trên ba rack, majority=3. Khi rack có hai replica bị mất, có thể còn majority không?

**Gợi ý:** chỉ còn 2, không đủ 3.

### Bài 5 — LOCAL_QUORUM hai DC

HCM và HN đều RF=3. Local majority là bao nhiêu trong mỗi DC? Nếu mất HCM, chỉ đổi client address sang HN có tự bảo đảm một transaction cũ đã được replicate đầy đủ không?

**Gợi ý:** local 2/3; phải xét write acknowledgment, lag và failover contract.

### Bài 6 — Snitch/rack labels

Ba node thực tế ở ba AZ nhưng đều được gắn rack label `default`. Những giả định về anti-affinity nào có thể không còn đúng?

**Gợi ý:** placement engine không nhìn thấy ba failure domains được mong muốn; cần xem cách sửa topology theo quy trình an toàn.

### Bài 7 — Đổi RF

Sau khi `ALTER KEYSPACE` từ RF=2 lên 3, operator báo “đã có ba bản sao dữ liệu”. Bạn cần xác minh điều gì?

**Gợi ý:** replica ownership mới, repair/streaming, data completeness, disk, timeouts.

### Bài 8 — Node offline lâu ngày

Replica C mất kết nối bốn ngày, A/B vẫn ghi, xóa và TTL. Khi C trở lại, tại sao chỉ nhìn trạng thái UP là chưa đủ?

**Gợi ý:** hint có giới hạn; tombstone, repair, version gap cần xem.

### Bài 9 — Tính dung lượng

Logical live data 4 TiB, RF=3, 8 node. Tính tổng replicated data trước overhead và trung bình per node. Nêu bốn loại headroom cần có.

**Gợi ý:** 12 TiB tổng, 1,5 TiB/node trung bình; thêm compaction, streaming, growth, skew.

### Bài 10 — Lỗi rack

RF=3, một replica mỗi rack. Lập ma trận khi mất một node, một rack, hai rack và toàn DC; thao tác cần majority=2.

**Gợi ý:** còn 2, 2, 1, 0 replica tương ứng.

### Bài 11 — R+W>N

Với N=5, R=3, W=3, kiểm tra giao nhau. Vì sao chưa thể tuyên bố toàn hệ linearizable?

**Gợi ý:** đồng thời ghi, version resolution, partial writes, membership, clock/network, commit.

### Bài 12 — MongoDB arbiter

Replica set có primary ở AZ1, secondary ở AZ2 và arbiter ở AZ3. Có mấy **data-bearing copies**? Arbiter giúp điều gì nhưng không giúp điều gì?

**Gợi ý:** hai bản sao dữ liệu; arbiter có vai trò voting nhưng không phục hồi user document.

### Bài 13 — Cross-region đọc sau ghi

Client ghi ở HCM rồi đọc ngay ở HN, nơi dữ liệu chưa bắt kịp. Nêu hai cách ứng dụng hoặc giao thức có thể đạt read-your-writes xuyên vùng.

**Gợi ý:** session watermark/chờ đủ version hoặc đường đọc/ACK mạnh hơn được DBMS hỗ trợ.

### Bài 14 — Một AZ duy nhất

Ba VM nằm trong cùng AZ, RF=3. Hệ có thể chịu hỏng một VM không? Có chịu mất cả AZ không?

**Gợi ý:** hai lỗi có phạm vi khác nhau.

### Bài 15 — Xác suất lỗi

Mỗi node lỗi độc lập với xác suất 1%. Tính xác suất tất cả ba replica lỗi nếu độc lập. Vì sao phép tính không áp dụng nguyên xi khi chúng cùng switch?

**Gợi ý:** `0.01^3=0.000001`; lỗi chung làm các biến cố không độc lập.

### Bài 16 — Active-active

Hai DC cùng ghi `customerAddress` khi WAN partition. RF=3 ở mỗi DC có tự quyết định địa chỉ nào thắng không?

**Gợi ý:** không; cần conflict semantics/version/merge theo nghiệp vụ.

### Bài 17 — Chịu mất hai rack

Hệ cần giữ majority khi mất hai rack độc lập. Hãy đề xuất topology giả định và RF hợp lý theo số học rồi nêu điều kiện cần xác minh ở DBMS thật.

**Gợi ý:** một mô hình RF=5 trên năm failure domains với majority=3; không phải luật bắt buộc cho mọi hệ.

### Bài 18 — RF và backup

Lệnh xóa nhầm được nhân bản tới cả năm replica. RF=5 có tự khôi phục dữ liệu trước khi xóa không?

**Gợi ý:** cần backup/PITR/restore có khả năng phục hồi phiên bản cũ.

### Bài 19 — Data residency

Tenant không cho phép dữ liệu cá nhân rời quốc gia A. Nhóm đề xuất backup và replica tại quốc gia B. Những điểm nào phải xem xét?

**Gợi ý:** hợp đồng/pháp lý, vị trí log/CDC, backup, mã hóa/quyền truy cập, DR nội vùng được phép.

### Bài 20 — Thiết kế cho ứng dụng đặt hàng

Hệ có hai DC, mỗi DC ba rack. Cần:

~~~text
RF=3 trong từng DC
Không bán vượt tồn
Chịu mất một rack ở DC local
Catalog read có thể stale
Order commit phải bảo vệ invariant
~~~

Hãy thiết kế:

1. Replica placement theo rack.
2. Consistency/conditional write cho inventory.
3. Read path cho catalog.
4. Failover và RPO/RTO khi mất DC.
5. Repair, backup và kiểm thử partition mạng.

**Gợi ý:** không dùng một consistency level duy nhất cho tất cả endpoint; phân biệt dữ liệu hiển thị, quyết định commit và đồng bộ xuyên DC.

## 37. Mẫu tài liệu quyết định replication

~~~yaml
dataset: "Order reservations"
database: "Product, deployment and version TBD"
replication:
  scope: "Per datacenter"
  strategy: "NetworkTopologyStrategy when Cassandra"
  datacenters:
    dc_hcm:
      replicationFactor: 3
      independentRacks: 3
    dc_hn:
      replicationFactor: 3
      independentRacks: 3
businessRequirements:
  - "No overselling"
  - "One accepted reservation per idempotency key"
faultModel:
  tolerate:
    - "One node failure in local DC"
    - "One rack failure in local DC"
  dcFailure:
    rpo: "TBD"
    rto: "TBD"
consistency:
  inventoryWrites: "Define authoritative conditional commit"
  catalogReads: "May use bounded/eventual freshness by contract"
  crossDcReadAfterWrite: "Define session version requirement"
operations:
  - "Verify replica mapping and rack labels"
  - "Plan headroom for rebuild/compaction"
  - "Monitor lag, repair and streaming"
  - "Maintain backup/restore procedures"
validation:
  - "Single node failure"
  - "Entire rack failure"
  - "Cross-DC network partition"
  - "Replica recovery with stale data"
  - "Timeout after committed write"
  - "Restore data after accidental deletion"
~~~

Đây là **mẫu tài liệu kiến trúc**, không phải cấu hình triển khai. Mỗi trường phải được điền bằng bảo đảm của DBMS và hạ tầng cụ thể; `TBD` không được bỏ lại trong kế hoạch production.

## 38. Tổng kết

Để thiết kế **replication factor và vị trí bản sao theo node/rack/datacenter**, hãy nhớ:

1. **RF là số bản sao dự kiến theo phạm vi xác định.** Với Cassandra `NetworkTopologyStrategy`, RF được khai báo theo từng DC; tổng qua các DC không phải một RF duy nhất mặc định.
2. **Placement quan trọng không kém RF.** Ba bản sao chung rack không mang khả năng chịu mất rack như ba bản sao trên ba rack độc lập.
3. **Node, rack, AZ, DC và region là những failure domains khác nhau.** Phải hiểu sơ đồ hạ tầng thật và ánh xạ đúng topology labels.
4. **Anti-affinity cần đủ failure domains.** Nếu RF vượt số rack độc lập, không thể đặt mỗi replica trên một rack khác nhau.
5. **RF không phải quorum.** Consistency level và commit protocol quy định điều kiện đọc/ghi; majority và `R+W>N` chỉ là công cụ phân tích một phần.
6. **LOCAL_QUORUM khác overall QUORUM.** Trong Cassandra DC RF=3, local majority là 2; không mặc định cộng mọi replica qua các DC khi chọn local quorum.
7. **Đổi RF phải chuyển dữ liệu thực.** Thay metadata không thay thế repair, streaming và xác minh replica mới đã đủ nội dung.
8. **Nhiều DC tăng lựa chọn dự phòng nhưng không tự bảo đảm RPO/RTO, read-your-writes hoặc conflict semantics.** WAN latency, failover và data residency phải được thiết kế.
9. **Replication không thay thế backup.** Xóa nhầm và corruption có thể lan qua tất cả bản sao.
10. **Mỗi DBMS có topology riêng.** Cassandra có replica strategy theo DC/rack; MongoDB cần phân biệt data-bearing member với arbiter; fully managed NoSQL có placement do provider quản lý.

**Nguyên tắc thực hành:** trước khi chọn RF=2, RF=3 hoặc RF=5, hãy vẽ **replica map trên các failure domains**, giả lập **mất node/rack/DC**, tính **ngưỡng quorum còn lại**, rồi xác định **API nào phải tiếp tục phục vụ và API nào cần từ chối để giữ đúng dữ liệu**. Khi đó replication factor trở thành một phần của cam kết chịu lỗi có thể kiểm chứng, chứ không chỉ là một con số cấu hình.
