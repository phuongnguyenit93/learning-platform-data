# Session requirement

## 1. Yêu cầu quản lý phiên giải quyết vấn đề gì?

Sau khi người dùng xác thực thành công, ứng dụng cần nhận biết các yêu cầu tiếp theo thuộc về ai và được phép thực hiện trong điều kiện nào. Session management quản lý sự liên tục đó: thiết lập phiên, sử dụng phiên, gia hạn, thay đổi mức tin cậy và chấm dứt phiên.

Nếu chỉ yêu cầu “người dùng phải đăng nhập”, thiết kế vẫn để ngỏ nhiều câu hỏi quan trọng:

- Đăng nhập thành công cho phép truy cập trong bao lâu?
- Đóng trình duyệt có chấm dứt quyền truy cập không?
- Token bị đánh cắp còn được dùng sau khi người dùng đăng xuất không?
- Tài khoản bị khóa thì phiên trên thiết bị khác mất hiệu lực khi nào?
- Phiên đã đăng nhập có đủ điều kiện đổi tài khoản nhận tiền không?
- Hệ thống có kiểm tra lại quyền sau khi người dùng bị gỡ khỏi một tenant không?

Session requirement là tập yêu cầu xác định hành vi bắt buộc của phiên trong các tình huống đó. Trong thiết kế yêu cầu bảo mật, mục tiêu không chỉ là chọn cookie hoặc token, mà là liên kết rủi ro với hành vi, điểm thực thi và bằng chứng kiểm chứng.

Một phiên hợp lệ không phải giấy phép truy cập mọi tài nguyên. Mỗi yêu cầu vẫn phải qua kiểm tra quyền phù hợp với người dùng, hành động, tài nguyên và ngữ cảnh hiện tại.

## 2. Xác định các khái niệm trước khi viết yêu cầu

| Khái niệm | Vai trò | Điều không nên suy diễn |
| --- | --- | --- |
| Tài khoản | Đại diện chủ thể trong miền quản trị | Tài khoản tồn tại không có nghĩa đang có phiên hợp lệ |
| Sự kiện xác thực | Xác minh một bằng chứng đăng nhập tại một thời điểm | Xác thực một lần không bảo đảm mức tin cậy giữ nguyên mãi |
| Phiên | Quan hệ truy cập có vòng đời giữa client và hệ thống | Một người dùng không nhất thiết chỉ có một phiên |
| Session credential | Bằng chứng client gửi để gắn yêu cầu với phiên | Sở hữu credential có thể đủ để giả mạo nếu không có ràng buộc khác |
| Access token | Credential cho phép truy cập theo ngữ nghĩa và phạm vi của hệ thống | Token còn hạn không bảo đảm tài khoản chưa bị khóa |
| Refresh token | Credential dùng xin access token mới theo chính sách | Hủy refresh token không tự hủy mọi access token đã cấp |
| Ngữ cảnh xác thực | Phương thức, thời điểm và mức tin cậy của xác thực | Cookie mới được phát hành không chứng minh người dùng vừa xác thực lại |
| Ngữ cảnh phân quyền | Quyền, tenant và điều kiện truy cập áp dụng | Quyền tại lúc đăng nhập có thể không còn đúng ở lần gọi sau |

Trong ứng dụng web, một cookie có thể chỉ chứa mã phiên ngẫu nhiên; trạng thái phiên nằm ở server. Một kiến trúc khác dùng token chứa thông tin đã được bảo vệ toàn vẹn, kết hợp với kho refresh token hoặc trạng thái thu hồi.

“Dùng JWT” và “dùng session” không phải hai lựa chọn luôn loại trừ nhau. Hệ thống dùng JWT vẫn có thể có phiên logic, vòng đời đăng nhập và yêu cầu thu hồi. Cần thống nhất phạm vi của từ “phiên” trong tài liệu để các nhóm không thực thi khác nhau.

### Phân biệt phiên ứng dụng với phiên đăng nhập liên kết

Khi ứng dụng dùng nhà cung cấp danh tính, có thể tồn tại đồng thời:

- Phiên của ứng dụng.
- Phiên tại nhà cung cấp danh tính.
- Access token và refresh token dành cho API.
- Phiên trên các thiết bị hoặc ứng dụng khác.

Đăng xuất khỏi một ứng dụng không mặc nhiên chấm dứt tất cả các trạng thái trên. Yêu cầu phải nêu rõ phạm vi đăng xuất và hành vi mong đợi khi người dùng quay lại ứng dụng.

## 3. Bắt đầu từ tài sản, hành trình sử dụng và rủi ro

Một cổng thông tin nội bộ chỉ đọc thông báo có mức rủi ro khác hệ thống cho phép thay đổi người thụ hưởng thanh toán. Không nên chọn chính sách phiên chỉ bằng cách sao chép một con số timeout.

Cần mô tả ít nhất:

