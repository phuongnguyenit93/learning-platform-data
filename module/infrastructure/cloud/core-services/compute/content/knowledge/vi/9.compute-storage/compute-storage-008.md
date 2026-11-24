# Snapshot nhất quán và phối hợp với ứng dụng đang ghi dữ liệu

## Mục tiêu bài học

Snapshot giúp ghi lại trạng thái của một volume hoặc nhóm volume tại một thời điểm để khôi phục, nhân bản môi trường hoặc tạo bản sao phục vụ kiểm thử. Tuy nhiên, một snapshot được tạo khi ứng dụng đang ghi dữ liệu chưa chắc đại diện cho trạng thái nghiệp vụ hợp lệ. Các thao tác ghi có thể đang nằm trong bộ nhớ đệm, một giao dịch có thể mới chỉ ghi được một phần, hoặc dữ liệu liên quan có thể nằm trên nhiều đĩa.

Sau bài học này, bạn có thể:

- Phân biệt snapshot crash-consistent và application-consistent.
- Giải thích vì sao filesystem, database và ứng dụng cần phối hợp trước khi chụp snapshot.
- Lập trình tự quiesce, flush, freeze, snapshot và resume phù hợp.
- Chọn cách sao lưu cho database, máy ảo nhiều volume và workload phân tán.
- Kiểm tra khả năng khôi phục, RPO/RTO và bảo vệ snapshot trong môi trường đám mây.

## 1. Snapshot là gì và vì sao tính nhất quán quan trọng?

Snapshot là bản ghi trạng thái của một volume hoặc tập tài nguyên lưu trữ tại một thời điểm logic. Nền tảng có thể triển khai snapshot bằng copy-on-write, redirect-on-write hoặc cơ chế nội bộ khác. Người dùng thường nhìn thấy một điểm khôi phục có thể dùng để tạo volume mới.

Snapshot hữu ích khi:

- Khôi phục volume sau lỗi hệ thống hoặc thao tác nhầm.
- Tạo bản sao dữ liệu để kiểm thử, phân tích hoặc phát triển.
- Tạo ảnh lưu trữ trước khi nâng cấp hệ điều hành hay ứng dụng.
- Làm nguồn cho quy trình backup, nhân bản hoặc phục hồi thảm họa.

Điểm cần quan tâm là snapshot phản ánh trạng thái lưu trữ tại thời điểm chụp. Nếu ứng dụng đang ghi dữ liệu, snapshot có thể chứa một số block đã được ghi và một số block chưa được ghi. Một file có thể đã cập nhật nhưng metadata hoặc file liên quan chưa cập nhật; database có thể có page mới nhưng log giao dịch chưa được bảo toàn đầy đủ.

Vì vậy, **snapshot thành công ở cấp hạ tầng không tự chứng minh dữ liệu bên trong ứng dụng nhất quán**. Cần xác định mức nhất quán mà ứng dụng và quy trình khôi phục yêu cầu.

## 2. Crash-consistent và application-consistent

Hai khái niệm thường dùng để mô tả chất lượng snapshot là crash-consistent và application-consistent.

### 2.1. Crash-consistent snapshot

Crash-consistent snapshot tương tự trạng thái của máy ngay sau khi mất điện đột ngột. Nền tảng ghi lại trạng thái block tại một thời điểm; những dữ liệu đã được ghi bền vững xuống storage trước thời điểm đó thường được giữ lại, còn dữ liệu chỉ nằm trong bộ nhớ đệm có thể chưa xuất hiện.

Hệ điều hành và filesystem hiện đại thường có journal hoặc cơ chế phục hồi metadata. Sau khi khôi phục volume, filesystem có thể replay journal để trở về trạng thái có thể mount. Tuy nhiên, điều này không bảo đảm mọi ứng dụng đã hoàn tất giao dịch hoặc nhiều file liên quan phản ánh cùng một phiên bản nghiệp vụ.

Crash-consistent thường phù hợp khi:

