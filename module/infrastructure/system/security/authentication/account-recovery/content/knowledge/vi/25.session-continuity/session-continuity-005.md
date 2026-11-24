# Session invalidation scope — Xác định phạm vi vô hiệu hóa session

## 1. Mục tiêu và phạm vi

Trong chương **Session Continuity** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, vô hiệu hóa session là biện pháp chặn quyền truy cập đã được cấp trước đó. Biện pháp này thường xuất hiện khi người dùng mất thiết bị, thay mật khẩu, đăng ký lại MFA, khôi phục passkey hoặc xử lý tài khoản bị chiếm quyền.

Câu hỏi thiết kế không chỉ là “có đăng xuất hay không”, mà còn gồm:

- Session nào thuộc phạm vi bị ảnh hưởng?
- Những token và quyền nào phát sinh từ các session đó?
- Thành phần nào phải ngừng chấp nhận chúng?
- Quyết định bắt đầu có hiệu lực từ đâu và hoàn tất khi nào?
- Người dùng hợp lệ lấy lại quyền truy cập bằng đường nào?

Thu hồi quá hẹp có thể để đối tượng tiếp tục dùng session hoặc refresh token đã lấy được. Thu hồi quá rộng có thể gây gián đoạn không cần thiết hoặc trở thành công cụ khóa tài khoản nạn nhân.

Bài học tập trung vào **session invalidation scope**: xác định, thực thi và diễn đạt đúng phạm vi thu hồi trong một quy trình khôi phục tài khoản an toàn.

Các tên scope, trạng thái, trường dữ liệu và mã giả trong bài là thiết kế minh họa. Chúng không phải bộ API chuẩn dùng chung cho mọi hệ thống, không tự xác lập mức AAL và cần được điều chỉnh theo kiến trúc cùng chính sách của sản phẩm.

## 2. Session, credential và token là những đối tượng khác nhau

### 2.1. Một credential có thể tạo nhiều session

Credential là phương tiện được dùng để xác thực, chẳng hạn password verifier, binding TOTP hoặc public key WebAuthn. Session là trạng thái tiếp tục truy cập sau một sự kiện xác thực.

