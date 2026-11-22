# Độ trễ cập nhật khóa, quyền và trạng thái thu hồi giữa các vùng

## 1. Vì sao cùng một token có thể được chấp nhận ở vùng này nhưng bị từ chối ở vùng khác?

Trong hệ thống phân tán hoặc triển khai nhiều vùng địa lý, các thành phần xác minh JWT thường giữ bản sao dữ liệu cục bộ để giảm độ trễ và duy trì khả năng phục vụ. Những dữ liệu này có thể gồm JWKS, danh sách khóa bị thu hồi, trạng thái phiên, quyền hiện tại của người dùng và chính sách authorization.

Khi dữ liệu thay đổi, cập nhật không nhất thiết xuất hiện đồng thời ở mọi vùng. Ví dụ:

- Issuer công bố public key mới ở vùng chính, nhưng verifier tại vùng khác vẫn giữ JWKS cache cũ.
- Một khóa ký bị lộ và bị gỡ khỏi JWKS, nhưng một số verifier vẫn có public key đó trong cache.
- Người dùng vừa bị thu hồi quyền quản trị, nhưng access token tự chứa vẫn mang claim quyền cũ.
- Một phiên đăng nhập bị thu hồi ở một vùng, trong khi vùng khác chưa nhận được sự kiện thu hồi.
- Một tài khoản bị vô hiệu hóa, nhưng cache authorization cục bộ vẫn trả về trạng thái trước đó.

Đây là vấn đề **độ trễ lan truyền trạng thái (state propagation delay)**. Trong khoảng thời gian dữ liệu chưa đồng nhất, các vùng có thể đưa ra quyết định khác nhau cho cùng một credential hoặc cùng một chủ thể.

Một JWT có chữ ký hợp lệ không chứng minh rằng khóa, tài khoản, quyền hoặc phiên vẫn còn được phép tại thời điểm request đến. Xác minh chữ ký và kiểm tra trạng thái hiện tại là hai việc khác nhau.

**Nguyên tắc:** thiết kế rõ dữ liệu nào được phép stale, stale tối đa bao lâu, cách lan truyền cập nhật và hành vi của từng vùng khi không thể xác định trạng thái mới nhất.

## 2. Những loại trạng thái có thể bị trễ giữa các vùng

Không phải mọi dữ liệu bảo mật đều thay đổi cùng tốc độ hoặc có cùng hậu quả khi cập nhật chậm.

| Trạng thái | Ví dụ thay đổi | Hậu quả nếu vùng khác chưa cập nhật |
| --- | --- | --- |
| **JWKS / public keys** | Thêm khóa mới hoặc gỡ khóa cũ | Token mới có thể bị từ chối; token dùng khóa bị lộ có thể vẫn được chấp nhận |
| **Key revocation** | Đánh dấu một signing key bị compromise | Verifier chưa nhận thông tin vẫn xác minh token do khóa đó ký |
| **User / account status** | Khóa tài khoản, xóa người dùng, đổi trạng thái rủi ro | Token cũ vẫn có thể được chấp nhận nếu chỉ kiểm tra chữ ký và exp |
| **Permissions / roles** | Thu hồi quyền admin, đổi tenant hoặc scope | Token tự chứa có thể tiếp tục mang quyền cũ |
| **Session / token revocation** | Logout, thu hồi refresh token hoặc token family | Vùng chưa nhận trạng thái có thể tiếp tục chấp nhận credential |
| **Policy / authorization rules** | Thay đổi điều kiện phê duyệt hoặc giới hạn giao dịch | Cùng request có thể được quyết định khác nhau giữa các vùng |
| **Replay state** | Ghi nhận jti đã dùng | Hai vùng có thể cùng chấp nhận assertion nếu replay store không nhất quán |

Cần phân biệt **dữ liệu xác minh mật mã** với **dữ liệu authorization động**. Public key dùng để xác minh chữ ký có vòng đời và cơ chế phân phối riêng. Quyền truy cập, trạng thái tài khoản và thu hồi phiên thường cần phản ánh thay đổi nghiệp vụ nhanh hơn.

## 3. Độ trễ lan truyền khác với thời hạn token

