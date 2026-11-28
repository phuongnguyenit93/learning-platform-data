# Cloud break-glass

Một tổ chức đưa toàn bộ quyền quản trị cloud qua đăng nhập liên kết và cổng PAM. Người quản trị dùng danh tính cá nhân, xác thực mạnh và được cấp quyền theo thời hạn. Đây là đường truy cập vận hành bình thường.

Nhưng nếu cấu hình liên kết danh tính bị thay đổi sai, nhà cung cấp danh tính không hoạt động hoặc chính cổng PAM không thể cấp phiên, người trực có thể không đăng nhập được để sửa lỗi. Khi đó, hệ thống cần một đường truy cập khẩn cấp đã được thiết kế và kiểm chứng từ trước.

Cloud break-glass là cơ chế cho phép người được ủy quyền khôi phục quyền kiểm soát cloud trong những tình huống đường truy cập bình thường không đáp ứng được. Nó không phải một tài khoản quản trị dùng chung để “vào cho nhanh”, cũng không phải cơ chế bỏ qua mọi kiểm soát khi có sự cố.

Bài học trình bày cách đưa break-glass vào Privileged Access Management (PAM) trên cloud: xác định tình huống kích hoạt, xây dựng đường truy cập đủ độc lập, giới hạn quyền, bảo quản credential, lưu bằng chứng và khôi phục trạng thái kiểm soát sau sử dụng. Nội dung sử dụng mô hình trung lập nhà cung cấp; ví dụ chính sách là mô tả thiết kế, không phải cấu hình chạy trực tiếp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt break-glass với cấp quyền JIT, tài khoản quản trị thông thường và quy trình phục hồi tài khoản.
- Xác định các phụ thuộc có thể làm đường khẩn cấp mất tác dụng.
- Thiết kế danh tính và phạm vi quyền phục hồi theo cấp cloud.
- Tổ chức bảo quản credential và phương tiện xác thực mà vẫn có thể kích hoạt khi hệ thống chính gặp lỗi.
- Vận hành một phiên khẩn cấp có người chịu trách nhiệm, thời hạn và bằng chứng.
- Kiểm chứng thu hồi phiên, luân chuyển credential phù hợp và diễn tập định kỳ theo rủi ro.

## 2. Break-glass giải quyết vấn đề gì?

Đường quản trị bình thường có thể phụ thuộc vào nhiều thành phần:

```text
Người quản trị
     |
     v
Nhà cung cấp danh tính / SSO
     |
     v
PAM, phê duyệt hoặc cấp quyền tạm thời
     |
     v
Liên kết và phân quyền trên cloud
     |
     v
Control plane và tài nguyên cloud
```

Một lỗi ở bất kỳ thành phần quan trọng nào cũng có thể khiến người có trách nhiệm không thực hiện được thao tác phục hồi.

Ví dụ:

- Thay đổi cấu hình federation làm mọi quản trị viên bị từ chối.
- Một policy hoặc ánh xạ nhóm cấp sai quyền.
- Dịch vụ PAM hoặc kho bí mật không thể truy cập.
- Sự cố mạng làm người trực không đến được cổng truy cập bình thường.
- Nhà cung cấp danh tính bị xâm nhập nên không còn được coi là nguồn xác thực đáng tin cho thao tác phục hồi.
- Một tài khoản hoặc phạm vi quản trị cloud bị mất người quản lý hợp lệ.

Break-glass cung cấp một phương án được chuẩn bị cho các tình huống xác định. Nó phải có điểm vào, người giữ quyền, điều kiện kích hoạt, phạm vi hành động và cách kết thúc.

Không có đường break-glass nào tự bảo đảm truy cập được khi toàn bộ control plane của nhà cung cấp không hoạt động. Cần phân biệt lỗi đường truy cập của tổ chức với lỗi dịch vụ cloud mà tổ chức không thể tự khắc phục bằng một credential khác.

## 3. Phân biệt các cơ chế dễ bị nhầm

| Cơ chế | Mục đích | Quan hệ với break-glass |
| --- | --- | --- |
| JIT thông thường | Cấp quyền ngắn hạn cho công việc đã được quản trị | Có thể không hoạt động nếu thành phần cấp quyền đang hỏng |
| JEA / chức năng quản trị vừa đủ | Hạn chế thao tác theo nhiệm vụ | Nên áp dụng cho đường khẩn cấp trong phạm vi khả thi |
| Tài khoản vận hành có quyền thường trực | Phục vụ công việc hằng ngày | Không nên được đổi tên thành break-glass để hợp thức hóa quyền rộng |
| Danh tính truy cập cloud khẩn cấp | Phục hồi khi đường bình thường không dùng được hoặc không đáng tin | Là một thành phần của thiết kế break-glass |
| Phục hồi tài khoản | Lấy lại khả năng kiểm soát danh tính, chủ sở hữu hoặc phương tiện xác thực | Có thể cần hỗ trợ của nhà cung cấp và không đồng nghĩa với một phiên break-glass |
| Khôi phục dữ liệu / dịch vụ | Đưa ứng dụng trở lại trạng thái hoạt động | Break-glass chỉ hỗ trợ quyền thực hiện khi phù hợp |

Một tài khoản có quyền cao nhưng không ai biết credential ở đâu không phải đường phục hồi đáng tin. Một runbook đầy đủ nhưng phụ thuộc vào chính SSO đang mất cũng không phải phương án khả dụng cho tình huống đó.

## 4. Xác định điều kiện kích hoạt

Điều kiện kích hoạt phải gắn với nhu cầu phục hồi cụ thể, không chỉ câu “hệ thống đang có sự cố”.

Một chính sách có thể cho phép kích hoạt khi:

1. Đường truy cập quản trị thông thường không hoạt động và cần thao tác khẩn cấp để phục hồi.
2. Đường truy cập thông thường bị nghi xâm nhập và cần sử dụng một miền tin cậy khác.
3. Người có thẩm quyền xác nhận nhiệm vụ không thể chờ quy trình bình thường vì tác động vận hành đã xác định.
4. Phạm vi phục hồi và người thực hiện đã được ghi nhận theo quy trình ứng phó.

