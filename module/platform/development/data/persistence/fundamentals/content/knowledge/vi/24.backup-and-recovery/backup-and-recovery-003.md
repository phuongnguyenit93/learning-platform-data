# Xác định mục tiêu thời gian khôi phục (RTO)

Một ứng dụng Java dùng PostgreSQL có thể chạy ổn định nhiều tháng, nhưng khi cơ sở dữ liệu hoặc cả vùng hạ tầng gặp sự cố, câu hỏi quan trọng không chỉ là **“có bản sao lưu không?”**. Doanh nghiệp còn cần biết: **mất bao lâu để người dùng có thể tiếp tục thực hiện một thao tác nghiệp vụ thiết yếu?** Nếu nhóm vận hành phát hiện lỗi sau 12 phút, mất 25 phút để phục hồi database và thêm 20 phút để các API kết nối đúng và đối soát dữ liệu, hệ thống đã gián đoạn gần một giờ, dù bản thân thao tác restore chỉ mất 25 phút.

**Recovery Time Objective (RTO)** là **mục tiêu thời gian tối đa có thể chấp nhận để khôi phục dịch vụ sau một gián đoạn đã xác định**. Đây là mục tiêu nghiệp vụ và vận hành, không phải tính năng mà một lệnh backup tự cung cấp. Đặt RTO cần kết hợp đánh giá tác động kinh doanh, kiến trúc dự phòng, khả năng restore, quy trình phát hiện và điều phối sự cố, kiểm thử bằng thời gian thực tế.

Bài thuộc chương **Sao lưu và khôi phục** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module giúp người học nắm lưu trữ bền vững trong ứng dụng, từ mô hình dữ liệu, lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập, kiểm soát đồng thời, xử lý kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng cho Java. Nội dung sử dụng PostgreSQL, WAL, backup/PITR, chiến lược HA và Spring/JDBC làm ví dụ. Các lệnh cấu hình bên dưới mang tính **minh họa trong môi trường thử nghiệm/diễn tập**, không phải runbook đã kiểm chứng để chạy trực tiếp trên production.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Định nghĩa RTO có **mốc bắt đầu, mốc kết thúc, phạm vi dịch vụ và điều kiện chấp nhận** rõ ràng.
- Phân biệt **RTO, RPO, thời gian phát hiện, thời gian khôi phục thực tế, availability và SLA/SLO**.
- Chuyển yêu cầu nghiệp vụ thành **ngân sách thời gian cho phát hiện, quyết định, restore/failover, kết nối lại, kiểm tra dữ liệu và mở traffic**.
- So sánh khả năng đáp ứng RTO của **cold restore, warm standby, hot standby, failover tự động, backup và point-in-time recovery (PITR)**.
- Nhận diện tác động của dung lượng dữ liệu, tốc độ đọc backup, mạng, WAL replay, dependency và cơ chế định tuyến tới thời gian thực tế.
- Thiết kế runbook/diễn tập phục hồi có thể đo, lặp lại và chứng minh dịch vụ Java thực sự hoạt động.
- Xây dựng báo cáo kết quả diễn tập, nhận diện trường hợp mục tiêu RTO không thể đạt và lập kế hoạch cải thiện.

## 2. RTO được tính cho dịch vụ nào và sự cố nào?

Một hệ thống có thể có nhiều chức năng:

~~~text
Người dùng
   |
   +-- Đăng nhập / xác thực
   +-- Tra cứu sản phẩm
   +-- Đặt hàng / thanh toán
   +-- Xem lịch sử đơn
   +-- Xuất báo cáo
            |
            v
API Java -> PostgreSQL -> Cache / broker / các dịch vụ phụ thuộc
~~~

Không nhất thiết mọi chức năng đều có cùng RTO. Ví dụ **đặt hàng** có thể cần phục hồi trong 30 phút, còn **xuất báo cáo tuần** được phép gián đoạn vài giờ. Tương tự, yêu cầu khôi phục sau **mất một database instance** có thể khác với **mất cả region, xóa nhầm bảng, mã độc phá dữ liệu hoặc lỗi schema do deploy**.

Một tuyên bố RTO tốt có cấu trúc:

> Trong kịch bản mất một máy PostgreSQL primary nhưng vùng hạ tầng và một standby đủ điều kiện còn hoạt động, chức năng **đọc và tạo đơn hàng** phải được phục hồi trong **15 phút kể từ thời điểm dịch vụ không còn đáp ứng tiêu chí đã định**, với kiểm tra dữ liệu và đường ghi thành công trước khi mở lại traffic.

Phát biểu trên vẫn cần các thông số cụ thể về tải, tỉ lệ lỗi, quyền giao dịch và phạm vi dữ liệu. Nhưng nó kiểm thử được hơn câu “RTO của database là 15 phút” vì xác định **sự cố, chức năng và thời điểm đánh giá**.

**Không công bố một con số RTO tuyệt đối cho mọi tình huống** nếu kiến trúc chưa thể đáp ứng: mất một node và mất toàn bộ region có thể cần phương án khác nhau.

## 3. Đồng hồ RTO bắt đầu và kết thúc lúc nào?

Hình dung dòng thời gian:

~~~text
t0        t1           t2           t3           t4           t5
|---------|------------|------------|------------|------------|
Sự cố     Giám sát     Xác định     DB có thể    API chạy     Nghiệp vụ được
bắt đầu   phát hiện    phương án    kết nối      trở lại     xác minh, traffic
                                                          hoạt động an toàn

                 <----------- thời gian gián đoạn ----------->
RTO mục tiêu được so với khoảng t5 - t0 theo định nghĩa đã thống nhất.
~~~

Mốc bắt đầu cần nêu rõ, ví dụ **lúc chức năng quan trọng bắt đầu không đáp ứng SLO**, không tự động thay bằng lúc kỹ sư nhận được cảnh báo. Nếu hệ thống hỏng từ 10:00 nhưng alert đến 10:12, **12 phút phát hiện trễ vẫn là thời gian người dùng bị ảnh hưởng**.

Mốc kết thúc không nên chỉ là:

- PostgreSQL process đã lên.
- Port **5432** chấp nhận TCP.
- Một câu **SELECT 1** chạy được.
- Load balancer đã chuyển IP hoặc pod Java trạng thái **Ready**.
- Một backup được giải nén xong.

Với dịch vụ đặt hàng, điều kiện kết thúc phù hợp hơn là **đúng endpoint hoạt động, có thể thực hiện thao tác nghiệp vụ được phép, dữ liệu cần thiết đúng, tỷ lệ lỗi và độ trễ đáp ứng ngưỡng tạm khôi phục, hệ thống nhận traffic thực tế**. Cần phân biệt **phục hồi chức năng tối thiểu được chấp nhận** với **phục hồi toàn bộ năng lực và xử lý hết backlog**; nếu backlog là điều kiện bắt buộc của nghiệp vụ thì phải tính nó vào RTO.

Một công thức tư duy:

~~~text
RTO thực đo = thời điểm đạt tiêu chí khôi phục - thời điểm bắt đầu gián đoạn
Đạt mục tiêu nếu RTO thực đo <= RTO mục tiêu trong kịch bản đã thỏa thuận
~~~

Đừng lẫn **mốc công bố phục hồi** với **mốc thực sự phục hồi**. Ghi cả hai trong incident timeline để phân biệt thời gian kỹ thuật và thời gian truyền thông.

## 4. RTO khác RPO, MTTR, SLA và availability thế nào?

| Thuật ngữ | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **RTO – Recovery Time Objective** | Dịch vụ cần trở lại trong bao lâu sau sự cố? | Mục tiêu trong 30 phút |
| **RPO – Recovery Point Objective** | Có thể chấp nhận mất tối đa bao nhiêu dữ liệu tính theo thời gian? | Mục tiêu dữ liệu không cũ quá 5 phút |
| **Thời gian khôi phục thực đo** | Sự cố hoặc diễn tập này thực sự mất bao lâu? | 42 phút |
| **MTTD – Mean Time to Detect** | Trung bình mất bao lâu để phát hiện sự cố? | Theo dữ liệu quan sát |
| **MTTR – Mean Time to Restore/Repair** | Trung bình mất bao lâu để phục hồi hoặc sửa chữa? | Cần làm rõ cách đơn vị định nghĩa MTTR |
| **SLO** | Mục tiêu mức dịch vụ theo một khoảng đo | 99,9% request hợp lệ đáp ứng tiêu chí |
| **SLA** | Cam kết chính thức với hệ quả/điều khoản liên quan | Mức dịch vụ và bồi hoàn đã thỏa thuận |
| **Availability** | Tỷ lệ thời gian hoặc request dịch vụ khả dụng theo định nghĩa | Một chỉ số thống kê, không thay cho runbook |

