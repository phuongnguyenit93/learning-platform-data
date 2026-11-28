# Identity lifecycle

Trong chương **Identity assurance**, **identity lifecycle** (vòng đời danh tính) là toàn bộ quá trình một danh tính số được **đề nghị, xác lập, liên kết với chủ thể, sử dụng, thay đổi, rà soát, tạm ngưng, khôi phục, chấm dứt và xử lý dữ liệu sau chấm dứt**. Vòng đời bao trùm không chỉ tài khoản đăng nhập mà còn thông tin nhận dạng, liên kết danh tính với cá nhân hoặc workload, phương thức xác thực, các mối quan hệ và quyền liên quan, lịch sử thay đổi và những bằng chứng giúp kiểm tra tính đúng đắn của từng quyết định.

Một người dùng có thể đăng ký tài khoản nền tảng học trực tuyến, xác minh email, trở thành học viên, được phân công làm trợ giảng, đổi trường học, quên thiết bị xác thực, tạm khóa tài khoản vì nghi ngờ bị chiếm quyền và cuối cùng yêu cầu đóng tài khoản. Ở mỗi lần chuyển trạng thái, một sai lệch có thể làm **người sai nhận được quyền**, **người hợp lệ mất khả năng truy cập**, hoặc **quyền cũ tiếp tục hoạt động khi điều kiện đã hết**.

Chỉ có màn hình “Tài khoản đã bị vô hiệu hóa” chưa đủ để chứng minh rằng mọi phiên, token, quyền cloud, khóa API, quyền chia sẻ hoặc job được ủy quyền trước đó đều đã hết khả năng gây tác động. **Identity lifecycle assurance** trả lời câu hỏi: tổ chức có những quy tắc nào để quản lý danh tính, những quy tắc đó có được thực thi chính xác ở các hệ thống liên quan không, và bằng chứng nào đủ để tin rằng chúng vẫn hoạt động đúng theo thời gian?

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**, tập trung vào cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật thông qua phân tích rủi ro, yêu cầu, security controls, kiểm thử, audit, khắc phục finding và security assurance liên tục trong phát triển, vận hành. Vì thế, không chỉ học các trạng thái danh tính mà còn thiết kế **chuỗi truy vết từ rủi ro → yêu cầu vòng đời → control → test/evidence → assessment → remediation → residual risk**.

## 1. Kết quả học tập

Sau khi học bài này, bạn có thể:

1. Phân biệt **identity**, **digital identity**, **account**, **principal**, **credential**, **authenticator**, **session**, **entitlement** và **identity lifecycle**.
2. Mô tả các bước hình thành, kiểm chứng, liên kết, kích hoạt, thay đổi, khóa, khôi phục, vô hiệu hóa và xử lý danh tính sau vòng đời.
3. Xác định những nguồn dữ liệu có thẩm quyền (*authoritative sources*) và cách hệ thống IAM/IdP, ứng dụng Java, SaaS, HR hoặc hệ thống học vụ phải đồng bộ.
4. Hiểu sự khác nhau giữa **identity proofing assurance**, **authentication assurance** và **federation assurance**, không đánh đồng việc kiểm chứng danh tính với việc đăng nhập thành công.
5. Xây security invariants cho từng chuyển trạng thái; thiết kế kiểm thử tích cực, tiêu cực, lỗi hệ thống, yêu cầu lặp và sự kiện đến sai thứ tự.
6. Kiểm chứng vòng đời của **người dùng, nhân sự, đối tác, tài khoản đặc quyền và non-human/workload identities**.
7. Xây hồ sơ bằng chứng cho cấp quyền, đổi vai trò, thu hồi, phục hồi và xóa theo đúng kỳ và phạm vi.
8. Áp dụng Claim–Argument–Evidence, phân biệt **control failure**, **evidence gap**, ngoại lệ được phê duyệt và residual risk.
9. Thiết lập metrics, trigger tái đánh giá và chương trình continuous identity assurance cho hệ thống phân tán.

## 2. Identity lifecycle là gì và vì sao quan trọng?

### 2.1. Danh tính không chỉ là username

Một **danh tính số** là tập thông tin, định danh và quan hệ mà hệ thống sử dụng để nhận biết một chủ thể trong một ngữ cảnh. Chủ thể có thể là con người hoặc một workload/service. Một cá nhân có thể có nhiều tài khoản, một tài khoản có thể nhận nhiều quyền theo thời gian, và một địa chỉ email **không nhất thiết là định danh ổn định, duy nhất hoặc chứng cứ về danh tính ngoài đời thực**.

Ví dụ:

- **Người học:** có learnerId nội bộ, email liên hệ, quyền truy cập khóa học, các phiên đăng nhập và lịch sử chuyển lớp.
- **Giảng viên:** có teacherId, quan hệ được phân công tới lớp, phương thức xác thực, quyền sửa điểm hoặc xuất báo cáo.
- **Nhân sự vận hành:** có mã nhân sự, account IdP, role cloud và những quyền sản xuất có thời hạn.
- **Workload:** có service identity, namespace, quyền gọi API, credential và owner kỹ thuật.
- **Đối tác:** có tài khoản hỗ trợ hoặc OAuth client với scope dữ liệu và điều khoản truy cập cụ thể.

Một hệ thống cần phân biệt **định danh của chủ thể** với **tập quyền được cấp** và **các bằng chứng cho phép tin vào định danh đó**.

### 2.2. Các khái niệm dễ nhầm

| Thuật ngữ | Ý nghĩa | Ví dụ và lưu ý |
|---|---|---|
| **Identity** | Thông tin/định danh biểu diễn một chủ thể trong phạm vi | Learner 1784 trong hệ thống học |
| **Account** | Bản ghi hay thực thể phục vụ tương tác với một hệ thống | Account trên IdP và account trong learning-api có thể khác nhau |
| **Principal** | Danh tính được hệ thống dùng trong ngữ cảnh xác thực/phân quyền | Principal từ token đã xác minh |
| **Identifier** | Giá trị tham chiếu chủ thể | UUID bất biến hơn email có thể đổi |
| **Identity proofing** | Quá trình thu thập/xác minh bằng chứng để thiết lập liên kết giữa danh tính được khai và chủ thể | Kiểm chứng danh tính ngoài đời thực khi mục tiêu yêu cầu |
| **Credential** | Thông tin/đối tượng được dùng làm căn cứ xác thực hoặc khai báo quyền, tùy hệ thống | Credential hoặc xác nhận danh tính trong quy trình |
| **Authenticator** | Yếu tố hoặc phương tiện chứng minh quyền kiểm soát khi xác thực | Passkey, khóa phần cứng, ứng dụng xác thực phù hợp |
| **Authentication** | Quá trình xác minh chủ thể đang cố truy cập có kiểm soát phương tiện xác thực hợp lệ | Đăng nhập thành công |
| **Session** | Trạng thái tương tác được duy trì sau xác thực | Browser session hoặc phiên admin |
| **Authorization/entitlement** | Quyền thực hiện hành động trên đối tượng trong ngữ cảnh | Giảng viên được xuất dữ liệu lớp 42 |
| **Directory/IdP** | Hệ thống lưu thông tin danh tính hoặc cung cấp xác thực | Corporate IdP, identity directory |
| **Lifecycle event** | Sự kiện thay đổi trạng thái danh tính/quyền | Học viên chuyển trường, nhân sự nghỉ việc |
| **Deprovisioning** | Gỡ bỏ quyền truy cập/tài khoản khỏi hệ thống thuộc phạm vi | Thu hồi role và vô hiệu hóa phiên |
| **Deletion/retention** | Xử lý dữ liệu danh tính sau khi chấm dứt theo nghĩa vụ | Tài khoản vô hiệu nhưng record cần được lưu có giới hạn |

**Authentication thành công** không tự chứng minh thông tin danh tính ban đầu được kiểm chứng ở mức cao, và cũng **không chứng minh người dùng có quyền** trên mọi dữ liệu. Identity lifecycle liên kết với access control, nhưng hai khái niệm không đồng nhất.

### 2.3. Ba nhóm rủi ro lớn

1. **Sai liên kết:** tạo hoặc liên kết nhầm tài khoản với cá nhân, hoặc cho một actor chiếm account trong quá trình đăng ký/khôi phục.
2. **Sai trạng thái:** tài khoản bị khóa nhưng token còn hiệu lực, quyền chuyển lớp chưa cập nhật, account trùng được cấp quyền khác nhau.
3. **Sai thẩm quyền:** cấp quyền không qua phê duyệt, tự nâng quyền, tài khoản hỗ trợ/vendor vẫn truy cập sau khi nhiệm vụ kết thúc.

Chương trình identity assurance phải nhìn cả ba nhóm thay vì chỉ kiểm tra chính sách mật khẩu.

## 3. Vòng đời danh tính ở cấp khái niệm

Một mô hình trạng thái minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> ProofingPending: Thu thập/kiểm chứng thông tin
    ProofingPending --> Active: Xác minh/duyệt theo chính sách
    ProofingPending --> Rejected: Không đáp ứng tiêu chí
    Active --> Active: Đổi thuộc tính, vai trò, authenticator
    Active --> RecoveryPending: Mất quyền kiểm soát phương thức
    RecoveryPending --> Active: Khôi phục được xác minh
    Active --> Suspended: Rủi ro, không hoạt động hoặc theo yêu cầu
    Suspended --> Active: Kích hoạt lại có thẩm quyền
    Active --> Deprovisioning: Kết thúc tư cách/quan hệ
    Suspended --> Deprovisioning: Chấm dứt
    Deprovisioning --> Retained: Thu hồi và giữ record theo nghĩa vụ
    Retained --> Deleted: Hết thời hạn và được phép xóa
    Rejected --> Retained: Lưu tối thiểu nếu cần
    Deleted --> [*]
~~~

Mô hình này **không phải state machine chuẩn bắt buộc**. Có hệ thống không cần proofing danh tính ngoài đời thật, có hệ thống phải tạm dừng thay vì xóa, có tài khoản chỉ được archive, hoặc cần trạng thái **Compromised/Locked** riêng. Các bước và chuyển trạng thái phải được lựa chọn theo loại danh tính, rủi ro và nghĩa vụ.

### 3.1. Mô hình theo sự kiện

| Giai đoạn/sự kiện | Điều kiện kích hoạt | Quyết định cần kiểm soát | Kết quả và bằng chứng |
|---|---|---|---|
| **Request/enrollment** | Người dùng hoặc hệ thống đề nghị tạo danh tính | Ai được đăng ký, dữ liệu nào cần lấy? | Request, nguồn và consent/approval khi áp dụng |
| **Proofing/verification** | Cần xác minh danh tính hoặc quyền kiểm soát kênh | Bằng chứng nào đủ theo rủi ro? | Verification result, method, limitations |
| **Account binding** | Liên kết chủ thể, account và identifier | Có tạo nhầm/liên kết trùng không? | Source mapping, uniqueness/linking decision |
| **Credential/authenticator enrollment** | Gắn phương thức xác thực | Ai kiểm soát phương thức, có chống chiếm quyền? | Enrollment event, verified binding, method |
| **Activation/provisioning** | Đủ tiêu chí kích hoạt | Quyền tối thiểu và scope nào được cấp? | Account state, entitlement grant, approval |
| **Use/monitoring** | Đăng nhập, đổi session, dùng quyền | AuthN/AuthZ và log có đúng? | Login test, events, review |
| **Change/mover** | Đổi vai trò/lớp/đơn vị | Quyền cũ có bị bỏ trước/sau khi thêm quyền mới? | Before/after access, effective permissions |
| **Suspension/lock** | Có cảnh báo, mất tư cách hoặc quyết định tạm khóa | Cần chặn những đường truy cập nào? | State change, session/token behavior, tests |
| **Recovery/rebinding** | Mất thiết bị/credential hoặc khôi phục tài khoản | Có xác minh đúng chủ thể và chặn actor giả? | Recovery approval, proof, credential replacement |
| **Termination/deprovisioning** | Kết thúc quan hệ, hết hợp đồng, đóng tài khoản | Account/quyền/session/token nào phải thu hồi? | Revocation events, downstream confirmation |
| **Retention/deletion** | Hết thời gian sử dụng hoặc thời hạn lưu | Cần giữ/xóa thông tin nào theo nghĩa vụ? | Retention rule, deletion/exception record |

