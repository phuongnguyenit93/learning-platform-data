# Control framework là gì?

Trong chương **Control framework**, **control framework** (khung kiểm soát) là một cấu trúc có tổ chức để xác định, phân loại, triển khai, quản trị và đánh giá các biện pháp kiểm soát nhằm hỗ trợ đạt mục tiêu của tổ chức. Trong an toàn thông tin, framework giúp chuyển câu hỏi chung **“Hệ thống có an toàn không?”** thành những câu hỏi có thể quản lý và kiểm chứng: **“Cần kiểm soát rủi ro nào, control nào phải hoạt động, ai chịu trách nhiệm, đánh giá theo tiêu chí gì và bằng chứng nào chứng minh điều đó?”**

Ví dụ, nền tảng học trực tuyến có mục tiêu ngăn giảng viên truy cập hồ sơ học viên ngoài lớp được phân công. Một framework có thể giúp tổ chức phân loại yêu cầu này vào nhóm quản lý danh tính/quyền truy cập, đặt kỳ vọng về phân quyền và giám sát, và bảo đảm việc đánh giá không chỉ kiểm tra một API riêng lẻ. Tuy nhiên, framework **không tự viết logic authorization, không tự cấp quyền tối thiểu và cũng không tạo ra bằng chứng** rằng API đã đúng. Đội ngũ phải lựa chọn control phù hợp, triển khai tại những điểm cần thiết và xác nhận hiệu quả trong thực tế.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**: xây dựng cách đánh giá có bằng chứng rằng hệ thống đạt mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls tới kiểm thử, audit, khắc phục phát hiện và tổ chức security assurance liên tục trong phát triển, vận hành. Vì vậy, trọng tâm của bài không phải thuộc lòng tên các framework, mà là hiểu **framework đóng vai trò gì trong chuỗi risk → requirement → control → test → evidence → conclusion → remediation**.

## 1. Kết quả học tập

Sau khi hoàn thành bài này, bạn có thể:

1. Giải thích control framework, mục đích, thành phần và giới hạn của nó trong quản trị bảo mật.
2. Phân biệt framework, security policy, standard, control objective, control, procedure, control catalog và audit checklist.
3. Nhận biết vai trò điển hình của NIST Cybersecurity Framework, ISO/IEC 27001–27002, NIST SP 800-53, CIS Controls và các bộ yêu cầu chuyên biệt.
4. Chọn, điều chỉnh (*tailor*) và ánh xạ framework dựa trên bối cảnh, rủi ro, nghĩa vụ và nguồn lực thực tế.
5. Xây dựng control register/baseline với owner, scope, tiêu chí đạt, phương pháp kiểm thử, loại bằng chứng và trigger đánh giá lại.
6. Phân biệt hiệu quả thiết kế, triển khai và vận hành control; tránh suy diễn từ checklist hoàn thành sang mức bảo đảm tuyệt đối.
7. Sử dụng kết quả đánh giá để quản lý finding, ngoại lệ, residual risk và báo cáo quản trị.
8. Áp dụng control framework cho hệ thống Java và nền tảng học trực tuyến có cloud, CI/CD, IAM, API, dữ liệu học viên và nhà cung cấp.

## 2. Hiểu đúng bản chất của control framework

### 2.1. Framework tổ chức cách suy nghĩ, không thay thế thực thi

Một framework bảo mật cung cấp **ngôn ngữ chung** để trao đổi về những kết quả hoặc lĩnh vực kiểm soát cần đạt. Tùy bộ framework, nó có thể nêu:

- **Mục tiêu/kết quả mong muốn:** ví dụ hạn chế truy cập trái phép hoặc khôi phục dịch vụ sau gián đoạn.
- **Lĩnh vực hoặc chức năng:** quản trị, nhận diện tài sản, bảo vệ, phát hiện, ứng phó, phục hồi.
- **Danh mục control:** tập các yêu cầu, biện pháp hoặc mục tiêu kiểm soát để lựa chọn.
- **Phân cấp và tham chiếu:** mã định danh, nhóm, mối quan hệ và cấu trúc ánh xạ.
- **Phương pháp đánh giá hoặc hồ sơ hỗ trợ:** phạm vi áp dụng, tiêu chí, hướng dẫn thực hiện, vai trò và nguồn bằng chứng, nếu framework hoặc tài liệu bổ trợ cung cấp.
- **Cơ chế cải tiến:** xem xét khoảng cách giữa trạng thái hiện tại và trạng thái mong muốn.

Không phải framework nào cũng có đủ các thành phần này. Có framework thiên về **kết quả quản trị**, có bộ thiên về **catalog controls**, có bộ thiên về **hướng dẫn triển khai kỹ thuật** và có tiêu chuẩn nêu **yêu cầu có thể đánh giá chứng nhận** trong phạm vi nhất định.

**Điểm mấu chốt:** framework chỉ có ích khi được nối với tài sản, mối đe dọa, chính sách, control owner, hiện trạng kỹ thuật và bằng chứng. Việc gắn nhãn “đã áp dụng framework X” không tự chứng minh tổ chức đạt mục tiêu bảo mật.

### 2.2. Vì sao cần khung thay vì các biện pháp rời rạc?

Một đội phát triển có thể đã bật MFA, dùng WAF và chạy dependency scanner. Dù mỗi biện pháp hữu ích, tổ chức vẫn có thể bỏ sót:

- Không có ai chịu trách nhiệm về tài khoản service có quyền lớn.
- Có alert rule nhưng không có người trực hoặc không biết alert bị ngắt.
- Có backup hằng ngày nhưng chưa từng kiểm thử restore.
- Có mã hóa trong truyền nhưng chia sẻ dữ liệu vượt mục đích cần thiết.
- Có kiểm tra code nhưng sản phẩm vẫn bị lộ dữ liệu chéo tenant do sai business authorization.
- Có quy trình xử lý lỗ hổng nhưng không xác định được tài sản nào đang chạy phiên bản liên quan.

Framework giúp **nhìn xuyên các nhóm hệ thống và vòng đời**: bảo mật không chỉ là tập công cụ phòng ngừa mà còn là phân vai, kiểm tra, phát hiện, ứng phó, phục hồi, nhà cung cấp và quản trị rủi ro.

### 2.3. Kết quả thực tế cần đạt

Một chương trình sử dụng control framework tốt có thể trả lời:

1. Những **mục tiêu bảo mật** và rủi ro trọng yếu nào đang được quản lý?
2. Vì sao từng control được chọn hoặc không áp dụng?
3. Control thuộc phạm vi **hệ thống, dữ liệu, đội, vendor** nào?
4. Ai chịu trách nhiệm **thiết kế, vận hành, tạo evidence, đánh giá**?
5. Điều kiện thế nào mới được gọi là **control đạt**?
6. Có evidence nào cho thấy control đạt **thiết kế, triển khai và hiệu quả vận hành**?
7. Những finding/ngoại lệ nào vẫn tồn tại, ai quyết định residual risk?
8. Khi code, cloud, dữ liệu, quyền và mối đe dọa thay đổi, điều gì sẽ được đánh giá lại?

Đó là cầu nối từ framework tới **security assurance có thể kiểm chứng**.

## 3. Framework khác policy, standard và control thế nào?

Các thuật ngữ thường xuất hiện cạnh nhau nhưng phục vụ mục đích khác nhau.

| Thành phần | Trả lời câu hỏi | Ví dụ của nền tảng học trực tuyến |
|---|---|---|
| **Risk** | Điều gì có thể gây ảnh hưởng và hậu quả là gì? | Giảng viên có thể đọc dữ liệu của lớp khác |
| **Security objective** | Kết quả bảo vệ nào cần đạt? | Dữ liệu học viên chỉ đến đúng người có quyền |
| **Control framework** | Những nhóm kết quả/control nào cần được xem xét và quản trị? | Lĩnh vực identity/access, application security, monitoring |
| **Policy** | Tổ chức tuyên bố nguyên tắc bắt buộc gì? | Dữ liệu học viên chỉ được chia sẻ trong mục đích được phê duyệt |
| **Standard/baseline** | Tiêu chí tối thiểu, mức và quy tắc áp dụng là gì? | API phải thực thi authorization theo đối tượng ở phía server |
| **Control objective** | Control cần đạt kết quả cụ thể nào? | Ngăn chủ thể không được cấp quyền đọc bản ghi lớp khác |
| **Control** | Biện pháp giảm rủi ro cụ thể được thiết kế/vận hành là gì? | Authorization trong service, log truy cập nhạy cảm |
| **Procedure** | Ai thực hiện bước nào để vận hành control? | Quy trình cấp/thu hồi quyền và review quyền lớp |
| **Test/assessment** | Kiểm tra control có đúng yêu cầu không? | Negative test truy cập lớp khác, review access |
| **Evidence** | Dữ liệu nào hỗ trợ kết luận? | Test report gắn build, IAM/config export, audit log |
| **Finding** | Sai lệch nào được chứng minh? | Worker vẫn tạo file export khi API trả lỗi |
| **Risk decision** | Residual risk được xử lý thế nào? | Sửa trước release hoặc giới hạn chức năng có điều kiện |

### 3.1. Control objective khác control implementation

**Control objective** nói về **điều cần đạt**, thường bền vững hơn công nghệ. **Control implementation** là cách tổ chức triển khai điều đó.

Ví dụ:

- Objective: chỉ các tài khoản được cấp quyền hợp lệ mới có thể thao tác quản trị production.
- Implementation A: cloud IAM roles với quy trình approval và xác thực phù hợp.
- Implementation B: privileged access management và session auditing.
- Implementation C: cơ chế break-glass bị giới hạn, được giám sát và kiểm tra sau sử dụng.

Một objective có thể được hỗ trợ bởi **nhiều control**. Một control có thể phục vụ **nhiều objective**. Không nên sao chép tên control vào hồ sơ mà không mô tả tác dụng đối với kịch bản rủi ro.

### 3.2. Framework, control catalog và checklist

