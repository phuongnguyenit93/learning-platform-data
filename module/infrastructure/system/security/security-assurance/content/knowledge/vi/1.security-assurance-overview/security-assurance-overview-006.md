# Assurance và compliance

Trong chương **Tổng quan security assurance**, hai khái niệm thường đi cùng nhau là **security assurance** (đảm bảo an toàn bảo mật dựa trên bằng chứng) và **security compliance** (tuân thủ các yêu cầu bảo mật). Chúng bổ trợ nhau nhưng trả lời hai câu hỏi khác nhau:

- **Compliance:** Hệ thống, tổ chức và quy trình có đáp ứng các nghĩa vụ, tiêu chí hoặc chuẩn mực đã xác định hay không?
- **Assurance:** Có đủ bằng chứng đáng tin cậy để kết luận rằng các mục tiêu bảo mật đã đặt ra thực sự được đáp ứng, trong một phạm vi và khoảng thời gian xác định hay không?

Bài học thuộc phạm vi **SECURITY_SECURITY_ASSURANCE**: tổ chức việc đánh giá bảo mật có bằng chứng từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, xử lý phát hiện và giám sát liên tục trong phát triển, vận hành.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa assurance, compliance, security control, assessment và audit.
2. Nhận diện nguồn yêu cầu tuân thủ và phân biệt yêu cầu bắt buộc với việc tự nguyện áp dụng framework.
3. Xây dựng chuỗi lập luận **mục tiêu → rủi ro → yêu cầu → control → kiểm thử → bằng chứng → kết luận**.
4. Đánh giá bằng chứng về **thiết kế**, **triển khai** và **hiệu quả vận hành** của một control.
5. Xử lý kết quả không đạt, ngoại lệ và thay đổi hệ thống bằng một quy trình assurance liên tục.

## 2. Assurance và compliance là gì?

### 2.1. Security assurance

**Security assurance** là hoạt động xây dựng và duy trì mức độ tin cậy hợp lý rằng hệ thống đáp ứng các mục tiêu bảo mật đã định. Mức độ tin cậy đó phải có **lập luận rõ ràng** và **bằng chứng có thể kiểm tra**.

Ví dụ, một nền tảng học trực tuyến đặt mục tiêu: *Chỉ nhân sự được cấp quyền mới có thể truy cập giao diện quản trị production*. Câu khẳng định “chúng tôi có quy định phân quyền” chưa đủ để tạo assurance. Cần chứng minh bằng cách kiểm tra các quyền đang tồn tại, cấu hình xác thực, quá trình phê duyệt, nhật ký truy cập, hoạt động thu hồi quyền và kết quả thử truy cập trái phép.

Assurance luôn gắn với các giới hạn:

- **Phạm vi:** Dịch vụ nào, môi trường nào, tài khoản nào, dữ liệu nào được xem xét?
- **Thời điểm hoặc kỳ đánh giá:** Bằng chứng phản ánh cấu hình ở một thời điểm hay hoạt động suốt một giai đoạn?
- **Mục tiêu và tiêu chí:** Thế nào là “đạt”? Ai phê duyệt tiêu chí đó?
- **Giả định và rủi ro còn lại:** Những thành phần bên ngoài, trường hợp ngoại lệ hoặc phương thức tấn công nào chưa được bao phủ?

Vì vậy, assurance không đồng nghĩa với cam kết “hệ thống an toàn tuyệt đối”. Một báo cáo assurance tốt phải chỉ ra **kết luận có thể khẳng định đến đâu**, **dựa trên điều gì** và **điều gì chưa được kiểm chứng**.

### 2.2. Security compliance

**Security compliance** là trạng thái và quá trình đáp ứng một tập hợp yêu cầu đã được xác định. Tập yêu cầu có thể đến từ:

- **Pháp luật và quy định quản lý:** Áp dụng tùy quốc gia, lĩnh vực, loại dữ liệu và hoạt động xử lý.
- **Hợp đồng và cam kết với khách hàng/đối tác:** Ví dụ nghĩa vụ bảo vệ dữ liệu, thời hạn báo cáo sự cố hay quyền được kiểm toán.
- **Tiêu chuẩn, bộ tiêu chí hoặc framework mà tổ chức chọn áp dụng:** Ví dụ ISO/IEC 27001, PCI DSS, SOC 2 Trust Services Criteria, NIST CSF.
- **Chính sách, tiêu chuẩn kỹ thuật và quy trình nội bộ:** Ví dụ quy định tất cả tài khoản đặc quyền production phải bật MFA.