Mỗi giai đoạn không nhất thiết diễn ra đúng một lần. Một chủ thể có thể **thay đổi vai trò, thêm authenticator, đổi email hoặc khôi phục nhiều lần**. Khi một sự kiện thất bại, hệ thống phải biết trạng thái đã được chuyển tới đâu và cách tiếp tục an toàn.

## 4. Identity assurance khác access control assurance

**Identity assurance** hỏi: *Chúng ta có cơ sở gì để tin danh tính số, liên kết và phương thức xác thực của chủ thể là đúng trong bối cảnh yêu cầu?*

**Access control assurance** hỏi: *Chúng ta có cơ sở gì để tin rằng các hành động trên tài nguyên được cho phép hoặc từ chối đúng chính sách?*

Chúng liên kết nhưng có thể thất bại độc lập:

| Tình huống | Identity assurance | Authorization assurance |
|---|---|---|
| Người dùng được xác minh đúng nhưng được cấp role admin sai | Liên kết chủ thể có thể đúng | Cấp quyền thất bại |
| User đăng nhập bằng phương thức mạnh nhưng tài khoản đã bị chiếm tại bước khôi phục | Vòng đời liên kết/xác thực bị suy yếu | Access decision có thể thi hành đúng policy đối với một account đã bị chiếm |
| Giảng viên hợp lệ cố xem lớp khác | Danh tính có thể đáng tin | Phân quyền theo đối tượng phải từ chối |
| Tài khoản bị vô hiệu hóa ở IdP nhưng ứng dụng vẫn cho session cũ truy cập | Lifecycle và liên hệ session không đạt | PEP cũng có thể thiếu điều kiện từ chối |
| Service account không có owner, còn secret hoạt động | Danh tính workload và governance thiếu | Có thể có quyền vượt phạm vi cần thiết |

Một chương trình assurance tốt không kết luận “identity được bảo đảm” chỉ từ việc MFA được bật. Cần xem **nguồn chủ thể, liên kết tài khoản, credential, sự kiện thay đổi, quyền, phiên và kênh khôi phục**.

## 5. Proofing, authentication và federation assurance

### 5.1. Identity proofing

**Identity proofing** thiết lập mức tin cậy rằng một danh tính được khai tương ứng với một chủ thể theo mục đích sử dụng. Không phải mọi ứng dụng học trực tuyến đều cần kiểm chứng pháp lý ở mức cao cho mọi người dùng. Một tài khoản chỉ xem bài học miễn phí có thể có yêu cầu khác với người được cấp chứng chỉ chuyên môn, ký tài liệu hoặc vận hành hệ thống production.

Các câu hỏi kiểm soát:

- Mục đích sử dụng có đòi hỏi xác minh danh tính thực tế không?
- Dữ liệu/giấy tờ hoặc nguồn xác nhận được dùng có đáng tin và phù hợp pháp lý không?
- Kênh xác minh chỉ chứng minh **kiểm soát email/điện thoại** hay chứng minh đúng **con người**?
- Bằng chứng proofing có được bảo vệ và lưu tối thiểu không?
- Khi có nghi vấn gian lận hoặc trùng danh tính, quy trình xử lý và đánh giá lại ra sao?

Xác nhận email là việc xác minh **quyền kiểm soát một kênh tại một thời điểm**; không nên diễn giải thành việc đã chứng minh đầy đủ tên thật hoặc thuộc tính ngoài đời thực.

### 5.2. Authentication assurance

Sau khi đã có identity/account, một hệ thống cần xác nhận người đang đăng nhập kiểm soát authenticator hợp lệ. Mức bảo đảm phụ thuộc phương thức, khả năng chống lừa đảo, cách enrolment, quy tắc session và rủi ro nghiệp vụ.

Những câu hỏi cần kiểm tra:

- Authenticator được liên kết với đúng account qua quy trình nào?
- Có thể thêm phương thức mới chỉ bằng quyền ở phiên yếu hơn không?
- Có đường recovery làm mất tác dụng của MFA/step-up không?
- Phương thức xác thực có được cưỡng chế trên **mọi đường có liên quan**?
- Session/refresh token có bị dùng khi tài khoản đã bị khóa hay quyền thay đổi không?
- Có bằng chứng log/test cho các đường bypass hoặc trường hợp khẩn cấp không?

### 5.3. Federation assurance

Khi ứng dụng tin một IdP hoặc đối tác liên kết, cần kiểm soát **mối tin cậy giữa các bên**: ai phát hành assertion/token, audience, issuer, thời hạn, chữ ký/khóa, subject identifier và cách liên kết account.

Một token ký hợp lệ nhưng có **audience sai** hoặc được liên kết nhầm người dùng có thể gây truy cập trái phép. Việc “dùng SSO” không tự chứng minh đúng người được cấp quyền trong ứng dụng.

### 5.4. Không đánh đồng ba loại mức bảo đảm

Một số hệ thống tham chiếu các khái niệm **IAL** (identity assurance level), **AAL** (authenticator assurance level) và **FAL** (federation assurance level) trong các hướng dẫn danh tính số của NIST. Chúng phản ánh **những chiều bảo đảm khác nhau** và phụ thuộc phiên bản hướng dẫn, mục tiêu áp dụng và lựa chọn theo rủi ro. Không nên tự gán một mức duy nhất cho mọi người dùng, hoặc khẳng định sử dụng MFA làm IAL tự tăng.

Nếu tổ chức lựa chọn tham chiếu một chuẩn cụ thể, cần lưu **phiên bản, phạm vi, tiêu chí thật và phương pháp đánh giá**; nội dung bài này không tự đặt ngưỡng chứng nhận hay mức bắt buộc.

## 6. Nguồn dữ liệu có thẩm quyền và account linking

### 6.1. Authoritative source là gì?

Một **authoritative source** là nguồn được tổ chức giao quyền xác lập hoặc xác nhận một loại thông tin trong phạm vi nhất định. Ví dụ:

| Thuộc tính/sự kiện | Nguồn có thể có thẩm quyền | Cần lưu ý |
|---|---|---|
| Nhân sự còn làm việc và ngày kết thúc | HR/employee lifecycle system | Cần chính sách cho contractor và cộng tác viên |
| Giảng viên thuộc khoa/phòng | Hệ thống học vụ/nhân sự | Không suy ra quyền cho từng lớp chỉ từ chức danh |
| Phân công giảng dạy lớp | Hệ thống quản lý lớp được phê duyệt | Cần tính hiệu lực thời gian và tenant |
| Tài khoản đăng nhập được liên kết | IdP/directory và identity mapping service | IdP không mặc nhiên biết quan hệ học vụ |
| Người dùng yêu cầu đổi email | Luồng profile/verification được phê duyệt | Email mới phải được kiểm chứng theo mục tiêu |
| Workload service và owner | Service registry/CI-CD/IAM governance | Kẻ sở hữu repo không nhất thiết là owner cuối cùng của mọi credential |
| Nhà cung cấp còn hợp đồng | Vendor management/procurement | Cần nối với account/vendor access thực tế |

Nguồn có thẩm quyền có thể khác nhau cho từng trường. **Không dùng nguồn gần nhất hoặc dễ truy vấn nhất thay cho nguồn được phê duyệt**.

### 6.2. Identity resolution và chống nhầm người

Các rủi ro phổ biến:

- Hai người trùng họ tên.
- Email được đổi, tái sử dụng hoặc thuộc hộp thư nhóm.
- Một người đăng nhập bằng nhiều IdP, tạo tài khoản trùng.
- Một tài khoản cũ được liên kết với người dùng mới do matching theo email.
- Nhân sự đổi mã hoặc chuyển giữa tổ chức/tenant.
- Nhà cung cấp dùng account chung nên không truy vết được người thao tác.

Một giải pháp thường nên có **internal immutable subject ID** trong phạm vi, giữ account linking history và kiểm soát việc hợp nhất/tách danh tính. Identifier như email/username có thể dùng cho liên hệ/đăng nhập nhưng **không nên mặc định là khóa nhận dạng bất biến**.

### 6.3. Account linking là hành động nhạy cảm

Liên kết một login mới hoặc external identity vào account đang chứa dữ liệu học viên có thể mở đường **account takeover**. Cần xác minh quyền kiểm soát cả hai phía theo chính sách, chống tự liên kết qua dữ liệu không đáng tin và ghi audit trail.

**Negative test:** actor cố đăng ký external identity có địa chỉ email trùng tài khoản đã tồn tại nhưng không chứng minh quyền kiểm soát hợp lệ. Expected: không thể tự chiếm hoặc chuyển quyền của account cũ.

## 7. Enrollment và tạo danh tính mới

### 7.1. Nguyên tắc chung

Bất kể tài khoản học viên, nhân viên hay contractor, quy trình tạo mới nên xác định:

1. **Ai được phép yêu cầu tạo?** Self-registration, admin hoặc hệ thống nguồn.
2. **Thông tin nào thật sự cần?** Dùng dữ liệu tối thiểu và giải thích mục đích.
3. **Điều kiện xác minh nào phù hợp?** Email ownership, chứng minh tư cách, quy trình phê duyệt.
4. **Identifier nào được cấp?** Cách tránh trùng, đổi ID hoặc account linking sai.
5. **Có cấp quyền mặc định không?** Mặc định chỉ mức cần cho trạng thái ban đầu.
6. **Khi kiểm tra thất bại?** Không kích hoạt account rộng, tránh record nửa hoàn thành.
7. **Bằng chứng nào được lưu?** Request ID, method, kết quả, thời điểm, actor thực hiện.
8. **Khi người dùng bỏ dở?** Quản lý pending/invited accounts và xóa/giữ theo policy.

### 7.2. Chống cấp tài khoản hai lần

Một luồng tạo tài khoản có thể bị retry vì mất mạng, worker nhận cùng một sự kiện hai lần hoặc nhân sự bấm tạo nhiều lần. Nếu xử lý không **idempotent**, tổ chức có thể tạo hai account với quyền khác nhau, một account không được quản lý trong HR/IdP.

Một sự kiện provisioning nên có **source event ID**, khóa nhận dạng được kiểm tra trong phạm vi, quy tắc idempotency và cơ chế đối chiếu. Không nên chỉ xử lý theo email không có kiểm chứng.

### 7.3. Kịch bản minh họa

**Use case hợp lệ:** học viên được trường ghi danh, nhận email kích hoạt, kiểm chứng quyền kiểm soát kênh và tạo phương thức đăng nhập.

**Abuse cases:** người lạ cố nhận email kích hoạt qua kênh bị kiểm soát sai, account được tạo với role TEACHER vì tham số client, email trùng được dùng để liên kết nhầm hồ sơ, hoặc tài khoản mời hết hạn vẫn có quyền.

