# Đã có break-glass

## 1. Mục tiêu của hạng mục trong checklist production

Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), break-glass là cơ chế truy cập khẩn cấp được chuẩn bị trước để xử lý tình huống đường quản trị thông thường không còn dùng được hoặc không đáp ứng kịp yêu cầu khôi phục. Ví dụ: nhà cung cấp danh tính không xác thực được quản trị viên, cổng PAM mất khả dụng, hệ thống MFA gặp sự cố, hoặc một thay đổi sai khiến mọi vai trò quản trị hợp lệ đều bị khóa.

Hạng mục **“Đã có break-glass”** chỉ đạt khi tổ chức chứng minh được một người có trách nhiệm, trên một thiết bị và đường kết nối được xác định, có thể sử dụng quyền khẩn cấp để hoàn thành một tác vụ khôi phục cần thiết trong thời gian chấp nhận được, đồng thời để lại bằng chứng và kết thúc quyền truy cập đó.

Có sẵn một tài khoản quản trị dự phòng chưa đủ. Một mật khẩu được cất trong phong bì cũng chưa chứng minh rằng tài khoản đăng nhập được, rằng quyền của nó còn đúng, hay rằng người trực ca biết lấy phong bì ở đâu.

Bài học tập trung vào việc nghiệm thu khả năng break-glass trước khi đưa PAM vào production. Mục tiêu là chuyển một ô đánh dấu thành một tập điều kiện có thể kiểm chứng: có đường vào, có quyền đúng việc, có người vận hành, có dấu vết và có cách đóng đường khẩn cấp sau khi sử dụng.

### Kết quả người học cần đạt

Sau bài học, người học có thể:

- Phân biệt break-glass với tài khoản quản trị thường trực, quyền JIT và một cơ chế dự phòng đơn thuần.
- Nhận diện các phụ thuộc khiến đường truy cập khẩn cấp cùng hỏng với đường truy cập chính.
- Xây dựng tiêu chí nghiệm thu, kịch bản diễn tập và gói bằng chứng cho hạng mục production.
- Mô tả cách phê duyệt, kích hoạt, giám sát, thu hồi, luân chuyển credential và rà soát sau sự kiện.
- Đưa ra kết luận đạt, chưa đạt hoặc chấp nhận rủi ro có điều kiện dựa trên bằng chứng cụ thể.

## 2. Break-glass giải quyết bài toán nào?

### 2.1. Tình huống điển hình

Một doanh nghiệp cho quản trị viên đăng nhập bằng tài khoản cá nhân qua IdP, xác thực MFA, sau đó mở phiên quản trị qua PAM. PAM lấy credential từ vault và kết nối tới máy đích.

Đường thông thường có thể được mô tả như sau:

```text
Quản trị viên
  → thiết bị quản trị
  → DNS và mạng
  → IdP + MFA
  → cổng PAM
  → vault / hệ thống bảo vệ khóa
  → máy đích
```

Nếu IdP bị lỗi và tài khoản khẩn cấp vẫn bắt buộc đi qua cùng IdP, tài khoản đó không giúp khôi phục được gì. Nếu mật khẩu truy cập vault được lưu duy nhất bên trong chính vault đang cần sửa, tổ chức có một phụ thuộc vòng.

Break-glass phải cắt được phụ thuộc gây ra kịch bản sự cố đã chọn. Không cần và thường không thể tạo một đường hoàn toàn độc lập với mọi thành phần. Cần chỉ rõ đường đó chịu được loại lỗi nào và còn phụ thuộc vào những thành phần nào.

### 2.2. Phân biệt với các cơ chế gần giống

| Cơ chế | Mục đích chính | Điều kiện sử dụng | Điều cần kiểm tra |
|---|---|---|---|
| Truy cập PAM thông thường | Thực hiện công việc quản trị hàng ngày | Theo quy trình tác nghiệp thường lệ | Danh tính cá nhân, phê duyệt, quyền và giám sát |
| JIT/JEA | Cấp quyền đúng lúc, đúng tác vụ, trong phạm vi hạn chế | Khi hệ thống cấp quyền và thực thi chính sách hoạt động | Quyền thực sự được giới hạn và kết thúc đúng hạn |
| PAM có tính sẵn sàng cao | Duy trì dịch vụ khi một thành phần hoặc vùng lỗi | Theo cơ chế chuyển đổi dự phòng của kiến trúc | Khả năng chuyển đổi và các phụ thuộc chung |
| Break-glass | Khôi phục khi đường quản trị thông thường không sử dụng được trong tình huống đã định | Theo tiêu chí khẩn cấp và thẩm quyền được chuẩn bị trước | Đường truy cập thay thế, tác vụ khôi phục, bằng chứng và thu hồi |
| Tài khoản quản trị dùng chung thường trực | Cho nhiều người dùng một danh tính đặc quyền | Thường bị sử dụng như lối tắt hằng ngày | Khó quy trách nhiệm và dễ biến thành quyền tồn tại lâu dài |

HA giảm nhu cầu dùng break-glass nhưng không thay thế break-glass. Hai cụm PAM có thể cùng phụ thuộc vào một IdP hoặc một hệ thống khóa. Ngược lại, break-glass không thay thế việc thiết kế HA, sao lưu hoặc khôi phục thảm họa.

Một vai trò JIT có thể phục vụ truy cập khẩn cấp nếu vẫn cấp và thu hồi được khi kịch bản sự cố xảy ra. Nếu cơ chế JIT nằm trong thành phần đang hỏng, cần một phương án khác đã được phê duyệt.

## 3. Xác định phạm vi trước khi tạo tài khoản

Không nên bắt đầu bằng yêu cầu “tạo một super-admin dự phòng”. Trước hết cần xác định tài sản phải cứu, tác vụ phải làm và loại lỗi phải chịu được.

### 3.1. Lập danh sách tác vụ khôi phục tối thiểu

Các tác vụ có thể bao gồm:

