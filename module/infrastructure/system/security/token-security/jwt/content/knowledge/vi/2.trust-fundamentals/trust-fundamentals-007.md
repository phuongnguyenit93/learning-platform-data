# Mô hình đe dọa trước khi chọn loại JWT

JWT không tự động là lựa chọn an toàn nhất cho mọi hệ thống. Trước khi quyết định dùng JWT có chữ ký, JWT được mã hóa, access token dạng opaque hay một cơ chế phiên khác, cần hiểu **tài sản nào cần bảo vệ, ai có thể tấn công, dữ liệu đi qua những ranh giới nào và hệ thống phải đáp ứng yêu cầu bảo mật/vận hành gì**. Quá trình xác định những yếu tố đó được gọi là **mô hình hóa mối đe dọa (threat modeling)**.

Bài học thuộc chương **Nền tảng tin cậy** của module **Security – JSON Web Token (JWT)**. Phạm vi là bảo mật ứng dụng, API và hệ thống phân tán nói chung, không phụ thuộc ngôn ngữ lập trình hoặc framework. Mục tiêu là chọn cơ chế token theo mô hình đe dọa và yêu cầu thực tế, thay vì chọn JWT chỉ vì định dạng này phổ biến.

## 1. Mô hình hóa mối đe dọa là gì?

Threat modeling là cách phân tích có cấu trúc để nhận diện:

- **Tài sản (assets):** dữ liệu, danh tính, quyền, khóa, phiên và chức năng mà hệ thống cần bảo vệ.
- **Tác nhân (actors):** người dùng, ứng dụng, dịch vụ, quản trị viên và đối thủ tiềm năng.
- **Ranh giới tin cậy (trust boundaries):** nơi dữ liệu hoặc quyền đi qua một miền kiểm soát khác.
- **Luồng dữ liệu (data flows):** token được phát hành, lưu, truyền, xác minh, sử dụng, làm mới và thu hồi như thế nào.
- **Mối đe dọa (threats):** cách đối thủ có thể lấy, giả mạo, sửa, phát lại hoặc lạm dụng token.
- **Biện pháp kiểm soát (controls):** xác minh mật mã, phân quyền, giới hạn thời hạn, ràng buộc người gửi, giám sát và ứng phó.
- **Rủi ro còn lại (residual risk):** phần rủi ro vẫn tồn tại sau khi đã áp dụng biện pháp kiểm soát.

Threat modeling không phải là danh sách kiểm tra để chứng minh hệ thống tuyệt đối an toàn. Nó giúp nhóm phát triển và vận hành đưa ra quyết định có căn cứ, ghi nhận giả định và biết những rủi ro nào đang được chấp nhận.

### 1.1. Vì sao phải làm trước khi chọn JWT?

JWT có thể giải quyết một số vấn đề như mang claims giữa các dịch vụ và xác minh dữ liệu đã ký mà không cần truy vấn trạng thái ở mỗi request. Nhưng nó cũng có thể tạo thêm vấn đề:

- Payload JWS thường đọc được; thông tin nhạy cảm có thể bị lộ nếu đưa vào claims.
- JWT tự chứa có thể tiếp tục được chấp nhận đến khi hết hạn nếu resource server xác minh offline và không kiểm tra trạng thái thu hồi.
- Nhiều API cùng tin một issuer có thể vô tình chấp nhận token không dành cho mình nếu bỏ qua audience.
- Khóa ký, khóa HMAC, JWKS cache và quy trình rotation trở thành phần phải vận hành.
- Bearer JWT bị đánh cắp vẫn có thể bị sử dụng lại trong thời gian còn hiệu lực.
- Claims là ảnh chụp tại thời điểm phát hành; quyền và trạng thái tài khoản có thể thay đổi sau đó.

Nếu hệ thống cần thu hồi ngay, quyền thay đổi liên tục hoặc kiểm soát tập trung từng phiên, opaque token có introspection có thể phù hợp hơn. Nếu chỉ cần session cho một ứng dụng web, cookie phiên có thể đơn giản và dễ thu hồi hơn. Không cần chọn JWT nếu yêu cầu không đòi hỏi những đặc tính mà JWT mang lại.

## 2. Bắt đầu bằng việc xác định phạm vi và tài sản

Một mô hình đe dọa có phạm vi quá rộng thường khó sử dụng; phạm vi quá hẹp có thể bỏ sót ranh giới quan trọng. Hãy chọn một luồng cụ thể, ví dụ: người dùng đăng nhập, nhận access token và gọi API đọc dữ liệu.

