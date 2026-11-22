# Quản lý ngoại lệ có thời hạn và bằng chứng giải thích

Quality gate (cổng chất lượng) đặt ra những điều kiện mà mã nguồn, bản build hoặc lần triển khai phải đáp ứng trước khi đi tiếp trong pipeline. Ví dụ, pipeline có thể yêu cầu unit test thành công, không có lỗ hổng bảo mật vượt ngưỡng, độ phủ kiểm thử đạt mức tối thiểu, dependency tuân thủ chính sách giấy phép và artifact có thể truy vết.

Trong thực tế, đôi khi một thay đổi chưa thể đáp ứng đầy đủ một cổng. Scanner có thể phát hiện một lỗ hổng đang chờ bản vá từ nhà cung cấp; một test cũ bị chập chờn nhưng chưa thể sửa ngay; một thành phần bên thứ ba chưa có phiên bản thay thế tương thích. Nhóm có thể cần tiếp tục công việc trong khi xử lý vấn đề. Khi đó, **ngoại lệ có thời hạn (time-bound exception)** cho phép chấp nhận một rủi ro cụ thể trong phạm vi và khoảng thời gian được phê duyệt, kèm bằng chứng giải thích và biện pháp kiểm soát bù.

Ngoại lệ là một quyết định quản trị rủi ro có thể kiểm toán. Nó không xóa kết quả scan, làm cho lỗi biến mất hoặc biến một pipeline chưa đạt thành một pipeline không có vấn đề. Một pipeline đúng cần giữ lại finding ban đầu, thể hiện rõ ngoại lệ nào đang được áp dụng, ai chịu trách nhiệm, vì sao chấp nhận, bằng chứng nào hỗ trợ quyết định và khi nào ngoại lệ tự hết hiệu lực.

Đây là một phần của **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng luồng CI/CD có cổng chất lượng, truy vết, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui. Ngoại lệ phải giúp nhóm xử lý tình huống thực tế mà vẫn duy trì kỷ luật phát hành.

## 1. Vì sao cần cơ chế ngoại lệ?

Quality gate tạo ra một chuẩn chung để nhóm quyết định thay đổi có đủ điều kiện đi tiếp hay không. Nếu mọi finding đều bị chặn vô thời hạn, nhóm có thể không xử lý được tình huống cần quyết định nhanh. Nhưng nếu người dùng có thể bỏ qua gate tùy ý, gate sẽ mất ý nghĩa.

Một cơ chế ngoại lệ có kiểm soát giúp giải quyết các tình huống như:

- Lỗ hổng đã được xác minh nhưng chưa có bản vá an toàn từ nhà cung cấp.
- Scanner báo false positive hoặc phát hiện một đường mã không thể khai thác trong ngữ cảnh hiện tại, cần bằng chứng để xác nhận.
- Một test tích hợp chập chờn do phụ thuộc ngoài hệ thống; nhóm cần thời gian sửa nhưng vẫn muốn theo dõi rõ ràng.
- Một thư viện có giấy phép chưa được phân loại đầy đủ; cần quyết định tạm thời trong khi bộ phận phụ trách hoàn tất đánh giá.
- Một ngưỡng chất lượng bị ảnh hưởng bởi mã cũ trong khi thay đổi mới không làm tình hình xấu hơn; nhóm cần một lộ trình giảm nợ kỹ thuật.

Ngoại lệ không phải cách xử lý mặc định cho mọi lần gate thất bại. Trước tiên cần tìm cách sửa nguyên nhân, cập nhật công cụ, điều chỉnh quy tắc sai hoặc bổ sung bằng chứng cho kết quả false positive. Chỉ dùng ngoại lệ khi vẫn còn rủi ro hoặc điều kiện chưa đạt cần một quyết định chấp nhận rõ ràng.

Một số yêu cầu có thể bị quy định nội bộ, hợp đồng hoặc pháp luật cấm miễn trừ. Ví dụ, tổ chức có thể quy định không được phát hành khi phát hiện secret đang hoạt động trong repository hoặc lỗ hổng ở mức nghiêm trọng đã bị xác nhận. Không có phê duyệt ngoại lệ nào được phép vượt qua một yêu cầu không thể miễn trừ.

## 2. Phân biệt ngoại lệ với các cách xử lý khác

Các trạng thái dưới đây có ý nghĩa khác nhau và cần được lưu riêng:

| Cách xử lý | Khi nào dùng | Điều gì xảy ra với gate |
| --- | --- | --- |
| Sửa lỗi (remediation) | Finding là đúng và có thể khắc phục | Chạy lại kiểm tra; gate chỉ đạt khi điều kiện được đáp ứng |
| Sửa quy tắc (policy correction) | Quy tắc cấu hình sai hoặc không còn phù hợp | Cập nhật policy có review; chạy lại kiểm tra trên phạm vi bị ảnh hưởng |
| Xác nhận false positive | Finding không phản ánh rủi ro thật, có bằng chứng kỹ thuật | Ghi disposition và bằng chứng; giữ dấu vết để không âm thầm bỏ qua |
| Ngoại lệ có thời hạn | Finding hoặc điều kiện chưa đạt là có thật nhưng rủi ro được chấp nhận tạm thời | Cho phép đúng phạm vi đã duyệt, giữ finding và ngày hết hạn |
| Bypass thủ công | Bỏ qua kiểm tra mà không có hồ sơ và kiểm soát | Không phải cơ chế ngoại lệ hợp lệ; làm mất khả năng kiểm toán |

False positive và ngoại lệ chấp nhận rủi ro không nên dùng thay cho nhau. Với false positive, nhóm khẳng định kết quả phát hiện không đúng trong ngữ cảnh cụ thể và phải đưa ra bằng chứng. Với ngoại lệ, nhóm thừa nhận điều kiện hoặc rủi ro tồn tại nhưng chấp nhận tạm thời vì có lý do và kiểm soát bù.

Ví dụ, scanner phát hiện một dependency có CVE. Nếu nhóm xác minh ứng dụng không sử dụng module bị ảnh hưởng và cấu hình package loại trừ module đó, có thể xem xét disposition false positive hoặc not affected theo chính sách của công cụ. Nếu ứng dụng thực sự sử dụng module bị ảnh hưởng nhưng có lớp kiểm soát bù, đây là trường hợp chấp nhận rủi ro tạm thời; finding vẫn phải được theo dõi.

Không nên đổi severity, xóa finding hoặc chỉnh kết quả scan chỉ để pipeline xanh. Hãy giữ nguyên bằng chứng gốc và ghi quyết định xử lý như một dữ liệu riêng.

## 3. Những nguyên tắc của một ngoại lệ hợp lệ

Một ngoại lệ nên tuân thủ các nguyên tắc sau:

1. **Cụ thể:** chỉ áp dụng cho một finding, một quy tắc hoặc một điều kiện được nhận diện rõ.
2. **Có lý do:** giải thích vì sao chưa thể khắc phục ngay và vì sao tiếp tục là lựa chọn có thể chấp nhận.
3. **Có bằng chứng:** liên kết kết quả scan, log, phân tích ảnh hưởng, ticket hoặc tài liệu hỗ trợ quyết định.
4. **Có người chịu trách nhiệm:** xác định owner chịu trách nhiệm xử lý và người có thẩm quyền chấp nhận rủi ro.
5. **Có thời hạn:** ghi thời điểm bắt đầu và hết hiệu lực; không dùng ngoại lệ vô thời hạn.
6. **Có kiểm soát bù:** giảm xác suất hoặc tác động trong thời gian chờ khắc phục.
7. **Có thể kiểm toán:** lưu lịch sử tạo, phê duyệt, gia hạn, thu hồi và sử dụng.
8. **Có thể thu hồi:** khi điều kiện thay đổi hoặc bằng chứng không còn đúng, ngoại lệ phải bị vô hiệu hóa.

Ngoại lệ cần gắn với một đối tượng cụ thể. Một phê duyệt cho CVE-2026-12345 trong dependency X ở phiên bản 2.4.1 không nên tự động áp dụng cho mọi CVE của dependency X, cho phiên bản 2.5.0 hoặc cho repository khác. Tương tự, ngoại lệ cho một test có thể áp dụng theo định danh test và phạm vi suite; không nên bỏ qua toàn bộ integration test.

## 4. Phân loại rủi ro trước khi xin ngoại lệ

Không phải mọi finding đều có cùng mức độ nghiêm trọng. Trước khi xin ngoại lệ, cần xác định rủi ro còn lại trong ngữ cảnh thực tế:

- **Mức độ nghiêm trọng:** tác động kỹ thuật hoặc nghiệp vụ nếu vấn đề bị khai thác hay xảy ra.
- **Khả năng khai thác/xảy ra:** có đường truy cập thực tế không, có điều kiện khai thác nào, test có tái hiện được không?
- **Mức độ phơi lộ:** thành phần có truy cập từ Internet, mạng nội bộ, người dùng đặc quyền hay chỉ trong môi trường cô lập?
- **Phạm vi ảnh hưởng:** một job, một service, một nhóm người dùng hay toàn bộ hệ thống?
- **Khả năng phát hiện:** log, alert và giám sát có phát hiện được vấn đề trước khi tác động lan rộng không?
- **Khả năng phục hồi:** có thể tắt tính năng, rollback artifact hoặc khôi phục dữ liệu trong thời gian chấp nhận được không?

Một ma trận đơn giản có thể giúp phân loại:

| Mức rủi ro | Ví dụ | Cách xử lý điển hình |
| --- | --- | --- |
| Thấp | Finding ít ảnh hưởng, có giới hạn rõ và không liên quan dữ liệu nhạy cảm | Owner xử lý theo thời hạn ngắn; phê duyệt theo chính sách nhóm |
| Trung bình | Thành phần có ảnh hưởng nhưng đã có kiểm soát bù và phạm vi phơi lộ hạn chế | Cần owner và reviewer có trách nhiệm bảo mật/chuyên môn phê duyệt |
| Cao | Có đường khai thác thực tế hoặc tác động lớn đến dữ liệu/dịch vụ | Mặc định chặn; chỉ xem xét nếu chính sách cho phép và có cấp phê duyệt phù hợp |
| Nghiêm trọng hoặc bị cấm miễn trừ | Secret production đang hoạt động bị lộ, lỗ hổng nghiêm trọng có thể khai thác theo chính sách không miễn trừ | Không cấp ngoại lệ; khắc phục hoặc cô lập trước khi đi tiếp |

Ma trận trên chỉ là ví dụ để thiết kế quy trình. Ngưỡng severity, thời hạn và cấp phê duyệt phải theo chính sách của tổ chức, loại hệ thống và nghĩa vụ tuân thủ. Không tự đặt một ngưỡng chung áp dụng cho mọi sản phẩm.

Nếu một ngoại lệ làm thay đổi rủi ro của production, người phê duyệt phải hiểu môi trường và tác động thực tế. Việc một test pass trong staging không tự chứng minh rủi ro production đã được kiểm soát.

## 5. Hồ sơ ngoại lệ cần có những gì?

Một hồ sơ ngoại lệ nên đủ thông tin để người không tham gia cuộc trao đổi ban đầu vẫn hiểu quyết định. Các trường tối thiểu:

| Trường | Nội dung cần ghi |
| --- | --- |
| Exception ID | Mã định danh duy nhất để tham chiếu trong log, ticket và pipeline |
| Finding/control ID | CVE, rule ID, test ID, policy ID hoặc tiêu chí gate cụ thể |
| Resource và version | Repository, service, artifact, dependency hoặc commit bị ảnh hưởng |
| Scope | Nhánh, môi trường, sản phẩm, phiên bản và phạm vi áp dụng |
| Rationale | Vì sao chưa thể sửa và vì sao chấp nhận rủi ro trong thời gian giới hạn |
| Evidence | Scan report, log, reproduction, phân tích ảnh hưởng, ticket hoặc tài liệu kỹ thuật |
| Risk assessment | Severity, exploitability, exposure, impact và residual risk |
| Compensating controls | Biện pháp tạm thời làm giảm rủi ro |
| Owner | Người chịu trách nhiệm khắc phục và cập nhật tiến độ |
| Approver | Người hoặc vai trò có thẩm quyền chấp nhận rủi ro |
| Created/approved at | Thời điểm tạo và phê duyệt |
| Expires at | Thời điểm ngoại lệ tự hết hiệu lực |
| Remediation plan | Công việc, ticket và mốc hoàn tất dự kiến |
| Status/history | Pending, approved, expired, revoked, remediated hoặc rejected cùng lịch sử thay đổi |

Evidence không nên chỉ là một câu “đã kiểm tra và an toàn”. Hãy đính kèm kết quả scan có timestamp và commit/artifact tương ứng, log tái hiện, phân tích module bị ảnh hưởng, cấu hình mạng, kết quả test hoặc liên kết ticket có owner và thời hạn. Nếu bằng chứng có dữ liệu nhạy cảm, lưu trong hệ thống có phân quyền và chỉ tham chiếu ID hoặc vị trí được phép truy cập.

