# Yếu tố biết (Knowledge factor) trong xác thực

## 1. Yếu tố biết là gì?

**Yếu tố biết** (*something you know*, *knowledge factor*) là loại bằng chứng xác thực dựa trên **một bí mật mà người dùng biết** và có thể cung cấp khi được yêu cầu. Ví dụ điển hình là mật khẩu (*password*), cụm mật khẩu (*passphrase*) và mã PIN dùng để xác minh một bí mật đã được thiết lập.

Trong chương **Authentication factor** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, yếu tố biết là điểm xuất phát để hiểu việc xác thực bằng credential: hệ thống cần xác định bằng chứng nào gắn với danh tính được khai báo, bằng chứng ấy có thể bị đoán hoặc đánh cắp ra sao, rồi chọn lớp bảo vệ phù hợp. Kiến thức này còn liên quan trực tiếp tới MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Đích đến là thiết kế luồng đăng nhập có ranh giới tin cậy rõ ràng, chống phishing, replay và lạm dụng thử đăng nhập.

Ví dụ người dùng nhập:

~~~text
Tài khoản:  lan@example.org
Mật khẩu:   <bí mật chỉ chủ tài khoản và bên xác minh cần kiểm tra>
~~~

Tên tài khoản là **thông tin định danh**, không phải yếu tố xác thực. Mật khẩu là một bằng chứng cho tuyên bố danh tính đó. Nếu mật khẩu đúng, hệ thống chỉ biết người gửi **đã cung cấp được bí mật phù hợp**; nó không chứng minh tuyệt đối người gửi chính là chủ sở hữu hợp pháp. Một người biết mật khẩu do bị lộ hoặc do được chia sẻ vẫn có thể vượt qua kiểm tra.

Phân biệt ba việc:

| Khái niệm | Câu hỏi | Vai trò trong ví dụ |
| --- | --- | --- |
| Định danh (*identification*) | Ai đang yêu cầu đăng nhập? | Nhập tên tài khoản hoặc mã nhân viên. |
| Xác thực (*authentication*) | Có bằng chứng đúng cho danh tính đã khai báo không? | Kiểm tra mật khẩu, hoặc mật khẩu kết hợp yếu tố khác. |
| Phân quyền (*authorization*) | Danh tính đã xác thực được làm gì? | Kiểm tra người dùng có quyền xem một tài liệu nhất định hay không. |

Yếu tố biết chủ yếu giải quyết bước **xác thực**. Kể cả sau khi xác thực thành công, tài nguyên vẫn phải được kiểm tra quyền ở server.

## 2. Các dạng yếu tố biết và trường hợp sử dụng

| Dạng bí mật | Đặc điểm | Ví dụ / lưu ý |
| --- | --- | --- |
| **Mật khẩu** (*password*) | Một chuỗi bí mật do người dùng nhớ hoặc do trình quản lý mật khẩu lưu hộ. | Mật khẩu đăng nhập dịch vụ web hoặc hệ thống nội bộ. |
| **Cụm mật khẩu** (*passphrase*) | Nhiều từ hoặc chuỗi dài, có thể dễ nhớ hơn mà vẫn đủ mạnh khi chọn ngẫu nhiên. | Một cụm từ dài, duy nhất cho tài khoản; tránh câu trích dẫn phổ biến. |
| **PIN** | Bí mật thường ngắn, thường có chữ số; độ an toàn phụ thuộc rất mạnh vào giới hạn số lần thử và vị trí kiểm tra. | PIN mở khóa thiết bị hoặc authenticator; PIN bốn đến sáu chữ số không phù hợp nếu cho phép đoán không giới hạn qua mạng. |
| **Câu hỏi bảo mật** | Câu trả lời được coi như bí mật ghi nhớ. | “Tên trường tiểu học?” dễ tìm, dễ đoán hoặc thay đổi, nên không dùng làm phương thức xác thực/khôi phục đáng tin cậy. |
| **Mã ghi nhớ được chia sẻ trước** | Bí mật theo thỏa thuận, có thể do quản trị viên cấp. | Mã kích hoạt tạm cần thay đổi hoặc hết hạn đúng cách, không nên duy trì như mật khẩu chung của cả nhóm. |

