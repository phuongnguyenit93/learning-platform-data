# Authentication requirement

## 1. Yêu cầu xác thực là gì?

**Yêu cầu xác thực** (authentication requirement) là đặc tả về bằng chứng mà một hệ thống phải thu thập, cách kiểm tra bằng chứng đó và điều kiện chấp nhận một chủ thể đang yêu cầu truy cập. Chủ thể có thể là người dùng, tài khoản quản trị, ứng dụng hoặc một dịch vụ khác.

Sau một lần xác thực thành công, hệ thống thường cấp một phiên hoặc thông tin xác thực có thời hạn để xử lý các yêu cầu tiếp theo. Vì vậy, yêu cầu xác thực cần bao quát cả vòng đời: đăng ký phương thức, đăng nhập, xác thực bổ sung, duy trì phiên, thu hồi, mất phương thức và khôi phục tài khoản. Chỉ đặc tả biểu mẫu đăng nhập sẽ bỏ sót nhiều đường dẫn có thể dẫn đến chiếm đoạt tài khoản.

Trong thiết kế yêu cầu bảo mật, mục đích không phải viết một danh sách công nghệ như “dùng JWT, OAuth và MFA”. Mục đích là chuyển rủi ro thành các điều kiện hệ thống **phải thực hiện**, có thể liên kết với kiến trúc và kiểm chứng bằng kiểm thử hoặc bằng chứng vận hành.

Ví dụ:

> Trước khi thay đổi phương thức MFA của tài khoản quản trị, hệ thống phải yêu cầu một lần xác thực mới bằng phương thức đã đăng ký trước đó. Một phiên đăng nhập đơn thuần không đủ để hoàn tất thay đổi.

Câu này mô tả hành vi cần bảo vệ. Để trở thành yêu cầu hoàn chỉnh, nó còn cần quy định thế nào là “mới”, phương thức nào được chấp nhận, trường hợp người dùng mất phương thức và tiêu chí kiểm thử tương ứng.

### 1.1. Phân biệt các khái niệm liên quan

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Nhận diện | Chủ thể khai báo mình là ai? | Nhập tên đăng nhập hoặc gửi mã định danh ứng dụng. |
| Xác thực | Chủ thể có bằng chứng hợp lệ cho danh tính đã khai báo không? | Chứng minh quyền kiểm soát khóa riêng, mật khẩu hoặc phương thức xác thực đã đăng ký. |
| Phân quyền | Chủ thể được phép thực hiện hành động nào trên tài nguyên nào? | Người đã đăng nhập chỉ được xem hóa đơn thuộc phạm vi được cấp. |
| Xác minh danh tính thực | Tài khoản liên hệ thế nào với một cá nhân hoặc tổ chức ngoài đời? | Đối chiếu danh tính khi mở một loại tài khoản cần định danh. |

Đăng nhập thành công không tự động chứng minh người dùng có quyền quản trị. Kiểm tra địa chỉ email chỉ chứng minh quyền kiểm soát hộp thư tại thời điểm kiểm tra, không mặc nhiên chứng minh danh tính pháp lý. Việc tách các khái niệm này giúp tránh đặt sai kỳ vọng vào cơ chế xác thực.

## 2. Bắt đầu từ tài sản, chủ thể và đe dọa

Trước khi chọn phương thức xác thực, cần xác định điều gì đang được bảo vệ, ai cần truy cập và hệ thống tin cậy bên nào.

Một nhóm phát triển nên trả lời tối thiểu các câu hỏi sau:

- Có những nhóm chủ thể nào: khách, người dùng thông thường, nhân viên, quản trị viên, tác vụ tự động?
- Hành động nào gây hậu quả lớn nếu kẻ tấn công thực hiện dưới danh nghĩa người khác?
- Có ranh giới tin cậy nào giữa trình duyệt, ứng dụng di động, dịch vụ xác thực, nhà cung cấp danh tính và các dịch vụ nghiệp vụ?
- Kẻ tấn công có thể thử mật khẩu, dùng thông tin bị rò rỉ, lừa người dùng nhập mã, lấy phiên hoặc lợi dụng hỗ trợ khách hàng không?
- Khi nhà cung cấp danh tính hoặc kênh nhận mã ngừng hoạt động, hệ thống phải xử lý truy cập như thế nào?
- Người dùng mất thiết bị hoặc bị khóa tài khoản có đường khôi phục nào và đường đó có thể bị lợi dụng ra sao?

### 2.1. Tình huống xuyên suốt

Giả sử một cổng nghiệp vụ có ba nhóm tài khoản:

1. Khách hàng xem thông tin và cập nhật hồ sơ.
2. Nhân viên hỗ trợ xem dữ liệu trong phạm vi công việc.
3. Quản trị viên thay đổi chính sách bảo mật và quản lý tài khoản đặc quyền.

Các dịch vụ nội bộ cũng cần gọi API của nhau. Hệ thống sử dụng một nhà cung cấp danh tính tập trung, nhưng ứng dụng vẫn chịu trách nhiệm kiểm tra kết quả đăng nhập và quản lý phiên của chính mình.

Nhóm thiết kế nhận diện một số rủi ro:

| Mã rủi ro | Kịch bản đe dọa | Hậu quả cần ngăn chặn |
| --- | --- | --- |
| R-A01 | Dùng cặp tên đăng nhập và mật khẩu đã rò rỉ để đăng nhập hàng loạt. | Chiếm đoạt tài khoản và truy cập dữ liệu. |
| R-A02 | Lừa quản trị viên nhập mật khẩu và mã dùng một lần vào trang giả. | Truy cập chức năng đặc quyền. |
| R-A03 | Đánh cắp phiên còn hiệu lực từ thiết bị hoặc qua lỗ hổng ứng dụng. | Tiếp tục hoạt động dưới danh nghĩa nạn nhân. |
| R-A04 | Lợi dụng khôi phục tài khoản để thay phương thức xác thực của nạn nhân. | Vượt qua cơ chế đăng nhập chính. |
| R-A05 | Ứng dụng chấp nhận token dành cho hệ thống khác hoặc do bên không tin cậy phát hành. | Giả mạo danh tính qua ranh giới hệ thống. |
| R-A06 | Tấn công dịch vụ xác thực hoặc gây khóa hàng loạt tài khoản. | Người dùng hợp lệ không thể truy cập. |
| R-A07 | Lộ khóa hoặc bí mật dùng chung giữa nhiều dịch vụ. | Giả mạo workload và khó xác định nguồn truy cập. |

Đây là mô hình minh họa để xây dựng yêu cầu. Các ngưỡng thời gian và số lần xuất hiện ở phần sau là **giả định thiết kế cho tình huống này**, cần điều chỉnh theo rủi ro, trải nghiệm sử dụng và khả năng vận hành của từng hệ thống; chúng không phải các giá trị bắt buộc cho mọi sản phẩm.

