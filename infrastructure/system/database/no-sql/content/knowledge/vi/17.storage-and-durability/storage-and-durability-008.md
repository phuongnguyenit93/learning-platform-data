# Dấu xóa, thời gian giữ lại và nguy cơ dữ liệu cũ xuất hiện lại

## 1. Vì sao đã xóa mà dữ liệu có thể quay trở lại?

Khi thực hiện lệnh xóa trong một cơ sở dữ liệu NoSQL phân tán, trực giác thường là:

> “Lệnh DELETE thành công thì bản ghi không còn, và các máy khác cũng sẽ không thấy nó nữa.”

Thực tế phức tạp hơn. Một bản ghi có thể được sao chép qua nhiều **replica**, lưu trong nhiều file bất biến trên đĩa, xuất hiện trong cache hoặc read model. Một số replica có thể đang mất kết nối đúng lúc lệnh xóa được thực hiện.

Hãy xét ví dụ một ứng dụng lưu giỏ hàng:

~~~text
Khóa nghiệp vụ: (userId=U42, itemId=P100)
Giá trị: quantity=2
Replication factor: 3

Replica A: quantity=2
Replica B: quantity=2
Replica C: quantity=2
~~~

Khi người dùng xóa P100 khỏi giỏ, hệ thống có thể ghi một **dấu xóa (tombstone)** để biểu thị rằng giá trị cũ không còn được xem là hợp lệ:

~~~text
T0: Cả A, B, C đều có quantity=2
T1: C bị mất kết nối
T2: Lệnh DELETE đến A, B
T3: A, B có dấu xóa; C vẫn giữ quantity=2 cũ
~~~

Nếu sau đó cơ chế dọn dẹp **loại bỏ dấu xóa quá sớm**, C có thể trở lại và mang theo giá trị cũ. Các replica còn lại không còn chứng cứ rằng `quantity=2` đã bị xóa. Trong một số điều kiện hợp nhất dữ liệu, giá trị cũ có thể được chấp nhận trở lại. Hiện tượng này thường được gọi là **zombie data**, **data resurrection** hoặc **dữ liệu cũ xuất hiện lại**.

Bài học này giải thích cơ chế tombstone, lý do phải giữ nó một khoảng thời gian, mối liên hệ với compaction và repair, những giới hạn của tham số `gc_grace_seconds` trong Apache Cassandra, cùng cách thiết kế và vận hành hệ NoSQL tránh phục hồi nhầm bản ghi đã xóa.

> **Ý chính:** Một dấu xóa không chỉ là “dữ liệu cần dọn”. Trong cơ sở dữ liệu phân tán, nó còn có thể là **thông tin cần thiết để các replica phân xử giữa giá trị cũ và lệnh xóa mới hơn**. Loại bỏ dấu xóa trước khi mọi nơi có thể chứa dữ liệu cũ đã được xử lý là một rủi ro về tính đúng đắn, không đơn thuần là vấn đề tiết kiệm dung lượng.

## 2. Các khái niệm cần phân biệt

### 2.1. Xóa logic và xóa vật lý

**Xóa logic (logical deletion)** làm cho một giá trị không còn được coi là hiện hành theo quy tắc đọc và giải quyết xung đột. Nó có thể được biểu diễn bằng tombstone, trạng thái `deleted=true` hoặc một marker khác.

**Xóa vật lý (physical deletion/reclamation)** thực sự loại bỏ byte lưu trữ khỏi cấu trúc đang được database quản lý, thường thông qua compaction, garbage collection hoặc quy trình dọn riêng.

~~~text
Ghi dữ liệu
    |
    v
Giá trị có hiệu lực
    |
    v
DELETE hoặc TTL hết hạn
    |
    v
Dữ liệu không còn được đọc như giá trị sống
    |
    v
Dấu xóa vẫn cần tồn tại để chặn dữ liệu cũ
    |
    v
Đủ điều kiện thu gom theo chính sách và trạng thái hệ
    |
    v
Compaction/garbage collection thu hồi dung lượng
~~~

Hai bước không nhất thiết xảy ra đồng thời. Một truy vấn trả “không tìm thấy” **không chứng minh** mọi bản sao, file đĩa, backup và log đã không còn dữ liệu.

### 2.2. Tombstone là gì?

**Tombstone** là một bản ghi/marker có ý nghĩa “giá trị hoặc phạm vi giá trị này đã bị xóa”, thường kèm timestamp hoặc metadata phiên bản để so với các bản ghi cũ.

Ví dụ khái niệm:

~~~text
Giá trị cũ:
  key = U42#P100
  quantity = 2
  writeTimestamp = 100

Dấu xóa:
  key = U42#P100
  deleted = true
  deleteTimestamp = 200
~~~

Nếu cơ chế hợp nhất dùng timestamp phiên bản, dấu xóa tại `200` có thể thắng giá trị cũ tại `100`, khiến giá trị cũ không được trả về.

Ví dụ này là **mô hình giải thích**, không phải định dạng byte tombstone thực tế của tất cả NoSQL. Cassandra có các dạng dấu xóa và quy tắc liveness/timestamp riêng; MongoDB, DynamoDB, Redis và RocksDB không có chung một API xóa hay cùng tham số giữ tombstone.

### 2.3. Tombstone không giống soft delete

Một ứng dụng có thể đặt:

~~~json
{
  "userId": "U42",
  "state": "DELETED",
  "deletedAt": "2026-11-14T08:00:00Z"
}
~~~

Đây là **soft delete ở tầng nghiệp vụ**. Document vẫn tồn tại và được ứng dụng quyết định ẩn hay hiển thị. Một tombstone của storage engine thường không phải document có thể `SELECT` như trên; nó là metadata giúp engine biểu diễn xóa và hợp nhất dữ liệu.

| Tiêu chí | Soft delete ứng dụng | Tombstone storage engine |
|---|---|---|
| Được tạo bởi | Logic nghiệp vụ | Lệnh xóa/TTL hoặc cơ chế engine |
| Hình thức | Trạng thái/trường trong record | Marker trong hệ lưu trữ |
| Có thể query như record thường? | Thường có, nếu không lọc | Thường không theo đường đọc thông thường |
| Mục đích chính | Quản lý vòng đời, khôi phục, audit | Chặn giá trị cũ và truyền trạng thái xóa |
| Dọn vật lý | Cần cơ chế riêng | Engine xử lý khi đủ điều kiện |
| Có dùng chung được không? | Có | Có, nhưng là hai lớp khác nhau |

Một hệ có thể dùng **soft delete ở nguồn** để lưu ý nghĩa nghiệp vụ, sau đó dùng **hard delete** và tombstone ở các bản sao theo lịch retention. Không nên đồng nhất hai lớp.

### 2.4. TTL và tombstone

**TTL (Time To Live)** xác định thời gian sống của dữ liệu. Khi TTL kết thúc, một số engine như Cassandra cần biểu diễn giá trị đã hết hạn bằng cơ chế tombstone để tránh dữ liệu cũ được xem là còn sống.

Vì thế TTL không phải “cách xóa miễn phí”. Với nhiều giá trị có TTL ngắn, hệ có thể tích lũy số lượng tombstone lớn và chịu chi phí đọc/compaction.

Những hệ khác có TTL ở cấp item hoặc key với quá trình dọn riêng; không được suy rằng TTL của Redis hay DynamoDB có đúng semantics `gc_grace_seconds` của Cassandra.

## 3. Bối cảnh lưu trữ: vì sao LSM-tree hay cần dấu xóa?

Nhiều NoSQL ghi dữ liệu bằng mô hình **Log-Structured Merge-tree (LSM-tree)** hoặc những biến thể: ghi mới thường vào vùng bộ nhớ/append log, sau đó flush thành các file đã sắp xếp (**SSTable** trong Cassandra).

Một mô hình khái niệm:

~~~text
Client WRITE/DELETE
       |
       v
Commit log / WAL (tùy engine)
       |
       v
Memtable
       |
       v  Flush
SSTable A   SSTable B   SSTable C
       \       |       /
        \      |      /
             Compaction
                |
                v
        SSTable hợp nhất mới
~~~

### 3.1. Vì sao không sửa ngay tất cả file?

Một file SSTable đã ghi thường không được chỉnh từng byte cho một lần update/delete. Giá trị mới hoặc tombstone được ghi như **phiên bản mới hơn**, rồi quá trình đọc/hợp nhất quyết định giá trị có hiệu lực.

Ví dụ:

~~~text
SSTable cũ:
  U42#P100 -> quantity=2, timestamp=100

Memtable hoặc SSTable mới:
  U42#P100 -> TOMBSTONE, timestamp=200
~~~

Khi đọc, engine phải biết tombstone tại `200` che giá trị tại `100`. Nếu chỉ xóa marker trong file mới nhưng chưa loại giá trị ở file cũ, giá trị `quantity=2` có thể xuất hiện lại ngay trên cùng node. Đây là lý do compaction không được thu gom tombstone chỉ dựa trên “nó đã cũ hơn 10 ngày”; còn phải xét những bản dữ liệu có khả năng bị nó che.

### 3.2. Hai rủi ro riêng biệt

Có ít nhất hai nhóm rủi ro:

1. **Trong cùng một node:** tombstone bị thu gom trong khi một file cũ vẫn còn giá trị mà nó che.
2. **Giữa các replica:** một replica không nhận delete, sau khi các replica khác thu gom tombstone thì replica cũ quay lại.

Storage engine phải xử lý cả hai theo cơ chế compaction/repair tương ứng. Một tham số thời gian giữ tombstone giúp giảm rủi ro replica cũ, nhưng không thể thay thế toàn bộ điều kiện an toàn khi compaction.

### 3.3. Tombstone cũng có chi phí

Khi đọc một partition có nhiều tombstone, engine có thể phải xét nhiều marker để tìm hàng còn sống. Chi phí có thể thể hiện ở:

- Nhiều SSTable phải được đọc;
- Tăng số cell/row cần kiểm tra;
- CPU/I/O và độ trễ tăng;
- Compaction tiêu tốn tài nguyên;
- Dung lượng giảm chậm hơn kỳ vọng;
- Truy vấn có thể bị cảnh báo hoặc từ chối theo ngưỡng tombstone của engine.

**Giữ tombstone càng lâu không phải lúc nào cũng tốt**, nhưng giảm thời gian giữ tùy tiện có thể làm hỏng dữ liệu. Cần cân bằng giữa an toàn xóa và chi phí vận hành.

## 4. Cassandra: bản sao, write timestamp và dấu xóa

Apache Cassandra là ví dụ nổi bật về vấn đề **dấu xóa – thời gian giữ lại – dữ liệu hồi sinh**, vì dữ liệu được phân tán trên nhiều replica và dùng timestamp để phân xử các giá trị trong nhiều trường hợp.

### 4.1. Replication factor và consistency level

Giả sử một keyspace có replication factor (**RF**) là 3 trong một data center:

~~~text
Partition U42 -> replica A, B, C
~~~

