# Kiểm tra expiration và not-before

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích ý nghĩa của hai claim thời gian **exp (expiration time)** và **nbf (not before)** trong JSON Web Token (JWT), phân biệt chúng với **iat (issued at)**.
- Áp dụng chính xác điều kiện biên: JWT **hết hạn tại thời điểm exp** và **chưa được sử dụng trước thời điểm nbf**.
- Đọc **NumericDate** đúng đơn vị giây kể từ Unix epoch, tránh nhầm giây với mili giây và nhầm thời gian UTC với múi giờ hiển thị.
- Chọn **clock skew/leeway** nhỏ, có giới hạn để xử lý sai lệch đồng hồ, mà không vô tình kéo dài hiệu lực token quá mức.
- Thiết kế kiểm tra thời gian cùng với xác minh chữ ký/trạng thái, issuer, audience, loại token, scope và phân quyền tại Resource Server.
- Viết hoặc kiểm thử bộ xác minh thời gian theo các tình huống hết hạn, chưa có hiệu lực, thiếu claim, sai kiểu dữ liệu, đồng hồ lệch và token đã bị thu hồi.

## 1. Vì sao chữ ký hợp lệ vẫn chưa đủ?

Giả sử Authorization Server phát hành access token cho client gọi Orders API lúc 10:00. Token được ký đúng và có scope **orders:read**, nhưng chỉ có hiệu lực trong 15 phút.

- Lúc **10:05**, token có thể được chấp nhận nếu các điều kiện khác cũng đúng.
- Lúc **10:15**, token đã tới mốc hết hạn; Resource Server không nên chấp nhận nó chỉ vì chữ ký vẫn hợp lệ.
- Nếu token được đặt chỉ có hiệu lực **từ 10:03**, mọi request trước mốc này phải bị từ chối dù chữ ký đúng.

Điều này cho thấy **chữ ký bảo vệ nguồn phát hành/tính toàn vẹn**, còn **claims thời gian giới hạn khi nào token được sử dụng**. Không thể dùng việc xác minh chữ ký để thay cho việc kiểm **exp** và **nbf**.

Trong hệ thống OAuth 2.0/OIDC, cần phân biệt hai lớp:

1. **Token validation:** Token đúng loại, đúng issuer và audience, chữ ký/trạng thái hợp lệ, nằm trong khoảng hiệu lực?
2. **Authorization:** Principal có quyền làm hành động này trên tài nguyên này, ở tenant và thời điểm hiện tại không?

Token đúng khoảng thời gian mới chỉ vượt qua một phần của lớp thứ nhất; nó **không tự cấp quyền nghiệp vụ**.

## 2. exp, nbf và iat trong JWT có ý nghĩa khác nhau

RFC 7519 định nghĩa ba registered claims liên quan thời gian:

| Claim | Tên đầy đủ | Ý nghĩa | Điều kiện mặc định nếu được áp dụng |
| --- | --- | --- | --- |
| **exp** | Expiration Time | Thời điểm **từ đó trở đi** JWT không được chấp nhận. | Token chỉ hợp lệ khi thời gian kiểm tra **trước exp**. |
| **nbf** | Not Before | Thời điểm **trước đó** JWT không được chấp nhận. | Token chỉ hợp lệ khi thời gian kiểm tra **từ nbf trở đi**. |
| **iat** | Issued At | Thời điểm JWT được phát hành. | Hỗ trợ đánh giá tuổi token; **không tự thay thế exp/nbf**. |

Ví dụ payload giả định:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900
}
~~~

Đây là **payload JSON minh họa**, chưa phải JWT có chữ ký. Chênh lệch giữa **exp** và **iat** trong ví dụ là **900 giây** (15 phút).

### Các điều kiện toán học

Gọi **t** là thời điểm Resource Server đánh giá token, cùng đơn vị NumericDate.

Nếu không áp dụng dung sai thời gian (leeway):

~~~text
exp có mặt:   t < exp      => chưa hết hạn
              t >= exp     => đã hết hạn

nbf có mặt:   t >= nbf     => đã bắt đầu hiệu lực
              t < nbf      => chưa có hiệu lực

Nếu cả hai claim được yêu cầu và nbf < exp:
              nbf <= t < exp
~~~

Điểm đặc biệt quan trọng:

- Tại **t = exp**, token **đã hết hạn**. Không dùng điều kiện **t <= exp**.
- Tại **t = nbf**, token **đã được phép có hiệu lực**. Không dùng điều kiện **t > nbf** khiến token bị từ chối sai ngay tại ranh giới.
- Một JWT chỉ có **exp** có thể hợp lệ trước exp theo kiểm tra thời gian; JWT chỉ có **nbf** có thể hợp lệ từ nbf theo quy tắc nbf. **Chính sách ứng dụng/profile** có thể yêu cầu cả hai.
- **iat** không mặc định làm token có hiệu lực từ thời điểm iat hay hết hạn sau một khoảng cố định. Nếu cần giới hạn tuổi tính từ iat, đó là **quy tắc bổ sung** cần định nghĩa rõ.

> Các điều kiện trên giả sử token đã qua những kiểm tra khác. Dữ liệu exp/nbf của một payload chưa được xác minh **không được dùng như bằng chứng hợp lệ**.

## 3. NumericDate: giây, không phải mili giây

Theo RFC 7519, các claims thời gian như **exp**, **nbf**, **iat** có giá trị **NumericDate**: số giây tính từ Unix epoch **1970-01-01T00:00:00Z**, theo cách đếm thời gian được RFC định nghĩa.

