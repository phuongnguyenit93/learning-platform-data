# Strong authentication

## 1. Xác thực mạnh cần bảo vệ điều gì?

**Strong authentication**, hay xác thực mạnh, là việc sử dụng phương thức và quy trình xác thực có khả năng chống lại các nguy cơ phù hợp với tài khoản và tài nguyên cần bảo vệ. Mục tiêu là tăng độ chắc chắn rằng bên đang đăng nhập kiểm soát những yếu tố xác thực đã được liên kết hợp lệ với tài khoản.

Một mật khẩu dài có thể khó đoán nhưng vẫn bị nhập vào trang giả mạo. Một mã OTP có thể còn hiệu lực nhưng đang được kẻ tấn công chuyển tiếp ngay trong lúc nạn nhân đăng nhập. Một phương thức chống phishing tốt vẫn có thể bị vô hiệu hóa về mặt vận hành nếu quy trình khôi phục cho phép người khác đăng ký lại phương thức chỉ bằng một câu trả lời dễ đoán.

Vì vậy, đánh giá xác thực mạnh cần xem đồng thời:

- Phương thức chứng minh quyền kiểm soát tài khoản.
- Khả năng chống đoán, đánh cắp, phát lại và lừa đảo lấy thông tin xác thực.
- Cách đăng ký, thay đổi, thu hồi và khôi phục phương thức.
- Cách cấp và bảo vệ phiên sau khi xác thực thành công.
- Mức kiểm soát phù hợp với tác vụ và phạm vi quyền.

Xác thực trả lời câu hỏi về danh tính hoặc quyền kiểm soát yếu tố đã đăng ký. Nó không tự cấp quyền quản trị, không chứng minh mọi hành động nghiệp vụ là được phép và không thay thế quản lý vòng đời tài khoản.

## 2. Yếu tố xác thực và sự độc lập

Các nhóm yếu tố thường được mô tả như sau:

| Nhóm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Điều người dùng biết | Một bí mật cần được nhớ hoặc cung cấp | Mật khẩu, PIN trong ngữ cảnh phù hợp |
| Điều người dùng có | Quyền kiểm soát một thiết bị hoặc bộ xác thực | Khóa bảo mật, ứng dụng sinh OTP, khóa mật mã trên thiết bị |
| Đặc điểm của người dùng | Một đặc điểm sinh trắc được kiểm tra | Vân tay, nhận diện khuôn mặt trong cơ chế hỗ trợ |

**MFA** kết hợp nhiều nhóm yếu tố, không chỉ nhiều bước trên giao diện. Nhập mật khẩu rồi trả lời câu hỏi bí mật vẫn chủ yếu dựa vào những điều người dùng biết. Nhập hai mật khẩu khác nhau cũng không tự tạo ra hai nhóm yếu tố độc lập.

Ngược lại, một thao tác xác thực có thể kết hợp nhiều yếu tố bên trong bộ xác thực. Ví dụ, một bộ xác thực dùng khóa mật mã và yêu cầu người dùng xác minh cục bộ bằng PIN hoặc sinh trắc có thể cung cấp bằng chứng phù hợp về quyền sở hữu cùng xác minh người dùng, nếu cơ chế và cấu hình thực sự hỗ trợ điều đó.

Không nên đếm số màn hình, số thiết bị hoặc số lần bấm để kết luận mức độ mạnh. Cần xem yếu tố nào được kiểm tra, bằng chứng nào được bên xác minh nhận và một sự cố đơn lẻ có thể làm mất những yếu tố nào.

Ví dụ, lưu mật khẩu và mã khôi phục tài khoản trong một nơi dễ bị truy cập có thể tạo rủi ro chung. Dù các phương thức được đặt tên khác nhau, khả năng bảo vệ thực tế phụ thuộc đường tấn công và cách triển khai.

## 3. Phân biệt những đặc tính thường bị đánh đồng

| Đặc tính | Câu hỏi đánh giá | Ví dụ về giới hạn |
| --- | --- | --- |
| Khó đoán | Kẻ tấn công có thể đoán bí mật bằng cách thử không? | Mật khẩu khó đoán vẫn có thể bị phishing |
| Chống phát lại | Bằng chứng đã dùng có thể được dùng lại không? | OTP dùng một lần vẫn có thể bị chuyển tiếp trước khi nạn nhân hoàn tất |
| Nhiều yếu tố | Có kết hợp các nhóm yếu tố phù hợp không? | Không phải mọi MFA đều chống phishing như nhau |
| Chống phishing | Bằng chứng có bị thu thập và sử dụng tại bên giả mạo hay chuyển tiếp dễ dàng không? | OTP nhập bằng tay có thể bị lấy qua trang giả |
| Bảo vệ khóa | Khóa hoặc bí mật có thể bị xuất, sao chép hoặc lạm dụng không? | Hai phương thức cùng dùng mật mã có thể có mô hình lưu khóa khác nhau |
| An toàn khôi phục | Người khác có thể chiếm tài khoản qua đường khôi phục không? | Helpdesk yếu có thể trở thành đường bỏ qua MFA |
| An toàn phiên | Phiên sau đăng nhập có dễ bị chiếm hoặc sử dụng lại không? | Xác thực mạnh không tự ngăn mọi hình thức đánh cắp token |

