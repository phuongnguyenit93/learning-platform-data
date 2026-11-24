# Access recertification

## 1. Access recertification là gì?

**Access recertification (rà soát và tái chứng nhận quyền truy cập)** là quy trình định kỳ hoặc theo sự kiện để người có trách nhiệm xác nhận rằng quyền truy cập hiện tại của một tài khoản vẫn cần thiết, đúng phạm vi và phù hợp với công việc hoặc mục đích sử dụng. Quy trình xem xét tài khoản, nhóm, role, entitlement, quyền trên ứng dụng, dữ liệu và hệ thống mà một danh tính đang được phép sử dụng.

Ví dụ: một nhân viên chuyển từ bộ phận kế toán sang vận hành. Họ vẫn cần truy cập hệ thống nhân sự, nhưng quyền duyệt thanh toán và xem dữ liệu ngân hàng có thể không còn phù hợp. Trong một đợt access review, quản lý và chủ sở hữu ứng dụng xác nhận quyền nào cần giữ, quyền nào phải giảm hoặc thu hồi.

Access recertification giúp phát hiện quyền tích lũy theo thời gian, tài khoản không còn người chịu trách nhiệm, quyền quản trị cấp tạm nhưng chưa thu hồi, và các quyền không còn phù hợp sau khi nhân viên đổi vai trò hoặc rời tổ chức.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, access recertification thuộc vòng đời danh tính và kiểm soát authorization. Đăng nhập thành công chỉ chứng minh người dùng kiểm soát credential; việc họ có còn cần hoặc được phép giữ quyền truy cập nào phải được đánh giá riêng.

## 2. Phân biệt access recertification với authentication và provisioning

Các hoạt động này có liên quan nhưng giải quyết các câu hỏi khác nhau:

| Hoạt động | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ai đang sử dụng tài khoản và họ có kiểm soát credential hợp lệ không? | Nhân viên đăng nhập bằng passkey. |
| **Authorization** | Chủ thể có được phép thực hiện thao tác trên tài nguyên này không? | API kiểm tra scope, role, tenant và ownership. |
| **Provisioning** | Cấp, thay đổi hoặc thu hồi quyền/tài khoản như thế nào? | Tạo tài khoản trong ứng dụng khi nhân viên bắt đầu làm việc. |
| **Access recertification** | Quyền đang tồn tại có còn đúng và cần thiết không? | Quản lý xác nhận nhân viên vẫn cần role kế toán. |
| **Identity proofing** | Bằng chứng nào xác lập danh tính của một người? | Kiểm tra giấy tờ và nguồn dữ liệu có thẩm quyền. |

Access recertification không phải một lần đăng nhập lại và cũng không tự động cấp quyền. Đây là hoạt động quản trị có bằng chứng: reviewer xem quyền cụ thể, ngữ cảnh và nhu cầu công việc, sau đó quyết định giữ, sửa hoặc thu hồi.

Một quyết định recertification cũng không thay thế authorization ở runtime. API vẫn phải kiểm tra quyền mỗi lần truy cập; một báo cáo review được phê duyệt không nên trở thành lý do bỏ qua kiểm tra policy tại service.

## 3. Vì sao quyền truy cập cần được rà soát?

Quyền thường được cấp khi người dùng bắt đầu công việc hoặc cần hoàn thành một nhiệm vụ. Theo thời gian, quyền có thể tích lũy vì:

- Người dùng chuyển nhóm, vai trò, quản lý hoặc địa điểm làm việc.
- Dự án kết thúc nhưng quyền tạm thời vẫn còn.
- Người dùng được thêm vào nhiều nhóm và các nhóm kế thừa role khác nhau.
- Tài khoản đặc quyền được cấp khẩn cấp nhưng không được thu hồi đúng hạn.
- Ứng dụng hoặc hệ thống thay đổi cấu trúc quyền mà không cập nhật hồ sơ người dùng.
- Tài khoản nhà thầu, đối tác hoặc nhân viên nghỉ việc vẫn hoạt động.
- Service account, API key hoặc workload identity không còn owner rõ ràng.
- Quyền truy cập dữ liệu nhạy cảm vẫn tồn tại sau khi mục đích sử dụng kết thúc.

