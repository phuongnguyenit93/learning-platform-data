# Session consistency — Duy trì trạng thái phiên xác thực nhất quán trong hệ thống phân tán

## 1. Session consistency là gì?

**Session consistency** (tính nhất quán của phiên) là khả năng các thành phần trong một hệ thống phân tán cùng đưa ra quyết định tương thích về trạng thái của một phiên xác thực. Khi người dùng đăng nhập, gia hạn token, đăng xuất, đổi mật khẩu hoặc bị thu hồi quyền, mọi node có trách nhiệm xác minh phiên phải nhìn thấy trạng thái phù hợp trong giới hạn thời gian và bảo đảm mà hệ thống đã cam kết.

Ví dụ: người dùng đăng nhập vào ứng dụng ở vùng A. Session được lưu trong kho dùng chung và một số node cache thông tin phiên. Sau đó người dùng nhấn Logout ở vùng B. Nếu vùng A vẫn chấp nhận session từ cache cũ, người dùng tưởng đã đăng xuất nhưng phiên vẫn có thể truy cập dữ liệu. Đây là lỗi nhất quán có tác động trực tiếp tới bảo mật.

Trong chương **Authentication trong distributed system** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, session consistency kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần mô hình hóa ranh giới tin cậy giữa gateway, identity provider, session store, cache và resource server; hiểu độ trễ lan truyền trạng thái; và thiết kế logout, revocation, refresh, failover an toàn.

**Session consistency không chỉ là đồng bộ dữ liệu cho đúng.** Nó quyết định một node có tiếp tục tin một phiên đã hết hạn, bị thu hồi hoặc không còn đạt assurance hay không. Một hệ thống có thể chấp nhận độ trễ nhất quán nhỏ cho dữ liệu hiển thị, nhưng không thể tùy tiện chấp nhận cùng độ trễ cho quyết định bảo mật quan trọng.

## 2. Vì sao phiên xác thực khó nhất quán trong hệ thống phân tán?

Một ứng dụng đơn giản có thể lưu session trong bộ nhớ của một process. Khi mở rộng thành nhiều instance, nhiều vùng hoặc microservices, trạng thái phiên có thể tồn tại ở nhiều nơi:

- Session store trung tâm hoặc database.
- Cache cục bộ của từng application node.
- API gateway hoặc reverse proxy.
- Identity provider và hệ thống federation.
- Resource server hoặc service nội bộ.
- Browser cookie, mobile secure storage hoặc token client.
- Refresh token family và access token đã phát hành.

Các thành phần này có thể nhận cập nhật vào những thời điểm khác nhau. Mạng có thể chậm, message có thể đến trễ hoặc lặp, cache có thể chưa hết TTL, một vùng có thể mất kết nối, và hai request có thể cập nhật cùng session đồng thời.

Ví dụ: session đang active ở hai region. Người dùng đổi mật khẩu tại region A. Region A tăng security version và thu hồi session cũ; region B vẫn đọc replica chưa nhận cập nhật. Nếu region B chấp nhận session cũ, hành động đổi mật khẩu chưa có hiệu lực bảo mật trên toàn hệ thống.

## 3. Những trạng thái nào cần nhất quán?

Không phải mọi dữ liệu liên quan phiên đều có cùng mức quan trọng. Hãy xác định rõ trạng thái authoritative và nơi cần kiểm tra:

| Trạng thái | Tác động nếu bị stale |
| --- | --- |
| Session active/revoked/expired | Node có thể tiếp tục cho phép phiên đã bị thu hồi. |
| Account active/suspended/disabled | Người dùng đã bị đình chỉ vẫn truy cập được. |
| Credential status | Passkey, certificate hoặc API key đã revoke vẫn được chấp nhận. |
| Authentication time và assurance | Thao tác nhạy cảm có thể dựa trên xác thực quá cũ hoặc yếu. |
| Session version/security epoch | Session cũ có thể không bị vô hiệu hóa sau reset password hoặc incident response. |
| Refresh token family status | Refresh token đã bị revoke vẫn cấp access token mới. |
| Role, scope và tenant membership | Quyền đã thu hồi hoặc thay đổi chưa có hiệu lực ở resource server. |
| Pending MFA/challenge state | Challenge đã dùng hoặc hết hạn có thể bị chấp nhận lại. |
| Logout/revocation event | Một node chưa nhận sự kiện nên tiếp tục tin session. |

Một số thuộc tính có thể cache lâu hơn, ví dụ tên hiển thị. Trạng thái revoke, account suspension, token family và quyền trên tài nguyên nhạy cảm thường cần độ mới cao hơn. Chính sách phải nói rõ trường nào được phép stale bao lâu.