Các tình huống sau thường cần đi qua quy trình thông thường:

- Quên xin quyền trước một đợt bảo trì đã có lịch.
- Cần bỏ qua phê duyệt vì thao tác gấp nhưng không có sự cố đường truy cập.
- Muốn đọc dữ liệu production ngoài nhiệm vụ.
- Một pipeline triển khai muốn sử dụng credential khẩn cấp thay cho danh tính workload.
- Cần cấp quyền quản trị lâu dài cho người mới.

Nên chuẩn bị cách khai báo sự cố khi hệ thống ticket hoặc kênh phê duyệt chính không dùng được. Hồ sơ tạm thời có thể được tạo bằng kênh thay thế đã quy định rồi đối chiếu lại sau. Kênh thay thế phải xác minh được người yêu cầu và người cho phép; một tin nhắn không xác thực không nên trở thành lệnh cấp quyền.

## 5. Mô hình lỗi và mức độc lập cần có

Tính độc lập phải được đánh giá theo từng tình huống lỗi.

| Thành phần gặp vấn đề | Câu hỏi đối với đường khẩn cấp |
| --- | --- |
| SSO / nhà cung cấp danh tính | Có thể xác thực mà không phụ thuộc vào liên kết đang lỗi không? |
| PAM / dịch vụ cấp phiên | Có thể lấy credential và vào cloud khi không qua PAM này không? |
| Kho bí mật | Credential có bản bảo quản thay thế phù hợp hay lại chỉ nằm trong kho đó? |
| Mạng doanh nghiệp | Có đường kết nối được phép, thiết bị và thông tin truy cập khả dụng không? |
| Email hoặc hệ thống liên lạc | Phương tiện phục hồi và xác nhận người có thẩm quyền còn hoạt động không? |
| Chính sách cloud | Principal khẩn cấp có quyền hiệu lực cho thao tác phục hồi không? |
| Control plane cloud | Các API cần thiết có hoạt động không; khi không hoạt động phải chuyển sang phương án nào? |
| Tài khoản quản trị bị xâm nhập | Kẻ tấn công có thể vô hiệu hóa hoặc chiếm cả đường khẩn cấp không? |

### 5.1. Độc lập không chỉ là có thêm một username

Hai danh tính có username khác nhau nhưng cùng phụ thuộc vào một IdP, một thiết bị xác thực bị mất hoặc một kho credential có thể cùng thất bại.

Các phụ thuộc thường bị bỏ sót gồm:

- Runbook chỉ đọc được sau khi đăng nhập SSO.
- Password của tài khoản khẩn cấp nằm trong vault chỉ truy cập qua SSO.
- Recovery email nằm trong cùng tenant đang mất quyền quản trị.
- MFA yêu cầu một thiết bị hoặc một người duy nhất.
- Hệ thống cấp quyền khẩn cấp chạy trong cùng phạm vi đang bị policy chặn.
- Mọi người giữ credential đều ở cùng một địa điểm hoặc cùng ca không khả dụng.
- Thiết bị truy cập cần dịch vụ quản lý đang gặp sự cố để khởi động hoặc nhận cấu hình.

Không cần làm mọi thứ độc lập với mọi thứ. Cần chỉ ra những lỗi nào phương án được thiết kế để chịu được và những phụ thuộc nào vẫn còn.

### 5.2. Mô tả bằng chuỗi điều kiện

Một cách kiểm tra thiết kế là viết đầy đủ:

```text
Muốn sửa federation:
  cần đăng nhập cloud bằng danh tính khẩn cấp
    cần credential và phương tiện xác thực
      cần mở kho bảo quản
        cần đăng nhập SSO đang bị lỗi
```

Chuỗi này cho thấy một vòng phụ thuộc. Cần đổi cách bảo quản hoặc điểm xác thực để đường phục hồi thực sự đáp ứng tình huống.

Nếu vấn đề là policy cloud chặn cả principal khẩn cấp, việc thêm một phương thức MFA khác không giải quyết được. Phân tích đúng lớp lỗi giúp tránh chuẩn bị nhiều credential nhưng không có quyền phục hồi thực tế.

## 6. Thiết kế danh tính khẩn cấp trên cloud

### 6.1. Phạm vi quản trị phải rõ ràng

Cloud có thể có nhiều cấp: tổ chức, tenant, tài khoản, subscription, project và tài nguyên. Tên gọi cũng như cơ chế quyền khác nhau theo nền tảng.

Cần xác định cấp nào cần phục hồi. Một danh tính sửa quyền ở project không mặc nhiên sửa được liên kết danh tính ở cấp tổ chức. Ngược lại, dùng quyền toàn tổ chức để xử lý một sự cố nhỏ ở project có thể tạo phạm vi tác động quá lớn.

Có thể thiết kế các lớp phục hồi:

- Phục hồi đường đăng nhập và phân quyền ở cấp quản trị chung.
- Phục hồi quyền vận hành trong một tài khoản hoặc project quan trọng.
- Phục hồi tài nguyên cụ thể bằng thao tác hẹp.
- Phục hồi quyền sở hữu danh tính qua quy trình riêng nếu mọi điểm đăng nhập đã mất.

Không nhất thiết mọi lớp phải có credential thường trực riêng. Quyết định phụ thuộc tình huống lỗi, khả năng cấp quyền và thời gian phục hồi yêu cầu.

### 6.2. Danh tính cục bộ hoặc cơ chế khẩn cấp được hỗ trợ

Một đường khẩn cấp có thể sử dụng danh tính được cloud xác thực trực tiếp hoặc cơ chế khẩn cấp khác mà nền tảng hỗ trợ. Điểm cần chứng minh là nó không phụ thuộc vào thành phần đang được dự phòng.

Không tự giả định một kiểu tài khoản luôn bỏ qua federation, điều kiện truy cập hay policy cấp cao. Phải kiểm tra cấu hình và quyền hiệu lực của nền tảng đang dùng.

