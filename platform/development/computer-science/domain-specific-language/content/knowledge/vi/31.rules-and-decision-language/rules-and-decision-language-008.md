# Phiên bản luật

Trong một hệ thống dùng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL) để mô tả luật và quyết định, luật thường thay đổi theo yêu cầu nghiệp vụ, chính sách, hợp đồng hoặc quy định. Một điều kiện đủ điều kiện có thể được điều chỉnh, ngưỡng phê duyệt có thể thay đổi, cách tính phí có thể được cập nhật hoặc một luật mới có thể thay thế luật cũ. **Phiên bản luật (rule versioning)** là cách quản lý các lần thay đổi đó để hệ thống biết chính xác nội dung nào được áp dụng, vào thời điểm nào, trong phạm vi nào và bởi ai.

Nếu chỉ ghi đè nội dung luật hiện tại, hệ thống sẽ khó giải thích một quyết định cũ được đưa ra dựa trên quy tắc nào. Nếu lưu nhiều bản sao mà không có quy tắc chọn phiên bản, hai môi trường có thể thực thi hai kết quả khác nhau. Một cơ chế versioning cần xác định danh tính ổn định của luật, lịch sử revision bất biến, trạng thái phát hành, thời gian hiệu lực, quan hệ giữa các luật trong một ruleset, chính sách tương thích và cách triển khai hoặc quay lui.

Phiên bản luật không chỉ là một con số gắn vào tên tệp. Nó là một phần của hợp đồng thực thi quyết định. Mỗi kết quả quan trọng cần có khả năng truy ngược về phiên bản luật, bộ luật, dữ liệu đầu vào và engine đã tạo ra kết quả đó.

## 1. Vì sao cần phiên bản luật?

Luật nghiệp vụ có vòng đời dài và thường thay đổi độc lập với mã ứng dụng. Ví dụ, hệ thống phê duyệt đơn vay có thể áp dụng các ngưỡng khác nhau theo chính sách từng giai đoạn:

- Trước ngày 1 tháng 1, khoản vay trên 100 triệu cần hai cấp phê duyệt.
- Từ ngày 1 tháng 1, ngưỡng được nâng lên 150 triệu.
- Một nhóm khách hàng doanh nghiệp được áp dụng chính sách riêng.
- Một quyết định cũ vẫn cần được giải thích theo chính sách tại thời điểm quyết định được tạo.

Nếu chỉ lưu nội dung luật mới nhất, không thể tái tạo chính xác quyết định cũ. Versioning giúp:

- Giữ lịch sử thay đổi và lý do thay đổi.
- Xác định luật nào được áp dụng tại một thời điểm.
- Thử nghiệm luật mới trước khi phát hành.
- Triển khai có kiểm soát theo môi trường hoặc nhóm người dùng.
- Quay lui về phiên bản đã biết là hoạt động đúng.
- Tái hiện và kiểm toán một quyết định đã xảy ra.
- Quản lý phụ thuộc giữa các luật và ruleset.
- Hỗ trợ nhiều phiên bản chính sách cùng tồn tại.
- Phân biệt lỗi trong nội dung luật với lỗi do dữ liệu hoặc engine.

Versioning đặc biệt quan trọng trong tài chính, bảo hiểm, thuế, định giá, phân quyền, tuân thủ và các hệ thống mà quyết định cần được giải thích sau nhiều tháng hoặc nhiều năm.

## 2. Phân biệt luật, revision và ruleset

Trước khi thiết kế versioning, cần phân biệt ba khái niệm:

- **Rule identity:** định danh ổn định của một luật xuyên suốt các lần chỉnh sửa.
- **Rule version/revision:** một bản nội dung cụ thể của luật tại một thời điểm trong lịch sử.
- **Ruleset version:** một tập hợp có phiên bản gồm nhiều luật, thứ tự áp dụng, cấu hình và phụ thuộc.

Ví dụ:

~~~text
Rule ID: credit.high_value_review

Revision 1:
  amount >= 100_000_000
  -> require_two_approvers

Revision 2:
  amount >= 150_000_000
  -> require_two_approvers

Ruleset: credit-policy
Version: 4.2
  includes:
    credit.high_value_review@2
    credit.customer_segment@3
    credit.risk_score@5
~~~

Rule ID giữ nguyên khi ý nghĩa nghiệp vụ của luật tiếp tục được phát triển. Revision mới biểu diễn nội dung mới. Ruleset version xác định tổ hợp luật chính xác mà một lần đánh giá sử dụng.

Nếu chỉ version từng luật mà không version ruleset, có thể không biết tổ hợp nào đã được triển khai cùng nhau. Ngược lại, chỉ version ruleset mà không lưu revision từng luật sẽ làm khó việc tái sử dụng hoặc so sánh thay đổi của một luật cụ thể.

## 3. Định danh ổn định cho luật

Một luật cần ID ổn định, không phụ thuộc vào vị trí dòng, tên hiển thị hoặc thứ tự trong tệp.

Ví dụ:

~~~text
rule "credit.high_value_review" {
    when application.amount >= 150000000
    then require_two_approvers()
}
~~~

ID có thể được cấu thành từ namespace, module và tên logic:

~~~text
credit.high_value_review
billing.late_fee
access.admin_approval
shipping.remote_area_surcharge
~~~

Các nguyên tắc đặt ID:

- Không tái sử dụng ID của luật đã bị loại bỏ cho một ý nghĩa khác.
- Không tạo ID từ số dòng hoặc vị trí trong tệp.
- Xác định quy tắc phân biệt chữ hoa/thường.
- Có namespace để tránh va chạm giữa module hoặc tổ chức.
- Đổi tên hiển thị không nhất thiết phải đổi ID.
- Nếu ý nghĩa nghiệp vụ thay đổi căn bản, cân nhắc tạo ID mới và đánh dấu luật cũ được thay thế.
- Giữ alias hoặc migration mapping khi cần tương thích với tham chiếu cũ.

