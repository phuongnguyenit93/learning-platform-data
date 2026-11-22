# Hint backlog, replica thiếu dữ liệu hoặc đọc kết quả cũ

> **Chương:** Xử lý sự cố  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — hiểu kiến trúc phân tán và mô hình wide-column của Apache Cassandra; partition key, bảng theo truy vấn, consistency đọc/ghi, CQL, replication, compaction, repair, lỗi phân tán và kết nối từ ứng dụng Java.

Một node Cassandra ngừng hoạt động 45 phút rồi trở lại với trạng thái `UN`. Dịch vụ Java đọc bằng `LOCAL_ONE` đôi lúc trả `status="PENDING"`, dù người dùng đã cập nhật thành `status="APPROVED"` và yêu cầu ghi trước đó trả thành công. Trên một số node, thư mục hints lớn và JMX báo delivery failures. Liệu đây có phải **mất dữ liệu**, lỗi ứng dụng, hay chỉ là replica chưa đồng bộ?

Đừng vội restart, xóa hints hoặc chạy repair toàn cụm. Muốn giải quyết đúng phải tách **bốn sự thật**:

1. **Client đã được xác nhận điều gì?** Write CL, RF/DC, response thành công hay timeout, serial consistency nếu LWT.
2. **Replica nào thực sự nhận mutation?** Một coordinator lưu hint cho replica thiếu kết nối không đồng nghĩa replica đó đã có dữ liệu.
3. **Việc bắt kịp đang ở trạng thái nào?** Hint tạo mới, xếp hàng trên node giữ hint, đang replay, thất bại, hết cửa sổ tạo hint hoặc cần anti-entropy repair.
4. **Read đã hỏi ai và với consistency nào?** Một SELECT tại `ONE/LOCAL_ONE` có thể thấy giá trị cũ trong lúc `LOCAL_QUORUM` vẫn đọc được giá trị mới; cache ứng dụng, timestamp và TTL cũng có thể tạo triệu chứng tương tự.

Bài này hướng dẫn khoanh vùng **hint backlog – replica divergence – stale reads**, lập bằng chứng từ Cassandra và Java Driver, lựa chọn giữa chờ hinted handoff, đọc đối chứng, anti-entropy repair và xử lý trạng thái dữ liệu. Ví dụ dùng **Cassandra 4.1/5.0, Java Driver 4.x**, giả định cluster lab nhiều node. Tên lệnh, cấu hình, JMX/exporter có khác biệt theo phiên bản; mọi thao tác can thiệp chỉ được thực hiện khi có runbook và quyền phù hợp.

> **Quy tắc an toàn:** đây là bài học chẩn đoán. Không dừng node, ngắt mạng, xóa hints, đổi CL, rút `gc_grace_seconds` hay thực hiện repair/compaction trên production chỉ để làm bài. Các số, UUID, IP và sự cố ở phần lab là **dữ liệu minh họa**, không phải bằng chứng quan sát môi trường thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích coordinator, natural replicas, write CL, read CL, hinted handoff và anti-entropy repair trong cùng luồng ghi/đọc.
2. Phân biệt **hint đang chờ giao** với **mutation đã được replica áp dụng**, và **write ACK** với **tất cả replicas đã nhận dữ liệu**.
3. Hiểu `max_hint_window` giới hạn **khoảng thời gian tạo hint cho một replica Down**, không phải lời hứa mọi hints đã replay sau đúng thời hạn ấy.
4. Phân biệt `ONE/LOCAL_ONE` stale read, quorum read repair, cross-DC lag và outcome không xác định sau write timeout.
5. Thu bằng chứng theo node **giữ hints** và **node nhận hints**, không chỉ theo node vừa khởi động lại.
6. Xác định hint creation, hints not stored, replay success/failure/timeout, delay, disk pressure, network và membership status.
7. Dùng `nodetool status`, `statushandoff`, `getmaxhintwindow`, `netstats`, logs và JMX một cách có giới hạn.
8. Giải thích vì sao repair quét token ranges khác với read repair vốn chỉ chạm dữ liệu tham gia truy vấn.
9. Nhận diện nguy cơ **tombstone resurrection** khi replica nghỉ quá lâu và thiếu repair trước thời hạn `gc_grace_seconds`.
10. Viết thí nghiệm RF3 có kiểm soát, ledger operation/outcome, Java Driver read probes và kế hoạch xác minh hội tụ dữ liệu.
11. Đề xuất một playbook xử lý an toàn, có thứ tự ưu tiên và điều kiện dừng/rollback.
12. Kết luận sự cố với bằng chứng đủ mạnh, nêu điều chưa biết và tránh báo “hết backlog = mọi dữ liệu chính xác”.

## 2. Ba cơ chế dễ bị đánh đồng

### 2.1. Hinted handoff: chuyển giúp những mutation bị lỡ

Với keyspace RF3 trong `dc1` có ba natural replicas N1, N2, N3, một client ghi ở `LOCAL_QUORUM`:

~~~mermaid
sequenceDiagram
    participant App as Java client
    participant C as Coordinator
    participant N1 as Replica N1
    participant N2 as Replica N2 (DOWN)
    participant N3 as Replica N3
    App->>C: UPDATE k=v2 (LOCAL_QUORUM)
    C->>N1: Mutation v2
    C-xN2: Mutation v2 (không tới)
    C->>N3: Mutation v2
    N1-->>C: ACK
    N3-->>C: ACK
    C-->>App: SUCCESS (2/3)
    Note over C: Có thể lưu hint cho N2 trên disk holder
    Note over N2: N2 vẫn giữ v1
    N2-->>C: Trở lại ring/được nhận diện Up
    C->>N2: Replay hints
    N2-->>C: Giao thành công/ACK
~~~

Coordinator có thể ghi hint **trên local filesystem của node giữ hints** để sau này chuyển cho target replica. Nơi lưu hint **không nhất thiết** là node N2 bị Down. Một mutation có thể được hint từ nhiều coordinators khác nhau; vì thế cần kiểm tra nhiều hint holders trong phạm vi cluster.

Kết luận:

- Client nhận **SUCCESS tại LOCAL_QUORUM** khi đủ số natural replica ACK; không đòi tất cả replicas ACK.
- Hint tạo ra **không biến N2 thành replica đã nhất quán** ngay lúc ghi.
- Hinted handoff là **best effort**: có thể có mutations bị lỡ do thời gian Down vượt window, hint không được tạo/lưu, disk/network, target identity thay đổi hoặc lỗi delivery.
- Hints replay giữ **write timestamp của mutation gốc** để tránh bản ghi cũ thay thế một bản mới hơn chỉ vì được giao muộn.
- Hints có thể mất nhiều thời gian để replay khi backlog lớn; `nodetool status` thấy N2 `UN` **không chứng minh** N2 đã nhận hết hints.

### 2.2. Read repair: kiểm tra sự khác biệt khi đọc

Khi coordinator thực hiện một read với CL cần nhiều replica responses (ví dụ `LOCAL_QUORUM`), nó có thể so full data và digests. Nếu các replicas tham gia phản hồi khác nhau, Cassandra reconcile theo cell timestamps/tombstones, rồi thực hiện **read repair** theo table option.

Trong Cassandra 4.x/5.x, `read_repair = 'BLOCKING'` là mặc định ở table level; `'NONE'` cho phép reconcile kết quả đọc nhưng không ghi sửa các replica tham gia theo cùng cách. Hai chính sách đánh đổi các thuộc tính *monotonic quorum reads* và *partition-level write atomicity* (xem tài liệu chính thức).

**Giới hạn quan trọng:**

- `ONE/LOCAL_ONE` thường chỉ cần một replica response, **không có digest comparison bắt buộc** để phát hiện mismatch như quorum read.
- Một read repair chỉ bao trùm **replicas tham gia và dữ liệu được đọc**, không sửa mọi partition của cả table.
- Read repair **không thay thế** anti-entropy repair; một `SELECT` thành công không chứng minh các keys khác trên N2 đã hội tụ.
- Một quorum read có thể lấy giá trị mới nhất **trong số replicas trả lời**; nó không cam kết thấy một write chỉ tồn tại ở replica không tham gia, đặc biệt khi write chưa được ACK theo CL cần thiết.

### 2.3. Anti-entropy repair: so sánh dữ liệu giữa replicas của token ranges

`nodetool repair` chủ động so sánh và đồng bộ dữ liệu cho token ranges/partitions có cùng natural replicas, thông qua Merkle trees và streaming differences. Nó xử lý những mutation **không còn hoặc chưa từng có hints**, bao gồm trường hợp node nghỉ vượt hint window.

Repair có chi phí disk, CPU, network và có thể gây compaction/streaming backlog. Cassandra không tự động chạy toàn bộ repair theo định kỳ chỉ vì hints chưa xong; đội vận hành cần lịch/scheduler và runbook rõ ràng.

| Cơ chế | Trigger | Phạm vi | Bảo đảm/giới hạn |
|---|---|---|---|
| **Hinted handoff** | Write gửi tới replica unavailable/timed out, trong policy/window | Những mutations có hint đã được giữ | Best effort, không bảo đảm đủ mọi write |
| **Read repair** | Đọc với đủ replicas và phát hiện mismatch | Replicas và partitions/rows trong read | Không sửa toàn dataset; policy tùy table |
| **Anti-entropy repair** | Operator/scheduler chạy repair | Token ranges, keyspace/tables được chọn | Kênh đồng bộ toàn diện có kiểm soát; cần đủ replicas và hoàn tất |

Một node trở lại ring là **điều kiện để phục hồi**, không phải bằng chứng **đã phục hồi xong**.

## 3. Tại sao đọc có thể trả kết quả cũ?

### 3.1. Mô hình v1/v2 với ba replicas

Giả sử một partition có giá trị `v1` trên cả N1, N2, N3. N2 Down, ghi `v2` ở `LOCAL_QUORUM` và nhận SUCCESS:

| Sau mutation | N1 | N2 | N3 |
|---|---|---|---|
| Giá trị được replica biết | `v2` | `v1` (Down) | `v2` |
| Xác nhận write tại CL? | ACK | Không | ACK |
| Trạng thái hint | Có thể được giữ bởi coordinator cho N2 | Chưa áp dụng | Có thể ở N1/N3 hoặc coordinator khác |

Sau khi N2 Up nhưng **chưa nhận hết hints**:

- Read `LOCAL_ONE` nếu được phục vụ từ N2 **có thể trả `v1`**.
- Read `LOCAL_ONE` nếu được phục vụ từ N1/N3 **có thể trả `v2`**.
- Read `LOCAL_QUORUM`, khi không có write mới cạnh tranh và đủ replicas phản hồi, giao nhau với cặp ACK của successful quorum write, nên có thể reconcile được `v2` theo timestamps/repair semantics.
- Nếu read timeout/unavailable, không có kết quả: **lỗi trả lời** khác với **kết quả stale**.

**Đây là khả năng, không phải kết quả deterministic của mọi lượt gọi.** Cùng một ứng dụng, load balancing/coordinator/replica selection và read repair có thể khiến stale read khó tái hiện sau vài truy vấn. Việc cắm `cqlsh` vào N2 không tự chứng minh mọi read được phục vụ từ local replica N2; cần xem traces/replica contacts.

### 3.2. Công thức R + W > RF có giả định

Trong mô hình đơn giản với RF=3 trong cùng DC:

~~~text
LOCAL_QUORUM write: W = 2
LOCAL_QUORUM read:  R = 2
2 + 2 > 3  -> các tập replica phản hồi phải giao nhau
~~~

Hệ quả có điều kiện: với **một write đã xác nhận thành công**, không có concurrent writes, không có write timestamps/tombstones bất thường, schema/replication nhất quán và read CL thực sự đáp ứng, quorum read có thể quan sát mutation đó.

Không sử dụng công thức này như bằng chứng mọi request là **linearizable** hoặc mọi replica đã hội tụ. W/R chỉ đếm replica responses, **không tự bảo đảm** về thời gian thực cho writes thất bại/không được xác nhận, LWT/Paxos, thao tác multi-partition, timeout, TTL, cluster topology thay đổi hoặc replication giữa DC.

