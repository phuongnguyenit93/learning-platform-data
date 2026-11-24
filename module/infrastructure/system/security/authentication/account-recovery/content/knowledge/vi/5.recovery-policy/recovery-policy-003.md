# Xếp thứ tự độ mạnh của các yếu tố trong chính sách khôi phục

Trong chương **Recovery Policy** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **factor strength ordering** là cách xác định bằng chứng nào đủ đáng tin để cho phép từng hành động khôi phục tài khoản. Đây là một phần của việc thiết kế luồng khôi phục an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực.

Vấn đề không chỉ là chọn phương thức “mạnh nhất”. Chính sách phải trả lời được: người dùng còn giữ bằng chứng nào, bằng chứng đó có thể đã bị lộ hay không, và nó được phép cấp quyền gì? Một mã gửi qua email có thể phù hợp để bắt đầu yêu cầu nhưng chưa chắc đủ để gỡ toàn bộ MFA. Một khóa bảo mật đã đăng ký có thể là bằng chứng tốt, nhưng quyền thay đổi tài khoản vẫn phải được xác định theo giao dịch cụ thể.

Mục tiêu là tránh để một đường khôi phục yếu trở thành cách vượt qua cơ chế xác thực mạnh, đồng thời vẫn có lối xử lý thực tế cho người dùng đã mất các phương thức chính.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt yếu tố xác thực, bằng chứng khôi phục và tín hiệu đánh giá rủi ro.
- So sánh các phương thức theo nhiều thuộc tính thay vì chỉ dựa vào tên công nghệ.
- Giải thích vì sao hai bằng chứng có thể cùng thất thủ dù được thu thập qua hai giao diện khác nhau.
- Xây dựng thứ tự ưu tiên phù hợp với từng hành động: đổi mật khẩu, thay kênh liên hệ, gỡ MFA hoặc đăng ký passkey mới.
- Thiết kế đường khôi phục có quyền giới hạn khi người dùng không còn bằng chứng mạnh.
- Chuyển quyết định về độ tin cậy thành kiểm tra phía máy chủ và trạng thái giao dịch có thể kiểm toán.

## 2. Phân biệt ba loại đầu vào của chính sách

### 2.1. Yếu tố xác thực

Yếu tố xác thực là căn cứ dùng để xác minh người đang đăng nhập, chẳng hạn bí mật người dùng biết hoặc thiết bị người dùng kiểm soát. Một phương thức cụ thể có thể kết hợp nhiều thành phần.

Ví dụ, việc dùng passkey có thể yêu cầu xác minh người dùng cục bộ bằng PIN hoặc sinh trắc học, tùy cấu hình. Điều đó không có nghĩa máy chủ đã nhận hai bằng chứng khôi phục độc lập. Máy chủ cần dựa trên kết quả giao thức và thuộc tính thực sự được xác minh, không tự đếm số màn hình người dùng đã đi qua.

Sinh trắc học dùng để mở khóa một authenticator cũng không tự trở thành bằng chứng từ xa độc lập rằng người yêu cầu là chủ hồ sơ tài khoản.

### 2.2. Bằng chứng khôi phục

Bằng chứng khôi phục là dữ liệu hoặc kết quả xác minh được chính sách chấp nhận để lấy lại quyền truy cập. Nó có thể đến từ:

- Một authenticator còn hoạt động và đã gắn với tài khoản từ trước.
- Mã khôi phục dự phòng đã được cấp trước sự cố.
- Quyền kiểm soát một kênh khôi phục đã được xác minh trước đó.
- Quy trình xác minh danh tính có căn cứ đối chiếu phù hợp.
- Một tổ hợp bằng chứng được chính sách cho phép.

Không phải mọi bằng chứng khôi phục đều tương đương một yếu tố đăng nhập thông thường. Ví dụ, đường khôi phục qua hỗ trợ có thể gồm nhiều kiểm tra nghiệp vụ và kiểm soát con người; không nên gọi toàn bộ quy trình đó là một “yếu tố mạnh” chỉ vì nó có nhiều bước.

### 2.3. Tín hiệu rủi ro

IP, vị trí gần đúng, cookie nhận diện thiết bị, lịch sử đăng nhập hoặc cách người dùng thao tác có thể giúp đánh giá bối cảnh. Những tín hiệu này thường không đủ để tự xác minh quyền sở hữu tài khoản.

