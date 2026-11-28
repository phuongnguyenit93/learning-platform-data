# Lưu password trong spreadsheet

## 1. Vì sao đây là một anti-pattern của PAM?

Một bảng tính có các cột `Hệ thống`, `Username`, `Password`, `Người phụ trách` thường bắt đầu như một giải pháp tiện lợi: đội vận hành cần biết mật khẩu quản trị nằm ở đâu và ai có thể sử dụng nó. Khi số hệ thống tăng lên, bảng được đưa vào thư mục dùng chung, gửi cho nhà cung cấp, tải về laptop hoặc đính kèm trong tài liệu bàn giao. Từ công cụ ghi chép, nó trở thành một kho credential không có đầy đủ cơ chế kiểm soát của kho bí mật chuyên dụng.

Trong Privileged Access Management (PAM), vấn đề không chỉ là làm cho người ngoài không mở được file. Tổ chức còn phải kiểm soát ai được dùng credential, dùng vào tài nguyên nào, trong khoảng thời gian nào, với quyền gì, và lưu được bằng chứng của lần sử dụng đó. Một spreadsheet chứa password khó đáp ứng đồng thời các yêu cầu này, đặc biệt với tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm.

Anti-pattern xuất hiện khi tổ chức dùng spreadsheet làm nguồn lưu trữ hoặc phân phối bí mật, kể cả khi file có đặt mật khẩu, nằm trên một nền tảng cộng tác có kiểm soát truy cập hoặc chỉ chia sẻ trong nhóm nội bộ. Các biện pháp bảo vệ file có giá trị, nhưng không tự biến file thành một hệ thống quản lý vòng đời credential.

Sau bài học, bạn có thể:

- Nhận diện những đường phát tán credential từ một bảng tính tưởng như được quản lý chặt.
- Phân biệt bảng kiểm kê tài khoản với kho chứa bí mật.
- Chọn cách truy cập phù hợp cho quản trị viên, ứng dụng và tình huống khẩn cấp.
- Lập kế hoạch chuyển credential sang vault và thay thế credential đã từng xuất hiện trong spreadsheet.
- Xác định bằng chứng để biết việc chuyển đổi đã đóng được rủi ro nào và còn tồn tại ngoại lệ nào.

## 2. Một tình huống điển hình

Đội vận hành của một doanh nghiệp dùng file `Infrastructure-Accounts.xlsx` để bàn giao tài khoản. File có mật khẩu quản trị cơ sở dữ liệu, tài khoản quản trị thiết bị mạng, tài khoản dịch vụ chạy tác vụ đêm và một tài khoản cứu hộ. Ban đầu chỉ ba người được truy cập. Sau vài đợt triển khai, file còn xuất hiện trong email bàn giao, thư mục đồng bộ của laptop và gói tài liệu gửi cho đối tác.

Khi một kỹ sư nghỉ việc, nhóm thu hồi quyền vào thư mục gốc. Tuy nhiên, không ai biết kỹ sư đã tải file hay chưa. Đội vận hành cũng không biết những password nào còn được dùng ở nơi khác, và một ứng dụng cũ vẫn phụ thuộc vào mật khẩu trong bảng. Vì sợ gián đoạn, nhóm chưa đổi các credential này.

Tình huống đó chứa nhiều vấn đề riêng biệt:

| Quan sát | Rủi ro thực tế | Điều cần kiểm soát trong PAM |
| --- | --- | --- |
| Nhiều người đọc cùng một password quản trị | Khó quy hành động cho từng cá nhân | Danh tính cá nhân, cấp quyền có kiểm soát, tương quan phiên |
| Có thể tải hoặc gửi cả file | Bí mật thoát khỏi phạm vi kiểm soát của bản gốc | Hạn chế tiết lộ và giảm nhu cầu nhận password |
| Không rõ ứng dụng nào dùng tài khoản | Rotation dễ gây gián đoạn | Kiểm kê dependency, kiểm thử và phối hợp thay credential |
| Thu hồi quyền file sau khi nhân viên rời đi | Bản sao đã có vẫn tồn tại | Vô hiệu hóa giá trị của credential cũ, xử lý phiên liên quan |
| Tài khoản cứu hộ nằm chung bảng | Sự cố file có thể ảnh hưởng luôn đường khôi phục | Cơ chế break-glass riêng, được bảo vệ và diễn tập |

