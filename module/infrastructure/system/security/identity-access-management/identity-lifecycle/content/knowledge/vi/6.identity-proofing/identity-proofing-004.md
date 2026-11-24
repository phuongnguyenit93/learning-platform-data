# Mức độ assurance trong Identity Proofing

## 1. Assurance trả lời câu hỏi nào trong IAM?

Trong **Identity and Access Management (IAM)**, một hệ thống có thể biết rằng tài khoản đã đăng nhập thành công nhưng vẫn chưa biết chắc **người đang sử dụng tài khoản là ai**. Ví dụ, một người tự khai tên và email khi đăng ký; sau đó đăng nhập bằng mật khẩu đúng. Hệ thống đã xác thực người nắm mật khẩu, nhưng chưa chắc người đó đúng là người mang danh tính đã khai.

**Identity proofing** là quá trình thiết lập và kiểm tra mối liên hệ giữa một chủ thể với danh tính được tuyên bố, dựa trên bằng chứng và phương pháp phù hợp. **Mức độ assurance** mô tả mức bảo đảm hoặc độ tin cậy mà quá trình và biện pháp kiểm soát cung cấp đối với một kết luận nhất định.

Trong thực tế, cần đặt ít nhất ba câu hỏi riêng:

1. **Danh tính đã được xác minh đến mức nào?** Người nhận quyền có đúng là người gắn với danh tính đó không?
2. **Phiên đăng nhập được xác thực mạnh đến mức nào?** Người đang thao tác có chứng minh được quyền kiểm soát các yếu tố xác thực được yêu cầu không?
3. **Thông tin xác thực liên kết đi qua các hệ thống có được bảo vệ đúng mức không?** Ứng dụng nhận danh tính từ IdP có thể tin thông điệp và quan hệ liên kết ở mức nào?

Ba câu hỏi này liên quan với nhau nhưng **không thể thay thế cho nhau**. Mức assurance không phải một điểm “uy tín cá nhân”, không bảo đảm danh tính không bao giờ bị đánh cắp, và không mặc nhiên cấp bất kỳ quyền nghiệp vụ nào.

Bài học thuộc chương **Identity proofing** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tập trung quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**. Mức assurance cung cấp cơ sở để tạo đúng người, liên kết tài khoản, quyết định khi nào phải xác minh lại, điều phối IdP/SSO/SCIM và giảm rủi ro cấp quyền nhầm hoặc giữ quyền tồn dư.

## 2. Phân biệt IAL, AAL và FAL

Bộ hướng dẫn danh tính số **NIST SP 800-63** sử dụng ba nhóm mức assurance với mục tiêu khác nhau. Các yêu cầu kỹ thuật chi tiết phải đối chiếu **ấn bản tiêu chuẩn và chính sách áp dụng thực tế**; bảng dưới tóm tắt ý nghĩa khái niệm:

| Nhóm | Tên đầy đủ | Câu hỏi mà nhóm này trả lời | Ví dụ về kiểm soát |
|---|---|---|---|
| **IAL** | Identity Assurance Level | Danh tính của người đăng ký đã được *proofing* đến mức nào? | Xác minh bằng chứng danh tính, đối chiếu người thật với bằng chứng, liên kết hồ sơ |
| **AAL** | Authenticator Assurance Level | Một phiên xác thực chứng minh quyền kiểm soát authenticator mạnh đến mức nào? | Đa yếu tố, khả năng chống phishing, ràng buộc khóa mật mã |
| **FAL** | Federation Assurance Level | Thông tin xác thực liên kết giữa IdP và bên nhận được bảo vệ đến mức nào? | Bảo vệ assertion, ràng buộc các bên, cơ chế chống giả mạo/phát lại |

**IAL** là trọng tâm của bài học này. **AAL** nằm ở khâu xác thực và phiên; **FAL** nằm ở khâu liên kết danh tính giữa các hệ thống. Chúng có thể được yêu cầu đồng thời, nhưng **IAL cao không tự suy ra AAL cao** và ngược lại.

Ví dụ: một nhân viên đã qua quy trình đối chiếu giấy tờ và xác minh trực tiếp, nhưng đang dùng một mật khẩu yếu làm phương thức đăng nhập duy nhất. Quy trình proofing có thể đạt mục tiêu nhận diện người ở mức đáng tin cậy, trong khi mức bảo đảm của phiên đăng nhập vẫn thấp. Ngược lại, người sử dụng khóa bảo mật chống phishing có thể đăng nhập rất an toàn vào một tài khoản chỉ gắn với tên tự khai; AAL mạnh không biến tên tự khai thành danh tính pháp lý đã được kiểm chứng.

~~~mermaid
flowchart LR
    P[Proofing danh tính] --> I[IAL: tin cậy về danh tính]
    A[Authentication] --> L[AAL: tin cậy về phiên đăng nhập]
    F[Federation IdP đến ứng dụng] --> K[FAL: tin cậy về xác thực liên kết]
    I --> D[Đánh giá truy cập]
    L --> D
    K --> D
    R[RBAC / ABAC / phê duyệt] --> D
    D --> X[Cho phép hoặc từ chối hành động]
~~~

**Lưu ý:** Nếu hệ thống không dùng federation, FAL có thể không phải một điều kiện cần kiểm tra cho chính luồng đó. Nếu chủ thể là thiết bị hoặc workload, cách xác minh danh tính máy thường có mô hình riêng; không nên gắn nhãn IAL của con người một cách cơ học.

## 3. Các mức Identity Assurance Level

