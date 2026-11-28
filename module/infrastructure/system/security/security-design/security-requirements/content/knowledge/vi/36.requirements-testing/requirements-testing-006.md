# Authentication test

## 1. Kiểm thử xác thực cần chứng minh điều gì?

**Authentication test** là kiểm thử cách hệ thống xác minh và duy trì danh tính của chủ thể. Chủ thể có thể là người dùng, dịch vụ hoặc một tiến trình tự động. Mục tiêu là chứng minh rằng hệ thống chỉ thiết lập ngữ cảnh xác thực khi các điều kiện đã được đặc tả thực sự được đáp ứng.

Một phép thử xác thực không chỉ kiểm tra màn hình đăng nhập. Nó cần xem xét:

- Đường vào của thông tin xác thực và cách xử lý trường hợp sai.
- Trạng thái tài khoản và các yếu tố xác minh bắt buộc.
- Việc tạo, sử dụng, hết hạn và thu hồi phiên hoặc token.
- Giới hạn thử sai, khả năng dùng lại và các thao tác đồng thời.
- Đăng xuất, đổi mật khẩu và khôi phục tài khoản.
- Những đường truy cập khác như API, ứng dụng di động hoặc nhà cung cấp định danh.
- Nhật ký phục vụ phát hiện, điều tra và kiểm chứng mà không làm lộ bí mật.

Chuỗi truy vết cần giữ là:

> Yêu cầu xác thực có phiên bản → tình huống và trạng thái → hành vi kỳ vọng → quan sát ở phía máy chủ → bằng chứng.

Các yêu cầu, mã và ngưỡng trong bài đều là **giả định phục vụ học tập**. Không lấy chúng làm chính sách mật khẩu, thời hạn phiên hoặc ngưỡng khóa mặc định cho một dự án khác.

### Xác thực và phân quyền là hai đối tượng kiểm thử khác nhau

| Tình huống | Nội dung chính cần đánh giá |
| --- | --- |
| Không có thông tin xác thực nhưng truy cập được API yêu cầu đăng nhập | Xác thực |
| Đúng mật khẩu nhưng chưa hoàn tất yếu tố thứ hai mà đã nhận quyền truy cập | Xác thực |
| Phiên hết hạn vẫn được máy chủ chấp nhận | Xác thực và vòng đời phiên |
| Người đã xác thực vào được dữ liệu của tenant khác | Phân quyền |
| Người dùng thường gọi được thao tác chỉ dành cho quản trị | Phân quyền; có thể liên quan yêu cầu xác minh bổ sung |

Một người dùng hợp lệ nhận phản hồi từ chối ở API quản trị chưa chứng minh đăng nhập thất bại. Có thể danh tính đã được xác thực nhưng không có quyền quản trị.

Ngược lại, phản hồi thành công của bước kiểm tra mật khẩu chưa chắc là đăng nhập hoàn tất. Với luồng MFA, đó có thể chỉ là trạng thái chờ yếu tố tiếp theo.

## 2. Xác định phạm vi và chuẩn bị fixture

Trước khi tạo test case, cần liệt kê các cách hệ thống thiết lập hoặc sử dụng danh tính:

| Đường truy cập hoặc vòng đời | Câu hỏi phạm vi |
| --- | --- |
| Đăng nhập web | Dùng cookie, token hay một tầng trung gian nào? |
| API và ứng dụng khác | Có kiểm tra cùng điều kiện hay có luồng riêng? |
| Đăng nhập liên kết | Nhà cung cấp nào được tin cậy và ai xác minh kết quả? |
| MFA | Khi nào bắt buộc, challenge gắn với ai và hoàn tất thế nào? |
| Khôi phục tài khoản | Khôi phục mật khẩu và khôi phục yếu tố thứ hai có khác nhau không? |
| Danh tính máy | Dùng khóa API, token, chứng thư hoặc cơ chế nào? |
| Phiên đang tồn tại | Những điểm thực thi nào phải nhận biết hết hạn hoặc thu hồi? |

Bài học dùng một ứng dụng có đăng nhập mật khẩu, MFA cho nhóm bắt buộc, phiên phía máy chủ và API yêu cầu xác thực. Các cơ chế khác được xem xét ở phần mở rộng theo yêu cầu thực tế.

### Bộ fixture giả định

| Fixture | Trạng thái và mục đích |
| --- | --- |
| user-basic | Tài khoản hoạt động, không thuộc nhóm bắt buộc MFA trong ví dụ |
| user-mfa | Tài khoản hoạt động, bắt buộc MFA |
| user-disabled | Tài khoản bị vô hiệu hóa |
| identity-unknown | Định danh không tồn tại nhưng có hình thức đầu vào hợp lệ |
| password-valid | Mật khẩu thử đúng của tài khoản tương ứng |
| password-wrong | Mật khẩu thử sai |
| otp-fixture | Mã xác minh do bộ cung cấp thử tạo theo đúng challenge |
| protected-resource | Một API chỉ yêu cầu xác thực, phù hợp để kiểm tra trạng thái đăng nhập |

Dùng dữ liệu thử riêng cho từng lần chạy và đặt trạng thái bộ đếm rõ ràng. Nếu test trước đã chạm ngưỡng thử sai, test sau có thể bị từ chối vì giới hạn thay vì vì thông tin xác thực sai.

Mật khẩu và mã thử vẫn cần được bảo vệ trong hiện vật của bộ thử. Không in đầy đủ cookie, token, OTP hoặc liên kết khôi phục vào báo cáo để chứng minh phép thử đã chạy.

## 3. Bộ yêu cầu xác thực giả định làm căn cứ

Không thể kết luận một test đạt nếu chưa biết chính sách hệ thống phải đáp ứng. Bộ yêu cầu dưới đây được xác định riêng cho ví dụ.