Không phải framework nào cũng tự động là nghĩa vụ pháp lý hay có cơ chế chứng nhận giống nhau. Chẳng hạn, **ISO/IEC 27001** đặt các yêu cầu cho hệ thống quản lý an toàn thông tin (ISMS) và có cơ chế chứng nhận theo phạm vi; **SOC 2** là hình thức báo cáo xác nhận của kiểm toán viên về các kiểm soát liên quan đến Trust Services Criteria, thường phân biệt **Type I** (thiết kế tại một thời điểm) và **Type II** (thiết kế cùng hiệu quả vận hành trong một giai đoạn); **PCI DSS** đưa ra các yêu cầu cho môi trường dữ liệu chủ thẻ trong phạm vi áp dụng; **NIST CSF** giúp cấu trúc và quản trị rủi ro an ninh mạng. Việc áp dụng hay chứng minh đáp ứng mỗi bộ tiêu chí phụ thuộc phạm vi, mục đích và nghĩa vụ cụ thể của tổ chức.

Compliance phải trả lời được: **Yêu cầu nào**, **áp dụng cho đối tượng nào**, **ai chịu trách nhiệm**, **đánh giá bằng tiêu chí gì**, **bằng chứng nào**, **kết quả ra sao**.

### 2.3. So sánh theo câu hỏi cần trả lời

| Khía cạnh | Assurance | Compliance |
|---|---|---|
| Câu hỏi trọng tâm | Có cơ sở đáng tin cậy để tin hệ thống đạt mục tiêu bảo mật không? | Có đáp ứng tập yêu cầu áp dụng không? |
| Điểm xuất phát | Mục tiêu bảo mật, tài sản, rủi ro, threat model, tiêu chí chấp nhận | Luật, hợp đồng, tiêu chuẩn, chính sách, bộ tiêu chí |
| Cách thực hiện | Phân tích, lập luận, thiết kế/kiểm thử control, xem xét bằng chứng, đánh giá rủi ro còn lại | Xác định nghĩa vụ, ánh xạ yêu cầu, thu thập bằng chứng, đánh giá và xử lý sai lệch |
| Đầu ra | Kết luận có điều kiện về mức độ tin cậy, giới hạn, khoảng trống bằng chứng | Tình trạng đạt/không đạt/tạm thời chưa xác định theo từng yêu cầu |
| Người dùng kết quả | Chủ sở hữu rủi ro, kỹ sư, lãnh đạo, khách hàng, assessor | Chủ sở hữu yêu cầu, GRC, kiểm toán, cơ quan quản lý, khách hàng |
| Nhịp đánh giá | Liên tục và khi rủi ro/hệ thống thay đổi | Theo chu kỳ đánh giá và mọi khi nghĩa vụ hoặc phạm vi thay đổi |

**Security control** là biện pháp kiểm soát rủi ro, chẳng hạn MFA, phân quyền tối thiểu, mã hóa, sao lưu, giám sát hoặc quy trình duyệt thay đổi. **Assessment** là hoạt động xem xét một hay nhiều control dựa trên tiêu chí và bằng chứng. **Audit** là hình thức đánh giá có quy trình, phạm vi và yêu cầu khách quan/độc lập thích hợp; audit có thể đóng góp bằng chứng assurance nhưng không thay thế toàn bộ hoạt động kỹ thuật, vận hành và quản trị rủi ro.

## 3. Quan hệ giữa hai khái niệm

Compliance thường cung cấp các **tiêu chí cần đạt**, còn assurance đánh giá **mức độ đáng tin của lời khẳng định đã đạt**. Một tổ chức có thể lưu đủ tài liệu để vượt qua một đợt rà soát hình thức nhưng vẫn vận hành control kém. Ngược lại, một hệ thống có thể có biện pháp kỹ thuật hiệu quả cho một rủi ro nhất định nhưng vẫn vi phạm nghĩa vụ lưu hồ sơ, báo cáo hoặc điều khoản hợp đồng.

