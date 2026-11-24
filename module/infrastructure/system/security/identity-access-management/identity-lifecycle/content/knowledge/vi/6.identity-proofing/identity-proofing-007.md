# Xác minh trực tiếp trong Identity Proofing

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **xác minh trực tiếp (in-person identity proofing)** là gì, khác gì với đăng nhập, kiểm tra tài khoản và xác minh từ xa.
- Phân biệt ba hoạt động **phân giải danh tính (identity resolution)**, **kiểm tra bằng chứng (evidence validation)** và **xác minh chủ thể (identity verification)** trong một phiên tiếp nhận trực tiếp.
- Thiết kế quy trình kiểm tra con người và chứng cứ danh tính tại địa điểm xác minh, sau đó liên kết kết quả với bản ghi nhân sự và danh tính số trong IAM.
- Xử lý các trường hợp không khớp, nghi ngờ mạo danh, thiếu giấy tờ, yêu cầu hỗ trợ tiếp cận và ngoại lệ theo chính sách mà không tự ý cấp quyền.
- Giải thích mối liên hệ giữa identity proofing, **Joiner–Mover–Leaver (JML)**, **IdP, SSO, SCIM, RBAC/ABAC**, tài khoản đặc quyền, kiểm toán và thu hồi quyền truy cập tồn dư.

## 1. Xác minh trực tiếp là gì?

**Xác minh trực tiếp** là hình thức **identity proofing** trong đó người cần chứng minh danh tính **có mặt tại địa điểm xác minh** và tương tác trực tiếp với nhân sự hoặc quy trình được tổ chức ủy quyền. Mục tiêu là thiết lập mức tin cậy phù hợp rằng **người đang có mặt chính là chủ thể được gắn với hồ sơ hoặc bằng chứng danh tính đã kiểm tra**.

Ví dụ: nhân viên mới đến văn phòng nhận việc. Nhân sự được phân công kiểm tra hồ sơ tuyển dụng, kiểm tra bằng chứng định danh theo chính sách, đối chiếu người đang có mặt với thông tin và bằng chứng phù hợp, xử lý sai lệch, ghi nhận kết quả. Sau đó bộ phận IAM có căn cứ để kích hoạt danh tính và gắn phương thức xác thực cho đúng người.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, xác minh trực tiếp là một **kiểm soát đầu vào** cho vòng đời danh tính. Nếu xác minh sai ngay lúc Joiner, hệ thống có thể tạo account IdP, đồng bộ SCIM và cấp quyền RBAC/ABAC cho người không có thẩm quyền. Xác minh tốt giúp giảm rủi ro **gắn nhầm tài khoản, chiếm đoạt bước kích hoạt, cấp quyền sai người**; song vẫn cần kiểm soát Mover và Leaver để không tích lũy quyền hoặc giữ truy cập tồn dư.

**Điểm cần nhớ:** người có mặt tại quầy không tự động là người có danh tính hợp lệ. Tương tác mặt đối mặt chỉ tạo điều kiện thu thập và đối chiếu bằng chứng; chất lượng kết quả còn phụ thuộc quy trình, độ tin cậy bằng chứng, kỹ năng người kiểm tra và việc liên kết đúng bản ghi.

### 1.1. Phân biệt các khái niệm

| Khái niệm | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| **Identity resolution** | Hồ sơ đang nói tới chủ thể nào; có trùng/nhầm người không? | Nối ứng viên với mã nhân sự đã duyệt |
| **Evidence validation** | Bằng chứng được xuất trình có phù hợp, đáng tin và còn hiệu lực không? | Kiểm tra bằng chứng theo yêu cầu của chính sách |
| **Identity verification** | Người có mặt có đúng là chủ thể gắn với bằng chứng/hồ sơ không? | Đối chiếu người xuất trình với thông tin có thể kiểm tra |
| **Identity proofing** | Toàn bộ quy trình thiết lập mức tin cậy về danh tính | Phân giải, kiểm tra, đối chiếu, xử lý sai lệch, ghi kết quả |
| **Authentication** | Người đăng nhập sau này có chứng minh sở hữu yếu tố xác thực đã đăng ký không? | Sử dụng passkey/MFA để vào IdP |
| **Authorization** | Danh tính đã xác thực được phép làm gì? | Truy cập hệ thống theo role và chính sách |
| **Provisioning** | Tài khoản/quyền được tạo và đồng bộ tới đâu? | Cấp account qua SCIM/API |

Một người có thể **được proofing chính xác**, nhưng **không được phép đăng nhập** vì hợp đồng chưa có hiệu lực hoặc tài khoản đã bị khóa. Ngược lại, một người có thể đang sử dụng phiên đăng nhập hợp lệ nhưng vẫn cần tái kiểm tra vì phát hiện **sai liên kết danh tính** trong hồ sơ.

### 1.2. Trực tiếp so với các kênh khác

- **Trực tiếp tại địa điểm:** người và người kiểm tra được tổ chức ủy quyền cùng có mặt; có thể xem bằng chứng vật lý, kiểm tra theo quy trình và hỗ trợ đăng ký yếu tố xác thực.
- **Từ xa có người hỗ trợ theo thời gian thực:** tương tác qua video hoặc kênh có giám sát; cần kiểm soát riêng đối với hình ảnh, phiên làm việc và bằng chứng. Đây không phải một buổi trực tiếp tại quầy.
- **Tự phục vụ từ xa:** người dùng gửi thông tin và bằng chứng qua ứng dụng; việc xác minh dựa trên cơ chế tự động hoặc hỗn hợp.

Không có kênh nào mặc nhiên bảo đảm độ tin cậy cao hơn trong mọi hoàn cảnh. Việc chọn kênh, loại bằng chứng, phương pháp đối chiếu và mức bảo đảm cần dựa trên **rủi ro, chính sách và yêu cầu áp dụng**.

## 2. Vai trò của xác minh trực tiếp trong IAM lifecycle

IAM quản lý **ai được phép có quyền nào, vì lý do gì và đến khi nào**. Xác minh trực tiếp tập trung vào câu hỏi **danh tính của chủ thể đã được thiết lập đáng tin đến mức nào**. Kết quả có thể trở thành một tín hiệu để quyết định tạo/kích hoạt tài khoản, nhưng không thay thế phê duyệt nghiệp vụ.