### 3.3. Các nguồn stale read khác hint backlog

| Nguồn | Dấu hiệu | Cần phân biệt |
|---|---|---|
| Replica vừa lên, chưa replay hints | Chỉ một replica/nhóm token lệch; hints waiting | Replication lag thật |
| W=ONE, R=ONE | Không bắt buộc quorum giao nhau | Behavior theo consistency contract |
| Write timeout/partial ACK | Mutation có thể đã được một vài replicas áp dụng | UNKNOWN outcome, không xác nhận “write đã xong” |
| Cross-DC `LOCAL_QUORUM` | DC gần có update, DC khác chưa nhận | Local quorum **không** bảo đảm immediate cross-DC visibility |
| Application/HTTP cache | Cassandra read đúng nhưng API trả cũ | Cache TTL/invalidation/routing |
| Timestamp conflict / clock skew | Giá trị “mới gửi” thua theo timestamp | Last-write-wins, client `USING TIMESTAMP` |
| TTL và tombstones | Vừa có vừa không theo tuổi cell/read | Expiration, GC grace, repair và read scope |
| LWT outcome misunderstood | CAS false bị coi success hoặc timeout bị coi false | `wasApplied()`/serial consistency |
| Materialized view/secondary read model | Bảng view cập nhật khác bảng gốc | Denormalization/write pipeline hoặc MV behavior |
| Sai partition key/bucket | Query đọc nhầm row/day/tenant | Prepared CQL, bind order và clustering constraints |

Một user bảo “đã sửa trạng thái” chỉ chứng minh ý định phía client. Hãy đối chiếu **write response, CL, query key, version/timestamp và code path đọc** trước khi quy kết replica thiếu dữ liệu.

## 4. Khoanh vùng thời điểm, phạm vi và giả thuyết

### 4.1. Timeline mẫu (giả định)

~~~text
09:00Z  RF3/dc1: N1 N2 N3 = UN, value=v1
09:05Z  N2 Down do maintenance
09:07Z  App ghi v2 tại LOCAL_QUORUM, response SUCCESS
09:08Z  Holder(s) có dấu hiệu Hints_created tăng cho N2
09:45Z  N2 trở lại UN
09:46Z  App dùng LOCAL_ONE đôi lúc đọc v1
09:49Z  Hint delivery failures/timeouts tăng, disk holder bận
10:10Z  HintsSucceeded tăng nhưng lag của N2 chưa chứng minh bằng 0
10:20Z  Một mẫu LOCAL_QUORUM đọc v2
~~~

**Lập timeline UTC bằng nguồn thực**, không lấy một câu log “node Up” để khẳng định tất cả hints đã replay. Phân biệt `T_down`, `T_write_ack`, `T_up`, `T_delivery_start/end`, `T_read_stale` và `T_repair_complete`. Mỗi thời điểm có thể có clock skew, log aggregation lag và metric bucket khác nhau.

### 4.2. Bản đồ blast radius

| Chiều | Phân nhóm nên đối chiếu | Câu hỏi |
|---|---|---|
| API/client | Mobile/web, service version, cache on/off | Stale từ Cassandra hay cache? |
| Data model | Keyspace/table, partition/key, TTL, liveness | Một tập keys hay toàn bảng? |
| Query shape | SELECT theo PK, range/latest-N, CL, paging | Đọc cùng hàng và cùng CL chưa? |
| Datacenter | dc1/dc2, local DC driver routing, RF từng DC | Chỉ local DC lag hay xuyên DC? |
| Topology | Node Up/Down/Joining/replacing, host ID | Target còn là node cũ không? |
| Hints holder | Coordinator từng ghi và các node giữ hint | Hints đang nằm ở đâu? |
| Hints target | Replica thiếu dữ liệu | Có nhận được replay không? |
| Storage | Disk, GC, network, hints directory, pending writes | Delivery bị nghẽn hay thiếu mutation? |
| Client outcome | SUCCESS, TIMEOUT_UNKNOWN, CAS_NOT_APPLIED | Có thật sự “đã ghi thành công” không? |

**Đừng chỉ xem một holder:** client traffic có thể chọn nhiều coordinators và hints được tạo rải khắp những node đã làm coordinator. Một node N2 Up không nói gì về disk/hints queue trên N1, N3 hoặc các coordinators khác.

### 4.3. Một giả thuyết phải có phép bác bỏ

~~~text
H1: N2 stale vì hinted handoff chưa replay đủ.
Predicts:
  - N2 từng Down trong thời gian writes v2;
  - Hints_created hoặc disk files trên một hay nhiều holders tăng;
  - HintsSucceeded tăng sau N2 Up nhưng pending/failed deliveries còn;
  - stale reads liên quan N2/partition thuộc replica set của N2.
Falsifiers:
  - không có write đến N2 khi Down, không có replica divergence;
  - truy vấn Cassandra đúng v2 ở CL mục tiêu nhưng cache trả v1;
  - mutation v2 bị discard do timestamp hoặc đã expired theo TTL.
Low-risk checks:
  - snapshot metrics hints / node topology / query fingerprint;
  - read đối chứng bằng CL được phê duyệt và trace sampling thấp.
~~~

Nếu lỗi xuất hiện **trước khi N2 Down**, hoặc chỉ ở một bản service khi tất cả CQL reads đều trả đúng, H1 ít được hỗ trợ. Không dùng `truncatehints` hay restart N2 như “phép thử” để kiểm tra H1.

## 5. Hiểu vòng đời của một hint và nguyên nhân backlog

### 5.1. Hint tồn tại ở đâu?

Theo Apache Cassandra, hints được lưu dưới dạng những **files trên filesystem của coordinator/hint holder**, thường là `$CASSANDRA_HOME/data/hints` hoặc thư mục do `hints_directory` cấu hình. Một hint mang thông tin target replica và mutation (gồm write timestamp gốc), sau đó được gửi theo từng segment khi target đã có thể nhận.

~~~mermaid
flowchart LR
    A["Mutation đến coordinator"] --> B{"Replica liên lạc được?"}
    B -->|Có| C["Replica nhận/ACK mutation"]
    B -->|Không| D{"Hint policy + window cho phép?"}
    D -->|Có| E["Hint holder ghi file/buffer"]
    D -->|Không| X["Không tạo hint mới"]
    E --> F["Target quay lại Up"]
    F --> G["Delivery queue / throttle / network"]
    G --> H{"Target áp dụng segment?"}
    H -->|Có| I["ACK, cleanup segment theo cơ chế"]
    H -->|Lỗi/time out| J["Retry/báo failure theo cơ chế"]
    X --> K["Cần anti-entropy repair để đồng bộ"]
    J --> G
~~~

Một hint trên disk **không có nghĩa write đã tồn tại trên target**. Đồng thời, file nhỏ đi sau delivery **không chứng minh mọi table đã đồng bộ**, vì một số mutation chưa từng được hint.

### 5.2. Max hint window không phải thời hạn replay

Một cấu hình quen thuộc trong Cassandra 4.x/5.x là `max_hint_window` có default **3 giờ** (tên cũ: `max_hint_window_in_ms` tùy release). Nó giới hạn khoảng thời gian sau khi node bị coi là Down mà **hints mới** được tạo cho target ấy.

Phân biệt:

| Thời điểm | Ý nghĩa |
|---|---|
| Node Down được nhận biết | Bắt đầu cửa sổ tạo hints tùy thông tin failure |
| Trong `max_hint_window` | Các coordinators có thể tạo hints cho mutations bị lỡ |
| Node vẫn Down quá window | **Không tiếp tục tạo hints mới** theo policy; có thể tăng `Hints_not_stored` |
| Node Up trở lại | Hints **đã lưu** vẫn có thể được replay; không phải cứ qua window là tất cả bị xóa ngay |
| Hints replay thành công | Chỉ những mutations đã được lưu/giao được áp dụng; không bảo đảm toàn bộ dữ liệu khác |

**Không suy rằng “Down 4 giờ → mọi hints bị xóa sạch” hoặc “Down 2 giờ → chắc chắn đầy đủ hints”.** Hãy đọc cấu hình thực, trạng thái disabled DC, failed storage, peer identity và metrics per-node.

### 5.3. Những cấu hình ảnh hưởng backlog

| Cấu hình (Cassandra 4.x/5.x) | Tác dụng | Ngộ nhận/rủi ro |
|---|---|---|
| `hinted_handoff_enabled` | Bật/tắt cơ chế hinting | Bật không đồng nghĩa mọi write đều được hint |
| `hinted_handoff_disabled_datacenters` | Loại trừ DC khỏi handoff | DC bị disable có thể tạo replication lag lâu |
| `max_hint_window` | Giới hạn **new hint creation** sau khi target Down | Không phải replay timeout |
| `hinted_handoff_throttle` | Giới hạn băng thông delivery mỗi thread, có scaling theo cluster | Quá thấp làm backlog lâu; quá cao tranh IO/network |
| `max_hints_delivery_threads` | Độ song song giao hints | Tăng bừa có thể overload target |
| `hints_directory` | Nơi lưu hints | Disk đầy/mount lỗi gây mất khả năng lưu hint |
| `hints_flush_period` | Chu kỳ flush buffer hints ra file, không nhất thiết fsync | Không dùng giá trị này làm guarantee durability |
| `max_hints_file_size` | Giới hạn file segment | Không phải tổng quota backlog |
| `max_hints_size_per_host` (tùy bản) | Quota dung lượng hints cho từng target | Khi vượt quota có thể không giữ thêm hints |

Tài liệu Cassandra 5.0 nêu default thường gặp: `max_hint_window=3h`, `hinted_handoff_throttle=1024KiB`, `max_hints_delivery_threads=2`, `max_hints_file_size=128MiB`. **Đây không phải cấu hình áp dụng bắt buộc cho mọi release hay cluster**, đặc biệt Cassandra 4.0 còn dùng một số tên với hậu tố đơn vị `_in_ms`/`_in_kb`. Xem `cassandra.yaml` và `nodetool help` trên **đúng bản được vận hành**.

### 5.4. Backlog tăng bởi năm nhóm nguyên nhân

1. **Target vẫn Down hoặc flapping:** từng Up vài phút rồi rớt, delivery bị hủy/khởi động lại.
2. **Tạo hints nhanh hơn giao:** tốc độ mutations tới unavailable replicas cao, throttle thấp, network hoặc target disk chậm.
3. **Thư mục hints gặp vấn đề:** gần hết dung lượng, inode thiếu, permission/IO error, volume mount/FS readonly, quota policy.
4. **Đường mạng/inter-DC:** packet loss, RTT, firewall, TLS nếu áp dụng internode encryption, congested NIC hoặc network partition.
5. **Tài nguyên nền:** target GC/compaction/streaming/repair nặng, nhiều holders cùng phát replay, hints delivery threads/throttles không phù hợp.

Vì thế phải thu **hai phía**: hint holders đang lưu/phát, và target đang nhận/áp dụng. Nếu target `UN` nhưng disk 100% bận do compaction, tăng throttle ngay có thể làm **recovery chậm hơn**.

### 5.5. Phân biệt hint backlog với các backlog khác

| Dấu hiệu | Chỉ ra điều gì | Không được suy |
|---|---|---|
| Hints directory lớn trên N1 | Có disk bytes liên quan hints tại N1 | Mọi file thuộc N2; tất cả đều chưa giao |
| HintsSucceeded tăng trên N1 | Có hint delivery thành công | Backlog đã bằng 0 |
| HintsFailed/HintsTimedOut tăng | Delivery gặp lỗi | Mọi hint đã mất; cần xóa files |
| `nodetool netstats` có streaming | Repair/bootstrap/streaming có thể đang chạy | Đây là chính xác số hints chờ |
| `PendingCompactions` cao | Compaction work tồn | Đây là nguyên nhân duy nhất của stale read |
| Node target `UN` | Node được gossip xem Up/Normal từ node hỏi | Node đã có mọi mutations |
| Read tại `LOCAL_QUORUM` thấy v2 | Các replicas tham gia read có thể reconcile v2 | Mọi replica/partition đã đồng bộ |