- **Framework:** cấu trúc tổng thể để phân loại mục tiêu, lĩnh vực hoặc control và điều phối chương trình.
- **Control catalog:** tập các control hoặc control statements có mã để lựa chọn; có thể là thành phần trong framework.
- **Checklist:** tập câu hỏi dùng để thu thập/kiểm tra trạng thái; có thể được xây dựng từ framework và catalog.

Một checklist 200 câu “Yes/No” không tự trở thành control framework hữu hiệu nếu thiếu phạm vi, lý do áp dụng, owner, phương pháp test và cách xử lý evidence gap. Ngược lại, một framework với danh mục rõ vẫn cần checklist hoặc test plan cụ thể để vận hành.

### 3.3. Framework khác compliance

**Compliance** là mức đáp ứng yêu cầu áp dụng từ luật, quy định, hợp đồng, chính sách hoặc một chương trình đánh giá cụ thể. **Security assurance** là mức có cơ sở bằng chứng để tin rằng các mục tiêu bảo mật được đáp ứng trong phạm vi và kỳ kiểm chứng.

Framework có thể hỗ trợ cả hai, nhưng:

- Áp dụng một framework **không tự đồng nghĩa** mọi nghĩa vụ pháp lý đã đáp ứng.
- Có chứng nhận/báo cáo trong một phạm vi **không chứng minh** mọi sản phẩm và đường tấn công đều an toàn.
- Đáp ứng một checklist **không loại bỏ** toàn bộ residual risk.
- Một control được đánh dấu không áp dụng cần **lý do và phê duyệt phù hợp**, không đơn giản vì thiếu nguồn lực.

## 4. Các loại control framework và tài liệu tham chiếu

Không tồn tại một “framework duy nhất tốt nhất” cho mọi bối cảnh. Cần xác định loại kết quả đang cần: quản trị, hệ thống quản lý, catalog biện pháp, ưu tiên bảo vệ, hay kiểm chứng kỹ thuật.

### 4.1. Các ví dụ thường được dùng

| Khung/tiêu chuẩn tham chiếu | Trọng tâm chính | Giá trị đối với security assurance | Điều không nên nhầm |
|---|---|---|---|
| **NIST Cybersecurity Framework (CSF)** | Các kết quả an ninh mạng ở cấp tổ chức và cách quản trị rủi ro | Tạo ngôn ngữ chung để nhìn trạng thái hiện tại, mục tiêu và khoảng trống | Không phải một danh sách cấu hình kỹ thuật áp dụng nguyên xi cho mọi máy chủ |
| **ISO/IEC 27001** | Yêu cầu đối với hệ thống quản lý an toàn thông tin (ISMS) và phương pháp quản trị | Kết nối phạm vi, risk treatment, trách nhiệm, review và cải tiến | Có chứng nhận ISMS trong scope không bảo đảm mọi ứng dụng không có lỗ hổng |
| **ISO/IEC 27002** | Hướng dẫn về các biện pháp kiểm soát an toàn thông tin | Gợi ý cách hiểu/chọn/triển khai các control phù hợp | Không nên coi tài liệu hướng dẫn tự nó là chứng nhận cho một sản phẩm |
| **NIST SP 800-53** | Catalog security/privacy controls chi tiết | Hỗ trợ lựa chọn, tailoring và kiểm tra các yêu cầu control | Không mặc nhiên mọi control đều bắt buộc với mọi tổ chức |
| **CIS Controls** | Tập các biện pháp ưu tiên để cải thiện phòng vệ trước các rủi ro thường gặp | Hỗ trợ lộ trình triển khai và xác minh các safeguards cụ thể | Không thay thế phân tích rủi ro nghiệp vụ và các nghĩa vụ khác |
| **COBIT** | Quản trị và quản lý thông tin/công nghệ doanh nghiệp | Hỗ trợ trách nhiệm, mục tiêu quản trị, đo lường và kiểm soát | Không phải checklist ứng dụng chuyên sâu cho một API Java |
| **OWASP ASVS** | Yêu cầu và mức kiểm chứng bảo mật ứng dụng | Hữu ích để định nghĩa yêu cầu/test cho authentication, authorization và các chức năng ứng dụng | Không thay thế toàn bộ quản trị rủi ro tổ chức hoặc ISMS |
| **CSA Cloud Controls Matrix (CCM)** | Các lĩnh vực/biện pháp kiểm soát phù hợp môi trường cloud | Hỗ trợ đánh giá trách nhiệm, kiểm soát và nhà cung cấp cloud | Cần xác định service/scope, tránh coi mọi cloud control là của nhà cung cấp |

Các khung trên có **mục đích và cấu trúc khác nhau**. Tùy phiên bản và tài liệu bản quyền, cách đặt tên, phân nhóm, control IDs và yêu cầu có thể thay đổi; khi xây hồ sơ áp dụng thật cần ghi rõ **phiên bản được phê duyệt** và kiểm tra bản gốc tương ứng.

### 4.2. NIST CSF dưới góc nhìn kết quả

NIST CSF 2.0 tổ chức các kết quả an ninh mạng trong sáu chức năng cấp cao:

1. **Govern:** quản trị chiến lược, kỳ vọng, trách nhiệm, chính sách, risk management và giám sát.
2. **Identify:** hiểu tài sản, bối cảnh, rủi ro và những yếu tố cần bảo vệ.
3. **Protect:** triển khai biện pháp giảm khả năng/tác động của sự kiện bất lợi.
4. **Detect:** phát hiện và phân tích những sự kiện hoặc dấu hiệu có thể gây hại.
5. **Respond:** phản ứng, phối hợp và hạn chế tác động khi có sự cố.
6. **Recover:** khôi phục tài sản, năng lực và hoạt động sau sự cố.

Một sản phẩm có CI/CD và MFA tốt vẫn có thể có điểm yếu lớn nếu **Detect** không hoạt động, **Recover** chưa test hoặc **Govern** thiếu owner. Các chức năng giúp tránh nhìn bảo mật chỉ là ngăn chặn tấn công.

**Lưu ý:** Chức năng, category/subcategory là cách tổ chức các kết quả trong CSF; đừng tự suy ra đây là một bộ yêu cầu kiểm thử kỹ thuật giống hệt control catalog khác.

### 4.3. ISO/IEC 27001 và 27002

ISO/IEC 27001 giúp tổ chức lập, vận hành, giám sát và cải tiến **Information Security Management System (ISMS)** theo phạm vi xác định. Trong triển khai, tổ chức xác định bối cảnh, yêu cầu liên quan, phân tích và xử lý rủi ro, xác định controls và đánh giá việc thực hiện. Phụ lục A của ISO/IEC 27001 cung cấp tham chiếu control; ISO/IEC 27002 cung cấp hướng dẫn liên quan đến những control này.

Một tài liệu quan trọng khi chọn control trong ISMS là **Statement of Applicability (SoA)**: giải thích các control cần thiết, lý do áp dụng hoặc loại trừ, và trạng thái triển khai theo phương pháp/phiên bản tiêu chuẩn áp dụng.

SoA **không thay thế evidence**. Control được ghi “implemented” phải được kiểm chứng theo mục tiêu và phạm vi; nếu chỉ có chính sách mà chưa test khả năng vận hành, không nên tuyên bố đã có operating effectiveness.

### 4.4. NIST SP 800-53 và lựa chọn control

NIST SP 800-53 cung cấp một catalog security/privacy controls có cấu trúc phục vụ các quy trình lựa chọn, tailoring và đánh giá. Khi sử dụng, không nên sao chép mọi control vào backlog rồi đòi triển khai tất cả bất kể bối cảnh.

Cần xác định baseline phù hợp nếu có, điều kiện áp dụng, shared responsibility, thông số cần điền, biện pháp tương đương, phần được kế thừa và các phép đánh giá cần thiết. Một catalog chi tiết hỗ trợ tính nhất quán nhưng **không thay thế phân tích attack path của ứng dụng**.

### 4.5. CIS Controls và triển khai theo ưu tiên

CIS Controls nhấn mạnh những safeguards thực tiễn như kiểm kê tài sản/phần mềm, quản trị cấu hình, truy cập, lỗ hổng, log và khả năng phục hồi. Cách ưu tiên giúp đội còn ít nguồn lực triển khai những biện pháp có giá trị sớm.

Điểm cần nhớ: ưu tiên thực hiện một safeguard không tự có nghĩa safeguard đó **đã đạt trong toàn bộ tài sản**. Cần scope, owner, test và evidence, đồng thời bổ sung control theo rủi ro riêng như phân quyền nghiệp vụ chéo lớp.

### 4.6. Kết hợp nhiều khung có hợp lý không?

Có. Một tổ chức có thể:

- Sử dụng **NIST CSF** để nói chuyện với lãnh đạo về kết quả tổng thể.
- Tổ chức chương trình ISMS và risk treatment theo **ISO/IEC 27001** nếu phù hợp.
- Dùng **NIST SP 800-53/CIS Controls** làm nguồn tham chiếu cho các control cụ thể.
- Dùng **OWASP ASVS** làm đầu vào cho tiêu chí kiểm chứng bảo mật ứng dụng.
- Dùng baseline cloud hoặc chính sách nội bộ cho phần thiết kế vận hành đặc thù.

Nhưng không nên tạo năm checklist độc lập khiến cùng một control bị đánh giá lặp lại mà kết quả không nhất quán. Hãy xây **một control register nội bộ có ID ổn định**, cho phép ánh xạ tới nhiều nguồn yêu cầu, đồng thời giữ được những khác biệt mà các khung đặt ra.

## 5. Cấu trúc logic của một chương trình control framework

Một cách nhìn tổng quát:

~~~mermaid
flowchart TD
    B["Mục tiêu kinh doanh và tài sản"] --> R["Risk scenarios và nghĩa vụ"]
    R --> F["Chọn và tailor control framework"]
    F --> S["Security policy, control baseline"]
    S --> C["Control catalog, scope, owners"]
    C --> I["Triển khai kỹ thuật và quy trình"]
    I --> E["Kiểm thử, telemetry, evidence"]
    E --> A{"Assessment có đủ căn cứ?"}
    A -->|"Đạt theo scope"| Q["Assurance claim và residual risk"]
    A -->|"Fail/thiếu bằng chứng"| G["Finding, evidence gap, remediation"]
    G --> I
    Q --> D["Báo cáo và quyết định có thẩm quyền"]
    D --> T["Change/incident/threat → reassessment"]
    T --> R
