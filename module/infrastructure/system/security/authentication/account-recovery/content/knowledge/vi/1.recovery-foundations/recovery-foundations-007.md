# Thuật ngữ khôi phục tài khoản dành cho người học

## 1. Vì sao cần hiểu đúng thuật ngữ?

Trong một luồng khôi phục tài khoản, câu “người dùng đã được xác minh” thường chưa đủ rõ. Hệ thống đã xác minh rằng người đó nhận được email, sở hữu một khóa đã đăng ký, có danh tính ngoài đời phù hợp hay được phép thay MFA? Những kết quả này liên quan với nhau nhưng không thể dùng thay thế cho nhau.

Tương tự, “đổi mật khẩu”, “khôi phục tài khoản” và “đăng xuất mọi thiết bị” mô tả các thay đổi khác nhau. Nếu đặc tả dùng chúng như từ đồng nghĩa, nhóm phát triển có thể vô tình cấp quyền lớn hơn dự định hoặc bỏ sót phiên vẫn còn hoạt động.

Bài học thuộc chương **Recovery Foundations**, cung cấp vốn từ để đọc, trao đổi và thiết kế các luồng khôi phục khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mỗi thuật ngữ cần được hiểu cùng đối tượng mà nó tác động và điều mà nó thực sự chứng minh.

Sau bài học, bạn cần có thể:

- Phân biệt tài khoản, định danh, danh tính, thông tin xác thực và phương tiện xác thực.
- Giải thích sự khác nhau giữa xác thực, phân quyền và kiểm chứng danh tính.
- Dùng đúng các từ chỉ mã, token, liên kết và yêu cầu khôi phục.
- Phân biệt thay thông tin xác thực với thu hồi phiên và thu hồi quyền truy cập.
- Đọc một mô tả luồng và chỉ ra những cụm từ mơ hồ cần được làm rõ.

## 2. Nhóm thuật ngữ về tài khoản và chủ thể

### 2.1. Account, account identifier và identity

| Thuật ngữ | Cách gọi tiếng Việt | Ý nghĩa trong khôi phục tài khoản |
| --- | --- | --- |
| Account | Tài khoản | Bản ghi trong dịch vụ, gắn với dữ liệu, thông tin xác thực, quyền và lịch sử hoạt động |
| Account identifier | Định danh tài khoản | Giá trị giúp tìm hoặc tham chiếu tài khoản, như tên đăng nhập, email đăng nhập hoặc mã tài khoản |
| Identity | Danh tính | Tập thuộc tính mô tả một chủ thể trong một ngữ cảnh; có thể là danh tính trong dịch vụ hoặc danh tính ngoài đời |
| Account holder | Chủ tài khoản | Chủ thể có quyền sử dụng hoặc kiểm soát tài khoản theo mô hình của dịch vụ |
| Claimant | Người đưa ra yêu cầu xác thực hoặc khôi phục | Chủ thể đang tuyên bố mình có quyền truy cập; hệ thống chưa thể mặc định tuyên bố đó đúng |
| Principal | Chủ thể bảo mật | Thực thể được hệ thống gắn các hành động và quyền, có thể là người dùng hoặc tài khoản dịch vụ |

**Định danh giúp tìm tài khoản; nó không tự chứng minh quyền kiểm soát tài khoản.** Biết email của một người không có nghĩa được phép đặt lại mật khẩu cho người đó.

Email cũng có thể đảm nhiệm nhiều vai trò: định danh đăng nhập, địa chỉ liên hệ và kênh khôi phục. Các vai trò phải được phân biệt ngay cả khi cùng dùng một giá trị. Đổi địa chỉ nhận thông báo không nhất thiết được phép đổi định danh đăng nhập hoặc bằng chứng khôi phục.

Danh tính trong dịch vụ có thể chỉ là một biệt danh. Một giấy tờ mang tên thật không tự động chứng minh mối liên hệ với tài khoản biệt danh nếu dịch vụ chưa có cơ sở liên kết đáng tin cậy. Khi nghe “đã xác minh danh tính”, cần hỏi tiếp: danh tính nào, bằng cách nào và liên kết với tài khoản nào?

### 2.2. Credential, authenticator và authentication factor

Ba thuật ngữ này thường bị dịch gộp thành “thông tin đăng nhập”, nhưng chúng giúp diễn đạt ba khía cạnh khác nhau.

| Thuật ngữ | Cách hiểu thực hành | Ví dụ |
| --- | --- | --- |
| Credential | Thông tin xác thực | Mật khẩu hoặc thông tin khóa được dùng trong cơ chế xác thực; cách dùng chi tiết của từ này có thể khác theo giao thức |
| Authenticator | Phương tiện xác thực | Thành phần người dùng sử dụng hoặc kiểm soát để xác thực, như ứng dụng tạo OTP, khóa bảo mật hoặc bộ xác thực trên thiết bị |
| Authentication factor | Yếu tố xác thực | Loại bằng chứng: điều người dùng biết, thứ họ sở hữu hoặc đặc điểm thuộc về họ |
| Authentication method | Phương thức xác thực | Cách thực hiện xác thực, chẳng hạn mật khẩu, OTP hoặc passkey |

