# Điều phối thay đổi topology trong khi Java Driver đang làm mới metadata

> **Chương:** Thay đổi topology  
> **Phạm vi:** Apache Cassandra phân tán, đặc biệt bootstrap, decommission, removenode và thay thế node; tác động tới gossip, token range, streaming, mức nhất quán đọc/ghi và Java Driver 4.x. Bài chú trọng **phối hợp thời điểm** giữa thay đổi của cluster và quá trình driver cập nhật metadata, không coi thông báo node UP là dấu hiệu dữ liệu đã sẵn sàng hoàn toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **ring/topology**, **gossip và liveness**, **tiến độ streaming**, **metadata/token map trong driver**; giải thích vì sao bốn góc nhìn có thể cập nhật ở những thời điểm khác nhau.
2. Mô tả cách Java Driver dùng **control connection**, các sự kiện thêm/xóa/UP/DOWN, cơ chế **debounce**, snapshot `session.getMetadata()` và token-aware load balancing.
3. Lập một chuỗi thao tác an toàn khi **thêm node**, **loại node khỏe**, **loại node chết** hoặc **thay node lỗi**, có điểm kiểm chứng trước khi chuyển bước.
4. Biết vì sao **NodeState.UP không chứng minh bootstrap đã hoàn tất**, và vì sao một snapshot metadata mới không đủ bảo đảm dữ liệu replica đã đồng bộ.
5. Theo dõi driver, Cassandra và ứng dụng Java đồng thời; đánh giá rủi ro CL, latency, timeout, reconnect, schema agreement và retry khi topology đang thay đổi.
6. Thực hành kiểm tra token map, trạng thái node và đường truy vấn bằng CQL, `nodetool` và Java Driver.

Đây là phần nối tiếp của mô hình **wide-column phân tán**: partition key quyết định token, replication strategy quyết định natural replicas, còn consistency level (CL) quyết định bao nhiêu replica phải phản hồi. **Driver chọn coordinator phù hợp**; chính Cassandra chịu trách nhiệm thực thi và duy trì các bản sao. Khi topology biến đổi, hai phía phải hội tụ nhưng không nhất thiết cập nhật đồng thời.

## 2. Bốn góc nhìn khác nhau về một lần đổi topology

Giả sử keyspace có RF=3 trên một datacenter. Cluster đang có ba node A/B/C, sắp thêm node D để phân bố token ranges và tải tốt hơn.

~~~text
              Sự kiện: chuẩn bị bootstrap node D

    Cluster/server                        Ứng dụng Java
    ─────────────────────────────────────────────────────────
    Ring: token ranges                    Driver Metadata #1:
      A B C                               A B C
        │                                    │
        ▼                                    │
    D được gossip nhận biết                  │
    D bắt đầu streaming                      │
        │                                    ▼
        │                            topology event / refresh
        │                                    │
        ▼                                    ▼
    D đã nhận đủ dữ liệu                 Driver Metadata #2:
    và vào trạng thái NORMAL            A B C D + token map mới
        │                                    │
        └───────── kiểm tra hội tụ ─────────┘
                 trước khi mở bước tiếp
~~~

Sơ đồ này **không biểu diễn thứ tự thời gian bắt buộc**: driver có thể biết D từ lúc D còn joining, trong khi một app khác cập nhật muộn vì mất control connection hoặc debounce; trạng thái trong metadata cũng có thể đổi trước/sau từng bước streaming.

| Góc nhìn | Nguồn quan sát | Trả lời điều gì? | Không chứng minh điều gì? |
|---|---|---|---|
| **Token ring và node lifecycle** | `nodetool status`, `nodetool ring`, thông tin gossip | Node đang JOINING/NORMAL/LEAVING? Token/range thuộc về ai? | Mọi replica đều đã đồng bộ hoặc ứng dụng đã biết ring mới |
| **Streaming và dữ liệu** | `nodetool netstats`, logs, repair, `tablestats` | Bootstrap/decommission/replace đang truyền dữ liệu ra sao? | Driver đã chuyển query plan hoặc toàn bộ dữ liệu đúng nghiệp vụ |
| **Java Driver metadata** | `session.getMetadata()`, NodeStateListener, token map | Driver biết node nào, host ID, state, khoảng token và schema nào? | Server đã hoàn tất di chuyển dữ liệu |
| **Trải nghiệm ứng dụng** | CL, latency, timeout, tracing, error rate, business checks | Query có thành công và đúng trong phạm vi kiểm? | Token ring của mọi node hoặc metadata của mọi app instance đã giống nhau |

**Tư duy quan trọng:** Một đợt thay đổi topology không nên được tuyên bố hoàn tất chỉ vì **một** trong bốn góc nhìn cho thấy trạng thái mong muốn.

### 2.1. Ai quyết định nơi lưu dữ liệu?

- **Partitioner** tính token từ partition key.
- **Replication strategy** như `NetworkTopologyStrategy` và RF theo DC quyết định natural replicas của từng token range.
- **Cassandra coordinator** nhận truy vấn, tính những replica cần tương tác và thực hiện đọc/ghi theo CL; khi topology chuyển tiếp, server có cơ chế xử lý các range đang di chuyển.
- **Java Driver token-aware load balancing** ưu tiên gửi truy vấn đến **coordinator** là replica thích hợp nếu biết routing key và token map; nó **không** tự ghi các bản sao hoặc quyết định replication factor.

Vì vậy một token map của driver chưa cập nhật có thể gây **định tuyến kém tối ưu, thêm network hop hoặc timeout khi node không liên lạc được**. Không suy rằng cứ sai token map là dữ liệu chắc chắn được lưu sai vị trí: server vẫn là bên thực thi replication. Tuy nhiên, không được dựa vào sự linh hoạt này để bỏ qua kiểm tra sau chuyển topology.

## 3. Các kiểu thay đổi topology và tác động tới metadata

| Thao tác | Diễn biến server thường gặp | Driver có thể quan sát | Cổng kiểm soát cần đạt |
|---|---|---|---|
| **Bootstrap thêm node** | Node mới nhận token, stream dữ liệu, JOINING → NORMAL | Node được thêm; state thay đổi; token map tính lại | Node NORMAL, streaming hoàn tất, đọc/ghi ổn định, metadata các app hội tụ |
| **Decommission node khỏe** | Node rời ring có điều phối, stream những range cần thiết | Node chuyển trạng thái/rời danh sách; token map mới | Streaming hoàn tất, node đã ra ring, RF vẫn được đáp ứng |
| **Removenode node chết** | Các replica còn sống tái phân phối range của node chết | Node DOWN rồi bị loại khỏi metadata | Không còn node cũ trong ring, streaming thành công, đủ replica khỏe |
| **Replace node hỏng** | Node thay thế nhận token/vai trò phù hợp, stream dữ liệu | Host ID/địa chỉ/state có thể thay đổi; pool mới | Replace hoàn tất, node NORMAL, dữ liệu đã đối chiếu, repair theo điều kiện |
| **Move token** | Di chuyển ownership của token range; dùng trong điều kiện phiên bản/topology cụ thể | Token map thay đổi, có thể kèm node state event | Range mới cân bằng, cleanup/repair khi cần, các client cập nhật |
| **Thay RF/DC** | Thay tập natural replicas dù số node không nhất thiết đổi | Metadata về schema/keyspace replication và token map mới | Bước data migration/repair hoàn tất, CL phù hợp, schema thống nhất |

Thao tác **`nodetool decommission`** dành cho node còn sống; **`nodetool removenode`** dùng khi node đã chết/không thể decommission. Đừng dùng chúng như hai cách tương đương để “bỏ một IP”. Thay node thường sử dụng quy trình replace đúng phiên bản, không chỉ chạy daemon mới với cùng tên.

### 3.1. Ví dụ chuyển ring logic

~~~text
Trước:
   A ───── B ───── C
   RF=3, ba node cùng DC

Thêm D:
   A ── D ── B ─── C
         ^    ^
       token ranges được chia lại;
       một số dữ liệu phải stream tới D

Ứng dụng:
   Driver instance 1: map A/B/C/D
   Driver instance 2: map A/B/C (chưa refresh)
   Driver instance 3: thấy D nhưng D chưa có pooled connection
~~~

Đây là ví dụ **khái niệm**, không phải sơ đồ xác định token cụ thể hoặc tải thực tế. Với virtual nodes (`num_tokens > 1`), một node có thể nắm **nhiều token ranges**, nên sơ đồ ring đơn giản không đại diện đầy đủ cho cách dữ liệu di chuyển.

## 4. Java Driver 4.x học topology bằng cách nào?