- Ứng dụng được thiết kế để phục hồi sau crash.
- Có transaction log hoặc cơ chế journal cho phép khôi phục.
- Có thể chấp nhận việc ứng dụng phải recovery khi khởi động.
- Snapshot chỉ là một phần của chiến lược backup và đã có quy trình kiểm tra restore.

### 2.2. Application-consistent snapshot

Application-consistent snapshot được tạo sau khi ứng dụng hoặc hệ điều hành phối hợp đưa dữ liệu về trạng thái có thể khôi phục theo quy tắc của ứng dụng. Tùy workload, quy trình có thể bao gồm chặn ghi mới, đợi giao dịch đang chạy kết thúc, flush dữ liệu, tạo checkpoint, giữ transaction log cần thiết và tạm dừng ghi trong lúc chụp snapshot.

Ví dụ:

- Database hoàn tất hoặc kiểm soát giao dịch đang chạy, tạo checkpoint và bảo toàn WAL/binlog cần cho phục hồi.
- Windows workload có thể dùng Volume Shadow Copy Service (VSS) với writer tương thích để phối hợp ứng dụng và filesystem.
- Linux workload có thể dùng script/agent của ứng dụng, flush dữ liệu và trong một khoảng ngắn freeze filesystem nếu quy trình của nền tảng yêu cầu.

Application-consistent thường giúp rút ngắn hoặc tránh bước recovery bất ngờ và bảo toàn quan hệ giữa các file theo yêu cầu ứng dụng. Tuy nhiên, nó chỉ đáng tin khi writer, agent hoặc script thực sự hỗ trợ ứng dụng đó và quy trình đã được kiểm thử.

### 2.3. So sánh

| Tiêu chí | Crash-consistent | Application-consistent |
|---|---|---|
| Trạng thái tương đương | Máy mất điện tại một thời điểm | Ứng dụng được phối hợp đưa về điểm có thể khôi phục |
| Phối hợp ứng dụng | Không nhất thiết | Có |
| Giao dịch đang chạy | Có thể cần recovery khi mở lại | Được xử lý theo quy trình của ứng dụng |
| Thời gian chuẩn bị | Thường ngắn | Có thể cần drain, checkpoint hoặc flush |
| Mức bảo đảm | Chủ yếu ở cấp block/filesystem | Theo khả năng của ứng dụng, writer và quy trình |
| Phù hợp | Workload có khả năng crash recovery | Database và workload cần tính nhất quán cao |

Một snapshot application-consistent không tự động bảo đảm tính nhất quán phân tán giữa nhiều máy hoặc nhiều dịch vụ. Phạm vi nhất quán phải được xác định rõ: một filesystem, nhiều volume trên một VM, một database cluster hay toàn bộ hệ thống nghiệp vụ.

## 3. Các lớp nhất quán cần xem xét

Từ tầng ứng dụng xuống storage có nhiều lớp trạng thái. Chỉ xử lý một lớp có thể chưa đủ.

1. **Nhất quán nghiệp vụ:** một đơn hàng, giao dịch hoặc quy trình có các bước liên quan đã hoàn tất hoặc được ghi nhận theo quy tắc nghiệp vụ.
2. **Nhất quán giao dịch:** database không bị chụp ở trạng thái giữa một transaction chưa được commit hoặc rollback.
3. **Nhất quán filesystem:** dữ liệu file và metadata được ghi theo cách filesystem có thể phục hồi.
4. **Nhất quán block storage:** các block được ghi lại tại một điểm thời gian xác định theo bảo đảm của nền tảng.
5. **Nhất quán giữa nhiều volume:** các volume liên quan được chụp tại cùng một điểm nhất quán hoặc theo cơ chế nhóm snapshot mà nền tảng hỗ trợ.
6. **Nhất quán giữa nhiều máy/dịch vụ:** các node hoặc hệ thống phụ thuộc phối hợp để tạo một điểm phục hồi tương thích.

~~~mermaid
flowchart TD
    A["Nghiệp vụ: đơn hàng / giao dịch"] --> B["Ứng dụng: request và buffer"]
    B --> C["Database: transaction và log"]
    C --> D["Filesystem: file và metadata"]
    D --> E["Block storage: volume"]
    E --> F["Snapshot"]
    G["Phối hợp ở từng lớp"] -.-> A
    G -.-> B
    G -.-> C
    G -.-> D
    G -.-> E
