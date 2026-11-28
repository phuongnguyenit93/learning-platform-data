# Token revocation — thu hồi token trong hệ thống IAM

**Token revocation** là việc làm mất hiệu lực sử dụng của token trước thời hạn tự hết hiệu lực của nó, theo phạm vi và chính sách mà hệ thống hỗ trợ. Đây là cơ chế quan trọng khi người dùng mất thiết bị, rút quyền truy cập của ứng dụng, tài khoản bị xâm nhập hoặc một workload không còn được phép hoạt động.

Điểm khó không chỉ là ghi một cờ `revoked` ở Authorization Server. Các API đang nhận token cũng phải có cách biết hoặc chịu tác động của quyết định đó. Một token vẫn đúng chữ ký có thể đã bị thu hồi; một token đã bị xóa khỏi trình duyệt có thể vẫn còn trong tay người khác.

Bài học phân biệt phạm vi thu hồi, cơ chế thực thi với opaque token và JWT, cùng những tình huống cần kiểm chứng để đảm bảo quyền truy cập thực sự bị chặn.

## 1. Thu hồi token khác với những thao tác nào?

Trong IAM, nhiều thao tác cùng liên quan tới việc ngừng truy cập nhưng không có hiệu quả giống nhau:

| Thao tác | Điều trực tiếp thay đổi | Điều không được tự suy ra |
|---|---|---|
| Token hết hạn | Token vượt cửa sổ thời gian được chấp nhận | Đã có quyết định thu hồi sớm |
| Xóa token phía client | Client không còn giữ bản sao đó | Các bản sao bị đánh cắp đã mất hiệu lực |
| Thu hồi access token | Token truy cập cụ thể bị vô hiệu theo cơ chế thực thi | Refresh token và mọi phiên khác cũng bị thu hồi |
| Thu hồi refresh token | Credential dùng để xin token mới không còn được chấp nhận | Mọi access token đã cấp đều dừng ngay tại mọi API |
| Logout ứng dụng | Phiên tại ứng dụng được kết thúc theo thiết kế | Phiên SSO và token của ứng dụng khác đều đã dừng |
| Khóa tài khoản | Trạng thái tài khoản thay đổi | Mọi JWT đang lưu hành tự cập nhật trạng thái |
| Đổi khóa ký | Khóa dùng để ký hoặc xác minh thay đổi | Đã thu hồi đúng một token hay một thiết bị |

Ví dụ, nhân viên báo mất điện thoại. Việc xóa cookie trong một trình duyệt khác không xử lý được refresh token đang nằm trên điện thoại mất. Ngược lại, thu hồi một refresh token của điện thoại cũng không nhất thiết phải làm mọi thiết bị hợp lệ của nhân viên đăng xuất, nếu chính sách chỉ yêu cầu ngừng phiên bị mất.

Trước khi triển khai, phải xác định rõ đối tượng cần ngừng truy cập và thời điểm phải ngừng có hiệu lực, thay vì dùng một nhãn chung “đã logout”.

## 2. Access token và refresh token có vai trò khác nhau

Access token được sử dụng tại resource server để truy cập tài nguyên. Refresh token được gửi tới Authorization Server để xin access token mới, không phải credential dùng gọi API nghiệp vụ. Sự phân biệt này được định nghĩa trong [RFC 6749, mục 1.4–1.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.5).

Giả sử ứng dụng có:

```text
Refresh token R1
    |
    +---- xin access token A1 -> gọi API
    |
    +---- xin access token A2 -> gọi API
```

Nếu chỉ chặn A1, R1 còn hợp lệ có thể tiếp tục xin A3. Nếu chỉ chặn R1, khả năng xin token mới bị ngắt, nhưng A1 hoặc A2 còn thời hạn vẫn cần được xử lý tại API theo kiến trúc thu hồi của hệ thống.

Đây là hai mục tiêu liên quan nhưng độc lập về mặt thực thi:

1. **Ngừng cấp thêm quyền truy cập qua credential hiện có.** Ví dụ, từ chối refresh token hoặc hủy grant của ứng dụng.
2. **Ngừng chấp nhận quyền truy cập đã phát hành.** Ví dụ, API kiểm tra trạng thái token, denylist hoặc một phiên bản bảo mật hiện hành.

Phạm vi lan sang token cùng grant phụ thuộc chính sách và khả năng sản phẩm. Không viết logic ứng dụng với giả định mọi nhà cung cấp đều thu hồi dây chuyền giống nhau.

