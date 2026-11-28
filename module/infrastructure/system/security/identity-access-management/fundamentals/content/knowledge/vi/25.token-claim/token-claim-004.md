# Token issuer

Một API nhận token có claim `role` bằng `admin`. Trước khi dùng claim đó, API cần biết ai đã phát hành token, có tin bên phát hành ấy trong ngữ cảnh này không, và token có thực sự được bên đó bảo vệ hay không. Nếu bỏ qua những câu hỏi này, bất kỳ ai cũng có thể tự tạo một payload JSON có vẻ hợp lệ rồi khai mình là quản trị viên.

Token issuer là bên phát hành token. Trong hệ thống IAM, xác định đúng issuer giúp thiết lập ranh giới tin cậy giữa hệ thống định danh, ứng dụng và API. Việc nhìn thấy tên một tổ chức uy tín trong token chưa tạo ra sự tin cậy; bên nhận phải xác thực token bằng cấu hình đã được kiểm soát.

## 1. Issuer chịu trách nhiệm phát hành token trong ngữ cảnh nào?

Issuer phát hành token theo chính sách của một hệ thống: xác thực chủ thể hoặc client, đánh giá yêu cầu cấp token, lựa chọn claim và giới hạn mục đích sử dụng. Các trách nhiệm cụ thể phụ thuộc giao thức, loại token và grant được sử dụng.

Trong một hệ thống minh họa:

```text
Người dùng hoặc workload
        → yêu cầu cấp token theo luồng được cho phép
Authorization Server / hệ thống phát hành
        → phát token cho client
Client
        → gửi access token tới API
API
        → xác thực token và áp dụng chính sách truy cập
```

Không phải token nào cũng đại diện cho một người vừa nhập mật khẩu. Ví dụ, một dịch vụ xử lý hóa đơn có thể nhận access token để gọi dịch vụ lưu trữ theo quyền của chính workload. Issuer vẫn phải là hệ thống phát hành được API tin cậy; subject và quyền trong token có thể đại diện cho dịch vụ thay vì nhân viên.

Một sản phẩm IAM có thể đồng thời đóng vai trò IdP, Authorization Server và OpenID Provider. Tuy vậy, cần phân biệt vai trò:

| Vai trò | Trọng tâm |
|---|---|
| Identity Provider (IdP) | Cung cấp thông tin định danh và kết quả xác thực trong cơ chế liên kết danh tính |
| OAuth Authorization Server | Cấp access token theo quyền được cho phép |
| OpenID Provider (OP) | Cung cấp lớp xác thực OpenID Connect, trong đó có ID Token |
| Resource Server / API | Tiếp nhận và xác thực access token để bảo vệ tài nguyên |
| Client | Yêu cầu token và sử dụng token đúng mục đích |

API không mặc nhiên trở thành issuer chỉ vì nó nhận token. Tương tự, một cổng mạng chuyển tiếp request không trở thành issuer của token được chuyển tiếp.

## 2. Claim `iss` trong JWT

JWT dùng claim `iss` để định danh bên phát hành. Theo định dạng JWT cơ sở, giá trị là chuỗi phân biệt chữ hoa, chữ thường thuộc kiểu `StringOrURI`; claim này không bắt buộc trong mọi ứng dụng JWT. Giao thức hoặc profile sử dụng JWT sẽ đặt yêu cầu chặt hơn. Xem [RFC 7519, mục 4.1.1](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.1).

Ví dụ một phần payload của access token, đã lược bớt các claim khác:

```json
{
  "iss": "https://login.example.org/workforce",
  "sub": "employee-417",
  "aud": "urn:example:api:invoice",
  "scope": "invoice.read"
}
```

Trong ví dụ:

- `iss` chỉ hệ thống phát hành thuộc miền định danh nhân sự.
- `sub` chỉ chủ thể mà các claim đề cập tới.
- `aud` chỉ API dự kiến sử dụng token.
- `scope` biểu diễn phạm vi truy cập theo hợp đồng của API và hệ thống cấp quyền.

Payload trên chỉ là dữ liệu minh họa, không phải một token hoàn chỉnh có thể dùng để đăng nhập hoặc gọi API. Chưa có căn cứ để tin các claim nếu chỉ decode được JSON.

