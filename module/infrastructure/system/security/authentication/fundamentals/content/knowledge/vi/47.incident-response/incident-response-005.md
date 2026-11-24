# Token compromise: phát hiện và ứng phó khi token bị lộ hoặc chiếm đoạt

Token compromise là tình huống một tác nhân không được phép có được, sử dụng hoặc giả mạo token đang đại diện cho một danh tính, phiên đăng nhập hay quyền truy cập. Token có thể bị đánh cắp từ trình duyệt, ứng dụng, log, kho mã nguồn hoặc hệ thống triển khai; cũng có thể bị phát lại (replay), bị lạm dụng sau khi người dùng đã xác thực, hoặc bị giả mạo khi khóa ký của bên phát hành bị lộ.

Trong hệ thống xác thực, token thường nằm giữa bước xác minh danh tính và bước truy cập tài nguyên. Vì vậy, đổi mật khẩu không phải lúc nào cũng chấm dứt được sự cố: một access token, refresh token, session cookie hay API key đã bị lộ có thể tiếp tục hoạt động độc lập với mật khẩu ban đầu. Ứng phó đúng phải xác định **token nào bị ảnh hưởng, ai phát hành, token cho phép làm gì, tài nguyên nào chấp nhận nó và cơ chế thu hồi nào thực sự có hiệu lực**.

Bài học này tập trung vào việc nhận diện, khoanh vùng, thu hồi và khôi phục sau khi token bị xâm phạm; không thay thế quy trình ứng cứu sự cố tổng thể của tổ chức.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt access token, refresh token, ID token, session cookie, API key, authorization code và token khôi phục.
- Giải thích vì sao token dạng bearer có thể bị sử dụng lại bởi bất kỳ ai sở hữu nó.
- Xây dựng giả thuyết về đường rò rỉ và đánh giá phạm vi ảnh hưởng dựa trên issuer, audience, subject, scope, thời hạn và quyền thực tế.
- Chọn cách containment phù hợp: thu hồi token, hủy phiên, thu hồi grant, xoay API key hoặc thay khóa ký.
- Bảo toàn bằng chứng mà không làm lộ thêm bí mật xác thực.
- Khôi phục quyền truy cập an toàn và bổ sung kiểm soát để giảm nguy cơ tái diễn.

## 1. Token là gì và vì sao bị lộ lại nguy hiểm?

Token là một giá trị được hệ thống phát hành hoặc tạo ra để đại diện cho một quyền, một phiên, một danh tính đã được xác minh hoặc một giao dịch xác thực đang diễn ra. Tùy thiết kế, token có thể là chuỗi ngẫu nhiên opaque, JWT có chữ ký, cookie phiên, API key hoặc một assertion có thời hạn.

Điểm quan trọng nhất khi ứng phó là: **không phải token nào cũng có cùng ý nghĩa và cùng phạm vi quyền**.

| Loại token / artefact | Mục đích thường gặp | Hệ quả nếu bị chiếm đoạt |
|---|---|---|
| Access token | Gọi API trong một audience và scope nhất định | Kẻ tấn công có thể gọi các API được cấp quyền cho đến khi token hết hạn hoặc bị thu hồi |
| Refresh token | Xin access token mới mà không cần đăng nhập lại | Có thể duy trì quyền truy cập lâu dài; rủi ro cao nếu không có rotation và phát hiện reuse |
| Session cookie | Đại diện cho phiên đã đăng nhập trong trình duyệt | Kẻ tấn công có thể chiếm phiên mà không cần biết mật khẩu |
| ID token | Truyền thông tin xác thực người dùng cho OIDC client | Có thể gây nhầm lẫn danh tính hoặc đăng nhập sai nếu client xác minh sai; không mặc định dùng làm access token cho API |
| API key / service token | Xác thực ứng dụng, tích hợp hoặc workload | Có thể mở quyền truy cập hệ thống hoặc dữ liệu theo quyền của service account |
| Authorization code | Hoàn tất luồng OAuth/OIDC | Có thể bị đổi lấy token nếu còn hiệu lực và các ràng buộc như PKCE không được áp dụng đúng |
| Password-reset / enrollment token | Cho phép đặt lại mật khẩu hoặc đăng ký yếu tố xác thực | Có thể chiếm tài khoản hoặc thay đổi phương thức xác thực |
| Signed assertion | Truyền một khẳng định đã ký giữa các hệ thống | Có thể bị phát lại hoặc giả mạo nếu chữ ký, audience, thời hạn và chống replay không được kiểm tra |

### 1.1. Bearer token và token gắn với người sở hữu

Với **bearer token**, quyền sử dụng gắn với việc sở hữu giá trị token. Máy chủ thường không biết người gửi có phải thiết bị hoặc người dùng ban đầu hay không. Nếu token bị sao chép, kẻ tấn công có thể phát lại token từ một thiết bị khác.

Với token được ràng buộc với người sở hữu (sender-constrained token), việc sử dụng token còn đòi hỏi bằng chứng sở hữu khóa hoặc chứng thư tương ứng. Ví dụ:

- mTLS-bound access token gắn với chứng thư phía client.
- DPoP yêu cầu client tạo proof gắn với khóa và request.