## 3. Cấu trúc của một yêu cầu có thể kiểm chứng

Một yêu cầu xác thực tốt nên có đủ các thành phần sau:

| Thành phần | Nội dung cần ghi |
| --- | --- |
| Mã định danh | Mã ổn định để liên kết thiết kế, mã nguồn, kiểm thử và bằng chứng. |
| Chủ thể và phạm vi | Áp dụng cho ai, luồng nào, kênh nào và môi trường nào. |
| Điều kiện kích hoạt | Đăng nhập, đổi phương thức, yêu cầu API hoặc thực hiện thao tác nhạy cảm. |
| Hành vi bắt buộc | Điều hệ thống phải chấp nhận, từ chối, yêu cầu thêm hoặc thu hồi. |
| Giới hạn đo được | Thời gian hiệu lực, độ mới của xác thực, thời gian thu hồi hoặc ngưỡng tải. |
| Trường hợp lỗi | Kết quả khi thiếu bằng chứng, hết hạn, lỗi dịch vụ hoặc phát hiện phát lại. |
| Liên kết rủi ro | Đe dọa nào được giảm và rủi ro nào còn lại. |
| Tiêu chí chấp nhận | Đầu vào, thao tác và kết quả mong đợi có thể quan sát. |
| Trách nhiệm | Thành phần triển khai, nhóm sở hữu và bên cung cấp bằng chứng. |

Một khuôn diễn đạt có thể dùng là:

> Khi **[điều kiện]**, **[thành phần]** phải **[hành vi]** đối với **[phạm vi chủ thể]**, trong **[giới hạn]**. Nếu **[điều kiện lỗi]**, hệ thống phải **[kết quả an toàn]**. Yêu cầu được kiểm chứng bằng **[phép thử hoặc bằng chứng]**.

### 3.1. Từ mong muốn chung đến đặc tả cụ thể

| Mong muốn chưa đủ rõ | Cách đặc tả có thể kiểm chứng |
| --- | --- |
| “Đăng nhập phải an toàn.” | Chỉ tạo phiên đặc quyền sau khi xác minh phương thức đã phê duyệt cho nhóm quản trị và kiểm tra bằng chứng xác thực trong luồng hiện tại. |
| “Token phải hết hạn nhanh.” | Token đặt lại mật khẩu có hiệu lực tối đa 15 phút từ lúc phát hành, dùng một lần và không còn hợp lệ sau khi yêu cầu mới được phát hành cho cùng tài khoản. |
| “Có chống brute force.” | Sau 5 lần sai trong cửa sổ trượt 10 phút cho cùng tài khoản, trì hoãn lần kiểm tra tiếp theo ít nhất 30 giây; đồng thời áp dụng giới hạn theo nguồn và giới hạn tổng ở cửa vào. |
| “Đăng xuất phải xóa phiên.” | Sau khi máy chủ xác nhận đăng xuất, mọi phiên bản của mã phiên đó phải bị từ chối tại các điểm kiểm tra thuộc phạm vi ứng dụng trong tối đa 60 giây. |
| “Có ghi log.” | Ghi sự kiện kết quả xác thực, thời điểm, mã tương quan và định danh nội bộ phù hợp; không ghi mật khẩu, mã dùng một lần, token khôi phục hoặc cookie phiên. |

Nếu một yêu cầu chứa nhiều hành vi có tiêu chí chấp nhận độc lập, nên tách thành các mã nhỏ hơn. Chẳng hạn, “MFA, chống thử mật khẩu, thu hồi phiên và logging đầy đủ” là bốn nhóm trách nhiệm khác nhau, khó nghiệm thu như một yêu cầu duy nhất.

## 4. Đặc tả phương thức xác thực theo mức rủi ro

### 4.1. Chọn mức bảo đảm cần đạt

Không phải mọi luồng đều cần cùng một mức bảo đảm. Một phiên dùng để xem nội dung công khai khác với một phiên cho phép thay cấu hình bảo mật. Tuy nhiên, phân loại phải dựa trên tác động và mô hình đe dọa, không chỉ dựa trên tên vai trò.

Với cổng nghiệp vụ minh họa, chính sách có thể là:

| Nhóm hoặc thao tác | Yêu cầu minh họa | Mục tiêu |
| --- | --- | --- |
| Khách hàng đăng nhập thông thường | Phương thức đã đăng ký, cùng cơ chế phát hiện và hạn chế thử đăng nhập bất thường. | Giảm truy cập trái phép và lạm dụng quy mô lớn. |
| Nhân viên truy cập dữ liệu nghiệp vụ | Bắt buộc MFA theo chính sách tổ chức. | Giảm phụ thuộc vào một bí mật có thể bị lộ. |
| Quản trị viên đăng nhập | Bắt buộc phương thức có khả năng chống phishing theo thiết kế của giao thức, chẳng hạn WebAuthn cấu hình đúng. | Giảm nguy cơ sử dụng bằng chứng trên trang giả. |
| Đổi phương thức MFA hoặc email khôi phục | Xác thực mới bằng phương thức hiện có và kiểm soát riêng cho thay đổi nhạy cảm. | Ngăn phiên bị lấy cắp chiếm luôn đường khôi phục. |
| Dịch vụ gọi API nội bộ | Danh tính riêng cho workload, bằng chứng có thời hạn và kiểm tra bên phát hành, bên nhận. | Hạn chế giả mạo và giảm phạm vi ảnh hưởng khi lộ bí mật. |

Cần chỉ rõ các phương thức được chấp nhận, điều kiện đăng ký, chính sách dự phòng và ai có quyền thay đổi chính sách. Trường “đã bật MFA” trong cơ sở dữ liệu không chứng minh lần đăng nhập hiện tại đã hoàn thành MFA; quyết định phải dựa trên bằng chứng của lần xác thực hoặc phiên cụ thể.

### 4.2. MFA và khả năng chống phishing

Các yếu tố thường được phân loại thành điều người dùng biết, điều họ sở hữu và đặc điểm sinh trắc học. Hai bí mật cùng thuộc nhóm “điều người dùng biết”, như mật khẩu và câu hỏi bí mật, không tự tạo thành hai yếu tố độc lập. MFA là xác thực đa yếu tố; yêu cầu cần xác định tổ hợp phương thức nào đáp ứng chính sách.

Cần phân biệt **nhiều yếu tố** với **chống phishing**. Một mã dùng một lần có thể bổ sung yếu tố sở hữu, nhưng người dùng vẫn có thể bị lừa chuyển mã cho kẻ tấn công trong thời gian mã còn hiệu lực. Khi rủi ro yêu cầu chống phishing, đặc tả phải nêu rõ thuộc tính cần đạt và phương thức đáp ứng, thay vì chỉ ghi “bật MFA”.