| Giai đoạn JML | Tình huống liên quan | Vai trò của xác minh trực tiếp |
| --- | --- | --- |
| **Joiner** | Nhân viên hoặc nhà thầu bắt đầu quan hệ làm việc | Liên kết đúng người với hồ sơ hợp lệ trước khi đăng ký credential và cấp quyền |
| **Mover** | Đổi vai trò, đổi đơn vị, mở rộng đặc quyền | Thường tính lại quyền; có thể yêu cầu tái xác minh nếu rủi ro hoặc bằng chứng có vấn đề |
| **Leaver** | Hết hợp đồng hoặc nghỉ việc | Dữ liệu liên kết từ bước proofing giúp tìm mọi account để thu hồi; không cần xác minh trực tiếp để bắt đầu khóa |
| **Rehire / recovery** | Người cũ quay lại, khôi phục tài khoản nhạy cảm | Có thể cần xác minh lại để tránh gắn nhầm chủ thể, tái sử dụng credential hoặc quyền cũ |

Xác minh trực tiếp **không phải một bước bắt buộc cho mọi sự kiện JML**. Một lần chuyển phòng ban đơn thuần có thể không cần người dùng quay lại quầy; thay vào đó hệ thống dùng dữ liệu HRIS có thẩm quyền, phê duyệt và đối soát quyền. Yêu cầu tái xác minh cần có **trigger rõ ràng**, ví dụ nghi ngờ mạo danh, thất lạc thông tin xác thực quan trọng, tranh chấp định danh hoặc cấp quyền đặc biệt nhạy cảm.

### 2.1. Điều kiện cần có trước khi cấp quyền

Một sự kiện “proofing hoàn tất” nên **đồng thời thỏa mãn** các nhóm điều kiện sau, theo mức rủi ro:

1. **Nguồn nghiệp vụ hợp lệ:** bản ghi tuyển dụng, hợp đồng hoặc yêu cầu truy cập có người bảo lãnh/phê duyệt hợp lệ.
2. **Danh tính được kiểm tra theo chính sách:** bằng chứng và người xuất trình đã được xác minh đủ mức áp dụng.
3. **Liên kết đúng chủ thể:** hệ thống đã đối chiếu với định danh ổn định, xử lý các bản ghi trùng hoặc sai khác đáng kể.
4. **Trạng thái/thời gian hiệu lực phù hợp:** sự kiện Joiner đã đến thời điểm hoặc được phép chuẩn bị account với giới hạn rõ ràng.
5. **Quyền được quyết định độc lập:** role và entitlement phải dựa vào nhu cầu công việc, RBAC/ABAC, người phê duyệt và nguyên tắc quyền tối thiểu.

**Xác minh danh tính thành công không đồng nghĩa người đó được cấp quyền quản trị.**

## 3. Ai thực hiện và chịu trách nhiệm?

Một quy trình tại quầy thường cần ít nhất ba vai trò logic. Trong tổ chức nhỏ, một cá nhân có thể được giao nhiều nhiệm vụ nếu chính sách cho phép, nhưng việc tách trách nhiệm giúp giảm sai lệch và rủi ro lạm dụng.

| Vai trò | Trách nhiệm chính | Giới hạn cần duy trì |
| --- | --- | --- |
| **Nguồn hồ sơ có thẩm quyền** (HRIS, quản lý hợp đồng) | Xác nhận sự tồn tại của quan hệ làm việc, ngày hiệu lực, đơn vị, sponsor | Không coi việc ghi hồ sơ là bằng chứng người có mặt đã được kiểm tra |
| **Người xác minh được ủy quyền** | Thực hiện kiểm tra trực tiếp, đánh giá bằng chứng theo checklist, ghi nhận kết quả và ngoại lệ | Không tự cấp quyền ngoài chính sách hoặc xử lý vượt phạm vi chuyên môn |
| **IAM/IGA và quản trị hệ thống** | Liên kết danh tính, đăng ký thông tin xác thực, cấp/thu hồi account và quyền, đối soát | Không coi một dấu tích “đã gặp” là chứng cứ đầy đủ khi thiếu kiểm tra |

Với quyền có rủi ro rất cao, chính sách có thể yêu cầu **kiểm tra bổ sung, phê duyệt độc lập hoặc nguyên tắc hai người**. Người quản lý trực tiếp có thể xác nhận nhu cầu công việc nhưng không nên là nguồn duy nhất xác nhận danh tính nếu quy trình đã quy định bằng chứng độc lập.

### 3.1. Chuẩn bị cơ sở vật chất và công cụ

Địa điểm xác minh nên bảo đảm:

- Có nhân sự được **ủy quyền và đào tạo**, dùng quy trình hiện hành và kênh hỗ trợ khi gặp ngoại lệ.
- Không gian đủ riêng tư để tránh lộ giấy tờ, thông tin định danh hoặc thao tác đăng ký authenticator.
- Thiết bị làm việc được quản lý, tài khoản nhân viên xác minh có quyền tối thiểu và có log.
- Hệ thống tra cứu hồ sơ nguồn hoặc yêu cầu đã được phê duyệt; không dựa duy nhất vào ảnh chụp màn hình, email chuyển tiếp hay lời giới thiệu.
- Phương thức an toàn để ghi kết quả và chuyển sang IAM mà không cần sao chép giấy tờ vào các kênh trao đổi không được phép.
- Quy trình xử lý khi mất kết nối, lỗi hệ thống hoặc tình huống an toàn tại địa điểm; chưa đủ bằng chứng thì chưa mở quyền nhạy cảm.

## 4. Quy trình xác minh trực tiếp từ đầu đến cuối

Quy trình cụ thể thay đổi theo loại chủ thể và mức rủi ro. Luồng dưới đây là mẫu có thể áp dụng cho **nhân viên hoặc nhà thầu đến cơ sở làm việc**, sau khi được điều chỉnh theo chính sách tổ chức.

~~~mermaid
flowchart TD
  A["Có hồ sơ Joiner / yêu cầu hợp lệ"] --> B["Xác nhận người đến và mã hồ sơ"]
  B --> C["Phân giải danh tính và kiểm tra trùng"]
  C --> D["Tiếp nhận bằng chứng theo chính sách"]
  D --> E{"Bằng chứng phù hợp và hợp lệ?"}
  E -->|"Không / chưa rõ"| X["Tạm dừng, ghi ngoại lệ, chuyển xử lý"]
  E -->|"Có"| F["Đối chiếu người có mặt với bằng chứng"]
  F --> G{"Đủ tin cậy và đúng hồ sơ?"}
  G -->|"Không / chưa rõ"| X
  G -->|"Có"| H["Lưu kết quả proofing tối thiểu + audit"]
  H --> I{"Điều kiện nghiệp vụ và approval đủ?"}
  I -->|"Chưa"| Y["Chờ hiệu lực / chờ phê duyệt"]
  I -->|"Đủ"| J["Kích hoạt identity và đăng ký authenticator"]
  J --> K["Provisioning IdP / SCIM / ứng dụng"]
  K --> L["Đối soát account và quyền thực tế"]