Ràng buộc này làm giảm giá trị của token bị đánh cắp đơn lẻ, nhưng không loại bỏ mọi rủi ro: thiết bị hoặc khóa riêng cũng có thể bị chiếm đoạt; proof vẫn cần được kiểm tra đúng và có biện pháp chống replay.

### 1.2. Token opaque và JWT

- **Opaque token** không mang các claim có thể đọc trực tiếp; resource server thường phải introspect token hoặc tra cứu trạng thái ở hệ thống phát hành.
- **JWT ký dạng JWS** có payload thường đọc được. Chữ ký giúp kiểm tra tính toàn vẹn và nguồn phát hành, không làm payload bí mật.
- **JWT mã hóa dạng JWE** cung cấp mã hóa theo cấu hình, nhưng vẫn cần xác minh issuer, audience, thời hạn và chính sách sử dụng.

Không được kết luận rằng JWT an toàn chỉ vì có chữ ký. Một JWT bị đánh cắp vẫn có thể được phát lại nếu nó là bearer token và còn hiệu lực. Claim **jti** chỉ giúp định danh token; nó không tự tạo ra khả năng thu hồi nếu resource server không kiểm tra denylist hoặc trạng thái tương ứng.

### 1.3. Access token không đồng nghĩa ID token

Trong OpenID Connect:

- ID token dành cho client để xác nhận kết quả xác thực và danh tính người dùng. Client phải kiểm tra chữ ký, issuer, audience, thời hạn, nonce khi áp dụng và các quy tắc OIDC liên quan.
- Access token dành cho resource server/API. API phải xác minh token theo hợp đồng của mình, đặc biệt là issuer, audience, scope/quyền và thời hạn.

Không lấy ID token làm access token chỉ vì cả hai đều là JWT. Việc chấp nhận nhầm audience có thể biến lỗi cấu hình thành đường truy cập trái phép.

## 2. Mô hình ranh giới tin cậy và vòng đời token

Để điều tra token compromise, hãy mô hình hóa đường đi của token qua các ranh giới tin cậy:

1. **Identity provider / authorization server** xác minh người dùng hoặc client, rồi phát hành token.
2. **Client** nhận và lưu token, chẳng hạn ứng dụng web, ứng dụng di động, CLI hoặc workload.
3. **Resource server** nhận token và quyết định có cho phép truy cập hay không.
4. **Hệ thống lưu trữ và vận hành** có thể vô tình ghi token vào log, telemetry, crash dump, bản sao lưu hoặc hệ thống hỗ trợ.
5. **Hệ thống thu hồi và quản trị phiên** quản lý trạng thái phiên, refresh token, grant, API key hoặc khóa ký.

Một token chỉ an toàn khi tất cả thành phần trong chuỗi đều thực thi đúng hợp đồng. Ví dụ, authorization server có thể phát hành access token ngắn hạn và đúng scope, nhưng resource server không kiểm tra audience; hoặc client lưu token đúng cách nhưng reverse proxy ghi nguyên header Authorization vào access log.

### 2.1. Các thuộc tính cần kiểm tra

Khi có token nghi bị lộ, xác định tối thiểu:

- **iss (issuer):** hệ thống nào phát hành?
- **sub (subject):** token đại diện cho người dùng hoặc workload nào?
- **aud (audience):** tài nguyên hoặc client nào được phép nhận token?
- **scope / roles / permissions:** token cho phép hành động nào?
- **iat, nbf, exp:** token được phát hành khi nào, bắt đầu có hiệu lực và hết hạn lúc nào?
- **jti** hoặc định danh nội bộ: có thể đối chiếu token với sự kiện nào?
- **kid:** khóa nào đã được dùng để ký JWT?
- client ID, grant, device/session ID và phương thức xác thực liên quan.

Không tin các claim chỉ vì có thể giải mã payload. Chỉ sử dụng claim sau khi xác minh chữ ký hoặc introspection theo đúng cấu hình tin cậy. Header JWT và **kid** cũng là dữ liệu đầu vào không đáng tin cậy cho đến khi được xử lý bằng cơ chế chọn khóa an toàn.

### 2.2. Thời hạn và khả năng thu hồi

Access token ngắn hạn giới hạn khoảng thời gian lạm dụng, nhưng không tự giải quyết được sự cố trong thời gian token còn hiệu lực. Các hệ thống có thể dùng:

- Introspection hoặc tra cứu trạng thái token tại resource server.
- Denylist theo **jti** hoặc fingerprint token.
- Hủy phiên ở kho session tập trung.
- Thu hồi refresh token hoặc toàn bộ token family.
- Thu hồi authorization grant / consent.
- Vô hiệu hóa API key hoặc client credential.
- Xoay khóa ký khi chính khóa ký bị lộ.

Cần kiểm tra cache ở API gateway, resource server và các vùng triển khai. Thu hồi tại authorization server chưa chắc có hiệu lực tức thời nếu resource server chấp nhận JWT tự xác minh mà không tra cứu trạng thái cho đến khi token hết hạn.

## 3. Đường dẫn phổ biến dẫn đến token compromise

