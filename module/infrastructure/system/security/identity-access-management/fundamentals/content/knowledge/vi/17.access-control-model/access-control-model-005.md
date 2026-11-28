# Distributed authorization

## 1. Phân quyền khi một yêu cầu đi qua nhiều dịch vụ

Distributed authorization là việc tổ chức kiểm tra và thực thi quyền trong một hệ thống có nhiều thành phần, nơi danh tính, policy, dữ liệu quan hệ và tài nguyên được quản lý ở những vị trí khác nhau.

Một yêu cầu có thể đi qua API gateway, dịch vụ nghiệp vụ, bộ đánh giá policy và kho dữ liệu. Khi tạo công việc nền, nó còn đi qua hàng đợi và workload xử lý sau. Mỗi bước cần biết mình đang kiểm soát quyền gì và có thể tin dữ kiện nào.

Ví dụ, Lan yêu cầu xuất một hóa đơn:

~~~text
Lan
-> Gateway
-> ReportService
-> InvoiceService
-> ObjectStorage
-> Lan tải kết quả
~~~

Gateway nhận diện Lan và giới hạn tuyến API. ReportService kiểm tra quyền tạo tác vụ. InvoiceService kiểm tra quyền trên đúng hóa đơn. Kho lưu trữ bảo vệ tệp xuất. Một lần cho phép ở đầu luồng chưa tự giải quyết toàn bộ quyền ở các bước sau.

Bài toán gồm ba phần gắn với nhau:

- Policy và dữ liệu quyền phải được quản lý có nguồn chuẩn rõ ràng.
- Thành phần quyết định phải có đủ ngữ cảnh đáng tin cậy và đủ mới.
- Điểm thực thi phải chặn đúng thao tác, kể cả khi có lỗi hoặc đường gọi khác.

Phân quyền phân tán có thể dùng RBAC, ABAC, ReBAC hoặc phối hợp các mô hình đó. “Phân tán” mô tả kiến trúc và ranh giới thực thi; nó không quy định hệ thống phải dùng một mô hình quyền duy nhất.

Trong bài, các schema JSON, version, thuật toán và mã Java là thiết kế minh họa của một ứng dụng hóa đơn. Chúng không phải giao thức chung bắt buộc cho mọi sản phẩm.

## 2. Vì sao việc tách dịch vụ làm phân quyền khó hơn?

Trong một ứng dụng đơn giản, lớp service có thể đọc vai trò người dùng, metadata tài nguyên và dữ liệu cần xử lý trong cùng một tiến trình. Khi tách hệ thống, những dữ kiện này có thể thuộc các dịch vụ khác nhau:

| Dữ kiện | Chủ thể quản lý trong ví dụ |
|---|---|
| Danh tính và phiên của Lan | IdentityProvider và tầng xác thực |
| Membership của tenant | OrganizationService |
| Vai trò và phạm vi chức năng | Hệ thống quản lý quyền |
| Tenant, owner, mức phân loại hóa đơn | InvoiceService |
| Quan hệ chia sẻ và ủy quyền | RelationStore |
| Policy đã được phê duyệt | PolicyRepository |
| Tệp xuất và quyền tải | ReportService, ObjectStorage |

Một quyết định đúng cần kết hợp các dữ kiện phù hợp mà không biến mọi request thành một chuỗi gọi mạng không giới hạn.

Các vấn đề mới xuất hiện:

- Dữ liệu quyền được đọc từ các thời điểm khác nhau.
- Một dịch vụ không biết đầy đủ ý nghĩa tài nguyên của dịch vụ khác.
- Danh tính người dùng có thể bị thay bằng quyền rộng của workload.
- Các bản policy được triển khai lệch phiên bản.
- Cache tiếp tục giữ Permit sau khi thu hồi.
- Lỗi mạng khiến bộ đánh giá không trả được quyết định.
- REST, GraphQL, job nền và đường quản trị có thể dùng các cơ chế kiểm tra khác nhau.

Không thể giải quyết tất cả bằng việc đặt thêm một role vào token. Token có thể giúp truyền danh tính và một số thuộc tính, nhưng quyền trên tài nguyên hiện hành còn phụ thuộc nguồn dữ liệu và ngữ nghĩa của thao tác.

## 3. Tách trách nhiệm: quản trị, quyết định và thực thi

Các vai trò logic thường dùng:

| Vai trò | Trách nhiệm |
|---|---|
| PAP — Policy Administration Point | Quản lý, kiểm thử, phê duyệt và phát hành policy |
| PDP — Policy Decision Point | Đánh giá yêu cầu quyền theo policy và dữ kiện |
| PEP — Policy Enforcement Point | Giữ hoặc chặn thao tác dựa trên quyết định hợp lệ |
| PIP — Policy Information Point | Cung cấp thuộc tính hoặc dữ liệu cần để đánh giá |

Một vai trò có thể được triển khai bằng nhiều instance. Nhiều vai trò cũng có thể cùng nằm trong một dịch vụ. Phân chia logic giúp làm rõ trách nhiệm, không bắt buộc một số lượng tiến trình cụ thể.

Có thể quản lý policy tập trung về mặt logic rồi phân phối tới nhiều PDP gần dịch vụ. Cũng có thể vận hành một cụm PDP từ xa phục vụ nhiều PEP.

~~~mermaid
flowchart TB
    P["Quản trị policy: kiểm thử, phê duyệt, phát hành"]
    P --> D1["PDP của InvoiceService"]
    P --> D2["PDP của ReportService"]
    I["Nguồn danh tính, thuộc tính và quan hệ"]
    I --> D1
    I --> D2
    C["Client"] --> G["Gateway PEP"]
    G --> S1["InvoiceService PEP"]
    G --> S2["ReportService PEP"]
    S1 --> D1
    S2 --> D2
    S2 --> S1
    S1 --> R["Kho hóa đơn"]
~~~

Các mũi tên từ quản trị tới PDP biểu diễn phân phối policy, không có nghĩa mọi request nghiệp vụ phải đi qua hệ thống phát hành policy.

Cần bảo vệ cả hai đường:

**Đường quản trị:** ai được sửa policy, nguồn nào được tin, phiên bản nào được triển khai.