Thời hạn JWT giới hạn khoảng thời gian token được chấp nhận theo claim thời gian. Nhưng thời hạn không tự đồng bộ trạng thái giữa các vùng.

Giả sử access token có exp sau 30 phút. Sau 5 phút, quản trị viên thu hồi quyền của subject. Nếu verifier chỉ kiểm tra chữ ký, iss, aud và exp, token vẫn có thể được chấp nhận thêm 25 phút, dù quyền đã thay đổi.

Có ba khoảng thời gian khác nhau cần tính:

1. **Token lifetime:** thời gian token được phép tồn tại theo exp và policy.
2. **Propagation delay:** thời gian một thay đổi cần để đến mọi verifier hoặc vùng.
3. **Cache staleness:** thời gian một thành phần có thể tiếp tục dùng dữ liệu cũ sau khi nguồn đã cập nhật.

Một giới hạn an toàn phải xem xét cả ba. Ví dụ, nếu một vùng giữ cache quyền trong 2 phút và sự kiện thu hồi cần 30 giây để tới vùng đó, một request có thể vẫn dùng trạng thái cũ trong khoảng kết hợp tùy cách hệ thống làm mới cache. Không nên chỉ nhìn TTL mà bỏ qua độ trễ event delivery hoặc retry.

### Bounded staleness

**Bounded staleness** là cam kết hoặc mục tiêu rằng dữ liệu cũ chỉ được dùng trong một khoảng tối đa đã định nghĩa. Thay vì nói “các vùng sẽ sớm đồng bộ”, hệ thống cần có ngân sách thời gian cụ thể cho từng loại trạng thái.

Ví dụ minh họa:

| Dữ liệu | Mức stale tối đa mục tiêu | Lý do |
| --- | --- | --- |
| JWKS cho rotation định kỳ | Theo cache/rollout window đã kiểm soát | Cho phép pre-publish khóa mới và overlap |
| Danh sách khóa compromise | Rất ngắn, có invalidation khẩn cấp | Giảm cửa sổ chấp nhận chữ ký giả mạo |
| Quyền đọc ít rủi ro | Có thể vài phút nếu policy cho phép | Cân bằng độ sẵn sàng và độ mới |
| Quyền quản trị hoặc thanh toán | Gần tức thời hoặc kiểm tra trạng thái trực tuyến | Hậu quả cao nếu quyền cũ tiếp tục được dùng |
| Replay cache của one-time assertion | Nhất quán nguyên tử trên phạm vi chấp nhận | Tránh hai vùng cùng chấp nhận một assertion |

Các con số cụ thể phải được xác định từ threat model, SLO, khả năng hạ tầng và hậu quả nghiệp vụ. Không có một TTL phù hợp cho mọi hệ thống.

## 4. JWKS propagation và độ trễ khi xoay vòng khóa

JWKS là tập hợp JWK mà verifier dùng để tìm public key phù hợp. Khi issuer thêm hoặc thay khóa, các verifier có thể nhận phiên bản mới ở những thời điểm khác nhau do cache, CDN, proxy và lịch refresh.

### Rotation định kỳ cần pre-publish

Với rotation bình thường, quy trình thường là:

1. Tạo khóa mới và công bố public JWK mới cùng public JWK cũ.
2. Chờ JWKS mới lan truyền đến các vùng và verifier quan trọng.
3. Chuyển issuer sang ký token mới bằng private key mới.
4. Giữ public key cũ để xác minh token đã phát hành trước cutover.
5. Chỉ gỡ public key cũ khi token cũ đã hết hạn và không còn nhu cầu hợp lệ cần xác minh.

Nếu issuer ký bằng khóa mới trước khi verifier các vùng nhận được JWKS mới, token hợp lệ có thể bị từ chối vì unknown kid.

### JWKS cache tạo ra độ trễ có thể dự đoán

Verifier và proxy có thể sử dụng HTTP caching, ví dụ Cache-Control, ETag và conditional request. Cần biết:

- Cache lifetime thực tế ở từng hop.
- Có proxy/CDN nào ghi đè cache directive hay không.
- Verifier có refresh khi gặp kid chưa biết không.
- Refresh có bị giới hạn tần suất và gộp request đồng thời không.
- Có vùng nào chỉ tải JWKS lúc khởi động hay không.
- Cache có thể bị giữ lâu hơn dự kiến khi endpoint JWKS lỗi hay không.