~~~

Ví dụ, database có thể lưu data file trên volume A và WAL trên volume B. Nếu chụp hai volume ở hai thời điểm không tương thích, trạng thái data và log có thể không khớp. Nếu nền tảng hỗ trợ multi-volume snapshot group, hãy xác minh phạm vi atomicity và giới hạn của nhóm đó. Nếu không, cần dùng cơ chế backup của database hoặc điều phối ghi để tạo một điểm phục hồi hợp lệ.

## 4. Quy trình phối hợp trước khi tạo snapshot

Một quy trình tổng quát cho workload ghi dữ liệu có thể chia thành các bước:

1. **Xác định phạm vi:** liệt kê VM, volume, database, file, log và dịch vụ phụ thuộc cần nằm trong cùng điểm khôi phục.
2. **Chuẩn bị:** kiểm tra dung lượng, trạng thái volume, snapshot cũ, quyền truy cập và thời gian bảo trì.
3. **Quiesce ứng dụng:** tạm ngừng nhận ghi mới hoặc chuyển ứng dụng sang chế độ bảo trì; đợi request và transaction đang chạy hoàn tất.
4. **Flush dữ liệu:** yêu cầu ứng dụng, database và hệ điều hành đẩy dữ liệu cần thiết xuống storage.
5. **Checkpoint/backup mode:** sử dụng API hoặc công cụ backup được database hỗ trợ để tạo điểm phục hồi và bảo toàn transaction log.
6. **Freeze filesystem khi phù hợp:** nếu quy trình yêu cầu, tạm đóng băng filesystem trong khoảng ngắn để tránh thay đổi file trong lúc snapshot.
7. **Tạo snapshot:** gọi API snapshot hoặc snapshot group và xác nhận nền tảng đã ghi nhận điểm snapshot.
8. **Thaw và resume:** luôn giải phóng filesystem, bật lại ghi và đưa ứng dụng về trạng thái phục vụ.
9. **Xác minh:** kiểm tra snapshot hoàn tất, volume nguồn hoạt động, log backup được lưu và ứng dụng tiếp tục nhận traffic.
10. **Kiểm thử restore:** định kỳ khôi phục vào môi trường riêng, chạy kiểm tra filesystem, database và nghiệp vụ.

~~~mermaid
flowchart TD
    A["Lập phạm vi và kiểm tra điều kiện"] --> B["Quiesce: chặn ghi mới, drain request"]
    B --> C["Commit/flush/checkpoint"]
    C --> D["Freeze filesystem nếu cần"]
    D --> E["Tạo snapshot hoặc snapshot group"]
    E --> F["Xác nhận snapshot đã được tạo"]
    F --> G["Thaw filesystem"]
    G --> H["Resume ứng dụng và traffic"]
    H --> I["Kiểm tra và ghi nhận kết quả"]
    I --> J["Restore test theo lịch"]
~~~

Thời gian quiesce cần ngắn và có giới hạn. Nếu API snapshot mất nhiều thời gian để hoàn tất, hãy xác định liệu nền tảng chỉ cần ghi nhận điểm snapshot ban đầu hay cần giữ filesystem đóng băng cho đến khi toàn bộ dữ liệu được sao chép. Với nhiều dịch vụ cloud, snapshot có thể tiếp tục xử lý nền sau khi điểm thời gian đã được xác lập; phải theo tài liệu của dịch vụ cụ thể để biết lúc nào có thể thaw an toàn.

Không để ứng dụng hoặc filesystem bị freeze vô thời hạn. Cần có timeout, xử lý lỗi và nhánh cleanup luôn chạy để thaw/resume ngay cả khi lệnh snapshot thất bại.

## 5. Quiesce, flush và freeze khác nhau thế nào?

Ba thao tác này có liên quan nhưng không thay thế cho nhau.