- Khôi phục một cấu hình xác thực hoặc phân quyền bị thay đổi sai.
- Đăng nhập vào nền tảng PAM để sửa cấu hình kết nối với IdP.
- Truy cập hệ thống quản trị ngoài băng để phục hồi một máy hoặc thiết bị mạng.
- Khôi phục một vai trò quản trị nền tảng bị gỡ nhầm.
- Lấy bản sao lưu phù hợp và khởi động quy trình phục hồi đã được kiểm thử.
- Chặn một phiên hoặc credential đặc quyền đang bị lạm dụng khi đường điều khiển chính gặp sự cố.

Mỗi tác vụ phải gắn với một phạm vi cụ thể. Quyền khẩn cấp để sửa PAM không tự động đồng nghĩa với quyền đọc toàn bộ dữ liệu nghiệp vụ. Quyền khôi phục một tenant không có nghĩa là được quản trị mọi tenant.

### 3.2. Mẫu kiểm kê đường break-glass

| Thuộc tính | Ví dụ minh họa |
|---|---|
| Mã đường khẩn cấp | BG-PAM-ADMIN-01 |
| Tài sản cần khôi phục | Mặt phẳng quản trị PAM production |
| Kịch bản được bao phủ | IdP không khả dụng; cấu hình federation sai |
| Hành động được phép | Khôi phục cấu hình xác thực đã được duyệt |
| Danh tính đích | Tài khoản khẩn cấp chuyên dụng theo cơ chế nền tảng |
| Phụ thuộc còn lại | Thiết bị quản trị, mạng quản trị, PAM, credential khẩn cấp |
| Người có thể kích hoạt | Nhóm trực ca đã được chỉ định |
| Người giữ phương tiện truy cập | Nhóm quản lý credential khẩn cấp |
| Nơi lưu runbook | Kho tài liệu khẩn cấp có thể truy cập khi IdP lỗi |
| Giới hạn đã biết | Không giải quyết trường hợp toàn bộ PAM và mạng quản trị cùng mất |
| Cách kết thúc | Đóng phiên, thu hồi khả năng truy cập, xử lý credential theo loại |

Ví dụ này cố ý không coi BG-PAM-ADMIN-01 là giải pháp cho mọi lỗi. Trường hợp PAM bị phá hủy cần đường khôi phục hạ tầng và dữ liệu riêng; trường hợp nhà cung cấp nền tảng mất dịch vụ có thể cần quy trình hỗ trợ của nhà cung cấp.

### 3.3. Phân tầng theo miền tin cậy

Nên đánh giá riêng các đường khẩn cấp của:

- Hạ tầng danh tính: IdP, directory và cơ chế xác thực.
- PAM/vault và hệ thống bảo vệ khóa.
- Nền tảng cloud, ảo hóa hoặc hệ thống quản trị vật lý.
- Mạng quản trị, bastion và truy cập ngoài băng.
- Các hệ thống đích quan trọng được đưa vào phạm vi.

Một credential có khả năng mở mọi tầng sẽ tạo ra phạm vi ảnh hưởng rất lớn. Nếu cần một quyền có phạm vi rộng để cứu mặt phẳng quản trị, phải ghi rõ lý do, kiểm soát lưu giữ, người được tiếp cận và điều kiện sử dụng; không mặc định mở rộng quyền cho mọi đường break-glass.

## 4. Kiểm tra sự độc lập theo từng kịch bản lỗi

### 4.1. Ma trận phụ thuộc

Ma trận sau là gợi ý thiết kế kiểm thử, không phải yêu cầu bỏ qua tất cả các cơ chế xác thực khi xảy ra sự cố.

| Thành phần gặp sự cố | Bẫy thường gặp | Điều cần chứng minh |
|---|---|---|
| IdP hoặc federation | Tài khoản khẩn cấp vẫn chuyển hướng tới IdP đó | Cơ chế xác thực thay thế hoạt động theo thiết kế và chính sách đã duyệt |
| Dịch vụ MFA | Phương tiện khẩn cấp vẫn gọi cùng dịch vụ đang lỗi | Phương thức xác thực khẩn cấp khả dụng; không vô hiệu hóa MFA đại trà |
| Cổng PAM | Mọi tài liệu và credential khẩn cấp chỉ lấy được qua cổng PAM | Có phương án khôi phục hoặc đường quản trị khác đúng phạm vi |
| Vault | Credential cứu vault nằm duy nhất trong vault | Có phương tiện khôi phục được bảo vệ và đã kiểm chứng ngoài phụ thuộc vòng |
| KMS/HSM hoặc vật liệu khóa | Bản sao lưu tồn tại nhưng không giải mã được | Khôi phục được dữ liệu cùng các điều kiện truy cập khóa cần thiết |
| DNS, VPN hoặc mạng quản trị | Đường dự phòng dùng cùng thành phần mạng bị hỏng | Tên miền, định tuyến và đường kết nối thay thế phù hợp với kịch bản |
| SIEM hoặc nơi nhận log | Không có thông báo và không biết ai đã dùng tài khoản | Có ghi nhận tại nguồn, thông báo thay thế và đối soát sau khi kết nối trở lại |
| Người giữ credential vắng mặt | Chỉ một người biết vị trí hoặc cách mở kho | Người thay thế được xác định và kiểm tra được khả năng nhận nhiệm vụ |

Không được “kiểm thử IdP down” bằng cách chỉ tắt một chính sách đăng nhập trong khi trình duyệt vẫn còn phiên SSO hợp lệ. Cần bảo đảm phép thử thực sự loại bỏ phụ thuộc đang đánh giá, ví dụ dùng phiên đăng nhập mới và mô phỏng lỗi tại môi trường kiểm thử phù hợp.

### 4.2. Đường ngoài băng cũng có phụ thuộc

Console quản trị vật lý hoặc cloud console không tự động độc lập. Nó có thể vẫn cần điện, mạng, tài khoản nền tảng, thiết bị xác thực hoặc quyền truy cập phòng máy.

Khi ghi “có console”, cần ghi thêm:

- Console nào và áp dụng cho tài sản nào.
- Ai có quyền mở console.
- Credential hoặc phương tiện xác thực nằm ở đâu.
- Cách tới console khi VPN hay directory gặp lỗi.
- Console cho phép hoàn thành tác vụ khôi phục nào.
- Nhật ký hoặc bằng chứng phiên được lưu ở đâu.