### 2.1. Xác định tài sản cần bảo vệ

| Tài sản | Giá trị đối với hệ thống | Hậu quả khi bị xâm phạm |
| --- | --- | --- |
| Danh tính người dùng và workload | Xác định ai đang yêu cầu hành động | Giả mạo người dùng hoặc dịch vụ |
| Access token | Mang quyền truy cập API | Đọc/sửa dữ liệu hoặc thực hiện giao dịch trái phép |
| Refresh token và phiên đăng nhập | Duy trì khả năng cấp access token mới | Chiếm phiên lâu dài, kể cả sau khi access token cũ hết hạn |
| Khóa riêng ký JWT | Cho phép tạo chữ ký được resource server tin | Kẻ tấn công có thể giả mạo token của issuer |
| Khóa HMAC | Cho phép tạo và xác minh MAC | Mọi bên dùng chung khóa có thể bị ảnh hưởng |
| Khóa mã hóa JWE | Cho phép giải mã nội dung được bảo vệ | Lộ claims hoặc dữ liệu nhạy cảm |
| Claims và chính sách phân quyền | Quyết định quyền trên hành động/tài nguyên | Leo thang đặc quyền hoặc truy cập chéo tenant |
| Dữ liệu cá nhân và nghiệp vụ | Thông tin mà token cho phép truy cập | Rò rỉ, sửa đổi hoặc mất dữ liệu |
| Audit log và sự kiện bảo mật | Hỗ trợ phát hiện và điều tra | Không phát hiện được lạm dụng hoặc không thể xác định phạm vi sự cố |

Không chỉ token mới là tài sản. Khóa, metadata issuer, cấu hình audience, dữ liệu phân quyền và log cũng cần được bảo vệ.

### 2.2. Phân loại mức độ nhạy cảm

Hãy ghi nhận mức độ nhạy cảm của dữ liệu mà token có thể truy cập:

- **Công khai:** dữ liệu ai cũng có thể đọc; rủi ro bí mật thấp nhưng toàn vẹn vẫn quan trọng.
- **Nội bộ:** dữ liệu chỉ dành cho thành viên hoặc dịch vụ được phép.
- **Bảo mật:** dữ liệu cá nhân, thông tin khách hàng, tài chính hoặc thông tin kinh doanh.
- **Rất nhạy cảm:** thao tác chuyển tiền, quản trị, thay đổi quyền, khóa ký, thông tin xác thực hoặc dữ liệu có tác động lớn.

Mức độ nhạy cảm ảnh hưởng đến TTL, phạm vi scope, cách lưu token, yêu cầu thu hồi, giám sát và việc có cần sender-constrained token hay không.

## 3. Xác định tác nhân và năng lực của đối thủ

Không nên giả định mọi request độc hại đều đến từ Internet. Đối thủ có thể là người dùng bình thường cố vượt quyền, tài khoản bị chiếm, mã độc trên thiết bị, một workload bị xâm nhập hoặc người có quyền truy cập vào log.

| Tác nhân | Năng lực có thể có | Mối đe dọa liên quan |
| --- | --- | --- |
| Người dùng độc hại đã đăng nhập | Sửa request, thay ID tài nguyên, thử scope khác | IDOR/BOLA, leo thang quyền, truy cập chéo tenant |
| Kẻ tấn công ngoài hệ thống | Gửi request tùy ý, giả mạo token, dò endpoint | Token forgery, issuer confusion, khai thác parser |
| Mã độc/XSS trong browser | Đọc storage, thao tác trang, gửi request thay người dùng | Token theft, session hijacking |
| Người có quyền đọc log hoặc telemetry | Tìm token, cookie hoặc secret bị ghi nhầm | Credential theft và replay |
| Workload nội bộ bị xâm nhập | Gọi API nội bộ, đọc secret, giả mạo header | Lateral movement, confused deputy |
| Nhà cung cấp/issuer bên ngoài bị xâm nhập | Phát hành token hoặc thay đổi khóa/metadata | Token giả mạo trên phạm vi các bên tin issuer |
| Quản trị viên hoặc tài khoản vận hành bị chiếm | Thay cấu hình issuer, JWKS, quyền và secret | Thay nguồn tin cậy, đánh cắp khóa, cấp quyền trái phép |

Mô hình đe dọa cần nêu rõ giả định. Ví dụ: “Kẻ tấn công có thể lấy bản sao access token từ browser nhưng không kiểm soát khóa riêng DPoP” là giả định khác với “Kẻ tấn công kiểm soát hoàn toàn thiết bị và có thể yêu cầu client ký proof”.