**RTO và RPO độc lập về mặt định nghĩa.** Có thể phục hồi nhanh nhưng mất vài phút dữ liệu, hoặc mất hàng giờ để khôi phục một trạng thái dữ liệu rất chính xác.

Ví dụ:

~~~text
Sự cố xảy ra lúc 10:00.
Backup/điểm khôi phục hợp lệ gần nhất ở 09:57.
Hệ thống phục hồi có kiểm chứng lúc 10:24.

Thời gian gián đoạn thực tế: 24 phút.
Khoảng dữ liệu có nguy cơ mất so với mốc 10:00: khoảng 3 phút.
~~~

Hai con số **24 phút** và **3 phút** trả lời hai câu hỏi khác nhau. Bài này tập trung vào **RTO**, nhưng bất kỳ phương án rút ngắn RTO nào cũng phải kiểm tra lại ảnh hưởng tới RPO và tính đúng dữ liệu.

**Availability 99,9% không tự suy ra một RTO duy nhất.** Cùng một tỷ lệ availability có thể là rất nhiều gián đoạn ngắn hoặc một gián đoạn dài. RTO nhắm vào **thời gian phục hồi của một lớp sự cố cụ thể**.

## 5. Phải có tiêu chí nghiệp vụ trước khi chọn công nghệ

Một nhóm kỹ thuật không nên tự đặt RTO bằng cách hỏi “restore của chúng ta hiện mất bao lâu?” rồi lấy con số đó làm mục tiêu. Trước hết cần phân tích **Business Impact Analysis (BIA)**:

1. Chức năng nào ngừng hoạt động sẽ ảnh hưởng doanh thu, an toàn, pháp lý hoặc trải nghiệm khách hàng?
2. Người dùng có thể chấp nhận chế độ **read-only** trong khi đường ghi chưa phục hồi không?
3. Hệ thống có phụ thuộc thanh toán, xác thực, broker, cache, object storage hoặc bên thứ ba không?
4. Những giao dịch nào phải được đối soát trước khi mở lại để không xử lý trùng?
5. Mất dịch vụ 5, 30, 60 hoặc 240 phút tạo tác động gì?
6. Nhóm có khả năng trực 24/7, quyền truy cập, bản sao và ngân sách phù hợp không?

Một bảng ưu tiên minh họa:

| Chức năng | RTO mục tiêu giả định | Điều kiện phục hồi tối thiểu |
| --- | --- | --- |
| Xác thực và kiểm tra quyền | 15 phút | Đăng nhập/xác thực và phân quyền không chấp nhận dữ liệu nguy hiểm bị cũ |
| Tạo và xem trạng thái đơn | 30 phút | Ghi được giao dịch mới, không tạo trùng, dữ liệu đúng phiên |
| Tra cứu catalog công khai | 60 phút | Có thể phục vụ từ bản sao/cache theo chính sách freshness |
| Đồng bộ báo cáo phân tích | 4 giờ | Pipeline tiếp tục, backlog được quản lý |
| Xuất dữ liệu định kỳ | 24 giờ | Job có thể chạy lại và kết quả đủ chính xác |

Đây **không phải SLO được áp dụng chung**; các con số chỉ minh họa cách phân tầng yêu cầu. RTO thực phải được chủ sở hữu nghiệp vụ, an toàn thông tin và vận hành cùng xác nhận.

## 6. Phân loại sự cố vì mỗi loại có đường phục hồi khác nhau

| Tình huống | Phương án thường được cân nhắc | Rủi ro đặc thù |
| --- | --- | --- |
| Một tiến trình DB chết, dữ liệu còn nguyên | Restart hoặc failover tùy nguyên nhân | Khởi động lại không giải quyết storage/network hỏng |
| Mất một node hoặc availability zone | Promote standby đủ điều kiện | Chọn nhầm standby, split-brain, RPO |
| Mất cả region | Khôi phục vùng khác hoặc DR site | Kết nối mạng, secret, DNS, năng lực vùng dự phòng |
| Xóa nhầm bảng hoặc dữ liệu | Backup + WAL/PITR tới thời điểm trước lỗi | Replication có thể đã sao chép lệnh DELETE |
| Migration schema lỗi | Roll-forward, restore/đối soát hoặc kế hoạch phục hồi cụ thể | Binary cũ không còn tương thích dữ liệu mới |
| Backup bị hỏng hoặc mã hóa thiếu key | Chuyển nguồn backup đã được kiểm chứng | Có backup nhưng không thể restore |
| Sự cố credential/IAM/TLS | Phục hồi quyền/secret/cert | DB còn hoạt động nhưng Java không kết nối được |
| Cache/broker/projection bị lỗi | Khôi phục phụ thuộc hoặc chế độ degrade an toàn | DB lên nhưng use case vẫn không chạy |
| Ransomware/hành vi xóa ác ý | Cách ly, phục hồi từ backup độc lập/immutable | Không được đưa máy nhiễm trở lại hoặc tin bản sao đã bị ảnh hưởng |

**Standby không tự thay thế backup.** Một lệnh xóa hợp lệ về cú pháp vẫn được replay tới standby. Đối với sự cố logic hoặc phá dữ liệu, thường cần bản khôi phục ở một thời điểm khác; đối với mất node, HA có thể nhanh hơn việc chép hàng terabyte backup.

## 7. Đường phục hồi phải được viết thành chuỗi bước có thời gian

Một ngân sách RTO có thể phân tách:

~~~text
Tổng thời gian =
  phát hiện gián đoạn
+ xác minh và chọn chiến lược
+ cấp/đánh thức tài nguyên dự phòng
+ chuyển vai trò hoặc khôi phục dữ liệu
+ phục hồi đường kết nối / định tuyến
+ kiểm tra dữ liệu và chức năng nghiệp vụ
+ mở traffic đến mức dịch vụ chấp nhận
~~~

Ví dụ với mục tiêu **RTO 30 phút**:

| Bước | Ngân sách tối đa giả định |
| --- | ---: |
| Phát hiện và cảnh báo | 3 phút |
| Xác định phạm vi/chọn runbook | 5 phút |
| Failover hoặc khôi phục DB | 10 phút |
| Cập nhật route, pool và kết nối ứng dụng | 4 phút |
| Xác minh dữ liệu và nghiệp vụ | 5 phút |
| Mở traffic/giám sát ổn định | 3 phút |
| **Tổng** | **30 phút** |

Đây là **ngân sách phân bổ**, không phải số đo đã đạt. Nếu bước failover thực tế đã mất 25 phút, các bước còn lại không biến mất. Cần đo thời gian ở **p95/p99 hoặc các kịch bản xấu hợp lý**, không chỉ lấy một lần chạy nhanh trong môi trường thử nhỏ.

Đừng quên sự cố có thể xuất hiện khi **không có người trực**, lúc backup đang chạy, vào kỳ cao điểm hoặc khi một thành phần dự phòng khác cũng đã suy yếu. Phương án chỉ đạt RTO khi mọi thứ bình thường chưa phải phương án đáng tin cậy.

## 8. Nút thắt vật lý: dung lượng restore và băng thông

Nếu dữ liệu phải được tải lại, thời gian sao chép tối thiểu có thể ước tính:

~~~text
Thời gian truyền dữ liệu lý tưởng
    ≈ dung lượng cần đọc / tốc độ hữu dụng

Ví dụ:
  600 GiB backup / 200 MiB/s ≈ 51,2 phút
~~~

