# Sẵn sàng cao

## Switchover, failover, fencing và kiểm chứng máy chủ được phép ghi

Trong hệ thống MySQL có tính sẵn sàng cao (high availability, HA), chuyển vai trò primary là một thay đổi có ảnh hưởng trực tiếp đến dữ liệu và khả năng phục vụ. **Switchover** là chuyển đổi có kế hoạch khi primary hiện tại vẫn hoạt động; **failover** là chuyển đổi sau khi primary gặp sự cố. Cả hai đều phải bảo đảm chỉ một máy chủ được phép nhận ghi tại một thời điểm.

Điểm quyết định của một lần chuyển đổi an toàn là fencing: cô lập hoặc vô hiệu hóa khả năng ghi của primary cũ trước khi mở quyền ghi trên primary mới. Nếu chỉ thấy máy chủ cũ không phản hồi từ một mạng mà đã mở ghi ở máy chủ khác, hệ thống có thể rơi vào split-brain: hai primary độc lập cùng nhận giao dịch. Khi kết nối trở lại, việc hợp nhất dữ liệu có thể rất khó hoặc không thể tự động.

Trong module `DATABASE_MYSQL`, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Những kỹ năng này là nền tảng để chuyển đổi HA: phải hiểu transaction đang chạy, replication lag, GTID, backup, quyền ghi và cách ứng dụng kết nối trước khi đổi vai trò máy chủ.

Bài này trình bày quy trình switchover, failover, fencing và kiểm chứng single-writer cho mô hình primary/replica. Các ví dụ SQL dùng tên `SOURCE`/`REPLICA` của MySQL 8.0.22 trở lên; MySQL 5.7 và các bản cũ hơn dùng `MASTER`/`SLAVE`. Hãy xác minh phiên bản, topology và công cụ điều phối trước khi thực hiện trên production.

### 1. Mục tiêu và thuật ngữ

Một quy trình chuyển đổi HA phải đáp ứng bốn mục tiêu:

1. **Không có hai writer:** tại mọi thời điểm chỉ một primary có quyền nhận ghi từ ứng dụng.
2. **Giới hạn mất dữ liệu:** chọn replica có dữ liệu gần nhất với primary và biết rõ giao dịch nào có thể bị mất.
3. **Chuyển hướng đúng:** proxy, router, VIP, DNS và connection pool phải đưa ứng dụng đến primary mới.
4. **Có thể kiểm chứng:** trạng thái máy chủ, GTID, quyền ghi, luồng replication và thao tác ứng dụng đều được kiểm tra sau chuyển đổi.

| Thuật ngữ | Ý nghĩa |
|---|---|
| Primary / source | Máy chủ hiện đang nhận ghi và phát binary log cho replica |
| Replica | Máy chủ nhận và áp dụng thay đổi từ source; thường chỉ phục vụ đọc |
| Switchover | Chuyển primary có kế hoạch, thường có thể đồng bộ giao dịch trước khi đổi vai trò |
| Failover | Chuyển primary khi primary hiện tại không còn phục vụ được hoặc được xác định là không an toàn |
| Fencing | Vô hiệu hóa khả năng ghi hoặc truy cập tài nguyên của primary cũ để ngăn nó tiếp tục hoạt động như writer |
| Split-brain | Hai hoặc nhiều node cùng tin rằng mình là primary và cùng nhận ghi |
| RPO | Mức mất dữ liệu tối đa có thể chấp nhận, tính theo thời gian hoặc giao dịch |
| RTO | Thời gian mục tiêu để khôi phục dịch vụ |

Replication bất đồng bộ không tự bảo đảm zero data loss. Replica có thể chưa nhận hoặc chưa áp dụng các giao dịch mới nhất khi primary hỏng. Switchover có kế hoạch thường có thể đạt RPO bằng 0 nếu dừng ghi, chờ đồng bộ và xác minh đầy đủ. Failover đột xuất phải đánh giá GTID và binlog còn lại để xác định giao dịch nào chưa được bảo vệ.

### 2. Chuẩn bị topology trước khi cần chuyển đổi

Không thể xây dựng một quy trình HA an toàn ngay giữa sự cố nếu chưa có baseline. Trước khi đưa hệ thống vào vận hành, cần xác định:

- Primary, replica, server UUID, server ID, channel và nguồn replication của từng node.
- Mô hình replication: bất đồng bộ, bán đồng bộ (semi-synchronous) hay Group Replication/InnoDB Cluster.
- Chính sách ghi: ứng dụng ghi qua một endpoint duy nhất; replica bật `read_only` và `super_read_only` theo thiết kế.
- Cơ chế điều phối: MySQL Router, proxy, load balancer, VIP, DNS hoặc nền tảng orchestration.
- Cơ chế fencing độc lập: dừng VM/instance, tắt nguồn, cô lập network, thu hồi quyền truy cập storage hoặc cơ chế lease/quorum được thiết kế rõ ràng.
- RPO/RTO, điều kiện chọn replica, ngưỡng replication lag và quy trình chấp nhận mất dữ liệu.
- Backup và binary log archive đủ để phục hồi hoặc dựng lại replica.
- Tài khoản quản trị, replication user, TLS, secret và quyền cần thiết cho thao tác chuyển vai trò.

Kiểm tra định danh trên từng máy chủ:

```sql
SELECT
  @@hostname AS hostname,
  @@server_id AS server_id,
  @@server_uuid AS server_uuid,
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only,
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.gtid_executed AS gtid_executed,
  @@GLOBAL.gtid_purged AS gtid_purged;
```

Mỗi instance phải có `server_id` và `server_uuid` duy nhất trong topology. Khi clone data directory, phải tuân theo quy trình tạo identity riêng của MySQL; không để hai node cùng sử dụng một identity. Lưu kết quả baseline cùng sơ đồ topology và runbook.

### 3. Switchover: chuyển đổi có kế hoạch

Switchover phù hợp khi primary cũ vẫn hoạt động, ứng dụng có thể tạm ngừng ghi và replica đích đang khỏe. Mục tiêu là đưa toàn bộ transaction đã commit trên primary cũ sang replica đích trước khi cho replica đó nhận ghi.

Giả sử `db-primary` đang là source và `db-replica-1` là replica được chọn làm primary mới.

#### 3.1. Kiểm tra điều kiện trước chuyển đổi

Trên primary và replica, ghi lại:

```sql
SELECT VERSION(), @@hostname, @@server_uuid,
       @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged,
       @@GLOBAL.read_only,
       @@GLOBAL.super_read_only;

SHOW REPLICA STATUS\G
```

Kiểm tra receiver và applier đều chạy, không có lỗi I/O hoặc SQL, không có backlog bất thường, disk còn đủ chỗ và replica không có transaction ghi ngoài luồng. Đối chiếu schema, filter replication, event scheduler và các tác vụ nền. Nếu có nhiều replica, xác định rõ node nào sẽ được promote và node nào sẽ theo primary mới.