### 4.1. Control connection

Java Driver 4.x duy trì **control connection** để thực hiện công việc quản trị:

1. Truy vấn các system tables về topology và schema.
2. Theo dõi các sự kiện server thông báo thay đổi trạng thái node và schema.
3. Kiểm tra schema agreement khi cần.
4. Làm mới những đối tượng metadata giúp load balancing và định tuyến token-aware.

Control connection **khác** các pooled connections phục vụ CQL bình thường. Nếu node giữ control connection bị lỗi, driver có cơ chế reconnect và có thể chọn node khác theo cấu hình. Trong khoảng mất kết nối hoặc chưa làm mới, app vẫn có thể chạy một số truy vấn qua các pool còn sống, nhưng metadata có thể chậm hơn trạng thái thật của server.

~~~text
Cassandra gossip / server topology events
                    |
                    v
         Driver control connection
                    |
         gom và điều tiết events
          (topology debounce)
                    |
                    v
         Refresh topology/schema
                    |
                    v
        Metadata snapshot mới
             /           \
         Node list       Token map
             \           /
           Load balancing policy
                    |
          chọn coordinator cho CQL
~~~

**Contact points không phải danh sách cố định mọi node**: chúng giúp driver thiết lập kết nối đầu tiên, sau đó driver khám phá topology. Nên cung cấp nhiều contact point ổn định trong **local DC**, tránh để duy nhất một node sắp decommission làm contact point của tất cả tiến trình mới khởi động.

### 4.2. Topology events không tới và được xử lý ngay tức thì

Driver có cơ chế **debouncing** để gom những sự kiện UP/DOWN/ADD/REMOVE đến nhanh. Ví dụ cấu hình tham khảo của Java Driver 4.17:

~~~hocon
datastax-java-driver {
  advanced.metadata {
    topology-event-debouncer {
      window = 1 second
      max-events = 20
    }
    schema.debouncer {
      window = 1 second
      max-events = 20
    }
  }
}
~~~

Ý nghĩa:

- Nếu node trạng thái thay đổi liên tục, chờ một cửa sổ debounce giúp tránh refresh metadata vô ích cho từng event.
- Khi số event trong batch đạt giới hạn, driver có thể xử lý sớm thay vì chờ kéo dài.
- **Tăng** window có thể giảm chi phí xử lý nhưng **tăng độ trễ hội tụ**; **giảm** window có thể làm refresh dồn dập khi node flapping.
- Trạng thái “đã nhận event” không bằng “tất cả session ở mọi JVM đã refresh”; mỗi instance có control connection và vòng đời riêng.

Không mặc định tối ưu bằng cách đặt `window=0`. Trước hết phải đo tần suất sự kiện, độ trễ metadata thực tế và tác động CPU/admin threads của driver.

### 4.3. NodeStateListener: biết sự kiện, không chứng minh dữ liệu đã sẵn sàng

Java Driver có `NodeStateListener` với các callback điển hình:

| Callback | Ý nghĩa từ góc nhìn driver | Không được dùng làm tín hiệu duy nhất cho |
|---|---|---|
| `onAdd(Node)` | Node mới được driver biết đến | Bootstrap thành công; note: node có thể **chưa UP** |
| `onUp(Node)` | Driver xem node đang UP | Streaming/repair đã hoàn tất |
| `onDown(Node)` | Driver xem node DOWN hoặc FORCED_DOWN | Node đã rời ring vĩnh viễn |
| `onRemove(Node)` | Node biến mất khỏi danh sách topology mà driver biết | Mọi dữ liệu đã cleanup hoặc ứng dụng khác đã refresh |

Callback có thể được gọi trên **internal driver threads**. Chỉ ghi metric/log hoặc đẩy sự kiện vào queue không chặn; **không** gọi `nodetool`, blocking I/O, truy vấn dài hoặc thao tác tạo/xóa node trực tiếp từ callback. Callback khi khởi tạo session có thể đến **trước khi session sẵn sàng**; cũng không nên mặc định `node.getHostId()` luôn có giá trị ngay từ sự kiện đầu tiên.

### 4.4. Snapshot metadata có thể lỗi thời nếu cache

~~~java
Metadata once = session.getMetadata();
// KHÔNG giữ "once" để định tuyến/giám sát suốt nhiều giờ.
~~~

`session.getMetadata()` trả **snapshot metadata nhất quán tại thời điểm đọc**, gồm node list, token map và schema (ngoại trừ một số thuộc tính mutable trong `Node`, như state). Một snapshot cũ **không tự bổ sung node vừa bootstrap**. Khi cần quan sát trạng thái hiện tại:

~~~java
Metadata latest = session.getMetadata();
latest.getNodes().values().forEach(node ->
    System.out.printf("%s %s %s%n",
        node.getConnectAddress(), node.getState(), node.getDistance()));
~~~

`getNodes()` bao gồm cả node DOWN hoặc IGNORED. Có tên trong map **không có nghĩa** driver có kết nối đang dùng tới node đó; kiểm `Node.getState()`, `getDistance()` và số pooled connections. Đừng dùng `Metadata#getNodes().size()` làm thước đo duy nhất số replica thực tế hoặc mức an toàn của cluster.

## 5. Token-aware routing trong cửa sổ metadata refresh

Driver 4.x có default load balancing policy ưu tiên **local DC** và **token-aware routing**. Để tính được replica ưu tiên, nó cần:

- Thông tin **keyspace** và replication strategy.
- Routing key hoặc routing token của statement.
- Token map đã được cập nhật.
- Các node đủ điều kiện kết nối, không bị load balancing policy bỏ qua.

### 5.1. Prepared statement giúp có routing key

Với bảng:

~~~sql
CREATE TABLE topology_lab.events_by_tenant (
    tenant_id text,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id), event_id)
);
~~~

Khi dùng `PreparedStatement` với bind marker của partition key:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT payload FROM topology_lab.events_by_tenant " +
    "WHERE tenant_id = ? AND event_id = ?");
BoundStatement query = ps.bind(
    "tenant-a", UUID.fromString("11111111-1111-1111-1111-111111111111"));
session.execute(query);
~~~

Driver có thể nhận metadata về partition-key bind variables từ prepared statement để tính routing key. Ngược lại, với **simple statement** tự do, driver thường **không tự suy routing key**, kể cả câu query có `WHERE tenant_id = 'tenant-a'`; muốn token-aware cho simple statement phải cung cấp thông tin định tuyến phù hợp hoặc chuyển sang prepared statement.

### 5.2. Trước và sau thay đổi token ownership

~~~text
Trước bootstrap:
  Driver token map: key tenant-a -> ưu tiên A/B/C

Trong bootstrap:
  Server: D đang nhận một phần ranges
  Driver app1: token map cũ, vẫn thử A/B/C
  Driver app2: token map mới, có thể cân nhắc D

Sau streaming + ring NORMAL + refresh:
  Driver mới tính đúng replica ưu tiên theo ranges hiện tại.
~~~

**Tác động chủ yếu của metadata chậm:** query đi qua coordinator kém tối ưu, tăng round-trip, pressure lên node cũ, timeout/retry trong lúc pools và streaming còn biến động. **Không** khẳng định stale token map tự làm mất dữ liệu: Cassandra còn xử lý replica selection và pending ranges phía server. Nhưng nếu quorum đang thiếu replica hoặc streaming lỗi, read/write vẫn có thể thất bại; phải đánh giá **cả server lẫn driver**.

### 5.3. Đừng tắt token map để “chữa” một lần topology refresh chậm

~~~hocon
datastax-java-driver {
  advanced.metadata {
    schema.enabled = true
    token-map.enabled = true
  }
}
~~~

Tắt `token-map.enabled` làm driver mất thông tin tối ưu định tuyến. Tắt `schema.enabled` hoặc lọc bỏ keyspace còn có thể làm mất thông tin replication cần để tính token map. Điều này có thể tăng tải/độ trễ mà **không sửa** lỗi gossip/streaming.

> **Khác biệt nên nắm:** **Topology metadata** mô tả node/token; **schema metadata** mô tả keyspace/table và RF. Cả hai cần đúng để token-aware routing hiệu quả, nhưng **schema agreement** không có nghĩa dữ liệu đã stream xong, và **node UP** không có nghĩa schema của mọi node đã thống nhất.

## 6. Cửa sổ chuyển tiếp: tránh coi một sự kiện là ranh giới an toàn

Một đợt bootstrap hoặc decommission có thể kéo dài nhiều phút đến nhiều giờ tùy lượng dữ liệu, băng thông và compaction. Metadata của driver có thể được làm mới trong **một phần** thời gian ấy.