1. Dữ liệu và hành động được bảo vệ.
2. Loại client: trình duyệt, ứng dụng di động, thiết bị dùng chung hoặc công cụ quản trị.
3. Mô hình tài khoản, tenant và cơ chế đăng nhập.
4. Tình huống bình thường: đăng nhập, làm việc lâu, chuyển màn hình, đổi quyền, đăng xuất.
5. Tình huống bất thường: mất thiết bị, lộ token, tài khoản bị khóa, hệ thống phiên bị gián đoạn.
6. Nhu cầu sẵn sàng và khả năng phục hồi khi phiên bị chấm dứt.

Ví dụ, một nhân viên dùng máy tính ở quầy giao dịch có thể rời máy mà không đóng trình duyệt. Một phiên tồn tại quá lâu làm tăng khả năng người khác tiếp tục thao tác. Tuy nhiên, timeout quá ngắn có thể làm mất bản nháp và khiến người dùng tìm cách né kiểm soát.

Yêu cầu bảo mật cần giải quyết cả rủi ro truy cập trái phép và trải nghiệm phục hồi hợp lệ, chẳng hạn bảo toàn bản nháp theo chính sách nhưng vẫn yêu cầu đăng nhập lại trước khi gửi giao dịch.

| Rủi ro | Hệ quả | Nhóm yêu cầu tương ứng |
| --- | --- | --- |
| Đoán hoặc lấy được session credential | Chiếm phiên của người khác | Sinh credential an toàn, bảo vệ đường truyền và nơi lưu |
| Giữ lại mã phiên có trước đăng nhập | Session fixation | Thay credential khi chuyển trạng thái tin cậy |
| Người dùng rời thiết bị | Người khác dùng phiên còn mở | Idle timeout, khóa giao diện và kiểm tra server |
| Credential còn dùng được sau đăng xuất | Phiên đã kết thúc vẫn truy cập được | Thu hồi có phạm vi và thời hạn rõ ràng |
| Quyền bị giảm nhưng phiên giữ quyền cũ | Truy cập vượt quyền hiện tại | Cập nhật hoặc đánh giá lại ngữ cảnh phân quyền |
| Bị đánh cắp refresh token | Kẻ tấn công duy trì truy cập | Bảo vệ, giới hạn thời hạn, phát hiện sử dụng lại khi thiết kế hỗ trợ |
| Gọi thao tác nhạy cảm từ phiên cũ | Lạm dụng phiên bị chiếm hoặc bỏ quên | Xác thực lại hoặc nâng mức xác thực |
| Mất kết nối tới kho phiên | Bỏ qua kiểm tra hoặc gây gián đoạn | Chính sách lỗi, cache và khôi phục được xác định trước |

## 4. Mô hình vòng đời và các chuyển trạng thái

Một mô hình khái niệm giúp xác định nơi nào phải có yêu cầu:

~~~text
Chưa xác thực
    |
    | xác thực thành công, thiết lập phiên mới
    v
Phiên đang hoạt động
    |-- đủ thời gian không hoạt động --> Hết hạn do idle
    |-- đạt tuổi tối đa -------------> Hết hạn tuyệt đối
    |-- đăng xuất / khóa / thu hồi --> Bị chấm dứt
    |
    | cần thực hiện hành động nhạy cảm
    v
Yêu cầu xác thực lại
    |-- thành công --> Được thực hiện trong phạm vi đã phê duyệt
    |-- thất bại --> Từ chối hành động, xử lý phiên theo chính sách
~~~

Trong thực tế, một phiên đang hoạt động có thể được phép đọc dữ liệu thông thường nhưng chưa đủ điều kiện thực hiện thao tác nhạy cảm. Do đó, “cần xác thực lại” không nhất thiết đồng nghĩa toàn bộ phiên đã hết hiệu lực.

Với mỗi chuyển trạng thái cần xác định:

- Sự kiện kích hoạt và nơi phát sinh.
- Điều kiện được chuyển.
- Trạng thái hoặc credential nào phải đổi.
- Thời gian tối đa để thay đổi có hiệu lực.
- Hành vi trên các request đồng thời và kết nối lâu dài.
- Bằng chứng audit và trách nhiệm vận hành.

### Phiên ẩn danh và phiên đã xác thực

Ứng dụng có thể tạo phiên trước đăng nhập để quản lý giỏ hàng hoặc trạng thái giao diện. Khi xác thực thành công, phải bảo đảm credential mà kẻ tấn công có thể biết trước không tiếp tục đại diện cho phiên đã đăng nhập.

Việc chuyển dữ liệu hợp lệ từ phiên ẩn danh sang phiên đăng nhập cần có quy tắc rõ ràng. Không chuyển mù quáng mọi thuộc tính, đặc biệt là thông tin quyền, tenant hoặc mức xác thực do client ảnh hưởng.

## 5. Yêu cầu khi thiết lập và bảo vệ phiên

### 5.1. Điều kiện thiết lập

Chỉ thiết lập phiên đã xác thực sau khi toàn bộ điều kiện đăng nhập bắt buộc được đáp ứng. Nếu quy trình cần nhiều bước, hoàn thành bước đầu không được tạo phiên có quyền tương đương hoàn tất cả quy trình.

