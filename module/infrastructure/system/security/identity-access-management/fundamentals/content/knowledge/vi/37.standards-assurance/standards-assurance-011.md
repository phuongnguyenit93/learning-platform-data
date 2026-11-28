# Security control mapping

Một tổ chức đã bật MFA, có quy trình cấp tài khoản và lưu log đăng nhập. Khi cần giải thích các biện pháp ấy đáp ứng yêu cầu nào, đội IAM lại có ba danh sách rời nhau: yêu cầu của khách hàng, tên các kiểm soát trong framework và cấu hình đang triển khai. Không có liên kết rõ ràng, cùng một bằng chứng có thể bị thu thập nhiều lần trong khi một yêu cầu quan trọng vẫn bị bỏ sót.

**Security control mapping** là việc xác định và ghi lại quan hệ giữa yêu cầu, mục tiêu hoặc kiểm soát từ các nguồn khác nhau. Trong thực hành IAM, công việc này còn cần nối đến cách triển khai và bằng chứng đánh giá để người khác kiểm tra được cơ sở của từng kết luận.

NIST mô tả Online Informative References — OLIR — như một cách biểu diễn có cấu trúc quan hệ giữa các khái niệm trong tài liệu về an ninh, quyền riêng tư và những lĩnh vực liên quan. Xem [NIST IR 8278 Rev. 1](https://csrc.nist.gov/pubs/ir/8278/r1/final). Tuy nhiên, có một quan hệ tham chiếu không có nghĩa hai yêu cầu tương đương hoặc hệ thống đã đạt yêu cầu.

## 1. Phân biệt năm lớp thông tin

Để tránh biến bảng mapping thành danh sách tên sản phẩm, cần tách các lớp sau:

| Lớp | Câu hỏi cần trả lời | Ví dụ IAM tự xây dựng |
|---|---|---|
| Yêu cầu hoặc kết quả mong muốn | Cần đạt điều gì, cho phạm vi nào? | Nhân viên đã nghỉ việc không tiếp tục dùng cổng tài liệu |
| Kiểm soát | Tổ chức dùng biện pháp quản lý rủi ro nào? | Quy trình thu hồi tài khoản và quyền khi chấm dứt quan hệ lao động |
| Triển khai | Biện pháp được thực hiện ở đâu, bằng cách nào? | Nhận sự kiện nhân sự, khóa tài khoản IdP, xử lý quyền và phiên tại ứng dụng |
| Bằng chứng | Có dữ liệu nào cho thấy việc triển khai đã diễn ra? | Sự kiện đầu vào, kết quả xử lý và dấu thời gian kiểm tra truy cập |
| Kết quả đánh giá | Bằng chứng có đủ và hành vi có đạt tiêu chí không? | Trường hợp thử nghiệm đạt hoặc không đạt thời hạn nội bộ |

Một chính sách mô tả quy trình không chứng minh quy trình đã hoạt động. Một ảnh cấu hình chứng minh điều gì đó ở thời điểm chụp, nhưng chưa cho biết mọi tài khoản thuộc phạm vi đều đi qua cấu hình ấy. Một log khóa tài khoản IdP cũng chưa chứng minh ứng dụng đã ngừng chấp nhận phiên đang tồn tại.

Ví dụ xuyên suốt bài là cổng tài liệu của một tổ chức giả định. Các mã kiểm soát nội bộ, thời hạn, schema và kết luận minh họa đều do bài học xây dựng; không phải yêu cầu mặc định của một framework.

## 2. Chốt phạm vi và phiên bản trước khi nối quan hệ

Một dòng mapping phải được hiểu trong phạm vi xác định. Với cổng tài liệu, đội IAM cần nêu rõ đang xét nhân viên, nhà thầu, quản trị viên hay danh tính workload; môi trường production hay thử nghiệm; tenant nào; các đường đăng nhập nào; và khoảng thời gian đánh giá nào.

Nếu chỉ xét nhân viên đăng nhập bằng SSO, không thể dùng kết quả đó để kết luận về tài khoản quản trị local hoặc service account chạy tác vụ nền. Nếu ứng dụng có cơ chế truy cập khẩn cấp, cơ chế ấy cần được xử lý trong phạm vi phù hợp thay vì bị bỏ quên vì ít sử dụng.

Về tài liệu nguồn, cần ghi ít nhất tên, phiên bản, mã phần tử và nơi lấy nội dung. Không nên chỉ lưu `AC-2` mà thiếu tên catalog: mã kiểm soát chỉ có ý nghĩa trong namespace và phiên bản của nó.

NIST SP 800-53 Rev. 5 là một catalog kiểm soát; CSF 2.0 mô tả các kết quả an ninh mạng ở mức cao và không quy định duy nhất cách đạt chúng. Hai nguồn có mức chi tiết khác nhau, nên việc nối chúng cần xét mục đích và phạm vi. Xem [SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final) và [NIST CSF 2.0](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf).

Ngoài revision lớn, catalog còn có thể có cập nhật nhỏ. Trang công bố SP 800-53 ghi nhận Release 5.2.0 vào năm 2025. Khi xây dựng mapping thật, cần cố định đúng bản dữ liệu đã sử dụng và theo dõi thay đổi; chỉ ghi “Rev. 5” có thể chưa đủ để tái tạo một đợt đối chiếu sau này. Nguồn: [thông tin cập nhật SP 800-53 của NIST](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final).

## 3. Tách yêu cầu lớn thành các phần có thể kiểm tra

Yêu cầu “quản lý quyền truy cập an toàn” quá rộng để đánh giá trực tiếp. Trong ví dụ cổng tài liệu, đội dự án tách thành những yêu cầu cụ thể:

| Mã nội bộ | Yêu cầu minh họa | Đối tượng cần kiểm tra |
|---|---|---|
| `REQ-IAM-01` | Tài khoản nhân viên mới chỉ được cấp quyền sau phê duyệt | Yêu cầu cấp quyền, người phê duyệt, quyền thực tế |
| `REQ-IAM-02` | Đăng nhập quản trị phải đi qua MFA theo chính sách tổ chức | Các đường đăng nhập quản trị và ngoại lệ |
| `REQ-IAM-03` | API tài liệu giới hạn hành động theo quyền và phạm vi tenant | Quyết định phân quyền với từng tài nguyên |
| `REQ-IAM-04` | Người đề nghị cấp quyền đặc biệt không tự phê duyệt yêu cầu của mình | Quan hệ người đề nghị và người phê duyệt |
| `REQ-IAM-05` | Quyền nhân viên nghỉ việc được xử lý trong thời hạn nội bộ đã duyệt | Tài khoản, quyền, phiên và đường truy cập liên quan |

Các yêu cầu trên có thể được phân rã tiếp. Chẳng hạn, `REQ-IAM-05` cần định nghĩa lúc bắt đầu đo thời hạn, danh sách hệ thống thuộc phạm vi và cách xác nhận truy cập đã bị chặn. Một câu “khóa trong 15 phút” vẫn chưa rõ nếu bên nhân sự và đội IAM dùng hai mốc bắt đầu khác nhau.

Nếu tổ chức chọn 15 phút cho ví dụ này, đó là tham số nội bộ cần được phê duyệt theo bối cảnh rủi ro. Không tự gắn con số ấy cho NIST hoặc một framework chỉ vì yêu cầu được liên kết đến kiểm soát của framework đó.

## 4. Quan hệ mapping thường là nhiều-nhiều

Một kiểm soát nội bộ có thể hỗ trợ nhiều yêu cầu; một yêu cầu rộng có thể cần nhiều kiểm soát. Đội dự án cần ghi rõ chiều và ý nghĩa của quan hệ, thay vì chỉ đặt dấu tích trong một bảng lớn.

Để minh họa, bài dùng ba nhãn nội bộ:

| Nhãn | Ý nghĩa trong bài |
|---|---|
| `SUPPORTS_PART` | Kiểm soát hỗ trợ một phần nội dung được tham chiếu; cần nêu phần còn thiếu |
| `SUPPORTS` | Có cơ sở cho thấy kiểm soát hỗ trợ mục tiêu tham chiếu trong phạm vi đã ghi |
| `NO_RELEVANT_LINK` | Đã xem xét nhưng không xác định quan hệ phù hợp trong phạm vi ấy |

Đây không phải bộ giá trị chuẩn của OLIR hay OSCAL. Một quan hệ `SUPPORTS` trong ví dụ cũng không có nghĩa “đáp ứng toàn bộ yêu cầu” hoặc “đã đánh giá đạt”. Mapping và đánh giá vận hành là hai quyết định khác nhau.

NIST lưu ý rằng crosswalk chỉ cho biết khái quát về mức liên quan giữa các kiểm soát; không nên suy ra tương đương chỉ từ bảng quan hệ, và mapping không luôn là một-một. Nguồn: [ghi chú về mappings và crosswalks của SP 800-53](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final).

Ví dụ, kiểm soát “khóa tài khoản IdP khi nhận sự kiện nghỉ việc” hỗ trợ quản lý vòng đời tài khoản. Nhưng nếu phiên tại cổng tài liệu còn hiệu lực thêm một giờ, kiểm soát ấy mới hỗ trợ một phần mục tiêu “ngừng truy cập trong 15 phút”. Đội dự án phải ghi khoảng trống về phiên, không đổi tên kiểm soát cho giống yêu cầu rồi xem là đủ.

Không tự suy diễn quan hệ bắc cầu: A liên quan B và B liên quan C chưa chứng minh A đáp ứng C. A có thể liên quan đến phần quản lý tài khoản của B, còn C lại liên quan đến phần rà soát đặc quyền khác của B.

## 5. Một bảng mapping IAM có giải trình

Các mã tham chiếu dưới đây được dùng để minh họa cách tổ chức hồ sơ: SP 800-53 Rev. 5 có AC-2 về quản lý tài khoản, AC-3 về thực thi truy cập, AC-5 về phân tách nhiệm vụ và AC-6 về đặc quyền tối thiểu. IA-2(1) liên quan MFA cho tài khoản đặc quyền. Có thể đối chiếu catalog qua [công cụ và nguồn catalog SP 800-53 của NIST](https://pages.nist.gov/oscal-tools/demos/csx/baseline-reviewer/).

Trong CSF 2.0, PR.AA-01 đề cập quản lý danh tính và thông tin xác thực; PR.AA-03 đề cập xác thực; PR.AA-05 bao gồm việc xác định, quản lý, thực thi và rà soát quyền, với đặc quyền tối thiểu và phân tách nhiệm vụ. Nguồn: [CSF 2.0, Appendix A](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf).

**Bảng sau là đề xuất phân tích cho hệ thống giả định, không phải crosswalk chính thức của NIST.** Mọi quan hệ vẫn cần được người có trách nhiệm đối chiếu nội dung nguồn và phạm vi cụ thể.

| Kiểm soát nội bộ | Tham chiếu được xem xét | Phần được hỗ trợ | Khoảng trống cần đánh giá tiếp |
|---|---|---|---|
| `CTL-IAM-01`: phê duyệt, cấp và thu hồi tài khoản nhân viên | AC-2; PR.AA-01 | Một phần vòng đời tài khoản và danh tính | Tài khoản nhà thầu, tài khoản khẩn cấp và workload cần phạm vi riêng |
| `CTL-IAM-02`: MFA trên đường đăng nhập quản trị | IA-2(1); PR.AA-03 | Xác thực tài khoản quản trị thuộc phạm vi | Phải kiểm tra đường đăng nhập local và cơ chế khôi phục |
| `CTL-IAM-03`: chính sách phân quyền API theo tenant và hành động | AC-3; AC-6; PR.AA-05 | Thực thi quyền ở ứng dụng và giới hạn phạm vi hành động | Chưa chứng minh quyền được rà soát hay cấp đúng ban đầu |
| `CTL-IAM-04`: chặn người đề nghị tự duyệt quyền đặc biệt | AC-5; PR.AA-05 | Một xung đột nhiệm vụ đã xác định | Chưa bao phủ mọi cặp nhiệm vụ xung đột trong tổ chức |
| `CTL-IAM-05`: rà soát định kỳ quyền của cổng tài liệu | AC-2; AC-6; PR.AA-05 | Xác nhận nhu cầu quyền và xử lý quyền thừa | Cần chứng minh quyết định thu hồi đã được thực thi |

Ví dụ này cho thấy PR.AA-05 không được giải quyết chỉ bằng một bộ kiểm tra quyền ở API. Cổng còn cần biết quyền được quản lý, rà soát và điều chỉnh ra sao. Ngược lại, một chiến dịch rà soát quyền trên giấy không thay thế việc cưỡng chế quyền tại API.

Trong một hồ sơ thật, mỗi ô tham chiếu có thể cần tách thành nhiều quan hệ riêng để ghi nguồn, lý do và kết quả review. Không nên ép tất cả quan hệ của một kiểm soát vào cùng một kết luận chung nếu mức hỗ trợ khác nhau.

## 6. Ghi hồ sơ có thể truy vết và kiểm tra lại

Một bản ghi cần cho phép người khác tìm được nội dung nguồn, hiểu lập luận, xác định người chịu trách nhiệm và biết việc đánh giá đã tiến đến đâu. Mẫu YAML sau là **schema nội bộ minh họa**, không phải tài liệu OSCAL hợp lệ theo mặc định:

```yaml
mappingId: MAP-IAM-005
mappingRevision: 2
internalRequirement: REQ-IAM-05
internalControl: CTL-IAM-01
scope:
  system: document-portal
  environment: production
  identityPopulation: employees
  accessPaths:
    - workforce-sso
  exclusions:
    - contractor-accounts
    - workload-identities
reference:
  document: NIST-SP-800-53
  revision: "5"
  element: AC-2
  source: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
relationship: SUPPORTS_PART
rationale: >
  Quy trình xử lý tài khoản nhân viên khi nghỉ việc;
  chưa chứng minh việc kết thúc truy cập qua phiên ứng dụng.
localParameters:
  accessTerminationTargetMinutes: 15
  timingStart: validated-termination-event-received
ownership:
  controlOwner: workforce-iam-team
  applicationOwner: document-portal-team
mappingReview:
  state: DRAFT
  requiredReviewer: security-controls-team
implementation:
  state: PARTIAL
assessment:
  state: NOT_ASSESSED
evidencePlan:
  - termination-event-reference
  - idp-account-disable-result
  - application-access-rejection-result
knownGap: Existing application sessions require additional verification.
```

Các giá trị như tên hệ thống và owner là dữ liệu giả định; trường `source` dùng đường dẫn công bố thật để minh họa việc lưu nguồn. Khi vận hành, hồ sơ cần thêm định danh bản catalog cụ thể hoặc dấu kiểm toàn vẹn để xác định đúng nội dung đã đối chiếu.

`mappingReview.state`, `implementation.state` và `assessment.state` cố ý tách nhau. Một mapping có thể được review chấp nhận nhưng triển khai còn thiếu; triển khai có thể hoàn tất nhưng chưa được đánh giá; đánh giá từng đạt có thể phải thực hiện lại sau thay đổi quan trọng.

Không đặt một trường `compliant: true` làm kết luận duy nhất cho tất cả các trạng thái này. Nếu cần trạng thái tổng hợp để báo cáo, tổ chức phải định nghĩa rõ quy tắc suy ra và cho phép truy ngược đến các dữ kiện gốc.

## 7. Chuyển mapping thành kế hoạch đánh giá

NIST SP 800-53A Rev. 5 cung cấp phương pháp và thủ tục đánh giá kiểm soát phù hợp với SP 800-53 Rev. 5. Nó giúp tổ chức xây dựng kế hoạch và phân tích kết quả đánh giá, thay vì chỉ liệt kê kiểm soát đang có. Nguồn: [SP 800-53A Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/a/r5/final).

Trong ví dụ, đội dự án có thể kết hợp xem xét tài liệu, trao đổi với người thực hiện và kiểm tra hành vi của hệ thống. Mỗi cách cung cấp một góc nhìn khác nhau:

| Hoạt động minh họa | Điều có thể làm rõ | Điều chưa đủ để kết luận riêng |
|---|---|---|
| Xem quy trình nghỉ việc và cấu hình kết nối | Thiết kế luồng, điểm tích hợp và trách nhiệm | Mọi lần xử lý thực tế đều thành công |
| Trao đổi với nhân sự, IAM và đội ứng dụng | Cách nhận sự kiện, xử lý lỗi, xử lý ngoại lệ | Hành vi phần mềm đúng trong mọi nhánh |
| Thử một tình huống nghỉ việc có kiểm soát | Thời điểm khóa tài khoản và khả năng truy cập sau xử lý | Toàn bộ quần thể tài khoản trong kỳ đều được bao phủ |
| Đối soát dữ liệu xử lý trong kỳ | Trường hợp thiếu sự kiện, thất bại hoặc quá hạn | Mỗi log thành công đều phản ánh truy cập thực sự đã chặn |

Một kế hoạch tốt nêu rõ quần thể, cách lấy mẫu hoặc bao phủ toàn bộ, kỳ đánh giá, tiêu chí đạt và giới hạn kết luận. Một trường hợp thử nghiệm thành công không đại diện tự động cho mọi nhân viên, mọi ứng dụng và mọi kiểu phiên.

### Theo dấu một tình huống nghỉ việc

Giả sử tổ chức đặt mục tiêu nội bộ ngừng truy cập trong 15 phút kể từ lúc nhận sự kiện đã được xác nhận. Đội đánh giá thu thập:

```text
t0 = thời điểm hệ thống tiếp nhận sự kiện nghỉ việc hợp lệ
t1 = thời điểm IdP xác nhận đã khóa tài khoản
t2 = thời điểm cổng tài liệu từ chối truy cập qua phiên đang tồn tại
```

Nếu `t1 - t0 = 2 phút` nhưng `t2 - t0 = 47 phút`, không thể kết luận mục tiêu ngừng truy cập đã đạt chỉ từ log IdP. Kết quả này chỉ ra điểm cần điều tra ở phiên hoặc quyết định truy cập của ứng dụng.

Nếu không đo được `t2`, kết luận phù hợp là chưa có đủ bằng chứng về phần đó. Không tự thay `t2` bằng `t1`, vì hai dấu thời gian đại diện cho hai sự kiện khác nhau.

Kế hoạch còn cần xét tình huống lỗi: ứng dụng đích không phản hồi, sự kiện nhân sự bị trùng, tác vụ thu hồi chạy lại hoặc tài khoản có nhiều tổ chức. Những tình huống được chọn phải phản ánh thiết kế thực tế và rủi ro của phạm vi đánh giá.

## 8. Kiểm soát dùng chung và trách nhiệm của từng bên

Trong môi trường SSO, một phần kiểm soát được thực hiện tại IdP dùng chung, một phần tại ứng dụng và một phần trong quy trình tổ chức. Việc nhà cung cấp có một chức năng không có nghĩa khách hàng đã cấu hình và sử dụng chức năng ấy đúng.

Ví dụ, với MFA cho đăng nhập quản trị, đội dự án có thể ghi trách nhiệm:

| Bên tham gia | Phần trách nhiệm trong ví dụ | Bằng chứng cần đối chiếu |
|---|---|---|
| Đơn vị vận hành IdP | Cung cấp và vận hành cơ chế xác thực | Tài liệu phạm vi dịch vụ và thông tin vận hành thích hợp |
| Đội IAM của tổ chức | Cấu hình chính sách áp dụng cho nhóm quản trị | Cấu hình thực tế, nhóm được áp dụng, danh sách ngoại lệ |
| Đội ứng dụng | Ràng buộc các đường đăng nhập quản trị và sử dụng kết quả xác thực | Kiểm tra luồng SSO, local login và truy cập khẩn cấp |
| Chủ sở hữu nghiệp vụ | Xác định ai cần quyền quản trị, phê duyệt ngoại lệ | Quyết định cấp quyền và kết quả rà soát |

Một báo cáo của nhà cung cấp có thể được tham chiếu cho phần họ vận hành, nhưng không thay thế bằng chứng về nhóm quản trị của chính tổ chức. Nếu tài khoản local còn truy cập được mà không qua chính sách đã đặt, bảng mapping phải thể hiện khoảng trống ấy.

Với danh tính workload, các câu hỏi triển khai có thể khác hẳn tài khoản con người: ai sở hữu workload, thông tin xác thực được cấp bằng cách nào, quyền tài nguyên được giới hạn ra sao và quyền bị thu hồi khi workload hết vòng đời thế nào. Không ghi “đã có MFA cho nhân viên” làm bằng chứng thay cho kiểm soát workload.

## 9. Quản lý bằng chứng, khoảng trống và ngoại lệ

Một tham chiếu bằng chứng cần kèm phạm vi và thời điểm để biết nó chứng minh điều gì. Với kết quả rà soát quyền, có thể cần mã chiến dịch, danh sách quần thể, người duyệt, quyết định và kết quả thực thi các quyết định thu hồi. Một file chỉ ghi “review completed” chưa cho biết quyền thừa đã được xử lý.

Bằng chứng IAM có thể chứa thông tin nhạy cảm. Hồ sơ mapping nên lưu tham chiếu đến kho bằng chứng có kiểm soát truy cập, thay vì sao chép access token, khóa bí mật hoặc toàn bộ hồ sơ cá nhân vào bảng chung. Người xem dashboard tổng hợp không mặc nhiên được quyền đọc tất cả bằng chứng gốc.

Khi phát hiện khoảng trống, cần phân biệt:

| Trạng thái nội bộ | Cách hiểu |
|---|---|
| Chưa triển khai | Biện pháp cần thiết còn thiếu |
| Triển khai một phần | Đã có một phần nhưng chưa bao phủ phạm vi hoặc tiêu chí |
| Chưa đủ bằng chứng | Chưa có cơ sở để đánh giá phần đã tuyên bố |
| Đánh giá không đạt | Có dữ liệu cho thấy hành vi không đáp ứng tiêu chí |
| Không áp dụng | Có lập luận phạm vi được xem xét và phê duyệt phù hợp |
| Ngoại lệ đã chấp thuận | Có quyết định xử lý rủi ro cho sai lệch trong thời hạn xác định |

Ngoại lệ không tự biến một yêu cầu chưa đáp ứng thành yêu cầu đã đạt. Chẳng hạn, chấp nhận tạm thời một tài khoản khẩn cấp ngoài chính sách MFA phải giữ nguyên mô tả sai lệch, người chấp thuận, giới hạn sử dụng và thời điểm xem xét lại.

Một kết luận “không áp dụng” cũng cần cơ sở. Việc hiện chưa có bằng chứng hoặc chưa tìm thấy owner không phải lý do để loại yêu cầu khỏi phạm vi.

## 10. Tự động hóa và quản lý thay đổi

OSCAL của NIST cung cấp các mô hình máy đọc được để biểu diễn catalog, lựa chọn và điều chỉnh kiểm soát, triển khai hệ thống cũng như kế hoạch và kết quả đánh giá. Cấu trúc này hỗ trợ liên kết giữa các lớp thông tin. Xem [OSCAL — Layers and Models](https://pages.nist.gov/OSCAL/learn/concepts/layer/).

Tự động hóa có thể giúp phát hiện mã kiểm soát không tồn tại, quan hệ thiếu nguồn, owner bỏ trống hoặc bằng chứng quá hạn theo quy tắc tổ chức. Tuy nhiên, một file đúng YAML và có đủ trường chưa chứng minh lập luận mapping đúng về nội dung.

Trong ví dụ cổng tài liệu, đội dự án có thể đặt các kiểm tra dữ liệu:

- Mỗi mã yêu cầu, kiểm soát và bằng chứng được tham chiếu phải tồn tại trong registry tương ứng.
- Mỗi quan hệ có tài liệu nguồn, phiên bản, phạm vi và giải trình.
- Quan hệ `SUPPORTS_PART` có mô tả phần được hỗ trợ và phần còn thiếu.
- Trạng thái đánh giá đạt phải liên kết đến kết quả và bằng chứng của đúng phạm vi, đúng kỳ.
- Thay đổi chính sách, ứng dụng, nhóm người dùng hoặc catalog phải kích hoạt xem xét các quan hệ bị ảnh hưởng.

Các quy tắc trên là thiết kế registry minh họa. Khi chọn OSCAL hoặc công cụ khác, cần tuân theo schema và ý nghĩa của định dạng đã chọn; không gọi một YAML tự đặt tên trường là OSCAL chỉ vì nó chứa mã NIST.

Mapping cũng cần lưu lịch sử. Nếu một control được tách, gộp hoặc đổi nội dung trong bản catalog mới, đội dự án phải kiểm tra quan hệ hiện có. Không chỉ đổi trường phiên bản rồi mặc định mọi kết luận cũ còn nguyên hiệu lực.

Khi dùng crosswalk bên ngoài, cần biết ai tạo, dựa trên phiên bản nào, khi nào cập nhật và có review nội bộ chưa. FAQ của NIST lưu ý các Informative References trong catalog cộng đồng không kèm bảo đảm hay sự chứng thực mặc nhiên từ NIST; bên sử dụng phải tự thẩm định cho quyết định triển khai. Nguồn: [NIST OLIR FAQs](https://csrc.nist.gov/projects/olir/faqs).

## 11. Báo cáo tiến độ mà không đánh đồng với mức an toàn

Giả sử registry có 20 yêu cầu IAM thuộc phạm vi. Cả 20 đã có quan hệ mapping, nhưng chỉ 12 có triển khai hoàn tất và 9 có đánh giá đạt với bằng chứng còn phù hợp. Báo cáo “100% đã mapping” chỉ mô tả độ đầy của bảng quan hệ, không thể hiện 100% yêu cầu đã đạt.

Đội dự án nên tách các thông tin: số yêu cầu đã được đối chiếu, số quan hệ đã review, tình trạng triển khai, kết quả đánh giá, khoảng trống và tuổi của bằng chứng. Khi dùng tỷ lệ, phải công khai mẫu số, phạm vi và cách xử lý yêu cầu không áp dụng.

Một chỉ số đếm dòng còn có thể gây lệch ưu tiên. Một yêu cầu về thu hồi quyền quản trị có thể quan trọng hơn nhiều yêu cầu tài liệu nhỏ, nhưng chỉ chiếm một dòng. Vì thế, quyết định xử lý khoảng trống cần xét tác động và rủi ro, không chỉ tối ưu phần trăm dòng màu xanh.

## 12. Bài tập áp dụng

### Tình huống 1: bật MFA và tuyên bố đáp ứng mọi yêu cầu IAM

Một đội cung cấp ảnh cấu hình MFA ở IdP rồi đánh dấu toàn bộ yêu cầu cấp quyền, thu hồi quyền, phân quyền API và rà soát đặc quyền là hoàn tất. Hãy chỉ ra các lớp thông tin bị gộp nhầm và những bằng chứng cần bổ sung.

**Gợi ý:** Xác thực, vòng đời tài khoản, cưỡng chế quyền và rà soát quyền có mục tiêu khác nhau. Ảnh cấu hình chỉ hỗ trợ kết luận trong phạm vi cụ thể của nó.

### Tình huống 2: khóa IdP nhanh nhưng phiên ứng dụng còn dùng được

Log cho thấy khóa tài khoản sau hai phút. Một phiên cũ vẫn đọc tài liệu được sau 30 phút, trong khi mục tiêu nội bộ là 15 phút từ lúc nhận sự kiện hợp lệ. Hãy viết kết luận và mô tả khoảng trống mà không bỏ qua phần đã thực hiện tốt.

**Gợi ý:** Ghi riêng thành công ở IdP và thất bại của mục tiêu ngừng truy cập ứng dụng. Đừng dùng một dấu thời gian để thay thế sự kiện khác.

### Tình huống 3: nâng phiên bản framework

Một công cụ nhập catalog mới và giữ nguyên mọi kết luận mapping cũ. Một số phần tử nguồn đã bị gộp hoặc thay đổi nội dung. Hãy đề xuất cách xác định quan hệ cần review và cách bảo toàn kết quả đánh giá lịch sử.

**Gợi ý:** Cố định phiên bản của từng quan hệ và đợt đánh giá, đối chiếu thay đổi nội dung, lưu quyết định review và không sửa lịch sử thành bản mới một cách âm thầm.

Security control mapping hữu ích khi giúp trả lời được: yêu cầu nào được xử lý bởi kiểm soát nào, trong phạm vi nào, ai chịu trách nhiệm, triển khai ra sao và kết luận dựa trên bằng chứng gì. Một bảng nhiều liên kết chỉ có giá trị khi những câu hỏi ấy vẫn có thể được kiểm tra lại.