| Thao tác | Mục đích | Ví dụ |
|---|---|---|
| Quiesce | Ngăn phát sinh thay đổi mới và đưa ứng dụng về điểm an toàn | Chuyển API sang read-only, drain request, pause consumer |
| Flush | Đẩy dữ liệu đang nằm trong buffer xuống lớp lưu trữ tiếp theo | Ứng dụng gọi fsync, database flush/checkpoint |
| Freeze | Tạm ngăn thay đổi filesystem để snapshot có trạng thái ổn định | Linux filesystem freeze hoặc Windows VSS freeze |

Quiesce ở tầng ứng dụng có ý nghĩa nghiệp vụ. Flush giúp dữ liệu đã được ứng dụng phát ra được chuyển xuống storage. Freeze giúp filesystem không thay đổi trong một khoảng ngắn. Freeze filesystem không tự commit transaction trong database và cũng không biết một quy trình nghiệp vụ đã hoàn tất hay chưa.

Một quy trình tốt chọn đúng thao tác cho từng thành phần. Không nên chỉ chạy lệnh freeze rồi cho rằng database và ứng dụng đã nhất quán.

### Ví dụ Linux: freeze và thaw filesystem

Trên Linux, fsfreeze có thể tạm dừng thay đổi đối với filesystem được hỗ trợ. Ví dụ minh họa sau giả định volume dữ liệu đã được mount tại /data và người vận hành có quyền phù hợp:

~~~bash
# Đẩy dữ liệu đã ghi qua các buffer của hệ thống
sync

# Freeze filesystem trong khoảng thời gian ngắn
sudo fsfreeze --freeze /data

# Tại đây, automation gọi API snapshot của nhà cung cấp.
# Chỉ tiếp tục khi đã xác nhận nền tảng ghi nhận điểm snapshot.

# Mở lại filesystem
sudo fsfreeze --unfreeze /data
~~~

Đây là trình tự minh họa, không phải script backup hoàn chỉnh. Trong automation thật, phải dùng cơ chế try/finally hoặc trap tương đương để luôn thaw nếu API lỗi, timeout hoặc tiến trình bị ngắt. Cần xác định filesystem và mount point chính xác; không freeze nhầm root filesystem hoặc filesystem chứa thành phần cần thiết để thực hiện lệnh khôi phục.

Nếu dùng database có quy trình backup online riêng, hãy theo hướng dẫn của database. Việc freeze filesystem không thay thế API backup, checkpoint hay transaction log của database.

## 6. Phối hợp snapshot với database

Database quản lý buffer pool, transaction log, checkpoint, transaction đang mở và nhiều file dữ liệu có quan hệ với nhau. Snapshot ở cấp volume chỉ nhìn thấy block storage, không hiểu ý nghĩa của transaction.

### 6.1. Database có khả năng crash recovery

Nhiều database ghi transaction log trước khi ghi page dữ liệu (write-ahead logging). Khi khởi động sau crash, database có thể replay log để phục hồi giao dịch đã commit và loại bỏ hoặc rollback giao dịch chưa hoàn tất.

Nếu snapshot bảo toàn đầy đủ các file cần thiết và có quan hệ thời gian hợp lệ, database có thể dùng crash recovery. Nhưng phải xác minh database hỗ trợ phương thức backup đó, transaction log có nằm trong snapshot hoặc được lưu riêng hay không, và snapshot có nhất quán trên các volume liên quan hay không.

### 6.2. Native online backup

Với database production, ưu tiên cơ chế backup được database hỗ trợ, ví dụ:

- Công cụ backup online hoặc physical backup của database.
- API tạo snapshot/backup do dịch vụ database được quản lý cung cấp.
- Checkpoint và cơ chế lưu trữ transaction log để phục hồi tới thời điểm (point-in-time recovery).
- Công cụ backup có khả năng phối hợp với storage snapshot và tạo manifest chỉ rõ log cần thiết.

Với PostgreSQL, quy trình physical backup có thể sử dụng các chức năng backup được hỗ trợ như pg_backup_start và pg_backup_stop trên các phiên bản hiện hành, đồng thời lưu WAL cần thiết theo hướng dẫn phiên bản. Với MySQL, có thể dùng công cụ backup nhất quán phù hợp với engine và phiên bản, đồng thời bảo toàn binary log nếu cần point-in-time recovery. Cú pháp và điều kiện cụ thể phải theo đúng phiên bản database.