| Đường dẫn | Ví dụ | Câu hỏi điều tra |
|---|---|---|
| Phishing / adversary-in-the-middle | Người dùng nhập thông tin tại trang giả; proxy độc hại lấy cookie hoặc token sau đăng nhập | Có phiên mới, thiết bị lạ, hoặc token được dùng ngay sau một lần đăng nhập bất thường không? |
| Malware hoặc thiết bị bị chiếm quyền | Malware đọc profile trình duyệt, bộ nhớ tiến trình hoặc file cấu hình | Thiết bị nào chứa token? Có dấu hiệu mã độc hoặc truy cập file bất thường không? |
| XSS / script độc hại | Script trong origin hợp lệ thực hiện hành động bằng phiên người dùng hoặc đọc token lưu trong vùng JavaScript truy cập được | Có lỗ hổng XSS, script bên thứ ba hoặc thay đổi nội dung trang đáng ngờ không? |
| Log / telemetry / crash dump | Header Authorization, cookie hoặc URL chứa token bị ghi lại | Proxy, APM, tracing, error report và hệ thống hỗ trợ có lưu giá trị nhạy cảm không? |
| URL và referrer | Token hoặc mã xác thực nằm trong query string; URL bị lưu trong lịch sử, analytics hoặc referrer | Có token trong URL, redirect, ảnh chụp màn hình hoặc lịch sử trình duyệt không? |
| Kho mã nguồn / CI-CD | API key nằm trong commit, build log, artifact hoặc biến môi trường bị lộ | Secret xuất hiện ở repository, fork, package, cache hay log pipeline nào? |
| Rò rỉ refresh token | Ứng dụng lưu refresh token không an toàn hoặc không rotation | Có refresh token reuse, nhiều thiết bị dùng cùng token family hoặc chuỗi refresh bất thường không? |
| Sai cấu hình xác minh | API chấp nhận sai issuer/audience, thuật toán hoặc chữ ký | Có thể giả mạo token hoặc dùng token phát hành cho dịch vụ khác không? |
| Lộ khóa ký | Private signing key bị truy cập trái phép | Có token giả được ký hợp lệ, kid bất thường hoặc quyền truy cập kho khóa trái phép không? |

Đừng mặc định rằng địa chỉ IP khác hoặc vị trí địa lý khác chứng minh token bị đánh cắp. Người dùng có thể dùng VPN, mạng di động hoặc roaming. Cần kết hợp nhiều tín hiệu, thời gian, thiết bị, hành vi và quyền được sử dụng.

## 4. Dấu hiệu phát hiện và đánh giá mức độ

### 4.1. Tín hiệu có thể chỉ ra token bị lạm dụng

- Cùng một session hoặc token fingerprint xuất hiện đồng thời từ thiết bị, ASN hoặc khu vực không phù hợp với hành vi thông thường.
- Refresh token đã bị rotation nhưng token cũ tiếp tục được sử dụng (reuse detection).
- Một phiên thực hiện hành động nhạy cảm mà không có bước xác thực tăng cường (step-up) theo chính sách.
- API nhận token có audience hoặc scope không phù hợp với client, route hoặc loại thao tác.
- Tài khoản có phiên mới, thiết bị mới, thay đổi phương thức MFA hoặc thông tin khôi phục ngay trước/sau hành vi đáng ngờ.
- Service account hoặc API key truy cập tài nguyên, thời điểm hay khối lượng khác thường.
- Có authorization grant/consent mới cho ứng dụng không quen thuộc.
- JWT được chấp nhận sau khi khóa ký tương ứng đã bị thu hồi, hoặc xuất hiện token có kid không được tin cậy.
- Token được sử dụng sau khi người dùng báo đã đăng xuất hoặc sau khi phiên được cho là đã hủy.

Một chỉ báo đơn lẻ không đủ để kết luận. Ví dụ, “impossible travel” có thể là false positive do VPN hoặc NAT; nhưng kết hợp với refresh token reuse, thiết bị mới và truy cập dữ liệu nhạy cảm thì mức tin cậy cao hơn.

### 4.2. Dữ liệu cần thu thập khi triage

Ghi nhận metadata, không sao chép bí mật xác thực:

- Loại token, issuer, audience, subject hoặc service account.
- Scope/role và tài nguyên có thể truy cập.
- Thời điểm phát hành, hết hạn, thời điểm phát hiện và lần sử dụng đáng ngờ.
- Client ID, session/device ID, grant ID, jti hoặc fingerprint đã được tạo an toàn.
- IP, ASN, user-agent, request ID, route/API và kết quả hành động.
- Sự kiện đăng nhập, MFA, đổi mật khẩu, khôi phục tài khoản, consent và thay đổi thiết bị.
- Nơi token có thể bị lộ: repository, log, endpoint, thiết bị hoặc hệ thống bên thứ ba.
- Trạng thái thu hồi và độ trễ đồng bộ đến các resource server.

**Không ghi token thô, cookie, authorization header, refresh token, password-reset link hoặc private key vào ticket, chat, email hay log điều tra.** Nếu cần liên kết nhiều sự kiện, dùng fingerprint có kiểm soát, ví dụ HMAC-SHA-256 của token bằng khóa chỉ dành cho logging. Không dùng fingerprint để thay thế xác minh chữ ký hoặc trạng thái token.

### 4.3. Ước lượng mức độ nghiêm trọng

