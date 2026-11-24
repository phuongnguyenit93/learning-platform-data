# Xác minh danh tính (Identity proofing) trong vòng đời IAM

**Xác minh danh tính (identity proofing)** là quy trình thu thập, kiểm tra và đối chiếu bằng chứng để thiết lập mức độ tin cậy rằng một người thực sự gắn với danh tính đang khai báo. Trong môi trường doanh nghiệp, quy trình có thể bắt đầu từ hồ sơ tuyển dụng, hợp đồng đối tác hoặc một yêu cầu cấp tài khoản, rồi kết thúc bằng kết quả được ghi nhận để hệ thống quản lý danh tính quyết định bước đăng ký và cấp quyền tiếp theo.

Bài thuộc chương **Identity proofing** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trọng tâm là xác minh một danh tính đủ tin cậy trước khi tạo và cấp quyền, đồng thời duy trì độ tin cậy khi chủ thể chuyển vai trò hoặc rời tổ chức theo mô hình **Joiner–Mover–Leaver (JML)**. Kết quả xác minh liên quan trực tiếp đến Identity Provider (**IdP**), Single Sign-On (**SSO**), provisioning qua **SCIM**, kiểm soát quyền **RBAC/ABAC**, danh tính dịch vụ, kiểm toán và ngăn quyền truy cập tồn dư.

Giả sử một người tự nhận là nhân viên mới của bộ phận Tài chính và yêu cầu truy cập hệ thống thanh toán. Việc người đó sở hữu một email hoặc biết một mật khẩu chưa chứng minh họ là nhân viên được tuyển dụng. Tổ chức cần xác minh đúng người, đúng hồ sơ, đúng nguồn phê duyệt trước khi kích hoạt tài khoản và cấp quyền nhạy cảm. Tuy nhiên, **xác minh danh tính thành công cũng chưa đồng nghĩa người đó được cấp mọi quyền**.

## 1. Phân biệt identity proofing với đăng nhập và phân quyền

| Khái niệm | Câu hỏi phải trả lời | Ví dụ | Kết quả thường gặp |
| --- | --- | --- | --- |
| **Identification – khai báo danh tính** | Người đăng ký tự nhận là ai? | Nhập họ tên, mã ứng viên, email công việc. | Một tuyên bố cần được kiểm chứng. |
| **Identity resolution – phân giải danh tính** | Hồ sơ này mô tả chủ thể nào trong phạm vi tổ chức, có trùng hồ sơ đã có không? | Đối chiếu hồ sơ ứng viên với mã nhân sự và danh tính đã tồn tại. | Một định danh/hồ sơ chủ thể được xác định. |
| **Identity proofing – xác minh danh tính** | Bằng chứng và quá trình đối chiếu có đủ để tin người đăng ký gắn với danh tính đó? | Kiểm tra bằng chứng, liên hệ nguồn có thẩm quyền, đối chiếu người thật theo phương thức phù hợp. | Kết quả proofing kèm mức bảo đảm, thời điểm, nguồn và ngoại lệ. |
| **Authentication – xác thực** | Chủ thể hiện đang truy cập có kiểm soát authenticator đã đăng ký không? | Đăng nhập bằng passkey, MFA hoặc khóa bảo mật. | Một phiên/khẳng định xác thực. |
| **Authorization – kiểm soát truy cập** | Chủ thể có được thực hiện hành động cụ thể với tài nguyên này không? | Nhân viên chỉ xem hồ sơ thuộc đơn vị phụ trách. | Quyết định cho phép hoặc từ chối. |

Sự khác biệt có ý nghĩa thực tế:

- **Proofing** thường thực hiện khi thiết lập danh tính, khi xảy ra sự kiện rủi ro hoặc khi cần nâng mức độ tin cậy.
- **Authentication** diễn ra khi đăng nhập, mở phiên hoặc thực hiện tác vụ cần xác thực lại.
- **Authorization** được kiểm tra khi truy cập tài nguyên; có thể đổi ngay cả khi danh tính đã xác minh và người dùng vẫn đăng nhập bình thường.

**Ví dụ:** Hòa đã được xác minh và tạo tài khoản nhân viên. Hòa đăng nhập SSO thành công bằng khóa bảo mật. API quản lý lương vẫn phải từ chối khi Hòa cố xem bảng lương ngoài phạm vi công việc. Proofing, authentication và authorization là ba quyết định riêng.

> **Điểm cần nhớ:** Xác minh danh tính không chỉ là “đọc giấy tờ”, còn đăng nhập thành công không phải bằng chứng rằng quy trình nhận diện ban đầu đã đúng.

## 2. Mục tiêu, đối tượng và phạm vi xác minh

Không có một quy trình bằng chứng duy nhất phù hợp với mọi loại danh tính. Tổ chức phải xác định **đối tượng**, **mục đích**, **mức rủi ro** và **nguồn có thẩm quyền**.

| Nhóm chủ thể | Mục tiêu proofing hoặc xác minh nguồn | Rủi ro điển hình |
| --- | --- | --- |
| Nhân viên chính thức | Gắn người được tuyển dụng với hồ sơ HR và định danh IAM đúng người. | Kẻ giả danh nhân viên mới, hồ sơ trùng, cấp quyền trước ngày hiệu lực. |
| Nhà thầu/đối tác | Xác minh người được đơn vị bảo trợ cho phép làm việc và thời hạn hợp đồng. | Quyền kéo dài khi hợp đồng hết hạn, người bảo trợ thay đổi. |
| Người dùng khách hàng | Xác minh phù hợp với dịch vụ, giá trị giao dịch và yêu cầu pháp lý cụ thể. | Gian lận tài khoản, hồ sơ giả, chiếm tài khoản. |
| Nhân viên có đặc quyền cao | Xác minh đủ tin cậy để đăng ký authenticator và cấp quyền nhạy cảm. | Giả mạo hỗ trợ kỹ thuật, chiếm quyền quản trị. |
| Tài khoản dịch vụ/workload | Xác thực nguồn yêu cầu và quyền sở hữu workload trước khi phát hành danh tính kỹ thuật. | Đăng ký workload giả, gán nhầm trust policy hoặc cấp key quá rộng. |

