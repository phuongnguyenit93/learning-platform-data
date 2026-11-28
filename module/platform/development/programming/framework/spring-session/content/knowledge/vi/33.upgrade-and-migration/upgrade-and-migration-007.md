# Thay đổi định dạng khóa, namespace, tên cookie và kế hoạch chuyển tiếp

Spring Session cho phép nhiều instance dùng chung trạng thái phiên trong Redis, JDBC hoặc một kho lưu trữ tùy chỉnh. Khi nâng cấp ứng dụng, nhóm phát triển có thể cần đổi Redis namespace, định dạng key, tên bảng JDBC hoặc tên cookie. Những thay đổi này tác động tới các lớp khác nhau của đường đi session ID và dữ liệu phiên. Nếu gộp chúng thành một thay đổi duy nhất, ứng dụng có thể mất khả năng tìm session cũ, tạo phiên mới ngoài ý muốn, hoặc khiến các node đang chạy song song không hiểu dữ liệu của nhau.

Cần phân biệt rõ ba định danh:

- **Session ID:** giá trị định danh phiên mà client gửi lại trong cookie hoặc header.
- **Repository key/namespace:** cách Spring Session ánh xạ session ID thành key, hash hoặc row trong kho dữ liệu.
- **Cookie name:** tên cookie mà browser dùng để gửi session ID về server.

Đổi cookie name không tự chuyển dữ liệu trong Redis/JDBC. Đổi namespace không tự đổi cookie mà browser gửi. Đổi định dạng key có thể ảnh hưởng tới cách repository tìm metadata, attributes, index và TTL. Một kế hoạch migration an toàn phải giữ tương thích trong thời gian các phiên bản cùng chạy, bảo toàn thời hạn session, có cách xác minh dữ liệu và xác định trước điều kiện rollback.

Bài này trình bày cách lập kế hoạch chuyển đổi cho Spring Session Servlet và Reactive, tập trung vào Redis/JDBC, cookie resolver, dual-read, dual-write có kiểm soát, lazy migration, cutover, cleanup và rollback.

## 1. Phân tách các lớp cần di chuyển

Một session có thể đi qua nhiều lớp:

~~~mermaid
flowchart LR
    B[Browser] --> C[Cookie name]
    C --> I[Session ID]
    I --> R[SessionRepository]
    R --> N[Namespace / key format]
    N --> S[(Redis or JDBC)]
    S --> D[Session metadata and attributes]
~~~

Mỗi thay đổi có phạm vi riêng:

| Thành phần | Ví dụ thay đổi | Ảnh hưởng trực tiếp |
|---|---|---|
| Cookie name | SESSION thành APPSESSION | Browser gửi session ID dưới tên mới |
| Cookie scope | Domain/Path/SameSite | Browser có gửi cookie tới host/path/request hay không |
| Session ID format | Định dạng ID do ứng dụng tùy chỉnh | Resolver và repository phải hiểu cùng giá trị |
| Redis namespace | spring:session thành app:session:v2 | Prefix của key repository |
| Redis key layout | Tổ chức metadata/attributes/index khác | Repository serialization và lookup |
| JDBC table/schema | SPRING_SESSION thành APP_SESSION_V2 | SQL repository đọc/ghi bảng khác |
| Attribute serialization | Java serialization sang JSON | Cách đọc payload đã lưu |
| TTL policy | Thay max inactive interval | Thời gian session được giữ |

Trước khi thay đổi, hãy ghi lại trạng thái hiện tại của từng lớp. Không suy ra tên Redis key hoặc tên cookie chỉ từ tên module hay tên ứng dụng; kiểm tra cấu hình thực tế của deployment đang chạy và tài liệu đúng phiên bản Spring Session.

## 2. Cookie name và repository namespace là hai hợp đồng khác nhau

Giả sử browser đang giữ cookie:

~~~http
Cookie: SESSION=abc...
~~~

Resolver đọc giá trị abc... rồi truyền ID cho repository. Repository có thể tìm dữ liệu trong Redis theo namespace hiện tại hoặc truy vấn JDBC table tương ứng.

Nếu chỉ đổi cookie name thành APPSESSION nhưng repository vẫn giữ nguyên namespace và key layout, dữ liệu session có thể vẫn được tìm thấy miễn là resolver nhận được cùng ID. Browser không tự đổi cookie name chỉ vì server được cấu hình mới; server phải phát Set-Cookie cho tên mới và có giai đoạn đọc cookie cũ nếu cần giữ phiên.

Ngược lại, nếu đổi Redis namespace nhưng giữ cookie name SESSION, browser vẫn gửi cookie như trước nhưng repository mới có thể tìm không thấy ID trong namespace mới. Khi đó, người dùng có thể bị xem là chưa có session dù dữ liệu cũ vẫn còn trong Redis.

Bảng quyết định:

| Thay đổi | Có cần chuyển dữ liệu repository? | Có cần thay đổi resolver/cookie? |
|---|---|---|
| Chỉ đổi cookie name, giữ ID và repository | Không | Có |
| Chỉ đổi Redis namespace | Có, hoặc có adapter đọc namespace cũ | Không nhất thiết |
| Chỉ đổi JDBC tableName | Có, hoặc có adapter đọc bảng cũ | Không nhất thiết |
| Đổi session ID format | Thường cần migration/bridge | Có thể cần |
| Đổi serializer | Cần reader tương thích hoặc chuyển payload | Không nhất thiết |
| Đổi cookie scope | Không nhất thiết | Có, và cần kiểm tra browser |

Không thực hiện đồng thời tất cả các thay đổi nếu chưa có kế hoạch tương thích. Chia migration thành các bước độc lập giúp biết chính xác lớp nào gây lỗi.

## 3. Kiểm kê cấu hình hiện tại trước migration

Tạo một bản ghi cấu hình được duyệt cho release đang chạy. Ít nhất cần có:

- Spring Boot và Spring Session version.
- Loại repository: Redis, JDBC hay custom.
- Redis namespace, database/cluster và serializer.
- Cấu trúc key/table đang dùng theo implementation thực tế.
- JDBC tableName, schema, index và migration version.
- Cookie name, Path, Domain, Secure, HttpOnly, SameSite.
- Session ID resolver: cookie hay header.
- Max inactive interval và mọi absolute timeout riêng.
- SaveMode/FlushMode nếu repository hỗ trợ.
- Cơ chế expiration event, cleanup và index.
- Số phiên bản ứng dụng có thể cùng chạy trong rollout.
- Thời gian tối đa session có thể tồn tại.
- Phiên bản rollback cần tiếp tục đọc được dữ liệu nào.

Không đọc trực tiếp hoặc thay đổi Redis key nội bộ bằng giả định về layout. Redis repository có thể dùng nhiều key cho session, attributes, expiration và index. Cấu trúc cụ thể phụ thuộc phiên bản và implementation.

## 4. Phân biệt đổi namespace với đổi key format

Namespace thường là prefix giúp cô lập dữ liệu của một ứng dụng hoặc một nhóm session. Ví dụ:

~~~java
@EnableRedisHttpSession(
    redisNamespace = "spring:session:portal"
)
class SessionRedisConfiguration {
}
~~~

Release mới có thể muốn dùng:

~~~java
@EnableRedisHttpSession(
    redisNamespace = "app:session:portal:v2"
)
class SessionRedisConfiguration {
}
~~~

Đổi namespace có thể làm repository mới tìm kiếm ở một tập key khác. Dữ liệu namespace cũ không tự biến mất và cũng không tự xuất hiện trong namespace mới.

Định dạng key là cách repository tổ chức key con, hash field, expiration marker hoặc index. Đây là chi tiết có thể thay đổi giữa implementation hoặc phiên bản. Không tự tạo một migration script giả định chỉ cần đổi prefix cho mọi key; cần hiểu toàn bộ cấu trúc liên quan và semantics expiration.

Một namespace mới có thể giúp cô lập release hoặc môi trường, nhưng không tự bảo đảm payload tương thích. Nếu hai namespace chứa cùng session ID nhưng serializer khác nhau, repository vẫn có thể đọc lỗi.

## 5. Đổi tên cookie mà giữ nguyên session ID

Đây thường là migration ít rủi ro hơn đổi repository layout, nhưng cần xử lý browser đang giữ cookie cũ.

Giả sử:

- Cookie cũ: SESSION.
- Cookie mới: APPSESSION.
- Session ID không đổi.
- Repository và serializer payload không đổi.

Một resolver chuyển tiếp cần có hành vi:

1. Nếu request có APPSESSION, ưu tiên ID từ cookie mới.
2. Nếu không có APPSESSION nhưng có SESSION, đọc ID cũ.
3. Khi phát hành cookie, ghi APPSESSION.
4. Chỉ xóa cookie SESSION khi không còn node cũ cần nó và khi browser scope khớp.
5. Không tạo hai session khác nhau cho cùng browser chỉ vì có hai cookie.

Pseudo-logic:

~~~text
resolveSessionId(request):
    if APPSESSION exists:
        return APPSESSION
    if SESSION exists:
        return SESSION
    return no session id

setSessionId(response, id):
    write APPSESSION=id

expireOldCookie(response):
    write SESSION with Max-Age=0 and matching Path/Domain
~~~

Spring Session có CookieHttpSessionIdResolver và CookieSerializer để xử lý cookie. Cấu hình serializer chuẩn thường có một cookie name. Nếu cần đọc đồng thời hai tên cookie, cần một resolver chuyển tiếp được thiết kế theo API phiên bản đang dùng hoặc một adapter ở lớp HTTP. Không chỉ phát thêm cookie bằng controller rồi cho rằng resolver sẽ đọc được cả hai.

