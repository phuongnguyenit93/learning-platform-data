# Kẻ tấn công kiểm soát hộp thư (Compromised mailbox attacker)

Trong chương **Recovery Threat Model** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, tình huống này xem xét một đối thủ có thể đọc hoặc thao tác với email khôi phục của người dùng. Phạm vi là luồng lấy lại tài khoản khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực; mục tiêu là tránh biến quyền truy cập hộp thư thành quyền chiếm đoạt tài khoản ở dịch vụ.

Điểm mấu chốt: **một token email hợp lệ chứng minh người trình token có quyền tiếp cận thông điệp đó; nó không tự chứng minh người ấy là chủ hợp pháp của tài khoản**. Khi hộp thư đã bị xâm nhập, token ngẫu nhiên mạnh, thời hạn ngắn và cơ chế dùng một lần vẫn cần thiết, nhưng không giải quyết được việc token được gửi đúng vào kênh mà đối thủ đang kiểm soát.

Sau bài học, người học cần có khả năng:

- Xác định tài sản, năng lực của đối thủ và ranh giới tin cậy liên quan đến email khôi phục.
- Giải thích đường đi từ hộp thư bị xâm nhập đến việc thay mật khẩu, vô hiệu MFA và đăng ký thiết bị của đối thủ.
- Phân biệt bằng chứng độc lập với nhiều bước xác minh cùng phụ thuộc vào một hộp thư.
- Thiết kế luồng khôi phục có kiểm soát token, session, thay đổi yếu tố xác thực và xử lý khi không còn bằng chứng đủ mạnh.
- Nêu được rủi ro còn lại của hệ thống mà email là bằng chứng khôi phục duy nhất.

## 1. Tình huống mở đầu: MFA mạnh nhưng khôi phục yếu

Lan có một tài khoản chứa dữ liệu nhạy cảm. Đăng nhập bình thường yêu cầu mật khẩu và passkey. Địa chỉ email của Lan được dùng để nhận thông báo và liên kết đặt lại mật khẩu.

Một đối thủ có quyền đọc hộp thư, nhưng không có passkey. Nếu dịch vụ cho phép chuỗi thao tác sau, passkey không còn bảo vệ được đường khôi phục:

1. Yêu cầu đặt lại mật khẩu bằng địa chỉ email.
2. Mở liên kết trong hộp thư và đặt mật khẩu mới.
3. Chọn “Tôi mất thiết bị xác thực”.
4. Nhận một mã khác qua cùng hộp thư để xóa passkey cũ.
5. Đăng ký passkey của đối thủ và nhận một session đầy đủ.

Mỗi bước có thể dùng token hợp lệ. Lỗi nằm ở chính sách cấp quyền: hệ thống dùng cùng một kênh đã bị xâm nhập để thay cả mật khẩu lẫn yếu tố xác thực vốn được kỳ vọng độc lập với email.

Không phải mọi chức năng “đặt lại mật khẩu bằng email” đều có cùng mức rủi ro. Nếu sau khi đổi mật khẩu, hệ thống vẫn yêu cầu passkey đã đăng ký để đăng nhập, đối thủ chưa hoàn tất chiếm đoạt tài khoản. Threat model phải theo dõi đến quyền truy cập thực tế, thay vì dừng ở việc một biểu mẫu đã được xác nhận.

## 2. Tài sản cần bảo vệ và định nghĩa thành công của đối thủ

Tài sản không chỉ là mật khẩu. Luồng recovery có thể thay đổi toàn bộ quan hệ giữa một người và tài khoản.

| Tài sản hoặc thuộc tính | Vì sao cần bảo vệ |
|---|---|
| Ràng buộc chủ tài khoản | Ngăn người có hộp thư tạm thời trở thành chủ tài khoản lâu dài |
| Passkey, MFA và mã dự phòng | Ngăn xóa yếu tố cũ hoặc thêm yếu tố của đối thủ |
| Email và kênh khôi phục đã đăng ký | Ngăn thay địa chỉ nhận bằng chứng, cảnh báo và yêu cầu trợ giúp |
| Session, refresh token và thiết bị được tin cậy | Ngăn đối thủ duy trì quyền truy cập sau khi nạn nhân lấy lại mật khẩu |
| Dữ liệu và hành động nhạy cảm | Ngăn đọc dữ liệu, xuất dữ liệu hoặc thay đổi thông tin quan trọng |
| Khả năng khôi phục của người dùng thật | Tránh thiết kế khiến đối thủ dễ khóa nạn nhân ngoài tài khoản |
| Lịch sử và bằng chứng điều tra | Giữ được dấu vết dù email cảnh báo bị xóa |

Cần ghi rõ tiêu chí thành công của đối thủ. Một số mục tiêu khác nhau là:

- **Chiếm đoạt:** có session đủ quyền để sử dụng tài khoản như chủ sở hữu.
- **Thiết lập chỗ đứng lâu dài:** thêm passkey, ứng dụng được cấp quyền hoặc kênh khôi phục của đối thủ.
- **Khóa người dùng thật:** vô hiệu yếu tố của nạn nhân hoặc lạm dụng quy trình chờ và hủy.
- **Che giấu:** xóa email cảnh báo, làm người dùng chậm phát hiện.
- **Truy cập trong thời gian ngắn:** lấy dữ liệu trước khi recovery bị đảo ngược.