Mỗi đặc tính giải quyết một phần của vấn đề. Không nên dùng một nhãn như “có MFA” để thay cho việc đánh giá toàn bộ các đặc tính cần thiết.

## 4. So sánh các phương thức trong bối cảnh IAM

### 4.1. Mật khẩu

Mật khẩu là bí mật có thể bị đoán, tái sử dụng, đánh cắp hoặc nhập vào nơi giả mạo. Cần giảm những đường rủi ro này bằng chính sách mật khẩu phù hợp, chống thử đoán, bảo vệ kho xác thực và kết hợp phương thức bổ sung khi mức rủi ro yêu cầu.

Phía server cần lưu giá trị kiểm tra mật khẩu bằng cơ chế băm dành cho mật khẩu với salt và cấu hình chi phí phù hợp, thay vì lưu bản rõ hoặc coi mã hóa có thể giải ngược là cách lưu mặc định. Bảo vệ kênh truyền và cơ chế xác thực vẫn cần thiết dù cách lưu đã đúng.

Không nhúng mật khẩu vào mã nguồn, log hoặc script dùng chung. Với danh tính workload, nên có cơ chế dành cho tự động hóa thay vì tái sử dụng mật khẩu tài khoản cá nhân.

### 4.2. OTP qua ứng dụng hoặc kênh liên lạc

OTP giúp giảm giá trị của việc phát lại một mã cũ và có thể bổ sung một yếu tố ngoài mật khẩu. Tuy nhiên, mã được người dùng đọc rồi nhập vào một trang có thể bị lấy và chuyển tiếp trong thời gian còn hiệu lực.

OTP qua tin nhắn còn phụ thuộc vào kiểm soát số điện thoại, nhà cung cấp dịch vụ và quy trình chuyển hoặc khôi phục số. Không nên coi số điện thoại là bằng chứng sở hữu bất biến suốt vòng đời tài khoản.

OTP qua ứng dụng cũng cần bảo vệ khâu đăng ký và bí mật sinh mã. Với cơ chế sinh OTP dựa trên một bí mật dùng chung, server cần sử dụng lại bí mật đó để xác minh theo thuật toán; do đó không thể máy móc áp dụng cách chỉ lưu hash như đối với mật khẩu. Cần bảo vệ bí mật bằng cơ chế lưu trữ, mã hóa và phân quyền phù hợp.

Độ an toàn phụ thuộc cả việc giới hạn thử mã, kiểm soát hiệu lực, ngăn chấp nhận lại bằng chứng đã dùng theo cơ chế hỗ trợ và xử lý sai lệch thời gian phù hợp. Không chọn khoảng chấp nhận quá rộng chỉ để giảm lỗi đăng nhập.

### 4.3. Xác nhận qua thông báo đẩy

Một yêu cầu xác nhận trên thiết bị đã đăng ký có thể thuận tiện, nhưng người dùng có thể bấm đồng ý do nhầm lẫn hoặc bị làm phiền bởi nhiều yêu cầu liên tiếp.

Hiển thị ngữ cảnh, yêu cầu đối chiếu số hoặc giới hạn yêu cầu giúp giảm một số dạng lạm dụng. Những biện pháp này không tự biến mọi cơ chế push thành phương thức chống phishing bằng mật mã.

Người dùng cần biết một yêu cầu họ không chủ động tạo ra phải được từ chối và báo cáo. Hệ thống cần kiểm soát nguồn phát yêu cầu, tần suất, thời hạn và phản ứng với dấu hiệu bất thường.

### 4.4. Khóa bảo mật và passkey

Các cơ chế xác thực khóa công khai gắn với bên cung cấp dịch vụ có thể giúp chống phishing bằng cách liên kết bằng chứng với đúng dịch vụ theo thiết kế giao thức. Bên xác minh sử dụng khóa công khai; người dùng không nhập một bí mật dùng chung có thể tái sử dụng ở mọi trang.

