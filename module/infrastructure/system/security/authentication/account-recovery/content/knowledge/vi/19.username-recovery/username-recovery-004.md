# Thiết kế thông điệp gửi lại tên đăng nhập

## 1. Gửi tên đăng nhập là một hành động tiết lộ thông tin

Trong chương **Username Recovery**, sau khi xác định được một tuyến khôi phục phù hợp, hệ thống cần chuyển tên đăng nhập tới người dùng. **Username delivery message** là thông điệp thực hiện việc đó: nội dung thư, tin nhắn hoặc hướng dẫn mở một trang xem thông tin có kiểm soát.

Tên đăng nhập không phải mật khẩu, nhưng việc gắn nó với email, số điện thoại, tổ chức hoặc một dịch vụ cụ thể vẫn có thể là thông tin nhạy cảm. Gửi sai người có thể làm lộ sự tồn tại của tài khoản, danh tính hoặc quan hệ thành viên, đồng thời hỗ trợ các bước tấn công tiếp theo.

Trong phạm vi `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, thông điệp phải giúp người dùng lấy lại định danh khi cần khôi phục quyền truy cập, đồng thời phối hợp với xác minh, chống lạm dụng và kiểm soát phiên. Nó không được âm thầm trở thành liên kết đăng nhập, token đặt lại mật khẩu hoặc quyền bỏ MFA và passkey.

Ví dụ, Thảo quên tên đăng nhập và nhập email vào biểu mẫu khôi phục. Trình duyệt của người gửi chưa chứng minh quyền kiểm soát hộp thư. Hệ thống có thể gửi thông tin qua một kênh đã được phép, nhưng không nên hiển thị tên đăng nhập ngay trên màn hình công khai chỉ vì đã tìm thấy tài khoản tương ứng.

Một thông điệp tốt cần trả lời rõ:

- Thông tin nào được phép tiết lộ, cho chủ thể nào và qua kênh nào?
- Tiêu đề, nội dung xem trước và phần thân có tiết lộ nhiều hơn cần thiết không?
- Người dùng cần thực hiện hành động gì, và hành động đó thực sự cấp quyền gì?
- Nếu người nhận không yêu cầu hoặc liên kết không còn dùng được, họ nên làm gì?
- Nếu tên đăng nhập hoặc địa chỉ nhận thay đổi trong lúc chờ gửi, thông điệp có còn đúng không?

## 2. Tách phản hồi công khai khỏi thông điệp gửi riêng

### 2.1. Biểu mẫu công khai chỉ xác nhận việc tiếp nhận

Một phản hồi minh họa cho yêu cầu hợp lệ về định dạng:

> Nếu có thông tin khôi phục phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký.

Phản hồi này không xác nhận email có tài khoản, không nói có bao nhiêu tên đăng nhập, không tiết lộ tổ chức và không trả về tên đăng nhập đã che một phần.

Ngay cả thông tin che bớt như `th***89` cũng có thể giúp người ngoài xác nhận một tài khoản. Che ký tự không tự biến dữ liệu thành thông tin được phép công khai.

### 2.2. Thư gửi tới kênh được phép có một mục tiêu khác

Thông điệp riêng có thể tiết lộ tên đăng nhập vì chính đó là mục đích khôi phục, nhưng chỉ trong phạm vi chính sách cho phép đối với kênh nhận. Đây là một sự tiết lộ có chủ đích cho người kiểm soát kênh, không phải bảo đảm rằng mọi người có thể đọc thư đều là chủ tài khoản duy nhất.

Hộp thư dùng chung, thiết bị bị mở khóa hoặc tài khoản email bị chiếm đều ảnh hưởng tới mức bảo vệ. Nếu quan hệ tài khoản có độ nhạy cảm cao, cần một phương thức tiết lộ phù hợp hơn, có thể yêu cầu thêm bằng chứng trên trang xem thông tin.

### 2.3. Không coi việc biết địa chỉ nhận là bằng chứng

Máy chủ phải chọn một kênh đã đăng ký và được phép dùng để khôi phục. Không để người gửi cung cấp `deliveryTo` bất kỳ rồi nhận tên đăng nhập của một người khác.

Nếu người dùng không còn truy cập kênh cũ, cần quy trình xác minh để thay hoặc khôi phục kênh. Không giải quyết bằng một ô “Gửi tới email mới” không có bằng chứng độc lập.

## 3. Chọn hình thức tiết lộ trước khi viết nội dung

Có hai hình thức phổ biến, với những đặc tính khác nhau:

| Hình thức | Cách hoạt động | Lợi ích | Giới hạn |
|---|---|---|---|
| Gửi tên đăng nhập trực tiếp | Tên đăng nhập nằm trong phần thân thông điệp | Ít thao tác, không cần mở một liên kết bí mật | Thông tin tồn tại trong hộp thư, bản sao và nội dung xem trước tùy thiết bị |
| Gửi liên kết tới trang xem | Thông điệp chỉ chứa hướng dẫn và quyền xem có hạn | Có thể kiểm tra lại trạng thái trước khi tiết lộ, giới hạn thời gian và phạm vi | Liên kết là một bí mật có thể bị chuyển tiếp; cần thiết kế chống lộ và dùng lại |

Chuyển từ tên đăng nhập trực tiếp sang một liên kết gửi trong cùng hộp thư **không tự tạo thêm một yếu tố xác thực độc lập**. Nếu người khác kiểm soát hộp thư, họ có thể đọc hoặc sử dụng liên kết, trừ khi trang đích còn yêu cầu bằng chứng khác theo chính sách.

Ngược lại, hình thức liên kết có giá trị khi cần kiểm tra lại việc tài khoản còn tồn tại, tên đăng nhập còn hiện hành hoặc kênh nhận chưa bị thu hồi. Thư chứa tên đăng nhập trực tiếp đã gửi đi thì không thể bảo đảm thu hồi mọi bản sao.

Hình thức nào cũng phải có phạm vi rõ. “Xem tên đăng nhập” không mặc nhiên bao gồm “đăng nhập”, “đặt lại mật khẩu”, “thêm passkey” hoặc “tắt MFA”.

## 4. Các thành phần cần có trong thông điệp

| Thành phần | Nội dung phù hợp | Điều cần tránh |
|---|---|---|
| Người gửi | Tên sản phẩm và miền gửi được cấu hình tin cậy | Lấy tên hoặc địa chỉ gửi từ dữ liệu request không đáng tin |
| Tiêu đề | Thông báo ngắn về thông tin người nhận đã yêu cầu | Đặt tên đăng nhập, email đầy đủ, tổ chức nhạy cảm hoặc token trong tiêu đề |
| Phần mở đầu | Nêu mục đích khôi phục tên đăng nhập | Khẳng định người nhận chắc chắn đã yêu cầu |
| Thông tin chính | Tên đăng nhập được phép tiết lộ hoặc liên kết xem có phạm vi | Mật khẩu, mã MFA, mã dự phòng, dữ liệu tài khoản khác |
| Hướng dẫn | Cách vào đúng ứng dụng hoặc trang đăng nhập | Đường dẫn tùy ý do người gửi cung cấp, liên kết rút gọn khó kiểm tra |
| Thời hạn nếu có | Hạn dùng thật của quyền xem, có múi giờ rõ | Hứa thời hạn không khớp dữ liệu phía máy chủ |
| Xử lý yêu cầu ngoài ý muốn | Có thể bỏ qua; hướng dẫn vào ứng dụng khi thấy dấu hiệu đáng ngờ | Gây hoảng sợ hoặc yêu cầu trả lời thư bằng bí mật |
| Giới hạn tác động | Nêu đúng việc yêu cầu này không thay thông tin xác thực | Hứa an toàn tuyệt đối khi chỉ mới gửi một thông điệp |

Tiêu đề và nội dung xem trước có thể xuất hiện trên màn hình khóa. Không đưa bí mật hoặc định danh cần bảo vệ lên những vị trí đó. Ngay cả tên sản phẩm trong người gửi cũng có thể cho biết quan hệ sử dụng dịch vụ; cần cân nhắc theo mức nhạy cảm của sản phẩm, không chỉ phần thân thư.

Không cần chèn họ tên, ảnh đại diện, mã khách hàng, vai trò quản trị hoặc địa chỉ IP đầy đủ để làm một thư khôi phục tên đăng nhập có vẻ cá nhân hóa. Mỗi trường thêm vào đều làm tăng thông tin bị lộ nếu thư tới sai người.

## 5. Mẫu thư gửi tên đăng nhập trực tiếp

Mẫu dưới đây chỉ phù hợp khi chính sách cho phép tiết lộ trực tiếp qua kênh nhận đã được kiểm tra. Các biến là placeholder để minh họa, không phải dữ liệu thật.

```text
Tiêu đề: Thông tin bạn đã yêu cầu