Danh tính chủ sở hữu cao nhất, root hoặc tương đương cần được quản trị theo khả năng và hạn chế riêng của nhà cung cấp. Không dùng danh tính đó cho mọi tác vụ khẩn cấp nếu có principal phục hồi hẹp hơn đủ khả năng thực hiện nhiệm vụ.

### 6.3. Truy vết người sử dụng

Ưu tiên thiết kế cho phép quy trách nhiệm tới người thực hiện. Nếu bắt buộc sử dụng một danh tính khẩn cấp được nhiều người lưu giữ, cần:

- Chỉ định rõ người checkout và người đang sử dụng.
- Ghi thời điểm bàn giao, mục đích và phạm vi.
- Hạn chế sử dụng đồng thời nếu điều đó làm mất khả năng quy trách nhiệm.
- Liên kết phiên đăng nhập và thao tác cloud với hồ sơ sự cố.
- Đối chiếu hoạt động sau sử dụng.

Một principal dùng chung không trở thành danh tính cá nhân chỉ vì đã ghi tên người trong phần mô tả ticket. Đó là một giới hạn phải được xử lý bằng cơ chế bàn giao, ghi nhận và thiết kế phiên phù hợp.

### 6.4. Tách đường con người khỏi workload

Ứng dụng, agent và pipeline không nên chạy bằng credential break-glass của con người.

Workload cần danh tính riêng và cơ chế phục hồi riêng. Nếu một quy trình khôi phục cần tự động hóa, phải định nghĩa principal, phạm vi, điều kiện kích hoạt và audit cho tự động hóa đó. Không đưa password khẩn cấp vào biến môi trường của pipeline để tiện gọi lại.

## 7. Giới hạn quyền mà vẫn sửa được sự cố

Least privilege trên đường khẩn cấp cần được hiểu theo **nhiệm vụ phục hồi đã dự kiến**, không phải theo toàn bộ công việc người quản trị có thể muốn làm.

Ví dụ, để phục hồi federation, một bộ quyền có thể cần:

- Đọc cấu hình liên kết danh tính hiện tại.
- Khôi phục một cấu hình đã được xác nhận.
- Sửa ánh xạ nhóm hoặc trust cần thiết.
- Cấp lại quyền vận hành cho principal được chỉ định.
- Đọc audit liên quan để xác minh kết quả.

Nhiệm vụ đó không tự yêu cầu quyền xuất dữ liệu khách hàng hoặc xóa backup ứng dụng.

### 7.1. Đường phục hồi hẹp và đường quyền cao cuối cùng

Một thiết kế có thể có đường phục hồi chức năng hẹp cho những lỗi thường gặp và một đường quyền cao hơn cho tình huống không thể xử lý bằng quyền hẹp.

Hai đường cần điều kiện kích hoạt và kiểm soát khác nhau. Không để đường quyền cao trở thành lựa chọn mặc định chỉ vì dễ vận hành.

Nếu một principal có thể sửa IAM để tự cấp quyền rộng hơn, đó vẫn là khả năng nâng quyền đáng kể. Dù policy ban đầu không có quyền đọc dữ liệu, phải đánh giá khả năng tự cấp hoặc ủy quyền quyền đọc.

### 7.2. JIT có một điểm khởi đầu

Một thiết kế “mọi quyền chỉ được cấp khi khẩn cấp” cần trả lời: thành phần nào sẽ cấp quyền khi thành phần IAM hoặc PAM liên quan đang lỗi?

Có thể phải giữ một quyền phục hồi thường trực hoặc một khả năng kích hoạt được chuẩn bị từ trước. Khi đó, bảo vệ khả năng này bằng phạm vi quyền, bảo quản credential, phương tiện xác thực, cảnh báo và diễn tập.

Không mô tả một tài khoản quyền cao thường trực là “không có quyền thường trực” chỉ vì ít được dùng.

### 7.3. Policy khẩn cấp không phải bỏ qua mọi ranh giới

Một principal khẩn cấp không tự vượt mọi deny, policy tổ chức, khóa tài nguyên hay điều kiện truy cập. Khả năng thực tế tùy nền tảng và loại ràng buộc.

Cần kiểm tra chính những thao tác phục hồi cần thiết trong cấu hình đích. Một phép thử “đăng nhập thành công” chưa chứng minh principal có thể sửa policy gây khóa người quản trị.

Nếu tổ chức có cơ chế ngăn thay đổi các quyền phục hồi quan trọng, cần kiểm tra nó không ngăn luôn hành động phục hồi được phép. Ngược lại, tránh tạo ngoại lệ quá rộng khiến một credential bị lộ trở thành đường vượt toàn bộ kiểm soát.

## 8. Bảo quản credential và phương tiện xác thực

### 8.1. Xác thực mạnh vẫn áp dụng cho đường khẩn cấp

Khẩn cấp không phải lý do mặc định để chỉ dùng password.

Lựa chọn phương tiện xác thực phải phù hợp cơ chế mà cloud hỗ trợ và mô hình lỗi cần chịu đựng. Có thể cần phương tiện xác thực độc lập với điện thoại doanh nghiệp, IdP hoặc mạng đang được dự phòng.

Thiết kế cần tính đến thiết bị dự phòng, người giữ, địa điểm bảo quản và quy trình thay thế khi hỏng hoặc mất. Không vô hiệu MFA đại trà để tránh bị khóa trong một tình huống chưa được phân tích.

### 8.2. Bảo quản có kiểm soát và khả dụng

Có thể sử dụng kho bảo quản độc lập phù hợp, vật mang được mã hóa hoặc phương thức niêm phong theo quy trình của tổ chức. Bất kỳ lựa chọn nào cũng cần trả lời:

- Ai được mở, và bằng chứng mở được ghi ở đâu?
- Có thể mở khi SSO, PAM hoặc mạng chính không hoạt động không?
- Bản sao dự phòng có được bảo vệ và kiểm kê không?
- Phương tiện giải mã có nằm cùng nơi với dữ liệu được mã hóa không?
- Có phát hiện được truy cập trái phép hoặc mất vật mang không?
- Người trực có thể nhận đúng tài liệu và phương tiện trong thời gian cần thiết không?

