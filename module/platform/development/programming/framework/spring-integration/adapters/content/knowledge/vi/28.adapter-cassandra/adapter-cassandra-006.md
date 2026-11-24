# Consistency level và timeout trong Cassandra message flow

## 1. Vì sao một Cassandra write có thể timeout dù đã lưu dữ liệu?

Giả sử dịch vụ thanh toán nhận sự kiện `OrderPaid` qua JMS, chuyển thành Spring `Message<OrderEvent>` và đưa vào **Cassandra outbound channel adapter**. Một lần xử lý gặp timeout. Ứng dụng không biết nên retry hay acknowledge JMS message: nếu retry, có thể ghi trùng; nếu bỏ qua, có thể mất bản ghi phục vụ đối soát.

Vấn đề không chỉ là “Cassandra có chạy không”, mà là hai câu hỏi khác nhau:

1. **Consistency level (CL):** có bao nhiêu replica cần xác nhận để Cassandra coordinator coi một thao tác đọc/ghi đã đáp ứng yêu cầu?
2. **Timeout:** hệ thống được chờ bao lâu để nhận kết quả theo yêu cầu đó, và tầng nào đang đưa ra quyết định hết thời gian?

Một coordinator có thể đã chuyển mutation tới nhiều replicas, nhưng phản hồi tới client bị chậm hoặc bị mất. **Timeout là thiếu xác nhận đúng hạn, không phải bằng chứng âm tính rằng database chưa thay đổi.** Ngay cả khi driver báo lỗi, một hoặc nhiều replicas có thể đã ghi; một retry mới vẫn phải có khóa nghiệp vụ và semantics phù hợp.

Trong module **SPRING_INTEGRATION_ADAPTERS**, người học kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành luồng qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời quản lý message contract, lỗi và connection lifecycle. Bài **Consistency level và timeout** thuộc chương **Adapter Cassandra**, tập trung vào ngữ nghĩa đọc/ghi Cassandra khi các thao tác được kích hoạt từ Spring Integration message flow.

### Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích **replication factor**, coordinator, replica và các CL như `ONE`, `LOCAL_ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL`, `EACH_QUORUM`, `ANY`.
2. Tính số xác nhận cần thiết với `RF=3`/`RF=5` và điều kiện giao nhau `R + W > RF` đúng phạm vi datacenter.
3. Hiểu khi nào `SERIAL`/`LOCAL_SERIAL` xuất hiện trong **lightweight transaction (LWT)** và không dùng nhầm như CL read/write thông thường.
4. Phân biệt **driver request timeout**, **server-side read/write timeout**, **Spring Integration channel/gateway timeout** và deadline của HTTP/JMS/Kafka.
5. Cấu hình CL/timeout qua Java Driver 4.x, Spring Data `WriteOptions`/`QueryOptions` và Spring Integration Cassandra DSL.
6. Phân loại `UnavailableException`, `ReadTimeoutException`, `WriteTimeoutException`, `DriverTimeoutException`; xác định khi nào có thể retry.
7. Thiết kế idempotency, acknowledgments, backpressure, monitoring và integration tests phù hợp consistency/SLA.

## 2. Kiến trúc: dữ liệu được ghi ở đâu và ai chờ ai?

~~~mermaid
flowchart LR
    A["JMS/Kafka/HTTP inbound"] --> B["Spring Integration MessageChannel"]
    B --> C["CassandraMessageHandler"]
    C --> D["ReactiveCassandraOperations"]
    D --> E["Java Driver 4.x / CqlSession"]
    E --> F["Cassandra Coordinator"]
    F --> R1[("Replica 1")]
    F --> R2[("Replica 2")]
    F --> R3[("Replica 3")]
    R1 -. "ACK" .-> F
    R2 -. "ACK" .-> F
    R3 -. "ACK" .-> F
    F -. "Response hoặc timeout" .-> E
~~~

| Khái niệm | Trách nhiệm | Không nên suy ra |
|---|---|---|
| `MessageChannel` | Bàn giao một Spring Message tới endpoint | `send(true)` luôn có nghĩa Cassandra đã lưu |
| `CassandraMessageHandler` | Chọn INSERT/UPDATE/DELETE/STATEMENT, gọi reactive operations; có thể async hoặc sync | Tạo một distributed transaction cùng JMS/Kafka |
| `ReactiveCassandraOperations` | Mapping entity và thực hiện Cassandra operation | Tự quyết định CL tối ưu cho nghiệp vụ |
| Driver `CqlSession` | Điều phối request, retries, execution profiles, timeout và routing | Timeout đồng nghĩa server chưa làm gì |
| Cassandra coordinator | Gửi yêu cầu tới replica và chờ đủ kết quả theo CL | Bắt buộc nhận ACK từ mọi replica ở CL=ONE |
| Replicas | Giữ các bản sao của một partition theo replication strategy | Một replica là một Kafka partition/JMS queue |

**Coordinator không bắt buộc là một replica của partition đang xét.** Driver thường cố chọn coordinator phù hợp với routing/token, nhưng theo network/routing configuration request có thể được điều phối qua node khác.

### 2.1. Chuỗi sự kiện với một write `LOCAL_QUORUM`

~~~mermaid
sequenceDiagram
    participant Flow as Spring Integration
    participant Driver as Java Driver
    participant Coord as Cassandra coordinator
    participant R1 as Replica A
    participant R2 as Replica B
    participant R3 as Replica C

    Flow->>Driver: INSERT eventId=evt-6001, CL=LOCAL_QUORUM
    Driver->>Coord: Execute CQL
    Coord->>R1: Mutation
    Coord->>R2: Mutation
    Coord->>R3: Mutation
    R1-->>Coord: ACK 1
    R2-->>Coord: ACK 2
    Coord-->>Driver: Success: đủ 2/3 local replicas
    Driver-->>Flow: Completion
    R3-->>Coord: ACK muộn
~~~

Sơ đồ dùng **RF=3 tại một local datacenter**. Cassandra có thể gửi write tới **tất cả replicas**, còn CL quy định **số phản hồi coordinator cần chờ**. CL=LOCAL_QUORUM không đòi phản hồi của replica thứ ba để trả thành công cho client, nhưng điều đó không có nghĩa replica thứ ba sẽ không bao giờ nhận mutation.

## 3. Replication factor và quorum: các phép tính căn bản

### 3.1. RF là số bản sao trong replication strategy

**Replication factor (RF)** cho biết Cassandra muốn giữ bao nhiêu bản sao cho mỗi partition ở một datacenter hoặc theo keyspace strategy. Ví dụ test multi-node, một keyspace dùng `NetworkTopologyStrategy`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Đây chỉ là **ví dụ khi cluster thực sự có datacenter `dc1` và đủ nodes**. Không chạy cấu hình RF=3 trên một Cassandra node test rồi mong nó tạo ra ba replica độc lập. Với Docker test một node, có thể dùng RF=1 để học CQL, nhưng **không thể tái hiện hành vi 2/3 replicas hoặc khả năng chịu lỗi một node**.

### 3.2. Quorum là quá bán

Với replication factor `RF`, quorum trong cùng tập replicas thường có kích thước:

\[
Q = \left\lfloor\frac{RF}{2}\right\rfloor + 1
\]

| RF | ONE | QUORUM | ALL |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 2 | 1 | 2 | 2 |
| 3 | 1 | 2 | 3 |
| 4 | 1 | 3 | 4 |
| 5 | 1 | 3 | 5 |

Với `LOCAL_QUORUM`, dùng **RF của local datacenter** khi tính quorum, không lấy tổng RF toàn cluster multi-DC. `QUORUM` thường dựa trên replication factor **toàn bộ keyspace** (trên các datacenters theo replication strategy).

### 3.3. Giao nhau giữa tập replica của read và write

Trong mô hình quorum cơ bản, nếu số responses cần cho **write** là `W` và cho **read** là `R`, điều kiện:

\[
R + W > RF
\]

giúp đảm bảo hai tập replicas được xét có **ít nhất một replica chung** khi truy cập **cùng partition và cùng tập replicas**. Ví dụ RF=3:

| Write CL | W | Read CL | R | `R+W>3`? |
|---|---:|---|---:|---|
| ONE | 1 | ONE | 1 | **Không** |
| ONE | 1 | QUORUM | 2 | **Không**, bằng 3 |
| QUORUM | 2 | QUORUM | 2 | **Có**, bằng 4 |
| ALL | 3 | ONE | 1 | **Có**, bằng 4 |
| ONE | 1 | ALL | 3 | **Có**, bằng 4 |

Điều kiện này là **công cụ lý luận về quorum overlap**, không phải cam kết tổng quát rằng mọi truy vấn đều linearizable. Cassandra dùng timestamp-based conflict resolution, có thể có concurrent writes, clock skew, tombstones, topology changes và các đường đọc LWT khác. Muốn giao dịch compare-and-set/serializable trong phạm vi hỗ trợ của Cassandra, phải xem xét **LWT** thay vì chỉ đổi CL.

### 3.4. Một phản ví dụ quan trọng

~~~text
RF=3: replicas A, B, C

Write CL=ONE:
    A ACK thành công, B và C chưa áp dụng.

Read CL=ONE:
    Coordinator đọc B trước khi B thấy write mới.

Kết quả:
    Read có thể trả giá trị cũ dù write trước đó đã thành công.
~~~

Với write và read `QUORUM` trên cùng tập ba replicas, các tập hai replicas phải có giao nhau. Tuy nhiên, nếu **đọc từ datacenter khác** với nơi write `LOCAL_QUORUM` vừa trả thành công, hai nhóm local replicas **không bắt buộc giao nhau**; dữ liệu remote có thể chưa kịp được áp dụng.

## 4. Các consistency level trong Cassandra

