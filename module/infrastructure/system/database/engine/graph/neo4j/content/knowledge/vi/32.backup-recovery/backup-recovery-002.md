# Đặt mục tiêu RPO, RTO và chính sách lưu giữ bản sao cho Neo4j

## 1. Sao lưu chỉ có ý nghĩa khi gắn với khả năng phục hồi

Trong Neo4j, dữ liệu nghiệp vụ được lưu thành **property graph** gồm node, relationship, label và property. Ví dụ dịch vụ quản lý dự án có node `:AppUser`, `:Project` cùng relationship `:MEMBER_OF`. Một sự cố có thể làm mất hoặc hỏng database, khiến ứng dụng Java/Spring Data Neo4j không còn truy vấn được graph. **Một file backup tồn tại không tự chứng minh hệ thống có thể khôi phục đúng thời hạn.**

Chính sách sao lưu cần trả lời ba câu hỏi **khác nhau**:

1. **RPO — Recovery Point Objective:** nếu xảy ra sự cố, doanh nghiệp chịu được mất tối đa bao nhiêu thời gian cập nhật dữ liệu?
2. **RTO — Recovery Time Objective:** từ khi sự cố bắt đầu đến khi dịch vụ được phục hồi ở mức đã cam kết, tối đa được mất bao lâu?
3. **Retention — chính sách lưu giữ:** bản sao nào, trong bao lâu và tại đâu phải còn khả dụng để đáp ứng vận hành, điều tra sai sót, an toàn thông tin và nghĩa vụ lưu trữ?

Ba đại lượng có liên quan nhưng **không thay thế cho nhau**. Sao lưu mỗi 15 phút không có nghĩa khôi phục trong 15 phút; giữ bản sao 90 ngày không có nghĩa có thể phục hồi đến **mọi thời điểm** trong 90 ngày.

### 1.1. Phân biệt mục tiêu và kết quả đo thực tế

| Khái niệm | Đơn vị thường dùng | Ví dụ | Điều cần xác minh |
| --- | --- | --- | --- |
| **RPO mục tiêu** | phút/giờ | 15 phút | Điểm dữ liệu có thể khôi phục không cũ quá 15 phút so với sự cố |
| **RPO thực tế** | phút/giờ | 12 phút | Thời điểm commit cuối cùng **thực sự khôi phục được** |
| **RTO mục tiêu** | phút/giờ | 2 giờ | Dịch vụ đáp ứng tiêu chí sẵn sàng không muộn hơn 2 giờ sau sự cố |
| **RTO thực tế** | phút/giờ | 1 giờ 38 phút | Đo từ sự cố tới khi ứng dụng và dữ liệu đã được nghiệm thu |
| **Retention** | ngày/tháng/năm | 35 ngày | Có ít nhất một chuỗi bản sao hợp lệ đáp ứng cửa sổ phục hồi cần giữ |

**RPO = 0** nghĩa là không chấp nhận mất transaction đã commit. Đây là mục tiêu rất khó và thường cần kiến trúc/đảm bảo bổ sung bên cạnh backup định kỳ. **RTO = 0** nghĩa là không chấp nhận gián đoạn; một quy trình restore truyền thống không thể tự cam kết điều đó.

Neo4j cluster, replication, failover, backup và khôi phục sau sự cố là **những cơ chế khác nhau**. Cluster tăng khả dụng khi hỏng một server; backup giúp quay về dữ liệu hợp lệ khi bị xóa nhầm, lỗi phần mềm, ransomware hoặc khi sự cố tác động lên toàn cluster. **Replication có thể sao chép cả thao tác xóa sai**, nên không thay thế lịch sử bản sao độc lập.

## 2. Cách tính và kiểm chứng RPO

### 2.1. Một dòng thời gian cụ thể

Giả sử nguồn Neo4j liên tục nhận transaction cập nhật node/relationship:

```text
10:00         10:15         10:30         10:42
  |-------------|-------------|-------------X  Sự cố
  FULL       DIFF 1        DIFF 2
                              ^
                     Điểm phục hồi cuối
```

Nếu `DIFF 2` hoàn tất thành công, chứa đầy đủ transaction tới **10:30**, và toàn chuỗi từ FULL đến DIFF 2 đều còn dùng được, thì:

```text
RPO thực tế = 10:42 - 10:30 = 12 phút
```

Với **RPO mục tiêu 15 phút**, trường hợp này đạt. Tuy nhiên, nếu DIFF 2 bị lỗi và chỉ khôi phục được đến **10:15** thì:

```text
RPO thực tế = 10:42 - 10:15 = 27 phút  ->  Vi phạm RPO 15 phút
```

**Thời điểm chạy job không nhất thiết là điểm phục hồi dữ liệu.** Một job bắt đầu 10:30, hoàn thành 10:36 có thể chỉ bao gồm những transaction tới một mốc được ghi trong metadata. Muốn đánh giá RPO chính xác cần quan sát **thời điểm/transaction ID cuối cùng thực sự có trong chuỗi backup**, không chỉ timestamp file hoặc lịch Cron.

### 2.2. Mối quan hệ giữa tần suất sao lưu và RPO

Nếu sao lưu vi sai (*differential*) cứ mỗi 15 phút thì trong điều kiện lý tưởng, độ cũ của điểm phục hồi ở một sự cố bất kỳ có thể tới **xấp xỉ 15 phút**. Trong thực tế còn:

- Độ trễ từ thời điểm lên lịch tới khi backup thực sự thu thập transaction.
- Job chạy lâu, timeout, hết dung lượng hoặc không tới được backup endpoint.
- Mất một phần **backup chain** hoặc transaction log cần thiết.
- Không có cảnh báo kịp thời khi lần backup cuối thất bại.
- Chênh lệch đồng hồ/metadata khiến cách xác định “mốc phục hồi” không chính xác.

Do đó một lịch 15 phút chỉ là **điều kiện cần** cho RPO 15 phút, không phải bảo đảm. Muốn có vùng an toàn nên lên lịch, giám sát và thử phục hồi đủ để đáp ứng ngưỡng trong cả trường hợp trễ và lỗi đơn lẻ.

Đặc biệt, **số lượng bản sao** không quyết định RPO: có 100 bản full cũ vẫn có thể không khôi phục được 5 phút dữ liệu mới nhất.

### 2.3. Graph phải nhất quán chứ không chỉ đủ số node

Ứng dụng có thể thực hiện trong một transaction:

```cypher
MATCH (u:AppUser {userId: $userId})
MATCH (p:Project {projectId: $projectId})
MERGE (u)-[m:MEMBER_OF]->(p)
SET m.role = $role;
```

