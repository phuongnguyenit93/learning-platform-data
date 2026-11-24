# Authentication failure: phân loại, điều tra và xử lý lỗi xác thực trong IAM lifecycle

**Authentication failure** (lỗi hoặc kết quả xác thực không thành công) xảy ra khi một yêu cầu xác thực không tạo ra được bằng chứng đăng nhập hợp lệ, hoặc một hệ thống không chấp nhận bằng chứng xác thực được trình bày. Trong IAM, đây là một chủ đề vừa liên quan đến **trải nghiệm đăng nhập**, vừa liên quan đến **khả năng phát hiện tấn công**, **tính sẵn sàng của dịch vụ**, và **trạng thái vòng đời danh tính**.

Ví dụ, người dùng nhập sai mật khẩu; một nhân viên mới chưa hoàn tất đăng ký MFA; ứng dụng không tin cậy SAML assertion do cấu hình sai; tài khoản đã bị disable khi nghỉ việc; hoặc Identity Provider (IdP) tạm thời không phản hồi. Những trường hợp này đều có thể khiến người dùng không đăng nhập được, nhưng **nguyên nhân, mức rủi ro và cách xử lý hoàn toàn khác nhau**.

Bài học nằm trong chương **Authentication** của module quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**. Nội dung liên kết xác thực với IdP, SSO, OIDC/SAML, MFA, provisioning qua SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và yêu cầu giảm quyền truy cập tồn dư. Mục tiêu là biết **nhận diện đúng lớp lỗi, bảo vệ hệ thống khi có thất bại, điều tra bằng bằng chứng và khôi phục quyền truy cập hợp lệ mà không mở ra đường vượt kiểm soát**.

## 1. Authentication failure là gì?

**Authentication (AuthN)** trả lời câu hỏi: *“Chủ thể đang yêu cầu truy cập có chứng minh được danh tính hoặc sở hữu yếu tố xác thực được chấp nhận không?”* **Authorization (AuthZ)** trả lời câu hỏi tiếp theo: *“Chủ thể đã được nhận diện có được phép thực hiện hành động này trên tài nguyên này không?”*

Một yêu cầu không đăng nhập được có thể thất bại tại nhiều lớp:

| Lớp | Ví dụ | Có phải lỗi xác thực? |
| --- | --- | --- |
| **Xác minh danh tính/tài khoản** | Không tìm thấy bản ghi account tương ứng với identifier do người dùng nhập. | Có thể là một nguyên nhân AuthN không thành công; không nên tiết lộ account có tồn tại hay không. |
| **Kiểm tra credential** | Mật khẩu không đúng, passkey assertion không hợp lệ, chứng chỉ không được tin cậy. | Có. |
| **Kiểm tra MFA** | Không hoàn tất yếu tố thứ hai hoặc thiếu yếu tố được chính sách yêu cầu. | Có hoặc là một bước AuthN chưa hoàn tất. |
| **Kiểm tra trạng thái danh tính** | Account đã disable, bị khóa hoặc chưa đến ngày kích hoạt. | Xác thực bị chặn theo chính sách; có thể là hành vi **đúng và mong đợi**. |
| **Federation/SSO** | SAML assertion sai audience hoặc OIDC callback có state không khớp. | Lỗi luồng xác thực/federation, không nhất thiết do người dùng nhập sai. |
| **Kiểm tra token/phiên** | Access token hết hạn hoặc chữ ký token không hợp lệ. | Thất bại kiểm chứng token tại một request; không nhất thiết là thất bại của lần đăng nhập ban đầu. |
| **Phân quyền ứng dụng** | Đã đăng nhập, nhưng thiếu role để xem báo cáo. | Chủ yếu là **AuthZ failure**, không phải AuthN. |
| **Ứng dụng lỗi kỹ thuật** | Database của ứng dụng không hoạt động dù IdP đã xác thực thành công. | Có thể là lỗi availability/provisioning của ứng dụng, không phải sai thông tin đăng nhập. |

**Phân biệt quan trọng:** câu “không vào được ứng dụng” chỉ mô tả **triệu chứng**. Không thể kết luận “sai mật khẩu” hoặc “IdP có vấn đề” khi chưa biết yêu cầu dừng ở bước nào. Trong luồng SSO, xác thực tại IdP có thể **thành công**, nhưng ứng dụng vẫn từ chối do không liên kết được tài khoản hoặc do thiếu quyền.

### 1.1. Thất bại mong đợi và thất bại bất thường

Trong IAM, không phải mọi AuthN failure đều là sự cố phải “sửa để đăng nhập thành công”:

- **Thất bại đúng chính sách:** nhân viên đã nghỉ việc bị từ chối đăng nhập; token đã hết hạn bị từ chối; phương thức MFA quá yếu không được chấp nhận.
- **Thất bại do người dùng:** nhập sai credential, mất yếu tố MFA hoặc sử dụng sai account. Cần hỗ trợ khôi phục có xác minh.
- **Thất bại do cấu hình/hệ thống:** certificate SAML hết hạn, redirect URI sai, đồng hồ lệch quá mức, kết nối IdP gián đoạn hoặc account chưa được provision.
- **Thất bại đáng nghi:** số lượng lớn yêu cầu đăng nhập không hợp lệ, nhiều lần thử trên nhiều account hoặc hành vi bất thường có thể liên quan password spraying, credential stuffing hay chiếm đoạt tài khoản.

**Mục tiêu của IAM không phải làm tỷ lệ authentication failure bằng 0.** Một hệ thống an toàn phải từ chối những yêu cầu không hợp lệ. Điều cần quan sát là *thất bại nào cần được duy trì, thất bại nào cần khắc phục và thất bại nào cần điều tra bảo mật*.

## 2. Đăng nhập có thể thất bại ở những điểm nào?

Sơ đồ sau minh họa một luồng đăng nhập qua IdP và ứng dụng, không phải chi tiết bắt buộc của mọi sản phẩm:

~~~mermaid
flowchart TD
    A["Người dùng mở ứng dụng"] --> B["Ứng dụng chuyển tới IdP hoặc luồng AuthN"]
    B --> C{"Account và trạng thái hợp lệ?"}
    C -->|Không| D["DENY: unknown / disabled / locked"]
    C -->|Có| E{"Yếu tố AuthN chính hợp lệ?"}
    E -->|Không| F["DENY: credential failure"]
    E -->|Có| G{"MFA/conditional access đạt?"}
    G -->|Không| H["DENY hoặc yêu cầu bước bổ sung"]
    G -->|Có| I["IdP tạo kết quả xác thực"]
    I --> J{"Ứng dụng xác minh federation/token?"}
    J -->|Không| K["ERROR: protocol / trust / session"]
    J -->|Có| L{"Ánh xạ đúng account ứng dụng?"}
    L -->|Không| M["ERROR: provisioning / account linking"]
    L -->|Có| N{"Có quyền thực hiện hành động?"}
    N -->|Không| O["DENY: authorization"]
    N -->|Có| P["Truy cập tài nguyên được phép"]
~~~

**Cách đọc:** các nhánh D, F, H thường nằm trong phạm vi quyết định AuthN/chính sách xác thực; K là lỗi kết nối hoặc kiểm chứng thông tin federation; M liên quan account provisioning; O là AuthZ. Người dùng có thể nhìn thấy một thông báo “Sign-in failed” chung cho tất cả, nhưng đội vận hành phải giữ **mã lỗi nội bộ và correlation ID** để phân biệt.

