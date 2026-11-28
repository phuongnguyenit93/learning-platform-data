# Session test: kiểm chứng vòng đời và thuộc tính bảo mật của phiên

## 1. Mục tiêu của kiểm thử phiên

Đăng nhập thành công chưa chứng minh phiên được quản lý an toàn. Một hệ thống có thể cấp đúng quyền lúc đăng nhập nhưng vẫn chấp nhận định danh phiên cũ sau logout, không thu hồi quyền đã thay đổi hoặc để refresh token kéo dài truy cập ngoài giới hạn cho phép.

Session test kiểm chứng cách hệ thống thiết lập, sử dụng, thay đổi và kết thúc ngữ cảnh truy cập của người dùng hoặc thành phần. Kết quả phải trả lời: phiên đại diện cho ai, được làm gì, có hiệu lực tới khi nào và điều kiện nào khiến nó không còn được chấp nhận.

Trong chương Kiểm thử yêu cầu của module Security Requirements, trọng tâm là chuyển yêu cầu về phiên thành ca kiểm thử có tiền điều kiện, thao tác, kết quả mong đợi và bằng chứng. Bài học liên kết xác thực, phân quyền, dữ liệu, logging và phục hồi qua vòng đời phiên.

Sau bài học, người học có thể:

- Phân biệt phiên ứng dụng, phiên tại IdP, access token và refresh token.
- Xây dựng hợp đồng thời gian cho idle timeout, absolute timeout và thu hồi.
- Thiết kế ca kiểm tra fixation, rotation, logout, phiên đồng thời và refresh.
- Phân biệt trạng thái trên trình duyệt với quyết định cấp quyền từ phía server.
- Lưu bằng chứng đủ để truy vết mà không làm lộ thông tin phiên.

Các mã yêu cầu, ngưỡng và API trong bài là ví dụ cho hệ thống giả định. Chúng không phải giá trị mặc định của OWASP hoặc điều kiện đủ để kết luận tuân thủ một tiêu chuẩn.

## 2. Hiểu mô hình phiên trước khi viết test

### 2.1. Các đối tượng khác nhau trong chuỗi truy cập

| Đối tượng | Vai trò | Điều cần kiểm chứng |
| --- | --- | --- |
| Phiên ứng dụng | Ngữ cảnh đăng nhập và truy cập tại ứng dụng | Danh tính, quyền, thời hạn và cách vô hiệu hóa |
| Cookie mang định danh phiên | Cách trình duyệt giữ và gửi thông tin phiên | Thuộc tính, phạm vi gửi, cập nhật và xóa |
| Access token | Thông tin cho phép gọi tài nguyên theo cơ chế được dùng | Nguồn phát hành, đối tượng sử dụng, phạm vi, hiệu lực và thu hồi theo hợp đồng |
| Refresh token | Cơ chế xin thông tin truy cập mới | Ràng buộc client, thời hạn, rotation hoặc cơ chế bảo vệ đã chọn |
| Phiên tại IdP | Trạng thái xác thực dùng cho đăng nhập tập trung | Tác động của logout, tái xác thực và tuổi xác thực |
| Kết nối dài | WebSocket, luồng tải hoặc kênh đã thiết lập | Điều kiện tiếp tục dùng sau thay đổi hoặc chấm dứt phiên |

JWT là một định dạng token, không tự quyết định hệ thống có trạng thái phía server hay không. Một ứng dụng dùng JWT vẫn có thể lưu trạng thái phiên, dùng kiểm tra thu hồi hoặc tham chiếu tới phiên logic.

Cookie có thể chứa định danh phiên hoặc một token. Không suy ra mô hình thu hồi chỉ từ tên cookie hoặc việc token có ba phần ngăn bằng dấu chấm.

### 2.2. Lập bản đồ điểm thực thi

Trước khi chạy ca, xác định:

- Thành phần nào cấp phiên và thành phần nào quyết định truy cập.
- Dữ liệu phiên, quyền và trạng thái thu hồi được lưu hoặc đồng bộ ở đâu.
- Gateway, ứng dụng và worker có cùng cách kiểm tra hay không.
- Đường API, tải file, giao diện và kết nối dài nào thuộc phạm vi.
- Logout chỉ áp dụng cho một ứng dụng, một thiết bị hay toàn bộ phiên.
- Phụ thuộc nào có thể gây độ trễ hoặc quyết định không nhất quán.

OWASP WSTG tổ chức kiểm thử quản lý phiên thành các chủ đề như cấu trúc phiên, cookie, fixation, logout và timeout. Có thể dùng danh mục đó để rà phạm vi, rồi chọn ca theo kiến trúc thực tế. [Nguồn: OWASP WSTG v4.2 — Session Management Testing](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/06-Session_Management_Testing/).

## 3. Đặc tả hợp đồng phiên có thể kiểm chứng

Nếu yêu cầu chỉ nói “phiên phải hết hạn an toàn”, người kiểm thử chưa biết phải đợi bao lâu, đo từ đâu hay mong đợi điều gì. Cần xác định ít nhất các mục sau.