### 5.1. Ví dụ hồ sơ ngoại lệ

YAML dưới đây là một schema minh họa để thảo luận, không phải định dạng tích hợp mặc định của mọi CI platform:

~~~yaml
exception:
  id: EXC-2026-0042
  finding:
    control_id: DEP-VULN-123
    type: dependency-vulnerability
    component: com.example:legacy-client
    version: 2.4.1
  scope:
    repository: order-service
    branch: main
    environment: staging
    artifact_digest: sha256:example-digest
  rationale: >
    Bản vá tương thích chưa được nhà cung cấp phát hành.
    Thành phần chỉ được dùng qua adapter nội bộ đã giới hạn endpoint.
  risk:
    severity: high
    exposure: internal-only
    residual: medium
  evidence:
    - scan-report-id: SEC-SCAN-8821
    - analysis-ticket: SEC-314
  compensating_controls:
    - Restrict outbound access to approved endpoint
    - Add request validation and enhanced monitoring
  owner: team-order-platform
  approver: application-security-lead
  approved_at: "2026-11-18T09:00:00Z"
  expires_at: "2026-12-02T09:00:00Z"
  remediation_ticket: SEC-314
  status: approved
~~~

Ví dụ minh họa cách ghi một finding cụ thể, một artifact cụ thể, môi trường staging, biện pháp bù và ngày hết hạn. Trong hệ thống thật, cần dùng ID evidence có thể truy cập, digest chính xác, người phê duyệt thực tế và thời điểm được tạo từ hệ thống. Không sao chép nguyên văn các giá trị ví dụ thành hồ sơ phát hành.

## 6. Bằng chứng giải thích phải trả lời được câu hỏi nào?

Một quyết định chấp nhận ngoại lệ cần có bằng chứng cho cả lý do chưa thể khắc phục và cách kiểm soát rủi ro:

**Về finding**

- Công cụ nào phát hiện, phiên bản công cụ và rule ID là gì?
- Finding xuất hiện trên commit, image hoặc artifact nào?
- Có thể tái hiện không? Đường đi dữ liệu hoặc điều kiện kích hoạt là gì?
- Kết quả scan có còn mới so với artifact dự kiến triển khai không?

**Về tác động**

- Thành phần bị ảnh hưởng có được gọi trong luồng thực tế không?
- Có thể truy cập từ đâu và bởi ai?
- Dữ liệu hoặc chức năng nào có thể bị tác động?
- Điều gì xảy ra nếu rủi ro xảy ra trong thời hạn ngoại lệ?

**Về biện pháp bù**

- Biện pháp nào giảm khả năng khai thác hoặc giới hạn tác động?
- Biện pháp đã được triển khai và xác minh chưa?
- Có log/alert để phát hiện dấu hiệu bất thường không?
- Có cách tắt tính năng hoặc rollback không?

**Về kế hoạch khắc phục**

- Ticket nào theo dõi công việc?
- Ai là owner?
- Mốc nào cần hoàn thành?
- Nếu đến hạn mà chưa sửa được thì hành động tiếp theo là gì?

Bằng chứng phải gắn với đúng phạm vi. Một báo cáo scan của branch cũ không chứng minh artifact mới không còn finding; một test trên staging không tự chứng minh production có cùng cấu hình. Nếu commit, dependency version hoặc artifact digest thay đổi, cần đánh giá xem ngoại lệ còn áp dụng hay phải phê duyệt lại.

## 7. Thời hạn, gia hạn và tự hết hiệu lực

Ngoại lệ phải có ngày hết hạn rõ ràng. Không dùng các giá trị như “until fixed”, “tạm thời” hoặc “đến khi có thời gian” làm thời hạn duy nhất. Có thể ghi thêm điều kiện hoàn tất, nhưng vẫn cần một mốc thời gian cụ thể.

Thời hạn nên tỷ lệ với rủi ro:

- Rủi ro cao cần thời hạn rất ngắn và giám sát thường xuyên.
- Rủi ro trung bình có thể có thời hạn dài hơn nếu kiểm soát bù đủ mạnh.
- Rủi ro thấp vẫn cần ngày xem xét và ngày hết hiệu lực.

