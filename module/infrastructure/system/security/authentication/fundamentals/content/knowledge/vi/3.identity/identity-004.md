# Bằng chứng danh tính

## 1. Bằng chứng danh tính trả lời câu hỏi nào?

**Bằng chứng danh tính** (*identity evidence*) là tài liệu, dữ kiện, xác nhận hoặc tín hiệu có thể dùng để hỗ trợ một tuyên bố về danh tính. Ví dụ: giấy tờ do cơ quan có thẩm quyền cấp, bản ghi trong nguồn dữ liệu được tin cậy, chứng nhận danh tính số, hoặc xác nhận quyền kiểm soát một địa chỉ email hay tên miền. Giá trị của bằng chứng phụ thuộc vào **điều cụ thể mà nó chứng minh**, nguồn cấp, cách kiểm tra và cách gắn nó với chủ thể đang tương tác.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bằng chứng danh tính là mắt xích nối phần *Identity* với credential, mật khẩu, MFA, passkey, chứng chỉ, phiên và token. Để thiết kế luồng xác thực an toàn, cần phân biệt ba câu hỏi:

| Câu hỏi | Quá trình | Kết quả cần đạt |
| --- | --- | --- |
| “Người hoặc tổ chức này là ai, và các thuộc tính khai báo có cơ sở nào?” | **Identity proofing**: thiết lập, kiểm chứng danh tính | Hồ sơ danh tính với các thuộc tính và mức tin cậy phù hợp |
| “Chủ thể đang đăng nhập có kiểm soát credential đã được gắn với hồ sơ đó không?” | **Authentication**: xác thực bằng mật khẩu, MFA, passkey, khóa, chứng chỉ… | Sự kiện xác thực và principal được nhận diện |
| “Principal này được phép làm gì với tài nguyên cụ thể?” | **Authorization**: kiểm tra chính sách và quyền | Quyết định cho phép hoặc từ chối thao tác |

Một hệ thống có thể xác thực rất mạnh bằng passkey nhưng **không hề biết tên pháp lý** của người dùng nếu tài khoản được tạo ẩn danh. Ngược lại, hồ sơ đăng ký có ảnh chụp giấy tờ tùy thân không chứng minh rằng người đang đăng nhập **hiện tại** là chủ thể được ghi trên giấy tờ đó. Hai trường hợp cần các loại kiểm chứng khác nhau.

> Nguyên tắc: bằng chứng danh tính chỉ có ý nghĩa trong **phạm vi tuyên bố đã được kiểm chứng**. “Kiểm soát hộp thư” không đồng nghĩa “là người có tên trong giấy tờ”; “chứng chỉ còn hiệu lực” không đồng nghĩa “có mọi quyền truy cập”.

## 2. Phân biệt claim, evidence, credential và principal

Một hệ thống thường đi từ lời khai ban đầu đến danh tính được sử dụng trong ứng dụng:

1. **Claim (tuyên bố):** “Tôi là Nguyễn A”, “tôi sở hữu tên miền example.test”, hoặc “tôi thuộc tổ chức X”.
2. **Evidence (bằng chứng):** giấy tờ, bản ghi, xác nhận từ nguồn tin cậy hoặc cơ chế kiểm soát một tài nguyên hỗ trợ claim đó.
3. **Proofing/verification (kiểm chứng):** đánh giá bằng chứng có thật, hợp lệ, còn thích hợp và có liên quan đến người/thiết bị đang yêu cầu hay không.
4. **Identity record và principal:** ứng dụng thiết lập một định danh nội bộ, chẳng hạn subject ID bất biến trong phạm vi hệ thống; các thuộc tính đã kiểm chứng gắn với bản ghi này.
5. **Credential:** mật khẩu, khóa passkey, khóa riêng, yếu tố MFA… được đăng ký và gắn với principal để dùng cho lần xác thực tiếp theo.

| Thuật ngữ | Ví dụ | Không nên suy diễn |
| --- | --- | --- |
| Identifier | User ID nội bộ, email, số tài khoản, subject ID của IdP | Identifier tự nó là bằng chứng người dùng sở hữu danh tính |
| Self-asserted attribute | Họ tên người dùng tự nhập | Dữ liệu đã được cơ quan có thẩm quyền xác nhận |
| Identity evidence | Giấy tờ hợp lệ, xác nhận từ nguồn đăng ký, bằng chứng kiểm soát tên miền | Mọi thuộc tính trong bằng chứng đều đúng mãi mãi |
| Authenticator / credential | Passkey, mật khẩu, khóa riêng gắn với tài khoản | Credential tự chứng minh tên pháp lý của người đang dùng |
| Authentication assertion | Xác nhận từ IdP rằng một subject vừa đăng nhập | Ứng dụng được phép bỏ qua kiểm tra issuer, audience và ngữ cảnh |
| Principal | Định danh ứng dụng dùng sau khi xác thực thành công | Principal đương nhiên có quyền với mọi tài nguyên |