NIST mô tả các mức **IAL1, IAL2, IAL3** nhằm phân biệt mức bảo đảm của việc xác lập danh tính. Tóm lược dưới đây mang tính định hướng; nó **không thay thế bảng yêu cầu bắt buộc** của phiên bản NIST SP 800-63A mà tổ chức áp dụng.

| Mức | Ý nghĩa khái quát | Đặc điểm proofing | Bối cảnh minh họa |
|---|---|---|---|
| **IAL1** | Không đòi hỏi xác minh danh tính theo mức proofing cao hơn; thuộc tính có thể do người dùng tự khai | Có thể tạo danh tính số với thông tin tự khai và một số kiểm tra kỹ thuật; không được ngầm xem các thuộc tính đó là đã kiểm chứng | Tài khoản diễn đàn hoặc chức năng ít rủi ro không đòi xác định danh tính thật |
| **IAL2** | Có mức tin cậy cao hơn rằng danh tính được tuyên bố tương ứng với người đăng ký | Yêu cầu kiểm tra bằng chứng và xác minh mối liên hệ người–danh tính theo các phương thức, cường độ và kiểm soát được quy định | Quy trình định danh cho một số dịch vụ nhân sự hoặc ứng dụng xử lý dữ liệu quan trọng |
| **IAL3** | Mức assurance cao hơn với quy trình proofing và bằng chứng/giám sát chặt chẽ hơn | Các yêu cầu cao hơn về xác minh và kiểm soát gian lận; cách triển khai hợp lệ phụ thuộc ấn bản chuẩn và hồ sơ chính sách | Tình huống có tác động rất lớn nếu gán nhầm danh tính hoặc chiếm đoạt hồ sơ |

### 3.1. IAL1: giới hạn của thông tin tự khai

Tại mức này, một hồ sơ có thể mang tên, email, số điện thoại hoặc vai trò do người đăng ký cung cấp mà chưa có bằng chứng đủ để xác nhận danh tính ngoài đời. Điều đó **không có nghĩa tài khoản vô dụng hoặc không thể xác thực mạnh**; chỉ có nghĩa việc xác thực thành công không được dùng để khẳng định mọi thuộc tính tự khai đều đúng.

Ví dụ: tài khoản email được xác nhận bằng đường dẫn gửi tới hộp thư chứng minh người đăng ký có quyền truy cập hộp thư **tại thời điểm kiểm tra**, không tự chứng minh họ là người có tên trên hồ sơ nhân sự.

### 3.2. IAL2: kiểm tra bằng chứng và liên kết với người đăng ký

Một thiết kế nhắm đến IAL2 phải đáp ứng đầy đủ yêu cầu của tiêu chuẩn được chọn, bao gồm các bước liên quan đến **danh tính được tuyên bố, độ tin cậy của bằng chứng, đối chiếu người đăng ký với danh tính và xử lý trường hợp không khớp**.

Có thể thực hiện qua các kênh proofing hợp lệ theo chính sách và tiêu chuẩn. Không nên tuyên bố “chụp giấy tờ + nhận diện khuôn mặt = IAL2” nếu chưa kiểm tra nguồn bằng chứng, độ tin cậy, quy tắc chống giả mạo, phương pháp xác minh, kiểm soát vận hành và toàn bộ các yêu cầu còn lại.

### 3.3. IAL3: assurance cao đòi hỏi toàn bộ quy trình chặt chẽ hơn

IAL3 đòi hỏi tuân thủ bộ yêu cầu cao hơn được quy định cho mức này. **Một bước xác minh bổ sung đơn lẻ không tự nâng IAL2 lên IAL3.** Tổ chức phải xem xét toàn bộ chuỗi proofing, loại bằng chứng, cách kiểm tra, giám sát/kiểm soát người thực hiện, khả năng chống gian lận, lưu vết và các điều kiện tương ứng của phiên bản tiêu chuẩn.

Nếu một quy trình tự xây dựng đạt “mức cao” theo thang nội bộ, không nên gắn nhãn **IAL3** của NIST cho đến khi đánh giá được sự phù hợp với yêu cầu tiêu chuẩn. Tên nhãn assurance là **kết quả tuân thủ một hồ sơ kiểm soát**, không phải đánh giá cảm tính của nhân viên xét duyệt.

## 4. Các hoạt động làm nên assurance của Identity Proofing

Một quy trình proofing đáng tin cậy cần xem xét nhiều bước. Tùy chuẩn và phương thức, tên gọi hoặc yêu cầu chi tiết có thể khác nhau, nhưng tư duy kiểm soát chung gồm:

1. **Identity resolution – phân giải danh tính:** thu thập thông tin cần thiết để phân biệt người đăng ký với người khác và phát hiện hồ sơ trùng/lẫn.
2. **Evidence collection – thu thập bằng chứng:** tiếp nhận dữ liệu hoặc chứng từ chứng minh danh tính từ nguồn hợp lệ, ở mức tối thiểu cần thiết.
3. **Evidence validation – kiểm tra bằng chứng:** đánh giá bằng chứng có đáng tin cậy, hợp lệ, đúng định dạng, còn giá trị và không bị sửa đổi/giả mạo theo yêu cầu hay không.
4. **Identity verification – xác minh quan hệ với người đăng ký:** kiểm tra người trước mặt hoặc người đang tương tác đúng là người tương ứng với danh tính trong bằng chứng.
5. **Binding – liên kết danh tính được proofing:** gắn kết quả xác minh với bản ghi IAM và các cơ chế để người đó tiếp tục thiết lập/sử dụng tài khoản, tránh trao nhầm kết quả cho người khác.
6. **Decision and audit – quyết định và lưu vết:** ghi mức assurance được công nhận, chính sách, người/hệ thống thực hiện, kết quả, lý do từ chối và bằng chứng kiểm toán phù hợp.