## 4. Ranh giới tin cậy và kiến trúc session phân tán

Một kiến trúc điển hình có nhiều thành phần cùng tham gia xác minh:

~~~mermaid
flowchart LR
    U["Browser / Mobile"]
    G["API Gateway"]
    A1["Application node A"]
    A2["Application node B"]
    R1["Resource service"]
    IDP["IdP / Auth service"]
    SS[("Authoritative session store")]
    C1[("Local cache A")]
    C2[("Local cache B")]
    E["Revocation event bus"]
    U --> G
    G --> A1
    G --> A2
    A1 --> SS
    A2 --> SS
    A1 <--> C1
    A2 <--> C2
    IDP --> SS
    SS --> E
    E --> C1
    E --> C2
    A1 --> R1
    A2 --> R1
~~~

Session store hoặc hệ thống quản lý danh tính là nguồn authoritative cho trạng thái phiên. Cache giúp giảm độ trễ nhưng chỉ là bản sao có thời hạn. Event bus giúp lan truyền thay đổi, nhưng message delivery không tự bảo đảm mọi consumer đã xử lý thành công.

Gateway có thể xác minh token hoặc session trước khi chuyển request. Resource service cũng cần hiểu trust boundary: nếu chỉ tin header user do gateway chuyển tiếp, phải xác thực gateway và bảo vệ kênh gateway-to-service; nếu service tự xác minh token, nó cần trust configuration và revocation policy tương ứng.

Không để browser tự khai session active hoặc security version. Cookie chỉ mang session identifier hoặc token; trạng thái và quyền phải được xác minh ở server.

## 5. Session consistency và các mô hình nhất quán dữ liệu

Các hệ thống phân tán có nhiều mô hình nhất quán. Chọn mô hình dựa trên tác động bảo mật, độ trễ và khả năng chịu lỗi:

| Mô hình | Đặc điểm | Cách cân nhắc cho session |
| --- | --- | --- |
| **Strong/linearizable consistency** | Mọi thao tác đọc/ghi quan sát được một thứ tự toàn cục hợp lệ tại một điểm tuyến tính hóa. | Phù hợp cho revoke, consume challenge hoặc cập nhật security version cần hiệu lực tức thời, nhưng có thể tăng latency và phụ thuộc quorum. |
| **Sequential consistency** | Mọi node thấy cùng một thứ tự thao tác, nhưng thứ tự đó không nhất thiết phù hợp với thời gian thực. | Có thể phù hợp một số luồng tuần tự; cần xem liệu yêu cầu bảo mật có đòi hiệu lực ngay theo thời gian thực hay không. |
| **Causal consistency** | Các thao tác có quan hệ nhân quả được quan sát theo đúng thứ tự. | Hữu ích khi logout/revoke và các thao tác phụ thuộc được truyền qua event, nhưng thao tác không có quan hệ nhân quả vẫn có thể khác thứ tự. |
| **Eventual consistency** | Các bản sao sẽ hội tụ nếu không có cập nhật mới và hệ thống phục hồi. | Dùng cho metadata ít nhạy cảm; cần đánh giá cửa sổ mà session cũ vẫn có thể được chấp nhận. |
| **Read-your-writes/session consistency** | Một client nhìn thấy cập nhật do chính nó thực hiện theo semantics hệ thống. | Hữu ích cho trải nghiệm sau logout hoặc thay đổi bảo mật, nhưng không tự bảo đảm các node khác đã thấy cập nhật. |

Không có yêu cầu phải dùng strong consistency cho mọi thuộc tính. Một cách thiết kế phổ biến là dùng nguồn authoritative có consistency cao cho thay đổi bảo mật, còn cache/replica phục vụ đọc với TTL và invalidation có giới hạn. Nếu dùng eventual consistency, phải định lượng và chấp nhận rõ cửa sổ stale.

## 6. Strong consistency, quorum và availability

Một thao tác revoke có thể yêu cầu ghi vào hệ thống có quorum hoặc transaction đảm bảo cập nhật được commit trước khi báo thành công. Khi một vùng mất kết nối, hệ thống có thể phải từ chối thao tác nhạy cảm thay vì ghi trạng thái cục bộ rồi để các vùng khác tiếp tục chấp nhận session cũ.

Theo nguyên tắc CAP, khi có network partition, hệ thống phân tán phải lựa chọn giữa consistency và availability cho thao tác đang bị ảnh hưởng. Điều này không có nghĩa toàn bộ hệ thống phải ngừng hoạt động. Có thể phân loại request:

- Thao tác nhạy cảm cần trạng thái revoke mới nhất: fail closed hoặc yêu cầu xác minh qua nguồn authoritative.
- Thao tác ít nhạy cảm có thể chấp nhận cache trong TTL đã định.
- Request chỉ đọc dữ liệu công khai có thể tiếp tục theo availability policy.
- Login mới có thể bị giới hạn nếu không thể kiểm tra account/credential status.

Không dùng “fail open” chung cho mọi request khi session store lỗi. Cần policy theo resource/action và mức rủi ro.

## 7. Sticky session không giải quyết session consistency

Sticky session hoặc session affinity cố gắng gửi request của một client tới cùng application node. Nó có thể giảm cache miss và giữ state cục bộ, nhưng không giải quyết:

- Người dùng chuyển sang thiết bị hoặc mạng khác.
- Node bị restart hoặc scale down.
- Load balancer định tuyến sang node khác.
- Session bị revoke từ admin console hoặc IdP.
- Nhiều service cùng xác minh một session.
- Failover sang region khác.

Sticky session là tối ưu định tuyến, không phải nguồn sự thật cho trạng thái bảo mật. Nếu dùng local in-memory session, cần có chiến lược replication, failover và invalidation rõ ràng. Thông thường, session store dùng chung hoặc token validation có revocation mechanism sẽ dễ quản lý hơn.

## 8. TTL, cache và cửa sổ stale

Cache session có thể giảm tải session store nhưng tạo ra một khoảng thời gian mà trạng thái cũ vẫn được tin:

1. Session active được cache tại node A.
2. Người dùng logout hoặc admin revoke session ở store.
3. Revocation event chưa đến node A.
4. Node A tiếp tục chấp nhận cache active cho tới khi cache hết hạn hoặc bị invalidated.

Nếu TTL là 5 phút, cửa sổ stale có thể gần 5 phút trong trường hợp event bị mất và không có revalidation khác. TTL không tự bảo đảm propagation nếu cache có thể được làm mới từ replica stale.

### Chọn TTL theo rủi ro

| Loại thao tác | Hướng thiết kế |
| --- | --- |
| Đọc nội dung ít nhạy cảm | Có thể chấp nhận cache ngắn nếu threat model cho phép. |
| Xem dữ liệu cá nhân nhạy cảm | TTL ngắn hơn, kiểm tra account/session state theo policy. |
| Đổi mật khẩu, MFA, recovery hoặc payout | Đọc trạng thái authoritative gần thời điểm commit. |
| Quản trị role/tenant | Revalidate membership và authorization ngay trước hành động. |
| Revoke session/token sau compromise | Cần propagation nhanh, status version hoặc denylist/introspection. |

Không có con số TTL mặc định phù hợp. Hãy định nghĩa mục tiêu như maximum revocation propagation time, đo thực tế và cảnh báo khi vượt SLA.

## 9. Revocation event và cache invalidation

Khi session bị revoke, hệ thống có thể phát một event chứa:

- Session ID hoặc reference đã pseudonymize.
- Principal/account reference.
- Session version hoặc security epoch mới.
- Thời điểm và reason code.
- Event ID và sequence/version để consumer phát hiện trùng hoặc thiếu.

Event không nên chứa cookie, access token, refresh token hoặc secret. Consumer cần idempotent: xử lý cùng một event nhiều lần không làm trạng thái sai.

### Transactional outbox

Nếu ứng dụng ghi session revoked vào database rồi publish message riêng, process có thể crash giữa hai thao tác. Database đã cập nhật nhưng event không được gửi; cache tiếp tục active.

Transactional outbox giải quyết bằng cách ghi trạng thái session và outbox event trong cùng database transaction. Worker đọc outbox và publish có retry. Consumer vẫn cần idempotency và có cơ chế reconciliation khi event bị mất hoặc consumer bị gián đoạn.

~~~mermaid
sequenceDiagram
    participant A as Auth service
    participant DB as Session DB + outbox
    participant W as Outbox worker
    participant B as Event bus
    participant C as Cache consumer
    A->>DB: Transaction: revoke session + insert outbox
    DB-->>A: Commit
    W->>DB: Read unpublished event
    W->>B: Publish revocation event
    B-->>C: Deliver event
    C->>C: Invalidate cache idempotently
    C-->>B: Acknowledge
    W->>DB: Mark published
~~~

