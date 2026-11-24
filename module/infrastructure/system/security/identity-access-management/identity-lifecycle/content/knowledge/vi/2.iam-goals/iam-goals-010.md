# Đánh đổi bảo mật và tiện dụng trong quản lý vòng đời danh tính IAM

## 1. Vì sao bảo mật và tiện dụng phải được cân bằng?

**Identity and Access Management (IAM)** trả lời những câu hỏi nền tảng: ai là chủ thể, đã được xác minh tới mức nào, có thể đăng nhập bằng cách nào, có quyền gì và khi nào các quyền đó phải thay đổi hoặc bị thu hồi. Mục tiêu của IAM không chỉ là ngăn truy cập trái phép mà còn **cho phép người dùng hợp lệ hoàn thành công việc đúng lúc, với ít ma sát hợp lý nhất**.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, bài toán này gắn với vòng đời **Joiner–Mover–Leaver (JML)**: một nhân viên mới cần được cấp đúng quyền khi bắt đầu làm việc; một nhân viên đổi vai trò cần được chuyển quyền mà không làm gián đoạn nhiệm vụ; một nhân viên nghỉ việc phải bị thu hồi quyền đúng hạn. Hệ thống thường phối hợp HRIS, Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán. Mỗi lựa chọn kỹ thuật đều có chi phí về thao tác, độ trễ, vận hành và trải nghiệm.

Ví dụ, bắt buộc xác thực đa yếu tố (MFA) mỗi lần mở một trang sẽ tăng ma sát nhưng chưa chắc cải thiện bảo vệ tương xứng; ngược lại, cho phép phiên tồn tại quá lâu có thể tạo rủi ro khi người dùng bị thu hồi quyền. **Thiết kế tốt không đồng nghĩa chọn bảo mật thấp hơn để tiện lợi hơn**. Điều cần làm là áp dụng kiểm soát phù hợp mức rủi ro, thiết kế trải nghiệm thông suốt và chứng minh kết quả bằng số liệu.

## 2. Bốn chiều đánh giá thay vì một lựa chọn nhị phân

| Chiều | Câu hỏi đánh giá | Dấu hiệu bất thường |
|---|---|---|
| **Bảo mật** | Có ngăn truy cập không được phép và giảm quyền tồn dư? | Leaver vẫn dùng token cũ để gọi API |
| **Tiện dụng** | Người hợp lệ có đăng nhập và xin quyền dễ hiểu, ít bước thừa? | Người dùng bị yêu cầu MFA liên tục không rõ lý do |
| **Khả năng vận hành** | Có tự động hóa, đối soát, xử lý lỗi và hỗ trợ hiệu quả? | Mỗi Mover cần nhiều ticket thủ công |
| **Tuân thủ và kiểm toán** | Có chứng cứ phê duyệt, thay đổi, thu hồi và ngoại lệ? | Không giải thích được ai cấp quyền admin |

Một chỉ số đơn lẻ dễ gây sai lệch. Tăng tốc độ provisioning bằng cách cấp role mặc định quá rộng có thể khiến onboarding trông tốt nhưng làm tăng rủi ro lâu dài. Giảm ticket hỗ trợ bằng cách bỏ xác minh khôi phục tài khoản sẽ làm trải nghiệm ngắn hơn nhưng mở ra đường chiếm đoạt danh tính.

### Nguyên tắc thiết kế

1. **Least privilege:** chỉ cấp quyền cần thiết, đúng phạm vi và thời hạn.
2. **Risk-based controls:** tăng mức xác minh cho hành động, ngữ cảnh hoặc tài nguyên có rủi ro cao.
3. **Secure defaults:** thiếu thông tin thiết yếu không dẫn tới cấp quyền nhạy cảm mặc định.
4. **Automation with verification:** tự động hóa quy trình nhưng vẫn kiểm tra quyền có hiệu lực ở ứng dụng đích.
5. **Accessible recovery:** người hợp lệ có kênh phục hồi tài khoản an toàn khi mất thiết bị hoặc gặp sự cố.
6. **Auditability:** mỗi quyết định quyền quan trọng có căn cứ và bằng chứng tương ứng.