Nếu một bước phụ thuộc vào nhà cung cấp, thời gian phản hồi và cách liên hệ cũng là một phần của giả định phục hồi. Không tính đó là khả năng đã có sẵn trong tay đội trực ca nếu chưa xác minh.

## 5. Thiết kế danh tính và credential khẩn cấp

### 5.1. Danh tính chuyên dụng, có chủ sở hữu

Mỗi danh tính khẩn cấp cần có:

- Mã định danh, phạm vi tài sản và mục đích.
- Chủ sở hữu nghiệp vụ hoặc nền tảng chịu trách nhiệm.
- Người quản lý vòng đời và người kiểm tra độc lập.
- Trạng thái thường lệ: được bật, bị vô hiệu hóa hay chỉ có thể kích hoạt qua một cơ chế xác định.
- Phương thức xác thực và nơi lưu phương tiện truy cập.
- Điều kiện kích hoạt và quy trình kết thúc.
- Chu kỳ rà soát và ngày kiểm thử thành công gần nhất.

Trạng thái thường lệ phụ thuộc thiết kế. Một tài khoản bị vô hiệu hóa mà chỉ có thể bật bằng chính IdP đang lỗi không đáp ứng kịch bản IdP down. Một tài khoản luôn bật có thể tránh phụ thuộc đó nhưng làm tăng nhu cầu bảo vệ credential, hạn chế đường truy cập và phát hiện mọi lần sử dụng.

Không có một trạng thái mặc định phù hợp cho mọi nền tảng. Lựa chọn phải được giải thích bằng kịch bản lỗi và được thử nghiệm.

### 5.2. Ưu tiên truy nguyên người thực hiện

Nếu nền tảng hỗ trợ, dùng danh tính cá nhân hoặc cơ chế cấp quyền có thể gắn người dùng với phiên khẩn cấp. Khi buộc phải dùng một tài khoản khẩn cấp dùng chung, cần nối được chuỗi bằng chứng:

```text
Người nhận nhiệm vụ
  → quyết định kích hoạt
  → sự kiện nhận credential / phương tiện xác thực
  → phiên trên hệ thống đích
  → hành động khôi phục
  → thu hồi và xác nhận kết thúc
```

Log “emergency-admin đăng nhập” không đủ để kết luận người nào thực hiện. Cần sự kiện bàn giao, mã sự cố, thiết bị nguồn và các bằng chứng liên quan. Nếu có nhiều người cùng dùng một credential, phải xử lý rõ cách phân biệt phiên; không phỏng đoán danh tính từ tên tài khoản.

### 5.3. Bảo vệ phương tiện truy cập

Tùy kiến trúc, phương tiện có thể là credential được lưu trong kho độc lập, thiết bị xác thực, vật liệu khôi phục hoặc một quy trình phục hồi do nền tảng hỗ trợ.

Các nguyên tắc vận hành cần kiểm tra:

- Vị trí lưu đủ độc lập với lỗi dự kiến nhưng vẫn nằm trong kiểm soát của tổ chức.
- Người mở kho được xác thực; sự kiện mở và bàn giao được ghi nhận.
- Không để cùng một cá nhân có thể âm thầm lấy mọi yếu tố nếu thiết kế yêu cầu phân tách trách nhiệm.
- Có phương án cho người giữ vắng mặt, mất thiết bị hoặc thay đổi nhân sự.
- Bản sao khẩn cấp và phương tiện dự phòng được kiểm kê; không có bản sao vô chủ.
- Credential, mã khôi phục và khóa riêng không xuất hiện trong ticket, ảnh chụp, chat hoặc gói bằng chứng.
- Runbook chứa định vị và thao tác nhận phương tiện, không chứa trực tiếp bí mật.

Hai người phê duyệt không tương đương với chia sẻ mật mã theo ngưỡng; hai kho lưu cũng không tự động tạo thành kiểm soát hai người. Cần mô tả đúng cơ chế đang áp dụng và những hành động một người có thể tự làm.

### 5.4. Không quên vòng đời của credential

Credential có thể hết hạn, bị thay đổi bởi chính sách, bị khóa sau nhiều lần đăng nhập sai hoặc mất hiệu lực khi nền tảng được phục hồi từ bản sao lưu. Phương tiện xác thực có thể hỏng hoặc không còn tương thích.

Vì vậy, cần kiểm tra định kỳ khả năng sử dụng, đối chiếu trạng thái tại hệ thống đích và cập nhật phương án sau thay đổi. Chỉ kiểm tra “đã có một mục trong vault” không phát hiện được các lỗi này.

## 6. Quyền khẩn cấp phải gắn với tác vụ khôi phục

### 6.1. Least privilege vẫn áp dụng

Tác vụ khôi phục thường cần quyền mạnh, nhưng không vì vậy mà bỏ qua việc xác định phạm vi. Với mỗi quyền cần trả lời:

1. Quyền đó dùng cho hành động khôi phục nào?
2. Có cách thực hiện với quyền hẹp hơn không?
3. Nó tác động tới tài sản, tenant hoặc môi trường nào?
4. Có thể giới hạn thiết bị nguồn, đường kết nối hoặc thời gian sử dụng không?
5. Làm thế nào chứng minh quyền đã hết sau khi xử lý?

JEA phù hợp khi có thể giới hạn tập lệnh hoặc thao tác khôi phục. Tuy nhiên, lớp giới hạn đó cũng phải khả dụng trong kịch bản lỗi. Không tuyên bố đã có JEA nếu tài khoản vẫn có một đường khác để thực thi toàn bộ quyền quản trị.

### 6.2. Thời hạn yêu cầu và thời hạn thực thi là hai việc khác nhau

Ticket ghi “quyền có hiệu lực 60 phút” chỉ là một quy định vận hành nếu không có cơ chế thực thi tương ứng.

Cần phân biệt:

- Thời hạn phê duyệt: khoảng thời gian được phép sử dụng.
- Thời hạn credential hoặc token: khi phương tiện xác thực hết hiệu lực.
- Thời hạn quyền: khi vai trò hoặc nhóm đặc quyền bị thu hồi.
- Thời hạn phiên: khi phiên đang hoạt động bị đóng hoặc mất quyền.
- Thời điểm xác nhận kết thúc: khi đội vận hành có bằng chứng đã kiểm tra trạng thái thực tế.

