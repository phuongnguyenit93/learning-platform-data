# So sánh repository Redis cơ bản với repository có chỉ mục

Spring Session Data Redis cung cấp các repository để lưu `Session` trong Redis. Hai lựa chọn thường gặp là `RedisSessionRepository` và `RedisIndexedSessionRepository`. Cả hai đều cho phép ứng dụng lưu session ngoài bộ nhớ JVM và tìm session theo ID. Điểm khác biệt quan trọng là repository indexed duy trì các chỉ mục phụ, đặc biệt là chỉ mục theo principal, để tìm các session thuộc về một người dùng và hỗ trợ các tính năng quản lý vòng đời liên quan.

Nếu ứng dụng chỉ cần khôi phục session từ cookie/session ID, repository cơ bản thường có mô hình đơn giản hơn. Nếu cần tìm tất cả session của một principal, kiểm soát nhiều phiên đăng nhập, hoặc dùng các tính năng phụ thuộc `FindByIndexNameSessionRepository` và session events, repository indexed phù hợp hơn. Chỉ mục đem lại khả năng truy vấn bổ sung nhưng cũng làm tăng số dữ liệu, thao tác ghi, yêu cầu cấu hình Redis và công việc vận hành.

## 1. Hai repository phục vụ hai nhu cầu khác nhau

| Tiêu chí | `RedisSessionRepository` | `RedisIndexedSessionRepository` |
|---|---|---|
| Lưu session trong Redis | Có | Có |
| Tìm session theo ID | Có | Có |
| Tìm session theo principal | Không cung cấp principal index | Có, thông qua index |
| Contract chính | `SessionRepository` | `FindByIndexNameSessionRepository` cùng contract session |
| Metadata phụ | Ít hơn, tập trung vào session | Có thêm index và metadata phục vụ lookup/lifecycle |
| Chi phí ghi và dung lượng | Thường thấp hơn do ít cấu trúc phụ | Cao hơn do duy trì index và metadata |
| Phù hợp | Session lookup theo ID | Quản lý nhiều session theo principal và các use case indexed |

Tên class, cách auto-configuration chọn implementation và một số API có thể khác theo phiên bản Spring Session/Spring Boot. Hãy kiểm tra dependency đang chạy và bean `SessionRepository` thực tế. Không suy luận repository được dùng chỉ từ việc ứng dụng có dependency Redis.

## 2. Điểm chung: session vẫn được lưu ngoài JVM

Cả hai repository đều lưu dữ liệu session trong Redis. Khi request mang session ID hợp lệ:
1. Spring Session filter hoặc WebSession integration resolve ID.
2. Repository tìm dữ liệu session trong Redis.
3. Session được khôi phục để ứng dụng đọc/ghi thuộc tính.
4. Thay đổi được lưu theo flush/save mode.
5. Request khác, kể cả đến instance khác, có thể đọc session từ cùng Redis namespace.

Điều này cho phép nhiều instance chia sẻ session mà không cần sticky session để giữ trạng thái trong heap của một node. Tuy nhiên, repository không tự làm cho mọi thao tác đọc-sửa-ghi thành transaction nghiệp vụ nguyên tử.

Cả hai lựa chọn đều cần cấu hình cookie/session ID, namespace, serializer, timeout và kết nối Redis nhất quán trên các instance.

## 3. RedisSessionRepository: mô hình lookup theo ID

`RedisSessionRepository` là lựa chọn cơ bản khi ứng dụng chỉ cần lưu và tìm session bằng ID. Nó triển khai `SessionRepository`, do đó các thao tác chính là:
- `createSession()` để tạo session mới.
- `save(session)` để lưu thay đổi.
- `findById(id)` để tìm session.
- `deleteById(id)` để xóa session.

Repository không cung cấp principal secondary index như `RedisIndexedSessionRepository`. Khi ứng dụng có session ID, nó có thể tìm session đó. Nhưng từ một username/principal, repository cơ bản không có cấu trúc index chuyên dụng để liệt kê toàn bộ session của người đó.

Ví dụ sử dụng contract cơ bản:

```java
Session session = sessionRepository.findById(sessionId);

if (session != null) {
    session.setAttribute("lastSection", "billing");
    sessionRepository.save(session);
}
```

