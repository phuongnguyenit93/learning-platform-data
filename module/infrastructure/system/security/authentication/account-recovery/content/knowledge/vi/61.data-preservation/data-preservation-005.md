# Preserving recovery evidence — Bảo toàn bằng chứng khôi phục tài khoản

## 1. Bảo toàn bằng chứng nhằm giải quyết vấn đề gì?

Khôi phục tài khoản diễn ra khi người dùng không còn sử dụng được mật khẩu, MFA, passkey hoặc thiết bị xác thực như bình thường. Hệ thống có thể phải dựa vào các kết quả xác minh bổ sung, xác nhận của tổ chức hoặc quyết định của quản trị viên. Nếu các căn cứ này bị thay đổi, thất lạc hoặc không còn liên hệ được với quyết định đã đưa ra, rất khó giải thích vì sao một người được phép tiếp cận tài khoản.

**Preserving recovery evidence** là việc thu nhận, lưu giữ và quản lý bằng chứng để dữ liệu cần thiết còn nguyên vẹn, có nguồn gốc được ghi nhận và có thể được truy xuất đúng thẩm quyền trong khoảng thời gian đã xác định.

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bảo toàn bằng chứng phải hỗ trợ xác minh danh tính, đánh giá rủi ro, chống lạm dụng và kiểm toán quyết định. Đồng thời, nó không được tạo ra một kho mật khẩu, mã dùng một lần hoặc giấy tờ cá nhân không được kiểm soát.

Ba mục tiêu cần được xem cùng nhau:

1. **Tính toàn vẹn:** biết dữ liệu nào đã được thu nhận và phát hiện thay đổi ngoài dự kiến.
2. **Khả năng truy vết:** liên kết được bằng chứng với nguồn, phương pháp xác minh, yêu cầu và quyết định sử dụng nó.
3. **Bảo vệ dữ liệu:** chỉ lưu, đọc và giữ dữ liệu trong phạm vi cần thiết, với quyền truy cập và thời hạn phù hợp.

Một tệp được lưu vĩnh viễn nhưng ai cũng đọc được không phải một kết quả bảo toàn an toàn. Ngược lại, một kho mã hóa rất tốt nhưng không thể xác định bản nào đã được người duyệt xem cũng chưa đáp ứng mục tiêu truy vết.

## 2. Phân biệt vật chứng, kết quả xác minh và quyết định

Không nên gọi mọi dữ liệu trong hồ sơ khôi phục là cùng một loại bằng chứng.

| Loại dữ liệu | Ví dụ | Điều cần bảo toàn |
|---|---|---|
| Vật chứng do người yêu cầu cung cấp | Tài liệu hoặc thông tin được gửi qua cổng hỗ trợ | Nguồn thu nhận, phiên bản và nội dung thực sự đã tiếp nhận nếu chính sách cho phép lưu |
| Kết quả xác minh từ backend | Hoàn thành thử thách trên kênh đã đăng ký | Phương pháp, ngữ cảnh, thời điểm, kết quả và liên kết với yêu cầu |
| Kết quả từ bên xác minh khác | Kết quả kiểm tra qua một nhà cung cấp hoặc tổ chức | Nguồn đã xác thực, tham chiếu, phiên bản và giới hạn của kết quả |
| Tín hiệu rủi ro | Cảnh báo thay đổi kênh liên hệ gần đây | Dữ liệu cần thiết để giải thích đánh giá tại thời điểm đó |
| Kết luận thẩm định | Người duyệt chấp nhận một tập bằng chứng | Bộ bằng chứng cụ thể, người duyệt, chính sách và phạm vi kết luận |
| Quyết định cấp quyền | Cho phép đăng ký lại MFA | Căn cứ, thời hạn, phạm vi và kết quả sử dụng quyền |

Việc bảo toàn một ảnh chụp màn hình không biến nội dung ảnh thành kết quả xác minh có thẩm quyền. Tính toàn vẹn của dữ liệu đã lưu và tính đúng đắn của điều được dữ liệu đó khẳng định là hai vấn đề khác nhau.

Ví dụ, hệ thống có thể chứng minh tệp không bị sửa kể từ khi tiếp nhận. Điều đó chưa chứng minh người gửi là chủ tài khoản hoặc tài liệu chưa bị giả mạo trước khi gửi. Hồ sơ cần ghi nhận giới hạn này thay vì dùng một nhãn chung `trusted = true`.