**Ví dụ:** Người dùng đăng ký bằng email rồi nhấp liên kết xác minh. Hệ thống có bằng chứng rằng người dùng *đã có khả năng truy cập hộp thư trong thời điểm xác minh*. Điều đó chưa chứng minh họ tên, tuổi, địa chỉ cư trú hoặc tư cách đại diện công ty. Nếu ứng dụng chỉ là diễn đàn, độ tin cậy đó có thể đủ; nếu cung cấp dịch vụ tài chính chịu quy định, yêu cầu bằng chứng sẽ khác.

## 3. Các nhóm bằng chứng thường gặp

Không có một loại bằng chứng “mạnh nhất” cho mọi tuyên bố. Việc chọn loại nào phụ thuộc thuộc tính cần thiết lập, nguồn tin cậy và rủi ro của thao tác.

| Nhóm bằng chứng | Ví dụ | Tuyên bố thường hỗ trợ | Giới hạn, điểm cần kiểm tra |
| --- | --- | --- | --- |
| Giấy tờ do bên có thẩm quyền cấp | Căn cước, hộ chiếu, giấy phép phù hợp | Tên, ngày sinh, một số thuộc tính pháp lý | Giả mạo/chỉnh sửa; giấy tờ thật nhưng bị đánh cắp; hết hạn; dữ liệu không khớp |
| Bản ghi hoặc xác nhận từ nguồn đáng tin | Cơ sở dữ liệu đăng ký, nhà cung cấp dịch vụ có thẩm quyền | Thuộc tính hiện hành, tư cách pháp lý | Quyền truy cập, độ cập nhật, phạm vi xác nhận, độ chính xác của bản ghi |
| Bằng chứng kiểm soát kênh liên lạc | Email link, OTP gửi điện thoại | Khả năng kiểm soát email/số điện thoại trong một thời điểm | Chuyển tiếp, chiếm đoạt hộp thư, SIM swap; không chứng minh danh tính pháp lý |
| Bằng chứng kiểm soát tài nguyên số | Thử thách DNS cho tên miền, chứng minh kiểm soát tài khoản nguồn | Quyền kiểm soát tài nguyên theo giao thức | Quyền kiểm soát có thể thay đổi; tài khoản bị xâm nhập; phải chống replay |
| Chứng chỉ / xác nhận có chữ ký số | Chứng chỉ X.509, credential số từ issuer được tin | Các thuộc tính được issuer chứng nhận, quyền kiểm soát khóa tương ứng | Trust anchor, chain, thu hồi, thời hạn, subject mapping và phạm vi sử dụng |
| Liên kết danh tính qua IdP | OIDC ID token, SAML assertion được xác minh | IdP khẳng định subject và thuộc tính theo hợp đồng tin cậy | Không phải mọi claim đều được proofing cùng mức; cần xác minh giao thức và issuer |
| Tín hiệu hỗ trợ chống gian lận | Lịch sử thiết bị, tốc độ yêu cầu, IP, hành vi đáng ngờ | Ngữ cảnh và đánh giá rủi ro | Có thể sai lệch; không tự đủ để khẳng định danh tính một người |

Có hai phân biệt thường bị bỏ qua:

- **Nguồn cấp khác với người cung cấp:** ảnh chụp một giấy tờ “do cơ quan nhà nước cấp” nhưng do người dùng tự tải lên vẫn cần kiểm tra tính xác thực của tài liệu và liên hệ của nó với người gửi. Chỉ nhìn tên cơ quan in trên ảnh chưa đủ.
- **Bằng chứng thuộc tính khác với bằng chứng sở hữu:** chứng minh một địa chỉ email đang được kiểm soát giúp xác nhận kênh liên lạc; chứng minh một con người là chủ sở hữu pháp lý của tài khoản có thể cần quy trình khác.

Trong hệ thống hiện đại, các tín hiệu bổ trợ có thể hỗ trợ đánh giá gian lận nhưng không nên âm thầm biến thành định danh pháp lý đáng tin cậy.

## 4. Đánh giá chất lượng bằng chứng theo từng chiều

“Có tài liệu” không đồng nghĩa “đã kiểm chứng”. Một thiết kế tốt cần ghi nhận bằng chứng đáp ứng **tuyên bố nào** và đã qua những phép kiểm tra nào.

