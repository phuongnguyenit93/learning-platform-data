# Xác định mục tiêu mất dữ liệu cho phép (RPO)

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích chính xác **Recovery Point Objective (RPO)** là gì, vì sao RPO đo lượng dữ liệu có thể mất theo **khoảng thời gian**, và phân biệt nó với RTO, retention, SLA và độ trễ replica.
2. Chuyển yêu cầu kinh doanh thành RPO cụ thể cho từng tập dữ liệu và luồng nghiệp vụ, thay vì gán cùng một giá trị cho toàn hệ thống.
3. Xác định **mốc dữ liệu có thể khôi phục an toàn** dựa trên backup, WAL, snapshot, replication và tính nhất quán của các nguồn phụ thuộc.
4. Phân tích RPO dưới các sự cố khác nhau: crash một node, mất vùng, lỗi vận hành, xóa nhầm, hỏng logic, ransomware và failover sang standby trễ.
5. Lựa chọn và đánh giá các chiến lược backup/PITR/replication trong PostgreSQL, hiểu giới hạn của từng chiến lược.
6. Thiết kế phép đo, cảnh báo, diễn tập restore và bảng bằng chứng để xác nhận hệ thống **thực sự đáp ứng** mục tiêu.
7. Xử lý đúng các transaction Java có kết quả commit chưa xác định, giữ idempotency và đối soát khi dữ liệu được phục hồi đến một mốc cũ hơn.

Bài thuộc chương **Sao lưu và khôi phục** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học thiết kế persistence cho Java, từ mô hình dữ liệu, schema, query, index, transaction, isolation và đồng thời đến kết nối, lỗi, bảo mật, tiến hóa lược đồ, sao lưu và hiệu năng. **RPO là một hợp đồng khôi phục về dữ liệu**, cần được phối hợp giữa chủ sở hữu nghiệp vụ, đội ứng dụng, DBA và vận hành.

## 1. RPO trả lời câu hỏi nào?

**Recovery Point Objective (RPO)** là mục tiêu về **mức mất dữ liệu tối đa có thể chấp nhận**, thường được biểu diễn bằng **khoảng thời gian từ thời điểm sự cố đến điểm dữ liệu gần nhất có thể khôi phục một cách hợp lệ**.

Ví dụ: “RPO = 5 phút đối với đơn hàng đã xác nhận” nghĩa là hệ thống phải được thiết kế để khi xảy ra một sự cố **thuộc phạm vi đã định nghĩa**, mất mát dữ liệu từ các giao dịch được bảo vệ không vượt quá khoảng năm phút. Đây là **mục tiêu thiết kế và vận hành**, không phải lời khẳng định rằng chỉ cần đặt một cấu hình `5m` là mặc nhiên đạt được.

~~~text
Các thay đổi nghiệp vụ theo thời gian
                |
  13:40         13:45         13:50         13:55         14:00
    |-------------|-------------|-------------|-------------|
                  ^                                         ^
          mốc khôi phục cuối                       sự cố phát sinh
          được xác minh: 13:55                     lúc 14:00

          <---------------- 5 phút ---------------------->
          Khoảng thay đổi có nguy cơ mất khi phục hồi
          về mốc 13:55:00
~~~

Giả sử thời điểm sự cố là `T_failure` và mốc có thể phục hồi đã **được xác minh** là `T_recoverable`, chênh lệch thời gian cần đánh giá:

`Loss window = T_failure − T_recoverable`.

Ví dụ: sự cố lúc 14:00:00, tập backup/WAL liên tục mới nhất có thể phục hồi đến 13:58:30 thì **cửa sổ phục hồi là 90 giây**. Nhưng chỉ khi đã chứng minh thực sự restore được đến mốc đó; một trang giám sát ghi “backup mới nhất lúc 13:59” chưa đủ bằng chứng.

### 1.1. RPO không phải số bản ghi bị mất

RPO được biểu diễn theo thời gian nhưng hệ quả kinh doanh là những thay đổi đã xảy ra trong khoảng đó:

- Một phút cao điểm có thể có 30.000 giao dịch; một phút ban đêm có thể chỉ có vài giao dịch.
- Một đơn bị mất có thể là bản nháp có thể tạo lại; cũng có thể là giao dịch tài chính đã xác nhận với khách hàng.
- Một bản ghi thuộc database có thể gắn với chứng từ trên object storage, thông điệp trong queue hoặc thanh toán ngoài hệ thống.

Vì vậy, cần quy đổi RPO thành **rủi ro mất giao dịch, khả năng tái tạo và chi phí đối soát**, chứ không chỉ một giá trị phút/giây trong tài liệu.

### 1.2. RPO gần 0 và RPO bằng 0

`RPO = 0` thể hiện mục tiêu **không mất giao dịch đã được công nhận là hoàn tất** trong tập tình huống được bảo vệ. Đây là yêu cầu mạnh, cần xác định:

- Một giao dịch được coi là hoàn tất khi nào: khi server nhận SQL, khi database commit, hay khi client nhận xác nhận?
- Có bảo vệ được crash một node, mất một vùng, lỗi operator và corruption logic hay không?
- Những replica nào phải ghi bền trước khi trả ACK?
- Khi mất kết nối/quorum, hệ thống có được phép ngừng nhận write để giữ bảo đảm không mất dữ liệu?
- Cách xử lý giao dịch đã commit nhưng client không nhận được ACK?

**Không hứa RPO = 0 cho mọi loại thảm họa chỉ vì có synchronous replication.** Mục tiêu này luôn cần gắn với fault model, xác định điểm ACK, cơ chế fencing/failover, kiểm chứng và các rủi ro còn lại.

## 2. Phân biệt RPO, RTO, retention và độ mới dữ liệu

| Khái niệm | Câu hỏi cốt lõi | Ví dụ |
| --- | --- | --- |
| **RPO** | Được phép **mất bao nhiêu dữ liệu mới** khi khôi phục? | Tối đa 5 phút giao dịch đã ghi |
| **RTO** | Được phép **gián đoạn bao lâu** trước khi dịch vụ phục hồi? | Phục vụ lại trong 30 phút |
| **Retention** | Lưu lịch sử backup/log trong bao lâu? | Giữ khả năng PITR 14 ngày |
| **Backup interval** | Bao lâu tạo một bản backup mới? | Full backup mỗi 24 giờ |
| **Replication lag** | Replica đang chậm sau primary bao nhiêu? | Đang trễ một vài giây |
| **Data freshness** | API có thể trả dữ liệu cũ tối đa bao lâu trong vận hành? | Cache hiển thị giá trễ 10 giây |
| **SLA/SLO** | Cam kết hoặc mục tiêu dịch vụ được đánh giá theo tiêu chí nào? | 99,9% request đạt mức phục vụ quy định |

Các khái niệm có liên hệ nhưng không thay thế nhau:

- **RTO thấp không suy ra RPO thấp.** Failover sang một replica nhanh nhưng trễ 10 phút có thể khôi phục dịch vụ rất nhanh và vẫn mất dữ liệu đã ACK.
- **RPO thấp không suy ra RTO thấp.** Có WAL đủ để phục hồi đến gần thời điểm sự cố nhưng quá trình tìm máy, tải backup và replay có thể mất hàng giờ.
- **Retention 14 ngày không có nghĩa RPO 14 ngày.** Retention nói về chiều sâu lịch sử; RPO nói về độ mới của mốc phục hồi.
- **Replica lag nhỏ không chứng minh RPO đạt.** Replication có thể lỗi, replica không được chọn khi failover, hoặc dữ liệu lỗi đã nhân bản sang tất cả node.
- **Cache stale không nhất thiết là mất dữ liệu.** Nếu nguồn dữ liệu vẫn bền và có thể đọc lại, đó là vấn đề nhất quán/độ mới API, không phải bằng chứng backup bị mất.

### 2.1. Hai tình huống minh họa

**Tình huống A:** lúc 16:00 primary không còn dùng được, service chuyển sang standby trong 20 giây. Standby chỉ có những commit đến 15:55. Hệ thống có **thời gian phục vụ lại thấp** nhưng cửa sổ dữ liệu có nguy cơ mất lên đến 5 phút.

**Tình huống B:** sự cố lúc 16:00, backup vật lý và WAL đủ để khôi phục an toàn đến 15:59:59. Việc restore/replay tốn 90 phút. Cửa sổ mất dữ liệu khoảng 1 giây, nhưng thời gian gián đoạn lớn.

RPO và RTO phải được chọn **cùng nhau**, vì cơ chế giảm RPO có thể làm tăng độ trễ commit hoặc làm failover bị chặn.

## 3. Xác định RPO từ giá trị kinh doanh trước khi chọn công nghệ

Không bắt đầu bằng câu “PostgreSQL backup được mỗi mấy giờ?”. Hãy bắt đầu bằng câu “Nếu mất những thay đổi vừa được xác nhận, điều gì sẽ xảy ra?”.

Quy trình đề xuất:

1. **Liệt kê luồng nghiệp vụ:** đăng ký tài khoản, tạo đơn, thu tiền, cập nhật tồn kho, gửi thông báo, audit, báo cáo, telemetry.
2. **Xác định nguồn sự thật:** database, object storage, ledger, event log, dịch vụ thanh toán bên ngoài hoặc tập nhiều nguồn.
3. **Xác định mốc thành công:** HTTP 200/201 được gửi, transaction commit, event được phát, đối tác xác nhận hay yêu cầu được đưa vào queue?
4. **Phân loại khả năng tái tạo:** có thể phát lại event an toàn không, có log độc lập không, cần đối soát tay không?
5. **Đánh giá hậu quả mất dữ liệu:** tiền bạc, pháp lý, quyền người dùng, uy tín, khả năng lập lại và khối lượng yêu cầu cao điểm.
6. **Chọn mục tiêu theo từng nhóm dữ liệu và loại sự cố:** ví dụ đơn đã thanh toán khác với thông số đo có thể sinh lại.
7. **Thống nhất giả định và bên chịu trách nhiệm:** business owner, SRE/DBA, an ninh, ứng dụng, bên thứ ba.
8. **Định nghĩa phép kiểm chứng:** sẽ đo và diễn tập thế nào để biết mục tiêu đạt hay không?

### 3.1. Ví dụ ma trận RPO theo nghiệp vụ

Các số sau **chỉ là ví dụ để thảo luận**, không phải giá trị khuyến cáo mặc định.

| Tập dữ liệu | Hậu quả khi mất | Khả năng tạo lại | Mục tiêu RPO giả định | Câu hỏi bắt buộc |
| --- | --- | --- | --- | --- |
| Ledger thanh toán đã xác nhận | Cao, có thể ảnh hưởng tiền và đối soát | Phải dựa vào sổ độc lập hoặc đối tác | Gần 0 hoặc 0 trong fault model đã nêu | ACK nào được bảo vệ, ai là authority? |
| Đơn hàng đã xác nhận | Mất cam kết với khách | Có thể đối soát một phần qua request ID | ≤ 1 phút | Có bằng chứng request/commit độc lập không? |
| Hồ sơ khách hàng | Mất thay đổi của người dùng | Khó tái tạo chính xác | ≤ 5 phút | Có read-your-writes và audit không? |
| Bản nháp chưa gửi | Có thể phải nhập lại | Một phần có thể nhập lại | ≤ 15 phút | Người dùng đã được thông báo về autosave chưa? |
| Báo cáo tổng hợp từ nguồn còn nguyên | Có thể chạy lại | Dễ tái tính toán | ≤ 24 giờ | Có mất mã/phiên bản phép biến đổi không? |
| Log telemetry không trọng yếu | Ảnh hưởng phân tích | Có thể chấp nhận thiếu | Theo phân loại dữ liệu | Có trường nào bắt buộc lưu vì audit không? |

**Đừng gộp audit bảo mật, ledger và metric kỹ thuật vào cùng một tập chỉ vì đều nằm trong PostgreSQL.** Chúng có độ nhạy và khả năng phục hồi khác nhau. Nếu một database chứa nhiều tập dữ liệu, **chính sách bảo vệ chung phải đáp ứng nhóm có yêu cầu mạnh nhất**, hoặc tách dữ liệu để dùng chiến lược riêng.

### 3.2. Từ thời gian đến khối lượng công việc mất

Có thể ước lượng tác động **để lập kế hoạch**, không dùng thay cho đo thực:

~~~text
Số thao tác có nguy cơ mất
  ≈ số thao tác đã xác nhận mỗi giây
    × cửa sổ mất dữ liệu (giây)
~~~

Ví dụ một luồng đơn có 100 đơn/phút trong thời gian cao điểm. RPO 5 phút gợi ý **tới khoảng 500 đơn trong khoảng đó** có thể bị ảnh hưởng ở mô hình đơn giản. Đó không phải một giới hạn chắc chắn về số hàng: traffic có burst, mỗi đơn sửa nhiều bảng và có transaction khác nhau.

Nếu hậu quả của 500 đơn không thể chấp nhận, phải **giảm RPO, thay cách xác nhận nghiệp vụ hoặc xây cơ chế ghi nhận độc lập**; không giải quyết bằng việc đổi tên metric.

## 4. RPO phải gắn với loại sự cố và phạm vi mất mát

Một hệ thống “RPO = 5 phút” mà không nêu điều kiện là chưa đủ để đánh giá.

| Sự cố | Điều có thể còn nguyên | Rủi ro mất dữ liệu cần kiểm tra |
| --- | --- | --- |
| Java process crash | PostgreSQL và WAL vẫn chạy | Có request chưa COMMIT hoặc client không biết kết quả |
| PostgreSQL instance crash | Storage vẫn an toàn | WAL cục bộ đã flush theo chính sách có thể phục hồi; unflushed commit có rủi ro |
| Mất máy hoặc ổ đĩa chứa primary | Standby/backup ở failure domain khác | Replica lag, backup/WAL chưa chuyển ra ngoài |
| Mất cả availability zone/vùng | Bản sao ở vùng khác hoặc kho backup ngoài vùng | Những commit được ACK nhưng chưa ra khỏi vùng |
| Xóa nhầm dữ liệu bằng SQL | Replication có thể nhân bản lệnh xóa | Cần PITR hoặc cơ chế khôi phục logic tại trước mốc xóa |
| Migration hoặc bug ghi sai hàng loạt | Backup lịch sử có thể vẫn nguyên | Phải xác định **mốc trước khi lỗi bắt đầu**, có thể cũ hơn nhiều giờ |
| Ransomware hoặc lộ quyền quản trị | Kho backup độc lập, immutable/offline có thể còn | Backup cùng account/credential có thể bị xóa hoặc sửa |
| Restore nhầm môi trường | Backup tồn tại nhưng đích sai | Nguy cơ mất, lộ hoặc ghi đè dữ liệu |
| Mất object storage nhưng DB còn | Metadata DB vẫn có thể nguyên | File/ảnh/chứng từ gắn với hàng DB có thể không khôi phục cùng mốc |
| Failover sang standby trễ | Service còn hoạt động | Commit mới trên primary cũ có thể thiếu trên primary mới |