Xin chào,

Một yêu cầu tìm lại tên đăng nhập tại {{product_name}} đã được tiếp nhận.

Tên đăng nhập:
{{username}}

Để đăng nhập, bạn có thể tự mở ứng dụng {{product_name}}
hoặc truy cập trang chính thức:
{{official_login_url}}

Yêu cầu này không thay đổi mật khẩu, MFA, passkey hoặc phiên đăng nhập.
Nếu bạn không gửi yêu cầu, bạn có thể bỏ qua thông điệp này.

Nếu thông điệp lặp lại nhiều lần hoặc bạn nhận thấy hoạt động bất thường,
hãy mở ứng dụng hoặc trang chính thức để xem hướng dẫn bảo mật.

Không gửi mật khẩu, mã xác thực hoặc mã dự phòng khi trả lời thư.
{{product_name}}
```

Các câu về tác động chỉ đúng nếu luồng gửi tên đăng nhập thực sự không thay đổi thông tin xác thực hoặc phiên. Không sao chép mẫu rồi gắn vào một luồng có hành vi khác mà giữ nguyên lời hứa.

`official_login_url` phải được tạo từ cấu hình tin cậy. Một địa chỉ minh họa có thể là `https://accounts.example.com/login`; sản phẩm thực tế dùng miền chính thức đã cấu hình của mình. Không lấy `Host`, `returnUrl` hoặc tên miền do người gửi tùy ý nhập để ghép đường dẫn trong thư.

