# Thay đổi lược đồ claims bằng phiên bản và khoảng chuyển tiếp

## 1. Vì sao lược đồ claims cần được quản lý phiên bản?

JWT thường mang claims do issuer phát hành để Resource Server hoặc service phía sau đưa ra quyết định. Theo thời gian, mô hình dữ liệu và nghiệp vụ thay đổi: tên claim được chuẩn hóa, kiểu dữ liệu được sửa, quyền được tách nhỏ, tenant được bổ sung, hoặc một trường cũ được thay bằng cấu trúc mới.

Ví dụ, phiên bản đầu của một access token có thể chứa:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "tenant": "tenant-17",
  "roles": ["reader", "operator"],
  "exp": 1893459600
}
~~~

Sau khi hệ thống chuẩn hóa mô hình authorization, issuer muốn phát hành:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "tenant_id": "tenant-17",
  "permissions": ["orders:read", "orders:update"],
  "https://identity.example/claims_version": 2,
  "exp": 1893459600
}
~~~

Hai token có thể cùng là JWT hợp lệ về mặt mật mã, nhưng không cùng lược đồ claims. Một consumer chỉ hiểu `tenant` và `roles` có thể không xử lý đúng token mới; một consumer chỉ hiểu `tenant_id` và `permissions` có thể từ chối token cũ hoặc diễn giải sai quyền.

Vấn đề còn phức tạp hơn trong hệ thống phân tán:

- Issuer có nhiều instance hoặc region và không chuyển phiên bản đồng thời.
- Nhiều Resource Server được triển khai độc lập, có tốc độ nâng cấp khác nhau.
- Token đã phát hành vẫn còn hiệu lực sau khi schema mới được triển khai.
- Refresh token cũ có thể tiếp tục tạo access token theo schema cũ nếu issuer chưa đổi policy.
- Một số consumer xử lý message hoặc assertion trễ hơn thời điểm token được phát hành.
- Rollback ứng dụng có thể đưa một consumer cũ trở lại trong khi token schema mới vẫn đang được lưu hành.

**Quản lý phiên bản claims** xác định cấu trúc, kiểu dữ liệu và ngữ nghĩa của claims mà một token profile được phép mang. **Khoảng chuyển tiếp** là thời gian có kiểm soát trong đó issuer và consumer phối hợp hỗ trợ các phiên bản liên quan để nâng cấp mà không tạo ra khoảng trống xác minh hoặc authorization.

Mục tiêu không chỉ là parse được JSON. Consumer phải hiểu đúng ý nghĩa của dữ liệu, áp dụng đúng quyền và từ chối rõ ràng khi gặp schema không được hỗ trợ.

## 2. Phân biệt schema claims với các phiên bản khác của JWT

Một hệ thống có nhiều loại phiên bản, nhưng chúng giải quyết các vấn đề khác nhau.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| JWT/JWS/JWE serialization | Token được biểu diễn hoặc bảo vệ theo cấu trúc nào? | JWS Compact, JWE Compact |
| JOSE algorithm | Dùng thuật toán nào để ký/MAC hoặc mã hóa? | `ES256`, `RS256`, `A256GCM` |
| Signing key version | Khóa nào đã tạo chữ ký? | `kid` = `signing-k2` |
| Issuer | Ai phát hành token? | `iss` |
| Token profile/type | Token thuộc loại credential nào? | OAuth access token, ID token, assertion |
| Audience | Token dành cho resource nào? | `aud` = `orders-api` |
| Claims schema version | Claims tuân theo cấu trúc và semantics nào? | `claims_version` = 2 |
| API version | Consumer endpoint hoặc hợp đồng API nào đang được gọi? | `/v2/orders` |

Thay đổi schema claims không nhất thiết yêu cầu đổi thuật toán ký, signing key, định dạng JWS/JWE hoặc API URL. Ngược lại, xoay vòng khóa không làm schema claims tự động chuyển phiên bản.

Một token có `kid` mới vẫn có thể chứa schema cũ. Một token có schema claims v2 vẫn có thể được ký bằng khóa đang dùng cho v1. Vì vậy không dùng `kid`, `iat`, API path hoặc tên issuer làm cách suy ra schema version.

### Version thuộc về token profile

Một issuer có thể phát hành nhiều loại token với claims khác nhau: access token cho Orders API, access token cho Payments API, ID token cho client hoặc assertion cho service-to-service. Không nên giả định cùng một số version có cùng semantics trên mọi profile.

Hợp đồng nên xác định phiên bản theo ít nhất:

- Issuer/trust profile.
- Token type/profile.
- Audience hoặc resource.
- Claims schema version.
- Các claim bắt buộc, tùy chọn và bị cấm.

Ví dụ, schema version 2 của access token cho Orders API không tự động có nghĩa schema version 2 của ID token hoặc Payments API cũng giống hệt.