Một khóa bảo mật là phương tiện xác thực, có thể quản lý nhiều thông tin xác thực cho các dịch vụ khác nhau. Một điện thoại có thể chứa nhiều phương tiện hoặc phương thức: ứng dụng OTP, passkey và phiên email. Vì vậy, mất một thiết bị có thể làm mất nhiều đường truy cập cùng lúc.

Không nên đếm số màn hình để suy ra số yếu tố. Mật khẩu rồi đến câu hỏi bí mật vẫn chủ yếu dựa vào điều người dùng biết. Một phương tiện cũng có thể yêu cầu mở khóa cục bộ bằng PIN hoặc sinh trắc học; việc nó đáp ứng yêu cầu xác thực nào còn phụ thuộc cơ chế và chính sách thực tế.

## 3. Nhóm thuật ngữ về việc kiểm tra và cấp quyền

### 3.1. Authentication và authorization

**Authentication — xác thực** là quá trình kiểm tra bằng chứng để xác lập chủ thể đang truy cập theo cơ chế của hệ thống. **Authorization — phân quyền hoặc cho phép thực hiện** là quyết định chủ thể đó được làm gì.

Ví dụ, việc kiểm tra một token khôi phục thành công có thể cho phép người yêu cầu đặt mật khẩu mới. Nó không mặc nhiên cho phép xuất dữ liệu, đổi email hay cấp quyền quản trị. Phạm vi được phép thực hiện phải được quyết định riêng.

Trong trao đổi kỹ thuật, nên nói “đã xác thực bằng phương thức X” và “được phép thực hiện thao tác Y” thay cho một câu chung chung là “đã qua bảo mật”.

### 3.2. Verification và identity proofing

**Verification — xác minh hoặc kiểm tra tính đúng đắn** là một từ rộng. Cần nêu đối tượng đang được kiểm tra: xác minh email, xác minh chữ ký, xác minh mã hoặc xác minh thông tin trên giấy tờ.

**Identity proofing — kiểm chứng danh tính** là quá trình thiết lập mức tin cậy rằng một chủ thể gắn với danh tính được khai báo. Tùy mô hình, quá trình có thể kiểm tra bằng chứng danh tính và sự liên kết giữa bằng chứng với người yêu cầu. Đây không phải tên gọi thay thế cho mọi lần đăng nhập.

| Kết quả kiểm tra | Có thể diễn đạt điều gì? | Không nên tự suy ra điều gì? |
| --- | --- | --- |
| Mã gửi tới email hợp lệ | Người yêu cầu có khả năng lấy mã tại kênh đó trong điều kiện của quy trình | Toàn bộ tài khoản và thiết bị đều an toàn |
| Chữ ký từ khóa đã đăng ký hợp lệ | Bên yêu cầu sử dụng được khóa tương ứng theo cơ chế xác thực | Người đang cầm thiết bị chắc chắn là chủ tài khoản trong mọi hoàn cảnh |
| Giấy tờ được kiểm tra | Một phần hoặc toàn bộ kiểm tra danh tính theo quy trình đã hoàn tất | Danh tính đó tự động sở hữu mọi tài khoản cùng tên |
| Nhân viên phê duyệt yêu cầu | Một quyết định xét duyệt đã được đưa ra theo thẩm quyền | Mọi thay đổi thông tin xác thực đã được thực thi thành công |

### 3.3. Assurance, evidence và risk signal

- **Evidence — bằng chứng:** thông tin hoặc kết quả kiểm tra được dùng để hỗ trợ quyết định, chẳng hạn sử dụng được khóa đã đăng ký hoặc mã dự phòng hợp lệ.
- **Assurance — mức bảo đảm:** mức tin cậy mà quy trình đem lại cho một kết luận cụ thể. Không nên diễn đạt bằng “chắc chắn tuyệt đối”.
- **Risk signal — tín hiệu rủi ro:** dữ liệu ngữ cảnh giúp đánh giá nguy cơ, chẳng hạn nhiều yêu cầu liên tiếp, thay kênh khôi phục gần đây hoặc thiết bị mới.
- **Risk assessment — đánh giá rủi ro:** quá trình xem xét khả năng bị lạm dụng và tác động để chọn cách xử lý phù hợp.

Một IP quen có thể là tín hiệu thuận lợi, nhưng không tự trở thành bằng chứng đủ để tắt MFA. Thiết bị mới có thể làm tăng nhu cầu kiểm tra, nhưng cũng là tình huống bình thường của người vừa mất thiết bị. Tín hiệu cần được đặt trong bối cảnh, không dùng như kết luận sở hữu tài khoản.

## 4. Nhóm thuật ngữ về mật khẩu, MFA và passkey

### 4.1. Password, OTP và MFA