### 2.1. Xác minh username không đồng nghĩa chứng minh danh tính

Hệ thống có thể nhận một identifier (username, email, số điện thoại...) để **tìm account**, sau đó mới kiểm tra credential. Nếu account không tìm thấy, thông báo gửi tới người dùng thường nên tránh xác nhận sự tồn tại của account. Không dùng employee identifier như một **bí mật xác thực**: mã nhân viên có thể bị biết hoặc đoán và chỉ là một khóa dữ liệu nhân sự.

Nếu username/email được đổi khi Mover hoặc thay đổi tên, hệ thống cần dùng liên kết identity–account ổn định. Việc không tìm thấy account theo username cũ có thể là vấn đề **account lookup**, không phải bằng chứng người dùng không còn tồn tại trong HRIS.

### 2.2. Credential không hợp lệ

Credential có thể là mật khẩu, khóa mật mã của passkey, chứng chỉ, bằng chứng từ thiết bị hoặc yếu tố khác tùy kiến trúc. Thất bại có thể do:

1. Credential được cung cấp không khớp hoặc đã bị thu hồi.
2. Một yếu tố không còn hiệu lực hoặc không đáp ứng loại xác thực được yêu cầu.
3. Người dùng thao tác nhầm account/thiết bị hoặc không hoàn tất nghi thức xác thực.
4. Hệ thống kiểm chứng credential lỗi cấu hình, thiếu trust hoặc không thể kết nối với thành phần xác thực.

Không nên giải quyết bằng cách **bỏ qua bước kiểm tra** hay hạ yêu cầu bảo mật. Khắc phục phải xác định credential bị sai, bị mất, hết hạn hay hệ thống xác thực đang gặp sự cố.

## 3. Phân loại nguyên nhân thường gặp

| Nhóm nguyên nhân | Dấu hiệu hoặc dữ liệu nội bộ | Hướng kiểm tra an toàn |
| --- | --- | --- |
| **Unknown/mismatched account** | Account lookup không khớp, liên kết identity–account thiếu. | Kiểm tra nguồn HR/IdP, username alias và account mapping; không công khai kết quả lookup cho người không có thẩm quyền. |
| **Incorrect credential** | Credential verification failed. | Kiểm tra đường xác thực, số lần lỗi và hỗ trợ reset/khôi phục qua quy trình định danh mạnh. |
| **Disabled/inactive account** | Account bị disable, ngày hiệu lực chưa đến, employment status không hợp lệ. | Đối chiếu sự kiện JML và thời điểm hiệu lực; không kích hoạt lại nếu người đó đã rời tổ chức. |
| **Lockout/rate limiting** | Account bị khóa, yêu cầu bị giới hạn do hoạt động bất thường. | Xác định đây là cơ chế bảo vệ hay hành vi đáng nghi; xử lý theo chính sách không gây account enumeration. |
| **MFA not completed** | Yêu cầu MFA chưa hoàn tất, người dùng mất phương thức hoặc thiết bị không tương thích. | Kiểm tra enrollment/recovery, loại yếu tố bắt buộc và tín hiệu rủi ro; không tắt MFA cho nhanh. |
| **Conditional access denied** | Policy yêu cầu thiết bị, vùng mạng, mức rủi ro hoặc phương thức xác thực khác. | Đối chiếu policy/version, thuộc tính ngữ cảnh và đánh giá rủi ro; không coi mọi từ chối là lỗi hệ thống. |
| **Federation mismatch** | SAML issuer/audience/recipient sai; OIDC state, nonce, code hoặc redirect URI không hợp lệ. | Kiểm tra metadata, trust, callback config, session và thay đổi cấu hình; không bỏ kiểm tra chữ ký/trạng thái. |
| **Token/session invalid** | Token hết hạn, revoked, issuer/audience không khớp hoặc session không còn hợp lệ. | Phân biệt token validation failure với login failure; kiểm tra thời hạn và cơ chế làm mới an toàn. |
| **Provisioning incomplete** | IdP xác thực thành công nhưng ứng dụng thiếu account hoặc mapping. | Kiểm tra SCIM/API, account binding, entitlement và kết quả reconciliation. |
| **Dependency/availability failure** | Timeout, IdP unavailable, network/DNS/TLS/certificate lỗi. | Kiểm tra health/dependency và change history, phân biệt lỗi tạm với quyết định từ chối. |

Một người có thể gặp **nhiều nguyên nhân cùng lúc**: account được kích hoạt nhưng chưa enroll MFA; hoặc IdP thành công nhưng ứng dụng chưa nhận SCIM user. Điều tra cần dựa trên sự kiện theo thời gian, không gán nguyên nhân đơn nhất từ thông báo ở giao diện.

## 4. Authentication failure trong mật khẩu, passkey và MFA

### 4.1. Mật khẩu và chính sách chống dò đoán

Các lần nhập mật khẩu sai có thể do lỗi thông thường, password manager điền sai, thông tin lưu trên thiết bị đã cũ hoặc hành vi tấn công. Hệ thống nên:

- Dùng kết quả **deny** nhất quán khi credential không hợp lệ; tránh làm lộ thông tin account có tồn tại.
- Áp dụng **rate limiting**, phát hiện lạm dụng và các biện pháp phòng chống thử mật khẩu quy mô lớn phù hợp rủi ro.
- Tránh chính sách khóa tài khoản quá dễ bị kích hoạt để kẻ xấu có thể cố ý làm người dùng hợp lệ không đăng nhập được.
- Cung cấp quy trình thay đổi/reset credential **có xác minh**, hạn chế social engineering tại help desk.
- Khi có nghi ngờ credential bị lộ, ưu tiên kiểm soát tài khoản, điều tra, khôi phục và thu hồi session/token theo chính sách.

**Thông báo chung cho người dùng** nên giải thích bước tiếp theo (thử lại, kiểm tra phương thức, liên hệ hỗ trợ) thay vì tiết lộ “email này có account” hay “mật khẩu đúng nhưng MFA sai” cho người chưa được xác thực. Nội bộ vẫn cần phân biệt các mã lỗi để điều tra.

### 4.2. Passkey/WebAuthn

Trong xác thực dựa trên WebAuthn/FIDO2, một thiết bị hoặc authenticator dùng khóa mật mã để chứng minh sự sở hữu credential theo nghi thức. Thất bại có thể đến từ việc chọn sai account, trình duyệt/thiết bị không hỗ trợ thao tác, credential đã bị xóa, người dùng hủy prompt hoặc server từ chối một assertion không hợp lệ.

Không nên diễn giải mọi lỗi WebAuthn là “nhập sai mật khẩu”, bởi hệ thống có thể **không sử dụng mật khẩu** trong luồng đó. Log cần thể hiện loại phương thức và **reason code đủ chi tiết cho đội vận hành**, nhưng tránh ghi các bí mật hoặc dữ liệu xác thực nhạy cảm. Với thay đổi thiết bị, cần có quy trình **đăng ký credential dự phòng và khôi phục có kiểm soát**, không tạo đường bypass yếu hơn chính sách.

### 4.3. OTP, push và MFA step-up

MFA failure có thể có nhiều dạng:

| Tình huống | Ý nghĩa có thể | Cách phản ứng |
| --- | --- | --- |
| **TOTP không khớp** | Nhập sai mã, đồng hồ client lệch, phương thức không đúng hoặc yêu cầu giả mạo. | Kiểm tra phương thức được chọn và sức khỏe hệ thống; không chấp nhận mã không hợp lệ. |
| **Push bị từ chối** | Người dùng từ chối thao tác hoặc có yêu cầu không do họ khởi tạo. | Hiển thị cảnh báo phù hợp và phân tích tín hiệu bất thường; không ép người dùng chấp nhận. |
| **Nhiều push liên tục** | Có thể liên quan MFA fatigue hoặc lỗi ứng dụng phát lại. | Giới hạn yêu cầu, cảnh báo, đánh giá tài khoản và chính sách phê duyệt. |
| **Mất thiết bị MFA** | Không thể hoàn tất một yếu tố đã đăng ký. | Quy trình recovery có xác minh đủ mạnh, ghi audit và giảm nguy cơ social engineering. |
| **Thiếu yếu tố mạnh** | Chính sách yêu cầu phishing-resistant MFA nhưng account chỉ có phương thức yếu hơn. | Hướng dẫn đăng ký yếu tố phù hợp; không tự hạ chính sách cho quyền nhạy cảm. |
| **Step-up chưa hoàn tất** | Người dùng đăng nhập cơ bản thành công nhưng hành động rủi ro cao cần tái xác thực mạnh. | Phân biệt session cơ bản với quyền thực hiện hành động đặc biệt. |

**MFA challenge thất bại không nhất thiết làm mất toàn bộ session đã được tạo trước đó.** Hệ quả phụ thuộc chính sách của IdP và ứng dụng. Phải xác định quyền nào đang yêu cầu step-up, kết quả step-up có được ghi đúng vào session/token hay không và ứng dụng có thực thi yêu cầu đó tại tài nguyên cần bảo vệ hay không.

### 4.4. Account recovery cũng là một luồng xác thực

Quên mật khẩu, thay điện thoại hoặc mất passkey không được giải quyết bằng “bỏ MFA tạm” nếu không có phê duyệt và biện pháp tương ứng. Kẻ tấn công có thể khai thác help desk hoặc chức năng reset để chiếm account. Quy trình recovery nên:

1. Xác minh người yêu cầu bằng phương pháp phù hợp độ nhạy của account.
2. Kiểm tra dấu hiệu bất thường và các thay đổi vừa xảy ra (đổi số điện thoại, chuyển thiết bị, reset liên tiếp).
3. Ghi người/phương thức phê duyệt, thực thi và thời điểm.
4. Thu hồi hoặc đánh giá lại credential/session cũ khi chính sách yêu cầu.
5. Thông báo cho chủ thể qua kênh đáng tin và theo dõi việc hoàn tất enrollment lại.

## 5. Lỗi ở IdP, SSO, OIDC và SAML

### 5.1. Phân định lỗi xác thực tại IdP và lỗi federation tại ứng dụng

Trong SSO, IdP có thể xác thực một nhân viên thành công, sau đó ứng dụng (relying party/service provider) phải **kiểm tra kết quả xác thực và ánh xạ account**. Nếu bước sau lỗi, người dùng vẫn nhìn thấy “đăng nhập thất bại”, nhưng không có nghĩa họ nhập credential sai.

Những câu hỏi hữu ích:

- IdP có log **authentication success** cho đúng request/correlation ID không?
- Ứng dụng có nhận được response/callback từ đúng IdP, đúng tenant và đúng endpoint không?
- Chữ ký, issuer, audience, thời hạn và các điều kiện chống replay có được kiểm tra thành công không?
- Subject/NameID trong assertion hoặc token có ánh xạ tới **đúng application account** không?
- Ứng dụng có account đang active không, hay SCIM provisioning chưa hoàn tất?
- Nếu ứng dụng đã nhận diện được user, việc từ chối là do **AuthZ** hay do một lỗi kỹ thuật khác?

### 5.2. OIDC: các lỗi giao thức không phải lỗi mật khẩu

**OpenID Connect (OIDC)** cung cấp lớp định danh trên OAuth 2.0. Trong một luồng Authorization Code phù hợp, ứng dụng dùng các tham số như **state**, **nonce** khi áp dụng, **redirect URI**, và thường dùng **PKCE** để bảo vệ việc trao đổi authorization code.

| Lỗi/điểm kiểm tra | Ví dụ ý nghĩa | Điều không được làm |
| --- | --- | --- |
| **state không khớp** | Callback không thuộc phiên yêu cầu hợp lệ hoặc session bị mất. | Không bỏ qua state check để “cho login chạy”. |
| **nonce không khớp (khi sử dụng nonce)** | ID token không đáp ứng ràng buộc với yêu cầu xác thực. | Không bỏ qua validation hoặc tái sử dụng response tùy tiện. |
| **redirect URI sai** | Cấu hình application/client không khớp với giá trị IdP cho phép. | Không mở wildcard redirect tùy tiện để né lỗi. |
| **Authorization code không hợp lệ/đã dùng** | Code expired, bị dùng lại, ràng buộc client/redirect/PKCE không đạt. | Không thử sửa bằng cách tắt PKCE hoặc kéo dài mã vô hạn. |
| **ID token validation failed** | Issuer, audience, signature hoặc thời hạn không hợp lệ. | Không tắt xác minh chữ ký hay chấp nhận token sai audience. |
| **Client secret/certificate lỗi** | Ứng dụng không xác thực được với token endpoint theo cấu hình. | Không đưa secret vào log hoặc code công khai để kiểm tra nhanh. |

**Access token** là bằng chứng ủy quyền truy cập tài nguyên theo thiết kế OAuth; **ID token** là kết quả định danh OIDC dành cho client. Hai loại token có mục đích và audience khác nhau. Không sử dụng ID token như access token để gọi API, và không tự cho rằng mọi lỗi API 401 sau khi login là một lần AuthN thất bại mới.

### 5.3. SAML: xác minh trust và điều kiện assertion

Với **SAML 2.0**, ứng dụng cần kiểm chứng assertion/response phù hợp cấu hình trust, bao gồm chữ ký theo profile áp dụng, issuer, recipient/destination, audience, thời gian hiệu lực và ràng buộc request khi cần.

Những tình huống thường gặp:
- **Certificate ký được thay đổi nhưng SP chưa cập nhật metadata**: chữ ký không được chấp nhận.
- **Issuer hoặc audience không khớp**: assertion không dành cho SP hiện tại.
- **Clock skew quá lớn hoặc assertion ngoài thời gian hiệu lực**: response bị từ chối.
- **NameID/attribute mapping không khớp account**: IdP đã xác thực nhưng SP không tìm thấy user.
- **ACS endpoint/cấu hình tenant sai**: response được gửi tới endpoint không phù hợp.

Khi khắc phục, nên kiểm tra metadata IdP/SP, lịch sử thay đổi cấu hình và đồng bộ thời gian. **Không tắt kiểm tra chữ ký, audience, recipient hoặc giới hạn thời gian** để vượt lỗi. Bằng chứng chẩn đoán phải tránh ghi hoặc phát tán assertion chứa dữ liệu định danh nhạy cảm.

### 5.4. Đồng hồ và thời gian

Thời gian ảnh hưởng đến TOTP, token expiration, SAML assertion và một số session. Clock skew đáng kể có thể khiến request bị từ chối dù credential đúng. Đồng bộ thời gian của IdP, ứng dụng và thiết bị quan trọng; mọi ngoại lệ tolerance phải được đánh giá theo yêu cầu bảo mật, không tăng tùy ý.