Khi gặp kid chưa biết, verifier có thể refresh JWKS từ URI đã cấu hình tin cậy rồi thử lại một lần có giới hạn. Không được tải khóa từ URL tùy ý trong token. Cần rate limit để attacker không thể gửi hàng loạt kid ngẫu nhiên và buộc verifier gọi JWKS liên tục.

### Gỡ khóa cũ không đồng nghĩa thu hồi tức thời

Khi public key cũ bị xóa khỏi JWKS, verifier đã cache bản cũ có thể tiếp tục dùng nó cho đến khi cache hết hạn hoặc được invalidation. Vì vậy, xóa JWK khỏi endpoint là một thay đổi phân phối; nó không tự bảo đảm mọi vùng ngừng tin khóa tại cùng một thời điểm.

Đối với rotation định kỳ, overlap được thiết kế để chấp nhận token cũ trong một khoảng có kiểm soát. Đối với khóa bị compromise, cần một đường thu hồi khẩn cấp có thể ghi đè cache bình thường.

## 5. Thu hồi khóa bị compromise cần đường lan truyền ưu tiên

Nếu private signing key bị lộ, attacker có thể tạo token mới có chữ ký hợp lệ theo public key tương ứng. Tiếp tục chấp nhận key đó chỉ để tránh gián đoạn có thể cho phép attacker giả mạo danh tính hoặc quyền.

Quy trình khẩn cấp cần phối hợp nhiều thành phần:

- Vô hiệu hóa quyền ký và quyền truy cập private key ở hệ thống phát hành.
- Phát hành khóa thay thế theo quy trình khẩn cấp.
- Đưa kid bị lộ vào danh sách từ chối hoặc trạng thái revoked được verifier kiểm tra.
- Phát sự kiện invalidation tới các vùng, verifier, gateway và service liên quan.
- Buộc làm mới JWKS hoặc cập nhật trust state theo kênh quản trị tin cậy.
- Xác nhận từng vùng đã áp dụng trạng thái revoked trước khi kết thúc incident.
- Đánh giá token được phát hành trong cửa sổ compromise và thực hiện thu hồi phiên hoặc xác thực lại khi cần.

### Vì sao chỉ xóa JWK là chưa đủ?

Một verifier có thể vẫn giữ public key trong cache. Nếu nó chỉ kiểm tra chữ ký bằng cache đó và không kiểm tra denylist hoặc key status mới, token giả mạo vẫn có thể được chấp nhận.

Một cơ chế khẩn cấp có thể là:

~~~text
if token.kid in emergency_revoked_kids:
    reject_token
else:
    verify_signature_with_trusted_jwks
~~~

Danh sách revoked phải đến từ control plane tin cậy, có xác thực, phiên bản và thời điểm hiệu lực rõ ràng. Không để token tự khai trạng thái khóa.

### Cân nhắc fail-closed trong incident

Nếu verifier không thể tải được trạng thái thu hồi mới nhất trong một incident đang diễn ra, hệ thống phải có policy xác định trước. Với endpoint quản trị, thanh toán hoặc dữ liệu nhạy cảm, có thể cần từ chối credential phụ thuộc khóa bị ảnh hưởng cho đến khi trạng thái được xác minh. Với dịch vụ ít rủi ro hơn, có thể áp dụng phương án availability có giới hạn và được phê duyệt trước.

Không nên tự động chuyển sang fail-open chỉ vì một vùng mất kết nối với control plane. Điều đó có thể biến lỗi đồng bộ thành cửa sổ chấp nhận token đã bị thu hồi.

## 6. Quyền và vai trò thay đổi nhưng JWT tự chứa vẫn giữ claims cũ

JWT access token thường là snapshot claims tại thời điểm phát hành. Ví dụ token mang:

~~~json
{
  "sub": "user-123",
  "tenant_id": "tenant-17",
  "roles": ["admin"],
  "scope": "users:read users:write",
  "exp": 1893459600
}
~~~