### 6.3. Vì sao chỉ snapshot data volume là chưa đủ?

Giả sử database có:

- Data file trên /db-data.
- WAL trên /db-wal.
- File cấu hình và chứng thư trên /etc/db.

Nếu chỉ snapshot /db-data, bản khôi phục có thể thiếu WAL hoặc cấu hình cần thiết. Nếu snapshot từng volume ở những thời điểm khác nhau, chúng có thể không đại diện cho cùng một trạng thái database.

Cách xử lý:

1. Xác định toàn bộ volume và file thuộc phạm vi backup.
2. Ưu tiên native backup hoặc công cụ hỗ trợ snapshot coordination.
3. Nếu dùng snapshot group, xác nhận các volume được chụp tại cùng điểm nhất quán.
4. Bảo toàn transaction log cần thiết ở nơi độc lập và lưu manifest/metadata backup.
5. Khôi phục thử toàn bộ tập volume cùng log rồi chạy recovery theo tài liệu database.

Không nên giả định snapshot nhiều volume luôn có tính atomic hoặc tự tạo được backup database hợp lệ. Điều đó phụ thuộc dịch vụ storage, API snapshot group, guest agent và cách database ghi dữ liệu.

## 7. Workload trên Windows và máy ảo

Trên Windows, Volume Shadow Copy Service (VSS) cung cấp cơ chế phối hợp giữa requestor, writer và provider để tạo shadow copy. VSS writer của ứng dụng có thể chuẩn bị dữ liệu, flush hoặc tạm dừng I/O theo giao thức VSS. Sau khi snapshot được tạo, writer hoàn tất và ứng dụng tiếp tục hoạt động.

Một quy trình snapshot VM có hỗ trợ VSS thường gồm:

- Agent hoặc dịch vụ backup gửi yêu cầu VSS.
- VSS writer tương thích chuẩn bị các thành phần ứng dụng.
- Provider tạo shadow copy hoặc phối hợp với snapshot storage.
- Writer được thông báo hoàn tất và workload tiếp tục ghi.

Cần xác nhận VSS writer của ứng dụng đang ở trạng thái ổn định và quy trình backup hỗ trợ đúng workload. Snapshot chỉ dùng crash-consistency nếu không có writer tương thích hoặc quá trình phối hợp không thành công.

Trên Linux, guest agent hoặc script hook có thể gọi lệnh flush, quiesce database và freeze filesystem. Cần kiểm tra timeout, quyền thực thi và khả năng thaw trong mọi nhánh lỗi.

Trong môi trường cloud, một số dịch vụ snapshot có guest-agent integration hoặc tùy chọn application-consistent. Tên tính năng và mức hỗ trợ khác nhau giữa nhà cung cấp, hệ điều hành và loại volume. Hãy kiểm tra trạng thái hoàn tất của agent/writer; nếu bước phối hợp thất bại, cần phân loại snapshot theo mức nhất quán thực tế thay vì gắn nhãn application-consistent.

## 8. Snapshot nhiều volume và workload phân tán

Một VM có thể dùng nhiều volume, nhưng một hệ thống có thể gồm nhiều VM hoặc nhiều dịch vụ. Hai trường hợp này cần cách phối hợp khác nhau.

### 8.1. Nhiều volume trên cùng VM

Nếu dữ liệu được chia trên boot disk, data disk và log disk, cần xác định volume nào phải được chụp cùng nhau. Snapshot group hoặc multi-volume snapshot có thể giúp tạo điểm snapshot đồng bộ trong phạm vi mà nền tảng hỗ trợ.

Trước khi dùng, kiểm tra:

- API có tạo snapshot đồng thời cho tất cả volume được chỉ định không.
- Có giới hạn số lượng hoặc loại volume không.
- Có hỗ trợ encryption key, cross-zone hoặc cross-region không.
- Snapshot group đảm bảo điểm nhất quán ở cấp block hay có tích hợp guest/application quiesce.
- Volume nào bị bỏ qua hoặc không được hỗ trợ.