| Thuật ngữ | Giải thích | Điểm dễ nhầm |
| --- | --- | --- |
| Password | Mật khẩu, một bí mật dùng trong cơ chế xác thực dựa trên điều người dùng biết | Đổi mật khẩu không tự làm mọi phiên cũ hết hiệu lực |
| OTP — One-Time Password | Mật khẩu hoặc mã dùng một lần trong một cơ chế xác thực | Không phải mọi OTP đều là mã khôi phục; cũng không phải mọi OTP đều được gửi qua SMS |
| TOTP — Time-based One-Time Password | OTP được tính theo bí mật dùng chung và thời gian | Mã có giá trị theo cửa sổ thời gian; không nên mô tả là liên kết đặt lại mật khẩu |
| MFA — Multi-Factor Authentication | Xác thực sử dụng các yếu tố thuộc những loại khác nhau theo cơ chế áp dụng | Hai bước trên giao diện chưa chắc là hai yếu tố |
| 2FA — Two-Factor Authentication | Trường hợp xác thực hai yếu tố | Tên gọi không cho biết phương thức cụ thể là SMS, OTP hay khóa bảo mật |
| Backup authenticator | Phương tiện xác thực dự phòng đã được thiết lập | Có thể là đường đăng nhập hợp lệ, không nhất thiết là thủ tục khôi phục đặc biệt |

“Dùng một lần” là thuộc tính cần được thực thi theo cơ chế tương ứng. Ví dụ, một mã TOTP đang nằm trong cửa sổ thời gian có thể bị gửi lại; hệ thống phải có kiểm soát chống sử dụng lại phù hợp. Không thể kết luận một cơ chế chống phát lại tốt chỉ từ chữ OTP trong tên gọi.

### 4.2. Passkey và security key

**Passkey** là thông tin xác thực dựa trên cặp khóa, được dùng trong một cơ chế xác thực khóa công khai. Dịch vụ xác minh bằng phần khóa công khai và thông tin liên quan; khóa riêng được sử dụng qua phương tiện xác thực, không được gửi cho dịch vụ như mật khẩu.

**Security key — khóa bảo mật** thường chỉ một thiết bị xác thực chuyên dụng. Thiết bị này có thể lưu và sử dụng passkey. Vì vậy, passkey và khóa bảo mật không phải hai tên gọi đồng nghĩa: một từ chỉ thông tin xác thực, một từ thường chỉ phương tiện.

Các cách gọi cần phân biệt:

- **Synced passkey — passkey đồng bộ:** có thể được cung cấp trên các thiết bị thông qua cơ chế đồng bộ của nhà cung cấp. Khả năng truy cập lại phụ thuộc cơ chế và điều kiện của nhà cung cấp đó.
- **Device-bound passkey — passkey gắn với thiết bị:** bị ràng buộc với thiết bị theo cơ chế triển khai. Mất thiết bị có thể làm mất khả năng sử dụng passkey này.
- **Local user verification — xác minh người dùng cục bộ:** kiểm tra trên phương tiện xác thực, chẳng hạn PIN hoặc sinh trắc học. Dịch vụ nhận kết quả theo giao thức, không nhận mẫu vân tay hay khuôn mặt chỉ vì người dùng đăng nhập bằng passkey.

Mất điện thoại không đồng nghĩa mọi passkey đã mất. Cần kiểm tra còn passkey khác đã đăng ký hoặc còn khả năng sử dụng bản đồng bộ hay không. Ngược lại, không nên hứa rằng dịch vụ có thể tái tạo khóa riêng của passkey gắn với thiết bị chỉ từ tên tài khoản.

### 4.3. Recovery code và backup code

**Recovery code — mã khôi phục** và **backup code — mã dự phòng** thường được sản phẩm dùng để gọi các mã được cấp trước, lưu lại và dùng khi không sử dụng được phương thức thông thường. Trong một số sản phẩm, hai tên này chỉ cùng một loại mã; trong sản phẩm khác, chúng có phạm vi khác nhau.

Cần đọc chính sách cụ thể để biết mã:

- Thay thế một bước MFA hay khởi động một quy trình khôi phục riêng.
- Có cần dùng cùng mật khẩu hoặc bằng chứng khác không.
- Được dùng một lần, được thay bộ mới hoặc bị vô hiệu hóa trong trường hợp nào.

Không suy ra rằng ai giữ một mã dự phòng đều được toàn quyền đổi email, mật khẩu và MFA. Tên gọi của mã không đủ để xác định quyền mà nó cấp.

## 5. Nhóm thuật ngữ về các luồng khôi phục

| Thuật ngữ | Cách hiểu | Ví dụ hoặc giới hạn |
| --- | --- | --- |
| Account recovery | Khôi phục khả năng xác thực và truy cập một tài khoản hiện có khi không dùng được đường thông thường | Có thể bao gồm thay yếu tố bị mất; không tự cấp thêm quyền nghiệp vụ |
| Password change | Đổi mật khẩu trong bối cảnh đã xác lập quyền thực hiện | Người dùng đang truy cập chọn thay mật khẩu và đáp ứng yêu cầu xác thực lại |
| Password reset | Đặt lại mật khẩu qua đường được phép khi không sử dụng được mật khẩu hiện tại | Không mặc nhiên tắt MFA |
| MFA reset | Đặt lại hoặc thay thế cấu hình MFA theo phạm vi đã được cấp phép | Từ “reset” phải chỉ rõ yếu tố nào bị gỡ và điều kiện đăng ký lại |
| Account unlock | Mở khóa tài khoản khỏi một trạng thái hạn chế | Không đồng nghĩa đặt lại mật khẩu hoặc kết luận tài khoản không bị xâm nhập |
| Account reinstatement | Khôi phục trạng thái hoạt động của tài khoản bị đình chỉ theo chính sách | Có thể thuộc xử lý vi phạm hoặc quản trị, tách biệt với chứng minh quyền truy cập |
| Compromised-account recovery | Khôi phục khi nghi hoặc biết tài khoản đã bị chiếm đoạt | Cần xem xét kênh, yếu tố và phiên có thể đã thuộc kẻ tấn công |
| Re-enrollment | Đăng ký lại phương thức hoặc phương tiện xác thực | Thêm ứng dụng OTP mới sau khi được phép thay yếu tố cũ |
| Recovery channel | Kênh được dùng trong quy trình khôi phục | Email hoặc kênh khác đã được thiết lập theo chính sách; không tự đồng nghĩa với yếu tố đủ mạnh |
| Recovery contact | Người hoặc điểm liên hệ hỗ trợ khôi phục theo mô hình sản phẩm | Quyền của họ phụ thuộc thiết kế; không mặc định được toàn quyền lấy tài khoản |