Tên đăng nhập cần được hiển thị chính xác, phân biệt với tên hiển thị hoặc email liên hệ. Không tự bỏ dấu, đổi chữ hoa, thay khoảng trắng hoặc thêm ký tự nhằm làm đẹp nếu việc đó khiến người dùng sao chép một định danh khác.

Nếu hệ thống hỗ trợ nhiều định danh đăng nhập, chỉ gửi loại mà người dùng có thể sử dụng trong ngữ cảnh hiện tại. Một định danh SSO nội bộ không nhất thiết là chuỗi nên nhập vào biểu mẫu mật khẩu cục bộ.

## 6. Mẫu thư dẫn tới trang xem tên đăng nhập

### 6.1. Nội dung thư

```text
Tiêu đề: Hướng dẫn tìm lại tên đăng nhập

Xin chào,

Một yêu cầu tìm lại tên đăng nhập tại {{product_name}} đã được tiếp nhận.

Bạn có thể mở trang sau để tiếp tục:
{{username_recovery_url}}

Quyền xem có hiệu lực đến {{expires_at_with_timezone}}.
Liên kết này chỉ dùng cho việc xem tên đăng nhập và không thay đổi
mật khẩu, MFA hoặc passkey.

Không chuyển tiếp liên kết cho người khác.
Nếu bạn không gửi yêu cầu, bạn có thể bỏ qua thông điệp này.

Bạn cũng có thể tự mở ứng dụng hoặc trang chính thức của {{product_name}}
để bắt đầu lại việc khôi phục.

Không gửi mật khẩu hoặc mã xác thực khi trả lời thư.
{{product_name}}
```

Thời gian hiển thị phải được dựng từ hạn dùng phía máy chủ với múi giờ rõ ràng. Không hứa “dùng một lần” nếu máy chủ không thực thi, hoặc ghi một thời hạn khác với thời hạn thực của token.

Nếu trang xem cần thêm bằng chứng, thư nên nói rõ người dùng có thể được yêu cầu hoàn thành bước xác minh. Không hứa rằng nhấp vào liên kết chắc chắn hiển thị tên đăng nhập trong mọi tình huống.

### 6.2. Quyền xem phải tách khỏi quyền đăng nhập

Một mô hình thử thách có thể gồm:

```text
username_disclosure_challenge:
  challenge_id
  token_verifier
  purpose = DISCLOSE_USERNAME
  account_id
  tenant_id
  identity_version
  recovery_channel_id
  recovery_channel_version
  expires_at
  consumed_at
```

Token cần được sinh khó đoán và kiểm chứng phía máy chủ. Nó gắn với định danh tài khoản bền vững, không chỉ một chuỗi username có thể đổi hoặc được cấp lại cho tài khoản khác.

Ở bước tiết lộ, máy chủ kiểm tra mục đích, hạn dùng, tính dùng một lần, trạng thái tài khoản và các phiên bản liên quan. Không cho máy khách thay `account_id` hoặc `tenant_id` để dùng quyền xem cho người khác.

Token này không được chấp nhận tại endpoint đăng nhập, reset mật khẩu, hủy MFA hoặc đăng ký passkey. Một ngữ cảnh xem tên đăng nhập cũng không nên được biến thành phiên tài khoản có quyền đầy đủ.

### 6.3. Cân nhắc trình quét liên kết

Hệ thống thư có thể mở liên kết trước người dùng. Một cách thiết kế là để yêu cầu `GET` chỉ hiển thị trang trung gian, không tiết lộ ngay thông tin và không tiêu thụ quyền xem cuối cùng. Người dùng chủ động tiếp tục bằng một thao tác thay đổi trạng thái được bảo vệ phù hợp; khi đó mới kiểm tra lại và sử dụng quyền xem.