### 4.1. Nguồn gốc, tính xác thực và tính toàn vẹn

- **Provenance (nguồn gốc):** ai phát hành bằng chứng, qua kênh nào, bên xác minh có lý do gì để tin nguồn đó?
- **Authenticity (tính xác thực):** có dấu hiệu giả mạo, làm lại, nhân bản, hoặc nguồn phát hành không hợp lệ hay không?
- **Integrity (tính toàn vẹn):** bằng chứng có bị sửa đổi sau khi phát hành không? Chữ ký số hợp lệ có thể giúp kiểm tra tính toàn vẹn và nguồn ký, nhưng chỉ khi khóa công khai và chuỗi tin cậy được xác minh đúng.
- **Validity (hiệu lực):** tài liệu có còn hạn, bị thu hồi, thay thế hoặc không còn phù hợp với mục đích sử dụng?

Ví dụ, chứng chỉ TLS được ký hợp lệ chỉ hữu ích khi ứng dụng còn kiểm tra danh tính mong đợi, thời hạn, chuỗi tin cậy, trường mục đích sử dụng và trạng thái thu hồi nếu chính sách yêu cầu.

### 4.2. Ràng buộc bằng chứng với đúng chủ thể

Tài liệu **có thật** và người đang nộp tài liệu **là người có quyền dùng nó** là hai mệnh đề khác nhau. Trong identity proofing của con người, việc đối chiếu dữ liệu, ảnh chân dung, xác minh trực tiếp hoặc quy trình từ xa được thiết kế thích hợp có thể giúp đánh giá ràng buộc này. Tuy nhiên, nhận diện sinh trắc có sai số; việc dùng ảnh, video hoặc liveness cũng có thể bị tấn công bằng giả mạo và deepfake.

Với danh tính máy/dịch vụ, ràng buộc thường là **chứng minh quyền kiểm soát private key** gắn với certificate/credential, rồi ánh xạ khóa hoặc subject sang dịch vụ được quản lý. Không được coi một certificate xuất hiện trong request nhưng chưa có bằng chứng sở hữu khóa là đã xác thực.

### 4.3. Độ mới, khả năng bị thu hồi và mức phù hợp

Một bằng chứng có thể đúng ở thời điểm cấp nhưng không còn đúng ở thời điểm dùng: tên miền đã chuyển chủ, nhân viên đã rời tổ chức, chứng chỉ đã bị thu hồi, số điện thoại đã chuyển sang người khác. Vì thế cần phân biệt:

- **Issued at:** lúc bằng chứng được phát hành.
- **Verified at:** lúc hệ thống thực sự kiểm tra nó.
- **Expires at / refresh by:** lúc bằng chứng, thuộc tính hoặc kết quả xác minh cần được xem xét lại.
- **Revocation status:** trạng thái thu hồi khi cơ chế hỗ trợ.
- **Permitted use:** phạm vi bên nhận và mục đích mà bằng chứng có giá trị.

Đừng đặt quy tắc “bằng chứng cũ hơn N ngày thì sai” cho mọi loại bằng chứng; tuổi, rủi ro và yêu cầu quy định khác nhau theo thuộc tính và hệ thống. Độ mới của **identity proofing** cũng không đồng nhất với thời gian xác thực gần nhất của một session.

### 4.4. Tính độc lập và khả năng kiểm tra lại

Hai nguồn có vẻ khác nhau có thể cùng sao chép một dữ liệu sai ban đầu. Ví dụ, hai trang web dùng lại thông tin do một người tự khai không tạo thành hai bằng chứng độc lập. Khi thiết kế mức đảm bảo cao, cần quan tâm nguồn gốc thật sự, cách xác minh và khả năng kiểm tra lại từng kết luận, đồng thời chỉ thu thập dữ liệu thực sự cần thiết.

## 5. Quy trình từ bằng chứng đến hồ sơ danh tính

Một quy trình identity proofing thường có các bước sau. Việc đặt tên là **mô hình thiết kế tham khảo**, không phải yêu cầu mỗi sản phẩm phải triển khai nguyên xi:

1. **Xác định claim cần chứng minh:** ví dụ “người dùng đủ 18 tuổi” hay “dịch vụ kiểm soát hostname cụ thể”. Tránh thu thập toàn bộ hồ sơ khi chỉ cần xác nhận một thuộc tính.
2. **Identity resolution:** phân giải, đối chiếu để hạn chế tạo bản ghi trùng hoặc gắn nhầm người. Cần xét rủi ro cả **false match** (gộp nhầm) lẫn **false non-match** (tách nhầm).
3. **Thu thập evidence theo kênh an toàn:** chỉ định loại bằng chứng được chấp nhận, thông báo rõ mục đích, bảo vệ truyền nhận và hạn chế sao chép.
4. **Evidence validation:** kiểm tra tính xác thực, toàn vẹn, hợp lệ và nguồn cấp.
5. **Identity verification:** kiểm tra bằng chứng liên hệ với đúng chủ thể đang yêu cầu và claim cần xác nhận.
6. **Ra quyết định:** chấp nhận, yêu cầu bằng chứng bổ sung, chuyển kiểm tra thủ công hoặc từ chối theo chính sách và mức rủi ro.
7. **Tạo/cập nhật identity record:** gắn thuộc tính, trạng thái và nguồn xác nhận vào định danh nội bộ; ghi nhận thời điểm, kết quả, phiên bản chính sách.
8. **Đăng ký credential và quản lý vòng đời:** liên kết passkey, mật khẩu/MFA hoặc cơ chế thích hợp với principal; xác minh lại khi có thay đổi nhạy cảm, phát hiện rủi ro hoặc hết thời gian tin cậy.

~~~mermaid
flowchart TD
    A[Claim danh tính cần chứng minh] --> B[Chọn evidence theo rủi ro]
    B --> C[Thu thập và kiểm tra kênh]
    C --> D[Validation: nguồn, toàn vẹn, hiệu lực]
    D --> E{Evidence hợp lệ?}
    E -- Không --> R[Từ chối hoặc yêu cầu bổ sung]
    E -- Có --> F[Verification: gắn đúng chủ thể]
    F --> G{Đủ tin cậy cho mục đích?}
    G -- Chưa --> H[Kiểm tra thêm hoặc review thủ công]
    G -- Có --> I[Identity record + provenance]
    I --> J[Đăng ký/binding credential]
    J --> K[Xác thực về sau bằng credential]
    K --> L[Session/token + kiểm tra authorization]
~~~

**Điểm quyết định quan trọng:** bằng chứng có thể đã qua validation nhưng verification vẫn thất bại. Một hộ chiếu thật bị người khác đánh cắp không làm người cầm hộ chiếu tự động trở thành chủ thể của hồ sơ.

## 6. Mô hình dữ liệu: lưu kết luận và nguồn xác minh

Một hệ thống nên tách **bằng chứng thô**, **kết quả kiểm tra**, **thuộc tính đã xác minh** và **credential xác thực**. Ví dụ TypeScript dưới đây chỉ mô tả **hợp đồng nội bộ**, không phải API hoặc định dạng chuẩn:

~~~ts
type EvidenceKind =
  | "government_document"
  | "trusted_registry"
  | "verified_email_control"
  | "domain_control"
  | "issuer_attestation";

type EvidenceResult = {
  evidenceId: string; // Mã tham chiếu, không chứa dữ liệu giấy tờ
  kind: EvidenceKind;
  claim: string; // Ví dụ: "control:domain:example.test"
  issuerOrSource: string;
  validatedAt: string;
  boundToSubjectAt?: string;
  expiresAt?: string;
  status: "verified" | "pending" | "rejected" | "revoked";
  policyVersion: string;
  verificationMethod: string;
};

type IdentityRecord = {
  subjectId: string; // Định danh nội bộ ổn định trong phạm vi hệ thống
  verifiedAttributes: Record<string, unknown>;
  evidenceReferences: string[];
  identityProofingStatus: "unverified" | "partial" | "verified";
};
~~~

Ví dụ, dữ liệu kết luận có thể được lưu như sau:

~~~json
{
  "subjectId": "usr_91af",
  "evidenceReferences": ["ev_02c1"],
  "verifiedAttributes": {
    "email": "member@example.test"
  },
  "identityProofingStatus": "partial"
}
~~~

Trong ví dụ này, **partial** chỉ biểu thị rằng ứng dụng đã kiểm chứng một phần thuộc tính theo **chính sách nội bộ**. Nó không phải mức assurance chuẩn hóa và tuyệt đối không được diễn giải thành “đã xác minh danh tính pháp lý”.

Lưu ý thiết kế:

- Chỉ đặt **kết quả và tham chiếu** trong hồ sơ nghiệp vụ khi có thể; tài liệu/ảnh hoặc dữ liệu sinh trắc cần khu vực lưu trữ riêng với kiểm soát truy cập chặt chẽ, thời hạn giữ và chính sách xóa.
- Không lưu mật khẩu, private key, OTP hoặc mã khôi phục dưới dạng bằng chứng danh tính; chúng thuộc cơ chế xác thực và quản lý bí mật.
- Bản ghi cần biết **claim nào** được xác minh, **bởi nguồn nào**, **theo chính sách nào**, **vào thời điểm nào** và **còn hiệu lực không**, thay vì chỉ có cờ boolean như “verified”.
- Trạng thái xác minh không tự cấp quyền quản trị. Hệ thống authorization vẫn phải xét principal, resource, action và policy tại thời điểm yêu cầu.