### AUTH-LOGIN-01@1 — đăng nhập bằng mật khẩu

- Chỉ tài khoản đang hoạt động với mật khẩu hợp lệ mới được vượt qua bước xác minh mật khẩu.
- Với nhóm bắt buộc MFA, vượt qua bước mật khẩu chỉ tạo trạng thái chờ MFA; chưa được truy cập tài nguyên yêu cầu đăng nhập hoàn chỉnh.
- Theo hợp đồng API của ví dụ, sai mật khẩu, tài khoản không tồn tại và tài khoản bị vô hiệu hóa cùng trả 401 với nội dung lỗi công khai AUTH_FAILED.
- Các trường hợp trên không được tạo phiên xác thực hoàn chỉnh.
- Thông báo công khai không được chỉ rõ định danh có tồn tại hoặc trạng thái nội bộ của tài khoản.

### AUTH-MFA-02@1 — hoàn tất nhiều yếu tố

- Challenge gắn với đúng tài khoản, giao dịch xác thực và mục đích.
- Challenge có hiệu lực trong khoảng từ lúc tạo đến trước mốc tạo cộng 120 giây.
- Challenge và phản hồi hợp lệ chỉ được dùng một lần để hoàn tất xác thực.
- OTP đã được dùng thành công không được dùng lại để hoàn tất một lần xác thực khác trong phạm vi hiệu lực được đặc tả của ví dụ.
- Tối đa 3 phản hồi sai được xử lý cho một challenge; sau lần sai thứ ba, challenge không được dùng tiếp.
- Không có đường API hoặc giao diện khác cho phép nhóm bắt buộc bỏ qua yếu tố thứ hai.

Bộ yêu cầu này giả định một cơ chế OTP có thể kiểm soát trong môi trường thử. Khi sử dụng yếu tố khác, cần thay dữ liệu và oracle theo cơ chế đã được phê duyệt.

### AUTH-SESSION-03@1 — vòng đời phiên

- Sau xác thực hoàn chỉnh, hệ thống tạo định danh phiên mới; định danh trước xác thực không được trở thành phiên đã đăng nhập.
- Phiên có thời hạn tuyệt đối 900 giây kể từ lúc tạo phiên hoàn chỉnh. Tại mốc hết hạn, máy chủ không được chấp nhận phiên.
- Hoạt động liên tục không kéo dài thời hạn tuyệt đối này.
- Trong tối đa 30 giây từ khi hệ thống tiếp nhận hợp lệ lệnh đăng xuất của một phiên, các điểm thực thi thuộc phạm vi phải ngừng chấp nhận phiên đó.
- Đăng xuất một phiên không mặc nhiên đăng xuất mọi phiên khác; chức năng đăng xuất toàn bộ cần có yêu cầu riêng.

### AUTH-RATE-04@1 — giới hạn thử mật khẩu sai

- Bộ đếm gắn với định danh đã được chuẩn hóa theo chính sách định danh của ứng dụng, không chỉ với địa chỉ IP.
- Lần sai thứ năm trong cửa sổ trượt 600 giây kích hoạt hạn chế 300 giây kể từ lần sai thứ năm.
- Lần sai thứ năm vẫn nhận kết quả thất bại thông thường; các lần thử tiếp theo trong khoảng hạn chế nhận kết quả 429 theo hợp đồng ví dụ, kể cả khi gửi mật khẩu đúng.
- Khoảng hạn chế kết thúc tại mốc bắt đầu cộng 300 giây.
- Sau hạn, thông tin xác thực hợp lệ có thể được xử lý bình thường; đăng nhập hoàn chỉnh thành công xóa bộ đếm của định danh đó.
- Chính sách phản hồi và bộ đếm phải được áp dụng nhất quán cho định danh tồn tại và không tồn tại.
- Các điểm tiếp nhận đăng nhập thuộc phạm vi phải chia sẻ hiệu lực của giới hạn.

Cửa sổ trượt được tính trên các lần sai có thời điểm trong khoảng lớn hơn t − 600 và không lớn hơn t tại thời điểm đánh giá t. Quy tắc này giúp chốt kết quả ở đúng ranh giới.

### AUTH-RECOVERY-05@1 — khôi phục mật khẩu

- Yêu cầu khôi phục cho định danh tồn tại hoặc không tồn tại cùng nhận 202 và thông điệp công khai chung.
- Yêu cầu gửi khôi phục chưa làm thay đổi mật khẩu hoặc vô hiệu hóa phiên hiện có.
- Chỉ tài khoản hợp lệ mới nhận phương tiện khôi phục qua kênh đã xác minh.
- Token khôi phục gắn với tài khoản và mục đích, dùng một lần, hết hiệu lực tại mốc tạo cộng 600 giây.
- Sau khi đổi mật khẩu thành công, mật khẩu cũ không được dùng cho lần đăng nhập mới.
- Các phiên cũ phải bị thu hồi trong tối đa 30 giây sau khi giao dịch đổi mật khẩu được hoàn tất.
- Khôi phục mật khẩu không tự cấp phiên hoàn chỉnh hoặc bỏ qua yêu cầu MFA còn áp dụng.

### AUTH-AUDIT-06@1 — ghi nhận mà không lộ bí mật

- Phải truy vết được đăng nhập thành công, thất bại, bị hạn chế, kết quả MFA, hoàn tất khôi phục và đăng xuất.
- Sự kiện có thời điểm, hành động, kết quả, định danh tài khoản khi đã xác định và mã liên kết.
- Không ghi mật khẩu, OTP, token phiên hoặc token khôi phục nguyên vẹn.
- Kết quả nội bộ phải đủ phục vụ vận hành theo quyền phù hợp; lỗi công khai vẫn phải tuân theo chính sách thông báo.