Nếu triển khai custom HttpSessionIdResolver, kiểm thử các trường hợp request chứa cả cookie cũ và mới, cookie rỗng, cookie trùng tên theo nhiều Path và response logout. Khi cả hai cookie cùng tồn tại, ưu tiên cookie mới theo một quy tắc cố định; không chọn ngẫu nhiên theo thứ tự header.

## 6. Đừng xóa cookie cũ khi node cũ vẫn cần đọc nó

Trong rolling deployment, V1 có thể chỉ đọc SESSION còn V2 bridge đọc cả SESSION và APPSESSION. Nếu V2 phát APPSESSION rồi xóa SESSION ngay, request kế tiếp có thể được load balancer gửi tới V1. V1 không nhận ID và tạo session mới.

Vì vậy, chia cookie migration thành hai giai đoạn:

- **Bridge stage:** V2 đọc cookie mới và cũ, nhưng trong thời gian V1 còn chạy vẫn giữ cookie cũ ở browser. V2 có thể phát cookie mới, song không xóa cookie cũ nếu V1 cần nó.
- **Cutover stage:** sau khi mọi V1 đã được drain và không còn rollback về V1, bắt đầu hết hạn cookie cũ. Giữ reader cũ trong khoảng thời gian được xác định nếu session cũ hoặc client cũ còn có thể xuất hiện.

Nếu rollback về V1 vẫn là mục tiêu, V2 phải tiếp tục bảo đảm V1 nhận được cookie mà nó hiểu. Có thể giữ cookie cũ song song trong thời gian rollback window, hoặc rollback về một bridge release có thể đọc cả hai.

Khi xóa cookie, tên, Path và Domain phải khớp cookie cũ. Cookie host-only phải được hết hạn dưới đúng host, không thêm Domain ngoài ý muốn. Cookie prefix __Host- yêu cầu Secure, Path=/ và không có Domain; không thay đổi các điều kiện đó khi phát header hết hạn.

## 7. Đổi Redis namespace: lựa chọn migration

Có bốn chiến lược thường gặp:

| Chiến lược | Cách làm | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| Freeze and copy | Dừng ghi, copy dữ liệu, chuyển traffic | Dễ reasoning về nhất quán | Có downtime hoặc write pause |
| Dual-read | Đọc namespace mới trước, fallback namespace cũ | Chuyển dần theo traffic | Cần xử lý migrate-on-read và race |
| Dual-write | Ghi cả namespace cũ và mới | Hai kho có dữ liệu song song | Ghi một nơi thành công, nơi kia thất bại |
| Lazy migration | Khi đọc thấy dữ liệu cũ thì ghi sang mới | Không cần copy toàn bộ ngay | Session ít hoạt động có thể còn ở namespace cũ lâu |

Chọn chiến lược theo quy mô session, yêu cầu availability, khả năng downtime và cửa sổ rollback. Đừng chọn dual-write chỉ vì nghe có vẻ an toàn; nếu không có transaction phân tán, hai lần ghi không atomic.

## 8. Dual-read với fallback namespace cũ

Một repository bridge có thể tìm ở namespace mới trước, sau đó fallback sang namespace cũ:

~~~text
findById(id):
    current = newRepository.findById(id)
    if current exists:
        return current

    legacy = oldRepository.findById(id)
    if legacy absent:
        return not found

    migrate legacy session to newRepository
    verify newRepository can read migrated session
    delete legacy copy only after safe handoff
    return current-format session
~~~

Đây là pseudocode. Việc migrate phải giữ:

- Session ID, trừ khi có kế hoạch rotation riêng.
- Creation time.
- Last accessed time.
- Max inactive interval.
- Tất cả attributes cần thiết.
- SecurityContext và principal theo serializer tương thích.
- Expiration semantics và TTL còn lại.

Không copy một session đã hết hạn. Nếu oldRepository.findById đã áp dụng logical expiry, chỉ session hợp lệ mới được chuyển. Sau khi ghi namespace mới, kiểm tra bản ghi mới đọc lại được trước khi xóa bản cũ nếu yêu cầu bảo toàn phiên cao.

### Race khi hai request cùng migrate

Hai request có thể cùng đọc một session cũ và cùng ghi sang namespace mới. Cần đảm bảo migration idempotent và không để một snapshot cũ ghi đè cập nhật mới hơn.

Có thể dùng:

- Lock có TTL theo session ID, nếu thực sự cần và có fencing token.
- Version/CAS ở storage.
- Atomic script/transaction trong phạm vi một kho.
- Ghi có điều kiện khi namespace mới chưa có session.
- Re-read và merge theo chính sách được định nghĩa.

Lock phân tán không có fencing có thể hết hạn trong lúc worker cũ vẫn chạy. Đừng dựa vào lock đơn giản như bằng chứng tuyệt đối không có writer cũ.

## 9. Lazy migration và session không hoạt động