Khi khôi phục, cần dữ liệu ở một **trạng thái giao dịch nhất quán**: node và relationship được tạo/cập nhật theo phạm vi commit, không chắp vá tập file store từ những mốc khác nhau. Copy thủ công các file dữ liệu của một database **đang chạy** không phải quy trình Neo4j backup an toàn, ngay cả khi kích thước file có vẻ đúng.

RPO phải được áp dụng với **dữ liệu mà ứng dụng thực sự sở hữu**: nếu transaction Neo4j đã commit nhưng service ngoài (ví dụ search index, message broker) chưa đồng bộ, phải có kế hoạch xây dựng lại/chạy bù các hệ thống dẫn xuất sau restore.

## 3. RTO là thời gian phục hồi dịch vụ, không chỉ thời gian restore file

### 3.1. Công thức thực hành

Một cách đo RTO từ góc nhìn nghiệp vụ:

```text
RTO thực tế =
  thời gian phát hiện và phân loại sự cố
  + quyết định phạm vi và mốc khôi phục
  + chuẩn bị hạ tầng, quyền và bản sao
  + tải/khôi phục/áp dụng transaction logs
  + kiểm tra dữ liệu, schema và quyền truy cập
  + kết nối lại ứng dụng, chuyển traffic
  + kiểm tra end-to-end đạt tiêu chí sẵn sàng
```

Thời gian các công đoạn có thể chồng lấp, nên phép cộng này là **mô hình lập kế hoạch**, không phải công thức đo chính xác khi hai công việc chạy song song. Khi diễn tập, đo từ **thời điểm sự cố được quy định trong SLA** đến khi **dịch vụ đã đáp ứng ngưỡng nghiệm thu**, không dừng đồng hồ ở lúc `neo4j-admin database restore` báo thành công.

### 3.2. Ví dụ RTO mục tiêu 120 phút

| Công đoạn | Ngân sách ví dụ |
| --- | ---: |
| Phát hiện sự cố, xác định chủ sở hữu | 10 phút |
| Cô lập nguồn lỗi, chọn mốc phục hồi | 15 phút |
| Cấp hạ tầng/khóa giải mã/tải bản sao | 15 phút |
| Restore và replay backup chain | 45 phút |
| Kiểm tra graph, schema và quyền | 20 phút |
| Chuyển ứng dụng/kiểm tra người dùng | 15 phút |
| **Tổng** | **120 phút** |

Đây là **ngân sách giả định**, không phải benchmark Neo4j. Nếu graph lớn, mạng chậm hoặc chuỗi DIFF dài, riêng giai đoạn restore có thể vượt 45 phút. Bắt buộc **đo bằng restore drill** với dữ liệu có quy mô đại diện và hạ tầng dự phòng thực tế.

### 3.3. Những yếu tố chi phối RTO

- **Kích thước full backup** và tốc độ đọc object storage/đĩa, băng thông mạng.
- **Độ dài chuỗi differential** phải replay; nhiều delta có thể kéo dài recovery.
- Thời gian cấp VM, volume, Kubernetes workload hoặc cluster mới.
- Không có sẵn container image, certificate, secret, cấu hình/index/schema cần thiết.
- Quy trình phê duyệt thay đổi DNS/router/load balancer và làm mới connection pool.
- Thời gian khôi phục **các database khác và database `system`**, nếu ứng dụng phụ thuộc RBAC hoặc đa database.
- Bước kiểm tra Cypher, ràng buộc uniqueness, luồng Java Driver và Spring Data Neo4j sau restore.

RTO có thể được cải thiện bằng full backup thường xuyên hơn, **aggregate** chuỗi differential, hạ tầng dự phòng, dữ liệu lưu ở nơi tải nhanh, tài liệu hóa runbook và diễn tập thường xuyên. Không cải thiện RTO chỉ bằng cách tăng tần suất DIFF nếu hệ thống không đủ thời gian replay.

## 4. Chọn RPO/RTO theo mức độ quan trọng của dịch vụ

Trước khi thiết kế lịch sao lưu, hỏi product owner và vận hành:

- Mất 5 phút cập nhật graph có ý nghĩa gì? Có thể chạy lại event từ hệ thống nguồn không?
- Khi Neo4j ngừng hoạt động, có thể cho frontend đọc dữ liệu cache hay bắt buộc ngừng giao dịch?
- Sau sự cố xóa nhầm dữ liệu, người dùng cần quay lại **ngày hôm qua** hay một mốc trong **30 ngày**?
- Mức thiệt hại theo mỗi giờ gián đoạn và mỗi phút mất dữ liệu là bao nhiêu?
- Có ràng buộc pháp lý, hợp đồng khách hàng hoặc quyền xóa dữ liệu nào ảnh hưởng đến retention?

Bảng phân cấp minh họa (**đề xuất để thảo luận**, không phải giá trị mặc định của Neo4j):

| Cấp dữ liệu/dịch vụ | RPO mục tiêu | RTO mục tiêu | Cách tiếp cận ban đầu |
| --- | --- | --- | --- |
| A — giao dịch quan trọng | 15 phút | 2 giờ | Online full+DIFF thường xuyên, chain ngắn, tập dượt restore |
| B — hệ thống nội bộ | 4 giờ | 8 giờ | Online backup theo ca hoặc nhiều lần/ngày, đối soát |
| C — dữ liệu báo cáo có thể dựng lại | 24 giờ | 48 giờ | Full/offline backup theo đêm hoặc build lại từ nguồn |

Nếu cấp A yêu cầu **không mất một transaction đã commit**, lịch DIFF 15 phút vẫn **không đáp ứng**. Khi đó cần thiết kế bổ sung như cơ chế đồng bộ được kiểm chứng, event/outbox lưu độc lập hoặc phương án DR có mục tiêu dữ liệu gần thời gian thực; phải đánh giá lại tính nhất quán và kịch bản hỏng toàn vùng, không gắn nhãn “RPO=0” chỉ vì có cluster.

Phân loại ở mức **database hoặc nhóm dữ liệu** chứ không dùng một con số cho mọi môi trường. Production, staging và tập dữ liệu tái tạo được thường có mức cần bảo vệ khác nhau.

## 5. Phương án backup Neo4j ảnh hưởng trực tiếp RPO/RTO

### 5.1. Phân biệt các công cụ

