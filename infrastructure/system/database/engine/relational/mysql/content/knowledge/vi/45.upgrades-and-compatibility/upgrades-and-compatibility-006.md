# Thứ tự nâng cấp source/replica hoặc thành viên cụm

Bài học này thuộc module **DATABASE_MYSQL**. Khi nâng cấp MySQL trong hệ thống đang replication hoặc chạy InnoDB Cluster, thứ tự nâng cấp ảnh hưởng trực tiếp đến khả năng duy trì dịch vụ, tính tương thích của luồng replication và khả năng quay lui. Một máy chủ độc lập có thể được nâng cấp trong một cửa sổ bảo trì; một topology nhiều máy chủ cần nâng cấp theo thứ tự để các node còn hoạt động tiếp tục trao đổi dữ liệu và duy trì quorum.

Với replication bất đồng bộ thông thường, nguyên tắc triển khai phổ biến là **nâng cấp replica trước, source sau**. Với Group Replication/InnoDB Cluster ở chế độ single-primary, thường nâng cấp các secondary lần lượt và nâng cấp primary sau cùng. Trong cả hai mô hình, cần kiểm tra ma trận tương thích của đúng cặp phiên bản, giữ trạng thái replication/quorum khỏe mạnh và xác minh từng node đã hoạt động ổn định trước khi chuyển sang node kế tiếp.

## 1. Vì sao thứ tự nâng cấp quan trọng?

Trong một topology MySQL, các node có thể đang chạy nhiều vai trò:

- **Source/primary:** nhận transaction ghi và phát binary log.
- **Replica/secondary:** nhận sự kiện từ source hoặc tham gia Group Replication để duy trì bản sao dữ liệu.
- **Router/proxy:** định tuyến kết nối ứng dụng đến primary hoặc secondary.
- **MySQL Shell/AdminAPI:** công cụ quản trị và kiểm tra cấu hình cụm.

Nâng cấp sai thứ tự có thể làm source phát sự kiện mà replica cũ không hiểu, khiến replica dừng áp dụng log; hoặc làm cụm mất quorum khi nhiều thành viên cùng offline. Một lần nâng cấp cũng có thể cập nhật data dictionary và định dạng nội bộ của data directory, khiến việc quay lại binary cũ không còn an toàn.

Các mục tiêu khi lập thứ tự:

1. Giữ topology ở trạng thái tương thích trong toàn bộ giai đoạn mixed-version.
2. Chỉ đưa một node ra khỏi dịch vụ tại một thời điểm, nếu kiến trúc và quy trình hỗ trợ rolling upgrade.
3. Duy trì đủ replica hoặc thành viên để đáp ứng RPO, availability và quorum.
4. Đảm bảo dữ liệu đã được nhận và áp dụng đầy đủ trước khi chuyển vai trò hoặc nâng cấp source.
5. Có backup và đường phục hồi phù hợp với phiên bản trước nâng cấp.

## 2. Quy tắc tương thích phiên bản

Trước khi chọn thứ tự, phải xác định chính xác phiên bản nguồn và phiên bản đích. Không phải mọi cặp phiên bản MySQL đều hỗ trợ replication hoặc Group Replication khi chạy xen kẽ.

Với asynchronous replication trong các tổ hợp phiên bản được hỗ trợ, quy tắc chung là source phải cùng phiên bản hoặc cũ hơn replica. Không thiết kế luồng replication từ source mới hơn sang replica cũ hơn rồi giả định nó sẽ hoạt động. Ngoài quy tắc tổng quát này, cần kiểm tra giới hạn theo release series, phiên bản vá, định dạng sự kiện binlog, tính năng được sử dụng và tài liệu upgrade path của phiên bản đích.

| Trạng thái topology | Đánh giá |
|---|---|
| Source cũ, replica mới hơn trong cặp phiên bản được hỗ trợ | Có thể dùng làm trạng thái trung gian khi nâng cấp replica trước source |
| Source và replica cùng phiên bản | Trạng thái bình thường sau khi nâng cấp hoàn tất |
| Source mới hơn, replica cũ hơn | Không dùng làm trạng thái replication mục tiêu; chiều này không được hỗ trợ trong các quy tắc tương thích thông thường |
| Bỏ qua nhiều release series | Chỉ thực hiện nếu upgrade path chính thức cho phép; có thể phải nâng cấp qua phiên bản trung gian |
| Group Replication có thành viên khác phiên bản | Chỉ duy trì trong cửa sổ rolling upgrade được tài liệu hỗ trợ; không xem mixed-version là trạng thái vận hành lâu dài |