Một thao tác với consistency level `QUORUM` có thể được xác nhận khi số replica đáp ứng yêu cầu quorum (với RF=3, thường cần 2 replica theo trường hợp đơn giản này).

Cần phân biệt:

- **Replica count**: bao nhiêu nơi giữ dữ liệu.
- **Consistency level**: bao nhiêu phản hồi cần thiết để một thao tác đạt mức nhất quán yêu cầu.
- **Replica availability**: replica nào có thể trả lời tại thời điểm đó.
- **Anti-entropy repair**: cơ chế đồng bộ để các replica hội tụ khi từng nơi có dữ liệu khác nhau.

Một thao tác DELETE đạt `QUORUM` **không đồng nghĩa mọi replica đã nhận dấu xóa**. Replica thứ ba có thể đang offline.

### 4.2. Timestamp trong giải quyết xung đột

Trong Cassandra, các mutation có **timestamp** (thường ở mức microseconds theo semantics CQL) để phân xử phiên bản dữ liệu. Một mutation có timestamp mới hơn có thể thắng mutation cũ trong phạm vi giá trị liên quan, theo quy tắc reconciliation của Cassandra.

Ví dụ khái niệm:

~~~text
WRITE quantity=2   timestamp=100
DELETE quantity    timestamp=200

=> Tombstone(200) che giá trị(100)
~~~

Nếu một ghi khác có timestamp 300 đến sau:

~~~text
WRITE quantity=5   timestamp=300
~~~

thì nó có thể trở thành trạng thái mới hợp lệ vì timestamp lớn hơn tombstone. Đây là **tái tạo dữ liệu bằng một ghi mới**, khác với zombie data do replica cũ chưa biết lệnh xóa.

**Quan trọng:** timestamp của Cassandra không phải tự động một sequence nghiệp vụ tuyệt đối hoàn hảo. Clock skew hoặc ứng dụng tự cấp timestamp có thể tạo thứ tự sai. Không nên suy rằng “request đến API sau” luôn có write timestamp lớn hơn trong mọi tình huống.

### 4.3. DELETE không chỉ là loại một cell

Cassandra có thể phát sinh tombstone ở những phạm vi khác nhau:

- Một cell/cột;
- Một row;
- Một khoảng clustering rows (**range tombstone**);
- Một partition;
- Những phần tử trong cấu trúc collection theo semantics tương ứng;
- Giá trị hết hạn do TTL.

Mỗi dạng có ảnh hưởng khác nhau khi đọc và compaction. Một lệnh xóa rộng phạm vi có thể tạo các marker che nhiều bản ghi thay vì một marker riêng cho từng cell.

### 4.4. Ví dụ bảng dữ liệu

Giả sử ứng dụng lưu item giỏ hàng:

```sql
CREATE TABLE cart_items_by_user (
    user_id text,
    item_id text,
    quantity int,
    updated_at timestamp,
    PRIMARY KEY ((user_id), item_id)
) WITH gc_grace_seconds = 864000;
```

`864000` giây tương đương **10 ngày**, thường được dùng để minh họa một cửa sổ giữ tombstone của Cassandra. Đây không phải lựa chọn tối ưu cho mọi hệ. Việc thay giá trị thực tế cần dựa vào topology, repair cadence, chính sách downtime và phiên bản sản phẩm.

Ghi:

```sql
INSERT INTO cart_items_by_user (
    user_id, item_id, quantity, updated_at
)
VALUES (
    'U42', 'P100', 2, toTimestamp(now())
);
```

Xóa:

```sql
DELETE FROM cart_items_by_user
WHERE user_id = 'U42'
  AND item_id = 'P100';
```

Sau khi xóa thành công, một truy vấn:

```sql
SELECT *
FROM cart_items_by_user
WHERE user_id = 'U42';
```

có thể không còn trả hàng `P100`. Nhưng điều đó **không chứng minh mọi tombstone đã được dọn hoặc mọi replica đã nhận lệnh xóa**.

## 5. Dòng thời gian zombie data khi một replica offline quá lâu

Đây là kịch bản cốt lõi cần hiểu.

### 5.1. Trạng thái ban đầu

~~~text
Replication factor = 3

           Key U42#P100, quantity=2, timestamp=100

             Replica A     Replica B     Replica C
             ---------     ---------     ---------
                v100          v100          v100
~~~

### 5.2. C ngừng hoạt động

C mất kết nối trong khi A và B vẫn phục vụ request.

~~~text
T1:
  A online
  B online
  C offline (vẫn có v100 trên đĩa)
~~~

### 5.3. Lệnh DELETE đến A và B

Ứng dụng xóa P100. Theo yêu cầu consistency đã chọn, A và B nhận tombstone timestamp 200, và thao tác được xác nhận.

~~~text
T2: DELETE U42#P100 (timestamp=200)

             Replica A     Replica B     Replica C
             ---------     ---------     ---------
             tombstone200  tombstone200     v100
                                             ^
                                         vẫn offline
~~~

Nếu C trở lại **trong cửa sổ tombstone còn được giữ** và repair/hệ đồng bộ áp dụng trạng thái xóa, C có thể nhận thông tin rằng v100 đã bị xóa.

### 5.4. A và B thu gom tombstone

Giả sử C offline lâu hơn thời gian giữ tombstone, A và B trải qua compaction với đầy đủ điều kiện thu gom. Khi đó marker 200 và các giá trị cũ mà nó che có thể bị loại bỏ khỏi lưu trữ hiện hành.

~~~text
T3: Sau thời gian giữ và khi tombstone thực sự được purge

             Replica A     Replica B     Replica C
             ---------     ---------     ---------
             không có      không có         v100
             dữ liệu sống  dữ liệu sống      ^
                                             |
                                         chưa nhận DELETE
~~~

**Chỉ hết thời gian `gc_grace_seconds` chưa đủ khẳng định dấu xóa đã bị dọn.** Tombstone thực sự được purge tùy compaction và các điều kiện an toàn của engine. Kịch bản này giả định việc purge đã xảy ra.

### 5.5. C quay lại

C vẫn mang giá trị v100. Khi hệ so dữ liệu giữa replica, các nơi A/B không còn tombstone 200 để áp đặt trạng thái xóa. Trong những điều kiện phù hợp, dữ liệu cũ từ C có thể được truyền sang nơi khác hoặc được trả lại như giá trị còn sống.

~~~text
T4: Replica C quay lại

             A               B               C
         không thấy      không thấy        v100
              \             |              /
               \            |             /
                     Anti-entropy/read
                             |
                             v
              v100 có nguy cơ được chấp nhận lại
~~~

Đó là **zombie data**. Người dùng đã xóa item, sau đó item xuất hiện lại như thể lệnh xóa chưa từng xảy ra.

### 5.6. Điều kiện để kịch bản xảy ra

Không phải mọi lần replica offline quá 10 ngày đều chắc chắn hồi sinh dữ liệu. Rủi ro đòi hỏi một tổ hợp điều kiện, ví dụ:

1. Replica C có giá trị cũ chưa nhận delete.
2. Tombstone trên các replica khác đã được purge.
3. Không còn cơ chế khác mang thông tin xóa đến C trước khi nó tham gia hợp nhất dữ liệu.
4. C được đưa trở lại và dữ liệu của nó có thể ảnh hưởng kết quả.

Nếu tombstone vẫn còn hoặc C được rebuild từ nguồn đúng thay vì đưa dữ liệu cũ vào, sự cố có thể được tránh. Chính sách vận hành nên ngăn **điều kiện rủi ro**, không chỉ dựa vào hy vọng hệ sẽ hội tụ.

## 6. gc_grace_seconds là gì và không phải là gì?

Trong Cassandra, `gc_grace_seconds` là tham số theo table liên quan đến khoảng thời gian **tombstone cần được giữ trước khi có thể được xem là ứng viên cho việc thu gom**, trong bối cảnh dữ liệu phân tán và các quy tắc compaction.

Ví dụ:

```sql
ALTER TABLE cart_items_by_user
WITH gc_grace_seconds = 864000;
```

Đây là lệnh minh họa thay cấu hình của bảng đã tồn tại. Không nên chạy trực tiếp lên production mà chưa đánh giá rủi ro và quy trình vận hành.

### 6.1. Điều tham số thể hiện

- Một khoảng thời gian tính bằng giây.
- Liên quan đến thời điểm tombstone đủ điều kiện được dọn.
- Cho phép thông tin xóa còn tồn tại một thời gian để replica bị bỏ sót có cơ hội được đồng bộ.
- Ảnh hưởng đến lượng tombstone và khả năng thu hồi dung lượng.
- Có ý nghĩa đặc biệt khi phối hợp với **repair cadence**, node downtime và topology.

### 6.2. Điều tham số **không** bảo đảm

**Không phải TTL của business row.** Bản ghi có thể bị coi là đã xóa từ lúc mutation xóa có hiệu lực; `gc_grace_seconds` không có nghĩa “người dùng còn nhìn thấy hàng trong 10 ngày”.

**Không phải lịch dọn chạy đúng giờ.** Sau khi đủ thời gian, tombstone có thể còn tồn tại lâu vì điều kiện compaction chưa đáp ứng.

**Không phải cơ chế tự sửa replica.** Đặt 10 ngày không tự chạy repair và không khiến replica offline tự nhận delete.

**Không phải lời hứa chống zombie vô điều kiện.** Nếu replica vắng quá lâu, repair không bao phủ hết hoặc có clock/timestamp sai, chỉ giữ 10 ngày không đủ.

**Không phải SLA xóa dữ liệu khỏi backup.** Snapshot, backup và bản xuất có retention riêng.

**Không áp dụng chung cho mọi NoSQL.** Redis, MongoDB, DynamoDB và các hệ khác có cơ chế delete/TTL khác nhau.

### 6.3. Vì sao “repair mỗi tuần, grace 10 ngày” là một ví dụ, không phải phép bảo đảm?

Một đội vận hành có thể dự kiến:

~~~text
gc_grace_seconds: 10 ngày
Repair toàn bộ dữ liệu: 7 ngày/lần
~~~

Ý tưởng là mỗi bản ghi được repair trước khi tombstone đủ tuổi bị purge.

Nhưng lịch **“chạy vào thứ bảy”** không chứng minh repair đã hoàn tất: một repair có thể kéo dài, thất bại một phần, bỏ sót keyspace/table/token range/replica hoặc bị hoãn vì sự cố. Ngoài ra, một node có thể offline hơn cửa sổ bảo vệ.

Cần đảm bảo **repair hoàn tất thành công trên phạm vi cần thiết** với tần suất và cách quản lý phù hợp phiên bản Cassandra; giám sát thời gian repair cuối cùng thành công, chứ không chỉ lần gần nhất khởi chạy.

### 6.4. Những giới hạn theo phiên bản và cấu hình

Cassandra qua các phiên bản có thay đổi về repair, compaction, cách quản lý repaired/unrepaired SSTables và khả năng tối ưu xóa tombstone. ScyllaDB và những dịch vụ tương thích CQL có thể có những cơ chế khác.