**RPO theo từng lớp sự cố có thể khác nhau.** Một hệ thống có thể không mất transaction khi PostgreSQL restart (với WAL cục bộ bền), nhưng mất vài phút commit nếu cả vùng primary bị mất trước khi replication/backup ngoài vùng hoàn thành.

Đối với dữ liệu quan trọng, cần nêu rõ: **RPO áp dụng cho transaction đã ACK hay mọi thao tác client đã gửi?** Các thao tác còn đang xử lý khi sự cố xảy ra không có cùng trạng thái cam kết như thao tác đã được xác nhận.

### 4.1. Corruption logic làm thay đổi cách tính

Ví dụ:

~~~text
10:00  Một job lỗi bắt đầu ghi giá sai
13:00  WAL backup vẫn đầy đủ, lưu liên tục
15:00  Phát hiện dữ liệu bị sửa sai
15:01  Backup mới nhất có thể replay đến 15:00:59
~~~

Có đủ WAL đến sát 15:01 **không** giải quyết được việc dữ liệu đã sai từ 10:00. Nếu chỉ có thể restore toàn database về 09:59, cửa sổ thay đổi cần hòa giải có thể **trên năm giờ**, dù năng lực PITR sát thời điểm hiện tại rất tốt.

Vì thế RPO đối với **hỏng logic phát hiện muộn** cần cách đánh giá riêng: khả năng nhận diện mốc dữ liệu tốt, restore vào môi trường cô lập, so sánh dữ liệu đúng/sai và phát lại những giao dịch hợp lệ sau mốc đó. Không hứa một RPO nhỏ cho mọi kiểu corruption chỉ dựa trên tần suất lưu WAL.

## 5. Năng lực khôi phục được quyết định bởi bản sao nào thực sự còn dùng được

Để tìm mốc khôi phục hợp lệ, không chỉ xem timestamp của một file backup. Cần có **chuỗi dữ liệu có thể restore**:

~~~text
        Base backup nhất quán
                 |
                 v
      WAL/redo liên tục cần thiết
                 |
                 v
      Recovery target hợp lệ
                 |
                 v
      Database khởi động và kiểm tra tốt
                 |
                 v
      Mốc cuối có thể phục hồi thật
~~~

Nếu backup cơ sở bị hỏng, thiếu khóa giải mã, không có quyền đọc object store, mất một segment WAL giữa chuỗi, hoặc restore không thể khởi động, timestamp “latest backup” không phản ánh RPO thực tế.

### 5.1. Ví dụ tính RPO theo bản sao khôi phục

| Cơ chế | Sự cố lúc | Bản sao cuối có thể phục hồi đã kiểm chứng | Cửa sổ dữ liệu có nguy cơ mất |
| --- | --- | --- | --- |
| Backup logic hằng ngày lúc 01:00 | 17:00 | 01:00 cùng ngày | 16 giờ |
| Snapshot mỗi 30 phút, nhất quán | 14:07 | 14:00 | 7 phút |
| Base backup + WAL đầy đủ tới 13:58:30 | 14:00 | 13:58:30 | 90 giây |
| Replica async được promote, đã nhận đủ commit đến 13:59:45 | 14:00 | 13:59:45 | 15 giây |
| Base backup mới nhưng thiếu WAL cần để replay | 14:00 | Chưa xác minh được | **Không được công bố RPO** |

Các mốc và số ở bảng chỉ minh họa. Trong thực tế phải xác định **thời điểm dữ liệu có thể phục hồi**, không chỉ thời điểm artifact được tạo hoặc thời điểm file xuất hiện trong kho lưu.

### 5.2. RPO thiết kế khác với khoảng mất thực tế

Gọi:

- **Target RPO:** mức tổ chức đã chấp nhận, ví dụ 5 phút.
- **Observed recoverability gap:** độ lệch hiện tại giữa mốc dữ liệu nguồn và mốc phục hồi có bằng chứng.
- **Actual data loss:** lượng giao dịch/biến đổi không còn sau **một sự cố thật** và quá trình khôi phục/đối soát.

Một backup job xanh không tự chứng minh observed recoverability gap thấp. Ngược lại, gap ở một thời điểm có thể thấp nhưng cao đột biến khi mạng đứt, archiver lỗi, hoặc backlog WAL tăng.

**Mục tiêu RPO phải được giám sát liên tục và thử trong tình huống thất bại**, không chỉ đo một giá trị trung bình đẹp trong ngày bình thường.

## 6. Chọn công nghệ tương ứng với RPO đã thống nhất

Không có một công nghệ phù hợp mọi phạm vi lỗi. Các phương án thường được kết hợp.

| Phương án | Điều bảo vệ chủ yếu | Giới hạn cần nhớ |
| --- | --- | --- |
| Export/`pg_dump` định kỳ | Bản chụp logic tới thời điểm dump | Không tự cung cấp replay WAL để PITR |
| Snapshot storage nhất quán | Trạng thái tại một thời điểm/consistency group | Cần chứng minh consistency ở database và các volume |
| Physical base backup | Cơ sở để phục hồi PostgreSQL | Muốn PITR còn cần WAL liên tục và recovery config |
| WAL archiving + PITR | Replay thay đổi từ base backup đến mốc chọn | Cần chuỗi WAL đầy đủ, archive hoạt động và diễn tập restore |
| Streaming standby async | Failover/đọc và giữ bản sao gần primary | Có thể thiếu commit đã ACK khi primary mất |
| Streaming standby sync | Giảm cửa sổ mất commit đã ACK với fault model phù hợp | Tăng latency và có thể chặn COMMIT khi không đủ standby |
| Backup offsite, immutable | Bảo vệ trước mất vùng, xóa nhầm/ransomware | Cần quyền, khóa giải mã, retention, kiểm tra phục hồi |
| Event log/ledger độc lập | Đối soát hoặc tái dựng một số luồng nghiệp vụ | Event log cũng cần RPO và thứ tự/duplicate handling riêng |

**Replication là cơ chế sao chép trạng thái, không phải backup lịch sử.** Một lệnh `DELETE` nhầm hoặc UPDATE do bug có thể được replication truyền rất nhanh. Muốn trở về trước lỗi logic, cần backup/PITR và khả năng xác định mốc khôi phục phù hợp.

### 6.1. Backup mỗi 24 giờ có RPO bao nhiêu?

Nếu mỗi ngày chỉ tạo một bản backup nhất quán và không có log/replica phục hồi bổ sung, tại thời điểm gần sát lần backup tiếp theo, khoảng thay đổi chưa được sao lưu có thể **gần 24 giờ**. Đó là **cửa sổ lý thuyết theo chu kỳ**, chưa tính job thất bại hoặc backup hỏng.