| Mức | Dấu hiệu tham khảo | Hướng xử lý |
|---|---|---|
| Thấp / đang xác minh | Có một cảnh báo yếu; chưa thấy sử dụng trái phép; token có quyền hẹp và thời hạn ngắn | Xác minh nguồn cảnh báo, kiểm tra log và chuẩn bị thu hồi |
| Trung bình | Có bằng chứng token bị lộ nhưng quyền hạn chế hoặc chưa thấy truy cập dữ liệu nhạy cảm | Thu hồi đúng token/phiên, kiểm tra hoạt động và đánh giá thiết bị/client |
| Cao | Token còn hiệu lực với quyền rộng, refresh token bị lộ, có hành vi trái phép hoặc truy cập dữ liệu quan trọng | Containment ngay, mở rộng rà soát đến tài khoản, grant, client và tài nguyên liên quan |
| Nghiêm trọng | Khóa ký, credential diện rộng hoặc token đặc quyền của hệ thống trọng yếu bị lộ; có dấu hiệu giả mạo hoặc di chuyển ngang | Kích hoạt quy trình sự cố nghiêm trọng, phối hợp chủ hệ thống, thu hồi diện rộng có kiểm soát và đánh giá toàn bộ trust domain |

Mức độ cuối cùng phụ thuộc vào quyền thực tế, dữ liệu bị ảnh hưởng, thời gian phơi nhiễm, khả năng phát lại và phạm vi hệ thống chấp nhận token. Không chỉ dựa vào tên loại token.

## 5. Quy trình ứng phó token compromise

### Bước 1 — Chuẩn bị

Trước khi có sự cố, tổ chức cần biết:

- Ai sở hữu authorization server, resource server, API gateway, session store, client và kho khóa.
- Cách thu hồi từng loại token và thời gian lan truyền đến các node.
- Cách hủy một phiên, một token family, một grant, một API key và một signing key.
- Log nào lưu metadata, thời gian lưu giữ và cách bảo vệ bằng chứng.
- Kênh liên lạc an toàn với chủ tài khoản, đội vận hành và bên thứ ba.
- Quy trình thay secret trong workload mà không để lộ secret mới.

Nên diễn tập tình huống token bị lộ trong repository, session cookie bị đánh cắp và refresh token reuse. Một quy trình thu hồi chỉ tồn tại trên tài liệu nhưng chưa được kiểm thử có thể không đủ nhanh khi sự cố xảy ra.

### Bước 2 — Xác nhận và phân loại

1. Xác nhận tín hiệu đến từ nguồn đáng tin cậy; lưu thời điểm và request/event ID.
2. Phân loại artefact: access token, refresh token, session cookie, API key, reset token, authorization code hay khóa ký.
3. Xác định issuer, subject, audience, scope, thời hạn và client.
4. Xác định token đã bị lộ ở đâu, ai có thể truy cập nơi đó và khoảng thời gian phơi nhiễm.
5. Kiểm tra token đã được sử dụng trái phép hay mới chỉ có khả năng bị lộ.
6. Đánh giá xem token có thể được thu hồi riêng lẻ hay cần thu hồi phiên, family, grant hoặc credential rộng hơn.

Nếu không thể xác định loại token hoặc phạm vi quyền, hãy giả định phạm vi chưa rõ và ưu tiên containment có kiểm soát; không tự suy luận rằng token vô hại chỉ vì tên hoặc định dạng của nó.

### Bước 3 — Containment: ngăn sử dụng tiếp

Chọn hành động theo đúng loại artefact:

| Artefact bị ảnh hưởng | Hành động containment | Lưu ý quan trọng |
|---|---|---|
| Session cookie | Hủy session tương ứng ở server-side session store; xoay session ID khi tạo phiên mới; nếu không xác định được phiên, cân nhắc hủy toàn bộ phiên của tài khoản | Xóa cookie ở trình duyệt của người dùng không làm cookie đã bị sao chép mất hiệu lực ở phía server |
| Access token opaque | Gọi cơ chế revoke/introspection hoặc đánh dấu token bị thu hồi theo định danh nội bộ | Xác minh resource server có kiểm tra trạng thái mới hay đang dùng cache |
| JWT access token | Denylist theo jti/fingerprint nếu có hỗ trợ; vô hiệu hóa grant hoặc chủ thể nếu cần; chờ hết hạn chỉ khi rủi ro chấp nhận được và có biện pháp giảm thiểu | JWT tự xác minh không tự biết đã bị thu hồi; cần tính đến cache và mọi resource server |
| Refresh token | Thu hồi token và token family liên quan; thu hồi grant khi cần; buộc xác thực lại; điều tra dấu hiệu reuse | Thu hồi access token đơn lẻ nhưng để refresh token sống có thể khiến kẻ tấn công lấy access token mới |
| OAuth grant / consent | Thu hồi grant hoặc consent đáng ngờ, token liên quan và kiểm tra ứng dụng/client được cấp quyền | Xóa ứng dụng khỏi giao diện người dùng không đảm bảo grant phía authorization server đã bị hủy |
| API key / service credential | Thu hồi key bị lộ; tạo key mới qua secret manager; triển khai key mới rồi xác minh trước khi xóa key cũ còn hợp lệ | Không chỉ xóa key khỏi commit mới; bản sao, fork, log và artifact cũ vẫn có thể tồn tại |
| Password-reset / enrollment token | Vô hiệu hóa token đang chờ; phát hành lại qua kênh đã xác minh; kiểm tra thay đổi mật khẩu/yếu tố gần đây | Không gửi token mới qua cùng kênh đang bị nghi xâm phạm |
| Signing key | Ngừng tin cậy kid bị ảnh hưởng, thay khóa, cập nhật JWKS và chính sách xác minh ở mọi consumer; vô hiệu hóa token được ký bằng khóa bị lộ | Đây là sự cố phạm vi rộng: kẻ có private key có thể tự tạo token giả hợp lệ cho đến khi mọi consumer ngừng tin khóa đó |