Rà soát định kỳ giúp phát hiện những sai lệch không được xử lý bởi luồng provisioning thông thường. Nó cũng tạo bằng chứng cho quản trị nội bộ, kiểm toán và việc chứng minh rằng quyền được cấp theo nhu cầu công việc.

## 4. Phạm vi của một access review

Một chiến dịch review cần xác định rõ những đối tượng nào được đưa vào phạm vi. Không chỉ rà soát tài khoản người dùng; nhiều quyền có thể được cấp thông qua nhóm, role, service principal hoặc quan hệ kế thừa.

| Đối tượng | Nội dung cần rà soát |
| --- | --- |
| Human user | Tài khoản nhân viên, nhà thầu, cộng tác viên và đối tác. |
| Privileged account | Tài khoản quản trị, tài khoản break-glass và quyền elevated. |
| Group membership | Nhóm trực tiếp, nhóm lồng nhau và quyền kế thừa. |
| Application role | Role trong ứng dụng, tenant và môi trường. |
| Entitlement | Quyền cụ thể như đọc, sửa, xuất, phê duyệt hoặc xóa dữ liệu. |
| Service account | Tài khoản dịch vụ, API client và workload identity. |
| Certificate/API key | Credential máy có quyền truy cập tài nguyên. |
| External identity | Danh tính đối tác, nhà cung cấp và người dùng federated. |
| Data access | Quyền trên database, bucket, dashboard, file và tập dữ liệu nhạy cảm. |

Review cần xem cả quyền trực tiếp lẫn quyền có được thông qua nhóm, role mapping hoặc policy. Nếu chỉ hiển thị danh sách group mà không giải thích các entitlement được kế thừa, reviewer khó đưa ra quyết định có ý nghĩa.

Phạm vi phải có ranh giới: hệ thống, tenant, môi trường, loại tài khoản, loại quyền và khoảng thời gian dữ liệu được lấy. Không nên gộp quyền production và development thành một mục chung nếu mức rủi ro và owner khác nhau.

## 5. Ai chịu trách nhiệm review?

Một chiến dịch tốt phân biệt người sở hữu quyền, người hiểu nhu cầu nghiệp vụ và người có quyền thực thi quyết định.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Line manager** | Xác nhận quyền có phù hợp với nhiệm vụ hiện tại của nhân viên không. |
| **Application owner** | Giải thích ý nghĩa role/entitlement và tác động khi giữ hoặc thu hồi. |
| **Data owner** | Xác nhận quyền truy cập dữ liệu nhạy cảm có đúng mục đích không. |
| **Resource owner** | Xác nhận nhu cầu truy cập tài nguyên hoặc hệ thống cụ thể. |
| **Security/IAM team** | Thiết kế policy, phạm vi, workflow, escalation và giám sát chất lượng review. |
| **Auditor/compliance** | Kiểm tra bằng chứng và tính toàn vẹn của quy trình theo quyền được cấp. |
| **User/credential owner** | Cung cấp thông tin cần thiết về mục đích sử dụng, không tự phê duyệt quyền của chính mình khi có xung đột. |

Người review phải hiểu quyền đang phê duyệt. Một nút “Approve all” cho hàng trăm entitlement không có mô tả, owner hoặc mức rủi ro dễ dẫn đến rubber-stamping.

Không nên để người dùng tự phê duyệt quyền đặc quyền của chính họ. Với quyền xung đột nhiệm vụ hoặc quyền truy cập dữ liệu rất nhạy cảm, có thể yêu cầu phê duyệt kép từ manager và data/application owner.

## 6. Khi nào cần chạy access recertification?

Có thể kết hợp chu kỳ định kỳ với các sự kiện làm thay đổi nhu cầu truy cập:

- **Periodic review:** theo tháng, quý, nửa năm hoặc năm, tùy rủi ro.
- **Joiner/mover/leaver:** khi bắt đầu làm việc, chuyển vai trò hoặc rời tổ chức.
- **Project end:** khi dự án, hợp đồng hoặc quyền truy cập tạm thời kết thúc.
- **Privileged access review:** thường xuyên hơn với quyền quản trị và break-glass.
- **Sensitive data review:** khi có quyền đọc/xuất dữ liệu cá nhân, tài chính hoặc bí mật kinh doanh.
- **Incident-driven review:** sau sự cố, nghi ngờ chiếm tài khoản hoặc phát hiện lạm dụng quyền.
- **Application change:** khi role, entitlement hoặc kiến trúc hệ thống thay đổi đáng kể.
- **Ownership change:** khi quản lý, data owner hoặc application owner thay đổi.

Tần suất phải dựa trên rủi ro, tốc độ thay đổi quyền và yêu cầu quản trị. Không có một lịch duy nhất phù hợp cho mọi hệ thống. Tài khoản đặc quyền và quyền truy cập dữ liệu có tác động cao cần chu kỳ ngắn hơn quyền thông thường ít nhạy cảm.

## 7. Chuẩn bị dữ liệu trước khi mở chiến dịch

Chất lượng review phụ thuộc vào dữ liệu quyền chính xác và dễ hiểu. Trước khi gửi nhiệm vụ cho reviewer, IAM hoặc application owner cần:

1. Đồng bộ danh sách principal và trạng thái tài khoản từ nguồn danh tính có thẩm quyền.
2. Thu thập quyền trực tiếp, group membership, nested group, role và entitlement kế thừa.
3. Xác định owner của từng ứng dụng, tài nguyên và quyền.
4. Gắn metadata như môi trường, tenant, mức nhạy cảm, ngày cấp, ngày hết hạn và nguồn cấp.
5. Phát hiện tài khoản không có owner, group không rõ mục đích và quyền không còn được sử dụng.
6. So sánh dữ liệu từ identity governance với trạng thái thực tế ở hệ thống đích.
7. Loại trừ bản ghi trùng hoặc đánh dấu xung đột để xử lý trước review.

Không nên yêu cầu manager xác nhận dữ liệu không đầy đủ. Nếu hệ thống không biết role có quyền gì hoặc không biết ai sở hữu ứng dụng, hãy chuyển bản ghi cho owner xử lý thay vì biến nó thành một checkbox mơ hồ.

## 8. Các quyết định trong một review

Mỗi entitlement nên có quyết định rõ ràng và lý do:

| Quyết định | Ý nghĩa |
| --- | --- |
| **Approve/Retain** | Giữ quyền vì vẫn cần thiết và phù hợp. |
| **Revoke/Remove** | Thu hồi quyền vì không còn cần, sai phạm vi hoặc có rủi ro. |
| **Modify/Reduce** | Giảm role hoặc chuyển sang entitlement ít quyền hơn. |
| **Time-bound exception** | Giữ quyền tạm thời với owner, lý do và ngày hết hạn cụ thể. |
| **Escalate** | Chuyển tới application/data/security owner khi reviewer không đủ thông tin hoặc có xung đột. |
| **Unable to determine** | Chưa đủ bằng chứng để quyết định; cần bổ sung thông tin trước deadline. |

Không nên coi việc reviewer không phản hồi là một quyết định approve. Policy có thể quy định thu hồi hoặc tạm ngưng một số quyền khi quá hạn, nhưng phải có thông báo, escalation, grace period phù hợp và phương án xử lý ngoại lệ để tránh gián đoạn vận hành không dự kiến.

Quyết định giữ quyền cũng cần lý do phù hợp, nhất là với quyền đặc quyền. “Đã có từ trước” hoặc “có thể cần trong tương lai” không phải là bằng chứng đủ mạnh cho quyền lâu dài.

## 9. Đánh giá quyền theo least privilege và separation of duties

Reviewer nên đánh giá mỗi quyền theo nguyên tắc **least privilege**: chỉ giữ quyền tối thiểu cần thiết cho nhiệm vụ hiện tại, trong thời gian cần thiết.

Các câu hỏi hữu ích:

- Người dùng có thực hiện nhiệm vụ cần quyền này không?
- Có entitlement ít quyền hơn đáp ứng cùng nhu cầu không?
- Quyền có phạm vi đúng tenant, môi trường và dữ liệu không?
- Quyền có thời hạn hay đang tồn tại vô thời hạn?
- Có phương thức truy cập khác an toàn hơn, ví dụ just-in-time privileged access không?
- Người dùng có quyền tạo và tự phê duyệt giao dịch của chính mình không?