## 3. Mô hình đánh đổi theo rủi ro

Rủi ro có thể được biểu diễn đơn giản:

~~~text
Risk ≈ Likelihood × Impact

ExpectedBenefit(control)
    = ReductionInExpectedLoss - ImplementationAndOperatingCost
~~~

Đây là mô hình suy nghĩ, không phải công thức chính xác cho mọi tổ chức. Khi đánh giá một kiểm soát IAM, cần đặt câu hỏi: tài nguyên nhạy cảm đến đâu; chủ thể có đặc quyền gì; thiết bị và phiên có đáng tin cậy; nguy cơ lạm dụng có cao; nếu khóa nhầm thì tác động vận hành ra sao; biện pháp thay thế có giảm rủi ro với ít ma sát hơn không?

| Tình huống | Rủi ro | Hướng cân bằng |
|---|---|---|
| Nhân viên đọc tài liệu công khai nội bộ | Thấp hơn quyền quản trị | SSO liền mạch, MFA phù hợp chính sách |
| Quản trị viên sửa quyền IAM | Cao | Xác thực mạnh, step-up, phê duyệt và audit |
| Bot triển khai dùng API | Cao theo phạm vi tài nguyên | Workload identity, credential ngắn hạn và scope nhỏ; không dùng MFA tương tác |
| Nhân viên mới chưa tới ngày bắt đầu | Rủi ro cấp quyền sớm | Chuẩn bị account nhưng giữ truy cập bị khóa tới effectiveAt |
| Leaver khẩn cấp | Rủi ro quyền tồn dư lớn | Ưu tiên containment và thu hồi, bàn giao thực hiện sau |

Một tổ chức có thể chọn mức kiểm soát khác nhau tùy dữ liệu, pháp lý và khẩu vị rủi ro. Điều quan trọng là chính sách rõ ràng, có chủ sở hữu, kiểm chứng được và không tùy tiện nới lỏng khi gặp bất tiện.

## 4. Trải nghiệm Joiner: nhanh nhưng không cấp thừa quyền

Trong giai đoạn **Joiner**, nhu cầu thực tế là người mới bắt đầu làm việc đúng lịch, không phải mất ngày đầu chờ tạo tài khoản. Tuy nhiên, cấp sẵn toàn bộ quyền từ nhiều ngày trước hoặc gán một nhóm “all-employees-admin” để tiết kiệm ticket là lựa chọn rủi ro.

Giải pháp cân bằng:

- Dùng HRIS làm nguồn thông tin về người, bộ phận, chức danh và thời điểm bắt đầu; yêu cầu xác minh trước khi kích hoạt.
- **Pre-provision** identity, mailbox hoặc profile ứng dụng khi được phép, nhưng chỉ mở truy cập theo `effectiveAt` và chính sách.
- Tính quyền mặc định tối thiểu theo RBAC/ABAC; ngoại lệ và đặc quyền cần phê duyệt bổ sung.
- Tự động đồng bộ bằng SCIM/connectors và đọc lại trạng thái, tránh thao tác thủ công lặp lại.
- Hỗ trợ đăng ký MFA/passkey qua luồng onboarding dễ hiểu, có phương án hỗ trợ an toàn khi người dùng chưa có thiết bị phù hợp.
- Cho người dùng xem trạng thái yêu cầu và nguyên nhân bị chặn, nhưng không lộ chi tiết bảo mật không cần thiết.

**Ví dụ:** một nhân viên Sales VN được cấp `crm.customer.read.vn` vào ngày bắt đầu, không được `crm.export.all`. Nếu tạo tài khoản thành công nhưng thiếu group CRM, hệ thống hiển thị `PENDING` và có retry. Không đánh dấu hoàn tất chỉ vì IdP đã có user.