Không có bằng chứng về truy cập trái phép không đồng nghĩa đã chứng minh credential an toàn. Ngược lại, việc phát hiện spreadsheet chứa password cũng chưa tự chứng minh đã xảy ra xâm nhập. Cần đánh giá phạm vi người có thể tiếp cận, đường sao chép và dấu vết sử dụng để quyết định biện pháp xử lý phù hợp.

## 3. Credential có những gì ngoài password?

Phạm vi rà soát không nên dừng ở các ô có nhãn `Password`. Những giá trị có thể trực tiếp xác thực hoặc khôi phục quyền truy cập đều cần được xem xét như bí mật:

- Mật khẩu tài khoản quản trị hệ điều hành, cơ sở dữ liệu, thiết bị mạng hoặc ứng dụng.
- Mật khẩu tài khoản dịch vụ, tài khoản chạy batch job và tài khoản tích hợp.
- API key, access token, refresh token hoặc chuỗi kết nối có nhúng credential.
- Private key, passphrase bảo vệ private key và một số loại khóa ký có quyền nhạy cảm.
- Recovery code, mã dự phòng MFA và bí mật dùng để thiết lập bộ sinh mã xác thực.
- Credential của chính vault, tài khoản khẩn cấp hoặc tài khoản dùng để khôi phục hệ thống PAM.

Username, tên hệ thống, địa chỉ quản trị và đường dẫn tham chiếu thường không phải bí mật xác thực giống password. Tuy vậy, chúng vẫn có thể là thông tin nội bộ nhạy cảm và phải được phân loại, giới hạn chia sẻ. Bảng kiểm kê không chứa password không có nghĩa là bảng đó được phép công khai.

Một URL cũng có thể chứa token hoặc chữ ký truy cập. Vì vậy, chỉ dùng đường dẫn định danh tài nguyên hoặc mã tham chiếu đã loại bỏ thông tin xác thực; không mặc định rằng mọi cột `Link` đều an toàn.

## 4. Những cơ chế khiến spreadsheet trở thành rủi ro

### 4.1. Quyền đọc file đồng nghĩa với khả năng biết nhiều bí mật

Trong nhiều bảng mật khẩu, một người chỉ cần credential của một hệ thống nhưng phải đọc cả workbook. File có thể chia sheet hoặc giới hạn một số vùng, nhưng cần đánh giá khả năng thực tế của nền tảng thay vì giả định các ranh giới hiển thị là ranh giới bảo mật.

Đối với PAM, đơn vị cấp quyền nên gần với nhu cầu công việc: một người, một vai trò, một tài nguyên, một thao tác và một khoảng thời gian. Nếu quyền đọc spreadsheet mở ra cả tập credential thì phạm vi truy cập thường rộng hơn nhu cầu đó.

Least privilege không chỉ áp dụng cho quyền trên hệ thống đích. Nó còn áp dụng cho quyền lấy, xem, xuất và quản lý bí mật trong kho.

### 4.2. Bản sao tồn tại độc lập với quyền của bản gốc

Sau khi một người biết password, việc thu hồi quyền vào spreadsheet không làm người đó quên password. Các bản tải xuống, ảnh chụp màn hình, lịch sử clipboard, email hoặc bản đồng bộ có thể tồn tại ngoài phạm vi quản lý của file gốc.

Có thể hình dung sự phát tán như sau:

```text
Spreadsheet gốc
  ├─ bản tải về máy cá nhân
  ├─ file đính kèm bàn giao
  ├─ bản sao trong thư mục dự án
  └─ bản lưu hoặc phiên bản lịch sử

Thu hồi quyền bản gốc ≠ vô hiệu hóa credential trong mọi bản sao
```

Đây là lý do kế hoạch chuyển đổi phải có bước thay thế hoặc vô hiệu hóa credential cũ. Chỉ di chuyển cùng một password từ spreadsheet sang vault chưa làm các bản sao cũ mất giá trị.

### 4.3. Log đọc file không phải log sử dụng tài khoản

Một nền tảng cộng tác có thể ghi nhận các sự kiện mở, tải, sửa hoặc chia sẻ file, tùy cấu hình và khả năng của sản phẩm. Những sự kiện đó hữu ích cho điều tra, nhưng thường không đủ để kết luận ai đã dùng một credential cụ thể trên hệ thống đích.