| Công cụ | Edition/điều kiện | Đặc điểm | Hệ quả với mục tiêu |
| --- | --- | --- | --- |
| `neo4j-admin database backup` | **Enterprise**, database đang chạy; không dùng trực tiếp trên Aura | Online full hoặc differential, tạo `.backup` artifact | Thích hợp lịch thường xuyên, RPO ngắn hơn |
| `neo4j-admin database dump` | Community và Enterprise; database **offline** | Toàn bộ database thành `.dump` archive | Có downtime; chỉ có bản full ở những lần dump |
| `neo4j-admin backup aggregate` | Enterprise | Ghép chuỗi full + differential thành một full backup đã recovered | Giảm thao tác replay lúc restore, hỗ trợ RTO |
| `neo4j-admin database restore` | Enterprise | Phục hồi từ artifact/backup chain; có thể chọn điểm theo timestamp/transaction ID | Cần kế hoạch target database, chain và kiểm tra sau restore |
| `neo4j-admin database load` | Community/Enterprise theo điều kiện | Nạp `.dump` hoặc full backup artifact phù hợp | Phù hợp phục hồi từ full archive, không thay thế PITR tùy ý |
| **Aura snapshot/backup** | Dịch vụ quản lý, theo tier | Theo lịch hoặc theo yêu cầu; restore qua console/API | Frequency, thời hạn giữ và cách restore phụ thuộc gói |

Không xem Docker volume snapshot, copy thô các file đang mở hay export CSV rời rạc là một **thay thế tương đương** cho Neo4j consistent backup. CSV còn có nguy cơ thiếu label, property, relationship, schema, quyền và transaction boundary nếu xuất không có quy trình thống nhất.

### 5.2. Full và differential: giữ nguyên chuỗi

```text
F0 (full) --> D1 --> D2 --> D3 --> D4
              |      |      |      |
         tx log    tx log  tx log  tx log

Để khôi phục sau D4 cần F0 và các phần transaction
liên tục đúng quan hệ phụ thuộc; thiếu một mắt xích
có thể làm các mốc về sau không còn khôi phục được.
```

**Full** chứa database store tại một mốc nhất quán. **Differential** chứa transaction log cần để đưa full (hoặc các delta trước đó) tới mốc mới hơn. Một chuỗi backup là các artifact có thể được sử dụng cùng nhau theo **transaction ID/metadata**, không đơn giản là các file có tên gần nhau.

Từ **Neo4j 2026.02**, bản Enterprise hỗ trợ lập lịch full và differential **độc lập** tốt hơn: DIFF đầu sau FULL có thể overlap transaction ID với full trước đó; các differential tiếp theo vẫn phải liên tục theo parent. Ở phiên bản cũ hơn, việc chèn FULL giữa các lần DIFF có thể làm đứt chuỗi dự kiến, nên cần theo tài liệu **đúng phiên bản**. Không nên sao chép lịch mới lên cụm Neo4j cũ mà chưa xác minh.

Neo4j có chế độ `--type=AUTO` (mặc định): ở lần đầu có thể thực hiện FULL và những lần sau có thể sinh DIFF dựa trên chuỗi có sẵn. Với lịch DIFF riêng dùng `--type=DIFF`, cần **seed FULL trước**; nếu transaction log cần thiết không còn, backup DIFF có thể thất bại hoặc ở chế độ AUTO phải fallback sang full tùy điều kiện/phiên bản.

### 5.3. Ví dụ lệnh Enterprise online backup — chỉ chạy trên môi trường được phép

Giả sử server Enterprise đã bật backup service an toàn; máy backup riêng truy cập `10.30.0.11:6362` qua mạng riêng, thư mục `/secure-backups/neo4j` thuộc sở hữu tài khoản chạy backup:

```bash
# Chạy ở máy backup/client thích hợp; không phải câu lệnh Cypher.
# Đường dẫn, TLS policy và tài nguyên phải được cấu hình trước.
bin/neo4j-admin database backup \
  --from=10.30.0.11:6362 \
  --to-path=/secure-backups/neo4j \
  --type=AUTO \
  neo4j
```

Lần đầu đường dẫn chưa có chuỗi có thể tạo full backup. Trong những lần sau, AUTO xác định mode thích hợp. Với một lịch full độc lập:

```bash
bin/neo4j-admin database backup \
  --from=10.30.0.11:6362 \
  --to-path=/secure-backups/neo4j \
  --type=FULL \
  neo4j
```

**Không thực thi hai lịch mà không xem phiên bản và cấu trúc chain trước.** Backup phải chạy bằng user hệ điều hành/role có quyền thích hợp; dịch vụ backup cần cấu hình, port riêng chỉ cho máy backup được phép và TLS nếu truyền qua mạng. Chạy trên máy riêng giúp hạn chế tác động CPU/memory lên các member cluster.

Đối với nhiều database, phải có lịch sao lưu từng **physical database**, bao gồm cả database `system` khi cần phục hồi người dùng, role và metadata vận hành. Không thể backup một database alias như một database vật lý. Các option như `--include-metadata` quyết định metadata RBAC nào được đóng gói; sao lưu dữ liệu nghiệp vụ **không tự bảo đảm đã lưu toàn bộ cấu hình, secrets và certificate ở ngoài Neo4j**.

### 5.4. Community Edition hoặc môi trường phải dừng database

Khi Neo4j không có Enterprise online backup, có thể dùng **offline dump**:

```bash
# Chạy sau khi database đích đã dừng theo quy trình vận hành.
bin/neo4j-admin database dump neo4j \
  --to-path=/secure-backups/offline
```

`dump` chỉ chứa dữ liệu database; **users/roles metadata không đi kèm**. Muốn phục hồi đầy đủ dịch vụ phải chuẩn bị riêng metadata/backup của database `system` và cấu hình/secret liên quan theo edition. Vì dump cần database offline, một hệ thống bắt buộc cập nhật liên tục phải tính downtime hoặc chọn giải pháp khác.

### 5.5. Point-in-time recovery (PITR) không có ở mọi chế độ

Với Enterprise backup chain phù hợp, lệnh restore hỗ trợ `--restore-until` theo **transaction ID** hoặc **UTC timestamp** để replay đến mốc yêu cầu. Với timestamp, các transaction commit **trước** mốc đó được khôi phục; với transaction ID, quy tắc giới hạn được mô tả theo bản Neo4j tương ứng (mốc ID được chỉ ra là **exclusive** trong tài liệu hiện hành).

PITR **không** có nghĩa có thể khôi phục ở một mốc bất kỳ nếu thiếu differential logs cần thiết. Một bản `.dump` full offline đơn lẻ chỉ khôi phục được trạng thái tại mốc dump, không cho phép replay phần lịch sử mà nó không chứa.

Một lệnh minh họa để **đọc cú pháp, không chạy trên production**:

```bash
# Mục tiêu là database lab mới, chưa tồn tại.
# Kiểm tra phiên bản, backup source và quyền/đường dẫn trước khi thực hiện.
bin/neo4j-admin database restore \
  --from-path=/secure-backups/neo4j \
  --source-database=neo4j \
  --restore-until="2026-11-20 10:30:00" \
  recovery_lab
```