## 7. Phân biệt mức đảm bảo danh tính với mức đảm bảo xác thực

Các khung như **NIST SP 800-63** phân biệt nhóm yêu cầu liên quan đến kiểm chứng danh tính (*identity proofing / identity assurance*) và nhóm yêu cầu liên quan đến xác thực (*authentication assurance*). Đơn vị triển khai cần xem phiên bản tiêu chuẩn và quy định áp dụng, thay vì tự gán nhãn bảo đảm cho một giao thức hay tài liệu.

Một số tình huống giúp thấy rõ sự độc lập này:

| Tình huống | Điều đã biết về danh tính | Điều đã biết về lần đăng nhập |
| --- | --- | --- |
| Tài khoản diễn đàn ẩn danh dùng passkey | Chỉ biết định danh nội bộ; có thể chưa có họ tên thật | Có bằng chứng quyền kiểm soát khóa gắn với account; passkey hỗ trợ chống phishing |
| Hồ sơ khách hàng đã được identity proofing kỹ nhưng đăng nhập bằng mật khẩu yếu | Đã xác minh một tập thuộc tính danh tính theo chính sách | Lần xác thực hiện tại có thể chưa đạt yêu cầu bảo vệ tài khoản |
| Người dùng vào ứng dụng bằng SSO OIDC | Có assertion về subject và các claim IdP cung cấp | Phụ thuộc phương thức, thời điểm xác thực và chính sách IdP; ứng dụng phải xác minh token |
| Dịch vụ dùng mTLS với chứng chỉ hợp lệ | Danh tính workload/chủ thể được ánh xạ qua hệ PKI | Bên kia đã chứng minh quyền kiểm soát khóa tương ứng trong handshake, nếu kiểm tra đúng |

**Passkey:** WebAuthn giúp relying party xác minh rằng thiết bị/authenticator kiểm soát khóa riêng đã đăng ký, cùng sự ràng buộc với RP ID, origin, challenge và các cờ theo chính sách. Điều này giúp chống phishing và replay của thử thách, nhưng **không tự chứng minh tên, ngày sinh hoặc tư cách pháp lý**.

**ID token:** OIDC ID token là assertion từ issuer đến client, cần kiểm tra chữ ký, issuer, audience, thời hạn và ràng buộc phiên/yêu cầu như nonce khi áp dụng. Claim email được đánh dấu verified trong một hệ IdP thường chỉ có ý nghĩa về **cách IdP xác minh email theo hợp đồng của IdP**. Không tự nâng nó thành chứng nhận pháp lý hoặc dùng ID token như access token cho API.

**Chứng chỉ:** X.509 có thể chứa danh tính hoặc thuộc tính theo PKI, nhưng chỉ khi hệ thống tin đúng CA, xác minh chain, key usage, thời hạn, thu hồi và ánh xạ subject phù hợp. Một chứng chỉ không mặc nhiên xác lập quyền truy cập đến tài nguyên cụ thể.

**MFA:** Thêm OTP hoặc yếu tố sinh trắc vào lần đăng nhập có thể nâng độ chắc chắn về kiểm soát credential theo chính sách, nhưng không tự làm tăng độ tin cậy của thuộc tính danh tính vốn chưa được kiểm chứng.

## 8. Ba kịch bản thiết kế thực tế

### 8.1. Đăng ký tài khoản học tập với email

**Mục tiêu:** xác lập tài khoản duy nhất và có kênh liên lạc kiểm soát được.

1. Người dùng nhập email và yêu cầu đăng ký.
2. Server tạo thử thách ngẫu nhiên, một lần, có thời hạn; gửi qua email, áp dụng giới hạn yêu cầu.
3. Người dùng xác nhận thử thách trong ngữ cảnh flow đã được ràng buộc; server tiêu thụ thử thách để chống replay.
4. Hệ thống đánh dấu **email được xác minh tại thời điểm T**, cấp subject ID nội bộ và cho đăng ký passkey hoặc phương thức đăng nhập.
5. Nếu người dùng đổi email, hệ thống yêu cầu kiểm tra lại email mới và có thể xác thực lại phiên cũ theo mức rủi ro.