Với WebAuthn hoặc passkey, yêu cầu cần làm rõ bên tin cậy, origin được phép, kiểm tra thử thách, chính sách xác minh người dùng và chính sách vòng đời credential. Origin là nguồn gốc web gồm giao thức, tên máy chủ và cổng; credential là thông tin hoặc bộ khóa được đăng ký để xác thực. Chọn công nghệ này không loại bỏ nhu cầu bảo vệ đăng ký phương thức, khôi phục tài khoản và phiên sau đăng nhập. Nếu tổ chức cần khóa không thể xuất khỏi thiết bị hoặc cần giới hạn thiết bị được quản lý, phải đặc tả riêng; không suy ra thuộc tính đó từ tên “passkey”.

### 4.3. Đăng ký và thay đổi phương thức

Phương thức xác thực chỉ đáng tin khi được gắn với đúng tài khoản qua một quy trình đáng tin.

Yêu cầu cần bao quát:

- Bằng chứng bắt buộc trước khi đăng ký phương thức đầu tiên và phương thức bổ sung.
- Ràng buộc thử thách với tài khoản, mục đích, luồng đăng ký và thời hạn.
- Hành vi khi người dùng hủy, thử thách hết hạn hoặc hai yêu cầu hoàn tất đồng thời.
- Xác thực mới trước khi xóa hoặc thay phương thức bảo vệ tài khoản.
- Thông báo về thay đổi qua kênh đã có từ trước, phù hợp chính sách dữ liệu.
- Cách xử lý tài khoản không còn phương thức đáp ứng chính sách.

Không cho phép một phiên vừa được khôi phục qua đường yếu hơn tự động cấp quyền thay mọi phương thức đặc quyền mà không qua kiểm soát tương ứng.

## 5. Yêu cầu khi hệ thống hỗ trợ mật khẩu

### 5.1. Tạo, nhập và thay mật khẩu

Đặc tả cần quy định độ dài tối thiểu, độ dài tối đa được hỗ trợ, cách xử lý ký tự và kiểm tra mật khẩu dễ đoán hoặc đã biết bị lộ. Những quyết định này cần nhất quán giữa đăng ký, đổi mật khẩu và đăng nhập.

Một chính sách minh họa có thể yêu cầu hỗ trợ mật khẩu dài ít nhất 64 ký tự, cho phép dán và sử dụng trình quản lý mật khẩu, đồng thời từ chối các giá trị nằm trong danh sách mật khẩu bị cấm của hệ thống. Đây là khả năng hỗ trợ độ dài, không có nghĩa mọi người dùng phải đặt mật khẩu tối thiểu 64 ký tự. Giới hạn tối đa và thông báo lỗi phải rõ ràng; hệ thống không được âm thầm cắt bớt mật khẩu rồi xác thực phần còn lại.

Độ dài tối thiểu và các điều kiện bổ sung phải được chốt theo phương thức đăng nhập thực tế, việc có MFA hay không và chính sách tổ chức. Không dùng yêu cầu thành phần ký tự hoặc chu kỳ đổi mật khẩu làm đại diện duy nhất cho mức an toàn. Khi có bằng chứng lộ thông tin xác thực, cần có luồng vô hiệu hóa và thiết lập lại phù hợp.

### 5.2. Lưu trữ và bảo vệ bí mật

Yêu cầu lưu trữ mật khẩu phải phân biệt với mã hóa dữ liệu thông thường:

- Không lưu mật khẩu dạng rõ hoặc dạng mã hóa có thể giải ngược để sử dụng lại.
- Lưu bộ kiểm chứng tạo bởi hàm băm mật khẩu thích ứng, với salt riêng và tham số chi phí được phê duyệt. Salt là giá trị riêng cho mỗi mật khẩu, giúp các mật khẩu giống nhau không tạo cùng một bộ kiểm chứng.
- Ghi nhận phiên bản thuật toán và tham số để hỗ trợ nâng cấp khi xác thực thành công hoặc qua quy trình chuyển đổi được thiết kế.
- Giới hạn quyền đọc bộ kiểm chứng; không để dữ liệu này xuất hiện trong log, công cụ hỗ trợ hoặc phản hồi API.
- Nếu dùng một bí mật bổ sung như pepper, quy định nơi quản lý, quyền truy cập, luân chuyển và kế hoạch khi bí mật đó bị lộ. Pepper phải được quản lý tách khỏi dữ liệu bộ kiểm chứng theo thiết kế.

Không dùng một con số chi phí băm cố định cho mọi hạ tầng. Tiêu chí cần kết nối với phép đo trên môi trường đích: độ khó chống dò ngoại tuyến, độ trễ chấp nhận được, tải đồng thời và cách ngăn kẻ tấn công biến phép băm tốn tài nguyên thành điểm gây từ chối dịch vụ.

### 5.3. Hạn chế dò mật khẩu và lộ sự tồn tại tài khoản

Biện pháp chống thử đăng nhập cần phối hợp nhiều chiều. Chỉ giới hạn theo IP có thể bỏ sót mạng bot phân tán; chỉ giới hạn theo tài khoản có thể bị lợi dụng để gây khóa tài khoản của nạn nhân.

Với ví dụ ngưỡng 5 lần sai trong 10 phút, cần chốt thêm:

1. Bộ đếm bắt đầu và kết thúc ở thời điểm nào; cửa sổ là trượt hay cố định.
2. Các nút ứng dụng chia sẻ trạng thái hạn chế ra sao.
3. Đăng nhập đúng có đặt lại bộ đếm không và trong điều kiện nào.
4. Kênh web, di động, API và luồng cũ có cùng chịu chính sách không.
5. Giới hạn theo nguồn, dải mạng, thiết bị hoặc toàn hệ thống được áp dụng ở đâu.
6. Người dùng hợp lệ có cách phục hồi truy cập nào mà không tạo đường bỏ qua kiểm soát.

Phản hồi cho tài khoản không tồn tại và mật khẩu sai cần có thông điệp công khai thống nhất, tránh để mã trạng thái hoặc cấu trúc phản hồi trực tiếp tiết lộ tài khoản. Kiểm thử cũng cần xem xét khác biệt thời gian đủ lớn và ổn định để bị khai thác; không giả định rằng chỉ đổi nội dung thông báo là đã loại bỏ mọi kênh suy đoán.

## 6. Phiên đăng nhập, token và xác thực lại

### 6.1. Xác thực thành công chưa kết thúc trách nhiệm

Sau đăng nhập, một phiên hoặc token thường trở thành bằng chứng cho các yêu cầu tiếp theo. Token là dữ liệu mang thông tin hoặc quyền sử dụng mà bên nhận kiểm tra theo giao thức. Nếu bằng chứng đó bị lấy cắp, kẻ tấn công có thể hoạt động mà không cần biết mật khẩu. Vì vậy, quản lý phiên là một phần trực tiếp của yêu cầu xác thực.

