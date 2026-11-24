# Recovery actor recording

## 1. Ghi nhận actor để trả lời đúng câu hỏi “ai đã làm?”

Trong khôi phục tài khoản, tài khoản bị thay đổi không nhất thiết là danh tính của người gửi yêu cầu. Một người nhập email của Lan có thể là Lan, một người nhầm địa chỉ hoặc kẻ đang tìm cách chiếm tài khoản. Nếu nhật ký ngay lập tức ghi người gửi là Lan, hệ thống đã biến một lời khai thành kết luận danh tính.

Recovery actor recording là việc ghi nhận chủ thể tham gia từng hành động khôi phục, nguồn xác định chủ thể và những giới hạn của kết luận đó. Mục tiêu là dựng lại diễn biến mà không làm người đọc hiểu quá mức bằng chứng hệ thống thực sự có.

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-attributes) hướng dẫn ghi đủ thông tin về thời điểm, nơi xảy ra, chủ thể và hành động của sự kiện. Trong luồng khôi phục, phần “chủ thể” cần bao gồm cả trường hợp chưa biết người yêu cầu là ai.

Ví dụ sai:

```json
{
  "eventType": "RecoveryRequested",
  "actorUserId": "account_lan"
}
```

Nếu giá trị được suy ra chỉ từ email người gọi nhập, bản ghi này không chứng minh Lan đã yêu cầu khôi phục.

Một mô tả thận trọng hơn là: “một người yêu cầu chưa xác thực đã gửi yêu cầu liên quan đến tài khoản này”. Khả năng liên kết yêu cầu với tài khoản và khả năng xác định danh tính người gửi là hai việc riêng.

## 2. Phân biệt actor, subject và bên thực thi

Một sự kiện có thể liên quan nhiều danh tính. Không nên ép tất cả vào một trường `userId`.

| Vai trò trong bản ghi | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Actor | Chủ thể trực tiếp khởi tạo hành động đang được ghi | Người yêu cầu, nhân viên hỗ trợ hoặc tác vụ tự động |
| Subject hoặc target | Tài khoản hay đối tượng bị tác động | Tài khoản đang được thay MFA |
| Approver | Chủ thể phê duyệt theo quy trình | Nhân viên thứ hai chấp thuận thao tác ngoại lệ |
| Executed by | Danh tính kỹ thuật thực thi thay đổi | Dịch vụ recovery xử lý command |
| Recorded by | Thành phần phát sinh hoặc thu nhận bản ghi | Ứng dụng hoặc bộ thu audit |

Một người dùng có thể tự khởi tạo thay đổi trên tài khoản của mình. Khi đó actor và subject có thể cùng trỏ tới một danh tính tài khoản, nhưng sự trùng nhau cần có cơ sở xác thực phù hợp.

Trong một thao tác hỗ trợ, actor có thể là nhân viên hỗ trợ và subject là tài khoản khách hàng. Nếu dịch vụ ghi actor bằng ID khách hàng chỉ vì đang thao tác “thay mặt khách”, trách nhiệm của nhân viên sẽ biến mất khỏi nhật ký.

Tương tự, khi một dịch vụ thực thi command đã được phê duyệt, danh tính dịch vụ không nên che mất người khởi tạo. Ngược lại, không được ghi một người dùng như thể chính họ trực tiếp thực thi các bước tự động mà không nêu thành phần xử lý.

Tên trường cụ thể có thể khác nhau. Điều quan trọng là schema diễn đạt rõ vai trò và được sử dụng nhất quán.

## 3. Không gán danh tính vượt quá mức đã biết

Trạng thái của người yêu cầu thay đổi theo từng bước. Nhật ký phải phản ánh thông tin có thẩm quyền tại thời điểm sự kiện xảy ra.

| Tình huống | Điều có thể ghi nhận | Điều chưa được suy ra |
| --- | --- | --- |
| Người gọi nhập email | Có một tương tác yêu cầu khôi phục với dữ liệu khai báo | Người gọi là chủ email hoặc chủ tài khoản |
| Người gọi trình token chưa được kiểm tra | Có một lần trình bằng chứng | Token hợp lệ hoặc người gọi có quyền thay credential |
| Một mã dùng một lần được chấp nhận | Một điều kiện của quy trình đã đạt trong phạm vi được định nghĩa | Mọi yêu cầu khôi phục đều hoàn tất |
| Chính sách khôi phục chấp nhận đủ bằng chứng | Người yêu cầu có quyền thực hiện các hành động khôi phục cụ thể | Người đó có toàn bộ quyền của một session đăng nhập thông thường |
| Một principal đã được xác thực | Hệ thống đã xác nhận credential hoặc ngữ cảnh xác thực tương ứng | Có bằng chứng chắc chắn về cá nhân đang cầm thiết bị |
| Nhân viên hỗ trợ được xác thực | Hành động gắn với principal của nhân viên | Nhân viên được phép thực hiện mọi thao tác trên mọi tài khoản |