| CL | Điều kiện xác nhận | Dùng cho | Đánh đổi/cảnh báo |
|---|---|---|---|
| `ONE` | Một replica phản hồi | Read/write ưu tiên latency và availability | Có thể chưa thấy dữ liệu mới khi đọc replica khác |
| `LOCAL_ONE` | Một replica ở local DC phản hồi | Workload ưu tiên local DC | Không bảo đảm đọc mới nhất nếu write chưa hội tụ |
| `TWO` | Hai replicas phản hồi | Trường hợp yêu cầu cụ thể | Phụ thuộc RF, topology |
| `THREE` | Ba replicas phản hồi | Trường hợp yêu cầu cụ thể | Không phù hợp nếu RF không đủ |
| `QUORUM` | Quá bán toàn tập replicas | Đọc/ghi yêu cầu quorum overlap toàn keyspace | Multi-DC có thể tăng độ trễ qua WAN |
| `LOCAL_QUORUM` | Quá bán replicas ở local DC | Read/write homed trong một DC | Không cam kết instant visibility tại DC khác |
| `EACH_QUORUM` | Quorum trong **mỗi** DC liên quan | **Write** yêu cầu local quorum ở nhiều DC | Availability giảm nếu một DC không đáp ứng |
| `ALL` | Tất cả replicas phản hồi | Trường hợp cần ACK từ mọi replica | Rất nhạy với replica chậm/lỗi |
| `ANY` | Một replica xác nhận hoặc coordinator ghi hint | **Chỉ write** với yêu cầu availability đặc biệt | Hint có thể tạm thời chưa thành row đọc được ở CL=ONE |

**`ANY` chỉ hợp lệ cho write.** Ở trường hợp tất cả replicas của partition đang không thể nhận write, coordinator có thể chấp nhận mutation qua **hinted handoff**. Thành công tại CL=ANY **không chứng minh** một replica đã lưu row và một read `ONE` có thể nhìn thấy nó ngay; không chọn ANY cho nghiệp vụ cần read-after-write.

**`EACH_QUORUM` chủ yếu dùng cho write** trong chiến lược replication multi-DC, không phải CL đọc thông dụng. Đừng đánh đồng với `QUORUM` toàn cluster: ví dụ RF=3 ở dc1 và RF=3 ở dc2 thì EACH_QUORUM yêu cầu **2 ACK tại mỗi DC**, trong khi QUORUM của tổng RF=6 yêu cầu **4 responses toàn cluster** mà không bắt buộc đúng hai mỗi DC.

### 4.1. SERIAL và LOCAL_SERIAL không thay cho ONE/QUORUM

`SERIAL` và `LOCAL_SERIAL` phục vụ **serial consistency** của Cassandra **lightweight transactions**, thường với câu CQL `IF NOT EXISTS` hoặc `IF version = ?`. Chúng điều phối giai đoạn consensus/compare-and-set trong phạm vi được hỗ trợ.

- `SERIAL` xét serial consensus trên phạm vi replica phù hợp; có thể liên quan nhiều DC.
- `LOCAL_SERIAL` giới hạn phạm vi local datacenter theo kiến trúc LWT.
- LWT vẫn có **regular consistency level** cho giai đoạn ghi/đọc kết quả, ví dụ `LOCAL_QUORUM`.
- **Không đặt `SERIAL` làm regular CL của một INSERT thường** để mong tự tạo transaction.

Khi cần kiểm tra `[applied]`, dùng gateway/driver có reply; một Cassandra outbound adapter **một chiều** sẽ không tự trả kết quả LWT cho caller.

## 5. Chọn consistency theo topology và yêu cầu nghiệp vụ

Không có “CL mạnh nhất luôn tốt nhất”. Một ứng dụng đọc trạng thái thanh toán cần độ chính xác cao, còn hệ thống thu thập metrics có thể chấp nhận độ trễ hội tụ. Mỗi trường hợp phải xem **read-after-write**, **availability khi node/DC lỗi**, **p99 latency**, **repair strategy**, và ranh giới business transaction.

### 5.1. Một DC, RF=3

Với `NetworkTopologyStrategy` và `dc1:3`:

- `ONE` cần ít nhất một replica phản hồi.
- `LOCAL_QUORUM` hoặc `QUORUM` cần hai responses trong trường hợp một DC.
- `ALL` cần cả ba.
- Nếu một replica unavailable, quorum còn có thể thành công; `ALL` có thể thất bại.
- Nếu hai replicas unavailable, `LOCAL_QUORUM` không đạt dù còn một node đang khỏe.

**Đừng hiểu “quorum chịu lỗi một node” là toàn hệ thống không bao giờ timeout khi một node chết.** Nếu node còn lại quá tải, network timeout hoặc coordinator gặp sự cố, request vẫn có thể lỗi.

### 5.2. Hai DC, mỗi DC có RF=3

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_multidc
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Giả sử ứng dụng ở `dc1` và chọn read/write `LOCAL_QUORUM`:

~~~mermaid
flowchart TB
    APP["Application gần dc1"] --> COORD["Coordinator ở dc1"]
    COORD --> A1[("dc1 replica A")]
    COORD --> A2[("dc1 replica B")]
    COORD --> A3[("dc1 replica C")]
    COORD --> B1[("dc2 replica D")]
    COORD --> B2[("dc2 replica E")]
    COORD --> B3[("dc2 replica F")]
    A1 -. "ACK local 1" .-> COORD
    A2 -. "ACK local 2" .-> COORD
    COORD --> RESULT["Đủ local quorum; trả thành công"]
~~~

Trong ví dụ này, `LOCAL_QUORUM` cần **hai ACK từ dc1**, không yêu cầu ACK từ dc2 trước khi trả lời. Replication sang dc2 có thể vẫn tiếp diễn hoặc chậm. Sau một write thành công ở dc1, một read `LOCAL_QUORUM` **tại dc2** chưa chắc thấy write ngay nếu replication chưa hội tụ.

Nếu nghiệp vụ yêu cầu giao dịch phải được xác nhận qua nhiều DC **trước** khi phản hồi thành công, cần đánh giá `EACH_QUORUM` cho writes hoặc mô hình khác; chấp nhận tăng latency và giảm availability khi một DC gặp lỗi. Với read `QUORUM` trên tổng RF=6, cần bốn responses; điều này tăng phụ thuộc liên vùng so với read `LOCAL_QUORUM`.

### 5.3. Câu hỏi trước khi chọn CL

| Câu hỏi | Ảnh hưởng đến thiết kế |
|---|---|
| Chỉ có một DC hay multi-DC? | Local vs global quorum, WAN latency |
| RF trên mỗi DC thực tế là bao nhiêu? | Số ACK cần thiết, khả năng chịu node failure |
| App có cố định ở một DC không? | Read-your-writes khi dùng LOCAL_QUORUM |
| Có yêu cầu đọc ngay sau khi ghi không? | Chọn R/W giao nhau và đánh giá LWT |
| Nếu một replica chậm, có cho phép request thành công? | ONE/LOCAL_QUORUM/ALL |
| Thời hạn HTTP/JMS callback bao lâu? | Driver timeout, ack boundary, p99 |
| Write có idempotent không? | Driver retry policy và redelivery |
| Cần compare-and-set hay unique claim không? | LWT với regular + serial CL |
| Có đọc dữ liệu tại DC khác ngay không? | Replication propagation và read consistency |

### 5.4. Consistency không tự giải quyết xung đột phiên bản

Cassandra sử dụng timestamp/last-write-wins để hòa giải concurrent mutations. Nếu `OrderCancelled(v3)` và `OrderPaid(v2)` đến từ hai đường xử lý khác nhau, chọn read/write `ALL` **không** tự bảo vệ thứ tự nghiệp vụ. Cần `aggregateVersion`, conditional update (LWT) hoặc một protocol ứng dụng phù hợp.

**Kết luận phần này:** CL là lựa chọn về **số phản hồi đủ để hoàn tất request**, không phải quy tắc ordering, uniqueness hay phân tán transaction giữa Cassandra và hệ thống nguồn.

## 6. Phân biệt bốn nhóm timeout

Một flow có thể có **nhiều đồng hồ đếm ngược độc lập**. Chúng không được tự cộng/trừ hoặc kế thừa lẫn nhau:

~~~mermaid
flowchart TD
    HTTP["HTTP client/API deadline"] --> SI["Spring Integration: send/reply timeout"]
    SI --> Driver["Java driver request timeout"]
    Driver --> Coord["Cassandra coordinator"]
    Coord --> Server["Server-side read/write timeout"]
    Server --> Replicas[("Replica I/O")]
    Broker["JMS/Kafka ack/redelivery lifecycle"] -. "Ranh giới riêng" .-> SI
~~~

| Timeout/deadline | Cấu hình ví dụ | Bắt đầu/kết thúc ở đâu? | Quan sát |
|---|---|---|---|
| **Java Driver request timeout** | `basic.request.timeout` hoặc `Statement.setTimeout(Duration)` | Tổng thời gian một **driver request** ở client, gồm retries/speculative executions | `DriverTimeoutException` khi client hết hạn |
| **Cassandra server read/write timeout** | `read_request_timeout`, `write_request_timeout` trong config Cassandra tương ứng version | Coordinator/server chờ replica responses | `ReadTimeoutException` hoặc `WriteTimeoutException` (server-side) |
| **Spring Integration channel send timeout** | `send(message, timeout)` trên `MessageChannel` hỗ trợ blocking send | Thời gian chờ bàn giao vào channel | Send trả `false` hoặc lỗi theo channel; không là DB deadline |
| **Spring Integration gateway reply timeout** | `replyTimeout` trên gateway phù hợp | Chờ Spring reply message | Timeout của request-reply, khác CQL write confirmation |
| **HTTP/gRPC caller deadline** | API gateway, client/service timeout | Caller chờ response | Caller có thể ngừng chờ trước khi backend hoàn tất |
| **JMS acknowledgment/transaction** | Listener container, broker policy | Commit/rollback và redelivery | Không mặc định có cùng deadline với CQL |
| **Kafka poll/processing lifecycle** | Consumer configs, offset commit và poll loop | Consumer membership/offset xử lý | Không tương đương Cassandra timeout |
| **Reactive publisher deadline** | Reactor `timeout(Duration)` | Subscriber chờ signal | Timeout có thể cancel subscription, không rollback remote mutation đã nhận |

**Một driver timeout không phải Spring Integration `sendTimeout`.** Tăng `sendTimeout` lên 30 giây không nhất thiết giúp một Cassandra CQL request hết hạn sau 2 giây. Tương tự, tăng driver timeout không kéo dài deadline HTTP client hay bảo đảm JMS session sẽ được giữ mở.

### 6.1. Driver request timeout là tổng thời hạn request