~~~

### Bước 1 – Tiếp nhận yêu cầu hợp lệ

Trước khi gặp người xuất trình, hệ thống phải có hồ sơ nguồn hoặc yêu cầu kiểm tra:

- Danh tính cần xác minh và mã hồ sơ ổn định.
- Loại quan hệ: nhân viên, nhà thầu, thực tập sinh, khách được bảo lãnh.
- Ngày bắt đầu, đơn vị, người quản lý/sponsor và phạm vi cần cấp quyền.
- Kênh xác minh được chấp thuận cùng mức kiểm tra tương ứng rủi ro.

Không nên tạo một bản ghi nhân sự hợp lệ chỉ từ việc ai đó đến quầy và nói rằng họ sắp gia nhập tổ chức.

### Bước 2 – Xác định đúng hồ sơ và kiểm tra trùng

Người xác minh tra cứu bằng **mã tham chiếu được cấp qua kênh tin cậy**; sau đó đối chiếu với hồ sơ nguồn. Cần chú ý:

- Có nhiều hồ sơ gần giống nhau hoặc một người tái gia nhập không?
- Người đến có tên, tên thường dùng hoặc ký tự phiên âm khác với hệ thống không?
- Email đã được tái sử dụng cho người khác chưa?
- Hồ sơ được tạo cho một pháp nhân, nhà thầu hoặc đơn vị khác không?

**Không nên dùng tên hay email làm khóa duy nhất để gắn quyền.** Phát hiện trùng chưa đủ căn cứ thì phải xử lý ngoại lệ trước khi liên kết tài khoản hiện hữu.

### Bước 3 – Yêu cầu bằng chứng phù hợp

Người xác minh thực hiện đúng danh mục bằng chứng do chính sách và quy định áp dụng cho phép. Có thể bao gồm giấy tờ định danh được công nhận, bằng chứng quan hệ làm việc hoặc phương thức khác tương ứng mức rủi ro.

Cần phân biệt:

- **Bằng chứng về con người/chủ thể:** giúp nhận biết cá nhân được khai báo.
- **Bằng chứng về quan hệ làm việc:** cho biết tổ chức có lý do nghiệp vụ để cấp danh tính/role.
- **Phê duyệt truy cập:** quyết định cá nhân có cần quyền đối với tài nguyên cụ thể không.

Một thẻ nhân viên do doanh nghiệp từng cấp **không nhất thiết đủ** để chứng minh người đó vẫn còn làm việc; một hợp đồng được phê duyệt **không tự chứng minh** người tại quầy là đúng người trong hợp đồng.

### Bước 4 – Kiểm tra bằng chứng

Theo phạm vi được đào tạo và công cụ hợp lệ, nhân sự xác minh đánh giá:

1. Bằng chứng có thuộc **loại được chấp nhận**, hiện còn giá trị và phù hợp với mức kiểm tra không?
2. Các trường quan trọng có **nhất quán** với nguồn dữ liệu có thẩm quyền hoặc kết quả xác minh hợp lệ không?
3. Có dấu hiệu bất thường về tính toàn vẹn hoặc chất lượng khiến **không thể kết luận** không?
4. Nếu cần kiểm tra qua cơ quan/nguồn phát hành, tổ chức có quyền và kênh được phép để thực hiện không?
5. Khi thông tin không khớp, có quy trình xác minh bổ sung và người có trách nhiệm ra quyết định không?

**Đánh giá hình thức bằng mắt không thể tự bảo đảm giấy tờ là thật.** Không nên yêu cầu người kiểm tra đưa ra kết luận chắc chắn ngoài khả năng của công cụ và đào tạo. Trường hợp nghi vấn phải chuyển theo quy trình, tránh tự ý chỉnh sửa hồ sơ cho khớp.

### Bước 5 – Xác minh người xuất trình là đúng chủ thể

Người xác minh đối chiếu người có mặt với bằng chứng và hồ sơ theo phương pháp được phép. Điều cần xác lập không chỉ là “có giấy tờ” mà còn là **có căn cứ gắn giấy tờ/hồ sơ đó với người đang có mặt**.

Trong một số môi trường có thể sử dụng đối chiếu ảnh khuôn mặt hoặc công cụ sinh trắc học được chấp thuận. Việc này phải có cơ sở phù hợp, hạn chế truy cập dữ liệu, kiểm soát sai số và phương án thay thế khi người dùng không thể sử dụng phương thức đó.

**Không nên coi sinh trắc học là luôn chính xác.** Kết quả tự động cần ngưỡng, quy trình xử lý false match/false non-match và biện pháp kiểm tra khác theo chính sách. Với trường hợp không đáp ứng điều kiện thông thường, người kiểm tra cần hỗ trợ tiếp cận thay vì tự động loại bỏ người dùng hợp lệ.

### Bước 6 – Kết luận, ghi nhận và xử lý ngoại lệ

Một phiên xác minh nên có một trong ba kết quả logic:

- **VERIFIED:** đã đủ bằng chứng và điều kiện theo mức kiểm tra được yêu cầu.
- **PENDING / NEEDS_REVIEW:** còn thiếu dữ liệu, chưa thể kết luận, cần bổ sung hoặc xem xét.
- **REJECTED:** có cơ sở không chấp nhận theo quy trình và thẩm quyền áp dụng.

Không nên suy diễn **PENDING = gian lận**; thiếu giấy tờ, khác biệt tên hoặc lỗi kết nối có thể có nguyên nhân hợp lệ. Kết quả cần lưu tối thiểu thông tin để **truy vết ai kiểm tra, theo chính sách nào, khi nào và với kết luận gì**, đồng thời hạn chế dữ liệu cá nhân.

### Bước 7 – Gắn kết quả với identity và authenticator

Chỉ sau khi đã xác lập danh tính và các điều kiện nghiệp vụ cần thiết, hệ thống mới cho phép **binding** phương thức xác thực vào đúng identity hoặc account.

