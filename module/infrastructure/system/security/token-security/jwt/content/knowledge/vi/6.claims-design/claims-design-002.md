# Registered claims, public claims và private claims

## 1. Vì sao JWT phân loại tên claim?

Một **JSON Web Token (JWT)** chứa tập các *claim*: các cặp tên–giá trị trong một đối tượng JSON, dùng để chuyển những khẳng định của bên phát hành (*issuer*) tới bên nhận token. Ví dụ, claim `sub` có thể xác định chủ thể, còn `tenant_id` có thể xác định ngữ cảnh tổ chức mà một hệ thống quy ước.

Trong một hệ thống duy nhất, các bên có thể thống nhất ý nghĩa tên claim tương đối dễ dàng. Khi JWT được trao đổi giữa nhiều API, nhà cung cấp định danh hoặc tổ chức, việc đặt cùng tên nhưng hiểu khác nghĩa có thể gây lỗi tích hợp, thậm chí lỗi phân quyền. Chẳng hạn, hai hệ thống cùng phát hành `role: "admin"`, nhưng một hệ thống nói đến quản trị **một cửa hàng**, hệ thống khác nói đến quản trị **toàn nền tảng**.

Để phân biệt cách đặt tên và mức độ chuẩn hóa, [RFC 7519, Mục 4](https://www.rfc-editor.org/rfc/rfc7519#section-4) mô tả ba loại:

| Loại | Tiêu chí nhận diện | Phạm vi sử dụng điển hình | Ví dụ |
| --- | --- | --- | --- |
| **Registered Claim Names** | Tên đã đăng ký trong **IANA JSON Web Token Claims Registry** | Những khái niệm có định nghĩa chung, được nhiều bên dùng | `iss`, `sub`, `aud`, `exp` |
| **Public Claim Names** | Tên được định nghĩa công khai; tên mới nên được đăng ký hoặc sử dụng **tên chống xung đột** (*collision-resistant name*) | Giao tiếp giữa nhiều nhóm, sản phẩm, tổ chức có hợp đồng chung | `https://claims.example.org/tenant_id` |
| **Private Claim Names** | Tên do các bên liên quan tự thỏa thuận; không có bảo đảm chống trùng tên toàn cục | Một ứng dụng, nhóm dịch vụ nội bộ hoặc quan hệ tích hợp song phương | `tenant_id`, `store_role` |

**Điểm cốt lõi:** Phân loại này nói về **tên, cách quản lý tên và khả năng tương tác**. Nó **không** xác định claim có bí mật hay không, có đáng tin hay không, hoặc người nhận token có quyền gì.

- *Registered* không có nghĩa mọi JWT bắt buộc chứa claim đó.
- *Public* không có nghĩa payload được phép công khai hoặc mọi API tự hiểu ý nghĩa của claim.
- *Private* không có nghĩa claim được mã hóa hoặc chỉ chủ sở hữu token đọc được.

JWT được ký theo JWS thông thường vẫn để lộ payload cho người có token; muốn giữ kín nội dung phải có thiết kế mã hóa thích hợp, chẳng hạn JWE. Dù thuộc nhóm nào, claim chỉ nên được dùng sau khi bên nhận xác minh token theo chính sách tin cậy của mình.

## 2. Registered claims: tên đã đăng ký và có định nghĩa chung

### 2.1. Nguồn đăng ký và phạm vi tiêu chuẩn

**Registered Claim Name** là tên nằm trong [IANA JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml). Một mục đăng ký cung cấp tên và tham chiếu tới tài liệu định nghĩa. RFC 7519 giới thiệu bảy registered claim phổ biến sau; registry có thể có thêm các tên được đăng ký bởi những đặc tả khác.

| Claim | Tên đầy đủ | Ý nghĩa | Điểm cần chú ý khi xử lý |
| --- | --- | --- | --- |
| `iss` | Issuer | Bên phát hành JWT | Phải đối chiếu với issuer được tin cậy theo cấu hình, không chỉ kiểm tra chuỗi không rỗng |
| `sub` | Subject | Chủ thể mà claim nói đến | Chỉ xác định danh tính trong phạm vi issuer/hợp đồng; không tự suy ra đó luôn là con người |
| `aud` | Audience | Một hay nhiều bên nhận JWT dự kiến | Bên nhận phải kiểm tra token thực sự dành cho mình; dạng hợp lệ có thể là chuỗi hoặc mảng chuỗi |
| `exp` | Expiration Time | Thời điểm JWT hết hiệu lực | Không chấp nhận từ thời điểm này trở đi, có thể áp dụng sai lệch đồng hồ nhỏ theo chính sách |
| `nbf` | Not Before | Thời điểm sớm nhất JWT được chấp nhận | Token chưa đến thời điểm cho phép phải bị từ chối |
| `iat` | Issued At | Thời điểm phát hành | Giúp kiểm tra tuổi token theo chính sách; bản thân `iat` không định nghĩa thời hạn sử dụng |
| `jti` | JWT ID | Định danh riêng của JWT | Có thể hỗ trợ theo dõi, thu hồi hoặc chống phát lại, nhưng phải có cơ chế thực thi kèm theo |

Các claim `exp`, `nbf` và `iat` nhận giá trị **NumericDate**: số giây tính từ Unix epoch theo định nghĩa RFC, không phải chuỗi ISO 8601 hoặc số mili giây. Giá trị NumericDate không bắt buộc là số nguyên; một hồ sơ ứng dụng có thể đặt thêm quy ước riêng.

Ví dụ về Claims Set có các tên đã đăng ký:

```json
{
  "iss": "https://id.example.org",
  "sub": "user_42",
  "aud": "https://orders.example.org",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900,
  "jti": "jwt_b8a7"
}
```

Đây là dữ liệu minh họa, không phải token được ký. Theo các giá trị trên, `exp` cách `iat` **900 giây (15 phút)**. Dịch vụ đơn hàng chỉ chấp nhận token nếu kiểm tra mật mã, issuer, audience, thời gian và mọi ràng buộc của hồ sơ token đều đạt.

### 2.2. “Registered” không đồng nghĩa “required”

RFC 7519 định nghĩa các claim phổ biến nhằm tăng khả năng tương tác, nhưng **không bắt buộc mọi JWT phải có đủ bảy trường**. Tập claim bắt buộc thuộc về **hồ sơ giao thức và hợp đồng của hệ thống**. Ví dụ, một API có thể yêu cầu `iss`, `aud`, `sub`, `exp` trong access token của nó, và từ chối token thiếu bất kỳ trường nào, dù không phải mọi JWT trên thế giới đều có quy tắc như vậy.

Không được dựa vào tên registered để bỏ qua kiểm tra nội dung. Token có `aud` nhưng trỏ đến một dịch vụ khác vẫn phải bị từ chối. `sub` trùng chuỗi giữa hai issuer không bảo đảm cùng chủ thể. `jti` có mặt không tự động khiến token chỉ dùng được một lần.

**Lưu ý về registry:** Không suy luận rằng chỉ bảy tên trên mới là registered claims. Khi cần xác định một tên có được đăng ký hay chưa, tra cứu registry và tài liệu được dẫn chiếu; tên có thể được bổ sung theo thời gian.

## 3. Public claims: đặt tên có khả năng tương tác, giảm xung đột

### 3.1. Public claim dùng khi nào?

Khi một nhóm cần truyền thêm thông tin mà các registered claims hiện có không diễn tả được, họ có thể định nghĩa **Public Claim Name**. Theo RFC 7519, để hạn chế va chạm với tên do bên khác tạo ra, một tên mới nên **được đăng ký trong registry** hoặc **chứa một tên chống xung đột**.

Một phương án phổ biến là dùng tên theo không gian định danh có kiểm soát, chẳng hạn URI do tổ chức sở hữu:

```json
{
  "iss": "https://id.example.org",
  "sub": "user_42",
  "aud": "https://orders.example.org",
  "exp": 1893456900,
  "https://claims.example.org/tenant_id": "tenant_17",
  "https://claims.example.org/account_tier": "business"
}
```

Trong ví dụ, hai khóa JSON dạng URI là **tên claim**, không phải URL mà API phải tự gọi. Địa chỉ `example.org` chỉ dùng để minh họa. Khi thiết kế thật, tổ chức phải có quyền kiểm soát không gian tên tương ứng và duy trì quy ước đặt tên ổn định.

Ưu điểm của tên chống xung đột: nếu hai bên cùng muốn diễn tả khái niệm tenant, `https://id.alpha.example/claims/tenant` và `https://id.beta.example/claims/tenant` vẫn là **hai tên khác nhau**. Chúng sẽ không vô tình bị coi là một trường chỉ vì cùng đoạn cuối `tenant`.

### 3.2. Public không bảo đảm ngữ nghĩa tự động

Một tên dài, duy nhất giúp tránh **xung đột tên**, nhưng không tự bảo đảm hai bên hiểu đúng **kiểu dữ liệu, nguồn xác nhận, mức độ cập nhật và phạm vi áp dụng**. Chẳng hạn:

- `https://claims.example.org/tenant_id` là chuỗi hay số?
- Mã tenant có duy nhất trên toàn nền tảng hay chỉ duy nhất trong một tổ chức?
- Tenant là nơi người dùng đăng nhập, tenant được chọn khi cấp token, hay tenant của tài nguyên?
- Khi thành viên rời tenant, access token đã phát hành có còn được tin để phân quyền không?

Những câu hỏi này phải được quy định trong **hợp đồng claim** và được bên nhận kiểm tra. URI chỉ tạo không gian tên; nó không đóng vai trò chính sách phân quyền.

### 3.3. Public claim và registered claim liên hệ thế nào?

Cả hai phục vụ khả năng chia sẻ tên claim giữa các bên. **Đăng ký IANA** tạo tham chiếu chính thức đến định nghĩa được công bố; **tên chống xung đột** cho phép các tổ chức định nghĩa tên mới một cách độc lập mà giảm nguy cơ trùng tên. Vì vậy không nên coi mọi tên claim được công bố là đã đăng ký IANA, cũng không nên cho rằng mỗi tên URI phải được IANA đăng ký mới sử dụng được.

Khi một khái niệm đã có registered claim với cùng ý nghĩa và kiểu dữ liệu thích hợp, **ưu tiên dùng tên đã đăng ký**. Tạo tên public khác cho cùng ngữ nghĩa thường làm tăng công việc ánh xạ và dễ gây hiểu nhầm.

## 4. Private claims: quy ước giữa các bên tham gia

**Private Claim Name** được tạo theo thỏa thuận riêng giữa issuer và bên nhận. Tên thường ngắn, dễ đọc và phù hợp khi phạm vi tích hợp được kiểm soát:

```json
{
  "iss": "https://id.example.org",
  "sub": "employee_18",
  "aud": "https://inventory.example.org",
  "exp": 1893456900,
  "store_id": "store_27",
  "store_role": "stock_editor",
  "inventory_region": "north"
}
```

Trong hợp đồng của API kho, `store_id` có thể nghĩa là cửa hàng mà người dùng đang thao tác, `store_role` là vai trò tại cửa hàng đó. Những tên này **không có nghĩa chung mặc định trong JWT**. Một API nhân sự hoặc nhà cung cấp token khác hoàn toàn có thể dùng `store_role` với một định nghĩa khác.

### Khi nào private claims phù hợp?

- Issuer và các API nhận token nằm trong cùng phạm vi kiểm soát, có chung phiên bản hợp đồng.
- Tên có ngữ nghĩa chỉ thuộc một nghiệp vụ cụ thể và không cần công bố để tái sử dụng rộng rãi.
- Các bên có cơ chế thay đổi, kiểm thử và từ chối những claim không đúng kiểu hoặc không rõ nguồn phát hành.

### Rủi ro chính: xung đột tên và xung đột nghĩa

Giả sử hệ thống A phát hành `"level": 3` nghĩa là **cấp bậc khách hàng**, còn hệ thống B hiểu `level = 3` là **cấp quyền duyệt giao dịch**. Nếu B chấp nhận token từ A và dùng thẳng `level` để cấp quyền, lỗi đã vượt ra khỏi vấn đề đặt tên thành **sai ranh giới tin cậy**.

Do đó, không bao giờ diễn giải private claim chỉ bằng tên khóa. Cần ràng buộc với **issuer được phép phát hành, audience, loại token, phiên bản hợp đồng và ngữ nghĩa đã thống nhất**. Khi hệ thống mở rộng sang đối tác hoặc nhiều issuer, nên xem xét tên chống xung đột hoặc một hợp đồng rõ ràng cho từng issuer, thay vì ghép các private claims có vẻ giống nhau.

**Private không đồng nghĩa dữ liệu riêng tư.** Giá trị `store_role` hoặc `store_id` trong JWT ký vẫn có thể được người giữ token đọc. Không đưa mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào bất kỳ nhóm claim nào.

## 5. So sánh ba nhóm qua một nhu cầu nghiệp vụ

Xét nhu cầu: API đơn hàng phải biết **ai** gửi yêu cầu, **token dành cho API nào**, **hạn sử dụng**, và **cửa hàng đang thao tác**.

| Nhu cầu | Tên claim | Loại | Giải thích |
| --- | --- | --- | --- |
| Chủ thể | `sub` | Registered | Tên chung cho chủ thể, cần hiểu trong phạm vi issuer |
| API nhận token | `aud` | Registered | Dùng để kiểm tra bên nhận dự kiến |
| Hạn token | `exp` | Registered | Định dạng và ngữ nghĩa thời gian đã được chuẩn hóa |
| Cửa hàng theo hợp đồng nội bộ | `store_id` | Private | Gọn trong hệ thống khép kín, nhưng tên dễ trùng với bên khác |
| Cửa hàng dùng chung với các đối tác | `https://claims.example.org/store_id` | Public dạng tên chống xung đột | Giảm khả năng va chạm tên giữa các tổ chức; vẫn phải công bố định nghĩa |

Không cần vừa đưa `store_id` vừa đưa `https://claims.example.org/store_id` vào cùng token nếu chúng chỉ biểu thị cùng một giá trị và không có nhu cầu chuyển đổi cụ thể. Khi cần hỗ trợ di trú, phải quy định rõ claim nào là nguồn chuẩn, cách so sánh nếu cả hai hiện diện và thời điểm ngừng nhận tên cũ.

Một token hoàn toàn có thể chứa **đồng thời** registered claims và private/public claims. Ba nhóm phân loại **tên claim**, không phải ba kiểu JWT tách biệt.

## 6. Nguyên tắc chọn và đặt tên claims

### Bước 1 — Xác định dữ liệu cần truyền

Bắt đầu từ câu hỏi nghiệp vụ, không từ cấu trúc database: API cần định danh chủ thể, định tuyến đến tenant hay kiểm tra phạm vi thao tác nào? Dữ liệu có thay đổi nhanh và cần được tra cứu tại thời điểm xử lý không? Không nên đưa toàn bộ hồ sơ người dùng hoặc trạng thái giao dịch vào token chỉ để tránh gọi dịch vụ.

### Bước 2 — Kiểm tra registered claims hiện có

Tra [IANA JWT Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml) và đặc tả liên quan để tránh tự tạo một tên mới đã có chuẩn. Tên giống nhau chưa đủ; cần kiểm tra **ý nghĩa, kiểu giá trị và ngữ cảnh giao thức**. Ví dụ, `sub` không phải nơi ghi tên hiển thị của người dùng, mà dùng định danh chủ thể theo hợp đồng.

### Bước 3 — Đánh giá ranh giới tích hợp

Nếu nhiều tổ chức hoặc nhiều nhà phát hành độc lập sẽ dùng chung hợp đồng, ưu tiên một tên công khai có định nghĩa rõ ràng, đăng ký được hoặc có không gian tên chống xung đột. Nếu tất cả bên tham gia đều được quản lý chung, private claim có thể đủ, miễn là quyền phát hành và cách dùng được mô tả.

### Bước 4 — Viết hợp đồng cho từng claim

Một hợp đồng tối thiểu nên nêu:

| Thuộc tính | Ví dụ cho `store_id` |
| --- | --- |
| Tên chính xác | `store_id` (phân biệt chữ hoa/chữ thường) |
| Nhóm và phạm vi | Private claim của hệ thống quản lý cửa hàng |
| Kiểu và dữ liệu hợp lệ | Chuỗi không rỗng, mã cửa hàng theo định dạng được mô tả |
| Ngữ nghĩa | Cửa hàng mà token được phát hành để thao tác |
| Ai phát hành được | Issuer đã kiểm tra quyền lựa chọn cửa hàng |
| Bên tiêu thụ | API đơn hàng trong `aud` |
| Bắt buộc ở đâu | Bắt buộc với các endpoint có ngữ cảnh cửa hàng |
| Độ tươi và nguồn dữ liệu | Quyền thành viên cửa hàng phải được kiểm tra theo chính sách hiện hành |
| Hành vi khi thiếu hoặc sai | Từ chối yêu cầu cần claim đó; không tự cấp quyền mặc định |
| Quy tắc thay đổi | Thay đổi tên/kiểu phải có kế hoạch tương thích hoặc phát hành phiên bản hợp đồng mới |

### Bước 5 — Kiểm tra đầy đủ ở bên nhận

Bên nhận cần xác minh chữ ký hoặc các bảo vệ mật mã phù hợp, thuật toán được chấp nhận, khóa tin cậy, `iss`, `aud`, thời gian, loại token và những ràng buộc theo hồ sơ trước khi dùng các claims để xác định chủ thể hoặc quyền. Sau đó mới kiểm tra **kiểu dữ liệu, giá trị hợp lệ và chính sách nghiệp vụ**.

Chẳng hạn, `store_role: "stock_editor"` không mặc nhiên cho phép sửa mọi đơn hàng của cửa hàng. API vẫn cần kiểm tra quyền áp dụng lên **tài nguyên cụ thể**, trạng thái đơn hàng và các luật hiện hành. Tính hợp lệ của JWT không thay thế cho phân quyền nghiệp vụ.

## 7. Những lỗi thiết kế dễ gặp

### 7.1. Tự đặt tên trùng hoặc gần giống registered claim

Không dùng `exp` để biểu thị “ngày hết hạn hợp đồng” dưới dạng chuỗi, vì `exp` đã có nghĩa và kiểu dữ liệu riêng trong JWT. Nếu cần hạn hợp đồng, dùng tên khác có định nghĩa rõ, chẳng hạn `contract_expires_at` trong phạm vi nội bộ hoặc tên public thích hợp.

Tương tự, không dùng `aud` để lưu “phòng ban công tác”, `sub` cho “tên hiển thị” hoặc `iss` cho “mã chi nhánh”. Gán lại ý nghĩa sẽ làm hỏng kiểm tra token và khả năng tương tác.

### 7.2. Nghĩ `roles`, `scope`, `permissions` luôn tương đương

Nhiều hồ sơ giao thức và nhà cung cấp định danh có quy ước riêng về `scope`, `roles`, `permissions` và kiểu dữ liệu của chúng. Không nên coi các tên đó là đồng nghĩa, hay mặc định một tên nào cũng là private claim trong mọi ngữ cảnh. Cần đọc đặc tả/hợp đồng tương ứng và xây dựng ánh xạ rõ ràng nếu có nhiều issuer.

### 7.3. Tin claim từ token chỉ mới giải mã

Payload JWT chỉ là một đối tượng JSON cho đến khi token đã được xác minh theo chính sách. Một bên tấn công có thể tự tạo payload chứa `"role": "admin"`. Không cấp quyền dựa vào việc Base64URL giải mã được, hoặc vào tên claim trông có vẻ chuẩn.

### 7.4. Không xử lý xung đột trường JSON

Đối tượng JSON không nên có hai thành viên trùng tên. RFC 7519 yêu cầu tên claim trong JWT Claims Set là duy nhất; bên phân tích phải **từ chối tên trùng** hoặc dùng trình phân tích chỉ trả về thành viên trùng xuất hiện cuối theo quy tắc mà RFC cho phép. Trong triển khai bảo mật, ưu tiên **từ chối payload có tên claim trùng**, tránh việc các thành phần diễn giải khác nhau.

Ví dụ payload không nên chấp nhận:

```json
{
  "sub": "user_42",
  "store_role": "viewer",
  "store_role": "admin"
}
```

Hai hệ thống phân tích JSON khác nhau có thể không đưa ra cùng kết quả nếu không thống nhất quy tắc. Ngoài ra, tên claim phân biệt chữ hoa/chữ thường: `store_id` và `Store_Id` là hai tên khác nhau, không nên tự chuyển đổi tùy tiện khi phân quyền.

### 7.5. Thay đổi ý nghĩa claim khi triển khai phiên bản mới

Ban đầu `tenant_id` là tenant người dùng **đang chọn**, nhưng sau đó đổi thành tenant **sở hữu tài khoản** mà vẫn giữ nguyên tên. API cũ có thể tiếp tục tin giá trị theo nghĩa cũ và truy cập nhầm dữ liệu. Với thay đổi ngữ nghĩa, cần tên mới hoặc phiên bản hợp đồng rõ ràng, kế hoạch chuyển đổi và kiểm thử tương thích giữa issuer với consumer.

### 7.6. Nhầm tên công khai với thông tin đáng tin

Claim dạng `https://claims.example.org/is_admin` có thể giảm xung đột tên nhưng **không chứng minh quyền quản trị**. Người nhận vẫn phải tin đúng issuer, hiểu hợp đồng và áp dụng chính sách phân quyền tại thời điểm sử dụng. Người kiểm soát một URI namespace không mặc nhiên có quyền cấp đặc quyền cho mọi API.

## 8. Tình huống thực tế: mở API cho đối tác

Ban đầu, một hệ thống bán hàng chỉ dùng JWT nội bộ:

```json
{
  "iss": "https://id.shop.example.org",
  "sub": "user_42",
  "aud": "https://orders.shop.example.org",
  "exp": 1893456900,
  "tenant_id": "shop_17",
  "role": "admin"
}
```

Ở giai đoạn này, `tenant_id` và `role` là các private claims; `admin` được định nghĩa là quản lý trong cửa hàng `shop_17`.

Khi mở API cho đối tác, bên đối tác cũng có claim `role: "admin"` nhưng nghĩa là quản lý tài khoản đối tác. Nếu API nhập hai giá trị vào cùng mô hình quyền không phân biệt issuer, rất dễ cấp quyền sai.

Một phương án thiết kế lại:

1. Giữ registered claims `iss`, `sub`, `aud`, `exp` theo đúng ý nghĩa chuẩn; API chấp nhận từng issuer theo cấu hình và kiểm tra audience.
2. Định nghĩa công khai các khẳng định chia sẻ, chẳng hạn `https://claims.shop.example.org/store_id` cho cửa hàng và `https://claims.shop.example.org/store_role` cho vai trò tại cửa hàng, kèm kiểu và tập giá trị hợp lệ.
3. Chỉ chấp nhận hai claim trên khi issuer được ủy quyền phát hành chúng và token thuộc hồ sơ tương ứng; không suy ra vai trò toàn cục từ chữ `admin`.
4. Dịch vụ đơn hàng tiếp tục kiểm tra quyền hiện hành trên đơn hàng thực tế, bao gồm phân vùng cửa hàng và luật sở hữu.
5. Nếu chuyển từ `tenant_id`/ `role` sang tên mới, công bố thời gian tương thích, cách xử lý hai trường cùng xuất hiện và ngày chấm dứt tên cũ.

Không bắt buộc mọi hệ thống phải đổi sang URI claim. Điều quan trọng là hợp đồng tin cậy **giữ nguyên nghĩa giữa các bên**, có cách tránh xung đột và có kiểm soát quyền phát hành.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Token thiếu `jti` có mặc nhiên vi phạm RFC 7519 không?

**Trả lời:** Không. `jti` là registered claim, nhưng không bắt buộc trong mọi JWT. Một hồ sơ ứng dụng có thể yêu cầu `jti` để thực hiện chính sách của mình.

**Câu 2.** Đặt tên `https://claims.example.org/tenant_id` có khiến JWT tự động được mã hóa hoặc quyền tenant tự động hợp lệ không?

**Trả lời:** Không. Đây là cách đặt tên chống xung đột. Tính bí mật đến từ cơ chế bảo vệ token; tính đáng tin đến từ issuer và quy trình xác minh; quyền còn phụ thuộc luật nghiệp vụ.

**Câu 3.** Hai issuer cùng gửi `"role": "admin"`. Có thể gộp luôn thành quyền admin chung không?

**Trả lời:** Không. Đây là private claim (trừ khi một hợp đồng/đặc tả cụ thể định nghĩa khác); ý nghĩa có thể khác nhau theo issuer và audience. Phải ánh xạ theo hợp đồng và ngữ cảnh quyền.

**Câu 4.** Khi cần thêm claim `order_id` cho hàng chục đối tác, nên cân nhắc điều gì?

**Trả lời:** Kiểm tra trước registered claims có phù hợp không. Nếu cần tên mới cho nhiều bên, chọn tên public có tính chống xung đột hoặc quy trình đăng ký phù hợp, công bố kiểu/ý nghĩa và quy tắc tin cậy. Không chỉ phát hành một private name ngắn rồi kỳ vọng mọi đối tác hiểu giống nhau.

## 10. Ghi nhớ khi thiết kế JWT claims

**Registered claims** giúp tái sử dụng tên và ngữ nghĩa đã được đăng ký. **Public claims** cho phép mở rộng khả năng tương tác bằng định nghĩa có kiểm soát xung đột. **Private claims** tạo sự linh hoạt cho các bên đã có thỏa thuận trực tiếp, nhưng cần quản lý rủi ro trùng tên và sai nghĩa.

Khi thiết kế token cho một nghiệp vụ, hãy chọn tên claim dựa trên phạm vi sử dụng, thiết lập hợp đồng chính xác cho cả issuer lẫn bên nhận, và giữ kiểm tra phân quyền tại nơi sở hữu tài nguyên. Việc đặt tên đúng giúp hệ thống hiểu nhau; **xác minh token và thực thi chính sách** mới quyết định liệu một yêu cầu được chấp nhận hay không.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Section 4: JWT Claims](https://www.rfc-editor.org/rfc/rfc7519#section-4): định nghĩa ba loại tên claim, registered claims và yêu cầu về trùng tên.
- [RFC 7519 — Section 10: IANA Considerations](https://www.rfc-editor.org/rfc/rfc7519#section-10): cơ chế registry cho JWT claim names.
- [IANA — JSON Web Token Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml): danh mục claim names được đăng ký và tài liệu định nghĩa.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành bảo mật về kiểm tra token, issuer, audience và tránh nhầm lẫn giữa các loại JWT.