ID ổn định giúp decision trace, audit log, ruleset manifest và công cụ quản trị liên kết được các revision với nhau.

## 4. Version là gì và có cần SemVer không?

Version có thể được biểu diễn bằng số nguyên tăng dần, chuỗi có cấu trúc hoặc revision ID duy nhất.

Một số dạng thường gặp:

| Cách biểu diễn | Ví dụ | Đặc điểm |
|---|---|---|
| Số revision | 1, 2, 3 | Đơn giản, dễ so sánh trong một rule ID |
| SemVer | 2.1.0 | Thể hiện mức thay đổi tương thích |
| Timestamp | 2026-11-15T10:30Z | Dễ nhận biết thời điểm tạo, không tự nói lên thứ tự phát hành |
| UUID/revision hash | r-8f3a... | Định danh duy nhất, khó đọc với con người |
| Version label | 2026-policy-a | Dễ gắn với chu kỳ nghiệp vụ |

SemVer (Semantic Versioning) thường dùng dạng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích theo hợp đồng đã công bố.
- MINOR: bổ sung khả năng theo cách tương thích.
- PATCH: sửa lỗi mà không chủ ý thay đổi hợp đồng.

Tuy nhiên, semantics của luật có thể thay đổi hành vi nghiệp vụ dù cấu trúc DSL không đổi. Ví dụ đổi ngưỡng từ 100 sang 150 là thay đổi hành vi, nhưng có thể không làm thay đổi kiểu dữ liệu hoặc schema. Vì vậy, không nên áp dụng SemVer máy móc. Cần định nghĩa rõ thế nào là breaking change đối với rule consumer.

Một hệ thống có thể dùng revision số nguyên để lưu lịch sử nội bộ, còn dùng version label hoặc release version cho ruleset được công bố.

## 5. Nội dung của một Rule Revision

Một revision nên lưu nội dung đầy đủ và metadata đủ để xác định nguồn gốc, trạng thái và cách áp dụng.

Ví dụ:

~~~yaml
ruleId: credit.high_value_review
revision: 7
status: APPROVED
dslVersion: "3"
createdAt: "2026-11-15T08:30:00Z"
createdBy: "policy-team"
changeReason: "Adjust threshold for current lending policy"
effectiveFrom: "2027-01-01T00:00:00Z"
effectiveTo: null
scope:
  region: VN
  product: personal-loan
contentHash: "sha256:..."
content: |
  rule "credit.high_value_review" {
      when application.amount >= 150000000
      then require_two_approvers()
  }
~~~

Các metadata quan trọng:

- Rule ID và revision.
- Trạng thái lifecycle.
- Phiên bản grammar hoặc DSL.
- Người tạo, người review và người phê duyệt.
- Thời điểm tạo và thời điểm phát hành.
- Lý do thay đổi.
- Thời gian hiệu lực.
- Phạm vi áp dụng như tenant, region, product hoặc channel.
- Content hash hoặc signature.
- Revision cha hoặc revision được thay thế.
- Dependency và compatibility constraint.
- Kết quả validation và test reference.

Không nên thay đổi nội dung của một revision đã phát hành. Nếu cần sửa, tạo revision mới. Điều này giúp mọi quyết định tham chiếu đến revision cũ vẫn có nghĩa ổn định.

## 6. Revision bất biến và lịch sử thay đổi

Một quy tắc quan trọng là revision đã publish nên bất biến (immutable). Sau khi được phát hành, không chỉnh sửa nội dung tại chỗ. Mọi sửa đổi tạo revision mới.

Ví dụ lịch sử:

~~~mermaid
flowchart TD
    A[Revision 1: Draft] --> B[Revision 1: Published]
    B --> C[Revision 2: Draft]
    C --> D[Revision 2: Approved]
    D --> E[Revision 2: Published]
    E --> F[Revision 3: Draft]
~~~

Nếu nội dung revision 1 bị ghi đè bằng nội dung revision 2, audit log chỉ cho biết có một lần sửa chứ không còn bản luật cũ để tái hiện quyết định. Một revision bất biến có thể được lưu bằng nội dung đầy đủ, content-addressed storage hoặc artifact repository.

Metadata quản trị có thể được cập nhật theo lifecycle, nhưng cần phân biệt trạng thái vận hành với nội dung revision. Ví dụ một revision có thể được đánh dấu deprecated sau này mà nội dung thực thi vẫn giữ nguyên.

## 7. Vòng đời của phiên bản luật

Một revision thường đi qua các trạng thái:

- **Draft:** đang soạn thảo, chưa được dùng cho quyết định chính thức.
- **Validated:** vượt qua kiểm tra cú pháp, kiểu và quy tắc tĩnh.
- **Tested:** đã chạy bộ kiểm thử theo yêu cầu.
- **In review:** đang chờ người có thẩm quyền xem xét.
- **Approved:** đã được phê duyệt.
- **Scheduled:** đã lên lịch có hiệu lực trong tương lai.
- **Published/Active:** được phép chọn để thực thi theo policy.
- **Deprecated:** không nên dùng cho cấu hình mới nhưng vẫn có thể cần để tái hiện lịch sử.
- **Retired:** không còn được chọn cho quyết định mới.
- **Archived:** được lưu trữ theo chính sách retention.

Một sơ đồ trạng thái minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Validated
    Validated --> Tested
    Tested --> InReview
    InReview --> Approved
    InReview --> Draft
    Approved --> Scheduled
    Approved --> Published
    Scheduled --> Published
    Published --> Deprecated
    Deprecated --> Retired
    Retired --> Archived
~~~

Không phải mọi tổ chức cần mọi trạng thái. Nhưng cần quy định ai có quyền chuyển trạng thái, điều kiện chuyển và thao tác nào được phép ở mỗi trạng thái.

### 7.1. Không đồng nhất Approved và Active