Ví dụ chính sách nội bộ có thể đặt thời hạn tối đa 7 ngày cho một nhóm finding rủi ro cao được phép miễn trừ, 14 ngày cho rủi ro trung bình và 30 ngày cho rủi ro thấp. Đây chỉ là ví dụ; tổ chức cần tự xác định giới hạn theo mức độ rủi ro và nghĩa vụ tuân thủ.

Khi ngoại lệ hết hạn:

1. Hệ thống chuyển trạng thái thành expired hoặc không còn hợp lệ.
2. Quality gate áp dụng lại chính sách gốc cho finding đó.
3. Pipeline mới bị chặn nếu finding vẫn tồn tại và không có quyết định mới hợp lệ.
4. Owner và approver nhận thông báo theo cơ chế của tổ chức.
5. Lịch sử ngoại lệ vẫn được giữ để kiểm toán.

Không nên để pipeline tự động coi ngoại lệ cũ là còn hiệu lực chỉ vì finding ID giống nhau. Hệ thống phải kiểm tra ngày hết hạn, trạng thái, scope và artifact/commit liên quan mỗi lần đánh giá.

### 7.1. Gia hạn không phải thao tác kéo dài ngày một cách máy móc

Nếu cần gia hạn, owner phải cập nhật:

- Tiến độ remediation và lý do chưa hoàn thành.
- Bằng chứng mới nhất cho thấy rủi ro vẫn trong phạm vi đã đánh giá.
- Hiệu quả của các biện pháp bù.
- Thời hạn mới và mốc xử lý tiếp theo.
- Thay đổi về scope, severity, exposure hoặc artifact.

Gia hạn phải được phê duyệt lại theo chính sách. Không cho phép owner tự gia hạn ngoại lệ của chính mình nếu quy trình yêu cầu phân tách nhiệm vụ. Số lần gia hạn nên được giới hạn hoặc yêu cầu cấp phê duyệt cao hơn khi vượt ngưỡng.

### 7.2. Thu hồi trước hạn

Ngoại lệ có thể bị thu hồi trước ngày hết hạn nếu:

- Phát hiện mới làm tăng mức độ nghiêm trọng hoặc khả năng khai thác.
- Biện pháp bù không còn hoạt động.
- Phạm vi sử dụng mở rộng sang production hoặc dữ liệu nhạy cảm.
- Artifact hoặc dependency thay đổi khiến đánh giá ban đầu không còn đúng.
- Owner không thực hiện kế hoạch remediation.
- Bằng chứng bị phát hiện sai hoặc không đầy đủ.

Khi bị thu hồi, gate phải áp dụng lại ngay cho lần chạy tiếp theo và tổ chức cần quyết định có dừng rollout hoặc thu hồi artifact đang triển khai hay không.

## 8. Quy trình tạo và phê duyệt ngoại lệ

Một quy trình có thể thực hiện theo các bước:

1. **Phát hiện:** pipeline tạo finding và lưu kết quả scan/test cùng commit, artifact hoặc release ID.
2. **Phân loại:** owner xác định finding là lỗi thật, false positive, policy misconfiguration hay rủi ro cần chấp nhận tạm thời.
3. **Khắc phục trước:** nếu có thể sửa an toàn, sửa và chạy lại gate.
4. **Đề nghị ngoại lệ:** nếu chưa thể sửa, tạo hồ sơ với scope, rationale, evidence, risk assessment, controls, owner, approver và expiry.
5. **Đánh giá độc lập:** reviewer có chuyên môn kiểm tra bằng chứng, mức rủi ro và biện pháp bù.
6. **Phê duyệt hoặc từ chối:** hệ thống lưu danh tính, thời điểm và quyết định.
7. **Đánh giá trong pipeline:** policy engine chỉ áp dụng ngoại lệ khi finding khớp chính xác, trạng thái approved, scope phù hợp và chưa hết hạn.
8. **Theo dõi:** owner xử lý remediation, cập nhật bằng chứng và nhận nhắc trước hạn.
9. **Đóng:** khi khắc phục đạt gate, đánh dấu remediated; nếu hết hạn hoặc bị thu hồi, gate trở lại trạng thái chặn theo policy.

Người tạo yêu cầu không nên tự phê duyệt rủi ro của mình trong những trường hợp cần phân tách nhiệm vụ. Với finding bảo mật, người phê duyệt nên có thẩm quyền phù hợp, chẳng hạn security owner hoặc risk owner. Với vấn đề chất lượng dữ liệu hoặc độ tin cậy kiểm thử, có thể cần owner của hệ thống và người chịu trách nhiệm chất lượng.