Các giá trị 3, 5, 30, 120, 300, 600 và 900 trong bài đều xuất phát từ bộ yêu cầu giả định này. Nếu chưa có ngưỡng đã xác nhận trong dự án thật, test case phải ghi câu hỏi mở thay vì tự điền các số trên.

## 4. Lập ma trận kiểm thử theo điều kiện

| Chiều kiểm tra | Giá trị hoặc trạng thái cần xét |
| --- | --- |
| Danh tính | Tồn tại, không tồn tại, bị vô hiệu hóa |
| Mật khẩu | Đúng, sai, trống, đầu vào không đúng định dạng theo hợp đồng |
| MFA | Chưa làm, hợp lệ, sai, hết hạn, dùng lại, sai tài khoản hoặc giao dịch |
| Phiên | Trước xác thực, hợp lệ, hết hạn, sau đăng xuất, sau khôi phục |
| Bộ đếm | Chưa chạm ngưỡng, đúng ngưỡng, đang hạn chế, hết hạn chế |
| Đường truy cập | Giao diện, API trực tiếp, những điểm tiếp nhận khác thuộc phạm vi |
| Đồng thời | Nhiều lần dùng OTP, nhiều lần gửi reset, nhiều điểm đăng nhập |
| Phụ thuộc | Dịch vụ danh tính, kho phiên hoặc dịch vụ MFA không phản hồi |
| Bằng chứng | Phản hồi, phiên được tạo, quyền truy cập tài nguyên và sự kiện |

Không cần tạo mọi tổ hợp một cách máy móc. Cần chọn tổ hợp theo rủi ro và giữ đủ điều kiện để biết nguyên nhân kết quả.

Ví dụ, muốn thử mật khẩu sai thì tài khoản nên hoạt động và chưa bị hạn chế. Muốn thử tài khoản vô hiệu hóa thì dùng mật khẩu vốn hợp lệ của tài khoản đó để cô lập điều kiện trạng thái.

Không chỉ kiểm tra “endpoint đăng nhập trả gì”. Sau các bước quan trọng, thử truy cập protected-resource bằng ngữ cảnh nhận được để xác minh máy chủ có thực sự coi chủ thể là đã xác thực hay không.

## 5. Test case đăng nhập và chống lộ trạng thái tài khoản

### 5.1. Trường hợp hợp lệ

**Mã:** TC-AUTH-LOGIN-001.  
**Yêu cầu:** AUTH-LOGIN-01@1 và AUTH-SESSION-03@1.

**Điều kiện đầu:** user-basic hoạt động, không bị hạn chế; mật khẩu đúng; không thuộc nhóm bắt buộc MFA.

**Các bước:**

1. Tạo một ngữ cảnh trình duyệt hoặc client mới.
2. Ghi nhận định danh phiên trước xác thực nếu có.
3. Gửi thông tin đăng nhập đúng.
4. Thu ngữ cảnh phiên sau xác thực.
5. Gọi protected-resource bằng phiên mới.
6. Thử dùng lại định danh trước xác thực nếu có.

**Kết quả kỳ vọng:**

- Đăng nhập hoàn chỉnh thành công.
- Phiên mới được máy chủ chấp nhận tại tài nguyên phù hợp.
- Định danh phiên sau xác thực khác định danh trước đó.
- Định danh trước xác thực không dùng để truy cập với danh tính đã đăng nhập.

Một cookie mới không tự chứng minh đã đăng nhập. Một số cookie chỉ phục vụ ngữ cảnh chưa xác thực hoặc bảo vệ luồng; cần kiểm tra hiệu lực ở phía máy chủ.

### 5.2. Các trường hợp thất bại

**Mã:** TC-AUTH-LOGIN-002.  
**Yêu cầu:** AUTH-LOGIN-01@1.

| Dữ liệu | Kết quả công khai kỳ vọng |
| --- | --- |
| user-basic và mật khẩu sai | 401, AUTH_FAILED |
| identity-unknown và một mật khẩu thử | 401, AUTH_FAILED |
| user-disabled và mật khẩu vốn hợp lệ | 401, AUTH_FAILED |

Với mỗi dòng:

- Bắt đầu từ trạng thái bộ đếm phù hợp.
- Xác nhận không tạo phiên hoàn chỉnh.
- Gọi protected-resource bằng mọi ngữ cảnh nhận được và kiểm tra không có quyền truy cập đã xác thực.
- Kiểm tra phản hồi không chứa thông tin về sự tồn tại hoặc trạng thái nội bộ.
- Kiểm tra audit theo yêu cầu, bằng quyền quan sát riêng của bộ thử.

Không áp dụng kỳ vọng 401 cho trường hợp đang hạn chế nếu hợp đồng đã quy định 429. Cần tách rõ điều kiện đầu.

### 5.3. Đánh giá khả năng phân biệt tài khoản

Cùng thông điệp chưa đủ nếu một đường trả thêm trường, redirect hoặc cookie đặc biệt làm lộ trạng thái.

Cần đối chiếu những yếu tố công khai có ý nghĩa theo mô hình đe dọa: mã, cấu trúc lỗi, header, điều hướng và hành vi khôi phục. Với thời gian phản hồi, phải đánh giá nhiều mẫu trong điều kiện có kiểm soát và dùng tiêu chí đã xác nhận.

Không yêu cầu hai request mạng có thời gian chính xác bằng nhau. Một mẫu chậm hơn chưa chứng minh có kênh phân biệt ổn định; một vài mẫu gần nhau cũng chưa chứng minh mọi chênh lệch có thể khai thác đã bị loại bỏ.

## 6. Test case MFA và các trạng thái trung gian

### 6.1. Chưa hoàn tất MFA không được thành phiên đầy đủ

**Mã:** TC-AUTH-MFA-001.  
**Yêu cầu:** AUTH-LOGIN-01@1 và AUTH-MFA-02@1.

