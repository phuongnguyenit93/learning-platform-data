# Phạm vi ngoại lệ (Exception Scope): giới hạn rõ ràng để quản trị rủi ro bảo mật

**Phạm vi ngoại lệ (exception scope)** là tập hợp **những đối tượng, yêu cầu, hành vi và điều kiện cụ thể** mà một quyết định cho phép **tạm thời không đáp ứng đầy đủ** một security policy, standard, baseline hoặc control được áp dụng. Phạm vi còn phải chỉ ra **ngoại lệ có hiệu lực từ khi nào đến khi nào**, những kiểm soát nào vẫn bắt buộc, giới hạn rủi ro được chấp nhận và điều kiện khiến quyết định phải được xem xét lại hoặc chấm dứt.

Trong chương **Exception management** của module **SECURITY_SECURITY_ASSURANCE**, phạm vi ngoại lệ là một phần thiết yếu của security assurance có bằng chứng. Nó giúp liên kết quyết định của risk owner với yêu cầu bảo mật, phân tích rủi ro, security controls, bằng chứng vận hành, audit findings và hành động khắc phục. Một ngoại lệ chỉ đáng quản lý khi người kiểm tra có thể trả lời chính xác:

> **Control nào được ngoại lệ, áp dụng cho tài sản và hành vi nào, trong môi trường/thời kỳ nào, với biện pháp bảo vệ nào, do ai chấp thuận, và làm thế nào phát hiện khi ngoại lệ vượt ra ngoài ranh giới?**

Phạm vi càng mơ hồ thì nguy cơ **ngoại lệ lan rộng ngoài dự kiến (scope creep)** càng lớn. “Tạm thời không cần vá cho hệ thống cũ” là một mô tả yếu. “Cho phép trì hoãn áp dụng bản vá X tới ngày D chỉ trên các host được liệt kê, thuộc dịch vụ Y, do phụ thuộc nhà cung cấp Z; cấm mở thêm host, duy trì network restrictions và monitoring; hết hạn phải triển khai bản vá hoặc có quyết định đánh giá lại” là mô tả có thể kiểm soát và kiểm toán.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Định nghĩa phạm vi ngoại lệ và giải thích vì sao phải xác định nó trước khi phê duyệt.
2. Phân biệt **ngoại lệ chính sách/control**, **sai lệch chưa được duyệt**, **chấp nhận rủi ro**, **loại trừ phạm vi đánh giá**, **miễn trừ hợp lệ theo một quy tắc** và **khắc phục finding**.
3. Mô tả ranh giới ngoại lệ theo control, tài sản, môi trường, danh tính, dữ liệu, thao tác, thời gian, phụ thuộc, mức rủi ro và điều kiện áp dụng.
4. Viết một **scope statement** có thể kiểm tra, kèm danh mục đối tượng, phần không bao gồm và giới hạn không được vượt qua.
5. Đề xuất cơ chế phê duyệt, phân quyền, biện pháp bù trừ, giám sát và điều kiện chấm dứt ngoại lệ.
6. Thiết kế kiểm tra scope drift, tái đánh giá khi thay đổi và quy trình gia hạn không tự động.
7. Đọc một bản ghi ngoại lệ theo bằng chứng để xác định còn hợp lệ, bị vượt phạm vi hay phải escalated.
8. Áp dụng kiến thức vào tình huống trì hoãn vá lỗi một số máy chủ production.

---

## 2. Phạm vi ngoại lệ là gì, và vì sao nó quan trọng?

Một tổ chức thường có chính sách chung, ví dụ:

- Mọi lỗ hổng có mức ưu tiên nhất định phải được xử lý theo thời hạn đã phê duyệt.
- Dịch vụ quản trị phải đáp ứng yêu cầu xác thực và phân quyền.
- Dữ liệu thuộc nhóm nhạy cảm phải được mã hóa khi lưu trữ/truyền theo chính sách.
- Các sự kiện an ninh bắt buộc phải được ghi log và lưu giữ.
- Những dịch vụ quan trọng phải được thử khả năng khôi phục theo mục tiêu được duyệt.

Thực tế có thể tồn tại một trường hợp ngoại lệ: một hệ thống nhà cung cấp cũ chưa thể áp dụng cấu hình mới ngay, việc vá một thư viện đòi hỏi thay đổi tương thích lớn, hoặc một yêu cầu logging cần thời gian để xử lý giới hạn của nền tảng. **Ngoại lệ là cơ chế quản trị sự sai khác có kiểm soát**, không phải cách làm cho một control chưa đạt thành đạt.

Phạm vi giúp tránh ba tình huống:

1. **Mở rộng ngoài ý định:** phê duyệt cho ba máy chủ nhưng đội vận hành hiểu là mọi máy cùng loại.
2. **Dùng sai ngữ cảnh:** phê duyệt ngoại lệ ở staging bị dùng để biện minh cho production.
3. **Tồn tại vô thời hạn:** một quyết định tạm thời không có hạn hoặc không có trigger rà soát trở thành trạng thái mặc định.

Khi giới hạn chính xác, tổ chức có thể đánh giá tác động thực tế, đặt compensating controls, theo dõi rủi ro còn lại và biết đúng thời điểm phải khắc phục hay ra quyết định mới.

### 2.1. Các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Liên hệ với phạm vi |
|---|---|---|
| **Policy/control exception** | Phê duyệt một sai khác cụ thể khỏi yêu cầu nội bộ đang áp dụng | Phải chỉ rõ yêu cầu, đối tượng, điều kiện, thời hạn và quyền phê duyệt |
| **Unapproved deviation** | Hệ thống không đạt yêu cầu nhưng chưa có quyết định hợp lệ | Không thể gọi là ngoại lệ được chấp thuận; cần xử lý, hạn chế rủi ro hoặc trình duyệt |
| **Risk acceptance** | Người có thẩm quyền chấp nhận rủi ro còn lại sau đánh giá | Có thể đi kèm ngoại lệ nhưng cần bản ghi quyết định rủi ro rõ ràng |
| **Compensating control** | Biện pháp thay thế giảm phần rủi ro tương ứng | Nằm trong **điều kiện bắt buộc** để ngoại lệ được duy trì, cần chứng minh hiệu lực |
| **Remediation / CAP** | Thay đổi để giải quyết vấn đề và nguyên nhân | Một ngoại lệ có thể tồn tại trong thời gian CAP được thực hiện |
| **Audit scope exclusion** | Một tài sản/quy trình không thuộc phạm vi cuộc kiểm toán | **Không phải** quyền bỏ thực hiện security control trên tài sản đó |
| **False positive** | Phát hiện sai sau khi đã kiểm tra bằng chứng | Có thể đóng finding sai; không cần ngoại lệ cho hành vi thực sự không vi phạm |
| **Not applicable** | Tiêu chí không áp dụng theo quy tắc và căn cứ cụ thể | Không nên tạo “ngoại lệ” để né một yêu cầu vốn không áp dụng |
| **Waiver / exemption** | Thuật ngữ miễn trừ tùy hệ thống quản trị | Phải xác nhận ý nghĩa, cấp quyền và giới hạn theo quy định tổ chức |