Ví dụ trên minh họa API đồng bộ `SessionRepository`. Trong Servlet app, thao tác thông thường có thể diễn ra qua `HttpSession` và Spring Session filter; không cần gọi repository trực tiếp trong controller. Với reactive WebFlux, dùng `ReactiveSessionRepository` tương ứng thay vì API đồng bộ.

## 4. RedisIndexedSessionRepository: thêm khả năng tìm theo index

`RedisIndexedSessionRepository` bổ sung khả năng tra cứu session theo index. Repository này triển khai `FindByIndexNameSessionRepository`, cho phép tìm session theo một tên index và giá trị index.

Index được dùng phổ biến nhất là principal name. Một ứng dụng có thể lấy tất cả session gắn với người dùng, ví dụ để:
- Hiển thị danh sách thiết bị/phiên đăng nhập.
- Giới hạn số phiên đồng thời.
- Thu hồi tất cả phiên của người dùng.
- Phục vụ màn hình quản trị session.
- Điều tra sự cố đăng nhập và logout.

Ví dụ:

```java
Map<String, ? extends Session> sessions =
        indexedRepository.findByPrincipalName("user-42");

sessions.forEach((sessionId, session) ->
        logSessionSummary(sessionId, session));
```

Map trả về ánh xạ session ID sang session. Không log session ID nguyên vẹn hoặc thuộc tính nhạy cảm khi xây màn hình quản trị/audit; chỉ hiển thị thông tin đã được lọc và người dùng có quyền xem.

## 5. Principal index hoạt động như thế nào?

Repository indexed cần biết principal nào sở hữu session. Với Spring Security, `PrincipalNameIndexResolver` có thể tìm tên principal từ `SecurityContext` được lưu trong session.

Luồng khái quát:
1. Người dùng xác thực.
2. `SecurityContext` chứa `Authentication` được lưu vào session.
3. Index resolver đọc principal name.
4. Repository cập nhật quan hệ principal → session ID.
5. Khi session bị xóa, hết hạn hoặc principal index thay đổi, repository cần cập nhật/gỡ metadata liên quan.
6. Truy vấn theo principal sử dụng index để tìm session ID và khôi phục session.

Index không phải dữ liệu xác thực độc lập. Session record vẫn là dữ liệu cần kiểm tra để xác định session còn tồn tại và hợp lệ.

## 6. Dùng FindByIndexNameSessionRepository

Contract cho phép truy vấn theo tên index và giá trị index:

```java
Map<String, ? extends Session> sessions =
        repository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName);
```

Với principal name, có thể dùng phương thức tiện ích `findByPrincipalName` nếu implementation cung cấp qua contract tương ứng:

```java
Map<String, ? extends Session> sessions =
        repository.findByPrincipalName(principalName);
```

Hãy inject đúng bean indexed repository hoặc interface `FindByIndexNameSessionRepository` trong cấu hình ứng dụng. Nếu chỉ inject `SessionRepository`, code gọi principal lookup sẽ không có method này và không nên ép kiểu tùy tiện.

## 7. Cấu hình principal index resolver

Khi ứng dụng dùng Spring Security với cấu trúc `SecurityContext` chuẩn, `PrincipalNameIndexResolver` thường là lựa chọn phù hợp. Nếu principal được lưu theo cấu trúc tùy chỉnh, cần cấu hình resolver biết cách lấy principal.

Ví dụ khung:

```java
@Bean
IndexResolver<Session> sessionIndexResolver() {
    return new PrincipalNameIndexResolver<>();
}
```

Cách đăng ký resolver phụ thuộc cấu hình repository và phiên bản Spring Session. Một số cấu hình cho phép truyền `IndexResolver` trực tiếp vào indexed repository hoặc customizer. Hãy dùng extension point của phiên bản hiện tại, tránh tự tạo repository thứ hai chỉ để thay resolver.

Nếu principal không được resolve, session có thể vẫn lưu và tìm theo ID bình thường nhưng không xuất hiện trong kết quả `findByPrincipalName`. Đây là lỗi cấu hình index, không nhất thiết là lỗi lưu session.

## 8. Principal tùy chỉnh và index riêng

Ứng dụng có thể dùng principal không dựa trên `SecurityContext` chuẩn, ví dụ xác thực API key, tenant identity hoặc principal từ hệ thống legacy. Khi đó có thể:
- Viết `IndexResolver<Session>` riêng.
- Lưu một thuộc tính index ổn định vào session.
- Chuẩn hóa principal name trước khi index.
- Dùng nhiều index nếu use case yêu cầu và implementation hỗ trợ.

