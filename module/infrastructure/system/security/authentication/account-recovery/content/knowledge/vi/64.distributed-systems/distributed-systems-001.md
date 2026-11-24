# Recovery state across services — Trạng thái khôi phục xuyên các dịch vụ

## 1. Một luồng khôi phục không chỉ có một biến trạng thái

Khôi phục tài khoản trong hệ thống phân tán có thể đi qua nhiều dịch vụ: tiếp nhận yêu cầu, xác minh danh tính, đánh giá rủi ro, quản lý phê duyệt, quản lý thông tin xác thực, quản lý phiên và gửi thông báo. Mỗi dịch vụ quan sát một phần của quá trình và có thể xử lý ở một thời điểm khác nhau.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, người dùng có thể cần đặt lại mật khẩu, đăng ký lại MFA, tạo passkey mới hoặc thay thiết bị xác thực. Một kết quả “đã xác minh” ở dịch vụ bằng chứng chưa đồng nghĩa credential đã thay đổi; một kết quả “đã thay credential” cũng chưa chứng minh các phiên cũ đã được vô hiệu hóa theo chính sách.

**Recovery state across services** là cách mô hình hóa, phân quyền sở hữu và phối hợp các trạng thái này để toàn hệ thống thực hiện đúng một hành động khôi phục được phép, ngay cả khi có timeout, sự kiện trùng, xử lý sai thứ tự hoặc dịch vụ tạm thời không hoạt động.

### Ví dụ mở đầu

Một người dùng mất điện thoại MFA. Dịch vụ khôi phục nhận đủ phê duyệt rồi gửi lệnh đăng ký lại MFA đến dịch vụ danh tính. Dịch vụ danh tính đã ghi thay đổi, nhưng phản hồi bị mất. Bộ điều phối gửi lại lệnh; trong lúc đó, dịch vụ phiên chưa xác nhận đã thu hồi các phiên bị ảnh hưởng.

Nếu hệ thống chỉ dùng `recoveryCompleted = true`, nó có thể vừa lặp lại hành động nhạy cảm vừa báo hoàn tất quá sớm. Thiết kế cần biết thay đổi nào đã commit, kết quả nào chưa rõ và điều kiện nào còn chờ.

## 2. Xác định chủ sở hữu cho từng trạng thái

Một bảng quyền sở hữu giúp tránh việc nhiều dịch vụ cùng tự quyết định một sự thật bảo mật.

| Miền trạng thái | Chủ sở hữu minh họa | Thành phần khác có thể giữ gì? |
|---|---|---|
| Yêu cầu và phiên bản quy trình | Dịch vụ khôi phục | Bản chiếu để hiển thị hoặc theo dõi |
| Kết quả xác minh bằng chứng | Dịch vụ xác minh | Tham chiếu và bản chụp được chấp nhận |
| Đánh giá rủi ro | Dịch vụ rủi ro | Kết quả có phiên bản, thời điểm và phạm vi |
| Quyết định phê duyệt | Dịch vụ quản lý phê duyệt | Tham chiếu quyết định và trạng thái quan sát được |
| Credential và thao tác đổi credential | Dịch vụ danh tính | Kết quả operation và phiên bản bảo mật |
| Phiên và trạng thái thu hồi | Dịch vụ phiên hoặc cơ chế phân quyền phiên | Bản chiếu phục vụ theo dõi |
| Giao thông báo | Dịch vụ thông báo | Trạng thái chờ gửi, đã gửi hoặc lỗi |

Đây là cách phân chia minh họa. Hệ thống nhỏ có thể gom nhiều miền trong cùng một dịch vụ để đơn giản hóa tính nguyên tử. Điều quan trọng là mỗi sự thật có nguồn có thẩm quyền rõ ràng và các bản sao không tự trở thành nguồn cấp quyền mới.