Đây chỉ là **cận dưới lý tưởng cho phần đọc/truyền tương ứng** khi tốc độ hữu dụng giữ nguyên. Trong thực tế còn có giải mã, giải nén, kiểm tra checksum, ghi ổ đĩa, chạy WAL replay, tạo instance, xây lại tài nguyên, truy vấn kiểm thử và chuyển traffic. Vì vậy, một kế hoạch **RTO 15 phút chỉ dựa vào tải 600 GiB backup ở tốc độ 200 MiB/s** không khả thi nếu không có phương án khác như standby nóng hoặc snapshot có khả năng phục hồi nhanh hơn đã kiểm chứng.

Các yếu tố quyết định thời gian:

- **Kích thước dữ liệu thực phải restore**, không chỉ size compressed trên object storage.
- **Throughput đọc backup và ghi disk** khi chịu tải đồng thời.
- **Băng thông liên region**, rate limits và độ trễ của nguồn backup.
- **Số WAL segment phải replay** từ base backup đến recovery target.
- **CPU giải nén/giải mã** và khả năng I/O của hệ lưu trữ đích.
- **Số lượng file, metadata, index và kiểm tra dữ liệu**.
- **Cơ chế khởi động database**, nhu cầu replay, warmup cache và recovery checks.

Hãy đo riêng **download**, **restore**, **WAL replay**, **DB ready**, **application ready**. Chỉ nhìn kích thước backup hoặc tên công cụ không đủ dự đoán RTO.

## 9. So sánh những chiến lược giảm RTO

| Chiến lược | Khả năng phục hồi điển hình | Đánh đổi chính |
| --- | --- | --- |
| **Cold restore từ backup** | Phải cấp tài nguyên, tải và phục hồi dữ liệu | Chi phí duy trì thấp hơn; RTO có thể dài |
| **Warm standby** | Có hạ tầng/DB đã chuẩn bị một phần | Chi phí sẵn sàng; phải xác minh dữ liệu và thao tác promote |
| **Hot standby/streaming replica** | Đã nhận WAL, có thể tiếp quản nhanh hơn restore toàn bộ | Lag, chọn nút, điều phối failover, split-brain |
| **Failover tự động có fencing** | Rút ngắn phát hiện/ra quyết định/chuyển hướng | Phức tạp, nguy cơ failover sai, kiểm tra rollback |
| **Snapshot storage** | Có thể giảm thời gian tạo volume | Độ bền/nhất quán snapshot, vùng lưu, WAL và mount/init vẫn cần |
| **PITR từ backup + WAL** | Khôi phục đến thời điểm mong muốn | Thường chậm hơn failover nếu phải dựng DB và replay nhiều WAL |
| **Active-active hoặc multi-region architecture** | Có thể giảm thời gian gián đoạn cho một số sự cố | Conflict, consistency, vận hành và chi phí lớn hơn |

Mọi chiến lược phải được đánh giá **theo kịch bản**. Hot standby giúp khi primary hỏng, nhưng không phải đáp án cho việc toàn bộ dữ liệu đã bị mã độc thay đổi và replication phát tán thay đổi đó. PITR có thể cứu dữ liệu logic nhưng khó đáp ứng RTO rất ngắn nếu khối lượng restore lớn.

## 10. PostgreSQL: backup và WAL liên hệ thế nào tới RTO?

PostgreSQL dùng **Write-Ahead Log (WAL)** để phục hồi giao dịch và hỗ trợ nhiều cơ chế backup/replication. Để phục hồi tới một thời điểm bằng PITR, thường cần:

1. **Base backup** hợp lệ, có trạng thái nhất quán theo cơ chế hỗ trợ.
2. **Chuỗi WAL cần thiết**, liên tục từ vị trí backup tới recovery target.
3. **Dữ liệu cấu hình và thông tin khôi phục** tương thích phiên bản PostgreSQL.
4. **Hạ tầng đích** đủ tài nguyên CPU/RAM/storage/network.
5. **Quy trình start recovery, kiểm tra, chuyển hướng ứng dụng và đối soát**.

~~~text
Base backup lúc 01:00
         |
         v
WAL 01:00 ---- WAL 01:30 ---- WAL 02:00 ---- WAL 02:15
                                              |
                                              v
                             Recovery target trước sự kiện xóa nhầm
~~~

Về RTO, số WAL phải phát lại và tốc độ replay là những yếu tố quan trọng. Một base backup rất cũ có thể khiến thời gian PITR dài hơn ngay cả khi backup file nhỏ và tải về nhanh.

**WAL archiving không tự là một bản backup hoàn chỉnh**: chỉ có WAL mà không có base backup phù hợp không đủ để tái tạo toàn bộ cluster theo cách PITR thông thường. Ngược lại, chỉ có base backup mà thiếu WAL cần thiết có thể không khôi phục được tới thời điểm mục tiêu.

## 11. Chọn điểm khôi phục khác với chọn thời điểm hoàn tất

Hai mốc cần phân biệt:

~~~text
T_event      Sự cố xóa nhầm bắt đầu
T_target     Thời điểm dữ liệu cần phục hồi (thường trước T_event)
T_service    Thời điểm dịch vụ phục hồi và kiểm chứng xong

RPO liên quan đến T_target và dữ liệu bị mất/không khôi phục.
RTO liên quan đến T_service - thời điểm dịch vụ bắt đầu gián đoạn.
~~~

Ví dụ nhân viên chạy nhầm câu DELETE lúc 10:00. Nhóm khôi phục một bản sao tại **09:59:59** rồi kiểm tra và mở lại API lúc **10:45**. RTO có thể là 45 phút nếu dịch vụ gián đoạn từ 10:00; nhưng các giao dịch hợp lệ được ghi sau 09:59:59 có thể cần **đối soát hoặc phát lại** trước khi chấp nhận trạng thái cuối cùng.

Không được coi việc restore tới một thời điểm sớm là hoàn tất nghiệp vụ nếu nó vô tình **xóa những thay đổi hợp lệ khác**. Một quy trình an toàn thường restore vào **môi trường cách ly** trước, trích xuất dữ liệu cần cứu hoặc xây phương án reconciliation thay vì ghi đè production ngay.

## 12. Ví dụ phân biệt failover và restore sau xóa nhầm

### 12.1. Mất primary, standby vẫn còn

~~~text
Primary A chết -> standby B có WAL hợp lệ
    |
    v
Fencing/leader decision
    |
    v
Promote B
    |
    v
Ứng dụng chuyển connection tới B
    |
    v
Kiểm tra thao tác đọc/ghi, dữ liệu, idempotency
    |
    v
Mở traffic
~~~

Thời gian phụ thuộc phát hiện, cơ chế HA, tình trạng WAL của B, cấp quyền ghi, mạng và Java pool. **Promote hoàn tất không tự chứng minh toàn API đã phục hồi**.

### 12.2. Xóa nhầm và dữ liệu đã replicate

~~~text
DELETE nhầm -> WAL được replicate tới B
    |
    v
Standby B cũng thiếu dữ liệu
    |
    v
Chọn backup + WAL trước lúc DELETE
    |
    v
Restore vào môi trường cách ly
    |
    v
Đối soát những ghi hợp lệ sau mốc restore
    |
    v
Khôi phục dữ liệu nghiệp vụ và kiểm thử
    |
    v
Mở lại chức năng
~~~

Với sự cố này, failover trực tiếp từ A sang B **không giải quyết lỗi logic**. RTO cần bao gồm **thời gian xác định recovery target, phục hồi dữ liệu, đối soát và xác nhận nghiệp vụ**, vốn có thể lâu hơn đáng kể so với sự cố mất một node.

## 13. PostgreSQL: các kiểm tra hữu ích trong diễn tập

Những truy vấn sau chỉ **quan sát trạng thái**, không thay thế kiểm tra toàn vẹn nghiệp vụ.

Trên một node PostgreSQL:

~~~sql
SELECT pg_is_in_recovery() AS is_standby,
       current_setting('server_version') AS pg_version,
       now() AS observed_at;
~~~

Trên primary (cần quyền quan sát phù hợp):

~~~sql
SELECT application_name,
       state,
       sync_state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn
FROM pg_stat_replication;
~~~

Trên physical standby:

~~~sql
SELECT pg_is_in_recovery() AS standby_mode,
       pg_last_wal_receive_lsn() AS received_lsn,
       pg_last_wal_replay_lsn() AS replayed_lsn,
       pg_last_xact_replay_timestamp() AS replay_timestamp;
~~~