Một thiết kế ngăn được việc thêm passkey mới nhưng vẫn cấp session cho phép tải toàn bộ dữ liệu chưa bảo vệ được tài sản dữ liệu.

## 3. Mô hình năng lực: đối thủ thực sự kiểm soát điều gì?

Không nên gộp mọi sự cố email thành một mức quyền duy nhất. Cần phân biệt việc lộ một thông điệp với việc kiểm soát liên tục hộp thư.

| Biến thể | Năng lực giả định | Hệ quả đối với recovery |
|---|---|---|
| Lộ một email recovery | Đọc được một token cụ thể, có thể chưa đọc được email tiếp theo | Token đó phải được coi là đã lộ; không tự suy ra toàn bộ hộp thư bị kiểm soát lâu dài |
| Quyền đọc hộp thư đang hoạt động | Đọc email mới, tìm lịch sử và lấy các mã tiếp theo | Gửi lại OTP qua email không tạo thêm bằng chứng độc lập |
| Quyền đọc, gửi và xóa thư | Nhận token, mạo danh trao đổi email và che cảnh báo | Email trả lời hoặc thư “tôi xác nhận” không đủ để chứng minh chủ tài khoản |
| Quyền truy cập kéo dài | Có thể tồn tại qua session email, quyền ứng dụng hoặc quy tắc chuyển tiếp | Chỉ đổi mật khẩu email có thể chưa chấm dứt mọi đường truy cập |
| Đọc được nhiều kênh | Ví dụ, hộp thư và nơi lưu mã dự phòng đều bị lộ | Một bằng chứng chỉ độc lập khi đối thủ trong mô hình chưa kiểm soát nó |

Trong kịch bản chính của bài, giả định đối thủ đọc được email recovery mới và có thể theo dõi hộp thư đủ lâu để tham gia toàn bộ quy trình. Khả năng gửi, xóa và chuyển tiếp là các biến thể cần kiểm tra thêm.

**Không mặc định** đối thủ có passkey trên thiết bị của nạn nhân, mã dự phòng được giữ riêng, hay một session đã xác thực mạnh tại dịch vụ. Tuy nhiên, cũng không mặc định những tài sản ấy an toàn nếu chúng được đồng bộ, lưu trữ hoặc khôi phục qua chính tài khoản email bị xâm nhập.

Một passkey có thể chống phishing ở bước đăng nhập, nhưng câu hỏi ở đây là đường khôi phục passkey hoặc tài khoản đồng bộ có phụ thuộc vào cùng hộp thư hay không. Phải xét toàn bộ chuỗi phụ thuộc, không chỉ tên công nghệ.

### Đối thủ có thể biết nhiều thông tin thật

Lịch sử email thường chứa tên, giao dịch, hóa đơn, ngày tham gia dịch vụ và trao đổi hỗ trợ. Vì vậy, các câu hỏi như “giao dịch gần nhất là gì?” hoặc “bạn đăng ký ngày nào?” có thể bị trả lời đúng bởi người đang đọc hộp thư.

Thông tin đúng giúp đối chiếu hồ sơ, nhưng không tự trở thành bí mật chứng minh quyền sở hữu. Đối thủ cũng có thể dùng dữ liệu đó để tạo một câu chuyện hỗ trợ khách hàng thuyết phục.

## 4. Ranh giới tin cậy: đọc thư không đồng nghĩa được cấp lại toàn quyền

Luồng khôi phục đi qua ít nhất bốn ranh giới:

1. Từ người gửi yêu cầu đến dịch vụ: chưa biết người gửi có phải chủ tài khoản hay không.
2. Từ dịch vụ sang hạ tầng email: token ra khỏi miền kiểm soát trực tiếp của dịch vụ.
3. Từ token được trình lại sang hồ sơ recovery: phải kiểm tra đúng tài khoản, lần yêu cầu, mục đích và trạng thái.
4. Từ recovery sang cấp quyền: đây là nơi quyết định có được đổi yếu tố, tạo session và truy cập dữ liệu hay không.

~~~mermaid
flowchart TD
    A["Người yêu cầu chưa được xác minh"] --> B["Dịch vụ tạo hồ sơ recovery"]
    B --> C["Hộp thư nhận liên kết"]
    X["Đối thủ kiểm soát hộp thư"] --> C
    C --> D["Người yêu cầu trình token email"]
    D --> E["Chỉ xác nhận khả năng tiếp cận email"]
    E --> F{"Có bằng chứng độc lập đủ mạnh?"}
    F -->|Có| G["Đánh giá chính sách và hoàn tất recovery"]
    F -->|Không| H["Xử lý tăng cường hoặc chưa cấp quyền"]
    G --> I["Thiết lập yếu tố và xử lý session"]
~~~

Bước dễ sai nhất là đổi nhãn của bằng chứng: từ “token được gửi tới email đã đăng ký” thành “chủ tài khoản đã được xác minh”.

Một bất biến bảo mật có thể viết như sau:

> Không được dùng riêng khả năng đọc hộp thư để vượt qua yêu cầu bằng chứng độc lập mà chính sách recovery của tài khoản đòi hỏi.

Bất biến này phải áp dụng cho giao diện tự phục vụ, API, luồng hỗ trợ và thao tác quản trị. Một quy trình hỗ trợ có thể bỏ qua nó sẽ trở thành đường recovery thực tế của hệ thống.

## 5. Những đường tấn công cần mô hình hóa