Có thể cấp một `recoveryActorRef` riêng cho tương tác khôi phục để liên kết các sự kiện khi chưa có principal đăng nhập. Đây là định danh tham chiếu do máy chủ quản lý, không phải token cấp quyền.

Không mặc định cùng IP, cookie hay trình duyệt nghĩa là cùng một con người. Tín hiệu đó có thể giúp đối chiếu nhưng không đủ để kết luận danh tính.

Nếu người yêu cầu được xác minh ở bước sau, giữ nguyên ý nghĩa của các bản ghi trước. Có thể thêm sự kiện liên kết hoặc đánh giá mới, nêu rõ từ thời điểm nào và bằng căn cứ nào quan hệ được chấp nhận. Không sửa ngược lịch sử để mọi hành động ban đầu đều mang nhãn “đã xác thực”.

## 4. Lấy thông tin actor từ nguồn có thẩm quyền

Thông tin trong payload do người gọi gửi có thể là dữ liệu khai báo, không phải bằng chứng actor.

Những giá trị như `actorId`, `role=admin`, `approvedBy` hoặc `onBehalfOf` không được tin chỉ vì xuất hiện trong JSON, query hoặc header. Máy chủ cần lấy danh tính từ security context đã được kiểm tra và đối chiếu quyền tại nơi xử lý hành động.

Các nguồn có thể dùng tùy kiến trúc:

- Principal người dùng đã được tầng xác thực của ứng dụng kiểm tra.
- Ngữ cảnh phiên khôi phục được máy chủ quản lý, kèm phạm vi hành động được cấp.
- Principal nhân viên từ hệ thống hỗ trợ có kiểm soát truy cập.
- Danh tính workload đã được dịch vụ đích xác thực.
- Bản ghi phê duyệt và ủy quyền đã được xác nhận, còn phù hợp với thao tác.

Các header chuyển tiếp danh tính chỉ có giá trị trong một ranh giới tin cậy được thiết lập và kiểm soát. Không mặc định mọi header mang tên nội bộ đều do gateway đáng tin cậy tạo ra.

Xác thực kết nối giữa hai dịch vụ cho biết bên gọi kỹ thuật là ai; nó không tự chứng minh mọi danh tính người dùng mà bên gọi đính kèm. Nếu cần truyền danh tính khởi tạo, phải có hợp đồng kiểm tra nguồn, tính toàn vẹn, mục đích và phạm vi sử dụng của ngữ cảnh đó.

