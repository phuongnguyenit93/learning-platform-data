# Certificate rotation

## 1. Certificate rotation là gì?

**Certificate rotation** là quá trình đưa chứng chỉ mới vào sử dụng và kết thúc việc sử dụng chứng chỉ cũ theo một chính sách có kiểm soát. Mục tiêu là duy trì xác thực danh tính, bảo vệ kênh truyền và tránh gián đoạn khi chứng chỉ hết hạn, thay đổi cấu hình hoặc có sự cố bảo mật.

Trong chương **Communication security** của module yêu cầu bảo mật, yêu cầu không nên chỉ dừng ở “tự động gia hạn chứng chỉ”. Cần xác định chứng chỉ nào bảo vệ luồng nào, ai kiểm tra nó, thời điểm nào phải thay, bằng chứng nào chứng minh phiên bản mới thực sự được dùng và cách xử lý khi không thể hoàn tất đúng hạn.

Ví dụ, hệ thống đã cấp chứng chỉ mới và ghi file vào nơi cấu hình nhưng tiến trình vẫn giữ chứng chỉ cũ trong bộ nhớ. Bảng quản lý báo gia hạn thành công, trong khi các TLS handshake mới vẫn nhận chứng chỉ sắp hết hạn. Đây là khoảng cách giữa việc tạo artifact và việc kiểm soát kênh truyền thực tế.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt đổi chứng chỉ, đổi khóa, đổi CA và cập nhật trust store.
2. Đặc tả tồn kho chứng chỉ, chủ sở hữu, luồng tin cậy và thời hạn thay thế.
3. Viết yêu cầu rollout, khoảng cùng tồn tại và điều kiện kết thúc phiên bản cũ.
4. Xác định tác động của mTLS, kết nối dài và session resumption.
5. Xây dựng tiêu chí nghiệm thu cho trạng thái bình thường, lỗi và sự cố lộ khóa.

## 2. Phân biệt các thay đổi trong vòng đời chứng chỉ

| Thay đổi | Điều thực sự thay đổi | Điều không được mặc nhiên suy ra |
|---|---|---|
| Renewal hoặc cấp lại chứng chỉ | Có chứng chỉ mới với định danh và thời hạn tương ứng | Khóa riêng đã thay hoặc tiến trình đã nạp bản mới |
| Key rotation | Có cặp khóa mới và chứng chỉ ràng buộc khóa công khai mới | Mọi bản sao khóa cũ đã bị vô hiệu hóa |
| Leaf certificate rotation | Đổi chứng chỉ của endpoint hoặc workload | Cần thay mọi trust anchor |
| Intermediate CA rotation | Đổi CA trung gian hoặc đường xây dựng chuỗi | Mọi client tự tải và hiểu chuỗi mới giống nhau |
| Root hoặc trust anchor migration | Thay tập nguồn tin cậy | Chỉ đổi chứng chỉ server là đủ |
| Thay cấu hình trust hoặc pinning | Đổi tập danh tính, issuer hoặc khóa được chấp nhận | Client ngoài phạm vi quản lý đã được cập nhật |
| Thu hồi chứng chỉ | Công bố hoặc áp dụng việc không còn chấp nhận chứng chỉ theo cơ chế đã chọn | Mọi peer, cache và phiên đang mở đã ngừng tin ngay |

Chứng chỉ chứa khóa công khai và thông tin được ký; khóa riêng cần được bảo vệ bằng cơ chế riêng. Chứng chỉ mới có thể được cấp cho cùng khóa hoặc cho một khóa mới tùy quy trình. Nếu mục tiêu là giảm thời gian dùng khóa hoặc khắc phục lộ khóa, đặc tả phải yêu cầu rõ khóa mới và cách ngừng dùng khóa cũ.

Không nên gộp mọi thay đổi vào một thao tác duy nhất. Chuyển CA có thể cần triển khai trust trước, trong khi thay leaf dưới cùng CA có thể không cần sửa trust store. Thay đổi trust không cần thiết còn làm tăng phạm vi và độ phức tạp của rollout.

## 3. Xuất phát từ tài sản và sơ đồ tin cậy

### 3.1. Những rủi ro cần chuyển thành yêu cầu

| Kịch bản | Tác động | Yêu cầu cần làm rõ |
|---|---|---|
| Chứng chỉ hết hạn khi đang phục vụ | Handshake mới thất bại, dịch vụ gián đoạn | Thời hạn kích hoạt, cảnh báo và ngân sách xử lý |
| Một số instance vẫn nạp bản cũ | Lỗi không ổn định theo tuyến hoặc vùng | Kiểm chứng trên từng binding và phát hiện rollout thiếu |
| Chứng chỉ mới sai danh tính hoặc mục đích | Bị từ chối hoặc xác thực sai đối tượng | Profile, tên dịch vụ, mục đích sử dụng và kiểm tra trước rollout |
| Peer chưa tin CA mới | mTLS hoặc TLS thất bại dù chứng chỉ chưa hết hạn | Thứ tự cập nhật trust và ma trận tương thích |
| Tắt xác minh để vượt lỗi | Chấp nhận sai peer hoặc kết nối không được bảo đảm | Hành vi lỗi không hạ mức bảo vệ |
| Lộ khóa cũ nhưng chỉ cấp chứng chỉ mới | Danh tính cũ có thể tiếp tục bị sử dụng | Thu hồi hoặc chặn thực sự, xử lý bản sao khóa và phiên |
| Kết nối hoặc ticket cũ tiếp tục dùng trạng thái xác thực cũ | Mục tiêu ngừng chấp nhận danh tính cũ chưa đạt | Deadline kết nối, resumption và xác minh tại peer |

### 3.2. Liệt kê từng hop

Một đường đi có thể gồm:

```text
Client → gateway kết thúc TLS → kết nối TLS hoặc mTLS tới backend
Batch client ──────────────────→ backend qua mTLS
```

Gateway và backend có các kênh riêng. Việc client nhìn thấy chứng chỉ gateway mới không chứng minh chứng chỉ backend hoặc chứng chỉ client dùng cho mTLS đã được thay.