Một số hướng cấu hình tối ưu như chỉ purge repaired tombstone hay cơ chế mới liên quan grace/repair phải được kiểm tra **theo đúng sản phẩm và phiên bản**, không được áp dụng “mẹo” từ một bài viết cũ như quy tắc phổ quát.

Nguyên tắc bất biến vẫn là: **không loại bỏ bằng chứng xóa trước khi có cơ sở tin cậy rằng dữ liệu cũ có thể được hợp nhất sẽ không làm nó sống lại**.

## 7. Anti-entropy repair giữ các replica đồng bộ thế nào?

**Anti-entropy repair** là quá trình phát hiện và giải quyết bất đồng giữa các replica, giúp dữ liệu hội tụ theo những quy tắc của hệ lưu trữ.

### 7.1. Tư duy về quá trình repair

~~~text
Replica A                 Replica B                 Replica C
   |                         |                         |
   |---- So sánh trạng thái / hash / ranges ------------|
   |                         |                         |
   |                Xác định khác biệt                  |
   |                         |                         |
   |<----- Truyền các mutation cần hội tụ ------------->|
   |                         |                         |
   +--------------- Kết quả đồng bộ --------------------+
~~~

Các cơ chế cụ thể trong Cassandra có thể dùng Merkle trees, so sánh token ranges, truyền dữ liệu/streaming và các metadata repair. Điều quan trọng là sửa khác biệt **trong khi thông tin cần để phân xử còn tồn tại**.

### 7.2. Repair khác read repair

Đừng đồng nhất mọi hoạt động sửa dữ liệu thành một cơ chế:

- **Read repair:** trong một số điều kiện đọc, hệ có thể làm các replica liên quan hội tụ theo semantics của phiên bản/consistency.
- **Anti-entropy repair:** vận hành có chủ đích để kiểm tra và đồng bộ dữ liệu theo phạm vi rộng, không phụ thuộc việc người dùng tình cờ đọc một key.
- **Hinted handoff:** giữ gợi ý cho các mutation mà replica không nhận khi tạm unavailable, với giới hạn thời gian và tài nguyên.
- **Replica rebuild/replacement:** dựng lại dữ liệu của node dựa trên nguồn đủ tin cậy theo quy trình phù hợp.

Không nên cho rằng “người dùng đọc dữ liệu thường xuyên nên sẽ tự repair đủ hết”. Những partition lâu không được đọc vẫn có thể mang dữ liệu lệch.

### 7.3. Hinted handoff không thay repair

Trong Cassandra, hints có thời gian lưu và những điều kiện áp dụng riêng. Nếu replica offline dài hơn thời gian giữ hints, các mutation không nhất thiết được replay đầy đủ qua hinted handoff.

Kể cả khi hint tồn tại, cần hiểu liệu nó đã được chuyển thành công và có bao phủ mọi trường hợp mất kết nối không. Vì vậy, **hinted handoff là một hỗ trợ phục hồi ngắn hạn, không phải thay thế cho anti-entropy repair định kỳ**.

### 7.4. Repair phạm vi nào?

Đặt câu hỏi:

- Keyspace/table nào có dữ liệu quan trọng?
- Data center nào?
- Token range nào?
- Replica nào?
- Repair là full hay incremental theo cơ chế hỗ trợ?
- Những node nào đang offline và có bị bỏ khỏi phạm vi?
- Repair có kết thúc thành công hay chỉ bắt đầu?
- Dữ liệu mới/TTL tombstone trong thời gian repair được xử lý thế nào?

Một command repair báo exit code 0 không đủ nếu chương trình vận hành gọi sai phạm vi hoặc có thêm công việc cần làm theo topology.

### 7.5. Ví dụ lệnh mang tính minh họa

Trong môi trường Cassandra đã được vận hành và kiểm soát, người quản trị có thể dùng lệnh thuộc họ:

```bash
nodetool repair app_data cart_items_by_user
```

Đây **không phải hướng dẫn chạy trực tiếp trên production**. Cú pháp tùy phiên bản và tùy chọn; phạm vi repair thực sự phụ thuộc node, data center, token ranges và quy trình cluster. Repair có thể tạo tải mạng/đĩa/CPU đáng kể; cần lịch vận hành, giám sát và cách xác nhận hoàn tất.

## 8. Tại sao giảm gc_grace_seconds xuống 0 có thể nguy hiểm?

Một đội vận hành thấy bảng có nhiều tombstone, truy vấn chậm và muốn:

```sql
ALTER TABLE cart_items_by_user
WITH gc_grace_seconds = 0;
```

Giá trị bằng 0 có nghĩa cửa sổ thời gian giữ tombstone theo tham số này gần như không còn, nhưng **không đồng nghĩa mọi tombstone được xóa lập tức**. Nó có thể mở ra nguy cơ purge sớm hơn, tùy compaction và những điều kiện khác.

### 8.1. Sai lầm trong lập luận

> “Dữ liệu được replication factor 3 nên không cần tombstone giữ lâu.”

Replication factor 3 chỉ cho biết có ba bản sao được thiết kế. Nó không bảo đảm cả ba đều nhận mọi DELETE khi một node mất kết nối.

> “Lệnh DELETE với QUORUM là đủ.”

QUORUM có thể được xác nhận bởi A và B trong khi C vẫn giữ giá trị cũ.

> “Hints sẽ gửi lại khi C online.”

Hints có giới hạn và có thể không tồn tại đủ lâu hoặc không bao phủ trường hợp bất thường.

> “Dữ liệu đã xóa không ai đọc nữa.”

Zombie có thể được phát hiện khi query sau này hoặc khi ứng dụng dùng lại cùng key; hiếm khi đọc không làm dữ liệu cũ an toàn hơn.

### 8.2. Khi nào có thể cân nhắc rút ngắn?

Một số trường hợp có thể cho phép chính sách tombstone khác, chẳng hạn dữ liệu hoàn toàn có thể dựng lại, được quản lý bằng bảng/partition bất biến, workflow repair rất chặt hoặc topology/cơ chế engine có bảo đảm bổ sung.

Nhưng quyết định phải dựa trên:

1. Loại dữ liệu và nguy cơ nghiệp vụ.
2. Replica downtime tối đa được cho phép.
3. Khả năng hoàn tất repair.
4. Các điều kiện compaction/tombstone purge của engine.
5. Có snapshot/backup cũ nào có thể được khôi phục?
6. Tác động của một giá trị cũ nếu xuất hiện lại.
7. Quy trình thay node/rebuild khi vượt ngưỡng.
8. Tài liệu chính thức của **đúng phiên bản sản phẩm**.

Giảm `gc_grace_seconds` để chữa latency mà không điều tra kiểu truy vấn và pattern TTL/delete là **tối ưu sai tầng**.

## 9. Cụ thể một khi node offline quá lâu, xử lý thế nào?

Giả sử đội vận hành phát hiện node C đã mất kết nối 16 ngày, trong khi một số bảng dùng grace 10 ngày và hệ có lệnh DELETE/TTL.

Quyết định đưa C trở lại cần được xử lý như một tình huống **mất an toàn tiềm tàng**, không chỉ là restart service.

### 9.1. Không khởi động và mở traffic một cách máy móc

Nếu C còn dữ liệu trước khi các DELETE xảy ra, việc để C tham gia đọc/repair có thể đưa giá trị cũ vào kết quả trong một số điều kiện. Cần xác định phạm vi bảng/keyspace và bảo đảm của phiên bản engine.

### 9.2. Kiểm tra trạng thái hệ và lịch repair

Thông tin cần thu thập:

- Thời điểm node ngừng nhận mutation;
- Bảng nào có tombstone và grace bao nhiêu;
- Lịch repair đã hoàn tất đến đâu;
- Các đợt compaction và cấu hình liên quan;
- Replica còn khỏe nào có thể cung cấp dữ liệu đúng;
- Hints còn giữ đủ không;
- Snapshot/backup nào được dùng hoặc đã phục hồi.

Việc điều tra có thể yêu cầu sự tham gia của DBA/đội vận hành, vì một thao tác sai có thể ảnh hưởng tới cả cụm.

### 9.3. Rebuild hoặc thay node có thể phù hợp hơn “cho nhập lại nguyên dữ liệu cũ”

Một hướng an toàn hơn trong nhiều tình huống là **rebuild/replacement** node từ các replica còn được đánh giá là đúng, theo quy trình chính thức của Cassandra/ScyllaDB đang chạy, thay vì cho dữ liệu cũ tự hòa vào cụm.

Nhưng không được suy rằng một replica còn chạy luôn chắc chắn là nguồn đúng: cần xét consistency, repair, khả năng dữ liệu đã hồi sinh trước đó và trạng thái xóa trên các replica còn lại.

### 9.4. Dùng runbook được diễn tập

Vì hệ quả có thể khó đảo ngược, một runbook cần phân biệt:

- Mất kết nối ngắn hơn grace, chưa có dấu hiệu bất thường;
- Mất kết nối dài hơn grace nhưng tombstone có thể còn;
- Node đã bị thay thế rồi bất ngờ quay lại;
- Restore từ snapshot nhiều ngày tuổi;
- Mất cả cụm hoặc mất một data center.

Quy trình thực thi khác nhau theo topology. Không nên áp một command duy nhất cho tất cả các kịch bản.

## 10. TTL cũng có thể tạo dấu xóa và rủi ro tương tự

Trong Cassandra, một cell được ghi với TTL:

```sql
INSERT INTO session_events (
    session_id, event_time, event_id, payload
)
VALUES (?, ?, ?, ?)
USING TTL 604800;
```

được thiết kế để giá trị hết hạn sau 7 ngày theo semantics của Cassandra. Khi cell hết hạn, nó không còn được coi là giá trị sống và có thể tham gia cơ chế tombstone/compaction.

### 10.1. TTL không phải DELETE không có metadata

Một giá trị đã hết hạn nhưng vẫn còn ở file cũ/replica khác cần được xử lý đúng trong quá trình hợp nhất. Cassandra không đơn giản “xóa ngay byte khỏi mọi SSTable tại giây cuối”.

Với bảng có rất nhiều cell TTL ngắn, số tombstone tồn tại trong khoảng thời gian grace có thể lớn, ngay cả khi ứng dụng **không gọi DELETE thủ công**.

### 10.2. TTL theo cell có thể làm record thiếu trường

Ví dụ:

~~~text
row (U42, E100)
  event_type = "CLICK"  (TTL 30 ngày)
  payload    = "{...}"  (TTL 7 ngày)
~~~

Sau 10 ngày, `payload` có thể hết hạn nhưng `event_type` còn. Ứng dụng phải hiểu tình trạng record không còn đủ field hoặc thiết kế lại để các trường có cùng vòng đời.

### 10.3. Default TTL cấp table

Ví dụ:

```sql
CREATE TABLE short_lived_events (
    stream_id text,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((stream_id), occurred_at, event_id)
) WITH default_time_to_live = 604800;
```

`default_time_to_live` đặt thời hạn mặc định cho dữ liệu ghi vào bảng, **không phải sau 7 ngày sẽ DROP cả table**.