“Khôi phục thiết bị” cũng cần nói rõ đối tượng. Khôi phục bản sao lưu của điện thoại, khôi phục tài khoản tại nhà cung cấp đồng bộ và khôi phục quyền truy cập vào một ứng dụng là ba quy trình có thể thuộc ba hệ thống khác nhau.

Trong đăng nhập liên kết, **Identity Provider — IdP**, hay nhà cung cấp danh tính, chịu trách nhiệm cho phần xác thực mà nó cung cấp. Ứng dụng sử dụng kết quả xác thực vẫn quản lý liên kết tài khoản, phiên và quyền của mình. Khôi phục tài khoản tại IdP không tự giải quyết mọi phiên hoặc thay đổi trong ứng dụng.

## 6. Nhóm thuật ngữ về yêu cầu, mã và token

### 6.1. Recovery request không phải recovery token

**Recovery request — yêu cầu khôi phục** là một đối tượng hoặc bản ghi nghiệp vụ, thể hiện có người yêu cầu thực hiện một hành động cho tài khoản. Nó có thể có mã yêu cầu, thời điểm tạo, mục đích, trạng thái và lịch sử xử lý.

**Request ID — mã định danh yêu cầu** giúp tra cứu đối tượng đó. Trừ khi hệ thống chủ ý thiết kế nó như một bí mật cấp quyền, việc biết mã yêu cầu không được coi là đủ quyền thực hiện thao tác. Trong đặc tả, nên tách rõ mã tra cứu và bí mật có khả năng cấp quyền.

**Recovery token — token khôi phục** là giá trị được dùng trong một bước khôi phục theo mục đích đã định. Token có thể được gửi trong liên kết hoặc nhập dưới dạng mã. Quyền thực tế phụ thuộc việc máy chủ kiểm tra token và trạng thái liên quan.

Một **recovery link — liên kết khôi phục** thường là URL đưa người dùng đến quy trình và có thể mang token. Liên kết là hình thức truyền hoặc mở luồng; token là giá trị nhạy cảm bên trong nếu thiết kế sử dụng nó. Việc tải trang qua liên kết không nhất thiết đã hoàn tất thay đổi tài khoản.

### 6.2. Những thuộc tính thường đi cùng token

| Thuật ngữ | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Secret | Bí mật | Giá trị nào phải được bảo vệ khỏi người không có quyền? |
| Bearer token | Token mà quyền sử dụng dựa vào việc nắm giữ nó và đáp ứng kiểm tra liên quan | Nếu bị lộ, người khác có thể dùng nó làm gì? |
| Scope hoặc purpose | Phạm vi hoặc mục đích | Token chỉ cho đổi mật khẩu hay còn cho thay MFA? |
| Binding | Sự ràng buộc | Token được gắn với tài khoản, yêu cầu và thao tác nào? |
| Expiration | Thời điểm hết hạn | Sau thời điểm nào máy chủ phải từ chối token? |
| TTL — Time To Live | Khoảng thời gian hiệu lực theo quy tắc đã định | TTL bắt đầu từ lúc phát hành hay một mốc khác? |
| Single-use | Dùng một lần | Khi nào quyền được tiêu thụ và làm sao ngăn sử dụng lại? |
| Invalidation | Làm mất hiệu lực | Khi nào token bị vô hiệu hóa trước hạn hoặc do thay đổi trạng thái? |
| Entropy hoặc unpredictability | Độ khó đoán của giá trị bí mật | Kẻ tấn công có thể đoán ra giá trị hợp lệ trong điều kiện thực tế không? |

Một token còn hạn chưa chắc còn dùng được: nó có thể đã được sử dụng, bị hủy hoặc bị vô hiệu hóa sau một sự kiện bảo mật. Vì vậy, “hợp lệ” thường là kết quả của nhiều kiểm tra, không chỉ là so sánh thời gian.

Độ dài chuỗi cũng không tự bảo đảm khó đoán. Một giá trị dài được tạo từ thông tin tài khoản dễ biết vẫn có thể dự đoán được. Tương tự, mã hóa hình thức biểu diễn không tự tạo thêm bằng chứng hay quyền.

### 6.3. Challenge, replay và atomic consumption

**Challenge — thử thách xác thực** là dữ liệu hoặc yêu cầu mà bên xác thực dùng để kiểm tra một phản hồi trong một ngữ cảnh cụ thể. Chẳng hạn, dịch vụ có thể yêu cầu phương tiện xác thực tạo chữ ký cho một thử thách. Challenge không mặc nhiên là bí mật cấp quyền như bearer token.