### 5.1. Đổi mật khẩu rồi bỏ qua MFA

Đối thủ dùng token email để đổi mật khẩu. Nếu endpoint hoàn tất tự cấp một session đầy đủ, yêu cầu MFA ở màn hình đăng nhập đã bị bỏ qua.

Cần quyết định riêng hai việc: cho phép thay mật khẩu và cho phép tạo session. Nếu tài khoản vẫn yêu cầu yếu tố đã đăng ký, việc đặt lại mật khẩu không được ngầm xóa yêu cầu ấy.

### 5.2. “Mất tất cả thiết bị” trở thành lối tắt

Luồng dự phòng cho mất MFA hoặc passkey gửi một mã email khác. Hai mã đến cùng một hộp thư vẫn nằm trong một miền bị xâm nhập. Đối thủ không phải phá yếu tố thứ hai; dịch vụ đã cho phép thay thế yếu tố đó bằng email.

### 5.3. Đổi email trước, recovery sau

Nếu một recovery session quyền hạn thấp được phép đổi email nhận mã, đối thủ có thể chuyển các bước tiếp theo về địa chỉ của mình. Việc xác nhận địa chỉ mới chỉ chứng minh đối thủ đọc được địa chỉ mới, không chứng minh họ được phép chuyển quyền sở hữu tài khoản cũ.

Kênh nhận bằng chứng phải lấy từ cấu hình đáng tin cậy trước yêu cầu recovery. Việc thay kênh là một hành động nhạy cảm riêng, cần thỏa chính sách tương ứng.

### 5.4. Củng cố quyền kiểm soát sau lần truy cập đầu tiên

Đối thủ có thể thêm passkey, tạo mã dự phòng, cấp quyền cho ứng dụng hoặc giữ refresh token. Sau đó, việc nạn nhân đổi lại mật khẩu có thể không đủ để loại bỏ đối thủ.

Threat model phải bao gồm bước thiết lập lại thông tin xác thực và quyền truy cập tồn tại sau recovery, không chỉ bước nhận email.

### 5.5. Che cảnh báo hoặc lạm dụng cơ chế hủy

Đối thủ có quyền xóa thư có thể che thông báo “tài khoản của bạn đang được khôi phục”. Nếu một liên kết email có thể hủy vô điều kiện mọi recovery, người đang kiểm soát hộp thư còn có thể liên tục cản trở người dùng thật.

Cảnh báo và hủy là các cơ chế khác nhau: cảnh báo giúp phát hiện; quyền hủy làm thay đổi trạng thái bảo mật. Cần quyết định mức bằng chứng cho quyền hủy, đồng thời cung cấp đường xử lý khi các bên tranh chấp quyền sở hữu.

### 5.6. Lợi dụng hỗ trợ khách hàng

Đối thủ trình bày đúng thông tin từ lịch sử thư để yêu cầu nhân viên bỏ MFA hoặc đổi địa chỉ recovery. Nếu hỗ trợ được phép thay đổi yếu tố chỉ dựa vào email và thông tin hồ sơ, giao diện tự phục vụ dù chặt chẽ cũng không đủ.

Quyền nhân viên, bằng chứng được chấp nhận, trường hợp phải chuyển cấp và dấu vết phê duyệt cần nằm trong cùng threat model.

## 6. Bằng chứng nào còn giá trị khi email bị xâm nhập?

Câu hỏi quan trọng không phải “đã có bao nhiêu bước?”, mà là “đối thủ có phải vượt qua thêm một miền kiểm soát độc lập hay không?”.

| Bằng chứng | Giá trị trong kịch bản này | Điều kiện và giới hạn |
|---|---|---|
| Liên kết hoặc OTP qua hộp thư bị xâm nhập | Chứng minh quyền tiếp cận thông điệp | Không phân biệt được nạn nhân với đối thủ |
| Email thứ hai đến cùng hộp thư, alias hoặc nơi chuyển tiếp chung | Không tăng tính độc lập | Khác địa chỉ hiển thị chưa có nghĩa là khác miền kiểm soát |
| Mật khẩu cũ | Có thể bổ sung trong một số tình huống | Có thể đã lộ cùng sự cố; không phù hợp khi mục tiêu recovery là mất mật khẩu |
| Passkey đã đăng ký trước sự cố | Có thể là bằng chứng mạnh | Kiểm tra ceremony của dịch vụ, challenge, RP ID, origin và yêu cầu xác minh người dùng theo chính sách; xét phụ thuộc vào đồng bộ và recovery |
| Mã dự phòng được tạo trước và giữ riêng | Có thể là bằng chứng sở hữu | Phải đủ khó đoán, dùng một lần và chưa bị lưu trong hộp thư bị lộ |
| Session ứng dụng có sẵn | Có thể hỗ trợ xác minh hoặc phản đối | Cookie đơn thuần không đồng nghĩa xác thực mạnh; xét thời điểm, mức xác thực, nguy cơ đánh cắp và step-up |
| Kênh khác đã đăng ký từ trước | Có thể bổ sung bằng chứng | Đánh giá quyền kiểm soát thực tế; SMS vẫn có rủi ro riêng như chuyển SIM và phishing |
| Thiết bị, IP, vị trí hoặc lịch sử hành vi | Tín hiệu đánh giá rủi ro | Có thể bị giả lập hoặc thay đổi hợp lệ; không tự là bằng chứng sở hữu |
| Danh tính hoặc hồ sơ được đối chiếu qua quy trình riêng | Có thể dùng ở dịch vụ phù hợp | Chỉ có ý nghĩa khi liên kết được với chủ tài khoản đã xác lập; cần quy trình kiểm tra, chống giả mạo và bảo vệ dữ liệu |

