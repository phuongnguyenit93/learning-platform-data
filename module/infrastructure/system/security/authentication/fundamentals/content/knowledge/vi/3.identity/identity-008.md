# Bằng chứng proofing

## 1. Bằng chứng trong identity proofing là gì?

**Identity proofing** là quá trình đánh giá bằng chứng để xác lập mức tin cậy rằng một **người hoặc chủ thể đang đăng ký** thực sự gắn với danh tính và các thuộc tính mà họ khai báo. *Identity evidence* có thể là giấy tờ từ cơ quan có thẩm quyền, hồ sơ của một nguồn đáng tin cậy, chứng thực điện tử, hoặc xác nhận đã được một tổ chức thực hiện theo chính sách phù hợp.

Ví dụ: người dùng nhập họ tên, ngày sinh và số căn cước. Đó là **thông tin khai báo (claim)**. Ảnh giấy tờ họ tải lên mới là **bằng chứng được nộp**. Để có kết luận đáng tin, hệ thống vẫn phải đánh giá nguồn gốc, tính thật, hiệu lực và liệu người nộp có phải chủ thể được giấy tờ mô tả không. Việc có ảnh rõ nét hoặc OCR đọc đúng ký tự tự nó **không** hoàn thành proofing.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, cần phân biệt:

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity proofing** | Ai là chủ thể của danh tính hoặc thuộc tính được khai báo, và bằng chứng đáng tin đến mức nào? | Đánh giá giấy tờ, tra nguồn dữ liệu có thẩm quyền, liên kết với người đăng ký. |
| **Enrollment / credential binding** | Credential được gắn với đúng danh tính đã kiểm chứng bằng cách nào? | Cho phép đăng ký passkey cho đúng tài khoản sau khi proofing thành công. |
| **Authentication** | Lần truy cập này có chứng minh được quyền sử dụng credential đã gắn không? | Kiểm tra mật khẩu, MFA, passkey hoặc chứng chỉ. |
| **Authorization** | Danh tính đã xác thực có được thao tác trên tài nguyên hiện tại không? | Kiểm tra quyền xem hồ sơ khách hàng cụ thể. |

Một **passkey chống phishing** chỉ chứng minh khả năng sử dụng khóa đã đăng ký theo giao thức; bản thân passkey không chứng minh họ tên pháp lý của người sử dụng. Ngược lại, giấy tờ được proofing vào ngày đăng ký không chứng minh người đang nắm session cookie hôm nay vẫn là người đó.

## 2. Xác định điều cần chứng minh trước khi chọn giấy tờ

Không phải mọi ứng dụng đều cần chứng minh danh tính dân sự:

- **Diễn đàn hoặc công cụ cộng đồng:** có thể chấp nhận bút danh; chỉ cần xác nhận kênh liên lạc để phục hồi, tùy rủi ro.
- **Hệ thống nhân sự nội bộ:** cần chứng minh người đăng ký là nhân viên của tổ chức và liên kết đúng với mã nhân sự. Nguồn HR có thể có thẩm quyền về tình trạng lao động nhưng không mặc nhiên xác nhận mọi thuộc tính dân sự.
- **Dịch vụ đòi hỏi danh tính pháp lý:** có thể cần kiểm chứng họ tên, ngày sinh, thông tin giấy tờ và mối liên hệ giữa người nộp với giấy tờ theo quy định và mức rủi ro áp dụng.
- **Workload hoặc dịch vụ máy-máy:** có thể cần chứng minh dịch vụ thuộc hệ thống nào, khóa riêng được cấp cho đúng workload và tổ chức có quyền vận hành; đây là bằng chứng kỹ thuật, không phải giấy tờ tùy thân.

Đầu vào của bài toán proofing nên nêu được năm yếu tố:

1. **Subject:** người, tổ chức hay workload nào cần được nhận diện?
2. **Claim:** thuộc tính nào phải được chứng minh và thuộc tính nào chỉ dùng liên hệ?
3. **Relying party:** hệ thống nào sẽ dựa vào kết quả để cấp tài khoản hoặc dịch vụ?
4. **Threat model:** nguy cơ giả giấy tờ, mạo danh, chiếm email, thay kết quả proofing hoặc mạo danh nhân viên hỗ trợ?
5. **Mức bảo đảm mong muốn:** chi phí chấp nhận sai, hậu quả từ chối nhầm, yêu cầu pháp lý và khả năng tiếp cận của người dùng?

Ví dụ, công ty cần biết một người là nhân viên hợp lệ để cấp tài khoản nội bộ. Yêu cầu mọi nhân viên tải thêm căn cước khi HR đã xác minh phù hợp có thể gây thu thập thừa dữ liệu nhạy cảm; quan trọng hơn là gắn đúng người đang đăng ký vào bản ghi HR.

## 3. Các loại bằng chứng và giới hạn của chúng

| Bằng chứng / tín hiệu | Có thể hỗ trợ chứng minh | Điều nó không tự chứng minh |
| --- | --- | --- |
| Căn cước hoặc hộ chiếu vật lý | Các thông tin thể hiện trên giấy tờ nếu giấy tờ được xác thực, còn phù hợp. | Người gửi ảnh là chủ giấy tờ; ảnh không bị sao chép hay sửa đổi. |
| Giấy tờ có chip hoặc chứng thực có chữ ký số | Tính toàn vẹn dữ liệu và nguồn ký, nếu chuỗi tin cậy, phạm vi và hiệu lực được kiểm tra đúng. | Người xuất trình là chủ thể được mô tả, nếu chưa có bước liên kết. |
| Hồ sơ từ nguồn có thẩm quyền như HR | Thuộc tính mà nguồn đó có trách nhiệm quản lý, tại thời điểm kiểm tra. | Những thuộc tính ngoài phạm vi nguồn; người nộp đúng là người trong hồ sơ. |
| Chứng thực thuộc tính từ đối tác / IdP | Claim mà issuer khẳng định theo chính sách và phạm vi tin cậy. | Chính sách proofing của issuer đáp ứng mọi yêu cầu của hệ thống tiếp nhận. |
| OTP qua email hoặc số điện thoại | Khả năng kiểm soát kênh liên hệ tại thời điểm xác minh. | Danh tính pháp lý, quyền sở hữu số vĩnh viễn, tư cách nhân viên. |
| Hóa đơn, sao kê, thư gửi tới địa chỉ | Một số liên hệ với địa chỉ hoặc tài khoản, tùy nguồn và cách kiểm tra. | Người nộp chắc chắn là chủ tài khoản hoặc cư trú lâu dài tại địa chỉ. |
| Selfie/video, kiểm tra hiện diện (liveness) | Có thể hỗ trợ liên kết người đang tham gia với ảnh tham chiếu đáng tin. | Giấy tờ tham chiếu là thật, giao dịch là tự nguyện, hoặc mọi kiểu deepfake đều bị chặn. |
| Mật khẩu, TOTP, passkey hoặc chứng chỉ đã đăng ký | Quyền kiểm soát credential theo giao thức xác thực. | Credential được gắn với danh tính đã proofing đúng cách. |

**Nhiều tài liệu không đồng nghĩa nhiều nguồn độc lập.** Hai ảnh của cùng một giấy tờ, hoặc hai dịch vụ cùng đọc một bản ghi gốc, có thể lặp lại cùng một lỗi. Cần xét nguồn phát hành, độ tin cậy, tính độc lập và thuộc tính mà từng bằng chứng thực sự xác nhận.

## 4. Thu thập, validation và verification là ba công đoạn khác nhau

**Thu thập (collection):** xác định loại bằng chứng được chấp nhận, yêu cầu dữ liệu tối thiểu, thông báo mục đích và bảo vệ dữ liệu khi nhận, truyền và lưu. Một tệp hợp lệ về định dạng chưa chắc là bằng chứng hợp lệ.