Approved nghĩa là nội dung đã được chấp thuận. Active nghĩa là phiên bản hiện được policy resolver chọn để thực thi trong một phạm vi và thời điểm. Một revision có thể được approved nhưng chưa đến ngày effectiveFrom, hoặc chỉ active ở một tenant thử nghiệm.

Tách hai khái niệm này giúp phê duyệt trước và triển khai sau.

### 7.2. Không xóa lịch sử đã phát hành

Một revision retired vẫn có thể cần cho audit hoặc replay. Thường nên giữ nội dung và metadata theo retention policy thay vì xóa vật lý. Nếu có yêu cầu xóa dữ liệu cá nhân, cần tách dữ liệu nhạy cảm khỏi artifact luật và áp dụng chính sách lưu trữ phù hợp.

## 8. Phiên bản DSL khác phiên bản luật

Phiên bản ngôn ngữ và phiên bản luật là hai trục độc lập.

- **DSL language version:** grammar, type system và semantics của ngôn ngữ.
- **Rule revision:** nội dung một luật nghiệp vụ.
- **Ruleset version:** tổ hợp luật được phát hành.
- **Rule schema version:** cấu trúc metadata hoặc input/output contract.
- **Decision engine version:** phiên bản runtime đánh giá luật.

Ví dụ, revision 7 của một luật có thể được viết bằng DSL version 3, được đưa vào ruleset 4.2 và chạy trên engine 5.1.

Một thay đổi grammar không nhất thiết có nghĩa nội dung luật thay đổi. Ngược lại, một ngưỡng nghiệp vụ có thể thay đổi mà không cần nâng DSL language version.

Manifest cần lưu các version độc lập này để có thể chọn parser và runtime phù hợp.

## 9. Phiên bản hiệu lực và thời gian ghi nhận

Trong rule management, cần phân biệt thời gian một revision được ghi vào hệ thống với thời gian nó có hiệu lực nghiệp vụ.

Hai khái niệm:

- **Transaction time:** thời điểm hệ thống ghi nhận revision hoặc thay đổi.
- **Valid time:** khoảng thời gian quy tắc được xem là có hiệu lực trong nghiệp vụ.

Ví dụ, chính sách mới được phê duyệt ngày 15 tháng 11 nhưng chỉ có hiệu lực từ ngày 1 tháng 1 năm sau. Transaction time là tháng 11; valid time bắt đầu tháng 1.

Điều này cho phép trả lời hai câu hỏi khác nhau:

1. Hệ thống biết chính sách mới từ khi nào?
2. Chính sách mới áp dụng cho các giao dịch nghiệp vụ từ khi nào?

Với hệ thống cần audit lịch sử sâu, có thể dùng mô hình bitemporal lưu cả hai chiều thời gian.

## 10. Effective date và khoảng hiệu lực

Một revision có thể khai báo:

~~~text
rule "billing.late_fee" version 3 {
    effective from 2027-01-01
    effective until 2027-06-30

    when invoice.days_overdue > 10
    then fee = invoice.balance * 0.02
}
~~~

Cần xác định rõ:

- effectiveFrom có bao gồm thời điểm bắt đầu không.
- effectiveTo có bao gồm thời điểm kết thúc không.
- Dùng timezone nào.
- Ngày không có giờ được diễn giải theo timezone nào.
- Khoảng hiệu lực có thể chồng lấn không.
- Có cho phép khoảng trống không có revision active không.
- Xử lý ngày nghỉ hoặc lịch nghiệp vụ như thế nào.

Dùng khoảng nửa mở [from, to) thường giúp tránh hai phiên bản cùng hiệu lực tại một thời điểm biên. Ví dụ revision A kết thúc nhưng không bao gồm 1/1; revision B bắt đầu và bao gồm 1/1.

Không nên so sánh ngày giờ bằng local timezone của máy chạy engine. Cần dùng timezone nghiệp vụ được cấu hình và biểu diễn instant một cách nhất quán.

## 11. Chọn revision khi thực thi

Khi đánh giá một quyết định, hệ thống cần chọn một revision phù hợp. Policy resolver có thể dùng:

- Rule ID.
- Ruleset hoặc policy name.
- Thời điểm nghiệp vụ cần áp dụng.
- Tenant, region, product, channel hoặc customer segment.
- Revision được pin tường minh.
- Compatibility với input schema và engine.
- Trạng thái approved/published.
- Priority hoặc scope specificity.

Ví dụ logic:

~~~text
resolve(
    ruleId = "credit.high_value_review",
    ruleset = "credit-policy",
    tenant = "vn-retail",
    effectiveAt = application.submittedAt
)
~~~

Kết quả nên là một revision cụ thể, không phải một con trỏ mơ hồ như latest nếu cần tái hiện quyết định sau này.

### 11.1. Latest không phải lúc nào cũng đúng

Chọn revision mới nhất có thể phù hợp với môi trường phát triển, nhưng không phải lúc nào cũng phù hợp cho production. Một quyết định được tạo theo ngày nghiệp vụ quá khứ có thể phải dùng phiên bản hiệu lực tại ngày đó, dù hiện tại đã có phiên bản mới hơn.

### 11.2. Pin version

Một workflow hoặc sản phẩm có thể pin ruleset version cụ thể để tránh kết quả thay đổi bất ngờ giữa hai lần chạy. Pinning hữu ích cho batch processing, replay, test và quy trình cần tái lập.

### 11.3. Resolution phải có kết quả rõ ràng

Nếu không tìm được revision active, có nhiều revision cùng phù hợp hoặc dependency không tương thích, resolver nên trả lỗi hoặc trạng thái chưa xác định. Không nên âm thầm chọn revision đầu tiên trong danh sách.

## 12. Phiên bản từng luật và phiên bản ruleset

Một quyết định nghiệp vụ thường phụ thuộc nhiều luật. Quản lý riêng từng rule revision chưa đủ nếu cần tái hiện chính xác tập luật được chạy cùng nhau.

