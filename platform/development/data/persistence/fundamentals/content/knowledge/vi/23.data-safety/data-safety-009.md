# Bảo vệ dữ liệu sao lưu và bản sao phục vụ kiểm thử

Một hệ thống có thể mã hóa kết nối đến cơ sở dữ liệu production, kiểm soát quyền truy cập rất chặt và ghi log đầy đủ, nhưng lại đặt một file sao lưu chứa mọi khách hàng vào bucket có thể tải công khai. Hoặc đội phát triển có thể sao chép database production sang môi trường kiểm thử với tài khoản dùng chung và vô tình gửi email thật cho khách hàng. Những tình huống đó cho thấy **dữ liệu sao lưu (backup) và bản sao phục vụ kiểm thử (test copy)** là những bề mặt rủi ro độc lập, không tự được bảo vệ chỉ vì database gốc an toàn.

Bản sao lưu giúp phục hồi trước hỏng phần cứng, lỗi con người, xóa nhầm, tấn công mã độc và sự cố triển khai; nó có thể tồn tại lâu, nằm ở nhiều địa điểm và chứa những dữ liệu đã bị xóa khỏi hệ thống chính. Bản sao phục vụ kiểm thử giúp tái hiện lỗi, đo hiệu năng và kiểm thử schema migration; nhưng nếu sao chép dữ liệu thật sang môi trường ít được bảo vệ hơn, nó có thể mở đường cho truy cập trái phép, lộ bí mật, vi phạm giới hạn sử dụng dữ liệu hoặc kích hoạt tác dụng phụ không mong muốn.