Theo [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#validate-the-permissions-on-every-request), quyền cần được kiểm tra cho từng request. Bản ghi actor đã xác thực không thay thế quyết định cho phép hành động cụ thể trên tài khoản cụ thể.

Không suy ra mức đảm bảo xác thực chỉ từ tên phương thức hoặc một cờ giao diện. Nếu ghi mức đảm bảo, phải lấy từ cơ chế đánh giá được định nghĩa và có thể đối chiếu.

## 5. Thông tin nào giúp diễn giải actor?

Schema dưới đây là thiết kế minh họa cho bài học, không phải định dạng bắt buộc của một tiêu chuẩn.

| Nhóm dữ liệu | Trường minh họa | Mục đích |
| --- | --- | --- |
| Phân loại chủ thể | `actor.kind` | Phân biệt người yêu cầu, người dùng đã xác thực, nhân viên và máy |
| Định danh | `actor.principalRef`, `actor.recoveryActorRef` | Tham chiếu danh tính đã biết hoặc tương tác chưa gắn principal |
| Không gian danh tính | `actor.issuerRef`, `actor.tenantRef` | Tránh nhầm ID giữa nhà phát hành hoặc tenant |
| Nguồn nhận diện | `actor.identitySource` | Cho biết nguồn có thẩm quyền của thông tin actor |
| Ngữ cảnh xác thực | `actor.authenticationState`, `authContextRef` | Diễn giải actor đã đáp ứng điều kiện gì tại thời điểm đó |
| Quyền hành động | `authorization.decisionRef`, `policyVersion` | Đối chiếu quyết định cho phép hoặc từ chối |
| Đối tượng bị tác động | `subject.accountRef`, `subject.tenantRef` | Tách tài khoản mục tiêu khỏi người thực hiện |
| Liên kết nghiệp vụ | `recoveryRequestRef`, `interactionRef` | Nối các sự kiện trong cùng quá trình |
| Trách nhiệm kỹ thuật | `executedBy`, `recordedBy` | Tách người khởi tạo khỏi dịch vụ thực thi và nơi ghi |

ID cần có phạm vi rõ ràng. Chuỗi `1234` có thể là khách hàng ở tenant này nhưng là nhân viên ở hệ thống khác. Dùng tham chiếu ổn định và không tái sử dụng theo cách khiến lịch sử gắn sang người mới.

Tên hiển thị, email và vai trò hiện tại có thể thay đổi. Khi cần biết quyền của actor tại thời điểm hành động, lưu tham chiếu quyết định hoặc dữ liệu tóm tắt được kiểm soát tại thời điểm đó, thay vì luôn tra vai trò hiện tại rồi coi đó là sự thật lịch sử.

Không cần sao chép toàn bộ profile, danh sách quyền hoặc credential vào log. Chọn thông tin đủ để điều tra và giữ phần chi tiết cần bảo vệ trong kho phù hợp.

Nếu chưa biết principal, để giá trị không có một cách có chủ đích và ghi trạng thái chưa xác thực. Không điền ID tài khoản mục tiêu chỉ để tránh một trường null.

## 6. Ví dụ người yêu cầu có quyền khôi phục giới hạn

Giả sử người yêu cầu mất MFA và đã đáp ứng các điều kiện cần thiết để thay phương thức đó. Hệ thống cấp quyền giới hạn cho đúng request, chưa tạo session có toàn quyền.

```json
{
  "eventId": "evt_example_801",
  "eventType": "RecoveryFactorReplacementCommitted",
  "occurredAt": "2026-11-24T09:10:00Z",
  "recordedAt": "2026-11-24T09:10:01Z",
  "actor": {
    "kind": "RECOVERY_CLAIMANT",
    "recoveryActorRef": "ra_example_17",
    "principalRef": null,
    "authenticationState": "RECOVERY_AUTHORIZED",
    "identitySource": "RECOVERY_WORKFLOW",
    "authContextRef": "rac_example_31"
  },
  "subject": {
    "tenantRef": "tenant_example_2",
    "accountRef": "acct_example_44"
  },
  "authorization": {
    "decisionRef": "decision_example_98",
    "policyVersion": "mfa-recovery-v3",
    "allowedAction": "REPLACE_MFA"
  },
  "recoveryRequestRef": "rr_example_61",
  "executedBy": {
    "kind": "SERVICE",
    "principalRef": "svc_recovery"
  },
  "outcome": "COMMITTED"
}
```

Các giá trị chỉ mang tính minh họa. `RECOVERY_AUTHORIZED` diễn đạt quyền giới hạn theo workflow trong ví dụ, không phải một mức đảm bảo xác thực chuẩn hóa.

Bản ghi nói rằng một tương tác được cấp quyền thay MFA đã tạo thay đổi trên tài khoản mục tiêu. Nó không khẳng định chỉ từ bằng chứng này rằng đã xác minh danh tính pháp lý của một cá nhân hoặc người đó được phép làm mọi việc khác.

`authContextRef` và `decisionRef` phải dẫn tới dữ liệu mà thành phần có thẩm quyền đã tạo. Không chấp nhận chuỗi do client tự khai rồi coi đó là chứng cứ.

Nếu thao tác bị từ chối, ghi kết quả từ chối và căn cứ phù hợp. Không dùng loại sự kiện có chữ `Committed` cho một lần thử thất bại.

## 7. Hỗ trợ thủ công, phê duyệt và hành động thay mặt

Một quy trình hỗ trợ có thể có ba người hoặc hệ thống tham gia:

```text
Nhân viên A đề xuất thay MFA cho tài khoản C
  -> nhân viên B phê duyệt theo chính sách
  -> dịch vụ recovery thực thi khi điều kiện còn đúng
```

Cần ghi riêng hành động đề xuất, hành động phê duyệt và hành động thực thi, cùng các tham chiếu liên kết. Một ticket hỗ trợ giải thích mục đích công việc, nhưng không tự chứng minh rằng B thực sự đã phê duyệt.

Ở sự kiện đề xuất, actor là A và subject là C. Ở sự kiện phê duyệt, actor là B. Ở sự kiện thực thi tự động, có thể ghi dịch vụ là actor trực tiếp và giữ `initiatedBy`, `approvalRef` hoặc quan hệ nguyên nhân để truy về A và B.

Cách biểu diễn nào cũng phải giữ được chuỗi trách nhiệm. Không đổi actor thành C trong cả ba sự kiện vì nhân viên đang “làm thay khách hàng”.

Nếu có chế độ impersonation, cần lưu cả principal nhân viên thực tế lẫn ngữ cảnh tài khoản mà hệ thống đang đại diện. Không chỉ giữ effective user rồi làm mất danh tính nhân viên.

Với tài khoản dùng chung hoặc tài khoản khẩn cấp, khả năng quy trách nhiệm cá nhân thường yếu hơn. Ghi rõ loại principal và tham chiếu quy trình sử dụng; không bịa một cá nhân khi dữ liệu hiện có chỉ chứng minh tài khoản dùng chung đã được dùng.

Một engine tự động chấp nhận bằng chứng không phải người phê duyệt thủ công. Ghi đúng nguồn quyết định, phiên bản chính sách và principal kỹ thuật tương ứng.

## 8. Duy trì actor qua xử lý bất đồng bộ

Một request khôi phục có thể được gửi tới hàng đợi rồi mới thực thi. Nếu chỉ dựa vào biến ngữ cảnh của request HTTP ban đầu, worker có thể mất danh tính khởi tạo hoặc ghi nhầm principal của tác vụ trước.

Cần tạo ngữ cảnh actor được kiểm soát tại lúc chấp nhận command và lưu hoặc truyền cùng tham chiếu có bảo vệ. Khi xử lý:

1. Xác thực nguồn command và kiểm tra cấu trúc ngữ cảnh.
2. Đối chiếu request, tài khoản, tenant và phạm vi hành động.
3. Kiểm tra các điều kiện cấp quyền còn phải đúng tại thời điểm thực thi.
4. Ghi danh tính dịch vụ thực thi riêng với thông tin người khởi tạo.
5. Liên kết sự kiện bằng định danh command, request và nguyên nhân.

Ngữ cảnh actor lịch sử không có nghĩa quyền được cấp sẽ tồn tại mãi. Nếu quyền nhân viên bị thu hồi, request đã hết hạn hoặc tài khoản đã đổi trạng thái, chính sách thực thi phải quyết định lại theo hợp đồng của thao tác.

Một lần retry nên giữ quan hệ với cùng command, nhưng có thể có một lần thực thi kỹ thuật riêng. Không ghi thành nhiều lần thay MFA thành công nếu thực tế chỉ có một thay đổi đã commit.

Nếu callback đến từ nhà cung cấp xác minh danh tính, actor kỹ thuật của callback là phía tích hợp đã được kiểm tra. Kết luận xác minh là dữ liệu cần đối chiếu với giao dịch dự kiến, không phải quyền để nhà cung cấp tùy ý thay credential.

## 9. Ghi đúng actor mà không tạo kho bí mật mới

Dữ liệu actor giúp điều tra nhưng có thể chứa thông tin cá nhân. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude) cảnh báo việc ghi trực tiếp mật khẩu, access token, giá trị định danh session và dữ liệu nhạy cảm. Thiết kế dưới đây ưu tiên tham chiếu nội bộ thay cho sao chép credential.