### 6.1. Timeline minh họa cho bootstrap

~~~text
                   Node D mới tham gia

T0  A/B/C hoạt động ổn định, app dùng token map M0
    |
T1  Khởi động D, ring nhận ra D đang JOINING
    |             \
    |              \-- Driver instance #1 nhận onAdd(D)
    |                          (chưa có nghĩa D đọc được mọi range)
T2  D streaming những range mình sẽ quản lý
    |             \
    |              \-- Driver #2 vẫn giữ metadata snapshot M0
    |                  vì debounce hoặc control connection chưa refresh
T3  D nhận đủ dữ liệu, trạng thái chuyển NORMAL
    |             \
    |              \-- Driver #1/#2 có thể lần lượt thấy state và token map mới
T4  Streaming/repair/checks ổn định; driver sessions hội tụ về M1
    |
T5  Mới thực hiện bước thay đổi tiếp theo, ví dụ cleanup
    hoặc điều chỉnh capacity/routing policy đã phê duyệt
~~~

**Không nên giả thiết T3, T4 và T5 là cùng một thời điểm.** Thậm chí trong lúc node đã NORMAL, một vài JVM vừa phục hồi control connection có thể còn metadata cũ; thay đổi token routing cũng không thể được xác minh bằng mỗi một callback `onUp`.

### 6.2. Rủi ro từng khoảng chuyển tiếp

| Cửa sổ | Điều có thể xảy ra | Biện pháp điều phối |
|---|---|---|
| D vừa được phát hiện, chưa stream đủ | `onAdd`/node list xuất hiện trước khi bootstrap hoàn tất | Không tăng lưu lượng chỉ dựa vào onAdd; kiểm `nodetool netstats` và lifecycle |
| Driver còn token map cũ | CQL có thể chọn coordinator cũ, phát sinh thêm hop | Giữ đủ capacity trên node cũ; theo dõi driver topology refresh |
| Node D có trạng thái UP trong driver | Pool có thể mở nhưng dữ liệu/range còn đang chuyển | Kiểm server state NORMAL, streaming và query thực tế |
| Control connection di chuyển sang node khác | Refresh metadata bị chậm, log có reconnect | Có nhiều contact point, giám sát control connection; không restart hàng loạt JVM |
| Node cũ LEAVING, app còn giữ địa chỉ | Query plan có thể tạm thử node đang rời hoặc node DOWN | Đảm bảo fallback nodes, kiểm lỗi kết nối/retry có giới hạn |
| Ring mới nhưng một app instance chưa refresh | Các instance có coordinator ưu tiên khác nhau | Kiểm snapshot metadata **trên nhiều JVM**, không chỉ một pod |
| Keyspace RF thay đổi cùng lúc | Replica placement/CL và schema metadata thay đổi | Tránh gộp trong cùng cửa sổ; thay RF có runbook/repair riêng |

Một request lỗi trong cửa sổ chuyển tiếp có thể vì **coordinator cũ đã rời**, **replica không đủ ACK**, **streaming tranh tài nguyên**, **metadata refresh chậm**, hoặc một lỗi ứng dụng khác. Cần phân loại bằng log/trace, không tự động đổ hết cho driver.

### 6.3. Quy tắc “hai mặt phẳng đã sẵn sàng”

Để tiến hành thao tác tiếp theo, hãy đánh giá tối thiểu:

**Mặt phẳng server/data:**

- Token ring và lifecycle đúng kế hoạch.
- Streaming bootstrap/decommission/replace đã hoàn tất, không còn phiên lỗi.
- Số replica khỏe đủ để thỏa CL và RF trong DC.
- Những hoạt động repair/consistency được yêu cầu đã hoàn thành hoặc có kế hoạch theo dõi rõ.

**Mặt phẳng client/driver:**

- Những Java service liên quan nhìn thấy node set và local DC hợp lệ qua snapshot **mới** của `session.getMetadata()`.
- Token map không bị disable/khuyết keyspace; query có routing key.
- Pool và coordinator còn đủ node UP, không bùng lỗi reconnect hoặc request timeout.
- Latency, throughput và kết quả CQL trên tập khóa kiểm tra đạt mức chấp nhận.

**Không có một flag duy nhất** được Cassandra và mọi JVM cùng đặt để xác nhận cả hai mặt phẳng. Runbook phải phối hợp những tín hiệu này.

## 7. Replication, consistency và schema agreement trong lúc đổi topology

### 7.1. CL không biến mất khi ring thay đổi

Giả sử một DC có RF=3, ứng dụng dùng `LOCAL_QUORUM`:

~~~text
RF dc1 = 3
LOCAL_QUORUM cần 2 phản hồi từ các full replica phù hợp.

Thêm D và chuyển token:
  Các range có thể được phân bổ lại.
  Cassandra chịu trách nhiệm xử lý replica/pending ranges.
  Driver chỉ quyết định coordinator ưu tiên để gửi CQL.
~~~

**Quorum có ý nghĩa theo replication và replica placement của keyspace**, không theo số địa chỉ có trong `Metadata#getNodes()`. Thêm node thứ tư **không tự tăng RF từ 3 lên 4**, nên không có chuyện chỉ nhìn thấy bốn node là đổi công thức quorum. Ngược lại, nếu đồng thời `ALTER KEYSPACE` tăng RF, số replica chịu trách nhiệm và quy trình đồng bộ dữ liệu **thực sự thay đổi**.

| Tình huống | Hệ quả cần cân nhắc |
|---|---|
| RF=3, thêm node D | D nhận một số range; mỗi partition vẫn có RF theo cấu hình |
| Node cũ bị decommission khi những replica khác còn khỏe | Thực hiện streaming để duy trì placement; app cần cập nhật token map |
| Node chết rồi removenode | Replica còn lại phải tái tạo range trên những node phù hợp; có thể chịu tải lớn |
| RF tăng | Có thêm replica mới cần dữ liệu lịch sử; cần repair/range streaming theo runbook |
| RF giảm | Giảm số bản sao; kiểm độ an toàn dữ liệu và cleanup theo quy trình |
| Multi-DC dùng `LOCAL_QUORUM` | Chỉ quorum local DC; không kết luận DC khác đã đồng bộ |

Không “giảm CL từ LOCAL_QUORUM xuống ONE” một cách tự động chỉ để đi qua giai đoạn bootstrap mà không cân nhắc yêu cầu tính nhất quán. Giảm CL là thay đổi hợp đồng đọc/ghi của ứng dụng.

### 7.2. Schema agreement là một trạng thái khác

Khi thay topology, thường **không cần** DDL. Tuy nhiên, đổi RF, schema table hoặc index có thể khiến driver phải refresh **schema metadata**. Những node mới hoặc node chưa hội tụ schema có thể gây lỗi query “unconfigured table” nếu lệnh DDL và request được điều phối không đúng.

- Java Driver có cơ chế **schema agreement check** cho các thay đổi schema.
- Schema agreement dựa trên schema version của những node được xét, **không** khẳng định token ranges đã stream xong.
- Trong một số **rolling upgrade trộn phiên bản server**, cách tính schema version khác nhau khiến schema agreement không nhất thiết đạt; cần hạn chế DDL ở giai đoạn nâng cấp theo hướng dẫn phiên bản.
- Chỉ xem `checkSchemaAgreementAsync()` như tín hiệu về **schema**, không phải API “đợi topology hoàn tất”.

**Khuyến nghị vận hành:** Thực hiện lần lượt các thay đổi lớn — topology, replication factor, schema và nâng cấp binary — theo cửa sổ bảo trì có kiểm chứng riêng. Nếu có lý do bắt buộc ghép, phải thiết kế lộ trình phụ thuộc và điều kiện dừng chính thức.

### 7.3. Đừng nhầm routing của driver với ghi dữ liệu

~~~text
Client biết token map cũ:
      |
      v
   Coordinator A
      |
      |  Server tự tính replica/pending ranges
      v
     B/C/D theo trạng thái ring server

Client biết token map mới:
      |
      v
   Coordinator D (nếu đủ điều kiện)
      |
      v
   Replica set do server quyết định
~~~

Việc gửi query thẳng tới D **không** buộc D một mình quyết định kết quả. Khi phân tích latency, ghi lại **coordinator** và các replica thực sự tham gia. Token-aware routing ưu tiên giảm hop, không thay quorum hoặc protocol streaming.

## 8. Runbook thêm node trong khi Java Driver đang hoạt động