Không phải dịch vụ nào cũng đã biết danh tính pháp lý của người dùng. Thu thập giấy tờ ở thời điểm recovery cho một tài khoản trước đây ẩn danh không tự tạo ra mối liên hệ đáng tin cậy với chủ tài khoản cũ.

Cũng không nên biến mọi thất bại recovery thành yêu cầu gửi tài liệu nhạy cảm. Bằng chứng cần tương xứng với tài sản và mô hình danh tính của dịch vụ.

### Sự độc lập phải được kiểm tra theo chuỗi

Giả sử mã dự phòng được gửi vào email lúc tạo tài khoản, rồi người dùng để nguyên trong hộp thư. Khi hộp thư bị xâm nhập, mã ấy không còn độc lập.

Tương tự, hai kênh có thể nhìn khác nhau nhưng cùng phụ thuộc vào một tài khoản nền. Cần ghi lại cách mỗi kênh được thiết lập và cách khôi phục chính kênh đó.

## 7. Chọn chính sách theo khả năng xác minh thực tế

### Trường hợp A: còn bằng chứng độc lập đủ mạnh

Ví dụ, người dùng mất mật khẩu nhưng vẫn có passkey đã đăng ký. Luồng recovery có thể yêu cầu bằng chứng đó trước khi cấp lại quyền thích hợp.

Chính sách cần xác định rõ bằng chứng cho từng hành động: đổi mật khẩu, xóa yếu tố cũ, đổi email, thêm passkey và nhận session. Không suy ra mọi quyền chỉ từ việc đã qua một bước hợp lệ.

### Trường hợp B: có tín hiệu hỗ trợ nhưng chưa đủ để kết luận

Ví dụ, yêu cầu xuất phát từ một thiết bị quen thuộc, nhưng không còn yếu tố xác thực. Các tín hiệu có thể giúp phân luồng để xem xét thêm, yêu cầu bằng chứng phù hợp hoặc áp dụng thời gian chờ.

Thời gian chờ tạo cơ hội phát hiện và phản ứng; nó **không tự biến người giữ hộp thư thành chủ tài khoản**. Đối thủ có thể kiên nhẫn và chặn thông báo. Với hành động rủi ro cao, hết thời gian chờ mà không có phản đối chưa chắc là điều kiện đủ để cấp quyền.

### Trường hợp C: email là bằng chứng duy nhất còn lại

Nếu dịch vụ chưa từng thiết lập bằng chứng độc lập, hệ thống không thể phân biệt chắc chắn người dùng thật và đối thủ chỉ bằng dữ liệu email đó.

Có hai hệ quả thiết kế cần nhìn thẳng:

- Với tài sản đòi hỏi bảo đảm cao, có thể phải chưa cấp lại quyền cho đến khi đạt chính sách xác minh; một số tài khoản có thể không khôi phục được.
- Nếu sản phẩm chủ động chấp nhận email là gốc tin cậy để ưu tiên khả năng phục hồi, phải ghi nhận rằng việc chiếm hộp thư có thể kéo theo việc chiếm tài khoản. Token tốt chỉ giảm các rủi ro khác của đường email.

Quyết định này cần được xác lập trong chính sách sản phẩm. Nhân viên hỗ trợ không nên tự ứng biến một lối bỏ qua yêu cầu khi người yêu cầu gây áp lực.

Chính sách rõ ràng cũng giảm tình trạng người dùng bị yêu cầu thử các bằng chứng không thể đáp ứng hoặc bị chuyển vòng giữa các kênh hỗ trợ.


## 8. Thiết kế trạng thái recovery để không cấp quyền quá sớm

Một cách tổ chức là dùng hồ sơ recovery phía máy chủ và tách các trạng thái theo ý nghĩa bảo mật:

| Trạng thái | Ý nghĩa | Quyền được phép |
|---|---|---|
| `REQUESTED` | Đã tiếp nhận yêu cầu | Chưa có quyền đối với tài khoản |
| `EMAIL_PROVEN` | Token email hợp lệ đã được trình | Chỉ tiếp tục hồ sơ recovery; chưa được coi là chủ tài khoản |
| `EVIDENCE_VERIFIED` | Đạt bằng chứng mà chính sách yêu cầu | Chuyển sang bước chờ hoặc chuẩn bị hoàn tất theo chính sách |
| `WAITING` | Đang trong khoảng chờ, nếu có | Chưa nhận quyền vượt quá giới hạn đã quy định |
| `READY_TO_COMMIT` | Đã đáp ứng các điều kiện hoàn tất hiện hành | Chỉ được thực hiện thay đổi đã được phê duyệt |
| `COMPLETED` | Đã áp dụng các thay đổi và quyết định session | Quyền sau recovery được cấp theo chính sách |
| `EXPIRED`, `CANCELLED`, `REJECTED` | Hồ sơ kết thúc mà không hoàn tất | Không được tái sử dụng để đổi yếu tố hoặc tạo session |

Không nhất thiết mọi hệ thống cần đúng các tên này. Điều quan trọng là **quyền của từng trạng thái phải rõ ràng và được thực thi phía máy chủ**.