Không dùng email hoặc tên hiển thị có thể thay đổi làm khóa index nếu ứng dụng có một subject ID bất biến. Index value nên ổn định, không chứa bí mật và không làm lộ dữ liệu cá nhân trong key Redis.

Nếu principal name thay đổi, cần đảm bảo index cũ được gỡ và index mới được tạo. Hãy kiểm thử cả thay đổi principal attribute và session lifecycle.

## 9. Chỉ mục phụ tạo thêm chi phí gì?

Repository indexed cần duy trì nhiều dữ liệu hơn session record cơ bản. Tùy phiên bản và tính năng được bật, có thể có:
- Principal index chứa các session ID theo người dùng.
- Metadata theo session để xác định các index cần xóa.
- Expiration tracking keys.
- Các cấu trúc hỗ trợ phát hiện session deletion/expiration.
- Event subscriptions và cleanup processing.

Điều này làm tăng:
- Số lệnh Redis khi tạo, cập nhật, xóa session.
- Dung lượng Redis.
- Độ phức tạp của serializer/index resolver.
- Công việc cleanup và reconciliation.
- Yêu cầu về keyspace notifications.
- Số tình huống cần kiểm thử khi failover hoặc mất event.

Mức overhead thực tế phụ thuộc số session, số index, tần suất cập nhật, save mode và phiên bản repository. Hãy đo bằng workload thực tế thay vì giả định indexed repository luôn chậm đáng kể hoặc luôn không đáng kể.

## 10. Redis keyspace notifications và session events

`RedisIndexedSessionRepository` sử dụng Redis keyspace notifications để nhận biết session bị xóa hoặc hết hạn và xử lý index/lifecycle event. Redis thường cần bật các loại notification phù hợp, ví dụ:

```text
notify-keyspace-events Egx
```

`E` bật keyevent notifications; `g` cho các generic commands; `x` cho expired events. Cấu hình chính xác cần theo tài liệu Spring Session và Redis version/topology.

Các sự kiện Spring Session liên quan có thể gồm:
- `SessionDeletedEvent` khi session bị xóa.
- `SessionExpiredEvent` khi session hết hạn.
- `SessionDestroyedEvent` là abstraction/supertype liên quan cho lifecycle destruction.

Sự kiện giúp dọn index và cho ứng dụng phản ứng với lifecycle, ví dụ đóng WebSocket liên quan. Không coi Redis Pub/Sub/keyspace notification là audit log bền vững; event có thể bị mất khi subscriber không hoạt động.

## 11. Repository cơ bản có đủ session expiration không?

Cần phân biệt ba việc:
1. Repository không trả session đã hết hạn.
2. Redis key có TTL để dữ liệu được thu hồi vật lý.
3. Ứng dụng nhận event để dọn index/tài nguyên phụ.

Hai repository có thể có semantics và cơ chế expiration/event khác nhau theo implementation/version. Không suy ra rằng repository cơ bản phát đầy đủ cùng loại `SessionDestroyedEvent` hoặc duy trì cùng expiration index như repository indexed.

Nếu ứng dụng cần listener để đóng WebSocket hoặc cần principal index được dọn theo expiration, hãy xác nhận implementation hỗ trợ event đó và cấu hình Redis notifications tương ứng. Kiểm thử repository behavior trên phiên bản đang dùng thay vì dựa vào tên class.

Dù event cleanup bị trễ, request không được xem session hết hạn là hợp lệ chỉ vì key vật lý chưa bị xóa. Tính hợp lệ của session phải được quyết định bởi repository theo timeout.

## 12. Redis namespace và cách ly ứng dụng

Mỗi ứng dụng hoặc môi trường nên có namespace riêng nếu không chủ ý chia sẻ session. Ví dụ Spring Boot:

```yaml
spring:
  session:
    redis:
      namespace: portal:sessions
```

Ứng dụng quản trị có thể dùng namespace khác:

```yaml
spring:
  session:
    redis:
      namespace: admin:sessions
```

Namespace giúp tránh key collision và phân tách dữ liệu logic. Nó không tự tạo ranh giới bảo mật nếu cùng Redis credential có quyền đọc/ghi mọi key. Dùng ACL key pattern và credential riêng khi cần isolation thực sự.

