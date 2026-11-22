# Backup, Data Guard và khả năng sẵn sàng trên Exadata

## 1. Mục tiêu và bối cảnh

Trong chương **Exadata và Cloud@Customer** của lộ trình Oracle Cloud Infrastructure (OCI), bài này trình bày cách kết hợp backup, Oracle Data Guard và các cơ chế sẵn sàng của Exadata để bảo vệ cơ sở dữ liệu. Trọng tâm là thiết kế có thể vận hành: phân quyền, kết nối mạng, giám sát, tự động hóa, khôi phục và chi phí.

Sau bài học, bạn có thể:

- Phân biệt tính sẵn sàng cao tại một địa điểm với khôi phục thảm họa và khôi phục dữ liệu lịch sử.
- Chuyển yêu cầu nghiệp vụ thành RPO, RTO và các phép đo cụ thể.
- Lựa chọn vị trí lưu backup và vị trí standby phù hợp với miền sự cố.
- Giải thích redo transport, redo apply, switchover và failover.
- Lập quy trình kiểm chứng backup, diễn tập chuyển vai trò và đưa ứng dụng trở lại phục vụ.

Các nguyên lý Oracle Database trong bài áp dụng cho nhiều môi trường Exadata. Khi triển khai bằng dịch vụ OCI, cần phân biệt **Exadata Database Service trên hạ tầng cloud** với **Exadata Database Service on Cloud@Customer** đặt tại trung tâm dữ liệu khách hàng. Khả năng cấu hình qua Console/API, đích backup và quyền sử dụng tính năng phụ thuộc dịch vụ, phiên bản và hợp đồng. Không lấy một tùy chọn của Cloud@Customer làm mặc định cho mọi dịch vụ Exadata.

## 2. Ba lớp bảo vệ giải quyết ba nhóm sự cố

Một hệ thống có nhiều nút và nhiều bản sao dữ liệu vẫn có thể mất dữ liệu hoặc ngừng phục vụ. Cần xác định từng cơ chế bảo vệ được điều gì.

| Cơ chế | Vai trò chính | Giới hạn cần nhớ |
| --- | --- | --- |
| Thành phần dự phòng của Exadata, ASM và Oracle RAC | Chịu một số lỗi phần cứng hoặc instance, duy trì dịch vụ trong cụm khi thiết kế và tài nguyên cho phép | Các instance RAC cùng truy cập một database; nhiều instance không tạo ra lịch sử dữ liệu độc lập |
| Oracle Data Guard | Duy trì standby và chuyển vai trò khi primary không còn phục vụ được | Thay đổi hợp lệ nhưng sai nghiệp vụ có thể được truyền sang standby |
| Backup và recovery | Khôi phục file, database hoặc trạng thái dữ liệu tại thời điểm được bảo vệ | Cần thời gian đọc backup, áp dụng thay đổi và kiểm tra ứng dụng |
| Flashback được cấu hình phù hợp | Hỗ trợ quay lại trạng thái trước đó trong phạm vi dữ liệu khôi phục còn giữ | Không thay thế bản backup tách khỏi nơi sản xuất |

Ví dụ: ứng dụng thực hiện nhầm một câu lệnh xóa đơn hàng rồi commit. RAC tiếp tục hoạt động; Data Guard có thể áp dụng chính thay đổi đó ở standby. Khả năng sống sót của cụm không tự phục hồi các đơn hàng đã xóa.

Ngược lại, nếu chỉ một instance RAC bị lỗi, khôi phục toàn bộ database từ backup thường là biện pháp vượt quá phạm vi sự cố. Cần để cơ chế cụm và dịch vụ ứng dụng xử lý lỗi cục bộ trước khi quyết định chuyển địa điểm.

Một kiến trúc thực tế thường kết hợp cả ba lớp: **sẵn sàng trong cụm, standby ở miền sự cố khác và backup có lịch sử khôi phục**.

## 3. Xác định RPO, RTO theo từng kịch bản

### 3.1. Hai mục tiêu khác nhau

**RPO — Recovery Point Objective** là mức mất dữ liệu tối đa có thể chấp nhận, thường biểu diễn bằng khoảng thời gian. RPO 5 phút nghĩa là nghiệp vụ chấp nhận mất tối đa khoảng dữ liệu của 5 phút trước sự cố, theo phạm vi đã thống nhất.

**RTO — Recovery Time Objective** là thời gian tối đa chấp nhận để khôi phục dịch vụ sau gián đoạn. Cần thống nhất mốc bắt đầu và điều kiện kết thúc: database mở được, hay người dùng đã thực hiện lại giao dịch thành công?

Đối với một dịch vụ bán hàng, nên đo RTO đến lúc luồng tạo đơn hoạt động đúng. Một database đã chuyển sang primary nhưng connection pool vẫn trỏ sai địa điểm chưa đáp ứng mục tiêu này.

Công thức lập ngân sách thời gian:

~~~text
RTO thực đo =
    thời gian phát hiện
  + thời gian đánh giá và quyết định
  + thời gian khôi phục/chuyển vai trò
  + thời gian định tuyến và kết nối lại
  + thời gian kiểm tra nghiệp vụ
~~~

### 3.2. Ví dụ về điểm dữ liệu khôi phục

Giả sử sự cố làm mất primary lúc 12:00:00. Standby giữ bền vững toàn bộ redo cần thiết đến 11:57:30; redo mới hơn không thể lấy lại từ nơi khác.

Trong giả định này, khoảng dữ liệu có nguy cơ mất là 2 phút 30 giây. Standby đã tồn tại từ trước không đủ để kết luận RPO bằng 0.

Nếu redo đến 12:00:00 đã được lưu bền vững ở standby nhưng mới được apply đến 11:58:30, phần chưa apply chưa đồng nghĩa với mất dữ liệu. Có thể cần thêm thời gian áp dụng redo trước khi mở database sau chuyển vai trò. Kịch bản này tác động đến thời gian khôi phục khác với việc redo chưa bao giờ tới standby.

### 3.3. Không dùng một cặp số cho mọi loại sự cố

Ví dụ mục tiêu do một doanh nghiệp giả định đặt ra:

| Sự cố | RPO mục tiêu | RTO mục tiêu | Hướng xử lý dự kiến |
| --- | --- | --- | --- |
| Mất một instance | Không mất giao dịch đã commit theo bảo đảm của cấu hình | Vài phút | RAC, dịch vụ theo role và ứng dụng kết nối lại |
| Mất toàn bộ địa điểm primary | Không quá 5 phút | Không quá 30 phút | Data Guard tại địa điểm thứ hai |
| Xóa nhầm được phát hiện sau 2 giờ | Khôi phục được trạng thái trước câu lệnh sai | Không quá 4 giờ cho phạm vi dữ liệu đã thỏa thuận | Khôi phục biệt lập, PITR hoặc Flashback nếu phù hợp |
| Mất cả primary và standby | Theo điểm bảo vệ của backup bên ngoài | Theo dung lượng và năng lực restore | Backup ở miền sự cố thứ ba |

Đây là mục tiêu thiết kế, không phải SLA của Oracle. Thời gian thực tế phải được chứng minh bằng diễn tập với dữ liệu và tải tương ứng.

Đối với lỗi nghiệp vụ, quay toàn bộ database về thời điểm trước lỗi có thể làm mất các thay đổi đúng sau thời điểm đó. Vì vậy phải đánh giá cả phạm vi khôi phục và phương án đối soát, thay vì chỉ ghi một RPO chung.

## 4. Thiết kế theo miền sự cố

Một miền sự cố là tập hợp thành phần có thể cùng bị ảnh hưởng bởi một nguyên nhân: nguồn điện, rack, hạ tầng Exadata, trung tâm dữ liệu, vùng cloud, đường truyền hoặc tài khoản quản trị.

Hai VM cluster khác nhau trên cùng hạ tầng vật lý vẫn có thể chia sẻ nhiều rủi ro. Với Cloud@Customer, Oracle khuyến nghị đặt primary và standby của tải production trên các Exadata Cloud Infrastructure khác nhau để tăng mức cách ly sự cố. [Tài liệu Data Guard cho Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-using-data-guard.html).

Một kiến trúc minh họa:

~~~mermaid
flowchart LR
    APP["Ứng dụng và connection pool"]
    SVC["Database service theo vai trò PRIMARY"]

    subgraph A["Địa điểm A"]
        P["Primary trên Exadata / RAC"]
        FA["Vùng recovery cục bộ"]
    end

    subgraph B["Địa điểm B: miền sự cố độc lập"]
        S["Physical standby trên Exadata"]
    end

    subgraph C["Miền bảo vệ backup độc lập"]
        BK["Đích backup và lịch sử khôi phục"]
        KEYS["Khóa, cấu hình và quyền phục hồi"]
    end

    OBS["Observer nếu dùng FSFO"]

    APP --> SVC
    SVC -->|"Vai trò đang phục vụ"| P
    SVC -.->|"Sau chuyển vai trò"| S
    P -->|"Redo transport"| S
    P --> FA
    P -->|"Backup"| BK
    S -.->|"Backup nếu phương án được hỗ trợ"| BK
    OBS -.-> P
    OBS -.-> S
    KEYS -.-> BK
~~~

Sơ đồ là phương án thiết kế, không khẳng định mọi tổ hợp dịch vụ hoặc địa điểm đều tạo được bằng một thao tác trên Console. Trước triển khai phải xác nhận topology được hỗ trợ, phiên bản database, vùng dịch vụ và phương thức quản lý.

Khi chọn vị trí, hãy ghi rõ:

- Sự cố nào có thể đồng thời làm mất primary và standby?
- Bản backup có tồn tại nếu toàn bộ hạ tầng sản xuất không thể truy cập?
- Nhóm khôi phục có lấy được khóa và thông tin xác thực nếu hệ thống quản lý bí mật chính gặp sự cố?
- Đường mạng dùng để restore có độc lập với đường mạng vừa hỏng?
- Standby có đủ CPU, bộ nhớ, I/O và kết nối để nhận toàn bộ tải production?

Cùng một tòa nhà nhưng khác phòng máy có thể xử lý được một số sự cố cục bộ; không nên mặc định cấu hình đó bảo vệ được trước việc mất toàn bộ tòa nhà.

## 5. Thiết kế backup để có thể khôi phục

### 5.1. Restore, recover và point-in-time recovery

Ba khái niệm cần phân biệt:

- **Restore**: đưa file dữ liệu từ backup trở lại nơi khôi phục.
- **Recover**: áp dụng incremental backup và/hoặc redo cần thiết để đưa các file đến trạng thái nhất quán mong muốn.
- **Point-in-time recovery — PITR**: khôi phục tới một thời điểm hoặc SCN được lựa chọn, thường trước một thay đổi sai.

Có file backup không có nghĩa có thể khôi phục đến mọi thời điểm. Điểm đích còn phụ thuộc chuỗi backup, redo còn giữ, metadata và khả năng giải mã.

RMAN phân biệt incremental level 0, level 1 differential và level 1 cumulative. Level 0 làm nền cho incremental; differential lấy các block thay đổi từ incremental level 0 hoặc level 1 gần nhất, còn cumulative lấy thay đổi từ level 0 gần nhất. Khi recovery, RMAN có thể dùng incremental và redo phù hợp. [Hướng dẫn backup và recovery của Oracle Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/admqs/performing-backup-and-recovery.html).

Một **full backup thông thường** không tự trở thành level 0 trong chiến lược incremental. Khi mô tả thiết kế hoặc đọc log, cần dùng đúng loại backup thay vì gọi mọi bản chứa dữ liệu đầy đủ là “full”.

### 5.2. Chính sách phải bao gồm cả dữ liệu và redo

Một chính sách minh họa cho môi trường do nhóm tự quản lý:

| Thành phần | Phương án minh họa | Điều cần chứng minh |
| --- | --- | --- |
| Nền incremental | Level 0 định kỳ | Có bản nền sử dụng được cho điểm khôi phục cần thiết |
| Thay đổi dữ liệu | Level 1 giữa các lần level 0 | Đọc được các bản cần dùng trong chuỗi |
| Archived redo log | Sao lưu đủ thường xuyên theo RPO | Có redo nối tiếp đến điểm khôi phục mục tiêu |
| Metadata khôi phục | Control file, SPFILE và thông tin nhận diện database | Có thể xác định và truy cập backup khi môi trường gốc mất |
| Khóa mã hóa | Giữ keystore/khóa cần thiết theo cơ chế quản lý khóa đang dùng | Có thể giải mã dữ liệu và backup tại nơi khôi phục |
| Kiểm chứng | Validation và restore/recovery diễn tập | Đạt điểm dữ liệu và thời gian đã cam kết |

Bảng này là khung thiết kế. Lịch backup được quản lý bởi dịch vụ có thể khác; không tự thay lịch hoặc ghi đè cấu hình do automation của dịch vụ sở hữu.

Nếu chỉ backup dữ liệu mỗi đêm nhưng thiếu các redo cần thiết trong ngày, không thể lấy tần suất backup đêm làm bằng chứng đạt RPO vài phút.

Ngược lại, giữ rất nhiều archived log nhưng mất bản nền hoặc khóa mã hóa vẫn có thể khiến quy trình khôi phục không thực hiện được.

### 5.3. Chọn đích backup cho Cloud@Customer

Tài liệu Cloud@Customer mô tả các đích gồm OCI Object Storage, NFS, Zero Data Loss Recovery Appliance (ZDLRA) và lưu trữ cục bộ, tùy phương thức backup. Các đích NFS hoặc ZDLRA do khách hàng quản lý cần được cấu hình để các VM cluster node truy cập được. [Quản lý backup và recovery trên Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-manage-db-backup-and-recovery.html).

Đánh giá từng lựa chọn theo đặc tính vận hành:

| Đích | Điểm cần đánh giá |
| --- | --- |
| OCI Object Storage | Tuyến mạng, DNS, quyền truy cập, thời gian truyền dữ liệu và phạm vi lưu dữ liệu đã thống nhất |
| NFS | Năng lực máy chủ NFS, throughput, quyền mount và mức độc lập với hạ tầng production |
| ZDLRA | Năng lực appliance, chính sách bảo vệ, kết nối và quy trình restore phù hợp môi trường |
| Lưu cục bộ/FRA khi phương án hỗ trợ | Dung lượng, tốc độ recovery tại chỗ và rủi ro mất cùng hạ tầng nguồn |

FRA — Fast Recovery Area — là vùng quản lý các file phục vụ recovery. FRA nằm trên cùng hệ thống lưu trữ với production không tạo ra bản bảo vệ độc lập trước việc mất toàn bộ hệ thống đó.