### 10.4. TTL và zombie data không phải một hiện tượng duy nhất

Một bản ghi “sống lại” có thể do:

1. Replica cũ chưa nhận delete/tombstone.
2. Khôi phục snapshot cũ rồi ghi lại.
3. Consumer event dùng phiên bản cũ và upsert lại.
4. Ứng dụng tính sai TTL hoặc timestamp.
5. Một mutation mới hợp lệ có timestamp mới hơn tombstone.

Các nguyên nhân cần cách xử lý khác nhau. Không nên quy mọi trường hợp thấy dữ liệu cũ thành “bug compaction”.

## 11. Compaction và việc thu gom tombstone

**Compaction** hợp nhất các file lưu trữ, giúp giảm số phiên bản và thu hồi dữ liệu đã bị che hoặc hết hạn theo điều kiện an toàn.

### 11.1. Một ví dụ với SSTable

~~~text
SSTable A:
  item P100 = quantity 2 (timestamp 100)

SSTable B:
  item P100 = tombstone (timestamp 200)

Compaction kết hợp A và B:
  Nếu có cơ sở an toàn để purge:
      bỏ cả giá trị cũ và tombstone
  Nếu chưa an toàn:
      giữ marker cần thiết
~~~

Nếu một SSTable khác chưa được xét còn chứa giá trị v100, engine phải tránh loại marker quá sớm theo điều kiện của chính nó.

### 11.2. Hết grace không đồng nghĩa purge ngay

Tombstone có thể còn tồn tại vì:

- Chưa có compaction phù hợp;
- Còn SSTable có dữ liệu mà tombstone che;
- Chiến lược compaction chưa chọn file liên quan;
- Engine có điều kiện an toàn bổ sung;
- Có sự khác nhau giữa SSTable repaired/unrepaired tùy phiên bản/cấu hình.

Do vậy, cả hai phát biểu sau đều sai nếu nói tuyệt đối:

> “Đúng 10 ngày, mọi tombstone biến mất.”

> “Chỉ cần tombstone còn trên disk thì không cần repair.”

Vế thứ hai sai vì tombstone có thể bị dọn ở lần compaction tiếp theo, và các replica có thể đang lệch.

### 11.3. Compaction strategy có ảnh hưởng lớn

Trong Cassandra, chiến lược compaction có thể gồm các họ như:

- SizeTieredCompactionStrategy (STCS);
- LeveledCompactionStrategy (LCS);
- TimeWindowCompactionStrategy (TWCS).

Mỗi chiến lược có đặc tính về số lượng file, write amplification, read amplification và việc chọn file compaction.

**TWCS** thường đáng cân nhắc cho dữ liệu time-series với TTL tương đối đồng nhất và ghi chủ yếu theo thời gian; nó có thể giúp xử lý toàn bộ cửa sổ dữ liệu hết hạn hiệu quả hơn trong một số điều kiện.

Nhưng nếu có **ghi dữ liệu đến muộn (out-of-order/late writes)**, TTL rất khác nhau hoặc dữ liệu bị cập nhật trên nhiều cửa sổ, TWCS có thể không mang lại lợi ích mong muốn và vẫn tạo những trường hợp khó thu gom. Không dùng TWCS như một cách tự động giải quyết zombie data.

### 11.4. Major compaction không phải “dọn sạch an toàn bất kể điều kiện”

Một thao tác compaction lớn có thể tạo tải CPU/I/O, chiếm dung lượng tạm và thay đổi đặc tính lưu trữ. Nếu các replica chưa đồng bộ, chạy compaction để ép dọn tombstone **không phải biện pháp an toàn đầu tiên**.

Thay vì “đĩa đầy thì ép compaction”, cần điều tra:

- Dữ liệu sống thực tế là bao nhiêu;
- Tỷ lệ tombstone;
- TTL và delete pattern;
- Repair đã hoàn tất hay chưa;
- Strategy và SSTable overlap;
- Dung lượng trống cho compaction;
- Khả năng tăng tài nguyên hoặc thay thiết kế schema.

## 12. Vì sao xóa cả partition, row và cell khác nhau?

Cassandra không chỉ có một kiểu DELETE.

Giả sử bảng:

```sql
CREATE TABLE readings_by_device_day (
    device_id text,
    day date,
    occurred_at timestamp,
    reading_id uuid,
    temperature decimal,
    humidity decimal,
    PRIMARY KEY ((device_id, day), occurred_at, reading_id)
);
```

### 12.1. Xóa một cell

```sql
DELETE humidity
FROM readings_by_device_day
WHERE device_id = 'D1'
  AND day = '2026-11-14'
  AND occurred_at = '2026-11-14T08:30:00Z'
  AND reading_id = 11111111-1111-1111-1111-111111111111;
```

Mục tiêu là loại một giá trị cột theo khóa hàng.

### 12.2. Xóa một row

```sql
DELETE FROM readings_by_device_day
WHERE device_id = 'D1'
  AND day = '2026-11-14'
  AND occurred_at = '2026-11-14T08:30:00Z'
  AND reading_id = 11111111-1111-1111-1111-111111111111;
```

Mục tiêu là loại row theo đầy đủ khóa.

### 12.3. Xóa một partition

```sql
DELETE FROM readings_by_device_day
WHERE device_id = 'D1'
  AND day = '2026-11-14';
```

Xóa một partition có thể tạo tombstone ở phạm vi rộng. Đây là ví dụ minh họa trong Cassandra có partition key ghép `(device_id, day)`.

### 12.4. Xóa theo phạm vi clustering

Nếu schema/truy vấn cho phép, một DELETE theo dải clustering key có thể tạo **range tombstone** cho những hàng thuộc phạm vi. Tùy phiên bản và giới hạn CQL, cú pháp/điều kiện hợp lệ khác nhau.

Điều quan trọng là phạm vi được che:

~~~text
Cell tombstone   -> một giá trị
Row tombstone    -> một hàng
Range tombstone  -> một dải clustering rows
Partition delete -> một partition
~~~

Khi đọc, engine phải xét những marker bao phủ các giá trị ứng viên. Một partition rộng với nhiều range tombstone có thể làm truy vấn scan tốn tài nguyên.

### 12.5. Không nên coi xóa rộng là miễn phí

Một lệnh xóa cả partition có thể nhanh ở thời điểm ghi vì không cần ghi một tombstone cho từng dòng. Nhưng chi phí vật lý, đọc và compaction còn về sau.

Vì vậy, khi thiết kế partition theo thời gian, cần cân nhắc **độ rộng partition**, vòng đời từng hàng, số lần xóa và chiến lược đọc sau khi xóa.

## 13. Timestamp sai và nguy cơ ghi mới bị “thua” dấu xóa

Zombie data do replica cũ là một loại vấn đề. Một loại khác là **độ lệch timestamp**.

Giả sử:

~~~text
DELETE key K: timestamp = 500

Sau đó ứng dụng muốn tạo lại K:
WRITE K=v2: timestamp = 450
~~~

Nếu hệ dùng timestamp để phân xử, lệnh ghi mới về mặt thời gian thực có thể bị tombstone timestamp 500 che. Ứng dụng có thể thấy “ghi thành công nhưng đọc không có dữ liệu”.

Nguyên nhân có thể là:

- Writer dùng timestamp cấp thủ công không nhất quán;
- Đồng hồ giữa các node bị lệch;
- Một node ghi timestamp nằm trong tương lai;
- Event replay dùng timestamp cũ;
- Hệ import backfill đặt sai mốc thời gian.

### 13.1. Không tự đặt write timestamp khi không cần

Trong Cassandra, `USING TIMESTAMP` là công cụ cần hiểu kỹ. Nếu ứng dụng tự cấp timestamp dựa trên một trường thời gian nghiệp vụ không đáng tin cậy, nó có thể phá thứ tự mutation.

Ví dụ **không nên sao chép vào production**:

```sql
UPDATE cart_items_by_user
USING TIMESTAMP 100
SET quantity = 5
WHERE user_id = 'U42'
  AND item_id = 'P100';
```

Timestamp `100` là ví dụ cố ý nhỏ để minh họa phân xử; không đại diện timestamp hợp lệ cho một thao tác hiện đại. Nếu tombstone của key có timestamp lớn hơn, ghi này có thể không trở thành giá trị hiện hành.

### 13.2. “Thời điểm nghiệp vụ” và “thứ tự mutation” khác nhau

Một đơn hàng tạo ngày hôm qua nhưng được import hôm nay không nhất thiết nên có storage timestamp là ngày hôm qua. Nếu nó được dùng để phân xử mutation với DELETE hôm nay, việc gắn timestamp theo eventTime có thể dẫn đến kết quả không mong muốn.

Cần tách:

- `eventTime`: thời điểm sự kiện xảy ra theo nghiệp vụ.
- `updatedAt`: thời điểm ứng dụng lưu thay đổi.
- Storage write timestamp/sequence: thứ tự phục vụ giải quyết xung đột.
- `aggregateVersion`: phiên bản nghiệp vụ tăng dần nếu ứng dụng quản lý.

Những giá trị này có thể liên quan nhưng không nên tự coi là một.

## 14. Backup và restore cũng có thể hồi sinh dữ liệu

Giả sử cụm hoạt động bình thường nhưng cần khôi phục sau sự cố.

~~~text
T1: Backup chứa key K = v1
T2: Người dùng DELETE K
T3: Các replica hiện hành đã ghi nhận xóa
T4: Restore từ backup T1
~~~

Bản backup chứa `K=v1` là **ảnh chụp lịch sử trước khi xóa**. Nếu restore đè lên môi trường hiện hành hoặc replay snapshot sai quy tắc, dữ liệu đã xóa có thể xuất hiện trở lại, dù cơ chế `gc_grace_seconds` trên cụm trước đó không gặp vấn đề.

### 14.1. Phân biệt hai tình huống

**Phục hồi vào môi trường tách biệt để điều tra:** có thể cần thấy lịch sử theo quyền và quy định, nhưng không được dùng trực tiếp làm dữ liệu live nếu chưa đối soát.

**Phục hồi lại production:** phải xác định mốc khôi phục, journal/commit log và những thay đổi hợp lệ sau snapshot, đặc biệt DELETE và TTL.

### 14.2. Restore không chỉ là copy file

Một kế hoạch khôi phục cần trả lời:

- Backup chụp ở thời điểm nào?
- Có chứa tombstone/metadata xóa hay không?
- Những DELETE sau backup được lưu ở đâu?
- Có thể replay commit log/event log đến mốc an toàn không?
- Snapshot thuộc schema/topology/version nào?
- Cách ngăn node cũ tự tham gia với dữ liệu sai?
- Có bản sao dữ liệu nhạy cảm đã được yêu cầu xóa không?
- Làm sao đối soát sau phục hồi?

Không nên cho rằng “restore thành công và query có dữ liệu” nghĩa là trạng thái sau restore đúng.

### 14.3. Không xóa dữ liệu trong backup bằng câu lệnh DELETE thông thường