Điều này giảm tác động của những trình quét chỉ truy cập liên kết thông thường. Nó không chứng minh người bấm nút là chủ tài khoản, không ngăn mọi công cụ tự động và không thay thế bằng chứng bổ sung khi chính sách yêu cầu.

Trang chứa quyền xem hoặc tên đăng nhập cần có chính sách cache phù hợp, chẳng hạn `Cache-Control: no-store`, và kiểm soát referrer thích hợp. Tránh tài nguyên theo dõi hoặc nội dung bên thứ ba có thể nhận URL hay dữ liệu khôi phục. Token trong URL phải được loại khỏi log ở các tầng có thể ghi URL, không chỉ log của mã ứng dụng.

## 7. Dựng thông điệp an toàn và dễ sử dụng

### 7.1. Tách dữ liệu khỏi cấu trúc thư

Tên đăng nhập, tên sản phẩm và các dữ liệu hiển thị cần được xử lý như dữ liệu. Với HTML, dùng cơ chế tự escape theo đúng ngữ cảnh của template; không đánh dấu một giá trị người dùng có thể ảnh hưởng là HTML an toàn.

Ví dụ cấu trúc hiển thị, giả sử template engine tự escape nội dung biến:

```html
<p>Tên đăng nhập của bạn:</p>
<p><bdi>{{ username }}</bdi></p>
<p>Hãy mở ứng dụng hoặc trang đăng nhập chính thức để tiếp tục.</p>
```

Phần tử hiển thị không phải lớp xác thực. Giá trị username vẫn phải được lấy từ dữ liệu có thẩm quyền và được escape. Đường dẫn trong thuộc tính HTML còn cần được tạo từ miền được phép, không chỉ escape một URL do máy khách đưa vào.

Các header như người gửi, người nhận và tiêu đề cần được tạo bằng thư viện phù hợp, không nối chuỗi thô có thể chứa xuống dòng hoặc cấu trúc header do người gửi kiểm soát.

### 7.2. Giữ bản văn bản thuần đầy đủ ý nghĩa

Không chỉ đặt tên đăng nhập trong một ảnh hoặc một nút có nhãn mơ hồ. Người đọc bằng công cụ hỗ trợ, người tắt tải ảnh hoặc người dùng trình đọc thư đơn giản vẫn phải hiểu được nội dung cần thiết.

Nếu có cả HTML và văn bản thuần, hai bản phải thống nhất về tên đăng nhập, miền đích, thời hạn và phạm vi hành động. Không để bản HTML nói “xem tên đăng nhập” nhưng bản văn bản chứa một liên kết đăng nhập tự động.

Tránh hình thức khiến người dùng sao chép kèm dấu câu trang trí vào tên đăng nhập. Với định danh có Unicode, cần kiểm tra cách hiển thị và hướng văn bản phù hợp; không tự sửa định danh trong nội dung thư để che một vấn đề của chính sách đặt tên.

### 7.3. Ngôn ngữ và thương hiệu từ nguồn tin cậy

Chọn bản dịch từ cấu hình hoặc lựa chọn ngôn ngữ đã được kiểm tra. Nếu chưa có bản dịch, dùng một bản dự phòng rõ ràng. Không chèn nguyên văn nội dung tự do do người gửi đưa vào thành lời nhắn của hệ thống.

Trong môi trường nhiều tenant, tên và thương hiệu tenant phải lấy từ cấu hình được quản lý. Cần giới hạn nội dung tùy biến để tránh thư khôi phục bị biến thành công cụ gửi thông điệp giả mạo.

## 8. Chọn đúng người nhận khi dữ liệu thay đổi

### 8.1. Địa chỉ được dùng phải là kênh được phép

Một kênh đã xác minh từ trước vẫn cần được đánh giá theo chính sách hiện tại. Số điện thoại có thể được cấp lại, hộp thư có thể trở thành hộp thư dùng chung hoặc địa chỉ có thể đã được thay trong tài khoản.

Không coi trường email không rỗng là đủ điều kiện nhận thông tin. Không tự áp dụng các quy tắc như xóa dấu chấm hoặc bỏ phần sau dấu cộng để gộp địa chỉ của mọi nhà cung cấp. Cần dùng ánh xạ và quy tắc nhận diện đã được thiết kế khi đăng ký kênh.

### 8.2. Hàng đợi phải ràng buộc đúng tài khoản và phiên bản kênh

Một công việc gửi nên tham chiếu tới tài khoản và kênh bằng định danh ổn định, đồng thời lưu phiên bản dự kiến. Khi lấy công việc ra, worker kiểm tra lại tài khoản còn đủ điều kiện, kênh còn được phép và phiên bản có còn khớp không.