NIST mô tả tính liên tục của session dựa trên session secret giữa phần mềm người dùng và dịch vụ. Session có thể tiếp tục mà không trình lại authenticator ở mỗi request. [NIST SP 800-63B-4, Session Bindings](https://pages.nist.gov/800-63-4/sp800-63b/session/#session-bindings)

Vì vậy, thu hồi một credential không tự chứng minh những session được cấp trước đó đã hết hiệu lực.

Ví dụ:

~~~text
Credential C1:
    dùng để xác thực tại thời điểm T1

Session S1:
    được cấp sau lần xác thực đó
    tiếp tục dùng session secret

Thu hồi C1 tại T2:
    chặn xác thực mới bằng C1
    cần quyết định riêng về hiệu lực của S1
~~~

### 2.2. Một session có thể liên quan nhiều loại quyền

~~~mermaid
flowchart TD
    A["Sự kiện xác thực"] --> S["Session logic S1"]
    S --> B["Session ID ở trình duyệt"]
    S --> R["Refresh token family nếu có"]
    R --> T["Access token cho API"]
    S --> W["Kết nối dài đang mở"]
    S --> P["Quyền step-up có thời hạn"]
    S --> C["Context recovery hoặc enrollment nếu được cấp"]
~~~

Sơ đồ thể hiện các quan hệ có thể có. Không phải hệ thống nào cũng có đủ các nhánh, và một OAuth grant không nhất thiết gắn với một browser session.

Phạm vi thu hồi phải dựa trên quan hệ thực tế đã được ghi nhận. Không suy ra mọi API key hoặc mọi grant của người dùng đều là con của session chỉ vì chúng cùng có account ID.

### 2.3. Session logic và session ID có thể không trùng một-một

Một session logic có thể đổi ID qua các lần rotation. Hệ thống cũng có thể chấp nhận ID trước đó trong một khoảng chuyển tiếp được kiểm soát.

Khi quyết định kết thúc session logic, cần xử lý cả các ID còn được chấp nhận của nó, kể cả ID đang được một request gia hạn tạo ra. Chỉ xóa một cookie value có thể bỏ sót đường truy cập khác của cùng session.

OWASP nhấn mạnh thu hồi phía server và xử lý các ID thuộc cùng session logic khi logout. [OWASP, Manual Session Expiration](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#manual-session-expiration)

## 3. Phân biệt vô hiệu hóa, xác thực lại và xóa dữ liệu client

| Hành động | Tác động trực tiếp | Điều chưa được giải quyết |
| --- | --- | --- |
| Vô hiệu hóa session | Server ngừng chấp nhận quyền tiếp tục của session theo cơ chế đã thiết kế | Khả năng đăng nhập lại bằng credential còn hợp lệ |
| Yêu cầu xác thực lại | Một số quyền cần bằng chứng mới trước khi được dùng | Những quyền vẫn được phép trước khi reauthentication |
| Hạ quyền session | Giới hạn tập hành động được phép | Session có thể vẫn tồn tại và đọc được dữ liệu trong phạm vi còn lại |
| Xóa cookie tại client | Browser đó không còn tự gửi cookie đã xóa | Bản sao cookie bị lấy trước đó |
| Thu hồi refresh token | Chặn cấp tiếp token từ đường refresh được xử lý | Access token đã cấp và còn được resource server chấp nhận |
| Thu hồi credential | Chặn các lần xác thực mới bằng credential đó | Session, token và quyền đã phát sinh |
| Xóa dữ liệu cục bộ | Dọn dữ liệu theo khả năng của client | Bản sao đối tượng đã tải ra ngoài hoặc thiết bị không nhận lệnh |

Đối với một session đã có căn cứ bị đánh cắp, “cho dùng tiếp nhưng hỏi MFA khi chuyển tiền” vẫn có thể để lộ dữ liệu đọc được. Nếu quyết định là thu hồi, việc ngừng chấp nhận session cần áp dụng cho toàn bộ quyền thuộc phạm vi đó.

Ngược lại, một chính sách chỉ yêu cầu fresh authentication cho một hành động nhạy cảm có thể không cần kết thúc mọi session. Hai hành vi phải được gọi đúng tên trong thiết kế và giao diện.

## 4. Những phạm vi thu hồi thường gặp

### 4.1. Chọn scope theo đối tượng và ranh giới quyền

| Scope minh họa | Tập đối tượng | Điều kiện cần làm rõ |
| --- | --- | --- |
| `CURRENT_LOGICAL_SESSION` | Session logic của người gọi | Bao gồm ID sau rotation và đường refresh liên quan nào |
| `SELECTED_SESSIONS` | Các session đã chọn theo ID server | Mỗi target phải thuộc phạm vi người gọi có quyền quản lý |
| `CLIENT_INSTANCE_SESSIONS` | Session gắn với một instance ứng dụng đã được nhận diện | Mức tin cậy của binding instance và các bản sao secret |
| `AUTHENTICATION_LINEAGE` | Session thuộc chuỗi xác thực bị ảnh hưởng | Có đủ provenance để chọn đúng hay không |
| `APPLICATION_SESSIONS` | Session tại một ứng dụng hoặc client cụ thể | Issuer, account, tenant và client nào |
| `ACCOUNT_EXISTING_SESSIONS` | Tập session hiện có của account theo ranh giới xác định | Cutoff, revision hoặc epoch dùng để đóng tập nào |
| `OTHER_SESSIONS` | Các session khác một session được phép giữ | Căn cứ tin cậy của session được giữ |
| `TENANT_ACCESS` | Quyền truy cập một tenant | Có cần kết thúc session toàn account hay chỉ chặn tenant đó |
| `FEDERATED_SESSIONS` | Các phiên OP/RP trong liên kết được hỗ trợ | Thành phần tham gia, giao thức và giới hạn thực thi |
| `RECOVERY_CONTEXTS` | Recovery session, capability và enrollment đang mở | Context nào bị đóng, context nào còn quyền giới hạn |

Đây là các trục lựa chọn có thể kết hợp trong quyết định. Một tên scope đơn lẻ chưa mô tả đủ tác động lên cookie, refresh token và access token.

### 4.2. “Thiết bị” cần định nghĩa cụ thể

Một laptop có thể có nhiều profile trình duyệt, ứng dụng native và session độc lập. Ngược lại, cùng một session secret có thể bị sao chép sang môi trường khác.

IP, User-Agent, tên thiết bị hoặc fingerprint chỉ có thể hỗ trợ nhận diện và đánh giá rủi ro. Chúng không tự chứng minh một thiết bị vật lý duy nhất.

Nếu hệ thống chỉ nhóm theo instance do ứng dụng khai, giao diện nên mô tả đúng mức nhận diện đó. Không hứa đã “xóa mọi quyền trên điện thoại” nếu server chỉ thu hồi một session mà người dùng chọn.

### 4.3. Tenant và account là hai ranh giới khác nhau

Một người dùng có thể truy cập nhiều tổ chức bằng cùng tài khoản. Quản trị viên tenant A có thể có quyền ngừng truy cập A nhưng không có quyền đăng xuất toàn bộ tài khoản khỏi tenant B.

Nếu session chứa context của nhiều tenant, việc chặn A cần được thực thi tại kiểm tra quyền cho A. Nó không nhất thiết yêu cầu phá toàn bộ session cá nhân.

Quyền quản trị tenant và quyền xử lý account compromise toàn cục cần được tách rõ ở phía server.

## 5. Chọn phạm vi theo tình huống và bằng chứng

### 5.1. Ma trận quyết định

| Tình huống | Phạm vi cần xem xét | Lý do cần đánh giá |
| --- | --- | --- |
| Người dùng logout trên máy dùng chung | Session logic hiện tại và các đường tiếp tục của nó | Xóa cookie đơn lẻ chưa chặn bản sao secret |
| Mất điện thoại có ứng dụng đang đăng nhập | Session, refresh family và quyền nhận diện được trên instance đó | Credential có thể còn an toàn nhưng session trên máy đã mất |
| Có căn cứ cookie của một session bị lộ | Session logic đó và các hậu duệ của nó | Rotation không loại bỏ sự cố nếu hậu duệ vẫn được chấp nhận |
| Phát hiện refresh token bị tái sử dụng | Refresh family hoặc grant bị ảnh hưởng theo chính sách | Chỉ thu hồi token cũ có thể bỏ sót token mới đã phát hành |
| Đổi mật khẩu theo kế hoạch | Chính sách session sau thay đổi và bằng chứng hiện có | Không tự suy ra mọi phiên đã bị chiếm |
| Recovery sau nghi ngờ account takeover | Tập session và quyền phát sinh có thể bị ảnh hưởng | Chỉ chặn credential cũ có thể để đối tượng tiếp tục truy cập |
| Thay MFA vì thiết bị hỏng, không có dấu hiệu bị lộ | Các session cần reauthentication hoặc thu hồi theo chính sách | Phạm vi có thể khác một sự cố bị đánh cắp |
| Mất khóa rời nhưng client vẫn trong kiểm soát | Credential mất và session liên quan theo đánh giá | Mất authenticator không đồng nghĩa mất cookie trên mọi client |
| Thu hồi tư cách thành viên tổ chức | Quyền tại tenant và token/grant tương ứng | Tránh tác động ngoài quyền quản trị tenant |
| Recovery request chưa được xác minh | Tiếp nhận và hạn chế lạm dụng theo chính sách | Người ngoài không được dùng request để đăng xuất nạn nhân |

Ma trận không phải quy tắc tự động áp dụng cho mọi tài khoản. Với tài khoản đặc quyền hoặc dữ liệu nhạy cảm, chính sách có thể yêu cầu phạm vi rộng hơn dựa trên rủi ro đã xác định.

### 5.2. Cần kiểm tra quyền của hành động thu hồi

Trước khi thực hiện, server cần xác minh:

- Người gọi đang có quyền nào và bằng chứng đó còn hiệu lực không.
- Target thuộc đúng account, tenant và ứng dụng được phép hay không.
- Yêu cầu có thay đổi phạm vi từ một session sang toàn account không.
- Có cần freshness hoặc step-up cho hành động này không.
- Context recovery có thực sự được cấp quyền thu hồi loại session đó không.

Một đường logout session hiện tại có thể dùng kiểm soát khác với đường “đăng xuất mọi nơi”. Không bắt mọi hành động nhỏ đi qua cùng một quy trình nặng, nhưng cũng không để quyền hẹp được diễn giải thành quyền rộng.

Nếu dùng cookie, endpoint có tác động cần chống CSRF phù hợp. Thay account ID, session ID hoặc tenant ID trong request không được chuyển target sang tài khoản khác.

### 5.3. Phân biệt thiếu bằng chứng với thiếu khả năng định vị

Có hai vấn đề khác nhau:

1. Chưa có đủ bằng chứng cho phép thu hồi.
2. Đã có căn cứ sự cố nhưng chưa biết chính xác session nào bị ảnh hưởng.

Vấn đề thứ nhất cần được giải quyết bằng xác minh và quy tắc chống lạm dụng. Vấn đề thứ hai có thể dẫn đến phạm vi rộng hơn hoặc reauthentication theo chính sách, kèm giải thích về mức độ không chắc chắn.

Không dùng việc “không tìm thấy thiết bị” để mặc định mọi session đều an toàn.

## 6. Ghi quyết định thu hồi thành đối tượng có thể kiểm tra

### 6.1. Mô hình quyết định minh họa

~~~text
SessionInvalidationDecision
    decision_id
    account_id
    tenant_context
    actor_reference
    authorization_reference
    recovery_case_reference
    reason_code
    policy_version
    scope_type
    resolved_target_reference
    expected_state_revision
    cutoff_or_epoch
    linked_token_actions
    retained_session_authorization
    effective_requirements
    expires_at
~~~

`resolved_target_reference` có thể trỏ đến tập session đã chốt hoặc một predicate có phiên bản được thực thi tại server. Không cần đưa toàn bộ tập target vào token phía client.

`effective_requirements` ghi rõ điều kiện hoàn tất, chẳng hạn ngừng session store, chặn refresh và có cơ chế kiểm soát access token tại các resource server trong phạm vi.

### 6.2. Chốt phạm vi trước khi tạo tác động

Quyết định nên trả lời được:

~~~text
Đang thu hồi:
    session S1 và các ID còn được chấp nhận của S1
    refresh family F1 liên kết với S1

Đang xử lý riêng:
    access token đã cấp từ F1 theo cơ chế của API

Chưa thuộc quyết định:
    grant độc lập của ứng dụng B
    session của account khác
~~~

Đây là ví dụ làm rõ hợp đồng thực thi. Trong sự cố rộng, quyết định có thể bao gồm nhiều tập đối tượng hơn.

Nếu mở rộng từ S1 sang mọi session sau khi phát hiện thêm bằng chứng, cần cập nhật quyết định hoặc tạo quyết định mới có thẩm quyền. Không để worker xử lý sự kiện tự mở rộng tác động ngoài scope.

### 6.3. Target cần ổn định qua retry

Một request “thu hồi mọi session đang có” phải xác định “đang có” ở thời điểm nào. Nếu mỗi retry lại truy vấn tất cả session hiện tại, nó có thể thu hồi cả session mới người dùng vừa tạo sau recovery.

Có thể dùng:

- Tập session ID được chốt cùng revision.
- Epoch để ngừng các session thuộc thế hệ cũ.
- Cutoff có semantics được định nghĩa và thực thi nhất quán.

Không chỉ dựa vào thời gian trên client để xác định ranh giới bảo mật.

## 7. Thực thi với session store và access token

### 7.1. Session phía server

Một session store có thể giữ trạng thái active/revoked hoặc các version cần thiết để verifier quyết định.

~~~text
authorizeRequest(request):
    xác minh session secret theo cơ chế hệ thống
    đọc session logic và trạng thái có thẩm quyền
    kiểm tra account, tenant, thời hạn và trạng thái thu hồi
    kiểm tra version hoặc epoch áp dụng
    kiểm tra quyền cho hành động cụ thể

    nếu không đáp ứng:
        từ chối
    nếu đáp ứng:
        tiếp tục theo phạm vi được phép
~~~

Đoạn mã giả không thay thế kiểm tra giao thức và triển khai lưu bí mật. Nó nhấn mạnh rằng một secret có định dạng đúng vẫn có thể thuộc session đã bị thu hồi.

Nếu dùng cache session, việc đọc cache phải tuân theo độ mới và cơ chế invalidation đã thiết kế. Cập nhật database nhưng chấp nhận cache cũ vô thời hạn không thực thi được quyết định.

### 7.2. Access token tự chứa

Một resource server chỉ kiểm tra chữ ký, issuer, audience và thời hạn của JWT có thể tiếp tục chấp nhận token chưa hết hạn dù session gốc đã bị thu hồi.

Hệ thống cần lựa chọn cơ chế phù hợp, chẳng hạn:

- Tra trạng thái session hoặc token ở thời điểm quyết định quyền.
- Kiểm tra epoch/version qua nguồn trạng thái tin cậy.
- Dùng danh sách thu hồi có phạm vi và thời hạn quản lý được.
- Chấp nhận một cửa sổ còn hiệu lực bị giới hạn bởi expiry, nếu chính sách cho phép.

Thêm trường epoch vào JWT chỉ có ích cho thu hồi nếu verifier thực sự đối chiếu nó với trạng thái mới. Một claim đứng riêng trong token không tự biết account đã chuyển epoch.

### 7.3. Token introspection và cache

RFC 7662 cung cấp cơ chế để resource server được phép hỏi trạng thái active cùng metadata của token. Nếu kết quả được cache, khả năng nhận biết thu hồi còn phụ thuộc chính sách cache. [RFC 7662, OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)

Do đó, cần xác định thời gian cache tối đa, cách nhận sự kiện và hành vi khi dịch vụ trạng thái không khả dụng. Một cache entry từng hợp lệ không phải bằng chứng token vẫn còn hợp lệ vô thời hạn.

Với thao tác cần chặn ngay theo quyết định sự cố, kiến trúc phải có đường kiểm tra đủ mới hoặc biện pháp từ chối phù hợp. Không dùng lỗi đọc trạng thái để âm thầm bỏ kiểm tra bảo mật bắt buộc.

### 7.4. Thu hồi token không đồng nghĩa mọi lớp đã hoàn tất

RFC 7009 mô tả endpoint revocation và lưu ý có thể có độ trễ lan truyền trong thực tế. HTTP 200 cũng được dùng khi token gửi lên không còn hợp lệ. [RFC 7009, Token Revocation và Revocation Response](https://www.rfc-editor.org/rfc/rfc7009.html)

Vì vậy, một response thành công từ endpoint không tự chứng minh:

- Đúng mọi token family đã nằm trong phạm vi.
- Mọi resource server đã cập nhật trạng thái.
- Session riêng của các ứng dụng đã bị ngừng.
- Không còn grant độc lập có thể cấp token mới.

Những điều đó cần được kiểm tra theo kiến trúc và hợp đồng thực thi của hệ thống.

## 8. Refresh token family và các đường cấp lại

### 8.1. Chặn tiếp tục cấp quyền, không chỉ token đang nhìn thấy

Giả sử một refresh family F1 đã phát hành:

~~~text
RT1 -> RT2 -> RT3
                 -> AT3
~~~

Nếu RT3 đang là token hiện tại, chỉ thu hồi RT1 có thể không ngăn được đường refresh đang hoạt động. Phạm vi cần dựa trên family, grant hoặc quan hệ trạng thái mà authorization server thực sự duy trì.

RFC 9700 mô tả rotation có giữ quan hệ giữa refresh token để phát hiện replay; khi phát hiện sự cố, authorization server không thể tự biết bên dùng lại là chủ hợp lệ hay đối tượng tấn công. [RFC 9700, Refresh Token Protection](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14)

Trong thiết kế ứng dụng, quyết định có thể cần vô hiệu hóa family bị ảnh hưởng và yêu cầu một authorization mới. Không mặc định đó là thu hồi mọi grant của account.

### 8.2. Refresh không được tạo thế hệ an toàn từ nguồn đã thu hồi

Một lỗi thiết kế:

~~~text
Nhận refresh token từ family cũ
Đọc epoch mới nhất của account
Phát token mới mang epoch mới
~~~

Nếu không kiểm tra trạng thái family và epoch gốc, thao tác này có thể làm session cũ vượt qua ranh giới thu hồi.

Đường refresh cần xác minh quyền nguồn còn hiệu lực trước khi phát token. Token hậu duệ phải giữ quan hệ đúng với session hoặc grant nguồn theo mô hình đã chọn.

### 8.3. Có thể còn đường đăng nhập im lặng

Sau khi thu hồi session ứng dụng, browser có thể còn phiên tại nhà cung cấp danh tính hoặc một cơ chế “ghi nhớ thiết bị”. Khi ứng dụng yêu cầu đăng nhập lại, các đường đó có thể tạo session mới.

Nếu mục tiêu là ngăn truy cập từ thiết bị bị mất, cần xem xét cả những đường cấp lại này. Chỉ chuyển người dùng về màn hình login không bảo đảm đối tượng phải trình bằng chứng mới đáng tin.

Yêu cầu fresh authentication, thu hồi remembered-device grant hoặc xử lý phiên SSO cần được quyết định theo phạm vi và khả năng thực tế.

## 9. Ranh giới thời gian, epoch và thao tác đồng thời

### 9.1. “Tất cả session” cần có semantics về thời điểm

Hai mục tiêu khác nhau:

1. Kết thúc mọi session tồn tại trước quyết định.
2. Ngăn mọi lần cấp session mới cho đến khi một điều kiện bảo mật được đáp ứng.

Mục tiêu thứ nhất là thu hồi một tập đã xác định. Mục tiêu thứ hai còn cần kiểm soát cấp quyền mới, chẳng hạn trạng thái tạm ngừng đăng nhập hoặc điều kiện recovery bắt buộc.

Nếu credential của đối tượng vẫn được chấp nhận, thu hồi toàn bộ session hiện có có thể chỉ làm đối tượng đăng nhập lại. Chính sách sự cố cần phối hợp việc chặn đường xác thực không còn tin cậy.

### 9.2. Epoch toàn account là một cách thực thi

Ví dụ hệ thống có `account_session_epoch`:

~~~text
Trước quyết định:
    account epoch = 7
    S1 epoch = 7
    S2 epoch = 7

Commit thu hồi toàn bộ session thế hệ cũ:
    account epoch = 8

Verifier có kiểm tra trạng thái mới:
    S1 và S2 không còn đáp ứng epoch

Session mới S3:
    chỉ được cấp epoch 8 sau khi điều kiện cấp mới được đáp ứng
~~~

Epoch chỉ thực thi được tại những nơi đối chiếu nó với nguồn trạng thái đủ tin cậy. Với token chỉ được xác minh ngoại tuyến, claim epoch cũ không tự bị từ chối nếu verifier không có thông tin epoch mới.

Một scope hẹp như thu hồi S1 không nên dùng tăng epoch toàn account nếu hệ thống muốn giữ S2. Có thể dùng trạng thái session riêng, family version hoặc một cấu trúc thu hồi phù hợp hơn.

Quyền tại tenant cũng có thể cần version riêng. Không dùng một epoch toàn account cho mọi thay đổi tenant rồi gây tác động ngoài ý định.

### 9.3. Cutoff không nên dựa vào thời điểm token vừa được mint

Một access token được mint lúc 10:05 có thể xuất phát từ refresh family đã được cấp lúc 09:00. Nếu cutoff thu hồi là 10:00, chỉ nhìn `iat=10:05` có thể bỏ lọt hậu duệ của quyền cũ.

Cần kiểm tra quan hệ cấp quyền gốc, session generation hoặc epoch theo mô hình thực tế. Nếu dùng thời điểm xác thực như một phần quyết định, cần bảo đảm trường đó có nguồn đáng tin và semantics phù hợp.

Không giả định mọi loại token đều có cùng bộ claim hoặc cùng cách biểu diễn thời điểm xác thực.

### 9.4. Cạnh tranh giữa refresh và thu hồi

~~~text
Request A:
    muốn refresh từ family F1

Request B:
    muốn thu hồi F1

Yêu cầu:
    không được để quyền nguồn đã bị thu hồi
    phát hành hậu duệ được coi là thế hệ mới hợp lệ
~~~

Điểm quyết định cấp token và điểm quyết định thu hồi cần được phối hợp bằng trạng thái có thẩm quyền, transaction hoặc cơ chế tương đương của kiến trúc.

Nếu refresh đã hoàn tất trước ranh giới thu hồi, token hậu duệ cần thuộc tập bị xử lý theo quyết định. Nếu refresh đến sau ranh giới, nguồn đã bị thu hồi phải bị từ chối.

Các cơ chế rotation, ghi session cuối request và gia hạn tự động đều phải giữ bất biến này. Một request đọc session active từ trước không được ghi nó trở lại active sau khi request khác đã thu hồi.

### 9.5. Retry không được tăng epoch thêm lần nữa

Giả sử decision D1 đã chuyển epoch 7 sang 8, rồi người dùng đăng nhập thành công và nhận S3 ở epoch 8.

Nếu retry D1 lại tăng epoch lên 9, S3 có thể bị thu hồi ngoài phạm vi ban đầu. Vì vậy, D1 cần có kết quả bền vững và việc áp dụng lặp phải trả kết quả cũ.

Idempotency không chỉ tránh gửi hai thông báo. Nó còn giữ ổn định tập session và ranh giới thu hồi đã được cấp quyền.

## 10. Commit quyết định và lan truyền trong hệ thống phân tán

### 10.1. Transaction phía nguồn có thẩm quyền

~~~text
BEGIN

Kiểm tra quyền caller đối với decision và phạm vi target
Kiểm tra kết quả idempotency đã được lưu hay chưa
Nếu đã hoàn tất cùng yêu cầu:
    trả kết quả đã lưu theo quyền được phép xem

Khóa hoặc kiểm tra version của đối tượng phạm vi
Đối chiếu account, tenant, policy và expected revision
Áp dụng target set hoặc chuyển epoch theo quyết định
Ngừng các session/family/grant thuộc phạm vi được quản lý tại đây
Đóng các capability liên quan theo scope riêng
Ghi decision result, audit và outbox

COMMIT
~~~

Đây là transaction tại thành phần quản lý được những đối tượng trên. Nếu session store, authorization server và các RP thuộc những miền giao dịch khác nhau, không được giả định tất cả có một transaction database chung.

Khi đó, quyết định bền vững cần dẫn dắt các bước thực thi ở từng nơi, với retry, trạng thái kết quả và cơ chế xử lý lỗi riêng.

### 10.2. Tách các mức hoàn tất

| Trạng thái minh họa | Ý nghĩa |
| --- | --- |
| `RECORDED` | Quyết định đã được ghi bền vững tại nguồn có thẩm quyền |
| `PROPAGATING` | Một số thành phần trong phạm vi còn đang áp dụng |
| `EFFECTIVE_FOR_SCOPE` | Các điều kiện hiệu lực đã công bố cho scope đều được đáp ứng |
| `NEEDS_ATTENTION` | Có thành phần hoặc điều kiện không hoàn tất như yêu cầu |

`RECORDED` không được hiển thị thành “đã kết thúc mọi quyền truy cập” nếu các resource server còn chấp nhận token cũ.

Điều kiện của `EFFECTIVE_FOR_SCOPE` cần được định nghĩa trước, chẳng hạn session store đã chặn, refresh đã ngừng và access token trong phạm vi đã bị từ chối hoặc hết cửa sổ hiệu lực được chính sách cho phép.

Không đổi nghĩa scope sau khi gặp lỗi để đánh dấu hoàn tất. Nếu có giới hạn đã biết, chúng cần được công bố trong kế hoạch và kết quả.

### 10.3. Sự kiện cần có thứ tự logic

Một sự kiện minh họa:

~~~text
event_id
decision_id
account_reference
tenant_context
scope_reference
revocation_revision
effective_boundary
issued_at
~~~

Consumer cần xác thực nguồn sự kiện, xử lý lặp an toàn và không để revision cũ ghi đè revision mới.

Việc nhận được message chưa đồng nghĩa mọi request đã bị chặn. Consumer cần áp dụng trạng thái tại đúng điểm quyết định quyền; acknowledgement nên phản ánh bước mà hợp đồng yêu cầu.

Đối tượng đã revoked cũng không được chuyển về active do một bản cập nhật “last seen” hoặc sự kiện rotation đến muộn.

### 10.4. Mô tả cửa sổ còn hiệu lực

Ví dụ minh họa:

~~~text
12:00:00  Thu hồi family tại authorization server
12:00:00  Access token A còn hạn đến 12:04:00
12:00:00  API X chỉ kiểm tra chữ ký và expiry
12:00:00  API Y kiểm tra trạng thái thu hồi online
~~~

API Y có thể chặn theo trạng thái mới khi kiểm tra thành công. API X có thể còn chấp nhận A đến expiry và sai lệch đồng hồ được phép nếu không có cơ chế khác.

Đây là phân tích cho token A với giả định expiry được thực thi đúng. Nó không phải giới hạn toàn hệ thống nếu vẫn còn một đường cấp token mới từ nguồn bị ảnh hưởng.

TTL ngắn giúp giới hạn một số cửa sổ nhưng không thay thế việc chặn refresh và những đường cấp lại cần thu hồi.

### 10.5. Chính sách khi thành phần xác minh không khả dụng

Hành vi cần được chọn theo tài nguyên và yêu cầu:

- Thao tác nhạy cảm có thể cần từ chối hoặc chờ khi không kiểm tra được trạng thái bắt buộc.
- Một quyền ít nhạy cảm hơn chỉ có thể dùng trạng thái cache nếu chính sách đã cho phép với giới hạn rõ.
- Sự kiện lỗi cần được theo dõi và xử lý lại.

Không để exception đọc revocation state trở thành nhánh mặc định “coi session hợp lệ”. Cũng không cần biến mọi lỗi mạng thành một tuyên bố đã thu hồi thành công.

## 11. Giữ tính liên tục cho người dùng đang recovery

### 11.1. Context recovery có quyền riêng

Recovery session có thể cho phép tiếp tục xác minh hoặc đăng ký credential thay thế. Nó cần có mục đích, thời hạn và scope riêng, không phải session ứng dụng đầy đủ.

Khi thu hồi toàn bộ session cũ, hệ thống cần quyết định rõ context recovery nào còn được dùng. Không sao chép quyền của một session cũ bị nghi chiếm sang context mới chỉ để giữ giao diện đang mở.

Một recovery capability còn hiệu lực có thể tiếp tục cho một operation cụ thể nếu chính sách cho phép. Điều đó không khiến cookie ứng dụng cũ tiếp tục được chấp nhận.

### 11.2. Cấp session mới sau ranh giới thu hồi

Luồng minh họa:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant R as Dịch vụ recovery
    participant A as Nguồn session có thẩm quyền
    participant V as Verifier ứng dụng
    U->>R: Hoàn tất bằng chứng recovery được hỗ trợ
    R->>A: Yêu cầu thu hồi theo decision
    A->>A: Ghi ranh giới thu hồi và chặn nguồn cấp cũ
    A-->>R: Kết quả và trạng thái thực thi
    U->>R: Đáp ứng điều kiện cấp session mới
    R->>A: Cấp session mới trong thế hệ được phép
    A-->>U: Session secret mới
    U->>V: Truy cập bằng session mới
    V->>V: Kiểm tra scope, trạng thái và quyền
~~~

Luồng này không yêu cầu hệ thống luôn cấp session ứng dụng ngay sau recovery. Sản phẩm có thể yêu cầu đăng nhập bình thường bằng phương tiện vừa được kích hoạt.

Nếu cấp session mới, cần kiểm tra đầy đủ các điều kiện tương ứng và chống session fixation. Không tái sử dụng secret cũ đã nằm trong phạm vi thu hồi.

### 11.3. “Giữ phiên hiện tại” cần căn cứ tin cậy

Người dùng có thể muốn đăng xuất các nơi khác và tiếp tục phiên đang thao tác. Tuy nhiên, chính phiên đó cũng có thể là phiên đối tượng đã chiếm.

Phạm vi ngoại lệ cần dựa trên bằng chứng được chấp nhận và đúng session. Chỉ vì một request gọi endpoint thu hồi không tự làm session của request ấy trở nên đáng tin.

Nếu thiết kế giữ quyền sau một quyết định epoch rộng, cần có cơ chế rõ để cấp phiên mới hoặc giữ một phiên được xác thực riêng. Không dùng ngoại lệ tổng quát “mọi session có ID bằng caller đều bỏ qua epoch”.

Việc đăng ký passkey mới cũng không tự nâng session recovery thành session có mọi mức quyền. Thuộc tính xác thực cần phản ánh sự kiện thực sự đã đáp ứng.

## 12. SSO, phiên liên kết và phạm vi tại nhiều tenant

### 12.1. Logout tại một RP có thể chỉ là logout cục bộ

Trong SSO, có thể tồn tại:

~~~text
Session tại OpenID Provider:
    OP-S1

Session ứng dụng A:
    RP-A-S1

Session ứng dụng B:
    RP-B-S1

OAuth grant độc lập:
    G1
~~~

Xóa RP-A-S1 không tự chứng minh OP-S1, RP-B-S1 và G1 đều bị thu hồi.

Nếu OP-S1 vẫn hoạt động, một yêu cầu xác thực mới từ A có thể tạo lại phiên tại A theo chính sách OP. Vì vậy, scope “đăng xuất ứng dụng A” khác scope “xử lý quyền truy cập SSO bị chiếm”.

### 12.2. Back-channel logout cần mapping đúng

OpenID Connect Back-Channel Logout dùng Logout Token để RP xác định session theo issuer cùng `sid` và/hoặc `sub`. RP phải xác minh token theo đặc tả trước khi thực hiện logout; `sid` có phạm vi theo issuer. [OpenID Connect Back-Channel Logout, Token Validation và Logout Actions](https://openid.net/specs/openid-connect-backchannel-1_0.html#Validation)

Triển khai cần giữ mapping từ danh tính liên kết đến session cục bộ. Không dùng một `sub` trần hoặc một `sid` trần làm khóa toàn cục xuyên mọi issuer.

Một message logout đúng cần dẫn tới việc session local không còn được chấp nhận. Nó không chỉ là yêu cầu browser đổi trang.

### 12.3. Tính bao phủ phụ thuộc các thành phần tham gia

Kế hoạch thu hồi liên kết cần nêu rõ:

- OP nào phát và xác nhận thông báo.
- RP nào hỗ trợ giao thức tương ứng.
- Session hoặc subject nào được chọn.
- Thành phần nào đã thực thi và thành phần nào chưa phản hồi.
- Token hoặc offline grant nào cần một quyết định OAuth riêng.

Không coi mọi grant truy cập nền là session browser. Một chính sách sự cố có thể thu hồi chúng, nhưng phải có thẩm quyền và cơ chế thực thi cho loại quyền đó.

Nếu một RP không tham gia hoặc không nhận được yêu cầu, hệ thống cần hiển thị và xử lý giới hạn này. Không hứa đã đăng xuất mọi ứng dụng chỉ từ một response thành công của OP.

### 12.4. Tách rời phạm vi tenant khi có danh tính dùng chung

Một account có thể còn quyền cá nhân và quyền ở tenant B sau khi tenant A thu hồi tư cách thành viên. API cần kiểm tra tenant authorization hiện tại ở thời điểm truy cập.

Nếu hệ thống dùng token có role cũ nhưng không kiểm tra thay đổi membership, logout giao diện A chưa giải quyết việc token tiếp tục gọi API của A.

Ngược lại, quản trị viên A không được chọn scope toàn account nếu họ chỉ được quản lý membership tại A. Đây là kiểm soát phạm vi quyền, không phải một tùy chọn trình bày của giao diện.

## 13. Kết nối dài, request đang chạy và công việc nền

### 13.1. WebSocket hoặc stream có thể tồn tại sau lần kiểm tra ban đầu

Một kết nối đã được xác thực khi mở có thể tiếp tục nhận dữ liệu sau khi session bị thu hồi nếu server không kiểm tra lại hoặc không đóng kết nối.

Phạm vi cần bao gồm các connection được gắn với session bị ảnh hưởng, với cơ chế phù hợp như:

- Đóng hoặc hạ quyền connection khi nhận sự kiện.
- Kiểm tra trạng thái ở những điểm trao đổi cần thiết.
- Giới hạn thời gian giữa các lần kiểm tra theo chính sách.
- Ngăn một reconnect dùng lại nguồn session đã bị thu hồi.

Việc đóng socket ở một node không tự chặn request HTTP hoặc connection khác dùng cùng quyền. Cần thực thi ở các điểm truy cập thuộc scope.

### 13.2. Request đã qua bước kiểm tra có thể đang chuẩn bị commit

Ví dụ:

~~~text
T1: Request chuyển quyền quản trị kiểm tra session active
T2: Quyết định thu hồi session được commit
T3: Request ở T1 chuẩn bị ghi thay đổi
~~~

Nếu sản phẩm yêu cầu ngăn commit sau ranh giới T2, chỉ kiểm tra session ở đầu request là chưa đủ. Cần phối hợp trạng thái quyền với điểm commit bằng transaction, version fence hoặc cơ chế phù hợp.

Một lần kiểm tra lại cũng cần tính đến cạnh tranh giữa kiểm tra và ghi. Không hứa tính nguyên tử nếu hai thao tác vẫn có khoảng hở ngoài cơ chế nhất quán.

Không phải mọi request đều cần cùng một cơ chế nặng. Điều kiện cần dựa vào tác động, nhưng cam kết hiệu lực phải phản ánh đúng hành vi.

### 13.3. Công việc nền không luôn là session còn sống

Một tác vụ có thể đã được chấp thuận và chạy bằng service identity riêng. Logout người khởi tạo không tự xác định tác vụ đó phải dừng.

Thiết kế cần phân loại:

| Loại hoạt động | Câu hỏi về thu hồi |
| --- | --- |
| Tác vụ tiếp tục đại diện quyền người dùng | Có cần kiểm tra lại quyền hoặc capability trước mỗi tác động không |
| Tác vụ đã được chấp thuận thành giao dịch nghiệp vụ | Chính sách hủy, bù trừ hoặc hoàn tất là gì |
| Job quản trị chạy bằng service identity | Có thuộc quyết định session người dùng không |
| Download URL hoặc link chia sẻ đã phát hành | Có cơ chế thu hồi riêng hay còn hiệu lực đến expiry |
| API key hoặc app password | Có cần quyết định thu hồi credential riêng không |

Mục tiêu là xử lý đúng quyền liên quan. Không suy ra mọi công việc của account đều phải hủy, cũng không mặc định tất cả đều không bị ảnh hưởng.

### 13.4. Giới hạn với dữ liệu đã ra ngoài

Vô hiệu hóa session ngăn quyền truy cập tiếp theo theo cơ chế thực thi. Nó không lấy lại được dữ liệu đã tải xuống, bản chụp màn hình hoặc bí mật đã xuất ra ngoài.

Dọn cache phía client và chính sách lưu dữ liệu có ích, nhưng không bảo đảm xóa dữ liệu trên một thiết bị không còn trong kiểm soát.

## 14. API, giao diện và khả năng quan sát

### 14.1. Endpoint minh họa

| Endpoint | Mục đích | Điều kiện cần kiểm tra |
| --- | --- | --- |
| `GET /security/sessions` | Xem session được phép quản lý | Account, tenant, quyền xem và dữ liệu hiển thị |
| `POST /security/session-invalidations` | Yêu cầu áp dụng scope | Scope được cho phép, target, bằng chứng và revision |
| `GET /security/session-invalidations/{id}` | Xem tiến độ của quyết định | Quyền với đúng decision |

Server chỉ nhận các selector được hỗ trợ; không chấp nhận một predicate tùy ý từ client để truy vấn hoặc thu hồi session.

Idempotency key cần có phạm vi account, hành động và nội dung quyết định. Nếu cùng key nhưng target hoặc scope khác, server phải phát hiện xung đột.

Endpoint đọc không được gây thu hồi. Trước khi có quyền, phản hồi không nên làm lộ danh sách thiết bị, lịch sử đăng nhập hoặc sự tồn tại của account chỉ từ một tên đăng nhập.

### 14.2. Giao diện cần mô tả hành động cụ thể

| Cách diễn đạt dễ gây hiểu lầm | Cách diễn đạt chính xác hơn |
| --- | --- |
| “Xóa thiết bị” | “Kết thúc các phiên đã xác định của ứng dụng trên thiết bị này” |
| “Đổi mật khẩu là đăng xuất hết” | “Các phiên được xử lý theo chính sách hiển thị sau khi đổi mật khẩu” |
| “Đã đăng xuất mọi nơi” ngay khi ghi database | “Đã chặn cấp tiếp và đang áp dụng thu hồi tại các dịch vụ trong phạm vi” |
| “Khóa mất đã bị xóa nên mọi quyền đã hết” | “Credential đã bị thu hồi; các phiên và token liên quan được xử lý riêng” |
| “Phiên hiện tại luôn được giữ” | “Chỉ giữ hoặc cấp lại phiên đáp ứng điều kiện xác thực và chính sách” |

Giao diện không cần đưa toàn bộ chi tiết giao thức cho người dùng. Nó cần nêu đúng những phiên bị ảnh hưởng, khả năng phải đăng nhập lại và giới hạn có tác động thực tế.

Nếu một phần đang chờ, trạng thái nên có khả năng cập nhật và hướng xử lý. Không chuyển lỗi lan truyền thành thông báo hoàn tất chung.

### 14.3. Nhật ký cần hỗ trợ giải thích phạm vi

Một audit record hữu ích có thể gồm:

~~~text
decision_id
actor_reference
authorization_reference
account_reference
tenant_context
reason_code
policy_version
scope_type
target_set_reference
previous_revision
new_revision
recorded_at
effective_state
pending_components
~~~

Không ghi session cookie, access token hoặc refresh token thô. Dùng reference nội bộ hoặc biểu diễn an toàn phù hợp cho tra cứu.

Metric có thể theo dõi thời gian từ recorded đến hiệu lực theo scope, số consumer chưa áp dụng, request dùng session đã revoked và lỗi cấp token sau ranh giới thu hồi.

Một metric đếm “đã gửi sự kiện” không thay thế bằng chứng verifier đã thực thi trạng thái mới.

### 14.4. Thông báo và quyền phản đối

Thông báo nên giải thích thay đổi nào đã được yêu cầu và cách báo nếu người dùng không thực hiện. Kênh gửi phải được chọn theo chính sách và tình trạng sự cố.

Không gửi bí mật session trong thông báo. Một link phản đối hoặc khôi phục cũng cần quyền, thời hạn và khả năng chống lạm dụng riêng; chỉ biết decision ID không đủ để đảo ngược thu hồi.

Đặc biệt, người ngoài không được làm session đã thu hồi sống lại bằng một request “hủy logout”.

## 15. Ví dụ áp dụng

### 15.1. Mất điện thoại nhưng laptop còn tin cậy

Minh mất điện thoại có session S1 và refresh family F1. Laptop còn session S2, nhưng Minh vẫn cần đáp ứng chính sách quản lý session trước khi thu hồi.

Một quyết định có thể chọn:

1. Thu hồi S1 cùng các ID còn được chấp nhận của session logic đó.
2. Chặn refresh từ F1 và xử lý token hậu duệ.
3. Đóng connection liên quan tại các dịch vụ trong phạm vi.
4. Kiểm tra đường remembered-device hoặc SSO có thể cấp lại trên điện thoại.
5. Giữ hoặc cấp lại quyền trên laptop theo bằng chứng và chính sách.

Nếu không đủ dữ liệu để nhận diện toàn bộ session của điện thoại, hệ thống cần phản ánh độ không chắc chắn và áp dụng phạm vi được chính sách cho phép.

Xóa một mục “điện thoại” trong giao diện không tự chứng minh cả năm bước đã hoàn tất.

### 15.2. Recovery sau nghi account takeover

Lan mất quyền với email và MFA; sau đó xuất hiện những session không do Lan nhận diện. Quy trình recovery chấp nhận bằng chứng theo chính sách và cấp quyền xử lý sự cố.

Phạm vi có thể rộng hơn một thiết bị:

- Thu hồi các session cũ theo ranh giới đã chốt.
- Chặn refresh family và grant bị ảnh hưởng.
- Xử lý credential hoặc kênh recovery không còn tin cậy theo quyền riêng.
- Kiểm tra quyền mới được tạo trong thời gian bị chiếm.
- Cấp session mới chỉ khi điều kiện đã được đáp ứng.

Quyết định thu hồi cần có idempotency để retry không làm mất session mới của Lan. Context recovery không được trở thành ngoại lệ cho mọi token cũ của account.

Một API chỉ xác minh JWT ngoại tuyến vẫn cần được tính vào kế hoạch hiệu lực; không được tuyên bố mọi truy cập đã bị chặn từ lúc tăng epoch.

### 15.3. Thu hồi một tenant trong hệ thống SSO

Hà dùng cùng account ở tenant A và B. Quản trị viên A cần chấm dứt quyền của Hà tại A.

Phạm vi phù hợp có thể là membership và quyền truy cập A, cùng những session hoặc token dành riêng cho A theo kiến trúc. Session cá nhân hoặc quyền tại B không tự nằm trong thẩm quyền quản trị A.

Nếu token cũ còn chứa role A, các API của A cần có cơ chế nhận biết thay đổi quyền. Chỉ ẩn menu A sau khi refresh trang chưa đủ.

Một sự cố account compromise toàn cục sẽ cần quyết định khác, với thẩm quyền rộng hơn.

## 16. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Client xóa cookie nhưng bản sao còn bị trình | Server từ chối nếu session đã bị thu hồi |
| Session logic có ID cũ và ID mới sau rotation | Các ID còn được chấp nhận đều thuộc phạm vi xử lý |
| Thu hồi một session được chọn | Không tác động session độc lập ngoài target nếu không được cấp quyền |
| Đổi target ID sang account khác | Bị từ chối theo kiểm soát quyền |
| Admin tenant A yêu cầu thu hồi toàn account | Không tự vượt phạm vi quản trị A |
| Recovery request chưa được xác minh | Không được dùng để đăng xuất nạn nhân tùy ý |
| Credential bị thu hồi nhưng session cũ còn tồn tại | Áp dụng quyết định session riêng, không mặc định đã hết hiệu lực |
| Thu hồi refresh token cũ nhưng family có hậu duệ | Xử lý đúng family/grant bị ảnh hưởng |
| Refresh chạy đồng thời với thu hồi | Nguồn cũ không tạo được hậu duệ vượt ranh giới |
| Session-save đến muộn sau logout | Không ghi session trở lại active |
| JWT còn hạn tại API chỉ xác minh ngoại tuyến | Phản ánh cửa sổ thực tế hoặc bổ sung cơ chế kiểm tra cần thiết |
| JWT có epoch nhưng verifier không tra epoch hiện tại | Không coi claim đứng riêng là cơ chế thu hồi hiệu quả |
| Token mới có iat sau cutoff nhưng xuất phát từ grant cũ | Kiểm tra đúng chuỗi cấp quyền và ranh giới gốc |
| Consumer nhận cùng decision nhiều lần | Không mở rộng target hoặc tăng epoch lần nữa |
| Sự kiện revision cũ đến muộn | Không ghi đè trạng thái mới |
| Retry decision cũ sau khi có session recovery mới | Không thu hồi session mới ngoài phạm vi ban đầu |
| Caller chọn giữ phiên hiện tại | Cần đáp ứng điều kiện giữ hoặc cấp mới, không tự miễn kiểm tra |
| Session bị thu hồi vẫn có WebSocket đang mở | Xử lý connection theo cam kết hiệu lực |
| Request nhạy cảm qua kiểm tra trước cutoff nhưng chưa commit | Thực thi ranh giới tại điểm cần thiết theo thiết kế nhất quán |
| Logout RP A nhưng session OP vẫn còn | Không tuyên bố đã thu hồi toàn bộ SSO |
| Logout Token sai issuer, audience hoặc loại sự kiện | Bị từ chối theo verifier giao thức |
| Hai issuer có sid hoặc sub giống nhau | Không nhầm mapping session giữa các issuer |
| Một RP không phản hồi back-channel | Trạng thái thể hiện phần chưa hoàn tất |
| Offline grant không thuộc browser session | Có quyết định và cơ chế riêng nếu cần thu hồi |
| Introspection hoặc kho trạng thái đang lỗi | Hành vi theo chính sách đã chọn, không âm thầm bỏ kiểm tra bắt buộc |
| Job nền có service identity riêng | Phân loại quyền và tác động, không hủy hay giữ mặc định chỉ từ account ID |
| Dữ liệu đã được tải trước thu hồi | Không hứa có thể xóa bản sao ngoài kiểm soát |
| Log và thông báo được kiểm tra | Không chứa secret session hoặc token thô |

## 17. Những điểm cần ghi nhớ

- Phạm vi vô hiệu hóa phải chỉ rõ đối tượng, quyền phát sinh, thành phần thực thi và ranh giới hiệu lực.
- Credential, session logic, session ID, refresh family và access token có vòng đời riêng.
- “Thiết bị”, “mọi phiên”, “mọi nơi” và “phiên khác” cần được định nghĩa bằng dữ liệu cùng quyền server có thể kiểm tra.
- Chặn session cũ cần đi cùng xem xét các đường cấp lại; refresh hoặc SSO còn hoạt động có thể tạo quyền mới.
- Cutoff và epoch phải giữ đúng quan hệ cấp quyền, chịu được cạnh tranh và không đổi nghĩa qua retry.
- Ghi quyết định bền vững khác với thu hồi đã có hiệu lực tại mọi thành phần thuộc phạm vi.
- Recovery có thể cần một context giới hạn để người dùng tiếp tục; context đó không phục hồi quyền của secret cũ.
- Một kết quả an toàn vừa chặn quyền bị ảnh hưởng, vừa phản ánh trung thực các giới hạn và đường truy cập còn hợp lệ.