Ví dụ, một bản chiếu ghi `APPROVED` ở cổng hỗ trợ có thể đã cũ. Nó không nên đủ để dịch vụ danh tính đổi MFA nếu quyết định gốc đã hết hạn, bị thu hồi hoặc không đúng phiên bản yêu cầu.

Không cần sao chép mọi trạng thái vào một trường tổng hợp rồi cho tất cả dịch vụ tự cập nhật. Cách đó dễ tạo ra những trạng thái không thể giải thích, chẳng hạn một consumer chậm ghi đè `REVOKED` bằng `APPROVED` từ sự kiện cũ.

## 3. Tách trạng thái nghiệp vụ khỏi trạng thái vận chuyển

Một trạng thái nghiệp vụ mô tả điều đã xảy ra với yêu cầu hoặc quyền. Một trạng thái vận chuyển mô tả việc lệnh hay sự kiện được gửi, nhận hoặc thử lại.

| Trạng thái | Ý nghĩa thực sự |
|---|---|
| `EVIDENCE_ACCEPTED` | Một bộ bằng chứng cụ thể được chấp nhận theo điều kiện đã ghi |
| `EXECUTION_AUTHORIZED` | Có quyết định cho phép một hành động trong phạm vi xác định |
| `COMMAND_DISPATCHED` | Lệnh đã được gửi hoặc được đưa vào cơ chế giao |
| `CREDENTIAL_CHANGE_COMMITTED` | Dịch vụ sở hữu credential xác nhận thay đổi đã commit |
| `SESSION_POLICY_PENDING` | Còn điều kiện xử lý phiên chưa được xác nhận |
| `COMPLETED` | Các bất biến hoàn tất đã được đáp ứng |
| `NOTIFICATION_RETRYING` | Thông báo đang được thử gửi lại |

`COMMAND_DISPATCHED` không đồng nghĩa `CREDENTIAL_CHANGE_COMMITTED`. Tương tự, nhận được một message từ broker không chứng minh một transaction nghiệp vụ đã hoàn tất.

Nên lưu kết quả từng bước hoặc các chiều trạng thái riêng thay vì ép mọi thứ thành một chuỗi tuyến tính. Sau khi thay đổi credential thành công nhưng email lỗi, trạng thái bảo mật và trạng thái giao thông báo cần thể hiện khác nhau.

## 4. Các bất biến bảo mật cần phối hợp

Trước khi chọn cơ chế hàng đợi hay kiểu orchestration, cần xác định những điều luôn phải đúng:

1. Hành động thực thi gắn với đúng tenant, tài khoản, yêu cầu và phiên bản nội dung.
2. Bằng chứng, rủi ro và phê duyệt đáp ứng điều kiện của quyết định cấp quyền.
3. Một quyền dùng một lần không tạo ra nhiều thay đổi credential ngoài phạm vi cho phép.
4. Một lệnh cũ không được tiếp tục có hiệu lực chỉ vì consumer xử lý chậm.
5. Thay đổi credential có kết quả bền vững và có thể tra cứu khi mất phản hồi.
6. Chính sách phiên được áp dụng theo yêu cầu trước khi hệ thống công bố mức hoàn tất tương ứng.
7. Thu hồi, hủy hoặc thay đổi phiên bản không bị một sự kiện cũ ghi đè.

Các bất biến có thể có yêu cầu nhất quán khác nhau. Một dashboard chậm cập nhật vài giây có thể chấp nhận được theo thiết kế. Ngược lại, một bản sao cũ dùng để chấp nhận token đã bị thu hồi có thể vi phạm mục tiêu bảo mật.

Không giải quyết cả hai loại bằng một lựa chọn chung “mọi thứ eventual consistency”. Cần chỉ rõ nơi nào chỉ để quan sát và nơi nào được phép đưa ra quyết định cấp quyền.

## 5. Ranh giới giao dịch và điểm quyết định có thẩm quyền

Trong cùng một cơ sở dữ liệu, có thể phối hợp các thay đổi bằng transaction. Giữa những dịch vụ độc lập, một transaction cục bộ không tự bao phủ toàn bộ quy trình.