1. Đăng nhập user-mfa với mật khẩu đúng.
2. Thu challenge hoặc ngữ cảnh trung gian.
3. Chưa gửi yếu tố thứ hai.
4. Gọi protected-resource bằng ngữ cảnh trung gian.
5. Thử các đường API thuộc phạm vi có thể hoàn tất hoặc sử dụng phiên.

**Kết quả kỳ vọng:** chỉ có trạng thái chờ MFA; không truy cập được tài nguyên yêu cầu xác thực hoàn chỉnh.

Không lấy mã 200 của bước đầu làm oracle thành công cuối cùng. Oracle là trạng thái danh tính và khả năng truy cập đã được đặc tả.

### 6.2. Mã đúng, sai, hết hạn và ràng buộc challenge

| Tình huống | Kết quả kỳ vọng theo AUTH-MFA-02 |
| --- | --- |
| Challenge đúng, phản hồi đúng, còn hiệu lực | Hoàn tất đúng giao dịch và tạo phiên theo chính sách |
| Phản hồi sai | Không hoàn tất, không tạo phiên đầy đủ |
| Đúng tài khoản nhưng sai giao dịch | Không hoàn tất giao dịch khác |
| Dùng challenge của tài khoản khác | Không chuyển danh tính hoặc hoàn tất sai tài khoản |
| Đúng mã tại mốc hết hạn 120 giây | Bị từ chối |
| Dùng lại sau khi đã thành công | Bị từ chối, không tạo phiên mới |
| Đúng mã sau 3 lần phản hồi sai | Challenge không được dùng tiếp |

Một challenge mới cần trạng thái thử riêng. Nếu liên tục dùng một challenge đã bị khóa để thử hết hạn, kết quả từ chối chưa chứng minh cơ chế hết hạn.

### 6.3. Dùng lại và gửi đồng thời

**Mã:** TC-AUTH-MFA-REPLAY-002.

- Tạo một challenge hợp lệ.
- Chuẩn bị các yêu cầu dùng cùng phản hồi hợp lệ theo tình huống.
- Thử gửi lại sau lần thành công.
- Thử các yêu cầu đồng thời ở những điểm tiếp nhận thuộc phạm vi.
- Quan sát số lần hoàn tất và số phiên mới được tạo.

Theo yêu cầu ví dụ, chỉ một lần hoàn tất được chấp nhận; những lần dùng lại không tạo thêm phiên. Cần kiểm tra dữ liệu phía máy chủ, không chỉ số phản hồi mà client tình cờ nhận được.

Nếu sản phẩm có cơ chế lặp lại idempotent cho request cùng định danh, phải đặc tả rõ hành vi đó để oracle phân biệt “trả lại kết quả cũ” với “thực hiện xác thực lần nữa”.

## 7. Test case phiên: tạo mới, hết hạn và đăng xuất

### 7.1. Chống dùng lại định danh trước xác thực

Giữ một định danh trước đăng nhập, hoàn tất đăng nhập rồi thử dùng lại nó trong client khác. Theo yêu cầu ví dụ, định danh cũ không trở thành phương tiện truy cập đã xác thực.

Kiểm tra này phải quan sát cả việc thay định danh và hiệu lực của bản cũ. Chỉ thấy cookie trình duyệt đổi chưa đủ nếu máy chủ vẫn chấp nhận định danh trước đó.

### 7.2. Hết hạn tuyệt đối

**Mã:** TC-AUTH-SESSION-EXP-001.  
**Yêu cầu:** AUTH-SESSION-03@1.

Gọi ts là thời điểm tạo phiên hoàn chỉnh:

| Thời điểm | Kỳ vọng nếu không có thay đổi trạng thái khác |
| --- | --- |
| Trước ts + 900 giây | Phiên còn hiệu lực theo yêu cầu về thời hạn |
| Tại ts + 900 giây | Máy chủ từ chối phiên hết hạn |
| Sau ts + 900 giây | Không tiếp tục xác thực bằng phiên đó |

Tạo hoạt động trong suốt thời gian chờ để xác nhận yêu cầu tuyệt đối không bị triển khai nhầm thành thời hạn trượt.

Các quy tắc khác như vô hiệu hóa tài khoản vẫn có thể làm phiên bị từ chối sớm hơn. Khi thử ranh giới hết hạn, giữ những trạng thái đó ổn định để cô lập nguyên nhân.

### 7.3. Đăng xuất phải có hiệu lực ở máy chủ

**Mã:** TC-AUTH-SESSION-LOGOUT-002.

1. Tạo hai phiên hợp lệ S1 và S2 của cùng tài khoản.
2. Giữ lại phương tiện thử của S1 trong client kiểm soát riêng.
3. Gửi lệnh đăng xuất S1 và ghi mốc tiếp nhận theo yêu cầu.
4. Thử lại S1 ở các điểm thực thi thuộc phạm vi.
5. Kiểm tra tại và sau giới hạn 30 giây.
6. Kiểm tra S2 theo chính sách đăng xuất một phiên.

**Kết quả kỳ vọng:**

- S1 ngừng được chấp nhận trong tối đa 30 giây.
- Xóa cookie trên giao diện không phải bằng chứng duy nhất.
- S2 không bị thu hồi ngoài phạm vi của lệnh đăng xuất một phiên trong ví dụ.

Mốc 30 giây là giới hạn tối đa; từ chối S1 ngay sau đăng xuất là hợp lệ. Không viết test bắt buộc S1 phải tiếp tục dùng được ở giây 29.

## 8. Test case giới hạn thử sai

### 8.1. Kiểm tra đúng ngưỡng và đúng khoảng hạn chế

**Mã:** TC-AUTH-RATE-001.  
**Yêu cầu:** AUTH-RATE-04@1.

