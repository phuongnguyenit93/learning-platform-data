# Hard delete, dấu xóa và sự lan truyền đến các bản sao

## 1. Vì sao xóa dữ liệu trong NoSQL phân tán không đơn giản?

Một ứng dụng học trực tuyến lưu hồ sơ người học L001 trên cụm NoSQL gồm nhiều replica. Người học yêu cầu xóa tài khoản. API gửi DELETE và trả kết quả thành công. Nhưng điều đó có nghĩa toàn bộ dữ liệu đã biến mất?

Những tình huống cần xét:

- Một replica offline chưa nhận lệnh xóa.
- Redis cache vẫn chứa hồ sơ cũ.
- Search index còn hiển thị người học vì sự kiện xóa chưa được xử lý.
- Bảng read model vẫn lưu tên, ảnh hoặc thông tin từ tài khoản.
- SSTable, journal, snapshot hoặc backup còn giữ dữ liệu cũ.
- Một worker xử lý UPDATE đến muộn và tạo lại bản ghi sau khi xóa.

Để thiết kế vòng đời dữ liệu đúng, ta phải phân biệt **hard delete**, **soft delete**, **tombstone**, **lan truyền đến replica**, **dọn vật lý** và **đồng bộ các bản sao nghiệp vụ**. Những thuật ngữ này liên quan nhưng không đồng nghĩa.

**Mục tiêu bài học:** Sau khi học, bạn có thể phân tích thời điểm xóa có hiệu lực, giải thích vì sao cần giữ dấu xóa để ngăn dữ liệu hồi sinh, nêu vai trò của compaction/repair trong Cassandra, thiết kế event xóa có version, kiểm soát cache/search và xây một quy trình xóa có khả năng phục hồi.

Các ví dụ sử dụng Cassandra/ScyllaDB, MongoDB, DynamoDB, Redis và search engine. Mỗi hệ có semantics, giới hạn và mức consistency riêng; không nên mặc định mọi sản phẩm hoạt động như Cassandra.

## 2. Phân biệt soft delete, hard delete và physical purge

### 2.1. Soft delete

Ứng dụng giữ bản ghi nhưng đổi trạng thái:

    {
      "learnerId": "L001",
      "displayName": "An",
      "status": "DELETED",
      "deletedAt": "2026-11-14T09:00:00Z",
      "version": 8
    }

Soft delete hữu ích nếu cần khôi phục, kiểm toán hoặc giữ lịch sử theo chính sách. Nhưng thông tin vẫn còn trong nguồn; nếu query quên loại status DELETED, dữ liệu có thể lộ.

### 2.2. Hard delete

Ví dụ MongoDB:

    db.learners.deleteOne({ _id: "L001" });

Document không còn là bản ghi hoạt động theo ngữ nghĩa của collection và đường đọc phù hợp. DynamoDB có DeleteItem, Redis có DEL và Cassandra hỗ trợ DELETE bằng CQL.

Tuy nhiên, **hard delete ở API không chứng minh các bytes đã bị xóa khỏi mọi file, replica, cache, backup hoặc hệ dẫn xuất ngay lúc đó**.

### 2.3. Physical purge

Physical purge là giai đoạn dữ liệu cũ được dọn khỏi cấu trúc lưu trữ hoặc bị xử lý không thể khôi phục theo chính sách. Nó có thể diễn ra khi:

- SSTable được compaction và dữ liệu bị tombstone che đủ điều kiện dọn.
- Storage engine thu hồi vùng lưu.
- Snapshot/backup hết retention.
- Object storage xóa các phiên bản file cũ.
- Hệ thống dùng cơ chế xóa mật mã (crypto-erasure) với thiết kế khóa phù hợp.

Không phải mọi thao tác hard delete đều đồng nghĩa physical purge ngay lập tức.

### 2.4. Những mốc phải nêu riêng

| Mốc | Điều đã biết | Điều chưa chắc xảy ra |
|---|---|---|
| Soft delete | Record bị đánh dấu không hoạt động | Payload còn ở nguồn |
| Hard delete ACK | Lệnh xóa được xác nhận ở phạm vi đã chọn | Replica khác chưa chắc đã hội tụ |
| Read không còn thấy | Đường đọc được kiểm tra đã ẩn dữ liệu | Search/cache/backup có thể còn |
| Tombstone được lưu | Có thông tin rằng dữ liệu cũ đã bị xóa | Bytes cũ có thể chưa dọn |
| Compaction/purge | Dữ liệu cũ đủ điều kiện đã được dọn tại tầng lưu trữ | Bản sao bên ngoài vẫn cần xử lý |
| Toàn bộ workflow hoàn tất | Các bước được cam kết đã thực hiện | Phải nói rõ phạm vi retention |

Trong tài liệu thiết kế, câu “đã xóa” nên đi kèm **đã xóa tại nguồn**, **đã ẩn tại API**, **đã lan tới replica**, **đã dọn hệ dẫn xuất** hoặc **đã hết retention backup**.

## 3. Tombstone là gì và tại sao nó quan trọng?

### 3.1. Replica bỏ lỡ DELETE

Giả sử cùng khóa K được sao chép ở ba nút:

    Replica A: K = ACTIVE, version 7
    Replica B: K = ACTIVE, version 7
    Replica C: K = ACTIVE, version 7

C bị ngắt mạng. Lệnh xóa version 8 tới A và B:

    Replica A: DELETE version 8 đã áp dụng
    Replica B: DELETE version 8 đã áp dụng
    Replica C: vẫn còn ACTIVE version 7