## 3. Xác định dữ liệu cần lưu trước khi thu thập

Không nên bắt đầu bằng việc lưu tất cả rồi mới quyết định dữ liệu nào cần thiết. Chính sách bảo toàn cần được xác định theo loại bằng chứng và mục đích sử dụng.

Những câu hỏi cần trả lời gồm:

- Cần lưu nội dung gốc hay chỉ cần kết quả xác minh cùng tham chiếu có thể kiểm tra?
- Dữ liệu được dùng để ra quyết định hiện tại, giải quyết khiếu nại hay điều tra lạm dụng?
- Ai có quyền truy cập và trong điều kiện nào?
- Cần giữ trong bao lâu, và sự kiện nào bắt đầu tính thời hạn?
- Nếu nguồn bên ngoài không còn cho truy xuất, phần dữ liệu còn lại có đủ để giải thích quyết định không?
- Khi không lưu nội dung gốc, giới hạn tái dựng cần được ghi nhận thế nào?

### Không bảo toàn bí mật có thể dùng để đăng nhập

Không lưu mật khẩu, OTP thô, recovery code, token đặt lại mật khẩu, cookie phiên hoặc khóa riêng passkey vào hồ sơ bằng chứng chỉ để chứng minh người dùng đã thực hiện bước xác minh.

Với thử thách dùng một lần, bằng chứng phù hợp thường là định danh thử thách, loại phương thức, thời điểm xác minh, trạng thái tiêu thụ và ngữ cảnh liên quan. Không cần giữ giá trị bí mật để biết thử thách đã hoàn tất.

Một giá trị băm của mã ngắn cũng không tự làm cho việc lưu mã trở nên an toàn, vì không gian đoán có thể nhỏ. Nếu không cần bí mật cho mục đích bảo toàn, giải pháp ưu tiên là không ghi nó vào hồ sơ.

Nếu người dùng gửi nhầm bí mật trong nội dung hỗ trợ, cần xử lý qua quy trình dữ liệu nhạy cảm và an ninh phù hợp. Không sao chép bí mật đó sang nhiều nhật ký để “giữ đủ bằng chứng”.

## 4. Mô hình siêu dữ liệu cho một bằng chứng

Một mô hình minh họa:

```text
evidenceId
tenantId
recoveryRequestId
requestVersion
evidenceType
sourceType
sourceReference
collectorIdentity
collectionMethod
occurredAt
collectedAt
preservedAt
storageObjectId
storageObjectVersion
contentLength
contentDigestAlgorithm
contentDigest
verificationResultReference
derivedFromEvidenceId
retentionPolicyId
retentionDeadline
preservationState
```

Không phải mọi loại bằng chứng đều cần một tệp. Một kết quả xác minh nội bộ có thể được lưu như bản ghi có cấu trúc, trong khi tài liệu được lưu ở kho đối tượng. Các trường không áp dụng cần có quy ước rõ ràng, thay vì điền giá trị giả để làm hồ sơ trông đầy đủ.

### Ý nghĩa các mốc thời gian

- `occurredAt` là thời điểm sự kiện nguồn xảy ra nếu được biết và có căn cứ.
- `collectedAt` là thời điểm hệ thống tiếp nhận dữ liệu.
- `preservedAt` là thời điểm hoàn tất bước lưu giữ theo contract của hệ thống.

Không dùng thời gian do thiết bị người gửi khai báo như thời điểm chắc chắn của một sự kiện đã được xác minh. Nếu thời điểm nguồn chưa rõ, giữ trạng thái chưa xác định và ghi nhận nguồn của timestamp.

### Định danh ổn định khác đường dẫn truy cập

`evidenceId` dùng để tham chiếu bằng chứng trong quyết định. Đường dẫn tải xuống hoặc URL tạm thời không nên là định danh duy nhất, vì chúng có thể hết hạn, thay đổi hoặc chứa thông tin truy cập nhạy cảm.

Thông tin kho lưu trữ cần đủ để tìm đúng đối tượng và phiên bản. Không dùng tên như `latest-document.pdf` rồi ghi đè mỗi khi người dùng gửi lại, vì một quyết định cũ khi đó có thể trỏ sang nội dung mới.

## 5. Thu nhận và lưu giữ theo một quy trình rõ ràng

Một trình tự minh họa:

```text
Tiếp nhận qua kênh được kiểm soát
    → kiểm tra phạm vi và giới hạn đầu vào
    → ghi nguồn thu nhận và định danh bằng chứng
    → lưu bản cần bảo toàn ở trạng thái cách ly phù hợp
    → xác nhận lưu đúng phiên bản và nội dung
    → thực hiện xử lý an toàn hoặc xác minh cần thiết
    → tạo bản dẫn xuất nếu cần cho người duyệt
    → công bố hồ sơ đủ điều kiện sử dụng
```

### Thu nhận qua kênh được kiểm soát

Nên dùng cổng hoặc API được thiết kế cho bằng chứng thay vì yêu cầu nhân viên tải tài liệu về máy cá nhân rồi gửi qua chat. Cần ràng buộc dữ liệu với đúng yêu cầu và tenant ngay từ đầu, đồng thời áp dụng kiểm soát đầu vào phù hợp.

Tên tệp, phần mở rộng, loại nội dung tự khai và nội dung tài liệu đều là dữ liệu không tin cậy. Chúng không được phép điều khiển đường dẫn lưu trữ tùy ý hoặc trở thành chỉ thị thay đổi quy trình khôi phục.

### Không xử lý chủ động một tệp chưa được kiểm soát

Tài liệu có thể chứa mã độc, nội dung gây quá tải hoặc liên kết dẫn ra ngoài. Bảo toàn không đồng nghĩa mở tệp trực tiếp trên máy người hỗ trợ. Cần cách ly, giới hạn dung lượng, kiểm soát xử lý tệp và cung cấp cách xem an toàn phù hợp với hệ thống.

Nếu chính sách yêu cầu giữ bản gốc đã tiếp nhận, việc quét hoặc chuyển đổi không được âm thầm thay thế bản gốc đó. Lưu kết quả xử lý và bản dẫn xuất với quan hệ rõ ràng. Nếu một loại nội dung không được phép lưu, cần có quy trình xử lý tương ứng, không tự tuyên bố mọi đầu vào đều phải giữ nguyên vô thời hạn.

### Xác nhận lưu giữ trước khi công bố sẵn sàng

Một thao tác upload được chấp nhận không tự chứng minh cả tệp và siêu dữ liệu đã được lưu nhất quán. Cần xác nhận đối tượng tồn tại ở đúng phiên bản, có chiều dài và giá trị toàn vẹn khớp với dữ liệu đã tiếp nhận.

Không đánh dấu bằng chứng sẵn sàng cho quyết định nếu bản ghi chỉ tới một tệp chưa lưu xong hoặc đã mất. Ngược lại, tệp lưu xong nhưng chưa liên kết với hồ sơ cần được quản lý như đối tượng chưa hoàn tất, không để tồn tại ngoài chính sách lưu trữ.

## 6. Tính toàn vẹn và giới hạn của hàm băm

Hệ thống có thể tính một digest, chẳng hạn SHA-256, trên đúng dãy byte cần bảo toàn. Khi đọc lại, tính lại digest để phát hiện sự khác nhau so với giá trị tham chiếu.

```text
digest lúc tiếp nhận
    == digest của đúng phiên bản đã lưu
    == digest khi truy xuất để đối chiếu
```

Mô hình này có ích khi giá trị tham chiếu và siêu dữ liệu được bảo vệ phù hợp. Nếu người tấn công có thể sửa cả tệp lẫn digest trong cùng một kho không được kiểm soát, phép so sánh có thể vẫn khớp sau khi bị thay đổi.

Các biện pháp bổ sung có thể gồm phân tách quyền quản trị, phiên bản đối tượng, bản ghi chỉ thêm, bản sao ở vùng bảo vệ độc lập và dấu xác thực được quản lý khóa phù hợp. Chọn biện pháp theo mô hình đe dọa; không gọi một thuộc tính kho lưu trữ là “không thể giả mạo” nếu chưa xét quyền của người quản trị và nguồn tham chiếu.

Hàm băm không chứng minh:

- Người gửi có quyền khôi phục tài khoản.
- Tài liệu là thật trước thời điểm tiếp nhận.
- Nội dung trong tài liệu đúng sự thật.
- Dữ liệu đã được thu thập đầy đủ, không bỏ sót phần quan trọng.
- Dữ liệu chưa từng bị người có quyền đọc sao chép ra ngoài.