### 3.1. Không đánh đồng các mức kiểm soát thiết bị

- **Chỉ lấy được token:** sender constraint có thể làm bản sao token đơn lẻ khó sử dụng.
- **Đọc được JavaScript storage:** token có thể bị gửi ra ngoài; BFF có thể giảm việc token xuất hiện ở browser.
- **Thực thi XSS trong origin:** mã độc có thể thao tác phiên và gửi request thay người dùng, kể cả khi cookie là HttpOnly.
- **Kiểm soát thiết bị:** có thể lấy dữ liệu trong bộ nhớ, thao tác ứng dụng hoặc sử dụng khóa mà thiết bị được phép truy cập.
- **Chiếm backend hoặc issuer:** có thể ảnh hưởng đến token, khóa và dữ liệu ở phạm vi lớn hơn; biện pháp phía client không đủ.

Biện pháp bảo vệ phải phù hợp với năng lực đối thủ được đưa vào mô hình, không chỉ với kịch bản dễ nhất.

## 4. Vẽ luồng dữ liệu và ranh giới tin cậy

Trước khi chọn token, hãy vẽ luồng từ lúc xác thực đến lúc API ra quyết định. Ví dụ:

~~~mermaid
flowchart LR
    U["Người dùng"] --> B["Browser / Mobile client"]
    B -->|"Đăng nhập"| I["Identity / Authorization Server"]
    I -->|"Access token"| B
    B -->|"Bearer token"| G["API Gateway"]
    G --> A["Resource API"]
    A --> D["Database / tài nguyên"]
    I -->|"JWKS / metadata"| A
    A --> L["Audit / telemetry"]
~~~

Các ranh giới đáng chú ý:

1. Thiết bị người dùng → ứng dụng client.
2. Client → authorization server.
3. Authorization server → client khi trả token.
4. Client → gateway hoặc resource server khi gửi token.
5. Gateway → service nội bộ.
6. Resource server → kho dữ liệu và dịch vụ phụ trợ.
7. Issuer → resource server khi phân phối metadata/JWKS.
8. Ứng dụng → hệ thống log, tracing và giám sát.

Ở mỗi ranh giới, hãy hỏi: dữ liệu nào đi qua, bên nhận có xác minh nguồn không, token có bị lộ không, quyền có được giới hạn không, và nếu bên gửi bị xâm nhập thì hậu quả lan tới đâu?

### 4.1. Luồng vòng đời token

~~~mermaid
flowchart TD
    A["Xác thực / cấp quyền"] --> B["Phát hành token"]
    B --> C["Lưu token ở client hoặc BFF"]
    C --> D["Gửi token tới API"]
    D --> E["Xác minh token và audience"]
    E --> F["Đánh giá scope và quyền tài nguyên"]
    F --> G["Thực thi request"]
    C --> H["Refresh / đổi token"]
    H --> B
    B --> I["Hết hạn / thu hồi / rotation"]
    I --> J["Từ chối token cũ"]
~~~

Threat modeling phải xem toàn bộ vòng đời, không chỉ thời điểm API kiểm tra chữ ký. Token có thể bị lộ lúc phát hành, lưu trữ, refresh, truyền, ghi log, cache hoặc thu hồi.

## 5. Nhận diện mối đe dọa bằng STRIDE

STRIDE là một cách phân loại mối đe dọa thường dùng trong threat modeling. Sáu nhóm giúp nhóm phát triển đặt câu hỏi có hệ thống; với hệ thống token, cần bổ sung phân tích replay và chiếm đoạt credential vì chúng thường xuất hiện xuyên nhiều nhóm.

| Nhóm | Ý nghĩa | Ví dụ trong hệ thống JWT | Biện pháp có thể cân nhắc |
| --- | --- | --- | --- |
| **S — Spoofing** | Giả mạo danh tính | Token tự tạo, issuer giả, giả mạo workload hoặc header user | Xác minh chữ ký, issuer, workload identity, nguồn khóa và ranh giới header |
| **T — Tampering** | Sửa đổi dữ liệu | Sửa role, scope, audience hoặc claims | Chữ ký/MAC được xác minh đúng, kiểm soát dữ liệu sau xác minh |
| **R — Repudiation** | Chối bỏ hành động hoặc thiếu bằng chứng | Không biết token/subject nào thực hiện thao tác nhạy cảm | Audit log có correlation ID, subject/issuer đã xác minh, thời điểm và quyết định |
| **I — Information Disclosure** | Lộ thông tin | Payload JWS chứa dữ liệu cá nhân; token bị ghi vào log | Claims tối thiểu, JWE khi cần, redaction, kiểm soát log và TLS |
| **D — Denial of Service** | Từ chối dịch vụ | Request làm parser/JWKS fetch tốn tài nguyên; refresh storm | Giới hạn kích thước, timeout, rate limit, cache có kiểm soát, thuật toán được allowlist |
| **E — Elevation of Privilege** | Leo thang đặc quyền | Chấp nhận sai audience, scope rộng, nhầm tenant hoặc token loại khác | Kiểm tra audience, scope, tenant, loại token và quyền trên tài nguyên |