Nếu hai instance của cùng ứng dụng phải chia sẻ session, tất cả phải dùng cùng namespace, cookie resolver, serializer và timeout. Nếu hai ứng dụng không nên chia sẻ session, namespace và cookie cần được tách rõ.

## 13. Cấu hình repository: kiểm tra bean thực tế

Spring Boot auto-configuration và annotation-based configuration có thể chọn repository theo phiên bản và thuộc tính. Một số phiên bản có cấu hình indexed riêng, ví dụ `@EnableRedisIndexedHttpSession`; các phiên bản hoặc cấu hình khác có thể đăng ký indexed repository qua auto-configuration.

Nguyên tắc:
- Không trộn nhiều annotation bật Redis HTTP session cùng lúc.
- Không tự khai báo thêm repository nếu auto-configuration đã tạo một bean.
- Kiểm tra bean `SessionRepository` và class thực tế lúc khởi động.
- Nếu cần principal lookup, xác nhận bean thực thi `FindByIndexNameSessionRepository`.
- Kiểm tra Redis namespace và `RedisSerializer`.
- Đồng bộ cấu hình trên tất cả application instances.

Có thể viết startup assertion hoặc integration test để xác nhận repository type. Điều này giúp phát hiện khi một thay đổi dependency hoặc Boot property vô tình chuyển từ indexed sang basic repository.

## 14. Concurrent session control phụ thuộc principal lookup

Spring Security có thể dùng `SessionRegistry` để quản lý session theo principal. Khi Spring Session được dùng với repository indexed, `SpringSessionBackedSessionRegistry` có thể kết nối registry với `FindByIndexNameSessionRepository`.

Điều này hỗ trợ:
- Tìm session hiện tại của principal.
- Giới hạn số session đồng thời.
- Đánh dấu hoặc thu hồi session theo policy.
- Hiển thị các session của một người dùng.

Nếu dùng repository cơ bản không có principal index, các use case này không thể được đáp ứng trực tiếp bằng principal lookup. Có thể xây một index riêng, nhưng khi đó ứng dụng tự chịu trách nhiệm đồng bộ, cleanup và consistency.

Lưu ý: principal index giúp tra cứu session; nó không tự làm thao tác kiểm tra số phiên và tạo session mới trở thành transaction nguyên tử. Hai login đồng thời vẫn có thể race nếu admission không được điều phối.

## 15. Thu hồi session theo principal

Với indexed repository, ứng dụng có thể tìm session của một principal rồi xóa những session cần thu hồi:

```java
Map<String, ? extends Session> sessions =
        indexedRepository.findByPrincipalName(principalName);

sessions.keySet().forEach(indexedRepository::deleteById);
```

Đây là ví dụ đơn giản cho luồng quản trị. Trong production, cần:
- Kiểm tra quyền người gọi.
- Giới hạn số lượng session xử lý.
- Ghi audit event an toàn.
- Xử lý lỗi từng lần xóa và retry có kiểm soát.
- Không log session ID nguyên vẹn.
- Xác nhận request mới với cookie cũ bị từ chối.
- Xem xét race khi session mới được tạo đồng thời với thao tác thu hồi.

Nếu cần thu hồi tất cả session kể cả session vừa được tạo trong lúc vòng lặp đang chạy, cần coordinator/versioning hoặc một cơ chế revocation mạnh hơn việc chụp snapshot index một lần.

## 16. Khi nào chọn RedisSessionRepository cơ bản?

Chọn repository cơ bản khi:
- Ứng dụng chỉ cần resolve session theo ID từ cookie.
- Không cần tìm tất cả session theo principal.
- Không dùng concurrent-session control dựa trên principal lookup.
- Không cần API liệt kê session theo username.
- Không cần các index phụ hoặc lifecycle behavior chỉ có ở indexed implementation.
- Muốn mô hình lưu trữ đơn giản hơn và giảm metadata phụ.

Ví dụ phù hợp: một ứng dụng web đơn giản có nhiều instance sau load balancer, session chỉ được đọc qua cookie session ID và logout bằng session hiện tại.

Trước khi chọn, xác nhận các yêu cầu về session events, expiration, WebSocket cleanup và audit. Nếu các yêu cầu này phụ thuộc implementation indexed, repository cơ bản có thể không đáp ứng.

