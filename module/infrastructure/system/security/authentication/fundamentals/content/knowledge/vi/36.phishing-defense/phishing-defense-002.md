# Domain impersonation

**Domain impersonation** là hành vi sử dụng tên miền, website, email hoặc điểm cuối mạng có vẻ giống một tổ chức hợp pháp nhằm khiến người dùng, trình duyệt hoặc hệ thống tự động tin rằng họ đang giao tiếp với đúng dịch vụ. Kẻ tấn công có thể đăng ký domain gần giống thương hiệu, tạo subdomain gây nhầm lẫn, dùng ký tự Unicode tương tự, giả mạo tên hiển thị email hoặc chiếm quyền một subdomain bị bỏ quên. Mục tiêu thường là lấy mật khẩu, OTP, session cookie, recovery code, thông tin thanh toán hoặc khiến nạn nhân cấp quyền OAuth cho ứng dụng độc hại.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, federation và account recovery. Domain impersonation là mối đe dọa trực tiếp với các luồng này: người dùng có thể nhập credential vào trang giả, phê duyệt push MFA, gửi mã khôi phục hoặc đăng nhập qua một IdP giả mạo.

Điểm cốt lõi: **một URL trông quen thuộc hoặc có HTTPS không chứng minh website thuộc về thương hiệu mà nó đang mô phỏng**. Cần xác định hostname thực, hiểu ranh giới giữa domain và subdomain, xác minh nguồn danh tính, dùng authenticator chống phishing và kiểm soát domain/DNS/email ở phía tổ chức.

## 1. Domain impersonation là gì?

Domain impersonation xảy ra khi attacker tạo hoặc kiểm soát một tên miền đủ giống domain hợp pháp để đánh lừa người dùng hoặc hệ thống. Website giả có thể sao chép logo, màu sắc, nội dung đăng nhập, quy trình MFA và trang hỗ trợ. Email có thể dùng tên hiển thị của thương hiệu nhưng gửi từ một domain khác.

Mục tiêu phổ biến gồm:
- Thu thập username/password bằng trang đăng nhập giả.
- Lấy OTP, recovery code hoặc mã xác minh ngay sau khi nạn nhân nhập.
- Dụ người dùng phê duyệt push MFA mà họ không khởi tạo.
- Đánh cắp session cookie hoặc token qua trang trung gian.
- Giả mạo trang OAuth consent để xin scope rộng.
- Phân phối malware hoặc tệp giả dạng tài liệu doanh nghiệp.
- Thu thập thông tin nhân sự, khách hàng, đối tác hoặc nhà cung cấp.
- Lừa người dùng thay đổi thông tin thanh toán hoặc chuyển tiền.

### 1.1. Phân biệt các khái niệm gần nhau

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Domain impersonation** | Dùng domain/lookalike để giả làm một tổ chức hoặc dịch vụ. | Đăng ký domain gần giống cổng đăng nhập công ty. |
| **Typosquatting** | Đăng ký tên miền dễ bị gõ nhầm. | Thay một ký tự, thêm/bớt dấu gạch nối hoặc chữ. |
| **Homograph attack** | Dùng ký tự có hình dạng giống ký tự khác, thường từ bảng Unicode khác. | Chữ Cyrillic nhìn gần giống chữ Latin trong tên miền. |
| **Subdomain deception** | Đặt tên thương hiệu ở phần subdomain để người đọc nhầm domain đăng ký thực. | login.brand.example.attacker.example. |
| **DNS hijacking** | Chiếm quyền DNS hoặc thay đổi bản ghi để chuyển domain hợp pháp tới hạ tầng attacker. | Chiếm tài khoản registrar rồi đổi nameserver. |
| **Subdomain takeover** | Chiếm một subdomain hợp pháp bị trỏ tới dịch vụ cloud/resource đã bị xóa hoặc bỏ quên. | CNAME còn tồn tại nhưng dịch vụ đích không còn được chủ domain kiểm soát. |
| **Compromised legitimate site** | Website/domain thật bị xâm nhập và dùng để phát tán nội dung độc hại. | Trang hỗ trợ hợp pháp bị chèn form giả. |

Các kiểu này có thể kết hợp. Ví dụ, attacker đăng ký domain lookalike rồi dùng email phishing để đưa nạn nhân tới đó; hoặc chiếm subdomain thật bị bỏ quên để tận dụng uy tín của domain tổ chức.

## 2. Đọc đúng cấu trúc URL và hostname

Để nhận diện domain impersonation, trước hết phải hiểu URL được phân tích như thế nào. Trong URL thông thường, hostname nằm sau scheme và có thể sau phần userinfo; nó kết thúc trước port, path, query hoặc fragment.

Cấu trúc tổng quát:

    scheme://userinfo@hostname:port/path?query#fragment

Ví dụ minh họa:

    https://alice:secret@login.example.org:8443/sign-in?next=/home#form

Trong ví dụ trên:
- Scheme là https.
- Userinfo là alice:secret.
- Hostname là login.example.org.
- Port là 8443.
- Path là /sign-in.
- Query là next=/home.
- Fragment là form.

Tên thương hiệu xuất hiện trong path hoặc query không làm thay đổi hostname. Người dùng phải xác định phần hostname mà browser thực sự kết nối tới.