Không ghi:

- OTP hoặc mã khôi phục đã trình, kể cả khi mã bị từ chối.
- Token khôi phục, bearer token, cookie hoặc URL chứa bí mật.
- Seed TOTP, private key, QR thiết lập phương thức.
- Ảnh giấy tờ hoặc toàn bộ kết quả xác minh danh tính trong trường actor.
- Toàn bộ request hoặc security context chỉ để tiện debug.

Nếu cần nối với session, dùng tham chiếu audit không có khả năng xác thực hoặc cơ chế định danh được thiết kế riêng. Không tạo “tham chiếu” bằng cách lưu lại chính session token.

Không mặc định hash một mã ngắn là đủ an toàn để ghi log. Không gian giá trị nhỏ có thể bị dò; thường chỉ cần tham chiếu bản ghi challenge và kết quả kiểm tra, không cần lưu mã hoặc bản biến đổi của mã.

Định danh liên hệ khai báo, IP và user agent đều có giới hạn tin cậy. Chỉ lưu khi có mục đích rõ ràng, giới hạn độ dài và bảo vệ quyền truy cập. Không dùng email người gọi nhập làm nhãn actor đã xác thực.

Trường chuỗi cần được serialize theo cấu trúc và xử lý ký tự điều khiển để không cho người gọi chèn bản ghi giả. Nếu một thuộc tính bổ sung không hợp lệ, giữ phần sự kiện an toàn và đánh dấu lỗi thuộc tính; không thay principal đáng tin bằng chuỗi do client cung cấp.