Sau khi token được phát hành, người dùng có thể bị gỡ role admin hoặc chuyển sang tenant khác. Payload đã ký không tự thay đổi theo cơ sở dữ liệu. Chữ ký vẫn hợp lệ cho đến khi token hết hạn hoặc một policy bổ sung từ chối nó.

Đây không hẳn là lỗi replication; ngay cả khi mọi vùng nhận cùng token, claim snapshot vẫn là dữ liệu cũ theo thiết kế. Muốn quyền thay đổi có hiệu lực nhanh, cần kết hợp token với trạng thái authorization động.

### Các chiến lược phổ biến

| Chiến lược | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| Token lifetime ngắn | Quyền cũ tự hết hiệu lực khi token hết hạn | Giảm cửa sổ stale nhưng tăng tần suất cấp token |
| Authorization lookup | Service tra cứu quyền hoặc trạng thái hiện tại | Cập nhật nhanh hơn nhưng thêm phụ thuộc mạng/cache |
| Token introspection | Resource Server hỏi AS token còn active không | Tập trung trạng thái nhưng tăng latency và tải |
| Subject/session version | Token mang version; service so sánh với version hiện tại | Có thể phát hiện token cũ bằng một lookup nhỏ |
| Revocation/denylist | Đánh dấu token hoặc session bị thu hồi | Hiệu quả nếu trạng thái lan truyền đủ nhanh |
| Sender-constrained token | Ràng buộc credential với khóa/chứng thư | Giảm rủi ro token bị đánh cắp; không tự cập nhật quyền |

### Authorization version hoặc epoch

Một hệ thống có thể lưu phiên bản authorization của subject hoặc session. Token mang phiên bản tại lúc phát hành:

~~~json
{
  "sub": "user-123",
  "authz_ver": 42,
  "exp": 1893459600
}
~~~

Khi quyền thay đổi, hệ thống tăng version hiện tại lên 43. Service kiểm tra version trong token với version hiện tại. Token có version 42 bị từ chối nếu policy yêu cầu khớp tuyệt đối.

Cách này chỉ hiệu quả nếu dữ liệu version được đọc từ nguồn đủ mới. Nếu mỗi vùng cache version cũ quá lâu, vấn đề propagation vẫn còn. Có thể dùng version cho một subject, tenant, client hoặc policy domain tùy cách quản lý.

Không nên tăng version cho mọi thay đổi nhỏ nếu gây invalidation quá rộng. Cần xác định phạm vi version và cách xử lý token đang được sử dụng.

## 7. Thu hồi token, session và refresh token giữa các vùng

Một số loại thu hồi cần được phân biệt:

- **Access-token revocation:** token hiện tại không còn được chấp nhận.
- **Refresh-token revocation:** không cho phép dùng refresh token để cấp access token mới.
- **Token-family revocation:** vô hiệu hóa cả nhóm token liên quan đến một phiên hoặc chuỗi refresh.
- **Session revocation:** kết thúc phiên đăng nhập hoặc phiên thiết bị.
- **Account disablement:** vô hiệu hóa danh tính hoặc ngăn mọi phiên mới.
- **Key revocation:** ngừng tin cậy mọi token được ký bằng khóa bị thu hồi, trừ khi policy có ngoại lệ được xác định rõ.

RFC 7009 định nghĩa OAuth token revocation endpoint; RFC 7662 định nghĩa token introspection để resource server truy vấn trạng thái token. Các cơ chế này không tự quyết định replication topology của hệ thống. Tổ chức vẫn phải bảo đảm trạng thái thu hồi đến các vùng và được áp dụng theo SLA nội bộ.

### Denylist theo jti hoặc token identifier

Một denylist có thể lưu định danh token bị thu hồi cho đến khi token không còn hiệu lực. Khóa bản ghi thường cần gắn với issuer và định danh token để tránh va chạm giữa các issuer.

Nếu chỉ lưu denylist ở một vùng, request đến vùng khác có thể chưa thấy trạng thái mới. Có thể dùng replication, event invalidation, hoặc tra cứu trung tâm cho các request nhạy cảm.

### Logout không tự làm JWT biến mất

Nếu access token tự chứa vẫn còn hạn và verifier không kiểm tra session/revocation state, thao tác logout ở một vùng không tự khiến mọi vùng từ chối token. Cần xác định logout có nghĩa là:

- Chỉ xóa cookie/token ở client.
- Thu hồi refresh token.
- Thu hồi toàn bộ token family.
- Thu hồi session trên mọi vùng.
- Thêm access-token identifier vào denylist.
- Tăng session/authz version.

Mỗi lựa chọn có độ trễ và chi phí khác nhau. UI hiển thị “đã đăng xuất” không chứng minh mọi Resource Server đã nhận trạng thái thu hồi.

## 8. Lan truyền thay đổi bằng event và invalidation

Một mô hình thường gặp là phát sự kiện khi khóa, quyền hoặc session thay đổi. Các consumer ở từng vùng nhận sự kiện và cập nhật cache cục bộ.

Ví dụ:

~~~json
{
  "event_id": "evt-9c21",
  "event_type": "SigningKeyRevoked",
  "issuer": "https://identity.example",
  "kid": "signing-k1",
  "version": 108,
  "effective_at": "2026-11-16T12:00:00Z"
}
~~~

Một event về thay đổi quyền có thể chứa subject hoặc authorization domain, version mới và thời điểm hiệu lực. Không nên đưa private key, access token hoặc dữ liệu nhạy cảm không cần thiết vào event.

### Yêu cầu đối với event propagation

- **Authenticated producer:** consumer xác minh event đến từ control plane hoặc producer được phép.
- **Integrity:** event không thể bị sửa đổi trên đường truyền hoặc trong broker.
- **Ordering/version:** consumer phát hiện event cũ, trùng hoặc đến sai thứ tự.
- **Idempotency:** xử lý lại cùng event không làm trạng thái sai.
- **Durability:** event không bị mất khi consumer tạm thời offline.
- **Retry and dead-letter:** lỗi xử lý có cơ chế retry và cảnh báo.
- **Acknowledgement:** chỉ xác nhận đã xử lý sau khi trạng thái được ghi bền vững.
- **Reconciliation:** consumer định kỳ so sánh version hoặc snapshot với nguồn chuẩn.

Event invalidation có thể giảm độ trễ nhưng không nên là nguồn duy nhất bảo đảm trạng thái cuối cùng. Cần một cơ chế đối soát để phát hiện consumer bỏ lỡ event hoặc cache bị lệch.

### Version giúp xử lý event đến sai thứ tự

Giả sử vùng A nhận version 12 rồi sau đó nhận event version 11 do retry hoặc mạng. Consumer không được ghi đè trạng thái mới bằng dữ liệu cũ. Chỉ áp dụng event nếu version mới hơn version đã lưu, hoặc dùng sequence/transaction có quy tắc tương đương.

## 9. Control plane và data plane

Trong hệ thống nhiều vùng, nên phân biệt:

- **Control plane:** nơi quản trị và phân phối thay đổi khóa, policy, quyền, trạng thái thu hồi và cấu hình tin cậy.
- **Data plane:** nơi tiếp nhận request thực tế và xác minh token, kiểm tra quyền hoặc xử lý nghiệp vụ.

Control plane có thể phát hành một trạng thái mới; data plane ở từng vùng cần xác nhận đã áp dụng trạng thái đó. Chỉ biết control plane đã ghi thành công không có nghĩa mọi verifier đã nhận cập nhật.

Một trạng thái phân phối có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `state_version` | Phiên bản mới nhất của trạng thái |
| `published_at` | Thời điểm control plane công bố |
| `received_at` | Thời điểm vùng nhận dữ liệu |
| `applied_at` | Thời điểm verifier thực sự áp dụng |
| `source` | Nguồn phát hành trạng thái |
| `effective_at` | Thời điểm chính sách bắt đầu có hiệu lực |
| `checksum` | Kiểm tra tính nhất quán của snapshot nếu phù hợp |

Với thay đổi khẩn cấp, cần xác nhận `applied_at` ở từng vùng. Một dashboard chỉ hiển thị event đã publish là chưa đủ để chứng minh trạng thái đã có hiệu lực trên data plane.

## 10. Multi-region: nhất quán mạnh hay nhất quán cuối cùng?

Các hệ thống nhiều vùng thường phải cân bằng latency, availability và consistency. Không phải mọi loại dữ liệu đều cần cùng một mô hình.