Trong Java Driver 4.x, `basic.request.timeout` đặt thời gian tối đa mà một request được giữ ở phía driver, **bao gồm retry và speculative executions** của request đó (không phải cấp thêm một timeout nguyên vẹn cho từng attempt). Khi hết hạn, caller có thể nhận `DriverTimeoutException`.

Ví dụ:

~~~text
Client driver request timeout: 2 giây
 t=0ms       gửi CQL
 t=350ms     có một attempt lỗi, driver thử coordinator khác nếu policy cho phép
 t=1100ms    request chưa hoàn tất
 t=2000ms    client deadline hết, DriverTimeoutException

Trên Cassandra server:
 - Mutation của attempt 1 hoặc 2 có thể vẫn đã được xử lý.
 - Kết quả tại t=2500ms không còn tới caller đang chờ.
~~~

**Không lấy thời gian request timeout mặc định của một version làm SLA của mọi cluster.** Tài liệu Java Driver 4.x thường đưa mặc định `2 seconds` và `LOCAL_ONE` trong `reference.conf`, nhưng Spring Boot, execution profile hoặc cấu hình ứng dụng có thể override; hãy đọc effective configuration thực tế.

### 6.2. Server-side read/write timeout

Server `ReadTimeoutException` cho biết coordinator đã gửi request nhưng **không nhận đủ responses theo CL trước ngưỡng server-side**. `WriteTimeoutException` tương tự với write. Cả hai có thể kèm số responses nhận được và số cần thiết.

Ví dụ CL=LOCAL_QUORUM, RF=3:

~~~text
Coordinator chờ 2 local responses.
Replica A: ACK.
Replica B: chậm.
Replica C: chậm.
Hết hạn write timeout ở coordinator -> WriteTimeoutException.
~~~

Không thể suy ra rằng A chưa ghi. B/C có thể cập nhật sau đó; coordinator có thể phát tín hiệu lỗi khi một số replicas đã lưu. **Retry mù quáng** một counter increment, side-effect không idempotent hoặc write với timestamp thay đổi có thể làm sai nghiệp vụ.

### 6.3. Tại sao có timeout phía driver nhưng không có server timeout?

Client có thể hết hạn khi:

- Network chậm/mất packet, response bị mất.
- Request bị queue trong driver/throttler, không kịp phát đến coordinator.
- Connection pool/coordinator quá tải.
- Request đang retry/đợi speculative executions.
- Server phản hồi sau driver deadline.

Vì vậy **`DriverTimeoutException` không khẳng định server coordinator từng nhận request hay chưa**. Cần đối chiếu logs/traces/metrics ở driver và Cassandra cluster.

### 6.4. Timeout cấp Reactor hoặc HTTP cũng không hoàn tác một remote write

Trong một reactive flow:

~~~java
return reactiveCassandraOperations.insert(event)
        .timeout(java.time.Duration.ofSeconds(2));
~~~

Đây là **fragment trong service** có bean `reactiveCassandraOperations` và entity `event`. Nếu Reactor timeout/cancel subscription sau 2 giây, **không có transaction rollback tự động** đối với một mutation đã được Cassandra coordinator nhận. Cần idempotency hoặc đọc/đối soát để xử lý kết quả không chắc chắn.

## 7. Cấu hình consistency và timeout bằng Java Driver 4.x

Java Driver 4.x quản lý lựa chọn mặc định ở `application.conf`/`reference.conf` hoặc programmatic `DriverConfigLoader`. Để xác định hành vi cần nhìn **effective driver config**, vì Spring Boot và code ứng dụng có thể override giá trị mặc định.

### 7.1. HOCON cấu hình mặc định

File `application.conf` **của ứng dụng** (không phải YAML metadata của bài học):

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
  }
}
~~~

Với RF=3 ở local datacenter phù hợp, cấu hình trên yêu cầu quorum hai responses và chờ tối đa 3 giây ở driver. **3 seconds là giá trị ví dụ cho lab, không phải khuyến nghị SLA production**. Nếu cluster chỉ có RF=1, `LOCAL_QUORUM` cũng cần một replica; phép thử đó không đại diện môi trường RF=3.

### 7.2. Execution profiles cho workload khác nhau

Một ứng dụng vừa ghi sự kiện cần độ nhất quán cao, vừa đọc bảng thống kê có thể chấp nhận dữ liệu hội tụ:

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
  }
  profiles {
    order-events {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 3 seconds
    }
    dashboard-read {
      basic.request.consistency = LOCAL_ONE
      basic.request.timeout = 1500 milliseconds
    }
  }
}
~~~

Trong thực tế, chọn profile còn phải xét auth, routing, p99, consistency giữa read và write, và tính chất dữ liệu. Đặt `dashboard-read=LOCAL_ONE` nghĩa là **chấp nhận nguy cơ đọc chưa thấy write mới**; không dùng profile đó cho màn hình bắt buộc read-your-writes mà không có cơ chế khác.

Một driver statement có thể chọn profile:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement stmt = SimpleStatement.builder(
        "SELECT event_type FROM order_event WHERE event_id = ?")
        .addPositionalValue("evt-6001")
        .setExecutionProfileName("dashboard-read")
        .build();

// session là CqlSession đã được Spring inject.
session.execute(stmt);
~~~

Ở đây `"dashboard-read"` phải tồn tại trong driver config; `SimpleStatement` chỉ dùng giá trị bind qua API, không ghép event ID vào CQL string.

### 7.3. Override một request bằng Statement API

Khi cần exception cho một loại operation cụ thể:

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement stmt = SimpleStatement.builder(
        "SELECT event_type FROM order_event WHERE event_id = ?")
        .addPositionalValue("evt-6001")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(2))
        .setIdempotent(true)
        .build();

session.execute(stmt);
~~~

`Statement.setTimeout(Duration)` chỉ override **driver request timeout** cho statement. Nó **không** sửa `read_request_timeout` trên Cassandra server hoặc deadline HTTP caller. `setIdempotent(true)` cho phép driver cân nhắc retry/speculative execution theo policy; với read-only SELECT thường hợp lý, nhưng với write side effects cần đánh giá riêng.

### 7.4. PreparedStatement và BoundStatement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
        "INSERT INTO order_event "
        + "(event_id, event_type, payload_json) VALUES (?, ?, ?)");

BoundStatement write = prepared.boundStatementBuilder()
        .setString(0, "evt-6001")
        .setString(1, "OrderPaid")
        .setString(2, "{\"eventId\":\"evt-6001\"}")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true)
        .build();

session.execute(write);
~~~

Đoạn trên là ví dụ trong một service có `session` bean và bảng `order_event` đã tạo. Khi dùng `setIdempotent(true)` cho INSERT, giả định có **`eventId` ổn định, cùng payload immutable và không có side effects khác**; nếu retry sinh giá trị mới, timestamp khác làm thay đổi kết quả hoặc event ID mới, đánh dấu idempotent có thể không phù hợp.

**BoundStatement là immutable ở driver 4.x.** Nếu dùng `bound.setTimeout(...)` hoặc `bound.setConsistencyLevel(...)`, phải dùng **giá trị trả về**; nếu không gán lại, statement ban đầu không thay đổi. Dùng `boundStatementBuilder()` với chain như trên để tránh lỗi này.

### 7.5. Programmatic config thay vì HOCON

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;

DriverConfigLoader loader = DriverConfigLoader
        .programmaticBuilder()
        .withDuration(DefaultDriverOption.REQUEST_TIMEOUT, Duration.ofSeconds(3))
        .withString(DefaultDriverOption.REQUEST_CONSISTENCY, "LOCAL_QUORUM")
        .build();

// Đưa loader vào CqlSession.builder().withConfigLoader(loader) khi tạo session.
~~~

Đoạn này là phương án thay thế **HOCON config** khi ứng dụng tự khởi tạo driver session. Nếu dùng Spring Boot auto-config, việc tự tạo thêm một `CqlSession` hoặc loader mà không wire vào session thực tế **không đổi hành vi endpoint**. Hãy kiểm tra bean/config nào đang có hiệu lực thay vì tin rằng file cấu hình được đọc chỉ vì nó tồn tại.

### 7.6. Kiểm tra effective config

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

DriverExecutionProfile profile = session.getContext()
        .getConfig()
        .getDefaultProfile();

System.out.println(
        "request timeout = "
        + profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT));
System.out.println(
        "consistency = "
        + profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY));
~~~

Đây là đoạn debug trong lab, **không in secrets/cấu hình nhạy cảm**. Khi dùng named execution profile, kiểm tra profile đó thay vì chỉ nhìn default profile. Bên cạnh request settings, retry policy và speculative execution policy cũng ảnh hưởng tổng thời gian và số attempts.

## 8. Spring Data Cassandra: `WriteOptions`, `QueryOptions` và template

Spring Data cho phép chỉ định CL/timeout ở cấp operation thông qua:

- `WriteOptions` cho entity writes `INSERT/UPDATE/DELETE`.
- `QueryOptions` cho CQL/query operations tương thích.
- Execution profiles hoặc driver statements khi cần settings chuyên biệt.
- `CqlTemplate`/`ReactiveCqlTemplate` và `CassandraTemplate`/`ReactiveCassandraTemplate` ở các tầng trừu tượng khác nhau.

**Không trộn `ttl` với `timeout`:** `WriteOptions.ttl(...)` nói về **thời gian sống của dữ liệu**, còn `WriteOptions.timeout(...)` nói về **thời hạn client chờ operation**. Cả hai có cùng kiểu Java `Duration` nhưng ý nghĩa hoàn toàn khác.

### 8.1. Tạo WriteOptions có CL và timeout

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.WriteOptions;

WriteOptions durableOrderEventWrite = WriteOptions.builder()
        .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .timeout(Duration.ofSeconds(3))
        .idempotent(true)
        .build();
~~~

Theo Spring Data Cassandra Javadoc, `WriteOptions` kế thừa `QueryOptions` và có builders `consistencyLevel(...)`, `timeout(...)`, `serialConsistencyLevel(...)`, `executionProfile(...)`, `idempotent(...)`. Chỉ những options **được set** mới được áp vào query; phần chưa đặt có thể theo driver defaults.

`idempotent(true)` trong ví dụ chỉ phù hợp với event-store operation đã **được review là idempotent**. Nó **không tự thêm unique constraint** vào Cassandra và không deduplicate JMS/Kafka events.