## 17. Khi nào chọn RedisIndexedSessionRepository?

Chọn repository indexed khi:
- Cần `findByPrincipalName` hoặc `findByIndexNameAndIndexValue`.
- Cần quản lý nhiều session theo người dùng.
- Dùng Spring Security concurrent session control qua `SpringSessionBackedSessionRegistry`.
- Cần hiển thị/thu hồi session theo principal.
- Cần các index/lifecycle event được implementation này cung cấp.
- Có khả năng cấu hình Redis keyspace notifications và vận hành cleanup tương ứng.

Đổi lại, cần quản lý index resolver, principal consistency, Redis notifications, event loss, stale index và chi phí metadata. Không chọn indexed chỉ vì “nhiều tính năng hơn”; chọn khi use case cần.

## 18. Bảng quyết định nhanh

| Nhu cầu | Basic repository | Indexed repository |
|---|---|---|
| Lưu session ngoài JVM | Có | Có |
| Khôi phục theo session ID | Có | Có |
| Tra cứu session theo principal | Không | Có |
| Danh sách thiết bị đăng nhập | Cần tự xây thêm | Hỗ trợ qua index |
| Concurrent session registry dựa trên principal | Không trực tiếp | Có thể tích hợp |
| Thu hồi session theo principal | Cần index/coordinator riêng | Có thể tra cứu rồi xóa |
| Metadata và thao tác Redis | Ít hơn | Nhiều hơn |
| Principal index cleanup | Không có principal index tích hợp | Có |
| Cấu hình event/notification | Theo khả năng implementation | Cần kiểm tra và cấu hình indexed lifecycle |
| Vận hành | Đơn giản hơn | Cần theo dõi index/event/cleanup |

## 19. Kiểm thử contract của hai repository

Có thể viết cùng một contract test cho các thao tác session cơ bản:
1. Tạo session.
2. Đặt attribute.
3. Lưu.
4. Đọc lại bằng ID.
5. Cập nhật.
6. Lưu lại và đọc lại.
7. Xóa.
8. Xác nhận không còn session.

Sau đó bổ sung test riêng cho indexed repository:
- Session được index theo principal.
- `findByPrincipalName` trả đúng session ID.
- Session bị xóa thì principal lookup không còn trả session hợp lệ.
- Session hết hạn và index được cleanup theo semantics của implementation.
- Principal thay đổi thì index cũ/mới được xử lý đúng.
- Redis keyspace notifications được cấu hình.
- Event listener nhận sự kiện cần thiết.

Test basic repository không nên assert principal lookup vì API đó không thuộc contract. Ngược lại, test indexed repository phải xác minh index thực sự được cập nhật chứ không chỉ kiểm tra `findById`.

## 20. Integration test với Redis thật

Dùng Redis Testcontainers hoặc Redis test instance tương đương để kiểm tra repository thật. Không thay repository bằng `MapSessionRepository` rồi kết luận đã kiểm tra Redis.

Một test indexed nên:
- Xác nhận bean repository là indexed implementation.
- Tạo session với `SecurityContext` hoặc index attribute phù hợp.
- Lưu session.
- Truy vấn theo principal.
- Xóa session.
- Xác nhận principal lookup không còn session hợp lệ.
- Kiểm tra event/expiration behavior với keyspace notifications.
- Dọn dữ liệu test theo namespace riêng.

Nếu chỉ tạo session mà không gắn principal hoặc không có resolver phù hợp, principal index có thể không được tạo. Test cần xác minh fixture chứa đúng dữ liệu mà resolver mong đợi.

## 21. Vận hành Redis keyspace notifications

Indexed repository có thể cần notification flags phù hợp để nhận delete/expiration event. Ví dụ thường gặp:

```text
notify-keyspace-events Egx
```

Trong môi trường Redis managed, ứng dụng có thể không có quyền `CONFIG SET`. Khi đó, cấu hình notification ở tầng hạ tầng và dùng cấu hình Spring Session tương ứng, chẳng hạn `ConfigureRedisAction.NO_OP`, nếu phiên bản yêu cầu ứng dụng không tự thay đổi Redis config.

Không cấp quyền CONFIG rộng cho runtime user chỉ để bật notification. Theo dõi trạng thái subscription, event processing và số lượng stale index. Nếu event bị mất, cần reconciliation có phạm vi.

