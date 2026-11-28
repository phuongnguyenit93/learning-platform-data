# RTO của key recovery

Trong quản lý khóa mật mã, **Recovery Time Objective (RTO)** là khoảng thời gian mục tiêu tối đa mà tổ chức đặt ra để khôi phục một dịch vụ hoặc hoạt động sau gián đoạn. Với key recovery, RTO cho biết tổ chức cần khôi phục khả năng sử dụng khóa và các thành phần phụ thuộc trong bao lâu để nghiệp vụ có thể tiếp tục. Mục tiêu này có thể áp dụng cho việc giải mã dữ liệu cũ, mở khóa DEK, mã hóa dữ liệu mới, ký số hoặc vận hành một hệ thống phụ thuộc vào KMS/HSM.

RTO không chỉ là thời gian đưa một bản backup khóa trở lại thiết bị. Một khóa chỉ thực sự phục vụ được nghiệp vụ khi hệ thống khôi phục được đúng vật liệu khóa hoặc cơ chế truy cập khóa, đúng phiên bản và metadata, quyền truy cập, cấu hình, đường mạng và ứng dụng cần dùng khóa. Vì vậy, cần xác định RTO theo dịch vụ và thao tác mật mã cụ thể, rồi đo thời gian đến khi thao tác nghiệp vụ được xác minh thành công.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**: quản lý khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy. Việc xác định RTO phải tính đến mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. RTO có nghĩa gì trong key recovery?

RTO là mục tiêu về **thời gian khôi phục** sau một sự cố. Trong key recovery, nó trả lời câu hỏi:

> Sau khi một sự cố làm mất khả năng sử dụng khóa xảy ra, trong bao lâu hệ thống phải lấy lại được khả năng mật mã cần thiết để nghiệp vụ tiếp tục?

Ví dụ, một dịch vụ lưu hồ sơ đã mã hóa bằng DEK. DEK được bọc bằng KEK trong KMS. Nếu KMS của vùng chính ngừng hoạt động, dịch vụ có thể không mở được DEK và không đọc được hồ sơ. RTO của quy trình phục hồi phải bao gồm thời gian chuyển sang vùng dự phòng hoặc khôi phục KMS, xác minh quyền truy cập KEK, mở được DEK và kiểm tra ứng dụng đọc thành công dữ liệu. Chỉ thấy KMS trả lời health check chưa đủ để kết luận đã đạt RTO.

RTO là mục tiêu được tổ chức chấp nhận dựa trên tác động kinh doanh, năng lực kỹ thuật và chi phí. Đây không phải cam kết mặc định của nhà cung cấp KMS, cũng không phải thời gian mà mọi sự cố chắc chắn sẽ được xử lý xong. Tổ chức phải chứng minh kiến trúc và quy trình của mình có thể đáp ứng mục tiêu đó qua kiểm thử.

## 2. Xác định điểm bắt đầu và điểm kết thúc của đồng hồ RTO

RTO chỉ có thể đo được khi định nghĩa rõ đồng hồ bắt đầu lúc nào và điều kiện nào được xem là khôi phục xong.

**Điểm bắt đầu** nên được ghi rõ trong chính sách. Có thể lấy thời điểm dịch vụ bắt đầu bị gián đoạn hoặc thời điểm sự cố được tuyên bố. Nếu dùng thời điểm tuyên bố sự cố, phải đo riêng thời gian phát hiện và tuyên bố để không bỏ qua độ trễ trước khi đội recovery bắt đầu làm việc. Với diễn tập, nên ghi cả thời điểm lỗi được đưa vào và thời điểm đội vận hành nhận biết lỗi.

**Điểm kết thúc** phải dựa trên kết quả nghiệp vụ có thể kiểm chứng, ví dụ:

- Ứng dụng gọi được đúng KMS/HSM hoặc vùng dự phòng bằng danh tính được phép.
- Khóa và phiên bản cần thiết có thể thực hiện đúng thao tác: unwrap/decrypt, encrypt hoặc sign theo phạm vi phục hồi.
- Một mẫu dữ liệu đại diện được giải mã và kiểm tra tính toàn vẹn thành công.
- Các dịch vụ phụ thuộc đã hoạt động, hàng đợi tồn đọng được xử lý theo kế hoạch và lưu lượng có thể trở lại mức vận hành chấp nhận được.
- Log kiểm toán được tạo đầy đủ và không làm lộ vật liệu khóa.