## 5. Trải nghiệm Mover: chuyển việc liền mạch mà không tích lũy quyền

**Mover** là giai đoạn dễ xuất hiện tranh luận “giữ quyền cũ thêm một thời gian cho tiện”. Người dùng chuyển từ Sales sang Finance có thể cần hoàn thành bàn giao, nhưng giữ mọi quyền Sales vô thời hạn tạo **privilege creep**.

Thực hiện:

1. Tính `desiredAfter` từ trạng thái HRIS và policy hiện hành.
2. So sánh tập quyền cũ và mới để xác định quyền phải thêm hoặc gỡ.
3. Xử lý xung đột SoD trước khi cấp các quyền có thể tạo rủi ro.
4. Đối với giai đoạn bàn giao thực sự cần thiết, tạo **ngoại lệ có phạm vi, người duyệt và ngày hết hạn**.
5. Cập nhật IdP/SCIM/ứng dụng và kiểm tra role trực tiếp, nhóm lồng nhau, token chứa claim cũ.
6. Cung cấp thông báo thân thiện: quyền nào chuyển đổi, quyền nào hết hạn và cách yêu cầu ngoại lệ.

~~~text
before = {crm.customer.read.vn, sales.dashboard.read}
desiredAfter = {finance.report.read, finance.dashboard.read}

toAdd = desiredAfter - before
toRemove = before - desiredAfter

actualAfter phải bằng desiredAfter sau thời hạn đồng bộ,
trừ các ngoại lệ bàn giao còn hiệu lực và được phê duyệt.
~~~

Không có nghĩa luôn phải “thu hồi trước, cấp sau” hay ngược lại: thứ tự phụ thuộc SoD và yêu cầu liên tục nghiệp vụ. Trong tình huống xung đột quyền, thu hồi quyền cũ hoặc kiểm soát giao dịch trước khi mở quyền mới có thể là bắt buộc.

## 6. Trải nghiệm Leaver: bảo vệ tức thời, bàn giao có kiểm soát

Ở **Leaver**, ưu tiên chuyển sang ngăn truy cập không được phép. Nếu người nghỉ vẫn có phiên SSO, API key hoặc quyền ứng dụng cục bộ, việc disable tại IdP chưa đủ.

Thiết kế cần:

- Xác minh nguồn chấm dứt và đúng `personId`, tránh khóa nhầm người vì trùng email/tên.
- Phân biệt nghỉ việc theo lịch, contractor hết hạn và chấm dứt khẩn cấp; áp dụng deadline tương ứng.
- Chặn đăng nhập mới và xử lý session, refresh token, access token, PAT, SSH key theo khả năng kỹ thuật và SLA.
- Thu hồi nhóm, role, quyền trực tiếp, chia sẻ tài liệu, VPN và quyền quản trị secret trong phạm vi.
- Bàn giao dữ liệu và tài sản theo chính sách retention; **không tự động xóa dữ liệu công việc** chỉ vì account inactive.
- Chuyển ownership service account, bot, repository và integration mà người nghỉ đang quản lý.
- Ghi bằng chứng readback và thử API để xác nhận không còn quyền tồn dư.

JWT self-contained có thể còn được ứng dụng chấp nhận tới hạn `exp` nếu chỉ kiểm chữ ký offline. Vì vậy SLA thu hồi, TTL, token introspection hoặc giải pháp vô hiệu hóa phiên phải được quyết định trước, không giả định mọi token lập tức hết hiệu lực khi khóa IdP.

## 7. SSO và MFA: giảm ma sát đúng cách

**SSO** giảm số lần người dùng nhập thông tin xác thực và giúp chính sách đăng nhập tập trung hơn. **MFA** bổ sung khả năng chống chiếm đoạt tài khoản; các phương thức MFA không mang mức bảo đảm giống nhau.