| Đầu vào | Có thể giúp kết luận | Không nên tự suy ra |
| --- | --- | --- |
| Mã dùng một lần gửi đến email đã xác minh | Người yêu cầu đang có khả năng nhận hoặc sử dụng thông tin từ email đó | Email chắc chắn chưa bị chiếm hoặc người nhận chắc chắn là chủ tài khoản |
| Passkey đã đăng ký, xác minh đúng giao thức | Người yêu cầu đã thực hiện xác thực bằng credential được tài khoản chấp nhận | Mọi kênh khôi phục khác đều an toàn hoặc mọi thay đổi nhạy cảm đều được cho phép |
| Cookie nhận diện thiết bị | Yêu cầu có liên hệ với một bối cảnh trình duyệt từng được nhận diện | Thiết bị còn sạch hoặc người đang thao tác là chủ tài khoản |
| Thông tin hồ sơ đúng | Người yêu cầu biết thông tin tương ứng | Thông tin là bí mật và chưa từng bị lộ |
| Giấy tờ được kiểm tra trong quy trình phù hợp | Có thêm căn cứ về danh tính theo phạm vi quy trình | Người đó tự động có quyền với mọi tài khoản cùng tên |

Quy tắc quan trọng: **tín hiệu thuận lợi không tự thay thế bằng chứng bắt buộc**. Một IP quen thuộc không làm cho một mã khôi phục đã hết hạn trở nên hợp lệ.

## 3. Độ mạnh phải gắn với thuộc tính và giả định

Không có một thứ tự duy nhất luôn đúng cho mọi sản phẩm. Cần mô tả mỗi phương thức bằng các thuộc tính có thể kiểm tra và các giả định mà nó dựa vào.

| Thuộc tính | Câu hỏi cần đặt ra | Ý nghĩa với khôi phục |
| --- | --- | --- |
| Liên kết từ trước với tài khoản | Phương thức được đăng ký và xác minh khi nào? | Một kênh vừa được người yêu cầu nhập vào chưa chứng minh quyền với tài khoản |
| Khả năng chống đoán | Bí mật có đủ khó đoán và có giới hạn thử không? | Mã ngắn cần kiểm soát thử sai; bí mật dài vẫn cần bảo vệ lưu trữ |
| Khả năng chống phishing | Người dùng có thể bị dụ đưa bằng chứng cho một bên khác không? | Mật khẩu, OTP hoặc mã dự phòng có thể bị chuyển tiếp qua giao diện giả |
| Khả năng chống phát lại | Bằng chứng cũ có dùng lại được không? | Cần hạn dùng, challenge, trạng thái tiêu thụ hoặc cơ chế tương ứng |
| Ràng buộc với dịch vụ | Bằng chứng có gắn với đúng bên xác minh không? | Giảm nguy cơ dùng bằng chứng lấy ở nơi khác để xác thực tại dịch vụ |
| Ràng buộc với hành động | Kết quả xác minh cho phép chính xác thay đổi nào? | Xác minh để đổi mật khẩu không tự cấp quyền thay email và gỡ MFA |
| Phụ thuộc vào môi trường | Thiết bị, email hoặc tài khoản đồng bộ nào cần còn an toàn? | Nhiều bằng chứng có thể bị ảnh hưởng bởi cùng một sự cố |
| Khả năng thu hồi | Có thể vô hiệu hóa khi nghi bị lộ không? | Bằng chứng bị nghi xâm phạm cần được xử lý trong trạng thái giao dịch |
| Khả năng kiểm toán | Có biết bằng chứng nào đã được dùng, theo phiên bản chính sách nào không? | Giúp giải thích, điều tra và sửa sai sau khôi phục |

Một phương thức có thể tốt ở thuộc tính này nhưng yếu ở thuộc tính khác. Mã dự phòng ngẫu nhiên, dài và lưu ngoại tuyến có thể khó đoán và không phụ thuộc số điện thoại. Tuy nhiên, nếu người dùng nhập mã vào trang giả, mã vẫn có thể bị lộ.

Ngược lại, việc chống phát lại không đồng nghĩa chống phishing. Một OTP chỉ dùng được một lần vẫn có thể bị đối thủ sử dụng trước chủ tài khoản.

## 4. So sánh các bằng chứng thường gặp

Bảng sau là cơ sở thảo luận chính sách, không phải bảng xếp hạng bắt buộc cho mọi hệ thống.