| Thuộc tính | Câu hỏi cần chốt |
| --- | --- |
| Chủ thể và quyền | Phiên gắn với danh tính nào, quyền lấy từ đâu và thay đổi có hiệu lực khi nào? |
| Tạo và nâng mức phiên | Khi đăng nhập hoặc tái xác thực, định danh và ngữ cảnh được thay đổi thế nào? |
| Idle timeout | Hoạt động nào làm mới mốc idle; bao lâu không hoạt động thì hết hạn? |
| Absolute timeout | Thời hạn tính từ mốc nào; refresh hoặc rotation có ảnh hưởng không? |
| Logout | Phạm vi chấm dứt, mốc xác nhận và điều kiện với thông tin phiên cũ |
| Thu hồi | Sự kiện bắt đầu, đường truy cập, thời hạn tối đa và bằng chứng |
| Phiên đồng thời | Có cho nhiều thiết bị, nhiều trình duyệt hoặc nhiều phiên không? |
| Refresh | Cơ chế cấp mới, phát hiện dùng lại và kết thúc quyền refresh |
| Mất phụ thuộc | Khi không xác định được trạng thái phiên, đường nhạy cảm xử lý thế nào? |
| Audit | Sự kiện cần có, trường bắt buộc, độ trễ và thông tin cấm ghi |

### Chính sách minh họa cho cổng quản trị

Trong các ví dụ sau, giả sử tổ chức đã phê duyệt:

- Idle timeout là 15 phút, tính từ yêu cầu được server chấp nhận là hoạt động theo định nghĩa của sản phẩm.
- Absolute timeout là 8 giờ từ khi tạo phiên ứng dụng ban đầu sau xác thực; đổi định danh và refresh trong cùng phiên logic không đặt lại mốc này.
- Thao tác đặc biệt cần ngữ cảnh tái xác thực đủ mới theo chính sách, ví dụ trong 5 phút.
- Sau khi server xác nhận logout, các yêu cầu mới dùng định danh phiên đã kết thúc không được cấp dữ liệu bảo vệ.
- Khi tài khoản bị vô hiệu hóa tại nguồn có thẩm quyền, yêu cầu mới trên các đường thuộc phạm vi phải bị từ chối trong tối đa 60 giây.
- Phạm vi logout một phiên và logout mọi phiên được đặc tả riêng.

Các điều kiện trên là hợp đồng của ví dụ. Nếu kiến trúc không thể đạt một điều kiện, cần điều chỉnh kiến trúc hoặc trình thay đổi yêu cầu theo thẩm quyền; không tự nới tiêu chí sau khi test FAIL.

## 4. Chuẩn bị fixture và bằng chứng

Bộ fixture tối thiểu nên có hai người dùng với dữ liệu phân biệt được, hai client độc lập và các tài nguyên tổng hợp. Với kiểm thử nhiều thiết bị, tạo thêm phiên thứ hai cho cùng một người dùng.

Mỗi ca cần kiểm soát:

1. Tài khoản, quyền, trạng thái và dữ liệu ban đầu.
2. Cookie jar hoặc nơi giữ token riêng cho từng client.
3. Mốc thời gian, phiên bản chính sách và bản triển khai.
4. Cách quan sát quyết định server và audit.
5. Cách dọn dữ liệu, kết nối và phiên do lần chạy tạo.

Không dùng nhầm phiên admin từ bước thiết lập cho hành động cần kiểm tra. Không để client tự đăng nhập lại hoặc refresh khi mục tiêu ca là thử định danh đã hết hiệu lực.

Thông tin phiên cũ có thể cần giữ tạm để kiểm chứng dùng lại, nhưng không đưa giá trị đầy đủ vào báo cáo. Chỉ dùng tài khoản và dữ liệu thử trong môi trường thuộc phạm vi kiểm chứng; lưu bằng chứng với quyền truy cập phù hợp.

## 5. Kiểm tra tạo phiên và ràng buộc danh tính

Ca cơ bản cần chứng minh người dùng hoàn tất luồng xác thực được phê duyệt, nhận phiên của đúng danh tính và truy cập được tài nguyên đúng quyền.

Các assertion cần có:

- Chủ thể thực tế khớp tài khoản thử, không phải tài khoản thiết lập dữ liệu.
- Phiên không mang thêm vai trò hoặc phạm vi ngoài quyền được cấp.
- Trạng thái chưa xác thực không tự trở thành đã xác thực trước khi đủ điều kiện.
- Cookie hoặc token được trả qua các kênh mà yêu cầu cho phép.
- Không có thông tin bí mật xuất hiện trong URL, nội dung lỗi hoặc bằng chứng được lưu ngoài chính sách.