Nếu kênh đã đổi, không tự gửi sang kênh mới chỉ bằng cách đọc trường email mới nhất. Quyền gửi từ yêu cầu ban đầu có thể không bao phủ địa chỉ mới. Chính sách cần hủy công việc lỗi thời hoặc đánh giá lại để tạo một công việc được cấp quyền mới.

Tên đăng nhập cũng có thể đổi trong lúc chờ. Không gửi một username đã được cấp cho tài khoản khác. Một chính sách đơn giản là hủy khi phiên bản định danh thay đổi và yêu cầu bắt đầu lại; một chính sách khác có thể đánh giá lại rồi dựng thông điệp với định danh hiện hành. Phải chọn rõ, không vô tình trộn username cũ với tài khoản mới.

### 8.3. Kiểm tra trước gửi không làm thư trở thành có thể thu hồi

Kiểm tra ngay trước khi gửi giảm rủi ro dữ liệu cũ, nhưng vẫn có khoảng thời gian giữa kiểm tra, nhà cung cấp chấp nhận và người nhận đọc. Không có một giao dịch cơ sở dữ liệu thông thường nào có thể bảo đảm thu hồi mọi bản sao của một email trực tiếp đã gửi.

Nếu cần kiểm soát hiệu lực tới thời điểm xem, hình thức liên kết cho phép kiểm tra lại và vô hiệu hóa quyền theo phiên bản kênh hoặc định danh. Tuy nhiên, khi người nhận đã xem hoặc sao chép thông tin, cơ chế đó cũng không thu hồi được hiểu biết đã được tiết lộ.

## 9. Nhiều tài khoản, nhiều tenant và kênh liên hệ dùng chung

Một email có thể liên quan tới nhiều tài khoản, hoặc cùng một người có nhiều tên đăng nhập theo tổ chức. Không mặc định rằng mọi tài khoản dùng cùng chuỗi email đều được phép liệt kê trong một thông điệp.

Cần xác định:

- Kênh đó đã được xác minh và được phép khôi phục cho từng tài khoản nào?
- Ngữ cảnh tổ chức hiện tại có được xác định một cách đáng tin cậy không?
- Việc tiết lộ tên tổ chức hoặc số lượng tài khoản có được phép không?
- Hộp thư là của một cá nhân, một nhóm hay một vai trò dùng chung?

Nếu chỉ được phép khôi phục tài khoản trong một tenant, nội dung không được kéo thêm danh sách từ những tenant khác. Nếu chính sách cho phép nhiều định danh trong cùng thông điệp, cần gắn nhãn đủ để người nhận dùng đúng, nhưng không bổ sung vai trò, quyền hoặc thông tin tổ chức vượt nhu cầu.

Không gửi câu như “Bạn còn ba tài khoản ở các tổ chức khác” chỉ để gợi ý thêm. Đó là một tiết lộ khác, cần một quyết định quyền riêng biệt.

Trong tài khoản liên kết SSO, thông điệp có thể hướng tới trang đăng nhập tổ chức thay vì đưa một username không sử dụng được tại biểu mẫu cục bộ. Hướng dẫn phải đúng mô hình xác thực, không vô tình khuyến khích người dùng mở luồng reset mật khẩu sai nơi.

## 10. Email, SMS và thông báo trong ứng dụng

### 10.1. Email

Email phù hợp với nội dung có hướng dẫn, nhưng phần thân có thể bị chuyển tiếp, sao lưu và đồng bộ trên nhiều thiết bị. Cần chọn người gửi và cấu hình xác thực miền gửi phù hợp với hạ tầng thư, đồng thời giữ đường dẫn nhất quán với miền chính thức.

Không thêm pixel theo dõi hoặc liên kết phân tích bên thứ ba vào thông điệp chỉ để biết người dùng đã đọc. Những thành phần đó có thể tạo thêm dữ liệu liên kết người nhận và làm phức tạp đường dẫn khôi phục.

### 10.2. SMS

SMS có không gian trình bày hạn chế, có thể hiển thị ngay trên màn hình khóa và chịu rủi ro của kênh số điện thoại. Không rút gọn đến mức mất tên sản phẩm, mục đích hoặc hướng dẫn nhận biết liên kết chính thức.

Ví dụ nếu chính sách cho phép gửi trực tiếp:

```text
{{product_name}}: Tên đăng nhập bạn yêu cầu là {{username}}.
Yêu cầu này không đổi mật khẩu. Nếu không yêu cầu, bạn có thể bỏ qua.
```