Với mỗi hop, cần ghi bên trình chứng chỉ, bên kiểm tra, danh tính mong đợi, issuer hoặc trust anchor được phép, điểm kết thúc TLS và chủ sở hữu. Nếu mã hóa hoặc xác thực không tiếp tục qua một đoạn, đó phải là quyết định kiến trúc được mô tả rõ.

### 3.3. Phân biệt vai trò server và client

Trong TLS thông thường, client kiểm tra chứng chỉ server theo hợp đồng danh tính. Với mTLS, server còn kiểm tra chứng chỉ client và ánh xạ danh tính đó sang quyền ứng dụng.

Cùng một tiến trình có thể đóng cả hai vai trò trên các kết nối khác nhau. Cần quản lý từng binding: chứng chỉ hoặc tham chiếu khóa nào được dùng ở endpoint, cổng, SNI, listener hoặc lời gọi ra nào. Không suy ra một binding đã được cập nhật chỉ vì một binding khác của cùng tiến trình dùng bản mới.

## 4. Inventory và hợp đồng chứng chỉ

### 4.1. Inventory phục vụ thực thi

Tồn kho cần đủ dữ liệu để biết cái gì phải đổi và ai chịu trách nhiệm:

| Nhóm | Thông tin cần xác định |
|---|---|
| Phạm vi | Môi trường, dịch vụ, vùng, instance hoặc nhóm workload, binding |
| Danh tính | Tên hoặc danh tính dịch vụ được cấp, nguồn phê duyệt và peer mong đợi |
| Artifact | Fingerprint hoặc định danh chứng chỉ, issuer, serial, chuỗi được triển khai |
| Hiệu lực | `notBefore`, `notAfter`, nguồn thời gian và giới hạn sai lệch được phép |
| Khóa | Tham chiếu khóa hoặc phiên bản secret, nơi tạo và nơi có quyền sử dụng |
| Trust | Trust store, pinning, bộ client và server có liên quan |
| Vận hành | Chủ sở hữu, pipeline, cách reload, kiểm chứng, cảnh báo và khôi phục |
| Kết thúc | Khi nào ngừng trình bản cũ, ngừng chấp nhận nếu yêu cầu, vô hiệu hóa khóa và giữ bằng chứng |

Inventory không được lưu khóa riêng, token cấp chứng chỉ hoặc nội dung secret để tiện tra cứu. Tham chiếu tới nơi quản lý khóa phải đủ cho vận hành nhưng được phân quyền phù hợp.

Tập đích cần bao gồm instance đang chạy, các phiên bản cũ còn trong rolling deployment và template mà autoscaling hoặc khởi động lại sẽ sử dụng. Nếu image hoặc cấu hình khởi tạo vẫn trỏ bản cũ, một instance mới có thể làm quay lại trạng thái đã tưởng xử lý xong.

### 4.2. Profile và kiểm tra trước triển khai

Chứng chỉ mới cần được xác minh về các thuộc tính có liên quan:

- Khóa riêng đang cấu hình tương ứng với khóa công khai trong chứng chỉ.
- Danh tính, SAN và mục đích sử dụng khớp vai trò, môi trường và dịch vụ.
- Hiệu lực thời gian phù hợp tại thời điểm đưa vào sử dụng.
- Chuỗi và các ràng buộc chứng chỉ phù hợp với trust policy của peer thật.
- Bộ thuật toán và tham số phù hợp profile mật mã đã được tổ chức phê duyệt.
- Không cấp phạm vi danh tính rộng hơn nhu cầu chỉ để làm rollout dễ hơn.

Profile mật mã cần có nguồn quản trị và phiên bản. Không chép một danh sách thuật toán cố định vào mọi yêu cầu rồi bỏ qua thay đổi của môi trường và chính sách. Bài này tập trung vào vòng đời và bằng chứng thực thi, không chọn một profile chung cho mọi hệ thống.

Chuỗi trung gian cần được triển khai theo hợp đồng của các peer được hỗ trợ. Không giả định client sẽ tự tìm được thành phần chuỗi còn thiếu từ mạng. Khả năng xây dựng và kiểm tra chuỗi phải được thử với client thực tế.

### 4.3. Thời gian là điều kiện của hệ thống

Cần theo dõi đồng hồ ở nơi cấp, nơi triển khai và nơi kiểm tra. Một chứng chỉ mới có thể chưa được peer coi là có hiệu lực nếu thời gian không nhất quán.

Không sửa sự cố thời gian bằng cách bỏ kiểm tra hiệu lực. Cần xác định giới hạn sai lệch, cách phát hiện và hành vi khi không thể bảo đảm thời gian đủ tin cậy cho yêu cầu.

## 5. Tính thời hạn từ ngân sách xử lý

### 5.1. Đổi trước hạn theo một ngân sách có căn cứ

Gọi `E_old` là thời điểm hết hạn của chứng chỉ cũ, `now` là thời điểm theo nguồn được quy định. Thời gian còn lại là:

```text
remaining = E_old - now
```

Ngưỡng bắt đầu phải đủ cho toàn bộ đường xử lý, không chỉ thời gian CA ký:

```text
required_headroom = B_issue + B_precheck + B_deploy
                    + B_observe + B_recovery + B_buffer
```

Ví dụ giả định:

| Công đoạn | Ngân sách |
|---|---|
| Cấp chứng chỉ và khóa theo quy trình | 12 giờ |
| Kiểm tra trước rollout | 6 giờ |
| Triển khai toàn bộ đích | 12 giờ |
| Quan sát và xác nhận | 24 giờ |
| Xử lý triển khai lỗi hoặc khôi phục an toàn | 6 giờ |
| Dự phòng | 12 giờ |
| Tổng | 72 giờ |

Một chính sách minh họa có thể dùng leaf có hiệu lực 30 ngày và kích hoạt khi còn 10 ngày. Đây là giá trị của ví dụ, không phải chuẩn bắt buộc. Việc chọn thực tế phải căn cứ thời hạn chứng chỉ, năng lực CA, đội vận hành và các peer phụ thuộc.