**Evidence validation:** kiểm tra *bản thân bằng chứng* có được phát hành từ nguồn đáng tin, có nguyên vẹn, có dấu hiệu giả mạo hoặc bị sửa, còn hiệu lực và phù hợp với mục đích không. Với chữ ký số, phải xác thực chữ ký và khóa/issuer tin cậy, kiểm tra phạm vi, thời hạn và trạng thái thu hồi khi cơ chế cho phép. OCR chỉ trích xuất ký tự; nó không chứng minh những điều này.

**Identity verification:** kiểm tra *mối liên hệ giữa người đang đăng ký và chủ thể được mô tả trên bằng chứng*. Có thể xác minh trực tiếp, đối chiếu người hiện diện với ảnh tham chiếu đã tin cậy, hoặc dùng giao thức số cho phép chứng minh quyền kiểm soát credential đã được liên kết với danh tính. Chỉ biết số giấy tờ và ngày sinh thường không đủ: thông tin đó có thể bị lộ.

Trong trường hợp cần xác minh một thuộc tính hiện tại, hệ thống còn phải kiểm tra **nguồn có thẩm quyền về thuộc tính ấy**. Chẳng hạn, giấy tờ dân sự không cho biết người đó còn là nhân viên; bản ghi HR lại không tự chứng minh họ đang giữ quyền truy cập ứng dụng cụ thể.

~~~mermaid
flowchart TD
    A["Khai báo danh tính và thuộc tính"] --> B["Nộp bằng chứng"]
    B --> C["Validation: nguồn, tính thật, toàn vẹn và hiệu lực"]
    C --> D{"Bằng chứng đủ tin cậy?"}
    D -- "Không" --> X["Từ chối hoặc kiểm tra thủ công"]
    D -- "Có" --> E["Verification: liên kết với người nộp"]
    E --> F{"Liên kết đủ tin cậy?"}
    F -- "Không/chưa rõ" --> X
    F -- "Có" --> G["Đánh giá chính sách và lưu kết quả tối thiểu"]
    G --> H["Tạo danh tính và gắn credential"]
    H --> I["Authentication cho các lần truy cập tiếp theo"]
~~~

Nếu một ứng dụng chỉ gọi OCR, thấy tên trên ảnh khớp ô nhập rồi đặt trạng thái “đã xác minh”, ứng dụng mới đối chiếu hai nguồn dữ liệu **do cùng người nộp kiểm soát**. Nó chưa xác thực giấy tờ và chưa liên kết đáng tin cậy người nộp với người trên giấy tờ.

## 5. Điều gì quyết định chất lượng proofing?

Mức tin cậy là kết quả của **toàn bộ quy trình**, phụ thuộc vào:

- **Nguồn và phạm vi:** ai cấp hoặc quản lý thông tin, nguồn có thẩm quyền về claim nào?
- **Khả năng chống giả mạo:** kiểm tra chữ ký, đặc điểm bảo mật hoặc nguồn độc lập, hay chỉ nhìn ảnh?
- **Độ mới:** giấy tờ đã hết hạn, credential bị thu hồi, thuộc tính nghề nghiệp đã thay đổi chưa?
- **Liên kết với chủ thể:** bằng chứng có thật nhưng người đăng ký có phải chủ thể của bằng chứng không?
- **Độc lập của các nguồn:** nhiều tín hiệu có thực sự bổ sung thông tin không?
- **Bảo vệ quy trình:** có chống replay, can thiệp phiên, chiếm kênh và lợi dụng đường hỗ trợ không?
- **Xử lý ngoại lệ:** ai được duyệt thủ công, dùng tiêu chí nào và có dấu vết kiểm toán không?

Ví dụ, để kết luận “Người đang đăng ký là nhân viên X của tổ chức Y”, cần cả việc nguồn nhân sự có thẩm quyền xác nhận X đang làm việc, dữ liệu được kiểm tra qua kênh đáng tin, người đăng ký được liên kết đúng với X và kết quả còn mới đủ cho quyết định. Làm mạnh bước kiểm tra hồ sơ **không thể tự bù** cho bước liên kết người nộp còn yếu.