**Điều kiện đầu:** user-basic hoạt động, bộ đếm sạch; các lần sai nằm trong cùng cửa sổ 600 giây.

| Thao tác | Kỳ vọng theo hợp đồng ví dụ |
| --- | --- |
| Lần sai 1 đến 4 | Thất bại thông thường; chưa ở trạng thái hạn chế |
| Lần sai 5 | Thất bại thông thường và kích hoạt hạn chế |
| Lần thử tiếp theo trước hết hạn | 429, kể cả khi mật khẩu đúng |
| Đúng tại mốc hết hạn chế | Có thể xử lý đăng nhập bình thường |
| Đăng nhập hoàn chỉnh thành công sau hạn | Xóa bộ đếm theo yêu cầu |

Ghi được thời điểm lần sai thứ năm, vì đó là mốc bắt đầu 300 giây. Không đo từ lúc mở trang hoặc từ lần sai đầu tiên.

Muốn kiểm tra cuối cửa sổ trượt, tạo các lần sai có mốc rõ ràng rồi tiến đến ranh giới 600 giây. Theo quy tắc của ví dụ, một lần sai đúng tại t − 600 không còn được tính trong cửa sổ đánh giá tại t.

### 8.2. Thay client và điểm tiếp nhận

Thực hiện các lần sai bằng nhiều client hoặc điểm tiếp nhận được kiểm soát nhưng cùng một định danh đã chuẩn hóa.

Mục tiêu là kiểm tra hiệu lực theo định danh và phạm vi chia sẻ trạng thái. Nếu mỗi nút chỉ biết bộ đếm riêng, tổng số lần thử có thể vượt quy tắc toàn hệ thống.

Không kết luận một cơ chế chống lạm dụng đầy đủ chỉ từ việc đổi IP không vượt qua bộ đếm tài khoản. Cần xem thêm các yêu cầu về giới hạn theo nguồn, tải tổng và nguy cơ làm người dùng hợp lệ bị từ chối.

### 8.3. Chuẩn hóa định danh

Chỉ tạo các biến thể mà chính sách ứng dụng xác nhận là cùng một danh tính. Nếu ứng dụng coi một số biến thể chữ hoa và chữ thường là tương đương, các biến thể đó phải có bộ đếm tương ứng theo yêu cầu.

Không tự áp dụng quy tắc chuẩn hóa của một dịch vụ khác cho mọi tên người dùng hoặc địa chỉ. Chính sách tra cứu và chính sách đếm phải nhất quán trong hệ thống đang thử.

Cũng cần kiểm tra hai định danh thực sự khác nhau không bị gộp ngoài ý muốn.

### 8.4. Cạnh tranh cập nhật bộ đếm

Gửi một nhóm yêu cầu có kiểm soát gần ngưỡng và quan sát thứ tự quyết định phía máy chủ.

Không giả định thứ tự gửi từ client là thứ tự hoàn tất ở máy chủ. Đánh giá số lần thất bại được xử lý và trạng thái hạn chế theo thứ tự thực tế, với fixture không bị các test khác dùng chung.

Bộ đếm cho mật khẩu không tự chứng minh OTP đã được giới hạn. Ngược lại, khóa một challenge sau 3 mã sai không chứng minh việc tạo nhiều challenge mới đã có cơ chế hạn chế đầy đủ. Những đường này cần yêu cầu và test case riêng khi thuộc mô hình đe dọa.

## 9. Test case khôi phục mật khẩu và tài khoản

Khôi phục là một đường thiết lập lại quyền kiểm soát danh tính. Một luồng đăng nhập chặt chẽ có thể bị vô hiệu hóa nếu luồng khôi phục cấp quyền với điều kiện yếu hơn yêu cầu đã xác nhận.

### 9.1. Gửi yêu cầu khôi phục

**Mã:** TC-AUTH-RECOVERY-001.  
**Yêu cầu:** AUTH-RECOVERY-05@1.

1. Gửi yêu cầu cho một tài khoản tồn tại.
2. Gửi yêu cầu tương ứng cho identity-unknown.
3. So sánh hợp đồng công khai.
4. Quan sát kênh gửi thử bằng quyền riêng của bộ thử.
5. Kiểm tra mật khẩu và phiên cũ trước khi hoàn tất khôi phục.

**Kết quả kỳ vọng:**

- Cùng nhận 202 và thông điệp chung.
- Tài khoản hợp lệ nhận phương tiện khôi phục ở kênh đã xác minh.
- Không có kênh gửi thực cho một danh tính không tồn tại.
- Chỉ gửi yêu cầu chưa đổi mật khẩu hoặc thu hồi phiên.
- Phản hồi công khai không chứa token hay tiết lộ địa chỉ nhận đầy đủ ngoài chính sách.

Nếu việc gửi email hoặc tin nhắn đi qua dịch vụ thử, cần kiểm tra đúng người nhận và liên kết tương ứng mà không gửi dữ liệu đến người dùng thật.

### 9.2. Token đúng tài khoản, đúng mục đích, còn hiệu lực

**Mã:** TC-AUTH-RECOVERY-002.

Tạo token khôi phục của user-basic và kiểm tra:

| Trường hợp | Kết quả cần quan sát |
| --- | --- |
| Token hợp lệ, đúng tài khoản, đúng mục đích | Cho phép đổi mật khẩu theo luồng đã đặc tả |
| Token bị sửa | Không đổi mật khẩu |
| Token của tài khoản khác | Không đổi mật khẩu của mục tiêu |
| Token dùng vào một chức năng khác | Không được chấp nhận như phương tiện xác thực cho mục đích đó |
| Token tại mốc tạo cộng 600 giây | Không còn hiệu lực |
| Token sau một lần hoàn tất thành công | Không dùng lại được |
| Hai lần hoàn tất đồng thời bằng cùng token | Không thực hiện hai lần thay đổi hợp lệ |

