# Security champion

## 1. Vai trò giúp yêu cầu bảo mật đi vào công việc của đội phát triển

Trong chương **Secure development**, security champion là thành viên trong hoặc gắn gần với đội sản phẩm, có nhiệm vụ hỗ trợ thực hành bảo mật trong công việc phát triển và kết nối đội với nguồn chuyên môn phù hợp.

Champion hiểu ngữ cảnh sản phẩm, kiến trúc và cách đội làm việc. Từ hiểu biết đó, họ giúp nhận diện thay đổi có rủi ro, đặt câu hỏi đúng, làm rõ yêu cầu, tìm mẫu triển khai phù hợp và theo dõi bằng chứng kiểm chứng.

OWASP mô tả champion như đầu mối giữa đội phát triển và AppSec; vai trò có thể do người làm phát triển, kiểm thử hoặc vai trò phù hợp khác đảm nhiệm, cùng chương trình hỗ trợ và đào tạo. [OWASP Developer Guide: Security champions program](https://devguide.owasp.org/en/08-culture-process/02-security-champions/01-security-champions-program/)

Trong module đặc tả yêu cầu bảo mật, đóng góp quan trọng của champion là giúp giữ chuỗi liên kết:

**Mục tiêu an toàn → rủi ro của thay đổi → yêu cầu cụ thể → quyết định kiến trúc → tiêu chí kiểm thử → bằng chứng trước và sau phát hành.**

Ví dụ, sản phẩm muốn thêm liên kết chia sẻ tài liệu. Champion hỗ trợ đội chuyển câu “chia sẻ phải an toàn” thành các câu hỏi: ai được tạo liên kết, chia sẻ tài nguyên nào, quyền nào được cấp, khi nào hết hạn, thu hồi được thực thi ở đâu và bằng chứng kiểm thử là gì.

Sau bài học, người học có thể:

- Định nghĩa trách nhiệm và phạm vi quyết định của champion.
- Đặc tả chương trình với thời gian, năng lực, hỗ trợ và người dự phòng.
- Gắn công việc champion với các điểm ra quyết định trong vòng đời phát triển.
- Phân biệt hỗ trợ kỹ thuật, xác minh kiểm soát và chấp nhận rủi ro.
- Viết yêu cầu quy trình đo được và kiểm chứng bằng hồ sơ thực tế.
- Đánh giá hiệu quả chương trình và duy trì liên tục khi nhân sự thay đổi.

Các mã, vai trò, thời hạn và dữ liệu minh họa bên dưới là lựa chọn của một chương trình giả định. Chúng cần được điều chỉnh theo mức rủi ro, cơ cấu tổ chức và nguồn lực thực tế.

## 2. Xác định trách nhiệm, quyền hạn và nguồn hỗ trợ

### 2.1. Trách nhiệm thường gặp

| Hoạt động | Sản phẩm công việc có thể quan sát |
|---|---|
| Nhận diện thay đổi có ảnh hưởng bảo mật | Phân loại thay đổi, tài sản và ranh giới tin cậy liên quan |
| Hỗ trợ threat modeling | Các tình huống đe dọa, giả định và vấn đề cần chuyên gia |
| Làm rõ yêu cầu | Yêu cầu có phạm vi, hành vi khi lỗi và tiêu chí chấp nhận |
| Hỗ trợ triển khai | Mẫu đã được duyệt, chỉ dẫn phù hợp stack và vấn đề cần quyết định |
| Hỗ trợ triage finding | Ngữ cảnh, bằng chứng, owner và đề xuất ưu tiên theo policy |
| Theo dõi xác minh | Liên kết yêu cầu với ca test và kết quả cho đúng bản phát hành |
| Chia sẻ kiến thức | Ví dụ đã xử lý, bài học và hướng dẫn có phiên bản |
| Chuyển cấp | Hồ sơ đủ ngữ cảnh gửi đúng role/kênh có thẩm quyền |

Khối lượng cụ thể phụ thuộc charter của chương trình. Không cần mọi champion thực hiện tất cả hoạt động ở cùng mức độ chuyên sâu.

### 2.2. Quyền hạn phải được cấp rõ

Một charter nên nêu:

- Champion được tự áp dụng những mẫu và quyết định chuẩn nào.
- Khi nào cần hỏi kiến trúc, AppSec, privacy hoặc người chịu trách nhiệm rủi ro.
- Ai xác nhận một kiểm soát kỹ thuật đã được thực hiện.
- Ai có quyền duyệt ngoại lệ, thay policy hoặc cho phát hành.
- Những quyết định nào đòi hỏi kiểm tra độc lập.
- Cơ chế xử lý bất đồng và hạn phản hồi.

OWASP nhấn mạnh việc làm rõ kỳ vọng và mandate của champion, cùng quyền quyết định trong giới hạn rủi ro mà tổ chức đã xác định. [OWASP Security Champions Guide: Trust your champions](https://securitychampions.owasp.org/principles/05_Trust_your_champions/)

Tên vai trò champion không tự cấp quyền chấp nhận mọi rủi ro, đóng mọi finding hoặc bỏ một gate. Nếu một người đồng thời là risk owner hoặc release approver, quyết định phải ghi rõ họ đang dùng thẩm quyền nào.

### 2.3. Trách nhiệm của các bên liên quan

Bảng sau là một cách phân công cho ví dụ. “Chịu trách nhiệm quyết định” cần được tổ chức gán cho role cụ thể; champion có thể hỗ trợ nhiều hàng nhưng không thay thế toàn bộ các role đó.

| Công việc | Người thực hiện chính | Role chịu trách nhiệm quyết định |
|---|---|---|
| Chốt phạm vi và nguồn lực chương trình | Chủ chương trình, quản lý đội và đại diện champion | Sponsor/chủ chương trình được chỉ định |
| Phân loại thay đổi và yêu cầu | Đội sản phẩm, champion, kỹ sư liên quan | Chủ sở hữu sản phẩm/thiết kế theo policy |
| Chọn kiến trúc và triển khai kiểm soát | Kỹ sư và kiến trúc sư, có tham vấn bảo mật | Technical owner |
| Xác minh yêu cầu bảo mật | Đội kiểm thử, người review và công cụ được cấp | Verification owner |
| Chấp nhận rủi ro còn lại | Risk owner với tư vấn chuyên môn | Risk owner được ủy quyền |
| Quyết định release | Quy trình/gate và người phát hành theo phạm vi | Release owner |
| Xử lý sự cố | Đội ứng phó, vận hành và đội sản phẩm | Incident lead theo quy trình sự cố |
| Duy trì năng lực và người dự phòng | Chủ chương trình, manager và mạng lưới champion | Chủ chương trình/manager theo phần trách nhiệm |

Trong đội nhỏ, một người có thể giữ nhiều role. Cần xác định trường hợp đòi hỏi độc lập và cơ chế bù phù hợp, thay vì chỉ thêm nhiều tên người trên biểu mẫu.

### 2.4. Thời gian và hỗ trợ phải có trong kế hoạch

Champion thường vẫn thực hiện công việc chuyên môn ban đầu. Chương trình cần thời gian được quản lý ghi nhận, kênh hỏi chuyên gia, tài liệu và kế hoạch phát triển năng lực.

OWASP SAMM mô tả chương trình với thời gian dành cho hoạt động an toàn thông tin và đào tạo phù hợp vai trò. Tổ chức cần lựa chọn cách bao phủ thích hợp với cơ cấu đội. [OWASP SAMM: Organization and Culture](https://owaspsamm.org/model/governance/education-and-guidance/stream-b/)

Ví dụ, một đội thí điểm thống nhất dành 4 giờ mỗi tuần cho champion. Con số này là ngân sách ban đầu, cần điều chỉnh nếu phát sinh review lớn; nó không tạo cam kết cá nhân phải hoàn tất mọi yêu cầu ngoài giờ.

Quản lý phải quyết định ưu tiên và capacity khi công việc vượt nguồn lực. Chương trình cần cả năng lực phản hồi của AppSec; có champion mà không có nơi giải quyết câu hỏi khó vẫn để lại khoảng trống.

## 3. Viết charter và mô hình rủi ro cho chương trình

### 3.1. Charter cần trả lời điều gì?

| Nội dung | Câu hỏi cần chốt |
|---|---|
| Mục tiêu | Chương trình muốn cải thiện hành vi hoặc kết quả nào? |
| Phạm vi | Sản phẩm, đội, stack và loại thay đổi nào được bao phủ? |
| Role và mandate | Champion được thực hiện/quyết định gì và cần chuyển cấp khi nào? |
| Nguồn lực | Thời gian, người hỗ trợ, tài liệu và công cụ ở đâu? |
| Năng lực | Điều kiện nào để làm độc lập, có mentor hay cần chuyên gia? |
| Kênh làm việc | Hệ thống ghi nhận, đầu mối, hạn phản hồi và đường dự phòng |
| Bằng chứng | Hồ sơ nào chứng minh hoạt động đã được thực hiện có chất lượng? |
| Tính liên tục | Khi nghỉ phép, đổi đội hoặc rời chương trình thì ai tiếp nhận? |
| Đánh giá | Chỉ số nào được theo dõi và chương trình được điều chỉnh ra sao? |

Chương trình cần sự hỗ trợ quản lý để thời gian và ưu tiên bảo mật có vị trí rõ trong công việc. Đây là một nội dung được OWASP Security Champions Guide nhấn mạnh. [OWASP: Secure management support](https://securitychampions.owasp.org/principles/03_Secure_management_support/)

Không dùng “mọi thay đổi phải được champion ký” làm mặc định nếu chưa xác định rủi ro, năng lực và khả năng phục vụ. Có thể có luồng chuẩn được tự động hóa, luồng cần tham vấn và luồng buộc chuyên gia review.

### 3.2. Rủi ro của mô hình tổ chức

| Mã rủi ro | Tình huống | Hệ quả |
|---|---|---|
| R-CHP-01 | Vai trò có tên nhưng thiếu scope, thời gian hoặc hỗ trợ | Yêu cầu bảo mật không được làm rõ đúng lúc |
| R-CHP-02 | Đội chuyển mọi trách nhiệm cho một người | Chất lượng triển khai và kiểm thử phụ thuộc quá mức vào cá nhân |
| R-CHP-03 | Champion vượt mandate hoặc được mặc định có toàn quyền | Ngoại lệ, finding hoặc release bị duyệt sai thẩm quyền |
| R-CHP-04 | Chỉ tham gia khi chuẩn bị release | Phát hiện vấn đề kiến trúc quá muộn, khó xử lý |
| R-CHP-05 | Không có đường chuyển cấp hoạt động được | Vấn đề rủi ro cao bị treo hoặc tự cho qua |
| R-CHP-06 | Đánh giá bằng số finding đóng hoặc số buổi tham gia | Tạo động lực che lỗi, làm nhiều hoạt động nhưng thiếu kết quả |
| R-CHP-07 | Kiến thức và hồ sơ nằm trong tài khoản cá nhân | Mất liên tục khi nhân sự thay đổi |
| R-CHP-08 | Chia sẻ quá rộng dữ liệu sự cố hoặc proof | Lộ secret, dữ liệu khách hàng hoặc thông tin nhạy cảm |

Mỗi rủi ro cần có yêu cầu quy trình và bằng chứng. Ví dụ, chống R-CHP-07 cần quyền truy cập được quản lý, kho dùng chung và kiểm tra bàn giao, chứ không chỉ nêu “có người backup”.

## 4. Gắn champion với vòng đời phát triển

### 4.1. Các điểm tham gia có đầu ra rõ

| Giai đoạn | Đóng góp của champion | Bằng chứng hoặc đầu ra |
|---|---|---|
| Lập kế hoạch | Nhận diện dữ liệu, đối tượng dùng và thay đổi ranh giới tin cậy | Phân loại thay đổi và câu hỏi chưa có lời giải |
| Đặc tả | Hỗ trợ chuyển mục tiêu thành yêu cầu đo được | ID yêu cầu, nguồn rủi ro và tiêu chí chấp nhận |
| Thiết kế | Cùng đội rà luồng dữ liệu, quyền và tình huống lỗi | Threat model, quyết định kiến trúc, vấn đề chuyển cấp |
| Triển khai | Hỗ trợ áp dụng mẫu đã được chấp nhận và nhận diện sai lệch | Review record, nhiệm vụ kỹ thuật và hướng dẫn liên quan |
| Kiểm thử | Giúp chọn ca âm/dương, sai quyền, lỗi phụ thuộc và phục hồi | Liên kết yêu cầu → test → evidence |
| Phát hành | Kiểm tra hồ sơ còn thiếu và chuyển đúng người quyết định | Trạng thái yêu cầu, finding, ngoại lệ và gate |
| Vận hành | Đưa finding/sự cố và cấu hình drift về backlog | Bài học, yêu cầu sửa và kiểm thử hồi quy |

Champion hỗ trợ chất lượng và kết nối công việc. Việc một người tham dự cuộc họp không tự chứng minh yêu cầu đã có implementation hoặc test.

### 4.2. Phân loại thay đổi để dùng nguồn lực đúng chỗ

Một đội có thể xác định nhóm cần review chuyên sâu khi:

- Thêm cơ chế xác thực, nguồn danh tính hoặc quyền quản trị.
- Thay đổi tenant isolation, object ownership hoặc cách cấp quyền.
- Mở chia sẻ công khai, upload, xử lý file không tin cậy hoặc egress.
- Xử lý thêm loại dữ liệu nhạy cảm hoặc đổi nơi lưu.
- Đổi khóa, secret, đường audit, recovery hoặc trust của pipeline.
- Thêm thành phần có đặc quyền hoặc thay đổi kiến trúc quan trọng.

Những tiêu chí này cần nằm trong policy có version. Champion hỗ trợ áp dụng; người đề nghị không được tự hạ phân loại chỉ để tránh review.

Một thay đổi theo mẫu chuẩn vẫn cần đáp ứng các điều kiện của mẫu: phạm vi, cấu hình, test và phần biến thể được phép. “Đã làm giống dự án trước” chưa đủ để kế thừa mọi kết luận.

### 4.3. Definition of Ready và Definition of Done

Nếu đội dùng Definition of Ready, phần bảo mật có thể yêu cầu biết owner, tài sản, loại thay đổi, yêu cầu cần áp dụng và điểm chưa được quyết định.

Definition of Done có thể yêu cầu:

- Yêu cầu có implementation và ca kiểm thử phù hợp.
- Evidence gắn với bản build/cấu hình đang xét.
- Finding hoặc khoảng trống đã được xử lý theo policy.
- Ngoại lệ được phép có đúng scope, thời hạn và người có thẩm quyền.
- Hướng dẫn vận hành, logging và phục hồi được cập nhật khi liên quan.

Các tiêu chí này cần được kiểm tra trong hệ thống làm việc. Không dùng checkbox do champion chọn làm thay bằng chứng của mọi điều kiện.

## 5. Từ một ý tưởng sản phẩm đến yêu cầu kiểm chứng được

Xét đội phát triển tính năng chia sẻ liên kết cho tài liệu đa tenant. Mục tiêu nghiệp vụ là cho người có quyền chia sẻ một tài liệu trong thời gian giới hạn.

### 5.1. Champion hỗ trợ đặt câu hỏi theo rủi ro

| Mối quan tâm | Câu hỏi cần làm rõ |
|---|---|
| Xác thực | Ai được tạo, gia hạn và thu hồi liên kết? |
| Phân quyền | Chủ thể có quyền chia sẻ chính tài liệu này trong tenant này không? |
| Dữ liệu | Liên kết cho đọc phần nào, có cho sửa hoặc tải hàng loạt không? |
| Hiệu lực | Khi hết hạn hoặc bị thu hồi, request nào phải bị từ chối và trong bao lâu? |
| Logging | URL hoặc token liên kết có bị ghi vào log, trace hay analytics không? |
| Audit | Ai làm gì, với tài nguyên nào và kết quả ra sao? |
| Lỗi và phục hồi | Restart, cache cũ, retry hoặc khôi phục dữ liệu có làm sống lại quyền đã thu hồi không? |

Sau đó đội có thể viết các yêu cầu sản phẩm, chẳng hạn:

| ID | Yêu cầu minh họa | Tiêu chí chấp nhận chính |
|---|---|---|
| SEC-SHARE-01 | Chỉ chủ thể đã xác thực và có quyền chia sẻ đối với tài liệu trong đúng tenant mới được tạo liên kết. | Thiếu danh tính, sai role hoặc sai tenant bị từ chối; không tạo quyền hay link mới. |
| SEC-SHARE-02 | Liên kết chỉ cấp quyền đọc tài liệu được chỉ định; mọi request mới bắt đầu sau thời điểm hết hạn không được cấp quyền qua link đó. | Không đọc tài liệu khác, không sửa dữ liệu; kiểm tra tại cận thời gian theo nguồn thời gian đã chọn. |
| SEC-SHARE-03 | Khi thu hồi được chấp nhận, mọi request mới sau thời hạn 60 giây không được dùng quyền của link đã thu hồi trên mọi điểm phục vụ. | Kiểm thử cache cũ, restart và điểm mất kết nối; không chỉ kiểm tra một instance khỏe. |
| SEC-SHARE-04 | Token hoặc URL chứa credential chia sẻ không xuất hiện trong log/trace/export bị cấm; audit quản lý chia sẻ chỉ dùng định danh được phép. | Dấu nhận dạng thử không đi vào các đầu ra đó; thao tác cấp/thu hồi vẫn có bằng chứng đã lọc. |

Thời hạn 60 giây là lựa chọn của ví dụ. Kiến trúc phải chứng minh cách đáp ứng; champion không thể tạo bảo đảm chỉ bằng cách ghi nó vào ticket.

SEC-SHARE-02 và SEC-SHARE-03 xác định phạm vi request mới. Hành vi của download đang diễn ra cần được quyết định riêng; hệ thống không thể thu hồi dữ liệu mà người nhận đã tải trước đó.

### 5.2. Giữ vấn đề chưa quyết định ở trạng thái rõ ràng

Nếu đội chưa biết cache phân tán sẽ thu hồi trong bao lâu, hồ sơ nên ghi:

- Yêu cầu và rủi ro đang bị ảnh hưởng.
- Phần kiến trúc chưa có bằng chứng.
- Owner của quyết định, người cần tham vấn và thời hạn cần giải quyết.
- Hạn chế đối với việc tiếp tục hoặc phát hành.
- Điều kiện để đóng vấn đề.

Champion hỗ trợ đưa vấn đề tới đúng người, còn technical owner và risk owner quyết định trong phạm vi của họ. Không chuyển một giả định thành yêu cầu “đã đạt” vì cuộc họp thiết kế đã kết thúc.

### 5.3. Một mẫu bản ghi yêu cầu

```yaml
requirementId: SEC-SHARE-03
revision: 1
riskRef: R-SHARE-STALE-PERMISSION
scope: documents-public-link
behavior: reject-new-requests-after-withdrawal-deadline
deadlineSeconds: 60

implementationOwnerRole: document-access-technical-owner
verificationOwnerRole: security-test-owner
championContribution: clarify-and-track-evidence
decisionAuthorityRole: product-risk-owner

architectureDecisionRef: ADR-SHARE-REVOCATION
testRefs:
  - share-revoke-with-cached-policy
  - share-revoke-during-instance-isolation
  - share-restart-after-withdrawal
evidenceRefs: []
status: DESIGN_OPEN
```

Đây là schema minh họa. ID và reference cần phân giải trong hệ thống hồ sơ thực tế; giá trị contribution chỉ ghi loại hỗ trợ, không cấp quyền tự phê duyệt.

## 6. Bộ yêu cầu cho chương trình security champion

### 6.1. Một yêu cầu quy trình đầy đủ

**CHP-01 — Thay đổi rủi ro cao có đường xử lý bảo mật trước phát hành**

- **Rủi ro:** R-CHP-01, R-CHP-04 và R-CHP-05.
- **Phạm vi:** các thay đổi được policy phân loại rủi ro cao trong những sản phẩm thuộc chương trình.
- **Điều kiện:** khi thay đổi được ghi nhận và trước điểm phát hành cần quyết định.
- **Yêu cầu:** có đầu mối hỗ trợ, owner xử lý, yêu cầu bảo mật và đường chuyển cấp áp dụng; phần chưa quyết định không được tự coi là đã chấp nhận.
- **Bằng chứng:** phân loại thay đổi, yêu cầu, quyết định review, ca kiểm thử và trạng thái khoảng trống.
- **Khi champion vắng:** đầu mối dự phòng hoặc AppSec tiếp nhận theo hợp đồng; thiếu champion không tự làm thay đổi mức rủi ro.
- **Tiêu chí chấp nhận:** lấy một thay đổi rủi ro cao và truy được người xử lý, quyết định đúng thẩm quyền cùng evidence cần cho gate.
- **Giới hạn:** có đường xử lý không đồng nghĩa ứng dụng đã đáp ứng mọi yêu cầu.

### 6.2. Các yêu cầu bổ sung

| ID | Hành vi bắt buộc trong chương trình minh họa | Bằng chứng chấp nhận chính |
|---|---|---|
| CHP-02 | Mỗi đơn vị thuộc phạm vi có champion hoặc đầu mối trong nhóm hỗ trợ chung, cùng coverage được công bố. | Danh mục đội/sản phẩm và đầu mối còn hiệu lực; khoảng trống được ghi rõ. |
| CHP-03 | Charter nêu nhiệm vụ, mandate, quyền, thời gian và nguồn hỗ trợ. | Role description và capacity đã được quản lý xác nhận; không chỉ danh sách tên. |
| CHP-04 | Người nhận vai trò có lộ trình năng lực và phạm vi làm việc theo mức đã được xác nhận. | Có bài tập/đánh giá phù hợp, mentor và hạn chế khi đang học. |
| CHP-05 | Thay đổi được phân loại theo tiêu chí có version, với lịch sử điều chỉnh. | Thử hạ phân loại trái quyền không làm bỏ review bắt buộc. |
| CHP-06 | Đầu ra review liên kết rủi ro, yêu cầu, owner, test và evidence. | Hồ sơ mẫu truy được chuỗi liên kết, gồm ca bị từ chối và tình huống lỗi liên quan. |
| CHP-07 | Chuyển cấp có role nhận, mốc phản hồi và đường dự phòng; sự cố dùng kênh ứng phó tương ứng. | Diễn tập vấn đề ngoài năng lực và đầu mối không phản hồi. |
| CHP-08 | Quyền duyệt ngoại lệ, đóng finding, sửa policy hoặc cho release được cấp riêng theo phạm vi. | Tên champion không vượt kiểm soát truy cập; quyết định ghi đúng thẩm quyền. |
| CHP-09 | Finding và yêu cầu chỉ được đóng theo tiêu chí bằng chứng; trạng thái chưa biết được giữ rõ. | Không đóng chỉ vì đã chuyển ticket hoặc công cụ không trả finding. |
| CHP-10 | Hồ sơ dùng kho được quản lý, có quyền phù hợp và hạn chế dữ liệu nhạy cảm. | Không chứa secret không cần thiết; người dự phòng có quyền đúng scope. |
| CHP-11 | Có cơ chế bàn giao khi vắng/đổi vai trò, giữ lịch sử và cập nhật quyền. | Người nhận truy được vấn đề đang mở; quyền chương trình cũ được xử lý theo chính sách. |
| CHP-12 | Chương trình theo dõi chất lượng, độ trễ, coverage và tải công việc; điều chỉnh theo kết quả. | Không dùng số finding đóng hoặc số buổi tham gia làm chỉ số duy nhất. |
| CHP-13 | Mẫu chuẩn và kiến thức dùng lại có owner, version và điều kiện áp dụng. | Mẫu lỗi thời hoặc ngoài scope không tự cấp kết luận cho thay đổi mới. |
| CHP-14 | Mọi ngoại lệ có scope, thẩm quyền, thời hạn và điều kiện kết thúc; không sửa lịch sử để làm như đã đạt. | Ngoại lệ hết hạn hoặc sai sản phẩm không được áp dụng tại gate. |

Các mã CHP là định danh nội bộ của bài học. Chúng đặc tả cơ chế tổ chức hỗ trợ an toàn phần mềm; các yêu cầu sản phẩm như SEC-SHARE vẫn cần implementation và kiểm chứng riêng.

## 7. Tuyển chọn, đào tạo và xác nhận năng lực

### 7.1. Chọn người cùng với điều kiện để làm được việc

Một ứng viên phù hợp có thể là developer, tester, kỹ sư nền tảng hoặc thành viên khác hiểu sản phẩm và sẵn sàng học. Cần trao đổi rõ mong muốn, phạm vi, thời gian và nguồn hỗ trợ trước khi giao nhiệm vụ.

Một kế hoạch onboarding có thể gồm:

| Giai đoạn minh họa | Nội dung thực hành | Bằng chứng đủ để chuyển bước |
|---|---|---|
| Hiểu vai trò | Đọc charter, biết các role, kênh và giới hạn quyền | Phân loại được tình huống nào tự xử lý, tình huống nào chuyển cấp |
| Học từ sản phẩm | Rà tài sản, dữ liệu, quyền và luồng lỗi cùng mentor | Tạo hoặc chỉnh được một yêu cầu có tiêu chí kiểm thử |
| Làm có hỗ trợ | Tham gia review một thay đổi và triage một finding | Giữ đúng bằng chứng, owner và lý do kết luận |
| Hoạt động trong scope | Xử lý nhóm nhiệm vụ đã được xác nhận | Có phạm vi năng lực và người hỗ trợ rõ ràng |
| Phát triển tiếp | Học chủ đề theo rủi ro và stack của đội | Bài học được áp dụng, kiểm tra và đưa về hướng dẫn chung khi phù hợp |

Đạt một khóa học hoặc chứng chỉ là dữ liệu về đào tạo, không tự chứng minh người đó có thể duyệt mọi thiết kế bảo mật.

### 7.2. Năng lực nên gắn với công việc cần làm

Trong ví dụ, bộ năng lực cơ bản gồm:

- Xác định chủ thể, tài nguyên, tenant và ranh giới tin cậy.
- Phân biệt xác thực với phân quyền.
- Viết yêu cầu về hành vi thành công, bị từ chối và lỗi phụ thuộc.
- Đọc kết quả công cụ cùng giới hạn của phương pháp.
- Ghi nhận rủi ro, bằng chứng và giả định chưa xác nhận.
- Biết tìm mẫu chuẩn và nhận diện khi thay đổi ra ngoài scope.
- Biết chuyển cấp sự cố hoặc vấn đề ngoài năng lực.
- Xử lý dữ liệu nhạy cảm trong ticket, log và ví dụ chia sẻ.

Năng lực sâu như thiết kế mật mã, identity federation hoặc phân tích một vấn đề runtime đặc biệt có thể nằm ở chuyên gia được chỉ định. Champion phải biết khi nào cần hỗ trợ, thay vì đưa ra kết luận thiếu căn cứ.

OWASP khuyến khích đầu tư thời gian và điều kiện phát triển cho champion. Chương trình cần biến đầu tư đó thành capacity và hoạt động học có thể áp dụng vào công việc. [OWASP: Invest in your champions](https://securitychampions.owasp.org/principles/09_Invest_in_your_champions/)

### 7.3. Đánh giá bằng bài thực hành có ngữ cảnh

Một bài đánh giá có thể giao tình huống thay đổi public link, yêu cầu ứng viên:

1. Xác định quyền và tài sản liên quan.
2. Viết một yêu cầu kiểm chứng được.
3. Tạo ca sai tenant và ca thu hồi.
4. Chỉ ra câu hỏi kiến trúc cần chuyên gia.
5. Ghi một finding kèm bằng chứng đã lọc.
6. Giải thích ai có quyền chấp nhận phần rủi ro còn lại.

Kết quả cần ghi phần đã đáp ứng và phần cần mentor. Không dùng số finding tìm được để xếp hạng năng lực chung, vì bài toán và độ khó có thể khác nhau.

## 8. Quy trình làm việc và chuyển cấp

### 8.1. Một yêu cầu hỗ trợ cần đủ ngữ cảnh

Khi đội cần hỗ trợ, bản ghi có thể gồm:

- Sản phẩm, thay đổi và technical owner.
- Dữ liệu, chủ thể và ranh giới tin cậy liên quan.
- Mục tiêu hoặc yêu cầu cần làm rõ.
- Tình huống rủi ro, tác động và bằng chứng đã có.
- Câu hỏi hoặc quyết định cụ thể đang cần.
- Mốc cần quyết định và ảnh hưởng tới kế hoạch.
- Đầu mối đang xử lý cùng trạng thái.

Không cần yêu cầu người báo cáo tự chứng minh đầy đủ một lỗ hổng trước khi được tiếp nhận. Phần chưa biết phải được ghi lại để hỗ trợ đúng chỗ.

### 8.2. Chuyển tới đúng luồng

| Tình huống | Luồng xử lý của chương trình minh họa |
|---|---|
| Câu hỏi thuộc mẫu chuẩn và trong phạm vi năng lực | Champion cùng đội áp dụng mẫu, ghi điều kiện và evidence |
| Thay đổi vượt mẫu hoặc có rủi ro cao | Technical owner và chuyên gia liên quan xem xét; ghi quyết định |
| Finding chưa rõ có thật hay không | Triage có bằng chứng; giữ trạng thái chưa xác nhận khi cần |
| Cần chấp nhận rủi ro hoặc ngoại lệ | Chuyển role có thẩm quyền; champion cung cấp ngữ cảnh |
| Có dấu hiệu đang lộ dữ liệu, mất kiểm soát hoặc bị xâm nhập | Dùng ngay kênh ứng phó sự cố; bổ sung champion để hỗ trợ ngữ cảnh |
| Champion không phản hồi/không có mặt | Dùng đầu mối dự phòng hoặc nguồn hỗ trợ chung theo charter |

Kênh báo cáo sự cố và kênh gửi finding phải cho phép thành viên đội liên hệ theo policy mà không bắt buộc đi qua champion. Nhờ đó một đầu mối vắng mặt không làm chậm tiếp nhận.

### 8.3. Hạn phản hồi cần định nghĩa đúng

Ví dụ, câu hỏi thông thường được xác nhận đã nhận trong hai ngày làm việc theo lịch hỗ trợ đã công bố. Mốc xác nhận không phải cam kết đã giải quyết xong.

Cần nêu:

- Thời điểm bắt đầu đo.
- Đâu là ngày/giờ hỗ trợ áp dụng.
- Ai tiếp nhận khi đầu mối chính vắng.
- Khi thiếu thông tin, phần chờ nào được ghi riêng.
- Khi quá hạn, role nào được báo hoặc nhận lại.
- Điều kiện nào cần quyết định trước thiết kế, trước merge hoặc trước release.

Không đặt lại timestamp để làm thời gian chờ trông ngắn hơn. Không tự coi hết thời gian chờ là đã được phê duyệt.

Vấn đề nghi sự cố thực tế đi theo lịch trực và cam kết phản ứng sự cố đã được tổ chức xác định. Nó không chờ tới hạn hai ngày của câu hỏi thông thường.

### 8.4. Ví dụ xử lý khoảng trống thu hồi public link

Nếu chưa chứng minh được SEC-SHARE-03:

1. Champion ghi rõ cache/instance nào chưa có cơ chế thu hồi phù hợp.
2. Technical owner đánh giá phương án kiến trúc và bằng chứng cần tạo.
3. Đội kiểm thử chuẩn bị ca có cache cũ, mất kết nối và restart.
4. Product owner cùng các role có thẩm quyền quyết định phạm vi giao hàng.
5. Nếu chọn chưa bật tính năng, điều kiện tắt và đường kích hoạt sau này phải được triển khai, kiểm thử và theo dõi.
6. Nếu policy cho phép ngoại lệ, hồ sơ phải nêu phạm vi, rủi ro, biện pháp bù, người quyết định và hiệu lực.

Champion không tự sửa tiêu chí 60 giây thành “khi có thể” rồi đóng yêu cầu. Thay yêu cầu cần quyết định có thẩm quyền và đánh giá tác động tới rủi ro.

## 9. Bằng chứng và chỉ số đánh giá chương trình

### 9.1. Giữ bằng chứng vừa đủ để đánh giá

Một bộ hồ sơ có thể gồm:

| Loại | Nội dung chính |
|---|---|
| Danh mục coverage | Đội/sản phẩm, đầu mối, scope, nguồn hỗ trợ và trạng thái hiện tại |
| Charter | Nhiệm vụ, mandate, capacity, quyền và đường chuyển cấp |
| Hồ sơ năng lực | Nhiệm vụ được làm, mentor, bằng chứng thực hành và phần còn cần hỗ trợ |
| Hồ sơ thay đổi | Rủi ro, yêu cầu, quyết định, owner, test và evidence |
| Hồ sơ finding/ngoại lệ | Lý do, tác động, thẩm quyền, thời hạn và retest |
| Kiến thức dùng lại | Hướng dẫn có owner/version, phạm vi áp dụng và bài học |
| Bàn giao | Việc đang mở, quyền truy cập, người nhận và xác nhận tiếp nhận |

Hồ sơ cần nằm trong nơi được quản lý, có lịch sử và quyền phù hợp. Với bằng chứng có secret hoặc dữ liệu khách hàng, dùng tham chiếu bảo vệ và bản tóm tắt đã lọc theo policy.

### 9.2. Chỉ số nên phản ánh hiệu lực

| Chỉ số | Điều nó giúp đánh giá | Điều cần kiểm soát |
|---|---|---|
| Coverage có hiệu lực | Phạm vi nào có đầu mối, năng lực, thời gian và hỗ trợ thực tế | Có tên trên danh sách chưa đủ |
| Thay đổi rủi ro cao được xem xét đúng mốc | Bảo mật tham gia trước quyết định khó đảo ngược | Mẫu số gồm mọi thay đổi thuộc tiêu chí, kể cả chưa xử lý |
| Chất lượng truy vết | Mẫu hồ sơ có đủ rủi ro → yêu cầu → test → evidence | Không tính chỉ theo số link hoặc checkbox |
| Thời gian chờ hỗ trợ | Điểm nghẽn giữa đội và nguồn chuyên môn | Tách xác nhận, chờ thông tin và quyết định; giữ lịch sử |
| Chất lượng đóng finding | Lỗi được đóng có evidence sửa/kiểm chứng phù hợp | Không thưởng cho số lượng đóng thiếu căn cứ |
| Lỗi tái diễn và phát hiện muộn | Kiến thức đã biến thành thay đổi hệ thống chưa | Cần xét độ khó, phạm vi và độ nhạy phát hiện |
| Tải công việc và khả năng hỗ trợ | Chương trình có capacity bền vững không | Không biến thành theo dõi cá nhân quá mức hoặc yêu cầu làm ngoài giờ |

Số buổi đào tạo hoặc số champion là chỉ số hoạt động. Chúng hữu ích để quản lý đầu vào nhưng cần đi cùng bằng chứng về công việc và kết quả.

Số finding tăng có thể do đội phát hiện tốt hơn. Không dùng riêng số đó để kết luận chương trình làm ứng dụng kém an toàn hoặc để phạt người báo cáo.

### 9.3. Ví dụ tránh báo cáo coverage quá cao

Một chương trình có 8 đội trong scope:

- 7 đội có tên đầu mối được ghi.
- Chỉ 5 đội có đủ scope năng lực, thời gian và nguồn dự phòng theo điều kiện chương trình.
- 2 đội còn lại có đầu mối đang học hoặc chưa có capacity/hỗ trợ phù hợp.
- 1 đội chưa có đầu mối.

Coverage danh nghĩa là 7/8, nhưng coverage đáp ứng hợp đồng hiện tại là 5/8. Báo cáo phải thể hiện cả hai cùng khoảng trống, owner và kế hoạch xử lý.

Tương tự, nếu trong 10 thay đổi rủi ro cao chỉ 8 thay đổi có hồ sơ đúng mốc, không loại 2 thay đổi chưa review khỏi mẫu số.

### 9.4. Kiểm tra chất lượng bằng lấy mẫu

Ví dụ, mỗi tháng chủ chương trình kiểm tra 5 hồ sơ thay đổi rủi ro cao, hoặc toàn bộ nếu ít hơn 5. Cần công bố cách chọn mẫu để không chỉ xem các hồ sơ dễ hoặc đã hoàn tất.

Một hồ sơ được kiểm tra theo những câu hỏi:

- Phân loại rủi ro có phù hợp không?
- Yêu cầu có thể kiểm chứng hay còn mơ hồ?
- Owner và người quyết định có đúng mandate không?
- Evidence có thuộc bản phát hành/cấu hình liên quan không?
- Ngoại lệ có còn hiệu lực và đúng scope không?
- Vấn đề đã được đóng theo tiêu chí nào?

Lấy mẫu không chứng minh mọi hồ sơ đều tốt. Nếu phát hiện lỗi hệ thống, cần mở rộng phạm vi hoặc thay quy trình theo mức ảnh hưởng.

## 10. Duy trì kiến thức, hỗ trợ và tính liên tục

### 10.1. Tài liệu dùng lại cần có vòng đời

Một mẫu review hoặc hướng dẫn an toàn nên có:

- Chủ sở hữu nội dung và version.
- Stack, loại dữ liệu và phạm vi kiến trúc áp dụng.
- Điều kiện, giới hạn và trường hợp cần chuyển cấp.
- Ví dụ triển khai/test đã được kiểm chứng trong phạm vi.
- Lần xem xét gần nhất và sự kiện kích hoạt cập nhật.
- Liên kết thay thế khi mẫu bị rút khỏi sử dụng.

Champion có thể đề xuất cải tiến từ kinh nghiệm sản phẩm. Policy và mẫu chuẩn cần đi qua quyền review/phê duyệt tương ứng trước khi được coi là nguồn có thẩm quyền.

Chia sẻ kiến thức nên dùng ví dụ tổng hợp hoặc đã được lọc. Không đưa token thật, dữ liệu khách hàng hoặc chi tiết sự cố đang hạn chế truy cập vào một buổi chia sẻ rộng.

### 10.2. Mạng lưới hỗ trợ giúp giảm điểm phụ thuộc

Tổ chức có thể kết hợp đầu mối gần đội với nhóm chuyên môn theo API, frontend, nền tảng hoặc các lĩnh vực khác. Cách tổ chức cần bảo đảm mỗi vấn đề vẫn có người nhận và owner rõ.

OWASP lưu ý phải chuẩn bị cho thay đổi nhân sự và tránh phụ thuộc quá lớn vào các cá nhân chủ chốt. [OWASP: Anticipate personnel changes](https://securitychampions.owasp.org/principles/10_Anticipate_personnel_changes/)

Có thể duy trì mentor, giờ hỗ trợ và kho câu hỏi có thể tìm kiếm. Việc đặt một người dự phòng trên danh sách chỉ có ý nghĩa khi người đó có thời gian, năng lực và quyền truy cập cần thiết.

### 10.3. Hợp đồng bàn giao

Khi champion nghỉ dài ngày, chuyển đội hoặc rời chương trình, cần:

1. Xác định việc đang mở, nghĩa vụ đến hạn và vấn đề chưa quyết định.
2. Gán người nhận theo phạm vi và xác nhận họ đã tiếp nhận.
3. Kiểm tra quyền truy cập hồ sơ và kênh hỗ trợ.
4. Cập nhật coverage, đầu mối và cơ chế chuyển cấp.
5. Xử lý quyền thuộc chương trình không còn cần theo policy, giữ quyền công việc khác theo vai trò tương ứng.
6. Giữ lịch sử người đã tham gia/quyết định tại thời điểm trước đó.

Không chuyển private key, token hay mật khẩu bằng tài liệu bàn giao. Dùng cơ chế quản lý truy cập và credential của tổ chức.

Người kế nhiệm cần hiểu được bằng chứng và lý do, không chỉ nhận danh sách ticket. Một quyết định quá khứ phải được đánh giá lại nếu scope hoặc điều kiện đã thay đổi.

### 10.4. Khi không có người đủ năng lực

Ghi rõ khoảng trống coverage và chuyển công việc cần chuyên môn tới nhóm hỗ trợ được cấp. Manager/chủ chương trình quyết định bổ sung nguồn lực hoặc điều chỉnh kế hoạch.

Các thay đổi theo luồng chuẩn vẫn có thể tiếp tục nếu đáp ứng điều kiện và gate hiện hành. Thay đổi cần chuyên gia chưa được thay thế bằng một checkbox “champion unavailable”.

Không coi champion là người trực sự cố mặc định. Nếu có nhiệm vụ trực, lịch, quyền, hỗ trợ và khả năng thay ca phải được quy định riêng.

## 11. Kế hoạch kiểm chứng chương trình

Đây là các tình huống đánh giá quy trình và quyền hạn, không phải những test phần mềm tự chứng minh mức an toàn của sản phẩm.

| Ca | Thiết lập hoặc tình huống | Kết quả chấp nhận |
|---|---|---|
| T01 | Một tính năng mới thay đổi tenant isolation | Có phân loại, yêu cầu, owner và đường review phù hợp trước gate cần thiết |
| T02 | Ứng viên đang học nhận câu hỏi ngoài scope | Có mentor/chuyên gia tiếp nhận; không tạo quyết định vượt mandate |
| T03 | Champion chính nghỉ phép khi có thay đổi rủi ro cao | Người dự phòng đủ điều kiện tiếp nhận; evidence không bị mất |
| T04 | Người có nhãn champion thử bỏ gate hoặc tự duyệt ngoại lệ ngoài quyền | Kiểm soát quyền từ chối; không tự tăng quyền vì tên vai trò |
| T05 | Finding được đề nghị đóng chỉ vì đã chuyển cho đội khác | Vẫn có owner và trạng thái đúng; chưa đóng nếu thiếu tiêu chí hoàn tất |
| T06 | Một ngoại lệ đã hết hạn hoặc khác sản phẩm | Không được áp dụng; cần quyết định mới nếu policy cho phép |
| T07 | Mẫu chuẩn được dùng cho kiến trúc ngoài scope | Nhận diện sai lệch và chuyển cấp; không kế thừa kết luận vô điều kiện |
| T08 | Có dấu hiệu dữ liệu đang bị truy cập trái phép | Đi vào kênh ứng phó sự cố, không chờ lịch hỗ trợ thông thường |
| T09 | Evidence có token hoặc dữ liệu nhạy cảm | Được hạn chế/lọc theo policy; không sao chép vào kênh chia sẻ rộng |
| T10 | Đầu mối có tên nhưng không có thời gian hoặc quyền hồ sơ | Coverage được đánh dấu thiếu điều kiện, không báo như đã bao phủ hiệu lực |
| T11 | Người báo finding liên hệ kênh bảo mật khi champion vắng | Kênh tiếp nhận hoạt động; không yêu cầu đợi riêng champion |
| T12 | Có đề nghị hạ phân loại thay đổi để tránh review | Cần đúng quyền và lý do, có lịch sử; không bỏ điều kiện âm thầm |
| T13 | Yêu cầu “an toàn” thiếu tiêu chí đo được được đưa vào review | Được làm rõ phạm vi, hành vi lỗi và acceptance criteria |
| T14 | Test chỉ dùng admin và bỏ ca sai tenant | Hồ sơ không được coi đủ cho yêu cầu phân quyền liên quan |
| T15 | Champion chuyển đội | Việc mở có người nhận, coverage/quyền được cập nhật, giữ lịch sử |
| T16 | Kết quả đào tạo tốt nhưng hồ sơ thực tế thiếu bằng chứng | Ghi nhận khoảng trống năng lực/quy trình; không dùng chứng chỉ thay evidence |

### 11.1. Ví dụ Given–When–Then

```gherkin
Given thay đổi chia sẻ tài liệu được phân loại rủi ro cao
And champion chính đang vắng
And đầu mối dự phòng có năng lực và quyền hỗ trợ đúng phạm vi
And ca kiểm thử thu hồi trên instance mất kết nối còn thiếu
When đội đề nghị phát hành tính năng
Then đầu mối dự phòng tiếp nhận hồ sơ và nêu rõ evidence còn thiếu
And không tự đánh dấu yêu cầu thu hồi là đạt
And quyết định phát hành đi theo gate và thẩm quyền hiện hành
And lịch sử thể hiện người nhận, phần chưa giải quyết và hành động tiếp theo
```

Ca dương cần chứng minh sau khi các điều kiện thực sự được đáp ứng, release không bị giữ chỉ vì thiếu tên của champion chính. Quy trình phải dựa vào quyền và bằng chứng được chấp nhận.

### 11.2. Điều đánh giá này không chứng minh

Một chương trình có đủ charter, đầu mối và hồ sơ vẫn cần kiểm chứng sản phẩm. Ví dụ, T14 chỉ kiểm tra quy trình nhận diện thiếu test; tính đúng của tenant isolation còn cần những phép thử và review kỹ thuật thực tế.

Tương tự, có kênh chuyển cấp không chứng minh chuyên gia luôn đáp ứng capacity. Cần theo dõi thời gian chờ và điều chỉnh nguồn lực khi hợp đồng hỗ trợ không được đáp ứng.

## 12. Bài tập: chuyển vai trò danh nghĩa thành cơ chế có bằng chứng

Một đội chỉ định một senior developer làm security champion. Mọi ticket bảo mật đều gán cho người đó, không dành thời gian, không có người dự phòng và policy nói “champion xác nhận là release được”.

Đội sắp phát hành public link cho tài liệu đa tenant. Test chỉ dùng admin; log đang ghi URL đầy đủ; cơ chế thu hồi còn phụ thuộc cache chưa có cận thời gian.

Hãy viết lại đề xuất gồm:

1. Charter của champion: scope, mandate, thời gian, hỗ trợ và điều kiện chuyển cấp.
2. Phân công cho technical owner, verification owner, risk owner và release owner.
3. Yêu cầu sản phẩm về quyền chia sẻ, tenant, hiệu lực, logging và phục hồi.
4. Evidence bắt buộc trước phát hành, gồm ca bị từ chối và ca lỗi.
5. Quy trình finding/ngoại lệ, kênh sự cố và đầu mối khi vắng mặt.
6. Cách đo coverage thực tế, chất lượng hồ sơ và khả năng bàn giao.

Một chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Mục tiêu | Chia sẻ đúng quyền và có thể thu hồi trong phạm vi cam kết |
| Rủi ro sản phẩm | Sai tenant, link tồn tại quá hạn hoặc lộ credential qua log |
| Yêu cầu sản phẩm | SEC-SHARE-01 đến SEC-SHARE-04 |
| Yêu cầu chương trình | CHP-01, CHP-06, CHP-07 và CHP-11 |
| Đóng góp champion | Làm rõ yêu cầu, nhận diện khoảng trống và nối đúng owner/chuyên gia |
| Evidence | Quyết định kiến trúc, test quyền/thu hồi, kiểm tra log và trạng thái gate |
| Bài học dùng lại | Mẫu review public link cùng giới hạn áp dụng và owner nội dung |

Sản phẩm cần đạt là cơ chế cộng tác có thể kiểm chứng: ai giúp đội làm rõ rủi ro, ai quyết định điều gì, điều kiện nào phải được thực hiện và bằng chứng nào cho thấy phần mềm đáp ứng yêu cầu.