Đây là khung thao tác để chuẩn bị và kiểm chứng; lệnh thay đổi topology chỉ nên thực hiện bởi người vận hành được cấp quyền, trên phiên bản và topology đã xác minh. Không áp dụng các bước hủy dữ liệu hoặc restart vào production từ một ví dụ học thuật.

### Giai đoạn A — Baseline trước khi bootstrap

1. **Chốt trạng thái cluster:** Cassandra version, DC/rack, seed, `num_tokens`, RF, tình trạng gossip, số node `UN`, tải và token distribution.
2. **Kiểm dữ liệu và repair:** Không bootstrap ngay giữa sự cố nghiêm trọng về mất replica, repair lỗi kéo dài hoặc tombstone cần xử lý.
3. **Ước lượng dữ liệu cần stream:** Còn đủ disk headroom cho node mới và các node nguồn, network và compaction capacity.
4. **Chốt SLO:** p95/p99 latency, error rate, throughput và timeout cho những truy vấn quan trọng.
5. **Chốt góc nhìn client:** phiên bản Java Driver, local datacenter, các contact points, metadata enabled, token-aware enabled, số app instance và thời điểm lấy snapshot driver.
6. **Đặt mức concurrency thay đổi:** Tránh bootstrap nhiều node cùng lúc khi chưa đo khả năng chịu streaming của cluster.

Các lệnh quan sát không chỉnh dữ liệu:

~~~bash
nodetool status
nodetool ring
nodetool describecluster
nodetool tablestats topology_lab
nodetool compactionstats
~~~

Lưu output cùng timestamp UTC và địa chỉ node gọi lệnh; `nodetool status` trên một node không đảm bảo mọi node có cùng góc nhìn gossip khi cluster đang có vấn đề.

### Giai đoạn B — Bootstrap theo cấu hình chính thức

1. Chuẩn bị node D với đúng **cluster name, version tương thích, snitch, datacenter, rack, seeds, network/security, data directories và token allocation**.
2. Bắt đầu bootstrap theo hướng dẫn Apache Cassandra cho phiên bản đang chạy. **Không** đặt `auto_bootstrap: false` để “nhanh” hơn trong bài toán thêm một node dữ liệu bình thường; làm vậy có thể bỏ qua việc nạp các range cần thiết.
3. Khi D gia nhập, theo dõi lifecycle của D (ví dụ `UJ`/JOINING) và `nodetool netstats` trong quá trình streaming.
4. Giữ capacity trên A/B/C. Không chuyển sang bước cleanup hoặc decommission node nguồn chỉ vì driver đã gọi `onAdd(D)`.
5. Nếu bootstrap fail, dừng và thực hiện runbook **resume/restart/rebuild** đúng bản Cassandra. Không tự xóa các file đang dùng hoặc ép vào ring với dữ liệu chưa nạp.

~~~bash
# Quan sát bootstrap; gọi trên các node được phép.
nodetool status
nodetool netstats
nodetool compactionstats
~~~

**Tình huống biên:** Trong một số bản Cassandra, consistent bootstrap có thể thất bại nếu replica nguồn không khả dụng. Tùy chọn bỏ qua bảo đảm này (ví dụ JVM flag liên quan consistent range movement) có thể dẫn tới dữ liệu thiếu; không tắt an toàn chỉ để bootstrap “được”.

### Giai đoạn C — Xác nhận D sẵn sàng phía server

Đặt điều kiện rõ:

- D vào trạng thái **UP/NORMAL (`UN`)** theo góc nhìn của cluster.
- `nodetool netstats` không còn streaming bootstrap đang chạy hoặc lỗi chưa giải thích.
- Disk, SSTable, compaction và log trên node mới không có dấu hiệu dữ liệu thiếu/hỏng.
- Các range mới có đủ replica để phục vụ CL; trường hợp có downtime trong bootstrap phải đánh giá hints/repair.
- Có thể đọc/ghi những partition đã chọn **trên token ranges liên quan**, không chỉ một truy vấn tổng quát.

**Không coi `UN` một mình là “đã đối soát toàn bộ dữ liệu”**. Nghi ngờ replica đã bỏ lỡ mutation thì chạy repair đúng phạm vi hoặc thủ tục xác minh dữ liệu thích hợp.

### Giai đoạn D — Xác nhận driver đã hội tụ

Trên **từng nhóm Java service**, lấy snapshot `session.getMetadata()` **mới** để xác minh:

- D đã xuất hiện với host ID/địa chỉ/local DC đúng.
- Driver có thể kết nối với các node local hợp lệ và pool hoạt động.
- Token map/keyspace metadata được bật; những request bằng prepared statement còn tính được routing key.
- Event/log control connection không bị vòng reconnect vô hạn.
- Tỷ lệ query vào coordinator phù hợp và latency/timeout không tăng bất thường.

Nếu một pod chưa thấy D, cần kiểm tra control connection, network, gossip, topology event debouncer và phiên bản driver. **Đừng buộc tất cả pod restart đồng loạt** nếu lỗi chỉ là refresh chậm, vì việc đó tạo đợt kết nối đồng thời làm cluster chịu thêm tải.

### Giai đoạn E — Chỉ sau khi hội tụ mới cleanup

Tài liệu Apache khuyến nghị dùng `nodetool cleanup` trên các node **đã mất quyền sở hữu một số range** sau khi xác nhận node mới hoạt động và dữ liệu đã được stream. Cleanup dọn SSTable dữ liệu không còn thuộc quyền node; đây là thao tác tốn I/O/disk và có thể ảnh hưởng SLA.

~~~bash
# Chỉ trong runbook production đã phê duyệt,
# trên những node được xác định cần cleanup:
nodetool cleanup topology_lab
~~~

**Không chạy cleanup sớm trong lúc bootstrap hoặc ring chưa ổn định.** Cũng không coi việc cleanup thành công là thay thế repair hay xác minh tất cả Java service đã cập nhật metadata.

## 9. Runbook decommission, removenode và thay node chết

### 9.1. Decommission một node khỏe

**Mục tiêu:** Node A đang hoạt động rời ring có điều phối, dữ liệu range của nó được chuyển đến các replica phù hợp.

1. Kiểm RF, node khỏe, disk headroom và đường streaming trên các node còn lại.
2. Xác nhận driver có **nhiều contact points** và đủ node LOCAL để duy trì pooling; đừng để A là contact point sống duy nhất cho các instance mới.
3. Phát lệnh decommission chỉ từ phiên điều hành được phê duyệt:

~~~bash
# Minh họa cú pháp; đây là thao tác thay đổi topology.
nodetool decommission
~~~

4. Theo dõi `nodetool netstats`, state LEAVING và quá trình streaming cho tới khi A rời ring.
5. Kiểm tra trên các Java session rằng `onRemove`/node list mới đã xuất hiện, query plans không phụ thuộc A và lỗi kết nối trở về baseline.
6. Chạy kiểm tra dữ liệu/CL và cleanup phù hợp sau khi ring ổn định.

**Không nhầm “A đã DOWN” với “A đã được decommission”**. Nếu chỉ tắt daemon, các natural replicas và token ranges vẫn được ring tính theo topology cũ.

### 9.2. Removenode khi node đã chết

Khi node A hỏng và không thể chạy decommission, `nodetool removenode` có thể được dùng **từ một node khỏe khác** theo quy trình chính thức. Phải xác định đúng **host ID** của node chết, bảo đảm các bản sao còn lại đủ dữ liệu và đĩa để tái phân phối.

~~~bash
# Tra host ID và tình trạng ring trước.
nodetool status

# Minh họa tham số; KHÔNG chạy với ID tự đoán.
nodetool removenode <dead-node-host-id>

# Theo dõi trong lúc phân phối lại.
nodetool netstats
~~~

Sau khi removenode hoàn tất, xác minh cả **ring/data** và **driver metadata**. `onRemove` chỉ xác nhận driver đã biết node rời, không chứng minh các replica còn lại đủ dữ liệu hợp lệ. Nếu toàn bộ bản sao của một range đã hỏng, removenode/repair không tự tạo lại dữ liệu đã mất.

### 9.3. Replace node hỏng

Thay node chết là quy trình khác với bootstrap một node hoàn toàn mới: có thể dùng flag **`-Dcassandra.replace_address_first_boot=<dead_node_ip>`** theo Apache Cassandra, cùng cấu hình đúng IP/host ID và phiên bản. Trong lúc replacement đang stream, trạng thái hiện lên từ các node khác và góc nhìn riêng của node thay thế có thể khác nhau.

Tài liệu Apache lưu ý phải chạy repair để đảm bảo dữ liệu trên replacement khi:

- Node cũ đã down **lâu hơn `max_hint_window`** trước khi được thay.
- Hoặc thay bằng **cùng IP** và quá trình replacement kéo dài **quá `max_hint_window`**.