**Replay — phát lại** là việc dùng lại một bằng chứng hoặc thông điệp trước đó để cố được chấp nhận thêm lần nữa. Chữ “one-time” chỉ có ý nghĩa an toàn khi cơ chế thực sự ngăn việc sử dụng lại theo yêu cầu của nó.

**Atomic consumption — tiêu thụ quyền một cách nguyên tử** diễn tả yêu cầu kiểm tra và đánh dấu sử dụng sao cho hai thao tác cạnh tranh không cùng tiêu thụ một quyền dùng một lần để thực hiện hai thay đổi độc lập. Thuật ngữ này nói về tính nhất quán của việc thực thi; nó không chỉ là việc giao diện vô hiệu hóa nút bấm.

**Idempotency — tính lũy đẳng** diễn tả việc gửi lại cùng một thao tác không tạo thêm tác động nghiệp vụ ngoài tác động dự định. Nó hữu ích khi trình duyệt gửi lại yêu cầu sau lỗi mạng, nhưng không thay thế kiểm tra quyền hoặc đặc tính dùng một lần của token.

### 6.4. Hashing, encryption và encoding

Ba từ này thường xuất hiện khi thảo luận cách lưu hoặc truyền bí mật:

- **Hashing — băm:** tạo giá trị băm theo một hàm; không phải cơ chế giải mã để lấy lại đầu vào. Cách băm phù hợp phụ thuộc loại dữ liệu, độ khó đoán và mục tiêu bảo vệ.
- **Encryption — mã hóa có khóa:** biến dữ liệu thành dạng cần khóa phù hợp để khôi phục nội dung.
- **Encoding — mã hóa biểu diễn:** đổi cách biểu diễn, như Base64 hoặc mã hóa ký tự trong URL; không tự giữ bí mật dữ liệu.

Không dùng câu “token đã mã hóa nên an toàn” nếu thực tế chỉ chuyển sang Base64. Băm cũng không tự cứu được một mã có không gian đoán quá nhỏ nếu không có các biện pháp bảo vệ phù hợp.

## 7. Nhóm thuật ngữ về phiên và quyền sau khôi phục

### 7.1. Session, cookie, access token và refresh token

| Thuật ngữ | Giải thích | Điều cần tránh suy diễn |
| --- | --- | --- |
| Session | Phiên: trạng thái hoặc ngữ cảnh cho phép các yêu cầu tiếp theo được gắn với một lần xác lập truy cập | Phiên không nhất thiết chỉ tồn tại trong một tab trình duyệt |
| Session cookie | Cookie dùng để tham chiếu hoặc mang dữ liệu liên quan đến phiên theo thiết kế | Xóa cookie trên một trình duyệt không tự thu hồi mọi phiên ở máy chủ |
| Access token | Token được dùng để truy cập tài nguyên trong phạm vi và thời hạn áp dụng | Token khôi phục không tự là access token |
| Refresh token | Token dùng để xin access token mới theo cơ chế áp dụng | Thu hồi nó không bảo đảm mọi access token đã phát hành lập tức mất hiệu lực |
| Recovery session | Phiên phục vụ một phần hoặc toàn bộ quá trình khôi phục | Cần quy định quyền; không mặc nhiên được mọi quyền như phiên thông thường |
| Restricted session | Phiên bị giới hạn quyền hoặc chức năng | Giới hạn phải được thực thi tại API, không chỉ bằng cách ẩn nút |
| Step-up authentication | Xác thực bổ sung để đáp ứng yêu cầu cao hơn cho một hành động | Đã có phiên không có nghĩa được bỏ qua mọi kiểm tra bổ sung |
| Reauthentication | Xác thực lại trước một thao tác hoặc sau một sự kiện | Có thể cần phương thức phù hợp với rủi ro, không chỉ một lần nhấp xác nhận |

Cookie và token có thể liên quan trong cùng một thiết kế nhưng không đồng nghĩa. Cookie là cơ chế lưu và gửi dữ liệu trong trình duyệt; token là giá trị có ý nghĩa theo giao thức hoặc ứng dụng. Cách chọn cơ chế ảnh hưởng đến việc bảo vệ và thu hồi, nhưng không thể suy ra chỉ từ tên gọi “session”.

### 7.2. Credential revocation và session revocation

**Credential revocation — thu hồi thông tin xác thực** là làm cho một thông tin xác thực không còn được chấp nhận. Ví dụ, vô hiệu hóa passkey đã đăng ký trên tài khoản làm cho dịch vụ từ chối sử dụng thông tin xác thực đó trong những lần xác thực tiếp theo.

**Session revocation — thu hồi phiên** là làm mất khả năng sử dụng phiên theo cơ chế của hệ thống. Một phiên được tạo trước khi passkey bị thu hồi có thể cần được xử lý riêng. Thu hồi passkey cũng không có nghĩa đã xóa khóa riêng khỏi thiết bị hoặc khỏi mọi bản đồng bộ.