| Bằng chứng hoặc phương thức | Điểm có thể làm tăng độ tin cậy | Điều kiện và giới hạn phải xét |
| --- | --- | --- |
| Authenticator dùng giao thức chống phishing, đã đăng ký từ trước | Có ràng buộc với dịch vụ và challenge khi giao thức được triển khai đúng | Cần kiểm tra tài khoản, credential, kết quả xác minh và tình trạng nghi bị chiếm; không tự cấp mọi quyền |
| Passkey đồng bộ đã đăng ký | Có các thuộc tính bảo vệ của giao thức passkey và thuận tiện khi mất một thiết bị | Cần xét tài khoản đồng bộ, các thiết bị liên quan và đường khôi phục của hệ sinh thái; không mặc định khóa riêng có thể bị xuất ra |
| Mã khôi phục dự phòng | Có thể ngẫu nhiên, dùng một lần và lưu tách khỏi thiết bị chính | Là bí mật có thể bị sao chép; mất tính độc lập nếu lưu trong cùng môi trường đã bị chiếm |
| Mã từ ứng dụng TOTP đã đăng ký | Chứng minh khả năng tạo mã từ bí mật tương ứng trong khoảng thời gian được chấp nhận | Không tự chống phishing; bản sao bí mật hoặc bản sao lưu có thể tạo ra cùng loại mã |
| Liên kết hoặc mã qua email đã xác minh | Sử dụng một kênh có quan hệ từ trước với tài khoản | Phụ thuộc bảo mật và đường khôi phục email; email mở sẵn trên thiết bị bị mất có thể không còn độc lập |
| Mã qua số điện thoại đã xác minh | Có thể tiếp cận người dùng khi họ không còn authenticator chính | Cần xét việc đổi chủ số, chiếm quyền số và khả năng đọc tin nhắn; không mặc định có cùng mức bảo đảm với authenticator chống phishing |
| Mật khẩu hiện tại | Có thể bổ sung bằng chứng khi người dùng chỉ mất yếu tố thứ hai | Có thể đã bị lộ; không dùng như bằng chứng duy nhất nếu sự cố được báo là lộ mật khẩu |
| Quy trình xác minh danh tính | Có thể hỗ trợ khi đã mất toàn bộ phương thức tự phục vụ | Phụ thuộc căn cứ đã có, chất lượng kiểm tra, gian lận và quyền của người xử lý; không phù hợp như nhau với mọi loại tài khoản |
| Thiết bị hoặc mạng quen thuộc | Hữu ích để điều chỉnh đánh giá rủi ro | Là tín hiệu bối cảnh; thiết bị quen thuộc cũng có thể bị chiếm |
| Câu hỏi cá nhân, thông tin công khai | Có thể giúp tìm hồ sơ hoặc hiểu bối cảnh yêu cầu | Không nên là căn cứ duy nhất để cấp lại quyền nhạy cảm vì có thể bị biết, đoán hoặc thu thập |

### Không suy luận độ mạnh chỉ từ tên phương thức

Các kết luận sau đều thiếu điều kiện:

- “Có passkey thì mọi yêu cầu khôi phục đều an toàn.”
- “Email luôn yếu hơn mọi mã dự phòng.”
- “Dùng phần cứng thì không cần kiểm tra giao dịch.”
- “Nhân viên hỗ trợ đã xem giấy tờ nên có thể bỏ qua toàn bộ chính sách.”
- “Người dùng đi qua ba bước nên chắc chắn có ba yếu tố độc lập.”

Cần so sánh cấu hình thực tế, cách đăng ký, tình trạng hiện tại và hành động định cấp quyền. Khi không có cơ sở xác minh một thuộc tính, không nên ghi nhận thuộc tính đó như đã được bảo đảm.

## 5. Xếp thứ tự theo hành động, không theo một con số chung

Hãy bắt đầu từ hành động cần bảo vệ rồi mới chọn bằng chứng. Mức thay đổi quyền càng lớn, hậu quả nếu chấp nhận sai càng nghiêm trọng.

Ví dụ, đổi mật khẩu trong khi vẫn giữ nguyên yêu cầu MFA khác với gỡ MFA và tạo một phiên đăng nhập đầy đủ. Cùng một bằng chứng có thể đủ cho hành động thứ nhất nhưng không đủ cho hành động thứ hai.

| Hành động | Hậu quả cần xét | Ví dụ hướng chính sách |
| --- | --- | --- |
| Bắt đầu yêu cầu khôi phục | Quấy rối, dò tài khoản, tạo nhiều giao dịch | Có thể cho phép khởi tạo với kiểm soát lạm dụng; chưa cấp quyền đăng nhập |
| Đặt lại mật khẩu, giữ yêu cầu MFA hiện có | Đối thủ thay được một credential nhưng chưa vượt mọi điều kiện đăng nhập | Có thể dùng kênh đã xác minh nếu chính sách cho phép; kết quả chỉ cấp quyền đổi mật khẩu |
| Gỡ hoặc thay một yếu tố MFA | Đối thủ có thể loại bỏ điều kiện đang chặn truy cập | Ưu tiên authenticator còn lại hoặc tổ hợp bằng chứng được thiết kế riêng cho mất MFA |
| Thêm passkey mới sau khi mất mọi authenticator | Đối thủ có thể tạo phương thức truy cập bền vững | Cần quy trình khôi phục được phê duyệt cho tình huống này, với phạm vi và kiểm soát tương ứng |
| Đổi email khôi phục | Đối thủ có thể chuyển các lần khôi phục sau sang kênh của họ | Không dùng chính email mới làm bằng chứng duy nhất; cần căn cứ có trước thay đổi |
| Khôi phục tài khoản quản trị | Quyền mới có thể tác động nhiều người hoặc hệ thống khác | Có thể yêu cầu quy trình riêng, phê duyệt độc lập và quyền ban đầu giới hạn |