Ngay cả log checkout từ vault cũng chưa tự chứng minh toàn bộ hành động tiếp theo của người dùng. Bằng chứng cần được kết hợp từ danh tính cá nhân, sự kiện yêu cầu và cấp quyền, phiên truy cập, log hệ thống đích, cùng thời gian và định danh tương quan.

Với tài khoản dùng chung, không nên hứa rằng chỉ đưa password vào vault là đã đạt đầy đủ khả năng quy trách nhiệm. Nếu hệ thống đích hỗ trợ danh tính riêng hoặc cơ chế truy cập ngắn hạn, cần cân nhắc sử dụng chúng. Nếu vẫn phải dùng tài khoản dùng chung, thiết kế broker, kiểm soát đồng thời và bằng chứng phiên phù hợp với khả năng của môi trường.

### 4.4. Rotation trở thành một thao tác sửa ô

Sửa giá trị trong spreadsheet không đồng nghĩa password trên hệ thống đích đã được đổi. Đổi password ở hệ thống đích cũng không bảo đảm ứng dụng phụ thuộc đã nhận giá trị mới. Khi hai thao tác này bị làm thủ công và tách rời, bảng có thể chứa credential lỗi thời hoặc credential đang được sử dụng ở nơi khác.

Rotation đáng tin cậy cần biết tài khoản được dùng ở đâu, ai sở hữu, cách cập nhật dependency, cách xác nhận credential mới hoạt động và cách xác nhận credential cũ không còn dùng được. Với môi trường cho phép nhiều credential cùng hiệu lực trong một giai đoạn chuyển tiếp, phải kiểm soát thời hạn và việc thu hồi giá trị cũ.

### 4.5. Một lần lộ có thể ảnh hưởng nhiều hệ thống

Một file tập trung password của cả môi trường có thể làm tăng phạm vi ảnh hưởng khi bị truy cập trái phép. Rủi ro tăng thêm nếu có password dùng lại, tài khoản đặc quyền rộng hoặc credential của nhiều môi trường nằm chung một nơi.

Vault cũng là thành phần tập trung cần được bảo vệ nghiêm ngặt. Lợi ích của vault không đến từ tên gọi mà đến từ thiết kế phân quyền, bảo vệ khóa, kiểm soát truy xuất, giám sát, khả năng phục hồi và cơ chế cấp quyền. Một vault được phân quyền quá rộng vẫn có thể tái tạo vấn đề của spreadsheet ở một giao diện khác.

## 5. Vì sao những cách chữa tạm chưa giải quyết đủ?

| Cách thường được áp dụng | Giá trị có thể mang lại | Phần rủi ro còn lại |
| --- | --- | --- |
| Đặt password để mở file | Có thể bảo vệ nội dung file khi dùng cơ chế mã hóa phù hợp | Người được phép mở vẫn có thể biết và sao chép credential; còn phải quản lý bí mật mở file |
| Khóa ô hoặc bảo vệ sheet | Hạn chế một số thao tác chỉnh sửa | Không được coi là cơ chế bảo mật nội dung tương đương mã hóa file hoặc phân quyền bí mật |
| Ẩn sheet hoặc ẩn cột password | Giảm hiển thị tình cờ trong một số tình huống | Việc không nhìn thấy trên giao diện chưa chứng minh không thể truy xuất |
| Chỉ chia sẻ cho nhóm vận hành | Giảm người có quyền truy cập ban đầu | Nhóm có thể có quyền quá rộng; bản sao và credential đã biết vẫn tồn tại |
| Chia password thành hai file | Tạo thêm điều kiện để ghép được bí mật | Tăng thao tác thủ công; hai file có thể cùng đến một người; không tạo được vòng đời PAM |
| Đổi tên cột hoặc mã hóa bằng quy ước tự nghĩ | Có thể gây khó đọc thoáng qua | Không cung cấp bảo vệ mật mã đáng tin cậy; khó kiểm toán và duy trì |
| Chuyển file sang nơi lưu trữ có mã hóa at rest | Bảo vệ một số dạng truy cập vào dữ liệu lưu trữ | Không ngăn người dùng đã được cấp quyền đọc hoặc xuất giá trị |
| Thêm MFA cho nền tảng chứa bảng | Giảm một số rủi ro chiếm quyền tài khoản của nền tảng | Không tự áp MFA cho đăng nhập trực tiếp bằng credential trên hệ thống đích |

Không nên kết luận mọi spreadsheet đều không có mã hóa hoặc mọi nền tảng đều không có audit log. Kết luận cần chính xác hơn: các tính năng bảo vệ tài liệu không mặc nhiên đáp ứng yêu cầu quản lý bí mật và kiểm soát sử dụng đặc quyền.

