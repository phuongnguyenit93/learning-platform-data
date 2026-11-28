# Khởi động lại một nút và kiểm chứng trạng thái phiên còn hay mất

Khi ứng dụng Spring Session chạy trên nhiều instance, một nút có thể được khởi động lại để triển khai phiên bản mới, thay cấu hình, vá lỗi hoặc phục hồi sau sự cố. Câu hỏi quan trọng là: người dùng đang đăng nhập qua nút đó có còn phiên sau khi nút khởi động lại không?

Câu trả lời phụ thuộc vào nơi lưu session. Nếu Spring Session lưu phiên trong Redis hoặc JDBC dùng chung và độc lập với vòng đời của instance ứng dụng, việc khởi động lại một node thường không làm mất session đã được lưu thành công. Request tiếp theo có thể được một node khác xử lý và khôi phục cùng HttpSession từ repository. Nếu ứng dụng chỉ dùng session trong bộ nhớ của JVM hoặc một store tạm thời gắn với node, phiên có thể mất khi process dừng.

Cần kiểm chứng bằng một bài test có kiểm soát: tạo và lưu session qua node A, xác nhận node B đọc được cùng trạng thái, dừng A, tiếp tục request qua B, khởi động lại A rồi xác nhận trạng thái vẫn còn. Bài test cũng phải phân biệt session mất thật với lỗi cookie, namespace, serializer, TTL, routing hoặc dữ liệu chưa kịp ghi khi request kết thúc.

## 1. Điều gì tồn tại sau khi một node dừng?

Một session có thể được nhìn thành hai phần:

- **Định danh ở client:** thường là cookie chứa session ID, ví dụ `SESSION`.
- **Trạng thái ở server:** các thuộc tính HttpSession và metadata được lưu trong SessionRepository.

Khi browser gửi cookie, Spring Session filter dùng session ID để tải session từ repository. Nếu repository nằm ngoài JVM của node, session có thể được khôi phục ở một instance khác.

| Nơi lưu session | Khi restart một node | Khi restart toàn bộ ứng dụng |
|---|---|---|
| HttpSession mặc định trong bộ nhớ container | Session của node đó mất | Session của tất cả node mất |
| Map repository trong JVM | Mất dữ liệu của process | Mất dữ liệu của tất cả process |
| Redis dùng chung và bền vững độc lập với node | Session đã lưu thường còn | Session còn nếu Redis vẫn giữ dữ liệu |
| JDBC database dùng chung | Session đã lưu thường còn | Session còn nếu database và schema vẫn nguyên vẹn |
| Redis/database ephemeral gắn với vòng đời test | Phụ thuộc container/store có bị xóa hay không | Có thể mất nếu môi trường test bị tạo lại |

Một repository chia sẻ giúp trạng thái phiên độc lập với node ứng dụng. Tuy nhiên, nó không bảo đảm session tồn tại vô thời hạn. TTL, logout, cleanup, eviction, database reset hoặc thay đổi format serialization vẫn có thể làm session mất hiệu lực.

## 2. Phân biệt restart node với xóa kho session

Restart một process ứng dụng và restart/xóa session store là hai sự kiện khác nhau.

Ví dụ với Redis:

    Browser
       |
       | SESSION cookie
       v
    Load balancer
       |
       +------> Node A
       |          |
       |          +----+
       |               |
       +------> Node B  |
                  |     |
                  +-----v
                 Redis dùng chung

Khi Node A dừng, Redis vẫn giữ các key session. Node B có thể tải session theo ID từ cookie. Nếu Redis cũng bị xóa dữ liệu, khởi động lại hoặc chuyển sang namespace khác, session có thể không còn.

Với JDBC, ứng dụng có thể dừng trong khi các hàng SPRING_SESSION và SPRING_SESSION_ATTRIBUTES vẫn tồn tại trong database. Node B tải session bằng cùng datasource và table/schema configuration.

Bài kiểm thử phải ghi nhận riêng trạng thái node và trạng thái store. Nếu test đồng thời restart ứng dụng và Redis/database, kết quả không chứng minh khả năng chịu restart của một node ứng dụng.

## 3. Điều kiện để session tồn tại qua restart

Các điều kiện cơ bản:

1. Session đã được lưu thành công trước khi node dừng.
2. Repository nằm ngoài process của node và vẫn hoạt động.
3. Node còn lại dùng cùng repository, namespace, database/schema và serialization tương thích.
4. Browser gửi đúng session cookie.
5. Session chưa hết idle timeout hoặc absolute lifetime theo policy ứng dụng.
6. Session chưa bị logout, revoke hoặc cleanup.
7. Dữ liệu session vẫn có thể deserialize bởi phiên bản ứng dụng đang chạy.
8. Không có chính sách eviction hoặc cleanup xóa session trước khi request tiếp theo tới.

Chỉ dùng Redis/JDBC trong dependency không đủ. Cần xác nhận Spring Session thực sự đang thay HttpSession bằng repository dự kiến. Nếu ứng dụng vô tình dùng HttpSession mặc định, một bean Redis không tự động làm session được chia sẻ.

## 4. Cấu hình Redis repository dùng chung

Ví dụ cấu hình annotation cho Servlet application:

~~~java
@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    redisNamespace = "orders:prod:spring-session"
)
public class SessionConfiguration {
}
~~~

Mọi node của cùng một ứng dụng cần dùng cấu hình tương thích:

- Cùng Redis endpoint hoặc cùng Redis cluster.
- Cùng namespace.
- Cùng serialization strategy.
- Cùng chính sách timeout.
- Cùng cookie name và scope.
- Cùng cách cấu hình session events nếu ứng dụng phụ thuộc vào event.

Với Spring Boot, có thể dùng auto-configuration và property tương ứng của phiên bản đang dùng thay cho annotation. Tránh bật nhiều cấu hình session độc lập tạo nhiều filter/repository cạnh tranh.

Namespace phải ổn định giữa các node và giữa các lần triển khai tương thích. Nếu Node A dùng orders:prod:v1 còn Node B dùng orders:prod:v2, B sẽ không tìm thấy session do A tạo dù cả hai kết nối cùng Redis.

Redis không nên bị xóa hoặc tái tạo như một phần của restart node ứng dụng. Trong môi trường production, cần hiểu persistence, replication, failover và eviction policy của Redis riêng biệt với lifecycle ứng dụng.

## 5. Cấu hình JDBC repository dùng chung

Ví dụ cấu hình Servlet application dùng JDBC:

~~~java
@Configuration
@EnableJdbcHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    tableName = "SPRING_SESSION"
)
public class JdbcSessionConfiguration {
}
~~~

Mọi node cần trỏ đến database/schema và bảng tương thích. Cần xác nhận:

- Cùng database endpoint hoặc cùng cụm database.
- Cùng schema và table name.
- Bảng session và bảng attributes đã được tạo đúng phiên bản.
- Runtime user có quyền đọc/ghi/xóa cần thiết.
- Index và cleanup job hoạt động.
- Không có node nào trỏ nhầm sang database của môi trường khác.

Restart Node A không xóa các hàng session. Nhưng nếu deployment đồng thời chạy migration phá hủy bảng, đổi schema hoặc thay table name, Node B có thể không đọc được session. Quản lý schema cần tương thích với rolling deployment.

## 6. Cookie phải được giữ nguyên khi chuyển request sang node khác

Repository có thể còn session nhưng browser vẫn phải gửi đúng session ID. Khi kiểm thử failover, dùng cùng cookie jar qua mọi request.

Các yếu tố cookie cần xác nhận:

- Tên cookie, thường là SESSION hoặc tên đã cấu hình.
- Domain và Path.
- Secure khi chạy HTTPS.
- HttpOnly.
- SameSite.
- Cookie chưa bị xóa bởi response logout hoặc response khác.
- Cookie chưa hết Max-Age/Expires.

Không copy session ID vào log hoặc tài liệu test công khai. Nếu cần ghi nhận cùng một phiên trong test, có thể dùng cookie jar tự động và so sánh bằng dấu vết đã che hoặc hash chỉ dành cho test.

Cookie session ID và server-side TTL là hai thời hạn độc lập. Cookie còn tồn tại không có nghĩa repository còn session; repository còn session cũng không giúp browser khôi phục nếu cookie đã mất.

## 7. Cấu hình hai node trong bài kiểm thử

Một môi trường integration có thể chạy hai instance cùng artifact và cùng session store:

| Thành phần | Node A | Node B |
|---|---|---|
| Ứng dụng | Cùng build | Cùng build |
| Port | 8081 | 8082 |
| Session store | Redis/database dùng chung | Cùng Redis/database |
| Namespace | orders:test:spring-session | Giống Node A |
| Cookie | Cùng tên và scope | Cùng tên và scope |
| Node marker | A | B |