**Điểm quan trọng:** ngoại lệ do nội bộ phê duyệt **không tự cho phép vi phạm pháp luật, điều khoản hợp đồng hoặc yêu cầu bên ngoài không thể miễn trừ**. Trước khi phê duyệt, phải xác định bên nào thực sự có quyền cho phép sai khác và nghĩa vụ nào vẫn bắt buộc.

## 3. Phạm vi ngoại lệ là một tập giới hạn, không chỉ là tên hệ thống

Một mô hình hữu ích là xem phạm vi như sự kết hợp của các chiều:

\`\`\`text
Exception scope =
  Control / Requirement
  × Asset / Service / Resource
  × Environment / Location / Region
  × Identity / Role / Tenant
  × Operation / Data flow / Protocol
  × Data classification
  × Effective time window
  × Preconditions / Compensating controls
  × Approved risk boundary
\`\`\`

Dấu nhân trong mô hình là cách **minh họa sự kết hợp điều kiện**, không phải phép tính đo rủi ro. Không phải mọi ngoại lệ đều cần điền từng chiều; tuy nhiên, mọi chiều **có khả năng làm thay đổi tác động hoặc quyền phê duyệt** đều phải được làm rõ.

Chẳng hạn ngoại lệ cho việc trì hoãn vá lỗi trên một cụm backend nên nêu danh sách workload, namespace/account, môi trường, version, nhóm tài sản có liên quan, ngày hết hạn và các điều kiện cách ly mạng. Ngoại lệ cho một role thì cần nêu chính xác principal, loại quyền, hành vi, thời gian và những resource mà role được phép truy cập.

### 3.1. Định nghĩa ranh giới bằng cách bao gồm và loại trừ

Một phạm vi tốt luôn có hai mặt:

- **In scope:** danh sách chính xác những gì được phép sai khác.
- **Explicitly out of scope:** những gì **không** được phép suy rộng, đặc biệt tài sản kế cận, region khác, production khi chỉ duyệt non-production, role mới, hệ thống mới và control khác.

Ví dụ:

> Ngoại lệ EX-214 chỉ áp dụng cho việc trì hoãn vá phiên bản package P của các host \`APP-L01\` và \`APP-L02\`, thuộc dịch vụ thanh toán cũ tại production region A, đến 18:00 UTC ngày 31/12/2026. Không áp dụng cho các host mới, máy ở region B, thư viện khác, tài khoản quản trị hoặc thay đổi yêu cầu MFA. Điều kiện bắt buộc: chặn inbound không cần thiết, giám sát truy cập đặc quyền và có kế hoạch thử bản vá trước khi hết hạn.

Các tên, ngày và điều kiện trên là **giả định học tập**. Trong tình huống thực tế, cần dùng risk assessment và tiêu chí kỹ thuật đã được phê duyệt; không thể mặc định những biện pháp bù trừ được liệt kê là đủ để giảm mọi rủi ro của package P.

## 4. Xác định đúng control hoặc requirement được ngoại lệ

Một ngoại lệ phải tham chiếu tới **điều khoản cụ thể**, không chỉ chủ đề rộng như “security” hoặc “compliance”.

| Mô tả yếu | Mô tả có thể kiểm tra |
|---|---|
| “Ngoại lệ về IAM” | Ngoại lệ tạm thời cho yêu cầu access review hàng quý của nhóm service account X trong kỳ Y |
| “Ngoại lệ về vá lỗi” | Kéo dài hạn xử lý finding VULN-017 trên các asset A, B theo phiên bản SLA-SEC-02 |
| “Ngoại lệ mã hóa” | Sai khác cụ thể với yêu cầu at-rest encryption cho loại dữ liệu D tại storage resource R |
| “Ngoại lệ logging” | Trì hoãn áp dụng trường log F trong audit event của ứng dụng S đến ngày D |
| “Ngoại lệ DR” | Chưa đáp ứng mục tiêu diễn tập failover định kỳ theo control DR-TEST-03 trên dịch vụ W |

Một số điểm cần chú ý:

1. **Version của policy/standard:** yêu cầu áp dụng lúc nào, có thay đổi trong giai đoạn ngoại lệ không?
2. **Loại control:** preventive, detective, corrective; thiết kế, triển khai hay hiệu quả vận hành bị ảnh hưởng?
3. **Mức sai lệch:** hoàn toàn không đáp ứng hay chỉ một phần tiêu chí; trường nào, tính năng nào, thời hạn nào?
4. **Control liên quan:** ngoại lệ patch SLA không đồng nghĩa ngoại lệ logging, network access, IAM hoặc incident response.
5. **Phạm vi pháp lý/hợp đồng:** requirement nào là nội bộ, cái nào do bên ngoài bắt buộc và ai được quyền quyết định ngoại lệ?

Nên ghi rõ **không được ngoại lệ** điều gì để tránh “phê duyệt một phần nhưng hiểu thành miễn toàn bộ”.

## 5. Ranh giới tài sản và môi trường: asset scope

Phạm vi tài sản phải sử dụng **định danh có thể đối chiếu** với hệ thống thực, không chỉ tên người dùng đặt trong tài liệu.

Các định danh có thể gồm:

- Service/application ID, business capability, control owner.
- Cloud account/subscription/project và region.
- Cluster, namespace, workload, database, object store hoặc bucket ID.
- Host ID, image version, package/version, tag được quản lý.
- Endpoint/route, API version, data pipeline, integration hoặc vendor instance.
- Identity/role/service principal có thể ánh xạ tới control plane.
- Môi trường development, test, staging, production, DR site.

**Cẩn trọng với wildcard:** phạm vi \`app-*\` hoặc “mọi service kế thừa image X” dễ tự mở rộng khi có workload mới. Nếu phải dùng dynamic scope, cần có **rule được phê duyệt, giới hạn số lượng/độ nhạy cảm và phát hiện tài sản mới**. Mặc định an toàn hơn là **deny expansion** cho tới khi đánh giá tác động và phê duyệt điều chỉnh.

### 5.1. Đối chiếu với inventory

Một tài sản có thể được đổi tên, autoscale hoặc chuyển vùng. Vì vậy nên lưu:

- Danh sách asset snapshot tại thời điểm phê duyệt.
- Truy vấn/nguồn dùng xây population.
- Cơ chế xử lý khi asset được thay thế hoặc tăng thêm.
- Owner chịu trách nhiệm kiểm tra rằng danh sách hiện tại vẫn khớp phạm vi.
- Bằng chứng kiểm tra định kỳ và các trường hợp vượt ranh giới.

Ví dụ approval cho hai VM không tự động bao gồm hai VM mới tạo từ cùng image. Nếu ngoại lệ thực sự cần theo workload group, định nghĩa group bằng điều kiện cụ thể và cách giám sát việc mở rộng.

## 6. Ranh giới danh tính, vai trò và quyền thao tác

Với ngoại lệ liên quan truy cập, cần phân biệt **ai** và **được làm gì**.

| Chiều | Câu hỏi cần chốt |
|---|---|
| Identity | Principal/user/service account nào, định danh bất biến hay nhóm động? |
| Role/privilege | Quyền cụ thể nào được thay đổi? Có quyền kế thừa? |
| Resource | Dữ liệu, namespace, tài nguyên, tenant nào có thể truy cập? |
| Action | Read, write, export, deploy, administer hay rotate key? |
| Entry point | Đường đăng nhập, API, bastion, console, mạng nào nằm trong phạm vi? |
| Time | Truy cập theo phiên, theo ca trực hoặc thời hạn chính xác nào? |
| Oversight | Ai duyệt, ai giám sát, log nào được lưu? |
| Revocation | Cơ chế nào bảo đảm quyền ngoại lệ hết hiệu lực đúng hạn? |

Một ngoại lệ dành cho **service identity** không tự trở thành ngoại lệ MFA cho mọi **human administrator**. Đặc biệt với **break-glass** hoặc quyền khẩn cấp, phải ghi rõ điều kiện kích hoạt, người được ủy quyền, thời hạn ngắn, kiểm tra sau sử dụng và thu hồi; không cho phép biến quyền khẩn cấp thành đường truy cập thường xuyên.

Ngoại lệ đối với **một quyền** không có nghĩa mọi quyền bổ sung của cùng role đều hợp lệ. Việc tách action/resource giúp thực thi **least privilege** ngay trong phạm vi ngoại lệ.

## 7. Ranh giới dữ liệu và đường xử lý

Đối với hệ thống xử lý dữ liệu, cùng một service có thể lưu nhiều phân loại dữ liệu: dữ liệu công khai, dữ liệu nội bộ, dữ liệu cá nhân hoặc bí mật nghiệp vụ. Phạm vi ngoại lệ phải đủ chính xác để không vô tình bao gồm nhóm dữ liệu nhạy cảm hơn.

Ví dụ ngoại lệ logging cho **metadata của một batch job** không thể được diễn giải thành ngoại lệ ghi audit trail cho hành động truy cập **hồ sơ khách hàng**.

Các câu hỏi quan trọng:

- Dữ liệu thuộc lớp phân loại nào, owner là ai?
- Phạm vi bao gồm production data hay chỉ fixture/test data?
- Luồng xử lý nào: lưu trữ, truyền tải, export, backup, replication, analytics, third-party sharing?
- Có cross-border transfer, multi-region hoặc multi-tenant không?
- Một control bù trừ có tạo ra rủi ro quyền riêng tư mới (ví dụ log quá nhiều dữ liệu nhạy cảm) không?
- Có yêu cầu retention hoặc quyền xóa bắt buộc không thể miễn bằng nội bộ?

**Một ngoại lệ về vận hành một pipeline không tự cho phép sử dụng dữ liệu cho mục đích khác**. Phải giữ nguyên những quyền và nghĩa vụ khác không được nêu rõ trong quyết định.

## 8. Ranh giới thời gian: hiệu lực và hết hạn

Ngoại lệ bảo mật thường được thiết kế như một cơ chế **có thời hạn**, với lịch đánh giá lại. Tối thiểu cần:

1. **Effective from:** thời điểm bắt đầu được phép áp dụng ngoại lệ.
2. **Expires at:** mốc hết hiệu lực với múi giờ rõ ràng, hoặc điều kiện chấm dứt có thể kiểm tra.
3. **Milestones:** các mốc CAP, kiểm tra biện pháp bù trừ, rà soát rủi ro và kiểm chứng khắc phục.
4. **Review triggers:** biến động threat, incident, tăng severity, đổi asset, thay policy, thất bại của compensating control.
5. **After expiry:** trạng thái mặc định, hành động cần thực hiện và người chịu trách nhiệm.

Một phê duyệt được ký ngày 10/12 không tự hợp thức hóa sai lệch đã tồn tại từ 01/11. Nếu có khoảng thời gian vi phạm trước khi phê duyệt, cần ghi nhận **unapproved deviation** của kỳ đó và xử lý audit/risk tương ứng. Không được giả định ngoại lệ có hiệu lực hồi tố trừ khi quy định cụ thể cho phép và đánh giá nghĩa vụ được thực hiện.

Gia hạn **không tự động**. Trước khi hết hạn, phải cung cấp rủi ro và bằng chứng mới, lý do chưa hoàn tất CAP, hiệu quả biện pháp tạm, thời hạn mới, người phê duyệt và kế hoạch escalation nếu cần.

### 8.1. Ví dụ timeline

~~~text
01/12    Phát hiện nhu cầu trì hoãn bản vá
03/12    Risk assessment và CAP dự thảo
05/12    Reviewer kiểm tra scope và compensating controls
06/12    Risk owner có thẩm quyền phê duyệt EX-214
07/12    Ngoại lệ bắt đầu có hiệu lực theo quyết định
15/12    Checkpoint: xác minh restriction và monitoring
27/12    Báo cáo tiến độ, thử bản vá ở môi trường đại diện
31/12    Hết hiệu lực; phải khắc phục hoặc có quyết định mới
~~~

Đây là lịch **minh họa**, không phải SLA bắt buộc của tổ chức hay một tiêu chuẩn quốc tế.

## 9. Giới hạn rủi ro và thẩm quyền phê duyệt

Phạm vi không chỉ là danh sách máy chủ. Nó còn xác định **mức độ phơi nhiễm và tác động mà người có thẩm quyền đã đánh giá và chấp nhận**.

Risk assessment nên xem:

- Threat/attack scenario hoặc failure mode được tạo ra bởi sai lệch.
- Tài sản và mục tiêu nghiệp vụ bị ảnh hưởng; mức độ nhạy cảm dữ liệu.
- Khả năng sự kiện xảy ra và tác động nếu xảy ra, theo phương pháp tổ chức.
- Quy mô tài sản, user/tenant và khu vực liên quan.
- Dependency và common-mode risk, ví dụ role hoặc image được tái sử dụng.
- Control đã có và compensating controls, mức hiệu lực đã được chứng minh.
- Rủi ro còn lại, các giả định và mức không chắc chắn.
- Quyền hạn của người phê duyệt so với mức rủi ro và nghĩa vụ áp dụng.

**Không chia nhỏ giả tạo một rủi ro lớn thành nhiều ngoại lệ nhỏ** để từng bản ghi rơi xuống dưới ngưỡng phê duyệt. Nếu ba yêu cầu ngoại lệ cùng có root cause hoặc phụ thuộc chung, phải đánh giá **rủi ro cộng gộp và tương quan**. Cũng cần kiểm tra liệu tổng số tài sản hoặc thời lượng ngoại lệ đã làm thay đổi mức rủi ro ban đầu chưa.

Một cấp quản lý có thể được quyền chấp nhận ngoại lệ cho môi trường thử nghiệm nhưng không có thẩm quyền đối với dữ liệu khách hàng production hoặc nghĩa vụ hợp đồng. **Approval phải khớp với phạm vi và mức độ tác động**, không chỉ có một chữ ký bất kỳ.

## 10. Compensating controls là điều kiện của ngoại lệ, không phải lời hứa

Một **compensating control** giảm rủi ro trong khi control gốc chưa thể được áp dụng. Đó có thể là phân đoạn mạng, hạn chế quyền, tăng giám sát, kiểm tra thủ công có log hoặc giảm tính năng truy cập. Nhưng **biện pháp phải tương xứng với threat**, có owner và bằng chứng vận hành.

| Mục | Câu hỏi cần chứng minh |
|---|---|
| Rủi ro cần giảm | Control thay thế giảm đường khai thác hoặc hậu quả nào? |
| Thiết kế | Ai thiết kế và kiểm tra sự phù hợp, có tạo rủi ro mới không? |
| Thực thi | Cấu hình thực tế đã triển khai ở đúng tài sản/đường truy cập? |
| Hiệu quả | Test, log hoặc monitoring nào cho thấy control thực sự hoạt động? |
| Thời kỳ | Control hoạt động suốt thời gian ngoại lệ hay chỉ tại ngày chụp ảnh? |
| Failure response | Nếu control mất hiệu lực, ngoại lệ được tạm dừng, thu hồi hay escalated ra sao? |
| Ownership | Ai theo dõi, kiểm tra định kỳ và báo thay đổi? |

Ví dụ khi trì hoãn vá một máy chủ, **giám sát truy cập** có thể giúp phát hiện hành vi bất thường nhưng chưa chắc ngăn khai thác; **cách ly mạng** có thể hạn chế đường truy cập nhưng chưa chứng minh rủi ro bị loại bỏ. Không nên nói “có SIEM nên an toàn” nếu chưa xác minh nguồn log, quy tắc cảnh báo, phạm vi và khả năng ứng phó.

**Nếu compensating control là điều kiện phê duyệt và nó thất bại, ngoại lệ có thể không còn hợp lệ theo chính điều kiện đã duyệt.** Cần quy định hành động trước: hạn chế tiếp xúc, đưa về baseline, điều tra incident hoặc xin phê duyệt lại trong thẩm quyền.

## 11. Viết scope statement có thể đo được

Một **scope statement** tốt nên trả lời đủ các mục:

| Thành phần | Mô tả |
|---|---|
| Exception ID | Mã định danh duy nhất, có liên kết với risk/control/finding |
| Requirement | Mã control, phiên bản policy, điều khoản bị sai khác |
| Allowed deviation | Chính xác điều gì được phép khác chuẩn; mức độ sai khác |
| In-scope assets | Danh sách/tập asset có định danh có thể kiểm tra |
| In-scope environment | Production/staging, account, region, tenancy, location |
| Identity/action/data boundaries | Role, loại thao tác và loại dữ liệu liên quan nếu cần |
| Explicit exclusions | Các tài sản, hành vi, control, môi trường **không** được bao gồm |
| Time window | Bắt đầu, hết hạn, mốc review, timezone |
| Risk/approval | Đánh giá tác động, residual risk, người phê duyệt đúng cấp |
| Conditional controls | Biện pháp bù trừ, owner và bằng chứng |
| Remediation path | CAP, mốc khắc phục, điều kiện trở lại baseline |
| Monitoring/verification | Cơ chế phát hiện scope drift, review, evidence index |
| Termination triggers | Khi nào tự hết hiệu lực hoặc phải escalated |

### 11.1. Ví dụ viết trước và sau

**Quá rộng:**

> Đội nền tảng được tạm hoãn vá các máy chủ cũ cho tới khi nhà cung cấp hỗ trợ. Có tăng cường giám sát.

Không biết **máy nào, control nào, mức sai lệch nào, môi trường nào, đến khi nào, ai phê duyệt và giám sát gì**.

**Giới hạn hơn (giả định):**

> Ngoại lệ EX-214 cho phép trì hoãn đáp ứng thời hạn khắc phục finding VULN-214 theo chính sách VULN-SLA-v3 đối với đúng hai host \`APP-L01\` và \`APP-L02\` thuộc dịch vụ đặt hàng legacy, cloud account \`legacy-prod\`, region A. Có hiệu lực từ 07/12/2026 00:00 UTC đến 31/12/2026 18:00 UTC. Ngoại lệ không áp dụng cho bất kỳ host mới, DR replica ở region B, lỗ hổng khác hoặc việc giảm logging/IAM. Trong thời gian này phải duy trì đường mạng giới hạn, giám sát sự kiện truy cập được xác minh và kiểm tra định kỳ. Risk owner phê duyệt sau khi xem residual risk; CAP phải triển khai và kiểm thử bản vá hoặc đề xuất phương án thay thế trước khi hết hiệu lực.

**Điều kiện bắt buộc:** phải chứng minh APP-L01 và APP-L02 đúng là toàn bộ population được phê duyệt, và nếu một host mới xuất hiện thì **không mặc định** được hưởng ngoại lệ.

## 12. Mẫu bản ghi ngoại lệ có phạm vi rõ

Ví dụ YAML dưới đây là **mẫu minh họa**, không phải schema bắt buộc hay approval thật:

~~~yaml
exception_id: EX-214
title: "Temporary patch-SLA deviation for legacy application nodes"
status: APPROVED
requester_role: LEGACY_PLATFORM_OWNER

requirement:
  policy_id: VULN-SLA-v3
  control_id: VULN-REMEDIATE-01
  deviation: "Deferred remediation of finding VULN-214 only"

scope:
  service_id: legacy-ordering
  environment: production
  account_id: legacy-prod
  region: region-A
  asset_ids:
    - APP-L01
    - APP-L02
  allowed_deviation:
    finding_id: VULN-214
    type: patch-deadline-extension
  excluded:
    - "all new hosts or replacements unless separately approved"
    - "all disaster-recovery replicas in region-B"
    - "all unrelated vulnerabilities and security controls"
    - "any relaxation of IAM, encryption or required audit logging"
  data_classification: internal-confidential

validity:
  effective_from_utc: "2026-12-07T00:00:00Z"
  expires_at_utc: "2026-12-31T18:00:00Z"
  review_frequency: weekly
  no_automatic_renewal: true

risk:
  assessment_ref: "restricted/risk/RA-214"
  residual_risk_ref: "restricted/risk/RISK-214"
  risk_owner_role: AUTHORIZED_SERVICE_RISK_OWNER

conditions:
  compensating_controls:
    - id: CC-214-01
      description: "approved network isolation policy"
      owner_role: NETWORK_SECURITY
      evidence_ref: "restricted/evidence/network-policy-check"
    - id: CC-214-02
      description: "security event monitoring and alert response"
      owner_role: SECURITY_OPERATIONS
      evidence_ref: "restricted/evidence/monitoring-check"
  scope_monitor:
    inventory_ref: "restricted/inventory/legacy-ordering"
    compare_assets_to_approval: true
    on_unapproved_growth: ESCALATE
  termination_triggers:
    - "compensating-control-failure"
    - "active-exploitation-indicator"
    - "scope-or-asset-expansion"
    - "policy-or-severity-material-change"

remediation:
  cap_id: CAP-214
  action_owner_role: PLATFORM_ENGINEERING
  target_date_utc: "2026-12-30T18:00:00Z"
  closure_criteria_ref: "restricted/remediation/CAP-214/criteria"

approvals:
  security_review_role: SECURITY_ASSURANCE
  authorized_approver_role: BUSINESS_RISK_AUTHORITY
  approval_evidence_ref: "restricted/approvals/EX-214"

audit:
  evidence_index: "restricted/evidence/EX-214"
  last_scope_check_utc: "2026-12-14T08:00:00Z"
  last_conditions_check_utc: "2026-12-14T08:00:00Z"
~~~

Các mã, ngày, role và đường dẫn là **placeholder**. Trong triển khai thật, mỗi tham chiếu phải dẫn tới chứng cứ có thể kiểm tra; không được tự tạo approval hoặc dùng YAML có chữ \`APPROVED\` làm bằng chứng rằng quyết định đã được ký hợp lệ.

Lưu hồ sơ theo quyền hạn phù hợp: scope có thể tiết lộ những tài sản đang có điểm yếu, cấu hình mạng và phương án bù trừ. Không công khai danh sách host dễ bị khai thác, token, bí mật hoặc dữ liệu nhạy cảm không cần thiết.

## 13. Quy trình xác định và phê duyệt phạm vi ngoại lệ

Một quy trình từ đầu đến cuối có thể tổ chức:

~~~mermaid
flowchart TD
    A["Yêu cầu sai khác từ control owner"] --> B["Xác định control, lý do, scope, thời hạn"]
    B --> C["Kiểm tra policy/hợp đồng/pháp lý có cho phép?"]
    C --> D{"Có thẩm quyền cho ngoại lệ?"}
    D -- "Không" --> E["Không phê duyệt; xử lý theo nghĩa vụ áp dụng"]
    D -- "Có" --> F["Đánh giá risk, phụ thuộc và tác động cộng gộp"]
    F --> G["Thiết kế compensating controls + CAP"]
    G --> H["Review scope, asset population, evidence"]
    H --> I{"Approval đúng cấp và đủ điều kiện?"}
    I -- "Không" --> J["Bổ sung hoặc từ chối"]
    I -- "Có" --> K["Lưu quyết định và giám sát hiệu lực"]
    K --> L["Kiểm tra scope drift và điều kiện"]
    L --> M{"Hết hạn, thay đổi hoặc control thất bại?"}
    M -- "Có" --> N["Escalate, revoke, remediate hoặc phê duyệt lại"]
    M -- "Không" --> L
~~~

**Giai đoạn đề nghị:** requester nêu yêu cầu và lý do không thể tuân thủ ngay; mô tả asset và điều kiện; đưa ra các phương án không cần ngoại lệ đã xem xét.

**Giai đoạn đánh giá:** risk/security xác minh policy áp dụng, phạm vi, threat, mức rủi ro, hiệu lực compensating controls, CAP và các yêu cầu bên ngoài.

**Giai đoạn phê duyệt:** người có thẩm quyền ký **đúng phiên bản và phạm vi**; cần xử lý xung đột lợi ích và tách vai trò trong mức độ phù hợp.

**Giai đoạn thực thi:** control owner thông báo điều kiện tới các bên liên quan, triển khai compensating controls, lưu bản ghi và theo dõi drift.

**Giai đoạn đóng/gia hạn:** khắc phục sai lệch theo tiêu chí, hết hiệu lực đúng hạn, hoặc đánh giá lại với evidence mới; mọi sửa đổi trọng yếu cần approval mới hoặc amendment theo quy trình.

Cần phân biệt việc **nhận yêu cầu** với việc **đã được duyệt**. Một request có ticket ID chưa cho phép tự thay đổi security baseline khi trạng thái vẫn PENDING.

## 14. Thay đổi nào làm phạm vi không còn hợp lệ?

Một ngoại lệ được duyệt cho trạng thái cụ thể. Khi giả định thay đổi, có thể không còn cơ sở chấp nhận rủi ro.

| Thay đổi | Nguy cơ | Hành động phù hợp |
|---|---|---|
| Thêm host mới từ image cũ | Population vượt số lượng đã duyệt | Không tự mở rộng; đánh giá và phê duyệt thay đổi nếu cần |
| Chuyển dịch vụ từ staging lên production | Tác động rủi ro tăng | Re-scope, risk review, quyền duyệt tương ứng |
| Dữ liệu chuyển sang lớp nhạy cảm hơn | Tác động tới privacy/compliance | Rà soát control, nghĩa vụ và quyết định |
| Thêm người dùng/tenant/role đặc quyền | Bề mặt tấn công mở rộng | Review least privilege, identity scope |
| Bên thứ ba thay đổi kiến trúc | Biện pháp bù trừ có thể không còn hiệu quả | Kiểm chứng dependency và test |
| Phát hiện dấu hiệu khai thác | Giả định mức phơi nhiễm không còn | IR, containment, review khẩn cấp |
| Công cụ giám sát mất log | Điều kiện bù trừ bị vi phạm | Escalate, áp dụng phương án bảo vệ đã duyệt |
| Policy được thay đổi hoặc finding tái phân loại | Criteria/risk rating thay đổi | Đánh giá lại hợp lệ và thời hạn |
| Hết ngày hiệu lực | Quyết định cũ không còn áp dụng | Trở về baseline hoặc có quyết định mới trước hạn |

**Scope drift** có thể xuất hiện do thay đổi hệ thống bình thường, không nhất thiết do cố tình vi phạm. Vì vậy cần cơ chế phát hiện tự động hoặc định kỳ, không chỉ dựa vào cam kết “sẽ thông báo khi có thay đổi”.

### 14.1. Minh họa kiểm tra scope drift

Một phép đối chiếu có thể dùng logic sau, dưới dạng pseudocode:

~~~text
approved_assets = {APP-L01, APP-L02}
current_assets = inventory_query(service="legacy-ordering", env="production")

for asset in current_assets:
    if asset has the affected finding:
        if asset.id not in approved_assets:
            raise "UNAPPROVED_EXCEPTION_SCOPE_EXPANSION"

for condition in exception.required_conditions:
    if not verify(condition, current_evidence):
        raise "EXCEPTION_CONDITION_NOT_DEMONSTRATED"

if now_utc >= exception.expires_at_utc:
    raise "EXCEPTION_EXPIRED"
~~~

Không sử dụng pseudocode trên như một công cụ tự ý ngắt production: khi phát hiện vi phạm, phải áp dụng **quy tắc phản ứng an toàn đã được phê duyệt** (escalation, containment, rollback hoặc thay đổi có kiểm soát) tương ứng với rủi ro. Giới hạn của inventory query, freshness và nguồn dữ liệu cũng cần được kiểm tra.

## 15. Gia hạn, điều chỉnh và kết thúc ngoại lệ

Có ba loại thay đổi cần phân biệt:

- **Amendment:** sửa phạm vi, điều kiện hoặc ngày của bản ghi còn hiệu lực theo đúng thẩm quyền. Không ghi đè lịch sử quyết định gốc.
- **Renewal:** yêu cầu một thời kỳ tiếp theo; cần đánh giá lại rủi ro, hiệu lực biện pháp bù trừ, nguyên nhân chậm CAP và thẩm quyền phê duyệt.
- **Closure/termination:** không còn sai khác hoặc quyết định chấm dứt; phải chứng minh việc trở về baseline, loại bỏ quyền/cấu hình tạm và đóng tài liệu liên quan theo quy trình.

Ví dụ gia hạn từ 31/12 sang 31/01 cần trả lời: vì sao bản vá chưa thể áp dụng; có thay đổi threat/vulnerability hay asset không; compensating control đã vận hành ra sao; ai chịu trách nhiệm giải quyết; có giải pháp thay thế; rủi ro cộng gộp qua nhiều đợt gia hạn là gì.

**Không nên gia hạn vô hạn bằng cách sao chép lý do cũ.** Đợt thứ hai hoặc thứ ba có thể cần escalation do rủi ro kéo dài đã vượt mức ban đầu. Hạn và cấp escalation phải theo chính sách tổ chức, không mặc định một mốc chung cho mọi doanh nghiệp.

### 15.1. Khi kết thúc bằng remediation

Một ngoại lệ chỉ nên được đóng vì khắc phục khi có bằng chứng:

1. Security control đã được triển khai hoặc thay thế hợp lệ trên **toàn bộ tài sản thuộc phạm vi**.
2. Retest đúng finding hoặc tiêu chí đã từng bị sai lệch.
3. Không gây regression trọng yếu cho chức năng/control liên quan.
4. Quyền, network rule, cổng tạm và compensating control chỉ cần trong ngoại lệ đã được thu hồi/điều chỉnh an toàn.
5. Người có thẩm quyền xác nhận closure và cập nhật risk register, finding, assurance case.

Nếu chỉ một host đã vá nhưng host còn lại chưa, có thể đóng action của host đã hoàn thành; **không nên đóng ngoại lệ tổng thể** khi phần sai khác còn tồn tại.

## 16. Evidence để chứng minh ngoại lệ được giữ đúng phạm vi

Một kết luận “ngoại lệ đang tuân thủ điều kiện phê duyệt” cần chứng cứ:

| Claim cần chứng minh | Evidence phù hợp | Điều cần xác minh |
|---|---|---|
| Đúng yêu cầu đã được duyệt | Bản policy/control và approval | Phiên bản, điều khoản, hiệu lực và thẩm quyền |
| Không vượt asset scope | Inventory, deployment/config export | Population đầy đủ, tài sản mới và shadow IT |
| Không vượt identity/action scope | IAM export, access logs, role graph | Quyền kế thừa, đường truy cập phụ, account mới |
| Đúng thời kỳ | Approval timestamps, workflow status | UTC, hiệu lực, không tự gia hạn |
| Compensating control còn hoạt động | Config test, logs, review record | Phạm vi, độ phủ, nguồn, thời kỳ |
| CAP đang tiến triển | Milestones, tickets, change evidence | Owner, hạn, phụ thuộc và rủi ro trễ |
| Không phát sinh rủi ro khác | Risk review, incident, change record | Threat thay đổi, phụ thuộc chung, dữ liệu nhạy cảm |
| Đã kết thúc ngoại lệ đúng | Retest, deployment proof, rollback log | Baseline đã phục hồi, không còn tài nguyên tạm |

Bằng chứng phải gắn **mã ngoại lệ, thời điểm, nguồn, phạm vi, người kiểm tra và kết quả**. Một screenshot cho thấy network rule đúng tại một mốc chưa chứng minh rule đó hoạt động trong cả ba tuần; cần thêm lịch sử thay đổi hoặc evidence theo kỳ khi yêu cầu.

Để bảo vệ integrity, có thể lưu version và hash của artifact, nhưng hash **không xác nhận tính đúng hoặc đầy đủ của dữ liệu nguồn trước khi thu thập**. Kho evidence cần phân quyền, ghi audit trail và lưu giữ theo chính sách.

## 17. Tình huống xuyên suốt: trì hoãn vá lỗi trên ứng dụng legacy

Tất cả thông tin, mã và ngày dưới đây là **giả định để học**, không mô tả môi trường thực tế.

### 17.1. Yêu cầu và vấn đề

Một tổ chức có chính sách **VULN-SLA-v3**, yêu cầu khắc phục finding thuộc nhóm ưu tiên nhất định trong thời hạn đã phê duyệt. Dịch vụ xử lý đơn hàng cũ có hai máy chủ production \`APP-L01\` và \`APP-L02\` phụ thuộc thành phần chưa tương thích với bản vá. Nhà cung cấp cần một chu kỳ kiểm thử bổ sung trước khi thay đổi production.

Chủ dịch vụ gửi yêu cầu: “Cho phép trì hoãn vá trong tháng 12”.

Câu này thiếu phạm vi. Trước khi phê duyệt, nhóm bảo mật yêu cầu:

- Chỉ ra finding/version và control SLA đang bị sai khác.
- Xác định hai host, account, region, environment và nguồn inventory.
- Chứng minh có hay không DR replica, autoscaling image hoặc service khác dùng cùng component.
- Đánh giá bề mặt truy cập, dữ liệu xử lý, điều kiện hoạt động và các khả năng tác động.
- Đề xuất hạn cụ thể, CAP với nhà cung cấp và các kiểm soát thay thế có thể kiểm tra.

### 17.2. Decision boundary

Nhóm thống nhất rằng, **nếu risk owner đủ thẩm quyền chấp thuận**, ngoại lệ chỉ cho phép trì hoãn **thời hạn xử lý finding VULN-214** trên hai host và trong cửa sổ 07/12–31/12/2026. Nó không nới lỏng các yêu cầu quản lý IAM, logging, network change hoặc việc triển khai patch cho hệ thống khác.

**Điều kiện:** áp dụng restriction mạng phù hợp, giám sát đường truy cập trọng yếu, kiểm tra định kỳ, không bổ sung host mới, kiểm tra bản vá trong môi trường đại diện và báo tiến độ trước hạn.

Việc biện pháp tạm có đủ hay không phụ thuộc **risk assessment thực tế**, không thể xác định chỉ từ tên “network restriction” hoặc “monitoring”.

### 17.3. Diễn biến và kiểm tra

| Thời điểm giả định | Quan sát | Đánh giá phạm vi |
|---|---|---|
| 07/12 | Phê duyệt đúng hai host và có bằng chứng control tạm | Ngoại lệ có thể bắt đầu theo quyết định |
| 12/12 | Inventory xuất hiện host \`APP-L03\` từ image cũ | Host mới **ngoài scope**, cần đánh giá riêng; không tự nhận ngoại lệ |
| 15/12 | Giám sát trên \`APP-L02\` mất một nguồn log bắt buộc | Điều kiện compensating control chưa chứng minh, cần escalation |
| 20/12 | Vendor cung cấp bản vá thử nghiệm, test kỹ thuật PASS | Chưa chứng minh production đã khắc phục |
| 28/12 | Hai host đã được vá trên production, retest thành công | Có cơ sở đề nghị closure, kiểm tra các điều kiện còn lại |
| 31/12 | Người có thẩm quyền xác nhận closure và cập nhật risk register | Ngoại lệ kết thúc nếu toàn bộ criteria đạt |

**Kết luận đối với APP-L03:** Nếu host đó bị ảnh hưởng cùng finding, nó là một **unapproved deviation** hoặc vấn đề rủi ro cần xử lý ngay theo quy trình; không được ngầm đưa vào EX-214. Nếu đã được thay thế an toàn trước khi kiểm tra, vẫn cần evidence thời điểm, phiên bản và lý do xác định không còn chịu ảnh hưởng.

**Kết luận đối với mất log:** Nếu logging là điều kiện bù trừ bắt buộc, không thể coi ngoại lệ vẫn hoàn toàn tuân thủ điều kiện cho thời gian mất log. Cần ghi khoảng trống, áp dụng biện pháp phù hợp và xem xét liệu risk acceptance ban đầu còn hiệu lực.

### 17.4. Mẫu kết luận assurance

> Ngoại lệ EX-214 được phê duyệt cho việc trì hoãn xử lý finding VULN-214 trên hai host production đã định, với thời gian và điều kiện cụ thể. Kết quả kiểm tra ngày 12/12 phát hiện tài sản APP-L03 nằm ngoài phạm vi; kiểm tra ngày 15/12 phát hiện thiếu evidence logging thuộc điều kiện phê duyệt. Vì vậy không có đủ cơ sở xác nhận ngoại lệ được duy trì đúng toàn bộ điều kiện trong giai đoạn đó. Các vấn đề được escalated; sau khi hoàn tất remediation và retest toàn bộ đối tượng liên quan, hồ sơ cần được người có thẩm quyền kiểm tra trước khi đóng.

Cách diễn đạt này không làm đẹp bản ghi nhưng giúp chương trình security assurance có dữ liệu đúng để ra quyết định.

## 18. Các trường hợp đặc biệt

### 18.1. Ngoại lệ áp dụng cho nhóm tài sản động

Một nhóm autoscaling có thể không cố định host ID. Phạm vi nên dùng **định danh workload bất biến hoặc rule membership có thể kiểm tra**, giới hạn môi trường, image, số lượng hoặc công suất, và event trigger khi có node mới. Nếu yêu cầu thay đổi vật liệu rủi ro, phải review trước khi tài sản mới được phép sai chuẩn.

### 18.2. Ngoại lệ ở nền tảng nhiều tenant

Một sai khác chỉ được phép cho một tenant không có nghĩa cùng cấu hình được bật trên shared service ảnh hưởng mọi tenant. Cần phân tích **data plane, control plane và blast radius**, nhất là khi feature flag, policy hoặc network segmentation có phạm vi toàn tài khoản.

### 18.3. Ngoại lệ liên quan nhà cung cấp

Nhà cung cấp có thể sở hữu control kỹ thuật nhưng tổ chức vẫn sở hữu rủi ro từ dịch vụ phụ thuộc. Phải xác định phần của vendor, phần của khách hàng, bằng chứng theo hợp đồng, phạm vi đánh giá độc lập, phương án tạm và owner nội bộ. Không dùng câu “vendor đang xử lý” thay cho CAP có thời hạn và điều kiện kiểm chứng.

### 18.4. Ngoại lệ emergency

Trong tình huống khẩn cấp có thể tồn tại luồng phê duyệt nhanh theo quy trình được duyệt trước; nó vẫn cần định danh principal/asset, hành vi, thời lượng, điều kiện kích hoạt, log, người được ủy quyền và review hậu sự kiện. **Emergency exception** không phải quyền miễn trừ không giới hạn và không mặc nhiên hợp thức hóa mọi thay đổi.

### 18.5. Ngoại lệ ở tầng chính sách vs ngoại lệ thực thi

Nếu policy cho phép một biến thể control được phê duyệt là tương đương (ví dụ lựa chọn cách xác thực khác đáp ứng yêu cầu), có thể đây là **phương án tuân thủ hợp lệ**, không phải ngoại lệ. Ngược lại, nếu control không đạt tiêu chí, không nên đổi tên thành “alternative control” mà không có đánh giá tính tương đương và quyền quyết định.

## 19. Anti-patterns khi định nghĩa phạm vi ngoại lệ

| Sai lầm | Rủi ro | Cách cải thiện |
|---|---|---|
| “Ngoại lệ cho toàn bộ legacy systems” | Phạm vi quá rộng, không xác định population | Asset IDs, môi trường, requirement và giới hạn cụ thể |
| Không ghi out-of-scope | Dễ suy rộng tới region, account và role khác | Nêu loại trừ quan trọng trong approval |
| Tên nhóm tài sản động không có rule | Tự mở rộng khi autoscale | Membership rule, snapshot và drift monitor |
| Không quy định thời hạn | Ngoại lệ tạm thành mặc định | Effective/expires/review trigger |
| Bắt đầu tính từ trước ngày phê duyệt mà không có căn cứ | Che thời kỳ unapproved deviation | Ghi lịch sử và nghĩa vụ xử lý riêng |
| Phê duyệt một control nhưng nới lỏng nhiều control | Sai giới hạn quyết định | Chỉ rõ allowed deviation và unaffected controls |
| Xem approval như control PASS | Làm sai assurance và audit status | Tách quyết định risk khỏi kết quả kiểm soát |
| Không có compensating control đủ bằng chứng | Không biết rủi ro tạm đã giảm không | Test, monitoring, owner và failure condition |
| Gia hạn bằng lý do copy-paste | Rủi ro kéo dài không được xem lại | Đánh giá mới, tiến độ CAP, escalation |
| Dùng một chữ ký cho mọi mức rủi ro | Sai thẩm quyền | Approval matrix theo mức tác động |
| Không xét rủi ro cộng gộp | Nhiều ngoại lệ cùng tạo đường tấn công lớn | Risk aggregation theo dịch vụ/threat/dependency |
| Không kiểm tra obligation bên ngoài | Ngoại lệ nội bộ có thể không hợp lệ | Pháp lý/hợp đồng/compliance review nếu cần |
| Không theo dõi asset mới | Scope creep không phát hiện | Inventory và đối chiếu định kỳ |
| Đóng ngoại lệ vì ticket Done | Không chứng minh trở lại baseline | Retest, deployment proof, closure reviewer |
| Sao chép secret và danh sách host nhạy cảm vào báo cáo rộng | Tăng bề mặt tiết lộ | Evidence reference trong kho có quyền hạn |

## 20. Bài tập thực hành

### Tình huống A — Ngoại lệ vá lỗi không rõ phạm vi

Chủ hệ thống viết:

> “Ứng dụng tài chính cũ không thể cập nhật bản vá bảo mật trong 2 tháng. Đề nghị ngoại lệ cho toàn bộ cụm, đội kỹ thuật sẽ theo dõi.”

Hãy:

1. Chỉ ra ít nhất **10 thông tin còn thiếu** để xác định scope và đánh giá rủi ro.
2. Viết lại scope statement có requirement, asset IDs, environment, thời kỳ, out-of-scope, compensating controls, owner và termination triggers.
3. Xác định ai cần review và ai được quyền phê duyệt nếu hệ thống chứa dữ liệu tài chính nhạy cảm.
4. Nêu evidence chứng minh cụm được liệt kê đã đầy đủ và compensating controls hoạt động.
5. Giải thích xử lý khi cụm mở rộng thêm hai node từ image cũ.
6. Xác định tiêu chí đóng ngoại lệ sau khi cập nhật bản vá.

### Tình huống B — Truy cập khẩn cấp ngoài thời gian duyệt

Một đội có ngoại lệ cho phép một principal thực hiện thao tác bảo trì được ghi log vào cửa sổ 02:00–04:00 UTC trên môi trường DR. Sau bảo trì, quyền vẫn còn hoạt động thêm hai ngày và được dùng để truy cập production.

1. Phần nào nằm ngoài scope theo thời gian, environment và action?
2. Vì sao không thể nói mọi truy cập đều hợp lệ vì “đã có approval”?
3. Cần evidence gì để xác nhận thời điểm sử dụng, đối tượng và tài nguyên?
4. Đề xuất containment, điều tra, thu hồi quyền và cải tiến quy trình.
5. Các quyết định rủi ro và báo cáo nào cần tách khỏi quyết định gốc?

### Tình huống C — Mất điều kiện giám sát

Một ngoại lệ được duyệt vì hệ thống chưa thể vá, với điều kiện bắt buộc có network isolation và security alert khi truy cập ngoài allowlist. Một tuần sau, log pipeline mất dữ liệu hai ngày, nhưng mạng vẫn bị giới hạn đúng policy.

1. Ngoại lệ còn được chứng minh đáp ứng **toàn bộ điều kiện** không?
2. Cần phân biệt thiếu evidence logging với việc chứng minh logging thực sự không hoạt động ra sao?
3. Khi nào cần escalation, containment hoặc review lại quyết định?
4. Bổ sung test và giám sát nào để phát hiện mất log sớm?
5. Có thể đóng vấn đề chỉ bằng screenshot dashboard xanh tại ngày hiện tại không?

### Tình huống D — Rủi ro cộng gộp

Ba đội riêng biệt xin ngoại lệ trì hoãn vá cùng một component trên ba ứng dụng. Mỗi đội cho rằng phạm vi nhỏ và mức rủi ro riêng thấp. Cả ba dùng chung identity provider, network segment và kho dữ liệu.

1. Vì sao đánh giá từng ngoại lệ riêng chưa đủ?
2. Xác định các common-mode risks và đường lây lan ảnh hưởng chéo.
3. Đề xuất cách tổng hợp thông tin và quyền phê duyệt.
4. Thiết kế điều kiện giám sát ảnh hưởng cộng gộp.
5. Nêu khi nào một quyết định ban đầu phải bị thu hồi hoặc đánh giá lại.

**Gợi ý:** Một phạm vi hợp lệ phải được xác nhận qua **danh mục asset/identity thực tế**, **yêu cầu cụ thể**, **ngày hiệu lực**, **đúng cấp phê duyệt**, **biện pháp bù trừ có bằng chứng**, và **điều kiện chấm dứt**. Nếu thiếu bằng chứng không nên tự báo đạt; nếu có sai lệch ngoài approval thì phải xử lý như vấn đề chưa được phê duyệt.

## 21. Ghi nhớ

**Phạm vi ngoại lệ** xác định **ranh giới của một quyết định được phép sai khác**: control nào, tài sản nào, môi trường và danh tính nào, hành vi và dữ liệu nào, trong thời kỳ nào, với điều kiện và rủi ro còn lại nào. Những thứ không được liệt kê hoặc không đáp ứng điều kiện **không mặc nhiên nằm trong ngoại lệ**.

Một ngoại lệ có chất lượng cần có: **criteria cụ thể → scope statement có in/out boundaries → risk assessment → compensating controls → approval đúng thẩm quyền → theo dõi scope drift → CAP và hạn kết thúc → retest/closure evidence**.

Trong module **SECURITY_SECURITY_ASSURANCE**, ngoại lệ không phải “lá phiếu PASS” cho security control chưa đạt. Nó là quyết định quản trị rủi ro được **giới hạn, giám sát, có thể truy xuất và có thể xem lại**, giúp tổ chức kiểm soát những sai khác tạm thời trong khi tiếp tục bảo vệ mục tiêu bảo mật và thúc đẩy khắc phục có bằng chứng.