Không chỉ so sánh số phiên bản. Hãy kiểm tra cả edition/distribution, plugin, authentication, TLS, cấu hình binlog, GTID và các tính năng ứng dụng đang sử dụng. Nếu bản nâng cấp thay đổi hành vi SQL hoặc loại bỏ một tính năng, ứng dụng có thể lỗi dù replication vẫn chạy.

## 3. Chuẩn bị chung trước khi nâng cấp

### 3.1. Ghi nhận topology và vai trò

Lập sơ đồ các node, phiên bản, vai trò, luồng replication, endpoint ứng dụng, Router/proxy và vị trí triển khai. Với replication dây chuyền, ghi rõ node nào là source của node nào.

Trên từng máy chủ, ghi lại phiên bản và định danh:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution,
       @@hostname AS host_name,
       @@server_id AS server_id,
       @@server_uuid AS server_uuid;
```

Với asynchronous replication, kiểm tra trạng thái replica bằng cú pháp phù hợp phiên bản. MySQL 8.0.22 trở lên dùng:

```sql
SHOW REPLICA STATUS\G
```

Các bản cũ hơn có thể dùng tên lệnh `SHOW SLAVE STATUS`. Hãy kiểm tra ít nhất:

- Receiver/IO thread và applier/SQL thread đang chạy.
- Không có lỗi ở phần nhận hoặc áp dụng transaction.
- Replication lag nằm trong ngưỡng cho phép.
- GTID đã nhận và đã thực thi phù hợp với source.
- Binary log cần thiết còn trong retention và đủ thời gian cho toàn bộ cửa sổ nâng cấp.

Với Group Replication, kiểm tra trạng thái thành viên:

```sql
SELECT MEMBER_ID, MEMBER_HOST, MEMBER_PORT,
       MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Trước khi bắt đầu, các thành viên cần ở trạng thái mong đợi, thường là `ONLINE`, có đúng một primary trong single-primary mode và nhóm còn quorum. Nếu có node `RECOVERING`, `ERROR`, `UNREACHABLE` hoặc thành viên đang rời nhóm, hãy xử lý trước khi nâng cấp.

### 3.2. Backup và kiểm chứng khả năng phục hồi

Tạo backup nhất quán trước khi nâng cấp. Với hệ thống quan trọng, giữ backup phù hợp cho source và kế hoạch tái tạo replica. Backup phải nằm ngoài data directory và được bảo vệ khỏi thao tác nâng cấp hoặc lỗi storage tại chỗ.

Kiểm tra:

1. Backup hoàn tất và có checksum/metadata cần thiết.
2. Đã thử restore trên một máy chủ độc lập với phiên bản tương ứng.
3. Có binary log/GTID cần thiết để phục hồi tới điểm mục tiêu.
4. Đã lưu cấu hình, TLS certificate, keyring, plugin và secret cần cho khởi động.
5. Đã biết cách dựng lại replica nếu upgrade một node thất bại.

Không coi snapshot của data directory là backup dùng được nếu chưa xác minh cách restore và tính tương thích với phiên bản MySQL tương ứng.

### 3.3. Kiểm tra tương thích và điều kiện vận hành

- Đọc release notes, upgrade path và ma trận tương thích của phiên bản đích.
- Chạy công cụ kiểm tra upgrade/configuration mà phiên bản hỗ trợ, ví dụ MySQL Shell AdminAPI cho instance thuộc InnoDB Cluster.
- Kiểm tra plugin/component, authentication plugin, audit, keyring và TLS có phiên bản tương thích.
- Kiểm tra dung lượng trống cho package, temporary files, redo/undo, binary log và backup.
- Kiểm tra transaction dài, metadata lock, DDL đang chạy và tác vụ batch lớn.
- Xác nhận `server_id` và `server_uuid` không bị trùng giữa các node.
- Kiểm tra ứng dụng tương thích với cả phiên bản cũ và mới trong giai đoạn chuyển tiếp.
- Lập cửa sổ bảo trì, tiêu chí dừng, người chịu trách nhiệm và kế hoạch thông báo.

