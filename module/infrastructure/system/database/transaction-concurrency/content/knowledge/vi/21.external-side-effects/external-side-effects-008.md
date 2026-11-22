# Phạm vi của giao dịch cục bộ khi đọc qua bản sao

Read replica (bản sao phục vụ đọc) giúp phân tải truy vấn khỏi máy chủ chính. Ứng dụng có thể gửi báo cáo, tìm kiếm hoặc các truy vấn đọc lớn đến replica trong khi primary tiếp tục nhận thao tác ghi. Tuy nhiên, một transaction chạy trên replica chỉ kiểm soát những lần đọc và snapshot mà chính replica đó cung cấp. Nó không tự mở rộng phạm vi ACID sang primary, không khóa dữ liệu trên primary và không bảo đảm replica đã áp dụng mọi commit mới nhất.

Đây là điểm cần hiểu khi ứng dụng vừa ghi dữ liệu ở primary, vừa đọc qua replica. Một transaction đọc-only có thể nhất quán nội bộ theo isolation level của database replica nhưng vẫn nhìn thấy dữ liệu cũ hơn primary do replication lag. Nếu nhiều câu lệnh được định tuyến đến các replica khác nhau, ứng dụng thậm chí có thể đọc thấy trạng thái lùi hoặc không nhất quán theo quan hệ nhân quả.

Để dùng replica đúng cách, cần xác định rõ phạm vi transaction, thời điểm dữ liệu được nhận và replay, mức nhất quán mà nghiệp vụ yêu cầu, cùng quy tắc định tuyến đọc. Với các luồng cần read-your-writes hoặc causal consistency, có thể phải đọc primary, giữ phiên đọc trên cùng replica hoặc chờ replica bắt kịp một vị trí replication cụ thể.

## 1. Primary và read replica hoạt động như thế nào?

Trong kiến trúc primary-replica, primary là nơi tiếp nhận các thay đổi dữ liệu. Các thay đổi được truyền đến một hoặc nhiều replica thông qua cơ chế replication của DBMS.

```text
                    Ứng dụng
                       |
             +---------+---------+
             |                   |
          Ghi dữ liệu          Đọc dữ liệu
             |                   |
             v                   v
        +----------+       +-------------+
        | Primary  | ----> | Read replica|
        +----------+       +-------------+
             |              ^
             |              |
             +---- log -----+
                replication
```

Primary ghi thay đổi vào log hoặc cơ chế lưu trữ replication tương ứng. Replica nhận dữ liệu, sau đó áp dụng/replay các thay đổi vào bản sao cục bộ. Tùy sản phẩm, việc truyền và áp dụng có thể diễn ra gần như đồng thời hoặc có độ trễ đáng kể.

Các thuật ngữ thường gặp:

- **Replication lag:** khoảng chênh lệch giữa trạng thái đã commit ở primary và trạng thái replica đã áp dụng.
- **Received position:** vị trí log mà replica đã nhận được.
- **Applied/replayed position:** vị trí log mà replica đã áp dụng vào dữ liệu có thể đọc.
- **Read replica:** bản sao thường được cấu hình để phục vụ truy vấn đọc; nhiều hệ thống không cho phép ghi nghiệp vụ trực tiếp lên replica.
- **Primary commit:** thời điểm transaction ghi được xác nhận commit trên primary theo semantics của DBMS và cấu hình replication.

Việc replica đã nhận log không nhất thiết có nghĩa truy vấn đọc đã nhìn thấy thay đổi đó. Với nhiều hệ thống, replica phải replay/apply log trước khi thay đổi trở nên khả dụng cho truy vấn. Vì vậy, cần phân biệt độ trễ truyền log với độ trễ áp dụng log.

## 2. Giao dịch cục bộ trên replica có phạm vi đến đâu?

Một transaction mở trên replica tạo phạm vi đọc và isolation tại chính database instance đó. Ví dụ:

```sql
BEGIN READ ONLY;

SELECT balance
FROM account
WHERE account_id = 42;

SELECT status
FROM orders
WHERE customer_id = 900;

COMMIT;
```

Transaction này có thể bảo đảm các câu lệnh đọc tuân theo isolation level được cấu hình trên replica. Nhưng phạm vi của nó vẫn là dữ liệu mà replica đã nhận và áp dụng, cộng với snapshot mà engine cho phép transaction nhìn thấy.