Nếu cần đối chiếu nội dung JSON có cấu trúc, phải xác định rõ đang băm byte nguồn hay biểu diễn chuẩn hóa. Hai tài liệu có cùng ý nghĩa có thể khác byte do thứ tự trường hoặc định dạng; ngược lại, một bản chuẩn hóa có thể không bảo toàn cách dữ liệu ban đầu được trình bày. Chọn mục tiêu rồi ghi lại phương pháp và phiên bản tương ứng.

## 7. Bản gốc, bản đã che dữ liệu và bản dẫn xuất

Người duyệt không phải lúc nào cũng cần xem toàn bộ tài liệu. Hệ thống có thể tạo bản che một phần dữ liệu, ảnh xem trước hoặc kết quả trích xuất để giảm việc tiếp xúc thông tin nhạy cảm.

Mỗi bản dẫn xuất cần liên kết với đúng bản nguồn:

```text
evidence-original-21, version=1
    → evidence-redacted-22, transform=redaction-policy-v3
    → evidence-preview-23, transform=preview-pipeline-v2
```

Ghi nhận phiên bản công cụ hoặc quy tắc xử lý khi cần để giải thích bản dẫn xuất đã được tạo thế nào. Không sửa bản gốc rồi vẫn giữ định danh và digest cũ.

Che dữ liệu cũng cần kiểm tra theo cách phù hợp với định dạng. Một lớp hình vẽ đè lên văn bản không luôn đồng nghĩa dữ liệu bên dưới đã bị loại khỏi tệp. Vì vậy, không mặc định một bản có vùng màu đen trên màn hình là bản đã giảm dữ liệu an toàn.

Nếu quyết định dựa trên bản đã che hoặc bản trích xuất, lưu tham chiếu tới đúng bản người duyệt đã xem và kết quả xác minh liên quan. Khi một lỗi xử lý dẫn xuất được phát hiện, hệ thống phải biết những quyết định nào có thể bị ảnh hưởng.

Không lưu bản gốc chỉ vì có khả năng tạo bản dẫn xuất nếu chính sách của loại bằng chứng không cho phép hoặc không cần giữ bản gốc. Quy trình phải nêu rõ phần nào được bảo toàn và giới hạn giải thích phát sinh từ lựa chọn đó.

## 8. Nguồn gốc và lịch sử quản lý bằng chứng

Lịch sử quản lý cần cho biết bằng chứng đã đi qua những bước nào kể từ khi hệ thống tiếp nhận: ai hoặc dịch vụ nào thu thập, xử lý, xác minh, truy cập hoặc thay đổi trạng thái.

Một sự kiện minh họa:

```json
{
  "eventType": "RECOVERY_EVIDENCE_PRESERVED",
  "eventId": "event-demo-301",
  "evidenceId": "evidence-demo-21",
  "tenantId": "tenant-demo-12",
  "recoveryRequestId": "recovery-demo-742",
  "requestVersion": 2,
  "objectVersion": "object-version-demo-1",
  "collector": "recovery-portal",
  "collectedAt": "2026-11-24T04:10:00Z",
  "preservedAt": "2026-11-24T04:10:02Z",
  "retentionPolicyId": "recovery-evidence-demo-v2"
}
```

Các giá trị trên chỉ minh họa cấu trúc. Sự kiện không chứa tài liệu gốc, mã xác thực hoặc URL có quyền truy cập.

Lịch sử bắt đầu từ thời điểm hệ thống quan sát được. Nếu tài liệu đã tồn tại ở thiết bị người dùng trước đó, không suy diễn rằng hệ thống biết toàn bộ lịch sử của tài liệu trước khi tiếp nhận.

Một chuỗi sự kiện đầy đủ có thể hỗ trợ giải thích cách quản lý bằng chứng, nhưng không tự bảo đảm mọi dữ liệu trong chuỗi là đúng. Các tài khoản dịch vụ, nguồn callback và người thực hiện vẫn phải được xác thực và kiểm soát quyền.

## 9. Bảo toàn đúng bộ bằng chứng đã được sử dụng

Một yêu cầu có thể nhận thêm dữ liệu qua nhiều lần. Nếu người duyệt xem bộ bằng chứng phiên bản 2 nhưng quyết định chỉ trỏ tới “bộ mới nhất”, dữ liệu bổ sung sau đó có thể làm sai lệch cách hiểu về quyết định cũ.