Phê duyệt qua chat hoặc lời nói có thể hỗ trợ trao đổi, nhưng quyết định chính thức cần được ghi vào hệ thống có kiểm soát truy cập và audit trail. Pipeline nên tham chiếu hồ sơ ngoại lệ đã được lưu, không dựa vào một dòng comment tự do trong PR.

## 9. Đánh giá ngoại lệ trong policy-as-code

Policy engine cần đánh giá finding và ngoại lệ theo quy tắc có thể kiểm tra. Logic tổng quát:

~~~text
for each finding:
    if finding is resolved:
        continue

    if finding is explicitly non-waivable:
        block pipeline
        continue

    exception = find_exact_match(
        finding_id,
        repository,
        resource_version,
        environment
    )

    if exception is missing:
        block pipeline
    else if exception.status is not approved:
        block pipeline
    else if now >= exception.expires_at:
        block pipeline
    else if evidence is missing or scope does not match:
        block pipeline
    else:
        record accepted_exception
        continue with visible exception status
~~~

Đây là pseudo-code giải thích ý tưởng, không phải cú pháp của một sản phẩm CI cụ thể. Khi triển khai, cần dùng thời gian UTC từ nguồn tin cậy, so sánh thời hạn theo quy tắc rõ ràng và tránh cho pipeline tự sửa hồ sơ ngoại lệ.

Kết quả đánh giá nên phân biệt:

| Kết quả | Ý nghĩa |
| --- | --- |
| PASS | Không còn finding bị chặn và không cần ngoại lệ |
| BLOCKED | Có finding chưa được xử lý hoặc ngoại lệ không hợp lệ |
| ACCEPTED_WITH_EXCEPTION | Có finding được chấp nhận tạm thời theo hồ sơ hợp lệ |
| EXPIRED | Ngoại lệ đã hết hạn; gate gốc được áp dụng lại |
| REVOKED | Ngoại lệ bị thu hồi trước hạn |

Nếu tổ chức cho phép tiếp tục triển khai với trạng thái ACCEPTED_WITH_EXCEPTION, trạng thái đó phải được thể hiện rõ trong kết quả pipeline, báo cáo release và audit log. Không đổi nó thành PASS thuần túy vì như vậy người xem sẽ không biết artifact đang mang rủi ro đã được chấp nhận.

Một số hệ thống có thể yêu cầu phê duyệt bổ sung trước khi production deployment ngay cả khi exception đã hợp lệ. Quyết định chấp nhận rủi ro và quyết định phát hành là hai bước quản trị khác nhau.

## 10. Tích hợp với pull request và luồng phát hành

Ngoại lệ nên xuất hiện ở những điểm người dùng cần ra quyết định:

- Trong PR, hiển thị finding, trạng thái ngoại lệ, owner và ngày hết hạn.
- Trước khi merge, kiểm tra ngoại lệ có áp dụng cho commit dự kiến hay không.
- Trước khi build artifact, lưu snapshot kết quả gate và danh sách exception ID.
- Trước khi triển khai, kiểm tra lại expiry, scope và trạng thái phê duyệt.
- Sau triển khai, liên kết release ID với finding và hồ sơ ngoại lệ đã dùng.

Không nên chỉ kiểm tra ngoại lệ lúc tạo PR. Một ngoại lệ có thể hết hạn giữa lúc merge và lúc production deploy. Vì vậy, pipeline phải đánh giá lại tại mỗi cổng quan trọng, đặc biệt trước khi cấp quyền triển khai.

Nếu ngoại lệ chỉ áp dụng cho staging, không được tự động mang sang production. Nếu ngoại lệ áp dụng cho artifact digest cụ thể, build lại artifact tạo digest mới cần được xem xét lại. Nếu ngoại lệ áp dụng cho một commit nhưng có thay đổi dependency hoặc cấu hình bảo mật, phải xác định xem bằng chứng ban đầu còn đúng hay không.

## 11. Ví dụ: chấp nhận tạm thời một lỗ hổng dependency

Giả sử scanner phát hiện CVE ở một thư viện mà service đang sử dụng. Nhà cung cấp chưa phát hành bản vá tương thích; nâng cấp ngay làm hỏng hợp đồng API với hệ thống khác. Nhóm muốn triển khai một bản sửa lỗi nghiệp vụ nhỏ.