Server phải gắn phiên với chủ thể và ngữ cảnh xác thực từ nguồn đáng tin cậy. Không chấp nhận user ID, role hoặc tenant do client tự khai làm căn cứ cấp phiên.

Credential mới phải không dự đoán được và có phạm vi sử dụng rõ ràng. Nếu chọn mã phiên opaque ngẫu nhiên, có thể đặt yêu cầu nội bộ về entropy và bộ sinh ngẫu nhiên mật mã; không dùng chuỗi tăng dần hoặc kết hợp các thuộc tính dễ đoán.

Ví dụ một chính sách nội bộ có thể yêu cầu ít nhất 128 bit ngẫu nhiên cho mã phiên opaque. Đây là quyết định thiết kế của hệ thống minh họa, không thay thế việc đánh giá toàn bộ cơ chế sinh, truyền và kiểm tra mã phiên.

### 5.2. Thay credential ở ranh giới tin cậy

Các sự kiện cần xem xét thay hoặc vô hiệu hóa credential gồm:

- Đăng nhập thành công.
- Nâng mức xác thực hoặc chuyển sang quyền đặc biệt.
- Thay đổi chủ thể trong cơ chế impersonation được phê duyệt.
- Phát hiện credential bị lộ.
- Những sự kiện khác được chính sách yêu cầu.

Đặc tả phải nêu rõ credential cũ bị từ chối khi nào. Chỉ phát hành credential mới trong khi credential cũ tiếp tục có toàn quyền không tự giải quyết session fixation hoặc lộ credential.

Thay credential định kỳ không nhất thiết là xác thực lại. Cũng không được coi việc thay credential là lý do để kéo dài tuổi tuyệt đối của phiên vô hạn.

### 5.3. Bảo vệ trong truyền và lưu

Với ứng dụng web dùng cookie, các thuộc tính Secure, HttpOnly và SameSite cần được cấu hình phù hợp với luồng sử dụng. Hạn chế domain và path giúp giảm nơi cookie được gửi, nhưng path không nên được coi là ranh giới bảo mật giữa các ứng dụng không tin cậy trên cùng host.

HttpOnly hạn chế JavaScript đọc cookie; nó không ngăn mọi tác động của XSS. Mã độc chạy trong ứng dụng vẫn có thể gửi thao tác dưới phiên của nạn nhân. SameSite có thể hỗ trợ giảm một số luồng gửi yêu cầu chéo site, nhưng không thay thế toàn bộ yêu cầu chống CSRF.

Không đưa session credential vào URL, log hoặc thông báo lỗi. URL dễ đi vào lịch sử, hệ thống quan sát hoặc các điểm trung gian ngoài dự kiến.

Với client khác trình duyệt, cần yêu cầu cơ chế lưu phù hợp với nền tảng và mô hình đe dọa. Không mặc định một quy tắc lưu token duy nhất phù hợp cho mọi loại client.

### 5.4. Nhận diện thiết bị và ngữ cảnh

Địa chỉ IP, user agent hoặc vị trí có thể hỗ trợ phát hiện rủi ro, nhưng không phải bằng chứng chắc chắn về người đang cầm thiết bị.

Ràng buộc cứng phiên vào IP có thể làm gián đoạn người dùng khi đổi mạng, đồng thời không ngăn được mọi kẻ tấn công chung đường ra mạng. Nếu dùng tín hiệu rủi ro để khóa phiên hoặc yêu cầu xác thực lại, phải đặc tả điều kiện, xử lý sai lệch và đường phục hồi.

## 6. Yêu cầu về thời gian và gia hạn

Các loại thời hạn có ý nghĩa khác nhau:

| Thời hạn | Điều nó giới hạn | Câu hỏi cần đặc tả |
| --- | --- | --- |
| Idle timeout | Khoảng không có hoạt động được tính là hợp lệ | Hoạt động nào cập nhật mốc cuối? |
| Absolute timeout | Tuổi tối đa của một phiên hoặc chuỗi đăng nhập được định nghĩa | Rotation và refresh có được đổi mốc gốc không? |
| Thời hạn access token | Khoảng credential truy cập được chấp nhận | Token hết hạn tác động thế nào đến phiên logic? |
| Thời hạn refresh token | Khả năng tiếp tục xin credential truy cập | Có giới hạn tuyệt đối và điều kiện thu hồi nào? |
| Cửa sổ xác thực gần đây | Thời gian cho phép dùng bằng chứng xác thực trước một hành động | Những sự kiện nào đặt lại thời điểm xác thực? |
| Thời hạn “ghi nhớ đăng nhập” | Khả năng quay lại mà không nhập lại toàn bộ bằng chứng | Khác gì với phiên đang có quyền hoạt động? |

### Idle timeout không chỉ là bộ đếm ở giao diện

Nếu giao diện chuyển về màn hình đăng nhập nhưng server vẫn chấp nhận credential cũ, yêu cầu hết hạn chưa được thực thi đầy đủ.