Transaction cục bộ trên replica **không tự động**:

- Đọc được những commit đã xảy ra ở primary nhưng replica chưa replay.
- Khóa hàng hoặc ngăn transaction trên primary sửa cùng dữ liệu.
- Tạo một transaction nguyên tử bao trùm cả primary và replica.
- Buộc các replica khác cùng nhìn thấy một snapshot giống hệt.
- Bảo đảm câu lệnh tiếp theo trên một replica khác sẽ thấy ít nhất dữ liệu đã đọc ở replica hiện tại.
- Cung cấp read-your-writes sau một lần ghi ở primary nếu replica chưa bắt kịp.

Do đó, transaction cục bộ chỉ bảo vệ tính nhất quán trong phạm vi nó kiểm soát. Nếu nghiệp vụ cần phối hợp một lần ghi ở primary với lần đọc tiếp theo ở replica, ứng dụng cần một giao thức định tuyến hoặc đồng bộ riêng.

### 2.1. Local transaction không phải distributed transaction

Một transaction đọc trên replica không phải transaction phân tán giữa primary và replica. Nó không có một coordinator commit/rollback cho nhiều database instance. Nếu ứng dụng thực hiện:

1. `UPDATE` trên primary và commit.
2. Mở transaction đọc trên replica.
3. Đọc một hàng liên quan đến thay đổi vừa ghi.

thì hai bước đầu và cuối không thuộc cùng một transaction ACID. Replica có thể chưa áp dụng thay đổi ở bước 1 khi bước 3 chạy.

Nếu một quy trình thật sự cần atomic commit giữa nhiều database độc lập, phải dùng một thiết kế distributed transaction hoặc một mô hình phối hợp khác. Đọc từ replica không tự tạo ra bảo đảm đó.

## 3. Replication lag làm transaction đọc thấy dữ liệu cũ

Giả sử balance ban đầu của tài khoản 42 là 100. T1 ghi ở primary, tăng balance lên 120 và commit. Trong lúc log chưa được replay ở replica, T2 đọc qua replica:

```text
Thời gian ------------------------------------------------------------>

Primary:
  T1 UPDATE balance = 120
  T1 COMMIT

Replication:
  log của T1 được gửi --------------------> replica replay

Replica:
  T2 SELECT balance = 100
                                          T3 SELECT balance = 120
```

T2 không nhất thiết đọc sai theo transaction local của nó. T2 đọc đúng trạng thái mà replica đang cung cấp tại thời điểm đó. Vấn đề là replica chưa theo kịp primary.

Điều này thường chấp nhận được với dữ liệu có thể eventual consistency, chẳng hạn số liệu phân tích, dashboard hoặc một số trang danh sách. Nhưng có thể gây lỗi nghiệp vụ nếu ứng dụng đọc ngay sau khi ghi để xác nhận đơn hàng, kiểm tra số dư mới, kiểm tra quyền vừa thay đổi hoặc quyết định có cho phép thao tác tiếp theo hay không.

## 4. Nhận log và replay log là hai mốc khác nhau

Một replica có thể đã nhận dữ liệu replication nhưng chưa áp dụng xong. Chỉ khi engine đã replay/apply đến vị trí cần thiết, truy vấn mới có thể nhìn thấy thay đổi tương ứng.

```text
Primary commit position:       LSN/GTID = P
Replica received position:     LSN/GTID = R
Replica applied position:      LSN/GTID = A

Nếu A chưa đạt đến vị trí của commit P,
truy vấn trên replica có thể chưa nhìn thấy thay đổi đó.
```

Tên và ý nghĩa chính xác của các vị trí khác nhau giữa DBMS. Một số hệ thống hiển thị log receive, redo/apply hoặc replay position riêng. Khi triển khai read-after-write, phải chờ mốc phản ánh dữ liệu đã áp dụng, không chỉ mốc log đã đến nơi.

Replication lag cũng không chỉ là một con số thời gian. Có thể đo theo thời gian, số byte log chưa replay, số transaction chưa áp dụng hoặc khoảng cách giữa các vị trí log. Một con số lag thấp ở thời điểm kiểm tra không bảo đảm replica sẽ bắt kịp ngay ở truy vấn tiếp theo.