### 5.1. Các mối đe dọa xuyên suốt

**Token theft:** lấy bản sao token từ storage, memory, log, clipboard, extension hoặc thiết bị bị xâm nhập.

**Replay:** dùng lại token hoặc proof hợp lệ. Claim jti tự nó không chặn replay nếu không có trạng thái hoặc giao thức kiểm tra việc sử dụng.

**Token substitution:** thay token loại này bằng token loại khác, ví dụ dùng ID token thay access token hoặc token dành cho API A ở API B.

**Issuer/key confusion:** khiến resource server xác minh bằng khóa của issuer khác, khóa do token chỉ định hoặc thuật toán không phù hợp.

**Confused deputy:** một service có quyền rộng bị lừa dùng quyền của chính nó để thực hiện hành động mà caller không được phép.

**Stale authorization:** token chứa quyền hợp lệ lúc phát hành nhưng quyền/tài khoản/tenant đã thay đổi trước khi token hết hạn.

**Privacy correlation:** subject hoặc claims ổn định bị dùng để liên kết hoạt động người dùng qua nhiều ứng dụng, dù việc liên kết đó không cần thiết.

## 6. Đánh giá rủi ro và ưu tiên xử lý

Không phải mọi mối đe dọa đều có cùng mức nghiêm trọng. Một cách đánh giá thực dụng là xem xét:

- **Khả năng xảy ra (likelihood):** đối thủ có thể khai thác dễ đến đâu, cần quyền gì, có cần xâm nhập trước không?
- **Tác động (impact):** dữ liệu nào bị lộ, hành động nào bị thực hiện, số người dùng/tenant/service bị ảnh hưởng?
- **Khả năng phát hiện:** hệ thống có log và tín hiệu để nhận biết sớm không?
- **Khả năng khôi phục:** có thể thu hồi token, vô hiệu hóa client, đổi khóa hoặc phục hồi dữ liệu trong thời gian chấp nhận được không?

Ví dụ ma trận đơn giản:

| Khả năng | Tác động | Ưu tiên gợi ý |
| --- | --- | --- |
| Cao | Cao | Xử lý trước khi triển khai hoặc trước khi mở rộng phạm vi |
| Cao | Thấp | Giảm bề mặt tấn công và giám sát |
| Thấp | Cao | Thiết kế biện pháp giảm thiểu và quy trình ứng phó rõ ràng |
| Thấp | Thấp | Ghi nhận, theo dõi và xem xét lại khi bối cảnh thay đổi |

Không dùng ma trận này như công thức định lượng tuyệt đối. Hãy ghi lại lý do xếp hạng, giả định và người chịu trách nhiệm chấp nhận rủi ro còn lại.

### 6.1. Ví dụ risk register cho access token

| Mối đe dọa | Tài sản | Khả năng | Tác động | Kiểm soát | Rủi ro còn lại |
| --- | --- | --- | --- | --- | --- |
| XSS lấy token từ browser | Access token, dữ liệu người dùng | Trung bình | Cao | BFF, CSP, output encoding, TTL ngắn | XSS vẫn có thể thao tác phiên |
| Token bị ghi vào log | Access/refresh token | Trung bình | Cao | Redact header/cookie, giới hạn quyền log, thu hồi | Bản sao log cũ có thể còn tồn tại |
| API nhận token sai audience | Dữ liệu của API | Thấp nếu kiểm tra đầy đủ | Cao | Audience riêng, validation tại resource server | Lỗi cấu hình hoặc profile không đồng nhất |
| Khóa ký bị lộ | Niềm tin vào issuer | Thấp | Rất cao | HSM/KMS, phân quyền, audit, rotation | Kẻ tấn công có thể giả mạo token trước khi khóa bị vô hiệu |
| Quyền bị thu hồi nhưng JWT vẫn còn hạn | Tài nguyên nhạy cảm | Tùy TTL và chính sách | Cao | TTL, introspection, denylist, trạng thái trung tâm | Độ trễ đồng bộ hoặc cache |
| Replay bearer token | Phiên và tài nguyên | Trung bình | Cao | TTL, DPoP/mTLS, phát hiện bất thường | Endpoint bị chiếm quyền vẫn có thể dùng token/proof |

