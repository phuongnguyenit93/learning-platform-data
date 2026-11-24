# Partial failure handling — Xử lý lỗi từng phần trong khôi phục tài khoản

## 1. Lỗi từng phần khác một yêu cầu thất bại hoàn toàn

Một quy trình khôi phục tài khoản có thể phối hợp dịch vụ xác minh danh tính, đánh giá rủi ro, phê duyệt, quản lý credential, quản lý phiên và gửi thông báo. Một thành phần có thể thành công trong khi thành phần khác chưa xử lý, mất kết nối hoặc không phản hồi.

**Partial failure** là tình huống chỉ một phần các bước hoặc tác động của quy trình đạt kết quả mong muốn. **Partial failure handling** là cách nhận diện trạng thái thực tế, giới hạn rủi ro và tiếp tục hoặc kết thúc quy trình mà không tạo thêm thay đổi trái phép.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, lỗi từng phần có thể ảnh hưởng trực tiếp đến mật khẩu, MFA, passkey, token dùng một lần và phiên đăng nhập. Vì vậy, hệ thống không thể chỉ bắt exception rồi thử chạy lại toàn bộ luồng.

### Ví dụ mở đầu

Một người dùng mất thiết bị MFA. Dịch vụ danh tính đã ghi nhận thay đổi yếu tố xác thực, nhưng phản hồi về bộ điều phối bị mất. Trong cùng thời gian, dịch vụ phiên chưa xác nhận đã xử lý các phiên cũ và dịch vụ email đang ngừng hoạt động.

Ba sự thật cần được giữ riêng:

- Thay đổi MFA có thể đã commit.
- Điều kiện xử lý phiên có thể còn chờ.
- Thông báo chưa được giao không chứng minh việc đổi MFA thất bại.

Nếu bộ điều phối đánh dấu mọi thứ là thất bại và mở lại token, nó có thể cho phép thực thi lần nữa. Nếu đánh dấu hoàn tất ngay, nó có thể che giấu một điều kiện bảo mật chưa đạt.

## 2. Phân loại lỗi theo điều đã biết về tác động

Một lỗi mạng hoặc mã phản hồi kỹ thuật không luôn cho biết tác động nghiệp vụ. Cần phân biệt ít nhất các nhóm sau:

| Nhóm | Điều đã biết | Hướng xử lý |
|---|---|---|
| Chưa bắt đầu tác động | Có căn cứ rằng lệnh chưa được chấp nhận hoặc bước chưa chạy | Có thể thử lại nếu quyền và thời hạn còn phù hợp |
| Thất bại chắc chắn không có tác động | Nguồn thực thi xác nhận transaction đã hủy hoặc hành động chưa thực hiện | Giữ kết quả và xác định có được retry hay không |
| Tác động đã commit | Nguồn có thẩm quyền ghi nhận thành công | Không lặp hành động; xử lý các bước còn thiếu |
| Kết quả chưa xác định | Không biết tác động đã xảy ra hay chưa | Tra cứu hoặc đối chiếu trước khi quyết định thực thi tiếp |
| Thành công từng phần | Một số bước đã commit, một số bước còn chờ hoặc lỗi | Tiếp tục có điều phối hoặc bù trừ theo từng bước |

Timeout thường thuộc nhóm chưa biết kết quả từ góc nhìn bên gọi. Dịch vụ nhận có thể đã hoàn tất rồi không gửi được phản hồi. Không đồng nhất timeout với “chưa có tác động”.

Lỗi xác thực, bằng chứng không đáp ứng chính sách và dịch vụ xác minh không phản hồi cũng khác nhau. Không thể suy ra người dùng giả mạo chỉ vì nhà cung cấp xác minh tạm thời không hoạt động; đồng thời, sự cố đó không cung cấp kết quả xác minh cần thiết để cấp quyền.

## 3. Xác định điều kiện an toàn trước khi chọn cách khắc phục

Chiến lược xử lý cần dựa vào các bất biến của hành động khôi phục:

1. Chỉ đúng tenant, tài khoản, yêu cầu và phiên bản được phép chịu tác động.
2. Một quyền dùng một lần không được thực hiện thêm vì retry hoặc mất phản hồi.
3. Không cấp quyền mới khi thiếu điều kiện xác minh, rủi ro hoặc phê duyệt bắt buộc.
4. Credential đã bị thu hồi hoặc thay thế không tự có hiệu lực trở lại do rollback.
5. Các phiên và quyền bị ảnh hưởng được xử lý theo chính sách trước khi công bố mức hoàn tất tương ứng.
6. Trạng thái chưa xác định được biểu diễn trung thực, không bị chuyển thành thành công hoặc thất bại theo phỏng đoán.

Khi một điều kiện cần cho hành động nhạy cảm không thể xác minh, có thể cần giữ yêu cầu chờ hoặc hạn chế bước tiếp theo. Điều này không có nghĩa phải ngừng mọi chức năng của mọi tài khoản.

Giới hạn nên theo phạm vi rủi ro: thao tác đăng ký lại MFA, tài khoản đang tranh chấp hoặc tập phiên bị ảnh hưởng. Một lỗi gửi email đơn lẻ không nên tự biến thành lệnh khóa toàn hệ thống.

Nếu có chế độ xử lý suy giảm, các điều kiện của nó phải được xác định trước theo chính sách. Không tự tạo một đường bỏ qua MFA hoặc bằng chứng vì hệ thống đang cần phục hồi nhanh.

## 4. Mô hình hóa kết quả từng bước và trạng thái toàn quy trình

Một cờ `failed` duy nhất không đủ cho luồng phân tán. Nên lưu trạng thái theo bước, định danh thao tác và kết quả có thể đối chiếu.

```text
recoveryOperationId
tenantId
accountId
recoveryRequestId
requestVersion
action
authorizationReference
workflowState
steps[]:
    stepId
    ownerService
    state
    externalOperationReference
    attemptCount
    lastObservedAt
    lastErrorCode
```

Các trạng thái bước có thể gồm:

```text
NOT_STARTED
IN_PROGRESS
SUCCEEDED
FAILED_NO_EFFECT
OUTCOME_UNKNOWN
COMPENSATION_PENDING
REQUIRES_INTERVENTION
```

Đây là tập trạng thái minh họa, không phải một chuỗi mà mọi bước phải đi qua. `FAILED_NO_EFFECT` chỉ được dùng khi có căn cứ phù hợp; không đặt trạng thái này chỉ từ một timeout phía client.

Trạng thái toàn quy trình có thể tổng hợp từ các bước, nhưng phải giữ ý nghĩa nghiệp vụ. Ví dụ:

| Kết quả quan sát được | Cách mô tả phù hợp |
|---|---|
| Chưa đổi credential, đang chờ kết quả xác minh | Chờ điều kiện đầu vào |
| Chưa biết dịch vụ danh tính đã commit hay chưa | Đang đối chiếu kết quả thực thi |
| Credential đã đổi, còn điều kiện phiên bắt buộc | Đang hoàn tất các bước bảo mật |
| Đủ điều kiện bảo mật, email còn chờ | Hoàn tất hành động, thông báo đang xử lý nếu chính sách cho phép |
| Không thể tự giải quyết một bất nhất | Cần can thiệp có thẩm quyền |

Không cho phép một lỗi thông báo ghi đè kết quả credential đã thành công. Cũng không dùng trạng thái toàn quy trình để che mất một bước bảo mật còn chờ.

## 5. Phân biệt bước bảo mật bắt buộc với tác vụ có thể chờ

Mức độ phụ thuộc của mỗi bước phải được định nghĩa theo hành động và chính sách.