Yêu cầu cần xác định:

- Mã phiên hoặc token được tạo bằng nguồn ngẫu nhiên phù hợp và có mức khó đoán được phê duyệt đối với phần bí mật; nếu token được ký, phải có yêu cầu riêng về khóa và xác minh chữ ký.
- Thời điểm tạo mới hoặc đổi mã phiên, bao gồm khi đăng nhập và khi tăng mức đặc quyền.
- Cách truyền và lưu trữ trên từng loại client; bằng chứng xác thực không được truyền qua kết nối không được bảo vệ. Phải xác định các chặng TLS, điểm kết thúc TLS và phạm vi tin cậy sau điểm đó.
- Điều kiện hết hạn do không hoạt động và thời hạn tuyệt đối.
- Khả năng xem, kết thúc từng phiên hoặc toàn bộ phiên của tài khoản.
- Thời gian tối đa để việc thu hồi có hiệu lực ở mọi thành phần liên quan.
- Hành vi khi tài khoản bị vô hiệu hóa, nghi ngờ bị chiếm đoạt hoặc thay đổi phương thức bảo mật.

Với cookie phiên trên trình duyệt, cần đặc tả phạm vi domain/path, `Secure`, `HttpOnly` và chính sách `SameSite` phù hợp với luồng ứng dụng. Các thuộc tính này phải đi cùng phòng vệ chống yêu cầu giả mạo qua trình duyệt (CSRF) và giảm nguy cơ mã độc được chèn vào trang (XSS). `HttpOnly` hạn chế việc JavaScript đọc cookie nhưng không ngăn mọi hành động trái phép qua trình duyệt đang bị khai thác.

### 6.2. Ví dụ chính sách phiên

| Loại phiên | Hết hạn khi không hoạt động | Thời hạn tuyệt đối | Yêu cầu cho thao tác nhạy cảm |
| --- | --- | --- | --- |
| Khách hàng | 30 phút | 12 giờ | Yêu cầu xác thực mới theo loại thao tác. |
| Nhân viên | 15 phút | 8 giờ | Xác thực bổ sung khi thay đổi yếu tố bảo mật. |
| Quản trị | 15 phút | 8 giờ | Bằng chứng xác thực mới không quá 5 phút trước khi đổi cấu hình bảo mật. |

Phải định nghĩa “hoạt động” là gì. Một tác vụ gọi nền hoặc làm mới token không nên tự động được coi là hoạt động chủ động của người dùng nếu mục tiêu của chính sách là kết thúc phiên bị bỏ quên. Việc gia hạn kỹ thuật cũng không được âm thầm đặt lại thời hạn tuyệt đối.

### 6.3. Thu hồi và giới hạn của token tự chứa

Xóa token khỏi trình duyệt chỉ kết thúc khả năng sử dụng token ở vị trí đó; một bản sao đã bị lấy cắp có thể vẫn được chấp nhận phía máy chủ.

Nếu hệ thống dùng token tự chứa và chỉ kiểm tra chữ ký, token có thể tiếp tục hợp lệ đến lúc hết hạn. Một yêu cầu như “thu hồi trong 60 giây” phải có cơ chế kiến trúc đáp ứng: tra cứu trạng thái, danh sách thu hồi, phiên bản phiên, kiểm tra tập trung hoặc thời hạn token phù hợp. Việc chọn cơ chế là quyết định thiết kế; khả năng đáp ứng giới hạn là điều phải được kiểm chứng.

Với refresh token, tức token dùng để xin bằng chứng truy cập mới, cần nêu thời hạn, phạm vi, nơi lưu và chính sách luân chuyển. Nếu chọn luân chuyển theo mỗi lần sử dụng, phải đặc tả xử lý token cũ bị dùng lại, quan hệ giữa các token trong cùng chuỗi và các yêu cầu đồng thời hợp lệ. Chính sách phát hiện phát lại thiếu quy tắc đồng thời rõ ràng có thể tự đăng xuất người dùng hoặc để lọt cuộc tấn công.

### 6.4. Ràng buộc xác thực lại với thao tác

Xác thực lại cần gắn với đúng tài khoản, phiên và hành động đang yêu cầu. Một cờ chung như `recentlyAuthenticated=true` do client gửi không phải bằng chứng tin cậy.

Ví dụ: trước khi đổi email khôi phục, máy chủ yêu cầu bằng chứng xác thực mới không quá 5 phút và phát hành quyền tiếp tục ngắn hạn cho đúng thao tác đó. Bằng chứng dùng để đổi email không tự cho phép xóa MFA hoặc tạo thông tin xác thực dịch vụ.

Nếu hành động có tham số quan trọng, cần xác định bằng chứng xác nhận ràng buộc với tham số nào và xử lý ra sao khi tham số thay đổi. Mục tiêu là tránh người dùng xác nhận một việc nhưng hệ thống lại thực hiện một việc khác.

## 7. Khôi phục tài khoản và đường dự phòng

### 7.1. Khôi phục là một luồng xác thực thay thế

Đường đăng nhập chính có thể mạnh nhưng toàn bộ tài khoản vẫn bị chiếm nếu chức năng “quên mật khẩu”, mất MFA hoặc hỗ trợ khách hàng dễ bị lợi dụng.

Cần đặc tả ít nhất:

- Ai được bắt đầu quy trình và bằng chứng nào đủ để hoàn tất.
- Kênh khôi phục nào được chấp nhận cho từng nhóm tài khoản.
- Thời hạn, số lần dùng và cách vô hiệu hóa token hoặc mã khôi phục.
- Giới hạn tần suất yêu cầu và xác minh, kể cả yêu cầu gửi thông báo.
- Thay đổi nào buộc thu hồi phiên hoặc credential cũ.
- Phương án cho mất cả thiết bị và kênh khôi phục.
- Quy trình đặc biệt cho tài khoản đặc quyền và người có quyền phê duyệt.

Câu hỏi bí mật dựa trên thông tin cá nhân dễ đoán hoặc dễ tìm kiếm không nên được coi là bằng chứng mạnh. Một yêu cầu hỗ trợ cũng không được tự động bỏ qua kiểm soát chỉ vì người yêu cầu biết tên, số điện thoại hoặc chức danh của nạn nhân.

### 7.2. Ví dụ token đặt lại mật khẩu

Một đặc tả có thể yêu cầu:

> Token đặt lại mật khẩu phải khó đoán, gắn với một tài khoản và mục đích đặt lại, có hiệu lực tối đa 15 phút, chỉ được dùng thành công một lần và bị vô hiệu hóa khi phát hành yêu cầu đặt lại mới cho cùng tài khoản. Máy chủ chỉ lưu bộ kiểm chứng token thay vì token dạng rõ. Việc tiêu thụ token và cập nhật mật khẩu phải bảo đảm không thể có hai lần hoàn tất từ cùng token khi xử lý đồng thời.