Ruleset version có thể chứa manifest cố định:

~~~yaml
rulesetId: credit-policy
version: 4.2.0
engineConstraint: ">=5.1 <6"
dslVersion: "3"
rules:
  - id: credit.base_eligibility
    revision: 4
  - id: credit.high_value_review
    revision: 7
  - id: credit.customer_segment
    revision: 3
  - id: credit.risk_score
    revision: 5
~~~

Manifest này đóng vai trò snapshot. Nếu một luật riêng lẻ có revision mới, ruleset 4.2 vẫn giữ các revision cũ cho đến khi ruleset version mới được phát hành.

Lợi ích:

- Quyết định có thể được tái hiện với đúng tổ hợp luật.
- Test có thể chạy trên snapshot cố định.
- Triển khai giữa staging và production có thể dùng cùng manifest.
- Rollback có thể trỏ về ruleset version trước.
- Thay đổi một luật không tự động làm thay đổi mọi consumer.

## 13. Dependency giữa các luật

Một luật có thể gọi hàm, tham chiếu decision table hoặc phụ thuộc kết quả từ luật khác. Dependency cần được version hóa hoặc ràng buộc rõ.

Ví dụ:

~~~text
rule "credit.final_decision" {
    let eligibility = evaluate("credit.base_eligibility")
    let risk = evaluate("credit.risk_score")

    when eligibility.allowed and risk.score < 70
    then decision = "APPROVE"
}
~~~

Nếu credit.final_decision revision 2 phụ thuộc credit.risk_score revision 4, nhưng resolver tự chọn risk_score revision 5, kết quả có thể thay đổi mà không có thay đổi ở final_decision. Có thể giải quyết bằng:

- Pin dependency revision.
- Pin toàn bộ ruleset snapshot.
- Khai báo version range tương thích và giải quyết thành lockfile.
- Dùng contract test giữa các luật.
- Ghi dependency resolution vào decision trace.

Với quyết định cần tái lập, dependency resolution cuối cùng nên được cố định trong ruleset manifest hoặc decision record.

## 14. Quy tắc tương thích (compatibility)

Một revision mới có thể tương thích hoặc không tương thích với consumer hiện tại.

Cần kiểm tra nhiều lớp:

- Input schema: field bắt buộc, kiểu và nullability.
- Output contract: tên decision, action và kiểu kết quả.
- DSL semantics: toán tử, hàm và cách xử lý null.
- Runtime API: built-in function và extension.
- Dependency: rule ID và revision được gọi.
- Side effects: hành động mới hoặc thay đổi thứ tự.
- Temporal semantics: effective date và timezone.
- Error behavior: lỗi mới hoặc cách fallback khác.

Ví dụ revision cũ trả:

~~~text
decision: APPROVE | REJECT
~~~

Revision mới thêm trạng thái:

~~~text
decision: APPROVE | REJECT | MANUAL_REVIEW
~~~

Consumer chỉ xử lý hai trạng thái cũ có thể lỗi hoặc bỏ sót trường hợp mới. Đây là breaking change ở output contract dù DSL syntax vẫn hợp lệ.

## 15. Backward và forward compatibility

- **Backward compatibility:** consumer hoặc runtime mới có thể xử lý artifact/rule revision cũ.
- **Forward compatibility:** consumer cũ có thể xử lý phiên bản mới trong phạm vi đã công bố, ví dụ giữ hoặc bỏ qua extension không ảnh hưởng semantics.

Trong rule system, compatibility cần xem cả cấu trúc lẫn hành vi. Một revision có thể giữ nguyên schema nhưng thay đổi ngưỡng, nên vẫn là thay đổi hành vi quan trọng.

Một số chiến lược:

- Thêm field output tùy chọn thay vì đổi field hiện có.
- Giữ ý nghĩa của enum đã phát hành.
- Version hóa input/output contract.
- Dùng adapter cho schema cũ.
- Đặt default rõ cho field mới.
- Không đổi semantics của built-in trong minor release nếu hợp đồng yêu cầu ổn định.
- Tạo major version khi thay đổi không tương thích.
- Chạy consumer contract tests trước khi phát hành.

## 16. Migration luật khi DSL thay đổi

Khi grammar hoặc API DSL thay đổi, luật cũ có thể cần migration.

Ví dụ cú pháp cũ:

~~~text
rule "discount" {
    if customer.vip then discount = 0.1
}
~~~

Cú pháp mới:

~~~text
rule "discount" {
    when customer.vip
    then discount = 0.1
}
~~~

Migration có thể gồm:

1. Parse bằng grammar phiên bản cũ.
2. Chuyển AST cũ sang canonical model.
3. Chuyển canonical model sang AST mới.
4. Serialize bằng grammar mới.
5. Validate semantics và dependencies.
6. Chạy test so sánh hành vi.
7. Tạo revision mới, giữ nguyên revision gốc.

Không nên chỉ thay chuỗi bằng regex nếu thay đổi grammar có thể ảnh hưởng đến nested block, comment, string literal hoặc precedence. Dùng AST transformation để giữ cấu trúc và source mapping.

Migration cần ghi lại tool version, nguồn đầu vào, kết quả và diagnostics. Nếu không thể chuyển đổi chính xác, báo phần không hỗ trợ và yêu cầu review thủ công.

## 17. Thay đổi cấu trúc và thay đổi hành vi

Một diff văn bản nhỏ có thể tạo thay đổi hành vi lớn. Ví dụ:

~~~diff
- when score > 70
+ when score >= 70
~~~

Chỉ một ký tự thay đổi nhưng trường hợp score bằng 70 chuyển từ không khớp sang khớp.

Ngược lại, một diff lớn do formatter có thể không thay đổi semantics. Vì vậy, review version luật nên hiển thị cả:

- Text diff.
- AST/semantic diff.
- Thay đổi input/output contract.
- Thay đổi dependency.
- Thay đổi phạm vi và effective date.
- Kết quả test trước/sau.
- Các ví dụ quyết định bị thay đổi.

