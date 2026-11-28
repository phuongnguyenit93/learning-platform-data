# ReactiveFindByIndexNameSessionRepository và tra cứu theo principal

Trong ứng dụng Spring WebFlux dùng Spring Session Redis, session được lưu trong Redis và được truy cập qua API reactive. Ngoài việc tìm session bằng session ID, một số nghiệp vụ cần tìm tất cả phiên của một người dùng: hiển thị các phiên đăng nhập, giới hạn số phiên đồng thời hoặc thu hồi phiên khi người dùng đăng xuất từ xa. ReactiveFindByIndexNameSessionRepository cung cấp hợp đồng reactive để tra cứu session theo một chỉ mục, phổ biến nhất là principal name.

Repository trả kết quả dưới dạng Mono<Map<String, S>>, trong đó key của map là session ID và value là session tương ứng. Vì thao tác là reactive, mã ứng dụng cần compose publisher bằng map, flatMap, flatMapMany hoặc các toán tử Reactor khác, không gọi block() trong request pipeline.

## 1. Tra cứu theo session ID và tra cứu theo principal

Tra cứu bằng session ID phù hợp khi request đã mang cookie và ứng dụng cần tải đúng một phiên:

- Trình duyệt gửi cookie chứa session ID.
- WebSessionIdResolver lấy ID từ request.
- Repository tìm session theo ID.
- WebFlux sử dụng WebSession để đọc hoặc cập nhật thuộc tính.

Tra cứu theo principal giải quyết một câu hỏi khác: người dùng này đang có những session nào? Principal thường là tên định danh ổn định của người dùng đã xác thực, ví dụ username hoặc subject được hệ thống xác thực cung cấp.

Ví dụ một người dùng đăng nhập trên laptop, điện thoại và một trình duyệt khác. Mỗi thiết bị có thể giữ session ID riêng. Tra cứu theo principal giúp backend tìm các phiên đó mà không cần biết cookie của từng thiết bị.

| Kiểu tra cứu | Đầu vào | Kết quả thường dùng |
| --- | --- | --- |
| Theo session ID | Một session ID từ request hoặc luồng quản trị | Một session hoặc không tìm thấy |
| Theo principal | Tên principal đã xác thực | Tập các session đang được index cho principal đó |

Không nhầm principal với session ID. Principal xác định người dùng hoặc danh tính đã xác thực; session ID xác định một phiên cụ thể của người dùng đó. Một principal có thể có nhiều session ID cùng lúc.

## 2. ReactiveFindByIndexNameSessionRepository là gì?

ReactiveFindByIndexNameSessionRepository<S> là interface của Spring Session mở rộng khả năng của ReactiveSessionRepository. Ngoài các thao tác reactive cơ bản như tạo, tìm, lưu và xóa session, interface này cung cấp phương thức tra cứu bằng tên index và giá trị index.

Các API chính:

- findByIndexNameAndIndexValue(indexName, indexValue): tìm các session có giá trị của index được chỉ định.
- findByPrincipalName(principalName): phương thức tiện ích để tìm theo chỉ mục principal name.

Kết quả là Mono<Map<String, S>>. Map có key là session ID; value là đối tượng session. Nếu không có session phù hợp, repository phát ra map rỗng theo hợp đồng của implementation, thay vì yêu cầu ứng dụng chặn luồng để chờ kết quả.

Chỉ mục principal name có tên chuẩn:

~~~java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
~~~

Hằng số này giúp tránh gõ chuỗi index tùy ý. Khi cần tra cứu principal, ưu tiên findByPrincipalName() vì phương thức diễn đạt đúng mục đích và giảm phụ thuộc vào tên index.

## 3. Reactive Redis repository và chỉ mục principal

Spring Session Data Redis có repository reactive được thiết kế để lưu session trên Redis. Với phiên bản hỗ trợ indexed reactive repository, implementation thường được cung cấp dưới tên ReactiveRedisIndexedSessionRepository và triển khai ReactiveFindByIndexNameSessionRepository.