Cần định nghĩa hoạt động nào làm mới idle timer. Ví dụ, polling nền, heartbeat, tab không hiển thị hoặc tự động refresh token có thể tiếp tục gửi request dù người dùng đã rời máy.

Nếu mọi request nền đều làm mới phiên, chính sách “hết hạn khi người dùng không hoạt động” có thể không bao giờ xảy ra. Nếu dùng sự kiện từ giao diện để nhận biết hoạt động người dùng, phải hiểu client có thể bị sửa; dữ liệu đó không được coi là bằng chứng mạnh rằng chủ thể hợp lệ đang hiện diện.

### Ví dụ ngữ nghĩa thời hạn

Giả sử một ứng dụng chọn idle timeout 15 phút và absolute timeout 8 giờ. Các giá trị này chỉ là ví dụ.

~~~text
createdAt       = thời điểm bắt đầu phiên được định nghĩa
lastActivityAt  = thời điểm hoạt động được chính sách công nhận gần nhất
idleLimit       = 15 phút
absoluteLimit   = 8 giờ

Phiên không còn được chấp nhận khi:
now >= lastActivityAt + idleLimit
hoặc
now >= createdAt + absoluteLimit
hoặc
phiên đã bị thu hồi
~~~

Đây là mô tả chính sách, không phải mã triển khai hoàn chỉnh. Cần quyết định thêm dung sai thời gian, nguồn thời gian, đồng bộ giữa các node và thứ tự kiểm tra.

Không cập nhật lastActivityAt trước khi xác định phiên còn hợp lệ. Nếu làm ngược, một request đến sau thời hạn có thể tự làm phiên sống lại.

Ở đúng ngưỡng thời gian, chính sách cần nhất quán. Dùng “lớn hơn hoặc bằng” như ví dụ trên giúp xác định ca kiểm tra tại ranh giới; nếu hệ thống chọn ngữ nghĩa khác, phải ghi rõ.

### Gia hạn và đăng nhập lại

Refresh token, “remember me” hoặc phiên của nhà cung cấp danh tính có thể tạo credential mới mà không yêu cầu người dùng nhập lại mật khẩu. Cần quyết định điều đó có đủ để bắt đầu một phiên logic mới hay chỉ là gia hạn trong cùng giới hạn.

Nếu mục tiêu là buộc xác thực lại sau một tuổi đăng nhập tối đa, việc tự động tạo một phiên ứng dụng mới từ phiên đăng nhập liên kết cũ không được âm thầm né giới hạn đó.

Thời điểm phát hành token và thời điểm người dùng thực sự xác thực là hai dữ kiện khác nhau. Đặc tả hành động nhạy cảm nên dựa vào dữ kiện xác thực phù hợp, không chỉ dựa vào token có vẻ mới.

## 7. Đăng xuất, thu hồi và các sự kiện thay đổi tài khoản

### 7.1. Định nghĩa phạm vi chấm dứt

“Đăng xuất thành công” phải có ý nghĩa cụ thể đối với server và client.

Có thể có các hành vi khác nhau:

- Đăng xuất phiên hiện tại.
- Đăng xuất mọi phiên của cùng người dùng trong ứng dụng.
- Thu hồi phiên của một thiết bị.
- Thu hồi toàn bộ credential thuộc một chuỗi đăng nhập.
- Chấm dứt phiên ứng dụng và yêu cầu chấm dứt phiên liên kết theo khả năng của các bên.

Giao diện cần thể hiện đúng phạm vi mà hệ thống thực thi. Không hiển thị “đã đăng xuất khỏi mọi thiết bị” nếu backend chỉ xóa cookie trên trình duyệt đang dùng.

Xóa cookie hoặc xóa token ở client giúp dọn trạng thái phía client, nhưng không bảo đảm bản sao credential đã bị lấy cắp không còn dùng được. Yêu cầu cần xác định server ngừng chấp nhận credential liên quan khi nào.

### 7.2. Credential đã phát hành và kết nối đang mở

Trong kiến trúc xác minh access token tại chỗ, hủy refresh token có thể ngăn cấp token mới trong khi access token cũ vẫn còn dùng được đến khi hết hạn.

Nếu cần chặn nhanh hơn thời hạn token, phải có cơ chế tương ứng, chẳng hạn trạng thái thu hồi được kiểm tra, phiên bản phiên hoặc cơ chế phân phối quyết định đến nơi thực thi. Tài liệu yêu cầu mô tả kết quả và thời hạn; thiết kế kiến trúc phải chứng minh đáp ứng được thời hạn đó.

Kết nối WebSocket, stream hoặc phiên làm việc lâu dài cần quy định riêng về tái kiểm tra và chấm dứt. Từ chối request HTTP mới không tự chứng minh một stream đang mở đã mất quyền tiếp tục nhận dữ liệu.

### 7.3. Sự kiện thay đổi tài khoản

Các sự kiện cần được phân loại theo tác động lên phiên:

| Sự kiện | Quyết định cần đưa vào yêu cầu |
| --- | --- |
| Tài khoản bị khóa do sự cố | Phạm vi phiên bị thu hồi, thời hạn chặn và cách xử lý refresh |
| Đổi hoặc đặt lại mật khẩu | Phiên nào giữ lại, phiên nào mất hiệu lực, có phụ thuộc loại xác thực không |
| Thay phương thức MFA | Có yêu cầu xác thực lại, thu hồi hoặc thông báo phiên khác không |
| Gỡ quyền quản trị | Khi nào các phiên đang mở ngừng dùng quyền cũ |
| Gỡ người dùng khỏi tenant | Khi nào quyền trên tenant đó mất hiệu lực |
| Nghi ngờ mất thiết bị | Cách chọn thiết bị, thu hồi và thông báo |
| Kết thúc quan hệ làm việc | Ai phát lệnh, liên kết với hệ thống tài khoản và bằng chứng thực thi |

Không nên gộp tất cả thành “đổi thông tin thì logout”. Chẳng hạn, thay tên hiển thị và thu hồi quyền quản trị có tác động bảo mật khác nhau.

Thu hồi không tự đảo ngược giao dịch đã hoàn thành trước đó. Với thao tác đã bắt đầu nhưng chưa commit, phải xác định yêu cầu kiểm tra quyền ở bước nào và có cần đánh giá lại trước khi hoàn tất hay không.

## 8. Phiên đồng thời, tenant và hành động nhạy cảm

### 8.1. Chính sách nhiều phiên

Hệ thống có thể cho phép nhiều thiết bị hoặc giới hạn số phiên theo loại tài khoản. Yêu cầu cần xác định:

- “Một phiên” được đếm theo credential, browser profile, thiết bị hay phiên logic.
- Khi đạt giới hạn thì từ chối đăng nhập mới hay chấm dứt phiên cũ.
- Phiên nào bị chọn để chấm dứt và cách thông báo.
- Cách xử lý đăng nhập đồng thời trên nhiều node.
- Cách người dùng xem và thu hồi phiên không nhận ra.

Một trình duyệt mở hai tab thường có thể dùng cùng credential; số tab không tự bằng số phiên. Tên thiết bị do client khai báo chỉ là thông tin hỗ trợ, không phải định danh thiết bị đã được chứng minh.

Nếu giới hạn là hai phiên, kiểm tra rồi tạo bằng hai thao tác không được điều phối có thể làm nhiều node cùng chấp nhận vượt giới hạn. Đặc tả cần yêu cầu kết quả nhất quán ở mức nghiệp vụ và nêu rõ ngoại lệ nếu chấp nhận độ trễ.

### 8.2. Tenant đang chọn không thay thế quyền tenant

Chuyển tenant là một thay đổi ngữ cảnh truy cập. Server phải kiểm tra người dùng còn thuộc tenant và có quyền cho tài nguyên ở tenant đó.

Nếu một cookie chứa lựa chọn tenant dùng chung giữa các tab, thay tenant ở tab này có thể ảnh hưởng tab khác. Yêu cầu phải quyết định tenant được gắn theo request hay theo phiên và cách tránh thao tác nhầm ngữ cảnh.

Không cho phép client tự gửi tenant ID để vượt quyền. Session context cũng không được giữ quyền đã thu hồi vô thời hạn chỉ vì người dùng chưa đăng xuất.

### 8.3. Xác thực lại theo hành động

Một phiên còn hiệu lực có thể chưa đủ tin cậy cho đổi email khôi phục, tạo khóa truy cập, thay người thụ hưởng hoặc thao tác quản trị quan trọng.

Yêu cầu xác thực lại nên mô tả:

1. Những hành động kích hoạt.
2. Phương thức và mức xác thực được chấp nhận.
3. Tuổi tối đa của bằng chứng xác thực.
4. Phạm vi hiệu lực sau xác thực: một thao tác, nhóm thao tác hay toàn phiên.
5. Ràng buộc với chi tiết giao dịch nếu có.
6. Hành vi khi thất bại, hết thời gian hoặc thay đổi nội dung thao tác.

Nếu người dùng xác thực để chuyển một khoản tiền, rồi client đổi người nhận trước khi gửi, hệ thống cần xử lý theo yêu cầu ràng buộc giao dịch đã xác định. Không mặc định mọi hình thức MFA đều xác nhận chính xác nội dung giao dịch.

## 9. Các yêu cầu đối với hệ thống phân tán và tình huống lỗi

### 9.1. Một chính sách phải có hiệu lực ở mọi điểm thực thi

Load balancer có thể đưa hai request liên tiếp đến hai node khác nhau. Nếu chỉ cập nhật trạng thái phiên trong bộ nhớ một node, đăng xuất có thể có hiệu lực ở nơi này nhưng không ở nơi khác.

Cần xác định:

- Nơi lưu trạng thái chuẩn và cơ chế cập nhật.
- Các cache được phép giữ quyết định trong bao lâu.
- Độ trễ tối đa để thay đổi có hiệu lực trên toàn phạm vi.
- Cách nhận biết node đang dùng trạng thái cũ.
- Hành vi khi một node khởi động lại hoặc phục hồi từ bản sao cũ.