Một giải pháp tạm có thể giảm phơi lộ trong lúc chuyển đổi. Nó cần có chủ sở hữu, phạm vi, hạn kết thúc và kế hoạch loại bỏ; không nên trở thành lý do giữ nguyên kho password vô thời hạn.

## 6. Thiết kế đích: kiểm kê tách khỏi bí mật

### 6.1. Spreadsheet chỉ dùng cho metadata được phép lưu

Bảng kiểm kê có thể hỗ trợ rà soát coverage, owner, tình trạng onboarding và ngoại lệ. Nó nên giữ mã tham chiếu đến đối tượng được quản lý thay vì giá trị bí mật.

Ví dụ minh họa:

```csv
asset_id,environment,account_ref,owner_team,secret_ref,access_method,review_state
DB-017,production,acct-db-maint,DataOps,secretref-017,brokered-session,reviewed
APP-024,staging,svc-reporting,AppOps,secretref-024,workload-identity,pending
NET-008,production,acct-net-emergency,NetOps,secretref-008,break-glass,reviewed
```

Các định danh trên là dữ liệu giả. `secret_ref` chỉ là tham chiếu, không chứa token truy cập, password hoặc một URL có khả năng tự cấp quyền. Người có bảng kiểm kê vẫn phải được xác thực và được cấp quyền riêng khi yêu cầu bí mật hoặc phiên truy cập.

Tùy môi trường, bảng kiểm kê có thể thêm trường chủ sở hữu tài khoản, mức đặc quyền, dependency, chính sách rotation, ngày xác minh gần nhất và mã ngoại lệ. Những trường này hỗ trợ vận hành, nhưng bảng không nên tự trở thành một bản sao cấu hình nhạy cảm vượt quá nhu cầu.

### 6.2. Với quản trị viên: ưu tiên quyền có phạm vi và thời hạn

Một luồng truy cập đích có thể gồm:

1. Người dùng xác thực bằng danh tính cá nhân và đáp ứng yêu cầu xác thực của môi trường.
2. Hệ thống đánh giá tài nguyên, vai trò, lý do công việc, cửa sổ thời gian và điều kiện cấp quyền.
3. Nếu cần phê duyệt, người có thẩm quyền phê duyệt đúng yêu cầu.
4. PAM cấp quyền hoặc tạo phiên truy cập với phạm vi phù hợp; có thể dùng JIT/JEA nếu môi trường hỗ trợ.
5. Ghi nhận việc cấp quyền, phiên và hoạt động liên quan theo chính sách.
6. Hết thời hạn thì thu hồi quyền hoặc kết thúc khả năng truy cập, kiểm tra kết quả thực tế.

Just-in-Time (JIT) giới hạn thời gian có quyền. Just Enough Administration (JEA) giới hạn phạm vi quản trị được phép thực hiện theo cơ chế của môi trường. Hai mục tiêu này bổ sung cho nhau; quyền tồn tại trong mười phút nhưng có thể làm mọi việc vẫn có thể quá rộng.

Nếu PAM hỗ trợ kết nối qua broker mà không tiết lộ password cho người dùng, có thể giảm số người biết bí mật. Tuy nhiên, broker không tự bảo đảm mọi hành vi trong phiên đều an toàn. Vẫn cần quyền hệ thống đích phù hợp, kiểm soát đường truy cập ngoài broker và giám sát có mục đích.

### 6.3. Với tài khoản dịch vụ: thay cách cấp bí mật cho workload

Ứng dụng không nên mở một spreadsheet hoặc nhận password qua email để kết nối hạ tầng. Các hướng thiết kế có thể gồm danh tính workload, credential ngắn hạn hoặc truy xuất bí mật từ vault bằng danh tính được cấp riêng.

Luồng khái niệm dưới đây không phải API của một sản phẩm cụ thể:

```text
workload_identity = authenticate_workload()
access_context = authorize(workload_identity, resource_ref, required_scope)
lease = obtain_short_lived_credential(access_context)
connection = connect_to_target(lease.credential)
perform_allowed_operation(connection)
close(connection)
finish_lease_according_to_policy(lease)
```

Ứng dụng chỉ nên nhận credential cần cho tác vụ của nó. Không ghi credential vào log, error message, telemetry hoặc file tạm. Việc không lưu trong spreadsheet không có ý nghĩa nếu bí mật lại xuất hiện trong log triển khai.