Một semantic diff có thể mô tả: “ngưỡng điểm được bao gồm giá trị biên 70” thay vì chỉ hiển thị một ký tự.

## 18. Phê duyệt và separation of duties

Trong môi trường quản trị, người viết luật không nhất thiết là người phê duyệt hoặc phát hành.

Một quy trình có thể yêu cầu:

- Author tạo revision draft.
- Validator kiểm tra cú pháp, kiểu và dependency.
- Test runner chạy test suite.
- Reviewer xem semantic diff và thay đổi nghiệp vụ.
- Approver phê duyệt.
- Release manager lên lịch hoặc publish.
- Runtime resolver chọn revision active theo policy.

Có thể áp dụng separation of duties: người tạo không được tự phê duyệt thay đổi rủi ro cao. Quyền cần gắn với vai trò và phạm vi (project, ruleset, tenant, environment).

Approval nên gắn với chính content hash của revision. Nếu nội dung thay đổi sau khi phê duyệt, approval cũ không còn hợp lệ và cần review lại.

## 19. Triển khai phiên bản luật

Publish một revision không nhất thiết đồng nghĩa mọi request lập tức dùng revision đó. Có thể có nhiều chiến lược triển khai.

### 19.1. Immediate activation

Sau khi publish, resolver chọn revision mới ngay cho các quyết định mới trong phạm vi được cấu hình. Cần bảo đảm cache và các instance runtime cùng nhận cấu hình nhất quán.

### 19.2. Scheduled activation

Revision được publish và lên lịch có hiệu lực trong tương lai. Resolver dùng effective time để chọn đúng version. Cần đồng bộ clock và timezone.

### 19.3. Canary rollout

Revision mới chỉ áp dụng cho một tỷ lệ hoặc nhóm nhỏ request. Mục tiêu là quan sát kết quả trước khi mở rộng. Cần ghi rõ cohort hoặc routing key để quyết định có thể tái hiện.

### 19.4. Blue-green hoặc versioned deployment

Hai ruleset version tồn tại đồng thời. Một alias hoặc configuration pointer quyết định version đang phục vụ traffic. Chuyển pointer có thể đơn giản hóa rollback, nhưng cần bảo đảm tất cả instance dùng cùng snapshot.

### 19.5. Shadow evaluation

Hệ thống đánh giá cả revision cũ và mới nhưng chỉ dùng kết quả cũ để quyết định thực tế. Kết quả mới được ghi để so sánh. Shadow mode hữu ích khi đánh giá ảnh hưởng, nhưng cần kiểm soát side effect: bản shadow không được gửi thông báo, tạo giao dịch hoặc thực hiện hành động thật.

## 20. Rollback và phục hồi

Rollback đưa hệ thống về một revision hoặc ruleset version trước đó. Nó không nhất thiết xóa revision mới; thường chỉ thay đổi version đang được chọn.

Một quy trình rollback:

1. Xác định ruleset version ổn định trước đó.
2. Kiểm tra runtime và input schema còn tương thích.
3. Cập nhật active pointer hoặc routing policy.
4. Invalidate cache theo version.
5. Xác nhận các instance đã nạp snapshot mới.
6. Theo dõi quyết định và lỗi sau rollback.
7. Ghi audit event và lý do rollback.

Không phải lúc nào rollback cũng an toàn. Nếu revision mới đã tạo side effect hoặc ghi dữ liệu theo schema mới, quay về luật cũ không tự đảo ngược những thay đổi đã xảy ra. Có thể cần compensating action hoặc migration dữ liệu riêng.

Rollback cần phân biệt “quay về rule logic cũ” với “hoàn tác mọi nghiệp vụ đã phát sinh”. Hai việc này có phạm vi khác nhau.

## 21. Tái hiện quyết định (decision replay)

Một mục tiêu quan trọng của versioning là có thể tái hiện quyết định cũ. Chỉ lưu rule ID và version có thể chưa đủ.

Một decision record nên lưu hoặc tham chiếu:

- Decision ID.
- Thời điểm đánh giá.
- Rule ID/revision hoặc ruleset version.
- Danh sách dependency revision đã resolve.
- DSL version và engine version.
- Input snapshot hoặc reference có integrity.
- Context như tenant, region, product và channel.
- Effective time được dùng để chọn luật.
- Output, explanation và matched rule trace.
- Các external facts được inject.
- Configuration ảnh hưởng kết quả.

Ví dụ:

~~~json
{
  "decisionId": "dec-90812",
  "evaluatedAt": "2027-02-10T09:15:00Z",
  "businessTime": "2027-02-10T09:15:00Z",
  "ruleset": {
    "id": "credit-policy",
    "version": "4.2.0"
  },
  "engineVersion": "5.1.3",
  "inputRevision": "sha256:...",
  "result": {
    "decision": "MANUAL_REVIEW"
  }
}
~~~

Nếu input chứa dữ liệu cá nhân, có thể lưu bản đã mã hóa hoặc reference đến bản snapshot được kiểm soát quyền truy cập. Không nên ghi toàn bộ dữ liệu nhạy cảm vào audit log nếu không cần.

## 22. Tính xác định và môi trường đánh giá

Cùng một input và cùng phiên bản luật nên tạo cùng kết quả nếu hệ thống yêu cầu deterministic decision. Nhưng một số hàm có thể phụ thuộc:

- Thời gian hiện tại.
- Random number.
- External API.
- Dữ liệu reference thay đổi.
- Locale hoặc timezone máy.
- Environment variable.
- Feature flag.
- Cache state.

Để replay đáng tin cậy, cần inject các giá trị này thành input/context có version hoặc snapshot. Ví dụ thay vì gọi now() trực tiếp trong rule, engine nhận evaluationTime tường minh. Thay vì gọi API tỷ giá trong lúc evaluate, hệ thống truyền tỷ giá đã được chụp cùng revision.