| Bước | Vai trò có thể có | Khi lỗi cần xem xét |
|---|---|---|
| Xác minh danh tính | Điều kiện cấp quyền | Chưa được coi là đáp ứng nếu chưa có kết quả được chấp nhận |
| Đánh giá rủi ro | Điều kiện cho hành động nhạy cảm | Giữ chờ hoặc dùng nhánh suy giảm đã được phê duyệt rõ |
| Tiêu thụ grant và đổi credential | Tác động bảo mật chính | Cần kết quả bền vững và tính dùng một lần |
| Xử lý phiên | Có thể là điều kiện bắt buộc trước khi mở truy cập | Xác nhận cơ chế vô hiệu hóa hoặc giữ giới hạn thích hợp |
| Giao thông báo | Có thể tách khỏi commit hành động | Retry riêng; không tự đổi lại credential |
| Cập nhật dashboard | Bản chiếu quan sát | Có thể đồng bộ lại từ nguồn có thẩm quyền |

Không mặc định mọi email đều là bước phụ. Nếu một thử thách qua email là điều kiện xác minh hoặc thông báo là điều kiện cụ thể của chính sách thực thi, lỗi ở bước đó phải được xử lý theo đúng vai trò.

Tương tự, việc một hệ thống phân tích hoặc dashboard chậm cập nhật không nhất thiết phải chặn hành động nếu nó không phải nguồn quyết định. Cần xác định đúng phụ thuộc để vừa giữ an toàn vừa tránh làm gián đoạn không cần thiết.

## 6. Giảm khoảng hở bằng ranh giới giao dịch phù hợp

Trong cùng miền dữ liệu, nên phối hợp những thay đổi không được phép tách rời. Ví dụ, dịch vụ sở hữu credential có thể commit cùng nhau:

```text
Tiêu thụ quyền thực thi
    + đổi credential đúng phạm vi
    + lưu kết quả operation
    + cập nhật phiên bản bảo mật nếu áp dụng
    + ghi outbox event
    → commit
```

Nếu transaction này thất bại và nguồn xác nhận đã rollback, các thay đổi thuộc transaction không được xem là đã commit. Nếu transaction đã commit nhưng phản hồi bị mất, operation vẫn cho phép tra cứu kết quả.

Những thành phần ở cơ sở dữ liệu hoặc dịch vụ khác không tự nằm trong transaction đó. Outbox giúp phát sự kiện từ trạng thái đã lưu, nhưng không tự bảo đảm dịch vụ phiên hoặc nhà cung cấp thông báo đã thực hiện xong.

Nếu quyền và credential được quản lý ở hai dịch vụ, cần một contract cấp quyền và thực thi rõ ràng. Hai lời gọi lần lượt không tự có tính nguyên tử. Phải biết khi nào quyền được chốt, cách xử lý thu hồi cạnh tranh và cách tìm kết quả khi mất phản hồi.

Một bước kiểm tra từ xa rồi ghi ở nơi khác có thể có khoảng hở thay đổi trạng thái. Nếu chính sách đòi hỏi không được thực thi sau thu hồi tại điểm quyết định, cơ chế phối hợp phải thật sự đáp ứng yêu cầu đó, thay vì chỉ dựa vào việc vừa đọc được `approved = true`.

## 7. Quy trình xử lý một lỗi từng phần

Một trình tự thực tế có thể gồm:

### Bước 1: Ghi nhận lỗi và bảo toàn định danh

Giữ operation ID, step ID, tenant, tài khoản và phiên bản yêu cầu. Retry không được tạo ý định nghiệp vụ mới chỉ để vượt trạng thái lỗi.

Không ghi mật khẩu, OTP hoặc token thô vào báo cáo lỗi. Dữ liệu đối chiếu cần đủ để tìm operation mà không tạo thêm bản sao bí mật.

### Bước 2: Xác định phần đã biết và phần chưa biết

Tra cứu kết quả ở dịch vụ sở hữu tác động, không chỉ đọc trạng thái phía bộ điều phối. Nếu chưa có căn cứ, giữ `OUTCOME_UNKNOWN` ở bên quan sát thay vì đoán.