Nếu chỉ khôi phục quyền truy cập đọc dữ liệu cũ nhưng chưa thể mã hóa dữ liệu mới, đó có thể là một trạng thái phục hồi từng phần. Hãy định nghĩa riêng RTO cho từng khả năng, chẳng hạn RTO-Decrypt và RTO-New-Encrypt, thay vì gộp chúng thành một trạng thái “KMS đã online”.

## 3. Phân biệt RTO, RPO và các chỉ số liên quan

RTO và Recovery Point Objective (RPO) trả lời hai câu hỏi khác nhau. RTO nói về **mất bao lâu để khôi phục**; RPO nói về **mức dữ liệu hoặc trạng thái gần nhất mà tổ chức có thể chấp nhận bị mất**.

| Chỉ số | Câu hỏi cần trả lời | Ý nghĩa với key recovery |
|---|---|---|
| RTO | Khôi phục trong bao lâu? | Thời gian để lấy lại thao tác mật mã và dịch vụ phụ thuộc khóa ở mức đã định nghĩa. |
| RPO | Có thể mất trạng thái mới nhất đến mức nào? | Mức mất trạng thái khóa, phiên bản, metadata, chính sách hoặc dữ liệu phụ thuộc khóa mà tổ chức chấp nhận. |
| MTPD/MAO | Gián đoạn tối đa bao lâu trước khi hậu quả trở nên không thể chấp nhận? | Giới hạn kinh doanh để đặt RTO có khoảng dự phòng phù hợp. |
| MTTR | Thời gian sửa chữa hoặc khôi phục trung bình là bao nhiêu? | Chỉ số quan sát vận hành qua nhiều sự cố; không thay thế mục tiêu RTO đã được phê duyệt. |
| SLA/SLO | Mức dịch vụ cam kết hoặc mục tiêu vận hành là gì? | Có thể mô tả tính sẵn sàng của nhà cung cấp hay hệ thống, nhưng không tự động chứng minh khả năng phục hồi khóa đầu cuối. |

Ví dụ: dịch vụ có RTO 60 phút và RPO 5 phút. Sau sự cố, tổ chức đặt mục tiêu khôi phục dịch vụ trong tối đa 60 phút, đồng thời chỉ chấp nhận mất tối đa 5 phút trạng thái đã ghi nhận theo định nghĩa RPO. Hai mục tiêu phải được kiểm tra độc lập.

Với khóa ngẫu nhiên, mất một phiên bản khóa có thể làm dữ liệu được mã hóa bằng phiên bản đó không thể giải mã. Vì vậy, RPO cho trạng thái khóa thường cần chặt hơn RPO của một số dữ liệu vận hành thông thường. Một thiết kế an toàn có thể yêu cầu khóa và metadata cần thiết được bảo vệ bền vững trước khi cho phép ứng dụng mã hóa dữ liệu phụ thuộc vào khóa mới. Không nên giả định rằng có thể tạo lại cùng một khóa chỉ vì bản ghi tạo khóa bị mất.

## 4. Đặt RTO theo tác động nghiệp vụ

Không có một RTO đúng cho mọi khóa. Hãy phân loại dịch vụ theo tác động khi thao tác mật mã không còn khả dụng:

- **Dịch vụ thời gian thực:** thanh toán, xác thực giao dịch, API cần giải mã dữ liệu để trả lời yêu cầu. Mỗi phút gián đoạn có thể gây lỗi giao dịch hoặc mất doanh thu.
- **Dịch vụ nội bộ quan trọng:** hệ thống kế toán, kho dữ liệu, quản trị danh tính hoặc xử lý batch. Một khoảng gián đoạn ngắn có thể chấp nhận được nếu dữ liệu được giữ nguyên và có thể xử lý bù.
- **Dữ liệu lưu trữ dài hạn:** hồ sơ, bản backup hoặc dữ liệu lưu trữ theo yêu cầu pháp lý. Khả năng khôi phục có thể cần thiết trong nhiều năm, nhưng RTO có thể khác dịch vụ trực tuyến.
- **Hệ thống tin cậy và ký số:** CA, ký phần mềm, ký tài liệu hoặc ký giao dịch. Mất khóa ký có thể làm dừng việc phát hành chữ ký mới; khả năng xác minh chữ ký cũ bằng khóa công khai có thể vẫn hoạt động.

Bảng sau chỉ là ví dụ minh họa để thảo luận với chủ sở hữu nghiệp vụ; không phải ngưỡng tiêu chuẩn áp dụng cho mọi tổ chức.