Repository lưu session và duy trì dữ liệu chỉ mục để có thể tìm các phiên theo principal. Khi session được tạo, cập nhật hoặc xóa, repository cần cập nhật trạng thái index tương ứng. Cấu trúc Redis key và chi tiết lưu trữ nội bộ là implementation detail, có thể thay đổi theo phiên bản Spring Session.

Vì vậy:

- Dùng API repository để tra cứu; không tự ghép tên Redis key nội bộ.
- Không dùng lệnh KEYS hoặc quét Redis thủ công để tìm phiên của một người dùng.
- Đảm bảo mọi instance dùng cùng Redis deployment, namespace và cấu hình serializer.
- Xác nhận repository thực tế có hỗ trợ reactive index lookup ở phiên bản dependency đang chạy.
- Không giả định mọi ReactiveSessionRepository đều hỗ trợ tra cứu theo principal; cần đúng interface indexed.

Tên class, package, cách Spring Boot auto-configure và khả năng của reactive indexed repository phụ thuộc phiên bản Spring Session. Hãy kiểm tra dependency và API của phiên bản dự án thay vì sao chép cấu hình từ một release khác.

## 4. Principal name được đưa vào index như thế nào?

Để tra cứu theo principal, repository phải biết principal nào gắn với một session. Trong ứng dụng Spring Security, thông tin xác thực thường được lưu trong SecurityContext, và security context có thể được lưu trong WebSession thông qua cơ chế lưu trữ context của Spring Security WebFlux.

Spring Session có thể dùng PrincipalNameIndexResolver để đọc tên principal từ thuộc tính security context đã được lưu trong session. Khi resolver xác định được tên principal, repository cập nhật chỉ mục để ánh xạ principal đó đến session ID.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Người dùng xác thực thành công"] --> B["Spring Security tạo Authentication"]
    B --> C["SecurityContext được lưu trong WebSession"]
    C --> D["PrincipalNameIndexResolver đọc principal"]
    D --> E["Reactive Redis indexed repository"]
    E --> F[("Redis: session và principal index")]
    G["findByPrincipalName(name)"] --> E
    E --> H["Mono<Map<sessionId, session>>"]
~~~

Nếu ứng dụng không dùng Spring Security hoặc lưu danh tính theo một cấu trúc khác, repository có thể không tự suy ra principal. Khi đó cần cấu hình index resolver phù hợp hoặc lưu thuộc tính principal theo hợp đồng mà resolver nhận biết.

Không coi việc có thuộc tính userId bất kỳ trong session là đủ để index tự động. Resolver phải biết chính xác thuộc tính nào chứa principal và cách chuyển giá trị đó thành chuỗi index.

## 5. Tra cứu các session của principal

Ví dụ một service sử dụng interface reactive để lấy session ID cho một principal:

~~~java
import java.util.Set;
import org.springframework.session.ReactiveFindByIndexNameSessionRepository;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class PrincipalSessionLookupService {

    private final ReactiveFindByIndexNameSessionRepository<?> sessions;

    PrincipalSessionLookupService(
            ReactiveFindByIndexNameSessionRepository<?> sessions) {
        this.sessions = sessions;
    }

    Mono<Set<String>> findSessionIds(String principalName) {
        return sessions.findByPrincipalName(principalName)
            .map(indexedSessions -> Set.copyOf(indexedSessions.keySet()));
    }
}
~~~

findByPrincipalName() trả về một Mono chứa map. Ví dụ trên lấy các key của map để có tập session ID nội bộ. Trong API quản trị, không nên trả session ID thô cho frontend hoặc ghi chúng vào log. Hãy dùng ID nội bộ để thực hiện thao tác backend và trả về metadata an toàn như thiết bị, thời điểm đăng nhập hoặc trạng thái phiên nếu ứng dụng có lưu các thông tin đó.

Nếu cần đọc các thuộc tính của session, có thể xử lý các value trong map:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