Nếu A/B chỉ quên hoàn toàn K thì khi C trở lại, dữ liệu cũ ở C có nguy cơ được sao chép trở lại. Hệ không biết A/B không có K vì **chưa từng lưu** hay vì **đã xóa ở version mới hơn**.

### 3.2. Lưu bằng chứng xóa

Nếu A/B giữ dấu xóa:

    Replica A: TOMBSTONE K, version 8
    Replica B: TOMBSTONE K, version 8
    Replica C: ACTIVE K, version 7

thì hệ có thông tin phục vụ hòa giải. Theo quy tắc timestamp/version của storage engine, quyết định xóa mới hơn có thể che dữ liệu cũ.

**Không có dữ liệu** không giống **có bằng chứng rằng dữ liệu đã bị xóa**. Tombstone bảo tồn bằng chứng đó trong một khoảng thời gian quan trọng.

### 3.3. Hai tầng tombstone

**Storage tombstone** là metadata của engine, chẳng hạn Cassandra đánh dấu cell, row, range hoặc partition đã xóa. Nó không nhất thiết là trường status trong document.

**Business tombstone** là bản ghi do ứng dụng quản lý để ngăn sự kiện cũ tạo lại dữ liệu sau hard delete:

    {
      "entityId": "L001",
      "deleted": true,
      "lastAppliedVersion": 8
    }

Hai tầng này có mục tiêu tương tự nhưng không thay thế nhau. Cassandra tombstone bảo vệ hòa giải replica; business tombstone có thể bảo vệ read model, cache và search khi nhận event sai thứ tự.

### 3.4. Luồng lan truyền

    Client gửi DELETE(K)
              |
              v
        Coordinator
          /      \
         v        v
      Replica A  Replica B  -> ghi tombstone
                    |
                 ACK theo mức yêu cầu

      Replica C đang offline và giữ bản cũ.
      Khi C trở lại, repair/đồng bộ cần
      truyền thông tin xóa mới hơn.

Đây là sơ đồ khái niệm; cơ chế ACK, coordinator, repair và conflict resolution của từng hệ phải được xác định riêng.

## 4. Cassandra/ScyllaDB: dấu xóa trong LSM-tree

### 4.1. SSTable không được sửa tại chỗ theo kiểu tùy ý

Trong storage dạng **LSM-tree**, các mutation mới được ghi qua những cấu trúc thích hợp với ghi tuần tự và được xả thành SSTable. Một giá trị có thể có nhiều phiên bản ở các file khác nhau:

    SSTable cũ:       K = "An", timestamp=t1
    SSTable mới hơn:  K = "An Nguyen", timestamp=t2
    SSTable gần nhất: TOMBSTONE(K), timestamp=t3

Khi t3 thắng theo ngữ nghĩa mutation, dữ liệu cũ không còn được trả ở đường đọc phù hợp. Compaction về sau có thể hợp nhất các SSTable và loại những giá trị/dấu xóa đủ điều kiện an toàn.

Điều đó giải thích vì sao **lệnh DELETE có thể kết thúc nhanh hơn quá trình dọn vật lý**.

### 4.2. Những thao tác có thể tạo tombstone

Trong Cassandra, tombstone có thể xuất hiện từ:

- DELETE một cột.
- DELETE một hàng theo primary key.
- DELETE tập hàng/range hoặc partition theo cú pháp hỗ trợ.
- Dữ liệu có TTL hết hạn.
- Một số thao tác cập nhật làm mất hiệu lực giá trị cũ.

Không phải một tombstone luôn tương ứng một document JSON đầy đủ. Phạm vi đánh dấu xóa và hình dạng dữ liệu ảnh hưởng tới chi phí đọc/compaction.

### 4.3. Ví dụ CQL: xóa một sự kiện

    CREATE TABLE activity_by_learner_day (
        learner_id text,
        activity_day date,
        occurred_at timestamp,
        event_id uuid,
        event_type text,
        payload text,
        PRIMARY KEY (
            (learner_id, activity_day),
            occurred_at,
            event_id
        )
    ) WITH CLUSTERING ORDER BY (
        occurred_at DESC,
        event_id ASC
    );

Xóa đúng một hàng:

    DELETE FROM activity_by_learner_day
    WHERE learner_id = 'L001'
      AND activity_day = '2026-11-14'
      AND occurred_at = '2026-11-14T08:40:00Z'
      AND event_id = 550e8400-e29b-41d4-a716-446655440001;

Trong mô hình này, khóa phân vùng là (learner_id, activity_day). Nếu cần xóa hàng triệu sự kiện của L001 trải nhiều ngày, ứng dụng phải có đường xác định các partition liên quan và chiến lược hạn tải. Không mặc định WHERE learner_id đủ để xóa hiệu quả toàn bộ lịch sử.

### 4.4. Timestamp mutation khác timestamp nghiệp vụ

Trong Cassandra, timestamp của mutation tham gia giải quyết xung đột giữa các ghi/xóa. Nó không đơn thuần là thời điểm xảy ra sự kiện mà ứng dụng lưu trong occurred_at.

Nếu client tự gán mutation timestamp tùy tiện hoặc các nguồn phát thời gian lệch, DELETE và INSERT cùng khóa có thể tạo kết quả bất ngờ. Cần tôn trọng quy tắc timestamp, consistency và giao dịch của hệ cụ thể.

## 5. gc_grace_seconds, repair và nguy cơ zombie data

### 5.1. Tombstone cần được giữ đủ lâu