## 3. Chọn cách biểu diễn phiên bản claims

JWT không tự định nghĩa một registered claim chung để version mọi schema ứng dụng. Hệ thống cần thống nhất một claim mở rộng và tài liệu hóa semantics của nó.

Một lựa chọn là claim có tên collision-resistant, chẳng hạn:

~~~json
{
  "https://identity.example/claims_version": 2
}
~~~

Tên URI ở ví dụ chỉ mang tính minh họa; hệ thống cần dùng namespace do tổ chức kiểm soát. Có thể chọn tên riêng khác theo profile, miễn là issuer và consumer thống nhất và tránh xung đột với registered claims hoặc claim của bên thứ ba.

### Quy tắc cho version field

- Dùng một kiểu dữ liệu cố định, ví dụ số nguyên dương.
- Định nghĩa rõ đây là major schema version hay version đầy đủ.
- Quy định version áp dụng cho toàn bộ claims set hay chỉ một namespace.
- Quy định version có bắt buộc trên mọi token thuộc profile hay không.
- Quy định cách xử lý token thiếu version và version không được hỗ trợ.
- Không tái sử dụng cùng số version cho hai cấu trúc hoặc ngữ nghĩa khác nhau.
- Không thay đổi ý nghĩa của version đã phát hành.

Ví dụ trong bài này dùng số nguyên dương `2` làm major schema version. Những bổ sung tương thích có thể được đưa vào cùng major version nếu hợp đồng quy định consumer phải bỏ qua claim tùy chọn chưa biết. Thay đổi không tương thích phải tăng major version.

Nếu tổ chức cần ghi cả minor version, có thể dùng chuỗi có định dạng đã định nghĩa như `2.1`, nhưng tất cả consumer phải parse cùng một grammar. Không trộn số, chuỗi, số thực hoặc các kiểu dữ liệu khác nhau cho cùng claim version.

### Không dùng version để thay thế validation

Version chỉ cho biết consumer cần áp dụng lược đồ nào. Nó không chứng minh token đáng tin. Consumer chỉ được dùng version claim sau khi token đã vượt qua xác minh chữ ký/MAC hoặc giải mã JWE có xác thực, kiểm tra issuer, audience, thời hạn và token profile.

Một parser có thể đọc sơ bộ version để chọn một validator trong danh sách giới hạn, nhưng giá trị chưa xác minh không được kích hoạt discovery, tải schema từ URL tùy ý hoặc thay đổi trust configuration. Sau khi xác minh phải kiểm tra lại version và áp dụng đúng validator đã cấu hình.

## 4. Phân loại thay đổi tương thích và không tương thích

Không phải mọi thay đổi claims đều cần tăng major version. Cần phân biệt thay đổi cấu trúc với thay đổi ngữ nghĩa.

| Loại thay đổi | Ví dụ | Tương thích thường gặp |
| --- | --- | --- |
| Thêm claim tùy chọn | Bổ sung `locale` hoặc `department_id` mà consumer cũ bỏ qua | Có thể tương thích nếu schema cho phép unknown optional claims |
| Bổ sung claim bắt buộc | Consumer mới yêu cầu `tenant_id` để phân quyền | Không tương thích với consumer chưa hỗ trợ |
| Đổi tên claim | `tenant` thành `tenant_id` | Không tương thích nếu bỏ tên cũ ngay |
| Đổi kiểu dữ liệu | `roles` từ string thành array | Không tương thích |
| Đổi cấu trúc | Object quyền thành array permission | Không tương thích |
| Thu hẹp hoặc mở rộng semantics | `role=admin` đổi nghĩa hoặc được hiểu thành quyền trên mọi tenant | Thay đổi ngữ nghĩa; cần đánh giá như breaking change |
| Đổi đơn vị hoặc format | Timestamp từ giây sang mili giây | Không tương thích nếu không có hợp đồng chuyển đổi |
| Đổi semantics của claim hiện hữu | `sub` chuyển từ user ID sang account ID | Breaking change nghiêm trọng |
| Loại bỏ claim cũ | Bỏ `roles` sau khi chuyển sang `permissions` | Chỉ an toàn khi mọi consumer cũ đã ngừng cần claim |

### Thêm claim không luôn luôn là thay đổi an toàn

Một consumer có thể từ chối mọi claim chưa biết do dùng schema strict. Consumer khác có thể bỏ qua claim mới. Do đó, “thêm field” chỉ tương thích nếu hợp đồng consumer quy định rõ cách xử lý unknown optional claims.

Ngược lại, consumer không được bỏ qua claim mà schema đánh dấu là bắt buộc để đưa ra quyết định bảo mật. Nếu consumer không hiểu phiên bản hoặc trường bắt buộc, phải từ chối token theo policy.