### Token email và hồ sơ recovery có vòng đời khác nhau

Ví dụ, token email có thể hết hạn sau 15 phút, còn hồ sơ recovery có thể cần chờ lâu hơn. Đây chỉ là con số minh họa, không phải giá trị mặc định cho mọi dịch vụ.

Sau khi token được chấp nhận, máy chủ ghi nhận bằng chứng vào đúng hồ sơ. Không giữ một bearer token email còn hiệu lực suốt thời gian chờ. Việc tiếp tục hồ sơ dùng một ngữ cảnh quyền hạn thấp, có hạn riêng và không thể đổi sang tài khoản hay mục đích khác.

Bằng chứng đã được ghi nhận cũng cần giới hạn độ mới. Nếu hồ sơ chờ quá lâu hoặc trạng thái tài khoản thay đổi, có thể phải đánh giá lại. Không để một lần xác minh từ nhiều tuần trước trở thành quyền đổi yếu tố vô thời hạn.

### Không cho phép đổi yêu cầu sau khi đã xác minh

Một hồ sơ được phê duyệt để đặt lại mật khẩu không được âm thầm chuyển thành hồ sơ xóa toàn bộ MFA. Các hành động nhạy cảm cần được ràng buộc với bằng chứng và quyết định chính sách.

Trước khi hoàn tất, cần kiểm tra lại ít nhất:

- Hồ sơ còn hiệu lực và chưa hoàn tất, bị hủy hoặc bị từ chối.
- Bằng chứng đủ, còn phù hợp với chính sách và đúng hành động yêu cầu.
- Khoảng chờ đã kết thúc nếu chính sách có yêu cầu.
- Không có thay đổi liên quan đến yếu tố xác thực hoặc kênh recovery làm quyết định cũ mất hiệu lực.
- Những thay đổi dự kiến vẫn là những thay đổi đã được phê duyệt.
- Kế hoạch xử lý session và quyền tồn tại sau recovery đã được xác định.

Có thể dùng phiên bản cấu hình bảo mật của tài khoản để phát hiện quyết định dựa trên dữ liệu cũ. Ví dụ, người dùng thật vừa thay kênh recovery thì hồ sơ trước đó cần được xem xét lại theo chính sách, thay vì tự động hoàn tất.

## 9. Token an toàn vẫn cần thiết, dù không sửa được hộp thư bị xâm nhập

Không nên hiểu giới hạn của email thành lý do bỏ các biện pháp bảo vệ token. Chúng giải quyết những mối đe dọa khác: đoán token, lộ token ngoài ý muốn, dùng sai mục đích và phát lại.

### Thuộc tính cơ bản

- Sinh token bằng nguồn ngẫu nhiên mật mã; ví dụ 32 byte ngẫu nhiên cho một token bearer khó đoán.
- Lưu dấu băm hoặc HMAC để tra cứu, thay vì lưu token thô; nếu dùng HMAC, khóa phải được quản lý tách khỏi dữ liệu token.
- Gắn token với tài khoản, hồ sơ recovery, mục đích, thời điểm phát hành, thời điểm hết hạn và trạng thái sử dụng.
- Dùng thời hạn ngắn phù hợp với trải nghiệm và mô hình rủi ro.
- Chỉ chấp nhận một lần bằng thao tác nguyên tử, tránh hai yêu cầu đồng thời cùng thành công.
- Không cho token của thao tác xác nhận email dùng để xóa MFA, đổi kênh recovery hoặc cấp session đầy đủ.

Dấu băm chỉ phù hợp khi token vốn đã có entropy cao; nó không làm một mã ngắn, dễ đoán trở nên khó thử. Với OTP ngắn, cần giới hạn số lần thử, thời hạn và phạm vi hồ sơ một cách chặt chẽ.

Việc lưu dấu băm bảo vệ tốt hơn khi dữ liệu lưu trữ bị lộ; nó không ngăn người đang đọc hộp thư lấy token thô từ email.

### Tránh tiêu thụ token chỉ vì truy cập liên kết

Bộ quét an toàn email hoặc trình xem trước có thể mở liên kết mà không có hành động chủ động của người dùng. Không dùng một yêu cầu GET để đổi mật khẩu, xóa yếu tố hoặc hoàn tất recovery.

GET có thể hiển thị trang tiếp tục, nhưng thao tác thay đổi trạng thái cần một hành động xác nhận phù hợp qua POST và bảo vệ chống giả mạo yêu cầu theo ngữ cảnh session. Việc trình token không phải là sự đồng ý với mọi thay đổi bảo mật.

Trang xử lý token cần hạn chế việc lộ bí mật qua log, analytics, referrer và tài nguyên bên thứ ba. Có thể trao đổi token lấy ngữ cảnh tạm phía máy chủ rồi chuyển tới URL sạch. Không ghi nguyên URL chứa token vào hệ thống giám sát.

### Dùng một lần và phát hành lại

Khi có nhiều yêu cầu recovery, cần chính sách rõ cho token cũ và mới. Một phương án là token mới thay thế token cũ trong cùng hồ sơ; phương án khác cho phép số lượng giới hạn với phạm vi riêng.

Không để một người chưa xác minh có thể vô hạn phát hành token mới, liên tục làm mất hiệu lực tiến trình hợp lệ của nạn nhân. Cần kết hợp giới hạn tần suất và quy tắc ổn định hồ sơ.