**Security invariants:**

- Chỉ nguồn có thẩm quyền xác nhận tư cách học viên hoặc giảng viên.
- Quyền ban đầu được gán **phía server** theo trạng thái nghiệp vụ được phê duyệt.
- Enrollment chưa hoàn tất không có quyền truy cập dữ liệu bảo vệ ngoài phạm vi.
- Link kích hoạt có điều kiện sử dụng và thời hạn thích hợp; test chống replay và gắn sai account.
- Tài khoản trùng và xác nhận thất bại được xử lý có kiểm soát, lưu trace phù hợp.

Không cần công khai chi tiết cá nhân trong log để chứng minh enrollment: record có ID nội bộ, kết quả, nguồn và timestamp thường hữu ích hơn.

## 8. Credential và authenticator lifecycle

### 8.1. Các trạng thái có thể phát sinh

Một authenticator có thể trải qua:

**Requested → Enrollment pending → Bound/active → Used → Changed/rotated → Suspended/compromised → Revoked/retired**.

Không phải mọi authenticator giống nhau. Passkey/khóa phần cứng, ứng dụng xác thực, mật khẩu, certificate, recovery code và workload credential có yêu cầu kỹ thuật khác nhau. Chính sách cần mô tả **chủ thể, mức bảo đảm, trường hợp dùng, quản lý khóa/secret, phục hồi và thu hồi**.

### 8.2. Các security requirements

- **Binding:** thêm authenticator phải được phép và có đủ cơ sở để liên kết với đúng account.
- **Protection:** credential/secret lưu và truyền theo thiết kế bảo mật phù hợp; không ghi vào log/ticket.
- **Use:** authentication kiểm tra đúng policy, hạn, trạng thái bị thu hồi và điều kiện step-up.
- **Replacement:** đổi phương thức không vô hiệu hóa điều kiện bảo mật quan trọng một cách tùy tiện.
- **Loss/compromise:** có cách khóa, thu hồi, thay mới và điều tra khi nghi bị lộ.
- **Recovery:** khôi phục không trở thành đường bypass dễ hơn mức rủi ro cho phép.
- **Evidence:** hoạt động nhạy cảm tạo record có nguồn và thời điểm, có thể kiểm tra mà không lộ bí mật xác thực.

### 8.3. Authenticator enrollment là điểm tấn công

Một actor đã chiếm một phiên yếu có thể cố **đăng ký authenticator mới** để duy trì kiểm soát account. Vì vậy, bên cạnh kiểm tra đăng nhập, cần đánh giá policy đối với **thêm/xóa phương thức**, step-up khi rủi ro cao, thông báo cho chủ account theo kênh tin cậy và khả năng thu hồi.

**Bằng chứng:** policy version, test thêm authenticator trong các điều kiện quyền khác nhau, log binding/rebinding, sample hoặc audit sự kiện thay đổi theo kỳ.

### 8.4. Recovery code không phải bằng chứng danh tính ngoài đời

Một recovery code hoặc kênh email dự phòng chứng minh quyền kiểm soát một **phương tiện phục hồi** trong điều kiện xác định, không tự chứng minh chủ thể pháp lý. Tổ chức phải phân tích rủi ro khi kênh phục hồi bị chiếm quyền hoặc bị thay đổi. Khi yêu cầu proofing bổ sung, cần áp dụng theo thiết kế và nghĩa vụ, không tự suy diễn từ một mã phục hồi hợp lệ.

## 9. Provisioning và phân biệt danh tính với quyền

### 9.1. Kích hoạt danh tính không có nghĩa cấp mọi quyền

Một identity hợp lệ được kích hoạt có thể chỉ được phép đăng nhập xem thông tin cơ bản; quyền truy cập khóa học, lớp, hệ thống quản trị hay dữ liệu nhạy cảm thuộc **những quyết định entitlement riêng**.

Ví dụ:

- Xác nhận học viên thuộc trường **không tự cấp quyền xem mọi lớp**.
- Xác thực một giảng viên thành công **không cấp quyền sửa điểm của mọi học viên**.
- Tài khoản contractor còn hiệu lực **không mặc định truy cập production**.
- Workload có tên service hợp lệ **không có quyền đọc mọi bucket**.

### 9.2. Access provisioning control

| Điều kiện | Yêu cầu có thể kiểm chứng |
|---|---|
| Nguồn phê duyệt | Quyền nhạy cảm có request và approval phù hợp thẩm quyền |
| Scope | Đúng đối tượng, tenant, vai trò, môi trường và dữ liệu |
| Least privilege | Không cấp quyền vượt mục đích đã phê duyệt |
| Start/end | Có thời gian hiệu lực/hạn sử dụng khi policy yêu cầu |
| Segregation of duties | Quyền không tạo xung đột không được phê duyệt |
| Identity binding | Quyền gắn đúng immutable subject ID/account mapping |
| Propagation | Entitlement đã được cấp/thu hồi thật ở downstream systems |
| Audit | Có thể đối chiếu quyết định với hành động hệ thống |
| Review | Quyền tiếp tục tồn tại được xem xét theo định kỳ và trigger |

### 9.3. Điều kiện đủ không được suy từ trường role

Một bảng trong ứng dụng ghi TEACHER là **một thuộc tính**; quyền xuất dữ liệu lớp 42 còn phụ thuộc quan hệ phân công, trạng thái lớp và quy tắc theo tenant. Identity lifecycle assurance cần cung cấp **dữ liệu danh tính và quan hệ được quản lý đúng** cho access control; application authorization vẫn phải thực thi quyết định tại request.

## 10. Mover: thay đổi vai trò, thuộc tính và quan hệ

### 10.1. Mover thường nguy hiểm hơn tạo mới

Khi nhân sự chuyển nhóm, giảng viên đổi lớp hoặc vendor thay phạm vi hợp đồng, hệ thống có thể **cấp quyền mới nhưng quên thu hồi quyền cũ**. Đây là **privilege accumulation** và là một trong những nguồn tạo quyền dư phổ biến.

Ví dụ:

- Giảng viên A rời lớp 42, được phân công lớp 43.
- Hệ thống học vụ cập nhật quan hệ lớp.
- Learning API cache vẫn coi A là giảng viên lớp 42.
- Export worker đã xếp hàng nhiều job của lớp 42.
- Một số link file cũ vẫn có thể tải.

Assurance không thể dừng ở “role mới đã được cấp”. Cần kiểm tra **quyền cũ hết hiệu lực, quyền mới đúng phạm vi, và những đường đã phát hành quyền trước đó được xử lý theo chính sách**.

### 10.2. Các câu hỏi bắt buộc khi thay đổi

1. **Authoritative event** xuất phát từ đâu; actor nào có quyền tạo thay đổi?
2. Thời điểm hiệu lực là khi nào; có backdated change hay không?
3. Có **danh sách quyền cũ** để so sánh, hay chỉ append quyền mới?
4. Những ứng dụng nào nhận sự kiện; có hệ thống không hỗ trợ tự động?
5. Cache/session/token/job có giữ dữ liệu thuộc tính cũ hay không?
6. Nếu một downstream service thất bại, có retry, báo lỗi và reconciliation không?
7. Có access review cho quyền đặc biệt hoặc SoD conflict không?
8. Khi thay đổi diễn ra sai, có cơ chế khôi phục an toàn và audit trail không?

### 10.3. Before/after effective permissions

| Thời điểm | Quyền mong muốn | Quan sát cần xác minh |
|---|---|---|
| Trước ngày chuyển lớp | A được truy cập lớp 42, không phải lớp 43 | Policy và test xác nhận |
| Ngày quyết định chuyển hiệu lực | A không còn quyền lớp 42 theo quy định; quyền lớp 43 được cấp hợp lệ | Mapping, event, thời gian đồng bộ |
| Sau sự kiện ở API | API từ chối yêu cầu mới tới lớp 42 | Negative test |
| Sau sự kiện ở worker/cache | Không chạy/tạo file ngoài quyền theo policy vòng đời | Job trace, cache/revoke behavior |
| Sau rà soát | Không còn quyền cũ do group, local account hoặc batch role | Effective permission diff |

Không nên áp một thời hạn đồng bộ duy nhất cho mọi hệ thống; **mốc xử lý tối đa và phương án hạn chế truy cập trong lúc đồng bộ phải được tổ chức quy định theo rủi ro**.

## 11. Suspension, lock và reactivation

### 11.1. Tạm khóa khác chấm dứt

**Suspension/lock** có thể phát sinh khi có dấu hiệu account takeover, vi phạm chính sách, nghỉ phép dài ngày, thiếu giấy tờ hoặc tài khoản không hoạt động. **Termination** thường là kết thúc tư cách/quan hệ theo nguồn có thẩm quyền.

Tạm khóa có thể được gỡ sau khi có đủ điều kiện; chấm dứt thường kéo theo thu hồi và quy trình retention khác. Không thể chỉ dùng một boolean disabled để diễn tả mọi lý do và nghĩa vụ.

### 11.2. Các loại khóa cần xác định rõ

- Khóa **đăng nhập mới**.
- Vô hiệu hóa **phiên hiện có** theo chính sách.
- Thu hồi hoặc chặn **refresh/access token** qua cơ chế khả thi.
- Hạn chế **credential/API key** và quyền truy cập bên thứ ba.
- Tạm dừng **job/ủy quyền đã cấp** có thể tiếp tục xử lý dữ liệu.
- Chặn hoặc rà soát **quyền ngoại lệ/break-glass**.
- Giữ **audit trail và bằng chứng** cho điều tra, không tự xóa record nguồn.

Tùy thiết kế, access token tự chứa có thể tiếp tục hợp lệ cho đến khi hết hạn nếu hệ thống không có cơ chế từ chối/thu hồi bổ sung. **Assurance phải đối chiếu hành vi thực với cam kết và rủi ro**, không chỉ xem trạng thái “disabled”.

### 11.3. Reactivation là quyết định mới

Kích hoạt lại account sau khóa cần xác minh **lý do khóa đã được giải quyết**, chủ thể đủ quyền, phương thức xác thực có còn tin cậy, các entitlements có cần được cấp lại và có approval trong trường hợp nhạy cảm hay không.

Không nên tự phục hồi toàn bộ quyền admin cũ chỉ vì user đã lấy lại quyền đăng nhập; account recovery và entitlement restoration cần chính sách riêng.

## 12. Account recovery: điểm rủi ro cao của vòng đời

### 12.1. Vì sao recovery dễ bị lạm dụng?

Một hệ thống có authenticator mạnh vẫn có thể bị chiếm account khi quy trình hỗ trợ chấp nhận thông tin dễ đoán để đặt lại phương thức đăng nhập. Actor có thể giả mạo nhân viên hỗ trợ, chiếm email dự phòng, lợi dụng quy trình đổi số điện thoại hoặc yêu cầu ghép account.

**Threat scenarios:**

- Người khác cố khôi phục account bằng kênh liên hệ đã bị chiếm.
- Kẻ giả mạo nhân viên yêu cầu support vô hiệu hóa MFA.
- Actor đổi email phục hồi trước khi nạn nhân nhận thông báo.
- Link khôi phục bị dùng lại, quá hạn hoặc không ràng buộc đúng account.
- Account được khôi phục nhưng phiên có dấu hiệu bị chiếm vẫn tồn tại.
- Một tài khoản đã bị chấm dứt lại được kích hoạt vì recovery workflow bỏ qua trạng thái nguồn.