Khi log, sử dụng timestamp có múi giờ hoặc UTC theo quy ước, lưu thời điểm IdP/ứng dụng và liên kết correlation ID để không đọc nhầm thứ tự sự kiện giữa nhiều hệ thống.

## 6. HTTP 401, 403, token và session: tránh chẩn đoán sai

Trong API dùng HTTP, ý nghĩa thường gặp là:

| Dấu hiệu | Diễn giải ban đầu | Lưu ý |
| --- | --- | --- |
| **401 Unauthorized** | Request thiếu hoặc không có thông tin xác thực hợp lệ cho tài nguyên. | Tên “Unauthorized” của HTTP có thể gây nhầm; đây thường là vấn đề credential/token, có thể kèm WWW-Authenticate. |
| **403 Forbidden** | Server hiểu request nhưng từ chối thực hiện, thường do thiếu quyền. | Có thể liên quan policy khác; không tự suy ra “mật khẩu sai”. |
| **429 Too Many Requests** | Giới hạn số lượng yêu cầu, có thể là rate limiting. | Không mặc nhiên là thất bại AuthN hay bằng chứng tấn công. |
| **5xx/timeout** | Lỗi dịch vụ/phụ thuộc. | Điều tra availability; không hiển thị như credential mismatch khi chưa rõ. |

Những mã này là **gợi ý**, không đủ để kết luận chính xác trong mọi sản phẩm. Một ứng dụng có thể dùng custom error code hoặc gộp lỗi vì lý do riêng tư. Điều tra nên dựa trên log của **IdP, resource server, reverse proxy và ứng dụng** với cùng correlation ID.

### 6.1. Token hết hạn hay bị thu hồi

Nếu access token hết hạn, client có thể cần lấy token mới qua cơ chế được phép hoặc yêu cầu người dùng xác thực lại. Nếu refresh token bị thu hồi khi Leaver hoặc do sự kiện bảo mật, không được cố “khôi phục” bằng cách cấp secret mới ngoài quy trình.

Phân biệt:

- **Expired:** hết thời gian hiệu lực được công bố.
- **Revoked:** bị vô hiệu hóa theo cơ chế hệ thống hỗ trợ.
- **Invalid signature/issuer/audience:** token không qua kiểm chứng tin cậy.
- **Insufficient scope:** token có thể hợp lệ nhưng không có quyền cho hành động.
- **Session expired:** phiên ứng dụng không còn hợp lệ, có thể cần đăng nhập lại.

Một token hợp lệ về chữ ký **không chứng minh** account vẫn được phép truy cập nếu hệ thống áp dụng thêm trạng thái account hoặc kiểm tra quyền động. Khi thu hồi quyền nhạy cảm, phải hiểu resource server xử lý token đã phát hành như thế nào.

## 7. Authentication failure theo vòng đời Joiner–Mover–Leaver

### 7.1. Joiner: account chưa sẵn sàng

Nhân viên mới có hồ sơ HRIS và identity trong IAM nhưng ứng dụng có thể chưa tạo account, chưa được kích hoạt hoặc chưa enroll MFA. Các tình huống:

| Hiện tượng | Nguyên nhân có thể | Hành động hợp lý |
| --- | --- | --- |
| Chưa đến ngày bắt đầu, account disabled. | Chính sách pre-start đang hoạt động đúng. | Không kích hoạt sớm nếu chưa có thẩm quyền. |
| Ngày bắt đầu đã đến nhưng IdP chưa có account. | Provisioning job bị trễ/lỗi; identity correlation chưa hoàn tất. | Kiểm tra HR event, IAM task, account mapping và connector. |
| Đăng nhập IdP thành công nhưng ứng dụng “user not found”. | SCIM/API/JIT user provisioning không chạy hoặc mapping SSO sai. | Readback user tại ứng dụng, kiểm tra target account ID và claim mapping. |
| Có account nhưng MFA chưa enroll. | Onboarding xác thực chưa hoàn chỉnh. | Hướng dẫn enrollment hoặc recovery có kiểm soát; không cấp ngoại lệ tùy tiện. |
| Người dùng được tạo sai tenant/domain. | Mapping hoặc thao tác provisioning sai môi trường. | Xác minh source/tenant, sửa liên kết và kiểm tra account trùng. |

**Không dùng thông tin HRIS chỉ để giải quyết đăng nhập mà bỏ qua chính sách cấp quyền.** Có account và xác thực thành công mới là một phần; entitlement phải được phê duyệt đúng theo vai trò và nguồn có thẩm quyền.

### 7.2. Mover: vai trò đổi, nhưng identity thường giữ nguyên

Nhân viên chuyển từ Operations sang Finance thường giữ cùng danh tính và account IdP, nhưng quyền, nhóm và điều kiện truy cập thay đổi. Authentication failure có thể xuất hiện vì:

- Chính sách **conditional access** mới yêu cầu yếu tố MFA hoặc thiết bị phù hợp.
- Nhóm cấp ứng dụng cũ bị gỡ đúng chính sách nên người dùng không còn thấy ứng dụng trong portal.
- Thuộc tính HR/IdP mới đã được cập nhật nhưng ứng dụng dùng claim cũ hoặc account mapping sai.
- Quyền tài chính mới chưa được phê duyệt/cấp; IdP login thành công nhưng ứng dụng trả **403**.
- Account local/role cũ vẫn còn, gây **residual access** chứ không phải authentication failure.

**Cách xử lý đúng:** nếu người dùng đã được IdP xác thực, không nên tự “reset mật khẩu” để sửa thiếu quyền. Kiểm tra **desired access** theo vai trò mới, kết quả provisioning và authorization tại ứng dụng. Đồng thời bảo đảm quyền cũ không còn hiệu lực, kể cả qua phiên hoặc token cũ khi chính sách yêu cầu.

### 7.3. Leaver: đăng nhập thất bại có thể là kết quả mong muốn

Khi HRIS xác nhận nhân viên rời tổ chức và mốc chặn truy cập đã đến, AuthN failure do **account disabled** tại IdP có thể là **bằng chứng một kiểm soát đang hoạt động**. Không nên sửa bằng cách kích hoạt lại account chỉ vì nhận yêu cầu hỗ trợ không được xác minh.

Tuy nhiên, IdP disabled **không tự chứng minh tất cả đường truy cập đã bị chặn**:
- Ứng dụng có **local password** độc lập?
- Session đã đăng nhập còn dùng được?
- Access token, personal access token hoặc API key còn hợp lệ?
- Tài khoản khác cùng người (privileged/local) đã được tìm qua IAM account bindings?
- SCIM/API deprovisioning ở ứng dụng đích có báo lỗi không?

Với Leaver, mục tiêu là **đăng nhập không hợp lệ bị từ chối ở mọi đường truy cập bắt buộc**, đồng thời lưu bằng chứng về thời điểm disable, thu hồi credential/session khi cần và trạng thái ở từng target.

### 7.4. Rehire và thay đổi định danh

Người được tái tuyển có thể có employee identifier mới hoặc cũ theo chính sách HRIS. Nếu IAM tạo identity/account mới mà không kiểm tra person linking, người dùng có thể đăng nhập nhầm account; ngược lại, **tự mở lại account cũ** có thể khôi phục quyền không còn hợp lệ.