Lazy migration chuyển session khi có request đọc. Nó giảm công việc copy dữ liệu và tránh di chuyển session đã hết hạn. Tuy nhiên, session không được truy cập có thể còn nằm ở namespace cũ cho tới khi hết TTL.

Quy trình:

1. Đọc namespace mới.
2. Nếu không có, đọc namespace cũ.
3. Nếu session cũ hợp lệ, tạo snapshot độc lập.
4. Ghi snapshot vào namespace mới với TTL còn lại.
5. Xác nhận ghi thành công.
6. Chỉ sau đó xóa bản cũ theo chiến lược nhất quán.
7. Đánh dấu metric migration outcome mà không ghi session ID.

Không refresh TTL thành một khoảng đầy đủ mới nếu migration không đại diện cho hoạt động người dùng. Nếu session còn 5 phút, việc chuyển kho không nên tự động biến nó thành 30 phút trừ khi policy yêu cầu và hành vi được phê duyệt.

Với session có absolute timeout riêng, giữ cả mốc tuyệt đối. Nếu chỉ lưu maxInactiveInterval mà không lưu mốc absolute expiration, migration có thể vô tình kéo dài phiên vượt giới hạn bảo mật.

## 10. Dual-write và trạng thái ghi không chắc chắn

Dual-write gửi cùng thay đổi tới hai repository. Một tình huống:

- Ghi namespace cũ thành công.
- Ghi namespace mới timeout.
- Ứng dụng không biết lệnh mới đã commit hay chưa.
- Request retry có thể ghi lại snapshot cũ.

Hoặc chiều ngược lại: namespace mới thành công nhưng namespace cũ lỗi. V1 và V2 sau đó nhìn thấy dữ liệu khác nhau.

Nếu bắt buộc dual-write:

- Chọn một nguồn authoritative.
- Định nghĩa thứ tự ghi.
- Có version cho session snapshot.
- Ghi nhận kết quả từng đích riêng.
- Có retry idempotent và reconciliation.
- Không trả success nếu contract yêu cầu cả hai nơi phải đồng bộ mà một nơi thất bại.
- Có cơ chế xử lý partial failure và trạng thái unknown.
- Không xóa nguồn cũ trước khi xác nhận nguồn mới.

Không thể tạo transaction atomic giữa hai Redis cluster hoặc giữa Redis và JDBC chỉ bằng cách gọi hai save liên tiếp. Nếu cần tính nhất quán mạnh, cân nhắc freeze/copy, adapter một nguồn authoritative hoặc một quy trình migration có write barrier.

## 11. Giữ TTL và expiration khi chuyển dữ liệu Redis

TTL là phần của dữ liệu session. Copy payload mà bỏ TTL có thể tạo session tồn tại vô hạn. Copy với TTL mới đầy đủ có thể kéo dài session ngoài ý muốn.

Khi chuyển Redis key trực tiếp, cần cân nhắc:

- Lấy TTL còn lại, không chỉ max inactive interval ban đầu.
- Phân biệt key không tồn tại, key không có expiration và key đã hết hạn.
- Dùng độ chính xác phù hợp, ví dụ PTTL khi cần milliseconds.
- Không chuyển key đã hết hạn.
- Bảo toàn expiration marker và index phụ trợ theo repository layout.
- Kiểm tra cleanup/event semantics ở namespace mới.
- Tránh race khi TTL giảm trong lúc copy.

Với migration ở tầng Session API, tính TTL còn lại từ metadata có thể dễ kiểm soát hơn, nhưng cần đồng hồ nhất quán và semantics lastAccessedTime chính xác. Với migration raw Redis key, phải hiểu mọi key liên quan mà repository sử dụng ở phiên bản hiện tại.

Không dùng lệnh đổi prefix đơn giản cho toàn bộ key nếu một key có cấu trúc khác hoặc chứa index phụ trợ. Chạy thử trên bản sao dữ liệu và so sánh số key/session trước khi áp dụng production.

## 12. Migration JDBC: tableName, schema và transaction

Với Spring Session JDBC, đổi tableName hoặc schema khiến repository mới truy vấn tập bảng khác. Dữ liệu cũ vẫn tồn tại nhưng không được tìm thấy bởi cấu hình mới.

Một chiến lược expand-contract:

1. Tạo bảng/schema mới tương thích với code bridge.
2. Giữ bảng cũ cho V1 và rollback.
3. Triển khai bridge đọc bảng mới trước, fallback bảng cũ.
4. Chuyển session hợp lệ sang bảng mới trong transaction.
5. Xác minh row metadata và attributes.
6. Sau khi tất cả node đã dùng bảng mới, chuyển writer sang bảng mới.
7. Chỉ xóa bảng cũ sau khi hết session cũ và rollback window.

Schema cụ thể phụ thuộc phiên bản Spring Session JDBC và database vendor. Không tự đoán cột hoặc kiểu dữ liệu; dùng schema được tài liệu hoặc migration script đúng phiên bản cung cấp.

