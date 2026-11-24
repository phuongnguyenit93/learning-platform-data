# Critical action taxonomy

## 1. Danh mục hành động trọng yếu là gì?

**Critical action taxonomy** là hệ thống phân loại có quy tắc cho những hành động cần được kiểm soát và truy vết đặc biệt vì có thể làm thay đổi quyền lợi, quyền truy cập, dữ liệu nhạy cảm hoặc các cơ chế bảo vệ của hệ thống. Taxonomy giúp mọi thành phần gọi cùng một hành động bằng cùng một tên, hiểu cùng một ý nghĩa và ghi nhận đúng bằng chứng.

Ví dụ, một dòng access log như `POST /refunds/42 200` chưa cho biết yêu cầu hoàn tiền vừa được tạo, vừa được phê duyệt hay đã thực sự hoàn tiền. Nó cũng chưa cho biết ai khởi tạo, ai thực thi, phiên bản hồ sơ nào được duyệt và quy tắc nào đã cho phép thao tác.

Một taxonomy phù hợp có thể phân biệt:

```text
PAYMENT.REFUND.REQUEST
PAYMENT.REFUND.APPROVE
PAYMENT.REFUND.EXECUTE
```

Ba mã thể hiện ba hành động khác nhau, có quyền thực hiện, điều kiện trạng thái và bằng chứng khác nhau. Một response HTTP thành công ở bước phê duyệt không được diễn giải thành tiền đã được hoàn.

Trong chương **Auditability** của module bảo vệ logic nghiệp vụ, taxonomy là nền tảng để quan sát các bất biến: không bỏ qua phê duyệt, không sửa giá trái phép, không thao tác sai đối tượng và không tạo quyền lợi trùng khi retry. Nó cũng giúp thiết kế kiểm thử và điều tra có câu hỏi cụ thể, thay vì thu thập nhiều log nhưng không biết bằng chứng nào còn thiếu.

NIST SP 800-53, nhóm kiểm soát AU-2 và AU-3, đề cập việc chọn loại sự kiện cần ghi và nội dung bản ghi để hỗ trợ kiểm toán. Danh mục trong bài là ví dụ thiết kế cho một ứng dụng, không phải một bộ mã hành động do NIST quy định. Xem [NIST SP 800-53 Rev. 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf).

## 2. Phân biệt hành động, sự kiện, mức trọng yếu và log level

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Hành động nghiệp vụ | Điều chủ thể muốn thực hiện | Phê duyệt hoàn tiền |
| Sự kiện audit | Bản ghi về một điều đã được quan sát ở một giai đoạn | Lần thử bị từ chối do tự phê duyệt |
| Mức trọng yếu nghiệp vụ | Tác động và yêu cầu bằng chứng của hành động | Thay đổi quyền quản trị có mức trọng yếu cao |
| Kết quả | Điều đã xảy ra trong giai đoạn được ghi | Bị từ chối, đã commit, nhà cung cấp chưa xác nhận |
| Log level | Mức ưu tiên vận hành của bản ghi theo quy ước hệ thống | INFO, WARN, ERROR |
| Cảnh báo | Quy tắc hoặc tín hiệu cần con người hay hệ thống phản ứng | Nhiều lần cố tự phê duyệt cùng một hồ sơ |

Một hành động trọng yếu được thực hiện hợp lệ có thể có log level `INFO` theo quy ước. Một lỗi kết nối tạm thời có thể là `ERROR` nhưng không đồng nghĩa có thay đổi quyền lợi. Không dùng log level làm trường duy nhất để phân loại rủi ro nghiệp vụ.

Một hành động có thể sinh nhiều sự kiện: lần tiếp nhận, quyết định từ chối, thay đổi trạng thái đã commit hoặc kết quả hiệu ứng bên ngoài. Ngược lại, một request có thể thực hiện nhiều hành động. Việc chỉnh sửa một hồ sơ bằng `PATCH` có thể đồng thời đổi chủ sở hữu và tăng hạn mức; chỉ ghi `UPDATE_PROFILE` sẽ che mất hai thay đổi trọng yếu.

Taxonomy cần mô tả rõ ngữ nghĩa từng sự kiện để người đọc không cộng nhầm số lần thử thành số lần thay đổi, hoặc nhầm một công việc đã vào hàng đợi thành một hiệu ứng đã hoàn tất.

## 3. Chọn hành động dựa trên tài sản và bất biến

Nên bắt đầu từ tài sản và quy tắc cần bảo vệ, rồi xác định các hành động có thể thay đổi chúng.

| Tài sản hoặc quy tắc | Câu hỏi lựa chọn hành động trọng yếu |
|---|---|
| Tiền, giá, điểm thưởng, quota | Hành động có tạo, chuyển, giảm hoặc giải phóng quyền lợi không? |
| Quyền truy cập | Hành động có cấp quyền mới, đổi chủ sở hữu hoặc tạo khả năng đại diện không? |
| Trạng thái workflow | Hành động có chuyển bước, bỏ điều kiện hoặc thay người phê duyệt không? |
| Dữ liệu nhạy cảm | Hành động có đọc, xuất, chia sẻ, công bố hoặc xóa dữ liệu không? |
| Lựa chọn và quy tắc riêng tư | Hành động có thay đổi phạm vi được phép sử dụng dữ liệu không? |
| Cấu hình kiểm soát | Hành động có làm yếu xác thực, hạn mức, chính sách hoặc kiểm toán không? |
| Tính sẵn sàng | Hành động có thể tạo nhiều công việc hoặc ảnh hưởng diện rộng không? |
| Bằng chứng | Hành động có thể sửa, xóa hoặc làm gián đoạn nguồn truy vết không? |

