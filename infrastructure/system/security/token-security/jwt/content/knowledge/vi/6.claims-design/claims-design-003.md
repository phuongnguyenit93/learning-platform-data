# Không gian tên và phòng tránh xung đột tên claim

## 1. Vì sao tên claim cần có không gian tên?

Trong **JSON Web Token (JWT)**, claims được biểu diễn bằng các thành viên của một đối tượng JSON: mỗi claim có một **tên** và một **giá trị**. Tên claim là chuỗi mà bên phát hành và bên nhận phải hiểu thống nhất. Khi chỉ một hệ thống phát hành và tiêu thụ token, một tên ngắn như `tenant_id` có thể đủ rõ. Khi nhiều nhóm, nhà cung cấp định danh hoặc đối tác cùng tạo claims, tên ngắn đó có thể bị dùng lại cho những ý nghĩa khác nhau.

Ví dụ, hai issuer cùng phát hành:

```json
{
  "tenant_id": "tenant_17"
}
```

Ở hệ thống thứ nhất, `tenant_id` là tenant người dùng đang chọn để làm việc. Ở hệ thống thứ hai, nó lại là tenant sở hữu tài khoản. Cùng một tên và cùng kiểu chuỗi nhưng hai giá trị có ngữ nghĩa khác nhau. Nếu một API nhận cả hai loại token và diễn giải chúng như nhau, nó có thể truy cập nhầm phạm vi dữ liệu.

**Không gian tên (namespace)** là quy ước giúp xác định nguồn sở hữu và phạm vi của tên. Thay vì chỉ dùng `tenant_id`, một hệ thống có thể dùng tên đầy đủ:

```json
{
  "https://claims.shop.example.org/active_tenant_id": "tenant_17"
}
```

Tên này cho biết claim thuộc không gian tên do tổ chức quản lý. Phần URI trong tên claim là **định danh dạng chuỗi**; bên nhận không cần và không nên tự động gọi URL đó để lấy dữ liệu. Tên có namespace giúp giảm khả năng trùng tên, nhưng vẫn cần tài liệu hợp đồng để xác định kiểu, ý nghĩa và cách kiểm tra giá trị.

## 2. Những loại xung đột cần phòng tránh

Không phải mọi lỗi liên quan đến claims đều là trùng tên theo nghĩa hẹp. Khi thiết kế namespace, cần phân biệt ít nhất năm tình huống:

| Loại xung đột | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Trùng tên** | Hai bên cùng dùng `role` | Một bên có thể ghi đè hoặc diễn giải claim của bên kia |
| **Trùng tên, khác ngữ nghĩa** | `tenant_id` là tenant đăng nhập ở hệ thống A, tenant sở hữu dữ liệu ở hệ thống B | API áp dụng sai ranh giới dữ liệu hoặc quyền |
| **Cùng ngữ nghĩa, khác cấu trúc** | Một issuer gửi `roles` dạng chuỗi, issuer khác gửi mảng chuỗi | Consumer phân tích sai kiểu hoặc bỏ sót quyền |
| **Khác tên, gần giống ý nghĩa** | `store_id`, `shop_id`, `merchant_id` không được định nghĩa rõ | Các thành phần không thống nhất cách ánh xạ danh tính |
| **Đúng tên nhưng sai nguồn tin cậy** | Token từ issuer ngoài chứa claim `is_admin` mà API nội bộ cũng sử dụng | Đặc quyền bị cấp dựa trên khẳng định không được ủy quyền |

Namespace chủ yếu giải quyết rủi ro **đụng tên**. Hợp đồng claims giải quyết rủi ro **khác ngữ nghĩa hoặc cấu trúc**. Cấu hình xác minh issuer, audience và chính sách phân quyền giải quyết rủi ro **tin nhầm nguồn**. Cả ba lớp đều cần thiết.

## 3. Quy tắc đặt tên trong JWT

### 3.1. Tên claim là chuỗi chính xác