## 7. Chuyển yêu cầu bảo mật thành tiêu chí chọn token

Sau khi xác định tài sản, đối thủ và rủi ro, hãy viết các yêu cầu có thể kiểm chứng. Tránh yêu cầu mơ hồ như “token phải an toàn” hoặc “phải dùng JWT”.

Ví dụ yêu cầu tốt:

- API phải xác minh token được phát hành bởi một trong các issuer đã đăng ký.
- Token chỉ được chấp nhận ở resource server có audience phù hợp.
- Access token có quyền tối thiểu và thời hạn không vượt quá giới hạn đã chọn.
- Quyền bị thu hồi phải có hiệu lực trong một khoảng thời gian xác định.
- Payload không được để lộ thông tin cá nhân cho bên cầm token không có quyền giải mã.
- Token bị sao chép đơn lẻ không đủ để gọi API đối với một nhóm endpoint có rủi ro cao.
- Mọi thao tác nhạy cảm phải có audit event liên kết với subject, issuer, client và request ID.
- Không có access token, refresh token hoặc khóa riêng trong log, URL, frontend bundle hay repository.

### 7.1. Các yêu cầu quyết định kiến trúc

| Câu hỏi | Nếu câu trả lời là “có” | Hướng thiết kế cần xem xét |
| --- | --- | --- |
| Nhiều resource server cần xác minh độc lập mà không gọi issuer mỗi request? | Cần xác minh phân tán/offline | JWT/JWS có thể phù hợp; quản lý khóa và rotation là bắt buộc |
| Cần thu hồi token hoặc cập nhật quyền gần thời gian thực? | Trạng thái hiện tại rất quan trọng | Opaque token + introspection, hoặc JWT kết hợp denylist/introspection/trạng thái trung tâm |
| Payload chứa dữ liệu cần giữ bí mật khỏi người cầm token? | Cần confidentiality ở tầng token | JWE hoặc không đưa dữ liệu đó vào token; JWE vẫn cần kiểm tra issuer riêng khi cần |
| API chỉ cần xác minh chữ ký và không được phép phát hành token? | Cần tách quyền ký/xác minh | Chữ ký bất đối xứng thường phù hợp hơn HMAC dùng chung |
| Chỉ có một miền tin cậy nhỏ và mọi bên giữ khóa đều được phép tạo MAC? | Chấp nhận shared-secret trust | HS256 có thể phù hợp nếu khóa được bảo vệ và phân phối đúng |
| Token bị sao chép đơn lẻ không được đủ để gọi endpoint? | Cần proof of possession | DPoP hoặc mTLS-bound access token theo môi trường |
| Quyền thay đổi theo từng tài nguyên hoặc quan hệ? | Claims không đủ để quyết định | Kiểm tra chính sách và quyền tài nguyên tại API |
| Ứng dụng chỉ cần duy trì phiên đăng nhập nội bộ? | Không cần claims tự chứa giữa nhiều service | Cookie phiên và session store có thể đơn giản hơn JWT |

## 8. Chọn giữa opaque token, JWS, JWE và các mô hình khác

“Loại JWT” thực tế bao gồm nhiều quyết định: token có cấu trúc hay opaque, được ký hay mã hóa, dùng khóa đối xứng hay bất đối xứng, bearer hay sender-constrained, và kiểm tra trạng thái offline hay online.

### 8.1. Opaque token và JWT tự chứa

| Tiêu chí | Opaque/reference token | JWT tự chứa |
| --- | --- | --- |
| Nội dung phía client | Chuỗi không cần hiểu cấu trúc | Thường có header/payload có thể đọc nếu là JWS |
| Xác minh tại API | Introspection hoặc tra cứu trạng thái theo thiết kế | Có thể xác minh chữ ký và claims offline |
| Thu hồi | Có thể cập nhật trạng thái tập trung và phản ánh ở lần introspection tiếp theo | Cần denylist, introspection hoặc chờ hết hạn nếu xác minh offline |
| Phụ thuộc mạng khi xác minh | Thường cần kết nối tới dịch vụ trạng thái hoặc cache | Có thể giảm phụ thuộc issuer khi xác minh offline |
| Quyền và claims mới nhất | Có thể lấy từ trạng thái hiện hành | Claims phản ánh thời điểm phát hành, có thể cũ |
| Vận hành | Cần tính sẵn sàng, tải và cache của introspection | Cần quản lý khóa, JWKS, rotation, TTL và chính sách claims |
| Riêng tư | Không lộ claims trực tiếp qua chuỗi token | JWS thường để lộ payload; JWE mới mã hóa nội dung |