Nếu yêu cầu RPO 5 phút, lịch backup một ngày một lần không đáp ứng được mục tiêu khi primary mất hoàn toàn và chỉ còn những backup ấy. Có thể bổ sung WAL archiving/PITR hoặc một giải pháp bảo vệ tương đương.

### 6.2. Backup liên tục không phải luôn là backup sau mỗi transaction

PostgreSQL có thể archive các WAL segment đã hoàn tất hoặc khi segment được chuyển. Dù thường gọi “continuous archiving”, **độ trễ chuyển/đẩy WAL ra đích backup vẫn khác 0** và có thể tăng theo workload/sự cố.

Nếu cần giới hạn RPO ở mức phút, phải kiểm tra:

- Mức độ thường xuyên WAL được archive hoặc stream ra đích.
- Trễ upload, mạng, độ bền và khả năng truy cập kho archive.
- WAL còn đủ liên tục để replay từ base backup.
- Mốc commit nào thực sự đã được đẩy ra failure domain an toàn.
- Giới hạn cảnh báo phù hợp với RPO đã cam kết.

## 7. PostgreSQL: từ backup cơ sở đến Point-in-Time Recovery

Đối với PostgreSQL, **PITR (Point-in-Time Recovery)** thường dựa trên một **physical base backup nhất quán** và chuỗi WAL có thể replay.

~~~text
Thời gian →
       Base backup
            |
            +--- WAL A --- WAL B --- WAL C --- WAL D ...
                                      |
                                      v
                          Recovery target được chọn
~~~

Một quy trình thiết kế:

1. Tạo base backup hợp lệ theo công cụ và version hỗ trợ, ví dụ `pg_basebackup` hoặc cơ chế physical backup tương thích.
2. Cấu hình WAL archiving tới kho độc lập có quyền truy cập và retention đủ.
3. Bảo đảm archived WAL cần thiết cho backup luôn **liên tục**, không bị dọn quá sớm.
4. Giám sát WAL archive lỗi, độ trễ và dung lượng; tránh để archive bế tắc làm đầy đĩa.
5. Thường xuyên restore sang một PostgreSQL instance cô lập và replay tới một target hợp lệ.
6. Kiểm tra dữ liệu phục hồi, quyền kết nối, schema, extension, job và các phụ thuộc ngoài DB.
7. Ghi lại **mốc phục hồi cuối chứng minh được**, không chỉ số WAL segment đã copy.

`pg_dump` là logical backup hữu ích cho nhiều nhu cầu, nhưng **không phải physical base backup có thể kết hợp tùy ý với WAL để thực hiện PostgreSQL PITR**. Cần phân biệt công cụ backup logic với cơ chế khôi phục vật lý/WAL.

### 7.1. WAL giúp RPO như thế nào?

WAL (*Write-Ahead Log*) ghi thông tin cần thiết để database phục hồi thay đổi và bảo đảm thứ tự ghi theo cấu hình. Sau khi có base backup, WAL cho phép phục hồi trạng thái tiến xa hơn thời điểm tạo backup.

Một ví dụ:

~~~text
01:00  Base backup nhất quán
       |
       +--> WAL được archive liên tục trong ngày
       |
13:58  Đoạn WAL cuối đã được bảo vệ ở kho ngoài vùng
14:00  Vùng chứa primary bị mất

Nếu chuỗi WAL từ backup tới 13:58 hợp lệ:
có thể hướng tới mốc phục hồi khoảng 13:58,
thay vì buộc quay về 01:00.
~~~

Phải tính cả **WAL bắt buộc để làm base backup nhất quán**. Không được chọn một file backup chỉ vì nó có tên đúng ngày rồi áp bất kỳ tập WAL không liên tục nào.

### 7.2. Cấu hình và thuật ngữ PostgreSQL

Các tham số/khái niệm thường liên quan:

- `wal_level`: mức thông tin WAL phù hợp với nhu cầu replication/logical decoding.
- `archive_mode` và `archive_command` hoặc `archive_library`: cơ chế chuyển WAL hoàn tất tới kho archive được cấu hình.
- `archive_timeout`: có thể buộc chuyển WAL segment theo khoảng thời gian để giảm độ trễ chờ segment hoàn tất; đổi lại có thể tăng số lượng/khối lượng WAL archive và overhead.
- `pg_basebackup`: công cụ tạo physical base backup.
- `restore_command` và `recovery_target_time`: thành phần cấu hình phục hồi từ archive tới một mốc thời gian được chọn.
- `pg_stat_archiver`: thống kê WAL archiving của PostgreSQL.

**Không sao chép các giá trị cấu hình minh họa vào production mà không thử nghiệm.** `archive_timeout` là một công cụ ảnh hưởng nhịp WAL segment switch, **không phải cam kết RPO**. Thay đổi cấu hình backup/archiving còn liên quan đĩa, object store, quyền, chi phí và tuổi thọ WAL.

Trong một phòng lab restore cô lập, các tham số có thể mang dạng khái niệm:

~~~text
restore_command = '<lệnh lấy WAL đã lưu từ kho archive an toàn>'
recovery_target_time = '2026-11-22 13:58:30+07'
recovery_target_action = 'pause'
~~~

Đây **không phải cấu hình chạy được nguyên xi**. Vị trí đặt recovery configuration, tín hiệu recovery và cơ chế fetch WAL phụ thuộc phiên bản PostgreSQL, backup tool và kịch bản phục hồi. Lệnh restore thực tế phải được kiểm tra để không xóa/ghi đè production hay đưa dữ liệu ra một môi trường có quyền yếu hơn.

### 7.3. Theo dõi archiver bằng SQL

Ví dụ truy vấn:

~~~sql
SELECT now() AS observed_at,
       archived_count,
       last_archived_wal,
       last_archived_time,
       failed_count,
       last_failed_wal,
       last_failed_time
FROM pg_stat_archiver;
~~~

Các giá trị giúp phát hiện archiver không tiến triển hoặc thất bại. Nhưng:

- `last_archived_time` là thời điểm thống kê archive hoàn tất, **không phải timestamp commit của transaction cuối đã được bảo vệ**.
- Khi database ít ghi, WAL có thể chưa cần chuyển segment mới; không thể kết luận RPO xấu chỉ dựa trên khoảng thời gian giữa hai event archive.
- Không suy ra một recovery point hợp lệ nếu WAL ở kho archive không đọc được, đã bị xóa hoặc thiếu đoạn.
- Quyền xem thống kê, tên cột và cấu hình cụ thể cần kiểm tra trên phiên bản đang sử dụng.

Với RPO nghiêm ngặt, cần hệ đo end-to-end về **tiến độ log có thể khôi phục**, khả năng truy cập backup và kết quả restore drill.

## 8. Replication và RPO khi primary hỏng

### 8.1. Asynchronous replication

Một primary có thể xác nhận commit ngay sau khi đáp ứng điều kiện durability cục bộ, trước khi standby nhận hoặc flush WAL tương ứng.

~~~text
Java app         PostgreSQL primary         Standby
   |                    |                      |
   |---- COMMIT ------->|                      |
   |                    | flush WAL local      |
   |<--- COMMIT OK -----|                      |
   |                    |--- WAL đang truyền ->|
   |                    X primary/vùng mất     |
   |                                           |
   |                    Standby có thể thiếu commit