Giả sử dịch vụ khôi phục đánh dấu quyền đã dùng rồi gọi dịch vụ danh tính. Nếu lời gọi thất bại, có thể có quyền đã tiêu thụ nhưng chưa đổi credential. Nếu làm ngược lại, có thể đổi credential xong mà quyền vẫn còn được xem là chưa dùng. Cần một contract thực thi rõ ràng để xử lý cả hai tình huống.

### Gom phần quyết định nhạy cảm khi phù hợp

Một cách giảm độ phức tạp là để dịch vụ sở hữu credential cũng sở hữu bản ghi thực thi dùng một lần liên quan đến thay đổi đó. Nó có thể kiểm tra quyền đã được cấp, ghi operation, tiêu thụ quyền thực thi và đổi credential trong cùng phạm vi nguyên tử phù hợp.

Điều này không có nghĩa tự chuyển toàn bộ logic bằng chứng sang dịch vụ danh tính. Có thể có một quyết định cấp quyền đã được xác lập trước, với phạm vi, phiên bản, thời hạn và tham chiếu căn cứ rõ ràng.

### Định nghĩa việc cấp quyền trước khác kiểm tra tại thao tác cuối

Cần chọn rõ một trong các ngữ nghĩa phù hợp:

- Quyết định trước đó cấp một quyền thực thi hạn chế có vòng đời riêng; thao tác cuối kiểm tra quyền này và các điều kiện hiện hành được quy định.
- Phê duyệt phải còn được chấp nhận đúng tại thao tác cuối; cơ chế thực thi phải kiểm tra và phối hợp điều kiện đó ở điểm quyết định tương ứng.

Một lần gọi đọc dịch vụ phê duyệt rồi đổi credential ở dịch vụ khác không tự làm hai việc nguyên tử. Quyết định có thể bị thu hồi giữa hai bước. Nếu chính sách đòi hỏi thu hồi có hiệu lực ngay tại điểm thực thi, cần một cơ chế tuần tự hóa, phối hợp hoặc ràng buộc phiên bản đủ mạnh cho yêu cầu đó.

Không tuyên bố đã giải quyết race condition chỉ vì message có chữ ký hoặc chứa `approved = true`. Chữ ký bảo vệ nội dung được cấp, không tự cập nhật trạng thái thu hồi về sau.

## 6. Mô hình dữ liệu cho một operation xuyên dịch vụ

Một operation có thể chứa:

```text
operationId
tenantId
accountId
recoveryRequestId
requestVersion
action
actionPayloadDigest
authorizationReference
authorizationVersion
createdAt
executionDeadline
workflowState
credentialOperationReference
sessionActionReference
lastObservedResults
```

Những định danh cần phân biệt:

| Trường | Mục đích |
|---|---|
| `recoveryRequestId` | Nhận diện một yêu cầu nghiệp vụ |
| `requestVersion` | Ràng buộc nội dung và căn cứ của yêu cầu |
| `operationId` | Nhận diện một hành động thực thi cụ thể |
| `eventId` | Nhận diện một sự kiện được phát |
| `aggregateSequence` | Biểu diễn thứ tự trong một miền trạng thái có nguồn cấp thứ tự rõ ràng |
| `securityEpoch` | Hỗ trợ vô hiệu hóa quyền hoặc phiên theo thiết kế bảo mật |

Không dùng timestamp cho tất cả những mục đích này. Hai sự kiện có thể xảy ra cùng thời điểm hiển thị, trong khi cùng một sự kiện có thể được giao lại nhiều lần.

`operationId` và idempotency key cần được gắn với tenant, người gọi và nội dung hành động. Cùng key nhưng khác tài khoản hoặc khác payload phải được xử lý như xung đột, không trả kết quả thành công của một thao tác không liên quan.

## 7. Lệnh yêu cầu hành động, sự kiện mô tả sự thật

