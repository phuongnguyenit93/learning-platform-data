# Automated recovery abuse

Luồng khôi phục tài khoản thường phải tiếp nhận yêu cầu từ người chưa đăng nhập hoặc vừa mất phương thức xác thực. Đây là điều kiện cần để hỗ trợ người quên mật khẩu, mất điện thoại MFA hoặc mất thiết bị chứa passkey. Nhưng chính điểm vào công khai đó cũng cho phép phần mềm tự động tạo lượng lớn yêu cầu với chi phí thấp.

**Automated recovery abuse** là việc dùng tự động hóa để khai thác luồng khôi phục nhằm gây hại: dò tài khoản, gửi thư hoặc SMS hàng loạt, thử mã, chiếm tài nguyên, làm tê liệt hỗ trợ hoặc tìm đường thay phương thức xác thực trái phép.

Mục tiêu thiết kế là hạn chế hành vi gây hại và chi phí mà nó tạo ra, đồng thời giữ cho chủ tài khoản có một con đường khôi phục phù hợp. Một hệ thống chặn được bot nhưng khiến người bị mất thiết bị không thể lấy lại tài khoản vẫn chưa đáp ứng mục đích của luồng khôi phục.

## 1. Tự động hóa không đồng nghĩa với lạm dụng

Không phải mọi request lặp hoặc có vẻ tự động đều độc hại. Người dùng có thể nhấn gửi lại vì email đến chậm; ứng dụng có thể retry khi mất mạng; nhiều người có thể cùng truy cập qua mạng công ty. Công cụ hỗ trợ tiếp cận cũng có thể tương tác khác với thao tác chuột thông thường.

Cần đánh giá hành vi trong ngữ cảnh:

| Hành vi quan sát | Khả năng gây hại | Điều cần xem thêm |
| --- | --- | --- |
| Nhiều yêu cầu cho một email | Làm ngập hộp thư của nạn nhân | Nhịp gửi thực tế, lịch sử giao dịch và việc retry |
| Nhiều email từ một nguồn | Dò danh sách tài khoản | Phạm vi định danh được thử và kết quả xử lý |
| Một tài khoản bị nhắm từ nhiều nguồn | Lạm dụng phân tán | Tổng lưu lượng theo tài khoản hoặc đích nhận |
| Nhiều lần nhập sai mã | Đoán bằng chứng | Tổng số lần thử, không chỉ số request tại một instance |
| Nhiều yêu cầu hỗ trợ cùng nội dung | Làm đầy hàng chờ hoặc gây áp lực cho nhân viên | Mối liên hệ giữa các hồ sơ và bằng chứng đã xác minh |
| Tăng mạnh việc gọi nhà cung cấp SMS | Tiêu hao ngân sách | Số lần gửi, retry, đích nhận và hạn mức chi phí |

Một tín hiệu rủi ro hỗ trợ quyết định kiểm soát. Nó không tự chứng minh người gọi là kẻ tấn công hoặc người đã vượt qua kiểm tra rủi ro là chủ tài khoản.

## 2. Nhìn toàn bộ bề mặt khôi phục

Chỉ đặt giới hạn ở nút “quên mật khẩu” dễ bỏ sót các đường khác tới cùng một tác dụng phụ.

Các điểm cần được xem là một phần của luồng:

- Bắt đầu khôi phục bằng email, tên đăng nhập hoặc số điện thoại.
- Gửi lại email, SMS, cuộc gọi hoặc thông báo tới thiết bị.
- Tạo và trả lời challenge; nhập token, OTP hoặc mã dự phòng.
- Chọn phương thức thay thế khi mất MFA hoặc passkey.
- Tải lên bằng chứng và mở hồ sơ hỗ trợ.
- Xác nhận thay mật khẩu, thêm phương thức xác thực và hoàn tất khôi phục.
- Đọc trạng thái giao dịch, hủy giao dịch và gửi phản hồi “không phải tôi”.

API web, ứng dụng di động và các endpoint cũ có thể cùng gọi một dịch vụ gửi. Nếu mỗi endpoint có ngân sách riêng không liên kết, việc chuyển endpoint có thể nhân số lần gửi được phép.