~~~

Đường đi này không phải một chuỗi waterfall cứng. Trong thực tế, đội security có thể phát hiện lỗ hổng và bổ sung control ngay, rồi cập nhật risk register, mapping và evidence. Quan trọng là **tính truy vết được bảo toàn**.

### 5.1. Framework nguồn và control nội bộ

Không nên gắn trực tiếp mọi logic vận hành với mã điều khoản của một tài liệu bên ngoài, vì các nguồn có thể đổi phiên bản hoặc có nhiều requirement cùng cần một control.

Một mô hình thường dễ quản trị hơn:

- **Source requirement:** yêu cầu từ framework, luật, hợp đồng, audit hoặc chính sách.
- **Internal control:** biện pháp nội bộ có ID ổn định.
- **Implementation:** cấu hình hoặc quy trình theo dịch vụ/đơn vị.
- **Test method:** phương pháp đánh giá tiêu chí control.
- **Evidence record:** kết quả và nguồn dữ liệu có metadata.
- **Assessment result:** kết luận có phạm vi, kỳ, mức tin cậy và giới hạn.
- **Finding/risk:** sai lệch, xử lý và residual risk.

Mối quan hệ có thể là **nhiều-nhiều**: một requirement được hỗ trợ bởi nhiều controls; một control đáp ứng nhiều yêu cầu; một evidence hỗ trợ nhiều kết luận nhưng phải chứng minh từng quan hệ.

### 5.2. Control framework không bằng tập công cụ

WAF, SIEM, SAST, MFA, vulnerability scanner, secrets manager và backup đều có thể là thành phần của một implementation. Nhưng một control framework còn quan tâm:

- Ai thiết kế quy tắc và phê duyệt thay đổi?
- Độ phủ của công cụ là bao nhiêu? Có tài sản bị bỏ sót không?
- Có đường bypass hoặc tính năng chưa được test không?
- Khi cảnh báo xuất hiện, ai triage và theo thời hạn nào?
- Có khả năng phục hồi khi control phòng ngừa thất bại không?
- Ai đánh giá hiệu quả và xử lý các ngoại lệ?

**Công cụ không phải kết quả bảo mật.** Phải đánh giá tác dụng thực tế đối với risk scenario.

## 6. Các nhóm control và tác động lên rủi ro

Một cách phân loại hữu ích là theo **thời điểm/tác dụng**:

| Loại | Mục tiêu | Ví dụ | Evidence cần xem |
|---|---|---|---|
| **Preventive** | Ngăn hoặc giảm khả năng sự kiện xảy ra | Least privilege, authorization, MFA, network segmentation | Cấu hình thực, negative test, review quyền |
| **Detective** | Phát hiện sự kiện/sai lệch đủ sớm | Audit log, SIEM alert, config drift detection | Test nguồn log, synthetic event, alert ticket |
| **Corrective** | Sửa nguyên nhân hoặc trạng thái không phù hợp | Patch, rollback, thu hồi quyền, phục hồi cấu hình | Change record, retest, post-fix config |
| **Responsive** | Hạn chế tác động khi sự cố đang diễn ra | Revoke token, cô lập dịch vụ, incident runbook | Diễn tập, incident record, thời gian xử lý |
| **Recovery** | Khôi phục dữ liệu/dịch vụ sau sự cố | Backup, restore, DR failover | Restore test, integrity check, RTO/RPO |
| **Governance/directive** | Xác lập trách nhiệm và điều kiện thực thi | Policy, RACI, approval, training, risk review | Chính sách phê duyệt, sample process records |

Các nhóm không tách biệt tuyệt đối. Một control có thể vừa phát hiện vừa hỗ trợ ứng phó; một quy trình access review có tác dụng phát hiện quyền dư và kích hoạt thu hồi.

### 6.1. Theo hình thức thực thi

- **Technical controls:** phần mềm, cấu hình, network, crypto, automation.
- **Administrative/organizational controls:** chính sách, quy trình, phê duyệt, phân quyền nhiệm vụ, đào tạo.
- **Physical controls:** kiểm soát ra vào, bảo vệ thiết bị, môi trường vật lý.

Framework hiệu quả xem xét **con người, quy trình và công nghệ**. Một control chỉ có quy định nhưng không có người vận hành là lỗ hổng thực thi. Một control chỉ có code mà thiếu ownership và monitoring cũng dễ suy yếu theo thời gian.

### 6.2. Theo ảnh hưởng tới likelihood và impact

Ví dụ bảo vệ API export:

- Server-side authorization làm giảm **khả năng truy cập thành công ngoài quyền**.
- Giới hạn dữ liệu và phân vùng quyền có thể giảm **quy mô/tác động** nếu có xâm nhập.
- Audit logging và detection không ngăn mọi sự kiện, nhưng giúp **phát hiện và hạn chế tác động**.
- Cơ chế thu hồi token, tạm dừng export và điều tra giúp **đáp ứng sự cố**.
- Backup và quy trình khôi phục giúp xử lý một số hậu quả về **toàn vẹn/sẵn sàng**, không thể “thu hồi” dữ liệu đã bị lộ ra ngoài.

Đánh giá hiệu quả control phải gắn với **risk path**, không chỉ đếm số control.

## 7. Chọn framework theo bối cảnh và mục đích

Một lựa chọn phù hợp bắt đầu từ **nhu cầu**, không phải tên framework nổi tiếng.

### 7.1. Những câu hỏi sàng lọc

1. Tổ chức muốn **quản trị rủi ro**, hỗ trợ audit/chứng nhận, thiết kế baseline hay kiểm tra ứng dụng?
2. Loại hệ thống nào: SaaS, IaaS, ứng dụng Java, thiết bị, OT, dữ liệu đặc biệt?
3. Dữ liệu và dịch vụ trọng yếu là gì; ảnh hưởng khi mất CIA?
4. Có nghĩa vụ pháp luật, hợp đồng, ngành hoặc bên quản lý nào áp dụng không?
5. Framework cần bao phủ toàn tổ chức hay chỉ một sản phẩm/khối hệ thống?
6. Nguồn lực: owner, nhân sự kỹ thuật, assessor, công cụ và hệ thống evidence có đáp ứng không?
7. Cần khả năng **mapping giữa nhiều nguồn** hay một baseline duy nhất?
8. Ai là đối tượng nhận báo cáo: lãnh đạo, risk owner, auditor, khách hàng hay kỹ sư?
9. Chu kỳ thay đổi hệ thống nhanh đến đâu; automation có thực tế không?
10. Khả năng duy trì, cập nhật phiên bản và quyền truy cập tài liệu gốc ra sao?

### 7.2. Ví dụ lựa chọn

Một công ty mới phát triển hệ thống học trực tuyến có thể chọn một cấu trúc quản trị rủi ro dễ hiểu ở cấp công ty, một catalog control cơ bản cho IAM/cloud/backup/monitoring, và một bộ tiêu chí application security cho API Java. Đây là **ví dụ kiến trúc chương trình**, không phải lời khuyên mặc định rằng mọi công ty phải đồng thời tuân thủ hoặc chứng nhận tất cả các bộ đó.

### 7.3. Framework và nghĩa vụ bắt buộc

Luật, hợp đồng hoặc yêu cầu khách hàng có thể đặt nghĩa vụ cụ thể. Khi có sự khác nhau:

- Xác định **nguồn yêu cầu** và đơn vị có thẩm quyền diễn giải.
- Không tự cho rằng áp dụng framework là đã đáp ứng pháp luật.
- Không loại bỏ yêu cầu bắt buộc chỉ vì framework chính không có mục tương ứng.
- Nếu yêu cầu trùng lặp, mapping về control chung nhưng giữ **tiêu chí riêng** của từng nguồn.
- Lưu phiên bản của tài liệu áp dụng và lịch review khi thay đổi.

Khi có yếu tố pháp lý, Legal/Compliance cần tham gia xác định nghĩa vụ; nhóm security không nên tự đưa ra kết luận pháp luật từ một bảng mapping kỹ thuật.

## 8. Tailoring: điều chỉnh framework mà không làm mất mục tiêu

**Tailoring** là quá trình lựa chọn, điều chỉnh hoặc bổ sung control theo phạm vi, rủi ro và yêu cầu áp dụng. Nó không có nghĩa tùy ý loại bỏ các control khó triển khai.

### 8.1. Những quyết định tailoring thường gặp

- **Áp dụng:** control cần thiết với một số hoặc toàn bộ hệ thống.
- **Không áp dụng (N/A):** không có đối tượng/điều kiện liên quan trong phạm vi, có căn cứ.
- **Triển khai theo cách khác:** mục tiêu được đáp ứng bằng một control tương đương hoặc phối hợp nhiều control; phải chứng minh hiệu quả.
- **Inherited/shared control:** kế thừa một phần từ cloud/vendor hoặc central platform; cần xác định trách nhiệm còn lại.
- **Bổ sung control:** rủi ro riêng của nghiệp vụ cần control không nêu rõ trong bộ khung nguồn.
- **Thay mức kiểm tra:** tăng độ phủ hoặc tần suất ở hệ thống trọng yếu, giảm các bước thủ công dư thừa ở nơi ít rủi ro.
- **Ngoại lệ có điều kiện:** tạm chưa đạt baseline nhưng có quyết định đúng thẩm quyền, risk assessment, giới hạn và theo dõi.

### 8.2. Ví dụ tailoring theo tài sản