Không chọn replica chỉ dựa trên `Seconds_Behind_Source`. Hãy kiểm tra `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, `gtid_executed` và lỗi worker. Nếu có transaction dài, parallel applier hoặc filter, phải đánh giá trạng thái thực tế của từng transaction.

#### 3.2. Ngừng ghi và drain transaction

1. Đưa ứng dụng vào maintenance hoặc bật chế độ chỉ đọc ở tầng ứng dụng để không tạo request ghi mới.
2. Chờ các transaction đang chạy hoàn tất hoặc xử lý theo chính sách timeout đã thống nhất.
3. Kiểm tra transaction còn mở và kết nối ghi; xác nhận không còn batch job, event hay tài khoản quản trị nào ghi vào primary.
4. Đặt primary cũ vào trạng thái read-only để tạo lớp bảo vệ bổ sung:

   ```sql
   SET GLOBAL super_read_only = ON;
   SET GLOBAL read_only = ON;
   ```

5. Ghi lại GTID set cuối cùng sau khi đã dừng mọi nguồn ghi:

   ```sql
   SELECT @@GLOBAL.gtid_executed AS final_source_gtids;
   ```

`super_read_only` và `read_only` là hàng rào ở tầng MySQL, hữu ích trong switchover khi node còn truy cập được. Chúng không thay thế fencing độc lập trong failover: một node bị cô lập mạng có thể vẫn đang chạy và có thể được một client khác truy cập; người có quyền quản trị cũng có thể thay đổi cấu hình. Hãy kiểm soát cả ứng dụng, tài khoản, proxy và node.

#### 3.3. Chờ replica áp dụng hết giao dịch

Trên replica được chọn, chờ tập GTID cuối cùng của primary cũ đã thực thi:

```sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'source_uuid:1-123456',
  60
) AS wait_result;
```

Thay chuỗi ví dụ bằng GTID set vừa ghi từ primary cũ. Kết quả `0` nghĩa là đã chờ đến khi tập GTID được thực thi; kết quả `1` nghĩa là timeout. Xử lý lỗi SQL riêng theo thông báo trả về. Nếu timeout, không promote: tìm transaction bị chặn, receiver/applier lỗi, thiếu binlog hoặc worker đang xử lý lâu.

Sau khi chờ thành công, xác nhận `GTID_SUBSET()`:

```sql
SELECT GTID_SUBSET(
  'source_uuid:1-123456',
  @@GLOBAL.gtid_executed
) AS source_history_is_present;
```

Kết quả `1` xác nhận GTID set nguồn là tập con của GTID đã thực thi trên replica. Đây là kiểm tra lịch sử giao dịch; vẫn cần kiểm tra dữ liệu và không có errant transaction ngoài dự kiến.

#### 3.4. Promote replica và chuyển hướng ứng dụng

Khi primary cũ đã ngừng ghi, replica đích đã áp dụng đủ giao dịch và fencing/chính sách chuyển vai trò được xác nhận:

1. Dừng replication channel trên node được promote:

   ```sql
   STOP REPLICA;
   ```

2. Xác nhận receiver/applier đã dừng và ghi lại GTID cuối cùng.
3. Cho phép ghi trên node mới:

   ```sql
   SET GLOBAL super_read_only = OFF;
   SET GLOBAL read_only = OFF;
   ```

4. Cập nhật MySQL Router/proxy/VIP hoặc endpoint ghi để trỏ đến primary mới.
5. Làm mới connection pool của ứng dụng; xác nhận kết nối mới đến đúng server UUID.
6. Chạy một giao dịch ghi kiểm thử có thể đối chiếu, sau đó xác nhận GTID mới tăng trên primary mới và các replica khác nhận được giao dịch.

Không cho ứng dụng ghi trước khi endpoint đã trỏ đúng node và node cũ đã bị giữ read-only/fenced. Với các replica còn lại, cấu hình chúng theo primary mới bằng `CHANGE REPLICATION SOURCE TO` và GTID auto-position theo runbook. Không reset metadata channel nếu chưa lưu cấu hình kết nối và trạng thái GTID.

### 4. Failover: chuyển đổi khi primary gặp sự cố

Failover khó hơn switchover vì primary cũ có thể không phản hồi, nhưng điều đó không chứng minh nó đã ngừng hoạt động. Nó có thể chỉ bị phân vùng mạng với hệ thống giám sát trong khi vẫn nhận ghi từ một nhóm client khác. Vì vậy, bước quan trọng nhất trước promote là xác định trạng thái node cũ và thực hiện fencing.

#### 4.1. Phân biệt primary hỏng và primary mất liên lạc

Thu thập tín hiệu từ nhiều nguồn độc lập:

- Health check của MySQL và hệ điều hành.
- Trạng thái VM/instance hoặc máy vật lý từ control plane/hypervisor.
- Kết nối mạng từ nhiều vùng giám sát, trạng thái DNS, firewall và load balancer.
- Log ứng dụng, proxy, Router và lỗi connection.
- Trạng thái replica, GTID, relay log và binary log cuối cùng đã nhận.
- Hệ thống quorum/lease nếu topology có cơ chế bầu chọn.

Ping thất bại hoặc một health check timeout không đủ để kết luận primary đã tắt. Đặt timeout failover quá thấp có thể khiến một đợt chậm mạng ngắn kích hoạt promote nhầm.

#### 4.2. Fencing primary cũ

Fencing là hành động làm cho primary cũ không thể tiếp tục ghi, ngay cả khi nó phục hồi hoặc vẫn chạy trong một phân vùng mạng. Tùy hạ tầng, có thể dùng:

| Cơ chế | Ví dụ | Điều cần xác minh |
|---|---|---|
| Power fencing | Tắt máy vật lý, dừng VM hoặc terminate instance qua control plane | Lệnh đã hoàn tất và node không còn chạy |
| Network fencing | Thu hồi security group, firewall rule hoặc cô lập VLAN | Không client nào có thể đến cổng MySQL hoặc endpoint ghi của node cũ |
| Storage fencing | Thu hồi quyền truy cập volume dùng chung hoặc dùng cơ chế reservation/lease được hỗ trợ | Node cũ không thể ghi vào tài nguyên lưu trữ có thể gây xung đột |
| Orchestrator/quorum fencing | Cơ chế HA quản lý lease, quorum và quyền primary | Chỉ một node giữ được quyền ghi; lease hết hạn phải được thực thi ở phía tài nguyên |
| Database-level read-only | Đặt `super_read_only=ON` khi còn kiểm soát được node | Đây là lớp phòng vệ bổ sung; không đủ khi node bị phân vùng và không thể điều khiển |

Fencing phải được xác nhận từ control plane hoặc cơ chế độc lập với MySQL trên node cũ. Nếu không xác minh được node cũ đã bị fence, không mở quyền ghi trên node mới. Giữ hệ thống ở chế độ không ghi trong lúc điều tra thường ít rủi ro hơn tạo hai lịch sử dữ liệu độc lập.

#### 4.3. Chọn replica để promote

Sau khi fence primary cũ, đánh giá tất cả replica đủ điều kiện:

1. Xác định node có receiver/applier khỏe trước sự cố và không có lỗi apply.
2. Thu thập `gtid_executed`, `gtid_purged`, `Retrieved_Gtid_Set` và GTID set theo từng channel.
3. So sánh các GTID set để xác định giao dịch đã áp dụng và giao dịch còn thiếu.
4. Kiểm tra candidate có errant GTID hoặc giao dịch ghi trực tiếp không.
5. Đối chiếu binlog/archive của primary cũ nếu còn truy cập được hoặc đã được lưu bên ngoài.
6. Chọn node có lịch sử giao dịch hợp lệ và đầy đủ nhất theo RPO; ghi rõ số giao dịch hoặc khoảng thời gian có thể mất.

Không mặc định replica có `Seconds_Behind_Source = 0` là candidate tốt nhất. Giá trị này có thể không phản ánh transaction chưa apply, lỗi worker hoặc sự khác biệt do thời điểm chụp. GTID giúp định lượng chênh lệch giao dịch, nhưng không chứng minh nội dung hàng dữ liệu giống nhau.

Nếu hai candidate có GTID set khác nhau, dùng `GTID_SUBTRACT(A, B)` và `GTID_SUBTRACT(B, A)` để tìm phần riêng của từng node. Phân tích nguồn gốc giao dịch thừa trước khi chọn. Không hợp nhất các GTID set bằng cách chỉnh metadata để ép hai node giống nhau.

#### 4.4. Promote và phục hồi topology

Khi đã xác nhận fencing và chọn candidate:

1. Lưu snapshot trạng thái và GTID của candidate.
2. Dừng receiver/applier trên candidate:

   ```sql
   STOP REPLICA;
   ```

3. Xác nhận node không có transaction apply đang dở và dữ liệu đã nhất quán đến GTID đã chọn.
4. Đặt `super_read_only=OFF`, sau đó `read_only=OFF` trên candidate theo runbook.
5. Cập nhật endpoint ghi, Router/proxy và connection pool.
6. Kiểm tra ứng dụng kết nối đúng server UUID; chạy giao dịch ghi thử và quan sát GTID.
7. Cấu hình các replica còn lại theo primary mới bằng GTID auto-position hoặc quy trình file/position phù hợp.
8. Theo dõi lỗi, replication lag, transaction và các chỉ số nghiệp vụ trong giai đoạn ổn định.

Primary cũ khi trở lại phải tiếp tục bị cô lập hoặc read-only. Không tự động cho nó nhận ghi. Kiểm tra GTID và dữ liệu; nếu node cũ có giao dịch riêng hoặc không thể chứng minh tương thích, dựng lại nó từ backup của primary mới rồi cấu hình làm replica. Chỉ đưa node trở lại topology sau khi xác nhận không còn lịch sử ghi phân kỳ.

### 5. Fencing và kiểm chứng single-writer

Một lần chuyển đổi chỉ được nghiệm thu khi chứng minh được node nào đang giữ quyền ghi và các node khác không thể nhận ghi từ ứng dụng.

#### 5.1. Kiểm tra ở tầng MySQL

Chạy truy vấn sau trên tất cả node có thể nhận traffic:

```sql
SELECT
  @@hostname AS hostname,
  @@server_uuid AS server_uuid,
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only,
  @@GLOBAL.gtid_executed AS gtid_executed;