| Dữ liệu | Mô hình có thể phù hợp | Lý do |
| --- | --- | --- |
| JWKS cho rotation định kỳ | Eventual consistency có overlap và cache bound | Có thể công bố khóa mới trước khi dùng |
| Emergency key revocation | Strong coordination hoặc fast invalidation có xác nhận | Cần hạn chế nhanh việc chấp nhận khóa bị lộ |
| Quyền đọc ít rủi ro | Bounded eventual consistency | Có thể chấp nhận độ trễ ngắn theo policy |
| Quyền admin, chuyển tiền | Online check hoặc consistency mạnh hơn | Chi phí của stale authorization cao |
| Replay cache one-time proof | Atomic shared state hoặc partitioning bảo đảm cùng key về một nơi | Hai vùng không được cùng chấp nhận một proof |
| Audit events | Durable event stream và reconciliation | Không được mất lịch sử quyết định |

Không nên tuyên bố toàn hệ thống “strongly consistent” nếu chỉ một kho dữ liệu có tính nhất quán mạnh. Cache tại gateway, CDN, service process và local replica vẫn có thể giữ trạng thái cũ.

### Khi các vùng bị partition

Nếu một vùng mất liên lạc với control plane hoặc kho trạng thái trung tâm, nó không thể biết chắc có thay đổi mới nào vừa xảy ra. Hành vi cần dựa trên risk tier:

- Với quyết định nhạy cảm, có thể từ chối hoặc yêu cầu kiểm tra trực tuyến khi không xác minh được trạng thái.
- Với tác vụ ít rủi ro, có thể cho phép stale state trong một ngân sách thời gian đã định nghĩa.
- Khi stale budget vượt ngưỡng, chuyển sang trạng thái hạn chế thay vì tiếp tục dùng cache vô thời hạn.
- Ghi nhận rõ vùng nào đang hoạt động với trạng thái cũ và cảnh báo vận hành.

Availability không nên được duy trì bằng cách âm thầm bỏ qua thu hồi hoặc authorization version.

## 11. Thiết kế ngân sách độ trễ cho từng loại cập nhật

Mỗi loại trạng thái cần có một ngân sách end-to-end, không chỉ một TTL cache.

Ví dụ ngân sách cập nhật một thay đổi quyền:

~~~text
change_committed
    -> event_published
    -> event_delivered_to_region
    -> consumer_applied
    -> local_cache_invalidated
    -> next_authorization_check_uses_new_state
~~~

Tổng thời gian có thể gồm:

~~~text
propagationDelay =
    publishDelay
    + brokerDeliveryDelay
    + consumerProcessingDelay
    + cacheInvalidationDelay
    + requestVisibilityDelay
~~~

Nếu hệ thống dùng polling thay vì event, cần cộng thêm khoảng polling và thời gian retry. Nếu một service có cache thứ cấp, cần tính cả TTL hoặc invalidation của cache đó.

### Ví dụ ngân sách minh họa

Giả sử một thay đổi quyền cần có hiệu lực trong tối đa 60 giây:

| Thành phần | Ngân sách ví dụ |
| --- | ---: |
| Ghi trạng thái và publish event | 5 giây |
| Broker giao đến các vùng | 10 giây |
| Consumer áp dụng và invalidation | 10 giây |
| Cache phụ hết hạn hoặc refresh | 20 giây |
| Dự phòng và kiểm tra | 15 giây |
| **Tổng** | **60 giây** |

Nếu một thành phần vượt ngân sách, hệ thống cần cảnh báo và có hành vi hạn chế phù hợp. Các con số trên chỉ minh họa cách phân bổ; cần đo latency thực tế và đặt SLO phù hợp với rủi ro.

## 12. Quan sát propagation và phát hiện vùng stale

Không thể quản lý độ trễ nếu hệ thống không đo được nó. Cần quan sát cả trạng thái control plane lẫn data plane.

### Chỉ số nên thu thập