### Không thay đổi ý nghĩa dưới cùng một tên

Nếu `roles` từng biểu thị vai trò toàn hệ thống, không được âm thầm đổi nó thành quyền trên một tenant. Dù JSON type không đổi, authorization semantics đã thay đổi và có thể tạo privilege escalation hoặc từ chối nhầm.

Khi semantics thay đổi, dùng claim mới hoặc schema major mới; mô tả rõ cách chuyển đổi và thời điểm ngừng claim cũ.

## 5. Viết hợp đồng schema trước khi thay đổi issuer

Trước khi triển khai, cần có tài liệu schema cho từng issuer/profile/version. Hợp đồng nên mô tả:

| Thuộc tính | Cần xác định |
| --- | --- |
| Schema identifier/version | Version nào và phạm vi áp dụng |
| Issuer/profile/audience | Token nào phải tuân theo schema |
| Claim name | Tên claim chính xác và namespace |
| JSON type | String, integer, boolean, array, object hoặc null nếu được phép |
| Required/optional | Có bắt buộc hay không |
| Meaning | Ngữ nghĩa nghiệp vụ và authorization |
| Constraints | Format, range, allowed values, cardinality |
| Absence/null semantics | Thiếu field khác gì field có giá trị null |
| Unknown claims | Consumer phải bỏ qua hay từ chối trong trường hợp nào |
| Deprecation | Thời điểm bắt đầu ngừng phát hành và thời điểm loại bỏ |
| Examples | Token hợp lệ, token không hợp lệ và các trường hợp biên |

Có thể dùng JSON Schema hoặc một schema registry nội bộ để mô tả cấu trúc, nhưng JSON Schema không tự định nghĩa toàn bộ semantics bảo mật của token. Cần bổ sung quy tắc về issuer, audience, token type, thời hạn, scope, tenant và cách các claims tương tác trong policy.

### Ví dụ schema contract rút gọn

~~~yaml
profile: orders-access-token
issuer: https://identity.example
audience:
  - orders-api
claims_version: 2
required:
  - iss
  - sub
  - aud
  - exp
  - https://identity.example/claims_version
  - tenant_id
  - permissions
properties:
  tenant_id:
    type: string
    non_empty: true
  permissions:
    type: array
    items:
      type: string
    unique_items: true
unknown_claims:
  optional: ignore
  security_critical: reject_if_unsupported
~~~

Đây là mô tả hợp đồng minh họa, không phải một JSON Schema chuẩn có thể dùng trực tiếp. Khi viết schema thực tế, cần dùng đúng cú pháp của công cụ đã chọn và kiểm tra cả kiểu dữ liệu lẫn semantics.

## 6. Thiết kế consumer hỗ trợ nhiều phiên bản

Trong giai đoạn chuyển tiếp, consumer mới thường cần đọc được cả schema cũ và mới. Thay vì để logic nghiệp vụ rải rác khắp ứng dụng, tạo một lớp chuyển đổi từ từng schema version sang một mô hình principal nội bộ thống nhất.

~~~mermaid
flowchart TD
    A["JWT đã xác minh"] --> B["Đọc claims_version"]
    B --> C{"Version được hỗ trợ?"}
    C -->|"v1"| D["Validator v1"]
    C -->|"v2"| E["Validator v2"]
    C -->|"Không"| F["Từ chối unsupported schema"]
    D --> G["Map sang Canonical Principal"]
    E --> G
    G --> H["Authorization và nghiệp vụ"]
~~~

Ví dụ mô hình nội bộ:

~~~text
CanonicalPrincipal {
    issuer
    subject
    audience
    tenantId
    permissions
    issuedAt
    expiresAt
    tokenProfile
}
~~~

Adapter v1 có thể ánh xạ `tenant` và `roles` sang `tenantId` và `permissions` bằng một mapping đã được định nghĩa. Adapter v2 đọc trực tiếp `tenant_id` và `permissions`.

### Mapping phải có ngữ nghĩa rõ

Ví dụ, nếu role `operator` trong v1 được chuyển thành permission `orders:update` trong v2, phải xác nhận rằng quyền cũ và mới thực sự tương đương trong mọi ngữ cảnh. Không suy diễn một role thành một permission rộng hơn chỉ để migration dễ dàng.

Nếu không thể ánh xạ an toàn, consumer phải từ chối token v1 cho thao tác đó hoặc yêu cầu token mới. Không gán quyền mặc định rộng hơn khi claim không tồn tại.

### Không đưa claims thô vào mọi tầng

Sau validation, tạo principal có kiểu và chỉ giữ trường cần thiết. Tầng authorization nên làm việc với canonical model, không cần biết tên claim v1/v2. Điều này giúp loại bỏ logic migration sau khi hết khoảng chuyển tiếp.