| Dịch vụ hoặc khả năng | RTO minh họa | Lý do cần xem xét |
|---|---:|---|
| Mã hóa/giải mã cho luồng thanh toán đang hoạt động | 15 phút | Gián đoạn ảnh hưởng trực tiếp đến giao dịch đang diễn ra. |
| Mở DEK để đọc hồ sơ vận hành quan trọng | 1 giờ | Cần khôi phục truy cập dữ liệu để nhân viên tiếp tục xử lý công việc. |
| Khôi phục quyền ký bằng khóa của hệ thống phát hành | 4 giờ | Có thể có hàng đợi chờ ký, nhưng cần duy trì danh tính và kiểm soát phê duyệt. |
| Truy cập dữ liệu lưu trữ ít được dùng | 24 giờ | Có thể chấp nhận thời gian phục hồi dài hơn nếu nghĩa vụ lưu trữ vẫn được đáp ứng. |

RTO cần được phê duyệt bởi chủ sở hữu nghiệp vụ, người chịu trách nhiệm về dữ liệu và đội vận hành nền tảng mật mã. Nếu mục tiêu quá ngắn so với khả năng thực tế, phải điều chỉnh kiến trúc, quy trình hoặc mục tiêu kinh doanh; không chỉ ghi một con số nhỏ vào tài liệu.

## 5. Lập bản đồ phụ thuộc trước khi đặt RTO

Khôi phục khóa thường phụ thuộc vào nhiều thành phần. Một quy trình có thể thất bại dù vật liệu khóa còn nguyên nếu thiếu danh tính quản trị, cấu hình HSM, kết nối mạng hoặc metadata xác định phiên bản.

Các phụ thuộc thường cần kiểm kê:

| Phụ thuộc | Vì sao ảnh hưởng đến RTO |
|---|---|
| KMS/HSM và miền bảo mật | Nơi thực hiện thao tác mật mã hoặc khôi phục vật liệu khóa. |
| Backup, replica và metadata | Cung cấp đúng phiên bản khóa, key ID, thuộc tính và quan hệ bọc khóa. |
| IAM, tài khoản quản trị và MFA | Cần để người được ủy quyền truy cập hoặc khôi phục khóa. |
| Network, DNS, định tuyến và firewall | Ứng dụng và đội recovery phải kết nối được đến KMS/HSM dự phòng. |
| Cấu hình ứng dụng và key reference | Ứng dụng phải biết key ID, phiên bản và context phù hợp. |
| Ciphertext, DEK đã bọc và dữ liệu | Cần có đủ dữ liệu để chứng minh thao tác giải mã hoạt động. |
| Hệ thống audit và giám sát | Ghi nhận hành động recovery và xác nhận trạng thái sau khôi phục. |
| Nhân sự và quy trình phê duyệt | Người giữ quyền, custodians và người phê duyệt phải sẵn sàng theo cơ chế đã định. |

Một luồng phụ thuộc đơn giản trong envelope encryption:

~~~mermaid
flowchart TD
    A["Sự cố làm mất khả năng dùng khóa"] --> B["Kích hoạt kế hoạch recovery"]
    B --> C["Khôi phục danh tính, quyền và kết nối"]
    C --> D["Truy cập hoặc khôi phục KMS/HSM"]
    D --> E["Xác định đúng KEK và phiên bản"]
    E --> F["Unwrap DEK đã lưu"]
    F --> G["Giải mã mẫu dữ liệu trong ứng dụng"]
    G --> H["Xác nhận dịch vụ và audit"]
~~~

Đồ thị phụ thuộc cũng giúp phát hiện vòng phụ thuộc. Ví dụ, nếu thông tin đăng nhập quản trị KMS lại được mã hóa bằng một khóa chỉ có thể lấy từ chính KMS đó, đội recovery có thể không có cách khởi động quy trình. Cần có thông tin bootstrap và cơ chế truy cập khẩn cấp độc lập, được bảo vệ và kiểm soát riêng.

## 6. Chọn kiến trúc đáp ứng RTO

Kiến trúc recovery quyết định phần lớn thời gian khôi phục. Có thể kết hợp các phương án sau:

| Mô hình | Cách hoạt động | Đặc điểm về RTO |
|---|---|---|
| Hot standby / active-active | Vùng hoặc cụm dự phòng sẵn sàng xử lý yêu cầu; khóa hoặc quyền truy cập được đồng bộ theo cơ chế được hỗ trợ. | Có thể đạt RTO ngắn, nhưng cần kiểm soát nhất quán, định tuyến và tránh hai nơi cùng ghi sai trạng thái. |
| Warm standby | Có hạ tầng và cấu hình dự phòng, nhưng cần một số bước kích hoạt hoặc đồng bộ trước khi dùng. | RTO phụ thuộc thời gian kích hoạt, xác minh và chuyển ứng dụng. |
| Cold recovery | Khôi phục từ backup, dựng lại thiết bị hoặc miền bảo mật rồi cấu hình ứng dụng. | Thường cần nhiều thời gian hơn; phải tính thời gian tìm phương tiện, phê duyệt, khôi phục và kiểm thử. |
| Nhà cung cấp hoặc vùng độc lập | Dùng phương án dự phòng tách biệt với miền lỗi chính. | Có thể giảm rủi ro sự cố diện rộng nhưng tăng độ phức tạp về tương thích khóa, danh tính và vận hành. |

Replication giúp tăng khả năng sẵn sàng nhưng không thay thế hoàn toàn backup. Thao tác xóa, cấu hình sai hoặc hành vi xâm nhập có thể lan sang replica. Cần kết hợp bản sao tách biệt, quyền xóa độc lập và kiểm thử restore nếu yêu cầu phục hồi bao gồm cả lỗi logic hoặc phá hoại.

Với khóa **non-exportable**, không được giả định có thể lấy vật liệu khóa ra để nhập vào bất kỳ HSM nào. Hãy thiết kế theo khả năng backup, clone, replication hoặc disaster recovery chính thức của KMS/HSM. Xác minh trước các điều kiện như cùng miền bảo mật, thiết bị tương thích, quorum quản trị và phiên bản firmware. Nếu nền tảng không có đường phục hồi được hỗ trợ, giới hạn đó phải được phản ánh trong RTO và quyết định chấp nhận rủi ro.

## 7. Tính ngân sách thời gian phục hồi

RTO tổng thể là giới hạn cho toàn bộ đường phục hồi. Không nên dành toàn bộ ngân sách cho thao tác restore khóa rồi bỏ quên phát hiện sự cố, phê duyệt, chuyển tuyến và kiểm tra ứng dụng.

Ví dụ, một dịch vụ có RTO 60 phút. Nhóm có thể phân bổ ngân sách như sau:

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Phát hiện, phân loại và tuyên bố sự cố | 5 phút |
| Gọi đúng người, xác thực và phê duyệt recovery | 10 phút |
| Chuyển vùng hoặc khôi phục KMS/HSM | 15 phút |
| Khôi phục metadata, policy và key reference | 10 phút |
| Kiểm thử thao tác mật mã trong ứng dụng | 10 phút |
| Chuyển lưu lượng và xác nhận ổn định | 5 phút |
| Dự phòng cho biến động | 5 phút |
| **Tổng ngân sách** | **60 phút** |

Đây là ví dụ lập kế hoạch, không phải thời gian cam kết. Khi kiểm thử, cần ghi thời gian thực tế cho từng giai đoạn và điều chỉnh ngân sách theo bằng chứng. Nếu bước phê duyệt mất 25 phút trong khi kế hoạch chỉ dành 10 phút, cần giải quyết nguyên nhân như lịch trực, phân quyền hoặc quy trình xác thực.

Có thể biểu diễn:

\[
T_{recovery} = T_{detect} + T_{declare} + T_{authorize} + T_{restore} + T_{configure} + T_{validate} + T_{cutover}
\]

Trong đó, tổng thời gian đo được phải nằm trong RTO đã phê duyệt. Nếu tổ chức bắt đầu đồng hồ tại thời điểm tuyên bố sự cố thì vẫn nên đo và báo cáo riêng \(T_{detect}\) để hiểu thời gian gián đoạn thực tế.

## 8. Quy trình khôi phục khóa theo từng giai đoạn

Một runbook thực tế nên nêu người chịu trách nhiệm, điều kiện chuyển bước, bằng chứng đầu ra và phương án quay lại.