### 2.1. Những URL dễ gây nhầm

Các ví dụ sau dùng domain dành riêng cho tài liệu:

| URL | Hostname thực | Nhận xét |
| --- | --- | --- |
| https://login.example.org.attacker.example/ | login.example.org.attacker.example | Domain đăng ký nằm dưới attacker.example; chuỗi example.org chỉ là phần subdomain. |
| https://example.org.attacker.example/ | example.org.attacker.example | Không thuộc example.org. |
| https://attacker.example/login?next=https://example.org | attacker.example | Domain thật là attacker.example; domain hợp pháp chỉ xuất hiện trong query. |
| https://example.org@attacker.example/ | attacker.example | Phần trước dấu @ là userinfo, không phải hostname. |
| https://example.org/login | example.org | Hostname là example.org; path không đổi domain. |

Không nên đánh giá URL bằng cách tìm chuỗi thương hiệu ở bất kỳ vị trí nào. Kiểm tra chuỗi có chứa example.org là cách làm sai vì domain attacker có thể chứa chuỗi đó ở subdomain, userinfo hoặc path.

### 2.2. Domain đăng ký và subdomain

Với hostname login.accounts.example.org:
- org là public suffix trong ví dụ đơn giản.
- example.org là registrable domain.
- accounts.example.org và login.accounts.example.org là các subdomain.

Trong thực tế, xác định registrable domain cần dựa vào Public Suffix List (PSL), vì có các suffix nhiều cấp và suffix theo chính sách riêng. Không nên tự lấy hai nhãn cuối cùng làm domain đăng ký cho mọi quốc gia và mọi loại domain.

Một kiểm tra như host.endsWith("example.org") cũng sai: nó có thể chấp nhận notexample.org. Nếu cần so khớp hostname, hãy parse bằng URL parser chuẩn, canonicalize theo quy tắc thống nhất và so sánh exact host hoặc ranh giới nhãn .example.org theo allowlist có chủ đích. Với redirect URI và issuer, thường cần so khớp chính xác theo cấu hình giao thức.

## 3. Các kỹ thuật giả mạo domain phổ biến

### 3.1. Typosquatting và ký tự thay thế

Attacker đăng ký domain có một hoặc vài thay đổi nhỏ:
- Bỏ một ký tự hoặc lặp ký tự.
- Thay chữ bằng số có hình dạng gần giống.
- Đảo vị trí hai ký tự.
- Thêm từ như login, secure, support hoặc verify.
- Thay TLD hoặc thêm dấu gạch nối.

Người dùng đọc nhanh trên màn hình nhỏ có thể không nhận ra khác biệt. Một email có thể hiển thị tên thương hiệu chính xác nhưng liên kết trỏ tới domain lookalike.

### 3.2. Homograph và IDN

Tên miền quốc tế hóa (Internationalized Domain Name, IDN) cho phép dùng ký tự Unicode. Một số ký tự từ các hệ chữ khác nhau có hình dạng giống nhau, ví dụ chữ Cyrillic nhỏ а có thể nhìn gần giống chữ Latin a. Attacker có thể kết hợp ký tự từ nhiều bảng chữ để tạo tên miền khó phân biệt bằng mắt.

IDNA chuyển tên miền Unicode sang dạng ASCII tương thích gọi là A-label, thường có tiền tố xn--. Dạng Unicode hiển thị được gọi là U-label. Browser có thể hiển thị Unicode hoặc Punycode tùy chính sách an toàn, script và khả năng phát hiện confusable.

Không phải mọi IDN đều độc hại; nhiều tổ chức hợp pháp cần tên miền bản địa. Cần đánh giá:
- Script có phù hợp ngôn ngữ và thương hiệu không.
- Có trộn các hệ chữ không cần thiết không.
- A-label/Punycode thực tế là gì.
- Domain có được tổ chức công bố chính thức không.
- Browser và email client hiển thị domain ra sao.

Không tự viết bộ chuyển đổi IDN hoặc bộ so sánh Unicode cho kiểm soát bảo mật nếu có thể dùng thư viện IDNA/UTS #46 phù hợp và được cập nhật.

### 3.3. Subdomain deception

Attacker có thể đặt tên thương hiệu ở phần đầu hostname:

    https://login.example.org.attacker.example/

Người dùng nhìn thấy login.example.org và dừng đọc trước phần domain thực. Nhưng hostname đầy đủ thuộc attacker.example.

Subdomain là phần do chủ sở hữu domain cha quản lý hoặc ủy quyền. Một chuỗi thương hiệu trong subdomain không chứng minh domain đó thuộc thương hiệu. Cần đọc hostname đầy đủ tới registrable domain, đồng thời dùng browser UI hoặc công cụ kiểm tra URL đáng tin cậy.

### 3.4. Brand name trong path, query và userinfo

Một URL có thể chứa tên thương hiệu ở nơi không quyết định host:

    https://attacker.example/brand/login
    https://attacker.example/?return=https://example.org
    https://example.org@attacker.example/

Tên thương hiệu trong path/query chỉ là dữ liệu của URL. Userinfo trước dấu @ có thể làm hostname thật khó nhận ra. Không nên dùng URL có userinfo trong liên kết đăng nhập hoặc hướng dẫn người dùng; hệ thống nên từ chối hoặc xử lý cẩn trọng những URL như vậy trong luồng nhạy cảm.