Một số JMX metrics trong Cassandra mang tên `Hints_created-<PeerIP>` nhưng vẫn có semantics và reset khác nhau theo release. **Không cộng bừa toàn bộ counters thành số hints currently pending**: theo dõi file bytes, delivery rates, độ trễ và thực tế có mutation chưa được giao.

## 6. Thu bằng chứng hint backlog đúng lớp

### 6.1. Snapshot ít tác động theo thời gian và node

Thu một bộ snapshot ở nhiều nodes/holders, kèm UTC timestamp, hostname, DC, Cassandra version, sampling interval:

~~~bash
# Các lệnh CHỦ YẾU ĐỌC; chạy theo quyền & runbook.
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
~~~

`nodetool status` là **gossip view của node được hỏi**, có thể khác nhau giữa N1/N3 trong network partition. `tpstats` cho request/response and thread-pool backlog nhưng không là một hint backlog counter toàn cục. `netstats` phản ánh streaming (repair/bootstrap), không thay thế metrics hints delivery.

Khi cần xác minh cài đặt hinted handoff trên Cassandra 4.x/5.x:

~~~bash
nodetool statushandoff
nodetool getmaxhintwindow
nodetool handoffwindow
~~~

**Chạy `nodetool help <command>` trước** vì tính khả dụng/cú pháp tùy phiên bản. Những lệnh trên chủ yếu đọc trạng thái/cửa sổ; ngược lại `disablehandoff`, `pausehandoff`, `sethintedhandoffthrottlekb`, `setmaxhintwindow` và `truncatehints` **thay đổi trạng thái**.

### 6.2. Hints directory ở node giữ hint

Trên Linux lab, sau khi biết `hints_directory` thực và được phép xem:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
df -h /var/lib/cassandra/hints
df -i /var/lib/cassandra/hints
du -sh /var/lib/cassandra/hints
ls -lah /var/lib/cassandra/hints
~~~

Đường dẫn `/var/lib/cassandra/hints` chỉ là **ví dụ thường gặp**; package/container khác có thể dùng đường khác. Hints files chứa mutations, có thể nhạy cảm. Không đọc nội dung/tải lên kênh public, không tự xóa/chmod/copy hay chặn directory trong lúc replay. Thống kê `du/ls` cũng có overhead khi có nhiều files, cần giới hạn tần suất.

**Cần ghi:** bytes ở `t0/t1/t2`, tốc độ tăng/giảm, disk free/inodes, file modified times, danh sách holders và các chỉ số delivery cùng thời điểm. Disk bytes tăng có thể chỉ vì hints creation đang tăng; bytes giảm có thể do segment cleanup, rotation hoặc file policy, nên cần kết hợp logs và counters.

### 6.3. Các metric cần tìm trong JMX/exporter

Tài liệu Cassandra 4.x/5.x mô tả:

| Metric/nhóm | Loại ý nghĩa | Cách đọc khi điều tra |
|---|---|---|
| `Storage.TotalHints` | Counter hints đã viết từ lúc start | Tăng cho thấy workload hinting; có reset sau restart |
| `Storage.TotalHintsInProgress` | Theo dõi hints đang thử gửi (theo tài liệu) | Không coi là total backlog bytes/age |
| `HintedHandOffManager.Hints_created-<PeerIP>` | Hints được tạo/lưu cho target cụ thể | Theo peer và sự thay đổi; không tự suy exact queue length |
| `HintedHandOffManager.Hints_not_stored-<PeerIP>` | Hints không lưu do target Down quá window | Cảnh báo **có thể thiếu mutations không còn hint** |
| `HintsService.HintsSucceeded` | Meter delivery successes | Throughput delivery, không chứng minh toàn cluster hội tụ |
| `HintsService.HintsFailed` | Meter failed deliveries | Có lỗi cần đối chiếu target/network/IO |
| `HintsService.HintsTimedOut` | Meter delivery timeout | Có dấu hiệu target/links quá chậm |
| `HintsService.Hint_delays` | Histogram độ trễ giao hints, thường milliseconds | Đuôi thời gian phục hồi |
| `HintsService.Hint_delays-<PeerIP>` | Histogram theo target peer | Xác định target có lag đặc biệt |

Tên và JMX ObjectNames có thể bị exporter đổi nhãn/đơn vị; ví dụ tài liệu gốc mô tả nhóm `org.apache.cassandra.metrics.HintsService`/`HintedHandOffManager`. **Kiểm tra JMX/exporter map thật**, đừng tự bịa một Prometheus metric để kết luận “backlog=0”.

### 6.4. Đo backlog bằng tốc độ và tuổi, không chỉ một counter

Một panel điều tra hữu ích hiển thị:

~~~text
By node holder and target peer:
  hints_written_per_second
  hints_delivery_succeeded_per_second
  hints_delivery_failed_or_timeout_per_second
  hints_not_stored_per_second
  hints_directory_bytes
  oldest_pending_hint_age (nếu có reliable source)
  hint_delivery_delay_p95/p99

Alongside:
  target_Up_Down_timeline
  client_write_rate_and_CL
  target_disk_io / GC / internode_network
  repair_and_compaction_load
~~~

Không phải exporter nào cũng có `oldest_pending_hint_age`; phải ghi **NOT_AVAILABLE** thay vì suy nó từ `TotalHints`. Số hints được tạo thành công và số deliveries là các dòng sự kiện khác semantics; không lấy `created - succeeded` làm exact backlog nếu không có định nghĩa reset/duplicated peer/segment accounting.

### 6.5. Logs theo cửa sổ downtime/rejoin

Đối chiếu trên **từng holder và target**:

~~~text
T_down  ± vài phút: endpoint marked DOWN, hint creation
T_up    ± vài phút: endpoint marked UP, attempt to dispatch hints
After T_up: hint replay failures/timeouts, disk/GC/network spikes
Repair window: anti-entropy repair start, progress, success/error
~~~

Trong Cassandra 4.x/5.x, logs có thể ở `logs/system.log`, `logs/debug.log`, journald hoặc container logs tùy đóng gói. Tìm theo timestamp UTC/offset và tên endpoint/host ID; log message text **không phải API ổn định** giữa các version. Không bật DEBUG toàn cụm ngay khi disk đầy hoặc network đang bão hòa.

### 6.6. Evidence ledger chuẩn

| ID | UTC/source | Đối tượng | Quan sát | Điều chưa chứng minh |
|---|---|---|---|---|
| EV-H01 | N1, 09:48Z | Hints holder | HintsSucceeded tăng | N2 đã nhận toàn bộ dữ liệu |
| EV-H02 | N3, 09:48Z | Hints holder | HintsTimedOut tăng, network RTT cao | Mutation nào bị thiếu |
| EV-H03 | N2, 09:49Z | Target | `UN`, disk busy 95% (ví dụ) | N2 đã hội tụ |
| EV-H04 | App v27, 09:50Z | Client | SELECT LOCAL_ONE thấy v1 | Vì sao chọn replica nào |
| EV-H05 | App v27, 09:51Z | Client | LOCAL_QUORUM thấy v2 | Mọi replica đều có v2 |

Mọi quan sát giả định trong bảng cần được thay bằng **liên kết metric/log/trace có thật** khi áp dụng. Nhớ kiểm tra clock offset và metric bucket để không lấy events sau này làm nguyên nhân trước đó.

## 7. Playbook khoanh vùng sự cố trong 30 phút đầu

### 7.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["API báo stale/replica lag"] --> B{"Write ACK thật sự thành công?"}
    B -->|Unknown timeout| C["Đưa vào UNKNOWN và đối chiếu operation ledger"]
    B -->|Có| D{"Read đã bỏ app cache chưa?"}
    D -->|Chưa| E["Bypass cache / so read trực tiếp an toàn"]
    D -->|Có| F{"Read CL và DC phù hợp?"}
    F -->|ONE/LOCAL_ONE| G["Có thể thấy replica chậm, kiểm tra quorum control"]
    F -->|Quorum| H["Xem timestamp, concurrent writes, read repair"]
    G --> I{"Có target Down/rejoin?"}
    H --> I
    I -->|Có| J["Tìm hint holders, backlog, window, delivery failures"]
    I -->|Không| K["Kiểm tra schema, timestamps, TTL, LWT, đa DC"]
    J --> L{"Hints đủ và đang giao được?"}
    L -->|Có| M["Theo dõi hội tụ có deadline"]
    L -->|Không rõ| N["Đánh giá anti-entropy repair theo runbook"]
    M --> O["Data verification và integrity gate"]
    N --> O
~~~

### 7.2. Phút 0–5: xác định ảnh hưởng và lưu bằng chứng

Ghi một incident statement:

~~~text
INC-CASS-... (minh họa)
First known bad: 2026-11-21T09:46Z (bucket 1 phút)
Affected: state API, service v27, dc1, SELECT by PK
Observed: stale v1 in 4 of 120 sampled reads at LOCAL_ONE
Write outcome: v2 ACK at LOCAL_QUORUM 09:07Z
Node history: N2 Down 09:05Z, Up 09:45Z
Hints evidence: not yet collected
Unknown: exact replica serving stale reads; all holders and their backlog
Risk: user-visible stale data / possible missed mutations
~~~

Kiểm tra lỗi **ghi bị mất, unavailable tăng, disk full, tombstone resurrection** và yêu cầu phản ứng khẩn cấp theo severity. Chưa đủ bằng chứng thì ghi `UNKNOWN` thay vì báo “database corrupt”.

### 7.3. Phút 5–15: tách lớp read và write

1. Xác minh client thực sự ghi **đúng primary key và keyspace**, đã nhận `SUCCESS` hay timeout, mức CL thực (không chỉ giá trị mặc định trong config).
2. So read path giữa cache và Cassandra: cùng query fingerprint, bind values được **ẩn danh có kiểm soát**, ngày/bucket và CL.
3. Chia affected/healthy cohorts theo service version, DC, node/replica (nếu truy được), thời điểm và TTL age.
4. Đọc `nodetool status` từ nhiều nodes, ghi N2 Down/Up và trạng thái Join/Leaving/Moving.
5. Thu hint metrics/disk trên **các holders**, không chỉ N2.
6. Kiểm tra `read_repair` table option, version, `gc_grace_seconds`, `max_hint_window` và thay đổi gần nhất.
7. Đặt giới hạn số read probes để **không tạo thêm tải** trên cluster đang yếu.

### 7.4. Phút 15–30: quyết định giữa chờ giao hints và repair

| Phát hiện | Hướng điều tra tiếp | Lưu ý hành động |
|---|---|---|
| Target Up, HintsSucceeded tăng, no failed, disk giảm | Theo dõi delay/lag, sample consistency reads | Có thể chỉ cần để handoff hoàn tất |
| Target flapping, delivery timeout cao | Host GC/IO/network, internode connectivity, target ID | Ổn định target trước khi tăng throughput |
| Hints_not_stored tăng hoặc downtime vượt window | Đánh giá anti-entropy repair đủ phạm vi | Không thể chỉ chờ hints bù những mutations không có |
| Holder disk gần hết | Capacity incident, bảo vệ hints/commitlog/data | Không xóa hints để lấy chỗ |
| Node Up, hints đã drain nhưng read stale còn | Xem CL/cache/timestamp/TTL, missing hints, repair history | Drain không chứng minh đồng bộ |
| Quorum read cũng thấy giá trị cũ | Kiểm tra write outcome, timestamp winner, concurrent mutations | Không suy v2 đã được xác nhận khi thiếu write ledger |
| Read LOCAL_ONE v1, quorum v2 | Replica mismatch hoặc read routing | Cần xác định target và theo dõi hội tụ |

**Không gọi `repair` như phản xạ mỗi khi thấy stale read.** Nó tiêu thụ tài nguyên; nếu node đang Down liên tục, repair có thể thất bại. Đánh giá target health, tải nền và khả năng phục hồi theo policy.

### 7.5. Chỉ một mitigation mỗi lần

Nếu được phép và user impact quá cao, cân nhắc thay đổi **routing/read policy** theo nghiệp vụ; nhưng **đừng âm thầm đổi `LOCAL_ONE` thành `LOCAL_QUORUM` hoặc ngược lại** để dashboard xanh. Tăng CL có thể tăng latency/timeout khi replicas chậm, giảm CL có thể làm tăng stale reads. Ghi rõ invariants, RF, availability và impact trước hành động.