**Kết luận đúng:** người dùng chứng minh đã kiểm soát mailbox vào thời điểm xác minh. Không nên hiện trạng thái “Đã xác minh danh tính pháp lý” chỉ nhờ email.

### 8.2. Nền tảng phải kiểm chứng thuộc tính pháp lý

**Mục tiêu:** ví dụ phải xác nhận tên và tuổi theo chính sách nghiệp vụ hoặc yêu cầu pháp luật áp dụng.

- Hệ thống chọn nguồn chứng cứ phù hợp: giấy tờ hoặc cơ sở dữ liệu/nhà cung cấp xác minh được chấp nhận.
- Kiểm tra tài liệu và nguồn cấp, đồng thời xác minh người cung cấp có liên hệ hợp lệ với danh tính đó.
- Xử lý trường hợp hồ sơ không khớp hoặc nghi gian lận bằng bước bổ sung/kiểm tra thủ công, cùng quy trình khiếu nại có thể kiểm soát.
- Chỉ lưu các thuộc tính cần thiết (ví dụ kết quả “đủ tuổi” nếu đó là điều nghiệp vụ cần), provenance, thời điểm kiểm chứng và kết quả; bảo vệ/xóa dữ liệu gốc theo quy định và thời hạn áp dụng.
- Sau khi proofing, người dùng vẫn phải đăng ký credential và xác thực cho các lần truy cập tiếp theo.

**Rủi ro nổi bật:** giấy tờ giả, giấy tờ thật bị đánh cắp, ghép mặt, deepfake, sai sót đối chiếu và nhân viên xử lý nhầm. Không một tín hiệu đơn lẻ nào bảo đảm loại bỏ hết các rủi ro này.

### 8.3. Định danh dịch vụ nội bộ bằng mTLS

**Mục tiêu:** service A chỉ chấp nhận kết nối từ service B đã đăng ký.

1. Hạ tầng cấp chứng chỉ phù hợp cho workload B qua một quy trình cấp phát có xác thực.
2. A hoặc gateway kiểm tra chain, validity, mục đích sử dụng, tên workload mong đợi, thu hồi theo thiết kế và chứng minh sở hữu private key trong TLS.
3. Subject/SAN đã được xác minh được ánh xạ tới principal nội bộ, ví dụ “inventory-reader”.
4. Authorization kiểm tra principal đó có được gọi endpoint và tài nguyên cụ thể hay không.
5. Khi B rời cụm hoặc bị thay thế, hệ thống cần quản lý vòng đời chứng chỉ và quyền liên quan.

Chứng chỉ ở đây là bằng chứng về danh tính workload trong hệ PKI được tin cậy; không phải chứng cứ về danh tính pháp lý của một nhân viên vận hành B.

## 9. Threat model: bằng chứng có thể bị tấn công thế nào?

| Mối đe dọa | Tình huống | Kiểm soát cần cân nhắc |
| --- | --- | --- |
| Giả mạo hoặc sửa bằng chứng | Ảnh giấy tờ chỉnh sửa; metadata bị can thiệp | Kiểm tra nguồn và tính toàn vẹn; xác minh với hệ thống phát hành khi có cơ sở và quyền |
| Dùng bằng chứng thật của người khác | Tài liệu đánh cắp, dữ liệu rò rỉ | Quy trình ràng buộc đúng người với evidence; kiểm tra rủi ro, xử lý sai khác |
| Replay | Dùng lại email link, OTP, response WebAuthn, đoạn video cũ | Nonce/challenge có hạn, gắn phiên/giao dịch, tiêu thụ một lần khi cần |
| Phishing hoặc chiếm đoạt kênh | Kẻ xấu kiểm soát mailbox/OTP hoặc trang IdP giả | Passkey/WebAuthn khi phù hợp, xác minh origin/issuer, cảnh báo thay đổi thông tin |
| Giả mạo xác nhận liên kết | Ghép account nội bộ với tài khoản IdP có email trùng | Ràng buộc theo cặp issuer + subject và quy trình linking có xác thực/đồng ý |
| Tự khai gian thuộc tính | Người dùng sửa tuổi hoặc vai trò trong request | Chỉ tin dữ liệu đã kiểm chứng từ bên có thẩm quyền, không tin giá trị client gửi |
| Deepfake hoặc giả sinh trắc | Video/ảnh giả vượt kiểm tra nhận diện | Nhiều lớp kiểm tra, đánh giá sai số, review thủ công, cập nhật phòng thủ |
| Nguồn tin cậy bị xâm nhập hoặc lỗi | IdP phát sai claim, CA cấp sai chứng chỉ | Giới hạn trust anchor, kiểm toán nguồn, chính sách thu hồi và phản ứng sự cố |
| Lạm dụng quy trình phục hồi | Dùng email reset hoặc recovery yếu để chiếm tài khoản proofed | Chính sách recovery tương xứng, step-up, thông báo và thu hồi phiên |