Các mốc **sent, write, flush, replay** khác nhau. Với một standby đang chậm, **đã nhận WAL không đồng nghĩa đã replay để câu SELECT nhìn thấy dữ liệu**. Giá trị **pg_last_xact_replay_timestamp()** có thể đứng yên khi không có transaction mới; lấy thời gian hiện tại trừ mốc này **không tự chứng minh replication lag**.

Khi diễn tập, cần lưu **LSN, timeline/nguồn dữ liệu, thời điểm sự cố và transaction nghiệp vụ cuối được xác nhận**. Không so sánh mù quáng LSN của các cluster/timeline không cùng lịch sử khi kiểm chứng sau failover.

## 14. Xác minh backup trước khi đưa vào kế hoạch RTO

**Có backup** và **restore thành công** là hai khẳng định khác nhau. Một bản sao có thể không dùng được vì:

- File thiếu hoặc không đúng chuỗi snapshot/WAL.
- Lỗi checksum, hỏng object hoặc thiếu metadata.
- Backup đã được mã hóa nhưng không còn khóa giải mã.
- Quyền đọc bucket/volume bị thu hồi khi xảy ra sự cố IAM.
- Phiên bản server/extension không tương thích với môi trường đích.
- Dung lượng ổ đĩa đích không đủ.
- Hệ thống lưu backup ở cùng vùng lỗi với production.
- Script restore phụ thuộc đường dẫn, user hoặc secret đã thay đổi.

Ví dụ những lệnh **minh họa** trên máy diễn tập có PostgreSQL cùng phiên bản phù hợp:

~~~text
# Tạo một base backup phục vụ diễn tập; không tự thay thế chính sách archive:
pg_basebackup -h db-primary.example -U backup_user -D /backup/test-base -Fp -Xs -P

# Với bản backup có manifest hợp lệ, kiểm tra cấu trúc/manifest:
pg_verifybackup /backup/test-base
~~~

Các lệnh trên **không thực hiện restore hoàn chỉnh**, không cấu hình PITR và không bảo đảm backup đang đáp ứng RTO. Cần quyền, kết nối, đường dẫn trống, manifest, WAL và cấu hình backup thích hợp. Không chạy lệnh với đường dẫn production hoặc thay thế dữ liệu đang phục vụ.

**Đo restore thử từ đầu đến cuối** mới cho bằng chứng về RTO: từ lúc phát hiện sự cố giả lập đến lúc bản sao được khôi phục và thao tác nghiệp vụ đạt tiêu chí.

## 15. PITR: lộ trình khái niệm và giới hạn thời gian

Với PostgreSQL phiên bản hiện đại, một restore tới thời điểm cụ thể thường gồm:

1. Chọn bản base backup **đã được kiểm chứng** và recovery target.
2. Cấp vùng lưu trữ/instance đích **cách ly**, không ghi đè cluster gốc.
3. Đưa dữ liệu backup về data directory theo tài liệu của công cụ backup.
4. Cấu hình **restore_command** để lấy các WAL cần thiết từ nguồn lưu đã xác thực.
5. Cấu hình **recovery_target_time** hoặc tiêu chí target được hỗ trợ.
6. Tạo **recovery.signal** trong data directory theo cơ chế PostgreSQL hiện hành.
7. Khởi động PostgreSQL ở môi trường restore, theo dõi replay và dừng ở target.
8. Xác minh dữ liệu, thông tin phân quyền, ràng buộc, extension và tương thích application.
9. Quyết định cách trích xuất/hợp nhất dữ liệu hoặc chuyển lưu lượng sang môi trường mới.

Một vài dòng cấu hình **minh họa cú pháp**, không phải bộ cấu hình an toàn hoặc đầy đủ:

~~~conf
# Chỉ minh họa ở MÔI TRƯỜNG RESTORE cách ly:
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2026-11-20 09:59:59+07'
recovery_target_action = 'pause'
~~~

Thời điểm trong ví dụ chỉ là dữ liệu giả định, **không phải mốc sự cố thực tế**. Đường dẫn archive phải được kiểm tra, shell command phải phù hợp hệ điều hành/quyền, WAL phải liên tục, target phải xác định rõ timezone. **Pause** giúp đánh giá kết quả trong diễn tập nhưng cần runbook cho bước tiếp theo; không vô tình cho ứng dụng ghi vào instance chưa hoàn tất phục hồi.

Không thực hiện restore production dựa trên vài dòng cấu hình này. Công cụ backup, version PostgreSQL, physical layout, encryption, quyền file và cách promote đều có quy trình riêng cần được lập tài liệu và diễn tập.

## 16. High availability rút ngắn RTO nhưng không xóa mọi sự cố

**HA** thường giải quyết một số lỗi bằng bản sao đã hoạt động và cơ chế chuyển vai trò. Với PostgreSQL, các điểm bắt buộc cần thiết kế:

- **Nhận diện primary đã thực sự mất khả năng phục vụ** hoặc cần cách ly.
- **Fencing:** ngăn primary cũ tiếp tục nhận ghi sau khi primary mới được công nhận.
- **Leader election / quorum** theo công cụ điều phối phù hợp, tránh split-brain.
- **Chọn standby đủ mới**, hiểu asynchronous/synchronous replication và RPO.
- **Promote đúng node**, cấp quyền ghi và đảm bảo ứng dụng không ghi vào standby read-only.
- **Chuyển hướng DNS/proxy/service discovery**, xử lý connection pool giữ socket cũ.
- **Readiness ở tầng ứng dụng**, không chỉ PostgreSQL listener.
- **Rejoin primary cũ an toàn** khi hệ thống ổn định, tránh đưa dữ liệu phân kỳ trở lại.

Một hệ thống failover tự động có thể giảm thời gian phát hiện và thao tác thủ công. Tuy nhiên, một cấu hình sai có thể **failover quá sớm**, chọn bản sao thiếu dữ liệu hoặc làm hai node cùng nhận ghi. RTO ngắn chỉ có ý nghĩa nếu phục hồi **đúng và an toàn**.

## 17. Mức đồng bộ replication ảnh hưởng RTO và RPO khác nhau

Trong PostgreSQL physical streaming replication, hai trục đánh đổi:

| Cấu hình/chiến lược | Tác động chính |
| --- | --- |
| **Asynchronous standby** | Primary thường không đợi standby khi commit; failover có thể nhanh nhưng standby có thể thiếu commit đã xác nhận |
| **Synchronous commit đợi remote flush** | Giảm rủi ro mất commit đã xác nhận trên standby đủ điều kiện; commit có thể chờ khi standby yếu |
| **Synchronous commit đợi remote apply** | Phù hợp hơn cho đọc từ standby sau commit trên nút đã xác nhận; có thể tăng commit latency |
| **Nhiều standby/quorum** | Cải thiện lựa chọn khi một node lỗi nhưng tăng chi phí và độ phức tạp |
| **Standby cùng region/AZ** | Có thể giảm độ trễ và thời gian failover cục bộ; vẫn cần xét lỗi vùng chung |
| **Standby khác region** | Có thể hỗ trợ DR theo vùng; network/replication và chuyển routing có chi phí riêng |

**Bật synchronous replication không tự động đạt RTO thấp**. Nếu cấu hình yêu cầu standby đồng bộ nhưng standby mất kết nối, primary có thể phải chờ COMMIT, khiến availability của đường ghi giảm. Ngược lại, failover sang asynchronous standby có thể nhanh nhưng cần đánh giá RPO.

Vì thế, chọn kiến trúc dựa trên **cặp mục tiêu RTO + RPO** cùng mô hình lỗi, không tối ưu duy nhất một con số.

## 18. Khôi phục database chưa phải khôi phục ứng dụng Java

Ngay sau khi primary mới sẵn sàng, ứng dụng Java vẫn có thể gặp:

- Pool giữ connection tới IP/instance cũ.
- DNS cache hoặc proxy chưa cập nhật backend.
- Credential, chứng chỉ TLS hoặc CA khác giữa vùng.
- Database role mới đang ở **read-only** hoặc chưa có grant cần thiết.
- Schema/version của DB không tương thích binary đang chạy.
- Transaction bị đứt giữa chừng; kết quả COMMIT trước sự cố không chắc chắn.
- Cache trả dữ liệu cũ; read replica chưa replay; projection/broker còn backlog.
- Queue consumer hoặc scheduler chạy lại tạo tác dụng trùng.
- Không đủ connection/CPU để nhận ngay tải đầy đủ sau failover.