Mọi mitigation nên có:

~~~text
Action/approval/time window:
Prediction:
Stop condition:
Rollback:
Before metrics:
After metrics:
Data correctness check:
Residual risks:
~~~

## 8. Kiểm chứng dữ liệu qua Java Driver 4.x

### 8.1. Không thử “đọc một node” bằng cách chọn contact point

Java Driver chọn coordinator theo query plan/local DC/token-aware routing. Coordinator có thể forward read tới replica khác; **contact point không phải lệnh ép đọc dữ liệu local từ replica ấy**.

Để xác định đường thực thi:

- Thu `ExecutionInfo.getCoordinator()` cho request thành công.
- Tracing có lấy mẫu và được phê duyệt để xác định endpoints/đường đọc.
- Xem load-balancing policy, token-aware routing, routing key và local DC.
- Nếu muốn test replica-specific trong lab, dùng fault-control/traffic routing được thiết kế cùng traces; không làm vậy trên production chỉ để “ép ra stale”.

### 8.2. Truy vấn đối chứng có partition key đầy đủ

Ví dụ table:

~~~sql
CREATE TABLE IF NOT EXISTS incident_lab.state_by_account (
    account_id uuid PRIMARY KEY,
    state text,
    revision bigint,
    updated_at timestamp
) WITH read_repair = 'BLOCKING';
~~~

Đối với lab RF3 ở `dc1`, khi có bảo đảm write `LOCAL_QUORUM` thành công cho revision=2, thử SELECT cùng key qua CL khác:

~~~sql
-- Trong cqlsh lab; CONSISTENCY là lệnh cqlsh, không phải CQL DML.
CONSISTENCY LOCAL_ONE;
SELECT state, revision, updated_at
FROM incident_lab.state_by_account
WHERE account_id = 11111111-1111-4111-8111-111111111111;

CONSISTENCY LOCAL_QUORUM;
SELECT state, revision, updated_at
FROM incident_lab.state_by_account
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

**Lưu ý:** Một `LOCAL_ONE` read có thể tình cờ thấy revision=2 dù N2 stale; một `LOCAL_QUORUM` read có thể kích hoạt read repair trên replicas tham gia và làm thay đổi hiện trạng quan sát. Nếu cần bằng chứng nguyên trạng, thu logs/metrics và thiết kế thứ tự thử theo lab trước khi tạo nhiều read probes.

### 8.3. Java code phân biệt consistency và coordinator

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

record Probe(ConsistencyLevel cl, Long revision, String state,
             String coordinator, Instant capturedUtc, String error) {}

static Probe readState(
    CqlSession session, PreparedStatement select, UUID accountId,
    ConsistencyLevel consistency, boolean traceSample) {

    Instant captured = Instant.now();
    BoundStatement bs = select.bind(accountId)
        .setConsistencyLevel(consistency)
        .setTimeout(Duration.ofSeconds(2))
        .setTracing(traceSample)
        .setIdempotent(true);

    try {
        ResultSet rs = session.execute(bs);
        Row row = rs.one();
        ExecutionInfo ei = rs.getExecutionInfo();
        String coordinator = String.valueOf(ei.getCoordinator());
        if (row == null) {
            return new Probe(consistency, null, null, coordinator,
                             captured, null);
        }
        Long revision = row.isNull("revision")
            ? null : row.getLong("revision");
        return new Probe(consistency, revision,
            row.getString("state"), coordinator, captured, null);
    } catch (RuntimeException e) {
        return new Probe(consistency, null, null, "UNKNOWN",
                         captured, e.getClass().getName());
    }
}

// Trong service/lab đã có CqlSession session và UUID accountId:
PreparedStatement select = session.prepare(
    "SELECT state, revision FROM incident_lab.state_by_account " +
    "WHERE account_id=?");

Probe one = readState(session, select, accountId,
    DefaultConsistencyLevel.LOCAL_ONE, false);
Probe quorum = readState(session, select, accountId,
    DefaultConsistencyLevel.LOCAL_QUORUM, false);
~~~

Đoạn code là **mẫu phương thức/statement trong class có sẵn `session` và `accountId`**, không phải một Java file standalone. Không log raw account/tenant IDs ở production. Exception được đưa vào field `error` để lưu probe; caller phải phân loại timeout/unavailable, không coi `revision=null` do lỗi đọc là “dữ liệu đã bị xóa”.

**Chú ý:** `ResultSet.one()` chỉ đọc một row; query theo PK đơn có tối đa một row. Với range/paged reads phải ghi thêm page consumption và per-page execution info. Tracing chỉ bật rất ít mẫu vì tạo thêm workload trong `system_traces`.

### 8.4. Expected revision phải đi cùng operation ledger

Không đủ nếu chỉ so `state` khi có concurrent writes:

~~~text
Write W1 revision=1, timestamp=T1, ACK
Write W2 revision=2, timestamp=T2, ACK
Write W3 revision=3, timestamp=T3, UNKNOWN_TIMEOUT
Read sees revision=3
~~~

Đọc revision=3 **không nhất thiết sai**, ngay cả khi client W3 nhận timeout: mutation có thể đã commit một phần. Nếu một write `USING TIMESTAMP` với timestamp cũ hơn T2 được gửi sau W2, nó có thể **không thắng** theo last-write-wins dù request báo SUCCESS. Revision là **dữ liệu nghiệp vụ**; trừ khi dùng LWT hoặc cơ chế đồng bộ thích hợp, Cassandra không tự bảo đảm revisions tăng tuần tự trên concurrent writers.

Ledger nên có:

- Operation ID, key đã pseudonymize, command type, intended state/revision.
- Write CL và serial CL nếu LWT, response SUCCESS/CAS_NOT_APPLIED/UNKNOWN.
- Timestamp effective / TTL deadline nếu app tự quản lý.
- Read CL, UTC time, coordinator/trace ID nếu có, observed value.
- Concurrent writes và reconciliation outcome.

### 8.5. Phân biệt lỗi read với read stale

| Kết quả Java | Diễn giải hợp lệ |
|---|---|
| `Row != null`, revision=1 | Giá trị revision 1 được trả trong lần đọc tại CL và thời điểm đã ghi |
| `Row != null`, revision=2 | Giá trị revision 2 được trả, không chứng minh mọi replica đã nhận |
| `Row == null`, request SUCCESS | Không có row live trong query tại consistency/đường đọc đó; có thể do TTL/delete hoặc chưa replicate |
| `ReadTimeoutException` | Không đủ phản hồi theo CL trong thời gian; **không có kết quả** |
| `UnavailableException` | Coordinator báo không có đủ replicas sống cho CL |
| `DriverTimeoutException` | Driver không nhận response trong deadline; không suy giá trị nào ở storage |

Đừng viết test `assertEquals(v1, readState(LOCAL_ONE))` như kỳ vọng deterministic sau khi N2 lên: Driver có thể chọn replica mới đã được repair, khiến test flaky dù cơ chế stale read là có thật.

## 9. Khi nào chờ hints, khi nào cần anti-entropy repair?

### 9.1. Ma trận quyết định vận hành

| Trạng thái | Kết luận tạm thời | Quyết định kế tiếp |
|---|---|---|
| Target Down, trong hint window, holders khỏe | Hints có thể đang được tạo/lưu | Khôi phục target an toàn; thu backlog/space |
| Target Up, HintsSucceeded tăng đều, delay giảm | Hinted handoff đang tiến triển | Theo dõi đến khi đạt integrity gate |
| Target Up nhưng hints failed/timed out tăng nhanh | Delivery bị nghẽn | Ưu tiên network, disk, GC, throttling/target health |
| Target Down vượt `max_hint_window` | Có khả năng **không có hint** cho các writes muộn | Lập kế hoạch anti-entropy repair khi target ổn |
| `Hints_not_stored` tăng | Một số mutations không được hint theo window | Không chỉ chờ backlog drain; cần repair |
| Target được thay bằng node mới/identity khác | Old hints có thể không có target phù hợp | Kiểm tra replacement/streaming/repair runbook |
| Mọi hints đã giao nhưng stale samples còn | Có thể có missing hints, timestamp/TTL/cache hoặc mismatch khác | Mở rộng evidence, xét repair/semantics |
| Replica nghỉ gần/vượt `gc_grace_seconds` | **Nguy cơ dữ liệu xóa sống lại** | Incident data-integrity, không repair mù |

**Không có quy tắc “hints directory nhỏ thì không cần repair”.** Hints là best effort, còn lịch anti-entropy repair cần được duy trì độc lập. Việc không thấy backlog hiện tại cũng không chứng minh trong downtime trước đó mọi mutation đã có hint.

### 9.2. Bản chất incremental và full repair

Theo tài liệu Cassandra 4.x/5.x:

- **Incremental repair** tập trung vào dữ liệu chưa được đánh dấu repaired từ những lần incremental trước; thường ít tốn hơn khi chạy đều, nhưng **không tự phát hiện mọi lỗi ở phần đã marked repaired**.
- **Full repair** so các dữ liệu trong phạm vi được chọn, bao gồm phần đã repaired; có chi phí cao hơn, nhưng quan trọng cho một số loại inconsistency mà incremental không phát hiện.
- **Primary-range repair** với `-pr` giúp tránh trùng lặp công việc nếu cần bao phủ toàn cluster bằng cách chạy trên **tất cả nodes và DCs được yêu cầu**. Một lần chạy từ một node không có nghĩa toàn cluster đã repair.
- Repair có thể ảnh hưởng Paxos/LWT state/streaming theo version và flag; phải xem lệnh thực cùng topology.

Ví dụ **kế hoạch lệnh**, không phải hướng dẫn thực thi ngay trên production:

~~~bash
# Chỉ sau khi change approval, window và health preflight đạt.
# Mỗi lệnh tác động lên dữ liệu và tài nguyên cluster.

# Incremental repair primary ranges cho một table:
nodetool repair -pr incident_lab state_by_account

# Full repair primary ranges cho một table:
nodetool repair --full -pr incident_lab state_by_account
~~~

**Cần điều phối vòng qua các nodes/DCs** theo repair runbook để bao phủ token ranges; không chạy đồng thời tất cả nodes vô hạn, không dùng một lần lệnh trên N2 rồi bảo đã xử lý toàn bộ consistency. Cassandra 5.x có thêm tùy chọn `--preview` để ước lượng các ranges/streaming mà không stream, nhưng **preview vẫn tạo Merkle trees và tốn CPU/IO**, phải giới hạn và kiểm chứng bản đang chạy.

### 9.3. Preflight trước repair

Trả lời trước khi thực thi:

1. **Mục tiêu:** keyspace/table/token range nào lệch? Tất cả replicas cần thiết có Up và ổn định không?
2. **Lịch sử:** lần full/incremental repair gần nhất, kết quả, scope, unrepaired/repaired SSTables, tombstone/grace risk?
3. **Tài nguyên:** disk free/headroom, network saturation, CPU/GC, compaction/streaming queue, maintenance window?
4. **Consistency:** RF/DC/CL đúng; có ongoing bootstrap/decommission/replace, schema disagreement hoặc upgrade hay không?
5. **Tác động:** SLA chịu được read/write slowdown và additional IO bao lâu; ai quyết định dừng?
6. **Lựa chọn:** repair đúng table/ranges trước hay toàn cluster, incremental vs full, throttling concurrency thế nào?
7. **Quan sát:** trước/sau dùng cùng metrics; lưu job IDs, errors, bytes streamed và thời gian hoàn thành.
8. **Rollback/recovery:** nếu repair làm quá tải hoặc nghi tombstone resurrection, dừng theo runbook và xác minh source of truth/backup.

Repair có thể cải thiện replica divergence nhưng **không tự đảo ngược mọi sai lầm ứng dụng** như write với timestamp cũ, CAS false bị hiểu nhầm hoặc nhầm partition key.

### 9.4. Không dùng lệnh phá hủy để “giải phóng backlog”