### Bước 3: Áp dụng giới hạn tạm thời khi cần

Ngăn các bước có thể làm tăng quyền hoặc tạo thêm credential trong khi trạng thái chưa rõ. Nếu cần hạn chế truy cập tài khoản, phải có cơ chế thực thi ở các điểm truy cập thực tế; đổi một trường trạng thái mà mọi consumer bỏ qua không tạo ra giới hạn an toàn.

### Bước 4: Chọn cách tiếp tục theo từng bước

Có thể retry một bước chưa có tác động, tiếp tục bước sau của một hành động đã commit, bù trừ một tài nguyên tạm hoặc chuyển sang can thiệp có thẩm quyền. Không dùng một quy tắc “lỗi thì chạy lại từ đầu” cho mọi loại tác động.

### Bước 5: Kiểm tra các điều kiện hiện hành

Trước hành động mới, kiểm tra thời hạn, phiên bản, phạm vi và trạng thái thu hồi theo contract. Việc đối chiếu một kết quả cũ và việc thực hiện một hành động mới có yêu cầu khác nhau.

### Bước 6: Ghi kết quả và thông báo đúng mức hoàn tất

Lưu căn cứ quyết định tiếp tục hoặc dừng, kết quả từng bước và điều kiện còn chờ. Phản hồi cho người dùng phải phù hợp với trạng thái thực tế, không làm họ tưởng credential chưa đổi nếu nó đã đổi.

## 8. Retry có kiểm soát và tính dùng một lần

Retry phù hợp khi lỗi có thể phục hồi và dịch vụ đích có contract hỗ trợ. Cần giữ cùng định danh lệnh hoặc định danh bước, cùng nội dung được phép và cùng phạm vi.

Một luồng minh họa:

```text
Nhận lỗi hoặc timeout
    → tra cứu operation bằng định danh ban đầu
    → nếu đã thành công: nhận lại trạng thái, không thực thi thêm
    → nếu chắc chắn chưa có tác động: cân nhắc retry còn hợp lệ
    → nếu chưa rõ: tiếp tục đối chiếu hoặc chuyển xử lý
```

Khoảng lùi, phân tán thời điểm retry và giới hạn số tác vụ đồng thời giúp tránh làm dịch vụ đang lỗi quá tải. Các giới hạn này phục vụ vận hành, không thay thế kiểm tra quyền khôi phục.

Một grant đã dùng không được chuyển về chưa dùng để retry thuận tiện. Nếu hai lệnh khác key cùng tham chiếu một grant, tính dùng một lần vẫn phải ngăn hành động thứ hai.

Hết cửa sổ retry tự động không chứng minh lệnh thất bại không có tác động. Trạng thái chưa rõ vẫn cần được giữ và điều phối xử lý.

Nếu dịch vụ đích không có chống trùng và cũng không cho tra cứu kết quả, việc retry một tác dụng phụ có thể gây lặp. Cần thay đổi cách tích hợp hoặc đưa trường hợp đó vào quy trình can thiệp, thay vì hứa tính thực thi một lần mà hệ thống không bảo đảm.

## 9. Bù trừ không đồng nghĩa phục hồi mọi trạng thái cũ

Một số tác động có thể đảo hoặc vô hiệu hóa tương đối rõ, như hủy một quyền tạm chưa dùng hoặc xóa tài nguyên staging do operation tạo. Những tác động khác không nên đảo máy móc.