Quy trình rehire cần xác minh đúng người/quan hệ, tính lại quyền từ vai trò hiện tại, cấp account theo điều kiện có hiệu lực và không kế thừa entitlement nhạy cảm chỉ vì có lịch sử. Lỗi login trong giai đoạn này phải được xử lý cùng **identity correlation** và account provisioning, không dùng một hành vi reset mật khẩu chung cho mọi trường hợp.

## 8. Authentication failure ở service account và workload

**Non-human identity** như service account, máy chủ, job và workload có thể xác thực bằng certificate, managed identity, workload federation hoặc credential khác. Những đối tượng này không tương tác như người dùng nhập mật khẩu/MFA; nhưng vẫn có thể gặp authentication failure.

| Tình huống | Nguyên nhân có thể | Kiểm soát |
| --- | --- | --- |
| Job báo token request failed. | Credential hết hạn/thu hồi, trust federation sai hoặc identity service không sẵn sàng. | Kiểm tra credential lifecycle, identity provider và log có correlation ID. |
| Certificate dùng cho mTLS hết hạn. | Không có cảnh báo/xoay vòng chứng chỉ kịp. | Inventory certificate, owner, cảnh báo trước hạn và rotation có kiểm chứng. |
| Workload chuyển environment/namespace. | Trust binding hoặc audience không khớp. | Kiểm tra liên kết workload identity và phạm vi chính sách, không mở rộng trust chung. |
| Owner nhân sự rời tổ chức. | Secret không được bàn giao hoặc quy trình phụ thuộc account cá nhân. | Chuyển owner, rà soát người có quyền, xoay vòng secret khi cần; không nhầm service lifecycle với HR JML. |
| API trả 403 sau khi token hợp lệ. | Workload thiếu permission hoặc scope. | Điều tra AuthZ, tránh tự kết luận credential sai. |

**Service account phải có owner, mục đích, tập quyền và quy trình rotation/deprovisioning riêng.** Khi service ngừng hoạt động, thu hồi credential và quyền đúng thời điểm; khi một nhân viên sở hữu service chuyển vai trò, đánh giá khả năng còn kiểm soát credential rồi bàn giao. Không cấp credential nhạy cảm qua ticket hoặc log để “test cho nhanh”.

## 9. Thiết kế thông báo lỗi an toàn

### 9.1. Thông báo cho người dùng và mã lỗi nội bộ phục vụ hai mục tiêu

Thông báo cho người dùng nên **rõ bước tiếp theo nhưng không tiết lộ bí mật hoặc tình trạng account**. Bên vận hành cần log nguyên nhân đủ phân biệt để không bắt người dùng thử đi thử lại.

| Ngữ cảnh | Thông báo người dùng tham khảo | Thông tin nội bộ cần giữ |
| --- | --- | --- |
| Identifier/credential không hợp lệ | “Không thể đăng nhập bằng thông tin đã cung cấp. Vui lòng kiểm tra hoặc sử dụng quy trình khôi phục.” | Reason code có kiểm soát, phương thức, correlation ID. |
| MFA chưa hoàn tất | “Cần hoàn tất bước xác minh bổ sung để tiếp tục.” | MFA method, trạng thái challenge, policy áp dụng. |
| Chính sách chặn | “Yêu cầu đăng nhập chưa đáp ứng chính sách bảo mật. Liên hệ bộ phận hỗ trợ qua kênh chính thức.” | Policy ID/version, lý do deny, thông tin đánh giá rủi ro phù hợp. |
| Dịch vụ IdP tạm gián đoạn | “Dịch vụ đăng nhập hiện không khả dụng. Vui lòng thử lại sau hoặc liên hệ hỗ trợ.” | Dependency health, timeout, error category, correlation ID. |
| IdP thành công, ứng dụng thiếu account | “Tài khoản ứng dụng chưa sẵn sàng. Vui lòng liên hệ bộ phận hỗ trợ.” | Target account mapping/provisioning result. |

**Đừng hiển thị** “username tồn tại nhưng mật khẩu sai” hoặc các lý do giúp dò tài khoản cho người chưa được xác thực. Chi tiết lỗi nội bộ có thể chứa dữ liệu định danh, nên phải được bảo vệ và chỉ cung cấp cho người được phép điều tra.

### 9.2. Giao diện không nên khuyến khích hành vi rủi ro

- Không hướng dẫn người dùng tắt MFA, bỏ xác thực chứng chỉ hoặc dùng account người khác.
- Không khuyến khích gửi mật khẩu, OTP, mã khôi phục hoặc secret qua email/chat.
- Không dùng lỗi không phân biệt kéo dài khiến người dùng retry vô hạn; cung cấp correlation ID và đường hỗ trợ.
- Với yêu cầu đăng nhập bất thường, nên cung cấp kênh báo cáo và biện pháp bảo vệ mà không tiết lộ logic detection chi tiết.
- Khi lỗi do **AuthZ** (thiếu quyền), thông báo nên thể hiện thiếu quyền truy cập tài nguyên, không làm người dùng hiểu rằng account của họ đã bị khóa.

## 10. Audit log: ghi đủ để điều tra mà không lộ bí mật

Một hệ thống xác thực tốt cần log có cấu trúc và khả năng ghép sự kiện giữa IdP, ứng dụng và gateway. Những trường thường hữu ích:

| Nhóm | Trường minh họa | Lý do |
| --- | --- | --- |
| Định danh sự kiện | eventId, correlationId, requestId, timestamp | Nối các bước thuộc cùng một luồng đăng nhập. |
| Phạm vi | application/clientId, IdP/issuer, tenant, environment | Biết lỗi ở ứng dụng và miền trust nào. |
| Chủ thể | identityId/accountId khi biết, identifier được bảo vệ khi cần | Truy vết đúng account, giảm rò rỉ thông tin danh tính. |
| Kết quả | outcome, reasonCode, category, stage | Phân biệt credential, MFA, policy, protocol, dependency. |
| Phương thức | authMethod, mfaMethod, assurance context | Biết bước xác thực nào đã được yêu cầu/thực hiện. |
| Chính sách | policyId/version, decision result | Giải thích vì sao yêu cầu bị từ chối. |
| Ngữ cảnh | tín hiệu thiết bị/mạng/rủi ro đã giảm thiểu phù hợp | Phục vụ phát hiện lạm dụng và điều tra có giới hạn quyền riêng tư. |
| Hậu xử lý | incident/ticketId, remediationOwner, resolvedAt | Kết nối lỗi với quá trình khắc phục. |

Ví dụ **event JSON minh họa nội bộ**, không phải schema chuẩn của một IdP:

~~~json
{
  "eventId": "auth-event-7102",
  "correlationId": "login-flow-83419",
  "timestamp": "2026-11-23T08:15:30+07:00",
  "application": "internal-portal",
  "issuer": "corporate-idp",
  "subject": {
    "accountRef": "idp-user-581",
    "identityRef": "person-2048"
  },
  "authentication": {
    "method": "password-and-totp",
    "stage": "MFA_VERIFICATION",
    "outcome": "FAILURE",
    "reasonCode": "SECOND_FACTOR_NOT_VERIFIED"
  },
  "policy": {
    "policyRef": "workforce-authn-policy-v6",
    "decision": "DENY"
  },
  "operational": {
    "incidentRef": null,
    "responseCategory": "USER_ACTION_OR_RECOVERY_REQUIRED"
  }
}
~~~