Một lệnh như `ExecuteMfaRecovery` yêu cầu dịch vụ có thẩm quyền thực hiện hành động. Dịch vụ nhận lệnh vẫn phải kiểm tra contract phân quyền và điều kiện hiện tại.

Một sự kiện như `MfaRecoveryCommitted` mô tả việc dịch vụ sở hữu credential đã ghi nhận thành công. Consumer dùng sự kiện này để cập nhật bản chiếu hoặc thực hiện bước tiếp theo; không được coi việc phát lệnh là tương đương sự kiện hoàn tất.

Ví dụ envelope minh họa:

```json
{
  "schemaVersion": 1,
  "eventId": "event-demo-501",
  "eventType": "MFA_RECOVERY_COMMITTED",
  "producer": "identity-service",
  "tenantId": "tenant-demo-12",
  "accountId": "account-demo-742",
  "recoveryRequestId": "recovery-demo-33",
  "requestVersion": 4,
  "operationId": "operation-demo-19",
  "aggregateId": "account-demo-742",
  "aggregateSequence": 18,
  "securityEpoch": 7,
  "occurredAt": "2026-11-24T06:10:00Z"
}
```

Các giá trị là dữ liệu giả. Envelope không chứa OTP, token khôi phục thô, mật khẩu hoặc bí mật MFA.

Consumer cần xác định nguồn phát có thẩm quyền cho loại sự kiện. Một message có `producer = identity-service` trong payload chưa tự chứng minh nó thật sự đến từ dịch vụ đó; quyền xuất bản và kênh truyền cần được kiểm soát phù hợp.

## 8. Outbox và xử lý giao trùng

Một khoảng hở phổ biến là dịch vụ commit thay đổi credential rồi dừng trước khi gửi sự kiện. Dữ liệu nguồn đã đổi nhưng các dịch vụ khác không biết.

Mẫu outbox có thể ghi trong cùng transaction:

```text
Thay đổi credential
    + lưu kết quả operation
    + cập nhật phiên bản bảo mật nếu áp dụng
    + chèn outbox event
    → commit
```

Bộ chuyển tiếp sau đó gửi sự kiện từ outbox. Nếu gặp lỗi hoặc mất xác nhận, nó có thể gửi lại. Vì vậy, consumer cần xử lý giao trùng.

Với một consumer cập nhật cơ sở dữ liệu cục bộ, có thể ghi nhận event đã xử lý và thay đổi nghiệp vụ trong cùng transaction. Nếu cùng `eventId` được nhận lại, consumer trả kết quả phù hợp mà không thực hiện lần nữa.

Outbox không tự bảo đảm mọi tác dụng phụ xảy ra đúng một lần. Gửi email, gọi nhà cung cấp hoặc ghi vào hệ thống khác vẫn cần contract riêng về retry, idempotency và trạng thái chưa xác định.

Không đánh dấu event đã xử lý trước khi tác dụng phụ hoàn tất rồi coi đó là đủ. Nếu đánh dấu trước, có thể mất tác dụng phụ khi ứng dụng dừng; nếu thực hiện trước rồi đánh dấu sau, có thể lặp khi retry. Cần thiết kế theo khả năng của hệ thống đích và chấp nhận rõ giới hạn còn lại.

## 9. Sự kiện sai thứ tự và bản chiếu lỗi thời

Giả sử consumer nhận `ApprovalRevoked` trước `ApprovalGranted` do độ trễ giao khác nhau. Nếu nó chỉ ghi đè trạng thái bằng message nhận cuối, phê duyệt có thể bị xem là có hiệu lực trở lại.

Có thể dùng phiên bản hoặc thứ tự của cùng aggregate để phát hiện sự kiện cũ. Tuy nhiên, cách xử lý cần theo ngữ nghĩa:

- Sự kiện cũ của cùng miền trạng thái có thể không được phép ghi đè trạng thái mới.
- Nếu cần đầy đủ mọi sự kiện để xây bản chiếu, phải phát hiện khoảng trống và đồng bộ lại hoặc chờ phần thiếu.
- Không so sánh sequence của hai dịch vụ độc lập như thể chúng dùng chung một bộ đếm.
- Không bỏ qua một sự kiện thu hồi chỉ vì timestamp của nó cũ hơn timestamp của một sự kiện ở miền khác.

Một bản chiếu nên cho biết phiên bản nguồn hoặc mức cập nhật mà nó đã quan sát. Nếu một thao tác nhạy cảm yêu cầu trạng thái mới hơn mức đó, cần tra cứu nguồn hoặc đi qua cơ chế có thẩm quyền thay vì suy đoán.

Việc giao diện vẫn hiển thị “đang chờ” sau khi thao tác nguồn đã hoàn tất là một vấn đề trải nghiệm và quan sát. Việc chấp nhận một quyền đã bị thu hồi vì bản chiếu chưa cập nhật là một vấn đề cấp quyền. Hai vấn đề có thể cần cơ chế xử lý khác nhau.

## 10. Timeout, retry và kết quả chưa xác định

Timeout nghĩa là bên gọi chưa biết kết quả trong khoảng thời gian chờ, không đồng nghĩa bên nhận chưa làm gì.

Một contract tốt cho lệnh nhạy cảm thường cho phép tra cứu:

```text
GET operation status by:
    tenantId
    accountId
    operationId
```

Việc tra cứu vẫn phải được phân quyền. Biết operation ID không tự cho phép xem dữ liệu của tài khoản khác.

Khi mất phản hồi:

1. Giữ trạng thái chưa xác định hoặc đang đối chiếu ở bên điều phối.
2. Tra cứu dịch vụ sở hữu operation bằng định danh ban đầu.
3. Nếu đã commit, ghi nhận kết quả đó; không cấp thêm một hành động mới.
4. Nếu chưa có kết quả, retry cùng nội dung và cùng cơ chế idempotency theo contract.
5. Nếu có xung đột hoặc không thể xác định, giới hạn các bước tiếp theo và chuyển sang xử lý phù hợp.

Không đánh dấu toàn bộ yêu cầu thất bại rồi tự mở lại token chỉ vì lời gọi đổi MFA timeout. Nếu credential đã đổi, việc mở lại quyền có thể tạo thêm lần thực thi ngoài ý muốn.

Retry cần có giới hạn vận hành và cơ chế quan sát. Hết số lần retry tự động không nên bị hiểu là trạng thái nguồn chắc chắn không thay đổi.

## 11. Thời hạn và thu hồi trong luồng bất đồng bộ

Job được tạo trước hạn không tự giữ chỗ cho quyền thực thi. Dịch vụ có thẩm quyền cần kiểm tra thời hạn tại điểm quyết định theo ngữ nghĩa đã xác định.

Không dùng timestamp từ client hoặc thời điểm message được đưa vào hàng đợi làm thời gian hiện tại. Các dịch vụ cần một chiến lược thời gian nhất quán đủ cho yêu cầu bảo mật và cần biết độ lệch đồng hồ có thể ảnh hưởng biên hết hạn.

Tách các giới hạn:

| Giới hạn | Điều bị giới hạn |
|---|---|
| Hạn yêu cầu | Vòng đời xử lý của hồ sơ khôi phục |
| Độ mới bằng chứng | Khả năng dùng kết quả xác minh cho quyết định |
| Hạn phê duyệt | Khả năng sử dụng quyết định của người duyệt |
| Hạn quyền thực thi | Khả năng thực hiện hành động cụ thể |
| Hạn retry hoặc lease | Cơ chế vận hành của worker |

Lease còn hiệu lực không gia hạn quyền thực thi. Lease hết hạn cũng không chứng minh worker cũ đã dừng. Nếu có nhiều worker, cần cơ chế như kiểm soát phiên bản hoặc fencing ở nơi ghi để lệnh của worker cũ không tiếp tục được chấp nhận ngoài contract.