Những mốc này có thể khác nhau. Thu hồi một vai trò chưa chắc đóng mọi phiên; đổi mật khẩu chưa chắc hủy mọi token hoặc kết nối đang mở. Cách thực thi phụ thuộc nền tảng và phải được thử với đúng loại phiên sử dụng.

### 6.3. Kế hoạch thu hồi là điều kiện trước khi kích hoạt

Trước khi mở quyền khẩn cấp, runbook phải chỉ rõ cách:

- Ngăn đăng nhập mới.
- Xử lý các phiên và token đã cấp theo cơ chế nền tảng.
- Loại bỏ quyền hoặc thành viên nhóm tạm thời.
- Thu hồi phương tiện đã bàn giao.
- Luân chuyển credential có khả năng đã lộ hoặc đã được dùng.
- Kiểm tra tác động tới dịch vụ phụ thuộc trước khi thay secret dùng chung.
- Xác nhận hệ thống quay lại đường quản trị thông thường.

Nếu không thể tự động kết thúc một loại phiên, phải có bước thủ công được giao cho người cụ thể, thời hạn, cách kiểm tra và cơ chế nhắc hoặc escalations. Không gọi một biện pháp thủ công là “tự động hết quyền”.

## 7. Phê duyệt và phân công khi đường thông thường bị lỗi

Một quy trình khẩn cấp cần bảo đảm kiểm soát nhưng vẫn thực hiện được khi hệ thống phê duyệt hoặc người phê duyệt thông thường không khả dụng.

### 7.1. Xác định tiêu chí kích hoạt

Tiêu chí nên dựa trên tình huống cụ thể, chẳng hạn:

- Không thể quản trị một hệ thống quan trọng qua đường thông thường.
- Chậm khôi phục có nguy cơ vượt thời gian gián đoạn mà dịch vụ chấp nhận.
- Một sự cố an ninh cần hành động khẩn cấp, trong khi đường quản trị chính không dùng được.
- Cần phục hồi một thay đổi sai làm mất quyền điều khiển.

“Đang bận”, “không muốn chờ phê duyệt” hoặc “đường thường hơi chậm” không tự động là lý do kích hoạt.

Ngưỡng thời gian và mức độ sự cố do tổ chức quyết định theo dịch vụ. Không lấy số phút trong ví dụ đào tạo làm tiêu chuẩn bắt buộc.

### 7.2. Các vai trò tối thiểu

| Vai trò | Trách nhiệm |
|---|---|
| Người chỉ huy hoặc điều phối sự cố | Xác nhận tình huống, phạm vi, ưu tiên và quyết định kích hoạt theo chính sách |
| Người phê duyệt khẩn cấp | Chấp thuận phạm vi và thời gian; áp dụng tuyến thay thế nếu được ủy quyền |
| Người thực hiện | Nhận quyền, làm đúng tác vụ, ghi lại thay đổi và bàn giao |
| Người giữ phương tiện truy cập | Xác minh điều kiện bàn giao, ghi nhận ai nhận và khi nào |
| Người giám sát hoặc ghi chép | Theo dõi sử dụng, lưu timeline và các bằng chứng được phép |
| Chủ hệ thống | Xác nhận chức năng đã khôi phục và tác động của thay đổi |
| Người rà soát sau sự kiện | Đối soát quyền, hành động, credential và cải tiến quy trình |

Tổ chức nhỏ có thể phải kiêm nhiệm một số vai trò. Khi đó cần xác định xung đột lợi ích và biện pháp bù đắp phù hợp, chẳng hạn rà soát độc lập sau sự kiện. Không ghi “đủ phân tách” nếu thực tế một người tự phê duyệt, tự lấy credential và tự xác nhận mọi bằng chứng.

### 7.3. Phương án khi không liên lạc được người phê duyệt

Chính sách phải có tuyến thay thế, điều kiện sử dụng và giới hạn quyền rõ ràng. Nếu có cơ chế cho phép hành động ngay theo thẩm quyền khẩn cấp được phê duyệt trước, cần quy định cách ghi nhận lý do, thông báo và rà soát sau đó.

Phê duyệt bổ sung sau sự kiện chỉ hợp lệ khi chính sách đã cho phép hình thức đó trong tình huống tương ứng. Không dùng việc bổ sung ticket sau này để hợp thức hóa một hành động vượt thẩm quyền.

Kênh liên lạc thay thế cũng phải được xác thực. Một cuộc gọi tự xưng là người chỉ huy không đủ; cần cách kiểm tra người gọi theo danh bạ hoặc cơ chế xác minh đã chuẩn bị.

## 8. Runbook phải sử dụng được trong lúc căng thẳng

Runbook cần đủ cụ thể để một người trực ca đã được đào tạo có thể thực hiện mà không cần tác giả ngồi cạnh.

### 8.1. Nội dung bắt buộc của runbook

1. Mã runbook, chủ sở hữu, phiên bản và ngày kiểm thử.
2. Tài sản và kịch bản lỗi được bao phủ.
3. Dấu hiệu đủ điều kiện kích hoạt và các trường hợp không áp dụng.
4. Danh sách vai trò cùng tuyến liên hệ thay thế.
5. Vị trí tài liệu, thiết bị và phương tiện truy cập khẩn cấp.
6. Các điều kiện ban đầu và cách xác minh danh tính người tham gia.
7. Trình tự phê duyệt, nhận quyền, mở phiên và ghi nhận mã sự cố.
8. Tác vụ khôi phục được phép cùng điểm dừng nếu kết quả khác dự kiến.
9. Kiểm tra chức năng sau thay đổi và phương án quay lui nếu có thể.
10. Đóng phiên, thu hồi quyền, xử lý credential và bàn giao.
11. Cách thu thập, bảo vệ và đối soát bằng chứng.
12. Người xác nhận kết thúc và bước rà soát sau sự kiện.

Các lệnh hoặc thao tác phụ thuộc sản phẩm phải được đội sở hữu nền tảng xác nhận và thử nghiệm trong môi trường thích hợp. Không sao chép một lệnh thay đổi quyền từ ví dụ chung rồi coi là runbook production.

### 8.2. Khả năng tiếp cận runbook