~~~mermaid
flowchart TD
    START[Người đăng ký / nguồn HRIS] --> RESOLVE[Resolution: phân giải và chống trùng]
    RESOLVE --> EVIDENCE[Thu thập bằng chứng cần thiết]
    EVIDENCE --> VALIDATE{Bằng chứng hợp lệ?}
    VALIDATE -->|Không| RETRY[Bổ sung / từ chối / chuyển xét duyệt]
    VALIDATE -->|Có| VERIFY{Người đăng ký khớp danh tính?}
    VERIFY -->|Không hoặc nghi vấn| RETRY
    VERIFY -->|Có| POLICY{Đáp ứng đầy đủ mức assurance yêu cầu?}
    POLICY -->|Chưa| RETRY
    POLICY -->|Đạt| BIND[Liên kết kết quả với identity record]
    BIND --> RECORD[Ghi quyết định, thời điểm, nguồn và trạng thái]
    RECORD --> IAM[Provisioning và chính sách IAM]
~~~

### Tách hai khái niệm dễ nhầm

**Validation** trả lời “bằng chứng này có hợp lệ và đáng tin không?”. **Verification** trả lời “người đăng ký có đúng là người mà bằng chứng ấy mô tả không?”. Một giấy tờ thật vẫn có thể bị người khác sử dụng. Ngược lại, ảnh selfie trông giống ảnh đã khai không chứng minh được giấy tờ đính kèm là thật.

### Không suy ra assurance chỉ từ một dấu hiệu

Các suy luận sau đều không đủ cơ sở:

- “Đã nhận OTP qua số điện thoại nên đã xác minh danh tính pháp lý.”
- “Đã bật MFA nên danh tính đã đạt IAL2.”
- “Đã đăng nhập qua SSO doanh nghiệp nên mọi thuộc tính cá nhân đều được kiểm chứng.”
- “Có một bản quét giấy tờ tùy thân nên chắc chắn đạt IAL3.”
- “HRIS có tên nhân viên nên không cần biết nguồn hoặc quá trình kiểm tra ban đầu.”

Kết luận assurance phải dựa trên **toàn bộ quy trình và bộ kiểm soát**, phù hợp với nguồn danh tính và rủi ro nghiệp vụ.

## 5. Cách chọn mức assurance dựa trên rủi ro

Không phải mọi ứng dụng đều cần cùng mức proofing. Mức yêu cầu nên được xác định từ **tác động nếu một danh tính bị gán nhầm, một tài khoản được cấp cho sai người hoặc một giao dịch được thực hiện bởi người không có quan hệ danh tính được tuyên bố**.

Các yếu tố đánh giá thường gồm:

- **Tổn thất tài chính:** sai danh tính có thể gây gian lận thanh toán, tạo tài khoản nhận tiền hoặc chiếm đoạt tài sản không?
- **Dữ liệu cá nhân và bí mật:** sai người có thể đọc hồ sơ nhân sự, dữ liệu sức khỏe, thông tin khách hàng hoặc bí mật kinh doanh không?
- **An toàn và vận hành:** danh tính bị giả mạo có thể điều khiển thiết bị, thay đổi hạ tầng, phá hoại môi trường sản xuất không?
- **Pháp lý/hợp đồng:** có yêu cầu biết khách hàng/nhân viên, kiểm tra tư cách hoặc lưu bằng chứng theo luật, hợp đồng và ngành nghề không?
- **Khả năng khắc phục:** hậu quả sai danh tính có khó đảo ngược, phát hiện muộn hoặc ảnh hưởng nhiều hệ thống không?
- **Khả năng bị lạm dụng:** kênh đăng ký từ xa, nhận ưu đãi giá trị cao, thuê ngoài hoặc có các dấu hiệu gian lận hàng loạt không?

### Ma trận quyết định minh họa

| Tình huống | Phân tích ban đầu | Hướng lựa chọn |
|---|---|---|
| Đọc tài liệu marketing công khai | Không cần ràng buộc người thật với danh tính pháp lý | Có thể không cần proofing danh tính |
| Đăng ký tài khoản cho tiện ích cá nhân ít nhạy cảm | Sai tên chưa gây tác động lớn | Có thể phù hợp với cách tiếp cận tương đương IAL1 |
| Nhận quyền truy cập hồ sơ nhân sự hoặc xử lý yêu cầu thanh toán | Cấp sai người dẫn tới lộ dữ liệu hoặc tổn thất | Cân nhắc yêu cầu proofing cao hơn, có thể nhắm IAL2 khi áp dụng NIST |
| Tác vụ có tác động đặc biệt lớn hoặc nghĩa vụ pháp lý chặt chẽ | Rủi ro gán nhầm danh tính rất cao | Đánh giá liệu mức assurance cao nhất theo bộ chuẩn/chính sách áp dụng có cần thiết và khả thi |

Bảng chỉ thể hiện **cách đặt vấn đề**, không phải quy tắc pháp lý hoặc ánh xạ IAL bắt buộc. Việc quyết định cuối phải dùng quy trình đánh giá rủi ro, nghĩa vụ áp dụng và tài liệu yêu cầu của **ấn bản tiêu chuẩn thực tế**.