Node marker chỉ dùng để xác định request đã đi đến instance nào. Nó không được lưu thay cho session ID và không ảnh hưởng tới dữ liệu phiên.

Có thể dùng Docker Compose, test profile hoặc hai process Spring Boot. Store nên nằm trong service riêng để restart một app node không vô tình restart store. Nếu dùng Testcontainers, giữ container Redis/database sống xuyên suốt thao tác dừng và khởi động lại app node.

## 8. Tạo session probe an toàn cho integration test

Nên có endpoint test chỉ được bật trong profile integration-test. Endpoint tạo session, ghi một giá trị probe và trả về node marker. Browser/client tự giữ cookie được phát trong response.

Ví dụ:

~~~java
@RestController
@Profile("integration-test")
public class SessionProbeController {

    @Value("`{app.node-id}")
    private String nodeId;

    @PostMapping("/it/session")
    public Map<String, String> create(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("probe.value", "created-before-restart");
        session.setAttribute("probe.owner", "integration-test");

        return Map.of(
                "node", nodeId,
                "state", "created"
        );
    }

    @GetMapping("/it/session")
    public ResponseEntity<Map<String, String>> read(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(401).build();
        }

        Object value = session.getAttribute("probe.value");
        if (value == null) {
            return ResponseEntity.status(404).build();
        }

        return ResponseEntity.ok(Map.of(
                "node", nodeId,
                "value", value.toString()
        ));
    }
}
~~~

Endpoint không trả session ID. Cookie được quản lý bởi client test. Không đưa controller này vào production; profile integration-test cần bị loại khỏi artifact/deployment production hoặc bị khóa bằng cấu hình không thể bật nhầm.

Trong test thật, bảo vệ endpoint và dùng dữ liệu duy nhất theo test run để tránh hai test ghi đè cùng session attribute.

## 9. Kịch bản kiểm thử cơ bản: tạo ở A, đọc ở B

Trước khi dừng node, xác nhận repository dùng chung hoạt động:

1. Gửi POST /it/session đến Node A.
2. Client lưu cookie SESSION từ response.
3. Gửi GET /it/session đến Node B bằng cùng cookie.
4. Xác nhận Node B trả probe.value=created-before-restart.
5. Xác nhận node marker là B.

Nếu B đọc được giá trị vừa tạo ở A, điều đó chứng minh session được chia sẻ giữa hai instance tại thời điểm kiểm thử. Nếu B trả 401 hoặc 404, cần điều tra repository, namespace, cookie, serialization và thời điểm lưu trước khi thử restart.

Không chỉ kiểm tra HTTP 200. Phải kiểm tra giá trị thuộc tính, principal hoặc trạng thái cần bảo toàn. Một response 200 có thể được tạo từ session mới rỗng, không phải session cũ.

## 10. Đợi response hoàn tất trước khi dừng node

Với Servlet integration, Spring Session filter quản lý lưu session theo vòng đời request/response. Nếu dùng Redis với flush mode ON_SAVE, các thay đổi thường được ghi khi session được lưu trong quá trình hoàn tất response.

Do đó, test phải chờ response tạo/cập nhật session hoàn tất trước khi dừng node. Nếu kill process giữa lúc controller thay đổi thuộc tính và filter chưa kịp lưu, mất thay đổi cuối cùng không chứng minh repository chia sẻ không hoạt động; đó có thể là một write chưa hoàn tất.

Một trình tự đúng:

    POST /it/session tới Node A
             |
             v
    Controller cập nhật HttpSession
             |
             v
    Spring Session filter lưu phiên
             |
             v
    Response hoàn tất, cookie được nhận
             |
             v
    Test xác nhận trạng thái đọc được ở B
             |
             v
    Mới dừng Node A

Nếu ứng dụng dùng FlushMode.IMMEDIATE hoặc repository khác, hành vi ghi có thể khác. Dù vậy, hãy dùng response hoàn tất và một lần đọc xác nhận làm ranh giới đồng bộ trong test.

## 11. Dừng Node A trong khi Node B vẫn phục vụ

Sau khi xác nhận B đọc được session, dừng Node A:

- Với process local, gửi tín hiệu shutdown phù hợp.
- Với container, dừng hoặc restart đúng container A.
- Với Kubernetes, xóa pod A hoặc thực hiện rollout theo đúng selector.
- Không dừng Redis/database dùng chung.
- Không xóa volume hoặc network resource của session store.

Trong giai đoạn A dừng, load balancer cần loại A khỏi endpoint nhận traffic. Nếu Node B còn khỏe, request tiếp theo phải được chuyển đến B.

Kiểm tra readiness/liveness riêng: readiness quyết định node có nhận traffic hay không; liveness có thể kích hoạt restart khi process bị kẹt. Không dùng health check chỉ kiểm tra process mà bỏ qua khả năng kết nối repository nếu session store là dependency bắt buộc.

## 12. Đọc lại session trong lúc A dừng

Khi A đã dừng hoàn toàn:

1. Giữ nguyên cookie jar đã nhận khi tạo session.
2. Gửi GET /it/session trực tiếp tới Node B hoặc qua load balancer đã loại A.
3. Xác nhận response đến từ B.
4. Xác nhận probe.value vẫn là giá trị đã ghi.
5. Xác nhận principal và thuộc tính cần bảo toàn còn đúng nếu test dùng đăng nhập thật.

Nếu request thành công, session đã tồn tại độc lập với process A. Đây là kết quả chính của bài test.

Không dùng sticky session để vô tình gửi request trở lại A. Trong bài test, cần biết chắc backend xử lý request là B; nếu load balancer có affinity cookie, dùng route test có thể chỉ định node hoặc gọi trực tiếp port B.

## 13. Khởi động lại A và kiểm chứng lần nữa

Sau khi B đọc được session khi A dừng, khởi động lại A với cùng cấu hình:

- Cùng repository endpoint.
- Cùng namespace.
- Cùng cookie serializer và cookie name.
- Cùng schema/serializer tương thích.
- Cùng application session policy.

Khi A đã healthy và ready:

1. Gửi request có cùng cookie đến A.
2. Xác nhận A đọc được probe.value đã tạo trước khi restart.
3. Gửi tiếp request đến B.
4. Xác nhận B vẫn đọc được cùng trạng thái.
5. Kiểm tra không xuất hiện một session mới rỗng ngoài ý muốn.

Kết quả này chứng minh session đã được lưu trong store chung và có thể được khôi phục bởi process mới. Nếu chỉ B đọc được còn A không đọc được, so sánh cấu hình A sau restart với B, đặc biệt namespace, datasource, serializer và cookie handling.

## 14. Restart graceful và kill đột ngột là hai bài test khác nhau

Nên kiểm thử cả hai kiểu dừng:

| Kiểu dừng | Điều gì được kiểm tra? | Kỳ vọng |
|---|---|---|
| Graceful shutdown | Node ngừng nhận request mới, hoàn tất request đang xử lý theo thời gian drain | Session đã lưu vẫn còn |
| Abrupt kill | Process bị kết thúc ngay, không có cơ hội hoàn tất request | Session đã lưu trước đó vẫn còn; thay đổi đang ghi dở có thể mất |
| Container restart | Container app được thay mới, store độc lập vẫn chạy | Session đã commit trước restart vẫn còn |
| Node reboot | Hệ điều hành/process trên một máy dừng | Redis/JDBC độc lập vẫn còn nếu hạ tầng store không bị ảnh hưởng |

Graceful shutdown giảm nguy cơ mất các request đang xử lý. Nhưng nó không phải transaction bảo đảm mọi side effect đã hoàn tất. Abrupt kill có thể làm mất cập nhật đang nằm trong buffer hoặc chưa được ghi. Bài test cần phân biệt dữ liệu đã được xác nhận lưu với dữ liệu của request đang bay.

Không kết luận session storage bị lỗi chỉ vì một request bị cắt giữa chừng khi kill -9. Hãy tạo một session baseline đã lưu trước, rồi mới thực hiện abrupt restart.

## 15. Kiểm tra dữ liệu còn tồn tại trong Redis

Trong môi trường test, có thể quan sát namespace và TTL bằng Redis CLI hoặc công cụ quản trị được cấp quyền. Không đưa session ID thật vào log chia sẻ hoặc command history công khai.

Các điểm cần quan sát:

- Key thuộc namespace đúng.
- TTL còn dương trước khi session hết hạn.
- Node A và B dùng cùng namespace.
- Restart app node không xóa key session.
- Không có lệnh FLUSHDB/FLUSHALL trong lifecycle script của app.
- Eviction policy không loại bỏ session ngoài ý muốn.
- Redis restart/failover được test riêng nếu phạm vi yêu cầu.

Không dựa vào số lượng key thô để kết luận một session còn hợp lệ. Redis repository có thể dùng nhiều key cho session, expiration và index. Dùng repository API hoặc request thực tế để xác minh session còn được tải và kiểm tra expiration logic.

## 16. Kiểm tra dữ liệu còn tồn tại trong JDBC

Với JDBC, test có thể xác minh session qua request ở node khác và quan sát bảng bằng truy vấn chỉ đọc trong môi trường test.

Cần kiểm tra:

- Bản ghi session tồn tại trước và sau restart node.
- Bảng attributes chứa dữ liệu cần thiết.
- Expiry time chưa qua.
- A và B dùng cùng database/schema/table.
- Cleanup job không xóa phiên hợp lệ.
- Restart app không chạy script reset dữ liệu session.

Không chỉnh sửa trực tiếp bảng session để làm test pass. Truy vấn database chỉ nên phục vụ quan sát; thao tác lưu/xóa phải đi qua Spring Session repository để bảo đảm metadata và quan hệ dữ liệu nhất quán.

## 17. Sticky session có thể che giấu lỗi chia sẻ

Load balancer có thể bật session affinity hoặc sticky session, nghĩa là cùng một client luôn được gửi về node đã phục vụ request đầu tiên.

Sticky session có thể giảm chuyển node, nhưng nó không chứng minh Spring Session được chia sẻ. Nếu Node A dừng và request chuyển sang B, bài test mới thực sự kiểm chứng khả năng failover.

Cách test:

- Tắt affinity trong test nếu có thể; hoặc
- Gọi trực tiếp từng node bằng cùng cookie; hoặc
- Dùng cơ chế route test xác định backend.
- Kiểm tra response node marker để biết request thực sự đến đâu.

Không để cookie affinity của load balancer bị nhầm với cookie SESSION. Hai cookie có thể cùng tồn tại nhưng có vai trò khác nhau.

## 18. Kiểm tra session khi serializer hoặc phiên bản ứng dụng thay đổi

Sau restart, node mới có thể dùng build khác. Nếu thay đổi class được lưu trong session, serializer hoặc cấu trúc thuộc tính, process mới có thể không deserialize được session cũ.

Các tình huống cần kiểm thử:

- Node A và B cùng build.
- Node A build cũ, node B build mới trong rolling deployment.
- Thay đổi DTO session attribute nhưng giữ namespace.
- Thay đổi serializer.
- Thay đổi class package hoặc type metadata.
- Thay namespace hoặc cookie name.

Ưu tiên lưu kiểu dữ liệu ổn định, nhỏ và tương thích. Khi rolling deployment, các phiên bản cùng hoạt động cần đọc được session format mà phiên bản còn lại ghi. Nếu thay đổi không tương thích, phải có migration hoặc kế hoạch invalidate session có chủ đích.

Không đổi namespace theo từng build chỉ để tránh lỗi serializer nếu yêu cầu sản phẩm là giữ đăng nhập qua deployment. Cách đó thường khiến mọi phiên cũ trở nên vô hình với bản mới.

## 19. Kiểm tra TTL và thời gian chờ khi restart

Một session có thể mất hiệu lực đúng lúc node được restart vì TTL đã hết. Đây không phải mất dữ liệu do restart.

Bài test nên:

1. Cấu hình timeout đủ dài cho toàn bộ thời gian test.
2. Ghi lại thời điểm tạo và thời điểm cuối cùng session được truy cập.
3. Hoàn thành restart trong khoảng idle timeout.
4. Dùng cookie còn hiệu lực.
5. Kiểm tra absolute lifetime nếu ứng dụng có policy riêng.
6. Không để cleanup test xóa namespace trong khi test đang chạy.

Nếu test dùng timeout rất ngắn để tăng tốc, phải dùng clock hoặc test fixture phù hợp và xác nhận thời gian thực tế. Không suy luận từ sleep cố định vì scheduler, container startup và CI load có thể làm thời gian dao động.

## 20. Restart trong khi request đang xử lý

Đây là tình huống khác với restart sau khi session đã lưu. Nếu A dừng khi request đang cập nhật session:

- Request có thể không trả response.
- Cookie cập nhật có thể chưa tới browser.
- Spring Session filter có thể chưa gọi save.
- Repository write có thể đã thành công nhưng response bị mất.
- Client retry có thể gửi lại thao tác và gây side effect trùng.

Cần test riêng với một endpoint có barrier/delay chỉ trong profile test để dừng node ở các thời điểm xác định: trước khi cập nhật session, sau khi cập nhật nhưng trước response, và sau khi response hoàn tất.

Không dùng thao tác nghiệp vụ thật có side effect không thể đảo ngược cho test kill giữa request. Dùng probe state và idempotency key để có thể quan sát kết quả.

Nếu yêu cầu không mất cập nhật khi node chết giữa request, session store không thay thế transaction nghiệp vụ. Hãy dùng database transaction/outbox cho side effect quan trọng và thiết kế retry idempotent.

## 21. Kiểm thử logout và revoke trước/sau restart

Session còn trong Redis/JDBC không có nghĩa session phải còn hiệu lực sau logout. Bài test nên xác minh:

1. Tạo session và xác thực.
2. Logout qua node A.
3. Xác nhận response xóa cookie phù hợp.
4. Dùng cookie cũ gọi node B.
5. Xác nhận session không còn được chấp nhận.
6. Restart A hoặc B.
7. Thử lại cookie cũ và xác nhận vẫn bị từ chối.

Điều này kiểm tra logout thực sự xóa/revoke session ở store dùng chung. Nếu chỉ xóa cookie phía browser nhưng session record còn, một client giữ bản sao cookie cũ có thể tiếp tục sử dụng phiên.

Với remember-me, cần kiểm tra credential ghi nhớ riêng. Xóa HttpSession không nhất thiết thu hồi persistent remember-me token nếu logout flow không xử lý token đó.

## 22. Kiểm thử nhiều lần restart và rolling deployment

Một lần restart thành công chưa đủ để chứng minh hành vi ổn định. Có thể thực hiện rolling restart:

1. Tạo nhiều session test khác nhau.
2. Dừng A, kiểm tra B.
3. Khởi động A, đợi readiness.
4. Dừng B, kiểm tra A.
5. Khởi động B.
6. Kiểm tra tất cả session baseline còn hạn.
7. Lặp lại với node build mới nếu đang kiểm thử deployment.

Trong production, rolling deployment nên duy trì đủ số node ready để phục vụ request. Đừng dừng đồng thời mọi node nếu mục tiêu là chứng minh một node restart không ảnh hưởng người dùng.

Nếu dùng Kubernetes, kiểm tra readiness probe, terminationGracePeriodSeconds, preStop hook và rolling update strategy. Các giá trị cần đủ để request đang xử lý có thể hoàn tất; chúng không thay thế kiểm tra repository persistence.

## 23. Test với Spring Boot và Testcontainers

Một bài integration test có thể khởi chạy Redis trong Testcontainers và hai application context hoặc hai process ứng dụng dùng cùng Redis. Sau khi tạo session qua node A, đóng context/process A, giữ Redis container hoạt động, rồi gửi request bằng cùng cookie đến B.

Nguyên tắc test:

- Redis container có lifecycle dài hơn application node.
- Mỗi node dùng namespace giống nhau.
- Dùng cùng serializer và cookie serializer.
- Client giữ cookie qua các request.
- Chờ response hoàn tất trước khi đóng context.
- Đóng A không được đóng Redis.
- Xác nhận B đọc được giá trị baseline.
- Tạo lại A và xác nhận A cũng đọc được.

Nếu chỉ dùng @SpringBootTest với một ApplicationContext và một Map repository, test không mô phỏng được process restart với store bên ngoài. Nếu đóng rồi tạo lại context nhưng repository vẫn là cùng bean trong JVM test, cũng chưa chứng minh Redis/JDBC persistence.

Với JDBC, dùng database container độc lập với application context và giữ container sống qua restart context. Kiểm tra migration/schema ở cả hai node.

## 24. Kết quả mong đợi và cách diễn giải

