# TTL, timestamp, dấu xóa và quan hệ với cơ chế lưu trữ

Trong mô hình cơ sở dữ liệu NoSQL **cột rộng (wide-column)**, việc ghi, cập nhật, hết hạn và xóa dữ liệu liên quan trực tiếp tới cách hệ quản trị lưu nhiều phiên bản của một giá trị. Ở các hệ phân tán dùng cấu trúc **LSM-tree** như Apache Cassandra hoặc ScyllaDB, một lần cập nhật không nhất thiết sửa ngay dữ liệu cũ trên đĩa; phiên bản mới được ghi, các phiên bản trước vẫn có thể còn trong các tệp bất biến và hệ thống hợp nhất chúng khi đọc hoặc khi chạy compaction.

Bốn khái niệm quan trọng tạo thành một chuỗi cơ chế:

- **TTL (Time To Live)** quy định một giá trị còn hiệu lực trong bao lâu.
- **Write timestamp** giúp quyết định phiên bản ghi nào có ưu tiên khi các cập nhật cùng khóa đến từ nhiều nơi hoặc theo thứ tự khác nhau.
- **Tombstone (dấu xóa)** biểu diễn rằng dữ liệu cũ đã bị xóa, để bản sao cũ ở replica hoặc SSTable không vô tình xuất hiện lại.
- **Compaction và quá trình thu hồi vật lý** hợp nhất các phiên bản, dọn dữ liệu hết hạn và tombstone khi việc dọn không làm mất an toàn.

Vì vậy, phải phân biệt ba sự kiện: **dữ liệu hết hiệu lực và không còn được trả về**, **dữ liệu được đánh dấu xóa**, và **byte dữ liệu cũ thực sự được thu hồi khỏi phương tiện lưu trữ**. Chúng có thể xảy ra ở những thời điểm rất khác nhau.

> **Phạm vi kỹ thuật:** Các ví dụ CQL, hàm TTL/writetime, SSTable và tùy chọn gc_grace_seconds chủ yếu minh họa cơ chế trong họ Cassandra/ScyllaDB. Tên gọi wide-column không phải một chuẩn về TTL, transaction, replication hay compaction. Khi triển khai, cần xác minh cú pháp và bảo đảm theo đúng sản phẩm, phiên bản, cấu hình và môi trường của hệ đang dùng.

## 1. Bối cảnh: dữ liệu cột rộng và các loại thời gian

Một bảng theo phong cách Cassandra thường thiết kế quanh **partition key** và **clustering columns**:

~~~sql
CREATE TABLE device_events (
    tenant_id text,
    device_id text,
    event_time timestamp,
    event_id timeuuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

**Partition key** nhóm dữ liệu theo thiết bị và tenant. Các **clustering columns** sắp thứ tự những hàng thuộc partition. Các trường event_type và payload là dữ liệu thông thường có thể được cập nhật và đặt TTL theo cơ chế của hệ quản trị.

Điểm rất dễ nhầm là **event_time trong primary key không đồng nghĩa write timestamp nội bộ**. Một thiết bị đo vào 10:00, mất kết nối rồi gửi lên lúc 11:00. Dữ liệu cần sắp xếp ở mốc 10:00, trong khi thao tác ghi vào database xảy ra lúc 11:00.

| Loại thời gian | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Event time / business time** | Sự kiện nghiệp vụ xảy ra khi nào? | Nhiệt độ được đo lúc 10:00 |
| **Ingestion time** | Hệ thống tiếp nhận dữ liệu khi nào? | Gateway nhận lúc 11:00 |
| **Write timestamp** | Phiên bản nào được ưu tiên khi hòa giải những lần ghi? | Phiên bản B có timestamp cao hơn A |
| **TTL / expiration time** | Từ thời điểm nào giá trị không còn sống? | Một giá trị hết hiệu lực sau 24 giờ |
| **Physical reclamation time** | Khi nào dữ liệu cũ được thu hồi khỏi SSTable? | Sau expiration, compaction và các điều kiện an toàn |

Không nên dùng một trường thời gian cho tất cả các ý nghĩa. Đặc biệt, trong hệ tương thích Cassandra, **write timestamp** là metadata phục vụ hòa giải phiên bản; trường **event_time** chỉ là dữ liệu nghiệp vụ và có thể được lựa chọn làm clustering key.

### 1.1. Một hàng logic có thể có nhiều phiên bản vật lý

Giả sử trạng thái thiết bị được ghi ba lần:

~~~text
Lần 1: status = "OFFLINE", write timestamp = 100
Lần 2: status = "ONLINE",  write timestamp = 200
Lần 3: status = "BUSY",    write timestamp = 300
~~~

Hệ lưu trữ LSM có thể có cả ba phiên bản trong những SSTable khác nhau. Khi đọc, hệ cần hòa giải phiên bản cùng khóa theo timestamp, tombstone và TTL để cho ra giá trị có hiệu lực. Sự tồn tại của nhiều phiên bản vật lý **không có nghĩa API trả về ba giá trị**.

## 2. TTL: giới hạn thời gian sống của giá trị

**TTL** là khoảng thời gian một giá trị được coi là còn sống kể từ khi được ghi theo semantics của hệ quản trị. Sau khi hết hạn, một truy vấn thông thường không còn trả về giá trị ấy như dữ liệu sống, dù byte cũ có thể tồn tại trên đĩa trong thời gian dài hơn.

Các trường hợp sử dụng thường gặp:

- Trạng thái session, token tạm thời và cache.
- Telemetry, log hoặc event có thời gian giữ hữu hạn.
- Dữ liệu trung gian có thể tái tạo.
- Những bảng time-series chỉ phục vụ cửa sổ gần đây.

TTL thường **không tự giải quyết** mọi yêu cầu retention, xóa tài khoản hoặc xóa dữ liệu theo hợp đồng, bởi còn replica, backup, cache, export, index và sự kiện phụ.

### 2.1. Đặt TTL khi INSERT

Ví dụ CQL cho dữ liệu hoạt động người dùng:

~~~sql
CREATE TABLE recent_activity (
    tenant_id text,
    user_id text,
    activity_id timeuuid,
    action text,
    details text,
    PRIMARY KEY ((tenant_id, user_id), activity_id)
);

INSERT INTO recent_activity
    (tenant_id, user_id, activity_id, action, details)
VALUES
    ('T-1', 'U-42', now(), 'VIEW_PRODUCT', 'SKU-9')
USING TTL 3600;
~~~

Trong nhiều hệ CQL tương thích Cassandra, TTL ở đây được tính bằng **giây**, nghĩa là giá trị được ghi có thời gian sống khoảng một giờ. Primary key dùng xác định vị trí dữ liệu; không nên tưởng tượng mỗi thành phần khóa chính có TTL độc lập giống một cell dữ liệu thường.

### 2.2. TTL khi UPDATE có thể áp dụng theo cell

Một ví dụ:

~~~sql
UPDATE recent_activity
USING TTL 900
SET details = 'SKU-9, nguồn: trang tìm kiếm'
WHERE tenant_id = 'T-1'
  AND user_id = 'U-42'
  AND activity_id = 11111111-1111-1111-1111-111111111111;
~~~

Thao tác này chỉ ghi lại cột được nêu trong SET. Trong mô hình TTL theo cell, **details** có thể hết hạn sau 15 phút trong khi **action** còn sống lâu hơn hoặc không có TTL. Cần xem xét điều đó nếu ứng dụng giả định tất cả các trường của một row luôn cùng tồn tại.

Một số lưu ý thiết kế:

- Ghi lại giá trị thường làm nó có timestamp mới và cơ chế TTL theo lần ghi mới.
- Không chỉ định TTL cho một lần UPDATE có thể cho ra thời hạn khác với giá trị cũ, tùy TTL mặc định của bảng.
- Không nên mặc định TTL cũ được kế thừa sau mọi lần cập nhật.
- Ghi đè một cột trong hàng không tự động gia hạn tất cả các cột khác.
- Một hàng có thể bị ẩn khi không còn dữ liệu sống thích hợp, dù các thành phần cấu trúc hoặc phiên bản cũ vẫn còn vật lý.

### 2.3. TTL mặc định của bảng

Cassandra cung cấp tùy chọn ví dụ **default_time_to_live**, cho phép quy định thời gian sống mặc định:

~~~sql
CREATE TABLE short_lived_events (
    tenant_id text,
    event_id timeuuid,
    payload text,
    PRIMARY KEY (tenant_id, event_id)
) WITH default_time_to_live = 86400;
~~~

Ví dụ chọn TTL mặc định một ngày cho loại dữ liệu có vòng đời đồng nhất. Trước khi sử dụng TTL mức bảng, cần biết có cột nào phải tồn tại lâu hơn không và các thao tác UPDATE có thay đổi vòng đời dự kiến không. Semantics ghi đè, hủy TTL, collection/counter và giới hạn giá trị TTL tùy sản phẩm.

### 2.4. Quan sát thời gian sống còn lại

Trong hệ hỗ trợ các hàm CQL tương ứng:

~~~sql
SELECT activity_id,
       action,
       ttl(action),
       writetime(action)
FROM recent_activity
WHERE tenant_id = 'T-1'
  AND user_id = 'U-42';
~~~

Với cột phù hợp, **ttl(action)** cho biết thời gian sống còn lại, thường tính theo giây; **writetime(action)** trả về write timestamp của giá trị. Trong Cassandra, write timestamp thường có độ phân giải **microsecond kể từ epoch**, nhưng độ phân giải lưu trữ không bảo đảm các đồng hồ phân tán luôn chính xác tới microsecond.

Không nên xem đây là hàm lấy một TTL thống nhất cho cả hàng: các cột khác nhau có thể có thời hạn khác nhau, và hàm có hạn chế với primary key hoặc kiểu đặc biệt.

### 2.5. Hết TTL khác với xóa vật lý

~~~text
10:00                       11:00                   Về sau
  |---------------------------|------------------------>
  Ghi giá trị với TTL 1 giờ   Giá trị hết hiệu lực     Thu hồi vật lý
                              khi truy vấn             khi đủ điều kiện
~~~

Không tồn tại lời hứa phổ quát rằng đĩa sẽ giảm đúng lúc 11:00. SSTable có thể còn giữ giá trị hết hạn và metadata liên quan. Compaction, trạng thái replica và quy tắc an toàn xóa ảnh hưởng thời điểm thu hồi.

**TTL xác định logic sống/hết hạn; compaction quyết định cơ hội thu hồi vật lý.**

## 3. Write timestamp: bản ghi nào thắng khi có nhiều phiên bản?

Nhiều hệ wide-column phân tán hỗ trợ cập nhật cùng một khóa từ những node khác nhau. Một cách hòa giải phổ biến trong Cassandra/ScyllaDB là dựa trên **write timestamp** của giá trị, thường được mô tả giản lược là *last-write-wins by timestamp*.

### 3.1. Ví dụ hòa giải

Giả sử hai replica nhận cập nhật theo thứ tự khác nhau:

~~~text
Replica A nhận:
  status = "PAID"    @200
  status = "PENDING" @100

Replica B nhận:
  status = "PENDING" @100
  status = "PAID"    @200
~~~

Theo quy tắc ưu tiên timestamp lớn hơn, phiên bản @200 có hiệu lực dù hai replica nhận request theo thứ tự khác nhau.

~~~mermaid
flowchart LR
    A["Replica A: PENDING @100"] --> R["Hòa giải theo phiên bản"]
    B["Replica B: PAID @200"] --> R
    R --> C["Kết quả logic: PAID @200"]
~~~

Sơ đồ đơn giản hóa quy tắc; hệ thực còn xét tombstone, TTL, xử lý trường hợp timestamp bằng nhau và mức nhất quán đọc.

### 3.2. Timestamp không nhất thiết phản ánh thứ tự request trong thời gian thực

Trong CQL, một số câu lệnh có thể cung cấp timestamp:

~~~sql
-- Chỉ dùng để minh họa: timestamp nhỏ và giả định không hợp
-- với timestamp thực tế có thể khiến cập nhật không có hiệu lực.
UPDATE device_state
USING TIMESTAMP 2000000
SET status = 'ONLINE'
WHERE tenant_id = 'T-1' AND device_id = 'D-9';
~~~

Nếu không chỉ định, hệ sẽ sử dụng cơ chế timestamp mặc định của nó. Nếu ứng dụng tự truyền timestamp từ client, **đồng hồ sai hoặc nguồn dữ liệu không đáng tin cậy** có thể tạo timestamp quá lớn và gây kết quả khó hiểu.

Ví dụ:

~~~text
Write A: status = "ACTIVE" @1000
Write B: status = "PAUSED" @999999999999 (đồng hồ bị lệch tương lai)
Write C: status = "ACTIVE" @2000 (request đến sau B)
~~~

Phiên bản B vẫn có thể thắng C dù C đến muộn hơn ngoài đời thực. Đây là lỗi **thứ tự phiên bản**, không nhất thiết là lỗi replication.

### 3.3. Đừng dùng event time làm write timestamp tùy tiện

Một cảm biến gửi event cũ sau khi mất mạng. Nếu hệ dùng event time lịch sử làm write timestamp khi cập nhật cùng cell, bản ghi tới muộn có thể thua một phiên bản có timestamp cao hơn; điều đó có thể đúng hoặc sai theo nghiệp vụ.

Cần:

- Tách **event time** để truy vấn theo thời gian sự kiện.
- Xác định nơi cấp **write timestamp** và chính sách đồng bộ đồng hồ.
- Phân biệt replay, backfill với cập nhật trạng thái hiện tại.
- Dùng idempotency và cơ chế điều kiện cập nhật nếu cần chặn việc ghi đè dữ liệu theo quy tắc nghiệp vụ.

### 3.4. Last-write-wins không thay thế transaction

Hai khách cùng mua một món còn duy nhất 1 đơn vị. Nếu cả hai cùng đọc tồn kho là 1 rồi tự đặt tồn kho thành 0, cơ chế chọn phiên bản cuối theo timestamp vẫn **không bảo đảm chỉ một khách được giữ hàng**.

Bất biến như “không giữ quá số lượng khả dụng” cần thao tác điều kiện nguyên tử, CAS/LWT, transaction hoặc cơ chế cấp quota phù hợp. Write timestamp giải quyết **phiên bản hiển thị**; nó không tự xác minh rằng một cập nhật hợp lệ trong mọi trạng thái cạnh tranh.

## 4. Tombstone: vì sao DELETE cần để lại dấu xóa?

Trong cơ sở dữ liệu phân tán, bản sao cũ có thể nằm ở một replica đang offline hoặc một SSTable bất biến. Nếu lệnh DELETE đơn giản loại bỏ bản ghi ở node hiện tại mà không để lại dấu, hệ thống có thể không phân biệt “dữ liệu không tồn tại” với “replica này chưa nhận bản cập nhật”.

**Tombstone** là thông tin biểu diễn một thao tác xóa có hiệu lực so với các phiên bản cũ hơn. Nó giúp truyền ý nghĩa xóa qua hệ thống replica và qua nhiều vòng hòa giải dữ liệu.

### 4.1. Ví dụ một replica bỏ lỡ lệnh xóa

~~~text
Ban đầu:
  A: email = "old@example.test" @100
  B: email = "old@example.test" @100
  C: email = "old@example.test" @100

Replica C mất kết nối.
Client gửi DELETE @200:
  A: tombstone @200
  B: tombstone @200
  C: email = "old@example.test" @100 (chưa biết đã xóa)
~~~

Khi C kết nối lại, nếu thông tin xóa còn được giữ và cơ chế repair/hòa giải hoạt động đúng, tombstone @200 sẽ thắng giá trị @100.

~~~mermaid
sequenceDiagram
    participant User
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    Note over A,C: Cùng lưu dữ liệu @100
    Note over C: C offline
    User->>A: DELETE @200
    A->>B: Đồng bộ dấu xóa
    Note over A,B: Tombstone @200
    Note over C: C vẫn có dữ liệu @100
    Note over A,C: C hoạt động lại, cần repair/hòa giải
    A-->>C: Dấu xóa @200
    Note over A,C: Phiên bản @100 phải bị che
~~~

Đây là mô hình tư duy. Hành vi write consistency, hinted handoff, read repair và anti-entropy repair phụ thuộc hệ quản trị, cấu hình và phiên bản.

### 4.2. Các phạm vi xóa khác nhau

| Phạm vi | Ý nghĩa logic | Ví dụ |
|---|---|---|
| **Cell tombstone** | Một cột/giá trị bị xóa | Xóa riêng trường details |
| **Row tombstone** | Một hàng bị xóa | Xóa event cụ thể |
| **Range tombstone** | Xóa một khoảng theo thứ tự clustering | Xóa các event thuộc một khoảng hợp lệ |
| **Partition tombstone** | Xóa dữ liệu trong một partition | Xóa dữ liệu theo khóa partition |
| **Expired cell/TTL marker** | Giá trị không còn sống vì hết TTL | Session hết hạn |

Các cấu trúc xóa vật lý cụ thể không hoàn toàn giống nhau giữa các phiên bản hoặc sản phẩm. Điều quan trọng là dấu xóa có **phạm vi** và **thông tin ưu tiên về phiên bản**, để bản ghi cũ không được xem là hiện hành.

### 4.3. DELETE logic không đồng nghĩa byte bị xóa ngay

~~~sql
DELETE FROM recent_activity
WHERE tenant_id = 'T-1'
  AND user_id = 'U-42'
  AND activity_id = 11111111-1111-1111-1111-111111111111;
~~~

Một lệnh DELETE có thể được coi là hoàn thành theo mức nhất quán và acknowledgment của yêu cầu, nhưng không chứng minh:

- Mọi replica từng offline đã biết lệnh xóa.
- Mọi SSTable cũ đã được viết lại.
- Dung lượng đĩa giảm ngay.
- Backup, snapshot, index bên ngoài và export không còn dữ liệu.

### 4.4. Tombstone có thể làm việc đọc tốn kém

Giả sử partition từng có một triệu event nhưng đa số đã bị DELETE hoặc hết TTL. Truy vấn tìm 20 event còn sống có thể phải duyệt qua nhiều dữ liệu bị che hoặc hết hạn để xác định bản ghi hợp lệ.

Tác động có thể gồm:

- Read latency p95/p99 tăng.
- CPU và I/O tăng dù số hàng trả về ít.
- Cảnh báo khi đọc nhiều tombstone, hoặc timeout theo ngưỡng của hệ.
- Tăng công việc compaction và dung lượng trung gian.

Không phải mọi truy vấn đều quét toàn bộ tombstone: index, partition key, clustering range, SSTable metadata và các tối ưu của hệ có thể thu hẹp phạm vi. Cần đo theo truy vấn thực để xác định ảnh hưởng.

## 5. LSM-tree: mối liên hệ giữa ghi, xóa, hết hạn và compaction

Trong kiểu lưu trữ **Log-Structured Merge-Tree**, hệ nhận các thay đổi mới mà không nhất thiết ghi đè trực tiếp tệp cũ trên đĩa. Một sơ đồ khái niệm:

~~~mermaid
flowchart TD
    W["WRITE / UPDATE / DELETE"] --> L["Commit log"]
    W --> M["Memtable"]
    M --> F["Flush"]
    F --> S1["SSTable mới"]
    S1 --> C["Compaction"]
    S2["Các SSTable cũ"] --> C
    C --> S3["SSTable hợp nhất"]
~~~

Đường ghi, thứ tự acknowledgment và sự phân phối giữa replica phức tạp hơn sơ đồ trên; mục đích của sơ đồ là chỉ ra **SSTable thường bất biến và được hợp nhất về sau**.

### 5.1. Commit log và memtable

Một thao tác ghi có thể được ghi vào log phục hồi và memtable. Khi memtable được flush, một SSTable mới hình thành. UPDATE có thể tạo phiên bản mới; DELETE tạo thông tin xóa.

### 5.2. SSTable bất biến khiến dữ liệu cũ còn tồn tại

Ví dụ cùng một cột:

~~~text
SSTable A: status = "PENDING"  @100
SSTable B: status = "PAID"     @200
Memtable:   tombstone          @300
~~~

Về mặt vật lý, hệ có thể lưu cả giá trị @100, @200 và tombstone @300. Về mặt logic, kết quả đọc phải xét tombstone @300 để không trả một giá trị đã bị xóa.

### 5.3. Read path

Mô hình đọc:

~~~text
1. Tìm dữ liệu liên quan theo partition/clustering key.
2. Xem xét các phiên bản từ memtable và SSTable phù hợp.
3. Hòa giải write timestamp, tombstone và TTL.
4. Loại những giá trị không còn sống.
5. Trả dữ liệu có hiệu lực theo mức nhất quán và truy vấn.
~~~

Các cơ chế Bloom filter, partition index, cache và các tối ưu khác có thể giảm số tệp thực sự cần đọc. Vì vậy **logical merge** không đồng nghĩa luôn quét mọi SSTable của bảng.

### 5.4. Compaction và xóa vật lý

Compaction đọc các SSTable đầu vào, hợp nhất dữ liệu và tạo tệp mới. Nó có thể:

- Loại bỏ phiên bản cũ bị ghi đè khi an toàn.
- Thu hồi tombstone và giá trị hết hạn khi các điều kiện được đáp ứng.
- Giảm số tệp cần xét hoặc cải thiện bố trí dữ liệu, tùy chiến lược.
- Tiêu thụ CPU, I/O và dung lượng tạm.

**Compaction không bảo đảm mọi tombstone được xóa ngay**, vì vẫn có thể còn các SSTable khác chứa phiên bản cũ hoặc các replica chưa nhận dấu xóa. Quyết định thu hồi phải cân nhắc cả sự an toàn của dữ liệu phân tán.

## 6. TTL hết hạn có thể hoạt động như một dấu xóa

Khi một giá trị có TTL hết thời gian sống, hệ cần ngăn phiên bản cũ xuất hiện lại. Vì vậy trong họ Cassandra, expired cells có thể được xử lý về mặt logic tương tự tombstone trong quá trình đọc và dọn dữ liệu.

### 6.1. Ví dụ cập nhật giá trị có TTL

~~~text
10:00: status = "PENDING" @100, TTL 60 phút
10:10: status = "ACTIVE"  @200, TTL 10 phút
10:20: phiên bản ACTIVE hết hạn
~~~

Sau 10:20, hệ **không nên quay về giá trị PENDING** chỉ vì PENDING có thời hạn ghi dài hơn. Phiên bản được ghi mới đã thay thế phiên bản cũ; dấu hết hạn có vai trò ngăn phiên bản cũ tái xuất hiện.

### 6.2. TTL, write timestamp và expiration time là những giá trị khác nhau

Không nên áp dụng chung công thức đơn giản:

~~~text
expireAt = writeTimestamp + TTL
~~~

cho mọi hệ và mọi tình huống. Write timestamp được dùng để hòa giải phiên bản. Thời điểm expiration có thể được tính từ thời gian nhận ghi và lưu như metadata riêng, với độ phân giải và cơ chế đồng hồ cụ thể. Khi client tự cung cấp write timestamp lịch sử hoặc tương lai, **thời hạn sống không nhất thiết là phép cộng đơn giản vào timestamp đó**.

Nếu chính sách đòi hỏi “xóa 30 ngày sau lúc sự kiện phát sinh”, cần tính **deadline nghiệp vụ** và xác định TTL còn lại theo thời gian thực của quá trình ghi, đồng thời xử lý các trường hợp event đến muộn.

### 6.3. DELETE có timestamp cao hơn có thể che lần ghi đến sau

~~~text
WRITE value="A" @100
DELETE          @300
WRITE value="B" @200   (request đến sau DELETE)
~~~

Với quy tắc hòa giải timestamp, B có thể vẫn bị tombstone @300 che. Thứ tự nhận request **không thể thay thế write timestamp** khi hiểu kết quả cuối cùng.

### 6.4. TTL không tự thực hiện hành động bù nghiệp vụ

Giả sử record Reservation có TTL 15 phút. Khi nó hết hạn, điều đó **không tự động tăng tồn kho trở lại**, không gọi API hoàn tiền và không phát một sự kiện nghiệp vụ đáng tin cậy nếu không có cơ chế được thiết kế riêng.

Một luồng giữ hàng cần trạng thái, timeout, idempotency, đối soát và thao tác giải phóng phù hợp. TTL có thể hỗ trợ dọn dữ liệu tạm nhưng không thay thế orchestration của hệ thống.

## 7. gc_grace_seconds, repair và nguy cơ dữ liệu hồi sinh

Trong Cassandra, cấu hình **gc_grace_seconds** liên quan tới khoảng thời gian an toàn để tombstone có cơ hội được chuyển tới những replica chưa nhận DELETE. Nó không phải bộ đếm chắc chắn xóa vật lý ngay khi hết số giây đó.

### 7.1. Cơ chế zombie resurrection

Trạng thái:

~~~text
Replica A: tombstone @200
Replica B: tombstone @200
Replica C: dữ liệu cũ @100 (offline lúc xóa)
~~~

Nếu tombstone ở A và B bị thu hồi quá sớm, trước khi C nhận được thông tin xóa, replica C có thể cung cấp lại giá trị @100. Trường hợp bản ghi đã xóa xuất hiện lại này thường được gọi là **zombie data**.

~~~mermaid
flowchart TD
    D["Xóa dữ liệu: có tombstone"] --> O["Replica C bỏ lỡ xóa"]
    O --> Q{"Dấu xóa còn khi C quay lại?"}
    Q -->|Có| R["Repair/hòa giải giúp xóa phiên bản cũ"]
    Q -->|Đã thu hồi quá sớm| Z["Nguy cơ bản ghi cũ hồi sinh"]
~~~

### 7.2. Repair đóng vai trò gì?

**Repair** giúp phát hiện và đồng bộ sự khác biệt giữa các replica. Với dữ liệu cần xóa, quá trình này có thể đưa thông tin tombstone tới replica đã bỏ lỡ cập nhật, trong khi tombstone vẫn được giữ.

Khi thiết kế và vận hành:

- Xác định replica có thể offline lâu tới mức nào.
- Lập lịch repair phù hợp với cơ chế grace của hệ.
- Theo dõi repair có hoàn tất thật hay không.
- Chuẩn bị quy trình cho node offline dài ngày và backup restore.
- Không tự giảm grace chỉ để giảm số tombstone mà bỏ qua khả năng replica mang dữ liệu cũ.

Ở một số topology, phiên bản hay dịch vụ quản lý có thể có cơ chế bổ sung cho các tình huống đặc biệt; cần tham khảo chính xác sản phẩm để chọn cấu hình an toàn.

### 7.3. Hết grace chưa chắc tombstone biến mất

Một tombstone qua thời gian grace vẫn có thể cần tồn tại nếu có những SSTable khác chứa dữ liệu cũ mà việc bỏ tombstone sẽ làm chúng lộ ra. Compaction và quy tắc đánh giá overlap có vai trò quan trọng.

~~~text
Qua khoảng thời gian bảo vệ
        +
Điều kiện compaction và overlap an toàn
        +
Replica và lịch repair được quản lý phù hợp
        ↓
Tombstone/dữ liệu bị che mới có cơ hội được thu hồi
~~~

Đừng diễn giải gc_grace_seconds như một hạn chót để disk usage giảm. Nó là một phần trong thiết kế chống hồi sinh dữ liệu và cần đặt trong bối cảnh vận hành toàn hệ.

## 8. Compaction strategy tác động tới TTL và tombstone

Trong hệ LSM, **compaction strategy** quyết định SSTable nào được gom và khi nào, ảnh hưởng cả read amplification, write amplification, space amplification và quá trình loại bỏ dữ liệu hết hạn.

| Chiến lược phổ biến trong họ Cassandra | Ý tưởng cơ bản | Ý nghĩa với dữ liệu có TTL |
|---|---|---|
| **STCS – Size-Tiered** | Hợp nhất các SSTable có kích thước tương đồng | Thời điểm dữ liệu cũ được gộp và dọn phụ thuộc vòng compaction |
| **LCS – Leveled** | Tổ chức nhiều mức với quy tắc kiểm soát chồng lấn | Có thể cải thiện một số đường đọc, nhưng cần tính chi phí ghi/compaction |
| **TWCS – Time-Window** | Nhóm SSTable theo cửa sổ thời gian | Có thể thuận tiện cho dữ liệu append theo thời gian, TTL đồng nhất, ít cập nhật record cũ |

### 8.1. Tại sao TWCS hữu ích với time-series có TTL?

Nếu dữ liệu:

1. Được ghi gần với thời gian hiện tại.
2. Có TTL giống nhau hoặc tương đối đồng nhất.
3. Chủ yếu append-only.
4. Hiếm khi sửa/xóa những record rất cũ.

thì một số SSTable thuộc cùng cửa sổ có thể trở thành **hết hạn toàn bộ** sau khoảng thời gian giữ. Khi các điều kiện an toàn thỏa mãn, việc thu hồi có thể đơn giản hơn so với SSTable chứa xen kẽ dữ liệu có vòng đời rất khác nhau.

### 8.2. Khi nào lợi ích TWCS suy giảm?

- Ứng dụng cập nhật record cũ liên tục.
- Backfill dữ liệu từ nhiều thời điểm cũ.
- Một số cột TTL 1 giờ, cột khác TTL 1 năm, cột khác không TTL.
- Dữ liệu đến muộn và sử dụng write timestamp không phù hợp.
- DELETE các range cũ hoặc sửa trạng thái ở nhiều cửa sổ.

Những tình huống này có thể làm SSTable trộn tuổi dữ liệu và phiên bản, khiến công việc dọn dữ liệu phức tạp hơn. Không nên chọn TWCS **chỉ vì bảng có cột thời gian**; phải xét đường ghi thực sự.

### 8.3. TTL khác nhau làm khó thu hồi theo cửa sổ

Giả sử cùng SSTable có:

~~~text
Record A: TTL 1 giờ
Record B: TTL 30 ngày
Record C: không TTL
~~~

SSTable không thể được coi là hết hạn toàn bộ sau một giờ. Một record sống lâu có thể giữ lại SSTable chứa rất nhiều record đã hết hạn, tùy cơ chế compaction.

Một phương án là tách **short-lived events** và **long-lived states** thành bảng khác nhau, với retention và compaction phù hợp từng nhóm. Điều này có chi phí schema/index và đôi khi phải ghép dữ liệu khi đọc, nên cần dựa trên workload và benchmark.

## 9. Partition key và TTL phải được thiết kế cùng nhau

TTL không tự làm một partition trở nên nhỏ hoặc phân tán đều. Nếu mọi event của một thiết bị nhiều năm nằm dưới một partition key duy nhất, lượng dữ liệu sống/hết hạn/tombstone có thể lớn và truy vấn theo phạm vi rộng vẫn tốn kém.

### 9.1. Thiết kế dễ tạo partition quá lớn

~~~text
partition key = deviceId
sort key      = eventTime
TTL           = 7 ngày
~~~

Một thiết bị gửi hàng trăm nghìn event mỗi ngày. TTL chỉ cho biết giá trị hết hạn, trong khi partition vẫn có thể chứa rất nhiều cell và nhiều phiên bản trên SSTable chưa dọn.

### 9.2. Thêm time bucket vào partition key

~~~text
partition key = (tenantId, deviceId, dayBucket)
sort key      = (eventTime, eventId)
TTL           = 7 ngày
~~~

Ưu điểm:

- Có thể ước tính số event trong mỗi partition ngày.
- Truy vấn theo một ngày có phạm vi rõ ràng.
- Giúp phân tách lịch sử và thường phù hợp hơn với workload time-series.
- Cùng TTL, compaction phù hợp có thể giúp thu hồi hiệu quả hơn.

Đánh đổi:

- Truy vấn nhiều ngày phải đọc nhiều partition và hợp nhất kết quả.
- Một thiết bị cực nóng vẫn có thể quá tải partition ngày.
- Late events làm một số truy vấn và chính sách retention khó xử lý.
- Phân trang xuyên ngày cần cursor có thông tin bucket.

### 9.3. Time bucket không phải shard tự động

Nếu một thiết bị tạo 50.000 event/giây, chỉ thêm dayBucket chưa chắc phân tán write load trong ngày. Có thể cần shard trong partition key, ví dụ:

~~~text
(tenantId, deviceId, dayBucket, shardNo)
~~~

Nhưng khi đọc danh sách theo thời gian, ứng dụng phải fan-out và merge nhiều shard theo sort key. Thiết kế **phân tán ghi** kéo theo chi phí **truy vấn hợp nhất**, nên cần kiểm chứng cả hai chiều.

## 10. Retention theo thời điểm ghi hay thời điểm sự kiện?

Yêu cầu “giữ log 30 ngày” chưa đủ rõ nếu không xác định mốc bắt đầu tính.

Giả sử:

~~~text
Ngày 1: thiết bị phát sinh sự kiện
Ngày 10: backend mới nhận sự kiện do thiết bị offline
Ngày 31: hạn giữ 30 ngày theo event time
~~~

Nếu backend cấp TTL 30 ngày tại ngày 10, record có thể tồn tại hiệu lực tới ngày 40, lâu hơn mục tiêu theo event time.

Một thiết kế có thể xác định:

~~~text
deadline = eventTime + retentionDuration
remainingTTL ≈ deadline - currentServerTime
~~~

Tại ngày 10, thời gian sống còn lại theo nghiệp vụ chỉ khoảng 21 ngày. Khi tính TTL cần xử lý:

- Thiết bị có đồng hồ sai hoặc eventTime không đáng tin.
- Event đến sau deadline đã hết hạn.
- Đơn vị, độ phân giải, làm tròn và giới hạn TTL của database.
- Chênh lệch thời gian giữa application server, coordinator và replica.
- Retention của backup và projection.

Nếu dữ liệu đã quá hạn trước khi được nhận, ứng dụng có thể từ chối lưu vào bảng chi tiết hoặc chuyển sang luồng xử lý riêng theo chính sách. Không nên cố đặt TTL âm hoặc gán tùy tiện một TTL lớn.

### 10.1. TTL không thay thế quản lý xóa toàn hệ thống

Chính sách xóa đôi khi đòi hỏi:

- Xóa hồ sơ ngay theo yêu cầu của người dùng.
- Xóa dữ liệu nhạy cảm tại nhiều bảng, index, cache và hệ phân tích.
- Hủy khả năng truy cập sau khi hết quyền.
- Quản lý bản sao backup, snapshot và export theo retention.
- Có audit và đối soát xóa.

TTL chỉ điều khiển vòng đời ở nơi nó được áp dụng. Nó không tự phát sự kiện có bảo đảm để đồng bộ tất cả hệ phụ trợ.

## 11. Case study: lưu telemetry thiết bị trong 7 ngày

Giả sử hệ thống có:

- 50.000 thiết bị.
- Mỗi thiết bị gửi một event mỗi 10 giây ở tải trung bình.
- Giao diện truy vấn lịch sử 24 giờ gần nhất của một thiết bị.
- Log chi tiết có retention 7 ngày.
- Thống kê theo ngày cần giữ 2 năm.
- Một số thiết bị gửi dữ liệu trễ nhiều giờ.

### 11.1. Ước lượng tải

Một thiết bị tạo:

~~~text
6 event/phút × 60 phút × 24 giờ = 8.640 event/ngày
8.640 event/ngày × 7 ngày = 60.480 event trong 7 ngày
~~~

Toàn bộ:

~~~text
50.000 × 8.640 = 432.000.000 event/ngày
432.000.000 × 7 = 3.024.000.000 event trong cửa sổ 7 ngày
~~~

Đây là **số lượng event logic**, chưa tính kích thước payload, số replica, SSTable, compaction, tombstone, index hoặc dữ liệu đến muộn. Không thể kết luận dung lượng ổ đĩa chỉ từ số event sống và TTL.

### 11.2. Thiết kế bảng theo ngày

~~~sql
CREATE TABLE device_log_by_day (
    tenant_id text,
    device_id text,
    log_day date,
    event_time timestamp,
    event_id timeuuid,
    event_type text,
    message text,
    PRIMARY KEY (
        (tenant_id, device_id, log_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
~~~

Mỗi ngày và mỗi thiết bị có partition riêng. Để lấy 24 giờ gần nhất qua ranh giới ngày, ứng dụng truy vấn một hoặc hai partition rồi ghép theo thứ tự.

### 11.3. Ví dụ INSERT có TTL

~~~sql
INSERT INTO device_log_by_day (
    tenant_id, device_id, log_day,
    event_time, event_id, event_type, message
)
VALUES (
    'T-1', 'D-99', '2026-11-14',
    '2026-11-14T08:10:00Z', now(),
    'TEMPERATURE', '24.3 C'
)
USING TTL 604800;
~~~

Số **604.800 giây** bằng 7 ngày. Câu lệnh trên minh họa TTL theo thời điểm ghi; nếu retention phải dựa trên event_time thì ingestion service cần tính TTL còn lại.

### 11.4. Truy vấn theo partition và clustering range

~~~sql
SELECT event_time, event_id, event_type, message
FROM device_log_by_day
WHERE tenant_id = 'T-1'
  AND device_id = 'D-99'
  AND log_day = '2026-11-14'
  AND event_time >= '2026-11-14T00:00:00Z'
  AND event_time <  '2026-11-15T00:00:00Z';
~~~

Lý tưởng là truy vấn có đường đi theo partition key và clustering key. Nếu ứng dụng cần cả tuần, nó phải đọc nhiều partition ngày. Pagination không nên dùng cách tải tất cả event rồi cắt 50 phần tử ở ứng dụng.

### 11.5. Compaction và dữ liệu đến muộn

Nếu event chủ yếu được append gần hiện tại với TTL đồng nhất, một cấu hình time-window compaction có thể là ứng viên cần thử. Nhưng nếu thiết bị thường xuyên backfill event cũ hoặc cập nhật trạng thái hàng cũ, lợi ích của TWCS có thể giảm.

Một hệ thống có thể tách:

~~~text
Thiết bị
  |
  v
Ingest có kiểm tra eventTime và idempotency
  |                                   |
  v                                   v
DeviceLogByDay (TTL 7 ngày)    DailySummary (giữ lâu)
  |
  v
Compaction + monitoring + repair
~~~

Việc tổng hợp cần xử lý duplicate/late event, có checkpoint và cơ chế đối soát. Nếu pipeline tổng hợp dừng hơn 7 ngày và log đã hết TTL, khả năng rebuild có thể bị mất; vì vậy retention phải cân bằng với nhu cầu phục hồi của các pipeline phụ thuộc.

## 12. Tombstone scan: truy vấn ít kết quả vẫn có thể chậm

Một partition chứa 2 triệu event lịch sử, nhưng 99% đã hết TTL. API cần lấy 20 event sống mới nhất. Nếu các giá trị sống nằm sau rất nhiều giá trị hết hạn trong phạm vi truy vấn, hệ có thể phải xem xét nhiều tombstone trước khi trả đủ 20 hàng.

Một số chỉ báo:

- Read latency p95/p99 tăng theo tuổi dữ liệu.
- Truy vấn trả ít hàng nhưng CPU, disk I/O hoặc bytes read lớn.
- Cảnh báo quá nhiều tombstone nếu hệ có cơ chế cảnh báo.
- Số SSTable và compaction backlog tăng.
- Disk usage không giảm dù dữ liệu sống giảm.
- Một số partition bị timeout, trong khi partition khác bình thường.

**Không nên kết luận ngay từ một triệu chứng.** Truy vấn rộng, cache miss, hot partition, độ lệch replica hoặc thiết kế index kém cũng có thể gây chậm. Quan sát metric và profile theo access pattern cụ thể trước khi chọn giải pháp.

### 12.1. Các lựa chọn cải thiện

| Tình huống | Hướng xử lý có thể xem xét | Đánh đổi |
|---|---|---|
| Partition quá lớn theo năm | Thêm day/hour bucket vào partition key | Tăng số partition phải đọc cho khoảng dài |
| Append theo thời gian, TTL đồng nhất | Đánh giá TWCS trên workload thật | Nhạy với cập nhật cũ/backfill |
| Nhiều DELETE chi tiết | Xem lại lifecycle, retention, data model | Có thể cần thay đường truy cập |
| Một thiết bị quá nóng | Shard/queue hoặc giới hạn tốc độ | Fan-out và merge khi đọc |
| Tombstone tồn tại lâu | Kiểm tra compaction, overlap, grace, repair | Thay đổi thiếu kiểm soát có thể gây dữ liệu hồi sinh |
| Query đọc khoảng thời gian quá rộng | Giới hạn range, phân trang, read model | Thay đổi API hoặc nghiệp vụ |

Thực hiện compaction ép buộc hay thay gc_grace tùy tiện có thể tạo tải lớn hoặc rủi ro an toàn dữ liệu; không nên coi đây là thao tác dọn rác miễn phí.

## 13. Chi phí và capacity planning khi có TTL

Giả sử ingest **100 GB dữ liệu logic/ngày** và TTL **7 ngày**. Không nên tính chính xác nhu cầu đĩa bằng 700 GB rồi dừng lại. Cần xét:

- **Replication factor** và overhead định dạng.
- **SSTable chứa dữ liệu hết hạn** chưa được dọn.
- **Tombstone và phiên bản cũ** sau nhiều UPDATE.
- **Compaction space amplification** và dung lượng tạm.
- Commit log, index, cache hoặc file metadata.
- Snapshot, repair, streaming, backup và dữ liệu khác TTL.

Một công thức tư duy:

~~~text
Dung lượng cần dự phòng
  ≈ dữ liệu sống × số bản sao
   + dữ liệu cũ/tombstone chưa thu hồi
   + chỉ mục và metadata
   + dung lượng tạm compaction/repair
   + backup/snapshot theo chính sách
~~~

Đây không phải cách tính billing chung cho mọi nhà cung cấp. Capacity planning cần đo thực tế qua nhiều chu kỳ TTL và compaction, dành đủ headroom cho spike hoặc mất một node/replica.

### 13.1. Chi phí đọc và ghi diễn ra ở nhiều giai đoạn

Hệ LSM thường có đường ghi ban đầu thuận tiện cho throughput cao, nhưng công việc tiếp tục sau acknowledgment:

~~~text
Một thay đổi logic:
  ghi dữ liệu
  + sao chép trên replica
  + flush thành SSTable
  + compaction các phiên bản
  + xử lý TTL/tombstone
  + repair và backup khi cần
~~~

Do đó, benchmark chỉ ghi dữ liệu mới trong vài phút chưa thể kết luận hệ sẽ ổn định sau nhiều tuần hết TTL và compaction.

## 14. Những sai lầm cần tránh

### “TTL hết hạn thì bản ghi biến mất khỏi đĩa đúng thời điểm ấy”

TTL điều khiển **logic dữ liệu sống**, còn dữ liệu vật lý được thu hồi khi cơ chế lưu trữ đủ điều kiện. Đĩa không nhất thiết giảm ngay.

### “Dùng DELETE thay TTL để xóa ngay hơn”

DELETE có thể tạo tombstone và cần đồng bộ qua replica. Nó không tự xóa byte vật lý tức thì; số tombstone lớn còn có thể khiến đọc chậm hơn.

### “Nếu TTL mới hết thì phiên bản cũ tự hiện lại”

Trong mô hình hòa giải như Cassandra, phiên bản mới hết TTL vẫn cần che phiên bản cũ để tránh hồi sinh giá trị đã bị thay thế.

### “Write timestamp chính là cột event_time”

Cột thời gian trong primary key hoặc payload thể hiện thời gian nghiệp vụ. Write timestamp là metadata phiên bản do hệ gán hoặc client cung cấp theo cơ chế của sản phẩm.

### “Client có timestamp lớn hơn chắc chắn là trạng thái hợp lệ hơn”

Timestamp lớn có thể do đồng hồ lỗi hoặc replay sai. Hòa giải phiên bản không thay thế bất biến nghiệp vụ, quyền ghi và điều kiện cạnh tranh.

### “Cứ giảm gc_grace_seconds xuống 0 là bớt rác”

Giảm grace có thể thu hẹp cửa sổ bảo vệ trước replica chưa nhận xóa. Nếu repair và topology không đáp ứng điều kiện, dữ liệu cũ có thể hồi sinh. Không dùng cấu hình ví dụ tùy tiện trên production.

### “Qua grace là tombstone phải được thu hồi”

Compaction còn phải xem xét các SSTable và phiên bản liên quan. Grace không phải deadline tuyệt đối để giảm disk usage.

### “Time-series có TTL thì luôn dùng TWCS”

TWCS có thể phù hợp với append-only và retention đồng nhất. Nếu có update cũ, late writes hoặc nhiều TTL khác nhau, hiệu quả cần được kiểm chứng.

### “TTL trên reservation sẽ tự trả lại tồn kho”

TTL không tự chạy một thao tác nghiệp vụ trên bản ghi khác. Cần workflow timeout, retry idempotent, trạng thái reservation và đối soát.

### “Partition key không quan trọng vì dữ liệu cũ tự hết hạn”

Partition lớn hoặc nóng vẫn làm truy vấn và ghi khó mở rộng. TTL và partitioning giải quyết hai câu hỏi riêng nhưng phải thiết kế cùng nhau.

## 15. Checklist trước khi thiết kế bảng có TTL

| Câu hỏi | Minh chứng cần có |
|---|---|
| TTL áp dụng ở cấp nào? | Các cell/bảng và cách UPDATE làm thay đổi thời hạn |
| TTL tính từ thời điểm nào? | Ghi, ingest hay event time; cách xử lý late event |
| Write timestamp ai cấp? | Coordinator/client, đồng bộ đồng hồ, replay và timestamp tương lai |
| Dữ liệu xóa ở phạm vi nào? | Cell, row, range, partition và projection phụ |
| Replica có thể offline bao lâu? | Grace, repair schedule, quy trình node recovery |
| Dữ liệu sống/hết hạn phân bố thế nào? | p50/p95/p99 row/partition, tỷ lệ tombstone |
| Compaction strategy phù hợp? | Append-only hay update cũ, TTL đồng nhất hay khác nhau |
| Đường truy vấn có cụ thể không? | Partition key, clustering range, page size và latency SLO |
| Có kiểm soát hot key không? | Tải/partition, quota, shard và fan-out khi đọc |
| Capacity plan đã tính overhead chưa? | Replica, SSTable cũ, compaction, snapshot, backup |
| Xóa toàn hệ thống được quản lý ra sao? | Index, cache, analytics, export, retention và audit |
| Có thể phục hồi dữ liệu hoặc báo cáo không? | Replay, backfill, checkpoint, restore và đối soát |

## 16. Thử nghiệm TTL và tombstone dưới tải thực

Một proof of concept hữu ích phải mô phỏng **cả vòng đời dữ liệu**, không chỉ tốc độ insert.

1. **Sinh workload có phân bố lệch:** nhiều thiết bị bình thường, vài thiết bị hoặc tenant cực nóng, payload có p99 lớn.
2. **Đo giai đoạn ghi:** throughput, write latency p95/p99, disk, số SSTable, compaction pending.
3. **Đợi một chu kỳ TTL trong môi trường thử nghiệm:** đo read latency và lượng tombstone khi dữ liệu bắt đầu hết hạn.
4. **Theo dõi compaction:** disk usage, số tệp, write amplification, độ trễ đọc sau compaction.
5. **Mô phỏng late event, backfill và retry:** kiểm chứng TTL còn lại và không ghi trùng.
6. **Mô phỏng sự cố replica có kiểm soát:** kiểm chứng quy trình repair và dấu xóa; không cố tình bỏ qua quy tắc an toàn ở production.
7. **So sánh ứng viên:** bucket ngày/giờ, chiến lược compaction, retention class và query range trên cùng dữ liệu đại diện.

Kết quả cần nêu rõ khi nào hệ bắt đầu chậm, dữ liệu hết hạn được dọn ra sao, vùng tải nào quá nóng và đường xử lý sự cố cần thiết. Một benchmark chỉ cho thấy insert nhanh lúc ban đầu chưa đủ để lựa chọn mô hình.

## 17. Bài tập thực hành

### Bài 1 — Phân biệt đồng hồ

Thiết bị đo nhiệt độ lúc 08:00, mất mạng và gửi lúc 09:30. Backend ghi hoàn tất lúc 09:31. Chính sách yêu cầu xóa dữ liệu chi tiết 24 giờ sau thời điểm đo.

Hãy xác định **event time**, **ingestion time**, **write timestamp**, **retention deadline** và thời gian TTL còn lại gần đúng tại lúc ghi. Phân tích việc xử lý nếu dữ liệu đến sau deadline hoặc đồng hồ thiết bị sai.

### Bài 2 — Timestamp và xóa

~~~text
WRITE value="A" @100
WRITE value="B" @300
DELETE           @400
WRITE value="C" @250
~~~

Theo mô hình hòa giải dựa trên timestamp, giải thích vì sao C có thể bị che dù request đến sau DELETE. Nếu một replica chỉ giữ B @300 và chưa nhận tombstone, chuyện gì có thể xảy ra khi tombstone bị thu hồi quá sớm?

### Bài 3 — Truy vấn chậm sau TTL

Một bảng có TTL 48 giờ, nhưng một partition từng chứa hàng triệu sự kiện. Sau vài ngày, API lấy 20 event còn sống chậm hơn trước nhiều lần, đĩa chưa giảm. Hãy giải thích vai trò của **expired cells**, **tombstone scan**, **SSTable**, **compaction** và **partition design**. Đề xuất hai cách cải thiện và nêu đánh đổi khi đọc nhiều ngày.

### Bài 4 — Replica offline và repair

Cụm có ba replica; một replica offline nhiều ngày. Trong thời gian đó, hai replica còn lại nhận DELETE. Hãy mô tả vai trò của **tombstone**, **gc_grace_seconds** và **repair**. Phân tích tại sao giảm grace quá thấp có thể gây hồi sinh dữ liệu.

### Bài 5 — Chọn retention và compaction

Hệ ingest hai loại record:

- Loại A: append-only, TTL 7 ngày, hiếm khi sửa.
- Loại B: thường xuyên cập nhật dữ liệu cũ, retention 2 năm.

Hãy so sánh việc lưu chung một bảng với tách bảng; giải thích khi nào TWCS phù hợp và vì sao backfill/update cũ làm giảm lợi ích.

### Bài 6 — TTL không phải workflow

Một hệ đặt phòng lưu bản ghi giữ chỗ với TTL 10 phút. Khi giữ chỗ hết hạn, số chỗ khả dụng phải được phục hồi, nhưng client có thể gửi lại yêu cầu và job có thể retry.

Hãy mô tả cách xây **idempotent expiration workflow**, điều kiện cập nhật số chỗ và cơ chế đối soát. Giải thích vì sao chỉ đặt TTL 600 giây cho reservation chưa giải quyết được nghiệp vụ.

## 18. Bảng tổng hợp các cơ chế

| Cơ chế | Chức năng chính | Không tự bảo đảm |
|---|---|---|
| **TTL** | Giá trị hết hiệu lực sau thời hạn | Thu hồi đĩa tức thời hoặc chạy hành động nghiệp vụ |
| **Write timestamp** | Ưu tiên phiên bản khi hòa giải | Thứ tự thời gian thực hoặc transaction đúng bất biến |
| **Tombstone** | Ghi nhận xóa để che bản cũ | Mọi replica đã nhận xóa hoặc backup đã biến mất |
| **Replication/repair** | Giúp các bản sao nhận và hòa giải thay đổi | An toàn nếu bỏ lỡ repair quá lâu |
| **Compaction** | Hợp nhất SSTable, thu hồi dữ liệu khi đủ điều kiện | Tất cả tombstone biến mất ngay khi hết grace |
| **Partition/clustering key** | Tổ chức đường đọc và phân bố dữ liệu | TTL, consistency hoặc throughput tự động phù hợp |
| **Retention workflow** | Kiểm soát vòng đời dữ liệu trên toàn hệ thống | Có thể thay bằng một tùy chọn TTL duy nhất |

Điều cốt lõi là **write timestamp quyết định cách hòa giải phiên bản; TTL xác định khi nào giá trị hết hiệu lực; tombstone giữ ý nghĩa xóa trước các bản sao cũ; còn LSM-tree và compaction quyết định lúc nào dữ liệu vật lý có thể được dọn an toàn**. Thiết kế tốt phải xét đồng thời partition key, dữ liệu đến muộn, replication, repair và retention để tránh dữ liệu hồi sinh, truy vấn chậm vì tombstone hoặc ước tính sai dung lượng lưu trữ.