Opaque token không tự động an toàn hơn JWT và JWT không tự động mở rộng quy mô tốt hơn. Lựa chọn phụ thuộc vào yêu cầu trạng thái, độ trễ, sẵn sàng, quyền riêng tư và năng lực vận hành.

### 8.2. JWS hay JWE?

| Nhu cầu | Cơ chế cần xem xét | Điều cần nhớ |
| --- | --- | --- |
| Chống sửa claims và xác minh issuer | JWS chữ ký số hoặc MAC | Payload JWS thường đọc được |
| Chỉ cần toàn vẹn/xác thực trong nhóm dùng chung bí mật | JWS với HMAC | Mọi bên có secret đều có thể tạo MAC |
| Giữ claims bí mật với người không có khóa giải mã | JWE | Giải mã thành công không tự chứng minh issuer |
| Vừa xác thực issuer vừa giữ payload bí mật | JWS lồng trong JWE theo hồ sơ phù hợp | Phải xác minh đầy đủ từng lớp theo đúng thứ tự |
| Không cần mang claims tự chứa hoặc chia sẻ giữa nhiều bên | Cân nhắc opaque token/session | Có thể giảm việc công bố claims và đơn giản hóa thu hồi |

### 8.3. Bearer hay sender-constrained?

Bearer token phù hợp khi mô hình đe dọa chấp nhận rủi ro token bị sao chép trong một cửa sổ ngắn và các kiểm soát lưu trữ/thu hồi đủ đáp ứng. Với dữ liệu hoặc thao tác có tác động lớn, có thể cân nhắc:

- **DPoP:** ràng buộc token với khóa của client và proof theo request.
- **mTLS-bound token:** ràng buộc token với chứng chỉ client trong kết nối TLS.

Sender constraint không thay thế bảo vệ endpoint. Nếu mã độc có thể sử dụng khóa tại thiết bị, nó có thể tạo proof hợp lệ thay client.

## 9. Các ví dụ kiến trúc theo mô hình đe dọa

### Tình huống A — Một backend và một API, quyền cần thu hồi nhanh

Một ứng dụng nội bộ có backend và một API. Quyền nhân viên thay đổi thường xuyên, phiên cần bị vô hiệu hóa ngay khi tài khoản bị khóa. Backend có thể sử dụng cookie session hoặc opaque access token với introspection/trạng thái tập trung.

**Lý do:** trạng thái hiện hành và thu hồi nhanh quan trọng hơn khả năng xác minh offline. JWT vẫn có thể dùng, nhưng phải bổ sung cơ chế kiểm tra trạng thái nếu yêu cầu không cho phép cửa sổ hiệu lực đến khi token hết hạn.

### Tình huống B — Một issuer, nhiều API độc lập

Một Identity Provider phát hành token cho nhiều resource server do các nhóm khác nhau vận hành. Các API cần xác minh token cục bộ để giảm độ trễ và phụ thuộc mạng.

**Lý do:** JWT/JWS dùng chữ ký bất đối xứng có thể phù hợp. Issuer giữ private key; API giữ public key qua JWKS tin cậy. Mỗi API phải kiểm tra issuer, audience, loại token, thời hạn và quyền.

### Tình huống C — Token chứa dữ liệu nhạy cảm

Một hệ thống muốn gửi claims nhạy cảm qua nhiều thành phần, trong đó một số thành phần không được phép đọc nội dung.

**Lý do:** trước tiên xem có thể bỏ claims nhạy cảm khỏi token và tra cứu qua API hay không. Nếu cần mã hóa ở tầng token, cân nhắc JWE cho đúng người nhận; nếu cần xác thực độc lập issuer, dùng chữ ký phù hợp bên trong và kiểm tra đầy đủ.

### Tình huống D — API tài chính có nguy cơ token bị sao chép

Một API cho phép tạo lệnh thanh toán. Thiệt hại khi bearer token bị đánh cắp là cao; thiết bị client có khả năng giữ khóa an toàn theo mô hình triển khai.

**Lý do:** cân nhắc DPoP hoặc mTLS-bound token, access token TTL ngắn, scope hẹp, xác nhận giao dịch theo ngữ cảnh, kiểm tra quyền và giám sát bất thường. Không xem sender constraint là biện pháp duy nhất.