Replica C offline khi A/B nhận DELETE. Nếu A/B dọn tombstone **trước khi C nhận thông tin xóa**, khi C trở lại nó vẫn có dữ liệu cũ. Hệ có thể hòa giải dữ liệu cũ vào A/B và làm bản ghi **hồi sinh (data resurrection hoặc zombie data)**.

### 5.2. Vai trò của gc_grace_seconds

**gc_grace_seconds** là một cấu hình của Cassandra liên quan thời gian giữ tombstone trước khi đủ điều kiện garbage collection, cùng những điều kiện khác.

    Ngày 1: A/B có tombstone; C offline giữ K cũ.
    Ngày 2: C chưa repair.
    Ngày 5: A/B vẫn có thông tin xóa.
    Ngày 6: Tombstone có thể đủ điều kiện purge
            tùy grace, compaction và điều kiện khác.
    Ngày 7: C quay lại. Nếu dấu xóa đã bị loại,
            dữ liệu cũ ở C có nguy cơ hồi sinh.

Đây là ví dụ rủi ro, **không** có nghĩa tombstone tự biến mất đúng lúc gc_grace_seconds trôi qua. Compaction, các SSTable còn chứa dữ liệu và điều kiện an toàn vẫn ảnh hưởng quá trình dọn.

### 5.3. TTL và gc_grace_seconds khác nhau

| Khái niệm | Vai trò |
|---|---|
| TTL | Khoảng thời gian một giá trị còn hiệu lực theo quy tắc |
| Tombstone | Thông tin xóa/hết hạn |
| gc_grace_seconds | Một yếu tố quyết định khi nào tombstone đủ điều kiện dọn |
| Compaction | Hợp nhất dữ liệu cũ và có thể loại dữ liệu/tombstone |
| Repair | Hòa giải các replica để xử lý mutation bị bỏ lỡ |

TTL 7 ngày **không** chứng minh mọi bytes của dữ liệu đã bị xóa vật lý tại đúng giây hết hạn.

### 5.4. Không giảm grace về 0 tùy tiện

Giảm grace chỉ để giải quyết cảnh báo tombstone có thể làm mất chứng cứ xóa trước khi replica offline được repair. Cần đánh giá:

- Replication factor, topology và consistency level.
- Replica có thể offline tối đa bao lâu.
- Lịch repair, phạm vi và thời gian hoàn tất.
- Retention của hinted handoff.
- Cơ chế compaction đang sử dụng.
- Hướng dẫn của đúng sản phẩm và phiên bản.

**Hinted handoff không thay thế hoàn toàn anti-entropy repair.** Hint có giới hạn thời gian và tình huống phục vụ. Replica ngắt mạng lâu có thể vẫn cần repair để hội tụ.

### 5.5. Tombstone-heavy query

Khi một partition có nhiều dữ liệu đã hết TTL hoặc bị DELETE, truy vấn có thể phải xét nhiều tombstone dù chỉ trả vài hàng sống. Điều này có thể tăng CPU, IO, latency p95/p99 và nguy cơ timeout.

Để cải thiện, nên đánh giá:

- Time bucketing và phạm vi truy vấn.
- Compaction strategy phù hợp workload TTL.
- Số lượng/kiểu DELETE.
- Cách phân trang.
- Thời hạn retention và tốc độ ghi dữ liệu.

Không nên giải quyết vấn đề hiệu năng bằng cách đánh đổi an toàn replica mà chưa hiểu tác động.

## 6. Consistency: DELETE được ACK nghĩa là gì?

### 6.1. Mức xác nhận ghi và đọc

Trong cụm RF=3, một DELETE được xác nhận theo write consistency level có thể hoàn tất trước khi mọi replica bắt kịp. Khi client đọc lại, read consistency và cơ chế hòa giải quyết định khả năng thấy dữ liệu mới hay cũ.

Ví dụ:

    Replica A: tombstone K
    Replica B: tombstone K
    Replica C: dữ liệu K cũ

Nếu read path không đủ bảo đảm phù hợp với nghiệp vụ,
client có thể tạm thời quan sát giá trị cũ.

Quorum và sự giao nhau giữa tập replica có thể cải thiện bảo đảm quan sát mutation, nhưng không nên lấy một công thức số lượng replica rồi khẳng định đúng tuyệt đối trong mọi race, kiểu timestamp hoặc topology.

### 6.2. Timeout không khẳng định xóa đã thất bại

    Client gửi DELETE K.
    Server áp dụng mutation.
    Response bị mất.
    Client nhận timeout.

Client không biết chắc thao tác đã áp dụng hay chưa. Retry cần idempotency và có thể cần version/generation để tránh xóa nhầm thực thể vừa được tạo lại cùng ID.

### 6.3. Read-after-delete khác physical purge

Một GET trả 404 sau DELETE chỉ chứng minh đường đọc đó không trả bản ghi tại thời điểm kiểm tra. Nó không chứng minh mọi replica, cache, search, snapshot và backup đã purge.

## 7. MongoDB: hard delete trong replica set

### 7.1. deleteOne và write concern

    db.learners.deleteOne({ _id: "L001" });

Với replica set, thay đổi được sao chép từ primary tới secondary theo cơ chế MongoDB. Nếu một ghi chỉ được xác nhận ở mức chưa đủ chống rollback sau failover, nó có thể chịu rủi ro mất trong những điều kiện nhất định.

Khi yêu cầu độ bền cao hơn, có thể chọn majority write concern trong phạm vi triển khai hỗ trợ:

    db.learners.deleteOne(
      { _id: "L001" },
      { writeConcern: { w: "majority" } }
    );