Với định danh opaque, có thể kiểm tra việc không chứa dữ liệu cá nhân hoặc cấu trúc dễ suy ra từ fixture. Tuy nhiên, vài mẫu khác nhau hoặc một biểu đồ phân bố đẹp không chứng minh nguồn ngẫu nhiên đủ mạnh. Kết luận về cơ chế sinh định danh còn cần xem xét thiết kế và cấu hình phù hợp.

Với token có nội dung đọc được, phân biệt tính bí mật với tính toàn vẹn. Đọc được payload của một token ký số không tự là lỗi; đưa bí mật vào payload có thể là lỗi theo yêu cầu dữ liệu. Việc đọc payload cũng không thay thế kiểm chứng tính hợp lệ của token.

## 6. Kiểm tra cookie và cách browser gửi thông tin phiên

Giả sử chính sách dùng cookie phiên có cấu hình minh họa:

~~~http
Set-Cookie: sid=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cấu hình thực tế cần phù hợp với domain, luồng đăng nhập và mô hình client. Không sao chép nguyên mẫu này cho mọi ứng dụng.

| Thuộc tính | Cách kiểm chứng |
| --- | --- |
| Secure | Kiểm tra header thực tế và hành vi browser trên kênh thuộc phạm vi |
| HttpOnly | Xác nhận script của trang không đọc được cookie cần bảo vệ |
| SameSite | Kiểm tra các luồng cùng site và khác site theo chính sách đã chọn |
| Domain và Path | Quan sát cookie được gửi tới đúng phạm vi cần thiết, không mở rộng ngoài thiết kế |
| Thời hạn cookie | Đối chiếu với yêu cầu lưu trên client, tách biệt với hiệu lực phía server |
| Cookie cùng tên | Kiểm tra cập nhật và xóa đúng cookie khi có các phạm vi khác nhau |

OWASP WSTG cung cấp hướng dẫn kiểm tra các thuộc tính cookie liên quan tới bảo vệ phiên. Header cần được quan sát trên phản hồi triển khai thực tế, không chỉ trong file cấu hình nguồn. [Nguồn: OWASP WSTG v4.2 — Testing for Cookies Attributes](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/06-Session_Management_Testing/02-Testing_for_Cookies_Attributes/).

HttpOnly không ngăn browser tự gửi cookie khi thực hiện request. SameSite cũng không thay thế mọi điều kiện chống CSRF mà ứng dụng cần. Path điều khiển phạm vi gửi cookie, không tự tạo một ranh giới phân quyền phía server.

Ca thuộc tính browser nên dùng browser có hành vi đại diện cho client được hỗ trợ. Một HTTP client tự gắn header Cookie có thể gửi dữ liệu mà browser sẽ không gửi, nên không dùng riêng nó để kết luận về SameSite hoặc phạm vi gửi cookie.

## 7. Kiểm tra fixation và đổi định danh phiên

### 7.1. Đăng nhập không nâng quyền cho định danh cũ

Session fixation xảy ra khi một định danh đã biết hoặc đã được thiết lập trước xác thực tiếp tục trở thành định danh có quyền của người đăng nhập.

Ca minh họa:

1. Client A nhận định danh trước xác thực S0 trong fixture được kiểm soát.
2. Client B bắt đầu với trạng thái trước xác thực tương ứng và hoàn tất đăng nhập hợp lệ.
3. Quan sát định danh sau xác thực S1 và ngữ cảnh quyền của B.
4. B dùng S1 truy cập được tài nguyên hợp lệ.
5. A dùng riêng S0 gọi tài nguyên bảo vệ bằng request mới, không tự đăng nhập hoặc refresh.
6. Xác nhận S0 không đại diện cho phiên đã xác thực của B và không nhận quyền của B.

S0 có thể tiếp tục là phiên ẩn danh nếu hợp đồng cho phép; điều cần ngăn là nó được dùng như phiên có quyền sau đăng nhập. Chỉ thấy chuỗi S1 khác S0 chưa đủ: phải kiểm tra hành vi với cả định danh mới và cũ.

### 7.2. Nâng mức phiên và tái xác thực

Khi một phiên được nâng mức xác thực hoặc quyền, cần kiểm chứng:

- Điều kiện tái xác thực đã thực sự hoàn tất.
- Phiên mới mang đúng chủ thể và mức xác thực.
- Định danh hoặc ngữ cảnh cũ không tự có quyền mới ngoài chính sách.
- Quyền mới chỉ tồn tại trong thời gian và phạm vi được cấp.
- Audit phản ánh thay đổi mà không ghi giá trị phiên đầy đủ.

Nếu hợp đồng yêu cầu vô hiệu hóa hoàn toàn định danh cũ, kiểm tra đúng điều đó. Nếu chỉ giữ quyền cũ hoặc có khoảng chuyển tiếp được phê duyệt, phải đặc tả rõ giới hạn, thời gian và hành vi tại ranh giới.

Đổi chuỗi token không chứng minh token cũ đã mất hiệu lực. Đặc biệt với access token tự chứa, cần biết resource server dựa vào cơ chế nào để thực thi việc thu hồi hoặc giới hạn hiệu lực.