Đây là ví dụ thiết kế, không phải cấu hình chung để sao chép vào mọi dịch vụ.

### Một thứ tự có điều kiện

Có thể diễn đạt chính sách như sau:

> Với hành động thay MFA, bằng chứng A được ưu tiên hơn bằng chứng B khi A đáp ứng các thuộc tính bắt buộc của hành động trong bối cảnh hiện tại, còn B thiếu ít nhất một thuộc tính đó.

Điều này tạo ra một thứ tự **có điều kiện**. Hai phương thức có thể không so sánh trực tiếp được: một phương thức ít phụ thuộc nhà mạng hơn, phương thức kia có quy trình kiểm toán tốt hơn, nhưng cả hai đều cần biện pháp bổ sung cho hành động cụ thể.

Nếu hệ thống dùng điểm số rủi ro, điểm số chỉ nên hỗ trợ những quyết định đã được chính sách cho phép. Tổng nhiều tín hiệu thuận lợi không được tự biến một phương thức thiếu thuộc tính bắt buộc thành phương thức đủ điều kiện.

## 6. Tính độc lập quan trọng hơn việc đếm số bằng chứng

Giả sử chính sách chấp nhận “mật khẩu + mã email”. Nếu email đang mở trên máy bị nhiễm mã độc và mật khẩu cũng bị đọc từ máy đó, hai đầu vào có thể cùng rơi vào tay một đối thủ.

Tương tự, “TOTP + mã dự phòng” không nhất thiết độc lập nếu cả bí mật TOTP và mã dự phòng được lưu trong cùng một kho đã bị chiếm.

~~~mermaid
flowchart TD
    A[Thiết bị hoặc tài khoản nền bị chiếm] --> B[Truy cập email]
    A --> C[Truy cập bản sao mã dự phòng]
    B --> D[Hai bằng chứng có chung nguồn thất thủ]
    C --> D
    D --> E[Không tự xem là hai lớp bảo vệ độc lập]
~~~

Khi xác định một tổ hợp đủ mạnh, cần hỏi:

1. Cả hai bằng chứng phụ thuộc vào thiết bị nào?
2. Chúng có phụ thuộc cùng tài khoản email hoặc tài khoản đồng bộ không?
3. Một đường khôi phục có thể đặt lại đường còn lại không?
4. Sự cố đang được báo có làm mất độ tin cậy của cả hai không?
5. Có bằng chứng nào vừa được thêm sau thời điểm nghi bị chiếm không?

Sự độc lập phải được đánh giá theo mô hình đe dọa. Hai thiết bị khác nhau vẫn có thể cùng phụ thuộc một tài khoản đồng bộ; ngược lại, không nên tự kết luận mọi phương thức trên cùng thiết bị đều có mức bảo vệ giống nhau.

Một kênh được thiết lập từ lâu là dữ kiện hữu ích, nhưng thời gian tồn tại không tự chứng minh kênh đó chưa bị chiếm. Một kênh vừa thêm cũng không trở thành căn cứ tin cậy chỉ vì người dùng đã nhận được mã trên kênh ấy.

## 7. Từ so sánh độ mạnh đến chính sách có thể thực thi

Một quy trình xây dựng chính sách có thể gồm sáu bước.

### Bước 1: Liệt kê hành động và hậu quả

Tách rõ các quyền: đặt lại mật khẩu, gỡ TOTP, thêm passkey, thay email, thu hồi phiên và cấp phiên mới. Tránh một quyền chung tên “recovered” cho phép mọi thao tác.

### Bước 2: Xác định các tình huống mất quyền

Ví dụ: chỉ quên mật khẩu, mất điện thoại nhưng còn khóa bảo mật, mất mọi authenticator, nghi thiết bị bị xâm nhập hoặc nghi email bị chiếm. Những tình huống này làm thay đổi bằng chứng nào còn dùng được.

Không cần coi mọi khai báo của người yêu cầu là sự thật đã kiểm chứng. Tuy nhiên, một khai báo về khả năng bị xâm nhập phải được đưa vào đánh giá thay vì tiếp tục dùng chính phương thức bị báo mất an toàn làm căn cứ duy nhất.

### Bước 3: Mô tả thuộc tính bắt buộc