### 3.5. TLD khác và domain dài

Attacker có thể dùng TLD khác, thêm nhiều nhãn hoặc chọn một domain dài để che khuất registrable domain. Một hostname có nhiều nhãn như login.account.verify.example.attacker.example vẫn thuộc domain attacker.example.

TLD mới không tự động đáng ngờ, và domain ngắn không tự động đáng tin. Phải so sánh với danh sách domain chính thức của tổ chức, không dựa vào cảm giác về đuôi domain.

## 4. HTTPS và certificate không chứng minh thương hiệu

HTTPS mã hóa kết nối giữa browser và hostname, đồng thời xác thực việc endpoint sở hữu private key tương ứng với certificate hợp lệ theo trust chain. Nó không mặc nhiên xác minh rằng chủ domain là ngân hàng, trường học, nhà cung cấp hoặc thương hiệu mà website đang mô phỏng.

Attacker có thể lấy certificate hợp lệ cho domain lookalike của chính họ. Browser hiển thị biểu tượng kết nối an toàn vì kết nối tới domain đó được bảo vệ; trang giả vẫn có thể thu thập credential.

### 4.1. Certificate chứng minh điều gì?

Tùy loại certificate và quy trình CA:
- Domain Validation (DV) chủ yếu xác minh khả năng kiểm soát domain theo phương thức CA chấp nhận.
- Organization Validation (OV) và Extended Validation (EV) có thể kiểm tra thêm thông tin tổ chức theo quy trình CA, nhưng browser hiện đại thường không trình bày EV như một dấu hiệu thương hiệu nổi bật.
- Certificate không chứng minh nội dung trang, ý định của người vận hành hoặc mọi hoạt động kinh doanh là hợp pháp.

Không hướng dẫn người dùng chỉ cần thấy ổ khóa là an toàn. HTTPS là điều kiện cần cho bảo vệ đường truyền, không phải bằng chứng website không phishing.

### 4.2. HSTS và giới hạn bảo vệ

HSTS yêu cầu browser dùng HTTPS khi truy cập domain đã áp dụng policy. Nó giúp chống downgrade và một số kiểu SSL stripping trên domain hợp pháp. HSTS của example.org không bảo vệ người dùng khi họ truy cập example-login.attacker.example.

Tổ chức cần bật HTTPS và HSTS trên domain mình sở hữu, cấu hình certificate/renewal đúng, nhưng vẫn phải giám sát domain giả mạo và bảo vệ luồng đăng nhập.

## 5. Domain impersonation trong email và thông điệp

Email phishing thường kết hợp tên hiển thị, địa chỉ From, Reply-To, liên kết và nội dung tạo áp lực. Người nhận có thể thấy tên IT Support hoặc tên lãnh đạo trong inbox nhưng không kiểm tra domain gửi.

### 5.1. Display name không phải sender identity

Tên hiển thị có thể được người gửi tự chọn. Một thư có thể hiển thị Security Team nhưng địa chỉ gửi là một domain không liên quan. Người dùng cần kiểm tra địa chỉ đầy đủ và domain, đặc biệt khi thư yêu cầu đăng nhập, đổi recovery, gửi mã hoặc thanh toán.

Reply-To cũng có thể khác From. Nếu email yêu cầu trả lời thông tin nhạy cảm, cần kiểm tra cả hai và xác minh qua kênh độc lập.

### 5.2. SPF, DKIM và DMARC

Các cơ chế xác thực email hỗ trợ xác minh nguồn gửi theo domain:

- **SPF:** công bố các máy chủ được phép gửi thư cho domain envelope sender/HELO tương ứng.
- **DKIM:** ký một số header và nội dung thư bằng khóa gắn với domain ký.
- **DMARC:** kiểm tra alignment giữa domain trong trường From hiển thị với domain được SPF hoặc DKIM xác thực; policy có thể yêu cầu xử lý thư không đạt.

DMARC giúp giảm giả mạo trực tiếp domain tổ chức trong email, nhưng không ngăn attacker đăng ký một domain lookalike của riêng họ. Thư từ security-example.attacker.example có thể vượt SPF/DKIM/DMARC của chính domain attacker mà vẫn giả mạo thương hiệu trong nội dung.

DMARC cũng không chứng minh nội dung email an toàn, không loại bỏ email từ account hợp pháp đã bị chiếm và không bảo vệ link sau khi người dùng click. Tổ chức cần triển khai SPF/DKIM/DMARC theo lộ trình, kiểm tra nguồn gửi hợp lệ và theo dõi report trước khi đặt policy reject rộng.

### 5.3. Bảo vệ email domain của tổ chức

- Duy trì SPF record chính xác, tránh nhiều record SPF hoặc vượt giới hạn DNS lookup.
- Ký DKIM cho các hệ thống gửi thư hợp lệ và quản lý rotation selector.
- Triển khai DMARC, kiểm tra alignment, xử lý nguồn gửi chưa được nhận diện rồi tăng dần policy.
- Bảo vệ tài khoản registrar, DNS, mail gateway và admin console bằng MFA chống phishing.
- Giám sát domain lookalike và tên hiển thị lãnh đạo/nhân sự.
- Đào tạo quy trình xác minh độc lập cho thay đổi thanh toán, credential và dữ liệu nhạy cảm.