Mono<List<SessionSummary>> findSessions(String principalName) {
    return sessions.findByPrincipalName(principalName)
        .map(indexedSessions -> indexedSessions.values().stream()
            .map(session -> new SessionSummary(
                session.getCreationTime(),
                session.getLastAccessedTime(),
                session.getMaxInactiveInterval()
            ))
            .toList()
        );
}
~~~

Ví dụ minh họa cách ánh xạ metadata. Kiểu session thực tế và các method thời gian cần được kiểm tra theo generic type của repository và phiên bản Spring Session đang dùng. Không đưa toàn bộ thuộc tính session vào response; chỉ trả các trường cần cho giao diện quản lý phiên.

## 6. Tra cứu bằng tên index và giá trị index

findByIndexNameAndIndexValue() cho phép truy vấn theo index khác nếu repository hỗ trợ. Principal name là trường hợp phổ biến, nhưng hệ thống có thể có index tùy chỉnh, chẳng hạn tenant hoặc loại danh tính.

Ví dụ:

~~~java
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.ReactiveFindByIndexNameSessionRepository;
import org.springframework.session.Session;
import reactor.core.publisher.Mono;

class GenericIndexedSessionLookup<S extends Session> {

    private final ReactiveFindByIndexNameSessionRepository<S> sessions;

    GenericIndexedSessionLookup(
            ReactiveFindByIndexNameSessionRepository<S> sessions) {
        this.sessions = sessions;
    }

    Mono<Map<String, S>> findByPrincipal(String principalName) {
        return sessions.findByIndexNameAndIndexValue(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
        );
    }
}
~~~

Ví dụ dùng generic S để giữ đúng kiểu session của repository được inject. Nếu đã có findByPrincipalName(), dùng phương thức đó sẽ rõ ý định hơn.

Không tự chọn một chuỗi index bất kỳ rồi giả định Redis repository tự duy trì nó. Một index chỉ có thể được tra cứu đúng khi resolver tạo ra giá trị index và repository duy trì ánh xạ đó trong suốt vòng đời session.

## 7. Tùy chỉnh principal index resolver

Trong ứng dụng có cách lưu principal riêng, có thể cần một IndexResolver tùy chỉnh. Resolver nhận session và trả về map gồm tên index cùng giá trị index. Ví dụ minh họa:

~~~java
import java.util.Collections;
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.IndexResolver;
import org.springframework.session.Session;

class ApplicationPrincipalIndexResolver implements IndexResolver<Session> {

    @Override
    public Map<String, String> resolveIndexesFor(Session session) {
        String principalName =
            session.getAttribute("APP_PRINCIPAL_NAME");
        if (principalName == null || principalName.isBlank()) {
            return Collections.emptyMap();
        }

        return Map.of(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
        );
    }
}
~~~

Resolver trên giả định ứng dụng đã ghi APP_PRINCIPAL_NAME vào session. Nếu Spring Security đã dùng resolver mặc định để lấy principal từ SecurityContext, thay resolver đó bằng resolver chỉ đọc thuộc tính riêng có thể làm mất index mặc định. Khi tùy chỉnh, phải giữ hoặc kết hợp đầy đủ logic mà ứng dụng cần.

Giá trị index nên:

- Ổn định trong suốt vòng đời session.
- Được chuẩn hóa nhất quán giữa mọi instance.
- Không chứa password, access token hoặc bí mật.
- Không thay đổi theo cách viết hoa/thường nếu nghiệp vụ coi các giá trị đó là cùng một principal.
- Có chính sách xử lý khi người dùng đổi tên đăng nhập hoặc danh tính liên kết.

Nếu principal thay đổi, repository cần cập nhật index cũ và index mới theo API được hỗ trợ. Không chỉ sửa thuộc tính session mà bỏ qua cơ chế cập nhật index.

## 8. Kết hợp với Spring Security WebFlux

Trong ứng dụng Spring Security WebFlux, Authentication đại diện cho danh tính đã xác thực. Security context thường được lưu vào WebSession thông qua WebSessionServerSecurityContextRepository hoặc cơ chế security context repository đã cấu hình.

Để findByPrincipalName() hoạt động:

1. Request đăng nhập phải hoàn tất xác thực thành công.
2. SecurityContext cần được lưu vào WebSession.
3. Index resolver phải đọc được principal name từ session.
4. Reactive Redis repository phải duy trì index cho session đó.
5. Tra cứu phải dùng đúng principal name mà resolver đã ghi.

Nếu ứng dụng dùng custom ServerSecurityContextRepository, cần xác nhận security context có được lưu trong WebSession và resolver có thể đọc được nó. Nếu security context chỉ nằm trong một kho khác hoặc trong Reactor Context của request hiện tại mà không được lưu vào session, principal index có thể không được tạo.

Không lấy principal từ query parameter hoặc request body để tra cứu session của người khác. Giá trị principal dùng trong chức năng quản trị phải được xác định từ Authentication của người gọi và phải được kiểm tra quyền truy cập. Người dùng thông thường chỉ được xem hoặc thu hồi phiên của chính họ; thao tác quản trị trên principal khác cần quyền riêng.

## 9. Hiển thị danh sách phiên đăng nhập

Một chức năng quản lý thiết bị có thể dùng principal lookup để lấy các phiên và hiển thị thông tin không nhạy cảm:

- Thời điểm tạo phiên.
- Thời điểm truy cập gần nhất.
- Thông tin thiết bị hoặc tên trình duyệt nếu ứng dụng đã lưu và đã kiểm soát dữ liệu đầu vào.
- Trạng thái phiên hiện tại.
- Một nhãn do ứng dụng gán, ví dụ “Máy tính cá nhân”.

Không phải repository nào cũng tự lưu thông tin thiết bị. Nếu cần hiển thị, ứng dụng có thể ghi một DTO nhỏ vào session lúc đăng nhập hoặc lưu metadata phiên trong một bảng nghiệp vụ riêng. Cần tránh lưu user-agent đầy đủ nếu không có nhu cầu và chính sách lưu trữ phù hợp.

Ví dụ service có thể trả về summary:

~~~java
import java.time.Duration;
import java.time.Instant;

record SessionSummary(
    Instant createdAt,
    Instant lastAccessedAt,
    Duration maxInactiveInterval
) {}
~~~

Tạo summary từ session values rồi trả về publisher. Không trả toàn bộ session attributes, vì chúng có thể chứa SecurityContext, thông tin nội bộ hoặc dữ liệu nhạy cảm.

## 10. Thu hồi một phiên hoặc tất cả phiên của principal

Sau khi tìm được các session theo principal, ứng dụng có thể thu hồi một phiên cụ thể bằng session ID hoặc xóa tất cả phiên thuộc principal. Reactive repository cung cấp các thao tác xóa session theo ID thông qua ReactiveSessionRepository.

Ví dụ thu hồi tất cả phiên được tìm thấy:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Void> revokeAllSessions(String principalName) {
    return sessions.findByPrincipalName(principalName)
        .flatMapMany(indexedSessions ->
            Flux.fromIterable(indexedSessions.keySet())
        )
        .flatMap(sessions::deleteById)
        .then();
}
~~~

Đây là luồng minh họa. Trong mã thực tế, kiểu repository phải cung cấp deleteById() và các thao tác xóa cần được thực hiện theo API reactive của phiên bản đang dùng. flatMap có thể chạy nhiều thao tác xóa đồng thời; nếu muốn giới hạn tải Redis, dùng flatMap với concurrency phù hợp hoặc xử lý tuần tự bằng concatMap.

Thu hồi phiên cần kiểm tra quyền:

- Người dùng chỉ được thu hồi session thuộc principal của chính mình, trừ khi có quyền quản trị.
- Nếu thu hồi một session cụ thể, xác nhận session ID thuộc tập kết quả của principal được phép quản lý.
- Không nhận principal tùy ý từ client rồi xóa session mà không xác thực quyền.
- Không trả session ID thô trong API response hoặc log.