Có tài liệu trên wiki nhưng wiki yêu cầu đăng nhập qua IdP đang hỏng là một lỗi thiết kế. Cần chuẩn bị bản khẩn cấp được quản lý phiên bản và có thể truy cập trong kịch bản đã chọn.

Bản ngoại tuyến cũng cần kiểm soát: ai được giữ, khi nào cập nhật, làm sao nhận biết bản cũ và cách thu hồi khi người giữ đổi vai trò. Không đưa bí mật vào bản in chỉ để tiện thao tác.

## 9. Giám sát và bằng chứng trong điều kiện suy giảm

### 9.1. Phải phát hiện cả hoạt động bất thường lẫn hoạt động hợp lệ

Nên ghi nhận các sự kiện liên quan đến:

- Mở hoặc thay đổi nơi lưu phương tiện truy cập khẩn cấp.
- Thay đổi cấu hình, quyền hoặc phương thức xác thực của danh tính khẩn cấp.
- Thử đăng nhập thất bại, đăng nhập thành công và mở phiên.
- Kích hoạt hoặc kéo dài quyền tạm thời.
- Hành động khôi phục quan trọng.
- Kết thúc phiên, thu hồi quyền và luân chuyển credential.
- Thất bại của chính cơ chế ghi log hoặc thông báo.

Một lần đăng nhập hợp lệ vẫn cần thông báo để đội an ninh biết break-glass đang được sử dụng. Cảnh báo “đã được phê duyệt” có thể mang cách xử lý khác cảnh báo không có mã sự cố; không nên tắt toàn bộ phát hiện chỉ vì đang có diễn tập.

### 9.2. Khi SIEM không khả dụng

Mất SIEM không nhất thiết đồng nghĩa với mất toàn bộ khả năng ghi nhận. Có thể còn log tại hệ thống đích, thiết bị quản trị, cổng ngoài băng hoặc một kênh thu thập độc lập.

Runbook cần quy định:

- Nguồn nào vẫn ghi được log.
- Dung lượng, thời gian lưu và cách bảo vệ log tại nguồn.
- Kênh thông báo thay thế cho người chịu trách nhiệm.
- Cách ghi timeline nếu hệ thống ticket cũng lỗi.
- Cách đưa bằng chứng vào kho tập trung khi dịch vụ hoạt động lại.
- Cách đánh dấu các khoảng trống quan sát.

Nếu nguồn thời gian không đồng bộ, lưu cả dấu thời gian gốc và sai lệch đã biết khi đối soát. Không chỉnh sửa âm thầm log gốc để làm timeline trông liền mạch.

### 9.3. Bảo vệ bằng chứng

Gói bằng chứng nên lưu mã sự cố, người thực hiện, phạm vi được duyệt, thời gian, mã phiên, thay đổi và kết quả thu hồi. Tránh lưu secret hoặc dữ liệu nhạy cảm không cần thiết.

Kiểm soát truy cập và lưu trữ hạn chế sửa đổi giúp bảo vệ bằng chứng. Giá trị băm hỗ trợ phát hiện một bản sao bị thay đổi so với giá trị đã lưu tin cậy; tự tạo một tệp và giá trị băm bên cạnh không chứng minh ai đã tạo tệp hoặc rằng dữ liệu gốc là đúng.

Nếu không có session recording trong đường khẩn cấp, phải nói rõ khoảng trống và cơ chế thay thế đã được chấp thuận. Không gắn nhãn “ghi hình đầy đủ” cho một timeline được viết thủ công.

## 10. Diễn tập để chứng minh khả năng khôi phục

### 10.1. Chọn cấp độ diễn tập

- **Tabletop:** đi qua tình huống, vai trò, liên lạc và quyết định. Phù hợp để tìm lỗ hổng quy trình nhưng chưa chứng minh đăng nhập hay quyền thực tế.
- **Kiểm thử kỹ thuật trong môi trường kiểm thử:** mô phỏng lỗi, xác thực, cấp quyền, khôi phục, cảnh báo và thu hồi. Cần ghi rõ mức tương đồng với production.
- **Kiểm tra có kiểm soát tại production:** xác minh những phần chỉ có thể chứng minh tại đích thật, theo phạm vi và cửa sổ đã phê duyệt.

Không tạo sự cố trên production chỉ để hoàn thành checklist. Phép thử ảnh hưởng dịch vụ phải có phạm vi, điều kiện dừng, người điều phối và phương án khôi phục được chấp thuận trước.

Kết quả từ môi trường kiểm thử không tự động chứng minh credential production còn dùng được. Cần xác định phần nào được kiểm chứng trực tiếp và phần nào vẫn là giả định hoặc chênh lệch môi trường.

### 10.2. Bộ kịch bản nghiệm thu gợi ý

| Mã | Kịch bản | Bằng chứng đạt |
|---|---|---|
| BG-T01 | IdP không thể phục vụ đăng nhập mới | Người được chỉ định vào được theo đường thay thế; không dùng phiên SSO còn hiệu lực để che phụ thuộc |
| BG-T02 | Người giữ phương tiện chính vắng mặt | Người thay thế nhận và dùng được phương tiện theo đúng thẩm quyền |
| BG-T03 | Thực hiện tác vụ khôi phục tối thiểu | Tác vụ thành công trên đúng phạm vi; chức năng sau phục hồi được xác nhận |
| BG-T04 | Người không có thẩm quyền yêu cầu sử dụng | Yêu cầu bị từ chối, có ghi nhận, không được bàn giao bí mật |
| BG-T05 | Đã quá thời gian hoặc yêu cầu vượt phạm vi | Hệ thống hoặc quy trình thực thi giới hạn đúng như thiết kế; mọi hạn chế được ghi rõ |
| BG-T06 | Kết thúc phiên và thu hồi quyền | Đăng nhập mới không còn được phép theo trạng thái dự kiến; các phiên/token thuộc phạm vi được xử lý và kiểm tra |
| BG-T07 | SIEM hoặc kênh thông báo chính bị lỗi | Có bằng chứng tại nguồn, thông báo thay thế và đối soát sau khi khôi phục |
| BG-T08 | Credential hoặc phương tiện đã được thay | Phương tiện mới hoạt động; phương tiện cũ bị vô hiệu theo đúng loại credential và hành vi phiên đã được xác minh |