Khi hủy yêu cầu cạnh tranh với lệnh thực thi, hệ thống phải xác định điểm quyết định nào thắng theo cơ chế tuần tự hóa của miền có thẩm quyền. Một sự kiện hủy gửi sau không thể khiến một thay đổi đã commit trở thành chưa từng xảy ra. Nếu cần vô hiệu hóa kết quả đã cấp, đó là một hành động bảo mật tiếp theo phải được thực hiện và ghi nhận riêng.

## 12. Phiên, cache và điều kiện hoàn tất

Sau khi đổi mật khẩu hoặc đăng ký lại MFA, chính sách có thể yêu cầu thu hồi một tập phiên, tăng phiên bản bảo mật hoặc hạn chế quyền cho tới khi người dùng xác thực lại.

Không thể khẳng định các yêu cầu này đã được đáp ứng chỉ vì dịch vụ danh tính phát một event. Cần định nghĩa cơ chế thực thi và căn cứ xác nhận. Một ACK của broker chỉ chứng minh bước vận chuyển tương ứng, không chứng minh mọi điểm truy cập đã từ chối phiên cũ.

Các thiết kế có thể khác nhau:

- Điểm truy cập kiểm tra phiên bản bảo mật có thẩm quyền cho những hành động cần bảo vệ ngay.
- Dịch vụ phiên cập nhật trạng thái thu hồi và phản hồi operation trước khi bộ điều phối mở bước tiếp theo.
- Một cơ chế cache có thời hạn và quy tắc kiểm tra lại được chấp nhận rõ theo mức rủi ro.

Nếu yêu cầu phải chặn phiên cũ ngay mà một thành phần vẫn chấp nhận cache cũ không giới hạn phù hợp, thiết kế chưa đáp ứng yêu cầu đó. Không dùng nhãn “đồng bộ cuối cùng” để che đi khoảng truy cập còn tồn tại.

`COMPLETED` cần được định nghĩa bằng các bất biến, ví dụ credential đã đổi đúng phạm vi, quyền đã tiêu thụ một lần và chính sách phiên bắt buộc đã được áp dụng. Thông báo có thể tiếp tục ở trạng thái chờ gửi nếu chính sách cho phép, nhưng trạng thái đó phải hiển thị riêng.

## 13. Bù trừ và phục hồi tiến về phía trước

Các bước khôi phục không phải lúc nào cũng có một thao tác đảo ngược an toàn. Sau khi đổi mật khẩu, việc khôi phục mật khẩu cũ có thể mở lại quyền cho kẻ tấn công. Sau khi thu hồi phiên, đưa phiên cũ trở lại hoạt động chỉ để làm trạng thái giống trước đó cũng có thể gây hại.

Vì vậy, khi một bước sau thất bại, thường cần đưa hệ thống tới một trạng thái an toàn mới thay vì tua ngược mọi bước:

```text
Credential đã đổi
    + chưa xác nhận xử lý phiên
    → giữ trạng thái đang hoàn tất bảo mật
    → tiếp tục xử lý phiên bằng operation có định danh
    → áp dụng giới hạn truy cập cần thiết
    → công bố hoàn tất khi đạt điều kiện
```

Nếu bằng chứng bị xác định không hợp lệ sau khi hành động đã commit, cần xử lý như một sự kiện bảo mật mới: thu hồi quyền hoặc yếu tố liên quan theo chính sách, giới hạn truy cập và yêu cầu xác minh lại khi cần. Không sửa bản ghi lịch sử để giả vờ hành động chưa xảy ra.

Saga hoặc bộ điều phối có thể theo dõi các bước và hành động bù trừ. Nó không tự biến mọi tác động thành có thể đảo ngược, cũng không thay thế phân quyền tại dịch vụ thực thi.

## 14. Đối chiếu trạng thái và quan sát hệ thống