Với Object Storage trên OCI, Cloud@Customer cần kết nối đi ra dịch vụ Object Storage theo điều kiện được tài liệu hóa. Việc database đặt trong trung tâm dữ liệu khách hàng không bảo đảm backup cũng chỉ nằm tại đó. [Quản lý database trên Cloud@Customer](https://docs.oracle.com/en/engineered-systems/exadata-cloud-at-customer/ecccm/ecc-manage-databases.html).

### 5.4. Retention, khả năng khôi phục và chính sách xóa

Recovery window mô tả khoảng thời gian cần có khả năng recovery; không nên diễn giải thành “xóa tất cả file cũ hơn N ngày”. Một backup nền cũ hơn đầu cửa sổ vẫn có thể cần thiết để khôi phục một thời điểm bên trong cửa sổ.

Ba chính sách phải nhất quán:

1. Chính sách giữ backup để đạt recovery window.
2. Chính sách giữ hoặc xóa archived log để phục vụ cả recovery và các standby cần thiết.
3. Chính sách vòng đời, thời hạn giữ và quyền xóa tại nơi lưu backup.

Không dùng tác vụ xóa file theo tuổi trên hệ điều hành để thay thế việc xác định file còn cần cho recovery. Trong dịch vụ được quản lý, tuân theo cơ chế retention và cleanup được hỗ trợ.

Cũng cần dự trù backup thất bại nhiều ngày, standby gián đoạn mạng hoặc đợt phát sinh redo lớn. Một hệ thống chỉ đủ dung lượng trong ngày bình thường dễ rơi vào vòng lặp: backup lỗi, log tích lại, FRA cạn, rồi ảnh hưởng đến dịch vụ.

### 5.5. Khóa và cấu hình là một phần của khả năng phục hồi

Runbook cần mô tả nơi lấy và cách sử dụng:

- Khóa TDE/keystore cần cho dữ liệu và các khóa cũ còn liên quan.
- Khóa hoặc mật khẩu mã hóa backup nếu dùng cơ chế riêng.
- Cấu hình kết nối, wallet, thông tin đích backup và metadata cần thiết.
- Thông tin nhận diện database, Oracle home phù hợp và cấu hình dịch vụ ứng dụng.

Không đặt toàn bộ bí mật khôi phục vào chính database đang được bảo vệ. Cần một đường truy cập dự phòng có kiểm soát, audit và người chịu trách nhiệm rõ ràng.

Một bản backup được giữ lâu hơn vòng đời khóa có thể không còn hữu dụng. Khi xoay khóa, thay đổi quyền hoặc chuyển đích backup, phải kiểm chứng đường khôi phục tương ứng.

## 6. Kiểm chứng backup bằng RMAN và restore diễn tập

### 6.1. Phân biệt các mức bằng chứng

| Mức kiểm chứng | Bằng chứng cung cấp | Phần còn phải kiểm tra |
| --- | --- | --- |
| Tác vụ backup báo thành công | Tác vụ đã hoàn tất theo công cụ | Đọc lại dữ liệu, đủ chuỗi recovery, đủ khóa |
| RMAN validation | Phát hiện một số lỗi file hoặc block, kiểm tra khả năng đọc backup theo lệnh | Môi trường restore thực và kết quả nghiệp vụ |
| Restore và recover biệt lập | Chứng minh phục hồi được đến điểm đã chọn | Năng lực khi toàn site mất và ứng dụng chuyển địa điểm |
| Diễn tập dịch vụ đầy đủ | Đo cả database, mạng, ứng dụng và đối soát | Những sự cố khác chưa được diễn tập |

RMAN hỗ trợ các lệnh validation cho file dữ liệu và backup; validation không thực hiện thay toàn bộ quá trình restore và mở ứng dụng. [Tài liệu RMAN validation](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/validating-database-files-backups.html).

### 6.2. Ví dụ quan sát và validation

Ví dụ dưới đây dành cho phiên RMAN đã kết nối đúng database và có quyền phù hợp:

~~~text
RMAN> SHOW ALL;
RMAN> LIST BACKUP SUMMARY;
RMAN> RESTORE DATABASE VALIDATE;
~~~

- `SHOW ALL` giúp xem cấu hình hiện tại.
- `LIST BACKUP SUMMARY` giúp xem metadata về backup.
- `RESTORE DATABASE VALIDATE` kiểm tra các backup được RMAN chọn cho thao tác restore database; lệnh không restore datafile thực.

Không suy ra khả năng PITR đến mọi thời điểm chỉ từ một lần `RESTORE DATABASE VALIDATE`. Archived log, điểm đích, các khóa và môi trường khôi phục cần được kiểm chứng riêng.

Validation có thể đọc lượng dữ liệu lớn. Xếp lịch và giám sát I/O, thay vì coi đây là thao tác không có tác động hiệu năng.

### 6.3. Một lần restore diễn tập cần ghi nhận gì?

Chọn một thời điểm cần khôi phục nằm trong recovery window, rồi thực hiện trên môi trường biệt lập:

1. Ghi điểm đích bằng timestamp có múi giờ hoặc SCN đã xác định.
2. Chuẩn bị compute, storage, phần mềm, quyền truy cập và khóa.
3. Restore và recover theo phương thức được hỗ trợ của dịch vụ.
4. Mở database thử nghiệm theo quy trình phù hợp.
5. Xác nhận các PDB cần dùng, tài khoản ứng dụng và đối tượng nghiệp vụ.
6. Kiểm tra dữ liệu tại điểm đích và thực hiện giao dịch thử trên bản phục hồi.
7. Đo thời gian từng giai đoạn và ghi nhận lỗi hoặc thao tác thủ công.

Bản phục hồi thử phải tách khỏi tích hợp production: gửi email, thanh toán, xử lý hàng đợi và tác vụ định kỳ. Đây là điều kiện để phép thử không phát sinh giao dịch bên ngoài ngoài ý muốn.

## 7. Data Guard hoạt động như thế nào?

### 7.1. Đường đi của redo

Trong cấu hình physical standby điển hình:

~~~text
Giao dịch trên primary
    -> tạo redo
    -> redo transport tới standby
    -> ghi nhận redo tại standby
    -> redo apply cập nhật standby datafile
~~~

Data Guard duy trì một database khác với primary bằng redo. Đây là điểm khác với RAC, nơi nhiều instance cùng phục vụ một database.

**Standby redo log — SRL** hỗ trợ nhận redo; real-time apply có thể áp dụng redo từ SRL mà không phải chờ toàn bộ log được archive. Với RAC, cần tính tất cả redo thread có thể phát sinh và chuẩn bị cho cả hai hướng sau khi chuyển vai trò. Tài liệu Oracle mô tả yêu cầu về số lượng và kích thước SRL theo redo source. [Redo transport services](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/oracle-data-guard-redo-transport-services.html).

Khi dịch vụ tự tạo Data Guard, dùng luồng cấu hình được dịch vụ hỗ trợ. Không chỉnh đồng thời bằng Console, script tự viết và lệnh database mà không biết thành phần nào sở hữu cấu hình.

### 7.2. Transport lag và apply lag

- **Transport lag**: mức trễ của redo tại đích so với redo được tạo ở nguồn.
- **Apply lag**: mức trễ của trạng thái dữ liệu được apply tại standby so với nguồn.

Transport lag nhỏ nhưng apply lag tăng có thể gợi ý nút thắt ở khâu apply, tài nguyên hoặc I/O. Transport lag tăng có thể liên quan đường mạng, kết nối, lỗi đích hoặc tải vượt năng lực truyền.

Cần xem độ mới của phép đo. `V$DATAGUARD_STATS` cung cấp `TIME_COMPUTED` và `DATUM_TIME`; `DATUM_TIME` không thay đổi qua nhiều lần đọc có thể cho thấy standby không nhận thông tin mới từ nguồn. View này không trả các hàng thống kê tương ứng khi truy vấn trên primary. [Tham chiếu V$DATAGUARD_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAGUARD_STATS.html).

Một dashboard hiện lag bằng 0 nhưng dữ liệu đo đã cũ không đủ chứng minh DR đang khỏe.

### 7.3. SYNC, ASYNC và các protection mode

ASYNC tránh việc commit chờ xác nhận redo từ standby; đổi lại, primary có thể mất trước khi redo mới nhất tới đích. SYNC có thể tăng độ trễ commit do chờ xác nhận từ xa.

| Protection mode | Đặc điểm chính | Đánh đổi |
| --- | --- | --- |
| Maximum Performance | Thường dùng ASYNC | Có nguy cơ mất phần redo chưa được bảo vệ tại standby |
| Maximum Availability | Dùng cơ chế đồng bộ phù hợp khi standby đáp ứng điều kiện | Primary có thể tiếp tục khi mất khả năng đồng bộ, làm thay đổi mức bảo vệ thực tế |
| Maximum Protection | Yêu cầu điều kiện bảo vệ đồng bộ nghiêm ngặt | Primary dừng nếu không còn standby đồng bộ đáp ứng yêu cầu |

Với SYNC cần phân biệt **AFFIRM** — xác nhận sau khi redo được ghi xuống lưu trữ — và **NOAFFIRM/FastSync** — không chờ bước ghi bền vững tương tự. Không dùng nhãn “SYNC” để tự kết luận không mất dữ liệu trong mọi tổ hợp sự cố. [Data Guard protection modes](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/oracle-data-guard-protection-modes.html).

Chọn mode phải dựa trên yêu cầu mất dữ liệu, độ trễ ứng dụng và khả năng giữ kết nối. Đồng thời xác nhận mode và tùy chọn được hỗ trợ bởi dịch vụ đang dùng; các khả năng của Oracle Database không mặc nhiên đều được cung cấp qua mọi luồng cloud.

### 7.4. Data Guard và Active Data Guard

Physical standby có thể phục vụ mục tiêu DR mà không cần được ứng dụng dùng để báo cáo. Active Data Guard bổ sung các khả năng, trong đó có truy vấn read-only trong khi apply redo theo cấu hình được hỗ trợ.

Quyền sử dụng phụ thuộc edition, mô hình license và dịch vụ. Trước khi đưa truy vấn báo cáo lên standby, xác nhận entitlement và kiểm tra ảnh hưởng đến apply cũng như khả năng nhận tải khi DR.

Một standby bận xử lý báo cáo vẫn phải được đánh giá như nơi có thể trở thành production. Tiết kiệm tài nguyên đến mức không đủ nhận tải khi chuyển vai trò sẽ làm RTO và chất lượng phục vụ xấu đi.

## 8. Năng lực mạng và tốc độ bắt kịp

Thông lượng mạng danh nghĩa không phải thông lượng redo hữu dụng. Cần đo sau khi tính overhead, mã hóa, cạnh tranh băng thông và giới hạn xử lý ở hai đầu.

Giả sử trong một khoảng tải tương đối ổn định:

- Primary tạo 100 MB redo mỗi giây.
- Đường truyền có thể chuyển hữu dụng 140 MB mỗi giây.
- Sau gián đoạn, còn backlog 120 GB.
- Dùng đơn vị thập phân trong phép tính: 120 GB = 120.000 MB.

Khi redo mới vẫn tiếp tục sinh ra:

~~~text
Năng lực xóa backlog = 140 - 100 = 40 MB/s

Thời gian truyền bù tối thiểu
    = 120.000 / 40
    = 3.000 giây
    = 50 phút
~~~

Đây chỉ là ước lượng cho khâu truyền. Nó chưa bao gồm giới hạn đọc archived log, ghi SRL, redo apply, độ biến động tải và gián đoạn khác.

Nếu thông lượng hữu dụng chỉ là 100 MB/s trong khi redo cũng sinh 100 MB/s, backlog không giảm theo mô hình này. Nếu thấp hơn tốc độ sinh redo, backlog tiếp tục tăng.

Khi thiết kế mạng trong OCI hoặc giữa Cloud@Customer với địa điểm DR, phải kiểm tra tuyến hai chiều, DNS, quy tắc mạng, firewall phía khách hàng và khả năng kết nối sau chuyển vai trò. Đường đi primary đến standby hoạt động không bảo đảm đường đi ngược lại đã sẵn sàng.

Với SYNC, đo thêm độ trễ commit của ứng dụng tại tải đỉnh. Một bài kiểm tra truyền file lớn không phản ánh đầy đủ ảnh hưởng của xác nhận redo lên giao dịch nhỏ, liên tục.

## 9. Switchover, failover và khôi phục lại mức bảo vệ

### 9.1. Switchover

Switchover là chuyển vai trò có kế hoạch khi các database còn có thể phối hợp: primary trở thành standby và standby trở thành primary.

Các bước vận hành nên bao gồm:

1. Xác nhận cấu hình khỏe, đủ redo và đích sẵn sàng chuyển vai trò.
2. Kiểm tra tài nguyên, dịch vụ và đường kết nối ứng dụng tại địa điểm đích.
3. Điều phối giao dịch và tác vụ nền theo phương án của ứng dụng.
4. Thực hiện switchover bằng công cụ được hỗ trợ.
5. Xác nhận role mới và hướng redo mới.
6. Kiểm tra giao dịch nghiệp vụ, backup và cảnh báo sau chuyển đổi.

Switchover hữu ích cho bảo trì và diễn tập DR. Nó không chứng minh đầy đủ hành vi khi primary biến mất đột ngột.

### 9.2. Failover

Failover đưa standby lên primary khi không thể tiếp tục dùng primary theo quy trình bình thường. Kết quả mất dữ liệu phụ thuộc redo có thể thu hồi và trạng thái bảo vệ tại thời điểm sự cố.

Trước quyết định failover cần xác định:

- Primary thực sự không phục vụ được, hay chỉ mất một đường giám sát?
- Standby còn redo chưa apply và có thể lấy thêm redo từ nguồn nào?
- Mức mất dữ liệu ước lượng có nằm trong thẩm quyền chấp nhận?
- Có cách ngăn primary cũ tiếp tục nhận giao dịch khi kết nối hồi phục?
- Ứng dụng, hàng đợi và tích hợp ngoài database sẽ được điều phối thế nào?

Không mở lại primary cũ để ứng dụng ghi độc lập sau khi standby đã trở thành primary. Cần quy trình cách ly và xác định nguồn dữ liệu có thẩm quyền để tránh hai nhánh giao dịch không nhất quán.

### 9.3. Reinstate, rebuild và trở lại địa điểm cũ

Sau failover, primary cũ có thể cần **reinstate** thành standby hoặc phải tạo lại standby. Khả năng reinstate phụ thuộc điều kiện như Flashback Database, lịch sử cần thiết và trạng thái cấu hình; không phải thao tác luôn thành công.

Data Guard Broker mô tả cơ chế chuyển vai trò và reinstate, bao gồm các điều kiện liên quan Flashback. [Switchover và failover với Broker](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/using-data-guard-broker-to-manage-switchovers-failovers.html).

Việc ứng dụng đã chạy tại địa điểm B chưa kết thúc công việc. Phải phục hồi mức bảo vệ cho primary mới: standby, backup, giám sát, quyền và lịch diễn tập.

Khi muốn quay lại A, trước hết xây dựng lại trạng thái bảo vệ và đồng bộ; sau đó lập một switchover có kế hoạch. Không xem “failback” là việc đổi DNS trở lại máy cũ.

## 10. Data Guard Broker và tự động hóa failover

### 10.1. Quan sát bằng Broker

Nếu cấu hình có Data Guard Broker và chính sách dịch vụ cho phép, có thể kiểm tra bằng DGMGRL. Trong ví dụ, `SALES_A` và `SALES_B` là `DB_UNIQUE_NAME` giả định:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'SALES_A';
DGMGRL> SHOW DATABASE VERBOSE 'SALES_B';
DGMGRL> VALIDATE DATABASE VERBOSE 'SALES_B';
~~~

Đọc các lỗi, cảnh báo và kết quả readiness; không chỉ nhìn dòng tổng kết đầu ra. Các lệnh, quyền và tùy chọn cần đối chiếu đúng phiên bản. [Tham chiếu lệnh DGMGRL](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/oracle-data-guard-broker-commands.html).

Với dịch vụ đang quản lý role transition qua Console/API, các lệnh trên chỉ minh họa lớp database; không phải chỉ dẫn thực hiện thay đổi ngoài luồng quản lý của dịch vụ.

### 10.2. Fast-Start Failover và observer

Fast-Start Failover — FSFO — dùng Broker cùng observer và các điều kiện đã cấu hình để tự động chuyển vai trò trong các trường hợp phù hợp.

Observer nên có mức độc lập vận hành phù hợp với hai địa điểm database. Nếu observer mất cùng primary, kiến trúc sẽ mất một thành phần quan sát đúng lúc cần quyết định.

Thiết kế FSFO phải nêu rõ:

- Đích failover và điều kiện đủ để chuyển.
- Ngưỡng thời gian, lag và các điều kiện sức khỏe được sử dụng.
- Cách xử lý network partition và primary cũ.
- Theo dõi observer, thông tin xác thực và khả năng kết nối.
- Phương án chuyển service của ứng dụng.
- Ai xử lý khi tự động hóa không thực hiện được.

Không thay Broker bằng script “ping không trả lời thì promote standby”. Một điểm kiểm tra mạng đơn lẻ không thể xác định đầy đủ trạng thái database và mức bảo vệ dữ liệu.

FSFO cũng không tự giải quyết kết nối của mọi ứng dụng, giao dịch với hệ thống ngoài hay quyết định khôi phục dữ liệu nghiệp vụ bị sửa sai.

## 11. Giám sát để phát hiện mất bảo vệ trước khi xảy ra thảm họa

### 11.1. Các tín hiệu cần theo dõi

| Nhóm | Tín hiệu | Ý nghĩa vận hành |
| --- | --- | --- |
| Backup | Lần thành công cuối, lỗi tác vụ, thời gian chạy, dung lượng | Phát hiện khoảng bảo vệ bị gián đoạn |
| Recovery | Kết quả validation, lần restore diễn tập gần nhất, điểm đích đạt được | Đánh giá khả năng khôi phục có bằng chứng |
| Data Guard | Transport lag, apply lag, redo gap, lỗi transport/apply | Phát hiện standby đang tụt lại |
| Mức bảo vệ | Mode cấu hình và trạng thái bảo vệ thực tế | Phát hiện tình trạng cấu hình mong muốn khác thực tế |
| Dung lượng | FRA, ASM, đích backup, tăng trưởng archived log | Dự báo nghẽn hoặc cạn chỗ |
| Hạ tầng | Kết nối giữa site, DNS, tài nguyên standby | Phát hiện phụ thuộc có thể cản trở DR |
| Ứng dụng | Lỗi kết nối, timeout, giao dịch thử | Đo khả năng phục vụ thay vì chỉ trạng thái database |

Mỗi cảnh báo cần người nhận và hướng xử lý. Trong OCI, gắn alarm và thông báo với nhóm vận hành phù hợp, đồng thời duy trì lịch sử để đánh giá các khoảng mất bảo vệ.

Ngưỡng minh họa cho mục tiêu RPO 5 phút: cảnh báo sớm khi transport lag vượt 60 giây liên tục hoặc khi dữ liệu đo bị cũ; tăng mức xử lý trước khi độ trễ tiến tới giới hạn 5 phút. Đây là giá trị thiết kế giả định, cần điều chỉnh theo workload và chất lượng phép đo.

### 11.2. Ví dụ truy vấn chỉ đọc

Trên database cần xác định vai trò:

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

Trên physical standby, kiểm tra lag và thời điểm dữ liệu nguồn:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Cần quyền đọc các dynamic performance view phù hợp. Với database đa tenant, xác định đúng container và phạm vi quyền trước khi diễn giải kết quả.

Các câu lệnh chỉ là một phần quan sát. Không kết luận standby sẵn sàng failover chỉ từ giá trị của một cột; kết hợp Broker, log, trạng thái transport/apply và kiểm tra dịch vụ.

## 12. Quy trình xử lý sự cố theo loại nguyên nhân

### 12.1. Một instance hoặc node gặp lỗi

Ưu tiên xác định phạm vi lỗi và tình trạng các instance còn lại. Kiểm tra tài nguyên, service, phiên ứng dụng và cơ chế kết nối lại.

Nếu database vẫn được cụm phục vụ đúng và đáp ứng yêu cầu, không tự động nâng sự cố thành failover sang địa điểm DR. Chuyển site không cần thiết có thể tăng gián đoạn và độ phức tạp.

Trong thời gian sửa node, tiếp tục giám sát backup và standby. Một hệ thống đang mất dự phòng cục bộ cần được theo dõi chặt hơn.

### 12.2. Mất toàn bộ địa điểm primary

Một runbook khung:

1. Ghi nhận thời điểm bắt đầu, triệu chứng và phạm vi mất kết nối.
2. Xác minh tình trạng primary từ các tín hiệu độc lập còn truy cập được.
3. Xác định standby tốt nhất, độ mới dữ liệu và redo có thể thu hồi.
4. Thực hiện quyết định failover theo thẩm quyền hoặc theo FSFO đã phê duyệt.
5. Bảo đảm primary cũ không tiếp tục nhận giao dịch độc lập.
6. Chuyển service/định tuyến và làm mới các kết nối ứng dụng.
7. Kiểm tra đọc, ghi, hàng đợi và tích hợp quan trọng.
8. Ghi RPO/RTO thực đo, dữ liệu chưa xác nhận và các phần phải đối soát.
9. Khôi phục backup và standby cho primary mới.

Khi primary không còn truy cập, có thể chưa biết chính xác giao dịch nào thiếu chỉ từ một con số lag. Cần phối hợp dữ liệu database với nhật ký giao dịch và mã định danh nghiệp vụ để đối soát.

### 12.3. Xóa hoặc sửa sai dữ liệu

Đầu tiên phải ngăn lỗi tiếp tục xảy ra: dừng tác vụ sai hoặc cô lập đường ghi liên quan theo phạm vi cần thiết.

Sau đó:

1. Xác định thời điểm và phạm vi thay đổi sai.
2. Kiểm tra standby đã apply thay đổi đó chưa; không mặc định standby còn dữ liệu đúng.
3. Chọn Flashback, PITR hoặc restore biệt lập theo khả năng và phạm vi ảnh hưởng.
4. Nếu khôi phục biệt lập, trích dữ liệu cần thiết và đối soát với production.
5. Lập cách đưa dữ liệu đúng trở lại mà không phá các giao dịch hợp lệ khác.
6. Kiểm tra ràng buộc, số liệu nghiệp vụ và tích hợp sau sửa.

Có thể thiết kế standby apply trễ cho một số mục tiêu bảo vệ lỗi người dùng, nhưng độ trễ đó cũng ảnh hưởng độ mới dữ liệu và thời gian chuyển vai trò. Không thay backup bằng một standby cố ý trễ.

### 12.4. Backup lỗi và FRA tăng nhanh

Không xóa ngay archived log chỉ để giải phóng chỗ. Xác định vì sao chúng còn cần: backup chưa hoàn tất, standby chưa nhận/áp dụng theo chính sách, hoặc thiếu chuỗi recovery.

Hướng xử lý có thể gồm sửa đích backup, sửa kết nối, khôi phục tiến trình liên quan, tăng dung lượng có kiểm soát và áp dụng cleanup theo cơ chế được hỗ trợ. Mọi quyết định xóa làm thay đổi khả năng recovery phải được đánh giá theo điểm khôi phục còn bảo vệ được.

## 13. Ứng dụng Java phải tham gia thiết kế sẵn sàng

Với ứng dụng Java chạy trên Compute, Kubernetes hoặc hạ tầng khách hàng, database role transition mới là một phần của chuỗi phục hồi.

Cần thiết kế và thử nghiệm:

- Dùng database service phục vụ đúng vai trò, tránh gắn ứng dụng vào hostname của một node cố định.
- Cấu hình connect timeout, read timeout và thời hạn chờ nghiệp vụ hợp lý.
- Để connection pool phát hiện, loại bỏ và tạo lại kết nối không còn hợp lệ.
- Kiểm tra cơ chế FAN, Application Continuity hoặc Transaction Guard nếu stack và quyền sử dụng hỗ trợ.
- Dùng mã nghiệp vụ/idempotency key khi thao tác có thể được gửi lại.
- Chuyển các tác vụ nền và tích hợp liên quan cùng với dịch vụ database.

Tình huống đặc biệt quan trọng: ứng dụng gửi commit, kết nối đứt trước khi nhận phản hồi. Giao dịch có thể đã commit hoặc chưa. Retry mù một thao tác trừ tiền hoặc tạo đơn có thể tạo giao dịch trùng.

Do đó phép thử DR cần có giao dịch đang chạy, không chỉ các câu SELECT sau khi database mới mở. Đo thời gian người dùng thực hiện lại nghiệp vụ thành công và kiểm tra kết quả cuối cùng.

Ví dụ bằng chứng ứng dụng sau chuyển vai trò:

| Phép thử | Điều kiện đạt |
| --- | --- |
| Tạo đơn có mã yêu cầu duy nhất | Có đúng một đơn, không bị nhân đôi khi kết nối lại |
| Đọc đơn trước sự cố | Dữ liệu phù hợp điểm khôi phục được xác nhận |
| Ghi giao dịch mới | Ghi vào primary mới và có thể đọc lại |
| Tác vụ nền | Không chạy đồng thời ngoài ý muốn tại hai site |
| Backup sau chuyển vai trò | Chính sách tiếp tục bảo vệ database đang phục vụ |

## 14. Phân quyền, tự động hóa và kiểm soát chi phí

### 14.1. Tách quyền theo nhiệm vụ

Quyền IAM trong OCI và quyền bên trong Oracle Database là hai lớp khác nhau. Có quyền xem tài nguyên Exadata không có nghĩa có quyền chạy RMAN hoặc chuyển role trong database.

Một mô hình trách nhiệm có thể tách:

- Người quan sát sức khỏe và đọc log.
- Người quản lý lịch backup, retention và đích lưu.
- Người thực hiện recovery hoặc role transition.
- Người quản lý khóa.
- Người quản lý quyền xóa backup và thay đổi chính sách giữ.

Quyền đọc backup có thể cho phép tiếp cận dữ liệu nhạy cảm. Đồng thời, tài khoản quản trị production bị xâm phạm không nên dễ dàng xóa cả dữ liệu nguồn lẫn mọi bản lịch sử bảo vệ.

Trong Cloud@Customer, cần ghi rõ trách nhiệm giữa Oracle, nhóm hạ tầng khách hàng, nhóm mạng, DBA và nhóm ứng dụng. Việc nhà cung cấp quản lý thành phần hạ tầng không thay cho việc khách hàng xác nhận mục tiêu recovery và kết quả nghiệp vụ.

### 14.2. Tự động hóa có điều kiện kiểm tra

Một tác vụ kiểm tra định kỳ có thể thu thập:

~~~text
1. Nhận diện database và role hiện tại.
2. Lấy tình trạng backup và điểm bảo vệ gần nhất.
3. Lấy transport/apply lag cùng độ mới phép đo.
4. Kiểm tra dung lượng và tốc độ tăng.
5. So sánh với mục tiêu đã cấu hình.
6. Gửi cảnh báo có database, thời gian và bằng chứng liên quan.
~~~

Các script vận hành nên có timeout, log, kiểm tra kết quả và xử lý chạy lặp. Sau switchover, script phải tìm đúng role thay vì mặc định A luôn là primary.

Các thay đổi hạ tầng có thể quản lý bằng công cụ khai báo khi dịch vụ hỗ trợ. Trạng thái runtime như độ đồng bộ, dữ liệu chưa apply và kết quả nghiệp vụ vẫn cần kiểm tra tại thời điểm thao tác.

### 14.3. Chi phí gắn với mục tiêu bảo vệ

Các khoản cần đưa vào ước tính:

- Tài nguyên standby và khả năng cấp đủ tải khi DR.
- Dung lượng backup, archived log và vùng recovery.
- Kết nối giữa site, thông lượng backup/restore và chi phí truyền dữ liệu liên quan.
- Quyền sử dụng các tính năng được lựa chọn.
- Môi trường diễn tập, nhân lực vận hành và lưu bằng chứng.

Không giảm chi phí bằng cách ngừng giám sát hoặc bỏ restore diễn tập. Cách tối ưu có thể là phân hạng database theo mục tiêu, điều chỉnh retention có căn cứ và đo lại tài nguyên standby bằng tải thực tế.

Không sử dụng một con số giá hay danh sách quyền license cố định cho mọi topology. Cần tính theo dịch vụ, khu vực, mô hình thuê bao/BYOL và hợp đồng đang áp dụng.

## 15. Thực hành: lập và chứng minh phương án bảo vệ

### 15.1. Bối cảnh và điều kiện

Một hệ thống bán hàng giả định chạy trên Exadata Cloud@Customer tại địa điểm A. Doanh nghiệp yêu cầu:

- Mất site A: RPO không quá 5 phút, RTO không quá 30 phút.
- Có thể lấy lại dữ liệu trước lỗi người dùng được phát hiện trong 7 ngày.
- Bản backup phục vụ mất toàn site không cùng phụ thuộc vào hạ tầng A.

Thực hành trên môi trường thử đã được cấp quyền. Cần có primary, standby theo topology được hỗ trợ, backup có thể truy cập và một ứng dụng hoặc client thử giao dịch. Nếu chưa có hạ tầng, có thể hoàn thành phần thiết kế và tính toán; chưa được kết luận đã đạt RPO/RTO.

### 15.2. Trình tự thực hiện

1. **Vẽ bản đồ miền sự cố.** Ghi vị trí primary, standby, backup, khóa, observer nếu dùng, DNS và ứng dụng.
2. **Lập ma trận mục tiêu.** Tách lỗi node, mất site và lỗi dữ liệu nghiệp vụ.
3. **Đọc cấu hình hiện tại.** Kiểm tra backup, retention, role, transport mode, lag và dung lượng.
4. **Kiểm chứng backup.** Chọn một điểm đích, restore/recover biệt lập và kiểm tra dữ liệu thử.
5. **Diễn tập switchover.** Ghi mốc thời gian, chuyển role bằng luồng hỗ trợ và thử giao dịch ứng dụng.
6. **Kiểm tra hướng ngược.** Xác nhận redo, backup và cảnh báo làm việc với role mới.
7. **Diễn tập failover riêng nếu phạm vi thử cho phép.** Mô phỏng lỗi đã thống nhất, kiểm tra cô lập primary cũ và ghi mức dữ liệu phục hồi.
8. **Khôi phục trạng thái bảo vệ.** Reinstate hoặc tạo lại standby phù hợp, kiểm chứng rồi mới đóng diễn tập.

Không lấy kết quả bước switchover làm số liệu RTO của failover. Hai tình huống có điều kiện phối hợp và thời gian quyết định khác nhau.

### 15.3. Mẫu ghi kết quả

| Hạng mục | Nội dung phải ghi |
| --- | --- |
| Phạm vi | Database, phiên bản, topology và loại sự cố thử |
| Dữ liệu | Mã giao dịch thử, thời điểm commit và kết quả đối soát |
| Backup | Đích, điểm đích recovery, thời gian restore và recover |
| Data Guard | Role, mode, lag và độ mới phép đo trước thử |
| RTO | Thời điểm gián đoạn đến giao dịch nghiệp vụ thành công |
| RPO | Điểm dữ liệu được xác nhận và giới hạn của phép đo |
| Sau thử | Standby, backup và giám sát đã bảo vệ primary mới chưa |
| Vấn đề còn lại | Thao tác thủ công, thiếu quyền, thiếu tài nguyên hoặc sai định tuyến |

### 15.4. Ví dụ đánh giá

Giả sử một lần diễn tập mất site đo được:

~~~text
Phát hiện:                         2 phút
Đánh giá và quyết định:            4 phút
Chuyển vai trò và mở dịch vụ DB:   7 phút
Ứng dụng kết nối lại:              3 phút
Kiểm tra nghiệp vụ:                4 phút
Tổng:                            20 phút
~~~

Nếu khoảng dữ liệu thiếu được xác nhận là 90 giây, lần diễn tập đó đáp ứng mục tiêu RTO 30 phút và RPO 5 phút của kịch bản đã thử.

Nếu chưa xác nhận giao dịch cuối cùng có mặt ở đích, chỉ có thể báo thời gian phục hồi dịch vụ; chưa đủ bằng chứng kết luận RPO. Nếu backup chưa được restore thử, kết quả Data Guard cũng chưa chứng minh yêu cầu khôi phục lỗi người dùng trong 7 ngày.

## 16. Các nguyên tắc cần vận dụng

Một thiết kế bảo vệ Exadata có thể vận hành phải trả lời được bốn câu hỏi: **sự cố nào được bảo vệ, dữ liệu nào có thể mất, dịch vụ mất bao lâu và bằng chứng kiểm chứng nằm ở đâu**.

- RAC và dự phòng lưu trữ xử lý một số lỗi cục bộ; phải giữ khả năng phục vụ của ứng dụng khi kết nối gián đoạn.
- Data Guard tạo đường phục hồi ở database khác; phải theo dõi redo, role và mức bảo vệ thực tế.
- Backup tạo lịch sử recovery; phải giữ đủ chuỗi dữ liệu, redo, metadata và khóa.
- Khôi phục thành công phải bao gồm database, ứng dụng và đối soát nghiệp vụ.
- Sau mọi lần chuyển vai trò, phải thiết lập lại backup, standby và giám sát cho primary đang phục vụ.

Các nguyên tắc này nối việc triển khai OCI với vận hành thực tế: phân quyền đúng, mạng đủ năng lực, cảnh báo có người xử lý và chi phí tương ứng mục tiêu sẵn sàng.
