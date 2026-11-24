# Audit event integrity — Tính toàn vẹn của sự kiện audit trong khôi phục tài khoản

## 1. Tính toàn vẹn cần bảo vệ điều gì?

**Audit event integrity** là khả năng bảo vệ và kiểm chứng rằng những sự kiện audit trong một phạm vi xác định không bị thay đổi trái phép, tráo đối tượng, chèn giả, xóa hoặc sắp xếp lại mà không được phát hiện theo mô hình tin cậy đã chọn.

Trong khôi phục tài khoản, audit có thể ghi nhận việc tạo request, kiểm tra token, xem xét bằng chứng, cấp quyền đặt lại mật khẩu, thay MFA, đăng ký passkey hoặc thu hồi session. Nếu lịch sử bị sửa từ “bị từ chối” thành “đã cho phép”, hoặc mất sự kiện nhân viên thay yếu tố xác thực, quá trình điều tra có thể đi tới kết luận sai.

Một bản ghi còn nguyên byte không tự chứng minh nội dung của nó đúng. Cần tách các thuộc tính:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Toàn vẹn nội dung | Nội dung được bảo vệ có bị thay đổi sau mốc tin cậy không? |
| Xác thực nguồn | Thành phần nào được xác nhận đã phát sinh hoặc ký dữ liệu? |
| Tính đầy đủ trong phạm vi | Có đủ những sự kiện mà phạm vi kiểm chứng yêu cầu không? |
| Thứ tự | Các sự kiện trong một stream có còn đúng thứ tự đã được xác lập không? |
| Độ mới | Lịch sử được xem có bị thay bằng một bản cũ từng hợp lệ không? |
| Đúng ngữ nghĩa nghiệp vụ | Sự kiện có thực sự phản ánh thao tác và kết quả giao dịch không? |
| Tính bí mật | Ai có quyền đọc dữ liệu audit? |

Băm hoặc ký hỗ trợ một số thuộc tính trên, không giải quyết tất cả. Một dịch vụ đã bị chiếm quyền có thể ký một lời khai sai; một bản sao cũ có chữ ký hợp lệ vẫn có thể thiếu hoạt động mới nhất.

Bài này trình bày một thiết kế minh họa cho audit của khôi phục tài khoản. Các trường, stream và cách niêm phong bên dưới cần được điều chỉnh theo kiến trúc thực tế; chúng không phải giao thức mật mã mới để tự triển khai thay cho thư viện và cơ chế đã được kiểm chứng.

## 2. Bắt đầu từ mô hình đe dọa và ranh giới tin cậy

Trước khi chọn hash hay chữ ký, cần xác định đối thủ có thể điều khiển thành phần nào:

- Người chưa đăng nhập có thể gửi đầu vào để giả nội dung log hoặc gây quá tải.
- Một tài khoản ứng dụng có thể bị lộ và được dùng để chèn sự kiện không hợp lệ.
- Người có quyền ghi cơ sở dữ liệu có thể sửa cả payload và cột hash.
- Quản trị viên kho lưu trữ có thể xóa dữ liệu, thay bản sao hoặc thay đổi cấu hình giữ liệu.
- Một dịch vụ phát sinh sự kiện có thể bị chiếm quyền trước khi dữ liệu tới collector.
- Một người điều tra có thể chỉ nhận một phần lịch sử rồi nhầm đó là toàn bộ lịch sử.

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) đề cập bảo vệ log khi truyền và lưu, phát hiện sửa hoặc xóa trái phép, cùng giám sát việc logging bị dừng. Trong bài này, những yêu cầu đó được cụ thể hóa thành nhiều lớp bảo vệ có ranh giới riêng.

Một cách phân chia trách nhiệm:

| Thành phần | Trách nhiệm | Quyền nên hạn chế |
| --- | --- | --- |
| Recovery Service | Tạo sự kiện có ngữ nghĩa đúng từ kết quả xử lý | Không tự sửa lịch sử đã tiếp nhận |
| Collector | Xác thực nguồn, kiểm tra hợp đồng và tiếp nhận | Không tự cấp quyền khôi phục |
| Kho audit | Lưu dữ liệu và bằng chứng toàn vẹn | Không để writer thường xuyên có quyền xóa lịch sử |
| Dịch vụ niêm phong | Ký phạm vi dữ liệu đã xác định | Không dùng khóa ký chung với tài khoản quản trị kho |
| Nơi giữ điểm neo độc lập | Lưu bằng chứng về phạm vi đã tồn tại | Không cùng chịu mọi quyền sửa với kho chính |
| Verifier | Kiểm chứng dữ liệu và nêu giới hạn kết luận | Không cần nắm khóa ký bí mật |