Các điều kiện bổ sung trong tình huống minh họa:

- API bắt đầu khôi phục trả thông báo công khai thống nhất, dù tài khoản có tồn tại hay không.
- Trang nhận token không đưa token vào log ứng dụng, công cụ phân tích hoặc yêu cầu tài nguyên bên thứ ba; URL và chính sách referrer được thiết kế để hạn chế rò rỉ.
- Mở liên kết bằng yêu cầu đọc không tự tiêu thụ token; hành động đặt mật khẩu phải được xác nhận rõ ràng để tránh trình quét liên kết vô tình dùng mất token.
- Sau đặt lại mật khẩu, thu hồi các phiên hiện có trong tối đa 60 giây và yêu cầu đăng nhập lại.
- Đặt lại mật khẩu không tự tắt MFA. Mất MFA đi qua quy trình riêng có mức bảo đảm phù hợp.
- Thông báo thay đổi được gửi tới kênh liên hệ đã xác minh từ trước theo chính sách tổ chức.

Mã dự phòng nếu được hỗ trợ cũng phải có quy tắc dùng một lần, lưu bộ kiểm chứng, hạn chế thử và vô hiệu hóa bộ mã cũ khi tạo bộ mới.

### 7.3. Tài khoản khẩn cấp

Nếu vận hành cần tài khoản truy cập khẩn cấp khi nhà cung cấp danh tính gặp sự cố, đây phải là ngoại lệ được thiết kế trước: danh tính riêng, phạm vi tối thiểu, lưu giữ credential có kiểm soát, phê duyệt sử dụng, giám sát và thay đổi credential sau sử dụng theo chính sách. Không biến tài khoản khẩn cấp thành mật khẩu dùng chung thường ngày hoặc cơ chế tự động mở quyền khi xác thực gặp lỗi.

## 8. Liên kết danh tính và xác thực giữa các hệ thống

### 8.1. Đăng nhập liên kết

Khi dùng nhà cung cấp danh tính bên ngoài, cần phân định rõ trách nhiệm. Nhà cung cấp xác thực người dùng; ứng dụng tiếp nhận vẫn phải kiểm tra giao thức, kết quả và điều kiện tạo phiên.

Nếu chọn OpenID Connect (OIDC), giao thức cung cấp lớp danh tính trên OAuth, cần đặc tả ít nhất:

- Danh sách bên phát hành được tin cậy và cách chọn cấu hình tin cậy.
- Cách kiểm tra chữ ký, thuật toán được phép, khóa, bên nhận và thời hạn.
- Kiểm tra `nonce` khi luồng áp dụng yêu cầu đó; ràng buộc phản hồi với giao dịch đăng nhập đã khởi tạo, bao gồm `state` theo thiết kế luồng.
- Đăng ký và kiểm tra redirect URI, tức địa chỉ nhận kết quả chuyển hướng; sử dụng PKCE cho luồng Authorization Code theo chính sách đã chọn. PKCE ràng buộc việc đổi mã ủy quyền với bên đã khởi tạo luồng bằng một bí mật tạm thời.
- Cách ánh xạ định danh chủ thể vào tài khoản nội bộ; không tự gộp tài khoản chỉ vì email trùng nhau.
- Bằng chứng nào cho thấy phương thức hoặc mức xác thực đáp ứng chính sách, và các giá trị nào được chấp nhận từ nhà cung cấp nào.
- Hành vi khi khóa luân chuyển, đồng hồ lệch trong giới hạn cho phép, nhà cung cấp ngừng hoạt động hoặc tài khoản bị vô hiệu hóa.

Trong thiết kế OIDC, ID token phục vụ thông tin về lần xác thực cho client; access token phục vụ truy cập tài nguyên theo giao thức và phạm vi được cấp. Không mặc định chấp nhận bất kỳ token nào có chữ ký hợp lệ cho mọi mục đích. OAuth tự nó là khuôn khổ ủy quyền; việc đăng nhập cần giao thức và kiểm tra danh tính được xác định rõ.

Một token hợp lệ về chữ ký vẫn phải bị từ chối nếu sai bên phát hành, sai bên nhận, sai loại sử dụng hoặc không đáp ứng chính sách của ứng dụng.

### 8.2. Danh tính dịch vụ và workload

Workload là đơn vị phần mềm đang thực thi, chẳng hạn một dịch vụ hoặc một tác vụ xử lý nền. Đối với giao tiếp máy với máy, yêu cầu phải nêu danh tính mà credential đại diện: ứng dụng, workload, môi trường hay một phiên chạy cụ thể. Không dùng một tài khoản người dùng dùng chung cho mọi tác vụ tự động.

Ví dụ yêu cầu:

> Mỗi workload sản xuất phải có danh tính riêng. API chỉ chấp nhận bằng chứng được phát hành cho đúng bên nhận và còn hiệu lực. Credential phát triển không được xác thực thành danh tính sản xuất. Khi workload bị vô hiệu hóa, mọi lần xác thực mới phải bị từ chối ngay và các bằng chứng đã phát hành phải mất khả năng truy cập trong giới hạn thu hồi đã công bố.

Thiết kế có thể chọn mTLS, tức TLS xác thực hai chiều bằng chứng thư, token ngắn hạn hoặc cơ chế nhận diện workload của hạ tầng. Cần đặc tả việc cấp phát, lưu giữ khóa, luân chuyển, thu hồi và hành vi khi cơ chế cấp credential gặp lỗi. Quyền mà workload nhận được sau xác thực thuộc yêu cầu phân quyền riêng, có liên kết với cùng danh tính.

## 9. Logging, dữ liệu và hành vi khi sự cố

### 9.1. Bằng chứng quan sát được

Các sự kiện cần xem xét gồm đăng nhập thành công hoặc thất bại, kích hoạt giới hạn thử, yêu cầu xác thực bổ sung, đăng ký hoặc xóa phương thức, khôi phục, tạo phiên, thu hồi và sử dụng tài khoản khẩn cấp.

Mỗi loại sự kiện cần có lược đồ rõ ràng: thời điểm, loại sự kiện, kết quả, mã lý do nội bộ, mã tương quan, thành phần phát sinh và định danh tài khoản nội bộ khi đã xác định được. Thông tin nguồn hoặc thiết bị chỉ được thu thập và lưu giữ theo mục đích và chính sách dữ liệu đã phê duyệt.

Không ghi mật khẩu, khóa riêng, mã dùng một lần, token khôi phục, access token, refresh token hoặc cookie phiên. Nếu cần liên kết sự kiện theo phiên, dùng định danh quan sát riêng không có khả năng xác thực, thay vì ghi trực tiếp bí mật phiên.

Yêu cầu logging phải nêu cả quyền đọc, thời gian lưu, tính toàn vẹn và xử lý dữ liệu người dùng có thể kiểm soát để tránh chèn nội dung giả vào log. Việc ghi quá nhiều dữ liệu mà thiếu bảo vệ có thể tạo thêm nguồn lộ thông tin xác thực.