Ví dụ: người dùng đăng ký **passkey/FIDO2** trên thiết bị của chính họ theo hướng dẫn an toàn; hệ thống kiểm tra hoàn tất đăng ký cho đúng tài khoản. Nhân viên hỗ trợ không cần nhìn hay lưu mật khẩu, khóa riêng hoặc mã khôi phục của người dùng.

Kiểm tra quan trọng:

- Kết quả proofing còn đủ mới và áp dụng cho đúng chủ thể chưa?
- Bản ghi identityId và accountId có khớp người vừa xác minh không?
- Có rủi ro đăng ký credential vào một tài khoản khác vì tra cứu theo tên/email không?
- Nếu cần cấp credential ban đầu hoặc recovery code, việc bàn giao có chống lộ và xác định đúng người nhận không?
- Khi sự kiện hủy hoặc hết hiệu lực xuất hiện trong lúc xử lý, hệ thống có chặn kích hoạt sai không?

### Bước 8 – Cấp quyền và kiểm tra thực thi

IAM sử dụng identity đã xác minh kết hợp **status trong HRIS, ngày hiệu lực, workerType, role, approval** và chính sách để tạo tài khoản và cấp quyền. Sau đó cần đọc lại trạng thái tại IdP/ứng dụng.

Việc xác minh danh tính chỉ giải quyết **một điều kiện đầu vào**. Quyền vẫn phải đi qua **RBAC/ABAC, least privilege, SoD (phân tách nhiệm vụ)** và kiểm tra giới hạn thời gian nếu có.

## 5. Xác minh trực tiếp không đồng nghĩa tuyệt đối tin cậy

Một buổi xác minh diễn ra mặt đối mặt vẫn có thể có lỗi hoặc bị lợi dụng. Những nhóm rủi ro chính:

| Rủi ro | Cơ chế | Kiểm soát |
| --- | --- | --- |
| **Giả mạo hoặc sử dụng bằng chứng không hợp lệ** | Người không có thẩm quyền xuất trình bằng chứng sai hoặc không đủ tin cậy | Loại bằng chứng chấp nhận được, đào tạo, công cụ kiểm tra hợp lệ, quy trình escalations |
| **Đúng người, sai hồ sơ** | Gắn người đến với mã nhân sự khác do trùng tên/email | identityId/sourceRecordId ổn định, kiểm tra liên kết và trùng |
| **Đúng người, sai vai trò** | Nhân viên xác minh thành công nhưng được cấp quyền vượt nhu cầu | Tách proofing khỏi authorization, phê duyệt và least privilege |
| **Giả mạo nhân viên xác minh** | Người dùng bị dẫn tới quầy/kênh không được ủy quyền | Công bố điểm tiếp nhận hợp lệ, xác nhận trách nhiệm và audit |
| **Bỏ qua quy trình vì áp lực thời gian** | Phê duyệt thủ công thiếu bằng chứng, thao tác mở account khẩn | Luồng ngoại lệ có thẩm quyền, không cấp quyền nhạy cảm khi thiếu điều kiện |
| **Lỗi con người** | Nhập nhầm mã hồ sơ, bỏ qua kết quả chưa rõ | Checklist, xác nhận trường quan trọng, hỗ trợ kiểm tra độc lập khi cần |
| **Lộ dữ liệu cá nhân** | Ảnh giấy tờ gửi qua chat/email, log toàn bộ dữ liệu | Data minimization, kênh bảo vệ, phân quyền, retention |
| **Credential binding sai** | Đăng ký MFA/passkey cho account không đúng người | Xác minh identityId–accountId, tránh liên kết bằng email duy nhất |
| **Proofing cũ được dùng vô hạn** | Kết quả bị dùng lại sau phát hiện gian lận hoặc thay đổi trạng thái | Ngày xác minh, trigger tái xác minh, đánh giá rủi ro |
| **Thiếu dấu vết kiểm toán** | Không biết ai đã xác nhận danh tính và căn cứ nào | Quyền người xác minh, sự kiện có mã tương quan, log chống sửa trái phép |

Tính tin cậy của **bằng chứng** cũng không đồng nghĩa tính hợp lệ của **quyền**: ngay cả khi người đó có mặt và được đối chiếu chính xác, họ vẫn có thể là người đã nghỉ, đã hết hợp đồng hoặc không còn được bảo lãnh.

### 5.1. Tránh tấn công vào quy trình hỗ trợ

Những yêu cầu như “hồ sơ đang lỗi, mở tạm quyền admin”, “quản lý đã đồng ý qua điện thoại”, hoặc “cấp MFA vào thiết bị này giúp tôi” phải được đối chiếu với kênh phê duyệt được tổ chức công nhận. Người xác minh không nên tự cấp, chuyển nhượng hay khôi phục quyền truy cập dựa vào lời xác nhận chưa được kiểm tra.

Nếu có nghi ngờ mạo danh, nhân sự cần **giữ an toàn cho người và dữ liệu**, tạm dừng xử lý, ghi nhận sự kiện theo mức cần thiết, rồi chuyển tới bộ phận có thẩm quyền. Không nên tự tiến hành điều tra ngoài phạm vi công việc hoặc công khai thông tin cá nhân của người xuất trình.

## 6. Phân biệt các mức bảo đảm và chứng cứ

Trong identity proofing, **mức bảo đảm** phản ánh mức độ tin cậy mà quy trình được thiết kế để đạt, dựa trên yêu cầu về bằng chứng, nguồn xác minh và phương pháp thực hiện. Một số khung hướng dẫn, ví dụ các khuôn khổ bảo đảm danh tính số, phân biệt **identity assurance**, **authenticator assurance** và **federation assurance**.

Dù tổ chức có tham chiếu một khung tiêu chuẩn, **không thể suy ra mức bảo đảm chỉ từ câu “đã xác minh trực tiếp”**:

- Một buổi gặp mặt nhưng không đối chiếu bằng chứng hợp lệ có thể cho mức tin cậy thấp.
- Một quy trình từ xa được thiết kế chặt chẽ có thể đáp ứng mức tin cậy phù hợp cho một mục đích nhất định.
- Một quy trình xác minh con người đầy đủ vẫn cần **xác thực nhiều yếu tố** và cấu hình federation an toàn khi truy cập hệ thống.

Ví dụ đánh giá theo rủi ro:

| Trường hợp | Rủi ro điển hình | Hướng thiết kế |
| --- | --- | --- |
| Tiếp nhận nhân sự vào hệ thống nội bộ thông thường | Nhầm chủ thể, gắn sai account | Xác minh theo chính sách chung, gắn identityId, kiểm tra account binding |
| Đăng ký tài khoản đặc quyền truy cập dữ liệu nhạy cảm | Hậu quả lớn nếu xác minh sai | Kiểm tra chặt hơn, phê duyệt độc lập, PAM/JIT và ghi log |
| Khôi phục authenticator sau mất thiết bị | Kẻ khác chiếm bước recovery | Xác minh lại phù hợp rủi ro, hủy authenticator bị mất, đăng ký lại an toàn |
| Nhà thầu ngắn hạn cần vào ứng dụng giới hạn | Thiếu owner/ngày hết hạn | Xác minh chủ thể + sponsor + phạm vi và thời hạn quyền |

**Không có bảng quy đổi mặc định** kiểu “trực tiếp = mức 3” áp dụng cho mọi hệ thống. Điều kiện đạt từng mức phụ thuộc phiên bản tiêu chuẩn hoặc chính sách được tổ chức chấp nhận.

## 7. Bằng chứng, thông tin cá nhân và nguyên tắc thu thập tối thiểu

Xác minh trực tiếp thường đụng tới **dữ liệu định danh nhạy cảm**. Thu thập càng nhiều không đồng nghĩa xác minh càng tốt. Doanh nghiệp cần xác định **mục đích, cơ sở và thẩm quyền xử lý dữ liệu**, loại bằng chứng, nơi lưu, người xem và thời hạn giữ.

### 7.1. Phân biệt bằng chứng gốc với dữ liệu được phép lưu

| Thông tin | Mục đích | Cách xử lý cần cân nhắc |
| --- | --- | --- |
| Bằng chứng được xuất trình tại quầy | Đánh giá tính phù hợp và đối chiếu | Có thể chỉ kiểm tra mà không lưu bản sao, tùy chính sách |
| Kết quả kiểm tra | Chứng minh bước proofing đã được thực hiện | Lưu trạng thái, phiên bản chính sách, thời gian, người xác minh |
| Mã hồ sơ HRIS / identityId | Liên kết đúng người với account | Bảo đảm ổn định, hạn chế quyền thay đổi |
| Bản chụp giấy tờ | Có thể cần cho một số quy trình cụ thể | Chỉ thu thập khi thật sự được phép và cần thiết; mã hóa, kiểm soát truy cập, retention |
| Thông tin sinh trắc học | Có thể dùng cho so khớp theo phương thức được chấp thuận | Kiểm soát đặc biệt, cơ chế thay thế, giảm lưu trữ, xử lý sai lệch |
| Credential, private key, mã khôi phục | Dùng cho xác thực sau này | Không ghi trong hồ sơ proofing, không nhờ người xác minh lưu thay |

Một bản ghi chỉ gồm **loại bằng chứng và kết quả kiểm tra** đôi khi đủ cho mục đích kiểm toán; không nên chụp và lưu tất cả giấy tờ theo thói quen nếu không có yêu cầu rõ ràng.

### 7.2. Bảo vệ dữ liệu trong vận hành

- Chỉ cho người được phân công đọc hồ sơ đang xác minh; tách quyền xem bằng chứng khỏi quyền cấp đặc quyền.
- Che giấu hoặc giảm trường dữ liệu nhạy cảm trong dashboard, báo cáo và log.
- Truyền dữ liệu qua kênh bảo vệ; kiểm soát copy/export và các thiết bị dùng tại quầy.
- Xác định thời hạn lưu, hủy, quyền truy cập và xử lý yêu cầu dữ liệu theo quy định/chính sách áp dụng.
- Đảm bảo bản ghi kiểm toán được bảo vệ tính toàn vẹn, không tiết lộ bí mật hoặc toàn bộ giấy tờ.

## 8. Dữ liệu kết quả proofing nên trông như thế nào?

Một mô hình dữ liệu riêng cho **proofing result** giúp IAM sử dụng kết quả có điều kiện, không biến trường “verified=true” thành quyền truy cập vô điều kiện.

Ví dụ JSON **minh họa nội bộ**:

~~~json
{
  "proofingId": "proof-20261123-00042",
  "identityId": "person-48210",
  "sourceRecordId": "worker-91422",
  "subjectType": "HUMAN",
  "method": "IN_PERSON",
  "policyId": "employee-onboarding",
  "policyVersion": "v3",
  "requestedAssuranceProfile": "standard-workforce",
  "result": "VERIFIED",
  "verifiedAt": "2026-11-23T09:20:00+07:00",
  "verifierActorId": "staff-0031",
  "evidenceChecks": [
    {
      "category": "approved-identity-evidence",
      "result": "PASS"
    }
  ],
  "exceptionIds": [],
  "correlationId": "joiner-event-1872"
}
~~~

Đây **không phải schema tiêu chuẩn** và không chứa giấy tờ thật. Những hệ thống có yêu cầu nghiêm ngặt hơn có thể cần lưu thêm chứng cứ, lý do ngoại lệ hoặc bản ghi đánh giá độc lập, nhưng phải kiểm soát dữ liệu tương ứng.

**Nguyên tắc khi sử dụng kết quả:**

1. **Ràng buộc với đúng danh tính:** kết quả chỉ có giá trị cho identityId và nguồn hồ sơ đã được đối chiếu.
2. **Có nguồn xác minh:** phải biết nhân sự được ủy quyền nào thực hiện và chính sách phiên bản nào đã áp dụng.
3. **Có thời gian và ngữ cảnh:** kết quả cũ có thể cần đánh giá lại nếu có dấu hiệu gian lận hoặc yêu cầu bảo đảm thay đổi.
4. **Kết quả không tự cấp quyền:** chỉ là một điều kiện trong quá trình quyết định kích hoạt/cấp entitlement.
5. **Có thể thu hồi hoặc đánh dấu vô hiệu:** khi phát hiện sai hồ sơ hoặc bằng chứng, hệ thống phải hỗ trợ xử lý lại kết quả.

## 9. Kết nối xác minh trực tiếp với IdP, SSO, SCIM và RBAC/ABAC

### 9.1. IdP và đăng ký phương thức xác thực