**Đường xử lý request:** ai được hỏi quyền, dữ kiện nào được chấp nhận và PEP có thực thi đúng hay không.

Một PDP chính xác nhưng nhận policy từ nguồn không được kiểm soát vẫn có thể cấp quyền sai. Một bộ policy chuẩn nhưng bị PEP bỏ qua cũng không bảo vệ tài nguyên.

## 4. Những cách triển khai PDP

| Cách triển khai | Đặc điểm | Điều cần quản lý |
|---|---|---|
| Thư viện hoặc bộ đánh giá nhúng | Quyết định trong cùng tiến trình ứng dụng | Cập nhật engine, policy và cách tích hợp theo từng ngôn ngữ |
| Sidecar hoặc agent gần ứng dụng | Gọi bộ đánh giá cục bộ, vòng đời tách tương đối với ứng dụng | Tài nguyên vận hành, readiness và phân phối dữ liệu |
| Dịch vụ PDP từ xa | Nhiều PEP gọi một cụm đánh giá dùng chung | Độ trễ mạng, khả năng mở rộng, sẵn sàng và cô lập tenant |
| Kết hợp | Luật ổn định đánh giá local, dữ liệu động từ dịch vụ chuyên trách | Hợp đồng phối hợp, độ mới và cách xử lý thiếu dữ liệu |