Nếu chuyển một session gồm row metadata và nhiều row attributes, dùng transaction để tránh trạng thái nửa chừng. Giữ nguyên expiration time, creation time, last access và max inactive interval. Index và foreign key phải được tạo trước khi traffic chuyển sang bảng mới.

Dùng tài khoản migration có quyền DDL riêng. Runtime account chỉ cần quyền DML tối thiểu. Không để từng application node tự chạy DDL cạnh tranh khi khởi động.

## 13. Thay đổi định dạng key hoặc serializer

Đổi key layout và đổi serializer là hai việc riêng nhưng thường liên quan.

Ví dụ:
- Key cũ dùng namespace prefix và một kiểu cấu trúc hash.
- Key mới dùng prefix có version hoặc layout khác.
- Attribute payload chuyển từ Java serialization sang JSON.
- Một class principal đổi package hoặc cấu trúc.

Một reader bridge cần xác định format theo cách rõ ràng. Có thể dùng version prefix, metadata field hoặc envelope chứa schema version. Tránh thử deserialize tuần tự bằng nhiều serializer rồi bỏ qua mọi exception; điều đó có thể che dữ liệu hỏng và tạo đường xử lý khó kiểm soát.

Ví dụ envelope JSON:

~~~json
{
  "formatVersion": 2,
  "sessionId": "opaque-id",
  "creationTime": "2026-11-26T09:00:00Z",
  "lastAccessedTime": "2026-11-26T09:12:00Z",
  "maxInactiveSeconds": 1800,
  "attributes": {
    "app.locale": "vi-VN",
    "app.cartId": "cart-42"
  }
}
~~~

Đây là minh họa cấu trúc, không phải định dạng wire chuẩn của Spring Session. Không tự thay payload repository bằng JSON như trên nếu implementation mong đợi một format khác. Hãy dùng serializer/repository adapter được thiết kế rõ ràng.

Với Java serialization, class name, package, hierarchy và serialVersionUID có thể ảnh hưởng khả năng đọc dữ liệu cũ. Hãy giữ fixture từ release trước và kiểm thử bằng artifact mới. Không coi serialVersionUID bằng nhau là bảo đảm mọi thay đổi đều tương thích.

## 14. Chuyển session ID format

Đổi session ID format có thể ảnh hưởng cookie, resolver, repository key và mọi tích hợp lưu ID bên ngoài. Cần phân biệt ID format với key prefix.

Ví dụ:
- ID cũ là chuỗi opaque ngẫu nhiên.
- ID mới thêm version prefix hoặc encode theo định dạng khác.

Không chuyển ID bằng cách thay chuỗi tùy tiện nếu ID cũ có thể đã được phát cho browser. Trong giai đoạn chuyển tiếp, resolver/repository bridge có thể cần nhận diện cả hai định dạng.

Nếu ID được rotate:
- Sinh ID mới bằng nguồn ngẫu nhiên an toàn.
- Chuyển attributes và metadata.
- Thu hồi ID cũ.
- Phát cookie mới.
- Đảm bảo mọi node đều hiểu ID mới.
- Kiểm tra session fixation protection không bị bỏ qua.

Không dùng session ID cũ làm key phụ lâu dài nếu nó đã bị thu hồi. Nếu cần mapping old-to-new trong migration, bảo vệ mapping như credential nhạy cảm, đặt TTL ngắn và không log mapping.

## 15. Kế hoạch chuyển tiếp theo bridge release

Một kế hoạch rolling deployment thường an toàn hơn nếu có một release trung gian chỉ mở rộng khả năng đọc:

~~~mermaid
flowchart TD
    A[V1: read/write old cookie and repository] --> B[V2 bridge: read old/new, write old]
    B --> C[Deploy V2 bridge to every node]
    C --> D[Drain all V1 nodes]
    D --> E[Enable new cookie/repository writer]
    E --> F[Read old and new during migration window]
    F --> G[Expire old cookie and clean old namespace]
    G --> H[V3: remove legacy reader]
~~~

Diễn giải:

- V1 chỉ hiểu hợp đồng cũ.
- V2 bridge hiểu cả cũ và mới nhưng vẫn ghi định dạng cũ khi V1 còn hoạt động.
- Sau khi V1 được drain, bật writer mới bằng feature flag hoặc cấu hình release.
- Reader mới tiếp tục hỗ trợ dữ liệu cũ trong suốt thời gian session cũ còn tồn tại.
- V3 chỉ bỏ reader cũ sau khi hết session cũ và rollback window.

Nếu không thể có bridge release, cần cân nhắc maintenance window, yêu cầu đăng nhập lại có kế hoạch hoặc tách nhóm traffic. Không đưa binary mới ghi dữ liệu không tương thích vào cụm khi node cũ vẫn có thể nhận request.

## 16. Cấu hình theo feature flag và thứ tự cutover

Tách các quyết định thành flag/cấu hình độc lập:

~~~yaml
app:
  session:
    read-legacy-namespace: true
    write-new-namespace: false
    emit-new-cookie: false
    accept-legacy-cookie: true
~~~

Đây là cấu hình minh họa thuộc ứng dụng, không phải property chuẩn Spring Boot. Feature flag nên được quản lý tập trung và có giá trị mặc định an toàn.

Một trình tự cutover:

1. Deploy bridge code với đọc cũ/mới, ghi cũ.
2. Xác nhận tất cả node chạy bridge.
3. Drain node cũ và kiểm tra load balancer không còn route tới chúng.
4. Bật ghi namespace mới.
5. Bật phát cookie mới theo chính sách.
6. Theo dõi lookup miss, migration success, save failure và cookie adoption.
7. Duy trì reader cũ.
8. Sau thời gian session cũ tối đa và rollback window, dọn dữ liệu cũ.
9. Release sau mới loại bỏ code đọc legacy.

Không bật nhiều flag cùng lúc nếu chưa xác định tác động. Bật writer mới trước khi mọi node tương thích là nguyên nhân phổ biến khiến session mất theo node.

## 17. Rollback phải tính cả dữ liệu và cookie

Rollback binary không tự khôi phục Redis/JDBC data hoặc cookie browser đã nhận.

| Trạng thái hiện tại | Rollback về V1 có an toàn? | Điều kiện |
|---|---|---|
| V2 chỉ đọc format mới, chưa ghi | Thường có | V1 vẫn đọc nguồn cũ |
| V2 dual-read, vẫn ghi nguồn cũ | Có thể | Cookie cũ còn được phát và repository cũ được giữ |
| V2 đã ghi namespace mới | Không trực tiếp | V1 cần bridge hoặc dữ liệu phải được chuyển ngược |
| Browser chỉ còn cookie mới | Không | V1 phải đọc cookie mới hoặc cookie cũ được khôi phục |
| JDBC schema đã xóa cột/bảng cũ | Không | Phải khôi phục schema tương thích trước |
| Serializer mới ghi payload cũ không đọc được | Không | Cần reader bridge hoặc chuyển đổi payload |
| Cookie cũ và mới cùng tồn tại | Có thể | V1 vẫn nhận được cookie cũ và ID trỏ tới dữ liệu nó hiểu |

Trước cutover, viết rollback runbook cụ thể:

- Binary rollback target.
- Repository namespace/table mà binary đó đọc.
- Cookie name mà resolver chấp nhận.
- Serializer/format mà binary đó đọc.
- Dữ liệu mới đã được ghi chưa.
- Cách chuyển dữ liệu mới về nguồn cũ nếu cần.
- Điều kiện phải invalidate session và yêu cầu login lại.
- Người chịu trách nhiệm quyết định rollback.

Nếu session mới không tương thích với V1, rollback an toàn có thể là đưa bridge release trở lại, hoặc invalidate các session không thể đọc và yêu cầu xác thực lại. Không giả vờ giữ session khi dữ liệu không thể khôi phục an toàn.

## 18. Bảo toàn thời hạn và chính sách session

Migration không được vô tình kéo dài session. Khi copy một phiên, cần bảo toàn:

- Creation time.
- Last accessed time.
- Max inactive interval.
- Remaining TTL.
- Absolute expiration nếu ứng dụng có.
- SecurityContext và thông tin cần thiết.
- Trạng thái invalidated hoặc expired.

Nếu migration xảy ra khi người dùng đang hoạt động, lastAccessedTime có thể được cập nhật đồng thời. Cần có chính sách xác định snapshot nào thắng và không để migration ghi đè một thay đổi mới hơn.

Không đặt TTL mới bằng maxInactiveInterval đầy đủ nếu session đã sống được một phần thời gian. Tính remaining TTL theo metadata và clock có kiểm soát. Nếu key cũ không có TTL do dữ liệu lỗi hoặc cấu hình cũ, không tự gán TTL vô hạn; xử lý theo chính sách đã được phê duyệt.

## 19. Session attributes và SecurityContext

Không chỉ chuyển metadata. Các attributes có thể bao gồm:
- Locale, theme hoặc lựa chọn giao diện.
- ID giỏ hàng hoặc trạng thái workflow.
- Principal và SecurityContext.
- OAuth2 authorization request hoặc trạng thái đăng nhập tùy tích hợp.
- Dữ liệu do thư viện framework thêm.

Tạo inventory các attribute name và type. Với payload có class riêng, kiểm tra compatibility giữa artifact cũ/mới. Nếu class đã bị xóa hoặc đổi package, có thể cần DTO chuyển đổi hoặc buộc re-authentication.

Không chuyển một SecurityContext lỗi hoặc không xác minh được rồi tiếp tục cấp quyền. Nếu không đọc được principal/authorities một cách tin cậy, invalidate session và yêu cầu đăng nhập lại theo chính sách.