Các yếu tố làm tăng mức trọng yếu gồm phạm vi nhiều đối tượng, giá trị lớn, khó đảo ngược, dữ liệu nhạy cảm hơn, quyền lực cao hơn hoặc khả năng làm suy yếu một kiểm soát khác.

Không giới hạn taxonomy ở thao tác của quản trị viên. Khách hàng đổi địa chỉ nhận tiền, rút lại sự đồng ý hoặc yêu cầu xuất dữ liệu cũng có thể thực hiện hành động trọng yếu. Một worker tự động thực thi hoàn tiền vẫn cần phân loại như hành động hoàn tiền dù không có người trực tiếp bấm nút lúc đó.

Nên dùng cả tình huống lạm dụng để tìm hành động còn thiếu:

- Nếu người gọi bỏ qua bước phê duyệt, cần thấy lần thực thi bị từ chối ở trạng thái nào.
- Nếu một nhân viên sửa giá sau phê duyệt, cần phân biệt sửa giá với cập nhật ghi chú.
- Nếu cùng yêu cầu tạo hai quyền lợi, cần liên kết các sự kiện với cùng lệnh nghiệp vụ.
- Nếu một người đổi chủ sở hữu rồi đọc dữ liệu, cần thấy cả thay đổi quan hệ và lần truy cập nhạy cảm sau đó.

## 4. Quy ước đặt mã và ranh giới ngữ nghĩa

Có thể dùng dạng ổn định:

```text
NHÓM.ĐỐI_TƯỢNG.HÀNH_ĐỘNG

ORDER.PRICE.OVERRIDE
PAYMENT.REFUND.APPROVE
IDENTITY.ROLE.GRANT
DATA.CUSTOMER.EXPORT_REQUEST
PRIVACY.CONSENT.WITHDRAW
GOVERNANCE.POLICY.PUBLISH
```

Mã cần do máy chủ xác định từ thao tác nghiệp vụ thực tế. Không tin `action`, `riskLevel` hoặc `auditRequired` do client gửi. Một route tên `updateNote` nhưng thực sự thay đổi giá vẫn phải bị ngăn vượt quyền và được phân loại theo thay đổi thực tế nếu có đường thao tác hợp lệ.

Các nguyên tắc đặt mã:

1. Dùng một nghĩa cho một mã, có mô tả đầu vào và hiệu ứng cụ thể.
2. Tránh mã quá chung như `UPDATE`, `ADMIN_ACTION` hoặc `SUCCESS`.
3. Tách những bước có quyền, trạng thái hoặc hậu quả khác nhau.
4. Giữ ID tài nguyên, người dùng và giá trị giao dịch trong trường dữ liệu, không nhúng vào mã hành động.
5. Dùng tập mã có kiểm soát để truy vấn, cảnh báo và metric không phát sinh số loại vô hạn.
6. Không đổi nghĩa mã cũ khi thay đổi giao diện hoặc đường dẫn API.

Ví dụ `PAYMENT.REFUND.APPROVE` có thể được định nghĩa là “ghi nhận phê duyệt một yêu cầu hoàn tiền theo đúng phiên bản đã xem xét”. Nó không bao gồm gửi lệnh cho nhà cung cấp. Nếu cần một thao tác phê duyệt ngoại lệ bỏ qua quy tắc thông thường, phải mô tả riêng điều kiện và bằng chứng của ngoại lệ; không che nó dưới cùng một thông điệp thành công chung.

Nếu một command thực hiện nhiều thay đổi trọng yếu, có thể ghi các hành động con có liên kết với cùng command và transaction, hoặc dùng một hợp đồng sự kiện kết hợp mô tả đầy đủ từng hiệu ứng. Phải tránh vừa đếm một sự kiện tổng vừa đếm các sự kiện con thành nhiều lần thực hiện cùng một quyền lợi.

## 5. Phân tầng mức trọng yếu theo ngữ cảnh

Bảng sau dùng các mức **C0–C3 tự định nghĩa cho bài học**. Tổ chức có thể dùng cách khác nếu ý nghĩa và yêu cầu bằng chứng rõ ràng.

| Mức | Ý nghĩa minh họa | Ví dụ | Yêu cầu phân loại |
|---|---|---|---|
| C0 | Hoạt động thông thường, phạm vi nhỏ và ít nhạy cảm theo ngữ cảnh | Xem danh mục công khai | Vẫn có thể cần log vận hành hoặc bảo vệ lưu lượng |
| C1 | Thay đổi nghiệp vụ cần truy vết, tác động giới hạn | Sửa tùy chọn hiển thị không nhạy cảm | Ghi chủ thể, đối tượng và thay đổi cần thiết |
| C2 | Tác động đáng kể đến quyền lợi, quyền hoặc dữ liệu | Phê duyệt hoàn tiền, cấp vai trò, xuất hồ sơ cá nhân | Bằng chứng nghiệp vụ và kết quả có cấu trúc |
| C3 | Phạm vi lớn, đặc quyền cao hoặc làm thay đổi cơ chế bảo vệ | Công bố chính sách toàn hệ thống, vô hiệu kiểm soát, xóa diện rộng | Kiểm soát và bằng chứng tăng cường theo chính sách |

Mức cuối cùng có thể là mức nền của mã hành động được nâng lên bởi ngữ cảnh đáng tin:

```text
criticality = classify(
  actionDefinition,
  affectedScope,
  dataClassification,
  privilegeChange,
  businessValue,
  reversibility,
  controlOverride
)
```