| Control objective | API lưu dữ liệu học viên | Công cụ nội bộ không có dữ liệu thật | Giải thích |
|---|---|---|---|
| Kiểm tra quyền truy cập đối tượng | Bắt buộc theo scope và kịch bản | Có thể khác phạm vi, vẫn phải kiểm tra nhu cầu quyền | Mục tiêu gắn với dữ liệu và actor |
| Giám sát truy cập nhạy cảm | Ưu tiên cao, bảo vệ audit log | Theo mức rủi ro hoạt động thực tế | Phụ thuộc impact và khả năng điều tra |
| Backup và restore dữ liệu | Đánh giá theo RPO/RTO đã phê duyệt | Có thể không cần phục hồi cùng mức nếu dữ liệu tái tạo được | Phải có BIA, không đoán |
| Quy trình phát hành an toàn | Bắt buộc với đường production quan trọng | Có thể dùng gate nhẹ hơn nhưng vẫn có kiểm soát thay đổi phù hợp | Không loại bỏ quản trị chỉ vì ít người dùng |
| Kiểm soát nhà cung cấp | Áp dụng nếu có vendor xử lý dữ liệu/tính năng | Có thể không áp dụng cho thành phần tự vận hành | Giải thích theo dependency thực |

### 8.3. Ghi bằng chứng về quyết định N/A

Một quyết định “không áp dụng” nên bao gồm:

- Control/requirement nguồn và phiên bản.
- Hệ thống, tài sản hoặc hoạt động thuộc phạm vi.
- Lý do không áp dụng: điều kiện thực tế nào không tồn tại?
- Bằng chứng về phạm vi và giả định hỗ trợ.
- Người đề xuất, người phê duyệt, ngày, điều kiện tái đánh giá.
- Trigger nếu dữ liệu, ứng dụng hoặc kiến trúc thay đổi.

Ví dụ không thể ghi “không có dữ liệu cá nhân” nếu sản phẩm mới đã thu thập email học viên nhưng inventory chưa cập nhật. Quyết định N/A phải được sửa khi giả định không còn đúng.

## 9. Xây dựng control baseline và control register

Một **control baseline** là tập yêu cầu tối thiểu được tổ chức phê duyệt cho một nhóm tài sản/hoạt động. **Control register** mô tả các control được lựa chọn và cách chúng được sở hữu, áp dụng, kiểm tra.

### 9.1. Trường tối thiểu của một control record

| Trường | Ý nghĩa |
|---|---|
| **Control ID và tên** | Định danh ổn định, tránh trùng lặp |
| **Objective/risk linkage** | Mục tiêu, kịch bản rủi ro, tài sản nào được bảo vệ |
| **Framework mappings** | Nguồn yêu cầu, phiên bản, mã tham chiếu phù hợp |
| **Control statement** | Quy định kết quả hoặc hành vi cần đạt |
| **Scope/applicability** | Tài sản, môi trường, user, ứng dụng, vendor |
| **Owner/accountability** | Người vận hành, người quản lý rủi ro và các bên tham gia |
| **Implementation** | Chính sách, service, config, code và quy trình cụ thể |
| **Design and acceptance criteria** | Tiêu chí xác nhận control xử lý đúng rủi ro |
| **Test/assessment method** | Phương pháp, dữ liệu, mức độc lập, chu kỳ/trigger |
| **Evidence** | Nguồn, loại artifact, metadata, owner và kỳ |
| **Status** | Đang thiết kế/triển khai/đạt/chưa đạt/thiếu bằng chứng/ngoại lệ theo quy tắc |
| **Finding/remediation** | Sai lệch, owner, hạn, retest và liên kết |
| **Residual risk** | Mức rủi ro sau control và thẩm quyền quyết định |
| **Change history** | Phiên bản, lần cập nhật, thay đổi scope, review |

Điều quan trọng hơn số trường là **trường nào phục vụ quyết định kiểm chứng và có dữ liệu đáng tin**.

### 9.2. Ví dụ control register YAML

Mẫu dưới đây dùng **mã nội bộ minh họa**, không giả định có một external control ID cụ thể tương đương hoàn toàn ở các framework.

~~~yaml
control_id: CTRL-APP-AUTHZ-01
name: "Kiểm soát truy cập dữ liệu học viên theo đối tượng"
control_objective: >
  Người dùng chỉ được đọc hoặc xuất dữ liệu lớp học khi có
  quyền hợp lệ đối với hành động và đối tượng trong phạm vi.
risk_ids: ["RISK-LEARNER-ACCESS-01"]
applicability:
  service: "Learning Platform API"
  environments: ["production"]
  assets: ["learner-records", "export-jobs", "exported-files"]
  paths: ["web-api", "mobile-api", "export-worker", "file-download"]
framework_mappings:
  - source: "Internal security control framework"
    requirement: "APP-AUTHORIZATION"
  - source: "Application verification standard selected by organization"
    requirement: "Mapped exact reference to be verified against version"
control_type: ["preventive", "detective"]
implementation:
  - "Server-side object authorization"
  - "Scope bound to background jobs and file downloads"
  - "Audit event for sensitive export"
owners:
  business_risk_owner: "Learning Platform Product Owner"
  technical_control_owner: "Backend Engineering"
  evidence_owner: "QA / Platform"
  reviewer: "Security Assurance"
assessment:
  expected:
    - "Unauthorized cross-class requests are denied"
    - "Denied requests do not create exposed files or jobs"
    - "Relevant audit records can be verified"
  methods:
    - "Positive and negative integration tests"
    - "Review production build and configuration mapping"
    - "Validate worker and storage side effects"
  frequency: "When authorization changes and by risk-based review"
  triggers: ["New endpoint", "Role change", "Export architecture change"]
evidence:
  - "Versioned test result with actor and class fixtures"
  - "Deployment record and runtime configuration"
  - "Job/file trace and audit log"
result: "Pending actual assessment"
residual_risk: "Determined after reviewing evidence"
~~~

**Không được dùng mã control minh họa thay cho việc xác minh nguồn chính thức**. Khi mapping vào một chuẩn bên ngoài, cần lưu phiên bản, điều khoản/control ID thực tế, và lý do nội bộ cho rằng control hỗ trợ yêu cầu đó.

### 9.3. Tại sao phải có ID và version?

Nếu dùng tên “kiểm soát truy cập” chung chung, các nhóm có thể hiểu khác nhau và tạo báo cáo trùng lặp. ID ổn định cùng version giúp xác định:

- Kết quả test thuộc control statement nào.
- Hệ thống nào áp dụng baseline phiên bản nào.
- Một finding ảnh hưởng control nào, đã được kiểm tra lại chưa.
- Khi framework nguồn đổi phiên bản, mapping nào phải cập nhật.
- Lãnh đạo đang xem **cùng một định nghĩa** giữa các kỳ báo cáo.

Đừng đồng nhất **phiên bản framework nguồn**, **phiên bản baseline nội bộ**, **phiên bản implementation**, và **kỳ evidence**. Chúng có thể thay đổi ở các thời điểm khác nhau.

## 10. Ánh xạ control frameworks: làm một lần, dùng nhiều mục đích

### 10.1. Vì sao mapping khó?

Các framework có thể mô tả cùng một chủ đề ở **mức trừu tượng khác nhau**.

Ví dụ “manage identities and credentials” có thể là một kết quả cấp cao, trong khi một catalog khác chia thành quản lý account, chứng thực, cấp quyền, review và thu hồi. Một requirement ứng dụng còn phải kiểm tra quyền theo **từng đối tượng**, không thể mặc định được bảo vệ chỉ nhờ SSO.

Do đó mapping không phải luôn là **một–một hoặc tương đương tuyệt đối**.

### 10.2. Mẫu bảng mapping

| Mục tiêu nội bộ | Nguồn tham chiếu | Control thực thi | Giới hạn mapping | Evidence |
|---|---|---|---|---|
| Quản lý quyền đặc biệt | Khung quản trị và catalog IAM được chọn | IAM approval, least privilege, access review | Cần tách tài khoản con người và workload | IAM export, approval, negative test |
| Bảo vệ truy cập dữ liệu theo lớp | Nguồn ứng dụng và access-control requirements | Object-level authorization trong Java service | SSO/MFA không thay authorization nghiệp vụ | Authz tests, deploy mapping |
| Phát hiện hoạt động bất thường | Các kết quả về detection/monitoring | Audit event, rule, alert triage | Có SIEM chưa chứng minh coverage | Synthetic event, log, ticket |
| Khôi phục dịch vụ | Các kết quả về resilience/recovery | Backup và restore runbook | Backup success chưa chứng minh restore | Restore test, RPO/RTO check |
| Quản trị bên thứ ba | Kết quả về supplier risk | Supplier tiering, due diligence, contract control | Evidence vendor không bao gồm config phía khách hàng | Supplier record, reviews, test |

### 10.3. Chất lượng mapping

Mỗi mapping nên ghi:

- Nguồn và phiên bản áp dụng.
- Mục đích mapping: hỗ trợ thực thi, compliance, báo cáo hay audit.
- Loại quan hệ: **trực tiếp, hỗ trợ một phần, tổng hợp từ nhiều controls, không tương đương**.
- Phạm vi và phần chưa được bao phủ.
- Người review và ngày review.
- Các bằng chứng để xác minh nội dung mapping khi cần.

Nếu một câu trong catalog nguồn yêu cầu điều mà control nội bộ chưa đáp ứng, không được đánh dấu “fully mapped” chỉ vì tiêu đề giống nhau.

### 10.4. Tránh “compliance by spreadsheet”

Một bảng tính có thể ghi 100% các hàng đã được gắn một control nội bộ, nhưng điều đó chỉ cho biết **mapping coverage**, không cho biết **control effectiveness**. Cần phân biệt:

1. Requirement được ánh xạ vào control nào?
2. Control đã được thiết kế đúng chưa?
3. Control được triển khai ở đâu và có bao phủ scope không?
4. Control hoạt động đúng trong kỳ không?
5. Evidence đủ cho claim hay không?
6. Residual risk và finding còn gì?

## 11. Từ framework sang security requirements có thể kiểm thử

Một framework thường mô tả định hướng rộng. Để engineering thực hiện, yêu cầu phải chuyển thành **behavior cụ thể**.

### 11.1. Phương pháp viết requirement

Một requirement nên nêu:

- **Actor/asset:** ai tương tác với dữ liệu hoặc hành động?
- **Security invariant:** điều gì bắt buộc đúng?
- **Điểm thực thi:** service, API, IdP, worker, cloud, quy trình?
- **Scope:** user, tenant, environment, kỳ.
- **Expected result:** hành vi đạt và hành vi bị từ chối.
- **Monitoring/exception:** nếu control fail hoặc cần ngoại lệ thì sao?
- **Testability:** phép thử và nguồn evidence cụ thể.

**Yêu cầu chưa đủ:** “Ứng dụng phải phân quyền an toàn.”

**Yêu cầu kiểm chứng được hơn:**

> Khi một giảng viên yêu cầu xem hoặc xuất dữ liệu học viên, hệ thống phải xác định quyền với **đúng lớp và hành động** tại phía server; mọi đường truy cập ngoài quyền phải bị từ chối và không tạo file hoặc job xuất dữ liệu ngoài phạm vi; hoạt động nhạy cảm phải được ghi dấu vết theo chính sách.

### 11.2. Kiểm tra end-to-end

Một control authorization ở API controller chưa chắc bảo vệ **queue, export worker, object storage, download URL**. Cần threat model và data flow để đặt điều kiện kiểm chứng cho từng ranh giới tin cậy. Đây là lý do catalog control và application threat modeling **bổ trợ**, không thay thế nhau.

### 11.3. Tiêu chí không chỉ là “đã bật”

Với một control logging, tiêu chí “log enabled = true” chưa đủ. Có thể cần:

- Nguồn sự kiện quan trọng trong scope được ghi.
- Log có nội dung cần thiết cho điều tra, tránh lộ secret/PII quá mức.
- Luồng ingest và alert hoạt động; có synthetic test phù hợp.
- Quyền sửa/xóa và retention được kiểm soát.
- Có owner nhận và triage khi alert xuất hiện.
- Khi hệ thống log fail, có health check và quy trình phản hồi.

Như vậy control objective về **khả năng phát hiện** có thể được kiểm thử bằng behavior thay vì sự hiện diện của công cụ.

## 12. Kiểm thử control và các lớp effectiveness

### 12.1. Ba lớp cần phân biệt

| Lớp | Câu hỏi | Evidence | Không thể kết luận thay |
|---|---|---|---|
| **Design effectiveness** | Control được thiết kế để giảm đúng rủi ro và không bỏ qua đường quan trọng? | Architecture review, threat model, control design | Chưa chứng minh đã triển khai |
| **Implementation effectiveness** | Control tồn tại và áp dụng đúng trên hệ thống hiện tại? | Runtime config, code, policy, test theo build | Chưa chắc hoạt động suốt kỳ |
| **Operating effectiveness** | Control vận hành ổn định theo tiêu chí trong kỳ đánh giá? | History, mẫu giao dịch, access review, log/alert, test định kỳ | Không suy rộng ngoài scope/kỳ được kiểm tra |

Ví dụ một chính sách yêu cầu MFA là bằng chứng thiết kế/quản trị. Screenshot MFA của một IdP là bằng chứng cấu hình tại một thời điểm. Để kết luận tất cả tài khoản admin production được bảo vệ cả quý, cần xác nhận **population**, các đường truy cập, lịch sử chính sách và ngoại lệ.

### 12.2. Chọn phương pháp test

- **Inspection:** xem policy, cấu hình, source code, hồ sơ phê duyệt hoặc data flow.
- **Interview:** hỏi owner hiểu và thực hiện quy trình ra sao; cần đối chiếu bằng chứng khác cho claim quan trọng.
- **Observation:** quan sát control hoạt động.
- **Technical testing:** negative/positive tests, config probe, restore drill, alert test.
- **Sampling:** kiểm tra population theo phương pháp xác định; không suy rộng tùy tiện.
- **Automated assessment:** CI/CD, policy-as-code, cloud controls monitoring, IAM diff.
- **Independent review:** người không trực tiếp vận hành control đánh giá evidence theo phạm vi được giao.

Một test tool pass không có nghĩa control đạt nếu **tool không nhìn thấy tài sản, quyền scan thiếu, test bị skip hoặc phạm vi thực hiện không tương đương production**.

### 12.3. Kết quả đánh giá phải rõ

Có thể dùng bốn trạng thái cơ bản:

- **Đạt:** tiêu chí được thỏa mãn trong scope/kỳ, evidence đủ và phù hợp.
- **Không đạt:** có sai lệch được chứng minh.
- **Chưa đủ bằng chứng:** không có cơ sở kết luận đạt/không đạt với chất lượng cần thiết.
- **Không áp dụng:** có căn cứ rằng control không liên quan trong phạm vi xác định.

**Ngoại lệ được chấp nhận** là một tình trạng quản trị riêng, không tự đổi control fail thành pass. Các nhãn nội bộ phải thống nhất với chương trình audit áp dụng; không dùng từ “compliant” một cách rộng quá phạm vi bằng chứng.

## 13. Bằng chứng cho control framework

Một khung kiểm soát chỉ có giá trị assurance khi mỗi control trọng yếu có **evidence contract**: mô tả bằng chứng cần có để hỗ trợ kết luận.

### 13.1. Các tiêu chí chất lượng

| Thuộc tính | Câu hỏi đối chiếu | Ví dụ sai thường gặp |
|---|---|---|
| **Relevance** | Bằng chứng chứng minh đúng control/claim nào? | Dùng dependency scanner để kết luận phân quyền nghiệp vụ đạt |
| **Scope/completeness** | Có đủ tài sản, user, môi trường, đường đi trong population? | Chỉ lấy IAM từ một cloud account |
| **Freshness/period** | Bằng chứng phản ánh đúng thời điểm/kỳ đánh giá? | Screenshot cũ sau nhiều lần thay đổi |
| **Provenance** | Nguồn, công cụ, người tạo, thời gian, version có rõ? | File “final-audit.pdf” không xác định xuất xứ |
| **Integrity** | Có thể phát hiện thay đổi trái phép/đối chiếu bản gốc? | Bản sửa tay không còn audit trail |
| **Accuracy/reliability** | Dữ liệu được thu thập đầy đủ, công cụ chạy đúng scope? | Scanner bỏ sót asset không được tag |
| **Representativeness** | Sample có đại diện cho kết luận muốn đưa? | Chọn vài ticket đẹp để chứng minh mọi change |
| **Repeatability/independence** | Người khác có thể kiểm tra lại và tránh xung đột lợi ích phù hợp? | Người viết control tự tuyên bố độc lập đạt |

**Thiếu bằng chứng không đồng nghĩa control chắc chắn thất bại**, nhưng cũng không được dùng sự thiếu đó làm lý do kết luận an toàn. Evidence gap cần có owner và action.

### 13.2. Evidence catalog mẫu

| Control | Evidence thiết kế | Evidence triển khai | Evidence vận hành |
|---|---|---|---|
| IAM privileged access | IAM policy và mô hình quyền | Runtime role, MFA/SSO config | Access review, cấp/thu hồi, kiểm tra bypass |
| Secure CI/CD | Release security standard | Pipeline rule, artifact mapping | Build/test/approval records theo release |
| App authorization | Object authorization requirement, threat model | Code và API/worker implementation | Integration/negative tests, log, incident review |
| Detection | Monitoring use case, alert criteria | Rule và pipeline config | Synthetic event, alert triage, health checks |
| Recovery | BIA, RPO/RTO, DR design | Backup/config, quyền khôi phục | Restore drill và integrity verification |
| Supplier risk | Vendor policy, due diligence criteria | Contract, shared responsibility, tenant config | Assessment, change notice, incidents, remediation |

Không nên áp đặt một dạng evidence cho mọi control. Một policy có thể được đánh giá qua phê duyệt/version và thực hiện, còn authorization cần **hành vi trong request thật hoặc test có ngữ cảnh**.

### 13.3. Evidence metadata quan trọng

Tối thiểu ghi control ID, claim, asset/environment, time, period, evidence source, method, tool/version, owner, expected/actual, exceptions, reviewer và links tới risk/finding. Với test CI/CD cần thêm **commit, build, artifact và deployment mapping**. Với log incident có thể cần quy trình bảo quản/chain of custody riêng.

Bằng chứng chứa PII, token, cấu hình mạng hoặc thông tin tấn công cần **phân loại, hạn chế truy cập và retention** phù hợp. Thu thập evidence không được tạo thêm một kho dữ liệu nhạy cảm bị chia sẻ rộng rãi.

### 13.4. Không suy diễn từ chứng nhận

Một chứng nhận hoặc báo cáo độc lập có thể hỗ trợ claim trong **scope và kỳ được nêu**, nhưng không tự chứng minh control phía tổ chức sử dụng dịch vụ đã đúng. Ví dụ một SaaS có báo cáo assurance không chứng minh khách hàng đã bật MFA cho tenant, cấp OAuth scope tối thiểu hoặc đã tắt tài khoản cũ.

## 14. Control owner, risk owner và người đánh giá

### 14.1. Vai trò trong chương trình

| Vai trò | Trách nhiệm |
|---|---|
| **Ban điều hành/cấp quản trị** | Phê duyệt chiến lược, mức rủi ro chấp nhận, nguồn lực và giám sát |
| **CISO/GRC** | Chọn/điều phối framework, baseline, chính sách, tiêu chí, đánh giá và báo cáo |
| **Business/risk owner** | Xác định tác động nghiệp vụ, phương án xử lý và quyết định trong thẩm quyền |
| **Control owner** | Thiết kế, triển khai/vận hành, ghi trạng thái và khắc phục sai lệch |
| **Engineering/Platform/Ops** | Thực hiện controls trong ứng dụng, hạ tầng, pipeline và quy trình vận hành |
| **Evidence producer** | Thu thập artifact, bảo đảm metadata, nguồn và khả năng truy vết |
| **Assessor/Security assurance** | Xác minh chất lượng evidence và kết luận control theo tiêu chí |
| **Internal audit** | Đánh giá độc lập theo kế hoạch và phạm vi được giao |
| **Legal/Compliance/Privacy** | Làm rõ nghĩa vụ áp dụng và các yêu cầu liên quan |
| **Vendor owner và supplier** | Phân định trách nhiệm và bằng chứng trong quan hệ bên thứ ba |