| | Assurance cao trong phạm vi được đánh giá | Assurance thấp trong phạm vi được đánh giá |
|---|---|---|
| **Đáp ứng yêu cầu compliance** | Control đáp ứng tiêu chí và có bằng chứng vận hành đáng tin | Hồ sơ có vẻ đạt nhưng thiếu kiểm thử, bằng chứng cũ hoặc phạm vi kiểm tra hẹp |
| **Chưa đáp ứng yêu cầu compliance** | Có bằng chứng tốt cho một số mục tiêu bảo mật, song vẫn có nghĩa vụ chưa được đáp ứng | Vừa thiếu chứng minh hiệu quả bảo mật, vừa còn yêu cầu chưa đạt |

Ma trận trên chỉ mô tả hai chiều đánh giá. “Assurance cao” không xóa nghĩa vụ compliance chưa hoàn thành; “compliant” không chứng minh hệ thống không còn lỗ hổng.

Ví dụ: Chính sách yêu cầu rà soát quyền quản trị mỗi quý. Việc có biên bản ký duyệt chứng minh một bước quy trình đã diễn ra; muốn tăng assurance cần kiểm tra danh sách tài khoản thực tế, quyền thừa, các trường hợp bị thu hồi, thời gian xử lý và khả năng tài khoản bị bỏ sót. **Bằng chứng về việc thực hiện một thủ tục khác với bằng chứng thủ tục đó đạt mục tiêu bảo mật.**

## 4. Chuỗi truy vết từ rủi ro đến bằng chứng

Mỗi kết luận assurance nên được truy vết về yêu cầu, control và bằng chứng cụ thể:

~~~mermaid
flowchart TD
    A["Tài sản, bối cảnh và mục tiêu bảo mật"] --> B["Đe dọa, rủi ro và yêu cầu"]
    B --> C["Thiết kế control và tiêu chí đạt"]
    C --> D["Triển khai control vào hệ thống/quy trình"]
    D --> E["Kiểm thử, giám sát và thu thập bằng chứng"]
    E --> F{"Bằng chứng đủ và control đạt?"}
    F -->|Có| G["Kết luận assurance có phạm vi và giới hạn"]
    F -->|Không| H["Ghi nhận phát hiện, khắc phục hoặc xử lý rủi ro"]
    H --> D
    G --> I["Theo dõi thay đổi và tái đánh giá"]
    I --> B
~~~

Trong mô hình **Claim–Argument–Evidence (CAE)**:

- **Claim (luận điểm):** Điều cụ thể cần khẳng định, ví dụ “Truy cập đặc quyền vào production được xác thực nhiều yếu tố”.
- **Argument (lập luận):** Vì sao các control và phép kiểm thử đã chọn là cơ sở hợp lý để chấp nhận luận điểm.
- **Evidence (bằng chứng):** Dữ liệu và kết quả có thể kiểm tra, ví dụ cấu hình identity provider, danh sách tài khoản, nhật ký xác thực và kết quả kiểm thử truy cập.

Một claim tốt phải có **chủ thể, phạm vi, thời gian, tiêu chí**, tránh lời hứa mơ hồ như “Hệ thống an toàn”. Chuỗi CAE có thể phân rã claim lớn thành các claim nhỏ: cấp quyền đúng, yêu cầu MFA, phát hiện sử dụng bất thường, thu hồi quyền đúng hạn.

Khi cùng một control đáp ứng nhiều yêu cầu từ các framework khác nhau, hãy liên kết chúng trong một **control inventory** và dẫn về cùng nhóm bằng chứng nguồn. Cách này giảm thu thập trùng lặp nhưng vẫn cần kiểm tra từng yêu cầu có điều kiện hoặc phạm vi riêng.

## 5. Ví dụ xuyên suốt: bảo vệ truy cập quản trị

Giả sử nền tảng học trực tuyến có API và giao diện quản trị chứa thông tin người học. Một mối đe dọa là kẻ tấn công chiếm được tài khoản nhân sự rồi truy cập dữ liệu hoặc thay đổi quyền. Tổ chức đặt ra mục tiêu: **Chỉ người được phê duyệt mới có quyền quản trị production, và mọi lần đăng nhập đặc quyền phải dùng MFA.**