Majority không có nghĩa mọi secondary đã áp dụng tức thì, cũng không có nghĩa cache/search/backup được xóa tự động.

### 7.2. Change streams để cập nhật hệ dẫn xuất

    const stream = db.learners.watch([
      { $match: { operationType: "delete" } }
    ]);

    for await (const event of stream) {
      const key = event.documentKey;
      // Xóa các projection tương ứng.
      // Lưu resume token/checkpoint.
      console.log(key);
    }

Change streams phụ thuộc replica set/sharded deployment và có giới hạn lịch sử oplog/change stream. Worker offline lâu hơn retention có thể phải backfill/rebuild.

### 7.3. Xóa document không phải secure erase

Hard delete khỏi collection hoạt động không chứng minh bytes cũ đã bị ghi đè trong storage, journal hay backup. Khi phải xử lý dữ liệu nhạy cảm, cần một chính sách bảo mật và retention cho tất cả bản sao.

## 8. DynamoDB: DeleteItem, GSI, Streams và TTL

### 8.1. DeleteItem theo khóa

Ví dụ AWS SDK JavaScript v3:

    import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
    import {
      DynamoDBDocumentClient,
      DeleteCommand
    } from "@aws-sdk/lib-dynamodb";

    const client = DynamoDBDocumentClient.from(
      new DynamoDBClient({ region: "ap-southeast-1" })
    );

    await client.send(new DeleteCommand({
      TableName: "Learners",
      Key: { PK: "LEARNER#L001", SK: "PROFILE" }
    }));

### 8.2. Conditional delete

Nếu ứng dụng chỉ muốn xóa version 7:

    await client.send(new DeleteCommand({
      TableName: "Learners",
      Key: { PK: "LEARNER#L001", SK: "PROFILE" },
      ConditionExpression: "#v = :expected",
      ExpressionAttributeNames: { "#v": "version" },
      ExpressionAttributeValues: { ":expected": 7 }
    }));

Khi item đã đổi version 8, điều kiện không còn khớp, tránh xóa vô điều kiện dựa trên dữ liệu cũ. Điều kiện này có phạm vi tại item nguồn và không tự lan tới những hệ khác.

### 8.3. GSI eventual

Global Secondary Index của DynamoDB được cập nhật bất đồng bộ. Sau khi DeleteItem đã được xử lý ở bảng chính, một query trên GSI có thể tạm thời còn trả entry cũ.

Do đó không nên chỉ dựa vào GSI eventual để quyết định quyền hoặc giao dịch yêu cầu nhất quán ngay lập tức.

### 8.4. Streams và Global Tables

DynamoDB Streams có thể phát thay đổi item cho projection worker. Tùy cấu hình, sự kiện chứa key hoặc ảnh dữ liệu. Worker vẫn phải quản lý checkpoint, retry, thứ tự và retention của stream.

Global Tables lan truyền thay đổi giữa các Region theo chế độ sử dụng. DELETE đồng thời với UPDATE ở Region khác có thể chịu cơ chế giải quyết xung đột của sản phẩm. Không được tự suy rằng xóa ở một Region lập tức thắng mọi thao tác khác ở tất cả Region.

### 8.5. TTL không xóa tức thì

DynamoDB TTL đánh dấu item đủ điều kiện dọn sau khi expiresAt đã qua. Việc dọn là bất đồng bộ; item có thể còn được đọc cho đến lúc dịch vụ xóa. Nếu token hết hạn lúc 09:00, API phải kiểm tra expiresAt và từ chối token lúc 09:10 dù TTL chưa dọn item.

## 9. Redis: DEL, UNLINK và lỗi cache repopulation

### 9.1. DEL và UNLINK

    SET learner:L001 "cached-data"
    DEL learner:L001

DEL loại key khỏi keyspace logic. Với giá trị lớn:

    UNLINK large:key

UNLINK loại key khỏi keyspace rồi xử lý phần thu hồi bộ nhớ bất đồng bộ, giúp giảm rủi ro tác động độ trễ khi giải phóng cấu trúc lớn.

### 9.2. TTL và replication

    SET session:L001 "session-data" EX 3600
    TTL session:L001

Redis xử lý key hết hạn theo cơ chế active/passive expiry và sao chép trạng thái giữa primary/replica theo phiên bản/topology. Điều đó không đồng nghĩa snapshot, AOF/RDB hoặc backup đã xóa vật lý tại cùng thời điểm.

### 9.3. Cache bị điền lại dữ liệu cũ

    t0: Request A đọc L001 ACTIVE từ nguồn.
    t1: Request B hard delete L001 tại nguồn.
    t2: Worker DEL cache:L001.
    t3: Request A SET cache:L001 = ACTIVE từ kết quả cũ.
    t4: Request C GET cache:L001 -> ACTIVE.

Đây là lỗi **cache repopulation race**. Xóa cache một lần không đủ nếu request cũ còn có thể ghi lại.

Các lựa chọn:

- Cache key gắn generation hoặc version.
- Negative cache/business tombstone có ưu tiên khi so sánh version.
- Ghi cache có điều kiện, từ chối nguồn cũ.
- Deletion gate tại API/authorization.
- TTL thích hợp, nhưng không xem TTL như bảo đảm cấp quyền tức thời.

Redis Cluster có giới hạn với thao tác nhiều key trên các hash slot khác nhau; không nên mặc định một script hoặc transaction đa khóa luôn hoạt động nguyên tử trên toàn cụm.

## 10. Search index: dữ liệu đã xóa có thể vẫn xuất hiện