Không sao chép credential vào wiki, ticket hoặc nhóm chat để đạt tính sẵn sàng.

### 8.3. Dual control phải có tác dụng thực tế

Dual control yêu cầu hai bên tham gia theo thiết kế để giảm khả năng một người tự ý sử dụng quyền. Ví dụ, một người yêu cầu và một người giữ phương tiện xác thực có thể cần phối hợp theo cơ chế được hỗ trợ.

Hai chữ ký trong biểu mẫu sau sự cố không chứng minh đã có dual control tại lúc sử dụng. Tương tự, hai phần thông tin nhưng cùng được một người lấy không tạo được sự tách biệt thực tế.

Không tự chế cách chia password hoặc chia mã xác thực nếu không có đánh giá về khả năng sử dụng và bảo mật. Cần cân bằng kiểm soát với rủi ro không liên hệ được người thứ hai; nếu có chế độ khẩn cấp đặc biệt, định nghĩa trước điều kiện, thẩm quyền và hậu kiểm.

### 8.4. Tránh tạo khóa truy cập dài hạn không cần thiết

Nếu nhiệm vụ chỉ cần giao diện quản trị với xác thực mạnh, không tự tạo thêm API key dài hạn “để dự phòng”.

Nếu cần CLI hoặc API trong một kịch bản xác định, thiết kế riêng cách xác thực, phạm vi và vòng đời credential. Credential phiên ngắn hạn vẫn cần bảo vệ nơi lưu và khả năng thu hồi; không ghi token vào transcript, shell history hoặc log tự động hóa.

## 9. Chuẩn bị runbook có thể dùng khi hệ thống chính mất

Runbook phải truy cập được trong những tình huống nó cần giải quyết. Nội dung nên đủ để người được phân công thực hiện có kiểm soát, nhưng không biến tài liệu hướng dẫn thành nơi lưu secret.

Một runbook tối thiểu cần có:

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| Điều kiện kích hoạt | Đường bình thường hỏng hoặc không đáng tin ở điểm nào? |
| Thẩm quyền | Ai quyết định, ai thực hiện, ai giám sát? |
| Đích truy cập | Tenant, tổ chức, tài khoản hoặc project chính xác nào? |
| Lấy credential | Mở phương tiện bảo quản qua quy trình nào? |
| Thiết bị và mạng | Dùng thiết bị nào, kết nối nào, cần chuẩn bị gì từ trước? |
| Xác minh quyền | Kiểm tra danh tính, phạm vi và thao tác phục hồi thế nào? |
| Thao tác dự kiến | Thay đổi nào được phép và thứ tự nào giảm tác động? |
| Bằng chứng | Ghi hoạt động, mã phiên và kết quả ở đâu? |
| Kết thúc | Thu hồi phiên, xử lý credential và phục hồi kiểm soát thế nào? |
| Nhánh thất bại | Khi không đăng nhập hoặc không có quyền, chuyển sang ai và quy trình nào? |

Định danh cloud cần chính xác, tránh chỉ ghi “production”. Khi tổ chức có nhiều tenant hoặc account cùng tên gần giống nhau, runbook nên có định danh ổn định và cách xác nhận đích trước thay đổi.

Chuẩn bị thông tin liên hệ và quy trình hỗ trợ nhà cung cấp nếu kịch bản cần đến. Quyền liên hệ hỗ trợ, khả năng xác minh chủ sở hữu và thông tin phục hồi cũng cần được duy trì; không mặc định bất kỳ người trực nào cũng có thể yêu cầu nhà cung cấp mở khóa ngay lập tức.

### 9.1. Thiết bị truy cập

Thiết bị dùng trong phiên khẩn cấp cần đủ tin cậy và có những công cụ cần thiết. Nếu việc cài CLI hoặc lấy cấu hình yêu cầu hệ thống quản lý đang ngừng hoạt động, phải giải quyết phụ thuộc đó trước.

Không đăng nhập credential khẩn cấp từ một máy đang nghi bị xâm nhập chỉ vì đó là máy còn mở sẵn. Cần phương án thiết bị phù hợp với tình huống, nhất là khi nguyên nhân kích hoạt là sự cố bảo mật.

### 9.2. Kênh thao tác

Console, CLI, API hoặc công cụ khôi phục đều có phụ thuộc riêng. Một terminal do cloud cung cấp có thể cần chính quyền hoặc dịch vụ đang lỗi, nên không mặc định nó luôn là phương án thay thế.

Chọn kênh theo thao tác phục hồi và khả năng đã thử nghiệm. Giữ rõ principal hiện tại, account đích và ngữ cảnh cấu hình để tránh thực hiện đúng lệnh trên sai môi trường.

## 10. Quy trình kích hoạt và sử dụng

Một luồng tham khảo gồm sáu giai đoạn:

```text
Xác nhận tình huống
        |
        v
Ủy quyền và giao người thực hiện
        |
        v
Nhận phương tiện truy cập khẩn cấp
        |
        v
Xác minh danh tính, đích và quyền
        |
        v
Thực hiện thay đổi phục hồi có giới hạn
        |
        v
Xác minh, đóng phiên và đối chiếu bằng chứng
```

### 10.1. Xác nhận sự cố và nhu cầu quyền

Ghi nhận đường truy cập nào thất bại, hệ thống nào chịu ảnh hưởng và vì sao quy trình bình thường không đáp ứng được.

Không cần chờ biết toàn bộ nguyên nhân mới được phục hồi, nhưng phải có giả thuyết và mục tiêu rõ. Ví dụ: “khôi phục trust đăng nhập quản trị tại tenant được chỉ định”, thay vì “cấp toàn quyền cho đội trực”.

