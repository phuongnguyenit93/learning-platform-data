Một ứng dụng muốn truy cập lịch của người dùng trên dịch vụ khác sau khi được người dùng cho phép. OAuth 2.0 chủ yếu giải quyết vấn đề nào?
A. Cấp quyền truy cập giới hạn tới tài nguyên thay mặt resource owner.
B. Xác minh danh tính người dùng và thiết lập phiên đăng nhập cho client.
C. Bảo vệ bí mật ứng dụng bằng cách mã hóa request gửi tới resource server.
D. Định nghĩa cấu trúc claim chuẩn để chia sẻ hồ sơ người dùng giữa các client.
Đáp án đúng: A

Một ứng dụng cần biết người dùng vừa đăng nhập là ai, ngoài việc xin quyền gọi API. Lớp giao thức nào bổ sung chức năng xác thực trên OAuth 2.0?
A. OAuth 2.0 tự xác thực người dùng khi request có scope openid.
B. JWT access token thay thế ID token để client nhận diện người đăng nhập.
C. OpenID Connect bổ sung lớp xác thực và ID token cho client.
D. UserInfo endpoint thay thế bước xác minh ID token trong mọi OIDC flow.
Đáp án đúng: C

Trong authorization code flow, resource owner, client và authorization server có quan hệ nào?
A. Resource server nhận authorization request và phát code cho client sau khi xác thực.
B. Client xác thực resource owner bằng mật khẩu rồi gửi credential tới authorization server.
C. Client yêu cầu quyền thay resource owner và nhận code từ authorization server.
D. Authorization server trả access token qua redirect thay cho authorization code.
Đáp án đúng: C

Một web client dùng authorization code flow. Trình tự nào mô tả đúng luồng trao đổi cơ bản?
A. Client chuyển hướng người dùng, nhận code tại redirect URI rồi đổi code lấy token.
B. Client nhận code tại token endpoint rồi gửi code về redirect URI để đổi token.
C. Client gửi authorization code tới authorization endpoint để nhận access token.
D. Authorization server chuyển access token qua redirect URI để client đổi lấy code.
Đáp án đúng: A

Một ứng dụng mobile là public client và authorization code có thể bị chặn trên redirect. PKCE giúp bảo vệ bước nào?
A. Ràng buộc ID token với nonce để phát hiện phản hồi đăng nhập bị phát lại.
B. Xác thực client bằng shared secret khi gửi code tới token endpoint.
C. Ràng buộc việc đổi authorization code với verifier do client ban đầu giữ.
D. Kiểm tra chữ ký ID token để bảo đảm authorization code chưa bị sửa.
Đáp án đúng: C

Trong PKCE với phương thức S256, client tạo code challenge theo cách nào?
A. Tạo challenge ngẫu nhiên rồi gửi SHA-256(challenge) làm verifier khi đổi code.
B. Dùng SHA-256(verifier) trực tiếp làm challenge mà không Base64URL encode.
C. Tạo verifier từ authorization code rồi gửi hash của code làm challenge.
D. Tạo verifier ngẫu nhiên rồi gửi Base64URL(SHA-256(verifier)) làm challenge.
Đáp án đúng: D

Một ứng dụng dùng redirect về callback sau khi người dùng đăng nhập. Tham số state nên được dùng như thế nào?
A. Sinh giá trị khó đoán, lưu theo phiên và so khớp tại callback để chống CSRF.
B. Dùng state cố định để authorization server nhận biết client qua các phiên.
C. Dùng nonce để liên kết callback OAuth, còn state để ràng buộc ID token.
D. Đưa redirect URI vào state để authorization server tự xác minh callback.
Đáp án đúng: A

Một client OIDC muốn ràng buộc ID token nhận được với yêu cầu đăng nhập ban đầu. Claim nào hỗ trợ mục đích này?
A. State được gửi trong authorization request và phải khớp claim trong ID token.
B. Nonce được dùng làm access token tạm thời để API nhận diện phiên.
C. Nonce được gửi trong authentication request và phải khớp claim trong ID token.
D. PKCE verifier được gửi trong ID token để xác minh yêu cầu đăng nhập.
Đáp án đúng: C