| Thao tác | Tại sao không dùng tùy tiện |
|---|---|
| `nodetool truncatehints` | Xóa hints chưa giao; mất đường best-effort chuyển mutations bị lỡ |
| Xóa thủ công files trong `hints_directory` | Phá dữ liệu hints, rủi ro filesystem/forensics |
| `nodetool disablehandoff` | Thay chính sách storing/delivery, có thể làm nhiều writes không có hints |
| `nodetool pausehandoff` | Dừng delivery trong khi backlog đang tăng |
| Tăng `hinted_handoff_throttle` vô hạn | Có thể bão hòa target disk/network, làm read p99 tệ hơn |
| Restart tất cả holders | Thay trạng thái pool/gossip, mất volatile log evidence, có thể chậm replay |
| Major compaction | Tốn IO, không thay thế anti-entropy repair |
| Đổi `gc_grace_seconds=0` | Có thể làm nguy cơ zombie data nghiêm trọng hơn |

Trong trường hợp đặc biệt, lệnh thay đổi có thể nằm trong runbook **đã thẩm định và được phê duyệt**; bài học không cấm công cụ, chỉ không coi chúng là bước chẩn đoán vô hại.

### 9.5. Xác minh đã đồng bộ: ba cấp độ khác nhau

| Cấp | Điều chứng minh | Điều chưa chứng minh |
|---|---|---|
| **Operationally Up** | Node/process Up/Normal theo gossip view | Dữ liệu của node đã đầy đủ |
| **Hint delivery completed** | Các holders được biết đã xử lý hints trong phạm vi theo dõi | Không có mutation nào nằm ngoài hint window/failed to store |
| **Replica data reconciliation** | Repair thành công trong phạm vi + kiểm chứng dữ liệu mẫu | Không mặc nhiên bảo đảm mọi business invariant/caches |

Một integrity gate tốt kết hợp **successful repair scope, errors đã được giải thích, convergence của dữ liệu có version, liveness/TTL, no unresolved writes, và application SLO phục hồi ở traffic đại diện**. Không có một `nodetool status` đơn lẻ nào thay thế được các điều kiện này.

## 10. TTL, tombstones và nguy cơ dữ liệu đã xóa xuất hiện lại

### 10.1. Hints cũng cần truyền thông tin xóa

Cassandra không xóa vật lý ngay khi DELETE hoặc TTL expire: nó dùng **tombstone** để các replicas khác không làm dữ liệu cũ trở lại. Một replica Down có thể bỏ lỡ **delete mutation** chứ không chỉ bỏ lỡ UPDATE mới. Nếu delete marker không đến replica ấy trước khi những bản khác purge tombstones, replica cũ có thể góp phần làm dữ liệu “zombie” xuất hiện lại.

~~~text
Ban đầu:          N1=A      N2=A       N3=A
N2 Down.
DELETE được ACK:  N1=DEL    N2=A       N3=DEL
Trước purge:      Tombstones trên N1/N3 có thể thắng A theo timestamp
Sau grace + compaction purge ở N1/N3:
                  N1=none   N2=A       N3=none
N2 quay lại, repair/read có thể khiến A trở lại.
~~~

Đây là **sơ đồ logic**, không biểu diễn chi tiết từng SSTable, row liveness marker hay điều kiện purge. Tombstones chỉ được purge khi **hết grace và compaction có điều kiện an toàn**; không phải đúng giây grace hết thì dữ liệu vật lý biến mất.

### 10.2. Hai cửa sổ thời gian khác mục đích

| Tham số | Mục đích | Ví dụ default thường gặp |
|---|---|---|
| `max_hint_window` | Khoảng thời gian **tiếp tục tạo hints mới** cho replica Down | Khoảng 3 giờ |
| `gc_grace_seconds` | Khoảng giữ deletion markers trước khi eligible purge trong compaction | 864.000 giây (10 ngày) |

**Không nhầm hai đại lượng.** Một node Down 4 giờ (vượt hint window mặc định) vẫn có thể còn trong gc grace, nên anti-entropy repair có thể khôi phục mutations/tombstones chưa giao. Một node Down vượt gc grace có nguy cơ data resurrection nếu tombstones đã purge và việc repair không đủ; case đó cần **incident dữ liệu**, không chỉ tăng hints throttle.

TTL còn chịu quy tắc **per-cell**, khác `event_time` ứng dụng. Một UPDATE với TTL mới có thể thay expiry deadline; retry cùng write có TTL sau timeout có thể kéo dài retention. Nếu ứng dụng đọc “v1” nhưng v2 đã hết TTL trong lúc N2 Up, stale read diagnosis phải xét thời điểm hết hạn thay vì mặc định hints đang lỗi.

### 10.3. Khi đã vượt gc grace

Trước khi repair/đưa node vào phục vụ đầy đủ:

- Đánh giá downtime thực, table-level `gc_grace_seconds`, repair history và compaction đã purge tombstones hay chưa.
- Nếu nghi dữ liệu đã xóa xuất hiện lại, **cô lập/điều phối replica theo runbook** để tránh khuếch tán; không tự chạy repair có thể làm stale data lan sang replicas khác.
- Xác định source of truth/backup/snapshot/operation log để đối chiếu trạng thái xóa đúng.
- Cần kế hoạch recovery/rebuild/restore phù hợp phiên bản, topology, DDL, SSTable/streaming safety và quyền vận hành.
- Ghi rõ data integrity scope, keys bị ảnh hưởng và bằng chứng về deletes/TTL, không chỉ đo API latency.

**Không phải cứ vượt grace là chắc chắn zombie xuất hiện**: cần missed deletion và tombstone đã purge. Nhưng khi rủi ro tồn tại, “hints đã hết” không phải điều kiện phục hồi đủ.

### 10.4. Chỉ số bổ trợ về tombstones

Trên đúng table:

~~~bash
nodetool tablestats incident_lab.state_by_account
nodetool tablehistograms incident_lab state_by_account
nodetool compactionstats
~~~

Tương ứng JMX/exporter: `TombstoneScannedHistogram`, `SSTablesPerReadHistogram`, partition-size histograms, compaction backlog và disk. Chúng giúp đánh giá read amplification/safety nhưng **không trực tiếp đếm mutations đã bị lỡ ở N2**. Không dùng một SELECT để khẳng định tombstones tồn tại trên mọi replica.

## 11. Multi-DC, RF, LOCAL_QUORUM và tính nhất quán

### 11.1. Local quorum là local, không phải global

Giả sử NetworkTopologyStrategy dùng:

~~~sql
CREATE KEYSPACE incident_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Đây là **DDL minh họa**, cần topology đủ nodes đúng DCs để thực hiện. Khi service ở dc1 ghi `LOCAL_QUORUM`, nó chờ 2/3 natural replicas **trong dc1**; các replicas dc2 có thể chưa bắt kịp tại thời điểm ACK. Một application ở dc2 đọc `LOCAL_ONE` hoặc `LOCAL_QUORUM` ngay sau đó có thể thấy giá trị cũ nếu cross-DC write chưa đến. Hints trong/giữa DCs còn chịu chính sách `hinted_handoff_disabled_datacenters`.

**Không suy từ write SUCCESS tại dc1 rằng mọi replica dc2 đã có mutation**, cũng không suy một read `LOCAL_QUORUM` tại dc2 chắc chắn thấy write mới vừa ACK ở dc1.

### 11.2. Đếm quorum theo từng DC

| RF / scope | Read/Write CL | Số replica đáp ứng | Điều kiện |
|---|---|---:|---|
| RF3 trong dc1 | LOCAL_ONE | 1 replica dc1 | Có thể thấy replica cũ |
| RF3 trong dc1 | LOCAL_QUORUM | 2 replicas dc1 | Hai quorum local giao nhau nếu write thành công |
| RF3+RF3 qua dc1/dc2 | LOCAL_QUORUM | 2 replicas trong DC local của coordinator/request | Không bảo đảm immediate visibility ở DC kia |
| RF3+RF3 | EACH_QUORUM (writes hỗ trợ) | Quorum ở mỗi DC | Availability/latency khác, cần thiết kế rõ |
| RF3+RF3 | QUORUM (global) | Majority tổng natural replicas | Không đồng nghĩa chỉ local DC |

Không sử dụng bảng này để tự đặt `EACH_QUORUM` cho ứng dụng production; mức consistency xuất phát từ invariants, latency budget và failure tolerance. Với transient replication hoặc RF đặc biệt, quy tắc cần tài liệu tương ứng, không chỉ ví dụ RF3.

### 11.3. Những khác biệt cần kiểm tra ở Java Driver

- `withLocalDatacenter("dc1")` ảnh hưởng load balancing/routing và phải khớp topology.
- Truy vấn có thể lấy CL mặc định từ execution profile; kiểm tra CL **thực thi**, không chỉ tài liệu application.
- Retry/speculative execution có thể phát thêm CQL attempts, tăng tải trên coordinators; không tự hạ CL trong retry policy.
- Driver `ConsistencyDowngradingRetryPolicy` có thể phá assumptions về visibility/availability khi lỗi/DC failover; không bật chỉ để che stale reads.

Khi một DC bị network-isolated, **phân biệt unavailable, timeout và stale**. Một request không thể vừa “trả giá trị cũ thành công” vừa “không có response”: ghi tách những outcomes này.

### 11.4. Những sai lệch sau topology change

Node Joining/Leaving/Moving hoặc được **replace** có thể thay token ownership và identity. Old hints được giữ cho target trước đó không phải cơ chế thay thế bootstrap/streaming/repair của node mới.

Khi chẩn đoán cần lưu:

~~~text
cluster name / partitioner / token ranges
keyspace NetworkTopologyStrategy and RF per DC
node host IDs, addresses, DC/rack, Up/Normal vs Joining/Leaving
replacement/bootstrap/decommission timeline
schema agreement and table options
hint holder/target peer IDs where available
repair/streaming status
~~~

Không xóa old hints trước khi xác minh target identity và runbook. Có thể tồn tại artifacts không còn target hợp lệ mà cách xử lý phụ thuộc release/tool; không xử lý bằng lệnh tay chỉ vì tên node không còn trong ring.

## 12. Sizing backlog và các nút thắt khi replay

### 12.1. Ước lượng giúp quyết định, không thay metric thật

Một mô hình sơ bộ:

\[
\text{hint bytes/s}
\approx
\text{affected writes/s}
\times \text{serialized mutation bytes/write}
\times \text{missed replica copies}.
\]

Hãy dùng mô hình để lập ngân sách disk/network **trước khi replay**, không dùng nó như phép đếm chính xác. Hints được nén/segment/batch, có overhead serialization và policy skipped/failed hints; không nhất thiết mỗi business request chỉ gửi một mutation hay mọi coordinator chỉ giữ một bản hint.

Ví dụ **số giả định**:

~~~text
Affected mutations: 1,000 writes/s
Mean serialized mutation: khoảng 2 KiB
Missed replicas: 1
Estimated hint logical creation: khoảng 2,000 KiB/s
~~~

Nếu delivery throughput thực thấp hơn creation khi target vẫn Down/flapping, backlog tăng. Khi target Up liên tục, directory bytes có thể giảm dần nhưng chỉ nhìn disk size không phân biệt data đã giao hay skipped/failed to store.

### 12.2. Vì sao tăng throttle không luôn giúp?

Giả sử hint holders có CPU/network headroom nhưng target N2 đang compaction/GC:

- Delivery đẩy nhiều mutations hơn → target memtable/commitlog/disk IO tăng.
- Read requests của người dùng cạnh tranh tài nguyên với replay.
- Target timeout nhiều hơn → delivery success rate có thể **giảm** dù configured throttle tăng.
- Các holders phát cùng lúc có thể bão hòa target NIC/CPU/disk.
- Một đợt replay lớn có thể kéo theo flush và compaction sau đó, khiến p99 tiếp tục cao dù backlog đang giảm.

Khi được phép điều chỉnh throughput, phải dựa trên **bottleneck thực** (throttle vs network/disk), chọn mục tiêu và stop condition. Không tăng cả `max_hints_delivery_threads` và throttle cùng lúc rồi không thể biết biến nào gây tác động.

### 12.3. Dashboard để xem hiệu quả phục hồi