Mốc thời gian trong `--restore-until` là **UTC**, không phải giờ địa phương Việt Nam. Lệnh có thể cần target offline, cấu hình thư mục dữ liệu và bước `CREATE DATABASE recovery_lab` trong `system` sau khi restore (nếu không thay thế database đã tồn tại). Không tự thêm `--overwrite-destination` để bỏ qua lỗi: phục hồi đè có thể phá hủy dữ liệu mới và **không an toàn cho cluster** theo hướng dẫn Neo4j.

## 6. Chính sách lưu giữ bản sao: giữ gì, giữ bao lâu và giữ ở đâu?

### 6.1. Hai mục tiêu retention khác RPO

**Retention** giải quyết nhu cầu “có thể quay lại **bao xa trong quá khứ**?”; RPO giải quyết “ở lúc sự cố, sẽ mất **bao nhiêu dữ liệu gần nhất**?”. Ví dụ:

- RPO 15 phút với 7 ngày retention: cần điểm phục hồi đủ gần sự cố **và** những chuỗi khả dụng trong cửa sổ 7 ngày.
- RPO 4 giờ với retention 90 ngày: vẫn có thể mất gần 4 giờ dữ liệu mới khi sự cố, nhưng phải giữ ít nhất bản sao/mốc hợp lệ theo chính sách cho 90 ngày.
- Giữ một full backup 90 ngày **không** đồng nghĩa có thể restore bất kỳ 1 phút nào trong 90 ngày; độ chi tiết mốc phụ thuộc lịch và log liên tục được giữ.

Vì vậy chính sách phải nói rõ **retention của artifact**, **độ phân giải các điểm phục hồi** và **cửa sổ PITR** nếu cam kết.

### 6.2. Mẫu Grandfather–Father–Son (GFS)

Một chính sách tham khảo (cần xét duyệt theo dữ liệu, pháp lý và khả năng lưu trữ):

| Tầng | Giữ trong bao lâu | Công dụng |
| --- | --- | --- |
| Bản sao gần nhất/hàng ngày | 14 ngày | Khôi phục lỗi phát hiện sớm hoặc test bản nâng cấp |
| Mốc hàng tuần | 8 tuần | Quay về trước những lần thay đổi dữ liệu sai |
| Mốc hàng tháng | 12 tháng | Phục vụ điều tra dài hơn theo yêu cầu |
| Lưu trữ đặc biệt | Chỉ khi có cơ sở pháp lý/kinh doanh | Legal hold, audit hoặc ràng buộc ngành |

Đây là **khung chính sách**, không phải một lịch backup đủ để đáp ứng RPO 15 phút. Nếu cần RPO 15 phút, bên cạnh các mốc GFS vẫn phải giữ **chuỗi full/differential và transaction coverage liên tục** đủ cho các điểm phục hồi được cam kết.

Khi thiết kế lịch GFS, đừng tạo 14+8+12 file bất kỳ rồi cho rằng đã đáp ứng retention. Một “mốc hàng tuần” chỉ có ích nếu có thể phục hồi bằng **full độc lập** hoặc một chuỗi đầy đủ tới đúng mốc đó.

### 6.3. Ba bản sao, hai dạng lưu trữ, một bản khác vị trí

Quy tắc **3-2-1** là hướng dẫn triển khai có tính phòng ngừa:

1. Có nhiều hơn một bản sao dữ liệu, ngoài dữ liệu production.
2. Tránh một điểm lỗi chung giữa các nơi lưu; cân nhắc hai loại media/hệ thống lưu trữ hoặc các fault domain độc lập.
3. Giữ ít nhất một bản **off-site** ở vùng/địa điểm khác với DBMS đang chạy.

Các biện pháp tăng chống ransomware và xóa nhầm:

- **Immutable/object-lock/WORM** cho những bản sao quan trọng và khoảng thời gian lưu phù hợp. “Artifact backup của Neo4j là immutable file” **không tự đồng nghĩa** cloud bucket có chính sách chống xóa/sửa.
- Credential của backup store tách khỏi credential database và khỏi tài khoản chạy ứng dụng. Ngăn attacker chiếm quyền database xóa cả backup.
- Mã hóa dữ liệu khi truyền và khi lưu, quản lý key theo chính sách; **không đặt key giải mã trong cùng chỗ attacker có thể xóa bản sao**.
- Không để backup directory ở chế độ world-readable/world-executable; kiểm soát quyền hệ điều hành và cloud IAM.
- Giới hạn cổng backup (thường `6362/TCP`) chỉ cho client/trạm backup đáng tin cậy. Dùng TLS cho backup online khi truyền qua mạng.
- Xây dựng kế hoạch phục hồi **không phụ thuộc vào cùng danh tính/quyền đã bị mất khi xảy ra sự cố**; lưu an toàn thủ tục và thông tin liên hệ khẩn cấp.

### 6.4. Xóa bản sao đúng cách: không phá backup chain

Ví dụ chuỗi:

```text
F-01 (full)
  +-- D-01 (diff)
  +-- D-02 (diff)
  +-- D-03 (diff)

F-02 (full độc lập, đã kiểm tra phục hồi)
  +-- D-04
  +-- D-05
```

Nếu muốn giữ mốc tại D-03, **không thể xóa F-01 hoặc các thành phần liên quan** khi chúng vẫn cần thiết cho phục hồi. Khi đã xác nhận F-02 và chuỗi mới bao phủ toàn bộ cửa sổ retention mong muốn, mới cân nhắc xóa chuỗi cũ **theo đồ thị phụ thuộc backup**, không chỉ theo tuổi file.

Một chính sách xóa hợp lệ nên:

1. Dựa trên **ngày commit/coverage** và metadata của chain, không chỉ filename/time.
2. Giữ tất cả full parent và differential logs cần để khôi phục mọi mốc đã hứa.
3. Kiểm tra một chain mới **đã restore thành công** trước khi xóa chain cũ duy nhất.
4. Tôn trọng object-lock, legal hold và yêu cầu xóa dữ liệu cá nhân; cân bằng giữa nghĩa vụ lưu và quyền xóa.
5. Ghi log ai duyệt, đã xóa artifact nào, giữ mốc nào và khả năng restore còn lại.

**Không tự áp dụng “xóa mọi file quá 30 ngày”** trên một thư mục chứa FULL + DIFF nếu chưa kiểm tra sự phụ thuộc giữa chúng.

### 6.5. Tính dung lượng lưu trữ để chính sách khả thi

Giả sử mỗi bản full nén là 400 GiB, mỗi ngày thêm 25 GiB differential, giữ hai full độc lập và 14 ngày delta. Một dự toán sơ bộ:

```text
2 full × 400 GiB       = 800 GiB
14 ngày diff × 25 GiB  = 350 GiB
                          --------
Dung lượng payload       1.150 GiB
```

Đây mới là **payload giả định**, chưa kể bản sao khác vùng, overhead object metadata, dung lượng staging/aggregate, khả năng nén biến đổi, tăng trưởng đồ thị, bản cũ do legal hold và headroom để restore. Cần đo lại theo dữ liệu thực và dự phòng chi phí download/egress.

Nếu muốn giảm dung lượng, đừng tùy ý rút retention đã cam kết. Có thể đánh giá nén, tầng storage, aggregate, lập lịch full phù hợp hoặc loại trừ dữ liệu *thật sự tái tạo được* theo thỏa thuận nghiệp vụ.

## 7. Bản sao “có tồn tại” khác bản sao “đã được kiểm chứng”

### 7.1. Kiểm tra metadata và tình trạng chain

Trong Neo4j Enterprise hiện hành, công cụ `neo4j-admin backup inspect` đọc metadata của artifact: database name/ID, backup time, trạng thái full/differential, ID transaction thấp nhất và cao nhất, cùng thông tin recovered.

Ví dụ xem thông tin trong thư mục backup được phép:

```bash
# Không sửa dữ liệu; dùng ở máy có quyền truy cập bản sao.
bin/neo4j-admin backup inspect /secure-backups/neo4j
```

Xem chuỗi kết thúc ở lần backup mới nhất:

```bash
bin/neo4j-admin backup inspect \
  --latest-chain \
  /secure-backups/neo4j
```

**Không dùng timestamp của file làm bằng chứng duy nhất** cho RPO. Cần kiểm tra ID transaction và mối quan hệ giữa các artifact. Hai file backup mới nhất có thể thuộc **hai database ID khác nhau** dù tên database giống nhau sau một lần drop/recreate; chúng không phải một chain phục hồi hợp lệ.

Ở phiên bản cũ, tên option cho metadata có thể khác; kiểm tra `neo4j-admin backup inspect --help` theo binary đang triển khai. Nếu dùng bucket cloud, quyền và cách truy cập đường dẫn cũng phải theo công cụ/tài liệu của phiên bản.

### 7.2. Aggregate để giảm phần việc lúc xảy ra sự cố

Với chuỗi differential dài, Neo4j Enterprise có thể **aggregate** thành một full backup đã recovered:

```bash
# Ví dụ chỉ dành cho quy trình chuẩn bị/kiểm chứng trên vùng backup.
# Giữ bản cũ trong lần thử để không mất đường quay lại.
bin/neo4j-admin backup aggregate \
  --from-path=/secure-backups/neo4j \
  --keep-old-backup=true \
  neo4j
```

Aggregate áp dụng transaction logs vào store để tạo một artifact đã recovered, giúp **giảm khối lượng recovery lúc restore** và rủi ro mất một mắt xích chain. Nó không xóa được nhu cầu giữ lịch sử PITR theo chính sách: nếu chỉ giữ bản aggregate mới nhất mà xóa toàn bộ logs cũ, các **mốc khôi phục trung gian** có thể mất.

Không chạy aggregate đồng thời với quy trình xóa retention trên cùng vùng backup khi chưa có cơ chế khóa/điều phối. Cần dự phòng đủ bộ nhớ, CPU, disk và thư mục tạm vì aggregate cũng là một tác vụ tài nguyên nặng.

### 7.3. Consistency check

Neo4j có `neo4j-admin database check` để kiểm tra cấu trúc graph, property ownership, counts và index trên database offline hoặc artifact backup/dump phù hợp.

```bash
# Ví dụ khi đã có một full backup đã recovered hoặc dump hợp lệ.
bin/neo4j-admin database check \
  --from-path=/secure-backups/recovered \
  neo4j
```

**Không chạy trực tiếp consistency checker trên database đang hoạt động** hoặc trên một differential artifact đơn lẻ. Những phiên bản/tùy chọn chỉ kiểm tra được full đã recovered hoặc dump; cần aggregate chain trước nếu cần kiểm tra chuỗi. Tham số `--from-path` và khả năng chọn file/thư mục phụ thuộc phiên bản, vì vậy phải xem `--help` của binary cụ thể.

Consistency check hữu ích nhưng **không chứng minh có thể phục hồi ứng dụng trong RTO**. Cần tiến thêm bước restore thử rồi chạy các truy vấn nghiệp vụ, truy cập qua Java Driver và Spring Data Neo4j trên môi trường độc lập.

### 7.4. Bốn mức xác nhận backup

| Mức | Kiểm chứng | Chưa chứng minh được điều gì? |
| --- | --- | --- |
| 1 | Job exit code thành công, artifact xuất hiện | Artifact có đủ các transaction cần khôi phục hay không |
| 2 | Metadata chain liên tục, đúng database ID và mốc | File lưu trữ có hỏng hoặc thiếu quyền giải mã hay không |
| 3 | Consistency check/aggregate trên artifact phù hợp | Hệ thống và ứng dụng có hoạt động đúng sau restore không |
| 4 | Restore thực tế vào môi trường riêng, kiểm tra Cypher, schema, RBAC, ứng dụng và thời gian | Cần tiếp tục giám sát những thay đổi của dữ liệu và hạ tầng về sau |

**Quy tắc vận hành:** không xem một chính sách backup là đạt chỉ dựa trên các job hằng ngày “màu xanh”. Trong mỗi kỳ diễn tập phải chứng minh **tối thiểu một điểm phục hồi** thực sự có thể sử dụng và đo được RTO.

## 8. Runbook diễn tập phục hồi có thể lặp lại

### 8.1. Phân công và chuẩn bị

Trước diễn tập, cần xác định rõ người sở hữu:

- **Incident commander:** quyết định mức độ sự cố, thời điểm bắt đầu tính RTO và mốc phục hồi được phê duyệt.
- **DBA/Neo4j operator:** chọn chain và chạy công cụ restore, kiểm tra database/status/consistency.
- **Hạ tầng/SRE:** cấp VM/storage/secret/certificate/network, theo dõi thời gian và tài nguyên.
- **Chủ dịch vụ Java/SDN:** kiểm tra Bolt connectivity, quyền, Cypher nghiệp vụ, kết nối và routing.
- **Product/data owner:** chấp thuận mức mất dữ liệu thực tế, so sánh ID/quan hệ quan trọng và quyết định mở lại traffic.

**Chỉ diễn tập trên hạ tầng và database thử nghiệm, không overwrite production**. Những lệnh restore có thể thay thế store và xóa dữ liệu đích; cần phương án kiểm tra an toàn trước khi thử thao tác phá hủy.