Quy trình có thể là:

1. Xác minh CVE ảnh hưởng đúng phiên bản dependency đang đóng gói; ghi scanner report và SBOM của artifact.
2. Phân tích đường sử dụng: module dễ tổn thương có được gọi không, dữ liệu nào có thể đi vào và service có phơi lộ Internet không.
3. Thử biện pháp khắc phục trước như nâng cấp phiên bản tương thích, loại bỏ module không dùng hoặc cấu hình an toàn.
4. Nếu chưa thể sửa, lập hồ sơ ngoại lệ cho CVE cụ thể, dependency version, repository và artifact digest.
5. Bổ sung kiểm soát bù, chẳng hạn giới hạn outbound, validate input, tắt endpoint liên quan hoặc tăng giám sát nếu phù hợp với nguyên nhân.
6. Giao ticket nâng cấp cho owner, đặt ngày hết hạn ngắn và yêu cầu approver bảo mật chấp nhận residual risk.
7. Pipeline giữ finding ở trạng thái visible exception và ghi exception ID vào báo cáo release.
8. Khi bản vá tương thích được phát hành, cập nhật dependency, chạy lại scan/test và đóng ngoại lệ sau khi gate đạt.

Nếu biện pháp bù không thực sự làm giảm rủi ro, hoặc chính sách tổ chức cấm miễn trừ severity đó, không được phát hành chỉ vì có một ticket và chữ ký phê duyệt.

## 12. Ví dụ: ngoại lệ cho một test chập chờn

Giả sử một integration test đôi khi timeout do dịch vụ bên thứ ba trong môi trường test. Test xác minh luồng quan trọng và không thể xóa bỏ lâu dài.

Một ngoại lệ hợp lệ cần:

- Chỉ rõ test ID hoặc suite cụ thể.
- Có log của những lần thất bại và thống kê tần suất.
- Chứng minh nguyên nhân nằm ở dependency môi trường, không phải lỗi sản phẩm đã biết.
- Giữ một kiểm tra thay thế hoặc smoke test cho luồng nghiệp vụ liên quan.
- Giao owner sửa cách đồng bộ, timeout hoặc test fixture.
- Đặt expiry và theo dõi số lần test bị bỏ qua.

Không nên tắt toàn bộ integration test hoặc biến mọi timeout thành success. Nếu test được tạm quarantine, pipeline phải thể hiện rõ test đang bị cách ly, có người chịu trách nhiệm và có thời hạn khôi phục. Một test bị bỏ qua không được báo cáo như test đã pass.

## 13. Theo dõi ngoại lệ và kiểm toán

Ngoại lệ là nợ rủi ro có chủ sở hữu và thời hạn. Nhóm nên theo dõi tối thiểu:

- Số ngoại lệ đang active theo mức độ rủi ro.
- Số ngoại lệ sắp hết hạn và đã quá hạn.
- Số lần gia hạn cho cùng finding hoặc cùng owner.
- Thời gian trung bình từ lúc tạo ngoại lệ đến lúc remediation.
- Tỷ lệ ngoại lệ được đóng đúng hạn.
- Số lần gate bị chặn do exception scope không khớp hoặc hết hạn.
- Các finding tái xuất hiện sau khi đã được khắc phục.

Audit trail cần ghi ai tạo, ai phê duyệt, ai thay đổi scope, thời hạn cũ/mới, lý do gia hạn, ai thu hồi và pipeline/release nào đã sử dụng ngoại lệ. Không ghi đè lịch sử cũ khi cập nhật hồ sơ; hãy tạo sự kiện hoặc phiên bản mới.