Các giá trị trong ví dụ sau là **tiêu chí nội bộ minh họa**, không phải ngưỡng bắt buộc của một tiêu chuẩn cụ thể.

| Mắt xích | Nội dung của ví dụ |
|---|---|
| Tài sản và rủi ro | Giao diện admin, IAM và dữ liệu người học; rủi ro truy cập trái phép, thay đổi dữ liệu |
| Yêu cầu bảo mật | Tài khoản đặc quyền phải được phê duyệt, có MFA; quyền bị thu hồi trong vòng 24 giờ sau khi chấm dứt nhu cầu theo chính sách nội bộ |
| Control phòng ngừa | SSO/MFA bắt buộc, RBAC theo quyền tối thiểu, quy trình duyệt cấp quyền |
| Control phát hiện | Log đăng nhập và cấp/thu hồi quyền; cảnh báo đăng nhập bất thường; rà soát quyền định kỳ |
| Control khắc phục | Vô hiệu hóa phiên/tài khoản, thu hồi token, xử lý sự cố và rà soát quyền sau sự cố |
| Kiểm thử | Đối chiếu tài khoản thực tế với danh sách phê duyệt; thử đăng nhập khi thiếu MFA; kiểm tra mẫu các sự kiện thu hồi quyền |
| Bằng chứng | Export cấu hình IAM, danh sách principal/role, ticket phê duyệt, log đăng nhập, ticket offboarding, kết quả test có ngày và người thực hiện |
| Kết luận | Đạt hoặc chưa đạt theo từng tiêu chí; ghi rõ môi trường, tài khoản, thời kỳ kiểm tra, ngoại lệ và giới hạn của mẫu |

Ví dụ một hồ sơ claim có thể được trình bày như sau:

~~~yaml
claim_id: SA-ACCESS-01
claim: "Truy cập quản trị production yêu cầu MFA và quyền hợp lệ"
scope:
  - "Production admin console"
  - "Tài khoản nhân sự và tài khoản đặc quyền qua IdP trung tâm"
period: "01/09 - 30/11 (kỳ đánh giá minh họa)"
criteria:
  - "100% tài khoản đặc quyền thuộc phạm vi được kiểm tra có MFA bắt buộc"
  - "Không có tài khoản không được phê duyệt còn quyền quản trị"
controls:
  - "SSO + MFA enforcement"
  - "RBAC + approval workflow"
evidence:
  - "Bản xuất cấu hình IdP có dấu thời gian"
  - "Danh sách tài khoản/quyền và ticket phê duyệt"
  - "Log đăng nhập, kết quả thử đăng nhập không có MFA"
limitations:
  - "Không bao gồm tài khoản break-glass; được đánh giá riêng"
owner: "Identity & Access Management"
~~~

Nếu có tài khoản **break-glass** để dùng trong tình huống khẩn cấp, phải xác định chúng thuộc phạm vi nào, được quản lý bằng control bù trừ nào, ai phê duyệt và bằng chứng được kiểm tra ra sao. Không nên loại tài khoản ngoại lệ khỏi phép đo mà không nêu rõ.

### Ba lớp đánh giá một control

1. **Thiết kế (design):** Control có hợp lý để xử lý rủi ro không? Ví dụ chính sách yêu cầu MFA nhưng tài khoản service không hỗ trợ xác thực tương tác; cần xác định cơ chế bảo vệ thích hợp cho loại tài khoản đó.
2. **Triển khai (implementation):** Control có được cấu hình đúng trong hệ thống đang vận hành không? Ví dụ chính sách MFA có áp dụng cho tất cả role admin và mọi đường truy cập liên quan không?
3. **Hiệu quả vận hành (operating effectiveness):** Control có hoạt động nhất quán trong kỳ đánh giá không? Ví dụ tài khoản mới được thêm đúng quy trình, ngoại lệ được xử lý, truy cập không có MFA bị từ chối, quyền được thu hồi đúng thời hạn.

Một ảnh chụp màn hình trang cấu hình MFA có thể hỗ trợ lớp **triển khai tại thời điểm chụp**, nhưng không đủ tự chứng minh hoạt động liên tục suốt ba tháng. Cần kết hợp dữ liệu cấu hình, các thay đổi, log, mẫu hồ sơ phê duyệt và kiểm thử thích hợp.

## 6. Chất lượng bằng chứng quyết định chất lượng assurance