Đây chỉ là mẫu nội dung. Cần kiểm tra độ dài và mã hóa thực tế, nhất là với tiếng Việt và username dài. Không cắt bớt tên đăng nhập để vừa một giới hạn rồi gửi một định danh sai. Khi nội dung không phù hợp, dùng một hình thức được phép khác thay vì chia bí mật tùy tiện giữa nhiều thông điệp.

Không dùng liên kết rút gọn khó kiểm tra chỉ để tiết kiệm ký tự. Nếu chọn liên kết xem, người dùng vẫn cần nhận biết được miền chính thức và mục đích thao tác.

### 10.3. Thông báo trong ứng dụng hoặc push

Một thiết bị đã đăng ký có thể cung cấp đường nhận khác, nhưng thông báo push không đồng nghĩa người cầm thiết bị là chủ tài khoản đã được xác thực gần đây. Có thể chỉ thông báo có hướng dẫn và yêu cầu mở ứng dụng trước khi xem định danh.

Không đẩy username đầy đủ lên màn hình khóa nếu chính sách không cho phép. Không chọn một token thiết bị cũ hoặc thiết bị đã bị thu hồi chỉ vì nó còn tồn tại trong cơ sở dữ liệu.

## 11. Chống spam, gửi lại và lỗi chuyển phát

### 11.1. Gửi yêu cầu không được trở thành công cụ quấy rối

Người ngoài có thể nhập địa chỉ của nạn nhân nhiều lần. Hệ thống cần giới hạn theo tài khoản, đích nhận, nguồn truy cập và thời gian phù hợp. Không chỉ dựa vào IP và không cho một lượng yêu cầu công khai làm chủ tài khoản mất khả năng khôi phục vĩnh viễn.

Có thể gộp hoặc bỏ qua các yêu cầu lặp trong một khoảng thời gian theo chính sách. Phản hồi công khai vẫn cần trung tính, không cho biết một email có nhận thông điệp hay đang bị giới hạn riêng theo tài khoản.

Một yêu cầu tìm tên đăng nhập tự nó không nên đổi mật khẩu, đăng xuất người dùng hoặc hủy các phương thức xác thực. Những tác động đó vừa vượt mục đích vừa có thể bị lợi dụng để gây từ chối dịch vụ.

### 11.2. Gửi lại không đồng nghĩa thu hồi mọi quyền xem trước đó

Nếu mỗi yêu cầu mới lập tức làm liên kết trước vô hiệu, người ngoài có thể liên tục yêu cầu để người dùng không mở được thư vừa nhận. Cần thiết kế số quyền xem đang hoạt động, thời hạn và chính sách gửi lại sao cho không tạo đường gây gián đoạn đơn giản.

Mặt khác, không cấp liên kết vô hạn. Một giới hạn hữu hạn, cơ chế gộp yêu cầu và trạng thái thử thách rõ ràng giúp cân bằng khả năng sử dụng với chống lạm dụng.

Nếu chỉ lưu verifier của token, hệ thống không thể tính lại token rõ để dựng lại cùng liên kết. Muốn gửi lại chính xác thông điệp bí mật ban đầu, cần một cơ chế giữ nội dung được bảo vệ trong thời gian cần thiết, chẳng hạn payload mã hóa ngắn hạn của hệ thống chuyển phát. Khi đó phải quản lý quyền đọc, khóa và thời hạn xóa; không mô tả nó như thể chỉ còn dữ liệu một chiều.

Một lựa chọn khác là cấp quyền xem mới theo chính sách đã định nghĩa. Việc đó cần xem xét hiệu lực của quyền cũ và nguy cơ người ngoài gây gián đoạn, không chỉ sinh token mới ở mỗi lần bấm.

### 11.3. Không hứa gửi đúng một lần khi hạ tầng không bảo đảm

Nếu nhà cung cấp đã nhận thư nhưng phản hồi bị mất, worker có thể không biết thư đã được chấp nhận. Khi thử lại có thể xảy ra bản sao. Cần dùng định danh thao tác, trạng thái gửi và khả năng khử trùng lặp của nhà cung cấp nếu có, đồng thời thiết kế nội dung chịu được việc nhận trùng.

Không để mỗi lần thử lại việc gửi tạo thêm tài khoản, thay thông tin xác thực hoặc cấp quyền rộng hơn. Với liên kết đã dùng hoặc hết hạn, trang đích cần đưa ra hướng xử lý phù hợp mà không tiết lộ dữ liệu chỉ từ một mã không còn quyền.

### 11.4. Bounce và lỗi nhà cung cấp là dữ liệu vận hành