### 12.2. Assurance requirements cho recovery

| Mục tiêu | Điều phải xác minh |
|---|---|
| Xác minh đúng chủ thể | Cơ chế recovery chứng minh đủ theo rủi ro, không chỉ hỏi thông tin công khai |
| Ràng buộc đúng account | Recovery artifact gắn với account và mục đích rõ |
| Giới hạn thời gian/số lần | Mã/link recovery có thời hạn, chống replay và abuse phù hợp chính sách |
| Tách vai trò hỗ trợ | Thao tác support nhạy cảm có kiểm soát/approval theo mức tác động |
| Ngăn lạm dụng phiên cũ | Xử lý session/credential theo policy sau recovery |
| Thông báo và điều tra | Chủ account hoặc owner nhận thông tin theo kênh đáng tin khi thích hợp |
| Logging/evidence | Ghi dấu vết, người quyết định, kết quả, không lưu secret hoặc recovery code thô |
| Hạn chế cấp quyền lại | Recovery không tự nâng đặc quyền hoặc vượt trạng thái terminated |

### 12.3. Test case về recovery

1. Người dùng hợp lệ mất authenticator, hoàn tất xác minh và thiết lập lại phương thức theo policy.
2. Actor không đủ bằng chứng cố yêu cầu khôi phục một account khác → không được liên kết hoặc thay phương thức.
3. Recovery token đã dùng một lần → không thể dùng lại.
4. Recovery token hết hạn → bị từ chối theo cơ chế quy định.
5. Account suspended/terminated → recovery flow phải tôn trọng trạng thái và thẩm quyền kích hoạt lại.
6. Sau recovery, session/credential bị nghi lộ được xử lý theo chính sách.
7. Log không chứa toàn bộ mã bí mật hoặc thông tin nhạy cảm không cần thiết.
8. Khi email/điện thoại thay đổi, các quyết định và thông báo được kiểm chứng.

Không nên tự đưa mọi tài khoản qua một mức proofing cao như nhau. Người dùng chỉ đọc bài học công khai có rủi ro khác với nhân viên có quyền xuất dữ liệu và tài khoản cloud admin.

## 13. Termination và deprovisioning end-to-end

### 13.1. Offboarding không dừng ở IdP

Một nhân viên nghỉ việc nhưng vẫn giữ:

- Cloud access key hoặc personal access token.
- Session trên ứng dụng SaaS.
- SSH key/VPN certificate.
- OAuth grant trong ứng dụng bên thứ ba.
- Quyền trực tiếp ở cơ sở dữ liệu hoặc hệ thống legacy.
- Service account mà chỉ nhân viên đó biết secret.
- Khả năng tải file qua signed URL hoặc share link còn hiệu lực.
- Job chạy với danh tính/ủy quyền đã tạo trước ngày nghỉ.

Chỉ khóa account chính ở IdP **không chứng minh** những đường trên đã bị thu hồi. Một số quyền có thể được kiểm soát gián tiếp bởi IdP, một số hoàn toàn tách rời.

### 13.2. Checklist offboarding theo risk

| Nhóm | Hành động | Evidence/verification |
|---|---|---|
| Nguồn sự kiện | Xác nhận ngày và thẩm quyền kết thúc | HR/vendor/business event có timestamp |
| Identity directory | Disable/deprovision user và đồng bộ downstream | IdP state, target acknowledgments |
| Sessions/tokens | Revoke hoặc giới hạn theo cơ chế hỗ trợ và policy | Token/session tests, revoke logs |
| Privileged access | Gỡ group/role, cloud/database/IAM quyền trực tiếp | Effective permission diff, negative test |
| Third-party apps | Thu hồi OAuth consent, SaaS accounts, support access | App inventory, account status, audit record |
| Devices/certificates | Thu hồi chứng chỉ, VPN, SSH keys và credential liên quan | Certificate/key inventory, revoke event |
| Workload ownership | Chuyển owner hoặc rotate secret mà người rời đi có thể biết | Service registry, credential rotation evidence |
| Jobs/shares | Kiểm tra scheduled task, queue authorization và share links | Job trace, share/URL review |
| Data/records | Giữ/xóa thông tin theo pháp lý và nghiệp vụ | Retention decision, deletion evidence |
| Audit trail | Bảo vệ lịch sử truy cập và phê duyệt | Evidence archive, access controls |

**Tốc độ thu hồi** nên phân theo risk tier: truy cập đặc quyền production có thể cần xử lý theo quy trình khẩn hơn tài khoản diễn đàn ít ảnh hưởng. Bài này không tự đặt SLA bắt buộc; tổ chức phải lựa chọn thời hạn theo nguy cơ, hợp đồng và nghĩa vụ áp dụng.

### 13.3. Offboarding một bên không phải xóa mọi dữ liệu nghiệp vụ

Một giảng viên thôi dạy có thể mất quyền truy cập trong khi **bài giảng, lịch sử điểm, hồ sơ thi hoặc audit record** phải tiếp tục được lưu và sở hữu bởi tổ chức trong một khoảng hợp lệ. Cần phân biệt:

- **Deactivation/deprovisioning**: ngừng sử dụng tài khoản và quyền.
- **Data retention**: giữ record có căn cứ, hạn và quyền truy cập.
- **Deletion/anonymization**: xóa hoặc biến đổi dữ liệu theo mục đích, luật, hợp đồng và kỹ thuật cho phép.

Đóng account không đồng nghĩa được xóa dữ liệu học tập có nghĩa vụ lưu; giữ dữ liệu cũng không đồng nghĩa được tiếp tục cho account cũ đăng nhập.

## 14. Retention, deletion và privacy trong identity lifecycle

### 14.1. Danh tính là dữ liệu có vòng đời riêng

Identity records có thể chứa:

- Tên, liên hệ, quan hệ tổ chức.
- Thuộc tính xác minh và bằng chứng proofing.
- Lịch sử phương thức xác thực, thiết bị/khóa đăng ký.
- IP, thông tin truy cập, lịch sử thay đổi profile.
- Role, grants, approvals, account linkage và audit logs.

Những dữ liệu này có thể nhạy cảm. Chuẩn identity assurance nên xác định **mục đích xử lý, cơ sở/điều kiện áp dụng, người truy cập, retention, cơ chế xóa và ngoại lệ cần thiết** theo chính sách và pháp luật liên quan.

### 14.2. Data minimization

Không thu thập ảnh giấy tờ, số định danh chính phủ hoặc sinh trắc chỉ để tạo account nếu mục tiêu thực tế không cần và không có căn cứ thích hợp. Khi một lần proofing được thực hiện qua nhà cung cấp, hệ thống có thể chỉ cần **kết quả và metadata cần thiết** thay vì giữ toàn bộ ảnh nguồn; phải quyết định theo nghĩa vụ và rủi ro.

### 14.3. Xóa và bảo toàn bằng chứng có thể cùng tồn tại

Một account bị xóa theo quy định nhưng tổ chức vẫn có thể cần giữ **audit record tối thiểu và được bảo vệ** phục vụ nghĩa vụ cụ thể. Cần phân biệt dữ liệu profile không còn cần, log có thời hạn, record giao dịch và tài liệu pháp chứng có legal hold hợp lệ.

Không hứa “xóa mọi bản sao ngay tức thì” khi backup/subprocessor và quy định lưu trữ chưa được đánh giá; cần có **thời hạn và quy trình xử lý được ghi rõ**, báo cáo giới hạn chính xác.

## 15. Non-human identity lifecycle

### 15.1. Workload identity cũng cần owner và trạng thái

Không phải danh tính nào cũng thuộc một con người. Backend Java, report-worker, CI/CD runner, ETL job, bot, integration và cloud workload có thể sử dụng **service account**, token, certificate hoặc workload identity.

Các mốc vòng đời:

**Request/owner approval → Create identity → Bind workload → Grant scopes → Operate/monitor → Rotate/reissue → Review → Revoke/decommission**.

Không áp dụng mô hình “nhân viên nghỉ việc” nguyên xi cho service account; trigger có thể là **dịch vụ bị xóa, chủ sở hữu thay, repo chuyển team, kết nối vendor chấm dứt, secret lộ hoặc quyền thay đổi**.

### 15.2. Các rủi ro nổi bật

- Một service account không có owner, sống lâu sau khi service đã bị xóa.
- Token không hết hạn hoặc có scope quá rộng.
- Secret dùng chung cho staging và production.
- Account được dùng bởi nhiều workload nên khó truy vết.
- Credential nằm trong source code, image hoặc log.
- Service mới kế thừa quyền của service cũ không còn hợp lệ.
- Ngừng vendor nhưng cron job tiếp tục gửi dữ liệu bằng token cũ.
- Workload identity federation sai audience/subject hoặc trust policy rộng.

### 15.3. Control và evidence

| Control objective | Control gợi ý | Bằng chứng nên kiểm tra |
|---|---|---|
| Có chủ thể chịu trách nhiệm | Service identity registry, owner mapping | Inventory, service/owner approvals |
| Chỉ workload hợp lệ dùng identity | Ràng buộc workload với issuer, subject, audience và trust policy theo kiến trúc | Policy runtime, negative tests |
| Quyền tối thiểu | IAM scopes/roles theo tài nguyên thực | Runtime policy export, test ngoài quyền |
| Secret được bảo vệ | Secret manager/identity-based access, không hardcode | Config review, scan result, rotation records |
| Rotation/revocation | Quy trình thay credential, xử lý khi lộ | Rotate/revoke tests, audit log |
| Không tồn tại mồ côi | Reconciliation service inventory và IAM | Orphan identity report, remediation |
| Logging và phát hiện | Truy vết workload, nguồn gọi và hành vi | Workload audit events, alert tests |
| Decommission | Gỡ quyền, tắt credential, job và kết nối | Disable logs, negative use test, exit checklist |

**MFA của con người không phải yêu cầu phù hợp trực tiếp cho workload**; phải kiểm tra cơ chế xác thực workload được thiết kế và áp dụng. Đồng thời, không vì service không có MFA mà được miễn kiểm tra identity lifecycle.

## 16. Privileged và emergency identity lifecycle

### 16.1. Quyền đặc biệt cần quản lý chặt hơn

Cloud administrator, database administrator, tenant superadmin, IAM policy editor, CI/CD deployer và support account có thể ảnh hưởng nhiều tài sản. Chúng thường cần:

- Nguồn đề nghị và người phê duyệt đúng thẩm quyền.
- Phân tách nhiệm vụ, giới hạn quyền và phạm vi theo rủi ro.
- Xác thực mạnh theo policy và quản lý session.
- Quyền nâng cao tạm thời hoặc cơ chế duyệt riêng khi phù hợp.
- Rà soát quyền và hành vi đã sử dụng.
- Điều kiện xử lý khi nhân sự thay đổi hoặc bị nghi bị chiếm account.
- Audit trail và cảnh báo các thao tác nhạy cảm.

### 16.2. Break-glass

Tài khoản/cơ chế khẩn cấp có thể cần thiết khi IdP hoặc nền tảng xác thực gặp sự cố. Tuy nhiên, nó không được trở thành **đường bypass thường trực** không có người chịu trách nhiệm.

Một assurance plan cần xác định:

- Tại sao phải tồn tại và trường hợp được dùng.
- Ai giữ quyền kích hoạt hoặc bí mật khẩn cấp?
- Cách bảo vệ, giám sát, kiểm tra định kỳ và xử lý sau sử dụng.
- Phân biệt quyền khẩn với quyền thông thường.
- Cách thu hồi/rotate sau sự cố.
- Cách bảo đảm tính sẵn sàng khi thực sự cần.
- Cơ chế đánh giá riêng nếu không thể dùng các điều kiện xác thực thông thường.

Một test chỉ xác nhận tài khoản khẩn “có thể đăng nhập” chưa chứng minh nó được **giới hạn, sử dụng đúng điều kiện và có hậu kiểm**.

## 17. Identity lifecycle trong hệ thống liên kết và phân tán

### 17.1. Luồng sự kiện đi qua nhiều thành phần

~~~mermaid
flowchart LR
    HR["Nguồn người dùng/học vụ/vendor"] --> IAM["Identity lifecycle orchestration"]
    IAM --> IDP["Identity Provider"]
    IAM --> APP["Learning API / Directory"]
    IAM --> CLOUD["Cloud IAM / SaaS"]
    IDP --> TOK["Sessions / Tokens"]
    APP --> JOB["Queue / Worker"]
    IAM --> EVD["Event journal / Evidence store"]
    IDP --> EVD
    APP --> EVD
    CLOUD --> EVD
    JOB --> EVD
~~~

Một lần HR cập nhật trạng thái “leaver” có thể cần nhiều hành động **không nguyên tử** tại IdP, learning-app, cloud, SaaS và worker. Vì thế vấn đề quan trọng không chỉ là gửi event mà còn là **biết đích nào đã xử lý, đích nào thất bại và liệu còn truy cập hay không**.

### 17.2. Các lỗi phân tán cần dự đoán

| Vấn đề | Hậu quả có thể | Control cần xem |
|---|---|---|
| Event đến trễ | Quyền cũ tồn tại lâu hơn chính sách cho phép | SLA propagation, alert/reconciliation |
| Event lặp | Tạo trùng tài khoản hoặc cấp lại quyền | Idempotency/event IDs |
| Event sai thứ tự | Sự kiện “Activate” cũ đến sau “Terminate” | Version/sequence và state transition guard |
| Partial failure | IdP đã disable nhưng SaaS còn active | Target acknowledgment, retry, reconciliation |
| Stale cache/token | Request được phép dù thuộc tính đã đổi | TTL/revocation design và test |
| Lost event | Một downstream không bao giờ nhận cập nhật | Periodic full reconciliation |
| Clock skew | Thời điểm hiệu lực bị hiểu sai | Timestamp semantics, clock sync |
| Manual override | Admin thêm quyền trực tiếp ngoài workflow | Audit, drift detection, approval review |
| Mismatch identifier | Đồng bộ event vào account sai | Stable ID, mapping verification |
| Missing evidence | Không biết đã deprovision thành công hay chưa | Evidence quality checks, investigation |

### 17.3. Thứ tự và tính idempotent

Một mô hình đơn giản để giảm rủi ro:

- Mỗi lifecycle event có **eventId**, **subjectId**, **eventVersion** hoặc mốc tương đương đáng tin, **source**, **type**, **effectiveAt**.
- State transition kiểm tra **thứ tự hợp lệ** và **trạng thái authoritative hiện tại**.
- Event cũ hoặc duplicate không được tự kích hoạt account đã terminated.
- Quyền được cập nhật theo **desired state** có căn cứ, không chỉ cộng thêm grants mới.
- Ghi trạng thái xử lý theo target system, retry có giới hạn và cảnh báo khi không hoàn tất.
- Định kỳ so sánh **actual states** với authoritative state; sửa lệch có kiểm soát.

**Không nên chỉ tin vào timestamp client gửi** hoặc một email dùng lại để xác định event mới hơn. Cơ chế thứ tự cần dựa trên nguồn authoritative và mô hình nhất quán phù hợp.

## 18. Ví dụ Java: phòng ngừa sự kiện lifecycle cũ kích hoạt lại tài khoản

Đoạn mã Java sau minh họa **ý tưởng chặn replay/out-of-order** của sự kiện lifecycle, không phải chương trình hoàn chỉnh có thể chạy nguyên xi. Phải bổ sung giao dịch, idempotency storage, xác thực event origin, mapping subject, concurrency control, audit và xử lý hệ thống downstream trong ứng dụng thật.

~~~java
public void applyLifecycleEvent(LifecycleEvent event) {
    // Chỉ nhận event từ nguồn đã được xác thực, được ủy quyền.
    verifyTrustedSource(event.source(), event.signature());

    Identity identity = identityRepository.findByStableSubjectId(
            event.subjectId());

    // Version/sequence được cấp từ nguồn authoritative.
    // Không lấy dữ liệu client tự khai làm thứ tự quyết định.
    if (event.version() <= identity.lastAppliedVersion()) {
        audit.recordIgnoredDuplicateOrStale(event.id(), identity.id());
        return;
    }

    if (!transitionPolicy.isAllowed(
            identity.state(), event.type(), event.source())) {
        audit.recordRejectedTransition(event.id(), identity.id());
        throw new InvalidLifecycleTransitionException();
    }

    identity.applyAuthorizedTransition(
            event.type(), event.effectiveAt(), event.version());

    // Trong triển khai thật: ghi state + outbox atomically.
    identityRepository.saveWithOutbox(identity, event.id());

    // Downstream grants, sessions, SaaS và service access cần
    // đồng bộ/đối chiếu riêng; save không đồng nghĩa đã revoke hết.
}
~~~

### 18.1. Những điểm cần kiểm chứng ngoài đoạn mã

1. **Nguồn event** được xác thực bằng cơ chế phù hợp, không để client giả mạo “terminated” hoặc “active”.
2. **Version ordering** thật sự nhất quán cho mỗi subject và không thể reset để qua guard.
3. **Identity lookup** xử lý account trùng, subject chưa tồn tại hoặc mapping bị sửa.
4. **Atomicity** của cập nhật local state và phát outbox đủ cho hệ thống đã thiết kế.
5. **Delivery semantics**: retry, duplicate, dead-letter queue, poison messages.
6. **Downstream state**: IdP, SaaS, cloud và API đều được quan sát và đối chiếu.
7. **Revocation behavior**: session/cache/token và dữ liệu đã xuất theo policy.
8. **Audit trail**: ghi đủ thao tác, không chứa secret hoặc bằng chứng nhạy cảm ngoài cần thiết.
9. **Race tests**: mover và terminate đến đồng thời hoặc theo thứ tự khác nhau.
10. **Recovery/rollback**: sửa trạng thái sai phải qua ủy quyền, không tự chuyển lại Active.

### 18.2. Kiểm thử minh họa

~~~java
@Test
void staleActivationCannotUndoTermination() {
    var subject = fixtures.activeTeacher("teacher-42");

    lifecycle.apply(event("terminated", subject.id(), 21));
    lifecycle.apply(event("activated", subject.id(), 20));

    assertEquals(
        IdentityState.TERMINATED,
        identities.find(subject.id()).state());

    // Cần xác minh thêm effective access ở từng downstream.
    assertFalse(accessPolicy.canExportClass(subject.id(), 42L));
}

@Test
void duplicateTerminationIsIdempotent() {
    var subject = fixtures.activeTeacher("teacher-42");

    lifecycle.apply(event("terminated", subject.id(), 21));
    lifecycle.apply(event("terminated", subject.id(), 21));

    assertEquals(IdentityState.TERMINATED,
        identities.find(subject.id()).state());
    // Kiểm tra không tạo thêm tác dụng ngoài dự kiến.
}
~~~

Test trên là **pseudo-code mang tính sư phạm**: tên hàm, fixture và enum phải điều chỉnh theo project, không phải mã sản xuất đầy đủ. Hai kiểm thử chỉ hỗ trợ claim về một phần **state transition logic**, không chứng minh SaaS/token/session đã bị thu hồi.

## 19. Kiểm thử vòng đời danh tính: test matrix

| ID | Actor/trạng thái đầu | Sự kiện hoặc yêu cầu | Expected result | Evidence ngoài response |
|---|---|---|---|---|
| IL-01 | Người mới chưa có identity | Đăng ký theo nguồn hợp lệ | Pending/active đúng điều kiện, không role nhạy cảm tự cấp | Source/request, account link |
| IL-02 | Người dùng chưa xác minh kênh | Gọi tính năng yêu cầu kích hoạt | Từ chối khi chưa đủ điều kiện | Policy, token/session status |
| IL-03 | Account đã tồn tại | Nhận trùng enrollment event | Không tạo account/quyền duplicate | Event journal, identity mapping |
| IL-04 | Actor không có thẩm quyền | Gửi sự kiện cấp role TEACHER | Không cấp quyền | Approval check, audit |
| IL-05 | Giảng viên lớp 42 | Chuyển sang lớp 43 | Quyền cũ bị thu hồi, quyền mới đúng scope | Effective permissions, API/worker tests |
| IL-06 | Account active | Suspended theo policy | Không tiếp tục truy cập qua các đường thuộc scope | Session/token, SaaS and API checks |
| IL-07 | Account suspended | Yêu cầu reactivation không có approval | Không tự Active | Workflow, audit record |
| IL-08 | Người mất authenticator | Recovery hợp lệ | Rebinding theo policy, session cũ xử lý thích hợp | Binding record, notifications |
| IL-09 | Actor giả danh | Cố phục hồi account người khác | Không thay credential/account link | Negative test, recovery log |
| IL-10 | Account đã terminated | Event activate cũ đến muộn | Giữ terminated | Event version/audit |
| IL-11 | Account active | Nhận hai termination events giống nhau | Idempotent, không tạo tác dụng ngoài | Outbox/processing logs |
| IL-12 | IdP đã disable | Downstream SaaS tạm không nhận revoke | Retry/alert, state chờ và đánh giá phơi bày | Reconciliation, target acknowledgment |
| IL-13 | Vendor contract đã kết thúc | Revocation của vendor identity | Không còn app/token/scope đã giao | OAuth/IAM exports, negative test |
| IL-14 | Service bị decommission | Xóa workload identity | Không còn credential/call path hoạt động | Registry, permission diff |
| IL-15 | Account archive | Hết retention theo policy | Xóa/giữ theo quy tắc và ngoại lệ | Deletion record, legal hold |
| IL-16 | Privileged break-glass | Dùng quyền khẩn cấp | Đúng quy trình, log và hậu kiểm | Approval/incident, audit session |
| IL-17 | Hai account cùng email | Yêu cầu liên kết tài khoản | Không hợp nhất sai chủ thể | Matching/linking proof |
| IL-18 | User đã đổi email | Dùng kênh cũ để recovery | Hành vi theo policy, không chiếm account | Contact history, negative test |

**Test matrix phải xác định environment, dataset, account fixtures, policy version và phạm vi**. Test ở staging không tự chứng minh production đúng nếu bản triển khai hoặc dữ liệu quyền khác. Với điều kiện rủi ro cao, cần test end-to-end và evidence runtime phù hợp.

### 19.1. Positive, negative, failure và side-effect tests

- **Positive:** sự kiện hợp lệ tạo thay đổi đúng, người dùng đủ quyền vẫn thao tác được.
- **Negative:** actor không có thẩm quyền, mã cũ hoặc yêu cầu sai account bị từ chối.
- **Boundary:** ngày hiệu lực, role hết hạn, token còn sống, session đang mở, account đang pending.
- **Concurrency:** hai event cùng lúc, duplicate, retry và out-of-order.
- **Failure:** IdP/SaaS/queue không sẵn sàng, lỗi một target, timeout và rollback.
- **Side effects:** không tự tạo quyền mới, job mới, email chứa thông tin nhạy cảm hoặc đường truy cập sau deny.
- **Audit:** event có thể truy vết, đủ nguồn/thời gian, không ghi secret.