Không phải mọi bằng chứng đều có sức thuyết phục ngang nhau. Khi đánh giá, kiểm tra ít nhất sáu thuộc tính:

1. **Liên quan:** Bằng chứng chứng minh đúng claim/control nào, hay chỉ mô tả chính sách chung?
2. **Đúng phạm vi:** Có bao phủ các tài khoản, dịch vụ, khu vực triển khai, môi trường và nhà cung cấp thuộc phạm vi không?
3. **Đúng thời kỳ:** Thời gian thu thập có trùng kỳ cần đánh giá? Có dữ liệu về hoạt động lặp lại hay chỉ một ảnh chụp?
4. **Tính toàn vẹn và nguồn gốc:** Nguồn tạo, người trích xuất, dấu thời gian, quyền truy cập và khả năng chỉnh sửa có truy vết được không?
5. **Đủ độ phủ và tính đại diện:** Nếu chọn mẫu, có nêu tổng thể, cách lấy mẫu, số lượng, ngoại lệ và giới hạn suy rộng không?
6. **Khả năng tái kiểm tra:** Người độc lập có thể lặp lại phép kiểm thử hoặc đối chiếu kết quả từ nguồn dữ liệu ban đầu không?

| Bằng chứng | Có thể chứng minh | Chưa thể kết luận chỉ từ bằng chứng đó |
|---|---|---|
| Chính sách phân quyền được phê duyệt | Tổ chức đã đặt quy tắc, xác định trách nhiệm | Quy tắc đang được thực thi đúng |
| Ảnh chụp cấu hình MFA | Một phần cấu hình ở thời điểm chụp | Mọi tài khoản và mọi luồng đăng nhập đều chịu chính sách đó trong cả kỳ |
| Danh sách user/role trích xuất từ IAM | Trạng thái phân quyền của hệ thống được trích xuất | Tất cả quyền đã có phê duyệt và không có tuyến truy cập ngoài IAM |
| Log, ticket phê duyệt và offboarding | Một chuỗi thao tác thực tế có thời gian/đối tượng cụ thể | Mọi thao tác đều đúng nếu chưa kiểm tra tính đầy đủ và lấy mẫu |
| Kết quả thử truy cập không có MFA | Một hành vi từ chối truy cập đã được quan sát | Không tồn tại đường bypass khác ngoài các tình huống đã thử |
| Báo cáo pentest | Các lỗ hổng/kịch bản đã được kiểm thử trong phạm vi và thời điểm xác định | Toàn bộ hệ thống không có lỗ hổng hoặc tất cả control đều hiệu quả |

Bằng chứng nên được lưu với **mã control, nguồn gốc, thời gian, phạm vi, phiên bản, người sở hữu và quyền truy cập**. Với log hoặc dữ liệu người dùng nhạy cảm, lưu theo nguyên tắc tối thiểu cần thiết; có thể làm mờ dữ liệu cá nhân trong bản cung cấp cho người đánh giá nhưng vẫn giữ đường dẫn kiểm chứng được tới nguồn được kiểm soát.

Một nhận định “**không thấy lỗi**” cần phân biệt với “**đã kiểm tra và không tìm thấy lỗi trong phạm vi phép thử**”. Nếu thiếu log, không lấy được cấu hình hoặc không xác định được tổng thể tài khoản, kết luận thích hợp là **chưa đủ bằng chứng** chứ không tự mặc định “đạt”.

## 7. Từ yêu cầu compliance đến bộ control có thể kiểm chứng

Một dự án thực tế có thể chịu nhiều nguồn yêu cầu cùng lúc. Để tránh đánh giá lặp lại và bỏ sót, thực hiện các bước:

**Bước 1 — Xác định nguồn và tính áp dụng.** Ghi rõ văn bản/bộ tiêu chí, phiên bản, hiệu lực, phạm vi và căn cứ tại sao yêu cầu áp dụng. Tách yêu cầu pháp lý/hợp đồng bắt buộc với mục tiêu tự nguyện theo framework.

**Bước 2 — Chuyển thành yêu cầu kiểm chứng được.** Ví dụ “kiểm soát truy cập phù hợp” quá rộng; có thể phân rã thành quy tắc cấp quyền, xác thực, rà soát quyền, thu hồi quyền, giám sát và thời hạn xử lý.