| Thiết kế | Lợi ích tiện dụng | Lợi ích và giới hạn bảo mật |
|---|---|---|
| SSO với phiên hợp lý | Ít đăng nhập lặp | Cần kiểm soát phiên và token khi trạng thái IAM thay đổi |
| Passkey / xác thực chống phishing phù hợp | Có thể nhanh hơn nhập mật khẩu+OTP | Giảm rủi ro phishing, cần quy trình enrollment/recovery |
| Step-up khi làm việc nhạy cảm | Ít thách thức vô ích | Xác minh mạnh đúng thời điểm rủi ro |
| Conditional access | Không áp dụng mức kiểm soát giống nhau cho mọi ngữ cảnh | Phụ thuộc độ tin cậy của tín hiệu thiết bị/risk |
| Session ngắn ở admin console | Giới hạn thời gian cửa sổ đặc quyền | Có thể gây gián đoạn nếu cấu hình quá ngắn |
| Recovery xác minh chặt | Giảm lạm dụng mở khóa | Phải có kênh hỗ trợ khi người hợp lệ mất thiết bị |

Ví dụ người dùng đang đọc báo cáo thường không cần bị hỏi MFA liên tục nếu đã có session hợp lệ. Khi chuyển sang phê duyệt thay đổi quyền quản trị, hệ thống có thể yêu cầu step-up với mức bảo đảm phù hợp. Tuy nhiên, **tài khoản đã Leaver không được đi qua step-up để tự trở lại trạng thái active**.

## 8. RBAC/ABAC: sự đơn giản và độ chính xác

RBAC dễ giải thích, kiểm toán và triển khai cho những nhóm vai trò ổn định; ABAC giúp mô tả điều kiện tinh hơn như vùng dữ liệu, loại hợp đồng, dự án, mức bảo mật và thời gian.

| Cách tiếp cận | Ưu điểm | Chi phí / rủi ro |
|---|---|---|
| RBAC đơn giản | Dễ hiểu, phê duyệt và rà soát | Role explosion khi cố biểu diễn mọi ngoại lệ |
| ABAC | Phân quyền sát ngữ cảnh, giảm nhu cầu tạo role nhỏ | Khó chẩn đoán khi thuộc tính thiếu, sai hoặc cache cũ |
| RBAC kết hợp ABAC | Role biểu diễn chức năng, attribute giới hạn phạm vi | Cần governance và test cả hai lớp |
| Quyền cấp trực tiếp | Nhanh cho trường hợp đặc biệt | Dễ nằm ngoài inventory và access review |

Ví dụ role `sales-reader` cho phép hành động `customer.read`, còn ABAC giới hạn `subject.region == resource.region`. Nhân viên Sales VN không được đọc khách hàng vùng khác dù có cùng role.

Để cân bằng trải nghiệm, nên có **giải thích quyết định** ở mức phù hợp: người dùng biết quyền đang thiếu hoặc cần manager duyệt, không phải chỉ nhận lỗi chung “Access denied”. Đối với log và chính sách nhạy cảm, không tiết lộ logic chi tiết giúp kẻ tấn công dò quyền.

## 9. Tài khoản dịch vụ: không ép quy trình của người lên máy

Machine identity, service principal và bot CI/CD thường xác thực bằng client credentials, chứng chỉ, workload federation hoặc credential được kiểm soát riêng. Không thể yêu cầu bot tự nhập OTP như người dùng.

Hướng thiết kế hợp lý:

1. Cấp danh tính máy riêng, không dùng tài khoản người chung cho automation.
2. Dùng credential ngắn hạn, workload federation hoặc rotation được quản lý khi phù hợp.
3. Chỉ cấp scope API cần dùng; tách quyền deploy, read secret và quyền quản trị hạ tầng.
4. Có owner chịu trách nhiệm, lịch rà soát và cơ chế bàn giao khi owner Mover/Leaver.
5. Giám sát hành vi bất thường, expiry và sai lệch quyền tại ứng dụng.

Khi nhân viên sở hữu bot nghỉ việc, thu hồi quyền của người đó và chuyển owner hợp lệ; không tự xóa bot khiến hệ thống triển khai ngừng hoạt động. Nếu secret dùng chung đã bị người cũ biết, chỉ thu hồi quyền đọc vault là chưa đủ: cần đánh giá rotation.