Nếu nghi IdP bị xâm nhập, cân nhắc rằng danh tính, email hoặc phê duyệt qua IdP đó có thể không đủ tin cậy. Sử dụng kênh xác minh thay thế đã được thiết kế cho tình huống này.

### 10.2. Giao người và giới hạn phiên

Chỉ định người thực hiện, người giám sát hoặc phê duyệt theo chính sách và người điều phối sự cố.

Ghi mục tiêu, phạm vi cloud, thời điểm bắt đầu và mốc cần đánh giá lại. Một mốc thời gian vận hành không tự làm phiên hết hiệu lực; phải biết cơ chế kỹ thuật nào giới hạn credential và phiên thực tế.

Khi cần kéo dài, ghi lý do và tiếp tục kiểm soát phạm vi. Không để một phiên khẩn cấp còn mở qua nhiều ca mà không xác định ai đang chịu trách nhiệm.

### 10.3. Nhận credential

Thực hiện thủ tục checkout hoặc mở phương tiện bảo quản. Ghi nhận việc bàn giao mà không ghi nội dung secret.

Nếu có niêm phong bất thường, mất thiết bị hoặc dấu hiệu credential từng bị truy cập trái phép, xử lý theo nhánh nghi lộ credential. Không chỉ cập nhật kiểm kê rồi sử dụng như bình thường.

### 10.4. Xác minh trước hành động có tác động

Trước khi sửa cấu hình:

- Xác nhận principal đang đăng nhập.
- Xác nhận tenant, account, subscription hoặc project đích.
- Xác nhận quyền hiệu lực cho hành động dự kiến.
- Đọc trạng thái hiện tại và ghi lại những thông tin cần thiết.
- Xác định phương án đảo ngược hoặc phục hồi cấu hình nếu thao tác thất bại.
- Kiểm tra việc thu thập audit trong phạm vi có thể xác minh.

Không dùng thao tác phá hủy làm cách kiểm tra quyền. Nếu chỉ cần xác nhận khả năng đọc cấu hình, không xóa một policy thật để chứng minh principal có thể quản trị IAM.

### 10.5. Thực hiện thay đổi nhỏ nhất đủ phục hồi

Ưu tiên thay đổi cụ thể, có thể giải thích và xác minh. Ví dụ, khôi phục một trust bị sửa sai thường tốt hơn việc xóa mọi điều kiện truy cập của tổ chức.

Nếu phải tạo một grant tạm thời để tiếp tục sửa chữa, giới hạn principal nhận quyền, hành động và thời hạn theo cơ chế nền tảng hỗ trợ. Ghi lại grant để có thể thu hồi sau.

Không dùng phiên khẩn cấp để xử lý thêm các công việc không liên quan chỉ vì “đã có quyền”.

### 10.6. Xác nhận đường bình thường hoạt động

Thử đường quản trị bình thường bằng danh tính phù hợp và kiểm tra một thao tác có ý nghĩa trong phạm vi cho phép.

Đăng nhập được chưa đủ nếu quyền quản trị cần thiết vẫn thiếu. Ngược lại, một phiên cũ còn hoạt động không chứng minh một lần đăng nhập mới sẽ thành công. Cần kiểm tra đúng hành vi đã được sửa.

Tính đến độ trễ áp dụng cấu hình hoặc lan truyền quyền khi nền tảng có đặc tính đó. Phân biệt thay đổi đang chờ có hiệu lực với thay đổi thất bại để tránh liên tục mở rộng quyền khi chưa cần.

## 11. Bằng chứng và giám sát phiên khẩn cấp

Mục tiêu là nối được:

```text
Người được ủy quyền
  → lần bàn giao credential
  → phiên cloud
  → API hoặc thay đổi cụ thể
  → kết quả phục hồi
  → việc đóng quyền và xử lý credential
```

Các nhóm bằng chứng có thể gồm:

| Nhóm | Nội dung minh họa |
| --- | --- |
| Kích hoạt | Sự cố, lý do, phạm vi, người cho phép |
| Bàn giao | Ai nhận, lúc nào, phương tiện nào theo mã kiểm kê |
| Xác thực | Principal, thời điểm, kết quả đăng nhập, định danh phiên nếu có |
| Thực thi | Hành động, tài nguyên, principal hiệu lực, kết quả |
| Thay đổi | Trạng thái trước và sau hoặc tham chiếu cấu hình được bảo vệ |
| Kết thúc | Phiên đã đóng, grant đã thu hồi, credential đã xử lý |
| Hậu kiểm | Chênh lệch với runbook, hành động ngoài phạm vi, việc cần khắc phục |

### 11.1. Cảnh báo cả hoạt động thành công

Bất kỳ lần sử dụng danh tính khẩn cấp nào cũng nên được chú ý theo chính sách, kể cả đăng nhập thành công và truy vấn chỉ đọc.

Cần theo dõi thêm:

- Thay password hoặc đăng ký phương tiện xác thực mới.
- Tạo API key hoặc credential bổ sung.
- Đổi email, thông tin phục hồi hoặc chủ sở hữu.
- Thay role, trust hoặc policy của danh tính khẩn cấp.
- Tắt audit hoặc thay nơi nhận log.
- Tạo principal mới hay cấp quyền có thể tồn tại sau sự cố.

Nếu cảnh báo chỉ gửi tới chính hệ thống email hoặc tenant đang mất, cần kênh quan sát thay thế phù hợp. Một cảnh báo được tạo nhưng không ai nhận được chưa đáp ứng mục tiêu vận hành.

### 11.2. Audit cloud không đồng nghĩa mọi hoạt động đã được ghi

Phân biệt sự kiện xác thực, thay đổi control plane và truy cập dữ liệu. Cần biết loại sự kiện nào được thu thập, ở phạm vi nào, có độ trễ gì và ai có quyền thay cấu hình.

Không mặc định bật một loại audit quản trị là đã ghi mọi lần đọc dữ liệu hoặc mọi hành động bên trong máy ảo.

Ghi màn hình hoặc transcript có thể hỗ trợ nhưng không thay thế audit tại nền tảng và tài nguyên đích. Những bản ghi này cũng có thể chứa secret, vì vậy cần bảo vệ nơi lưu, quyền đọc và thời hạn lưu.