Một cá nhân có thể kiêm nhiều vai trò ở công ty nhỏ, nhưng phải công khai **mức độc lập của assessment**. Người trực tiếp vận hành control không nên được mặc định là auditor độc lập của chính mình.

### 14.2. Ví dụ RACI giản lược

R = Responsible, A = Accountable, C = Consulted, I = Informed.

| Công việc | CISO/GRC | Control owner | Risk owner | Assessor | Internal audit |
|---|---|---|---|---|---|
| Chọn/tailor baseline nội bộ | A/R theo phân quyền | C | C | C | I |
| Triển khai control kỹ thuật | C | A/R | I | C | I |
| Thu thập evidence và tự kiểm | C | A/R | I | C | I |
| Đánh giá assurance được giao | A hoặc C theo cơ cấu | C | I | R hoặc A/R | I |
| Quyết định xử lý/chấp nhận residual risk | C, khuyến nghị | C | A/R | C | I |
| Audit nội bộ độc lập | C | C | I | C | A/R |

Bảng là **minh họa**, không phải một mô hình RACI bắt buộc. Tổ chức phải có cấp phê duyệt rõ và cơ chế escalation khi control trọng yếu fail hoặc rủi ro vượt appetite.

## 15. Case study: framework cho nền tảng học trực tuyến Java

### 15.1. Bối cảnh

Một nền tảng học có:

- Frontend web/mobile cho học viên và giảng viên.
- Backend Java xử lý đăng nhập, lớp học, bài nộp, điểm, quyền giáo viên.
- PostgreSQL lưu dữ liệu học tập và object storage lưu file.
- Cloud IAM và CI/CD triển khai vào production.
- Queue/worker tạo file báo cáo.
- API tích hợp nhà cung cấp email và phân tích học tập.
- Dashboard vận hành, hệ thống logging và backup.

Lãnh đạo yêu cầu: **“Có thể chứng minh rằng những rủi ro bảo mật quan trọng nhất đã được kiểm soát chưa?”**

Một framework giúp chuyển câu hỏi thành **các control domains** có chủ sở hữu và test. Nhưng phải bắt đầu từ asset/data flow và risk scenarios, không chỉ mua công cụ.

### 15.2. Mục tiêu và rủi ro trọng yếu

| Mục tiêu | Kịch bản rủi ro | Hậu quả |
|---|---|---|
| Chỉ đúng người có quyền xem dữ liệu học viên | API hoặc worker bỏ qua quyền theo lớp | Lộ thông tin và mất niềm tin |
| Điểm và kết quả học tập không bị sửa ngoài quyền | Sai quy trình hoặc privilege escalation | Mất tính toàn vẹn dữ liệu |
| Quyền admin production được kiểm soát | Lộ token, tài khoản thừa quyền, không có MFA phù hợp | Chiếm quyền vận hành hoặc trích xuất dữ liệu |
| Phát hiện hoạt động bất thường | Thiếu log/alert hoặc rule bị vô hiệu | Không thể nhận ra và điều tra sự cố kịp |
| Khôi phục hệ thống khi gián đoạn | Backup không dùng được, thiếu khóa giải mã | Mất dữ liệu, gián đoạn hoạt động học |
| Không chuyển dữ liệu vượt mục đích cho vendor | API key quá rộng, thiếu data minimization | Lộ dữ liệu và nghĩa vụ liên quan |
| Artifact phát hành có nguồn đáng tin | Dependency hoặc pipeline bị can thiệp | Thực thi code không mong muốn ở production |

### 15.3. Thiết kế control baseline rút gọn

| Control ID | Domain | Control và tiêu chí | Owner | Bằng chứng |
|---|---|---|---|---|
| CTRL-APP-01 | Application security | Server-side object authorization ở mọi đường dữ liệu học viên; deny ngoài quyền và không có side effect | Backend | Negative tests, worker/file trace, deploy proof |
| CTRL-IAM-01 | Identity/access | Đặc quyền có owner, approval, xác thực phù hợp và được rà soát | Platform/IAM | Permission export, access review, test login |
| CTRL-SDLC-01 | Secure delivery | Release qua kiểm tra được phê duyệt và artifact truy vết được | Engineering/DevOps | CI result, approval, artifact/deploy record |
| CTRL-LOG-01 | Detection | Sự kiện nhạy cảm được ghi và pipeline phát hiện còn hoạt động | SecOps | Log health, synthetic alert, ticket |
| CTRL-DATA-01 | Data protection | Dữ liệu vendor nhận đúng scope, retention và quyền | Data/Backend + vendor owner | Data flow, payload test, IAM scope, contract |
| CTRL-DR-01 | Recovery | Dữ liệu/trạng thái khôi phục đạt mục tiêu đã phê duyệt | Operations/DBA | Restore test, integrity, RTO/RPO |
| CTRL-CHG-01 | Change management | Thay đổi production có owner và approval hoặc ngoại lệ khẩn cấp hợp lệ | Platform/DevOps | Change history, deployment reconciliation |

Đây là **baseline minh họa**, không phải bộ control bắt buộc đủ cho mọi nền tảng. Mỗi control cần thêm scope, phân loại rủi ro, tần suất, owner phụ, điều kiện fail và quy trình xử lý.

### 15.4. Đi sâu vào control authorization

**Risk:** một giảng viên có tài khoản hợp lệ gửi yêu cầu xuất dữ liệu lớp khác.

**Requirement:** chỉ cho phép đọc/xuất dữ liệu đúng lớp mà actor có quyền, ở tất cả đường API, worker và download.

**Design:** authorization ở backend từ nguồn quyền đáng tin, export job ràng buộc actor/scope, storage private, đường tải được bảo vệ.

**Implementation:** code kiểm tra quyền, cấu hình triển khai, phân quyền worker và storage đúng bản.

**Tests:** quyền hợp lệ phải hoạt động, quyền ngoài lớp bị deny; đổi quyền hoặc dùng job sai scope không làm lộ file; kiểm tra hậu điều kiện DB/queue/storage.

**Evidence:** danh mục endpoint, test results có build/version và actor/class fixtures, job/file trace, runtime IAM/config, log, deployment record.

**Assurance claim:** có thể kết luận trong những đường export production đã được kiểm tra, theo kỳ/bản đã nêu; các đường chưa thuộc phạm vi phải được ghi riêng.

### 15.5. Control implementation có thể phản ánh bằng mã Java

Ví dụ sau chỉ minh họa một biện pháp phía server; không phải đoạn mã hoàn chỉnh cho production:

~~~java
public ExportJobId createExport(
        AuthenticatedUser actor,
        long classId) {

    if (!authorization.canExportClass(
            actor.userId(), classId)) {
        throw new AccessDeniedException("Export not permitted");
    }

    // Export job, worker và download path cũng phải bảo toàn scope.
    return exportService.scheduleForAuthorizedScope(
            actor.userId(), classId);
}
~~~

Một rule trong framework có thể dẫn tới requirement và kiểm thử nói trên. Tuy vậy đoạn code chưa chứng minh **authorization ở worker và storage**, chưa nói đến giao dịch đồng thời, thu hồi quyền, quyền service account hoặc logging. Vì thế framework không thay threat modeling và kiểm thử end-to-end.

### 15.6. Khi control thất bại

Giả sử kiểm thử cho thấy endpoint trả 403 nhưng worker vẫn tạo file export lớp khác. Đó là **control failure có bằng chứng**, không phải “đã có authorization nên pass”. Quy trình:

1. Ghi finding với actor, request, job trace, file reference và ảnh hưởng.
2. Đánh giá risk và giới hạn chức năng hoặc khắc phục theo mức ưu tiên.
3. Giao backend/worker owner sửa nguyên nhân.
4. Bổ sung test âm cho side effects và các đường tương tự.
5. Deploy bản sửa qua security gate.
6. Retest đối với artifact/môi trường đúng scope.
7. Đánh giá residual risk, cập nhật control record và assurance claim.

Không đóng finding chỉ vì pull request đã merge hoặc ticket đã chuyển “Done”.

## 16. Shared controls và nhà cung cấp

Trong hệ thống cloud, nhiều control được chia sẻ giữa **bên dùng dịch vụ, nhà cung cấp nền tảng và các đội nội bộ**.

Ví dụ với cloud managed database:

- Cloud provider vận hành một số biện pháp vật lý và nền tảng theo hợp đồng.
- Platform team cấu hình network, access policy, backup option và monitoring thuộc trách nhiệm của bên sử dụng.
- App team kiểm tra quyền tại endpoint và quyền workload khi truy cập DB.
- Risk owner chịu trách nhiệm về rủi ro dữ liệu và phương án xử lý theo thẩm quyền.
- Security assurance đánh giá evidence và các phần không được bao phủ.

### 16.1. Control kế thừa không có nghĩa bỏ qua kiểm chứng

Nếu dựa vào một control inherited/shared, control register cần ghi:

- Nhà cung cấp hoặc team nào thực hiện phần nào?
- Scope và thời kỳ của báo cáo vendor/bằng chứng nội bộ.
- Điều khoản trách nhiệm, thay đổi và thông báo sự cố.
- Những phần do bên mình phải cấu hình hoặc giám sát.
- Rủi ro khi provider control fail hoặc không có bằng chứng.
- Khả năng thay thế, cô lập, khôi phục hoặc ngừng tích hợp.

Một chứng nhận ISO hoặc báo cáo SOC 2 của provider có thể hỗ trợ đánh giá trong **scope của báo cáo**, nhưng không chứng minh IAM, dữ liệu và API của mình được cấu hình đúng. Khi provider thay dịch vụ hoặc subprocessor, cần xem lại trách nhiệm và mapping.

## 17. Kiểm soát thay đổi và continuous assurance

Framework có xu hướng được phê duyệt theo kỳ, nhưng code, cấu hình cloud, IAM và luồng dữ liệu thay đổi nhanh. Vì vậy cần nối control register với **trigger và bằng chứng đang sống**.

### 17.1. Nhịp đánh giá theo vòng đời