| Tác động đã xảy ra | Cách xử lý cần cân nhắc | Điều nguy hiểm |
|---|---|---|
| Mật khẩu đã đổi | Hoàn tất chính sách phiên, kiểm tra căn cứ hoặc mở luồng xử lý sự cố | Tự phục hồi mật khẩu cũ vì email gửi lỗi |
| Phiên đã thu hồi | Giữ thu hồi và cho đăng nhập mới theo điều kiện | Kích hoạt lại phiên cũ để làm trạng thái giống trước |
| Grant đã dùng | Giữ lịch sử tiêu thụ, đối chiếu operation | Mở lại grant vì mất phản hồi |
| Yếu tố mới bị xác định không hợp lệ | Vô hiệu hóa theo chính sách, xác minh lại khi cần | Xóa lịch sử thay đổi như thể chưa từng thực thi |
| Thông báo đã gửi | Gửi đính chính nếu cần và hạn chế quyền trong liên kết | Giả định có thể thu hồi mọi bản sao email |
| Tài nguyên tạm chưa sử dụng | Thu hồi hoặc xử lý theo kế hoạch có nguồn gốc | Xóa theo tiêu chí quá rộng ảnh hưởng operation khác |

Trong nhiều trường hợp, hướng an toàn là tiếp tục đưa hệ thống tới một trạng thái mới đã được xác minh, thay vì tua ngược. Ví dụ, credential đã đổi nhưng xử lý phiên còn chờ thì tiếp tục hoàn tất xử lý phiên, không quay lại credential cũ.

Nếu nghi ngờ người yêu cầu là kẻ tấn công, không tiếp tục cấp quyền chỉ để hoàn thành quy trình. Cần chuyển sang nhánh bảo mật phù hợp, giữ các bằng chứng và kiểm soát những quyền đã phát sinh.

## 10. Hủy yêu cầu, hết hạn và lỗi xảy ra đồng thời

Một job có thể chờ lâu tới khi phê duyệt hoặc grant hết hạn. Việc job được tạo trong thời hạn không tự cho phép thực thi sau hạn. Dịch vụ có thẩm quyền cần kiểm tra thời gian tại điểm quyết định theo ngữ nghĩa đã định nghĩa.

Nếu kết quả đã commit trước đó, trả lại trạng thái operation là quan sát hành động cũ, không phải thực hiện lại sau hạn. Đường tra cứu vẫn cần phân quyền và giới hạn dữ liệu phù hợp.

Hủy yêu cầu có thể cạnh tranh với thực thi:

```text
Nhánh A: hủy được chấp nhận trước điểm thực thi
    → hành động mới không được thực hiện

Nhánh B: hành động đã commit trước khi hủy có hiệu lực
    → giữ sự thật đã commit
    → đánh giá thao tác thu hồi hoặc xử lý tiếp nếu cần
```

Hệ thống phải có cơ chế phân xử tại miền có thẩm quyền, không dựa vào thứ tự event đến dashboard. Một message hủy đến muộn không tự đảo được thay đổi credential đã commit.

Lease của worker cũng là thời hạn khác. Worker cũ có thể vẫn chạy sau khi lease hết hạn; cần kiểm soát phiên bản sở hữu hoặc cơ chế tương đương ở nơi thực thi để ngăn lệnh cũ không còn hợp lệ.

## 11. Phiên đăng nhập là một phần của xử lý lỗi bảo mật

Đổi credential và kiểm soát phiên cần được phối hợp theo chính sách. Nếu token hoặc phiên cũ vẫn có thể được chấp nhận sau thay đổi, việc báo hoàn tất quá sớm có thể gây hiểu nhầm về mức bảo vệ đã đạt.

Cần xác định rõ căn cứ cho trạng thái xử lý phiên:

- Dịch vụ sở hữu phiên đã commit trạng thái thu hồi nào?
- Các điểm truy cập kiểm tra nguồn trạng thái hay một phiên bản bảo mật như thế nào?
- Cache có thể chậm tới mức nào theo contract được chấp nhận?
- Hành động nhạy cảm có yêu cầu kiểm tra mới hơn không?

Một ACK của broker không chứng minh phiên đã bị chặn. Một event đã phát cũng không chứng minh mọi dịch vụ đã áp dụng. Nếu chính sách đòi hỏi chặn ngay, phải có đường thực thi đáp ứng yêu cầu đó hoặc giữ giới hạn thích hợp.