### 10.1. Delete và refresh

Ví dụ API kiểu Elasticsearch/OpenSearch:

    DELETE /learners_v1/_doc/L001

Search engine có thể xác nhận thao tác index/delete, nhưng query search chỉ quan sát thay đổi sau cơ chế refresh/visibility. Dữ liệu trong segment cũ cũng có thể được dọn vật lý muộn hơn.

### 10.2. Event cũ làm hồi sinh

    v10: LEARNER_UPDATED -> ACTIVE
    v11: LEARNER_DELETED

    Worker A xử lý v11: xóa document.
    Worker B nhận lại v10: index ACTIVE.

Nếu worker B ghi vô điều kiện, L001 hồi sinh trên search dù nguồn đã xóa. Cần versioned delete, business tombstone hoặc cơ chế kiểm soát phiên bản tương đương.

### 10.3. Reindex từ snapshot cũ

Nếu tạo index v2 từ snapshot trước DELETE v11, dữ liệu L001 ACTIVE có thể được index lại. Quy trình rebuild cần:

1. Xác định mốc snapshot.
2. Nhận các sự kiện sau mốc đó, gồm DELETE.
3. Hòa giải theo version/generation.
4. Đối soát trước khi chuyển alias.

Không nên rebuild từ ảnh chụp cũ rồi mặc định dữ liệu chính xác như nguồn hiện tại.

## 11. Event DELETE có phiên bản và business tombstone

### 11.1. Sự kiện xóa đầy đủ metadata tối thiểu

Nguồn L001 version 7. Khi xóa, có thể phát:

    {
      "eventId": "EVT-DEL-008",
      "tenantId": "T1",
      "entityType": "LEARNER",
      "entityId": "L001",
      "entityVersion": 8,
      "generationId": "GEN-001",
      "operation": "DELETE",
      "occurredAt": "2026-11-14T09:00:00Z"
    }

Sự kiện chỉ cần những trường phục vụ định vị và ngăn replay sai; không nên phát nguyên hồ sơ cá nhân đã xóa vào message bus nếu không có lý do.

### 11.2. Metadata chống hồi sinh

    {
      "entityId": "L001",
      "lastAppliedVersion": 8,
      "deleted": true,
      "generationId": "GEN-001"
    }

Một bản chiếu có thể xóa payload nhưng giữ metadata tối thiểu để biết UPDATE v7 là cũ.

### 11.3. Giả mã cập nhật bản chiếu

    apply(event):
        current = readProjectionMetadata(event.entityId)

        if current and event.generationId != current.generationId:
            handleGenerationConflict(event, current)

        if current and event.entityVersion <= current.lastAppliedVersion:
            return STALE_OR_DUPLICATE

        if event.operation == DELETE:
            removeVisiblePayload(event.entityId)
            saveTombstone(event.entityVersion)
        else:
            upsertProjection(event.payload, event.entityVersion)

Việc so sánh version và thay đổi trạng thái phải **nguyên tử hoặc được điều phối đúng**. Hai worker cùng đọc version cũ rồi PUT vô điều kiện vẫn có thể ghi sai thứ tự.

### 11.4. Cẩn trọng tái sử dụng ID

    v8: DELETE L001 thế hệ GEN-001.
    v9: CREATE L001 thế hệ GEN-002.
    DELETE v8 đến muộn sau v9.

Nếu chỉ dựa vào entityId, sự kiện cũ có thể xóa nhầm đối tượng mới. Phương án gồm không tái sử dụng ID, sử dụng generationId hoặc version đơn điệu xuyên vòng đời.

### 11.5. Retention của dấu xóa

Business tombstone có thể chứa ID liên quan dữ liệu cá nhân. Phải xác định:

- Event cũ có thể được giao lại trong bao lâu?
- Backup/snapshot cũ có thể phục hồi sau bao lâu?
- Có deletion ledger để chống hồi sinh sau khi marker hết retention không?
- Metadata nào thực sự cần giữ và ai được truy cập?

Không giữ vô hạn không có lý do, cũng không dọn quá sớm rồi mở đường cho dữ liệu cũ xuất hiện lại.

## 12. Dual write/delete và transactional outbox

### 12.1. Vì sao chuỗi lệnh xóa có thể để lại dữ liệu?

    await source.deleteLearner(learnerId);
    await redis.del("learner:" + learnerId);
    await search.deleteDocument(learnerId);
    await dashboardView.deleteByLearner(learnerId);

Nếu tiến trình chết sau dòng đầu, nguồn đã xóa nhưng cache/search/read model chưa xử lý. Các hệ độc lập không tự tạo một transaction chung chỉ vì code gọi liên tiếp.

### 12.2. Outbox khi nguồn hỗ trợ transaction

    BEGIN
      Xác thực yêu cầu xóa.
      Ghi deletion version/generation.
      Xóa hoặc chuyển trạng thái nguồn theo chính sách.
      INSERT OUTBOX(LEARNER_DELETED, L001, version=8).
    COMMIT

Worker đọc sự kiện, cập nhật những bản chiếu và lưu checkpoint. Outbox giảm khoảng trống “đã commit xóa nhưng không còn event”, nhưng **không bảo đảm consumer chỉ xử lý một lần**.

Vẫn cần retry, idempotency, version check, dead-letter queue và khả năng đối soát.

### 12.3. CDC và retention

Change Data Capture có thể đọc mutation đã commit từ nguồn. Nhưng change log/stream có retention và phạm vi ordering nhất định. Nếu consumer offline quá lâu, không được mặc định nó có thể replay mọi DELETE từ vô hạn; cần backfill/rebuild dựa trên nguồn và deletion ledger.