Outbox giúp không mất sự kiện giữa database commit và publish, nhưng không làm event bus trở thành strongly consistent. Cần retry, dead-letter handling, consumer lag monitoring và reconciliation.

## 10. Session version và security epoch

Một cách hiệu quả để vô hiệu hóa nhiều session là gắn phiên với một version bảo mật của tài khoản:

- Account có **security epoch** hoặc session version hiện tại.
- Khi tạo session, server ghi version hiện tại vào session.
- Khi reset password, xử lý compromise hoặc revoke toàn bộ phiên, server tăng version.
- Mỗi lần xác minh session, server so sánh version trong session với version authoritative hoặc cache có TTL được kiểm soát.
- Nếu version khác nhau, session cũ bị từ chối.

Ví dụ:

~~~text
Account:
    principal_id: user-204
    security_epoch: 18

Session:
    session_id: opaque-random-id
    principal_id: user-204
    security_epoch: 17
    status: active

Validation:
    session.security_epoch == account.security_epoch
~~~

Trong ví dụ, session mang epoch 17 bị từ chối vì account đã tăng lên 18.

Security epoch giúp revoke nhiều phiên mà không cần cập nhật từng session record. Tuy nhiên, nó chỉ hiệu quả nếu verifier nhận được epoch mới trong giới hạn đã cam kết. Nếu epoch được cache quá lâu, session cũ vẫn có thể được chấp nhận trong cửa sổ stale.

Có thể dùng version riêng theo credential hoặc tenant nếu cần thu hồi có phạm vi nhỏ hơn. Tránh một counter duy nhất làm vô hiệu hóa quá nhiều session ngoài ý muốn.

## 11. Logout trong hệ thống nhiều node

Logout thường bao gồm nhiều hành động:

1. Xóa cookie hoặc token ở client.
2. Đánh dấu server-side session revoked.
3. Thu hồi refresh token family hoặc grant nếu policy yêu cầu.
4. Phát revocation event để invalidation cache.
5. Cập nhật security epoch nếu logout all sessions.
6. Ghi audit và thông báo khi có dấu hiệu compromise.

Xóa cookie ở browser không thu hồi session ở server. Nếu cookie bị sao chép trước đó, attacker vẫn có thể sử dụng cho tới khi server từ chối. Ngược lại, revoke server-side nhưng client vẫn giữ cookie không phải lỗi bảo mật nếu mọi verifier đều kiểm tra trạng thái; tuy nhiên giao diện nên xóa cookie để tránh gửi lại vô ích.

### Logout current session và logout all sessions

Hai thao tác cần semantics khác nhau:

- **Logout current session:** revoke một session ID cụ thể và các token liên quan theo policy.
- **Logout all sessions:** tăng security epoch hoặc revoke toàn bộ session của principal.
- **Logout from one device:** xác định binding/device và session thuộc thiết bị đó; không dựa chỉ vào tên thiết bị do client gửi.

Với SSO, logout ở RP không nhất thiết đăng xuất IdP hoặc các RP khác. Cần xác định front-channel/back-channel logout, token revocation và session federation semantics theo giao thức đang dùng.

## 12. Refresh token rotation và concurrent refresh

Refresh token thường được dùng để cấp access token mới. Với rotation, mỗi lần refresh thành công token cũ bị vô hiệu hóa và token mới được cấp. Điều này giúp phát hiện token reuse, nhưng tạo thách thức khi nhiều request đồng thời.

Ví dụ:

1. Mobile app gửi hai refresh request gần như cùng lúc với token R1.
2. Request A thắng, R1 bị consume và R2 được cấp.
3. Request B đến trễ với R1.
4. Server có thể coi B là reuse và revoke cả token family.
5. Người dùng hợp lệ bị đăng xuất dù chỉ do race trong app.

### Thiết kế cần có

- Token family ID và trạng thái token rõ ràng.
- Consume token cũ và tạo token mới trong transaction nguyên tử.
- Client-side single-flight để tránh refresh song song khi có thể.
- Grace/retry semantics được thiết kế cẩn thận, không mở cửa cho replay.
- Phát hiện reuse theo token family và risk context.
- Thu hồi family khi có bằng chứng token bị sao chép theo policy.
- Đồng bộ kết quả refresh để nhiều app worker không phát hành hai nhánh token không nhất quán.

Không cho phép refresh token cũ được dùng lại vô hạn chỉ để tránh lỗi đồng thời. Nếu có grace window, phải giới hạn theo thời gian, client/session binding và semantics rõ; đồng thời đánh giá khả năng attacker tận dụng nó.

## 13. Access token tự chứa và revocation