[Tài liệu triển khai OPA](https://www.openpolicyagent.org/docs/deploy) mô tả OPA ở vai trò PDP và các lựa chọn sidecar hoặc dịch vụ tập trung. Vị trí gần PEP giảm chi phí gọi mạng cho phần đánh giá cục bộ; lựa chọn từ xa cũng có trường hợp phù hợp.

Bảng trong bài mở rộng thành các phương án kiến trúc để phân tích ứng dụng. Không có phương án nào tự bảo đảm mọi thuộc tính đều mới hoặc mọi lần thu hồi đều có hiệu lực ngay.

Ví dụ, sidecar có thể đánh giá policy rất nhanh nhưng vẫn dùng membership cũ được đồng bộ từ hôm trước. Một PDP từ xa có dữ liệu quyền mới vẫn không giúp nếu PEP tái dùng một Permit cũ trong mười phút.

“Quản trị tập trung” cũng không đồng nghĩa “mọi quyết định chạy trên một máy duy nhất”. Có thể dùng nhiều replica, nhiều vùng hoặc PDP local, miễn là có hợp đồng rõ về phiên bản và dữ liệu.

Việc chọn vị trí nên dựa trên quyền cần kiểm tra, dữ kiện cần đọc, độ mới, độ trễ và khả năng vận hành. Chọn công cụ trước rồi ép mọi quyền vào một schema thường làm mất ngữ nghĩa nghiệp vụ.

## 5. Gateway, service mesh và quyền trên đối tượng nghiệp vụ

Gateway phù hợp với các kiểm soát ở cửa vào, chẳng hạn tuyến API, phương thức, loại client và yêu cầu xác thực. Proxy trong service mesh có thể kiểm soát kết nối giữa workload và một số điều kiện request.

[NIST SP 800-204B](https://csrc.nist.gov/pubs/sp/800/204/b/final) trình bày hướng dẫn xác thực và phân quyền cho microservices dùng service mesh, trong đó có xác thực giữa dịch vụ và ABAC. Đây là một nguồn tham khảo cho phần hạ tầng bảo vệ đường gọi.

Trong ứng dụng hóa đơn, vẫn cần xác định ai có dữ kiện để trả lời câu hỏi:

~~~text
Lan có được xuất hóa đơn inv-2048 của tenant acme
với trạng thái, mức phân loại và quan hệ chia sẻ hiện hành không?
~~~

Nếu gateway chỉ nhìn URL và token, nó có thể chưa biết hóa đơn thực sự thuộc tenant nào hoặc ai là owner. Dịch vụ quản lý tài nguyên thường phải tham gia dựng ngữ cảnh và thực thi ở độ chi tiết đó.

Một thiết kế minh họa:

- Gateway yêu cầu danh tính hợp lệ và chỉ cho client phù hợp gọi tuyến xuất báo cáo.
- ReportService kiểm tra quyền tạo job, phạm vi được yêu cầu và giới hạn sử dụng.
- InvoiceService kiểm tra workload gọi nó và quyền nghiệp vụ trên từng hóa đơn hoặc tập hóa đơn được xác định.
- Điểm tải tệp kiểm tra quyền lấy kết quả.

Mỗi kiểm soát trả lời một câu hỏi khác nhau. Không chuyển Permit của gateway thành một cờ trusted=true để bỏ mọi kiểm tra phía sau.

Cũng không cần lặp lại toàn bộ policy giống hệt ở mọi tầng. Nên phân công phần kiểm tra rõ ràng để tránh luật sao chép dần khác nhau.

## 6. Danh tính phải đi qua ranh giới dịch vụ một cách rõ ràng

Trong một lời gọi nội bộ, cần phân biệt:

~~~text
caller workload     = service:report-api
requesting subject  = user:lan
effective tenant    = acme
action              = invoice:export
target resource     = invoice:inv-2048
delegation          = grant:dg-501, nếu có
~~~

Danh tính workload cho biết dịch vụ nào đang gọi. Danh tính người dùng hoặc bên được đại diện giải thích yêu cầu nghiệp vụ đang được thực hiện cho ai.

Nếu InvoiceService chỉ nhìn quyền rộng của ReportService, một người dùng ít quyền có thể nhờ ReportService đọc dữ liệu vượt phạm vi. Dịch vụ có quyền trở thành nơi thực hiện yêu cầu cho bên không đủ thẩm quyền.

Ngữ cảnh đại diện phải được kiểm chứng qua cơ chế đã thiết kế, chẳng hạn credential phù hợp cho backend và quan hệ ủy quyền được xác nhận. Không coi header X-User-Id hoặc X-On-Behalf-Of tự khai là bằng chứng.

Danh tính được truyền qua proxy còn cần quy định rõ:

- Thành phần nào có quyền thiết lập hoặc thay đổi trường danh tính.
- Header nào bị loại khỏi request từ bên ngoài.
- Audience hoặc mục đích sử dụng credential.
- Cách ràng buộc actor với người được đại diện.
- Hạn sử dụng và quy tắc thu hồi.
- Trường nào chỉ phục vụ trace, không được dùng làm căn cứ quyền.

Tenant cũng phải được kiểm chứng. Client có thể chọn tenant muốn hoạt động, nhưng lựa chọn đó phải nằm trong membership được cấp. Tài nguyên được gọi vẫn phải thuộc đúng tenant hoặc một cơ chế chia sẻ chéo được policy công nhận.

Một workload chạy tác vụ hệ thống có thể hành động bằng quyền riêng của nó. Khi đó, policy phải mô tả hành động hệ thống rõ ràng, thay vì gán một người dùng giả hoặc mặc định mọi tác vụ nền là quản trị viên.

## 7. Một yêu cầu phân quyền cần mang những gì?

Request minh họa tới PDP:

~~~json
{
  "schemaVersion": "authz-input-v1",
  "requestId": "authz-729",
  "actor": {
    "workloadId": "service:report-api"
  },
  "subject": {
    "id": "user:lan",
    "tenantId": "acme",
    "attributeVersion": 42
  },
  "resource": {
    "type": "invoice",
    "id": "inv-2048",
    "tenantId": "acme",
    "securityVersion": 17
  },
  "action": "invoice:export",
  "environment": {
    "purpose": "customer-requested-export",
    "assurance": "mfa"
  },
  "requiredFreshness": {
    "relationFence": "opaque-relation-fence"
  }
}
~~~

Đây là hợp đồng riêng của ví dụ. Không mặc định một PDP bất kỳ đều nhận những field này.

Các nguyên tắc khi dựng request:

**Định danh tài nguyên phải có ngữ nghĩa ổn định.** invoice:inv-2048 và report:inv-2048 là hai loại tài nguyên khác nhau. Dùng URL tùy ý làm identity mà không chuẩn hóa có thể khiến cùng đối tượng được biểu diễn bằng nhiều tên.

**Action phải là thao tác được thực hiện thật.** invoice:read, invoice:export và invoice:approve không nhất thiết có cùng policy.

**Thuộc tính phải có nguồn đáng tin cậy.** Một chữ ký token hợp lệ chỉ chứng minh dữ liệu được issuer phát hành theo hợp đồng của token; nó không tự bảo đảm trạng thái tài khoản hiện tại chưa thay đổi.

**Chỉ truyền dữ liệu cần thiết.** PDP thường không cần toàn bộ nội dung hóa đơn để kiểm tra tenant, phân loại hoặc quyền được chia sẻ.

**Độ mới phải có định nghĩa.** Một field tên requiredFreshness chỉ có ý nghĩa nếu adapter và kho dữ liệu thực sự đáp ứng hoặc báo không thể đáp ứng.

Không bắt PDP tự đoán những field thiếu bằng cách đọc toàn bộ hệ thống. Nên xác định nguồn dữ kiện, yêu cầu bắt buộc và cách xử lý lỗi trong hợp đồng.

## 8. Quyết định cần gắn với ngữ cảnh đã được đánh giá

Phản hồi minh họa:

~~~json
{
  "schemaVersion": "authz-decision-v1",
  "requestId": "authz-729",
  "effect": "PERMIT",
  "policyRelease": "invoice-policy-r12",
  "evaluatedRelationFence": "opaque-evaluated-fence",
  "contextFingerprint": "fingerprint-of-canonical-request",
  "validUntil": "2026-11-26T04:00:30Z",
  "obligations": [
    {"id": "MASK_TAX_ID", "parameters": {}}
  ]
}
~~~

PEP cần kiểm chứng phản hồi đến từ PDP tin cậy, thuộc đúng request, đáp ứng hợp đồng và còn dùng được tại thời điểm thực thi.

contextFingerprint chỉ là một cơ chế ràng buộc của ứng dụng. Hai bên phải thống nhất chuẩn hóa dữ liệu và đưa vào đó các yếu tố ảnh hưởng đến quyết định. Hash không tự xác thực người gửi và không làm response trở thành credential an toàn để chuyển tùy ý.

Không dùng một Permit cấp cho invoice:read để thực hiện invoice:export. Không đổi resourceId hoặc tenant rồi giữ nguyên quyết định. Nếu dữ kiện bảo mật thay đổi, phải tuân thủ hợp đồng đánh giá lại hoặc kiểm tra version.

Nghĩa vụ đi kèm cũng phải được thực thi. Nếu Permit yêu cầu che mã số thuế nhưng dịch vụ không hỗ trợ, nó không được trả dữ liệu nguyên vẹn rồi ghi log cảnh báo.

Các dấu mốc từ những nguồn khác nhau không nhất thiết so sánh trực tiếp được. policyRelease, relationFence và securityVersion đại diện cho các trục khác nhau. Không chọn “số lớn nhất” giữa chúng rồi coi đó là một revision toàn hệ thống.

## 9. Phân phối policy và quản lý tương thích

Khi nhiều PDP cùng phục vụ, có thể tồn tại một giai đoạn một số instance dùng r11 và số khác dùng r12. Cần biết giai đoạn đó được phép hay phải chặn.

Một bản phát hành nên có:

- Nội dung policy có định danh hoặc checksum.
- Phiên bản schema đầu vào và đầu ra.
- Các nguồn dữ liệu và phiên bản tương thích.
- Bộ tình huống cho phép, từ chối và lỗi dự kiến.
- Điều kiện readiness và cách xác nhận đã nạp.
- Quy tắc rollback và xử lý thay đổi quyền khẩn cấp.

Một quy trình minh họa:

~~~text
Soạn policy
-> kiểm thử và xem xét
-> tạo artifact
-> xác minh nguồn và tính toàn vẹn
-> triển khai canary hoặc shadow phù hợp
-> xác nhận trạng thái các PDP
-> mở rộng phạm vi
~~~

Shadow evaluation cho phép so sánh quyết định mà chưa dùng kết quả mới để thực thi. Tuy nhiên, cần bảo vệ dữ liệu được gửi sang bộ đánh giá shadow và tính tới chi phí phát sinh.

Rollout có thể yêu cầu tương thích ngược giữa PEP và PDP. Nếu policy mới trả thêm nghĩa vụ bắt buộc mà PEP cũ không hiểu, việc vẫn trả Permit từ PDP không giải quyết được vấn đề tương thích.

Rollback policy cũng có tác động quyền. Quay lại bản cũ có thể mở lại một quyền vừa bị đóng. Vì vậy, rollback phải được xem xét theo kết quả phân quyền, không chỉ theo việc tiến trình có khởi động thành công.

Khi chưa nạp được một bộ policy được chấp nhận, instance không nên báo sẵn sàng phục vụ phần chức năng phụ thuộc vào bộ policy đó. Readiness của PDP còn cần phản ánh dữ liệu bắt buộc và độ mới theo hợp đồng của hệ thống.

## 10. Tính nhất quán: policy đúng nhưng dữ liệu có thể cũ

Một hệ thống phân tán có nhiều trục thay đổi:

| Trục dữ liệu | Ví dụ thay đổi |
|---|---|
| Policy | Bản r12 yêu cầu MFA cho export |
| Danh tính và membership | Lan bị gỡ khỏi nhóm finance |
| Quan hệ ReBAC | Grant chia sẻ hóa đơn bị thu hồi |
| Metadata tài nguyên | Hóa đơn đổi tenant hoặc mức phân loại |
| Phiên | Phiên đã hết hạn hoặc mức bảo đảm không còn đáp ứng |
| Workload | ReportService bị gỡ quyền gọi InvoiceService |

Cập nhật policy không tự cập nhật membership. Tăng version của tài nguyên cũng không tự làm mới trạng thái phiên.

Một quyết định phải dựa trên tổ hợp dữ kiện được hợp đồng chấp nhận. Tổ hợp đó có thể là snapshot nhất quán của một kho, hoặc nhiều nguồn với giới hạn độ mới được định nghĩa. Không tự coi mọi dữ kiện mới nhất ở từng nơi là một snapshot nguyên tử toàn hệ thống.

Ví dụ:

~~~text
T0: Lan có quyền đọc inv-2048.
T1: Quyền của Lan bị thu hồi.
T2: Một người khác thêm dữ liệu nhạy cảm mới vào hóa đơn.
T3: PEP dùng quyền trước T1 để trả nội dung sau T2.
~~~

Trong trường hợp này, độ mới của quyền phải được phối hợp với nội dung được bảo vệ.

Nghiên cứu [Zanzibar tại USENIX ATC 2019](https://www.usenix.org/conference/atc19/presentation/pang) trình bày một hệ thống phân quyền tôn trọng thứ tự nhân quả giữa thay đổi quyền và nội dung. Đây là ví dụ cho việc tính nhất quán của quyền là một yêu cầu kiến trúc, bên cạnh logic policy.

Ứng dụng minh họa có thể yêu cầu quyết định không được dùng dữ liệu quan hệ cũ hơn một mốc thay đổi đã biết. Cơ chế thực tế phụ thuộc kho quyền; một revision token có thể là giá trị opaque và không được tự so sánh bằng chuỗi.

Cần trả lời hai câu hỏi:

1. Ai biết mốc độ mới tối thiểu cần áp dụng?
2. PEP và PDP bảo đảm mốc đó bằng cơ chế gì?

Nếu chỉ để client tự gửi mốc mới sau khi bấm thu hồi, các client khác có thể vẫn dùng trạng thái cũ. Server phải bảo đảm yêu cầu độ mới được áp dụng trên các đường truy cập cần bảo vệ.

## 11. Cache và giới hạn hiệu lực quyết định

Cache có thể tồn tại ở gateway, ứng dụng, PDP, kho quan hệ và nguồn thuộc tính. Mỗi tầng giữ một loại dữ liệu khác nhau.

Một cache key chỉ gồm userId và role dễ bỏ sót tài nguyên, tenant hoặc action. Với ví dụ export, các phụ thuộc có thể gồm:

~~~text
subject và phiên bản thuộc tính
actor workload
tenant
resource type + id + security version
action
grant hoặc relation revision
policy release
các điều kiện môi trường liên quan
~~~

Không nhất thiết phải ghép mọi giá trị thành một chuỗi dài. Có thể dùng một cấu trúc khóa, fingerprint hoặc dependency index. Điều quan trọng là không dùng chung quyết định cho những ngữ cảnh có ý nghĩa quyền khác nhau.

Thời gian sống cache phải phù hợp với nguồn dữ liệu. Một Permit không được tồn tại lâu hơn một điều kiện bắt buộc đã hết hạn chỉ vì TTL cục bộ còn.

Các cách quản lý độ mới có thể phối hợp:

- TTL có giới hạn và được tính theo mốc hết hiệu lực gần nhất.
- Sự kiện thay đổi quan hệ hoặc thuộc tính.
- Epoch theo phạm vi tài nguyên hoặc tổ chức.
- Revision tối thiểu được yêu cầu khi kiểm tra.
- Không cache một số thao tác nhạy cảm.
- Đánh giá lại ở thời điểm quan trọng.

Sự kiện vô hiệu hóa có thể bị trễ, trùng hoặc đến sai thứ tự. TTL ngắn giúp giới hạn một số cửa sổ dữ liệu cũ nhưng không sửa một key thiếu action ngay từ đầu.

Cũng cần bảo vệ cache theo tenant và loại tài nguyên. Hai tenant dùng cùng mã hóa đơn không được chia sẻ kết quả quyền chỉ vì cùng resourceId dạng chuỗi.

Không dùng một quyết định đã hết hiệu lực làm fallback vô thời hạn khi PDP lỗi. Đó là thay đổi chính sách cấp quyền, không còn chỉ là tối ưu cache.

## 12. Độ trễ, lỗi phụ thuộc và khả năng phục vụ

Giả sử một request có ngân sách xử lý hữu hạn. Phân quyền phải nằm trong ngân sách đó thay vì được phép gọi mạng và retry không giới hạn.

Một đường xử lý có thể gồm:

~~~text
Đọc ngữ cảnh
+ gọi PDP
+ đọc dữ liệu phụ thuộc
+ thực hiện nghĩa vụ
+ thao tác nghiệp vụ
+ xuất kết quả
~~~

Nếu một PDP gọi ba nguồn dữ liệu tuần tự, đặt nó cạnh PEP chỉ giảm được một phần chi phí. Cần quan sát cả đường quyết định, không chỉ thời gian chạy biểu thức policy.

Trong thiết kế minh họa, ba nhóm kết quả được tách:

| Nhóm | Ý nghĩa | Hành vi đối với thao tác |
|---|---|---|
| Permit hợp lệ | Có căn cứ cấp quyền theo hợp đồng | Chỉ tiếp tục trong phạm vi được cấp |
| Deny theo policy | Ngữ cảnh không được policy cho phép | Chặn |
| Không thể quyết định hoặc phản hồi không dùng được | Timeout, thiếu dữ liệu, sai schema, chưa đủ độ mới | Không tự cấp quyền; phân loại lỗi phụ thuộc |

Không đồng nhất lỗi PDP với việc người dùng thiếu vai trò trong log vận hành. Một trường hợp cần sửa policy hoặc cấp quyền; trường hợp khác cần khôi phục hệ thống.

Các cơ chế vận hành có thể gồm deadline, giới hạn số request đồng thời, circuit breaker và retry có ngân sách. Retry cần giữ đúng ngữ cảnh hoặc đánh giá lại nếu dữ kiện đã đổi; tránh tạo ra bão gọi lại khi PDP quá tải.

Fallback local chỉ hợp lệ nếu nó có policy và dữ liệu đáp ứng yêu cầu của thao tác. Có thể tiếp tục đánh giá bằng artifact đã xác minh khi control plane tạm ngừng, nhưng vẫn phải xét tuổi dữ liệu và giới hạn thu hồi.

Tách control plane khỏi đường request có thể giúp dịch vụ tiếp tục phục vụ trong một số sự cố phân phối policy. Nó không chứng minh hệ thống còn đủ dữ kiện động để cấp mọi quyền.

Nếu có truy cập khẩn cấp, cần mô hình hóa thành một luồng quyền riêng có thẩm quyền, phạm vi và kiểm toán. Không ẩn “cho phép tất cả” trong nhánh catch lỗi mạng.

## 13. Ví dụ Java: một guard cho quyết định phân tán

Đoạn mã minh họa một ranh giới kiểm tra dùng chung. Các interface là hợp đồng ứng dụng, không phải API của OPA hoặc một engine cụ thể. Mã chưa phải một chương trình chạy độc lập.

~~~java
public final class DistributedAuthorizationGuard {

    private final PolicyClient client;
    private final DecisionContract contract;
    private final PolicyCompatibility compatibility;
    private final ObligationSupport obligationSupport;
    private final java.time.Clock clock;

    public DistributedAuthorizationGuard(
            PolicyClient client,
            DecisionContract contract,
            PolicyCompatibility compatibility,
            ObligationSupport obligationSupport,
            java.time.Clock clock) {
        this.client = client;
        this.contract = contract;
        this.compatibility = compatibility;
        this.obligationSupport = obligationSupport;
        this.clock = clock;
    }

    public AuthorizedOperation requirePermit(
            AuthorizationRequest request,
            EvaluationDeadline deadline) {

        final PolicyResponse response;

        try {
            response = client.evaluate(request, deadline);
        } catch (PolicyTransportFailure ex) {
            throw new AuthorizationUnavailable(
                    "Policy dependency unavailable", ex);
        }

        // Bao gồm schema, nguồn phản hồi, tương quan request,
        // ngữ cảnh và yêu cầu độ mới theo adapter của nhà cung cấp.
        contract.requireValidDecision(request, response);

        if (response.effect() == Effect.DENY) {
            throw new AccessRejected("Operation not permitted");
        }

        if (response.effect() != Effect.PERMIT) {
            throw new AuthorizationUnavailable(
                    "No usable authorization decision");
        }

        compatibility.requireAccepted(response.policyRelease());
        obligationSupport.requireSupported(response.obligations());

        if (!clock.instant().isBefore(response.validUntil())) {
            throw new AuthorizationUnavailable("Decision expired");
        }

        if (deadline.exhausted()) {
            throw new AuthorizationUnavailable(
                    "Authorization budget exhausted");
        }

        return new AuthorizedOperation(
                request,
                response.decisionId(),
                response.policyRelease(),
                response.evidence(),
                response.obligations(),
                response.validUntil()
        );
    }
}
~~~

Ý nghĩa các hợp đồng:

**AuthorizationRequest** là snapshot bất biến do server dựng từ danh tính và dữ liệu đáng tin cậy. Không chuyển nguyên request body của client thành dữ kiện đã xác minh.

**PolicyClient** gọi một endpoint được cấu hình và bảo vệ phù hợp. Client nghiệp vụ không được tự chọn PDP hoặc URL để cấp quyền cho chính mình.

**DecisionContract** kiểm tra cấu trúc, danh tính nguồn và phản hồi có áp dụng cho request hiện tại không. Với độ mới, adapter phải dùng cơ chế được nhà cung cấp hỗ trợ. Không thể chứng minh snapshot mới chỉ bằng việc nhìn một chuỗi tên evidence.

**PolicyCompatibility** kiểm tra bản policy được phép dùng trong giai đoạn rollout. Nó không so sánh các chuỗi version tùy ý rồi tự suy ra tính tương thích.

**ObligationSupport** chỉ xác nhận PEP có khả năng hiểu và thực hiện nghĩa vụ. Sau đó PEP vẫn phải thực hiện chúng thật sự.

**AuthorizedOperation** là dữ liệu dùng trong ranh giới thực thi của ứng dụng. Nó không mặc nhiên là bearer token có thể chuyển cho dịch vụ khác. Nếu cần truyền qua mạng, phải thiết kế giao thức và bằng chứng phù hợp.

Caller phải ràng buộc AuthorizedOperation với đúng thao tác đã yêu cầu. Ví dụ:

~~~text
Lấy metadata inv-2048
-> dựng AuthorizationRequest cho invoice:export
-> requirePermit
-> đọc đúng dữ liệu theo điều kiện version
-> thực hiện che field
-> kiểm tra điều kiện hiệu lực sát lúc công bố
-> trả kết quả
~~~

Guard không tự loại bỏ khoảng cách giữa kiểm tra và sử dụng. Tài nguyên có thể thay đổi sau khi nhận Permit; thao tác ghi cần cơ chế kiểm tra version hoặc giao dịch phù hợp, còn stream cần hợp đồng kiểm tra lại theo thời gian hoặc checkpoint.

Một tầng phía trên không được bắt AccessRejected rồi gọi thẳng repository để thử lại. Ranh giới thực thi phải bao phủ mọi đường đi tới thao tác được bảo vệ.

## 14. Kết hợp nhiều quyết định mà vẫn giữ đúng ngữ nghĩa

Một thao tác có thể cần đồng thời:

~~~text
Workload được phép gọi dịch vụ
AND người dùng được phép thực hiện nghiệp vụ
AND tài nguyên thuộc đúng phạm vi
AND policy toàn cục không chặn
~~~

Trong mô hình này, một Permit không bù được một điều kiện bắt buộc chưa đạt.

Một câu hỏi khác là người dùng có nhiều đường cấp quyền độc lập:

~~~text
owner
OR editor qua nhóm
OR grant được ủy quyền hợp lệ
~~~

Đó là các nhánh của policy quyền trên tài nguyên. Việc kết hợp các nhánh phải do policy hoặc evaluator xác định, thay vì từng dịch vụ tùy ý gộp boolean.

Không trộn hai loại quan hệ thành:

~~~text
gateway cho phép OR service cho phép
~~~

nếu cả hai tầng đều là kiểm soát bắt buộc. Cách gộp đó biến một tầng thành đường vượt qua tầng khác.

Lỗi trên một nhánh quyền cũng phải theo ngữ nghĩa bộ đánh giá. Nếu policy có một căn cứ độc lập đủ để cho phép, bộ đánh giá có thể có cách xử lý tương ứng; không để PEP tự suy đoán khi chỉ nhận một lỗi không rõ phạm vi.

Hợp đồng giữa các dịch vụ nên dùng action nghiệp vụ có tên rõ ràng. Hai dịch vụ cùng dùng chữ read nhưng một bên hiểu là xem vài trường, bên kia hiểu là tải toàn bộ dữ liệu sẽ tạo ra một lỗ hổng ngữ nghĩa dù schema vẫn khớp.

Với bulk API, cần ánh xạ từng kết quả về đúng tài nguyên và hành động. Không áp một Permit cho phần tử đầu lên mọi phần tử trong batch. Với danh sách, còn phải kiểm soát phạm vi truy vấn, trường dữ liệu, số lượng tổng và metadata phân trang.

## 15. Giao dịch và luồng bất đồng bộ qua nhiều dịch vụ

Một quyết định Permit tại thời điểm tạo request không phải bằng chứng quyền tồn tại vô thời hạn.

Ví dụ:

~~~text
Lan tạo export job lúc 09:00.
Grant bị thu hồi lúc 09:05.
Worker bắt đầu đọc hóa đơn lúc 09:10.
~~~

Ứng dụng phải chọn ngữ nghĩa rõ ràng:

- Worker cần quyền hiện hành tại thời điểm thực hiện.
- Hoặc job đã được cấp một quyền nhiệm vụ riêng có phạm vi, thời hạn và cơ chế hủy.

Không thay lựa chọn đó bằng một field authorized=true trong thông điệp rồi dùng mãi.

Cần phân biệt command với event:

| Loại thông điệp | Ý nghĩa | Vấn đề quyền cần xét |
|---|---|---|
| Command yêu cầu hành động sau | “Hãy xuất hóa đơn này” | Người yêu cầu hoặc quyền nhiệm vụ còn được phép khi thực hiện không? |
| Event thông báo việc đã xảy ra | “Hóa đơn đã được phê duyệt và commit” | Nguồn phát có đáng tin cậy, consumer có quyền xử lý và event có hợp lệ không? |

Thu hồi quyền sau khi một hóa đơn đã được phê duyệt không tự làm sự kiện lịch sử đó biến mất. Ngược lại, một command còn trong hàng đợi chưa thực hiện có thể cần kiểm tra lại.

Với thao tác ghi quan trọng, khoảng trống giữa đánh giá và commit phải được xử lý. Nếu dữ liệu quyền và tài nguyên cùng một kho có hỗ trợ phù hợp, có thể ràng buộc bằng version, khóa hoặc transaction. Nếu nằm ở nhiều hệ thống, transaction cục bộ không tự bao phủ toàn bộ đường đi.

Ví dụ một luồng phê duyệt rồi thanh toán cần xác định:

1. Dịch vụ nào quyết định quyền phê duyệt?
2. Khi nào phê duyệt được coi là đã chấp nhận?
3. Dịch vụ thanh toán tin bằng chứng nào?
4. Nếu quyền thay đổi giữa hai bước, thanh toán được tiếp tục hay phải dừng?
5. Nếu tác động bên ngoài đã xảy ra, có cơ chế bù trừ nào được nghiệp vụ cho phép?

Những câu hỏi này thuộc hợp đồng nghiệp vụ và nhất quán, không thể giải quyết chỉ bằng một retry PDP.

Truyền thông điệp cũng cần kiểm chứng nguồn, giới hạn phạm vi workload và xử lý idempotent. Quyền của producer được gọi một topic không tự có nghĩa mọi payload producer gửi đều được thực thi như lệnh quản trị.

## 16. Cô lập tenant và bảo vệ chính hệ thống phân quyền

Một dịch vụ phân quyền dùng chung có thể trở thành nơi tập trung thông tin nhạy cảm về tổ chức, tài nguyên và quan hệ người dùng.

Cần kiểm soát riêng các khả năng:

- Hỏi quyền cho một loại tài nguyên.
- Đọc hoặc liệt kê quan hệ.
- Tạo, sửa và thu hồi quan hệ.
- Phát hành hoặc rollback policy.
- Xem decision log và dữ liệu chẩn đoán.

Một PEP được hỏi “Lan có được đọc hóa đơn này không?” không mặc nhiên được liệt kê mọi thành viên và mọi tài nguyên trong tenant.

Định danh phải tránh va chạm giữa tenant:

~~~text
tenant:acme / invoice:2048
tenant:beta / invoice:2048
~~~

Hai hóa đơn có cùng mã cục bộ vẫn là hai tài nguyên khác nhau. Cache, relation store, API và audit phải cùng tôn trọng ranh giới đó.

Trong một thiết kế cho phép chia sẻ chéo tenant, quan hệ chia sẻ phải có nguồn cấp và policy rõ ràng. Không thể thực hiện bằng việc bỏ điều kiện tenant trên mọi truy vấn.

Giới hạn request và tài nguyên tính toán cũng quan trọng. Một truy vấn đồ thị quá sâu hoặc batch quá lớn có thể làm cạn tài nguyên PDP. Cần giới hạn phù hợp và không chuyển lỗi vượt giới hạn thành Permit.

Đường quản trị policy cần xác minh nguồn artifact và quyền ghi. Với sidecar local, API nạp policy hoặc cấu hình không nên mở cho client không được phép chỉ vì API đánh giá ở cùng host.

Tính tối thiểu của dữ liệu giúp giảm tác động khi log hoặc thành phần quyền bị lộ. Tránh gửi toàn bộ hồ sơ cá nhân, token hoặc nội dung hóa đơn nếu quyết định chỉ cần một số thuộc tính.

## 17. Audit phải nối được quyết định với thao tác thực tế

Một decision log cho biết PDP đã đánh giá gì. Một enforcement log cho biết PEP đã làm gì. Một business event cho biết nghiệp vụ đã đạt mốc nào.

Ba loại bằng chứng có thể liên kết bằng requestId hoặc traceId, nhưng không nên đồng nhất ý nghĩa.

~~~json
{
  "event": "authorization_enforced",
  "requestId": "authz-729",
  "traceId": "trace-836",
  "pep": "service:invoice-api",
  "actorWorkload": "service:report-api",
  "subject": "user:lan",
  "tenant": "acme",
  "resource": "invoice:inv-2048",
  "action": "invoice:export",
  "decisionId": "decision-551",
  "policyRelease": "invoice-policy-r12",
  "effect": "PERMIT",
  "enforcementResult": "masked_export_ready"
}
~~~

Sự kiện minh họa trên không khẳng định client đã tải xong. Tệp có thể đã sẵn sàng nhưng mạng bị lỗi trước khi trả kết quả.

Các câu hỏi cần trả lời khi điều tra:

- PEP nào đã cho thao tác đi tiếp?
- PDP và policy release nào tạo quyết định?
- Dữ kiện thuộc tính hoặc quan hệ ở phiên bản nào?
- Danh tính workload và người dùng thực tế là ai?
- Nghĩa vụ có được thực hiện không?
- Có đường quyền khác giải thích Permit không?
- Quyết định còn hiệu lực tại mốc thao tác cần bảo vệ không?

Các chỉ số hữu ích gồm độ trễ quyết định, tỷ lệ lỗi phụ thuộc, tuổi policy trên instance, độ mới dữ liệu quan hệ và số lần nghĩa vụ không thể thực hiện.

Nên theo dõi phân phối policy thực tế thay vì chỉ kiểm tra pipeline phát hành thành công. Một artifact đã được xuất bản không chứng minh tất cả PDP đã nạp hoặc có thể dùng nó.

Log phải tránh access token, cookie phiên và dữ liệu nghiệp vụ không cần thiết. Chính việc ai có quyền đối với tài nguyên nào cũng là thông tin cần bảo vệ.

Nếu một thao tác bắt buộc phải có bằng chứng audit bền vững trước khi thực hiện, cần triển khai hợp đồng đó riêng. Không mặc định một lời gọi log bất đồng bộ trong bộ nhớ đã đáp ứng yêu cầu.

## 18. Kiểm thử theo cả quyết định và đường thực thi

| Tình huống | Điều cần xác minh |
|---|---|
| Người dùng hợp lệ, workload hợp lệ, đủ quyền | Chỉ thao tác và tài nguyên được đánh giá được thực hiện |
| Workload không được gọi backend | Bị chặn dù người dùng có quyền nghiệp vụ |
| SubjectId hoặc tenantId tự khai | Không thay thế ngữ cảnh đã kiểm chứng |
| Cùng resourceId ở hai tenant | Không dùng chung cache hoặc quyền |
| Permit cho read dùng sang export | Bị chặn do khác action |
| PDP trả Deny | Không phát sinh thao tác được bảo vệ |
| PDP timeout hoặc sai schema | Không có nhánh cho phép vô điều kiện |
| Nghĩa vụ chưa được hỗ trợ | Không công bố dữ liệu không đáp ứng policy |
| PEP cũ nhận policy có output mới | Xử lý đúng hợp đồng tương thích |
| Instance chưa nạp policy bắt buộc | Không phục vụ như một PDP đã sẵn sàng |
| Thu hồi quyền rồi cập nhật nội dung | Không dùng quyền cũ để trả nội dung mới ngoài cam kết |
| Policy rollout lệch phiên bản | Hành vi đúng phạm vi phiên bản được chấp nhận |
| GraphQL hoặc endpoint quản trị gọi đường khác | Vẫn có điểm thực thi phù hợp |
| Batch có một phần tử bị từ chối | Ánh xạ kết quả đúng từng tài nguyên |
| Job chạy sau khi grant hết hiệu lực | Kiểm tra lại hoặc dùng quyền nhiệm vụ hợp lệ |
| Sự kiện nghiệp vụ đã commit rồi người dùng mất quyền | Xử lý lịch sử theo hợp đồng, không tự đảo ngược sự kiện |
| Một vùng không đọc được dữ liệu đủ mới | Không cấp quyền bằng bằng chứng ngoài giới hạn |
| Audit bắt buộc bị lỗi | Tuân thủ yêu cầu bền vững trước tác động |

Kiểm thử policy đơn lẻ giúp xác minh luật nhưng chưa chứng minh complete mediation — mọi đường truy cập đều được kiểm soát. Cần kiểm thử qua các PEP và đường dữ liệu thật.

Có thể dùng các nhóm kiểm thử khác nhau:

**Kiểm thử policy:** tổ hợp input và kết quả kỳ vọng.

**Kiểm thử hợp đồng:** schema, action, nghĩa vụ và phiên bản giữa PEP với PDP.

**Kiểm thử tích hợp:** quyết định dẫn tới đúng hành vi trên tài nguyên.

**Kiểm thử thay đổi trạng thái:** cấp quyền, thu hồi, đổi tenant, đổi owner và policy rollout.

**Kiểm thử lỗi:** timeout, nguồn thuộc tính mất kết nối, dữ liệu không đủ mới và artifact chưa sẵn sàng.

Với race condition, điều khiển thứ tự bằng các rào chắn kiểm thử sẽ hữu ích hơn chỉ gửi nhiều request ngẫu nhiên. Với cache và thời gian hết hạn, dùng nguồn thời gian có thể kiểm soát giúp xác minh đúng mốc.

Không chỉ assert rằng ứng dụng đã gọi PDP. Một ứng dụng có thể gọi PDP rồi bỏ qua Deny. Bằng chứng cần là tác động nghiệp vụ có hoặc không có theo kết quả quyền.

## 19. Phân tích một kiến trúc gặp lỗi vượt quyền

Giả sử Gateway kiểm tra Lan đã đăng nhập, ReportService có role export, nhưng Lan vẫn xuất được hóa đơn của tenant beta.

Hãy lần theo đường quyền:

1. Role export gắn với Lan hay gắn với workload?
2. Tenant acme có được kiểm chứng hay chỉ lấy từ request?
3. ReportService có truyền resourceId do client chọn xuống backend mà không kiểm tra phạm vi không?
4. InvoiceService có kiểm tra quyền trên từng hóa đơn hoặc một tập dữ liệu được xác định không?
5. Cache có tenant trong ngữ cảnh không?
6. ObjectStorage có bảo vệ kết quả đúng người nhận không?
7. Có một đường tải trực tiếp bỏ qua PEP không?

Một nguyên nhân có thể là InvoiceService chỉ kiểm tra ReportService có quyền gọi API export. Workload có quyền hạ tầng, nhưng phạm vi người dùng chưa được áp dụng.

Một thiết kế sửa theo yêu cầu nghiệp vụ có thể:

- Giữ kiểm soát workload tại backend.
- Truyền và kiểm chứng danh tính người yêu cầu.
- Dựng tenant và metadata từ nguồn server.
- Kiểm tra action invoice:export trên đúng tài nguyên hoặc phạm vi truy vấn.
- Gắn quyết định với phiên bản và điều kiện cần thiết.
- Bảo vệ riêng tệp kết quả và điểm tải.

Nếu job được xử lý sau, còn cần giải quyết quyền tại thời điểm chạy. Nếu dữ liệu xuất chứa nhiều hóa đơn, cần kiểm tra cả từng phần tử, tổng số và field được công bố.

Kết quả sửa phải được xác minh qua cùng đường export gây lỗi. Thêm một điều kiện trên endpoint xem hóa đơn đơn lẻ chưa chứng minh luồng export đã được bảo vệ.

## 20. Tự kiểm tra kiến thức

**Quản lý policy tập trung có bắt buộc mọi lần đánh giá đều gọi một PDP từ xa không?**

Không. Có thể phân phối policy tới nhiều PDP local rồi thống nhất cách quản trị, phát hành và quan sát.

**mTLS giữa hai workload có chứng minh người dùng được đọc một hóa đơn không?**

Không thể suy ra như vậy. Nó giúp xác thực đường gọi theo cấu hình; quyền trên đối tượng nghiệp vụ cần dữ kiện và policy tương ứng.

**Vì sao PDP local vẫn có thể trả quyền cũ?**

Policy hoặc dữ liệu thuộc tính, membership và quan hệ mà nó sử dụng có thể chưa cập nhật. Vị trí local chủ yếu thay đổi chi phí và phụ thuộc của đường đánh giá.

**Một Permit có được chuyển sang dịch vụ khác dùng tiếp không?**

Chỉ khi có hợp đồng và bằng chứng phù hợp cho việc truyền đó. Một object kết quả nội bộ hoặc boolean không tự trở thành credential được mọi backend tin.

**Vì sao không thể dùng policyVersion để đại diện mọi trạng thái quyền?**

Membership, quan hệ, trạng thái phiên và metadata tài nguyên có vòng đời riêng. Policy không đổi nhưng quyền trên một tài nguyên vẫn có thể đã bị thu hồi.

**Tại sao lỗi mạng không nên bị ghi đơn thuần là thiếu quyền?**

Vì nó che nguyên nhân vận hành và dẫn tới cách khắc phục sai. Cả hai có thể không cấp dữ liệu, nhưng cần phân biệt lý do.

## 21. Những điểm cần giữ khi thiết kế

Phân quyền phân tán cần một hợp đồng thống nhất về danh tính, tài nguyên, action, dữ kiện và kết quả. Mỗi thành phần phải biết trách nhiệm của mình và giới hạn của bằng chứng nhận được.

Vị trí PDP, cách phân phối policy và nguồn dữ liệu phải được lựa chọn cùng yêu cầu độ mới, thời gian thu hồi, độ trễ và khả năng phục vụ. Tối ưu riêng thời gian đánh giá biểu thức không giải quyết được toàn bộ đường quyết định.

PEP phải bảo vệ thao tác thật sự, thực hiện nghĩa vụ và ràng buộc quyết định với đúng ngữ cảnh. Các đường nội bộ, luồng bất đồng bộ và điểm tải kết quả cũng cần được kiểm soát theo hợp đồng.

Audit và kiểm thử phải nối được quyết định với kết quả thực thi. Khi nhiều dịch vụ cùng tham gia, tính đúng đắn nằm ở cách chúng phối hợp, không chỉ ở một policy hoặc một token riêng lẻ.

## Tài liệu tham khảo

- [NIST SP 800-204B — Attribute-based Access Control for Microservices-based Applications using a Service Mesh](https://csrc.nist.gov/pubs/sp/800/204/b/final): hướng dẫn xác thực và phân quyền trong kiến trúc microservices dùng service mesh.
- [Open Policy Agent — How to Deploy OPA](https://www.openpolicyagent.org/docs/deploy): vai trò PDP và các lựa chọn triển khai gần ứng dụng hoặc tập trung.
- [Zanzibar: Google’s Consistent, Global Authorization System — USENIX ATC 2019](https://www.usenix.org/conference/atc19/presentation/pang): tham chiếu về phối hợp nhất quán giữa thay đổi quyền và nội dung được bảo vệ.