### 8.2. Các bước diễn tập

1. **Chọn tình huống:** lỗi mất disk, xóa nhầm relationship, database bị hỏng, mất toàn vùng hoặc credential bị xâm nhập. Mỗi tình huống có mốc phục hồi và vùng mạng khác nhau.
2. **Đóng băng bằng chứng:** ghi thời điểm sự cố, version Neo4j, database ID, transaction metadata và các hệ thống phụ trợ. Với sự cố bảo mật, cô lập nguồn gây hại trước khi phục hồi.
3. **Chọn bản sao:** xác định full và toàn bộ differential bắt buộc, hoặc dump/snapshot phù hợp; đối chiếu RPO dự kiến.
4. **Chuẩn bị đích độc lập:** cấp vùng restore có đủ disk, phần mềm/version tương thích, chứng thư/secret/quyền phù hợp. Không dùng chung URI production khi chưa được phép.
5. **Phục hồi:** chạy công cụ restore/load theo tài liệu edition và version. Nếu PITR, chốt timestamp UTC/transaction ID **trước sự kiện gây hại**.
6. **Khởi động database:** kiểm tra trạng thái online và log. Với cluster, sử dụng quy trình restore cluster đúng phiên bản thay vì overwrite một member tùy ý.
7. **Xác minh Neo4j:** schema/index, node/relationship, khóa nghiệp vụ, số lượng đối tượng, quyền truy cập và các query trọng yếu.
8. **Xác minh từ ứng dụng:** Java Driver `verifyConnectivity()`, Spring Data Neo4j repository/service, kiểm tra tài khoản đọc và tài khoản ghi trên một transaction thử nghiệm đã được phê duyệt.
9. **Chuyển traffic có kiểm soát:** chỉnh routing/URI/DNS và health check, theo dõi connection pool, latency và error; chỉ khi product owner chấp thuận.
10. **Tổng kết:** đo RPO/RTO thật, ghi bước dài nhất và lỗi phát sinh, cập nhật policy và runbook.

### 8.3. Những truy vấn Cypher nên dùng khi nghiệm thu

Các label và ID dưới đây là **ví dụ miền nghiệp vụ**, cần đổi theo graph của ứng dụng:

```cypher
MATCH (u:AppUser)
RETURN count(u) AS totalUsers;
```

```cypher
MATCH (p:Project)
RETURN count(p) AS totalProjects;
```

```cypher
MATCH (:AppUser)-[r:MEMBER_OF]->(:Project)
RETURN count(r) AS totalMemberships;
```

```cypher
MATCH (u:AppUser {userId: $userId})-[r:MEMBER_OF]->
      (p:Project {projectId: $projectId})
RETURN u.userId AS userId,
       p.projectId AS projectId,
       r.role AS role;
```

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Số node/cạnh đúng là điều kiện cần, **không đủ**: cần so những ID quan trọng, property và hướng relationship. Nếu database nguồn có nhiều cập nhật đang tiến hành ở mốc backup, kỳ vọng phải dựa trên **mốc khôi phục đã chọn**, không tự động so với số liệu production hiện tại sau sự cố.

Đối với system RBAC, kiểm tra user/role và quyền tương ứng khi có thẩm quyền. `SHOW CONSTRAINTS`/`SHOW INDEXES` giúp đối chiếu schema, nhưng không thay thế xác minh cấu hình Neo4j, chứng thư TLS, Java connection pool, secret và job ngoài database.

### 8.4. Đo RPO/RTO ngay trong diễn tập

Giả sử:

```text
Sự cố mô phỏng:      14:00 UTC
Last restored commit:13:46 UTC
Dịch vụ đạt nghiệm thu:15:25 UTC
```

Khi đó:

- **RPO thực tế:** 14 phút.
- **RTO thực tế:** 85 phút.

Nếu mục tiêu là RPO 15 phút và RTO 120 phút, diễn tập này **đạt hai mục tiêu**. Nếu restore chỉ phục hồi được đến 13:30 hoặc đến 16:10 mới cho ứng dụng hoạt động bình thường, phải đánh dấu **không đạt**, dù command backup/restore trả exit code 0.

Không nên dùng một lần diễn tập nhỏ để cam kết mọi sự cố tương lai. Cần diễn tập nhiều loại lỗi, dữ liệu tăng trưởng thực tế, cross-region restore và thao tác với tài khoản vận hành khác nhau để giảm rủi ro “chỉ một người biết khôi phục”.

## 9. AuraDB: retention phụ thuộc gói dịch vụ

**Neo4j Aura** là dịch vụ quản lý nên người dùng không chạy trực tiếp `neo4j-admin database backup` trên server của Aura. Thay vào đó, Aura cung cấp cơ chế **snapshots/backups** ở console/API, với lịch và chính sách giữ khác nhau theo tier/version.

Những điểm cần nhớ:

- **Instance một database:** tài liệu Aura gọi bản sao là **snapshot**, bao gồm database người dùng và `system` liên quan.
- **Instance nhiều user database:** backups quản lý theo từng database, gồm cả `system`; khi phục hồi toàn instance phải xem quy trình riêng.
- **Scheduled và on-demand:** tùy tier. Tài liệu hiện hành nêu AuraDB Professional có scheduled snapshots hằng ngày; Business Critical và Virtual Dedicated Cloud trên bản latest có full theo ngày và differential theo giờ; Free chỉ có snapshot on-demand.
- **Retention và khả năng export** khác nhau. Không phải snapshot nào cũng export được, và các differential snapshot có thể chỉ phục vụ restore trong dịch vụ.
- **Restore có thể overwrite** dữ liệu instance/database đích. Nếu cần giữ phiên bản hiện tại, đánh giá tùy chọn tạo instance từ snapshot hoặc export trước, theo khả năng gói.
- Aura lưu bản sao trong hạ tầng cloud của dịch vụ, thường cùng provider/region với instance. Nếu doanh nghiệp cần khả năng phục hồi độc lập **ngoài cùng một provider/region**, cần đánh giá phương án export và giữ bản sao riêng được hỗ trợ.

**Không sao chép cứng số ngày giữ của một tier sang tier khác.** Chính sách sản phẩm có thể đổi theo phiên bản và gói dịch vụ. Trước khi chốt RPO/RTO/retention, kiểm tra bảng **Snapshot/backup details** trên tài liệu Aura và những tùy chọn thực sự xuất hiện ở instance của tổ chức.

### 9.1. Đọc bảng Aura đúng cách