### 8.2. Dùng trong Cassandra outbound channel adapter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow orderEventWriteFlow(
        ReactiveCassandraOperations operations,
        WriteOptions durableOrderEventWrite) {

    return IntegrationFlow.from("orderEventWriteRequests")
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(durableOrderEventWrite),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Flow này nhận Spring Message có **entity payload đã map bằng `@Table`**. `CassandraMessageHandler` gọi `ReactiveCassandraOperations`, áp `WriteOptions` cho mode `INSERT` và chờ operation khi `async(false)`. Với Spring Integration Cassandra, **mặc định handler asynchronous**, nên nếu không chọn sync, kết quả write có thể đến **sau khi upstream `send()` kết thúc**.

**`.writeOptions(...)` trong Cassandra DSL dành cho `INSERT`, `UPDATE`, `DELETE`; đừng mặc định nó sẽ áp timeout/CL của một driver `Statement<?>` mà bạn tự tạo bằng `statementFunction(...)`.** Với mode `STATEMENT`, đặt options trên statement hoặc driver execution profile.

### 8.3. Bean configuration đầy đủ cho ví dụ WriteOptions

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.WriteOptions;

@Configuration
class CassandraWriteOptionsConfig {
    @Bean
    public WriteOptions durableOrderEventWrite() {
        return WriteOptions.builder()
                .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .timeout(Duration.ofSeconds(3))
                .idempotent(true)
                .build();
    }
}
~~~

Đặt bean này **trước khi handler bắt đầu xử lý**. Không đổi cùng singleton `WriteOptions` hoặc cấu hình handler từ một client header `consistency="ANY"` vì sẽ mở đường để nguồn không đáng tin làm yếu CL của business write.

### 8.4. Dùng `QueryOptions` cho read query phù hợp

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.QueryOptions;

QueryOptions readOptions = QueryOptions.builder()
        .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .timeout(Duration.ofSeconds(2))
        .pageSize(100)
        .build();
~~~

`QueryOptions` mô tả settings cho query/read operations. **Cách gắn đối tượng này vào `CassandraTemplate`/repository query phụ thuộc API/overload và phiên bản Spring Data đang dùng**; không lắp vào `CassandraMessageHandlerSpec.writeOptions(...)` của mode `STATEMENT` rồi giả định nó sẽ được đọc. Với Spring Integration Cassandra gateway SELECT dùng query string, có thể chọn **driver execution profile** mặc định cho query, hoặc tạo `Statement<?>` đã được cấu hình CL/timeout và dùng `statementFunction(...)`.

### 8.5. Khi nào dùng `CqlTemplate` thay vì CassandraMessageHandler?

Nếu ứng dụng chủ động dùng imperative `CqlTemplate` trong một Spring `@ServiceActivator`, nó chạy **blocking CQL** và có thể dùng driver statements/callbacks hoặc template configuration. Ngược lại Cassandra outbound adapter/gateway có sẵn yêu cầu `ReactiveCassandraOperations`; không truyền `CqlTemplate` vào constructor `CassandraMessageHandler`.

Với reactive `Mono`/`Flux`, nhớ rằng publisher **lazy**: tạo `Mono` không có nghĩa I/O đã chạy. Sử dụng subscription/error handling đúng để timeout và exception không bị mất. **Không dùng `block()` trên WebFlux event-loop** chỉ để tạo cảm giác đồng bộ.

## 9. Cassandra outbound adapter và gateway: timeout đi đến đâu?

**Outbound channel adapter** và **outbound gateway** đều dùng `CassandraMessageHandler` nhưng có hợp đồng response khác nhau:

| Endpoint | Phản hồi Spring Message | Điều cần quan sát |
|---|---|---|
| `Cassandra.outboundChannelAdapter(...)` | Một chiều, không reply nghiệp vụ | Write completion và error path |
| `Cassandra.outboundGateway(...)` | Có reply theo operation | Query result/WriteResult, correlation và reply channel |
| Handler `async=true` (mặc định) | Xử lý reactive/asynchronous | Caller có thể kết thúc trước I/O |
| Handler `async=false` | Chờ kết quả reactive operation | Có thể propagate exception theo đường channel đồng bộ |

### 9.1. Gateway SELECT với CL/timeout trên statement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow findEventWithTimeout(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("findEventRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .statementFunction(message -> {
                        String eventId = (String) message.getPayload();
                        return SimpleStatement.builder(
                                "SELECT event_id, event_type FROM order_event "
                                + "WHERE event_id = ?")
                                .addPositionalValue(eventId)
                                .setConsistencyLevel(
                                        DefaultConsistencyLevel.LOCAL_QUORUM)
                                .setTimeout(Duration.ofSeconds(2))
                                .setIdempotent(true)
                                .build();
                    }),
                    endpoint -> endpoint.async(false))
            .channel("findEventResults")
            .get();
}
~~~

`findEventRequests` là một Spring input channel; payload là `String eventId` đã được validate. `statementFunction(...)` trả driver `Statement<?>` với bind value, CL và driver request timeout. `findEventResults` phải có **consumer** phù hợp; với query nhiều rows phải xử lý đúng kiểu reply của Cassandra gateway/driver trong version dùng.

**Đây là một flow thay thế** cho outbound adapter INSERT ở mục 8, không nên đăng ký hai endpoint cùng input channel nếu chỉ muốn thực hiện một operation. `async(false)` giúp nhìn thấy lỗi trong đường gọi đồng bộ nhưng có thể block thread; không triển khai trên event-loop có yêu cầu nonblocking.

### 9.2. Điều gì xảy ra khi có `DirectChannel`?

~~~mermaid
sequenceDiagram
    participant P as Upstream Service
    participant Ch as DirectChannel
    participant H as CassandraMessageHandler async=false
    participant DB as Cassandra

    P->>Ch: send(message)
    Ch->>H: handle(message)
    H->>DB: INSERT / SELECT
    alt Operation completed
        DB-->>H: Completion / result
        H-->>Ch: Handler returns
        Ch-->>P: send returns
    else Exception propagated
        DB-->>H: timeout/unavailable/error
        H-->>Ch: Exception
        Ch-->>P: Exception
    end
~~~

Trên `DirectChannel` với handler sync, caller có cơ hội thấy exception trước khi source JMS listener kết thúc callback. Nhưng **bất kể CL nào**, Cassandra write và JMS commit **không atomic**.

### 9.3. Điều gì thay đổi khi dùng async channel hoặc handler?

~~~text
JMS inbound listener
  -> ExecutorChannel / QueueChannel (in-memory) / Cassandra async handler
  -> listener có thể return/commit
  -> Cassandra write đang chạy
  -> Cassandra timeout xảy ra sau source commit
~~~

Trong trường hợp đó một lỗi Cassandra **không tự rollback lại JMS message đã commit**. Muốn bền vững cần thiết kế:

- Chỉ acknowledge/commit nguồn sau khi đích xác nhận completion khi cơ chế cho phép.
- Durable handoff/inbox/outbox để có thể replay công việc chưa hoàn tất.
- Recovery worker có idempotency và retry budget.
- Một quy trình DLQ/quarantine khi gặp lỗi không thể sửa bằng retry.

**Không coi `errorChannel` là một broker DLQ.** Nó là Spring MessageChannel cho `ErrorMessage`; phải thiết kế rõ cách errors được chuyển tới nguồn/monitoring hoặc kho bền vững.

### 9.4. Spring gateway reply timeout khác Cassandra request timeout

Khi gọi một request/reply gateway để truy vấn Cassandra:

~~~text
Spring gateway replyTimeout = 1500 ms
Driver request timeout       = 3000 ms
Cassandra server read timeout = giá trị theo server config
~~~

Gateway có thể ngừng chờ Spring reply sau 1,5 giây trong khi Cassandra request vẫn đang tiếp tục. **Không có rollback tự động** cho remote write nếu request đã tới coordinator. Nếu chọn timeout phân tầng, cân nhắc driver deadline **ngắn hơn deadline dành cho caller** (còn chừa thời gian transform/network/error handling), nhưng phải kiểm tra thực tế vì một số async boundaries không tự hủy downstream operation.

## 10. Phân loại lỗi nhất quán và lỗi timeout

### 10.1. Những exception quan trọng

| Driver exception | Nguồn lỗi | Ý nghĩa cần hiểu |
|---|---|---|
| `UnavailableException` | Cassandra coordinator | Coordinator biết không đủ replicas **đang khả dụng** để đáp ứng CL đã chọn |
| `ReadTimeoutException` | Cassandra coordinator | Read không nhận đủ responses đúng hạn theo read CL |
| `WriteTimeoutException` | Cassandra coordinator | Write không nhận đủ ACK đúng hạn theo write CL |
| `ReadFailureException` | Cassandra coordinator | Replica/coordinator báo lỗi read khác timeout |
| `WriteFailureException` | Cassandra coordinator | Replica/coordinator báo lỗi write khác timeout |
| `DriverTimeoutException` | Java Driver client | Tổng request deadline ở driver đã hết |
| `AllNodesFailedException` / `NoNodeAvailableException` | Java Driver client | Không tìm được coordinator/attempt thành công trong query plan |
| `OverloadedException` | Cassandra coordinator | Node quá tải, có thể cần giảm concurrency |
| `UnauthorizedException` / `InvalidQueryException` | Cassandra server | Quyền hoặc query/schema không hợp lệ; retry nguyên dạng thường vô ích |

**Spring Data Cassandra có exception translation** sang `DataAccessException` hoặc runtime exception phù hợp. Vì vậy tầng Spring service có thể không thấy nguyên class driver ở top-level; khi phân loại sự cố, xem cause chain và metadata **mà không làm rò bí mật**. Đừng viết retry chỉ dựa vào string `"timeout"` trong exception message.

### 10.2. `Unavailable` khác timeout như thế nào?

Ví dụ RF=3, CL=QUORUM cần 2 responses:

- **Unavailable:** coordinator đã biết chỉ có 1 replica live/reachable theo thông tin hiện tại, nên **không thể đạt CL ngay**.
- **WriteTimeout:** coordinator đã thử write nhưng **không nhận đủ ACK trước thời hạn**.
- **DriverTimeout:** client không thấy kết quả cuối cùng trong request deadline; có thể server chưa nhận, đang chờ hoặc đã ghi xong.