Không triển khai schema hoặc câu lệnh SQL chỉ có ở phiên bản mới khi còn node cũ cần đọc hoặc áp dụng thay đổi đó.

## 4. Thứ tự nâng cấp asynchronous source/replica

### 4.1. Vì sao nâng cấp replica trước?

Giả sử topology có một source MySQL phiên bản cũ và ba replica. Trong upgrade path cho phép source cũ phát binlog sang replica mới, ta có thể nâng cấp từng replica trước. Source vẫn chạy phiên bản cũ trong lúc các replica được nâng cấp và tiếp tục nhận transaction.

Khi tất cả replica đã chạy phiên bản đích và hoạt động ổn định, mới nâng cấp source. Như vậy, source không phát binlog từ phiên bản mới tới replica còn ở phiên bản cũ. Đây là lý do quan trọng của thứ tự replica trước, source sau.

```text
Trước nâng cấp:
                 Source vA
                /    |    \
               v     v     v
          Replica vA vA   Replica vA

Trong giai đoạn nâng cấp replica:
                 Source vA
                /    |    \
               v     v     v
          Replica vB vA   Replica vA

Sau khi mọi replica đã nâng cấp:
                 Source vA
                /    |    \
               v     v     v
          Replica vB vB   Replica vB

Cuối cùng nâng cấp source:
                 Source vB
                /    |    \
               v     v     v
          Replica vB vB   Replica vB
```

Sơ đồ minh họa thứ tự; chỉ thực hiện nếu cặp phiên bản vA/vB được hỗ trợ cho replication trong thời gian nâng cấp.

### 4.2. Nếu có replication dây chuyền

Với topology source A → replica B → replica C, nên nâng cấp từ các node lá đi ngược về gốc: C trước, B tiếp theo, A sau cùng. Khi nâng cấp B, C đã chạy phiên bản mới; B vẫn nhận binlog từ A phiên bản cũ và có thể phát lại log tới C mới trong giới hạn tương thích đã xác minh.

Nếu có nhiều nhánh, nâng cấp các replica ở cùng tầng độc lập từng node, sau đó tiến dần về source gốc. Luôn xác minh compatibility ở từng cạnh source→replica, không chỉ kiểm tra phiên bản của hai node đầu-cuối.

### 4.3. Quy trình nâng cấp từng replica

1. **Chọn một replica:** ưu tiên node ít ảnh hưởng tới ứng dụng đọc và không phải failover candidate duy nhất.
2. **Kiểm tra bắt kịp:** xác nhận replica đã áp dụng hết transaction cần thiết và không có lỗi replication.
3. **Giảm hoặc chuyển tải đọc:** nếu replica đang phục vụ truy vấn, chuyển traffic sang node khác theo kế hoạch.
4. **Dừng replication và MySQL có kiểm soát:** dùng quy trình shutdown/stop replica đúng phiên bản, không xóa relay log hoặc file dữ liệu bằng tay.
5. **Nâng cấp phần mềm và dữ liệu:** thực hiện quy trình in-place upgrade hoặc restore/rebuild đã thử cho phiên bản đích.
6. **Khởi động và kiểm tra:** xem error log, trạng thái server, plugin, cấu hình, data dictionary và cảnh báo.
7. **Kết nối lại replication:** cấu hình source/replication channel và GTID hoặc file/position theo runbook.
8. **Chờ bắt kịp:** xác nhận receiver/applier chạy, không có lỗi và lag trở về mức chấp nhận được.
9. **Khôi phục traffic đọc:** chỉ đưa node trở lại pool khi đã kiểm tra query và hiệu năng.
10. **Chuyển sang replica tiếp theo:** chỉ khi node vừa nâng cấp ổn định.

Không nâng cấp đồng thời nhiều replica nếu điều đó làm mất toàn bộ khả năng dự phòng hoặc khiến source không còn replica đủ mới. Với một source và chỉ một replica, cần quyết định rõ cửa sổ không có bản sao dự phòng, RPO chấp nhận được và phương án tái tạo replica nếu thất bại.