Không trả nguyên lỗi chuyển phát cho người chưa xác minh vì lỗi có thể tiết lộ sự tồn tại hoặc trạng thái của địa chỉ. Callback từ nhà cung cấp phải được xác minh theo cơ chế tích hợp trước khi cập nhật trạng thái nội bộ.

Một lần gửi thất bại không cho phép tự đổi địa chỉ nhận, chuyển sang kênh chưa được phép hoặc khẳng định tài khoản không tồn tại. Cần tách lỗi chuyển phát khỏi quyết định định danh và quyền khôi phục.

## 12. Mã giả điều phối thông điệp

Ví dụ dưới đây chọn chính sách hủy công việc nếu phiên bản định danh hoặc kênh đã thay đổi. Đây là một lựa chọn minh họa, không phải bắt buộc cho mọi hệ thống.

```text
acceptUsernameRecoveryRequest(request):
    enforcePublicRequestLimits(request)
    normalizedIdentifier = normalizeUsingRegisteredIdentifierRules(request)

    # Kết quả tra cứu và quyết định không được đưa vào phản hồi công khai.
    decision = evaluateUsernameDisclosureRoute(normalizedIdentifier)
    if decision permits delivery:
        transaction:
            insertDeliveryOutboxIfAllowed(
                accountId = decision.accountId,
                tenantId = decision.tenantId,
                channelId = decision.channelId,
                expectedChannelVersion = decision.channelVersion,
                expectedIdentityVersion = decision.identityVersion,
                templateVersion = configuredTemplateVersion,
                deliveryMode = decision.deliveryMode,
                operationId = newOperationId()
            )

    return genericAcknowledgement()
```

Việc đọc và ghi ở bước cấp công việc cần bảo đảm ràng buộc được kiểm tra theo cơ chế nhất quán của hệ thống. Worker vẫn đánh giá lại trước chuyển phát:

```text
deliverUsernameRecoveryMessage(job):
    claimJobWithBoundedRetryPolicy(job)
    state = loadAuthoritativeAccountIdentityAndChannel(job)

    if not stillEligibleForUsernameDisclosure(state, job):
        cancelWithoutRevealingDetails(job)
        return

    if state.channelVersion != job.expectedChannelVersion:
        cancelAsStale(job)
        return

    if state.identityVersion != job.expectedIdentityVersion:
        cancelAsStale(job)
        return

    recipient = resolveApprovedDestination(state.channel)
    model = buildMinimalTrustedTemplateModel(state, job)

    if job.deliveryMode == CONTROLLED_VIEW_LINK:
        model.recoveryUrl = obtainScopedDisclosureLinkUsingDefinedLifecycle(job)

    message = renderEscapedTemplate(model, job.templateVersion)
    result = deliverViaApprovedProvider(recipient, message, job.operationId)
    recordDeliveryOutcomeWithoutMessageBody(job, result)
```

Các hàm trong ví dụ biểu diễn trách nhiệm, không phải một thư viện hoàn chỉnh. Việc cấp token, lưu verifier và giữ payload chuyển phát nếu cần phải có ranh giới rõ ràng. Không ghi body hoặc liên kết bí mật vào log để phục vụ thử lại.

Khóa một hàng cơ sở dữ liệu không làm giao dịch của nhà cung cấp thư trở thành nguyên tử với cơ sở dữ liệu. Cần thừa nhận cửa sổ gửi trùng và cửa sổ thay đổi trạng thái, chọn chính sách phù hợp và kiểm tra lại khi tiết lộ qua trang có kiểm soát.

## 13. Tình huống xuyên suốt: đổi email khi thông điệp còn trong hàng đợi

Vy yêu cầu tìm tên đăng nhập khi tài khoản có kênh email phiên bản 7 và định danh phiên bản 12. Công việc gửi được tạo với các phiên bản đó nhưng chưa chuyển phát.

1. Trước khi worker xử lý, Vy hoàn tất một luồng hợp lệ để đổi email. Kênh cũ bị thu hồi và trạng thái hiện tại chuyển sang phiên bản mới.
2. Worker đọc lại dữ liệu, thấy phiên bản kênh không khớp và hủy công việc lỗi thời theo chính sách của ví dụ.
3. Worker không gửi tới email cũ và cũng không tự chuyển công việc sang email mới. Một yêu cầu mới có thể được mở theo điều kiện hiện tại.
4. Nếu một liên kết xem đã được gửi trước lúc thu hồi, bước tiết lộ cần kiểm tra phiên bản kênh; liên kết đó không tiếp tục cho xem chỉ vì còn hạn thời gian.
5. Nếu thư đã chứa tên đăng nhập trực tiếp và đã được nhận, hệ thống không thể bảo đảm thu hồi bản sao. Đây là giới hạn cần được cân nhắc khi chọn hình thức tiết lộ ban đầu.