Các thử nghiệm từ chối không nên khóa tài khoản cứu hộ thật hoặc làm cạn phương tiện khôi phục dùng một lần. Chọn cách thử phù hợp trong môi trường kiểm thử, hoặc dùng kiểm tra cấu hình kết hợp phép thử production được duyệt.

### 10.3. Đo thời gian theo các mốc rõ ràng

Một diễn tập có thể ghi:

```text
t0: Xác nhận đường quản trị thông thường không dùng được
t1: Quyết định kích hoạt break-glass
t2: Người thực hiện nhận đủ phương tiện và điều kiện truy cập
t3: Đăng nhập được vào phạm vi khẩn cấp
t4: Hoàn thành tác vụ khôi phục và xác nhận chức năng
t5: Đóng phiên, thu hồi và kiểm tra trạng thái kết thúc
```

Từ đó:

- Thời gian tới truy cập hữu dụng: `t3 - t0`.
- Thời gian tới hoàn thành khôi phục trong kịch bản: `t4 - t0`.
- Thời gian đóng quyền sau phục hồi: `t5 - t4`.

Chỉ số thứ nhất không thay thế thời gian khôi phục dịch vụ. Đăng nhập nhanh nhưng không đủ quyền sửa lỗi vẫn là thất bại đối với tác vụ khôi phục.

Mọi mục tiêu thời gian cần được chủ dịch vụ chấp thuận. Một kết quả diễn tập không bảo đảm mọi sự cố thực tế đều đạt cùng thời gian.

## 11. Ví dụ nghiệm thu cho một đường khẩn cấp

Giả sử một nền tảng đặt mục tiêu minh họa: đội trực ca phải có truy cập quản trị hữu dụng trong 20 phút kể từ khi xác nhận lỗi IdP. Đây là mục tiêu giả định của ví dụ, không phải chuẩn chung cho PAM.

Phạm vi là khôi phục cấu hình federation của PAM. Đường break-glass dùng một cơ chế xác thực cục bộ mà nền tảng hỗ trợ, thiết bị quản trị được chỉ định và mạng quản trị riêng. Nó vẫn phụ thuộc vào PAM và không bao phủ tình huống PAM mất toàn bộ dữ liệu.

### 11.1. Diễn biến kiểm thử

1. Đội kiểm thử mô phỏng lỗi IdP ở môi trường kiểm thử, bảo đảm dùng phiên đăng nhập mới.
2. Người trực ca xác nhận lỗi và khởi tạo hồ sơ sự cố qua kênh được chỉ định.
3. Người phê duyệt thay thế xác nhận phạm vi vì người phê duyệt chính không tham gia diễn tập.
4. Người giữ phương tiện kiểm tra danh tính và bàn giao theo quy trình.
5. Người thực hiện mở phiên, ghi mã phiên và thực hiện tác vụ khôi phục được duyệt.
6. Chủ hệ thống xác nhận đường federation hoạt động lại.
7. Đội vận hành đóng phiên khẩn cấp, xử lý credential và kiểm tra các quyền còn lại.
8. Người rà soát đối chiếu timeline, log và các bước thu hồi.

### 11.2. Kết quả cần đánh giá

| Tiêu chí | Kết quả ví dụ | Nhận định |
|---|---|---|
| Truy cập hữu dụng trong mục tiêu | 14 phút | Đạt mục tiêu của ví dụ |
| Người thay thế thực hiện được vai trò | Có bằng chứng xác minh và bàn giao | Đạt |
| Tác vụ khôi phục hoàn thành | Có xác nhận chức năng | Đạt trong phạm vi thử |
| Cảnh báo tới đội an ninh | Kênh chính lỗi, kênh thay thế hoạt động | Đạt nếu phù hợp thiết kế đã duyệt |
| Thu hồi phiên | Một phiên vẫn còn hoạt động sau khi đổi credential | Chưa đạt |
| Phương tiện cũ | Đăng nhập mới bằng phương tiện cũ bị từ chối | Chỉ chứng minh được phần đăng nhập mới |

Kết luận: đường khẩn cấp chưa thể được nghiệm thu đầy đủ vì cơ chế kết thúc phiên chưa đạt. Không cộng các tiêu chí thành một tỷ lệ rồi bỏ qua lỗi thu hồi.

Đội nền tảng cần bổ sung bước kết thúc hoặc vô hiệu hóa phiên theo khả năng thực tế của sản phẩm, cập nhật runbook và kiểm thử lại phần lỗi cùng các phần bị ảnh hưởng. Việc sửa ticket thành “đã đóng” không giải quyết phiên còn tồn tại.

## 12. Mẫu hồ sơ bằng chứng cho checklist

Mẫu dưới đây là cấu trúc hồ sơ minh họa, không phải cấu hình để nạp vào một sản phẩm PAM. Hồ sơ thật phải tham chiếu bằng chứng đã tồn tại và không chứa credential.

```yaml
controlId: BG-PAM-ADMIN-01
scope:
  environment: production
  target: pam-control-plane
  recoveryTask: restore-federation-configuration
coveredFailureModes:
  - identity-provider-unavailable
  - federation-misconfiguration
remainingDependencies:
  - approved-admin-workstation
  - management-network
  - pam-service
authority:
  activationPolicyRef: POLICY-EMERGENCY-ACCESS
  primaryRole: incident-commander
  alternateRole: delegated-duty-manager
access:
  runbookRef: RUNBOOK-BG-PAM-ADMIN
  credentialRecordRef: CUSTODY-BG-01
  targetRoleRef: ROLE-PAM-RECOVERY
  credentialValueIncluded: false
validation:
  exerciseRef: EXERCISE-BG-017
  targetVerificationRef: EVIDENCE-BG-017-TARGET
  positiveAccessTest: PASS
  unauthorizedRequestTest: PASS
  recoveryTaskTest: PASS
  alertDeliveryTest: PASS
  sessionRevocationTest: FAIL
  credentialRetirementTest: PASS
closure:
  findingRef: FINDING-BG-SESSION-01
  ownerRole: pam-platform-owner
  retestRequired: true
decision:
  state: NOT_READY
  reason: emergency-session-remains-active-after-closure
```

