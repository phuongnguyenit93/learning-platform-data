# Khôi phục theo thời điểm khi công nghệ hỗ trợ

Lúc 14:05, một thao tác quản trị chạy nhầm câu lệnh xóa dữ liệu đơn hàng. Bản sao lưu gần nhất được tạo lúc 01:00 cùng ngày. Nếu chỉ khôi phục bản sao lưu đó, hệ thống sẽ mất cả những giao dịch hợp lệ diễn ra từ 01:00 đến 14:05. Nhưng nếu cơ sở dữ liệu có **bản sao lưu nền nhất quán và chuỗi nhật ký thay đổi liên tục**, đội vận hành có thể dựng một bản database ở trạng thái ngay **trước giao dịch xóa nhầm**. Đó là ý tưởng của **Point-in-Time Recovery (PITR)**.

PITR không đơn thuần là chọn một ngày trên giao diện backup. Nó là một khả năng phục hồi **có điều kiện**: công nghệ lưu trữ phải hỗ trợ phát lại thay đổi tới một điểm được xác định, chuỗi bản sao lưu và nhật ký phải đầy đủ, khóa giải mã phải còn, quy trình restore phải được thử nghiệm và trạng thái sau phục hồi phải được kiểm chứng. Nhiều hệ thống chỉ hỗ trợ khôi phục theo snapshot hoặc một phạm vi PITR hạn chế, không thể giả định mọi kho dữ liệu có cùng cơ chế.

Bài này thuộc chương **Sao lưu và khôi phục** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học Java sẽ kết nối kiến thức về transaction, WAL, độ bền, mô hình dữ liệu, kết nối ứng dụng, consistency và vận hành để thiết kế một kịch bản PITR an toàn, xác định **RPO/RTO**, khôi phục bản sao để kiểm tra trước khi chuyển traffic và hiểu điều gì PITR **không** thể khôi phục.

## 1. PITR là gì và khác việc restore backup thông thường thế nào?

**Khôi phục bản sao lưu thông thường** đưa dữ liệu về đúng trạng thái mà bản sao lưu đại diện, trong giới hạn bảo đảm nhất quán của loại backup đó. Nếu chỉ có snapshot lúc 01:00, dữ liệu commit sau mốc này có thể không có trong kết quả restore.

**PITR** kết hợp một trạng thái nền với **log thay đổi có thể phát lại** để phục hồi tới một mốc trong khoảng được hỗ trợ:

~~~mermaid
flowchart LR
    A[Base backup nhất quán] --> B[Phát lại log/WAL liên tục]
    B --> C{Đã tới target?}
    C -- Chưa --> B
    C -- Rồi --> D[DB ở trạng thái ứng với target]
    D --> E[Kiểm tra và chọn cách đưa vào phục vụ]
~~~

Khái niệm “mốc” tùy engine: có thể là **thời gian**, **log sequence number/LSN**, **transaction ID**, **restore point được đặt tên** hoặc một recovery position do dịch vụ quản lý cung cấp. Không phải mọi engine cho phép chọn tất cả loại mốc trên.

| Cách phục hồi | Có gì để áp dụng thay đổi sau backup? | Mức chi tiết đạt được |
| --- | --- | --- |
| Restore một bản dump/snapshot | Không có replay log | Trạng thái tại snapshot/dump thích hợp |
| Restore snapshot + archived log | Có chuỗi log hợp lệ | Đến mốc nằm trong phạm vi replay hỗ trợ |
| PITR managed service | Nhà cung cấp duy trì chuỗi backup/log | Tới thời điểm do dịch vụ cho phép |
| Chỉ dùng replica | Không nhất thiết có lịch sử đã lưu độc lập | Thường không cứu được DELETE đã replicate |
| Chỉ lưu SQL query log | Không phải transaction recovery log | Không bảo đảm tái tạo trạng thái database |

**Điểm mấu chốt:** PITR là khả năng phục hồi một *trạng thái dữ liệu có ý nghĩa giao dịch*, không phải tua ngược lịch sử ứng dụng giống chức năng Undo. Sau PITR, dữ liệu trong database có thể lùi về trước, trong khi email, thanh toán, file object và những dịch vụ khác đã nhận tác động của các giao dịch bị loại khỏi lịch sử phục hồi.

## 2. Timeline: xóa nhầm và chọn mốc phục hồi

Giả sử PostgreSQL có một base backup lúc 01:00, WAL được lưu liên tục và sự cố như sau (giờ Việt Nam, UTC+07:00):

~~~text
01:00:00  Bắt đầu bản backup nền (backup nhất quán).
01:18:00  Base backup hoàn tất, log cần thiết được lưu.
10:40:12  Đơn hàng #712 được tạo hợp lệ.
14:04:50  Đơn hàng #713 được tạo hợp lệ.
14:05:10  Giao dịch DELETE nhầm được COMMIT.
14:05:15  Phát hiện và ngăn tiếp tục thao tác sai.
14:05:30  Một số giao dịch hợp lệ khác có thể đã COMMIT.
~~~

Mục tiêu dự kiến là khôi phục **sau** những commit hợp lệ lúc 14:04:50 nhưng **trước** commit DELETE lúc 14:05:10. Không thể chọn mốc chỉ bằng cảm giác; cần xác minh thời điểm commit thực và biên transaction. Thời gian client gửi lệnh, thời gian log ứng dụng và thời gian commit trong database **không nhất thiết trùng nhau**.