### 12.4. Fan-out sang nhiều kho

    Delete API
       |
       v
    Source + Outbox
       |
       v
    Event bus
       |------------> Cache invalidation
       |------------> Search cleanup
       |------------> Read model cleanup
       |------------> File cleanup
       |------------> Analytics cleanup
       |
       v
    Deletion job / reconciliation

Đường xóa phải bao phủ mọi bản sao thực tế, không chỉ những nơi được nhớ đến khi viết một handler.

## 13. Xóa dữ liệu phi chuẩn hóa và dữ liệu liên quan

Một Learner có thể xuất hiện ở:

    Learner source
      +-- Enrollment
      +-- Progress
      +-- LearningActivity
      +-- LearnerCourseView
      +-- Search index
      +-- Redis session/cache
      +-- File bài nộp
      +-- Analytics, log, export, backup

Hard delete Learner document không tự xóa mọi Enrollment hoặc LearningActivity nếu không có cascade hay workflow tương ứng.

### 13.1. Phải thiết kế đường tìm dữ liệu để xóa

Nếu activity được phân vùng theo (learnerId, activityDay), muốn xóa mọi activity phải xác định các ngày/bucket. Nếu một read model chỉ tra theo courseId, cần reverse lookup hoặc bảng mapping để tìm mọi bản ghi thuộc learnerId.

**Thiết kế theo truy vấn không chỉ phục vụ đọc; nó phải tính cả truy vấn xóa và retention.**

### 13.2. Fan-out delete

Xóa một triệu hoạt động có thể tạo:

- Nhiều mutation/tombstone.
- Backlog ở projection worker.
- Tải IO và compaction cao.
- Thời gian xóa kéo dài.

Cần batch, giới hạn tốc độ, checkpoint và đường tiếp tục sau lỗi. Nếu chính sách đòi hỏi ngừng hiển thị ngay, phải chặn tại API trước khi xóa vật lý hoàn tất.

## 14. Deletion workflow theo nhiều giai đoạn

Một trạng thái mẫu:

    REQUESTED
       |
       v
    ACCESS_BLOCKED
       |
       v
    SOURCE_DELETED
       |
       v
    PROJECTIONS_CLEANING
       |
       v
    ACTIVE_COPIES_CLEANED
       |
       v
    RETENTION_PENDING
       |
       v
    COMPLETED

**REQUESTED:** Đã tiếp nhận và xác thực yêu cầu.

**ACCESS_BLOCKED:** API/authorization không phục vụ dữ liệu đã thu hồi dù cache/search trễ.

**SOURCE_DELETED:** Đã áp dụng quyết định xóa ở nguồn theo consistency/durability level được chọn.

**PROJECTIONS_CLEANING:** Worker đang dọn những bản sao.

**ACTIVE_COPIES_CLEANED:** Các kho đang phục vụ đã được đối soát theo hợp đồng.

**RETENTION_PENDING:** Backup/snapshot còn trong thời hạn giữ được xác định.

**COMPLETED:** Chỉ dùng khi các điều kiện quy trình đã cam kết được xác minh.

### 14.1. Checkpoint

    DeleteJob JOB-1001
    Target = LEARNER#L001

    Source profile:      DONE
    Enrollment:          DONE
    LearningActivity:    IN_PROGRESS, cursor=page-25
    Search:              PENDING
    Redis cache:         DONE
    Submitted files:     PENDING
    Backup:              RETENTION_PENDING

Nếu worker chết, job có thể tiếp tục từ checkpoint. Nhưng mỗi DONE phải nói rõ nghĩa: đã gửi lệnh, đã không thể đọc, đã đối soát hay đã purge?

## 15. Backup, snapshot và restore có thể làm dữ liệu hồi sinh

### 15.1. Backup cũ vẫn có thể hợp lệ theo retention

    Ngày 1: Backup chứa L001.
    Ngày 2: L001 yêu cầu xóa.
    Ngày 2: Source hard delete thành công.
    Ngày 3: Backup ngày 1 còn trong retention 30 ngày.

Xóa ở nguồn không tự xóa chọn lọc dữ liệu trong mọi backup. Với immutable backup, chính sách xóa và retention cần được xác định rõ, gồm cả bảo vệ truy cập và mã hóa.

### 15.2. Restore phải replay quyết định xóa

Nếu ngày 10 khôi phục backup ngày 1 mà không phát lại quyết định xóa ngày 2, L001 có thể xuất hiện trở lại.

Một quy trình restore:

1. Xác định mốc snapshot.
2. Lấy deletion ledger/event có hiệu lực sau mốc đó.
3. Áp dụng các quyết định xóa trước khi mở dữ liệu restored cho người dùng.
4. Rebuild cache/search/read model từ nguồn đã hòa giải.
5. Kiểm tra quyền và đối soát.

### 15.3. Xóa mật mã

**Crypto-erasure** có thể dùng việc hủy khóa giải mã theo nhóm dữ liệu để khiến ciphertext không còn đọc được. Nhưng để bảo đảm mục tiêu, cần chắc chắn không có plaintext hoặc khóa dự phòng còn khả dụng trong cache, log, snapshot hay hệ khác.

## 16. TTL: hết hiệu lực và dọn vật lý là hai mốc