Không nên tự gán một tỷ lệ “chắc chắn 99%” bằng cách cộng điểm OCR, khớp khuôn mặt và số lượng giấy tờ. Nếu tổ chức sử dụng thang bảo đảm định danh theo chuẩn hoặc quy định, cần đáp ứng **đầy đủ tiêu chí của thang áp dụng**, không suy ra mức bảo đảm chỉ từ loại giấy tờ hoặc tên nhà cung cấp.

## 6. Proofing trực tiếp và từ xa

**Trực tiếp:** người được ủy quyền có thể quan sát người xuất trình và kiểm tra giấy tờ vật lý, nhưng vẫn có rủi ro giấy tờ giả, sai sót, thông đồng, bỏ qua bước hoặc đánh giá thiếu nhất quán.

**Từ xa:** thuận tiện hơn nhưng phụ thuộc camera, thiết bị, đường truyền, phần mềm và nguồn xác minh. Rủi ro gồm ảnh giấy tờ bị đánh cắp, replay video, camera ảo, deepfake, chiếm phiên đăng ký, thay kết quả và sử dụng lại bằng chứng của người khác.

| Nguy cơ | Cách giảm thiểu theo rủi ro | Giới hạn |
| --- | --- | --- |
| Video/ảnh ghi trước, replay | Challenge ràng buộc với phiên, nonce một lần, kiểm tra chống phát lại. | Deepfake, can thiệp kênh camera hoặc đánh cắp phiên có thể vượt qua một lớp kiểm soát. |
| Giấy tờ giả hoặc sửa | Xác thực thuộc tính bảo mật, chữ ký số, đối chiếu nguồn có thẩm quyền nếu được phép. | Ảnh rất rõ không chứng minh giấy tờ thật. |
| Mạo danh nhân viên hỗ trợ | Phân quyền, xác thực nhân viên, phê duyệt ngoại lệ và kiểm toán. | Quy trình thủ công có thể thành đường vòng yếu nhất. |
| Dò dữ liệu hoặc gửi hồ sơ hàng loạt | Giới hạn tốc độ, phát hiện tự động hóa và phản hồi không làm lộ trạng thái hồ sơ. | Chặn một IP không ngăn hết tấn công phân tán. |
| Từ chối nhầm người hợp lệ | Kiểm tra thủ công và kênh thay thế an toàn, tiêu chí rõ, quyền khiếu nại. | Không được hạ tiêu chí đến mức tạo đường tắt dễ chiếm tài khoản. |

**Liveness hoặc face matching không phải bằng chứng đủ của danh tính.** Kết quả chỉ hỗ trợ một phần của bài toán hiện diện hoặc tương đồng khuôn mặt, phụ thuộc chất lượng nguồn, mô hình và khả năng chống giả mạo. Cần đánh giá sai số, tránh loại trừ người dùng không thể dùng công nghệ này và có phương án thay thế với mức bảo đảm tương ứng.

## 7. Ranh giới tin cậy: từ bằng chứng đến credential và phiên

~~~mermaid
sequenceDiagram
    participant U as Người đăng ký
    participant P as Dịch vụ proofing
    participant S as Nguồn dữ liệu
    participant I as Dịch vụ identity
    participant A as Ứng dụng
    U->>P: Khai báo và nộp bằng chứng
    P->>S: Kiểm tra nguồn/thuộc tính khi được phép
    S-->>P: Kết quả xác minh
    P->>P: Liên kết người nộp với bằng chứng
    P-->>I: Kết quả proofing có phạm vi và mức tin cậy
    I->>U: Đăng ký credential cho đúng subject
    U->>I: Đăng nhập bằng credential
    I-->>U: Session hoặc token
    U->>A: Yêu cầu kèm session/token
    A->>A: Xác thực phiên/token và kiểm tra quyền
    A-->>U: Trả kết quả theo quyết định quyền