Một sơ đồ end-to-end:

~~~text
DB node healthy
      |
      v
Primary writable + dữ liệu được xác minh
      |
      v
Proxy/DNS/service discovery chuyển sang primary mới
      |
      v
Java DataSource/connection pool mượn kết nối mới
      |
      v
Giao dịch nghiệp vụ tối thiểu thực hiện an toàn
      |
      v
Đường đọc/cache/consumer đáp ứng điều kiện dữ liệu
      |
      v
Mở traffic + kiểm tra latency/error-rate + công bố phục hồi
~~~

Đối với RTO của dịch vụ Java, cần đo tới **bước cuối theo tiêu chí đã định**, không dừng ở lệnh promote.

## 19. Java/JDBC: kiểm tra tín hiệu kết nối sau sự cố

Ví dụ tối giản kiểm tra DataSource có kết nối được tới một node PostgreSQL và node có ở recovery mode không:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DatabaseReadinessProbe {
    private final DataSource dataSource;

    public DatabaseReadinessProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record Signal(
            boolean reachable, boolean standby,
            boolean transactionReadOnly, String reason) {}

    public Signal inspect() {
        String sql = """
            SELECT pg_is_in_recovery(),
                   current_setting('transaction_read_only')
            """;
        try (Connection connection = dataSource.getConnection();
             PreparedStatement st = connection.prepareStatement(sql)) {
            st.setQueryTimeout(2);
            try (ResultSet rs = st.executeQuery()) {
                if (!rs.next()) {
                    return new Signal(false, false, true, "no row");
                }
                boolean standby = rs.getBoolean(1);
                boolean readOnly = "on".equals(rs.getString(2));
                return new Signal(true, standby, readOnly, "ok");
            }
        } catch (SQLException ex) {
            // Phân loại SQLSTATE cho metrics; không log credential.
            return new Signal(false, false, true, "sql failure");
        }
    }
}
~~~

Đây chỉ là **tín hiệu chẩn đoán**, không phải bảo đảm cuối cùng đường ghi sẵn sàng:

1. **pg_is_in_recovery() = false** cho biết node không ở chế độ recovery tại thời điểm kiểm tra; nó **không chứng minh** role hiện tại có quyền INSERT hoặc mọi tài nguyên cần thiết đã sẵn sàng.
2. **transaction_read_only = off** cũng không bảo đảm ứng dụng có grant, schema hợp lệ hay đủ dung lượng ghi.
3. Connection có thể lỗi **ngay sau health check**; nghiệp vụ vẫn cần xử lý exception.
4. Một kiểm tra readiness gọi DB quá thường xuyên trên mọi request có thể tạo tải; hãy thiết kế tần suất, timeout, phân biệt **liveness** với **readiness**.
5. Với hành vi quan trọng, cần synthetic transaction được kiểm soát trong môi trường/không gian dữ liệu phù hợp và quan sát kết quả nghiệp vụ thực.

**Không chạy thử ghi vào dữ liệu production của người dùng chỉ để làm health check.** Nếu cần kiểm tra đường ghi end-to-end, dùng bảng/tài nguyên kiểm thử chuyên biệt, idempotency và cơ chế cleanup được phê duyệt.

## 20. Spring và connection pool trong thời gian failover

Ứng dụng Spring thường nhận DataSource được pool hóa, ví dụ qua HikariCP. Pool không tự biết **primary nào đang được leader election công nhận**; nó làm việc theo URL, driver, mạng và health check của connection.

Trong một quá trình phục hồi, cần kiểm tra:

- **JDBC URL/endpoint:** trỏ tới service/proxy writer hoặc primary mới theo thiết kế.
- **Driver connect timeout:** tránh thread treo quá lâu khi IP cũ không phản hồi.
- **Pool acquisition timeout:** giới hạn đợi connection; không nhầm với query timeout.
- **Connection validation và loại bỏ connection hỏng:** driver/pool có phát hiện socket tới primary cũ không?
- **DNS/endpoint resolution:** nếu dùng DNS, TTL và cache ở các tầng có phù hợp thời gian chuyển hướng không?
- **Pool size khi phục hồi:** không để mọi instance tạo bão kết nối tới primary mới cùng lúc.
- **Transaction timeout và retry:** transaction cũ phải kết thúc/lỗi rõ ràng, không cố dùng connection đã hỏng.
- **Read/write routing:** sau failover không được gửi INSERT tới replica read-only hoặc GET cần read-your-writes tới replica chưa bắt kịp.

Ví dụ tham số **minh họa** trong Spring Boot:

~~~properties
# Các giá trị chỉ dùng làm ví dụ; cần đánh giá theo SLO thực.
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.validation-timeout=1000
~~~

**Hikari connection-timeout** có đơn vị mili giây và giới hạn thời gian chờ mượn connection từ pool; nó **không** tự giới hạn toàn bộ failover hoặc câu SQL đang thực thi. Các cấu hình **connectTimeout/socketTimeout** của pgJDBC có ngữ nghĩa và đơn vị khác; cần xem phiên bản driver, URL và chính sách mạng hiện hành.

Với retry sau failover, chỉ tự động thử lại **lỗi tạm thời và thao tác an toàn để lặp**. Sau kết nối đứt đúng lúc COMMIT, server có thể đã commit; thao tác tạo đơn/chuyển tiền cần **request ID ổn định, unique constraint và cơ chế đối soát** trước khi retry.

## 21. Dữ liệu sau failover: xác nhận đúng, không chỉ xác nhận có

Một PostgreSQL primary mới có thể khởi động và trả SELECT nhưng vẫn thiếu một số transaction của primary cũ nếu replication trước đó là bất đồng bộ. Sau phục hồi, cần xác định:

- **Transaction cuối cùng đã được ứng dụng xác nhận** ở đâu?
- Primary mới đã replay đủ những WAL nào?
- Có giao dịch nào đã nhận phản hồi COMMIT nhưng không tồn tại ở primary mới không?
- Có xử lý giao dịch nào nhận timeout nhưng DB đã commit không?
- Các **sequence/ID, idempotency records, outbox events, trạng thái thanh toán** có nhất quán không?
- Cache, search index và consumer có đang đọc/lưu từ lịch sử dữ liệu cũ không?

Ví dụ với API tạo đơn:

~~~text
Client gửi request_id = R123
       |
       v
Primary cũ có thể đã COMMIT
       |
       v
Failover, kết quả phản hồi không rõ
       |
       v
Kiểm tra trên nguồn đã được công nhận:
  - Có bản ghi R123: trả kết quả đã lưu
  - Chưa có: cần xem RPO/failover và quy tắc retry
  - Chưa kết luận được: giữ trạng thái chờ đối soát
~~~

RTO không nên được “đạt” bằng cách mở ghi ngay lên một primary mới **chưa được kiểm chứng độ đúng dữ liệu** nếu điều đó gây thêm mất mát hoặc trùng lặp nghiêm trọng. Trường hợp không thể đáp ứng cả mục tiêu thời gian lẫn dữ liệu, cần **cơ chế ra quyết định, chuyển chế độ read-only/partial và truyền thông sự cố** theo ưu tiên đã thỏa thuận.

## 22. Phụ thuộc ngoài database cũng nằm trong đường phục hồi

Giả sử PostgreSQL đã khôi phục lúc 10:10, nhưng:

- Service xác thực chưa khôi phục khóa ký token.
- Broker chưa khởi động nên nghiệp vụ không phát được outbox event bắt buộc.
- Object storage chứa hóa đơn đang lỗi quyền.
- KMS không trả khóa giải mã dữ liệu.
- Payment provider còn từ chối giao dịch.
- Search index chưa đủ dữ liệu để tìm đơn cũ.

Nếu những thành phần đó là **điều kiện thiết yếu của use case**, người dùng chưa thể xem dịch vụ là khôi phục. Do đó:

~~~text
RTO dịch vụ = thời gian phục hồi của đường phụ thuộc thiết yếu
             + các bước kiểm chứng/mở traffic theo kiến trúc
