# Backup code purpose: Mục đích của mã dự phòng

## 1. Mã dự phòng giải quyết tình huống nào?

Mã dự phòng, thường gọi là *backup code* hoặc *recovery code*, là bí mật được cấp trước để người dùng có một đường tiếp tục truy cập hoặc khôi phục tài khoản khi phương thức xác thực thông thường không còn sử dụng được.

Ví dụ, Lan vẫn nhớ mật khẩu nhưng mất điện thoại chứa ứng dụng tạo mã TOTP. Nếu hệ thống cứ yêu cầu mã trên điện thoại đã mất, Lan bị kẹt. Một mã dự phòng đã lưu từ trước có thể được dùng trong bước thay thế phù hợp, theo chính sách của dịch vụ.

Điểm cốt lõi là **chuẩn bị một bằng chứng dự phòng trước sự cố**, thay vì tìm cách bỏ kiểm tra danh tính sau sự cố.

Mã dự phòng thường có các đặc điểm:

- Được hệ thống cấp cho một tài khoản cụ thể.
- Có giá trị bí mật khó đoán.
- Được người dùng cất giữ để dùng khi cần.
- Mỗi mã chỉ được chấp nhận thành công một lần.
- Có thể bị thu hồi khi cấp bộ mới hoặc khi phát hiện rủi ro.
- Chỉ mở quyền mà chính sách xác thực hoặc khôi phục cho phép.

Trong bài này, “mã dự phòng” chỉ loại mã đã cấp trước và được lưu giữ. Nó khác với mã khôi phục mới gửi qua email hoặc SMS sau khi người dùng bắt đầu một yêu cầu.

NIST phân biệt *saved recovery codes* với *issued recovery codes* trong các phương thức khôi phục tài khoản. Xem [NIST SP 800-63B-4, Account Recovery Methods](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery-methods).

## 2. Mục đích chính: có đường dự phòng mà vẫn kiểm soát quyền truy cập

### Tránh phụ thuộc vào một thiết bị duy nhất

Một thiết bị có thể bị mất, hỏng, hết pin, bị xóa dữ liệu hoặc không sử dụng được vào thời điểm cần đăng nhập. Nếu mọi đường xác thực đều phụ thuộc thiết bị đó, khả năng bảo vệ tài khoản sẽ đi kèm nguy cơ tự khóa người dùng hợp lệ.

Mã dự phòng tạo một đường có thể tách khỏi thiết bị chính. Người dùng không cần lấy mã từ authenticator đã mất hoặc chờ nhận SMS trên số không còn kiểm soát.

Tuy nhiên, nếu bản mã duy nhất nằm trong chính điện thoại vừa mất, lợi ích dự phòng gần như không còn.

### Giảm nhu cầu xử lý ngoại lệ thiếu căn cứ

Khi không có phương thức đã chuẩn bị, người dùng có thể phải liên hệ hỗ trợ. Nhân viên hỗ trợ dễ bị đặt vào tình huống phải quyết định dựa trên lời khai, thông tin công khai hoặc áp lực “mở tài khoản ngay”.

Mã dự phòng cung cấp một bằng chứng mà hệ thống đã gắn với tài khoản từ trước. Nó không loại bỏ mọi yêu cầu xác minh khác, nhưng giúp giảm sự phụ thuộc vào quyết định tùy ý.

OWASP nêu mã khôi phục dùng một lần được cấp khi thiết lập MFA là một phương án giúp xử lý mất yếu tố xác thực, đồng thời nhấn mạnh đường khôi phục phải được đánh giá để không tạo cơ hội chiếm đoạt. Xem [OWASP Multifactor Authentication Cheat Sheet, Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa).

### Duy trì kiểm soát khi đổi phương thức

Mã dự phòng có thể hỗ trợ một bước đăng nhập dự phòng hoặc cấp quyền giới hạn để người dùng thiết lập lại phương thức xác thực. Mục tiêu sau cùng là đưa tài khoản trở lại trạng thái có phương thức chính hoạt động được.

Không nên biến mã dự phòng thành lý do tắt MFA vĩnh viễn hoặc cho phép thay mọi thông tin bảo mật mà không xét mục đích.

## 3. Phân biệt mã dự phòng với những bí mật khác