Unavailable không nhất thiết là “cluster chết”; cluster có thể còn một replica phục vụ `ONE`, nhưng điều đó không hợp thức hóa việc tự downgrade CL để “cho chạy”.

### 10.3. Các con số trong server-side timeout

Trong `ReadTimeoutException` và `WriteTimeoutException`, driver/server có thể cho biết `received` và `blockFor` (số responses đã nhận và số cần theo CL); với write còn có `writeType`, với read có `dataPresent` theo API.

~~~text
WriteTimeout:
    CL = LOCAL_QUORUM
    required/blockFor = 2
    received = 1

Diễn giải đúng:
    Không đủ ACK cho write CL.
    Một replica có thể đã lưu; outcome toàn cục chưa chắc.

Diễn giải sai:
    Không replica nào đã ghi, có thể retry counter tùy ý.
~~~

Chỉ dùng các số này cho observability/diagnostics; **không tự suy rằng mọi replica còn lại chắc chắn đã hoặc chưa lưu**.

### 10.4. Retry nào là hữu ích?

| Kịch bản | Hướng xử lý | Không nên |
|---|---|---|
| Temporary unavailable hoặc overload | Circuit breaker/backoff; thử lại có giới hạn khi operation idempotent | Retry liên tục với concurrency lớn |
| Write timeout, outcome không chắc | Giữ cùng eventId, idempotent retry/reconcile | Sinh eventId mới rồi insert |
| Read timeout | Retry có giới hạn/điều chỉnh workload khi phù hợp | Tự hạ CL của read quan trọng |
| Invalid CQL, missing table | Fail-fast, sửa schema/migration/config | Retry 100 lần cùng câu CQL |
| Unauthorized/bad credentials | Alert, sửa ACL/secrets | Thử lại vô hạn mà không đổi quyền |
| Codec/type mismatch | Sửa transformer/contract | Coi là lỗi tạm thời của cluster |
| LWT applied=false | Đọc/kiểm tra state; xử lý business conflict | Coi là transport error cần retry vô điều kiện |

### 10.5. Không tự downgrade consistency khi gặp lỗi

Ví dụ một nghiệp vụ đặt `LOCAL_QUORUM` vì cần tính chất read-after-write trong local DC. Nếu driver policy tự động downgrade write sang `ONE`, các giả định về độ nhất quán **có thể không còn đúng**. Tài liệu Java Driver cảnh báo về `ConsistencyDowngradingRetryPolicy`. Đừng bật nó trên các luồng thanh toán/audit chỉ để giảm error rate.

### 10.6. Speculative execution

Java Driver có thể thực hiện **speculative execution**: gửi thêm attempt tới coordinator khác khi request chậm, nhằm giảm tail latency. Nó **mặc định bị tắt** trong cấu hình driver 4.x và chỉ được áp cho những request được xem là **idempotent**.

Đánh đổi:

- Tăng request traffic trong lúc cluster chậm.
- Các speculative attempts có thể cùng thực thi; việc “cancel” ở driver thường chỉ bỏ qua response, **không thu hồi mutation đã gửi**.
- Mỗi speculative attempt có thể kích hoạt retries riêng.
- Có thể làm outage nặng hơn khi cluster đang quá tải.

Với event log upsert cùng key/cùng payload, speculative/retry có thể dễ chấp nhận hơn; với counter increment, email sending hoặc side effects ngoài Cassandra, **không đánh dấu idempotent chỉ để bật speculative execution**.

## 11. Thiết kế timeout budget từ SLA đầu nguồn

Một API phải phản hồi trong 5 giây không nên dành trọn 5 giây chỉ cho Cassandra. Còn có thời gian nhận request, authentication, validation, serialization, truyền qua channel, network tới client và xử lý lỗi.

### 11.1. Một ví dụ về phân bổ thời gian

Giả sử **HTTP caller deadline = 5 giây** và workload normal p99 Cassandra thường dưới 1 giây. Phương án để thảo luận:

~~~text
HTTP / API gateway hard deadline               5000 ms
  authentication + validation + routing          300 ms dự trù
  Cassandra driver request timeout              2500 ms
  Spring reply wait budget                      3500 ms
  response transform / network buffer            500 ms
  khoảng dự phòng cho jitter / scheduler         phần còn lại
~~~

Các số là **ví dụ minh họa**, không phải công thức cộng đơn giản. Một số khoảng có thể **chồng lấn** khi xử lý bất đồng bộ; total budget phải được đo bằng traces trong pipeline thực. Spring channel reply timeout 3500 ms chỉ có ý nghĩa nếu flow thật sự dùng một gateway **chờ reply**.

Quy tắc triển khai:

1. Đo p95/p99 thực tế từng bước khi không có lỗi.
2. Chọn deadline của business operation, không chỉ network timeout.
3. Cho driver timeout thấp hơn caller deadline một khoảng đủ để chuyển exception/response.
4. Chọn **retry budget** trong khoảng deadline còn lại; không khởi động một retry mới khi đã chắc chắn không thể hoàn tất trước deadline.
5. Với HTTP timeout, quyết định trả **failure**, **accepted + status URL**, hoặc trạng thái **uncertain/pending reconciliation** theo contract; không báo “write chắc chắn thất bại” khi chưa biết.
6. Với JMS/Kafka, ranh giới acknowledge/offset có thể khác HTTP; dùng nguyên tắc completion/transaction riêng.

### 11.2. Không chỉ tăng timeout để chữa cluster quá tải

Nếu write p99 tăng từ 200ms lên 8s vì hot partition, compaction hoặc network congestion, tăng driver timeout từ 2s lên 30s có thể làm **nhiều requests nằm chờ**, tạo thêm memory pressure/in-flight backlog và che dấu nút thắt.

Nếu ứng dụng có 1000 incoming messages/s và Cassandra chỉ xử lý được 500 writes/s ổn định, backlog tăng khoảng **500 messages mỗi giây** khi không có backpressure/giới hạn nguồn. Timeout dài hơn không giúp tạo năng lực xử lý mới.

### 11.3. Hủy request phía client không đồng nghĩa hủy bên Cassandra

Client deadline/cancel có thể chỉ khiến application không đợi nữa. Cassandra coordinator có thể đã gửi mutations đi; với `INSERT` đã áp dụng trên replica, **không thể coi cancel là database rollback**. Cần dùng business `eventId` và reconciliation để xử lý trạng thái không chắc.

## 12. Idempotency và tính đúng đắn qua timeout

### 12.1. Ghi sự kiện có khóa nghiệp vụ cố định

Schema lab:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

Payload:

~~~json
{
  "eventId": "evt-6001",
  "orderId": "ORD-6001",
  "eventType": "OrderPaid",
  "payloadJson": "{\"currency\":\"VND\",\"amountMinor\":150000}"
}
~~~

Nếu cùng event được gửi lại sau timeout:

- Giữ **cùng `eventId`** qua JMS redelivery, Kafka replay và HTTP retry.
- Dùng cùng partition/full primary key.
- Giữ payload event bất biến; cùng eventId nhưng nội dung khác cần được phát hiện là **conflicting event**.
- Không tự tạo một `UUID.randomUUID()` mới ở consumer mỗi lần nhận event.
- Nếu write có TTL hoặc mutation timestamp khác theo retry, kiểm tra rằng operation **thực sự idempotent theo nghiệp vụ**; upsert không luôn tương đương một kết quả bất biến trong mọi schema.

### 12.2. Một timeline lỗi cụ thể

~~~mermaid
sequenceDiagram
    participant Source as JMS broker
    participant App as Spring Integration
    participant C as Cassandra
    Source->>App: OrderPaid evt-6001
    App->>C: INSERT evt-6001, CL=LOCAL_QUORUM
    C-->>App: Response bị mất / driver timeout
    Note over C: Một hoặc nhiều replicas có thể đã ghi
    App-->>Source: Rollback / không ack theo policy
    Source->>App: Redeliver evt-6001
    App->>C: INSERT lại cùng key và values
    C-->>App: Success
    App-->>Source: Commit / ack
~~~

Flow trên **chỉ an toàn tương đối** nếu operation được thiết kế idempotent. Cassandra regular INSERT không từ chối duplicate key như unique insert RDBMS; nó có **upsert semantics**. Nếu retry cùng ID nhưng `payloadJson` khác, row có thể nhận một giá trị khác tùy timestamp/last-write-wins.

### 12.3. Nguy cơ khi source commit sớm

Với Cassandra handler mặc định async hoặc Spring `ExecutorChannel`, JMS listener có thể acknowledge **trước khi reactive Cassandra operation hoàn tất**. Nếu write timeout sau đó, JMS broker không tự redeliver message đã commit.

Các lựa chọn:

1. Chờ Cassandra completion trong ranh giới xử lý nguồn khi hạ tầng/throughput cho phép.
2. Ghi message vào một **durable handoff/inbox** trước khi ack nguồn, sau đó worker riêng ghi Cassandra.
3. Có recovery/reconciliation job và bộ lưu trạng thái event để phát lại operation chưa hoàn tất.

**Không gọi lựa chọn (1) là distributed transaction.** Cassandra write có thể thành công nhưng JMS commit thất bại → broker vẫn giao lại; vì vậy **idempotency vẫn bắt buộc**.

### 12.4. Tránh side effect không idempotent

| Operation | Retry khi không rõ outcome | Điều kiện cần xem xét |
|---|---|---|
| `INSERT` event immutable theo `eventId` | Thường có thể | Khóa/values ổn định, TTL/timestamp semantics |
| `SELECT` theo eventId | Thường có thể | Dữ liệu có thể đổi giữa hai lần đọc |
| `UPDATE SET state = ?` | Có điều kiện | Version guard/ordering, timestamp |
| `UPDATE counter = counter + 1` | Không an toàn để retry mù | Một retry có thể tăng hai lần |
| Gửi email/HTTP sau Cassandra write | Không tự idempotent | Idempotency key bên hệ ngoài |
| LWT `INSERT IF NOT EXISTS` | Có điều kiện | Phải quan sát `[applied]` và reconcile timeout |

## 13. LWT: regular consistency và serial consistency là hai cấu hình

Một case khác thường gặp: bảng `order_current_state` lưu phiên bản của trạng thái đơn hàng. Hai events đến lệch thứ tự; ứng dụng cần chỉ chấp nhận update khi stored version đúng.

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_current_state (
    order_id text PRIMARY KEY,
    version bigint,
    state text,
    last_event_id text
);