Kết quả tra cứu là snapshot tại thời điểm đọc. Một session mới có thể được tạo sau khi truy vấn hoàn tất; do đó revokeAllSessions() ở trên không tạo bảo đảm nguyên tử rằng mọi phiên hiện tại và tương lai đều bị thu hồi. Nếu nghiệp vụ yêu cầu vô hiệu hóa mọi phiên kể cả đăng nhập đồng thời, cần thêm cơ chế như thay đổi phiên bản xác thực của người dùng, thu hồi token/session generation hoặc khóa thao tác đăng nhập trong thời gian thu hồi.

## 11. Tính nhất quán của index và vòng đời session

Index phải được cập nhật khi session được tạo, thay đổi principal hoặc xóa. Trong hệ thống phân tán, việc đọc và cập nhật có thể chịu ảnh hưởng của độ trễ mạng, Redis failover, cấu hình serializer và phiên bản ứng dụng.

Một số tình huống cần kiểm tra:

- Session chưa có principal index vì được tạo trước khi người dùng xác thực.
- SecurityContext được lưu sau khi session đã được tạo, nên index chỉ xuất hiện sau thao tác lưu tiếp theo.
- Session bị xóa hoặc hết hạn nhưng index chưa được dọn đúng lúc do lỗi hoặc độ trễ.
- Principal name được chuẩn hóa khác nhau giữa các instance.
- Một phiên bản ứng dụng mới thay đổi cách resolver trích xuất principal trong khi phiên bản cũ vẫn chạy.

Không nên tự xóa Redis key index theo mẫu nội bộ để sửa dữ liệu. Dùng repository API và quy trình đối soát được kiểm soát. Khi index có vẻ sai, xác minh session gốc và resolver trước, sau đó kiểm tra phiên bản Spring Session và cấu hình Redis.

## 12. Hiệu năng và giới hạn của truy vấn

Tra cứu theo principal có thể trả về nhiều session nếu người dùng đăng nhập trên nhiều thiết bị hoặc hệ thống không giới hạn số phiên. Kết quả map có kích thước tăng theo số session được index cho principal đó.

Để tránh tạo tải không cần thiết:

- Giới hạn số phiên cho mỗi principal theo yêu cầu nghiệp vụ.
- Không gọi principal lookup trên mọi request nếu chỉ cần kiểm tra session hiện tại.
- Chỉ truy vấn khi cần quản lý thiết bị, thu hồi phiên hoặc kiểm tra chính sách số phiên.
- Trả metadata tối thiểu thay vì serialize toàn bộ session.
- Giới hạn concurrency khi xóa nhiều session.
- Đặt timeout và xử lý lỗi Redis phù hợp.
- Theo dõi số session trả về, độ trễ lookup và số thao tác xóa.

Nếu một principal có số lượng session bất thường, kiểm tra nguyên nhân tạo session lặp lại, cookie không được gửi lại, timeout quá dài hoặc client liên tục tạo session mới. Không giải quyết vấn đề chỉ bằng cách tăng tài nguyên Redis mà không tìm nguyên nhân.

## 13. Kiểm thử reactive principal lookup

Nên kiểm thử trên repository reactive thực tế, không chỉ mock interface. Các kịch bản quan trọng:

| Kịch bản | Thao tác | Kết quả cần xác nhận |
| --- | --- | --- |
| Chưa có session | Tra cứu principal chưa từng đăng nhập | Map rỗng |
| Một session | Xác thực một lần và lưu session | Map chứa session ID đó |
| Nhiều session | Đăng nhập cùng principal ở nhiều client | Map chứa các session tương ứng |
| Không có principal index | Tạo session không xác thực | Không được giả định session xuất hiện trong principal lookup |
| Logout một session | Xóa một session ID | Phiên đó không còn trong kết quả sau khi cập nhật index |
| Logout tất cả | Tra cứu rồi xóa mọi session trả về | Các session đã tìm được bị thu hồi |
| Principal thay đổi | Cập nhật danh tính/index theo quy trình | Tra cứu cũ và mới phản ánh chính sách đã chọn |
| Redis lỗi hoặc timeout | Ngắt kết nối trong test | Publisher báo lỗi; ứng dụng xử lý lỗi có kiểm soát |