Khôi phục dữ liệu không được vô tình làm sống lại phiên đã bị thu hồi. Kế hoạch phục hồi phải xét lịch sử thu hồi, giới hạn tuổi và khả năng đối chiếu trạng thái sau sự cố.

### 9.2. Không có một câu trả lời duy nhất cho lỗi hệ thống phiên

Cho phép tiếp tục mọi truy cập khi không kiểm tra được phiên làm mất khả năng thực thi bảo mật. Từ chối toàn bộ truy cập cũng có thể gây gián đoạn nghiêm trọng.

Yêu cầu nên phân loại hành động. Ví dụ:

- Thao tác đặc quyền bị từ chối khi không xác minh được trạng thái bắt buộc.
- Một loại truy cập đọc rủi ro thấp có thể dùng kết quả xác minh đã cache trong một khoảng được phê duyệt.
- Cache không được dùng quá thời hạn credential hoặc vượt giới hạn tuổi phiên.
- Không tạo phiên mới hoặc kéo dài quyền chỉ vì hệ thống kiểm tra bị lỗi.

Đây là lựa chọn dựa trên rủi ro và nhu cầu sẵn sàng, cần được owner chấp thuận trong yêu cầu. Không để từng nhóm tự chọn hành vi khác nhau khi triển khai.

### 9.3. Request đồng thời và refresh

Các tình huống cần làm rõ gồm request đến cùng lúc với đăng xuất, hai tab cùng refresh, nhiều request cùng cập nhật hoạt động, hoặc retry sau khi client không nhận được phản hồi.

Nếu refresh token dùng một lần, việc tiêu thụ token và cấp token thay thế cần tránh tạo nhiều nhánh credential hợp lệ ngoài chính sách. Client cũng cần phối hợp các lần refresh đồng thời.

Tín hiệu sử dụng lại refresh token có thể đến từ đánh cắp hoặc từ retry hợp lệ. Thiết kế cần xác định cách phân biệt trong phạm vi khả năng của nó và hành động phản ứng; không được chấp nhận tái sử dụng vô hạn để tránh lỗi giao diện.

Nếu chọn chính sách nghiêm ngặt “một lần sử dụng”, tiêu chí chấp nhận phải bao gồm request đồng thời: chỉ một lần tiêu thụ thành công, request còn lại được xử lý đúng quy tắc, không tạo thêm chuỗi credential độc lập.

## 10. Bộ yêu cầu minh họa và tiêu chí chấp nhận

Giả sử một cổng quản trị tài chính chọn idle timeout 15 phút, tuổi phiên tối đa 8 giờ, cửa sổ xác thực gần đây 5 phút và thời gian lan truyền thu hồi tối đa 60 giây. Đây là các ngưỡng minh họa cho bài học; hệ thống thực tế phải lựa chọn theo rủi ro và hành trình sử dụng.

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| SR-01 | Chỉ tạo phiên có quyền sau khi hoàn tất mọi bước xác thực bắt buộc | Dừng ở bước trung gian không gọi được API yêu cầu phiên đã xác thực |
| SR-02 | Khi đăng nhập thành công, server cấp credential mới và credential trước đăng nhập không được dùng như phiên đã xác thực | Dùng lại credential cũ để gọi API bảo vệ bị từ chối |
| SR-03 | Session credential không được lộ qua URL, log, trace, thông báo lỗi hoặc artifact thuộc phạm vi ứng dụng | Với credential thử nghiệm, kích hoạt đường thành công và lỗi; đầu ra được thu thập không chứa giá trị credential |
| SR-04 | Phiên hết hạn sau 15 phút không có hoạt động được chính sách công nhận | Request tại hoặc sau mốc hết hạn bị từ chối trên mọi node; polling nền không kéo dài phiên theo định nghĩa đã chọn |
| SR-05 | Phiên hết hạn tuyệt đối sau 8 giờ kể từ mốc gốc, dù credential được thay hoặc refresh | Liên tục có hoạt động và refresh vẫn không vượt tuổi phiên; không tạo lại mốc gốc để né chính sách |
| SR-06 | Đăng xuất phiên hiện tại chặn mọi request mới dùng credential của phiên đó trong tối đa 60 giây | Credential được sao chép trước logout không dùng được tại mọi điểm thực thi sau giới hạn |
| SR-07 | Lệnh khóa tài khoản do sự cố ngừng tạo, refresh và sử dụng mọi phiên của tài khoản trong phạm vi ứng dụng sau tối đa 60 giây | Kiểm tra nhiều thiết bị, credential còn hạn và các node có cache |
| SR-08 | Gỡ quyền quản trị có hiệu lực trên request mới trong tối đa 60 giây | Phiên vẫn có thể truy cập chức năng thường nếu được phép, nhưng không dùng được quyền quản trị cũ |
| SR-09 | Đổi người thụ hưởng yêu cầu bằng chứng xác thực đạt mức quy định và không quá 5 phút | Phiên hợp lệ nhưng bằng chứng quá cũ bị yêu cầu xác thực lại; token mới cấp từ refresh không tự đáp ứng |
| SR-10 | Khi không kiểm tra được trạng thái thu hồi, API quản trị bị từ chối | Gián đoạn đường kiểm tra không làm API bỏ qua điều kiện; lỗi được quan sát và ghi nhận |
| SR-11 | Giới hạn hai phiên logic đồng thời cho tài khoản quản trị, theo quy tắc chọn phiên đã công bố | Đăng nhập đồng thời ở nhiều node không tạo vượt giới hạn ngoài ngoại lệ được nêu rõ |
| SR-12 | Mọi quyết định tạo, thu hồi và hết hạn phiên có audit liên kết được với phiên nhưng không chứa credential | Từ sự kiện mẫu xác định được chủ thể, phạm vi, thời điểm và lý do, nhưng không lấy được credential để truy cập |