| Thành phần | Cách có được | Vai trò chính | Điểm khác mã dự phòng |
| --- | --- | --- | --- |
| Mật khẩu | Người dùng tạo hoặc được cấp theo chính sách | Xác thực trong luồng thường ngày | Thường được dùng nhiều lần cho tới khi thay |
| Mã TOTP | Authenticator tính từ seed và thời gian | Cung cấp mã trong bước xác thực tương ứng | Người dùng cần còn phương thức tạo mã |
| Mã SMS hoặc email cấp theo yêu cầu | Máy chủ gửi khi bắt đầu một thao tác | Xác minh quyền nhận thông tin tại kênh đó | Phụ thuộc việc nhận được thông điệp vào thời điểm sử dụng |
| Mã dự phòng đã lưu | Được cấp trước và được cất giữ | Đường thay thế khi phương thức thông thường không khả dụng | Không cần nhận mã mới để có giá trị đã lưu |
| Seed của authenticator | Được cấp khi thiết lập ứng dụng OTP | Tạo ra nhiều mã OTP theo thời gian hoặc bộ đếm | Là bí mật lâu dài, không phải một mã tiêu thụ sau một lần dùng |
| Passkey | Được tạo và đăng ký qua cơ chế khóa công khai | Xác thực bằng credential của thiết bị hoặc hệ sinh thái hỗ trợ | Không phải một chuỗi mã để nhập thay thế tùy ý |
| Liên kết đặt lại mật khẩu | Được cấp cho một yêu cầu cụ thể | Cho phép đặt mật khẩu mới trong phạm vi được cấp | Không tự thay thế mọi yêu cầu MFA |
| Session hoặc refresh token | Được cấp sau một sự kiện xác thực hoặc ủy quyền | Duy trì quyền truy cập | Không phải bản mã dự phòng mà người dùng được hướng dẫn cất giữ |

Một bộ mã dự phòng cũng không phải bản sao lưu dữ liệu tài khoản. Nó không chứa tệp, lịch sử giao dịch hay cấu hình cần khôi phục.

Đặc biệt, mã dự phòng không phục hồi khóa riêng của passkey đã mất. Nếu đủ điều kiện, luồng khôi phục có thể cho đăng ký một phương thức mới; đó là một hành động được cấp quyền, không phải giải mã để lấy lại khóa cũ.

## 4. Khi nào mã dự phòng hữu ích?

| Tình huống | Vai trò có thể có của mã dự phòng | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Nhớ mật khẩu nhưng mất ứng dụng TOTP | Thay bước chứng minh mà authenticator không còn cung cấp được | Chính sách có chấp nhận mã trong bước đó không? |
| Hỏng điện thoại hoặc khóa bảo mật chính | Dùng đường dự phòng đã chuẩn bị | Có phương thức khác còn dùng được và phù hợp hơn không? |
| Không nhận được SMS | Tránh phụ thuộc vào giao nhận tại thời điểm đó | Mã có được cấp cho tài khoản và mục đích tương ứng không? |
| Quên mật khẩu và mất MFA | Cung cấp một phần bằng chứng khôi phục | Một mã có đủ không, hay cần thêm bằng chứng? |
| Mất passkey trên một thiết bị | Có thể hỗ trợ quy trình đăng ký phương thức mới | Có passkey khác còn sử dụng được không? |
| Mất cả phương thức chính lẫn mã dự phòng | Không còn đường này để sử dụng | Cần đi theo phương thức khôi phục khác được cho phép |
| Nghi ngờ có người đã sao chép bộ mã | Bộ mã có thể đã mất tính bí mật | Cần thu hồi, cấp lại và đánh giá ảnh hưởng |