## 10. Quy trình yêu cầu quyền: tự phục vụ nhưng không tự duyệt

Một cổng **self-service access request** giúp giảm thời gian gửi ticket nếu được thiết kế đúng:

~~~mermaid
flowchart TD
    U[Người dùng yêu cầu quyền] --> C[Hiển thị quyền và lý do nghiệp vụ]
    C --> P[Policy engine: RBAC / ABAC / SoD]
    P -->|Không hợp lệ| D[Từ chối, giải thích và hướng dẫn]
    P -->|Cần duyệt| A[Manager / App owner / Security]
    P -->|Được cấp tự động theo policy| G[Provision]
    A -->|Duyệt có thời hạn| G
    A -->|Từ chối| D
    G --> R[SCIM / API readback]
    R --> V{Quyền thực tế đúng?}
    V -->|Có| N[Thông báo và audit]
    V -->|Không| E[Retry / Escalate]
~~~

Đối với quyền thông thường, tự động phê duyệt theo chính sách đã được tổ chức thông qua có thể phù hợp. Với quyền đặc biệt hoặc xung đột SoD, cần phê duyệt độc lập và thời hạn. Cổng nên có trạng thái `REQUESTED`, `PENDING_APPROVAL`, `PROVISIONING`, `VERIFIED` hoặc `FAILED` rõ ràng để người dùng biết việc gì đang diễn ra.

Tránh “tự phục vụ” biến thành **tự cấp mọi quyền**. Chức năng request chỉ tạo ý định; chính sách và bộ phận có thẩm quyền mới quyết định có cấp hay không.

## 11. Ngoại lệ, break-glass và lúc hệ thống IAM gặp sự cố

Mọi tổ chức cần cơ chế xử lý sự cố khi IdP, SCIM hoặc MFA không khả dụng, nhưng ngoại lệ không được trở thành con đường thường xuyên để bỏ qua kiểm soát.

| Tình huống | Phương án cân bằng |
|---|---|
| Nhân viên không có thiết bị MFA | Recovery có xác minh danh tính, giới hạn hiệu lực và audit |
| Connector SCIM bị lỗi | Giữ trạng thái pending, retry idempotent và escalation |
| Hệ thống quyền chưa đồng bộ | Không phát biểu thành công trước khi readback; thông báo ETA theo SLA thật |
| IdP gặp sự cố | Phương án dự phòng theo chính sách, kiểm tra deny/conditional access |
| Cần truy cập khẩn cấp | Break-glass có owner, giám sát, phạm vi, lý do và rà soát sau sự cố |
| Quyền dự án chỉ cần ngắn hạn | Time-bound entitlement, tự hết hạn và review |

Với quyền nhạy cảm, thiếu dữ liệu thuộc tính hoặc PDP không sẵn sàng thường cần tránh **fail-open**; tuy vậy phương án fail-safe phải được thiết kế cùng yêu cầu duy trì hoạt động và cơ chế khẩn cấp được phê duyệt. Không giả định một chế độ sự cố phù hợp mọi ứng dụng.

## 12. Đo lường trải nghiệm và rủi ro bằng dữ liệu

Muốn cải tiến IAM phải theo dõi cả **friction** và **security outcomes**.

| Nhóm | Metric | Cách hiểu |
|---|---|---|
| Joiner | Time-to-first-approved-access | Từ thời điểm được phép bắt đầu đến lúc quyền thiết yếu hoạt động |
| Mover | Role-transition completion time | Từ thay đổi có hiệu lực đến lúc quyền mới/thu hồi cũ hội tụ |
| Leaver | Verified deprovisioning latency | Từ effectiveAt đến khi không còn quyền bị cấm tại từng target |
| Xác thực | MFA challenge frequency / completion rate | Có gây gián đoạn quá mức hay không |
| Hỗ trợ | Account recovery success/time | Người dùng hợp lệ khôi phục an toàn ra sao |
| Cấp quyền | Request approval / provisioning latency | Chậm ở bước phê duyệt hay tích hợp |
| Bảo mật | Residual access findings | Quyền thừa thực tế sau JML hoặc access review |
| Chất lượng | Wrong-user changes / duplicate identities | Thao tác nhầm và provisioning trùng |
| Kiểm toán | Approval and evidence completeness | Tỷ lệ thay đổi quyền có đủ căn cứ và readback |