**Bước 3 — Ánh xạ vào control hiện có.** Gán mã control ổn định, người sở hữu, hệ thống áp dụng, thiết kế control và cách vận hành. Một control có thể phục vụ nhiều yêu cầu, nhưng phải giữ quan hệ truy vết hai chiều.

**Bước 4 — Định nghĩa test và bằng chứng trước kỳ đánh giá.** Nêu tiêu chí đạt, nguồn bằng chứng, phương pháp đối chiếu, cách kiểm tra ngoại lệ, chu kỳ đánh giá và ai đủ độc lập để đánh giá.

**Bước 5 — Kết luận theo từng yêu cầu.** Có thể dùng trạng thái **đạt**, **không đạt**, **chưa đủ bằng chứng**, **không áp dụng** (kèm lý do). Các trạng thái này là cách quản lý nội bộ; khi nộp cho auditor hoặc cơ quan bên ngoài cần dùng đúng phân loại của chương trình đánh giá tương ứng.

Ví dụ bảng truy vết rút gọn:

| Mã yêu cầu nội bộ | Nguồn/tiêu chí áp dụng | Control | Phép kiểm thử | Bằng chứng | Trạng thái |
|---|---|---|---|---|---|
| REQ-IAM-01 | Chính sách truy cập production | CTRL-IAM-01: MFA cho admin | Đối chiếu danh sách admin, kiểm tra enforcement | IAM export, test report, log | Đạt nếu đủ độ phủ |
| REQ-IAM-02 | Chính sách cấp/thu hồi quyền | CTRL-IAM-02: approval và offboarding | Đối chiếu quyền với phê duyệt, kiểm tra hạn xử lý | Role export, ticket, HR/IAM events | Chờ xác minh mẫu |
| REQ-LOG-01 | Quy định giám sát nội bộ | CTRL-LOG-01: thu thập và cảnh báo | Thử sự kiện, kiểm tra đường đi và xử lý cảnh báo | Log, rule, incident ticket | Không đạt nếu không phát cảnh báo |

Không nên sao chép nguyên một control list của framework rồi coi đó là bảo đảm đủ. Mối đe dọa thực tế của sản phẩm có thể đòi hỏi thêm control hoặc phép thử mà checklist không diễn đạt chi tiết.

## 8. Chương trình assurance liên tục trong phát triển và vận hành

Security assurance bền vững cần kết nối hoạt động thiết kế, build, release và vận hành:

| Giai đoạn | Hoạt động assurance | Dạng bằng chứng thường gặp |
|---|---|---|
| Phân tích và thiết kế | Phân loại dữ liệu, threat modeling, đánh giá rủi ro, chốt yêu cầu | Risk register, threat model, security requirements |
| Phát triển | Review thiết kế/code, SAST, kiểm tra dependency, secret scanning | Kết quả scan có phiên bản, review và cách xử lý phát hiện |
| Build và triển khai | Kiểm tra cấu hình/IaC, policy-as-code, kiểm soát thay đổi | Pipeline result, artifact/version, approval, IaC diff |
| Trước release hoặc thay đổi lớn | Kiểm thử xác thực/phân quyền, DAST/pentest phù hợp rủi ro, kiểm chứng khắc phục | Test report, scope, evidence, issue linkage, retest |
| Vận hành | Giám sát sự kiện, quản lý lỗ hổng, rà soát quyền, kiểm thử khôi phục | Telemetry, ticket, access review, kết quả restore drill |
| Đánh giá và cải tiến | Control assessment, internal audit, rà soát ngoại lệ, cập nhật nghĩa vụ | Control register, audit finding, CAPA, quyết định xử lý rủi ro |

**Continuous assurance** không có nghĩa là chạy mọi bài kiểm thử liên tục. Mỗi nguồn bằng chứng cần một tần suất phù hợp với tốc độ thay đổi và mức rủi ro: một số kiểm tra có thể tự động trên mỗi commit/deploy; số khác theo ngày, tháng, quý hoặc khi có thay đổi đáng kể.

Một số **trigger cần tái đánh giá** là: thêm cloud account hoặc môi trường production, thay identity provider, thay đổi luồng truy cập đặc quyền, mở rộng loại dữ liệu xử lý, thay nhà cung cấp trọng yếu, thay yêu cầu pháp lý/hợp đồng, sự cố bảo mật hoặc phát hiện control không còn hoạt động.