Với WebFlux, có thể dùng StepVerifier để kiểm tra publisher:

~~~java
StepVerifier.create(repository.findByPrincipalName("user-42"))
    .assertNext(sessions -> {
        assertThat(sessions).hasSize(1);
    })
    .verifyComplete();
~~~

Ví dụ cần có repository test được khởi tạo và session fixture đã được lưu trước khi chạy assertion. Nếu principal lookup không tìm thấy session, kiểm tra cả việc SecurityContext đã được lưu và index resolver đã trích xuất đúng principal hay chưa.

Kiểm thử HTTP bằng WebTestClient cũng cần xác nhận luồng đăng nhập tạo cookie, request tiếp theo dùng cookie đó và repository tìm thấy session theo principal. Mock WebSession có thể kiểm tra controller nhưng không xác nhận Redis index được ghi đúng.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| findByPrincipalName() trả map rỗng | Session chưa có principal index hoặc principal name không khớp | Kiểm tra SecurityContext, resolver và cách chuẩn hóa tên |
| Tra cứu theo ID hoạt động nhưng theo principal không có kết quả | Repository không hỗ trợ index hoặc index chưa được tạo | Dùng indexed reactive repository và kiểm tra cấu hình |
| Chỉ tìm thấy một trong nhiều phiên | Các phiên được tạo bằng luồng xác thực khác nhau hoặc index không đồng nhất | Kiểm tra từng session và cách resolver xử lý |
| Sau logout session vẫn xuất hiện trong danh sách | Xóa chưa hoàn tất, event/index cập nhật trễ hoặc thao tác xóa lỗi | Theo dõi publisher, repository và trạng thái Redis |
| Gọi lookup làm event loop bị chặn | Dùng block() hoặc truy cập đồng bộ | Compose Mono/Flux và dùng reactive Redis driver |
| Thu hồi nhầm phiên của người khác | Tin principal do client gửi mà không kiểm tra quyền | Lấy principal từ Authentication và kiểm tra authorization |
| Lookup chậm khi principal có nhiều session | Map kết quả lớn hoặc Redis đang chịu tải | Giới hạn phiên, phân trang ở lớp nghiệp vụ nếu phù hợp và đo tải |

Khi chẩn đoán, kiểm tra theo thứ tự: repository được inject có đúng interface indexed reactive không, session đã lưu hay chưa, principal có được ghi vào SecurityContext/WebSession không, resolver có trích xuất đúng tên không và index trong Redis có được duy trì không.

## 15. Nguyên tắc sử dụng

- Dùng ReactiveFindByIndexNameSessionRepository khi cần tra cứu session theo principal hoặc index.
- Dùng findByPrincipalName() cho trường hợp phổ biến; dùng findByIndexNameAndIndexValue() khi có index khác được hỗ trợ.
- Hiểu kết quả Mono<Map<String, S>> là map có key session ID.
- Bảo đảm principal được lưu trong session và index resolver nhận diện được nó.
- Với Spring Security WebFlux, xác nhận SecurityContext được lưu vào WebSession theo cách tương thích với resolver.
- Compose reactive publisher; không gọi block() trong request pipeline.
- Bảo vệ chức năng xem/thu hồi phiên bằng authorization ở backend.
- Không trả hoặc log session ID và toàn bộ session attributes.
- Kiểm thử nhiều session, logout, index cập nhật và lỗi Redis trên repository thật.

ReactiveFindByIndexNameSessionRepository bổ sung khả năng tìm các phiên theo chỉ mục trong mô hình reactive. Với principal lookup, repository trả về các session ID và session tương ứng để ứng dụng quản lý thiết bị, giới hạn phiên hoặc thu hồi phiên từ xa. Kết quả chỉ chính xác khi principal được trích xuất và index được duy trì nhất quán; do đó cần phối hợp đúng Spring Security WebFlux, resolver, Redis repository và quyền truy cập nghiệp vụ, đồng thời giữ toàn bộ luồng xử lý ở dạng reactive.