Không lưu entity nghiệp vụ lớn chỉ để tiện migration. Session nên chứa dữ liệu nhỏ, ổn định và có thể chuyển đổi.

## 20. Quan sát migration mà không lộ session ID

Metrics nên dùng dimension có cardinality thấp:

~~~text
spring_session_migration_total{
  source="legacy",
  target="v2",
  outcome="success"
}

spring_session_migration_duration_seconds_bucket{
  source="legacy",
  target="v2",
  outcome="success",
  le="0.5"
}
~~~

Có thể đo:
- Số session đọc từ namespace cũ.
- Số session đọc từ namespace mới.
- Số lần lazy migration thành công/thất bại.
- Số partial dual-write.
- Số lookup miss.
- Số lỗi serialization.
- Số cookie cũ/mới được nhận, nếu đếm mà không log giá trị.
- Remaining TTL distribution.
- Tỷ lệ session bị buộc re-authentication.

Không dùng session ID, user ID, cookie value hoặc raw key làm metric label. Log có thể ghi traceId/requestId, migration phase, source/target, outcome, duration và application version. Nếu cần fingerprint, chỉ dùng HMAC có quản lý khóa, retention ngắn và không đưa vào metric.

## 21. Kiểm thử trước khi cutover

Dùng fixture session từ release cũ. Fixture nên bao gồm:
- Session chỉ có metadata.
- Session có attributes ứng dụng.
- Session có SecurityContext/principal.
- Session gần hết TTL.
- Session đã hết hạn.
- Session có collection/object lồng nhau.
- Session có payload serialization cũ.
- Session có cookie cũ và cookie mới trong request test.

Ma trận kiểm thử:

| Người ghi | Người đọc | Kết quả cần xác nhận |
|---|---|---|
| V1 | V1 | Baseline cũ |
| V1 | V2 bridge | Đọc được session cũ |
| V2 bridge | V1 | V1 đọc được nếu V2 còn ghi format cũ |
| V2 writer | V2 | Đọc lại đúng format mới |
| V2 writer | V1 rollback | Chỉ pass nếu tương thích đã được chứng minh |
| Cookie cũ | V2 resolver | Resolver fallback đúng |
| Cookie mới | V2 resolver | Resolver ưu tiên cookie mới |
| Cookie cũ + mới | V2 resolver | Quy tắc ưu tiên ổn định |
| Logout | Cả hai version | Session bị thu hồi và cookie được xử lý đúng |
| Expired session | V2 migration | Không chuyển session đã hết hạn |

Kiểm thử trên Redis/JDBC thật với namespace/schema production-like. Mock repository không phát hiện mọi vấn đề key layout, TTL hoặc transaction.

## 22. Kiểm thử cookie migration

Nếu đổi cookie name, kiểm tra:
- Browser có thể gửi cookie cũ.
- Resolver bridge đọc được cookie cũ.
- Resolver ưu tiên cookie mới khi cả hai có mặt.
- Response phát cookie mới với Secure, HttpOnly, SameSite, Path và Domain đúng.
- Trong mixed rollout, cookie cũ chưa bị xóa khi node V1 còn cần.
- Khi cutover hoàn tất, response hết hạn cookie cũ đúng scope.
- Cookie cũ sau khi hết hạn không tạo lại session.
- Cookie mới tham chiếu tới session trong repository đúng namespace.

Không log cookie value trong test. Có thể dùng marker giả lập trong test harness và kiểm tra redaction.

## 23. Kiểm thử Redis/JDBC migration

Với Redis:
- Xác nhận key prefix/namespace cũ và mới.
- Kiểm tra toàn bộ key phụ trợ mà repository version sử dụng.
- Bảo toàn TTL và expiration semantics.
- Kiểm tra keyspace notification/listener nếu phụ thuộc event.
- Test race khi hai request cùng migrate.
- Test storage restart và partial copy.
- Kiểm tra old namespace chỉ bị xóa sau khi xác minh.

Với JDBC:
- Migration DDL chạy trước khi code mới cần schema.
- V1 tiếp tục truy cập bảng cũ trong bridge phase.
- Transaction chuyển metadata và attributes không để lại row dở dang.
- Index và constraint mới đã sẵn sàng.
- Runtime credentials có quyền tối thiểu.
- Rollback không yêu cầu xóa bảng mới.
- Cleanup bảng cũ chỉ diễn ra sau khi session cũ hết hạn và rollback window kết thúc.

## 24. Cutover, reconciliation và cleanup

Trong thời gian migration, cần so sánh số liệu nguồn và đích:

- Tổng số session còn hạn ở nguồn cũ.
- Tổng số session được chuyển.
- Số session lỗi serialization.
- Số session đã hết hạn trong lúc copy.
- Số session trùng ID ở cả hai namespace.
- Số session có version mới hơn ở nguồn nào.
- Tổng remaining TTL theo nhóm.
- Số request vẫn fallback về nguồn cũ.