Nên tạo tập tham chiếu có phiên bản:

```text
evidenceSetId = set-demo-66
evidenceSetVersion = 2
members = [
    evidence-demo-21@version-1,
    verification-demo-44@version-3,
    organization-confirmation-demo-8@version-1
]
```

Quyết định phê duyệt tham chiếu đúng tập này, phiên bản yêu cầu, chính sách và đánh giá rủi ro đã được sử dụng. Bằng chứng mới tạo phiên bản mới, không viết lại nội dung tập cũ.

Nếu một kết quả bị thu hồi hoặc được xác định không còn đáng tin cậy, giữ sự kiện thay đổi và tham chiếu bản bị ảnh hưởng. Không xóa im lặng kết quả cũ khiến lịch sử trông như người duyệt chưa từng dựa vào nó.

Tuy nhiên, việc giữ bằng chứng cũ trong lịch sử không có nghĩa tiếp tục chấp nhận nó để cấp quyền. Tính hiện hữu trong kho và tính hợp lệ cho quyết định mới phải được kiểm tra riêng.

## 10. Nhất quán giữa kho đối tượng và cơ sở dữ liệu

Nhiều hệ thống lưu tệp ở kho đối tượng và siêu dữ liệu ở cơ sở dữ liệu. Hai nơi này không mặc nhiên cùng thuộc một transaction.

Một luồng có thể dùng các trạng thái minh họa:

```text
PENDING_CAPTURE
    → STAGED
    → PRESERVED
    → RETENTION_REVIEW hoặc DELETION_PENDING
    → DELETED
```

`STAGED` thể hiện đối tượng đã được tiếp nhận nhưng chưa đủ điều kiện công bố là bằng chứng được bảo toàn. `PRESERVED` chỉ được đặt khi các điều kiện lưu trữ và liên kết cần thiết đã được xác nhận.

Khi xử lý lỗi, cần phân biệt:

| Trạng thái lỗi | Cách xử lý cần có |
|---|---|
| Upload chưa hoàn tất | Không cho dùng làm căn cứ; hủy hoặc tiếp tục theo contract |
| Tệp đã lưu nhưng ghi siêu dữ liệu thất bại | Tra cứu bằng operation ID và quản lý đối tượng chưa liên kết |
| Siêu dữ liệu tồn tại nhưng đối tượng bị thiếu | Chặn việc sử dụng, phát hiện bất nhất và điều tra |
| Phản hồi bị mất sau khi lưu thành công | Retry theo idempotency key, không tạo hồ sơ trùng ngoài ý muốn |
| Cùng khóa retry nhưng nội dung khác | Từ chối xung đột hoặc tạo phiên bản mới theo contract rõ ràng |

Chỉ dùng idempotency key khi đã ràng buộc nó với người gọi, tenant, yêu cầu và nội dung phù hợp. Không để một key do client chọn cho phép tham chiếu tới tệp của tài khoản khác.

Nếu dùng outbox để phát sự kiện bảo toàn, nó giúp ràng buộc trạng thái nguồn và yêu cầu phát sự kiện trong cùng cơ sở dữ liệu. Nó không tự xác nhận rằng đối tượng bên ngoài đã được lưu đúng; điều kiện đó cần được xử lý trước khi công bố trạng thái tương ứng.

## 11. Kiểm soát truy cập và mã hóa

Bằng chứng khôi phục có thể chứa thông tin giúp kẻ tấn công tiếp tục mạo danh người dùng. Vì vậy, quyền đọc hồ sơ phải được giới hạn theo nhiệm vụ, không chỉ dựa vào việc người dùng có một vai trò hỗ trợ chung.

Các kiểm tra cần bao gồm đúng tenant, đúng yêu cầu, vai trò người truy cập và mục đích thao tác. Một đối tượng có tên khó đoán không thay thế kiểm tra phân quyền.

Nếu cung cấp URL tải xuống tạm thời, cần kiểm soát việc cấp URL, thời hạn và phạm vi truy cập. URL hết hạn không có nghĩa đối tượng đã được xóa; ngược lại, URL còn hiệu lực có thể là một đường đọc dữ liệu cần được xem xét khi thu hồi quyền.

Mã hóa khi truyền và khi lưu giúp bảo vệ dữ liệu theo những rủi ro tương ứng. Khóa mã hóa cần được quản lý tách biệt phù hợp; không đưa khóa hoặc thông tin giải mã vào cùng nhật ký truy cập tài liệu.