-- Update khi version trước đó khớp.
UPDATE shop_integration.order_current_state
SET version = ?, state = ?, last_event_id = ?
WHERE order_id = ?
IF version = ?;
~~~

Đây là **lightweight transaction** của Cassandra, không phải transaction SQL nhiều bảng. LWT cho phép compare-and-set trong phạm vi partition/condition mà Cassandra hỗ trợ, với **chi phí nhiều vòng trao đổi/consensus** hơn normal write.

### 13.1. Cấu hình một LWT statement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement lwt = SimpleStatement.builder(
        "UPDATE order_current_state "
        + "SET version = ?, state = ?, last_event_id = ? "
        + "WHERE order_id = ? IF version = ?")
        .addPositionalValue(3L)
        .addPositionalValue("CANCELLED")
        .addPositionalValue("evt-6003")
        .addPositionalValue("ORD-6001")
        .addPositionalValue(2L)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
        .setTimeout(Duration.ofSeconds(5))
        .build();

// Cần đọc result.wasApplied() hoặc kết quả tương đương trong gateway/driver.
var result = session.execute(lwt);
boolean applied = result.wasApplied();
~~~

Đây là **đoạn lab** cho một cụm hỗ trợ LOCAL_SERIAL/LOCAL_QUORUM với replication topology tương thích. `LOCAL_SERIAL` có phạm vi local DC, cần xét kỹ failover/multi-DC và business invariants. Timeout 5 giây là minh họa vì LWT thường đắt hơn regular write; không nhân mọi timeout lên 5 giây trên production.

### 13.2. `applied=false` không phải lỗi kết nối

Nếu stored version không bằng `2`, Cassandra có thể trả `[applied]=false`. Đây là **kết quả điều kiện nghiệp vụ không thỏa**, không tự là `UnavailableException`. Handler phải phân loại:

- Stored version đã là `3` với same `last_event_id`: có thể là retry hợp lệ.
- Stored version cao hơn hoặc eventId khác: conflict/out-of-order event, cần xử lý domain.
- Timeout hoặc Unavailable: **không chắc trạng thái**; retry/reconcile theo business key.

Không dùng outbound **adapter một chiều** rồi coi `send(true)` tương đương `[applied]=true`. Cần gateway/driver API đọc được kết quả LWT hoặc quy trình reconcile.

### 13.3. LWT không gộp JMS và Cassandra thành một atomic commit

Ngay cả khi LWT đảm bảo compare-and-set tại Cassandra, một JMS commit có thể thất bại sau khi Cassandra đã applied. Một event sẽ đến lại; cần kiểm tra version/idempotency. Không xây hệ thống dựa trên giả định **“LWT + JMS transacted = exactly once end-to-end”**.

## 14. Backpressure, concurrency và consistency dưới tải cao

**CL và timeout không hoạt động trong chân không**: chúng chịu ảnh hưởng của partition key, replica load, coordinator routing, request queue, compaction, network, timeout/retry configuration và nguồn message.

### 14.1. RF/CL mạnh không sửa được hot partition

Giả sử workload ghi 20.000 events/giây vào một Cassandra partition key. Cả ba replicas của partition đó có thể bị nóng, và `LOCAL_QUORUM` cần ACK từ hai trong ba replicas. Tăng số consumers lên gấp đôi có thể **tăng timeout rate** vì application đẩy thêm requests vào cùng tập replicas.

Hướng điều tra:

1. Kiểm tra **query shape** và partition key; một tenant/key quá nóng?
2. Đo write/read latency p95/p99 theo table/node/coordinator.
3. Đếm in-flight requests và pending tasks; cluster có đang ở ngưỡng overload?
4. Kiểm tra compaction, tombstones, GC pauses, network packet loss, repair.
5. Xem broker backlog/consumer lag và retry rate.
6. Giới hạn concurrency, giảm batch size hoặc xem lại data model/bucketing trước khi tăng request timeout.

### 14.2. Cassandra reactive không cho phép concurrency vô hạn

`ReactiveCassandraOperations` trả publisher, nhưng nếu application subscribe cho mọi message **không giới hạn**, số operations đang thực thi có thể tăng tới mức driver/cluster không đáp ứng.

Ví dụ một reactive pipeline có số operations in-flight hữu hạn:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// Fragment: source là Flux<OrderEvent> đã validate.
Flux<OrderEvent> successfullyWritten = source.concatMap(event ->
        reactiveCassandraOperations.insert(event)
                .map(writeResult -> event)
);
~~~

`concatMap` giữ một publisher active tại một thời điểm trong luồng này, phù hợp để minh họa **bảo toàn thứ tự theo source** nhưng throughput thấp. Với luồng độc lập có thể dùng `flatMap(..., maxConcurrency)` được giới hạn và theo dõi; **không** tự xem kết quả `flatMap` có thứ tự hoàn tất đúng với thứ tự event.

**Lưu ý:** snippet không phải một Spring IntegrationFlow hoàn chỉnh; với Kafka/JMS source, subscription và acknowledgment boundary phải được thiết kế riêng. Nó chỉ minh họa cách giới hạn concurrency khi thao tác reactive Cassandra.

### 14.3. Retry budget end-to-end

Giả sử:

~~~text
Driver retry             tối đa 1 lần theo policy
Service-layer retry      tối đa 2 lần
JMS redelivery           tối đa 5 lần
DLQ replay               có thể thêm sau khắc phục
~~~

Không nên coi các giới hạn riêng lẻ là “nhỏ” rồi bỏ qua tác động nhân giữa các tầng. Trong trường hợp đơn giản với mỗi attempt ở service có tối đa hai driver executions và mỗi JMS delivery có ba service attempts (lần đầu + hai retry), tổng có thể tới **30 attempts** trước DLQ. Speculative execution có thể còn làm tăng số yêu cầu được phát tới cluster.

Nếu write có outcome không chắc, retries chồng nhau còn có thể gây **concurrent writes cùng key**. Giới hạn retry, backoff có jitter, circuit breaker và khả năng queue/durable handoff thường quan trọng hơn việc tiếp tục tăng timeout.

## 15. Metrics và quy trình chẩn đoán timeout

Cassandra cung cấp metrics ở **table**, **keyspace**, **client request** và thread pool levels. Mỗi node có metrics riêng nên hệ thống quan sát cần tổng hợp và so sánh theo cluster/topology.

| Metric / tín hiệu | Vị trí | Ý nghĩa |
|---|---|---|
| Read/Write latency p50/p95/p99 | Cassandra table/coordinator, Java driver | Phân biệt latency bình thường và tail latency |
| ClientRequest Read/Write `Timeouts` | Cassandra coordinator | Server-side timeout counts |
| ClientRequest `Unavailables` / `Failures` | Cassandra coordinator | CL không đạt hoặc server errors |
| Driver `DriverTimeoutException` count | Application/driver | Client-side request deadline hết |
| Driver retries/speculative executions | Driver metrics | Xem số attempts và request amplification |
| In-flight requests/connection saturation | Java driver | Đánh giá overload/backpressure |
| Pending compactions/flushes, dropped messages | Cassandra cluster | Backend quá tải |
| Hot partition / partition sizes | Table diagnostics | Workload skew, phân bố key xấu |
| Source JMS queue depth/Kafka consumer lag | Broker | Downstream chậm khiến backlog |
| Handler completion/error rate | Spring Integration | Endpoint có thật sự hoàn tất operation? |
| Duplicate/conflicting event IDs | Business metrics | Chất lượng retry/redelivery và idempotency |
| LWT applied/condition-not-met | Application/Cassandra CAS metrics | Conflict nghiệp vụ khác transport error |

### 15.1. Truy dấu một timeout theo năm câu hỏi

1. **Exception class là gì?** `UnavailableException`, `WriteTimeoutException`, `DriverTimeoutException` hay gateway reply timeout?
2. **CL thực tế bao nhiêu?** Đọc effective execution profile/statement options; RF và DC topology có phù hợp?
3. **Request đã tới coordinator chưa?** So sánh client traces với Cassandra metrics/logs trong cùng khung thời gian.
4. **Có mutation đã được áp dụng không?** Với eventId cố định, đọc lại theo key khi cần; không tự assume timeout là rollback.
5. **Message nguồn đã ack/commit chưa?** Tìm message ID, eventId, JMS delivery count hoặc Kafka topic/partition/offset; xác định recovery path.

### 15.2. Runbook khi timeout tăng đột biến

~~~mermaid
flowchart TD
    A["Cassandra timeout rate tăng"] --> B{"Client hay server timeout?"}
    B -->|"DriverTimeout"| C["Kiểm tra request deadline, in-flight, network, retries"]
    B -->|"Read/WriteTimeout"| D["Kiểm tra CL, RF, ACK counts, slow replicas"]
    B -->|"Unavailable"| E["Kiểm tra replica health, topology, local DC"]
    C --> F{"Cluster overloaded?"}
    D --> F
    E --> F
    F -->|"Có"| G["Giảm concurrency, dừng retry storm, xử lý node/hot partition"]
    F -->|"Không rõ"| H["Collect traces và driver/server metrics"]
    G --> I["Reconcile events có outcome chưa rõ"]
    H --> I
    I --> J["Replay có kiểm soát theo eventId"]
~~~

Chỉ hạ CL sau một **quyết định nghiệp vụ rõ ràng**, đánh giá rủi ro stale reads và durability/availability. Thay `LOCAL_QUORUM` bằng `ONE` để biểu đồ lỗi “đẹp” hơn có thể làm sai hợp đồng read-after-write mà người dùng đang phụ thuộc.

### 15.3. Logs và cardinality

Nên log `eventId`, request/trace ID, logical operation, CL, timeout config/profile, elapsed time, exception type, keyspace/table. Không log raw tokens, passwords, dữ liệu thanh toán hoặc toàn bộ payload JSON. `eventId` thường phù hợp cho **logs/traces**, không dùng làm **metric label cho từng event** vì cardinality quá cao.