Nếu cùng một principal có thể sửa dữ liệu, tạo lại chuỗi hash, ký lại điểm cuối và thay bản sao đối chiếu, cơ chế đó không bảo vệ được trước chính principal ấy.

## 3. Sự kiện phải đúng trước khi được niêm phong

Mật mã chỉ bảo vệ dữ liệu đã được đưa vào cơ chế bảo vệ. Vì vậy, bước đầu tiên là tạo đúng sự kiện.

Ví dụ, một sự kiện PASSWORD_REPLACEMENT_COMPLETED phải tương ứng với việc thay mật khẩu đã commit thành công. Không ghi “hoàn tất” chỉ vì code đã đi tới trước lời gọi cập nhật, hoặc nhà cung cấp đã nhận một công việc xử lý.

Một giao dịch minh họa khi nghiệp vụ và audit cục bộ cùng cơ sở dữ liệu:

~~~text
BEGIN
  Kiểm tra quyền tác vụ, thời hạn, scope và trạng thái request
  Thực hiện thay đổi credential hoặc trạng thái được bảo vệ
  Tiêu thụ quyền dùng một lần theo cơ chế đồng thời phù hợp
  Lưu sự kiện audit cục bộ của kết quả thành công
  Lưu công việc chuyển tiếp nếu cần
COMMIT
~~~

Nếu không lưu được dấu vết bền vững bắt buộc, tác vụ nhạy cảm không nên âm thầm commit rồi trông chờ log từ xa sẽ xuất hiện sau. Tuy nhiên, không nhất thiết phải chờ kho phân tích nhận xong mới được commit: dấu vết audit cục bộ cùng công việc chuyển tiếp bền vững có thể là ranh giới giao dịch ban đầu.

Sự kiện bị từ chối hoặc lỗi cần cách ghi phù hợp. Chèn một sự kiện từ chối rồi rollback toàn bộ giao dịch sẽ làm mất chính sự kiện đó. Có thể ghi bằng giao dịch khác sau rollback, với ngữ nghĩa chính xác về điều đã quan sát.

Không gán actor bằng account ID chỉ vì người gửi nhập đúng email. Thông tin nhận dạng người yêu cầu, tài khoản bị tác động và thành phần thực thi phải được phân biệt. Một chữ ký hợp lệ trên actor được gán sai vẫn là dữ liệu sai được bảo vệ tốt.

## 4. Xác thực nguồn và chống giả bản ghi

Collector cần nhận biết producer nào được phép gửi loại sự kiện nào cho phạm vi tài khoản hoặc tenant nào. Một kết nối được bảo vệ khi truyền chưa đủ nếu mọi dịch vụ đều có quyền khai báo mọi event type.

Ví dụ:

- Dịch vụ gửi thông báo có thể phát sinh DELIVERY_ACCEPTED.
- Nó không tự được phát sinh MFA_REPLACEMENT_COMPLETED.
- Một công cụ hỗ trợ chỉ được ghi quyết định có trong quyền công việc của actor đã được xác thực.
- Client không được tự cung cấp actor type, kết quả thành công và policy version rồi yêu cầu collector tin nguyên dữ liệu đó.

Thông tin về nguồn kết nối phải được đối chiếu với producer trong payload. Nếu payload tự khai sourceService là một dịch vụ khác, cần xử lý như vi phạm hợp đồng thay vì coi chuỗi đó là bằng chứng nguồn gốc.

Mỗi sự kiện cần một event ID ổn định. Khi gửi lại cùng một sự kiện, giữ nguyên ID và nội dung được bảo vệ. Nếu ID đã tồn tại nhưng payload khác, đó là xung đột cần xử lý; không ghi đè bằng một UPSERT tùy tiện.

Đầu vào phải có cấu trúc, giới hạn kích thước và được mã hóa đúng khi hiển thị. Một chuỗi chứa xuống dòng như “mã sai\nADMIN APPROVED” không được biến thành hai bản ghi hợp lệ. Việc hash chuỗi đó không làm cách hiển thị nguy hiểm trở nên an toàn.