Nếu luật có side effect, cần tách phần quyết định thuần khỏi phần thực thi hành động. Replay chỉ nên tính lại decision; nó không được gửi lại email, trừ tiền hoặc tạo giao dịch lần nữa.

## 23. Cache và version resolution

Kết quả hoặc compiled rule có thể được cache để tăng hiệu năng. Cache key phải bao gồm mọi yếu tố ảnh hưởng kết quả:

- Rule/revision hoặc ruleset version.
- Engine version nếu semantics runtime thay đổi.
- Input schema version.
- Tenant/scope nếu luật phụ thuộc.
- Evaluation time bucket nếu hiệu lực theo thời gian.
- Context hoặc external facts revision.
- Configuration và feature flags.

Nếu cache chỉ dùng rule ID mà không có revision, khi luật thay đổi, engine có thể trả kết quả từ phiên bản cũ. Nếu cache dùng latest làm key, nó vẫn cần invalidation đúng lúc alias latest trỏ sang version mới.

Compiled artifact cũng cần được gắn với DSL version, engine ABI hoặc runtime API tương thích.

## 24. Xung đột giữa các luật và thứ tự ưu tiên

Một ruleset có thể chứa nhiều luật cùng khớp. Phiên bản luật có thể thay đổi kết quả không chỉ bằng điều kiện mà còn bằng priority, salience hoặc conflict resolution strategy.

Cần định nghĩa:

- Một luật hay nhiều luật có thể match.
- Thứ tự thực thi.
- Dừng sau kết quả đầu tiên hay tiếp tục.
- Luật nào ghi đè kết quả trước.
- Cách kết hợp output.
- Xử lý hai luật có hành động mâu thuẫn.
- Priority có ổn định qua các revision hay không.

Ví dụ:

~~~text
rule "discount.vip" priority 20 {
    when customer.vip
    then discount = 0.15
}

rule "discount.campaign" priority 10 {
    when campaign.active
    then discount = 0.10
}
~~~

Nếu policy chọn priority cao nhất, cần xác định priority 20 thắng hay các discount được kết hợp. Không nên để thứ tự file hoặc thứ tự hash map quyết định kết quả.

Một revision mới có thể thay đổi priority; semantic diff và test cần làm nổi bật thay đổi này.

## 25. Nhiều phiên bản cùng tồn tại

Trong một hệ thống lớn, nhiều phiên bản luật có thể hoạt động đồng thời:

- Tenant A dùng ruleset 4.2.
- Tenant B đang thử ruleset 4.3.
- Batch cũ cần replay bằng ruleset 4.1.
- Một sản phẩm có ngày hiệu lực khác sản phẩm khác.
- Một khu vực có phụ lục chính sách riêng.

Version resolver cần có precedence rõ giữa scope. Ví dụ, luật đặc thù tenant có thể ưu tiên luật toàn hệ thống, nhưng phải định nghĩa trường hợp tenant override không tồn tại hoặc không tương thích.

Không nên chỉ dựa vào “phiên bản mới nhất toàn cục” nếu có nhiều scope độc lập. Một mapping rõ như (tenant, product, environment, effectiveAt) -> ruleset version giúp giải thích lựa chọn.

## 26. Feature flag và thử nghiệm phiên bản

Feature flag có thể điều hướng một nhóm request sang ruleset version mới. Cần phân biệt:

- Feature flag chọn phiên bản luật.
- Effective date quyết định luật có hiệu lực nghiệp vụ.
- Approval quyết định phiên bản có được phép phát hành.
- Canary policy quyết định nhóm request nào nhận revision thử nghiệm.

Các yếu tố này có thể cùng tham gia resolver nhưng không nên gộp thành một trường trạng thái duy nhất.

Trong A/B test, cần cố định cohort assignment để cùng một khách hàng không liên tục chuyển giữa hai luật nếu thử nghiệm yêu cầu ổn định. Decision record cần lưu experiment ID, variant và ruleset version đã chọn.

## 27. Lưu trữ, manifest và lockfile

Một hệ thống có thể lưu revision trong repository, database hoặc artifact registry. Dù dùng nơi nào, cần bảo đảm nội dung và metadata có thể truy xuất lâu dài.

Manifest của ruleset đóng vai trò lockfile, cố định toàn bộ dependency:

~~~yaml
rulesetId: billing-policy
version: 6.1.0
engineVersion: 5.2.0
dslVersion: "3"
rules:
  - id: billing.base_fee
    revision: 8
    hash: "sha256:..."
  - id: billing.late_fee
    revision: 4
    hash: "sha256:..."
  - id: billing.tax
    revision: 6
    hash: "sha256:..."
~~~

Lockfile giúp:
- Build/release dùng đúng tập revision.
- Kiểm tra artifact không bị thay đổi.
- Replay quyết định.
- So sánh staging và production.
- Phát hiện dependency bị cập nhật ngoài ý muốn.

Một manifest được ký hoặc lưu trong kho bất biến có thể tăng khả năng tin cậy trong môi trường tuân thủ.

## 28. Audit và khả năng truy vết

Audit trail nên ghi nhận các sự kiện quản trị:

- Tạo revision.
- Thay đổi nội dung.
- Chạy validation/test.
- Gửi review.
- Phê duyệt hoặc từ chối.
- Lên lịch.
- Publish hoặc activate.
- Deprecate, retire hoặc archive.
- Rollback.
- Thay đổi resolver configuration.

Mỗi sự kiện nên có actor, timestamp, đối tượng, content hash, hành động và lý do. Nếu một revision bị sửa sau approval, audit phải thể hiện rõ approval nào đã bị vô hiệu.

Audit log cần chống sửa đổi trái phép và có retention policy. Việc lưu nội dung luật và log có thể có yêu cầu bảo mật khác nhau; quyền xem policy không nhất thiết giống quyền xem input quyết định chứa dữ liệu cá nhân.