Đây là điều kiện vận hành rất quan trọng: replacement có thể đã hoàn tất bootstrap nhưng **đã bỏ lỡ các ghi xảy ra trước hoặc trong khoảng chuyển đổi**. Java Driver nhận `onUp` của node thay thế không chứng minh các mutation bị bỏ lỡ đã được repair.

Không chỉnh `max_hint_window` như “vô hạn” để tránh repair; hints không phải bản sao backup và cũng không thay anti-entropy repair có coverage.

### 9.4. Tránh trộn nhiều sự kiện lớn

Một chuỗi nguy hiểm thường là:

~~~text
Bootstrap D chưa stream xong
      |
Tắt A (node nguồn)
      |
Đồng thời ALTER KEYSPACE đổi RF
      |
Driver nhiều instance nhận loạt sự kiện ADD/DOWN/SCHEMA
      |
Retry và metadata refresh tăng tải
      |
Không rõ lỗi do topology, RF, dữ liệu hay ứng dụng
~~~

Thay vào đó, điều phối **một thay đổi lớn tại một thời điểm**, có checkpoint server/data/driver và tiêu chí rollback/escalation. Khi thao tác thật sự độc lập được phép chạy song song, phải có bằng chứng capacity và phạm vi token không gây cạnh tranh nguy hiểm.

## 10. Java Driver 4.x: quan sát snapshot metadata và node events

### 10.1. Tạo session với local DC, contact point và listener

Ví dụ Java Driver 4.x minh họa cách thu tín hiệu thay đổi node **không chạy thao tác nặng trong callback**. Dữ liệu demo giả định Cassandra lab ở `127.0.0.1:9042` và tên DC là `dc1`; thay bằng cấu hình môi trường thực.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.Metadata;
import com.datastax.oss.driver.api.core.metadata.Node;
import com.datastax.oss.driver.api.core.metadata.NodeStateListenerBase;
import java.net.InetSocketAddress;
import java.util.concurrent.atomic.AtomicInteger;

public final class TopologyObserver {
    public record Counters(
            AtomicInteger added,
            AtomicInteger up,
            AtomicInteger down,
            AtomicInteger removed) {
        public Counters() {
            this(new AtomicInteger(), new AtomicInteger(),
                 new AtomicInteger(), new AtomicInteger());
        }
    }

    public static CqlSession openLabSession(Counters counters) {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .addNodeStateListener(new NodeStateListenerBase() {
                @Override public void onAdd(Node node) {
                    counters.added().incrementAndGet();
                }
                @Override public void onUp(Node node) {
                    counters.up().incrementAndGet();
                }
                @Override public void onDown(Node node) {
                    counters.down().incrementAndGet();
                }
                @Override public void onRemove(Node node) {
                    counters.removed().incrementAndGet();
                }
            })
            .build();
    }

    public static void printSnapshot(CqlSession session) {
        // Lấy snapshot mới MỖI LẦN cần quan sát.
        Metadata snapshot = session.getMetadata();
        System.out.println("knownNodes=" + snapshot.getNodes().size()
                + ", tokenMapPresent=" + snapshot.getTokenMap().isPresent());

        for (Node node : snapshot.getNodes().values()) {
            System.out.printf(
                "addr=%s hostId=%s state=%s distance=%s connections=%d%n",
                node.getConnectAddress(),
                node.getHostId(),
                node.getState(),
                node.getDistance(),
                node.getOpenConnections());
        }
    }
}
~~~

Sử dụng trong phương thức chạy lab:

~~~java
TopologyObserver.Counters counters = new TopologyObserver.Counters();
try (CqlSession session = TopologyObserver.openLabSession(counters)) {
    TopologyObserver.printSnapshot(session);
    // Khi topology thay đổi: gọi printSnapshot lại từ đường
    // điều phối/quan sát bên ngoài, KHÔNG từ listener.
    System.out.println("onAdd=" + counters.added().get()
            + ", onUp=" + counters.up().get()
            + ", onDown=" + counters.down().get()
            + ", onRemove=" + counters.removed().get());
}
~~~

Đoạn sử dụng này đặt **trong một phương thức Java**, không phải toàn bộ class tự chạy. Với ứng dụng thật, tạo `CqlSession` **một lần** và tái sử dụng; không tạo session mới trên mỗi request hoặc mỗi lần lấy metadata. Một ứng dụng nhiều process cần **thu metric trên từng process**, không chỉ log của một JVM.

**Giới hạn của demo:**

- Listener cũng nhận các event trong quá trình khởi tạo. Bộ đếm không đại diện “chỉ các thay đổi sau bootstrap”.
- `Node.getHostId()` có thể tạm `null` ở sự kiện khởi tạo rất sớm; không dùng nó khi chưa sẵn sàng.
- `getNodes()` là danh sách node **driver biết**, gồm cả DOWN/IGNORED; số node trong map không bằng số pool kết nối hoạt động.
- Callback chạy trên thread driver. Bộ đếm atomic giúp không chặn; với log sự kiện thực tế nên dùng queue **có giới hạn** và consumer riêng.
- Nếu nhiều sự kiện bị debounce/gom lại, **không** suy số lần callback bằng số mọi chuyển trạng thái diễn ra trong gossip.

### 10.2. Prepared query tiếp tục hoạt động khi coordinator thay đổi

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

public final class EventReadService {
    private final CqlSession session;
    private final PreparedStatement findByKey;

    public EventReadService(CqlSession session) {
        this.session = session;
        this.findByKey = session.prepare(
            "SELECT payload FROM topology_lab.events_by_tenant " +
            "WHERE tenant_id = ? AND event_id = ?");
    }