## 5. Chỉ bảo vệ được nội dung đã được định nghĩa rõ

Trước khi băm hoặc ký, cần xác định chính xác tập trường thuộc nội dung được bảo vệ. Nếu chỉ băm message nhưng bỏ account ID, outcome hoặc actor, kẻ có quyền ghi có thể thay những trường quyết định ngữ nghĩa mà kiểm tra hash vẫn thành công.

Một payload minh họa:

~~~json
{
  "schemaVersion": 1,
  "eventId": "06c18212-fc93-4d98-8ead-4be830a0ccaa",
  "tenantId": "tenant-17",
  "subjectAccountId": "account-42",
  "requestId": "recovery-request-91",
  "eventType": "RECOVERY_ACTION_COMPLETED",
  "outcome": "SUCCESS",
  "purpose": "REPLACE_MFA",
  "actorType": "SERVICE",
  "actorRef": "account-recovery",
  "sourceService": "account-recovery",
  "occurredAt": "2026-11-24T10:00:00Z",
  "policyVersion": "recovery-policy-v3",
  "metadata": {
    "operation": "MFA_REPLACED"
  }
}
~~~

Các ID và thời điểm trên là dữ liệu minh họa. Payload không chứa OTP, token, khóa riêng, cookie, mật khẩu hay hồ sơ xác minh.

Một quy tắc thực tế là giữ phần sự kiện được bảo vệ riêng với trạng thái vận hành có thể thay đổi:

- Số lần worker thử gửi.
- Thời điểm export gần nhất.
- Trạng thái lập chỉ mục.
- Ghi chú điều tra bổ sung.
- Trạng thái lưu trữ hoặc phục hồi bản sao.

Thay đổi các trạng thái này không nên đòi sửa payload lịch sử. Ghi chú đính chính cần là bản ghi bổ sung có liên kết, actor và lý do, không phải sửa âm thầm sự kiện gốc.

## 6. Canonicalization: cùng dữ liệu phải ra cùng byte

Hai chuỗi JSON có thể biểu diễn cùng một object nhưng khác khoảng trắng hoặc thứ tự thuộc tính. Nếu producer và verifier băm các chuỗi tự serialize theo cách khác nhau, kết quả có thể không khớp dù ngữ nghĩa dự kiến giống nhau.

Cần chọn một hợp đồng rõ:

1. Bảo vệ chính xác byte gốc và giữ nguyên chúng; hoặc
2. Chuyển object hợp lệ thành byte theo một cơ chế canonicalization được xác định rồi bảo vệ byte đó.

[RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html) mô tả một cách tạo biểu diễn JSON ổn định cho hashing và signing. Nếu chọn JCS, phải dùng triển khai tuân thủ hợp đồng đó; việc chỉ sắp xếp key chưa đủ để tự gọi là JCS.

Hợp đồng sự kiện vẫn cần định nghĩa các khác biệt về nghiệp vụ:

- Trường bị thiếu và trường có giá trị null có cùng nghĩa hay không.
- Timestamp phải dùng biểu diễn nào.
- Giá trị enum được chấp nhận là gì.
- Kiểu dữ liệu nào được dùng cho sequence lớn.
- Metadata của mỗi event type có những trường nào.

Ví dụ, có thể quy định timestamp UTC ở một định dạng cố định và sequence là chuỗi số thập phân. Đây là quyết định schema trước khi canonicalize, không phải để verifier tự sửa dữ liệu lịch sử cho “đẹp”.

Không trim chuỗi, đổi chữ hoa, chuẩn hóa Unicode hoặc đổi kiểu số sau khi ký rồi kỳ vọng chữ ký vẫn kiểm chứng được. Muốn có quy tắc chuyển đổi phải xác định nó trong hợp đồng trước khi tạo byte được bảo vệ.

Khi đổi schema hoặc cơ chế canonicalization, lưu phiên bản đủ để verifier biết phải dùng cách nào. Không diễn giải lại toàn bộ sự kiện cũ bằng quy tắc mới mà không có dấu hiệu phân biệt.

## 7. Hash, MAC và chữ ký bảo vệ những gì?