Trong một biến thể khác, username cũ của Vy đã đổi và được cấp cho người khác. Vì công việc gắn với tài khoản bền vững cùng phiên bản định danh, nó không được tra ngược username cũ rồi gửi thông tin của chủ mới.

Không bước nào trong tình huống này tự đổi mật khẩu, tắt MFA, đăng ký passkey hoặc tạo phiên đăng nhập. Người dùng lấy lại tên đăng nhập rồi tiếp tục xác thực hoặc khôi phục những yếu tố còn thiếu qua các luồng tương ứng.

## 14. Các tình huống kiểm chứng và dấu vết vận hành

### 14.1. Tiêu chí hành vi

| Tình huống | Kết quả mong đợi |
|---|---|
| Định danh không tồn tại hoặc không có tuyến gửi phù hợp | Phản hồi công khai không xác nhận kết quả tra cứu |
| Tài khoản có username nhưng người gửi chưa có bằng chứng trên trình duyệt | Không hiển thị username ngay trong phản hồi công khai |
| Người gửi chỉ định một địa chỉ nhận mới | Không gửi thông tin tài khoản nếu chưa qua luồng xác minh tương ứng |
| Tiêu đề hoặc nội dung xem trước được hiển thị trên màn hình khóa | Không có username hoặc token tại vị trí không được phép |
| Username có ký tự đặc biệt | Được hiển thị đúng, không trở thành HTML hoặc cấu trúc thư |
| URL đích được gửi từ tham số không đáng tin | Không được dùng để dựng liên kết khôi phục |
| Một email liên quan tới nhiều tenant | Không tự liệt kê quan hệ ngoài phạm vi được phép |
| Kênh nhận thay đổi sau khi tạo công việc | Công việc được hủy hoặc đánh giá lại theo chính sách rõ ràng, không tự chuyển đích |
| Username đổi hoặc được cấp lại | Tham chiếu vẫn gắn đúng tài khoản bền vững; không tiết lộ dữ liệu chủ mới |
| Trình quét thư mở liên kết | Không tự cấp phiên, thay thông tin xác thực hoặc tiêu thụ bước tiết lộ cuối theo thiết kế trung gian |
| Token dùng cho endpoint reset mật khẩu hoặc đăng nhập | Bị từ chối vì sai mục đích |
| Kênh bị thu hồi trước lúc người dùng xem | Quyền xem được kiểm tra lại, không chỉ kiểm tra hạn dùng |
| Gửi lại khi chỉ lưu verifier token | Không giả định có thể tái tạo token rõ từ verifier |
| Nhà cung cấp nhận thư nhưng phản hồi mất | Cơ chế thử lại không mở rộng quyền; nội dung và trạng thái xử lý được việc trùng |
| Lỗi bounce hoặc lỗi nội bộ | Không được công khai nguyên chi tiết cho người chưa xác minh |
| Yêu cầu tìm tên đăng nhập bị gửi liên tục | Được giới hạn mà không tự thay mật khẩu hay khóa vĩnh viễn chủ tài khoản |
| Người dùng biết username nhưng mất MFA hoặc passkey | Chuyển sang luồng khôi phục yếu tố phù hợp, không coi thông điệp là bằng chứng đầy đủ |

Đây là các tiêu chí để người triển khai kiểm chứng thiết kế, không phải kết quả thử nghiệm của một hệ thống cụ thể.

### 14.2. Ghi sự kiện thay vì sao chép toàn bộ thông điệp

Audit có thể giữ định danh thao tác, tham chiếu tài khoản và kênh nội bộ, loại thông điệp, phiên bản template, phiên bản định danh, quyết định gửi hoặc hủy, kết quả chuyển phát và thời gian. Quyền đọc và thời gian lưu cần phù hợp vì các tham chiếu này vẫn có thể cho biết hoạt động tài khoản.

Không ghi username nếu không cần cho mục tiêu vận hành, địa chỉ nhận đầy đủ trong nhãn chỉ số, toàn bộ body, URL chứa token hoặc bằng chứng khôi phục. Nội dung thử nghiệm nên dùng dữ liệu giả lập; không sao chép thư thật vào hệ thống theo dõi lỗi chỉ để kiểm tra giao diện.

Một thông điệp gửi lại tên đăng nhập chỉ hoàn thành mục đích khi đúng thông tin được chuyển qua đúng kênh, trong phạm vi được phép và với hướng dẫn đúng về hành động tiếp theo. Khả năng đọc được tên đăng nhập giúp người dùng tiếp tục quá trình truy cập; nó không tự chứng minh quyền thay mật khẩu, MFA, passkey hoặc phiên đăng nhập của tài khoản.