Với mỗi hành động, ghi rõ bằng chứng phải liên kết với tài khoản từ trước, còn hiệu lực, chưa bị tiêu thụ và có phạm vi phù hợp. Thêm những yêu cầu về độc lập hoặc phê duyệt khi cần.

### Bước 4: Chỉ định các đường được phép

Định nghĩa các tổ hợp có thể chấp nhận và những đường cần chuyển sang xem xét. Không để giao diện tự chọn đường ít bước nhất trong khi máy chủ chỉ kiểm tra “đã có một mã hợp lệ”.

Đường dự phòng phải được đánh giá cùng đường chính. Nếu một tài khoản dùng authenticator mạnh nhưng có thể bị đặt lại toàn bộ chỉ bằng thông tin công khai, thuộc tính bảo vệ của authenticator không bảo vệ được đường khôi phục đó.

### Bước 5: Giới hạn quyền sau mỗi đường

Một đường khôi phục có mức tin cậy hạn chế có thể chỉ tạo giao dịch chờ, cho phép bổ sung bằng chứng hoặc thực hiện một hành động cụ thể. Không tự cấp quyền đổi mọi kênh liên hệ.

Nếu sản phẩm quyết định chấp nhận một đường có mức bảo đảm thấp hơn để tránh mất tài khoản vĩnh viễn, đây phải là quyết định rủi ro được mô tả rõ, với quyền và kiểm soát tương ứng.

### Bước 6: Ghi phiên bản và trách nhiệm

Lưu phiên bản chính sách, loại bằng chứng, thời điểm xác minh, hành động được cấp và lý do quyết định. Với hỗ trợ thủ công, ghi nhận người xử lý và người phê duyệt khi quy trình yêu cầu.

Không lưu token, OTP, mã dự phòng, cookie hoặc tài liệu nhạy cảm đầy đủ vào log chỉ để tiện kiểm toán. Giữ dữ liệu tối thiểu cần thiết theo chính sách của dịch vụ.

## 8. Ví dụ ma trận quyết định

Giả sử một dịch vụ cá nhân hỗ trợ mật khẩu, TOTP, passkey và mã dự phòng. Dịch vụ lựa chọn chính sách minh họa sau:

| Bối cảnh | Bằng chứng còn lại | Quyết định minh họa | Giới hạn |
| --- | --- | --- | --- |
| Quên mật khẩu, còn TOTP | Kênh email đã xác minh để đặt lại mật khẩu | Cho phép đổi mật khẩu qua giao dịch dùng một lần | Đăng nhập sau đó vẫn cần TOTP; không tự gỡ MFA |
| Mất điện thoại, còn passkey trên khóa khác | Xác thực lại bằng passkey đã đăng ký | Cho phép giao dịch thay yếu tố bị mất theo chính sách | Xác minh lại đúng hành động; không thay email cùng lúc |
| Mất TOTP, còn mã dự phòng | Mã dự phòng hợp lệ, chưa dùng và không bị nghi lộ | Cho phép đường thay TOTP mà sản phẩm đã quy định | Tiêu thụ mã và giới hạn quyền vào giao dịch tương ứng |
| Báo email đã bị chiếm | Chỉ còn mã gửi tới chính email đó | Chưa đủ để thực hiện thay đổi nhạy cảm | Yêu cầu đường khác; không cộng điểm thiết bị quen để bỏ điều kiện |
| Mất mọi authenticator và mã dự phòng | Còn kênh liên hệ nhưng thiếu bằng chứng theo đường tự phục vụ | Chuyển quy trình xử lý riêng nếu dịch vụ có hỗ trợ | Chưa cấp phiên đầy đủ hoặc cho tự thêm authenticator |
| Tài khoản đặc quyền mất mọi yếu tố | Yêu cầu qua hỗ trợ nội bộ | Áp dụng chính sách khôi phục tài khoản đặc quyền | Không tự kế thừa đường khôi phục dành cho tài khoản thông thường |

Ma trận này không tuyên bố mã dự phòng luôn đủ để thay TOTP ở mọi sản phẩm. Nó cho thấy một lựa chọn phải được ghi rõ: bằng chứng nào, tình huống nào, quyền gì và giới hạn nào.

Đối với hệ thống không thu thập hoặc không có căn cứ đối chiếu danh tính từ trước, yêu cầu gửi giấy tờ có thể không giải quyết được câu hỏi ai sở hữu tài khoản. Một dịch vụ cần xác định trước liệu có cung cấp đường xác minh danh tính hay không, thay vì tự phát thu thập dữ liệu nhạy cảm khi hỗ trợ gặp ca khó.

## 9. Thực thi phía máy chủ

Thứ tự độ mạnh không có tác dụng nếu chỉ tồn tại trong tài liệu hoặc giao diện. Máy chủ phải kiểm tra các điều kiện của đường khôi phục ở mọi bước cấp quyền.