~~~

Không nhất thiết cộng mọi thời gian đơn lẻ: một số bước có thể chạy **song song**, một số bước phải **nối tiếp**. Hãy lập **critical path**: chuỗi phụ thuộc có tổng thời gian dài nhất quyết định khi nào chức năng có thể trở lại.

Các nhóm vận hành nên biết dịch vụ nào **có thể degrade**: ví dụ trang catalog đọc được khi báo cáo phân tích chưa chạy. Nhưng **không** tắt kiểm tra quyền, ràng buộc giao dịch hoặc bảo vệ thanh toán chỉ để đạt thời gian khôi phục đẹp hơn.

## 23. Runbook RTO mẫu cho một sự cố primary PostgreSQL

Runbook là tài liệu có thể thực thi bởi người trực, không chỉ là mô tả kiến trúc. Một mẫu:

~~~text
Tên: PostgreSQL primary không phục vụ ghi
Mức độ: ảnh hưởng đường tạo đơn
RTO mục tiêu: 30 phút (mất một node, standby còn hoạt động)
RPO mục tiêu: do bộ phận nghiệp vụ phê duyệt riêng

START:
  T0 = thời điểm chức năng tạo đơn không còn đáp ứng tiêu chí

0. Xác nhận cảnh báo, tạo incident ID, ghi timestamp
1. Xác định phạm vi lỗi và khả năng tồn tại split-brain
2. Kiểm tra standby, vị trí WAL, backup và điều kiện RPO
3. Quyết định failover theo cơ chế điều phối đã được phê duyệt
4. Fencing primary cũ trước khi cho primary mới nhận ghi
5. Promote/chuyển endpoint qua công cụ HA chính thức
6. Kiểm tra primary mới, grants, schema, trạng thái WAL
7. Làm mới đường kết nối ứng dụng và kiểm tra transaction
8. Chạy kiểm thử nghiệp vụ an toàn, kiểm tra idempotency
9. Mở traffic theo từng mức và quan sát lỗi/độ trễ

STOP:
  T1 = lúc tiêu chí nghiệp vụ tối thiểu được xác minh và phục vụ

RECORD:
  RTO thực đo = T1 - T0
  Dữ liệu có nguy cơ mất / RPO thực tế
  Các bước vượt ngân sách, nguyên nhân, điều chỉnh runbook
~~~

Với mỗi bước cần chỉ định **vai trò phụ trách, ngưỡng timeout, điều kiện quyết định, lệnh/console đã được kiểm chứng, phương án dừng và cách liên lạc**. Không khuyến nghị một script tự chọn standby và promote chỉ vì một lần ping thất bại.

### 23.1. Quyết định khi sắp vượt RTO

Runbook nên nêu **điểm chuyển hướng**. Ví dụ nếu sau 8 phút không có standby đủ điều kiện thì không tiếp tục chờ vô hạn một nhánh đã thất bại; chuyển sang quy trình backup/DR hoặc chế độ read-only theo chính sách đã được phê duyệt. Thời điểm chuyển phải tính đến **thời gian còn lại**, điều kiện RPO và nguy cơ sai dữ liệu.

Nếu RTO chắc chắn sẽ bị vượt, cần **báo sự cố trung thực và ghi nguyên nhân**, không bỏ qua bước xác minh hoặc thay đổi dữ liệu một cách nguy hiểm để tuyên bố khôi phục đúng hạn.

## 24. Diễn tập RTO: đo cả hệ thống trong điều kiện thực

**Diễn tập khôi phục** là cách kiểm chứng một RTO. Một lần thành công trong máy ảo nhỏ với 5 GB dữ liệu không chứng minh production 2 TB sẽ phục hồi trong cùng thời gian.

Nên có nhiều mức:

1. **Tabletop:** đi qua kịch bản và runbook, xác định người chịu trách nhiệm, quyền và những bước chưa rõ.
2. **Restore kỹ thuật:** lấy backup thực tế, phục hồi ở môi trường cách ly, kiểm tra tính hợp lệ và dữ liệu.
3. **Diễn tập HA/failover:** mô phỏng mất một node, chuyển primary, kiểm tra fencing và route.
4. **Diễn tập nhiều vùng:** kiểm tra mạng, credential, DNS/proxy, secret, KMS và capacity ở vùng dự phòng.
5. **Diễn tập logic/PITR:** khôi phục dữ liệu tới mốc trước xóa nhầm, đối soát những ghi hợp lệ.
6. **Diễn tập end-to-end:** synthetic user journey từ API Java tới DB, cache, broker và chức năng nghiệp vụ.

Đo từng mốc:

~~~text
incident_start_at
incident_detected_at
runbook_selected_at
restore_or_failover_started_at
database_usable_at
application_connected_at
business_validation_passed_at
traffic_restored_at
~~~

Giữ đồng hồ đồng bộ và timestamp có múi giờ rõ ràng; nếu phân tích bằng sự kiện từ nhiều máy, cần tính tới chênh lệch đồng hồ. Có thể dùng monotonic clock để đo duration bên trong một tiến trình, và nguồn thời gian chuẩn đã đồng bộ cho timeline xuyên hệ thống.

### 24.1. Tập dữ liệu thử cần sát thực tế

- Dung lượng data + index + WAL tương ứng production.
- Phân phối bảng lớn, dữ liệu nóng/lạnh và số lượng file.
- Số transaction đồng thời, backfill/import đang chạy.
- Tốc độ snapshot/object storage trong giờ cao điểm.
- Lượng WAL cần replay theo lịch backup thực tế.
- Cấu hình encryption/compression và tốc độ CPU.
- Số Java instances, connection pools và dependencies cần phục hồi.

Không thao tác phá dữ liệu trên production nếu không có quy trình diễn tập được phê duyệt. Ưu tiên môi trường cách ly và kiểm soát chặt những kịch bản fault injection.

## 25. Báo cáo RTO: đo theo phân phối, không chỉ lần tốt nhất

Ví dụ số liệu giả định cho cùng kịch bản mất một primary:

| Lần diễn tập | Phát hiện + quyết định | DB failover | Ứng dụng + kiểm chứng | Tổng |
| --- | ---: | ---: | ---: | ---: |
| A | 5 phút | 7 phút | 6 phút | 18 phút |
| B | 7 phút | 11 phút | 8 phút | 26 phút |
| C | 9 phút | 14 phút | 11 phút | 34 phút |

Nếu **RTO mục tiêu = 30 phút**, lần C **không đạt**, dù trung bình của ba lần còn dưới 30 phút. Đối với nghiệp vụ nhạy cảm, các lần diễn tập nên bao gồm kịch bản stress, lỗi kép đã xác định, thiếu người trực và hạ tầng đang chịu tải.

Một báo cáo đầy đủ nên ghi:

- **Kịch bản**, điều kiện và phạm vi sự cố được giả lập.
- **RTO mục tiêu**, tiêu chí start/stop và người phê duyệt.
- **RTO thực đo** cùng timeline theo từng bước.
- **RPO đạt được** và dữ liệu cần đối soát (nếu có).
- Các **bước thủ công**, công cụ, dependency và quyền đã cần.
- Lỗi do **DNS, pool, grants, schema, WAL, backup, KMS, cache**.
- Các phát hiện về **tính đúng dữ liệu** sau khôi phục.
- Hành động cải thiện, người chịu trách nhiệm và lịch kiểm chứng lại.

Không được thay thế một lần diễn tập thực bằng **ước tính từ tài liệu nhà cung cấp** hoặc số phút mà script tự thông báo. RTO được đo tới tiêu chí dịch vụ, không chỉ tốc độ của một công cụ.

## 26. Quan sát và cảnh báo phục vụ mục tiêu RTO

RTO thấp đòi hỏi **phát hiện sớm và có thông tin đủ để ra quyết định**. Các chỉ số cần quan sát:

| Thành phần | Tín hiệu | Mục đích |
| --- | --- | --- |
| API Java | Synthetic transaction, error rate, p95/p99 latency | Biết người dùng có thực sự hoàn thành use case |
| Connection pool | Active, idle, pending, acquisition failures | Phát hiện nghẽn pool hoặc route kết nối hỏng |
| PostgreSQL | Kết nối, transaction errors, pg_is_in_recovery | Nhận biết tình trạng DB và vai trò node |
| Replication | sent/write/flush/replay LSN, sync state | Xác định standby sẵn sàng và rủi ro dữ liệu |
| Backup | Thành công, tuổi backup, chuỗi WAL, verify failures | Tránh chỉ phát hiện backup hỏng khi cần restore |
| Storage | Dung lượng, I/O latency, WAL retention, object-store errors | Ước lượng và dự báo restore bottleneck |
| HA orchestration | Leader state, fencing state, failover events | Ngăn hai primary cùng nhận ghi |
| Security/IAM/KMS | Khả năng truy cập key/secret/cert | Phục hồi được backup đã mã hóa |
| Job/outbox/cache | Backlog, lag, stale-read violations | Đánh giá tính sẵn sàng nghiệp vụ sau DB |

Thiết lập cảnh báo cho **điều người dùng quan tâm** kết hợp với lỗi thành phần. DB server báo healthy nhưng API đặt hàng vẫn trả 503 là trường hợp cần cảnh báo.

### 26.1. Phải phân biệt detection timeout và query timeout

Một request đợi mượn connection 2 giây rồi thất bại không chứng minh database đã down; pool có thể bị cạn vì query chậm. Ngược lại, database khởi động được nhưng ứng dụng timeout vì DNS cache cũ. Các lớp timeout **pool, connect, socket, statement, transaction và HTTP** cần được phân loại riêng để nhóm vận hành chọn đúng nhánh runbook.

## 27. Bảo mật và tính sẵn sàng của dữ liệu backup

Một backup có thể tồn tại nhưng **không có ai được phép sử dụng nó đúng lúc sự cố**. Kiến trúc đáp ứng RTO cần xét:

- **Mã hóa ở nơi lưu và khi truyền**, khóa giải mã có bản sao/khả năng phục hồi theo chính sách.
- **IAM tối thiểu nhưng có break-glass access**, ghi audit và kiểm soát người phê duyệt.
- **Backup độc lập với miền lỗi production**, cân nhắc immutable/offline copies để chống sửa/xóa ác ý.
- **Chính sách retention và dữ liệu cá nhân** phù hợp yêu cầu pháp lý.
- **Kiểm chứng checksum/manifest**, dữ liệu backup đủ và WAL archive liên tục.
- **Bảo vệ secret khi diễn tập**: không đặt password trong command line lịch sử shell, file log hoặc tài liệu chia sẻ.
- **Tài khoản ứng dụng và migration tách biệt**, tránh phục hồi bằng tài khoản quá quyền rồi giữ nguyên quyền ấy khi mở traffic.
- **Khả năng quay về trạng thái an toàn khi backup chứa mã độc**, không đơn thuần restore rồi nối ngay vào mạng production.

Những kiểm soát này có thể tạo thêm bước phê duyệt/giải mã. Hãy **đưa chúng vào runbook và đo thời gian**, thay vì vô hiệu hóa bảo mật khi cần chạy nhanh.

## 28. RTO, chi phí và khả năng phục hồi phải được cân bằng

RTO càng thấp thường đòi hỏi nhiều thứ luôn sẵn sàng:

- Standby hoặc cụm dự phòng đủ năng lực.
- Nhân sự trực, quyền và runbook rõ ràng.
- Health checks, tự động chuyển hướng và synthetic verification.
- Backup kiểm tra định kỳ, network route và KMS dự phòng.
- Diễn tập thường xuyên, khả năng cập nhật binary/schema tương thích.
- Năng lực hấp thụ traffic khi một vùng hạ tầng không còn phục vụ.

| Phương án | Chi phí vận hành | Thường giúp gì cho RTO? | Giới hạn |
| --- | --- | --- | --- |
| Chỉ lưu backup định kỳ | Thấp hơn về hạ tầng nóng | Có dữ liệu để restore | Dựng lại dịch vụ có thể lâu |
| Standby đã tạo sẵn | Tăng chi phí tài nguyên | Bớt thời gian cấp máy/restore | Cần failover và kiểm chứng |
| HA tự động có kiểm soát | Đầu tư vận hành/tự động hóa | Giảm thời gian phát hiện/chuyển vai trò | Có nguy cơ lỗi điều phối |
| DR site khác region | Chi phí mạng, dữ liệu và năng lực | Bảo vệ trước một số lỗi vùng | Routing và consistency phức tạp |
| Active-active | Cao và phức tạp | Có thể giảm gián đoạn một số lớp sự cố | Conflict, split-brain, dữ liệu và quyền |

Trước khi đầu tư, hãy tìm **critical path** của RTO. Nếu 70% thời gian nằm ở bước “đợi người có quyền KMS phê duyệt”, tăng tốc restore disk chưa phải cải thiện quan trọng nhất. Nếu quá trình WAL replay mất một giờ, tự động hóa chuyển DNS một phút không đủ đáp ứng RTO 15 phút.

## 29. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng RTO như thời gian chạy một lệnh restore | Bỏ sót detection, ứng dụng, xác minh | Đo tới tiêu chí nghiệp vụ end-to-end |
| Chỉ đặt một RTO cho mọi sự cố | Mục tiêu không thể kiểm chứng hoặc không thực tế | Phân theo use case và failure scenario |
| Nhầm RTO với RPO | Hệ thống lên nhanh nhưng mất dữ liệu ngoài mức chấp nhận | Đặt và kiểm tra hai mục tiêu riêng |
| Nghĩ backup tồn tại nghĩa là khôi phục được | Backup thiếu WAL/key hoặc hỏng | Thử restore/verify định kỳ |
| Tin rằng replication thay backup | Lỗi DELETE/ransomware được nhân bản | Backup/PITR độc lập, cách ly khỏi miền lỗi |
| Tuyên bố phục hồi khi DB port mở | Java vẫn 500, kết nối cũ, nghiệp vụ lỗi | Synthetic business validation |
| Đặt RTO 15 phút nhưng cold restore cần 1 giờ | Cam kết vật lý không khả thi | Đổi kiến trúc hoặc thỏa thuận lại mục tiêu |
| Failover không fencing | Nguy cơ split-brain, dữ liệu phân kỳ | Leader coordination và fencing |
| Chọn standby nhanh nhất nhưng không kiểm tra WAL | Có thể mất commit đã xác nhận | Quy tắc chọn bản đủ mới và đối soát |
| Quên connection pool, DNS và credential | DB đã lên nhưng app vẫn down | Kiểm tra route/pool/secret end-to-end |
| Bỏ kiểm tra dữ liệu để kịp mục tiêu | Phục hồi nhanh nhưng dữ liệu sai | Gates về tính đúng và chế độ degrade an toàn |
| Tự retry thanh toán/tạo đơn sau commit timeout | Giao dịch trùng | Idempotency key, unique constraint, reconciliation |
| Chỉ diễn tập trên DB nhỏ, không có tải | Đánh giá thiếu thời gian thật | Restore test với dữ liệu/tải đại diện |
| Không có owner/on-call hoặc quyền khẩn cấp | Phát hiện nhanh nhưng không ai có thể thực hiện | Role, escalation, break-glass đã diễn tập |
| Lấy thời gian tốt nhất làm RTO đạt được | Che các trường hợp vượt ngưỡng | Ghi mọi lần diễn tập và đánh giá phân phối |

## 30. Bài tập vận dụng

### Bài 1. Tính thời gian gián đoạn

Một API đặt hàng bị gián đoạn lúc 09:00. Alert đến 09:04, primary được promote lúc 09:13, API nhận connection lúc 09:17, kiểm thử nghiệp vụ và mở traffic lúc 09:22. Nếu tiêu chí stop ở mốc cuối, RTO thực đo là bao nhiêu?

**Gợi ý:** 22 phút từ lúc bắt đầu gián đoạn đến khi dịch vụ phục hồi, **không phải** 9 phút từ alert tới promote và cũng không phải chỉ 13 phút từ 09:00 tới lúc DB lên.

### Bài 2. Phân biệt RTO và RPO

Primary chết lúc 15:00, standby mới có dữ liệu tới 14:58 và hệ thống phục hồi lúc 15:12. Nêu thời gian phục hồi và khoảng dữ liệu có nguy cơ mất theo các mốc.