Không phải hệ thống nào cũng hỗ trợ credential động hoặc danh tính workload. Nếu phải dùng password tĩnh, vẫn cần owner, phạm vi nhỏ nhất, truy xuất có kiểm soát, quản lý dependency và rotation phù hợp. Credential dùng để ứng dụng vào vault cũng phải được bảo vệ; tránh chỉ chuyển password của hệ thống đích thành một password bootstrap được chia sẻ ở chỗ khác.

### 6.4. Với break-glass: thiết kế đường khôi phục riêng

Tài khoản khẩn cấp cần hoạt động trong những kịch bản đã xác định, kể cả một số trường hợp hạ tầng danh tính hoặc PAM không sẵn sàng. Điều đó không đồng nghĩa phải lưu password cứu hộ trong spreadsheet dùng chung.

Cơ chế break-glass cần xác định ai được kích hoạt, điều kiện sử dụng, cách lấy credential, nơi lưu bằng chứng, cách thông báo khi hạ tầng giám sát phục hồi và việc thay credential sau sử dụng. Phương án dự phòng phải được bảo vệ theo thiết kế riêng và diễn tập định kỳ.

Tránh phụ thuộc vòng: nếu đường khôi phục vault chỉ có thể lấy từ chính vault đang hỏng, khả năng khôi phục chưa được giải quyết. Ngược lại, một bản sao cứu hộ ai cũng có thể tải lại mở ra đường bỏ qua kiểm soát.

## 7. Quy trình chuyển đổi có kiểm soát

### Bước 1 — Khoanh vùng nguồn và ngừng phát tán thêm

Xác định file gốc, chủ sở hữu, quyền chia sẻ, người hoặc nhóm nhận file, các bản xuất đã biết và những kênh đã dùng để bàn giao. Thu hẹp quyền chia sẻ khi phù hợp và ngừng bổ sung credential mới vào bảng.

Khi rà soát, không tạo thêm một spreadsheet tổng hợp chứa tất cả password. Báo cáo chỉ cần định danh credential, vị trí nguồn, trạng thái xử lý và người phụ trách. Nếu cần điều tra, bảo quản bằng chứng theo quy trình đã được tổ chức áp dụng; không gửi giá trị bí mật trong ticket.

### Bước 2 — Kiểm kê tài khoản và dependency

Với mỗi credential, xác minh ít nhất:

- Tài khoản thuộc hệ thống và môi trường nào, còn hoạt động hay đã ngừng sử dụng.
- Ai sở hữu tài khoản và ai chịu trách nhiệm cho ứng dụng hoặc dịch vụ phụ thuộc.
- Tài khoản có đặc quyền gì, có thể giảm quyền hoặc thay bằng danh tính khác không.
- Người dùng trực tiếp, ứng dụng, script, scheduled job hoặc công cụ nào đang sử dụng.
- Khả năng thay credential, thu hồi phiên, kiểm thử và khôi phục kết nối khi có lỗi.
- Credential có dùng lại ở nơi khác hoặc có loại bí mật liên quan cần thay cùng không.

Không cần thu thập password vào tài liệu kiểm kê để trả lời các câu hỏi này. Nếu chưa xác định được owner hoặc dependency, phải ghi rõ phần chưa biết và giao người xử lý.

### Bước 3 — Ưu tiên theo phạm vi ảnh hưởng

Các yếu tố như đặc quyền cao, tiếp xúc Internet, chia sẻ ngoài nhóm, password dùng lại và thiếu log có thể làm tăng mức ưu tiên. Tài khoản đã có dấu hiệu bị sử dụng trái phép cần được xử lý theo quy trình ứng phó sự cố của tổ chức, thay vì chờ hoàn tất cả dự án chuyển đổi.

Không nên dùng một thứ tự cứng cho mọi môi trường. Một tài khoản dịch vụ có thể cần phối hợp thay đổi để không làm gián đoạn hệ thống trọng yếu; sự phối hợp đó phải có người chịu trách nhiệm và thời hạn cụ thể.

### Bước 4 — Onboard phương thức truy cập đích

Tạo đối tượng bí mật hoặc phương thức truy cập trong hệ thống được chọn, cấu hình owner, phân quyền, chính sách truy xuất và giám sát. Kiểm tra người được cấp quyền thực hiện được tác vụ cần thiết và người không có quyền bị từ chối.

