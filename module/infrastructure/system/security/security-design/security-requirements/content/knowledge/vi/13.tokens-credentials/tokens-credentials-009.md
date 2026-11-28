# Token storage

## 1. Lưu token là giữ một khả năng truy cập

Token không phải dữ liệu cấu hình thông thường. Với bearer token, bên có được giá trị còn hiệu lực có thể sử dụng quyền gắn với token mà không cần biết mật khẩu của người dùng. Một ứng dụng có cơ chế cấp quyền đúng vẫn có thể mất an toàn nếu token xuất hiện trong cơ sở dữ liệu đọc được quá rộng, log, browser storage hoặc bản sao lưu không được kiểm soát.

Mục tiêu của token storage không chỉ là “có mã hóa”, mà là:

> Chỉ thành phần thực sự cần sử dụng hoặc xác minh token mới được tiếp cận dạng dữ liệu cần thiết cho nhiệm vụ đó; mọi bản sao phải được giới hạn quyền truy cập, thời gian tồn tại và khả năng phục hồi theo đúng vòng đời credential.

Yêu cầu lưu trữ phải xét cả giá trị token, metadata quyết định hiệu lực và khóa dùng bảo vệ dữ liệu. Nếu không sửa được token nhưng có thể đổi `subjectId`, `tenantId` hoặc trạng thái thu hồi trong kho, kẻ tấn công vẫn có thể phá vỡ liên kết quyền.

Trong module yêu cầu bảo mật, điều cần tạo ra là một contract kiểm chứng được: lưu loại token nào, ở đâu, dưới dạng nào, ai có quyền đọc hoặc sử dụng, khi nào dọn và xử lý thế nào khi bị lộ hoặc phải khôi phục dữ liệu.

## 2. Câu hỏi đầu tiên: có cần lấy lại token gốc không?

Hai hệ thống đều “lưu token” nhưng có thể có mục tiêu hoàn toàn khác:

1. Máy chủ tự phát hành token và chỉ cần xác minh giá trị client gửi lại.
2. Client nhận token từ một hệ thống khác và sau đó cần xuất trình chính token đó để gọi API hoặc refresh.

Sự khác biệt này quyết định có thể dùng dữ liệu một chiều hay cần cơ chế bảo vệ có thể giải mã.

| Vai trò | Nhu cầu thực tế | Dạng lưu phù hợp để đánh giá |
|---|---|---|
| Máy chủ xác minh opaque session token do mình quản lý | So sánh token được gửi với bản ghi phiên | Verifier một chiều và metadata, nếu phù hợp mô hình |
| Authorization server quản lý refresh token opaque của mình | Nhận diện, xác minh, xoay vòng và thu hồi token | Có thể lưu verifier một chiều theo thiết kế giao thức |
| OAuth client giữ refresh token của nhà cung cấp khác | Gửi lại token gốc đến token endpoint | Kho lưu có khả năng lấy lại token, với mã hóa và kiểm soát truy cập |
| Resource server kiểm tra JWT | Xác minh token nhận trên request | Thường không cần lưu bền vững toàn bộ raw token chỉ để kiểm tra chữ ký |
| Trình duyệt giữ credential phiên | Gửi credential khi gọi ứng dụng | Cơ chế client được chọn theo ranh giới script, cookie và phiên |

Không thể gửi `SHA-256(refreshToken)` thay cho refresh token gốc tới một authorization server yêu cầu token gốc. Ngược lại, một máy chủ chỉ cần xác minh token có thể không cần giữ bản sao có thể dùng lại làm bearer credential.

### Hash, mã hóa và encoding không thay thế nhau

| Cơ chế | Có thể lấy lại giá trị gốc bằng thiết kế thông thường không? | Vai trò |
|---|---|---|
| Encoding như Base64 | Có, không cần bí mật | Biểu diễn dữ liệu |
| Hash một chiều | Không có thao tác giải mã | Tạo verifier trong mô hình phù hợp |
| Mã hóa có xác thực | Có khi được phép dùng khóa | Bảo mật và kiểm tra tính toàn vẹn dữ liệu được mã hóa |
| Phân quyền đọc/sử dụng | Không phải phép biến đổi dữ liệu | Giới hạn chủ thể tiếp cận dữ liệu hoặc thao tác |

Base64 không phải mã hóa bảo mật. JWT có chữ ký cũng không tự che giấu payload. Mã hóa dữ liệu không thay thế việc xác định ai được phép yêu cầu giải mã.

## 3. Bắt đầu từ mô hình đe dọa và bản đồ bản sao

Không có một thuộc tính lưu trữ đủ để xử lý mọi kiểu xâm nhập. Cần nêu khả năng của bên tấn công và điều hệ thống phải bảo vệ trong từng trường hợp.

