# Sao chép hai chiều, vòng lặp và rủi ro xung đột

Logical replication của PostgreSQL thường được dùng để chuyển các thay đổi dữ liệu từ một publisher tới một subscriber. Trong mô hình thông thường, một hệ thống là nơi ghi dữ liệu chính và một hoặc nhiều hệ thống nhận bản sao để phục vụ migration, integration, reporting hoặc phân tách workload. Khi hai hệ thống đều cần nhận writes tại chỗ và gửi các thay đổi sang nhau, kiến trúc trở thành **bidirectional logical replication**. Mô hình này mở ra khả năng ghi ở nhiều địa điểm, nhưng đồng thời đặt ra các vấn đề khó hơn: một thay đổi có thể quay lại nguồn qua vòng lặp, hai nơi có thể sửa cùng một row, khóa chính có thể trùng, và các giao dịch độc lập có thể tạo ra trạng thái không nhất quán.

PostgreSQL logical replication cung cấp cơ chế publication/subscription và metadata replication origin để truyền thay đổi. Từ PostgreSQL 16, subscription có tùy chọn origin filtering giúp chỉ nhận các thay đổi có nguồn gốc local, qua đó hỗ trợ ngăn việc chuyển tiếp một transaction đã được nhận từ subscription khác. Tuy nhiên, cơ chế này **không giải quyết xung đột dữ liệu**. Nếu hai node cùng cập nhật một row hoặc cùng chèn một key, apply worker vẫn có thể gặp lỗi và dừng áp dụng thay đổi.

Vì vậy, bidirectional replication cần một thiết kế dữ liệu và quy tắc ghi rõ ràng. Cần xác định node nào được phép ghi vào từng row/tenant/key range, cách tạo khóa không va chạm, cách phát hiện và xử lý conflict, cách giữ schema đồng bộ, và cách phục hồi khi subscription bị dừng. Nếu nghiệp vụ yêu cầu nhiều node cùng ghi đồng thời vào cùng một dữ liệu với tự động hợp nhất, phải có conflict-resolution model rõ ràng hoặc một giải pháp multi-master chuyên dụng; chỉ tạo hai subscriptions không đủ.

Bài học thuộc chương **Sao chép logic** của module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào kiến trúc sao chép hai chiều, ngăn vòng lặp, các loại xung đột, chính sách ownership và quy trình vận hành an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả publisher, publication, subscriber và subscription trong logical replication.
- Thiết kế topology hai node cùng publish/subscribe.
- Giải thích vì sao thay đổi được replicate có thể quay lại node nguồn.
- Dùng origin filtering trên PostgreSQL 16+ để hạn chế forwarding loops.
- Phân biệt loop prevention với conflict detection và conflict resolution.
- Nhận diện duplicate-key, missing-row, constraint và concurrent-update conflicts.
- Thiết kế keyspace/ownership để giảm khả năng hai node ghi cùng row.
- Hiểu giới hạn của native logical replication về DDL, sequences, large objects và schema drift.
- Xây dựng quy trình initial sync, cutover và bật replication hai chiều.
- Theo dõi subscription, apply errors, replication origins và lag.
- Xử lý apply worker bị dừng và đánh giá rủi ro khi skip transaction.
- Thiết kế failover, resubscription, resynchronization và data reconciliation.
- Đánh giá khi nào logical replication hai chiều phù hợp và khi nào cần giải pháp khác.

## 2. Logical replication: publisher và subscriber

Logical replication chuyển các thay đổi ở mức logical row operations thông qua publication/subscription.

~~~text
Publisher database
      |
      | publication
      v
WAL logical decoding
      |
      | replication protocol
      v
Subscriber apply worker
      |
      v
Subscriber tables
~~~

### 2.1. Publication

Publication xác định các bảng và loại thao tác được công bố. Có thể publish INSERT, UPDATE, DELETE và TRUNCATE theo cấu hình. Publication không phải bản sao toàn bộ database object metadata.

### 2.2. Subscription

Subscription kết nối tới publisher, đăng ký publication, tạo replication slot ở phía publisher và chạy apply worker ở phía subscriber. Subscriber nhận thay đổi và áp dụng vào các bảng đích tương ứng.

### 2.3. Initial table synchronization

Khi subscription được tạo với copy_data mặc định, PostgreSQL có thể copy dữ liệu hiện có của các bảng được publish trước khi chuyển sang stream thay đổi liên tục. Cần quản lý thời điểm snapshot, writes trong lúc sync và khả năng conflict.

### 2.4. Apply worker

Apply worker đọc logical change stream và áp dụng các thao tác vào subscriber. Lỗi như duplicate key hoặc thiếu row có thể khiến apply worker dừng cho subscription/table liên quan cho tới khi được xử lý.

### 2.5. Logical replication không phải physical standby

Subscriber là database có các bảng logical tương ứng. Nó không phải bản sao physical của toàn cluster; schema và nhiều global objects phải được quản lý riêng.

## 3. Sao chép một chiều và hai chiều

Trong mô hình một chiều, một publisher gửi thay đổi sang subscriber:

~~~text
Node A (writes)
      |
      v
Node B (read copy)
~~~

Trong mô hình hai chiều, cả hai node đều có publication và subscription:

~~~text
       Publication A
Node A ---------------> Node B
  ^                       |
  |                       |
  +-----------------------+
       Publication B
~~~

### 3.1. Mỗi node vừa publish vừa subscribe

Node A publish thay đổi local để B nhận. Node B cũng publish thay đổi local để A nhận.

### 3.2. Mỗi hướng là một replication stream riêng

A→B và B→A có subscription, slot, apply worker, origin và lag riêng. Một hướng khỏe không chứng minh hướng còn lại khỏe.

### 3.3. Hai chiều không tự tạo một transaction toàn cục

Một transaction commit ở A rồi được apply sang B sau một khoảng trễ. Không có distributed commit/consensus tự động giữa hai databases chỉ vì có subscriptions ngược chiều.

### 3.4. Hai node có thể ghi đồng thời

Nếu A và B cùng cho phép writes vào cùng bảng/keyspace, các thay đổi có thể va chạm. Cần quy tắc ownership và conflict policy trước khi đưa vào production.

### 3.5. Bidirectional không đồng nghĩa multi-master hoàn chỉnh

Native logical replication cung cấp transport/apply primitives. Nó không cung cấp đầy đủ conflict resolution, global uniqueness, distributed locking hoặc transaction coordination.

## 4. Vì sao xuất hiện replication loop?

Giả sử A chèn một row. A publish transaction tới B. B apply transaction đó. Nếu B publish cả thay đổi vừa nhận sang A, A có thể nhận lại transaction từ chính mình qua một đường khác.

~~~text
A local INSERT
    |
    v
A publishes to B
    |
    v
B applies INSERT
    |
    v
B publishes applied change to A
    |
    v
A receives the same logical change again
~~~

### 4.1. Một thay đổi có thể bị chuyển tiếp

Trong topology nhiều node, một transaction có thể đi qua nhiều subscriptions. Nếu không lọc nguồn gốc, một node có thể nhận lại thay đổi mà nó đã khởi tạo.

### 4.2. Hậu quả không chỉ là duplicate INSERT

Vòng lặp có thể gây duplicate-key errors, apply worker failures, tăng WAL/network load, repeated updates hoặc chuỗi lỗi khó điều tra.

### 4.3. Replication origin

PostgreSQL theo dõi nguồn gốc của transactions được áp dụng qua logical replication. Metadata origin giúp nhận biết một thay đổi bắt nguồn từ local transaction hay từ một subscription khác.

### 4.4. Origin filtering