### Tình huống E — Hệ thống nhiều tenant với nhiều IdP

Một SaaS chấp nhận token từ các issuer khác nhau. Mỗi tenant có chính sách và khóa riêng.

**Lý do:** cần registry issuer được quản trị, ánh xạ danh tính theo cặp issuer/subject, JWKS cache tách biệt và kiểm tra audience. Không tải metadata từ URL issuer tùy ý trong token.

## 10. Quy trình threat modeling thực hành

Có thể áp dụng quy trình sau cho một tính năng mới hoặc khi thay đổi cách xác thực:

1. **Chốt phạm vi:** chọn endpoint, người dùng, service, dữ liệu và môi trường cần phân tích.
2. **Liệt kê tài sản:** token, refresh token, khóa, claims, dữ liệu, phiên và log.
3. **Vẽ sơ đồ luồng dữ liệu:** đánh dấu browser, IdP, BFF, gateway, resource server, kho dữ liệu và bên thứ ba.
4. **Đánh dấu ranh giới tin cậy:** nơi credential, dữ liệu hoặc quyền đi qua.
5. **Xác định đối thủ và giả định:** năng lực truy cập, quyền, thiết bị, mạng và hệ thống mà đối thủ có thể kiểm soát.
6. **Liệt kê threat:** dùng STRIDE và các mối đe dọa token như theft, replay, substitution, issuer confusion và stale authorization.
7. **Đánh giá rủi ro:** xem khả năng, tác động, khả năng phát hiện và khôi phục.
8. **Đặt yêu cầu bảo mật:** issuer, audience, scope, TTL, privacy, revocation, sender constraint, audit.
9. **So sánh phương án:** opaque, JWS, JWE, nested JWT, cookie session và introspection.
10. **Chọn biện pháp và ghi trade-off:** ai vận hành khóa, JWKS, introspection, denylist, cache, rotation và incident response?
11. **Xác định kiểm thử:** mỗi threat quan trọng phải có tình huống kiểm thử hoặc bằng chứng kiểm soát.
12. **Rà soát lại khi bối cảnh thay đổi:** thêm API, tenant, issuer, dữ liệu nhạy cảm hoặc luồng refresh mới có thể làm mô hình cũ không còn đúng.

### 10.1. Mẫu ghi nhận threat model

| Trường | Nội dung cần điền |
| --- | --- |
| Tính năng / luồng | Ví dụ: browser gọi Billing API để đọc hóa đơn |
| Tài sản | Access token, dữ liệu hóa đơn, khóa xác minh, audit log |
| Tác nhân | Người dùng độc hại, XSS, kẻ lấy token từ log |
| Ranh giới | Browser–API, issuer–API, API–database |
| Giả định | TLS hoạt động; issuer đã đăng ký; browser có thể bị XSS |
| Threat | Token theft, replay, sai audience, truy cập chéo tenant |
| Tác động | Lộ hóa đơn, sửa dữ liệu, giả mạo request |
| Kiểm soát | BFF, audience riêng, scope tối thiểu, resource authorization, TTL |
| Rủi ro còn lại | XSS vẫn có thể gửi request qua phiên đang hoạt động |
| Kiểm thử | Token sai audience, token hết hạn, token bị thu hồi, user truy cập tenant khác |
| Chủ sở hữu / quyết định | Nhóm chịu trách nhiệm và người chấp nhận rủi ro |

Mẫu này có thể được lưu cùng tài liệu thiết kế để quyết định về token có thể được xem lại khi hệ thống thay đổi.

## 11. Kiểm thử dựa trên mối đe dọa

Threat model chỉ hữu ích khi các biện pháp kiểm soát có thể được kiểm tra. Các bài kiểm thử nên mô phỏng cả token hợp lệ và token sai ngữ cảnh.