### 11.3. Bảo vệ audit trước người có quyền khẩn cấp

Nếu principal khẩn cấp có quyền thay đổi audit, khả năng can thiệp cần được đánh giá rõ.

Có thể dùng đích log với miền quản trị tách biệt, cơ chế lưu giữ hoặc giám sát bên ngoài phạm vi đang phục hồi. Kiểm tra quyền hiệu lực ở cả kho lưu, khóa mã hóa và tài khoản quản trị cấp cao; hai đích lưu khác nhau không tự tạo sự độc lập nếu cùng một principal kiểm soát mọi thứ.

Không tuyên bố bằng chứng không thể bị mất chỉ vì đã bật một tùy chọn bất biến. Cần kiểm chứng giới hạn của cơ chế thực tế và khả năng mất sự kiện trước khi đến nơi lưu.

### 11.4. Khi audit không hoạt động

Runbook cần định nghĩa hành vi khi audit bị trễ, mất đích lưu hoặc không thể xác minh.

Có thể cần người giám sát, ghi chép được bảo vệ hoặc phương thức ghi thay thế trong một kịch bản được cho phép. Điều này không có nghĩa mọi thao tác đều được tiếp tục vô điều kiện.

Nếu phải phục hồi chính audit, xác định phạm vi thay đổi, cách ghi bằng chứng tạm thời và cách đối chiếu sau đó. Không dùng sự cố audit làm lý do để tắt thêm kiểm soát không liên quan.

## 12. Kết thúc phiên và khôi phục kiểm soát

Kết thúc break-glass là một phần của nhiệm vụ phục hồi, không phải việc tùy chọn sau khi ứng dụng hoạt động lại.

### 12.1. Kiểm kê những gì đã được tạo

Trong phiên có thể đã phát sinh:

- Phiên trình duyệt và token truy cập.
- Credential CLI hoặc token tạm thời.
- Phiên ủy quyền sang role khác.
- Grant hoặc thành viên nhóm tạm thời.
- API key hoặc service principal mới.
- Kết nối tới tài nguyên đích.
- Job bất đồng bộ còn chạy.
- File cấu hình hoặc credential cache trên thiết bị.
- Bản xuất dữ liệu hoặc bản sao phục vụ điều tra.

Đóng tab trình duyệt không chứng minh tất cả những đối tượng này đã hết hiệu lực.

### 12.2. Thu hồi theo cơ chế thực tế

Dùng khả năng thu hồi mà nền tảng hỗ trợ cho từng loại phiên và credential. Cần hiểu độ trễ, phạm vi và trường hợp token hoặc phiên đích còn tồn tại.

Đổi password không mặc nhiên thu hồi mọi token đã cấp, mọi phiên ủy quyền hoặc mọi kết nối đến hệ thống đích. Thu hồi grant ban đầu cũng có thể không chấm dứt ngay mọi phiên đã tạo trước đó, tùy cơ chế.

Phải kiểm tra những hành vi quan trọng trong phạm vi an toàn: phiên cũ còn gọi được API hay không, credential cũ còn hợp lệ hay không và grant tạm thời đã thực sự bị gỡ chưa.

### 12.3. Xử lý credential sau sử dụng

Password hoặc secret đã được tiết lộ cho người sử dụng có thể cần luân chuyển theo quy trình. API key tạo tạm cần được xóa hoặc thu hồi sau nhiệm vụ nếu không còn nhu cầu.

Phương tiện xác thực phần cứng không tự động cần thay sau mỗi lần sử dụng hợp lệ. Cần kiểm kê, kiểm tra việc bàn giao và xử lý khi mất, nghi lộ hoặc thay người giữ theo chính sách.

Với từng loại credential, mục tiêu là khôi phục trạng thái bảo quản đáng tin cậy, không phải áp dụng một thao tác “rotate” giống nhau cho mọi thứ.

Sau thay đổi, xác nhận đường khẩn cấp vẫn sử dụng được bằng phương thức kiểm tra phù hợp và cập nhật tài liệu bảo quản. Không kết thúc sự cố với bản niêm phong cũ chứa credential không còn đúng.

### 12.4. Kiểm tra quyền tồn dư và đường truy cập mới

Đối chiếu trước và sau đối với role, trust, principal, key, phương tiện xác thực, policy và cấu hình audit liên quan.

Đặc biệt tìm những thay đổi có thể tạo tính thường trực:

- Quyền rộng được cấp cho tài khoản cá nhân.
- Một principal mới không có chủ sở hữu.
- Ngoại lệ policy không có thời hạn.
- Khóa truy cập dài hạn được tạo để sửa lỗi nhưng chưa bị thu hồi.
- Federation thứ hai hoặc trust mở rộng không còn cần.
- Một thay đổi audit làm giảm khả năng quan sát.

Một hệ thống đã phục hồi khả dụng nhưng còn quyền quản trị ngoài kiểm soát chưa hoàn tất nhiệm vụ break-glass.

## 13. Tình huống minh họa: mất quyền quản trị do cấu hình federation

Một doanh nghiệp có nhiều tài khoản cloud. Đội vận hành đăng nhập qua IdP doanh nghiệp và nhận role từ PAM. Một thay đổi trust làm mọi lần đăng nhập quản trị mới bị từ chối.

Đường khẩn cấp đã được chuẩn bị gồm:

- Danh tính phục hồi không phụ thuộc vào federation vừa thay đổi.
- Phương tiện xác thực và credential được bảo quản theo cơ chế đã thử.
- Quyền khôi phục cấu hình trust ở đúng cấp.
- Runbook truy cập được khi IdP không dùng được.
- Cảnh báo sử dụng danh tính khẩn cấp qua kênh phù hợp.
- Audit thay đổi được đưa tới nơi bảo quản đã xác định.

### 13.1. Kích hoạt