Đặc điểm quan trọng:

- NumericDate có thể là số nguyên hoặc số có phần thập phân theo chuẩn, không nhất thiết chỉ là số nguyên.
- Giá trị này **không phải** chuỗi thời gian đã định dạng như **2026-11-23T10:00:00+07:00**.
- Giá trị này **không phải** số mili giây thường có từ JavaScript **Date.now()**.
- Múi giờ Việt Nam hay UTC chỉ ảnh hưởng cách **hiển thị** thời gian, không làm thay đổi instant thực tế của exp/nbf.
- **iat**, **nbf** và **exp** phải được giải thích theo cùng một hệ thời gian; không so một bên giây và một bên mili giây.

Ví dụ đơn vị trong Java/JavaScript:

~~~text
Unix seconds:       1_730_000_000
Unix milliseconds:  1_730_000_000_000

Cùng một instant, nhưng khác đơn vị gấp 1000 lần.
~~~

### Lỗi đơn vị phổ biến

~~~text
// Sai vì nowMillis và expSeconds khác đơn vị
nowMillis = currentTimeMillis()
if (nowMillis >= jwt.expSeconds) reject(EXPIRED)

// Một cách so sánh phù hợp hơn
nowSeconds = currentTimeMillis() / 1000
if (nowSeconds >= jwt.expSeconds) reject(EXPIRED)
~~~

Mã giả trên dùng số giây nguyên để minh họa. Khi xử lý NumericDate có phần thập phân hoặc yêu cầu độ chính xác cao, hãy chuyển cả hai bên về **Instant** với độ chính xác phù hợp thay vì cắt cụt không có chủ đích.

### Lỗi làm token sống quá lâu

Ngược lại, nếu lấy giá trị **exp theo mili giây** của một hệ thống riêng nhưng lại đọc nó như giây, token có thể bị hiểu là còn hạn rất xa trong tương lai. Đây là lỗi nghiêm trọng vì làm vô hiệu giới hạn tuổi token.

Để chống lỗi dữ liệu, server nên:

1. Parse exp/nbf theo schema của **profile được tin cậy**, không chấp nhận mọi kiểu dữ liệu tùy ý.
2. Từ chối giá trị vượt phạm vi hợp lý hoặc gây overflow khi tính toán.
3. Áp giới hạn tuổi/thời gian sống tối đa theo chính sách nếu API yêu cầu.
4. Kiểm thử giá trị theo giây, mili giây, phân số, số âm và số rất lớn.

## 4. Kiểm tra expiration chính xác

Claim **exp** xác định mốc mà token không còn được chấp nhận. Theo RFC 7519, thời gian xử lý phải **trước** thời điểm exp thì yêu cầu mới đạt điều kiện expiration.

Xem ví dụ không có leeway:

~~~text
exp = 1_000

t = 999       -> chưa hết hạn
t = 1_000     -> hết hạn
t = 1_001     -> hết hạn
~~~

Một bộ kiểm tra sai có thể cho phép t bằng exp:

~~~text
Sai: if (now > exp) reject
Đúng: if (now >= exp) reject
~~~

Trong hệ thống có độ phân giải tới mili giây hoặc phần lẻ giây, điều kiện vẫn như vậy: **now phải nhỏ hơn exp**. Đừng thay đổi logic chỉ vì chọn cách làm tròn khác.

### Thiếu exp xử lý thế nào?

Trong JWT nói chung, các registered claims có thể là tùy chọn, trừ khi profile hoặc ứng dụng yêu cầu. Tuy nhiên, với **access token dùng cho API bảo vệ dữ liệu**, chính sách an toàn thường yêu cầu thời gian sống hữu hạn và một exp hợp lệ; nhiều token profile chuyên biệt cũng có yêu cầu rõ ràng về exp.

Do đó, không nên suy luận:

~~~text
Nếu không có exp thì mặc nhiên không bao giờ hết hạn.
~~~

Thay vào đó, hãy quy định theo hợp đồng:

~~~text
Nếu access token profile yêu cầu exp:
    exp vắng mặt hoặc sai kiểu -> từ chối token.
~~~

Với opaque token, thời điểm hết hạn có thể được Authorization Server quản lý trong trạng thái token và phản ánh qua introspection; Resource Server không tự bóc một chuỗi opaque để suy ra exp.

### Kiểm tra TTL tối đa bổ sung

Một JWT được ký hợp lệ nhưng có exp cách iat nhiều năm vẫn có thể vi phạm chính sách nội bộ nếu Resource Server chỉ muốn chấp nhận access token tuổi tối đa 15 phút.

Khi có yêu cầu này, validator nên thêm quy tắc **max token lifetime**, ví dụ:

~~~text
Giới hạn được cấu hình:  15 phút
Token:                  iat = 1_000, exp = 101_000
Kết luận:               từ chối theo policy vì vòng đời quá dài
~~~

Giới hạn 15 phút chỉ là **ví dụ chính sách**, không phải giá trị mặc định của OAuth hay JWT. Cần hiểu rõ semantics của iat/exp theo profile, đồng thời kiểm tra tính hợp lý của cặp thời gian này.

## 5. Kiểm tra not-before chính xác