## 5. Snapshot của transaction và replication replay

Có hai nguyên nhân độc lập khiến transaction đọc thấy dữ liệu cũ:

1. Replica chưa áp dụng commit từ primary.
2. Transaction đã lấy snapshot cũ và tiếp tục đọc theo snapshot đó, dù replica đã replay thêm dữ liệu sau khi transaction bắt đầu.

Ví dụ khái quát:

```text
T1 trên replica: BEGIN; lấy snapshot S1; đọc balance = 100
Primary:         UPDATE balance = 120; COMMIT
Replica:         replay thay đổi balance = 120
T1 trên replica: SELECT lại trong cùng snapshot S1
                 có thể vẫn thấy balance = 100
T1 kết thúc
T2 mới trên replica: BEGIN; đọc balance = 120
```

Hành vi cụ thể phụ thuộc DBMS và isolation level. Với snapshot isolation hoặc Repeatable Read theo mô hình MVCC, transaction có thể giữ một snapshot ổn định. Ở Read Committed, mỗi statement thường có snapshot mới, nhưng vẫn chỉ nhìn thấy những thay đổi replica đã áp dụng trước thời điểm statement lấy snapshot.

Vì vậy, nếu cần thấy một commit mới hơn, chỉ chờ replication lag giảm là chưa đủ khi transaction đọc cũ vẫn đang mở. Có thể phải kết thúc transaction cũ và bắt đầu transaction mới sau khi replica đã replay đến vị trí cần thiết.

## 6. Isolation level cục bộ không tạo ra độ mới toàn cụm

Isolation level điều chỉnh cách transaction đọc và ghi tương tác với những transaction khác trong cùng hệ quản trị. Nó không biến replica thành bản sao đồng bộ tức thời của primary.

| Isolation/read mode | Bảo đảm ở replica | Điều không tự bảo đảm |
|---|---|---|
| Read Committed | Mỗi statement đọc theo snapshot/visibility rule mới của replica | Không bảo đảm replica đã áp dụng mọi commit vừa xảy ra ở primary |
| Repeatable Read / Snapshot | Các lần đọc trong transaction có thể dùng snapshot ổn định | Không tự làm mới snapshot khi replica replay thêm log |
| Serializable | Lịch transaction cục bộ được bảo vệ theo semantics Serializable của DBMS | Không tạo serializable transaction xuyên primary và replica |
| Read-only transaction | Ngăn hoặc hạn chế ghi trong transaction theo DBMS | Không bảo đảm dữ liệu đọc là mới nhất trên primary |

Một transaction Serializable trên replica vẫn có thể chạy hoàn toàn trên một trạng thái đã cũ hơn primary. Serializable bảo vệ quan hệ giữa các transaction mà engine kiểm soát; nó không đồng nghĩa với linearizability hoặc global latest-read trên toàn cụm.

## 7. Read-your-writes: đọc lại dữ liệu vừa ghi

Read-your-writes là yêu cầu một client sau khi ghi thành công phải đọc thấy chính thay đổi đó trong các lần đọc tiếp theo. Đây là kỳ vọng thường gặp trong giao diện người dùng:

1. Người dùng cập nhật địa chỉ giao hàng.
2. API ghi địa chỉ mới ở primary và trả thành công.
3. Trang chi tiết được tải lại từ read replica.
4. Replica chưa replay thay đổi nên trang hiển thị địa chỉ cũ.

Người dùng có thể nghĩ thao tác cập nhật bị mất dù primary đã commit.

Các cách thường dùng để giữ read-your-writes:

- Sau khi ghi, định tuyến các lần đọc liên quan về primary trong một khoảng thời gian hoặc cho đến khi replica bắt kịp.
- Gắn một replication position/token vào kết quả ghi và chỉ đọc replica đã replay ít nhất đến vị trí đó.
- Dùng sticky routing để phiên người dùng tiếp tục đọc từ một node có thể đáp ứng mức nhất quán cần thiết; sticky routing đơn thuần không đủ nếu node đó vẫn lag.
- Trả dữ liệu vừa ghi trực tiếp từ kết quả `RETURNING` hoặc object đã được xác nhận, nếu luồng nghiệp vụ không cần đọc lại toàn bộ từ database.

### 7.1. Đọc primary sau khi ghi