| Cửa sổ | Quan sát | Kỳ vọng nếu đang tiến triển |
|---|---|---|
| Trước target Up | Hints_created, directory bytes, not-stored | Có baseline creation và giới hạn |
| Ngay sau Up | HintsSucceeded/Failed/TimedOut, target CPU/IO | Delivery bắt đầu, failures không kéo dài |
| Đang replay | Directory bytes, Hint_delays p95/p99, network/throttle | Delay giảm theo thời gian, target không overload |
| Sau drain | Read probes, app errors, repair policy | Không còn stale trong phạm vi đã kiểm tra |
| Sau anti-entropy repair | Job success/range coverage, integrity checks | Replica reconciliation trong phạm vi |

**Không lấy p99 hints delivery làm end-user p99.** Delivery delay đo thời gian giao mutation; HTTP/CQL latency đo request. Cần cùng timeline và cơ chế nguyên nhân để kết nối.

### 12.4. Cẩn trọng với metrics type và reset

| Loại | Ví dụ | Bẫy |
|---|---|---|
| Counter | TotalHints, Hints_not_stored | Reset khi node restart; đừng tính delta âm là “xóa backlog” |
| Meter | HintsSucceeded/Failed/TimedOut | Rate trượt theo interval, khác total pending |
| Histogram | Hint_delays | Percentiles phản ánh các hints đã có sample, không nhất thiết cả queue |
| Gauge/file size | hints_directory_bytes, disk free | Size biến động do flush/cleanup/rotation |
| Event | Target Down/Up, delivery error log | Log sampling/clock skew có thể làm thiếu events |

Không cộng p99 của hai holders rồi báo p99 cluster; phải tổng hợp histogram/buckets có cùng nghĩa và đủ sample. Đặc biệt, nếu N2 vừa restart làm exporters reset, biểu đồ không có datapoint hoặc counter về 0 **không** chứng minh issue đã hết.

### 12.5. Một recovery budget được viết trước

~~~text
Maximum user-visible stale-read rate at required CL: theo SLO
Target recoverable hint age: theo retention/repair policy
Maximum added disk pressure: theo disk headroom
Target end-to-end recovery window: theo maintenance objectives
Failed hints: 0 sustained hoặc mọi failures có kế hoạch
Repair coverage: keyspace/tables/ranges/DCs theo runbook
Outstanding UNKNOWN writes: được reconcile hoặc có owner
~~~

Nếu data correctness là yêu cầu cứng, không coi “p99 đã giảm” hoặc “không còn hint file” là exit criterion độc lập. Lưu các điều kiện theo app/business invariant và xác minh bằng bằng chứng.

## 13. Lab RF3: cố ý tạo replica lag trong môi trường cô lập

### 13.1. Điều kiện bắt buộc

Lab phải có:

- **Ba Cassandra nodes** trong cùng datacenter thật tên `dc1`, Cassandra 4.1+ hoặc 5.0, cluster riêng chỉ dùng để học.
- Network và volumes không chứa dữ liệu production; quyền stop/start **một node test**, runbook khôi phục và giới hạn thời gian.
- Keyspace RF3 theo NetworkTopologyStrategy, schema agreement trước khi chạy.
- Một host/app chạy `cqlsh`/Java Driver từ vị trí phù hợp; có JMX/nodetool access và đồng hồ UTC gần đồng bộ.
- Một bảng đơn giản theo PK, không TTL, không LWT cho thí nghiệm cơ bản; phân biệt test TTL ở phần khác.
- **Không** chạy các lệnh mô phỏng lỗi trên shared staging/production hoặc môi trường có dữ liệu thật.

Nếu chỉ có một Cassandra node/RF1, bạn có thể luyện phần quan sát hint/config/CQL nhưng **không** kiểm thử khả năng ghi quorum khi một replica Down.

### 13.2. Chuẩn bị CQL

Chỉ trên lab, sau khi xác nhận DC:

~~~sql
CREATE KEYSPACE IF NOT EXISTS incident_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS incident_lab.state_by_account (
    account_id uuid PRIMARY KEY,
    state text,
    revision bigint,
    updated_at timestamp
) WITH read_repair = 'BLOCKING';
~~~

`IF NOT EXISTS` **không tự chỉnh** keyspace/table đã tồn tại và khác schema. Trước khi bắt đầu, kiểm tra đúng RF/DC/table options trong `DESCRIBE KEYSPACE incident_lab` / `DESCRIBE TABLE ...` của `cqlsh`.

Ghi baseline:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO incident_lab.state_by_account
  (account_id, state, revision, updated_at)
VALUES
  (11111111-1111-4111-8111-111111111111,
   'PENDING', 1, '2026-11-21T09:00:00Z');

SELECT state, revision, updated_at
FROM incident_lab.state_by_account
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

`updated_at` là cột dữ liệu để đối chiếu nghiệp vụ; Cassandra write timestamp thực dùng cho conflict resolution **khác** với cột này. Không mặc nhiên coi sửa `updated_at` đồng nghĩa write thắng khi có concurrent writers.

### 13.3. Kịch bản từng pha

**P0 — Preflight.** Cả ba node `UN`, schema agreement, CL=LOCAL_QUORUM. Thu `nodetool status` từ ít nhất hai nodes, hint metrics per holder, disk free, client p99 baseline.

**P1 — Dừng N2, chỉ trên lab.** Dừng container/process theo runbook lab. Chờ **N1/N3 thực sự nhận biết N2 Down**; nếu chưa, lỗi write timeout giai đoạn đầu có thể xảy ra và phải ghi riêng.

**P2 — Ghi v2 trong downtime.** Từ client kết nối còn hoạt động tới N1/N3, dùng:

~~~sql
CONSISTENCY LOCAL_QUORUM;
UPDATE incident_lab.state_by_account
SET state = 'APPROVED',
    revision = 2,
    updated_at = '2026-11-21T09:07:00Z'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

Nếu response SUCCESS ở `LOCAL_QUORUM`, lưu UTC và ID của operation. Nếu timeout, **không biến nó thành successful quorum write**; ghi UNKNOWN và reconcile riêng.

**P3 — Snapshot hints trên holders.** Thu `TotalHints`, `Hints_created-<PeerIP>`, hints directory bytes, `Hints_not_stored`, disk/GC, trạng thái N2 Down. Không cần đọc nội dung file hints hay bật debug toàn cụm.

**P4 — Khởi động lại N2.** Chờ node đạt `UN`, quan sát HintsSucceeded/Failed/TimedOut/Hint_delays từ N1/N3 và target N2 CPU/IO/network. Không restart các holders hoặc xóa hints.

**P5 — Đọc đối chứng.** Dùng Java code mục 8 hoặc `cqlsh`:

- `LOCAL_ONE` **có thể** đọc v1 hoặc v2 tùy replica/độ trễ giao hints; không assert v1 bắt buộc.
- `LOCAL_QUORUM` sau successful LQ write và không có writes cạnh tranh phải lấy được v2 khi request thành công theo assumptions.
- Query với `BLOCKING` read repair có thể **tự làm giảm mismatch**; vì thế lấy metrics/log trước probes.
- Thu coordinator/trace ID có lấy mẫu; không đồng nhất coordinator với replica.

**P6 — Xác minh phục hồi.** Đợi hint delivery ổn, quan sát các holders, kiểm tra data/version trên sample keys và repair policy. Không coi một successful SELECT hoặc directory size giảm là đủ để tuyên bố cluster hội tụ.

### 13.4. Phiếu thực nghiệm

| Mốc | UTC | N2 state | Holder disk bytes | HintsSucceeded rate | Failed/Timeout rate | LQ read revision | ONE read revision |
|---|---|---|---:|---:|---:|---|---|
| P0 | _điền_ | UN | _điền_ | _điền_ | _điền_ | 1 | 1 hoặc tương đương |
| P2 | _điền_ | DN | _điền_ | _điền_ | _điền_ | 2 nếu write ACK | Nondeterministic |
| P4 | _điền_ | UN | _điền_ | _điền_ | _điền_ | 2 nếu assumptions giữ | 1 hoặc 2 |
| P6 | _điền_ | UN | _điền_ | _điền_ | _điền_ | 2 nếu không update mới | 2 nếu replicas đã hội tụ |

**Không điền kết quả giả**. Nếu `LOCAL_ONE` luôn thấy v2 ngay sau Up, bài test vẫn có giá trị về hint creation/replay và điều kiện consistency; điều đó không bác bỏ khả năng stale read trên môi trường khác.

### 13.5. Thí nghiệm mở rộng: node nghỉ vượt hint window

Đây là thí nghiệm có thể mất nhiều thời gian và tăng nguy cơ vận hành. Chỉ tiến hành trong **lab cô lập**, chọn cửa sổ phù hợp và **không** thay `gc_grace_seconds` để ép kết quả.

1. Ghi v1 trên RF3.
2. Cho N2 Down quá cửa sổ tạo hints **được cấu hình thực**.
3. Thực hiện một số writes trước và sau window, ghi đúng thời điểm/ACK/CL.
4. Theo dõi `Hints_not_stored` và hint disk trên các holders.
5. N2 quay lại, kiểm tra những writes mới có thể không có hint tương ứng.
6. Lập **repair plan** trong lab sau khi phục hồi target và giới hạn IO.
7. Kiểm tra dữ liệu **trước/sau repair** bằng ledger keys/revisions; không chỉ quan sát success message của nodetool.

**Không giả định** `Hints_not_stored` sẽ tăng trong mọi lab release/config đúng một đơn vị mỗi write; theo dõi counter thực và window policy. Nếu không có tài nguyên để chạy lab dài, thực hiện tabletop với giả định có gắn nhãn thay vì rút ngắn grace/tắt bảo vệ an toàn.

### 13.6. Negative test về timeout outcome

Trong window N2 Down, nếu client write bị timeout:

~~~text
Input intended: revision=3, state='REVIEW'
Response: WriteTimeoutException at LOCAL_QUORUM
Known: coordinator/CL/required vs received responses (nếu có)
Unknown: mutation đã tới N1/N3/N2 hay chưa, theo từng thời điểm
~~~

**Đừng chạy lại cùng mutation với TTL mới hoặc counter/list append** rồi nói đã đảm bảo đúng; reconciliation cần operation ID, key, value, timestamp và idempotency policy. Một write timeout có thể đã apply ở một replica; việc read thấy revision=3 không tự biến timeout thành ACK thành công.

## 14. Năm tình huống xử lý sự cố có lời giải

### 14.1. Case A — Node trở lại nhưng hints replay chậm

**Giả định:**

~~~text
09:05Z  N2 Down
09:07Z  v2 write LOCAL_QUORUM thành công
09:45Z  N2 Up, app LOCAL_ONE đôi lúc thấy v1
09:47Z  HintsSucceeded tăng trên N1 nhưng N3 HintsTimedOut tăng
09:50Z  Disk util N2 cao; N2 status UN từ N1 và N3
~~~

**Cách tiếp cận:**

1. Bằng chứng **v2 đã ACK tại LQ** cho đúng PK từ operation ledger.
2. So `LOCAL_ONE` và `LOCAL_QUORUM` trên cùng key/CL được phép, thu coordinator/trace với sampling thấp.
3. Kiểm tra **N1 và N3** là những hint holders có thể; không chỉ N2.
4. HintsSucceeded tăng là tín hiệu tiến triển, HintsTimedOut và disk util N2 cao là tín hiệu delivery nghẽn.
5. Giữ tài nguyên dành cho replay, đánh giá target disk/GC/network. Nếu không có missing hints và progress ổn, có thể **theo dõi** trước khi repair.
6. Đạt exit gate khi sample keys đúng, lỗi stale giảm ở CL contract, delivery failures hết hoặc có giải thích và lịch repair vẫn đáp ứng policy.

**Không nên:** tăng throttle cực đại ngay, xóa hints hoặc restart N2 lần nữa không có bằng chứng.

### 14.2. Case B — Hints_not_stored sau downtime dài

**Giả định:**

~~~text
T0       N2 Down
T0+1h    successful LQ writes; có hints
T0+4h    successful LQ writes; max_hint_window mặc định 3h
T0+5h    N2 Up
T0+5h15  Những writes cuối có thể còn thiếu ở N2
~~~

