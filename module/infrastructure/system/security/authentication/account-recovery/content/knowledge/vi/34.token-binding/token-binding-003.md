# Binding token to device

## 1. Ràng buộc token với thiết bị giải quyết vấn đề gì?

Một token khôi phục dạng bearer cho phép bên đang giữ token thực hiện quyền mà token đại diện, nếu các điều kiện khác vẫn hợp lệ. Khi liên kết khôi phục bị sao chép từ email, lịch sử trình duyệt hoặc một kênh bị lộ, kẻ tấn công có thể thử sử dụng nó trên máy khác.

**Binding token to device** bổ sung điều kiện: máy chủ chỉ chấp nhận token khi bên sử dụng chứng minh được quyền kiểm soát một khóa hoặc ngữ cảnh đã được ràng buộc từ trước. Trong thiết kế dùng khóa bất đối xứng, lấy được token chưa đủ; bên sử dụng còn phải tạo được bằng chứng bằng private key tương ứng.

Điều cần mô tả chính xác là hệ thống đang ràng buộc với cái gì:

- Một cookie trong một hồ sơ trình duyệt.
- Một khóa do một bản cài ứng dụng quản lý.
- Một credential WebAuthn đã đăng ký.
- Một khóa có bằng chứng được bảo vệ bằng phần cứng theo chính sách cụ thể.

Các đối tượng này không đồng nghĩa với “đúng chiếc điện thoại vật lý của chủ tài khoản”. Một khóa có thể được đồng bộ, sao lưu hoặc bị sử dụng từ xa. Một cookie có thể bị sao chép. Một nhãn `device_id` do client gửi không tự tạo ra bằng chứng sở hữu thiết bị.

Trong khôi phục tài khoản, ràng buộc thiết bị cần đạt hai mục tiêu cùng lúc:

1. Giảm khả năng token bị sử dụng ngoài ngữ cảnh đã được phép.
2. Không buộc người đã mất thiết bị phải sử dụng chính thiết bị bị mất để khôi phục.

Vì vậy, device binding là một điều kiện bảo vệ quyền khôi phục, không phải sự thay thế cho xác minh danh tính, thời hạn token, tính dùng một lần hoặc chính sách chống lạm dụng.

## 2. Phân biệt định danh, tín hiệu rủi ro và bằng chứng sở hữu

| Cơ chế | Máy chủ biết được điều gì? | Giới hạn cần hiểu |
| --- | --- | --- |
| Chuỗi `device_id` trong request | Client khai báo một định danh | Có thể bị sửa hoặc sao chép nếu không đi kèm bằng chứng |
| User-Agent, loại hệ điều hành, độ phân giải | Một số thuộc tính do môi trường cung cấp | Không phải bí mật, không đủ để xác thực |
| Địa chỉ IP | Điểm xuất phát mạng mà máy chủ quan sát | Có thể đổi do mạng di động, VPN hoặc được nhiều người dùng chung |
| Cookie ngẫu nhiên do máy chủ cấp | Request có giữ một bí mật của trình duyệt | Bảo vệ theo mô hình bearer; mất cookie có thể làm mất ràng buộc |
| Chữ ký của khóa đã ràng buộc | Bên gửi có khả năng sử dụng private key tương ứng | Chưa chứng minh danh tính chủ tài khoản hoặc một thiết bị vật lý duy nhất |
| Credential và attestation đáp ứng chính sách | Có thêm thông tin về credential hoặc môi trường tạo khóa | Cần xác minh đúng chuỗi tin cậy; attestation không tự xác minh chủ tài khoản |

Không đặt điều kiện “IP và User-Agent phải giống lúc cấp token” rồi gọi đó là ràng buộc mật mã. Có thể dùng các thuộc tính này làm tín hiệu rủi ro, nhưng cần phân biệt với bằng chứng mà kẻ chỉ có token không tạo được.