Khi thử hết hạn hoặc sai tài khoản, dùng token chưa bị tiêu thụ để không nhầm nguyên nhân từ chối.

Chính sách “phát token mới có làm token cũ mất hiệu lực không” cần được xác nhận riêng. Không tự thêm kỳ vọng này nếu yêu cầu chưa quy định.

### 9.3. Trạng thái sau khôi phục thành công

1. Tạo các phiên cũ trước khi đổi mật khẩu.
2. Hoàn tất đổi bằng token hợp lệ và mật khẩu mới đáp ứng chính sách.
3. Ghi mốc hoàn tất giao dịch.
4. Thử đăng nhập mới bằng mật khẩu cũ.
5. Thử đăng nhập bằng mật khẩu mới.
6. Tại và sau 30 giây, thử các phiên cũ ở các điểm thực thi.
7. Với user-mfa, xác nhận đăng nhập bằng mật khẩu mới vẫn phải hoàn tất MFA.

**Kết quả kỳ vọng:**

- Mật khẩu cũ không còn hợp lệ cho lần đăng nhập mới.
- Mật khẩu mới hoạt động trong đúng luồng.
- Các phiên cũ ngừng được chấp nhận trong giới hạn.
- Token khôi phục đã dùng không mở lại quy trình.
- Hoàn tất khôi phục không tự tạo đường bỏ qua MFA.

Cần giữ trạng thái giới hạn thử sai phù hợp để kết quả mật khẩu cũ không bị lẫn với trạng thái 429.

### 9.4. Khôi phục yếu tố thứ hai

Mất yếu tố thứ hai là luồng khác với quên mật khẩu. Cần đặc tả ai được khởi tạo, bằng chứng danh tính cần có, kênh thay thế, phê duyệt, thu hồi yếu tố cũ và thông báo liên quan.

Không mặc định nhân viên hỗ trợ có thể tắt MFA chỉ vì biết thông tin hồ sơ. Nếu một phương thức thay thế được cho phép, phải kiểm thử theo yêu cầu đảm bảo và thẩm quyền đã xác nhận cho chính phương thức đó.

## 10. Mở rộng sang token, đăng nhập liên kết và danh tính máy

Những phép thử dưới đây áp dụng khi cơ chế tương ứng có trong hệ thống. Cần chốt profile, nguồn tin cậy và hợp đồng cụ thể trước khi tạo oracle.

### 10.1. Token được xác minh như thế nào?

| Tình huống | Điều cần đối chiếu với yêu cầu |
| --- | --- |
| Token bị sửa nội dung hoặc chữ ký | Không được chấp nhận khi kiểm tra toàn vẹn thất bại |
| Token từ nguồn phát hành không được tin cậy | Không thiết lập danh tính chỉ vì định dạng có vẻ đúng |
| Token dành cho ứng dụng hoặc đối tượng nhận khác | Không được dùng ngoài phạm vi đã xác nhận |
| Token hết hạn hoặc chưa có hiệu lực | Tuân theo thời gian và chính sách sai lệch đồng hồ được phê duyệt |
| Token không đúng loại hoặc mục đích | Không thay thế cho một phương tiện xác thực khác |
| Khóa xác minh hoặc dịch vụ phụ thuộc không sẵn sàng | Thực hiện đúng hành vi lỗi, không bỏ bước xác minh để đăng nhập thành công |

Việc giải mã đọc được các trường trong token không chứng minh token đã được xác minh.

Không tự chọn thuật toán, nguồn khóa hoặc mức sai lệch thời gian trong test để phù hợp với kết quả thực tế. Những giá trị đó phải có căn cứ từ cấu hình và baseline được phê duyệt.

### 10.2. Luồng qua nhà cung cấp định danh

Cần xét:

- Kết quả trả về có gắn với giao dịch đăng nhập đã khởi tạo không.
- Kết quả của tài khoản hoặc giao dịch khác có bị dùng nhầm không.
- Các ràng buộc chống dùng lại và liên kết giao dịch được kiểm tra theo giao thức đang dùng không.
- Chuyển hướng và điểm nhận kết quả có đúng danh sách được phép không.
- Cách ánh xạ danh tính ngoài vào tài khoản nội bộ có đúng nguồn và định danh đã xác nhận không.
- Mất kết nối hoặc lỗi nhà cung cấp có tạo một đường đăng nhập thay thế ngoài chính sách không.

Không chỉ kiểm tra luồng thành công tại giao diện nhà cung cấp. Cần quan sát danh tính mà ứng dụng cuối cùng thiết lập và ngữ cảnh mà API chấp nhận.

Một trường email giống nhau từ hai nguồn không tự chứng minh đó là cùng danh tính. Nếu hệ thống hỗ trợ liên kết tài khoản, điều kiện và việc xác nhận liên kết cần có yêu cầu riêng.

### 10.3. Danh tính máy

Không áp dụng màn hình MFA của người dùng cho mọi dịch vụ. Kiểm thử theo cơ chế thực tế:

- Thông tin xác thực hợp lệ hoặc không hợp lệ.
- Sai nguồn, sai đối tượng nhận hoặc sai dịch vụ.
- Hết hạn, thu hồi, xoay vòng và khoảng chuyển tiếp được cho phép.
- Khả năng dùng lại khóa cũ ngoài thời gian quy định.
- Việc đưa bí mật vào URL, lỗi hoặc log.
- Hành vi khi kho bí mật hoặc thành phần xác minh gặp lỗi.

Mục tiêu vẫn là chỉ thiết lập đúng danh tính theo điều kiện đã xác nhận. Quyền mà danh tính máy được thực hiện cần bộ test phân quyền tương ứng.

## 11. Thời gian, đồng thời và lỗi phụ thuộc

### 11.1. Phân biệt hạn hiệu lực với giới hạn lan truyền