| Cơ chế | Có thể hỗ trợ | Giới hạn cần nhớ |
| --- | --- | --- |
| Hash của payload | So sánh nội dung với một digest đáng tin cậy | Người sửa được cả payload và digest có thể tạo lại hash |
| HMAC | Kiểm tra nội dung với khóa bí mật dùng chung | Bên nắm khóa kiểm tra cũng có thể tạo MAC mới |
| Chữ ký số | Bên có public key tin cậy kiểm tra dữ liệu do khóa ký tương ứng ký | Không chứng minh nội dung nghiệp vụ đúng hoặc khóa ký chưa từng bị lạm dụng |
| Chuỗi hash | Ràng buộc nội dung và thứ tự trong một stream | Cần điểm neo tin cậy để chống tính lại hoặc cắt đuôi |
| Kho hạn chế ghi/xóa | Giảm khả năng sửa lịch sử trong phạm vi cấu hình | Không chứng minh producer đã ghi đủ và đúng từ đầu |

Một cột SHA-256 đặt ngay cạnh payload chỉ là bằng chứng hữu ích khi giá trị đối chiếu được bảo vệ khỏi cùng khả năng sửa. Nó không tự làm bảng dữ liệu bất biến.

Với HMAC, không phát khóa cho mọi công cụ điều tra chỉ để họ tự kiểm tra. Nếu cần nhiều bên kiểm chứng độc lập mà không có khả năng tạo chữ ký mới, chữ ký bất đối xứng có thể phù hợp hơn. Khóa ký cần được bảo vệ và quyền gọi dịch vụ ký cũng phải được giới hạn.

Mã hóa dữ liệu khi lưu nhằm bảo vệ bí mật theo mô hình tương ứng. Không mặc định “đã mã hóa” đồng nghĩa “không thể sửa” hoặc “đã ghi đủ”. Nếu dùng cơ chế mã hóa có xác thực, nó vẫn không tự giải quyết việc xóa cả bản ghi hoặc thay bằng một phiên bản cũ hợp lệ.

## 8. Chuỗi hash theo một stream có phạm vi rõ

Một chuỗi minh họa có thể bảo vệ thứ tự tiếp nhận của collector. Stream có thể được phân chia theo tenant và phân vùng vận hành phù hợp. Không nhất thiết tạo một thứ tự toàn cục cho toàn bộ hệ thống.

Với sự kiện thứ i:

~~~text
eventBytes_i = Canonicalize(event_i)
eventHash_i  = SHA256(eventBytes_i)

protectedEnvelope_i = Canonicalize({
  integrityFormatVersion,
  hashAlgorithm,
  streamId,
  streamEpoch,
  sequence,
  receivedAt,
  previousHash,
  eventHash
})

chainHash_i = SHA256(
  EncodeFields(
    "account-recovery-audit-chain-v1",
    protectedEnvelope_i
  )
)
~~~

Trong ví dụ:

- sequence là thứ tự tiếp nhận trong stream, được biểu diễn theo schema đã quy định.
- previousHash bằng chainHash của bản ghi trước.
- Bản ghi đầu liên kết tới giá trị khởi đầu nằm trong mô tả stream được bảo vệ.
- streamEpoch phân biệt các lần mở một đoạn stream mới theo quy trình.
- EncodeFields phải có cách phân tách không mơ hồ, chẳng hạn mã hóa độ dài trường theo hợp đồng.
- chainHash và chữ ký không nằm trong chính dữ liệu đang được dùng để tính chúng.

Không nối các chuỗi có độ dài tùy ý mà không có framing. Hai bộ trường khác nhau có thể tạo cùng chuỗi đầu vào khi ranh giới trường không được xác định.

Việc thêm bản ghi và cập nhật đầu stream cần nguyên tử theo cơ chế đồng thời phù hợp. Nếu hai worker cùng đọc một previousHash rồi cùng ghi sự kiện tiếp theo, có thể xuất hiện hai nhánh.

~~~text
Đọc đầu stream với quyền cập nhật độc quyền hoặc cơ chế tương đương
Kiểm tra phiên bản đầu stream
Cấp sequence tiếp theo
Lưu sự kiện, envelope và chainHash
Cập nhật đầu stream
Commit
~~~

Đây là mã giả mô tả một đơn vị ghi, không phải lời khuyên dùng một khóa toàn cục cho mọi tài khoản. Khi cần phân vùng, mỗi stream cần có danh tính và phạm vi riêng.

Nếu hợp đồng đòi sequence liên tục, không dùng một bộ cấp số có thể bỏ số khi rollback rồi coi mọi khoảng trống là bị xóa dữ liệu. Cơ chế cấp số và ý nghĩa khoảng trống phải thống nhất. Thứ tự tiếp nhận tại collector cũng không tự chứng minh thứ tự nhân quả tại các producer.