```

Kết quả kỳ vọng trong mô hình single-primary cổ điển:

| Vai trò | `read_only` | `super_read_only` | Nhận ghi ứng dụng |
|---|---:|---:|---|
| Primary hiện tại | `0` | `0` | Có |
| Replica khỏe | `1` | `1` | Không |
| Primary cũ đã demote | `1` | `1` hoặc đã dừng/fenced | Không |

Các giá trị này là trạng thái mong muốn ở tầng database, không thay thế kiểm tra fencing. Cần kiểm tra người dùng có quyền thay đổi biến, tài khoản quản trị, event, scheduled job và ứng dụng có thể kết nối trực tiếp đến node nào.

#### 5.2. Kiểm tra ở tầng hạ tầng và ứng dụng

- Control plane xác nhận primary cũ đã dừng hoặc bị cô lập theo cơ chế fencing.
- Router/proxy/load balancer chỉ định tuyến endpoint ghi đến một server UUID.
- DNS/VIP đã cập nhật và các connection pool cũ đã được làm mới hoặc hết hạn.
- Các tài khoản ứng dụng không thể ghi trực tiếp vào replica hoặc primary cũ.
- Health check của endpoint ghi xác minh identity của server, không chỉ kiểm tra cổng TCP mở.
- Giao dịch kiểm thử trên primary mới tạo GTID mới; replica nhận và áp dụng GTID đó.
- Không có transaction mới xuất hiện trên node cũ sau thời điểm fence.

Nên có một cơ chế tự động từ chối ghi nếu node không sở hữu lease/quorum hoặc không được hệ thống điều phối xác nhận là primary. Khi dùng lease, phải bảo đảm lease được thực thi ở nơi có thể ngăn node cũ ghi; chỉ lưu timestamp lease trong ứng dụng mà không kiểm soát tài nguyên không đủ để chống split-brain.

### 6. Khác biệt theo mô hình HA

Quy trình primary/replica cổ điển ở trên không thay thế cơ chế quản lý membership của Group Replication hoặc InnoDB Cluster.

| Mô hình | Cơ chế chọn primary | Lưu ý chuyển đổi |
|---|---|---|
| Asynchronous replication | Người vận hành hoặc orchestrator chọn replica | Có thể mất giao dịch chưa được replica nhận/applied; phải so sánh GTID và fencing primary cũ |
| Semi-synchronous replication | Vẫn cần quy trình chọn và promote replica | ACK xác nhận ít nhất một replica nhận sự kiện theo cấu hình; không đồng nghĩa mọi candidate đã apply hoặc bảo đảm zero data loss |
| Group Replication single-primary | Thành viên nhóm và cơ chế bầu primary của group | Kiểm tra quorum, trạng thái member, transaction certification và primary hiện tại; tránh can thiệp membership khi chưa hiểu trạng thái group |
| InnoDB Cluster | Group Replication kết hợp MySQL Shell AdminAPI và MySQL Router | Dùng trạng thái cluster/metadata và quy trình failover của AdminAPI; kiểm tra Router và client routing sau chuyển đổi |

Trong Group Replication, quorum là điều kiện quan trọng để nhóm tiếp tục hoạt động nhất quán. Một phân vùng thiểu số không nên tự ý được ép thành primary. Các lệnh ép quorum hoặc cấu hình `group_replication_force_members` có thể làm tăng nguy cơ split-brain nếu thành viên cũ vẫn hoạt động ở phân vùng khác. Chỉ dùng theo quy trình phục hồi Group Replication của đúng phiên bản sau khi xác minh trạng thái mọi thành viên.

Semi-synchronous replication giảm cửa sổ mất dữ liệu trong một số tình huống, nhưng không bảo đảm candidate được chọn đã áp dụng transaction cuối cùng. Khi timeout, hệ thống có thể quay về asynchronous theo cấu hình. Hãy kiểm tra chế độ thực tế và GTID của từng replica thay vì xem nhãn “semi-sync” là bảo đảm không mất dữ liệu.

### 7. Lỗi thường gặp trong chuyển đổi HA

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai node cùng nhận ghi | Promote trước khi fence primary cũ hoặc routing còn trỏ đến node cũ | Ngừng ghi, fence node cũ, xác định lịch sử dữ liệu phân kỳ và lập kế hoạch hợp nhất/re-seed có kiểm chứng |
| Promote xong nhưng thiếu giao dịch | Replica chưa apply hết GTID hoặc failover bất đồng bộ có transaction chưa truyền | Định lượng GTID thiếu, kiểm tra binlog/archive của primary cũ và thông báo mức RPO thực tế |
| `WAIT_FOR_EXECUTED_GTID_SET` timeout | Applier lỗi, relay log thiếu, transaction dài hoặc GTID set không đúng | Kiểm tra trạng thái worker, source GTID và binlog; không promote chỉ để bỏ qua timeout |
| Ứng dụng vẫn ghi vào primary cũ | Connection pool giữ kết nối, DNS/VIP chưa cập nhật hoặc có đường kết nối trực tiếp | Fencing node cũ, thu hồi endpoint cũ, làm mới pool và xác minh server UUID trong ứng dụng |
| Replica mới có GTID thừa | Ghi trực tiếp, nhiều nguồn hoặc dữ liệu từ lần restore trước | Xác định origin và dữ liệu liên quan; không xóa GTID bằng thao tác metadata tùy tiện |
| Primary cũ không thể rejoin | Có transaction phân kỳ, cấu hình source cũ hoặc GTID không tương thích | Giữ node read-only/fenced, đối chiếu lịch sử và re-seed từ primary mới nếu cần |
| Router báo primary sai | Metadata hoặc health check chưa cập nhật | Kiểm tra trạng thái cluster/metadata, endpoint và identity; chỉ mở traffic sau khi định tuyến được xác minh |

### 8. Runbook switchover và failover

Runbook nên chỉ rõ người quyết định, người thực hiện, nguồn dữ liệu, điều kiện dừng và cách quay lại. Có thể dùng khung sau làm mẫu.

**Switchover có kế hoạch**

1. Thông báo cửa sổ bảo trì và chuyển ứng dụng sang chế độ không ghi.
2. Xác nhận source/replica khỏe, chọn candidate và lưu trạng thái/GTID ban đầu.
3. Drain transaction, dừng mọi job ghi và đặt source cũ `super_read_only=ON`.
4. Ghi GTID cuối của source; chờ candidate thực thi đủ bằng `WAIT_FOR_EXECUTED_GTID_SET`.
5. Xác minh GTID subset, không có lỗi apply và dữ liệu đạt tiêu chí.
6. Dừng replication trên candidate, mở quyền ghi ở candidate.
7. Chuyển endpoint ghi, làm mới connection pool và xác minh server UUID.
8. Cấu hình source cũ thành replica của primary mới; xác minh single-writer và theo dõi.

**Failover do sự cố**

1. Xác nhận sự cố bằng nhiều nguồn giám sát và xác định nguy cơ phân vùng mạng.
2. Chặn traffic ghi và thực hiện fencing primary cũ bằng cơ chế độc lập.
3. Thu thập GTID/binlog còn lại từ archive và các replica; đánh giá RPO.
4. Chọn candidate có lịch sử giao dịch hợp lệ và đầy đủ nhất; kiểm tra GTID thừa.
5. Dừng replication ở candidate, promote và chuyển endpoint sau khi fencing được xác nhận.
6. Kiểm tra ứng dụng ghi vào đúng server UUID, GTID tăng và replica khác bắt đầu theo primary mới.
7. Giữ primary cũ fenced/read-only khi phục hồi; xác định có thể rejoin hay cần re-seed.
8. Ghi lại transaction có thể mất, thời gian RTO, quyết định và bằng chứng nghiệm thu.

**Điều kiện dừng quy trình**

- Không xác minh được primary cũ đã bị fence.
- Không xác định được candidate có lịch sử dữ liệu hợp lệ.
- GTID hoặc schema cho thấy giao dịch phân kỳ chưa được giải thích.
- Không thể kiểm soát endpoint ghi hoặc tài khoản có thể bypass proxy.
- RPO dự kiến vượt mức được phê duyệt mà chưa có quyết định của người chịu trách nhiệm.

### 9. Bài tập thực hành

Một hệ thống MySQL có `db-primary`, `db-replica-a` và `db-replica-b`, dùng asynchronous replication với GTID. Ứng dụng ghi qua proxy. Primary mất kết nối từ vùng giám sát chính, nhưng control plane vẫn báo VM đang chạy. Hai replica có `gtid_executed` khác nhau; replica A có ít GTID hơn replica B nhưng B có một số GTID không xuất hiện ở A.

1. Vì sao mất kết nối từ monitoring không đủ để promote ngay?
2. Bạn cần fencing primary bằng cách nào và lấy bằng chứng xác nhận từ đâu?
3. Dùng `GTID_SUBTRACT` để phân tích GTID thiếu/thừa giữa hai replica. Vì sao không thể chỉ chọn node có số GTID lớn nhất?
4. Làm thế nào xác định transaction cuối cùng của primary có được replica nhận và apply hay chưa?
5. Nếu không thể lấy binary log từ primary, bạn sẽ đánh giá RPO và thông báo mức mất dữ liệu như thế nào?
6. Sau promote, cần kiểm tra những gì ở MySQL, proxy, connection pool và ứng dụng để chứng minh chỉ có một writer?
7. Khi primary cũ phục hồi, điều kiện nào cho phép cấu hình nó thành replica? Khi nào cần re-seed?

### 10. Checklist nghiệm thu single-writer

- [ ] Đã xác định rõ mô hình HA, phiên bản, topology, source UUID và candidate.
- [ ] Đã lưu trạng thái replication, GTID set, lỗi worker và backup/binlog trước chuyển đổi.
- [ ] Với switchover, ứng dụng đã ngừng ghi và transaction đã được drain.
- [ ] Với failover, primary cũ đã được fence bằng cơ chế độc lập và có bằng chứng hoàn tất.
- [ ] Candidate đã áp dụng toàn bộ GTID cần thiết hoặc RPO mất dữ liệu đã được đánh giá/phê duyệt.
- [ ] Không có errant transaction chưa giải thích trên candidate.
- [ ] Chỉ primary mới có `read_only=OFF` và `super_read_only=OFF` theo thiết kế.
- [ ] Replica và primary cũ không nhận ghi ứng dụng; primary cũ tiếp tục bị fence/read-only khi phục hồi.
- [ ] Router/proxy/VIP/DNS và connection pool đã trỏ đến đúng server UUID.
- [ ] Giao dịch ghi kiểm thử thành công trên primary mới và GTID mới được replica nhận/applied.
- [ ] Dữ liệu nghiệp vụ, replication lag, lỗi và các job nền đã được kiểm tra.
- [ ] Runbook, thời điểm chuyển đổi, RPO/RTO thực tế và quyết định vận hành đã được ghi lại.

### 11. Nguyên tắc vận hành

Switchover cần drain transaction và đồng bộ replica trước khi đổi vai trò. Failover cần xác định primary cũ có thật sự mất quyền ghi hay chỉ mất liên lạc với một vùng mạng. Fencing là điều kiện để ngăn split-brain; `read_only` và `super_read_only` là lớp bảo vệ trong MySQL, không thay thế fencing độc lập. Chọn candidate bằng GTID và bằng chứng dữ liệu, sau đó kiểm tra cả MySQL, hạ tầng và đường kết nối ứng dụng. Chỉ kết thúc chuyển đổi khi chứng minh được một writer duy nhất, replica theo đúng primary mới và mức mất dữ liệu nằm trong RPO đã chấp nhận.