Claim **nbf** xác định mốc mà **trước đó** token không được chấp nhận. Nó có thể dùng cho token phát hành trước thời điểm bắt đầu quyền truy cập, quy tắc thời gian của một phiên hoặc trường hợp có thời gian kích hoạt cụ thể.

Không có leeway:

~~~text
nbf = 1_000

t = 999       -> chưa có hiệu lực
t = 1_000     -> đã đạt điều kiện not-before
t = 1_001     -> đã đạt điều kiện not-before
~~~

Mã giả:

~~~text
if (now < nbf) reject(NOT_YET_VALID)
~~~

**Không dùng nbf như ngày hết hạn.** Sau thời điểm nbf, token vẫn có thể bị từ chối vì exp, chữ ký, issuer, audience, scope, thu hồi hoặc quyền nghiệp vụ.

### nbf không phải iat

Trong một số token, **nbf** có thể bằng **iat**; nhưng không nên mặc định hai giá trị này luôn trùng nhau.

~~~text
iat = 1_000     // phát hành
nbf = 1_300     // bắt đầu dùng sau 300 giây
exp = 2_200     // hết hạn
~~~

Trong tình huống này, token đã được phát hành trước khi nó được phép sử dụng. Nếu validator chỉ kiểm iat mà bỏ nbf, nó có thể chấp nhận token quá sớm.

### Có nên từ chối nbf lớn hơn exp?

Nếu cả hai claims có mặt và **nbf >= exp**, không tồn tại khoảng thời gian dương nào thỏa **nbf <= t < exp** khi không leeway. Bộ validator có thể từ chối token vì cấu hình thời gian bất nhất theo policy.

Ngay cả khi có leeway, không nên dùng dung sai để biến token thời gian sai logic thành một token hợp lệ lâu dài. Nên quy định tính nhất quán của claims và sinh token đúng từ Authorization Server.

## 6. Leeway: dung sai lệch đồng hồ, không phải thêm thời hạn tùy ý

Trong hệ thống phân tán, đồng hồ của AS, API gateway, Resource Server và client có thể lệch một lượng nhỏ. RFC 7519 cho phép validator áp một **leeway nhỏ**, thường ở quy mô vài phút hoặc ít hơn, để tính tới clock skew.

Nếu gọi **L** là leeway cho phép, một cách biểu diễn nhất quán là:

~~~text
Expiration:
    hợp lệ nếu now < exp + L

Not-before:
    hợp lệ nếu now + L >= nbf

Không có leeway:
    L = 0
~~~

**Những công thức này chủ động mở rộng khoảng chấp nhận token.** Do đó, L phải được cấu hình từ phía Resource Server theo rủi ro và sai số đồng hồ đo được; không để client chọn L hoặc chỉnh exp để né kiểm tra.

Ví dụ:

~~~text
exp = 1_000
nbf = 800
L   = 30 giây

now = 970   -> hợp lệ theo thời gian
now = 1_000 -> vẫn có thể được chấp nhận vì leeway (nhưng đã tới exp)
now = 1_029 -> vẫn nằm trong dung sai
now = 1_030 -> hết hạn theo chính sách có L=30
~~~

Một ví dụ not-before:

~~~text
nbf = 1_000
L   = 30 giây

now = 969 -> chưa có hiệu lực
now = 970 -> có thể được chấp nhận vì leeway
now = 999 -> có thể được chấp nhận vì leeway
now = 1_000 -> đã tới thời điểm nbf
~~~

**Cẩn trọng:** L cho exp kéo dài khả năng dùng token sau exp; L cho nbf cho phép dùng sớm hơn nbf. Với các quyền nhạy cảm hoặc token có lịch kích hoạt nghiêm ngặt, có thể cần L nhỏ hơn hoặc không có leeway cho claim tương ứng, theo hợp đồng và chính sách rủi ro.

### Có nên đặt L bằng hàng giờ để giảm lỗi?

Không. Một leeway quá lớn có thể làm token hết hạn vẫn được chấp nhận lâu hoặc token chưa tới thời điểm hiệu lực được sử dụng sớm quá mức. Nếu các server lệch đồng hồ nhiều, hãy **sửa đồng bộ thời gian** thay vì dùng leeway lớn che giấu sự cố.

### Có nên dùng cùng một L cho exp và nbf?

Có thể, nhưng không bắt buộc nếu profile/thư viện hỗ trợ cấu hình riêng. Điều quan trọng là có quy tắc rõ ràng, được kiểm thử theo rủi ro và thống nhất giữa các API chấp nhận cùng loại token. Không nên để mỗi đội tự thêm dung sai khác nhau mà không kiểm soát.

## 7. iat là dữ liệu thời gian phát hành, không thay cho exp hoặc nbf

Claim **iat (Issued At)** chỉ thời điểm JWT được tạo. Nó thường giúp phân tích tuổi token, xác minh tính hợp lý về thời gian hoặc hỗ trợ quy tắc riêng như giới hạn tuổi tối đa.

Một số nhầm lẫn phổ biến:

| Nhận định sai | Thực tế |
| --- | --- |
| Có iat là biết token lúc nào hết hạn. | Không. Cần exp hoặc quy tắc lifetime rõ ràng được profile/chính sách thiết lập. |
| Token hợp lệ khi now lớn hơn iat, không cần nbf. | Không. nbf độc lập và có thể ở tương lai so với iat. |
| iat luôn trùng nbf. | Không bắt buộc. |
| iat của JWT mới bằng thời điểm user đăng nhập lại. | Không. Token có thể được phát hành qua refresh token mà không có xác thực người dùng mới. |
| iat nằm trong quá khứ chứng minh token chưa bị thu hồi. | Không. Trạng thái thu hồi/phiên là kiểm tra riêng. |