Không vô hiệu token cũ không có nghĩa được cho phép nhiều lần hoàn tất: quyết định cuối cùng vẫn phải bảo đảm mỗi hồ sơ chỉ được áp dụng một lần và các hồ sơ cạnh tranh được xử lý nhất quán.

## 10. Ví dụ logic cấp quyền phía máy chủ

Đoạn mã sau là mã giả để minh họa ranh giới quyền. Nó không phải một triển khai sẵn để đưa vào sản xuất.

~~~text
function proveEmail(rawToken, recoveryContext):
    digest = digestRecoveryToken(rawToken)

    transaction:
        token = lockTokenByDigest(digest)
        require token exists
        require token.expiresAt > now
        require token.usedAt is null
        require token.purpose == "RECOVERY_EMAIL_PROOF"

        attempt = lockRecoveryAttempt(token.attemptId)
        require attempt.accountId == token.accountId
        require recoveryContext is bound to attempt
        require attempt is active

        token.usedAt = now
        attempt.emailProvenAt = now
        recordEvent("RECOVERY_EMAIL_PROVEN", attempt.id)

    return limitedRecoveryContext(attempt.id)
    // Chưa tạo session tài khoản đầy đủ ở đây.


function completeRecovery(attemptId, limitedContext, proposedChanges):
    require limitedContext is bound to attemptId
    require validSubmissionContext(limitedContext)

    transaction:
        attempt = lockRecoveryAttempt(attemptId)
        account = lockAccount(attempt.accountId)

        require attempt is active and not completed
        require attempt.overallDeadline > now
        require account.securityVersion == attempt.approvedSecurityVersion
        require proposedChanges match attempt.approvedChanges

        decision = evaluateRecoveryPolicy(
            account,
            attempt.evidence,
            attempt.evidenceFreshness,
            attempt.riskSignals,
            proposedChanges
        )

        require decision.allows(proposedChanges)
        require decision.requiredWaitHasElapsed
        require decision.requiredIndependentEvidenceSatisfied

        applyApprovedCredentialChanges(account, proposedChanges)
        applyRevocationBoundary(account, decision.sessionPlan)
        account.securityVersion += 1
        attempt.state = "COMPLETED"
        markCompetingAttemptsAccordingToPolicy(account, attempt)
        enqueueSecurityNotification(account, attempt)
        recordEvent("RECOVERY_COMPLETED", attempt.id)

    return nextAuthenticationStep(decision)
~~~

Trong chính sách cho phép recovery chỉ bằng email, điều kiện bằng chứng độc lập có thể không được yêu cầu. Khi ấy hệ thống phải ghi nhận mức bảo đảm thấp hơn và chấp nhận rủi ro tương ứng; không nên gắn nhãn quyết định đó là đã chống được đối thủ kiểm soát hộp thư.

Một vài chi tiết triển khai quan trọng:

- Thứ tự khóa và transaction phải nhất quán để xử lý cạnh tranh, tránh việc hai hồ sơ cùng vượt qua kiểm tra rồi áp dụng những thay đổi khác nhau.
- `approvedChanges` mô tả mục đích và phạm vi thay đổi, không chứa bí mật thô trong audit log.
- Các bằng chứng mật mã cần được xác minh đúng trước khi đưa vào hồ sơ; hàm đánh giá chính sách không thể sửa một bằng chứng vốn được ghi nhận sai.
- Nếu session và credential ở nhiều dịch vụ, cần cơ chế thu hồi có hiệu lực thực tế. Chỉ xếp một tác vụ thu hồi bất đồng bộ rồi cấp quyền ngay có thể để lại khoảng truy cập cho đối thủ.
- Thông báo có thể dùng cơ chế outbox để được gửi lại khi lỗi; việc hệ thống đã xếp hàng gửi không chứng minh người dùng đã đọc được cảnh báo.

## 11. Xử lý session và yếu tố xác thực sau recovery

Recovery hoàn tất là một sự kiện thay đổi quyền sở hữu tiềm tàng. Chính sách session cần dựa trên loại sự cố và mức bằng chứng, không chỉ dựa vào việc mật khẩu vừa đổi.

### Không cấp session đầy đủ ngay sau bằng chứng email

Một recovery context nên có phạm vi tối thiểu, chẳng hạn chỉ cho phép xem tiến độ và gửi bằng chứng vào đúng hồ sơ. Nó không nên có quyền đọc dữ liệu, xuất dữ liệu, thêm passkey hoặc cấp quyền cho ứng dụng.

Giới hạn giao diện là chưa đủ. API cũng phải từ chối thao tác ngoài phạm vi. Đối thủ có thể gọi trực tiếp endpoint ngay cả khi nút tương ứng không xuất hiện trên trang.

### Quyết định thu hồi theo các quyền đang tồn tại

Tùy kết quả xác minh và loại sự cố, kế hoạch có thể bao gồm:

- Thu hồi session và refresh token được xác định là không còn đáng tin.
- Xóa hoặc vô hiệu dấu tin cậy thiết bị và cơ chế bỏ qua MFA liên quan.
- Đánh giá ứng dụng đã được cấp quyền, token API và quyền tồn tại lâu dài; không giả định chúng tự mất hiệu lực khi mật khẩu đổi.
- Luân chuyển mã dự phòng nếu có nguy cơ lộ hoặc nếu chúng đã được dùng.
- Chấm dứt recovery context đã hoàn tất và xử lý các hồ sơ recovery cạnh tranh.