Snapshot đồng thời nhiều volume có thể giải quyết vấn đề thời điểm block giữa các đĩa, nhưng vẫn cần phối hợp ứng dụng để đảm bảo transaction và dữ liệu nghiệp vụ.

### 8.2. Nhiều VM hoặc database cluster

Snapshot từng VM không tự tạo ra một điểm phục hồi chung cho cả cluster. Một node có thể đã nhận giao dịch mới trong khi node khác vẫn ở trạng thái cũ. Với hệ thống phân tán, hãy cân nhắc:

- Cơ chế backup/restore native của database cluster.
- Quorum, replication log và vị trí commit được xác nhận.
- Tạm dừng ghi ở tầng ứng dụng hoặc điều phối leader/follower theo tài liệu sản phẩm.
- Tạo backup theo từng shard hoặc node với manifest chung và quy tắc phục hồi.
- Lưu checkpoint hoặc watermark để xác định dữ liệu đã được xử lý đến đâu.

Ví dụ, hệ thống xử lý đơn hàng ghi vào database, phát sự kiện sang message broker và cập nhật object storage. Snapshot riêng database và broker ở hai thời điểm khác nhau có thể làm lệch trạng thái giữa đơn hàng và sự kiện. Cần dùng cơ chế transactional outbox, checkpoint hoặc quy trình backup/restore phối hợp để xử lý phần chênh lệch khi phục hồi.

## 9. Ví dụ quy trình backup cho một ứng dụng trên VM

Giả sử một VM Linux chạy dịch vụ quản lý đơn hàng. PostgreSQL lưu data và WAL trên hai volume riêng. Mục tiêu là tạo snapshot phục vụ phục hồi toàn bộ VM.

Một quy trình có thể thiết kế như sau:

1. Load balancer chuyển ứng dụng sang chế độ bảo trì hoặc ngừng gửi request ghi mới.
2. Ứng dụng đợi request đang xử lý hoàn tất; consumer của message queue tạm dừng và ghi nhận offset/checkpoint.
3. Database thực hiện quy trình backup online được hỗ trợ, bảo đảm checkpoint và WAL cần thiết được lưu.
4. Guest agent gọi flush; nếu giải pháp snapshot yêu cầu, freeze các filesystem liên quan trong thời gian ngắn.
5. Hệ thống tạo snapshot group cho volume data và WAL theo khả năng nền tảng.
6. Agent thaw filesystem ngay sau khi nền tảng xác nhận điểm snapshot đã được ghi nhận.
7. Ứng dụng và consumer tiếp tục hoạt động; load balancer gửi traffic trở lại.
8. Backup pipeline lưu manifest gồm VM ID, volume ID, snapshot ID, thời điểm, database version, WAL range, cấu hình mã hóa và trạng thái writer.
9. Theo lịch, nhóm vận hành tạo VM thử nghiệm, gắn các volume đã phục hồi, chạy database recovery, kiểm tra số lượng bản ghi và thực hiện smoke test API.

Điều quan trọng là phải định nghĩa rõ thời điểm resume. Không giữ ứng dụng ở trạng thái quiesce trong toàn bộ thời gian sao chép snapshot nếu dịch vụ chỉ cần giữ trạng thái đóng băng đến lúc snapshot point-in-time được xác lập. Thời điểm này phụ thuộc API và nhà cung cấp.

## 10. Khôi phục và kiểm chứng snapshot

Snapshot chỉ có giá trị khi có thể khôi phục thành công. Trạng thái completed trong console/API thường cho biết tác vụ snapshot hoàn tất ở lớp hạ tầng; nó không thay thế kiểm tra tính hợp lệ của ứng dụng.

Quy trình restore test:

1. Chọn snapshot và xác minh metadata, nguồn, thời điểm, encryption key cùng retention.
2. Tạo volume mới từ snapshot trong môi trường cô lập.
3. Gắn volume vào VM phục hồi hoặc tạo máy từ image phù hợp.
4. Mount filesystem và kiểm tra journal/recovery log.
5. Khởi động database theo đúng quy trình phục hồi.
6. Replay WAL/binlog nếu backup yêu cầu.
7. Kiểm tra tính toàn vẹn dữ liệu, số lượng bản ghi, quan hệ và checkpoint.
8. Khởi động ứng dụng với cấu hình test, không kết nối nhầm production.
9. Chạy smoke test và kiểm tra luồng nghiệp vụ quan trọng.
10. Ghi lại thời gian phục hồi, lỗi phát hiện, dữ liệu mất và kết quả đối chiếu.

Không khôi phục snapshot production trực tiếp đè lên volume đang chạy khi chưa có kế hoạch cutover. Hãy khôi phục vào volume hoặc môi trường riêng, xác minh xong rồi mới chuyển traffic hoặc thay thế tài nguyên.

## 11. RPO, RTO và lịch snapshot

Tần suất snapshot và cách phối hợp cần dựa trên mục tiêu khôi phục.

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa có thể mất, tính theo thời gian. RPO 15 phút nghĩa là hệ thống hướng tới khả năng khôi phục về một điểm không cũ hơn khoảng 15 phút trong điều kiện giải pháp hoạt động đúng.
- **RTO (Recovery Time Objective):** khoảng thời gian mục tiêu để đưa dịch vụ trở lại hoạt động sau sự cố.

Snapshot mỗi 24 giờ có thể không đáp ứng RPO 15 phút. Khi đó cần kết hợp snapshot định kỳ với transaction log shipping, continuous backup hoặc replication phù hợp. RTO còn phụ thuộc thời gian tạo volume, khởi động VM, database recovery, kiểm tra ứng dụng và chuyển traffic.

| Nhu cầu | Cách tiếp cận có thể cân nhắc |
|---|---|
| RPO vài giờ, workload ít thay đổi | Snapshot định kỳ, backup riêng cho dữ liệu quan trọng |
| RPO dưới một giờ cho database | Snapshot kết hợp lưu transaction log và point-in-time recovery |
| RPO rất thấp | Replication/continuous data protection cùng backup độc lập |
| RTO ngắn | Chuẩn bị sẵn image/template, tự động hóa restore và kiểm thử định kỳ |
| Phục hồi sau lỗi vùng | Sao chép backup/snapshot sang vùng khác và kiểm thử quy trình DR |

Snapshot thường là một thành phần trong chiến lược backup, không phải toàn bộ chiến lược. Cần bảo vệ bản backup khỏi lỗi tài khoản, lỗi vùng, xóa nhầm và ransomware. Có thể dùng retention lock/immutability, tài khoản backup riêng, quyền tách biệt và bản sao ở vùng hoặc tài khoản khác.

## 12. Bảo mật và vận hành snapshot

Snapshot có thể chứa toàn bộ dữ liệu của volume, bao gồm file cấu hình, log, dữ liệu cá nhân và thông tin xác thực. Vì vậy, cần bảo vệ snapshot tương tự dữ liệu production.

Các biện pháp cần xem xét:

- Mã hóa volume và snapshot bằng khóa được quản lý theo chính sách tổ chức.
- Giới hạn quyền tạo, đọc, chia sẻ, sao chép và xóa snapshot.
- Kiểm soát việc chia sẻ snapshot giữa tài khoản, project hoặc subscription.
- Dùng retention policy và cơ chế chống xóa cho bản backup quan trọng.
- Ghi audit cho thao tác snapshot, copy, restore và delete.
- Đặt tag/metadata để nhận diện owner, workload, môi trường, nguồn và thời hạn lưu giữ.
- Theo dõi snapshot lỗi, snapshot quá cũ hoặc volume quan trọng chưa được backup.
- Tránh để secret trong snapshot test được chia sẻ cho nhóm không có quyền production.
- Có quy trình xóa an toàn khi hết hạn lưu giữ và kiểm tra ảnh hưởng tới snapshot phụ thuộc.

Một snapshot được mã hóa bằng customer-managed key có thể không khôi phục được nếu khóa bị vô hiệu hóa hoặc xóa. Quy trình DR cần bảo vệ cả quyền sử dụng khóa, chính sách key rotation và khả năng truy cập khóa trong tài khoản/vùng phục hồi.