Đây là cách đơn giản và mạnh về ngữ nghĩa: mọi lần đọc cần xác nhận thay đổi vừa commit được gửi về primary. Primary là nơi commit được xác nhận nên không phải chờ replication.

Nhược điểm là tăng tải trên primary và có thể làm mất lợi ích phân tải của read replica. Có thể chỉ định tuyến các thao tác read-after-write hoặc dữ liệu có yêu cầu mới nhất, còn truy vấn báo cáo vẫn dùng replica.

### 7.2. Chờ replica replay đến commit position

Một cách khác là lấy vị trí commit ở primary rồi chờ replica áp dụng đến ít nhất vị trí đó trước khi đọc. Cách triển khai phụ thuộc DBMS:

- PostgreSQL có thể dùng LSN và hàm kiểm tra replay position.
- MySQL có thể dùng GTID và cơ chế chờ transaction GTID đã được thực thi trên replica.
- Các nền tảng khác có thể cung cấp commit token, log sequence hoặc API đồng bộ tương đương.

Chỉ nên đọc sau khi điều kiện chờ xác nhận vị trí **đã replay/applied**. Nếu hết timeout, ứng dụng cần fallback về primary hoặc trả trạng thái chưa thể đáp ứng, tùy hợp đồng API.

## 8. Ví dụ PostgreSQL: theo dõi replay position

PostgreSQL physical streaming replication dùng WAL và LSN (Log Sequence Number). Sau khi transaction ghi commit ở primary, ứng dụng hoặc tầng điều phối có thể lấy một vị trí WAL liên quan rồi kiểm tra replica đã replay đến đâu.

Trên primary, sau khi transaction ghi đã commit, có thể lấy vị trí WAL hiện tại:

```sql
SELECT pg_current_wal_lsn();
```

Trên standby, xem vị trí WAL đã replay:

```sql
SELECT pg_last_wal_replay_lsn();
```

Có thể so sánh hai LSN bằng hàm so sánh LSN của PostgreSQL:

```sql
SELECT pg_last_wal_replay_lsn() >= '0/16B6A20'::pg_lsn AS replayed;
```

Giá trị `'0/16B6A20'` chỉ là ví dụ. Trong ứng dụng, vị trí cần chờ phải là token gắn với commit cần đọc, được lấy và truyền qua giao thức phù hợp; không nên lấy một LSN tùy ý sau đó giả định nó chính là vị trí commit của request.

Một luồng khái quát:

```text
1. Ghi transaction trên primary.
2. COMMIT thành công.
3. Lấy/nhận commit position tương ứng.
4. Chọn một replica.
5. Poll hoặc wait đến khi replay position >= commit position.
6. Bắt đầu transaction đọc mới trên replica đó.
7. Nếu timeout, fallback primary hoặc trả kết quả phù hợp.
```

Không nên mở transaction snapshot trên replica trước khi chờ replay rồi giữ transaction đó qua thời gian chờ. Khi bắt đầu transaction đọc, hãy bảo đảm snapshot được tạo sau khi replica đã bắt kịp vị trí yêu cầu.

### 8.1. Synchronous replication và remote_apply

Trong PostgreSQL, cấu hình synchronous replication có nhiều mức xác nhận. Với một số chế độ, primary có thể chờ standby nhận hoặc ghi WAL nhưng chưa chắc standby đã replay và truy vấn đọc thấy thay đổi. `synchronous_commit = remote_apply` có thể chờ synchronous standby áp dụng transaction trước khi primary xác nhận commit theo semantics cấu hình.

Điều này giảm cửa sổ read-after-write lag cho các standby tham gia đồng bộ, nhưng có chi phí latency và phụ thuộc cấu hình synchronous standby. Nó không có nghĩa mọi replica trong cụm đều đã áp dụng thay đổi; chỉ những standby được tính theo cấu hình liên quan mới tham gia bảo đảm đó.

## 9. Ví dụ MySQL: chờ GTID được áp dụng

MySQL replication có thể dùng GTID (Global Transaction Identifier) để nhận diện transaction đã được thực thi. Trên replica, có thể chờ một GTID cụ thể được thực thi bằng hàm `WAIT_FOR_EXECUTED_GTID_SET`:

```sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('source_uuid:transaction_number', 5);
```