## 3. Chọn đúng phạm vi thu hồi

Một hệ thống có thể cung cấp nhiều mức thu hồi. Bảng sau mô tả các lựa chọn thiết kế, không phải danh sách endpoint bắt buộc của mọi Authorization Server.

| Phạm vi | Ví dụ sử dụng | Quan hệ cần theo dõi |
|---|---|---|
| Một token | Một access token bị lộ riêng lẻ | Định danh token hoặc dấu băm của token |
| Một phiên/thiết bị | Mất điện thoại, dừng một lần đăng nhập | Phiên, client, chủ thể và token liên quan |
| Một refresh-token family | Phát hiện dùng lại token đã được rotate | Chuỗi quan hệ giữa các refresh token |
| Một grant của ứng dụng | Người dùng rút quyền đã cấp cho ứng dụng | Chủ thể, client, grant và các token phát sinh |
| Toàn bộ phiên/quyền của tài khoản | Tài khoản bị chiếm quyền hoặc nghỉ việc | Các grant, credential, phiên và token của tài khoản |
| Một workload/client | Dịch vụ bị xâm nhập | Credential của workload, quyền cấp token và token đang tồn tại |

Định danh phải được đặt trong đúng ngữ cảnh issuer, tenant và client. Không dùng một `sub` đơn lẻ để xóa hoặc khóa dữ liệu của nhiều hệ thống phát hành khác nhau.

Đối với workload dùng client credentials, thu hồi access token hiện tại chưa đủ nếu credential của client vẫn có thể xin token mới. Phải đánh giá cả khóa/chứng thư/secret hoặc quan hệ federation đang cho workload quyền nhận token.

## 4. OAuth token revocation endpoint