| Thuộc tính Aura | Câu hỏi khi ký SLA |
| --- | --- |
| Scheduled frequency | Mỗi ngày, mỗi giờ hay không có scheduled backup? |
| Full/differential | Có thể restore ở mốc nào, có PITR hay chỉ mốc snapshot? |
| Restorable days | Trong bao lâu còn chọn được mốc restore? |
| Exportable days | Trong bao lâu được tải/clone full snapshot? |
| On-demand | Có được tạo snapshot trước migration hay release không? |
| Restore target | Có overwrite instance hay tạo clone độc lập? |
| Region/provider | Có đáp ứng yêu cầu off-site/cross-region thực tế không? |

Nếu RPO nghiệp vụ ngắn hơn lịch mà tier Aura hỗ trợ, không nên “hứa” mức RPO đó dựa trên backup có sẵn. Cần thay đổi gói, kiến trúc, đồng bộ dữ liệu hoặc điều chỉnh mục tiêu sau khi đánh giá chi phí/rủi ro.

## 10. Chỉ số giám sát và cảnh báo theo RPO/RTO

Một chính sách sao lưu chỉ vận hành được khi có **owner và telemetry**:

| Metric / kiểm tra | Ý nghĩa | Gợi ý cảnh báo |
| --- | --- | --- |
| Tuổi điểm khôi phục cuối cùng được xác minh | Độ cũ của transaction cuối có thể phục hồi | Sắp vượt ngân sách RPO thì cảnh báo; vượt ngưỡng phải tạo sự cố |
| Thời điểm backup **thành công** cuối | Lịch đang chạy hay bị kẹt | Không thành công trong cửa sổ cho phép |
| Backup chain continuity | Full và DIFF có đủ parent/transaction ranges không | Đứt chain, thiếu artifact hoặc sai database ID |
| Tổng dung lượng và tăng trưởng backup | Khả năng tiếp tục giữ đúng retention | Gần hết quota/disk hoặc chi phí vượt dự toán |
| Tuổi bản off-site mới nhất | Khả năng phục hồi khi mất cả site | Không chuyển dữ liệu sang off-site đúng lịch |
| Restore drill duration | Thời gian từ sự cố mô phỏng đến nghiệm thu | P95/max vượt mục tiêu RTO hoặc xu hướng tăng |
| Consistency/restore verification | Khả năng sử dụng bản sao | Job check hoặc restore test thất bại |
| Lịch hết hạn certificate/khóa mã hóa | Khả năng truy cập bản sao khi sự cố | Key/CA sắp hết hạn hoặc không đủ quyền giải mã |
| Retention compliance | Có mốc quá hạn hoặc thiếu mốc hợp lệ không | Xóa quá sớm, giữ quá lâu hoặc không tuân thủ legal hold |

Đặt cảnh báo **trước khi** vượt RPO, có khoảng dự phòng cho người vận hành phản ứng. Ví dụ mục tiêu 15 phút, nếu mốc khôi phục đã cũ 12 phút và job dự kiến tiếp theo chưa xong, cần cảnh báo sớm thay vì đợi 15 phút mới phát hiện.

**RPO dashboard không nên chỉ lấy `last_success_timestamp` của Cron**: phải biết backup đó chứa transaction tới mốc nào. Khi backup bị lỗi một lần hoặc chain bị mất, metric khôi phục được sẽ phản ánh rủi ro rõ hơn.

## 11. Mẫu chính sách có thể giao cho đội vận hành

Đây là **mẫu tài liệu chính sách**, không phải tệp cấu hình tự động được `neo4j-admin` hiểu. Các giá trị dưới đây đều **giả định** và phải được product owner, DBA, SRE và đội bảo mật thống nhất:

```yaml
policyId: neo4j-production-business
owner: data-platform
scope:
  environment: production
  databases: [neo4j, system]
  edition: enterprise
objectives:
  rpoMinutes: 15
  rtoMinutes: 120
  pointInTimeWindowDays: 7
schedule:
  full: daily
  differential: every-10-minutes
  verifyChain: every-run
retention:
  nearTermDays: 14
  weeklyCopies: 8
  monthlyCopies: 12
storage:
  offSite: true
  encryptionAtRest: required
  immutableCopies: required
  restoreCredentialsSeparated: true
operations:
  metadataInspect: every-run
  consistencyCheck: weekly-on-recovered-full
  restoreDrill: monthly
  drSiteDrill: quarterly
  approvalForDeletion: required
```

**Chú ý:** lịch DIFF 10 phút ở ví dụ tạo khoảng dự phòng cho RPO 15 phút, nhưng vẫn chỉ là kế hoạch. Khả năng đạt thật cần chứng minh bằng metadata transaction coverage, cảnh báo đúng thời gian, độ trễ backup và restore drill. Thời gian lưu GFS **không tự bảo đảm** cửa sổ PITR 7 ngày trừ khi chuỗi logs tương ứng còn nguyên.

### 11.1. Điều kiện nghiệm thu chính sách

Một policy chỉ được công nhận khi:

1. **Có chủ sở hữu và SLA được phê duyệt** cho từng database/nhóm nghiệp vụ.
2. **Bản sao có thật:** tác vụ backup theo lịch, ghi metadata và log kết quả.
3. **Bản sao đủ an toàn:** phân quyền, mã hóa, off-site, chống sửa/xóa, quản lý khóa và secret.
4. **Retention kiểm chứng được:** có thể liệt kê các mốc lịch sử và chain cần để restore chúng; không xóa nhầm parent.
5. **RPO đo được:** mốc transaction phục hồi cuối nằm trong ngưỡng hoặc hệ thống phát cảnh báo/sự cố.
6. **RTO diễn tập đạt:** dịch vụ Java/Spring Data Neo4j thực sự phục vụ lại đúng chức năng và đúng thời hạn.
7. **Runbook có thể được người khác thực hiện**, không phụ thuộc trí nhớ hoặc tài khoản cá nhân duy nhất.
8. **Có kiểm tra định kỳ:** khi version, graph size, lịch backup, vùng lưu trữ hoặc SLA thay đổi, policy phải được đánh giá lại.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Cluster 3 node nên không cần backup.” | Cluster giúp availability nhưng có thể cùng nhận thao tác xóa sai hoặc bị ảnh hưởng toàn vùng |
| “Sao lưu 15 phút/lần = RPO 15 phút chắc chắn.” | Phải tính cả job fail, delay và tính liên tục của transaction coverage |
| “Backup hoàn tất trong 5 phút nên RTO là 5 phút.” | RTO bao gồm sự cố, restore, kiểm tra dữ liệu và ứng dụng, cutover |
| “Có 30 file backup nên giữ được 30 ngày.” | Cần biết timestamp phục hồi, phụ thuộc full/DIFF và thời gian thực tế |
| “Có thể xóa full cũ nhưng giữ DIFF mới.” | Có thể phá chain và mất khả năng restore mọi mốc phụ thuộc |
| “RPO 0 có thể đạt bằng backup hằng giờ.” | Không; backup định kỳ luôn có khoảng thời gian có thể mất dữ liệu |
| “Snapshot hạ tầng = Neo4j backup.” | Snapshot thiếu nhất quán transaction nếu không phối hợp công cụ/quy trình được hỗ trợ |
| “Full backup luôn gồm role, account và toàn bộ secret.” | Phải xác định backup `system`, `--include-metadata`, file cấu hình và secret bên ngoài |
| “File dump có thể PITR đến phút bất kỳ.” | Dump chỉ chứa trạng thái tại mốc dump, không có chain transaction cần replay |
| “Consistency check PASS là restore thành công.” | Còn phải khôi phục thật và kiểm tra query, index/constraint, quyền, ứng dụng |
| “Đã bật object-lock nên key giải mã không quan trọng.” | Mất key hoặc quyền truy cập có thể khiến backup không thể khôi phục |
| “Một mốc snapshot Aura luôn export được.” | Tùy tier, tuổi snapshot, loại full/diff và chính sách dịch vụ |
| “Restore lên member cluster nào cũng có thể overwrite.” | Neo4j có quy trình riêng cho cluster; overwrite store tùy tiện có thể làm trạng thái cluster sai |
| “Dùng data từ trước migration không cần quan tâm version.” | Restore về version Neo4j **cũ hơn** bản tạo backup không được hỗ trợ |
| “Xóa dữ liệu theo yêu cầu người dùng đồng nghĩa xóa ngay mọi backup.” | Cần chính sách retention/deletion theo pháp lý, cơ chế mã hóa và bản sao immutable được quản trị đúng |