Sau proofing, hệ thống quản trị danh tính liên kết người đã xác minh với account tại **Identity Provider (IdP)**, sau đó cho phép đăng ký authenticator theo chính sách. Đây là bước có rủi ro cao: nếu gắn nhầm authenticator, người khác có thể đăng nhập **nhân danh đúng account nhưng không phải đúng chủ thể**.

Kiểm soát gồm xác định rõ identityId–IdP accountId, tránh dùng email làm khóa duy nhất, bảo vệ quy trình kích hoạt, thông báo thay đổi authenticator và ghi log.

### 9.2. SSO

**Single Sign-On (SSO)** cho phép ứng dụng dựa vào IdP để xác thực thông qua quan hệ tin cậy. Một người đã proofing trực tiếp vẫn có thể bị từ chối SSO nếu account chưa đến ngày hiệu lực, MFA không đáp ứng hoặc chính sách bảo mật đang chặn truy cập.

SSO giải quyết việc chuyển kết quả xác thực và một số claim; **không thay thế bước xác minh ban đầu**, cũng không chứng minh ứng dụng đích đã áp đúng quyền.

### 9.3. SCIM và provisioning

**SCIM** hỗ trợ tạo, cập nhật, vô hiệu hóa user/group tại ứng dụng có tích hợp. Quy trình thường là:

~~~text
Người có mặt tại quầy
       |
       v
Proofing result = VERIFIED
       |
       v
Identity registry: đối chiếu HRIS + ngày hiệu lực
       |
       v
IAM/IGA: xác định quyền được phê duyệt
       |
       +--> IdP: account / authenticator
       |
       +--> SCIM/API: app account và group
       |
       +--> RBAC/ABAC: quyền theo role, thuộc tính, policy
       |
       v
Reconciliation: trạng thái account & quyền thực tế
~~~

Nếu ứng dụng chưa phản hồi hoặc từ chối cấp account, không nên coi việc proofing thành công là dấu hiệu provisioning hoàn tất. Tương tự, Leaver cần xử lý **phiên, token, account cục bộ và quyền riêng của ứng dụng** ngoài việc khóa IdP.

### 9.4. RBAC/ABAC và quyền tối thiểu

**RBAC** gán role theo nhu cầu công việc; **ABAC** áp chính sách dựa trên thuộc tính chủ thể, tài nguyên, hành động và ngữ cảnh. Một chính sách ví dụ có thể yêu cầu:

~~~text
ALLOW_READ_FINANCE_RECORD IF
    identity.proofingStatus == VERIFIED
    AND employment.status == ACTIVE
    AND subject.department == FINANCE
    AND subject.hasApprovedEntitlement("finance-reader")
    AND resource.ownerDepartment == FINANCE
ELSE DENY
~~~

Đây là **mã giả**, không phải policy engine thật. Điều kiện VERIFIED chỉ là một yếu tố; tính hợp lệ của quyền còn phụ thuộc trạng thái việc làm, phê duyệt, loại tài nguyên và độ mới thuộc tính. Khi Mover đổi department, các quyền cũ phải được **tính lại và thu hồi**, ngay cả khi kết quả proofing trước đó vẫn hợp lệ.

## 10. Các trường hợp đặc biệt và xử lý ngoại lệ

### 10.1. Khác biệt tên hoặc thông tin hồ sơ

Tên trong HRIS có thể khác với bằng chứng vì ký tự dấu, phiên âm, tên đã thay đổi hoặc lỗi nhập liệu. Không tự kết luận gian lận; cũng không tự sửa giấy tờ hoặc ép hệ thống bỏ qua sai lệch. Cần:

- Xác định trường nào là khóa ổn định, trường nào là thuộc tính hiển thị.
- Đối chiếu nguồn có thẩm quyền và thông tin bổ sung được chính sách cho phép.
- Ghi ngoại lệ và yêu cầu người có thẩm quyền xác nhận khi mức sai khác có thể dẫn đến nhầm chủ thể.
- Đảm bảo không liên kết account hoặc cấp entitlement cho đến khi có kết luận phù hợp.

### 10.2. Thiếu bằng chứng thông thường

Một người có thể chưa nhận được giấy tờ, giấy tờ đang được thay mới hoặc có khó khăn tiếp cận. Tổ chức cần quy định **phương án thay thế phù hợp** hoặc chuyển xét duyệt, thay vì tự ý bỏ qua quy trình. Phương án có thể gồm yêu cầu thêm bằng chứng khác, dùng nguồn xác minh được chấp nhận hoặc hoãn kích hoạt các quyền có rủi ro cho tới khi hoàn tất.

**Không có một bộ giấy tờ duy nhất phù hợp cho mọi đối tượng và quốc gia.** Danh mục được phép phải do tổ chức xác định theo yêu cầu áp dụng.

### 10.3. Người dùng cần hỗ trợ tiếp cận

Xác minh tại quầy cần tính tới người không thể sử dụng một phương thức thông thường vì hạn chế vận động, khả năng nghe/nhìn, khác biệt ngôn ngữ hoặc các yếu tố tiếp cận khác. Thiết kế nên có:

- Phương thức hỗ trợ giao tiếp và lịch hẹn phù hợp.
- Lối đi và thiết bị có thể tiếp cận.
- Lựa chọn bằng chứng hoặc cách đối chiếu tương đương khi được chính sách chấp nhận.
- Đảm bảo bên hỗ trợ không tự ý biết hoặc kiểm soát credential riêng tư của chủ thể.

Việc hỗ trợ tiếp cận cần duy trì mục tiêu **xác minh đúng chủ thể** và bảo vệ sự riêng tư.

### 10.4. Nhà thầu và người được bảo lãnh

Nhà thầu có thể không có bản ghi trong HRIS nhân viên. Quy trình phải đối chiếu với **nguồn hợp đồng/sponsor**, ngày bắt đầu và kết thúc, loại truy cập được yêu cầu và người chịu trách nhiệm gia hạn. Không cấp role của nhân viên nội bộ chỉ vì nhà thầu đã được proofing trực tiếp.

### 10.5. Tái tuyển dụng

Một người đã nghỉ và quay lại cần xác định rõ **quan hệ làm việc mới**, đánh giá liên kết với identity cũ và đăng ký credential theo chính sách hiện tại. Không tự động bật lại tài khoản đặc quyền, token cũ hoặc mọi role đã có ở lần làm việc trước.

### 10.6. Khôi phục tài khoản bị mất yếu tố xác thực

