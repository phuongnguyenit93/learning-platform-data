# Thiết kế khóa cho phiên đăng nhập, cấu hình và dữ liệu tra cứu

Mô hình **khóa–giá trị (key–value)** lưu một giá trị dưới một khóa xác định. Khi ứng dụng đã biết khóa, việc tìm giá trị thường rất thuận tiện: `GET key`, `SET key value` hoặc thao tác tương đương trong hệ quản trị đang dùng. Nhưng điểm mạnh này cũng tạo ra trách nhiệm thiết kế: **ứng dụng phải định nghĩa khóa nào đại diện cho đối tượng nào, khóa có duy nhất trong phạm vi nào, tồn tại bao lâu và phải làm gì khi giá trị đổi hoặc biến mất**.

Ba nhu cầu rất thường gặp là:

- **Phiên đăng nhập (session):** tra cứu trạng thái xác thực từ một token ngẫu nhiên, có thời hạn và có thể thu hồi.
- **Cấu hình (configuration):** đọc thiết lập ứng dụng theo môi trường, dịch vụ và khách hàng; phải biết bản nào được ưu tiên và lúc nào thay đổi có hiệu lực.
- **Dữ liệu tra cứu (lookup):** chuyển một mã, tên chuẩn hóa hoặc khóa bên ngoài thành ID hay dữ liệu thường dùng; cần kiểm soát dữ liệu cũ và tính nhất quán với nguồn chính.

Cùng là `key -> value`, ba nhóm này có **quy tắc về danh tính, thời hạn, cập nhật, bảo mật và độ tin cậy khác nhau**. Không thể chọn chung một quy ước kiểu `"user:" + id` rồi áp dụng một TTL cho tất cả.

Bài học dùng Redis làm ví dụ vì cú pháp khóa rõ ràng và có hỗ trợ TTL, lệnh điều kiện, nhiều kiểu giá trị. Những nguyên tắc đặt tên, phân vùng và vòng đời còn áp dụng được cho nhiều key–value store khác, nhưng chi tiết atomicity, durability, consistency và cách xử lý TTL luôn phụ thuộc sản phẩm cụ thể.

## 1. Bắt đầu từ thao tác truy cập, không bắt đầu từ tên khóa

Với mô hình key–value, trước tiên cần biết ứng dụng truy cập dữ liệu **bằng thông tin nào**.

| Nhu cầu | Ứng dụng biết gì khi đọc? | Cần lấy gì? | Thời hạn thường mong muốn |
|---|---|---|---|
| Kiểm tra session | Token trong cookie hoặc request | User ID, tenant, trạng thái và mốc hết hạn | Ngắn, có thể gia hạn có kiểm soát |
| Kiểm tra cấu hình toàn dịch vụ | Môi trường, tên dịch vụ | Cấu hình chung hoặc một snapshot | Dài hơn; thay đổi theo phiên bản |
| Cấu hình riêng tenant | Tenant đã xác thực, tính năng | Giá trị override hay cấu hình hiệu lực | Theo chính sách cập nhật và cache |
| Tra cứu SKU | Tenant và SKU đã chuẩn hóa | Product ID hoặc snapshot sản phẩm | TTL phù hợp với tốc độ thay đổi |
| Tra cứu mã đối tác | Nguồn cấp, tài khoản đối tác, mã ngoài | Internal ID | Có thể cần lưu bền vững, tùy nghiệp vụ |
| Tra cứu danh mục ít thay đổi | Mã danh mục | Nhãn hiển thị, metadata | Dài hơn; cần cơ chế vô hiệu hóa |

Sự khác biệt chủ yếu không nằm ở độ dài khóa. Nó nằm ở **tính đúng đắn của kết quả khi nhiều người dùng cùng truy cập, khi giá trị bị sửa, khi key hết hạn và khi hệ key–value không khả dụng**.

Ví dụ, cache thiếu một SKU có thể truy vấn lại database rồi phục hồi. Ngược lại, session biến mất có thể buộc người dùng đăng nhập lại. Một cấu hình thanh toán bị đọc nhầm tenant có thể gây tác động nghiêm trọng dù thao tác `GET` chỉ mất vài mili giây.

## 2. Một khóa tốt phải xác định được phạm vi và ý nghĩa

Một quy ước đặt tên hữu ích có thể gồm các phần:

~~~text
<nhóm>:<phiên-bản-key>:<môi-trường>:<dịch-vụ>:<phạm-vi>:<định-danh>
~~~

Không bắt buộc khóa nào cũng có đủ các thành phần này. Cấu trúc có thể ngắn hơn khi thông tin đã được cô lập bằng cluster/database riêng. Điều quan trọng là **cùng một dạng khóa luôn có cùng ngữ nghĩa**.

Ví dụ minh họa:

~~~text
auth:session:v1:prod:7f83b1657ff1fc53...
cfg:v2:prod:checkout:global
cfg:v2:prod:checkout:tenant:shop-17
lookup:product-sku:v1:prod:shop-17:SP-001
lookup:category:v1:prod:vi-VN:ACCESSORY
rate:login:v1:prod:account-284
~~~

Với từng mẫu, hãy trả lời:

1. **Namespace là gì?** Khóa này thuộc session, cấu hình, tra cứu hay kiểm soát lưu lượng?
2. **Có cần version trong tên không?** Nếu đổi định dạng value hoặc cách tạo key, làm sao chuyển từng bước?
3. **Phạm vi duy nhất là gì?** Toàn hệ thống, một tenant, một dịch vụ, ngôn ngữ hay một môi trường?
4. **Định danh đến từ nguồn nào?** Đã được xác thực và chuẩn hóa chưa?
5. **Ai tạo, cập nhật, xóa key?** Chỉ một service hay nhiều producer?
6. **TTL và eviction có được phép không?** Mất key ảnh hưởng nghiệp vụ thế nào?
7. **Ai có thể quan sát tên khóa?** Tên khóa có chứa bí mật hoặc dữ liệu cá nhân không?

### 2.1. Phân cách và mã hóa các thành phần khóa

Ghép chuỗi ngây thơ rất dễ va chạm:

~~~text
tenant = "a:b", code = "c"  -> lookup:a:b:c
tenant = "a",   code = "b:c" -> lookup:a:b:c
~~~

Hai cặp đầu vào khác nhau tạo cùng một khóa.

Có thể giải quyết bằng **định dạng đã định nghĩa trước**: kiểm tra character set của mỗi thành phần, mã hóa chiều dài, percent-encode theo một quy ước thống nhất hoặc dùng hash có prefix. Không để dữ liệu người dùng tùy ý chèn dấu phân tách rồi tin rằng có thể tách ngược chính xác.

Ví dụ nếu SKU chỉ cho phép chữ ASCII viết hoa, số và gạch nối, ứng dụng có thể chuẩn hóa thành `skuKey` trước khi ghép. Với tenant ID do hệ thống sinh, cũng cần quy định định dạng hợp lệ của ID. Nếu phải dùng chuỗi tự do hoặc Unicode, sử dụng bộ mã hóa ổn định và test trường hợp ký tự đặc biệt, khoảng trắng, chữ hoa/thường.

### 2.2. Tránh tên khóa chứa dữ liệu nhạy cảm

Không đưa trực tiếp mật khẩu, access token, session token, mã xác thực một lần hoặc thông tin cá nhân nhạy cảm vào tên khóa. Tên key có thể xuất hiện trong log, công cụ giám sát, trace hoặc bản dump phục vụ vận hành.

Thay vì:

~~~text
session:raw-token-from-user
~~~

nên dùng khóa tạo từ **dấu vết một chiều** của token có entropy đủ cao, chẳng hạn SHA-256 hoặc HMAC với khóa bí mật do server quản lý, tùy threat model:

~~~text
auth:session:v1:prod:<digest-của-token>
~~~

Giá trị digest vẫn là một định danh kỹ thuật cần được bảo vệ trong log và công cụ vận hành. Không in cả token gốc lẫn digest nếu không có nhu cầu chẩn đoán được phê duyệt.

## 3. Thiết kế session: token, key và value có vai trò khác nhau

Phiên đăng nhập lưu trên server thường dùng một **opaque session token** do server tạo sau khi xác thực thành công. Browser giữ token trong cookie; mỗi request gửi lại token để server tìm session tương ứng.

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant A as Ứng dụng
    participant KV as Key–value store

    U->>A: Đăng nhập bằng thông tin xác thực
    A->>A: Xác thực và tạo token ngẫu nhiên
    A->>A: Tính digest(token)
    A->>KV: SET session:<digest> -> trạng thái, TTL
    KV-->>A: Ghi thành công
    A-->>U: Set-Cookie session=<token>
    U->>A: Request kèm cookie
    A->>A: Tính digest(token)
    A->>KV: GET session:<digest>
    KV-->>A: User ID + hạn hiệu lực + metadata
    A->>A: Kiểm tra trạng thái và quyền
    A-->>U: Phản hồi theo quyền truy cập
~~~

**Token** là bằng chứng sở hữu session; **key** là địa chỉ tra cứu; **value** mô tả người dùng và vòng đời của phiên. Không xem token là user ID và không dùng email hay số điện thoại làm session key. Nhiều thiết bị hoặc nhiều lần đăng nhập của cùng một người cần có thể tồn tại như những session riêng.

Ví dụ value:

~~~json
{
  "userId": "u-2048",
  "tenantId": "shop-17",
  "createdAt": "2026-11-14T08:00:00Z",
  "lastSeenAt": "2026-11-14T08:03:00Z",
  "absoluteExpiresAt": "2026-11-21T08:00:00Z",
  "authLevel": "PASSWORD_MFA",
  "sessionVersion": 2
}
~~~

Đây là dữ liệu minh họa. Chỉ lưu các thuộc tính thực sự cần để xử lý session, phân quyền hoặc quản trị. Những thuộc tính có thể thay đổi bất ngờ như vai trò người dùng, quyền truy cập tenant và trạng thái tài khoản cần có **chính sách làm mới và thu hồi**. Lưu role trong session rồi giữ mãi có thể khiến quyền cũ vẫn hiệu lực sau khi bị thu hồi.

### 3.1. Sinh token đủ mạnh