- Thời gian từ lúc thay đổi được commit đến khi publish event.
- Thời gian event tới từng vùng.
- Thời gian consumer áp dụng và invalidation cache.
- Version mới nhất tại control plane và version đang dùng tại từng vùng.
- Tuổi của JWKS cache và thời điểm refresh thành công gần nhất.
- Số request bị từ chối do unknown kid.
- Số token bị từ chối do revoked kid, revoked jti hoặc authz version mismatch.
- Tỷ lệ quyết định authorization khác nhau giữa các vùng.
- Số lần verifier không thể truy cập control plane hoặc introspection endpoint.
- Số vùng vượt stale budget.

Không ghi nguyên access token, private key hoặc assertion vào metric/log. Có thể ghi issuer đã được chuẩn hóa, kid, state version, region, decision reason và timestamp theo chính sách bảo vệ dữ liệu.

### Phân biệt event delivered và state applied

Một message broker báo event đã giao không chứng minh consumer đã cập nhật cache thành công. Cần theo dõi ít nhất:

1. Event đã được publish.
2. Event đã được consumer nhận.
3. Trạng thái đã được ghi bền vững.
4. Cache đã được invalidated hoặc thay thế.
5. Request mới thực sự dùng version mới.

Đây là các mốc khác nhau và nên có telemetry tương ứng.

## 13. Kiểm thử độ trễ và lỗi lan truyền

Kiểm thử không chỉ xác nhận đường đi thành công trong điều kiện bình thường. Cần mô phỏng vùng nhận cập nhật chậm, mất event hoặc giữ cache cũ.

| Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- |
| JWKS mới đã publish nhưng một vùng còn cache cũ | Token dùng key mới chỉ được phát hành sau pre-publish window hoặc verifier refresh có giới hạn |
| Unknown kid xuất hiện đồng thời ở nhiều request | Refresh được gộp/rate limit, không tạo JWKS request storm |
| Public key cũ bị gỡ khỏi JWKS nhưng verifier cache chưa hết hạn | Rotation bình thường vẫn xác minh token cũ trong overlap; incident compromise phải áp dụng revoked-kid state |
| Sự kiện revoke bị giao trùng | Consumer xử lý idempotent, trạng thái không bị thay đổi sai |
| Event version cũ đến sau version mới | Consumer bỏ qua event cũ |
| Một vùng mất kết nối broker | Cảnh báo stale state, replay event hoặc reconcile khi kết nối phục hồi |
| Quyền admin bị thu hồi | Quyết định nhạy cảm không tiếp tục dựa vào role cũ quá stale budget |
| Logout ở vùng A, request đến vùng B | Hành vi phù hợp với SLA thu hồi đã công bố; không giả định logout tự đồng bộ |
| Introspection endpoint không khả dụng | Thực hiện failure policy theo risk tier, không tự động tin token chưa kiểm tra |
| Hai vùng nhận cùng one-time assertion đồng thời | Chỉ một vùng có thể ghi replay state thành công |
| Clock lệch giữa các vùng | exp, nbf, iat được đánh giá theo clock policy đã thống nhất và có monitoring |

Có thể dùng fault injection để trì hoãn, đảo thứ tự, nhân đôi hoặc làm mất event. Mục tiêu là xác nhận hệ thống phát hiện stale state và phản ứng đúng, không chỉ kiểm tra happy path.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ xóa key khỏi JWKS để thu hồi khẩn cấp | Verifier cache cũ vẫn có thể chấp nhận token | Có revoked-kid state và invalidation ưu tiên |
| Dùng một TTL cho mọi loại cache | Quyền nhạy cảm stale quá lâu hoặc cache vô ích | Đặt stale budget theo loại dữ liệu và risk tier |
| Cho rằng publish event nghĩa là mọi vùng đã cập nhật | Một số consumer có thể chưa nhận hoặc chưa áp dụng | Theo dõi applied version từng vùng |
| Không có version/sequence cho event | Event cũ đến sau có thể ghi đè trạng thái mới | Dùng version và từ chối update cũ |
| Dùng cache cục bộ cho replay protection đa vùng | Cùng assertion có thể được chấp nhận ở hai vùng | Dùng atomic shared replay state hoặc partitioning bảo đảm |
| Dùng access token tự chứa để phản ánh quyền tức thời | Claim quyền cũ vẫn hợp lệ đến exp | Introspection, authz version, denylist hoặc lookup động |
| Logout chỉ xóa cookie phía client | Token đã sao chép vẫn có thể được sử dụng | Thu hồi session/token theo policy |
| Fail-open khi control plane mất kết nối | Token/key/quyền đã thu hồi có thể tiếp tục được chấp nhận | Fail policy theo risk tier và stale budget |
| Không kiểm tra clock giữa các vùng | Sai lệch exp/nbf làm chấp nhận hoặc từ chối sai | Đồng bộ thời gian và giới hạn clock skew |
| Chỉ đo broker delivery latency | Không biết cache đã áp dụng hay request đã thấy trạng thái mới | Đo tới applied state và decision path |
| Không kiểm thử partition và event reorder | Lỗi chỉ xuất hiện khi sự cố thật xảy ra | Fault injection và reconciliation test |