**Cách tiếp cận:**

- Xác minh `max_hint_window` **thực tế**, không mặc định 3h nếu cluster đã thay config.
- Xem `Hints_not_stored-<N2>` trên các holders và khoảng thời gian nó tăng.
- Phân biệt hints **đã tồn tại** trước window với mutations **không có hint** sau window.
- Đánh giá repair **đúng scope** sau khi N2 ổn và các replicas cần thiết Up.
- Khi hoàn tất repair, kiểm tra ledger revisions/writes và status trước/sau; không coi riêng job exit code là đủ.

**Không nên:** đợi vô hạn cho hints mà bản thân không được lưu, hoặc làm repair ngay khi target còn Down.

### 14.3. Case C — Replica nghỉ 12 ngày, dữ liệu xóa tái xuất hiện

**Giả định:** table có `gc_grace_seconds=864000` (10 ngày), N2 Down 12 ngày; các deletes được ACK ở N1/N3. Một số tombstones đã eligible purge và bị compact. Sau N2 Up có báo cáo “đã xóa nhưng hiện lại”.

**Cách tiếp cận:**

1. Đánh dấu đây là **data integrity incident**, không chỉ hint backlog.
2. Thu delete operation IDs, timestamps, repair history, gc grace policy, SSTables/compaction evidence, impacted partitions.
3. Không chạy full repair một cách mù quáng; bản dữ liệu cũ có thể bị lan truyền nếu tombstones đã mất.
4. Dùng backup/operation log/source of truth xác minh trạng thái đúng; theo runbook recovery/rebuild và cô lập luồng ảnh hưởng nếu cần.
5. Xây lịch repair/protocol recovery sao cho replicas được bảo vệ trước grace trong tương lai.

**Điểm cần nhớ:** 12 ngày Down **không tự chứng minh** đã xảy ra zombie; cần bằng chứng deletion missed + tombstone purge + dữ liệu xuất hiện lại.

### 14.4. Case D — Cross-DC stale read dù DC local vẫn có quorum

**Giả định:** RF3 ở dc1 và dc2. Client dc1 ghi v2 thành công với `LOCAL_QUORUM`; client dc2 đọc v1 tại `LOCAL_QUORUM` ngay sau đó, trong khi network WAN chậm.

**Cách tiếp cận:**

- Kiểm tra local DC routing của từng client và CL thực.
- Xác định W LQ dc1 không đòi dc2 ACK; chưa cần giả định hints backlog.
- So internode cross-DC traffic, errors, hints disabled per DC, topology và time window.
- Thiết kế consistency contract phù hợp cross-region read-after-write thay vì coi mỗi LQ như một global quorum.
- Không bật `ConsistencyDowngradingRetryPolicy` để che lỗi.

**Điểm cần nhớ:** một successful local write không tự làm các local quorums ở **hai DC khác nhau** giao nhau.

### 14.5. Case E — Không có replication lag, chỉ cache hoặc timestamp sai

**Giả định:** người dùng thấy v1 qua HTTP cache trong 5 phút, nhưng direct CQL read đúng v2 ở `LOCAL_ONE` và `LOCAL_QUORUM` trên cùng key. Một cách khác, direct CQL luôn v1 vì client gửi mutation “v2” với `USING TIMESTAMP` cũ hơn v1.

**Cách tiếp cận:**

1. Bypass cache có kiểm soát rồi so direct CQL với API response, xác minh keyspace/PK.
2. Kiểm tra invalidation/cache TTL, JSON serialization, device/day bucket và version.
3. Nếu Cassandra vẫn v1, đọc `WRITETIME(column)` trên cột phù hợp, so timestamp effective và concurrent writes; không suy từ `updated_at`.
4. Xem logs về write CL/response và CAS outcomes; có thể mutation được ACCEPTED nhưng thua timestamp order.
5. Khi xác định không có replica lag, **không** chạy repair chỉ vì HTTP thấy cũ.

**Điểm cần nhớ:** “user thấy stale” và “replica thực sự lệch” là hai phát biểu khác nhau, phải được chứng minh độc lập.

### 14.6. Bảng phân biệt nhanh

| Case | Dấu hiệu mạnh | Hướng xử lý ưu tiên |
|---|---|---|
| A | Target rejoin, hint delivery progress nhưng fail/lag | Ổn định target, theo dõi delivery, validate |
| B | Downtime quá hint window, not-stored tăng | Repair có kiểm soát sau khi node khỏe |
| C | Downtime quá grace, deletes tái xuất hiện | Data integrity recovery, tránh repair mù |
| D | Write LQ dc1, read LQ dc2 cũ | Kiểm tra consistency contract cross-DC |
| E | Direct CQL đúng nhưng API cũ / timestamp thua | Cache/DTO/last-write-wins, không đổ lỗi hints |

## 15. Anti-patterns, báo cáo và xác nhận phục hồi

### 15.1. Mười sáu ngộ nhận cần bác bỏ

| Ngộ nhận | Vì sao sai | Hành vi đúng |
|---|---|---|
| “N2 UN nghĩa đủ dữ liệu” | Gossip liveness khác replica convergence | Thu hints/repair/data evidence |
| “Hint created nghĩa target nhận rồi” | Hint được giữ trên holder | Quan sát delivery và target |
| “Hết 3 giờ thì hints tự xóa hết” | Window liên quan new hint creation | Tách stored hints vs not-stored |
| “Một holder có disk trống, cluster không còn hint” | Hints có thể rải nhiều coordinators | Kiểm tra tất cả holders liên quan |
| “TotalHints là số pending” | Counter đã tạo từ lúc start; reset có thể xảy ra | Kết hợp rates, files, per-peer metrics |
| “HintsSucceeded tăng thì không cần repair” | Hints best effort, có thể không được tạo | Duy trì repair schedule và integrity gates |
| “Hãy chạy repair ngay khi node vẫn Down” | Có thể fail/không đủ replicas, tăng IO | Ổn định topology và preflight |
| “Repair một node là repair toàn cluster” | Scope chỉ token ranges của node được gọi | Lập coverage per node/DC; -pr hợp lý |
| “Read repair thay thế full repair” | Chỉ dữ liệu và replicas tham gia read | Anti-entropy repair theo lịch |
| “LOCAL_ONE luôn đọc bản mới nhất” | Một replica stale có thể được chọn | Hiểu CL và read routing |
| “Hai LOCAL_QUORUM ở hai DC luôn đồng bộ tức thì” | Quorum local khác tập replicas | Xem cross-DC consistency contract |
| “WriteTimeout nghĩa không replica nào ghi” | Có thể mutation đã apply một phần | UNKNOWN outcome + reconciliation |
| “v2 có updated_at lớn là thắng” | LWW xét write timestamp, không mặc định cột updated_at | Xem WRITETIME và concurrent writes |
| “Xóa hints giúp cluster sạch hơn” | Mất cơ hội giao missed mutations | Chỉ dùng truncatehints theo recovery runbook |
| “gc_grace_seconds=0 giúp sửa stale reads” | Tăng nguy cơ deleted-data resurrection | Giữ grace phù hợp repair/downtime |
| “API cũ nghĩa Cassandra replica cũ” | Cache/schema/DTO/timestamp cũng có thể gây lỗi | So direct CQL và app cache |

### 15.2. Mẫu báo cáo incident có thể dùng khi trực ca

~~~markdown
# INC-... Hinted handoff / stale read

## Scope / UTC
- Last known good: ...
- First known bad: ...
- User impact: % stale responses, read errors, p99, tenant/service/DC
- Node history: N2 Down ... Up ..., source nodes for gossip view

## Write/read contract
- Keyspace/table/PK shape: ...
- RF by DC, write CL, read CL, serial CL if LWT: ...
- Successful writes: ...
- Unknown timeouts/outstanding operations: ...
- Cache behavior and query fingerprint: ...

## Hints and repair
- Holders inspected (names/host IDs/DCs): ...
- Target identity and state: ...
- Config: enabled, disabled DCs, max window, throttle, delivery threads
- Hints_created, Hints_not_stored, Succeeded/Failed/TimedOut rates
- Hints directory bytes and disk headroom by holder
- Last full/incremental repair scope, success, time and gc_grace

## Evidence
- EV-001: metric URL, UTC window, units, source node, snapshot
- EV-002: logs/trace ID, UTC window, redacted fields
- EV-003: sampled read one/quorum, same PK, result and error

## Hypotheses and actions
- H1 ... prediction, falsifier, confidence
- H2 ... prediction, falsifier, confidence
- Action ... owner, approval, before/after, rollback and stop conditions

## Recovery gate
- User SLO at representative offered traffic: ...
- Replica convergence / repair coverage: ...
- Data integrity including deletes/TTL: ...
- Remaining unknown writes/risks and next owner: ...
~~~

**Không tuyên bố đã repair hoặc đã xác minh dữ liệu chỉ từ trạng thái `UN`.** Báo cáo phải tách quan sát trực tiếp, suy luận và giả thuyết. Không nêu raw user IDs/partition keys nếu không được phép; dùng pseudonymized operation IDs và links nội bộ có quyền.

### 15.3. Recovery gate nhiều tầng

Một sự cố chỉ nên được đánh dấu **RESOLVED** khi các điều kiện đã xác định trong runbook đạt:

1. **User-facing SLO:** stale/error rate và p95/p99 theo query/tenant/DC trở lại mức mục tiêu trong cửa sổ đủ dài, ở traffic đại diện.
2. **Cluster health:** target/holders ổn định, không có backlog không kiểm soát, disk/GC/network/compaction có headroom.
3. **Hint status:** các holders liên quan đã quan sát; failed/timeout deliveries không kéo dài; biết có hoặc không có `Hints_not_stored`.
4. **Data correctness:** sample ledger keys đúng theo policy, các mutations UNKNOWN đã reconcile hoặc có owner và deadline.
5. **Repair coverage:** nếu cần anti-entropy repair, job thành công và bao phủ đúng token ranges/tables/DCs theo runbook.
6. **Deletion safety:** không còn cảnh báo zombie/downtime quá grace chưa xử lý, TTL/deletes được kiểm tra ở mức cần thiết.
7. **Operational handoff:** rollback/mitigation có owner/expiry, root cause confirmed hoặc hypotheses chưa giải quyết được ghi rõ.

Nếu p99 khỏe vì traffic giảm 90%, hoặc read `LOCAL_ONE` được thay bằng cache có TTL rất dài, **không** được dùng như bằng chứng hệ thống đã phục hồi đúng nghĩa.

### 15.4. Bàn giao ca ngắn

~~~text
INC ID / STATUS: ...
Last good/first bad UTC: ...
Affecting: keyspace/table/service/DC/client version ...
Write/read CL and actual outcomes: ...
Known N2 downtime, max_hint_window, gc_grace: ...
Holders checked / still unchecked: ...
Metrics: created, not-stored, succeeded, failed, timeout, disk
Best hypothesis and falsifier: ...
What we did NOT do: truncatehints, downgrade CL, unsafe repair
Next safe check and owner: ...
Repair plan / data integrity risk / next update UTC: ...
~~~

## 16. Bài tập vận dụng và câu hỏi phỏng vấn

### Bài 1 — Replica Up có đồng nghĩa đã bắt kịp?

N2 nghỉ 30 phút, quay lại với `nodetool status` là `UN`. Dashboard `HintsSucceeded` mới bắt đầu tăng. Có thể kết luận mọi replica đã nhận đủ writes trong downtime?

**Đáp án:** không. `UN` phản ánh topology/liveness theo gossip view; HintsSucceeded là tín hiệu có delivery, **không xác nhận toàn backlog và những mutations chưa được hint**. Cần theo dõi holders/targets, failure/not-stored, data checks và repair scope nếu cần.

### Bài 2 — Điều gì khác giữa hint window và gc grace?

Node Down bốn giờ, cluster có `max_hint_window=3h`, `gc_grace_seconds=10d`. Có nghĩa tất cả hints bị xóa và dữ liệu delete chắc chắn zombie?