**Logout — đăng xuất** có thể chỉ kết thúc phiên hiện tại. **Global logout — đăng xuất toàn bộ** cần được định nghĩa về phạm vi: những ứng dụng nào, những loại token nào và thời gian thực thi đến đâu. Không nên dùng cụm từ này nếu chỉ xóa cookie trên máy đang sử dụng.

**Remembered device — thiết bị được ghi nhớ** thường là trạng thái tin cậy hoặc thuận tiện được dịch vụ lưu để điều chỉnh trải nghiệm xác thực. Nó không tự chứng minh thiết bị đang do đúng người sử dụng và cần được xem xét khi xử lý mất thiết bị.

## 8. Nhóm thuật ngữ về trạng thái và quyết định

Một yêu cầu khôi phục thường tồn tại qua nhiều bước. Hiểu đúng tên trạng thái giúp tránh nhầm việc “đã được cho phép” với việc “đã hoàn tất”.

| Trạng thái hoặc quyết định | Cách hiểu |
| --- | --- |
| Initiated hoặc requested | Yêu cầu đã được khởi tạo; chưa nói lên người yêu cầu có quyền |
| Pending verification | Đang chờ hoàn tất kiểm tra bằng chứng |
| Pending review | Đang chờ xét duyệt theo quy trình |
| Approved hoặc authorized | Đã có quyết định cho phép phạm vi thao tác cụ thể; có thể vẫn chưa thực hiện thay đổi |
| Completed | Thay đổi và các điều kiện hoàn tất đã được thực hiện theo định nghĩa của luồng |
| Rejected hoặc denied | Yêu cầu bị từ chối theo điều kiện hoặc quyết định áp dụng |
| Expired | Yêu cầu hoặc quyền đã hết hạn |
| Cancelled | Yêu cầu bị hủy theo cơ chế cho phép |

Tên chính xác tùy hệ thống. Điều quan trọng là điều kiện chuyển trạng thái phải rõ ràng và được thực thi ở máy chủ.

```text
REQUESTED
    → PENDING_VERIFICATION
    → AUTHORIZED_FOR_MFA_REPLACEMENT
    → COMPLETED

Nhánh khác tùy chính sách: PENDING_REVIEW, REJECTED, EXPIRED, CANCELLED.
```

Trong ví dụ này, `AUTHORIZED_FOR_MFA_REPLACEMENT` diễn đạt rõ quyền thay MFA. Nếu chỉ ghi `VERIFIED`, người đọc không biết đã kiểm tra điều gì và còn được phép làm gì tiếp theo.

**Cooldown — thời gian chờ** là khoảng trì hoãn theo chính sách trước một hành động hoặc lần thử tiếp theo. **Rate limiting — giới hạn tần suất** là kiểm soát số lượng hoặc tốc độ thao tác theo các chiều được chọn. Hai cơ chế có thể kết hợp, nhưng một khoảng chờ trên giao diện không tự tạo ra giới hạn tần suất phía máy chủ.

## 9. Nhóm thuật ngữ về rủi ro và lạm dụng

| Thuật ngữ | Ý nghĩa trong khôi phục | Ví dụ dễ hình dung |
| --- | --- | --- |
| Account takeover — ATO | Chiếm quyền kiểm soát tài khoản trái phép | Kẻ tấn công thay mật khẩu và MFA qua một đường khôi phục yếu |
| Account enumeration | Dò xem tài khoản nào tồn tại | So sánh thông báo hoặc hành vi của chức năng quên mật khẩu |
| Phishing | Lừa người dùng tiết lộ bí mật hoặc thực hiện hành động trên bối cảnh giả mạo | Trang giả yêu cầu nhập mã dự phòng |
| Social engineering | Thao túng con người để vượt quy trình hoặc tiết lộ thông tin | Giả làm người dùng khẩn cấp để yêu cầu nhân viên gỡ MFA |
| SIM swap | Chuyển quyền kiểm soát số điện thoại sang SIM do kẻ khác sử dụng | Kẻ tấn công nhận được SMS vốn gửi đến số của nạn nhân |
| Brute force | Thử nhiều giá trị để tìm bí mật hoặc mã hợp lệ | Thử liên tục mã khôi phục có không gian đoán nhỏ |
| Replay attack | Dùng lại bằng chứng hoặc thông điệp đã có | Gửi lại token đã sử dụng để cố thực hiện thêm thay đổi |
| Race condition | Kết quả phụ thuộc việc các thao tác cạnh tranh xen kẽ không được kiểm soát đúng | Hai yêu cầu cùng kiểm tra mã còn dùng được rồi cùng đổi thông tin |
| Recovery abuse | Lạm dụng chức năng khôi phục để gây tác động ngoài mục đích hợp lệ | Gửi hàng nghìn email hoặc tạo nhiều yêu cầu làm quá tải hỗ trợ |
| Denial of service | Làm suy giảm hoặc ngăn khả năng sử dụng dịch vụ | Lạm dụng cơ chế khóa để người dùng hợp lệ không truy cập được |

**Threat — mối đe dọa** chỉ nguồn hoặc tình huống có thể gây hại; **vulnerability — điểm yếu** là điều kiện có thể bị khai thác; **impact — tác động** là hậu quả nếu sự việc xảy ra. “Email bị chiếm quyền” có thể là tình huống đe dọa, còn việc cho email đó đủ quyền tắt mọi yếu tố là một lựa chọn thiết kế cần được đánh giá trong bối cảnh rủi ro.