Một số profile yêu cầu iat; hệ thống cũng có thể từ chối token có iat quá xa trong tương lai theo giới hạn clock skew hoặc có tuổi lớn hơn chính sách cho phép. Đó là **quy tắc kiểm tra thêm**, không phải thay đổi định nghĩa của exp và nbf.

Trong OIDC, **auth_time** (khi có) chỉ thời gian người dùng được xác thực. **iat** của ID token không thay thế auth_time nếu ứng dụng cần chứng minh xác thực gần đây hoặc step-up.

## 8. Thứ tự trách nhiệm: không tin exp/nbf trong token giả

Client có thể dễ dàng tự tạo một payload JSON với exp đặt xa trong tương lai. Vì vậy, **exp hợp lệ về mặt số học không thể biến token giả thành token đáng tin**.

Quy trình hợp lý với JWT access token:

1. Nhận token từ kênh được phép và nhận diện đúng token profile/format.
2. Dùng bộ xác minh được cấu hình cho **issuer đã tin cậy**, với tập thuật toán/khóa được phép; chống token confusion.
3. Xác minh chữ ký JWT; nếu token được mã hóa theo profile thì xử lý mã hóa đúng đặc tả.
4. Kiểm **iss**, **aud**, loại token và các claims bắt buộc theo profile.
5. Kiểm **exp**, **nbf**, **iat nếu policy yêu cầu**, tính nhất quán và leeway đã cấu hình.
6. Kiểm token bị thu hồi/trạng thái phiên hoặc sender binding nếu API yêu cầu.
7. Kiểm **scope**, principal, tenant, permission và chính sách của tài nguyên.

Một số thư viện thực hiện các bước trong pipeline khác nhau. Điều bất biến là **không dùng claims chưa xác minh để cấp quyền hoặc chọn nguồn tin cậy tùy ý**.

~~~mermaid
flowchart TD
    A["Nhận access token"] --> B{"Đúng profile và issuer tin cậy?"}
    B -->|Không| X["Từ chối token"]
    B -->|Có| C{"Chữ ký/trạng thái và audience hợp lệ?"}
    C -->|Không| X
    C -->|Có| D{"exp hợp lệ với leeway cấu hình?"}
    D -->|Không| X
    D -->|Có| E{"nbf hợp lệ với leeway cấu hình?"}
    E -->|Không| X
    E -->|Có| F{"Scope, sender proof và trạng thái bổ sung đạt?"}
    F -->|Không| X
    F -->|Có| G{"Principal có quyền trên tài nguyên?"}
    G -->|Không| Y["Từ chối thao tác"]
    G -->|Có| H["Cho phép yêu cầu"]
~~~

**Chữ ký và hiệu lực thời gian là hai kiểm tra khác nhau.** JWT có chữ ký hợp lệ nhưng đã hết hạn phải bị từ chối; JWT có exp trong tương lai nhưng chữ ký không hợp lệ cũng phải bị từ chối.

## 9. JWT và opaque token kiểm tra thời gian khác nhau thế nào?

Một JWT access token có thể chứa **exp** và **nbf** để Resource Server xác minh tại chỗ, sau khi xác minh chữ ký/issuer/audience phù hợp. Opaque access token không yêu cầu Resource Server tự đọc claims từ chuỗi token.

| Khía cạnh | JWT access token tự xác minh | Opaque access token qua introspection |
| --- | --- | --- |
| Nguồn kiểm thời gian | Claims đã được xác minh bằng chữ ký và profile tin cậy. | Trạng thái/token metadata được AS trả qua kênh introspection tin cậy. |
| exp/nbf | RS kiểm đúng thời gian sau khi kiểm token hợp lệ. | AS thường tính trạng thái active có xét hiệu lực; RS áp các ràng buộc thuộc tính do profile yêu cầu khi được cung cấp. |
| Thu hồi sớm | Không tự có chỉ từ exp/nbf; cần cơ chế trạng thái riêng. | AS có thể trả **active=false** khi token bị thu hồi/hết hạn theo chính sách. |
| Cache | Khóa công khai và policy có thể cache; token còn hiệu lực theo exp/nbf. | Cache **active=true** có thể làm trạng thái thu hồi chậm đến RS. |
| Sai lệch đồng hồ | RS cần có clock/leeway rõ ràng. | AS và RS vẫn cần đồng bộ thời gian; cache/introspection cũng có TTL và chính sách. |

Ví dụ phản hồi introspection minh họa:

~~~json
{
  "active": true,
  "client_id": "dashboard-client",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900
}
~~~

Một phản hồi **active=true** cho biết AS coi token hoạt động theo dữ liệu của mình tại thời điểm kiểm tra. Nó không có nghĩa Resource Server được bỏ kiểm audience, scope, loại token hoặc permission của tài nguyên.

Đừng lấy chuỗi opaque token rồi cố giải mã như JWT nếu AS không định nghĩa như vậy. **Định dạng token phải theo hợp đồng với issuer**, không được suy từ số dấu chấm hoặc độ dài của chuỗi đầu vào để quyết định mức tin cậy.

## 10. Các trường hợp lỗi biên cần xử lý