    public String read(String tenantId, UUID eventId) {
        BoundStatement bound = findByKey.bind(tenantId, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        Row row = session.execute(bound).one();
        return row == null ? null : row.getString("payload");
    }
}
~~~

**Ưu điểm:** prepared statement cung cấp partition-key bind metadata để driver tính routing key, nếu schema/token metadata được bật. Khi coordinator tối ưu đổi do token map mới, driver có thể gửi tới node khác mà ứng dụng không cần biết địa chỉ IP của mỗi replica.

**Không được suy quá mức:** `LOCAL_QUORUM` chỉ bảo đảm số phản hồi thích hợp theo RF trong local DC, không thay repair, không chứng minh bootstrap đã stream đủ dữ liệu, và không xác nhận dữ liệu DC xa đã đồng bộ. Với kết quả `null`, cần kiểm xem hàng vốn không tồn tại hay lỗi đường đọc/CL, không tự kết luận “driver chưa refresh”.

### 10.3. Đo độ trễ hội tụ metadata mà không cache snapshot

Trong một công cụ quan sát (không chạy trong NodeStateListener), có thể lấy hai snapshot cách nhau một khoảng do **người vận hành chủ động**:

~~~java
Metadata before = session.getMetadata();
int beforeCount = before.getNodes().size();

// Ở một thời điểm KHÁC, sau khi cluster có event và
// người vận hành chủ động gọi lại từ monitoring:
Metadata after = session.getMetadata();
int afterCount = after.getNodes().size();

System.out.printf("knownNodes before=%d after=%d%n",
    beforeCount, afterCount);
~~~

Ở đây `before` và `after` chỉ hữu ích khi thật sự được thu tại **hai thời điểm khác nhau**. Đọc hai snapshot liền nhau không ép driver refresh. Không có quy tắc “ngủ hai giây là chắc chắn metadata mới”: mất control connection, network partition, debounce và phiên bản driver có thể kéo dài quá trình.

Để đánh giá hội tụ, gắn timestamp từ hệ thống quan sát với **event server được xác nhận**, rồi theo dõi bao nhiêu Java process đã thấy node/token map mới. Một process không thấy event cần được điều tra riêng thay vì tăng timeout toàn bộ ứng dụng.

## 11. Cấu hình driver và những lựa chọn cần tránh

Ví dụ phần cấu hình HOCON được kiểm chứng với dòng Java Driver 4.17, điều chỉnh theo môi trường:

~~~hocon
datastax-java-driver {
  basic {
    load-balancing-policy.local-datacenter = dc1
  }

  advanced {
    metadata {
      schema.enabled = true
      token-map.enabled = true
      topology-event-debouncer {
        window = 1 second
        max-events = 20
      }
    }
  }
}
~~~

Lệnh cấu hình driver Java 4.x **không** giống các tên thuộc tính của Java Driver 3.x; không tự đưa `DCAwareRoundRobinPolicy`/`TokenAwarePolicy` lồng nhau từ mẫu cũ sang driver 4.x. Driver 4 dùng default load balancing policy có tính local-DC và token-aware khi đủ metadata.

| Quyết định | Lựa chọn khuyến nghị ban đầu | Phản tác dụng khi làm sai |
|---|---|---|
| Local DC | Ghi đúng tên DC thực tế của ứng dụng | Driver không có local node phù hợp, định tuyến sai DC |
| Contact points | Nhiều địa chỉ ổn định trong local DC | Chỉ còn IP node vừa decommission → app mới khởi động không vào cluster được |
| Token metadata | Giữ enabled và không lọc mất keyspace cần thiết | Mất token-aware routing, tăng network hop |
| Schema metadata | Giữ enabled cho ứng dụng cần token/keyspace mapping | Thiếu replication info để tính token map |
| Debounce window | Giữ mặc định trước khi benchmark | Chỉnh quá nhỏ tạo nhiều refresh; quá lớn phản ứng muộn |
| Node listener | Callback rất ngắn, không blocking | Nghẽn internal driver threads |
| Session lifecycle | Một session dùng lại | Tạo nhiều control connections, reconnect storm |
| Retry/speculative execution | Chỉ dùng policy phù hợp idempotency và SLA | Retry ghi không idempotent hoặc khuếch đại tải lúc streaming |
| CL | Giữ theo yêu cầu nghiệp vụ và RF | Hạ CL để tránh timeout có thể làm đọc cũ/ghi thiếu ACK |

**Không dùng API nội bộ của driver để “ép node UP” hoặc tự sửa token map** trong ca vận hành bình thường. Những thao tác đó có thể đưa load balancing policy vào trạng thái không phù hợp với server; ưu tiên chữa kết nối, topology event, config và control connection.

### 11.1. Retry không phải cơ chế đồng bộ topology

Một request timeout trong lúc coordinator D chuẩn bị đi vào ring có thể **đã được áp dụng một phần** dù client chưa nhận response. Với INSERT/UPDATE/DELETE, quyết định retry phụ thuộc tính idempotent và timestamp, tránh tự tạo thêm tác dụng nghiệp vụ không mong muốn.

**Không** đồng loạt bật retry vô hạn hoặc speculative execution trên toàn ứng dụng khi thấy latency tăng trong lúc streaming. Điều đó có thể khiến coordinator và replica chịu thêm lưu lượng, làm quá trình di chuyển range lâu hơn. Cần đo tỷ lệ retry, timeout và số request đang in-flight, sau đó xử lý gốc rễ.

## 12. Bài lab: quan sát ring và driver trong lúc thêm node

**Mục tiêu:** Không tạo nguy cơ production. Dùng cluster lab có **ít nhất ba node `dc1`**, sau đó cho phép thêm node D theo runbook của phiên bản. Dữ liệu ví dụ nhỏ để quan sát metadata, **không** đo performance của hàng triệu partition.

### Bước 1 — Tạo schema và dữ liệu mẫu

~~~sql
CREATE KEYSPACE IF NOT EXISTS topology_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3'
};

CREATE TABLE IF NOT EXISTS topology_lab.events_by_tenant (
    tenant_id text,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id), event_id)
);

CONSISTENCY LOCAL_QUORUM;

INSERT INTO topology_lab.events_by_tenant
    (tenant_id, event_id, payload)
VALUES ('tenant-a',
        11111111-1111-1111-1111-111111111111,
        'created');

INSERT INTO topology_lab.events_by_tenant
    (tenant_id, event_id, payload)
VALUES ('tenant-b',
        22222222-2222-2222-2222-222222222222,
        'paid');

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-a';
~~~

Thay `dc1` nếu tên DC thực khác. Trong lab RF=3, `LOCAL_QUORUM` cần hai phản hồi của DC cục bộ. Nếu node đang không đủ bản sao khỏe, câu ghi có thể fail; không hạ CL chỉ để demo trôi qua.

### Bước 2 — Ghi nhận trạng thái baseline

~~~bash
nodetool version
nodetool status
nodetool ring
nodetool describecluster
nodetool getendpoints topology_lab events_by_tenant tenant-a
~~~

Lưu:

- Số node `UN` và địa chỉ theo DC/rack.
- Replica endpoints của `tenant-a` tại thời điểm trước thay đổi.
- Thống kê latency/timeout trong ứng dụng.
- Snapshot `TopologyObserver.printSnapshot(session)` **trên các Java process quan sát**.

Lệnh `getendpoints` trả **natural replicas** dự kiến cho partition key theo ring tại node được hỏi, không chứng minh dữ liệu mỗi replica đã được stream thành công.

### Bước 3 — Khởi động observer Java và theo dõi sự kiện

Giữ một `CqlSession` hoạt động trong lab; ghi nhận:

~~~text
M0:
  session.getMetadata().getNodes() -> {A, B, C}
  tokenMapPresent               -> true
  Node states                   -> UP ở các node local khỏe
  App read tenant-a             -> 'created'
~~~

Lưu ý `onAdd`/`onUp` ban đầu có thể ghi nhận sự kiện khi session vừa mở. Đừng trộn chúng với những event được tạo ra bởi lần bootstrap kế tiếp; dùng một mốc thời gian sau khi session khởi tạo xong.

### Bước 4 — Bootstrap D (chỉ lab đã cho phép)

Người điều hành lab chuẩn bị D và khởi động theo tài liệu topology changes của Apache Cassandra. Trong lúc đó, quan sát:

~~~bash
# Gọi định kỳ khi người vận hành cần kiểm tra.
nodetool status
nodetool netstats
nodetool compactionstats
~~~

**Không** được phép giả tạo một `onUp` trên driver để thay thế bootstrap. Theo dõi trong Java:

- Listener có thể nhận `onAdd(D)` trước khi node sẵn sàng phục vụ CQL.
- Snapshot metadata mới có thể đưa D vào node list và token map sau một số sự kiện.
- Các app instance khác nhau có thể nhận biến đổi ở các thời điểm khác nhau.
- Prepared query của `tenant-a` vẫn phải trả dữ liệu logic đúng, dù coordinator tối ưu có thể đổi.

### Bước 5 — Đợi D NORMAL và metadata hội tụ

~~~bash
nodetool status
nodetool netstats
nodetool getendpoints topology_lab events_by_tenant tenant-a
~~~

So sánh `getendpoints` trước/sau: vì token allocation, `tenant-a` có thể đổi tập replica **hoặc không**, tùy vị trí token. Hãy kiểm thêm các tenant/range khác nếu muốn chứng minh driver đã nhìn thấy thay đổi token ownership cụ thể.

Từ Java, gọi lại `printSnapshot(session)`. Nếu thấy D:

- Kiểm đúng **DC**, host ID và state.
- Kiểm token map có mặt.
- Kiểm request không timeout, driver không vào vòng reconnect.
- Không khẳng định tất cả JVM đã hội tụ khi mới kiểm một JVM.

### Bước 6 — Test CQL từ nhiều mốc sau thay đổi

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-a';

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-b';

TRACING ON;

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-a';

TRACING OFF;
~~~

Tracing có thể cho thấy coordinator và các replica liên quan, nhưng phát sinh overhead; chỉ dùng trong lab/phiên điều tra ngắn. **Kỳ vọng dữ liệu:** `tenant-a` có payload `created`; `tenant-b` có `paid`. Việc token map được cập nhật **không được** làm đổi kết quả CQL.

### Bước 7 — Thu lại bảng đối chiếu

| Bằng chứng | Trước bootstrap | Sau bootstrap và hội tụ | Có đạt? |
|---|---|---|---|
| Server ring | A/B/C `UN` | A/B/C/D `UN` | Đối chiếu output |
| Streaming | Không có job bootstrap | Không còn job lỗi/đang chạy | Đối chiếu `netstats` |
| Driver metadata | Danh sách A/B/C | Danh sách A/B/C/D ở các JVM đã chọn | Kiểm snapshot mới |
| Token metadata | Có cho `topology_lab` | Có và khớp ring mới trong phạm vi kiểm tra | Không suy từ node count |
| CQL logic | `created`/`paid` | Vẫn `created`/`paid` | Test cả read/write |
| Driver errors | Baseline timeout/reconnect | Không tăng bất thường | Metrics/log |
| Server resources | Baseline disk/network/compaction | Ổn định sau stream | Metrics/log |

Nếu một cổng chưa đạt, giữ đợt thay đổi ở trạng thái **PARTIAL/INVESTIGATING**. Không cleanup sớm hoặc khởi động decommission node tiếp theo chỉ vì deadline.