Trong những cơ chế phổ biến này, PIN hoặc sinh trắc có thể dùng để xác minh người dùng cục bộ và cho phép bộ xác thực sử dụng khóa. Ứng dụng cần kiểm tra đúng các bằng chứng và thuộc tính mà cơ chế cung cấp, thay vì tự suy rằng mọi lần chạm thiết bị đều đã xác minh người dùng ở mức yêu cầu.

Passkey có thể có mô hình đồng bộ hoặc gắn với một thiết bị, với những khác biệt về lưu khóa, sao lưu và khôi phục. Không mặc định mọi passkey đều là khóa phần cứng không thể xuất, cũng không mặc định mọi cách triển khai đều phù hợp cùng một yêu cầu bảo vệ.

Việc lựa chọn cần xét quyền của tài khoản, yêu cầu quản lý thiết bị, khả năng phục hồi khi mất thiết bị và các đường khôi phục đi kèm. Không chỉ nhìn tên phương thức trên màn hình đăng nhập.

## 5. Chọn chính sách theo tài khoản và hành động

Xác thực mạnh cần được thiết kế theo phạm vi rủi ro, không phải bằng cách thêm cùng một bước cho mọi luồng.

| Ngữ cảnh | Điều cần chú ý |
| --- | --- |
| Người dùng thông thường | Phương thức dễ sử dụng đúng, bảo vệ đăng nhập và khôi phục |
| Quản trị viên IAM | Khả năng chống phishing, môi trường quản trị, xác thực đủ mới và quyền có phạm vi |
| Đối tác hoặc khách mời | Nguồn danh tính, bằng chứng từ bên liên kết, vòng đời quan hệ truy cập |
| Thay đổi phương thức xác thực | Ngăn phiên bị chiếm dùng để gắn phương thức của kẻ tấn công |
| Hành động nghiệp vụ nhạy cảm | Kiểm tra mức và độ mới của xác thực cùng quyền nghiệp vụ |
| Workload | Chứng minh danh tính máy, bảo vệ khóa, phạm vi và vòng đời thông tin xác thực |

Một phiên đủ dùng để đọc tài liệu có thể chưa đủ để thay phương thức khôi phục hoặc quản trị quyền. Hệ thống có thể yêu cầu **step-up authentication** hoặc xác thực lại trước hành động nhạy cảm.

Khi đó cần xác định điều kiện thực tế: phương thức được chấp nhận, độ mới của xác thực, bằng chứng mà ứng dụng kiểm tra và cách liên kết kết quả với đúng phiên, chủ thể, yêu cầu.

Step-up không được dùng để cấp quyền còn thiếu. Người không có quyền sửa chính sách vẫn bị từ chối sau khi xác thực lại thành công.

## 6. Đăng ký phương thức là một thao tác bảo mật quan trọng

Nếu kẻ tấn công có thể đăng ký bộ xác thực của mình vào tài khoản nạn nhân, phương thức mạnh sẽ chứng minh quyền kiểm soát của chính kẻ tấn công ở lần đăng nhập sau.

Một luồng đăng ký cần giải quyết:

1. Chủ thể đang đăng ký là ai và bằng chứng khởi tạo tài khoản có đủ tin cậy không.
2. Phương thức mới có được liên kết với đúng tài khoản và đúng phạm vi không.
3. Bộ xác thực mới có hoàn tất bước chứng minh hoặc xác nhận mà cơ chế yêu cầu không.
4. Phiên hiện tại có đủ mức và độ mới để thay đổi phương thức không.
5. Sự kiện đăng ký có được ghi nhận và thông báo qua kênh phù hợp không.

Đặc biệt cần bảo vệ giai đoạn đăng ký lần đầu. Không chỉ bật yêu cầu MFA sau khi cho bất kỳ người có một mật khẩu bị lộ nào tự đăng ký yếu tố thứ hai mà không có kiểm soát phù hợp.

Với đổi hoặc thêm phương thức, cần tránh việc một phiên cũ hoặc một đường khôi phục yếu trở thành cách né chính sách. Thông báo sau thay đổi hữu ích cho phát hiện nhưng không thay thế kiểm tra trước khi thay đổi.

Nếu người dùng có nhiều phương thức dự phòng, phải biết phương thức nào đáp ứng điều kiện của tác vụ. Một tài khoản đăng ký khóa bảo mật nhưng luôn được phép chuyển sang phương thức yếu hơn vẫn có thể bị tấn công qua đường thay thế đó.

## 7. Khôi phục và thu hồi phải giữ được mức bảo vệ