**Không ghi** mật khẩu, OTP, recovery code, private key, access token/refresh token đầy đủ, hoặc toàn bộ SAML assertion/HTTP header chứa secret. Nếu cần liên kết session/token phục vụ điều tra, có thể dùng định danh hoặc fingerprint phù hợp cơ chế bảo vệ của tổ chức. Dữ liệu vị trí, thiết bị và địa chỉ mạng cũng cần giới hạn thu thập/truy cập và chính sách lưu giữ.

### 10.1. Vì sao correlation ID quan trọng?

Một yêu cầu SSO có thể đi qua browser → reverse proxy → application → IdP → MFA service → application. Chỉ đọc log ứng dụng “login failed” sẽ không biết IdP thực sự từ chối hay callback đến sai. **Correlation ID/request ID** giúp kết nối, nhưng không phải mọi hệ thống tự chia sẻ một ID duy nhất. Khi cần, đội vận hành dùng mapping sự kiện, timestamp, client ID và subject ID đã được kiểm soát để nối luồng.

### 10.2. Quyết định từ chối và sự cố kỹ thuật cần phân biệt

Ví dụ, hệ thống có thể log:

~~~text
AUTHN_DENIED_INVALID_CREDENTIAL
AUTHN_DENIED_ACCOUNT_DISABLED
AUTHN_DENIED_MFA_POLICY
AUTHN_DENIED_RISK_POLICY
FEDERATION_VALIDATION_FAILED
TOKEN_VALIDATION_FAILED
ACCOUNT_LINKING_NOT_FOUND
IDP_DEPENDENCY_UNAVAILABLE
~~~

Đây là **bộ reason code minh họa**, không phải tên bắt buộc của một tiêu chuẩn. Chúng giúp phân nhóm: các kết quả **DENIED** có thể đúng chính sách, còn **UNAVAILABLE** thường đòi hỏi kiểm tra độ sẵn sàng. Các tên “ACCOUNT_DISABLED” hoặc “ACCOUNT_LINKING_NOT_FOUND” chỉ nên hiển thị cho hệ thống/nhân sự có quyền, không xuất lộ trực tiếp trong phản hồi công khai.

## 11. Quy trình chẩn đoán khi người dùng báo không đăng nhập được

### Bước 1 — Xác định phạm vi và mức độ nghiêm trọng

Hỏi/đối chiếu thông tin không nhạy cảm: ứng dụng nào, thời điểm, loại thiết bị/trình duyệt, thông báo hiển thị và correlation ID. Kiểm tra đây là **một account**, một nhóm người dùng, một tenant hay **sự cố diện rộng**. Nếu nhiều hệ thống cùng lỗi, ưu tiên kiểm tra IdP/dependency chung; nếu chỉ một ứng dụng, kiểm tra federation và account mapping ở đích.

Không yêu cầu người dùng gửi mật khẩu, OTP, passkey private key hoặc token đầy đủ. Nếu có dấu hiệu chiếm đoạt tài khoản, kích hoạt quy trình an ninh theo mức rủi ro trước khi khôi phục.

### Bước 2 — Truy vết trạng thái trong IdP

Xác định tại thời điểm yêu cầu:
1. Account có tồn tại và liên kết đúng identity, tenant hay không?
2. Account đang active, disabled, locked hoặc chờ enrollment theo chính sách?
3. Credential verification có được chạy không? Kết quả ra sao?
4. MFA/conditional access yêu cầu những bước nào; có bước bị thiếu hoặc bị từ chối không?
5. Nếu IdP thành công, kết quả xác thực có được phát hành đúng cho application/client không?

**Không suy ra** account phải được bật lại chỉ vì người dùng nói đó là tài khoản của mình. Kiểm tra HRIS/contractor source và các sự kiện Joiner–Mover–Leaver có hiệu lực.

### Bước 3 — Nếu IdP thành công, kiểm tra ứng dụng

Xem ứng dụng đã nhận callback/assertion hợp lệ chưa, có mapping đúng target account ID không và việc provisioning đã hoàn tất chưa. Nếu xác thực và account linking thành công nhưng ứng dụng từ chối hành động, xem **authorization policy, role, group, entitlement hoặc dữ liệu tài nguyên**, không tập trung reset credential.

### Bước 4 — Kiểm tra độ sẵn sàng và thay đổi cấu hình

Đối chiếu thời điểm bắt đầu lỗi với:
- IdP hoặc MFA provider outage, DNS/TLS/network error.
- Rotation signing certificate/secret, federation metadata hoặc trust configuration.
- Thay đổi redirect URI, issuer, audience, SAML ACS endpoint.
- Thay đổi conditional access, MFA policy hoặc cách ánh xạ group/claim.
- Clock skew ở những thành phần liên quan.
- SCIM/API provisioning error, đồng bộ chậm, dữ liệu identity bị sai.

Ưu tiên **khắc phục chính xác nguyên nhân** hoặc rollback có kiểm soát một cấu hình lỗi theo quy trình thay đổi. Không tắt kiểm tra chữ ký, MFA hoặc policy risk chỉ vì muốn khôi phục nhanh.

### Bước 5 — Khôi phục và xác minh

Sau khi sửa:
1. Kiểm tra với account kiểm thử hoặc user hợp lệ theo chính sách, không dùng account người khác.
2. Xác minh luồng đăng nhập chính và MFA/conditional access như thiết kế.
3. Kiểm tra ứng dụng nhận diện đúng account và không tự cấp entitlement mới ngoài phê duyệt.
4. Nếu lỗi liên quan Leaver, xác minh **yêu cầu bị từ chối vẫn bị từ chối**; không coi login success là tiêu chí thành công.
5. Ghi nguyên nhân, thay đổi đã thực hiện, evidence và thời điểm xác nhận, đánh giá cần cập nhật monitor/runbook không.

### Sơ đồ quyết định ngắn

~~~mermaid
flowchart TD
    A["Người dùng báo sign-in failed"] --> B{"IdP có log tương ứng?"}
    B -->|Không| C["Kiểm tra routing, client, network, browser/session"]
    B -->|Có| D{"IdP từ chối AuthN?"}
    D -->|Có| E{"Theo chính sách và lifecycle là đúng?"}
    E -->|Có| F["Giữ deny; giải thích/hỗ trợ đúng quy trình"]
    E -->|Không hoặc chưa rõ| G["Điều tra account, credential, MFA, policy, availability"]
    D -->|Không, IdP thành công| H{"Ứng dụng kiểm tra federation thành công?"}
    H -->|Không| I["Kiểm tra OIDC/SAML trust, state, audience, clock"]
    H -->|Có| J{"Có account ứng dụng và liên kết đúng?"}
    J -->|Không| K["Kiểm tra provisioning/SCIM/account mapping"]
    J -->|Có| L["Điều tra AuthZ, ứng dụng, dữ liệu và phiên"]
~~~

Sơ đồ chỉ là hỗ trợ phân loại ban đầu: cùng một triệu chứng có thể có các nguyên nhân chồng lấn; cần kiểm tra bằng sự kiện thực tế trước khi quyết định thay đổi quyền hay policy.

## 12. Phản ứng bảo mật và tính sẵn sàng của AuthN

### 12.1. Phân biệt tấn công và lỗi vận hành

Một số lỗi đăng nhập là tín hiệu an ninh, nhưng không nên tự gắn nhãn mọi login failure là tấn công. Đội vận hành có thể phân tích **tần suất, phân bố tài khoản, thiết bị/mạng, phương thức và thay đổi hành vi** theo chính sách để phân loại.