**Gợi ý:** RTO thực đo 12 phút nếu sự cố bắt đầu đúng 15:00 và tiêu chí stop đạt 15:12. Cửa sổ dữ liệu khoảng 2 phút liên quan RPO thực tế; cần đối chiếu transaction đã commit chứ không suy từ đồng hồ một cách tuyệt đối.

### Bài 3. RTO có khả thi không?

Ứng dụng có 600 GiB dữ liệu phải tải qua đường truyền hữu dụng 200 MiB/s. Nhóm cam kết cold restore đầy đủ và mở API trong 10 phút. Điều gì sai?

**Gợi ý:** Chỉ phần truyền 600 GiB đã cần khoảng 51,2 phút trong điều kiện lý tưởng. Cần một chiến lược khác như standby hoặc snapshot khôi phục nhanh đã kiểm chứng, hoặc đổi mục tiêu.

### Bài 4. PostgreSQL đã online nhưng API vẫn lỗi

Sau failover, lệnh **SELECT 1** trên primary mới thành công nhưng pool Java vẫn báo connection timeout. Có được tuyên bố RTO đạt không?

**Gợi ý:** Chưa. Cần kiểm tra endpoint, DNS/proxy, connection pool, credential và thực thi synthetic business transaction trước khi công bố phục hồi.

### Bài 5. Xóa nhầm có thể sửa bằng failover không?

Một lệnh DELETE sai đã commit và được replay đến tất cả standby. Chỉ promote standby có lấy lại dữ liệu không?

**Gợi ý:** Thường không; standby đã mang cùng lỗi logic. Cần backup/PITR/đối soát hoặc cách phục hồi nghiệp vụ phù hợp.

### Bài 6. Bản backup thiếu khóa

Backup được mã hóa đúng chuẩn nhưng DR site không thể truy cập khóa giải mã trong tình huống mất region. Mục tiêu RTO có được bảo đảm không?

**Gợi ý:** Không. Khả năng truy cập key và quyền khẩn cấp là phụ thuộc phải diễn tập; tồn tại file backup chưa đủ.

### Bài 7. Phân bổ ngân sách

RTO mục tiêu 30 phút, phát hiện 6 phút, quyết định 7 phút, failover 12 phút. Còn bao nhiêu thời gian cho route, xác minh và mở traffic?

**Gợi ý:** Còn 5 phút. Nếu các bước còn lại được đo mất 10 phút, kế hoạch chưa đạt RTO dù failover đã thành công.

### Bài 8. Tình huống split-brain

Standby được promote trong lúc primary cũ chỉ bị mất liên lạc với bộ điều phối nhưng vẫn nhận ghi. Vấn đề gì xuất hiện?

**Gợi ý:** Hai nguồn ghi có thể tạo lịch sử dữ liệu phân kỳ. Cần fencing primary cũ, leader election đáng tin và kiểm tra topology trước khi mở traffic.

### Bài 9. Commit timeout

Trong lúc failover, client Java gửi COMMIT tạo đơn và thấy SQLException. Nó có thể lập tức gửi lại tạo đơn với request ID mới không?

**Gợi ý:** Không. COMMIT có thể đã được primary cũ xác nhận. Dùng lại request ID ổn định, unique constraint và tra trạng thái trên nguồn đáng tin cậy để tránh tạo trùng.

### Bài 10. Có cần tính backlog vào RTO?

API đã trả 200 nhưng outbox publisher bị kẹt, khách hàng chưa nhận được xác nhận và cổng thanh toán chưa được cập nhật. Có thể tuyên bố dịch vụ phục hồi không?

**Gợi ý:** Phụ thuộc **tiêu chí nghiệp vụ đã định**. Nếu tác dụng đó là điều kiện hoàn tất của use case, backlog phải được xử lý hoặc có chế độ pending minh bạch được chấp nhận. Không đồng nhất HTTP 200 với hoàn tất toàn nghiệp vụ.

### Bài 11. Chọn nơi đầu tư

Một diễn tập ghi nhận detect 2 phút, restore 48 phút, routing 3 phút và kiểm tra 7 phút. Nhóm dự định tối ưu alert từ 2 phút xuống 30 giây để đạt RTO 15 phút. Có đủ không?

**Gợi ý:** Không. Critical path nằm ở restore gần 48 phút; phải đổi cơ chế phục hồi hoặc cải thiện sâu throughput/kiến trúc, không chỉ tối ưu alert.

### Bài 12. Đánh giá diễn tập

Trong ba diễn tập cùng kịch bản, tổng thời gian là 18, 26 và 34 phút. RTO mục tiêu 30 phút. Có nên báo “đã đạt vì trung bình dưới 30” không?

**Gợi ý:** Không nên. Một lần đã vượt mục tiêu; cần xem nguyên nhân, độ phân tán và mức bảo đảm trước khi khẳng định năng lực phục hồi.

## 31. Checklist thiết lập RTO cho hệ thống persistence Java

1. **Phạm vi:** chức năng nghiệp vụ nào có RTO; tình huống lỗi nào nằm trong cam kết?
2. **Mốc đo:** sự cố bắt đầu khi nào, khi nào dịch vụ được coi là hoạt động trở lại?
3. **Mục tiêu RPO:** dữ liệu nào có thể mất, mức mất tối đa và phương án đối soát?
4. **Kịch bản:** mất node, zone, region, xóa nhầm, migration lỗi, storage corruption, ransomware?
5. **Đường phục hồi:** failover, warm standby, snapshot, cold restore hay PITR phù hợp từng kịch bản?
6. **Ngân sách:** đã tính detection, triage, phê duyệt, restore, WAL replay, routing, validation, traffic?
7. **Khả năng vật lý:** dung lượng backup, tốc độ đọc/ghi, mạng và năng lực DR site có đáp ứng không?
8. **Backup:** base backup, WAL archive, checksum, manifest, retention, mã hóa và key có sẵn?
9. **Failover:** fencing, chọn standby đủ mới, promote, rejoin và tránh split-brain đã có runbook?
10. **Java:** connection pool, endpoint, timeout, DNS, TLS, credentials, transaction recovery và retry đã được thử?
11. **Tính đúng:** sau restore có kiểm tra dữ liệu, giao dịch chưa rõ kết quả, idempotency và quyền tenant?
12. **Dependencies:** KMS, IAM, broker, cache, object storage, payment, schema registry và các dịch vụ khác có nằm trong critical path không?
13. **Runbook:** ai làm bước nào, quyền gì, điều kiện chuyển nhánh và escalation ra sao?
14. **Thử nghiệm:** đã diễn tập với dữ liệu/tải đại diện, cả giờ cao điểm và kịch bản thất bại chưa?
15. **Đo lường:** timestamp đầy đủ, báo cáo thực đo, các lần vượt mục tiêu và hành động khắc phục?
16. **Truyền thông:** có thông báo khi sự cố vượt RTO và quyết định degrade an toàn đã được phê duyệt?

## 32. Tổng kết

**RTO không phải thời gian khởi động database hay chạy một lệnh restore; đó là mục tiêu thời gian để khôi phục chức năng dịch vụ theo điều kiện đã được nghiệp vụ phê duyệt.** Một RTO có ý nghĩa luôn gắn với kịch bản sự cố, mốc bắt đầu, mốc kết thúc và mức dịch vụ tối thiểu. Phải phân biệt **RTO (thời gian)** với **RPO (mức mất dữ liệu)**; rút ngắn thời gian bằng một lần failover không đáng giá nếu làm mất dữ liệu ngoài giới hạn hoặc tạo split-brain.

Với PostgreSQL và ứng dụng Java, hãy phân rã RTO thành **phát hiện → quyết định → failover/restore/PITR → kết nối ứng dụng → xác minh dữ liệu, giao dịch và phụ thuộc → mở traffic**. Đo thời gian của từng bước trên dữ liệu và hạ tầng đại diện, đặc biệt là kích thước backup, WAL replay, connection pool và đường đọc/ghi sau failover. Chuẩn bị backup có thể restore, quyền/khóa giải mã, HA an toàn, runbook được diễn tập và các kiểm tra nghiệp vụ end-to-end là cách biến một con số RTO thành **năng lực phục hồi có thể chứng minh**.