## 15. Checklist thiết kế propagation an toàn

**Với khóa và JWKS**

- Xác định cache TTL, nguồn JWKS tin cậy và lịch refresh ở từng vùng.
- Pre-publish public key mới trước khi issuer bắt đầu ký bằng key đó.
- Giữ public key cũ trong overlap theo maximum token lifetime và clock skew.
- Có revoked-kid mechanism riêng cho key compromise.
- Có refresh/invalidation khẩn cấp và xác nhận applied state ở từng vùng.
- Rate limit unknown-kid refresh và không tải key từ URL do token kiểm soát.

**Với quyền, tài khoản và session**

- Xác định claim nào là snapshot và claim nào phải tra cứu động.
- Đặt stale budget theo mức rủi ro của hành động.
- Dùng authorization version, introspection, denylist hoặc lookup khi cần thu hồi nhanh.
- Phân biệt access token, refresh token, token family, session và account revocation.
- Đảm bảo logout và account disablement có semantics rõ trên mọi vùng.
- Không để token có quyền nhạy cảm tồn tại lâu hơn nhu cầu.

**Với event và multi-region**

- Xác thực producer, bảo vệ integrity và giới hạn quyền publish.
- Dùng event ID, version/sequence và idempotent consumer.
- Bảo đảm event durable, retry và dead-letter handling.
- Có reconciliation để phát hiện event bị mất hoặc cache lệch.
- Theo dõi published, received, applied và cache-invalidated time.
- Định nghĩa hành vi khi partition hoặc stale budget bị vượt.

**Với vận hành**

- Đặt SLO propagation cho từng loại trạng thái.
- Cảnh báo theo region/version lag và stale age.
- Kiểm thử delay, duplicate, reorder, lost event và concurrent request.
- Chọn fail-open/fail-closed theo rủi ro và quyết định cần bảo vệ.
- Không ghi token hoặc khóa bí mật vào log/metric.
- Có runbook cho key compromise, mass revocation và authorization policy change.

**Ghi nhớ:** Trong hệ thống nhiều vùng, chữ ký hợp lệ và token chưa hết hạn không bảo đảm khóa, quyền hoặc session vẫn được chấp nhận ở mọi nơi. JWKS cache, event delivery, authorization cache và replication tạo ra các cửa sổ stale khác nhau. Hãy đặt stale budget theo rủi ro, theo dõi version đã áp dụng tại từng vùng, dùng invalidation khẩn cấp cho khóa bị compromise và kiểm tra trạng thái authorization động cho hành động nhạy cảm. Eventual consistency có thể phù hợp với rotation định kỳ hoặc quyền ít rủi ro; thu hồi khóa, quyền quản trị và replay protection cần cơ chế mạnh hơn và hành vi rõ khi mất kết nối.

### Tài liệu chuẩn để tra cứu

- **RFC 7517 — JSON Web Key (JWK):** JWK, JWKS và thuộc tính khóa.
- **RFC 7519 — JSON Web Token (JWT):** claims thời gian, issuer, audience và token identifier.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh JWT, thuật toán và khóa tin cậy.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi access token và refresh token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** truy vấn trạng thái token từ Authorization Server.
- **RFC 9111 — HTTP Caching:** cache directives, freshness và revalidation áp dụng cho phân phối JWKS qua HTTP.
- **RFC 8693 — OAuth 2.0 Token Exchange:** cấp token theo audience, actor và delegation giữa các service.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị giảm rủi ro token và bảo vệ authorization flow.