## 9. Điểm neo độc lập mới giúp phát hiện cắt ngắn lịch sử

Giả sử stream đã có 100 sự kiện. Người có quyền quản trị xóa các sự kiện 96–100 và thay đầu stream thành hash của sự kiện 95. Phần còn lại vẫn có thể nối hash đúng.

Nếu verifier chỉ được đưa dữ liệu tới sự kiện 95 và không có bằng chứng rằng sự kiện 100 từng tồn tại, nó không thể tự biết phần đuôi đã bị cắt.

Một điểm neo được niêm phong có thể chứa:

~~~text
streamId
streamEpoch
firstSequence
lastSequence
eventCount
lastChainHash
previousSealDigest
closedAt
integrityFormatVersion
signatureAlgorithm
signingKeyId
~~~

Chữ ký bảo vệ biểu diễn đã được xác định của các trường đó. Metadata chọn thuật toán và khóa phải nằm trong phần được bảo vệ, đồng thời được verifier đối chiếu với danh sách tin cậy. Không tin một public key chỉ vì nó được đính kèm trong gói dữ liệu cần kiểm tra.

Bản niêm phong cần được đưa tới một nơi độc lập về quyền sửa hoặc có cơ chế đối chiếu đáng tin cậy. Nếu verifier biết một điểm neo hợp lệ có lastSequence = 100 nhưng chỉ nhận tới 95, nó có căn cứ kết luận bộ dữ liệu được cung cấp chưa đủ phạm vi đó.

Cơ chế liên kết các bản niêm phong giúp phát hiện lịch sử các đoạn bị thay đổi, nhưng vẫn cần biết bản nào mới nhất được kỳ vọng. Một bản niêm phong cũ có chữ ký hợp lệ không tự chứng minh không có đoạn mới hơn.

Có một cửa sổ trước lần neo độc lập tiếp theo. Trong cửa sổ đó, dữ liệu mới có thể chưa được bảo vệ trước mọi khả năng xóa hoặc rollback của kho chính. Tần suất niêm phong và đối chiếu phải phản ánh giới hạn này.

[AWS CloudTrail — Log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html) là một ví dụ thực tế dùng hash của log và digest được ký để hỗ trợ kiểm tra thay đổi sau chuyển phát. Tài liệu cũng phân biệt việc tạo bằng chứng với việc thực sự chạy kiểm chứng; có digest không đồng nghĩa mọi tệp đã được kiểm tra.

## 10. Chống thiếu sự kiện trước collector và chống phát lại

Một chuỗi tiếp nhận liên tục vẫn có thể thiếu sự kiện nghiệp vụ nếu producer chưa từng chuyển chúng tới collector. Sequence của collector chỉ mô tả những gì nó đã tiếp nhận.

Cần các tín hiệu bổ sung phù hợp:

- Hàng đợi hoặc outbox còn tồn đọng.
- Dấu vết giao dịch nhạy cảm đã commit nhưng chưa được xác nhận tiếp nhận.
- Đối soát phạm vi nguồn với phạm vi collector.
- Sự kiện thay đổi cấu hình logging hoặc quyền phát sự kiện.
- Cảnh báo về producer ngừng hoạt động khi đang có công việc được kỳ vọng.

Không kết luận “không có sự kiện khôi phục” chỉ vì truy vấn audit không trả dòng nào. Có thể đó là giai đoạn không có hoạt động, lỗi thu thập, độ trễ lập chỉ mục hoặc một phạm vi truy vấn sai.

Phát lại một sự kiện đã được tiếp nhận cần được nhận biết bằng event ID và nội dung tương ứng. Nếu ID và nội dung khớp, có thể xác nhận lại thay vì thêm một lần nghiệp vụ mới. Nếu không khớp, cần giữ bằng chứng xung đột và xử lý theo policy.

Phát lại một bản sao lịch sử cũ là vấn đề khác. Để phát hiện, verifier cần phạm vi kỳ vọng, bằng chứng về đầu stream hoặc bản niêm phong mới nhất từ nguồn tin cậy. Chữ ký hợp lệ trên một bản cũ chỉ chứng minh bản cũ đó đã được ký.

Timestamp do producer khai báo không tự là đồng hồ tin cậy. Chữ ký bảo vệ giá trị timestamp đã được ghi, không chứng minh thời gian thực tế chính xác hoặc mọi đồng hồ đã đồng bộ.