Tương tự, một request cho phép gửi tới nhiều đích có thể tạo nhiều tác dụng phụ. Giới hạn số request không đủ nếu không giới hạn số thao tác bên trong request.

## 3. Tách các mục tiêu tấn công

### Dò sự tồn tại của tài khoản

Kẻ gọi thử nhiều định danh rồi so sánh thông báo, mã HTTP, kích thước dữ liệu, thời gian phản hồi hoặc metadata của hạn mức. Chỉ đổi câu chữ thành “nếu tài khoản tồn tại” chưa đủ nếu phần còn lại vẫn phân biệt được.

### Làm ngập kênh nhận

Mỗi request có thể hoàn toàn đúng cú pháp nhưng khiến hệ thống gửi thêm một email hoặc SMS. Hộp thư nạn nhân bị làm phiền, thông báo quan trọng bị che khuất và uy tín gửi của dịch vụ có thể bị ảnh hưởng.

### Đoán bằng chứng

Các request thử token hoặc mã ngắn khai thác số lần thử được phép. Nếu bộ đếm chỉ theo IP, bên gọi có thể phân tán nguồn. Nếu tạo giao dịch mới làm reset bộ đếm tổng, hạn mức theo từng giao dịch cũng không còn đủ.

### Tiêu hao tài nguyên và ngân sách

Tra cứu, sinh token, ghi database, tải tệp, kiểm tra giấy tờ, gọi nhà cung cấp và xử lý hỗ trợ đều có chi phí. OWASP API4:2023 nhấn mạnh rằng tài nguyên API bao gồm cả dịch vụ tính phí theo lần gọi, đồng thời đề cập giới hạn payload, tần suất thao tác và ngân sách tích hợp. Xem [Unrestricted Resource Consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/).

### Gây khóa hoặc ép mở đường yếu hơn

Bên gây hại có thể liên tục kích hoạt khôi phục để làm hết hạn đường dẫn của nạn nhân, khóa tài khoản hoặc tạo áp lực để nhân viên bỏ qua bằng chứng. Cơ chế phòng vệ không được vô tình cung cấp những khả năng đó cho người chưa xác thực.

## 4. Đặt kiểm soát trước tác dụng phụ tốn kém

Luồng dưới đây là một thiết kế minh họa, không phải một quy trình bắt buộc cho mọi sản phẩm:

~~~mermaid
flowchart TD
    A["Yêu cầu công khai"] --> B["Giới hạn kích thước và chi phí đầu vào"]
    B --> C["Ngân sách theo nguồn và toàn dịch vụ"]
    C --> D["Chuẩn hóa định danh theo quy tắc tài khoản"]
    D --> E["Policy theo định danh, giao dịch và kênh"]
    E --> F["Quyết định tác dụng phụ được phép"]
    F --> G["Hàng chờ có giới hạn và chống trùng"]
    G --> H["Kiểm tra ngân sách gửi tại thời điểm thực hiện"]
    H --> I["Gửi hoặc xử lý theo policy"]
    F --> J["Phản hồi công khai nhất quán"]
~~~

Kiểm tra rẻ và có khả năng loại sớm nên diễn ra trước bước tốn kém. Ví dụ, giới hạn kích thước body trước khi phân tích dữ liệu lớn; kiểm soát số lần gửi trước khi gọi nhà cung cấp.

Đường xác minh bằng chứng có thể được xử lý riêng với đường yêu cầu gửi mới. Một đợt làm ngập endpoint gửi không nên mặc nhiên ngăn người dùng đang giữ token hợp lệ hoàn tất giao dịch. Endpoint xác minh vẫn cần giới hạn phù hợp để chống đoán và bảo vệ tài nguyên.

Hàng chờ không tự tạo ra an toàn. Một API phản hồi nhanh nhưng đẩy mọi request vào queue không giới hạn chỉ chuyển điểm nghẽn sang phía sau.

## 5. Dùng nhiều chiều giới hạn

Không có một khóa giới hạn duy nhất phù hợp với mọi kiểu lạm dụng.