~~~

Các ranh giới cần kiểm soát rõ:

1. **Người nộp → proofing:** chống thay tài liệu, giả camera, replay và hoán đổi dữ liệu giữa phiên đăng ký.
2. **Proofing → nguồn:** xác thực nguồn, phân quyền tra cứu, xác thực phản hồi và độ mới; không tin kết quả do trình duyệt tự gửi.
3. **Proofing → identity service:** truyền kết quả qua kênh đã xác thực, gồm subject, thuộc tính, chính sách, thời điểm và tham chiếu kiểm toán; client không được tự gắn cờ `verified: true`.
4. **Identity service → credential:** gắn passkey, mật khẩu, chứng chỉ hoặc phương thức khác vào **đúng subject được phê duyệt**; chống chiếm luồng enrollment và đăng ký thiết bị.
5. **Identity service → ứng dụng:** token hoặc session chứng minh một phiên truy cập theo giao thức, thời gian và phạm vi tương ứng; ứng dụng vẫn cần kiểm tra issuer, audience, hiệu lực, quyền và trạng thái hiện tại khi cần.

Một claim `identity_verified` trong token nếu không định nghĩa rõ **thuộc tính nào được kiểm chứng, chính sách nào được áp dụng và khi nào** có thể gây hiểu lầm. “Đã xác minh email” khác xa “đã xác minh danh tính pháp lý”, và cả hai đều không tự quyết định authorization.

## 8. Chứng thực bên thứ ba và liên kết danh tính

Hệ thống có thể nhận kết quả proofing từ nhà cung cấp danh tính (IdP) hoặc một đơn vị cấp chứng thực. Đây là **niềm tin được ủy thác có điều kiện**: bên tiếp nhận phải biết nguồn khẳng định điều gì, chứng cứ gốc được kiểm tra ra sao, chính sách nào đã áp dụng và kết quả còn phù hợp với mục đích không.

Chẳng hạn, claim `email_verified: true` của IdP thường chỉ nói rằng họ đã kiểm tra quyền kiểm soát địa chỉ email theo quy trình của họ. Claim đó không tự chứng minh người dùng đang giữ vai trò trong doanh nghiệp, là chủ sở hữu giấy tờ dân sự, hay có quyền truy cập một tenant cụ thể. Ngay cả claim `department: finance` cũng có thể chỉ được sao chép từ dữ liệu hồ sơ khai báo nếu hệ thống không biết nguồn cập nhật.

Khi liên kết tài khoản, hệ thống nên:

1. Xác minh token/chứng thực bằng giao thức thích hợp: chữ ký hoặc khóa tin cậy, issuer, audience, thời hạn và các ràng buộc bảo vệ luồng tương ứng.
2. Ánh xạ danh tính bằng định danh ổn định trong **phạm vi issuer**; với OpenID Connect thường là cặp `(iss, sub)`. Không tự động nối tài khoản chỉ vì hai địa chỉ email trùng nhau.
3. Kiểm tra tenant, quyền liên kết và trạng thái chủ thể từ nguồn có thẩm quyền của tổ chức.
4. Ghi rõ *provenance* (nguồn gốc), thời điểm và phạm vi claim đã xác minh; xử lý khi thuộc tính thay đổi hoặc chứng thực bị thu hồi.

Với bằng chứng có chữ ký số, chữ ký hợp lệ chỉ cho biết dữ liệu phù hợp với khóa đã ký. Vẫn phải tin đúng issuer, hiểu chính sách của họ, kiểm tra thời hạn/thu hồi khi khả dụng và kiểm tra người đang trình bằng chứng có gắn với chủ thể được chứng thực hay không.

## 9. Proofing khi khôi phục tài khoản và thay đổi credential

Khôi phục tài khoản thường cần thiết lập lại niềm tin rằng **người yêu cầu có quyền quay về tài khoản cũ**. Nếu ban đầu hệ thống buộc proofing kỹ nhưng cho phép bỏ hết passkey/MFA chỉ sau một cuộc gọi với vài câu hỏi dễ đoán, đường khôi phục trở thành lối tắt cho kẻ tấn công.