## 11. Verifier phải đưa ra kết luận có phạm vi

Quy trình kiểm chứng cần biết nó đang kiểm tra toàn stream, một đoạn hay chỉ một sự kiện. Một bản export đã lọc theo account ID thường không có đủ các bản ghi xen giữa để kiểm tra nguyên chuỗi của stream dùng chung.

Mã giả cho một đoạn có bằng chứng đầu và cuối phù hợp:

~~~text
Nhận phạm vi kỳ vọng và trust material từ nguồn tin cậy
Kiểm tra phiên bản định dạng và thuật toán được cho phép
Kiểm tra chữ ký của bản niêm phong và liên kết niêm phong cần thiết
Xác định điểm bắt đầu, điểm kết thúc và số lượng kỳ vọng

Với từng bản ghi theo thứ tự đã quy định:
  Kiểm tra stream, epoch và sequence
  Tạo lại canonical bytes của sự kiện
  So sánh eventHash
  Kiểm tra previousHash và tính lại chainHash
  Kiểm tra nội dung envelope thuộc phạm vi được bảo vệ

Đối chiếu hash cuối, số lượng và biên phạm vi với bằng chứng tin cậy
Trả kết quả cùng phần chưa thể kết luận
~~~

Không nên chỉ trả một cờ valid chung. Có thể phân biệt:

| Kết quả | Ý nghĩa |
| --- | --- |
| VERIFIED_FOR_RANGE | Dữ liệu đáp ứng các kiểm tra cho phạm vi và nguồn tin cậy đã nêu |
| CONTENT_MISMATCH | Nội dung không khớp digest được bảo vệ |
| CHAIN_LINK_MISMATCH | Liên kết hoặc thứ tự không khớp hợp đồng |
| MISSING_EXPECTED_RECORD | Thiếu dữ liệu mà bằng chứng phạm vi yêu cầu |
| SIGNATURE_INVALID | Chữ ký không kiểm chứng được theo khóa và thuật toán hợp lệ |
| TRUST_MATERIAL_UNAVAILABLE | Chưa có đủ khóa hoặc điểm neo tin cậy |
| RANGE_INCOMPLETE | Bộ dữ liệu được cung cấp chưa đủ để kiểm chứng phạm vi yêu cầu |

Thiếu public key không đồng nghĩa đã chứng minh dữ liệu bị sửa. Ngược lại, không thấy mismatch trong một tập con không đồng nghĩa toàn bộ lịch sử đầy đủ.

Nếu cần kiểm tra một bản export có lọc, phải cung cấp bằng chứng phù hợp hoặc giới hạn kết luận vào nội dung từng bản ghi. Không bỏ qua những khoảng trống do lọc rồi gọi đó là kiểm chứng toàn stream.

## 12. Quản lý khóa, quyền ghi và thay đổi hợp lệ

Khóa ký hoặc khóa MAC không nên được lưu cùng quyền quản trị đầy đủ của kho audit. Cần kiểm soát quyền sử dụng khóa, việc đổi chính sách ký và việc truy cập công cụ xác minh.

Khi xoay khóa:

- Bản ghi hoặc bản niêm phong chỉ rõ key ID và định dạng chữ ký.
- Verifier có nguồn public key hoặc trust configuration được xác thực.
- Giữ được khả năng kiểm tra dữ liệu cũ theo chính sách lưu giữ.
- Việc chuyển khóa có dấu vết và liên kết tin cậy phù hợp.

Không xóa khả năng kiểm chứng lịch sử chỉ vì đã ngừng dùng khóa cũ để ký mới. Nếu khóa bị lộ, cần xác định khoảng thời gian và phạm vi bị ảnh hưởng. Một chữ ký có thể còn đúng về toán học nhưng nguồn gốc đáng tin của nó đã bị nghi ngờ.

Ký lại toàn bộ lịch sử bằng khóa mới không tự phục hồi tính đúng đắn của dữ liệu sau sự cố. Cần căn cứ đối chiếu độc lập và ghi rõ điều gì đã được xác nhận.

Ở lớp lưu trữ, có thể hạn chế writer thường xuyên vào quyền thêm mới, tách quyền đọc và quyền bảo trì, lưu bản sao có chính sách chống sửa phù hợp. Quyền owner, quyền quản trị, khả năng đổi policy và việc phục hồi backup đều phải nằm trong mô hình đe dọa.