Dưới đây là mã giả về cấu trúc quyết định, không phải một thuật toán chấm điểm dùng chung:

~~~text
evaluateRecovery(transaction, requestedAction, currentContext):
    policy = loadPolicy(transaction.policyVersion)

    require transaction.accountId is fixed
    require transaction.action == requestedAction
    require transaction is active and not expired
    require transaction has not been completed or cancelled

    evidence = loadVerifiedEvidence(transaction.id)

    require every accepted item:
        is bound to this account and transaction
        is valid for the requested action
        is still fresh under policy
        is not revoked or already consumed

    route = policy.findEligibleRoute(
        action = requestedAction,
        accountClass = currentContext.accountClass,
        evidence = evidence,
        incidentContext = currentContext.incidentContext,
        dependencies = evidence.dependencyInformation
    )

    if route is absent:
        return REQUIRE_MORE_EVIDENCE_OR_REVIEW

    if currentContext requires unresolved review:
        return PENDING_REVIEW

    return AUTHORIZE_LIMITED_ACTION(
        transactionId = transaction.id,
        action = requestedAction,
        expiresAt = policy.authorizationExpiry(route)
    )
~~~

Một số điểm cần làm rõ khi triển khai:

- Bằng chứng đã xác minh phải được lưu trong trạng thái do máy chủ quản lý; không tin trường do client gửi như “factorStrength=high”.
- Phạm vi hành động phải được ràng buộc từ giao dịch. Không dùng kết quả xác minh cho đặt lại mật khẩu để gọi API gỡ MFA.
- Nếu cần thay hành động, phải đánh giá lại quyền tương ứng.
- Thời hạn của bằng chứng và thời hạn của quyền thực hiện thay đổi có thể khác nhau; cả hai phải được kiểm tra.
- Nếu chính sách đổi khi giao dịch đang chờ, phải có quy tắc rõ về việc tiếp tục theo phiên bản cũ hay buộc đánh giá lại. Không âm thầm trộn điều kiện của hai phiên bản.
- Quyền dựa trên mã dùng một lần phải được tiêu thụ bằng cơ chế bảo đảm hai yêu cầu đồng thời không cùng thành công.

Khi thực hiện thay đổi cuối cùng, máy chủ phải kiểm tra lại trạng thái và quyền còn hiệu lực, đồng thời ghi nhận việc tiêu thụ quyền một cách nhất quán với thay đổi credential. Không chỉ kiểm tra mã ở đầu luồng rồi cho mọi bước sau chạy tự do.

## 10. Khôi phục với bằng chứng yếu hơn: giới hạn và xây lại độ tin cậy

Người dùng có thể thực sự mất tất cả phương thức mạnh. Chính sách không thể giải quyết vấn đề này bằng cách yêu cầu họ dùng lại phương thức đã mất. Tuy nhiên, bỏ mọi điều kiện cũng tạo ra một đường chiếm đoạt.

Một cách thiết kế là phân biệt các kết quả:

1. **Chưa đủ bằng chứng:** chưa cho thay credential; có thể bổ sung bằng chứng hoặc chuyển xử lý.
2. **Được tiếp tục một giao dịch giới hạn:** cho thực hiện đúng bước đã được duyệt, không cấp phiên đầy đủ.
3. **Được khôi phục theo phạm vi đã phê duyệt:** hoàn thành thay đổi, xử lý phương thức bị mất và áp dụng chính sách phiên tương ứng.

Các kiểm soát bổ sung có thể gồm thông báo tới kênh đã có trước, thời gian chờ, xem xét độc lập và hạn chế một số thay đổi liên tiếp. Cách chọn phải phù hợp với giá trị tài khoản, khả năng phát hiện chiếm đoạt và nhu cầu sử dụng.

Những kiểm soát này không tự tạo ra bằng chứng sở hữu. Chờ đủ thời gian không chứng minh người yêu cầu là chủ tài khoản. Không có ai phản đối thông báo cũng không chứng minh yêu cầu hợp lệ, vì người bị mất quyền có thể không còn nhận được thông báo.

### Authenticator mới chưa giải quyết được tính hợp lệ của quyết định trước đó

Một đối thủ được chấp nhận nhầm qua đường yếu có thể đăng ký một passkey hoạt động hoàn toàn đúng giao thức. Các lần xác thực sau bằng passkey ấy có thể hợp lệ về mặt kỹ thuật, nhưng quyết định cấp quyền ban đầu vẫn sai.

Vì vậy, việc tạo authenticator mới không được tự xóa dấu vết về đường khôi phục đã dùng hoặc làm mất những hạn chế còn áp dụng. Hệ thống nên lưu nguồn gốc việc đăng ký và trạng thái khôi phục cần thiết để thực thi chính sách.