Tự động hóa thu thập bằng chứng có thể giảm công sức và tăng tính kịp thời; nhưng pipeline báo “pass” cũng cần được kiểm tra **đang kiểm tra điều gì**, **có bao phủ đúng phạm vi không**, **có thể bị bỏ qua không** và **có ai xử lý khi nó fail không**.

## 9. Audit, phát hiện và khắc phục

Một cuộc audit hoặc control assessment hữu ích cần thống nhất từ đầu về **mục tiêu, tiêu chí, phạm vi, kỳ đánh giá, người thực hiện, phương pháp chọn mẫu và cách báo cáo**. Người đánh giá xem xét hồ sơ, phỏng vấn, quan sát và kiểm thử tùy loại control. Tính độc lập phù hợp giúp giảm thiên lệch tự đánh giá; tuy nhiên kết luận vẫn bị giới hạn bởi bằng chứng và phạm vi thực tế.

Khi phát hiện control không đạt hoặc bằng chứng không đủ:

1. **Ghi nhận finding rõ ràng:** Yêu cầu/claim nào bị ảnh hưởng, hiện trạng quan sát, bằng chứng, phạm vi, rủi ro và mức độ nghiêm trọng.
2. **Tìm nguyên nhân gốc:** Ví dụ IAM policy có nhưng một ứng dụng đi qua cơ chế đăng nhập riêng; chỉ bật thêm MFA trên trang chính chưa xử lý hết.
3. **Xác định chủ sở hữu và biện pháp:** Có thể sửa cấu hình, thay quy trình, thu hồi quyền, bổ sung detection, hoặc control bù trừ trong thời gian chuyển tiếp.
4. **Theo dõi hạn hoàn thành và ngoại lệ:** Ghi quyết định, người phê duyệt, thời hạn, lý do và rủi ro còn lại. Việc chấp nhận rủi ro cần đúng thẩm quyền và không tự miễn nghĩa vụ bắt buộc.
5. **Retest rồi mới đóng:** Xác nhận biện pháp đã triển khai, hoạt động trong phạm vi phát hiện và không tạo lỗi mới; liên kết evidence mới với finding cũ.
6. **Cập nhật assurance:** Nếu control thất bại, điều chỉnh hoặc rút lại claim có liên quan cho đến khi có bằng chứng mới đủ sức hỗ trợ.

Ví dụ, phát hiện “Hai tài khoản admin vẫn có thể đăng nhập mà không dùng MFA” không nên được đóng chỉ bằng ticket “đã bật MFA”. Cần kiểm thử lại đúng hai tài khoản, kiểm tra những tài khoản tương tự và xác nhận cấu hình không bị revert sau thay đổi.

## 10. Đo lường để biết chương trình có hiệu quả hay không

Các chỉ số dưới đây giúp quản lý tiến độ và chất lượng assurance; chúng **không thay cho kết luận bảo mật**:

| Chỉ số | Cách đọc hữu ích | Cảnh báo khi diễn giải |
|---|---|---|
| Tỷ lệ yêu cầu có mapping tới control và chủ sở hữu | Cho biết độ bao phủ quản trị | Có mapping không có nghĩa control hiệu quả |
| Tỷ lệ control có evidence hợp lệ trong kỳ | Theo dõi độ kịp thời/đầy đủ của chứng cứ | Evidence “tồn tại” có thể vẫn không đúng phạm vi |
| Tỷ lệ phép kiểm thử đạt theo mức rủi ro | Phân biệt chất lượng kiểm soát ở khu vực quan trọng | “100% pass” vô nghĩa nếu test quá dễ hoặc bao phủ thấp |
| Số finding quá hạn và thời gian khắc phục theo mức độ | Thể hiện khả năng xử lý vấn đề | Đóng ticket chưa chắc đã retest |
| Số ngoại lệ còn mở và tuổi ngoại lệ | Cho thấy rủi ro tồn đọng | Có phê duyệt không đồng nghĩa rủi ro đã biến mất |
| Tỷ lệ thay đổi quan trọng được tái đánh giá | Kiểm tra assurance có theo kịp thay đổi không | Cần định nghĩa rõ thế nào là thay đổi quan trọng |