Một lệnh DELETE ở database hiện hành không sửa những snapshot/bản backup tĩnh đã được lưu ở nơi khác. Backup retention và quy trình hủy an toàn phải được quản lý theo chính sách riêng, bao gồm nghĩa vụ pháp lý và bảo mật áp dụng.

**Dữ liệu đã xóa ở production có thể còn trong backup hợp lệ trong thời hạn retention**; đây là vấn đề vòng đời và quản trị dữ liệu, không đồng nghĩa nó đã hồi sinh vào trạng thái live.

## 15. Event replay, CDC và read model: một dạng hồi sinh khác

Trong nhiều kiến trúc NoSQL, dữ liệu gốc được đồng bộ sang bảng dẫn xuất, search index hoặc vector store.

~~~text
Source database
     |
     v
CDC / Outbox / Event stream
     |
     v
Read model / Search / Cache
~~~

Giả sử:

~~~text
E10: UPSERT Product P100, version=10
E11: DELETE Product P100, version=11

Consumer nhận:
  E11 trước
  E10 đến muộn
~~~

Nếu consumer xử lý vô điều kiện, E10 có thể **tạo lại P100** sau khi E11 đã xóa.

Đây là **application-level resurrection**, không nhất thiết liên quan tới compaction Cassandra. Nhưng về mặt sản phẩm, người dùng vẫn thấy “đã xóa mà lại xuất hiện”.

### 15.1. Version guard

Một consumer có thể dùng quy tắc:

~~~text
if event.aggregateVersion <= projection.lastAppliedVersion:
    ignore event
else:
    apply event atomically and store new version
~~~

Khi xử lý `DELETE v11`, sink nên giữ metadata đủ để biết đã áp dụng version 11. Nếu xóa hoàn toàn record cùng `lastAppliedVersion`, một `UPSERT v10` đến sau có thể không bị phát hiện là cũ.

### 15.2. Tombstone ở tầng projection

Có thể giữ một marker:

```json
{
  "entityId": "P100",
  "deleted": true,
  "sourceVersion": 11,
  "deletedAt": "2026-11-14T08:00:00Z"
}
```

Đây là tombstone **do ứng dụng định nghĩa**, khác tombstone trong Cassandra SSTable. Nó giúp projector chặn event cũ.

Thời gian giữ marker cần xét:

- Thời gian broker giữ event;
- Độ trễ tối đa của consumer;
- Backfill/snapshot lịch sử;
- Khả năng khôi phục dữ liệu;
- Idempotency và thứ tự version;
- Rủi ro bất kỳ upsert cũ nào đến sau khi marker đã được xóa.

### 15.3. Xóa nguồn không tự lan đến mọi bản sao

Nếu TTL xóa một item ở nguồn mà CDC hoặc service không phát sự kiện phù hợp, read model có thể giữ object. Cần pipeline hoặc đối soát tự phát hiện orphan.

Ví dụ:

~~~text
Orders source: O100 đã xóa
orders_by_user: còn O100
Search index: còn O100
Analytics facts: có thể cần giữ theo chính sách lịch sử
~~~

Không được tự lấy trạng thái hiện tại từ một read model khác làm chân lý. Mỗi bản sao có mục đích và retention riêng.

## 16. Một quy tắc an toàn: “xóa” phải có danh tính và phiên bản

Một workflow xóa mạnh thường cần:

1. Định danh đối tượng cần xóa.
2. Mốc/version của lệnh xóa.
3. Phạm vi xóa: cell, row, partition, document hay toàn bộ aggregate.
4. Bằng chứng để các writer/replica khác biết lệnh xóa mới hơn dữ liệu cũ.
5. Quy trình phát tán.
6. Cơ chế kiểm tra hoàn tất.
7. Điều kiện thu gom bằng chứng xóa.
8. Khả năng phát hiện và phục hồi nếu dữ liệu cũ xuất hiện lại.

### 16.1. Ví dụ hai phiên bản

~~~text
Version 20: Order O100 status=CREATED
Version 21: Order O100 status=CANCELLED
Version 22: Order O100 deleted
~~~

Nếu một index hiện giữ marker version 22, một snapshot version 20 hoặc event version 21 không được phép làm O100 thành active.

Khi muốn tạo một order mới **với cùng business key** sau khi xóa, cần định nghĩa liệu đó là cùng aggregate được tái kích hoạt hay một aggregate mới có generation/version khác. Không nên cho một event cũ của aggregate trước ghi vào đối tượng mới chỉ vì ID hiển thị trùng nhau.

### 16.2. Generation/fencing token

Một mô hình có thể lưu:

~~~json
{
  "businessKey": "USER#U42#CART#P100",
  "generation": 5,
  "version": 22,
  "deleted": true
}
```

Khi business key được tái sử dụng, generation tăng. Worker cũ mang generation 4 không được cập nhật giá trị generation 5.

Cơ chế cần được bảo vệ nguyên tử ở nơi authoritative nếu mục tiêu là ngăn race. Chỉ so phiên bản trong code trước khi ghi rồi ghi vô điều kiện vẫn có thể gặp TOCTOU.

## 17. Đọc tombstone nhiều có thể làm truy vấn chậm

Cassandra có thể phải duyệt những marker đã xóa để tìm record còn sống. Đây là vấn đề đặc biệt đáng chú ý với:

- Partition rất lớn;
- TTL ngắn;
- DELETE nhiều;
- Quét dải thời gian có nhiều dữ liệu đã hết hạn;
- Cập nhật collection làm phát sinh nhiều marker;
- Truy vấn yêu cầu lấy rất ít bản ghi sống từ một vùng chứa nhiều dữ liệu chết.

### 17.1. Ví dụ bảng log

Giả sử bảng chứa 30 triệu event/ngày với TTL 24 giờ. Nếu dữ liệu được ghi và hết hạn liên tục, số cell quá hạn mà engine phải quản lý có thể rất lớn.

Một truy vấn:

```sql
SELECT *
FROM events_by_device
WHERE device_id = 'D1'
LIMIT 100;
```

nếu không có partition/time bucket và clustering design phù hợp, có thể phải xét một lượng lớn dữ liệu đã hết hạn trước khi tìm đủ 100 hàng còn sống. CQL `LIMIT 100` **không bảo đảm engine chỉ cần đọc 100 cell vật lý**.

### 17.2. Một số dấu hiệu vận hành

- p95/p99 read latency tăng;
- Truy vấn cảnh báo tombstones;
- Các truy vấn bị giới hạn do quá nhiều tombstone theo cơ chế engine;
- Nhiều SSTable/compaction backlog;
- Disk usage giảm chậm dù dữ liệu đã hết TTL;
- CPU/I/O tăng khi quét partition;
- Thời gian repair tăng;
- Những partition đặc biệt nóng chứa nhiều phiên bản cũ.

### 17.3. Đừng xử lý chỉ bằng tăng ngưỡng cảnh báo

Nếu hệ báo truy vấn có quá nhiều tombstone, tăng ngưỡng warning/failure không xóa nguyên nhân. Nó có thể chỉ khiến truy vấn nặng được phép chạy lâu hơn hoặc làm hệ thêm quá tải.

Cần xem lại schema, partition, TTL pattern, query path, compaction và dữ liệu lịch sử.

## 18. Thiết kế dữ liệu time-series để giảm áp lực tombstone

Dữ liệu theo thời gian có cơ hội tối ưu vòng đời bằng **bucketing**.

### 18.1. Một partition vô hạn là rủi ro

Không nên để mọi event của thiết bị D1 suốt nhiều năm nằm trong một partition quá lớn:

~~~text
Partition key = deviceId
Rows = mọi event từ trước đến nay
~~~

Với hàng triệu event, việc đọc lịch sử, compaction và TTL có thể trở nên tốn kém.

### 18.2. Bucket theo ngày hoặc tháng

Một schema có thể là:

```sql
CREATE TABLE events_by_device_day (
    device_id text,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)
  AND default_time_to_live = 2592000;
```

`2592000` giây bằng 30 ngày. Dữ liệu được chia theo `device_id, event_day`, giúp kiểm soát kích thước partition và đọc theo ngày. Đây là ví dụ thiết kế; độ rộng bucket phù hợp còn tùy tần suất dữ liệu.

### 18.3. TTL đồng nhất và TWCS

Nếu các event trong một cửa sổ có vòng đời gần giống nhau, TimeWindowCompactionStrategy có thể giúp tổ chức SSTable theo thời gian và giảm chi phí dọn dữ liệu hết hạn trong những điều kiện phù hợp.

Nhưng phải kiểm tra:

- Late-arriving events;
- Ghi đè dữ liệu cũ;
- Retention khác nhau giữa các cột;
- Kích thước thời gian window;
- Mức độ read/write amplification;
- Mức độ đồng nhất TTL;
- Điều kiện tombstone purge.

Một bucket theo ngày không tự động làm toàn bộ partition được xóa tức thì sau 30 ngày; TTL vẫn theo cơ chế cell và compaction của engine.

### 18.4. Dùng retention theo nhóm dữ liệu khi phù hợp

Nếu mọi event trong một tháng đều có cùng policy, có thể cân nhắc việc lưu trữ theo partition/index/table mà ứng dụng có thể dọn trọn nhóm. Đây là một quyết định khác với TTL từng cell; nó cần quy trình an toàn, quản lý backup và bảo đảm không xóa nhầm dữ liệu đến muộn.

## 19. Đối soát định kỳ để phát hiện dữ liệu hồi sinh

Một chiến lược tin cậy không chỉ cố giữ tombstone đủ lâu mà còn **phát hiện sai lệch** khi chúng xảy ra.

### 19.1. Kiểm tra theo danh sách đã xóa

Nếu ứng dụng có một deletion ledger ở nguồn authoritative:

~~~json
{
  "entityId": "P100",
  "deletedAt": "2026-11-14T08:00:00Z",
  "deleteVersion": 22,
  "scope": "PRODUCT",
  "operationId": "DEL-100"
}
```

một reconciler có thể kiểm tra:

- Product nguồn có đang bị coi là đã xóa?
- Có bản ghi P100 ở view theo tenant?
- Có search document P100 không?
- Có vector chunks P100 không?
- Có event cũ tái tạo P100?
- Có một replica hoặc backup restore mang version trước delete?

### 19.2. Phân loại mismatch

| Loại | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Replica lag | Replica còn giá trị cũ, tombstone vẫn còn nơi khác | Repair theo quy trình engine |
| Zombie sau purge | Replica cũ mang data, tombstone đã bị purge | Cô lập phạm vi, khôi phục từ nguồn đúng, điều tra |
| Stale read model | Nguồn đã xóa, index còn document | Replay delete/version-aware repair |
| Replay resurrection | Event cũ tạo lại object sau delete | Version/tombstone guard và sửa consumer |
| Backup resurrection | Restore snapshot cũ không replay delete | Phục hồi đúng mốc, reconcile deletion log |
| Timestamp anomaly | Ghi mới bị che hoặc giá trị cũ được ưu tiên | Điều tra timestamp/clock/write path |
| Business re-create | Người dùng cố tình tạo lại cùng key | Xác định generation và quyền sở hữu |
| TTL policy mismatch | Bản sao còn dù nguồn đã hết hạn | Đồng bộ expire/cleanup và kiểm tra deadline |