JWT access token tự chứa có thể được resource server xác minh chữ ký, issuer, audience, expiry và scope mà không hỏi authorization server ở mỗi request. Cách này giảm latency và tăng availability, nhưng token đã phát hành có thể tiếp tục được chấp nhận tới khi hết hạn nếu resource server không có cơ chế revocation bổ sung.

Các chiến lược:

| Chiến lược | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Short-lived access token | Giới hạn thời gian token cũ còn hiệu lực. | Refresh nhiều hơn; không revoke tức thời. |
| Token introspection | Resource server hỏi trạng thái token tại authorization server. | Thêm network dependency và latency; cần cache có TTL. |
| Denylist/revocation list | Từ chối token cụ thể đã bị revoke. | Cần phân phối trạng thái và quản lý kích thước/retention. |
| Security epoch/version claim | Có thể từ chối token có version cũ. | Cần đọc version mới hoặc cache với giới hạn stale. |
| Sender-constrained token | Giảm khả năng token bị dùng bởi bên không giữ khóa. | Không thay thế revocation; cần proof validation ở resource server. |

Không nói rằng JWT không thể revoke. JWT có thể được kiểm soát bằng expiry ngắn, introspection, denylist hoặc version check; lựa chọn tùy latency, scale và yêu cầu hiệu lực thu hồi.

## 14. Clock skew và thời gian hết hạn

Session và token thường có timestamp như issued-at, not-before, expiry, last-authenticated và idle timeout. Các node có thể lệch đồng hồ:

- Node A nghĩ token chưa hết hạn.
- Node B nghĩ token đã hết hạn.
- Session store và application node tính idle timeout khác nhau.
- Refresh token rotation dùng thời gian khác nhau giữa các region.

Dùng đồng bộ thời gian đáng tin cậy và đặt clock-skew tolerance có giới hạn. Không mở rộng tolerance quá mức để che lỗi đồng hồ. Với thao tác nhạy cảm, dùng timestamp từ nguồn authoritative và semantics rõ; không tin thời gian client tự khai để kéo dài session.

### Absolute timeout và idle timeout

- **Absolute timeout:** giới hạn tổng thời gian sống của session, bất kể hoạt động.
- **Idle timeout:** giới hạn thời gian không có hoạt động hợp lệ.
- **Authentication freshness:** thời điểm người dùng thực sự xác thực gần nhất.

Ba khái niệm khác nhau. Request API liên tục không nhất thiết làm mới authentication freshness; token refresh không có nghĩa người dùng vừa nhập lại passkey. Policy nhạy cảm cần dựa trên authentication time, không chỉ session last-seen.

## 15. Concurrent session updates và lost update

Hai node có thể cùng cập nhật một session:

- Node A gia hạn idle expiry.
- Node B đánh dấu session revoked.
- Nếu A ghi toàn bộ object từ bản đọc cũ sau B, trạng thái revoked có thể bị ghi đè thành active.

Đây là lost update và có thể trở thành lỗ hổng bảo mật.

Biện pháp:

- Dùng compare-and-swap hoặc optimistic concurrency với version.
- Dùng transaction/row lock cho transition nhạy cảm.
- Cập nhật field có điều kiện thay vì ghi đè toàn bộ record cũ.
- Định nghĩa transition hợp lệ; revoked không được chuyển ngược active qua thao tác refresh thông thường.
- Dùng event ordering/version để bỏ qua update cũ đến trễ.

Ví dụ bất biến: một session đã revoked không thể được refresh hoặc gia hạn bằng một request được tạo trước thời điểm revoke. Nếu cần khôi phục, phải tạo session mới sau authentication phù hợp.

## 16. Multi-region, replication và failover

Triển khai đa vùng tăng khả năng chịu lỗi và giảm latency, nhưng session consistency cần thiết kế cụ thể:

| Kiến trúc | Lợi ích | Rủi ro cần quản lý |
| --- | --- | --- |
| Một primary region | Dễ xác định nguồn ghi authoritative. | Region lỗi có thể ảnh hưởng login/logout/refresh; latency từ vùng xa. |
| Synchronous replication/quorum | Có thể giảm nguy cơ đọc trạng thái chưa commit. | Tăng latency và có thể từ chối ghi khi mất quorum. |
| Asynchronous replication | Ghi nhanh và tăng availability. | Replica lag tạo cửa sổ chấp nhận session đã revoke. |
| Active-active | Phục vụ gần người dùng và tăng khả năng phục hồi. | Conflict, ordering, duplicate event và split-brain phức tạp hơn. |
| Regional cache + central authority | Đọc nhanh, kiểm soát trạng thái trung tâm. | Cần invalidation, TTL và fail-closed policy. |