Theo RFC 7519, tên claim là chuỗi. Việc so khớp tên phải dựa trên tên được định nghĩa trong hợp đồng:

- `store_id` và `Store_Id` là hai tên khác nhau.
- `tenant_id` và `tenant-id` là hai tên khác nhau.
- Không tự ý chuyển tên thành chữ thường, bỏ dấu gạch dưới, trim khoảng trắng hoặc đổi dấu phân cách trước khi tra cứu.
- Không tự động xem hai URI có cách viết khác nhau là cùng một tên nếu hợp đồng không quy định rõ.

Các bên nên thống nhất chính xác cách viết của tên claim, kiểu dữ liệu và quy tắc xử lý. Không tạo nhiều alias cho cùng một khái niệm nếu không có nhu cầu tương thích được xác định rõ.

### 3.2. Ưu tiên tên đã đăng ký khi đã có định nghĩa phù hợp

JWT có ba nhóm tên claim theo RFC 7519:

- **Registered Claim Names**: tên được đăng ký trong IANA JWT Claims Registry, ví dụ `iss`, `sub`, `aud`, `exp`.
- **Public Claim Names**: tên được định nghĩa công khai; tên mới nên được đăng ký hoặc sử dụng tên chống xung đột (*collision-resistant name*).
- **Private Claim Names**: tên do các bên thỏa thuận, có nguy cơ trùng tên và cần được sử dụng thận trọng.

Trước khi tạo một tên mới, hãy tra [IANA JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml) và đặc tả liên quan. Nếu một registered claim đã mô tả đúng thông tin cần truyền, hãy dùng tên và ngữ nghĩa đã chuẩn hóa. Không tái sử dụng tên chuẩn với ý nghĩa riêng.

Ví dụ, không dùng `exp` để lưu ngày hết hạn hợp đồng dưới dạng chuỗi. `exp` đã có ý nghĩa là thời điểm JWT hết hiệu lực theo NumericDate. Có thể dùng một tên riêng như `contract_expires_at`, với kiểu dữ liệu và quy tắc được mô tả trong hợp đồng.

### 3.3. Dùng tên chống xung đột cho claims cần chia sẻ

Khi định nghĩa public claim mới, RFC 7519 khuyến nghị đăng ký tên hoặc sử dụng **collision-resistant name**. Một cách thường dùng là tạo tên dựa trên URI thuộc namespace mà tổ chức kiểm soát:

```text
https://claims.example.org/tenant/active-id
https://claims.example.org/store/role
https://identity.example.org/claims/customer-segment
urn:example:claims:account-class
```

Đây là ví dụ về hình thức tên; `example.org` và `example.net` là tên miền dành cho tài liệu minh họa, không phải namespace để đưa vào hệ thống thật.

Một namespace URI có một số lợi ích:

1. Tên có thể gắn với tổ chức hoặc nhóm chịu trách nhiệm định nghĩa.
2. Các tổ chức khác có thể tạo tên riêng trong namespace của họ mà ít nguy cơ trùng nhau.
3. Consumer có thể cấu hình allowlist các tên claim mà nó hiểu.
4. Tài liệu đặc tả có thể được công bố tại địa chỉ liên quan, dù việc truy cập địa chỉ đó không phải một phần của thao tác đọc JWT.

Không phải mọi public claim đều bắt buộc dùng URL có thể truy cập. Điều cần đạt là tên chống xung đột và có định nghĩa đủ rõ; URI chỉ là một cách phổ biến để đạt mục tiêu đó.

## 4. Thiết kế namespace ổn định

### 4.1. Chọn phần namespace do tổ chức kiểm soát

Một tổ chức nên dùng tên miền hoặc định danh mà mình có quyền quản lý lâu dài. Có thể thiết kế cấu trúc như:

```text
https://claims.<organization-domain>/<domain>/<claim-name>
```

Ví dụ minh họa:

```text
https://claims.acme.example/commerce/active-store
https://claims.acme.example/commerce/store-role
https://claims.acme.example/customer/segment
```