**Separation of duties (SoD)** ngăn một chủ thể nắm các quyền kết hợp có thể tạo ra xung đột, ví dụ vừa tạo nhà cung cấp vừa phê duyệt thanh toán cho nhà cung cấp đó. Review cần phát hiện tổ hợp quyền nguy hiểm, không chỉ đánh giá từng role một cách độc lập.

Nếu ngoại lệ SoD là cần thiết, phải có lý do nghiệp vụ, phạm vi, biện pháp bù đắp, người phê duyệt và ngày hết hạn. Không để ngoại lệ trở thành quyền vĩnh viễn không được rà soát.

## 10. Đánh giá quyền đặc quyền và tài khoản phi con người

### 10.1. Privileged access

Quyền quản trị có thể thay đổi cấu hình, tạo tài khoản, đọc bí mật hoặc tắt kiểm soát bảo mật. Vì vậy, review cần xem:

- Ai là owner và vì sao cần quyền quản trị?
- Có dùng tài khoản quản trị riêng, tách khỏi tài khoản làm việc thường ngày không?
- Quyền có thể cấp just-in-time và tự hết hạn không?
- Có MFA/phishing-resistant authentication và audit đầy đủ không?
- Tài khoản break-glass có được kiểm tra sau mỗi lần sử dụng không?
- Có quyền nào không còn sử dụng hoặc không có owner không?

### 10.2. Service account và workload identity

Service account không có line manager như nhân viên. Reviewer cần là service owner, application owner hoặc nhóm chịu trách nhiệm workload. Kiểm tra:

- Workload nào đang dùng identity này?
- Owner kỹ thuật và owner nghiệp vụ là ai?
- Quyền có giới hạn đúng API, resource, tenant và môi trường không?
- Credential có được luân chuyển, giới hạn thời hạn và lưu trong secret manager không?
- Có key/certificate cũ, không dùng hoặc không rõ nguồn gốc không?
- Workload có còn tồn tại và còn cần quyền không?

Không tự động xóa service account chỉ vì không có hoạt động gần đây nếu chưa hiểu dependency. Nhưng tài khoản không owner hoặc quyền rộng phải được đưa vào quy trình xác minh và giảm rủi ro có thời hạn.

## 11. Risk-based access review

Không phải mọi entitlement có mức rủi ro như nhau. Risk engine có thể ưu tiên các mục cần reviewer chú ý:

- Quyền quản trị hoặc khả năng thay đổi policy.
- Quyền đọc, xuất hoặc chia sẻ dữ liệu nhạy cảm.
- Tài khoản không hoạt động trong thời gian dài.
- Quyền được cấp tạm nhưng đã quá hạn.
- Quyền mới được cấp gần đây hoặc thay đổi bất thường.
- Tài khoản không có manager/owner rõ.
- Tổ hợp quyền vi phạm SoD.
- Credential máy có scope rộng, không rotation hoặc không rõ owner.
- Tài khoản ngoài tổ chức hoặc nhà cung cấp có quyền production.

Một ma trận mẫu:

| Mức rủi ro | Ví dụ | Cách review |
| --- | --- | --- |
| **Cao** | Admin production, quyền xuất dữ liệu nhạy cảm, break-glass | Review thường xuyên, owner chuyên môn, có thể phê duyệt kép. |
| **Trung bình** | Role nghiệp vụ cho phép sửa dữ liệu hoặc phê duyệt quy trình | Manager và application owner xác nhận theo chu kỳ. |
| **Thấp** | Quyền đọc tài liệu nội bộ ít nhạy cảm | Review theo chu kỳ rộng hơn hoặc theo sự kiện. |

Điểm rủi ro chỉ là tín hiệu ưu tiên. Không tự động kết luận một người là rủi ro chỉ từ vị trí, thiết bị hoặc IP. Quyết định thu hồi cần dựa trên entitlement, nhu cầu công việc, nguồn dữ liệu và policy có thể giải thích.

## 12. Workflow của một access review campaign