### 9.2. Chỉ số và cảnh báo

Các chỉ số hữu ích gồm tỷ lệ thất bại theo nhóm luồng, số lần kích hoạt giới hạn, tỷ lệ hoàn thành MFA, số lần khôi phục, độ trễ đăng nhập và thời gian thu hồi thực tế.

Một yêu cầu cảnh báo minh họa:

> Khi cùng một tài khoản quản trị có ít nhất 20 lần xác thực thất bại trong cửa sổ trượt 5 phút, hệ thống giám sát phải tạo cảnh báo trong tối đa 2 phút sau khi đạt ngưỡng. Cảnh báo chứa mã tài khoản nội bộ, thời gian và mã tương quan, không chứa bí mật xác thực.

Cần quy định cách gộp cảnh báo, xử lý sự kiện trùng và người chịu trách nhiệm phản ứng. Ngưỡng cảnh báo hỗ trợ vận hành; nó không thay thế cơ chế ngăn chặn trong luồng đăng nhập.

### 9.3. Sẵn sàng nhưng không tự hạ chính sách

Khi không thể kiểm chứng bằng chứng do lỗi phụ thuộc, hệ thống không được coi lỗi đó là xác thực thành công. Điều này không đồng nghĩa mọi phiên hiện hữu phải bị ngắt ngay: cần quyết định rõ điều gì còn xác minh được bằng thông tin tin cậy đang có, dữ liệu nào được phép lưu đệm và thời hạn của dữ liệu đó.

Ví dụ:

- Không cho đăng nhập quản trị bằng mật khẩu đơn thuần khi dịch vụ MFA ngừng hoạt động.
- Chỉ tiếp tục chấp nhận token với khóa tin cậy đã có trong thời hạn và điều kiện lưu đệm đã phê duyệt; không tự tải khóa từ địa chỉ tùy ý do token cung cấp.
- Nếu kho trạng thái thu hồi không truy cập được, áp dụng chính sách đã chốt theo loại phiên; không để mỗi dịch vụ tự chọn hành vi khác nhau.
- Đặt timeout, giới hạn hàng đợi và ngân sách tài nguyên cho luồng xác thực để sự cố phụ thuộc không kéo sập toàn bộ ứng dụng.

Yêu cầu hiệu năng cũng phải đo được. Chẳng hạn, thời gian xử lý phía hệ thống ở phân vị 95 không vượt 2 giây tại 100 yêu cầu đăng nhập mỗi giây trên cấu hình nghiệm thu đã nêu, không tính thời gian người dùng nhập MFA. Phân vị 95 nghĩa là ít nhất 95% số lần đo không vượt giá trị đó. Kịch bản tải phải bao gồm đăng nhập sai và hoạt động hạn chế tần suất, thay vì chỉ đo đường thành công.

## 10. Bộ yêu cầu minh họa liên kết với rủi ro

Bảng dưới đây là bộ yêu cầu rút gọn cho cổng nghiệp vụ giả định. Các chính sách và ngưỡng ở trên được dùng làm nền để mỗi dòng có thể truy vết. Đây là khung minh họa; các tham số còn dẫn chiếu chính sách phải được chốt trước khi dùng làm hồ sơ nghiệm thu thực tế.

| Mã yêu cầu | Hành vi bắt buộc | Rủi ro | Chủ thể triển khai | Bằng chứng chấp nhận chính |
| --- | --- | --- | --- | --- |
| AUTH-01 | Chỉ tạo phiên quản trị sau khi xác minh phương thức chống phishing đã phê duyệt; đường đăng nhập và dự phòng đều phải tuân thủ chính sách tương ứng. | R-A01, R-A02 | Nhóm danh tính và ứng dụng quản trị. | Đường thiếu phương thức bị từ chối; bằng chứng đúng chỉ được chấp nhận cho đúng giao dịch. |
| AUTH-02 | Mọi kênh đăng nhập bằng mật khẩu áp dụng trì hoãn ít nhất 30 giây sau 5 lần sai trong cửa sổ trượt 10 phút, cùng giới hạn nguồn và tổng đã định nghĩa. | R-A01, R-A06 | Cổng truy cập và dịch vụ xác thực. | Thử phân tán qua nhiều nút vẫn chịu cùng bộ đếm; kiểm thử nêu rõ giới hạn của nhận diện nguồn. |
| AUTH-03 | Đổi cấu hình bảo mật cần xác thực mới không quá 5 phút bằng phương thức đáp ứng chính sách; bằng chứng gắn với phiên và thao tác. | R-A03, R-A04 | Backend nghiệp vụ và dịch vụ xác thực. | Phiên còn hiệu lực nhưng bằng chứng quá cũ không đủ để thực hiện thao tác. |
| AUTH-04 | Mã phiên bị thu hồi phải mất hiệu lực ở mọi điểm kiểm tra của ứng dụng trong tối đa 60 giây. | R-A03 | Nhóm nền tảng phiên và các API. | Phát lại bản sao mã phiên sau hạn thu hồi bị từ chối ở tất cả nút kiểm thử. |
| AUTH-05 | Token đặt lại mật khẩu có hạn 15 phút, một lần dùng, vô hiệu khi phát hành token mới và không tắt MFA. | R-A04 | Dịch vụ tài khoản. | Kiểm thử hết hạn, token cũ, dùng lại và hai lần hoàn tất đồng thời. |
| AUTH-06 | Chỉ chấp nhận kết quả đăng nhập liên kết đúng bên phát hành, bên nhận, thời hạn, giao dịch và chính sách phương thức. | R-A05 | Bộ tích hợp danh tính. | Từ chối token có chữ ký đúng nhưng sai bên nhận hoặc sai giao dịch. |
| AUTH-07 | Ghi sự kiện xác thực và thay đổi phương thức theo lược đồ; loại bỏ bí mật trước mọi đích log đã đăng ký. | R-A01–R-A05 | Nhóm xác thực và quan sát hệ thống. | Kiểm tra các đích log của cả đường thành công và thất bại không chứa bí mật thử nghiệm. |
| AUTH-08 | Lỗi nhà cung cấp MFA không được làm đăng nhập quản trị hạ xuống mật khẩu đơn yếu tố. | R-A02, R-A06 | Nhóm danh tính và vận hành. | Mô phỏng lỗi phụ thuộc vẫn từ chối tạo phiên không đáp ứng chính sách. |
| AUTH-09 | Mỗi workload có danh tính riêng theo môi trường, kiểm tra bên nhận và có cơ chế luân chuyển, thu hồi được xác định. | R-A07 | Nhóm nền tảng và chủ dịch vụ. | Credential sai môi trường hoặc sai bên nhận bị từ chối; đo được thời gian thu hồi. |