## 7. Expand, migrate, contract: trình tự chuyển đổi an toàn

Một quy trình phổ biến gồm ba giai đoạn.

### Giai đoạn A — Expand consumers

Trước tiên triển khai consumer có khả năng hiểu cả phiên bản cũ và mới:

- Giữ validator v1 đang hoạt động.
- Thêm validator v2 và mapping sang canonical principal.
- Kiểm thử token v1 và v2 bằng test vector.
- Triển khai tới mọi service, instance và region.
- Xác nhận không còn consumer chỉ hiểu v1 trước khi issuer bắt đầu phát hành v2.

Trong giai đoạn này issuer vẫn phát hành v1. Việc consumer hỗ trợ v2 chưa buộc issuer phải chuyển ngay.

### Giai đoạn B — Migrate issuer

Sau khi consumer sẵn sàng:

- Cập nhật issuer để phát hành v2 theo profile đã chọn.
- Có thể canary trên một nhóm client hoặc audience nếu policy hỗ trợ.
- Theo dõi tỷ lệ token theo version, validation failure và authorization decision.
- Duy trì khả năng đọc v1 trong khoảng chuyển tiếp.
- Đảm bảo mọi issuer instance/region phát hành version nhất quán theo rollout policy.

Nếu có nhiều issuer hoặc nhiều profile, chuyển từng nhóm có kiểm soát. Không để hai instance cùng issuer tùy ý phát hành hai schema khác nhau cho cùng client/audience mà không có kế hoạch tương thích.

### Giai đoạn C — Contract old schema

Chỉ loại bỏ v1 sau khi:

- Issuer đã ngừng phát hành v1 trên mọi instance/region.
- Không còn refresh flow hoặc batch job nào tiếp tục phát hành v1.
- Tất cả token v1 đã hết hiệu lực theo giới hạn được tính.
- Consumer metrics không còn request v1 trong khoảng quan sát đủ dài.
- Các consumer cũ đã được nâng cấp hoặc loại khỏi routing.
- Runbook và rollback plan không còn yêu cầu khôi phục v1-only consumer.

Sau đó mới bỏ validator v1, claim mapping cũ và các test vector chỉ phục vụ migration nếu không còn cần cho regression/security testing.

## 8. Dual-read và dual-write khi đổi tên hoặc cấu trúc claim

Một cách chuyển đổi thường gặp là hỗ trợ song song claim cũ và claim mới trong thời gian ngắn.

### Dual-read

Consumer hiểu cả tên cũ và mới:

~~~text
if claims_version == 1:
    tenantId = claims["tenant"]
    permissions = mapLegacyRoles(claims["roles"])

if claims_version == 2:
    tenantId = claims["tenant_id"]
    permissions = claims["permissions"]
~~~

Đây là cách ưu tiên khi version claim có mặt và rõ ràng. Không nên chọn schema chỉ bằng cách “field nào tồn tại thì đọc field đó” nếu hai field có thể cùng xuất hiện hoặc có semantics khác nhau.

### Dual-write

Issuer có thể phát hành cả claim cũ và mới trong token chuyển tiếp:

~~~json
{
  "tenant": "tenant-17",
  "tenant_id": "tenant-17",
  "roles": ["reader"],
  "permissions": ["orders:read"],
  "https://identity.example/claims_version": 2
}
~~~

Dual-write chỉ phù hợp khi:

- Giá trị cũ và mới có mapping tương đương đã được kiểm chứng.
- Consumer cũ vẫn cần claim cũ.
- Consumer mới có quy tắc ưu tiên claim mới rõ ràng.
- Nếu cả hai claim xuất hiện nhưng mâu thuẫn, consumer từ chối hoặc phát cảnh báo theo policy; không tùy tiện chọn một giá trị.
- Token size và dữ liệu nhạy cảm tăng thêm vẫn nằm trong giới hạn.
- Có thời điểm kết thúc dual-write.

Không dual-write hai claim có ý nghĩa khác nhau chỉ vì tên gần giống. Đặc biệt không phát hành cả role cũ và permission mới nếu mapping có thể mở rộng quyền mà chưa được phê duyệt.

### Version claim phải quyết định validator

Nếu token khai `claims_version` = 2 nhưng chỉ có các claim v1, consumer không nên âm thầm fallback sang v1. Đây là token không tuân thủ schema v2. Fallback tự động có thể che giấu lỗi issuer hoặc cho phép attacker khai thác cách diễn giải khác nhau giữa các consumer.

## 9. Xác định khoảng chuyển tiếp có giới hạn

Không nên duy trì hỗ trợ schema cũ vô thời hạn. Khoảng chuyển tiếp cần được tính từ thời điểm issuer ngừng phát hành phiên bản cũ và giới hạn tồn tại tối đa của token.

Gọi:

- `T_stop`: thời điểm cuối cùng issuer được phép phát hành token v1.
- `L_max`: thời hạn sống tối đa của token v1 tính từ lúc phát hành.
- `S_clock`: clock skew được chấp nhận.
- `P_config`: thời gian dự phòng để policy/version configuration lan truyền và cache cũ hết hiệu lực nếu consumer cache cấu hình.

Một giới hạn bảo thủ có thể xác định:

~~~text
T_remove_v1 >=
    T_stop
    + L_max
    + S_clock
    + P_config
~~~

Đây là mô hình lập kế hoạch, không phải công thức giao thức bắt buộc. Consumer rollout là điều kiện phải hoàn tất trước `T_stop`: mọi consumer cần nhận token phải hỗ trợ version mới trước khi issuer ngừng phát hành v1. `P_config` chỉ tính độ trễ phân phối policy/cache còn tồn tại sau mốc đó. Các thành phần cần được đo hoặc quy định theo kiến trúc thực tế; tránh cộng trùng những khoảng thời gian đã bao hàm nhau.

### Phải tính cả refresh token và luồng phát hành trễ

Nếu refresh token cũ vẫn cho phép cấp access token v1, việc ngừng phát hành v1 ở một instance là chưa đủ. Cần:

- Chuyển policy phát hành tại mọi Authorization Server instance/region.
- Quy định refresh token cũ khi được sử dụng sẽ cấp schema mới hay buộc re-authentication.
- Đảm bảo batch job, token exchange và service assertion không tiếp tục phát hành v1.
- Xem xét thời gian cache cấu hình và thời gian rollout của issuer.
- Ghi nhận thời điểm phát hành cuối cùng của v1 theo issuer/profile.

Nếu issuer không thể xác định token nào đã phát hành theo version nào, cần dùng `iat`, version claim hoặc metadata phát hành có kiểm soát để quan sát. Không suy luận version chỉ từ thời điểm nếu có thể có token cũ được phát hành trễ hoặc hệ thống có clock lệch.

### Không rút ngắn thời hạn token một cách đột ngột

Trong migration, giảm `exp` của token mới có thể giúp rút ngắn cửa sổ chuyển tiếp, nhưng không thay đổi token đã phát hành. Nếu cần thu hồi v1 sớm hơn thời hạn tự nhiên, cần cơ chế denylist, introspection, session version hoặc policy chặn version cũ sau thời điểm hiệu lực; phải đánh giá tác động đến người dùng và mọi consumer.

## 10. Xử lý token thiếu version và version không được hỗ trợ

Token thiếu version có thể là token cũ trước khi hệ thống bổ sung version claim, hoặc token không tuân thủ profile. Cách xử lý phải được quy định rõ cho từng issuer/profile.

Các lựa chọn có thể gồm:

- **Legacy profile explicit:** chỉ một issuer/profile được cấu hình cho phép token không có version được xem là v1 trong một khoảng thời gian có giới hạn.
- **Reject missing version:** áp dụng khi version claim là bắt buộc ngay từ đầu.
- **Sunset legacy support:** sau thời điểm cutover, token thiếu version bị từ chối.

Không dùng quy tắc chung “thiếu version thì coi là phiên bản mới nhất”. Cách đó có thể diễn giải token cũ theo schema mới và tạo sai quyền.

### Unknown version

Nếu version là `3` nhưng consumer chỉ hỗ trợ v1/v2:

- Từ chối theo reason code như `UNSUPPORTED_CLAIMS_VERSION`.
- Ghi nhận issuer alias, audience, token profile và version đã được xác minh ở dạng an toàn.
- Không bỏ qua validator rồi tiếp tục dùng claims theo phỏng đoán.
- Cảnh báo nếu unknown version xuất hiện trước rollout đã lên lịch.

Nếu version claim sai kiểu, âm, số thực không hợp lệ hoặc vượt giới hạn parser, từ chối theo schema validation. Không tự ép kiểu string sang integer nếu hợp đồng không cho phép.

## 11. Thay đổi ngữ nghĩa quyền cần thận trọng hơn đổi tên field

Thay đổi claim về authorization có thể làm tăng hoặc giảm quyền của principal mà không thay đổi chữ ký hoặc token lifetime.

Ví dụ v1:

~~~json
{
  "roles": ["operator"]
}
~~~

V1 có thể định nghĩa role `operator` chỉ được cập nhật đơn hàng thuộc tenant hiện tại. Nếu v2 chuyển thành:

~~~json
{
  "permissions": ["orders:update"]
}
~~~

consumer phải tiếp tục áp dụng ràng buộc tenant và ownership. Permission `orders:update` không tự chứng minh chủ thể có quyền cập nhật mọi đơn hàng.

Khi migrate role sang permission:

1. Liệt kê semantics và phạm vi của từng role cũ.
2. Xác định permission mới tương đương và các điều kiện tài nguyên.
3. Kiểm thử các trường hợp positive và negative.
4. So sánh authorization decision v1/v2 trên cùng bộ dữ liệu.
5. Theo dõi chênh lệch quyết định khi canary.
6. Chỉ chuyển issuer sau khi mapping được phê duyệt.
7. Không mặc định cấp quyền nếu mapping thiếu hoặc không rõ.

Một migration schema có thể parse thành công nhưng vẫn sai về bảo mật nếu quyền được ánh xạ rộng hơn.

## 12. Tương thích nhiều issuer và nhiều consumer

Trong môi trường liên tổ chức, issuer và consumer có thể nâng cấp độc lập. Cần có ma trận hỗ trợ thay vì giả định tất cả thành phần đồng bộ.

Ví dụ:

| Thành phần | v1 | v2 | Vai trò trong chuyển tiếp |
| --- | --- | --- | --- |
| Issuer A hiện tại | Phát hành | Chưa phát hành | Tiếp tục v1 trước cutover |
| Issuer A sau nâng cấp | Có thể ngừng | Phát hành | Migrate theo rollout |
| Consumer cũ | Đọc | Không đọc | Phải loại khỏi routing trước khi phát v2 |
| Consumer mới trong giai đoạn mở rộng | Đọc | Đọc | Hỗ trợ cả hai version |
| Consumer sau contract | Không đọc | Đọc | Chỉ hoạt động với v2 |
| Partner consumer | Theo hợp đồng | Theo hợp đồng | Cần xác nhận readiness và thời hạn riêng |

Nếu có nhiều issuer, cùng `claims_version` = 2 không bảo đảm schema giống nhau. Version phải được gắn với issuer/profile hoặc schema identifier đã định nghĩa. Hai issuer có thể cùng dùng claim `tenant_id` nhưng khác format hoặc semantics; không được gom chúng thành một schema chỉ vì tên field giống nhau.

### Consumer hỗ trợ version có giới hạn

Mỗi consumer nên công bố rõ tập version được hỗ trợ. Issuer chỉ phát hành version mà toàn bộ consumer cần nhận token có thể xử lý. Nếu một audience được nhiều service dùng chung, phải xác định consumer nào thực sự là bên nhận và version readiness của tất cả thành phần trong chuỗi.

Không dùng một token audience quá rộng chỉ để tránh phải quản lý ma trận tương thích.

## 13. Rollback khi migration schema gặp lỗi

Rollback cần được thiết kế trước khi chuyển issuer. Một khi token v2 đã phát hành, token đó có thể còn hiệu lực trong toàn bộ lifetime đã cấp.

Các nguyên tắc:

- Consumer hỗ trợ v1/v2 nên tiếp tục hỗ trợ v2 trong khi rollback issuer về v1.
- Không rollback consumer thành v1-only nếu token v2 vẫn có thể xuất hiện.
- Nếu v2 có lỗi ngữ nghĩa, có thể chặn v2 theo policy khẩn cấp, nhưng phải chấp nhận tác động từ chối các token v2 còn hiệu lực.
- Nếu rollback issuer, xác nhận tất cả instance/region ngừng phát hành v2 theo cùng policy.
- Không tái sử dụng version number v2 cho một schema khác sau khi đã phát hành.
- Ghi nhận token v2 đã phát hành và xác định thời điểm chúng hết hạn hoặc bị thu hồi.

Nếu v2 đã được phát hành cho client nhưng consumer gặp lỗi, rollback an toàn thường là khôi phục consumer tương thích v1/v2 hoặc sửa adapter. Không thể giả định đổi issuer về v1 sẽ khiến các token v2 đã tồn tại biến mất.

## 14. Tách schema version khỏi key rotation và token revocation

Ba hoạt động này có thể xảy ra gần nhau nhưng cần được quản lý độc lập:

- **Schema migration:** thay đổi cấu trúc/semantics claims.
- **Key rotation:** thay đổi khóa ký hoặc khóa mã hóa, thường thể hiện qua `kid` và JWKS.
- **Token revocation:** thay đổi trạng thái chấp nhận của token/session/family.

Ví dụ, issuer có thể phát hành schema v2 nhưng vẫn dùng signing key hiện tại. Sau đó issuer xoay khóa mà vẫn phát hành schema v2. Hai rollout cần telemetry và rollback riêng.

Không dùng `kid` để xác định schema version, không coi schema v2 là bằng chứng token được ký bằng khóa mới và không thu hồi toàn bộ token chỉ vì version schema tăng nếu policy không yêu cầu.

Nếu schema v1 có lỗ hổng authorization nghiêm trọng, có thể cần từ chối v1 sớm. Khi đó đây là một policy deprecation/revocation có tác động bảo mật, cần thông báo, xác nhận phạm vi và cơ chế kiểm tra ở mọi Resource Server.