| Thời điểm | Việc phải làm | Evidence/đầu ra |
|---|---|---|
| Xác định sản phẩm và dữ liệu | Chọn risk scenarios và control baseline ban đầu | Asset inventory, threat model, risk assessment |
| Thiết kế | Xác định security requirements, owner, testability | Architecture review, control design |
| Phát triển | Thực hiện controls, test behavior | Code review, integration/security tests |
| CI/CD và release | Kiểm chứng change, artifact và các gate có liên quan | Build result, approval, deploy mapping |
| Vận hành | Quan sát log, IAM, drift, lỗ hổng, sự cố | Telemetry, access review, config evidence |
| Phục hồi/diễn tập | Kiểm tra phản ứng và khôi phục | IR/DR drill, restore report, lessons learned |
| Audit và đánh giá rủi ro | Đối chiếu hiệu quả, finding, ngoại lệ | Assessment, residual risk, decision record |
| Khi có thay đổi lớn | Xem lại applicability, mapping, tiêu chí và evidence | Delta assessment, control/test updates |

**Continuous** không đồng nghĩa đánh giá mọi control mỗi phút. Tần suất cần dựa vào rủi ro, tốc độ thay đổi và khả năng tự động hóa. Kiểm tra chính sách có thể theo kỳ; policy-as-code có thể chạy mỗi release; diễn tập DR thực hiện theo lịch/trigger thích hợp.

### 17.2. Trigger cần cập nhật control framework nội bộ

- Thêm dữ liệu nhạy cảm, tenant hoặc nhóm người dùng mới.
- Thay IAM provider, cơ chế phân quyền, gateway, API hoặc network architecture.
- Thay mô hình cloud, vendor, subprocessor hoặc vùng lưu trữ.
- Có mối đe dọa mới, CVE ảnh hưởng thành phần trọng yếu, khai thác đã quan sát.
- Có control failure hoặc incident chứng minh giả định không còn đúng.
- Có yêu cầu hợp đồng/pháp lý mới hoặc thay risk appetite.
- Framework nguồn cập nhật phiên bản, nội dung mapping có thay đổi.
- Có finding quá hạn, ngoại lệ hết hiệu lực hoặc kiểm thử restore thất bại.

Khi trigger xuất hiện, đánh giá **những control/claim bị ảnh hưởng**; không cần làm lại toàn bộ chương trình nếu phần lớn không thay đổi, nhưng cũng không được tiếp tục dựa trên evidence đã hết giá trị.

## 18. Quản lý finding, exception và residual risk

### 18.1. Control fail không nhất thiết bằng risk “không chấp nhận được”, nhưng phải đánh giá

Một control fail có thể tạo rủi ro đáng kể hoặc được giảm bởi control khác. Quy trình đúng không phải che kết quả fail, mà:

1. Xác định **tiêu chí và scope thất bại**.
2. Đánh giá kịch bản rủi ro và tác động kinh doanh.
3. Xác nhận những control khác có thực sự giảm đường rủi ro không.
4. Phân công remediation owner và deadline.
5. Đề xuất giới hạn chức năng hoặc control bù trừ nếu cần.
6. Trình residual risk và phương án lên người có thẩm quyền.
7. Retest sau thay đổi và cập nhật conclusion.

**Risk acceptance** là quyết định quản trị về rủi ro còn lại, không tự biến test fail thành pass. Nếu một tiêu chí pháp luật/hợp đồng bắt buộc chưa đạt, approval nội bộ không tự miễn nghĩa vụ đó.

### 18.2. Ngoại lệ nên có gì?

Một exception record tốt gồm **requirement/control ID**, nguồn và phiên bản, scope, lý do sai lệch, current risk, evidence, control bù trừ, người đề nghị, cấp phê duyệt, thời hạn, monitoring, trigger đánh giá lại và remediation plan.

Ví dụ môi trường cũ chưa hỗ trợ MFA trực tiếp. Tổ chức có thể đánh giá cơ chế truy cập qua gateway đã có xác thực mạnh và monitoring, đồng thời lên kế hoạch thay thế. Nhưng phải kiểm tra có đường truy cập trực tiếp bypass gateway hay không và liệu ngoại lệ có được phép theo nghĩa vụ áp dụng không.

### 18.3. Trạng thái control và trạng thái risk không giống nhau

| Control assessment | Risk treatment | Giải thích |
|---|---|---|
| Pass trong scope | Residual risk vẫn có thể tồn tại | Control đạt tiêu chí không làm mọi threat biến mất |
| Fail | Mitigation cần thực hiện | Có finding và action, không được báo đạt |
| Insufficient evidence | Điều tra/bổ sung bằng chứng | Không được tự xếp risk thấp |
| Fail với exception hợp lệ | Risk accepted có điều kiện | Sai lệch vẫn được ghi, giám sát và xem lại |
| Not applicable có căn cứ | Không xem là coverage thực thi | Cần review nếu scope thay đổi |

## 19. Đo lường chương trình control framework

### 19.1. Những metric hữu ích

| Metric | Ý nghĩa | Điều có thể làm sai lệch |
|---|---|---|
| % tài sản trọng yếu có control owner | Độ rõ trách nhiệm | Có tên owner không chứng minh control chạy tốt |
| % controls có mapping tới risk và requirements | Tính truy vết | Mapping chỉ theo tiêu đề có thể sai |
| % controls critical có evidence hợp lệ | Độ phủ assurance | Evidence cũ/sai scope làm số liệu đẹp giả |
| % controls pass / fail / insufficient theo mức rủi ro | Tình trạng thực | Nhiều control ít quan trọng có thể che một lỗi nghiêm trọng |
| Số finding high quá hạn | Khả năng xử lý sai lệch | Đóng ticket không retest làm giảm giả |
| % remediation đã retest đạt | Chất lượng khắc phục | Test chỉ ở staging không luôn đủ cho claim production |
| % release có security gates và artifact mapping | Bảo đảm quy trình phát hành | Gate có thể bị bypass hoặc test bị skip |
| Tỷ lệ control kế thừa có trách nhiệm rõ | Shared responsibility coverage | Báo cáo vendor không đủ cho config của khách hàng |
| Số ngoại lệ quá hạn/gia hạn nhiều lần | Nợ kiểm soát | Ít ngoại lệ có thể do không báo sai lệch |
| Thời gian xử lý khi control fail | Năng lực phản ứng | Chỉ đo những sự kiện được phát hiện |

### 19.2. Không gộp mọi thứ thành “% compliant”

Một dashboard báo “98% controls passed” cần chú thích:

- Mẫu số gồm những control nào; đã xét applicability chưa?
- Có trọng số theo **risk/criticality** không?
- Điều kiện “pass” là policy, implementation hay operating effectiveness?
- Evidence có trong kỳ và đúng scope không?
- “Not assessed” hoặc “insufficient evidence” có bị coi như pass?
- Hai control fail có nằm trên một hệ thống quan trọng và tạo đường tấn công không?
- Chương trình có kiểm tra độc lập với owner ở mức phù hợp không?

Không nên biến số lượng control đạt thành xác suất hệ thống an toàn. Một authorization control thất bại trên API học viên có thể quan trọng hơn hàng chục biện pháp quản trị nhỏ đang đạt.

### 19.3. Báo cáo cho lãnh đạo

Một báo cáo hữu ích nên nêu **mục tiêu bảo mật trọng yếu, phạm vi, trạng thái control theo rủi ro, xu hướng finding, điều chưa thể chứng minh, residual risk và quyết định cần cấp trên**. Đính kèm links tới hồ sơ nguồn để kiểm chứng, đồng thời bảo vệ thông tin nhạy cảm.

## 20. Các sai lầm thường gặp khi áp dụng framework

### “Chọn framework nổi tiếng là hệ thống đã bảo mật”

Không đúng. Framework định hướng tổ chức control; thiết kế, cấu hình, code, vận hành và kiểm thử mới cho biết hiệu quả thực tế.

### “Cứ triển khai toàn bộ control trong catalog là đủ”

Không luôn hợp lý. Tổ chức cần tailoring theo scope, risk, nghĩa vụ, shared responsibility; có thể phải bổ sung requirement nghiệp vụ không được mô tả đủ chi tiết.

### “Mapping một control với một requirement nghĩa là đạt yêu cầu”

Mapping là quan hệ thiết kế. Phải kiểm tra control implementation, evidence, scope và operating effectiveness.

### “Có chứng chỉ là không còn vulnerability”

Chứng nhận có phạm vi, thời điểm và tiêu chí. Nó không chứng minh mọi endpoint mới, dependency hoặc cấu hình đều an toàn.

### “Framework chỉ việc của Security/GRC”

Control thường được vận hành bởi business, engineering, platform, operations, HR và vendor. Không có owner thực, framework dễ thành tài liệu tĩnh.

### “MFA giải quyết mọi rủi ro truy cập”

MFA hỗ trợ xác thực danh tính, nhưng không tự thay object-level authorization, least privilege, review quyền hoặc giám sát tài khoản dịch vụ.

### “Kết quả scanner pass nghĩa mọi control đang hoạt động”

Scanner chỉ phát hiện những lớp vấn đề và tài sản được nó kiểm tra. Lỗi nghiệp vụ, quyền, quy trình khẩn cấp, phục hồi và bên thứ ba có thể chưa được bao phủ.

### “Không có alert tức detection hoạt động tốt”

Có thể hệ thống không phát hiện vì thiếu log, rule sai hoặc tuyến ingest lỗi. Cần health checks, synthetic tests và đánh giá điều tra thực tế.

### “Lấy mẫu vài ticket đạt có thể kết luận mọi change đều được phê duyệt”

Phải xác định population, cách chọn mẫu, loại change và độ suy rộng. Emergency/manual changes thường cần chú ý riêng.

### “Control fail nhưng risk owner chấp nhận thì có thể báo Pass”

Chấp nhận rủi ro không làm thay đổi bằng chứng thất bại của control. Hãy ghi exception/accepted risk riêng, tiếp tục theo dõi và retest theo yêu cầu.

### “Framework chỉ cần cập nhật vào mùa audit”