Các tên này thể hiện nhóm nghiệp vụ và khái niệm cụ thể. Tổ chức cần có quy trình quản lý tên miền, tài liệu và quyền phát hành claim tương ứng.

Nên tránh:

- Dùng namespace thuộc một bên thứ ba mà tổ chức không kiểm soát.
- Dùng tên miền cá nhân hoặc dịch vụ miễn phí có thể bị đổi chủ.
- Dùng tên quá chung như `https://claims.example.org/admin` mà không nêu rõ admin của hệ thống hay phạm vi nào.
- Dùng tên dựa trên môi trường triển khai như `/dev/`, `/prod/` nếu ý nghĩa claim không khác nhau giữa các môi trường.
- Dùng URL của một endpoint tạm thời làm tên claim, khiến việc đổi hạ tầng vô tình làm đổi định danh.

Namespace nên bền vững qua thay đổi máy chủ, sản phẩm hoặc cấu trúc tổ chức. Nếu tên miền thay đổi, cần duy trì khả năng nhận diện các tên cũ trong thời gian chuyển đổi và xác định rõ issuer nào còn được phép phát hành chúng.

### 4.2. Tách namespace khỏi tên miền nghiệp vụ quá rộng

Một namespace tốt cần đủ cụ thể để phân biệt trách nhiệm nhưng không nên phản ánh mọi chi tiết nội bộ. Ví dụ:

| Tên | Nhận xét |
| --- | --- |
| `https://claims.acme.example/admin` | Quá chung; không rõ admin của sản phẩm hay phạm vi nào |
| `https://claims.acme.example/commerce/store-role` | Gắn với miền thương mại và vai trò tại cửa hàng |
| `https://claims.acme.example/internal/team-a/role-v3` | Phơi bày cấu trúc nội bộ, khó duy trì khi nhóm hoặc phiên bản thay đổi |

Tên claim là một phần của hợp đồng liên hệ giữa issuer và consumer. Chọn tên theo khái niệm ổn định của nghiệp vụ, không theo tên class, tên bảng dữ liệu hay cấu trúc thư mục của một ứng dụng.

### 4.3. Không nhầm namespace của tên với phạm vi duy nhất của giá trị

Tên claim có namespace không có nghĩa giá trị của nó tự nhiên duy nhất toàn cầu. Ví dụ:

```json
{
  "https://claims.acme.example/commerce/active-store": "store_17"
}
```

Hợp đồng vẫn phải nói rõ `store_17` duy nhất trong toàn nền tảng, trong một quốc gia, hay chỉ trong phạm vi issuer. Nếu mã chỉ duy nhất theo issuer, consumer phải kết hợp với danh tính issuer hoặc một định danh đầy đủ khác khi lưu trữ và đối chiếu.

Tương tự, `sub` thường chỉ duy nhất trong phạm vi issuer. Khi cần khóa định danh ổn định giữa nhiều issuer, hệ thống không nên chỉ dùng giá trị `sub` mà bỏ qua `iss`.

## 5. Ví dụ thiết kế: nhiều hệ thống cùng phát hành JWT

Giả sử nền tảng Acme có hai hệ thống:

- **Commerce Identity** phát hành token cho nhân viên cửa hàng. Claim cửa hàng thể hiện cửa hàng mà nhân viên đang chọn trong phiên.
- **Partner Identity** phát hành token cho nhân viên của đối tác. Claim cửa hàng thể hiện cửa hàng mà đối tác sở hữu hoặc quản lý.

Nếu cả hai dùng `store_id`, API có thể nhầm hai ngữ cảnh. Hãy định nghĩa hai claim khác nhau:

```json
{
  "iss": "https://identity.acme.example",
  "sub": "employee_42",
  "aud": "https://api.acme.example",
  "exp": 1893456900,
  "https://claims.acme.example/commerce/active-store": "store_17"
}
```

Token từ Partner Identity có thể dùng:

```json
{
  "iss": "https://identity.partner.example",
  "sub": "partner_user_9",
  "aud": "https://api.acme.example",
  "exp": 1893456900,
  "https://claims.partner.example/partner/managed-store": "store_17"
}
```

API hiểu rõ claim nào diễn tả ngữ cảnh nào. Nếu API có nhu cầu ánh xạ cả hai thành một mô hình nội bộ, việc ánh xạ phải được cấu hình theo **issuer, audience và hợp đồng**, không chỉ dựa trên giá trị chuỗi.

| Thành phần | Commerce Identity | Partner Identity |
| --- | --- | --- |
| `iss` | `https://identity.acme.example` | `https://identity.partner.example` |
| Tên claim cửa hàng | `https://claims.acme.example/commerce/active-store` | `https://claims.partner.example/partner/managed-store` |
| Ngữ nghĩa | Cửa hàng đang được chọn trong phiên | Cửa hàng do đối tác quản lý |
| Nguồn xác nhận | Quan hệ nhân viên và quyền chọn cửa hàng | Quan hệ đối tác và danh sách cửa hàng được quản lý |
| Kiểm tra tại API | Kiểm tra quyền hiện hành trên tài nguyên | Kiểm tra quyền hiện hành trên tài nguyên |

Tên khác nhau giảm khả năng diễn giải nhầm. Tuy nhiên, API vẫn phải kiểm tra `iss`, `aud`, chữ ký, thời gian, loại token và chính sách nghiệp vụ. **Namespace không phải cơ chế xác thực hay phân quyền.**

## 6. Quy tắc xử lý xung đột trong JSON Claims Set

### 6.1. Tên thành viên JSON phải duy nhất

RFC 7519 quy định các tên claim trong JWT Claims Set phải duy nhất. Khi nhận một đối tượng JSON có tên claim lặp lại, bộ phân tích phải từ chối JWT hoặc chỉ trả về thành viên trùng tên xuất hiện cuối theo quy tắc RFC cho phép.

Ví dụ không nên chấp nhận:

```json
{
  "sub": "user_42",
  "https://claims.acme.example/commerce/store-role": "viewer",
  "https://claims.acme.example/commerce/store-role": "admin"
}
```

Nếu một thành phần đọc giá trị đầu và thành phần khác đọc giá trị cuối, cùng token có thể dẫn đến hai quyết định quyền khác nhau. Với hệ thống bảo mật, lựa chọn rõ ràng và an toàn hơn là **từ chối payload có tên claim trùng** ngay tại bước phân tích.

Đừng chỉ kiểm tra trùng tên sau khi đã chuyển JSON thành map/dictionary nếu thư viện phân tích đã âm thầm ghi đè thành viên trước đó. Cần bảo đảm parser hoặc lớp kiểm tra đầu vào có khả năng phát hiện tên trùng trước khi dữ liệu bị mất.

### 6.2. Không tự động chuẩn hóa tên

Không chuyển tất cả tên claim về chữ thường hoặc tự đổi URI trước khi so khớp. Việc chuẩn hóa tùy tiện có thể khiến hai tên riêng biệt bị gộp lại hoặc khiến consumer chấp nhận một tên mà hợp đồng không cho phép.

Ví dụ:

```json
{
  "https://claims.acme.example/commerce/store-role": "viewer",
  "https://claims.acme.example/Commerce/store-role": "admin"
}
```

Hai tên trên khác nhau. Consumer chỉ nên chấp nhận tên được khai báo chính xác trong hợp đồng; nếu nhận một tên gần giống nhưng chưa biết, xử lý theo chính sách unknown claim, không suy đoán rằng đó là alias hợp lệ.

### 6.3. Unknown claims và allowlist

Một JWT có thể chứa claim mà API không biết. Việc có nên từ chối token khi gặp claim lạ phụ thuộc hồ sơ giao thức và chính sách của ứng dụng:

- Nếu claim lạ không liên quan đến quyết định truy cập và hồ sơ cho phép mở rộng, API có thể bỏ qua.
- Nếu endpoint yêu cầu một claim cụ thể để xác định tenant, chủ thể hoặc quyền, claim thiếu hoặc sai kiểu phải dẫn đến từ chối.
- Nếu một claim lạ có tên gần giống claim đặc quyền, tuyệt đối không tự động ánh xạ hoặc cấp quyền.
- Với hệ thống có ranh giới tin cậy chặt, dùng allowlist tên claim và kiểu dữ liệu được chấp nhận cho từng issuer/audience.

Không nên coi “token có thêm trường” là lỗi trong mọi trường hợp, nhưng cũng không được để một claim không được định nghĩa tham gia quyết định bảo mật.

## 7. Namespace cần đi cùng hợp đồng claim

Tên duy nhất vẫn chưa đủ. Mỗi claim được sử dụng trong quyết định nghiệp vụ nên có hợp đồng ghi rõ:

| Thuộc tính | Ví dụ: `active-store` |
| --- | --- |
| Tên đầy đủ | `https://claims.acme.example/commerce/active-store` |
| Chủ sở hữu namespace | Tổ chức Acme |
| Kiểu dữ liệu | Chuỗi không rỗng |
| Ý nghĩa | Cửa hàng được chọn trong ngữ cảnh access token |
| Nguồn xác nhận | Issuer kiểm tra người dùng là thành viên và được phép chọn cửa hàng |
| Issuer được phép phát hành | Commerce Identity |
| Audience được phép nhận | API thương mại đã đăng ký |
| Phạm vi duy nhất của giá trị | Mã cửa hàng duy nhất trong nền tảng Acme |
| Tính bắt buộc | Bắt buộc với endpoint thao tác theo cửa hàng |
| Độ tươi dữ liệu | Kiểm tra lại tư cách thành viên khi nghiệp vụ yêu cầu thu hồi tức thời |
| Xử lý thiếu/sai kiểu | Từ chối yêu cầu cần ngữ cảnh cửa hàng |
| Chính sách thay đổi | Không đổi ý nghĩa tại chỗ; thay đổi không tương thích cần tên hoặc hợp đồng mới |

Đặc biệt, phải mô tả **ai được phép phát hành claim**. Một bên nhận không được tin một claim đặc quyền chỉ vì tên của nó nằm trong namespace quen thuộc. Khóa ký và issuer phải được liên kết với quyền phát hành claim tương ứng.

## 8. Quản lý thay đổi namespace và tương thích

### 8.1. Đổi tên miền hoặc tổ chức sở hữu

Nếu tổ chức đổi tên miền, các claim URI cũ vẫn là tên đã xuất hiện trong token và hợp đồng đã phát hành. Không thể chỉ thay chuỗi trong cấu hình issuer mà kỳ vọng mọi token cũ tự đổi tên. Cần:

1. Xác định issuer nào còn được phép phát hành tên cũ.
2. Công bố namespace mới và thời gian chuyển đổi.
3. Nếu phát hành đồng thời tên cũ và tên mới, quy định một giá trị chuẩn và kiểm tra chúng không mâu thuẫn.
4. Cập nhật consumer theo từng audience, kiểm thử token cũ/mới.
5. Ngừng chấp nhận tên cũ theo kế hoạch và theo thời hạn của token.

Không tái sử dụng namespace cũ cho ý nghĩa khác sau khi chuyển đổi.

### 8.2. Khi nào cần phiên bản mới?

Nếu chỉ sửa lỗi diễn đạt trong tài liệu nhưng không đổi ý nghĩa hay kiểu dữ liệu, có thể giữ nguyên tên và cập nhật tài liệu. Nếu thay đổi làm consumer cũ diễn giải khác, ví dụ `active-store` đổi từ cửa hàng đang chọn sang cửa hàng sở hữu tài khoản, đó là thay đổi không tương thích.

Có thể dùng một tên mới:

```text
https://claims.acme.example/commerce/active-store
https://claims.acme.example/commerce/account-owner-store
```

Hoặc định nghĩa phiên bản hợp đồng riêng nếu có nhiều claim cần thay đổi đồng bộ. Tránh thêm hậu tố phiên bản vào mọi tên theo thói quen; chỉ làm vậy khi phiên bản thực sự cần thiết để phân biệt ngữ nghĩa. Dù chọn cách nào, issuer và consumer phải có kế hoạch chuyển đổi rõ ràng.

### 8.3. Tránh phát hành hai claim mâu thuẫn

Trong giai đoạn chuyển tiếp, nếu token chứa cả tên cũ và tên mới, cần quy định:

- Claim nào là nguồn có thẩm quyền?
- Nếu cả hai cùng có nhưng giá trị khác nhau thì từ chối hay áp dụng quy tắc chuyển đổi nào?
- Consumer cũ có bỏ qua tên mới không?
- Thời điểm nào issuer ngừng phát hành tên cũ?

Không để mỗi API tự quyết định ưu tiên một trường. Quy tắc tương thích cần thống nhất ở hợp đồng và được kiểm thử.

## 9. Quy trình thiết kế namespace cho một claim mới

Có thể áp dụng quy trình sau trước khi đưa claim vào token:

1. **Xác định nhu cầu:** claim phục vụ quyết định nào, thành phần nào cần đọc và có thể lấy dữ liệu từ nguồn hiện hành hay không.
2. **Tra cứu tên chuẩn:** kiểm tra IANA JWT Claims Registry và đặc tả đang sử dụng; không tái định nghĩa tên đã có.
3. **Xác định phạm vi chia sẻ:** chỉ một ứng dụng, nhiều dịch vụ nội bộ hay nhiều tổ chức/đối tác.
4. **Chọn tên:** dùng private claim cho thỏa thuận khép kín; với public claim mới, đăng ký tên hoặc dùng collision-resistant name thuộc namespace kiểm soát.
5. **Định nghĩa ngữ nghĩa:** kiểu dữ liệu, đơn vị, phạm vi duy nhất, nguồn xác nhận, độ tươi và trường hợp thiếu.
6. **Ràng buộc issuer và audience:** xác định bên nào được phát hành và bên nào được phép tiêu thụ claim.
7. **Xác định quy tắc parser:** tên trùng, claim lạ, sai kiểu, tên gần giống và giá trị không hợp lệ được xử lý thế nào.
8. **Kiểm thử tương thích:** kiểm thử token từ từng issuer, token cũ/mới, trường hợp thiếu claim, trùng tên và giá trị không khớp.
9. **Quản lý vòng đời:** chỉ định chủ sở hữu tài liệu, quy trình thay đổi, thời gian tương thích và kế hoạch ngừng tên cũ.

Luồng quyết định rút gọn:

```text
Nhu cầu claim mới
       |
       v
Đã có registered claim phù hợp?
       | Có                    | Không
       v                       v
Dùng tên chuẩn          Xác định phạm vi sử dụng
                               |
                 +-------------+-------------+
                 |                           |
           Nội bộ khép kín             Nhiều bên/đối tác
                 |                           |
                 v                           v
           Private claim          Public: đăng ký hoặc dùng
                                  collision-resistant name
                 |                           |
                 +-------------+-------------+
                               |
                               v
                 Định nghĩa hợp đồng và issuer
                               |
                               v
                 Kiểm thử parser và phân quyền
```