Ví dụ, người dùng xin khôi phục bằng Wi-Fi ở nhà, sau đó mở email trên cùng điện thoại qua mạng di động. IP thay đổi không chứng minh thiết bị đã đổi. Ngược lại, kẻ tấn công cùng mạng công ty có thể có IP công khai giống nạn nhân.

Một chính sách hợp lý cần ghi rõ:

```text
Điều kiện bắt buộc:
  Có token hợp lệ và bằng chứng của đúng khóa đã ràng buộc.

Tín hiệu đánh giá thêm:
  Mạng mới, trình duyệt mới, địa lý bất thường,
  số lần thử, lịch sử recovery và trạng thái tài khoản.
```

Khi tín hiệu rủi ro xấu đi, hệ thống có thể yêu cầu xác minh bổ sung hoặc chuyển sang luồng khác. Không âm thầm bỏ điều kiện sở hữu khóa chỉ vì các thuộc tính trình duyệt nhìn có vẻ quen thuộc.

## 3. Hai loại ràng buộc cần tách biệt

### 3.1. Ràng buộc với thiết bị hoặc credential đã được tin cậy

Tài khoản đã có một khóa được đăng ký trước. Một token khôi phục chỉ có thể dùng khi có bằng chứng từ khóa ấy.

Cách này phù hợp khi người dùng mất mật khẩu nhưng vẫn giữ một phương tiện xác thực đủ điều kiện. Tuy nhiên, nếu chính thiết bị hoặc credential đó bị mất, đường khôi phục này không còn sử dụng được. Hệ thống cần một phương án độc lập có mức xác minh phù hợp.

Không được cho client thay `trusted_device_key_id` bằng một khóa mới trong request cuối. Khóa mới chưa có quan hệ tin cậy với tài khoản chỉ vì client gọi nó là “thiết bị của tôi”.

### 3.2. Ràng buộc với thiết bị đang thực hiện một recovery flow mới

Người dùng có thể bắt đầu khôi phục trên một thiết bị mới. Thiết bị tạo khóa dành cho luồng; máy chủ lưu public key và yêu cầu chứng minh sở hữu khóa đó trước khi tiếp tục.

Ở đây, khóa mới chỉ chứng minh **tính liên tục của client trong cùng luồng**. Nó chưa xác minh chủ tài khoản. Các bằng chứng khôi phục độc lập vẫn quyết định liệu luồng có được phép đặt lại mật khẩu, gỡ MFA hoặc đăng ký passkey mới hay không.

Ví dụ:

```text
Khóa mới K thuộc recovery flow F.
F đã hoàn tất các bằng chứng mà chính sách yêu cầu.
Token T được cấp cho account A, flow F, mục đích P và khóa K.

Muốn dùng T:
  phải có T;
  phải chứng minh sử dụng được private key của K;
  F vẫn phải đủ điều kiện thực hiện P.
```

Nếu kẻ tấn công có thể tự mở flow, gắn khóa của mình rồi nhận token chỉ bằng một địa chỉ email, việc ràng buộc với khóa không tự ngăn chiếm đoạt tài khoản. Điểm quyết định vẫn là cách flow được xác minh và được người dùng cho phép.

## 4. Cấp token với thông tin ràng buộc do máy chủ quản lý

Một luồng minh họa cho thiết bị mới gồm các bước:

1. Client tạo cặp khóa trong môi trường lưu trữ phù hợp.
2. Máy chủ tạo recovery flow và challenge ngắn hạn để kiểm tra quyền sử dụng khóa.
3. Client gửi public key cùng bằng chứng đáp ứng challenge.
4. Máy chủ kiểm tra khóa, bằng chứng và ghi ràng buộc vào flow.
5. Flow hoàn tất những bằng chứng xác minh danh tính và phê duyệt theo chính sách.
6. Máy chủ cấp token có phạm vi hẹp, ràng buộc với khóa đã lưu của flow.