| Trường hợp | Điều kiện | Hành vi mong đợi |
| --- | --- | --- |
| **Hết hạn đúng tại biên** | now = exp, L = 0. | Từ chối. |
| **Sớm một đơn vị thời gian** | now < exp, nbf đã đạt, L = 0. | Đạt kiểm tra thời gian, vẫn cần các kiểm tra khác. |
| **Chưa có hiệu lực** | now < nbf - L. | Từ chối. |
| **Vừa đạt nbf** | now = nbf. | Đạt kiểm tra nbf. |
| **Thiếu exp** | Profile yêu cầu exp. | Từ chối token sai profile. |
| **exp kiểu chuỗi** | exp = "1730000900" trong profile yêu cầu NumericDate. | Từ chối kiểu dữ liệu sai. |
| **exp vượt phạm vi** | Giá trị không parse an toàn hoặc vượt giới hạn tuổi token. | Từ chối theo schema/policy, không làm tràn số. |
| **nbf sau exp** | nbf >= exp khi policy yêu cầu khoảng hiệu lực dương. | Từ chối claims bất nhất. |
| **iat trong tương lai xa** | iat vượt now + dung sai được chấp nhận. | Từ chối nếu policy/profile kiểm iat như vậy. |
| **Thiếu nbf** | Profile cho phép thiếu. | Không áp điều kiện nbf; vẫn kiểm exp và những điều kiện khác. |
| **Nhiều máy có đồng hồ lệch** | Đồng hồ RS nhanh/chậm so với AS. | Đồng bộ thời gian; dùng leeway nhỏ có giới hạn nếu cần. |
| **Token bị thu hồi trước exp** | Token đúng chữ ký, chưa tới exp. | Từ chối nếu cơ chế thu hồi/policy đòi hỏi và trạng thái đã được phản ánh. |

Điều quan trọng là phải phân biệt **đạt kiểm tra thời gian** với **được cấp quyền**: một token đạt bảng trên vẫn có thể không hợp lệ vì sai issuer, sai audience hoặc không đủ scope.

## 11. Ví dụ Java: kiểm tra thời gian sau khi đã xác minh JWT

Ví dụ dưới đây dùng **java.time.Instant**, **Clock** và **Duration** để thể hiện điều kiện biên. Nó là **thành phần kiểm tra claims thời gian**, **không phải** một JWT decoder, không xác minh chữ ký hay issuer/audience. Trong production, hãy sử dụng thư viện bảo mật uy tín thực hiện toàn bộ validation theo profile.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class TokenTimeChecks {
    public enum Result {
        VALID_TIME,
        MISSING_EXP,
        INCONSISTENT_INTERVAL,
        NOT_YET_VALID,
        EXPIRED,
        ISSUED_IN_FUTURE
    }

    public record Times(Instant exp, Instant nbf, Instant iat) {}

    public static Result check(
            Times times, Clock clock, Duration leeway
    ) {
        Objects.requireNonNull(times);
        Objects.requireNonNull(clock);
        Objects.requireNonNull(leeway);

        if (leeway.isNegative() || leeway.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException("Unsupported leeway");
        }

        if (times.exp() == null) {
            return Result.MISSING_EXP;
        }
        if (times.nbf() != null && !times.nbf().isBefore(times.exp())) {
            return Result.INCONSISTENT_INTERVAL;
        }

        Instant now = clock.instant();

        // Từ exp trở đi không được chấp nhận, ngoại trừ leeway đã cấu hình.
        if (!now.isBefore(times.exp().plus(leeway))) {
            return Result.EXPIRED;
        }

        // Được chấp nhận từ nbf trở đi, có tính dung sai nhỏ đã cấu hình.
        if (times.nbf() != null && now.plus(leeway).isBefore(times.nbf())) {
            return Result.NOT_YET_VALID;
        }

        // Quy tắc riêng của ứng dụng: không chấp nhận iat quá xa tương lai.
        if (times.iat() != null && now.plus(leeway).isBefore(times.iat())) {
            return Result.ISSUED_IN_FUTURE;
        }

        return Result.VALID_TIME;
    }

    private TokenTimeChecks() {}
}
~~~

**Lưu ý giới hạn của ví dụ:**

- Giá trị **30 giây** là trần leeway **chỉ để minh họa policy**, không phải khuyến nghị chung cho mọi hệ thống. Có thể cấu hình **Duration.ZERO** nếu không chấp nhận lệch.
- Code giả định **exp, nbf, iat đã được parse thành Instant hợp lệ từ claims đã xác minh**. Với dữ liệu không đáng tin, cần xử lý schema và giới hạn giá trị **trước khi** gọi phương thức; phép **plus** có thể overflow với instant cực trị.
- Trong ứng dụng thật, việc chỉ kiểm thời gian rồi trả **VALID_TIME** **không đồng nghĩa JWT hợp lệ**; còn chữ ký, issuer, audience, loại token, scope, sender binding và trạng thái liên quan.
- Quy tắc kiểm **iat trong tương lai** là lựa chọn bổ sung theo policy, không được hiểu là định nghĩa bắt buộc của claim iat trong RFC 7519.
- Đặt **Clock** thành tham số giúp kiểm thử với thời điểm cố định, không phụ thuộc thời gian thật của máy chạy test.