## 15. Kiểm thử tương thích và khoảng chuyển tiếp

Cần kiểm thử cả cấu trúc, semantics và hành vi triển khai. Bộ test nên dùng token test được ký bằng khóa kiểm thử, không dùng production credential.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token v1 hợp lệ tới consumer hỗ trợ v1/v2 | Được xác minh và map đúng canonical principal |
| Token v2 hợp lệ tới consumer hỗ trợ v1/v2 | Được xác minh và map đúng canonical principal |
| Token v2 tới consumer chỉ hỗ trợ v1 | Bị từ chối rõ ràng, không fallback sang v1 |
| Token thiếu version trong legacy window | Chỉ được xử lý theo legacy profile đã cấu hình |
| Token thiếu version sau sunset | Bị từ chối |
| Token có version không hỗ trợ | `UNSUPPORTED_CLAIMS_VERSION` |
| Version sai kiểu hoặc giá trị ngoài miền | Schema validation từ chối |
| Version v2 nhưng chỉ chứa claims v1 | Bị từ chối do không tuân thủ v2 |
| Dual-write với hai claim bằng nhau | Consumer áp dụng precedence đã định nghĩa |
| Dual-write với hai claim mâu thuẫn | Từ chối hoặc cảnh báo theo policy; không tùy tiện chọn |
| Claim mới tùy chọn chưa biết | Xử lý theo unknown-claim policy |
| Claim bắt buộc bị thiếu | Từ chối |
| Permission mapping v1/v2 | Authorization decisions tương đương theo policy đã duyệt |
| Token v1 còn hạn sau issuer cutover | Consumer mới vẫn xử lý trong transition window |
| Refresh token cũ sau cutover | Issuer phát hành version mới hoặc yêu cầu re-auth theo policy |
| Một region còn phát hành v1 | Alert và rollout gate phát hiện |
| Rollback issuer sau khi đã phát hành v2 | Consumer vẫn xử lý token v2 đang còn hiệu lực |
| Schema version và `kid` thay đổi độc lập | Validator chọn đúng schema và đúng key theo từng policy |
| Token có issuer hợp lệ nhưng profile/version không khớp | Từ chối theo profile, không tự chọn schema khác |

### Kiểm thử authorization, không chỉ JSON parsing

Với mỗi version, kiểm tra:

- Subject và tenant được map đúng.
- Permission không tăng ngoài ý muốn.
- Claim thiếu không tạo quyền mặc định.
- Claim null, empty array, false và zero có semantics rõ.
- Resource ownership và tenant boundary vẫn được kiểm tra.
- Token version cũ không được dùng trên audience khác.
- Unknown version không thể bypass validator.
- Consumer không sử dụng claims trước khi chữ ký được xác minh.

## 16. Theo dõi migration bằng metrics và rollout gates

Để biết khi nào có thể kết thúc transition window, cần quan sát theo issuer, profile, audience, version, service và region.

Các metric gợi ý:

~~~text
jwt_claims_version_total{
    issuer_alias,
    token_profile,
    audience_alias,
    claims_version,
    consumer,
    region
}

jwt_claims_version_rejected_total{
    reason_code,
    issuer_alias,
    consumer,
    region
}

jwt_legacy_claim_seen_total{
    issuer_alias,
    consumer,
    region
}

jwt_issuer_version_issued_total{
    issuer_alias,
    claims_version,
    audience_alias,
    region
}
~~~

Không dùng raw subject, token hoặc issuer URL tùy ý làm label. Các dimension cần lấy từ cấu hình đã kiểm soát để tránh cardinality explosion.

### Rollout gates trước mỗi bước

Trước khi issuer phát hành v2:

- Tất cả consumer cần nhận token đã hỗ trợ v2.
- Test vectors v1/v2 đều pass.
- Metrics và alert cho unknown version đã hoạt động.
- Có rollback plan và người chịu trách nhiệm.
- Các region đã có verifier/adapter version tương thích.

Trước khi bỏ v1:

- Không còn issuer phát hành v1.
- Không còn refresh/token exchange/job tạo v1.
- Token v1 cuối cùng đã hết hạn cộng clock skew và các khoảng dự phòng đã định nghĩa.
- Consumer metrics không còn v1 trong thời gian quan sát phù hợp.
- Partner và consumer ngoài hệ thống đã xác nhận hoàn tất.
- Không còn rollback path cần v1-only consumer.