~~~

Nếu chỉ còn standby và nó chưa nhận đủ WAL, việc promote standby có thể làm mất **commit đã được client xác nhận**. Độ trễ replica vì thế là tín hiệu quan trọng đối với RPO của **failover**, nhưng phải đánh giá trên WAL đã thực sự tồn tại ở node được chọn để promote.

Một request Java đã nhận `COMMIT OK` không chứng minh commit đó đã có ở standby bất đồng bộ.

### 8.2. Synchronous replication

Khi PostgreSQL được cấu hình synchronous standby đúng cách, primary có thể chờ các xác nhận từ standby trước khi trả kết quả commit.

Nhưng cần phân biệt:

- `synchronous_commit = on` thường yêu cầu WAL commit record được flush cục bộ; **nếu có cấu hình synchronous standby phù hợp**, nó còn chờ WAL được flush trên số standby cần thiết.
- `remote_write` có thể chỉ chờ standby ghi WAL tới bộ đệm hệ điều hành, **không đồng nghĩa flush bền trên thiết bị lưu trữ**.
- `remote_apply` chờ thêm mức áp dụng WAL phía standby, liên quan đến khả năng đọc thấy giao dịch sau khi phản hồi.
- `synchronous_commit = off` có thể trả ACK trước khi commit WAL được flush bền cục bộ, tạo cửa sổ mất commit ngay cả khi cùng một máy gặp crash.

Cùng với `synchronous_standby_names`, các tham số trên quyết định **ACK nghĩa là gì**. Synchronous replication có thể tăng độ trễ và giảm availability khi không đủ standby được chọn có thể trả ACK. Đó là đánh đổi hợp lý **nếu yêu cầu RPO của nghiệp vụ biện minh cho chi phí này**.

**Không suy rằng synchronous standby tự thực hiện leader election/fencing an toàn.** Khi failover, cần đảm bảo chọn replica đạt trạng thái cần thiết, ngăn primary cũ tiếp tục nhận ghi (split-brain) và không promote một bản sao thiếu commit đã ACK.

### 8.3. Một truy vấn theo dõi replication

Trên primary PostgreSQL, có thể xem:

~~~sql
SELECT application_name,
       state,
       sync_state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn,
       write_lag,
       flush_lag,
       replay_lag
FROM pg_stat_replication;
~~~

**Cảnh báo khi diễn giải:**

- `write_lag`, `flush_lag`, `replay_lag` có thể là NULL và không phải phép đo trực tiếp “bao nhiêu giây dữ liệu sẽ mất nếu failover ngay bây giờ”.
- LSN là vị trí trong dòng WAL; chênh lệch byte LSN **không tương đương trực tiếp với thời gian hoặc số transaction**.
- Replica còn hoạt động có thể đã nhận log nhưng chưa flush hoặc chưa replay.
- Tại sự cố thật, cần biết **standby nào được promote**, mức ACK của các transaction và tập WAL của standby đó.

Chỉ số replication giúp phát hiện nguy cơ, nhưng để công bố đáp ứng RPO cần phối hợp với chính sách promote/fencing và fault-injection test.

## 9. Những tập dữ liệu ngoài DB có làm RPO hiệu dụng tệ hơn không?

Một nghiệp vụ có thể chứa nhiều trạng thái:

~~~text
Đặt hàng của khách
      |
      +-- orders / payments trong PostgreSQL
      +-- chứng từ PDF trong object storage
      +-- sự kiện OrderConfirmed trong outbox/queue
      +-- thông báo tới cổng thanh toán
      +-- projection cho tìm kiếm và báo cáo
~~~

Nếu database phục hồi tới 13:59 nhưng object storage chỉ phục hồi tới 13:30, trạng thái đơn hàng và chứng từ **không cùng điểm nhất quán**. RPO nghiệp vụ phải tính theo dữ liệu **thực sự cần để khôi phục luồng công việc**, không chỉ DB chính.

### 9.1. Phân loại từng thành phần theo khả năng tạo lại

| Thành phần | Có thể tái tạo không? | Quyết định khi lập RPO |
| --- | --- | --- |
| Đơn hàng và trạng thái đã xác nhận | Thường không nên đoán/tự tái tạo từ cache | Bảo vệ bền, đối soát theo request ID |
| File đính kèm gốc của khách | Không thể tái tạo nếu không có bản sao | Có RPO và retention riêng, liên kết nhất quán với DB |
| Search index | Thường xây lại được từ DB/source | RPO thấp có thể không cần, nhưng RTO rebuild phải chấp nhận |
| Cache | Thường làm mới được | Không coi cache như backup |
| Event outbox | Có thể quan trọng để tái phát sự kiện | Backup nhất quán cùng transaction DB |
| Log nghiệp vụ/audit | Một số loại bắt buộc giữ và khó tạo lại | Xác định RPO/retention riêng và quyền bất biến |
| Dashboard aggregate | Có thể tính lại từ nguồn còn nguyên | RPO có thể nới rộng, nhưng tính đến RTO tái tạo |

**Nếu hai kho dữ liệu cùng là authority cho một nghiệp vụ**, phải có phương án khôi phục/đối soát giữa chúng. Không thể chọn RPO mỗi nơi độc lập rồi giả định toàn nghiệp vụ luôn nhất quán.

### 9.2. Outbox giúp giữ lịch sử sự kiện theo transaction

Giả sử tạo đơn và ghi sự kiện vào **cùng transaction PostgreSQL**:

~~~sql
BEGIN;

INSERT INTO orders (tenant_id, request_key, status)
VALUES (42, 'req-001', 'CONFIRMED');

INSERT INTO outbox_events (tenant_id, request_key, event_type)
VALUES (42, 'req-001', 'OrderConfirmed');

COMMIT;
~~~

Ví dụ giả định các bảng/ràng buộc đã được định nghĩa ở hệ thống thực. Nếu transaction commit, đơn hàng và outbox row được lưu trong **cùng một transaction DB**. Khi restore tới cùng recovery point, hai bản ghi đi cùng nhau.

Nhưng worker phát event có thể đã gửi `OrderConfirmed` trước khi xảy ra sự cố, trong khi database khi restore được đưa về mốc trước event đó. Hệ ngoài có thể đã xử lý tác dụng phụ. Do đó:

- Event phải có ID/idempotency key đủ ổn định.
- Consumer phải xử lý phát lại an toàn, thường theo chính sách **at-least-once**.
- Hệ thống cần đối soát sự kiện/side effect ngoài DB sau restore.
- Không coi việc “restore DB rồi replay mọi outbox” là hoàn toàn an toàn nếu consumer không chống trùng.

RPO thấp của database là điều kiện quan trọng, nhưng **tính đúng đắn của nghiệp vụ phân tán** còn yêu cầu thiết kế idempotency và reconciliation.

## 10. Java/JDBC: giao dịch đã ACK, chưa ACK và kết quả chưa xác định

Ứng dụng Java nên phân biệt ba tình huống:

1. **Đã nhận kết quả commit thành công:** dưới giả định primary hợp lệ, transaction đã được DB xác nhận theo cấu hình của nó; vẫn cần xem replication/failover protection.
2. **Đã nhận lỗi SQL xác định trước commit và rollback thành công:** có bằng chứng transaction không hoàn tất; có thể retry theo lỗi và hợp đồng nghiệp vụ.
3. **Mất kết nối hoặc timeout khi chờ COMMIT:** client không biết chắc database đã commit hay chưa. Đây là **unknown outcome**.

Ví dụ điều khiển transaction bằng JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderWriter {
    private final DataSource dataSource;

    public OrderWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(
            long tenantId, String requestKey, long amount)
            throws SQLException {

        String sql = """
            INSERT INTO orders
                (tenant_id, request_key, amount)
            VALUES (?, ?, ?)
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    statement.setLong(1, tenantId);
                    statement.setString(2, requestKey);
                    statement.setLong(3, amount);
                    statement.executeUpdate();
                }
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đây là **ví dụ điều khiển transaction**, giả định bảng và các ràng buộc được tạo ở môi trường thực, trong đó có unique key `(tenant_id, request_key)`. Nó **không tự giải quyết** commit không xác định; ngay cả sau khi catch gọi rollback, commit có thể đã hoàn tất ở server.

### 10.1. Khi failover làm mất transaction đã xác nhận

Giả sử ứng dụng đã nhận `COMMIT OK` từ primary nhưng backup/standby phục hồi về thời điểm **trước** transaction đó. Client có thể gọi lại vì không thấy đơn hàng nữa, hoặc hệ thống bên ngoài vẫn giữ biên lai cũ.

Cách xử lý cần có:

- **Request key không thay đổi** giữa các lần thử của cùng yêu cầu.
- Ràng buộc duy nhất tại DB theo phạm vi nghiệp vụ.
- Bằng chứng nghiệp vụ ngoài DB có thể đối soát, như transaction ID đối tác hoặc event log độc lập.
- Quy trình khôi phục không kết luận “chưa từng xảy ra” chỉ vì bản ghi không có trong DB đã bị đưa về mốc cũ.
- Khi phát lại, kiểm tra tác dụng phụ đã xảy ra và không lặp thanh toán, gửi hàng, trừ tiền.

**RPO thiết kế không thay thế giao thức idempotency.** Ngay cả RPO gần 0 vẫn có request mất ACK hoặc HTTP response bị mất. Ngược lại, idempotency không tự giúp khôi phục dữ liệu gốc đã mất nếu không còn bằng chứng độc lập.

### 10.2. Chọn một mốc “đơn hàng thành công” rõ ràng

Một API đặt hàng cần quy định rõ:

~~~text
RECEIVED   -> đã nhận request, chưa chắc ghi
PROCESSING -> đang xử lý transaction
COMMITTED  -> database commit đã được xác nhận
CONFIRMED  -> các điều kiện nghiệp vụ về xác nhận đạt
UNKNOWN    -> chưa thể kết luận, cần tra cứu/đối soát
~~~

Không dùng `HTTP 202 Accepted` để khẳng định đơn đã lưu bền; nó có thể chỉ nghĩa hệ thống đã nhận yêu cầu. Nếu phát `HTTP 201 Created`, cần có hợp đồng về những điều kiện đã được thỏa trước khi gửi phản hồi.

Khi hệ thống phục hồi sau thảm họa, danh sách request từng được ACK ngoài DB có thể là cơ sở để xác định dữ liệu cần phát lại/đền bù. Tổ chức phải quyết định liệu mất những ACK đó có được tính là vi phạm RPO nghiệp vụ hay không.

## 11. Diễn tập: chứng minh mốc có thể khôi phục chứ không chỉ dựa vào dashboard

RPO **không thể được xác nhận chỉ bằng việc job backup chạy exit code 0**. Cần thử restore, đọc dữ liệu và so sánh mốc.

### 11.1. Quy trình restore drill an toàn

Trong lab hoặc môi trường phục hồi **cô lập khỏi production**:

1. Chọn kịch bản lỗi và yêu cầu RPO, ví dụ “mất hoàn toàn primary region, khôi phục từ backup/WAL ngoài vùng”.
2. Ghi dấu một loạt transaction thử nghiệm có `request_key`, timestamp và sequence/ID tăng; định nghĩa mốc ACK.
3. Xác nhận các artifact backup/WAL ở **đích phục hồi thực**, không dùng bản còn nằm trên primary sắp giả định bị mất.
4. Cô lập nguồn theo kịch bản (không phá production); ngừng điểm ghi hoặc chốt timestamp/LSN cần đo.
5. Dựng PostgreSQL instance mới trong vùng được phép với credential và KMS access đúng.
6. Restore base backup và replay WAL tới target hợp lệ hoặc promote standby được thử nghiệm.
7. Kiểm tra DB start, schema, transaction consistency, chuỗi ID/record, quyền kết nối và sự tồn tại của dữ liệu phụ thuộc.
8. Xác định **transaction cuối cùng đã ACK mà vẫn còn trong hệ khôi phục**, và những transaction ACK thiếu.
9. Tính cửa sổ dữ liệu bị mất so với mốc sự cố; đối chiếu với mục tiêu RPO.
10. Thử đối soát với hệ ngoài, outbox và object storage nếu nghiệp vụ phụ thuộc.
11. Ghi số liệu, nguyên nhân thiếu/khác và những cải tiến cần thực hiện.
12. Hủy hoặc bảo vệ môi trường restore theo chính sách vì nó có thể chứa dữ liệu nhạy cảm.

Không coi một backup “restore được tới trạng thái database khởi động” là đã đủ nếu dữ liệu nghiệp vụ thiếu, quyền tenant sai hoặc file đính kèm không khớp.

### 11.2. Ví dụ phép đo bằng checkpoint dữ liệu

Trên môi trường test, dùng bảng kiểm tra (không phải thay thế cơ chế backup chính):

~~~sql
CREATE TABLE recovery_probe (
    probe_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    written_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Worker ghi từng probe, chỉ coi probe là **được xác nhận** khi transaction commit trả thành công; bộ giám sát lưu bằng chứng ACK ở vị trí độc lập với database đang kiểm thử.

Sau restore:

~~~sql
SELECT MAX(probe_id) AS latest_recovered_probe,
       MAX(written_at) AS latest_recovered_record_time,
       COUNT(*) AS recovered_count
FROM recovery_probe;
~~~

**Đừng dùng một mình `MAX(written_at)` làm chứng minh RPO**: timestamp khi INSERT không nhất thiết là timestamp COMMIT; transaction có thể chạy lâu, đồng hồ có lệch và thứ tự ID không hoàn toàn phản ánh thứ tự commit. Cần đối chiếu probe với **nhật ký ACK/commit order đáng tin ở ngoài failure domain**, kiểm tra khoảng trống và thời điểm sự cố.

Nếu source đã có cơ chế đánh dấu LSN/timeline hợp lệ hoặc log nghiệp vụ bền khác, dùng chúng theo giao thức nhất quán đã thiết kế. Nhiệm vụ là **chứng minh những cam kết nào còn/thiếu**, không chỉ tìm hàng có timestamp lớn nhất.

## 12. Giám sát RPO liên tục

Một SLO RPO cần có tín hiệu sớm trước khi thảm họa xảy ra.

| Nhóm tín hiệu | Cần quan sát | Lý do |
| --- | --- | --- |
| Backup | Lần base backup mới nhất **đã kiểm chứng**, checksum, khả năng đọc | Tránh chỉ nhìn backup job “success” |
| WAL archive | Tốc độ archive, segment thiếu, lỗi, backlog, tuổi artifact chưa gửi | Phát hiện cửa sổ phục hồi tăng |
| Replica | Sent/write/flush/replay position, trạng thái synchronous standby | Đánh giá nguy cơ mất ACK khi failover |
| Storage | Độ bền và tính sẵn sàng kho ngoài vùng, quyền/KMS, object lock | Backup có thể không truy cập được lúc cần |
| Retention | Backup + WAL đủ để khôi phục các mốc trong thời gian giữ lịch sử | Không xóa WAL còn cần cho base backup |
| Restore drill | Thời gian restore, mốc dữ liệu đạt, checksum/kiểm tra nghiệp vụ | Chứng minh có thể khôi phục thật |
| App nghiệp vụ | ACK request ID, unknown COMMIT, idempotency duplicate, reconciliation backlog | Biết hậu quả ở cấp giao dịch |
| Multi-system | Đồng bộ DB/object storage/event log, sai lệch và reprocess status | Không bỏ sót dữ liệu ngoài DB |

### 12.1. Cảnh báo không được gây hiểu lầm

Một cảnh báo có ích thường phân biệt:

- **Tín hiệu nguy cơ:** archive bị lỗi hai lần; lag tăng; standby rớt.
- **Mức bảo vệ suy giảm:** chưa chứng minh được WAL gần nhất đã ra khỏi failure domain trong giới hạn.
- **Vi phạm mục tiêu đã đo:** bài restore hoặc kịch bản fault injection chứng minh khoảng dữ liệu bị mất vượt RPO.

Không dựa trên một metric đơn lẻ như `now() - last_archived_time` để công bố RPO: ở hệ ít ghi, các segment có thể không chuyển thường xuyên mà không có transaction cần bảo vệ; ở hệ ghi nhiều, một segment đã archive cũng không nói tất cả dependency đã bền.

Cần định nghĩa **cách tính progress của nguồn và bản sao** theo workload/engine, và bảo đảm cảnh báo bao gồm trường hợp monitoring cũng gặp lỗi.

## 13. Ví dụ thiết kế RPO cho ba luồng

### 13.1. Danh mục sản phẩm: RPO 15 phút

Giả định giá và mô tả có lịch sử thay đổi riêng, có thể nhập lại một phần. Mục tiêu minh họa RPO ≤ 15 phút khi mất primary region.

Phương án có thể gồm physical backup định kỳ, WAL archive offsite có nhịp/độ trễ phù hợp, giữ bản backup đủ lâu và một quy trình restore có thể đo được. Vì giá chốt ở đơn hàng cần chính xác hơn danh mục hiển thị, **không dùng RPO nới rộng của catalog để áp vào đơn đã xác nhận**.

Kiểm chứng: chạy probe theo workload, ngắt nguồn trong lab, restore chỉ từ artifact offsite, kiểm tra lịch sử giá và dữ liệu phụ thuộc.

### 13.2. Đơn hàng đã xác nhận: RPO ≤ 1 phút

Đòi hỏi nghiêm hơn: snapshot 30 phút một lần có thể không đủ nếu không có log bổ sung. Có thể cần WAL liên tục, standby ngoài vùng, lag control, đối soát bằng request key và quy trình chặn xác nhận nếu trạng thái bảo vệ suy giảm quá mức.

Phải định nghĩa **khi nào một đơn được coi đã xác nhận**: commit cục bộ hay chỉ sau khi có đủ bằng chứng lưu ở failure domain mục tiêu? Cơ chế kỹ thuật phải khớp với lời hứa với khách hàng.

### 13.3. Ledger quan trọng: RPO = 0 trong phạm vi mất một node

Nếu nghiệp vụ không chấp nhận mất bất kỳ transaction đã ACK nào khi một node mất, có thể lựa chọn cơ chế commit chờ một thành viên khác trong failure domain phù hợp, failover có fencing, log idempotency và đối soát độc lập.

Nhưng nếu yêu cầu mở rộng sang **mất đồng thời cả vùng**, hoặc **corruption logic nhiều giờ không phát hiện**, thiết kế phải được đánh giá lại. Một hệ thống có RPO bằng 0 đối với mất một node chưa chắc đạt 0 với mọi kiểu lỗi.

Không đánh đổi “đạt RPO = 0” lấy việc **luôn ACK ngay cả khi bản sao cần bảo vệ không sẵn sàng**. Trong trường hợp thiếu điều kiện đảm bảo, đôi khi hành vi đúng là chặn/xếp hàng/chưa xác nhận yêu cầu và công khai trạng thái cho client.

## 14. Chi phí, hiệu năng và lựa chọn đánh đổi

Càng yêu cầu dữ liệu gần thời điểm sự cố, hệ thống thường càng cần:

- Sao chép/ghi log với tần suất cao hơn, kho lưu trữ bền và vùng lỗi độc lập.
- Network băng thông và latency phù hợp, giám sát replication/archiving chặt hơn.
- Nhiều tài nguyên dự phòng và quy trình failover có kiểm soát.
- Khả năng restore theo từng thời điểm và giữ WAL đúng retention.
- Test, vận hành on-call, cảnh báo và xử lý incident chuyên sâu.
- Giao thức idempotency/reconciliation giữa các dịch vụ.

Một số đánh đổi điển hình:

| Quyết định | Được gì | Phải trả giá gì |
| --- | --- | --- |
| Rút ngắn nhịp copy/WAL bảo vệ | Thu hẹp cửa sổ dữ liệu chưa sao chép | Nhiều I/O, network, storage operation |
| Dùng synchronous standby | Tăng bảo vệ commit đã ACK với fault model phù hợp | Commit latency, nguy cơ chờ khi standby mất |
| Giữ WAL/PITR dài hơn | Có thể quay về trước lỗi phát hiện muộn | Tốn dung lượng, quản trị retention, bảo mật |
| Nhiều vùng địa lý | Chống mất một vùng | Chi phí, độ trễ, failover và consistency phức tạp |
| Tách dữ liệu theo mức độ quan trọng | Phương án riêng cho ledger, báo cáo, telemetry | Tăng vận hành, cần bảo vệ giao dịch/phụ thuộc xuyên kho |
| Chấp nhận RPO lớn cho dữ liệu tái tạo được | Giảm chi phí sao chép | Tăng thời gian reprocess; phải có nguồn để tái tạo |

Không đặt RPO cực thấp cho mọi bảng “cho an toàn” mà chưa tính lợi ích và chi phí. Ngược lại, không nới RPO của dữ liệu khách hàng chỉ vì chi phí backup thấp hơn nếu cam kết nghiệp vụ không cho phép mất các giao dịch đã ACK.

## 15. Những ngộ nhận thường gặp

**“RPO là thời gian hệ thống được phép ngừng hoạt động.”** Đó là RTO. RPO nói về điểm dữ liệu có thể khôi phục.

**“Backup 24 giờ/lần nghĩa là luôn mất 24 giờ dữ liệu.”** Khoảng mất thực tế phụ thuộc thời điểm sự cố và mốc backup còn dùng được; gần cuối chu kỳ có thể gần 24 giờ.

**“Backup thành công nghĩa là đảm bảo RPO.”** Chỉ restore và kiểm chứng chuỗi dữ liệu hợp lệ mới đủ bằng chứng.

**“Có replica nên không cần backup.”** Replica có thể nhân bản DELETE/corruption; không cung cấp lịch sử và cơ chế phục hồi tùy ý.

**“Async replica trễ 1 giây nghĩa là chắc chắn chỉ mất đúng 1 giây.”** Lag là tín hiệu, không phải chứng minh mốc ACK đã có trên standby được promote.

**“Có synchronous replication thì RPO = 0 cho mọi thảm họa.”** Cần định nghĩa ACK, standby, storage durability, failure domain, failover/fencing và lỗi logic.

**“WAL archive bật rồi là PITR dùng được.”** Phải có base backup hợp lệ, WAL liên tục, retention, quyền/KMS và restore drill.

**“RPO 5 phút là giữ backup trong 5 phút.”** Nhầm RPO với retention.

**“Một backup có timestamp mới là đủ.”** File mới có thể hỏng, thiếu WAL, không giải mã được hoặc nằm trong vùng đã mất.

**“Timestamp mới nhất trong DB restore chứng minh giao dịch cuối đã được bảo vệ.”** Timestamp record và thứ tự commit có thể khác; phải đối chiếu bằng chứng ACK.

**“Khôi phục PostgreSQL là khôi phục toàn bộ đơn hàng.”** Object storage, queue, payment gateway và event consumer có thể lệch mốc.

**“Restore trước lúc bug xảy ra chắc chắn đạt RPO 1 phút.”** Nếu bug phát hiện muộn, phục hồi về trước bug có thể bỏ nhiều giờ thay đổi hợp lệ; cần đối soát và phục hồi chọn lọc.

**“Java nhận SQLException nên DB chắc chắn chưa commit.”** Mất phản hồi commit tạo trạng thái chưa xác định; retry phải idempotent.

**“RPO bằng 0 nghĩa là mọi request đã gửi đều không thể mất.”** Phải tách request chưa hoàn tất khỏi transaction đã được xác nhận theo hợp đồng.

**“RPO chỉ là chỉ số vận hành DB.”** Nó là quyết định nghiệp vụ liên quan quyền khách hàng, tiền, pháp lý, rủi ro và trải nghiệm.

## 16. Bài tập vận dụng

### Bài 1 — tính cửa sổ khôi phục

Một hệ thống gặp sự cố lúc 18:00. Có bản base backup lúc 01:00 và chuỗi WAL archive hợp lệ đến 17:57:20.

1. Nếu restore được đến 17:57:20, cửa sổ mất dữ liệu theo thời gian là bao nhiêu?
2. RPO mục tiêu là 2 phút có đạt theo **kịch bản đang giả định** không?
3. Nếu WAL ở đích archive bị thiếu một segment trước 17:57:20, kết luận có thay đổi không?

*Gợi ý:* Chênh lệch từ 17:57:20 đến 18:00:00 là 2 phút 40 giây; lớn hơn mục tiêu 2 phút. Khi chuỗi WAL thiếu, không được khẳng định đã có recovery point này.

### Bài 2 — phân biệt RPO và RTO

Một standby được promote trong 15 giây nhưng thiếu 4 phút transaction đã ACK; phương án PITR phục hồi đến sát sự cố 10 giây nhưng phải restore trong 75 phút. Hãy so sánh RPO/RTO của hai phương án và đề xuất cách trình bày đánh đổi với nghiệp vụ.

### Bài 3 — xác định RPO theo dữ liệu

SaaS lưu đơn hàng, ledger, file đính kèm, search index và dashboard. Hãy xác định nguồn sự thật của từng tập dữ liệu, khả năng tái tạo, hậu quả mất mát và RPO mục tiêu. Nếu database có thể restore gần thời điểm sự cố nhưng file đính kèm chỉ có backup hôm qua, API đặt hàng đã sẵn sàng phục vụ đầy đủ chưa?

### Bài 4 — phân tích replication

Primary PostgreSQL dùng async standby. Một transaction được client xác nhận xong, primary mất trước khi WAL tới standby. Nêu điều gì có thể mất và vì sao replica lag không phải bảo đảm RPO tuyệt đối. Sau đó so sánh với synchronous standby khi standby không phản hồi.

### Bài 5 — thử recovery drill

Thiết kế một bài diễn tập chỉ dùng artifact ở kho ngoài vùng. Nêu cách tạo dữ liệu probe, ghi nhận mốc ACK độc lập, restore, kiểm tra WAL liên tục, tính dữ liệu thiếu và ghi lại bằng chứng. Vì sao chỉ kiểm tra `pg_stat_archiver` là chưa đủ?

### Bài 6 — xóa nhầm phát hiện muộn

Job lỗi bắt đầu xóa dữ liệu lúc 09:00, bị phát hiện lúc 15:00. WAL archive liên tục và RPO hạ tầng theo sự cố mất đĩa là 1 phút. Hãy giải thích tại sao restore toàn database về 08:59 có thể ảnh hưởng sáu giờ thay đổi hợp lệ, và đề xuất phục hồi chọn lọc/đối soát.

### Bài 7 — idempotency sau restore

Client A đã nhận xác nhận đơn hàng trước sự cố; DB được restore về một điểm chưa chứa đơn này. Trong khi đó cổng thanh toán đã thu tiền và consumer đã phát thông báo. Hãy thiết kế quy trình đối soát với `request_key`, ID thanh toán và outbox, đảm bảo không thu tiền hay giao hàng hai lần.

### Bài 8 — quyết định chi phí

Một sản phẩm có ba nhóm dữ liệu: ledger quan trọng (mục tiêu 0 trong phạm vi mất một node), đơn hàng (mục tiêu ≤ 1 phút), telemetry có thể tạo lại (mục tiêu ≤ 1 ngày). Chọn backup, replication, retention và test khác nhau; giải thích vì sao không nên chỉ cấu hình một thông số backup cho cả ba nhóm.

## Ghi nhớ

**RPO là mục tiêu về mức mất dữ liệu có thể chấp nhận khi khôi phục, không phải thời gian khởi động lại dịch vụ hay chu kỳ backup.** Để chọn RPO, bắt đầu từ các giao dịch đã được xác nhận, hậu quả mất mát, khả năng tái tạo, dữ liệu phụ thuộc và fault model. Sau đó mới thiết kế base backup, WAL/PITR, replication, backup ngoài vùng, retention và failover phù hợp.

Trong hệ thống Java/PostgreSQL, hãy đo **điểm dữ liệu thực sự có thể khôi phục**, diễn tập từ artifact tại đích phục hồi, giám sát lag/backup và so sánh với bằng chứng commit/ACK. **Chỉ một transaction đã được bảo vệ theo đúng hợp đồng mới được coi là an toàn trước loại sự cố đã định nghĩa**; khi mất phản hồi commit hoặc phục hồi về một mốc cũ, cần idempotency và đối soát xuyên hệ thống. RPO đáng tin là một mục tiêu đã được thống nhất, có giới hạn rõ ràng và được kiểm chứng — không phải con số được suy ra từ cấu hình.