Chỉ kiểm tra API trả 200/403 **chưa đủ** nếu downstream vẫn cấp quyền, tạo file hoặc giữ token sống.

## 20. Evidence standard cho identity lifecycle assurance

### 20.1. Nguồn bằng chứng phổ biến

| Claim | Evidence thiết kế | Evidence triển khai | Evidence vận hành |
|---|---|---|---|
| Chỉ nguồn được phép tạo identity | Enrollment policy, data flow | API/event source validation | Sample event/approval và audit trail |
| Account linking không chiếm account | Linking rules, threat model | Code/config + negative test | Change/recovery records, incident review |
| Role được cấp đúng tư cách | Entitlement model/RACI | Provisioning logic, effective permissions | Grant/approval history và access review |
| Mover thu hồi quyền cũ | State transition requirements | Sync jobs, revocation tests | Before/after diffs, reconciliation |
| Suspended account không tiếp tục truy cập trái policy | Suspension/session rules | IdP/API/token config | Lock/revoke tests, activity records |
| Recovery gắn đúng chủ thể | Recovery proofing/approval design | Token binding, policy tests | Recovery events, exception review |
| Leaver không còn đường truy cập | Offboarding policy, system scope | Deprovision workflow và integrations | Target acknowledgments, negative tests |
| Workload identity có owner/quyền tối thiểu | Service registry và control objective | IAM trust/scope config | Rotation, usage review, orphan scan |
| Identity data được lưu/xóa đúng hạn | Retention rule, data map | Deletion/archival controls | Disposal record, access review, exception |

### 20.2. Chất lượng của evidence

Một evidence tốt cần:

1. **Relevance:** trực tiếp hỗ trợ claim và control nào?
2. **Scope:** system, tenant, account type, environment và target systems có đầy đủ?
3. **Population/completeness:** có bao gồm local accounts, emergency, vendor, workload theo claim?
4. **Period/freshness:** phản ánh đúng kỳ/phiên bản, hay chỉ một screenshot tại thời điểm?
5. **Provenance:** nguồn authoritative, công cụ, query, producer, thời gian rõ.
6. **Integrity:** có chống sửa/xóa không được phép, giữ đường đối chiếu?
7. **Reliability:** sync, event pipeline, log collector và script có hoạt động đúng?
8. **Representativeness:** mẫu có bao phủ actor, risk và đường hệ thống cần thiết?
9. **Repeatability:** người đánh giá khác có thể tái kiểm tra theo điều kiện hợp lệ?
10. **Confidentiality:** không lưu lộ secret, token, ảnh giấy tờ hoặc PII quá mức.

Một báo cáo “100% tài khoản nghỉ việc đã disable” chỉ có nghĩa khi **mẫu số leavers, thời kỳ, hệ thống nguồn, target coverage và cách xác nhận disable** được giải thích.

### 20.3. Record YAML minh họa

~~~yaml
evidence_id: EVD-IDENTITY-LEAVER-2026Q4-01
claim_id: CLAIM-ID-LEAVER-01
requirement_ids:
  - ID-REQ-TERMINATE-01
  - ID-REQ-SESSION-REVOCATION-02
scope:
  population: "Workforce identities with completed leaver events"
  authoritative_sources: ["workforce-system", "vendor-registry"]
  targets: ["corporate-idp", "learning-api", "cloud-iam", "approved-saas"]
  period: "Kỳ đánh giá nội bộ được phê duyệt"
  exclusions: ["Workloads under separate lifecycle assessment"]
owner:
  risk: "Service business owner"
  control: "IAM Operations"
  evidence: "IAM Engineering"
  reviewer: "Security Assurance"
criteria:
  - "Every valid leaver event has source and subject mapping"
  - "Target account, grants and sessions meet approved revoke policy"
  - "Failed target synchronization is detected and remediated"
methods:
  - "Reconcile authoritative leaver population to target inventories"
  - "Sample high-risk accounts and test effective access"
  - "Review retry, stale events and exceptions"
artifacts:
  - "Authoritative event export with time and source metadata"
  - "Target disable/revoke acknowledgments"
  - "Effective access negative test and audit history"
  - "Exception, finding and retest records"
assumptions:
  - "Source identity mapping has been verified"
limitations:
  - "No conclusion for unregistered local accounts until inventoried"
result: "Pending evidence validation"
quality:
  source_integrity: "Needs reviewer verification"
  completeness: "Needs reviewer verification"
reassessment_triggers:
  - "New SaaS integration, identity provider or privileged path"
  - "Failed deprovision, account takeover or reconciliation drift"
~~~

Đây chỉ là **mẫu mô tả**; không chứa kết quả audit thực tế. Các trường Source/Target phải dùng danh mục hệ thống thật, và mục “Pending” không được tự đổi thành “Pass” trước khi người đánh giá kiểm tra.

## 21. Claim–Argument–Evidence cho một lifecycle claim

### 21.1. Định nghĩa claim

> **Claim:** Trong phạm vi workforce identities và các hệ thống production được liệt kê, khi một nhân sự có sự kiện chấm dứt hợp lệ, các quyền và đường truy cập tương ứng được thu hồi theo chính sách trong kỳ đánh giá; các trường hợp thất bại hoặc không thuộc phạm vi được ghi và xử lý riêng.

### 21.2. Argument

1. Nguồn workforce/vendor có thẩm quyền xác định **ai** đã kết thúc tư cách và **khi nào**.
2. Mapping ổn định gắn đúng subject với account ở IdP và target systems.
3. Orchestration bảo vệ thứ tự/idempotency của lifecycle events và ghi trạng thái thực thi.
4. Các target accounts/grants, session/token và quyền ngoài IdP được xử lý theo thiết kế đã phê duyệt.
5. Reconciliation tìm quyền sót, target thất bại và trường hợp manual/bypass.
6. Negative tests và operating records xác nhận actor không còn effective access theo tiêu chí.
7. Những ngoại lệ, hệ thống thiếu quan sát và thay đổi điều kiện được báo cho risk owner.

### 21.3. Evidence

- Danh sách leaver events từ nguồn có thẩm quyền với mốc thời gian và ID.
- Bảng identity mapping giữa source subject và target accounts.
- IdP/IAM/SaaS exports, nhóm quyền, revoke/disable timestamps.
- Outbox/event journal, acknowledgment từ mỗi target, retry/dead-letter logs.
- Negative tests với actor kiểm soát, bao gồm cloud, API và SaaS scope.
- Session/token behavior verification, đặc biệt các đường privileged.
- Báo cáo access review/reconciliation, finding và retest.
- Review của assessor với phạm vi, thời kỳ, phương pháp và limitations.

### 21.4. Giới hạn hợp lệ

Nếu ứng dụng legacy có local admin chưa nằm trong inventory, claim không thể bao phủ nó. Nếu chỉ có trạng thái hiện tại mà không có lịch sử, khó kết luận control đã hoạt động **suốt kỳ**. Nếu không thu được log vì pipeline bị lỗi, đó là **evidence gap**, không tự chứng minh leaver vẫn truy cập hay đã bị chặn.

Một kết luận có chất lượng luôn nói **điều được chứng minh, điều không được chứng minh và rủi ro còn lại**.

## 22. Case study: vòng đời giảng viên trên nền tảng học Java

### 22.1. Bối cảnh

Nền tảng học trực tuyến có:

- **Academic System:** quản lý giảng viên và phân công lớp.
- **Identity Provider:** xác thực đăng nhập, quản lý phương thức và session.
- **Learning API Java:** cung cấp xem điểm, nhập điểm, xuất danh sách.
- **PostgreSQL:** lưu users, class assignment và quyền nghiệp vụ.
- **Queue/Report Worker:** xử lý export bất đồng bộ.
- **Object Storage:** giữ file export.
- **Vendor SaaS:** cung cấp công cụ phân tích hoặc thông báo.

Một giảng viên A rời trường. Academic System phát sự kiện **TEACHER_TERMINATED**. Product owner muốn chứng minh rằng A **không thể tiếp tục truy cập dữ liệu học viên hoặc thực hiện thao tác liên quan** sau mốc hiệu lực theo policy.

### 22.2. Risk scenarios và kiểm soát

| Risk ID | Kịch bản | Control cần xem | Evidence |
|---|---|---|---|
| R-ID-01 | Academic System gửi nhầm subjectId hoặc thiếu event | Source validation và reconciliation | Event source, subject mapping, population diff |
| R-ID-02 | Event bị lặp/tới sai thứ tự, account được kích hoạt lại | Version guard, idempotency | Event journal, transition tests |
| R-ID-03 | IdP disable nhưng session API còn hoạt động | Session/token policy | Revoke/expiry tests, runtime config |
| R-ID-04 | Quyền giảng dạy cũ vẫn còn trong DB/cache | Entitlement revoke và cache invalidation | Before/after rights, negative tests |
| R-ID-05 | Worker xử lý job cũ sau khi A mất quyền | Job authorization lifecycle | Queue/job/file trace, controlled tests |
| R-ID-06 | File xuất vẫn tải được qua link đã phát hành | Download access/URL lifecycle | Storage/URL test, access logs |
| R-ID-07 | Vendor SaaS hoặc admin support account chưa bị thu hồi | Third-party identity offboarding | Vendor inventory, revoke evidence |
| R-ID-08 | Log thiếu nên không biết sự kiện đã thành công | Evidence pipeline/monitoring | Source health, target acknowledgments |
| R-ID-09 | Dữ liệu học tập bị xóa nhầm cùng account | Separate identity deprovisioning and retention | Data retention policy, negative integrity test |

### 22.3. Dòng thời gian cần xem xét

| Mốc | Điều kỳ vọng | Cách xác minh |
|---|---|---|
| T0 – Academic System quyết định chấm dứt | Có event được phê duyệt và effectiveAt rõ | Authoritative event và audit |
| T1 – IAM orchestration nhận event | Đúng subject, đúng version, không duplicate lạ | Event processing record |
| T2 – IdP và application cập nhật | Account/entitlements thay trạng thái đúng | Export runtime, authorization test |
| T3 – Session/token và job xử lý | Không tiếp tục cho phép ngoài chính sách | Revoke tests, queue/file inspection |
| T4 – SaaS/cloud integrations xác nhận | Không còn grant, quyền hoặc phiên ngoài policy | Target acknowledgments và negative checks |
| T5 – Reconciliation/review | Không còn quyền mồ côi trong scope; gaps được báo | Diff, exceptions, remediation |
| T6 – Retention | Hồ sơ học tập cần giữ vẫn nguyên vẹn; quyền cũ không còn | Data integrity check, retention review |

Các mốc là **trình tự minh họa, không định nghĩa số phút bắt buộc**. Nếu hệ thống thực có SLAs/thresholds cụ thể, chúng phải được ghi vào requirement và phép đánh giá.

### 22.4. Negative test quyết định

Sau khi sự kiện termination được áp dụng và đạt thời điểm kiểm tra theo policy, dùng test account của A trong môi trường kiểm soát thử:

1. Đăng nhập mới qua IdP và các đường local SSO phụ.
2. Gọi API đọc điểm với session/token đã được phát hành trước đó.
3. Yêu cầu export mới cho lớp A từng dạy.
4. Tải file đã có sẵn bằng đường đã phát hành.
5. Kiểm tra job đang chờ hoặc đã chạy không tạo file ngoài điều kiện.
6. Kiểm tra các OAuth/SaaS grants và quyền cloud nếu A có liên quan.
7. Xác nhận các tài khoản giảng viên khác vẫn dùng được chức năng hợp lệ.
8. Kiểm tra lịch sử điểm/hồ sơ học viên không bị xóa sai.

Không nhất thiết kết quả của mọi phép thử là “từ chối ngay tại cùng một giây”. Kỳ vọng phải **khớp chính sách, cơ chế session/download, giới hạn kỹ thuật, tác động và cam kết đã được duyệt**. Nếu một đường vẫn cho truy cập trái requirement, mở finding với evidence.

### 22.5. Khi chỉ có ảnh chụp “Disabled”

IAM team cung cấp ảnh tài khoản A có trạng thái “Disabled”. Điều này hỗ trợ claim **IdP account bị disable tại thời điểm chụp**, chưa chứng minh:

- Tất cả target systems đã nhận event.
- Existing sessions/tokens đã bị chặn theo policy.
- App/worker không còn dùng assignment cũ.
- Quyền SaaS, cloud hoặc local account đã gỡ.
- Trong cả kỳ, mọi leaver đều được xử lý đúng.
- Không còn quyền khác do A sở hữu hoặc chia sẻ.

Assessor nên yêu cầu evidence bổ sung, kiểm tra phạm vi và báo cáo **insufficient evidence** cho những phần chưa được chứng minh, thay vì mặc định toàn bộ vòng đời đạt.

## 23. Quản lý finding, exception và residual risk

### 23.1. Phân loại kết quả trung thực

| Kết luận | Điều kiện | Phản ứng |
|---|---|---|
| **Pass/Supported** | Control đáp ứng tiêu chí trong scope/kỳ, evidence hợp lệ | Ghi claim và limitations, tiếp tục giám sát |
| **Fail/Unsupported** | Có bằng chứng thay đổi quyền/trạng thái không đúng policy | Finding, đánh giá risk, containment, fix, retest |
| **Insufficient evidence** | Thiếu population, log, mapping, test hoặc nguồn tin cậy | Evidence request, mở rộng kiểm tra, hạn chế claim |
| **Not applicable** | Có căn cứ rằng control không liên quan phạm vi | Ghi rationale và trigger review |
| **Exception được duyệt** | Sai lệch policy nội bộ được cho phép có điều kiện và thẩm quyền | Theo dõi risk/conditions; không tự biến test fail thành pass |

Các trạng thái chỉ là ví dụ tổ chức nội bộ. Khi đánh giá theo chương trình audit hoặc tiêu chuẩn cụ thể, phải tuân theo quy tắc kết luận của chương trình đó.

### 23.2. Ví dụ finding

**Finding:** Ở môi trường production, khi giảng viên A bị chấm dứt, IdP ngừng đăng nhập mới nhưng một refresh token cũ vẫn cấp access token qua luồng chưa tích hợp trạng thái account; actor có thể đọc dữ liệu lớp thuộc quyền cũ trong khoảng thời gian vượt giới hạn policy.

**Evidence:** token/session test với dữ liệu kiểm soát, IdP event và mốc hiệu lực, API log, runtime policy, version, quyền tại thời điểm request. Nếu chưa xác minh dữ liệu thật bị lấy, không nên tự khẳng định đã xảy ra data breach.

**Actions:**

1. Giới hạn đường truy cập liên quan theo thẩm quyền/risk.
2. Kiểm tra tác động thực tế và các nghĩa vụ incident khi cần.
3. Sửa token validation/session revocation hoặc nguồn quyết định quyền theo policy.
4. Test với session cũ, refresh path, các quyền API và queue.
5. Triển khai đúng artifact, retest runtime và đánh giá lịch sử sự kiện.
6. Cập nhật finding, residual risk, control register và test suite.

### 23.3. Risk acceptance không sửa được sự thật kỹ thuật

Risk owner có thể cân nhắc chấp nhận **một mức residual risk xác định** trong giới hạn ủy quyền và nghĩa vụ, ví dụ một hệ thống legacy chưa tích hợp deprovision đầy đủ nhưng đã được hạn chế tạm thời với control bù trừ được kiểm chứng. Tuy nhiên:

- Không được tự đổi kết quả test fail thành pass.
- Không bỏ qua nghĩa vụ pháp lý/hợp đồng bắt buộc.
- Phải ghi scope, điều kiện, thời hạn, trigger và plan khắc phục.
- Nếu control bù trừ không hoạt động, cần xem xét lại quyết định ngay.
- Chữ ký acceptance không thay nguồn evidence về trạng thái tài khoản.

## 24. Chương trình continuous identity assurance

### 24.1. Không chỉ đánh giá theo kỳ audit

Identity lifecycle có thể thay đổi hàng ngày: account mới, chuyển lớp, đổi email, credential enrollment, role grants, terminated staff, service deployments và vendor exits. Assurance cần **giám sát sự kiện rủi ro cao và đánh giá theo kỳ thích hợp**, không phải chỉ chụp danh sách tài khoản vào cuối năm.

| Hoạt động | Automation hoặc review | Trigger |
|---|---|---|
| Enrollment | Kiểm tra nguồn, account duplicate, binding | Cơ chế đăng ký đổi, thêm IdP |
| HR/vendor reconciliation | So source vs target accounts, disabled states | Leaver event, đổi vendor, sync errors |
| Entitlement review | So effective permissions với approval/owner | Mover, privileged grant, review deadline |
| Authenticator change | Kiểm tra enrollment/recovery events | Phát hiện bất thường, policy đổi |
| Session/token controls | Test revoke và đường bypass | Session architecture đổi, incident |
| Workload identities | Inventory, scope diff, orphan detection | Service decommission, CI/CD/cloud change |
| Privileged access | Review break-glass và JIT grants | Emergency use, unusual admin event |
| Recovery monitoring | Review account linking và đổi phương thức | Password/MFA reset spike, support incident |
| Evidence health | Pipeline completeness, source/target acknowledgments | Collector failure, missing population |
| Retention/deletion | Review nghĩa vụ và kết quả xử lý dữ liệu | Hết thời hạn, chấm dứt, legal hold |

**Continuous assurance** không có nghĩa mọi control phải được kiểm thử mỗi phút. Thiết kế tần suất dựa trên **impact, độ biến động, độ tin cậy dữ liệu và cam kết**, còn những trigger quan trọng phải kích hoạt đánh giá lại trước kỳ review.

### 24.2. Metrics nên đi kèm mẫu số và giới hạn

| Metric | Câu hỏi quản trị | Không nên kết luận quá mức |
|---|---|---|
| % identities có owner/source rõ | Inventory và accountability đủ chưa? | Có owner không chứng minh identity binding đúng |
| % leavers được deprovision theo SLA đã phê duyệt | Có đáp ứng thời gian thu hồi? | Chỉ đo targets đã inventoried có thể bỏ sót local account |
| Thời gian từ authoritative event tới target revoke | Propagation có kịp không? | Average có thể che outlier critical |
| Số privileged grants không có approval | Có sai lệch quyền nhạy cảm? | Cần xác nhận đường approval và exception hợp lệ |
| % mover events có removal quyền cũ đã xác minh | Có tích lũy đặc quyền? | Có event processed không bảo đảm effective permission đổi |
| % identity-recovery events được review khi rủi ro cao | Recovery có bị lạm dụng? | Nhiều review không chứng minh proofing hiệu quả |
| % service accounts có owner, scope và review | Workload identity governance | Chủ thể không có owner có thể nằm ngoài danh sách |
| Số orphan/duplicate accounts | Rủi ro mapping và tồn đọng | Một account trùng có thể hợp lệ, cần ngữ cảnh |
| % downstream targets có acknowledgment đáng tin | Độ phủ orchestration | Ack chỉ là xử lý event, không tự chứng minh quyền đã mất |
| Số evidence gaps và finding quá hạn | Độ bất định chưa xử lý | “0 finding” có thể do không kiểm tra |
| Tỷ lệ retest đạt sau remediation | Chất lượng đóng lỗi vòng đời | Test không đúng production có thể làm số liệu đẹp giả |

Lãnh đạo cần nhìn **rủi ro trọng yếu, xu hướng, vùng không quan sát được, quyền quá hạn và quyết định cần thẩm quyền**, thay vì một biểu đồ “100% accounts processed” không nêu scope và phương pháp.

## 25. Vai trò và trách nhiệm (RACI)

Một chương trình vòng đời danh tính liên quan nhiều nhóm:

| Vai trò | Trách nhiệm |
|---|---|
| **Business/academic owner** | Định nghĩa tư cách học viên/giảng viên, quy tắc phân công và mốc hiệu lực |
| **HR/vendor management** | Nguồn authoritative về nhân sự/đối tác theo phạm vi |
| **Identity/IAM team** | Danh tính, IdP, policy, credentials, provisioning, revocation và inventory |
| **Application owner/Backend** | Account mapping, authorization nghiệp vụ, session, API/worker behavior |
| **Platform/Cloud/DevOps** | Workload identity, cloud access, secrets, CI/CD và SaaS integrations |
| **Security Assurance/GRC/CISO** | Khung yêu cầu, threat/risk review, chuẩn evidence, đánh giá control, báo cáo |
| **SOC/Incident Response** | Phát hiện chiếm account, khai thác, theo dõi, containment và điều tra |
| **Legal/Privacy** | Nghĩa vụ dữ liệu danh tính, retention, xử lý quyền và thông báo khi áp dụng |
| **Risk owner** | Quyết định phương án xử lý/residual risk theo quyền hạn |
| **Internal audit/assessor** | Kiểm tra độc lập theo scope, phương pháp và thẩm quyền được giao |

RACI minh họa:

| Hoạt động | Source/business owner | IAM | App/Platform | Security Assurance | Risk owner |
|---|---|---|---|---|---|
| Xác định tư cách và mốc hiệu lực | A/R | C | C | C | I |
| Thiết kế lifecycle control | C | A/R theo phân quyền | R cho thành phần liên quan | C | I |
| Triển khai đồng bộ, thu hồi và test | C | A/R cho IAM | A/R cho hệ thống của mình | C | I |
| Thu thập evidence, đối chiếu population | C | R | R | A hoặc reviewer theo cơ cấu | I |
| Đánh giá độc lập của chương trình | C | C | C | A/R hoặc phối hợp assessor | I |
| Quyết định residual risk | C | C | C | C/khuyến nghị | A/R |
| Khắc phục lifecycle finding | C | R | R | C/retest | I |

R = thực hiện, A = chịu trách nhiệm cuối cùng, C = tham vấn, I = được thông báo. Bảng chỉ là **mẫu phân công**, không nhất thiết có duy nhất một team IAM chịu mọi thành phần. Khi nhiều dòng có vai trò A/R tùy phạm vi, tổ chức phải quy định **accountable owner cụ thể cho từng activity và target system**.

## 26. Những sai lầm thường gặp

**“Identity lifecycle chỉ là tạo và xóa user.”** Chưa đủ. Nó gồm proofing, linking, credential, session, thay đổi vai trò, recovery, suspension, offboarding và retention.

**“Xác minh email nghĩa là đã xác minh danh tính ngoài đời thực.”** Không. Email verification thường chứng minh quyền kiểm soát kênh trong điều kiện nhất định.