Các biện pháp hữu ích:
- Giới hạn tốc độ/thử lại phù hợp để giảm lạm dụng, tránh cơ chế khóa tài khoản quá dễ bị lợi dụng gây từ chối dịch vụ.
- Cảnh báo những chuỗi thất bại đáng ngờ và những lần MFA push bất thường.
- Dùng MFA chống phishing và yêu cầu step-up cho hành động nhạy cảm khi phù hợp.
- Cập nhật tín hiệu rủi ro và điều tra thông qua kênh có thẩm quyền.
- Khi có xác nhận tài khoản bị xâm phạm, thực hiện containment, credential recovery và session/token revocation theo quy trình.

Không đưa nguyên nhân chính xác của biện pháp phát hiện lạm dụng lên giao diện công khai đến mức làm lộ chính sách hoặc tạo khả năng dò tìm tài khoản.

### 12.2. Nếu IdP không khả dụng thì có nên “fail open”?

**Fail open** (cho phép truy cập khi không kiểm chứng được) có thể đưa một ứng dụng vào trạng thái nguy hiểm. Đối với quyền nhạy cảm, không nên bỏ xác thực hoặc tự cấp quyền khi IdP không trả lời. Thiết kế cần xác định rõ **fail-safe behavior**, bảo đảm an toàn theo mức rủi ro và yêu cầu sẵn sàng.

Nếu tổ chức phải duy trì vận hành khẩn cấp, hãy dùng **break-glass procedure** đã được chuẩn bị: tài khoản/credential được bảo vệ, phạm vi giới hạn, quyền truy cập cần thiết, giám sát, logging, người chịu trách nhiệm và review sau sự cố. Break-glass không đồng nghĩa cho phép mọi người dùng bỏ qua MFA hoặc chấp nhận token sai chữ ký.

Ứng dụng có thể duy trì một số phiên hợp lệ đã được tạo trước sự cố theo chính sách về session; việc này **khác** với cho phép một login mới mà không kiểm chứng được danh tính. Cần đánh giá rõ rủi ro của cached session và khả năng thu hồi khi lifecycle thay đổi.

## 13. Tình huống xuyên suốt: ba lỗi “không đăng nhập được” khác nhau

**Bối cảnh:** Công ty dùng HRIS, IAM/IGA, IdP hỗ trợ SSO và một ứng dụng Finance Portal nhận user thông qua provisioning. Cùng một ngày có ba báo cáo “authentication failure”, nhưng nguyên nhân không giống nhau.

| Người/sự kiện | Triệu chứng | Bằng chứng | Phân loại | Cách xử lý |
| --- | --- | --- | --- | --- |
| **Lan — Joiner** | Đăng nhập IdP được nhưng Finance Portal báo user not found. | IdP AuthN success; connector provisioning tới Portal lỗi, chưa có account target. | **Provisioning/account linking failure**, không phải sai credential. | Sửa connector, provision đúng account, readback và kiểm tra quyền được duyệt. |
| **Minh — Mover** | Mở Finance Portal được nhưng không xem báo cáo của đơn vị cũ. | Login success; RBAC/ABAC mới không cho dữ liệu đơn vị cũ. | **AuthZ deny có thể đúng chính sách**. | Xác nhận role mới và scope; không tự cấp lại quyền cũ hay reset MFA. |
| **Hà — Leaver** | Không đăng nhập IdP được. | HRIS có termination effective; account IdP disabled; policy yêu cầu deny. | **Authentication denied mong đợi**. | Giữ deny, kiểm tra các đường session/local token còn sót ở ứng dụng đích. |

### 13.1. Bản ghi và quyết định cho Lan

~~~text
HRIS:           JOINER effective, identity active
IAM:            account target Finance Portal expected
IdP:            AuthN success, MFA completed
Provisioning:   SCIM/API task failed
Finance Portal: account not found
Decision:       fix provisioning, not reset password
Verification:   target account exists + approved role assigned
~~~

Nếu đội hỗ trợ chỉ xem thông báo “sign-in failed” rồi reset mật khẩu Lan, họ có thể khiến người dùng phải đổi credential không cần thiết và không giải quyết được nguyên nhân. Cần có correlation giữa HRIS identity, IAM task, IdP event và account ID của Portal.

### 13.2. Bản ghi và quyết định cho Minh

~~~text
HRIS:         MOVER Operations -> Finance
IdP:          successful authentication
App account:  mapped correctly
Authorization:
  old department report -> DENY (not in approved scope)
  new department report -> ALLOW (approved)
Decision:     confirm role/ABAC policy and communicate access scope
Verification: old entitlement removed; new entitlement matches policy
~~~

Nếu quyền cũ vẫn hoạt động do session/token/role tại ứng dụng, đó lại là **residual access** cần điều tra, dù người dùng không gặp authentication failure. Vì vậy, kết quả AuthN thành công cũng không tự bảo đảm toàn bộ lifecycle access đúng.

### 13.3. Bản ghi và quyết định cho Hà

~~~text
HRIS:           LEAVER effective at defined cutoff
IAM:            disable and revoke workflow scheduled/executed
IdP:            account disabled -> AUTHN DENIED (expected)
App A:          local account also disabled -> VERIFIED
App B:          existing session still active -> REMEDIATION REQUIRED
Decision:       do not re-enable IdP; close App B access path
Verification:   all mandatory access paths blocked with evidence
~~~

Trong trường hợp này, đăng nhập thất bại tại IdP là **tín hiệu tích cực**, nhưng chưa đủ chứng minh offboarding đã hoàn tất. Kiểm toán cần theo dõi tất cả đường truy cập bắt buộc, bao gồm quyền còn tồn dư tại ứng dụng.

## 14. Chỉ số vận hành và kiểm soát chất lượng

| Chỉ số | Cách đo tham khảo | Điều cần tránh |
| --- | --- | --- |
| **Authentication attempt failure rate** | Số lần AuthN không thành công ÷ tổng số attempt trong phạm vi/khoảng thời gian xác định. | Coi tỷ lệ cao luôn là lỗi sản phẩm; traffic tự động/đáng nghi có thể làm thay đổi mẫu số. |
| **Unexpected legitimate-user failure rate** | Số luồng đăng nhập hợp lệ nhưng bị lỗi không mong đợi ÷ số luồng hợp lệ được quan sát phù hợp. | Không có khả năng phân biệt người dùng hợp lệ với truy cập đáng nghi mà vẫn kết luận chắc chắn. |
| **MFA completion rate** | Challenge hợp lệ được hoàn tất ÷ challenge cần hoàn tất trong phạm vi. | Gộp các challenge bị hủy hoặc bị tấn công thành lỗi usability. |
| **Federation error rate** | SAML/OIDC validation hoặc callback failures ÷ tổng federation flows trong phạm vi. | Gộp lỗi cấu hình với người dùng sai credential. |
| **IdP availability / latency** | Mức sẵn sàng và độ trễ của dependency AuthN. | Bỏ qua sự cố theo tenant, region hoặc phương thức MFA. |
| **Provisioning-related sign-in incidents** | Số incident login do account chưa được provision/mapping sai. | Reset mật khẩu để đóng ticket thay vì sửa account mapping. |
| **Account recovery time** | Thời gian từ yêu cầu recovery hợp lệ đến khi khôi phục an toàn và xác minh. | Tối ưu tốc độ bằng cách bỏ identity proofing hoặc MFA. |
| **Leaver access-block verification** | Tỷ lệ các đường truy cập bắt buộc đã được xác minh bị chặn đúng thời hạn. | Coi mọi AuthN failure tại IdP là bằng chứng toàn bộ ứng dụng đã chặn. |
| **Suspicious auth activity detection** | Sự kiện đáng nghi được phân loại và xử lý trong thời hạn theo mức rủi ro. | Dùng số lượng thất bại thô để suy luận có tấn công. |