Ngoài luồng sự kiện, hệ thống cần cơ chế phát hiện trạng thái mắc kẹt hoặc lệch giữa các dịch vụ. Một tác vụ đối chiếu có thể tìm operation quá lâu chưa rõ kết quả, tra cứu nguồn có thẩm quyền và cập nhật bản chiếu theo contract.

Ví dụ cần xem xét:

- Bộ điều phối ghi “đang thực thi” nhưng dịch vụ danh tính đã có kết quả commit.
- Outbox còn tồn đọng khiến dịch vụ phiên chưa nhận yêu cầu xử lý.
- Một bản chiếu thiếu sequence hoặc đang giữ phiên bản cũ.
- Có quyền thực thi đã tiêu thụ nhưng thiếu liên kết tới operation cần điều tra.
- Một thông báo đang chờ gửi cho quyền đã hết hạn hoặc bị thu hồi.

Đối chiếu không được tự tạo một phê duyệt mới hoặc bỏ qua bằng chứng chỉ để làm cho trạng thái các bảng khớp nhau. Nó phải dùng các sự thật đã ghi nhận và contract của từng miền.

Nhật ký cần nối được request, operation, command và event, đồng thời giữ tenant, tài khoản và nguồn phát. Không ghi token thô hoặc bí mật xác thực. Các chỉ số về độ trễ, retry, trạng thái chưa xác định và lỗi đối chiếu giúp xác định nơi cần xử lý, nhưng không thay thế căn cứ nghiệp vụ.

Nếu không thể kết luận an toàn từ dữ liệu hiện có, giữ trạng thái rõ ràng để điều phối tiếp. Không chuyển sang `COMPLETED` chỉ để loại một cảnh báo vận hành.

## 15. Các tình huống thiết kế cần được làm rõ

Những tình huống sau minh họa hành vi mong muốn, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi phù hợp |
|---|---|
| Credential đã commit nhưng phản hồi bị mất | Tra cứu cùng operation và tránh thay đổi lần hai |
| Event được giao hai lần | Consumer xử lý theo định danh, không lặp tác dụng nghiệp vụ ngoài contract |
| Event thu hồi đến trước event cấp quyền | Không cho event cũ làm quyền có hiệu lực trở lại |
| Bản chiếu còn ghi phê duyệt hợp lệ | Không dùng nó như nguồn cấp quyền nếu không đáp ứng độ mới và contract |
| Job chạy sau hạn quyền thực thi | Kiểm tra tại điểm quyết định và từ chối quyền đã hết hạn |
| Worker cũ tiếp tục sau khi mất lease | Cơ chế ở nơi ghi ngăn lệnh không còn hợp lệ |
| Hủy yêu cầu cạnh tranh với thực thi | Có điểm quyết định rõ, không suy diễn hủy đã đảo được commit |
| Đổi MFA thành công nhưng xử lý phiên còn chờ | Giữ trạng thái phù hợp, tiếp tục hoàn tất các điều kiện bảo mật |
| Email gửi thất bại sau thay credential | Retry thông báo mà không phục hồi credential hoặc mở lại token |
| Không thể xác định kết quả ở dịch vụ nguồn | Giữ trạng thái chưa rõ và giới hạn bước tiếp theo theo chính sách |
| Cùng idempotency key nhưng khác payload | Từ chối xung đột, không trả nhầm kết quả operation khác |

Những lỗi cốt lõi là để nhiều dịch vụ cùng sở hữu một quyết định, coi timeout là thất bại chắc chắn, coi gửi lệnh là đã thực thi và dùng trạng thái sao chép chậm để cấp quyền nhạy cảm.

Trạng thái khôi phục xuyên dịch vụ cần được tổ chức quanh nguồn có thẩm quyền, bất biến bảo mật và kết quả thực thi có thể tra cứu. Sự kiện, retry và bản chiếu giúp phối hợp hệ thống, nhưng quyền đặt lại mật khẩu, MFA hoặc passkey chỉ nên được sử dụng khi đúng phạm vi, đúng điều kiện và tại một điểm quyết định được thiết kế rõ ràng.