Không tối ưu một chỉ số bằng cách làm xấu chỉ số khác. Ví dụ giảm thời gian cấp quyền bằng cách tạm bỏ SoD có thể tăng số vi phạm; giảm số lần MFA bằng cách kéo dài session vô hạn có thể tăng thời gian truy cập tồn dư khi Leaver.

Một scorecard đơn giản:

~~~text
goal: minimize user friction
subject to:
  - no unauthorized grants above approved threshold
  - revocation SLA met for critical targets
  - all privileged grants approved and time-bounded
  - no critical access-review or audit gaps
  - recovery remains usable for legitimate identities
~~~

Ngưỡng phải được đặt bởi người chịu trách nhiệm rủi ro và hoạt động. Phép đo cần tách từng ứng dụng và loại danh tính, tránh để giá trị trung bình che khuất một nhóm có rủi ro cao.

## 13. Thiết kế thí nghiệm so sánh hai phương án IAM

Giả sử nhóm triển khai muốn thay đổi cách áp dụng MFA cho người dùng thông thường. Hai phương án để đánh giá trong sandbox:

| Yếu tố | Phương án A | Phương án B |
|---|---|---|
| Đăng nhập app thông thường | Thách thức MFA mỗi lần vào app | Dựa vào SSO session hợp lệ, đánh giá lại theo policy |
| Thao tác admin | MFA theo cấu hình chung | Step-up mạnh trước thao tác nhạy cảm |
| Người dùng bị Leaver | Chặn đăng nhập mới | Chặn đăng nhập mới và xác minh session/token hết quyền theo SLA |
| Audit | Log đăng nhập cơ bản | Log ngữ cảnh xác thực, step-up, thay đổi lifecycle và enforcement |

Không thể mặc định B an toàn hơn chỉ vì ít bước hơn. Học viên cần đo tỷ lệ hoàn tất đăng nhập, số lần challenge, tốc độ truy cập, khả năng chặn admin action không đủ assurance và độ trễ thu hồi session. Kết quả phải dựa vào thực thi thực tế và chính sách, không chỉ cảm nhận.

### Một ma trận thử tối thiểu

| ID | Tình huống | Kết quả kỳ vọng |
|---|---|---|
| UX01 | Active user truy cập app thường | Đăng nhập liền mạch khi đáp ứng policy |
| UX02 | Active user dùng assurance thấp vào admin console | Step-up hoặc DENY |
| UX03 | Joiner chưa effective | Không cấp truy cập sớm |
| UX04 | Mover đổi role, token cũ | Không còn quyền cũ sau SLA |
| UX05 | Leaver với session đang mở | Không truy cập vượt deadline |
| UX06 | Thiết bị mất trust | Quyết định phù hợp conditional access |
| UX07 | Người dùng mất MFA device | Recovery an toàn, đủ kiểm toán |
| UX08 | SCIM timeout khi cấp quyền | Retry không tạo trùng và trạng thái minh bạch |
| UX09 | Service bot chạy không tương tác | Xác thực máy đúng scope, không đòi OTP |
| UX10 | Reviewer thu hồi quyền cũ | API đích DENY sau remediation |

## 14. Ví dụ mô phỏng policy và trải nghiệm

Mã giả dưới đây thể hiện mục tiêu: dùng ngữ cảnh để quyết định cần thách thức thêm hay không, nhưng tuyệt đối không bỏ qua lifecycle state.