Chuỗi GTID trong ví dụ là placeholder; ứng dụng phải lấy GTID thực tế của transaction cần chờ theo cách được nền tảng triển khai hỗ trợ. Kết quả và hành vi timeout cần được xử lý theo tài liệu phiên bản MySQL.

Trong MySQL semisynchronous replication, primary có thể nhận xác nhận rằng replica đã nhận và ghi relay log, nhưng điều đó không nhất thiết có nghĩa transaction đã được apply vào bảng để truy vấn đọc thấy ngay. Nếu yêu cầu là read-after-write trên replica, phải chờ trạng thái thực thi/applied phù hợp.

## 10. Monotonic reads và đọc qua nhiều replica

Read-your-writes yêu cầu client thấy thay đổi của chính mình. Một yêu cầu khác là **monotonic reads**: sau khi client đã thấy một phiên bản dữ liệu, những lần đọc sau không được quay về phiên bản cũ hơn.

Giả sử có hai replica:

```text
Primary:       balance = 120
Replica A:     balance = 120  [đã replay]
Replica B:     balance = 100  [đang lag]

Request 1 -> Replica A -> đọc 120
Request 2 -> Replica B -> đọc 100
```

Người dùng thấy số dư giảm từ 120 về 100 dù không có giao dịch nào làm giảm số dư. Đây là một dạng đọc lùi do load balancer chuyển request giữa các replica có mức replay khác nhau.

Sticky routing đến cùng replica có thể giảm nguy cơ đọc lùi do chuyển node, nhưng không tự bảo đảm read-your-writes nếu replica đó còn lag so với primary. Nếu replica bị failover hoặc client được chuyển sang node khác, cần cơ chế token/position để giữ mức nhất quán.

### 10.1. Causal consistency

Causal consistency yêu cầu một lần đọc sau phải thấy những thay đổi có quan hệ nhân quả với thao tác trước đó. Ví dụ, sau khi người dùng tạo đơn hàng rồi mở trang chi tiết đơn hàng đó, trang chi tiết phải thấy đơn vừa tạo.

Một mô hình thường dùng là truyền causal token hoặc commit position từ thao tác ghi sang thao tác đọc. Router chọn replica đã áp dụng ít nhất vị trí đó. Nếu không có replica nào đáp ứng, router có thể đọc primary hoặc chờ trong giới hạn.

Causal consistency mạnh hơn việc chỉ giữ cùng một replica theo phiên. Nó gắn yêu cầu đọc với một mốc dữ liệu cụ thể mà thao tác trước đã tạo ra.

## 11. Đọc nhiều bảng trong cùng transaction trên replica

Một transaction đọc-only có thể cần lấy dữ liệu từ nhiều bảng để tạo một kết quả nghiệp vụ. Ví dụ:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT *
FROM orders
WHERE order_id = 500;

SELECT *
FROM order_items
WHERE order_id = 500;

SELECT *
FROM payments
WHERE order_id = 500;