~~~mermaid
flowchart TD
    A["Xác định scope và chu kỳ"] --> B["Thu thập identity, role và entitlement"]
    B --> C["Làm sạch dữ liệu, gắn owner và risk"]
    C --> D["Tạo review items và phân công reviewer"]
    D --> E["Reviewer xem quyền và ngữ cảnh"]
    E --> F{"Quyết định"}
    F -->|Giữ| G["Approve + lý do"]
    F -->|Thu hồi/giảm| H["Revoke hoặc modify request"]
    F -->|Thiếu thông tin| I["Escalate tới owner"]
    I --> E
    G --> J["Ghi nhận evidence"]
    H --> K["Provisioning thực thi"]
    K --> J
    J --> L["Reconcile trạng thái thực tế"]
    L --> M["Đóng campaign và báo cáo"]
~~~

Một campaign có thể triển khai theo các bước:

1. **Define:** xác định hệ thống, loại quyền, tenant, reviewer và deadline.
2. **Collect:** lấy snapshot quyền và metadata từ nguồn tin cậy.
3. **Assign:** phân công đúng người hiểu nhu cầu và có quyền quyết định.
4. **Review:** hiển thị quyền, mô tả, lý do cấp, lần dùng gần nhất và rủi ro.
5. **Decide:** ghi approve, revoke, modify, exception hoặc escalate.
6. **Enforce:** gửi quyết định tới provisioning workflow và hệ thống đích.
7. **Reconcile:** đọc lại trạng thái thực tế để xác nhận quyền đã thay đổi.
8. **Close:** tổng hợp kết quả, ngoại lệ còn mở và bằng chứng audit.

Không đóng campaign chỉ vì tất cả reviewer đã bấm nút. Các quyết định thu hồi phải được thực thi và đối chiếu ở hệ thống đích.

## 13. Thực thi quyết định và đồng bộ trạng thái

Quyết định trong công cụ review thường không trực tiếp thay đổi quyền tại mọi ứng dụng. Nó cần đi qua quy trình provisioning hoặc connector phù hợp.

Ví dụ, reviewer thu hồi một group membership:

1. Ghi quyết định và request ID.
2. Kiểm tra actor có quyền yêu cầu thay đổi trong tenant.
3. Gửi lệnh tới identity governance/provisioning service.
4. Provisioning service cập nhật group hoặc entitlement tại nguồn quản lý.
5. Connector đồng bộ thay đổi tới ứng dụng đích, có thể qua SCIM hoặc API riêng.
6. Hệ thống đọc lại trạng thái thực tế và ghi kết quả.
7. Nếu connector lỗi, giữ trạng thái pending, retry có giới hạn và escalation; không báo đã thu hồi khi chưa xác nhận.

~~~mermaid
sequenceDiagram
    participant R as Reviewer
    participant I as Identity governance
    participant P as Provisioning service
    participant A as Application
    participant E as Evidence store
    R->>I: Thu hồi entitlement
    I->>I: Kiểm tra quyền reviewer và policy
    I->>E: Lưu quyết định + request ID
    I->>P: Gửi revoke request
    P->>A: Cập nhật role/group
    A-->>P: Kết quả thực thi
    P-->>I: Trạng thái provisioning
    I->>A: Reconcile entitlement thực tế
    A-->>I: Trạng thái hiện tại
    I->>E: Ghi kết quả và thời điểm hoàn tất
~~~

Với hệ thống phân tán, cần idempotency, retry, dead-letter handling và đối chiếu định kỳ. Một lệnh revoke lặp không được tạo side effect ngoài dự kiến. Nếu ứng dụng đích không hỗ trợ thu hồi qua API, cần workflow thủ công có owner, deadline và bằng chứng hoàn tất.

## 14. Quản lý ngoại lệ và quyết định quá hạn

Một số quyền cần giữ tạm thời để tránh gián đoạn hoạt động, ví dụ quyền vận hành trong thời gian bàn giao. Ngoại lệ cần:

- Lý do nghiệp vụ cụ thể.
- Entitlement và phạm vi chính xác.
- Người phê duyệt độc lập phù hợp.
- Biện pháp bù đắp như giám sát tăng cường hoặc chỉ cho phép truy cập just-in-time.
- Ngày bắt đầu và ngày hết hạn.
- Người chịu trách nhiệm gia hạn hoặc thu hồi.
- Review lại trước khi hết hạn nếu vẫn cần tiếp tục.

Không cho phép ngoại lệ không có ngày hết hạn hoặc tự gia hạn vô thời hạn. Nếu reviewer không phản hồi, policy phải xác định escalation, thông báo và hành động mặc định theo mức rủi ro. Với quyền đặc quyền hoặc quyền truy cập dữ liệu rất nhạy cảm, có thể tạm ngưng khi hết grace period; với quyền vận hành quan trọng, cần đánh giá tác động và kế hoạch thay thế trước khi thu hồi.

## 15. Bằng chứng audit và chỉ số chất lượng

Một review cần lưu đủ bằng chứng để trả lời:

- Quyền nào đã được xem xét?
- Ai là reviewer và họ có thẩm quyền gì?
- Reviewer thấy dữ liệu nào tại thời điểm quyết định?
- Quyết định là gì, lý do và thời điểm nào?
- Có ngoại lệ, phê duyệt bổ sung hoặc xung đột SoD không?
- Quyết định thu hồi đã được thực thi ở hệ thống đích chưa?
- Trạng thái thực tế sau khi thực thi có khớp không?

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Review completion rate | Tỷ lệ review items được quyết định đúng hạn. |
| Revocation completion time | Thời gian từ quyết định tới khi quyền bị thu hồi thực tế. |
| Overdue privileged access | Số quyền đặc quyền chưa được review hoặc đã quá hạn. |
| Orphaned entitlement count | Số quyền không có owner hoặc không có mục đích rõ. |
| Exception age | Tuổi của ngoại lệ đang mở. |
| Reconciliation mismatch | Số trường hợp trạng thái công cụ review khác hệ thống đích. |
| Repeated approval rate | Tỷ lệ giữ quyền lặp lại không có lý do mới; tín hiệu cần kiểm tra chất lượng review. |

Audit phải có tính toàn vẹn, kiểm soát truy cập và retention policy. Không lưu secret, password, private key, token hoặc nội dung dữ liệu cá nhân không cần thiết trong review evidence.

## 16. Ví dụ dữ liệu review và logic xử lý

Một review item có thể được biểu diễn như sau:

~~~json
{
  "campaignId": "q4-prod-access-review",
  "principalId": "user-42",
  "tenantId": "tenant-a",
  "resource": "payments-production",
  "entitlement": "payment-approver",
  "grantedVia": "group-finance-leads",
  "risk": "high",
  "reviewerId": "manager-7",
  "decision": "revoke",
  "reason": "role-changed",
  "decidedAt": "2026-11-22T10:00:00Z",
  "executionStatus": "pending"
}
~~~

Đây là dữ liệu minh họa, không phải schema bắt buộc. Cần phân biệt `decision` với `executionStatus`: reviewer có thể đã quyết định revoke nhưng connector chưa thực thi xong.

Pseudocode xử lý quyết định:

~~~ts
async function applyAccessReviewDecision(item, actor) {
  await policy.assertCanReview(actor, item);
  await policy.assertReviewerIsNotSubject(actor, item);

  const decision = await reviewStore.recordOnce({
    itemId: item.id,
    actorId: actor.id,
    decision: item.decision,
    reason: item.reason
  });

  if (decision.action === "revoke" || decision.action === "modify") {
    await provisioning.enqueue({
      requestId: decision.requestId,
      principalId: item.principalId,
      tenantId: item.tenantId,
      entitlementId: item.entitlementId,
      action: decision.action
    });
  }

  return decision;
}
~~~

Đây là pseudocode khái niệm. Production cần kiểm tra quyền reviewer, xung đột SoD, tenant, version của entitlement, idempotency, approval bổ sung và trạng thái provisioning. Sau khi enqueue, worker phải thực thi, retry có giới hạn và reconcile với ứng dụng đích.