| Giai đoạn | Công việc | Bằng chứng hoàn thành |
|---|---|---|
| 1. Phát hiện và phân loại | Xác định vùng, loại khóa, thao tác bị ảnh hưởng và liệu đây là mất khả năng truy cập hay nghi ngờ compromise. | Incident ID, phạm vi ảnh hưởng và mức độ ưu tiên được ghi nhận. |
| 2. Kích hoạt | Gọi incident commander, key custodians, chủ sở hữu ứng dụng và người phê duyệt theo danh sách trực. | Đúng người tham gia; quyết định kích hoạt được lưu audit. |
| 3. Chọn đường recovery | Quyết định failover sang replica, restore backup hoặc dựng lại miền bảo mật. | Phương án phù hợp với nguyên nhân và miền lỗi đã được xác nhận. |
| 4. Khôi phục quyền và hạ tầng | Xác minh danh tính, MFA, quyền quản trị, network và cấu hình cần thiết. | Đội recovery truy cập được môi trường đích theo quyền tối thiểu. |
| 5. Khôi phục khóa | Khôi phục hoặc truy cập đúng key ID, phiên bản, policy và miền bảo mật. | KMS/HSM xác nhận khóa sẵn sàng theo trạng thái mong muốn. |
| 6. Kiểm thử mật mã | Thử unwrap/decrypt/encrypt/sign bằng dữ liệu kiểm thử đã định trước. | Kết quả mật mã hợp lệ và ứng dụng đọc được dữ liệu mẫu. |
| 7. Chuyển dịch vụ | Chuyển ứng dụng hoặc lưu lượng theo từng bước; theo dõi lỗi và độ trễ. | Giao dịch hoặc tác vụ đại diện thành công trong môi trường phục hồi. |
| 8. Kết thúc và rà soát | Ghi thời gian, hành động, ngoại lệ, trạng thái bản backup và việc cần khắc phục. | Biên bản recovery, audit đầy đủ và kế hoạch follow-up. |

Không nên bật lại lưu lượng sản xuất chỉ vì thao tác restore trả về thành công. Cần xác nhận ứng dụng đang dùng đúng key ID và version, dữ liệu không bị tráo context, quyền truy cập vẫn đúng tenant và log kiểm toán được ghi nhận.

## 9. Quản lý quyền khẩn cấp mà không làm chậm recovery

Quy trình phê duyệt có thể trở thành nút thắt RTO nếu chỉ một cá nhân có quyền khôi phục hoặc người phê duyệt không có mặt. Tuy nhiên, mở quyền rộng cho mọi người để rút ngắn thời gian sẽ tạo rủi ro lạm dụng.

Nên chuẩn bị trước:

- Danh sách trực và kênh liên hệ cho incident commander, key owner, custodians, quản trị KMS/HSM và chủ sở hữu ứng dụng.
- Quy trình dual control hoặc M-of-N cho thao tác nhạy cảm, với số người và cách xác thực đã được diễn tập.
- Tài khoản break-glass được bảo vệ độc lập, quyền giới hạn theo thời gian và phạm vi, MFA mạnh, phê duyệt rõ ràng và cảnh báo tức thời.
- Hướng dẫn lấy lại quyền quản trị khi hệ thống IAM chính bị sự cố, không phụ thuộc vào bí mật chỉ có thể lấy từ KMS đang gặp lỗi.
- Quy định ghi log đầy đủ cho mọi thao tác khẩn cấp và rà soát sau sự cố.

Break-glass giúp khôi phục quyền truy cập trong tình huống đặc biệt; nó không phải tài khoản dùng chung hoặc cách bỏ qua kiểm soát. Cần kiểm tra cả tính sẵn sàng của phương thức xác thực, thiết bị MFA, thông tin liên hệ và người giữ các thành phần cần thiết.

## 10. Giữ đúng phiên bản khóa và dữ liệu phụ thuộc

Một trong những nguyên nhân làm recovery kéo dài là đội vận hành khôi phục được khóa nhưng không biết phiên bản nào đã bảo vệ dữ liệu. Hệ thống cần lưu key ID và version rõ ràng cùng ciphertext hoặc DEK đã bọc. Không nên chỉ lưu alias có thể trỏ sang phiên bản mới mà không giữ lịch sử ánh xạ.

Với envelope encryption:

- Mỗi DEK cần được liên kết với KEK và phiên bản đã bọc nó.
- Metadata cần đủ để dựng lại context, chẳng hạn tenant, resource ID, thuật toán, nonce/tag và AAD theo thiết kế.
- Việc xoay vòng KEK không có nghĩa là có thể xóa KEK cũ ngay; dữ liệu hoặc DEK đã bọc có thể vẫn phụ thuộc vào phiên bản cũ.
- Sau recovery, phải xác minh khả năng unwrap các phiên bản còn được lưu giữ, không chỉ phiên bản mới nhất.

Khi ứng dụng ghi dữ liệu bằng một phiên bản khóa mới, trạng thái khóa cần được bảo vệ bền vững trước khi dữ liệu phụ thuộc vào nó được xác nhận thành công. Cơ chế ghi nhận key version, ciphertext và metadata phải có khả năng xử lý retry, lỗi giữa chừng và phục hồi nhất quán.