COMMIT;
```

Nếu database replica hỗ trợ snapshot isolation cho transaction, các câu lệnh có thể nhìn thấy một snapshot nhất quán cục bộ. Điều này hữu ích để tránh đọc header đơn hàng ở một trạng thái rồi đọc items ở một trạng thái khác do replica tiếp tục replay giữa các statement.

Tuy nhiên, snapshot đó vẫn có thể cũ hơn primary. Tính nhất quán giữa ba bảng ở replica không đồng nghĩa replica đã áp dụng commit mới nhất của primary.

Ở Read Committed, mỗi statement có thể nhìn thấy một mốc replay mới hơn statement trước. Điều đó có thể làm hai câu lệnh trong cùng transaction quan sát các trạng thái khác nhau nếu replica áp dụng log trong lúc transaction đang chạy, tùy DBMS và semantics isolation. Nếu cần một snapshot cục bộ ổn định cho nhiều câu lệnh, chọn isolation level phù hợp và kiểm tra hỗ trợ của engine.

## 12. Transaction dài trên replica và xung đột với replay

Một truy vấn đọc dài trên replica có thể cản trở việc replay các thay đổi cần thiết để duy trì bản sao. Một số DBMS phải lựa chọn giữa tiếp tục truy vấn đọc và áp dụng thay đổi từ primary.

Trong PostgreSQL hot standby, replay một số thao tác cleanup hoặc thay đổi cấu trúc có thể xung đột với snapshot mà truy vấn standby đang giữ. Tùy cấu hình như `max_standby_streaming_delay` và `hot_standby_feedback`, PostgreSQL có thể chờ replay, hủy truy vấn trên standby hoặc gửi feedback để primary giữ lại một số phiên bản lâu hơn.

Các đánh đổi:

- Cho truy vấn đọc thêm thời gian: báo cáo có thể hoàn tất, nhưng standby lag tăng.
- Ưu tiên replay: standby theo kịp primary hơn, nhưng truy vấn đọc dài có thể bị cancel.
- Bật feedback: giảm một số xung đột truy vấn bị hủy, nhưng primary có thể giữ tuple cũ lâu hơn và tăng bloat.

Đây là ví dụ cụ thể của việc transaction cục bộ trên replica ảnh hưởng đến replication progress. Nó không tạo ra khóa ghi trên primary theo cách thông thường, nhưng snapshot của truy vấn standby có thể làm thay đổi cách hệ thống xử lý cleanup/replay.

Không nên giữ transaction đọc mở lâu hơn nhu cầu. Với báo cáo lớn, cân nhắc chia batch, dùng snapshot/reporting replica riêng hoặc thiết kế workload để không làm replication lag tăng kéo dài.

## 13. Read replica thường là read-only

Nhiều read replica được cấu hình để từ chối thao tác ghi nghiệp vụ. Ví dụ, PostgreSQL hot standby chỉ cho phép truy vấn đọc trong trạng thái standby; MySQL replica thường dùng `read_only` hoặc `super_read_only`; SQL Server readable secondary trong Availability Group phục vụ workload đọc theo cấu hình.

Ứng dụng không nên giả định có thể chạy transaction đọc/ghi thông thường trên read replica. Nếu một luồng cần ghi, hãy gửi thao tác đó đến primary hoặc node được chỉ định làm writer.

Một số kiến trúc multi-primary hoặc distributed database cho phép ghi ở nhiều node, nhưng đó là mô hình khác với read replica truyền thống. Cần hiểu conflict resolution và transaction semantics riêng của hệ thống đó.

### 13.1. Read-only transaction có ích gì?

Khai báo transaction read-only có thể giúp DBMS xác nhận ý định chỉ đọc, áp dụng tối ưu hoặc từ chối thao tác ghi không hợp lệ. Ví dụ PostgreSQL:

```sql
BEGIN READ ONLY;

SELECT count(*)
FROM orders
WHERE created_at >= current_date;

COMMIT;
```

`READ ONLY` không phải một cam kết dữ liệu mới nhất. Nó chỉ giới hạn loại thao tác trong transaction theo quy tắc của DBMS.

## 14. Định tuyến đọc theo yêu cầu nhất quán

Không phải mọi truy vấn đều cần cùng mức độ mới. Có thể phân loại đường đọc:

| Loại thao tác | Mức nhất quán thường cần | Định tuyến gợi ý |
|---|---|---|
| Đọc ngay sau khi tạo/cập nhật | Read-your-writes | Primary hoặc replica đã replay đến commit token |
| Xem số dư, hạn mức hoặc trạng thái quyết định giao dịch | Dữ liệu mới nhất theo yêu cầu nghiệp vụ | Primary hoặc một cơ chế consistency token rõ ràng |
| Dashboard tổng hợp có thể chậm vài giây | Eventual consistency có giới hạn | Read replica với lag monitoring |
| Báo cáo lịch sử lớn | Snapshot nhất quán tại một mốc | Reporting replica/warehouse với transaction snapshot phù hợp |
| Chuỗi thao tác đọc có quan hệ nhân quả | Causal/monotonic reads | Sticky session kết hợp commit token hoặc wait-for-replay |
| Đọc không quan trọng, chấp nhận stale | Eventual consistency | Replica bất kỳ còn khỏe trong ngưỡng lag cho phép |

Một router có thể dùng chính sách sau:

```text
if request.requires_read_your_writes:
    if replica_can_replay(commit_token) within deadline:
        route_to_that_replica
    else:
        route_to_primary
else if request.accepts_staleness and replica_lag < threshold:
    route_to_healthy_replica
else:
    route_to_primary_or_consistent_read_path
