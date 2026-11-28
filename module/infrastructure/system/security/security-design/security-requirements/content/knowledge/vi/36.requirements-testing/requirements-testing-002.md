# Positive security test: kiểm chứng hành vi bảo mật hợp lệ

## 1. Positive security test là gì?

Trong bài này, positive security test là ca kiểm thử xác nhận hệ thống thực hiện đúng hành vi bảo mật được yêu cầu khi đầu vào, danh tính, quyền và trạng thái đều hợp lệ theo chính sách.

Ví dụ: một người đã hoàn tất xác thực theo chính sách, có quyền xem hóa đơn của tổ chức A và dùng phiên còn hiệu lực phải đọc được đúng hóa đơn được cấp quyền. Ca kiểm thử còn kiểm tra hệ thống giữ đúng danh tính, giới hạn trường dữ liệu và tạo bằng chứng audit khi yêu cầu quy định.

Mục tiêu không dừng ở “chức năng chạy được”. Một phản hồi thành công nhưng dùng sai danh tính, trả quá nhiều dữ liệu hoặc bỏ qua cơ chế bắt buộc vẫn không đạt yêu cầu bảo mật.

Trong chương Kiểm thử yêu cầu của module Security Requirements, positive security test nối đặc tả với bằng chứng trên một bản triển khai cụ thể. Nó giúp phát hiện cả việc kiểm soát bảo mật bị cấu hình quá chặt khiến người hợp lệ không làm được việc, lẫn trường hợp luồng thành công hoạt động sai thuộc tính bảo mật.

Sau bài học, người học có thể:

- Chọn các tình huống hợp lệ từ yêu cầu và tiêu chí chấp nhận.
- Thiết kế dữ liệu, danh tính và quyền tối thiểu cần cho từng ca.
- Viết phép kiểm tra cho xác thực, phân quyền, dữ liệu, logging và phục hồi.
- Phân biệt kết quả nghiệp vụ với bằng chứng hiệu lực kiểm soát.
- Báo cáo kết quả và giới hạn phạm vi mà không suy ra quá mức.

Các mã yêu cầu, API, ngưỡng và dữ liệu trong bài là ví dụ thiết kế. Chúng phải được thay bằng chính sách và tiêu chí thực tế của hệ thống; không phải ngưỡng chung do một tiêu chuẩn bắt buộc.

## 2. Phân biệt với các khái niệm dễ nhầm

| Khái niệm | Điều nó mô tả | Ví dụ |
| --- | --- | --- |
| Positive security test | Hành vi mong đợi trong điều kiện hợp lệ | Người có quyền đọc đúng tài nguyên được cấp |
| Negative security test | Hành vi trước điều kiện không hợp lệ hoặc hành động bị cấm | Người dùng A không đọc được hóa đơn B |
| PASS hoặc FAIL | Kết quả đối chiếu quan sát với mong đợi của một ca | Một positive test FAIL vì người hợp lệ bị từ chối |
| Positive finding | Cách một công cụ hoặc báo cáo gọi một phát hiện | Công cụ báo có điểm yếu cần xác minh |
| False positive | Phát hiện báo có vấn đề nhưng đánh giá xác nhận vấn đề đó không thực sự tồn tại trong phạm vi xét | Cảnh báo nhầm về một cấu hình |

Một negative test bị hệ thống từ chối đúng chính sách có thể PASS. Một positive test nhận mã 200 vẫn có thể FAIL nếu trả nhầm dữ liệu. Tên loại kiểm thử không quyết định kết quả.