### 4.4. Nâng cấp source sau cùng

Khi mọi replica đã chạy phiên bản đích:

1. Xác nhận các replica đều khỏe, bắt kịp và có GTID/position phù hợp.
2. Dừng hoặc khóa luồng ghi ứng dụng theo kế hoạch cutover.
3. Xác nhận không còn transaction đang chạy hoặc transaction dài cản trở shutdown.
4. Ghi nhận điểm cuối và tạo backup/snapshot cần thiết.
5. Dừng source sạch sẽ và nâng cấp server theo upgrade path.
6. Khởi động source, kiểm tra error log, data dictionary, plugin và cấu hình.
7. Xác nhận binary logging và GTID hoạt động theo đúng thiết kế.
8. Xác minh các replica kết nối lại và tiếp tục áp dụng transaction.
9. Chạy smoke test, mở lại ghi và theo dõi replication lag.

Nếu source không khởi động hoặc replication không hoạt động sau nâng cấp, giữ hệ thống ở trạng thái bảo trì và thực hiện runbook phục hồi. Không vội promote một node rồi để source cũ tiếp tục nhận ghi.

## 5. Thứ tự nâng cấp Group Replication và InnoDB Cluster

InnoDB Cluster dùng Group Replication để duy trì nhóm thành viên và MySQL Router để định tuyến kết nối. Với single-primary mode, một node là primary nhận ghi, các node còn lại là secondary.

### 5.1. Nguyên tắc rolling upgrade

Với một upgrade path hỗ trợ mixed-version Group Replication, thứ tự thường dùng là:

1. Nâng cấp một secondary.
2. Chờ secondary khởi động, tham gia nhóm và trở lại trạng thái `ONLINE`.
3. Xác minh nhóm vẫn có quorum, primary còn hoạt động và transaction được đồng bộ.
4. Nâng cấp secondary kế tiếp.
5. Sau khi các secondary đã nâng cấp và ổn định, thực hiện switchover có kế hoạch nếu cần để đưa primary hiện tại thành secondary.
6. Nâng cấp node primary cũ sau cùng.
7. Xác minh toàn bộ thành viên cùng chạy phiên bản đích, nhóm khỏe mạnh và primary được xác định đúng.

Không dừng nhiều thành viên cùng lúc. Với nhóm ba node, khi một node offline, hai node còn lại có thể duy trì đa số; nếu tiếp tục dừng thêm một node, nhóm có thể mất quorum và không thể tiếp tục nhận ghi. Cần tính toán quorum theo trạng thái thành viên thực tế và cấu hình failure detection, không chỉ nhìn số node ban đầu.

### 5.2. Thứ tự secondary trước, primary sau

Ví dụ cụm ba node single-primary:

```text
Ban đầu:
       Node A (PRIMARY, vA)
       Node B (SECONDARY, vA)
       Node C (SECONDARY, vA)

Nâng cấp B, chờ ONLINE:
       Node A (PRIMARY, vA)
       Node B (SECONDARY, vB)
       Node C (SECONDARY, vA)

Nâng cấp C, chờ ONLINE:
       Node A (PRIMARY, vA)
       Node B (SECONDARY, vB)
       Node C (SECONDARY, vB)

Chuyển primary sang node đã nâng cấp nếu runbook yêu cầu:
       Node A (SECONDARY, vA)
       Node B (PRIMARY, vB)
       Node C (SECONDARY, vB)

Nâng cấp A:
       Node A (SECONDARY, vB)
       Node B (PRIMARY, vB)
       Node C (SECONDARY, vB)
```

Sơ đồ chỉ mô tả thứ tự vai trò. Thực tế, Group Replication có thể bầu primary theo cấu hình và trạng thái nhóm; hãy dùng thao tác switchover của MySQL Shell/AdminAPI hoặc runbook đã được xác minh. Không chỉnh sửa metadata của cụm bằng tay.

### 5.3. Multi-primary mode

Trong multi-primary mode, nhiều thành viên có thể nhận ghi. Không có một primary duy nhất để nâng cấp cuối cùng. Cần:

- Xác minh phiên bản đích hỗ trợ rolling upgrade với phiên bản hiện tại của toàn nhóm.
- Cân nhắc chuyển sang single-primary trước nâng cấp nếu quy trình và ứng dụng cho phép.
- Loại từng node khỏi traffic ghi, nâng cấp và chờ node trở lại `ONLINE` trước khi tiếp tục.
- Duy trì quorum và kiểm soát certification failure, retry và transaction đang chạy.
- Không để hai phiên bản cùng xử lý workload dùng tính năng SQL khác nhau trong thời gian chuyển tiếp.

Nếu phiên bản hoặc topology không hỗ trợ mixed-version rolling upgrade, dùng quy trình nâng cấp offline hoặc dựng cụm mới song song rồi chuyển ứng dụng theo kế hoạch. Không ép một rolling upgrade chỉ vì muốn tránh downtime.

### 5.4. Kiểm tra trạng thái nhóm sau mỗi node

Sau khi một thành viên tham gia lại, kiểm tra:

```sql
SELECT MEMBER_HOST, MEMBER_PORT, MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Chỉ chuyển sang node tiếp theo khi thành viên vừa nâng cấp đã `ONLINE`, không có lỗi recovery và nhóm có đủ quorum. Kiểm tra thêm log của Group Replication, transaction certification, flow control và replication applier. `ONLINE` là điều kiện cần, nhưng vẫn cần kiểm tra ứng dụng và tải thực tế.

## 6. Router, MySQL Shell và các thành phần phụ trợ

Máy chủ database không phải thành phần duy nhất cần nâng cấp. InnoDB Cluster còn có MySQL Router, MySQL Shell/AdminAPI, plugin và công cụ giám sát.

Một thứ tự quản lý an toàn thường là:

1. Kiểm tra phiên bản Router và Shell hiện tại có tương thích với cả phiên bản cluster trước và sau nâng cấp hay không.
2. Giữ Router hoạt động trong thời gian rolling upgrade nếu phiên bản đó hỗ trợ kết nối tới các node ở trạng thái mixed-version.
3. Nâng cấp Router theo từng instance, duy trì ít nhất một Router khỏe mạnh nếu ứng dụng đang dùng nhiều instance.
4. Sau khi server cluster đã nâng cấp và ổn định, nâng cấp các công cụ quản trị/giám sát theo ma trận tương thích.
5. Kiểm tra lại routing tới primary và secondary, TLS, metadata cluster và health check.

Không giả định Router, Shell hoặc plugin có thể dùng với mọi phiên bản server. Kiểm tra release notes và compatibility matrix riêng cho từng thành phần. Nếu metadata InnoDB Cluster cần nâng cấp, thực hiện bằng AdminAPI ở phiên bản và thời điểm được tài liệu yêu cầu; không tự sửa bảng metadata.

## 7. Những điều cần tránh trong giai đoạn mixed-version

Trong thời gian các node chạy hai phiên bản:

- Không dùng cú pháp hoặc tính năng chỉ có ở phiên bản mới nếu node cũ vẫn phải parse hoặc áp dụng statement đó.
- Tránh thay đổi schema lớn cùng lúc với nâng cấp server; tách hai hoạt động để dễ khoanh vùng lỗi.
- Không đổi `binlog_format`, GTID mode, authentication plugin hoặc TLS policy ngoài kế hoạch upgrade.
- Không xóa binlog mà replica còn cần; retention phải đủ cho node offline nâng cấp và bắt kịp.
- Không sao chép `auto.cnf` hoặc nhân bản `server_uuid` sang node mới.
- Không cho ứng dụng ghi trực tiếp vào replica/secondary trong khi vai trò đang chuyển đổi.
- Không nâng cấp thêm node khi node vừa nâng cấp chưa `ONLINE` hoặc replication chưa bắt kịp.
- Không coi việc service khởi động thành công là bằng chứng dữ liệu và replication đã đúng.

Các thay đổi về data dictionary, SQL mode, collation, optimizer, authentication và plugin có thể ảnh hưởng ứng dụng. Nên kiểm tra workload đại diện trên phiên bản mới trước khi nâng cấp toàn bộ topology.

## 8. Kế hoạch rollback và phục hồi node lỗi

Nâng cấp MySQL có thể cập nhật định dạng dữ liệu nội bộ. Đặc biệt với major upgrade, không được giả định rằng chỉ cần cài lại binary phiên bản cũ là có thể mở data directory đã được phiên bản mới nâng cấp.

### 8.1. Một replica nâng cấp thất bại

Nếu replica không khởi động hoặc không tham gia lại được:

1. Giữ source và các replica còn lại hoạt động ổn định.
2. Đọc error log, xác định lỗi package, plugin, cấu hình, data dictionary hay replication.
3. Không tiếp tục nâng cấp replica khác nếu điều đó làm giảm dự phòng dưới mức cho phép.
4. Phục hồi replica từ backup/snapshot tương ứng hoặc dựng lại replica từ source theo quy trình đã thử.
5. Xác minh GTID/position, replication và trạng thái bắt kịp trước khi đưa node trở lại pool.

### 8.2. Source hoặc primary nâng cấp thất bại

Nếu source không thể khởi động sau nâng cấp, giữ ghi ứng dụng bị dừng. Xác định liệu có thể sửa lỗi trên phiên bản đích hay cần restore backup trước nâng cấp. Nếu phải quay lại phiên bản cũ, dùng data directory/backup tương thích với phiên bản cũ và khôi phục log đến điểm phù hợp.

Với Group Replication, nếu primary không quay lại được, chỉ thực hiện failover hoặc bootstrap nhóm theo runbook đã xác minh. Tránh bootstrap một nhóm mới khi các thành viên khác vẫn có thể hoạt động vì có thể tạo hai nhóm dữ liệu độc lập.

### 8.3. Không dùng downgrade như rollback mặc định

Downgrade major version thường bị giới hạn hoặc không được hỗ trợ trực tiếp. Cách quay lui an toàn thường là:

- Restore backup trước upgrade bằng đúng phiên bản cũ.
- Phục hồi binary log/GTID cần thiết để đưa dữ liệu tới điểm được chọn.
- Hoặc dựng lại replica từ một source vẫn còn ở phiên bản cũ trong giai đoạn chuyển tiếp.

Nếu đã có transaction mới trên phiên bản đích, cần xác định cách bảo toàn chúng trước khi quay lại. Không đổi endpoint về source cũ rồi bỏ qua dữ liệu đã ghi trên node mới.

## 9. Xác minh sau khi nâng cấp

Sau mỗi node và sau toàn bộ topology, kiểm tra theo các nhóm sau:

| Nhóm | Nội dung xác minh |
|---|---|
| Phiên bản | `SELECT VERSION()`, edition, plugin và package đúng mục tiêu |
| Khởi động | Error log sạch, không có upgrade failure, crash loop hoặc cảnh báo nghiêm trọng |
| Dữ liệu | Schema, bảng, index, constraint, row count và truy vấn nghiệp vụ quan trọng |
| Replication | Receiver/applier chạy, không có lỗi, GTID/position tiến triển và lag trong ngưỡng |
| Group Replication | Thành viên `ONLINE`, đúng primary, quorum và không có node bị expel |
| Bảo mật | User/role, authentication plugin, TLS, keyring và audit hoạt động |
| Ứng dụng | Kết nối, đọc/ghi, transaction, job nền, event và báo cáo |
| Hiệu năng | Query latency, CPU, I/O, buffer pool, connection, lock wait và replication lag |
| Backup | Backup mới thành công và restore test theo phiên bản mới |

Một số lệnh kiểm tra tổng quát:

```sql
SELECT VERSION();
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'server_id';
```

Với asynchronous replication, tiếp tục dùng `SHOW REPLICA STATUS\G` hoặc tên lệnh phù hợp với phiên bản. Với Group Replication, kiểm tra `performance_schema.replication_group_members` và log của plugin. Hãy so sánh trạng thái trước/sau thay đổi thay vì chỉ xem một giá trị riêng lẻ.

## 10. Ví dụ kế hoạch nâng cấp source/replica

Giả sử có một source và hai replica, tất cả đang ở phiên bản A. Mục tiêu là nâng cấp lên phiên bản B và upgrade path chính thức cho phép A làm source cho B trong thời gian chuyển tiếp.

| Giai đoạn | Source | Replica 1 | Replica 2 | Điều kiện đi tiếp |
|---|---|---|---|---|
| Ban đầu | A | A | A | Replication khỏe, backup hợp lệ |
| Bước 1 | A | B | A | Replica 1 bắt kịp, không có lỗi |
| Bước 2 | A | B | B | Cả hai replica `Yes/Yes`, lag trong ngưỡng |
| Bước 3 | B | B | B | Source khởi động ổn định, replication tiếp tục |
| Hoàn tất | B | B | B | Dữ liệu, ứng dụng, bảo mật và backup được xác minh |

Trong ví dụ này, source vẫn giữ phiên bản A cho tới khi cả hai replica đã nâng cấp. Nếu replica thứ hai thất bại, có thể dừng quy trình và xử lý node đó trong khi source vẫn ở phiên bản A, miễn là replica thứ nhất và source đáp ứng yêu cầu availability/RPO. Không nâng cấp source chỉ vì một replica đã thành công.

## 11. Checklist thứ tự nâng cấp

- [ ] Đã ghi nhận phiên bản, vai trò và topology của tất cả node.
- [ ] Đã kiểm tra upgrade path và compatibility matrix cho đúng cặp phiên bản.
- [ ] Đã xác nhận source/replica hoặc Group Replication đang khỏe mạnh.
- [ ] Đã có backup và đã thử restore bằng phiên bản tương ứng.
- [ ] Đã kiểm tra plugin, TLS, keyring, authentication và cấu hình hệ điều hành.
- [ ] Đã xác định thứ tự replica lá → replica trung gian → source gốc nếu replication dây chuyền.
- [ ] Đã xác định secondary trước, primary sau nếu Group Replication single-primary hỗ trợ rolling upgrade.
- [ ] Đã tính quorum và giới hạn số node được phép offline cùng lúc.
- [ ] Đã chuẩn bị kế hoạch chuyển traffic đọc/ghi và dừng ghi khi nâng cấp source/primary.
- [ ] Đã bảo đảm retention binlog đủ cho node offline nâng cấp và bắt kịp.
- [ ] Đã đặt điều kiện dừng: node không khởi động, replication lỗi, mất quorum hoặc lag vượt ngưỡng.
- [ ] Đã có phương án restore/rebuild node và rollback toàn topology.
- [ ] Đã xác minh từng node trước khi nâng cấp node kế tiếp.
- [ ] Đã chạy smoke test, kiểm tra hiệu năng và tạo backup mới sau nâng cấp.

## 12. Tự kiểm tra

1. Vì sao trong asynchronous replication thường nâng cấp replica trước source?
2. Với topology A → B → C, vì sao nên nâng cấp C trước B rồi mới đến A?
3. Điều gì có thể xảy ra nếu source đã nâng cấp lên phiên bản mới nhưng replica vẫn ở phiên bản cũ?
4. Trong InnoDB Cluster single-primary, vì sao cần nâng cấp secondary từng node rồi mới nâng cấp primary?
5. Vì sao phải chờ một thành viên trở lại `ONLINE` trước khi dừng thành viên tiếp theo?
6. Quorum bị ảnh hưởng thế nào khi hai node trong cụm ba thành viên cùng offline?
7. Khi nào cần chuyển primary có kế hoạch trước khi nâng cấp node primary cũ?
8. Vì sao không thể mặc định downgrade bằng cách cài lại binary cũ?
9. Những chỉ số nào chứng minh một replica đã bắt kịp sau khi nâng cấp?
10. Hãy lập thứ tự nâng cấp cho topology một source, hai replica và một Router; nêu điều kiện xác minh sau mỗi bước.

Thứ tự nâng cấp phải bắt nguồn từ hướng replication, quy tắc tương thích phiên bản và cơ chế quorum của topology. Nâng cấp từng node, xác minh trạng thái thực tế rồi mới tiếp tục sẽ giúp phát hiện lỗi sớm, giữ được khả năng phục hồi và giảm nguy cơ biến một đợt bảo trì thành sự cố dữ liệu diện rộng.
