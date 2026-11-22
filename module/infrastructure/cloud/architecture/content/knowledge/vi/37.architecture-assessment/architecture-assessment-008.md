# Kiểm thử phục hồi dữ liệu và chuyển khu vực

## 1. Vì sao đánh giá kiến trúc phải kiểm thử khả năng phục hồi?

Một kiến trúc ứng dụng đám mây có thể có nhiều vùng sẵn sàng (Availability Zone), bản sao cơ sở dữ liệu, sao lưu định kỳ và khu vực dự phòng (Region), nhưng vẫn không khôi phục được khi xảy ra sự cố thật. Lý do là **có thành phần dự phòng không đồng nghĩa với có quy trình phục hồi đã được kiểm chứng**. Dữ liệu sao lưu có thể không giải mã được; bản sao có thể chứa cả thao tác xóa nhầm; ứng dụng ở Region phụ có thể thiếu cấu hình, khóa mã hóa hoặc không nhận được lưu lượng; đội vận hành có thể mất nhiều giờ để xác định điểm chuyển quyền ghi.

Trong module **CLOUD_ARCHITECTURE**, thiết kế kiến trúc bắt đầu từ yêu cầu nghiệp vụ rồi mới chọn mạng, compute, dữ liệu và mô hình triển khai. Bài này thuộc chương **Đánh giá kiến trúc**, tập trung cách kiểm thử bằng chứng thực tế cho hai năng lực:

1. **Phục hồi dữ liệu:** đưa dữ liệu về trạng thái đủ, đúng và sử dụng được từ backup, snapshot, point-in-time recovery (PITR) hoặc bản sao phù hợp.
2. **Chuyển khu vực:** tiếp tục phục vụ ở Region khác khi Region chính không khả dụng hoặc khi chủ động di chuyển, đồng thời bảo vệ quyền ghi, tính nhất quán và trải nghiệm người dùng.

Mục tiêu là đánh giá các đánh đổi theo tinh thần **Well-Architected**: độ tin cậy, bảo mật, hiệu năng, chi phí, khả năng vận hành và sử dụng tài nguyên hợp lý.

Sau khi học, bạn có thể xác định mục tiêu RPO/RTO, phân biệt phục hồi từ backup và failover theo bản sao, xây dựng kịch bản diễn tập, đo kết quả end-to-end, kiểm tra dữ liệu/ứng dụng sau phục hồi và đưa ra quyết định kiến trúc dựa trên bằng chứng.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| **Backup / snapshot** | Bản dữ liệu được lưu để khôi phục tại một thời điểm hoặc theo chính sách. | Replica luôn cập nhật; backup cần được khôi phục và kiểm chứng. |
| **PITR** | Khôi phục về thời điểm có thể lựa chọn trong khoảng được hỗ trợ, thường dựa trên backup và transaction log. | Khả năng hoàn tác mọi lỗi ngay lập tức hoặc về mọi thời điểm tùy ý. |
| **Replication** | Duy trì một hoặc nhiều bản sao dữ liệu, đồng bộ hoặc bất đồng bộ tùy cấu hình. | Backup độc lập chống lỗi logic, ransomware hay xóa nhầm. |
| **Failover** | Chuyển vai trò phục vụ, đặc biệt vai trò ghi, sang thành phần hoặc Region dự phòng khi có sự cố. | Failback: chuyển trở lại sau khi khu vực cũ phục hồi. |
| **Planned switchover** | Chuyển chủ có kế hoạch, có thể tạm dừng ghi để đối soát và giảm rủi ro mất dữ liệu. | Unplanned failover khi nguồn bất ngờ không thể liên lạc. |
| **Restore** | Phục dựng dữ liệu hoặc hệ thống từ bản lưu có thể sử dụng. | Tự động chuyển lưu lượng mạng. |
| **DR (Disaster Recovery)** | Tập hợp năng lực kỹ thuật và vận hành để phục hồi dịch vụ sau thảm họa. | Chỉ có một bản sao hoặc một tài liệu hướng dẫn. |
| **RPO** | Mức mất dữ liệu tối đa được doanh nghiệp chấp nhận, thường biểu diễn bằng khoảng thời gian. | Độ trễ replication tức thời; replication lag chỉ là một tín hiệu. |
| **RTO** | Thời gian tối đa được chấp nhận để khôi phục dịch vụ hoặc chức năng tới mức đã cam kết. | Thời gian máy ảo khởi động hoặc kết nối DB thành công riêng lẻ. |

**Backup, replication và chuyển traffic giải quyết những loại lỗi khác nhau.** Ví dụ, lỗi phần cứng có thể được giải quyết bằng failover; xóa nhầm hoặc mã hóa dữ liệu độc hại có thể lan sang replica, nên cần bản backup sạch, lưu tách biệt và khả năng phục hồi theo mốc.

### 2.1. Xác định RPO và RTO ở cấp hành trình nghiệp vụ

Một yêu cầu như “RTO 30 phút” chưa đủ nếu không chỉ rõ điều gì được coi là đã khôi phục: trang chủ hiển thị, API đọc được dữ liệu, hay khách hàng có thể tạo đơn và thanh toán thành công?

Với từng dịch vụ, cần ghi:

- **Điểm bắt đầu đo RTO:** thời điểm dịch vụ trở nên không đáp ứng tiêu chí (để đánh giá tác động thực tế), đồng thời lưu thời điểm phát hiện và thời điểm tuyên bố sự cố.
- **Điểm kết thúc RTO:** thời điểm toàn bộ chức năng tối thiểu đã xác định vượt qua kiểm thử giao dịch, đáp ứng SLO chấp nhận trong trạng thái phục hồi.
- **Cách đo RPO:** thời điểm commit cuối cùng còn tồn tại và nhất quán trên hệ thống được khôi phục so với thời điểm mất nguồn hoặc mốc chốt được quy định.
- **Phạm vi:** ứng dụng nào, tenant nào, loại dữ liệu nào, khu vực nào; có loại trừ nghiệp vụ báo cáo hoặc tính năng phụ không?
- **Mục tiêu sau phục hồi:** phục vụ đầy đủ hay chế độ suy giảm có kiểm soát, chẳng hạn chỉ đọc hoặc tạm ngưng thanh toán.

Một hệ thống có thể đặt RPO khác nhau cho từng nhóm dữ liệu: dữ liệu giao dịch cần mất mát gần bằng không trong giới hạn thiết kế, dữ liệu cache có thể xây dựng lại, còn dữ liệu báo cáo có thể chậm nhiều giờ.