Một hồ sơ ghi tất cả giá trị `PASS` nhưng không có nguồn chứng minh không phải bằng chứng nghiệm thu. Nếu phép thử chưa được làm, dùng trạng thái thể hiện đúng việc đó thay vì suy ra thành công từ cấu hình dự kiến.

Hồ sơ kiểm thử cần gắn với phiên bản runbook và cấu hình có liên quan. Sau thay đổi lớn, kết quả cũ vẫn hữu ích để truy vết nhưng không mặc nhiên chứng minh cấu hình mới.

## 13. Checklist quyết định trước production

### 13.1. Khả năng sử dụng

- [ ] Có danh sách tài sản, tác vụ khôi phục và kịch bản lỗi cần bao phủ.
- [ ] Mỗi đường break-glass có chủ sở hữu và giới hạn được ghi rõ.
- [ ] Credential hoặc phương tiện xác thực tại đích còn hiệu lực.
- [ ] Người trực ca và người thay thế tiếp cận được runbook, thiết bị và phương tiện.
- [ ] Đã kiểm thử đường truy cập trong điều kiện mô phỏng lỗi tương ứng.
- [ ] Đã hoàn thành tác vụ khôi phục hữu ích, không chỉ đăng nhập thành công.
- [ ] Thời gian đo được phù hợp mục tiêu đã được chủ dịch vụ chấp thuận.

### 13.2. Kiểm soát và trách nhiệm

- [ ] Có tiêu chí kích hoạt, phạm vi quyền, thời hạn và tuyến thẩm quyền thay thế.
- [ ] Phương tiện truy cập được bảo vệ; quá trình bàn giao truy nguyên được.
- [ ] Quyền phù hợp tác vụ và không tự mở rộng sang tài sản khác.
- [ ] Hoạt động dùng break-glass tạo thông báo tới người có trách nhiệm.
- [ ] Có cách lưu bằng chứng khi một phần hạ tầng log hoặc ticket bị lỗi.
- [ ] Các khoảng trống quan sát hoặc phân tách trách nhiệm đã được ghi và xử lý.

### 13.3. Kết thúc và duy trì

- [ ] Đã thử đóng phiên, thu hồi quyền và kiểm tra khả năng đăng nhập lại.
- [ ] Có cách xử lý token, phiên và credential theo đúng cơ chế nền tảng.
- [ ] Có kế hoạch luân chuyển phương tiện sau sử dụng và xử lý bản sao cũ.
- [ ] Có người xác nhận khôi phục đường quản trị thông thường.
- [ ] Có lịch kiểm tra lại và các sự kiện thay đổi bắt buộc kiểm tra lại.
- [ ] Các phát hiện còn mở có chủ sở hữu, hạn xử lý và quyết định rủi ro phù hợp.

Checklist phải đọc cùng bằng chứng. Ô đánh dấu là kết quả của phép kiểm tra, không thay thế phép kiểm tra.

### 13.4. Ba loại kết luận cần phân biệt

**Đạt:** các điều kiện bắt buộc trong phạm vi đã duyệt có bằng chứng phù hợp, không còn lỗi chặn, và giới hạn được ghi rõ.

**Chưa đạt:** tồn tại lỗi như không lấy được credential khi IdP lỗi, không đủ quyền thực hiện tác vụ, không biết ai đã dùng tài khoản, hoặc không kết thúc được quyền theo tiêu chí đã đặt.

**Chấp nhận rủi ro có điều kiện:** người có thẩm quyền chấp nhận một thiếu hụt được nêu rõ, kèm phạm vi, thời hạn, biện pháp bù đắp và trách nhiệm xử lý. Đây là quyết định rủi ro riêng, không biến phép thử thất bại thành `PASS`.

Quyết định đưa dịch vụ vào production còn phụ thuộc quy trình phát hành của tổ chức. Người điền checklist không tự cấp quyền bỏ qua một tiêu chí bắt buộc nếu không có thẩm quyền đó.

## 14. Quy trình sau mỗi lần sử dụng thật

Một lần break-glass kết thúc khi trạng thái truy cập và chức năng hệ thống đã được xác minh, không chỉ khi sự cố được thông báo là ổn định.

Trình tự đóng cần bao gồm:

1. Xác nhận tác vụ khôi phục hoàn thành và các thay đổi đã được ghi nhận.
2. Đóng các phiên khẩn cấp; xử lý token và kết nối liên quan theo phạm vi.
3. Gỡ quyền tạm thời hoặc đưa danh tính về trạng thái thường lệ.
4. Thu hồi phương tiện đã bàn giao và luân chuyển credential khi cần.
5. Kiểm tra credential mới và xác nhận phương tiện cũ không còn dùng được theo cơ chế đã thiết kế.
6. Kiểm tra đường quản trị thông thường hoạt động và không để lại lối tắt tạm thời.
7. Thu thập, đối soát bằng chứng; ghi rõ dữ liệu thiếu hoặc chưa xác minh.
8. Rà soát lý do kích hoạt, thẩm quyền, hành động và chênh lệch so với runbook.
9. Giao các việc khắc phục, cập nhật tài liệu và quyết định phần cần diễn tập lại.

Khi thay secret có dịch vụ phụ thuộc, cần phối hợp để tránh tạo sự cố thứ hai. Không chọn cách “đổi tất cả ngay lập tức” nếu chưa xác định consumer và trình tự cập nhật. Nếu nghi ngờ credential bị lộ, việc cô lập và luân chuyển phải được điều phối với ứng phó sự cố theo mức rủi ro thực tế.

Việc một hệ thống được phục hồi từ backup cũng có thể đưa trạng thái quyền hoặc credential về thời điểm cũ. Sau phục hồi cần đối chiếu lại trạng thái hiện hành; không mặc định mọi lần thu hồi trước đó vẫn được bảo toàn.

## 15. Giữ break-glass sẵn sàng sau ngày go-live

### 15.1. Các sự kiện cần xem xét kiểm tra lại