Không xoay signing key chỉ vì một access token riêng lẻ bị lộ. Xoay khóa ký là biện pháp cho tình huống khóa ký hoặc trust chain bị xâm phạm, hoặc khi phân tích cho thấy cần thiết. Ngược lại, nếu private signing key thực sự bị lộ, chỉ thu hồi một token đã phát hiện là không đủ.

Nếu chưa thể thu hồi token riêng lẻ, có thể cần tạm khóa subject/client, chặn route hoặc tăng xác thực cho hành động nhạy cảm. Mọi biện pháp diện rộng phải được phối hợp với chủ dịch vụ để giảm gián đoạn nhưng không trì hoãn containment khi nguy cơ đang diễn ra.

### Bước 4 — Xác định phạm vi ảnh hưởng

Sau khi chặn việc sử dụng tiếp, trả lời các câu hỏi:

- Token cho phép truy cập API, tenant, dự án, dữ liệu hoặc môi trường nào?
- Có quyền đọc, ghi, xóa, quản trị hay tạo credential mới không?
- Kẻ tấn công đã thực hiện hành động nào? Có tạo người dùng, key, grant, webhook hoặc session mới không?
- Token có được dùng để lấy token khác, truy cập hệ thống khác hoặc di chuyển ngang không?
- Có bản sao của token trong cache, log, backup, artifact, repository, thiết bị hoặc bên thứ ba không?
- Có token khác được phát hành trong cùng phiên, grant hoặc chuỗi tin cậy cần thu hồi không?

Tìm kiếm theo subject, client, session ID, jti, token family, fingerprint và khoảng thời gian. Không tìm bằng cách đưa token thô vào công cụ tìm kiếm/log nếu điều đó tạo thêm bản sao bí mật.

### Bước 5 — Eradication: loại bỏ nguyên nhân

- Xóa hoặc vô hiệu hóa nơi rò rỉ: secret trong repository, log, artifact, biến môi trường, file cấu hình hoặc thiết bị bị xâm nhập.
- Vá lỗ hổng XSS, SSRF, redirect hoặc lỗi kiểm tra token đã tạo điều kiện rò rỉ/lạm dụng.
- Gỡ ứng dụng độc hại, extension không tin cậy hoặc workload bị xâm nhập theo quy trình endpoint/security.
- Sửa cấu hình issuer, audience, thuật toán, scope, redirect URI, PKCE hoặc xác minh chữ ký nếu có sai sót.
- Xoay credential liên quan theo thứ tự an toàn; cập nhật secret manager, workload và dịch vụ tiêu thụ.
- Kiểm tra persistence: session mới, refresh token mới, API key mới, OAuth grant mới, yếu tố MFA lạ, tài khoản phụ hoặc thay đổi thông tin khôi phục.

Không chỉ xóa dấu vết lộ secret khỏi nơi nhìn thấy được. Nếu secret đã vào lịch sử Git, fork hoặc artifact, phải coi giá trị đó đã bị lộ và thu hồi nó.

### Bước 6 — Khôi phục và xác minh

- Xác minh mọi resource server và gateway đã áp dụng trạng thái thu hồi hoặc trust key mới.
- Cấp lại token/credential qua luồng xác thực đáng tin cậy; dùng scope tối thiểu và thời hạn phù hợp.
- Với tài khoản người dùng, xác minh danh tính qua kênh đáng tin cậy; xem xét đổi mật khẩu nếu mật khẩu cũng có thể bị lộ.
- Hủy các phiên và refresh token còn nghi vấn; kiểm tra phương thức MFA, passkey, email/điện thoại khôi phục và OAuth consent.
- Không tự động xóa passkey hoặc chứng chỉ chỉ vì access token bị lộ; chỉ thu hồi authenticator nếu có bằng chứng thiết bị/khóa riêng hoặc quy trình đăng ký đã bị xâm phạm.
- Theo dõi đăng nhập, refresh, consent và hành động nhạy cảm sau khôi phục để phát hiện tái xâm nhập.

Đổi mật khẩu không tự động hủy mọi phiên. Cần xác minh chính sách session invalidation của hệ thống; nếu không, phiên cũ hoặc refresh token cũ có thể tiếp tục hoạt động.

### Bước 7 — Kết thúc và rút kinh nghiệm

Ghi nhận timeline, nguyên nhân gốc, hệ thống bị ảnh hưởng, token/credential đã thu hồi, phạm vi dữ liệu và quyết định containment. Đánh giá:

- Phát hiện mất bao lâu từ thời điểm lộ đến cảnh báo?
- Thu hồi mất bao lâu để có hiệu lực trên mọi resource server?
- Có log nào chứa bí mật xác thực không?
- Có token sống quá lâu hoặc scope quá rộng không?
- Có thiếu refresh rotation, reuse detection, token binding hoặc kiểm tra audience không?
- Có thể tự động hóa thu hồi và thông báo cho chủ tài khoản không?

Chỉ đóng sự cố khi có bằng chứng rằng đường truy cập bị xâm phạm đã bị chặn, persistence đã được kiểm tra và hệ thống đã hoạt động theo trạng thái tin cậy mới.

## 6. Các tình huống ứng phó mẫu

### Tình huống A — Session cookie của người dùng bị đánh cắp

**Dấu hiệu:** Một session ID xuất hiện từ hai môi trường khác nhau; phiên thực hiện thao tác nhạy cảm sau một lần đăng nhập bình thường.

**Xử lý:**

1. Đối chiếu session ID/fingerprint, thời gian, thiết bị, IP/ASN và các hành động.
2. Hủy session ở phía server; không chỉ hướng dẫn người dùng xóa cookie.
3. Hủy các phiên liên quan nếu không thể xác định chính xác phiên bị lộ.
4. Kiểm tra hoạt động trong phiên: đọc/xuất dữ liệu, thay đổi email, thêm MFA, tạo API key hoặc OAuth consent.
5. Kiểm tra thiết bị, XSS, extension, malware, log và kênh phishing có thể đã làm lộ cookie.
6. Cho người dùng đăng nhập lại qua origin chính thức; xác minh yếu tố khôi phục và MFA trước khi khôi phục quyền nhạy cảm.

**Bài học:** Cookie có HttpOnly ngăn JavaScript đọc trực tiếp cookie, nhưng không ngăn script XSS thực hiện request dưới phiên người dùng. Vẫn cần chống XSS, CSRF, quản lý phiên và phát hiện hành vi bất thường.

### Tình huống B — Refresh token bị reuse

**Dấu hiệu:** Client đã đổi refresh token cũ lấy token mới, nhưng token cũ lại xuất hiện trong một lần refresh sau đó.

**Xử lý:**

1. Xác định token family, client, subject và thiết bị liên quan.
2. Kiểm tra đây có phải retry hợp lệ, đồng bộ nhiều tiến trình hoặc lỗi rotation của client hay không.
3. Nếu reuse không hợp lệ, thu hồi token family và grant liên quan; yêu cầu xác thực lại.
4. Rà soát access token đã được cấp từ family đó và hành động thực hiện trong thời gian nghi vấn.
5. Kiểm tra nơi lưu refresh token, backup, log, thiết bị và khả năng malware/phishing.
6. Sau khôi phục, xác minh client thực hiện rotation đúng và server phát hiện reuse nhất quán.

**Bài học:** Rotation có giá trị khi server duy trì quan hệ giữa token cũ và token mới, phát hiện reuse và có chính sách thu hồi family. Chỉ phát hành token mới mà không theo dõi family sẽ bỏ lỡ tín hiệu quan trọng.

### Tình huống C — API key xuất hiện trong repository công khai

**Dấu hiệu:** Secret scanning phát hiện chuỗi có hình dạng API key trong commit hoặc pull request.

**Xử lý:**

1. Xác định key thuộc service account, project, môi trường và quyền nào.
2. Thu hồi key đã lộ; nếu cần duy trì dịch vụ, tạo key thay thế qua secret manager, triển khai và kiểm tra trước khi ngừng key cũ còn lại.
3. Kiểm tra audit log từ thời điểm sớm nhất key có thể đã công khai; tìm hành vi truy cập bất thường.
4. Rà soát fork, clone, package, build log, artifact, cache và bản sao.
5. Xóa secret khỏi nguồn lưu trữ theo quy trình, nhưng không coi việc rewrite Git history là thay thế cho thu hồi key.
6. Giảm scope, giới hạn nguồn gọi nếu phù hợp và bổ sung secret scanning/pre-commit/CI.

**Bài học:** Xóa commit không làm giá trị bí mật trở lại an toàn. Hãy coi key đã công khai là bị xâm phạm.

### Tình huống D — Private signing key của issuer bị lộ

**Dấu hiệu:** Có bằng chứng truy cập trái phép vào kho khóa hoặc token giả được ký bằng kid hợp lệ.

**Xử lý:**

1. Kích hoạt quy trình sự cố phạm vi issuer/trust domain; xác định khóa, thuật toán, issuer và toàn bộ consumer tin cậy khóa đó.
2. Tạo khóa mới trong môi trường tin cậy; bảo vệ private key và xác minh quy trình phân phối public key.
3. Loại kid bị xâm phạm khỏi tập khóa được chấp nhận; cập nhật JWKS/cache và cấu hình verifier ở mọi resource server.
4. Vô hiệu hóa token được ký bằng khóa bị lộ hoặc áp dụng chính sách từ chối theo kid/thời điểm phát hành; xác định cách xử lý token còn hiệu lực.
5. Rà soát token giả, subject/scope bất thường, API access và các credential được tạo trong khoảng thời gian phơi nhiễm.
6. Kiểm tra backup, replica, HSM/KMS policy, quyền quản trị và audit log để tìm đường truy cập ban đầu.