## 13. Bài tập và tình huống thực tế

### Bài 1 — Tính RPO từ mốc commit

Lịch backup hoàn tất lúc 10:00, 10:15, 10:30; sự cố lúc **10:42**. Artifact 10:30 có transaction tới 10:29. Khi đó:

- Hãy xác định **RPO thực tế theo mốc 10:29**.
- Nếu lần backup 10:30 hỏng và lần 10:15 chỉ chứa transaction tới 10:14, RPO mới là bao nhiêu?
- Với mục tiêu RPO 15 phút, trường hợp nào vi phạm? Cảnh báo nên xuất hiện ở thời điểm nào?

*Gợi ý:* câu trả lời phải dựa vào transaction coverage, không dựa vào thời điểm file hoàn tất.

### Bài 2 — Thiết kế RTO khả thi

Một graph có 300 GiB node/relationship và 50 GiB transaction logs cần replay; môi trường DR chỉ có băng thông tải hiệu dụng 100 MiB/s, hạ tầng cần 30 phút khởi tạo, còn kiểm tra và cutover cần thêm 40 phút.

Hãy tự ước lượng **giới hạn tối thiểu** chỉ cho bước tải khoảng 350 GiB, rồi xem còn bao nhiêu thời gian để restore thực tế nếu RTO là 2 giờ. Giải thích vì sao chưa tính thời gian CPU replay logs, mở database, kiểm tra ứng dụng thì không được ký SLA ngay.

### Bài 3 — Chính sách retention có đứt chain không?

Có F1 ngày 1, các D1…D20 từ ngày 2 đến ngày 20, F2 ngày 21 và các D21…D30 từ ngày 22 đến 30. Chính sách muốn giữ khả năng khôi phục một mốc ở ngày 15 và một mốc ngày 28.

- Những artifact nào **chắc chắn không được xóa** trước khi chứng minh đường phục hồi của ngày 15?
- Nếu F2 đã được khôi phục thử thành công, nó có thay thế được F1 cho nhu cầu phục hồi ngày 15 không?
- Thêm thao tác aggregate ở đâu để giảm RTO nhưng vẫn giữ những mốc PITR đã cam kết?

### Bài 4 — Sự cố Cypher xóa nhầm dữ liệu

Một thao tác `DETACH DELETE` nhầm đã xóa 30.000 node `:Project` và các quan hệ `:MEMBER_OF` vào 14:05. Bản full gần nhất lúc 00:00, DIFF gần nhất chứa transaction tới 14:00; từ 14:06 ứng dụng vẫn có những cập nhật hợp lệ mới.

Hãy đề xuất cách chọn mốc PITR trước 14:05, quy trình **khôi phục trong môi trường tách biệt**, cách đối soát ID và quan hệ, cũng như phương án đánh giá/replay những cập nhật hợp lệ sau đó. Không đề xuất restore đè production ngay khi chưa có chấp thuận của incident commander và data owner.

### Bài 5 — Aura có đáp ứng SLA không?

Doanh nghiệp sử dụng AuraDB Professional và cần **RPO 5 phút**, RTO 30 phút, retention 90 ngày, trong khi chỉ dựa vào snapshots mặc định của tier. Kiểm tra lịch/tính năng thực sự của tier hiện hành và kết luận liệu có thể cam kết ba chỉ tiêu đó chỉ bằng backup mặc định hay không. Đề xuất phương án thay đổi tier, kiến trúc hoặc mục tiêu nếu không đạt.

**Tiêu chí hoàn thành:** người học tính được RPO/RTO từ **dữ liệu khôi phục và thời gian dịch vụ hoạt động lại**, xây dựng được retention bảo toàn backup chain, chọn đúng công cụ theo Neo4j edition/Aura, có lịch diễn tập phục hồi và giải thích được vì sao một bản backup chưa bao giờ được restore thử không phải bằng chứng DR sẵn sàng.

## Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/): yêu cầu đánh giá RPO/RTO, edition, chi phí và lưu trữ off-site.
- [Neo4j Operations Manual — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/): full/differential và phân biệt online/offline.
- [Neo4j Operations Manual — Online backup](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/): lịch full/DIFF, phiên bản 2026.02, backup chain và tham số.
- [Neo4j Operations Manual — Offline backup](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/): cách dùng `neo4j-admin database dump`.
- [Neo4j Operations Manual — Inspect backup metadata](https://neo4j.com/docs/operations-manual/current/backup-restore/inspect/): transaction IDs, database ID và xác định chain.
- [Neo4j Operations Manual — Aggregate backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/): chuẩn bị artifact recovered và quản lý thời gian phục hồi.
- [Neo4j Operations Manual — Restore backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/): restore, `--restore-until`, điểm UTC, cảnh báo cluster.
- [Neo4j Operations Manual — Consistency checker](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/): kiểm tra database và full backup phù hợp.
- [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/): snapshot/backup theo tier, khả năng restore/export và retention.