**Hai mật khẩu không tạo thành xác thực hai yếu tố.** Cả hai cùng thuộc loại “điều biết”: nếu một kịch bản phishing thu được cả hai, hệ thống vẫn chỉ kiểm tra một **loại** bằng chứng. MFA đúng nghĩa kết hợp các loại bằng chứng độc lập phù hợp, chẳng hạn mật khẩu với khóa bảo mật hoặc authenticator.

Một số ví dụ có vẻ giống yếu tố biết nhưng phải xem **bí mật nằm ở đâu và bên nào thực sự chứng minh điều gì**:

- **PIN mở khóa passkey hoặc điện thoại:** người dùng nhập PIN để authenticator **cục bộ** cho phép sử dụng khóa riêng. RP/server thường không nhận PIN. Trong luồng WebAuthn, bằng chứng gửi về là kết quả mật mã của authenticator; PIN là cơ chế xác minh người dùng tại thiết bị, không nên tính thành một mật khẩu thứ hai độc lập ở server.
- **Mã TOTP sáu chữ số:** người dùng đọc và nhập mã, nhưng yếu tố gốc dựa trên **quyền sở hữu authenticator đang giữ khóa bí mật**, không phải một sự thật lâu dài người dùng phải nhớ. Mã ngắn và theo thời gian không nên được phân loại thành một “yếu tố biết” độc lập chỉ vì người dùng gõ nó.
- **Email hoặc SMS OTP:** quyền nhận mã qua một kênh không đồng nghĩa với việc người dùng có thêm một bí mật ghi nhớ. Mức bảo đảm của kênh, nguy cơ SIM swap/phishing và cơ chế khôi phục cần được đánh giá riêng.
- **Mã khôi phục dùng một lần:** là bí mật mang theo để sử dụng khi mất authenticator, có thể bị sao chép; chính sách sử dụng/hết hạn của nó khác với mật khẩu ghi nhớ thông thường.

## 3. Bí mật được xác minh qua ranh giới tin cậy như thế nào?

Đối với đăng nhập bằng mật khẩu trên web, mô hình đơn giản:

~~~mermaid
flowchart LR
    U["Người dùng<br/>biết mật khẩu"]
    C["Trình duyệt / ứng dụng<br/>không được tự quyết định đăng nhập"]
    E["Điểm vào server<br/>TLS, chống lạm dụng"]
    V["Dịch vụ xác thực<br/>kiểm tra mật khẩu"]
    D[("Kho thông tin xác minh<br/>password hash")]
    S[("Kho phiên / token")]
    A["API tài nguyên<br/>kiểm tra quyền"]
    U -->|"Cung cấp bí mật"| C
    C -->|"Yêu cầu đăng nhập qua TLS"| E
    E --> V
    V <-->|"Đối chiếu hash"| D
    V -->|"Thành công: tạo phiên mới"| S
    C -->|"Gửi phiên khi gọi API"| A
    A -->|"Xác thực phiên + phân quyền"| S
~~~

Các điểm cần giữ đúng:

1. **Thiết bị và trình duyệt là phía chưa tin cậy.** Không chấp nhận cờ \`authenticated=true\`, \`isAdmin=true\` hoặc kết quả so sánh mật khẩu do client tự gửi như một bằng chứng đã đăng nhập.
2. **Kênh truyền cần được bảo vệ.** Sử dụng HTTPS/TLS hợp lệ khi gửi credential; không truyền mật khẩu trên HTTP thường hoặc đặt mật khẩu trong query string.
3. **Server kiểm tra bí mật.** Thông thường server lưu giá trị kiểm chứng dẫn xuất bằng thuật toán băm mật khẩu chuyên dụng, không lưu lại mật khẩu gốc để so sánh chuỗi thuần.
4. **Khi thành công, server cấp trạng thái đăng nhập riêng.** Cookie phiên, session ID hoặc token có vòng đời, phạm vi và cách thu hồi của chúng; mật khẩu không nên được gửi lặp lại với mọi yêu cầu API.
5. **Mỗi API cần kiểm tra quyền trên tài nguyên đích.** Đã đăng nhập không có nghĩa là được phép lấy dữ liệu của người khác.

Đây là mô hình khái niệm; hệ thống triển khai thực tế có thể đặt thành phần trong cùng một dịch vụ hoặc tách thành nhiều dịch vụ. Ranh giới quan trọng là **ai được tạo và xác minh bằng chứng**, không phải số lượng server.

### Vì sao không lưu mật khẩu dạng đọc được?

Nếu cơ sở dữ liệu chứa mật khẩu gốc hoặc một bản mã có thể giải mã dễ dàng, việc rò rỉ dữ liệu hoặc khóa giải mã có thể làm lộ ngay mật khẩu của rất nhiều tài khoản. **Password hashing** làm việc kiểm tra bằng cách chạy thuật toán dẫn xuất một chiều có chi phí tính toán chủ động, thay vì cần biết lại mật khẩu gốc.

Với mỗi tài khoản, hệ thống dùng **salt ngẫu nhiên riêng** và thuật toán băm mật khẩu phù hợp như **Argon2id**, **scrypt** hoặc **bcrypt** được cấu hình theo yêu cầu vận hành; một số môi trường tiêu chuẩn hóa sử dụng **PBKDF2** với tham số đủ mạnh. Salt **không cần bí mật** nhưng cần duy nhất/khó trùng để các tài khoản dùng cùng mật khẩu không có kết quả kiểm chứng giống nhau. Một **pepper** quản lý ngoài cơ sở dữ liệu có thể được dùng như lớp tăng cường, nhưng không thay thế salt, thuật toán phù hợp hoặc bảo vệ khóa.

Không dùng các hash tổng quát như \`SHA-256(password)\` hay \`MD5(password)\` làm cơ chế lưu mật khẩu trực tiếp: chúng quá nhanh để chống đoán ngoại tuyến khi dữ liệu bị lộ.

~~~text
Khi đăng ký / đổi mật khẩu:
    salt = secureRandom()
    verifier = passwordKDF(password, salt, tunedParameters)
    lưu {thuật_toán, tham_số, salt, verifier}

Khi đăng nhập:
    lấy bản ghi kiểm chứng tương ứng
    passwordKDF.verify(mật_khẩu_đã_nhập, bản_ghi)
    chỉ tạo phiên nếu kết quả hợp lệ và các bước xác thực khác đã đạt
~~~

Đây là **mã giả về trách nhiệm**, không phải cách triển khai trực tiếp. Nên dùng API của thư viện mật khẩu đã được kiểm thử, quản lý tham số/phiên bản để nâng cấp dần và xử lý lỗi nhất quán. Mật khẩu vẫn có thể bị đoán nếu yếu hoặc phổ biến, ngay cả khi được băm đúng: hash chỉ làm việc đoán mật khẩu **khó và tốn kém hơn**, không bảo đảm bí mật yếu trở nên mạnh.

## 4. Những nguy cơ đặc trưng với yếu tố biết

Yếu tố biết có nhược điểm căn bản: **bí mật có thể bị tiết lộ, đoán hoặc sao chép** mà chủ sở hữu không hay biết. Không có bằng chứng vật lý cho biết ai đang gõ bí mật.

| Nguy cơ | Diễn biến thực tế | Vì sao yếu tố biết dễ bị tác động? |
| --- | --- | --- |
| **Phishing** | Trang giả hoặc cuộc gọi mạo danh yêu cầu nhập mật khẩu. | Người dùng có thể tiết lộ một bí mật dùng lại được. |
| **Credential stuffing** | Kẻ tấn công dùng danh sách email/mật khẩu đã lộ từ dịch vụ khác. | Mật khẩu bị tái sử dụng giữa nhiều tài khoản. |
| **Password spraying** | Thử một vài mật khẩu phổ biến trên rất nhiều tài khoản. | Tránh giới hạn đoán ở từng tài khoản đơn lẻ. |
| **Brute force trực tuyến** | Gửi hàng loạt lượt thử bí mật tới endpoint đăng nhập. | Server phải quyết định giới hạn số lần thử. |
| **Đoán ngoại tuyến sau rò rỉ hash** | Kẻ tấn công có database hash, thử ứng viên trên thiết bị của họ. | Rate limit của trang đăng nhập không áp dụng cho quá trình ngoại tuyến. |
| **Keylogger / mã độc** | Ghi các phím hoặc đọc clipboard/mật khẩu trên thiết bị. | Bí mật bị lấy trước khi server có cơ hội kiểm tra. |
| **Quan sát trực tiếp / chia sẻ** | Người khác nhìn thấy PIN, xem ghi chú, nghe chủ tài khoản đọc mật khẩu. | Không thể phân biệt người sở hữu và người được tiết lộ bí mật. |
| **Replay ở giao thức yếu** | Bằng chứng tĩnh bị ghi lại và phát lại trên kênh không an toàn hoặc giao thức tự chế. | Bằng chứng không thay đổi, không gắn với giao dịch. |
| **Khôi phục tài khoản yếu** | Kẻ tấn công trả lời câu hỏi bảo mật hoặc chiếm hộp thư khôi phục. | Đường khôi phục có thể bỏ qua mật khẩu ban đầu. |

### Ba bối cảnh tấn công khác nhau

**Đoán trực tuyến:** mỗi lần thử phải đi qua server. Hạn chế tốc độ, giám sát và chính sách chặn có điều kiện giảm số lần kẻ tấn công có thể thử.

**Đoán ngoại tuyến:** kẻ tấn công đã có dữ liệu kiểm chứng như password hash. Họ tự thử tại chỗ, không bị hạn chế bởi endpoint đăng nhập; chất lượng mật khẩu, salt và cấu hình KDF là các lớp phòng vệ quan trọng.

**Phishing:** người dùng tự cung cấp mật khẩu đúng cho kẻ tấn công. Hash/KDF tốt ở server không ngăn được sự cố này. MFA có thể giảm nguy cơ dùng mật khẩu bị lộ, nhưng OTP cũng có thể bị chuyển tiếp; passkey/WebAuthn gắn với origin/RP ID có khả năng chống phishing tốt hơn khi triển khai đúng.

**Không nên coi HTTPS là biện pháp chống phishing đầy đủ.** Trang giả có thể có HTTPS hợp lệ cho *tên miền của trang giả*. Người dùng cần được bảo vệ bằng thiết kế đăng nhập có khả năng ràng buộc với nguồn gốc xác thực, cùng các cơ chế phát hiện lạm dụng.

## 5. Thiết lập và quản lý mật khẩu an toàn

### 5.1. Hướng dẫn người dùng tạo bí mật

- **Ưu tiên mật khẩu dài, duy nhất cho mỗi tài khoản.** Một mật khẩu mạnh cho một dịch vụ nhưng lặp lại ở nhiều nơi vẫn dễ gây credential stuffing khi nơi khác rò rỉ.
- **Cho phép trình quản lý mật khẩu và tính năng dán/autofill.** Chúng giúp người dùng tạo và dùng mật khẩu ngẫu nhiên khác nhau mà không phải ghi nhớ tất cả.
- **Cho phép passphrase đủ dài.** Độ dài và mức khó dự đoán thường quan trọng hơn việc buộc thay chữ bằng ký tự đặc biệt theo các mẫu dễ đoán như \`Password1!\`.
- **Không đặt giới hạn độ dài quá thấp hoặc cắt bớt đầu vào âm thầm.** Cần quy định giới hạn hợp lý để chống lạm dụng tài nguyên, đồng thời xử lý Unicode và khoảng trắng nhất quán với cơ chế kiểm chứng đã chọn.
- **Tránh ép đổi mật khẩu theo chu kỳ tùy ý** khi không có bằng chứng bị lộ hoặc lý do vận hành cụ thể. Đổi bắt buộc quá thường xuyên có thể khiến người dùng tạo chuỗi đoán được.
- **Không dùng gợi ý mật khẩu dễ lộ bí mật** hay câu hỏi dựa trên dữ liệu công khai làm bước khôi phục.

Ví dụ minh họa tư duy (không dùng nguyên văn các chuỗi ở đây làm mật khẩu thật):

~~~text
Dễ đoán:     Welcome123!
Dễ lộ qua tái sử dụng: mật khẩu từng dùng ở email cá nhân
Tốt hơn:     chuỗi ngẫu nhiên dài, riêng cho dịch vụ, do password manager sinh
Hoặc:        passphrase dài gồm các từ được chọn ngẫu nhiên, không phải câu quen thuộc
~~~

**Lưu ý về độ dài:** độ dài tối thiểu, tối đa và chính sách sàng lọc phụ thuộc chuẩn/độ bảo đảm áp dụng. Thiết kế tốt nên hỗ trợ bí mật dài, kiểm tra danh sách mật khẩu phổ biến hoặc đã lộ, thay vì dựa hoàn toàn vào quy tắc bắt buộc chữ hoa/chữ thường/số/ký tự đặc biệt.

### 5.2. Chính sách phía server

1. **Kiểm tra mật khẩu bị lộ hoặc phổ biến** khi tạo/đổi, với dữ liệu hoặc dịch vụ đáng tin cậy và cách kiểm tra hạn chế tiết lộ mật khẩu. Từ chối các bí mật quá dễ đoán.
2. **Hash bằng KDF chuyên dụng** có salt riêng, tham số phù hợp với khả năng hệ thống; thiết kế nâng cấp thuật toán hoặc tham số khi người dùng đăng nhập/đổi mật khẩu.
3. **Giới hạn thử đăng nhập** theo tài khoản, IP/mạng và tín hiệu khác ở nhiều tầng; có cân nhắc rủi ro gây khóa nhầm và từ chối dịch vụ.
4. **Giảm liệt kê tài khoản:** phản hồi lỗi chung cho “sai tài khoản” và “sai mật khẩu”, tránh rò rỉ qua API, UI hoặc thời gian xử lý khi có thể.
5. **Bảo vệ credential khi nhập và truyền:** dùng HTTPS/TLS, tránh đưa mật khẩu vào URL, log, analytics, sự kiện lỗi, telemetry hoặc cache không được bảo vệ.
6. **Hỗ trợ MFA và passkey:** đặc biệt với tài khoản đặc quyền hoặc thao tác nhạy cảm; có thể từng bước chuyển từ mật khẩu sang phương thức chống phishing tốt hơn.
7. **Thu hồi/đánh giá phiên khi đổi mật khẩu hoặc nghi bị chiếm:** mật khẩu mới không tự vô hiệu hóa phiên hoặc refresh token đã phát hành từ trước.

Không cần đặt chính sách bắt mọi tài khoản có cùng số lần thử, thời hạn chặn hoặc cấp độ MFA. **Điều chỉnh theo mối đe dọa và ảnh hưởng khi bị chiếm**, đồng thời bảo đảm người dùng hợp lệ có cách phục hồi an toàn.

## 6. Giới hạn thử đăng nhập mà vẫn chống được lạm dụng

Một endpoint đăng nhập cần tính đến cả thử sai do người thật lẫn tấn công có tổ chức:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đăng nhập"]
    B{"Lạm dụng vượt<br/>ngưỡng chính sách?"}
    C["Giới hạn / tăng thời gian chờ<br/>và ghi nhận sự kiện"]
    D["Kiểm chứng password hash<br/>trên server"]
    E{"Bằng chứng đúng?"}
    F["Trả lỗi chung, cập nhật<br/>tín hiệu thất bại"]
    G{"Cần yếu tố bổ sung<br/>hoặc xác thực tăng cường?"}
    H["Kiểm chứng bằng chứng<br/>bổ sung còn hiệu lực"]
    I["Tạo phiên mới an toàn<br/>và ghi sự kiện thành công"]
    A --> B
    B -->|"Có"| C
    B -->|"Không"| D
    D --> E
    E -->|"Không"| F
    E -->|"Có"| G
    G -->|"Có"| H
    G -->|"Không"| I
    H -->|"Đạt"| I
    H -->|"Không đạt"| F
~~~

Trong hệ thống có nhiều server, **giới hạn phải có trạng thái chung hoặc cơ chế phối hợp**. Nếu mỗi máy tự đếm, kẻ tấn công có thể phân tán lượt thử để vượt ngưỡng. Kiểm soát theo IP đơn lẻ cũng chưa đủ: nhiều người dùng có thể cùng đi qua NAT/văn phòng, còn kẻ tấn công có thể dùng nhiều IP để tránh chặn.

Cần cân bằng ba điều:

- **Chống tự động hóa:** tăng chi phí thử nhiều bí mật, theo dõi đợt credential stuffing/password spraying, thách thức bổ sung khi rủi ro tăng.
- **Tính sẵn sàng:** không để kẻ tấn công khóa vô thời hạn tài khoản người khác chỉ bằng cách thử sai; cung cấp cơ chế tự phục hồi được bảo vệ.
- **Giảm lộ thông tin:** không trả “không tồn tại tài khoản này” trên các endpoint cho phép dò từng email; cần chú ý khác biệt giữa các đường xử lý.

**Ví dụ:** người dùng nhập sai mật khẩu ba lần trong vài phút khác với việc hàng trăm tài khoản khác nhau bị thử cùng một mật khẩu từ nhiều nguồn. Hệ thống cần quan sát cả mức **tài khoản** và mức **chiến dịch**, không chỉ một bộ đếm đơn giản.

## 7. Yếu tố biết nằm ở đâu trong MFA?

**Multi-Factor Authentication (MFA)** là xác thực dựa trên bằng chứng thuộc **ít nhất hai nhóm yếu tố độc lập** được triển khai phù hợp:

| Nhóm | Bản chất | Ví dụ |
| --- | --- | --- |
| **Điều biết** (*knowledge*) | Một bí mật người dùng biết. | Mật khẩu, passphrase, PIN kiểm tra từ xa. |
| **Điều có** (*possession*) | Bằng chứng kiểm soát một vật/thiết bị hoặc khóa bí mật. | Authenticator TOTP, khóa bảo mật, thiết bị giữ khóa riêng. |
| **Đặc điểm cá nhân** (*inherence*) | Đặc trưng sinh trắc hoặc cơ chế kiểm chứng tương ứng. | Vân tay, nhận diện khuôn mặt trong bộ xác thực phù hợp. |

Các cặp tình huống:

1. **Mật khẩu + mật khẩu khác:** vẫn cùng nhóm *knowledge*, không trở thành MFA.
2. **Mật khẩu + mã TOTP sinh từ authenticator độc lập:** thường là hai nhóm *knowledge + possession*, nhưng TOTP vẫn có thể bị phishing/chuyển tiếp trong thời gian hiệu lực.
3. **Mật khẩu + email OTP:** có thêm lớp kiểm soát, nhưng mức độ độc lập của kênh email và khả năng khôi phục phải được xem xét. Không mặc định mọi mã gửi qua email đạt cùng mức bảo đảm như authenticator chuyên dụng.
4. **Passkey với user verification bằng PIN/sinh trắc tại authenticator:** bằng chứng mật mã chứng minh quyền dùng khóa, đồng thời quá trình kiểm chứng người dùng được thực hiện cục bộ theo khả năng và chính sách authenticator. Ứng dụng phải xác minh chữ ký WebAuthn, challenge, origin/RP ID và cờ user verification khi yêu cầu.

Không nên chỉ hỏi “có đủ hai bước chưa?”. Cần hỏi **hai bằng chứng có độc lập không, chống phishing được đến đâu, và kẻ tấn công chiếm một bước có thể chiếm luôn bước còn lại hay không**.

### Xác thực mạnh không dừng lại sau đăng nhập

Sau MFA, server tạo **phiên hoặc token**. Nếu phiên bị đánh cắp, kẻ tấn công có thể bỏ qua cả mật khẩu lẫn OTP. Vì vậy vẫn phải bảo vệ cookie/token, thời hạn, thu hồi, chống CSRF khi cần và kiểm tra lại danh tính trước thao tác nhạy cảm. Nếu dùng OAuth/OIDC federation, ứng dụng nhận kết quả từ IdP cần xác minh thông điệp và mức bảo đảm theo giao thức, không tự tin một cờ “MFA done” do trình duyệt gửi.

## 8. Đổi, quên và khôi phục bí mật

**Khôi phục tài khoản là một luồng xác thực thay thế**, thường là điểm yếu nếu được thiết kế dễ hơn nhiều so với đăng nhập thông thường.

Với chức năng **quên mật khẩu**, một quy trình cơ bản:

1. Người dùng gửi yêu cầu; giao diện trả thông báo không tiết lộ email/tài khoản tồn tại hay không.
2. Server áp dụng chống lạm dụng gửi yêu cầu, sau đó gửi đường dẫn hoặc mã khôi phục tới **kênh đã được đăng ký và bảo vệ**.
3. Mã/đường dẫn cần có entropy đủ mạnh, thời hạn ngắn, ràng buộc với tài khoản và mục đích, chỉ được dùng một lần. Không để token khôi phục bị lộ qua log hay URL bên thứ ba.
4. Server xác minh bằng chứng khôi phục, cho phép tạo mật khẩu mới phù hợp chính sách và vô hiệu hóa mã đã dùng.
5. Ghi nhận sự kiện, thông báo tới kênh thích hợp; đánh giá và thu hồi các phiên/refresh token cũ theo mức rủi ro hoặc chính sách.

**Thay đổi mật khẩu khi đang đăng nhập** khác với “quên mật khẩu”: thao tác đổi credential nên yêu cầu xác thực lại phù hợp, đặc biệt nếu phiên đã lâu hoặc có dấu hiệu bất thường. Người đang cầm một cookie bị lấy cắp không nên mặc nhiên được đổi toàn bộ bằng chứng xác thực.

Câu hỏi bảo mật dễ đoán và các dữ liệu hồ sơ như ngày sinh, quê quán, tên người thân **không phải phương thức khôi phục đáng tin**. Nếu mất thiết bị MFA/passkey, cần có mã dự phòng được bảo vệ, phương thức xác thực dự phòng hoặc quy trình hỗ trợ có kiểm soát; không tự động bỏ bước kiểm chứng chỉ vì người dùng nói đã mất thiết bị.

## 9. Tình huống thực tế: đăng nhập một cổng nhân sự

Giả sử một công ty có cổng nhân sự, đăng nhập bằng email và mật khẩu. Một nhân viên dùng cùng mật khẩu cho cổng này và một diễn đàn bên ngoài. Sau khi diễn đàn bị lộ dữ liệu, kẻ tấn công thử thông tin trên cổng nhân sự.

### Phân tích bốn điểm hỏng

| Điểm hỏng | Hệ quả | Giải pháp theo đúng lớp |
| --- | --- | --- |
| Người dùng tái sử dụng mật khẩu. | Credential stuffing có thể thành công ngay lần đầu. | Mật khẩu duy nhất; dùng password manager; hỗ trợ passkey/MFA. |
| Endpoint chỉ giới hạn mỗi IP. | Kẻ tấn công phân tán nhiều nguồn để thử. | Thêm tín hiệu theo tài khoản, thiết bị và chiến dịch, tránh khóa nhầm. |
| Server lưu \`SHA-256(password)\` không salt. | Khi database lộ, kẻ tấn công thử đoán ngoại tuyến rất nhanh. | KDF chuyên dụng với salt và tham số được đánh giá. |
| Khi đổi mật khẩu, phiên cũ vẫn sống vô hạn. | Kẻ tấn công đã chiếm phiên có thể tiếp tục truy cập. | TTL phiên hợp lý, thu hồi phiên sau sự cố, xác thực lại cho thao tác nhạy cảm. |

Mỗi biện pháp giải quyết **một vị trí khác nhau trong chuỗi tấn công**. Mật khẩu mạnh không ngăn phiên bị đánh cắp. MFA không thể thay thế KDF. Rate limit không khắc phục database hash bị lộ. Cần thiết kế các lớp sao cho một thất bại không dẫn đến toàn quyền truy cập.

### Mã giả: quyết định xác thực bằng mật khẩu

~~~text
authenticate(identifier, password, context):
    signals = collectRiskSignals(identifier, context)
    if rateLimiter.denies(signals):
        audit("login_restricted", safeMetadataOnly)
        return genericFailureOrRetryLater()

    record = lookupPasswordVerifier(identifier)
    // Triển khai phải hạn chế lộ việc tài khoản có tồn tại hay không.
    valid = verifyPasswordUsingApprovedKDF(record, password)
    if not valid:
        audit("login_failed", safeMetadataOnly)
        return genericLoginFailure()

    if policy.requiresAdditionalFactor(record.accountId, signals):
        if not verifyFreshIndependentFactor(context):
            audit("login_failed", safeMetadataOnly)
            return genericLoginFailure()

    session = createFreshSession(record.accountId)
    audit("login_succeeded", safeMetadataOnly)
    return issueProtectedSession(session)
~~~

Mã giả dùng để học cách sắp thứ tự kiểm soát, không phải mã production. Cần xử lý an toàn cả khi \`record\` không tồn tại, tránh kênh phụ qua thời gian hoặc phản hồi; dùng KDF và API so sánh do thư viện đáng tin cậy cung cấp; chống đua trạng thái trong giới hạn thử và phiên; bảo vệ session ID/token; không lưu mật khẩu hay OTP vào log.

## 10. Bài tự kiểm tra và ghi nhớ

### Câu hỏi tự kiểm tra

1. Nếu người dùng phải nhập **hai PIN khác nhau** ở cùng một màn hình, đó có phải MFA không? Vì sao?
2. Nếu database lưu password hash có salt bị lộ, biện pháp **rate limit trên endpoint đăng nhập** có ngăn việc đoán mật khẩu ngoại tuyến không?
3. Tại sao **PIN mở khóa passkey cục bộ** khác với PIN gửi lên server để đăng nhập?
4. Khi một nhân viên đổi mật khẩu sau sự cố phishing, còn thành phần nào cần xử lý ngoài bản ghi password hash?
5. Trong thiết kế khôi phục tài khoản, điều gì xảy ra nếu câu trả lời “quê quán” được coi đủ để đặt lại mật khẩu?

### Gợi ý đối chiếu

- **Câu 1:** Không; cả hai vẫn là bằng chứng cùng loại *knowledge*. MFA đòi hỏi yếu tố độc lập thuộc nhóm khác.
- **Câu 2:** Không; việc đoán ngoại tuyến diễn ra ngoài server. Phải dựa vào bí mật đủ mạnh, KDF, salt và bảo vệ dữ liệu.
- **Câu 3:** PIN cục bộ là cách mở khóa authenticator; RP kiểm chứng bằng chứng mật mã, không nhận PIN đó. PIN gửi từ xa là một bí mật server cần kiểm tra.
- **Câu 4:** Xem xét thu hồi phiên và refresh token, điều tra thiết bị/kênh bị xâm phạm, thông báo và tăng cường bảo vệ, không chỉ sửa mật khẩu.
- **Câu 5:** Kẻ tấn công có thể dùng dữ liệu dễ tìm để chiếm quyền thiết lập mật khẩu mới; quy trình khôi phục trở thành điểm yếu hơn đăng nhập chính.

### Ghi nhớ

**Yếu tố biết xác thực bằng một bí mật người dùng có thể cung cấp.** Nó dễ triển khai nhưng có thể bị đoán, chia sẻ, phishing hoặc lộ từ dịch vụ khác. Để giảm truy cập trái phép cần kết hợp **mật khẩu dài và duy nhất, quản lý bí mật an toàn, KDF với salt, giới hạn và phát hiện lạm dụng, MFA/passkey phù hợp, phiên an toàn và khôi phục tài khoản có kiểm soát**. Quan trọng hơn, phải xác định ranh giới: server kiểm chứng bí mật, authenticator có thể kiểm chứng PIN cục bộ, còn API tự chịu trách nhiệm kiểm tra quyền truy cập.