Code, cloud, IAM, dữ liệu và mối đe dọa thay đổi liên tục. Framework nội bộ cần trigger reassessment phù hợp.

### “Một framework áp dụng cho mọi vendor và hệ thống giống nhau”

Dữ liệu, quyền, mức phụ thuộc và nghĩa vụ khác nhau; shared responsibility và tiering cần phản ánh thực tế.

## 21. Xây chương trình control framework từ đầu

Một lộ trình có thể chia thành sáu bước. Đây là **thứ tự tham khảo**, không phải dự án bắt buộc có thời lượng cố định.

### Bước 1 — Xác định scope, mục tiêu và risk owners

Liệt kê các dịch vụ, môi trường, dữ liệu, bên thứ ba và hoạt động trọng yếu. Thu thập mục tiêu kinh doanh, kịch bản rủi ro, nghĩa vụ, risk appetite và người có quyền quyết định.

**Đầu ra:** asset/data-flow inventory tối thiểu, risk scenarios, danh sách owner và mục đích chương trình.

### Bước 2 — Chọn nguồn framework và phương pháp tailoring

Đánh giá framework theo nhu cầu và loại hệ thống. Ghi phiên bản, nguồn yêu cầu, phạm vi, điều khoản bắt buộc, cách xác định N/A và quyền phê duyệt.

**Đầu ra:** framework adoption decision, mapping approach và quy tắc applicability.

### Bước 3 — Lập baseline và control register

Chuyển mục tiêu thành control statements có ID, scope, owner, criteria, evidence type và tần suất. Hợp nhất các requirement tương tự nhưng giữ khác biệt có ý nghĩa.

**Đầu ra:** approved baseline, control register, RACI và các gap quan trọng.

### Bước 4 — Triển khai và kiểm thử trên tài sản ưu tiên

Bắt đầu với IAM, data authorization, backup/restore, secure deployment, log/detection và vendor risk nếu đó là những đường rủi ro trọng yếu của hệ thống. Đánh giá thiết kế trước, rồi triển khai/test.

**Đầu ra:** technical controls, procedures, test plans và implementation evidence.

### Bước 5 — Thu thập evidence và lập assurance conclusions

Tự động hóa những nguồn đáng tin, lưu metadata, review chất lượng và trạng thái đạt/không đạt/chưa đủ/N/A. Liên kết finding với owner, hạn và retest.

**Đầu ra:** evidence catalog, assessment record, risk register và executive report.

### Bước 6 — Duy trì theo biến động và cải tiến

Tích hợp trigger từ CI/CD, IAM, change, vulnerability management, incident và audit. Review framework mapping/phiên bản, baseline, N/A và effectiveness khi có thay đổi.

**Đầu ra:** continuous assurance cadence, trend metrics, closed-loop remediation và revised risk decisions.

## 22. Bài tập thực hành

### Bài tập A — Phân biệt framework, standard và control

Một tài liệu nội bộ ghi: “Theo framework bảo mật, mọi tài khoản admin phải có MFA”. Nhóm Platform đưa screenshot có nút MFA bật trên IdP và ghi “control passed”.

Hãy trả lời:

1. Đâu là mục tiêu bảo mật, đâu là requirement và control implementation?
2. Screenshot hỗ trợ đánh giá **design**, **implementation** hay **operating effectiveness**?
3. Cần biết gì về population admin, đường đăng nhập, break-glass và account ngoài IdP?
4. Cần những evidence nào để kết luận cho toàn bộ kỳ?
5. Những trường hợp nào phải ghi finding hoặc evidence gap thay vì Pass?

**Gợi ý:** Danh sách account đặc quyền và các đường đăng nhập thuộc scope phải được đối chiếu từ nguồn thực. Một screenshot chưa đủ cho cả kỳ hoặc cho những hệ thống không dùng cùng IdP.

### Bài tập B — Tailoring framework cho hai dịch vụ

Có hai hệ thống: (A) API quản lý điểm học viên chạy production và (B) ứng dụng tạo biểu đồ nội bộ không xử lý dữ liệu thật theo thiết kế. Hãy lập bảng cho năm control objectives: authorization, logging, backup, vulnerability management, change management.

Với từng control:

- Xác định applicability và lý do.
- Nêu dữ liệu phải xác minh trước khi ghi N/A.
- Đặt owner và mức kiểm thử.
- Nêu evidence minh họa.
- Ghi trigger làm quyết định cần xem lại.

**Gợi ý:** Nếu B bắt đầu nhận dữ liệu học viên hoặc kết nối production, assessment trước đó có thể không còn giá trị.

### Bài tập C — Mapping nhưng không đánh đồng

Tổ chức dùng khung quản trị chung, catalog IAM và tiêu chí kiểm chứng ứng dụng. Một quản lý cho rằng “đã có SSO và MFA nên mọi yêu cầu authorization đều đạt”.

Hãy tạo một mapping ba lớp:

1. Mục tiêu quản trị quyền ở cấp tổ chức.
2. Control IAM xác thực và quyền đặc biệt.
3. Control application object-level authorization cho API dữ liệu học viên.

Giải thích vì sao một control có thể hỗ trợ nhưng **không thay thế** control khác. Thiết kế negative test cho việc giảng viên lớp 42 cố xuất dữ liệu lớp 43.

### Bài tập D — Từ finding tới residual risk

Security test phát hiện worker vẫn tạo file dữ liệu ngoài quyền sau khi controller trả 403. Backend sửa lỗi và đóng ticket. CISO hỏi có thể đánh dấu control Pass chưa.

Hãy viết quy trình:

- Mô tả finding, attack path, ảnh hưởng và owner.
- Đề xuất sửa và test end-to-end, gồm side effects.
- Xác định build và môi trường phải kiểm chứng.
- Lập evidence plan với expected/actual, job/file trace, deploy record.
- Kết luận Pass, Fail hay Insufficient evidence theo từng trường hợp.
- Cập nhật residual risk, risk owner decision và thời điểm review lại.

**Gợi ý:** Ticket Done là trạng thái công việc; không thay bằng chứng retest.

### Bài tập E — Chọn framework theo mục tiêu

Một startup học trực tuyến có ít nhân sự security, khách hàng doanh nghiệp bắt đầu yêu cầu evidence về IAM, secure SDLC, backup và xử lý nhà cung cấp. Hãy đề xuất **cách chọn framework/các nguồn tham chiếu** dựa trên:

- Mục tiêu quản trị, loại hệ thống và nghĩa vụ khách hàng.
- Kiểu control catalog cần cho các nhóm kỹ thuật.
- Cách tránh nhiều checklist trùng lặp.
- Control register và evidence catalog tối thiểu.
- Kế hoạch triển khai theo rủi ro trong ba giai đoạn.
- Giới hạn của chứng nhận hoặc self-attestation vendor.

Không nhất thiết phải chọn nhiều khung. Điều cần chứng minh là phương án đủ bao phủ các rủi ro và yêu cầu, có owner, tiêu chí và cơ chế kiểm tra.

## 23. Checklist đánh giá việc sử dụng control framework

Một tổ chức có thể dùng checklist này để xem chương trình đã vận hành thực chất hay chưa. **Tick đủ ô không phải bằng chứng mọi control đạt**.

- [ ] Mục tiêu kinh doanh, tài sản và risk scenarios đã được xác định.
- [ ] Framework nguồn, mục đích, phiên bản và phạm vi áp dụng được ghi rõ.
- [ ] Nghĩa vụ pháp lý/hợp đồng và nguồn requirement khác đã được nhận diện.
- [ ] Có phương pháp chọn, tailor, bổ sung và phê duyệt N/A có căn cứ.
- [ ] Có approved baseline và control register với ID, owner, scope và mappings.
- [ ] Control statements mô tả kết quả có thể kiểm chứng, không chỉ tên công cụ.
- [ ] Control objective và implementation được phân biệt rõ.
- [ ] Có ma trận risk → requirement → control → test → evidence.
- [ ] Phân định control owner, evidence owner, assessor và risk decision authority.
- [ ] Đã xác định shared/inherited controls và trách nhiệm vendor.
- [ ] Có test plan cho design, implementation và operating effectiveness.
- [ ] Bằng chứng có nguồn, phạm vi, kỳ, integrity và độ phủ phù hợp.
- [ ] Quy định trạng thái Pass/Fail/Insufficient/N/A và các ngoại lệ.
- [ ] Finding có owner, deadline, remediation và retest trước khi đóng theo tiêu chí.
- [ ] Risk acceptance không che giấu control failure hoặc nghĩa vụ bắt buộc.
- [ ] Có monitoring, trigger thay đổi và lịch reassessment theo rủi ro.
- [ ] Báo cáo cho lãnh đạo phản ánh residual risk và giới hạn bằng chứng.
- [ ] Chương trình có cơ chế cải tiến khi audit, incident hoặc framework phiên bản mới xuất hiện.

## 24. Ghi nhớ

- **Control framework là cấu trúc tổ chức mục tiêu và các biện pháp kiểm soát**, giúp tổ chức quản lý rủi ro bảo mật nhất quán.
- Framework **không đồng nghĩa** security policy, standard, catalog, checklist, công cụ hay chứng nhận; mỗi thứ giữ một vai trò khác nhau.
- Không có một framework tốt nhất cho mọi tổ chức: phải **chọn và tailor theo tài sản, rủi ro, nghĩa vụ, thẩm quyền và nguồn lực**.
- Một control thực chất cần **objective, scope, owner, implementation, criteria, test, evidence và reassessment trigger**.
- Phân biệt **design, implementation và operating effectiveness**; bằng chứng ở một lớp không tự chứng minh lớp còn lại.
- **Mapping nhiều framework** chỉ giúp truy vết; không chứng minh các requirement tương đương hoàn toàn hoặc control đã đạt.
- **Finding, ngoại lệ và residual risk** phải được quản trị trung thực, có remediation/retest và người phê duyệt đúng thẩm quyền.
- Trong security assurance, framework chỉ tạo giá trị khi được biến thành chuỗi sống **risk → requirement → control → test/evidence → assessment → decision → continuous improvement**.