### Failover không được làm sống lại session cũ

Khi failover, replica có thể thiếu các revoke event gần nhất. Nếu hệ thống lập tức phục vụ xác thực từ replica đó, session vừa revoke có thể sống lại. Cần:

- Xác định replication lag tối đa và đo nó.
- Chỉ promote replica đạt consistency point cần thiết cho bảo mật.
- Dùng durable revocation log hoặc security epoch.
- Nếu không thể chứng minh trạng thái đủ mới, tạm từ chối thao tác nhạy cảm hoặc yêu cầu xác thực lại theo policy.
- Sau disaster recovery, xem xét tăng security epoch/rekey hoặc thu hồi session không thể xác minh trạng thái.

Không chỉ kiểm thử node restart trong cùng region; cần diễn tập mất region, partition, delayed replication và khôi phục từ backup.

## 17. Session consistency trong microservices

Trong kiến trúc microservices, gateway có thể xác minh session rồi truyền identity context cho nhiều service. Cần xác định mỗi service tin điều gì:

- Service nhận JWT và tự xác minh signature/issuer/audience/scope.
- Service tin gateway đã xác minh và nhận metadata qua kênh mTLS nội bộ.
- Service gọi introspection hoặc session service để kiểm tra trạng thái mới.
- Service dùng policy engine để kiểm tra quyền theo tenant/resource.

Không để service tin header từ internet có thể giả mạo. Gateway phải loại bỏ header identity do client gửi trước khi gắn header đã xác minh. Kênh nội bộ cần xác thực service-to-service và giới hạn quyền.

### Context đã xác minh không thay thế authorization

Một service có thể biết principal đã xác thực nhưng vẫn phải kiểm tra quyền truy cập resource riêng. Role hoặc membership có thể đã bị thu hồi kể từ lúc session tạo. Với thao tác nhạy cảm, kiểm tra policy hiện tại hoặc version của quyền gần thời điểm commit.

## 18. Session consistency và authentication context

Session thường lưu authentication context như:

- Principal, issuer và subject.
- Authentication time.
- Phương thức đã dùng và assurance class.
- Session creation time, idle expiry và absolute expiry.
- Credential/key reference tạo phiên.
- Tenant/client/audience.
- Security epoch hoặc policy version.

Nếu người dùng hoàn tất step-up ở node A, node B cần nhìn thấy context mới trước khi cho phép hành động yêu cầu assurance cao. Nếu context chỉ được cập nhật trong local cache, người dùng có thể bị từ chối nhầm hoặc một node khác có thể tiếp tục dùng context cũ.

Một cách làm là cập nhật session context trong authoritative store bằng version tăng dần, sau đó phát event invalidation. Resource server kiểm tra version/context theo policy. Không nhận claim step-up do mobile app tự gửi.

## 19. Fail-open, fail-closed và degraded mode

Khi session store hoặc revocation service không sẵn sàng, hệ thống phải có degraded mode được thiết kế trước:

| Tình huống | Phản ứng tham khảo |
| --- | --- |
| Session store không truy cập được | Không tạo session mới nếu không thể kiểm tra account/credential; request đọc ít nhạy cảm có thể dùng cache trong giới hạn policy. |
| Revocation event bus bị gián đoạn | Outbox giữ event; verifier dùng authoritative check hoặc giảm TTL cache. |
| Introspection timeout | Không coi timeout là token active; retry có giới hạn hoặc từ chối request cần trạng thái mới. |
| Cache unavailable | Có thể đọc authoritative store; nếu không được, áp dụng policy theo risk. |
| Region partition | Chỉ tiếp tục thao tác có thể chứng minh trạng thái đủ mới; thao tác nhạy cảm có thể bị từ chối tạm thời. |
| Clock synchronization lỗi | Không tự kéo dài token/session; giới hạn thao tác phụ thuộc thời gian và cảnh báo. |

Fail closed không nhất thiết nghĩa toàn bộ sản phẩm dừng. Có thể cho phép nội dung công khai hoặc thao tác không cần session, trong khi từ chối hành động thay đổi bảo mật. Degraded mode cần được ghi rõ, kiểm thử và thông báo phù hợp.

## 20. Mã giả: xác minh session theo version

Mã giả dưới đây minh họa logic khái niệm:

~~~text
validateSession(sessionId, request):
    session = loadSessionFromTrustedStoreOrBoundedCache(sessionId)
    require session exists
    require session.status == "active"
    require now < session.absoluteExpiry
    require now < session.idleExpiry

    accountState = loadAuthoritativeOrPolicyFreshAccountState(
        session.principalId
    )
    require accountState.status == "active"
    require session.securityEpoch == accountState.securityEpoch
    require session.tenantId == request.tenantId

    if request.requiresFreshRevocationState:
        require revalidateSessionAgainstAuthority(session)

    require authorizationAllows(
        principal = session.principalId,
        tenant = request.tenantId,
        resource = request.resource,
        action = request.action
    )

    updateLastSeenConditionally(session.version)
    return authenticatedContext(session)
~~~

Đối với logout:

~~~text
logoutCurrentSession(session):
    atomically:
        markSessionRevoked(session.id)
        revokeRelatedRefreshTokenFamilyIfRequired(session)
        appendRevocationOutboxEvent(session.id, session.principalId)

    clearClientCookie()
    return logoutAccepted()
~~~

Đối với logout all sessions, tăng security epoch bằng thao tác nguyên tử và phát event để các cache/resource server cập nhật. Không chỉ xóa cookie ở client.

## 21. Tình huống thực tế: logout nhưng một region vẫn chấp nhận session

Một dịch vụ SaaS chạy ở hai region. Session được lưu ở database primary region A và replica region B. Application node ở mỗi region cache session active trong vài phút.

Người dùng nhấn Logout tại region A:

1. Primary ghi session revoked.
2. Region A xóa cache và browser cookie.
3. Revocation event tới region B bị chậm.
4. Replica B chưa nhận thay đổi.
5. Node B vẫn có cache active hoặc đọc replica cũ và chấp nhận cookie bị sao chép.

### Tác động

- Người dùng tin rằng đã đăng xuất nhưng session cũ vẫn dùng được.
- Attacker có cookie trước đó tiếp tục truy cập.
- Nếu token refresh còn active, attacker có thể kéo dài quyền truy cập.
- Audit ở region A cho thấy logout thành công nhưng hành vi ở region B vẫn tiếp diễn.

### Thiết kế phòng thủ

1. Ghi revoke và outbox event trong cùng transaction.
2. Có event ID/version để consumer xử lý idempotent và phát hiện gap.
3. Đặt TTL cache phù hợp với maximum revocation propagation time.
4. Dùng security epoch hoặc session version để vô hiệu hóa phiên cũ.
5. Với thao tác nhạy cảm, revalidate với nguồn authoritative.
6. Thu hồi refresh token family nếu policy yêu cầu.
7. Theo dõi consumer lag, replica lag và thời gian từ logout tới từ chối ở mọi region.
8. Nếu region không thể xác minh trạng thái mới, chuyển sang degraded mode an toàn.

## 22. Kiểm thử session consistency

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Login ở node A, request tiếp theo tới node B | Cả hai node nhận cùng session state theo consistency contract. |
| Logout current session | Mọi verifier từ chối session trong thời gian propagation đã cam kết. |
| Logout all sessions | Security epoch/version tăng; session cũ bị từ chối. |
| Account suspended | Node không tiếp tục chấp nhận session theo cache stale vượt policy. |
| Password reset | Session/token cũ được xử lý theo revocation policy. |
| Hai request refresh cùng token | Một transition hợp lệ; reuse được xử lý theo semantics đã định. |
| Session revoke đồng thời với refresh | Revoke không bị ghi đè thành active; refresh không tạo nhánh token trái phép. |
| Cache invalidation event bị lặp | Consumer idempotent; trạng thái cuối đúng. |
| Event bị mất hoặc consumer offline | Outbox/reconciliation khôi phục cập nhật; có cảnh báo lag. |
| Replica lag sau revoke | Không promote/đọc stale cho thao tác cần trạng thái mới nhất. |
| Failover sang region khác | Session revoked không sống lại. |
| Session version cũ | Verifier từ chối theo security epoch. |
| Clock skew | Expiry/freshness xử lý trong tolerance có giới hạn. |
| Session store unavailable | Degraded mode theo resource/action; không fail-open chung. |
| Introspection timeout | Không mặc định token còn active. |
| Sticky session node restart | Người dùng được xử lý qua shared state hoặc reauthentication an toàn. |
| Role/tenant membership bị thu hồi | Resource server áp dụng quyền mới theo SLA. |
| Context step-up cập nhật ở node A | Node B không dùng assurance cũ cho hành động yêu cầu mức cao hơn. |

### Kiểm thử tải và diễn tập sự cố