Tấn công không chỉ nhằm đánh cắp bằng chứng. Một đối thủ có thể lợi dụng các **đường vòng**, ví dụ đăng ký lại passkey, đổi email, tự ghép danh tính liên kết hoặc khôi phục tài khoản bằng phương thức yếu hơn luồng đăng nhập thông thường.

## 10. Liên kết danh tính và khôi phục tài khoản

Trong federation, ứng dụng có thể gặp hai assertion cùng email nhưng với **issuer khác nhau**. Hai assertion đó không tự động chỉ cùng một người. Khóa liên kết an toàn thường cần cặp **issuer + subject** đã kiểm chứng; liên kết với tài khoản nội bộ phải dựa vào một quy trình phù hợp, chẳng hạn người dùng đã đăng nhập tài khoản hiện có và xác thực thêm khi cần.

Ví dụ sai về tư duy:

~~~text
if idp.email == existingAccount.email:
    attachNewIdentity(existingAccount)
~~~

Tư duy phù hợp hơn là:

~~~text
validateFederationAssertion()
resolveIdentityByTrustedIssuerAndSubject()

if linkingRequested:
    requireAuthorizedAccountLinkFlow()
    verifyControlOfExistingAccount()
    verifyNewExternalIdentity()
    applyRiskAndReauthenticationPolicy()
    recordAuditEvent()
~~~

Đây là **pseudocode**, không phải mã triển khai hoàn chỉnh. Cách liên kết và yêu cầu bảo vệ cụ thể phụ thuộc mô hình đe dọa.

Với khôi phục tài khoản, một email reset hoặc mã khôi phục chứng minh **quyền điều khiển một kênh/phương thức khôi phục**, không nhất thiết đạt cùng mức chắc chắn với lần identity proofing ban đầu. Trước khi cho phép thay đổi credential quan trọng, hệ thống cần xét rủi ro chiếm đoạt tài khoản và bảo vệ tương xứng: giới hạn thử, challenge một lần, thời hạn ngắn, thông báo qua kênh cũ nếu khả thi, luân chuyển/thu hồi phiên và token, cùng review thủ công cho trường hợp nhạy cảm.

Nếu có sự kiện nghi gian lận hoặc thay đổi thuộc tính quan trọng (đổi tên pháp lý, thay tư cách tổ chức), ứng dụng cũng cần quy tắc **re-proofing** hoặc xác minh lại từng claim. Không nên xem việc đã được proofing một lần là đủ cho toàn bộ vòng đời danh tính.

## 11. Quyền riêng tư và trách nhiệm vận hành

Bằng chứng danh tính có thể bao gồm dữ liệu nhạy cảm: số giấy tờ, địa chỉ, ảnh khuôn mặt, ngày sinh. Kiểm chứng danh tính tốt phải đồng thời quản lý nguy cơ lộ lọt và dùng sai dữ liệu.

1. **Tối thiểu hóa:** chỉ xin thuộc tính cần cho quyết định. Nếu chỉ cần điều kiện “trên 18 tuổi”, cân nhắc lưu kết quả xác nhận thay vì toàn bộ ảnh giấy tờ khi hợp pháp và phù hợp mục đích.
2. **Mục đích và minh bạch:** thông báo rõ lý do thu thập, bên xử lý và cách sử dụng; có cơ sở xử lý dữ liệu phù hợp quy định áp dụng.
3. **Bảo vệ dữ liệu:** mã hóa khi truyền và lưu, phân quyền, ghi audit truy cập, giới hạn truy xuất của nhân viên và nhà cung cấp.
4. **Vòng đời dữ liệu:** đặt thời hạn giữ, cơ chế xóa hoặc ẩn danh khi thích hợp; không kéo dài thời hạn lưu dữ liệu gốc chỉ vì dễ debug.
5. **Chống rò rỉ qua vận hành:** không đưa ảnh giấy tờ, OTP, passkey assertion, ID token thô hoặc thuộc tính nhạy cảm vào log, URL, thông báo lỗi hay công cụ phân tích.
6. **Quy trình xử lý ngoại lệ:** có cơ chế sửa sai, kiểm tra thủ công và đánh giá tỷ lệ nhận nhầm/từ chối nhầm; hạn chế phân biệt đối xử do chất lượng dữ liệu hoặc thuật toán.
7. **Giảm tin cậy bên thứ ba không cần thiết:** nếu thuê nhà cung cấp proofing, cần biết họ xác minh claim gì, phương pháp và giới hạn nào; không tự nâng nhãn “verified” của họ thành mức đảm bảo cao nhất.