Không phải mọi lần khôi phục thất bại đều là tấn công. Người dùng có thể nhập sai mã, dùng liên kết cũ hoặc gặp lỗi mạng. Phân loại sự kiện giúp vận hành đưa ra phản hồi phù hợp mà không phải tiết lộ thêm dữ liệu nhạy cảm cho bên chưa xác thực.

## 10. Thuật ngữ về thông báo, nhật ký và xử lý thủ công

**Notification — thông báo** là hành động cho một bên biết sự kiện đã xảy ra hoặc sắp xảy ra. Gửi thông báo đổi MFA tới email cũ có thể hỗ trợ phát hiện thay đổi trái phép. Nó không đồng nghĩa chủ tài khoản đã đọc hoặc phê duyệt thay đổi.

**Audit log hoặc audit trail — nhật ký hoặc dấu vết kiểm toán** ghi lại các sự kiện và quyết định cần truy vết: yêu cầu nào, loại thao tác nào, kết quả nào, chủ thể thực hiện và thời điểm. Nhật ký không nên chứa token thô, mật khẩu hoặc mã dự phòng có thể dùng lại.

**Manual review — xét duyệt thủ công** là việc người có thẩm quyền đánh giá yêu cầu theo quy trình. **Escalation — chuyển cấp** là đưa tình huống vượt thẩm quyền hoặc độ phức tạp hiện tại đến cấp xử lý thích hợp. Cả hai đều cần điều kiện và giới hạn, không có nghĩa nhân viên được tự bỏ mọi kiểm tra.

**Exception — ngoại lệ** cần được diễn đạt thành một cơ chế có căn cứ và thẩm quyền nếu sản phẩm hỗ trợ. “Nhân viên thấy hợp lý” là mô tả quá mơ hồ để xác định bằng chứng, trách nhiệm hoặc quyền được cấp.

## 11. Ví dụ đọc một luồng bằng các thuật ngữ đã học

### 11.1. Tình huống

Minh mất điện thoại chứa ứng dụng TOTP và một passkey. Minh vẫn nhớ mật khẩu, còn mã dự phòng được lưu riêng nhưng không còn quyền truy cập email trên điện thoại. Dịch vụ quy định mã dự phòng có thể thay bước OTP sau khi mật khẩu hợp lệ, rồi cho phép đăng ký lại MFA theo chính sách.

### 11.2. Diễn giải từng bước

1. **Minh nhập email đăng nhập.** Email đang được dùng như `account identifier`. Bước này tìm tài khoản, chưa chứng minh Minh là chủ tài khoản.
2. **Hệ thống kiểm tra mật khẩu.** Một bằng chứng xác thực đã được kiểm tra. Điều đó chưa tự cho phép bỏ yếu tố thứ hai.
3. **Minh cung cấp mã dự phòng.** Theo chính sách của ví dụ, đây là bằng chứng thay thế bước OTP. Máy chủ kiểm tra phạm vi, trạng thái và việc dùng lại mã.
4. **Hệ thống cho phép thay MFA.** Đây là quyết định `authorization` cho một hành động cụ thể. Nếu dùng phiên hạn chế, quyền của phiên phải được kiểm tra tại các chức năng liên quan.
5. **Minh đăng ký phương thức mới.** Đây là `re-enrollment`. Yếu tố cũ được xử lý theo điều kiện chốt thay đổi để tránh trạng thái đã gỡ cũ nhưng chưa có mới.
6. **Hệ thống xử lý tài sản trên thiết bị mất.** Việc thu hồi passkey đã đăng ký là `credential revocation`; thu hồi các phiên liên quan là `session revocation`. Hai việc cần được phân biệt.
7. **Hệ thống ghi nhận và thông báo.** `Audit trail` phục vụ truy vết; `notification` giúp phát hiện thay đổi. Chúng không thay thế bằng chứng đã dùng để cấp quyền ở bước trước.

Nếu không còn mã dự phòng hoặc bằng chứng được chấp nhận khác, quy trình có thể phải xét duyệt hoặc không thể khôi phục. Không có thuật ngữ nào biến việc thiếu bằng chứng thành đủ quyền chỉ bằng cách gọi yêu cầu là “khẩn cấp”.

### 11.3. Một bản ghi khái niệm

```text
request_id: R-EXAMPLE-42
account_id: A-EXAMPLE-18
purpose: REPLACE_LOST_MFA
evidence_result: PASSWORD_AND_BACKUP_CODE_ACCEPTED
state: AUTHORIZED_FOR_MFA_REPLACEMENT
granted_scope: ENROLL_REPLACEMENT_MFA
session_policy: RESTRICTED_UNTIL_COMPLETION
```

Đây là ví dụ minh họa ngôn ngữ đặc tả, không phải cấu trúc dữ liệu bắt buộc hoặc mã triển khai. Bản ghi không chứa mật khẩu, mã dự phòng hay token thô. Các tên trường giúp người đọc tách được đối tượng yêu cầu, bằng chứng đã kiểm tra, quyết định và quyền được cấp.

## 12. Thay câu mơ hồ bằng câu có thể kiểm chứng