Nếu peer ngoài quyền quản lý cần cập nhật trust hoặc pinning qua một chu kỳ phát hành dài, ngân sách đó phải được đưa vào kế hoạch. Không thể dùng ngân sách 72 giờ để bảo đảm một quá trình phụ thuộc đã biết cần lâu hơn.

### 5.2. Cảnh báo trước khi hết đường phục hồi

Cảnh báo phải xét chứng chỉ **đang được trình hoặc chấp nhận trong phạm vi quản lý**, không chỉ chứng chỉ mới đã được tạo. Ví dụ có thể có mốc 7 ngày, 3 ngày và 1 ngày, với người nhận và mức nâng cấp xử lý khác nhau.

Cần định nghĩa thời điểm bắt đầu và kết thúc phép đo: cấp thành công, triển khai xong và được xác nhận qua handshake là các mốc khác nhau. Một pipeline không được kết thúc thành công chỉ vì đã nhận artifact từ CA.

Khi thời gian còn lại thấp hơn ngân sách xử lý an toàn, phải có trạng thái thiếu headroom và quy trình nâng cấp xử lý. Không chờ đến khi handshake thất bại mới coi là sự cố cần chủ sở hữu.

## 6. Quy trình rotation có điều kiện chuyển bước

### 6.1. Mô hình trạng thái

Một luồng tham khảo:

```text
PLANNED → ISSUED → VALIDATED → STAGED → CANARY
                                        ↓
                     RETIRED ← VERIFIED ← ROLLOUT
```

Các lỗi ở mỗi bước phải có trạng thái và hành động riêng. `VERIFIED` nghĩa là phạm vi triển khai đã đáp ứng bằng chứng yêu cầu; `RETIRED` nghĩa là bản cũ đã được xử lý theo các tiêu chí kết thúc đã chọn, không chỉ bị xóa khỏi một thư mục cấu hình.

| Bước | Điều kiện cần có trước khi tiếp tục |
|---|---|
| PLANNED | Biết chủ sở hữu, đích, peer phụ thuộc, ngân sách và cách phục hồi |
| ISSUED | Có artifact và tham chiếu khóa hợp lệ từ nguồn được phép |
| VALIDATED | Đạt profile, danh tính, thời gian, quan hệ khóa và kiểm thử chuỗi |
| STAGED | Candidate được lưu theo phiên bản và phân quyền, chưa tự thay mọi runtime |
| CANARY | Một phần phạm vi dùng bản mới và vượt kiểm chứng kết nối, danh tính, quyền |
| ROLLOUT | Mở rộng có kiểm soát, xử lý đích lỗi và giữ cấu hình khởi tạo nhất quán |
| VERIFIED | Các đích bắt buộc được xác nhận qua runtime và kết nối theo hợp đồng |
| RETIRED | Không còn sử dụng bản cũ ngoài phạm vi cho phép; khóa, trust và phiên được xử lý theo chính sách |

### 6.2. Đưa candidate vào sử dụng nhất quán

Key reference, leaf, chuỗi trung gian và cấu hình liên quan cần tạo thành một thế hệ cấu hình nhất quán. Không để runtime đọc khóa mới cùng chứng chỉ cũ trong lúc từng file được ghi riêng lẻ.

Cần xác định cơ chế reload: theo dõi secret, gọi API quản trị, nạp cấu hình mới hoặc khởi động lại có kiểm soát. Việc file thay đổi không tự chứng minh tiến trình đã reload thành công.

Nếu reload lỗi, runtime không được tự chuyển sang chứng chỉ khác danh tính, bỏ xác minh peer hoặc dùng kênh không được bảo vệ. Giữ thế hệ cũ chỉ được phép khi nó còn hợp lệ, không bị đánh dấu không an toàn và nằm trong thời hạn dự phòng được phê duyệt.

### 6.3. Canary phải đi qua đường thật

Canary cần kiểm tra kết nối từ các nhóm peer đại diện, đúng hostname hoặc danh tính, SNI khi có, vai trò client và server, cùng đường qua proxy hoặc gateway liên quan.

Probe phải chứng minh handshake đầy đủ mới quan sát được chứng chỉ mong muốn. Một request thành công trên kết nối đã mở hoặc phiên được resume có thể không đọc chứng chỉ mới như bài thử giả định.

Không chỉ kiểm tra đường mặc định. Binding phụ, cổng quản trị, SNI khác, vùng khác hoặc một pool chưa reload có thể vẫn trình bản cũ.

### 6.4. Xác nhận toàn bộ đích

Cần đối chiếu tập đích kỳ vọng với tập đích đã có bằng chứng. Một tỷ lệ có thể là:

```text
rotation_coverage = số binding bắt buộc có bằng chứng mới hợp lệ
                    / tổng binding bắt buộc trong inventory đã xác minh
```

Bằng chứng phải có tuổi tối đa và gắn với thế hệ chứng chỉ, cấu hình, endpoint hoặc instance tương ứng. Mất dữ liệu inventory không được coi là không còn đích để trả 100%.

Probe ngẫu nhiên qua load balancer không tự chứng minh mọi backend đã đổi. Cần phương pháp quan sát từng binding hoặc cơ chế kiểm chứng tương đương có thể giải thích phạm vi bao phủ. Các instance mới xuất hiện trong lúc rollout cũng phải lấy đúng thế hệ cấu hình.

## 7. Thay CA và cập nhật trust

### 7.1. Xác định ai phải tin cái gì

Trong một đợt đổi CA, phải lập ma trận peer và các thế hệ chứng chỉ được chấp nhận. Bao gồm chiều kiểm tra chứng chỉ server và chiều kiểm tra chứng chỉ client trong mTLS.

Một thứ tự thường dùng khi CA cũ vẫn an toàn:

1. Cấp quyền tin CA hoặc chuỗi mới cho đúng các peer cần thiết.
2. Xác minh peer vẫn hoạt động với bản cũ và có thể xác thực candidate mới.
3. Chuyển endpoint hoặc workload sang chứng chỉ mới theo canary và rollout.
4. Xác minh không còn đối tượng bắt buộc phụ thuộc đường tin cũ.
5. Thu hẹp hoặc gỡ đường tin cũ theo tiêu chí đã công bố.