PostgreSQL 16+ hỗ trợ tùy chọn origin trên subscription. Với `origin = none</BT>, subscription chỉ nhận thay đổi có nguồn gốc local ở publisher và bỏ qua các thay đổi đã được replicate từ một origin khác.

### 4.5. Loop prevention không phải conflict resolution

Origin filtering ngăn một transaction bị chuyển tiếp vòng lại theo topology phù hợp. Nó không quyết định hai transaction local độc lập sửa cùng row thì transaction nào thắng.

## 5. Bidirectional topology trên PostgreSQL 16+

Một thiết kế hai node đơn giản có thể tạo publication ở cả A và B, sau đó mỗi node subscribe publication của peer với origin filtering phù hợp.

~~~text
Node A                                      Node B
+----------------------+          +----------------------+
| publication pub_a    | -------> | subscription sub_ba  |
| subscription sub_ab  | <------- | publication pub_b    |
| local writes         |          | local writes         |
+----------------------+          +----------------------+
       origin=none on each subscription
~~~

### 5.1. Tạo publication trên A

~~~sql
CREATE PUBLICATION pub_a
FOR TABLE public.customer, public.order_header
WITH (publish = 'insert, update, delete');
~~~

### 5.2. Tạo publication trên B

~~~sql
CREATE PUBLICATION pub_b
FOR TABLE public.customer, public.order_header
WITH (publish = 'insert, update, delete');
~~~

Các bảng cần có schema tương thích ở cả hai phía. Publication không tự tạo schema.

### 5.3. Subscription trên B nhận từ A

~~~sql
CREATE SUBSCRIPTION sub_ba
CONNECTION 'host=node-a.example.internal dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION pub_a
WITH (origin = none);
~~~

### 5.4. Subscription trên A nhận từ B

~~~sql
CREATE SUBSCRIPTION sub_ab
CONNECTION 'host=node-b.example.internal dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION pub_b
WITH (origin = none);
~~~

Ví dụ này minh họa PostgreSQL 16+; connection secrets nên được quản lý theo policy, không hard-code password trong scripts hoặc source control.

### 5.5. Kiểm tra version trước khi dùng

Tùy chọn subscription origin có từ PostgreSQL 16. Trên các phiên bản cũ, không giả định có cơ chế native tương đương. Không triển khai reciprocal subscriptions một cách máy móc khi chưa có loop-prevention design đã kiểm chứng.

## 6. Ý nghĩa của origin = none

Origin filtering phân biệt transaction được tạo local trên publisher với transaction đã được nhận từ một replication origin.

### 6.1. Transaction local trên A

A thực hiện INSERT local. Khi A publish transaction này, origin của thay đổi là local. B nhận và apply.

### 6.2. B apply transaction từ A

B ghi nhận origin của transaction đến từ A. Thay đổi đã được replicate, không phải transaction do B tạo local.

### 6.3. B publish sang A

Nếu publication của B chứa thay đổi này, subscription trên A nhận từ B với origin filtering none sẽ lọc transaction có origin remote, tránh chuyển tiếp lại transaction bắt nguồn từ A.

### 6.4. Transaction local trên B vẫn được truyền

Một INSERT do ứng dụng thực hiện trực tiếp trên B có local origin. Subscription A nhận từ B với origin filtering none có thể nhận và apply thay đổi đó.

### 6.5. Cấu hình phải đối xứng và có kiểm chứng

Đặt origin filtering ở từng subscription có khả năng nhận lại forwarded changes. Kiểm tra behavior thực tế qua lab và metrics; không dựa chỉ vào tên option.

## 7. Giới hạn của origin filtering

Origin filtering giúp ngăn loops nhưng không tạo ra một distributed database có conflict resolution.

### 7.1. Không ngăn concurrent local writes

Nếu A và B cùng cập nhật row id=10, mỗi transaction đều có local origin trên node khởi tạo. Cả hai có thể được truyền và xung đột khi apply ở peer.

### 7.2. Không tạo global uniqueness

Hai node có thể tự tạo cùng một primary key. Origin filtering không cấp phát key toàn cục.

### 7.3. Không giải quyết ordering giữa các streams

Mỗi subscription có stream/apply order riêng. Không có một thứ tự toàn cục tự động cho các transactions phát sinh độc lập ở hai nodes.

### 7.4. Không đồng bộ DDL

ALTER TABLE trên A không tự động được thực thi trên B. Schema drift có thể làm apply fail hoặc làm dữ liệu hiểu khác nhau.

### 7.5. Không thay application ownership

Ứng dụng vẫn cần biết node nào được phép ghi row/tenant nào, hoặc có quy tắc xử lý concurrent changes.

## 8. Các loại conflict phổ biến

| Loại conflict | Ví dụ | Hậu quả thường gặp |
|---|---|---|
| Duplicate key | Hai node INSERT cùng id | Unique violation |
| Missing row | DELETE/UPDATE ở node nhận không thấy row | Apply error |
| Concurrent update | Hai node sửa cùng row | Một thay đổi apply vào trạng thái đã đổi hoặc conflict |
| Unique constraint | Hai row khác id nhưng cùng email | Unique violation |
| Foreign key | Row tham chiếu chưa tồn tại | FK violation |
| Check/exclusion constraint | Dữ liệu từ peer vi phạm constraint | Apply error |
| Schema mismatch | Column/type không khớp | Decode/apply error |
| Truncate interaction | TRUNCATE không phù hợp publication/relationship | Dữ liệu bị xóa rộng hoặc apply failure |

### 8.1. INSERT duplicate key

A và B cùng chèn customer id=500. Khi thay đổi từ A tới B apply, B đã có key 500 từ local write nên unique constraint fail.

### 8.2. UPDATE row đã thay đổi

A cập nhật status='paid', B cập nhật status='cancelled'. Khi stream đến, mỗi nơi có thể áp dụng thay đổi lên row state khác nhau; native apply không tự hợp nhất hai giá trị.

### 8.3. DELETE row không tồn tại

A xóa row trong khi B đã xóa local hoặc chưa có row do sync/filter. Apply DELETE có thể không tìm thấy row mục tiêu theo expected identity.

### 8.4. Unique key khác nhau nhưng business key trùng

A tạo user id=101 với email x@example.com; B tạo user id=202 cùng email. Primary keys không trùng nhưng unique email constraint vẫn xung đột.

### 8.5. Constraint errors dừng apply

Khi apply worker gặp lỗi transaction, worker có thể dừng xử lý subscription. Các transaction sau đó không thể tiến tiếp qua cùng stream cho đến khi lỗi được xử lý.

## 9. PostgreSQL xử lý conflict như thế nào?

Native logical replication không tự chọn “last write wins” hoặc merge fields khi có xung đột. Subscriber thực hiện các thao tác theo stream; constraint/apply errors được báo và cần operator/application xử lý.

### 9.1. Apply worker có thể dừng

Một lỗi ở transaction có thể làm apply worker dừng xử lý subscription. Các transaction sau đó không thể tiến tiếp qua cùng stream cho đến khi lỗi được xử lý.

### 9.2. Không tự động retry mãi sẽ sửa được conflict

Nếu row/key/constraint vẫn ở trạng thái xung đột, retry thường gặp lại lỗi. Cần hiểu dữ liệu hiện tại và quyết định đúng.

### 9.3. Conflict không phải lúc nào cũng có thể giải bằng DELETE

Xóa row xung đột để apply tiếp có thể làm mất dữ liệu hợp lệ của node nhận. Cần xác định business owner và quy tắc merge.

### 9.4. Log là nguồn chẩn đoán quan trọng

PostgreSQL log thường cho biết duplicate key, relation, constraint và apply context. Ghi nhận LSN/transaction context để đối chiếu.

### 9.5. Subscriber data có thể đã diverge

Sau khi một transaction fail, các node có thể tiếp tục nhận writes local. Divergence tăng theo thời gian nếu không dừng writes hoặc có reconciliation plan.

## 10. Xây dựng quy tắc ownership dữ liệu

Cách hiệu quả nhất để giảm conflict là giới hạn node nào được phép ghi từng phần dữ liệu.

### 10.1. Single-writer per table

Một số bảng chỉ cho phép A ghi; B chỉ đọc bản sao. Những bảng khác có thể do B sở hữu.

### 10.2. Single-writer per tenant

Tenant được gán về một home region/node. Chỉ node owner nhận writes cho tenant đó; thay đổi được replicate sang peer để đọc.

### 10.3. Keyspace partitioning

A tạo keys trong một range/prefix, B tạo keys trong range/prefix khác. Ví dụ A dùng node prefix 1, B dùng node prefix 2 hoặc dùng UUID.

### 10.4. Ownership transfer

Khi tenant chuyển từ A sang B, cần protocol: freeze writes ở A, đồng bộ thay đổi, đổi owner, xác nhận B đã catch up rồi mới mở writes ở B.

### 10.5. Enforce ownership trong ứng dụng và database

Chỉ document policy là chưa đủ. Có thể enforce qua service routing, role privileges, row-level security, stored procedures hoặc validation triggers phù hợp. Đảm bảo replication apply không bị policy local chặn ngoài dự kiến.

## 11. Primary keys và global uniqueness

Bidirectional nodes cần tạo identifiers không va chạm.

### 11.1. UUID

UUID ngẫu nhiên hoặc UUID theo chuẩn phù hợp giảm đáng kể nguy cơ trùng key giữa nodes. Vẫn cần unique constraint và xử lý collision dù xác suất thấp.

### 11.2. Node-specific ranges

Mỗi node dùng sequence range riêng, ví dụ A cấp số chẵn/B cấp số lẻ hoặc các block không giao nhau. Phải có allocation policy và xử lý khi node mất/đổi role.

### 11.3. Composite keys

Có thể đưa node/tenant/region identifier vào khóa chính, ví dụ (origin_node, local_id). Mọi foreign keys và API references phải dùng đủ components.

### 11.4. Sequence không được replicate như table data

Logical replication không tự đồng bộ sequence state theo cách đảm bảo global uniqueness. Hai node có sequence cùng start/increment có thể cấp cùng ID.

### 11.5. Business keys vẫn có thể trùng

Email, username, invoice number hoặc external reference có thể unique toàn hệ thống. Phải có central allocation, ownership hoặc conflict-resolution policy cho các keys đó.

## 12. Update conflict và merge semantics

Một row được sửa độc lập trên hai node là vấn đề nghiệp vụ, không chỉ vấn đề kỹ thuật.

### 12.1. Last-write-wins

Có thể xây dựng rule chọn phiên bản theo timestamp/version, nhưng timestamp đồng hồ có thể lệch và thứ tự commit trên hai nodes không đồng nhất. Cần tie-breaker deterministic và audit.

### 12.2. Field-level merge

Nếu A đổi phone còn B đổi address, có thể merge từng field nếu business semantics cho phép. Nhưng hai bên cùng đổi một field vẫn cần rule.

### 12.3. Version column

Một cột version/updated_at giúp phát hiện stale updates hoặc xác định thứ tự theo policy. Nó không tự giải quyết conflict nếu version không được cấp phát globally/deterministically.

### 12.4. Append-only events

Thay vì cùng update một row, có thể lưu events bất biến với unique event IDs rồi derive state. Cách này giảm một số overwrite conflicts nhưng cần idempotency và ordering model.

### 12.5. CRDT hoặc domain-specific merge

Một số domain có thể dùng commutative operations (counter/set/mergeable state). Chỉ dùng khi phép hợp nhất phù hợp nghiệp vụ và đã xác định semantics; không biến mọi bảng quan hệ thành CRDT tự động.


## 13. Replica identity và khả năng apply UPDATE/DELETE

Logical replication cần xác định row nào trên subscriber tương ứng với row được UPDATE hoặc DELETE ở publisher. PostgreSQL dùng replica identity để xác định row key cho các thao tác này.

### 13.1. Primary key mặc định

Nếu bảng có primary key, primary key thường là replica identity mặc định. Subscriber cần có key tương ứng để tìm row cần thay đổi.

### 13.2. REPLICA IDENTITY USING INDEX

Có thể dùng một unique index phù hợp, không partial và đáp ứng các điều kiện của PostgreSQL, làm replica identity:

~~~sql
ALTER TABLE public.customer
REPLICA IDENTITY USING INDEX customer_replica_key;
~~~

Index cần thỏa các yêu cầu về uniqueness, NOT NULL và loại index được hỗ trợ.

### 13.3. REPLICA IDENTITY FULL

Nếu không có key phù hợp, có thể dùng FULL để ghi nhận toàn bộ row cũ trong WAL logical decoding:

~~~sql
ALTER TABLE public.audit_item REPLICA IDENTITY FULL;
~~~

Cách này có thể làm WAL lớn hơn và việc tìm row ở subscriber tốn kém hơn, nhất là bảng lớn.

### 13.4. Không có replica identity phù hợp

Bảng không có replica identity phù hợp có thể publish INSERT, nhưng UPDATE/DELETE sẽ không được hỗ trợ theo cách cần thiết. Kiểm tra cấu hình trước khi bật publication hai chiều.

### 13.5. Identity phải đồng nhất ở cả hai phía

Nếu A và B có khóa/replica identity khác nhau, apply có thể thất bại hoặc xác định row không như mong đợi. Schema contract cần được quản lý chung.

## 14. Publication scope, row filters và column lists

Publication xác định dữ liệu nào được gửi đi. Trong bidirectional topology, scope phải được thiết kế để tránh gửi những rows mà node không có quyền sở hữu hoặc không nên chuyển tiếp.

### 14.1. Publish theo danh sách bảng

~~~sql
CREATE PUBLICATION pub_orders
FOR TABLE public.orders, public.order_items
WITH (publish = 'insert, update, delete');
~~~

Đây là cách rõ ràng cho một tập bảng nhỏ. Bảng mới cần được thêm có chủ đích.

### 14.2. FOR ALL TABLES

Publication có thể publish tất cả bảng đủ điều kiện, nhưng phạm vi rộng làm tăng rủi ro gửi nhầm dữ liệu, bảng hệ thống/không phù hợp hoặc bảng có semantics không hỗ trợ multi-writer. Dùng khi inventory và schema governance đủ chặt.

### 14.3. Row filters

PostgreSQL hỗ trợ row filters trên publication trong các phiên bản hiện đại. Filter có thể giới hạn rows được gửi, ví dụ chỉ publish tenant thuộc region:

~~~sql
CREATE PUBLICATION pub_region_a
FOR TABLE public.orders
WHERE (region_id = 1);
~~~

Row filters là bộ lọc replication, không phải security boundary thay thế RLS/IAM.

### 14.4. Column lists

Column lists có thể giới hạn cột được publish. Subscriber phải có các cột phù hợp với thao tác và schema. Primary/replica identity columns cần được xem xét theo rules của version.

### 14.5. Filter hai chiều phải được thiết kế nhất quán

Nếu A publish tenant 1 và B publish tenant 2, các filter/ownership rules phải bảo đảm mỗi row chỉ có một writer authoritative. Không để một row được local-write ở cả hai nơi chỉ vì hai filter không loại trừ nhau.

## 15. Row ownership bằng publication filters

Một pattern là phân chia dữ liệu theo tenant/region để mỗi node ghi tập rows riêng, nhưng cả hai vẫn nhận bản sao của nhau.

~~~text
Node A owns region_id = 1
Node B owns region_id = 2

A -- publish region 1 --> B
B -- publish region 2 --> A
~~~

### 15.1. Mỗi node có thể publish rows local

A chỉ publish rows do A sở hữu; B chỉ publish rows do B sở hữu. Khi A nhận rows từ B, origin filtering ngăn chúng bị publish vòng lại.

### 15.2. Dữ liệu nhận về có thể read-only theo policy

Ứng dụng có thể cho phép đọc mọi regions nhưng chỉ cho ghi region thuộc node. Enforce ownership ở service/DB layer.

### 15.3. Foreign keys xuyên vùng

Một row thuộc tenant 1 có thể tham chiếu tenant 2. Nếu hai rows được replicate khác thời điểm hoặc filter khác nhau, FK có thể fail. Cần mô hình dữ liệu và ordering phù hợp.

### 15.4. Row filter không giải quyết concurrent ownership change

Khi chuyển tenant từ A sang B, cần freeze writes và chuyển ownership có kiểm soát. Chỉ sửa filter không bảo đảm không có writes đang bay.

### 15.5. Global tables

Bảng country codes, product catalog hoặc shared configuration có thể được ghi tại một node duy nhất và replicate một chiều. Không nhất thiết phải publish hai chiều mọi bảng.

## 16. Partitioned tables trong logical replication hai chiều

Partitioning có thể hỗ trợ phân chia workload/keyspace, nhưng cần chú ý cách publication đại diện partition root hoặc leaf tables.

### 16.1. Publish partition root

Với publish_via_partition_root phù hợp, thay đổi từ partitions có thể được gửi như thay đổi trên root table. Điều này giúp subscriber có cấu trúc partition tương ứng theo cách đã thiết kế.

### 16.2. Publish leaf partitions

Có thể publish partition riêng, nhưng topology và mapping cần thống nhất. Một row chuyển partition do UPDATE partition key có thể được biểu diễn thành DELETE/INSERT tùy behavior.

### 16.3. Partition ownership

Có thể phân vùng theo region/tenant để mỗi node sở hữu một số partitions. Tuy nhiên, replication apply và table identity cần được thử với schema/partition layout cụ thể.

### 16.4. Không giả định partition pruning đồng nghĩa replication filtering

Partitioning là cách lưu trữ/route rows trong database. Publication filters và row ownership là cơ chế khác; cần cấu hình rõ.

### 16.5. Schema changes trên partitions

Tạo/drop/attach/detach partitions là DDL và không tự được logical replication chuyển sang peer. Thực hiện migration đồng bộ theo quy trình schema governance.

## 17. TRUNCATE và các thao tác có phạm vi lớn

TRUNCATE là thao tác đặc biệt vì nó tác động toàn bảng thay vì một row cụ thể.

### 17.1. Publication có thể bật publish TRUNCATE

Nếu publication bao gồm truncate, thao tác TRUNCATE ở publisher có thể được chuyển tới subscriber. Kiểm tra publish options trước khi dùng.

### 17.2. Rủi ro trong bidirectional topology

Một node có thể TRUNCATE bảng trong khi peer có local rows hợp lệ chưa được gửi đi. Khi thao tác được apply, các rows đó có thể bị xóa khỏi peer.

### 17.3. TRUNCATE không phải row-level conflict

Origin filtering ngăn transaction quay vòng, nhưng không ngăn TRUNCATE xóa rows do node khác sở hữu nếu publication scope cho phép.

### 17.4. Không publish TRUNCATE nếu semantics không an toàn

Có thể chỉ publish INSERT/UPDATE/DELETE cho một số bảng, hoặc quản lý truncate qua maintenance window có freeze/coordination.

### 17.5. Foreign keys và cascades

TRUNCATE có quy tắc riêng về referenced tables và CASCADE. Kiểm tra schema trên cả hai phía và không dùng CASCADE như cách sửa conflict.

## 18. Những đối tượng không tự được logical replication đồng bộ

Logical replication tập trung vào row changes của các bảng đã publish. Nhiều loại metadata và object cần quản lý riêng.

| Đối tượng | Native logical replication |
|---|---|
| Table row changes | Có, nếu table được publish |
| DDL/schema changes | Không tự replicate |
| Sequence state | Không tự replicate như row changes |
| Roles/global privileges | Không |
| Tablespaces | Không |
| Large objects | Không được replicate như table rows |
| Views/functions/triggers | Definition không tự replicate |
| Materialized view contents | Không tự đồng bộ như bảng được publish |
| Extensions/binaries | Không |
| Server configuration | Không |

### 18.1. DDL phải có schema migration pipeline

Dùng migration tool hoặc deployment process để áp dụng cùng schema version ở hai node. Thứ tự migration cần tương thích với stream đang chạy.

### 18.2. Sequences cần allocation policy

Đừng để hai nodes dùng sequence cùng start/increment cho cùng một keyspace. Dùng UUID, disjoint ranges hoặc central key allocation.

### 18.3. Roles và grants cần IaC/configuration

Quản lý roles, ownership và grants bằng scripts/migrations riêng. Không nghĩ rằng subscription tự tạo login roles.

### 18.4. Large objects cần giải pháp riêng

Nếu ứng dụng dùng PostgreSQL large objects, cần kiểm tra cách backup/replicate chúng. Có thể chuyển nội dung sang object storage hoặc một bảng bytea nếu phù hợp domain.

### 18.5. Trigger behavior phải được hiểu

Logical apply dùng replication role semantics; triggers thông thường không nhất thiết chạy như local DML. Trigger được cấu hình REPLICA/ALWAYS có behavior khác. Tránh trigger side effects làm tạo thêm writes/loops.

## 19. Schema evolution và rollout hai chiều

Schema drift là nguyên nhân phổ biến khiến logical apply fail hoặc dữ liệu hai node có semantics khác nhau.

### 19.1. Expand-and-contract

Một migration an toàn thường thêm cột nullable/compatible trước, deploy ứng dụng tương thích cả hai schema, backfill, chuyển đọc/ghi, rồi mới loại bỏ cột cũ sau khi mọi node đã đồng bộ.

### 19.2. Thứ tự DDL

Áp dụng schema change lên subscriber trước khi publisher bắt đầu gửi rows cần column mới, hoặc dùng một rollout sequence đã thử. DDL không tự được replicate.

### 19.3. Type changes

Đổi type, rename/drop column hoặc đổi collation có thể khiến apply không tương thích. Chia migration thành bước additive và destructive riêng.

### 19.4. Publication refresh

Khi thêm bảng vào publication, subscription có thể cần REFRESH PUBLICATION để phát hiện bảng mới. Việc refresh có thể kích hoạt table synchronization tùy options.

### 19.5. Schema version check

Ghi schema migration version trên từng node và alert nếu lệch. Không mở writes hai chiều nếu schema chưa đạt compatibility contract.

## 20. Initial sync cho hai node

Khởi tạo hai chiều là giai đoạn nhạy cảm nhất vì hai bên có thể đã có dữ liệu và writes độc lập.

### 20.1. Không bật copy_data hai chiều một cách mù quáng

Nếu cả A và B đã có cùng rows, hai initial table sync có thể cố insert các keys trùng. Apply conflict có thể xuất hiện ngay khi khởi tạo.

### 20.2. Chọn baseline

Quyết định một nguồn canonical cho từng bảng/tenant hoặc dùng snapshot được tạo từ một trạng thái nhất quán. Ghi rõ snapshot/LSN và ownership.

### 20.3. Freeze hoặc fence writes trong bootstrap

Với bảng cần baseline chung, có thể tạm dừng writes trong thời gian snapshot/copy và chuyển tiếp. Nếu không thể freeze, cần một protocol capture/catch-up được thiết kế kỹ.

### 20.4. Preload rồi dùng copy_data=false

Một pattern là nạp dữ liệu baseline vào subscriber bằng backup/ETL đã xác minh, sau đó tạo subscription với copy_data=false và bắt đầu từ replication slot/consistent point phù hợp. Cần đồng bộ LSN/slot đúng; không chỉ bỏ qua initial copy tùy tiện.

### 20.5. Bật chiều thứ hai sau khi kiểm chứng chiều đầu

Đưa một hướng vào trạng thái ổn định, xác minh origin behavior, row ownership và conflict monitoring, sau đó mới bật chiều còn lại theo kế hoạch. Với bidirectional active writes, ownership phải có hiệu lực trước khi mở cả hai.

## 21. Replication slots và WAL retention trong logical replication

Mỗi subscription thường dùng logical replication slot ở publisher để giữ WAL cần cho decoding/apply.

### 21.1. Slot trên publisher

Subscription B nhận từ A sẽ có slot tương ứng trên A. Subscription A nhận từ B có slot riêng trên B.

### 21.2. Slot inactive có thể giữ WAL

Nếu subscriber ngừng hoạt động, slot có thể giữ WAL và làm tăng disk usage trên publisher. Theo dõi slot activity và retained WAL.

### 21.3. Hai hướng có failure độc lập

A→B có thể hoạt động trong khi B→A dừng. Monitor từng slot/subscription và alert theo hướng.

### 21.4. max_replication_slots và max_wal_senders

Cần đủ slots/senders cho subscriptions, physical standbys, backup tools và maintenance. Tính riêng từng node.

### 21.5. Slot bị mất

Nếu slot bị drop hoặc publisher mất WAL cần thiết, subscriber có thể không tiếp tục từ vị trí cũ. Có thể cần resync/reseed hoặc tạo slot mới sau khi xác định consistency boundary.



## 22. Theo dõi subscription và apply workers

Logical replication có các statistics views giúp quan sát mỗi subscription và worker. Cần theo dõi riêng từng chiều A→B và B→A.

### 22.1. pg_stat_subscription

Trên subscriber, query:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

View này cho biết subscription workers và tiến độ nhận message. Cột có thể khác theo PostgreSQL version.

### 22.2. Subscription không có worker

Nếu pid NULL hoặc không có row phù hợp, subscription có thể disabled, worker chưa khởi chạy, hoặc đang ở trạng thái table synchronization khác. Kiểm tra pg_subscription và logs.

### 22.3. pg_stat_subscription_stats

Các PostgreSQL versions có view này cung cấp counters như apply_error_count và sync_error_count:

~~~sql
SELECT
    subname,
    apply_error_count,
    sync_error_count,
    stats_reset
FROM pg_stat_subscription_stats
ORDER BY subname;
~~~

Counters cần được đọc cùng server logs; reset stats không xóa nguyên nhân lỗi.

### 22.4. pg_replication_origin_status

Trên subscriber, view này cho biết tiến độ theo replication origin:

~~~sql
SELECT
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status
ORDER BY external_id;
~~~

Đây là thông tin hữu ích để đối chiếu remote progress với local WAL position.

### 22.5. pg_replication_slots trên publisher

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Một số cột chỉ có trên phiên bản mới hơn. Dùng catalog phù hợp với major version đang chạy.

## 23. Monitoring lag và freshness

Bidirectional replication có ít nhất hai lag directions và mỗi direction có thể có các table sync workers riêng.

### 23.1. Last message receipt

So sánh last_msg_receipt_time với thời điểm hiện tại để phát hiện subscription ngừng nhận messages. Khi workload idle, thời điểm cũ không nhất thiết là lỗi; cần heartbeat hoặc synthetic writes để đo freshness.

### 23.2. Latest end LSN

Theo dõi latest_end_lsn và latest_end_time theo từng subscription. Đây là mốc stream gần nhất được báo, không phải bằng chứng mọi bảng đã được apply đầy đủ.

### 23.3. Origin progress

remote_lsn cho biết tiến độ remote theo origin; đối chiếu với local_lsn và publisher-side WAL positions.

### 23.4. Apply error counters

Tăng apply_error_count hoặc sync_error_count là dấu hiệu cần xem log và trạng thái worker. Không chỉ alert theo worker PID.

### 23.5. Business freshness

Một subscription có thể khỏe nhưng một bảng quan trọng không được publish hoặc bị row filter loại. Kiểm tra dữ liệu nghiệp vụ bằng heartbeat rows hoặc canary records theo policy.

## 24. Xử lý apply worker bị dừng

Khi subscription dừng do conflict, cần dừng việc đoán và xác định chính xác transaction, row và constraint.

### 24.1. Đọc PostgreSQL logs

Tìm duplicate key, missing row, foreign key, check constraint, relation/schema mismatch và transaction context. Lưu LSN/commit LSN nếu log cung cấp.

### 24.2. Xác định hướng bị lỗi

Phân biệt subscription A→B hay B→A. Kiểm tra publisher, subscriber, slot và origin tương ứng. Không nhầm lỗi một chiều với toàn hệ thống.

### 24.3. Chụp trạng thái dữ liệu hai bên

Lấy các rows liên quan từ A và B, kèm primary key, version, timestamps và business metadata. Lưu evidence trước khi sửa.

### 24.4. Quiesce writes nếu divergence đang tăng

Nếu conflict có thể tiếp tục lặp hoặc tạo thêm divergence, tạm dừng writes liên quan hoặc disable subscription theo runbook. Đừng để các nodes tiếp tục tạo dữ liệu phụ thuộc vào row đang tranh chấp.

### 24.5. Sửa theo business rule rồi resume

Chọn canonical state hoặc merge theo quy tắc đã phê duyệt. Sau khi sửa, enable subscription và xác nhận worker apply tiếp qua LSN lỗi, đồng thời kiểm tra chiều ngược.

## 25. Skip transaction: chỉ dùng như biện pháp có kiểm soát

Một số PostgreSQL versions hỗ trợ bỏ qua transaction đang gây lỗi bằng thao tác ALTER SUBSCRIPTION SKIP với commit LSN cụ thể. Đây là công cụ vận hành nguy hiểm nếu dùng thay cho conflict resolution.

### 25.1. Khi nào cân nhắc skip?

Chỉ khi transaction đã được điều tra, biết rõ tác động, có quyết định chấp nhận bỏ qua và có kế hoạch reconcile dữ liệu bị thiếu. Không skip chỉ để làm worker chạy lại.

### 25.2. Skip làm mất một transaction ở subscriber

Publisher đã commit transaction đó. Bỏ qua có nghĩa subscriber sẽ không có các thay đổi trong transaction; những transaction sau có thể tiếp tục apply.

### 25.3. Transaction có thể cập nhật nhiều bảng

Bỏ qua toàn transaction có thể làm mất nhiều row changes và phá business invariants/foreign keys. Xem toàn bộ transaction scope trước khi quyết định.

### 25.4. Version và syntax

Cú pháp/availability của subscription skip phụ thuộc PostgreSQL version. Xác nhận tài liệu đúng major version và commit LSN của transaction đang lỗi trước khi thực hiện.

### 25.5. Reconcile sau skip

Ghi transaction/LSN đã bỏ qua, dữ liệu bị ảnh hưởng, cách sửa ở cả hai nodes và kết quả kiểm tra. Skip không tự tạo một state nhất quán.

## 26. Conflict resolution runbook

Một quy trình xử lý conflict có thể theo thứ tự:

1. Ghi incident ID, subscription direction và timestamp.
2. Xác định transaction/LSN và relation gây lỗi.
3. Chụp rows liên quan ở publisher và subscriber.
4. Xác định row owner và business source of truth.
5. Chọn merge rule: giữ A, giữ B, merge fields, hoặc tái tạo từ event log.
6. Tạm dừng writes liên quan và các subscription directions cần thiết.
7. Áp dụng sửa chữa có audit trên các nodes theo kế hoạch.
8. Nếu phải skip, ghi rõ transaction bị bỏ và dữ liệu cần reconcile.
9. Resume subscription/apply workers.
10. Xác nhận LSN tiến lên và cả hai directions khỏe.
11. Chạy business invariants, duplicate checks và foreign-key checks.
12. Ghi root cause và thay đổi ownership/schema để ngăn tái diễn.

### 26.1. Không dùng “node mới hơn” làm rule mặc định

Timestamp có thể lệch; một update mới hơn về thời gian có thể dựa trên state cũ hơn. Dùng version/ownership/domain rule có thể giải thích.

### 26.2. Không sửa một phía mà quên chiều ngược

Local repair transaction có thể được publish ngược sang peer. Kiểm soát subscriptions và writes để repair không tạo thêm conflict.

### 26.3. Audit trước khi xóa

Nếu quyết định xóa một row trùng, lưu snapshot/export và lý do. DELETE có thể lan sang peer sau khi replication được bật lại.

### 26.4. Xử lý idempotency

Application events và reconciliation jobs cần event IDs/checkpoints để retry mà không tạo duplicate side effects.

### 26.5. Kiểm tra dữ liệu sau khi worker chạy tiếp

Worker running chỉ chứng minh apply tiếp tục; cần xác nhận dữ liệu đúng về mặt nghiệp vụ.

## 27. Tạm dừng và bật lại subscriptions

Subscription có thể disable/enable để bảo trì hoặc xử lý sự cố.

~~~sql
ALTER SUBSCRIPTION sub_ab DISABLE;
ALTER SUBSCRIPTION sub_ab ENABLE;
~~~

### 27.1. Disable một hướng không dừng hướng còn lại

Nếu A→B bị disable, B→A có thể vẫn tiếp tục. Điều này có thể làm state diverge thêm nếu hai bên vẫn ghi cùng rows.

### 27.2. Slot có thể vẫn giữ WAL

Khi subscription disabled, logical replication slot ở publisher có thể tiếp tục giữ WAL. Theo dõi disk và slot retention trong thời gian maintenance.

### 27.3. Không drop slot tùy tiện

Drop slot có thể làm mất khả năng tiếp tục từ vị trí cũ. Nếu cần drop, xác định rõ sẽ resync/recreate subscription như thế nào.

### 27.4. Bật lại sau khi schema sẵn sàng

Đảm bảo tables/columns/types/constraints phù hợp ở cả hai nodes trước khi enable.

### 27.5. Kiểm tra catch-up

Theo dõi slot confirmed_flush_lsn, subscription progress, apply errors và business freshness tới khi stream bắt kịp.

## 28. Resynchronization khi divergence lớn

Nếu hai nodes đã diverge nhiều hoặc slot/WAL bị mất, sửa từng conflict có thể không thực tế.

### 28.1. Chọn authoritative dataset

Xác định node/source of truth theo từng table/tenant/key range. Không chọn một node chỉ vì nó có nhiều rows hơn.

### 28.2. Tạm dừng writes

Freeze ownership scope trong thời gian snapshot/reseed để tránh dữ liệu tiếp tục thay đổi khi copy.

### 28.3. Tạo consistent baseline

Dùng logical dump/ETL snapshot hoặc phương pháp copy phù hợp. Ghi snapshot boundary và cách bắt đầu stream sau snapshot.

### 28.4. Recreate subscription/slot có kiểm soát

Nếu cần tạo slot mới, đồng bộ snapshot và replication start point. Không dùng copy_data=false nếu không có baseline chứng minh subscriber đã đồng bộ tới đúng điểm.

### 28.5. Validate rồi mở writes

Kiểm tra row counts/checksums/business invariants, ownership, unique keys và origin filtering. Mở writes theo từng vùng sau khi xác nhận.

## 29. Initial synchronization và writes đồng thời

Initial table synchronization có thể chạy theo worker riêng. Trong bidirectional topology, việc cả hai phía copy dữ liệu đồng thời cần được quản lý chặt.

### 29.1. Copy data từ A sang B

Nếu B đã có rows tạo local cùng primary keys, initial copy có thể fail duplicate key. Dùng baseline hoặc ownership để tránh collision.

### 29.2. Copy data từ B sang A

Nếu bật chiều ngược ngay lập tức, A cũng có thể nhận các rows mà nó đã có hoặc đang thay đổi. Không mặc định hai initial sync sẽ hợp nhất an toàn.

### 29.3. copy_data=false

Dùng khi subscriber đã được preload từ baseline phù hợp và replication start position được xác định đúng. Nó không tự kiểm tra hai datasets giống nhau.

### 29.4. Table sync progress

Theo dõi trạng thái table synchronization trong catalog subscription relation phù hợp với version, logs và worker state.

### 29.5. Mở writes theo ownership

Sau khi baseline và stream bắt kịp, bật writes theo vùng/tenant. Tránh mở đồng thời writes cho cùng keys trước khi conflict policy có hiệu lực.

## 30. Consistency model và ứng dụng

Logical replication mặc định là asynchronous. Subscriber có thể trễ so với publisher và hai chiều không tạo một transaction boundary chung.

### 30.1. Eventual consistency

Sau khi writes ngừng và replication catch up, hai nodes có thể hội tụ nếu không có conflict unresolved và mọi thay đổi được áp dụng đầy đủ.

### 30.2. Read-your-writes

Nếu client ghi ở A rồi đọc ở B, B có thể chưa nhận/apply transaction. Route reads về node đã nhận write hoặc chờ replication progress theo policy.

### 30.3. Monotonic reads

Client chuyển qua lại giữa hai nodes có lag khác nhau có thể thấy state cũ hơn. Sticky routing, version tokens hoặc read source affinity giúp giảm vấn đề.

### 30.4. Cross-node transactions

Một workflow ghi A rồi ghi B không trở thành atomic chỉ vì A/B replicate hai chiều. Nếu một nửa commit và nửa kia fail, cần saga/outbox/idempotency hoặc coordination ở tầng ứng dụng.

### 30.5. Business consistency

Định nghĩa invariants như inventory không âm, ledger cân bằng, unique username toàn cục, order/payment state hợp lệ. Chạy checks sau conflict/resync và có alert khi vi phạm.



## 31. Multi-node topology và vòng lặp nhiều hop

Hai node là ví dụ đơn giản. Khi có A, B, C và D, topology có thể là mesh hoặc hub-and-spoke. Mỗi kết nối thêm vào làm tăng số đường mà một transaction có thể đi qua.

~~~text
             A
           /   \
          B     C
           \   /
             D
~~~

### 31.1. Mesh dễ tạo nhiều đường vòng

Nếu mọi node publish cho mọi node khác, một thay đổi có thể đi theo nhiều path. Origin filtering hỗ trợ loại bỏ các thay đổi có nguồn gốc remote, nhưng topology vẫn cần được thiết kế và kiểm chứng.

### 31.2. Hub-and-spoke

Một hub có thể làm điểm trao đổi cho các spokes. Tuy nhiên, hub không tự giải quyết conflict giữa hai spokes cùng tạo business key hoặc sửa cùng row.

### 31.3. Không dùng origin như global conflict key

Origin giúp nhận diện nguồn transaction trong replication stream. Nó không phải một global transaction coordinator hay một phiên bản row có thể dùng để tự động chọn winner.

### 31.4. Một node có thể nhận nhiều origins

Theo dõi replication origins riêng và xác định publisher/peer tương ứng. Đặt tên nodes/subscriptions rõ ràng để điều tra.

### 31.5. Giới hạn số đường kết nối

Mỗi publication/subscription thêm slots, workers, network sessions và operational state. Chỉ tạo topology cần thiết cho ownership và failure domains.

## 32. Multi-region và network partition

Bidirectional replication thường được cân nhắc cho nhiều regions, nhưng network partition làm lộ rõ trade-off giữa availability và consistency.

### 32.1. Hai region cùng nhận writes

Khi đường truyền giữa regions bị đứt, mỗi node có thể tiếp tục nhận local writes. Sau khi mạng phục hồi, những rows cùng bị sửa có thể conflict.

### 32.2. Network partition không tự phân xử writer

Logical replication không bầu leader và không cấp lease cho node được phép ghi. Application/cluster control plane cần xác định writer authority.

### 32.3. Fencing và ownership leases

Có thể dùng lease/leader assignment hoặc fencing token ở tầng điều phối để bảo đảm chỉ node được cấp quyền mới nhận writes cho một ownership scope.

### 32.4. Split-brain writes

Nếu hai nodes cùng tin mình là authoritative cho cùng tenant/row, chúng có thể commit các state không tương thích. Khi stream trở lại, apply errors chỉ là biểu hiện; vấn đề gốc là ownership.

### 32.5. Fail closed hay accept local writes?

Business phải quyết định khi partition: từ chối writes ở region mất authority hay tiếp tục nhận writes với khả năng reconciliation. Không có lựa chọn vừa luôn available vừa bảo đảm mọi write conflict-free nếu không có coordination/domain model phù hợp.

## 33. Failover publisher và subscription continuity

Logical subscription kết nối tới publisher cụ thể. Khi publisher failover sang một server khác, cần đảm bảo subscriber có thể tiếp tục từ một slot/position hợp lệ.

### 33.1. Không giả định logical slot tự chuyển

Trong nhiều cấu hình/version, logical slot được tạo trên publisher cũ. Nếu node đó mất, subscriber có thể mất slot hoặc publisher endpoint mới không có slot tương ứng.

### 33.2. Failover slots theo version

Các PostgreSQL versions mới hơn có hỗ trợ cải thiện cho logical replication slots/failover, nhưng yêu cầu cấu hình và synchronization cụ thể. Kiểm tra tài liệu đúng major version và provider trước khi dựa vào tính năng này.

### 33.3. Đánh giá slot state sau promotion

Kiểm tra slot name, restart_lsn, confirmed_flush_lsn, failover/synced state nếu version cung cấp và khả năng publisher mới phục vụ subscription.

### 33.4. Nếu slot không thể tiếp tục

Có thể phải tạo lại subscription/slot và resynchronize dữ liệu từ baseline. Không tạo slot mới rồi tiếp tục như thể không có gap; cần reconciliation.

### 33.5. Subscriber HA cũng cần kiểm thử

Nếu subscriber được bảo vệ bằng physical standby, sau khi subscriber node được promote, xác nhận subscription worker/slot state, origin progress và apply behavior trước khi mở writes.

## 34. Synchronous commit và độ bền dữ liệu

Native logical replication mặc định là asynchronous. Việc apply ở subscriber diễn ra sau commit ở publisher.

### 34.1. Commit trên A không có nghĩa B đã apply

Ứng dụng có thể nhận commit success ở A trong khi B chưa nhận hoặc chưa apply transaction. Read từ B có thể stale.

### 34.2. Local synchronous_commit

Setting synchronous_commit điều khiển durability của transaction trên server đang commit. Nó không tự biến hai logical subscriptions thành một distributed synchronous transaction.

### 34.3. Không có global atomic commit

Nếu một workflow ghi A và B riêng rẽ, một bên có thể commit còn bên kia fail. Dùng application-level transaction coordination, outbox/saga hoặc single-writer model tùy yêu cầu.

### 34.4. Durability và convergence là hai mục tiêu

WAL fsync trên A bảo vệ local commit theo cấu hình; nó không chứng minh B đã apply hoặc hai nodes đã hội tụ.

### 34.5. Đặt freshness SLO

Định nghĩa thời gian tối đa dữ liệu được phép trễ ở mỗi peer và alert khi vượt. Nếu cần read-after-write, route/chờ theo token thay vì giả định immediate propagation.

## 35. Security và quyền replication

Logical replication có thể chuyển dữ liệu nhạy cảm từ một database sang database khác. Publisher role và subscriber identity cần được bảo vệ.

### 35.1. Replication role

Dùng role có quyền cần thiết để kết nối replication và đọc dữ liệu trong publication. Không cấp SUPERUSER nếu không có lý do được phê duyệt.

### 35.2. Publication scope là data access scope

Một publication rộng có thể gửi nhiều bảng/columns/rows hơn ứng dụng peer cần. Giới hạn table list, row filters và column lists theo data contract.

### 35.3. TLS

Dùng TLS với certificate validation phù hợp cho kết nối publisher/subscriber. Quản lý certificate rotation và xác minh hostname.

### 35.4. Secret management

Không lưu plaintext passwords trong repository, logs hoặc shared configuration. Dùng secret manager/permissioned files và rotation process.

### 35.5. Network allowlist và audit

Chỉ cho phép subscriber hosts kết nối publisher. Audit publication/subscription changes, slot operations, role grants và data export.

## 36. Performance và capacity planning

Bidirectional replication tạo tải ở cả hai nodes: logical decoding, WAL retention, network, apply workers và index/constraint maintenance.

### 36.1. Publisher workload

Logical decoding cần đọc WAL và tạo change stream. Nhiều publications/subscriptions và high write rate có thể tăng CPU/I/O và WAL retention.

### 36.2. Subscriber apply workload

Apply worker thực thi row changes, kiểm tra constraints và cập nhật indexes. Subscriber có local writes đồng thời sẽ tranh chấp locks/IO với apply.

### 36.3. Network bandwidth

Tính theo WAL change volume thực tế, compression/protocol overhead và burst. Hai hướng đều có traffic riêng.

### 36.4. Index maintenance

Subscriber cần indexes/constraints phù hợp. Nhiều secondary indexes làm apply writes chậm hơn, nhưng thiếu unique constraints có thể làm dữ liệu không đúng.

### 36.5. Backpressure

Nếu apply chậm, replication slot giữ WAL trên publisher. Theo dõi disk growth và lag; không chỉ tăng slot retention mà không giải quyết throughput.

## 37. Quy tắc vận hành cho hai chiều

Mỗi node có thể vừa là publisher vừa là subscriber. Runbook phải xác định thao tác nào cần thực hiện trên node nào.

### 37.1. Thay đổi publication

Nếu thêm/bớt bảng ở A, đánh giá subscription trên B và refresh publication. Làm tương tự theo hướng B→A.

### 37.2. Thay đổi schema

Áp dụng DDL theo migration sequence được kiểm soát trên cả hai nodes. Đừng để một publisher gửi row shape mới tới subscriber chưa có cột tương ứng.

### 37.3. Tạm dừng một hướng

Ghi rõ lý do, thời gian dự kiến và WAL retention. Nếu peer vẫn ghi, divergence có thể tăng.

### 37.4. Khởi động lại workers

Sau khi sửa lỗi, enable subscription và xác nhận apply progress. Kiểm tra chiều ngược để chắc chắn repair không tạo lỗi mới.

### 37.5. Kết thúc maintenance

Kiểm tra slot health, lag, business invariants, schema version, duplicate keys và audit trail.

## 38. Khi nào nên dùng bidirectional logical replication?

Có thể phù hợp khi hai hệ thống cần trao đổi một tập dữ liệu giới hạn, có ownership rõ và conflict rate thấp.

### 38.1. Multi-region read/write với ownership theo tenant

Mỗi tenant có một home region ghi; dữ liệu được replicate để regions khác đọc. Ownership transfer được điều phối.

### 38.2. Data exchange giữa hai ứng dụng

Hai databases sở hữu các bảng khác nhau và chỉ publish các bảng/rows cần chia sẻ. Bảng master có một writer duy nhất.

### 38.3. Migration song song có thời hạn

Trong migration, logical replication có thể chuyển changes từ source tới target; chiều ngược chỉ bật khi có kế hoạch rollback/dual-write được kiểm soát và hiểu rõ conflict.

### 38.4. Edge sites

Các edge nodes có thể ghi tập dữ liệu local riêng, sau đó gửi events/rows về central system. Cần xử lý offline duration, duplicate events và conflict.

### 38.5. Không phù hợp khi cùng row được ghi tự do ở mọi node

Nếu mọi node cùng sửa mọi bảng mà không có ownership, unique key strategy hay conflict resolution, native logical replication sẽ dễ dừng do apply errors và tạo divergence.

## 39. Khi nào cần giải pháp khác?

Nếu yêu cầu là active-active writes tự do trên cùng dữ liệu, hãy đánh giá kiến trúc khác.

### 39.1. Single-writer routing

Định tuyến writes tới một primary/owner cho mỗi data partition. Đây thường là cách đơn giản nhất để tránh concurrent conflicts.

### 39.2. Event-driven integration

Publish domain events và xử lý idempotently ở consumers. Event model có thể hỗ trợ reconciliation tốt hơn việc replicate mọi row update.

### 39.3. Application-level conflict resolution

Ứng dụng có thể lưu version, origin, event ID và merge policy theo domain. Database replication chỉ vận chuyển thay đổi đã được xác định.

### 39.4. Multi-master extensions/services

Một số giải pháp bên thứ ba cung cấp conflict handling, distributed key generation hoặc multi-master orchestration. Đánh giá version compatibility, support model, failure semantics và test recovery.

### 39.5. Distributed database

Nếu consistency, availability và multi-region write semantics là yêu cầu cốt lõi, cân nhắc hệ thống được thiết kế cho distributed transactions/consensus hoặc partitioned ownership ngay từ đầu.



## 40. Lab: dựng hai node logical replication hai chiều

Lab sử dụng hai PostgreSQL instances riêng, cùng major version, cùng schema và network cô lập. Không dùng dữ liệu production.

~~~text
Node A (port 5432) <------> Node B (port 5433)
       pub_a                    pub_b
       sub_ab                   sub_ba
~~~

### 40.1. Tạo bảng giống nhau

Chạy trên cả A và B:

~~~sql
CREATE TABLE public.replication_lab (
    id UUID PRIMARY KEY,
    origin_node TEXT NOT NULL,
    payload TEXT NOT NULL,
    version_no BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 40.2. Tạo replication role

Trên mỗi publisher, tạo role có quyền replication và quyền SELECT cần thiết cho publication/table sync. Dùng credentials lab riêng và HBA chỉ cho peer.

### 40.3. Tạo publication trên A và B

~~~sql
CREATE PUBLICATION pub_a
FOR TABLE public.replication_lab
WITH (publish = 'insert, update, delete');

CREATE PUBLICATION pub_b
FOR TABLE public.replication_lab
WITH (publish = 'insert, update, delete');
~~~

### 40.4. Tạo subscriptions với origin filtering

Trên B:

~~~sql
CREATE SUBSCRIPTION sub_ba
CONNECTION 'host=127.0.0.1 port=5432 dbname=labdb user=replicator'
PUBLICATION pub_a
WITH (origin = none);
~~~

Trên A:

~~~sql
CREATE SUBSCRIPTION sub_ab
CONNECTION 'host=127.0.0.1 port=5433 dbname=labdb user=replicator'
PUBLICATION pub_b
WITH (origin = none);
~~~

Điều chỉnh host/port/database và SSL theo môi trường lab. Với bảng rỗng, initial copy không có nhiều dữ liệu; trong môi trường có data baseline, phải thiết kế copy_data và LSN trước.

### 40.5. Kiểm tra subscription

Trên mỗi subscriber, xem pg_stat_subscription và PostgreSQL logs. Xác nhận cả hai directions có worker và không có apply/sync errors.

## 41. Lab: chứng minh origin filtering ngăn forwarding loop

### 41.1. Insert local trên A

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('10000000-0000-0000-0000-000000000001', 'A', 'created on A');
~~~

### 41.2. Kiểm tra B nhận row

Trên B:

~~~sql
SELECT *
FROM public.replication_lab
WHERE id = '10000000-0000-0000-0000-000000000001';
~~~

### 41.3. Kiểm tra A không nhận lại cùng transaction như local change

Theo dõi origin progress và subscription logs. Với origin filtering đúng, transaction đã được replicate từ A không được B forward ngược lại như một local-origin transaction.

### 41.4. Insert local trên B

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('20000000-0000-0000-0000-000000000001', 'B', 'created on B');
~~~

Xác nhận A nhận row này. Điều đó chứng minh origin filtering vẫn cho phép transaction được tạo local ở peer đi qua hướng ngược lại.

### 41.5. Đối chiếu cả hai nodes

So sánh rows/IDs và xem apply errors. Origin filtering phải ngăn vòng lặp mà không chặn local writes hợp lệ.

## 42. Lab: mô phỏng duplicate-key conflict

Chỉ thực hiện trên lab, không trên hệ thống thật.

### 42.1. Chuẩn bị conflict window

Tạm ngăn replication network hoặc disable subscriptions theo lab procedure để hai nodes có thể nhận local writes trước khi thay đổi được trao đổi.

### 42.2. Chèn cùng UUID trên hai nodes

Trên A:

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'A', 'value from A');
~~~

Trên B:

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'B', 'value from B');
~~~

### 42.3. Bật lại replication

Enable subscriptions và quan sát logs. Một phía có thể gặp unique violation khi apply row cùng key đã tồn tại local.

### 42.4. Ghi lại dữ liệu hai bên

SELECT row trên A/B, xem payload/origin_node/version. Không xóa row để “sửa nhanh” trước khi ghi nhận evidence.

### 42.5. Thực hành resolution

Chọn winner theo policy lab, freeze writes, reconcile hai nodes, resume subscriptions và xác nhận cả hai hội tụ. Ghi transaction/rows đã thay đổi.

## 43. Lab: kiểm tra row ownership và row filters

### 43.1. Thêm region key

~~~sql
ALTER TABLE public.replication_lab
ADD COLUMN region_id INTEGER;
~~~

Áp dụng schema change trên cả hai nodes trước khi thay publication.

### 43.2. Tạo publication filter cho A

~~~sql
CREATE PUBLICATION pub_a_region
FOR TABLE public.replication_lab
WHERE (region_id = 1);
~~~

Tạo publication tương ứng cho B với region_id = 2. Dùng publication mới/subscription lab riêng để thử nghiệm.

### 43.3. Ghi rows theo owner

A chỉ ghi region 1; B chỉ ghi region 2. Kiểm tra rows được truyền sang peer để đọc.

### 43.4. Thử ghi sai ownership

Chèn row region 2 trên A và quan sát publication filter không gửi row đó theo cấu hình. Đồng thời kiểm tra application/database policy có chặn sai ownership hay không.

### 43.5. Ownership transfer

Thực hành freeze tenant/region, catch up stream, đổi owner và mở writes ở node mới. Không chỉ sửa filter khi writes vẫn chạy.

## 44. Lab: theo dõi apply errors và recovery

### 44.1. Thu thập subscription stats

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

~~~sql
SELECT *
FROM pg_stat_subscription_stats;
~~~

View thứ hai chỉ có trên các phiên bản hỗ trợ. Ghi số counters trước/sau bài lab.

### 44.2. Xem origin progress

~~~sql
SELECT *
FROM pg_replication_origin_status;
~~~

Đối chiếu remote_lsn và local_lsn theo origin.

### 44.3. Đọc server logs

Tìm lỗi duplicate key hoặc constraint. Ghi subscription, table, key và transaction/LSN.

### 44.4. Disable hướng lỗi

Trong lab, disable subscription bị lỗi, chụp rows và chọn cách reconcile. Đảm bảo hiểu slot/WAL retention trong lúc disable.

### 44.5. Enable và verify

Bật lại subscription, xác nhận apply worker chạy, progress tăng và dữ liệu nghiệp vụ hội tụ. Không chỉ xác nhận PID tồn tại.

## 45. Runbook vận hành bidirectional replication

Một runbook production nên có các bước sau:

1. Ghi incident/change ID, node names, subscription direction và thời gian.
2. Xác định PostgreSQL major versions và origin filtering capability.
3. Vẽ topology publisher/subscriber, slots và ownership scopes.
4. Xác định transaction/row/constraint gây conflict từ logs.
5. Chụp dữ liệu liên quan ở cả hai nodes và bảo toàn evidence.
6. Xác định node/tenant/keyspace owner và business source of truth.
7. Tạm dừng writes hoặc subscriptions theo scope để ngăn divergence tăng.
8. Chọn resolution rule: winner, field merge, event replay hoặc resync.
9. Áp dụng sửa chữa có audit trên các nodes.
10. Nếu skip transaction, ghi commit LSN và reconcile toàn bộ thay đổi bị bỏ.
11. Resume subscriptions và kiểm tra origin/slot/apply progress.
12. Chạy unique/FK/business invariant checks trên cả hai nodes.
13. Xác nhận schema version và publication scope.
14. Mở lại writes theo ownership policy.
15. Ghi root cause, action items và bằng chứng convergence.

### 45.1. Incident owner

Chỉ định database operator, application owner và business decision maker. DBA không nên tự quyết định giá trị nào thắng khi dữ liệu có ý nghĩa nghiệp vụ.

### 45.2. Stop conditions

Dừng việc mở writes nếu không xác định được row owner, thiếu WAL, schema mismatch, conflict liên tục hoặc business invariant fail.

### 45.3. Evidence

Lưu logs, LSN, row snapshots, subscription stats, schema version và approvals. Không ghi credentials hoặc dữ liệu nhạy cảm không cần thiết.

### 45.4. Sau khi xử lý

Xác nhận cả hai directions hoạt động, slots không giữ WAL bất thường, lag trở lại SLO và backup/PITR vẫn có thể phục hồi.

### 45.5. Post-incident review

Tìm nguyên nhân gốc như key allocation trùng, ownership không enforced, schema rollout sai thứ tự hoặc application retry không idempotent. Sửa design để conflict ít có khả năng lặp lại.

## 46. Các lỗi thiết kế thường gặp

1. Tạo reciprocal subscriptions mà không có loop-prevention mechanism.
2. Cho rằng origin filtering giải quyết concurrent updates.
3. Dùng sequence cùng start/increment trên hai nodes.
4. Cho mọi node ghi mọi row mà không có ownership.
5. Dùng timestamp đồng hồ làm conflict winner mà không xử lý clock skew.
6. Bật copy_data hai chiều khi cả hai bên đã có dữ liệu trùng.
7. Giả định DDL tự được replicate.
8. Quên sequences, roles, grants, large objects và extension dependencies.
9. Không đặt replica identity phù hợp cho UPDATE/DELETE.
10. Publish TRUNCATE trong khi hai nodes sở hữu rows độc lập.
11. Thay schema một phía trước khi subscriber tương thích.
12. Không refresh publication khi thêm bảng.
13. Không monitor logical replication slots và retained WAL.
14. Disable subscription nhưng không theo dõi disk growth.
15. Skip transaction chỉ để apply worker chạy lại.
16. Sửa conflict ở một phía nhưng quên chiều ngược.
17. Không kiểm tra row filters và tenant ownership.
18. Coi eventual consistency là immediate consistency.
19. Dùng read từ peer ngay sau write mà không có read-your-writes policy.
20. Cho rằng failover publisher tự động giữ nguyên logical slot.
21. Không có baseline/resync plan khi slot bị mất.
22. Dùng native logical replication như một distributed transaction coordinator.
23. Không test network partition và split-brain write behavior.
24. Không có audit cho manual conflict resolution.
25. Không diễn tập resync sau schema/data divergence.

## 47. Bài tập thực hành

### Bài 1 — Khái niệm

Bidirectional logical replication là gì?

**Đáp án:** Hai databases đều publish local changes và subscribe changes từ peer.

### Bài 2 — Publisher

Publication làm nhiệm vụ gì?

**Đáp án:** Xác định tables/operations/rows/columns được gửi từ publisher.

### Bài 3 — Subscriber

Subscription quản lý những gì?

**Gợi ý:** Kết nối publisher, slot, initial sync và apply worker.

### Bài 4 — Replication loop

Vì sao một transaction có thể quay lại node nguồn?

**Đáp án:** Node nhận apply transaction rồi publish nó tiếp về nguồn hoặc qua một đường khác.

### Bài 5 — Origin filtering

Tùy chọn origin nào lọc các thay đổi có nguồn gốc remote?

**Đáp án:** origin = none trên PostgreSQL 16+.

### Bài 6 — Version

Từ PostgreSQL major version nào có subscription origin filtering?

**Đáp án:** PostgreSQL 16.

### Bài 7 — Conflict resolution

Origin filtering có giải quyết duplicate key do hai local writes không?

**Đáp án:** Không.

### Bài 8 — Duplicate key

Hai node chèn cùng primary key sẽ có nguy cơ gì?

**Đáp án:** Unique violation khi transaction từ peer apply.

### Bài 9 — Missing row

Vì sao UPDATE/DELETE có thể fail ở subscriber?

**Gợi ý:** Row mục tiêu không tồn tại hoặc replica identity không xác định được row.

### Bài 10 — Replica identity

Mặc định bảng dùng gì làm replica identity nếu có?

**Đáp án:** Primary key.

### Bài 11 — REPLICA IDENTITY FULL

Trade-off chính là gì?

**Gợi ý:** Có thể hỗ trợ xác định row nhưng tạo WAL lớn hơn và tìm row tốn kém hơn.

### Bài 12 — Ownership

Single-writer per tenant giúp giảm rủi ro nào?

**Đáp án:** Hai nodes cùng sửa rows thuộc cùng tenant.

### Bài 13 — UUID

UUID giải quyết điều gì?

**Đáp án:** Giảm đáng kể nguy cơ primary-key collision; không giải quyết business-key conflicts.

### Bài 14 — Sequences

Logical replication có đồng bộ sequence state để bảo đảm global uniqueness không?

**Đáp án:** Không.

### Bài 15 — DDL

ALTER TABLE trên publisher có tự chạy trên subscriber không?

**Đáp án:** Không.

### Bài 16 — TRUNCATE

Vì sao publish TRUNCATE có thể nguy hiểm trong bidirectional setup?

**Gợi ý:** Nó xóa toàn bảng ở peer, kể cả rows do peer sở hữu.

### Bài 17 — Row filter

Row filter có thay thế security policy/RLS không?

**Đáp án:** Không.

### Bài 18 — Initial sync

Vì sao không nên bật copy_data hai chiều mù quáng?

**Đáp án:** Có thể copy các keys đã tồn tại ở peer và gây duplicate conflicts.

### Bài 19 — copy_data=false

Khi nào có thể dùng?

**Gợi ý:** Subscriber đã được preload từ baseline đúng và stream start point được đồng bộ.

### Bài 20 — Slot

Logical replication slot nằm ở đâu?

**Đáp án:** Trên publisher tương ứng với subscription.

### Bài 21 — Slot retention

Subscription disabled lâu có thể gây rủi ro gì?

**Đáp án:** Slot giữ WAL và làm đầy disk.

### Bài 22 — Apply worker

Một duplicate-key error có thể ảnh hưởng gì?

**Đáp án:** Apply worker dừng và subscription lag tăng cho tới khi xử lý.

### Bài 23 — Monitoring

View nào xem apply/worker state trên subscriber?

**Đáp án:** pg_stat_subscription.

### Bài 24 — Origin progress

View nào theo dõi remote/local LSN theo replication origin?

**Đáp án:** pg_replication_origin_status.

### Bài 25 — Error counters

View nào có apply_error_count trên versions hỗ trợ?

**Đáp án:** pg_stat_subscription_stats.

### Bài 26 — Skip transaction

Vì sao skip transaction nguy hiểm?

**Đáp án:** Subscriber bỏ toàn bộ thay đổi trong transaction, có thể phá invariants và foreign-key/business state.

### Bài 27 — Field-level merge

Khi nào có thể merge riêng các fields?

**Gợi ý:** Khi fields có semantics độc lập và domain cho phép hợp nhất.

### Bài 28 — Last-write-wins

Rủi ro của timestamp-based winner là gì?

**Đáp án:** Clock skew và thứ tự commit không toàn cục.

### Bài 29 — Event sourcing

Append-only events có thể giảm loại conflict nào?

**Gợi ý:** Overwrite cùng row; nhưng vẫn cần unique event IDs, idempotency và ordering.

### Bài 30 — Multi-region partition

Network partition có tự chọn node writer không?

**Đáp án:** Không.

### Bài 31 — Fencing

Fencing/lease giúp gì?

**Gợi ý:** Enforce chỉ owner hiện tại được phép ghi trong ownership scope.

### Bài 32 — Synchronous commit

Logical replication mặc định có đồng bộ commit giữa hai nodes không?

**Đáp án:** Không; subscriber apply bất đồng bộ.

### Bài 33 — Read-your-writes

Client ghi ở A rồi đọc B cần làm gì?

**Gợi ý:** Route A hoặc chờ B apply tới mốc transaction cần thiết.

### Bài 34 — Schema rollout

Expand-and-contract giúp giảm rủi ro gì?

**Đáp án:** Publisher gửi schema/data mới khi subscriber chưa tương thích.

### Bài 35 — Large objects

Native logical replication có replicate large objects như table rows không?

**Đáp án:** Không.

### Bài 36 — Failover slot

Publisher failover có luôn giữ logical slot không?

**Đáp án:** Không; phụ thuộc PostgreSQL version, failover-slot configuration và provider.

### Bài 37 — Resync

Khi slot bị mất và WAL không còn, có thể cần gì?

**Đáp án:** Rebaseline/resynchronize subscriber từ consistent snapshot.

### Bài 38 — Conflict ownership

Ai quyết định row conflict winner?

**Đáp án:** Business/data owner theo domain rule, với DBA/application owner hỗ trợ.

### Bài 39 — Monitoring

Vì sao cần monitor cả A→B và B→A?

**Đáp án:** Mỗi subscription/slot/apply worker có failure và lag độc lập.

### Bài 40 — Thiết kế tổng hợp

Hai regions cần ghi orders tại chỗ, mỗi tenant có home region, yêu cầu tránh loops và giữ read copies ở cả hai. Hãy đề xuất thiết kế.

**Gợi ý:** Ownership per tenant enforced ở app/DB; publication row filters theo owner; subscriptions hai chiều với origin=none trên PostgreSQL 16+; UUID/global key strategy; schema migration đồng bộ; initial baseline/LSN có kiểm soát; monitor slots, apply errors và freshness; conflict runbook; failover/fencing và resync drills. Nếu cùng tenant cần ghi đồng thời ở cả hai regions, bổ sung domain conflict-resolution hoặc chọn một writer authority.

## 48. Checklist thiết kế

### 48.1. Topology và version

- [ ] PostgreSQL major version đã xác nhận?
- [ ] Origin filtering được hỗ trợ và bật đúng trên từng subscription?
- [ ] Publisher/subscriber direction được ghi rõ?
- [ ] Topology không có đường forwarding loop ngoài dự kiến?
- [ ] Failure domains và network paths được xác định?

### 48.2. Data ownership và keys

- [ ] Writer owner per table/tenant/keyspace?
- [ ] Primary keys không va chạm?
- [ ] Business unique keys có allocation/ownership policy?
- [ ] Sequences được quản lý độc lập?
- [ ] Concurrent update/merge rules đã phê duyệt?
- [ ] Foreign-key ordering/dependencies đã xem xét?

### 48.3. Schema và publication

- [ ] Schema version tương thích ở hai phía?
- [ ] Replica identity phù hợp cho UPDATE/DELETE?
- [ ] Publication table/operation scope tối thiểu?
- [ ] Row filters/column lists được kiểm tra?
- [ ] TRUNCATE có được publish có chủ đích?
- [ ] DDL/roles/extensions/large objects có quy trình riêng?

### 48.4. Initial sync và recovery

- [ ] Baseline snapshot/LSN rõ ràng?
- [ ] copy_data phù hợp trạng thái subscriber?
- [ ] Initial sync hai chiều tránh duplicate rows?
- [ ] Logical slots có owner/retention alerts?
- [ ] Resync khi mất slot/WAL đã có runbook?
- [ ] Publisher failover behavior đã thử?

### 48.5. Monitoring và operations

- [ ] pg_stat_subscription được giám sát?
- [ ] Apply/sync error counters và logs được alert?
- [ ] pg_replication_origin_status được theo dõi?
- [ ] Cả hai directions có freshness SLO?
- [ ] Conflict runbook và business approver có sẵn?
- [ ] Security/TLS/secret rotation/audit được cấu hình?
- [ ] Network partition/fencing/resync drills đã thực hiện?

## 49. Bảng tra cứu nhanh

| Khái niệm | Ý nghĩa |
|---|---|
| Logical replication | Chuyển row changes qua publication/subscription |
| Publisher | Database công bố changes |
| Publication | Phạm vi tables/operations/rows/columns được gửi |
| Subscriber | Database nhận và apply changes |
| Subscription | Kết nối, slot, sync và apply configuration |
| Bidirectional replication | Hai nodes đều publish và subscribe |
| Replication loop | Change đã nhận bị chuyển tiếp quay lại nguồn |
| Replication origin | Metadata nguồn gốc transaction được replicate |
| origin = none | Chỉ nhận changes có local origin trên PostgreSQL 16+ |
| Apply worker | Tiến trình áp dụng changes trên subscriber |
| Conflict | Hai trạng thái/thao tác không thể apply theo constraints |
| Replica identity | Key dùng tìm row cho UPDATE/DELETE |
| REPLICA IDENTITY FULL | Dùng toàn bộ row identity |
| Row filter | Giới hạn rows được publication gửi |
| copy_data | Điều khiển initial table data copy |
| Logical slot | Giữ WAL cho logical decoding/subscription |
| Schema drift | Schema hai node không còn tương thích |
| Selective merge | Hợp nhất phần dữ liệu cần thiết theo business rule |
| Skip transaction | Bỏ qua transaction đang lỗi, có rủi ro mất dữ liệu |
| Resync | Tạo lại baseline và replication stream |
| Fencing | Ngăn node không còn owner tiếp tục ghi |
| Eventual consistency | Các nodes hội tụ sau khi stream catch up |
| Read-your-writes | Đảm bảo client đọc thấy write của chính nó |
| Expand-and-contract | Migration schema theo bước tương thích |
| Conflict resolution | Quy tắc chọn/merge state khi có concurrent writes |

## 50. Kết luận

**Sao chép hai chiều không chỉ là tạo hai subscriptions ngược hướng.** Nó yêu cầu kiểm soát nguồn gốc thay đổi, quyền sở hữu dữ liệu, khóa toàn cục, schema, transaction ordering và quy trình xử lý conflict. PostgreSQL 16+ cung cấp origin filtering với origin=none để hạn chế replication loops: thay đổi đã nhận từ peer không bị chuyển tiếp như một local-origin transaction. Cơ chế này giải quyết một phần bài toán forwarding, không tự hợp nhất concurrent writes.

Để giảm conflict, nên thiết kế single-writer per table/tenant/keyspace, dùng UUID hoặc key allocation không giao nhau, kiểm soát business unique keys và thực hiện schema migrations đồng bộ. Logical replication không tự đồng bộ DDL, sequence state, roles, large objects hay extension binaries; initial sync hai chiều cần baseline/LSN có kiểm soát. Khi apply worker dừng, điều tra transaction và rows ở cả hai phía, quyết định theo business ownership, chỉ skip khi hiểu đầy đủ dữ liệu bị bỏ và có kế hoạch reconciliation.

Bidirectional logical replication phù hợp khi hai nodes trao đổi các tập dữ liệu có ownership rõ và conflict thấp. Nếu mọi node được phép ghi tự do cùng rows trong lúc network partition, cần conflict-resolution model hoặc nền tảng multi-master được thiết kế cho semantics đó. Hãy monitor từng direction, slots, apply errors, origins và business freshness; diễn tập failover/resync và bảo đảm có backup/PITR độc lập.

Nguyên tắc vận hành: **ngăn loops bằng origin-aware topology, ngăn conflicts bằng ownership/key design, xử lý conflicts bằng domain rules, và chứng minh convergence bằng monitoring cùng reconciliation drills.**