## 6. Domain impersonation trong luồng đăng nhập và federation

Trang đăng nhập giả có thể sao chép giao diện thật đến mức người dùng không nhận ra. Khi người dùng nhập password, OTP hoặc recovery code, attacker có thể sử dụng ngay dữ liệu đó.

### 6.1. Password và MFA relay

Một số phishing site hoạt động như reverse proxy giữa người dùng và dịch vụ thật. Người dùng nhập password và OTP vào trang giả; proxy chuyển dữ liệu tới dịch vụ thật rồi lấy session cookie/token trả về. Vì vậy MFA dựa trên mã có thể bị relay theo thời gian thực.

Number matching và transaction context giúp giảm MFA fatigue, nhưng không biến OTP thành phishing-resistant. Passkey/WebAuthn gắn xác thực với RP ID/origin; credential được tạo cho domain thật không thể dùng như một passkey hợp lệ trên lookalike origin.

### 6.2. Passkey và origin binding

Trong WebAuthn, browser kiểm tra origin và RP ID theo quy tắc giao thức. Authenticator ký dữ liệu gắn với challenge và RP context. Một trang ở attacker.example không thể đơn giản yêu cầu passkey đã đăng ký cho example.org ký như thể nó đang ở domain hợp pháp.

Đây là lý do passkey và security key FIDO2 được xem là phương thức chống phishing mạnh. Tuy vậy, chúng không bảo vệ khỏi mọi trường hợp:
- Domain thật hoặc máy chủ thật bị chiếm quyền.
- Endpoint người dùng bị malware điều khiển.
- Người dùng bị lừa phê duyệt một hành động hợp lệ nhưng không mong muốn.
- Quy trình recovery yếu cho phép bypass authenticator.
- Ứng dụng xử lý sai origin, redirect hoặc session sau xác thực.

### 6.3. OIDC, redirect URI và IdP impersonation

Trong OIDC, client chuyển browser tới issuer/authorization endpoint đã cấu hình. Nếu người dùng bị đưa tới một IdP giả hoặc client chấp nhận issuer/redirect URI không chặt, attacker có thể chiếm credential hoặc gây nhầm lẫn identity.

Client cần:
- Cấu hình issuer tin cậy từ nguồn quản trị; không chọn issuer chỉ từ tham số callback không xác minh.
- Xác minh exact issuer, chữ ký ID Token, audience và thời hạn.
- Đăng ký và so khớp redirect URI chặt chẽ; tránh wildcard và open redirect.
- Dùng Authorization Code Flow với PKCE; kiểm tra state và nonce theo flow/policy.
- Kiểm tra app identity và scope trên consent screen.
- Không tự động liên kết account chỉ vì email từ IdP trùng nhau.

### 6.4. OAuth consent phishing

Attacker có thể đăng ký ứng dụng với tên và logo giống công cụ nội bộ rồi yêu cầu scope đọc mailbox, file hoặc hồ sơ. Người dùng đăng nhập tại IdP thật nhưng đang cấp quyền cho client độc hại.

Đây không nhất thiết là giả mạo domain đăng nhập; domain/issuer có thể hoàn toàn hợp pháp, nhưng client identity và consent là giả mạo. Cần kiểm tra publisher/client ID, scope, resource, quyền offline và quy trình admin consent; cung cấp trang xem/thu hồi grant.

## 7. Dấu hiệu nhận diện domain impersonation

Không có một dấu hiệu đơn lẻ luôn đúng. Kết hợp nhiều quan sát:
- Domain không khớp danh sách domain chính thức đã công bố.
- Có lỗi chính tả, ký tự thay thế, thêm từ hoặc TLD khác.
- Hostname dài bất thường và thương hiệu chỉ nằm ở subdomain.
- Domain dùng IDN hoặc ký tự trộn script không phù hợp.
- Link có userinfo trước dấu @ hoặc redirect qua nhiều domain.
- Email tạo áp lực, yêu cầu bí mật, OTP, recovery code hoặc đăng nhập khẩn cấp.
- Trang yêu cầu đăng nhập lại sau khi người dùng vừa đăng nhập ở dịch vụ khác.
- Consent xin quyền rộng không phù hợp chức năng.
- Certificate mới cấp cho domain lookalike hoặc domain vừa đăng ký.
- Website có nội dung sao chép nhưng contact, policy hoặc thông tin tổ chức không khớp.

### 7.1. Quy trình kiểm tra an toàn

Khi nghi ngờ:
1. Không nhập credential, OTP, recovery code hoặc thông tin thanh toán.
2. Không tiếp tục qua link trong email/SMS/QR.
3. Mở ứng dụng qua bookmark đã lưu hoặc tự nhập domain chính thức đã xác minh từ nguồn độc lập.
4. Kiểm tra hostname thực trong thanh địa chỉ; trên mobile có thể cần mở chi tiết URL thay vì chỉ nhìn preview.
5. Nếu là yêu cầu công việc, xác nhận qua kênh liên hệ nội bộ đã biết trước.
6. Báo cáo email/link cho đội security qua kênh chính thức.
7. Không tải tệp hoặc cài profile/certificate từ trang đáng ngờ.