Trong sản phẩm thực tế, một số bước có thể đổi thứ tự theo kênh xác minh. Điều bất biến là **không được để bên chỉ đang trình token tự quyết định khóa nào sẽ được tin cậy để sử dụng token đó**.

Máy chủ có thể lưu bản ghi như sau:

```json
{
  "token_record_id": "rt_601",
  "account_id": "account_148",
  "tenant_id": "tenant_032",
  "recovery_flow_id": "rf_492",
  "purpose": "CREATE_LIMITED_RECOVERY_GRANT",
  "binding_mode": "RECOVERY_CLIENT_KEY",
  "device_key_id": "key_825",
  "device_key_thumbprint": "<server-computed-thumbprint>",
  "binding_version": 1,
  "expires_at": "2026-11-23T09:10:00Z",
  "consumed_at": null,
  "revoked_at": null
}
```

Đây là metadata minh họa ở phía máy chủ, không phải token gửi cho người dùng. Bí mật token cần được lưu bằng cơ chế bảo vệ phù hợp, tách khỏi định danh bản ghi.

Các ràng buộc về account, tenant, flow và purpose vẫn cần thiết. Hai tài khoản có thể dùng chung một thiết bị hoặc cùng một khóa trong một số thiết kế; bằng chứng của khóa không tự xác định tài khoản nào được phép thay đổi.

### 4.1. Không tin thumbprint do client tự khai báo

Máy chủ cần kiểm tra cấu trúc public key, thuật toán cho phép và tính hợp lệ của bằng chứng, rồi tự tính định danh khóa theo quy tắc đã chọn.

Nếu dùng JWK thumbprint, cần tính theo quy tắc chuẩn hóa của [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638.html). Hash trực tiếp chuỗi JSON tùy ý dễ tạo ra các giá trị khác nhau cho cùng một khóa vì thứ tự thuộc tính hoặc cách biểu diễn khác nhau.

Thumbprint là định danh public key, không phải bí mật và không phải chữ ký. Gửi đúng thumbprint nhưng không có bằng chứng sử dụng private key phải bị từ chối.

Không cho payload của request cập nhật `device_key_id`, `binding_version` hoặc ràng buộc token đang hoạt động. Nếu cần đổi khóa, đó là một chuyển trạng thái được phê duyệt riêng, không phải chỉnh sửa metadata thuận tiện cho client.

### 4.2. Khóa không xuất được chưa đồng nghĩa khóa phần cứng

Một trình duyệt hoặc ứng dụng có thể tạo khóa không cho xuất private key qua API thông thường. Đó là một lớp bảo vệ hữu ích, nhưng máy chủ không nên chỉ dựa vào tuyên bố `non_exportable=true` trong request để kết luận khóa nằm trong phần cứng.

Nếu chính sách yêu cầu mức bảo vệ cụ thể, cần cơ chế chứng thực và xác minh tương ứng với nền tảng. Nếu không có bằng chứng ấy, mô tả đúng mức bảo đảm là “request chứng minh sử dụng được khóa K”, không phải “request chắc chắn đến từ duy nhất điện thoại X”.

## 5. Kiểm tra bằng chứng khi sử dụng token

Một chữ ký hợp lệ trên một chuỗi cố định như `"recover-account"` là chưa đủ. Bằng chứng đó có thể bị sao chép và dùng lại cho một request khác.

Thiết kế cần xác định bằng chứng có liên hệ với:

- Challenge hoặc nonce phù hợp do máy chủ cấp.
- Recovery flow và phiên bản ràng buộc hiện tại.
- Đúng token hoặc một challenge đã được máy chủ liên kết cố định với token.
- Đúng thao tác được cho phép.
- Thời hạn và điều kiện chống phát lại.