Với quản trị viên, kiểm thử danh tính cá nhân, đường truy cập PAM và việc hạn chế đường đăng nhập trực tiếp nếu thuộc thiết kế. Với ứng dụng, kiểm thử khả năng lấy credential và xử lý lỗi mà không lộ bí mật. Với break-glass, kiểm thử phương án khẩn cấp theo kịch bản được phê duyệt.

### Bước 5 — Thay credential đã từng nằm trong spreadsheet

Onboard xong mới là chuẩn bị nơi quản lý mới. Cần thay password, thu hồi key/token hoặc cấp lại loại bí mật tương ứng theo khả năng của hệ thống đích. Xác nhận credential mới hoạt động và credential cũ không còn được chấp nhận ở phạm vi cần xử lý.

Đối với một tài khoản dịch vụ, kế hoạch thay đổi có thể gồm:

1. Xác minh đầy đủ những consumer đã biết và cửa sổ thay đổi.
2. Chuẩn bị credential mới hoặc cơ chế cấp credential mới.
3. Cập nhật consumer theo khả năng của nền tảng, kiểm soát giai đoạn có nhiều credential cùng hiệu lực nếu có.
4. Chạy kiểm tra kết nối và tác vụ đại diện.
5. Vô hiệu hóa credential cũ và xác nhận không còn consumer cần nó.
6. Theo dõi lỗi xác thực và hành vi bất thường sau chuyển đổi.

Không dùng lại password đã bị coi là phơi lộ để rollback cho tiện. Phương án phục hồi nên dựa trên credential mới được kiểm soát hoặc cơ chế khôi phục khác đã chuẩn bị. Với hệ thống chỉ hỗ trợ một password tại một thời điểm, cần phối hợp cập nhật và dự kiến gián đoạn theo thực tế.

### Bước 6 — Xử lý phiên và các dạng quyền còn tồn tại

Đổi password không bảo đảm mọi phiên đang hoạt động, cookie, ticket, token hoặc credential dẫn xuất đều tự mất hiệu lực. Cơ chế này phụ thuộc vào hệ thống đích và loại xác thực.

Đánh giá loại phiên hoặc token được tạo từ credential cũ, rồi thu hồi hay kết thúc chúng theo chức năng của hệ thống và phạm vi xử lý. Ghi rõ những gì đã vô hiệu hóa, những gì còn chờ hết hạn và biện pháp kiểm soát trong thời gian đó.

### Bước 7 — Loại bỏ vai trò kho bí mật của spreadsheet

Sau khi credential cũ đã được xử lý, loại bỏ giá trị bí mật khỏi nơi đang dùng để phân phối. Rà soát phiên bản lịch sử, bản xuất, đính kèm và bản sao đã biết theo quyền quản lý, yêu cầu lưu giữ và quy trình của tổ chức.

Không tự xóa log, bằng chứng hoặc backup đang phải lưu giữ để làm sạch số liệu. Nếu một bản lưu không thể xóa ngay theo chính sách, hạn chế truy cập, bảo vệ nó và ghi nhận thời hạn xử lý. Credential đã được thay hoặc thu hồi giúp giảm giá trị khai thác của dữ liệu trong bản lưu, nhưng không làm tài liệu đó hết nhạy cảm.

Giữ lại một bảng metadata nếu có nhu cầu vận hành, với mã tham chiếu và owner. Cập nhật tài liệu bàn giao để người mới dùng quy trình PAM, tránh việc spreadsheet chứa password được tạo lại sau vài tháng.

## 8. Bằng chứng nào cho thấy chuyển đổi đã đạt mục tiêu?

Việc đếm số dòng đã đưa vào vault chỉ phản ánh một phần tiến độ. Mỗi credential cần có bằng chứng phù hợp với kiểu sử dụng của nó:

| Tiêu chí | Bằng chứng có thể dùng | Điểm cần tránh |
| --- | --- | --- |
| Có owner và biết mục đích | Mã tài khoản, đội sở hữu, dependency đã xác nhận | Coi tên người sửa file cuối cùng là owner mặc định |
| Có đường truy cập được kiểm soát | Kết quả thử quyền đúng/sai, cấu hình truy cập đã đối chiếu | Chỉ chứng minh quản trị viên vault lấy được password |
| Giá trị cũ mất hiệu lực | Sự kiện thay/thu hồi và kiểm tra xác thực theo cách an toàn | Ghi password cũ và mới vào ảnh chụp bằng chứng |
| Consumer hoạt động sau chuyển đổi | Kiểm tra tác vụ, kết nối và lỗi xác thực | Chỉ thử đăng nhập bằng tay mà bỏ qua batch job |
| Có khả năng truy vết | Liên kết yêu cầu, người dùng/workload, phiên và sự kiện đích | Đồng nhất log mở file với log thực hiện thao tác quản trị |
| Có phục hồi phù hợp | Kết quả diễn tập và trách nhiệm xử lý rõ ràng | Giữ một spreadsheet password làm phương án cứu hộ ngầm |

Một hồ sơ chuyển đổi không chứa bí mật có thể chỉ cần các trường:

```yaml
credential_ref: cred-mig-017
owner_team: DataOps
source_ref: legacy-register-01
target_ref: secretref-017
access_test_ref: evidence-access-017
old_credential_invalidation_ref: evidence-revoke-017
consumer_validation_ref: evidence-consumer-017
session_review_ref: evidence-session-017
exception_ref: null
```

Đây là ví dụ cấu trúc hồ sơ, không phải cấu hình chạy của sản phẩm. Các mã bằng chứng tham chiếu đến hệ thống lưu bằng chứng được phân quyền; chúng không chứa credential.

## 9. Xử lý khi phát hiện file đã bị chia sẻ rộng

Giả sử một spreadsheet chứa tài khoản quản trị được gửi cho nhiều bên ngoài phạm vi dự kiến. Các hành động cần phối hợp có thể gồm khoanh vùng đường chia sẻ, xác định credential bị ảnh hưởng, bảo quản dấu vết, thay hoặc thu hồi credential và rà soát hoạt động trên hệ thống đích.

Đánh giá theo loại credential và khả năng ảnh hưởng, thay vì chỉ hỏi file đã được xóa hay chưa. Nếu một password được dùng cho nhiều tài khoản, việc xử lý một dòng chưa đủ. Nếu đã có phiên hoặc token được tạo, cần xem xét chúng riêng.

Trong quá trình điều tra:

- Dùng định danh tài khoản và mã tham chiếu trong trao đổi, không dán bí mật vào chat hoặc ticket.
- Thu thập log truy cập, tải hoặc chia sẻ từ nền tảng chứa file nếu có, rồi đối chiếu với log xác thực và hoạt động đích.
- Xác định khoảng thời gian credential có thể bị tiếp cận và khoảng thời gian còn hiệu lực.
- Ghi nhận những bản sao đã biết, các giới hạn quan sát và phần chưa thể chứng minh.
- Phối hợp với owner để duy trì hoặc khôi phục dịch vụ bằng credential được kiểm soát.

Một sự kiện tải file cho biết cần điều tra thêm, không tự chứng minh người tải đã sử dụng mọi credential. Tương tự, việc không có sự kiện tải có thể do hạn chế ghi log hoặc lưu giữ; không nên suy diễn thành chắc chắn không có bản sao.

## 10. Ngoại lệ phải có giới hạn rõ

Một hệ thống cũ có thể chưa tích hợp được với PAM, hoặc việc thay đổi ứng dụng cần thời gian. Ngoại lệ hợp lý cần mô tả cụ thể điều chưa làm được và cách kiểm soát trong thời gian chờ.

Một hồ sơ ngoại lệ nên nêu tài nguyên, tài khoản, lý do kỹ thuật, owner, người chấp nhận rủi ro, biện pháp giảm thiểu, thời hạn và kế hoạch đóng. Nếu có thể đưa password tĩnh vào vault dù chưa có broker hay rotation tự động, hãy đánh giá phương án đó thay vì coi thiếu tự động hóa là lý do giữ password trong spreadsheet.

Đừng biến ngoại lệ thành một cột `Approved = Yes` tồn tại mãi. Khi hết hạn, phải rà soát lại dependency và khả năng tích hợp, rồi hoàn tất chuyển đổi hoặc ghi nhận quyết định mới theo thẩm quyền.

Đối với trao đổi credential một lần trong quy trình đặc biệt, chọn kênh phân phối được tổ chức cho phép, giới hạn người nhận và thời gian hiệu lực. Không mặc định tính năng tự hết hạn của một đường dẫn có thể làm người nhận quên một password đã xem. Cần xem xét credential sau khi được tiết lộ và thay thế nó khi phù hợp.