### 19.3. Tại sao count không đủ?

Nếu nguồn có 100 sản phẩm sống và index cũng có 100, vẫn có thể có 1 sản phẩm zombie và thiếu 1 sản phẩm hợp lệ khác. Cần so **tập ID, phiên bản và trạng thái**, không chỉ đếm tổng.

### 19.4. Bảo vệ repair khỏi ghi lùi

Trong lúc reconciler đọc P100 đã xóa version 22, một operation hợp lệ có thể tạo generation 6 với version mới. Repair không được xóa generation mới chỉ vì thấy business key cũ nằm trong deletion ledger.

Phải so khóa bao gồm **entity identity/generation** và áp dụng điều kiện nguyên tử phù hợp.

## 20. Nguy cơ dữ liệu cũ xuất hiện lại do cách dùng TTL

Một thiết kế ứng dụng có TTL 7 ngày nhưng sau 7 ngày vẫn có dữ liệu ở vài bản sao. Cần xác định chính xác lớp nào đang sai.

### 20.1. Hết hạn logic

Nếu một token hết hạn lúc 10:30, API phải từ chối token từ 10:30 theo quy tắc thời gian/clock của hệ. Việc token vẫn chiếm disk đến 11:00 có thể là hành vi cleanup bất đồng bộ, không nhất thiết vi phạm hợp đồng xác thực.

### 20.2. Dọn vật lý

Một số database xóa item hoặc key bằng tiến trình nền; số byte có thể còn trong file/SSTable/backup. Đây không phải bằng chứng token còn được API xem là hợp lệ.

### 20.3. Hồi sinh sau xóa

Nếu sau khi token đã bị coi là hết hạn, một replica hoặc read model **trả token như đang hợp lệ** do dữ liệu cũ được chấp nhận trở lại, đây mới là vi phạm nghiệp vụ rõ ràng.

Cần tách metric:

- Tỷ lệ request được chấp nhận sau deadline;
- Số bản ghi quá hạn còn được query nhìn thấy;
- Dung lượng vật lý chưa thu hồi;
- Số record orphan/zombie phát hiện qua đối soát.

Mỗi metric có ý nghĩa và thời hạn xử lý khác nhau.

## 21. Thời gian giữ tombstone và thời gian giữ backup khác nhau thế nào?

Giả sử:

~~~text
Tombstone grace Cassandra: 10 ngày
Snapshot retention:       30 ngày
Event log retention:       14 ngày
Read model tombstone:       7 ngày
~~~

Đây là bốn chính sách độc lập. Chúng **không tạo thành một bảo đảm thống nhất** chỉ vì đều là thời hạn.

- Tombstone grace: liên quan tới an toàn hợp nhất bản dữ liệu trên replica của một bảng.
- Snapshot retention: bản sao lịch sử có thể được restore.
- Event log retention: event có thể replay trong phạm vi còn được lưu.
- Read model tombstone: marker ứng dụng chặn event cũ.

Một snapshot 30 ngày tuổi có thể chứa dữ liệu trước DELETE. Nếu restore và đưa vào cụm sai quy trình, grace 10 ngày trước đó không tự chặn được sự cố.

Một projector có marker xóa 7 ngày nhưng event log giữ 14 ngày có thể nhận lại một UPSERT cũ sau khi marker đã hết hạn. Nếu không có cơ chế version/generation khác, read model có thể hồi sinh record.

### 21.1. Tạo bảng chính sách xóa tổng thể

| Lớp dữ liệu | Nơi lưu | Mốc hết hạn/giữ | Cách chống hồi sinh | Xác minh |
|---|---|---|---|---|
| Cassandra source | Replica/SSTable | gc grace + repair policy | Tombstone, anti-entropy, rebuild node cũ | Repair status, data audit |
| Event stream | Broker | Retention theo cấu hình | Version/tombstone ở consumer | Lag, replay tests |
| Search index | Search service | Lifecycle riêng | Delete event + sourceVersion | Reconciliation |
| Vector index | Vector store | Retention theo nội dung/ACL | Delete all chunks + version | Orphan scan |
| Cache | Redis hoặc tương đương | TTL key | Kiểm tra deadline/nguồn khi cần | Cache invalidation checks |
| Backup | Storage riêng | Backup retention | Restore + replay delete ledger | Restore drill |

Dữ liệu nhạy cảm có thể yêu cầu chính sách riêng. Không nên tự suy một tham số tombstone của Cassandra đáp ứng mọi quy định về xóa dữ liệu.

## 22. Giám sát Cassandra khi có nhiều tombstone

### 22.1. Nhóm metric quan trọng

| Nhóm | Metric/quan sát | Câu hỏi |
|---|---|---|
| Repair | Lần repair thành công, phạm vi, lỗi, thời gian | Các replica có được đồng bộ kịp grace không? |
| Availability | Node downtime, replica bị mất liên lạc | Có node nào quá cửa sổ bảo vệ? |
| Query | Tombstone scanned, warning/failure, read latency | Read có phải lướt qua nhiều marker không? |
| Compaction | Pending tasks, throughput, duration | Dữ liệu chết có được dọn không? |
| Storage | SSTable count, disk usage, live/total bytes | Dung lượng tăng do dữ liệu gì? |
| TTL/delete | Số ghi có TTL, số DELETE, tuổi dữ liệu | Workload tạo tombstone nhiều thế nào? |
| Clock | Clock skew, timestamp anomaly | Có mutation tương lai/quá khứ bất thường không? |
| Data correctness | Record cũ xuất hiện sau delete | Có zombie hoặc replay sai không? |
| Backup | Snapshot age, restore drill | Khôi phục có tạo sai lệch không? |

Tùy phiên bản sản phẩm, metric có thể được cung cấp qua JMX/Prometheus, công cụ cluster, logs hoặc telemetry tương ứng. Không nên coi tên metric là giống nhau trên Cassandra và ScyllaDB.

### 22.2. Một số công cụ chẩn đoán phổ biến

Họ công cụ `nodetool` có những lệnh như:

```text
nodetool status
nodetool tablestats
nodetool compactionstats
nodetool netstats
~~~

Những lệnh này cung cấp các góc nhìn khác nhau vào cluster, table, compaction và truyền dữ liệu. Cú pháp, phạm vi output và metric được trình bày phụ thuộc phiên bản.

Có thể bổ sung query tracing, log warning tombstone và công cụ SSTable offline theo quy trình DBA. Không nên thực thi thao tác sửa/compaction trên production chỉ để “thử” khi chưa có kế hoạch.

### 22.3. SLO cho an toàn xóa

Ví dụ một mục tiêu vận hành:

> Mọi token range thuộc các bảng có DELETE/TTL phải được repair thành công theo lịch với khoảng cách an toàn trước `gc_grace_seconds`; node có dữ liệu cũ vượt cửa sổ bảo vệ không được tự động đưa lại vào phục vụ.

Mục tiêu này cần đo **hoàn tất repair và node downtime**, không chỉ schedule.

Một mục tiêu nghiệp vụ khác:

> Khi API xác nhận xóa session, mọi request xác thực mới sau mốc đã định phải bị từ chối, bất kể việc xóa vật lý còn trễ.

Hai mục tiêu không thay nhau: một mục tiêu bảo vệ hệ lưu trữ phân tán, một mục tiêu bảo vệ hành vi ứng dụng.

## 23. Kiểm thử tình huống replica mất kết nối

Một hệ chỉ test INSERT/SELECT/DELETE khi mọi node khỏe có thể bỏ qua kịch bản zombie.

### 23.1. Mô hình thí nghiệm trong môi trường test

Với RF3 và grace được chọn phù hợp cho thí nghiệm:

1. Ghi bản ghi K=v1 và xác nhận dữ liệu đến các replica theo mức cần thiết.
2. Làm replica C không thể nhận mutation.
3. Xóa K qua A/B.
4. Kiểm tra đọc theo consistency được chọn không thấy K trong điều kiện thử nghiệm.
5. Thực hiện các hoạt động khôi phục/repair trong một kịch bản.
6. Ở kịch bản khác, mô phỏng điều kiện tombstone bị purge trước khi C nhận DELETE.
7. Đánh giá liệu K có thể xuất hiện lại khi C tái tham gia và dữ liệu được hợp nhất.

Bước 6 **không nên thực hiện trên production**; thử nghiệm phải dùng môi trường cô lập, dữ liệu giả và cơ chế được DBA đánh giá an toàn.

### 23.2. Không đánh đồng mọi kết quả đọc

Nếu read consistency thấp và một replica chưa nhận delete, một lượt đọc có thể trả dữ liệu cũ **ngay khi tombstone vẫn còn ở replica khác**. Đây là stale read do bất đồng replica, không nhất thiết là tombstone đã bị purge gây zombie dài hạn.

Phân biệt:

- **Stale read tạm thời:** một replica chưa hội tụ;
- **Zombie sau purge:** dữ liệu cũ có nguy cơ trở thành dữ liệu hiện hành vì bằng chứng xóa đã mất;
- **New write:** một ghi mới hợp lệ tạo lại cùng key;
- **Restore/replay:** dữ liệu cũ được đưa lại từ một luồng khác.

### 23.3. Kiểm thử timestamp bất thường

Cho một mutation có timestamp tương lai rồi thử DELETE hoặc ghi mới với timestamp thấp hơn. Quan sát quy tắc phân xử. Mục tiêu là hiểu tại sao thứ tự request từ client không nhất thiết trùng thứ tự storage timestamp.

Không sử dụng timestamp giả hoặc thao tác thay clock thật trên production.

### 23.4. Kiểm thử read model sau DELETE

Kịch bản:

~~~text
Source v10: UPSERT K
Source v11: DELETE K
Consumer nhận v11 trước
Consumer nhận v10 sau
~~~

Kết quả đúng: read model không được tạo lại K từ v10. Điều kiện này phải được bảo vệ bằng version/tombstone/manifest phù hợp.

### 23.5. Kiểm thử backup restore

Phục hồi snapshot trước DELETE trong môi trường cách ly, sau đó áp dụng delete ledger/event log theo quy trình. Xác nhận không có dữ liệu đã xóa được đưa trở lại môi trường live.

## 24. Một ví dụ thực tế: giỏ hàng và giá trị cũ

Giả sử:

~~~text
T0  U42 thêm P100 số lượng 2.
T1  U42 xóa P100.
T2  Một replica offline không nhận delete.
T3  Các replica khác purge tombstone trước khi replica offline được sửa.
T4  Replica cũ trở lại; P100 số lượng 2 xuất hiện ở API.
~~~

Hậu quả nghiệp vụ:

- Người dùng thấy item mình đã xóa.
- Nếu hệ tính giá/tạo đơn từ giỏ hàng, có thể có thao tác ngoài ý muốn.
- Nếu user thêm P100 lần nữa với số lượng khác, dữ liệu hợp nhất sai có thể gây tranh chấp.
- Những read model/caches có thể sao chép trạng thái zombie.

### 24.1. Cách giảm rủi ro ở tầng storage

- Xác định grace phù hợp với downtime/repair.
- Repair bao phủ đầy đủ phạm vi đúng lịch.
- Không tự đưa node đã offline quá cửa sổ an toàn trở lại.
- Điều tra compaction/tombstone pressure trước khi rút ngắn grace.
- Tránh clock/timestamp sai.

### 24.2. Cách giảm tác động ở tầng ứng dụng

Với dữ liệu quan trọng, có thể dùng:

- Version/generation của cart item;
- Deletion ledger hoặc operation log;
- Idempotent command và replay;
- Kiểm tra trạng thái tại nguồn trước bước thanh toán;
- Reconciliation sau sự cố.

Không nên để hai lớp tự mâu thuẫn: một storage tombstone đã purge nhưng ứng dụng giữ bản ghi deletion ledger riêng có thể giúp phát hiện/sửa, nhưng không thay thế được việc thiết kế storage an toàn.

## 25. Một ví dụ thực tế: hồ sơ người dùng bị xóa

Giả sử hệ có các kho:

~~~text
Users Source DB
  |
  +--> users_by_email
  +--> search_profiles
  +--> vector_profiles
  +--> cache:user:U42
  +--> backup snapshots
~~~

Một yêu cầu xóa U42 có thể cần:

1. Xác nhận quyền và phạm vi yêu cầu.
2. Đánh dấu/truyền lệnh xóa authoritative.
3. Không cho các request mới tiếp tục dùng hồ sơ đã xóa.
4. Xóa hoặc ẩn ở các read model.
5. Xóa toàn bộ vector chunks.
6. Invalidate cache.
7. Xử lý backup theo retention/policy.
8. Lưu bằng chứng hoàn tất mà không giữ quá mức dữ liệu nhạy cảm.
9. Đối soát để phát hiện bản sao còn sót.
10. Chặn replay event cũ tạo lại U42.

Một tombstone của một bảng Cassandra giải quyết **một phần vấn đề replica storage**, không thay thế toàn bộ workflow xóa dữ liệu cá nhân.

### 25.1. Đặc biệt nguy hiểm: dữ liệu cũ xuất hiện dưới ID mới

Nếu một service tái tạo hồ sơ bằng một ID khác nhưng cùng email, đối soát chỉ dựa trên userId có thể không phát hiện. Với yêu cầu xóa dữ liệu, cần xác định các khóa nghiệp vụ và quan hệ liên quan theo chính sách an toàn.

Tuy nhiên, việc lưu dữ liệu định danh đã xóa trong deletion ledger cũng cần được cân nhắc về bảo mật/retention. Có thể dùng token/hash hoặc cơ chế kiểm toán phù hợp, không mặc định lưu nguyên dữ liệu vô thời hạn.

## 26. Trình tự điều tra khi thấy dữ liệu đã xóa xuất hiện lại

Giả sử nhận phản ánh:

> “Hôm qua tôi xóa item khỏi giỏ, hôm nay nó lại có mặt.”

Không nên kết luận ngay Cassandra compaction lỗi. Một trình tự điều tra:

### Bước 1 — Xác minh thao tác xóa

- Request xóa có được nhận?
- Có trả thành công thật không?
- Nó xóa đúng key/partition không?
- Có idempotency/operation ID không?
- Có timestamp/version của mutation không?

### Bước 2 — Xác minh nguồn authoritative

- Query hiện tại thấy gì?
- Read consistency là gì?
- Kết quả có khác theo replica/region không?
- Có writer nào tạo lại cùng key hợp lệ không?

### Bước 3 — Xem lịch sử sự kiện

- Có event DELETE không?
- Có upsert sau DELETE không?
- Consumer nào replay dữ liệu cũ?
- Có restore/backfill gần thời điểm lỗi không?

### Bước 4 — Xem sức khỏe cluster

- Node nào từng offline?
- Offline bao lâu so với grace của table?
- Repair gần nhất **hoàn tất thành công** khi nào?
- Có compaction/purge trong giai đoạn đó không?
- Có bất thường clock/timestamp không?

### Bước 5 — Khoanh vùng phạm vi

- Một key hay nhiều key?
- Một partition/tenant hay toàn cụm?
- Bảng gốc hay chỉ read model/cache?
- Có thể cần chặn các đường ghi/đọc nhạy cảm trong lúc điều tra không?

### Bước 6 — Phục hồi và xác minh

- Chọn nguồn chuẩn có chứng cứ.
- Sửa bằng mutation/version đúng.
- Cô lập node dữ liệu cũ nếu cần.
- Reconcile các projection.
- Theo dõi dữ liệu không tái xuất hiện.
- Viết lại runbook và cải thiện giám sát.

**Điều tra nguyên nhân phải đi trước biện pháp “xóa lại”.** Nếu nguồn hồi sinh còn tồn tại, một lần DELETE bổ sung có thể chỉ che lỗi tạm thời.

## 27. Khi nào tombstone là chi phí chấp nhận được?

Không phải cứ có tombstone là thiết kế kém. Trong hệ phân tán, tombstone có thể là **chi phí cần thiết để bảo vệ tính đúng**.

### 27.1. Workload phù hợp

- Dữ liệu ghi nhiều, có TTL/DELETE có kiểm soát;
- Partition không quá lớn;
- Query thường đọc vùng dữ liệu còn sống;
- Compaction phù hợp;
- Repair được vận hành đầy đủ;
- Dung lượng và latency ở mức SLO.

Trong trường hợp này, tombstone là một phần bình thường của engine.

### 27.2. Workload dễ gây áp lực

- TTL vài phút cho hàng tỷ cell/giờ trong cùng nhóm partition;
- DELETE range liên tục trên partition khổng lồ;
- Đọc nhiều dữ liệu hết hạn để tìm một ít dữ liệu sống;
- Nhiều field có TTL khác nhau trong cùng row;
- Repair kéo dài hoặc thường xuyên thất bại;
- Dữ liệu đến muộn khiến chiến lược compaction theo thời gian khó dọn.

Với những trường hợp này, cần xem lại **mô hình dữ liệu và vòng đời** chứ không chỉ thay một tham số.

## 28. Quy tắc chọn retention an toàn theo nhu cầu

Một bảng dữ liệu có giá trị cao cần chính sách khác với telemetry có thể tái tạo.

| Đặc tính | Giỏ hàng/đơn hàng | Sensor telemetry | Cache/read model |
|---|---|---|---|
| Tác động nếu zombie | Có thể ảnh hưởng giao dịch | Có thể gây báo cáo sai | Có thể là UX sai/trễ |
| Nguồn khôi phục | Operation log/trạng thái nghiệp vụ | Dữ liệu cảm biến nếu còn | Source authoritative |
| TTL | Tùy nghiệp vụ | Thường có retention rõ | Thường ngắn |
| Tombstone/repair | Cần bảo vệ | Cần điều chỉnh theo throughput | Có thể rebuild toàn bộ |
| Đối soát | Quan trọng | Tùy tính chất báo cáo | Rất hữu ích |
| Chấp nhận mất dữ liệu | Thường thấp | Theo sản phẩm | Có thể cao nếu dựng lại được |

Không có một giá trị `gc_grace_seconds` duy nhất phù hợp mọi bảng, đặc biệt khi có sự khác biệt lớn về downtime, repair, compaction và mức rủi ro.

### 28.1. Không giải quyết deletion safety chỉ bằng SLO của từng request

API DELETE có p99 latency 15 ms không chứng minh sau một tuần dữ liệu không hồi sinh. Tính đúng của thao tác phân tán còn phụ thuộc trạng thái replica nhiều ngày sau đó.

Cần đo cả **vận hành dài hạn**: repair coverage, node downtime, tombstone age và correctness audit.

### 28.2. Không giải quyết dung lượng chỉ bằng nới grace vô hạn

Giữ tombstone 365 ngày có thể giảm một loại rủi ro purge nhưng có thể làm đọc/compaction/dung lượng trở nên khó vận hành. Nếu node thường offline hàng tháng, vấn đề lớn hơn có thể là **quy trình xử lý node lỗi hoặc topology**, không phải chỉ chọn grace dài thêm.

## 29. Những sai lầm thường gặp

**“DELETE thành công thì mọi replica đã xóa ngay.”** Không. Consistency level có thể cho phép xác nhận trước khi mọi replica nhận mutation.

**“Tombstone là rác nên càng xóa sớm càng tốt.”** Không. Nó có thể là bằng chứng duy nhất rằng dữ liệu cũ đã bị xóa.

**“gc_grace_seconds là TTL của dữ liệu.”** Không. Nó liên quan thời gian giữ dấu xóa để bảo vệ quá trình hội tụ.

**“Đủ 10 ngày là tombstone tự biến mất.”** Không. Còn phụ thuộc compaction và điều kiện an toàn.

**“Chỉ cần có RF3 thì không có zombie.”** Không. Một replica offline có thể bỏ lỡ DELETE.

**“Dùng QUORUM thì không bao giờ hồi sinh.”** Không phải bảo đảm tuyệt đối khi tombstone bị purge trước khi một replica cũ được đồng bộ.

**“Hinted handoff thay repair.”** Không. Hints có giới hạn và không bao phủ mọi bất đồng lâu dài.

**“Repair chạy theo lịch là đủ.”** Chưa đủ. Cần repair **hoàn tất thành công** trên phạm vi cần thiết.

**“Nút offline 20 ngày cứ bật lại.”** Nguy hiểm nếu cửa sổ giữ tombstone ngắn hơn và có khả năng node mang dữ liệu cũ.

**“Giảm gc_grace_seconds về 0 để giảm tombstone là an toàn.”** Không nếu chưa chứng minh điều kiện topology/repair/compaction cho phép.

**“Compaction là cách sửa zombie.”** Compaction trên một replica không tự truyền DELETE tới replica khác; compaction sai thời điểm còn có thể loại bỏ marker cần thiết.

**“Read repair sẽ tự chữa mọi partition.”** Không. Những dữ liệu không được đọc hoặc không nằm trong phạm vi cũng cần anti-entropy repair thích hợp.

**“TTL không tạo tombstone.”** Không đúng với Cassandra: dữ liệu hết hạn có thể tham gia cơ chế tombstone và compaction.

**“SSTable không còn tombstone thì chắc chắn không còn giá trị cũ ở đâu.”** Không, có thể có replica offline, backup hoặc pipeline khác.

**“Backup trước DELETE có thể restore vào production mà không cần replay xóa.”** Có thể làm sống lại dữ liệu cũ.

**“Read model đã xóa thì event cũ không thể tạo lại.”** Sai nếu không giữ version/tombstone hoặc điều kiện idempotent.

**“Mọi dữ liệu xuất hiện lại đều là bug Cassandra.”** Không. Có thể do ứng dụng ghi mới, cache, CDC, restore, timestamp hoặc giao dịch nghiệp vụ.

**“Đã hết hạn logic nghĩa là byte đã bị xóa khỏi mọi nơi.”** Không. Physical cleanup và backup retention có lịch riêng.

## 30. Bài tập thực hành

### Bài tập 1 — Quorum DELETE và replica offline

RF=3, A và B online, C offline. DELETE được A và B xác nhận.

**Câu hỏi:** Có chắc C đã biết DELETE không? Điều gì xảy ra nếu C trở lại sau khi tombstone ở A/B bị purge?

**Gợi ý:** C có thể chưa biết DELETE. Nếu marker xóa đã biến mất và C còn giá trị cũ, có nguy cơ zombie data.

### Bài tập 2 — Hết grace và compaction

Một bảng có `gc_grace_seconds=864000`. Đúng 10 ngày sau DELETE, hệ chưa chạy compaction liên quan.

**Câu hỏi:** Có thể nói tombstone đã biến mất không?

**Gợi ý:** Không. Hết grace chỉ liên quan điều kiện thời gian; việc purge thực tế còn phụ thuộc compaction và điều kiện an toàn.

### Bài tập 3 — Lịch repair

Grace là 10 ngày, repair job chạy 7 ngày/lần nhưng có một lần thất bại sau 10% token ranges.

**Câu hỏi:** Có thể coi toàn bộ dữ liệu đã được repair trong 7 ngày không?

**Gợi ý:** Không. Phải ghi nhận phạm vi **hoàn tất thành công** và chạy bù những phần thất bại trước khi vượt cửa sổ bảo vệ.

### Bài tập 4 — Hinted handoff

Một node offline 15 ngày. Đội vận hành nói “không cần repair vì hints sẽ tự gửi lại”.

**Câu hỏi:** Lập luận này có an toàn không?

**Gợi ý:** Không được mặc định. Hints có retention/giới hạn riêng; cần xem trạng thái node, grace và repair/rebuild theo quy trình engine.

### Bài tập 5 — Timestamp không đúng thứ tự

Một DELETE mang timestamp 500. Một thao tác INSERT mới được thực hiện sau về thời gian thực, nhưng writer đặt timestamp 450.

**Câu hỏi:** Điều gì có thể xảy ra?

**Gợi ý:** Tombstone có timestamp 500 có thể tiếp tục che mutation 450. Phải kiểm soát timestamp/clock, không suy từ thời gian request đến.

### Bài tập 6 — TTL và tombstone

Một bảng session dùng TTL 5 phút cho mọi cell và lưu hàng triệu phiên mỗi giờ.

**Câu hỏi:** Dù không có DELETE thủ công, vì sao hệ vẫn có thể chịu áp lực tombstone/compaction?

**Gợi ý:** Cell hết hạn theo TTL cũng có semantics deletion; engine phải quản lý tombstone và thu gom an toàn.

### Bài tập 7 — Xóa cell hay xóa partition?

Trong bảng theo `(device_id, day)`, ứng dụng muốn loại toàn bộ reading ngày hôm qua của D1.

**Câu hỏi:** Xóa mỗi cell khác gì xóa cả partition? Cần lưu ý điều gì?

**Gợi ý:** Phạm vi marker khác nhau; xóa partition có thể tạo tombstone diện rộng. Vẫn cần xét replication, grace, compaction và cost read.

### Bài tập 8 — Quét partition nhiều tombstone

Query `LIMIT 100` nhưng phải xét hàng triệu cell đã hết hạn.

**Câu hỏi:** Vì sao LIMIT không bảo đảm chỉ đọc 100 cell?

**Gợi ý:** Engine cần bỏ qua các giá trị không còn sống để tìm 100 hàng hợp lệ. Cân nhắc bucket, TTL pattern, compaction và query path.

### Bài tập 9 — Snapshot phục hồi

Backup ở T1 chứa P100. DELETE ở T2. Restore từ backup T1 vào môi trường live ở T3.

**Câu hỏi:** Rủi ro gì và cần những thông tin gì để restore đúng?

**Gợi ý:** Có thể phục hồi P100 cũ; cần lịch sử mutation/delete sau T1, mốc phục hồi, replay, quyền dữ liệu và đối soát.

### Bài tập 10 — Event replay sai thứ tự

Nguồn phát:

~~~text
v10 UPSERT P100
v11 DELETE P100
~~~

Projector nhận v11 trước rồi v10.

**Câu hỏi:** Nếu sink xóa sạch document và không giữ version, điều gì có thể xảy ra?

**Gợi ý:** Event v10 có thể tạo lại P100. Cần version marker/tombstone ở tầng projection hoặc cơ chế khác bảo vệ thứ tự.

### Bài tập 11 — Read consistency

Một replica chưa nhận DELETE và vẫn trả giá trị cũ, nhưng tombstone vẫn được giữ ở hai replica khác.

**Câu hỏi:** Đây đã là zombie do purge hay có thể chỉ là stale read?

**Gợi ý:** Có thể là stale read do replica chưa hội tụ. Zombie do purge liên quan việc mất bằng chứng xóa và dữ liệu cũ được chấp nhận trở lại.

### Bài tập 12 — Chọn gc_grace_seconds

Bảng A lưu đơn hàng khó phục hồi; bảng B lưu dữ liệu telemetry có thể dựng lại. Đội vận hành muốn đặt grace bằng 0 cho cả hai để tiết kiệm đĩa.

**Câu hỏi:** Những thông tin cần thu thập trước khi quyết định?

**Gợi ý:** Repair cadence/coverage, node downtime, topology, compaction, backup/restore, rủi ro nghiệp vụ và khả năng tái dựng dữ liệu. Không áp một giá trị theo cảm tính.

### Bài tập 13 — TWCS và late writes

Một bảng ghi event theo thời gian, TTL 30 ngày, nhưng mỗi ngày import thêm dữ liệu có eventTime của ba tháng trước.

**Câu hỏi:** Vì sao TWCS/retention theo cửa sổ có thể không hoạt động như kỳ vọng?

**Gợi ý:** Late/out-of-order data làm dữ liệu các khoảng thời gian trộn lẫn; cần xét write time, TTL, SSTable window, compaction và mục tiêu retention thực tế.

### Bài tập 14 — Bảo mật và xóa dữ liệu cá nhân

Nguồn user đã xóa, nhưng search và vector index còn hồ sơ U42.

**Câu hỏi:** Sửa cấu hình `gc_grace_seconds` của Cassandra có giải quyết toàn bộ không?

**Gợi ý:** Không. Phải truyền delete sang read models, xóa chunks/caches, đối soát, xử lý backup retention theo chính sách và chặn replay.

### Bài tập 15 — Node quay lại sau 16 ngày

RF3, grace 10 ngày. Node C chứa dữ liệu cũ và đã offline 16 ngày. A/B đã có nhiều compaction.

**Câu hỏi:** Bước vận hành an toàn hơn là restart C ngay hay điều tra và cân nhắc rebuild?

**Gợi ý:** Điều tra trước khi đưa dữ liệu cũ vào phục vụ; xác định repair/grace/compaction và theo quy trình sản phẩm cân nhắc rebuild hoặc replacement.

### Bài tập 16 — Phân biệt nguồn hồi sinh

Một giỏ hàng có P100 sau khi đã xóa. Có ba giả thuyết:

1. Replica cũ chưa nhận tombstone và quay lại.
2. Consumer replay UPSERT v3 sau DELETE v4.
3. Người dùng đã thêm lại P100 hợp lệ.

**Câu hỏi:** Cần log/metadata nào để phân biệt?

**Gợi ý:** Operation ID, writer, storage timestamp, aggregate version/generation, delete event, replica/repair history, source state và request audit.

## 31. Checklist thiết kế và vận hành

Khi một bảng NoSQL có DELETE hoặc TTL, hãy trả lời những câu hỏi sau:

- [ ] Bảng sử dụng cơ chế lưu trữ và xóa nào?
- [ ] Có tombstone ở cấp cell, row, range hoặc partition không?
- [ ] Bản ghi được sao chép tới bao nhiêu replica, ở data center nào?
- [ ] Consistency level của DELETE/READ là gì?
- [ ] Có trường hợp replica mất kết nối dài ngày không?
- [ ] Thời gian giữ tombstone hoặc chính sách xóa là bao nhiêu?
- [ ] Repair được lên lịch và **xác nhận hoàn tất** thế nào?
- [ ] Nếu node offline quá cửa sổ an toàn, runbook xử lý ra sao?
- [ ] Compaction strategy có phù hợp TTL/delete pattern không?
- [ ] Có nhiều tombstone làm truy vấn/compaction chậm không?
- [ ] Ứng dụng có tự cấp write timestamp không?
- [ ] Có backup/restore từ mốc trước DELETE không?
- [ ] Có event stream/read model có thể replay UPSERT cũ không?
- [ ] Có version/tombstone/generation chặn upsert cũ không?
- [ ] Có cơ chế đối soát bản ghi đã xóa giữa các hệ không?
- [ ] Có phân biệt hết hạn logic, xóa vật lý và retention backup không?
- [ ] Có kiểm thử replica downtime, restore và replay sai thứ tự không?

Đây là checklist định hướng thiết kế; việc thực thi một thay đổi cấu hình cần tài liệu và quy trình vận hành cho **đúng engine, đúng phiên bản, đúng topology**.

## 32. Tổng kết

Trong một cơ sở dữ liệu phân tán, **lệnh xóa không thể luôn được hiểu là “xóa byte ngay tại mọi nơi”**. Các replica có thể giữ phiên bản cũ, còn storage engine có thể lưu dữ liệu và dấu xóa trong nhiều SSTable cho đến khi compaction. Tombstone đóng vai trò **bằng chứng phiên bản mới hơn**, giúp một DELETE hoặc TTL hết hạn thắng giá trị cũ trong quá trình đọc và đồng bộ.

Với Cassandra, `gc_grace_seconds` là một yếu tố quan trọng trong việc giữ tombstone đủ thời gian cho repair và những replica từng mất liên lạc. Nếu một replica giữ giá trị cũ quá lâu, trong khi các bản sao khỏe đã purge tombstone, dữ liệu cũ có thể **hồi sinh** khi replica ấy quay lại. Đặt grace không tự chạy repair, và hết grace không đồng nghĩa purge tức thì: phải xét compaction, trạng thái replica và các điều kiện an toàn của engine.

Một thiết kế bền vững cần kết hợp **thời gian giữ dấu xóa phù hợp, anti-entropy repair hoàn tất, xử lý node offline, kiểm soát timestamp, compaction hợp lý, backup/restore đúng mốc và version-aware replay ở các read model**. Đồng thời phải đo tombstone pressure, độ trễ đọc, repair coverage và khả năng dữ liệu đã xóa xuất hiện lại.

**Nguyên tắc cốt lõi:** Đừng thu gom bằng chứng xóa trước khi có cơ sở tin cậy rằng các bản dữ liệu cũ sẽ không còn khả năng được hợp nhất thành dữ liệu đang sống. Và đừng coi sự biến mất của một record khỏi kết quả truy vấn là bằng chứng nó đã biến mất khỏi toàn bộ hệ thống.