### 2.2. Tính RPO và RTO từ chứng cứ

Giả sử Region A bị ngừng hoạt động lúc **14:07:32**. Giao dịch mới nhất đã commit ở A là **14:07:30**, nhưng Region B chỉ áp dụng thay đổi tới **14:07:12**. Ở kịch bản phải kích hoạt B từ trạng thái đó:

\[
\text{Khoảng mất dữ liệu tiềm năng}
\approx 14{:}07{:}32 - 14{:}07{:}12 = 20\ \text{giây}
\]

Đây là phép ước tính minh họa theo thời điểm commit cuối đã được xác minh, không phải bảo đảm có đúng 20 giây giao dịch thực sự bị mất. Cần đối soát các transaction ID, phiên bản hoặc vị trí log: có thể không có giao dịch trong khoảng đó, nhưng cũng có thể có nhiều lệnh ghi quan trọng.

Nếu đến **14:14:02** người dùng mới hoàn tất được giao dịch kiểm tra ở B và ứng dụng đạt tiêu chí khôi phục, thì RTO quan sát được là **6 phút 30 giây** tính từ 14:07:32. Đo tới thời điểm DNS được đổi hoặc VM đã chạy sẽ cho một con số nhỏ hơn nhưng không đại diện cho dịch vụ đã phục hồi.

## 3. Chọn chiến lược bảo vệ dữ liệu phù hợp rủi ro

| Phương án | Cách phục hồi | Ưu điểm | Giới hạn cần kiểm thử |
| --- | --- | --- | --- |
| **Backup định kỳ tại một Region** | Dựng tài nguyên, phục hồi bản sao lưu gần nhất. | Triển khai tương đối đơn giản, chi phí thường thấp hơn mô hình dự phòng nóng. | RPO phụ thuộc lịch backup/log; RTO có thể dài; nếu Region mất, nơi chứa backup có thể không truy cập được. |
| **Backup sao chép sang Region/account độc lập** | Tạo hệ thống ở nơi khác rồi restore. | Có bản dự phòng tách khỏi khu vực nguồn; phù hợp DR ít thường xuyên. | Phải chứng minh backup, khóa giải mã, metadata, mạng và khả năng dựng lại đều sẵn sàng. |
| **Pilot light** | Giữ dữ liệu và thành phần nền ở Region phụ, dựng/tăng công suất ứng dụng khi có sự cố. | Cân bằng chi phí và thời gian phục hồi. | Provisioning, cấu hình và tăng công suất khi khẩn cấp có thể mất thời gian. |
| **Warm standby** | Duy trì một hệ thống phụ có khả năng chạy nhưng công suất thấp hơn. | RTO thường ngắn hơn pilot light nếu thiết kế đủ. | Chi phí chạy song song; phải thử scaling, replication và chuyển owner. |
| **Active-passive đa Region** | Region A chủ động nhận traffic/ghi; B chờ tiếp quản. | Dễ xác định write owner hơn active-active. | RPO tùy cơ chế sao chép; cần fencing và chuyển đường truy cập. |
| **Active-active đa Region** | Nhiều Region phục vụ đồng thời theo phân vùng hoặc chiến lược nhất quán. | Có thể cải thiện độ gần người dùng và tính sẵn sàng. | Xung đột ghi, thứ tự sự kiện, split-brain, chi phí và thiết kế dữ liệu phức tạp. |

Mức RTO/RPO thấp thường đòi hỏi đầu tư đáng kể vào tài nguyên luôn sẵn sàng, vận chuyển dữ liệu, tự động hóa và thử nghiệm. Không nên chọn active-active chỉ vì nghe có vẻ “không downtime”; hãy chứng minh cơ chế nhất quán và phạm vi lỗi mà kiến trúc thực sự chịu được.

### 3.1. Đồng bộ và bất đồng bộ giữa các Region

- **Replication bất đồng bộ:** nguồn có thể xác nhận ghi trước khi Region B nhận được; độ trễ thấp hơn trên đường ghi nhưng RPO khi mất A có thể lớn hơn 0. Cần theo dõi replication lag, log backlog và mức commit đã được xác minh.
- **Replication đồng bộ:** lệnh ghi có thể phải đợi xác nhận từ các bản sao theo cơ chế của hệ thống; cải thiện khả năng không mất dữ liệu trong các điều kiện nhất định nhưng tăng độ trễ và có thể giảm tính sẵn sàng khi mạng phân vùng. Khả năng đồng bộ **xuyên Region** phải được kiểm tra theo công nghệ cụ thể; không tự suy ra mọi CSDL đều hỗ trợ.
- **Chuyển vùng theo phân khu dữ liệu:** có thể giảm phạm vi lỗi nếu từng tenant hoặc phân vùng có owner rõ ràng, nhưng cần làm sạch routing và không cho ghi đồng thời.

**Không thể chỉ nhìn một nhãn “multi-region” để kết luận RPO = 0 hay RTO = 0.** Việc khôi phục còn phụ thuộc lúc phát hiện lỗi, điều kiện chọn primary mới, năng lực tải, DNS/client retry, khóa mã hóa và khả năng đối soát.

## 4. Kiến trúc tham chiếu để đánh giá phục hồi

~~~mermaid
flowchart LR
    Client[Người dùng và hệ thống tích hợp] --> Route[DNS / Global traffic routing]
    subgraph RA[Region A - primary]
       LB_A[Load balancer] --> APP_A[Ứng dụng A]
       APP_A --> DB_A[(Dữ liệu chủ A)]
       DB_A --> BAK_A[(Backup/PITR)]
    end
    subgraph RB[Region B - dự phòng]
       LB_B[Load balancer] --> APP_B[Ứng dụng B]
       APP_B --> DB_B[(Dữ liệu B)]
       BAK_B[(Backup độc lập)] --> DB_B
    end
    Route -->|Bình thường| LB_A
    Route -.->|Khi failover đã phê duyệt| LB_B
    DB_A -->|Replication: có thể trễ| DB_B
    BAK_A -->|Sao chép bảo vệ theo chính sách| BAK_B
    MON[Monitoring / Audit / Runbook] -.-> RA
    MON -.-> RB
~~~

Sơ đồ minh họa một phương án **active-passive**, không hàm ý mọi thành phần có thể hoạt động ngay khi chuyển tuyến. Khi đánh giá, cần xác nhận:

1. Region B có thể khởi tạo hoặc mở rộng đầy đủ application, database, queue, object storage, cache, certificate, key, secret và IAM không?
2. Bản sao dữ liệu ở B có được phục hồi thành một trạng thái **nhất quán và ghi được** theo cơ chế của DB không?
3. Cơ chế chuyển quyền ghi có ngăn hệ cũ tiếp tục chấp nhận write khi đường kết nối giữa các Region bị phân vùng không?
4. Global routing, DNS, health check và client connection có chuyển được traffic thật tới B không?
5. Hệ thống phụ thuộc bên ngoài (cổng thanh toán, email, identity provider, license server, webhook, batch) có được phép và có thể hoạt động từ B không?
6. Backup/PITR có tách khỏi sự cố logic ở DB chủ và có thể khôi phục khi control plane của Region A không dùng được không?

Trụ cột tin cậy yêu cầu xét **toàn bộ đường giao dịch**, không chỉ một thành phần đang có replica.

## 5. Kiểm thử phục hồi dữ liệu: quy trình đầy đủ

### 5.1. Bảo vệ nơi lưu backup trước khi thử restore

Một backup hữu dụng phải thỏa đồng thời điều kiện *tồn tại, truy cập được, giải mã được, khôi phục được, đúng dữ liệu và nằm trong ngân sách thời gian*. Kiểm tra:

| Lớp kiểm tra | Nội dung xác minh |
| --- | --- |
| Bản lưu | Lịch backup, phạm vi bảng/volume/object, transaction log, retention và tuổi backup cuối. |
| Tính độc lập | Backup được tách khỏi tài khoản/quyền có thể xóa nguồn; có lưu Region khác khi mục tiêu DR yêu cầu. |
| Bảo mật | Mã hóa, quản trị khóa, phân quyền restore, audit và thử khôi phục khi quyền nguồn không còn. |
| Toàn vẹn | Checksum hoặc cơ chế xác minh của công cụ, log backup, phục hồi thử và kiểm tra cấu trúc dữ liệu. |
| Khả năng khôi phục | Phiên bản engine, storage/IOPS, quota, dung lượng, hình ảnh hệ điều hành và tài nguyên mạng. |
| Nhất quán ứng dụng | Backup có đủ tất cả thành phần phụ thuộc để tạo trạng thái nghiệp vụ hợp lệ hay không. |

**Một thông báo “backup succeeded” chỉ xác nhận bước tạo bản lưu theo tiêu chí của công cụ.** Không chứng minh người dùng có thể giao dịch sau restore.

### 5.2. Bài kiểm thử restore trong môi trường cô lập

1. **Xác định mục tiêu:** chọn dataset, đối tượng cần phục hồi, RPO/RTO mục tiêu, ràng buộc bảo mật và tiêu chí nghiệm thu.
2. **Đặt mốc bằng chứng:** ghi thời điểm backup/PITR, version ứng dụng, schema DB, transaction ID hoặc watermark; tạo một số bản ghi kiểm thử không nhạy cảm có kết quả kỳ vọng.
3. **Cô lập:** phục hồi sang môi trường thử có mạng, tài khoản, identity và endpoint tách khỏi production. Vô hiệu hóa email/thanh toán/webhook thật để không phát sinh tác dụng phụ.
4. **Khôi phục:** chọn đúng backup hoặc mốc PITR; đo thời gian từ yêu cầu restore, provision tài nguyên đến lúc DB sẵn sàng phục vụ.
5. **Kiểm tra dữ liệu:** so số dòng, khóa quan trọng, checkpoint, checksum theo phạm vi nhất quán; kiểm tra khóa ngoại, định dạng, lịch sử thay đổi và bất biến nghiệp vụ.
6. **Kiểm tra ứng dụng:** chạy phiên bản app tương thích trên dữ liệu phục hồi; smoke test đọc, ghi vào môi trường thử, phân quyền và luồng giao dịch.
7. **Đo và ghi nhận:** thời điểm kết thúc, RPO/RTO đạt được, giới hạn, lỗi và khuyến nghị; thu dọn dữ liệu thử theo chính sách.

Ví dụ phép kiểm tra chi tiết cho hệ thống đơn hàng:

~~~sql
-- Ví dụ SQL minh họa; chạy trên phạm vi dữ liệu được chốt theo cùng mốc.
-- total_minor_unit lưu giá trị tiền bằng đơn vị nhỏ nhất để tránh sai số float.
SELECT
    tenant_id,
    COUNT(*) AS order_count,
    SUM(total_minor_unit) AS amount_total
FROM orders
WHERE created_at < :recovery_cutoff
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

Kết quả tổng hợp bằng nhau chưa đủ: hai lỗi có thể bù trừ, khiến tổng vẫn đúng. Cần so theo khóa đơn và nội dung quan trọng, hoặc chia thành các khoảng khóa cố định để tính checksum, rồi điều tra những nhóm lệch. Nếu phục hồi về thời điểm trước sự cố, bản ghi **sau mốc phục hồi** bị thiếu có thể là kết quả đúng của mục tiêu PITR, không tự động là lỗi restore.

### 5.3. Thử các loại hỏng dữ liệu khác nhau

| Tình huống | Bài kiểm thử nên thực hiện | Điều kiện thành công |
| --- | --- | --- |
| Mất một volume/instance | Tạo hệ thống mới và restore. | Dữ liệu cùng ứng dụng dùng được; RTO đạt. |
| Xóa nhầm bảng hoặc object | Phục hồi từ backup sạch hoặc PITR trước lệnh xóa. | Trạng thái nghiệp vụ được khôi phục; kiểm soát dữ liệu ghi sau mốc. |
| Schema migration lỗi | Phục hồi dữ liệu/schema phù hợp phiên bản ứng dụng. | App đọc/ghi hợp lệ; không mất trường quan trọng. |
| DB bị lỗi logic đã lan sang replica | Dùng backup tách biệt có lịch sử phiên bản. | Khôi phục trước mốc hỏng; không ghi đè trạng thái đúng. |
| Không truy cập được khóa mã hóa | Diễn tập quyền/khóa dự phòng theo chính sách. | Bản backup được giải mã đúng dưới quyền khẩn cấp có kiểm soát. |
| Region lưu backup không dùng được | Phục hồi từ bản sao ở Region/account đã chuẩn bị. | Không phụ thuộc các thành phần chỉ tồn tại ở Region lỗi. |

Các bài thử phá hủy dữ liệu phải dùng **dữ liệu tổng hợp và môi trường cô lập**, hoặc một game day production có phạm vi, quyền hạn, điểm dừng và cơ chế bảo vệ rõ ràng. Không dùng dữ liệu thật để tạo lỗi khó đảo ngược khi mục tiêu chỉ là xác minh quy trình restore.