| Chiều kiểm soát | Mục tiêu | Hạn chế nếu dùng riêng |
| --- | --- | --- |
| Nguồn mạng đã xác định đúng | Hạn chế một nguồn tạo nhiều yêu cầu | Mạng dùng chung dễ bị ảnh hưởng; nguồn có thể thay đổi |
| Định danh được nhập | Giảm việc nhắm liên tục vào một định danh | Có thể bị lợi dụng để làm cạn ngân sách của nạn nhân |
| Đích nhận đã đăng ký | Giới hạn email, SMS hoặc cuộc gọi thực tế | Cần xử lý cẩn thận khi nhiều tài khoản dùng chung đích |
| Giao dịch khôi phục | Giới hạn resend và thử bằng chứng trong một luồng | Tạo giao dịch mới có thể né giới hạn nếu không có lớp tổng |
| Tài khoản và họ bằng chứng | Hạn chế thử trải rộng qua nhiều giao dịch | Phải tránh biến số lần thử công khai thành khóa đăng nhập toàn cục |
| Tenant hoặc tổ chức | Ngăn một nhóm sử dụng hết tài nguyên chung | Cần chính sách công bằng giữa các nhóm |
| Nhà cung cấp và toàn dịch vụ | Giữ chi phí, queue và năng lực trong giới hạn | Quá tải chung có thể tác động người dùng hợp lệ |

Các chiều này phối hợp với nhau. Không cộng hạn mức của từng endpoint rồi coi đó là ngân sách tổng. Cũng không giả định mọi chiều đều phải có cùng một phản ứng khi vượt ngưỡng.

Ví dụ thiết kế: vượt ngân sách gửi cho một đích có thể khiến hệ thống bỏ qua việc gửi thêm trong khoảng chờ, trong khi bằng chứng đã phát và còn hiệu lực vẫn được xét theo policy riêng.

Giá trị ngưỡng cần dựa vào lưu lượng, rủi ro, độ trễ kênh và năng lực vận hành của sản phẩm. Một con số cố định sao chép từ hệ thống khác không tự trở thành chính sách phù hợp.

## 6. Khóa giới hạn phải phản ánh đúng thực thể

Nếu cùng một định danh có nhiều cách biểu diễn hợp lệ nhưng mỗi cách dùng một bộ đếm, bên gọi có thể phân tán yêu cầu giữa các biến thể.

Chuẩn hóa phải dùng quy tắc của chính hệ thống tài khoản. Không tự xóa dấu chấm, bỏ phần sau dấu cộng hoặc đổi mọi phần của email về chữ thường nếu mô hình định danh chưa cho phép việc đó. Một phép chuẩn hóa sai có thể gộp hai tài khoản khác nhau hoặc làm liên kết nhầm kênh khôi phục.

Với địa chỉ nguồn, chỉ tin metadata từ proxy đã được cấu hình. Header do client tự gửi không phải bằng chứng rằng request đến từ địa chỉ được khai báo. Địa chỉ IP cũng chỉ là một tín hiệu; nó không đồng nghĩa với một người hay một thiết bị.

Có thể tạo khóa nội bộ bằng HMAC trên định danh đã chuẩn hóa, kèm namespace cho mục đích và tenant. Cách này giúp tránh đưa email thô vào tên khóa hoặc log. Nó vẫn là dữ liệu có khả năng liên kết, cần kiểm soát truy cập và thời gian lưu; không nên gọi đó là dữ liệu vô danh.

Kho bộ đếm cần có TTL và giới hạn số khóa. Nếu mỗi chuỗi tùy ý đều tạo bản ghi sống lâu, cơ chế chống lạm dụng có thể trở thành mục tiêu gây đầy bộ nhớ.

## 7. Phản hồi công khai không được tiết lộ tài khoản