Mã yêu cầu phải xuất hiện trong thiết kế tương ứng và liên kết với các ca kiểm thử. Nếu thay chính sách phiên hoặc đường khôi phục, nhóm phải xác định các mã yêu cầu và bằng chứng nào bị ảnh hưởng.

## 11. Ví dụ đặc tả đầy đủ cho một yêu cầu

### AUTH-03 — Xác thực mới trước khi đổi phương thức bảo mật

**Mục tiêu:** giảm khả năng một phiên bị lấy cắp được sử dụng để chiếm quyền kiểm soát lâu dài đối với tài khoản.

**Phạm vi:** API đổi email khôi phục, đăng ký hoặc xóa MFA và thay đổi cấu hình bảo mật quản trị. Quy trình mất toàn bộ phương thức thuộc luồng khôi phục riêng, không được đánh dấu hoàn tất bằng cùng quy tắc này.

**Điều kiện trước:** người dùng đã có phiên hợp lệ; phía máy chủ xác định được tài khoản, loại phiên và chính sách phương thức áp dụng.

**Hành vi bắt buộc:**

1. Máy chủ phải xác định thời điểm hoàn tất xác thực gần nhất từ nguồn tin cậy, không nhận thời điểm do client tự khai báo.
2. Bằng chứng phải không quá 5 phút tại thời điểm phê duyệt thay đổi và phải đáp ứng chính sách của thao tác. Bằng chứng trong tương lai vượt dung sai đồng hồ đã phê duyệt phải bị từ chối.
3. Khi chưa có bằng chứng phù hợp, API chưa được thay đổi trạng thái bảo mật và phải yêu cầu xác thực bổ sung.
4. Thử thách bổ sung phải có thời hạn tối đa 5 phút, gắn với tài khoản, phiên và loại thao tác. Kết quả thành công cấp quyền tiếp tục một lần cho đúng thao tác trong tối đa 2 phút và không vượt thời hạn độ mới của bằng chứng xác thực.
5. Máy chủ phải kiểm tra lại các điều kiện tại thời điểm thực hiện thay đổi, xử lý tiêu thụ quyền tiếp tục và cập nhật trạng thái theo cách không cho phép sử dụng thành công hai lần.
6. Khi thành công hoặc thất bại, ghi sự kiện theo chính sách logging; không ghi nội dung bằng chứng bí mật.
7. Khi lỗi phụ thuộc hoặc không đủ bằng chứng, giữ nguyên trạng thái bảo mật và trả kết quả thất bại có thể xử lý được cho client.

**Tiêu chí chấp nhận:**

| Trường hợp | Thiết lập và thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Bằng chứng phù hợp | Cùng tài khoản và phiên, đúng thao tác, xác thực 2 phút trước. | Cho phép hoàn tất một lần nếu các điều kiện khác đều đạt. |
| Bằng chứng quá cũ | Xác thực đã quá 5 phút tại thời điểm phê duyệt. | Không đổi dữ liệu; yêu cầu xác thực mới. |
| Sai phiên | Dùng bằng chứng của phiên A để thay đổi qua phiên B. | Từ chối, không sửa trạng thái. |
| Sai thao tác | Dùng quyền tiếp tục đổi email để xóa MFA. | Từ chối, yêu cầu bằng chứng cho đúng thao tác. |
| Phát lại | Dùng lại quyền tiếp tục sau một lần hoàn tất. | Từ chối lần tiếp theo. |
| Yêu cầu đồng thời | Gửi hai yêu cầu thay đổi với cùng quyền tiếp tục. | Tối đa một yêu cầu được phép hoàn tất bằng quyền đó. |
| Đợi quá hạn | Xác thực lúc phút 0, cấp quyền tiếp tục ở phút 4, thực hiện sau phút 5. | Từ chối do bằng chứng không còn đủ mới, dù quyền tiếp tục chưa đạt giới hạn 2 phút riêng của nó. |
| Lỗi phụ thuộc | Ngắt dịch vụ xác minh trong luồng bổ sung. | Không thay đổi dữ liệu và không tự chuyển sang phương thức yếu hơn. |

**Bằng chứng nghiệm thu:** kết quả kiểm thử API, kiểm thử đồng thời, kiểm thử lỗi phụ thuộc và mẫu sự kiện đã loại bỏ bí mật. Chủ sở hữu yêu cầu là nhóm bảo mật sản phẩm; nhóm tài khoản triển khai, nhóm kiểm thử xác minh và nhóm vận hành theo dõi lỗi thực tế.

## 12. Liên kết yêu cầu với kiến trúc và kiểm thử trong vòng đời phát triển

### 12.1. Phân bổ trách nhiệm

Một yêu cầu có thể cần nhiều thành phần cùng thực hiện. Ví dụ, giới hạn thử đăng nhập có thể bắt đầu ở cổng truy cập, dùng trạng thái tại dịch vụ xác thực và sinh cảnh báo ở hệ thống giám sát. Thiếu một chủ sở hữu đầu cuối dễ tạo ra khoảng trống giữa các nhóm.

Với mỗi yêu cầu, cần lưu được chuỗi liên kết:

```text
Tài sản và mục tiêu bảo vệ
    -> Kịch bản đe dọa / rủi ro
    -> Mã yêu cầu xác thực
    -> Quyết định và thành phần kiến trúc
    -> Ca kiểm thử + bằng chứng
    -> Chỉ số vận hành + người xử lý
```

Ví dụ cho AUTH-04:

```text
R-A03: Bản sao phiên bị đánh cắp
    -> AUTH-04: Thu hồi có hiệu lực trong tối đa 60 giây
    -> Kho trạng thái phiên + cơ chế truyền thay đổi + kiểm tra tại API
    -> Kiểm thử phát lại trên nhiều nút, kể cả nút có dữ liệu lưu đệm
    -> Đo độ trễ thu hồi và cảnh báo khi vượt ngưỡng
```

Nếu kiến trúc không có cách kiểm tra thu hồi trước khi token hết hạn, nhóm phải thay thiết kế hoặc đưa giới hạn thực tế ra quyết định chấp nhận rủi ro. Không giữ nguyên lời hứa “60 giây” trong tài liệu khi hệ thống không thể thực hiện.

### 12.2. Các lớp bằng chứng