| Hệ | Ngữ nghĩa liên quan |
|---|---|
| Cassandra | TTL hết hạn tạo trạng thái xóa; dọn vật lý qua compaction khi đủ điều kiện |
| MongoDB TTL index | Background deletion; không cam kết xóa chính xác từng giây |
| DynamoDB TTL | Item hết hạn được dọn bất đồng bộ; có thể tạm thời còn |
| Redis EXPIRE | Cơ chế active/passive expiry và replication riêng |
| Search index | Retention job/ILM hoặc event xóa tùy cấu hình |

Nếu token truy cập hết hạn 09:00 nhưng DynamoDB TTL chưa xóa item đến 09:20, API phải **từ chối token lúc 09:10**. Thời điểm hết quyền thuộc logic xác thực, không phải lịch thu hồi bytes của database.

### 16.1. Dữ liệu đến muộn

Một cảm biến đo sự kiện ngày 1 nhưng đến hệ ngày 40. Nếu retention là 30 ngày **từ thời điểm đo**, cấp TTL thêm 30 ngày từ lúc ingest sẽ giữ dữ liệu lâu hơn quy tắc.

Phải thống nhất event time hay ingest time, cách xử lý sự kiện quá hạn và việc có cho phép ghi lại dữ liệu thuộc bucket đã xóa hay không.

## 17. Bảo mật và dữ liệu cá nhân

### 17.1. Không dùng bản sao cũ để cấp quyền

Một tài khoản đã bị xóa ở nguồn nhưng search/cache chưa cập nhật. Nếu API lấy bản sao đó rồi cung cấp thông tin nhạy cảm, quyết định xóa chưa có hiệu lực ở đường phục vụ.

Có thể sử dụng **deletion gate** hoặc cơ chế authorization đáng tin cậy để chặn trước, trong khi các worker tiếp tục dọn dữ liệu dẫn xuất.

### 17.2. Metadata xóa vẫn cần bảo vệ

Business tombstone chứa ID và deletedAt có thể vẫn liên quan đến một cá nhân. Cần xác định mục đích sử dụng, quyền truy cập, retention và phương án loại metadata khi không còn cần chống hồi sinh.

### 17.3. Nghĩa vụ giữ dữ liệu khác nhau

Một đơn hàng đã thanh toán có thể liên quan chứng từ, hoàn tiền và kiểm toán. Xóa tài khoản không nhất thiết có nghĩa xóa ngay mọi dữ liệu giao dịch nếu có nghĩa vụ lưu trữ hợp pháp. Cần phối hợp với chính sách pháp lý/bảo mật thay vì áp dụng một câu DELETE cho mọi loại dữ liệu.

## 18. Giám sát và đối soát

### 18.1. Các chỉ số quan trọng

| Chỉ số | Mục đích |
|---|---|
| Delete requests accepted | Số yêu cầu đã tiếp nhận |
| Source delete success/failure | Trạng thái nguồn |
| Replica repair health | Nguy cơ replica bỏ lỡ mutation |
| Tombstone/compaction metrics | Chi phí xử lý dấu xóa |
| Pending deletion jobs | Công việc còn dang dở |
| Oldest pending delete age | Job bị kẹt quá lâu |
| CDC/outbox lag | Độ trễ đồng bộ bản sao |
| Retry/DLQ count | Event xóa lỗi |
| Search visibility lag | Chỉ mục còn hiển thị cũ |
| Cache invalidation lag | Cache chưa hội tụ |
| Source–projection mismatch | Bản sao không đúng trạng thái nguồn |
| Restore deletion replay failures | Nguy cơ hồi sinh từ backup |

### 18.2. Độ trễ lan truyền

\[
\text{DeletePropagationLag}
= t_{\text{bản sao không còn hiển thị}}
- t_{\text{source commit}}.
\]

Nên đo cho từng hệ theo p50/p95/p99, không chỉ thời gian gửi DELETE. Search refresh và cache repopulation có thể khiến dữ liệu vẫn được phục vụ sau khi worker báo ACK.

### 18.3. Đối soát

    for each deletionJob marked activeCopiesCleaned:
        verify authoritative source state
        verify search no longer serves entity
        verify read models no longer serve entity
        verify cache cannot return stale entity
        record backup/retention status
        repair or alert on mismatches

Một GET trả 404 ở một replica không chứng minh toàn bộ cụm đã hội tụ; việc kiểm tra phải hiểu semantics của hệ được dùng.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi DELETE ACK là đã purge mọi nơi | Cam kết sai | Phân biệt các mốc xóa |
| Dọn tombstone trước repair | Zombie data | Grace/repair an toàn |
| Coi hinted handoff thay thế repair | Replica offline dài ngày bỏ lỡ xóa | Anti-entropy repair |
| Quên search/cache | Dữ liệu cũ tiếp tục hiển thị | Outbox/CDC và deletion gate |
| Event UPDATE cũ đến sau DELETE | Bản chiếu hồi sinh | Version/CAS/tombstone |
| Chỉ DEL cache một lần | Request cũ điền lại cache | Version-aware cache |
| Dùng GSI eventual xác nhận xóa ngay | Vẫn có entry cũ | Kiểm tra nguồn |
| Dùng TTL làm đồng hồ hết quyền | Item hết hạn còn được chấp nhận | Kiểm tra expiresAt |
| Restore snapshot cũ mà không replay xóa | Hồ sơ xuất hiện lại | Deletion ledger |
| Tái sử dụng ID không có generation | Xóa nhầm thực thể mới | ID ổn định/generation |
| Xóa hồ sơ quên dữ liệu dẫn xuất | Rò dữ liệu | Data inventory |
| Xóa hàng triệu row không giới hạn tải | Tải ghi/tombstone tăng | Batch/checkpoint/bucket |
| Không đo lag và drift | Lỗi tồn tại lâu | Metrics/reconciliation |
| Giữ metadata xóa nhạy cảm vô hạn | Rủi ro quyền riêng tư | Retention phù hợp |