Một authorization server cho phép redirect URI theo prefix, ví dụ mọi địa chỉ bắt đầu bằng https://app.example. Rủi ro chính của cách kiểm tra này là gì?
A. Attacker có thể lợi dụng URI ngoài ý muốn để nhận authorization response.
B. Access token được cấp scope rộng hơn vì redirect URI có nhiều path prefix.
C. Authorization server sẽ phát hành token với audience của subdomain thay vì client.
D. Client không cần xác minh state vì redirect URI đã được kiểm tra theo prefix.
Đáp án đúng: A

Một client dùng redirect URI trỏ tới endpoint có open redirect. Tác động nào cần được xem xét trong OAuth flow?
A. Open redirect khiến authorization server tự chấp nhận callback chưa đăng ký.
B. Authorization response có thể bị chuyển tiếp tới đích do attacker kiểm soát.
C. Authorization server có thể chấp nhận URI không thuộc danh sách callback đã đăng ký.
D. PKCE verifier có thể bị lộ nếu client đưa verifier vào URL redirect.
Đáp án đúng: B

Một ứng dụng native được phân loại là public client. Điều gì đúng về client secret được nhúng trong binary?
A. Binary được ký số nên secret nhúng bên trong được bảo vệ khỏi việc trích xuất.
B. Secret dùng chung có thể giữ kín nếu ứng dụng được obfuscate và rotate thường xuyên.
C. Secret trong ứng dụng phân phối cho người dùng không thể được giữ bí mật đáng tin cậy.
D. Secret chỉ lộ khi người dùng có quyền root hoặc jailbreak thiết bị.
Đáp án đúng: C

Một ứng dụng mobile cần đăng nhập bằng authorization code flow. Cách mở trang xác thực nào được khuyến nghị?
A. Dùng embedded user-agent để client giữ session cookie và kiểm soát điều hướng.
B. Dùng external user-agent như trình duyệt hệ thống và redirect đã đăng ký.
C. Dùng webview nhúng để ứng dụng quan sát form đăng nhập và xử lý MFA.
D. Mở form đăng nhập trong webview để ứng dụng quản lý cookie của authorization server.
Đáp án đúng: B

Một SPA chạy hoàn toàn trong trình duyệt cần OAuth 2.0. Cấu hình client nào phù hợp với môi trường public?
A. Dùng authorization code với PKCE và không dựa vào client secret nhúng trong mã.
B. Dùng implicit flow và lưu access token lâu dài trong URL fragment của trang.
C. Dùng client credentials flow với secret được đóng gói trong JavaScript bundle.
D. Dùng resource owner password credentials để trình duyệt gửi mật khẩu cho client.
Đáp án đúng: A

Một ứng dụng web dùng Backend-for-Frontend để giảm lộ token cho trình duyệt. Token nên được quản lý thế nào?
A. BFF giữ token phía server và trình duyệt dùng session cookie được bảo vệ.
B. BFF trả access token cho JavaScript nhưng giữ refresh token ở server.
C. BFF mã hóa token rồi trả về browser để JavaScript tự gắn vào request API.
D. BFF proxy request nhưng đính kèm access token vào URL khi gọi API downstream.
Đáp án đúng: A

Một client yêu cầu scope calendar.read và calendar.write. Scope trong OAuth 2.0 thể hiện điều gì?
A. Danh sách thuộc tính hồ sơ người dùng được authorization server xác minh.
B. Định danh client và loại ứng dụng đang xin quyền truy cập.
C. Audience hoặc resource server mà access token được phát hành để gửi tới.
D. Phạm vi quyền mà client yêu cầu hoặc được cấp trên tài nguyên.
Đáp án đúng: D