### Một kiểm thử Java tập trung điều kiện biên

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class TokenTimeExample {
    static void example() {
        Instant exp = Instant.ofEpochSecond(1_000);
        Instant nbf = Instant.ofEpochSecond(900);
        TokenTimeChecks.Times times =
                new TokenTimeChecks.Times(exp, nbf, null);

        Clock before = Clock.fixed(
                Instant.ofEpochSecond(999), ZoneOffset.UTC);
        Clock atExp = Clock.fixed(
                Instant.ofEpochSecond(1_000), ZoneOffset.UTC);
        Clock atNbf = Clock.fixed(
                Instant.ofEpochSecond(900), ZoneOffset.UTC);

        assert TokenTimeChecks.check(times, before, Duration.ZERO)
                == TokenTimeChecks.Result.VALID_TIME;
        assert TokenTimeChecks.check(times, atExp, Duration.ZERO)
                == TokenTimeChecks.Result.EXPIRED;
        assert TokenTimeChecks.check(times, atNbf, Duration.ZERO)
                == TokenTimeChecks.Result.VALID_TIME;
    }
}
~~~

Các mốc **1000** và **900** là giá trị Unix giây giả để thử logic, không phải thời điểm phát hành token thực. Với test production, nên dùng framework test có assertion chạy được dù JVM không bật **-ea**, thay vì dựa vào **assert** của Java.

## 12. Vì sao phải đồng bộ thời gian trên nhiều máy?

Giả sử AS phát token với exp = 10:15:00 UTC, còn hai Resource Server có đồng hồ:

~~~text
AS clock:               10:14:45 UTC
Resource Server A:      10:14:45 UTC
Resource Server B:      10:15:35 UTC   // nhanh hơn 50 giây
~~~

Nếu L = 0, Server B sẽ từ chối token sớm hơn Server A dù request đến cùng lúc thực tế. Nếu Server C chạy chậm hơn AS, nó có thể chấp nhận token đã hết hạn quá lâu.

Các biện pháp:

1. Đồng bộ đồng hồ máy chủ qua hệ thống thời gian đáng tin như NTP trong môi trường được quản trị.
2. Giám sát drift, cảnh báo khi vượt ngưỡng, không chỉ tăng leeway cho đến khi mọi test “xanh”.
3. Cấu hình leeway nhỏ, tương ứng mức drift thực tế có thể chấp nhận và rủi ro token.
4. Dùng **Clock/Instant** nhất quán trong code; không lẫn UTC với múi giờ địa phương hoặc giây với mili giây.
5. Kiểm thử khi clock nhanh, chậm, khi thời gian nhảy đột ngột và khi nhiều instance API khác nhau.

### Wall clock và monotonic clock

**exp/nbf** là mốc thời gian tuyệt đối, nên cần một **wall clock** có thể ánh xạ sang Unix epoch. Đồng hồ monotonic hữu ích để đo **thời lượng** và timeout trong tiến trình, nhưng không tự quy đổi thành exp JWT nếu không có mốc tham chiếu đáng tin.

Nếu máy chủ bị đổi giờ ngược hoặc tiến đột ngột, cách kiểm token có thể thay đổi. Vì vậy, đồng bộ đồng hồ và giám sát không kém quan trọng so với code so sánh timestamp.

## 13. Expiration và not-before trong vòng đời OAuth 2.0/OIDC

**Access token:** AS có thể phát hành access token JWT chứa exp/nbf hoặc opaque token có thời hạn trong trạng thái quản lý. RS phải từ chối token không còn hiệu lực theo hợp đồng.

**Refresh token:** Refresh token được gửi tới token endpoint để xin access token mới. Thời hạn/trạng thái refresh token **độc lập** với exp của access token; refresh token có thể hết hạn, bị thu hồi, xoay vòng hoặc bị từ chối vì chính sách phiên.

**ID token OIDC:** ID token phục vụ **client/relying party**, không phải Resource Server. Client phải xác minh chữ ký, issuer, audience, exp và các điều kiện OIDC liên quan; không được dùng ID token thay access token để gọi Orders API.

**Authorization code:** Thường sống rất ngắn và chỉ đổi một lần, nhưng không phải access token để Resource Server kiểm exp như JWT. AS quản lý hiệu lực code tại token endpoint và kiểm client, redirect URI, PKCE.

### Client nên refresh trước hay sau exp?

Client có thể chủ động xin access token mới **gần thời điểm hết hạn** để tránh request bị từ chối do token hết hạn khi đi qua mạng. Tuy nhiên:

- **Client dự đoán hạn** để cải thiện trải nghiệm; **Resource Server mới là bên tự xác minh** token khi nhận yêu cầu.
- Trường **expires_in** trong token response cho biết thời gian sống access token theo định nghĩa phản hồi; **exp** là mốc tuyệt đối trong JWT khi có. Không trộn hai giá trị hoặc lấy đồng hồ client làm nguồn tin cậy để API cấp quyền.
- Nếu AS không cấp refresh token, client phải dùng luồng phù hợp để nhận token mới; không thể tự sửa exp trong JWT.
- Không retry vô hạn mọi lỗi **401**. Sai audience, token giả hoặc lỗi issuer không tự được khắc phục bằng refresh.
- Dùng cơ chế **single-flight** nếu nhiều request cùng cần refresh, đặc biệt khi refresh token rotation dùng RT một lần.

### Exp đã qua có nghĩa bị đăng xuất không?

Không nhất thiết. Một access token hết hạn chỉ nói token đó không còn dùng được. Phiên đăng nhập, sự ủy quyền và refresh token có vòng đời riêng. Ngược lại, **logout/thu hồi RT không bảo đảm mọi JWT access token đã cấp bị vô hiệu ngay** nếu RS chỉ xác minh ngoại tuyến.