Không áp dụng hàng loạt việc thu hồi chỉ vì nhận một yêu cầu email chưa được xác minh. Nếu mỗi yêu cầu bắt đầu đều đăng xuất mọi thiết bị, đối thủ có thể gây từ chối dịch vụ mà không cần đọc hộp thư.

Ngược lại, cũng không luôn giữ session cũ chỉ để tránh gây phiền. Khi bằng chứng cho thấy session hoặc thiết bị đã bị chiếm, duy trì chúng có thể phá hỏng toàn bộ recovery.

### Thêm yếu tố mới và mở lại quyền nhạy cảm

Việc đăng ký passkey hoặc MFA mới phải nằm sau các điều kiện recovery phù hợp. Yếu tố do người đang giữ một recovery context yếu tạo ra không tự trở thành bằng chứng mạnh cho quyền sở hữu trước đó.

Với một số hành động rủi ro cao, dịch vụ có thể tiếp tục hạn chế trong khoảng thời gian sau recovery. Tuy nhiên, hạn chế phải gắn với tài sản thực tế: chặn đổi email nhưng vẫn cho tải toàn bộ dữ liệu nhạy cảm có thể không đáp ứng mục tiêu bảo vệ dữ liệu.

Nếu nghi ngờ hộp thư còn bị đối thủ kiểm soát, tiếp tục gửi mọi bằng chứng và cảnh báo vào đó sẽ giữ nguyên điểm yếu. Cần một đường xác minh phù hợp để chuyển sang kênh đáng tin cậy; quyền truy cập địa chỉ mới đơn thuần chưa đủ để cho phép chuyển.

## 12. Chống lạm dụng, cảnh báo và hỗ trợ người dùng

### Giới hạn tần suất theo nhiều chiều

Cần bảo vệ cả bước khởi tạo, gửi lại thư, thử token, gửi bằng chứng và liên hệ hỗ trợ. Có thể kết hợp giới hạn theo tài khoản, hồ sơ, nguồn yêu cầu và các tín hiệu lạm dụng.

Giới hạn chỉ theo IP có thể gây ảnh hưởng người dùng chung mạng và không đủ khi đối thủ thay nguồn gửi. Giới hạn chỉ theo tài khoản có thể bị dùng để ngăn nạn nhân recovery. Cần có cách xử lý khi người dùng hợp lệ bị giới hạn mà không tạo lối bỏ xác minh.

Phản hồi khởi tạo nên tránh tiết lộ tùy tiện việc địa chỉ email có tài khoản hay không. Tuy vậy, chống dò tài khoản không ngăn đối thủ đã biết địa chỉ và có quyền đọc hộp thư.

### Cảnh báo qua kênh đã thiết lập từ trước

Nếu có kênh độc lập hoặc thiết bị đáng tin đã đăng ký, có thể gửi thông báo về yêu cầu recovery, thay đổi yếu tố và session mới. Cảnh báo nên giúp người dùng biết:

- Sự kiện nào đã xảy ra và vào thời điểm nào.
- Thay đổi nào đang chờ hoặc đã được thực hiện.
- Đường phản hồi an toàn khi họ không thực hiện yêu cầu.

Không đưa bí mật recovery vào thông báo. Không coi việc gửi được thông báo hoặc không nhận phản hồi là bằng chứng người dùng đã chấp thuận.

Nếu chỉ có email, cảnh báo vẫn hữu ích khi người dùng thật còn truy cập hộp thư, nhưng phải ghi rõ giới hạn: đối thủ có thể đọc hoặc xóa nó.

### Hỗ trợ không được trở thành đường vòng

Nhân viên cần quy tắc cho việc thay email, xóa MFA và hủy recovery. Không chấp nhận việc “gửi email từ đúng địa chỉ” như bằng chứng đủ mạnh trong chính kịch bản hộp thư bị xâm nhập.

Với tài khoản nhạy cảm, có thể yêu cầu chuyển cấp hoặc phê duyệt phù hợp. Mọi ngoại lệ được phép phải có lý do và dấu vết, không phải một quyền bỏ qua chính sách không giới hạn.

Người dùng thật cũng cần hướng dẫn xử lý kênh email trước khi tiếp tục nhận bí mật mới: xem xét các session email, quyền ứng dụng, cấu hình khôi phục và quy tắc chuyển tiếp liên quan. Dịch vụ không nên giả định hộp thư đã an toàn chỉ vì người dùng thông báo đã đổi mật khẩu.

## 13. Quan sát và điều tra mà không làm lộ bí mật

Các sự kiện hữu ích bao gồm yêu cầu recovery được tạo, email proof được chấp nhận, bằng chứng độc lập được xác minh, quyết định chờ, thay đổi bị từ chối, hoàn tất recovery và kết quả thu hồi session.

Một bản ghi có thể chứa:

- Mã hồ sơ recovery và định danh tài khoản nội bộ.
- Loại sự kiện, thời điểm và phiên bản chính sách.
- Nhóm bằng chứng đã được sử dụng, không phải nội dung bí mật.
- Mã lý do cho phép hoặc từ chối.
- Định danh session đã được giả danh hóa phù hợp và kết quả thu hồi.

Không ghi token, OTP, mã dự phòng, cookie, URL recovery đầy đủ hoặc tài liệu xác minh thô vào log thông thường. Dữ liệu mạng, thiết bị và hồ sơ danh tính cũng cần quyền truy cập và thời hạn lưu phù hợp.