OWASP khuyến nghị thông báo nhất quán cho tài khoản tồn tại và không tồn tại, kiểm soát khác biệt thời gian, hạn chế gửi tự động quá mức và tránh thay đổi tài khoản trước khi có token hợp lệ. Tham khảo [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Một thông báo minh họa:

~~~text
Nếu thông tin phù hợp với tài khoản, hướng dẫn khôi phục
sẽ được gửi theo chính sách của dịch vụ.

Hãy kiểm tra kênh liên hệ đã đăng ký trước khi thử lại.
~~~

Hành vi thực hiện nội bộ có thể khác nhau: không có tài khoản thì không gửi; đã đạt ngân sách gửi thì không tạo thêm thông báo. Phản hồi công khai không cần tiết lộ chi tiết đó.

Cần cân nhắc đồng thời nội dung, mã trạng thái, header và độ trễ:

- Không trả “đã đạt giới hạn của tài khoản” chỉ cho email tồn tại.
- Không công khai số lần gửi còn lại theo tài khoản trên endpoint chưa xác thực.
- Không trả nhanh ngay cho email không tồn tại nhưng chờ gọi nhà cung cấp ở trường hợp còn lại.
- Khi cần hạn chế theo nguồn, áp dụng phản ứng cùng nguyên tắc cho các định danh được thử, thay vì để kết quả tra tài khoản quyết định việc lộ hạn mức.

Xử lý bất đồng bộ và đường phản hồi có cấu trúc tương đồng giúp giảm khác biệt. Việc giữ mọi kết nối bằng một khoảng sleep dài tùy ý có thể làm tăng nguy cơ cạn tài nguyên, nên không được coi là giải pháp đầy đủ cho timing.

Định danh không tồn tại cũng cần được tính trong ngân sách thăm dò thích hợp, nhưng không vì thế mà tạo trạng thái vô hạn cho mọi đầu vào.

## 8. Giảm khuếch đại ở kênh gửi

Trong thiết kế minh họa, bước yêu cầu gửi và bước thực sự gửi được kiểm soát riêng:

1. Kiểm tra ngân sách của yêu cầu.
2. Xác định tác dụng phụ có được phép tạo hay không.
3. Dành ngân sách hoặc giữ chỗ cho job gửi theo cơ chế nhất quán.
4. Chống tạo job trùng trong phạm vi đã xác định.
5. Kiểm tra lại điều kiện còn hiệu lực khi job được thực hiện.
6. Ghi nhận kết quả mà không đưa bí mật vào log.

Một khoảng chờ resend có thể giảm số thông báo mà nạn nhân nhận. Tuy nhiên, mỗi lần bị từ chối không nên tự kéo dài thời gian chờ mãi mãi; nếu không, người ngoài có thể duy trì tình trạng từ chối dịch vụ.

Không tự hủy mọi token còn hiệu lực mỗi khi có yêu cầu khôi phục công khai mới. Nếu áp dụng chính sách thay token, cần xác định ai có quyền thay và trong giao dịch nào. Mục tiêu là tránh việc nạn nhân mở liên kết hợp lệ thì liên kết vừa bị một request khác làm mất hiệu lực.

Idempotency có thể ngăn một lần retry tạo hai lần gửi, nhưng khóa idempotency do client cung cấp không phải giấy phép bỏ qua ngân sách. Cần ràng buộc khóa với phạm vi thao tác và ngữ cảnh, đồng thời giữ giới hạn tổng khi bên gọi thay khóa liên tục.

Retry của nhà cung cấp cũng phải có giới hạn và được tính vào chi phí. Khi kết quả gửi chưa rõ, không giả định gửi lại luôn miễn phí hoặc không tạo thêm thông báo.

Với email, không hoàn tất thay đổi tài khoản chỉ vì một GET được mở. Bộ quét liên kết và tính năng xem trước cũng có thể truy cập URL. Với push, tránh biến việc xác nhận thiếu ngữ cảnh thành hành động dễ được người dùng chấp nhận chỉ để tắt thông báo.

## 9. Friction tăng dần không thay thế bằng chứng

Có thể tăng yêu cầu tương tác khi rủi ro cao: trì hoãn gửi mới, yêu cầu hoàn tất một challenge chống bot, giới hạn đường gửi tốn kém hoặc chuyển sang quy trình hỗ trợ được quản lý.

Những biện pháp này điều tiết việc sử dụng dịch vụ. Chúng không thay thế bằng chứng sở hữu tài khoản.

Một người vượt qua CAPTCHA vẫn có thể đang yêu cầu khôi phục tài khoản của người khác. Một client có lịch sử “sạch” cũng không được phép đăng ký MFA mới nếu chưa đạt điều kiện khôi phục.

Challenge chống bot cần được máy chủ kiểm tra theo phạm vi và thời hạn phù hợp. Chỉ ẩn nút trên giao diện hoặc tin một trường `captchaPassed=true` do client gửi không tạo ra ranh giới kiểm soát.

Cần có lựa chọn phù hợp cho người dùng gặp khó khăn với challenge, mất thiết bị cũ hoặc dùng công cụ hỗ trợ tiếp cận. Đường thay thế vẫn phải có ngân sách và quy trình xác minh; không tự động trở thành đường ít bảo vệ hơn.

Thông báo cho người dùng nên nói rõ việc có thể làm tiếp theo. Tránh tiết lộ công thức chấm điểm, ngưỡng nội bộ hoặc chi tiết giúp điều chỉnh hành vi né kiểm soát.

## 10. Giữ cơ chế nhất quán khi nhiều instance cùng xử lý

Một bộ đếm chỉ nằm trong bộ nhớ của từng instance không phản ánh tổng lưu lượng. Nhiều request đồng thời cũng có thể cùng đọc trạng thái “còn một lượt” rồi cùng gửi nếu việc kiểm tra và dành ngân sách không nguyên tử.

Điểm quyết định nên dựa vào cơ chế dùng chung có bảo đảm phù hợp:

~~~text
Request A: xin giữ chỗ cho một job gửi tới đích D.
Request B: đồng thời xin giữ chỗ cho cùng đích D.

Kho kiểm soát chỉ cấp số chỗ phù hợp với ngân sách.
Chỉ job có quyền giữ chỗ hợp lệ mới đi tới nhà cung cấp.
~~~

Đây là mô hình khái niệm. Cách triển khai phụ thuộc kho dữ liệu, kiến trúc queue và yêu cầu sẵn sàng. Cần tính tới việc giữ chỗ hết hạn, job bị hủy, timeout và việc xác nhận kết quả đến trễ.

Kiểm tra ở API gateway hữu ích cho lưu lượng bên ngoài, nhưng tác dụng phụ vẫn cần kiểm soát ở dịch vụ thực thi. Công việc trong queue, endpoint nội bộ hoặc một đường API khác không nên vô tình bỏ qua cùng policy.

Khi thành phần chống lạm dụng bị lỗi, hành vi dự phòng phải được xác định trước. Không mở vô hạn việc gửi SMS hoặc tự bỏ qua giới hạn thử bằng chứng. Có thể tạm giảm năng lực gửi mới, giữ đường đọc trạng thái đã được bảo vệ hoặc ưu tiên giao dịch có bằng chứng hợp lệ theo khả năng của hệ thống.

Tình trạng quá tải không phải lý do để giảm điều kiện xác minh trước khi thay mật khẩu, MFA hay passkey.

## 11. Không biến kiểm soát thành công cụ khóa nạn nhân

Một yêu cầu khôi phục ban đầu chưa chứng minh ai đang gọi. Vì vậy, việc người ngoài tạo nhiều yêu cầu không nên tự dẫn tới:

- Khóa đăng nhập toàn bộ tài khoản của nạn nhân.
- Thu hồi mọi session đang hợp lệ.
- Xóa hoặc thay phương thức xác thực.
- Hủy mọi giao dịch mà chủ tài khoản đang thực hiện.
- Tự động nâng hồ sơ lên mức “đã xác minh” chỉ vì có nhiều yêu cầu khẩn cấp.

Giới hạn thử bằng chứng có thể dừng một giao dịch hoặc yêu cầu bằng chứng mới theo policy. Cần phân biệt phản ứng cục bộ đó với việc khóa mọi khả năng truy cập của tài khoản.

Sau khi chủ tài khoản được xác minh và hoàn tất khôi phục, các thay đổi session hoặc authenticator được thực hiện theo chính sách của giao dịch. Đó là quyết định có bằng chứng, khác với tác dụng phụ tự động từ một đợt gửi công khai.

Nếu phải dùng hỗ trợ thủ công, nhân viên cần nhìn thấy lịch sử đã tổng hợp và quy trình xác minh rõ ràng. Lượng ticket lớn, lời thúc giục hoặc việc bot đã tạo nhiều dấu vết không được coi là bằng chứng danh tính.

## 12. Quan sát chi phí, hiệu quả và ảnh hưởng người dùng

Số request bị chặn không đủ để đánh giá cơ chế. Chặn nhiều nhưng vẫn gửi hàng nghìn SMS là kết quả khác với giảm được số lần gửi thực tế.

Các nhóm dữ liệu vận hành có ích:

| Nhóm | Dữ liệu cần hiểu |
| --- | --- |
| Tác dụng phụ | Số job được tạo, số lần gửi thực tế, retry và chi phí tương ứng |
| Hành vi | Số định danh trên một nguồn, số nguồn nhắm cùng đích, tỷ lệ thử sai |
| Năng lực | Độ dài queue, độ trễ, số job bị gộp hoặc bỏ qua, tải kho kiểm soát |
| Trải nghiệm | Tỷ lệ người hợp lệ hoàn tất, số lần resend và nhu cầu hỗ trợ |
| Chính sách | Loại quyết định, phiên bản policy và nguyên nhân được phân loại |

Tránh dùng email, số điện thoại hoặc token làm nhãn metric có số lượng giá trị không giới hạn. Token, OTP, mã dự phòng và URL chứa bí mật không được đưa vào log phân tích.

Chỉ số theo nguồn hoặc theo đích cần giới hạn truy cập và thời gian lưu thích hợp. Khi dùng tín hiệu mạng hoặc thiết bị, cần xem cả ảnh hưởng tới người dùng chung mạng và người vừa mất thiết bị; đây chính là nhóm có thể thiếu lịch sử tin cậy.

Cảnh báo chi phí nên gắn với hành động vận hành cụ thể, chẳng hạn hạn chế một kênh đang bị lạm dụng hoặc điều chỉnh năng lực queue. Không tự biến mọi cảnh báo thành khóa tài khoản.

## 13. Ví dụ: nhiều nguồn cùng làm ngập một hộp thư

Hà mất điện thoại chứa MFA và bắt đầu khôi phục. Cùng lúc, một đợt tự động hóa gửi hàng trăm yêu cầu cho email của Hà từ nhiều nguồn mạng.

Nếu chỉ giới hạn theo IP, mỗi nguồn có thể ở dưới ngưỡng nhưng tổng số email vẫn lớn. Nếu mỗi lần gửi làm mất hiệu lực token trước, Hà còn có thể không dùng được hướng dẫn vừa nhận.

Trong thiết kế của bài này, ngân sách theo nguồn chặn một phần lưu lượng, ngân sách theo đích hạn chế tác dụng phụ và cơ chế chống trùng giữ queue không phình theo mọi request. Phản hồi công khai vẫn không tiết lộ trạng thái tài khoản. Những yêu cầu mới không tự thu hồi session hoặc hủy bằng chứng hợp lệ mà Hà đang sử dụng.

Khi Hà mở liên kết và thực hiện bước xác minh, dịch vụ áp dụng ngân sách thử riêng cùng điều kiện khôi phục của tài khoản. Việc vượt qua kiểm soát chống bot không tự cho phép thay MFA; bằng chứng vẫn phải được xác nhận đầy đủ.

Nếu lượng gửi vượt năng lực chung, hệ thống điều tiết kênh gửi và bảo vệ các giao dịch có quyền tiếp tục theo chính sách. Dữ liệu vận hành giúp phân biệt yêu cầu bị chặn, thông báo thực sự được gửi và người dùng đã hoàn tất.

Thiết kế này coi lạm dụng tự động là bài toán xuyên suốt luồng khôi phục: kiểm soát điểm vào, chi phí, tác dụng phụ và quyền thay đổi tài khoản phải phối hợp, trong khi đường đi của chủ tài khoản vẫn được bảo vệ.