Hover lên link có thể giúp xem URL trên desktop nhưng không phải biện pháp đủ tin cậy trên mobile. Link preview cũng có thể bị cắt ngắn hoặc hiển thị không đầy đủ.

## 8. Phòng thủ ở cấp người dùng và trình duyệt

### 8.1. Dùng password manager và passkey

Password manager thường gắn credential với origin/domain đã lưu; nó thường không tự động điền password của domain thật vào domain lookalike. Nếu trình quản lý mật khẩu không đề xuất credential như thường lệ, hãy dừng lại và kiểm tra hostname thay vì copy/paste password vào trang lạ.

Ưu tiên passkey hoặc security key chống phishing khi dịch vụ hỗ trợ. Không chấp nhận prompt MFA bất ngờ; nếu nhận được push mà không tự khởi tạo đăng nhập, từ chối và báo cáo.

### 8.2. Dùng bookmark hoặc đường dẫn đã biết

Với dịch vụ nhạy cảm như email, ngân hàng, HR, cloud console và IAM:
- Truy cập qua bookmark đã kiểm tra hoặc ứng dụng chính thức.
- Không dùng link đăng nhập trong email bất ngờ.
- Kiểm tra domain ở lần đầu và sau khi redirect.
- Không tin logo, màu sắc, tên hiển thị hoặc nội dung trang.
- Không cài root certificate, browser extension hoặc profile thiết bị theo yêu cầu từ email không xác minh.

### 8.3. Browser và endpoint protection

Browser có thể cảnh báo domain độc hại qua Safe Browsing/reputation service, nhưng danh sách có thể chưa cập nhật kịp domain mới. Endpoint protection, DNS filtering và secure web gateway bổ sung lớp phát hiện, không thay thế xác thực domain và hành vi an toàn.

Tổ chức cần cập nhật browser/OS, bật phishing protection, quản lý extension, hạn chế cài ứng dụng không rõ nguồn và giám sát thiết bị có thể đọc clipboard/session.

## 9. Phòng thủ ở cấp tổ chức: bảo vệ domain thật

Domain chính thức là một tài sản bảo mật. Tổ chức cần inventory tất cả domain, subdomain, registrar, DNS provider, certificate, mail sender và owner.

### 9.1. Bảo vệ registrar và DNS

- Bật MFA chống phishing cho tài khoản registrar/DNS admin.
- Dùng tài khoản quản trị riêng, least privilege và phê duyệt cho thay đổi nameserver/registrant.
- Bật registrar/domain lock hoặc registry lock khi phù hợp.
- Dùng DNSSEC để bảo vệ tính xác thực/toàn vẹn dữ liệu DNS theo mô hình hỗ trợ.
- Cấu hình CAA để giới hạn CA được phép cấp certificate cho domain.
- Theo dõi thay đổi NS, MX, TXT, CNAME và bản ghi xác thực email.
- Bảo vệ API token của DNS provider và luân chuyển khi nghi lộ.
- Có quy trình khôi phục domain và liên hệ registrar ngoài băng.

DNSSEC giúp chống một số kiểu giả mạo dữ liệu DNS trên đường phân giải; nó không ngăn attacker đăng ký một domain lookalike khác. CAA giới hạn việc cấp certificate cho domain thuộc tổ chức; nó không xác minh thương hiệu trên domain của attacker.

### 9.2. Quản lý subdomain và tránh subdomain takeover

Duy trì inventory subdomain và record DNS. Khi xóa dịch vụ cloud, phải xóa hoặc cập nhật CNAME/A/AAAA liên quan. Kiểm tra định kỳ các bản ghi trỏ tới SaaS/cloud resource không còn được claim.

Với mỗi subdomain:
- Có owner, mục đích và environment.
- Chỉ cấp quyền DNS cho người cần thiết.
- Xác minh target resource còn thuộc tổ chức.
- Xóa record khi decommission.
- Theo dõi certificate và dịch vụ đang phục vụ hostname.
- Tránh wildcard DNS/certificate quá rộng nếu không cần.

Subdomain takeover thường là chiếm một hostname thuộc domain thật thông qua dangling DNS record; nó khác với việc attacker đăng ký một domain lookalike độc lập.

### 9.3. Giám sát domain giả mạo

Có thể kết hợp:
- Domain registration/RDAP monitoring.
- Certificate Transparency log monitoring.
- Passive DNS và DNS change monitoring.
- Phát hiện typosquat, homoglyph và brand keyword.
- Theo dõi trang web, favicon, logo và nội dung đăng nhập bị sao chép.
- Báo cáo từ nhân viên, khách hàng và nhà cung cấp.
- Threat intelligence và dịch vụ brand protection.

Không phải domain mới chứa tên thương hiệu đều là phishing; có thể có đối tác hoặc chiến dịch hợp pháp. Cần quy trình triage, xác minh quyền sở hữu và bằng chứng trước khi yêu cầu takedown.

## 10. Phòng thủ ở cấp email và ứng dụng

### 10.1. Email authentication

Triển khai SPF, DKIM và DMARC với inventory nguồn gửi chính xác. Theo dõi report để tìm hệ thống gửi thư chưa được cấu hình. Sau giai đoạn quan sát và xử lý nguồn hợp lệ, áp dụng policy phù hợp để giảm giả mạo trực tiếp domain tổ chức.