Không chỉ dựa vào một khoảng thời gian cố định kể từ ngày deploy; cần bằng chứng từ trạng thái phát hành và quan sát sử dụng.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đổi tên claim ngay trên issuer | Consumer cũ không đọc được token mới | Expand consumer trước, sau đó migrate issuer |
| Không có schema version | Consumer phải đoán cấu trúc từ field tồn tại | Version rõ theo issuer/profile |
| Thiếu version thì mặc định là mới nhất | Token cũ có thể bị diễn giải sai | Legacy profile có thời hạn hoặc reject |
| Dùng `kid` làm schema version | Key rotation làm sai validator | Quản lý key version và claims version độc lập |
| Chỉ kiểm thử JSON parsing | Permission semantics có thể thay đổi ngoài ý muốn | Test canonical mapping và authorization decision |
| Dual-write claim mâu thuẫn | Consumer khác nhau chọn giá trị khác nhau | Quy định precedence và từ chối conflict |
| Consumer fallback khi version không hỗ trợ | Token sai schema có thể được chấp nhận | Reject unsupported version |
| Không tính token lifetime vào transition window | Consumer ngừng hỗ trợ khi token cũ còn hiệu lực | Tính từ lần phát hành v1 cuối cùng và `exp` tối đa |
| Quên refresh flow vẫn phát hành schema cũ | V1 tiếp tục xuất hiện sau cutover | Kiểm tra refresh, exchange và mọi issuer instance |
| Cùng version number nhưng issuer khác semantics | Consumer dùng nhầm validator | Scope version theo issuer/profile/schema ID |
| Rollback consumer về v1-only | Token v2 còn hiệu lực bị từ chối | Duy trì multi-version support trong rollback window |
| Không kiểm tra unknown claims policy | Consumer có thể reject hoặc ignore không nhất quán | Định nghĩa optional/critical claims rõ |
| Gộp schema migration với key rotation | Khó xác định nguyên nhân và rollback | Tách rollout, metrics và runbook |

## 18. Checklist triển khai thay đổi schema claims

**Hợp đồng schema**

- Xác định issuer, token profile, audience và schema version.
- Tài liệu hóa claim name, JSON type, required/optional, semantics và constraints.
- Quy định rõ absent, null, empty, false và zero.
- Xác định unknown-claim policy.
- Tăng major version cho thay đổi cấu trúc hoặc semantics không tương thích.
- Không tái sử dụng version number cho schema khác.

**Consumer và issuer**

- Triển khai consumer hỗ trợ version cũ và mới trước khi issuer chuyển đổi.
- Map từng schema sang canonical principal có kiểu.
- Kiểm thử authorization semantics và tenant/resource boundary.
- Dùng dual-read/dual-write chỉ khi precedence và equality rules rõ ràng.
- Không fallback sang schema khác khi version đã khai báo không khớp.
- Chuyển issuer theo canary/region với metrics và rollout gate.

**Khoảng chuyển tiếp và rollback**

- Ghi nhận thời điểm cuối cùng phát hành schema cũ.
- Tính maximum token lifetime, clock skew, propagation và consumer rollout allowance.
- Kiểm tra refresh token, token exchange, job và mọi issuer region.
- Chỉ bỏ validator cũ sau khi token cũ hết hiệu lực và không còn consumer cần nó.
- Duy trì khả năng đọc version mới trong rollback window.
- Không nhầm schema migration với key rotation hoặc token revocation.

**Quan sát và kiểm thử**

- Theo dõi issued/observed/rejected token count theo version.
- Cảnh báo unknown/missing version và issuer phát hành sai version.
- Kiểm thử token v1/v2, dual-write conflict, unknown version, expired token và multi-region.
- Kiểm tra cả principal mapping lẫn quyết định authorization.
- Dùng test keys/test tokens, không đưa production token vào fixture.
- Ghi lại kết quả rollout và xác nhận readiness của mọi consumer liên quan.

**Ghi nhớ:** Claims là hợp đồng dữ liệu có ngữ nghĩa bảo mật. Khi thay đổi tên, kiểu hoặc ý nghĩa claim, hãy version schema theo issuer và token profile, triển khai consumer hỗ trợ nhiều phiên bản trước khi đổi issuer, rồi duy trì một transition window được tính từ lần phát hành schema cũ cuối cùng và thời hạn token tối đa. Version claim chỉ chọn validator sau khi token đã được xác minh; nó không thay thế chữ ký, issuer, audience hoặc authorization. Chỉ loại schema cũ khi token cũ đã hết hiệu lực, mọi luồng phát hành đã chuyển đổi và mọi consumer cần thiết đã sẵn sàng.

### Tài liệu chuẩn để tra cứu

- **RFC 7519 — JSON Web Token (JWT):** registered claims, private claim names và cách biểu diễn claims trong JWT.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh issuer, audience, thuật toán và phân biệt token profile.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** các claim và yêu cầu validation của JWT access token.
- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc và xác minh JWS; schema claims là hợp đồng ở tầng payload.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ access/refresh token và các cân nhắc khi chuyển đổi OAuth.