| Khả năng của bên tấn công | Rủi ro điển hình | Kiểm soát cần xem xét |
|---|---|---|
| Chỉ đọc được một dump cơ sở dữ liệu | Lấy bearer token thô hoặc dữ liệu quyền | Verifier một chiều khi có thể; mã hóa với khóa nằm ngoài dump; giới hạn metadata |
| Đọc được ổ đĩa hoặc snapshot | Lấy tệp, cache, swap, backup | Bảo vệ lưu trữ, khóa, quyền snapshot và chính sách dump |
| Có script chạy trong origin của ứng dụng | Đọc dữ liệu script có quyền và thao tác dưới phiên người dùng | Giảm token lộ cho script, chống XSS, bảo vệ hành động |
| Chiếm tiến trình có quyền giải mã | Lấy plaintext khi dùng hoặc gọi dịch vụ khóa | Giảm đặc quyền, cô lập, giới hạn tác động, phát hiện và thu hồi |
| Sửa được bản ghi token | Thay người nhận, scope, trạng thái hoặc verifier | Bảo vệ quyền ghi và tính toàn vẹn, kiểm tra liên kết quyền |
| Có quyền đọc log hoặc hệ thống hỗ trợ | Thu thập token vô tình bị ghi | Redaction, loại bỏ credential trước khi phát telemetry, quyền đọc hẹp |

Ví dụ, mã hóa cơ sở dữ liệu trên đĩa có thể bảo vệ khi ổ đĩa bị lấy cắp nhưng không ngăn một tài khoản có quyền `SELECT` đọc cột plaintext thông qua dịch vụ cơ sở dữ liệu. Mã hóa ở tầng ứng dụng với khóa ngoài cơ sở dữ liệu giải quyết một ranh giới khác, nhưng vẫn không ngăn tiến trình được phép giải mã lạm dụng quyền đó.

### Bản đồ bản sao cần đầy đủ

```text
Token được nhận hoặc tạo
    → bộ nhớ tiến trình
    → cookie hoặc vùng lưu client
    → cơ sở dữ liệu / secret store / cache
    → replica và backup

Các nhánh rò rỉ cần kiểm soát:
    request log, tracing, lỗi, crash dump,
    công cụ debug, hàng đợi, export và gói hỗ trợ
```

Với mỗi nơi lưu, cần trả lời: token có cần xuất hiện ở đây không, ai có thể đọc, có thể xuất hàng loạt không, tồn tại bao lâu và khi nào bản sao mất khả năng tạo quyền.

## 4. Lưu verifier khi máy chủ chỉ cần xác minh

Giả sử ứng dụng tự phát hành opaque session token ngẫu nhiên đủ mạnh. Máy chủ có thể lưu một verifier thay vì giữ raw bearer token trong kho phiên.

Một thiết kế minh họa tách hai phần:

```text
Client giữ:
    publicLookupId.secret

Máy chủ giữ:
    publicLookupId
    digest(secret)
    subjectId, tenantId
    issuedAt, expiresAt, state
    thông tin vòng đời cần thiết
```

`publicLookupId` giúp tìm bản ghi, không phải bằng chứng xác thực. `secret` mới là phần phải khó đoán và cần được client bảo vệ. Không cộng độ dài của mã tra cứu công khai vào ngân sách bí mật của secret.