## 6. Kiểm thử chuyển khu vực: chuyển traffic chỉ là một bước

### 6.1. Ba dạng diễn tập cần tách biệt

| Dạng bài thử | Bối cảnh | Có thể thực hiện thế nào? |
| --- | --- | --- |
| **Simulation / tabletop** | Giả định Region chính mất; nhân sự mô tả quyết định. | Kiểm tra runbook, escalation, quyền, contact, điểm bất đồng; chưa chứng minh RTO. |
| **Isolated technical drill** | Dựng môi trường hoặc traffic thử ở Region dự phòng. | Khôi phục/đẩy bản sao, tạo primary thử, chạy E2E test, không chuyển ghi sản xuất. |
| **Controlled switchover/game day** | Chuyển một phần traffic thật hoặc chuyển quyền chủ có kế hoạch. | Cần write fence, phê duyệt, rollback/roll-forward, theo dõi SLO; cung cấp bằng chứng sát thực tế hơn. |

Một bài test dry-run không thể thay thế hoàn toàn kiểm thử chuyển traffic và quyền ghi của production, nhưng cho phép phát hiện phần lớn lỗi trước khi chấp nhận rủi ro thật. Độ sâu bài thử phải tương ứng mức quan trọng nghiệp vụ.

### 6.2. Runbook chuyển khu vực tham khảo

**Chuẩn bị trước sự cố**

1. Định nghĩa vai trò chỉ huy sự cố, người phụ trách dữ liệu, mạng, ứng dụng và bảo mật; quy định ai có quyền quyết định chuyển Region.
2. Đồng bộ IaC, image, cấu hình, secret, certificate, policy, quota và capacity ở B; thử build độc lập với A.
3. Lập danh sách dịch vụ phải hoạt động ở B; tạo health check và giao dịch synthetic, công cụ đối soát và kênh liên lạc dự phòng.
4. Viết quy tắc chọn owner, fencing, xác định RPO hiện tại, giới hạn chấp nhận mất dữ liệu và phương án xử lý giao dịch đang chạy.
5. Chuẩn bị định tuyến global, DNS/TTL, xử lý connection pool và cache; kiểm thử đối tác và bên thứ ba cho endpoint ở B.

**Khi mất Region chính**

1. **Phát hiện và tuyên bố:** xác minh lỗi ảnh hưởng chức năng nghiệp vụ; đánh dấu thời điểm t0 để đo RTO, đánh giá phạm vi và kích hoạt đúng runbook.
2. **Đánh giá tính toàn vẹn dữ liệu:** xác định trạng thái last-applied ở B, backlog, log chưa chuyển và RPO ước tính; tránh cho người dùng tiếp tục ghi sai owner khi trạng thái A chưa chắc chắn.
3. **Chặn đường ghi cũ (fencing):** bảo đảm chỉ một nơi được chấp nhận ghi theo cơ chế được thiết kế (ví dụ epoch/lease có cơ chế chống chủ cũ tái xuất hiện, quorum hoặc fencing hạ tầng phù hợp). Nếu không chắc chắn ngăn được split-brain, ưu tiên chế độ đọc hoặc tạm dừng ghi thay vì kích hoạt hai primary.
4. **Kích hoạt B:** hoàn tất promotion/restore dữ liệu, cập nhật vai trò primary, mở rộng compute, bật queue/worker đúng trách nhiệm; xác minh key/secret và các tích hợp.
5. **Chuyển đường truy cập:** điều chỉnh global traffic steering hoặc DNS theo cơ chế thực tế; theo dõi caching, kết nối giữ lâu và client retry để tránh traffic còn đi về A.
6. **Xác nhận phục hồi:** chạy giao dịch đọc và ghi có kiểm soát; kiểm tra dữ liệu quan trọng, phát hành webhook/queue chính xác một lần về mặt tác dụng nghiệp vụ, độ trễ và tỷ lệ lỗi ở B.
7. **Ghi nhận mốc:** đo thời điểm người dùng thực sự giao dịch trở lại, thời điểm commit cuối an toàn và mức mất/thiếu dữ liệu; thông báo trạng thái theo cơ chế của tổ chức.

**Sau khi ổn định**

1. Đối soát những lệnh ghi người dùng gửi trong khoảng lỗi, xử lý retry/idempotency và mọi thao tác chưa biết kết quả.
2. Sao lưu trạng thái mới ở B, khôi phục giám sát và capacity, kiểm tra chi phí tăng thêm.
3. Khi A trở lại, không tự động cho A ghi. Xác định B đang là owner và chọn chiến lược failback đã kiểm chứng.

### 6.3. Vì sao split-brain là rủi ro trọng yếu?

Giả sử đường mạng giữa hai Region đứt nhưng cả A và B vẫn nhận được traffic riêng. Nếu A tiếp tục xác nhận đơn hàng và B cũng được promote làm primary, hệ thống có thể nhận hai lệnh cập nhật tồn kho hoặc thanh toán đối nghịch. Khi kết nối trở lại, ghép hai luồng một cách tự động có thể làm sai nghiệp vụ.

~~~mermaid
flowchart LR
    CLIENT[Client / API] --> G[Điều phối owner ghi]
    G -->|Epoch n: chỉ A ghi| A[(Region A)]
    G -.->|Standby| B[(Region B)]
    A -->|Sao chép| B
    F[Quy trình fencing + chọn primary] -->|Chuyển sang epoch n+1| G
    F -->|A mất quyền ghi| A
    G -->|Epoch n+1: chỉ B ghi| B
~~~

Sơ đồ diễn giải **ý đồ kiểm soát**; cơ chế fencing/epoch thực tế phải được toàn bộ lớp ghi tuân thủ, được xác nhận dưới lỗi phân vùng mạng và sau restart. Chỉ đổi DNS không phải là fencing đáng tin cậy vì client cũ vẫn có thể giữ kết nối hoặc gọi trực tiếp endpoint A.

## 7. Kiểm chứng dữ liệu sau failover

Sau khi B được promote, đừng chỉ kiểm tra API trả HTTP 200. Cần đối soát theo phạm vi nghiệp vụ:

| Lớp | Cần kiểm tra | Ví dụ |
| --- | --- | --- |
| **Giao dịch đã commit** | Những giao dịch A xác nhận trước sự cố có tồn tại ở B không? | Đối chiếu order ID, payment reference, commit marker. |
| **Lệnh chưa rõ kết quả** | Request timeout có thể đã commit trước khi client retry. | Tìm theo idempotency key trước khi tạo lại đơn. |
| **Thứ tự và khóa** | Các bản ghi phụ thuộc và version có đúng thứ tự không? | order_item không tồn tại trước order, inventory revision không lùi. |
| **Dữ liệu phi quan hệ** | Object, message, cache, search index có đủ hoặc tái tạo được không? | Ảnh hóa đơn, event chưa xử lý, index sản phẩm. |
| **Bất biến nghiệp vụ** | Tính đúng trong toàn bộ trạng thái sau khôi phục. | Tổng tiền order = tổng dòng; thanh toán không trùng; tồn kho không âm ngoài quy tắc. |
| **Ứng dụng và tích hợp** | API, auth, batch, external callback, queue hoạt động đúng. | Mua thử và hoàn trả thử trong sandbox. |

Các điểm cần chú ý:

- Với replication bất đồng bộ, **mốc commit ở A có thể cao hơn mốc applied ở B**. Phải ghi chính xác vùng mất dữ liệu, phân loại giao dịch có thể khôi phục từ nguồn khác và xử lý theo quy trình nghiệp vụ.
- Không replay mù mọi message sau failover. Nếu có lệnh đã thành công ở A hoặc được B áp dụng nhưng ack bị mất, cần cơ chế idempotency theo thực thể và tác dụng phụ.
- Cache và search index có thể bị trễ hoặc tái tạo; đừng xem dữ liệu cache là source of truth.
- Khóa, chứng chỉ và identity liên quan dữ liệu mã hóa cũng là điều kiện khôi phục. Một backup có đủ byte nhưng không có khóa giải mã hợp lệ vẫn không sử dụng được.
- Nếu có nhiều kho dữ liệu, phải ghi rõ **mốc nhất quán xuyên hệ thống** hoặc cách hợp nhất chúng. Snapshot đồng thời theo đồng hồ không tự bảo đảm tính nhất quán giao dịch xuyên DB, queue và object store.

## 8. Các phụ thuộc bị bỏ sót trong diễn tập Region

Chuyển Region sẽ thất bại nếu hệ thống DR lệ thuộc một thành phần chỉ có ở Region A.

| Thành phần | Tình huống rủi ro | Bằng chứng mong đợi |
| --- | --- | --- |
| DNS/global routing | TTL, cache, connection pooling hoặc health check sai khiến client tiếp tục tới A. | Đo lưu lượng thật sau chuyển tuyến, tỷ lệ lỗi theo địa chỉ/vùng. |
| Cấu hình và IaC | Template, state, artifact registry hoặc image chỉ ở A. | Dựng B thành công khi giả lập A không truy cập được. |
| IAM và secret | Role không đủ quyền, secret/KMS key không khả dụng ở B. | App B giải mã dữ liệu và truy cập phụ thuộc bằng danh tính hợp lệ. |
| Network | CIDR, peering, route, private endpoint hoặc allowlist đối tác không có ở B. | Kiểm tra end-to-end trên mạng B. |
| Data plane | DB, queue, object, cache, search index không cùng mốc hoặc không có mặt. | Kiểm tra nội dung, replay và cấu trúc phụ thuộc. |
| Capacity/quota | B là standby nhỏ, không scale được vì thiếu quota hoặc hết công suất sẵn có. | Thử tăng đến tải phục hồi và quan sát saturation. |
| External integration | Cổng thanh toán, webhook hoặc provider danh tính chỉ tin IP/URL A. | Giao dịch thử ở B có xác nhận của hệ thống liên quan. |
| Observability và quy trình | Dashboard, log hoặc kênh liên lạc cũng đặt ở A. | Quan sát và điều phối hoạt động khi A giả định không dùng được. |

**Phân biệt lỗi data plane và control plane:** hệ thống đang chạy có thể tiếp tục phục vụ trong khi các API điều khiển tài nguyên không hoạt động, hoặc ngược lại. Runbook không nên giả định luôn có thể tạo VM, thay policy hay restore từ giao diện quản lý của Region đang lỗi; hãy thử những thao tác thiết yếu từ địa điểm và quyền thật sẽ dùng lúc sự cố.

## 9. Thiết kế bài diễn tập an toàn, lặp lại được

Một bài kiểm thử tốt phải có giả thuyết, điều kiện thành công, phạm vi ảnh hưởng và bằng chứng trước khi chạy. Mẫu tối thiểu:

| Trường | Nội dung ví dụ |
| --- | --- |
| **ID và phạm vi** | DR-REGION-01, ứng dụng đặt hàng và dữ liệu giao dịch của tenant kiểm thử. |
| **Giả thuyết** | Region A không truy cập được, Region B có thể nhận traffic đọc/ghi trong 15 phút. |
| **RPO/RTO mục tiêu** | RPO ≤ 60 giây, RTO ≤ 15 phút, tính theo định nghĩa đã thống nhất. |
| **Điểm lỗi được tạo** | Cô lập đường truy cập thử vào A và mất quyền điều khiển các thành phần A trong phạm vi diễn tập. |
| **Điều kiện bảo vệ** | Không chuyển traffic thật ngoài nhóm thử; mock email/thanh toán; có rollback và ngưỡng dừng. |
| **Tín hiệu quan sát** | Synthetic success, p95/p99, DB applied position, split-brain alarm, queue backlog, trace. |
| **Bằng chứng đầu ra** | Thời gian lỗi/khôi phục, mốc dữ liệu, ảnh chụp trạng thái, log quyết định và kết quả đối soát. |
| **Người chịu trách nhiệm** | Incident commander, dữ liệu, ứng dụng, mạng, bảo mật, người phê duyệt. |

### 9.1. Ma trận bài kiểm thử cần có

| ID | Sự cố giả lập | Điều cần chứng minh |
| --- | --- | --- |
| DR-01 | Cần restore một DB/volume từ backup | Restore thành công, dữ liệu hợp lệ, app dùng được, RTO/RPO đạt. |
| DR-02 | Xóa nhầm dữ liệu rồi cần PITR | Chọn được điểm khôi phục sạch, xử lý ghi phát sinh sau mốc hợp lý. |
| DR-03 | Region A mất hoàn toàn | B dựng/chạy được độc lập, chuyển traffic và owner an toàn. |
| DR-04 | Mất liên lạc A↔B, cả hai vẫn còn máy hoạt động | Không xuất hiện hai nơi nhận ghi cho cùng dữ liệu; có fencing. |
| DR-05 | Replication trễ vượt ngưỡng | Giám sát phát hiện, quy trình từ chối/hoãn promotion hoặc chấp nhận rủi ro có thẩm quyền. |
| DR-06 | B thiếu quota/secret/khóa | Phát hiện trước khi chuyển traffic; kịch bản khắc phục và trách nhiệm rõ. |
| DR-07 | API đã ghi thành công nhưng client timeout | Retry không tạo giao dịch/tác dụng phụ trùng. |
| DR-08 | Failback về A sau nhiều giờ chạy ở B | Tái đồng bộ, đối soát và chuyển owner trở lại không phân nhánh dữ liệu. |
| DR-09 | Backup hoặc replica chứa lỗi logic | Có khả năng chọn bản sạch, phục hồi và giới hạn mất dữ liệu đúng chính sách. |