Cũng không nên dùng proofing mạnh để bù đắp cho kiểm soát phiên yếu. Một chức năng thanh toán giá trị lớn có thể đòi **cả assurance danh tính, xác thực chống phishing, phê duyệt giao dịch và phân tách nhiệm vụ**.

## 6. Các mức AAL và FAL phối hợp với IAL ra sao?

### 6.1. AAL: xác thực người đang thao tác

Theo mô hình NIST, **AAL1/AAL2/AAL3** mô tả các mức bảo đảm tăng dần của quá trình xác thực. Ở mức khái quát:

- **AAL1** có thể dựa trên một yếu tố xác thực đáp ứng các yêu cầu tương ứng.
- **AAL2** đòi hỏi xác thực đa yếu tố theo yêu cầu kỹ thuật của tiêu chuẩn.
- **AAL3** đặt yêu cầu nghiêm ngặt hơn, bao gồm biện pháp mật mã và khả năng chống các mối đe dọa cụ thể theo tiêu chuẩn áp dụng.

Không nên phân loại một hệ thống đạt AAL cụ thể chỉ bằng số “bước đăng nhập”. Ví dụ, việc nhập mật khẩu hai lần không tạo thành hai yếu tố; một OTP không tự bảo đảm chống phishing. Phương thức và khả năng chống tấn công phải được đánh giá theo bộ yêu cầu kỹ thuật.

### 6.2. FAL: tin cậy khi sử dụng IdP và SSO

**FAL1/FAL2/FAL3** liên quan đến mức bảo vệ xác thực liên kết giữa **Identity Provider (IdP)** và **Relying Party (RP)**. Chẳng hạn, một ứng dụng nhận assertion/token sau khi nhân viên đăng nhập SSO cần bảo đảm thông điệp được phát hành bởi bên tin cậy, được gửi cho đúng đối tượng và tuân thủ các yêu cầu chống sửa đổi, giả mạo, phát lại hay chiếm dụng phù hợp.

Một hệ thống **SAML hoặc OpenID Connect (OIDC)** không tự động đạt một FAL chỉ vì dùng giao thức chuẩn. Cần kiểm tra cấu hình, cơ chế bảo vệ, ràng buộc và nghĩa vụ tương ứng.

### 6.3. Kết hợp ba lớp trong một quyết định

Ví dụ một tác vụ cập nhật thông tin nhận lương có thể áp dụng chính sách tổ chức như sau:

| Lớp | Yêu cầu minh họa | Kiểm tra |
|---|---|---|
| IAL | Danh tính nhân sự đã được proofing theo mức được phê duyệt | Hồ sơ proofing và quan hệ với HRIS |
| AAL | Phiên hiện tại đáp ứng xác thực đa yếu tố phù hợp | Bằng chứng xác thực của IdP, thời điểm xác thực |
| FAL | Nếu ứng dụng nhận danh tính qua SSO, federation đáp ứng yêu cầu tin cậy | Cấu hình IdP/RP và assertion được bảo vệ |
| Authorization | Người đó được phép sửa **chính thông tin của mình** | RBAC/ABAC, quyền sở hữu bản ghi, chính sách |
| Transaction control | Thay đổi nhạy cảm có thể cần xác nhận/phê duyệt bổ sung | Step-up, cảnh báo, xác minh giao dịch |

Các lớp được kiểm tra độc lập. **IAL không thay cho authorization**; nếu người dùng đã được xác minh danh tính nhưng không có quyền duyệt lương, hệ thống vẫn phải từ chối thao tác duyệt.

## 7. Assurance trong vòng đời Joiner–Mover–Leaver

### 7.1. Joiner: proofing trước khi gán quyền

Một nhân viên mới có thể được HRIS tạo hồ sơ trước ngày vào làm. Quy trình IAM nên xác định **nguồn xác minh danh tính**, kết quả proofing, bản ghi nhân sự ổn định và điều kiện kích hoạt tài khoản.

Chuỗi điển hình:

1. HR hoặc nguồn có thẩm quyền khởi tạo hồ sơ người gia nhập với mã định danh bền vững.
2. Đối chiếu để phát hiện trùng với người từng làm việc, người trùng tên hoặc hồ sơ đã tồn tại.
3. Thực hiện proofing cần thiết theo loại quan hệ và rủi ro; nếu HR đã proofing trước đó, IAM cần biết **mức, nguồn, độ tin cậy, phạm vi và điều kiện chấp nhận** thay vì tự động giả định.
4. Gắn kết quả xác minh với identity record, tổ chức phát hành tài khoản IdP theo đúng điều kiện.
5. Áp chính sách **RBAC/ABAC**, phê duyệt ngoại lệ và điều kiện MFA; đồng bộ tài khoản qua **SCIM/API** hoặc connector phù hợp.
6. Kiểm tra quyền thực tế tại hệ thống đích và ghi log, tránh nhầm danh tính hoặc cấp nhầm entitlement.

**Tình huống dễ sai:** hai người cùng tên “Nguyễn Văn An” gia nhập trong cùng tuần. Nếu dùng tên hoặc email được tạo theo mẫu làm khóa nhận diện duy nhất, nhân sự mới có thể bị liên kết nhầm với tài khoản từng tồn tại và nhận quyền cũ. Bản ghi phải được liên kết bằng định danh và quy trình xác minh đáng tin cậy, đồng thời xử lý tái gia nhập một cách có chủ đích.

### 7.2. Mover: đánh giá lại rủi ro khi thay đổi vai trò

Mover không tự động có nghĩa phải proofing lại toàn bộ. Việc đổi bộ phận thường trước hết làm thay đổi **quyền nghiệp vụ**; IAM cần thu hồi quyền cũ và cấp quyền mới dựa trên trạng thái nhân sự hiện hành.