Thứ tự này có điều kiện: không dùng để giữ lại một CA đã bị coi là không an toàn chỉ nhằm thuận tiện vận hành. Với sự cố CA, cần kế hoạch khẩn cấp và nguồn phân phối trust mới đáng tin cậy.

### 7.2. Khoảng cùng tin hai thế hệ

Khoảng overlap hỗ trợ tương thích nhưng cũng là khoảng nhiều credential hoặc issuer có thể được chấp nhận. Cần có thời điểm bắt đầu, hạn kết thúc, phạm vi danh tính và chủ sở hữu.

Tin một CA không nên làm bỏ điều kiện danh tính, môi trường, mục đích sử dụng hoặc quyền dịch vụ. Đặc tả phải bảo đảm issuer mới không vô tình mở rộng quyền cho mọi chứng chỉ mà nó có thể cấp.

Không gỡ CA cũ chỉ dựa vào việc server chính đã đổi. Batch client, workload ít chạy, hệ thống dự phòng hoặc tác vụ định kỳ có thể vẫn dùng chứng chỉ dưới đường tin cũ.

### 7.3. Client ngoài quyền quản lý và pinning

Nếu client pin chứng chỉ hoặc khóa, candidate mới có thể không được chấp nhận dù chain phù hợp với trust store chung. Phải xác định pin đang gắn với leaf, khóa hay nguồn tin cậy nào và quy trình cập nhật thực tế.

Cần có bằng chứng client trong phạm vi bắt buộc đã được cập nhật trước khi cắt đường cũ. Client không thể cập nhật kịp phải được xử lý như một phụ thuộc của kế hoạch, không giải quyết bằng cách hướng dẫn bỏ xác minh.

Hệ thống dự phòng và image khôi phục cũng cần có trust mới. Một failover có thể đưa toàn bộ dịch vụ trở lại trust store cũ nếu chỉ cập nhật các node đang phục vụ.

## 8. mTLS và quyền của danh tính dịch vụ

### 8.1. Chứng chỉ hợp lệ chưa đủ để có quyền

mTLS xác thực credential theo chính sách của peer; ứng dụng vẫn cần ánh xạ danh tính sang quyền. Rotation không được thay đổi danh tính hoặc phạm vi quyền ngoài thay đổi được phê duyệt.

Ví dụ, client mới của dịch vụ tạo báo cáo phải tiếp tục chỉ có quyền gọi các API đã được phép. Không mở rộng sang mọi dịch vụ chỉ vì chứng chỉ mới được cấp bởi một issuer nằm trong trust store.

Yêu cầu cần xác định thuộc tính nào được dùng làm danh tính, cách issuer được ràng buộc với thuộc tính đó và profile cho vai trò client hoặc server. Không suy ra quyền chỉ từ tên hiển thị hoặc một trường tùy ý chưa được chính sách xác minh.

### 8.2. Đổi leaf dưới cùng CA

Khi CA và hợp đồng danh tính không đổi, peer có thể xác thực leaf mới mà không sửa trust anchor. Tuy nhiên, các danh sách cho phép theo fingerprint, serial hoặc pin vẫn cần được xử lý.

Cần phân biệt ba mốc:

- **Ngừng trình bản cũ:** runtime do mình quản lý không dùng nó cho handshake mới.
- **Ngừng cho phép dùng khóa cũ:** các điểm có quyền ký hoặc nạp khóa bị vô hiệu hóa theo chính sách.
- **Ngừng chấp nhận credential cũ:** peer thực sự từ chối bản cũ khi yêu cầu điều này.

Ba mốc không tự xảy ra đồng thời. Xóa secret khỏi pipeline không khiến một peer khác ngừng tin leaf còn hạn, và không tự xóa bản khóa đã được một tiến trình nạp trước đó.

### 8.3. Thu hồi phải được thực thi tại peer

Nếu dùng CRL, OCSP hoặc một chính sách chặn credential, phải xác định điểm nào kiểm tra, thông tin mới tối đa bao nhiêu tuổi, hành vi khi không lấy được trạng thái và cách kiểm thử.

Không mặc nhiên giả định mọi TLS client hoặc server đã bật kiểm tra thu hồi giống nhau. Công bố thu hồi ở nguồn mà peer không tham vấn chưa tạo ra bằng chứng peer đã ngừng chấp nhận.

Với yêu cầu từ chối một credential cụ thể, định danh chặn phải đủ rõ, chẳng hạn fingerprint hoặc kết hợp định danh issuer có thẩm quyền với serial. Chỉ tên subject hoặc tên hiển thị issuer có thể không phân biệt đúng các credential cần xử lý.

## 9. Kết nối dài và session resumption

### 9.1. Kết nối đang mở không phải handshake mới

Một kết nối đã được thiết lập có thể tiếp tục dùng trạng thái xác thực trước đó sau khi runtime đổi chứng chỉ. Rotation thường lệ cần có chính sách cho phép tồn tại, drain hoặc thiết lập lại kết nối theo deadline.

Nếu hồ sơ tham chiếu cho một hop quy định tuổi kết nối tối đa 2 giờ sau thời điểm bắt đầu kết nối, cần kiểm thử cơ chế thực thi cùng giao thức ứng dụng. Không chỉ đổi một cấu hình rồi suy rằng mọi stream dài đều tự phục hồi đúng.

Phải xác định tác động tới request đang xử lý, giao dịch, stream, retry và idempotency. Đóng kết nối không đồng nghĩa tác động nghiệp vụ đang diễn ra chưa được thực hiện.

### 9.2. Resumption có thể giữ trạng thái cũ

Kết nối dùng session cache hoặc ticket có thể đi theo đường xác thực khác với handshake đầy đủ. Phải kiểm tra hành vi cụ thể của stack được dùng, đặc biệt khi thay trust, thu hồi hoặc thay danh tính mTLS.

Yêu cầu cần quy định thời hạn, phạm vi và khả năng vô hiệu hóa trạng thái resume khi cần. Thay leaf certificate không được coi là bằng chứng rằng ticket hoặc session cũ đã bị vô hiệu hóa.