```

Đây là pseudocode minh họa. Chính sách thật cần tính đến replica health, vùng địa lý, deadline, failover, chi phí primary và cách lấy token commit.

## 15. Một transaction không nên đổi replica giữa chừng

Nếu một transaction mở trên replica A rồi câu lệnh tiếp theo được router gửi sang replica B, transaction semantics có thể bị phá vỡ. Connection, transaction state, locks và snapshot thuộc một database session cụ thể.

Ví dụ không nên làm:

```text
Statement 1 -> Replica A -> BEGIN / đọc order header
Statement 2 -> Replica B -> đọc order items
Statement 3 -> Replica A -> đọc payment
```

Đây không phải một transaction cục bộ thống nhất. Mỗi connection/node có transaction state riêng; ứng dụng có thể ghép các phần dữ liệu từ những trạng thái replication khác nhau.

Khi bắt đầu transaction, router nên pin toàn bộ connection/transaction vào cùng database node cho đến khi commit/rollback. Nếu cần chuyển node vì failover, transaction cũ thường phải được xử lý như một lần thất bại và chạy lại theo quy tắc phù hợp, không tiếp tục nửa chừng trên node mới.

Ngay cả khi mọi statement ở cùng replica, nếu dùng Read Committed thì snapshot có thể khác giữa các statement theo semantics DBMS. Nếu nghiệp vụ cần một ảnh chụp nhất quán xuyên nhiều câu lệnh, cần isolation level tương ứng.

## 16. Failover và transaction đọc đang mở

Nếu replica đang phục vụ transaction bị promote thành primary hoặc bị loại khỏi cụm, connection hiện tại có thể mất. Transaction đọc cục bộ không tự động tiếp tục trên node mới vì snapshot và session state thuộc node cũ.

Ứng dụng cần:

- Xử lý lỗi connection và xác định transaction đã hoàn tất hay chưa.
- Với transaction read-only, thường có thể mở transaction mới trên node được định tuyến lại và chạy lại truy vấn.
- Với thao tác ghi, cần idempotency hoặc kiểm tra kết quả commit nếu kết quả không rõ.
- Không giả định node mới có cùng replay position hoặc cùng snapshot với node cũ.
- Sau failover, kiểm tra topology và vai trò writer/reader trước khi định tuyến tiếp.

Một lần promote có thể làm node mới trở thành primary nhưng các replica còn lại vẫn đang đồng bộ theo topology mới. Router cần cập nhật vai trò node và chính sách read-after-write theo trạng thái cụm mới.

## 17. Những hiểu lầm thường gặp

- **Transaction trên replica nhìn thấy mọi commit của primary.** Replica có thể chưa nhận hoặc chưa replay log.
- **Đã nhận WAL/binlog là truy vấn đọc thấy ngay.** Receive và apply/replay là các mốc khác nhau.
- **Serializable trên replica nghĩa là serializable toàn cụm.** Nó chỉ bảo vệ transaction theo phạm vi engine và dữ liệu mà node kiểm soát.
- **Refresh hoặc query lại luôn thấy dữ liệu mới.** Snapshot của transaction có thể vẫn cũ.
- **Sticky routing tự bảo đảm read-your-writes.** Cùng replica vẫn có thể lag so với primary; cần chờ commit position nếu cần bảo đảm.
- **Synchronous replication luôn đồng nghĩa replica đọc thấy commit ngay.** Semantics phụ thuộc chế độ xác nhận; có chế độ chỉ chờ nhận/ghi log, chưa chờ apply.
- **Một transaction có thể chạy qua nhiều replica như một connection.** Transaction state và snapshot thuộc một node/session; không nên đổi node giữa transaction.
- **Read-only nghĩa là dữ liệu mới nhất.** Read-only chỉ giới hạn thao tác ghi, không xác định freshness.
- **Đọc từ replica luôn rẻ và không ảnh hưởng primary.** Truy vấn dài có thể làm replay bị chậm hoặc gây xung đột cleanup tùy DBMS.

## 18. Quy trình điều tra dữ liệu cũ khi đọc qua replica

Khi người dùng báo rằng vừa cập nhật dữ liệu nhưng lần đọc sau vẫn thấy giá trị cũ, hãy kiểm tra theo thứ tự:

1. **Ghi ở node nào?** Xác nhận transaction ghi đã commit thành công trên primary hay chưa.
2. **Đọc ở node nào?** Ghi lại endpoint/replica thực tế được router chọn.
3. **Replica đã nhận log đến đâu?** Xem receive position hoặc trạng thái replication tương ứng.
4. **Replica đã apply/replay đến đâu?** So sánh với commit position của transaction cần đọc.
5. **Transaction đọc bắt đầu khi nào?** Một snapshot cũ có thể vẫn nhìn thấy dữ liệu cũ dù replica đã bắt kịp sau đó.
6. **Có chuyển replica giữa các statement không?** Kiểm tra connection pinning và load balancer.
7. **Isolation level là gì?** Xác định snapshot theo statement hay transaction.
8. **Có cache ở tầng ứng dụng hoặc ORM không?** Phân biệt dữ liệu cũ do replica với dữ liệu cũ từ identity map/cache.
9. **Có query dài hoặc replay conflict không?** Kiểm tra standby query cancel, lag và cấu hình feedback/delay.
10. **Yêu cầu nghiệp vụ là gì?** Xác định eventual consistency có chấp nhận được hay phải có read-your-writes/causal reads.

Nên ghi log database role/node, replication token, transaction start time và route decision ở mức đủ để chẩn đoán. Tránh log dữ liệu nhạy cảm hoặc thông tin xác thực.

## 19. Thiết kế API để thể hiện mức nhất quán

Một API có thể phân biệt rõ thao tác đọc chấp nhận stale và thao tác đọc cần xác nhận commit vừa xảy ra.

Ví dụ response sau khi ghi có thể trả về một token nhất quán:

```json
{
  "accountId": 42,
  "balance": 120,
  "consistencyToken": "<commit-position-or-opaque-token>"
}
```

Client gửi token khi đọc tiếp:

```http
GET /accounts/42
Consistency-Token: <commit-position-or-opaque-token>
```

Router có thể chờ replica đáp ứng token hoặc chuyển primary. Token nên được tạo/diễn giải bởi tầng database hoặc service tin cậy; không để client tự chọn một vị trí replication tùy ý.

Một cách đơn giản hơn là response ghi trả luôn representation mới từ primary. Client có thể hiển thị kết quả vừa xác nhận mà không lập tức đọc lại replica. Những lần đọc sau vẫn cần chính sách nhất quán phù hợp.

## 20. Những điểm cần ghi nhớ

- Transaction cục bộ trên read replica chỉ kiểm soát snapshot và isolation tại node đó; nó không tạo transaction ACID xuyên primary và replica.
- Replica có thể chậm hơn primary do replication lag; phải phân biệt log đã nhận với log đã replay/apply.
- Isolation level cục bộ không bảo đảm dữ liệu mới nhất toàn cụm. Serializable trên replica không phải global serializability.
- Snapshot cũ có thể tiếp tục nhìn thấy dữ liệu cũ dù replica replay thêm commit trong lúc transaction đang mở.
- Read-your-writes cần định tuyến về primary, chờ replica đến commit position hoặc dùng một token nhất quán.
- Monotonic reads và causal consistency có thể bị phá vỡ khi request chuyển giữa các replica có mức lag khác nhau.
- Giữ toàn bộ transaction trên cùng connection/node; không định tuyến từng statement của một transaction sang replica khác.
- Synchronous replication có nhiều mức xác nhận; chỉ một số chế độ chờ apply/replay trước khi commit được xác nhận.
- Transaction đọc dài có thể làm replay chậm hoặc bị cancel tùy DBMS; cần theo dõi lag và xung đột standby.
- Khi điều tra stale read, kiểm tra node ghi/đọc, commit position, replay position, transaction snapshot, router và cache.

Một read replica giúp tăng khả năng phục vụ truy vấn đọc, nhưng mỗi transaction trên đó chỉ có thể bảo đảm những gì node và isolation level của nó kiểm soát. Hãy phân loại rõ truy vấn nào chấp nhận eventual consistency, truy vấn nào cần read-your-writes hoặc causal consistency, rồi định tuyến hoặc chờ replay theo yêu cầu. Nhờ vậy, ứng dụng có thể tận dụng replica mà không nhầm tính nhất quán cục bộ với trạng thái mới nhất của toàn cụm.