Tuy nhiên, cần cân nhắc **re-proofing hoặc xác minh tăng cường** khi có một trong các tình huống:

- Hồ sơ gốc được tạo từ kênh assurance thấp nhưng vai trò mới yêu cầu xác minh mạnh hơn.
- Tài khoản chuyển sang quyền truy cập nhạy cảm, quyền quản trị hoặc xử lý giao dịch giá trị cao.
- Có mâu thuẫn danh tính, nghi ngờ giả mạo hoặc thay đổi thuộc tính định danh cốt lõi mà chưa xác minh được.
- Tài khoản trước đó do bên thứ ba bảo trợ, giờ được chuyển thành nhân viên hoặc vai trò có mức tin cậy khác.
- Chính sách tổ chức yêu cầu xác minh lại sau sự kiện cụ thể hoặc khoảng thời gian nhất định.

**Không nên hiểu IAL như vai trò.** Vai trò mới có thể yêu cầu IAL cao hơn, nhưng IAL chỉ có thể được nâng sau khi **đã hoàn thành toàn bộ quy trình proofing tương ứng**; không tự tăng trường metadata từ IAL1 lên IAL2 khi người dùng được thăng chức.

### 7.3. Leaver: assurance không làm chậm thu hồi

Khi nhận sự kiện Leaver hợp lệ từ nguồn có thẩm quyền, IAM cần ưu tiên **vô hiệu hóa đăng nhập, thu hồi phiên/token/quyền và đối soát hệ thống đích** theo mức độ rủi ro. Không nên trì hoãn chặn truy cập chỉ vì người nghỉ không sẵn sàng tham gia proofing lại.

Sau khi chấm dứt quan hệ, bản ghi proofing có thể phải được giữ trong thời hạn kiểm toán/pháp lý nhưng **không còn là cơ sở cấp quyền hiện hành**. Khi người đó tái gia nhập, tổ chức cần quyết định theo chính sách có thể tái sử dụng phần bằng chứng nào, phải xác minh lại những gì và **không khôi phục tự động các quyền cũ**.

### 7.4. Đối tượng phi con người

**Service account, device account, workload identity và bot** không được định danh như con người qua giấy tờ tùy thân. Chúng cần assurance phù hợp với loại chủ thể: nguồn cấp phát đáng tin cậy, định danh khối lượng công việc/thiết bị, attestation khi hỗ trợ, chứng chỉ hoặc khóa, quyền sở hữu rõ ràng, luân chuyển credential và vòng đời thu hồi.

Không nên gắn nhãn “IAL2” cho máy chủ hoặc bot chỉ vì máy dùng chứng chỉ mạnh. **Mức bảo đảm danh tính máy** và **IAL proofing danh tính người** có đối tượng và bộ kiểm soát khác nhau.

## 8. Proofing tại nguồn và việc tin cậy kết quả giữa các hệ thống

IAM thường không phải nơi trực tiếp kiểm tra mọi giấy tờ. Một quy trình HR onboarding, đối tác định danh hoặc dịch vụ proofing có thể là **nguồn kết quả đáng tin cậy**. Nếu sử dụng kết quả từ hệ thống khác, tổ chức cần thiết kế quan hệ tin cậy:

| Câu hỏi | Vì sao quan trọng |
|---|---|
| Ai thực hiện proofing và chịu trách nhiệm về quyết định? | Tránh sử dụng kết quả từ bên không được chấp thuận |
| Theo chính sách và phiên bản nào? | Một nhãn “verified” không cho biết các kiểm soát thực sự đã áp dụng |
| Loại danh tính và bằng chứng nào được kiểm tra? | Proofing nhân viên, nhà thầu, khách hàng có yêu cầu khác nhau |
| Người nhận đã được liên kết với identity record nào? | Tránh nhận nhầm kết quả của người trùng tên, email hoặc bị tái sử dụng ID |
| Kết quả còn hiệu lực và có bị thu hồi/đính chính không? | Quyết định danh tính có thể thay đổi khi phát hiện gian lận |
| Dữ liệu nào được phép chia sẻ và lưu giữ? | Giới hạn sao chép giấy tờ, sinh trắc học, PII vượt nhu cầu |

**IdP** có thể chứa thuộc tính và nguồn gốc proofing, nhưng IdP chủ yếu chịu trách nhiệm xử lý danh tính và xác thực trong hệ sinh thái của nó. **SSO** truyền hoặc liên kết kết quả xác thực; **SCIM** đồng bộ người dùng/nhóm/thuộc tính trong phạm vi triển khai; **RBAC/ABAC** áp quyền truy cập. Không thành phần nào **tự chứng minh** mức proofing đã thực sự đạt chuẩn chỉ bởi việc tài khoản có tồn tại.

Ví dụ: SCIM tạo thành công người dùng với thuộc tính *verified=true* tại ứng dụng SaaS. Ứng dụng vẫn cần biết giá trị ấy do nguồn nào xác nhận, được ký hoặc bảo vệ thế nào, đã được ánh xạ đúng đối tượng hay chưa và có phù hợp chính sách tin cậy không. **Một trường boolean do nguồn không đáng tin cấp không phải chứng cứ assurance.**

## 9. Lưu trữ trạng thái assurance và bằng chứng

Kết quả proofing cần đủ **metadata để kiểm tra quyết định**, nhưng không nên nhân bản tài liệu gốc hoặc thông tin sinh trắc học sang mọi hệ thống.