| Câu dễ gây hiểu sai | Cách diễn đạt rõ hơn |
| --- | --- |
| “Đã xác minh người dùng” | “Đã kiểm tra mã gửi đến kênh email đã đăng ký; kết quả này được dùng cho bước xác minh email” |
| “Token hợp lệ nên cho vào tài khoản” | “Token đáp ứng kiểm tra tài khoản, mục đích, thời hạn và trạng thái; chỉ cấp quyền đặt mật khẩu mới” |
| “Đã reset bảo mật” | “Đã thay phương thức OTP cũ bằng phương thức mới; chính sách xử lý phiên được áp dụng riêng” |
| “Đăng xuất mọi thiết bị rồi” | “Đã thu hồi các phiên và token trong phạm vi xác định; nêu rõ loại token còn hiệu lực và độ trễ nếu có” |
| “Có hai bước nên là MFA” | “Cần xác định hai bước sử dụng những loại yếu tố nào và cơ chế có đáp ứng chính sách MFA không” |
| “Passkey đã được khôi phục” | “Đã lấy lại khả năng dùng passkey qua cơ chế đồng bộ” hoặc “đã đăng ký passkey mới sau khôi phục” |
| “Email mới đã xác minh nên được đổi chủ tài khoản” | “Đã kiểm tra khả năng nhận mã tại email mới; quyền thay email tài khoản cần bằng chứng và quyết định riêng” |
| “Hỗ trợ đã duyệt, vậy là hoàn tất” | “Yêu cầu đã được phê duyệt; còn phải thực hiện thay đổi và đáp ứng điều kiện hoàn tất” |

Khi đọc một yêu cầu sản phẩm, hãy tìm bốn thành phần: **đối tượng**, **bằng chứng**, **quyền được cấp** và **thay đổi có hiệu lực**. Thiếu một thành phần thường làm câu mô tả khó triển khai hoặc khó kiểm tra.

## 13. Tự kiểm tra thuật ngữ

### Câu 1: Mã yêu cầu có phải bí mật khôi phục không?

Nhân viên hỗ trợ đưa người dùng một mã để tra cứu tiến độ. Có nên cho phép dùng mã đó để đổi mật khẩu?

**Gợi ý:** Không suy ra quyền đổi mật khẩu từ khả năng tra cứu. Cần phân biệt `request ID` với bí mật hoặc bằng chứng được thiết kế để cấp quyền khôi phục.

### Câu 2: Xác minh email có phải kiểm chứng danh tính không?

Một người nhập đúng mã nhận qua email. Hệ thống đã kiểm chứng danh tính ngoài đời của người đó chưa?

**Gợi ý:** Chưa thể kết luận như vậy. Kết quả kiểm tra liên quan đến khả năng lấy mã tại kênh email. Kiểm chứng danh tính ngoài đời và liên kết danh tính với tài khoản là các kết luận khác.

### Câu 3: Gỡ passkey có phải đăng xuất thiết bị không?

Một passkey bị vô hiệu hóa trong tài khoản. Phiên được tạo trước đó trên điện thoại mất có chắc đã dừng hoạt động không?

**Gợi ý:** Không chắc. `Credential revocation` và `session revocation` tác động đến các đối tượng khác nhau. Cần biết cơ chế và chính sách xử lý phiên.

### Câu 4: Hai bước có đồng nghĩa hai yếu tố không?

Người dùng nhập mật khẩu rồi trả lời một câu hỏi bí mật. Có thể gọi ngay là 2FA không?

**Gợi ý:** Không nên. Cả hai chủ yếu dựa vào điều người dùng biết. Số bước không tự chứng minh các loại yếu tố độc lập.

### Câu 5: Token chưa hết hạn có chắc còn dùng được không?

Người dùng mở lại liên kết sau khi đã hoàn tất đặt mật khẩu mới. Thời gian hết hạn vẫn chưa đến. Hệ thống có phải cho dùng tiếp không?

**Gợi ý:** Không. Thời hạn chỉ là một điều kiện. Token dùng một lần đã được tiêu thụ phải bị từ chối cho lần sử dụng lại, dù chưa đến thời điểm hết hạn.

## 14. Các cặp cần ghi nhớ

- **Định danh / bằng chứng:** biết tài khoản nào khác với chứng minh quyền truy cập tài khoản đó.
- **Xác thực / phân quyền:** kiểm tra chủ thể khác với cho phép một hành động.
- **Xác minh kênh / kiểm chứng danh tính:** nhận được mã không tự chứng minh danh tính ngoài đời hoặc toàn bộ quyền sở hữu.
- **Thông tin xác thực / phương tiện xác thực / yếu tố:** thứ được dùng để xác thực, thành phần sử dụng nó và loại bằng chứng cần được diễn đạt riêng.
- **Mã yêu cầu / token khôi phục:** tra cứu tiến độ khác với nắm giữ một bí mật có thể cấp quyền.
- **Đặt lại mật khẩu / thay MFA:** hai thay đổi có mục đích và điều kiện khác nhau.
- **Thu hồi thông tin xác thực / thu hồi phiên:** ngăn xác thực lần sau khác với ngăn tiếp tục sử dụng quyền truy cập đã cấp.
- **Phê duyệt / hoàn tất:** quyết định cho phép khác với thay đổi đã được thực hiện đầy đủ.