**Bài học:** Khi private signing key bị lộ, kẻ tấn công có thể tạo token có chữ ký hợp lệ theo khóa đó. Mọi consumer vẫn tin khóa cũ đều nằm trong phạm vi ảnh hưởng, kể cả khi chưa tìm thấy token giả.

## 7. Kiểm soát phòng ngừa và thiết kế chống tái diễn

### 7.1. Giảm giá trị của token bị đánh cắp

- Dùng access token có thời hạn ngắn phù hợp với mức rủi ro và độ trễ thu hồi.
- Giới hạn audience, scope, role, tenant và quyền theo nguyên tắc đặc quyền tối thiểu.
- Dùng refresh token rotation, token family và reuse detection.
- Cân nhắc DPoP hoặc mTLS-bound token cho client và môi trường phù hợp.
- Dùng session timeout, idle timeout và xác thực tăng cường cho thao tác nhạy cảm.
- Tách token của người dùng khỏi credential của workload; không dùng chung một key cho nhiều ứng dụng/môi trường.

### 7.2. Lưu trữ và truyền token an toàn

- Chỉ truyền token qua TLS; không đưa access token, refresh token hoặc reset token vào query string.
- Với cookie phiên, dùng Secure, HttpOnly và SameSite phù hợp; có biện pháp CSRF tương ứng với kiến trúc.
- Tránh lưu token dài hạn ở nơi JavaScript bất kỳ trên origin có thể đọc, chẳng hạn localStorage, nếu có lựa chọn an toàn hơn.
- Giới hạn quyền truy cập file cấu hình, keychain, keystore và secret manager; không hard-code secret trong source code.
- Không ghi token vào application log, reverse-proxy log, tracing, analytics, crash report hoặc support ticket.
- Che/redact các trường Authorization, Cookie, Set-Cookie, mã reset và secret tương tự ở mọi tầng logging.

HttpOnly không phải biện pháp chống XSS toàn diện; SameSite không thay thế mọi biện pháp chống CSRF. Cần phòng vệ nhiều lớp: encode output, CSP phù hợp, kiểm soát dependency/script bên thứ ba, kiểm tra origin và xác thực request theo ngữ cảnh.

### 7.3. Xác minh token đúng ở resource server

Với JWT, verifier phải có chính sách rõ ràng và nhất quán:

- Chỉ chấp nhận thuật toán được cấu hình cho issuer; không suy ra thuật toán tin cậy từ token do client gửi.
- Xác minh chữ ký bằng khóa tin cậy và xử lý kid an toàn.
- Kiểm tra issuer, audience, thời hạn và các claim bắt buộc.
- Kiểm tra scope/role theo từng endpoint và từng hành động.
- Không chấp nhận token hết hạn, chưa đến thời điểm hiệu lực hoặc token dành cho audience khác.
- Có cơ chế thu hồi/denylist/introspection khi yêu cầu nghiệp vụ đòi hỏi hiệu lực thu hồi nhanh.
- Đồng bộ thời gian hệ thống và đặt clock skew nhỏ, có kiểm soát.

Với opaque token, resource server cần introspection hoặc cơ chế tra cứu trạng thái có xác thực, bảo vệ kênh truyền và cache theo chính sách phù hợp.

### 7.4. Thiết kế OAuth/OIDC an toàn

- Ưu tiên Authorization Code Flow với PKCE cho ứng dụng công khai.
- Ràng buộc redirect URI chính xác; không dùng wildcard rộng.
- Kiểm tra state, nonce và các ràng buộc giao dịch theo đúng flow.
- Giới hạn audience và scope; không phát access token rộng hơn nhu cầu.
- Bảo vệ refresh token, rotation và reuse detection.
- Không dùng ID token thay access token cho API.
- Có quy trình thu hồi token, grant và consent; ghi audit event khi cấp hoặc thu hồi quyền.
- Với authorization code, bảo đảm dùng một lần, thời hạn ngắn và ràng buộc PKCE đúng.

### 7.5. Khả năng quan sát mà không làm lộ bí mật

Log nên ghi nhận loại token, issuer, audience, subject nội bộ, client, scope, session/device ID, jti hoặc fingerprint an toàn, thời điểm và request ID. Log không nên chứa giá trị token hoặc private key.

Đặt cảnh báo cho:

- Refresh token reuse.
- Một session/token fingerprint hoạt động từ nhiều môi trường không phù hợp.
- Consent hoặc grant mới có quyền rộng.
- API key/service account sử dụng ngoài baseline.
- Token sai audience, issuer, kid hoặc chữ ký.
- Hành động nhạy cảm sau đăng nhập hoặc thiết bị mới.

Cảnh báo phải có ngữ cảnh để giảm false positive; cần quy trình kiểm chứng và hành động tương ứng, không chỉ gửi thông báo.

## 8. Sơ đồ luồng ứng phó

~~~mermaid
flowchart TD
    A[Phát hiện token có dấu hiệu bị lộ] --> B[Phân loại token và xác minh tín hiệu]
    B --> C[Xác định issuer, subject, audience, scope và thời hạn]
    C --> D{Có bằng chứng hoặc rủi ro sử dụng trái phép?}
    D -->|Có| E[Containment: thu hồi token, phiên, family, grant hoặc key]
    D -->|Chưa rõ| F[Giữ bằng chứng, giới hạn rủi ro và tiếp tục triage]
    F --> E
    E --> G[Kiểm tra resource server, cache và phạm vi truy cập]
    G --> H[Loại bỏ nguyên nhân và persistence]
    H --> I[Khôi phục credential/phiên qua luồng tin cậy]
    I --> J[Xác minh thu hồi, theo dõi và rút kinh nghiệm]