Những cơ chế hỗ trợ **tiết lộ có chọn lọc** trong hệ credential số có thể giúp chứng minh một thuộc tính mà không cần tiết lộ toàn bộ hồ sơ. Tuy nhiên, chữ ký, freshness, trạng thái thu hồi, holder binding và sự chấp nhận của verifier vẫn phải được kiểm tra; định dạng “verifiable” không tự bảo đảm nội dung đúng hoặc bên phát hành đáng tin.

## 12. Checklist kiểm tra thiết kế bằng chứng danh tính

| Câu hỏi khi review | Dấu hiệu thiết kế đúng |
| --- | --- |
| Hệ thống muốn xác minh **claim cụ thể** nào? | Mỗi yêu cầu evidence gắn với mục đích, không thu thập thừa |
| Evidence hỗ trợ chính xác điều gì? | Không suy từ “email verified” sang “họ tên verified” |
| Ai phát hành và vì sao nguồn đó đáng tin? | Issuer/provenance và phạm vi tin cậy được mô tả rõ |
| Evidence có thật, toàn vẹn, còn hạn không? | Validation bao gồm hiệu lực, chữ ký/nguồn và trạng thái thu hồi khi cần |
| Đã gắn bằng chứng với đúng chủ thể chưa? | Có bước verification/holder binding riêng |
| Bằng chứng có thể bị dùng lại hoặc giả mạo không? | Challenge gắn flow, có TTL và chống replay theo giao thức |
| Kết quả được lưu thế nào? | Có kết luận theo claim, nguồn, thời điểm, policy; dữ liệu gốc được giới hạn |
| Khi IdP, email hoặc tài khoản thay đổi thì sao? | Có chính sách account linking, re-proofing, recovery và thu hồi |
| Mức proofing có bị nhầm với mức authentication? | Hồ sơ danh tính và phiên/MFA được đánh giá theo hai cơ chế riêng |
| Có xử lý false match, false rejection và gian lận? | Có đường review, sửa sai và audit an toàn |
| Bên nhận có thể tin assertion/token đến mức nào? | Xác minh issuer, audience, signature, thời hạn, ngữ cảnh và quyền |
| Quyền riêng tư đã được kiểm soát chưa? | Tối thiểu hóa, bảo vệ, giới hạn lưu giữ, phân quyền và cơ sở xử lý |

### Ba câu hỏi luyện tập

**Tình huống A:** Một người đăng nhập bằng passkey và thay đổi trường “họ tên” trong trang hồ sơ. Hệ thống có thể tuyên bố họ tên đã được kiểm chứng không? **Không**, trừ khi có quy trình identity proofing độc lập xác nhận thuộc tính ấy. Passkey chỉ giúp xác thực quyền kiểm soát khóa của tài khoản.

**Tình huống B:** Hai IdP gửi về cùng email và đều cho biết người dùng đã đăng nhập thành công. Có được tự gộp hai subject không? **Không**. Cần xác thực assertion của từng issuer, kiểm tra subject và áp dụng flow liên kết danh tính được cho phép.

**Tình huống C:** Một chứng chỉ client hợp lệ được gửi qua request, nhưng ứng dụng chưa xác minh private key và chưa kiểm tra subject có thuộc workload dự kiến không. Có nên gán principal nội bộ và quyền đọc dữ liệu? **Không**. Chưa đủ bằng chứng ràng buộc cũng như chưa có kết luận authorization.

## 13. Ghi nhớ

**Bằng chứng danh tính** là cơ sở để đánh giá một **tuyên bố về chủ thể hoặc thuộc tính**. Muốn tin kết luận, cần biết nguồn phát hành, phạm vi, tính xác thực, hiệu lực, khả năng bị giả mạo và cách bằng chứng gắn với đúng chủ thể. Một hồ sơ có thể được proofing tốt nhưng vẫn cần authentication mạnh cho mỗi lần truy cập; một lần authentication mạnh không tự tạo ra thuộc tính danh tính chưa được kiểm chứng.

Khi thiết kế luồng thực tế, hãy diễn đạt chính xác: **“Đã xác minh claim nào, bằng evidence nào, từ nguồn nào, lúc nào, đối với subject nào, cho mục đích nào?”** Sau đó mới quyết định credential, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản cần bảo đảm điều gì để chống phishing, replay và lạm dụng đăng nhập.