Với **service account** hoặc danh tính thiết bị, “identity proofing” theo nghĩa kiểm tra con người không áp dụng nguyên xi. Quy trình tương ứng là **xác minh nguồn gốc workload/thiết bị, quyền sở hữu và bằng chứng đăng ký**, rồi mới phát hành credential. Không nên yêu cầu giấy tờ tùy thân của một chương trình chạy tự động.

Một kết quả proofing tốt thường hỗ trợ trả lời:

1. Chủ thể nào đã được xác minh, bằng định danh ổn định nào?
2. Những dữ kiện nào đã kiểm tra, từ nguồn đáng tin nào?
3. Người hoặc tổ chức nào được quyền đề xuất, xác nhận hoặc phê duyệt?
4. Mức độ chắc chắn và những hạn chế còn lại là gì?
5. Kết quả có hiệu lực từ khi nào, có cần kiểm tra lại không?
6. Quy trình có tạo sai lệch hồ sơ hoặc làm lộ dữ liệu cá nhân không?

Không nên coi “đã gửi ảnh giấy tờ” là đồng nghĩa “đã xác minh”. Việc có một tệp ảnh chỉ chứng minh hệ thống đã **nhận dữ liệu**, chưa chứng minh tính hợp lệ của giấy tờ, chủ thể gửi hay mối liên kết với danh tính khai báo.

## 3. Quy trình xác minh danh tính từ đầu đến cuối

Một luồng proofing có kiểm soát nên tách các bước sau:

1. **Khởi tạo yêu cầu:** HR, hệ thống tuyển dụng, bộ phận bảo trợ hoặc nghiệp vụ tạo sự kiện đăng ký; xác định mục đích, loại chủ thể và mức tin cậy cần đạt.
2. **Phân giải danh tính:** kiểm tra định danh nội bộ và hồ sơ đã có, hạn chế tạo hai tài khoản cho cùng người hoặc gộp nhầm hai người khác nhau.
3. **Thu thập tối thiểu:** lấy đúng dữ liệu/bằng chứng cần cho trường hợp sử dụng, thông báo mục đích và cách xử lý theo chính sách.
4. **Validation – kiểm tra tính hợp lệ của bằng chứng:** xác minh định dạng, thời hạn, tính toàn vẹn, nguồn phát hành và các dấu hiệu bị chỉnh sửa hoặc giả mạo khi áp dụng.
5. **Verification – kiểm tra mối liên kết với chủ thể:** đối chiếu rằng người đang thực hiện quy trình có quan hệ với bằng chứng/hồ sơ, ví dụ kiểm tra trực tiếp, đối chiếu được cho phép hoặc xác nhận từ nguồn có thẩm quyền.
6. **Kiểm tra bất thường:** phát hiện đăng ký trùng, nguồn không nhất quán, hành vi gian lận hoặc sự kiện có dấu hiệu rủi ro; chuyển sang review nếu cần.
7. **Đưa ra quyết định:** \`VERIFIED\`, \`REJECTED\` hoặc \`MANUAL_REVIEW\` kèm mức độ tin cậy, lý do và lịch sử.
8. **Ràng buộc với danh tính IAM:** liên kết kết quả với ID ổn định; chỉ sau các điều kiện cần thiết mới đăng ký authenticator, kích hoạt danh tính IdP và đưa vào luồng cấp quyền.
9. **Lưu bằng chứng kiểm toán:** ghi người/nguồn xác nhận, chính sách áp dụng, thời điểm và kết quả, đồng thời hạn chế giữ dữ liệu thô nhạy cảm.
10. **Đánh giá lại khi có kích hoạt:** khi khôi phục tài khoản rủi ro cao, phát hiện gian lận, xung đột dữ liệu hoặc nâng cấp truy cập đặc quyền.

~~~mermaid
flowchart TD
    A["Nguồn đăng ký/HR/sponsor"] --> B["Phân giải danh tính và kiểm tra trùng"]
    B --> C["Thu thập bằng chứng tối thiểu"]
    C --> D["Kiểm tra tính hợp lệ của bằng chứng"]
    D --> E["Xác minh liên kết với chủ thể"]
    E --> F{"Đạt chính sách proofing?"}
    F -->|Có| G["VERIFIED + mức tin cậy + audit"]
    F -->|Chưa rõ| H["MANUAL_REVIEW / bổ sung bằng chứng"]
    F -->|Không| I["REJECTED / xử lý gian lận"]
    H --> F
    G --> J["Liên kết ID và đăng ký authenticator"]
    J --> K["IdP / SCIM provisioning có điều kiện"]
    K --> L["RBAC/ABAC: cấp quyền đã phê duyệt"]
~~~

**Quan trọng:** không dùng trạng thái \`MANUAL_REVIEW\` như một cách “cho qua” khi hệ thống quá tải. Trường hợp chưa đủ bằng chứng phải giữ các quyền phụ thuộc proofing ở trạng thái chưa cấp, hoặc cấp chế độ rất hạn chế theo chính sách ngoại lệ đã phê duyệt.

## 4. Bằng chứng danh tính và nguồn có thẩm quyền

**Bằng chứng danh tính (identity evidence)** có thể là tài liệu, dữ liệu từ nguồn chính thức, tài khoản được kiểm soát hoặc xác nhận trực tiếp. Độ tin cậy không chỉ phụ thuộc hình thức tài liệu mà còn phụ thuộc **nguồn, cách thu thập, cách kiểm tra và khả năng chứng minh mối liên kết với người đăng ký**.

| Bằng chứng/nguồn | Có thể giúp xác minh điều gì? | Không chứng minh được điều gì nếu đứng riêng |
| --- | --- | --- |
| Hồ sơ HRIS đã được quy trình tuyển dụng xác nhận | Quan hệ lao động, ngày hiệu lực, đơn vị, mã nhân sự. | Người đang cầm thiết bị đăng ký chắc chắn là người trong hồ sơ. |
| Giấy tờ nhận dạng phù hợp yêu cầu | Thuộc tính được cơ quan/đơn vị phát hành ghi nhận. | Giấy tờ không giả, không bị chiếm dụng hoặc người gửi thực sự là chủ giấy tờ. |
| Xác minh trực tiếp bởi người được phân quyền | Quan hệ giữa người xuất hiện và bằng chứng theo quy trình. | Không tự bảo đảm chất lượng nguồn dữ liệu ban đầu. |
| Tài khoản email/số điện thoại đã kiểm soát | Quyền kiểm soát một kênh liên lạc tại thời điểm kiểm tra. | Danh tính pháp lý, chức danh hay quyền được cấp trong công ty. |
| Xác nhận của đơn vị bảo trợ nhà thầu | Cá nhân được giao nhiệm vụ/được sponsor công nhận. | Mọi thuộc tính cá nhân có độ chính xác tuyệt đối hoặc hợp đồng vô thời hạn. |
| Hệ thống danh tính đáng tin đã liên kết trước đó | Có thể tái sử dụng một số khẳng định trong phạm vi và điều kiện được phép. | Mức bảo đảm chắc chắn giống yêu cầu mới khi nguồn không cung cấp metadata cần thiết. |

**Chất lượng nguồn** và **độ mới của dữ liệu** quan trọng không kém loại bằng chứng. Ví dụ, danh sách nhân sự xuất từ sáu tháng trước có thể đã lỗi thời. Một email \`@company.example\` chỉ cho thấy người gửi hiện kiểm soát hộp thư hoặc kênh được sử dụng, không tự xác nhận tình trạng lao động hiện tại.

### Identity resolution không phải phép so khớp tên đơn giản

Tên người có thể trùng, đổi theo quyết định hành chính, chứa dấu hoặc bị nhập khác thứ tự. Email có thể đổi hoặc được tái sử dụng. Vì vậy cần **định danh nội bộ ổn định** được liên kết với nguồn HR/đơn vị bảo trợ và một quy trình xử lý trùng lặp có kiểm soát.

Tìm kiếm gần đúng theo tên, ngày sinh hoặc email chỉ giúp **gợi ý rà soát**; không nên tự động gộp hai danh tính nếu kết quả có thể gây cấp quyền nhầm. Quyết định gộp/tách phải có bằng chứng, phê duyệt và nhật ký, bởi việc gộp sai có thể làm lộ hồ sơ và quyền của một người cho người khác.

## 5. Xác minh trực tiếp, từ xa và bằng quy trình đã có

### Xác minh trực tiếp (in-person)

Một người được phân quyền kiểm tra bằng chứng và đối chiếu với người có mặt. Phương pháp này có thể giúp đánh giá một số dấu hiệu mà hệ thống tự động bỏ qua, nhưng vẫn chịu rủi ro tài liệu giả, người kiểm tra thiếu đào tạo, quy trình không đồng nhất hoặc thông đồng nội bộ. Cần quy định trách nhiệm, tài liệu đối chiếu và cơ chế escalation.

### Xác minh từ xa (remote)

Người đăng ký gửi dữ liệu qua ứng dụng/web và có thể thực hiện bước xác minh bổ sung bằng video hoặc phương pháp kiểm tra theo chính sách. Rủi ro bao gồm ảnh/chứng từ chỉnh sửa, video phát lại, giả mạo tổng hợp bằng AI, tấn công vào thiết bị người đăng ký và đánh tráo luồng đăng ký.

Một hệ thống có thể dùng biện pháp như phát hiện trình chiếu lại, kiểm tra tính sống (**liveness**), đối chiếu tài liệu và giới hạn số lần thử. **Không một kỹ thuật đơn lẻ nào bảo đảm loại trừ mọi trường hợp giả mạo**. Cần đánh giá sai số, tấn công mới và kênh thay thế khi phương thức tự động không hoạt động.

### Tái sử dụng kết quả đã xác minh

Không phải mọi lần người dùng đổi vai trò hay đổi ứng dụng đều cần thu thập lại giấy tờ. Khi tái sử dụng bằng chứng/kết quả có sẵn, cần kiểm tra:

- Danh tính đã được kiểm tra từ nguồn nào và vào thời điểm nào.
- Mức tin cậy có đáp ứng nhu cầu tài nguyên mới không.
- Có sự kiện thay đổi nào làm kết quả cũ không còn đáng tin không.
- Quy định và chính sách tổ chức có cho phép tái sử dụng, chuyển giao hay nhận assertion từ bên thứ ba không.

**Reproofing (xác minh lại)** nên là biện pháp được kích hoạt theo rủi ro, không phải thao tác bắt buộc một cách máy móc đối với mọi sự kiện Mover.

## 6. Mức bảo đảm danh tính và cách tránh nhầm lẫn

Để thiết kế chính sách, nên tách ít nhất ba khía cạnh của sự tin cậy:

| Khía cạnh | Ý nghĩa | Tình huống minh họa |
| --- | --- | --- |
| **Identity Assurance Level (IAL)** | Mức bảo đảm của quy trình thiết lập/liên kết danh tính. | Nhân viên mới đã được xác minh theo quy trình được duyệt. |
| **Authentication Assurance Level (AAL)** | Mức bảo đảm của phương thức và phiên xác thực người dùng. | Đăng nhập bằng phương thức chống phishing theo chính sách. |
| **Federation Assurance Level (FAL)** | Mức bảo đảm khi trao đổi kết quả xác thực/danh tính giữa các bên tin cậy. | Ứng dụng nhận assertion qua quan hệ federation. |

IAL, AAL và FAL là các khái niệm thường gặp trong khung bảo đảm danh tính như **NIST SP 800-63**. Khi áp dụng một phiên bản tiêu chuẩn cụ thể, phải kiểm tra định nghĩa và yêu cầu chính thức của phiên bản đó. Không tự suy ra rằng “đã dùng MFA” thì identity proofing đã đạt mức cao, hay đã có SSO thì đủ bảo đảm cho mọi loại truy cập.

Ví dụ:

- Một tài khoản được tạo qua email tự đăng ký có thể dùng MFA mạnh nhưng **nguồn danh tính ban đầu** vẫn có độ bảo đảm thấp.
- Một nhân viên đã hoàn thành proofing đầy đủ nhưng dùng mật khẩu bị lộ để đăng nhập thì **xác thực phiên** không còn đáng tin.
- Hai hệ thống có mức xác thực tương đương nhưng quan hệ federation khác nhau vẫn cần chính sách kiểm tra assertion và trust riêng.

**Kết quả proofing là đầu vào cho kiểm soát truy cập, không phải quyết định cấp quyền.** Ứng dụng tài chính còn phải xét vai trò, phân quyền tác vụ, thuộc tính tài nguyên và phê duyệt.

## 7. Liên kết identity proofing với IdP, SSO, SCIM và RBAC/ABAC

Một kiến trúc IAM có thể phân chia trách nhiệm như sau:

~~~mermaid
flowchart LR
    HR["HRIS / nguồn nhân sự"] --> WF["Quy trình proofing + approval"]
    SP["Sponsor của nhà thầu"] --> WF
    WF --> REG["Identity registry: ID ổn định và trạng thái"]
    REG --> IDP["IdP: tạo tài khoản, authenticator, SSO"]
    REG --> IGA["IGA: vai trò, entitlement, review"]
    IDP --> APP["Ứng dụng / API"]
    IGA --> PROV["SCIM / connector provisioning"]
    PROV --> APP
    APP --> PDP["RBAC/ABAC + kiểm tra tài nguyên"]
    WF --> AUDIT["Audit: bằng chứng, quyết định"]
    IDP --> AUDIT
    IGA --> AUDIT
~~~

Trong đó:

- **HRIS/nguồn nghiệp vụ:** cung cấp trạng thái nhân sự, hợp đồng, ngày hiệu lực và các thuộc tính có thẩm quyền.
- **Proofing workflow:** kiểm tra bằng chứng và sự liên kết đúng người; lưu quyết định cùng mức bảo đảm được phép sử dụng.
- **Identity registry:** quản lý ID ổn định, giải quyết trùng và liên kết danh tính nội bộ với các hệ thống.
- **IdP/SSO:** đăng ký authenticator, xác thực trong từng phiên và phát hành assertion/token theo giao thức.
- **IGA:** quản trị phê duyệt, role, quyền ngoại lệ, rà soát và thu hồi khi thay đổi vai trò.
- **SCIM:** đồng bộ tài khoản và nhóm tới ứng dụng hỗ trợ; **SCIM không thực hiện thay quy trình kiểm tra giấy tờ hay người thật**.
- **Ứng dụng/API:** thực thi quyết định quyền theo tài nguyên. Một tài khoản đã proofed và đăng nhập thành công vẫn có thể bị từ chối truy cập.

### Không cấp quyền từ một boolean thiếu ngữ cảnh

Trạng thái \`verified: true\` đơn lẻ không diễn tả ai xác minh, theo chính sách nào và còn giá trị trong trường hợp nào. Kết quả tốt hơn cần kèm metadata có cấu trúc: nguồn, cấp độ bảo đảm áp dụng, thời điểm, phiên bản policy và tình trạng hiệu lực.

Đặc biệt, **proofing status**, **employment status**, **account status** và **entitlement status** phải được quản lý độc lập. Một nhân viên có thể đã xác minh danh tính nhưng chưa đến ngày bắt đầu; ứng dụng không nên kích hoạt quyền chỉ vì \`proofing=VERIFIED\`.

## 8. Joiner: xác minh trước khi cấp tài khoản và quyền

Với sự kiện **Joiner**, mục tiêu là tạo đúng một quan hệ có thể kiểm toán giữa người được tuyển dụng và danh tính IAM được sử dụng cho công việc.

Ví dụ: Bình được tuyển vào đội Tài chính, bắt đầu làm từ ngày 1/12.

1. Nguồn HR đã được phê duyệt tạo hồ sơ có **employee ID** ổn định và ngày bắt đầu hiệu lực.
2. Bộ phận phụ trách kiểm tra bằng chứng theo chính sách và xác minh đúng Bình gắn với hồ sơ đó.
3. Registry đối chiếu hồ sơ hiện có để tránh tạo danh tính trùng; nếu tên trùng nhưng ID và bằng chứng khác thì không được tự động gộp.
4. Khi proofing hoàn tất, IdP có thể tạo trước account ở trạng thái chưa cho truy cập, tùy quy trình.
5. Quyền nền theo role chỉ được kích hoạt khi **đến ngày hiệu lực**, có phê duyệt thích hợp và các điều kiện an toàn khác được đáp ứng.
6. Bình đăng ký phương thức xác thực (chẳng hạn passkey hoặc khóa bảo mật) qua luồng enrollment được bảo vệ chống chiếm quyền.
7. IGA/SCIM đồng bộ tài khoản và entitlement đến ứng dụng cần thiết; các hệ thống đích xác nhận trạng thái cấp quyền.
8. Đối soát giữa HR, registry, IdP và ứng dụng để bảo đảm không có tài khoản thừa hay quyền được cấp sớm.

### Điều kiện cấp quyền nên tách rõ

~~~text
eligibleForProvisioning =
    identityProofing == VERIFIED
    AND employmentStatus == ACTIVE
    AND effectiveDateReached
    AND sponsorOrManagerApproval == APPROVED

canPerformSensitiveAction =
    authenticatedSession
    AND currentEntitlementAllowsAction
    AND resourceAndContextPolicyAllows
~~~

Đây là mô hình logic minh họa; điều kiện chính xác phụ thuộc loại tài khoản và chính sách. Với một số quy trình, có thể tạo tài khoản IdP trước ngày bắt đầu để chuẩn bị thiết bị, nhưng **tạo account sớm không đồng nghĩa cho đăng nhập hoặc truy cập dữ liệu sớm**.

## 9. Mover và Leaver: khi nào cần xác minh lại?

Trong **Mover**, chủ thể vẫn là cùng một người, nhưng chức danh, phòng ban và phạm vi quyền thay đổi. Trong **Leaver**, trạng thái quan hệ với tổ chức kết thúc. Cả hai không mặc nhiên yêu cầu thu thập lại chứng minh thư, nhưng có yêu cầu quản trị khác nhau.

| Sự kiện | Xử lý danh tính đã proofed | Xử lý quyền và authenticator | Rủi ro tồn dư cần kiểm tra |
| --- | --- | --- | --- |
| **Mover nội bộ thông thường** | Giữ ID và kết quả proofing còn tin cậy; kiểm tra lại nếu có tín hiệu bất thường. | Gỡ role cũ, cấp role mới theo phê duyệt; cân nhắc step-up authentication cho tác vụ nhạy cảm. | Quyền của phòng ban cũ, dữ liệu chia sẻ và session/cache giữ quyền cũ. |
| **Mover vào vị trí đặc quyền/rủi ro cao** | Đánh giá có cần bổ sung hoặc nâng mức bảo đảm bằng chứng theo chính sách. | Phê duyệt riêng, MFA chống phishing, privileged access có thời hạn, tách nhiệm vụ. | Giao thoa quyền cũ/mới và đặc quyền tích lũy. |
| **Leaver** | Có thể giữ lịch sử xác minh phục vụ kiểm toán theo retention; không biến kết quả cũ thành quyền tiếp tục làm việc. | Khóa IdP, thu hồi session/refresh token, SCIM deprovision, gỡ entitlement và khóa truy cập cục bộ. | Ứng dụng chưa đồng bộ, session cũ, API token, thư mục chia sẻ và quyền trên hệ thống legacy. |
| **Rehire – tuyển lại** | Đối chiếu với hồ sơ cũ, kiểm tra thay đổi và thực hiện proofing lại theo rủi ro/chính sách. | Cấp quyền theo vị trí mới; không tự khôi phục nguyên quyền cũ. | Tái sử dụng email, sai liên kết account và quyền từ lần làm việc trước. |

**Ví dụ Mover:** Lan chuyển từ Chăm sóc khách hàng sang bộ phận Kế toán. Hồ sơ danh tính và nhân viên vẫn liên kết với cùng một ID, nhưng quyền đọc dữ liệu khách hàng có thể phải gỡ và quyền xử lý hóa đơn chỉ cấp sau phê duyệt. Nếu phát hiện dữ liệu bằng chứng từng bị sửa trái phép hoặc có dấu hiệu mạo danh, mới cần kích hoạt xác minh lại phù hợp.

**Ví dụ Leaver:** Việc xóa vai trò ở IdP không bảo đảm session của mọi ứng dụng đã hết hiệu lực. IAM cần theo dõi trạng thái thực tế ở các ứng dụng đích, bao gồm các tài khoản cục bộ và token ngoài kênh SSO. **Kết quả identity proofing đúng không thể bù cho deprovisioning chưa hoàn tất.**

## 10. Xử lý ngoại lệ và khôi phục tài khoản

Một trong các đường tấn công thực tế là **giả danh người dùng để yêu cầu đặt lại authenticator hoặc khôi phục tài khoản**. Nếu quy trình phục hồi yếu hơn đăng ký ban đầu, kẻ tấn công có thể chiếm tài khoản dù phương thức đăng nhập hằng ngày rất mạnh.

Các trường hợp thường cần xử lý riêng:

- Người mới không có đủ bằng chứng ở thời điểm đăng ký.
- Nhà thầu ở xa không thể đến trực tiếp.
- Tên, ảnh hoặc dữ liệu hồ sơ thay đổi hợp pháp.
- Bằng chứng bị hỏng hoặc nguồn kiểm tra đang gián đoạn.
- Người dùng mất điện thoại, passkey hoặc khóa bảo mật.
- Một quản trị viên bị nghi chiếm tài khoản.

Quy trình ngoại lệ nên ghi **lý do, quyền tạm thời (nếu có), thời hạn, người phê duyệt, giới hạn truy cập và mốc đánh giá lại**. Không dùng ngoại lệ như đường tắt cấp quyền đầy đủ khi chưa xác minh.

### Recovery có kiểm soát

Khi người dùng mất authenticator:

1. Tiếp nhận yêu cầu qua kênh được kiểm soát, gắn với ID danh tính ổn định.
2. Xác minh lại người yêu cầu bằng một phương thức hoặc tập bằng chứng **đáp ứng chính sách khôi phục**, không chỉ dựa vào dữ liệu công khai dễ đoán.
3. Kiểm tra các tín hiệu bất thường (thay đổi thiết bị, yêu cầu liên tiếp, thời điểm nhạy cảm, tài khoản đặc quyền).
4. Nếu cần, chuyển phê duyệt cho bộ phận độc lập hoặc tăng mức kiểm tra.
5. Thu hồi authenticator hoặc phiên có nguy cơ lộ; đăng ký authenticator mới qua luồng tin cậy.
6. Gửi thông báo bảo mật phù hợp, ghi log và giám sát truy cập sau phục hồi.

Không yêu cầu người dùng gửi mật khẩu hoặc mã OTP qua email/chat để “chứng minh danh tính”. Quy trình helpdesk phải chống kỹ thuật xã hội; chỉ “biết tên quản lý hoặc số nhân viên” chưa đủ để vượt qua kiểm tra.

## 11. Các mối đe dọa đối với identity proofing

| Mối đe dọa | Cơ chế có thể xảy ra | Biện pháp kiểm soát phù hợp |
| --- | --- | --- |
| **Giả mạo bằng chứng** | Dùng tài liệu chỉnh sửa hoặc danh tính giả. | Kiểm tra độ tin cậy nguồn phát hành, tính toàn vẹn, quy trình review và kết hợp bằng chứng khi cần. |
| **Synthetic identity** | Ghép nhiều thuộc tính thật/giả thành hồ sơ có vẻ hợp lệ. | Kiểm tra bất thường, nguồn có thẩm quyền và quan hệ dữ liệu. |
| **Impersonation** | Dùng giấy tờ của người khác hoặc thông tin bị lộ. | Kiểm tra liên kết giữa người đăng ký và bằng chứng, chống replay/giả mạo. |
| **Deepfake hoặc presentation attack** | Dùng ảnh/video/giọng nói tổng hợp để vượt kiểm tra từ xa. | Đánh giá rủi ro từ xa, liveness phù hợp, kênh xác minh bổ sung và review con người. |
| **Identity collision** | Hai người chung tên hoặc một người có nhiều hồ sơ bị nối sai. | ID ổn định, quy trình đối chiếu trùng và phê duyệt merge/split. |
| **Insider abuse** | Người có quyền xác minh cố tình duyệt hồ sơ giả. | Phân tách nhiệm vụ, log không thể chỉnh sửa trái phép, kiểm tra mẫu và giám sát ngoại lệ. |
| **Social engineering helpdesk** | Giả nhân viên để reset MFA hoặc chuyển số điện thoại. | Recovery policy mạnh, kiểm tra độc lập, giới hạn quyền hỗ trợ và thông báo bảo mật. |
| **Stale evidence** | Tin thông tin HR/hợp đồng đã hết hiệu lực. | Kiểm tra trạng thái hiện hành trước cấp quyền và tái kiểm tra khi có sự kiện. |
| **Data leakage** | Lưu ảnh giấy tờ, dữ liệu sinh trắc hoặc video ở nơi không bảo vệ. | Thu thập tối thiểu, mã hóa, kiểm soát truy cập, retention và xóa theo chính sách. |

Các biện pháp phòng chống gian lận **không nên gây từ chối sai hàng loạt** đối với người có giấy tờ đặc thù, chất lượng camera thấp hoặc nhu cầu trợ năng. Phải có đường xử lý thay thế có mức bảo đảm phù hợp và khả năng khiếu nại/đánh giá lại.

## 12. Quyền riêng tư và bảo vệ bằng chứng nhạy cảm

Xác minh danh tính có thể xử lý dữ liệu cá nhân rất nhạy cảm: giấy tờ nhận dạng, địa chỉ, ảnh khuôn mặt, bản ghi video hoặc thuộc tính khác. Rủi ro không kết thúc khi quá trình proofing đã thành công.

Các nguyên tắc thiết kế:

1. **Giới hạn mục đích:** chỉ thu thập dữ liệu cần thiết cho loại tài khoản và mức rủi ro tương ứng.
2. **Data minimization:** ưu tiên lưu kết quả xác minh và metadata đủ kiểm toán thay vì giữ toàn bộ bản sao tài liệu nếu không cần.
3. **Minh bạch:** thông báo mục đích, nguồn xử lý, thời hạn lưu và kênh hỗ trợ theo chính sách/luật áp dụng.
4. **Tách quyền:** người kiểm tra giấy tờ không mặc nhiên có quyền cấp role quản trị hoặc truy cập tất cả dữ liệu.
5. **Bảo vệ dữ liệu:** mã hóa khi truyền/lưu, kiểm soát truy cập, ghi audit, tránh dữ liệu thô trong log/traces.
6. **Quy định retention và xóa:** xác định dữ liệu cần giữ cho kiểm toán, thời điểm xóa an toàn và xử lý bản sao lưu.
7. **Kiểm soát bên thứ ba:** nếu dùng nhà cung cấp eKYC/identity verification, đánh giá quyền sử dụng dữ liệu, chia sẻ, bảo mật và cơ chế trả kết quả đáng tin.
8. **Cơ chế sửa sai:** cho phép xử lý trường hợp tên, định danh, trạng thái bị ghi sai; mọi sửa đổi phải có nguồn và người phê duyệt.

**Dữ liệu sinh trắc học** cần được đánh giá đặc biệt về quyền riêng tư, bảo mật và khả năng sai lệch. Một điểm “khuôn mặt trùng” chỉ là một tín hiệu từ công nghệ đối chiếu, không phải bằng chứng tuyệt đối rằng toàn bộ danh tính và tư cách lao động đều chính xác.

### Không dùng bí mật làm bằng chứng hồ sơ

Tránh lưu mật khẩu, khóa riêng, mã OTP, access token hoặc refresh token trong hệ thống proofing. Đây là **authenticator/credential** cần có vòng đời riêng. Proofing nên lưu kết quả và các tham chiếu cần thiết; quá trình đăng ký authenticator tiếp theo được IdP hoặc hệ thống chuyên trách thực hiện qua kênh bảo vệ.

## 13. Mô hình dữ liệu và sự kiện cho hệ thống triển khai

Ví dụ một bản ghi kết quả proofing:

~~~yaml
proofingCaseId: proof-2026-0512
subjectId: person-4821
identitySourceRef: hr-employee-4821
subjectType: EMPLOYEE
purpose: WORKFORCE_ONBOARDING
requestedAssuranceProfile: workforce-standard
status: VERIFIED
completedAt: "2026-11-23T09:00:00Z"
policyVersion: workforce-proofing-v3
evidence:
  - type: HR_RECORD_VALIDATION
    sourceRef: trusted-hris
    result: PASSED
  - type: PERSON_TO_RECORD_BINDING
    sourceRef: approved-verification-workflow
    result: PASSED
review:
  reviewerRef: verifier-team-7
  exceptions: []
recordRetentionRef: identity-proofing-policy
~~~

Đây là **schema minh họa** để diễn đạt thông tin cần quản lý, không phải yêu cầu lưu tất cả bằng chứng thô và không đại diện cấu trúc của một sản phẩm IAM cụ thể. Trong thực tế, các trường nên có quy định về bảo vệ PII, phân quyền và phiên bản policy.

### Event giúp tách proofing khỏi provisioning

Ví dụ sự kiện đã xác minh:

~~~json
{
  "eventId": "evt-9d31",
  "eventType": "identity.proofing.verified",
  "subjectId": "person-4821",
  "proofingCaseId": "proof-2026-0512",
  "assuranceProfile": "workforce-standard",
  "policyVersion": "workforce-proofing-v3",
  "occurredAt": "2026-11-23T09:00:00Z"
}
~~~

Consumer của sự kiện **không nên cấp quyền chỉ vì có message**. Phải kiểm tra chữ ký/tính xác thực của sự kiện theo hệ thống, quyền phát hành từ nguồn tin cậy, trạng thái HR hiện hành, ngày có hiệu lực và approval. Xử lý cần **idempotent** theo \`eventId\` hoặc khóa nghiệp vụ thích hợp; sự kiện lặp/đến sai thứ tự không được tạo nhiều account hoặc khôi phục quyền đã thu hồi.

Một hệ thống event-driven cũng cần lưu **thời điểm sự kiện phát sinh** và **thời điểm áp dụng**, cơ chế retry, dead-letter và đối soát. Proofing workflow báo thành công không có nghĩa mọi ứng dụng SCIM đích đã nhận và xử lý hoàn tất.

## 14. Ví dụ kiểm soát phía backend

Khi dịch vụ provisioning nhận yêu cầu kích hoạt một tài khoản nhân viên, logic nên kiểm tra **quyết định proofing và điều kiện nghiệp vụ hiện hành**:

~~~java
// Pseudocode Java: dữ liệu lấy từ hệ thống HR/IGA/proofing đáng tin.
ProvisioningDecision evaluateJoiner(String subjectId) {
    ProofingResult proofing = proofingRegistry.latestTrustedResult(subjectId);
    EmploymentRecord employment = hrRepository.currentRecord(subjectId);
    Approval approval = iamApprovalService.currentApproval(subjectId);

    if (proofing == null || proofing.status() != ProofingStatus.VERIFIED) {
        return ProvisioningDecision.hold("identity_not_verified");
    }

    if (!proofing.meetsPolicy("workforce-standard")
            || !proofing.isValidForCurrentContext()) {
        return ProvisioningDecision.hold("proofing_insufficient");
    }

    if (employment == null || !employment.isActiveNow()) {
        return ProvisioningDecision.hold("employment_not_active");
    }

    if (approval == null || !approval.allowsInitialAccess()) {
        return ProvisioningDecision.hold("approval_missing");
    }

    return ProvisioningDecision.allowBaselineRolesOnly();
}
~~~

Mã chỉ minh họa **tách điều kiện**, chưa phải hệ thống policy đầy đủ. Triển khai thực cần bảo vệ API, xác minh nguồn dữ liệu, xử lý race condition và xem xét giao dịch/cơ chế đối soát. Quyền cơ sở vẫn phải được định nghĩa riêng theo chức năng, không “tự động cấp admin” vì proofing đạt kết quả tốt.

Sau khi cấp tài khoản, **SSO authentication** và **RBAC/ABAC authorization** tiếp tục kiểm tra mọi request nhạy cảm. Kết quả proofing được dùng để xây dựng và duy trì độ tin cậy của danh tính, không thay thế kiểm tra session và resource.

## 15. Kiểm toán, đối soát và các chỉ số vận hành

Một quy trình proofing có thể đúng trên giấy nhưng thất bại khi tài khoản được kích hoạt trước thời hạn hoặc một ngoại lệ bị bỏ quên. Kiểm toán cần kết nối các sự kiện qua **subject ID ổn định** và **correlation ID**.

| Nhóm bằng chứng | Trường nên có | Câu hỏi kiểm toán |
| --- | --- | --- |
| Khởi tạo case | Subject ID, nguồn yêu cầu, mục đích, policy/version, thời gian. | Ai đề nghị xác minh và vì sao? |
| Kiểm tra bằng chứng | Loại bằng chứng, nguồn, kết quả từng bước, verifier, thời điểm. | Những kiểm tra nào thực sự hoàn tất? |
| Quyết định | Status, mức bảo đảm, lý do từ chối/ngoại lệ, reviewer, approval. | Ai chấp nhận hoặc từ chối và dựa trên quy định nào? |
| Liên kết IAM | Registry ID, IdP account ID, ngày kích hoạt, trạng thái authenticator registration. | Đã tạo đúng account cho đúng chủ thể chưa? |
| Provisioning | Target app, role/scope, phê duyệt, hiệu lực, kết quả SCIM/API. | Quyền nào được cấp, ở đâu và khi nào? |
| Mover/Leaver | Thay đổi HR, quyền trước/sau, session/credential revoke, target readback. | Quyền cũ có thực sự hết hiệu lực? |
| Reproofing/recovery | Trigger, loại kiểm tra lại, quyết định, authenticator thay thế. | Quy trình khôi phục có bảo đảm tương xứng không? |

Một số chỉ số hữu ích:

- **Proofing completion rate:** tỷ lệ yêu cầu hoàn tất theo chính sách và loại case.
- **Time to verified:** thời gian từ khi hồ sơ đủ điều kiện đến khi có quyết định.
- **Manual review backlog:** số hồ sơ chờ người kiểm tra, độ tuổi tồn đọng và nguyên nhân.
- **Identity collision/duplicate rate:** tỷ lệ hồ sơ bị nghi trùng hoặc có quyết định gộp/tách.
- **False rejection / appeal outcomes:** tỷ lệ từ chối sai được phát hiện qua khiếu nại và review, để cải thiện công bằng/trải nghiệm.
- **Provisioning gate violations:** số trường hợp tài khoản hoặc quyền được kích hoạt không đúng điều kiện proofing/HR/approval.
- **Orphan and residual access:** quyền/tài khoản còn tồn sau khi chủ thể chuyển vai trò hoặc rời tổ chức.

Không đánh giá chất lượng chỉ bằng tỷ lệ hồ sơ được chấp thuận: một quy trình duyệt 100% có thể che giấu bỏ sót gian lận. Ngược lại, quá nhiều từ chối sai gây tắc nghẽn onboarding và làm nhân viên tìm cách lách quy trình.

## 16. Bộ tình huống kiểm thử

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Joiner có hồ sơ HR hợp lệ, proofing VERIFIED, đến ngày hiệu lực và có approval. | Cho phép provisioning quyền nền đúng vai trò; vẫn yêu cầu enrollment/xác thực khi đăng nhập. |
| Joiner gửi ảnh giấy tờ nhưng chưa kiểm tra nguồn hoặc liên kết người–bằng chứng. | Chưa đánh dấu VERIFIED, không cấp quyền phụ thuộc proofing. |
| Hai người có tên giống nhau nhưng employee ID và bằng chứng khác nhau. | Giữ hai định danh riêng; không tự động gộp hồ sơ. |
| Một người đổi email công ty. | Cập nhật thuộc tính theo nguồn có thẩm quyền; bảo toàn subject ID ổn định. |
| Một người chuyển từ Sales sang Finance, proofing cũ vẫn đáng tin. | Đánh giá role/quyền mới; không mặc định bắt xác minh lại danh tính pháp lý. |
| Một nhân viên đã proofed nhưng hợp đồng chưa có hiệu lực. | Chặn quyền nghiệp vụ theo điều kiện ngày hiệu lực/trạng thái quan hệ. |
| Helpdesk nhận yêu cầu reset MFA chỉ dựa trên tên và số nhân viên. | Không cho phép reset; kích hoạt quy trình recovery mạnh hơn. |
| Quy trình remote phát hiện tài liệu mâu thuẫn hoặc nghi deepfake. | Giữ hồ sơ chờ review hoặc từ chối theo chính sách; không tự bỏ qua cảnh báo. |
| Proofing VERIFIED nhưng người dùng không đủ quyền xem bảng lương. | API từ chối hành động theo authorization. |
| Leaver còn session ở ứng dụng legacy sau khi IdP đã khóa. | Đối soát và thu hồi tại ứng dụng đích; chưa coi deprovision hoàn tất. |
| Event \`identity.proofing.verified\` được gửi lặp. | Xử lý idempotent, không tạo account hoặc cấp quyền trùng. |
| Nhà thầu được sponsor xác nhận nhưng hợp đồng đã hết hạn. | Không cấp/kéo dài quyền khi nguồn quan hệ không còn hiệu lực. |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Một người nhập đúng email công ty và nhận được OTP. Có thể kết luận đã xác minh danh tính nhân viên chưa?

**Trả lời:** Chưa. Việc nhận OTP chủ yếu chứng minh quyền kiểm soát kênh liên lạc tại thời điểm đó. Cần kiểm tra sự liên kết với hồ sơ người được phép làm việc bằng nguồn có thẩm quyền và quy trình proofing phù hợp.

**Câu 2.** Tại sao chứng minh giấy tờ hợp lệ và chứng minh người cầm giấy tờ là chủ giấy tờ lại là hai bước khác nhau?

**Trả lời:** Một giấy tờ thật vẫn có thể bị đánh cắp hoặc sử dụng bởi người khác. Validation kiểm tra bằng chứng; verification đánh giá mối liên kết giữa chủ thể đang đăng ký và bằng chứng.

**Câu 3.** Một nhân viên chuyển phòng ban có phải thực hiện identity proofing lại từ đầu không?

**Trả lời:** Không mặc định. Thường cần cập nhật và thu hồi/cấp lại quyền theo vai trò. Reproofing được cân nhắc khi có thay đổi thuộc tính quan trọng, dấu hiệu gian lận hoặc yêu cầu tin cậy cao hơn theo chính sách.

**Câu 4.** Một nhân viên đã proofed, đăng nhập SSO thành công và có MFA. Điều đó có tự cấp quyền quản trị cho họ không?

**Trả lời:** Không. Quyền quản trị cần authorization riêng: approval, vai trò, điều kiện phân tách nhiệm vụ, thời hạn và chính sách tài nguyên.

**Câu 5.** Có nên lưu toàn bộ ảnh giấy tờ và video vô thời hạn để “chắc chắn còn bằng chứng” không?

**Trả lời:** Không. Chỉ lưu theo mục đích/retention được phê duyệt; ưu tiên metadata/kết quả đủ kiểm toán và bảo vệ dữ liệu thô nhạy cảm. Việc lưu lâu hơn tạo thêm rủi ro rò rỉ dữ liệu.

**Câu 6.** Một event proofing thành công đã tới hệ thống IAM nhưng SCIM provisioning lỗi. Có thể coi onboarding hoàn tất không?

**Trả lời:** Chưa. Proofing hoàn tất và account/entitlement ở hệ thống đích là hai trạng thái khác nhau. Cần xử lý lỗi, retry/đối soát và xác nhận kết quả cuối đường.

---

**Ghi nhớ:** Identity proofing xây dựng **độ tin cậy ban đầu đối với danh tính được khai báo** và cung cấp kết quả có thể kiểm toán để khởi tạo quan hệ với IAM. **Authentication** chứng minh chủ thể kiểm soát authenticator khi truy cập, còn **authorization** quyết định hành động được phép trên tài nguyên cụ thể. Trong Joiner–Mover–Leaver, cả ba phải gắn với nguồn nhân sự, trạng thái tài khoản, quy trình phê duyệt và đối soát thu hồi nhằm hạn chế tài khoản nhầm, cấp quyền sai và quyền truy cập tồn dư.