Quản lý khóa bảo vệ session ticket là một vòng đời liên quan nhưng khác với khóa riêng của leaf. Nếu mục tiêu sự cố yêu cầu kết thúc mọi trạng thái xác thực cũ, kế hoạch phải bao gồm cơ chế resume và các kết nối đang mở.

### 9.3. Tiêu chí kết thúc theo đúng mục tiêu

Với đổi thường lệ, mục tiêu có thể là mọi handshake đầy đủ mới trên đích quản lý dùng bản mới trước hạn và kết nối cũ kết thúc theo tuổi tối đa. Với lộ credential, mục tiêu có thể mạnh hơn: peer từ chối credential cũ và các trạng thái xác thực liên quan bị chấm dứt trong deadline khống chế.

Không dùng bằng chứng của mục tiêu thứ nhất để tuyên bố đã đạt mục tiêu thứ hai. Phải có bài thử cho handshake mới, kết nối cũ và resumption tương ứng với hợp đồng đã chọn.

## 10. Bảo vệ khóa, quyền tự động hóa và phục hồi

### 10.1. Quyền cấp và triển khai

Tài khoản tự động hóa chỉ được xin chứng chỉ cho danh tính, môi trường và profile thuộc phạm vi được phép. Quyền sửa template hoặc policy cấp phát cần được kiểm soát riêng với quyền kích hoạt một rotation thông thường.

Khóa riêng cần được tạo, lưu và dùng theo chính sách: quyền truy cập tối thiểu, bảo vệ khi truyền và khi lưu, hạn chế xuất nếu cơ chế hỗ trợ, cùng audit việc sử dụng hoặc thay đổi có ý nghĩa. Không đưa khóa vào log, artifact chẩn đoán hay cấu hình công khai.

Nếu bản tham chiếu yêu cầu khóa mới cho mỗi rotation, phải có bằng chứng candidate dùng khóa công khai khác và quyền dùng khóa cũ được kết thúc theo kế hoạch. Cấp lại một chứng chỉ cùng khóa không đáp ứng yêu cầu đó.

### 10.2. Lỗi trong rotation thường lệ

Một kế hoạch khôi phục cần xác định điều kiện dừng rollout, đích đã chuyển, đích chưa chuyển và cấu hình an toàn còn có thể dùng. Rollback chỉ được phép tới một thế hệ vẫn đáp ứng danh tính, thời gian, trust và trạng thái an toàn.

Không quay về chứng chỉ hết hạn, khóa đã bị coi là lộ hoặc CA đã bị loại khỏi tập tin cậy để giữ dịch vụ chạy. Cũng không khôi phục một trust bundle rộng hơn ngoài quyết định được phép.

Khi candidate sai, có thể cần cấp candidate khác thay vì quay lại bản cũ. Pipeline phải giữ đúng thế hệ, tránh kết quả của một rollout trước ghi đè trạng thái của rollout mới.

### 10.3. Rotation khi có sự cố khóa hoặc CA

Kế hoạch khẩn cấp cần xác định nguồn tin cậy để cấp và phân phối credential mới, phạm vi bị ảnh hưởng, deadline khống chế, điểm chặn credential cũ và hành vi của kết nối, ticket hoặc cache.

Không chờ hết khoảng overlap thường lệ nếu mô hình sự cố không cho phép tiếp tục tin bản cũ. Ngược lại, việc ngừng tin đột ngột có thể làm gián đoạn; tác động và cách duy trì các luồng ưu tiên phải được chuẩn bị trong thiết kế ứng phó.

Vô hiệu hóa một phiên bản secret chỉ giới hạn cơ chế truy xuất secret đó theo khả năng của hệ thống. Nó không tự chứng minh mọi bản sao khóa trong runtime, máy dự phòng hoặc nơi xuất trước đó đã mất khả năng sử dụng. Cần bằng chứng tại các điểm nạp, sử dụng và chấp nhận có liên quan.

### 10.4. Khởi động lại và phục hồi thảm họa

Node mới, failover và môi trường phục hồi phải lấy thế hệ hợp lệ đã được phê duyệt, không vô tình phục hồi credential cũ từ image hoặc backup. Cần kiểm tra cả key reference, chain, trust và chính sách quyền.

Giữ bằng chứng và metadata lịch sử không có nghĩa giữ khóa cũ luôn hoạt động. Chính sách lưu giữ khóa, khả năng khôi phục và thời điểm vô hiệu hóa hoặc hủy phải được mô tả theo nhu cầu, quyền và giới hạn của hệ thống quản lý khóa.

## 11. Monitoring, audit và bằng chứng hoàn tất

### 11.1. Quan sát cả artifact và runtime

Các chỉ số cần được định nghĩa theo dịch vụ, binding và môi trường:

- Thời gian còn lại nhỏ nhất của chứng chỉ thực sự đang phục vụ.
- Tuổi dữ liệu inventory và bằng chứng handshake gần nhất.
- Số đích kỳ vọng, đã kiểm chứng, còn bản cũ và chưa quan sát được.
- Thời gian từng bước cấp, kiểm tra, triển khai, xác nhận và kết thúc bản cũ.
- Lỗi handshake phân theo nhóm nguyên nhân phù hợp: thời gian, danh tính, trust, profile hoặc cấu hình khóa.
- Số peer hoặc binding còn phụ thuộc CA, pin hoặc credential cũ.
- Số kết nối và trạng thái resume còn thuộc thế hệ cần kết thúc, nếu mục tiêu yêu cầu quan sát chúng.

Trong hồ sơ minh họa, có thể probe mỗi binding tối đa cách nhau 5 phút và không dùng bằng chứng cũ hơn 10 phút để kết luận rollout đã hoàn tất. Phải chứng minh phép đo đi qua đúng đường và không chỉ đọc file cấu hình.

Nếu endpoint có nhiều certificate slot hoặc chọn chuỗi khác nhau theo nhóm client, cần kiểm thử các lựa chọn được hỗ trợ. Một probe dùng một kiểu client không tự quan sát mọi lựa chọn runtime có thể trình.

### 11.2. Chưa quan sát được khác với đã đạt