| Kịch bản kiểm thử | Kết quả mong đợi |
| --- | --- |
| Token có chữ ký sai hoặc bị sửa claims | Bị từ chối |
| Token từ issuer không nằm trong allowlist | Bị từ chối |
| Token đúng issuer nhưng sai audience | Bị từ chối |
| ID token được gửi tới resource server yêu cầu access token | Bị từ chối |
| Token hết hạn hoặc chưa tới thời điểm hiệu lực | Bị từ chối |
| Token thiếu scope cần thiết | Bị từ chối |
| Token đủ scope nhưng subject không sở hữu tài nguyên | Bị từ chối |
| Token có issuer/URL khóa do đối thủ kiểm soát | Không thực hiện fetch tùy ý; bị từ chối |
| JWKS không truy cập được hoặc kid không tồn tại | Xử lý theo fail-closed policy, không bỏ qua xác minh |
| Token bị đưa vào log | Log phải che/loại bỏ giá trị token |
| Refresh token cũ được dùng lại sau rotation | Phát hiện và xử lý theo chính sách |
| Bearer token bị sao chép | Cửa sổ khai thác được giới hạn; sender constraint được kiểm tra nếu áp dụng |
| Quyền bị thu hồi khi JWT chưa hết hạn | Hiệu lực thu hồi đáp ứng SLA đã định nghĩa |

Với mỗi kịch bản, hãy kiểm tra cả kết quả HTTP, audit event và việc hệ thống không làm lộ thêm dữ liệu nhạy cảm trong thông báo lỗi.

## 12. Những sai lầm khi chọn JWT mà không threat model

### Sai lầm A — Dùng JWT vì nghĩ stateless luôn tốt hơn

JWT có thể xác minh offline, nhưng hệ thống vẫn cần quản lý khóa, rotation, JWKS, TTL, thu hồi và claims cũ. Nếu yêu cầu thu hồi tức thời, opaque token với introspection có thể giảm độ phức tạp ở phía resource server.

### Sai lầm B — Đưa mọi thông tin người dùng vào payload

JWS không che giấu payload. Claims có thể bị đọc bởi người cầm token, proxy, log hoặc hệ thống trung gian. Chỉ đưa thông tin cần thiết và không dùng token như kho dữ liệu cá nhân.

### Sai lầm C — Chỉ kiểm tra chữ ký

Chữ ký đúng không xác minh audience, loại token, thời hạn, scope, tenant hoặc quyền trên tài nguyên. Phải kiểm tra toàn bộ profile và chính sách cần thiết.

### Sai lầm D — Dùng một token cho mọi API

Audience và scope quá rộng làm tăng phạm vi thiệt hại nếu token bị lộ. Cấp token theo resource server và tác vụ.

### Sai lầm E — Tin rằng JWT không cần trạng thái

Nếu cần thu hồi token, phát hiện replay, giới hạn phiên đồng thời hoặc phản ánh quyền mới ngay, hệ thống vẫn cần trạng thái tập trung hoặc cơ chế tương đương.

### Sai lầm F — Nghĩ mã hóa giải quyết mọi vấn đề

JWE bảo vệ bí mật payload và cơ chế xác thực mật mã theo cấu hình, nhưng không tự chứng minh issuer, không quyết định quyền và không ngăn bearer token bị phát lại.

### Sai lầm G — Bỏ qua vận hành khóa

Chọn RS256 nhưng không có kế hoạch bảo vệ private key, công bố JWKS, cache, rotation và xử lý key compromise sẽ tạo ra rủi ro vận hành nghiêm trọng.

### Sai lầm H — Chỉ threat model ở thời điểm đăng nhập

Token còn đi qua refresh, API gateway, service-to-service, log, queue và các hệ thống quan sát. Mô hình phải bao phủ toàn bộ vòng đời.

## 13. Ghi nhớ

- Threat modeling bắt đầu từ **tài sản, đối thủ, ranh giới tin cậy và luồng dữ liệu**, không bắt đầu từ câu hỏi “dùng thuật toán JWT nào?”.
- Xác định rõ yêu cầu về toàn vẹn, xác thực nguồn, bí mật, thu hồi, replay, quyền riêng tư và tính sẵn sàng.
- JWT/JWS phù hợp khi cần claims tự chứa và xác minh phân tán; phải chấp nhận và quản lý khóa, claims cũ, TTL và thu hồi.
- Opaque token/introspection hoặc session có thể phù hợp hơn khi cần trạng thái hiện hành, thu hồi nhanh và không cần claims tự chứa.
- JWE chỉ cần khi có yêu cầu giữ bí mật payload; chữ ký vẫn cần nếu phải xác thực issuer độc lập.
- Bearer token dễ sử dụng nhưng có rủi ro replay khi bị lộ; cân nhắc DPoP/mTLS cho luồng rủi ro cao.
- Mọi phương án đều cần kiểm tra issuer, audience, loại token, scope, quyền tài nguyên và có kế hoạch ứng phó sự cố.
- Ghi lại trade-off, giả định, rủi ro còn lại và kiểm thử tương ứng; cập nhật threat model khi kiến trúc thay đổi.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [OWASP Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html)