[DPoP trong RFC 9449](https://www.rfc-editor.org/rfc/rfc9449.html) là một ví dụ chuẩn cho việc ràng buộc token OAuth với khóa của bên gửi. Đây không phải giao thức khôi phục tài khoản. Nếu sản phẩm dùng OAuth với DPoP, cần triển khai đầy đủ chuẩn; không đổi tên một chữ ký tùy ý thành DPoP.

Đối với một luồng khôi phục riêng, phần dưới mô tả quan hệ dữ liệu và giao dịch, không định nghĩa một định dạng chữ ký mới để sao chép vào production. Việc xác minh mật mã phải dùng giao thức và thư viện phù hợp.

### 5.1. Challenge phải được gắn với ngữ cảnh trên máy chủ

Giả sử thao tác là đổi token lấy một recovery grant giới hạn. Máy chủ cấp challenge và lưu:

```text
challenge_id        = ch_214
recovery_flow_id    = rf_492
token_record_id    = rt_601
device_key_id      = key_825
binding_version    = 1
authorized_action  = CREATE_LIMITED_RECOVERY_GRANT
expires_at         = thời điểm hết hạn phía máy chủ
used_at            = chưa dùng
```

Client không được sửa ý nghĩa challenge bằng cách gửi thêm `account_id` hay `authorized_action` khác trong request. Máy chủ lấy quan hệ từ bản ghi đã lưu và đối chiếu với đường xử lý hiện tại.

Nếu sử dụng WebAuthn, challenge đi qua quy trình xác minh assertion của WebAuthn; nếu dùng một cơ chế proof khác, cần thực hiện đúng những kiểm tra mà cơ chế đó yêu cầu. Không xác minh chữ ký trên dữ liệu tự tái dựng tùy ý rồi bỏ qua các trường ngữ cảnh của giao thức.

Đối với thao tác có dữ liệu nghiệp vụ nhạy cảm, cần làm rõ bằng chứng cho phép chính xác dữ liệu nào. Ví dụ, cho phép tạo grant để đặt lại mật khẩu không được đồng nghĩa cho phép đổi địa chỉ email nhận khôi phục. Không mặc định rằng mọi chữ ký proof đều bảo vệ toàn bộ body HTTP.

### 5.2. Quy trình xử lý và tiêu thụ nguyên tử

```text
Nhận token và proof với giới hạn kích thước/định dạng.
Tra cứu token bằng cách bảo vệ bí mật theo thiết kế.
Lấy public key từ ràng buộc đã lưu trên máy chủ.
Xác minh proof theo giao thức và thuật toán được phép.

BEGIN
  Khóa hoặc kiểm tra version của flow, token và challenge.
  Đối chiếu lại key_id và binding_version đã xác minh.
  Kiểm tra account, tenant, purpose, thời hạn và thu hồi.
  Kiểm tra flow vẫn đạt điều kiện khôi phục bắt buộc.
  Kiểm tra challenge đúng ngữ cảnh, chưa hết hạn và chưa dùng.

  Đánh dấu challenge đã dùng bằng cập nhật có điều kiện.
  Tiêu thụ token bằng cập nhật có điều kiện.
  Tạo recovery grant giới hạn, ràng buộc với cùng khóa.
  Ghi audit và outbox nếu có.
COMMIT
```

Các cập nhật bắt buộc phải thành công cùng nhau. Nếu challenge đã dùng, token đã hết hạn hoặc binding version đã thay đổi, không được tạo grant rồi mới phát hiện sai sót sau đó.

Có thể xác minh chữ ký trước giao dịch để giảm thời gian giữ khóa. Khi đó, trong giao dịch vẫn cần kiểm tra lại rằng ràng buộc dùng để xác minh chưa bị thay thế hoặc thu hồi.

Challenge dùng một lần trong mô hình trên phải được kiểm soát bằng trạng thái dùng chung giữa các instance. Lưu cờ `used=true` riêng trong bộ nhớ của từng máy chủ không ngăn một request bị gửi lại sang máy khác.

Tương tự, binding không thay thế tính dùng một lần của token. Cùng một private key có thể ký nhiều request hợp lệ; máy chủ vẫn phải ngăn token tạo ra nhiều kết quả khôi phục.

## 6. Dùng WebAuthn hoặc passkey cần hiểu đúng mức bảo đảm

Nếu sử dụng một credential WebAuthn đã đăng ký, máy chủ cần xác minh assertion theo giao thức, bao gồm challenge, origin được phép, RP ID, chữ ký và credential tương ứng; yêu cầu user verification phải được kiểm tra nếu chính sách đặt ra điều kiện đó. Không chỉ kiểm tra rằng response có một `credentialId` quen thuộc.

Passkey có thể được sao lưu hoặc đồng bộ. WebAuthn phân biệt credential theo khả năng sao lưu và trạng thái đã sao lưu; vì vậy cùng credential không luôn đồng nghĩa cùng thiết bị vật lý. Xem [WebAuthn Level 3 của W3C](https://www.w3.org/TR/webauthn-3/).

Từ đó, cần lựa chọn cách diễn đạt và chính sách phù hợp:

| Mục tiêu sản phẩm | Điều phải xác định trước |
| --- | --- |
| Chỉ yêu cầu bên sử dụng tiếp tục kiểm soát credential đã ràng buộc | Credential nào được chấp nhận và cách kiểm tra trạng thái thu hồi |
| Yêu cầu bước có tương tác người dùng | Cơ chế thực sự cung cấp tương tác nào và máy chủ xác minh được điều kiện nào |
| Yêu cầu xác minh người đang sử dụng authenticator | Chính sách user verification và phương án thay thế khi không đáp ứng |
| Yêu cầu một khóa không được đồng bộ sang thiết bị khác | Bằng chứng và chính sách về thuộc tính credential, môi trường khóa, mức độ tin cậy |
| Yêu cầu chứng minh chủ tài khoản hợp pháp | Các bằng chứng danh tính của recovery flow, ngoài quyền sử dụng credential |

Một credential mới được tạo trong quá trình khôi phục không tự trở thành passkey đăng nhập đã được tin cậy. Việc đăng ký yếu tố xác thực lâu dài cần là một hành động được cấp quyền riêng, sau khi luồng đạt điều kiện tương ứng.

Tương tự, xác minh người dùng ở thiết bị không tự chứng minh rằng người ấy đã đồng ý mọi thay đổi tài khoản. Giao diện và challenge cần gắn với hành động đang được thực hiện, thay vì dùng một tương tác chung để cấp quyền không giới hạn.

## 7. Thiết bị cũ bị mất hoặc người dùng mở email trên máy khác

### 7.1. Mất thiết bị đã được ràng buộc

Giả sử token T đang ràng buộc với khóa K của một điện thoại bị mất. Người dùng chỉ còn token nhưng không còn cách sử dụng K.

Cách xử lý an toàn là:

1. Không chấp nhận token thiếu proof chỉ để giúp người dùng tiếp tục.
2. Cho phép bắt đầu một recovery flow khác có xác minh phù hợp.
3. Xác định cách vô hiệu hóa flow hoặc token cũ theo chính sách và bằng chứng đã có.
4. Chỉ cấp token mới ràng buộc với khóa mới sau khi điều kiện của flow mới được đáp ứng.
5. Ghi lại việc thay đổi và thông báo qua kênh phù hợp.

Không thiết kế một endpoint `rebind(token, newPublicKey)` mà chỉ cần token cũ. Endpoint đó cho phép kẻ lấy được token chuyển ràng buộc sang khóa của chính mình.

Nếu cho phép chuyển khóa trong cùng flow, cần một giao thức được phê duyệt rõ ràng: chứng minh khóa cũ nếu còn dùng được, hoặc thực hiện lại mức xác minh khôi phục bắt buộc. Việc thay đổi phải vô hiệu hóa các challenge và quyền tạm thời không còn phù hợp; không để cả khóa cũ và mới tiếp tục sử dụng ngoài ý định.

Việc chuyển sang hỗ trợ thủ công cũng không phải ngoại lệ bỏ xác minh. Nhân viên hỗ trợ cần có quy trình, quyền hạn và audit cho quyết định thay đổi ngữ cảnh khôi phục.

### 7.2. Email mở trên thiết bị khác

Ví dụ người dùng bắt đầu khôi phục trên laptop, nhưng bấm liên kết email trên điện thoại. Token được ràng buộc với khóa của laptop nên điện thoại không thể trực tiếp thực hiện thao tác cuối.

Một trải nghiệm có thể là hướng dẫn người dùng trở lại trình duyệt ban đầu và nhập mã xác nhận, hoặc sử dụng một cơ chế xác nhận giữa hai thiết bị đã được thiết kế riêng. Khi có cơ chế chuyển tiếp:

- Chỉ xác nhận đúng flow và khóa đang chờ, với thời hạn ngắn.
- Cho người dùng thấy thao tác họ đang cho phép.
- Ngăn mã hoặc liên kết bị dùng để phê duyệt nhầm flow do kẻ tấn công khởi tạo.
- Không tự đăng ký điện thoại thành thiết bị tin cậy lâu dài.
- Không chuyển token sang chế độ bearer khi thiếu khóa.

Không coi việc ai đó đã bấm một email là sự đồng ý ràng buộc tài khoản với bất kỳ khóa nào đang chờ. Nếu kẻ tấn công tạo flow trước rồi thuyết phục nạn nhân xác nhận, hệ thống vẫn có thể bị chiếm đoạt dù mọi proof mật mã đều hợp lệ.

### 7.3. Xóa dữ liệu trình duyệt hoặc cài lại ứng dụng

Khóa tạm thời có thể biến mất khi người dùng xóa dữ liệu, đổi hồ sơ trình duyệt, cài lại ứng dụng hoặc khôi phục máy. Không nên coi mọi trường hợp mất khóa là tấn công, nhưng cũng không thể lấy sự tiện lợi làm lý do bỏ binding.

Sản phẩm cần thông báo rõ phạm vi: “Hoàn tất bước này trong trình duyệt đã bắt đầu khôi phục” hoặc hướng dẫn bắt đầu lại. Với thiết bị dùng chung, cần tránh để quyền khôi phục còn sót trong một hồ sơ mà người khác tiếp tục sử dụng.

## 8. Những đe dọa binding không tự giải quyết

| Tình huống | Binding bằng khóa giúp gì? | Kiểm soát còn cần |
| --- | --- | --- |
| Chỉ token bị sao chép sang máy khác | Ngăn dùng token nếu thiếu khả năng sử dụng khóa đã ràng buộc | Token ngắn hạn, dùng một lần, chống lộ và chống dò đoán |
| Token và private key đều bị lộ | Lớp ràng buộc không còn tách biệt hai bí mật | Thu hồi, bảo vệ kho khóa, điều tra và giới hạn quyền |
| Mã độc có thể yêu cầu khóa ký ngay trên client | Có thể không cần xuất private key để thực hiện hành động | Bảo vệ client, giới hạn quyền ký và xác nhận phù hợp |
| Kẻ tấn công tự tạo flow và gắn khóa của mình | Chứng minh đúng khóa của kẻ tấn công | Xác minh danh tính và chống phê duyệt nhầm flow |
| Tài khoản email đã bị chiếm quyền | Không tự khôi phục được độ tin cậy của email | Chính sách bằng chứng độc lập khi mức rủi ro yêu cầu |
| Proxy hoặc instance bỏ kiểm tra binding | Token có thể được chấp nhận qua đường yếu hơn | Áp dụng cùng chính sách ở mọi đường tiêu thụ |

RFC 9449 cũng nêu giới hạn khi mã không tin cậy chạy trong ngữ cảnh client: khóa không xuất được vẫn có thể bị yêu cầu tạo proof tại chỗ. Vì vậy binding không thay thế phòng chống XSS và bảo vệ mã phía client. [RFC 9449, phần 11.4](https://www.rfc-editor.org/rfc/rfc9449.html#section-11.4).

Cần kiểm tra cả đường dự phòng về mặt thiết kế: API phiên bản cũ, ứng dụng cũ hoặc tác vụ hỗ trợ không được chấp nhận cùng token mà bỏ proof. Nếu client không hỗ trợ cơ chế bắt buộc, phải chuyển sang một flow được cho phép khác, không hạ cấp âm thầm.

Nếu hạ tầng kiểm tra challenge hoặc trạng thái thu hồi không hoạt động, không thể kết luận điều kiện binding đã đạt. Đối với thao tác nhạy cảm, trả lỗi có thể thử lại hoặc tạm dừng flow theo chính sách, thay vì chấp nhận token như bearer.

## 9. Quản lý vòng đời khóa và dữ liệu vận hành

Khóa dành riêng cho một recovery flow nên có vòng đời tương ứng với flow. Không tự biến khóa tạm thành định danh theo dõi lâu dài.

Khi flow kết thúc, bị thu hồi hoặc hết thời hạn:

- Vô hiệu hóa token, challenge và grant liên quan theo đúng trạng thái.
- Giữ audit cần thiết theo chính sách lưu trữ.
- Xóa vật liệu tạm hoặc chấm dứt quyền sử dụng khi không còn cần.
- Chỉ giữ khóa đăng nhập hoặc khóa thiết bị lâu dài nếu đã có quy trình đăng ký được cấp quyền riêng.

Audit có thể chứa flow ID, token record ID, key ID, binding version, kết quả và loại lỗi nội bộ. Không ghi token gốc, private key, cookie, recovery grant hoặc proof đầy đủ còn khả năng phát lại. Public key và thumbprint cũng có thể tạo khả năng liên kết hoạt động, nên cần giới hạn quyền truy cập và mục đích sử dụng.

Thông báo ra ngoài nên hướng dẫn người dùng mà không tiết lộ không cần thiết về tài khoản hoặc thiết bị đã đăng ký. Phân biệt các lỗi nội bộ như `BOUND_KEY_MISMATCH`, `CHALLENGE_EXPIRED` và `FLOW_REVOKED` giúp vận hành; không nhất thiết công bố toàn bộ phân loại đó cho mọi caller.

## 10. Ví dụ quyết định cấp quyền

Giả sử token T thuộc flow F của tài khoản A, mục đích tạo recovery grant và ràng buộc với khóa K:

| Request | Quyết định | Lý do |
| --- | --- | --- |
| Có T, không có proof | Từ chối | Chưa đáp ứng điều kiện sở hữu khóa |
| Có T, proof hợp lệ của khóa khác K2 | Từ chối | Chữ ký đúng nhưng không đúng ràng buộc |
| Có T, proof của K nhưng challenge thuộc flow khác | Từ chối | Sai ngữ cảnh được cho phép |
| Có T, proof của K, challenge hợp lệ nhưng F bị thu hồi | Từ chối | Binding không vượt qua quyết định thu hồi |
| Có T, proof của K, flow đủ điều kiện, token chưa dùng | Có thể cho phép và tiêu thụ nguyên tử | Tất cả điều kiện bắt buộc đều đạt |
| Gửi lại sau lần thành công | Không tạo thêm grant | Binding không bỏ tính dùng một lần |

Giá trị của ràng buộc nằm ở việc máy chủ kiểm tra một quan hệ đã được cấp phép từ trước: **token này, tài khoản này, flow này, mục đích này và khóa này**. Trải nghiệm khôi phục cần cho phép thiết lập một quan hệ mới khi thiết bị cũ đã mất, nhưng chỉ thông qua quyết định xác minh mới có đủ mức bảo đảm.