Mục tiêu của việc thiết lập lại phương thức mạnh là bảo vệ truy cập tiếp theo, sau khi quyết định khôi phục đã đạt điều kiện. Nó không thể thay thế bằng chứng còn thiếu của chính quyết định đó.

## 11. Kiểm soát session là phần nối tiếp của quyết định độ tin cậy

Một giao dịch được duyệt không nên tự trở thành phiên đăng nhập có toàn quyền. Quyền đổi một credential và quyền sử dụng toàn bộ tài khoản là hai quyết định liên quan nhưng cần phân biệt.

Ví dụ, một liên kết đặt lại mật khẩu có thể chỉ cho phép đặt mật khẩu mới. Người dùng vẫn phải hoàn thành các yêu cầu đăng nhập còn áp dụng để truy cập tài khoản.

Sau thay đổi, chính sách cần xác định:

- Phiên hoặc refresh token nào phải bị thu hồi do sự cố hay do loại thay đổi.
- Authenticator hoặc mã dự phòng nào cần vô hiệu hóa vì bị mất, bị lộ hoặc đã dùng.
- Kênh liên hệ nào cần được kiểm tra trước khi sử dụng cho các lần khôi phục sau.
- Khi nào được cấp phiên mới và phiên đó có những quyền gì.
- Thông báo và bản ghi kiểm toán nào phải được tạo.

Nếu đối thủ còn giữ một phiên có quyền đổi thông tin khôi phục, chỉ thay mật khẩu có thể không loại bỏ đường truy cập đó. Ngược lại, cũng không nên mặc định mọi sự cố đều cần vô hiệu hóa tất cả phương thức còn an toàn; phạm vi xử lý phải được chính sách và bối cảnh sự cố quyết định.

Khi nghi thiết bị bị xâm nhập, việc tạo bí mật mới ngay trên thiết bị đó có thể tiếp tục làm lộ bí mật. Một đường khôi phục cần cho phép sử dụng môi trường khác theo chính sách và không coi việc xuất hiện thiết bị mới là lý do tự động từ chối chủ tài khoản hợp lệ.

## 12. Tình huống thực tế

Linh dùng mật khẩu, TOTP trên điện thoại và một passkey trên khóa bảo mật riêng. Linh báo mất điện thoại, vẫn giữ khóa bảo mật và đang truy cập từ một máy tính mới.

Nếu chỉ có bảng điểm đơn giản, hệ thống có thể coi máy mới là rủi ro cao rồi ép Linh nhận SMS trên chiếc điện thoại đã mất. Đây là lựa chọn không phản ánh đúng bằng chứng hiện có.

Với chính sách theo hành động:

1. Linh chọn yêu cầu thay TOTP do mất thiết bị.
2. Máy chủ xác minh lại bằng passkey đã gắn với tài khoản, theo giao thức và yêu cầu của đường này.
3. Hệ thống kiểm tra bối cảnh, trạng thái credential và phạm vi giao dịch; máy tính mới là dữ kiện để đánh giá, không tự phủ nhận bằng chứng hợp lệ.
4. Giao dịch chỉ cho phép thay TOTP bị mất và xử lý các phiên liên quan theo chính sách.
5. Nếu Linh tiếp tục muốn thay email khôi phục, đó là hành động khác cần được kiểm tra riêng.

Bây giờ đổi giả định: Linh mất cả khóa bảo mật, không còn mã dự phòng và báo email có thể đã bị chiếm. Nhận được mã qua chính email ấy chưa giải quyết được vấn đề. Hệ thống phải chuyển sang đường khác đã định nghĩa, hoặc giữ yêu cầu ở trạng thái chưa đủ căn cứ nếu không có đường phù hợp.