## 14. Exp/nbf không thay thế thu hồi và chống phát lại

Hai claim này giới hạn **cửa sổ thời gian được chấp nhận**, nhưng không ngăn bản sao token bị đánh cắp và dùng trong cửa sổ đó.

Ví dụ:

~~~text
Token phát hành: 10:00
nbf:              10:00
exp:              10:15

10:04   Kẻ tấn công lấy một bearer access token.
10:05   Token còn hiệu lực; có thể bị dùng thử đến API.
10:06   Hệ thống phát hiện lộ token.
10:07   Policy đòi chặn request mới dù chưa đến exp.
~~~

Để đạt yêu cầu 10:07, Resource Server phải có biện pháp thu hồi/trạng thái hoặc policy động, không thể chỉ kiểm exp. Cách triển khai có thể gồm:

- **Opaque token + introspection** để kiểm trạng thái với độ mới đáp ứng SLA.
- **JWT + denylist/phiên/policy lookup** hoặc thông báo thu hồi tới API.
- **Access token sống ngắn** nhằm giới hạn cửa sổ tổn thất, nếu SLA cho phép.
- **Sender-constrained token** như DPoP hoặc mTLS theo profile để giảm khả năng bản sao bearer bị dùng khi không có khóa tương ứng.
- Kiểm **audience**, scope, tenant, permission hiện hành và chính sách giao dịch; token còn hiệu lực không có nghĩa được thao tác mọi tài nguyên.
- Với giao dịch thay đổi trạng thái, bổ sung **idempotency/nonce** nghiệp vụ chống thực hiện trùng. Exp/nbf không kiểm chứng một request đã được xử lý hay chưa.

Thời hạn và not-before cũng không thay thế kiểm **issuer, chữ ký, thuật toán, type, audience**. Mọi điều kiện phải được thực thi đúng ranh giới tin cậy.

## 15. Hành vi lỗi và observability

Nếu access token chưa có hiệu lực hoặc đã hết hạn, Resource Server thường coi đây là credential không được chấp nhận và trả **401 Unauthorized** theo profile bảo vệ API, có thể dùng Bearer error **invalid_token** theo RFC 6750. Token hợp lệ nhưng không đủ permission/scope có thể dẫn tới **403 Forbidden**; hai nhóm lỗi cần phân biệt.

Cần lưu ý:

- **Không trả toàn bộ JWT**, refresh token hoặc payload chứa dữ liệu nhạy cảm trong response lỗi hoặc log.
- Có thể ghi mã lý do nội bộ như **TOKEN_EXPIRED**, **TOKEN_NOT_YET_VALID**, **CLOCK_SKEW_DETECTED** và thông tin tối thiểu để phân tích sự cố.
- Không để client chỉ bằng cách đo lỗi có thể suy luận quá nhiều về account, khóa hoặc các trạng thái nhạy cảm.
- Theo dõi tỷ lệ token bị từ chối vì exp, nbf và chênh lệch clock giữa các node. Một đợt lỗi bất thường có thể là sự cố đồng bộ thời gian, không nhất thiết là đợt tấn công.
- Nếu dùng introspection, theo dõi cache TTL và độ trễ thu hồi để không tuyên bố “thu hồi tức thì” khi dữ liệu active vẫn còn cache.

**Không sửa đồng hồ server theo đồng hồ client** và không chấp nhận một trường **current_time** do client tự gửi để quyết định tính hợp lệ của exp/nbf.

## 16. Bộ test gợi ý cho validator

Một bộ test có thể dùng **Clock.fixed** và tạo JWT kiểm thử bằng khóa test riêng hoặc stub của thành phần parse claims. Khi test tích hợp, phải kiểm cả chữ ký, audience, issuer và policy bên cạnh thời gian.

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Đúng lúc exp, không leeway | now = exp, L = 0 | **EXPIRED**. |
| Ngay trước exp | now = exp - 1 giây, nbf đã tới | Đạt kiểm thời gian. |
| Ngay sau exp | now = exp + 1 giây, L = 0 | **EXPIRED**. |
| Trong leeway exp | now = exp + 5 giây, L = 30 giây | Có thể đạt kiểm thời gian theo policy L. |
| Vừa hết leeway | now = exp + 30 giây, L = 30 giây | **EXPIRED**. |
| Trước nbf | now = nbf - 1 giây, L = 0 | **NOT_YET_VALID**. |
| Đúng nbf | now = nbf | Đạt kiểm nbf. |
| Trong leeway nbf | now = nbf - 5 giây, L = 30 giây | Có thể đạt kiểm nbf theo policy L. |
| Quá sớm | now = nbf - 31 giây, L = 30 giây | **NOT_YET_VALID**. |
| Thiếu exp | Profile yêu cầu exp | Từ chối. |
| Thiếu nbf | Profile cho phép thiếu | Không tự coi là lỗi nếu các điều kiện khác đạt. |
| exp sai kiểu | exp là chuỗi hoặc object trong JWT profile đòi NumericDate | Từ chối schema. |
| Seconds/milliseconds | exp từ nguồn khác được truyền sai đơn vị | Từ chối/nhận diện sai schema hoặc lifetime bất hợp lý. |
| exp cực trị | Giá trị gây overflow khi cộng leeway | Từ chối an toàn, không crash/mở quyền. |
| nbf >= exp | Khoảng hiệu lực trống theo policy | Từ chối claims bất nhất. |
| iat quá xa tương lai | iat lớn hơn now + tolerance | Từ chối nếu policy có kiểm iat. |
| Chữ ký sai nhưng thời gian đúng | JWT đã bị sửa exp | Từ chối chữ ký. |
| Audience sai nhưng thời gian đúng | JWT dành cho API khác | Từ chối audience. |
| Thu hồi trước hạn | exp chưa tới nhưng token bị revoke | Từ chối theo cơ chế trạng thái được yêu cầu. |
| Máy chủ clock lệch | Hai RS có now khác nhau | Hành vi đúng leeway, cảnh báo drift. |