| Lớp kiểm chứng | Ví dụ kiểm tra | Điều cần lưu ý |
| --- | --- | --- |
| Cấu hình và thiết kế | Phương thức được phép, thời hạn phiên, nguồn khóa, phạm vi cookie. | Cần kiểm tra cấu hình thực sự được triển khai. |
| Đơn vị | Tính tuổi bằng chứng, quy tắc hết hạn, ánh xạ chính sách phương thức. | Không đủ để chứng minh hành vi qua nhiều thành phần. |
| Tích hợp | Callback danh tính, tạo phiên, thay mật khẩu, thu hồi. | Bao gồm dữ liệu sai và phụ thuộc không đáng tin. |
| Đầu cuối | Web, di động, API, liên kết khôi phục, thao tác nhạy cảm. | Bao phủ mọi đường truy cập còn hoạt động. |
| Đồng thời và phân tán | Dùng token một lần đồng thời, bộ đếm qua nhiều nút, độ trễ thu hồi. | Kiểm tra tính nguyên tử và ảnh hưởng của lưu đệm. |
| Lỗi và tải | MFA timeout, kho phiên lỗi, đăng nhập sai với tải lớn. | Xác minh hành vi lỗi và ngân sách tài nguyên. |
| Vận hành | Cảnh báo, thiếu sự kiện, khóa luân chuyển, tài khoản khẩn cấp. | Dùng dữ liệu thử nghiệm, có bằng chứng phản ứng và phục hồi. |

Các ca thất bại thường cung cấp bằng chứng quan trọng hơn việc chỉ chứng minh người dùng đúng có thể đăng nhập. Ví dụ, token đúng chữ ký nhưng sai bên nhận là ca bắt buộc xem xét khi rủi ro nằm ở ranh giới tin cậy.

### 12.3. Duy trì yêu cầu sau khi phát hành

Yêu cầu xác thực cần được xem lại khi thêm kênh truy cập, đổi nhà cung cấp danh tính, thay chính sách MFA, đưa dữ liệu nhạy cảm mới vào hệ thống hoặc xuất hiện sự cố chiếm đoạt tài khoản.

Mỗi ngoại lệ cần có phạm vi, người chịu trách nhiệm, rủi ro còn lại, biện pháp bù, ngày hết hạn và cách loại bỏ. Một ngoại lệ không có hạn kết thúc dễ trở thành đường đăng nhập yếu tồn tại lâu dài.

Khi thay đổi ngưỡng hoặc phương thức, phải cập nhật cả tài liệu, cấu hình triển khai, tiêu chí kiểm thử và khả năng quan sát. Bằng chứng kiểm thử của phiên bản cũ không tự chứng minh yêu cầu vẫn được đáp ứng sau thay đổi.

## 13. Những lỗi đặc tả thường gặp

| Lỗi | Vì sao gây vấn đề | Cách sửa |
| --- | --- | --- |
| Chỉ ghi “dùng JWT” hoặc “dùng OAuth”. | Tên công nghệ không mô tả chủ thể, bên tin cậy, thu hồi và điều kiện từ chối. | Viết các thuộc tính và hành vi cần đạt, rồi liên kết với lựa chọn kiến trúc. |
| Chỉ bảo vệ đăng nhập chính. | Luồng cũ, đặt lại mật khẩu hoặc hỗ trợ có thể trở thành đường bỏ qua. | Liệt kê toàn bộ vòng đời và các đường dự phòng. |
| Xem MFA nào cũng chống phishing. | Bằng chứng có thể bị chuyển tiếp trong một cuộc lừa đảo trực tiếp. | Nêu rõ mô hình đe dọa và thuộc tính của phương thức được phép. |
| Dùng trạng thái tài khoản thay bằng chứng của phiên. | Tài khoản đã đăng ký MFA nhưng phiên hiện tại có thể chưa hoàn thành MFA. | Kiểm tra ngữ cảnh xác thực của phiên và mức đáp ứng chính sách. |
| Khóa tài khoản vô hạn sau vài lần sai. | Kẻ tấn công có thể gây mất truy cập cho nạn nhân. | Đặc tả trì hoãn, giới hạn nhiều chiều và đường phục hồi có kiểm soát. |
| Coi đăng xuất là xóa dữ liệu phía client. | Bản sao phiên bị đánh cắp vẫn có thể hoạt động. | Quy định thu hồi phía máy chủ và thời gian lan truyền. |
| Chỉ kiểm tra token có chữ ký đúng. | Có thể chấp nhận token sai bên nhận, sai loại hoặc sai giao dịch. | Kiểm tra toàn bộ ngữ cảnh tin cậy theo giao thức và chính sách. |
| Đặt lại mật khẩu đồng thời tắt MFA. | Kênh khôi phục yếu có thể vô hiệu mọi lớp bảo vệ khác. | Tách quy trình và yêu cầu bằng chứng tương xứng. |
| Ghi bí mật vào log để dễ xử lý lỗi. | Người có quyền đọc log có thể lấy khả năng đăng nhập. | Thiết kế sự kiện quan sát riêng và kiểm tra các đích log. |
| Không chốt hành vi khi phụ thuộc lỗi. | Các thành phần có thể tự hạ chính sách hoặc chặn sai người dùng. | Đặc tả từng trường hợp lỗi và kiểm chứng bằng mô phỏng. |

## 14. Bài tập áp dụng

Một nhóm đưa ra yêu cầu: “Hệ thống phải hỗ trợ đăng nhập an toàn, có MFA, tự hết phiên và cho phép khôi phục khi mất điện thoại.”

Hãy chuyển yêu cầu này thành một bộ đặc tả có thể nghiệm thu:

1. Chọn ít nhất hai nhóm chủ thể và ba hành động có mức tác động khác nhau.
2. Xác định ít nhất bốn đe dọa, bao gồm chiếm phiên và lạm dụng khôi phục.
3. Viết các yêu cầu có mã riêng cho phương thức đăng nhập, đăng ký MFA, giới hạn thử, phiên, xác thực lại và mất MFA.
4. Với mỗi yêu cầu, nêu phạm vi, điều kiện từ chối, giới hạn đo được và thành phần chịu trách nhiệm.
5. Thiết kế ít nhất một ca thành công, một ca thất bại và một ca biên hoặc đồng thời cho từng luồng quan trọng.
6. Nêu bằng chứng cho thời gian thu hồi phiên và hành vi khi nhà cung cấp danh tính ngừng hoạt động.

Ví dụ một phần đáp án cho trường hợp mất điện thoại: phiên đang mở không tự đủ để xóa MFA; người dùng phải chứng minh bằng phương thức dự phòng đã đăng ký hoặc qua quy trình hỗ trợ được phê duyệt. Sau khôi phục, credential đã mất phải bị thu hồi, việc đăng ký phương thức mới phải có bằng chứng và mọi thay đổi phải được ghi nhận, thông báo theo chính sách. Những chi tiết như thời gian chờ, người phê duyệt và hiệu lực phiên sau khôi phục phải được chốt thành yêu cầu riêng.

Một bộ yêu cầu đạt mục tiêu khi người thiết kế biết cần xây gì, người kiểm thử biết phải thử gì và người vận hành biết dấu hiệu nào cho thấy kiểm soát không còn hoạt động như đã cam kết. Đó là cách chuyển mục tiêu bảo vệ danh tính thành các cam kết bảo mật cụ thể trong vòng đời phát triển.