Với Redis Cluster, xác minh behavior subscription theo phiên bản Spring Session/Spring Data Redis; không mặc định mọi node event đều được broadcast đến subscriber đang kết nối một node.

## 22. Hiệu năng: đo thay vì phỏng đoán

Các chỉ số cần so sánh:
- Redis commands/request khi create, save, delete.
- Số key và dung lượng trung bình cho mỗi session.
- Latency p50/p95/p99 của `findById` và `save`.
- Latency của principal lookup.
- Số session trong index và stale member count.
- Cleanup duration và event processing delay.
- CPU/network Redis khi session update nhiều.
- Connection pool saturation.
- Tỷ lệ lỗi serializer và repository.

Benchmark nên dùng cùng số session, payload, TTL, concurrency và hardware. Với indexed repository, cần mô phỏng principal index thực tế; benchmark chỉ lưu session không có principal có thể không đo được chi phí index đầy đủ.

Không đưa username hoặc session ID làm metric label vì cardinality và nguy cơ lộ dữ liệu. Dùng operation, repository type, environment và namespace class.

## 23. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Session đọc theo ID được nhưng principal lookup rỗng | Repository basic hoặc index resolver không tìm được principal | Kiểm tra repository type và resolver |
| Một số session không có index | SecurityContext/principal không được lưu hoặc custom principal chưa được hỗ trợ | Kiểm tra object graph và IndexResolver |
| Index còn session ID cũ | Event cleanup trễ/mất hoặc delete không qua repository | Kiểm tra notifications, listener và reconciliation |
| Concurrent session control không hoạt động | Registry không dùng indexed repository hoặc principal index không có | Kiểm tra `SpringSessionBackedSessionRegistry` và repository bean |
| Redis báo lỗi cấu hình notification | Runtime user không có quyền CONFIG | Cấu hình ở hạ tầng và dùng NO_OP phù hợp |
| Dung lượng Redis tăng nhanh | Nhiều session/index hoặc cleanup trễ | Đo key count, TTL, event lag và index residue |
| Hai ứng dụng ghi đè session nhau | Namespace/cookie/serializer dùng chung ngoài dự kiến | Tách namespace và cookie hoặc định nghĩa hợp đồng chia sẻ rõ |

## 24. Checklist lựa chọn và triển khai

- Xác định ứng dụng chỉ cần lookup theo session ID hay cần principal lookup.
- Nếu chỉ cần session ID, cân nhắc `RedisSessionRepository` để giảm cấu trúc phụ.
- Nếu cần principal index, dùng `RedisIndexedSessionRepository` phù hợp phiên bản.
- Xác nhận bean repository thực tế trong Spring context.
- Cấu hình namespace và cookie nhất quán trên các instance.
- Cấu hình serializer tương thích với mọi node.
- Cấu hình `IndexResolver` nếu principal không theo Spring Security mặc định.
- Bật Redis keyspace notifications theo yêu cầu implementation indexed.
- Theo dõi event processing, stale index và cleanup.
- Dùng API repository để xóa session, tránh xóa key nội bộ tùy tiện.
- Kiểm thử create/find/save/delete cho cả hai implementation.
- Kiểm thử principal lookup, logout và expiration riêng cho indexed repository.
- Đánh giá race của concurrent login; index không thay thế admission transaction.
- Benchmark bằng payload, session count và concurrency gần production.
- Không log cookie, session ID nguyên vẹn hoặc SecurityContext.

## 25. Kết luận

`RedisSessionRepository` phù hợp khi ứng dụng cần lưu session trong Redis và khôi phục theo session ID, với mô hình đơn giản và ít metadata phụ. `RedisIndexedSessionRepository` phù hợp khi ứng dụng cần tìm session theo principal, quản lý nhiều phiên đăng nhập, tích hợp `SpringSessionBackedSessionRegistry` hoặc dùng lifecycle/index behavior mà implementation cung cấp.

Chỉ mục mang lại khả năng truy vấn bổ sung nhưng tạo thêm thao tác ghi, dung lượng, cấu hình keyspace notifications và công việc cleanup. Hãy chọn repository theo use case, xác nhận implementation được Spring Boot thực sự tạo ra, kiểm thử principal resolver và lifecycle trên Redis thật, đồng thời nhớ rằng index không tự bảo đảm admission nguyên tử hoặc biến session thành transaction nghiệp vụ.