## 11. RTO cho các thao tác mật mã khác nhau

Không phải mọi thao tác với khóa đều cần cùng một thời gian phục hồi:

| Thao tác | Câu hỏi phục hồi | Lưu ý |
|---|---|---|
| Decrypt/unwrap dữ liệu cũ | Có thể mở dữ liệu đã lưu bằng đúng phiên bản khóa không? | Có thể cần nhiều phiên bản KEK/DEK cũ và metadata đi kèm. |
| Encrypt dữ liệu mới | Có thể tạo hoặc lấy DEK mới và bảo vệ nó bằng KEK đang hoạt động không? | Không nên ghi dữ liệu mới bằng khóa hoặc policy chưa được xác minh. |
| Sign | Có thể ký mới bằng đúng danh tính và quyền phê duyệt không? | Mất khóa riêng ký có thể cần recovery nghiêm ngặt; nếu không thể phục hồi, có thể phải chuyển sang khóa và chứng thư mới. |
| Verify | Có thể xác minh chữ ký cũ bằng khóa công khai, chứng thư và dữ liệu tin cậy không? | Thường không cần khôi phục khóa riêng ký để xác minh; phải giữ vật liệu công khai và chuỗi tin cậy. |
| TLS handshake | Dịch vụ có thể hoàn tất bắt tay bằng khóa riêng và chứng thư hợp lệ không? | Có thể cần khôi phục khóa hoặc cấp cặp khóa/chứng thư mới tùy thiết kế. |

Ví dụ, một hệ thống ký tài liệu có thể đặt RTO ngắn cho việc xác minh tài liệu đã ký vì xác minh dùng khóa công khai đã được phân phối, nhưng đặt RTO khác cho việc tiếp tục ký mới bằng khóa riêng của CA. Tách mục tiêu giúp không kéo dài hoặc rút ngắn sai kỳ vọng.

## 12. Đo lường RTO bằng kiểm thử

Không thể chứng minh RTO chỉ bằng cách đọc tài liệu thiết kế hoặc kiểm tra trạng thái backup. Cần diễn tập có đo thời gian và bằng chứng đầu cuối.

Các cấp độ kiểm thử nên bao gồm:

1. **Kiểm thử thành phần:** restore hoặc failover KMS/HSM, xác minh phiên bản khóa và policy.
2. **Kiểm thử thao tác mật mã:** unwrap một DEK thử nghiệm, giải mã mẫu dữ liệu, ký và xác minh một thông điệp thử.
3. **Kiểm thử ứng dụng:** chạy luồng nghiệp vụ đại diện qua vùng phục hồi, xác nhận key reference và quyền truy cập.
4. **Kiểm thử quy trình con người:** mô phỏng gọi người trực, dual control, break-glass và phê duyệt ngoài giờ.
5. **Diễn tập thảm họa:** mô phỏng mất vùng hoặc thiết bị chính, thực hiện toàn bộ runbook và chuyển dịch vụ.
6. **Kiểm thử lỗi phụ thuộc:** mô phỏng IAM, DNS, network hoặc audit service không sẵn sàng để phát hiện vòng phụ thuộc và nút thắt.

Nên kiểm thử trong môi trường cô lập, dùng khóa và dữ liệu thử nghiệm. Không tùy tiện xóa khóa sản xuất hoặc làm gián đoạn dịch vụ thật để đo RTO. Với thao tác nhạy cảm, phải có kế hoạch quay lui, người giám sát và phê duyệt theo chính sách.

Kết quả mỗi lần diễn tập cần ghi:

- Thời điểm bắt đầu lỗi, phát hiện, tuyên bố sự cố và bắt đầu từng bước.
- Thời gian khôi phục quyền, KMS/HSM, metadata, ứng dụng và lưu lượng.
- Thao tác mật mã đã thử và bằng chứng kết quả.
- RTO thực tế, RPO thực tế và phần ngân sách đã sử dụng.
- Bước bị chậm, phụ thuộc không sẵn sàng, thao tác thủ công và lỗi tài liệu.
- Người tham gia, người phê duyệt và liên kết đến audit log.

Nếu thời gian thực tế vượt RTO, phải ghi nhận là không đạt mục tiêu, tìm nguyên nhân và cập nhật kiến trúc hoặc runbook. Không được đổi mốc bắt đầu sau diễn tập chỉ để làm số đo có vẻ đạt.

## 13. Chỉ số vận hành cần theo dõi

Các chỉ số sau giúp phát hiện sớm nguy cơ không đạt RTO:

| Chỉ số | Ý nghĩa |
|---|---|
| Recovery readiness | Tỷ lệ khóa/dịch vụ có đường recovery được ghi nhận và kiểm thử gần đây. |
| Restore duration | Thời gian thực tế để khôi phục KMS/HSM hoặc phiên bản khóa. |
| Application recovery duration | Thời gian từ khi có khóa đến khi luồng nghiệp vụ thành công. |
| Approval latency | Thời gian chờ xác thực, quorum và phê duyệt. |
| Dependency availability | Mức sẵn sàng của IAM, network, DNS, audit và các thành phần bootstrap. |
| Recovery test pass rate | Tỷ lệ diễn tập đạt RTO và RPO đã phê duyệt. |
| Key version coverage | Tỷ lệ dữ liệu lưu trữ có thể xác định đúng key ID/version cần thiết. |

Không đưa vật liệu khóa, DEK hoặc secret vào metric và log. Chỉ ghi metadata vận hành cần thiết như key ID đã được phân loại phù hợp, version, trạng thái, thời gian, kết quả và mã sự cố. Log recovery cần chống sửa đổi và có thể truy vết đến người thực hiện.

## 14. Ví dụ: khôi phục dịch vụ dữ liệu dùng envelope encryption

Một hệ thống hồ sơ lưu ciphertext trong cơ sở dữ liệu. Mỗi bản ghi được mã hóa bằng DEK riêng; DEK được bọc bởi KEK trong KMS của vùng chính. Hệ thống đặt RTO đọc hồ sơ là 60 phút.

Khi vùng chính gặp sự cố, đội recovery thực hiện:

1. Tuyên bố sự cố và xác định key ID/version mà dữ liệu đang sử dụng.
2. Chuyển sang vùng KMS dự phòng đã được chuẩn bị, hoặc khôi phục KMS/HSM từ backup theo runbook.
3. Xác minh danh tính, policy, quyền unwrap và metadata cần cho context.
4. Lấy một mẫu ciphertext cùng DEK đã bọc, gọi thao tác unwrap bằng đúng KEK/version.
5. Giải mã mẫu dữ liệu trong ứng dụng và xác minh kết quả với dữ liệu tham chiếu.
6. Chuyển lưu lượng theo từng bước, theo dõi lỗi decrypt, độ trễ và audit.

Giả sử toàn bộ quá trình mất 48 phút từ lúc sự cố bắt đầu đến khi luồng đọc hồ sơ thành công và ổn định. RTO 60 phút đạt trong lần diễn tập đó, còn 12 phút dự phòng. Kết quả này chỉ có giá trị cho phạm vi và điều kiện đã thử; cần kiểm thử thêm các phiên bản khóa cũ, tải thực tế, quyền khẩn cấp và trường hợp vùng dự phòng cũng gặp lỗi.

Nếu chỉ KMS health check thành công ở phút thứ 20 nhưng ứng dụng không unwrap được DEK do policy thiếu hoặc key version không tồn tại, thời gian recovery chưa kết thúc ở phút 20. Đồng hồ chỉ dừng khi điều kiện nghiệp vụ đã định nghĩa được đáp ứng.

## 15. Ví dụ: khôi phục khả năng ký số

Một hệ thống phát hành tài liệu dùng khóa riêng trong HSM để ký. RTO cho việc ký tài liệu mới là 4 giờ. Khi thiết bị chính hỏng, đội vận hành cần kiểm tra:

- HSM dự phòng có cùng miền bảo mật hoặc có thể khôi phục backup theo quy trình đã kiểm thử không?
- Quorum custodians và người phê duyệt có sẵn sàng không?
- Chứng thư, chuỗi CA, key ID và cấu hình ứng dụng có tương ứng với khóa được khôi phục không?
- Chữ ký thử có xác minh thành công bằng khóa công khai và chứng thư đã công bố không?
- Quy trình ký có giữ nguyên chính sách phê duyệt, dấu thời gian và audit không?

Nếu không thể khôi phục khóa riêng nhưng có thể tạo khóa mới, tổ chức có thể phải phát hành chứng thư mới, cập nhật bên xác minh và xử lý danh tính tin cậy. Đây là phương án thay thế có tác động rộng hơn và phải được tính trong kế hoạch BCP/DR, không được coi tương đương với restore khóa cũ.

## 16. Khi khóa bị compromise, mục tiêu recovery thay đổi

RTO của key recovery thường giả định khóa bị mất khả năng truy cập do sự cố khả dụng, thiết bị hỏng hoặc lỗi hạ tầng. Nếu khóa bị lộ hoặc nghi bị xâm phạm, khôi phục lại chính khóa đó có thể làm tăng rủi ro.