Bổ sung:
- Banner cảnh báo email ngoài tổ chức khi phù hợp.
- Phát hiện display name giả mạo lãnh đạo/IT/helpdesk.
- Link scanning và attachment sandboxing.
- Tắt hoặc hạn chế macro/tệp thực thi không cần thiết.
- Bảo vệ mailbox bằng passkey/security key và conditional access.
- Quy trình xác minh độc lập cho thanh toán, thay đổi tài khoản ngân hàng và reset credential.

### 10.2. Ứng dụng web

- Chỉ phục vụ trang đăng nhập trên domain chính thức và HTTPS.
- Dùng HSTS trên domain sở hữu.
- Không chuyển credential qua query string hoặc redirect không kiểm soát.
- Dùng cookie Secure, HttpOnly, SameSite phù hợp và session rotation.
- Ràng buộc redirect URI, issuer và audience.
- Áp dụng CSP và chống XSS để giảm nguy cơ trang thật bị lợi dụng.
- Tránh open redirect có thể biến domain đáng tin thành điểm trung chuyển phishing.
- Hiển thị rõ client/publisher và scope trên consent.
- Không yêu cầu người dùng gửi OTP, password hoặc recovery code qua chat/email.

CSP, HSTS và cookie flags bảo vệ domain/ứng dụng thật khỏi một số rủi ro web; chúng không tự chặn domain lookalike ở nơi khác.

## 11. Kiểm tra domain an toàn trong code

Ứng dụng có thể cần kiểm tra callback URL, redirect, link chia sẻ hoặc domain được phép. Không dùng so sánh chuỗi tùy tiện.

### 11.1. Các lỗi thường gặp

Không nên:
- Kiểm tra URL có chứa chuỗi domain tin cậy.
- Dùng regex tự viết thay cho URL parser chuẩn.
- Chỉ so sánh suffix mà không kiểm tra ranh giới nhãn.
- Chấp nhận wildcard redirect quá rộng.
- Tin hostname từ header client tự gửi.
- So sánh Unicode thô mà không chuẩn hóa theo IDNA.
- Cho phép userinfo hoặc scheme không mong muốn.
- Kiểm tra URL trước redirect rồi không kiểm tra đích redirect cuối.

### 11.2. Nguyên tắc allowlist

Một kiểm tra an toàn thường gồm:
1. Parse bằng thư viện URL chuẩn.
2. Chỉ chấp nhận scheme được phép, thường là HTTPS.
3. Từ chối userinfo nếu không có use case rõ.
4. Canonicalize hostname theo IDNA policy thống nhất.
5. So exact hostname hoặc subdomain boundary theo allowlist cụ thể.
6. Kiểm tra port nếu ứng dụng có giới hạn.
7. Kiểm tra path/query theo hợp đồng redirect.
8. Xử lý redirect chain và không để endpoint mở chuyển tiếp tới host tùy ý.
9. Dùng Public Suffix List khi cần suy ra registrable domain.
10. Ghi log reason code mà không lưu query chứa token/secret.

Pseudocode minh họa cho một allowlist host:

    validateRedirect(candidate):
        url = parseWithStandardUrlLibrary(candidate)
        require url.scheme == "https"
        require url.username == ""
        require url.password == ""

        host = canonicalizeIdnaHostname(url.hostname)
        require host is valid

        require host in EXACT_ALLOWED_HOSTS
            or host is an explicitly permitted subdomain
               with a label boundary

        require url.port is permitted
        require pathMatchesRegisteredRedirect(url.path)
        return accepted

Đây chỉ là pseudocode. Trong OAuth/OIDC, redirect URI thường phải khớp chính xác URI đã đăng ký theo specification/provider policy; không thay bằng allowlist domain chung chung. Kiểm tra domain ở tầng ứng dụng không thay thế validation tại authorization server.

### 11.3. Xử lý redirect chain

Một URL ban đầu có thể thuộc domain hợp pháp nhưng chuyển hướng sang domain attacker qua open redirect hoặc parameter do người dùng kiểm soát. Với luồng đăng nhập, thanh toán hoặc tải tài liệu, kiểm tra điểm cuối cuối cùng và giới hạn redirect destination. Không để một endpoint trên domain đáng tin nhận URL tùy ý rồi chuyển browser tới đó.

## 12. Incident response khi phát hiện domain giả mạo

Khi phát hiện domain impersonation, cần xử lý cả người dùng đã tương tác và hạ tầng domain giả. Chỉ yêu cầu gỡ website có thể chưa đủ nếu credential/session đã bị đánh cắp.

### 12.1. Thu thập bằng chứng an toàn

Ghi lại:
- Domain/URL đầy đủ và thời điểm quan sát.
- Email header, sender, Reply-To và message ID nếu có.
- Screenshot hoặc bản sao nội dung theo quy trình an toàn.
- DNS resolution, registrar/hosting và certificate metadata.
- Tài khoản/nhóm người nhận và số người đã click/nhập dữ liệu.
- Dấu hiệu credential, session, OAuth grant hoặc thiết bị bị ảnh hưởng.

Không mở domain độc hại trên máy làm việc thông thường. Dùng môi trường phân tích cô lập theo quy trình security team; không nhập credential thật.

### 12.2. Containment cho người dùng và account