| Quan sát | Diễn giải có khả năng |
|---|---|
| A tạo, B đọc được, A dừng, B vẫn đọc được | Session được lưu trong store dùng chung và độc lập với A |
| A tạo, B không đọc được | Sai store/namespace/cookie hoặc session chưa được lưu |
| B đọc được khi A sống nhưng không đọc được khi A dừng | Có thể B thực ra dùng local state, sticky routing che giấu hoặc A đang giữ store cục bộ |
| B đọc được khi A dừng, A mới khởi động không đọc được | Cấu hình A sau restart khác B hoặc serializer/schema không tương thích |
| Session mất sau một khoảng thời gian | TTL, absolute lifetime, cleanup hoặc eviction |
| Session còn trong store nhưng HTTP trả 401 | Cookie không được gửi, SecurityContext không deserialize, principal/account policy hoặc filter chain |
| Request trong lúc kill bị lỗi, nhưng baseline session còn | Request đang bay bị gián đoạn; persistence của session đã commit vẫn hoạt động |
| Logout ở A nhưng B vẫn chấp nhận cookie cũ | Logout không xóa/revoke store chung hoặc request stale ghi lại session |

Không phân loại mọi lỗi 401 là session bị mất. Kiểm tra repository lookup, cookie, Authentication và authorization thành từng bước.

## 25. Checklist thực hiện bài test

- [ ] Dùng Redis/JDBC store độc lập với process ứng dụng.
- [ ] Node A và B dùng cùng namespace/schema/table.
- [ ] Cùng cookie name, Domain, Path và serializer.
- [ ] Cùng timeout và session policy.
- [ ] Tạo session probe ở A và chờ response hoàn tất.
- [ ] Giữ cookie jar qua toàn bộ bài test.
- [ ] Xác nhận B đọc được cùng thuộc tính trước restart.
- [ ] Dừng A mà không dừng session store.
- [ ] Xác nhận B tiếp tục đọc được session khi A dừng.
- [ ] Khởi động lại A và chờ readiness.
- [ ] Xác nhận A và B đều đọc được session.
- [ ] Test riêng graceful shutdown và abrupt kill.
- [ ] Test riêng logout/revoke và session hết TTL.
- [ ] Kiểm tra sticky session không làm sai kết luận.
- [ ] Kiểm tra serializer/schema khi rolling version.
- [ ] Không ghi session ID hoặc cookie thô vào log.
- [ ] Không dùng endpoint probe trong production.

## 26. Chẩn đoán sự cố sau restart

Khi người dùng bị đăng xuất sau deployment, điều tra theo thứ tự:

1. **Node:** request mới đến node nào? Node đó đã ready chưa?
2. **Cookie:** browser có gửi đúng cookie không? Cookie có bị response khác xóa hoặc ghi đè không?
3. **Repository:** node mới có kết nối đúng Redis/database không?
4. **Namespace/schema:** có cùng namespace, database, schema và table name không?
5. **Session lookup:** repository có tìm thấy session ID không?
6. **Expiration:** session đã quá idle timeout hoặc absolute lifetime chưa?
7. **Serialization:** node mới có deserialize được thuộc tính cũ không?
8. **Security:** SecurityContext, account status hoặc authorization policy có từ chối không?
9. **Cleanup/eviction:** store có xóa hoặc eviction key không?
10. **Deployment:** có migration, reset volume, flush database hoặc đổi secret nào chạy cùng lúc không?

Thu thập timestamp, node marker, build version, repository latency và loại lỗi. Không ghi session ID đầy đủ. Nếu cần đối chiếu request, dùng correlation ID riêng.

## Kết luận

Restart một node ứng dụng không nên làm mất session đã được lưu trong Redis hoặc JDBC dùng chung và độc lập với process đó. Để chứng minh điều này, tạo session ở A, chờ response hoàn tất, xác nhận B đọc được bằng cùng cookie, dừng A, xác nhận B vẫn đọc được, rồi khởi động lại A và xác nhận cả hai node tiếp tục khôi phục cùng trạng thái. Bài test phải giữ store hoạt động, kiểm tra namespace/schema, serializer, cookie và TTL, đồng thời tách restart graceful khỏi kill đột ngột và request đang bay. Nếu session mất, hãy xác định nó mất ở client, repository, expiration, serialization hay security policy trước khi kết luận restart là nguyên nhân.

## Tài liệu tham khảo

- Spring Session Reference: https://docs.spring.io/spring-session/reference/
- Spring Session Redis Configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session JDBC Configuration: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Session HttpSession Integration: https://docs.spring.io/spring-session/reference/http-session.html
- Spring Boot Graceful Shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Testcontainers Documentation: https://java.testcontainers.org/