Trong tình huống compromise, mục tiêu ưu tiên là cô lập, đánh giá phạm vi ảnh hưởng, thu hồi hoặc vô hiệu hóa khóa theo chính sách, tạo khóa thay thế, cập nhật hệ thống phụ thuộc và re-encrypt hoặc re-wrap dữ liệu khi cần. Thời gian cần để khôi phục hoạt động an toàn có thể được quản lý bằng một mục tiêu phục hồi sự cố riêng, bao gồm thời gian containment và thay thế khóa.

Không dùng bản backup của khóa nghi bị lộ làm khóa hoạt động trở lại. Bản backup chứa cùng vật liệu khóa và có thể đã bị xâm phạm. Nếu cần giữ bản sao phục vụ điều tra, phải cách ly và kiểm soát theo quy trình incident response.

## 17. Những lỗi thường làm trượt RTO

- Chỉ đo thời gian restore vật liệu khóa mà bỏ qua IAM, phê duyệt, mạng, metadata và kiểm thử ứng dụng.
- Dùng SLA của nhà cung cấp làm bằng chứng duy nhất cho RTO của nghiệp vụ.
- Không lưu key ID/version cùng ciphertext hoặc DEK đã bọc, khiến đội recovery không xác định được khóa cần thiết.
- Có replica nhưng không có backup tách biệt, nên lỗi xóa hoặc hành vi phá hoại lan sang bản sao.
- Quy trình khẩn cấp phụ thuộc vào một người, một thiết bị MFA hoặc một tài khoản đang nằm trong vùng sự cố.
- Backup khóa non-exportable nhưng chưa từng thử restore trên miền bảo mật tương thích.
- Chỉ kiểm tra KMS API mà không kiểm thử unwrap/decrypt/sign qua ứng dụng.
- Không kiểm thử các phiên bản khóa cũ còn bảo vệ dữ liệu lưu trữ.
- Không có thông tin bootstrap độc lập, tạo vòng phụ thuộc giữa KMS và danh tính quản trị.
- Không ghi thời gian từng bước, nên không biết nút thắt thực sự nằm ở kỹ thuật hay phê duyệt.

## 18. Checklist xác lập và duy trì RTO

Trước khi phê duyệt RTO cho một dịch vụ phụ thuộc khóa, hãy xác nhận:

- [ ] Đã xác định nghiệp vụ và thao tác mật mã cần khôi phục: decrypt, unwrap, encrypt, sign hoặc verify.
- [ ] Đã có chủ sở hữu nghiệp vụ phê duyệt tác động và RTO.
- [ ] Đã xác định rõ điểm bắt đầu, điểm kết thúc và cách đo thời gian phát hiện.
- [ ] Đã xác định RPO và quan hệ giữa trạng thái khóa với dữ liệu phụ thuộc.
- [ ] Đã kiểm kê key ID, version, thuật toán, policy, ciphertext và quan hệ KEK/DEK.
- [ ] Đã lập bản đồ KMS/HSM, IAM, network, DNS, backup, audit và các phụ thuộc bootstrap.
- [ ] Đã chọn mô hình hot, warm hoặc cold recovery phù hợp với RTO và chi phí.
- [ ] Đã xác nhận cơ chế recovery chính thức cho khóa non-exportable.
- [ ] Đã chuẩn bị quyền khẩn cấp, custodians, quorum và danh sách trực.
- [ ] Đã phân bổ ngân sách thời gian cho phát hiện, phê duyệt, restore, cấu hình, kiểm thử và cutover.
- [ ] Đã có runbook, bằng chứng đầu ra và điều kiện quay lui cho từng bước.
- [ ] Đã diễn tập end-to-end bằng dữ liệu thử nghiệm và đo RTO/RPO thực tế.
- [ ] Đã theo dõi các bước chậm, khắc phục và lên lịch kiểm thử lại sau thay đổi lớn.
- [ ] Đã tách quy trình mất khả năng truy cập khóa khỏi quy trình xử lý khóa bị compromise.

Một RTO có ý nghĩa khi gắn với một kết quả nghiệp vụ đo được, một đường phục hồi đã được kiểm thử và những người có thể thực hiện quy trình trong điều kiện sự cố thật. Khi kiến trúc, quyền truy cập hoặc phụ thuộc thay đổi, cần đánh giá lại RTO và diễn tập để bảo đảm mục tiêu vẫn khả thi.