Điểm quyết định là **bằng chứng còn đáng tin cho hành động nào**, không phải Linh đã đi qua bao nhiêu màn hình.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Vì sao thứ tự độ mạnh bị phá vỡ | Hướng sửa |
| --- | --- | --- |
| Mọi phương thức đều tạo cùng một session đầy đủ | Bằng chứng có mức bảo đảm hạn chế nhận quyền giống đường mạnh hơn | Cấp quyền theo hành động và đường khôi phục đã được duyệt |
| Cộng nhiều tín hiệu bối cảnh để bỏ bằng chứng bắt buộc | Dữ kiện dễ giả mạo hoặc cùng phụ thuộc có thể thay thế một điều kiện cốt lõi | Giữ điều kiện bắt buộc tách khỏi đánh giá rủi ro bổ sung |
| Nhận mã ở email mới rồi dùng mã đó để cho đổi email | Người yêu cầu tự chọn nơi nhận bằng chứng | Dựa trên căn cứ đã có trước thay đổi hoặc đường xác minh khác được phép |
| Đếm TOTP và mã dự phòng như hai yếu tố độc lập trong mọi ca | Cả hai có thể nằm trong cùng kho đã bị chiếm | Xét quan hệ phụ thuộc và bối cảnh mất an toàn |
| Cho hỗ trợ tự bỏ qua yêu cầu vì ca khẩn cấp | Đường thủ công trở thành đường dễ vượt nhất | Định nghĩa quyền, điều kiện ngoại lệ, phê duyệt và kiểm toán |
| Đăng ký passkey mới là xóa mọi hạn chế ngay | Authenticator mới có thể được cấp cho người bị xác minh nhầm | Giữ nguồn gốc và điều kiện khôi phục còn hiệu lực |
| Kiểm tra một lần rồi không kiểm tra lúc commit | Quyền có thể hết hạn, bị thu hồi hoặc bị dùng đồng thời | Kiểm tra lại và tiêu thụ quyền nhất quán với thay đổi |
| Dùng một chính sách cho cả người dùng và quản trị viên | Hậu quả của cấp quyền sai khác nhau đáng kể | Xác định yêu cầu theo loại tài khoản và phạm vi quyền |

Cơ chế giới hạn tốc độ và chống lạm dụng cũng cần bảo vệ các đường có thể bị thử lặp lại. Tuy vậy, giới hạn tốc độ không làm bằng chứng yếu trở thành mạnh: nó giảm khả năng thử và quấy rối, không chứng minh ai đang yêu cầu.

## 14. Tự kiểm tra cách hiểu

### Câu hỏi 1: OTP chỉ dùng một lần có luôn mạnh hơn mật khẩu không?

Không thể kết luận chung. OTP có thể giảm khả năng dùng lại một mã cũ, nhưng vẫn có thể bị phishing hoặc bị đối thủ dùng trước. Cần xét nơi nhận mã, điều kiện kiểm tra và hành động mà mã cho phép.

### Câu hỏi 2: Nếu mã dự phòng và email đều hợp lệ, có thể coi là hai bằng chứng độc lập không?

Chỉ khi mô hình đe dọa và thông tin hiện có hỗ trợ giả định đó. Nếu mã dự phòng nằm trong email đã bị chiếm, tính hợp lệ kỹ thuật của hai bằng chứng không tạo ra hai nguồn bảo vệ độc lập.

### Câu hỏi 3: Người dùng đã đăng ký passkey mới sau khôi phục thì có thể coi lần khôi phục ban đầu đủ mạnh không?

Không. Passkey mới bảo vệ một số lần xác thực tiếp theo theo thuộc tính của giao thức. Nó không chứng minh rằng quyết định chấp nhận người đăng ký trước đó là đúng.

### Câu hỏi 4: Có nên xóa hoàn toàn đường dự phòng vì nó yếu hơn đường chính không?

Cần đánh giá cả nguy cơ chiếm đoạt và nguy cơ mất quyền hợp lệ. Có thể cung cấp đường dự phòng với bằng chứng, phạm vi quyền và quy trình xử lý phù hợp. Không nên để một đường yếu hơn tự động có cùng quyền với đường mạnh chỉ vì nó có nhãn “khôi phục”.

## 15. Những điều cần ghi rõ trong một chính sách

Một chính sách factor strength ordering có thể được đọc và thực thi khi trả lời được:

- Hành động nào đang được bảo vệ và hậu quả nếu cấp quyền sai là gì?
- Loại tài khoản và tình huống mất quyền nào được đường này hỗ trợ?
- Bằng chứng nào được chấp nhận, đã liên kết từ khi nào và còn hiệu lực bao lâu?
- Những bằng chứng nào có thể cùng thất thủ hoặc không còn đáng tin trong sự cố đang xét?
- Điều kiện nào bắt buộc, điều kiện nào chỉ hỗ trợ đánh giá rủi ro?
- Nếu thiếu bằng chứng mạnh, yêu cầu bị giữ lại, chuyển xem xét hay được cấp quyền giới hạn nào?
- Một lần xác minh có thể dùng cho hành động nào và bị tiêu thụ ra sao?
- Sau khôi phục, credential, session và các hạn chế còn lại được xử lý như thế nào?
- Máy chủ và người hỗ trợ có thể giải thích quyết định dựa trên phiên bản chính sách và bằng chứng nào?

Xếp thứ tự độ mạnh có ích khi nó dẫn đến quyết định cụ thể: chấp nhận bằng chứng nào, cấp đúng quyền nào và giữ kiểm soát gì cho phần rủi ro còn lại. Chính sách khôi phục an toàn phải bảo vệ cả quá trình trở lại tài khoản, thay vì chỉ bảo vệ màn hình đăng nhập.