## 29. Kiểm thử phiên bản luật

Mỗi revision mới nên được kiểm tra trước khi active. Các loại test thường gồm:

### 29.1. Syntax và static validation

- Grammar hợp lệ.
- Kiểu input/output tương thích.
- Tên và dependency được phân giải.
- Không có rule ID trùng.
- Không có dependency cycle nếu policy cấm.
- Effective interval và scope hợp lệ.

### 29.2. Unit tests cho luật

Kiểm tra điều kiện và kết quả ở các trường hợp đại diện, bao gồm biên của ngưỡng, null, thiếu dữ liệu và giá trị ngoài phạm vi.

Ví dụ:

~~~text
test "high value loan requires two approvers" {
    given application.amount = 150000000
    expect evaluate("credit.high_value_review") {
        approvers_required == 2
    }
}
~~~

### 29.3. Regression tests

Giữ lại các trường hợp đã từng gây lỗi. Chạy cùng fixture trên revision cũ và mới để xác định quyết định nào thay đổi.

### 29.4. Golden decision tests

Lưu cặp input/output mong đợi cùng ruleset version. Khi thay đổi luật, diff output cho biết tác động lên các ví dụ đã biết.

### 29.5. Boundary và temporal tests

Kiểm tra thời điểm ngay trước, tại và sau effectiveFrom/effectiveTo. Kiểm tra timezone, daylight saving time và khoảng giao nhau.

### 29.6. Differential testing

Chạy cùng input trên ruleset cũ và mới, sau đó phân loại khác biệt:
- Thay đổi dự kiến.
- Thay đổi ngoài ý muốn.
- Thay đổi do engine/runtime.
- Thay đổi do dữ liệu hoặc external fact.

### 29.7. Performance và load tests

Đo độ trễ, throughput, memory và số lần gọi external service. Một revision logic đúng nhưng làm tăng thời gian đánh giá vượt SLA vẫn cần được xem xét trước khi phát hành.

## 30. Kiểm thử tính tương đương và giải thích thay đổi

Không phải revision mới phải cho cùng kết quả với revision cũ. Mục tiêu test là xác nhận khác biệt đúng với ý định nghiệp vụ.

Có thể xây một report:

| Input case | Revision 6 | Revision 7 | Đánh giá |
|---|---|---|---|
| Amount 90M | One approver | One approver | Unchanged |
| Amount 120M | Two approvers | One approver | Expected change |
| Amount 150M | Two approvers | Two approvers | Unchanged |
| Missing income | Reject | Manual review | Review required |

Một report tốt cần gắn mỗi khác biệt với rule ID, điều kiện đã match và output thay đổi. Người review có thể xem trace thay vì chỉ nhìn tổng số kết quả khác nhau.

## 31. Triển khai và đồng bộ nhiều instance

Trong production, nhiều instance decision engine có thể chạy cùng lúc. Khi publish ruleset mới, cần tránh trạng thái một số instance dùng version mới, một số instance dùng version cũ ngoài kế hoạch.

Một số chiến lược:

- Publish immutable artifact vào registry trước.
- Kiểm tra tất cả dependency và hash.
- Cập nhật active pointer bằng thao tác nguyên tử.
- Instance tải ruleset snapshot rồi xác nhận đã sẵn sàng.
- Router chuyển traffic theo rollout policy.
- Theo dõi version đang chạy của từng instance.
- Chỉ retire version cũ khi không còn request hoặc replay cần nó.

Có thể giữ nhiều version trong memory để phục vụ request đã pin version. Với hệ thống có long-running workflow, quyết định có tiếp tục dùng ruleset tại thời điểm khởi tạo hay chuyển sang ruleset mới cần được quy định rõ.

## 32. API quản lý phiên bản luật

Một API quản trị có thể tách thao tác tạo revision, validate, approve, publish và resolve.

Ví dụ Java:

~~~java
record RuleRef(String ruleId, int revision) {}

record RulesetRef(String rulesetId, String version) {}

interface RuleVersionService {
    RuleRef createRevision(String ruleId, String source);
    ValidationReport validate(RuleRef revision);
    ApprovalResult approve(RuleRef revision, String approver);
    PublishResult publish(RulesetRef ruleset);
    ResolvedRuleset resolve(DecisionContext context);
}
~~~

Đây là interface khái niệm. Implementation cần kiểm soát authorization, optimistic concurrency, audit event, transaction và idempotency. Publish cùng một ruleset version hai lần không nên tạo hai bản phát hành khác nhau.

API resolve nên trả về resolved snapshot hoặc manifest cụ thể. Consumer cần biết nó thực thi revision nào, không chỉ nhận một object evaluator không có provenance.

## 33. Ví dụ Java: chọn phiên bản theo thời gian hiệu lực

Một mô hình đơn giản có thể biểu diễn khoảng hiệu lực:

~~~java
record RuleRevision(
    String ruleId,
    int revision,
    Instant effectiveFrom,
    Instant effectiveTo,
    RuleStatus status
) {
    boolean isEffectiveAt(Instant time) {
        return !time.isBefore(effectiveFrom)
            && (effectiveTo == null || time.isBefore(effectiveTo));
    }
}
~~~

Resolver có thể lọc các revision đã publish và có hiệu lực:

~~~java
RuleRevision resolve(
        List<RuleRevision> revisions,
        Instant businessTime) {

    List<RuleRevision> matches = revisions.stream()
        .filter(r -> r.status() == RuleStatus.PUBLISHED)
        .filter(r -> r.isEffectiveAt(businessTime))
        .toList();

    if (matches.size() != 1) {
        throw new IllegalStateException(
            "Expected exactly one effective rule revision");
    }

    return matches.getFirst();
}
~~~

Ví dụ này giả định một rule ID chỉ có đúng một revision active tại thời điểm đã chọn. Hệ thống thực tế có thể cần xét scope, tenant, product và priority. Nếu có nhiều match, cần áp dụng precedence đã công bố hoặc báo ambiguity.