Một ví dụ thực tế là GitHub mô tả recovery codes như các mã dùng một lần để hỗ trợ khi không truy cập được phương thức 2FA, đồng thời hướng dẫn lưu giữ an toàn. Xem [GitHub Docs, About the recovery codes file](https://docs.github.com/en/authentication/securing-your-account-with-two-factor-authentication-2fa/configuring-two-factor-authentication-recovery-methods#about-the-recovery-codes-file).

Đây là ví dụ sản phẩm, không phải cam kết rằng mọi dịch vụ đều cho mã dự phòng cùng quyền hoặc cùng cách sử dụng.

### Không dùng mã dự phòng để giải quyết sai vấn đề

Nếu chỉ tạm thời không thấy điện thoại nhưng vẫn có một phương thức mạnh khác, người dùng có thể chọn phương thức đó theo giao diện của dịch vụ. Không nhất thiết tiêu thụ mã dự phòng trong mọi tình huống bất tiện.

Nếu người dùng muốn khôi phục dữ liệu đã xóa, mã dự phòng không giải quyết được vấn đề đó.

Nếu người dùng muốn truy cập tài khoản của người khác hoặc một tài khoản quản trị chung, mã dự phòng cá nhân không thay thế quy trình phân quyền, bàn giao hoặc quản lý tài khoản khẩn cấp của tổ chức.

## 5. Một mã đúng chứng minh điều gì?

Một mã hợp lệ cho thấy người yêu cầu biết một bí mật dự phòng đã được cấp cho tài khoản và vẫn được hệ thống chấp nhận. Nó không tự chứng minh danh tính ngoài đời, ý định của người dùng hoặc mức độ an toàn của thiết bị đang sử dụng.

Bởi vậy, cần phân biệt:

- **Mã đúng:** dữ liệu nhập khớp một mã còn hợp lệ.
- **Đủ bằng chứng:** các điều kiện của hành động hiện tại đã được đáp ứng.
- **Được cấp quyền:** hệ thống đã cho phép một hành động cụ thể trong một ngữ cảnh xác định.

Ba kết quả này không phải lúc nào cũng xuất hiện cùng lúc.

Ví dụ, một dịch vụ có thể chấp nhận mật khẩu cộng mã dự phòng để hoàn tất bước đăng nhập thay cho TOTP. Một dịch vụ khác có thể chỉ dùng mã dự phòng để tiếp tục luồng thay authenticator, rồi yêu cầu kiểm tra bổ sung.

Trong bài toán khôi phục, có thể mô tả như sau:

~~~text
Bằng chứng đã có
    + Mã dự phòng hợp lệ
    + Kiểm tra chính sách của hành động
    = Quyết định tiếp tục, yêu cầu thêm bằng chứng hoặc từ chối
~~~

Không suy luận rằng một mã dự phòng bất kỳ luôn đủ để đặt lại mật khẩu, xóa MFA, thay email và thu hồi mọi passkey trong cùng một lần.

### Nhiều mã trong một bộ không mặc nhiên là nhiều yếu tố độc lập

Nếu người dùng nhập hai mã từ cùng một tờ giấy, hệ thống đã nhận hai giá trị bí mật. Điều đó không tự biến thành hai yếu tố độc lập hoặc hai phương thức khôi phục có rủi ro tách biệt.

Nếu cả bộ mã đã bị sao chép, người giữ bản sao có thể biết nhiều mã cùng lúc. Việc xác định đủ bằng chứng cần dựa trên chính sách, không chỉ dựa vào số ô nhập đã hoàn thành.

## 6. Mã dự phòng phải được chuẩn bị trước khi mất quyền truy cập

Một vòng đời minh họa gồm:

1. Người dùng đã đáp ứng yêu cầu để thiết lập hoặc quản lý phương thức bảo mật.
2. Hệ thống cấp một mã hoặc một bộ mã dự phòng.
3. Người dùng lưu ở nơi phù hợp và biết cách tìm lại.
4. Khi cần, người dùng chọn đúng đường sử dụng mã.
5. Máy chủ kiểm tra và tiêu thụ mã được chấp nhận.
6. Người dùng hoàn tất bước được phép, khôi phục phương thức chính và bổ sung phương án dự phòng.

Giá trị của mã dự phòng nằm ở giai đoạn chuẩn bị. Một API cho phép người chưa xác minh tải bộ mã chỉ bằng tên đăng nhập sẽ phá hỏng chính mục đích bảo vệ tài khoản.

### Vì sao cần bí mật ngẫu nhiên đủ mạnh?

Mã dự phòng có thể nằm trong thời gian dài trước khi được sử dụng. Nếu dễ đoán hoặc được suy ra từ thông tin cá nhân, người tấn công có thể tìm được đường vào mà không cần kiểm soát thiết bị chính.

Độ mạnh phụ thuộc phần bí mật thực sự được sinh, không phụ thuộc số dấu gạch nối hoặc cách in đẹp. Chia nhóm ký tự giúp đọc và nhập; nó không làm tăng tính ngẫu nhiên.

NIST yêu cầu saved recovery code có ít nhất 64 bit từ bộ sinh ngẫu nhiên được chấp thuận, lưu ở dạng băm, giới hạn thử và vô hiệu hóa sau khi dùng; hướng dẫn cũng yêu cầu cấp mã thay thế sau sử dụng. Tham khảo [NIST SP 800-63B-4, Saved Recovery Codes](https://pages.nist.gov/800-63-4/sp800-63b.html#saved-recovery-codes). Đây là yêu cầu trong phạm vi hướng dẫn đó; thiết kế dịch vụ vẫn cần xem xét toàn bộ chính sách liên quan.

Đối với bài học này, điều cần nhớ là mã phải khó đoán và được quản lý như một bí mật xác thực, thay vì một số tham chiếu hỗ trợ khách hàng.

### Hiệu lực không giống OTP ngắn hạn

Mã dự phòng đã lưu không cần đổi liên tục như TOTP. Nó có thể còn hiệu lực cho tới khi được dùng, bị thu hồi, bị thay thế hoặc hết hạn nếu chính sách có đặt thời hạn.

Do đó, không được mặc định một mã đã cũ là an toàn để đăng công khai. Nếu chưa bị vô hiệu hóa, bản lưu nhiều tháng trước vẫn có thể mang giá trị xác thực.

Một mô hình trạng thái đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> UNUSED: Cấp mã
    UNUSED --> USED: Xác minh và tiêu thụ thành công
    UNUSED --> REVOKED: Thu hồi hoặc thay bộ mã
    UNUSED --> EXPIRED: Hết hạn nếu chính sách có quy định
    USED --> [*]
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Các tên trạng thái là minh họa cho mô hình dữ liệu. Mã đã dùng không được tự trở lại UNUSED chỉ vì người dùng đóng trình duyệt.

## 7. Lưu giữ để còn sử dụng được khi sự cố xảy ra

Mã dự phòng vừa cần bí mật, vừa cần có thể lấy ra lúc phương thức chính hỏng. Chỉ đáp ứng một trong hai yêu cầu là chưa đủ.

| Cách lưu | Điểm cần đánh giá |
| --- | --- |
| Bản in ở nơi có kiểm soát | Có chống người khác đọc và có thể tìm lại khi cần không? |
| Trình quản lý mật khẩu đáng tin cậy | Có truy cập được nếu mất điện thoại chính không? |
| Tệp được bảo vệ trên phương tiện khác | Ai có thể đọc và người dùng có biết vị trí, cách mở không? |
| Chỉ chụp màn hình trên điện thoại chính | Có thể mất cùng thiết bị đang cần khôi phục |
| Chỉ lưu trong chính tài khoản đang bảo vệ | Có nguy cơ phải đăng nhập tài khoản mới đọc được mã |
| Gửi cho người khác qua kênh trò chuyện | Tạo thêm người và bản sao có thể sử dụng bí mật |

“Lưu ở nơi khác” không nhất thiết chỉ là dùng thiết bị vật lý khác. Cần xét **chuỗi phụ thuộc thực tế**.

Ví dụ, mã nằm trong kho được mã hóa trên máy tính khác vẫn không giúp được nếu khóa mở kho chỉ có trên điện thoại đã mất. Ngược lại, một trình quản lý mật khẩu có cách truy cập độc lập và được bảo vệ phù hợp có thể là lựa chọn khả dụng.

Nếu mật khẩu và mã dự phòng cùng nằm trong một nơi, việc nơi đó bị xâm phạm có thể làm lộ cả hai. Cần hiểu ảnh hưởng này khi quyết định cách lưu, thay vì mặc định mọi dữ liệu lưu cùng chỗ đều tạo ra bằng chứng độc lập.

### Hướng dẫn người dùng cần cụ thể

Một hướng dẫn có thể ghi:

> Đây là mã dùng khi bạn không sử dụng được phương thức xác thực thông thường. Mỗi mã chỉ dùng một lần. Lưu ở nơi an toàn mà bạn vẫn truy cập được nếu mất thiết bị chính. Không gửi mã cho người khác.

Người dùng cần biết mã thuộc dịch vụ hoặc tài khoản nào, nhưng bản lưu không nên gom thêm mật khẩu và dữ liệu cá nhân không cần thiết.

Không yêu cầu người dùng đăng một mã thật vào biểu mẫu khảo sát hoặc gửi cả bộ mã cho hỗ trợ để chứng minh đã lưu.

## 8. Một lần sử dụng phải dẫn tới một kết quả được kiểm soát

Luồng dưới đây minh họa dịch vụ cho phép dùng mã dự phòng trong một bước xác minh. Bằng chứng ban đầu có thể khác nhau tùy chính sách.

~~~mermaid
flowchart TD
    A[Bắt đầu đăng nhập hoặc khôi phục] --> B[Bằng chứng ban đầu theo chính sách]
    B --> C[Chọn sử dụng mã dự phòng]
    C --> D[Nhập một mã chưa dùng]
    D --> E[Máy chủ kiểm tra mã, tài khoản và ngữ cảnh]
    E --> F{Mã còn hợp lệ?}
    F -- Không --> G[Phản hồi phù hợp và giới hạn thử]
    F -- Có --> H[Tiêu thụ mã và ghi bằng chứng nguyên tử]
    H --> I{Đã đủ điều kiện hành động?}
    I -- Chưa --> J[Thực hiện bước xác minh bổ sung]
    I -- Đủ --> K[Cấp quyền hoặc session đúng phạm vi]
    J --> L[Hoàn tất chính sách]
    L --> K
    K --> M[Khôi phục phương thức chính và rà soát bảo mật]
~~~

### Dùng một lần phải do máy chủ thực thi

Ẩn một mã trên giao diện hoặc để người dùng tự gạch mã trên giấy không đủ. Hai bản sao của tờ giấy vẫn chứa cùng giá trị.

Khi mã được chấp nhận, máy chủ phải cập nhật trạng thái để cùng mã không được chấp nhận lần nữa. Nếu hai yêu cầu tới đồng thời, chúng không được cùng đọc “chưa dùng” rồi cùng thành công.

Ở mức trách nhiệm, có thể mô tả:

~~~text
Khi chấp nhận một mã dự phòng:
    kiểm tra mã thuộc đúng tài khoản và còn hiệu lực
    trong một cập nhật nguyên tử:
        tiêu thụ mã nếu vẫn chưa dùng
        ghi bằng chứng vào đúng luồng
        ghi kết quả cần thiết để tiếp tục theo chính sách
    chỉ cho bước tiếp theo dựa trên kết quả đã lưu
~~~

Đoạn mô tả không thay thế việc thiết kế giao dịch cụ thể. Nó cho thấy tiêu thụ mã và ghi nhận bằng chứng không được tách rời theo cách có thể tạo hai lần chấp nhận.

Nếu mạng bị ngắt sau khi mã đã được tiêu thụ, có thể cho người dùng kiểm tra lại trạng thái bằng phiên đã liên kết. Không tự bật lại mã cũ chỉ để giải quyết việc phản hồi bị mất.

### Giới hạn thử và phạm vi quyền

Hệ thống cần hạn chế thử sai theo các phạm vi phù hợp, chẳng hạn tài khoản, luồng và nguồn yêu cầu. Không chỉ vô hiệu hóa nút trên trình duyệt.

Thông báo lỗi ở điểm vào công khai không nên cho biết chi tiết tài khoản có tồn tại, bộ mã có bao nhiêu mã hay giá trị vừa nhập đã từng được dùng. Chi tiết cần thiết có thể chỉ dành cho xử lý nội bộ và người đã được phép xem.

Sau khi đủ điều kiện, quyền có thể là hoàn thành một bước đăng nhập hoặc cho phép thay một authenticator cụ thể. Không cần cấp toàn bộ quyền tài khoản chỉ để người dùng có thể bắt đầu sửa phương thức xác thực.

## 9. Giới hạn bảo vệ: dùng một lần vẫn có thể bị đánh cắp

Mã dự phòng không bị phụ thuộc vào việc nhận SMS tại thời điểm dùng, nhưng có những rủi ro riêng.

### Người khác có thể dùng trước chủ tài khoản

Nếu đối tượng khác chụp được bộ mã, một mã chưa dùng có thể trở thành bằng chứng cho họ. Cơ chế dùng một lần ngăn lần sử dụng sau; nó không phân biệt ai là người dùng mã đầu tiên.

Vì vậy, phát hiện hoặc nghi ngờ lộ mã là căn cứ để thu hồi và đánh giá ảnh hưởng. Không chờ tới khi có một mã bị dùng mới xử lý.

### Mã có thể bị lấy qua phishing

Một trang giả có thể yêu cầu người dùng nhập mã dự phòng rồi dùng mã đó trong luồng thật. Chuỗi mã người dùng nhập không tự được ràng buộc mật mã với tên miền như một cơ chế xác thực chống phishing thích hợp.

Cảnh báo và giao diện rõ ràng giúp giảm nhầm lẫn, nhưng không thay đổi bản chất bí mật có thể sao chép.

Dịch vụ nên hướng dẫn nhập mã trên trang chính thức của hành động đã chủ động bắt đầu, không đọc mã cho người tự xưng là nhân viên hỗ trợ.

### Để lộ cả bộ làm mất nhiều cơ hội dự phòng

Trong luồng sử dụng, chỉ nên yêu cầu giá trị cần thiết, thường là một mã theo chính sách. Không thu cả bộ để “kiểm tra nhanh”.

Nếu kẻ tấn công có toàn bộ bản lưu, việc mỗi mã chỉ dùng một lần không ngăn họ sử dụng các mã khác chưa bị thu hồi.

### Mã dự phòng không khắc phục thiết bị đang bị kiểm soát

Nếu máy tính đang có phần mềm độc hại hoặc trình duyệt bị can thiệp, nhập mã dự phòng có thể làm lộ thêm bí mật và tạo quyền truy cập cho đối tượng khác.

Khi nghi thiết bị không còn tin cậy, cần xử lý ngữ cảnh sử dụng và lựa chọn thiết bị phù hợp. Tiêu thụ thêm nhiều mã trên cùng thiết bị không tự giải quyết sự cố.

## 10. Sau khi dùng, mục tiêu là phục hồi trạng thái bảo mật bền vững

Sử dụng mã dự phòng là bước chuyển tiếp. Sau đó, người dùng và hệ thống cần xem xét nguyên nhân khiến phương thức chính không dùng được.

### Phương thức chính chỉ tạm thời không khả dụng

Nếu điện thoại chỉ hết pin và không có dấu hiệu mất kiểm soát, người dùng có thể tiếp tục dùng phương thức chính khi khả dụng. Mã dự phòng đã tiêu thụ vẫn không được dùng lại.

### Thiết bị hoặc bí mật xác thực đã mất

Nếu điện thoại chứa TOTP bị đánh cắp, có thể cần thay seed và thu hồi liên kết cũ theo quy trình được cấp quyền. Nếu mất khóa bảo mật hoặc passkey trên một thiết bị, cần quản lý đúng credential bị ảnh hưởng và thiết lập phương thức mới khi đủ điều kiện.

Việc dùng mã dự phòng không tự thực hiện các bước này.

### Session cũ cần được đánh giá riêng

Thu hồi authenticator hoặc tiêu thụ mã không nhất thiết chấm dứt session đã tồn tại. Nếu sự cố liên quan thiết bị bị mất hoặc nghi chiếm đoạt, cần áp dụng chính sách đối với session, refresh token và thiết bị đã ghi nhớ.

Tương tự, một quyền khôi phục giới hạn không tự chuyển thành session đầy đủ chỉ vì người dùng đã tới trang cuối của giao diện.

### Duy trì phương án dự phòng còn dùng được

Sau khôi phục, cần cho người dùng biết có phải bổ sung mã hoặc cấp bộ mới không. Khi còn rất ít mã, dịch vụ có thể nhắc chuẩn bị tiếp trong ngữ cảnh đã được xác minh.

Không hiển thị nguyên bộ mã còn lại ở nơi không có kiểm soát chỉ để thuận tiện đếm số lượng.

Một thông báo về việc mã dự phòng vừa được dùng hoặc bộ mã vừa được thay có thể hỗ trợ phát hiện lạm dụng. Thông báo không chứa chính mã đó và cần gửi qua kênh phù hợp với tình huống.

## 11. Cấp lại bộ mã khác với xem lại hoặc dùng lại mã cũ

Trong một thiết kế lưu mã bằng bản biểu diễn một chiều, máy chủ kiểm tra giá trị người dùng gửi mà không cần giữ bản rõ để đọc lại. Nếu người dùng mất bản lưu, có thể cần cấp mã mới sau khi đáp ứng yêu cầu bảo mật, thay vì tìm cách khôi phục giá trị cũ từ bản băm.

Chính sách phát bộ mới phải nói rõ ảnh hưởng:

| Thao tác | Câu hỏi cần được trả lời |
| --- | --- |
| Cấp bộ mới | Toàn bộ mã cũ còn chưa dùng có bị vô hiệu hóa không? |
| Bổ sung một mã thay thế | Mã nào còn giữ hiệu lực và người dùng phân biệt được ra sao? |
| Thu hồi vì lộ bí mật | Có vô hiệu hóa mọi mã trong bộ bị ảnh hưởng không? |
| Mất quyền truy cập trước khi lưu bộ mới | Có đường tiếp tục nào đã được kiểm soát không? |

Một chính sách dễ hiểu là phát bộ mới và thu hồi bộ cũ. Nếu chọn cách này, việc thay trạng thái cần nhất quán và người dùng phải biết bản in cũ không còn dùng được.

Không chỉ thêm mã mới rồi để các bộ cũ tồn tại vô thời hạn ngoài ý muốn. Ngược lại, không hủy bộ đang dùng trước khi quyết định thiết kế đã giải quyết rủi ro người dùng bỏ dở thao tác cấp lại.

Quyền phát mã mới cũng là quyền nhạy cảm. Một người chiếm được session không nên mặc nhiên có thể tạo bộ mã cho mình mà không qua kiểm tra phù hợp với hành động.

Các sản phẩm có thể có chính sách hiển thị, tải lại và lưu trữ khác nhau. Điều cần đánh giá là cách bảo vệ bản rõ, quyền truy cập và vòng đời hiệu lực, thay vì suy rằng mọi chức năng tên “recovery codes” đều giống nhau.

## 12. Tình huống tổng hợp

Lan đã bật MFA, lưu mã dự phòng ở nơi có thể truy cập độc lập và sau đó mất điện thoại. Cô vẫn nhớ mật khẩu.

Trong một chính sách minh họa:

1. Lan truy cập trang chính thức và hoàn thành bước mật khẩu.
2. Lan chọn sử dụng mã dự phòng.
3. Hệ thống chấp nhận một mã chưa dùng, tiêu thụ mã và hoàn tất bước được phép.
4. Vì điện thoại bị mất, Lan thực hiện quy trình thay authenticator hoặc đăng ký phương thức mới phù hợp.
5. Hệ thống xử lý credential và session bị ảnh hưởng theo tình huống.
6. Lan chuẩn bị lại phương án dự phòng và cất bản lưu theo chính sách mới.

Nếu Lan cũng quên mật khẩu, bước 1 không thể được coi là đã hoàn thành. Mã dự phòng khi đó có thể là một bằng chứng trong luồng khôi phục khác; hệ thống phải quyết định cần thêm gì.

Nếu Lan chưa từng lưu mã, không có thao tác an toàn nào biến một tên đăng nhập công khai thành bộ mã đã cấp trước. Cô cần dùng phương thức khác còn hợp lệ hoặc quy trình hỗ trợ được thiết kế.

Nếu Lan nghi bộ mã đã bị chụp lại, ưu tiên là xử lý nguy cơ lộ bí mật. Dùng một mã rồi giữ nguyên các mã còn lại mà không đánh giá rủi ro có thể để đường truy cập cho người khác.

**Mục đích của mã dự phòng là giúp người dùng đã chuẩn bị trước vượt qua sự cố của phương thức xác thực chính, trong giới hạn quyền được thiết kế.** Để đạt mục đích đó, mã phải còn bí mật, còn lấy ra được khi cần, chỉ được chấp nhận một lần và dẫn tới bước khôi phục phù hợp.