Hai quy tắc có oracle khác nhau:

| Quy tắc | Cách hiểu |
| --- | --- |
| Challenge hết hạn tại thời điểm tạo cộng 120 giây | Tại mốc đó phải từ chối challenge |
| Phiên bị thu hồi trong tối đa 30 giây sau đăng xuất | Có thể từ chối sớm; không được vượt hạn |
| Phiên có thời hạn tuyệt đối 900 giây | Hoạt động không tự gia hạn mốc cuối |
| Hạn chế thử sai có hiệu lực trong 300 giây | Đúng mốc hết hạn phải đánh giá theo quy tắc kết thúc khoảng |

Nếu dùng đồng hồ ảo, cần biết thành phần nào sử dụng nó. Đồng hồ của test runner không tự thay đổi đồng hồ của dịch vụ định danh, token đã ký hoặc kho cache.

Với phép thử tích hợp, ghi rõ mốc thời gian, sai lệch và điểm ra quyết định. Trường hợp phép đo không đủ phân giải để kết luận tại ranh giới cần được ghi là chưa đủ bằng chứng, thay vì tự nới ngưỡng.

### 11.2. Tiêu thụ một lần phải chịu được cạnh tranh

MFA và token khôi phục cần được thử đồng thời ở những điểm có thể dùng chung trạng thái.

Nếu hai tiến trình cùng đọc “chưa dùng”, sau đó cả hai hoàn tất, kiểm tra tuần tự có thể không phát hiện. Cần tổ chức lịch thử để các yêu cầu cạnh tranh tại bước tiêu thụ và quan sát giao dịch thực tế.

Không buộc triển khai phải dùng một kỹ thuật khóa cụ thể. Oracle là kết quả một lần sử dụng và tác động được yêu cầu.

### 11.3. Hành vi khi dịch vụ phụ thuộc lỗi

Mô phỏng có kiểm soát việc kho phiên, dịch vụ MFA hoặc dịch vụ danh tính không phản hồi.

Cần xác định:

- Bước nào bị chặn.
- Có tạo phiên hoàn chỉnh nhầm không.
- Có sử dụng trạng thái cache và trong giới hạn nào.
- Có thông báo và sự kiện vận hành phù hợp không.
- Khi phụ thuộc phục hồi, các challenge hoặc token cũ còn hiệu lực theo quy tắc nào.

Không coi mọi phản hồi lỗi là bằng chứng an toàn. Một endpoint có thể trả lỗi nhưng đã tạo phiên hoặc đổi mật khẩu trước đó; cần kiểm tra tác động phía máy chủ.

## 12. Tự động hóa theo trạng thái và hành vi quan sát được

Một bài thử nên có fixture riêng, điều kiện đầu rõ, oracle từ yêu cầu và dọn dẹp cả khi thất bại.

Mã giả sau minh họa MFA, không phải API của một thư viện cụ thể:

```text
fixture = create_isolated_auth_fixture()
try:
    user = fixture.active_user(mfa_required=true)
    flow = begin_login(user, fixture.valid_password(user))

    assert flow.state == WAITING_FOR_MFA
    assert protected_resource(flow.context).is_unauthenticated()

    otp = fixture.valid_otp(flow.challenge)
    result = complete_mfa(flow.transaction_context, otp)

    assert result.established_identity == user.id
    assert protected_resource(result.session).is_authenticated()
    assert new_session_count_for(flow.transaction_id) == 1

    replay = complete_mfa(flow.transaction_context, otp)

    assert replay.is_rejected()
    assert new_session_count_for(flow.transaction_id) == 1
    assert audit_has_expected_outcomes(flow.transaction_id)
    assert audit_contains_no_raw_secrets(flow.transaction_id)
finally:
    cleanup_auth_fixture(fixture)
```

Ngữ cảnh gửi lại phải phản ánh đúng giao dịch cần kiểm tra. Nếu dùng một tài khoản khác hoặc challenge đã sai ngay từ đầu, kết quả từ chối không chứng minh cơ chế chống replay của giao dịch hợp lệ.

### Kết hợp các mức kiểm thử

- Kiểm thử thành phần kiểm tra quy tắc thời gian, bộ đếm và chuyển trạng thái.
- Kiểm thử tích hợp kiểm tra kho phiên, cập nhật thu hồi, dịch vụ MFA và nhật ký.
- Kiểm thử toàn luồng kiểm tra đường truy cập thật của client và API.
- Kiểm tra cấu hình xác nhận những yêu cầu liên quan tới cơ chế trình duyệt, kênh truyền hoặc baseline triển khai.

Mock luôn trả “MFA thành công” không chứng minh việc ràng buộc challenge hoặc kiểm tra OTP thực đã đúng.

Không chạy lại tới khi thấy PASS rồi bỏ các lần thất bại. Nếu hạ tầng thử có lỗi, cần ghi nguyên nhân và giữ kết quả để phân biệt với lỗi sản phẩm.

## 13. Oracle và bằng chứng cho authentication test

Đối với xác thực, oracle cần kết hợp phản hồi và trạng thái danh tính.

| Quan sát | Vì sao cần |
| --- | --- |
| Phản hồi từng bước | Phân biệt thất bại, chờ MFA, hạn chế và hoàn tất |
| Phiên được tạo hoặc cập nhật | Phát hiện cấp phiên ngoài điều kiện |
| Gọi tài nguyên cần xác thực | Kiểm tra máy chủ thực sự chấp nhận ngữ cảnh nào |
| Hiệu lực phiên cũ | Kiểm tra rotation, logout và khôi phục |
| Trạng thái challenge hoặc token | Kiểm tra hết hạn, ràng buộc và tiêu thụ một lần |
| Sự kiện audit | Liên kết hành động và phát hiện việc ghi bí mật |
| Các điểm thực thi | Phát hiện một nút hoặc một đường truy cập chưa nhận trạng thái mới |