Token cần được sinh bằng bộ tạo số ngẫu nhiên dùng cho bảo mật (CSPRNG), có đủ entropy để khó đoán. Ví dụ 32 byte ngẫu nhiên mã hóa base64url không padding:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class SessionTokens {
    private static final SecureRandom RANDOM = new SecureRandom();

    private SessionTokens() {}

    public static String newToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

Đoạn code cho cách tạo token, chưa bao gồm toàn bộ xử lý đăng nhập, cookie, bảo vệ thông tin trong memory và lưu session. Không dùng `Random` thông thường, timestamp hoặc `userId + currentTimeMillis` làm token bảo mật.

Với token ngẫu nhiên đủ entropy, một digest SHA-256 ổn định có thể dùng làm khóa tra cứu; HMAC có bí mật phía server cung cấp thêm ranh giới bảo vệ khi thiết kế đòi hỏi. Bất kể cách nào, **token thô phải được giữ kín** và các hoạt động xác thực/ủy quyền vẫn cần được kiểm tra đầy đủ.

### 3.2. Cookie session

Một ví dụ header:

~~~http
Set-Cookie: __Host-session=<opaque-token>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính có ý nghĩa:

- `Secure`: trình duyệt chỉ gửi cookie qua HTTPS.
- `HttpOnly`: JavaScript trang không đọc trực tiếp cookie.
- `SameSite`: giúp giảm một số tình huống request từ site khác; vẫn cần thiết kế phòng chống CSRF phù hợp với luồng ứng dụng.
- Prefix `__Host-`: khi được browser hỗ trợ, yêu cầu `Secure`, `Path=/` và không có `Domain` để giảm rủi ro cookie bị ghi đè theo domain.

Không để session token vào URL vì URL dễ bị ghi vào lịch sử, log hoặc header tham chiếu. TLS và chính sách origin/cookie là một phần của thiết kế session, song không thay thế kiểm tra quyền trong service.

## 4. TTL của session: hết hạn khi không hoạt động và hết hạn tuyệt đối

Session thường có ít nhất hai khái niệm thời hạn:

- **Idle timeout:** session hết hiệu lực nếu không có hoạt động hợp lệ trong khoảng đã quy định.
- **Absolute timeout:** session hết hiệu lực chậm nhất tại một mốc cố định, dù người dùng hoạt động liên tục.

Ví dụ:

~~~text
Thời điểm đăng nhập:       08:00, ngày 14/11
Idle timeout:             15 phút
Absolute timeout:         7 ngày
Hoạt động hợp lệ lúc:     08:03, 08:10, 08:20
Hạn tuyệt đối:            08:00, ngày 21/11
~~~

Trong Redis, có thể tạo session với TTL ban đầu:

~~~redis
SET auth:session:v1:prod:<tokenDigest> '{"userId":"u-2048","absoluteExpiresAt":"2026-11-21T08:00:00Z"}' EX 900 NX
~~~

Ở đây:

- `EX 900` đặt thời gian hết hạn 900 giây.
- `NX` chỉ ghi nếu key chưa tồn tại, hữu ích khi tạo session mới.
- `GET` hoặc `HGETALL` thông thường **không tự gia hạn TTL**.
- `EXPIRE key seconds` có thể dùng để cập nhật TTL sau khi xác minh session còn hợp lệ.

Khi thực hiện sliding idle timeout, không đơn giản `EXPIRE 900` ở mọi request mà quên absolute deadline. Thời gian gia hạn còn lại nên được giới hạn:

\[
TTL_{\text{mới}} = \min(T_{\text{idle}},\ T_{\text{absolute}} - T_{\text{now}})
\]

Nếu `T_absolute <= T_now`, phiên phải bị từ chối và có thể xóa. Việc kiểm tra token, trạng thái và gia hạn cần tính đến concurrency và logout/revocation; nếu nhiều lệnh phải cùng tạo một chuyển trạng thái bất biến, dùng cơ chế atomic được hệ quản trị hỗ trợ.

### 4.1. TTL không phải lời hứa chính xác tới từng mili giây

TTL là cơ chế lưu trữ và dọn dẹp; hệ quản trị có thể xử lý việc thu hồi bộ nhớ bất đồng bộ, còn thời điểm chặn truy cập tùy cách engine kiểm tra expiry. Với session, ứng dụng nên có **mốc hết hạn trong hợp đồng trạng thái** và kiểm tra hạn đó khi cần mức bảo đảm rõ ràng.

Không dùng “khóa còn có mặt” làm toàn bộ kết luận xác thực nếu trạng thái người dùng đã bị khóa, phiên đã bị thu hồi hoặc mốc tuyệt đối đã qua.

### 4.2. Sliding expiration không nên gia hạn ở mọi request phụ

Một ảnh tĩnh, polling hoặc background API có thể khiến session không bao giờ đạt idle timeout dù người dùng đã rời máy. Cần xác định **thế nào là hoạt động hợp lệ**, có thể chỉ gia hạn theo thao tác tương tác hoặc giới hạn tần suất cập nhật `lastSeenAt` để tránh biến mỗi lượt đọc thành một lượt ghi vào Redis.

## 5. Đăng xuất, thu hồi và quản lý nhiều phiên

Nếu mỗi session có khóa độc lập, đăng xuất ở một thiết bị tương đối trực tiếp:

~~~redis
DEL auth:session:v1:prod:<tokenDigest>
~~~

Nhưng yêu cầu “đăng xuất khỏi tất cả thiết bị” khó hơn. Không nên dùng `KEYS auth:session:*` để quét toàn bộ không gian key ở hệ thống lớn.

Có thể quản lý một quan hệ phụ:

~~~text
auth:user-sessions:v1:prod:u-2048 -> tập các session digest/ID
~~~

Khi tạo session, thêm session vào tập; khi thu hồi, xóa session và cập nhật tập. **Tập phụ có thể bị lệch** vì session tự hết hạn nhưng phần tử trong tập chưa được xóa, hoặc vì một trong nhiều lệnh ghi thất bại. Cần thiết kế dọn dẹp và cơ chế đồng bộ phù hợp.

Một phương án khác là **session generation/version**:

~~~text
user:u-2048:sessionGeneration = 8
session value: sessionGeneration = 8
~~~

Khi quản trị yêu cầu thu hồi toàn bộ session, tăng generation theo một thao tác nhất quán; mọi request so sánh version session với version hiện hành. Thiết kế này cần biết nơi lưu generation đáng tin cậy, chính sách cache và cách xử lý khi nơi kiểm tra không khả dụng.

Lựa chọn phụ thuộc yêu cầu sản phẩm:

- Thu hồi đúng một phiên hay toàn bộ phiên?
- Thu hồi có cần hiệu lực ngay hay cho phép một khoảng trễ?
- Có cần liệt kê các thiết bị đang đăng nhập không?
- Có cần hỗ trợ hoạt động khi một replica đang trễ không?
- Có chấp nhận đăng xuất ngoài ý muốn khi cache/session store mất dữ liệu không?

Nếu yêu cầu thu hồi nghiêm ngặt, không chỉ dựa vào một bản sao cache cuối cùng nhất quán mà không xác định cửa sổ trễ.

### 5.1. Session rotation

Sau đăng nhập, nâng mức xác thực hoặc sự kiện bảo mật quan trọng, có thể sinh token session mới và vô hiệu token cũ để hạn chế nguy cơ session fixation. Khi đổi token, cần tránh tình huống hai request cùng dùng phiên cũ và vô tình khôi phục lại trạng thái đã thu hồi. Có thể dùng transaction, script/atomic command hoặc version phù hợp với topology.

### 5.2. Session server-side khác JWT tự chứa

Một JWT có chữ ký và tự chứa claims có thể được kiểm tra mà không cần truy vấn session store trên mọi request. Tuy nhiên, **thu hồi ngay lập tức** hoặc theo dõi từng thiết bị có thể cần danh sách thu hồi, version hoặc hệ thống session bổ sung. Ngược lại, opaque session có trạng thái ở server dễ thu hồi bằng xóa key nhưng phụ thuộc vào khả năng sẵn sàng của kho session.

Không có lựa chọn nào “luôn tốt hơn”; cần chọn theo bài toán bảo mật, tải, thời hạn, tính sẵn sàng và khả năng vận hành.

## 6. Thiết kế khóa cho cấu hình: global, môi trường và tenant

Cấu hình khác session ở chỗ nhiều request cùng đọc một giá trị, nhưng **ít ghi hơn**, cần audit và phải biết nguồn nào đang có hiệu lực.

Ví dụ dịch vụ checkout có các thiết lập:

~~~json
{
  "currency": "VND",
  "maxCartItems": 50,
  "reservationMinutes": 15,
  "enableVoucherStacking": false
}
~~~

Ứng dụng có thể có:

- Giá trị mặc định đóng gói trong code.
- Cấu hình theo môi trường `dev`, `staging`, `prod`.
- Cấu hình theo region hoặc cụm triển khai.
- Override theo tenant hoặc nhóm khách hàng.
- Feature flag theo nhóm người dùng được phép.

Không nên tự đặt một key `config:checkout` rồi không rõ đó là cấu hình ở môi trường nào. Một quy ước:

~~~text
cfg:v1:prod:checkout:global
cfg:v1:prod:checkout:region:ap-southeast
cfg:v1:prod:checkout:tenant:shop-17
cfg:v1:prod:checkout:tenant:shop-42
~~~

Mỗi khóa có thể lưu một object chứa một nhóm thuộc tính liên quan:

~~~json
{
  "revision": 12,
  "updatedAt": "2026-11-14T08:00:00Z",
  "updatedBy": "config-service",
  "data": {
    "maxCartItems": 80,
    "enableVoucherStacking": true
  }
}
~~~

`updatedBy` trong ví dụ nên là định danh service hoặc metadata audit không tiết lộ bí mật. Với hệ cấu hình nghiêm túc, lịch sử thay đổi và quyền sửa thường được lưu ở một nguồn có kiểm soát hơn là chỉ phụ thuộc giá trị cache.

## 7. Thứ tự ưu tiên và cách hợp nhất cấu hình

Nếu cả global và tenant đều có `maxCartItems`, ứng dụng phải có thứ tự ưu tiên **công bố trước**.

Ví dụ chính sách:

~~~text
Mặc định từ code
  -> Global theo môi trường
  -> Override theo khu vực
  -> Override theo tenant
  -> Quy tắc tính năng đặc biệt có định nghĩa riêng
~~~

Trong đó tầng sau có thể ghi đè tầng trước. Nhưng quy tắc **merge sâu object**, **thay nguyên mảng**, **xử lý null** và **xóa một override** phải được xác định rõ.

Ví dụ:

~~~json
// Global
{
  "maxCartItems": 50,
  "reservationMinutes": 15,
  "enableVoucherStacking": false
}
~~~

~~~json
// Tenant shop-17 chỉ ghi trường muốn override
{
  "maxCartItems": 80
}
~~~

Kết quả mong muốn của cơ chế merge theo trường:

~~~json
{
  "maxCartItems": 80,
  "reservationMinutes": 15,
  "enableVoucherStacking": false
}
~~~

Ngược lại, nếu code hiểu override là **thay toàn bộ object**, hai trường còn lại biến mất. Đây là khác biệt lớn về hợp đồng cấu hình, không phải chi tiết triển khai nhỏ.

### 7.1. Ba trạng thái phải được phân biệt

- **Không có override:** kế thừa giá trị từ tầng trước.
- **Override bằng giá trị `false` hoặc `0`:** giá trị hợp lệ, không được hiểu là “thiếu”.
- **Override bằng `null`:** cần định nghĩa là xóa, tắt, trở về mặc định hoặc không hợp lệ.

Một lỗi dễ gặp:

~~~javascript
// Sai nếu 0 hoặc false là giá trị override hợp lệ.
const effectiveValue = tenantValue || globalValue;
~~~

Nếu `tenantValue = false` hoặc `0`, code sẽ lấy global. Với trường đơn giản, có thể dùng kiểm tra tồn tại tường minh hoặc nullish coalescing **chỉ khi `null` được quy định là không có override**. Với hợp nhất nhiều field, nên dùng hàm merge có hợp đồng và validation rõ ràng.

### 7.2. Bảo vệ kiểu và miền giá trị

Bản ghi cấu hình nên được validate như dữ liệu nghiệp vụ:

- `maxCartItems` là số nguyên dương trong khoảng cho phép.
- `reservationMinutes` có giới hạn để tránh giữ tồn kho quá lâu.
- `enableVoucherStacking` là Boolean.
- Các trường quan trọng có default an toàn và chính sách khi không tải được cấu hình.
- Tránh cấu hình tùy ý thay đổi các bất biến phải được thực thi ở tầng domain.

Cấu hình sai có thể làm dịch vụ lỗi hàng loạt. Quy trình phê duyệt, phân quyền, version, kiểm thử trước khi rollout và khả năng rollback đặc biệt quan trọng với các thiết lập ảnh hưởng thanh toán, bảo mật hoặc dữ liệu.

## 8. Cập nhật cấu hình nhất quán khi nhiều instance cùng đọc

Giả sử một cấu hình cần đổi hai trường cùng lúc:

~~~json
{
  "reservationMinutes": 20,
  "enableVoucherStacking": true
}
~~~

Nếu viết thành hai key độc lập, một instance có thể đọc trường mới của key thứ nhất nhưng vẫn thấy trường cũ ở key thứ hai. Với những thuộc tính bắt buộc phải đi cùng nhau, nên cân nhắc một **snapshot cấu hình**:

~~~text
cfg:v1:prod:checkout:snapshot:rev-12 -> toàn bộ object phiên bản 12
cfg:v1:prod:checkout:snapshot:rev-13 -> toàn bộ object phiên bản 13
cfg:v1:prod:checkout:current -> rev-13
~~~

Một quy trình triển khai:

1. Tạo snapshot `rev-13` hoàn chỉnh và xác thực hợp lệ.
2. Đảm bảo snapshot sẵn sàng để đọc.
3. Đổi con trỏ `current` sang `rev-13` bằng thao tác thích hợp.
4. Reader lấy revision trước, rồi tải đúng một snapshot.
5. Giữ các phiên bản cũ đủ lâu cho các reader đang xử lý; dọn chúng sau theo chính sách.
6. Khi rollback, chuyển con trỏ về revision cũ đã biết là hợp lệ.

Cần lưu ý: khi reader đọc pointer rồi snapshot, hệ thống phải bảo đảm snapshot chưa bị xóa hoặc bị thay đổi giữa chừng. Redis cung cấp tính nguyên tử cho nhiều lệnh đơn riêng lẻ; không phải mọi chuỗi `GET` rồi `SET` hoặc cập nhật nhiều key tự động là một transaction đầy đủ. Khi cần so sánh revision và cập nhật có điều kiện, có thể dùng `WATCH/MULTI/EXEC` hoặc script phù hợp với Redis và cấu hình cluster.

### 8.1. TTL cho cấu hình khác TTL của session

Không nên tự động đặt TTL 15 phút cho mọi key cấu hình chỉ vì session dùng 15 phút. Với cấu hình, cần phân biệt:

- **Nguồn sự thật:** hệ quản lý cấu hình hay database bền vững.
- **Bản cache cấu hình:** có thể có TTL, revision và cơ chế invalidation.
- **Thời gian chấp nhận cấu hình cũ:** có thể vài giây với feature flag, nhưng rất ngắn hoặc bằng không đối với một số chính sách bảo mật.
- **Hành vi khi cache miss:** tải lại nguồn; nếu nguồn cũng lỗi, dùng last-known-good hay ngừng chức năng? Cần quyết định theo mức độ rủi ro.

Nếu key Redis là **nguồn duy nhất** của cấu hình thiết yếu, eviction hoặc mất dữ liệu có thể làm toàn hệ thống thay đổi hành vi. Nên có kế hoạch backup, khôi phục, audit và kiểm soát quyền ghi phù hợp.

### 8.2. Bí mật không phải cấu hình tùy ý

Password database, private key và token truy cập bên thứ ba nên được xử lý theo hệ thống quản lý secret và quyền truy cập chuyên biệt, với encryption/rotation/audit thích hợp. Không trộn secret vào các value cấu hình được cache hoặc log cùng metadata thông thường.

## 9. Dữ liệu tra cứu: từ khóa nghiệp vụ đến ID ổn định

Một nhu cầu phổ biến:

> Người bán nhập SKU `"sp-001"`. Hệ thống phải tìm sản phẩm thuộc đúng tenant.

Trong nguồn dữ liệu chính, sản phẩm có thể dùng `productId` kỹ thuật ổn định và unique index trên `(tenantId, skuKey)`. Tầng key–value lưu bản tra cứu:

~~~text
lookup:product-sku:v1:prod:shop-17:SP-001 -> p-101
~~~

Ở đây:

- `shop-17` là phạm vi tenant.
- `SP-001` là SKU đã chuẩn hóa theo cùng quy tắc của nguồn chính.
- `p-101` là định danh sản phẩm ổn định.
- `v1` biểu thị phiên bản hợp đồng key/value.
- `prod` tách môi trường khi dùng cùng hệ thống lưu trữ.

Cách đặt này cho phép hai tenant cùng có SKU `SP-001` mà không va chạm.

### 9.1. Lookup key khác business unique constraint

Một cache key chứa `(tenantId, skuKey)` **không có nghĩa database nguồn tự cấm SKU trùng**. Cache có thể bị xóa, hết hạn hoặc bị ghi đè. Nếu SKU phải duy nhất trong tenant, nguồn chính cần unique index/conditional write/transaction hoặc cơ chế nhất quán tương ứng của hệ quản trị đang dùng.

Có thể xem lookup store là **chỉ mục tăng tốc**, trừ khi kiến trúc đã chủ động thiết kế nó làm nguồn sự thật và chứng minh được các thuộc tính durability/consistency cần thiết.

### 9.2. Cache-aside cho dữ liệu tra cứu

Một luồng đọc điển hình:

~~~mermaid
flowchart TD
    A["Nhận tenant đã xác thực và SKU"] --> B["Chuẩn hóa SKU"]
    B --> C["Tạo lookup key"]
    C --> D["Đọc cache"]
    D --> E{"Có giá trị hợp lệ?"}
    E -->|Có| F["Trả Product ID / dữ liệu"]
    E -->|Không| G["Truy vấn nguồn chính"]
    G --> H{"Tìm thấy?"}
    H -->|Có| I["Cache giá trị với TTL"]
    I --> F
    H -->|Không| J["Trả Not Found và áp dụng chính sách negative cache"]
~~~

Giả mã:

~~~python
def lookup_product_id(tenant_id, raw_sku):
    # tenant_id đến từ ngữ cảnh đã xác thực.
    sku_key = normalize_sku(raw_sku)
    cache_key = build_key("lookup", "product-sku", "v1",
                          "prod", tenant_id, sku_key)

    cached = cache.get(cache_key)
    if cached is not None:
        if cached == "NOT_FOUND":
            return None
        return cached

    product = product_repository.find_by_tenant_and_sku(
        tenant_id, sku_key
    )
    if product is None:
        cache.set(cache_key, "NOT_FOUND", ttl_seconds=15)
        return None

    cache.set(cache_key, product.id, ttl_seconds=300)
    return product.id
~~~

Đây là pseudo-code; `build_key` và các đối tượng khác là cơ chế phải triển khai. Giá trị `"NOT_FOUND"` cần được mã hóa có phân biệt với ID hợp lệ. TTL 15 và 300 giây là **giả định minh họa**, không phải thông số đúng cho mọi hệ thống.

### 9.3. Negative caching và dữ liệu vừa tạo

Khi SKU không tồn tại, ghi kết quả âm trong thời gian ngắn có thể giảm nhiều request lặp. Nhưng nếu ngay sau đó người dùng tạo sản phẩm với SKU ấy, negative cache còn tồn tại sẽ trả “không tìm thấy” sai trong một khoảng thời gian.

Có thể giải quyết bằng vô hiệu hóa cache tại đường tạo sản phẩm, TTL âm ngắn, hoặc thiết kế yêu cầu đọc mạnh tại một số thao tác. Đừng để kết quả âm tồn tại quá lâu đối với dữ liệu có thể được tạo bất cứ lúc nào.

## 10. Lookup có thể cũ sau khi dữ liệu đổi

Giả sử người bán đổi SKU của `p-101` từ `SP-001` sang `KB-001`.

Nguồn chính sau cập nhật:

~~~text
(tenantId = shop-17, skuKey = KB-001) -> productId = p-101
~~~

Cache trước cập nhật vẫn có thể giữ:

~~~text
lookup:product-sku:v1:prod:shop-17:SP-001 -> p-101
~~~

Đồng thời lookup mới có thể chưa được tạo. Nếu ứng dụng chỉ thay đổi database mà không nghĩ tới cache, người dùng có thể tìm thấy sản phẩm bằng mã cũ hoặc không tìm thấy bằng mã mới.

Một cơ chế invalidation cơ bản cần:

1. Chuẩn hóa và ghi SKU mới tại nguồn chính, chịu unique constraint của nguồn.
2. Sau khi thay đổi được xác nhận thành công, vô hiệu key lookup cũ.
3. Vô hiệu key lookup mới hoặc ghi giá trị mới theo chính sách cache.
4. Xử lý request đang thực hiện đồng thời và tình huống xóa cache thất bại.
5. Nếu có nhiều bản cache theo ngôn ngữ/tenant/biến thể, xác định danh sách key phụ thuộc.

### 10.1. Vì sao delete cache không bảo đảm hoàn toàn tránh dữ liệu cũ?

Một race điển hình:

~~~text
Request A đọc cache miss
Request A đọc giá trị cũ từ database

Request B cập nhật database sang giá trị mới
Request B xóa cache

Request A ghi giá trị cũ vào cache sau khi B xóa
~~~

Lúc này cache giữ giá trị cũ dù đường cập nhật đã invalidation. TTL giới hạn thời gian sai lệch; nếu nghiệp vụ không chấp nhận sai lệch, cần thiết kế **versioning, đọc kiểm tra revision, cập nhật cache có điều kiện hoặc chiến lược đồng bộ khác**.

Các cách phổ biến:

- **TTL hữu hạn:** đơn giản, phù hợp dữ liệu cho phép stale trong khoảng nhất định.
- **Invalidation theo sự kiện:** giảm thời gian stale nhưng phụ thuộc độ tin cậy của event và consumer.
- **Version trong cache value:** reader xác minh revision ở nguồn hoặc theo một token đáng tin cậy khi cần.
- **Key theo version/epoch:** đổi version giúp reader không tiếp tục dùng key cũ; cần quản lý version và dọn key cũ.
- **Ghi lại từ nguồn khi cần kết quả chắc chắn mới:** bỏ qua cache cho những thao tác quan trọng.

Không có “xóa cache một lần” nào thay thế được mô hình nhất quán phù hợp với hợp đồng nghiệp vụ.

## 11. Giá trị tra cứu nên là ID hay cả document?

Hai chiến lược:

~~~text
lookup:product-sku:...:SP-001 -> p-101
~~~

hoặc

~~~json
{
  "productId": "p-101",
  "name": "Bàn phím cơ",
  "priceMinor": 450000,
  "revision": 18
}
~~~

### Chỉ lưu ID

Ưu điểm: value nhỏ, ít dữ liệu stale, dễ định danh đúng tài nguyên. Nhược điểm: sau khi tìm ID, có thể phải đọc sản phẩm từ nguồn chính hoặc cache khác.

### Lưu snapshot sản phẩm

Ưu điểm: tiết kiệm truy vấn trong những đường đọc thường xuyên. Nhược điểm: giá, trạng thái bán hoặc quyền hiển thị có thể cũ. Cần xác định field nào có thể cache, trong bao lâu và liệu cần kiểm tra lại nguồn chính trước hành động có hậu quả nghiệp vụ.

Ví dụ, tên hiển thị danh mục có thể chấp nhận cũ vài phút. Giá chốt đơn, số lượng tồn kho, hạn mức hoặc quyền truy cập thường không nên dựa chỉ vào snapshot cũ mà không có kiểm tra nhất quán tại thời điểm ghi.

### Dữ liệu tra cứu bền vững khác cache

Một bảng mapping `(provider, externalOrderId) -> internalOrderId` có thể là **dữ liệu nghiệp vụ cần tồn tại lâu dài và có uniqueness**. Nếu mất mapping sẽ gây tạo đơn lặp hoặc gộp nhầm, thì không nên coi nó như cache có thể tùy ý eviction. Khi ấy dùng key–value database có cơ chế bền vững, conditional write và chính sách backup phù hợp, hoặc lưu mapping ở nguồn transactional đáng tin cậy rồi cache kết quả tra cứu.

## 12. Phân biệt missing key, value rỗng và lỗi hệ thống

Với mô hình key–value, ba trạng thái này cần khác nhau:

| Tình trạng | Ý nghĩa | Cách xử lý gợi ý |
|---|---|---|
| **Key không tồn tại** | Chưa cache, đã hết TTL hoặc dữ liệu thực sự không có | Tra nguồn chính nếu đó là cache; hoặc thực hiện luồng not found của nguồn sự thật |
| **Key tồn tại nhưng value rỗng/`null`** | Có thể là giá trị hợp lệ hoặc dữ liệu lỗi | Quy định rõ schema value, tránh suy đoán |
| **Lỗi kết nối/timeout** | Không thể biết key hiện có hay không | Theo chính sách fail-open/fail-closed của từng loại dữ liệu, có quan sát và retry hữu hạn |
| **Giá trị có version không hỗ trợ** | Reader và writer không tương thích | Bỏ cache và tải lại/adapter, hoặc báo lỗi theo chính sách |
| **Key đã hết hạn** | Không còn hiệu lực theo TTL | Session thường từ chối; cache có thể tải lại |
| **Value sai kiểu** | Có lỗi ghi, deploy hoặc migration | Không ép kiểu im lặng; ghi nhận và sửa nguồn |

**Không được xử lý timeout Redis như “không tìm thấy session nhưng cứ cho truy cập”.** Với xác thực, nếu không thể xác minh session hợp lệ thì cần hành vi an toàn đã xác định, thường là từ chối hoặc yêu cầu xác thực lại.

Với cache tra cứu không mang tính quyết định bảo mật, lỗi cache có thể được xem là cache miss và truy vấn nguồn chính, nhưng phải tính khả năng source bị dồn tải khi cache hỏng. Với cấu hình, chính sách lỗi tùy mức quan trọng: có thể dùng last-known-good đã được xác thực cho một số thiết lập, nhưng không tùy tiện dùng cấu hình mặc định làm suy yếu bảo mật.

## 13. TTL, eviction và retention: đừng dùng một chính sách chung

Trong Redis, TTL điều khiển vòng đời của key; **eviction policy** là cách server xử lý khi chạm giới hạn bộ nhớ. Hai cơ chế này khác nhau.

Ví dụ:

~~~redis
SET lookup:category:v1:prod:vi-VN:ACCESSORY '{"label":"Phụ kiện"}' EX 3600
TTL lookup:category:v1:prod:vi-VN:ACCESSORY
DEL lookup:category:v1:prod:vi-VN:ACCESSORY
~~~

Lưu ý:

- `TTL` trả thời gian còn lại tính theo giây hoặc giá trị đặc biệt nếu key thiếu hay không có expiry.
- `GET` không tự gia hạn hạn sử dụng.
- Lệnh cập nhật giá trị có thể thay đổi hoặc loại bỏ TTL tùy cú pháp/lệnh; phải dùng đúng lựa chọn giữ TTL nếu cần.
- TTL càng đồng đều có thể tạo nhiều cache miss cùng thời điểm. Có thể thêm **jitter** vào TTL cache để phân tán thời điểm hết hạn.
- Nếu key bị eviction trước hạn, hành vi phải được xử lý riêng; có TTL không đồng nghĩa key chắc chắn tồn tại tới khi TTL bằng 0.

So sánh:

| Nhóm dữ liệu | TTL | Có chấp nhận eviction? | Hành vi khi mất |
|---|---|---|---|
| Session đăng nhập | Idle + absolute, xác minh trong logic | Thường cần hạn chế/kiểm soát chặt | Người dùng phải xác thực lại; không bỏ qua kiểm tra |
| Cache cấu hình | Theo chính sách cập nhật/revision | Chỉ khi có nguồn dự phòng và logic phục hồi | Tải từ nguồn/last-known-good có kiểm soát |
| Lookup cache | Theo độ mới có thể chấp nhận | Thường có, nếu có nguồn sự thật | Cache miss và tải lại |
| Registry khóa nghiệp vụ | Theo vòng đời nghiệp vụ | Không tùy tiện | Có thể mất ràng buộc nhất quán nếu mất |
| Rate limit counter | Theo cửa sổ rate limit | Cần xem tác động đến chính sách bảo vệ | Mất counter có thể làm reset hạn mức |

Không được sử dụng eviction như cơ chế xóa nghiệp vụ có bảo đảm. Với dữ liệu bền vững hoặc định danh quan trọng, phải xem xét persistence, replication, failover, backup và khôi phục theo đặc tính của kho lưu trữ.

## 14. Tải lớn: hot key, bộ nhớ và cache stampede

Thiết kế khóa còn quyết định khả năng mở rộng. Một key quá nóng có thể tạo nút thắt dù tổng số key lớn.

### 14.1. Hot key

Ví dụ:

~~~text
cfg:v1:prod:checkout:global
~~~

Nếu mọi request checkout đều đọc cùng key mà không có local cache, nó có thể trở thành điểm nóng ở tầng Redis/network. Không nhất thiết cần phân shard key này thành nhiều bản sao thủ công; với cấu hình đọc nhiều ghi ít, có thể cache trong bộ nhớ ứng dụng với TTL ngắn hoặc cơ chế nhận bản cập nhật.

Tương tự, key `lookup:trending-product:...` có thể chịu hàng chục nghìn request mỗi giây. Cân nhắc local cache, CDN cho dữ liệu công khai, request coalescing và khả năng phân tán đọc của hệ quản trị.

### 14.2. Cache stampede

Khi một key phổ biến hết hạn, hàng nghìn request cùng đọc miss và cùng truy vấn database nguồn. Các cách hạn chế:

- **TTL jitter** để nhiều key không hết hạn đồng loạt.
- **Single-flight / request coalescing** trong instance hoặc ở mức phân tán nếu thật sự cần.
- **Stale-while-revalidate** khi nghiệp vụ chấp nhận dùng dữ liệu cũ trong thời gian làm mới.
- **Warmup có kiểm soát** cho cache quan trọng trước sự kiện tải lớn.
- **Giới hạn concurrency xuống nguồn chính** và báo lỗi rõ khi không đủ năng lực.

Nếu dùng Redis lock bằng `SET lock:key token NX PX ...` để điều phối làm mới, khi giải phóng phải kiểm tra đúng token sở hữu, thường qua script nguyên tử; không gọi `DEL lock:key` vô điều kiện vì có thể xóa khóa của tiến trình khác sau khi lock cũ hết hạn. Với nhiều thao tác nghiệp vụ yêu cầu fencing, lock đơn giản cũng chưa đủ.

### 14.3. Nhiều key nhỏ chưa chắc rẻ hơn một key lớn

Mỗi key có chi phí metadata và phân bổ bộ nhớ. Hàng triệu key nhỏ có thể tiêu tốn đáng kể hơn tổng byte value. Ngược lại, một value JSON quá lớn khiến mỗi lần đọc/ghi phải truyền và parse nhiều byte.

Nên ước lượng:

- Số session đồng thời và kích thước trung bình mỗi session.
- Số tenant × số loại cấu hình × phiên bản retained.
- Số lookup key, tỷ lệ hit/miss, TTL và giá trị phổ biến.
- Dung lượng metadata, index, replication, fragment và backup theo engine.
- Tốc độ tạo/xóa key và tác động khi hàng loạt key hết hạn.
- Số connection, network I/O, command latency và hottest key.

Không nên dự báo dung lượng chỉ bằng `số key × độ dài chuỗi JSON`. Hãy đo bộ nhớ thực tế với dữ liệu đại diện của hệ thống được chọn.

## 15. Khi phải thao tác nhiều key: atomicity và tính nhất quán

Một thao tác `SET` đơn giản thường có ngữ nghĩa rõ. Nhưng nghiệp vụ lại hay đòi hỏi **nhiều key cùng thay đổi**:

- Tạo session và thêm nó vào danh sách session của user.
- Đổi SKU: xóa lookup cũ, tạo lookup mới.
- Cập nhật cấu hình: lưu snapshot và đổi pointer.
- Giữ một mã định danh: tạo mapping và ghi đối tượng chính.

Các hệ key–value có phạm vi atomicity khác nhau. Trong Redis, các lệnh đơn thường được xử lý nguyên tử; `MULTI/EXEC`, `WATCH` và script cho phép thực hiện một số mẫu thao tác phối hợp. Trong Redis Cluster, nhiều lệnh/script/transaction liên quan nhiều key có các ràng buộc về hash slot; không thể giả định mọi tổ hợp key đều thao tác như trên một instance.

### 15.1. Tránh để key phụ trở thành nguồn mâu thuẫn

Nếu dữ liệu sản phẩm nguồn chính ở database A nhưng lookup cache ở Redis B, không có transaction phân tán mặc định đảm bảo hai hệ đổi cùng lúc. Một phương án phổ biến là:

1. Cập nhật nguồn chính trong transaction của chính nguồn đó.
2. Ghi outbox/event trong cùng ranh giới transaction nếu cần phát sự kiện đáng tin cậy.
3. Consumer nhận event và vô hiệu/cập nhật cache; thực hiện idempotent.
4. Đặt TTL để giới hạn hậu quả nếu đường event tạm thời lỗi.
5. Đọc trực tiếp nguồn chính khi nghiệp vụ yêu cầu dữ liệu vừa cập nhật hoặc tính đúng đắn chặt.

Một cache tra cứu được cập nhật bất đồng bộ có thể phù hợp với trang danh mục, nhưng không nên tự quyết định đặt hàng hay quyền tài nguyên nếu dữ liệu cần nhất quán nghiêm ngặt.

### 15.2. Chọn key có tính đến khả năng thao tác theo nhóm

Một số ứng dụng muốn nhiều key của cùng tenant hoặc cùng một đối tượng nằm chung slot để dùng operation đa khóa. Redis Cluster hỗ trợ **hash tag** trong cú pháp key, ví dụ:

~~~text
session:{u-2048}:s-01
session:{u-2048}:s-02
user-session-index:{u-2048}
~~~

Chuỗi trong `{...}` là phần dùng để xác định hash slot của Redis Cluster, giúp các key có cùng tag có thể nằm cùng slot. Đây là ví dụ minh họa cơ chế key grouping, không phải kiến nghị công khai dùng user ID trong session key hay giữ mọi session của người dùng trong cùng một partition ở mọi quy mô.

**Đánh đổi:** gom nhiều key vào một slot có thể tạo điểm nóng. Chỉ dùng khi thật sự cần thao tác phối hợp, và xác định giới hạn tải cho đơn vị được gom. Không áp dụng hash tag cho mọi key chỉ để “đẹp tên”.

## 16. Giám sát và vận hành key–value store

Khác với database quan hệ có bảng/schema rõ ràng, một key–value store có thể chứa nhiều loại key do các nhóm khác nhau ghi. Nếu không có quy ước ownership, tuổi thọ và metrics, việc vận hành dễ trở nên khó kiểm soát.

Một hợp đồng vận hành tối thiểu cho mỗi namespace:

| Thuộc tính | Session | Cấu hình | Lookup |
|---|---|---|---|
| Chủ sở hữu | Auth service | Config service | Product/read service |
| Dạng key | `auth:session:v1:...` | `cfg:v1:...` | `lookup:product-sku:v1:...` |
| Giá trị | State phiên, mốc hạn | Snapshot có revision | ID/snapshot/sentinel |
| Nguồn sự thật | Kho session được chọn | Config source có audit | Product DB |
| TTL | Idle + absolute | Theo cache/revision | Theo độ mới |
| Khi miss | Từ chối session/đăng nhập lại | Tải nguồn hoặc last-known-good theo chính sách | Truy vấn database |
| Khi lỗi hệ lưu trữ | Không bỏ qua xác thực | Tùy cấu hình quan trọng | Có thể fallback có giới hạn |
| Chỉ số | Session active, logout, expiry, lookup latency | Revision, config propagation lag | Hit/miss, stale, fallback latency |

Ngoài latency và throughput, nên quan sát:

- Số key và bộ nhớ theo namespace.
- Cache hit/miss, negative-cache hit, invalidation failure.
- Session creation, expiry, revocation và truy cập session đã hết hạn.
- Thời gian từ lúc cấu hình được phát hành đến khi các instance áp dụng.
- Key eviction, TTL bất thường, timeout, failover và connection saturation.
- Top hot key hoặc nhóm key **dùng cơ chế thống kê giới hạn**, tránh đưa mọi user ID/SKU làm nhãn metric.
- Số lần fallback xuống database và mức tăng tải nguồn khi cache lỗi.

Không dùng lệnh duyệt toàn bộ key kiểu `KEYS *` trong môi trường có lượng dữ liệu lớn chỉ để đếm hoặc chẩn đoán. Redis có `SCAN` để duyệt tăng dần, nhưng cách dùng vẫn phải giới hạn tần suất và hiểu rằng kết quả không phải snapshot nhất quán của tập key đang thay đổi.

## 17. Kịch bản triển khai end-to-end

Giả sử nền tảng SaaS quản lý kho có đăng nhập, cấu hình riêng từng cửa hàng và tra cứu SKU. Một request vào API cần xử lý theo thứ tự:

~~~mermaid
flowchart TD
    A["Request kèm cookie và SKU"] --> B["Băm token, tìm session"]
    B --> C{"Session hợp lệ và còn hạn?"}
    C -->|Không| D["401 hoặc luồng xác thực phù hợp"]
    C -->|Có| E["Lấy tenant/định danh đã xác thực"]
    E --> F["Đọc cấu hình hiệu lực của tenant"]
    F --> G{"Cấu hình hợp lệ?"}
    G -->|Không| H["Xử lý theo chính sách lỗi cấu hình"]
    G -->|Có| I["Chuẩn hóa SKU, tạo lookup key theo tenant"]
    I --> J{"Cache có giá trị?"}
    J -->|Có| K["Sử dụng kết quả đúng phạm vi"]
    J -->|Không| L["Truy vấn nguồn sản phẩm"]
    L --> M["Cache theo chính sách TTL"]
    M --> K
    K --> N["Kiểm tra quyền và nghiệp vụ của thao tác"]
    N --> O["Trả phản hồi"]
~~~

Trong luồng này, cần giữ các bất biến:

- **Session token** không tiết lộ danh tính và không được lấy làm user ID.
- **Tenant** đến từ bối cảnh đã xác thực/ủy quyền, không tin giá trị tenant do người gọi tự chọn.
- **Cấu hình** được lấy theo thứ tự ưu tiên, phiên bản và chính sách an toàn đã xác định.
- **SKU** được chuẩn hóa trước khi tạo key; cùng một SKU ở hai tenant không bị lẫn.
- **Lookup** chỉ tăng tốc tra cứu. Các điều kiện nghiệp vụ mạnh vẫn kiểm tra ở nguồn phù hợp.
- **Hết hạn/miss/lỗi store** có đường xử lý khác nhau tùy loại dữ liệu.

### Bảng key của tình huống

| Key mẫu | Value mẫu | Đời sống / nguyên tắc |
|---|---|---|
| `auth:session:v1:prod:<digest>` | `{userId, tenantId, absoluteExpiresAt}` | TTL idle, chặn tại hạn tuyệt đối; xóa khi logout |
| `cfg:v1:prod:inventory:global` | `{revision: 18, data: {...}}` | Có version; thay theo chính sách xuất bản |
| `cfg:v1:prod:inventory:tenant:shop-17` | `{revision: 4, data: {...}}` | Override được validate, có audit |
| `lookup:product-sku:v1:prod:shop-17:SP-001` | `p-101` | Cache-aside; TTL và invalidation khi đổi SKU |
| `lookup:product-sku:v1:prod:shop-17:NOT-EXIST` | Sentinel not-found | Negative cache ngắn |
| `rate:login:v1:prod:ip:<digest>` | Counter | TTL theo cửa sổ rate limit; chính sách riêng |

Bảng minh họa **quan hệ key/value**, không định nghĩa schema thực tế của Redis. Các thành phần `<digest>` chỉ là ký hiệu; key thật phải dùng digest được tính từ token hoặc định danh phù hợp.

## 18. Ví dụ Redis CLI theo từng trường hợp

Các ví dụ dưới đây tập trung vào hành vi của lệnh. Chúng giả sử Redis instance dành cho thử nghiệm, và chuỗi `<...>` đại diện cho giá trị đã được ứng dụng tạo.

### 18.1. Session: tạo, đọc và xóa

~~~redis
SET auth:session:v1:prod:<digest> '{"userId":"u-2048","absoluteExpiresAt":"2026-11-21T08:00:00Z"}' EX 900 NX

GET auth:session:v1:prod:<digest>

TTL auth:session:v1:prod:<digest>

DEL auth:session:v1:prod:<digest>
~~~

Khi triển khai thật, server phải kiểm tra token, tuyệt đối không tin dữ liệu session do client tự gửi. TTL thực tế phải được tính lại khi gia hạn, có chính sách thu hồi và lỗi store.

### 18.2. Cấu hình: một snapshot có revision

~~~redis
SET cfg:v1:prod:checkout:snapshot:rev-12 '{"revision":12,"maxCartItems":50,"enableVoucherStacking":false}'

SET cfg:v1:prod:checkout:current rev-12

GET cfg:v1:prod:checkout:current

GET cfg:v1:prod:checkout:snapshot:rev-12
~~~

Khi phát hành revision mới, cần xác nhận snapshot mới đã tồn tại, giá trị hợp lệ, rồi mới chuyển pointer. Nếu nhiều người cùng chỉnh sửa, bổ sung optimistic concurrency để không ghi đè một revision mới hơn chỉ vì writer đến muộn.

### 18.3. Lookup: cache kết quả

~~~redis
SET lookup:product-sku:v1:prod:shop-17:SP-001 p-101 EX 300

GET lookup:product-sku:v1:prod:shop-17:SP-001

DEL lookup:product-sku:v1:prod:shop-17:SP-001
~~~

Lệnh `SET` này không áp đặt uniqueness ở database sản phẩm. Nó chỉ cho phép lưu hoặc cập nhật **một mapping tra cứu trong Redis**. Một source record khác có cùng SKU vẫn có thể tồn tại nếu nguồn chính thiếu ràng buộc.

## 19. Những lỗi thiết kế nên tránh

**“Dùng `session:<userId>` để lưu login.”** Một người có thể đăng nhập nhiều thiết bị; mỗi phiên cần định danh riêng, vòng đời và khả năng thu hồi. User ID không phải session token.

**“Session còn key là chắc chắn hợp lệ.”** Cần kiểm tra trạng thái, hạn tuyệt đối, quyền và chính sách thu hồi. Không dùng timeout Redis như cơ chế xác thực duy nhất.

**“Redis lỗi thì bỏ qua kiểm tra session cho người dùng.”** Lỗi hệ xác thực phải đi theo chính sách an toàn; không cho phép truy cập chỉ vì store không phản hồi.

**“Mọi cấu hình để chung `config` là xong.”** Dễ lẫn môi trường, tenant, revision và quyền sửa. Cần namespace, scope và thứ tự ưu tiên rõ ràng.

**“Cấu hình có TTL là tự nhất quán.”** TTL chỉ điều khiển thời gian tồn tại, không đảm bảo các instance cùng đọc một revision và không thay thế audit/rollout.

**“Dùng `tenant + sku` là chắc chắn duy nhất.”** Cách ghép có thể va chạm, và cache không tạo unique constraint ở nguồn dữ liệu. Cần chuẩn hóa, encode đúng và bảo vệ bất biến tại nơi ghi.

**“Chỉ xóa cache sau update thì không thể stale.”** Request đồng thời có thể ghi lại cache cũ sau thao tác xóa. TTL, version hoặc chiến lược nhất quán phù hợp vẫn cần thiết.

**“TTL hết thì key bị xóa vật lý chính xác ngay lập tức.”** Không nên dựa vào thời điểm dọn bộ nhớ để xác định tính hợp lệ của giao dịch hoặc session.

**“Dữ liệu lookup có thể lưu giá và tồn kho như nguồn sự thật.”** Cache có thể cũ và bị eviction. Quyết định có hậu quả nghiệp vụ cần dữ liệu có mức nhất quán phù hợp.

**“Redis Cluster phân tán mọi key đều nhau.”** Hash tag, key nóng và access pattern có thể làm một slot quá tải. Thiết kế khóa phải xem cả phân bố lưu lượng.

**“Có `KEYS *` là biết được mọi key của nghiệp vụ.”** Quét toàn không gian key có thể gây tải nặng và khó suy ra owner/TTL. Nên duy trì metrics theo namespace và công cụ quản trị có giới hạn.

**“Càng nhiều prefix càng an toàn.”** Tên khóa dài và phức tạp không tự bảo vệ thông tin. Cần phân quyền truy cập store, TLS, chuẩn hóa key và tránh dữ liệu nhạy cảm.

## 20. Bài tập thiết kế

### Bài tập A — Một người đăng nhập trên ba thiết bị

User `u-2048` đăng nhập trên laptop, điện thoại và máy tính bảng. Sản phẩm yêu cầu “đăng xuất chỉ điện thoại” và “đăng xuất mọi thiết bị”.

**Hỏi:** Có nên dùng một key `session:u-2048` không?

**Hướng suy luận:** không. Cần token/khóa riêng cho từng session và một chiến lược thu hồi đúng một hoặc tất cả session, ví dụ session index hoặc generation. Nếu dùng index phụ, phải tính đến expiry và thao tác đồng thời.

### Bài tập B — Tenant bật tắt tính năng

Global đặt `enableVoucherStacking = true`, tenant `shop-17` muốn đặt `false`. Code hiện dùng `tenantValue || globalValue`.

**Hỏi:** Vì sao kết quả sai?

**Hướng suy luận:** `false` là giá trị override hợp lệ nhưng toán tử `||` coi như “không có”, làm rơi về `true`. Cần phân biệt trường thiếu, `null` và giá trị Boolean có chủ đích, định nghĩa merge chính xác.

### Bài tập C — Đổi SKU khi có nhiều request

Sản phẩm `p-101` đổi SKU từ `SP-001` sang `KB-001`, trong khi nhiều request vẫn tìm `SP-001`.

**Hỏi:** Chỉ xóa key cũ đã đủ chưa?

**Hướng suy luận:** có thể xảy ra request đọc giá trị cũ rồi ghi lại vào cache sau khi key bị xóa. Cần TTL, version/invalidation phù hợp, và quan trọng nhất là nguồn chính phải giữ uniqueness theo tenant; với thao tác quan trọng có thể đọc lại nguồn.

### Bài tập D — Thiết kế key theo ngôn ngữ và môi trường

Dịch vụ danh mục có hai ngôn ngữ `vi-VN` và `en-US`, chạy ở `staging` và `prod`.

**Hỏi:** Key `category:BOOK` có đủ không?

**Hướng suy luận:** nếu cùng store, key thiếu môi trường và ngôn ngữ dễ ghi đè giá trị. Một key như `lookup:category:v1:prod:vi-VN:BOOK` rõ scope hơn. Nếu môi trường đã cách ly bằng cluster, prefix có thể rút gọn theo hợp đồng đã thống nhất.

### Bài tập E — Cache mất hoàn toàn giữa flash sale

Lookup cache bị flush ngoài kế hoạch; 15.000 request đồng thời tìm cùng 20 SKU.

**Hỏi:** Rủi ro gì và phải chuẩn bị ra sao?

**Hướng suy luận:** nguồn chính có thể chịu cache stampede. Cần request coalescing, hạn mức truy vấn xuống DB, cache warmup, TTL jitter, scaling/monitoring và hành vi lỗi rõ. Cơ chế bảo vệ giá/tồn kho phải giữ ở nguồn có tính nhất quán phù hợp.

## 21. Mẫu hợp đồng cho ba nhóm khóa

Để thiết kế và vận hành thống nhất, có thể ghi một mẫu tài liệu kỹ thuật:

~~~yaml
keyContracts:
  session:
    pattern: "auth:session:v1:{environment}:{tokenDigest}"
    owner: "auth-service"
    identity: "cryptographically random opaque token"
    value: "userId, tenantId, createdAt, absoluteExpiresAt, auth metadata"
    ttl: "idle timeout capped by absolute expiration"
    mutation: "create, verify, renew, revoke"
    failureBehavior: "deny unverifiable session"
    sensitiveData: "never put raw token in key or logs"

  config:
    pattern: "cfg:v1:{environment}:{service}:{scope}"
    owner: "config-service"
    identity: "environment + service + scope/revision"
    value: "validated settings and revision"
    ttl: "according to authoritative source and cache policy"
    mutation: "authorized versioned publish and rollback"
    failureBehavior: "per-setting fallback or fail closed"

  lookup:
    pattern: "lookup:product-sku:v1:{environment}:{tenantId}:{skuKey}"
    owner: "product-service"
    identity: "tenantId + normalized SKU"
    value: "stable productId or explicit negative sentinel"
    ttl: "short bounded cache lifetime"
    mutation: "invalidate on source change"
    failureBehavior: "fallback to authoritative product database"
~~~

Các chuỗi trong mẫu trên là **quy ước tài liệu**, không phải cấu hình có thể chạy trực tiếp trên Redis. Muốn triển khai thực tế, phải xây dựng encoder/decoder key, serializer value, validation, phân quyền, TTL, xử lý lỗi và cơ chế quan sát tương ứng.

Tư duy cốt lõi của thiết kế key–value là: **khóa phải xác định đúng thực thể và phạm vi; value phải có hợp đồng rõ; vòng đời và tính nhất quán phải phù hợp với nghiệp vụ**. Với session, ưu tiên xác thực an toàn, token khó đoán và thu hồi chính xác. Với cấu hình, ưu tiên revision, thứ tự override và triển khai đồng bộ có kiểm soát. Với lookup, ưu tiên tốc độ đọc nhưng phải quản lý stale cache và giữ ràng buộc dữ liệu ở nguồn sự thật. Khi ba nhóm này được thiết kế khác nhau theo đúng trách nhiệm, một mô hình lưu trữ đơn giản vẫn có thể hỗ trợ ứng dụng NoSQL phức tạp và mở rộng an toàn.