~~~

Một luồng phản ứng mẫu có thể biểu diễn như sau:

~~~text
Detection
  -> Classify token and trust boundary
  -> Preserve metadata and timeline
  -> Revoke the smallest effective scope
  -> Verify propagation to every consumer
  -> Investigate use and persistence
  -> Remove root cause
  -> Re-authenticate / re-issue safely
  -> Monitor and close with evidence
~~~

## 9. Checklist thực hành cho người ứng cứu

### Trước khi containment

- [ ] Đã xác định loại token hoặc ghi rõ rằng loại token chưa chắc chắn.
- [ ] Đã xác định issuer, subject, audience, scope/quyền và thời hạn.
- [ ] Đã lưu timestamp, request ID, session/client ID và metadata cần thiết.
- [ ] Không sao chép token thô vào ticket, chat, email hoặc log.
- [ ] Đã đánh giá token có thể tạo token khác hoặc truy cập hệ thống khác không.

### Trong containment

- [ ] Đã chọn đúng cơ chế thu hồi cho loại token bị ảnh hưởng.
- [ ] Đã thu hồi refresh token family/grant khi cần, không chỉ access token hiện tại.
- [ ] Đã kiểm tra session store, gateway, cache và mọi resource server.
- [ ] Đã thay API key hoặc signing key khi chính credential/khóa đó bị lộ.
- [ ] Đã cân nhắc tác động dịch vụ và thông báo cho chủ hệ thống.

### Trước khi đóng sự cố

- [ ] Đã xác định hành động trái phép và phạm vi dữ liệu/tài nguyên bị ảnh hưởng.
- [ ] Đã loại bỏ đường rò rỉ hoặc lỗ hổng gốc.
- [ ] Đã kiểm tra session, grant, MFA, thông tin khôi phục và credential mới đáng ngờ.
- [ ] Đã xác minh trạng thái thu hồi có hiệu lực trên mọi consumer liên quan.
- [ ] Đã khôi phục quyền truy cập qua kênh tin cậy và theo dõi sau khôi phục.
- [ ] Đã ghi nhận timeline, quyết định, bằng chứng và hành động phòng ngừa.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Một người dùng đổi mật khẩu sau khi báo bị phishing. Vì sao vẫn cần hủy session và refresh token?

**Gợi ý:** Token/phiên đã phát hành có thể độc lập với mật khẩu. Nếu không thu hồi, kẻ tấn công có thể tiếp tục dùng session cookie hoặc lấy access token mới bằng refresh token.

**Câu 2.** API nhận JWT có chữ ký hợp lệ nhưng audience không dành cho API đó. API nên xử lý thế nào?

**Gợi ý:** Từ chối token. Chữ ký hợp lệ chỉ xác nhận token được ký bởi khóa tin cậy; audience vẫn phải khớp với resource server.

**Câu 3.** Secret scanner phát hiện API key trong commit công khai. Vì sao xóa commit là chưa đủ?

**Gợi ý:** Secret có thể đã được sao chép vào fork, clone, cache, log và artifact. Phải thu hồi key đã lộ, kiểm tra audit log và cấp key mới an toàn.

**Câu 4.** Khi nào cần xoay signing key thay vì chỉ thu hồi một access token?

**Gợi ý:** Khi private signing key hoặc trust chain bị xâm phạm, hoặc có bằng chứng kẻ tấn công có thể tự tạo token được consumer tin cậy. Nếu chỉ một bearer token bị lộ, hãy thu hồi token/phiên/grant theo phạm vi phù hợp.

**Câu 5.** Vì sao jti không tự làm JWT có thể thu hồi?

**Gợi ý:** jti chỉ là định danh. Resource server phải tra cứu denylist hoặc trạng thái tương ứng; nếu chỉ xác minh chữ ký và thời hạn, token vẫn được chấp nhận đến khi hết hạn.

## 11. Nguyên tắc cần ghi nhớ

1. Token bị lộ là sự cố về quyền truy cập, không chỉ là sự cố về mật khẩu.
2. Phân loại token và ranh giới tin cậy trước khi chọn hành động thu hồi.
3. Bearer token bị sao chép có thể bị phát lại; chữ ký JWT không ngăn replay.
4. Thu hồi phải có hiệu lực ở nơi token được chấp nhận, kể cả cache và resource server.
5. Refresh token, session, grant, API key và signing key cần các chiến lược containment khác nhau.
6. Không lưu hoặc chia sẻ token thô trong quá trình điều tra.
7. Khôi phục chỉ hoàn tất khi nguyên nhân gốc và persistence đã được xử lý, không chỉ khi người dùng đăng nhập lại.

Token compromise được xử lý tốt khi đội ứng cứu có thể chứng minh ba điều: quyền truy cập bị xâm phạm đã bị chặn, phạm vi ảnh hưởng đã được xác định bằng bằng chứng và luồng xác thực đã được khôi phục mà không tái tạo đường rò rỉ cũ.