Người điều phối xác nhận lỗi xảy ra sau thay đổi, không chỉ là lỗi password của một người. Người được phân công nhận phương tiện truy cập và ghi mã sự cố.

Trước khi sửa, họ xác nhận đang ở đúng tenant và đọc cấu hình hiện tại. Việc đối chiếu không dựa vào một file bất kỳ nhận qua chat; dùng nguồn cấu hình được quản trị và có thể truy cập trong tình huống này.

### 13.2. Phục hồi

Người thực hiện sửa phần trust được xác định là sai, giữ nguyên những ràng buộc không liên quan.

Nếu quyền dự kiến không đủ, họ chuyển sang nhánh xử lý được quy định, đánh giá nhu cầu quyền bổ sung và ghi lý do. Không tự xóa policy rộng để thử từng bước.

Sau khi cấu hình có hiệu lực, một người khác kiểm tra lần đăng nhập mới qua đường bình thường và một thao tác quản trị phù hợp.

### 13.3. Đóng và đối chiếu

Đội trực đóng phiên khẩn cấp, xử lý credential, gỡ quyền tạm đã tạo và kiểm tra audit.

Hậu kiểm xác định vì sao thay đổi trust có thể làm mất toàn bộ đường quản trị, biện pháp kiểm tra trước thay đổi còn thiếu và thử nghiệm nào cần bổ sung. Không chỉ đánh dấu sự cố “đã xử lý bằng tài khoản dự phòng”.

## 14. Trường hợp break-glass không giải quyết được

| Tình huống | Giới hạn cần hiểu |
| --- | --- |
| Control plane cloud không xử lý API cần thiết | Một credential khác không làm API hoạt động trở lại |
| Mọi credential và phương tiện xác thực đã mất | Có thể cần quy trình phục hồi tài khoản hoặc hỗ trợ nhà cung cấp |
| Policy chặn cả principal khẩn cấp ở cấp không thể tự sửa | Cần phương án quản trị hoặc phục hồi đúng cấp |
| Tài khoản bị chiếm cùng mọi đường phục hồi | Có thể không còn một miền tin cậy nội bộ đủ để tự khôi phục |
| Ứng dụng hỏng dữ liệu nhưng IAM vẫn hoạt động | Cần quy trình khôi phục dữ liệu; không mặc định dùng quyền khẩn cấp |
| Mất mạng tới cloud từ mọi đường được chuẩn bị | Cần phương án kết nối hoặc vận hành khác |
| Credential còn đúng nhưng đích bị đình chỉ theo quy trình của nhà cung cấp | Cần xử lý nguyên nhân và quy trình liên quan, không phải đổi principal |

Nhận diện giới hạn giúp tránh lặp lại đăng nhập, tạo thêm key hoặc mở rộng quyền trong khi nguyên nhân nằm ngoài quyền truy cập.

Kế hoạch liên tục hoạt động có thể cần phương án chuyển dịch vụ, khôi phục dữ liệu hoặc chờ nhà cung cấp. Những phương án đó cần được thiết kế riêng, không suy ra từ việc có một tài khoản khẩn cấp.

## 15. Diễn tập theo tình huống lỗi

Một bài diễn tập cần kiểm tra giả thuyết cụ thể. Ví dụ: “IdP không dùng được nhưng control plane cloud còn hoạt động”.

Không chỉ yêu cầu người trực mở một trang đăng nhập rồi chụp ảnh.

### 15.1. Những lớp cần kiểm tra

1. **Con người:** người có trách nhiệm nhận biết tình huống, liên hệ được người giữ phương tiện và xác minh thẩm quyền.
2. **Tài liệu:** runbook và định danh cloud còn đúng, truy cập được trong điều kiện giả định.
3. **Credential:** phương tiện bảo quản có thể mở đúng cách và không lộ secret.
4. **Xác thực:** đăng nhập được qua đường dự phòng mà không dùng phụ thuộc đang được mô phỏng là hỏng.
5. **Phân quyền:** thực hiện được thao tác phục hồi thử nghiệm phù hợp.
6. **Bằng chứng:** cảnh báo được nhận, audit có sự kiện và nối được với người thực hiện.
7. **Kết thúc:** phiên và grant được đóng, credential được xử lý, khả năng dự phòng được khôi phục.

### 15.2. Bộ kiểm tra tham khảo

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| SSO không dùng được | Đường xác thực khẩn cấp không quay lại phụ thuộc SSO |
| PAM không cấp phiên | Nhận được phương tiện truy cập theo đường đã chuẩn bị |
| Người giữ chính vắng mặt | Người dự phòng có thể thực hiện đúng thẩm quyền |
| Thiết bị xác thực chính mất | Phương án dự phòng được bảo quản và sử dụng đúng |
| Sai account hoặc tenant đang được chọn | Có bước phát hiện trước thay đổi |
| Đăng nhập được nhưng thiếu quyền sửa lỗi | Nhánh xử lý quyền không dẫn tới mở rộng tùy ý |
| Audit đến chậm hoặc không nhận được cảnh báo | Nhận diện được thiếu bằng chứng và áp dụng nhánh phù hợp |
| Credential cũ bị sử dụng sau kết thúc | Bị từ chối hoặc giới hạn theo hành vi thu hồi đã kiểm chứng |
| Grant hoặc role tạm còn sót | Kiểm kê cuối phiên phát hiện được |
| Runbook hoặc thông tin phục hồi đã cũ | Có chủ sở hữu và hành động sửa cụ thể |

### 15.3. Diễn tập mà không tạo sự cố thật

Dùng môi trường thử nghiệm, tài nguyên phục hồi mẫu hoặc thay đổi an toàn có thể xác minh. Khi cần kiểm tra trên production, phạm vi và hành động phải được cho phép, có bảo vệ phù hợp với tác động.

Không vô hiệu hóa toàn bộ SSO production chỉ để chứng minh tài khoản khẩn cấp hoạt động. Có thể kết hợp mô phỏng điều kiện lỗi, kiểm tra độc lập phụ thuộc và thử thao tác hẹp trên đích được chọn.