Binding mất kết nối, thiếu inventory hoặc không đủ mẫu phải có trạng thái chưa xác định. Không loại đích lỗi khỏi mẫu số chỉ để tăng tỷ lệ hoàn tất.

Khi một đích được loại khỏi phạm vi, cần bằng chứng đã ngừng phục vụ hoặc một thay đổi inventory được phê duyệt. Một pod biến mất khỏi màn hình không tự chứng minh không còn template hoặc đường failover có thể tạo lại bản cũ.

### 11.3. Audit và báo cáo

Audit cần ghi chủ thể hoặc tài khoản tự động hóa, danh tính được xin cấp, profile, chứng chỉ và key reference trước sau, trust policy, đích, thời điểm, kết quả và lý do can thiệp.

Không ghi khóa riêng, mã truy cập CA, token secret manager hoặc session ticket vào bằng chứng dùng chung. Fingerprint và thông tin chứng chỉ cũng cần được phân phối theo nhu cầu vì có thể mô tả cấu trúc nội bộ.

Báo cáo hoàn tất phải nêu rõ đã đạt điều gì: bản mới đã được cấp, mọi đích đã trình bản mới, credential cũ đã bị peer chặn hay khóa cũ đã kết thúc quyền dùng. Các bằng chứng này không được thay thế lẫn nhau.

## 12. Bộ yêu cầu bảo mật minh họa

Bộ yêu cầu sau dùng các tham số minh họa của bài. Ngoài rotation thường lệ, giả sử quy trình sự cố đặt deadline khống chế 15 phút kể từ `T0`, là thời điểm nguồn quản lý sự cố có thẩm quyền tuyên bố credential cũ không còn được tin. Deadline này áp dụng trong phạm vi peer được hệ thống quản lý và phải được kiểm chứng trước khi dùng làm cam kết.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| CR-01 | Mọi binding bắt buộc phải có danh tính, profile, thời hạn, key reference, trust phụ thuộc và chủ sở hữu; inventory phải bao phủ cả template và failover | Đối chiếu cấu hình, runtime, inventory và đích phục hồi |
| CR-02 | Candidate phải vượt kiểm tra quan hệ khóa, danh tính, mục đích, hiệu lực, chuỗi và profile trước rollout | Candidate sai từng thuộc tính bị từ chối trước phát hành |
| CR-03 | Trong hồ sơ tham chiếu, mỗi rotation phải dùng khóa mới; khóa và quyền cấp chỉ thuộc phạm vi dịch vụ, môi trường, profile được phép | Đối chiếu khóa công khai trước sau và kiểm thử quyền cấp, quyền dùng |
| CR-04 | Với leaf 30 ngày của ví dụ, kích hoạt khi còn 10 ngày, theo ngân sách 72 giờ đã phân bổ; thiếu headroom phải được nâng cấp xử lý | Diễn tập trigger, cấp lỗi và cảnh báo ở các mốc đã định |
| CR-05 | Key reference, leaf, chain và cấu hình liên quan phải được triển khai theo thế hệ nhất quán; mọi template khởi tạo phải dùng thế hệ được phê duyệt | Reload, restart, autoscaling và lỗi cập nhật một phần |
| CR-06 | Không đánh dấu rollout hoàn tất nếu một binding bắt buộc chưa được xác minh bằng kết nối phù hợp; probe cách nhau tối đa 5 phút, bằng chứng kết luận không cũ quá 10 phút | Probe đầy đủ mới, đúng danh tính và đối chiếu tập đích |
| CR-07 | Khi đổi CA trong điều kiện CA cũ còn an toàn, trust mới phải được xác nhận trước khi chuyển leaf; gỡ trust cũ cần bằng chứng hết phụ thuộc theo phạm vi | Ma trận peer, canary và client ít hoạt động |
| CR-08 | Rotation mTLS phải giữ đúng ánh xạ danh tính và quyền; mở rộng tập issuer không được tự mở rộng quyền dịch vụ | Chứng chỉ mới hợp lệ vẫn bị từ chối ở API ngoài quyền |
| CR-09 | Kết nối dài và resumption phải có chính sách riêng; trong hop tham chiếu có tuổi kết nối tối đa 2 giờ, phải kiểm chứng drain và trạng thái resume theo hợp đồng | Kết nối tạo trước rollout và các lần kết nối lại có resume |
| CR-10 | Mọi nhánh lỗi và rollback phải giữ xác minh peer, danh tính và chính sách kênh truyền; không dùng lại credential đã bị coi là không an toàn | Candidate lỗi, hết hạn, sai trust và rollback bị chặn |
| CR-11 | Trong kịch bản sự cố tham chiếu, sau `T0 + 15 phút`, peer quản lý không được chấp nhận credential bị chặn; kết nối và trạng thái resume liên quan phải được xử lý để không tiếp tục quyền xác thực đã bị loại | Thử credential cũ, ticket cũ và kết nối đang mở sau deadline |
| CR-12 | Audit phải liên kết thay đổi với binding, thế hệ và bằng chứng runtime; dữ liệu secret không được xuất vào báo cáo hoặc log ngoài chính sách | Đối chiếu một rotation xuyên pipeline và kiểm tra dữ liệu bằng chứng |
| CR-13 | Restart, failover hoặc phục hồi không được tái đưa thế hệ cũ đã kết thúc vào sử dụng; quyền dùng khóa và trust phải theo trạng thái hiện hành | Khởi động từ image hoặc backup cũ trong môi trường thử nghiệm |

CR-09 mô tả giới hạn thường lệ của hop tham chiếu. CR-11 là yêu cầu mạnh hơn khi có sự cố và không được trì hoãn đến hết tuổi kết nối 2 giờ. Phải chọn hành vi khống chế thực sự đáp ứng deadline, bao gồm việc từ chối hoặc ngừng phục vụ một đường không còn có thể xác thực an toàn.

Sản phẩm phải chốt thêm thời hạn session, hành vi thu hồi, điều kiện CA lỗi và cách xử lý từng nhóm client. Những tham số chưa chốt phải được ghi là phần cần hoàn thiện của đặc tả triển khai, không ẩn trong các cụm như “rotate định kỳ” hoặc “không downtime”.