Một access token được cấp cho API lịch nhưng bị gửi nhầm tới API thanh toán. Claim hoặc thuộc tính nào giúp API xác định token có dành cho mình?
A. Nonce xác định người dùng đã đăng nhập vào client nào trong phiên trước.
B. Audience xác định resource server hoặc nhóm người nhận dự kiến của token.
C. State xác định redirect URI đã được người dùng chấp thuận trong consent.
D. Azp xác định scope mà mọi resource server trong hệ thống đều phải chấp nhận.
Đáp án đúng: B

Một API nhận access token từ authorization server. Nhận định nào đúng về định dạng access token?
A. Access token luôn là JWT và mọi API có thể giải mã payload để tin các claim.
B. Access token có thể opaque hoặc self-contained; API phải theo cơ chế phát hành đã thống nhất.
C. Access token luôn opaque nên API bắt buộc gọi introspection trong mọi cấu hình.
D. Access token luôn là JWT và không cần kiểm tra issuer nếu client đã xác minh.
Đáp án đúng: B

Một API nhận ID token từ ứng dụng web và định dùng nó làm bearer token để đọc dữ liệu. Vì sao cách này sai?
A. ID token mang danh tính đã xác thực nên API có thể dùng làm bearer token nếu có chữ ký.
B. ID token có audience là client, nhưng resource server vẫn có thể chấp nhận nếu chữ ký hợp lệ.
C. ID token dành cho client xác nhận đăng nhập, không phải quyền truy cập API.
D. ID token có thể thay access token khi scope được ghi trong claim của token.
Đáp án đúng: C

Một resource server tự xác minh JWT access token. Tập kiểm tra nào cần được thực hiện?
A. Chỉ giải mã payload, kiểm tra subject tồn tại và tin các claim còn lại.
B. Xác minh chữ ký, thuật toán cho phép, issuer, audience và thời hạn token.
C. Kiểm tra client ID trong query, rồi chấp nhận token nếu chữ ký có mặt.
D. Chỉ kiểm tra issuer và thời hạn vì audience được client tự lựa chọn.
Đáp án đúng: B

Một JWT hợp lệ về chữ ký nhưng có claim aud trỏ tới một API khác. Resource server hiện tại nên xử lý thế nào?
A. Chấp nhận token nếu scope phù hợp dù aud trỏ tới API khác.
B. Chấp nhận token nếu issuer và chữ ký hợp lệ vì aud chỉ dành cho client.
C. Chuyển token tới API có audience phù hợp rồi dùng kết quả thay thế.
D. Từ chối token vì audience không bao gồm resource server hiện tại.
Đáp án đúng: D

Một issuer xoay khóa ký JWT và JWKS hiện có key mới với kid khác. Resource server nên xử lý key selection thế nào?
A. Tin jku hoặc x5u trong token header để tải khóa từ URL do token chỉ định.
B. Dùng khóa đã cache bất kể kid rồi chỉ kiểm tra chữ ký có hợp lệ.
C. Lấy khóa từ JWKS của issuer tin cậy, chọn theo kid và refresh khi cần.
D. Chọn khóa chỉ theo thuật toán, không ràng buộc với issuer và kid.
Đáp án đúng: C

Một authorization server phát hành opaque access token. API cần kiểm tra trạng thái token và metadata quyền hiện tại. Cơ chế nào phù hợp?
A. Giải mã opaque token bằng Base64 để đọc claim mà không cần gọi server.
B. Gọi UserInfo vì endpoint đó xác nhận token còn hiệu lực cho mọi API.
C. Gọi introspection endpoint qua kênh được xác thực theo cấu hình tin cậy.
D. Tải JWKS của issuer rồi xác minh chữ ký dù token ở dạng opaque.
Đáp án đúng: C

Một client OIDC gọi UserInfo endpoint sau khi xác thực. Kiểm tra nào giúp liên kết phản hồi với ID token?
A. So khớp sub của UserInfo với client_id trong ID token.
B. So khớp issuer của UserInfo nhưng không cần kiểm tra sub.
C. So khớp nonce trong authorization request với sub của UserInfo.
D. So khớp claim sub của UserInfo với sub đã xác minh trong ID token.
Đáp án đúng: D