Bài thuộc chương **An toàn dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung gắn bảo mật với persistence trong Java: mô hình dữ liệu và lược đồ, transaction và tính bền vững, quản lý kết nối, backup/restore, tiến hóa schema, phân quyền, xử lý lỗi và vận hành. Trọng tâm là bảo vệ dữ liệu **trước, trong và sau** khi tạo bản sao, đồng thời chứng minh khả năng khôi phục và chất lượng dữ liệu kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **backup**, **replica**, **snapshot**, **database dump**, **test clone** và **dữ liệu tổng hợp (synthetic data)**.
2. Nhận diện rủi ro mất tính bí mật, toàn vẹn, sẵn sàng và khả năng khôi phục của bản sao lưu.
3. Thiết kế bảo vệ nhiều lớp: quyền tối thiểu, mã hóa, quản lý khóa, phân tách môi trường, sao lưu bất biến và giám sát.
4. Xác định mục tiêu **RPO**/**RTO** và phân biệt backup thành công với khôi phục thành công.
5. Giải thích sự khác nhau giữa sao lưu logic, vật lý, snapshot và khôi phục đến một thời điểm (PITR).
6. Thiết kế luồng tạo bản sao kiểm thử **cách ly → loại bỏ/biến đổi dữ liệu nhạy cảm → kiểm tra → cấp quyền sử dụng**.
7. Phân biệt masking, pseudonymization, anonymization, tokenization và dữ liệu tổng hợp; nhận biết nguy cơ tái định danh.
8. Giữ tính nhất quán tham chiếu và giá trị kiểm thử mà không đưa dữ liệu nhạy cảm không cần thiết vào môi trường test.
9. Thiết lập quy trình kiểm tra backup, restore drill, giới hạn lưu giữ và xử lý sự cố.
10. Đánh giá các ví dụ thực hành PostgreSQL và Java, chỉ áp dụng sau khi đã kiểm tra chính sách và quyền trên môi trường thực.

## 2. Tại sao bản sao dữ liệu là một tài sản có rủi ro riêng?

Giả sử hệ thống có bảng `customers`, `orders`, `payments` và `audit_logs`. Người dùng truy cập ứng dụng chỉ được xem đơn của chính mình, nhưng file backup vật lý có thể chứa **toàn bộ** bảng, cả dữ liệu của những tài khoản đã đóng và metadata không hiển thị qua API.

~~~text
                Production
          PostgreSQL + ứng dụng Java
                    |
         +----------+-----------+
         |          |           |
         v          v           v
  Backup/PITR    Read replica   Test clone
  nhiều ngày     gần real-time   tạo khi cần
         |          |           |
    Kho lưu trữ  truy vấn đọc   CI, QA, developer
    dài hạn      hoặc HA        môi trường khác
~~~

Ba nhánh có nhiệm vụ khác nhau:

| Hình thức | Mục tiêu | Rủi ro đáng chú ý |
|---|---|---|
| **Backup** | Khôi phục khi dữ liệu/hạ tầng bị mất hoặc sai | File bị đọc trái phép, bị xóa/mã hóa bởi attacker, backup hỏng, khóa giải mã bị mất |
| **Read replica** | Khả năng sẵn sàng hoặc mở rộng đọc | Lỗi/xóa nhầm ở primary có thể được nhân bản; replication không thay thế backup |
| **Test clone** | Phát triển, kiểm thử, benchmark, tái hiện lỗi | Production data lọt sang môi trường kém kiểm soát; tool gửi mail/webhook ra bên ngoài |
| **Snapshot** | Chụp trạng thái volume/VM/DB theo cơ chế nhà cung cấp | Snapshot thiếu tính nhất quán ứng dụng, quyền snapshot rộng, copy sang account khác |
| **Logical dump** | Trích xuất schema và dữ liệu qua SQL/format logic | Tệp có thể chứa toàn bộ PII, schema/role, dữ liệu lỗi thời hoặc thiếu các đối tượng cấp cluster |

**Một bản sao càng dễ truy cập để phục vụ công việc, càng cần xác định rõ dữ liệu nào được phép tồn tại trong đó.** Backup production giữ tính đầy đủ để có thể khôi phục; môi trường kiểm thử thường chỉ cần đặc tính dữ liệu đại diện, không nhất thiết cần danh tính thật của người dùng.

### 2.1. Tính chất bảo vệ không chỉ là “không bị đọc trộm”

Một hệ thống sao lưu an toàn phải bảo vệ:

- **Confidentiality – bí mật:** người không có quyền không thể xem nội dung backup hoặc bản sao kiểm thử.
- **Integrity – toàn vẹn:** nội dung backup không bị sửa, giả mạo hoặc hỏng âm thầm.
- **Availability – sẵn sàng:** bản sao cần thiết vẫn truy cập được khi database chính bị lỗi hoặc bị tấn công.
- **Recoverability – phục hồi được:** có thể khôi phục một trạng thái đúng và sử dụng được trong thời gian yêu cầu.
- **Accountability – truy vết:** biết ai tạo, tải, khôi phục, chia sẻ, biến đổi và xóa bản sao.
- **Data minimization – tối thiểu dữ liệu:** bản sao kiểm thử không chứa những thông tin thật mà mục tiêu test không cần.

Mã hóa chỉ giúp một phần của confidentiality; nó **không bảo đảm** backup chưa bị hỏng, công cụ restore đọc được file, khóa giải mã còn tồn tại hoặc người có quyền đã không sao chép dữ liệu ra ngoài.

## 3. Lập bản đồ dữ liệu và mô hình đe dọa

Trước khi mua công cụ backup hay viết script, cần biết **dữ liệu nào đang được sao chép, đi đến đâu, ai dùng và tồn tại bao lâu**.

Một danh mục tối thiểu nên có:

| Thuộc tính | Ví dụ câu hỏi |
|---|---|
| Nguồn | PostgreSQL primary nào? Database, schema và tenant nào? |
| Độ nhạy | PII, hồ sơ tài chính, token, password hash, log truy cập, dữ liệu nghiệp vụ? |
| Loại bản sao | Full backup, WAL archive, logical dump, snapshot, clone kiểm thử? |
| Chủ sở hữu | Nhóm nào chịu trách nhiệm nguồn, khóa giải mã và phục hồi? |
| Vị trí | Region, bucket, account, môi trường, thiết bị hoặc nhà cung cấp nào? |
| Quyền | Ai đọc, tải, xuất, restore, đổi retention hoặc xóa? |
| Vòng đời | Tạo khi nào, giữ bao lâu, có tự xóa hoặc legal hold không? |
| Phụ thuộc | Backup có cần sequence, role, extension, WAL, schema version, khóa ứng dụng? |
| Khả năng phục hồi | RPO/RTO cần đạt và lần restore drill gần nhất? |
| Điều kiện test | Có được dùng dữ liệu production? Cần masking trước cấp quyền nào? |

### 3.1. Các đường tấn công và lỗi phổ biến

1. **Kho backup công khai hoặc sai ACL:** một bucket hay file share bị cấu hình cấp quyền đọc quá rộng.
2. **Tài khoản backup bị chiếm:** kẻ tấn công lấy credential có quyền đọc/xóa/đổi retention.
3. **Mã độc trong cùng vùng tin cậy:** ransomware xóa cả dữ liệu chính và bản sao có thể ghi.
4. **Khóa mã hóa không được bảo vệ:** có backup mã hóa nhưng cả khóa và file cùng nằm trong một kho bị xâm nhập.
5. **Lộ từ máy phát triển/CI:** bản dump thật nằm trong thư mục làm việc, artifact của CI hoặc máy cá nhân.
6. **Rò dữ liệu qua môi trường test:** tài khoản demo, công cụ BI, email gateway, webhook hoặc log vô tình xử lý PII.
7. **Backup không khôi phục được:** file hỏng, thiếu WAL, không có key, thiếu extension hoặc phiên bản DB không hỗ trợ restore.
8. **Sao chép quá mức:** nhiều bản clone ở nhiều tenant/account, không còn ai biết vị trí và hạn lưu.
9. **Xóa chưa triệt để:** dữ liệu đã bị xóa ở production vẫn nằm trong snapshot, dump, cache và bản sao test.
10. **Tấn công chuỗi cung ứng:** script phục hồi hoặc job masking không được kiểm soát làm rò dữ liệu qua log hoặc đích gửi ngoài.

### 3.2. Đường tin cậy phải có ranh giới rõ

~~~mermaid
flowchart TD
    P["Production DB: dữ liệu có thẩm quyền"] --> B["Backup job trong vùng được kiểm soát"]
    B --> S["Kho backup mã hóa, quyền hẹp, retention/immutability"]
    S --> R["Vùng restore cách ly để kiểm tra phục hồi"]
    P --> C["Vùng xử lý clone hạn chế truy cập"]
    C --> M["Mask/minimize + kiểm thử rò rỉ dữ liệu"]
    M --> T["Test environment được phê duyệt"]
    T --> D["Dọn bản sao theo thời hạn"]
~~~

Điểm cần tránh là mũi tên trực tiếp từ production backup sang máy developer hoặc hệ test mở rộng khi chưa có phê duyệt, phân loại và xử lý thông tin nhạy cảm.

## 4. Chọn chiến lược sao lưu theo rủi ro và mục tiêu phục hồi

Không phải cứ giữ một file dump là đủ để phục hồi sau mọi loại sự cố. Cần hiểu backup bảo vệ điều gì và điểm nào có thể mất.

### 4.1. RPO và RTO

- **RPO – Recovery Point Objective:** lượng thay đổi dữ liệu tối đa có thể mất, thường biểu diễn bằng độ dài khoảng thời gian.
- **RTO – Recovery Time Objective:** thời gian mục tiêu để dịch vụ phục hồi tới mức vận hành đã định sau sự cố.

Ví dụ: backup toàn phần lúc 00:00 hằng ngày nhưng không có WAL/PITR. Nếu hệ thống lỗi lúc 17:00, phiên bản backup gần nhất có thể thiếu dữ liệu của 17 giờ. Mục tiêu RPO 5 phút sẽ **không đạt** chỉ nhờ bản backup hằng ngày.

Nếu restore một database 2 TB mất nhiều giờ, dù có bản backup rất mới, RTO 15 phút cũng khó đạt. Cần tính cả:

~~~text
RTO thực tế ≈ phát hiện + quyết định phục hồi
             + cấp hạ tầng + lấy khóa + đọc/khôi phục dữ liệu
             + replay log + chạy migration/kiểm tra + chuyển traffic
~~~

Công thức chỉ để chia các pha vận hành, không phải mô hình ước lượng chuẩn. RPO/RTO là **mục tiêu**, phải được chứng minh bằng bài diễn tập với dữ liệu và tài nguyên gần thực tế.

### 4.2. Các kiểu backup thường gặp

| Loại | Cơ chế | Phù hợp | Giới hạn |
|---|---|---|---|
| **Logical backup** | Xuất cấu trúc/hàng qua công cụ như `pg_dump` | Chuyển dữ liệu logic, khôi phục bảng/schema, kiểm thử migration | Restore lớn có thể chậm; không có PITR chỉ với dump |
| **Physical/base backup** | Sao chép dữ liệu vật lý theo giao thức/công cụ DBMS | Khôi phục cụm dữ liệu lớn, kết hợp WAL/PITR | Phụ thuộc DBMS, phiên bản và cách bố trí storage |
| **Snapshot hạ tầng** | Chụp volume/DB theo nền tảng | Phục hồi nhanh trong một số kiến trúc | Cần biết snapshot có nhất quán ứng dụng/đa-volume không |
| **WAL/log archive** | Lưu các bản ghi thay đổi sau base backup | Khôi phục đến thời điểm được phép | Cần chuỗi base backup + log đầy đủ và cấu hình khôi phục phù hợp |
| **Replica** | Áp dụng thay đổi từ primary | Sẵn sàng/đọc mở rộng | Lỗi logic hoặc DELETE có thể lan sang replica |

### 4.3. Backup logic và vật lý là các hợp đồng khác nhau

Với PostgreSQL, `pg_dump` tạo một bản sao logic của **một database** theo một snapshot nhất quán của database đó trong điều kiện công cụ hỗ trợ. Nó không tự bao gồm tất cả đối tượng cấp cluster, ví dụ roles hoặc một số cấu hình chung; phục hồi có thể cần thêm thông tin như extension, quyền và cấu hình môi trường.

`pg_basebackup` tạo bản base backup vật lý theo cơ chế PostgreSQL; kết hợp với WAL archive mới có thể xây chiến lược PITR. **Không dùng `pg_dump` như một bản thay thế tự nhiên cho base backup + WAL** khi yêu cầu phục hồi theo thời điểm.

Một snapshot file system của nhiều volume có thể cần phối hợp để đạt nhất quán theo trạng thái database; snapshot của một volume và snapshot của volume chứa WAL ở thời điểm khác nhau không mặc nhiên tạo một bản restore hợp lệ. Phải theo tài liệu và cơ chế backup do DBMS/nền tảng hỗ trợ.

### 4.4. Transaction nhất quán không bằng nghiệp vụ liên hệ thống nhất quán

Một snapshot PostgreSQL có thể nhất quán ở một database nhưng ứng dụng còn phụ thuộc:

- Object store lưu tệp đính kèm.
- Message broker lưu event.
- Database của service thanh toán.
- Search index và projection.
- Khóa mã hóa hoặc secret của một version khác.

Nếu bản khôi phục của các thành phần ở những thời điểm khác nhau, trạng thái toàn nghiệp vụ có thể cần đối soát. Hãy ghi nhận **điểm khôi phục theo từng tài nguyên** và kế hoạch phục hồi nhất quán ở cấp ứng dụng. Transaction cục bộ không tự biến nhiều hệ thống thành một backup nguyên tử.

## 5. Thiết kế các lớp bảo vệ backup

### 5.1. Nhiều bản sao và phân tách miền sự cố

Nguyên tắc thường dùng là có nhiều bản sao trên các miền lỗi khác nhau (ví dụ biến thể của **3-2-1**: ba bản dữ liệu, hai loại phương tiện, một bản ở vị trí khác). Tùy rủi ro, bổ sung bản **offline/immutable** và quy trình kiểm thử restore định kỳ.

Điểm quan trọng không nằm ở việc đếm số file, mà là **không để cùng một sự cố phá hủy mọi bản sao**:

- Một tài khoản bị chiếm không xóa được cả production và mọi backup.
- Một region mất điện không làm mất toàn bộ nơi lưu.
- Một lệnh xóa nhầm hoặc ransomware không làm mọi replica/backup biến mất.
- Một khóa mã hóa bị xóa không khiến mọi bản backup không thể giải mã.

Một file được copy thành ba tên trong cùng bucket, cùng account, cùng quyền xóa **không đủ phân tách rủi ro**.

### 5.2. Immutability và chống xóa trái phép

Một số kho lưu trữ hỗ trợ **object lock/WORM**, retention lock hoặc immutable snapshot. Khi sử dụng đúng cơ chế, chúng có thể ngăn sửa/xóa backup trước thời hạn theo chính sách.

Cần đánh giá:

- Ai có quyền tạo và thay retention policy?
- Chính sách có thể được rút ngắn/xóa bởi cùng admin bị chiếm không?
- Bản sao bất biến có được lưu tại account/vùng tin cậy riêng không?
- Thời hạn bất biến có phù hợp retention dữ liệu và yêu cầu xóa không?
- Chi phí lưu trữ, legal hold và quy trình phá hủy cuối kỳ là gì?

Không coi `read-only` tại hệ điều hành là tương đương WORM khi tài khoản bị chiếm vẫn có quyền thay permission, phá khóa hoặc xóa cả volume.

### 5.3. Mã hóa khi lưu và khi truyền

Cần bảo vệ các giai đoạn:

~~~text
DB --encrypted transport--> backup process
   --encrypted transport--> backup storage
   --encryption at rest--> bản lưu
   --TLS + access control--> restore environment
~~~

Có thể dùng mã hóa do nền tảng backup/storage quản lý hoặc một lớp mã hóa phía client. Trong nhiều trường hợp cần kết hợp cả hai, nhưng lựa chọn phải xét hiệu năng, khả năng restore và vận hành khóa.

**Quan trọng:** một bản dump plaintext trước khi được mã hóa và upload vẫn có thể lộ trên đĩa tạm, log, crash dump hoặc artifact CI. Ưu tiên đường xuất–mã hóa–truyền trực tiếp có kiểm soát, hoặc đảm bảo staging plaintext là nơi lưu tạm đã mã hóa, được giới hạn quyền và có xóa an toàn theo chính sách.

### 5.4. Quản lý khóa là một phần của khả năng phục hồi

Một backup mã hóa không thể phục hồi nếu:

- Khóa hoặc key version đã bị xóa.
- Restore identity không được phép gọi dịch vụ giải mã trong tình huống khẩn cấp.
- Key store nằm cùng miền sự cố với production.
- Quy trình rotate không giữ khả năng đọc backup cũ.
- Không ai có quyền thực hiện recovery khi người phụ trách không sẵn sàng.

Nên có:

1. KMS/HSM hoặc hệ thống quản lý khóa phù hợp.
2. Phân quyền tạo backup, quản trị khóa và khôi phục theo nguyên tắc tối thiểu.
3. Theo dõi key ID/version đã dùng cho mỗi tập backup.
4. Runbook cấp quyền khẩn cấp và thử restore giải mã.
5. Quy trình rotation/re-encryption và retention khóa phù hợp vòng đời backup.
6. Audit các thao tác sử dụng khóa bất thường.

**Rotation của key alias không đồng nghĩa mọi bản ciphertext cũ được mã hóa lại.** Nên hiểu cụ thể envelope encryption và chính sách version của nền tảng đang dùng.

## 6. Phân quyền, cách ly và nhật ký kiểm toán

### 6.1. Vai trò cần tách

| Vai trò | Quyền cần thiết | Quyền nên tránh |
|---|---|---|
| Backup writer | Đọc đúng nguồn, ghi vào nơi backup đã chỉ định | Xóa toàn bộ lịch sử backup, chia sẻ public, tự tắt audit |
| Backup verifier | Đọc metadata/checksum, thực hiện kiểm tra theo quyền | Đổi retention và đưa dữ liệu ra môi trường không kiểm soát |
| Restore operator | Khôi phục ở đích được phép, dùng khóa qua luồng kiểm soát | Tự ý restore production data vào laptop |
| Test data sanitizer | Đọc bản clone trong vùng cách ly để masking | Cấp quyền trực tiếp cho dev trước khi làm sạch |
| Developer/QA | Truy cập dữ liệu đã làm sạch, theo phạm vi công việc | Truy cập file production backup hoặc khóa giải mã |
| Security/auditor | Xem quyền, log, policy và trạng thái kiểm soát | Mặc định đọc toàn bộ dữ liệu khách hàng |

Đây là **tách nhiệm vụ theo rủi ro**, không bắt buộc mỗi dòng phải thuộc một người riêng ở nhóm nhỏ. Dù ít người, hành động rủi ro cao vẫn nên yêu cầu phê duyệt, có audit và dùng quyền tạm thời.

### 6.2. Backup operator không mặc nhiên là superuser

Quyền để lấy backup logic có thể khác với quyền để lấy physical backup hoặc backup trên hệ managed database. Không trao superuser hay owner của mọi object chỉ vì muốn “cho script chạy cho nhanh”.

Xác định loại backup, công cụ và quyền tối thiểu thực sự cần. Khi một công cụ yêu cầu quyền cao, nên:

- Dùng service identity riêng có vòng đời credential rõ.
- Hạn chế nguồn mạng, tài nguyên đích và thời gian quyền hiệu lực.
- Ghi audit, phát hiện credential bị sử dụng ngoài job.
- Tránh để mật khẩu trong command line, source code hoặc log.
- Rotation và thu hồi quyền ngay khi ngừng sử dụng.

### 6.3. Không đưa credential vào artifact và log

Những cách cần tránh:

~~~text
Sai: ghi connection URI chứa password vào file backup README.
Sai: hardcode password DB và key mã hóa trong script đã commit Git.
Sai: in toàn bộ biến môi trường khi job backup lỗi.
Sai: upload bản dump cùng file .env hoặc cấu hình secret lên CI artifacts.
Sai: đặt backup vào thư mục web server để “dễ tải”.
~~~

Với PostgreSQL CLI, có thể dùng cơ chế xác thực được cấp bởi nền tảng (ví dụ file pass/secret store được bảo vệ hoặc workload identity theo môi trường) và không truyền password như một chuỗi dễ lộ trong shell history.

### 6.4. Theo dõi những hành động cần audit

Ghi lại metadata có cấu trúc (không phải nội dung PII):

- Ai tạo hoặc yêu cầu tạo backup/test clone.
- Nguồn, đích, phân loại và mục đích sử dụng.
- Thời điểm, backup ID, phiên bản công cụ/schema và chính sách lưu.
- Thao tác đọc, download, chia sẻ, đổi ACL, đổi retention.
- Dùng khóa giải mã và các lần restore.
- Kết quả sanitization và người phê duyệt cho test.
- Hạn xóa, ngày xóa thật, kết quả restore drill.
- Các sự kiện truy cập bất thường và thất bại.

Audit log cũng phải có retention, quyền đọc và chống sửa phù hợp. Nếu log chứa đường dẫn hoặc identifier nhạy cảm, vẫn cần phân loại và bảo vệ.

## 7. Quy trình backup PostgreSQL: minh họa kỹ thuật, không phải runbook đầy đủ

Các lệnh trong phần này **chỉ minh họa** ở môi trường được cấp quyền. Không chạy trên production mà chưa kiểm tra chiến lược backup, đường dẫn đích, quyền, dung lượng, dữ liệu nhạy cảm và thời gian thực hiện.

### 7.1. Sao lưu logic một database

Ví dụ lệnh `pg_dump` ở terminal được quản lý bởi quy trình backup:

~~~bash
pg_dump \
  --dbname="service_db" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="/secure-backups/service-db.dump"
~~~

Điều kiện trước khi chạy:

- Kết nối tới host/port/identity phù hợp đã được cấp qua cấu hình an toàn; `--dbname` ở đây chỉ là tên minh họa.
- Thư mục `/secure-backups` phải có quyền hẹp, storage có mã hóa và chính sách chuyển sang kho backup được kiểm soát.
- File dump là **dữ liệu production nhạy cảm cho tới khi được xử lý**, ngay cả khi bỏ owner/ACL.
- `--no-owner` và `--no-acl` thay đổi thông tin phục hồi ownership/privileges, **không** làm sạch dữ liệu khách hàng.
- Backup custom format thích hợp cho `pg_restore`, nhưng không cho phép PITR như base backup + WAL.
- `pg_dump` không tự sao lưu tất cả role/global objects của cluster; cần kế hoạch riêng nếu restore cần chúng.

Bật `--no-owner --no-acl` có thể hữu ích cho restore sang môi trường mới khi quyền khác nhau, nhưng **không phải lựa chọn mặc định cho mọi backup khôi phục production** nếu cần bảo toàn đúng phân quyền. Phải phân biệt bản phục vụ restore production và bản phục vụ test.

### 7.2. Kiểm tra manifest và định dạng

Với custom-format dump, có thể kiểm tra cấu trúc danh mục:

~~~bash
pg_restore --list "/secure-backups/service-db.dump"
~~~

Lệnh này kiểm tra khả năng đọc danh mục dump, **không chứng minh** toàn bộ data blocks có thể restore, mọi constraint sẽ hợp lệ hoặc ứng dụng chạy thành công. Ngoài ra có thể lưu checksum, kích thước, backup ID, timestamp và phiên bản công cụ trong một manifest đã được bảo vệ.

Checksum giúp phát hiện thay đổi byte giữa thời điểm tạo và kiểm tra; **không chứng minh file đáng tin** nếu attacker có quyền sửa cả dump lẫn checksum. Với threat model phù hợp, dùng manifest có chữ ký hoặc integrity control mà tài khoản backup đơn lẻ không thể giả mạo.

### 7.3. Restore vào môi trường cách ly

Ví dụ minh họa sau khi đã tạo một database đích **mới, được phê duyệt và cách ly**, với chính sách phân quyền phù hợp:

~~~bash
pg_restore \
  --dbname="isolated_restore_db" \
  --no-owner \
  --no-acl \
  "/secure-backups/service-db.dump"
~~~

**Cảnh báo:** câu lệnh chỉ dùng sau khi đã xác minh đích. Một file dump có thể chứa đối tượng và dữ liệu nhạy cảm; restore có thể tạo object, extension hoặc chạy hành vi tại DB tùy nội dung và môi trường. Chỉ phục hồi bản được tin cậy, trên đích có kiểm soát, với role/quyền thấp phù hợp. Không chạy tùy tiện các tùy chọn `--clean`, `--create` hoặc kết nối đến database đang được người khác dùng nếu chưa có kế hoạch xác minh đích và tác động.

Hạn chế kết nối outbound từ vùng restore để các job, trigger, extension hoặc ứng dụng vô tình không gửi dữ liệu thật ra ngoài. Việc restore thành công mới là bước đầu: cần kiểm tra schema, row count, ràng buộc, dữ liệu ứng dụng, quyền và khả năng khởi động service.

### 7.4. PITR và log giao dịch

Nếu yêu cầu khôi phục đến thời điểm gần sự cố (ví dụ trước thao tác xóa nhầm), chiến lược PostgreSQL thường cần **base backup hợp lệ và chuỗi WAL cần thiết**. Cần:

1. Có base backup nhất quán theo công cụ/cơ chế được hỗ trợ.
2. Lưu WAL archive/stream đủ để khôi phục từ base backup tới điểm đích.
3. Bảo vệ và giám sát cả **base backup lẫn WAL**, không chỉ file dump.
4. Chọn thời điểm/LSN/timeline đích đúng theo sự cố.
5. Restore thử nghiệm có kiểm tra rằng dữ liệu mong đợi xuất hiện và dữ liệu lỗi chưa được áp dụng.
6. Định nghĩa rõ khi nào recovery được phép ghi trở lại và xử lý replication/search sau phục hồi.

Không phát biểu “RPO bằng 0” chỉ vì bật WAL archiving hoặc replication. Thực tế cần đo độ trễ archive, mất đoạn log, miền lỗi và kết quả rehearsal.

## 8. Khả năng khôi phục phải được kiểm thử định kỳ

**Backup job thành công không đồng nghĩa backup có thể phục hồi.** Một file có thể được ghi đủ byte nhưng thiếu key, thiếu cluster role, thiếu WAL, sai version DBMS hoặc không đủ dung lượng đích để restore.

### 8.1. Quy trình restore drill

Một bài diễn tập có thể gồm:

1. Chọn kịch bản: mất toàn database, xóa nhầm bảng, lỗi migration, mất region hoặc ransomware.
2. Chọn recovery point và backup set tương ứng với RPO/RTO.
3. Cấp môi trường restore **cách ly**, không kết nối tới production theo cách có thể ghi ngược.
4. Lấy khóa và credential qua đường break-glass đã được phê duyệt.
5. Restore base/logical backup, replay WAL nếu cần.
6. Kiểm tra integrity, constraint, row count, schema và quyền.
7. Khởi động ứng dụng Java/đường truy vấn mẫu trong vùng an toàn.
8. Đối chiếu nghiệp vụ: một số đơn, số dư, trạng thái, dữ liệu file đi kèm.
9. Đo thời gian và điểm phục hồi thực, ghi lại mọi blocker.
10. Dọn environment/dump tạm theo chính sách, lưu report chỉ gồm metadata an toàn.

### 8.2. Restore ở tầng SQL khác restore được ứng dụng

Có thể `pg_restore` thành công nhưng Java service vẫn lỗi vì:

- Thiếu extension hoặc function.
- Role/privilege khác production.
- Schema và phiên bản app không tương thích.
- Sequence chưa phù hợp sau import đặc biệt.
- Thông tin file/object store tham chiếu không có.
- Khóa mã hóa phía ứng dụng không tồn tại.
- Transactional outbox cần xử lý lại sau khôi phục.
- Search index/cache đang ở phiên bản khác.

Vì vậy kiểm thử phải bao gồm **luồng nghiệp vụ mẫu**, không chỉ lệnh restore trả exit code 0.

### 8.3. Chỉ số cần theo dõi

| Chỉ số | Câu hỏi |
|---|---|
| Last successful backup age | Bao lâu rồi chưa có backup thành công? |
| Backup coverage | Mọi nguồn quan trọng có nằm trong phạm vi bảo vệ? |
| Backup size/throughput | Kích thước và thời gian có tăng bất thường? |
| Integrity verification failures | Tập backup nào bị hỏng/sai checksum? |
| WAL archive lag/gap | Có điểm nào trong chuỗi khôi phục bị thiếu? |
| Last successful restore drill age | Lần gần nhất thực sự khôi phục thành công? |
| Measured recovery point/time | RPO/RTO đạt được thực tế tới đâu? |
| Key access failures | Có backup nào không giải mã được? |
| Restore validation failures | Query, constraint hoặc app test nào thất bại? |
| Unexpected backup download | Có hành vi truy cập dữ liệu bất thường? |

Một backup bị dừng vài ngày nên được phát hiện bằng alert trước khi hệ thống chính gặp sự cố. Chỉ đếm số file là không đủ; cần so với **lịch backup kỳ vọng và khả năng khôi phục**.

## 9. Vì sao môi trường kiểm thử không nên nhận nguyên bản dữ liệu production?

Test data có hai mục tiêu cần cân bằng:

- **Đủ giống thực tế** để kiểm tra truy vấn, dữ liệu biên, migration, ràng buộc, phân bố và hiệu năng.
- **Không phơi bày dữ liệu thật ngoài mục đích và vùng bảo vệ** đã được phê duyệt.

Một bản sao nguyên production có thể chứa tên, email, số điện thoại, địa chỉ, lịch sử giao dịch, thông tin sức khỏe, thông tin thanh toán, token đăng nhập, password hash hoặc những ghi chú tự do mà không có ai nhớ đang tồn tại.

Một môi trường test thường có nhiều rủi ro hơn production:

- Developer, QA, contractor hoặc hệ thống CI có quyền truy cập rộng hơn.
- Log SQL/debug có mức chi tiết cao; nhiều snapshot/artifact được sinh tự động.
- Tài khoản test có thể ít giám sát hơn hoặc dùng credential lâu ngày.
- Dữ liệu bị copy tới laptop, container volume, database tạm hoặc dịch vụ staging.
- Test có thể thực hiện gửi email, SMS, webhook, thông báo đẩy hoặc tạo hóa đơn.
- Các đợt chạy test tạo thêm backup, cache, search index và file xuất riêng.

Do vậy, nguyên tắc đầu tiên là **không dùng dữ liệu thật nếu dữ liệu tổng hợp/fixture đã đáp ứng bài kiểm thử**.

### 9.1. Các lựa chọn dữ liệu kiểm thử

| Lựa chọn | Ưu điểm | Điểm cần kiểm tra |
|---|---|---|
| **Fixture thủ công** | Nhỏ, dễ hiểu, xác định được kết quả mong đợi | Có thể thiếu dữ liệu biên, phân bố không giống production |
| **Synthetic data** | Không cần lấy dữ liệu thật; có thể tạo nhiều quy mô | Phải mô phỏng phân bố, FK, độ dài, NULL, tương quan đúng |
| **Subset đã làm sạch** | Bám sát schema và phân bố một phần | Kích thước nhỏ có thể bỏ sót tình huống hiếm; còn nguy cơ tái định danh |
| **Clone đã masking toàn diện** | Hữu ích cho migration/performance test phức tạp | Đường clone thô phải cực kỳ hạn chế; masking phải kiểm chứng |
| **Production clone nguyên bản** | Tính thực tế cao | Rủi ro lớn; chỉ cân nhắc trường hợp đặc biệt với kiểm soát tương đương production, phê duyệt rõ và thời hạn ngắn |

Đặc biệt, **dữ liệu đã che một vài cột không mặc nhiên trở thành dữ liệu vô danh**. Lịch sử giao dịch, vị trí, thời gian và các tổ hợp thuộc tính hiếm vẫn có thể chỉ ra một cá nhân.

### 9.2. Những loại dữ liệu thường bị bỏ quên

Không chỉ `users.email` là nhạy cảm. Cần rà soát:

- `orders.shipping_address`, tên người nhận, số điện thoại.
- Các cột văn bản tự do: `notes`, `support_message`, `error_detail`.
- `JSONB` chứa object lồng nhau, ảnh hoặc file đính kèm.
- Dữ liệu xác thực: password hash, session token, refresh token, API key, OAuth credential.
- Audit log, IP address, user-agent, lịch sử vị trí và thời điểm.
- Tham số tìm kiếm, nội dung chat và URL có token.
- Bảng outbox/inbox, message payload, job queue, dead-letter queue.
- Cache Redis, search index và các bản export/analytics.
- Metadata của tenant, mã số khách hàng và khóa có thể đối chiếu với nguồn ngoài.

Một bản test clone “chỉ mask bảng `customers`” có thể vẫn tiết lộ toàn bộ tên và địa chỉ trong bảng `orders` hoặc văn bản hỗ trợ khách hàng.

## 10. Masking, pseudonymization, anonymization và tokenization

Các thuật ngữ này không đồng nghĩa; đánh giá mức giảm rủi ro cần dựa trên khả năng liên kết hoặc khôi phục danh tính trong bối cảnh thực tế.

### 10.1. Masking

**Masking** thay thế hoặc che bớt một trường, ví dụ:

~~~text
Trước:   email = "khachhang@example.com"
Sau:     email = "test-1042@example.invalid"

Trước:   phone = "+84..."
Sau:     phone = NULL hoặc số giả trong dải kiểm thử
~~~

Giá trị sau phải phù hợp test nhưng không gửi tới người thật. Miền `example.invalid` chỉ minh họa một đích không có thực theo cách dùng tên miền dành cho ví dụ; hệ thống vẫn phải chặn outbound trên hạ tầng, không dựa duy nhất vào format email.

Masking có thể **không bảo vệ được một người** nếu giữ nguyên tổ hợp ngày sinh, vùng cư trú, giá trị giao dịch và thông tin hiếm.

### 10.2. Pseudonymization (bút danh hóa)

Pseudonymization thay định danh trực tiếp bằng một giá trị đại diện; hệ thống có thể giữ khả năng liên kết giữa nhiều bản ghi của cùng đối tượng mà không lộ tên/email thật.

Ví dụ tạo một khóa đại diện ổn định từ định danh gốc bằng HMAC với khóa bí mật. Nếu khóa tồn tại hoặc có thể so sánh với tập nguồn, dữ liệu vẫn có thể liên kết về người thật, do đó **pseudonymized data không mặc nhiên là anonymous data**.

Cần xem:

- Khóa/secret được lưu ở đâu, ai sử dụng được?
- Dùng chung một key cho nhiều bản clone có tạo khả năng liên kết không mong muốn?
- Giá trị đại diện có thể giải ngược qua bảng mapping không?
- Bản sao còn giữ nhiều quasi-identifiers không?
- Có yêu cầu đổi bút danh giữa từng lần tạo test copy không?

### 10.3. Anonymization (ẩn danh hóa)

Anonymization hướng tới việc không còn khả năng nhận diện cá nhân trong bối cảnh sử dụng và các nguồn phụ trợ hợp lý có thể tiếp cận. Đây là **mức độ đảm bảo phải được đánh giá theo rủi ro**, không đạt được chỉ bằng việc gọi một hàm `hash()`.

Một hàng có tên đã bị xóa nhưng giữ tổ hợp vị trí, tuổi hiếm, ngày giao dịch và chi phí đặc biệt vẫn có thể bị tái định danh qua dữ liệu công khai. Cần đánh giá dữ liệu liên kết, đặc tính phân bố, khả năng truy vấn và độ hiếm của bản ghi.

### 10.4. Tokenization và bảng ánh xạ

Tokenization thay giá trị nhạy cảm bằng token, có thể có một dịch vụ vault quản lý ánh xạ gốc ↔ token. Khi tồn tại bảng ánh xạ hoặc API detokenize, dữ liệu tokenized vẫn cần được bảo vệ tương ứng.

Không đưa bản đồ token → danh tính thật vào cùng môi trường test nếu test không có nhu cầu đó. Nếu cần dữ liệu có hình dạng tương tự thanh toán, ưu tiên token/test credential do nhà cung cấp sandbox cấp, không sao chép token production.

### 10.5. Hash thường không đủ cho định danh có miền nhỏ

Một cột email/phone được thay bằng SHA-256 không khóa có thể vẫn bị dò qua từ điển những giá trị phổ biến. HMAC với khóa bí mật được bảo vệ tốt hơn cho định danh hóa ổn định trong một phạm vi test được phê duyệt, nhưng vẫn không tự tạo ẩn danh tuyệt đối.

**Không lưu key HMAC cùng dump**, và không tái sử dụng tùy tiện key production cho test. Key/seed được quản lý tách biệt, quyền rất hẹp và có cơ chế xóa/rotate theo vòng đời bản clone.

## 11. Quy trình production → test copy an toàn

Một pipeline cần ngăn việc “restore xong rồi mới nhớ mask” ở môi trường đã được cấp quyền rộng. Bản clone nguyên production phải nằm trong **vùng cách ly có mức bảo vệ tương đương**, chỉ sanitizer và nhân sự được phê duyệt mới truy cập được.

~~~mermaid
flowchart TD
    A["Nguồn backup/production được phê duyệt"] --> B["Restore trong enclave cô lập"]
    B --> C["Vô hiệu hóa email, webhook, jobs, token và network egress"]
    C --> D["Chọn tập dữ liệu tối thiểu"]
    D --> E["Mask/tokenize/generate dữ liệu thay thế"]
    E --> F["Kiểm tra FK, bất biến, PII scanner, dữ liệu lộ sót"]
    F --> G{"Chứng minh đạt chính sách?"}
    G -->|"Không"| H["Cách ly + sửa và chạy lại"]
    G -->|"Có"| I["Đóng gói bản sạch + cấp quyền test"]
    I --> J["TTL, audit, cleanup"]
~~~

### 11.1. Bước 1 – Yêu cầu, mục đích và phê duyệt

Trước khi clone:

1. Mô tả chính xác mục tiêu: tái hiện lỗi SQL, test migration hay benchmark?
2. Xác định dữ liệu tối thiểu và mức độ thật cần thiết.
3. Chọn synthetic data/fixture nếu có thể.
4. Quy định ai được nhận bản sao, trong môi trường nào và trong bao lâu.
5. Xác định hành vi bị cấm: export, chia sẻ, gửi đến third-party, làm công khai.
6. Ghi thông tin phê duyệt và kết quả đánh giá quyền riêng tư theo chính sách của tổ chức.

Không để một job CI bất kỳ tự quyết định clone toàn production chỉ vì đã có credential.

### 11.2. Bước 2 – Vùng restore thô cách ly

Nếu buộc phải restore dữ liệu thật để làm sạch:

- Dùng account/project/network riêng có inbound/outbound mặc định bị hạn chế.
- Chỉ sanitizer identity được truy cập trong thời gian ngắn.
- Mã hóa volume, file tạm, snapshot và log.
- Không kết nối các ứng dụng tiêu thụ thật tới clone.
- Chặn gửi email, SMS, webhook và thông báo ngoài; thay credential bằng secret giả hoặc sandbox.
- Không bật job định kỳ sinh tác dụng phụ.
- Không tải dump về laptop hoặc artifact CI trước khi được làm sạch.

**Ẩn danh hóa sau khi data đã xuất hiện trên máy developer không sửa được sự cố phơi bày trước đó.** Việc sanitization phải xảy ra trước khi mở quyền dùng bản sao.

### 11.3. Bước 3 – Tối thiểu hóa tập dữ liệu

Nếu bài test chỉ cần 10.000 đơn với nhiều dạng trạng thái, không cần chép 50 triệu đơn và tất cả khách hàng.

Có thể chọn mẫu theo:

- Nhóm trạng thái quan trọng.
- Kích thước và đặc tính quan hệ.
- Các ca biên từng gây lỗi.
- Phân bố giá trị NULL, chuỗi dài và độ sâu quan hệ.
- Dữ liệu nhiều tenant giả lập nhưng không giữ identity gốc.

**Sampling** phải có FK và dependency graph: sao chép vài đơn nhưng thiếu hàng khách hàng tham chiếu có thể làm test migration sai. Một tập dữ liệu nhỏ cũng có thể dễ tái định danh hơn nếu những hàng được chọn là các trường hợp rất hiếm; vì vậy phải làm sạch sau chọn mẫu.

### 11.4. Bước 4 – Biến đổi trường nhạy cảm có chủ đích

Mỗi trường được phân loại theo chiến lược:

| Nhóm dữ liệu | Cách xử lý có thể phù hợp | Điều cần kiểm tra |
|---|---|---|
| Tên, email | Tên giả, email dùng miền test riêng | Unique, format, không gửi mail thật |
| Điện thoại, địa chỉ | Thay bằng giá trị giả hoặc bỏ | Quy tắc validation, timezone, mã vùng |
| Định danh khách hàng | ID giả/bút danh có ràng buộc | FK và khả năng liên kết liên bảng |
| Thẻ/thanh toán | Không sao chép; dùng token/test fixtures của provider sandbox | Không giữ PAN/CVV/token production |
| Password hash/session token | Xóa hoặc thay bằng credential test riêng | Không thể đăng nhập tài khoản thật |
| Ghi chú/JSON tự do | Xóa, sinh nội dung giả hoặc redaction theo schema | PII lồng nhau, nội dung file |
| Giá, tồn kho, trạng thái | Có thể giữ phân bố đã xử lý để test | Không tạo bản ghi nhận diện qua tổ hợp hiếm |
| Timestamp | Dịch/khái quát hóa hoặc sinh lại | Bảo toàn quan hệ thứ tự và duration test |
| Logs, event, outbox | Lọc hoặc thay payload bằng phiên bản test | Không phát lại side effect/thông tin nhạy cảm |
| Bí mật và khóa ứng dụng | Không chuyển; dùng secret môi trường test | Không giải mã/truy cập hệ production |

Không phải trường nào cũng cần giữ nguyên giá trị để có test tốt. Đối với kiểm thử chức năng, dữ liệu tổng hợp được thiết kế đúng bất biến thường mang lại kết quả dễ lặp lại hơn.

### 11.5. Bước 5 – Kiểm tra trước khi cấp quyền

Các lớp kiểm tra nên bổ sung cho nhau:

- Kiểm tra schema và ràng buộc (FK, unique, not-null, check).
- DLP/PII scanner theo cột cấu trúc và trường tự do.
- Phát hiện email/điện thoại/tên miền production còn sót.
- Kiểm tra credential, token, webhook target, job queue và endpoint.
- Kiểm tra không có app vẫn kết nối production hay gửi outbound không mong muốn.
- Kiểm tra số hàng, phân bố, dữ liệu biên và tính hữu ích của test.
- Đối chiếu tỷ lệ bản ghi không được sanitize và xử lý ngoại lệ.
- Kiểm tra audit, owner, thời hạn xóa và quyền của môi trường đích.

**Scanner không tìm thấy PII không chứng minh dữ liệu đã hoàn toàn vô danh.** Quy trình phải kết hợp danh mục dữ liệu, kiểm tra schema-specific và đánh giá rủi ro tái định danh.

## 12. Ví dụ làm sạch dữ liệu trên PostgreSQL

Các câu lệnh dưới đây là **mô hình minh họa trên database kiểm thử đã được cô lập**, tuyệt đối không dùng như script chung trực tiếp trên production. Trước khi chạy cần có bản đồ dữ liệu, quan hệ và chính sách an toàn phù hợp.

### 12.1. Thay email và thông tin liên lạc

Giả sử bảng test clone có cột:

~~~sql
CREATE TABLE customers (
    id          BIGINT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT NOT NULL,
    phone       TEXT,
    address     TEXT
);
~~~

Một phép chuyển tối giản cho fixture kiểm thử:

~~~sql
BEGIN;

UPDATE customers
SET email = 'test-user-' || id::text || '@example.invalid',
    full_name = 'Test Customer ' || id::text,
    phone = NULL,
    address = NULL;

COMMIT;
~~~

Điểm tốt của ví dụ là giữ unique theo `id` và tránh email có thật. Nhưng **không được xem nó là giải pháp làm sạch hoàn chỉnh**:

- ID gốc có thể tự nó là định danh nhạy cảm hoặc giúp liên kết với nguồn production.
- Các bảng khác có thể lặp lại email, tên và địa chỉ trong snapshot.
- Ghi chú, event JSON, file, logs, password hash/token vẫn còn.
- Giá trị tiền, thời gian, địa lý và tổ hợp thuộc tính có thể tái định danh.
- Nếu một bảng dùng email làm khóa ngoại thay vì ID, thay độc lập ở một bảng sẽ phá tham chiếu.

Đó là lý do pipeline phải có **kế hoạch chuyển đổi xuyên bảng**, thay vì một câu UPDATE đơn lẻ.

### 12.2. Duy trì khóa và quan hệ

Một cách đơn giản trong một vùng test cô lập là **giữ surrogate key nội bộ** chỉ để bảo vệ FK, nhưng phải đánh giá nguy cơ các ID đó liên kết với dữ liệu bên ngoài.

Nếu cần thay ID, tạo mapping cũ → mới **bên trong enclave** và áp dụng nhất quán cho tất cả bảng liên quan; không công bố mapping. Ví dụ về ý tưởng:

~~~text
customers.id:             102 -> 900102
orders.customer_id:       102 -> 900102
support_threads.user_id:  102 -> 900102

Mapping này được bảo vệ trong vùng sanitizer;
bản sao phát hành cho test không chứa bảng ánh xạ ngược.
~~~

Sự chuyển đổi khóa chính và khóa ngoại phải tuân thủ thứ tự/ràng buộc của DBMS hoặc thực hiện qua bảng staging/transaction theo thiết kế cụ thể. **Đừng tắt FK, thay ID từng bảng rồi bật lại mà không validate toàn bộ**, vì có thể để lại dữ liệu mồ côi.

### 12.3. Một bước kiểm tra kết quả minh họa

Sau khi phát hành một bản clone chỉ được phép có email giả dạng `test-user-...@example.invalid`, có thể kiểm tra:

~~~sql
SELECT COUNT(*) AS unexpected_email_count
FROM customers
WHERE email NOT LIKE 'test-user-%@example.invalid';
~~~

Đây là kiểm tra hợp đồng **cho cột email của fixture cụ thể**, không phải kiểm tra PII tổng quát. Một bản sao vẫn có thể chứa thông tin nhạy cảm ở bảng khác dù kết quả là 0. Ngoài ra cần kiểm tra `COUNT(*)`, unique, FK và chất lượng dữ liệu kiểm thử.

## 13. Ví dụ Java: bút danh hóa có khóa để giữ quan hệ dữ liệu

Đôi khi test cần biết cùng một email ở các bảng khác nhau cùng trỏ về một đối tượng nhưng không muốn giữ email thật. Có thể dùng **HMAC** với khóa bí mật do hạ tầng sanitizer cung cấp để tạo chuỗi đại diện ổn định trong phạm vi bản clone.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class TestIdentityPseudonymizer {
    private final SecretKey key;

    public TestIdentityPseudonymizer(SecretKey key) {
        if (key == null) {
            throw new IllegalArgumentException("Missing HMAC key");
        }
        this.key = key;
    }

    public String testEmail(String email)
            throws GeneralSecurityException {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Missing email");
        }

        // Quy tắc normalize phải phù hợp ngữ nghĩa email ứng dụng.
        String normalized = email.trim().toLowerCase(Locale.ROOT);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        byte[] digest = mac.doFinal(
            ("test-email:v1:" + normalized)
                .getBytes(StandardCharsets.UTF_8)
        );

        String code = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);

        return "test-" + code + "@example.invalid";
    }
}
~~~

Những lưu ý quan trọng:

1. **Key được inject** từ secret manager/KMS qua vùng sanitizer; không hardcode và không viết key vào code, log hoặc bản sao đích.
2. Chuẩn hóa email `toLowerCase` chỉ an toàn nếu ứng dụng đã có ngữ nghĩa nhận diện tương ứng; ở hệ thống khác, local part có thể yêu cầu cách xử lý khác.
3. Prefix `test-email:v1:` là một dạng **domain separation** theo mục đích; có thể cần khóa riêng cho mỗi môi trường/bản clone để không liên kết chéo.
4. HMAC giúp tránh kiểu hash không khóa dễ bị dò danh sách email phổ biến, nhưng kết quả vẫn **pseudonymous**, không tự được công nhận anonymous.
5. Giá trị đầu ra có thể đáp ứng định dạng email của fixture, nhưng cần kiểm thử độ dài trường DB, unique, validation và kích thước field. Chuỗi Base64 URL an toàn về ký tự cho nhiều use case, không phải đặc tả email đầy đủ.
6. Nếu liên kết qua email giữa nhiều bảng, phải áp dụng **cùng quy tắc trong một phạm vi được kiểm soát** và tránh lưu email thật bên cạnh bút danh.
7. Nếu bút danh có thể truy ngược bằng key hoặc liên kết với dataset khác, vẫn cần hạn chế quyền, retention và xử lý theo phân loại dữ liệu tương ứng.

Trong môi trường ưu tiên dữ liệu tổng hợp, có thể tạo ID/email giả nhất quán từ seed không liên quan dữ liệu thật. Điều đó thường đơn giản hơn và ít rủi ro hơn so với xử lý dữ liệu thật chỉ để dựng fixture.

## 14. Tính hữu ích của dữ liệu test không đồng nghĩa giữ nguyên danh tính

Một dataset dùng cho test migration hoặc hiệu năng thường cần giữ các đặc tính:

- Số hàng và tỷ lệ lớn/nhỏ giữa các bảng.
- Phân bố `NULL`, unique, foreign key và các ca vi phạm lịch sử.
- Độ dài chuỗi, payload JSON, kích thước BLOB.
- Mức độ skew của khóa và tần suất JOIN.
- Tỷ lệ bản ghi theo trạng thái, thời gian, tenant hoặc nhóm chiết khấu.
- Quan hệ thời gian: một đơn tạo trước thanh toán, giao sau xác nhận.
- Các biến thể Unicode, timezone, mã vùng và giá trị biên.
- Quy mô index, selectivity và query plan nếu test performance.

### 14.1. Sinh dữ liệu tổng hợp có chủ đích

Thay vì sao chép toàn bộ khách hàng thật, có thể sinh:

~~~text
1.000.000 users giả:
  - ID unique và email @example.invalid
  - tên và địa chỉ giả
  - tỷ lệ active/inactive tương tự workload đã tổng hợp
  - vài nhóm có nhiều order, vài nhóm có ít order

5.000.000 orders giả:
  - FK trỏ user giả hợp lệ
  - trạng thái có phân bố đã thiết kế
  - giá trị tiền có biên hợp lệ
  - timestamp có thứ tự nghiệp vụ hợp lệ
~~~

Các thống kê phân bố lấy từ production cũng có thể nhạy cảm ở nhóm quá nhỏ. Chỉ xuất các thống kê được phê duyệt, tổng hợp đủ lớn và không làm lộ tập hiếm.

### 14.2. Một bản sao nhỏ không luôn đủ để benchmark

Nếu mục tiêu là kiểm tra query plan trên bảng rất lớn, một dataset 1000 hàng có thể khiến planner dùng seq scan trong khi production dùng index, hoặc ngược lại. Cần dữ liệu test có kích thước, skew và index gần thực tế, nhưng **không bắt buộc dùng danh tính thật**.

Đo hiệu năng trên dữ liệu đã được sanitize hoặc synthetic theo quy mô phù hợp; ghi rõ khác biệt với production như tỷ lệ hit cache, concurrency, phân vùng, tài nguyên I/O và cấu hình DB để không hiểu nhầm benchmark.

### 14.3. Test kiểm thử quyền truy cập và tenant isolation

Để kiểm thử lỗi rò dữ liệu qua tenant, cần các tenant giả có dữ liệu chồng lấn về ID hoặc điều kiện tìm kiếm, không cần dùng tenant thật. Ví dụ:

- Tenant A có user 100, order 500.
- Tenant B có user 100, order 500 trong phạm vi tenant riêng.
- Query thiếu `tenant_id` phải bị test bắt.
- API trả lỗi phân quyền, không tiết lộ số lượng/tên đối tượng ở tenant khác.

Dữ liệu tổng hợp giúp chủ động tạo những tình huống an toàn mà production có thể không có hoặc không cho phép truy cập.

## 15. Ngăn tác dụng phụ ngoài ý muốn của bản clone

Ngay cả khi dữ liệu đã được masking, ứng dụng chạy trên clone có thể có cấu hình kết nối ra ngoài:

- Hệ gửi email/SMS thật.
- Payment gateway ở chế độ live.
- Webhook gửi tới hệ thống đối tác.
- Message broker dùng chung production.
- Object storage production hoặc CDN.
- API nền tảng có quyền ghi dữ liệu thật.
- Search indexing nhầm vào cluster production.

### 15.1. Các guardrail cần áp dụng

1. **Mặc định chặn egress**, chỉ cho phép endpoint sandbox cần thiết.
2. Dùng credential test riêng; không sao chép credential production.
3. Tắt scheduler, worker và job nền khi restore thô.
4. Chuyển email/SMS sang sink cục bộ hoặc hộp thư test.
5. Thay payment provider bằng sandbox theo đúng hợp đồng provider.
6. Gắn tên môi trường rõ, để service từ chối gửi hoặc ghi vào đích production.
7. Kiểm tra cấu hình DB host, broker, queue, storage và search trước khi cấp traffic.
8. Log metadata về các lệnh outbound bị chặn, không log payload nhạy cảm.

Việc đổi email thành `@example.invalid` **không thay thế network isolation**: một test vẫn có thể gửi dữ liệu thật từ trường `notes` hoặc event payload tới webhook nếu egress mở.

### 15.2. Bản sao làm sạch cũng có thể cần quyền hẹp

Một số bản clone đã loại bỏ tên/email nhưng vẫn giữ giá bán, chiến lược chiết khấu, doanh số và thông tin kinh doanh nội bộ. Các dữ liệu này có thể vẫn là bí mật thương mại, nên “không còn PII” **không đồng nghĩa công khai cho mọi người**.

Cấp quyền theo nhóm và thời hạn; không đẩy bản sạch lên repository công khai hoặc môi trường demo bên thứ ba nếu chưa có đánh giá riêng.

## 16. Retention, xóa và vòng đời bản sao

Backup và test clone có vòng đời khác nhau.

### 16.1. Backup production

Retention phải đáp ứng mục tiêu phục hồi, quy tắc vận hành và nghĩa vụ lưu giữ, nhưng không nên vô hạn nếu không có cơ sở. Cần quy định:

- Full backup, incremental, WAL/log giữ bao lâu.
- Các bản sao dài hạn/immutable có thời hạn khác nhau ra sao.
- Khi xóa một bản backup cũ, có làm đứt chuỗi restore phụ thuộc nó không?
- Có legal hold hoặc yêu cầu kiểm toán ngăn xóa không?
- Cách ghi nhận kết quả xóa, tiêu hủy phương tiện và khả năng phục hồi còn lại.
- Khóa mã hóa cần giữ bao lâu để đọc những bản còn hợp lệ.

**Xóa khóa trước khi hết hạn backup có thể biến bản sao thành không phục hồi được**, ngay cả khi ciphertext vẫn còn nguyên.

### 16.2. Test clone

Bản sao test thường nên có **thời hạn ngắn và xóa tự động**, gắn với ticket/job/đợt kiểm thử. Ngoài database phải tính cả:

- Snapshot tạm.
- File dump và object storage.
- Volume container, máy ảo và môi trường ephemeral.
- Search index, cache, file attachment.
- Log và CI artifacts.
- Bản clone được developer tải về hoặc chia sẻ lại.

Một chính sách “xóa database test sau 7 ngày” không đủ nếu file dump nguyên vẫn tồn tại trong artifact của job. Cần quản lý **tất cả bản sao phái sinh** và theo dõi việc dọn dẹp.

### 16.3. Yêu cầu xóa dữ liệu cá nhân và backup bất biến

Có thể tồn tại sự căng thẳng giữa khả năng phục hồi/audit và yêu cầu xóa dữ liệu cá nhân. Không tự đặt một thời hạn pháp lý chung cho mọi tổ chức hoặc quốc gia. Thay vào đó:

1. Xác định mục đích, nghĩa vụ lưu giữ và chính sách áp dụng.
2. Ngăn tạo thêm bản sao test không cần thiết.
3. Duy trì danh mục nguồn/bản sao chứa dữ liệu cần xử lý.
4. Quy định các bản backup chưa thể sửa trực tiếp trong retention có được khôi phục trong điều kiện nào.
5. Khi restore một backup cũ, **phát lại những yêu cầu xóa/điều chỉnh cần thiết** trước khi đưa dữ liệu trở lại phục vụ.
6. Bảo đảm backup/test copy hết thời hạn được loại bỏ theo cơ chế phù hợp.

Không coi “backup là ngoại lệ nên giữ mãi” là chính sách mặc định. Cần phối hợp chủ sở hữu dữ liệu, bảo mật và pháp chế theo nghĩa vụ thực tế.

## 17. Ứng phó khi bản backup hoặc test copy bị lộ

Một sự cố có thể bắt đầu bằng cảnh báo download bất thường của file dump, bucket bị thay ACL hoặc phát hiện dữ liệu thật trong log CI.

### 17.1. Quy trình phản ứng ở mức hệ thống

1. **Xác nhận và khoanh vùng:** tài sản nào bị ảnh hưởng, loại dữ liệu và thời gian phơi bày?
2. **Chặn truy cập mới:** thu hồi link/token, hạn chế quyền và khóa đường xuất dữ liệu; tránh phá hủy chứng cứ cần điều tra.
3. **Bảo toàn audit:** lưu metadata truy cập, key usage, network logs và lịch sử thay quyền.
4. **Đánh giá tác động:** bản sao có mã hóa không, ai có thể lấy khóa, có download thành công không, có dữ liệu bí mật nào?
5. **Khôi phục kiểm soát:** rotate credential/keys theo chiến lược, sửa IAM, rà soát các bản sao tương tự.
6. **Thông báo theo nghĩa vụ:** phối hợp bảo mật/pháp chế và quy trình thông báo áp dụng.
7. **Ngăn tái diễn:** bổ sung policy-as-code, kiểm tra exposure, DLP, quy trình phê duyệt và rehearsal.
8. **Đánh giá tính khôi phục:** nếu ransomware hoặc kẻ tấn công đã xóa backup, xác minh còn ít nhất một restore path tin cậy.

Không khẳng định “không có rủi ro vì file đã mã hóa” nếu attacker cũng có quyền sử dụng KMS key hoặc tài khoản restore.

### 17.2. Sự cố tính toàn vẹn khác sự cố bí mật

Nếu backup bị sửa hoặc bị nhiễm mã độc nhưng không bị công khai, phản ứng tập trung vào:

- Ngừng sử dụng bản đáng ngờ.
- So sánh manifest/checksum/chữ ký và backup set độc lập.
- Kiểm tra nguồn gốc và thời điểm thay đổi.
- Khôi phục từ bản đáng tin hơn, trong vùng cách ly.
- Phát hiện nguồn production có bị xâm nhập trước khi chụp backup không.

Một bản backup được mã hóa và lưu bất biến **vẫn có thể chứa trạng thái đã sai hoặc đã bị mã độc sửa trước khi chụp**. Cần chọn recovery point theo timeline sự cố và kiểm tra ở mức nghiệp vụ.

## 18. Bộ kiểm soát kỹ thuật có thể đưa vào CI/CD

### 18.1. Kiểm tra trước khi tạo bản sao

- Chỉ cho phép workflow có danh tính/công việc đã được phê duyệt.
- Chặn export trực tiếp từ production sang artifact công khai.
- Dùng short-lived credentials/workload identity khi nền tảng hỗ trợ.
- Bắt buộc bucket encryption, private access và retention policy.
- Không cho phép dùng production secrets trong pipeline test.
- Gắn metadata: owner, purpose, source, classification, expiry.

### 18.2. Kiểm tra trước khi cấp quyền test

- Có bằng chứng sanitizer đã chạy và thoát thành công.
- Data quality và constraint checks đạt.
- PII/secret scanning đạt trong phạm vi đã kiểm chứng.
- Egress và external integrations đã được khóa/sandbox.
- Không có role production hoặc token thật trong database.
- Log và snapshot tạm được kiểm soát và có lịch dọn.
- Có approval, audit record và TTL.

### 18.3. Kiểm tra liên tục

- Phát hiện bucket/public exposure.
- Phát hiện backup thất bại hoặc quá hạn.
- Phát hiện object bị đổi retention/ACL bất thường.
- Phát hiện test clone vượt tuổi hoặc không còn owner.
- Báo cáo restore drill, key lifecycle và coverage.
- Kiểm tra build artifact có dấu dữ liệu thật/secret không.

Trên thực tế, policy-as-code và DLP không thể thay thế việc hiểu **ý nghĩa nghiệp vụ của trường dữ liệu**, nhưng có thể ngăn lỗi thao tác phổ biến trước khi dữ liệu rời vùng tin cậy.

## 19. Bảng quyết định nhanh

| Tình huống | Cách tiếp cận phù hợp | Điều không nên làm |
|---|---|---|
| Cần phục hồi sau mất DB | Base backup/WAL hoặc chiến lược phù hợp RPO/RTO, drill restore | Chỉ lưu một dump chưa từng restore thử |
| Muốn tạo dữ liệu cho unit/integration test | Fixture/synthetic data | Copy nguyên production vì tiện |
| Cần kiểm thử migration với dữ liệu lịch sử thật | Bản clone cách ly, masking có kiểm chứng và giới hạn thời gian | Cho developer truy cập clone raw |
| Cần benchmark bảng rất lớn | Synthetic/sanitized dataset có phân bố sát workload | Giữ PII thật chỉ để đạt số hàng |
| Muốn backup chống ransomware | Kho có retention/immutability, tách quyền và miền lỗi | Để cùng credential xóa cả DB và backup |
| Restore dump vào test | Đích cô lập, quyền hẹp, tắt outbound/job, sanitize rồi cấp quyền | Restore thẳng vào staging đang mở cho bên ngoài |
| Backup mã hóa nhưng mất key | Kiểm tra key lifecycle và restore drill | Coi có ciphertext là đủ để phục hồi |
| Test clone có PII trong JSON/log | Mở rộng inventory, làm sạch và quét lại | Chỉ mask email trên bảng users |
| App test có cấu hình payment live | Vô hiệu hóa, chuyển sandbox, chặn egress | Tin rằng email giả bảo vệ mọi side effect |
| Người dùng yêu cầu xóa dữ liệu | Theo policy retention, quản lý bản sao và quy trình xử lý khi restore | Xóa ở primary rồi quên backup/test clone |

## 20. Bài tập tự kiểm tra

### Bài 1. Backup nhiều bản nhưng cùng account

Một nhóm tạo ba backup mỗi ngày trong cùng bucket, cùng admin có quyền xóa. Có đủ chống ransomware chưa?

**Gợi ý:** Chưa. Cùng miền tin cậy khiến một credential bị chiếm có thể xóa cả ba. Cần phân tách quyền/account/vị trí, retention bất biến và restore drill.

### Bài 2. Có file backup nhưng không có khóa

Backup được mã hóa, nhưng KMS key của năm trước đã bị xóa. Có thể coi backup còn phục hồi được không?

**Gợi ý:** Không, nếu không có phương án giải mã hợp lệ. Key lifecycle và khả năng restore phải được diễn tập cùng backup.

### Bài 3. Production clone vào CI

Một workflow tải toàn bộ `pg_dump` production vào CI artifact rồi chạy SQL mask email. Artifact chỉ tồn tại 24 giờ. Điều gì sai?

**Gợi ý:** Dữ liệu thật đã vào môi trường/artifact có quyền khác trước khi sanitization. Cần restore/sanitize trong enclave hạn chế, chỉ phát hành bản sạch được kiểm chứng, kiểm tra tất cả artifact/log.

### Bài 4. Email giả nhưng notes thật

Bảng khách hàng đã thay mọi email bằng `@example.invalid`; bảng `support_tickets.notes` còn số điện thoại và địa chỉ thật. Có thể gọi dataset là anonymous không?

**Gợi ý:** Không. Cần inventory toàn bộ bảng/JSON/text/file và đánh giá tái định danh, không chỉ một cột email.

### Bài 5. Cần giữ quan hệ giữa bảng

Test cần JOIN `customers` với `orders` nhưng muốn thay định danh khách hàng. Làm sao giữ FK?

**Gợi ý:** Tạo mapping old→new trong vùng cô lập, áp dụng nhất quán trên mọi bảng và không xuất mapping ra test; hoặc giữ surrogate key đã được đánh giá không nhạy cảm và làm sạch các trường khác.

### Bài 6. HMAC có phải ẩn danh tuyệt đối?

Một email được thay bằng HMAC có key bí mật. Nhóm vẫn giữ key và có thể tạo cùng HMAC từ danh sách email production. Có thể khẳng định dữ liệu hoàn toàn vô danh không?

**Gợi ý:** Không. Đó là pseudonymization, có khả năng liên kết/khôi phục theo key và dữ liệu phụ trợ.

### Bài 7. RPO và backup mỗi ngày

Ứng dụng muốn RPO không quá 5 phút nhưng chỉ chạy `pg_dump` lúc 00:00. Có đáp ứng không?

**Gợi ý:** Không. Cần giải pháp lưu thay đổi liên tục hoặc cơ chế khác phù hợp RPO, cùng kiểm chứng khả năng phục hồi theo điểm thời gian.

### Bài 8. Replica thay backup

Hệ có PostgreSQL streaming replica đồng bộ nên nhóm muốn bỏ backup. Điều gì có thể sai?

**Gợi ý:** DELETE, schema lỗi hoặc lỗi logic có thể lan sang replica; còn cần khôi phục về trạng thái trước sự cố. Replica là thành phần HA/read scaling, không thay thế backup/PITR.

### Bài 9. Test gửi webhook thật

Một bản clone đã mask email, nhưng worker có thể gọi webhook đến đối tác production với payload từ bảng outbox. Cần biện pháp gì?

**Gợi ý:** Tắt worker/job, thay endpoint/credential sandbox và chặn egress mặc định; không chỉ dựa vào thay email.

### Bài 10. Restore SQL thành công nhưng service không chạy

`pg_restore` trả exit code 0, nhưng ứng dụng Java lỗi vì thiếu extension và role. Có thể đánh dấu restore drill thành công không?

**Gợi ý:** Chưa đạt mức khôi phục dịch vụ. Cần kiểm tra schema, permission, extension, dữ liệu và luồng nghiệp vụ end-to-end.

### Bài 11. Xóa dữ liệu người dùng

Đã xóa user khỏi primary nhưng bản backup hai tháng trước vẫn chứa dữ liệu đó. Sau khi restore backup, cần làm gì?

**Gợi ý:** Áp dụng chính sách lưu trữ/xóa hợp lệ, phát lại yêu cầu xóa/điều chỉnh liên quan trước khi mở dữ liệu phục vụ; quản lý cả bản test và những bản phái sinh.

### Bài 12. Benchmark không cần PII

Đội tối ưu index cần 10 triệu đơn có phân bố tương tự production. Có nhất thiết clone toàn bộ dữ liệu thật không?

**Gợi ý:** Không. Sinh synthetic data có thống kê phân bố đã được phê duyệt và các ràng buộc tương ứng; nếu cần clone thật phải qua enclave/sanitization và approval.

## 21. Tổng kết

- **Backup và test copy là dữ liệu cần được bảo vệ độc lập.** Chúng có thể chứa nhiều thông tin hơn API công khai và có vòng đời dài hơn chương trình tạo ra chúng.
- **Mã hóa là cần thiết nhưng chưa đủ.** Cần bảo vệ khóa, quyền truy cập, toàn vẹn, sự phân tách miền lỗi, audit và khả năng phục hồi.
- **Backup không bằng replica.** Muốn đáp ứng RPO/RTO cần chọn cơ chế backup/log phù hợp và **thực sự diễn tập restore**.
- **Không đưa bản raw production vào môi trường test mở rộng.** Ưu tiên synthetic/fixture; nếu phải clone thật, dùng enclave cách ly, tối thiểu hóa, làm sạch rồi mới phát hành.
- **Masking khác ẩn danh hóa.** HMAC/pseudonym giúp che định danh trực tiếp nhưng vẫn cần kiểm soát liên kết, dữ liệu hiếm và rủi ro tái định danh.
- **Giữ đúng dữ liệu kiểm thử.** Cần duy trì FK, phân bố, ràng buộc và ca biên mà không giữ nguyên danh tính hoặc secret production.
- **Chặn tác dụng phụ và giới hạn vòng đời.** Test environment phải không thể gửi email/thanh toán/webhook production ngoài ý muốn, có TTL và xóa cả bản sao phái sinh.
- **Bảo mật đi cùng vận hành.** IAM, KMS, WAL/PITR, DLP, backup integrity, restore drill, alert và incident runbook tạo thành một hệ thống bảo vệ thống nhất.

Bảo vệ dữ liệu sao lưu và bản sao phục vụ kiểm thử nghĩa là vừa **giữ được khả năng khôi phục khi nguồn chính thất bại**, vừa **giữ dữ liệu thật trong đúng ranh giới tin cậy và mục đích sử dụng**. Một hệ thống persistence Java an toàn không chỉ đảm bảo `COMMIT` thành công: nó phải biết dữ liệu đã được nhân bản ở đâu, ai có thể đọc, có thể phục hồi đúng hay không, và làm thế nào để kiểm thử mà không tạo thêm một nơi rò rỉ dữ liệu.