## 13. Tiêu chí nghiệm thu và diễn tập

### 13.1. Bản mới được dùng ở mọi binding

```gherkin
Given candidate đã được phê duyệt cho thế hệ mới
And inventory xác định đầy đủ các binding bắt buộc
When rollout được báo hoàn tất
Then mỗi binding có bằng chứng hợp lệ trong giới hạn tuổi đã định
And handshake đầy đủ mới nhận đúng danh tính, chain và chứng chỉ mong đợi
And không có binding đang phục vụ còn trình thế hệ cũ ngoài chính sách
And instance mới khởi tạo cũng dùng thế hệ mới
```

Probe phải xác minh peer như client thực tế. Nếu kết nối trực tiếp node để bao phủ từng đích, vẫn phải dùng tên và SNI đúng hợp đồng, không bỏ kiểm tra danh tính chỉ vì địa chỉ kết nối khác.

Thêm trường hợp một instance không reload, một SNI phụ còn bản cũ và một template autoscaling chưa đổi. Rollout không được thành công chỉ vì các request ngẫu nhiên qua load balancer đều tình cờ tới đích đã đổi.

### 13.2. Candidate không hợp lệ

Thử chứng chỉ hết hạn, chưa có hiệu lực, sai danh tính, sai mục đích, khóa không tương ứng và chuỗi không dẫn tới trust được phép. Chúng không được đưa vào phục vụ như candidate hợp lệ, và đường lỗi không được tắt xác minh để tiếp tục.

Kiểm thử chuỗi trung gian với các nhóm client có cache hoặc khả năng tìm chuỗi khác nhau. Một client đã có sẵn intermediate không được dùng làm bằng chứng duy nhất rằng candidate đủ tương thích với toàn bộ client bắt buộc.

Các tình huống thời gian nên dùng đồng hồ hoặc môi trường kiểm thử được kiểm soát. Đối chiếu mốc thời gian thực mà peer sử dụng, không chỉ mốc trong dashboard cấp chứng chỉ.

### 13.3. Ma trận chuyển trust

Trong một kịch bản đổi CA có đường tin cũ và mới được xác định rõ, lập bảng cho từng nhóm peer:

| Credential trình | Trạng thái trust của peer | Kết quả cần xác minh |
|---|---|---|
| Bản cũ | Trust cũ, còn trong chính sách | Hoạt động như baseline hợp lệ |
| Candidate mới | Chưa có trust cần thiết | Không được vượt kiểm tra chỉ vì đang rollout |
| Bản cũ hoặc mới | Trust chuyển tiếp được phê duyệt | Được chấp nhận đúng danh tính, profile và thời gian |
| Bản mới | Trust cuối đã chốt | Hoạt động với quyền dự kiến |
| Credential cũ đã bị chính sách cuối loại | Sau thời điểm ngừng chấp nhận | Bị từ chối tại điểm cưỡng chế tương ứng |

Đối chiếu batch client, hệ thống dự phòng và client có pinning. Nếu có nhóm chưa sẵn sàng, phải thấy trạng thái chưa hoàn tất và ảnh hưởng, không tự bỏ nhóm đó khỏi inventory.

### 13.4. mTLS không làm đổi quyền

Cho một client chuyển sang chứng chỉ mới đúng danh tính. Nó phải tiếp tục truy cập API thuộc quyền và vẫn bị từ chối ở API ngoài quyền. Thử credential của danh tính hoặc môi trường khác dù issuer nằm trong tập tin cậy.

Kiểm tra cả hai chiều cần thiết: client xác minh server mới và server xác minh client mới. Thành công ở một chiều chưa chứng minh toàn bộ hop mTLS đạt yêu cầu.

### 13.5. Kết nối cũ và resumption

Mở kết nối trước rollout, đổi chứng chỉ rồi thử request trên kết nối đó. Kết quả phải phù hợp chính sách tuổi kết nối và danh tính của ứng dụng, không được diễn giải như một phép thử đã quan sát leaf mới.

Tạo session hoặc ticket trước thay đổi, sau đó thử resume và handshake đầy đủ mới riêng biệt. Với cơ chế bị tắt resumption, kiểm chứng rằng đường đó thực sự không được sử dụng; với cơ chế có resumption, kiểm chứng deadline và thu hồi như đã đặc tả.

Trong diễn tập sự cố, sau deadline 15 phút của ví dụ, thử credential bị chặn, trạng thái resume cũ và kết nối còn mở. Việc chỉ nhìn thấy leaf mới ở một handshake đầy đủ không đủ để đánh dấu đã khống chế.

### 13.6. Lỗi cấp, lỗi rollout và rollback

Các tình huống cần có:

1. CA hoặc nơi quản lý khóa không khả dụng khi trigger chạy.
2. Candidate có khóa và chain không nhất quán.
3. Một phần instance reload thất bại trong khi phần khác đã chuyển.
4. Inventory hoặc probe mất dữ liệu, làm thiếu bằng chứng phạm vi.
5. Bản cũ còn hạn nhưng đã bị đánh dấu không an toàn.
6. Kết quả rollout cũ đến muộn sau khi candidate khác đã được chọn.

Xác minh pipeline dừng, cảnh báo, phục hồi hoặc cấp candidate khác đúng chính sách. Không có trường hợp nào được “sửa” bằng HTTP không được phép, bỏ xác minh hoặc quay về credential đã bị loại.

Đối chiếu ngân sách 72 giờ và các mốc 7 ngày, 3 ngày, 1 ngày của ví dụ bằng cách điều khiển thời gian trong môi trường thử nghiệm. Cảnh báo phải tới đúng chủ sở hữu, kèm chứng chỉ và binding đang gây thiếu headroom.

### 13.7. Khởi động lại và failover

Sau khi rotation được xác nhận và bản cũ đã kết thúc, khởi tạo một instance mới, thực hiện failover và phục hồi cấu hình từ bản sao cũ trong môi trường thử nghiệm. Hệ thống phải hội tụ về thế hệ được phê duyệt hiện tại hoặc từ chối phục vụ khi không có credential hợp lệ.