Đính chính nghiệp vụ cần thêm sự kiện tham chiếu bản gốc. Ví dụ, phát hiện actorRef được gán sai thì ghi một bản đính chính có thẩm quyền; không đổi trực tiếp sự kiện cũ rồi tính lại hash để lịch sử trông như chưa có lỗi.

## 13. Lưu giữ, xóa dữ liệu và phản ứng khi kiểm chứng thất bại

Tính toàn vẹn không phải lý do để giữ bí mật hoặc dữ liệu cá nhân vô thời hạn. Ngay từ lúc tạo sự kiện, chỉ đưa vào phần cần thiết. Không lưu token, OTP hoặc mật khẩu dưới dạng rõ; cũng không cho rằng hash của một mã ít khả năng là cách che giấu an toàn.

Nếu payload chứa dữ liệu nhạy cảm rồi bị neo vào nhiều kho, việc xử lý sau đó sẽ phức tạp hơn. Có thể tách dữ liệu chi tiết có quyền đọc và vòng đời riêng khỏi lõi audit tối thiểu, nhưng tham chiếu và digest vẫn cần được đánh giá về khả năng nhận dạng.

Khi xóa theo chính sách:

- Xác định rõ phạm vi, thời điểm và chủ thể có quyền.
- Giữ bằng chứng tối thiểu về quyết định xóa nếu policy cho phép.
- Phân biệt dữ liệu đã được xóa hợp lệ với dữ liệu chưa tìm thấy do lỗi.
- Không báo “đã kiểm chứng toàn bộ nội dung” khi nội dung cần kiểm tra không còn.

Một manifest có chữ ký về việc xóa có thể giúp giải thích quyết định, nhưng không thay thế được nội dung đã xóa để kiểm tra lại toàn bộ hash. Việc giữ điểm neo cũng cần chính sách lưu giữ phù hợp.

Khi gặp mismatch, không tự sửa chuỗi bằng cách tính lại mọi hash rồi xóa cảnh báo. Cần giữ bản sao và kết quả kiểm chứng, xác định phạm vi, đối chiếu nguồn độc lập và xử lý sự cố theo quyền được cấp.

Không dùng audit bị nghi ngờ làm nguồn duy nhất để cấp quyền khôi phục hoặc kết luận một người đã phê duyệt. Dữ liệu nghiệp vụ hiện tại, bằng chứng giao dịch và lịch sử độc lập cần được đánh giá theo vai trò riêng.

## 14. Tình huống vận dụng

Một dịch vụ hoàn tất thay MFA cho một request đã đủ điều kiện. Tác vụ, sự kiện audit cục bộ và công việc chuyển tiếp được commit cùng nhau. Collector tiếp nhận sự kiện vào một stream, sau đó một đoạn lịch sử được niêm phong và neo độc lập.

Sau sự cố, nhóm điều tra phát hiện bản sao trong kho chính có ba dấu hiệu:

1. Outcome của một sự kiện đã đổi từ DENIED thành SUCCESS.
2. Bản ghi cuối của đoạn đã biến mất.
3. Một bản export chỉ gồm các sự kiện còn lại được trình bày như lịch sử đầy đủ.

Cách đánh giá phù hợp:

- Tính lại event hash và kiểm tra chuỗi dựa trên điểm neo tin cậy để nhận diện nội dung bị thay.
- Đối chiếu biên đoạn và số lượng kỳ vọng để phát hiện thiếu bản ghi cuối.
- Giới hạn kết luận của bản export nếu thiếu dữ liệu hoặc bằng chứng phạm vi.
- Đối soát với giao dịch nghiệp vụ và nguồn audit cục bộ để xác định tác vụ nào thực sự đã commit.
- Không coi chữ ký hợp lệ của một đoạn cũ là bằng chứng rằng không có sự kiện mới hơn.
- Giữ bằng chứng ban đầu trước khi phục hồi hoặc thay bản sao bị lỗi.

Một thiết kế toàn vẹn hữu ích phải trả lời được **dữ liệu nào được bảo vệ, từ thời điểm nào, trước những quyền can thiệp nào, và phạm vi nào đã thực sự được kiểm chứng**. Những câu trả lời đó quyết định giá trị của lịch sử audit khi điều tra một vụ khôi phục tài khoản đáng ngờ.