Các mẫu cần chú ý gồm recovery từ môi trường mới rồi xóa yếu tố và thêm yếu tố khác, nhiều hồ sơ cạnh tranh, hoặc yêu cầu hỗ trợ ngay sau nhiều lần xác minh thất bại. Chúng là tín hiệu để điều tra hoặc tăng kiểm tra, không phải kết luận tự động rằng người dùng là đối thủ.

## 14. Tự kiểm tra thiết kế bằng các tình huống đối nghịch

Bảng sau là các câu hỏi rà soát thiết kế, không phải kết quả kiểm thử của một hệ thống cụ thể.

| Tình huống | Kết quả mong đợi |
|---|---|
| Đối thủ đọc được token email nhưng không có passkey đã đăng ký | Không vượt qua yêu cầu passkey độc lập nếu chính sách yêu cầu |
| Đổi mật khẩu thành công nhưng chưa qua MFA bắt buộc | Chưa nhận session đầy đủ hoặc quyền nhạy cảm |
| Đối thủ nhận hai mã qua cùng một hộp thư | Không được nâng mức bảo đảm chỉ vì có hai lần xác nhận |
| Dùng token email proof cho endpoint xóa MFA | Bị từ chối do sai mục đích hoặc thiếu quyền |
| Hai yêu cầu trình cùng token đồng thời | Chỉ một lần được ghi nhận thành công |
| Bộ quét email mở liên kết bằng GET | Không đổi mật khẩu, xóa yếu tố hoặc hoàn tất recovery |
| Người chưa xác minh thay email nhận bằng chứng trong lúc chờ | Bị từ chối hoặc chuyển sang quy trình thay kênh có chính sách riêng |
| Đối thủ đăng ký passkey mới chỉ bằng recovery context yếu | Bị từ chối; yếu tố mới không được dùng để hợp thức hóa chính recovery ấy |
| Không ai phản đối trong thời gian chờ nhưng chưa có bằng chứng bắt buộc | Không tự động bỏ qua điều kiện bằng chứng |
| Người dùng thật thay yếu tố khi hồ sơ cũ vẫn đang chờ | Quyết định cũ được kiểm tra lại theo phiên bản bảo mật |
| Đối thủ liên tục tạo yêu cầu mới hoặc bấm hủy qua email | Không dễ dàng làm người dùng thật mất quyền vô thời hạn; có đường xử lý tranh chấp |
| Mật khẩu đã đổi nhưng refresh token của đối thủ còn tồn tại | Chính sách thu hồi phát hiện và xử lý đúng phạm vi sự cố |
| Hộp thư vẫn có quyền ứng dụng hoặc chuyển tiếp ngoài ý muốn | Không coi việc đổi mật khẩu email là bằng chứng kênh đã được làm sạch |
| Nhân viên nhận đúng thông tin hóa đơn từ người gửi email | Chưa tự kết luận đã xác minh chủ tài khoản |
| Hệ thống không có bất kỳ bằng chứng độc lập nào | Nêu rõ giới hạn bảo đảm; không tuyên bố đã loại trừ đối thủ kiểm soát email |

Một câu hỏi chốt cho từng endpoint là: **người chỉ đọc được hộp thư có thể làm gì tại đây?** Trả lời câu hỏi ấy từ lúc bắt đầu đến lúc có quyền truy cập dữ liệu sẽ bộc lộ các bước nâng quyền ngầm.

## 15. Áp dụng lại vào tình huống của Lan

Một thiết kế phù hợp hơn cho tài khoản có passkey của Lan có thể vận hành như sau:

1. Email chỉ giúp khởi tạo và tiếp tục một hồ sơ recovery có quyền hạn thấp.
2. Nếu Lan chỉ mất mật khẩu, passkey đã đăng ký được dùng theo chính sách để cho phép hành động tương ứng.
3. Nếu Lan mất cả passkey và thiết bị, dịch vụ chuyển sang mã dự phòng hoặc quy trình xác minh đã xác lập; không mặc định thay bằng một OTP email khác.
4. Khi bằng chứng chưa đủ, hồ sơ được xử lý theo chính sách tăng cường hoặc chưa được cấp lại quyền. Thời gian chờ không thay thế bằng chứng bắt buộc.
5. Khi hoàn tất, dịch vụ áp dụng đúng thay đổi đã phê duyệt, xử lý session và quyền tồn tại, rồi yêu cầu bước xác thực tiếp theo phù hợp.
6. Kênh recovery mới chỉ được thiết lập sau khi người yêu cầu có đủ thẩm quyền. Các sự kiện quan trọng được ghi nhận và thông báo qua những kênh đã có khi khả dụng.

Nếu Lan không còn bất kỳ bằng chứng độc lập nào và dịch vụ chỉ có email, không có một mẹo token nào giải quyết được sự mơ hồ đó. Hệ thống phải chọn chính sách chấp nhận rủi ro hoặc chưa cho khôi phục, đồng thời giúp người dùng chuẩn bị phương án dự phòng từ trước.

Điều cần ghi nhớ là sự khác nhau giữa **vận chuyển bí mật an toàn** và **xác minh đúng chủ tài khoản**. Luồng recovery an toàn cần cả hai; trong mô hình compromised mailbox attacker, phần thứ hai phải được thiết kế với giả định rằng đối thủ cũng nhận được email.