Theo dõi các hành động nhạy cảm như xem bản gốc, tải xuống hàng loạt, xuất hồ sơ hoặc cấp quyền đọc đặc biệt. Nhật ký truy cập cũng cần tránh chứa nội dung bằng chứng hoặc bí mật truy cập.

Nếu kho bằng chứng bị xâm phạm, việc chỉ đổi quyền đọc ở giao diện hỗ trợ có thể chưa đủ. Cần xem xét các đường truy cập thực tế như URL còn hiệu lực, tài khoản dịch vụ, khóa và bản sao đã xuất theo quy trình xử lý sự cố.

## 12. Thời hạn lưu khác thời hạn sử dụng bằng chứng

Một kết quả xác minh có thể không còn đủ mới để cấp quyền nhưng vẫn được giữ để giải thích quyết định trước đó. Ngược lại, việc dữ liệu còn nằm trong kho không cho phép dùng nó cho mọi yêu cầu mới.

| Giới hạn | Câu hỏi được trả lời |
|---|---|
| Hạn sử dụng bằng chứng | Bằng chứng có còn được chấp nhận cho quyết định hiện tại không? |
| Hạn phê duyệt | Quyết định đã duyệt còn có thể cấp quyền không? |
| Hạn token hoặc quyền khôi phục | Người dùng còn có thể thực hiện bước khôi phục không? |
| Hạn lưu dữ liệu | Hệ thống còn được giữ dữ liệu cho mục đích đã xác định đến khi nào? |

Không kéo dài token để giữ bằng chứng. Khi token hết hạn hoặc đã dùng, có thể giữ bản ghi kết quả trong thời hạn cho phép mà vẫn giữ token mất hiệu lực.

Chính sách lưu cần xác định mốc bắt đầu, thời hạn theo loại dữ liệu, trách nhiệm đánh giá và cách xử lý bản sao. Các trường hợp cần giữ lâu hơn cho điều tra hoặc giải quyết tranh chấp phải có phạm vi, lý do, thẩm quyền và điều kiện kết thúc rõ ràng. Không dùng một cờ giữ lại không hết hạn cho toàn bộ tài khoản một cách mặc định.

Việc gia hạn lưu trữ không tự gia hạn độ mới của bằng chứng hoặc thẩm quyền của quyết định. Hệ thống cần kiểm tra các giới hạn này bằng những quy tắc riêng.

## 13. Xóa có kiểm soát và phục hồi từ bản sao lưu

Đến hạn, việc xóa cần xét cả đối tượng gốc, các phiên bản, bản dẫn xuất, bản xuất và các nơi lưu liên quan trong phạm vi hệ thống quản lý. Chỉ xóa một hàng siêu dữ liệu có thể để lại tệp không còn được theo dõi.

Một quy trình có thể chuyển sang `DELETION_PENDING`, xác minh điều kiện được phép xóa, xử lý các bản liên quan rồi ghi kết quả tối thiểu theo chính sách. Nếu một bước thất bại, giữ trạng thái và nguyên nhân rõ ràng; không báo đã xóa đầy đủ khi vẫn còn bản được quản lý chưa xử lý.

Lịch sử quyết định có thể cần giữ một tham chiếu tối thiểu để diễn giải rằng bằng chứng từng tồn tại nhưng nội dung đã hết thời hạn lưu. Phần lịch sử đó cũng phải được xem xét về dữ liệu cá nhân và thời hạn riêng, thay vì mặc định không cần quản lý.

Backup phục vụ khả năng khôi phục vận hành nhưng không phải kho để tùy ý truy xuất bằng chứng đã hết hạn. Cần có quy tắc về vòng đời backup, quyền phục hồi và cách áp dụng lại các trạng thái xóa hoặc hạn lưu khi phục hồi.

Phục hồi dữ liệu từ backup không được làm sống lại token đã tiêu thụ, phiên đã thu hồi hoặc phê duyệt đã hết hạn. Dữ liệu bằng chứng và trạng thái bảo mật hiện hành có liên quan nhưng không thể được tua lại đồng loạt mà bỏ qua các sự kiện đã xảy ra.

## 14. Ví dụ: bảo toàn hồ sơ mất thiết bị MFA