## 10. Bảo vệ ý nghĩa và tính toàn vẹn của bản ghi

Actor, action, subject và outcome cần gắn với cùng sự kiện nghiệp vụ. Có thể lưu sự kiện audit hoặc ý định phát audit trong cùng transaction với thay đổi nhạy cảm khi chúng thuộc cùng phạm vi lưu trữ.

Khi thay đổi rollback, không để lại kết luận “đã thay phương thức thành công”. Một bản ghi về lần thử vẫn có thể cần tồn tại, nhưng phải nêu đó là lần thử hoặc lỗi, không phải kết quả đã commit.

Phân biệt `occurredAt` và `recordedAt` giúp người đọc hiểu độ trễ thu thập. Thứ tự nhận ở bộ thu không tự chứng minh thứ tự nghiệp vụ; cần tham chiếu request, phiên bản hoặc quan hệ nguyên nhân phù hợp.

Những biện pháp bảo vệ có thể gồm:

- Tách quyền ghi ứng dụng khỏi quyền sửa hoặc xóa lịch sử.
- Hạn chế quyền tra cứu và xuất dữ liệu actor.
- Ghi dấu vết các lần truy cập hoặc xuất audit nhạy cảm.
- Theo dõi lỗi thu thập, mất liên kết và sự kiện trùng.
- Đặt thời hạn lưu và quản lý dữ liệu liên kết theo mục đích sử dụng.
- Có cách bổ sung đính chính rõ nguồn thay vì âm thầm sửa actor trong sự kiện cũ.

Không gọi nhật ký là bằng chứng không thể chối bỏ chỉ vì đã ghi một user ID. Principal có thể bị chiếm, dịch vụ phát log có thể có lỗi và thông tin nguồn có thể thiếu. Kết luận điều tra cần xét các giới hạn đó.

Nếu thành phần audit gặp lỗi, phải có chính sách cho từng loại hành động, cơ chế lưu bền hoặc cảnh báo phù hợp. Không tự bỏ yêu cầu kiểm soát của thao tác nhạy cảm, và cũng không biến mọi lỗi của hệ thống thu log thành việc khóa toàn bộ dịch vụ mà chưa có thiết kế.

## 11. Tình huống minh họa

### Một người nhập email của người khác

Hệ thống ghi một người yêu cầu chưa xác thực, tương tác và dữ liệu mục tiêu được phép lưu nội bộ. Nó không ghi chủ tài khoản là actor. Phản hồi công khai vẫn không được tiết lộ thông tin nội bộ giúp dò tài khoản.

### Người dùng còn passkey nhưng mất mật khẩu

Nếu một principal đã được xác thực bằng phương thức còn dùng được, ghi ngữ cảnh xác thực có thẩm quyền và quyền cụ thể cho thao tác đặt lại mật khẩu. Không suy ra quyền chỉ từ việc account ID trong request trùng tên người dùng.

### Nhân viên xử lý ticket khôi phục MFA

Actor của thao tác hỗ trợ là principal nhân viên. Subject là tài khoản khách hàng; ticket, quyết định quyền và phê duyệt là những quan hệ riêng. Người đọc có thể truy ai đề xuất, ai chấp thuận và dịch vụ nào thực thi.

### Điều tra cho thấy principal bị chiếm

Giữ nguyên sự kiện rằng principal đó đã được hệ thống chấp nhận tại thời điểm hành động, rồi bổ sung kết quả điều tra có nguồn và thời gian. Không đổi lịch sử thành kết luận cá nhân mà hệ thống chưa từng chứng minh.

Ghi nhận recovery actor có giá trị khi mỗi bản ghi nói rõ điều hệ thống biết về người thực hiện, cách biết điều đó và phạm vi quyền của họ. Sự tách biệt giữa lời khai, principal, tài khoản mục tiêu và dịch vụ thực thi giúp dựng lại luồng khôi phục mà không làm sai trách nhiệm.