Nếu người dùng đã nhập password hoặc OTP:
- Đổi password qua domain/app chính thức và kiểm tra reuse ở dịch vụ khác.
- Revoke session, refresh token và OAuth grant nghi bị lộ.
- Kiểm tra authenticator/recovery method mới được thêm.
- Thu hồi API key hoặc certificate nếu có khả năng bị lộ.
- Kiểm tra mailbox forwarding rule, app consent và login history.
- Bảo vệ account bằng passkey/security key nếu hỗ trợ.
- Xử lý endpoint bị nhiễm theo incident response.

Nếu attacker đã lấy session cookie, chỉ đổi password có thể chưa đủ; cần thu hồi session và token liên quan.

### 12.3. Takedown và bảo vệ domain thật

- Báo cáo domain tới registrar, registry, hosting, CDN, DNS provider và nhà cung cấp email.
- Gửi abuse report tới browser Safe Browsing/reputation service theo quy trình.
- Yêu cầu CA xem xét certificate nếu có căn cứ vi phạm policy.
- Cập nhật blocklist/DNS filtering và thông báo người dùng.
- Kiểm tra domain thật: registrar, nameserver, MX, DNSSEC, CAA, certificate, IdP redirect URI.
- Nếu domain thật bị chiếm, khôi phục registrar/DNS trước, sau đó rotate credential quản trị, certificate/key và session/token có liên quan.
- Theo dõi domain giả có thể đổi IP, host hoặc đăng ký biến thể mới.

Takedown có thể mất thời gian và attacker có thể chuyển hạ tầng. Containment account và bảo vệ domain thật phải được tiến hành song song.

## 13. Threat model cho domain impersonation

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Typosquatting** | Domain chỉ khác một vài ký tự. | Người dùng nhập credential vào trang giả. | Bookmark, passkey, domain monitoring, browser protection. |
| **IDN homograph** | Ký tự Unicode trông giống Latin. | Nhầm hostname và tin trang giả. | IDNA/Punycode review, browser policy, domain monitoring. |
| **Subdomain deception** | Brand nằm ở đầu hostname, attacker domain ở cuối. | Người dùng hiểu nhầm chủ sở hữu domain. | Đọc hostname, URL parser, exact allowlist. |
| **Userinfo deception** | Brand xuất hiện trước dấu @. | Hostname attacker bị che khuất. | Từ chối userinfo trong link nhạy cảm, parse URL chuẩn. |
| **Email sender spoofing** | Giả From/display name hoặc Reply-To. | Nạn nhân click link, gửi thông tin hoặc thanh toán. | SPF/DKIM/DMARC, display-name detection, out-of-band verification. |
| **MFA relay** | Reverse proxy chuyển tiếp password và OTP. | Attacker lấy session sau MFA. | Passkey/FIDO2, transaction binding, session protection. |
| **OAuth consent phishing** | App giả yêu cầu scope rộng trên IdP thật. | Grant tồn tại sau khi người dùng rời trang. | Publisher/client verification, least privilege, admin consent, revoke grant. |
| **DNS hijacking** | Chiếm registrar hoặc DNS provider. | Domain thật trỏ tới hạ tầng attacker. | Registrar MFA/lock, DNSSEC, change alerts, recovery runbook. |
| **Subdomain takeover** | Dangling DNS trỏ tới resource không còn được claim. | Attacker phục vụ nội dung dưới domain thật. | Inventory, DNS cleanup, ownership verification. |
| **Lookalike certificate trust** | Domain giả có certificate TLS hợp lệ. | Người dùng nhầm HTTPS với tính hợp pháp. | Education, domain verification, passkey, brand monitoring. |
| **Open redirect abuse** | Domain thật chuyển tiếp tới URL attacker. | Tận dụng uy tín domain hợp pháp để phân phối phishing. | Redirect allowlist, exact URI matching, chain validation. |

## 14. Tình huống thực hành: email giả mạo cổng đăng nhập

**Bối cảnh:** Nhân viên nhận email có tên hiển thị IT Security. Nội dung thông báo session sắp hết hạn và yêu cầu xác minh MFA. Nút trong email trỏ tới:

    https://login.example.org.attacker.example/session

Trang giả sao chép logo công ty, có HTTPS và yêu cầu username, password, OTP.

**Phân tích:**

1. Hostname thực là login.example.org.attacker.example; registrable domain trong ví dụ là attacker.example.
2. Chuỗi example.org chỉ nằm trong subdomain, không chứng minh domain thuộc tổ chức.
3. HTTPS chỉ mã hóa kết nối tới attacker domain; nó không xác minh thương hiệu.
4. OTP có thể bị reverse proxy relay ngay tới IdP thật.
5. Nếu attacker lấy được session cookie hoặc token, họ có thể truy cập sau khi email phishing kết thúc.

**Phản ứng đúng:**

- Không nhập credential hoặc OTP; đóng trang và báo cáo email.
- Truy cập cổng đăng nhập bằng bookmark/domain chính thức.
- Security team kiểm tra email header, DNS, registrar, hosting và certificate của domain giả.
- Nếu đã nhập credential, reset qua kênh chính thức, revoke session/refresh token và rà soát OAuth grants.
- Kiểm tra login history, authenticator enrollment, recovery changes và hoạt động sau đăng nhập.
- Thêm domain vào blocklist/reputation feeds và thông báo người dùng theo phạm vi ảnh hưởng.
- Rà soát DMARC và các kiểm soát email để giảm giả mạo domain của chính tổ chức.