~~~mermaid
flowchart LR
    B[Base backup] --> V1[Commit hợp lệ #712]
    V1 --> V2[Commit hợp lệ #713]
    V2 --> T[Mốc muốn phục hồi]
    T --> X[Commit DELETE nhầm]
    X --> V3[Commit hợp lệ sau sự cố]
~~~

PITR tới trước X cũng **loại bỏ V3**, dù V3 là giao dịch hợp lệ. Đây là đánh đổi quan trọng: phục hồi cả database về một mốc trước lỗi có thể làm mất tiến độ nghiệp vụ sau mốc đó. Đôi khi khôi phục một **bản song song** rồi chỉ **trích xuất phần dữ liệu cần cứu** an toàn hơn việc thay toàn bộ production bằng bản đã tua lùi.

## 3. RPO và RTO: hai yêu cầu phải định nghĩa riêng

**RPO — Recovery Point Objective**: mức mất dữ liệu tối đa chấp nhận được tính theo thời gian hoặc đơn vị nghiệp vụ, tùy cách tổ chức định nghĩa. **RTO — Recovery Time Objective**: thời gian tối đa chấp nhận được để dịch vụ được khôi phục sau sự cố.

Ví dụ:

| Yêu cầu | Diễn giải | Phụ thuộc chính |
| --- | --- | --- |
| RPO = 15 phút | Có thể chấp nhận mất tối đa khoảng 15 phút giao dịch trong sự cố được xét | Khoảng cách backup/log, độ trễ archive và tính đầy đủ |
| RPO gần 0 | Muốn giữ gần như mọi commit đã được xác nhận | Khả năng lưu giữ/replicate log và tình huống lỗi cụ thể |
| RTO = 60 phút | Muốn ứng dụng trở lại phục vụ trong vòng 60 phút | Restore dữ liệu, replay, kiểm tra, chuyển traffic |
| Mục tiêu PITR trước lỗi | Tránh phát lại một giao dịch sai | Xác định được commit/LSN/target phù hợp |

RPO/RTO là **mục tiêu dịch vụ**, không phải những con số suy ra từ việc có bật WAL archiving. Một hệ lưu WAL mỗi vài phút có thể mất nhiều hơn mong đợi nếu bản lưu cuối chưa chuyển tới nơi độc lập khi primary hỏng. Một bản backup vài terabyte có thể đạt RPO thấp nhưng **RTO rất dài** nếu tải dữ liệu và replay mất nhiều giờ.

Khi rollback có chủ đích về trước một giao dịch xóa nhầm, lượng giao dịch hợp lệ xảy ra **sau điểm mục tiêu** bị loại có thể lớn hơn RPO mong muốn trong kịch bản mất hạ tầng. Đừng coi “PITR thành công tới thời điểm đã chọn” là bằng chứng mọi nghiệp vụ không mất dữ liệu.

### Những câu hỏi cần ghi trước khi triển khai

1. Sự cố cần cứu là **hỏng hạ tầng**, **xóa nhầm**, **schema migration lỗi** hay **dữ liệu bị thay đổi độc hại**?
2. RPO/RTO đo từ mốc nào đến mốc nào?
3. Cần khôi phục **toàn cluster**, **một database**, **một tenant** hay **một số bản ghi**?
4. Có cơ chế lấy lại giao dịch tốt sau mốc PITR không?
5. Những hệ ngoài database nào đã nhận tác động và cần đối soát?

## 4. Điều kiện cốt lõi: base backup và chuỗi log không đứt

Với PostgreSQL physical PITR, công thức khái niệm:

~~~text
Một physical base backup có thể sử dụng
    + các WAL segment liên tục cần thiết từ backup
    + log bao phủ tới recovery target
    + metadata/timeline tương thích
    + khóa giải mã và cấu hình cần thiết
    = ứng viên có thể khôi phục theo thời điểm
~~~

**Base backup** cung cấp dữ liệu nền vật lý. **WAL (Write-Ahead Log)** ghi các thông tin cần thiết cho phục hồi thay đổi của PostgreSQL. Bắt đầu từ một base backup có thể khôi phục, PostgreSQL phát lại WAL theo quy tắc của engine; mọi đoạn WAL cần dùng phải còn và đọc được.

Nếu thiếu một WAL segment trên đường từ bản nền tới target, không được tự bỏ qua “vài phút” rồi tiếp tục như thể chuỗi phục hồi còn hợp lệ. Cần tìm bản backup nền khác hoặc nguồn WAL phù hợp, nếu tồn tại. Các bản backup incremental/differential của một công cụ còn có phụ thuộc riêng; một file backup riêng lẻ không chứng minh restore được.

**Một số điểm kỹ thuật:**

- Một base backup không nhất thiết biểu diễn snapshot đã commit tại giây bắt đầu copy; quá trình sao chép vật lý cần WAL để đạt trạng thái nhất quán. Mốc target phải nằm trong **phạm vi thực sự hỗ trợ**, không thể tùy ý chọn trước thời điểm backup có thể phục hồi.
- WAL lưu trong cùng ổ đĩa với primary **không phải bản bảo vệ độc lập** khi mất ổ/host. Cần kho lưu trữ backup/WAL tách biệt theo mô hình rủi ro.
- WAL archiving phục vụ PITR khác với streaming replication: replica có thể phát lại ngay cả giao dịch xóa nhầm; replica không tự giữ toàn bộ lịch sử cũ.
- Một bản sao lưu logic như `pg_dump` rất hữu ích cho phục hồi object, nhưng **không tương đương** physical base backup để PostgreSQL replay WAL vật lý tới thời điểm mong muốn.
- Phải xem tương thích major version, database system identifier, timeline, backup history và công cụ restore; không phát WAL của một cluster bất kỳ lên một base backup không tương ứng.

## 5. Chuỗi WAL và vị trí phục hồi: hiểu đúng phạm vi

Một luồng PITR PostgreSQL điển hình:

~~~mermaid
sequenceDiagram
    participant P as PostgreSQL primary
    participant R as WAL archiver
    participant S as Backup storage
    participant O as Recovery operator
    P->>S: Tạo physical base backup
    loop Khi WAL hoàn tất/đủ điều kiện archive
        P->>R: Archive WAL segment
        R->>S: Ghi object/segment và xác minh
    end
    O->>S: Lấy base backup + WAL cần thiết
    O->>O: Dựng instance mới, config recovery target
    O->>S: restore_command yêu cầu WAL
    S-->>O: Các WAL segment theo timeline
    O->>O: Replay tới target, kiểm tra trước khi phục vụ
~~~

Một transaction thường tạo WAL trong quá trình thực thi, và commit có record cùng các quy tắc durability tương ứng. Khi restore tới mốc, engine quyết định trạng thái giao dịch qua cơ chế recovery — **không** có nghĩa replay từng câu SQL ứng dụng theo thứ tự log text.

| Thuật ngữ | Vai trò |
| --- | --- |
| `LSN` (*Log Sequence Number*) | Vị trí trong dòng WAL, dùng quan sát/khôi phục theo hỗ trợ của engine |
| WAL segment | Đơn vị file lưu một đoạn WAL, cần bảo quản và truy xuất liên tục |
| Archive | Nơi giữ WAL đã lưu để có thể replay sau sự cố |
| Timeline | Nhánh lịch sử WAL, đặc biệt quan trọng sau promotion/PITR |
| Restore target | Mốc dừng recovery theo thời gian/LSN/XID/restore point, tùy engine |
| Recovery target inclusive | Quyết định có bao gồm transaction/record tại target theo loại target được hỗ trợ |

Một **timestamp trong log ứng dụng** không phải LSN. Nếu cần khôi phục ngay trước một commit quan trọng, nên có bằng chứng đáng tin về mốc commit/restore point/timeline chứ không chỉ mốc client bắt đầu gọi API.

## 6. PostgreSQL: chuẩn bị backup và WAL archiving trước sự cố

Không thể bật PITR **sau khi** mất dữ liệu và hy vọng PostgreSQL tự tái tạo những WAL segment chưa từng được lưu. Khả năng này phải được chuẩn bị từ trước.

Trong triển khai tự quản, các thành phần thường gồm:

1. Cấu hình WAL và archive phù hợp (ví dụ `wal_level=replica` hoặc mức có khả năng phù hợp, `archive_mode=on`, `archive_command`/`archive_library`).
2. Một physical base backup bằng cơ chế hỗ trợ, chẳng hạn `pg_basebackup` hoặc công cụ như pgBackRest/Barman.
3. Kho archive WAL **bền vững, độc lập và có kiểm soát quyền**; kiểm tra archive success và độ trễ.
4. Retention bảo đảm **không xóa base backup hoặc WAL còn cần cho khoảng PITR đã cam kết**.
5. Quy trình kiểm chứng backup và diễn tập restore định kỳ.

~~~conf
# Minh họa một phần cấu hình ở primary tự quản.
# Giá trị thật phụ thuộc phiên bản PostgreSQL và hạ tầng.
wal_level = replica
archive_mode = on
archive_timeout = '60s'

# archive_command phải do công cụ/chiến lược archive thực tế cung cấp.
# Không copy một lệnh cp ngây thơ vào production khi chưa kiểm chứng
# ghi đè, concurrency, checksum, trả mã lỗi và độ bền lưu trữ.
~~~

`archive_timeout` có thể giúp yêu cầu PostgreSQL chuyển sang WAL segment mới khi hoạt động thấp, nhưng làm tăng số segment được archive và **không** bảo đảm RPO tuyệt đối là 60 giây. Archiver thất bại hoặc storage mất kết nối có thể tạo backlog; phải giám sát thay vì coi một cấu hình là lời hứa an toàn.

### Vì sao cần công cụ backup chuyên dụng?

Các công cụ trưởng thành có thể hỗ trợ:

- Quản lý chuỗi backup/WAL, kiểm tra integrity, checksum và metadata.
- Lưu trữ ngoài host, mã hóa, object storage và chính sách retention.
- Parallel restore, incremental/differential theo khả năng công cụ/phiên bản.
- Lựa chọn target và kiểm chứng archive coverage.
- Báo cáo tiến độ, cảnh báo thiếu segment và restore rehearsal.

Không phụ thuộc vào tên công cụ để kết luận PITR được bảo đảm. Phải kiểm tra **cấu hình thực tế, phiên bản, quyền lưu trữ và kết quả diễn tập**.

## 7. Preflight khi có sự cố: bảo toàn bằng chứng và phạm vi ảnh hưởng

Ngay khi phát hiện xóa nhầm hoặc dữ liệu hỏng:

1. **Dừng tác nhân gây lỗi**: chặn job, tắt feature flag hoặc hạn chế thao tác ghi sai theo runbook; không tự động kill một database quan trọng mà chưa hiểu tác động.
2. **Ghi nhận mốc sự cố** bằng thời gian có timezone, transaction/job ID, nguồn lệnh và bằng chứng audit/DB có sẵn.
3. **Bảo toàn backup và WAL**: tạm dừng chính sách dọn dẹp có nguy cơ xóa đoạn WAL cần phục hồi; kiểm tra archive tiếp tục hoạt động khi hạ tầng còn an toàn.
4. **Đánh giá tác động**: bảng/tenant nào bị ảnh hưởng, có giao dịch tốt sau lỗi, có dịch vụ bên ngoài đã nhận event?
5. **Chọn chiến lược**: phục hồi nguyên cluster, tạo cluster song song để trích xuất dữ liệu, hay dùng cách sửa dữ liệu có thể kiểm chứng.
6. **Phân quyền ứng cứu**: người có quyền backup/restore khác quyền app runtime; mọi lệnh tác động môi trường sản xuất cần review theo quy trình.

Một tài khoản Java runtime thông thường **không nên** có khả năng ghi đè thư mục dữ liệu database hoặc xóa toàn bộ backup. Recovery là thao tác vận hành được ủy quyền, không phải endpoint `POST /restore` công khai.

## 8. Chọn target: timestamp, transaction, LSN hay restore point?

PostgreSQL hỗ trợ nhiều cách chọn mục tiêu recovery trong những phiên bản/cấu hình thích hợp. Loại mốc ảnh hưởng độ chính xác khi tránh giao dịch sai.

| Mốc | Khi có ích | Điểm cần chú ý |
| --- | --- | --- |
| `recovery_target_time` | Biết khoảng thời gian sự cố với timezone rõ | Dựa vào semantics thời gian commit/recovery, có thể có nhiều transaction gần nhau |
| `recovery_target_xid` | Biết transaction ID liên quan | XID wraparound/ngữ cảnh timeline; cần chắc target là giao dịch cần xét |
| `recovery_target_lsn` | Có vị trí WAL đáng tin | Phải thuộc timeline và phạm vi replay phù hợp |
| `recovery_target_name` | Đã tạo restore point trước đó | Phải tồn tại record `pg_create_restore_point` trong WAL đã lưu |
| `recovery_target=immediate` | Muốn dừng ngay khi trạng thái nhất quán sớm nhất đạt được | Không phải “mốc trước sự cố” tùy ý |

Ví dụ một mốc minh họa có timezone:

~~~text
2026-11-22T14:05:09+07:00
~~~

Mốc có offset tránh nhập nhằng hơn chuỗi `2026-11-22 14:05:09` khi hệ có nhiều múi giờ. Tuy nhiên, **độ chính xác 1 giây không đủ** nếu nhiều transaction tốt/xấu cùng commit trong giây đó. Cần phân tích log/audit hoặc một target có định danh đáng tin hơn.

### Recovery target inclusive

Với PostgreSQL, tham số `recovery_target_inclusive` điều khiển có bao gồm transaction tại target hay không cho các target phù hợp, chẳng hạn thời gian hoặc XID. Đặt `false` có thể giúp dừng **trước** giao dịch xác định. Nhưng phải hiểu chính xác ý nghĩa engine và target đã chọn: đây không phải một cách nói chung “lùi đúng một câu SQL” hoặc “bỏ qua duy nhất lệnh DELETE”.

Nếu một transaction xóa nhầm cùng lúc commit nhiều thay đổi tốt, PITR không tách riêng những câu trong transaction đó. Cần phục hồi một bản khác rồi trích xuất dữ liệu hoặc áp dụng correction có kiểm chứng.

## 9. PostgreSQL 12+: nguyên tắc khôi phục vào một cluster cách ly

**Đừng restore đè trực tiếp data directory đang phục vụ.** Quy trình an toàn hơn là dựng một **instance/cluster mới** với port, storage, network, credential và tên riêng trong môi trường phục hồi được kiểm soát. Những thao tác bên dưới chỉ là **khung hướng dẫn**, không phải lệnh chạy trực tiếp trên production.

~~~text
1. Chọn base backup tương ứng với timeline và target.
2. Chuẩn bị thư mục dữ liệu / volume MỚI, trống và đúng quyền.
3. Restore base backup vật lý theo đúng công cụ/phiên bản.
4. Cấu hình restore_command lấy WAL từ archive đã được kiểm chứng.
5. Tạo recovery.signal trong thư mục data của PostgreSQL 12+.
6. Cấu hình recovery_target_time / recovery_target_* và target action.
7. Khởi động instance CÁCH LY, theo dõi WAL replay và điểm dừng.
8. Xác minh tính nhất quán, dữ liệu nghiệp vụ và phạm vi target.
9. Chỉ sau phê duyệt mới quyết định promote / cutover / trích xuất.
~~~

Ví dụ **cấu hình diễn giải**, trong đó đường dẫn và lệnh lấy WAL chỉ là placeholder phải được thay bằng công cụ backup đã chọn:

~~~conf
# postgresql.conf trên instance PHỤC HỒI, không phải primary đang chạy.
restore_command = '/opt/backup/bin/restore-wal %f %p'
recovery_target_time = '2026-11-22 14:05:09+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
~~~

Trong `restore_command` của PostgreSQL, `%f` biểu thị tên file WAL được yêu cầu, `%p` biểu thị đường dẫn đích nơi PostgreSQL mong nhận nội dung. Script `/opt/backup/bin/restore-wal` **không được cung cấp trong bài**; đó là placeholder diễn giải, không phải một file có sẵn để chạy. Công cụ/script thật phải trả exit code chính xác, lấy đúng timeline/WAL, kiểm tra file không hỏng và tuyệt đối không trả thành công giả khi chưa có file hợp lệ.

Với PostgreSQL 12 trở lên, `recovery.signal` được đặt trong **data directory** của instance cần restore để vào chế độ archive recovery; không dùng hướng dẫn cũ dựa trên `recovery.conf` như thể áp dụng cho mọi phiên bản. Cách một công cụ backup tạo signal file hoặc cấu hình target có thể khác nhau; nếu dùng công cụ chuyên dụng, **làm theo cơ chế do công cụ cung cấp**, tránh vừa chỉnh tay vừa để công cụ ghi đè.

### Vì sao chọn `pause` khi diễn tập?

`recovery_target_action='pause'` có thể cho phép operator kiểm tra trước khi kết thúc recovery/promote, tùy phiên bản và trạng thái. Trong lúc instance còn recovery, **không mặc định đây là primary ghi được**. Cần kiểm tra log và trạng thái recovery; nếu target không đạt được do thiếu WAL, không được coi việc PostgreSQL “khởi động được” là đã đạt đúng mốc.

Ở một môi trường sao lưu managed, quy trình có thể là gọi chức năng restore tới thời điểm vào **một instance mới**, không thao tác trực tiếp với file `recovery.signal`. Luôn phân biệt sơ đồ khái niệm và giao diện/cơ chế cụ thể.

## 10. Timeline sau PITR và nguy cơ split brain

Khi một PostgreSQL cluster được phục hồi tới điểm trong quá khứ rồi **promote**, lịch sử WAL thường tạo **timeline mới**. Hai cluster xuất phát từ cùng một quá khứ nhưng tiếp tục nhận giao dịch độc lập không phải hai bản sao có thể tùy ý ghép lại.

~~~mermaid
flowchart LR
    A[Timeline 1: trước sự cố] --> B[Điểm PITR]
    B --> C[Timeline 1: các commit sau target]
    B --> D[Timeline 2: cluster đã promote sau PITR]
    C -. không tự merge .- D
~~~

Điều cần kiểm soát:

- **Không cho cả primary cũ và cluster phục hồi cùng nhận ghi dưới một danh tính phục vụ** nếu không có thiết kế đa primary đúng nghĩa; đó là nguy cơ split brain, mất cập nhật và sai ledger.
- Cắt traffic theo quy trình có khóa ghi/đồng bộ DNS/proxy/connection pool phù hợp, không chỉ đổi một biến cấu hình trên một instance.
- Ghi rõ **timeline và restore target** trong biên bản; khi cần restore tiếp, phải chọn nhánh WAL tương ứng.
- Không giả định replica cũ có thể attach trực tiếp vào primary mới; có thể cần base backup mới hoặc quy trình rewind tương thích nếu đủ điều kiện.
- Sau cutover, lưu/đóng băng primary cũ theo chính sách điều tra; không xóa ngay những dữ liệu tốt sau target chưa được đối soát.

**Một PITR đúng về mặt PostgreSQL có thể sai về mặt nghiệp vụ** nếu hệ khác vẫn coi primary cũ là nguồn cập nhật hoặc consumer tiếp tục phát lại sự kiện từ timeline đã bỏ.

## 11. Chỉ nhận “PITR thành công” khi kiểm tra được trạng thái đích

Khởi động instance và kết nối được **chưa đủ**. Cần kiểm tra ít nhất:

1. **Đúng nguồn restore:** database system identifier, backup ID, timeline, target và cấu hình lưu WAL đúng.
2. **Đúng trạng thái recovery:** log engine thông báo đạt target; kiểm tra `pg_is_in_recovery()` và thông tin replay phù hợp trước khi quyết định promote.
3. **Đúng dữ liệu nghiệp vụ:** các đơn hợp lệ trước target tồn tại; những bản ghi do thao tác xóa nhầm đáng lẽ tồn tại đã được phục hồi; không có những thay đổi chỉ xảy ra sau mốc.
4. **Đúng quan hệ/constraint:** tham chiếu đơn–chi tiết, tổng tiền, tồn kho, dữ liệu kế toán và số lượng theo tiêu chí đã định.
5. **Đúng quyền:** credential vận hành, phân quyền dữ liệu, RLS, encryption và audit không bị bỏ qua chỉ vì restore.
6. **Đúng kết nối ứng dụng:** các Java service, pool, background job, cache, CDC và broker sẽ được chuyển/bật theo kế hoạch an toàn.

Ví dụ một số câu SQL **chỉ đọc** trên instance phục hồi:

~~~sql
SELECT pg_is_in_recovery() AS still_in_recovery;

-- Trong chế độ recovery, giá trị có thể NULL khi chưa replay
-- transaction commit phù hợp; không phải phép đo toàn diện.
SELECT pg_last_xact_replay_timestamp() AS last_replayed_commit;

-- Câu query nghiệp vụ phải phù hợp schema thực tế:
SELECT id, status, total_amount
FROM app.orders
WHERE id IN (712, 713)
ORDER BY id;
~~~

`pg_last_xact_replay_timestamp()` không tự chứng minh “đã đến chính xác recovery_target_time”, vì có thể không có transaction commit đúng tại target; sau khi promote, ý nghĩa metric cũng khác. **Kết hợp logs, recovery metadata, WAL/backup tool và truy vấn nghiệp vụ** để chứng minh mục tiêu.

Trước khi thử thay đổi trong bản phục hồi, lưu bằng chứng của trạng thái tại target. Một khi promote và ghi tiếp, bạn đã tạo lịch sử mới; không nên coi đó là snapshot kiểm tra còn bất biến.

## 12. Cứu dữ liệu chọn lọc hay thay toàn bộ database?

Đối với một lệnh xóa nhầm vài nghìn bản ghi, **khôi phục bản song song để trích xuất dữ liệu** thường giảm tác động hơn việc tua lùi toàn bộ database đang nhận đơn mới.

| Chiến lược | Phù hợp khi | Đánh đổi |
| --- | --- | --- |
| **Full PITR và cutover** | Primary không thể tiếp tục; phần lớn dữ liệu sau mốc không còn đáng tin; chấp nhận mất/đối soát giao dịch sau target | RTO phụ thuộc restore và cutover; cần xử lý các thay đổi tốt sau target |
| **Restore bản cách ly rồi chọn lọc dữ liệu** | Lỗi chỉ ảnh hưởng một số bảng/tenant/bản ghi; production vẫn nhận giao dịch tốt | Trích xuất và ghép dữ liệu phức tạp, phải kiểm tra conflict và foreign key |
| **Sửa tại chỗ bằng correction transaction** | Có nguồn sự thật để tính lại chính xác; lỗi đã được xác định, phạm vi nhỏ | Cần logic sửa có kiểm chứng; không được suy dữ liệu đã xóa từ log ứng dụng |
| **Phục hồi từ snapshot gần nhất** | Không có replay log hoặc không cần lịch sử sau snapshot | Có thể mất toàn bộ dữ liệu sau snapshot |
| **Failover sang replica** | Mất node primary, replica có trạng thái phù hợp | Replica có thể đã áp dụng giao dịch xóa nhầm; không phải cách Undo |

### Quy trình trích xuất có kiểm soát

Giả sử một nhóm `orders` bị xóa nhầm nhưng những đơn khác vẫn đang cập nhật:

1. Restore vào **cluster cách ly** ở thời điểm trước DELETE.
2. Truy vấn danh sách ID/tenant bị ảnh hưởng và xác định tập bản ghi cần lấy lại.
3. Kiểm tra các bảng phụ thuộc như `order_lines`, payment metadata, shipping status, outbox và audit.
4. **Đối chiếu với production hiện tại**: bản ghi nào đã được tạo lại, có ID bị tái sử dụng không, liệu trạng thái mới sau sự cố có hợp lệ hơn snapshot cũ không?
5. Thiết kế một migration/correction riêng có ràng buộc, transaction, idempotency, audit, kiểm tra tenant và **không ghi đè mù dữ liệu hiện tại**.
6. Kiểm tra kết quả và tạo bản backup/checkpoint mới sau khắc phục.

**Đừng** chạy lệnh kiểu `INSERT INTO live.orders SELECT * FROM restored.orders` trên hai hệ rồi mặc định đúng: cột mới có thể khác schema, có sequence/identity, unique constraint, foreign key, event ngoài DB và bản ghi được cập nhật hợp lệ sau mốc. Việc copy dữ liệu theo schema không có nghĩa đã khôi phục được **ngữ nghĩa nghiệp vụ**.

Một câu `pg_dump` từ **instance được restore** có thể hữu ích để xuất dữ liệu, nhưng việc import vào production phải qua quy trình kiểm chứng riêng. Một SQL dump không tự giải quyết merge conflict, missing references hoặc duplicate side effects.

## 13. Kiểm tra tính đầy đủ của archive và khả năng restore

PITR phụ thuộc **chuỗi backup**, không chỉ việc cron job báo “backup success”. Những tín hiệu cần theo dõi:

| Kiểm tra | Câu hỏi |
| --- | --- |
| Base backup gần nhất dùng được | Có thể restore thật không, có thiếu file/checksum không? |
| WAL archive coverage | Từ backup nền đến target có mọi segment cần thiết không? |
| `last_archived_time` và archive failures | Archiver có hoạt động gần thời điểm hiện tại không? |
| Kho lưu trữ độc lập | Host/volume production hỏng thì archive còn không? |
| Encryption keys | Có giải mã được tất cả backup và WAL không? |
| Retention/garbage collection | Backup và những WAL cần để restore có bị xóa lệch nhau không? |
| Timeline history | Restore tool có đủ lịch sử nhánh và segment thích hợp không? |
| Restore rehearsal | Lần phục hồi có kết thúc đúng target và dữ liệu đúng không? |

Trên PostgreSQL có thể xem thông tin hoạt động archiver:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Lưu ý:

- Các bộ đếm tích lũy từ `stats_reset`, không phải số lỗi trong 1 phút gần nhất; cần lấy **delta theo thời gian**.
- `last_archived_time` cũ không nhất thiết là lỗi nếu workload rất thấp và chưa có segment hoàn chỉnh; phải hiểu WAL generation, `archive_timeout` và cơ chế archival của môi trường.
- `archived_count` tăng không chứng minh mọi backup chain đều dùng được; có thể thiếu một segment do lỗi retention/copy/permission ở nơi lưu trữ.
- Managed database có thể không cung cấp `pg_stat_archiver` đầy đủ hoặc dùng cơ chế log riêng; phải theo dõi metric/backup history của nhà cung cấp.

### Kiểm tra trên primary không thay diễn tập restore

Ở primary có thể quan sát WAL position và lưu lượng ghi:

~~~sql
-- Chỉ là vị trí WAL quan sát tại thời điểm gọi.
SELECT pg_current_wal_lsn() AS current_lsn;
~~~

LSN tăng chứng minh server tạo WAL, **không** chứng minh WAL đã đến kho archive an toàn hoặc có thể khôi phục từ base backup. Cần đối chiếu trạng thái archive/backup tool và thực hiện restore thực tế.

### Retention cần tính theo chuỗi phụ thuộc

Giữ base backup 30 ngày nhưng xóa WAL sau 7 ngày có thể khiến không thể phục hồi tới phần lớn mốc 30 ngày trước đó. Ngược lại, giữ WAL rất lâu mà không có base backup tương thích có thể làm kho lưu trữ lớn nhưng không có giá trị khôi phục mong muốn. Chính sách retention phải đảm bảo **mỗi mốc còn được cam kết có một đường restore hoàn chỉnh**.

## 14. Java/JDBC: kiểm chứng bản dữ liệu đã phục hồi

Trong một ứng dụng Java, người học cần biết cách **kiểm chứng nghiệp vụ sau PITR** mà không biến môi trường recovery thành hệ thống xử lý production thứ hai. Ví dụ dưới đây dùng `DataSource` trỏ vào **cluster cách ly**, credential chỉ đọc và hai order ID đã biết từ kịch bản thử nghiệm.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HashSet;
import java.util.Set;
import javax.sql.DataSource;

public final class RestoreVerifier {
    private final DataSource recoveryDataSource;

    public RestoreVerifier(DataSource recoveryDataSource) {
        this.recoveryDataSource = recoveryDataSource;
    }

    public void assertOrdersRestored(long firstId, long secondId)
            throws SQLException {
        if (firstId <= 0 || secondId <= 0 || firstId == secondId) {
            throw new IllegalArgumentException("ID kiểm thử không hợp lệ");
        }

        String sql = "SELECT id FROM app.orders " +
                "WHERE id IN (?, ?)";

        try (Connection connection =
                     recoveryDataSource.getConnection()) {
            // setReadOnly là hint của JDBC/driver;
            // quyền SELECT-only tại DB mới là hàng rào thực thi.
            connection.setReadOnly(true);
            try (PreparedStatement statement =
                         connection.prepareStatement(sql)) {
                statement.setLong(1, firstId);
                statement.setLong(2, secondId);

                Set<Long> found = new HashSet<>();
                try (ResultSet rows = statement.executeQuery()) {
                    while (rows.next()) {
                        found.add(rows.getLong(1));
                    }
                }
                if (!found.contains(firstId) ||
                        !found.contains(secondId)) {
                    throw new IllegalStateException(
                            "Bản restore thiếu order dự kiến");
                }
            }
        }
    }
}
~~~

Đây là **một kiểm tra hẹp**, không phải bài test toàn diện xác nhận PITR. Hai ID tồn tại chưa chứng minh những lần thanh toán và thay đổi tồn kho đã đúng. Đối với kịch bản thực tế cần thêm:

- So sánh snapshot với mốc/phiên bản nghiệp vụ đã được kiểm chứng.
- Tổng số dòng trong tập bị tác động, các ràng buộc foreign key và tổng số tiền (có tiêu chí sai số cụ thể).
- Kiểm tra **giao dịch không được xuất hiện sau target** thay vì chỉ xác nhận các bản ghi trước target còn.
- Đối chiếu outbox, idempotency keys và external payment/order state.
- Chỉ truy vấn bằng **role read-only** trên recovery instance; hạn chế chạy migrations, consumer, scheduled jobs và webhook.

`Connection.setReadOnly(true)` không nên được xem là policy an ninh tuyệt đối. Driver/database có thể dùng nó như hint hoặc thiết lập khác tùy công nghệ; quyền database và mạng cách ly mới là biện pháp phòng vệ phù hợp.

### Không khởi động toàn bộ Java service trên bản restore

Nếu bật một bản sao service với scheduler, email sender, outbox relay hoặc webhook consumer, nó có thể **gửi thông điệp/thu tiền lần thứ hai** cho những đơn đã xử lý trên hệ thật. Để kiểm chứng an toàn:

- Cấu hình recovery application ở chế độ **read-only/verification-only**.
- Chặn outbound network tới broker, payment provider, email, object store ghi và webhook ngoài.
- Không cho worker xử lý outbox hoặc chạy job migration/cleanup theo lịch.
- Dùng credential/secret dành riêng cho môi trường phục hồi, không sao chép nguyên mọi quyền production khi không cần.

## 15. Tính nhất quán của transaction sau PITR

Một physical recovery của PostgreSQL áp dụng WAL theo quy tắc database, nhằm tạo trạng thái nhất quán ở mốc target phù hợp. Điều này khác việc chép thủ công từng file giữa các thời điểm và khác một snapshot không nhất quán giữa các volume.

Tuy nhiên, cần phân biệt:

| Phạm vi | PITR của một PostgreSQL cluster có thể bao phủ? | Ghi chú |
| --- | --- | --- |
| Các bảng cùng cluster đã commit đúng quy tắc | **Có, trong giới hạn backup/WAL và mốc target** | Transaction DB giữ atomicity cục bộ |
| Những transaction chưa commit ở target | **Không được xem là commit hợp lệ** | Recovery áp dụng semantics crash/transaction log |
| Dữ liệu trên một PostgreSQL cluster khác | **Không tự động** | Hai cluster không chia sẻ một commit boundary |
| Redis cache / search index | **Không tự động** | Cần rebuild/invalidate/reconciliation |
| Kafka broker / outbox consumer offsets | **Không tự động** | Event đã gửi có thể tồn tại dù DB được tua về trước |
| Payment provider / email / SMS | **Không** | Tác động bên ngoài không được rollback bởi WAL |
| File trên S3 hoặc object storage | **Không** | Cần backup/versioning/quy trình phục hồi riêng |

Sau PITR, một record `outbox_events` có thể biến mất vì được tạo sau target, nhưng event tương ứng **đã phát tới broker trước sự cố**. Ngược lại, một event đã được phát và đánh dấu xử lý trước target có thể trở lại trạng thái pending trên bản DB cũ, dẫn đến nguy cơ **phát lại**. Phải định nghĩa quy tắc đối soát producer/consumer và chống trùng bằng event ID/idempotency key.

### Cẩn trọng khi tua lùi khóa định danh và sequence

Sau PITR, sequence và các bộ đếm ID cũng phản ánh một lịch sử cũ theo cơ chế của engine. Nếu downstream hoặc hệ thanh toán đã lưu các ID được tạo sau target, việc hệ khôi phục về trạng thái trước đó có thể gây xung đột khi cấp ID mới hoặc tạo mapping sai. Cần thiết kế định danh không tái sử dụng khi đi qua nhiều hệ, đối soát các khoảng ID và kiểm tra sequence/identity trước khi ghi production. Không đặt thủ công `setval()` theo ước lượng mà thiếu kiểm chứng dữ liệu hiện có và các external references.

## 16. Tác động ngoài DB: saga, outbox, idempotency và đối soát

Giả sử một order đã được thanh toán trước lúc database bị phục hồi về thời điểm trước khi order được tạo:

~~~mermaid
sequenceDiagram
    participant O as Order DB
    participant B as Broker
    participant P as Payment Provider
    O->>B: OrderPlaced(order=713)
    B->>P: Charge(paymentKey=R713)
    P-->>B: Đã thu tiền
    Note over O: Sau đó PITR lùi về trước order=713
    Note over P: Payment vẫn đã thu, không tự hoàn
~~~

Đây không phải lỗi của PostgreSQL; nó là **giới hạn của ranh giới transaction**. Cần có kế hoạch:

1. Tạm dừng luồng tạo giao dịch/consumer có thể gây tác động ngoài trong thời gian chuyển trạng thái.
2. Trích xuất danh sách business ID và event ID của các giao dịch sau target từ nguồn còn tin cậy, logs, broker, provider hoặc bản primary cũ được bảo tồn.
3. Tra cứu kết quả thực tế từ bên ngoài qua **idempotency key/provider transaction ID**.
4. Chọn hành động phù hợp: tạo lại dữ liệu DB theo kết quả thực, hoàn tiền, hủy yêu cầu, giữ ở trạng thái `PENDING_RECONCILIATION`.
5. Phát sự kiện bù/đối soát có định danh ổn định; consumer phải xử lý trùng an toàn.
6. Audit những quyết định thủ công và giữ bằng chứng để giải quyết tranh chấp.

Không chạy lại hàng loạt mọi request sau target mà không đối soát; thao tác như **charge**, gửi email hoặc giữ inventory có thể đã thành công dù database được tua về trước. Tính **idempotent** của từng thao tác quan trọng hơn việc một worker “chạy lại thành công”.

## 17. PITR trong hệ multi-tenant, sharding và nhiều vùng

Một hệ thống có thể chứa nhiều tenant trong một cluster hoặc phân vùng theo shard. **Mốc phục hồi của một physical database** thường bao trùm cả phạm vi backup của nó, không chỉ tenant bị ảnh hưởng.

Ví dụ tenant A bị lệnh DELETE sai ở bảng dùng chung. Nếu PITR cả cluster về trước sự cố, tenant B cũng mất những giao dịch hợp lệ sau target. Vì vậy:

- Ưu tiên **restore bản song song** và trích xuất chọn lọc theo tenant khi còn có thể.
- Kiểm tra **khóa định danh, foreign key và dữ liệu dùng chung** trước khi import tenant.
- Với sharding, phải định nghĩa target và log coverage **theo từng shard**, không mặc định các shard có cùng timestamp nghĩa là cùng snapshot ứng dụng nhất quán toàn cục.
- Với active-active/multi-region, xác định **nguồn sự thật, replication direction, conflict resolution và fencing** trước khi cho cluster phục hồi nhận ghi.
- Khi thay một shard bằng bản cũ, phải kiểm tra sự kiện/offset trên các shard và hệ downstream; transaction liên shard có thể cần phục hồi theo giao thức riêng.

**Không có một PITR toàn cục miễn phí** chỉ vì từng database đơn lẻ hỗ trợ PITR. Nếu invariant trải qua nhiều hệ, khôi phục đòi hỏi trạng thái phối hợp hoặc reconciliation của toàn workflow.

## 18. Các công nghệ khác: hỗ trợ PITR tùy engine và dịch vụ

Không nên áp dụng nguyên mẫu PostgreSQL vào mọi hệ.

| Công nghệ/triển khai | Năng lực có thể dùng | Điều cần xác minh |
| --- | --- | --- |
| **PostgreSQL tự quản** | Physical base backup + archived WAL, recovery target | Chuỗi WAL/timeline, phiên bản, retention, cấu hình recovery và phục hồi cluster |
| **PostgreSQL managed** | Tính năng PITR/continuous backup do provider cung cấp khi bật | Earliest/latest restorable time, cách tạo instance mới, RPO/RTO, chi phí |
| **MySQL/InnoDB** | Full backup phù hợp + binary log để roll forward theo khả năng công cụ | Binlog format, GTID/position, backup consistency, transaction boundary, timezone và log retention |
| **MongoDB** | Snapshot/backup cộng oplog hoặc PITR do công cụ/managed service hỗ trợ | Replica set/sharding, oplog window, restore consistency, quyền và phiên bản |
| **Cassandra** | Snapshots + incremental backup/commit log hoặc công cụ phục hồi đặc thù | Không suy rằng có arbitrary PITR tương tự PostgreSQL; phạm vi và vận hành khác |
| **Redis** | RDB/AOF và snapshot theo cấu hình | Không mặc định có chọn mốc thời gian bất kỳ; AOF/RDB không tự thành PITR được quản lý |
| **Search engine** | Snapshot và các cơ chế backup/index restore | Không mặc định có transaction-log PITR của source-of-truth DB |
| **Object storage** | Versioning/snapshot/replication theo nhà cung cấp | Phục hồi object/version không phải một transaction PITR toàn database |

Ví dụ MySQL có thể cần bản backup nhất quán cùng binlog bắt đầu từ **vị trí ghi nhận trong backup**, rồi replay tới điểm an toàn. Việc dùng một timestamp với `mysqlbinlog` để cắt replay có thể vướng timezone, transaction boundary và lệch đồng hồ; đối với nghiệp vụ quan trọng nên chọn position/GTID hoặc quy trình do công cụ chính thức hỗ trợ và **kiểm thử kết quả**.

Với managed database, nhà cung cấp có thể trả về một **cửa sổ PITR** gồm earliest/latest restorable times. Không được yêu cầu target mới hơn latest restorable time rồi giả định dữ liệu đã sẵn sàng; cũng không được coi retention “7 ngày” là chứng minh mọi giây trong 7 ngày đều restorable khi backup/log đang lỗi.

Những phát biểu về tính năng, độ chính xác và giới hạn phải được xác minh theo **phiên bản, cấu hình và dịch vụ đang dùng**; không thay thế tài liệu tương thích bằng bảng so sánh tổng quan.

## 19. Backup security: dữ liệu còn an toàn khi được khôi phục không?

Backup thường chứa **rất nhiều dữ liệu hơn một API được phép trả**. Một file backup bị lộ có thể vượt qua toàn bộ kiểm tra authorization của ứng dụng.

Những yêu cầu tối thiểu:

- **Mã hóa:** bảo vệ dữ liệu khi truyền và lưu, kiểm soát khóa giải mã; kiểm tra khả năng khôi phục khi xoay vòng key.
- **Quyền tối thiểu:** role backup/restore không phải credential HTTP runtime; phân quyền đọc/xóa backup, đổi retention và thay cấu hình archive riêng.
- **Tách biệt:** tránh cùng host/volume/tài khoản có thể bị xóa khi primary bị chiếm quyền; có thể dùng immutable/object lock hoặc cơ chế chống sửa/xóa phù hợp.
- **Bảo vệ truy cập mạng:** instance restore không tự public; tách khỏi network của production khi cần, chặn outbound side effects.
- **Giữ bản sao phục hồi tin cậy:** kẻ tấn công có thể đã sửa dữ liệu/credential trước target; cần xác định một mốc đủ tin cậy và kiểm tra dấu hiệu xâm nhập.
- **Retention và xóa an toàn:** tuân thủ nhu cầu pháp lý/quyền dữ liệu, hiểu rằng backup có chu kỳ xóa riêng với production.
- **Audit:** ghi ai chọn mốc, đọc backup, đổi quyền, bắt đầu restore, promote và cutover.

Đừng đưa mật khẩu thật vào script restore, command history hoặc log CI. Backup metadata, key và secret phải có kế hoạch bảo quản độc lập; **khóa bị mất làm bản backup đã mã hóa có thể không khôi phục được** dù file vẫn còn.

### Backup không thay quyền truy cập và transaction

Khả năng restore tốt giúp phục hồi sau lỗi, nhưng không phải lý do cho phép ứng dụng dùng `SUPERUSER`, bỏ constraint, hoặc thiếu validation. Ngăn lỗi từ đầu (least privilege, migration review, parameter binding, audit, lock/transaction correctness) và khôi phục sau lỗi là **hai lớp phòng vệ bổ sung**.

## 20. Đo lường: các chỉ số vận hành PITR

Một dashboard đủ dùng nên theo dõi **khả năng thực sự phục hồi**, không chỉ số lượng file backup:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| `last_successful_base_backup` | Có bản nền gần đây đã được xác minh không? |
| `backup_duration` / `backup_size` | Khối lượng và thời gian restore dự kiến đang thay đổi thế nào? |
| `archive_success_rate` / `archive_failure_count` | WAL archiving có thất bại không? |
| `archive_lag_seconds` | Log tới kho phục hồi trễ bao lâu so với tiến độ ghi? |
| `oldest_restorable_time` | Mốc sớm nhất còn khôi phục được là khi nào? |
| `latest_verified_restorable_time` | Mốc mới nhất đã có bằng chứng đủ log là gì? |
| `restore_test_success` | Lần diễn tập gần nhất phục hồi được dữ liệu theo target không? |
| `restore_elapsed_seconds` | Thời gian thực tế so với RTO |
| `replay_duration` / `WAL_volume` | Replay đang là phần chậm của restore không? |
| `backup_integrity_failure_count` | Có checksum, thiếu file hoặc lỗi giải mã không? |
| `reconciliation_gap` | Có bao nhiêu giao dịch/side effect cần đối soát sau target? |

`latest_verified_restorable_time` là một chỉ số **do công cụ/quy trình kiểm chứng suy ra** hoặc do nhà cung cấp cung cấp theo định nghĩa của họ; không phải view PostgreSQL mặc định có sẵn chỉ cần SELECT. Cần ghi rõ nguồn đo và sai số.

**Cảnh báo đáng hành động:** archive không tiến trong khi WAL sinh liên tục, backup test thất bại, backup retention sắp xóa log cần thiết, restore test vượt RTO, hoặc cửa sổ PITR thực ngắn hơn cam kết. Cảnh báo phải dẫn đến người trực và runbook cụ thể.

## 21. Diễn tập khôi phục: đo RTO và xác minh RPO

Một hệ có SLA phục hồi chỉ đáng tin khi **thường xuyên diễn tập**:

1. Tạo môi trường thử nghiệm có dữ liệu và tải đại diện, quyền truy cập phù hợp.
2. Tạo base backup và bảo đảm WAL đang được archive liên tục.
3. Ghi một chuỗi giao dịch có ID/mốc rõ: create order A, update order B, commit, sau đó cố ý tạo một thay đổi sai có kiểm soát.
4. Chọn recovery target ngay trước giao dịch sai bằng bằng chứng WAL/time/restore point phù hợp.
5. Phục hồi vào instance **cách ly**; đo thời gian tải base, replay, kiểm tra và sẵn sàng chuyển traffic.
6. Dùng SQL/JDBC kiểm tra **có** những commit hợp lệ trước target và **không có** thay đổi chỉ xảy ra sau target.
7. Thử mất một WAL segment trong môi trường test: quy trình phải **báo lỗi thiếu chain**, không tuyên bố đã đạt target.
8. Thử archive trễ, storage object không truy cập được hoặc key giải mã sai; kiểm tra alert và runbook.
9. Xác minh cache/search/outbox/payment reconciliation plan và khả năng chặn duplicate.
10. Lập biên bản bài học: target, timeline, phạm vi restore, thời gian, dữ liệu mất/được cứu, blockers và kế hoạch cải thiện.

### Fault-injection có ích

| Lỗi mô phỏng | Kỳ vọng hệ thống |
| --- | --- |
| Backup tồn tại nhưng thiếu WAL giữa đường | Từ chối công bố PITR đạt target |
| WAL archive chậm nhiều phút | Metric/alert thể hiện cửa sổ mất dữ liệu có thể tăng |
| Sai timezone khi nhập target | Kiểm tra preflight bắt được trước khi promote |
| Target trước khả năng phục hồi của base backup | Tool báo target không đạt, chọn backup phù hợp |
| Phục hồi vào instance có kết nối mạng sản xuất | Runbook chặn trước khi worker phát side effect |
| Primary cũ tiếp tục nhận ghi sau cutover | Fencing/routing policy ngăn hai primary độc lập |
| Consumer nhận lại event sau PITR | Inbox/idempotency ngăn side effect lặp |
| Backup giải mã thất bại sau rotation | Báo lỗi và kiểm tra quyền/khóa theo runbook |

Không gây sự cố trên production chỉ để “thử hệ thống”. Diễn tập nên chạy ở môi trường được phê duyệt, sử dụng dữ liệu đã bảo vệ và công cụ không cần quyền vượt quá mức cần thiết.

## 22. Bài tập: khôi phục một giao dịch xóa nhầm

Một hệ thống Java dùng PostgreSQL và Kafka:

~~~text
01:00:00 +07  Base backup tạo trên primary.
01:12:00 +07  Base backup hoàn tất.
14:00:00 +07  Kafka và Order Service hoạt động bình thường.
14:04:50 +07  Order 713 được commit, OrderPlaced đã gửi Kafka.
14:05:10 +07  Transaction DELETE nhầm orders được commit.
14:05:40 +07  Một khoản thanh toán hợp lệ khác được charge.
14:06:00 +07  Phát hiện lỗi và dừng job gây sự cố.
14:08:00 +07  Kho archive WAL đang có segment bao phủ 14:05:10
                nhưng chưa xác minh đủ tới 14:06:00.
~~~

**Yêu cầu:**

1. Bản base backup lúc 01:00 có thể tự đưa hệ thống về 14:05:09 không? Vì sao?
2. Nếu WAL chain đầy đủ tới 14:05:09 nhưng không tới 14:06:00, có thể khôi phục mốc nào?
3. Nếu service đã phát `OrderPlaced(713)` tới Kafka, tại sao PITR không tự lấy message đó ra khỏi broker?
4. Nếu mục tiêu là cứu chỉ các order bị DELETE nhưng còn nhiều đơn hợp lệ sau 14:05:10, có nên đưa toàn bộ production về trước lỗi?
5. Nếu nhập mốc `2026-11-22 14:05:09` **không kèm timezone**, nguy cơ là gì?
6. Nếu sau PITR, order 713 có trong DB nhưng bảng payment của hệ ngoài ghi kết quả khác, cần xử lý ra sao?
7. Nếu restore đạt target nhưng toàn bộ job outbox trên recovery instance tự bật, rủi ro là gì?
8. Bộ metric và kiểm thử nào chứng minh RPO/RTO trong tình huống này?

**Hướng giải:**

- (1) Không. Base backup cần WAL và metadata tương ứng; một snapshot không tự replay đến thời điểm bất kỳ.
- (2) Mốc có thể chọn phải nằm **trong chuỗi log có thể replay và được công cụ xác minh**, không vượt những đoạn WAL thiếu. Không mặc định snapshot WAL tới 14:05:10 bao hàm mọi thay đổi 14:06:00.
- (3) Broker nằm ngoài ranh giới transaction PITR của PostgreSQL; event đã phát vẫn tồn tại và có thể được consumer xử lý.
- (4) Cân nhắc restore bản song song rồi **trích xuất và merge chọn lọc** để giữ giao dịch hợp lệ sau sự cố, có đối soát FK/ID/đơn vị tiền.
- (5) Timezone của tool/session có thể khiến target lệch giờ; dùng offset rõ và xác minh commit boundary.
- (6) Dựa vào provider event ID/idempotency key, đối chiếu, cập nhật/trả lại trạng thái đúng hoặc kích hoạt workflow bù; không tự charge lần nữa.
- (7) Có thể gửi event lặp hoặc thực thi side effect ngoài DB; phải cách ly mạng và tắt worker.
- (8) Cần backup chain integrity, archive coverage/lag, restore test tới target, đo thời gian restore+verify+cutover, kiểm tra giao dịch trước/sau target và số yêu cầu cần reconciliation.

## 23. Checklist trước khi công bố khả năng PITR

1. **Phạm vi:** biết PITR áp dụng cho cluster/database/tenant nào và công nghệ/phiên bản có thực sự hỗ trợ không.
2. **Mốc:** xác định timezone, target type, inclusive/exclusive, transaction boundary và timeline.
3. **Backup:** có physical base backup hoặc cơ chế backup phù hợp, đã kiểm tra integrity và tính nhất quán.
4. **Log:** đầy đủ WAL/binlog/oplog/chuỗi thay đổi cần thiết từ backup đến target; không có khoảng hở.
5. **Retention:** mỗi mốc còn được cam kết có đủ backup, log, khóa giải mã và metadata để restore.
6. **RPO/RTO:** có mục tiêu đo được, dữ liệu thử nghiệm và biên bản thời gian restore thực tế.
7. **Nguồn sự thật:** biết các hệ ngoài DB chịu tác động và chiến lược reconcile/outbox/idempotency.
8. **Cách ly:** restore vào cluster mới, chặn external side effects và không cho primary cũ cùng nhận ghi.
9. **Quyền:** principal restore, secret, TLS, archive access và audit tuân theo least privilege.
10. **Kiểm chứng:** log xác nhận đạt target, kiểm tra dữ liệu có/không đúng lúc, invariants và constraints.
11. **Chuyển traffic:** có runbook fencing, routing, pool drain, promotion và rollback/correction.
12. **Theo dõi:** archive lag, backup integrity, latest restorable time, restore rehearsal và alert.
13. **Diễn tập:** đã thử mất log, sai timezone, unknown commit, duplicate event và các tình huống lỗi thực tế.
14. **Sau sự cố:** chốt mốc kiểm chứng, đối soát giao dịch, lập backup mới, làm báo cáo nguyên nhân gốc và phòng ngừa lặp lại.

**Kết luận:** Khôi phục theo thời điểm là một khả năng quan trọng của persistence khi công nghệ hỗ trợ phát lại lịch sử thay đổi. Trong PostgreSQL, nó đòi hỏi **base backup có thể sử dụng và chuỗi WAL liên tục**, cùng việc chọn đúng target/timeline và kiểm tra phục hồi trên một instance cách ly. PITR bảo vệ **trạng thái giao dịch trong phạm vi database**, không tự hoàn tác tác động ở broker, cache, thanh toán hay các hệ khác. Muốn kết quả vừa an toàn vừa phục vụ được nghiệp vụ, phải kết hợp **PITR, RPO/RTO, backup integrity, kiểm thử khôi phục, quyền truy cập và quy trình đối soát**; một file backup tồn tại chưa phải bằng chứng hệ thống phục hồi được.