Khi người dùng mất thiết bị MFA, tổ chức có thể chọn xác minh trực tiếp để hỗ trợ khôi phục. Cần kiểm tra danh tính theo mức phù hợp, sau đó **vô hiệu hóa yếu tố thất lạc nếu cần, đăng ký yếu tố mới cho đúng account và thông báo thay đổi**. Buổi gặp mặt không đủ căn cứ để bỏ qua các điều kiện bảo vệ tài khoản đặc quyền.

### 10.7. Danh tính dịch vụ không xác minh “trực tiếp”

Service account, workload và máy móc không có bản thân con người để đến quầy proofing. Chúng cần quy trình **đăng ký owner, xác nhận workload/mục đích, kiểm soát nguồn tạo, cấp credential an toàn, định kỳ review và thu hồi**. Nếu người sở hữu dịch vụ nghỉ việc, cần chuyển giao owner và rà soát quyền/secret liên quan; không suy luận workload đã kết thúc chỉ vì người tạo ban đầu đã nghỉ.

## 11. Tình huống minh họa: nhân viên mới đến văn phòng

Giả sử nhân viên **Minh** dự kiến gia nhập bộ phận hỗ trợ khách hàng vào ngày 25/11/2026. HRIS đã ghi sự kiện Joiner với mã hồ sơ **worker-2081**, ngày có hiệu lực và người quản lý. Nhân viên đến văn phòng xác minh trực tiếp hai ngày trước khi bắt đầu.

### 11.1. Tiếp nhận

Nhân viên được ủy quyền kiểm tra mã hồ sơ từ quy trình tuyển dụng, xác nhận ngày bắt đầu **25/11**, quan hệ làm việc, trường thông tin cần thiết và yêu cầu proofing đã được phê duyệt.

### 11.2. Kiểm tra

Nhân viên xác minh thực hiện đối chiếu bằng chứng và người xuất trình theo chính sách, kiểm tra trùng identity và ghi kết quả **VERIFIED** vào bản ghi proofing; không lưu toàn bộ ảnh giấy tờ nếu chính sách không đòi hỏi.

**Quan trọng:** kết quả VERIFIED ngày 23/11 không có nghĩa tài khoản phải được mở đầy đủ từ ngày này. IAM có thể chuẩn bị account và đăng ký phương thức xác thực trong giới hạn cho phép, nhưng quyền sử dụng hệ thống nghiệp vụ cần tuân theo ngày hiệu lực và phê duyệt.

### 11.3. Kích hoạt

Đến 25/11, HRIS xác nhận ACTIVE và không có lệnh chặn khác. Bộ điều phối IAM kích hoạt account IdP, triển khai MFA và cấp nhóm Support theo RBAC. Ứng dụng CRM nhận provisioning qua SCIM; IAM kiểm tra lại trạng thái account và quyền đã áp dụng.

### 11.4. Chuyển vai trò và nghỉ việc

Sau ba tháng, Minh chuyển sang bộ phận quản lý chất lượng. Proofing trực tiếp trước đó giúp IAM biết đúng chủ thể, nhưng **Mover vẫn phải thu hồi quyền CRM Support không còn phù hợp**. Khi Minh nghỉ việc, liên kết identityId với các account sẽ giúp tìm những tài khoản phải vô hiệu hóa, khóa phiên và thu hồi token theo khả năng từng ứng dụng.

**Bài học của tình huống:** proofing xây dựng lòng tin vào **chủ thể**, còn JML và authorization duy trì sự phù hợp của **quyền truy cập theo thời gian**. Hai việc liên quan nhưng không thay thế cho nhau.

## 12. Kiểm toán và chỉ số đánh giá

### 12.1. Dấu vết tối thiểu cho một phiên trực tiếp

Nên có khả năng trả lời:

- Danh tính nào và hồ sơ nguồn nào đã được kiểm tra?
- Buổi kiểm tra diễn ra **khi nào, ở đâu hoặc qua điểm tiếp nhận nào**, theo quy trình/phiên bản nào?
- Nhân viên nào được ủy quyền đã thực hiện, ai phê duyệt ngoại lệ nếu có?
- Danh mục bằng chứng nào đã được kiểm tra và kết quả gì; có phải lưu bản sao hay không?
- Khi nào kết quả được dùng để gắn account/authenticator và kích hoạt quyền?
- Có phát hiện sai lệch sau này, cần thu hồi kết quả proofing hoặc truy cập đã cấp không?

Log phải đủ truy vết mà không chứa bí mật, toàn bộ thông tin giấy tờ hoặc dữ liệu sinh trắc học không cần thiết. Các hệ thống cần bảo vệ tính toàn vẹn, quyền xem và thời hạn lưu giữ.

### 12.2. Chỉ số cần theo dõi

| Chỉ số | Cách diễn giải | Giá trị quản trị |
| --- | --- | --- |
| **Tỷ lệ proofing hoàn tất hợp lệ** | Số phiên đủ tiêu chí VERIFIED / số phiên phải xử lý | Năng lực hoàn tất trong phạm vi chính sách |
| **Thời gian từ yêu cầu đến quyết định** | Từ khi yêu cầu đủ điều kiện đến kết quả VERIFIED/PENDING/REJECTED | Phát hiện nút thắt trong onboarding |
| **Tỷ lệ ngoại lệ** | Phiên cần kiểm tra bổ sung / tổng phiên | Đánh giá chất lượng dữ liệu và thực thi |
| **Tỷ lệ nối trùng/sai identity** | Trường hợp phát hiện tài khoản gắn nhầm hoặc hồ sơ trùng / tổng trường hợp đã đối soát | Đo rủi ro identity resolution |
| **Tỷ lệ binding thất bại** | Đăng ký authenticator/account không khớp identity hoặc phải sửa | Kiểm soát rủi ro chiếm tài khoản |
| **Quyền được mở trước ngày hiệu lực** | Tài khoản/entitlement vượt giới hạn trước ngày Joiner | Phát hiện cấp quyền sớm |
| **Số ngoại lệ quá hạn** | Ngoại lệ chưa có quyết định sau thời hạn chính sách | Kiểm soát tồn đọng rủi ro |
| **Tỷ lệ tái xác minh hợp lệ** | Trường hợp phải tái proofing và hoàn tất theo chính sách | Theo dõi recovery và rủi ro thay đổi |