Tần suất diễn tập phụ thuộc mức độ quan trọng và thay đổi kiến trúc. Ví dụ, có thể kiểm tra restore định kỳ theo tháng/quý, diễn tập runbook theo quý và thử chuyển Region sau những thay đổi lớn; đây chỉ là lịch tham khảo, không thay thế yêu cầu pháp lý hay SLO của tổ chức.

### 9.2. Các mức độ bằng chứng

1. **Cấp 1 – Chỉ tài liệu:** có sơ đồ, runbook và danh sách backup; chưa chứng minh chức năng.
2. **Cấp 2 – Thử thành phần:** restore được database hoặc khởi động app ở B, nhưng chưa kiểm tra luồng nghiệp vụ.
3. **Cấp 3 – Thử tích hợp:** giao dịch end-to-end, dữ liệu và các phụ thuộc ở môi trường kiểm thử hoạt động theo mục tiêu.
4. **Cấp 4 – Diễn tập chuyển đổi có kiểm soát:** có đo traffic thật/phạm vi giới hạn, write fencing, SLO và hành vi người dùng.
5. **Cấp 5 – Vận hành được lặp lại:** bằng chứng mới, tự động hóa, cảnh báo, hậu kiểm và kết quả sau nhiều lần diễn tập hoặc thay đổi lớn.

Các cấp này là **thang đánh giá minh họa cho bài học**, không phải tiêu chuẩn chứng nhận chính thức. Khi chấm một kiến trúc, cần nêu rõ loại bài thử và bằng chứng; không công bố “đạt DR” chỉ dựa trên backup status.

## 10. Đánh giá kết quả: tiêu chí pass/fail và các con số

### 10.1. Bộ tiêu chí nghiệm thu

| Hạng mục | Tiêu chí chấp nhận mẫu | Cách đo |
| --- | --- | --- |
| RPO | Không quá 60 giây với dữ liệu đơn hàng. | Commit ID hoặc watermark cuối có ở đích so với thời điểm sự cố. |
| RTO | Không quá 15 phút cho giao dịch tạo đơn. | Thời gian gián đoạn thực tới lúc synthetic/E2E tạo đơn thành công và đạt ngưỡng SLO. |
| Tính toàn vẹn | Không có khác biệt chưa giải thích ở dữ liệu giao dịch nằm trước recovery point đã chốt. | Đối soát theo khóa, tổng tiền, trạng thái, bất biến. |
| Quyền ghi | Không có hai primary cùng chấp nhận ghi trên một phạm vi. | Audit log, fencing token/epoch, thử lỗi phân vùng mạng. |
| Khả năng hoạt động | Đăng nhập, đặt hàng, đọc lịch sử và tích hợp thiết yếu hoạt động. | Kịch bản nghiệp vụ đại diện; log/trace và kết quả người dùng. |
| Khả năng vận hành | On-call tìm được runbook, quyền và thực hiện từng bước. | Timeline, bằng chứng thao tác, lỗi điều phối. |
| Khả năng chịu tải | B đáp ứng tải phục hồi đã thống nhất. | Load test, p95/p99, lỗi, saturation CPU/DB/queue. |
| Bảo mật và tuân thủ | Không lộ dữ liệu; Region B hợp quy định lưu trữ và truy cập. | Kiểm tra vị trí dữ liệu, IAM, mã hóa, audit, retention. |

Đây là các ngưỡng **giả định**, chỉ phục vụ luyện tập. Từng hệ thống cần thương lượng RPO/RTO và SLO từ tác động kinh doanh cùng chi phí phù hợp. Nếu một tiêu chí tối quan trọng không đạt, đánh giá tổng thể cần ghi **FAIL hoặc CONDITIONAL**, dù các tiêu chí khác đều tốt.

### 10.2. Ví dụ đối soát một lần restore

Một ứng dụng chỉ sao lưu đầy đủ lúc **09:00** và chưa có transaction log phục hồi sau thời điểm đó. Sự cố xảy ra lúc **09:47**. DB được restore và ứng dụng qua kiểm thử giao dịch lúc **10:42**.

- **RPO quan sát tối đa theo thời gian:** 47 phút, do bản gần nhất khôi phục tới 09:00. Nếu có transaction log/PITR áp dụng được tới mốc mới hơn thì phải dùng mốc đó, không lấy 09:00 máy móc.
- **RTO quan sát:** 55 phút, từ 09:47 đến 10:42.
- Với yêu cầu giả định RPO ≤ 15 phút và RTO ≤ 60 phút, kết quả **RPO FAIL, RTO PASS**.
- Hệ thống chỉ được kết luận dữ liệu đúng khi đã kiểm tra bản ghi tới đúng recovery point; cần giải thích xử lý những giao dịch đã commit từ 09:00 tới 09:47.

Ví dụ cho thấy chỉ đo “khôi phục xong trong một giờ” chưa đủ đánh giá phương án dữ liệu.

### 10.3. Nhật ký bằng chứng nên lưu

~~~text
Exercise: DR-REGION-01
Scope: order-api, region A -> region B, tenant thử nghiệm
Target: RPO <= 60 s; RTO <= 15 min
Outage started: 14:07:32
Last verified commit on A: 14:07:30
Last applied commit on B: 14:07:12
Service restored (E2E passed): 14:14:02
Observed potential data-loss window: 20 s
Observed RTO: 6 min 30 s
Write fencing: verified by audit + controlled test
Integrity check: orders and payments within recovery watermark PASS
Remaining risk: third-party callback retries need further test
Decision: conditional pass; follow-up assigned to integration owner
~~~

Mẫu báo cáo nên kèm đường dẫn bằng chứng (dashboards, log được che dữ liệu nhạy cảm, kết quả so sánh, bản ghi quyết định), người xác nhận và ngày kiểm thử. Nếu chỉ có câu “thử rồi, ổn” thì khó kiểm toán và không thể đánh giá tiến bộ lần sau.