SR-06 không thể được chứng minh chỉ bằng việc thấy cookie biến mất trên trình duyệt. SR-07 không thể được chứng minh chỉ bằng việc tài khoản bị đổi trạng thái trong cơ sở dữ liệu. Cả hai cần kiểm chứng tại nơi nhận và quyết định yêu cầu truy cập.

Nếu kiến trúc dùng access token có thời hạn 10 phút và không có đường kiểm tra thu hồi, nó chưa chứng minh được cam kết chặn trong 60 giây. Cần điều chỉnh thiết kế hoặc điều chỉnh yêu cầu bằng một quyết định rõ ràng.

### Mẫu đặc tả cho một yêu cầu

~~~yaml
requirement_id: SR-06
subject: Phiên hiện tại của người dùng
trigger: Server xác nhận yêu cầu đăng xuất hợp lệ
scope:
  - Mọi API của ứng dụng nhận credential thuộc phiên đó
  - Mọi node xử lý và cache quyết định trong phạm vi triển khai
required_behavior: Từ chối request mới sử dụng credential của phiên đã đăng xuất
maximum_effect_delay_seconds: 60
credential_scope:
  - Mã phiên đang dùng
  - Credential truy cập đã cấp thuộc cùng phiên logic
verification:
  - Ghi nhận thời điểm server xác nhận logout
  - Gửi request bằng credential đã sao chép trước logout tới từng node
  - Đối chiếu thời điểm từ chối và audit
separate_requirements:
  - Cách xử lý kết nối lâu dài
  - Phạm vi đăng xuất tại nhà cung cấp danh tính
owner: Nhóm ứng dụng và nhóm nền tảng identity
~~~

Đoạn YAML là ví dụ viết yêu cầu, không phải cấu hình chạy. Việc tách những yêu cầu liên quan giúp tránh hiểu sai rằng logout một phiên phải tự động xử lý cả hệ thống SSO hoặc hoàn tác mọi tác vụ đã chạy.

## 11. Từ yêu cầu đến kế hoạch kiểm chứng

Mỗi yêu cầu nên có bằng chứng phù hợp với điều nó khẳng định. Kiểm tra cấu hình có thể chứng minh một giá trị đã được đặt; không tự chứng minh toàn bộ luồng phân tán tuân theo giá trị đó.

### 11.1. Ca thành công và ca từ chối

Với cùng một tài nguyên, cần kiểm tra:

- Chưa có phiên.
- Phiên hợp lệ và có quyền.
- Phiên hợp lệ nhưng thiếu quyền.
- Phiên đã hết hạn do idle hoặc tuổi tuyệt đối.
- Phiên đã bị đăng xuất hoặc thu hồi.
- Phiên còn hiệu lực nhưng chưa đáp ứng xác thực lại.
- Phiên của người dùng hoặc tenant khác.

Các ca này phân biệt lỗi quản lý phiên với lỗi phân quyền. Một response thành công trong ca chuẩn không chứng minh các ca từ chối an toàn.

### 11.2. Ranh giới thời gian

Nếu yêu cầu là hết hạn ở mốc T, cần xác định cách kiểm tra ngay trước T, tại T và sau T. Đồng hồ của client không phải nguồn quyết định thời hạn server.

Ví dụ một dòng thời gian kiểm chứng idle timeout:

~~~text
09:00:00  Xác thực thành công
09:05:00  Hoạt động được công nhận gần nhất
09:10:00  Polling nền, không được tính là hoạt động theo chính sách ví dụ
09:19:59  Chưa đạt mốc idle 15 phút
09:20:00  Request mới phải bị từ chối nếu không có hoạt động hợp lệ khác
~~~

Nếu request ở 09:19:59 là một hoạt động được công nhận, nó sẽ thay đổi mốc idle. Vì vậy, mỗi ca kiểm thử ranh giới cần kiểm soát hoạt động phát sinh; không dùng một chuỗi request rồi kỳ vọng mốc cũ vẫn giữ nguyên.

### 11.3. Phân tán và độ trễ thu hồi

Cần bao gồm node có cache nóng, node vừa khởi động, thay đổi tuyến load balancer và đường gọi trực tiếp được phép trong môi trường kiểm chứng.