Không chỉ so sánh số lượng key. Một session có thể gồm nhiều key hoặc row; số key không bằng số session. Dùng API/repository hoặc script hiểu cấu trúc dữ liệu đúng phiên bản.

Cleanup theo thứ tự:

1. Ngừng writer legacy.
2. Xác nhận không còn node đọc/ghi legacy ngoài bridge cần thiết.
3. Đợi hết session legacy còn hạn hoặc hoàn tất migration.
4. Xác nhận rollback window đã đóng.
5. Backup hoặc snapshot theo chính sách.
6. Xóa legacy data theo batch có giới hạn.
7. Theo dõi lỗi lookup và session miss sau cleanup.
8. Chỉ release sau mới xóa legacy reader/config.

Không xóa toàn bộ namespace cũ ngay khi metric migration success đạt 100% trong một khoảng ngắn. Session ít hoạt động, client offline hoặc session có absolute timeout dài có thể còn tồn tại.

## 25. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Người dùng bị logout sau đổi cookie name | Browser vẫn gửi cookie cũ, resolver mới chỉ đọc tên mới | Dual-cookie reader trong bridge |
| Session mất sau đổi namespace | Repository mới chỉ tìm prefix mới | Dual-read hoặc copy dữ liệu |
| V1 không thấy session do V2 tạo | V2 writer mới được bật khi V1 còn chạy | Giữ writer cũ trong mixed phase |
| Session tồn tại vô hạn sau copy | TTL bị bỏ khi migration | Bảo toàn remaining TTL |
| Session hết hạn sớm | Copy TTL theo giá trị sai hoặc clock lệch | Tính expiry từ metadata/remaining TTL |
| Logout không xóa cookie cũ | Sai Path/Domain hoặc chỉ xóa tên mới | Hết hạn từng cookie đúng scope |
| Một phần session có attributes thiếu | Copy metadata nhưng bỏ qua rows/keys phụ trợ | Chuyển toàn bộ payload và verify |
| Dual-write tạo dữ liệu lệch | Một đích thành công, đích kia timeout | Authoritative source, version và reconciliation |
| Lazy migration ghi đè update mới | Hai request migrate cùng snapshot cũ | CAS/version/atomic write |
| Rollback không đọc được session | V2 đã ghi format mới hoặc cookie mới | Bridge rollback hoặc re-auth theo kế hoạch |
| Event expiration bị mất | Chưa cấu hình listener/keyspace notifications | Kiểm tra event source và cleanup |
| Cleanup xóa session còn hoạt động | Xóa theo tuổi key thay vì expiration semantics | Xác minh remaining TTL và session state |

## 26. Checklist migration

Trước migration:
- Đã kiểm kê cookie, resolver, namespace, key layout, serializer và schema.
- Đã xác định version Spring Session/Boot đang dùng.
- Đã tạo fixture session cũ và test đọc bằng release mới.
- Đã xác định session lifetime tối đa và rollback window.
- Đã chọn chiến lược freeze/copy, dual-read, dual-write hoặc lazy migration.
- Đã xác định authoritative repository trong từng phase.

Trong rolling deployment:
- Bridge release đọc được cũ và mới.
- Bridge writer giữ tương thích với node cũ.
- Không xóa cookie cũ khi V1 còn cần.
- Không bật writer mới trước khi node cũ được drain.
- TTL, metadata và attributes được bảo toàn.
- Partial failure và unknown write outcome có reconciliation.
- Cookie name, Path, Domain và security flags được kiểm thử.
- Metric/log không chứa session ID hoặc raw key.

Sau cutover:
- Mọi node dùng cấu hình mới.
- Reader cũ tiếp tục hoạt động trong thời gian session legacy còn hạn.
- Lookup miss, serialization error, migration rate và TTL được theo dõi.
- Rollback target đã được xác nhận.
- Legacy data chỉ được xóa sau khi hết session cũ và rollback window.
- Legacy reader/config chỉ được loại bỏ trong release sau.

Thay đổi cookie name, repository namespace và key format là ba migration khác nhau. Cookie name quyết định browser gửi ID dưới tên nào; namespace/key format quyết định repository tìm dữ liệu ở đâu; serializer quyết định payload có đọc được hay không. Hãy tách các thay đổi, triển khai bridge reader trước, giữ writer tương thích trong mixed rollout, bảo toàn remaining TTL và metadata, rồi mới cutover và cleanup. Rollback phải tính cả binary, cookie browser và dữ liệu đã ghi. Chỉ xóa legacy format sau khi session cũ không còn hợp lệ và cửa sổ rollback đã đóng.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — CookieSerializer API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/CookieSerializer.html)
- [Spring Session — HttpSessionIdResolver API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/HttpSessionIdResolver.html)
- [Spring Boot — Database Initialization and Migration](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
- [Redis — EXPIRE and PTTL](https://redis.io/docs/latest/commands/pttl/)