Một daemon cần gọi API đối tác bằng danh tính của chính nó, không có người dùng tương tác. Grant nào thường phù hợp?
A. Client credentials cấp token cho confidential client theo quyền của chính client.
B. Authorization code yêu cầu người dùng đăng nhập mỗi khi daemon chạy tác vụ.
C. Device authorization yêu cầu người vận hành nhập user code cho từng request.
D. Implicit flow cấp token trực tiếp cho daemon thông qua redirect của trình duyệt.
Đáp án đúng: A

Một thiết bị giới hạn nhập liệu cần đăng nhập người dùng mà không có trình duyệt đầy đủ. Device authorization flow hoạt động ra sao?
A. Thiết bị hiển thị user code để người dùng xác thực ở thiết bị khác.
B. Thiết bị gửi user_code trực tiếp tới token endpoint thay cho device_code.
C. Authorization server gửi device_code qua SMS để thiết bị nhập tại verification URI.
D. Thiết bị polling authorization endpoint bằng client credentials đến khi có ID token.
Đáp án đúng: A

Một ứng dụng dùng refresh token rotation. Server phát hiện refresh token cũ đã được dùng lại sau khi token mới được cấp. Phản ứng nào phù hợp?
A. Cấp thêm một refresh token mới để cả hai thiết bị tiếp tục hoạt động.
B. Coi đây là dấu hiệu replay và thu hồi token family hoặc phiên liên quan.
C. Chấp nhận token cũ nếu client ID giống với lần refresh trước đó.
D. Gia hạn token cũ và bỏ qua sự kiện vì refresh token có thể dùng nhiều lần.
Đáp án đúng: B

Một hệ thống gọi revocation endpoint để thu hồi access token nhưng API vẫn chấp nhận token JWT đã cache. Nguyên nhân nào có thể giải thích?
A. Thu hồi tại authorization server làm mọi resource server từ chối JWT ngay lập tức.
B. JWT có exp nên API phải gọi revocation endpoint trước mỗi request.
C. Audience còn khớp với API nên việc thu hồi không làm token mất hiệu lực.
D. Resource server chưa nhận trạng thái thu hồi hoặc vẫn tin JWT đến khi hết hạn.
Đáp án đúng: D

Một người dùng chọn Sign out trong ứng dụng OIDC. Phân biệt nào giữa logout cục bộ và logout tại OpenID Provider là chính xác?
A. Xóa session cookie của ứng dụng luôn thu hồi mọi refresh token tại OP.
B. Xóa phiên ứng dụng không nhất thiết kết thúc phiên đăng nhập tại OP.
C. Logout tại OP tự động xóa mọi phiên cục bộ của tất cả relying party.
D. Thu hồi access token đồng nghĩa mọi phiên đăng nhập trên trình duyệt đã kết thúc.
Đáp án đúng: B

Một ứng dụng yêu cầu quyền đọc danh bạ và vị trí dù chỉ cần lịch hẹn. Nguyên tắc consent nào nên áp dụng?
A. Yêu cầu mọi scope có thể có để tránh phải xin consent khi thêm tính năng.
B. Gộp tất cả quyền vào một scope rộng và chỉ giải thích sau khi cấp token.
C. Tự động bỏ qua consent nếu người dùng đã xác thực bằng một identity provider.
D. Chỉ yêu cầu scope cần thiết, giải thích mục đích và tôn trọng lựa chọn người dùng.
Đáp án đúng: D

Một client hỗ trợ nhiều authorization server nhưng callback không xác định rõ issuer đã bắt đầu luồng đăng nhập. Rủi ro nào cần phòng vệ?
A. Authorization server mix-up có thể khiến code hoặc token gửi nhầm issuer.
B. Login CSRF có thể khiến nạn nhân đăng nhập vào tài khoản do attacker kiểm soát.
C. Open redirect có thể chuyển authorization code tới endpoint do attacker kiểm soát.
D. Nonce không được kiểm tra có thể cho phép phát lại ID token cũ.
Đáp án đúng: A