Không được tái kích hoạt khóa, trust hoặc leaf cũ chỉ vì artifact vẫn tồn tại trong backup. Audit cần cho biết thế hệ được nạp và kết quả handshake sau phục hồi.

## 14. Truy vết tới kiến trúc và vòng đời phát triển

| Rủi ro | Yêu cầu liên quan | Điểm thực thi | Bằng chứng chính |
|---|---|---|---|
| Hết hạn trước khi thay xong | CR-01, CR-04, CR-06 | Inventory, pipeline và monitoring | Headroom, mốc xử lý và chứng chỉ đang phục vụ |
| Có file mới nhưng runtime còn cũ | CR-05, CR-06, CR-13 | Reload, binding và template triển khai | Handshake đầy đủ theo từng đích |
| Peer chưa tin hoặc chấp nhận sai danh tính | CR-02, CR-07, CR-08 | Trust store và ánh xạ quyền | Ma trận tương thích và kiểm thử quyền mTLS |
| Khóa cũ tiếp tục bị dùng sau sự cố | CR-03, CR-09, CR-11 | Nơi dùng khóa, điểm xác minh và trạng thái phiên | Thử credential cũ, session cũ và kết nối cũ |
| Rollback hạ mức bảo mật | CR-10, CR-12 | Điều phối rollout và quyền quản trị | Đường lỗi, tiêu chí rollback và audit |
| Phục hồi làm quay lại credential cũ | CR-05, CR-13 | Image, backup và nguồn cấu hình có thẩm quyền | Restart, autoscaling và failover |

Ở giai đoạn phân tích, liệt kê luồng liên lạc, tài sản, chủ thể và hậu quả nếu xác thực sai hoặc kênh truyền gián đoạn. Chốt ai quản lý mỗi peer và yêu cầu ngừng sử dụng, ngừng chấp nhận riêng biệt.

Ở giai đoạn thiết kế, xác định profile, thời hạn, ngân sách, pipeline, trust transition, mTLS và vòng đời kết nối. Các mục tiêu phải phù hợp khả năng thực thi của stack, CA, key store và hệ thống triển khai.

Ở giai đoạn triển khai và nghiệm thu, gắn mã yêu cầu với cấu hình và diễn tập. Đối chiếu artifact với handshake thực tế và bằng chứng của từng nhóm peer, bao gồm đường phủ định và lỗi.

Ở giai đoạn vận hành, duy trì inventory, cảnh báo, audit và diễn tập sự cố. Khi đổi client, proxy, thư viện TLS, CA, cơ chế pinning hoặc chính sách session, đánh giá lại khả năng rotation và thu hồi thay vì giữ nguyên giả định cũ.

## 15. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Khoảng hở | Cách làm rõ |
|---|---|---|
| “Gia hạn xong là rotation xong” | Runtime và một số binding có thể còn cũ | Bằng chứng handshake theo tập đích và thế hệ |
| “Đổi chứng chỉ nghĩa là đổi khóa” | Có thể tái sử dụng cùng khóa | Yêu cầu và kiểm chứng khóa mới khi mục tiêu cần |
| “Đã thêm CA mới nên xóa CA cũ ngay” | Peer hoặc tác vụ ít chạy chưa chuyển | Ma trận phụ thuộc và tiêu chí gỡ trust |
| “Chứng chỉ hợp lệ thì có mọi quyền” | mTLS identity bị ánh xạ quá rộng | Giữ quyền dịch vụ độc lập với việc trust issuer |
| “Xóa secret là thu hồi chứng chỉ” | Khóa đã nạp, bản sao và peer trust vẫn tồn tại | Kiểm soát nơi dùng và nơi chấp nhận |
| “Một request thành công đã kiểm tra bản mới” | Có thể dùng kết nối cũ hoặc resume | Tách probe đầy đủ mới, kết nối cũ và resumption |
| “Rollback về bản cũ bằng mọi giá” | Có thể tái dùng khóa lộ hoặc chứng chỉ hết hạn | Điều kiện an toàn bắt buộc của phương án khôi phục |
| “Hết hạn thì kết nối cũ tự dừng” | Trạng thái xác thực đang mở có vòng đời riêng | Deadline kết nối và cơ chế kết thúc có kiểm thử |
| “Không có telemetry nghĩa là không còn đích lỗi” | Mất bằng chứng bị coi là thành công | Trạng thái chưa xác định và mẫu số inventory có thẩm quyền |
| “Thường lệ và sự cố dùng cùng overlap” | Credential không an toàn bị giữ quá lâu | Chính sách khẩn cấp và deadline khống chế riêng |

## 16. Bài tập tự kiểm tra

Một hệ thống cấp leaf mới mỗi tháng, ghi đè file rồi báo thành công. Gateway có ba instance nhưng chỉ probe ngẫu nhiên một URL. Backend dùng mTLS, batch client pin khóa cũ và có kết nối dài. Khi một khóa bị nghi lộ, đội vận hành xóa phiên bản secret nhưng cho phép rollback về chứng chỉ cũ nếu handshake lỗi. Image dự phòng vẫn chứa cấu hình ban đầu.

Hãy thực hiện các việc sau:

1. Vẽ các hop, vai trò trình chứng chỉ và vai trò kiểm tra ở mỗi hop.
2. Viết inventory tối thiểu và tiêu chí một binding đã chuyển thành công.
3. Tách yêu cầu đổi leaf, đổi khóa, cập nhật pin và thay trust.
4. Đặc tả headroom, khoảng overlap và điều kiện kết thúc bản cũ.
5. Viết tiêu chí cho handshake đầy đủ mới, resumption và kết nối dài.
6. Thiết kế diễn tập lộ khóa với deadline và bằng chứng peer đã từ chối credential cũ.
7. Viết yêu cầu rollback, failover và audit để thế hệ cũ không tự quay lại.

Một lời giải đầy đủ cần chứng minh danh tính đúng và kênh truyền đạt chính sách trong cả triển khai thường lệ lẫn tình huống sự cố. Certificate rotation có thể kiểm chứng khi việc cấp, nạp, sử dụng, chấp nhận và kết thúc credential đều có phạm vi, thời hạn, chủ sở hữu và bằng chứng riêng.