## 34. Ví dụ quản lý thay đổi luật

Giả sử luật phí trễ hạn hiện tại:

~~~text
rule "billing.late_fee" {
    when invoice.days_overdue > 10
    then fee = invoice.balance * 0.01
}
~~~

Chính sách mới tăng phí lên 2% và thay ngưỡng thành 15 ngày:

~~~text
rule "billing.late_fee" {
    when invoice.days_overdue > 15
    then fee = invoice.balance * 0.02
}
~~~

Quy trình có thể là:

1. Tạo revision 2 từ revision 1.
2. Ghi lý do thay đổi và ngày hiệu lực.
3. Chạy syntax/type validation.
4. Chạy test với 10, 11, 15 và 16 ngày quá hạn.
5. So sánh decision output giữa revision 1 và 2.
6. Review semantic diff và phê duyệt.
7. Đưa revision 2 vào ruleset version mới.
8. Publish và lên lịch activation.
9. Theo dõi số quyết định và tổng phí sau khi active.
10. Nếu có vấn đề, chuyển active pointer về ruleset ổn định trước đó.

Quyết định tạo trước ngày hiệu lực vẫn có thể được replay bằng revision 1. Quyết định sau ngày hiệu lực dùng revision 2 theo business time và resolver policy.

## 35. Những lỗi thiết kế thường gặp

- Ghi đè nội dung revision đã phát hành.
- Dùng latest mà không lưu revision đã resolve.
- Version từng luật nhưng không cố định ruleset snapshot.
- Gộp DSL version, rule revision và engine version thành một con số.
- Không lưu effective date hoặc timezone.
- Cho phép khoảng hiệu lực chồng lấn mà không có precedence.
- Thay đổi output contract mà không kiểm tra consumer.
- Chỉ kiểm thử syntax mà không kiểm thử quyết định.
- Không ghi input/external facts cần thiết để replay.
- Cache theo rule ID mà không theo revision.
- Rollback luật nhưng không xử lý side effect đã phát sinh.
- Publish ruleset trước khi dependency được xác minh.
- Cho phép approval tồn tại sau khi nội dung đã thay đổi.
- Xóa revision cũ dù audit hoặc workflow dài hạn còn cần.
- Không theo dõi version thực tế đang chạy trên các instance.

Những lỗi này khiến version number tồn tại nhưng không mang lại khả năng tái lập hoặc kiểm soát thực sự.

## 36. Quy trình thiết kế và phát hành phiên bản luật

Một quy trình đầy đủ có thể gồm:

1. **Xác định rule identity:** tạo ID ổn định và namespace.
2. **Tạo revision bất biến:** mọi thay đổi nội dung tạo revision mới.
3. **Lưu metadata:** author, reason, DSL version, hash, scope và effective interval.
4. **Validate:** syntax, type, dependency và policy.
5. **Test:** unit, regression, boundary, temporal và performance.
6. **Tạo semantic diff:** mô tả thay đổi hành vi và contract.
7. **Review/approve:** áp dụng separation of duties nếu cần.
8. **Đóng gói ruleset:** pin các rule revision và dependency chính xác.
9. **Publish:** lưu artifact bất biến và manifest.
10. **Schedule/activate:** chọn thời điểm, scope và rollout strategy.
11. **Observe:** theo dõi kết quả, lỗi và version đang chạy.
12. **Rollback/deprecate:** chuyển version có kiểm soát khi cần.
13. **Retain/archive:** giữ lịch sử cho replay và audit.

## 37. Nguyên tắc thiết kế

- **Giữ rule ID ổn định:** ID biểu diễn danh tính logic, revision biểu diễn nội dung cụ thể.
- **Không sửa revision đã phát hành:** thay đổi tạo revision mới để bảo toàn lịch sử.
- **Version ruleset cùng các luật thành phần:** cố định đúng tổ hợp được thực thi.
- **Tách version của DSL, rule, schema và engine:** mỗi trục có vòng đời riêng.
- **Phân biệt approval với activation:** được duyệt không có nghĩa đã có hiệu lực.
- **Lưu valid time và transaction time khi cần:** hỗ trợ quyết định theo lịch sử nghiệp vụ.
- **Quy định resolver rõ ràng:** scope, effective time, priority và pinning không được mơ hồ.
- **Khóa dependency:** tránh luật thay đổi gián tiếp qua revision được resolve khác.
- **Kiểm tra compatibility:** xét input, output, runtime, dependency và hành vi.
- **Dùng semantic diff và regression tests:** review tác động nghiệp vụ, không chỉ text diff.
- **Gắn decision với provenance:** lưu ruleset, engine, input revision và context đã dùng.
- **Giữ evaluation deterministic khi cần replay:** inject clock và external facts có version.
- **Quản lý cache theo revision:** không dùng kết quả cũ cho luật mới.
- **Triển khai có kiểm soát:** scheduled, canary, shadow hoặc blue-green tùy mức rủi ro.
- **Rollback có hiểu biết về side effect:** quay lại luật cũ không tự hoàn tác nghiệp vụ.
- **Audit đầy đủ:** ghi ai tạo, duyệt, phát hành và thay đổi trạng thái.
- **Giữ lịch sử theo retention:** revision cũ có thể cần cho replay, kiểm toán và tranh chấp.

Phiên bản luật giúp hệ thống quyết định không chỉ biết kết quả là gì mà còn biết kết quả được tạo ra từ chính sách nào. Khi rule identity ổn định, revision bất biến, ruleset được pin, thời gian hiệu lực và dependency được giải quyết tường minh, cùng với kiểm thử, phê duyệt, audit và rollout có kiểm soát, các thay đổi nghiệp vụ có thể được phát hành mà vẫn giữ khả năng giải thích, tái hiện và quản trị quyết định trong suốt vòng đời hệ thống.