Mốc bắt đầu phép đo phải được thống nhất. Chẳng hạn, bắt đầu tại lúc server xác nhận yêu cầu logout, kết thúc khi mọi điểm thực thi trong phạm vi từ chối request mới. Không dùng thời điểm người dùng bấm nút nếu không đo được độ trễ gửi và xử lý.

Với giao dịch nhạy cảm, cần thêm ca request đến sát thời điểm thu hồi và ca hành động kéo dài qua thời điểm đó. Kết quả mong đợi phải dựa trên yêu cầu về điểm quyết định, không tự suy diễn rằng mọi thao tác đang chạy đều phải bị hủy.

### 11.4. Bằng chứng audit tối thiểu

Một sự kiện nên có thời gian, loại sự kiện, chủ thể, mã tham chiếu phiên không dùng được để xác thực, nguồn phát sinh, kết quả và lý do. Khi cần, bổ sung phạm vi tenant, actor thực hiện thu hồi, correlation ID và phiên bản chính sách.

Không ghi session ID hoặc token nguyên giá trị chỉ để tiện liên kết. Có thể dùng định danh audit riêng hoặc cơ chế tham chiếu phù hợp được bảo vệ.

Dữ liệu về phiên, thiết bị và địa chỉ mạng cũng cần chính sách truy cập và lưu trữ. Thu thập nhiều hơn không tự làm điều tra hiệu quả hơn nếu không có liên kết sự kiện hoặc chất lượng thời gian.

## 12. Những yêu cầu dễ viết sai

| Cách viết | Điều còn thiếu | Cách làm rõ |
| --- | --- | --- |
| Session phải an toàn | Không có hành vi kiểm chứng | Nêu vòng đời, credential, quyền, thời hạn và tình huống lỗi |
| Tự logout sau 15 phút | Không rõ 15 phút tính từ đâu và logout ở phía nào | Định nghĩa hoạt động, mốc thời gian và từ chối ở server |
| Refresh để người dùng không bao giờ bị văng | Có thể vô hiệu hóa tuổi phiên và xác thực lại | Phân biệt gia hạn credential với giới hạn đăng nhập |
| Logout bằng cách xóa cookie | Bỏ sót bản sao credential | Yêu cầu thời hạn server ngừng chấp nhận credential |
| Có MFA thì phiên luôn đáng tin | Không xét thời gian và thao tác | Xác định tuổi bằng chứng và phạm vi đủ điều kiện |
| Giới hạn một thiết bị | Không định nghĩa thiết bị hoặc phiên | Nêu đơn vị đếm, tín hiệu nhận biết và xử lý đồng thời |
| Token có role nên khỏi tra quyền | Quyền có thể thay đổi sau khi cấp token | Đặc tả thời hạn cập nhật và cơ chế đáp ứng |
| Cookie HttpOnly nên không cần chống XSS | Hiểu quá mức tác dụng của thuộc tính | Giữ yêu cầu chống XSS và kiểm soát thao tác dưới phiên |
| Đăng xuất SSO nghĩa là logout mọi ứng dụng | Bỏ qua ranh giới và khả năng các bên | Nêu chính xác phạm vi, giao thức và bằng chứng đạt được |

Một yêu cầu tốt mô tả kết quả bắt buộc mà các nhóm có thể kiểm chứng cùng nhau. Nó có thể chứa ràng buộc công nghệ khi thật sự cần, nhưng không dùng tên công nghệ để thay cho tiêu chí chấp nhận.

## 13. Áp dụng vào thiết kế một chức năng

Xét chức năng thay đổi tài khoản nhận tiền trên cổng quản trị. Bộ yêu cầu cần bao quát cả hành trình:

1. Người dùng phải có phiên còn hiệu lực và quyền cập nhật đúng đối tượng.
2. Phiên phải thỏa chính sách idle và tuổi tối đa.
3. Thao tác cần bằng chứng xác thực gần đây theo mức được chọn.
4. Dữ liệu giao dịch phải được kiểm tra và ràng buộc theo yêu cầu xác nhận đã định.
5. Việc gỡ quyền hoặc thu hồi phiên phải có hiệu lực trong thời hạn cam kết.
6. Request đồng thời với thay đổi quyền được xử lý theo điểm quyết định được đặc tả.
7. Khi hệ thống kiểm tra điều kiện bắt buộc bị lỗi, hành động bị từ chối theo chính sách.
8. Audit liên kết được chủ thể, phiên, thao tác, kết quả và nguyên nhân mà không lộ credential.
9. Khi phiên hết hạn, giao diện hỗ trợ phục hồi thao tác hợp lệ nhưng không tự bỏ qua xác thực lại.

Các yêu cầu đó liên kết quản lý phiên với xác thực, phân quyền, bảo vệ dữ liệu, logging và vận hành. Đầu ra cần đủ rõ để kiến trúc sư chọn cơ chế thực thi, lập trình viên xử lý đúng các chuyển trạng thái và nhóm kiểm chứng xác định được khi nào yêu cầu đã đạt.