Các chỉ số cần phân loại theo **nhóm người dùng, loại bằng chứng, địa điểm, mức rủi ro và khả năng tiếp cận** để tránh tối ưu hóa tốc độ bằng cách bỏ qua kiểm tra hoặc tạo bất lợi cho những người cần phương thức hỗ trợ.

## 13. Bảng kiểm tra triển khai quy trình xác minh trực tiếp

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Có nguồn HRIS/hợp đồng hoặc yêu cầu hợp lệ trước buổi gặp không? | Hồ sơ có mã tham chiếu, owner, ngày hiệu lực |
| Đã xác định mức kiểm tra theo rủi ro chưa? | Chính sách theo loại danh tính và tài nguyên |
| Người xác minh có được ủy quyền không? | Danh sách/quyền nhân viên và đào tạo |
| Có chống trùng và nhầm hồ sơ không? | identityId bền vững, quy trình match/merge |
| Bằng chứng được chọn có phù hợp không? | Danh mục được chấp thuận và kết quả kiểm tra |
| Có đối chiếu đúng người với bằng chứng không? | Kết luận phiên theo phương pháp đã quy định |
| Khi không đủ bằng chứng có dừng và chuyển xử lý không? | Kết quả PENDING/REJECTED, owner ngoại lệ |
| Có giảm dữ liệu cá nhân được lưu không? | Chính sách thu thập, truy cập, lưu giữ |
| Authenticator được gắn vào đúng account không? | Bản ghi liên kết identityId–accountId, log binding |
| Quyền sau xác minh có cần approval/role không? | RBAC/ABAC, chính sách least privilege và phê duyệt |
| Account/quyền có được mở đúng thời điểm không? | Kiểm tra effectiveAt và trạng thái HRIS |
| Có thể phát hiện lỗi SCIM/provisioning không? | Reconciliation và xử lý queue lỗi |
| Có thể thu hồi quyền khi Mover/Leaver không? | Account inventory, đối soát và bằng chứng deprovision |
| Có xử lý recovery, rehire và contractor không? | Luồng riêng và người chịu trách nhiệm |
| Có thể chứng minh kết quả proofing và quyền hiệu lực? | Audit trail nối proofing, binding, cấp quyền, thu hồi |

## 14. Những nhầm lẫn thường gặp

1. **“Đã gặp trực tiếp tức là danh tính đã xác minh.”** Cần bằng chứng phù hợp, kiểm tra tính hợp lệ và đối chiếu đúng người.
2. **“Xác minh thành công tức là được cấp mọi quyền theo yêu cầu.”** Authorization cần phê duyệt và nguyên tắc quyền tối thiểu riêng.
3. **“Một lần proofing đủ mãi mãi.”** Khi xuất hiện nghi vấn, khôi phục tài khoản quan trọng hoặc thay đổi điều kiện tin cậy, có thể cần tái xác minh theo chính sách.
4. **“Có tên và email khớp là nối đúng account.”** Tên có thể trùng và email có thể đổi/tái sử dụng; cần định danh ổn định và quy tắc liên kết.
5. **“Càng lưu nhiều ảnh giấy tờ càng an toàn.”** Lưu dữ liệu không cần thiết tăng nguy cơ lộ thông tin; phải cân nhắc mục đích và yêu cầu áp dụng.
6. **“IdP khóa tài khoản là mọi phiên ứng dụng kết thúc.”** Cần kiểm tra phiên, token, credential và quyền cục bộ tại hệ thống đích.
7. **“Tài khoản dịch vụ cũng đi qua xác minh trực tiếp.”** Danh tính phi con người cần kiểm soát đăng ký và ownership riêng.

## 15. Câu hỏi tự đánh giá

1. Vì sao chứng minh người đến quầy đúng danh tính và chứng minh người đó được quyền vào hệ thống tài chính là hai quyết định khác nhau?
2. Ba khâu **identity resolution**, **evidence validation**, **identity verification** khác nhau ở điểm nào?
3. Nếu hồ sơ HRIS ghi nhận ngày bắt đầu là ngày mai nhưng proofing đã VERIFIED hôm nay, IAM có nên mở toàn bộ quyền ngay không? Vì sao?
4. Một nhân viên có tên trùng với người đã nghỉ và email cũ vừa được cấp lại. Cần kiểm tra gì trước khi liên kết tài khoản?
5. Những loại thông tin nào nên lưu trong proofing result để kiểm toán mà không phải giữ toàn bộ giấy tờ?
6. Một người đánh mất yếu tố MFA và yêu cầu đăng ký lại ở quầy. Những rủi ro nào xuất hiện tại bước account binding?
7. Một nhà thầu được xác minh trực tiếp nhưng hợp đồng không có ngày kết thúc. Quy trình IAM cần xử lý gì?
8. Tại sao proofing không thay thế việc thu hồi quyền khi nhân viên chuyển phòng ban hoặc rời tổ chức?
9. Khi có sai lệch bằng chứng nhưng chưa đủ căn cứ kết luận mạo danh, người xác minh nên ghi trạng thái nào và tiếp tục ra sao?
10. Tài khoản IdP đã bị khóa trong Leaver nhưng SaaS vẫn còn refresh token. Việc proofing trước đây có giúp xác định các account cần thu hồi như thế nào?

## 16. Tổng kết

**Xác minh trực tiếp** là một phương thức identity proofing nhằm thiết lập cơ sở tin cậy rằng người có mặt là đúng chủ thể của hồ sơ được kiểm tra. Quy trình đáng tin phải có **nguồn yêu cầu hợp lệ, kiểm tra bằng chứng, đối chiếu người–hồ sơ, xử lý ngoại lệ, kết quả có thể kiểm toán và liên kết an toàn với identity/account**. Phương thức gặp mặt không tự bảo đảm mức tin cậy; chất lượng đến từ thiết kế và thực thi kiểm soát.

Trong quản lý vòng đời danh tính **Joiner–Mover–Leaver**, kết quả proofing hỗ trợ tạo/kích hoạt danh tính đúng người và đăng ký authenticator an toàn. **IdP/SSO** quản lý xác thực; **SCIM/API** đồng bộ account; **RBAC/ABAC** xác định quyền theo công việc và ngữ cảnh; **reconciliation và audit** xác minh việc cấp–đổi–thu hồi đã thực thi. Khi người dùng chuyển vai trò hoặc rời tổ chức, việc tiếp tục quản lý quyền, session và token là cần thiết để ngăn **quyền truy cập tồn dư**, kể cả khi danh tính ban đầu đã được xác minh trực tiếp.