Một bản ghi **minh họa nội bộ**, không phải schema chuẩn NIST hoặc SCIM:

~~~json
{
  "personId": "P-2046",
  "identityProofing": {
    "result": "VERIFIED",
    "assuranceProfile": "IAL2",
    "policyVersion": "proofing-policy-2026-03",
    "standardEdition": "organization-approved-edition",
    "verifiedAt": "2026-11-20T14:00:00+07:00",
    "verifiedBy": "approved-proofing-provider",
    "evidenceReference": "restricted-vault-ref-178",
    "decisionId": "proofing-decision-4021",
    "reviewDueAt": "2027-11-20T14:00:00+07:00"
  },
  "identityLifecycle": {
    "employmentState": "ACTIVE",
    "source": "HRIS",
    "sourceRecordId": "HR-2046"
  }
}
~~~

**Cách đọc bản ghi:**

- **assuranceProfile** phải có tiêu chí và bằng chứng đánh giá tương ứng; tên mức không đủ để tuyên bố tuân thủ.
- **policyVersion** cùng **standardEdition** xác định bộ quy tắc đã áp dụng. Trong triển khai thực tế, cần ghi giá trị ấn bản cụ thể đang có hiệu lực, thay cho chuỗi minh họa.
- **verifiedAt** là lúc hoàn thành proofing; **reviewDueAt** là thời hạn tái đánh giá theo chính sách nội bộ, **không phải thời hạn bắt buộc chung của mọi IAL**.
- **evidenceReference** là tham chiếu tới kho bảo vệ có phân quyền và chính sách lưu giữ; không nên chứa ảnh giấy tờ hoặc đặc trưng sinh trắc học trực tiếp trong log ứng dụng.
- **employmentState** phản ánh quan hệ hiện tại với tổ chức và phải được đánh giá riêng. Người có proofing hợp lệ nhưng đã Leaver **không còn quyền truy cập công việc**.

Không lưu mã định danh pháp lý, ảnh giấy tờ hoặc dữ liệu sinh trắc học nếu quy trình không cần; nếu bắt buộc, cần cơ sở xử lý hợp lệ, mã hóa, thời hạn lưu giữ, phân quyền và quy trình xóa/đính chính phù hợp.

## 10. Đánh giá assurance trong policy engine

Một điểm kiểm soát quyền có thể đọc kết quả proofing đã được tin cậy, sau đó kết hợp với trạng thái tài khoản, phiên xác thực và chính sách phân quyền.

~~~text
function canAccess(request, identity, session, resource):
    if identity.lifecycleState != ACTIVE:
        return DENY

    if identity.proofing.result != VERIFIED:
        return DENY_OR_RESTRICT

    if not acceptedProofingProfile(
        identity.proofing.profile,
        identity.proofing.policyVersion,
        resource.requiredIdentityAssurance
    ):
        return REQUIRE_PROOFING_OR_REVIEW

    if not validAuthenticationSession(
        session,
        resource.requiredAuthenticatorAssurance
    ):
        return REQUIRE_STEP_UP_AUTHENTICATION

    if request.isFederated and not federationPolicySatisfied(session, resource):
        return DENY

    if not authorizationPolicyAllows(
        identity.roles,
        identity.attributes,
        request.action,
        resource
    ):
        return DENY

    return ALLOW
~~~

Đây là **giả mã**, không phải mã có thể dùng trực tiếp để triển khai bảo mật. Hàm *acceptedProofingProfile* phải đối chiếu yêu cầu thật của tổ chức, kết quả/chứng cứ và ấn bản chuẩn tương ứng; không chỉ so sánh một số nguyên IAL. Các hệ thống có yêu cầu riêng cho trạng thái thuộc tính, thời điểm xác minh, rủi ro giao dịch, trạng thái federation và sự tươi mới của phiên.

**Quy tắc quan trọng:** không dùng *proofing failed* như một lý do cho phép fallback sang tài khoản có quyền cao. Nếu có ngoại lệ vì khả năng tiếp cận, mất giấy tờ hoặc sai lệch dữ liệu, cần một quy trình xử lý thay thế được phê duyệt, có phạm vi và bằng chứng rõ ràng.

## 11. Các mối đe dọa ảnh hưởng tới assurance

| Mối đe dọa | Ví dụ | Hướng kiểm soát |
|---|---|---|
| **Danh tính tổng hợp hoặc hồ sơ giả** | Trộn dữ liệu thật và giả để tạo người đăng ký không tồn tại | Kiểm tra tính hợp lệ và tính nhất quán của bằng chứng, đối chiếu nguồn tin cậy, phát hiện gian lận |
| **Dùng giấy tờ của người khác** | Người A dùng giấy tờ thật của B | Phân biệt validation của giấy tờ với verification người đăng ký |
| **Ảnh/video giả hoặc phát lại** | Gửi hình, video hoặc tín hiệu được thao túng vào quy trình từ xa | Kiểm soát chống giả mạo và phát lại phù hợp phương thức, người duyệt khi cần |
| **Chiếm quyền kênh đăng ký** | Thay email/số liên hệ trước khi liên kết authenticator | Bảo vệ liên kết tài khoản, xác nhận kênh và bảo đảm người đã proofing nhận credential |
| **Trùng/nhầm hồ sơ** | Hai nhân viên cùng tên hoặc một người tái gia nhập | Dùng khóa định danh bền vững, resolution có kiểm tra, tránh tái sử dụng khóa tùy tiện |
| **Lạm dụng quyền ngoại lệ** | Nhân viên nội bộ duyệt nhãn assurance không có đủ bằng chứng | Phân quyền phê duyệt, kiểm toán, kiểm tra độc lập, thời hạn ngoại lệ |
| **Kết quả bị giả mạo giữa các hệ thống** | Ứng dụng tin trường *verified* do nguồn không được phép gửi | Xác minh nguồn, bảo vệ truyền dữ liệu và quy tắc ánh xạ tin cậy |
| **Kết quả proofing cũ hoặc bị thu hồi** | Danh tính đã được xác minh nhưng sau đó bị phát hiện gian lận | Cơ chế cập nhật trạng thái, re-proofing theo sự kiện và thu hồi quyền liên quan |