## 10. Các tình huống kiểm thử nên có

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Claim có tên đúng, issuer và audience hợp lệ, giá trị đúng kiểu | Có thể tiếp tục đánh giá chính sách nghiệp vụ |
| Cùng tên nhưng token đến từ issuer không được phép | Từ chối token hoặc không chấp nhận claim theo chính sách |
| Tên claim sai khác chữ hoa/chữ thường | Không tự coi là tên hợp lệ |
| Claim bắt buộc bị thiếu | Từ chối thao tác cần claim đó |
| Claim có kiểu dữ liệu không đúng hợp đồng | Từ chối; không ép kiểu tùy tiện |
| JSON có tên claim lặp lại | Từ chối payload theo chính sách parser an toàn |
| Token có claim lạ không liên quan | Xử lý theo chính sách unknown claim của hồ sơ |
| Tên cũ và mới cùng xuất hiện nhưng giá trị mâu thuẫn | Từ chối hoặc xử lý theo quy tắc chuyển đổi đã định nghĩa; không tự đoán |
| Claim đúng namespace nhưng tài nguyên thuộc tenant khác | Từ chối theo chính sách phân quyền tài nguyên |

## 11. Tự kiểm tra

**Câu 1.** Đổi `tenant_id` thành `https://claims.acme.example/tenant_id` có đủ để tránh mọi lỗi bảo mật không?

**Trả lời:** Không. Tên namespace giảm nguy cơ trùng tên. Hệ thống vẫn cần xác minh issuer, audience, chữ ký, kiểu dữ liệu, ngữ nghĩa và quyền trên tài nguyên.

**Câu 2.** Một API nhận token từ hai issuer, cả hai đều có `role = "admin"`. API có thể xem hai giá trị này là tương đương không?

**Trả lời:** Không, trừ khi hợp đồng quy định rõ và API đã xác minh từng issuer được phép phát hành khẳng định đó. Cùng tên không bảo đảm cùng ý nghĩa.

**Câu 3.** Vì sao nên từ chối JSON có hai thành viên trùng tên claim?

**Trả lời:** Các parser có thể xử lý thành viên trùng khác nhau. Nếu một thành phần đọc giá trị đầu và thành phần khác đọc giá trị cuối, token có thể dẫn tới quyết định không nhất quán. Từ chối sớm loại bỏ sự mơ hồ.

**Câu 4.** URI trong tên claim có bắt buộc phải truy cập được qua HTTP không?

**Trả lời:** Không. Nó có thể được dùng như một định danh chuỗi. Tài liệu có thể được công bố ở địa chỉ đó, nhưng việc đọc JWT không đòi hỏi truy cập mạng đến URI.

**Câu 5.** Nếu một claim đổi ý nghĩa nhưng giữ nguyên tên, có cần cập nhật consumer không?

**Trả lời:** Có. Đây là thay đổi hợp đồng không tương thích. Hãy dùng tên hoặc phiên bản hợp đồng mới, lập kế hoạch chuyển đổi và không để consumer cũ hiểu sai dữ liệu.

## 12. Ghi nhớ

Namespace giúp các bên đặt tên claim độc lập mà giảm nguy cơ va chạm. Để thiết kế an toàn, hãy dùng tên chuẩn khi phù hợp, dùng tên chống xung đột cho public claims mới, và giới hạn private claims trong các thỏa thuận có quản lý. Tên claim phải ổn định, có chủ sở hữu, có định nghĩa về kiểu và ngữ nghĩa, đồng thời được ràng buộc với issuer và audience hợp lệ.

**Tên duy nhất không tự tạo ra niềm tin.** Chỉ sau khi xác minh token và áp dụng hợp đồng cùng chính sách nghiệp vụ, API mới có thể quyết định có sử dụng claim đó cho yêu cầu hiện tại hay không.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Section 4: JWT Claims](https://www.rfc-editor.org/rfc/rfc7519#section-4): định nghĩa claim names, public/private claims và yêu cầu tên duy nhất.
- [RFC 7519 — Section 10.1: JSON Web Token Claims Registry](https://www.rfc-editor.org/rfc/rfc7519#section-10.1): quy trình đăng ký claim names.
- [IANA — JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml): tra cứu các tên claim đã đăng ký.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format, Section 4](https://www.rfc-editor.org/rfc/rfc8259#section-4): quy tắc và lưu ý về tên thành viên trong JSON object.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh issuer, audience và không tin claims nhận được khi chưa kiểm tra.