Nếu không thể hoàn tất bước phiên ngay, hệ thống có thể giữ trạng thái đang hoàn tất bảo mật và tiếp tục retry có định danh. Không tự mở một phiên đầy đủ cho người yêu cầu để “bù” cho lỗi xử lý phiên cũ.

Giới hạn tạm thời phải có phạm vi, người chịu trách nhiệm và điều kiện giải phóng rõ ràng. Không để tài khoản rơi vào trạng thái khóa không ai biết cách xử lý chỉ vì một bước nền đã hết retry.

## 12. Hàng đợi lỗi, đối chiếu và can thiệp thủ công

Những lệnh lỗi kéo dài có thể được chuyển sang vùng chờ xử lý hoặc hàng đợi lỗi. Mục đích là giữ khả năng điều tra và điều phối tiếp, không phải tạo đường phát lại không giới hạn.

Trước khi phát lại, cần kiểm tra:

1. Operation có còn đúng tenant, tài khoản và phiên bản không?
2. Dịch vụ đích đã có kết quả nào chưa?
3. Quyền cho một hành động chưa thực hiện có còn hợp lệ không?
4. Payload hoặc lỗi có chứa dữ liệu nhạy cảm cần được bảo vệ không?
5. Người hoặc công cụ phát lại có thẩm quyền cho phạm vi này không?

Phát lại giữ định danh nghiệp vụ và contract idempotency. Không sửa deadline, tenant hoặc trạng thái grant để lệnh cũ chạy được. Nếu cần một hành động mới, nó phải có quyết định và quyền mới theo chính sách.

Một tác vụ đối chiếu có thể tìm các operation mắc kẹt, tra cứu nguồn và cập nhật trạng thái quan sát. Nó không được tự bịa một kết quả xác minh hoặc phê duyệt để làm các bảng khớp nhau.

Can thiệp thủ công cũng cần được ghi nhận theo từng người và hành động. “Đã sửa bằng tay” không đủ để giải thích một tài khoản được mở lại hay một yếu tố xác thực bị thay đổi.

## 13. Ví dụ xử lý một lần khôi phục MFA bị lỗi từng phần

Giả sử operation `operation-demo-19` được phép đăng ký lại MFA và chính sách yêu cầu xử lý tập phiên bị ảnh hưởng trước khi công bố hoàn tất.

| Mốc | Sự kiện | Trạng thái cần giữ |
|---|---|---|
| T1 | Dịch vụ danh tính nhận lệnh đúng phạm vi | Đang thực thi |
| T2 | Credential, tiêu thụ grant, operation và outbox cùng commit | Hành động chính đã thành công tại nguồn |
| T3 | Phản hồi về bộ điều phối bị mất | Bộ điều phối chưa rõ kết quả, không được mở lại grant |
| T4 | Dịch vụ phiên tạm thời chưa xử lý được | Còn điều kiện bảo mật chờ hoàn tất |
| T5 | Bộ điều phối tra cứu cùng operation | Nhận lại kết quả đã commit, không đổi MFA lần nữa |
| T6 | Bước phiên được retry theo cùng định danh | Đối chiếu hoặc thực thi phần còn thiếu |
| T7 | Có căn cứ chính sách phiên đã được áp dụng | Có thể đạt điều kiện hoàn tất bảo mật |
| T8 | Email vẫn chờ gửi | Theo dõi riêng trạng thái thông báo nếu chính sách cho phép |

Nếu đến T6 xuất hiện cảnh báo bằng chứng bị giả mạo, không chỉ tiếp tục theo kế hoạch cũ. Hệ thống cần đánh giá trạng thái mới và áp dụng nhánh xử lý sự cố, chẳng hạn vô hiệu hóa yếu tố hoặc quyền liên quan theo chính sách.

Nếu bước phiên chưa thể xác nhận, trạng thái chưa hoàn tất phải còn được nhìn thấy. Việc operation chính đã commit giúp biết sự thật, nhưng không tự làm mọi phụ thuộc bảo mật thành công.