~~~python
def evaluate_sign_in(identity, request, policy):
    if identity.status not in policy.allowed_statuses:
        return "DENY"
    if request.at < identity.effective_at:
        return "DENY"

    if request.resource.is_privileged:
        if not request.auth_context.meets(policy.admin_assurance):
            return "STEP_UP"

    if not request.device.meets(policy.device_requirements(request.resource)):
        return "DENY_OR_STEP_UP"

    if request.session.is_valid_for(request, policy):
        return "ALLOW"
    return "AUTHENTICATE"
~~~

Đây là pseudocode, không phải policy engine chuẩn; `DENY_OR_STEP_UP` cần được thay bằng hành vi rõ ràng đã duyệt. Sau AuthN, ứng dụng vẫn phải chạy **authorization** theo RBAC/ABAC cho từng hành động và tài nguyên. Một phiên đăng nhập hợp lệ không cấp quyền quản trị mặc định.

## 15. Checklist đánh giá quyết định đánh đổi

Trước khi chấp nhận một thay đổi IAM, nhóm triển khai nên trả lời:

1. Nhóm người dùng và tài nguyên nào chịu tác động, với mức rủi ro ra sao?
2. Thay đổi giảm bao nhiêu bước không cần thiết, nhưng có tạo đường cấp/giữ quyền ngoài policy không?
3. Có giữ nguyên kiểm soát quyền khi Joiner chưa bắt đầu, Mover và Leaver không?
4. Session/token đã phát trước khi đổi trạng thái được xử lý thế nào?
5. Có thể dùng xác thực mạnh, passkey, step-up hoặc automation thay cho việc bỏ kiểm soát?
6. Có phương án phục hồi cho người hợp lệ và khẩn cấp cho vận hành không?
7. Ngoại lệ có approval, owner, phạm vi, thời hạn và audit không?
8. Có đo được quyền có hiệu lực tại hệ thống đích, đặc biệt role local và credential máy không?
9. Monitoring có phát hiện quyền tồn dư, sync failure, tài khoản mồ côi và lỗi SoD không?
10. Có kế hoạch rollout, đánh giá theo nhóm nhỏ và rollback an toàn khi phát hiện vi phạm không?

## 16. Bài thực hành tổng kết

Thiết kế chính sách IAM cho tổ chức giả định có HRIS, IdP/SSO, CRM qua SCIM, ứng dụng Finance và bot CI/CD. Người học được yêu cầu:

1. Chọn chính sách xác thực cho người dùng thông thường, admin, contractor và workload identity.
2. Mô tả onboarding để nhân viên được cấp quyền đúng ngày mà không phải chờ ticket không cần thiết.
3. Xây dựng quy tắc Mover chuyển Sales → Finance; nếu cần giữ quyền trong giai đoạn bàn giao, xác định ngoại lệ và expiry.
4. Viết tiêu chí Leaver để đảm bảo IdP, app local, session, token, API key và quyền quản lý bot được xử lý.
5. Thiết kế luồng yêu cầu quyền tự phục vụ với approval, SoD, SCIM readback và trạng thái minh bạch.
6. Tạo bảng đo ít nhất ba chỉ số tiện dụng và ba chỉ số bảo mật; chỉ rõ điều kiện không được vi phạm.
7. Diễn tập một tình huống mất thiết bị MFA, một SCIM timeout và một quyền CRM tồn dư sau Mover.
8. Viết quyết định thiết kế: rủi ro nào được giảm, ma sát nào được loại bỏ, rủi ro nào còn lại, owner và kế hoạch theo dõi.

Một phương án đạt yêu cầu khi giúp người hợp lệ làm việc với ma sát được kiểm soát **mà không nới lỏng việc xác minh, phê duyệt, phân quyền và thu hồi bắt buộc**. Trọng tâm của đánh đổi bảo mật–tiện dụng không phải chọn một trong hai, mà là thiết kế IAM theo ngữ cảnh và xác minh các kết quả thực tế qua toàn bộ vòng đời danh tính.