## 13. Lỗi thường gặp và cách tránh

**Chụp snapshot khi ứng dụng đang ghi mà không phối hợp:** snapshot có thể chỉ crash-consistent và cần recovery. Xác định mức nhất quán yêu cầu, quiesce ứng dụng hoặc dùng backup API phù hợp.

**Chỉ flush filesystem mà bỏ qua database:** dữ liệu trong buffer database hoặc transaction đang chạy vẫn có thể chưa ở trạng thái ứng dụng hợp lệ. Dùng native database backup/checkpoint và bảo toàn log.

**Snapshot từng volume ở các thời điểm khác nhau:** data và log có thể không khớp. Dùng snapshot group được hỗ trợ hoặc quy trình backup phối hợp.

**Giữ filesystem freeze quá lâu:** ứng dụng có thể bị block I/O, timeout và gián đoạn. Chỉ freeze trong khoảng cần thiết để xác lập điểm snapshot, có timeout và luôn thaw trong cleanup.

**Cho rằng snapshot nhiều volume đồng nghĩa với application-consistent:** snapshot group chỉ giải quyết mức đồng bộ mà nền tảng cam kết. Vẫn cần kiểm tra database và ứng dụng.

**Cho rằng snapshot một VM đủ để phục hồi cluster:** các node và dịch vụ phụ thuộc có thể ở các thời điểm khác nhau. Dùng quy trình backup/restore có nhận thức về cluster và checkpoint.

**Không lưu transaction log:** snapshot có thể không phục hồi được tới thời điểm mong muốn. Bảo toàn WAL/binlog hoặc log tương đương và ghi manifest.

**Không thử restore:** backup có thể thiếu khóa mã hóa, file cấu hình, quyền truy cập hoặc log cần thiết. Thực hiện restore test định kỳ và ghi nhận RTO thực tế.

**Dùng snapshot làm bản sao duy nhất:** snapshot cùng tài khoản hoặc vùng có thể bị xóa hoặc ảnh hưởng bởi cùng sự cố. Duy trì bản backup độc lập và bản sao ở phạm vi lỗi khác.

## 14. Checklist trước và sau khi tạo snapshot

- [ ] Đã xác định workload, volume, database và dịch vụ phụ thuộc trong phạm vi snapshot.
- [ ] Đã xác định snapshot cần crash-consistent hay application-consistent.
- [ ] Đã kiểm tra cơ chế quiesce/flush/checkpoint phù hợp với ứng dụng.
- [ ] Đã xác minh tất cả volume liên quan và khả năng snapshot group.
- [ ] Đã kiểm tra agent/writer và trạng thái trước khi bắt đầu.
- [ ] Có timeout và cleanup để luôn thaw/resume khi thao tác lỗi.
- [ ] Snapshot API đã xác nhận điểm snapshot được ghi nhận trước khi resume.
- [ ] Đã lưu snapshot ID, volume ID, thời điểm, log range và metadata backup.
- [ ] Đã xác nhận ứng dụng tiếp tục hoạt động sau snapshot.
- [ ] Snapshot được mã hóa, phân quyền và áp dụng retention phù hợp.
- [ ] Có bản sao độc lập theo yêu cầu khôi phục thảm họa.
- [ ] Đã kiểm thử restore ở cấp filesystem, database và nghiệp vụ.
- [ ] Đã đo RPO/RTO thực tế và cập nhật runbook.

Snapshot nhất quán đòi hỏi hiểu trạng thái ghi dữ liệu từ ứng dụng, database, filesystem đến storage. Crash-consistent mô phỏng trạng thái sau sự cố mất điện; application-consistent cần phối hợp workload để tạo điểm có thể khôi phục theo quy tắc ứng dụng. Hãy chọn đúng cơ chế quiesce, flush, checkpoint, freeze và snapshot group, luôn giải phóng workload sau khi điểm snapshot được xác lập, đồng thời kiểm thử restore để xác nhận backup thực sự dùng được.