Theo dõi xu hướng theo thời gian và liên hệ chỉ số với tài sản quan trọng, kịch bản đe dọa và các phát hiện thực tế sẽ hữu ích hơn tổng hợp một “điểm số an toàn” không giải thích được.

## 11. Các ngộ nhận thường gặp

**“Đạt chứng nhận hoặc qua audit tức là sản phẩm không có lỗ hổng.”** Không đúng. Chứng nhận/báo cáo đánh giá có phạm vi, thời kỳ, tiêu chí và giới hạn nhất định; chúng không loại trừ lỗ hổng mới hay rủi ro ngoài phạm vi.

**“Có chính sách và screenshot là đủ chứng minh control.”** Không đủ cho claim về hiệu quả vận hành. Phải kiểm tra việc thực thi, tính đầy đủ của tổng thể và bằng chứng trong kỳ liên quan.

**“Một pentest thay thế được mọi yêu cầu compliance.”** Không. Pentest đánh giá một tập kịch bản kỹ thuật, còn yêu cầu compliance có thể bao gồm tổ chức, quy trình, trách nhiệm, chứng từ và nghĩa vụ khác.

**“Risk acceptance có thể hợp thức hóa mọi trường hợp không tuân thủ.”** Không. Chấp nhận rủi ro nội bộ không tự xóa yêu cầu của luật, hợp đồng hoặc tiêu chí bắt buộc.

**“Một control đã pass thì sẽ pass mãi.”** Không. Hệ thống, nhân sự, tài sản, dữ liệu và cấu hình thay đổi. Claim cần được tái đánh giá khi bằng chứng hết hiệu lực hoặc xuất hiện thay đổi có ý nghĩa.

**“Không phát hiện lỗi nghĩa là đã chứng minh an toàn.”** Không. Kết luận chỉ có giá trị trong phương pháp kiểm tra, phạm vi, độ phủ và mức tin cậy cụ thể.

## 12. Bài tập áp dụng

**Tình huống:** Nhóm vận hành nói rằng “Nền tảng đã compliant vì có quy trình sao lưu hằng ngày”. Trong ba tháng gần nhất, không ai thử khôi phục dữ liệu và một số job sao lưu thất bại không tạo cảnh báo.

Hãy tự đặt bốn câu hỏi:

1. **Claim:** Nhóm đang muốn khẳng định điều gì: “job sao lưu được cấu hình” hay “có thể phục hồi dữ liệu trong thời gian chấp nhận được”?
2. **Tiêu chí:** Tập yêu cầu nào thực sự áp dụng? Phạm vi dữ liệu, tần suất sao lưu, RPO/RTO và quy trình thử khôi phục đã được tổ chức xác định chưa?
3. **Bằng chứng:** Cần bổ sung những gì ngoài tài liệu quy trình: log thành công/thất bại, phạm vi dữ liệu được backup, cảnh báo, kết quả restore test, thời gian phục hồi?
4. **Xử lý:** Ai khắc phục cảnh báo bị thiếu, khi nào retest, rủi ro còn lại do ai chấp nhận và kết luận assurance cần thay đổi ra sao?

Một câu trả lời hợp lý là: **chưa đủ bằng chứng để khẳng định khả năng phục hồi**, đồng thời đã có dấu hiệu control giám sát sao lưu hoạt động không hiệu quả. Cần xác minh nghĩa vụ compliance cụ thể, sửa nguyên nhân, thử restore trong phạm vi phù hợp và lưu lại kết quả; không nên suy diễn “compliant” từ sự tồn tại của một quy trình.

## 13. Ghi nhớ

- **Compliance xác định và kiểm tra nghĩa vụ**; **assurance tạo niềm tin có căn cứ về mục tiêu bảo mật**.
- Mọi kết luận nên nêu rõ **claim, phạm vi, tiêu chí, thời gian, bằng chứng, giới hạn và rủi ro còn lại**.
- Đánh giá control phải vượt qua việc “có tài liệu” để xem xét **thiết kế, triển khai và hiệu quả vận hành**.
- Kiểm thử, audit, khắc phục finding và giám sát thay đổi phải tạo thành **vòng lặp liên tục** trong cả phát triển lẫn vận hành.