Xác định lịch diễn tập theo rủi ro, mức quan trọng và tốc độ thay đổi của hệ thống. Cần kiểm tra lại sau những thay đổi ảnh hưởng tới đường phục hồi như IdP, PAM, chính sách cloud, phương tiện xác thực, người giữ hoặc vị trí bảo quản.

Đo thời gian phục hồi để biết khả năng thực tế, nhưng không đặt tốc độ lên trên việc xác minh đúng đích và quyền. Một lần truy cập nhanh vào sai tenant không phải kết quả tốt.

## 16. Những sai lầm thường gặp

### 16.1. Tất cả credential đều nằm trong cùng vault phụ thuộc SSO

Vault có thể rất an toàn trong vận hành bình thường nhưng không cung cấp độc lập cho lỗi SSO nếu mọi cách mở vault đều qua SSO đó.

Cách sửa là phân tích phụ thuộc và chuẩn bị đường bảo quản phù hợp với tình huống, thay vì sao chép secret ra nhiều nơi không kiểm soát.

### 16.2. Chỉ kiểm tra đăng nhập

Tài khoản đăng nhập được nhưng thiếu quyền sửa cấu hình ở cấp tổ chức vẫn không thực hiện được nhiệm vụ.

Phải kiểm tra thao tác phục hồi đại diện, quyền hiệu lực và giới hạn cấp quản trị.

### 16.3. Tài khoản khẩn cấp được dùng hằng ngày

Việc sử dụng thường xuyên làm credential xuất hiện trên nhiều thiết bị và che lấp bất thường. Nó cũng khiến việc thu hồi hoặc luân chuyển khó vì công việc bình thường đang phụ thuộc vào tài khoản đó.

Cần cung cấp đường vận hành thông thường đủ dùng và đưa tài khoản khẩn cấp trở lại đúng mục đích.

### 16.4. Tắt MFA hoặc audit để đơn giản hóa

Cách làm này có thể tạo một đường tấn công quyền cao luôn tồn tại.

Giải quyết sự phụ thuộc của MFA và audit theo mô hình lỗi. Khi có ngoại lệ cần thiết, phải thiết kế phạm vi và bằng chứng thay thế cụ thể, không bỏ kiểm soát cho mọi trường hợp.

### 16.5. Đổi password rồi coi như đã thu hồi

Phiên, token, key và quyền được tạo thêm có vòng đời riêng. Cần kiểm kê và xử lý từng loại thay vì chỉ thay một secret.

### 16.6. Cảnh báo gửi về nơi đang hỏng

Một tài khoản khẩn cấp có cảnh báo nhưng không có kênh nhận khả dụng trong kịch bản lỗi thì vẫn có khoảng mù.

Kiểm tra người nhận và kênh liên lạc trong chính bài diễn tập.

### 16.7. Không cập nhật phương tiện bảo quản

Sau khi luân chuyển password, bản lưu dự phòng vẫn chứa giá trị cũ. Đến lần sự cố tiếp theo, tổ chức mới phát hiện đường khẩn cấp không dùng được.

Mỗi lần thay đổi credential cần hoàn tất cập nhật, bàn giao và kiểm tra khả năng sử dụng theo quy trình.

## 17. Bài tập áp dụng

Bạn quản lý một môi trường cloud gồm một cấp quản trị chung và ba project production. Người dùng đăng nhập qua IdP, quyền JIT được cấp qua PAM, credential được lưu trong vault có đăng nhập SSO.

Hãy thiết kế phương án cho hai tình huống:

- IdP ngừng hoạt động nhưng control plane cloud còn dùng được.
- Một thay đổi policy khiến đội vận hành mất quyền ở một project, trong khi IdP vẫn hoạt động.

Với từng tình huống, mô tả:

1. Điều kiện được kích hoạt break-glass.
2. Danh tính nào được dùng và cấp cloud nào cần thao tác.
3. Những phụ thuộc phải tách khỏi đường bình thường.
4. Credential, phương tiện xác thực và người giữ được tổ chức thế nào.
5. Hành động tối thiểu để phục hồi.
6. Bằng chứng xác thực, thực thi và kết thúc được thu thập ở đâu.
7. Cách xử lý phiên, token và grant còn tồn tại.
8. Một phép diễn tập an toàn chứng minh phương án có tác dụng.

Một đáp án tốt sẽ không mặc định hai tình huống cần cùng một tài khoản toàn quyền. Nó cần phân biệt lỗi xác thực với lỗi phân quyền và chứng minh đường dự phòng giải quyết đúng lỗi.

## 18. Tiêu chí hoàn thành

Một thiết kế cloud break-glass đạt mục tiêu khi tổ chức có thể chứng minh:

- Tình huống kích hoạt và giới hạn của phương án đã được xác định.
- Đường truy cập có mức độc lập phù hợp với các lỗi cần chịu đựng.
- Principal có quyền hiệu lực để thực hiện nhiệm vụ phục hồi ở đúng cấp cloud.
- Phạm vi quyền, khả năng tự nâng quyền và quyền thường trực còn lại được hiểu rõ.
- Credential và phương tiện xác thực được bảo quản an toàn, có người dự phòng và có thể nhận khi cần.
- Runbook, thiết bị, mạng và kênh xác minh khả dụng trong tình huống giả định.
- Người thực hiện, phiên cloud và thay đổi được nối với hồ sơ sự cố.
- Audit và cảnh báo có phạm vi, nơi nhận và giới hạn được kiểm chứng.
- Phiên, token, key, grant và quyền tồn dư được xử lý sau sử dụng.
- Diễn tập kiểm tra cả thao tác phục hồi lẫn việc khôi phục trạng thái bảo quản.

Cloud break-glass là một năng lực phục hồi được quản trị. Giá trị của nó nằm ở khả năng đưa người có trách nhiệm trở lại đúng quyền cần thiết khi đường bình thường thất bại, đồng thời giữ đủ kiểm soát để một lần truy cập khẩn cấp không trở thành đặc quyền tồn tại ngoài quản lý.