Các giá trị phải lấy từ hồ sơ, chính sách và thay đổi đã xác minh, không lấy nguyên số lượng hay mức nhạy cảm do client khai. Một thao tác bulk bị giới hạn mười phần tử cũng phải ghi nhận số thực tế, không dùng con số client khai để giảm mức.

Không dùng một tổng điểm tùy ý để cho phép yếu tố “giá trị nhỏ” bù trừ việc vô hiệu hóa kiểm toán. Có thể có điều kiện bắt buộc đặt mức sàn, chẳng hạn mọi thay đổi chính sách audit đều thuộc một lớp cần bằng chứng tăng cường.

Kết quả bị từ chối không tự làm hành động mất tính trọng yếu. Tuy nhiên, chính sách lưu bằng chứng của một lần thử bị chặn có thể khác chính sách của thay đổi đã commit. Cần diễn đạt sự khác biệt đó trong catalog thay vì bỏ cả loại sự kiện.

## 6. Catalog mẫu cho bảo vệ logic nghiệp vụ

Catalog dưới đây chỉ minh họa một phần ứng dụng bán hàng và quản trị. Mức cụ thể phải được duyệt theo hệ thống thực tế.

| Mã hành động | Bất biến hoặc rủi ro chính | Bằng chứng nghiệp vụ cần thiết |
|---|---|---|
| `ORDER.PRICE.OVERRIDE` | Không sửa giá ngoài thẩm quyền | Đơn, phiên bản, giá trị trước/sau được phép ghi, tiền tệ, chính sách ngoại lệ |
| `ORDER.DISCOUNT.APPLY` | Đúng điều kiện, không vượt quyền lợi | Đơn, campaign hoặc coupon tham chiếu an toàn, mức giảm đã tính, revision |
| `PAYMENT.REFUND.REQUEST` | Chỉ yêu cầu cho khoản thanh toán thuộc phạm vi | Người yêu cầu, khoản thanh toán tham chiếu, số tiền và trạng thái tạo |
| `PAYMENT.REFUND.APPROVE` | Không tự phê duyệt hoặc duyệt sai phiên bản | Người yêu cầu, người duyệt, phiên bản và quy tắc phân tách nhiệm vụ |
| `PAYMENT.REFUND.EXECUTE` | Không hoàn vượt hoặc hoàn trùng | Lệnh thực thi, phê duyệt được dùng, số tiền, trạng thái hiệu ứng bên ngoài |
| `IDENTITY.ROLE.GRANT` | Không leo thang quyền | Người cấp, người nhận, vai trò, phạm vi và chính sách cho phép |
| `IDENTITY.ACCOUNT.TRANSFER_OWNERSHIP` | Không chiếm quyền sở hữu | Quan hệ trước/sau, bằng chứng xác minh và revision |
| `DATA.CUSTOMER.EXPORT_REQUEST` | Chỉ xuất đúng chủ thể, mục đích và phạm vi | Người yêu cầu, tác vụ, projection, bộ lọc và đích nhận đã duyệt |
| `DATA.CUSTOMER.EXPORT_PUBLISH` | Không công bố file trái quyền | Job, artifact, phạm vi kết quả, kiểm tra quyền ở bước công bố |
| `DATA.ARTIFACT.DOWNLOAD` | Không lấy file qua đường bỏ kiểm tra | Chủ thể tải, artifact, quyết định quyền và lượng dữ liệu được phục vụ |
| `PRIVACY.CONSENT.GRANT` | Đúng nội dung và lựa chọn | Chủ thể, actor, định nghĩa, artifact, phạm vi và revision |
| `PRIVACY.CONSENT.WITHDRAW` | Không hồi sinh grant cũ | Phạm vi rút lại, revision và sự kiện liên quan |
| `GOVERNANCE.POLICY.PUBLISH` | Không bỏ qua phê duyệt hoặc mở quyền ngầm | Người soạn/duyệt, phiên bản, phạm vi hiệu lực và diff được kiểm soát |
| `SECURITY.LIMIT.OVERRIDE` | Không cấp quota hoặc đường bỏ kiểm soát trái quyền | Chủ thể, đối tượng, giới hạn trước/sau, lý do, hạn ngoại lệ |
| `AUDIT.RETENTION.CHANGE` | Không làm mất bằng chứng ngoài chính sách | Chính sách trước/sau, người duyệt và phạm vi dữ liệu ảnh hưởng |
| `AUDIT.RECORD.DELETE` | Không xóa bằng chứng tùy tiện | Công việc xóa hợp lệ, phạm vi, chính sách lưu giữ và kết quả |

Đọc dữ liệu nhạy cảm cũng cần được đưa vào catalog khi rủi ro yêu cầu; không chỉ những thao tác ghi mới quan trọng. Danh mục export phải bao phủ cả yêu cầu, tạo đầu ra và truy cập đầu ra nếu chúng là các ranh giới quyền khác nhau.

Không sao chép toàn bộ đơn, dữ liệu khách hàng hoặc token vào audit để đáp ứng cột “bằng chứng”. Catalog phải chỉ rõ trường tối thiểu và dữ liệu bị cấm ghi.

## 7. Hợp đồng cho từng hành động

Một mục catalog cần đủ cụ thể để đội phát triển có thể triển khai và đội kiểm thử có thể xác minh. Ví dụ sau là cấu hình minh họa nằm trong tài liệu:

```yaml
actionId: PAYMENT.REFUND.APPROVE
semanticVersion: 1
owner: payment-domain
description: Ghi nhận phê duyệt yêu cầu hoàn tiền theo phiên bản đã thẩm định
minimumCriticality: C2
targetType: refund-request
allowedActorKinds:
  - human-with-approval-authority
requiredDecisionContext:
  - policyVersion
  - requesterId
  - approverId
  - expectedResourceVersion
requiredBusinessEvidence:
  - refundId
  - paymentReference
  - approvedAmountMinor
  - currency
  - fromState
  - toState
captureRules:
  deniedDecision: protected-security-audit-path
  committedTransition: same-transaction-durable-audit-record
prohibitedData:
  - accessToken
  - fullPaymentInstrument
  - rawRequestBody
```

Hợp đồng còn cần mô tả những kết quả hợp lệ, mã lý do, thời điểm ghi, yêu cầu lưu giữ, đối soát và hành vi khi không ghi được bằng chứng bắt buộc. Các tên trong ví dụ không phải yêu cầu phải dùng YAML để triển khai catalog.

Một trường như `reason` cần được tách rõ:

- `reasonCode` do máy chủ xác định, ví dụ `SEPARATION_OF_DUTIES_VIOLATION`.
- `userJustification` là nội dung người dùng cung cấp, có độ dài, quyền xem và cách xử lý dữ liệu riêng.

Việc có một lý do tự do không chứng minh người dùng được phép vượt quy tắc. Catalog chỉ mô tả bằng chứng; cơ chế phân quyền và kiểm tra workflow vẫn phải thực thi trước hiệu ứng.

## 8. Biểu diễn sự kiện để không đánh đồng ý định và hiệu ứng

Catalog định nghĩa **loại hành động**; mỗi bản ghi audit là một **lần quan sát cụ thể** của loại đó. Nên có một phần dữ liệu chung và phần bằng chứng riêng theo hành động. Ví dụ dưới đây là hợp đồng do bài học đề xuất, không phải schema tiêu chuẩn:

```json
{
  "schemaVersion": 1,
  "actionId": "PAYMENT.REFUND.APPROVE",
  "actionSemanticVersion": 1,
  "eventId": "evt-approval-104",
  "commandId": "cmd-approval-61",
  "attemptId": "attempt-http-92",
  "correlationId": "refund-flow-42",
  "occurredAt": "2026-11-22T02:15:00Z",
  "producer": "refund-service",
  "tenantId": "tenant-a",
  "initiator": { "kind": "USER", "id": "user-18" },
  "executor": { "kind": "SERVICE", "id": "refund-service" },
  "target": { "type": "refund-request", "id": "refund-42" },
  "criticality": "C2",
  "phase": "LOCAL_COMMIT",
  "outcome": "COMMITTED",
  "reasonCode": "APPROVAL_RECORDED",
  "policyVersion": "refund-policy-v7",
  "evidence": {
    "requesterId": "user-11",
    "approverId": "user-18",
    "expectedResourceVersion": 6,
    "resourceVersionAfter": 7,
    "fromState": "PENDING_APPROVAL",
    "toState": "APPROVED",
    "approvedAmountMinor": 250000,
    "currency": "VND"
  }
}
```

`approvedAmountMinor` là số nguyên theo đơn vị nhỏ nhất đã thống nhất cho tiền tệ; trong ví dụ VND này, `250000` biểu diễn 250.000 đồng. Không dùng tên trường giống nhau cho giá trị tính theo đồng và giá trị tính theo đơn vị khác. Đây là bằng chứng của việc phê duyệt trong cơ sở dữ liệu, chưa phải xác nhận nhà cung cấp đã hoàn tiền.

| Nhóm trường | Điều cần quy định trong catalog |
|---|---|
| Chủ thể | Ai khởi tạo, ai thực thi, có đại diện hoặc ủy quyền cho ai không |
| Đối tượng | Loại, định danh và tenant đáng tin cậy; không chỉ có URL từ client |
| Liên kết | Event, command, lần thử và luồng nghiệp vụ liên hệ với nhau thế nào |
| Kết quả | Giai đoạn được quan sát và kết quả thuộc giai đoạn đó |
| Quyết định | Phiên bản chính sách, mã lý do và bằng chứng điều kiện nghiệp vụ |
| Phiên bản | Phiên bản schema, ngữ nghĩa hành động và phiên bản đối tượng liên quan |

Chủ thể trong audit phải lấy từ ngữ cảnh xác thực và ủy quyền đã kiểm tra. Worker không được gán khách hàng là người trực tiếp thực thi chỉ vì command chứa `userId` của khách hàng. Với tác vụ được ủy quyền, cần giữ cả người khởi tạo, danh tính dịch vụ thực thi và tham chiếu ủy quyền đã xác minh khi có.

Có thể quy định các cặp `phase`/`outcome` như sau. Đây là tập giá trị minh họa; mỗi hành động chỉ chấp nhận những cặp phù hợp với ngữ nghĩa của nó.

| Giai đoạn | Kết quả minh họa | Điều bản ghi khẳng định |
|---|---|---|
| `DECISION` | `DENIED` | Một lần thử bị chặn bởi kiểm soát cụ thể |
| `DECISION` | `ALLOWED` | Kiểm tra đã cho phép ở thời điểm quyết định; chưa chứng minh commit |
| `LOCAL_COMMIT` | `COMMITTED` | Thay đổi cục bộ và bằng chứng tương ứng đã commit |
| `REPLAY` | `REPLAYED` | Trả lại kết quả command cũ; không tạo thêm thay đổi nghiệp vụ |
| `EXTERNAL_EFFECT` | `CONFIRMED` | Có bằng chứng nhà cung cấp xác nhận hiệu ứng theo hợp đồng tích hợp |
| `EXTERNAL_EFFECT` | `UNKNOWN` | Chưa đủ bằng chứng kết luận hiệu ứng bên ngoài đã xảy ra hay chưa |