### Bài tập tự đánh giá

Cho các giá trị:

~~~text
iat = 1_000
nbf = 1_100
exp = 1_400
L   = 0
~~~

**Câu 1:** now = 1_050 có chấp nhận token theo thời gian không?

**Đáp án:** Không. Token chưa đạt nbf = 1_100 dù đã được phát hành từ iat = 1_000.

**Câu 2:** now = 1_100?

**Đáp án:** Đạt kiểm nbf và chưa tới exp. Vẫn cần xác minh chữ ký, issuer, audience và quyền.

**Câu 3:** now = 1_400?

**Đáp án:** Đã hết hạn, vì tại mốc exp token không được chấp nhận.

**Câu 4:** Nếu bật L = 20 giây, now = 1_390 có đạt kiểm exp không?

**Đáp án:** Có theo điều kiện thời gian có leeway; nhưng trong trường hợp này now còn trước exp ngay cả khi L = 0.

**Câu 5:** Với L = 20, now = 1_420 có đạt kiểm exp không?

**Đáp án:** Không. Đã chạm đúng ranh giới **exp + L**; điều kiện now < exp + L không còn đúng.

**Câu 6:** Nếu client tự sửa exp từ 1_400 thành 2_400 trên một JWT đã ký, token có hợp lệ không?

**Đáp án:** Không nếu chữ ký được xác minh đúng. Payload bị sửa sẽ không còn khớp chữ ký hợp lệ; không được chấp nhận chỉ vì exp mới ở tương lai.

## 17. Checklist triển khai

Trước khi đưa kiểm tra expiration và not-before vào production, hãy xác nhận:

1. **Nguồn tin cậy:** Claims chỉ được dùng sau khi xác minh token đúng issuer, thuật toán/khóa, audience và token profile; opaque token được kiểm qua AS/introspection tin cậy.
2. **Schema:** exp/nbf/iat được đọc đúng kiểu NumericDate **giây**; có kiểm giá trị không hợp lệ/overflow và giới hạn TTL nếu policy yêu cầu.
3. **Biên exp:** Bảo đảm **now >= exp** bị từ chối khi không leeway.
4. **Biên nbf:** Bảo đảm **now < nbf** bị từ chối khi không leeway.
5. **Thiếu claim:** Có quy định rõ exp/nbf/iat bắt buộc hay tùy chọn cho từng loại token/profile.
6. **Leeway:** Do server cấu hình, nhỏ, có lý do và đo được; không dùng dung sai để bù cho hệ thống đồng hồ bị lỗi.
7. **Đồng bộ thời gian:** Clock của AS/RS được giám sát, dùng UTC/Instant nhất quán, test cả drift và bước nhảy thời gian.
8. **Phân quyền:** Không coi exp/nbf đúng là được phép truy cập; vẫn kiểm scope, principal, tenant và quyền trên tài nguyên.
9. **Thu hồi:** Có chính sách rõ khi account bị khóa hoặc token bị lộ trước exp; đo độ trễ thu hồi và cache.
10. **Client refresh:** Client không tự sửa token; xử lý expires_in, refresh grant và retry có kiểm soát, tránh race.
11. **Quan sát:** Log mã lỗi và metadata tối thiểu, không log bearer token, JWT đầy đủ hoặc refresh token.
12. **Test ranh giới:** Có test exactly-at-exp, exactly-at-nbf, fractions, seconds/milliseconds, missing/invalid claims và overflow.

## Kết luận

**exp và nbf xác định khoảng thời gian JWT được phép sử dụng**: với leeway bằng 0, điều kiện thời gian là **nbf <= now < exp** khi cả hai claims có mặt. **iat** cho biết thời điểm phát hành và không tự thay thế hai giới hạn này. NumericDate sử dụng **giây Unix**, nên sai đơn vị hoặc sai điều kiện biên có thể làm token được sử dụng quá lâu hoặc bị từ chối quá sớm.

Trong OAuth 2.0/OIDC, kiểm tra thời gian chỉ là một phần của **token validation**. Một hệ thống an toàn còn phải xác minh chữ ký/trạng thái, issuer, audience, loại token, scope và quyền hiện hành; quản lý clock skew, thu hồi token và chống đánh cắp/phát lại. Đặt giới hạn thời gian đúng giúp giảm cửa sổ lạm dụng, nhưng **không biến token thành bằng chứng quyền vĩnh viễn hay thay thế chính sách phân quyền của Resource Server**.

### Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Section 2: NumericDate](https://www.rfc-editor.org/rfc/rfc7519#section-2)
- [RFC 7519 — Section 4.1.4: exp](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.4)
- [RFC 7519 — Section 4.1.5: nbf](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.5)
- [RFC 7519 — Section 4.1.6: iat](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.6)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