Chất lượng proofing không thể đo duy nhất bằng tỷ lệ người dùng hoàn tất. Quy trình cho tất cả người đăng ký đi qua trong vài giây có thể thuận tiện nhưng chưa chắc đủ assurance nếu khả năng phát hiện gian lận và xử lý ngoại lệ yếu.

## 12. Tính bao trùm, quyền riêng tư và xử lý ngoại lệ

Proofing ở mức assurance cao hơn có thể khó tiếp cận với người không có đầy đủ giấy tờ, người ở xa, người khuyết tật hoặc người có dữ liệu nguồn không nhất quán. Thiết kế tốt cần **các kênh thay thế hợp lệ trong chính sách và tiêu chuẩn áp dụng**, thay vì mặc nhiên loại bỏ người dùng hoặc nới lỏng kiểm soát không có bằng chứng.

Nguyên tắc vận hành:

- Nói rõ cần loại dữ liệu nào, mục đích gì, lưu bao lâu, ai được xem và cách yêu cầu sửa sai.
- Chỉ thu thập bằng chứng đủ cho mức assurance cần thiết; tránh thu thập sinh trắc học “phòng khi cần”.
- Cho phép quy trình xử lý sai khác tên, thay đổi giấy tờ, lỗi OCR hoặc sai hồ sơ mà vẫn giữ kiểm soát chống gian lận.
- Bố trí kênh hỗ trợ có nhân sự được ủy quyền hoặc phương thức được chấp nhận khi người dùng không hoàn tất tự động.
- Không để nhân viên hỗ trợ bỏ qua kiểm soát hoặc cấp mức assurance cao bằng thao tác thủ công thiếu phê duyệt.
- Phân quyền, mã hóa, giám sát và xóa dữ liệu proofing theo chính sách lưu giữ; không ghi tài liệu gốc vào application logs.

**Định danh bằng sinh trắc học** có thể là một thành phần của xác minh người đăng ký, nhưng sinh trắc học là dữ liệu nhạy cảm và có sai số. Nó cần được sử dụng trong đúng mô hình được cho phép, kết hợp các kiểm soát phù hợp; không phải bằng chứng tuyệt đối rằng một người đã được nhận diện đúng.

## 13. Kiểm toán và chỉ số vận hành

Hệ thống nên phân biệt **quyết định proofing**, **thao tác tạo tài khoản** và **trạng thái quyền tại hệ thống đích**. Một luồng có thể proofing thành công nhưng provisioning lỗi; hoặc tạo tài khoản thành công khi proofing chưa đủ điều kiện. Việc tổng hợp thành một trạng thái *SUCCESS* sẽ che mất rủi ro.

### Bằng chứng kiểm toán nên có

| Nhóm bằng chứng | Thông tin cần truy vết |
|---|---|
| **Đầu vào** | Mã yêu cầu, nguồn HRIS/đối tác, định danh chủ thể, thời điểm tiếp nhận |
| **Proofing** | Mức yêu cầu, chính sách và ấn bản, phương thức, tham chiếu bằng chứng, kết quả |
| **Xử lý ngoại lệ** | Lý do, người xét duyệt, thẩm quyền, mức tạm thời, thời hạn và kết quả khắc phục |
| **Liên kết danh tính** | Bản ghi IAM đã gắn, phương thức chống trùng, sự kiện thay đổi liên kết |
| **Cấp quyền** | Quyết định RBAC/ABAC, phê duyệt, hệ thống đích, trạng thái quyền thực tế |
| **Thu hồi** | Sự kiện Mover/Leaver, các token/phiên/quyền phải thu hồi, kết quả đối soát |

### Chỉ số hữu ích

- **Proofing completion rate:** tỷ lệ yêu cầu hoàn tất theo chính sách, tách rõ từng kênh và từng nhóm người dùng.
- **Proofing failure and manual-review rate:** tỷ lệ thất bại, chuyển xét duyệt và lý do phổ biến; chú ý cả gian lận lẫn lỗi dữ liệu.
- **Wrong-link / duplicate-identity incidents:** số vụ liên kết nhầm hoặc trùng bản ghi có tác động thực tế.
- **Assurance policy exceptions:** số ngoại lệ còn hiệu lực, quá hạn, chưa đủ bằng chứng hoặc chưa được xử lý.
- **Joiner readiness:** tỷ lệ người mới đạt điều kiện xác minh và có quyền hợp lệ trước thời điểm bắt đầu.
- **Mover assurance gap:** số người có vai trò mới đòi mức proofing khác nhưng chưa xử lý.
- **Leaver residual access:** số đường truy cập còn hiệu lực sau mốc thu hồi, kể cả khi hồ sơ proofing vẫn đang được lưu giữ hợp lệ.

Đặt SLA theo mức rủi ro; một hồ sơ mới đọc tài liệu công khai và một nhân sự được cấp quyền quản trị hệ thống lõi có thể có ngưỡng kiểm soát khác nhau. Cần lưu tương quan giữa yêu cầu proofing, quyết định IAM, sự kiện HRIS và việc thực thi tại IdP/ứng dụng.