HTTP timeout sau commit không biến hành động đã commit thành thất bại nghiệp vụ. Ngược lại, đã gửi lệnh ra mạng không đủ để ghi `CONFIRMED`. Catalog cần nói rõ bằng chứng nào cho phép chuyển từ chưa rõ kết quả sang đã xác nhận.

`occurredAt` cũng cần có nghĩa cụ thể. Nếu nó là thời điểm tạo bản ghi trong transaction, không gọi đó là thời điểm commit chính xác. Có thể bổ sung thời điểm nhận vào kho audit để phân biệt trễ truyền. Trong cùng đối tượng, dùng phiên bản trạng thái và liên kết nhân quả để hỗ trợ dựng lại thứ tự; không dựa duy nhất vào đồng hồ giữa các dịch vụ.

OWASP khuyến nghị log cung cấp đủ thông tin về thời gian, nơi phát sinh, chủ thể và sự kiện, đồng thời dùng định danh tương tác để liên kết các bản ghi. OWASP cũng lưu ý loại bỏ dữ liệu bí mật và xử lý đầu vào để tránh log injection. Xem [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-attributes). Schema trong ví dụ là một lựa chọn thiết kế nhằm phục vụ các câu hỏi nghiệp vụ cụ thể của bài.

### Ghi ít dữ liệu nhưng đủ bằng chứng

- Định nghĩa allowlist cho `evidence` của từng `actionId`; không serialize toàn bộ request hay entity.
- Giới hạn độ dài và mã hóa đúng định dạng đối với lý do do người dùng nhập. Chuỗi chứa xuống dòng không được trở thành một bản ghi audit giả.
- Không ghi access token, mật khẩu, cookie phiên hoặc khóa bí mật; không dùng việc băm một bí mật làm lý do để thu thập nó tùy tiện.
- Với lần thử truy cập đối tượng ngoài tenant, có thể ghi định danh mục tiêu được yêu cầu dưới dạng đã kiểm soát, cùng mã từ chối. Không đọc rồi sao chép dữ liệu đối tượng bị cấm chỉ để làm phong phú audit.
- Giá trước/sau, số tiền và định danh cá nhân chỉ được ghi theo hợp đồng dữ liệu và quyền truy cập kho audit. Một danh mục hành động tốt vẫn cần chính sách bảo vệ bằng chứng.

## 9. Gắn taxonomy với transaction, state machine và idempotency

Taxonomy không tự ngăn được lạm dụng. Giá trị của nó là làm rõ kiểm soát nào phải chạy và bằng chứng nào phải tồn tại khi một hành động đi qua ranh giới nghiệp vụ.

### 9.1. Đặt điểm ghi tại nơi hiểu quyết định nghiệp vụ

Nếu chỉ ghi ở HTTP filter, hệ thống thường biết route và mã phản hồi nhưng không biết phiên bản hồ sơ, số tiền được duyệt hay bất biến đã chặn thao tác. Nếu chỉ ghi ở giao diện, một API hoặc worker khác có thể bỏ qua hoàn toàn điểm ghi.

Nên phát sinh bằng chứng trong luồng xử lý nghiệp vụ có đủ ngữ cảnh đáng tin. Các đường vào HTTP, hàng đợi, tác vụ định kỳ và công cụ quản trị cần tuân theo cùng hợp đồng hành động, dù cơ chế tiếp nhận khác nhau. Không cho phép một endpoint cập nhật trạng thái tổng quát đi vòng qua command phê duyệt và điểm ghi tương ứng.

### 9.2. Lưu bằng chứng thành công cùng thay đổi cục bộ

Với hành động yêu cầu bằng chứng bền vững, một phương án là ghi trạng thái mới và bản ghi audit trong cùng transaction cơ sở dữ liệu. Nếu cần gửi tiếp sang kho audit tập trung, có thể thêm outbox trong cùng transaction:

```text
Trong một transaction:
  kiểm tra quyền trên đúng đối tượng và tenant
  kiểm tra trạng thái, phiên bản và bất biến
  cập nhật trạng thái với cơ chế chống ghi đè đồng thời
  ghi bằng chứng audit bền vững
  ghi kết quả command phục vụ idempotency
  ghi outbox tham chiếu cùng eventId nếu cần chuyển tiếp
COMMIT

Sau commit:
  relay chuyển sự kiện từ outbox sang kho audit
  consumer nhận lại cùng eventId thì xử lý trùng theo hợp đồng
```

Không ghi thông điệp `COMMITTED` vào một hệ thống log độc lập rồi mới thử commit cơ sở dữ liệu: transaction vẫn có thể rollback. Cũng không chỉ gọi logger sau commit rồi mặc định đã có bằng chứng bền vững: tiến trình có thể dừng giữa hai bước.

Outbox giúp thu hẹp khoảng trống giữa commit cục bộ và việc chuyển tiếp; nó không tạo transaction nguyên tử với cổng thanh toán. Relay có thể gửi lại cùng sự kiện, nên consumer phải phân biệt bản giao lại với một hành động mới. Kho audit còn cần phân quyền, lưu giữ và bảo vệ tính toàn vẹn; có một bảng audit chưa đồng nghĩa bằng chứng không thể bị sửa.

Nếu việc ghi bằng chứng bắt buộc trong transaction thất bại, hành động đó phải rollback theo chính sách đã chọn. Nếu chỉ đích tập trung tạm thời mất kết nối nhưng bản ghi cục bộ và outbox vẫn bền vững, hệ thống có thể tiếp tục theo chính sách và giám sát backlog. Khi bộ đệm bền vững đầy hoặc quá hạn cho phép, cần hành vi suy giảm được định nghĩa trước cho từng nhóm hành động.