Khôi phục tài khoản là quá trình cấp lại khả năng truy cập khi người dùng mất phương thức hiện tại. Đây là một đường nhạy cảm vì nó có thể thay đổi người kiểm soát tài khoản.

Không coi câu hỏi bí mật dễ đoán, tên người quản lý hoặc thông tin hồ sơ công khai là bằng chứng đủ mạnh chỉ vì người gọi biết chúng. Helpdesk cần một quy trình xác minh được thiết kế cho mức rủi ro của tài khoản, có trách nhiệm và bằng chứng phù hợp.

Mã khôi phục nên có độ ngẫu nhiên phù hợp, được bảo vệ khi phát hành và chỉ sử dụng theo chính sách đã định nghĩa. Với mã dùng một lần, server có thể lưu giá trị kiểm tra dạng hash thích hợp và phải tiêu thụ mã theo cách tránh chấp nhận đồng thời nhiều lần. Không để mã xuất hiện trong log hoặc nơi người khác dễ đọc.

Khi bộ xác thực bị mất, nghi bị lộ hoặc không còn thuộc người dùng, cần thu hồi phương thức tương ứng. Đổi mật khẩu không tự bảo đảm đã thu hồi mọi khóa, ứng dụng OTP, mã dự phòng hoặc phiên đang hoạt động.

Sau khôi phục, cần xem xét những gì còn có thể bị lạm dụng: phương thức cũ, phương thức mới được gắn trong thời gian nghi ngờ, phiên hiện có, token và thay đổi quyền. Cách xử lý phụ thuộc sự kiện, nhưng phải có phạm vi rõ thay vì chỉ tuyên bố tài khoản đã an toàn khi đăng nhập lại được.

## 8. Luồng đăng nhập cần bảo vệ từ đầu đến phiên

Một mô hình tổng quát:

```text
Yêu cầu truy cập
      |
      v
Xác định tài khoản, chính sách và giao dịch xác thực
      |
      v
Kiểm tra các yếu tố và bằng chứng bắt buộc
      |
      v
Đánh giá kết quả cùng điều kiện hiện tại
      |
      v
Cấp phiên hoặc token có phạm vi và vòng đời phù hợp
      |
      v
Ứng dụng tiếp tục kiểm tra quyền và quản lý phiên
```

Các kiểm soát cần đi cùng luồng này gồm bảo vệ kênh truyền, ràng buộc giao dịch, giới hạn thử đoán, xử lý bằng chứng hết hạn và chống phát lại theo cơ chế đang dùng.

Không ghép tùy ý kết quả từ hai giao dịch xác thực khác nhau. Ví dụ, việc đã kiểm tra mật khẩu ở một giao dịch không cho phép ứng dụng chấp nhận một kết quả OTP không được liên kết đúng với tài khoản và giao dịch đó.

Các lỗi đăng nhập cũng cần tránh tiết lộ thông tin tài khoản không cần thiết. Đồng thời, cơ chế chống thử đoán không nên dễ bị lợi dụng để khóa hàng loạt người dùng hợp lệ; cần kết hợp giới hạn phù hợp, phát hiện và khả năng phục hồi.

Sau thành công, phiên và token trở thành tài sản nhạy cảm. Cần quản lý thời hạn, lưu trữ, thu hồi và đánh giá lại. Một kẻ tấn công đã lấy được bearer token có thể không cần thực hiện lại các yếu tố của người dùng để thử sử dụng token đó, nên bảo vệ phiên là phần không thể bỏ qua.

## 9. Strong authentication trong SSO và liên kết danh tính

Trong SSO, ứng dụng có thể dựa vào kết quả xác thực từ nhà cung cấp danh tính được tin cậy. Điều này không có nghĩa ứng dụng có thể bỏ mọi kiểm tra vì người dùng “đã đăng nhập ở đâu đó”.

Ứng dụng cần kiểm tra bằng chứng theo giao thức và cấu hình tin cậy, bao gồm những điều kiện liên quan như bên phát hành, bên nhận dự kiến, thời hạn và ràng buộc giao dịch. Các yêu cầu cụ thể phụ thuộc loại giao thức và token đang sử dụng.

Nếu một tác vụ yêu cầu mức xác thực nhất định, ứng dụng phải hiểu cách nhà cung cấp biểu diễn và bảo đảm mức đó. Không suy mức mạnh từ một chuỗi thuộc tính tùy ý hoặc từ việc tài khoản có đăng ký MFA nhưng lần đăng nhập hiện tại chưa thực hiện yêu cầu tương ứng.