- Thay đổi IdP, federation, MFA hoặc chính sách truy cập có điều kiện.
- Thay đổi kiến trúc PAM/vault, cơ chế khóa hoặc quy trình sao lưu.
- Nâng cấp nền tảng làm thay đổi cách xác thực, cấp quyền hoặc thu hồi phiên.
- Thay đổi VPN, DNS, bastion, mạng quản trị hoặc truy cập ngoài băng.
- Người giữ phương tiện, người phê duyệt hoặc nhóm trực ca thay đổi.
- Luân chuyển credential, thay thiết bị xác thực hoặc phát hiện bản sao cũ.
- Sử dụng break-glass thật, diễn tập thất bại hoặc có dấu hiệu dùng sai.
- Thay đổi phạm vi tài sản hay tác vụ phục hồi.

Chu kỳ định kỳ do tổ chức chọn theo mức độ quan trọng và tốc độ thay đổi. Chu kỳ không thay thế việc đánh giá lại sau một thay đổi có ảnh hưởng trực tiếp.

### 15.2. Chỉ số có ích

Có thể theo dõi số đường khẩn cấp quan trọng đã có bằng chứng hợp lệ, tuổi của lần thử gần nhất, tỷ lệ tác vụ khôi phục thành công, thời gian tới truy cập hữu dụng, thời gian đóng quyền và số phát hiện quá hạn.

Khi báo cáo tỷ lệ bao phủ, mẫu số phải là các đường hoặc tài sản nằm trong phạm vi đã thống nhất. “Đã thử 100% tài khoản đã biết” không chứng minh đã kiểm kê đủ mọi mặt phẳng quản trị cần cứu.

Chỉ số phải đi cùng lý do thất bại. Thời gian truy cập giảm nhưng số phiên không được thu hồi tăng là một dấu hiệu cần xử lý, không phải tiến bộ toàn diện.

## 16. Những lỗi khiến checklist dễ bị đánh dấu sai

| Cách hiểu sai | Hậu quả | Cách kiểm chứng phù hợp |
|---|---|---|
| Có tài khoản emergency là đủ | Tài khoản có thể bị khóa, không có quyền hoặc không có đường vào | Thử nhận phương tiện, đăng nhập và hoàn thành tác vụ |
| Lưu credential trong chính vault cần cứu | Không lấy được credential lúc vault lỗi | Kiểm tra phụ thuộc vòng và phương án khôi phục được bảo vệ |
| Dùng break-glass để bỏ mọi kiểm soát | Tạo đường quản trị khó truy nguyên | Giữ thẩm quyền, phạm vi, ghi nhận và thu hồi phù hợp điều kiện khẩn cấp |
| Chỉ tác giả runbook biết làm | Đội trực không tự khôi phục được | Cho người thay thế thực hiện diễn tập theo tài liệu |
| Đổi mật khẩu là đã đóng mọi quyền | Phiên, token hoặc quyền tạm có thể còn tồn tại | Kiểm tra từng loại quyền và phiên trong thiết kế thực tế |
| SIEM lỗi thì không cần bằng chứng | Không đối soát được hành động sau sự cố | Duy trì nguồn ghi thay thế và ghi rõ khoảng trống |
| Diễn tập lab thành công là đủ cho production | Credential hoặc cấu hình đích có thể khác | Đánh giá chênh lệch và có xác minh thích hợp tại đích thật |
| Phê duyệt sau là luôn hợp lệ | Hành động có thể vượt thẩm quyền | Đối chiếu chính sách khẩn cấp đã được phê duyệt trước |
| Kết quả năm trước vẫn còn hiệu lực | Phụ thuộc và quyền đã thay đổi | Gắn bằng chứng với phiên bản và kiểm tra lại khi có thay đổi |

## 17. Bài tập tự đánh giá

### Tình huống

Một đội chuẩn bị go-live PAM với các thông tin sau:

- Có hai tài khoản khẩn cấp cho mặt phẳng quản trị PAM.
- Credential được lưu trong một kho riêng, nhưng kho chỉ đăng nhập được bằng IdP chính.
- Đội đã thử đăng nhập khi mọi dịch vụ hoạt động.
- Có cảnh báo khi tài khoản khẩn cấp đăng nhập.
- Runbook yêu cầu đổi credential sau sử dụng nhưng chưa có bước xử lý phiên đang mở.
- Chỉ trưởng nhóm đã từng thực hiện toàn bộ quy trình.

Hãy trả lời:

1. Hạng mục “Đã có break-glass” có đủ bằng chứng để đạt chưa?
2. Kịch bản lỗi nào chưa được chứng minh?
3. Phép thử nào cần bổ sung để kiểm tra khả năng của người thay thế?
4. Vì sao đổi credential chưa chứng minh đã kết thúc quyền?
5. Cần lưu những bằng chứng nào mà không làm lộ bí mật?

### Gợi ý phân tích

Hạng mục chưa đủ điều kiện đạt cho kịch bản IdP không khả dụng. Kho riêng vẫn phụ thuộc cùng IdP, và phép thử khi mọi dịch vụ khỏe không chứng minh khả năng chịu lỗi đó.

Đội cần thiết kế lại hoặc bổ sung phương án nhận phương tiện phù hợp, rồi diễn tập đường đó trong điều kiện lỗi được kiểm soát. Người thay thế phải tự thực hiện các bước được giao theo runbook, bao gồm liên lạc, nhận phương tiện, truy cập và bàn giao.

Phần kết thúc cần kiểm tra quyền, phiên và token theo khả năng nền tảng; không chỉ thay credential. Gói bằng chứng nên có quyết định kích hoạt, mã sự cố, sự kiện bàn giao, mã phiên, tác vụ khôi phục, kết quả thu hồi và người xác nhận. Không đưa giá trị credential, khóa riêng hoặc mã khôi phục vào hồ sơ.

## 18. Điều kiện hoàn thành cần nhớ

Một đường break-glass sẵn sàng cho production phải trả lời được sáu câu hỏi bằng bằng chứng: **cứu tài sản nào, sống sót qua loại lỗi nào, ai được dùng, lấy quyền bằng cách nào, chứng minh đã làm gì và kết thúc quyền ra sao**.

Kết luận “Đã có break-glass” cần gắn với phạm vi và phiên bản đã kiểm chứng. Khi một trong các câu trả lời thay đổi, phải đánh giá lại khả năng khôi phục và các kiểm soát liên quan.