### 7.3. Rotation trong lúc sử dụng

Nếu có renewal hoặc rotation định kỳ, cần kiểm tra phiên mới hoạt động, phiên cũ hết hiệu lực theo hợp đồng và các request đồng thời không làm phiên cũ sống lại.

Thử cả hai hướng: request với định danh mới rồi dùng lại định danh cũ; và request cũ đến trễ sau khi rotation hoàn tất. Theo dõi danh tính và quyền, không chỉ số lần đổi cookie.

## 8. Kiểm tra idle timeout và absolute timeout

OWASP phân biệt idle timeout với absolute timeout, đồng thời nhấn mạnh việc thực thi thời hạn phiên ở phía server. Renewal định danh là một cơ chế khác, không nên bị nhầm với việc kéo dài tuổi phiên logic. [Nguồn: OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

### 8.1. Idle timeout

Với chính sách minh họa 15 phút:

- t_last là thời điểm server ghi nhận hoạt động cuối cùng làm mới idle.
- t_idle = t_last + 900 giây.
- Khi server đánh giá phiên tại hoặc sau t_idle, phiên không được cấp quyền theo hợp đồng ví dụ.

Ca cần:

1. Tạo phiên mới, thực hiện một hoạt động hợp lệ và xác định t_last.
2. Ngừng các hoạt động được định nghĩa là làm mới idle.
3. Tới thời điểm hết hạn, dùng thông tin phiên đã giữ để gọi tài nguyên bảo vệ.
4. Xác nhận server từ chối, dù client vẫn giữ cookie hoặc token.
5. Đối chiếu nguyên nhân hết hạn bằng bằng chứng phù hợp.

Background polling, refresh, tải tài nguyên hoặc WebSocket có thể ảnh hưởng t_last tùy thiết kế. Cần tắt hoặc kiểm soát chúng trong fixture; đồng thời có ca riêng xác nhận chính sách về những hoạt động này.

Không gọi một API có tác dụng làm mới idle để “xem phiên còn sống không” rồi vẫn tính deadline từ mốc cũ. Muốn kiểm tra trước, tại và sau ranh giới, có thể dùng các phiên độc lập hoặc đồng hồ kiểm thử được hệ thống hỗ trợ.

### 8.2. Absolute timeout

Với chính sách 8 giờ:

- t_start là mốc tạo phiên logic ban đầu đã thỏa thuận.
- t_absolute = t_start + 28.800 giây.
- Hoạt động hợp lệ tiếp diễn không được vượt giới hạn này trong cùng phiên logic.

Để chứng minh absolute timeout, duy trì hoạt động hợp lệ với khoảng cách nhỏ hơn idle timeout, cập nhật định danh mới nếu có rotation, rồi kiểm tra tại giới hạn tuyệt đối. Nếu để phiên chết do idle trước đó, lần từ chối sau 8 giờ không chứng minh absolute timeout.

Cần xác nhận refresh và rotation giữ đúng mốc t_start theo hợp đồng. Tái xác thực thực sự có thể tạo một ngữ cảnh mới theo chính sách, nhưng chỉ cấp token mới hoặc quay lại từ một phiên SSO cũ không tự chứng minh người dùng vừa tái xác thực.

### 8.3. Thời gian và sai số

Phép đo cần ghi rõ mốc server sử dụng, độ phân giải, độ trễ và lệch đồng hồ. Khi sai số không cho phép phân biệt hai phía của ranh giới, chưa đủ bằng chứng kết luận đạt.

Có thể kiểm tra logic bằng đồng hồ được tiêm vào trong môi trường test, sau đó có mức kiểm chứng phù hợp cho tích hợp thực tế. Không chỉ sửa giờ trên browser rồi kết luận server đã thực thi timeout.

## 9. Kiểm tra logout và dùng lại thông tin phiên cũ

### 9.1. Chấm dứt phiên tại server

Với hợp đồng logout của ví dụ:

1. Đăng nhập và xác nhận S1 truy cập được tài nguyên bảo vệ.
2. Giữ tạm S1 trong bộ nhớ kiểm thử.
3. Gọi logout bằng client hợp lệ và nhận xác nhận từ server.
4. Từ client không tự đăng nhập hoặc refresh, gửi request mới dùng S1 tới API bảo vệ.
5. Kiểm tra các đường nhạy cảm khác thuộc phạm vi.
6. Xác nhận S1 không được cấp dữ liệu hoặc tạo tác dụng phụ nghiệp vụ trái phép.

Client nhận cookie rỗng hoặc giao diện chuyển về trang login chưa đủ chứng minh S1 mất hiệu lực. OWASP WSTG mô tả việc kiểm tra lại bằng giá trị phiên cũ và kiểm tra các trang bảo vệ sau logout. [Nguồn: OWASP WSTG v4.2 — Logout Functionality](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/06-Session_Management_Testing/06-Testing_for_Logout_Functionality/).

Không tự theo redirect qua SSO rồi đánh giá phiên cuối cùng mà bỏ qua quá trình cấp phiên mới. Một lần đăng nhập lại do phiên IdP còn hiệu lực khác với việc S1 cũ tiếp tục được chấp nhận.

### 9.2. Tách các loại thông tin truy cập

Nếu có access token và refresh token, cần tiêu chí riêng:

- Refresh token có còn xin được thông tin truy cập mới sau logout không?
- Access token cũ còn được resource server chấp nhận trong khoảng nào?
- Phiên cookie của ứng dụng đã kết thúc có được tái sử dụng không?
- Quyền tải file hoặc kết nối dài đã mở được xử lý theo điều kiện nào?

Một access token tự chứa có thể tiếp tục hợp lệ theo cơ chế triển khai nếu resource server không kiểm tra trạng thái thu hồi. Khi yêu cầu đòi vô hiệu ngay sau logout, đây là khoảng trống cần xử lý, không phải lý do tự đổi test thành PASS.

Nếu hợp đồng cho phép một khoảng hiệu lực còn lại đã được phê duyệt, phải đo đúng giới hạn đó và ghi rõ token, đường truy cập, phạm vi dữ liệu. “Token sẽ hết hạn sớm” chưa là tiêu chí đủ rõ.

### 9.3. Dữ liệu còn trên client

Sau logout, kiểm tra theo yêu cầu dữ liệu của sản phẩm:

- Back, Forward, reload và mở lại trang có hiển thị dữ liệu nhạy cảm không?
- Service worker hoặc chế độ offline có trả dữ liệu từ phiên trước không?
- Cache, bộ nhớ ứng dụng hoặc nơi lưu cục bộ có giữ thông tin ngoài thời hạn cho phép không?
- Đăng nhập bằng người B trên cùng client có thấy dữ liệu A không?

Header như Cache-Control cần được kiểm tra cùng hành vi thực tế của client được hỗ trợ. Nó không tự chứng minh mọi bản sao trên client đã được xử lý theo chính sách.

Dữ liệu hiển thị từ cache và một response mới do server cấp là hai nguồn bằng chứng khác nhau. Cần phân biệt để xác định lỗi ở lưu dữ liệu phía client hay ở chấm dứt phiên phía server.

## 10. Kiểm tra thu hồi, thay đổi quyền và độ mới xác thực

### 10.1. Vô hiệu hóa tài khoản

Với giới hạn 60 giây trong ví dụ:

- t_revoke là lúc nguồn có thẩm quyền xác nhận tài khoản đã bị vô hiệu hóa.
- Ghi nhận phiên và token đang hoạt động trước t_revoke.
- Gửi yêu cầu mới trên các đường thuộc phạm vi tại những mốc cần kiểm tra.
- Tại hoặc sau t_revoke + 60 giây, yêu cầu mới không được cấp quyền.
- Đối chiếu API, gateway và các thành phần có thể giữ cache quyết định.

Cần biết mốc bắt đầu thực sự. Thời điểm người vận hành bấm nút trên UI và thời điểm thay đổi có hiệu lực ở nguồn danh tính có thể khác nhau.

Nếu access token có thể được chấp nhận thêm 5 phút nhưng yêu cầu chỉ cho 60 giây, kết quả không đạt trên đường đó. Không lấy bằng chứng rằng tài khoản đã bị khóa ở IdP thay cho bằng chứng resource server đã từ chối truy cập.

### 10.2. Hạ quyền hoặc đổi phạm vi tổ chức

Một phiên đã xác thực không được mặc nhiên giữ quyền cũ vô hạn. Ca nên:

1. Tạo phiên có quyền trên tài nguyên tổng hợp.
2. Xác nhận thao tác hợp lệ trước thay đổi.
3. Thu hồi quyền hoặc đổi phạm vi theo quy trình được hỗ trợ.
4. Kiểm tra thao tác mới sau thời hạn đồng bộ đã quy định.
5. Kiểm tra quyền còn lại vẫn hoạt động đúng nếu chính sách cho phép.

Với chuyển tổ chức trong cùng giao diện, xác nhận dữ liệu, cache và quyết định quyền không dùng nhầm ngữ cảnh trước đó. Thay trường hiển thị tên tổ chức chưa chứng minh server đã chuyển phạm vi truy cập.

### 10.3. Tái xác thực cho thao tác đặc biệt

Nếu thao tác nhạy cảm cần tái xác thực trong 5 phút, cần định nghĩa mốc xác thực dùng để tính tuổi. Không dùng thời điểm refresh token làm bằng chứng rằng người dùng vừa xác thực lại.

Kiểm tra cả trường hợp đủ mới, hết thời gian và sau khi người dùng hoàn tất lại cơ chế được yêu cầu. Sự kiện cấp token mới và sự kiện tái xác thực phải được phân biệt trong bằng chứng.

## 11. Kiểm tra refresh token và phát hiện dùng lại

Phần này áp dụng khi kiến trúc có OAuth hoặc cơ chế refresh tương ứng. Không gán refresh token cho một ứng dụng chỉ dùng session ID truyền thống.

RFC 9700 mô tả cơ chế ràng buộc token với bên gửi hoặc rotation để phát hiện việc dùng lại refresh token trong những ngữ cảnh client liên quan. Ca kiểm thử phải theo cơ chế đã chọn và điều kiện của giao thức. [Nguồn: RFC 9700, mục 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).

Giả sử hợp đồng dùng rotation với các token ký hiệu R0, R1:

1. Dùng R0 hợp lệ để nhận access token mới và R1.
2. Xác nhận client hợp lệ dùng được kết quả mới theo quyền đã cấp.
3. Dùng lại R0 bằng client kiểm thử độc lập theo kịch bản được định nghĩa.
4. Xác nhận hành vi phát hiện dùng lại và xử lý chuỗi refresh đúng hợp đồng.
5. Kiểm tra R1 và các thông tin truy cập liên quan có trạng thái đúng sau sự kiện.
6. Đối chiếu audit hoặc tín hiệu điều tra mà chính sách yêu cầu.

Không dừng ở việc R0 trả lỗi: hệ thống có thể chưa thực hiện biện pháp xử lý phần refresh còn đang hoạt động mà hợp đồng quy định.

Thử thêm refresh sau logout, sau vô hiệu hóa tài khoản và sau hết hạn tuyệt đối theo phạm vi. Token mới không được làm sống lại một phiên logic đã kết thúc.

Hai request refresh đồng thời có thể xuất hiện do nhiều tab. Cần đặc tả trường hợp sử dụng hợp lệ, cách phối hợp client và cách server xử lý cạnh tranh. Không tự cho phép một khoảng dùng lại không giới hạn để làm test ổn định.

## 12. Phiên đồng thời, SSO và đường truy cập đặc biệt

### Nhiều thiết bị và nhiều tab

Tạo hai phiên S-A1 và S-A2 cho cùng tài khoản, đồng thời có phiên của người B. Kiểm tra riêng:

- Logout phiên hiện tại chấm dứt đúng phạm vi.
- Logout mọi phiên chấm dứt các phiên mà hợp đồng liệt kê.
- Hoạt động trên một thiết bị có làm mới timeout của thiết bị khác hay không.
- Rotation hoặc refresh ở một tab có gây khôi phục quyền cho định danh cũ không.
- Dữ liệu và phiên của B không bị lẫn với A.

Không mặc định “chỉ một phiên được phép” hoặc “logout phải kết thúc mọi thiết bị”. Cả hai đều cần chính sách cụ thể.

### SSO và các lớp phiên

Với đăng nhập tập trung, lập danh sách phiên ứng dụng, phiên IdP và các ứng dụng khác thuộc phạm vi logout. Kiểm tra kết thúc ở từng lớp theo hợp đồng.

Nếu logout ứng dụng chỉ chấm dứt phiên cục bộ, việc IdP cho phép đăng nhập lại không tự là lỗi. Nếu yêu cầu đòi kết thúc SSO hoặc buộc xác thực lại, phải kiểm chứng hành vi đó thay vì chỉ xem ứng dụng đã xóa cookie.

### Kết nối dài và tác vụ nền

Cần tiêu chí riêng cho:

- WebSocket đã xác thực trước khi logout hoặc thu hồi.
- File đang truyền và yêu cầu tải mới.
- Tác vụ nền đã xếp hàng nhưng chưa chạy.
- URL tải không dựa vào cookie phiên hiện tại.

Không suy ra các đối tượng này tự dừng chỉ vì request HTTP mới bị từ chối. Cũng không hứa thu hồi những byte đã được client nhận; cần xác định hành vi khả thi và yêu cầu tương ứng.

## 13. Liên kết với CSRF, audit và phục hồi

### Request dùng cookie và CSRF

Nếu browser tự gắn cookie, cần kiểm tra các thao tác thay đổi trạng thái theo cơ chế chống CSRF của sản phẩm. Dùng browser để kiểm tra ngữ cảnh gửi request khi kết luận phụ thuộc hành vi browser.

Một thao tác hợp lệ phải vẫn hoạt động khi có đủ điều kiện. Request thiếu điều kiện chống CSRF hoặc đến từ ngữ cảnh bị cấm phải được xử lý đúng hợp đồng, không gây thay đổi nghiệp vụ.

Phần này kiểm tra giao điểm với phiên; nó không thay thế một bộ kiểm thử CSRF đầy đủ.

### Audit vòng đời phiên

Các sự kiện cần xem xét gồm tạo phiên, nâng mức xác thực, đổi định danh, refresh, timeout, logout và thu hồi. Với mỗi sự kiện, chỉ rõ trường bắt buộc, độ trễ và cách tương quan.

Bằng chứng nên đủ để đối chiếu chủ thể, hành động, kết quả và thời gian, nhưng không chứa cookie, access token hoặc refresh token đầy đủ. Dùng mã tham chiếu không có khả năng truy cập thay cho bí mật phiên.

Không coi một dòng log “logout success” là bằng chứng duy nhất. Cần kết hợp với request dùng lại phiên cũ và kết quả thực thi ở tài nguyên bảo vệ.

### Khởi động lại, failover và phục hồi

Nếu trạng thái phiên hoặc thu hồi được lưu phân tán, kiểm tra theo kiến trúc:

- Sau khi chuyển node, phiên còn hợp lệ có hoạt động đúng không?
- Phiên đã logout hoặc bị thu hồi có sống lại khi một node dùng dữ liệu cũ không?
- Khôi phục snapshot có làm mất các quyết định thu hồi mới hơn không?
- Khi store phiên không truy cập được, đường nhạy cảm xử lý đúng chế độ đã quy định không?
- Sau phục hồi, audit và ngữ cảnh danh tính có còn đối chiếu được không?

Không mặc định mất store phải cho phép truy cập, cũng không mặc định phải ngừng mọi chức năng. Yêu cầu cần xác định phản ứng phù hợp theo rủi ro. Nếu không xác định được quyền, không được tự diễn giải lỗi phụ thuộc thành một quyết định cho phép.

## 14. Pseudocode kiểm chứng logout ở phía server

Đoạn sau minh họa thiết kế ca ST-LOGOUT-01, không phải bộ test có thể chạy trực tiếp. Trong ví dụ, API bảo vệ trả 401 cho phiên không hợp lệ và logout thành công trả 204.

~~~text
fixture = provisionUsersAndProtectedResources()
runId = newTestRunId()

try:
    clientA = newClientWithIndependentSession()
    clientB = newClientWithIndependentSession()

    clientA.signInThroughApprovedFlow(fixture.userA)
    clientB.signInThroughApprovedFlow(fixture.userB)

    oldCredential = captureSessionCredentialInMemory(clientA)

    before = clientA.readProtectedResource(fixture.resourceA)
    assert before.status == 200
    assert before.body matches fixture.expectedA

    logout = clientA.logoutWithRequiredRequestProtections(runId)
    assert logout.status == 204

    replayClient = newClient(
        automaticLogin = false,
        automaticRefresh = false,
        followAuthenticationRedirects = false
    )

    after = replayClient.readProtectedResource(
        resource = fixture.resourceA,
        credential = oldCredential,
        correlationId = runId
    )

    assert after.status == 401
    assert after.body contains no protectedResourceData
    assert no prohibitedBusinessSideEffectWasCreated(runId)

    control = clientB.readProtectedResource(fixture.resourceB)
    assert control.status == 200
    assert control.body matches fixture.expectedB

    event = awaitAuditWithinAgreedDeadline(runId)
    assert event describes terminationOfExpectedSession
    assert event.actorId == fixture.userA.id

    saveEvidenceWithCredentialsRemoved(runId)
finally:
    closeClientsAndClearInMemoryCredentials()
    cleanupOnlyResourcesOwnedByThisRun(fixture)
~~~

Client B là đối chứng giúp nhận ra tình huống toàn bộ dịch vụ đang lỗi hoặc mọi người đều bị từ chối. Đối chứng này không thay thế các ca kiểm tra khác, nhưng làm kết luận của ca chính rõ hơn.

Không cho replayClient nhận cookie mới sau logout hoặc tự hoàn tất lại SSO. Nếu nó dùng một phiên mới, ca không còn kiểm tra hiệu lực của oldCredential.

Với hệ thống cho phép độ trễ thu hồi, thay assertion thời gian bằng deadline đúng hợp đồng và giữ bằng chứng các mốc. Không thêm khoảng chờ tùy ý rồi chỉ báo kết quả cuối cùng.

## 15. Ma trận ca kiểm thử tối thiểu theo rủi ro

| Mã minh họa | Mục tiêu | Bằng chứng trọng tâm |
| --- | --- | --- |
| ST-CREATE-01 | Phiên mới đại diện đúng danh tính và quyền | Luồng xác thực, tài nguyên hợp lệ, ngữ cảnh server |
| ST-COOKIE-01 | Cookie có thuộc tính và phạm vi gửi đúng | Header thực tế và hành vi browser |
| ST-FIX-01 | Định danh trước đăng nhập không có quyền sau đăng nhập | Kết quả với cả định danh mới và cũ |
| ST-ROTATE-01 | Rotation tuân thủ giới hạn định danh cũ | Mốc chuyển đổi, request đồng thời và quyết định quyền |
| ST-IDLE-01 | Không hoạt động đủ lâu làm phiên hết hạn | Mốc hoạt động cuối, không có request làm mới ngoài ý muốn |
| ST-ABS-01 | Hoạt động tiếp diễn không vượt tuổi phiên tối đa | Hoạt động duy trì, mốc tạo phiên logic, kết quả tại deadline |
| ST-LOGOUT-01 | Thông tin phiên cũ không truy cập được sau logout | Request mới dùng lại thông tin cũ, không tự xác thực lại |
| ST-REVOKE-01 | Vô hiệu hóa tài khoản có hiệu lực đúng hạn | Nguồn thu hồi, các đường truy cập và thời gian |
| ST-REFRESH-01 | Refresh hợp lệ và dùng lại tuân thủ chính sách | Chuỗi token, trạng thái sau dùng lại và audit |
| ST-MULTI-01 | Logout hiện tại và toàn bộ phiên đúng phạm vi | Nhiều phiên độc lập của cùng chủ thể |
| ST-SSO-01 | Kết thúc hoặc tái xác thực đúng các lớp | Phiên ứng dụng, IdP và các ứng dụng liên quan |
| ST-RECOVER-01 | Failover không làm sống lại phiên đã kết thúc | Trạng thái trước và sau chuyển node hoặc phục hồi |

Không phải hệ thống nào cũng có đủ các đối tượng trong bảng. Ghi rõ NOT_APPLICABLE khi có căn cứ, thay vì giả lập một cơ chế không tồn tại để hoàn thành danh sách.

## 16. Báo cáo, truy vết và các lỗi dễ kết luận sai

Mỗi ca nên liên kết:

~~~text
Rủi ro -> yêu cầu có phiên bản -> tiêu chí chấp nhận -> ca kiểm thử
       -> mô hình phiên và bản triển khai -> bằng chứng -> kết quả / phát hiện
~~~

Báo cáo cần có danh tính thử, phạm vi đường truy cập, chính sách thời gian, mốc quan sát, phương pháp đo, cấu hình liên quan và giới hạn kết luận. Tham chiếu an toàn tới phiên được dùng, không ghi giá trị có thể tái sử dụng để truy cập.

Phân biệt:

- **PASS:** bằng chứng đáp ứng tiêu chí trong phạm vi đã kiểm tra.
- **FAIL:** có bằng chứng một điều kiện không đạt.
- **BLOCKED hoặc chưa đánh giá:** thiếu tiền điều kiện, môi trường hoặc bằng chứng để kết luận.
- **NOT_APPLICABLE:** có căn cứ rằng cơ chế hoặc tiêu chí không áp dụng.

Một ngoại lệ được phê duyệt là quyết định quản trị riêng, không chuyển bằng chứng FAIL thành PASS.

| Lỗi kiểm thử | Vì sao kết luận có thể sai |
| --- | --- |
| Chỉ nhìn cookie bị xóa | Server vẫn có thể chấp nhận giá trị cũ |
| Dùng client tự refresh | Yêu cầu thử phiên cũ thực tế dùng token mới |
| Poll cùng phiên trong lúc đo idle | Phép kiểm tra tự dời deadline |
| Để idle hết trước khi đo absolute | Không biết cơ chế nào đã gây từ chối |
| Chỉ thấy định danh đổi | Chưa chứng minh định danh cũ mất quyền |
| Chỉ kiểm tra gateway | Backend hoặc đường tải có thể dùng cơ chế khác |
| Coi JWT là không thể thu hồi | Bỏ qua cơ chế và yêu cầu thực tế của hệ thống |
| Bỏ qua phiên IdP | Đăng nhập lại có thể bị hiểu nhầm là phiên cũ còn sống |
| Chỉ lưu log logout thành công | Chưa có bằng chứng hành vi tại tài nguyên bảo vệ |
| Ghi toàn bộ token vào report | Kho bằng chứng trở thành nguồn lộ thông tin truy cập |

Khi đổi IdP, thêm endpoint, thay store phiên, mở kết nối dài hoặc điều chỉnh cache, cần đánh giá lại phạm vi test. Kết quả cũ không tự chứng minh cơ chế mới giữ nguyên thuộc tính bảo mật.

## 17. Thực hành thiết kế hợp đồng và ca kiểm thử

Với một cổng quản trị giả định, hãy xác định mô hình phiên và viết bộ tiêu chí cho tạo phiên, idle, absolute, logout hiện tại, logout mọi phiên và vô hiệu hóa tài khoản.

Sau đó chọn ít nhất một ca ở mỗi nhóm có áp dụng: luồng hợp lệ, dùng lại thông tin cũ, điều kiện thời gian, nhiều client và phục hồi trạng thái. Mỗi ca cần có fixture, mốc đo, request thuộc phạm vi, kết quả mong đợi và bằng chứng không chứa bí mật.

Đặt thêm một worker, một đường tải file hoặc một ứng dụng SSO vào kiến trúc. Xác định phần tiêu chí và ca kiểm thử nào phải mở rộng trước khi có thể kết luận yêu cầu về phiên vẫn được đáp ứng.

Session test có giá trị khi kiểm chứng được quyết định truy cập trong suốt vòng đời, không chỉ trạng thái hiển thị trên client. Kết luận cần bám vào đúng chủ thể, đúng quyền, đúng thời gian, đúng đường truy cập và bằng chứng trên hệ thống thực tế.