Ví dụ: tài khoản được proofing qua giấy tờ và đăng ký passkey. Người dùng mất thiết bị. Dịch vụ không nên xem việc người gọi biết ngày sinh, số căn cước hoặc tên mẹ là đủ bằng chứng — các dữ kiện đó có thể có trong dữ liệu rò rỉ. Tùy mức rủi ro, có thể dùng credential dự phòng được thiết lập trước, xác minh qua kênh độc lập hoặc một quy trình proofing lại tương xứng với tài khoản.

Các kiểm soát quan trọng gồm:

- Liên kết yêu cầu khôi phục với tài khoản cũ bằng nguồn tin cậy và chính sách rõ ràng.
- Chống replay đối với mã, đường dẫn hoặc challenge; giới hạn lượt thử và giám sát bất thường.
- Xác thực nhân viên hỗ trợ, phân tách quyền và phê duyệt ngoại lệ nhạy cảm; không cho phép bỏ qua toàn bộ proofing bằng một thao tác thủ công tùy ý.
- Thông báo thay đổi bảo mật qua kênh độc lập khi phù hợp, cân nhắc trì hoãn hoặc rà soát thêm khi rủi ro cao.
- Cân nhắc thu hồi credential/phiên bị nghi lộ và có phương án cứu trợ người dùng hợp lệ.

**Bằng chứng cũng có vòng đời.** Tình trạng lao động, tên, giấy tờ, địa chỉ và quan hệ với tổ chức có thể thay đổi. Các trường hợp như đổi chủ tài khoản, thu hồi quyền đại diện, nghi chiếm tài khoản hoặc thay đổi thuộc tính rủi ro cao có thể cần cập nhật nguồn hoặc **re-proofing**. Không nên mặc định dữ liệu proofing lúc đăng ký còn đúng mãi về sau.

## 10. Thiết kế dữ liệu kết quả và trạng thái proofing

Ứng dụng nên phân biệt **bằng chứng thô có dữ liệu nhạy cảm** với **kết quả xác minh tối thiểu** mà dịch vụ khác được phép sử dụng. Kết quả tốt có ngữ nghĩa rõ: subject nào, thuộc tính nào, nguồn nào, chính sách nào, thời điểm nào và trạng thái quyết định.

Ví dụ minh họa một cấu trúc **nội bộ**, không phải giao thức hay tiêu chuẩn bắt buộc:

~~~json
{
  "subjectId": "employee_123",
  "decision": "approved",
  "policyId": "employee-onboarding-v2",
  "verifiedClaims": [
    {
      "name": "employmentStatus",
      "value": "active",
      "source": "trusted-hr-record",
      "verifiedAt": "2026-11-20T09:30:00Z"
    }
  ],
  "proofingMethod": "hr-record-and-controlled-enrollment",
  "decisionAt": "2026-11-20T09:31:00Z",
  "auditRef": "proof_7b9a"
}
~~~

Ví dụ này chỉ thể hiện kết quả xác minh **tư cách nhân viên** theo một chính sách giả định, không phải kết quả xác minh danh tính pháp lý. `subjectId` phải được tạo và ánh xạ từ phía tin cậy, không nhận tùy ý từ client. Tham chiếu `auditRef` tránh phải đưa ảnh giấy tờ và sinh trắc học vào log ứng dụng.

Một state machine giúp tránh đường xử lý “mặc định thành công”:

~~~text
RECEIVED
  -> EVIDENCE_VALIDATION
  -> APPLICANT_BINDING
  -> POLICY_EVALUATION
     -> APPROVED
     -> REJECTED
     -> MANUAL_REVIEW

Chỉ quyết định APPROVED do hệ thống tin cậy xác nhận,
với chính sách và subject rõ ràng, mới kích hoạt cấp credential.
~~~

Trong triển khai, cần chú ý:

| Yêu cầu | Lý do |
| --- | --- |
| Đánh giá và phê duyệt ở máy chủ | Trình duyệt không được tự gửi `approved` hay tự quyết định mức bảo đảm. |
| Ràng buộc yêu cầu, bằng chứng, quyết định và enrollment vào đúng phiên/subject | Chống hoán đổi tài liệu, dùng lại kết quả và cấp credential cho nhầm người. |
| Quyền tối thiểu, kiểm toán và phê duyệt ngoại lệ | Giảm khả năng nhân viên hoặc dịch vụ trung gian lạm dụng chức năng duyệt. |
| Nhật ký ghi chính sách, nguồn, thời điểm, kết quả và lý do cần thiết | Có căn cứ điều tra mà không lưu dữ liệu nhận dạng thừa trong log. |
| Mã hóa, kiểm soát truy cập, giới hạn lưu giữ, xóa an toàn | Bằng chứng thường chứa dữ liệu cá nhân hoặc sinh trắc học nhạy cảm. |
| Xử lý kết quả không chắc chắn và đo lường sai số | Tránh biến điểm mô hình thành khẳng định tuyệt đối, hỗ trợ người dùng hợp lệ bị từ chối nhầm. |
| Hạn chế nộp hàng loạt, replay và tiết lộ trạng thái hồ sơ | Bảo vệ dịch vụ proofing khỏi lạm dụng, dò thông tin và đánh cắp danh tính. |

Khi thiết kế API, kết quả proofing từ dịch vụ chuyên trách phải đi qua kênh đã xác thực và được kiểm tra quyền; client chỉ được gửi yêu cầu và bằng chứng. Một trường kiểu `proofed=true` do frontend gửi lên **không thể** là căn cứ mở tài khoản có đặc quyền.

## 11. Hai tình huống thiết kế

### Tình huống A: cấp tài khoản nội bộ cho nhân viên mới

**Mục tiêu:** cấp tài khoản cho đúng người được HR tuyển vào đúng bộ phận.

**Bằng chứng:** bản ghi HR có thẩm quyền về nhân sự; bước liên kết người nhận lời mời với đúng hồ sơ (chẳng hạn kiểm tra trực tiếp do người được ủy quyền thực hiện, hoặc hình thức xác minh tương đương theo chính sách); bước đăng ký credential.

**Luồng xử lý:** xác nhận bản ghi HR đang hoạt động qua kênh tin cậy → liên kết đúng người đang enrollment với mã nhân sự → cấp định danh → cho đăng ký passkey → áp dụng quyền từng ứng dụng dựa trên vai trò và trạng thái hiện tại. Khi chuyển bộ phận hoặc nghỉ việc, quyền và phiên phải được xử lý theo chính sách.

**Lỗi thường gặp:** chỉ gửi liên kết đăng ký qua email rồi xem mọi người bấm được liên kết là nhân viên hợp lệ. Email có thể bị chuyển tiếp, chiếm quyền hoặc thuộc tài khoản đã cấp lại; việc kiểm soát thư không tự chứng minh mối liên hệ với hồ sơ HR.

### Tình huống B: đăng ký khách hàng từ xa

**Mục tiêu:** xác lập độ tin cậy rằng khách hàng là người được giấy tờ mô tả, theo mức rủi ro dịch vụ.

**Bằng chứng:** giấy tờ phù hợp, kiểm tra tính thật và nguồn khi được phép, xác minh sự liên kết người nộp với bằng chứng, cơ chế xử lý không chắc chắn.

**Luồng xử lý:** bảo vệ phiên nộp hồ sơ → kiểm tra chứng cứ giấy tờ → kiểm tra người nộp và chống phát lại → đánh giá chính sách → phê duyệt hoặc chuyển kiểm tra thủ công → tạo danh tính và đăng ký credential. Khi khách hàng đăng nhập bằng passkey sau đó, các API vẫn phải kiểm tra token, quyền và hành động cụ thể.