Không đồng nhất `iss` với những giá trị sau:

| Giá trị | Vì sao khác issuer |
|---|---|
| `client_id` | Định danh client, không phải danh tính bên phát hành |
| `sub` | Định danh chủ thể, có thể là người dùng hoặc workload |
| `aud` | Định danh bên dự kiến sử dụng token |
| `kid` trong JOSE header | Gợi ý chọn khóa, không phải một tuyên bố tin cậy về issuer |
| Tên miền trong email | Là dữ liệu về người dùng, không xác định ai đã phát hành token |
| Token endpoint URL | Là endpoint xử lý yêu cầu; không tự động bằng issuer identifier |

### Quy định phụ thuộc loại token

Với ID Token của OpenID Connect thông thường, `iss` là claim bắt buộc và được biểu diễn bằng URL HTTPS theo quy định của giao thức. Bên nhận phải đối chiếu chính xác với issuer đã xác định cho OpenID Provider. Không thể dựa vào tính tùy chọn của JWT cơ sở để bỏ kiểm tra này. Xem [OpenID Connect Core, mục 2 và 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).

Với JWT access token theo RFC 9068, resource server cũng phải đối chiếu chính xác issuer mong đợi với `iss`, đồng thời kiểm tra chữ ký, audience, thời hạn và các yêu cầu của profile. Xem [RFC 9068, mục 4](https://www.rfc-editor.org/rfc/rfc9068.html#section-4).

Vì vậy, trước khi cấu hình validator, hãy xác định mình đang xử lý loại token nào. Cùng một issuer có thể phát nhiều loại token; một ID Token hợp lệ không mặc nhiên là access token hợp lệ cho API.

## 3. Vì sao chuỗi issuer đúng vẫn chưa đủ?

Một người có thể tự tạo payload sau:

```json
{
  "iss": "https://login.example.org/workforce",
  "sub": "employee-417",
  "role": "admin"
}
```

Việc viết đúng chuỗi `iss` không chứng minh người đó điều khiển hệ thống phát hành. Cần có cả quan hệ tin cậy với issuer lẫn cơ chế xác thực token gắn với issuer đó.

Với JWT được ký bất đối xứng, có thể hình dung:

```text
Issuer đã được phê duyệt
        → tập khóa xác minh được gắn với issuer ấy
        → chính sách thuật toán được cho phép
        → chữ ký token được xác minh bằng khóa phù hợp
        → claim iss được đối chiếu với issuer mong đợi
```

Một chữ ký đúng bằng khóa do kẻ gửi tự cung cấp cũng không đủ. Bên nhận phải biết khóa đó thuộc bên phát hành mà mình đã quyết định tin. JWT Best Current Practices yêu cầu kiểm tra sự gắn kết giữa issuer và các khóa mật mã sử dụng cho JWT. Xem [RFC 8725, mục 3.8](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.8).

Trong thiết kế API, có thể phân biệt ba tình huống:

| Tình huống | Quyết định |
|---|---|
| `iss` đúng nhưng chữ ký không xác minh được | Từ chối |
| Chữ ký đúng với một khóa nhưng issuer không được API chấp nhận | Từ chối |
| Issuer và chữ ký hợp lệ, nhưng token dành cho API khác | Từ chối trong API hiện tại |

Tin issuer cũng không có nghĩa chấp nhận mọi claim thành quyền nội bộ. Nếu đối tác được phép xác nhận người dùng của họ, điều đó chưa trao cho đối tác quyền cấp vai trò quản trị hạ tầng của doanh nghiệp.

## 4. Cấu hình mối quan hệ issuer, khóa và chính sách

Một cấu hình tin cậy nên đủ thông tin để trả lời: issuer nào được chấp nhận, khóa xác minh được lấy từ đâu, loại token nào được xử lý, audience nào được dùng và các claim được diễn giải thế nào.

Ví dụ mô hình cấu hình dưới đây do bài học tự đặt để minh họa, không phải tên thuộc tính của một framework:

```json
{
  "trustedIssuers": {
    "https://login.example.org/workforce": {
      "jwksUri": "https://keys.example.org/workforce/jwks.json",
      "allowedAlgorithms": ["RS256"],
      "tokenProfile": "invoice-access-token",
      "expectedAudience": "urn:example:api:invoice",
      "identityNamespace": "workforce"
    }
  }
}
```

Giá trị `RS256` chỉ là lựa chọn của ví dụ. Hệ thống thật phải dùng thuật toán và tham số mật mã phù hợp với profile, thư viện và chính sách triển khai; không lấy bất kỳ giá trị `alg` nào trong token làm mệnh lệnh tự động chấp nhận thuật toán đó.

Issuer identifier không cần trùng URL của JWKS. Trong ví dụ, nơi công bố khóa nằm ở `keys.example.org`, còn issuer ở `login.example.org`. Điều quan trọng là mối liên hệ này được cấu hình hoặc thiết lập qua metadata tin cậy, không phải do request gửi vào tự quyết định.

Metadata hoặc discovery giúp phân phối cấu hình, nhưng không thay thế quyết định issuer nào được phép. Việc một URL trả về metadata có cấu trúc đúng không tự trao quyền phát token được API của mình chấp nhận.

### Key rotation không đồng nghĩa đổi issuer

Một issuer có thể thay khóa ký theo thời gian trong khi giữ nguyên danh tính issuer. Thiết kế vận hành có thể gồm:

1. Công bố khóa xác minh mới trước khi dùng khóa mới để ký.
2. Cho phép giai đoạn chuyển tiếp phù hợp với token còn hiệu lực và chính sách thu hồi.
3. Làm mới cache khóa có kiểm soát khi cần.
4. Ngừng dùng khóa cũ theo kế hoạch và bằng chứng vận hành.

Không bỏ kiểm tra issuer hoặc chấp nhận token chưa xác minh chỉ vì chưa thấy `kid` mới. Tương tự, đổi tên issuer là thay đổi danh tính tin cậy, không đơn giản là thay một khóa ký.

Nếu nhiều API dùng chung bí mật HMAC để xác minh token, các bên giữ bí mật ấy cũng có khả năng tạo MAC. Khi thiết kế ranh giới issuer, phải tính đến quyền giữ khóa thực tế, thay vì coi mọi bên xác minh bằng bí mật chung đều chỉ có khả năng đọc.

## 5. Xử lý nhiều issuer mà không tự mở rộng sự tin cậy

Một hệ thống SaaS có thể chấp nhận issuer nhân viên và issuer đối tác. Cần cấu hình riêng phạm vi quyền của từng nguồn, chẳng hạn:

| Issuer | Chủ thể dự kiến | Giới hạn sử dụng minh họa |
|---|---|---|
| `https://login.example.org/workforce` | Nhân viên | Các chức năng nhân sự được cấp quyền |
| `https://partners.example.net/tenant-a` | Người dùng đối tác A | Dữ liệu thuộc đối tác A |

Có thể cần đọc `iss` chưa được xác thực để chọn validator trong một tập issuer đã biết. Đây chỉ là bước định tuyến, không phải bước xác nhận danh tính.

Một mô hình xử lý minh họa là:

```text
Nhận token với giới hạn kích thước và định dạng
        → đọc issuer để tra cứu cấu hình, chưa tin các claim
        → chỉ tìm trong danh sách issuer đã được phê duyệt
        → không tìm thấy: từ chối
        → dùng validator gắn với issuer vừa chọn
        → xác thực mật mã và toàn bộ ràng buộc của profile
        → đối chiếu issuer trên kết quả đã được xác thực
        → áp dụng chính sách tenant, tài khoản và quyền
```

Không biến luồng này thành: “nhận issuer bất kỳ, tải khóa từ issuer ấy, chữ ký đúng thì cho vào”. Kẻ tấn công có thể điều khiển cả issuer lẫn khóa của một hệ thống riêng và tự cấp token mang quyền cao.

Việc truy cập URL từ dữ liệu chưa tin cậy còn tạo nguy cơ request phía máy chủ tới địa chỉ ngoài ý định. Không tự theo `jku`, `x5u` hoặc đường dẫn khóa do token cung cấp. Cần kiểm soát nguồn truy cập và việc chọn khóa; vấn đề này được nêu tại [RFC 8725, mục 3.10](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.10).

Trong cấu hình nhiều tenant, danh sách issuer được tin cậy có thể là cần thiết nhưng chưa đủ. Route hoặc tài nguyên thuộc tenant A phải có chính sách ràng buộc với tenant A; một token hợp lệ từ issuer tenant B không được tự động truy cập tenant A.

## 6. Issuer tạo phạm vi cho danh tính subject

Giả sử hai hệ thống phát hành cùng dùng `sub` bằng `user-42`:

```text
(https://login.example.org/workforce, user-42)
(https://partners.example.net/tenant-a, user-42)
```

Hai cặp này không mặc nhiên đại diện cùng một người. Nếu ứng dụng chỉ lấy `user-42` để tìm tài khoản nội bộ, người dùng đối tác có thể bị gắn nhầm vào tài khoản nhân viên.

Với danh tính OpenID Connect, cặp `iss` và `sub` là cơ sở định danh ổn định của người dùng trong ngữ cảnh issuer. Không dùng email hoặc tên hiển thị thay cho cặp định danh này khi liên kết tài khoản. Xem [OpenID Connect Core, mục 5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability).

Một mô hình lưu trữ nội bộ có thể dùng:

```text
ExternalIdentity
  issuer_identifier
  subject_identifier
  internal_account_id

Ràng buộc duy nhất: (issuer_identifier, subject_identifier)
```

Liên kết hai danh tính bên ngoài vào cùng tài khoản phải là một thao tác có chính sách xác minh và kiểm toán riêng. Không tự hợp nhất chỉ vì hai token có email giống nhau.

Đối với workload, cũng cần xác định rõ phạm vi subject và quyền tương ứng. Tên `billing-worker` ở môi trường thử nghiệm không nên tự được coi là workload production có quyền xử lý hóa đơn thật.

## 7. So khớp issuer chính xác và kiểm soát môi trường

Trong các profile yêu cầu exact match, đối chiếu toàn bộ issuer identifier. Không chỉ so tên miền, không dùng tiền tố để chấp nhận mọi path và không tự sửa chuỗi để làm mất sự khác biệt cấu hình.

Ví dụ API được cấu hình tin:

```text
https://login.example.org/workforce
```

Các giá trị sau không được chấp nhận chỉ vì trông tương tự:

```text
https://login.example.org/workforce/
https://login.example.org/partners
https://login.example.org/workforce-test
https://login.example.org.attacker.example/workforce
```

Một dịch vụ hỗ trợ các issuer ấy phải có cấu hình và chính sách riêng. Không áp dụng `startsWith("https://login.example.org")` hoặc chỉ kiểm tra chuỗi có chứa tên miền doanh nghiệp.

Khi triển khai sau reverse proxy, issuer được công bố có thể bị cấu hình nhầm thành địa chỉ HTTP nội bộ trong khi client và API mong đợi URL HTTPS công khai. Cách xử lý là sửa cấu hình URL chuẩn và cơ chế tin cậy proxy phù hợp, rồi đồng bộ metadata với bên nhận. Không giảm mức kiểm tra issuer để che sự khác biệt đó.

Việc đổi issuer khi di chuyển hệ thống IAM còn ảnh hưởng ánh xạ danh tính, do cặp issuer–subject có thể thay đổi. Kế hoạch chuyển đổi cần xử lý cả cấu hình validator, liên kết tài khoản, token còn hiệu lực và quyền của các nguồn cũ, mới.

## 8. Token opaque vẫn có bên phát hành

Không phải access token nào cũng là JWT có thể decode. Với token opaque, API không nên suy issuer bằng cách cắt chuỗi token hoặc giả định token luôn có ba phần phân tách bằng dấu chấm.

Một cơ chế thường dùng là introspection: resource server hỏi Authorization Server được cấu hình để lấy trạng thái và thông tin của token. Phản hồi có trường `active` và có thể có `iss`; `iss` không bắt buộc trong mọi phản hồi introspection. Xem [RFC 7662, mục 2.2](https://www.rfc-editor.org/rfc/rfc7662.html#section-2.2).

Quan hệ tin cậy khi đó bao gồm endpoint introspection đã xác minh, cơ chế bảo vệ kết nối, quyền gọi introspection và cách API áp dụng thông tin nhận về. API vẫn phải kiểm tra quyền truy cập tài nguyên theo hợp đồng triển khai; `active: true` không tự mang nghĩa có mọi quyền.

Trong hệ thống nhiều issuer dùng token opaque, cần có cách định tuyến được thiết kế trước, chẳng hạn cấu hình riêng theo tài nguyên hoặc tenant. Tránh gửi một bearer token lần lượt tới mọi endpoint không được xác định rõ, vì có thể làm lộ token cho bên không liên quan.

## 9. Sự cố thường gặp và cách chẩn đoán

Khi token bị từ chối vì issuer, hãy đối chiếu cấu hình hiệu lực thay vì chỉ nhìn tên nhà cung cấp IAM trên giao diện.

| Hiện tượng | Khả năng cần kiểm tra |
|---|---|
| Chữ ký đúng nhưng issuer mismatch | Có nhầm realm, tenant, môi trường hoặc URL chuẩn không |
| Token được phát từ cùng sản phẩm nhưng API từ chối | Hai cấu hình có thể là hai issuer độc lập |
| `kid` không tìm thấy sau rotation | Cache khóa, nguồn JWKS, phạm vi issuer và lịch chuyển khóa |
| Issuer đúng nhưng API vẫn từ chối | Audience, profile token, thời hạn hoặc điều kiện truy cập khác |
| Người dùng được gắn nhầm tài khoản | Có dùng `sub` riêng lẻ hoặc tự liên kết bằng email không |
| Đối tác có vai trò vượt phạm vi | Có ánh xạ claim thành quyền nội bộ mà thiếu giới hạn theo issuer không |

Trình tự chẩn đoán có thể gồm:

1. Xác nhận loại token và luồng cấp token đang dùng.
2. Xác nhận expected issuer của đúng API registration hoặc tenant.
3. So sánh issuer trong cấu hình, metadata và token; dữ liệu token chưa xác thực chỉ dùng cho chẩn đoán.
4. Kiểm tra nguồn khóa và kết quả xác thực chữ ký của validator.
5. Kiểm tra các điều kiện còn lại trước khi kết luận token được chấp nhận.
6. Sau khi sửa cấu hình, thử cả trường hợp hợp lệ và trường hợp issuer ngoài phạm vi.

Log nên có mã lỗi, registration, correlation ID và thông tin cấu hình cần thiết theo chính sách. Tránh ghi bearer token nguyên vẹn, khóa bí mật hoặc toàn bộ claim cá nhân vào log. Token xuất hiện trong log có thể trở thành thông tin truy cập bị lộ.

## 10. Tự kiểm tra bằng các quyết định của API

Giả sử API hóa đơn chỉ tin issuer nhân sự, audience phải là `urn:example:api:invoice` và token phải thuộc profile access token đã cấu hình:

| Tình huống | Kết quả mong đợi |
|---|---|
| Payload ghi đúng issuer nhưng chữ ký giả | Từ chối |
| Token hợp lệ do issuer đối tác chưa được phê duyệt cấp | Từ chối |
| Token hợp lệ từ issuer nhân sự nhưng dành cho API báo cáo | Từ chối |
| ID Token từ đúng issuer được gửi thay access token | Từ chối theo chính sách loại token của API |
| Token thỏa issuer, chữ ký, audience và thời hạn nhưng thiếu quyền đọc hóa đơn | Từ chối thao tác đọc hóa đơn |
| `sub` trùng tài khoản khác nhưng issuer khác | Không tự coi là cùng danh tính |
| Khóa mới chưa tải được và token chưa xác minh được | Không chấp nhận token chỉ để duy trì truy cập |

Khi đánh giá một issuer mới, cần trả lời được: bên đó được quyền xác nhận những chủ thể nào, claim nào có thể ánh xạ thành quyền gì, token được dùng ở tài nguyên nào và ai có quyền thay đổi cấu hình tin cậy. Đây là cách đưa kiểm tra issuer vào quản lý vòng đời quyền và nguyên tắc ít quyền nhất, thay vì chỉ coi `iss` là một chuỗi bắt buộc trong JWT.