Các chỉ số cần có **định nghĩa event, mẫu số, phạm vi tenant/ứng dụng và cách phân biệt user/policy/dependency**. Không có một ngưỡng failure rate cố định phù hợp mọi môi trường; đặc biệt việc người dùng đã nghỉ việc bị từ chối là kết quả mong muốn.

## 15. Các lỗi thiết kế và vận hành thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Gọi mọi lỗi vào ứng dụng là “sai mật khẩu”. | Điều tra sai lớp, khắc phục không hiệu quả. | Tách AuthN, federation, provisioning, AuthZ và availability. |
| Hiển thị “account này tồn tại” khi đăng nhập sai. | Tạo nguy cơ enumeration. | Phản hồi trung tính cho người chưa xác thực, giữ reason code nội bộ. |
| Dùng employee number hoặc email làm yếu tố xác thực. | Dữ liệu dễ lộ/đoán bị dùng như bí mật. | Dùng credential và MFA đúng chính sách, bảo vệ account mapping. |
| Đề xuất tắt MFA để chữa lỗi onboarding. | Mở đường chiếm account. | Recovery/enrollment có kiểm soát và kiểm chứng. |
| Bỏ state/nonce/signature/audience check để sửa SSO. | Có nguy cơ chấp nhận response/token không hợp lệ. | Sửa cấu hình trust, redirect, clock và validation. |
| Không phân biệt token expired với permission denied. | Retry login không cần thiết, API xử lý sai. | Phân loại token validation và AuthZ theo giao thức/ứng dụng. |
| Chỉ nhìn log IdP, không nhìn log ứng dụng. | Bỏ sót lỗi account linking, local role hoặc session. | Correlate IdP–app–connector với event/account ID. |
| Reset mật khẩu khi target user chưa được SCIM provision. | Không sửa được “user not found” tại ứng dụng. | Readback target account và khắc phục provisioning. |
| Mở lại account Leaver theo yêu cầu không được kiểm chứng. | Vi phạm chính sách thu hồi, tạo residual access. | Xác minh trạng thái từ authoritative source và quy trình rehire. |
| Lockout quá dễ bị kích hoạt bởi người ngoài. | Người dùng hợp lệ bị DoS. | Thiết kế rate limiting/risk control cân bằng và giám sát. |
| Lưu full token, password hoặc OTP trong debug log. | Rò rỉ credential. | Dùng reason code, correlation ID, tham chiếu an toàn và retention. |
| Coi IdP disabled là mọi session ở app đã kết thúc. | Local/session/token cũ có thể còn hoạt động. | Deprovision và xác minh các đường truy cập ở target. |
| Không có owner cho lỗi federation/SCIM. | Sự cố kéo dài, người dùng tự tìm cách vượt qua kiểm soát. | Giao owner, incident/ticket, kiểm chứng sau khắc phục. |

## 16. Checklist thực hành

### 16.1. Checklist khi điều tra một authentication failure

- [ ] Xác định ứng dụng, tenant, thời điểm và correlation ID; không thu thập credential hoặc token bí mật.
- [ ] Phân loại lỗi ở **account lookup, credential, MFA, risk policy, federation, token, provisioning, AuthZ hay dependency**.
- [ ] Kiểm tra identity/account binding và trạng thái nhân sự ở nguồn có thẩm quyền, bao gồm effective date JML.
- [ ] Phân biệt AuthN failure **đúng chính sách** với sự cố khiến người dùng hợp lệ không truy cập được.
- [ ] Nếu SSO: kiểm tra IdP event, metadata/trust, issuer, audience, redirect/callback và thời gian.
- [ ] Nếu IdP thành công: readback account tại ứng dụng, mapping SCIM/API/JIT và quyền RBAC/ABAC.
- [ ] Nếu liên quan MFA: kiểm tra enrollment, loại phương thức và recovery không làm suy yếu chính sách.
- [ ] Nếu liên quan token/session: phân biệt expired/revoked/invalid/insufficient scope và quyền vẫn còn hiệu lực.
- [ ] Nếu nghi ngờ tấn công: giữ bằng chứng, phân loại rủi ro và containment theo quy trình.
- [ ] Khắc phục đúng nguyên nhân, không tắt validation hoặc MFA để bypass.
- [ ] Xác minh kết quả với luồng hợp lệ; giữ deny đối với Leaver hoặc yêu cầu không đủ điều kiện.
- [ ] Ghi owner, nguyên nhân, hành động, audit evidence, kết quả và cải tiến cần thiết.

### 16.2. Bài tập tình huống

**Tình huống A — OIDC callback thất bại:** IdP log xác thực thành công nhưng ứng dụng báo lỗi sau redirect. Hãy liệt kê sự khác biệt giữa lỗi credential và lỗi **state/nonce/redirect URI/token validation**, cùng cách kiểm tra mà không tắt các cơ chế bảo vệ.

**Tình huống B — Mover thiếu quyền:** Nhân viên đổi sang bộ phận mới, IdP login vẫn thành công nhưng API trả 403. Hãy xác định vai trò của HRIS, IAM desired access, SCIM/account mapping và application authorization; giải thích vì sao reset mật khẩu không giúp giải quyết.

**Tình huống C — MFA push đáng nghi:** Người dùng nhận nhiều yêu cầu xác thực không do mình khởi tạo. Hãy đề xuất cách từ chối, báo cáo, giới hạn lạm dụng, kiểm tra account và hỗ trợ recovery an toàn thay vì chấp nhận push để làm biến mất thông báo.

**Tình huống D — Leaver vẫn dùng được API key:** IdP account đã bị disable nhưng một ứng dụng còn chấp nhận personal access token. Hãy phân loại kết quả tại IdP và API, xác định đường truy cập tồn dư và bằng chứng cần có trước khi đóng offboarding.

**Tình huống E — Lỗi diện rộng:** Sau khi xoay vòng chứng chỉ ký SAML, nhiều ứng dụng báo login failed, trong khi mật khẩu và MFA vẫn xác thực được tại IdP. Hãy xác định dấu hiệu khoanh vùng sự cố, cách kiểm tra trust/metadata ở SP và điều gì **không được tắt** để sửa nhanh.

**Điểm cần ghi nhớ:** **Authentication failure là một kết quả cần được phân loại theo đúng lớp**, không phải một nguyên nhân duy nhất. Trong IAM lifecycle, việc từ chối truy cập có thể là **kiểm soát đúng chính sách** (chẳng hạn Leaver), **lỗi người dùng hoặc MFA**, **sự cố IdP/SSO**, **thiếu account sau provisioning**, hoặc **lỗi phân quyền ứng dụng**. Cần nối bằng chứng từ nguồn JML, IdP, ứng dụng và hệ thống provisioning; giữ thông báo lỗi an toàn, xử lý recovery có xác minh, không bỏ kiểm tra bảo mật và xác nhận rằng **quyền hợp lệ được khôi phục trong khi quyền không còn căn cứ vẫn bị chặn**.