**Giới hạn:** hình ảnh nét, OCR khớp và liveness thành công không thể bảo đảm tuyệt đối trước deepfake, nguồn bị sai, việc kiểm soát thiết bị hoặc người dùng bị lừa/cưỡng ép.

## 12. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có ảnh căn cước là đã proofing.” | Ảnh mới là đầu vào; cần validation, liên kết người nộp và quyết định theo chính sách. |
| “Hai tài liệu luôn mạnh hơn một tài liệu.” | Phải đánh giá nguồn, tính độc lập, tính hiện hành và ý nghĩa của mỗi bằng chứng. |
| “Email OTP xác nhận tên pháp lý của người này.” | OTP chủ yếu chứng minh quyền kiểm soát kênh liên hệ. |
| “OCR và khớp khuôn mặt là đủ.” | Chúng chỉ giải quyết từng phần và phụ thuộc tính thật của dữ liệu tham chiếu, sai số và khả năng chống giả mạo. |
| “Passkey mạnh nên tài khoản chắc chắn được proofing.” | Passkey xác thực credential; quy trình enrollment mới quyết định gắn nó vào danh tính nào. |
| “Đã proofing thì không cần kiểm tra quyền API.” | Authorization vẫn phải quyết định tài nguyên và hành động hiện tại. |
| “Tài khoản dùng cùng email tại hai IdP chắc chắn là một.” | Cần liên kết theo issuer, chủ thể ổn định, tenant và chính sách cụ thể. |
| “Chỉ cần proofing một lần mãi mãi.” | Nhiều thuộc tính và rủi ro thay đổi; có thể cần cập nhật hoặc re-proofing. |
| “Khôi phục chỉ cần biết thông tin trong hồ sơ.” | Thông tin đó có thể bị lộ và không đủ chứng minh người yêu cầu là chủ tài khoản. |

## 13. Checklist đánh giá một quy trình proofing

Trước khi triển khai đăng ký, liên kết danh tính hoặc khôi phục tài khoản, hãy trả lời:

1. Dịch vụ cần xác minh **đúng thuộc tính nào**, để phục vụ quyết định gì?
2. Ai có thẩm quyền về mỗi thuộc tính, bằng chứng được xác thực nguồn gốc, toàn vẹn và hiệu lực ra sao?
3. Người nộp được liên kết với chủ thể trên bằng chứng bằng phương thức nào?
4. Hệ thống đã xét tấn công giấy tờ giả, phishing, replay, deepfake, chiếm kênh, giả mạo hỗ trợ và thử hàng loạt chưa?
5. Khi bằng chứng thiếu, mâu thuẫn hoặc công nghệ tự động từ chối nhầm, có đường xử lý thủ công an toàn, có kiểm toán và phù hợp người dùng không?
6. Kết quả được truyền qua ranh giới tin cậy nào, có gắn đúng subject, phiên đăng ký và credential không?
7. Các ứng dụng dùng kết quả có hiểu **nguồn, thời điểm, phạm vi và chính sách** của những claim đã xác minh không?
8. Dữ liệu cá nhân có được tối thiểu hóa, mã hóa, giới hạn truy cập, lưu giữ và xóa đúng chính sách không?
9. Tình huống thuộc tính đổi, credential mất, IdP bị thu hồi hoặc tài khoản bị nghi chiếm được xử lý ra sao?
10. Phương án khôi phục có giữ được mức tin cậy cần thiết của danh tính, thay vì tạo đường vòng dễ hơn đăng nhập chính không?

**Kết luận:** Bằng chứng proofing là căn cứ để quyết định **danh tính và thuộc tính cụ thể** tại một thời điểm. Giá trị của bằng chứng phụ thuộc nguồn phát hành, tính xác thực và hiện hành, khả năng liên kết với người nộp và an toàn của toàn bộ quy trình. Kết quả proofing giúp thiết lập danh tính để cấp credential; authentication, session/token và authorization vẫn phải bảo vệ mọi lần truy cập và hành động sau đó.