Mỗi kết quả nên gắn với:

- Mã test case và phiên bản yêu cầu.
- Bản dựng, cấu hình, môi trường và loại cơ chế xác thực.
- Fixture, trạng thái đầu và phạm vi các điểm thực thi.
- Mốc thời gian cùng cách đo.
- Định danh giao dịch, mã liên kết và kết quả thực tế.
- Bằng chứng đã che bí mật và giới hạn quan sát.

Kết quả có thể là PASS, FAIL, BLOCKED, INCONCLUSIVE hoặc NOT_RUN theo định nghĩa của nhóm.

Ví dụ, không truy cập được kho phiên của bộ thử có thể khiến phần kiểm tra số phiên chưa kết luận được. Nó không đồng nghĩa chắc chắn không có phiên tạo ra. Nếu API thực sự chấp nhận một phiên hết hạn trong điều kiện thử hợp lệ, đó là quan sát vi phạm yêu cầu.

Đăng nhập bị từ chối đúng nhưng log làm lộ OTP là hai kết luận khác nhau: luồng xác minh có thể đạt tình huống đã thử, còn yêu cầu bảo vệ nhật ký không đạt.

## 14. Những lỗi kiểm thử thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ thử mật khẩu đúng và sai | Bỏ sót trạng thái tài khoản và vòng đời | Thêm MFA, phiên, thu hồi và khôi phục |
| Coi bước mật khẩu thành công là đăng nhập hoàn tất | Không phát hiện bỏ qua MFA | Gọi tài nguyên cần xác thực bằng trạng thái trung gian |
| Chỉ kiểm tra cookie trình duyệt đã mất | Chưa biết máy chủ có thu hồi phiên không | Giữ phương tiện thử cũ và thử tại điểm thực thi |
| Dùng challenge đã khóa để kiểm tra hết hạn | Không cô lập nguyên nhân từ chối | Tạo fixture riêng cho từng điều kiện |
| Chỉ thử replay tuần tự | Bỏ sót tiêu thụ hai lần khi cạnh tranh | Thêm lịch đồng thời và quan sát trạng thái |
| Dùng bộ đếm đã bẩn | Sai mật khẩu và hạn chế bị lẫn | Thiết lập, cô lập và dọn bộ đếm |
| Mặc định mọi định danh chuẩn hóa giống nhau | Kiểm tra sai chính sách ứng dụng | Dùng quy tắc định danh đã xác nhận |
| Khẳng định phản hồi phải có thời gian tuyệt đối bằng nhau | Oracle không phù hợp thực tế đo | Định nghĩa mục tiêu và phương pháp đánh giá kênh phân biệt |
| Dùng token đọc được mà không xác minh | Nhầm định dạng với tính tin cậy | Thử nguồn, toàn vẹn, mục đích và hiệu lực |
| Chỉ kiểm thử đường đăng nhập chính | Bỏ sót reset, liên kết và kênh hỗ trợ | Lập bản đồ các đường thiết lập danh tính |
| In mật khẩu, OTP hoặc reset link để làm bằng chứng | Bộ thử làm lộ bí mật | Che dữ liệu và giới hạn hiện vật |
| Gắn kết quả của một nút cho toàn hệ thống | Kết luận vượt bằng chứng | Ghi phạm vi và thử các nhóm điểm thực thi |

## 15. Độ bao phủ và điều kiện hoàn tất

Một ma trận truy vết tối thiểu cho ví dụ có thể là:

| Yêu cầu | Nhóm test case phải liên kết |
| --- | --- |
| AUTH-LOGIN-01@1 | Hợp lệ, sai mật khẩu, không tồn tại, vô hiệu hóa, trạng thái chờ MFA |
| AUTH-MFA-02@1 | Đúng, sai, hết hạn, sai tài khoản hoặc giao dịch, quá số lần sai, replay và cạnh tranh |
| AUTH-SESSION-03@1 | Tạo mới định danh, phiên cũ, hết hạn tuyệt đối, đăng xuất và các điểm thực thi |
| AUTH-RATE-04@1 | Ngưỡng, cửa sổ trượt, hạn chế, hết hạn, chuẩn hóa và hiệu lực chia sẻ |
| AUTH-RECOVERY-05@1 | Phản hồi chung, kênh nhận, token, dùng một lần, mật khẩu mới và phiên cũ |
| AUTH-AUDIT-06@1 | Sự kiện ở các kết quả và kiểm tra bí mật không bị ghi |

Trước khi xem bộ kiểm thử sẵn sàng hoặc đánh giá một lượt chạy, kiểm tra:

- Mỗi oracle đến từ đúng phiên bản yêu cầu.
- Đã có cả luồng hợp lệ và trường hợp bị cấm.
- Đã phân biệt xác thực, trạng thái trung gian và phân quyền.
- Đã xét hết hạn, thu hồi, replay và cạnh tranh trong phạm vi.
- Đã kiểm tra khôi phục không tạo đường bỏ qua chính sách.
- Đã xác định các phụ thuộc, điểm thực thi và giới hạn quan sát.
- Phép đo thời gian có mốc rõ, không tự nới ngưỡng.
- Bằng chứng được bảo vệ và lỗi được liên kết đúng yêu cầu.
- Kết quả không được mở rộng sang cơ chế hoặc đường truy cập chưa thử.

Kiểm thử xác thực có giá trị khi chỉ ra hệ thống thiết lập danh tính đúng điều kiện, duy trì hiệu lực đúng vòng đời và kết thúc khả năng sử dụng khi yêu cầu đòi hỏi. Kết luận đó phải dựa trên trạng thái và hành vi thực ở các điểm kiểm soát, cùng bằng chứng có thể truy vết.