### 9.3. Giữ bằng chứng từ chối ngoài transaction đã rollback

Một lần cố tự phê duyệt vẫn đáng ghi dù không có trạng thái nào thay đổi. Nếu audit từ chối nằm trong chính transaction bị rollback vì ngoại lệ, bằng chứng có thể mất theo transaction.

Cần một đường ghi phù hợp cho quyết định từ chối, chẳng hạn kênh security audit bền vững riêng hoặc bước ghi sau khi transaction nghiệp vụ đã kết thúc. Không để transaction audit độc lập chờ các khóa mà transaction lỗi đang giữ. Catalog phải quy định dữ liệu tối thiểu, xử lý khi kênh này lỗi và cơ chế phát hiện thiếu bằng chứng.

Dù ghi audit thất bại, quyết định từ chối vẫn phải giữ nguyên. Không chuyển một hành động trái quyền thành được phép để tránh lỗi logging. Đồng thời, giới hạn kích thước bản ghi, bảo vệ dung lượng và cảnh báo lưu lượng bất thường để kẻ tấn công không dùng hàng loạt yêu cầu bị từ chối làm cạn kho audit.

### 9.4. Phân biệt định danh để hiểu yêu cầu trùng

| Định danh | Phạm vi trong ví dụ |
|---|---|
| `eventId` | Một sự kiện logic; relay gửi lại vẫn giữ nguyên ID này |
| `commandId` | Một lệnh nghiệp vụ đã được nhận diện bền vững; nhiều lần retry có thể dùng cùng lệnh |
| `attemptId` | Một lần gọi hoặc một lần xử lý cụ thể; retry có ID mới |
| `correlationId` | Luồng lớn hơn, có thể gồm tạo yêu cầu, phê duyệt và thực thi |

Khóa idempotency từ client phải được ràng buộc vào phạm vi phù hợp, ví dụ tenant, chủ thể, loại thao tác và dấu vân tay nội dung nghiệp vụ đã chuẩn hóa. Cùng khóa nhưng khác nội dung phải được xử lý là xung đột theo hợp đồng. Không ghi nguyên khóa nếu nó có thể chứa dữ liệu nhạy cảm; `commandId` nội bộ thường đủ cho liên kết audit.

Trước khi trả lại kết quả cũ, vẫn phải xác thực và kiểm tra quyền truy cập hiện tại đối với kết quả đó. Biết một khóa không được trở thành cách đọc hồ sơ của người khác. Ngoài idempotency key, bất biến như không hoàn vượt số tiền đã thu vẫn phải được thực thi: người gọi có thể gửi nhiều khóa khác nhau.

Ví dụ, lần thử A phê duyệt thành công, nhưng response bị mất. Lần thử B gửi lại cùng lệnh hợp lệ nhận kết quả đã lưu. Audit có một sự kiện `LOCAL_COMMIT/COMMITTED` và có thể có thêm sự kiện `REPLAY/REPLAYED` theo catalog, chứ không có hai lần phê duyệt mới. Số lần gọi có thể là hai, số chuyển trạng thái đã commit vẫn là một.

## 10. Ví dụ xử lý phê duyệt theo catalog

Đoạn dưới là **mã giả theo cú pháp Java**, nhằm minh họa vị trí kiểm soát và tạo bằng chứng. Các API như `transaction.run` hoặc `commands.claimOrReplay` là tên minh họa, không phải thư viện có thể sao chép để chạy ngay.

```java
ApprovalResult approve(ApproveRefund cmd, TrustedContext ctx) {
    try {
        return transaction.run(() -> {
            Refund refund = refunds.lockInTenant(ctx.tenantId(), cmd.refundId());

            // Chạy cả khi có khả năng trả kết quả cũ.
            authorization.requireCanApprove(ctx.actor(), refund);

            // Phải có lưu trữ, unique constraint và xử lý cạnh tranh thực sự.
            // Hàm minh họa ràng buộc khóa với scope + fingerprint của lệnh.
            CommandSlot slot = commands.claimOrReplay(
                ctx.tenantId(), ctx.actor().id(),
                "PAYMENT.REFUND.APPROVE", cmd.idempotencyKey(),
                canonicalFingerprint(cmd)
            );
            if (slot.isReplay()) {
                return slot.authorizedStoredResult();
            }

            RefundPolicy policy = policies.currentFor(refund);
            refund.requireState(PENDING_APPROVAL);
            refund.requireVersion(cmd.expectedVersion());
            policy.requireDifferentRequesterAndApprover(
                refund.requesterId(), ctx.actor().id()
            );
            policy.requireAmountWithinApprovalAuthority(ctx.actor(), refund);

            ApprovalEvidence evidence = evidenceFactory.forApproval(
                ctx, refund, policy.version(), slot.commandId()
            );
            refund.approve(ctx.actor().id());
            refunds.saveWithVersionCheck(refund);

            AuditEvent event = catalog.committedApproval(
                evidence, refund.version(), ctx.attemptId()
            );
            auditRecords.insert(event);       // cùng transaction
            auditOutbox.insert(event);        // cùng eventId; relay có thể retry

            ApprovalResult result = ApprovalResult.from(refund);
            commands.complete(slot, result);  // cùng transaction
            return result;
        });
    } catch (BusinessRejection rejected) {
        // transaction.run đã kết thúc rollback trước khi tới đây.
        // Không bắt mọi lỗi rồi gán thành "bị từ chối nghiệp vụ".
        denialAudit.recordWithDefinedFailurePolicy(
            catalog.deniedApproval(ctx, cmd.refundId(), rejected.reasonCode())
        );
        throw rejected;
    }
}
```