**Câu hỏi:** Nếu trang giả có biểu tượng ổ khóa và certificate hợp lệ thì có thể tin không? Không. Certificate xác thực domain đang kết nối theo trust model TLS, không chứng minh domain đó thuộc tổ chức bị mô phỏng.

## 15. Checklist phòng chống domain impersonation

- [ ] Duy trì danh sách domain, subdomain, issuer, redirect URI và kênh liên hệ chính thức.
- [ ] Dạy người dùng xác định hostname thực, registrable domain và ranh giới subdomain.
- [ ] Không đánh giá URL bằng chuỗi thương hiệu xuất hiện ở path, query hoặc userinfo.
- [ ] Dùng URL parser chuẩn, IDNA policy thống nhất và Public Suffix List khi cần.
- [ ] Kiểm tra exact hostname/redirect URI; tránh substring match, wildcard và open redirect.
- [ ] Giải thích rằng HTTPS/certificate không chứng minh website thuộc thương hiệu.
- [ ] Ưu tiên passkey/FIDO2 chống phishing; không chấp nhận push/OTP bất ngờ.
- [ ] Dùng password manager và bookmark/ứng dụng chính thức cho dịch vụ nhạy cảm.
- [ ] Triển khai SPF, DKIM và DMARC; kiểm tra alignment và nguồn gửi hợp lệ.
- [ ] Bảo vệ registrar, DNS provider, IdP và mailbox admin bằng MFA chống phishing.
- [ ] Bật registrar lock, DNSSEC và CAA theo kiến trúc phù hợp.
- [ ] Inventory subdomain, xóa dangling DNS record và kiểm tra cloud resource bị bỏ quên.
- [ ] Giám sát RDAP/domain registration, Certificate Transparency và passive DNS.
- [ ] Có quy trình triage và takedown domain giả; phân biệt lookalike với domain hợp pháp của đối tác.
- [ ] Khi credential bị lộ, revoke session/token/grant và kiểm tra recovery/authenticator changes.
- [ ] Kiểm tra OIDC issuer, signature, audience, state, nonce, PKCE và redirect URI.
- [ ] Kiểm thử typosquat, IDN homograph, subdomain deception, userinfo, email spoofing và OAuth consent phishing.
- [ ] Có incident runbook cho cả domain giả mạo và trường hợp domain/DNS thật bị chiếm.

## 16. Câu hỏi tự kiểm tra

**1. Domain impersonation là gì?**  
Là sử dụng domain hoặc điểm cuối có vẻ giống tổ chức hợp pháp để khiến người dùng/hệ thống nhầm nguồn và tiết lộ credential hoặc cấp quyền.

**2. Trong URL, phần nào xác định máy chủ browser kết nối tới?**  
Hostname sau khi URL được parse; path, query, fragment và phần userinfo không xác định domain đích.

**3. Vì sao example.org.attacker.example không thuộc example.org?**  
Vì registrable domain nằm dưới attacker.example; example.org chỉ là nhãn subdomain.

**4. HTTPS có chứng minh website là của thương hiệu không?**  
Không. TLS bảo vệ kết nối và xác thực domain theo certificate; attacker cũng có thể lấy certificate hợp lệ cho domain giả của họ.

**5. IDN homograph attack hoạt động thế nào?**  
Attacker dùng ký tự Unicode có hình dạng giống ký tự trong domain thật, khiến người dùng khó phân biệt bằng mắt.

**6. DMARC có chặn mọi email phishing không?**  
Không. DMARC giảm giả mạo trực tiếp domain From của tổ chức; attacker vẫn có thể dùng domain lookalike, account hợp pháp bị chiếm hoặc nội dung giả mạo.

**7. Vì sao OTP/MFA dạng mã có thể bị phishing?**  
Attacker có thể dùng reverse proxy chuyển tiếp password và OTP theo thời gian thực để lấy session từ dịch vụ thật.

**8. Passkey giúp chống domain impersonation ra sao?**  
WebAuthn ràng buộc credential với RP ID/origin; passkey của domain thật không thể được dùng hợp lệ trên lookalike origin.

**9. DNSSEC có ngăn typosquatting không?**  
Không. DNSSEC bảo vệ tính xác thực/toàn vẹn dữ liệu DNS trong zone được ký; nó không ngăn người khác đăng ký domain gần giống.

**10. Khi đã nhập password vào domain giả, cần làm gì?**  
Truy cập dịch vụ qua domain chính thức, đổi/reset credential theo quy trình, revoke session/token/grant, kiểm tra authenticator/recovery changes và báo security team.

**Ghi nhớ:** Domain impersonation khai thác sự nhầm lẫn giữa tên miền nhìn thấy và hostname thực. Hãy parse URL đúng, hiểu IDN/subdomain/userinfo, không xem HTTPS là bằng chứng thương hiệu, bảo vệ domain/email/DNS của tổ chức và ưu tiên passkey chống phishing. Khi sự cố xảy ra, xử lý đồng thời domain giả, credential, session, token, grant và account recovery để cắt đứt quyền truy cập đã bị lạm dụng.