**“Tài khoản có MFA thì identity assurance hoàn chỉnh.”** MFA là một phần authentication assurance; enrollment, recovery, liên kết account và trạng thái danh tính vẫn có thể bị sai.

**“Disable ở IdP nghĩa là mọi quyền đã mất.”** Không chắc. Session, local account, cloud token, SaaS grant, workload và job cần được xem theo phạm vi.

**“Role mới đã cấp, quyền cũ không còn quan trọng.”** Quyền cũ có thể tích lũy và dẫn tới vượt quyền.

**“Tên/email đủ để gắn mọi tài khoản.”** Không đáng tin khi có trùng tên, email đổi/tái sử dụng hoặc ghép account từ nhiều IdP. Cần stable subject mapping và policy liên kết.

**“Recovery chỉ cần người dùng trả lời câu hỏi hoặc có email.”** Cơ chế phục hồi phải đạt mức bảo đảm tương xứng nguy cơ và tránh trở thành đường chiếm account.

**“Tài khoản service không cần quản lý lifecycle.”** Non-human identities có owner, scope, credential, rotation, monitoring, decommission và rủi ro riêng.

**“Chỉ cần event processed = success.”** Thành công tại orchestration chưa chứng minh mọi target đã xử lý hoặc không còn effective access.

**“Một screenshot account disabled là bằng chứng đủ cho cả quý.”** Không bao phủ population, kỳ, session, quyền và các đích liên quan.

**“Trạng thái tài khoản đã xóa nghĩa phải xóa hết dữ liệu nghiệp vụ.”** Account deprovisioning và data retention cần xử lý khác nhau theo mục đích và nghĩa vụ.

**“Một test authn pass chứng minh người đó được phép xem dữ liệu.”** Identity binding, AuthN và AuthZ là các chiều khác nhau; phân quyền theo object/tenant vẫn phải kiểm tra.

**“Thừa nhận residual risk nghĩa control failure biến thành Pass.”** Acceptance không sửa sự thật kỹ thuật hoặc miễn nghĩa vụ bắt buộc.

**“Chỉ review vào mùa audit.”** Identity và quyền đổi hàng ngày; cần trigger và reconciliation theo risk.

## 27. Bài tập thực hành

### Bài tập A — Thiết kế state machine

Một nền tảng học có account learner và teacher. Learner có thể chuyển trường; teacher có thể chuyển lớp, bị tạm khóa và khôi phục sau khi xác minh.

Hãy:

1. Vẽ state machine cho vòng đời identity.
2. Tách trạng thái danh tính khỏi role/entitlement.
3. Nêu authoritative source cho tư cách, lớp và email.
4. Viết security invariant cho Requested → Active, Active → Suspended và Suspended → Active.
5. Đặt ít nhất năm trường hợp chuyển trạng thái không hợp lệ.
6. Đề xuất test/evidence về duplicate account và stale event.

**Gợi ý:** Không nên để một link email hợp lệ tự cấp TEACHER role. Không dùng một boolean active làm nguồn duy nhất của mọi quyết định về quyền.

### Bài tập B — Identity proofing khác authentication

Một ứng dụng thông báo “đã xác minh danh tính học viên” vì học viên nhận OTP qua email. Sau đó người dùng tải giấy chứng nhận mang tên thật.

Hãy đánh giá:

- Email verification đã chứng minh được gì và chưa chứng minh gì?
- Rủi ro nếu email được chia sẻ, tái sử dụng hoặc tài khoản được tạo hộ?
- Khi phát hành chứng nhận, có cần thêm nguồn/tư cách học vụ được xác minh không?
- Phương thức authentication có giúp đảm bảo nguồn dữ liệu học vụ đã đúng không?
- Những evidence nào cần cho claim của dịch vụ chứng nhận?

**Gợi ý:** Kiểm soát một email không tự xác nhận tên hoặc tư cách. Cần chọn yêu cầu proofing theo mục đích và rủi ro, không tự đặt mức xác minh cao cho mọi hoạt động.

### Bài tập C — Deprovision end-to-end

Một nhân viên vận hành nghỉ việc lúc 17:00 theo nguồn HR. IdP báo disabled lúc 17:01, nhưng còn:

- Cloud access key.
- Một SaaS account có đăng nhập riêng.
- Refresh token ứng dụng.
- Scheduled job do nhân viên tạo.
- Shared report link.
- Một service account do nhân viên quản lý.

Hãy lập:

1. Inventory tất cả đường tiếp tục truy cập.
2. Các control owners và authoritative event.
3. Thứ tự hành động, biện pháp giới hạn tác động trong lúc đồng bộ.
4. Evidence cho từng target và negative test.
5. Cách quản lý sự kiện duplicate/out-of-order và retry fail.
6. Tiêu chí kết luận Pass, Fail, Insufficient evidence.
7. Khác biệt giữa thu hồi quyền và giữ audit/business records.

**Gợi ý:** IdP disabled là một phần evidence, chưa có nghĩa tất cả credential/rights đã hết hiệu lực.

### Bài tập D — Account recovery có nguy cơ takeover

Một người gọi support nói mất điện thoại và muốn gỡ MFA. Người này biết email, tên hiển thị và tên lớp.

Hãy phân tích:

- Những thông tin nào có thể là công khai/dễ biết, vì sao chưa đủ?
- Policy recovery phù hợp risk tier nên bảo vệ điều gì?
- Khi nào cần step-up, approval hoặc kiểm tra bổ sung?
- Cần xử lý session cũ, authenticator cũ và thông báo như thế nào?
- Negative tests chống gỡ MFA trái thẩm quyền?
- Audit log nên lưu gì và tuyệt đối tránh lưu gì?

**Gợi ý:** Recovery cần đủ căn cứ về quyền kiểm soát account; không ghi recovery secret vào log hoặc yêu cầu người dùng chia sẻ token qua kênh không bảo vệ.

### Bài tập E — Review service identities

Hệ thống Java có 35 service accounts, trong đó 8 không còn owner rõ, 4 token chưa được sử dụng theo log trong thời gian dài và 2 account có quyền đọc toàn bộ dữ liệu.

Hãy đề xuất:

1. Cách xác minh inventory và xác định purpose/owner.
2. Phân tích quyền thực tế, trust policy và dữ liệu có thể truy cập.
3. Quy trình đóng account mồ côi hoặc chuyển owner.
4. Test revoke/rotate và rollback an toàn cho production.
5. Bằng chứng cần lưu và lịch review theo rủi ro.
6. Vì sao không thể tự xóa mọi token ít dùng dựa trên một metric?
7. Cách ưu tiên account có ảnh hưởng lớn trước.

### Bài tập F — Kết luận assurance có giới hạn

Assessor có dữ liệu sau: 100 leaver events trong kỳ; 99 IdP accounts báo disabled; một record không match subject; chỉ 80 accounts có target acknowledgment từ SaaS; không có log về local admin; 10 negative tests với actor mẫu đều bị từ chối.

Viết một báo cáo ngắn gồm:

- Claim ban đầu và population.
- Bằng chứng đã hỗ trợ những subclaim nào?
- Những khoảng trống nào là **control failure đã chứng minh**, những gì chỉ là **insufficient evidence**?
- Cần làm gì với record không match và 20 acknowledgment chưa có?
- Có được kết luận “100% leavers không còn quyền” không?
- Owner, thời hạn, remediation/retest và residual risk đề nghị ra sao?

**Định hướng:** 99/100 IdP disabled không đủ để kết luận toàn bộ access lifecycle đã đạt; record không match phải được điều tra, thiếu SaaS acknowledgment/log cần đối chiếu và test bổ sung. Báo cáo phải tách trạng thái biết chắc và phần chưa biết.

## 28. Checklist kiểm tra chất lượng identity lifecycle assurance

Checklist là công cụ rà soát; **đánh dấu đủ ô không tự tạo ra bằng chứng control đạt**:

- [ ] Đã định nghĩa scope: workforce, learner, teacher, contractor, vendor và workload identities liên quan.
- [ ] Có source authority cho từng loại thuộc tính và sự kiện.
- [ ] Có stable subject ID và quy trình account linking/duplicate resolution.
- [ ] Có identity proofing/verification theo rủi ro và mục đích, không suy diễn từ email.
- [ ] Credential/authenticator enrollment, change, recovery và revocation có requirements.
- [ ] Phân biệt identity state với authorization/entitlements.
- [ ] Trạng thái pending, active, suspended, terminated, retained/deleted có transition rules.
- [ ] Lifecycle events có nguồn, ID, effective time và cơ chế idempotency/ordering.
- [ ] Có JML/role change control và review effective permissions.
- [ ] Suspension và termination có kiểm tra session/token/caches và đường bypass.
- [ ] Có reconciliation mọi target quan trọng và xử lý partial failure.
- [ ] Recovery và account linking được test với actor giả mạo/không đủ quyền.
- [ ] Có privileged/break-glass governance và independent review theo rủi ro.
- [ ] Có non-human identity inventory, owner, purpose, scope, credential lifecycle.
- [ ] Có vendor/SaaS access inventory và quy trình offboarding.
- [ ] Có retention và deletion quy định rõ, bảo vệ dữ liệu danh tính.
- [ ] Có test positive/negative, duplicate/out-of-order, recovery và downstream side effects.
- [ ] Có evidence metadata về source, population, period, method, integrity và limitations.
- [ ] Có assessor/reviewer và phân vai tạo evidence, đánh giá, phê duyệt risk.
- [ ] Assessment phân biệt Pass, Fail, Insufficient evidence, N/A và exception.
- [ ] Finding có owner, impact, remediation và retest đúng bản/môi trường.
- [ ] Có trigger review sau thay IdP, policy, recovery flow, SaaS hoặc incident.
- [ ] Các kết luận cho lãnh đạo nêu scope, kỳ, điểm chưa chứng minh và residual risk.

## 29. Ghi nhớ

- **Identity lifecycle** quản lý toàn bộ quá trình từ tạo, kiểm chứng, liên kết, sử dụng, đổi trạng thái đến thu hồi và xử lý dữ liệu danh tính.
- **Identity proofing, authentication, federation và authorization không giống nhau**; mỗi chiều cần yêu cầu và bằng chứng phù hợp.
- **Nguồn có thẩm quyền và stable subject mapping** quyết định sự kiện/thuộc tính được áp vào đúng người hoặc workload.
- Đừng chỉ kiểm tra **cấp quyền mới**: mover phải gỡ quyền cũ, leaver phải thu hồi đường truy cập thực tế, recovery không được trở thành đường chiếm account.
- **IdP disabled không tự chứng minh session, token, cloud, SaaS, worker hoặc file shares đã được thu hồi**.
- Workload, vendor và break-glass identities có vòng đời, owner và risk riêng, không dùng checklist dành cho người dùng mà bỏ qua đặc thù.
- Hệ thống phân tán phải kiểm soát **duplicate/out-of-order events, partial failures, reconciliation và effective access**.
- Assurance cần phân biệt **design, implementation và operating effectiveness**; evidence phải có nguồn, phạm vi, kỳ, độ tin cậy và giới hạn.
- Khi kiểm thử fail hoặc thiếu evidence, phải ghi **finding/evidence gap, remediation, retest và residual risk decision** trung thực, không dùng chữ ký acceptance để đổi fail thành pass.
- Một chương trình trưởng thành tạo vòng lặp **risk → lifecycle requirement → identity control → test/evidence → assessment → response → monitoring/reassessment** trong phát triển và vận hành.