Một client nhận authorization code qua redirect và muốn đổi code tại token endpoint. Kiểm soát nào ngăn code bị dùng lại hoặc chuyển client?
A. Code có thể dùng nhiều lần nếu access token trước đó đã hết hạn hoàn toàn.
B. Chỉ cần code còn hạn và client gửi cùng scope như authorization request.
C. Code được ràng buộc với user session nhưng không cần kiểm tra client hoặc redirect URI.
D. Code dùng một lần, ràng buộc client và kiểm tra redirect URI cùng PKCE verifier.
Đáp án đúng: D

Một client OIDC nhận ID token và cần xác minh token thuộc đúng issuer, client và lần đăng nhập. Tập kiểm tra nào phù hợp?
A. Chỉ kiểm tra chữ ký và sub vì issuer đã được chọn trong authorization request.
B. Kiểm tra chữ ký, iss, aud, exp và nonce; kiểm tra azp khi áp dụng.
C. Kiểm tra aud bằng resource API identifier và dùng scope thay cho nonce.
D. Chỉ kiểm tra nonce vì chữ ký và thời hạn do authorization server bảo đảm.
Đáp án đúng: B

Một API muốn giảm nguy cơ access token bị dùng lại khi bị đánh cắp khỏi thiết bị. DPoP bổ sung cơ chế nào?
A. Mã hóa token bằng khóa đối xứng chung của mọi resource server trong hệ thống.
B. Ràng buộc token với địa chỉ IP công cộng được ghi khi cấp authorization code.
C. Đưa client secret vào header để API xác thực ứng dụng ở mỗi request.
D. Ràng buộc token với khóa của client và yêu cầu proof cho từng request.
Đáp án đúng: D

Một tổ chức dùng mutual TLS cho machine-to-machine API. Sender-constrained token được liên kết với yếu tố nào?
A. Client ID được gửi trong authorization request của ứng dụng native.
B. Dấu vân tay khóa DPoP được dùng để tạo proof cho từng request.
C. Mã định danh phiên TLS được ghi trong metadata của refresh token.
D. Chứng thư client đã được xác thực trong kết nối TLS tương ứng.
Đáp án đúng: D

Một dịch vụ trung gian cần gọi API phía sau thay mặt người dùng nhưng với audience và scope hẹp hơn. Cơ chế nào phù hợp?
A. Dùng ID token gốc làm access token cho mọi API phía sau trong chuỗi gọi.
B. Chia sẻ refresh token của người dùng cho tất cả dịch vụ để tự xin token.
C. Token exchange có thể phát hành token mới với audience hoặc quyền được thu hẹp.
D. Sao chép access token ban đầu vào header mới mà không thay đổi audience.
Đáp án đúng: C

Một access token chứa scope orders.read hợp lệ nhưng người dùng yêu cầu đọc đơn hàng thuộc tenant khác. API cần làm gì?
A. Chấp nhận vì scope orders.read đã chứng minh quyền đọc mọi đơn hàng.
B. Kiểm tra thêm quyền trên đối tượng và ranh giới tenant trước khi trả dữ liệu.
C. Chỉ kiểm tra chữ ký token vì resource authorization nằm ngoài OAuth.
D. Tin tenant ID do client gửi kèm nếu subject trong token hợp lệ.
Đáp án đúng: B

Một access token bị lộ trong log của client production. Nhóm ứng cứu nên ưu tiên xử lý theo hướng nào?
A. Chỉ xoay client secret và giữ access token đã phát hành đến khi hết TTL.
B. Thu hồi token hoặc phiên liên quan, hạn chế credential mới và điều tra phạm vi sử dụng.
C. Yêu cầu người dùng đăng nhập lại nhưng không xử lý token đã lộ.
D. Đổi redirect URI của client để access token cũ không còn được chấp nhận.
Đáp án đúng: B