## 13. Giám sát đồng thời server, driver và ứng dụng

Để biết khi nào metadata refresh có thể ảnh hưởng đến lưu lượng, cần có **timeline chung** với clock đồng bộ, event ID và thông tin node/DC/range.

| Nhóm tín hiệu | Quan sát tối thiểu | Ý nghĩa và giới hạn |
|---|---|---|
| Gossip/ring | `nodetool status`, `ring`, DC/rack, trạng thái JOINING/LEAVING/NORMAL | Cho biết thay đổi ownership; không xác nhận client đã refresh |
| Streaming | `nodetool netstats`, session progress, lỗi source/destination | Phản ánh chuyển dữ liệu; không đồng nghĩa app nhìn thấy token map mới |
| Repair | Job IDs, range coverage, failed sessions, hints | Kiểm nguy cơ thiếu mutation; không chứng minh đúng nghiệp vụ |
| Driver control connection | Node đang giữ control connection, reconnect/error logs | Có thể giải thích chậm refresh khi control node down |
| Driver node metadata | Map node, `NodeState`, host ID, distance, connection count | Node trong metadata có thể DOWN/IGNORED |
| Driver token/schema map | Token map enabled, replication keyspace có thể tính | Mất keyspace/schema metadata làm token-aware kém |
| Node events | `onAdd`/`onUp`/`onDown`/`onRemove`, timestamp | Không phải chứng chỉ streaming hoàn tất |
| Pooled connections | Open connections, reconnect, unavailable hosts | Pool chưa sẵn sàng có thể gây timeout |
| CQL | Success/error, p95/p99, timeout, CL, retry | Đo trải nghiệm thực tế, không thay xác minh ring |
| Capacity | Disk, compaction, network, CPU, GC | Streaming/refresh/retries có thể cạnh tranh tài nguyên |

### 13.1. Tương quan sự kiện bằng một timeline

~~~text
UTC 09:00:00  Operation START bootstrap D
UTC 09:00:07  Server D = JOINING; netstats STREAMING
UTC 09:00:09  JVM-1 node event onAdd(D)
UTC 09:00:10  JVM-1 metadata includes D
UTC 09:00:11  JVM-2 control connection reconnecting
UTC 09:01:35  Server D = NORMAL; streaming complete
UTC 09:01:38  JVM-2 metadata includes D
UTC 09:02:10  App latency/retry returns to baseline
UTC 09:03:00  Operator verifies gates; change accepted
~~~

Đây là **timeline mô phỏng**, không phải SLA mặc định của driver hoặc Cassandra. Cần thu thời gian thật bằng telemetry trên từng node/JVM, vì tốc độ streaming và refresh có thể khác nhiều giữa các cluster.

**Tín hiệu tổng hợp nên có:** Tỷ lệ Java process nhìn thấy node set mong muốn; số process đang reconnect; phân phối latency/timeout theo DC; server streaming trạng thái; và số bước topology còn chưa hoàn tất. Tỷ lệ này phải tính trên **toàn bộ tập JVM cần phục vụ**, không chỉ vài instance vừa redeploy.

### 13.2. Không dùng NodeState thay cho health-check đầy đủ

Một node có thể hiện `UP` trong driver nhưng:

- Vẫn đang bootstrap hoặc streaming phần range.
- Chưa đủ tài nguyên cho SLA.
- Có network path chỉ một số client reach được.
- Chưa nhận toàn bộ mutation do từng replica bỏ lỡ.
- Có schema/replication khác nhau giữa một số node.

Ngược lại, một node tạm `DOWN` trong một JVM chưa chắc đã bị cả cluster xác nhận chết: có thể chỉ network path từ pod đó lỗi. **Kiểm hai phía** trước khi quyết định removenode hay thay node.

## 14. Phân tích sự cố thường gặp khi metadata chưa hội tụ

### 14.1. “Node đã NORMAL nhưng Java service không thấy”

**Triệu chứng:** `nodetool status` cho D `UN`, nhưng `session.getMetadata().getNodes()` trên một JVM không có D.

Thứ tự kiểm tra:

1. JVM có đang dùng **session còn sống** và đọc snapshot mới chưa, hay giữ `Metadata` cũ từ startup?
2. Control connection đang trỏ đến node khỏe? Có lỗi timeout/reconnect, TLS hoặc authentication không?
3. Các gossip/system tables trên node control có cập nhật D chưa?
4. Java service có dùng đúng cluster, local datacenter, địa chỉ broadcast/native transport không?
5. Debounce/refresh đang xử lý loạt event lớn hay bị một thay đổi liên tục làm chậm?
6. Có policy lọc node khiến D `IGNORED`, hoặc token/schema metadata bị tắt không?
7. So sánh nhiều JVM để xác định lỗi cục bộ hay toàn bộ workload.

**Không sửa bằng cách:** ghi cứng IP D vào mọi CQL statement hoặc restart đồng loạt tất cả JVM khi chưa biết nguyên nhân. Nếu control connection thực sự không hồi phục, áp dụng quy trình reconnect/deploy từng nhóm có giới hạn.

### 14.2. “Driver thấy D nhưng không dùng D làm coordinator”

Có thể vì:

- D chưa được xem là `UP`, chưa có pool kết nối hoặc đã bị policy đánh dấu `IGNORED`.
- D không thuộc **local DC** của app, trong khi default policy không chọn remote DC.
- Với partition key cụ thể, D **không** phải natural replica theo token map — điều này hoàn toàn bình thường.
- Query dùng `SimpleStatement` không có routing key hoặc schema/token metadata đã bị tắt/lọc.
- Load balancing vẫn chọn node khác vì policy và khả năng sẵn sàng, không nhất thiết chọn D cho mọi request.

Để đánh giá, chọn **nhiều partition keys** có token ranges liên quan tới D, dùng prepared statement và xác minh token map/keyspace replication. Không ép mọi query đi tới D để “kiểm thử load balancing”.

### 14.3. “Decommission xong nhưng Java app vẫn thử IP cũ”

Các khả năng:

- Metadata chưa refresh hoặc ứng dụng đang giữ snapshot cũ.
- Driver process mất control connection, không nhận REMOVE event.
- App có **chỉ một contact point** là IP đã rời, khiến **session mới** không thể khởi tạo.
- Load balancing/session đã có pool tới node cũ nhưng chưa cập nhật state; timeout có thể xảy ra khi pool reconnect.
- Các node server chưa thống nhất ring sau decommission lỗi.

Khắc phục bằng cách xác minh server remove đã hoàn tất, làm mới cấu hình contact points nếu cần cho **khởi tạo session mới**, quan sát driver reconnect và metadata mới; không cần hard-code mọi node trong request path.

### 14.4. “Read/Write timeout tăng mạnh dù metadata cập nhật đúng”

Metadata đúng không có nghĩa năng lực của cluster đủ cho thay đổi. Khi streaming:

- Disk I/O và network của source/destination tăng.
- Compaction, hints và repair có thể cạnh tranh tài nguyên.
- Node còn lại phải gánh thêm query khi một node rời.
- CL có thể không đạt vì thiếu số replica UP.
- Driver retry/speculative execution làm số request thật tăng.

Giải pháp là **điều tiết thay đổi topology, capacity và concurrency**, không chỉ giảm debounce window. Quan sát đủ ba lớp server/driver/app để xác định nút thắt.

### 14.5. “Sau replace, mọi node UP nhưng một số hàng cũ vẫn thiếu”

Theo hướng dẫn Apache, replacement có thể cần repair nếu node trước đó down quá cửa sổ hints hoặc dùng cùng IP và quá trình replacement kéo dài. `onUp` không đảm bảo repair đã xong; phải đối chiếu dữ liệu theo range và theo dõi hints/repair/streaming.

Đặc biệt, nếu replica cũ vắng mặt vượt `gc_grace_seconds` và có DELETE bị bỏ lỡ, nguy cơ **zombie data** cần được đánh giá riêng. Bật lại node chứa SSTable cũ không phải phương án “tự repair” an toàn khi đã mất tombstone.

### 14.6. “Schema agreement báo lỗi, nhưng node list trông bình thường”

Phân biệt:

- **Topology metadata:** node/token ranges và liveness.
- **Schema metadata:** table, keyspace, replication, UDT, index.
- **Schema agreement:** các node được xét có schema version tương thích không.

Một node list đúng không đồng nghĩa schema đã đồng bộ. Dừng DDL mới, kiểm schema version và hướng upgrade, chờ/sửa propagation theo runbook trước khi cho Java service dùng bảng mới. Không chữa “unconfigured table” bằng thay đổi CL hoặc ép query sang một IP cố định.