OWASP mô tả việc lưu verifier một chiều để giảm nguy cơ tái sử dụng khi kho session bị đọc, cùng một cách tách mã tra cứu và secret verifier. Xem [OWASP Session Management — Server-Side Session Token Storage](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#server-side-session-token-storage).

### 4.1. Luồng phát hành và kiểm tra minh họa

```text
Phát hành:
    tạo publicLookupId theo chính sách không xung đột
    tạo secret từ nguồn ngẫu nhiên mật mã đủ mạnh
    tính verifier từ toàn bộ byte secret
    lưu verifier và metadata bằng thao tác tạo không ghi đè
    trả token cho client qua kênh được bảo vệ

Kiểm tra:
    phân tích token với giới hạn định dạng và độ dài
    tìm bản ghi bằng publicLookupId
    tính verifier từ secret được gửi
    so sánh verifier bằng cơ chế phù hợp
    kiểm tra trạng thái, thời hạn, chủ thể và phạm vi
    chỉ tạo ngữ cảnh xác thực sau khi mọi điều kiện đạt
```

Các bước trên là mã giả của thiết kế, không phải một implementation hoàn chỉnh. Khi so sánh các byte verifier bí mật, dùng cơ chế so sánh được thiết kế để hạn chế rò rỉ thời gian. Đồng thời cần xem hành vi của toàn endpoint; một phép so sánh riêng lẻ không bảo đảm mọi đường xử lý đều có thời gian không phân biệt được.

### 4.2. Vì sao không áp dụng máy móc quy tắc hash mật khẩu?

Token ngẫu nhiên có không gian bí mật đủ lớn khác mật khẩu do người dùng chọn. Với token ngẫu nhiên mạnh, một hash mật mã phù hợp như SHA-256 có thể được dùng làm verifier mà không cần áp dụng cơ chế kéo dài thời gian tính như với mật khẩu yếu.

Điều kiện quan trọng là secret thực sự đủ khó đoán. Mã sáu chữ số, timestamp hoặc token từ bộ sinh dự đoán được vẫn có thể bị dò offline nếu dump verifier bị lộ. Không được dùng nhận xét về token ngẫu nhiên mạnh để biện minh cho việc hash nhanh mọi credential.

Nếu thiết kế chọn HMAC với khóa riêng để tăng bảo vệ khi chỉ cơ sở dữ liệu bị đọc, cần đặc tả quản lý khóa, version, rotation và cách xác minh dữ liệu cũ. HMAC không loại bỏ yêu cầu token đủ mạnh, và khóa không được nằm ngay trong cùng bản dump được giả định sẽ bị lộ.

### 4.3. Giới hạn của verifier một chiều

Verifier giúp giảm nguy cơ từ việc chỉ đọc dữ liệu. Nó không tự bảo vệ khi bên tấn công sửa được bản ghi, thay verifier thành giá trị của mình, đổi người nhận hoặc điều khiển tiến trình xác thực.

Không lưu raw secret ở một cột khác, log hoặc bản backup phụ rồi tuyên bố kho chính “chỉ lưu hash”. Mục tiêu chỉ đạt nếu các bản sao trong phạm vi đe dọa cũng không chứa credential có thể tái sử dụng.

Khi mất secret gốc ở client, máy chủ không thể lấy lại nó từ hash để gửi lại. Quy trình khôi phục phải phát hành credential mới theo cơ sở xác thực hợp lệ, không biến verifier thành credential được chấp nhận thay thế.

## 5. Lưu token cần lấy lại bằng cơ chế bảo vệ có thể giải mã

Một backend gọi dịch vụ bên ngoài thường cần xuất trình access token hoặc refresh token gốc. Trường hợp này cần hạn chế khả năng lấy plaintext, không thể chỉ lưu hash.

Một mô hình khái niệm:

```text
Token gốc
    → mã hóa có xác thực ở ranh giới được chọn
    → ciphertext + metadata cần thiết trong kho dữ liệu

Workload được phép
    → kiểm tra quyền lấy token cho đúng mục đích
    → yêu cầu sử dụng khóa qua KMS hoặc cơ chế tương đương
    → giải mã trong thời gian cần dùng
    → gọi đúng dịch vụ đích
```

Không cần mỗi ứng dụng tự sáng tạo giao thức mã hóa. Có thể dùng thư viện hoặc dịch vụ quản lý secret phù hợp, nhưng vẫn phải biết ranh giới nào được bảo vệ và chủ thể nào có quyền giải mã.

### 5.1. Tách quyền đọc dữ liệu khỏi quyền giải mã

Một nhân viên hỗ trợ có thể cần xem issuer, thời điểm hết hạn và trạng thái kết nối, nhưng không cần lấy raw refresh token. Một tác vụ báo cáo có thể đọc metadata mà không được gọi KMS để giải mã.

OWASP khuyến nghị áp dụng least privilege và quyền truy cập chi tiết cho hệ thống quản lý secret. Xem [OWASP Secrets Management — Access Control](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html#23-access-control).

Chính sách cần nêu riêng:

- Ai được xem metadata?
- Workload nào được đọc ciphertext?
- Workload nào được sử dụng khóa hoặc yêu cầu lấy plaintext?
- Ai được đổi policy, export, backup hoặc khôi phục secret?
- Quyền khẩn cấp có giới hạn thời gian và audit như thế nào?

Quyền giải mã hàng loạt thường có tác động lớn hơn quyền xử lý một token của một tài khoản. Không cấp quyền rộng mặc định cho mọi thành phần cùng dùng một cơ sở dữ liệu.

### 5.2. Bảo vệ liên kết với tenant và mục đích

Nếu một ciphertext được chuyển sang bản ghi của người dùng khác, ứng dụng không được sử dụng token đó dưới ngữ cảnh sai. Cần bảo vệ và kiểm tra liên kết giữa token với chủ thể, tenant, issuer, client và tài nguyên đích theo contract.

Khi cơ chế mã hóa hỗ trợ authenticated associated data, các trường ngữ cảnh thích hợp có thể được ràng buộc với ciphertext để phát hiện việc chuyển đổi trái phép. Nhưng dữ liệu ngữ cảnh đó phải được lấy và kiểm tra từ nguồn đáng tin. Việc giải mã thành công không tự chứng minh người gọi được phép sử dụng secret.

Kho token phải kiểm tra tenant và ủy quyền tại API lấy hoặc sử dụng token, không chỉ dựa vào tên đường dẫn do client gửi. Mỗi lớp phải thực hiện đúng trách nhiệm thay vì cho rằng “đã có mã hóa” là đủ.

### 5.3. Khóa là một phần của thiết kế lưu trữ

Yêu cầu cần nêu cách tạo, lưu, sử dụng, đổi, vô hiệu hóa và phục hồi khóa. Không giữ khóa giải mã cùng ciphertext trong cùng tệp cấu hình hoặc ảnh triển khai mà bất kỳ người đọc dữ liệu nào cũng có thể lấy.

Đổi khóa không nhất thiết đồng nghĩa đổi token bên ngoài, và thu hồi token không đồng nghĩa đổi khóa mã hóa. Hai vòng đời có liên hệ nhưng khác nhau. Nếu thay khóa, phải xử lý version dữ liệu và khả năng đọc những bản ghi còn hợp lệ theo quy trình đã chọn.

Nếu không truy cập được dịch vụ khóa, hệ thống phải thất bại theo chính sách đã xác định. Không ghi plaintext tạm xuống đĩa hoặc dùng khóa mặc định để duy trì hoạt động mà không có thiết kế được chấp thuận.

## 6. Token trong trình duyệt

### 6.1. Phân biệt các vùng lưu

| Cách giữ dữ liệu | Thuộc tính cần hiểu | Rủi ro còn lại |
|---|---|---|
| Bộ nhớ JavaScript | Thường không lưu bền sau khi mất ngữ cảnh trang | Script độc hại cùng ngữ cảnh có thể sử dụng hoặc lấy dữ liệu |
| `localStorage` | Lưu bền và script cùng origin có thể truy cập | XSS hoặc thư viện bị xâm nhập có thể đọc token |
| `sessionStorage` | Có vòng đời và phạm vi tab khác `localStorage` | Vẫn có thể bị script trong ngữ cảnh được phép đọc |
| IndexedDB | Lưu dữ liệu có cấu trúc theo cơ chế của origin | Không phải kho bí mật miễn nhiễm mã cùng origin |
| Cookie `HttpOnly` | Không cho script đọc giá trị qua API cookie thông thường | Trình duyệt vẫn gửi cookie trong request phù hợp |

Việc đổi tên một khóa storage hoặc mã hóa token bằng khóa cũng nằm trong JavaScript có thể bị đọc cùng lúc không tạo một ranh giới bí mật đáng tin trước XSS. Cần xác định bên tấn công có thể lấy cả dữ liệu và khả năng giải mã hay không.

Một kiến trúc giảm mức lộ token cho browser là backend giữ access token và refresh token, còn browser chỉ giữ credential phiên để nói chuyện với backend. Khi đó hệ thống vẫn cần bảo vệ credential phiên, kiểm tra authorization và chống CSRF ở ranh giới browser–backend. Không coi việc chuyển token về backend là hoàn thành mọi yêu cầu bảo mật.

### 6.2. Cookie cần chính sách đầy đủ

Ví dụ cookie phiên cho một host:

```http
Set-Cookie: __Host-session=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Đây là cookie phiên minh họa, không phải access token thật. Với tiền tố `__Host-`, cookie phải có `Secure`, `Path=/` và không có `Domain` ở user agent hỗ trợ tiền tố đó. `HttpOnly` ngăn script đọc cookie nhưng cookie vẫn được gửi trong request phù hợp. Xem [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Các thuộc tính cần được chọn theo luồng thực tế. `SameSite=Lax` không phải cơ chế chống mọi CSRF; `Secure` không ngăn người có quyền đọc máy client lấy dữ liệu; path cookie không phải một ranh giới authorization giữa các phần ứng dụng.

Nếu cần cookie cross-site, phải đánh giá riêng sự tương thích, chính sách cookie và biện pháp chống yêu cầu giả mạo. Không mở rộng domain hoặc giảm bảo vệ chỉ để một luồng đăng nhập hoạt động mà chưa hiểu phạm vi mới.

### 6.3. Logout và đổi tài khoản

Khi kết thúc phiên, cần dọn đúng cookie và trạng thái client được quản lý. Nhưng xóa token khỏi storage không làm mất hiệu lực một bản sao ở nơi khác; phải có cơ chế chấm dứt phía máy chủ hoặc giới hạn token phù hợp.

Khi đổi từ tài khoản A sang B, cache trong bộ nhớ, service worker hoặc lớp dữ liệu client không được trả dữ liệu của A cho B. Đây là yêu cầu cách ly dữ liệu client, cần kiểm thử ngoài việc cookie đã thay đổi.

## 7. Token trên mobile và desktop client

Ứng dụng native cần đánh giá cả dữ liệu lưu trên thiết bị lẫn khả năng dùng credential khi thiết bị bị mất hoặc tiến trình bị xâm nhập.

Trên Android, Keystore chủ yếu bảo vệ khóa mật mã và giới hạn cách dùng khóa; không nên diễn đạt như thể mọi chuỗi token tự động được lưu trực tiếp an toàn trong Keystore. Một thiết kế có thể dùng khóa được Keystore bảo vệ để mã hóa dữ liệu token lưu ở vùng ứng dụng. Khả năng bảo vệ bằng phần cứng phụ thuộc thiết bị và cấu hình. Xem [Android Keystore system](https://developer.android.com/privacy-and-security/keystore).

Trên nền tảng Apple, Keychain cung cấp cơ chế lưu các dữ liệu bí mật nhỏ. Khi áp dụng cho token cần chọn thuộc tính truy cập và chia sẻ phù hợp với yêu cầu ứng dụng. Xem [Apple Keychain services](https://developer.apple.com/documentation/security/keychain-services).

Một đặc tả cho client native cần trả lời:

- Credential nào phải tồn tại sau khi đóng ứng dụng, credential nào chỉ ở bộ nhớ?
- Khi thiết bị khóa, thành phần nào còn được phép sử dụng token?
- Có yêu cầu người dùng xác thực trước khi dùng khóa hoặc secret không?
- Dữ liệu có được backup, đồng bộ hoặc chuyển sang thiết bị mới không?
- Cơ chế chia sẻ giữa ứng dụng có thật sự cần thiết không?
- Logout, mất thiết bị và đổi tài khoản sẽ xóa hoặc thu hồi những gì?

Không đặt token trong preference, tệp cấu hình hoặc database thông thường chỉ vì chúng nằm trong thư mục riêng của ứng dụng. Nếu mô hình đe dọa gồm việc đọc dữ liệu thiết bị, cần một cơ chế bảo vệ phù hợp với khả năng đó.

Kho bảo mật của hệ điều hành không loại bỏ hoàn toàn rủi ro ở runtime. Khi ứng dụng được phép dùng token, plaintext hoặc khả năng sử dụng credential vẫn có thể xuất hiện trong ranh giới thực thi của ứng dụng. Cần kết hợp giới hạn quyền, thời hạn và thu hồi phía máy chủ.

## 8. Vòng đời lưu trữ: hết hạn, cache, backup và phục hồi

### 8.1. Hết hiệu lực khác với bị xóa khỏi kho

Cần tách ít nhất ba thời điểm:

- **Hết hiệu lực:** credential không còn được phép xác thực hoặc tạo quyền.
- **Dọn dữ liệu vận hành:** bản ghi không còn cần cho xử lý trực tuyến được loại bỏ.
- **Kết thúc retention:** các bản sao lưu, bản xuất và dữ liệu còn được giữ theo chính sách hết thời hạn lưu.

Không được chờ tác vụ xóa định kỳ chạy mới từ chối token đã hết hạn. Ngược lại, xóa bản ghi ở một client không chứng minh token đã bị thu hồi tại hệ thống phát hành. Đặc tả phải nói rõ thành phần nào quyết định hiệu lực và loại token nào chịu sự quyết định đó.

Ví dụ, một authorization server thu hồi refresh token có thể ngăn việc cấp access token mới, nhưng không được tự suy ra mọi resource server đã ngừng chấp nhận access token đang tồn tại. Cần xác định cơ chế kiểm tra và phạm vi thu hồi của hệ thống. RFC 7009 cũng nêu khả năng có độ trễ lan truyền thông tin vô hiệu hóa giữa các máy chủ. Xem [RFC 7009, mục 2.1 — Revocation Request](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1).

### 8.2. Cache và replica phải tuân theo giới hạn thu hồi

Một bản ghi bị thu hồi ở kho chính vẫn có thể được chấp nhận nếu node xử lý tiếp tục tin cache cũ. Vì vậy, yêu cầu “thu hồi ngay” chưa đủ để thiết kế và kiểm thử.

Cần xác định:

- Mốc bắt đầu đo: khi lệnh thu hồi được chấp nhận, khi giao dịch được commit hay khi người dùng bấm logout?
- Giới hạn trễ cho từng đường xác thực, gồm cache, replica và vùng triển khai.
- Cách vô hiệu hóa cache hoặc giới hạn thời gian sử dụng trạng thái cũ.
- Hành vi khi không thể xác nhận trạng thái thu hồi còn đủ mới.
- Cách kiểm tra để một cache lạnh hoặc node vừa khởi động không nạp lại dữ liệu cũ.

Có thể dùng TTL ngắn, sự kiện vô hiệu hóa hoặc kiểm tra phiên bản trạng thái tùy kiến trúc. TTL của cache chỉ là một tham số; giới hạn thực tế còn phụ thuộc replica lag, thời điểm nạp dữ liệu và hành vi khi lỗi. Phải đo từ đầu đến cuối theo đường request mà ứng dụng sử dụng.

### 8.3. Phục hồi không được làm sống lại credential đã chấm dứt

Xét tình huống tự xây dựng từ mô hình đe dọa của bài:

```text
09:00  backup chứa phiên S đang hoạt động
09:10  S bị thu hồi vì nghi ngờ bị lộ
09:20  xảy ra sự cố kho phiên
09:30  hệ thống phục hồi từ backup lúc 09:00
```

Nếu chỉ tin trường trạng thái trong backup, phiên S có thể xuất hiện trở lại như đang hoạt động. Do đó, yêu cầu phục hồi phải bao gồm tính đúng đắn của trạng thái bảo mật, bên cạnh khả năng đọc dữ liệu.

Tùy kiến trúc, hệ thống có thể giữ thông tin thu hồi ở nguồn độc lập đủ mới, đối soát sự kiện sau thời điểm backup hoặc vô hiệu hóa toàn bộ nhóm credential không thể xác minh. Nếu không chứng minh được trạng thái an toàn, luồng phụ thuộc credential phải yêu cầu cấp lại hoặc xác thực lại trước khi phục vụ.

Đây là các lựa chọn thiết kế cho tình huống minh họa, không phải khẳng định rằng mọi sản phẩm hỗ trợ cùng một cơ chế. Quy trình đã chọn cần có người chịu trách nhiệm và một bài diễn tập phục hồi có thể lặp lại.

Backup chứa ciphertext vẫn cần được bảo vệ vì có thể bị giải mã nếu khóa còn khả dụng. Việc xóa bản ghi trực tuyến cũng không tự xóa mọi snapshot bất biến. Cần ghi rõ retention, quyền phục hồi và giới hạn bảo đảm xóa. OWASP đề cập riêng việc mã hóa backup, thu hẹp quyền truy cập và kiểm thử restore trong [Secrets Management — Backup and Restore](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html#29-downtime-break-glass-backup-and-restore).

### 8.4. Cập nhật token khi refresh phải nhất quán

Với refresh token rotation, client có thể nhận giá trị mới và cần thay thế giá trị đang lưu. RFC 9700 mô tả việc authorization server vô hiệu hóa refresh token trước đó, giữ liên kết giữa các token và dùng thông tin này để phát hiện tái sử dụng. Xem [RFC 9700, mục 4.14.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2).

Từ hành vi đó, đặc tả lưu trữ của client cần trả lời: hai request refresh đồng thời được phối hợp ra sao; cập nhật bản ghi mới có thể bị ghi đè bởi kết quả cũ không; và ứng dụng làm gì nếu nhận token mới nhưng chưa lưu bền thì bị dừng.

Có thể dùng một đầu mối điều phối refresh theo credential và cập nhật bản ghi có kiểm tra version. Tuy nhiên, giao dịch trong database của client không tự tạo ra giao dịch nguyên tử với authorization server bên ngoài. Khi kết quả refresh không xác định, cần xử lý theo contract của nhà cung cấp; không giả định token cũ luôn dùng lại được hoặc gửi lại vô hạn.

## 9. Chuyển quyết định kiến trúc thành yêu cầu kiểm chứng được

Một câu như “token được lưu an toàn” không chỉ ra điều kiện nghiệm thu. Mẫu viết hữu ích là:

> Khi **điều kiện** xảy ra, **thành phần chịu trách nhiệm** phải thực hiện **hành vi cụ thể**, trong **phạm vi và giới hạn đã định**, được chứng minh bằng **bằng chứng kiểm tra**.

### 9.1. Bối cảnh minh họa và giả định

Giả sử một cổng quản trị nhiều tenant sử dụng backend để gọi API của đối tác. Browser giữ opaque session credential; backend lưu verifier của phiên. Refresh token của đối tác cần lấy lại được nên được lưu mã hóa, còn access token chỉ được cache trong bộ nhớ theo nhu cầu.

Trong ví dụ này, nhóm dự án chọn:

- Phiên có thời hạn tuyệt đối 8 giờ, hết hạn sau 15 phút không hoạt động.
- Trạng thái thu hồi phiên được áp dụng trên mọi node xử lý trong tối đa 30 giây từ khi giao dịch thu hồi commit.
- Bản ghi secret không còn cần sử dụng được dọn khỏi kho trực tuyến trong tối đa 24 giờ sau khi chấm dứt kết nối.
- Backup giữ trong 7 ngày; phục hồi phải đối soát trạng thái thu hồi trước khi mở lại luồng phụ thuộc credential.

**Các con số này là giả định của ví dụ, không phải giá trị mặc định do OWASP hoặc RFC bắt buộc.** Dự án thực tế phải chọn giới hạn theo rủi ro, độ nhạy dữ liệu, yêu cầu nghiệp vụ và khả năng kiến trúc. Hạn của access token và refresh token bên ngoài còn phụ thuộc nhà cung cấp.

### 9.2. Ma trận rủi ro, yêu cầu và bằng chứng

Các mã rủi ro trong bảng chỉ dùng cho tình huống minh họa:

| Mã | Rủi ro được xử lý | Yêu cầu cụ thể | Bằng chứng nghiệm thu |
|---|---|---|---|
| TS-01 | R1: dump kho phiên chứa bearer token dùng lại được | Kho phiên chỉ giữ verifier và metadata cần thiết; không giữ raw secret của phiên | Kiểm tra schema và dump dữ liệu thử; gửi riêng lookup ID hoặc verifier thay cho credential phải bị từ chối |
| TS-02 | R2: người đọc database lấy được refresh token của đối tác | Refresh token lưu bền phải được mã hóa có xác thực; quyền đọc dữ liệu không mặc nhiên cho quyền sử dụng khóa | Tài khoản chỉ đọc database không lấy được plaintext; workload được cấp quyền đúng có thể sử dụng token cho tác vụ hợp lệ |
| TS-03 | R3: dùng credential của tenant khác | API sử dụng token phải xác thực workload và kiểm tra quyền với tenant, chủ thể, kết nối và mục đích đích | Đổi connection ID sang tenant khác bị từ chối trước khi gọi đối tác; có audit sự kiện từ chối |
| TS-04 | R4: phiên quá hạn vẫn có hiệu lực | Mọi đường xác thực phiên áp dụng hạn tuyệt đối 8 giờ và hạn bất hoạt 15 phút ở máy chủ | Kiểm thử sát các mốc thời gian; hoạt động liên tục không kéo dài hạn tuyệt đối; tác vụ dọn chưa chạy vẫn bị từ chối |
| TS-05 | R5: cache tiếp tục chấp nhận phiên đã thu hồi | Không node nào chấp nhận phiên sau 30 giây kể từ commit thu hồi; quá thời hạn cho phép mà không xác minh được trạng thái mới thì từ chối xác thực | Giữ bản sao credential trước logout, phát lại vào từng node và mô phỏng đứt kết nối cập nhật trạng thái |
| TS-06 | R6: token lọt vào telemetry | Không ghi raw credential vào log, trace, lỗi, sự kiện audit hoặc gói hỗ trợ trong các luồng được đặc tả | Dùng token thử có dấu hiệu nhận biết; kiểm tra cả đường thành công và lỗi tại nơi dữ liệu telemetry được tiếp nhận |
| TS-07 | R7: bản sao lưu hoặc bản ghi cũ kéo dài rủi ro | Dọn secret khỏi kho trực tuyến trong 24 giờ; backup có retention 7 ngày và quyền phục hồi riêng | Quan sát tác vụ dọn trên dữ liệu thử; kiểm tra chính sách backup và quyền đọc, khôi phục |
| TS-08 | R8: restore làm sống lại phiên bị thu hồi | Đối soát trạng thái thu hồi trước khi mở luồng dùng credential; nếu không đủ dữ liệu xác minh thì vô hiệu hóa nhóm bị ảnh hưởng | Diễn tập tình huống mục 8.3; phiên S vẫn bị từ chối sau restore |
| TS-09 | R9: dịch vụ khóa lỗi dẫn đến bỏ kiểm soát | Khi không thể giải mã hợp lệ, backend không gọi đối tác và không lưu plaintext dự phòng | Mô phỏng timeout và mất quyền giải mã; không phát sinh request có credential hoặc bản ghi plaintext |
| TS-10 | R10: script đọc token của đối tác từ browser | Browser không nhận token của đối tác trong kiến trúc này; cookie phiên có các thuộc tính đã đặc tả | Kiểm tra response, cookie và browser storage; kiểm thử CSRF riêng cho các thao tác thay đổi trạng thái |

Bằng chứng dump hoặc tìm chuỗi chỉ bao phủ những bản sao được quan sát trong bài kiểm thử. Nó cần đi cùng kiểm tra cấu hình, luồng dữ liệu và quyền truy cập để tránh kết luận quá rộng từ một lần không tìm thấy token.

TS-05 áp dụng cho phiên do cổng quản trị kiểm soát. Không dùng kết quả đó để tuyên bố access token của đối tác cũng bị thu hồi trong 30 giây. Nếu nghiệp vụ cần giới hạn này ở đối tác, phải có yêu cầu và cơ chế tương ứng được đối tác hỗ trợ.

### 9.3. Ví dụ tiêu chí chấp nhận cho thu hồi phiên

```gherkin
Given phien S con han va da duoc nap vao cache cua cac node
And ban sao credential cua S duoc giu trong moi truong kiem thu
When giao dich thu hoi S commit tai thoi diem t0
Then moi request bat dau tu t0 + 30 giay voi credential S bi tu choi
And node mat ket noi cap nhat khong duoc chap nhan trang thai cu qua han
And log chi chua ma su kien va dinh danh doi soat duoc phep
And log khong chua raw credential
```

Tiêu chí này cần được chạy qua các đường xác thực có trong kiến trúc, không chỉ một endpoint thuận tiện. Cần ghi rõ cách đồng bộ hoặc kiểm soát thời gian trong môi trường thử và điểm quan sát kết quả. Quyền của request đã được chấp nhận trước thời hạn thu hồi là một yêu cầu riêng nếu nghiệp vụ cần hủy cả tác vụ đang chạy.

## 10. Logging, vận hành và ứng phó khi lộ token

### 10.1. Ghi sự kiện cần thiết mà không tạo kho credential thứ hai

Một sự kiện sử dụng token có thể ghi workload, hành động, thời gian, kết quả, correlation ID và ID bản ghi không dùng để xác thực. Chỉ giữ metadata đáp ứng mục đích audit; metadata về chủ thể hoặc tenant vẫn cần quyền truy cập và retention phù hợp.

Các điểm dễ bỏ sót gồm header Authorization ở reverse proxy, request body của token endpoint, response refresh khi bật debug, trace tự động và thông báo lỗi từ thư viện gọi API. Redaction cần thực hiện trước khi chuyển dữ liệu đến hệ thống log hoặc đơn vị xử lý bên ngoài.

Không coi một prefix hoặc một phần credential là an toàn mặc định. Nếu cần dấu vết đối soát, ưu tiên ID nội bộ không có giá trị xác thực. Tuyệt đối không tạo endpoint nhận ID đó như phương thức đăng nhập thay thế.

### 10.2. Sự cố phải xử lý cả credential và nơi lưu

Nếu phát hiện token trong log, chỉ xóa dòng log không xử lý bản sao mà người khác có thể đã lấy. Quy trình cho tình huống này cần:

1. Xác định loại token, chủ thể, phạm vi quyền, thời hạn và những hệ thống đã nhận dữ liệu.
2. Thu hồi hoặc thay thế credential theo cơ chế mà bên phát hành hỗ trợ; xử lý các phiên hoặc grant liên quan theo chính sách đã đặc tả.
3. Ngăn luồng ghi token tiếp tục phát sinh và hạn chế quyền truy cập dữ liệu đã bị ảnh hưởng.
4. Kiểm tra việc phát lại bản sao cũ theo phạm vi thu hồi, đồng thời theo dõi dấu hiệu sử dụng bất thường.
5. Xử lý các bản sao còn giữ theo quy trình ứng phó và retention; lưu bằng chứng điều tra ở nơi có quyền phù hợp.

Nếu chỉ lộ token mà khóa mã hóa không bị ảnh hưởng, đổi khóa mã hóa không tự thu hồi token đó. Nếu khóa hoặc workload có quyền giải mã bị xâm nhập, cần đánh giá thêm các secret mà quyền đó có thể tiếp cận. Phạm vi ứng phó phải theo bằng chứng sự cố.

## 11. Những câu đặc tả cần viết rõ hơn

| Câu còn mơ hồ | Điều cần bổ sung |
|---|---|
| “Token phải được mã hóa” | Token nào cần lấy lại, mã hóa ở ranh giới nào, ai có quyền giải mã và metadata nào phải được ràng buộc |
| “Không lưu token ở client” | Kiến trúc vẫn cần credential phiên hay không, vùng lưu cụ thể, vòng đời và biện pháp bảo vệ request |
| “Xóa token khi logout” | Xóa bản sao nào, chấm dứt hiệu lực ở đâu, giới hạn lan truyền và cách kiểm thử bản sao đã bị lấy |
| “Không ghi secret vào log” | Những điểm thu thập nào thuộc phạm vi, dữ liệu bị loại bỏ trước khi gửi đi và bằng chứng trên cả đường lỗi |
| “Có backup an toàn” | Quyền backup, quyền restore, bảo vệ khóa, retention và cách ngăn phục hồi credential đã bị thu hồi |
| “Dùng secret manager” | Workload nào được lấy hoặc dùng secret, kiểm tra tenant ở đâu, hành vi khi lỗi và cách audit quyền khẩn cấp |

Một đặc tả token storage hoàn chỉnh cho phạm vi đã chọn cần liên kết được **rủi ro → dạng lưu → chủ thể được phép sử dụng → vòng đời → hành vi khi lỗi → bằng chứng kiểm thử**. Khi các mắt xích này rõ ràng, nhóm triển khai mới có thể chứng minh rằng quyết định lưu trữ đáp ứng mục tiêu bảo mật của hệ thống.