## 14. Phản hồi cho người dùng và khả năng quan sát

Người dùng cần hiểu liệu họ nên chờ, đăng nhập lại hay thực hiện một bước xác minh mới. Một phản hồi “lỗi, hãy thử lại” cho mọi trường hợp có thể khiến họ tạo nhiều yêu cầu hoặc thay đổi nội dung trong khi thao tác cũ đã commit.

Phản hồi phù hợp có thể nêu rằng yêu cầu đang được xác nhận kết quả hoặc đang hoàn tất bước bảo mật, đồng thời cung cấp cách kiểm tra trạng thái được phân quyền. Không cần tiết lộ topology nội bộ hoặc dữ liệu phát hiện gian lận cho người chưa được xác minh.

Endpoint tra cứu operation cần kiểm soát người gọi, tenant, tài khoản và mức dữ liệu trả về. Biết operation ID không tự cho phép xem hồ sơ khôi phục hoặc nhận lại một bí mật.

Những chỉ số hữu ích gồm:

- Số operation có kết quả chưa xác định và thời gian tồn tại của chúng.
- Số trường hợp credential đã commit nhưng điều kiện phiên còn chờ.
- Độ trễ outbox, số lần giao lại và lỗi đối chiếu.
- Lệnh bị phát lại khi quyền đã hết hạn hoặc phiên bản đã đổi.
- Bước bù trừ thất bại và số trường hợp cần can thiệp.

Nhật ký nên liên kết request, operation, step, attempt và nguồn kết quả, nhưng không chứa token thô, mật khẩu hoặc recovery code. Một cảnh báo được đóng phải có căn cứ xử lý, không chỉ là thay đổi nhãn trạng thái.

## 15. Các tình huống thiết kế cần được làm rõ

Những tình huống sau mô tả hành vi mong muốn, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi phù hợp |
|---|---|
| Dịch vụ xác minh không phản hồi | Giữ trạng thái chưa có kết quả, không suy ra xác minh thành công |
| Thay credential commit nhưng mất phản hồi | Tra cứu operation, không thực hiện thêm lần nữa |
| Transaction chính được xác nhận rollback | Không công bố tác động đã commit; retry chỉ khi quyền còn phù hợp |
| Dịch vụ phiên chưa xác nhận điều kiện bắt buộc | Giữ trạng thái còn chờ và giới hạn cần thiết |
| Email lỗi sau khi credential đã đổi | Retry thông báo riêng, không khôi phục credential cũ |
| Grant hết hạn trong lúc job chờ | Không dùng thời điểm tạo job để bỏ qua hạn thực thi |
| Hủy yêu cầu đến sau khi hành động đã commit | Giữ lịch sử và xử lý thu hồi hoặc bước tiếp theo theo chính sách |
| Worker cũ tiếp tục sau khi mất lease | Nơi thực thi ngăn lệnh không còn hợp lệ |
| Hàng đợi lỗi được phát lại thủ công | Kiểm tra quyền, kết quả nguồn và phiên bản trước khi chạy |
| Không còn đủ căn cứ xác định tác động bên ngoài | Giữ trạng thái chưa rõ, không tự đánh dấu không có tác động |
| Có cảnh báo giả mạo sau thành công từng phần | Chuyển sang xử lý bảo mật mới, không hoàn tất máy móc |

Những lỗi cốt lõi là coi timeout như rollback chắc chắn, thử lại toàn bộ quy trình với key mới, mở lại quyền đã dùng và đánh dấu hoàn tất khi các điều kiện bảo mật còn thiếu.

Xử lý lỗi từng phần an toàn cần bảo toàn sự thật đã commit, xác định rõ phần chưa biết và chọn hành động tiếp theo theo từng tác động. Một luồng khôi phục mật khẩu, MFA hoặc passkey phải tiếp tục hướng tới trạng thái an toàn có thể giải thích, thay vì chỉ cố làm mọi dịch vụ hiển thị cùng một nhãn thành công.