## 20. Bài tập thực hành

### Bài 1. Phân loại những mốc xóa

Cho:

1. DELETE được ACK.
2. GET ở nguồn không còn thấy bản ghi.
3. Replica offline nhận tombstone qua repair.
4. Compaction dọn SSTable cũ.
5. Redis/search không còn trả dữ liệu.
6. Backup cũ hết retention.

Hãy phân loại vào **source commit, logical visibility, replica propagation, physical purge, derived-data cleanup và backup retention**. Vì sao không thể gộp mọi mốc vào một trạng thái DONE?

### Bài 2. Zombie data trong Cassandra

RF=3: A/B nhận DELETE(K), C offline. Sau nhiều ngày, dấu xóa bị purge khỏi A/B trước khi C repair.

Giải thích nguy cơ hồi sinh, vai trò của gc_grace_seconds và repair. Có nên giảm grace về 0 chỉ để giảm cảnh báo tombstone không? Nêu điều kiện cần xem xét.

### Bài 3. Versioned delete

    v10: LEARNER_UPDATED, status=ACTIVE
    v11: LEARNER_DELETED

Worker nhận v11 rồi nhận lại v10. Hãy thiết kế business tombstone chứa lastAppliedVersion, nêu cách từ chối v10 và vai trò của generationId khi tạo thực thể mới cùng ID.

### Bài 4. Cache repopulation

    t0: A đọc user ACTIVE.
    t1: B DELETE user ở nguồn.
    t2: Worker DEL cache.
    t3: A SET cache bằng dữ liệu ACTIVE cũ.

Giải thích lỗi. Đề xuất hai cách bảo vệ cache và một cách bảo vệ API authorization khi bản sao chưa hội tụ.

### Bài 5. TTL và quyền truy cập

Token hết hạn lúc 09:00 nhưng DynamoDB TTL chỉ dọn item lúc 09:20. API có được cho phép token lúc 09:10 không? Tại sao cần kiểm tra expiresAt? Backup lúc 08:30 có thể còn token sau 09:00 không?

### Bài 6. Quy trình xóa tài khoản đa kho

Hệ lưu hồ sơ tại MongoDB, sự kiện tại Cassandra, Enrollment projection tại DynamoDB, session ở Redis, search index và file trong object storage.

Hãy thiết kế:

- Data inventory và điểm chặn quyền.
- Outbox/CDC event chứa ID, version và generation.
- Các worker xóa từng kho, xử lý retry/idempotency.
- Checkpoint, DLQ và đối soát.
- Quy trình restore backup không hồi sinh dữ liệu.
- Điều kiện chính xác trước khi báo COMPLETED.

### Bài 7. Retention dữ liệu cảm biến

Một thiết bị phát 2.000 sự kiện/giây. Số sự kiện/ngày:

\[
2.000 \times 86.400 = 172.800.000.
\]

Tại sao DELETE từng sự kiện cũ có thể gây tải lớn? Đề xuất time bucket, TTL và chiến lược compaction/repair an toàn. Nếu dữ liệu ngày 1 đến muộn ngày 45, cần xử lý thế nào với retention 30 ngày tính theo thời điểm đo?

### Bài 8. Soft delete hay hard delete cho đơn hàng?

Một đơn đã thanh toán có dữ liệu hoàn tiền và chứng từ cần đối soát. Người dùng muốn xóa tài khoản. Hãy phân tích cách tách dữ liệu nhận diện cần xóa hoặc ẩn danh với dữ liệu giao dịch có yêu cầu giữ, cùng ảnh hưởng tới search/cache/backup và việc cung cấp bằng chứng xóa.

## 21. Tổng kết

Trong NoSQL phân tán, **hard delete** thường chỉ là bước đầu của một chuỗi công việc. **Tombstone** giúp những hệ như Cassandra giữ bằng chứng rằng dữ liệu cũ đã bị xóa đủ lâu để replica bỏ lỡ mutation có thể được sửa mà không làm dữ liệu hồi sinh. **Compaction, gc_grace_seconds và anti-entropy repair** liên quan trực tiếp tới mức an toàn của việc dọn dấu xóa.

Ở tầng ứng dụng, các bản sao có thể nằm trong **replica, GSI, cache, search, read model, file, log và backup**. Outbox/CDC, event có version/generation, business tombstone, idempotent worker và workflow đối soát giúp quyết định xóa được lan truyền có thể phục hồi.

Khi thiết kế một tính năng xóa, hãy luôn trả lời rõ:

1. **Xóa dữ liệu nào ở những nơi nào?**
2. **Khi nào dữ liệu không còn được phục vụ và khi nào được dọn vật lý?**
3. **Cơ chế gì ngăn replica, event hoặc snapshot cũ làm dữ liệu hồi sinh?**
4. **Nếu một bước thất bại, quy trình retry/repair thế nào?**
5. **Làm sao kiểm chứng các bản sao đã đạt mức xóa được cam kết?**

Một hệ thống đáng tin cậy không đánh đồng **DELETE thành công** với **mọi nơi đã quên dữ liệu**. Nó phải có phạm vi bảo đảm rõ ràng, truyền tải thông tin xóa đúng, kiểm soát sự kiện cũ và theo dõi toàn bộ vòng đời dữ liệu.