## 11. Chỉ số giúp phát hiện việc anti-pattern quay lại

Các chỉ số nên cho biết rủi ro còn lại, thay vì chỉ đếm số file đã xóa:

- Tỷ lệ tài khoản đặc quyền đã xác định owner và dependency trên tổng phạm vi kiểm kê.
- Tỷ lệ credential từng xuất hiện trong spreadsheet đã được thay hoặc thu hồi có bằng chứng.
- Số ngoại lệ còn mở, số ngoại lệ quá hạn và độ nhạy cảm của tài nguyên liên quan.
- Số vị trí phát hiện mới chứa bí mật, kèm thời gian từ phát hiện đến khoanh vùng và xử lý.
- Tỷ lệ đường truy cập đặc quyền được kiểm soát theo thiết kế đã chọn.
- Tỷ lệ kiểm thử break-glass và kiểm thử phục hồi credential đạt yêu cầu.

Cần định nghĩa mẫu số và phạm vi cho từng chỉ số. `100% đã đưa vào vault` trên danh sách mới kiểm kê được không chứng minh đã tìm thấy tất cả tài khoản. Hoạt động rà soát phải tôn trọng quyền truy cập, hạn chế đưa bí mật vào báo cáo và bảo vệ kết quả phát hiện.

## 12. Bài tập áp dụng

Bạn nhận được một bảng có ba dòng:

| Dòng | Mục đích sử dụng | Tình trạng đã biết |
| --- | --- | --- |
| A | Tài khoản quản trị cơ sở dữ liệu production | Bốn quản trị viên và một đối tác từng có quyền đọc file |
| B | Tài khoản dịch vụ chạy báo cáo hằng đêm | Có owner, chưa biết đủ scheduled job phụ thuộc |
| C | Tài khoản cứu hộ cho hệ thống PAM | Password được lưu trong cùng bảng, chưa diễn tập mất dịch vụ danh tính |

Hãy đề xuất cho mỗi dòng: phương thức truy cập đích, dependency cần làm rõ, cách vô hiệu hóa credential cũ và bằng chứng hoàn tất.

Hướng xử lý tham khảo:

- Dòng A: xem xét danh tính cá nhân và truy cập qua PAM với phạm vi, thời hạn phù hợp; rà soát quyền của đối tác; thay password cũ, đánh giá phiên còn hiệu lực và lưu bằng chứng tương quan việc cấp quyền với phiên đích.
- Dòng B: kiểm kê scheduled job và consumer trước thay đổi; thiết kế cách workload nhận credential; phối hợp rotation, thử tác vụ báo cáo và xác nhận credential cũ đã ngừng hiệu lực.
- Dòng C: thiết kế đường khẩn cấp hoạt động trong kịch bản đã xác định; tránh phụ thuộc vòng vào hệ thống đang cần khôi phục; bảo vệ credential cứu hộ theo cơ chế riêng, diễn tập và xác minh lại sau sử dụng.

Trong cả ba trường hợp, chuyển giá trị hiện có vào vault rồi xóa cột password vẫn thiếu bước xử lý giá trị cũ. Ngược lại, đổi password ngay mà không biết dependency có thể gây gián đoạn không cần thiết. Cách thực hiện cần kết hợp kiểm soát phơi lộ, hiểu hệ thống và xác nhận kết quả.

## 13. Những điểm cần nhớ

Spreadsheet phù hợp để ghi metadata được phép lưu, theo dõi owner, dependency và tiến độ onboarding. Khi chứa password, key hoặc token có giá trị sử dụng, nó đang đảm nhận vai trò kho bí mật với các giới hạn về phân phối, thu hồi và truy vết.

Đích đến của chuyển đổi là một vòng đời credential được kiểm soát: danh tính rõ ràng, quyền vừa đủ, thời hạn phù hợp, truy xuất được quản lý, rotation hoặc thu hồi có kiểm chứng, khả năng phục hồi và bằng chứng sử dụng. Vault là một thành phần hỗ trợ vòng đời đó, cần được cấu hình và vận hành phù hợp.

Điểm đóng rủi ro quan trọng là credential từng phát tán không còn giá trị sử dụng, consumer hoạt động qua đường được kiểm soát và những phiên hoặc quyền còn tồn tại đã được đánh giá. Việc loại bỏ password khỏi bảng tính phải đi cùng thay đổi quy trình bàn giao để anti-pattern không tái xuất hiện.