## 15. Checklist trước khi tuyên bố thay đổi hoàn tất

| Nhóm | Câu hỏi xác nhận | Trạng thái kỳ vọng |
|---|---|---|
| Phê duyệt | Đúng change request, thao tác và phạm vi node/DC? | Có |
| Ring | Node join/leave/remove/replace đã vào trạng thái đích? | Có |
| Streaming | Không còn job đang chạy hoặc thất bại không được giải thích? | Có |
| Replica | Đủ RF và replica khỏe cho CL ứng dụng trong phạm vi yêu cầu? | Có |
| Repair/hints | Điều kiện repair sau replace/outage đã đáp ứng hoặc có kế hoạch an toàn? | Có |
| Driver control | Session kết nối, control connection hồi phục? | Có |
| Driver metadata | Phần lớn/100% JVM cần phục vụ nhìn thấy topology mục tiêu theo tiêu chí rollout? | Theo chính sách, số liệu rõ |
| Token/schema | Token map enabled, keyspace/schema hợp lệ? | Có |
| Routing | Prepared query cho partition key có latency/coordinator phù hợp? | Có |
| Client config | Contact points/local DC không phụ thuộc node đã rời? | Có |
| SLA | Error rate, p95/p99, timeout, retry, resource usage đạt ngưỡng? | Có |
| Dữ liệu | Tập khóa trước/sau khớp giá trị kỳ vọng, gồm DELETE/TTL nếu liên quan? | Có |
| Cleanup | Chỉ thực hiện sau khi cluster ổn định, nếu cần? | Có kế hoạch |
| Rollback | Có phương án an toàn nếu node mới/metadata không hội tụ? | Có, đã được kiểm chứng |

**Nếu ring đạt nhưng driver chưa đạt:** chưa nên tăng tốc bước tiếp theo. **Nếu driver đạt nhưng streaming chưa đạt:** cũng chưa nên tuyên bố hoàn tất. Đặt **cổng chung** bằng bằng chứng trên cả hai mặt phẳng.

### 15.1. Bảng quyết định khi gặp blocker

| Tình huống | Quyết định ban đầu | Không nên làm |
|---|---|---|
| D đang JOINING, onAdd đã phát | Giữ cửa sổ, theo dõi streaming | Cleanup/rút node nguồn ngay |
| D NORMAL, một số JVM chưa refresh | Điều tra control connection/metadata từng JVM | Restart toàn bộ service không kiểm soát |
| Decommission lỗi, A còn LEAVING | Dừng bước đổi tiếp và xử lý server | Coi onDown là đã removenode |
| RF chưa đủ healthy replicas | Ưu tiên phục hồi replica/capacity | Hạ CL hàng loạt rồi báo hoàn tất |
| Replacement bỏ lỡ hints | Thực hiện repair theo runbook | Tin node UP là dữ liệu đầy đủ |
| Schema disagreement | Dừng migration DDL, đồng bộ schema | Ép query vào một coordinator cố định |
| Timeout tăng do streaming | Điều tiết streaming/compaction/load và phân tích retry | Chỉ tăng timeout vô hạn |

## 16. Câu hỏi tự đánh giá

**Câu 1.** Node D vừa gọi `onAdd` trong Java Driver. Có thể ngay lập tức decommission node nguồn A không?  
**Định hướng:** Không. onAdd cho biết driver khám phá D; D có thể chưa UP hoặc chưa stream đủ range.

**Câu 2.** Vì sao `Metadata once = session.getMetadata()` được tạo lúc startup không phù hợp để theo dõi bootstrap diễn ra sau đó?  
**Định hướng:** Metadata là snapshot; phải lấy lại `session.getMetadata()` để quan sát thay đổi.

**Câu 3.** Nếu một node đã `UN` trên server nhưng chỉ 20/30 JVM thấy node mới, điều gì còn thiếu trước khi hoàn tất?  
**Định hướng:** Chưa hội tụ metadata của toàn bộ nhóm app; cần xem control connection, debounce, network và tiêu chí rollout.

**Câu 4.** Driver có token map cũ thì nó có tự quyết định lưu dữ liệu theo replica cũ không?  
**Định hướng:** Không; driver ưu tiên coordinator, còn Cassandra xử lý replication và pending ranges.

**Câu 5.** RF=3, thêm node thứ tư có tự làm LOCAL_QUORUM cần ba phản hồi không?  
**Định hướng:** Không; RF của keyspace không tự thay đổi khi thêm node.

**Câu 6.** Tại sao prepared statement thường định tuyến token-aware tốt hơn simple statement?  
**Định hướng:** Driver biết bind variables thuộc partition key để tạo routing key.

**Câu 7.** `onUp(D)` có bảo đảm replacement đã nhận toàn bộ ghi trong thời gian node cũ down không?  
**Định hướng:** Không. Có thể cần repair theo max_hint_window và trạng thái replace.

**Câu 8.** Driver thấy D trong `getNodes()` nhưng state DOWN. Có thể xem D là coordinator đang khỏe không?  
**Định hướng:** Không; danh sách node bao gồm DOWN/IGNORED, phải xét pool và distance.

**Câu 9.** Một query với `LOCAL_QUORUM` ở dc1 thành công có chứng minh dc2 đồng bộ sau thay đổi topology không?  
**Định hướng:** Không. Local quorum chỉ thỏa điều kiện của DC cục bộ.

**Câu 10.** Khi node A decommission xong, application mới khởi động lỗi vì chỉ có contact point A. Có nên hard-code toàn bộ IP vào mọi query?  
**Định hướng:** Không; cập nhật contact points ổn định cho session initialization, để driver khám phá các node qua control connection.

**Câu 11.** Schema agreement là tín hiệu D đã hoàn tất bootstrap chưa?  
**Định hướng:** Không; schema và streaming/token ring là các trục trạng thái riêng.

**Câu 12.** Nếu đợt bootstrap làm p99 tăng và retry bùng nổ, nên chỉnh gì đầu tiên?  
**Định hướng:** Phân tích disk/network/streaming và retry, điều tiết thay đổi; không mặc định giảm debounce hoặc hạ CL.

## 17. Tổng kết

~~~text
                        THAY ĐỔI TOPOLOGY
                             |
                   +---------+----------+
                   |                    |
             SERVER / RING         JAVA DRIVER
                   |                    |
        gossip, token ranges       control connection
        JOINING / LEAVING          topology events
                   |                    |
        streaming / repair         debounce / refresh
                   |                    |
       NORMAL / range ownership    Metadata snapshot mới
                   |                    |
                   +---------+----------+
                             |
                Kiểm tra CLIENT / DATA
           CL, kết quả CQL, p95/p99, timeout
                             |
                 Điều kiện hoàn tất chung
                             |
                  Mới chuyển bước tiếp
~~~

**Nguyên tắc cốt lõi:** Cassandra giữ dữ liệu và di chuyển token ranges ở **mặt phẳng server**; Java Driver học topology, duy trì pools và chọn coordinator ở **mặt phẳng client**. Hai mặt phẳng không cập nhật nguyên tử với nhau. Vì vậy, khi bootstrap/decommission/removenode/replace, hãy **giữ capacity trong giai đoạn chuyển tiếp, quan sát metadata mới trên nhiều session, xác minh streaming/replica và CQL trước khi cleanup hoặc thực hiện thay đổi tiếp theo**. Đây là cách giảm rủi ro timeout, routing kém tối ưu và dữ liệu chưa đồng bộ trong hệ thống Cassandra phân tán có ứng dụng Java.

## Tài liệu tham khảo

- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/topo_changes.html) — bootstrap, decommission, removenode, replace, streaming, cleanup và điều kiện repair.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — gossip, coordinator, replication, consistency level và cơ chế phục hồi.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, phạm vi replica/range và giữ nhất quán.
- [DataStax Java Driver 4.17 — Control connection](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/control_connection/) — khám phá topology/schema, sự kiện và khôi phục control connection.
- [DataStax Java Driver 4.17 — Node metadata](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metadata/node/) — `getNodes()`, NodeState và NodeStateListener.
- [DataStax Java Driver 4.17 — Token metadata](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metadata/token/) — token map, replicas và giới hạn khi disable.
- [DataStax Java Driver 4.17 — Performance](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/performance/) — topology-event debouncer, schema metadata và refresh overhead.
- [DataStax Java Driver 4.17 — Load balancing](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/load_balancing/) — local DC, token-aware routing và routing key.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — bind metadata và routing key.
- [DataStax Java Driver 4.17 — Session API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/session/Session.html) — tính chất snapshot của `getMetadata()` và schema agreement.