## 16. Bảng xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
|---|---|---|
| `LOCAL_QUORUM` không hoạt động như mong muốn trên test một node | Keyspace RF=1 hoặc config không đúng topology | Dùng RF>=3 với ít nhất 3 replica nodes để thử quorum behavior |
| Write `Unavailable` khi một node down | CL=ALL hoặc không đủ live replicas cho quorum | Đối chiếu RF/CL, topology và replica health |
| Read `LOCAL_ONE` không thấy event mới | Write chưa hội tụ đến replica vừa đọc | Chọn R/W CL theo read-after-write contract |
| Cross-DC read không thấy write mới | Write `LOCAL_QUORUM` ở DC khác | Đánh giá replication lag, local/global quorum strategy |
| `DriverTimeoutException` nhưng server timeout metric không tăng | Client deadline hết sớm hoặc network/client queue | Đo driver in-flight, tracing, client timeout |
| `WriteTimeoutException` nhưng row tồn tại sau đó | Mutation đã được một số replicas áp dụng | Reconcile theo stable key, không kết luận rollback |
| Gateway `replyTimeout` trước Cassandra completion | Spring reply budget ngắn hơn DB request | Phân bổ deadlines đồng bộ với SLA và thiết kế cancellation/recovery |
| `send()` trả true nhưng row chưa có | Cassandra handler async mặc định | Theo dõi completion/error; cân nhắc `async(false)` khi phù hợp |
| `WriteOptions` không áp vào custom statement | `writeOptions` dành cho entity operation modes | Cấu hình options trên `Statement<?>` hoặc execution profile |
| Thay CL bằng header client không được | Config endpoint không đọc header hoặc sai hợp đồng | Đặt CL server-side, allowlist use cases |
| Retry source gây write amplification | Driver + service + broker retry cùng lúc | Giới hạn retry budget, idempotency, circuit breaker |
| Speculative execution khiến tải tăng | Bật policy và operation idempotent | Kiểm tra max-executions/delay, disable nếu overload |
| LWT trả `applied=false` | Version condition không khớp | Xử lý duplicate/conflicting event, không coi là timeout |
| Read chậm dù CL=ONE | Hot partition/scan/table model xấu | Chỉnh query/partition, paging, cluster health |
| Driver timeout lớn nhưng HTTP vẫn 504 | HTTP reverse proxy deadline thấp hơn | Thiết kế deadline từ caller tới DB |
| JMS redelivery không xảy ra sau write failure | Source đã ack trước async completion | Chọn acknowledgment boundary/durable handoff |
| Cassandra đã ghi nhưng JMS lại redeliver | DB và broker commit không atomic | Stable eventId, idempotent replay |
| Query sai schema/auth và retry mãi | Permanent error | Fail fast, sửa migration/ACL/DTO |
| Một node p99 cao hơn hẳn | Compaction/GC/replica hot | Node diagnostics, data model, load balancing |

## 17. Checklist thiết kế trước production

1. **Replication:** keyspace replication strategy, RF từng DC và số nodes thực tế được ghi rõ.
2. **Write CL:** dựa trên mức xác nhận cần thiết cho event/audit/state, không chỉ tối ưu tốc độ.
3. **Read CL:** dựa trên read-after-write và phạm vi DC, kiểm tra điều kiện overlap.
4. **LWT:** chỉ dùng serial consistency cho conditional operations có invariant rõ.
5. **Timeout budget:** có số đo p99 từ caller đến Cassandra, có thời gian để trả lỗi hoặc retry.
6. **Driver config:** kiểm tra effective profile và per-statement overrides, không phụ thuộc giá trị mặc định suy đoán.
7. **Spring flow:** phân biệt adapter không reply và gateway có reply; hiểu handler async default.
8. **JMS/Kafka boundary:** source ack/offset có thể xảy ra trước hay sau Cassandra completion?
9. **Idempotency:** cùng business `eventId`/full key và payload immutable qua retry/replay.
10. **Retry:** policy của driver, app, broker và DLQ được tính thành một budget; có backoff/jitter.
11. **Backpressure:** giới hạn in-flight requests, reactive concurrency, nguồn buffer và hot partitions.
12. **Error taxonomy:** phân biệt Unavailable, server timeout, driver timeout, LWT applied=false, permanent contract errors.
13. **Monitoring:** CL, request latency p99, client/server timeout counters, retries và message backlog.
14. **Security:** chỉ service tin cậy được chọn CL và execution profile; không log credentials/payload nhạy cảm.
15. **Recovery:** có reconciliation khi timeout outcome chưa rõ và replay không tạo side effect sai.

## 18. Bài thực hành: consistency và timeout trong Spring Integration

**Môi trường:** Java 17+, Spring Integration Cassandra 6+, Spring Data Cassandra reactive tương thích, Apache Cassandra cluster test và `cqlsh`. Các bài kiểm thử quorum/node failure cần **ít nhất ba Cassandra replica nodes thực sự** ở một DC (RF=3); một test container chỉ có một node chỉ dùng được cho exercises về API/CQL/timeout đơn giản, **không chứng minh quorum failover**.

### Bài A — Tạo schema và kiểm tra RF