Ví dụ giả định lớp nghiệp vụ phân loại rõ `BusinessRejection`, lỗi tranh chấp và lỗi hạ tầng. Nếu commit ném lỗi kết nối khiến kết quả chưa xác định, không được tự ghi rằng chắc chắn không có thay đổi. Cần tra cứu kết quả command hoặc đối soát trước khi kết luận.

`lockInTenant` chỉ là một cách minh họa việc tải đúng đối tượng và tuần tự hóa cập nhật. Thiết kế thực tế có thể dùng khóa hoặc cập nhật có điều kiện theo phiên bản, nhưng phải xử lý được cạnh tranh. Trong ví dụ, thay đổi chính sách và bằng chứng của quyết định cũng cần có semantics phiên bản rõ ràng; tên hàm `currentFor` tự nó không giải quyết các cuộc đua khi công bố chính sách.

Các điểm taxonomy giúp thể hiện rõ trong luồng này:

1. Mã hành động được chọn ở máy chủ và thuộc catalog, không lấy từ request.
2. Quyền theo đối tượng và tenant được kiểm tra trước khi đọc kết quả idempotency trả cho người gọi.
3. Bằng chứng dùng số tiền và trạng thái từ hồ sơ đáng tin, cùng chính sách đã áp dụng.
4. Tự phê duyệt hoặc phiên bản cũ tạo kết quả từ chối cụ thể; không gộp vào `UPDATE_FAILED`.
5. Sự kiện phê duyệt thành công chỉ tồn tại cùng commit của thay đổi và kết quả command.
6. Không có lời gọi hoàn tiền bên ngoài trong hành động phê duyệt; đó là hành động `PAYMENT.REFUND.EXECUTE` với hợp đồng riêng.

Nếu cần audit cho replay, phải thêm sự kiện thuộc giai đoạn `REPLAY` ở một đường ghi được định nghĩa rõ. Không tạo lại sự kiện `COMMITTED` chỉ vì hàm đang trả về một kết quả thành công đã lưu.

## 11. Từ taxonomy đến tiêu chí kiểm thử

Mỗi hành động trong catalog nên có bộ tiêu chí về **quyết định, hiệu ứng và bằng chứng**. Chỉ kiểm tra API trả `403` hoặc `200` không đủ để chứng minh taxonomy đã được triển khai đúng.

| Tình huống | Quyết định và hiệu ứng mong đợi | Bằng chứng cần kiểm tra |
|---|---|---|
| Duyệt yêu cầu hợp lệ | Chuyển đúng phiên bản sang `APPROVED` | Đúng action, chủ thể, số tiền, phiên bản và `LOCAL_COMMIT/COMMITTED` |
| Người yêu cầu tự phê duyệt | Từ chối, không chuyển trạng thái | Mã lý do phân tách nhiệm vụ; không có commit event |
| Người có vai trò nhưng sai tenant hoặc ngoài phạm vi đối tượng | Từ chối trước thay đổi | Audit không sao chép dữ liệu bị cấm của tenant khác |
| Gọi thực thi khi chưa được duyệt | Không tạo lệnh hoàn tiền hợp lệ | Action thực thi và mã lý do sai trạng thái, không giả thành lỗi phê duyệt |
| Sửa số tiền sau lúc đã được thẩm định | Không dùng phê duyệt cũ cho nội dung mới | Liên kết phiên bản và quyết định kiểm soát tương ứng |
| Hai người duyệt đồng thời cùng phiên bản | Chỉ một chuyển trạng thái thắng | Một commit event; kết quả lần còn lại được phân loại đúng |
| Retry sau khi response mất | Trả kết quả command cũ nếu còn quyền | Không thêm commit event; replay event nếu catalog yêu cầu |
| Cùng idempotency key nhưng đổi số tiền hoặc đối tượng | Từ chối xung đột nội dung | Mã lý do xung đột, không tiết lộ kết quả thuộc scope khác |
| Lỗi ghi bản audit bắt buộc trong transaction | Rollback thay đổi cục bộ | Không báo thành công; có tín hiệu lỗi hạ tầng phù hợp |
| Relay gửi lại cùng outbox event | Không tính thành hành động nghiệp vụ mới | Kho nhận nhận diện cùng `eventId` |
| Nhà cung cấp timeout khi thực thi | Giữ kết quả chưa xác định để đối soát | Không ghi xác nhận hoàn tiền khi chưa đủ bằng chứng |
| Lý do chứa token hoặc chuỗi tạo dòng giả | Không rò bí mật hoặc chèn bản ghi | Dữ liệu được lọc, giới hạn và mã hóa đúng schema |
| Thao tác từ job hoặc công cụ quản trị | Vẫn áp dụng hợp đồng tương ứng | Có danh tính thực thi và nguồn khởi tạo đúng ngữ cảnh |

Đây là các tiêu chí thiết kế cho bài học. Khi triển khai trong hệ thống, nên kiểm tra trên biên transaction và kho dữ liệu thật phù hợp với phạm vi kiểm thử; một mock logger chỉ chứng minh hàm đã được gọi, chưa chứng minh audit và thay đổi commit cùng nhau.