Một thuộc tính về phương thức hoặc ngữ cảnh xác thực chỉ có ý nghĩa khi các bên có quy ước đáng tin cậy về cách phát hành và diễn giải nó. Không mặc định một nhãn của bên liên kết có cùng ý nghĩa ở mọi tổ chức.

Ngoài ra, phiên SSO, phiên cục bộ và access token có thể có vòng đời khác nhau. Cần biết yêu cầu xác thực lại tác động đến đâu, kết quả mới được ứng dụng nhận thế nào và các phiên cũ được xử lý ra sao.

## 10. Danh tính workload không dùng MFA tương tác như con người

Ứng dụng, service và pipeline cũng cần xác thực mạnh theo mô hình phù hợp. Một tác vụ tự động không nên phụ thuộc việc một nhân viên bấm xác nhận điện thoại mỗi lần chạy, hoặc giữ mật khẩu và mã OTP của tài khoản cá nhân trong script.

Các cơ chế có thể gồm chứng minh quyền sở hữu khóa, chứng thư, liên kết danh tính workload hoặc thông tin xác thực ngắn hạn do hạ tầng tin cậy cấp. Việc chọn cơ chế cần gắn với cách workload được nhận diện và ranh giới tin cậy của môi trường triển khai.

Những câu hỏi quan trọng gồm:

- Khóa hoặc bằng chứng được cấp cho workload nào và dựa trên điều kiện gì?
- Workload khác có thể đọc hoặc sử dụng thông tin xác thực đó không?
- Bằng chứng dành cho service hoặc tài nguyên nào?
- Khi workload bị xóa hoặc bị xâm nhập, có thể thu hồi hoặc hạn chế truy cập ra sao?
- Quyền được cấp có đúng chức năng và phạm vi cần thiết không?

Chứng minh danh tính máy bằng mật mã không tự cấp quyền gọi mọi API. Service đích vẫn cần phân quyền cho hành động và tài nguyên cụ thể, kể cả khi hai workload nằm trong cùng mạng.

## 11. Sai lầm thường gặp và cách kiểm chứng

| Sai lầm | Hệ quả | Điều cần kiểm chứng |
| --- | --- | --- |
| Xem mật khẩu dài là đủ cho mọi tài khoản | Vẫn bị lừa lấy mật khẩu hoặc đánh cắp bằng đường khác | Phương thức đáp ứng đúng nguy cơ của tài khoản |
| Gọi hai bước nhập bí mật là MFA | Không có sự kết hợp yếu tố như mong đợi | Yếu tố nào thực sự được kiểm tra và bằng chứng nào được nhận |
| Coi mọi MFA đều chống phishing | Có thể chấp nhận mã bị chuyển tiếp | Đặc tính chống phishing của phương thức và luồng thực tế |
| Đăng ký khóa mạnh nhưng cho fallback yếu không kiểm soát | Kẻ tấn công đi qua đường thay thế | Mọi đường đăng nhập và khôi phục đều đáp ứng chính sách |
| Cho phiên bất kỳ thêm yếu tố mới | Phiên bị chiếm có thể gắn bộ xác thực của kẻ tấn công | Điều kiện và độ mới của xác thực khi đổi phương thức |
| Chỉ thu hồi mật khẩu khi thiết bị bị mất | Các phương thức hoặc phiên khác vẫn hoạt động | Phạm vi thu hồi đầy đủ theo sự kiện |
| Tin kết quả MFA do client tự khai báo | Có thể giả trạng thái xác thực | Kết quả đến từ thành phần được xác minh và đúng giao dịch |
| Cho rằng xác thực mạnh đồng nghĩa đủ quyền | Vượt ranh giới tài nguyên hoặc tác vụ | Phân quyền độc lập sau xác thực |

Các tình huống kiểm chứng nên bao gồm đăng nhập hợp lệ, bằng chứng sai hoặc hết hạn, dùng lại bằng chứng đã tiêu thụ, đổi tài khoản giữa giao dịch, đăng ký thêm phương thức từ phiên không đủ điều kiện, mất thiết bị và khôi phục tài khoản.

Cũng cần kiểm tra đường sau đăng nhập: phiên bị thu hồi, token còn hạn khi tài khoản bị khóa, hành động nhạy cảm yêu cầu xác thực lại và người dùng đủ mức xác thực nhưng thiếu quyền nghiệp vụ.

Một thiết kế xác thực mạnh đạt giá trị khi toàn bộ vòng đời duy trì được mức bảo vệ cần thiết: đăng ký đúng người, xác minh đúng bằng chứng, khôi phục có kiểm soát, thu hồi đúng phạm vi và bảo vệ quyền truy cập sau khi đăng nhập thành công.