## 11. Failback: chuyển về Region gốc cũng cần kiểm thử

Khi A phục hồi, B có thể đã có nhiều giao dịch mới. **Không được tự động chuyển traffic và ghi về A** nếu A chưa có toàn bộ thay đổi mới hoặc vẫn được coi là primary ở một số client.

Quy trình tham khảo:

1. Giữ B làm owner ghi trong khi A được dựng lại hoặc đồng bộ từ B; không nhận ghi độc lập ở A.
2. Xác minh dữ liệu A bắt kịp mốc B theo cơ chế sao chép hỗ trợ; đối soát giao dịch quan trọng và đảm bảo không có sự kiện lỗi chưa xử lý.
3. Lập thời điểm switchover có kế hoạch; chặn/đệm hoặc định tuyến lệnh ghi theo cơ chế thiết kế, chốt watermark và đổi vai trò primary một cách nguyên tử theo khả năng hệ thống.
4. Chuyển global traffic tới A; xác thực read/write, authentication, queue/webhook, độ trễ và theo dõi kết nối còn tới B.
5. Đưa B về vai trò dự phòng, xác lập sao chép đúng chiều và kiểm tra kế hoạch DR tiếp theo.

Nếu không có cách chuyển ngược an toàn, phương án ưu tiên có thể là **tiếp tục vận hành ở B (roll forward)** và sửa chữa A trong trạng thái bị chặn ghi. Quyết định phải dựa trên khả năng bảo toàn giao dịch, không dựa trên mong muốn trở lại cấu hình ban đầu càng sớm càng tốt.

## 12. Đánh đổi theo Well-Architected

| Trụ cột | Câu hỏi đánh giá | Đánh đổi điển hình |
| --- | --- | --- |
| **Reliability – Độ tin cậy** | Có dữ liệu sạch và Region dự phòng độc lập, fencing, khả năng failover và restore đã kiểm chứng? | RPO/RTO thấp thường cần replication, capacity và tự động hóa nhiều hơn. |
| **Security – Bảo mật** | Backup, khóa mã hóa và quyền khẩn cấp tách biệt ra sao; thử diễn tập có làm lộ dữ liệu? | Quyền tối thiểu cần đi cùng quy trình cấp quyền khẩn cấp có kiểm toán. |
| **Operational Excellence – Vận hành hiệu quả** | Có runbook, on-call, giám sát, bài thử định kỳ, postmortem và cải tiến? | Tự động hóa giảm thao tác nhưng bản thân pipeline DR cũng phải được thử. |
| **Performance Efficiency – Hiệu quả hiệu năng** | Region B có đủ quota, DB IOPS, mạng và công suất ở tải phục hồi? | Warm standby nhỏ tiết kiệm chi phí nhưng mất thời gian scale. |
| **Cost Optimization – Tối ưu chi phí** | Tính đủ sao chép xuyên Region, backup, egress, standby, diễn tập, lưu log và nhân sự? | Hot standby tăng phí nhưng có thể giảm tổn thất kinh doanh khi ngừng dịch vụ. |
| **Sustainability – Bền vững** | Tài nguyên dự phòng có được sizing hợp lý, có chính sách lưu trữ/xóa và kế hoạch diễn tập tiết kiệm? | Giảm VM dự phòng quá mức có thể khiến RTO không đạt. |

Một kiến trúc không có DR cho Region có thể vẫn phù hợp với một workload nội bộ có thể gián đoạn nhiều ngày; ngược lại, quy trình thanh toán quan trọng cần mục tiêu phục hồi nghiêm ngặt hơn. **Đánh giá kiến trúc phải nối quyết định kỹ thuật với tác động kinh doanh**, thay vì áp một cấu hình đa Region cho mọi ứng dụng.

### 12.1. Tính chi phí phục hồi, không chỉ chi phí duy trì DR

Một mô hình sơ bộ có thể xem xét:

\[
\text{Chi phí kỳ vọng}
= \text{chi phí DR định kỳ}
+ \text{chi phí diễn tập}
+ \text{xác suất gián đoạn}\times\text{thiệt hại nếu gián đoạn}
\]

Đây là khung so sánh đơn giản, không phải công thức tài chính đầy đủ. Xác suất và thiệt hại thường khó ước tính; hãy dùng các kịch bản nhạy cảm về downtime, mất dữ liệu, vi phạm nghĩa vụ và số giao dịch bị ảnh hưởng, tránh đưa ra độ chính xác giả tạo.

## 13. Các sai lầm đánh giá thường gặp

| Kết luận sai | Vì sao sai | Bằng chứng cần thay thế |
| --- | --- | --- |
| “Đã bật backup thì khôi phục được.” | Backup có thể hỏng, thiếu quyền/khóa hoặc không tương thích phiên bản. | Restore thử và chạy ứng dụng trên dữ liệu phục hồi. |
| “Replica lag bằng 0 thì RPO bằng 0.” | Chỉ số đo không chứng minh mọi commit đã áp dụng hoặc không bị xóa/hỏng. | Mốc commit, watermark, đối soát và chính sách mất dữ liệu. |
| “DNS trỏ sang B thì failover xong.” | Client cache, kết nối cũ, thiếu service và DB có thể khiến chức năng vẫn lỗi. | End-to-end synthetic và giao dịch có kiểm soát từ nhiều client. |
| “Hai Region cùng ghi thì chắc chắn sẵn sàng hơn.” | Split-brain, xung đột và đồng hồ khác nhau có thể làm sai dữ liệu. | Quy tắc owner, kiểm thử phân vùng mạng, fencing và hòa giải. |
| “Thử chuyển vùng trong staging đã chứng minh production đạt RTO.” | Kích thước dữ liệu, traffic, quota và tích hợp khác thực tế. | Diễn tập đại diện, kiểm tra năng lực và đo độ sai khác với production. |
| “Failback chỉ cần đảo route.” | A có thể thiếu toàn bộ giao dịch phát sinh trên B. | Reverse sync, đối soát, đổi chủ có kiểm soát và thử failback. |
| “CSDL lên rồi nghĩa là ứng dụng đã phục hồi.” | Auth, queue, object, email/thanh toán và frontend vẫn có thể lỗi. | Kiểm thử các luồng nghiệp vụ tối thiểu đã thỏa thuận. |
| “Có cơ chế chuyển vùng nhưng không cần diễn tập.” | Lỗi cấu hình thường chỉ xuất hiện khi chuyển quyền hoặc thiếu dịch vụ phụ thuộc. | Game day định kỳ, báo cáo và cải tiến theo nguyên nhân. |