Một yêu cầu `recovery-demo-742` trải qua các bước:

1. Người yêu cầu gửi tài liệu E1 qua cổng hỗ trợ.
2. Hệ thống ghi nguồn tiếp nhận, lưu đúng phiên bản E1 và xác nhận tính toàn vẹn.
3. Một quy trình tạo bản đã che dữ liệu D1 từ E1 để người duyệt xem.
4. Backend ghi kết quả xác minh V1, liên kết với yêu cầu phiên bản 2.
5. Người duyệt chấp thuận một phạm vi dựa trên tập `[D1, V1]` và các tham chiếu nguồn tương ứng.
6. Người yêu cầu gửi tài liệu thay thế E2 và đề nghị đổi đích nhận kết quả.

Ở bước 6, hệ thống không được ghi đè E1 bằng E2 rồi để quyết định cũ tiếp tục trỏ tới “tài liệu hiện tại”. Cần tạo bằng chứng và phiên bản tập mới; thay đổi đích nhận kết quả được đánh giá theo quy tắc phiên bản yêu cầu và phạm vi phê duyệt.

Nếu sau đó phát hiện E1 có vấn đề, lịch sử phải cho biết quyết định nào đã dựa vào E1 hoặc D1. Từ đó có thể xác định quyền khôi phục, thay đổi MFA hoặc phiên nào cần được xem xét. Việc ghi nhận E1 không còn được chấp nhận không tự thu hồi mọi quyền phát sinh; các thao tác bảo mật đó cần được thực hiện và ghi nhận riêng.

Khi đến hạn lưu, E1 và D1 được xử lý theo chính sách áp dụng. Nếu nội dung đã bị xóa, một báo cáo sau này cần nêu rõ chỉ còn các tham chiếu và kết quả nào, không khẳng định người điều tra đã xem lại toàn bộ tài liệu gốc.

## 15. Các tình huống cần được thiết kế rõ

Những tình huống sau mô tả hành vi mong muốn, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi phù hợp |
|---|---|
| Người dùng gửi lại tài liệu khác | Tạo bản mới, không thay nội dung được quyết định cũ tham chiếu |
| Digest khớp nhưng nguồn chưa xác minh | Chỉ xác nhận tính toàn vẹn trong phạm vi đối chiếu, không kết luận nguồn là thật |
| Tệp chứa nội dung nguy hiểm | Cách ly và xử lý qua cơ chế an toàn, không mở trực tiếp để xem xét |
| Người duyệt chỉ cần kết quả xác minh | Không mặc định cấp quyền đọc toàn bộ tài liệu gốc |
| Tệp lưu xong nhưng siêu dữ liệu chưa ghi | Quản lý trạng thái chưa hoàn tất và retry có định danh |
| Siêu dữ liệu trỏ đến đối tượng bị mất | Chặn sử dụng làm căn cứ và xử lý bất nhất |
| Bằng chứng quá cũ nhưng còn trong hạn lưu | Giữ cho mục đích được phép, không tự chấp nhận cho quyết định mới |
| Token hết hạn nhưng hồ sơ cần giữ | Giữ kết quả cần thiết, không phục hồi hiệu lực token |
| Hết hạn lưu khi đang có yêu cầu giữ lại được phê duyệt | Áp dụng phạm vi và thời hạn giữ lại đã xác định, không gia hạn mọi dữ liệu vô điều kiện |
| Backup được phục hồi | Áp dụng lại các ràng buộc vòng đời và trạng thái bảo mật hiện hành |
| Nội dung gốc đã được xóa theo chính sách | Báo giới hạn tái dựng, không dùng tham chiếu trống để khẳng định đã xác minh lại |

Những sai lầm thường gặp là giữ mọi dữ liệu vô thời hạn, lưu bí mật xác thực như vật chứng, coi hàm băm là chứng minh danh tính và để quyết định cũ trỏ vào một tệp có thể bị ghi đè.

Bảo toàn bằng chứng tốt giúp biết chính xác dữ liệu nào đã được tiếp nhận, xử lý và sử dụng cho một quyết định khôi phục. Kết quả đó cần đi cùng dữ liệu tối thiểu, truy cập có kiểm soát, phiên bản ổn định và vòng đời lưu trữ rõ ràng, trong khi hiệu lực của token, phê duyệt và phiên vẫn được quản lý bằng những ràng buộc bảo mật riêng.