Trên cluster có ba nodes thuộc DC `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

Trước khi chạy, **xác minh tên datacenter thực tế là `dc1`**, các nodes khỏe và RF=3 có thể đạt. Nếu đang dùng cluster một node, đổi **chỉ trong lab một node** thành RF=1 và không thực hiện so sánh khả năng chịu lỗi 1/3 nodes.

Kiểm chứng bằng `cqlsh`:

~~~sql
DESCRIBE KEYSPACE shop_integration;
CONSISTENCY LOCAL_QUORUM;

INSERT INTO shop_integration.order_event
    (event_id, order_id, event_type, payload_json)
VALUES
    ('evt-6001', 'ORD-6001', 'OrderPaid', '{"source":"lab"}');

SELECT event_id, event_type
FROM shop_integration.order_event
WHERE event_id = 'evt-6001';
~~~

**PASS:** xác nhận CL được chọn, ghi/đọc theo primary key, và schema có RF/topology đúng. `CONSISTENCY` là lệnh của **cqlsh**, không phải câu CQL mà `CqlTemplate.execute(...)` nên gửi.

### Bài B — RF=3, ONE vs LOCAL_QUORUM vs ALL

1. Ghi 100 events bằng CL=ONE, đo latency p50/p95/p99 trên cluster khỏe.
2. Ghi tập events tương ứng với `LOCAL_QUORUM`, đo lại.
3. Ghi với `ALL` trên **test cluster**, đo tác động latency.
4. Dừng **một Cassandra node** bằng test orchestration được quản lý, xác minh hai replicas còn khỏe.
5. Thử `LOCAL_QUORUM` và `ALL`; giải thích vì sao quorum có thể thành công nhưng ALL có thể lỗi.
6. Dừng node thứ hai (chỉ trong lab đã kiểm soát), thử `LOCAL_QUORUM`; phân biệt `UnavailableException` với timeout.
7. Khôi phục cluster, chờ trạng thái bình thường, đối chiếu các node/replica.

**PASS:** giải thích được `Q=2` với RF=3, mô hình chịu lỗi một replica và lý do **ALL** dễ giảm availability. Không kết luận mọi lỗi khi node down nhất thiết là cùng một exception; phụ thuộc thời điểm failure detection/timeout.

### Bài C — Driver config và per-statement override

1. Cấu hình `application.conf` với `LOCAL_QUORUM` và `3 seconds`.
2. Đọc effective driver profile bằng `session.getContext().getConfig()`.
3. Gửi một prepared INSERT dùng `BoundStatement` với `setTimeout(Duration.ofSeconds(2))`.
4. Thử SELECT dùng execution profile `dashboard-read` (`LOCAL_ONE`) và `order-events` (`LOCAL_QUORUM`).
5. Kiểm tra CL và deadline áp dụng **đúng statement/operation**, không chỉ tên bean hoặc file config.
6. Đọc lại values Cassandra và so sánh thời gian `session.execute(...)` trả về.

**PASS:** phân biệt global config, execution profile và per-statement override; không ghép user value vào CQL string.

### Bài D — Spring Data WriteOptions và Spring Integration adapter

1. Tạo entity Java:

~~~java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEvent(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {
}
~~~

2. Tạo bean `WriteOptions` với `consistencyLevel(LOCAL_QUORUM)`, `timeout(Duration.ofSeconds(3))`.
3. Tạo `Cassandra.outboundChannelAdapter(operations, Type.INSERT).writeOptions(options)`.
4. Gửi `Message<OrderEvent>` vào channel; query Cassandra theo `event_id`.
5. Chuyển từ `async(false)` sang `async(true)` để so sánh thời điểm `send()` trả về và lúc write completion.
6. Tắt một replica trên cluster RF=3; quan sát handler error/latency và source handling.

**PASS:** Spring Data mapping và `WriteOptions` hoạt động trên đúng entity operation; hiểu adapter một chiều không tạo reply.

### Bài E — Ba loại failure và outcome chưa rõ

1. Thiết lập một driver timeout ngắn **chỉ trong test** và tạo tình huống latency cao có kiểm soát.
2. Thu `DriverTimeoutException` nếu driver deadline hết trước khi có kết quả.
3. Tạo tình huống coordinator nhận request nhưng chờ replica responses quá hạn để quan sát `ReadTimeoutException`/`WriteTimeoutException` khi môi trường hỗ trợ.
4. Giảm số replicas khả dụng dưới CL và quan sát `UnavailableException` hoặc lỗi tương ứng khi coordinator biết đủ node đã down.
5. Với write timeout, **đọc lại theo `eventId`** sau khi cluster ổn định để chứng minh một lỗi client **không đủ kết luận** row chưa tồn tại.
6. Thiết kế xử lý retry cùng event ID và payload immutable. Không gửi một event ID mới cho mỗi attempt.

**PASS:** báo cáo được class exception, CL, RF, elapsed time, received/required responses nếu có, và trạng thái row sau reconciliation. Không cố ép Cassandra sinh đúng exception trong mọi lần thử bằng cách dùng một cluster một node.

### Bài F — Spring Integration gateway và timeout độc lập

1. Tạo `findEventWithTimeout` ở mục 9, có consumer cho `findEventResults`.
2. Chạy request thành công bằng CL=LOCAL_QUORUM.
3. Đặt Spring gateway reply timeout ngắn hơn driver timeout trên **flow test có cấu hình gateway đúng loại**, rồi kiểm tra caller có thể hết hạn trước Cassandra.
4. So sánh với driver timeout ngắn hơn reply timeout; ghi nhận **exception và elapsed time**.
5. Thử một input không hợp lệ (event ID thiếu, authorization sai), xác nhận validation error không được retry như temporary database timeout.
6. Kiểm tra error channel và request/reply contract, không coi timeout gateway là proof Cassandra chưa xử lý.

**PASS:** hai loại timeout có phạm vi độc lập và được đo trong traces.

### Bài G — JMS/Kafka acknowledgment qua hai kiểu channel

1. Dùng JMS transacted listener hoặc Kafka source test đưa `OrderPaid(evt-6001)` vào `DirectChannel` với Cassandra handler `async(false)`.
2. Cho Cassandra write báo lỗi và **propagate exception**, quan sát rollback/redelivery (JMS) hoặc offset policy (Kafka) theo cấu hình cụ thể.
3. Đổi sang `ExecutorChannel` hoặc Cassandra async handler; kiểm tra nguồn **có thể kết thúc callback trước database completion**.
4. Giả lập lỗi: Cassandra ghi xong rồi JVM crash trước JMS commit/offset commit; broker phát lại cùng `eventId`.
5. Xác minh event key/payload bất biến và không phát sinh side effect nghiệp vụ lặp.
6. Đưa event malformed vào quarantine/DLQ theo chính sách, không retry vô hạn.

**PASS:** trình bày đúng ranh giới ACK/commit và phương án replay bền vững. Không tuyên bố JMS transacted tự giao dịch nguyên tử với Cassandra.

### Bài H — LWT và serial consistency

1. Tạo bảng `order_current_state` ở mục 13.
2. Thêm row ban đầu bằng `INSERT ... IF NOT EXISTS`; đọc `[applied]`.
3. Dùng `UPDATE ... IF version = ?` với regular `LOCAL_QUORUM` và serial `LOCAL_SERIAL`, cập nhật version 2 → 3.
4. Gửi lại cùng update khi version đã 3; kiểm tra `[applied]=false`.
5. Thử timeout và phân biệt “không được applied” với “không biết chắc vì timeout”.
6. Đo độ trễ LWT so với regular INSERT trên cluster test, cân nhắc có thực sự cần dùng LWT cho mọi event không.

**PASS:** hiểu hai consistency settings và xử lý applied=false như business result thay vì transport exception.

### Ma trận kiểm chứng tối thiểu

| Case | Kết quả PASS |
|---|---|
| RF=3, local quorum | Hai local responses là điều kiện đủ khi các replicas khỏe |
| ONE vs LOCAL_ONE | Biết phạm vi local và nguy cơ stale read |
| QUORUM overlap | Giải thích `R+W>RF` đúng phạm vi |
| ALL | Nhận biết availability giảm khi replica mất |
| ANY | Không dùng cho read, không giả định read-after-write |
| Multi-DC | Phân biệt LOCAL_QUORUM và EACH_QUORUM/QUORUM |
| Driver timeout | Xác định `DriverTimeoutException` và tổng request deadline |
| Server timeout | Xác định read/write timeout ở coordinator |
| WriteOptions | Áp cho entity INSERT/UPDATE/DELETE đúng mode |
| Statement options | Dùng CL/timeout trên `Statement<?>` phù hợp |
| Sync/async | Biết lúc nào nguồn có thể ack trước write completion |
| Timeout uncertainty | Cùng `eventId`, reconciliation chứ không tạo ID mới |
| LWT | Đọc `wasApplied()`, phân biệt result và lỗi |
| Load control | Có concurrency cap và retry budget |
| Observability | Đo error type, CL, RF, p99 và source backlog |

**Giới hạn của mock:** test giả `ReactiveCassandraOperations` hoặc `CqlSession` chỉ kiểm tra service gọi đúng API, **không chứng minh** replica ACK, quorum intersection, server/driver timeout, failover, LWT consensus hoặc sự kiện đã được lưu sau timeout. Các hành vi đó cần Cassandra thật/test cluster nhiều nodes; kiểm tra JMS/Kafka ack cần broker phù hợp.

## 19. Câu hỏi tự đánh giá

1. Consistency level và request timeout giải quyết hai vấn đề khác nhau như thế nào?
2. Replication factor RF=3 có bao nhiêu bản sao cho một partition trong local DC của ví dụ?
3. Với RF=3, `LOCAL_QUORUM` đợi bao nhiêu responses?
4. Với RF=5, quorum là bao nhiêu? Nếu hai replicas không phản hồi thì sao?
5. Vì sao Cassandra có thể gửi write đến tất cả replicas dù CL=ONE?
6. Điều kiện `R + W > RF` giúp suy luận điều gì? Có tự bảo đảm linearizable trong mọi trường hợp không?
7. Việc chọn read/write `LOCAL_QUORUM` ở hai datacenters khác nhau có bảo đảm thấy ngay dữ liệu mới không?
8. `ONE` và `LOCAL_ONE` khác nhau thế nào trong multi-DC?
9. `QUORUM` khác `LOCAL_QUORUM` ở tập replicas được xét như thế nào?
10. `EACH_QUORUM` phù hợp hơn với write hay read, và có đánh đổi gì khi một DC lỗi?
11. Vì sao CL=ALL có thể tăng write latency và giảm availability?
12. `ANY` có dùng cho SELECT không? Một write ANY thành công có bảo đảm read ONE thấy ngay không?
13. `SERIAL` và `LOCAL_SERIAL` dùng trong hoạt động Cassandra nào?
14. Một LWT có cần regular consistency level bên cạnh serial consistency level không?
15. `DriverTimeoutException` khác `WriteTimeoutException` và `UnavailableException` như thế nào?
16. Với `WriteTimeoutException received=1, required=2`, ta biết chắc điều gì và không biết điều gì?
17. Driver 4.x `basic.request.timeout` có bao gồm retries/speculative executions không?
18. Một `Statement.setTimeout(Duration)` có thay đổi Cassandra server `write_request_timeout` không?
19. Tăng `MessageChannel.sendTimeout` có giúp một CQL request đã hết driver timeout không?
20. Vì sao Reactor `timeout(...)` không rollback một remote Cassandra mutation đã xảy ra?
21. Execution profile có lợi gì so với việc thay đổi singleton template config ở từng request?
22. `WriteOptions.consistencyLevel/timeout` dùng cho Spring Integration Cassandra mode nào?
23. Khi dùng `statementFunction(...)` trả `SimpleStatement`, cần đặt CL/timeout ở đâu?
24. `CassandraMessageHandler` mặc định sync hay async, và điều đó ảnh hưởng tới `send()` ra sao?
25. Vì sao Spring Integration outbound adapter một chiều không trả `[applied]` giống gateway?
26. Nếu JMS broker đã commit rồi Cassandra async write lỗi, liệu có thể rollback message nguồn không?
27. Khi Cassandra đã ghi nhưng JVM crash trước JMS commit, lần redelivery cần giữ những field nào?
28. Vì sao `eventId` mới ở mỗi retry là nguy hiểm?
29. Đánh dấu `setIdempotent(true)` có tự động thêm database unique constraint hoặc idempotency inbox không?
30. Vì sao counter increment thường không an toàn khi retry mù quáng?
31. Khi nào một `WriteTimeoutException` cần reconciliation hơn là thông báo “ghi thất bại hoàn toàn”?
32. Đổi CL từ `LOCAL_QUORUM` xuống `ONE` để giảm lỗi có thể phá vỡ giả định nghiệp vụ nào?
33. Speculative execution có thể tăng traffic ra sao; vì sao không bật cho non-idempotent mutation?
34. Tại sao tăng Cassandra request timeout không giải quyết được hot partition?
35. Kể tên năm metrics giúp phân biệt cluster overload, stale reads và driver timeout.
36. Vì sao mock Cassandra không thể chứng minh quorum behavior và failover?

## 20. Tài liệu tham khảo chính thức

- [Apache Cassandra — Dynamo Architecture: Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo): replication, CL, quorum, `R+W>RF` và timestamp conflict resolution.
- [Apache Cassandra — Managing and Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): client request timeouts, unavailable, failures, read/write latency, table/node metrics.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): replication strategy, partition/primary keys, keyspace layout.
- [Apache Cassandra — Lightweight Transactions](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): conditional operations, applied result và Cassandra LWT semantics.
- [Apache Cassandra Java Driver 4.19 — Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): `basic.request.timeout`, `basic.request.consistency`, execution profiles và programmatic config.
- [Apache Cassandra Java Driver 4.19 — Upgrade Notes](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/): driver request timeout bao gồm retries/speculative executions.
- [Apache Cassandra Java Driver 4.19 — Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): retry policy, error-specific actions và cảnh báo consistency downgrading.
- [Apache Cassandra Java Driver 4.19 — Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): idempotency, extra attempts, timeout, request amplification.
- [Apache Cassandra Java Driver API — DriverTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/DriverTimeoutException.html): client-side request timeout.
- [Apache Cassandra Java Driver API — UnavailableException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/UnavailableException.html): CL required/alive và server response.
- [Apache Cassandra Java Driver API — WriteTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html): coordinator-side write timeout và WriteType.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): per-operation consistency, timeout, serial consistency, TTL và idempotency.
- [Spring Data Cassandra API — WriteOptionsBuilder](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.WriteOptionsBuilder.html): `consistencyLevel`, `timeout`, `executionProfile` và builder API.
- [Spring Data Cassandra Reference — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraOperations`, lazy publisher và reactive error handling.
- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): Cassandra outbound channel adapter/gateway, `CassandraMessageHandler`, async default.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): `writeOptions`, `statementFunction`, `query`/`parameter`.

**Ghi nhớ:** **Consistency level** quyết định **số replica responses cần thiết**, còn **timeout** quyết định **thời gian một tầng chấp nhận chờ kết quả**. `LOCAL_QUORUM` với RF=3 cần hai ACK trong local DC, nhưng không tạo transaction nguyên tử với JMS/Kafka hoặc đảm bảo dữ liệu tại DC khác đã hội tụ. **Timeout không chứng minh Cassandra chưa ghi.** Trong Spring Integration, phải chọn CL/timeout ở đúng tầng (driver statement, Spring Data `WriteOptions`, gateway/channel), hiểu `CassandraMessageHandler` mặc định async, giữ business `eventId` ổn định, giới hạn retry/backpressure, và kiểm thử failure/acknowledgment với cluster thực trước khi đưa vào production.