Các ca kiểm thử bảo mật cần bao phủ cả điều kiện được phép và bị cấm. OWASP WSTG đề cập việc kiểm chứng yêu cầu tích cực và tiêu cực đối với các nhóm kiểm soát như danh tính, xác thực, truy cập, mã hóa và audit trong hoạt động phát triển. [Nguồn: OWASP WSTG v4.2 — Introduction](https://wstg.owasp.org/v4.2/2-Introduction/).

### Luồng hợp lệ cũng phải có điều kiện bảo mật

So sánh hai cách kiểm tra:

~~~text
Kiểm tra nghiệp vụ quá hẹp:
  Gọi API đọc hóa đơn và xác nhận nhận HTTP 200.

Positive security test:
  Dùng danh tính và phiên hợp lệ với đúng quyền.
  Gọi API đọc hóa đơn nằm trong phạm vi được cấp.
  Xác nhận đúng tài nguyên, đúng trường dữ liệu và đúng danh tính xử lý.
  Kiểm tra sự kiện audit theo yêu cầu.
  Ghi lại phiên bản chính sách và triển khai được đánh giá.
~~~

Cách thứ hai tạo bằng chứng rõ hơn, nhưng vẫn chưa chứng minh mọi truy cập trái phép đều bị chặn. Phần đó cần các ca đối ứng và phương pháp đánh giá bổ sung.

## 3. Từ yêu cầu đến ca kiểm thử hợp lệ

Bắt đầu từ bốn câu hỏi:

1. Hệ thống phải cho phép hành vi nào?
2. Điều kiện nào làm hành vi đó hợp lệ?
3. Những thuộc tính bảo mật nào vẫn phải giữ khi hành vi thành công?
4. Bằng chứng nào cho phép kết luận?

Ví dụ:

| Thành phần | Nội dung minh họa |
| --- | --- |
| Mục tiêu | Cách ly dữ liệu hóa đơn giữa các tổ chức |
| Rủi ro | Sai ánh xạ danh tính hoặc quyền làm trả dữ liệu ngoài phạm vi |
| Yêu cầu | SEC-AUTHZ-21: người dùng chỉ đọc hóa đơn thuộc tổ chức và quyền được cấp |
| Tiêu chí chấp nhận | Người có quyền đọc hóa đơn hợp lệ nhận đúng tài nguyên và tập trường được phép |
| Positive test | POS-AUTHZ-01: A-reader đọc hóa đơn INV-A-01 của A |
| Bằng chứng | Danh tính thử, quyền hiệu lực, phản hồi, mã tương quan, audit nếu được yêu cầu |

Nếu yêu cầu chỉ viết “phân quyền đúng” mà chưa có cách xác định quyền hợp lệ, cần làm rõ đặc tả. Không tự dùng trạng thái hiện tại của ứng dụng làm định nghĩa điều đúng.

### Chọn các lớp điều kiện hợp lệ

“Người dùng hợp lệ” không phải một giá trị duy nhất. Cần cân nhắc các nhóm khác nhau có thể đi qua logic riêng:

- Người dùng cá nhân, người quản trị và danh tính máy.
- Vai trò chỉ đọc, người được chỉnh sửa và người phê duyệt.
- Quyền cấp trực tiếp và quyền qua nhóm, nếu hệ thống hỗ trợ.
- Tài nguyên có chủ sở hữu khác nhau nhưng đều được cấp quyền hợp lệ.
- Các đường API, giao diện và tác vụ nền thuộc phạm vi yêu cầu.
- Phiên mới và phiên còn hiệu lực trong các trạng thái được chính sách cho phép.

Chọn đại diện dựa trên rủi ro và kiến trúc. Không cần nhân mọi biến thành toàn bộ tổ hợp, nhưng phải biết tổ hợp nào đang chưa được kiểm chứng.

## 4. Thiết kế fixture và môi trường

Fixture là bộ trạng thái ban đầu có thể kiểm soát: tài khoản, quyền, phiên, tài nguyên và cấu hình cần cho ca kiểm thử.

Với ví dụ hóa đơn:

| Đối tượng | Trạng thái |
| --- | --- |
| Tổ chức A | Có hóa đơn tổng hợp INV-A-01 |
| Tổ chức B | Có hóa đơn tổng hợp INV-B-01 với dữ liệu phân biệt rõ |
| A-reader | Tài khoản cá nhân, đang hiệu lực, chỉ có quyền đọc tại A |
| B-reader | Tài khoản cá nhân, đang hiệu lực, chỉ có quyền đọc tại B |
| Chính sách | Phiên bản xác thực và phân quyền đã được phê duyệt cho môi trường |
| Audit | Nguồn sự kiện và nơi truy xuất bằng chứng đã được cấu hình |
| Mã lần chạy | Giá trị riêng để phân biệt dữ liệu và sự kiện giữa các ca |

### Dùng quyền đúng với hành vi cần chứng minh

Tài khoản đặc quyền có thể cần để tạo fixture, nhưng hành động đang kiểm thử phải dùng đúng danh tính cần đánh giá. Nếu dùng admin để chứng minh người chỉ đọc truy cập được hóa đơn, kết quả không trả lời yêu cầu của vai trò chỉ đọc.

Tách danh tính chuẩn bị dữ liệu khỏi danh tính thực hiện thao tác. Tương tự, quyền dọn dữ liệu sau ca không được vô tình đi theo client đang kiểm thử.

Nếu chạy nhiều tài khoản, dùng phiên và cookie jar riêng. Một client còn giữ phiên admin từ bước thiết lập có thể làm mọi assertion nghiệp vụ đúng trong khi danh tính thực hiện đã sai.

### Kiểm tra tiền điều kiện bằng nguồn có thẩm quyền

Trước khi thực hiện, cần xác nhận:

- Tài khoản và tài nguyên thuộc đúng phạm vi.
- Quyền cấp tối thiểu đã có hiệu lực.
- Phiên được tạo qua cơ chế phù hợp với mục tiêu ca.
- Dữ liệu kỳ vọng được biết từ fixture độc lập.
- Phụ thuộc cần thiết sẵn sàng và cấu hình tương ứng với bản triển khai được đánh giá.

Nếu tiền điều kiện không thiết lập được, kết quả nên là lỗi thiết lập hoặc BLOCKED theo quy ước của nhóm. Không đánh dấu PASS vì “không có phản hồi trái yêu cầu”.

Môi trường không nhất thiết giống production từng chi tiết, nhưng các cơ chế liên quan tới kết luận phải có tính đại diện. Nếu tắt security filter hoặc thay toàn bộ quyết định quyền bằng mock cho phép, chỉ có thể kết luận trong phạm vi lớp đang được kiểm tra.

## 5. Ca kiểm thử hoàn chỉnh: người chỉ đọc xem hóa đơn của mình

### 5.1. Hợp đồng kiểm chứng

**Mã:** POS-AUTHZ-01.

**Yêu cầu liên quan:**

- SEC-AUTHZ-21: đọc dữ liệu theo đúng danh tính, quyền và tổ chức.
- SEC-DATA-08: chỉ trả tập trường được phép cho vai trò đọc.
- SEC-AUDIT-05: thao tác đọc thuộc phạm vi phải có sự kiện audit trong tối đa 60 giây ở điều kiện vận hành bình thường.

**Tiền điều kiện:** A-reader có phiên hợp lệ, có quyền đọc INV-A-01, không có đặc quyền quản trị. INV-A-01 được tạo từ fixture tổng hợp với giá trị kỳ vọng đã biết.

**Hành động:** dùng phiên của A-reader yêu cầu đọc INV-A-01 qua API thuộc phạm vi.

~~~http
GET /api/invoices/INV-A-01 HTTP/1.1
Host: billing.test
Authorization: Bearer <session-token-cua-A-reader>
X-Correlation-ID: <ma-lan-chay>
Accept: application/json
~~~

Đường dẫn, domain và token ở đây chỉ là ký hiệu minh họa.

Phản hồi mong đợi theo hợp đồng giả định:

~~~json
{
  "id": "INV-A-01",
  "organizationId": "A",
  "number": "TEST-A-001",
  "total": 1250000,
  "currency": "VND"
}
~~~

### 5.2. Các assertion cần có

| Thuộc tính | Phép kiểm tra |
| --- | --- |
| Thành công theo hợp đồng | Trạng thái và kiểu nội dung đúng hợp đồng API |
| Đúng tài nguyên | Mã hóa đơn, tổ chức và giá trị khớp fixture độc lập |
| Đúng tập trường | Tập khóa trả về đúng danh sách được phép cho vai trò, không có trường nội bộ ngoài hợp đồng |
| Đúng danh tính | Ngữ cảnh xử lý và audit đối chiếu được tới A-reader |
| Đúng hành động | Audit thể hiện đọc hóa đơn, đúng đối tượng và kết quả thành công |
| Đúng thời hạn | Sự kiện của hành động có thể truy xuất trong cửa sổ 60 giây đã định |
| Giới hạn dữ liệu bằng chứng | Báo cáo không chứa token sống hoặc dữ liệu ngoài mục đích kiểm tra |

Không lấy toàn bộ phản hồi thực tế rồi lưu lại làm kết quả kỳ vọng mới mỗi lần chạy. Làm vậy có thể hợp thức hóa việc API bắt đầu trả thêm một trường nhạy cảm.

Nếu API có các trường động được phép, cần ghi rõ quy tắc kiểm tra từng trường. Ví dụ thời gian phản hồi phải hợp lệ trong cửa sổ của ca, chứ không phải bỏ kiểm tra toàn bộ metadata vì “nó thường thay đổi”.

### 5.3. Pseudocode cho Arrange–Act–Assert

Đoạn dưới mô tả ý tưởng, không phải bộ test có thể chạy trực tiếp. Các helper phải được triển khai theo kiến trúc và framework thực tế.

~~~text
runId = newTestRunId()
fixture = provisioner.createInvoiceReaderFixture(runId)

try:
    session = identity.signInByApprovedFlow(fixture.reader)
    requireFixture(session.principalId == fixture.reader.id)
    requireFixture(effectiveRights(fixture.reader) == fixture.expectedRights)

    startedAt = monotonicClock.now()
    response = invoiceApi.read(
        id = fixture.invoice.id,
        session = session,
        correlationId = runId
    )

    assert response.status == 200
    assert response.contentType matches agreedJsonContract
    assert response.body.keys == fixture.allowedResponseFields
    assert response.body.id == fixture.invoice.id
    assert response.body.organizationId == fixture.organization.id
    assert response.body.number == fixture.invoice.number
    assert response.body.total == fixture.invoice.total
    assert response.body.currency == fixture.invoice.currency

    event = awaitMatchingAudit(
        correlationId = runId,
        action = "INVOICE_READ",
        resourceId = fixture.invoice.id,
        deadline = startedAt + 60 seconds
    )

    assert event.actorId == fixture.reader.id
    assert event.organizationId == fixture.organization.id
    assert event.result == "SUCCESS"

    recordEvidenceWithoutCredentials(runId, response, event)
finally:
    provisioner.cleanupOwnedFixture(runId)
~~~

Mã trạng thái 200, tên sự kiện và các trường là hợp đồng giả định của ví dụ. Khi triển khai cần dùng đúng hợp đồng của sản phẩm.

Việc chờ audit được giới hạn bằng một deadline cố định tính từ mốc đã chọn. Mỗi lần poll không được tự đặt lại 60 giây; nếu không, ca có thể chờ rất lâu rồi vẫn báo đạt. Có thể dừng sớm khi có sự kiện phù hợp, nhưng phải kiểm tra nội dung sự kiện thay vì chỉ kiểm tra “có log”.

Nếu lỗi trong cleanup, cần ghi nhận riêng mà không che mất lỗi assertion ban đầu. Cleanup cũng phải giới hạn vào dữ liệu do lần chạy tạo, tránh làm thay đổi fixture của ca khác.

### 5.4. Kết luận đúng phạm vi

Nếu mọi assertion đạt, có thể kết luận A-reader đọc được đúng INV-A-01 qua đường API đã kiểm tra và các thuộc tính liên quan đạt theo bằng chứng.

Chưa thể kết luận API không có lỗi phân quyền, mọi tổ chức đều được cách ly, hoặc người thiếu quyền luôn bị chặn. Một hệ thống bỏ kiểm tra quyền hoàn toàn vẫn có thể trả đúng dữ liệu cho yêu cầu hợp lệ này; cần ca đối ứng và đánh giá bổ sung để phân biệt.

## 6. Positive test cho xác thực và phiên

### Luồng xác thực hợp lệ

Một ca có thể đặt mục tiêu: người dùng đang hiệu lực hoàn tất cơ chế xác thực được phê duyệt và nhận phiên đại diện đúng danh tính.

Các bước chính:

1. Tạo tài khoản thử có trạng thái và phương thức xác thực phù hợp.
2. Thực hiện luồng đăng nhập thực tế thuộc phạm vi.
3. Hoàn tất các yếu tố hoặc bước bổ sung mà chính sách yêu cầu.
4. Nhận phiên và dùng phiên đó gọi một chức năng được cấp.
5. Đối chiếu chủ thể, thuộc tính phiên cần thiết và audit từ nguồn đáng tin cậy.

Các assertion có thể gồm:

- Danh tính được thiết lập đúng tài khoản thử.
- Quyền và phạm vi không rộng hơn fixture đã phê duyệt.
- Thuộc tính phiên đáp ứng chính sách có phiên bản.
- Thông tin bí mật không bị đưa vào phản hồi hoặc log ngoài hợp đồng.
- Chức năng được cấp hoạt động đúng khi dùng phiên vừa tạo.

Nếu chỉ giải mã payload của token mà không xác minh nguồn và tính hợp lệ, các trường nhìn thấy chưa đủ làm bằng chứng xác thực. Cách kiểm chứng phải tương ứng với cơ chế thật, chẳng hạn nguồn xác minh chữ ký hoặc trạng thái phiên có thẩm quyền.

### Kiểm tra kênh truyền trong luồng hợp lệ

Có thể quan sát luồng đăng nhập và sử dụng phiên để xác nhận thông tin xác thực được truyền qua kênh bảo vệ đã quy định. OWASP WSTG hướng dẫn kiểm tra việc vận chuyển thông tin xác thực trong quá trình đăng nhập và sử dụng phiên, đồng thời lưu ý rằng có mã hóa không tự chứng minh mọi thuộc tính an toàn đều đạt. [Nguồn: OWASP WSTG v4.2 — Credentials Transported over an Encrypted Channel](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/04-Authentication_Testing/01-Testing_for_Credentials_Transported_over_an_Encrypted_Channel/).

Nếu kiến trúc kết thúc TLS tại gateway, quan sát client–gateway chỉ hỗ trợ kết luận cho đoạn đó. Các đoạn khác thuộc yêu cầu cần bằng chứng tương ứng.

### Giới hạn của ca đăng nhập thành công

Hoàn tất MFA thành công chưa chứng minh MFA bắt buộc trên mọi đường truy cập. Người dùng nhận được một phiên hợp lệ cũng chưa chứng minh phiên giả, hết hạn hoặc đã thu hồi sẽ bị từ chối. Những tình huống đó cần ca khác.

Trong một positive test, assertion “phản hồi không chứa mật khẩu” vẫn phù hợp. Phân loại positive ở đây dựa trên điều kiện và hành vi hợp lệ đang kiểm tra, không dựa trên việc assertion được viết dưới dạng khẳng định hay phủ định.

## 7. Positive test cho phân quyền

Thay vì dùng một ca admin cho mọi chức năng, xây ma trận các hành vi được cấp thực sự.

| Danh tính | Điều kiện hợp lệ | Hành động được phép | Thuộc tính cần giữ |
| --- | --- | --- | --- |
| Người chỉ đọc A | Có quyền đọc tài nguyên tại A | Xem hóa đơn được cấp | Đúng dữ liệu, đúng trường, không chuyển sang thao tác sửa |
| Nhân viên xử lý | Được phân công và hóa đơn còn ở trạng thái cho sửa | Chỉnh sửa các trường được cấp | Chỉ trường cho phép thay đổi, đúng người thực hiện |
| Người phê duyệt | Có quyền, đủ điều kiện tách nhiệm vụ theo chính sách | Phê duyệt hóa đơn hợp lệ | Đúng trạng thái, đúng người, có audit |
| Danh tính worker | Có quyền thực thi đúng loại tác vụ | Xử lý tác vụ hợp lệ đã được giao | Đúng phạm vi dữ liệu, không dùng quyền quản trị không cần thiết |
| Người được cấp quyền qua nhóm | Thành viên nhóm đã có hiệu lực | Thực hiện chức năng nhóm được phép | Ánh xạ quyền và tổ chức chính xác |

Mỗi hàng có thể dẫn tới nhiều ca cụ thể. Ma trận giúp phát hiện trường hợp cấu hình quá chặt, ánh xạ nhóm sai hoặc một đường tích hợp không truyền đúng ngữ cảnh người dùng.

Ví dụ, việc phân quyền mới đã được cấp và có hiệu lực phải cho phép người được cấp thực hiện hành vi tương ứng. Để kiểm tra đúng, cần xác định mốc hiệu lực và giới hạn đồng bộ mà yêu cầu cho phép; không thêm retry không giới hạn để đợi một lúc nào đó hệ thống sẽ chấp nhận.

Với nghiệp vụ tách nhiệm vụ, chọn người phê duyệt hợp lệ khác người tạo. Nếu fixture dùng chính người tạo, ca không còn đại diện cho điều kiện được phép theo chính sách đó.

## 8. Positive test cho bảo vệ dữ liệu

### Xuất dữ liệu theo đúng mục đích và quyền

Một người có quyền xuất dữ liệu được phép tạo và tải bản xuất. Ca cần xác nhận:

- Bộ lọc và phạm vi thuộc đúng quyền được cấp.
- Tập bản ghi, trường dữ liệu và định dạng đúng hợp đồng.
- Người nhận hoặc nơi phân phối là đúng đối tượng đã chọn.
- Luồng lưu và tải đáp ứng các điều kiện bảo vệ được quy định.
- Tác vụ nền, nếu có, giữ đúng ngữ cảnh quyền ở các thời điểm yêu cầu.

Một bản xuất có đủ dữ liệu cần dùng nhưng kèm thêm trường nội bộ vẫn là lỗi. Kiểm tra tập trường dự kiến hoặc schema được phê duyệt thường có giá trị hơn chỉ tìm một vài trường cấm đã biết.

### Ghi và đọc dữ liệu qua cơ chế mã hóa

Một ca tích hợp có thể dùng danh tính dịch vụ được cấp quyền để ghi dữ liệu tổng hợp, rồi đọc lại qua luồng ứng dụng được phép. Nó kiểm tra khả năng sử dụng dữ liệu hợp lệ và tính toàn vẹn nghiệp vụ qua cơ chế bảo vệ.

Để kết luận yêu cầu mã hóa đạt, cần bằng chứng bổ sung phù hợp về cấu hình đang hiệu lực, cơ chế khóa và phạm vi lưu trữ. Đọc lại đúng dữ liệu không chứng minh dữ liệu được mã hóa; không tìm thấy chuỗi rõ trong một file cũng không đủ chứng minh cơ chế mã hóa phù hợp.

Không dùng quyền quản trị kho lưu trữ để thay cho quyền ứng dụng rồi kết luận luồng ứng dụng đã đúng. Mục tiêu là kiểm tra chính danh tính và cơ chế mà yêu cầu quy định.

## 9. Positive test cho logging và audit

Một ca hợp lệ như cập nhật hóa đơn có thể đồng thời kiểm tra yêu cầu audit, nếu các tiêu chí được liên kết rõ.

Ví dụ POS-AUDIT-02:

1. Người có quyền sửa thay đổi một trường được cấp trên hóa đơn tổng hợp.
2. Xác nhận thay đổi nghiệp vụ có hiệu lực đúng một lần theo hợp đồng thao tác.
3. Tìm sự kiện bằng mã tương quan và mã tài nguyên của lần chạy.
4. Kiểm tra chủ thể, hành động, kết quả, thời gian và ngữ cảnh bắt buộc.
5. Kiểm tra dữ liệu không được phép ghi theo chính sách audit.

Nếu hạ tầng gửi sự kiện ít nhất một lần và có retry, cần phân biệt bản gửi lặp với một sự kiện logic. Không mặc định “chỉ có đúng một dòng log” trừ khi hợp đồng thật sự yêu cầu và cơ chế triển khai bảo đảm điều đó.

Bằng chứng phải khớp hành động của ca hiện tại. Một sự kiện cũ có cùng tên hành động không chứng minh lần chạy mới đã được ghi nhận. Mã tương quan nên kết hợp với đối tượng, danh tính và thời gian phù hợp, thay vì chỉ dựa vào một chuỗi client tự gửi.

Khi audit tới trễ, phép kiểm tra cần giữ giới hạn thời gian đã thỏa thuận. Nếu quá hạn, tiêu chí độ trễ không đạt dù sự kiện xuất hiện sau đó. Nếu không truy cập được nguồn bằng chứng, ghi rõ chưa xác nhận được thuộc tính audit thay vì suy ra đạt từ phản hồi nghiệp vụ.

## 10. Positive test cho phục hồi

Ở phạm vi bài này, positive test cho phục hồi là thực hiện thành công một quy trình phục hồi được hỗ trợ, với bản sao và quyền truy cập đáp ứng tiền điều kiện. Việc thử backup hỏng, mất khóa hoặc phụ thuộc thất bại thuộc các tình huống bổ sung khác.

Một ca có thể gồm:

- Chuẩn bị dữ liệu tổng hợp có mốc nhất quán xác định.
- Tạo bản sao theo quy trình được hỗ trợ.
- Thực hiện phục hồi trong môi trường kiểm chứng đã quy định.
- Dùng danh tính hợp lệ truy cập dịch vụ và thực hiện chức năng đại diện.
- Kiểm tra dữ liệu, quyền và cấu hình bảo mật sau phục hồi.
- Đo thời gian và khoảng dữ liệu mất theo yêu cầu.

Nếu kịch bản diễn tập bắt đầu bằng một sự cố giả lập, luồng phục hồi vẫn là hành vi được hệ thống thiết kế để hỗ trợ trong kịch bản đó. Cần ghi rõ cách phân loại để người đọc không nhầm “positive” với việc hệ thống luôn ở trạng thái bình thường.

Với RTO và RPO, định nghĩa mốc bắt đầu, mốc sẵn sàng nghiệp vụ và mốc dữ liệu khôi phục được trước khi chạy. Khôi phục database thành công nhưng quyền quản trị trở lại cấu hình mặc định hoặc người dùng không thực hiện được nghiệp vụ chưa đáp ứng toàn bộ yêu cầu phục hồi an toàn.

## 11. Chọn mức kiểm thử phù hợp

Positive security test có thể tồn tại ở nhiều mức; mỗi mức trả lời một phần khác nhau.

| Mức | Điều có thể kiểm chứng | Giới hạn thường gặp |
| --- | --- | --- |
| Đơn vị | Hàm hoặc chính sách trả đúng kết quả cho điều kiện hợp lệ | Không chứng minh đường truy cập thực tế gọi đúng hàm |
| Thành phần / tích hợp | Ứng dụng kết nối đúng với IdP, nơi quyết định quyền, kho dữ liệu hoặc audit | Có thể chưa bao phủ gateway, client và mọi đường triển khai |
| Đầu cuối | Danh tính hợp lệ thực hiện nghiệp vụ qua chuỗi thành phần thuộc phạm vi | Tốn thời gian, khó chẩn đoán hơn, vẫn chỉ bao phủ tình huống đã chọn |
| Kiểm chứng vận hành | Cấu hình và khả năng quan sát giữ đúng trong môi trường mục tiêu | Cần kiểm soát dữ liệu và tác động của thao tác kiểm chứng |

Không có tỷ lệ chung bắt buộc giữa các mức. Chọn theo vị trí thực thi kiểm soát, rủi ro và chi phí duy trì.

Ví dụ với yêu cầu MFA: một unit test của hàm ánh xạ thuộc tính phiên không chứng minh ứng dụng thật đã cấu hình đúng IdP và không bỏ qua security filter. Cần ít nhất phần tích hợp hoặc đầu cuối phù hợp với kết luận muốn đưa ra.

Ngược lại, dồn mọi biến thể dữ liệu vào test đầu cuối có thể làm suite chậm và khó phân tích. Có thể kiểm tra nhiều biến thể ở mức thấp, giữ các luồng đầu cuối đại diện cho ranh giới quan trọng.

OWASP Developer Guide lưu ý các phép kiểm tra cần được chọn và điều chỉnh theo ứng dụng và yêu cầu của tổ chức. Việc tham khảo hướng dẫn không có nghĩa mọi ca đều phù hợp hoặc phải áp dụng nguyên một danh sách. [Nguồn: OWASP Developer Guide — WSTG](https://devguide.owasp.org/en/06-verification/01-guides/01-wstg/).

## 12. Bảo đảm ca kiểm thử có khả năng phát hiện sai lệch

### 12.1. Oracle phải độc lập với lỗi có thể xảy ra

Test oracle là căn cứ xác định kết quả đúng. Với POS-AUTHZ-01, oracle gồm dữ liệu fixture, quyền được cấp và hợp đồng phản hồi.

Nếu hệ thống lấy tổ chức từ header client, còn test cũng dùng chính header đó làm kết quả kỳ vọng, hai bên có thể cùng sai. Cần dùng nguồn fixture đã biết người dùng thực sự được cấp quyền tại đâu.

Tương tự, không lấy danh tính do response tự khai làm bằng chứng duy nhất rằng cơ chế xác thực đã được thực hiện. Đối chiếu với luồng tạo phiên và nguồn quan sát đáng tin cậy phù hợp.

### 12.2. Kiểm tra nguyên nhân của một PASS

Một ca hợp lệ có thể PASS dù kiểm soát bị vô hiệu hóa. Các nguyên nhân thường gặp:

- Tài khoản thử có nhiều quyền hơn dự kiến.
- Request thực tế dùng token hoặc cookie của tài khoản khác.
- Mock luôn trả quyết định cho phép.
- Cấu hình thử bỏ qua cơ chế bảo mật.
- Đường được kiểm tra là endpoint công khai khác với endpoint yêu cầu bảo vệ.
- Cache hoặc fixture tồn dư trả dữ liệu giống kết quả mong đợi.

Cách khắc phục là xác nhận tiền điều kiện, tách client và dữ liệu, giữ thông tin phiên bản cấu hình, chọn assertion đúng ranh giới và có ca đối ứng thích hợp.

Ví dụ, với cùng thao tác đọc hóa đơn, một ca riêng dùng người không có quyền phải bị từ chối theo hợp đồng. Ca đó thuộc nhóm kiểm thử điều kiện bị cấm; nó giúp kiểm tra khả năng phân biệt giữa được phép và không được phép. Không cần biến positive test thành một chuỗi kiểm tra mọi tấn công trong cùng hàm.

### 12.3. Dùng dữ liệu phân biệt được sai sót

Nếu mọi hóa đơn đều có cùng giá trị và mọi tổ chức đều dùng cùng một tài khoản thử, trả nhầm tài nguyên có thể không làm test FAIL.

Nên dùng mã và giá trị phân biệt giữa các tổ chức, tài nguyên và lần chạy. So sánh tập bản ghi hoặc trường theo tiêu chí đã định, không chỉ kiểm tra “danh sách không rỗng”.

Với phép đo thời gian, sử dụng nguồn đo phù hợp. Đồng hồ đơn điệu hữu ích để đo khoảng thời gian trong tiến trình test; sự kiện qua nhiều hệ thống còn cần quy ước timestamp, lệch đồng hồ và tương quan rõ ràng.

### 12.4. Retry không được che lỗi

Có thể poll để đợi một kết quả bất đồng bộ trong giới hạn đã thống nhất. Tuy nhiên:

- Không tự đăng nhập bằng admin khi người thử bị từ chối.
- Không bỏ qua assertion bảo mật sau một số lần thất bại.
- Không tự đổi dữ liệu hoặc quyền để buộc thao tác thành công.
- Không xóa lần thất bại khỏi báo cáo chỉ vì một lần chạy lại đạt.
- Không gia hạn deadline sau mỗi lần poll.

Nếu cần chạy lại do lỗi hạ tầng, phải giữ dấu vết lần đầu và nguyên nhân. Sự không ổn định lặp lại cần được phân tích thay vì coi là nhiễu mặc định.

## 13. Truy vết kết quả trong vòng đời phát triển

Một ca nên giữ chuỗi liên kết:

~~~text
Rủi ro / mục tiêu bảo vệ
  -> yêu cầu và phiên bản
  -> tiêu chí chấp nhận
  -> positive test và fixture
  -> thành phần, chính sách, bản triển khai
  -> bằng chứng và kết quả
  -> phát hiện, khắc phục và kiểm chứng lại
~~~

Báo cáo có thể dùng mẫu:

~~~text
Test: POS-AUTHZ-01
Requirement: SEC-AUTHZ-21 v2
Acceptance criterion: AC-AUTHZ-21-01
Scope: API đọc chi tiết hóa đơn, vai trò chỉ đọc tại tổ chức A
Environment / build / policy: các định danh được lưu cùng bằng chứng
Identity and fixture: tham chiếu an toàn, không kèm thông tin xác thực
Expected: đúng tài nguyên, tập trường, danh tính và audit theo hợp đồng
Observed: kết quả thực tế và liên kết bằng chứng đã giới hạn quyền truy cập
Result: PASS / FAIL / BLOCKED
Limitations: chưa kết luận cho vai trò hoặc đường truy cập ngoài phạm vi
Related finding: mã phát hiện nếu có
~~~

Một positive test FAIL cần được phân loại: sản phẩm từ chối người hợp lệ, sai ánh xạ danh tính, trả dữ liệu sai, audit không đạt hoặc fixture chưa đúng. Không quy mọi lỗi thành lỗ hổng, nhưng cũng không bỏ qua lỗi khả dụng của kiểm soát bảo mật.

Trong pipeline, các ca nhanh có thể kiểm tra mỗi thay đổi; các ca tích hợp hoặc đầu cuối chạy theo mốc phù hợp. Điều kiện chặn phát hành phải gắn với rủi ro và tiêu chí đã thỏa thuận.

Khi thêm worker, thay IdP, đổi cache, mở endpoint hoặc thay đổi chính sách quyền, cần đánh giá ca hiện có còn đại diện không. Kết quả cũ không tự chứng minh thành phần hoặc đường truy cập mới.

Chỉ số “100% positive test PASS” cần đi kèm số ca, phạm vi và bộ tiêu chí. Nó không chứng minh 100% yêu cầu bảo mật đã được kiểm chứng, càng không chứng minh không tồn tại lỗ hổng.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ kiểm tra HTTP 200 | Bỏ sót sai danh tính, sai dữ liệu và audit | Kiểm tra các thuộc tính gắn với yêu cầu |
| Dùng admin cho mọi ca | Không chứng minh vai trò ít quyền hoạt động đúng | Dùng quyền tối thiểu cho hành động cần kiểm tra |
| Tái sử dụng client còn phiên cũ | Hành động không do danh tính dự kiến thực hiện | Tách phiên và xác nhận danh tính thực tế |
| Dữ liệu A và B giống nhau | Trả nhầm tài nguyên vẫn có thể PASS | Dùng dữ liệu tổng hợp phân biệt được |
| Mock toàn bộ quyết định bảo mật | Chỉ chứng minh hệ thống hoạt động khi luôn được cho phép | Giới hạn kết luận và thêm kiểm tra tích hợp phù hợp |
| Chỉ tìm một vài trường cấm | Bỏ sót trường nhạy cảm mới | Kiểm tra schema hoặc tập trường được phép |
| Audit khớp mỗi tên hành động | Có thể nhận nhầm sự kiện cũ | Tương quan danh tính, tài nguyên, lần chạy và thời gian |
| Chờ hoặc retry vô hạn | Che sai ngưỡng và làm test treo | Giữ deadline cố định, ghi đầy đủ kết quả |
| Bật chức năng bảo mật nhưng không dùng luồng thật | Có cấu hình mà không có bằng chứng thực thi | Kiểm tra qua đúng ranh giới cần đánh giá |
| PASS được diễn giải thành không có lỗ hổng | Kết luận vượt bằng chứng | Ghi rõ phạm vi và kết hợp phương pháp bổ sung |

## 15. Thực hành thiết kế một bộ positive security test

Với chức năng xuất hóa đơn, xây dựng tối thiểu các ca hợp lệ sau:

1. Người có quyền hoàn tất luồng xác thực và nhận phiên đúng danh tính.
2. Người chỉ đọc xem đúng tài nguyên và tập trường được cấp.
3. Người có quyền xuất tạo và tải bản xuất đúng phạm vi.
4. Danh tính worker xử lý tác vụ hợp lệ bằng quyền được cấp.
5. Thao tác hợp lệ tạo được audit đúng nội dung và thời hạn.
6. Quy trình phục hồi được hỗ trợ đưa dữ liệu và chức năng về trạng thái đáp ứng yêu cầu.

Với mỗi ca, ghi mã yêu cầu, tiêu chí, tiền điều kiện, fixture, hành động, assertion, bằng chứng và giới hạn kết luận. Chỉ ra ca đối ứng hoặc đánh giá khác cần có để phát hiện kiểm soát bị bỏ qua; không gán các kết luận đó cho positive test khi chưa có bằng chứng.

Positive security test có giá trị khi chứng minh người và thành phần hợp lệ thực hiện được đúng việc, bằng đúng quyền, trên đúng dữ liệu và trong các điều kiện bảo vệ đã quy định. Nó là một phần của kiểm chứng yêu cầu bảo mật, cần được đặt cạnh các tình huống bị cấm, điều kiện lỗi và đánh giá thiết kế để tạo kết luận đầy đủ hơn.