## 14. Tình huống xuyên suốt: thay đổi assurance theo vai trò

Giả sử một tổ chức có nhân viên **Minh** với mã nội bộ **P-2046**. Minh gia nhập ở vai trò cộng tác viên nội dung; sau đó chuyển sang phụ trách xử lý thông tin nhân sự, và cuối cùng nghỉ việc.

### Giai đoạn 1 — Joiner

Nguồn nhân sự tạo bản ghi Minh, IAM kiểm tra trùng và quy định proofing tối thiểu cho loại hợp đồng. Nếu hồ sơ mới chỉ có thông tin tự khai và đã xác thực email, IAM **không được gắn nhãn IAL2** nếu chưa hoàn tất quy trình proofing phù hợp. Quyền được giới hạn vào không gian biên tập ít nhạy cảm, sau khi các điều kiện về tài khoản và xác thực đáp ứng chính sách.

### Giai đoạn 2 — Mover

Minh chuyển sang bộ phận HR, cần truy cập dữ liệu lương. IAM nhận sự kiện thay đổi vai trò, tính chênh lệch quyền, **thu hồi quyền không còn hợp lệ** ở ứng dụng biên tập và kiểm tra bộ điều kiện mới. Nếu vai trò HR yêu cầu IAL2 theo chính sách tổ chức, Minh phải qua proofing phù hợp trước khi nhận quyền nhạy cảm. Sau khi đạt, IdP cập nhật các thuộc tính đáng tin cậy, quyền được cấp theo RBAC/ABAC và phải vượt kiểm tra xác thực, SoD hoặc phê duyệt liên quan. Việc “đã chuyển vào phòng HR” **không tự chứng minh** danh tính được proofing ở mức cao hơn.

### Giai đoạn 3 — Leaver

HRIS phát sự kiện chấm dứt hợp đồng. IAM vô hiệu hóa đăng nhập, hủy phiên/token có thể thu hồi, thu hồi quyền ở ứng dụng HR và các hệ thống liên quan, đối soát phần truy cập tồn dư. Hồ sơ proofing được bảo quản hoặc xóa theo lịch lưu giữ, nhưng **không còn tạo quyền truy cập**. Nếu Minh quay lại sau này, chính sách tái gia nhập quyết định phần thông tin nào có thể dùng lại và cần proofing gì trước khi cấp lại quyền.

### Phân tích quyết định

Ở mỗi bước, cần trả lời riêng: **Minh là ai (IAL)? Phiên đăng nhập có đủ mạnh (AAL)? Nếu đi qua IdP–ứng dụng, federation có đủ bảo vệ (FAL)? Minh hiện được làm gì (authorization)? Quan hệ công việc hiện còn hiệu lực không (lifecycle)?**

Chỉ khi tất cả điều kiện tương ứng đều đạt thì hành động mới được cho phép.

## 15. Checklist thực hành

1. **Tách khái niệm:** tài liệu và hệ thống có phân biệt IAL, AAL, FAL với vai trò/quyền không?
2. **Chọn mức theo rủi ro:** mỗi loại nghiệp vụ có mức assurance và điều kiện chấp nhận được phê duyệt, có căn cứ không?
3. **Tuân thủ bộ chuẩn cụ thể:** kết luận IAL có chỉ ra phiên bản, quy trình, nguồn, bằng chứng và bộ kiểm soát đã thực hiện không?
4. **Chống nhầm danh tính:** identity resolution và account linking có xử lý tên trùng, hồ sơ trùng, đổi email và tái gia nhập không?
5. **Liên kết kết quả:** IdP, HRIS, IGA và ứng dụng có biết nguồn gốc, phạm vi, trạng thái và thời điểm proofing thay vì tin một cờ tùy ý không?
6. **Áp dụng trong JML:** Joiner xác minh trước khi cấp quyền; Mover đánh giá nhu cầu proofing mới; Leaver thu hồi quyền độc lập với trạng thái lưu hồ sơ proofing chưa?
7. **Kiểm soát phiên và quyền:** đã đánh giá AAL/FAL, RBAC/ABAC, phê duyệt và SoD riêng với IAL chưa?
8. **Xử lý ngoại lệ:** người không thể dùng kênh proofing mặc định có quy trình thay thế được phê duyệt và kiểm toán không?
9. **Bảo vệ dữ liệu:** có tối thiểu hóa dữ liệu, giữ bằng chứng trong nơi bảo vệ, đặt thời hạn lưu giữ và tránh lộ PII trong log không?
10. **Đối soát và sự cố:** có phát hiện mức assurance thiếu, kết quả hết phù hợp, account linking sai và quyền tồn dư sau Mover/Leaver không?

### Ghi nhớ

**IAL đo mức bảo đảm của việc xác lập danh tính; AAL đo mức bảo đảm của xác thực; FAL đo mức bảo đảm của xác thực liên kết.** Chúng hỗ trợ nhưng không thay thế kiểm soát phân quyền. Trong quản lý vòng đời IAM, assurance cần được chọn theo rủi ro, chứng minh bằng một quy trình phù hợp, gắn với nguồn danh tính tin cậy và đánh giá lại khi có thay đổi quan trọng. Sự chính xác của proofing giúp tránh cấp tài khoản cho sai người; **đối soát và thu hồi quyền khi Mover/Leaver** giúp ngăn kết quả xác minh cũ trở thành đường truy cập tồn dư.