Một truy vấn điều tra cũng có thể là tiêu chí chấp nhận: với `refund-42`, người vận hành có dựng lại được ai yêu cầu, ai phê duyệt phiên bản nào, command nào thực thi và bằng chứng nào xác nhận hiệu ứng bên ngoài hay không? Nếu cần đoán từ một chuỗi thông điệp tự do, catalog hoặc schema vẫn thiếu thông tin.

## 12. Quản lý thay đổi của taxonomy

Taxonomy cần được quản lý như hợp đồng giữa ứng dụng, kho audit, đội phát hiện sự cố và người điều tra. Mỗi mục nên có người chịu trách nhiệm nghiệp vụ, người chịu trách nhiệm triển khai, phạm vi dữ liệu và các bên tiêu thụ đã biết.

Phân biệt hai loại phiên bản:

- **Phiên bản schema** thay đổi khi cấu trúc hoặc cách biểu diễn bản ghi thay đổi. Thêm trường tùy chọn có thể tương thích với consumer hiện có; đổi kiểu trường có thể không tương thích.
- **Phiên bản ngữ nghĩa hành động** thay đổi khi nghĩa nghiệp vụ thay đổi. Nếu `APPROVE` trước đây chỉ phê duyệt nhưng nay còn thực thi hoàn tiền, không được âm thầm giữ nguyên nghĩa cũ. Cần tách mã hoặc chuyển đổi hợp đồng có công bố rõ.

Khi thêm đường thao tác mới, có thể đi theo các bước:

1. Xác định tài sản, bất biến và hiệu ứng của command; kiểm tra mã hiện có có cùng nghĩa hay không.
2. Chọn mã, mức trọng yếu nền và các điều kiện nâng mức từ ngữ cảnh đáng tin.
3. Khai báo quyền, trạng thái, kết quả, trường bằng chứng, dữ liệu cấm và hành vi khi không ghi được.
4. Xác định điểm commit, đường audit từ chối, idempotency và cách liên kết các hiệu ứng bên ngoài nếu có.
5. Cập nhật producer, consumer, quy tắc truy vấn và tiêu chí kiểm thử trước khi đưa đường mới vào sử dụng.

Không viết lại lịch sử chỉ để các bản ghi cũ mang tên mới. Nếu cần chuẩn hóa cho truy vấn, giữ bản gốc và thêm ánh xạ có phiên bản để người điều tra biết bản ghi ban đầu có nghĩa gì.

Mã hành động chưa được đăng ký, trường bắt buộc thiếu hoặc cặp giai đoạn/kết quả không hợp lệ phải được phát hiện. Với thay đổi bắt buộc có audit, đường xử lý cần kiểm tra hợp đồng trước hiệu ứng hoặc rollback nếu không lưu được bằng chứng hợp lệ; không âm thầm biến hành động đó thành `OTHER` rồi bỏ các điều kiện kiểm soát.

Các tín hiệu vận hành có ích gồm số mã chưa biết, bản ghi bị từ chối bởi schema, độ trễ outbox, thiếu liên kết command, thiếu bằng chứng của thay đổi đã commit và số lần replay. Phải giám sát cả sức khỏe đường audit. Không mặc định im lặng đồng nghĩa không có hành động trọng yếu.

Đối soát nên dựa trên phạm vi có thể xác minh, ví dụ mọi bản ghi phê duyệt đã commit trong sổ nghiệp vụ đều có bằng chứng theo command và phiên bản tương ứng. So sánh hai tổng số log bằng nhau không chứng minh từng đối tượng đều đủ bằng chứng.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa theo taxonomy |
|---|---|---|
| Dùng tên endpoint làm toàn bộ phân loại | Đổi route làm đứt truy vấn; nhiều hiệu ứng bị gộp | Dùng mã theo hành động nghiệp vụ ổn định |
| Chỉ ghi thao tác của admin | Bỏ sót hành động trọng yếu của khách hàng và worker | Chọn theo tài sản, quyền lợi và bất biến |
| Dùng `SUCCESS` cho mọi giai đoạn | Nhầm nhận yêu cầu với commit hoặc hiệu ứng bên ngoài | Khai báo riêng giai đoạn và kết quả có nghĩa rõ |
| Cho client chọn mức trọng yếu hoặc tắt audit | Người gọi có thể che dấu hành động rủi ro | Phân loại từ phía máy chủ với ngữ cảnh đã kiểm tra |
| Đếm mọi event như một lần thực hiện | Retry và giao lại outbox làm tăng giả số quyền lợi | Quy định đơn vị đếm, command và event phù hợp |
| Ghi audit trước commit vào logger độc lập | Có bằng chứng thành công cho thay đổi đã rollback | Gắn bằng chứng thành công với commit bền vững |
| Chỉ ghi sau commit vào logger thông thường | Dừng tiến trình có thể tạo khoảng trống bằng chứng | Dùng bản ghi cùng transaction và đường chuyển tiếp có phục hồi |
| Lưu toàn bộ request để tiện điều tra | Rò bí mật, dữ liệu thừa và nguy cơ log injection | Allowlist bằng chứng, giới hạn dữ liệu và quyền đọc |
| Coi sự hiện diện của audit là kiểm soát quyền | Có log của một hành động trái phép nhưng thiệt hại đã xảy ra | Thực thi quyền, trạng thái và bất biến trước hiệu ứng |

Một mục taxonomy có thể coi là đủ rõ để bắt đầu triển khai khi người đọc trả lời được: hành động thay đổi điều gì; ai được làm trên đối tượng nào; điều kiện trạng thái và phiên bản là gì; cần ghi bằng chứng ở giai đoạn nào; retry được hiểu thế nào; và điều tra có phân biệt được ý định, quyết định, commit cùng hiệu ứng bên ngoài hay không.