Một báo cáo hữu ích không chỉ đếm tổng số ngoại lệ. Nó cần chỉ ra rủi ro nào đang tồn tại lâu, nhóm nào thường xuyên xin gia hạn và biện pháp kiểm soát nào không đưa đến remediation. Dữ liệu đó giúp nhóm cải thiện nền tảng, nâng cấp dependency hoặc sửa quy tắc quality gate.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Ngoại lệ không có ngày hết hạn | Rủi ro tạm thời trở thành vĩnh viễn | Bắt buộc expiry và tự động đánh dấu hết hạn |
| Chỉ ghi lý do “cần release gấp” | Không có bằng chứng để đánh giá rủi ro | Ghi finding, impact, evidence và controls |
| Owner tự phê duyệt mọi ngoại lệ | Thiếu đánh giá độc lập | Phân tách requester, owner và approver theo chính sách |
| Ngoại lệ áp dụng cho cả rule hoặc repository | Bỏ qua nhiều finding không liên quan | Giới hạn theo finding, version, scope và environment |
| Chỉnh scanner để finding biến mất | Mất bằng chứng gốc và lịch sử | Lưu finding nguyên trạng, ghi disposition riêng |
| Cache hoặc artifact cũ vẫn được ngoại lệ bao phủ | Bằng chứng không khớp đầu vào hiện tại | Gắn exception với commit/digest và kiểm tra lại khi thay đổi |
| Gia hạn không giới hạn | Nợ rủi ro tích tụ | Giới hạn số lần, yêu cầu bằng chứng và cấp duyệt cao hơn |
| Pipeline chỉ kiểm tra expiry lúc merge | Ngoại lệ có thể hết hạn trước deployment | Đánh giá lại ở các gate quan trọng |
| Ngoại lệ được báo cáo là PASS | Người phát hành không thấy rủi ro còn tồn tại | Dùng trạng thái ACCEPTED_WITH_EXCEPTION riêng |
| Dùng ngoại lệ để vượt yêu cầu không thể miễn trừ | Vi phạm chính sách hoặc nghĩa vụ tuân thủ | Định nghĩa non-waivable controls và luôn chặn |

## 15. Checklist trước khi chấp nhận ngoại lệ

**Phạm vi và lý do**

- [ ] Finding hoặc control ID được xác định chính xác.
- [ ] Repository, resource, version, commit/artifact và environment được ghi rõ.
- [ ] Đã thử hoặc đánh giá phương án khắc phục trực tiếp.
- [ ] Lý do chưa thể khắc phục được diễn giải cụ thể.
- [ ] Xác nhận control này được phép miễn trừ theo chính sách.

**Rủi ro và bằng chứng**

- [ ] Severity, exposure, impact và residual risk được đánh giá.
- [ ] Có scan report, log, reproduction hoặc phân tích hỗ trợ.
- [ ] Bằng chứng gắn với đúng commit/artifact đang xét.
- [ ] Kiểm soát bù có thể thực hiện và đã được xác minh.
- [ ] Có kế hoạch rollback hoặc giới hạn ảnh hưởng nếu cần.

**Trách nhiệm và thời hạn**

- [ ] Owner và approver có thẩm quyền được xác định.
- [ ] Người tạo yêu cầu không tự phê duyệt nếu cần phân tách nhiệm vụ.
- [ ] Có remediation ticket và mốc xử lý.
- [ ] Có ngày hết hạn cụ thể theo UTC.
- [ ] Có quy trình nhắc hạn, gia hạn, thu hồi và tự động áp dụng lại gate.

**Pipeline và audit**

- [ ] Pipeline kiểm tra scope, trạng thái và expiry ở thời điểm đánh giá.
- [ ] Finding gốc vẫn được lưu và hiển thị.
- [ ] Kết quả ACCEPTED_WITH_EXCEPTION được phân biệt với PASS.
- [ ] Exception ID được liên kết với commit, artifact và release.
- [ ] Lịch sử tạo, duyệt, gia hạn và thu hồi có thể kiểm toán.

## Kết luận

Ngoại lệ có thời hạn là cách chấp nhận rủi ro có kiểm soát khi một quality gate chưa thể đạt ngay. Một hồ sơ hợp lệ phải chỉ rõ finding và phạm vi, giải thích lý do, có bằng chứng, đánh giá residual risk, biện pháp bù, owner, approver và ngày hết hạn. Pipeline phải kiểm tra lại trạng thái và phạm vi ngoại lệ ở các cổng quan trọng, giữ nguyên finding gốc và hiển thị rõ khi release được chấp nhận với ngoại lệ.

Khi ngoại lệ hết hạn, bị thu hồi hoặc không còn khớp với artifact hiện tại, quality gate phải áp dụng lại. Khi vấn đề được khắc phục, chạy lại kiểm tra và đóng hồ sơ bằng bằng chứng mới. Cách làm này giúp nhóm xử lý tình huống thực tế mà vẫn giữ được khả năng truy vết, trách nhiệm giải trình và kỷ luật phát hành của CI/CD.