## 14. Bài tập thực hành đánh giá kiến trúc

### Đề bài

Một nền tảng thương mại điện tử dùng Region A làm nơi phục vụ chính, Region B làm warm standby. Cơ sở dữ liệu giao dịch sao chép bất đồng bộ sang B; object storage sao chép theo chính sách riêng; backup hằng ngày được giữ tại A, bản copy backup sang B hoàn tất sau khi tạo. Ứng dụng B chạy ở 25% công suất A và phải scale khi có sự cố. Đối tác thanh toán chỉ allowlist một IP outbound của A.

Yêu cầu nghiệp vụ: **RPO ≤ 2 phút**, **RTO ≤ 20 phút** cho chức năng tạo đơn và xác nhận thanh toán. Khi mô phỏng ngắt A, sau 4 phút đội vận hành mới phát hiện; họ cần thêm 8 phút để promote DB và scale app; thêm 6 phút để chuyển traffic. Việc thử thanh toán tại B thất bại vì allowlist; sau 12 phút nữa mới được đối tác thay đổi cấu hình. Tại thời điểm lỗi, Region B trễ 90 giây theo mốc commit đã xác minh.

### Yêu cầu người học

1. Xác định RPO tiềm năng và RTO quan sát theo định nghĩa end-to-end.
2. Đánh giá PASS/FAIL đối với hai mục tiêu.
3. Chỉ ra ba điểm yếu chính và các bài kiểm thử bổ sung.
4. Đề xuất một phương án giảm RTO mà chưa cần chuyển sang active-active.
5. Giải thích cần thử restore riêng dù đã có replica bất đồng bộ ở B.

### Hướng dẫn phân tích

- **RPO tiềm năng:** 90 giây nếu không lấy thêm được log/giao dịch từ A; nằm trong ngưỡng 2 phút theo giả định mốc commit được xác nhận và không có thay đổi thiếu khác. Cần đối soát từng giao dịch quan trọng; kết luận RPO cuối cùng phải dựa trên dữ liệu còn lại.
- **RTO:** 4 + 8 + 6 + 12 = **30 phút** từ lúc mất dịch vụ tới khi thanh toán hoạt động; vì quy trình thanh toán thuộc phạm vi mục tiêu nên **RTO FAIL** so với 20 phút. Mốc 18 phút sau đổi traffic chưa phải khôi phục end-to-end.
- **Điểm yếu:** allowlist đối tác không có Region B; năng lực warm standby chưa chứng minh thời gian scale; lịch backup có nguy cơ không xử lý được lỗi logic hoặc mất vùng lưu nếu quá phụ thuộc A. Cần thêm kiểm thử tăng tải, điều phối mạng/đối tác và restore bản backup sạch từ B.
- **Cải thiện:** cấu hình allowlist/endpoint dự phòng với đối tác từ trước; chuẩn bị capacity/quota và image ở B; tự động hóa promotion khi đáp ứng quy tắc fencing; giám sát tác động nghiệp vụ và chạy synthetic payment từ B định kỳ.
- **Vì sao cần restore:** xóa nhầm, sửa nhầm và hỏng logic có thể được replication sang B; muốn quay về mốc sạch cần backup/PITR độc lập có thể giải mã và phục hồi.

### Biến thể nâng cao

Nếu A không mất hẳn mà chỉ bị phân vùng mạng, thử xem cả A lẫn B có cùng nhận lệnh ghi hay không. Nếu có, hệ thống chưa đạt kiểm chứng về chủ quyền ghi dù RPO/RTO ở kịch bản mất Region hoàn toàn từng đạt. Hãy đề xuất write fencing hoặc chuyển vào chế độ chỉ đọc khi không thể xác định owner duy nhất.

## 15. Checklist nghiệm thu một kiến trúc phục hồi và chuyển Region

### Yêu cầu và bảo vệ dữ liệu

- [ ] Có phân hạng dữ liệu/ứng dụng, RPO/RTO, SLO và cách đo end-to-end được nghiệp vụ xác nhận.
- [ ] Backup/PITR có phạm vi, retention, tính độc lập, chính sách mã hóa và quyền restore rõ ràng.
- [ ] Đã restore sang môi trường cô lập, giải mã, kiểm tra schema và giao dịch ứng dụng thành công.
- [ ] Có quy tắc đối soát theo commit/watermark, khóa dữ liệu và bất biến nghiệp vụ; không còn sai lệch trọng yếu chưa giải thích.
- [ ] Đã thử một lỗi logic hoặc xóa nhầm mà replica không bảo vệ được.

### Chuyển khu vực và vận hành

- [ ] Region dự phòng dựng được mà không phụ thuộc tài nguyên chỉ có ở Region chính.
- [ ] Đã kiểm tra capacity/quota, mạng, DNS, TLS, IAM/secret/key và các tích hợp bên ngoài tại Region dự phòng.
- [ ] Có cơ chế xác định owner ghi, fencing hoặc biện pháp ngăn split-brain được thử dưới lỗi phân vùng.
- [ ] Có runbook phát hiện, quyết định go/no-go, chuyển dữ liệu/traffic, smoke test, theo dõi và điều phối sự cố.
- [ ] Bài thử đo đúng RPO/RTO, tỷ lệ lỗi và giao dịch thực tế; có log mốc thời gian.
- [ ] Đã diễn tập phục hồi từ lỗi failover, kế hoạch failback hoặc roll-forward và đối soát dữ liệu ghi mới.
- [ ] Có báo cáo bằng chứng, chủ sở hữu tồn đọng, hạn xử lý và lịch diễn tập lại sau thay đổi quan trọng.

### Đánh đổi kiến trúc

- [ ] Chi phí backup, sao chép xuyên Region, standby, network egress, quan sát và diễn tập nằm trong kế hoạch.
- [ ] Bảo mật, vị trí dữ liệu và nghĩa vụ tuân thủ áp dụng cho cả nơi lưu backup lẫn Region phục hồi.
- [ ] Kết luận kiến trúc nêu rõ điều kiện đạt, điểm chưa kiểm chứng và mức rủi ro được chấp nhận.

**Kết luận:** câu hỏi đánh giá không phải “kiến trúc có backup và Region B không?”, mà là **“đã chứng minh được dữ liệu đúng, quyền ghi an toàn và người dùng sử dụng được dịch vụ trong RPO/RTO hay chưa?”**. Chỉ khi restore, chuyển Region, đối soát và failback được diễn tập với bằng chứng đo được, thiết kế phục hồi mới có cơ sở để được chấp nhận.