## 17. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi login thành công là quyền còn hợp lệ | Quyền cũ tiếp tục tồn tại dù nhiệm vụ đã thay đổi. | Rà soát entitlement theo vòng đời và nhu cầu hiện tại. |
| Chỉ review group name, không hiển thị quyền kế thừa | Reviewer không hiểu tác động thực tế. | Hiển thị role/entitlement hiệu lực và nguồn cấp. |
| Giao reviewer không hiểu ứng dụng | Quyết định approve/revoke thiếu cơ sở. | Phân công manager, application owner hoặc data owner phù hợp. |
| Cho reviewer tự phê duyệt quyền của mình | Xung đột lợi ích và quyền không được kiểm soát. | Separation of duties và phê duyệt độc lập. |
| Mặc định không phản hồi là approve | Quyền dư thừa tiếp tục tồn tại. | Deadline, escalation và default action theo risk policy. |
| Thu hồi trên công cụ nhưng không kiểm tra ứng dụng đích | Quyền thực tế vẫn còn. | Provisioning status và reconciliation. |
| Xóa service account không owner ngay lập tức | Có thể làm gián đoạn workload quan trọng. | Xác định owner/dependency và xử lý có kiểm soát, có deadline. |
| Ngoại lệ không có expiry | Quyền tạm thời trở thành vĩnh viễn. | Bắt buộc owner, lý do và ngày hết hạn. |
| Chỉ review người dùng, bỏ qua API key/workload | Danh tính máy có quyền rộng không được kiểm soát. | Đưa non-human identities vào scope review. |
| Dùng hoạt động gần nhất làm bằng chứng duy nhất | Quyền cần thiết nhưng ít dùng có thể bị thu hồi nhầm. | Kết hợp usage, job role, owner và mục đích nghiệp vụ. |
| Đóng campaign trước khi thực thi revoke | Báo cáo không phản ánh trạng thái thật. | Chỉ đóng khi reconcile hoặc ghi rõ pending exception. |
| Không lưu snapshot và lý do quyết định | Không thể tái dựng bằng chứng audit. | Lưu reviewer, context, decision, reason và execution evidence. |

## 18. Checklist triển khai access recertification

Trước khi chạy chiến dịch review, hãy kiểm tra:

1. Scope có bao gồm human user, privileged account, group, role, entitlement và non-human identity phù hợp không?
2. Nguồn dữ liệu có chính xác, mới và có thể đối chiếu với hệ thống đích không?
3. Mỗi entitlement có mô tả, owner, nguồn cấp, tenant, môi trường và mức rủi ro không?
4. Reviewer có đủ hiểu biết và thẩm quyền cho loại quyền đang xét không?
5. Có ngăn người dùng tự phê duyệt quyền của chính mình và xử lý SoD conflict không?
6. Tần suất review có dựa trên rủi ro và trigger vòng đời không?
7. Quyết định approve/revoke/modify/exception/escalate có ngữ nghĩa và lý do rõ ràng không?
8. Quyền đặc quyền, dữ liệu nhạy cảm, tài khoản ngoài tổ chức và service account có được ưu tiên không?
9. Ngoại lệ có owner, biện pháp bù đắp và ngày hết hạn không?
10. Quyết định thu hồi có được gửi tới provisioning workflow với idempotency và audit không?
11. Có reconcile trạng thái thực tế ở ứng dụng đích trước khi đóng campaign không?
12. Quy trình quá hạn có escalation và default action theo mức rủi ro không?
13. Evidence có lưu snapshot, reviewer, context, decision, reason và execution result không?
14. Có theo dõi thời gian thu hồi, quyền không owner, ngoại lệ quá hạn và mismatch không?
15. Có kiểm thử nested groups, quyền kế thừa, tenant isolation, connector lỗi, retry và race condition không?

**Kết luận:** Access recertification xác nhận quyền truy cập còn cần thiết và đúng phạm vi trong suốt vòng đời tài khoản. Quy trình hiệu quả phải có dữ liệu entitlement đầy đủ, reviewer hiểu quyền, quyết định có lý do, ngoại lệ có thời hạn và provisioning được đối chiếu ở hệ thống đích. Cần rà soát cả tài khoản đặc quyền lẫn service/workload identity; authentication thành công không có nghĩa quyền cũ luôn còn hợp lệ.