- Đo latency đọc/ghi session và refresh token.
- Đo thời gian propagation revocation giữa mọi region.
- Kiểm tra event backlog, consumer restart và duplicate delivery.
- Diễn tập network partition, mất primary, promote replica và restore backup.
- Kiểm tra concurrent update/lost update bằng nhiều request đồng thời.
- Đo tỷ lệ false rejection do cache invalidation hoặc clock skew.
- Kiểm tra log không chứa cookie, bearer token, refresh token hoặc credential secret.

## 23. Checklist thiết kế session consistency

- [ ] Xác định nguồn authoritative cho session, account, credential, token family và authorization state.
- [ ] Phân loại dữ liệu theo mức nhạy cảm và freshness requirement.
- [ ] Chọn consistency model riêng cho login, refresh, logout, revoke và metadata.
- [ ] Định nghĩa maximum revocation propagation time và đo SLA thực tế.
- [ ] Cache có TTL, invalidation, version và hành vi khi event bị mất.
- [ ] Dùng transactional outbox hoặc cơ chế tương đương cho revoke event.
- [ ] Consumer idempotent, phát hiện event gap và có reconciliation.
- [ ] Session/security epoch ngăn session cũ sống lại sau password reset hoặc compromise.
- [ ] Logout server-side revoke session/token; xóa cookie chỉ là bước phía client.
- [ ] Refresh rotation xử lý concurrency, reuse detection và token family atomically.
- [ ] Tránh lost update; dùng version/CAS/transaction cho state transition.
- [ ] Failover chỉ dùng replica có trạng thái đủ mới cho quyết định nhạy cảm.
- [ ] Clock skew có tolerance giới hạn; không tin timestamp client để kéo dài session.
- [ ] Resource server kiểm tra issuer, audience, scope, session/account state và authorization theo trust model.
- [ ] Sticky session không được coi là cơ chế bảo đảm trạng thái.
- [ ] Degraded mode phân biệt theo resource/action; không fail-open chung.
- [ ] Kiểm thử logout, revoke, refresh, race, event loss, partition, failover và backup restore.
- [ ] Log đủ điều tra nhưng không ghi cookie/token/secret.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao logout ở một region chưa chắc làm session mất hiệu lực ở region khác?

**Gợi ý:** Cache, replica và event bus có thể nhận cập nhật trễ; verifier ở region khác vẫn có thể dùng trạng thái active cũ.

**Câu 2.** Sticky session có giải quyết session consistency không?

**Gợi ý:** Không. Nó chỉ ưu tiên định tuyến tới cùng node; node có thể restart, request có thể sang node khác và revoke vẫn cần lan truyền.

**Câu 3.** Vì sao revocation event nên được ghi qua transactional outbox?

**Gợi ý:** Tránh trường hợp database đã commit revoke nhưng process crash trước khi publish event, khiến cache tiếp tục active.

**Câu 4.** Security epoch giúp gì cho session?

**Gợi ý:** Tăng epoch ở account có thể làm mọi session mang epoch cũ bị từ chối mà không cần cập nhật từng record.

**Câu 5.** Vì sao refresh token rotation có thể gây race?

**Gợi ý:** Hai request cùng dùng token cũ; một request rotate trước, request còn lại có thể bị coi là reuse. Cần atomic transition và client coordination.

**Câu 6.** JWT có thể revoke không?

**Gợi ý:** Có thể dùng expiry ngắn, introspection, denylist hoặc version check; token tự chứa chỉ khó revoke tức thời nếu resource server không tra trạng thái.

**Câu 7.** Khi session store không sẵn sàng, vì sao không nên fail open cho mọi request?

**Gợi ý:** Node không thể biết session/account đã bị revoke hay chưa. Chỉ một số thao tác ít nhạy cảm mới có thể dùng cache trong giới hạn policy.

## 25. Ghi nhớ

**Session consistency bảo đảm các node trong hệ thống phân tán không tiếp tục tin một phiên đã bị thu hồi, hết hạn hoặc không còn đạt policy quá thời gian cho phép.** Hệ thống cần xác định nguồn authoritative, chọn consistency model theo mức rủi ro, giới hạn cửa sổ stale của cache/replica và lan truyền revocation bằng event có khả năng retry, idempotency và reconciliation. Security epoch, transaction nguyên tử và kiểm soát refresh rotation giúp tránh session cũ sống lại, lost update và token family không nhất quán. Sticky session không thay thế shared state; xóa cookie không thay thế server-side logout; và khi không thể xác minh trạng thái mới nhất, degraded mode phải giới hạn theo hành động thay vì fail open chung.