**Đáp án:** không. Window 3h liên quan **tạo hint mới** sau khi target Down; các hints đã lưu có thể được giao sau đó. Grace 10 ngày bảo vệ tombstones khỏi purge sớm trong compaction theo điều kiện; bốn giờ không tự tạo zombie. Tuy nhiên mutations ngoài hint window có thể cần anti-entropy repair.

### Bài 3 — W=LOCAL_QUORUM và R=LOCAL_ONE

RF3 trong dc1, N2 Down. Write v2 được N1 và N3 ACK tại `LOCAL_QUORUM`. N2 Up nhưng chưa replay. Điều gì có thể xảy ra nếu read `LOCAL_ONE` được phục vụ từ N2?

**Đáp án:** N2 có thể trả v1. Write quorum success không làm tất cả replicas nhận mutation ngay. Nếu read `LOCAL_QUORUM` thành công và không có concurrent writes/timestamp conflict, quorum giao nhau với successful write, có thể reconcile v2.

### Bài 4 — “Đã sửa” nhưng chỉ đổi CL

Ứng dụng đọc stale 5% tại LOCAL_ONE. Đội vận hành đổi toàn service sang LOCAL_QUORUM, stale giảm nhưng timeout tăng. Có gọi đó là root-cause fix không?

**Đáp án:** không. CL mới có thể che replica lag bằng reconcile/đọc nhiều replicas nhưng đánh đổi availability/latency. Cần xác minh source divergence, hint/replay/repair và policy consistency; chỉ đổi CL theo business contract/phê duyệt.

### Bài 5 — Quorum đọc v2 có chứng minh N2 đã có v2?

Ứng dụng đọc `LOCAL_QUORUM` trả v2. Hỏi: mọi replica đã có v2 chưa?

**Đáp án:** chưa. CL quorum chỉ cần phản hồi từ một quorum; read repair có thể cập nhật replicas tham gia, không phải mọi replicas và mọi partitions. Cần evidence target/hints/repair.

### Bài 6 — HintsSucceeded cao nhưng Hints_not_stored cũng tăng

Sau N2 Up, HintsSucceeded tăng đều. Đồng thời, trên N3 có Hints_not_stored tăng trong downtime. Có được chỉ chờ delivery để khẳng định đủ dữ liệu?

**Đáp án:** không. Những mutations đã **không được lưu hint** không xuất hiện chỉ nhờ replay. Cần đánh giá anti-entropy repair đúng phạm vi sau khi topology ổn, đồng thời xác minh data.

### Bài 7 — Tại sao phải thu trên nhiều holders?

Operator chỉ xem `/var/lib/cassandra/hints` trên N2 và thấy rỗng, kết luận không có backlog. Sai ở đâu?

**Đáp án:** hints thường nằm trên **coordinators/hint holders** khi N2 unreachable; N2 là target chứ không nhất thiết holder. Tra holders có thể gồm N1/N3 và node khác từng làm coordinator.

### Bài 8 — Tracing từ contact point

Kết nối `cqlsh` trực tiếp tới N2 rồi đọc v2 tại LOCAL_ONE. Có chứng minh N2 local replica đã nhận v2 không?

**Đáp án:** không tự động. Coordinator có thể liên hệ replica khác. Cần xác định replica contacts bằng tracing/diagnostic trong lab hoặc phương án kiểm thử phù hợp; kết nối vào một node không bắt buộc đọc SSTable local của nó.

### Bài 9 — ReadTimeout khác dữ liệu cũ

Một request trả `ReadTimeoutException`. Có thể ghi “query thấy state cũ” không?

**Đáp án:** không. Timeout là **không có kết quả đọc hợp lệ** theo CL/deadline, khác với một successful read trả v1. Phân nhóm outcomes riêng.

### Bài 10 — Incremental repair có thay full repair?

Cluster chạy incremental đều. Sau một sự cố mất SSTable data ở vùng đã marked repaired, operator kết luận “incremental sẽ tự phát hiện và khôi phục”. Vì sao cần xem lại?

**Đáp án:** incremental có thể bỏ qua dữ liệu đã marked repaired; không xử lý mọi corruption/loss. Cần full repair hoặc kế hoạch recovery phù hợp theo phạm vi và mức độ; không chạy mù khi nghi tombstone resurrection.

### Bài 11 — Deleted data xuất hiện lại

Node nghỉ 12 ngày, table grace 10 ngày, một record đã DELETE trước đó nay lại xuất hiện sau khi node quay lại. Chọn hành động nào?

**Đáp án:** coi là **data-integrity incident**. Thu deletion/tombstone/repair history, khoanh vùng keys và source of truth, lập kế hoạch cô lập/recovery; **không** chạy repair toàn cluster hoặc xóa hints tùy tiện, vì có thể lan truyền stale data.

### Bài 12 — Cross-DC local quorums

Client dc1 nhận write v2 SUCCESS ở LOCAL_QUORUM. Client dc2 ngay sau đó đọc v1 ở LOCAL_QUORUM. Có nhất thiết là bug Cassandra?

**Đáp án:** không. Hai local quorums ở hai DC khác nhau không bắt buộc giao nhau; cross-DC mutation có thể chưa tới. Cần xác minh RF, WAN/network, hint policy và consistency contract.

### Bài 13 — Value có write timestamp cũ

Một API nhận SUCCESS cho UPDATE revision=3 nhưng mọi đọc vẫn thấy revision=2. Client gửi `USING TIMESTAMP` nhỏ hơn timestamp của v2. Có nên đổ lỗi hint backlog?

**Đáp án:** chưa. Cassandra giải quyết conflict theo write timestamp; mutation mới gửi có thể thua và không trở thành visible winner. Dùng `WRITETIME` trên cột phù hợp và operation ledger/concurrent writes để điều tra.

### Bài 14 — Hints directory tăng 5 GiB

N1 hints directory tăng 5 GiB trong khi target N2 Up, nhưng HintsSucceeded rất thấp và HintsTimedOut cao. Có nên tăng throttle 20 lần?

**Đáp án:** chưa. Xem target disk IO/GC, network errors, hints delivery threads/throttle, number of holders và scope trước. Nếu bottleneck là target disk, tăng throttle có thể làm timeout nhiều hơn. Chỉ thay một biến có stop condition.

### Bài 15 — TTL hết hạn khi hints đang replay

Ứng dụng ghi cell TTL 60 s trong downtime, N2 Up sau 5 phút. Không thấy cell trên N2 sau khi hint được xử lý. Có chắc hint thất bại?

**Đáp án:** chưa. Dữ liệu có TTL có thể đã hết hạn theo deadline của mutation; cần phân biệt **expiry đúng semantics** với **missed mutation**. Thu thời điểm ghi, TTL còn lại, write timestamp, tình trạng tombstones/repair; không kỳ vọng một cell đã hết hạn phải xuất hiện live.

### Bài 16 — Kết thúc incident khi không còn errors

Sau rollback giảm traffic 90%, HTTP timeout về zero. Nhưng `Hints_not_stored` đã tăng và N2 chưa repair. Có thể đóng incident là “resolved”?

**Đáp án:** không nếu data correctness gate chưa đạt. Cần traffic đại diện, repair/reconciliation policy, integrity verification, outstanding unknown writes và owner cho residual risks.

### Checklist thực hành

- [ ] Có timestamp UTC: last-good, first-bad, N2 Down/Up, write ACK, replay, repair.
- [ ] Biết RF và CL **theo DC thực**, không chỉ cấu hình mặc định trong code.
- [ ] Tách SUCCESS, CAS_FALSE, UNKNOWN_TIMEOUT, UNAVAILABLE và STALE_RESULT.
- [ ] Phân biệt coordinator/hint holder với target natural replica.
- [ ] Thu topology `nodetool status` từ nhiều nodes khi nghi gossip partition.
- [ ] Biết hints mặc định best effort, không thay anti-entropy repair.
- [ ] Hiểu `max_hint_window` là new hint creation window, không phải thời hạn replay.
- [ ] Kiểm tra hints disabled per DC, window, throttle, threads, quota và directory thực.
- [ ] Đo Hints_created/not-stored/Succeeded/Failed/TimedOut và Hint_delays theo peer/nodes.
- [ ] Theo dõi hints directory bytes, disk IO/space, target GC/network và compaction.
- [ ] Không dùng created-minus-succeeded như exact backlog khi chưa xác minh semantics.
- [ ] Không suy từ node UN hay read quorum SUCCESS rằng mọi replicas đều hội tụ.
- [ ] Kiểm tra read cache, query keyspace/PK, timestamp, TTL và concurrency trước khi đổ lỗi hints.
- [ ] Không giả định contact point là replica trực tiếp trả data.
- [ ] Nếu hints thiếu hoặc Down vượt window, lập anti-entropy repair theo runbook.
- [ ] Phân biệt incremental/full repair, phạm vi primary ranges/nodes/DCs.
- [ ] Đánh giá tombstone/gc grace và nguy cơ zombie trước repair sau downtime dài.
- [ ] Không chạy truncatehints, xóa files, disablehandoff hoặc hạ CL để che lỗi.
- [ ] Có data integrity gate, repair evidence, error/SLO recovery và owner bàn giao.

## 17. Tài liệu tham khảo

Các tài liệu sau là điểm xuất phát để kiểm tra theo **đúng phiên bản Cassandra/Driver đang dùng**. Cấu hình và lệnh không thay thế runbook production.

1. Apache Cassandra — [Hints / Hinted Handoff](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hint lifecycle, best-effort semantics, replay, `max_hint_window`, throttling, `nodetool statushandoff`/`pausehandoff`/`truncatehints`.
2. Apache Cassandra — [Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): `Storage.TotalHints`, `HintedHandOffManager`, `HintsService.HintsSucceeded/Failed/TimedOut`, `Hint_delays` và table-level read/compaction metrics.
3. Apache Cassandra — [Read Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/read_repair.html): `BLOCKING`/`NONE`, monotonic quorum reads, read repair theo replicas/partitions tham gia và các giới hạn.
4. Apache Cassandra — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, Merkle trees, incremental/full repair, `-pr`, lịch repair và khoảng an toàn với tombstones.
5. Apache Cassandra — [nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html): cú pháp `--full`, `-pr`, `--preview`, `--validate`, scope theo keyspace/table/token ranges.
6. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): delete markers, TTL, `gc_grace_seconds`, nguy cơ zombie data và điều kiện purge.
7. Apache Cassandra — [Compaction Overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html): SSTables, tombstone reclamation, compaction IO và ảnh hưởng tới read latency.
8. Apache Cassandra — [cassandra.yaml Configuration](https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_yaml_file.html): tham số hints, network internode, các tên/cú pháp theo release.
9. Apache Cassandra — [Data Definition (DDL)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): NetworkTopologyStrategy, replication factor, table `read_repair` option, table-level `gc_grace_seconds`.
10. Apache Cassandra — [Data Manipulation (DML)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): CL, TTL, write timestamps, DELETE/upsert, conditional writes.
11. Apache Cassandra — [nodetool Status](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/status.html): node Up/Down/Normal/Joining/Leaving, views theo gossip.
12. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): read/write timeout, unavailable, default retry policy và nguy cơ consistency downgrading.
13. Apache Cassandra Java Driver 4.19 — [Statement Attributes](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): immutable statements, consistency, timeout, tracing, idempotence.
14. Apache Cassandra Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): execution profiles, local DC và default CL/request timeout.
15. Apache Cassandra Java Driver 4.19 — [Tracing](https://apache.github.io/cassandra-java-driver/4.19.0/core/tracing/): `ExecutionInfo`, per-query traces, sampling và hệ thống `system_traces`.
16. Apache Cassandra Java Driver 4.19 — [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): driver session/node metrics, in-flight, connection pools và request attempts.

**Kết luận:** Hints giúp replicas bắt kịp sau downtime nhưng chỉ là **một cơ chế phục hồi best effort**. Muốn giải thích một read trả cũ, hãy chứng minh trước **write outcome**, **replica set/CL**, **hint holder/target state**, **TTL/timestamp**, rồi mới chọn **theo dõi replay hoặc anti-entropy repair**. Một incident được giải quyết khi cả **trải nghiệm người dùng** và **tính đúng đắn dữ liệu** đạt yêu cầu — không chỉ vì mọi node đã trở về `UN`.