[RFC 7009, mục 2](https://www.rfc-editor.org/rfc/rfc7009.html#section-2) chuẩn hóa yêu cầu thu hồi qua HTTPS `POST`, dùng form có `token` và có thể thêm `token_type_hint`. Authorization Server kiểm tra client và quan hệ của token với client. Server hỗ trợ thu hồi refresh token; hỗ trợ access token được khuyến nghị.

```http
POST /oauth/revoke HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic DEMO_CLIENT_AUTHENTICATION

token=DEMO_REFRESH_TOKEN&token_type_hint=refresh_token
```

Đường dẫn và các chuỗi `DEMO_...` chỉ minh họa, không phải credential hay cấu hình thực. Cách client xác thực phải theo đăng ký của nó; public client không được giả lập confidential client bằng một secret nhúng trong ứng dụng.

Những điểm cần nhớ về phản hồi của RFC 7009:

- HTTP `200` áp dụng khi thu hồi thành công hoặc token không hợp lệ.
- `token_type_hint` chỉ là gợi ý tra cứu; hint sai không chứng minh token sai loại.
- `unsupported_token_type` có thể báo server không hỗ trợ thu hồi loại token được đưa vào.
- HTTP `503` không xác nhận đã thu hồi; client phải coi token có thể vẫn tồn tại.

HTTP `200` không phải bằng chứng rằng mọi cache tại mọi API đã đồng bộ. Client phải ngừng dùng token đã gửi thu hồi, còn hệ thống cần kiểm chứng hiệu lực ở nơi thực thi quyền truy cập.

Một thao tác quản trị “thu hồi mọi phiên của người dùng” không đồng nhất với giao thức client thu hồi một token. Nếu hệ thống có API quản trị rộng hơn, nó cần quyền quản trị, kiểm toán và phạm vi riêng.

## 5. Vì sao JWT tự xác minh không tự biết đã bị thu hồi?

Một API có thể xác minh JWT hoàn toàn cục bộ bằng khóa công khai và các điều kiện như issuer, audience, thời gian, loại token. Khi JWT được tạo, claims và chữ ký của nó không tự thay đổi theo trạng thái mới ở Authorization Server.

Ví dụ:

```text
09:00  Cấp JWT A1, thời hạn tới 09:05
09:01  Nhận quyết định thu hồi
09:02  API kiểm tra cục bộ: chữ ký đúng, audience đúng, chưa hết hạn
09:05  A1 vượt mốc hết hạn theo chính sách kiểm tra thời gian
```

Nếu API không kiểm tra thêm trạng thái động, nó không có dữ liệu để phân biệt A1 bị thu hồi lúc 09:01 với một token tương tự chưa bị thu hồi. Chỉ ghi trạng thái tại Authorization Server không truyền thông tin đó vào bộ xác minh cục bộ.

Trong ví dụ này, chỉ dựa vào hết hạn sẽ để lại gần bốn phút từ thời điểm thu hồi tới mốc `exp`, có thể thêm dung sai thời gian mà API cho phép. Đây là giới hạn kiến trúc cần công khai trong yêu cầu vận hành, không thể giải quyết bằng cách sửa một claim trong bản sao JWT ở server.

`jti` là định danh JWT, còn `exp` là mốc hết hạn theo [RFC 7519, mục 4.1.4 và 4.1.7](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.7). Có `jti` không tự tạo denylist, không tự thông báo thu hồi và cũng không khiến bearer token trở thành token dùng một lần.

## 6. Các cách để API thực thi quyết định thu hồi

### 6.1. Kiểm tra trạng thái qua introspection

Resource server có thể hỏi Authorization Server về trạng thái token qua introspection. Phản hồi `active: false` biểu thị token không còn được coi là hoạt động trong ngữ cảnh introspection. Cơ chế này áp dụng được cho opaque token và cũng có thể dùng với token có cấu trúc nếu Authorization Server hỗ trợ. [Nguồn: RFC 7662, mục 2.2 và 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-2.2).

```json
{
  "active": false
}
```

Introspection không có nghĩa API bỏ mọi kiểm tra còn lại: khi token hoạt động, API vẫn cần áp dụng điều kiện tài nguyên và chính sách phân quyền. Authorization Server cũng cần thực sự kiểm tra trạng thái thu hồi; chỉ parse token rồi trả claims sẽ không mang lại hiệu quả này.

Nếu cache kết quả `active: true`, token đã thu hồi có thể còn được nhận trong thời gian cache. RFC 7662 yêu cầu không cache quá `exp` nếu phản hồi có trường đó. Thời gian cache càng dài càng giảm độ mới của quyết định.

### 6.2. Denylist cho token đã thu hồi

Trong thiết kế denylist, API kiểm tra token có nằm trong tập bị từ chối không. Một khóa tra cứu có thể kết hợp issuer với `jti`, hoặc dùng dấu băm của toàn token theo thiết kế. Không lưu bearer token nguyên văn vào log hoặc dùng nó làm dữ liệu dễ lộ khi chỉ cần một định danh tra cứu.

Ví dụ bản ghi khái niệm:

```text
issuer:           https://login.example.com/
tokenId:          access-1042-a1
state:            REVOKED
retainUntil:      hết cửa sổ API còn có thể chấp nhận token
reason:           DEVICE_LOST
```

Đây là mô hình dữ liệu tự thiết kế, không phải schema OAuth chuẩn. API chỉ dùng claims sau xác minh để tra cứu. Nếu chọn định danh từ claims, hợp đồng phải yêu cầu chúng có mặt và không xung đột trong phạm vi áp dụng.

Không xóa bản ghi denylist chỉ vì đã qua một TTL ngắn tùy ý. Phải giữ đủ lâu để token không thể còn được chấp nhận ở bất kỳ node nào chịu chính sách đó, có tính tới dung sai đồng hồ và thời hạn tối đa đã cấu hình.

### 6.3. Kiểm tra trạng thái phiên hoặc phiên bản bảo mật

Một lựa chọn khác là quản lý trạng thái theo phiên, grant hoặc tài khoản. Ví dụ, token chứa claim tùy biến `session_version`, còn kho trạng thái lưu phiên bản hiện hành.

```text
Token đã cấp:       session_version = 7
Sau khi thu hồi:    phiên bản hiện hành = 8
API đối chiếu:      7 != 8 -> từ chối
```

`session_version` ở đây là ví dụ claim nội bộ, không phải claim bắt buộc trong OAuth/JWT. Cơ chế chỉ có tác dụng nếu API thực sự đối chiếu với trạng thái đủ mới. Chỉ thêm phiên bản vào token rồi kiểm tra chữ ký cục bộ không tạo ra thu hồi.

Phiên bản theo tài khoản có phạm vi rộng; phiên bản theo từng phiên có thể nhắm một thiết bị. Hệ thống cần chọn đúng mức để tránh vô tình ngắt mọi thiết bị khi chỉ muốn dừng một phiên.

### 6.4. Access token ngắn hạn kết hợp ngừng refresh

Hệ thống có thể giới hạn access token bằng thời hạn ngắn và ngừng cấp token mới sau khi thu hồi refresh token hoặc grant. Thiết kế này giảm trạng thái cần tra cứu tại API, nhưng không phải thu hồi access token tức thời.

| Cách tiếp cận | Lợi ích chính | Chi phí hoặc giới hạn |
|---|---|---|
| Introspection | Đọc trạng thái do Authorization Server cung cấp | Phụ thuộc kết nối, tải và chính sách cache |
| Denylist | Chặn token cụ thể | Cần phân phối, lưu giữ và tra cứu trạng thái |
| Trạng thái phiên/phiên bản | Thu hồi theo phiên, grant hoặc tài khoản | Cần định nghĩa phạm vi và đảm bảo dữ liệu đủ mới |
| Token ngắn hạn, dừng refresh | Giới hạn thời gian token tồn tại | Token cũ có thể dùng tới hết cửa sổ chấp nhận |

Các cơ chế có thể kết hợp. Ví dụ, API đọc dữ liệu thông thường chấp nhận một cửa sổ thu hồi ngắn, còn thao tác thay đổi quyền quản trị yêu cầu trạng thái mới hơn. Đó phải là quyết định được thiết kế và kiểm chứng, không phải hành vi ngầm do cache.

## 7. Refresh-token rotation và phát hiện dùng lại

Rotation phát hành refresh token mới khi refresh thành công và vô hiệu token cũ. Authorization Server giữ quan hệ giữa các token để phát hiện token cũ bị sử dụng lại. Với public client, [RFC 9700, mục 2.2.2 và 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14) yêu cầu refresh token được ràng buộc bên gửi hoặc dùng rotation nhằm phát hiện replay.

```text
R1 --refresh thành công--> R2
R1 trở thành token cũ không còn hợp lệ

Sau đó lại có yêu cầu dùng R1:
    -> phát hiện reuse
    -> xử lý chuỗi/grant liên quan theo chính sách bảo vệ
    -> buộc bên hợp lệ xin lại quyền khi cần
```

Phát hiện reuse không tự cho biết người gửi nào là kẻ tấn công. Việc bảo vệ chuỗi token có thể khiến client hợp lệ cũng phải xác thực/cấp quyền lại. Rotation cũng không tự thu hồi mọi access token đã cấp từ chuỗi đó; phạm vi thực thi tại API vẫn cần cơ chế đã chọn.

Client phải điều phối các lần refresh đồng thời. Hai tab hoặc hai request cùng dùng R1 có thể gây xung đột và kích hoạt xử lý reuse. Không khắc phục bằng cách cho phép token cũ dùng lại vô hạn. Nếu sản phẩm có chính sách xử lý race hoặc thời gian dung sai, phải đánh giá tác động tới phát hiện đánh cắp và kiểm thử đúng chính sách đó.

Việc đổi mật khẩu hoặc logout có thể là tín hiệu để hệ thống thu hồi refresh token, nhưng mức lan truyền vẫn phải được cấu hình và xác nhận. Không mặc định sự kiện đó đã xử lý mọi token và mọi phiên.

## 8. Logout, phiên SSO và thu hồi quyền

Trong một ứng dụng dùng OIDC, thường có ít nhất ba lớp trạng thái khác nhau: phiên tại ứng dụng, phiên đăng nhập tại nhà cung cấp danh tính và token/grant cho phép ứng dụng truy cập API.

[OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) định nghĩa việc Relying Party yêu cầu OpenID Provider đăng xuất người dùng. Đây là luồng quản lý phiên, khác với yêu cầu OAuth thu hồi token.

Ví dụ “đăng xuất thiết bị này” có thể cần hủy phiên ứng dụng và thu hồi chuỗi refresh token gắn thiết bị. Ví dụ “ngắt quyền ứng dụng kế toán” có thể cần hủy grant của client kế toán, dù người dùng vẫn được giữ phiên SSO để dùng ứng dụng khác.

ID Token mô tả sự kiện xác thực theo hợp đồng OIDC; nó không phải access token để gọi API nghiệp vụ. Thu hồi token truy cập không tự xóa được các phiên ứng dụng từng được tạo từ một lần đăng nhập hợp lệ. Nếu mục tiêu là buộc đăng xuất các phiên đó, phải có cơ chế tác động tới chúng.

Đối với người nghỉ việc, quy trình cần xem xét đồng thời tài khoản, credential, quyền nhận token, grant, phiên và quyền tại ứng dụng đích. API không kiểm tra trạng thái tài khoản động có thể vẫn nhận JWT cũ trong cửa sổ cho phép, dù bước khóa tài khoản ở hệ thống trung tâm đã thành công.

## 9. Thu hồi là một luồng phân tán có độ trễ

Trong hệ thống nhiều instance, quyết định cần đi từ nguồn trạng thái tới mọi nơi thực thi. Những nơi này có thể gồm gateway, API, cache introspection, cache phiên và worker xử lý tác vụ nền.

Ví dụ tự xây dựng:

```text
10:00:00  Ghi bền vững quyết định thu hồi phiên S17
10:00:01  Node API A nhận cập nhật
10:00:08  Cache cũ của node API B hết hạn
10:00:09  Yêu cầu mới bằng token S17 bị chặn ở A và B
```

Nếu yêu cầu của nghiệp vụ là chặn trong 5 giây, ví dụ này chưa đạt dù Authorization Server đã trả thành công. Cần xác định ngân sách độ trễ cho việc ghi trạng thái, sao chép, phân phối sự kiện, cache và lần kiểm tra tiếp theo; đo đường đi thực tế thay vì chỉ đo tốc độ endpoint thu hồi.

Các ràng buộc thiết kế cần nêu rõ:

- Quyết định thu hồi phải được lưu bền vững; sự kiện thông báo không nên là bản duy nhất của trạng thái quan trọng.
- Node khởi động lại phải nạp được trạng thái cần thiết, không quên denylist rồi chấp nhận lại token.
- Mất hoặc đảo thứ tự sự kiện phải có cách đối soát; cập nhật cũ không được phục hồi một phiên đã bị thu hồi.
- Lỗi kho trạng thái cần có chính sách cụ thể. Với thao tác nhạy cảm, không coi “không đọc được trạng thái” là “chưa bị thu hồi”.
- Nếu cho phép dùng kết quả cache trong một khoảng lỗi, phải giới hạn thời gian và đưa khoảng đó vào cam kết thu hồi.

Thu hồi cũng không quay ngược một giao dịch đã hoàn tất. Request đang chạy, luồng tải dữ liệu dài hoặc job đã xếp hàng cần chính sách kiểm tra lại phù hợp. Với thao tác rủi ro cao, có thể cần kiểm tra quyền hiện hành gần thời điểm thực hiện thay đổi quan trọng.

## 10. Một luồng xử lý mất thiết bị

Luồng dưới đây minh họa chính sách thu hồi một phiên trên điện thoại, không phải API chuẩn của một sản phẩm cụ thể.

```text
revokeLostDeviceSession(operator, targetSession):
    requireAuthorizedRevocation(operator, targetSession)

    atomically:
        markSessionRevoked(targetSession)
        disableRefreshFamilyFor(targetSession)
        persistRevocationRecord(targetSession)
        enqueueRevocationNotification(targetSession)

    invalidateApplicableCaches(targetSession)
    recordAuditWithoutRawTokens(operator, targetSession, "DEVICE_LOST")
    return revocationAcceptedWithDefinedEnforcementWindow
```

Tại API, với kiến trúc kiểm tra trạng thái phiên đã chọn:

```text
authorizeRequest(rawAccessToken, operation):
    claims = verifySignatureIssuerAudienceTypeAndTime(rawAccessToken)
    session = readSessionStateUnderFreshnessPolicy(claims.sessionReference)

    require session is not revoked
    requireTokenNotDenied(claims)
    requireCurrentAuthorization(claims, session, operation)

    return allow()
```

Tham chiếu phiên trong mã giả là trường theo hợp đồng nội bộ. Không tin `sessionReference`, `sub` hay `jti` do client gửi riêng mà chưa được ràng buộc vào token đã xác minh.

Ranh giới giao dịch giữa thu hồi và refresh đặc biệt quan trọng. Nếu request refresh đã đọc trạng thái “còn hoạt động”, sau đó luồng thu hồi ghi trạng thái mới, request refresh không được tùy tiện phát hành một chuỗi token thoát khỏi phạm vi bị thu hồi. Cần cơ chế nhất quán như phiên bản trạng thái hoặc kiểm tra đồng thời theo thiết kế lưu trữ.

Luồng kiểm toán nên phân biệt người yêu cầu, người bị tác động, client/phiên, phạm vi, lý do, thời điểm ghi nhận và bằng chứng thực thi. Không ghi token nguyên văn vào audit log hoặc đưa token vào URL, nơi nó dễ bị lưu bởi proxy và lịch sử truy cập.

## 11. Vì sao đổi khóa ký không phải cách thu hồi một token?

Nếu API ngừng tin một khóa ký, nhiều token được ký bằng khóa đó có thể bị từ chối cùng lúc. Điều này có phạm vi rộng hơn một thiết bị hoặc một grant; các API còn cache khóa cũng có thể phản ứng ở thời điểm khác nhau.

Trong rotation theo kế hoạch, khóa cũ thường còn được tin trong giai đoạn chuyển đổi để token đang tồn tại hoạt động tới hạn. Chỉ bắt đầu ký bằng khóa mới không đồng nghĩa các token ký bằng khóa cũ đã mất hiệu lực.

Khi nghi lộ khóa ký, phải có quy trình sự cố riêng để ngừng tin khóa, ngăn cấp thêm token giả và kiểm tra việc phân phối cấu hình. Đây là tình huống khác với người dùng rút quyền của một ứng dụng. Không dùng đổi khóa toàn hệ thống như thao tác logout thông thường.

## 12. Các tình huống cần kiểm chứng

Các trường hợp sau là gợi ý kiểm thử cho một hệ thống đã chọn chính sách thu hồi, không phải báo cáo đã chạy test.

| Tình huống | Điều cần quan sát |
|---|---|
| Thu hồi một refresh token | Không xin được access token mới từ token đó |
| Dùng lại refresh token trước rotation | Phát hiện reuse và xử lý chuỗi liên quan đúng chính sách |
| Dùng access token đã cấp trước thu hồi | Bị chặn trong cửa sổ thực thi đã cam kết, hoặc ghi rõ giới hạn tới hết hạn nếu dùng mô hình đó |
| Gọi API qua nhiều node | Hiệu lực thu hồi nhất quán trong ngân sách độ trễ |
| Cache introspection đang có `active: true` | Không tiếp tục cho phép quá giới hạn cache và hạn token |
| Node API khởi động lại | Không mất trạng thái cần thiết để từ chối token |
| Refresh và revoke diễn ra đồng thời | Không phát hành token mới thoát phạm vi thu hồi |
| Gửi lại yêu cầu thu hồi cùng token | Không phục hồi token và không tiết lộ trạng thái nhạy cảm ngoài hợp đồng |
| Endpoint thu hồi lỗi hoặc timeout | Không tuyên bố hệ thống đã thu hồi thành công |
| Chỉ thu hồi phiên điện thoại | Phiên khác bị tác động đúng phạm vi chính sách |
| Workload còn credential hợp lệ | Xác nhận đã ngăn được cả việc xin token mới nếu đó là mục tiêu sự cố |
| Kho trạng thái không truy cập được | Thực thi đúng chính sách lỗi; không ngầm bỏ kiểm tra |

Kết quả kiểm chứng nên đo tại resource server bằng yêu cầu có kiểm soát, không chỉ nhìn một cờ trong giao diện quản trị. Đồng thời theo dõi tác động ngoài ý muốn: thu hồi một token không được vô tình xóa quyền của tenant khác hoặc client khác.

## 13. Tự kiểm tra hiểu biết

**Xóa access token khỏi ứng dụng có thu hồi được bản sao đã bị lấy cắp không?** Không. Phải có tác động ở nơi xác minh/trạng thái token hoặc chờ hết cửa sổ hiệu lực đã thiết kế.

**Thu hồi refresh token có bảo đảm mọi JWT access token dừng ngay không?** Không. Nó ngăn refresh theo phạm vi thu hồi; access token đã cấp cần cơ chế thực thi tại API và chính sách lan truyền phù hợp.

**Một JWT đúng chữ ký có thể đã bị thu hồi không?** Có. Chữ ký chứng minh tính toàn vẹn theo khóa được tin cậy, không tự phản ánh trạng thái thu hồi mới nhất.

**`jti` có phải danh sách token bị thu hồi không?** Không. Nó có thể là một thành phần định danh để xây cơ chế đó, nhưng cần kho trạng thái và kiểm tra thực tế.

**Logout ứng dụng có kết thúc mọi phiên SSO và grant không?** Không mặc định. Phải xác định rõ từng lớp trạng thái và cơ chế tác động.

**Khi nào có thể nói yêu cầu thu hồi đã được đáp ứng?** Khi phạm vi cần chặn đã được xử lý, không còn đường cấp token mới trái chính sách, và các nơi thực thi từ chối quyền truy cập trong giới hạn thời gian đã cam kết với bằng chứng kiểm chứng phù hợp.
