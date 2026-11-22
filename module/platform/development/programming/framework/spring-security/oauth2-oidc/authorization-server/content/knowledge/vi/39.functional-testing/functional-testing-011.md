# Kiểm thử lưu trữ bền vững, restart và phối hợp nhiều instance

Một Authorization Server có thể chạy tốt trong một lần khởi động nhưng vẫn thất bại khi triển khai production: authorization code biến mất sau restart, refresh token đã thu hồi lại được chấp nhận, consent không được chia sẻ giữa các node hoặc hai instance cùng xử lý thành công một authorization code. Những lỗi này thường xuất hiện khi dữ liệu được lưu trong bộ nhớ cục bộ, cấu hình các node không đồng nhất hoặc thao tác cập nhật trạng thái không được bảo vệ trước truy cập đồng thời.

Với Spring Authorization Server, kiểm thử chức năng cần chứng minh dữ liệu client, authorization, consent và trạng thái token được lưu bền vững; luồng có thể tiếp tục qua lần khởi động mới; và nhiều instance có thể cùng phục vụ một issuer mà không tạo ra trạng thái mâu thuẫn. Bài học này tập trung vào cách thiết kế fixture, kịch bản và tiêu chí đạt cho các kiểm thử đó.

## 1. Phân biệt các nhóm trạng thái cần kiểm thử

Spring Authorization Server sử dụng các abstraction lưu trữ riêng cho từng nhóm dữ liệu. Kiểm thử cần xác minh đúng kho lưu trữ mà ứng dụng thực sự dùng:

| Thành phần | Vai trò | Điều cần xác minh |
|---|---|---|
| RegisteredClientRepository | Lưu cấu hình OAuth2 client | Client, redirect URI, grant type, scope và phương thức xác thực còn nguyên sau restart |
| OAuth2AuthorizationService | Lưu authorization và trạng thái token | Authorization code, access token, refresh token và metadata được đọc đúng từ instance khác |
| OAuth2AuthorizationConsentService | Lưu consent của principal đối với client | Consent mới, thay đổi và gỡ bỏ được phản ánh nhất quán |
| JWKSource / kho khóa | Cung cấp khóa ký và public key | Các instance dùng cùng key ring và token cũ vẫn xác minh được |
| HTTP session / Spring Session | Giữ trạng thái đăng nhập trình duyệt | Phiên người dùng được chia sẻ nếu luồng đăng nhập có thể đi qua nhiều node |
| Cấu hình issuer và endpoint | Xác định danh tính Authorization Server | Discovery metadata, issuer và endpoint không lệch giữa các instance |

Không gộp tất cả dữ liệu trên vào một khái niệm “session”. Authorization, consent và RegisteredClient có vòng đời lưu trữ riêng. Phiên đăng nhập trình duyệt cũng có thể được quản lý bởi Spring Security hoặc Spring Session. Một kiểm thử OAuth2 token thành công sau restart chưa chứng minh phiên đăng nhập của người dùng cũng được chia sẻ giữa các node.

## 2. Cấu hình kho lưu trữ bền vững cho môi trường kiểm thử

Trong môi trường production, ứng dụng thường dùng JDBC hoặc implementation tùy chỉnh để lưu dữ liệu. Spring Authorization Server cung cấp các implementation JDBC phổ biến:

- **JdbcRegisteredClientRepository** cho RegisteredClient.
- **JdbcOAuth2AuthorizationService** cho authorization và token.
- **JdbcOAuth2AuthorizationConsentService** cho consent.

Ví dụ cấu hình các repository dùng chung một DataSource:

~~~java
@Configuration
public class AuthorizationStorageConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository clients) {
        return new JdbcOAuth2AuthorizationService(jdbcTemplate, clients);
    }

    @Bean
    OAuth2AuthorizationConsentService consentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository clients) {
        return new JdbcOAuth2AuthorizationConsentService(jdbcTemplate, clients);
    }
}
~~~

Các schema SQL đi kèm Spring Authorization Server cần được áp dụng theo đúng phiên bản thư viện đang dùng. Trong dự án thực tế, nên quản lý thay đổi schema bằng Flyway hoặc Liquibase để mọi instance triển khai cùng một cấu trúc database. Không để từng node tự chạy một bộ script không được kiểm soát khi khởi động.

Ví dụ kiểm thử tích hợp có thể dùng Testcontainers để chạy database thật trong vòng đời test:

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthorizationPersistenceIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // Các bài test gọi endpoint thật và kiểm tra trạng thái qua repository.
}
~~~

Ví dụ trên minh họa cách cấp database cho test. Cần áp dụng migration/schema của ứng dụng, seed client kiểm thử và cấu hình khóa ký dùng riêng cho test. Không dùng dữ liệu production hoặc private key production trong Testcontainers.

H2 có thể hữu ích cho kiểm thử nhanh, nhưng không nên là bằng chứng duy nhất cho các tình huống nhiều instance. Khác biệt về transaction isolation, khóa hàng, kiểu dữ liệu, unique constraint và cú pháp SQL có thể khiến hành vi trên H2 khác PostgreSQL, MySQL hoặc database production. Hãy chạy các kiểm thử lưu trữ và đồng thời quan trọng trên cùng loại database với môi trường triển khai.

## 3. Kiểm thử dữ liệu còn nguyên sau khi khởi động lại

Một kiểm thử restart có ý nghĩa phải giữ nguyên database giữa hai lần chạy ứng dụng. Nếu test xóa database, tái tạo schema hoặc seed lại mọi dữ liệu trước khi kiểm tra, test không chứng minh được tính bền vững.

Có thể tổ chức kịch bản thành hai pha:

1. Khởi động ứng dụng lần thứ nhất, tạo RegisteredClient, authorization, consent và trạng thái token cần kiểm thử.
2. Đóng application context hoặc dừng process, sau đó khởi động ứng dụng lần thứ hai với cùng database và cùng cấu hình issuer/key ring; truy vấn lại dữ liệu và gọi các endpoint cần thiết.

Ví dụ khung kiểm thử repository qua hai service instance độc lập:

~~~java
@Test
void authorizationSurvivesServiceRecreation() {
    RegisteredClientRepository clients =
            new JdbcRegisteredClientRepository(jdbcTemplate);

    OAuth2AuthorizationService firstService =
            new JdbcOAuth2AuthorizationService(jdbcTemplate, clients);

    OAuth2Authorization authorization = createTestAuthorization(clients);
    firstService.save(authorization);

    // Tạo service mới nhưng giữ nguyên database và RegisteredClient.
    OAuth2AuthorizationService secondService =
            new JdbcOAuth2AuthorizationService(jdbcTemplate, clients);

    OAuth2Authorization restored =
            secondService.findById(authorization.getId());

    assertThat(restored).isNotNull();
    assertThat(restored.getRegisteredClientId())
            .isEqualTo(authorization.getRegisteredClientId());
}
~~~

Đoạn mã là khung minh họa; **createTestAuthorization** phải tạo authorization hợp lệ theo fixture của ứng dụng, bao gồm RegisteredClient và principal tương ứng. Việc tạo service mới kiểm tra lớp lưu trữ. Để kiểm tra restart thực sự, cần có thêm bài test khởi động hai application context hoặc hai process tuần tự với cùng database, không chỉ tạo hai object service trong một JVM.

Các nhóm dữ liệu cần xác minh sau restart:

- RegisteredClient vẫn có cùng client ID, grant type, redirect URI, authentication method và scope.
- Consent vẫn có cùng principal, client và authority đã chấp thuận.
- Authorization có thể được tìm lại bằng ID hoặc token phù hợp.
- Metadata token, thời hạn, trạng thái invalidated và thuộc tính liên quan được đọc chính xác.
- Khóa ký và public key được phục hồi đúng, bao gồm key ID.
- Issuer và discovery metadata giữ đúng giá trị đã triển khai.

Không chỉ kiểm tra bản ghi tồn tại. Hãy kiểm tra hành vi sau restart: authorization code còn dùng được nếu chưa hết hạn và chưa sử dụng; refresh token đã bị vô hiệu hóa vẫn bị từ chối; consent bị gỡ không xuất hiện lại; token JWT cũ vẫn được xác minh nếu khóa tương ứng còn được tin cậy.

## 4. Kiểm thử authorization code và refresh token qua restart

Authorization code là credential dùng một lần và có thời hạn ngắn. Một kịch bản quan trọng là tạo authorization code trước restart, sau đó đổi code lấy token sau restart. Điều này chứng minh authorization state được lưu trong kho bền vững thay vì bộ nhớ của instance.

Luồng kiểm thử:

1. Seed RegisteredClient hỗ trợ authorization code và PKCE.
2. Thực hiện authorization request với redirect URI, state và PKCE challenge hợp lệ.
3. Đăng nhập principal kiểm thử và hoàn tất consent theo cấu hình.
4. Lấy authorization code từ redirect URI trong môi trường test.
5. Dừng ứng dụng nhưng giữ database và key ring.
6. Khởi động lại cùng issuer và cấu hình.
7. Gửi token request chứa code, redirect URI và PKCE verifier hợp lệ.
8. Xác minh token endpoint trả token hợp lệ và authorization code không thể được sử dụng lần thứ hai.

Nếu authorization code đã hết hạn trong thời gian restart, kết quả từ chối là đúng nhưng không kiểm chứng được khả năng phục hồi code. Hãy kiểm soát clock hoặc đặt TTL đủ dài cho bài test, đồng thời có một test riêng xác minh code hết hạn bị từ chối.

Đối với refresh token, tạo token, thực hiện rotation hoặc thu hồi theo cấu hình, restart ứng dụng rồi thử dùng lại. Nếu rotation được bật và chính sách không cho phép reuse, refresh token cũ phải tiếp tục bị từ chối sau restart. Refresh token mới phải được chấp nhận theo thời hạn và trạng thái đã lưu.

Không giả định mọi cấu hình refresh token đều có cùng hành vi. Test phải phản ánh chính sách reuse/rotation thực tế của client và Authorization Server. Nếu cấu hình cho phép reuse, tiêu chí của bài test phải theo đúng chính sách đó; nếu cấu hình xoay vòng token, phải kiểm tra token cũ bị vô hiệu hóa và token mới được lưu.

## 5. Kiểm thử consent và thao tác thu hồi qua restart

Consent cần được kiểm tra bằng cả trạng thái lưu trữ và kết quả của luồng authorization. Một bản ghi consent còn trong database nhưng ứng dụng không đọc được do sai RegisteredClient ID hoặc principal name vẫn là lỗi chức năng.

Các kịch bản cơ bản:

| Kịch bản | Trước restart | Sau restart |
|---|---|---|
| Consent mới | Người dùng chấp thuận scope cho client | Kho consent trả về đúng authority |
| Consent thay đổi | Scope được thêm hoặc bỏ | Kết quả đọc phản ánh tập quyền mới |
| Consent bị gỡ | Consent được remove | Consent không xuất hiện lại |
| Token bị revoke | Authorization lưu trạng thái invalidated | Introspection hoặc thao tác sử dụng token phản ánh trạng thái đã revoke |
| Authorization bị xóa | Bản ghi bị remove theo nghiệp vụ | Instance mới không tìm thấy authorization đã xóa |

Ví dụ, khi người dùng gỡ consent của client A, sau restart hãy gửi authorization request mới từ client A và xác minh ứng dụng áp dụng lại chính sách consent. Nếu client B có consent độc lập, trạng thái của client B không được thay đổi.

Khi kiểm tra thu hồi, phân biệt token hết hạn với token bị invalidated. Một token hết hạn có thể không active nhưng không chứng minh thao tác revoke đã được lưu. Test nên kiểm tra trạng thái invalidated hoặc hành vi endpoint introspection/revocation phù hợp với thiết kế.

## 6. Kiểm thử phối hợp giữa hai instance

Trong triển khai nhiều instance, mỗi node phải sử dụng cùng issuer, cùng RegisteredClient data, cùng authorization/consent store và một key ring nhất quán. Một node không được giữ bản sao in-memory riêng làm nguồn sự thật cho trạng thái OAuth2.

Sơ đồ luồng kiểm thử:

~~~mermaid
flowchart TD
    C[OAuth2 Client] --> LB[Load Balancer]
    LB --> A[Authorization Server A]
    LB --> B[Authorization Server B]
    A --> DB[(Shared Database)]
    B --> DB
    A --> K[Shared KMS / Key Ring]
    B --> K
    A --> J[Same Issuer and JWKS]
    B --> J
    R[Resource Server] --> J
~~~

Thực hiện các kịch bản xuyên node:

- Instance A tạo authorization; instance B tìm thấy authorization đó.
- Instance A phát hành token; instance B có thể introspect hoặc xử lý revoke theo trạng thái đã lưu.
- Instance A cập nhật consent; instance B đọc được thay đổi ngay theo mức nhất quán mà hệ thống cam kết.
- Token do A ký được xác minh bằng public key mà B và resource server công bố/tiêu thụ.
- Token do B ký cũng phải có key ID thuộc key ring được quản lý chung.
- Instance A khởi động lại; instance B tiếp tục phục vụ các authorization đã lưu trước đó.
- Instance B khởi động lại; trạng thái và hành vi của A không bị thay đổi.

Có thể triển khai hai application context hoặc hai process với cổng HTTP khác nhau, cùng trỏ tới một database test. Gửi request tạo trạng thái vào A rồi request đọc hoặc sử dụng trạng thái vào B. Đây là bằng chứng thực tế hơn việc gọi trực tiếp hai repository trong cùng một context.

Issuer cần giữ nguyên giữa các node. Trong môi trường production, các instance thường nằm sau cùng một hostname/load balancer; không để mỗi node tự công bố issuer chứa hostname hoặc port riêng. Discovery metadata và JWKS phải có nội dung tương thích, không phụ thuộc node nào trả lời request.

## 7. Kiểm thử cạnh tranh và tính chất dùng một lần

Nhiều instance cùng truy cập một database chưa tự động bảo đảm các thao tác nhạy cảm được thực hiện đúng một lần. Hai request có thể cùng đọc authorization code ở trạng thái còn hiệu lực trước khi một request kịp lưu trạng thái đã sử dụng.

Kiểm thử cạnh tranh nên bao gồm:

| Tài nguyên | Tình huống đồng thời | Kết quả mong đợi |
|---|---|---|
| Authorization code | Hai instance đổi cùng một code gần như đồng thời | Tối đa một request thành công |
| Refresh token có rotation | Hai request dùng cùng refresh token cũ | Hành vi đúng theo chính sách reuse/rotation; không tạo trạng thái mâu thuẫn |
| Consent | Hai request cập nhật tập authority | Không mất cập nhật ngoài chính sách đã định nghĩa |
| Revocation | Hai request revoke cùng token | Trạng thái cuối cùng nhất quán; audit không tạo kết luận sai |
| RegisteredClient | Cập nhật client khi node khác đang đọc | Node đọc được cấu hình nhất quán theo cơ chế cache/version |

Ví dụ cách đồng bộ hai request trong test:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

Callable<Response> redeemSameCode = () -> {
    ready.countDown();
    start.await();
    return tokenClient.exchangeAuthorizationCode(code, verifier);
};

Future<Response> first = executor.submit(redeemSameCode);
Future<Response> second = executor.submit(redeemSameCode);

ready.await();
start.countDown();

Response a = first.get();
Response b = second.get();

assertThat(List.of(a.isSuccessful(), b.isSuccessful()))
        .containsExactlyInAnyOrder(true, false);
~~~

Đây là pseudocode để minh họa cách tạo tranh chấp. **tokenClient**, **Response** và việc quản lý executor là fixture của test. Trong bài test thật, gửi hai HTTP request độc lập tới hai instance và xác minh response theo giao thức, thường là một token response thành công và một lỗi invalid grant. Không dùng mock repository vì mục tiêu là kiểm tra transaction và hành vi database thực.

Nếu cả hai request đều thành công, cần điều tra cách lưu trạng thái authorization, transaction isolation, locking và điều kiện cập nhật. Có thể cần bảo vệ thao tác bằng khóa hàng, optimistic locking/version, cập nhật có điều kiện hoặc cơ chế đồng bộ phù hợp với database. Không kết luận rằng JDBC repository mặc định đã bảo đảm mọi race condition của ứng dụng nếu chưa kiểm tra phiên bản và cách triển khai cụ thể.

Với refresh token, tiêu chí phụ thuộc cấu hình reuse. Nếu token cũ phải bị vô hiệu hóa sau rotation, test đồng thời phải chứng minh hệ thống không cấp hai nhánh refresh độc lập từ cùng một token cũ. Nếu reuse được bật, hãy xác minh đúng chính sách đó và khả năng phát hiện replay nếu ứng dụng yêu cầu.

## 8. Kiểm thử khóa ký và JWKS giữa các node

Nhiều instance phải tạo và xác minh token theo một key ring được quản lý chung. Nếu mỗi node tạo một cặp khóa mới khi khởi động, token phát hành bởi node A có thể không được xác minh khi resource server hoặc node B chỉ biết public key khác.

Các kiểm thử cần có:

1. Khởi động A và B; xác minh JWKS trả về tập public key tương thích ở cả hai node.
2. Yêu cầu A phát hành JWT; kiểm tra chữ ký bằng public key tương ứng từ JWKS.
3. Yêu cầu B phát hành JWT; xác minh tương tự.
4. Restart A rồi kiểm tra token do A phát hành trước restart vẫn xác minh được nếu token còn hạn và khóa vẫn được tin cậy.
5. Restart B và lặp lại kiểm tra với token do B phát hành.
6. Rotation khóa trong môi trường test: public key mới được công bố trước khi token mới được ký; public key cũ vẫn được giữ trong thời gian cần thiết.
7. Sau khi ngừng công bố khóa cũ theo kế hoạch, xác minh resource server cập nhật JWKS và xử lý token cũ theo chính sách.

Không dùng test chỉ kiểm tra endpoint JWKS trả HTTP 200. Hãy parse JWK Set, kiểm tra kid, kty, use, thuật toán và thực hiện xác minh chữ ký của JWT thực tế. Private key không được xuất hiện trong response JWKS hoặc log test.

Nếu sử dụng KMS/HSM, test tích hợp phải xác minh từng instance có quyền ký đúng key ID và public key công bố khớp với khóa trong thiết bị. Có thể dùng fake KMS trong unit test, nhưng cần ít nhất một bài kiểm thử tích hợp với cơ chế quản lý khóa của môi trường gần production.

## 9. Kiểm thử session trình duyệt khi load balancing

Lưu authorization vào database không đồng nghĩa phiên đăng nhập của người dùng được chia sẻ giữa các node. Nếu request đăng nhập vào instance A nhưng request tiếp theo tới B, B cần khôi phục được session và SecurityContext theo kiến trúc ứng dụng.

Nếu ứng dụng dùng HTTP session, hãy kiểm tra cấu hình Spring Session và kho lưu trữ session dùng chung, chẳng hạn Redis. Nếu sử dụng sticky session, phải kiểm tra cả trường hợp node đang giữ session bị mất và load balancer chuyển request sang node khác. Sticky session có thể giảm chuyển node nhưng không thay thế cơ chế phục hồi session khi node lỗi.

Kịch bản test nên mô phỏng:

- Người dùng bắt đầu authorization request qua A.
- Luồng đăng nhập tiếp tục qua B.
- SecurityContext, trạng thái đăng nhập và dữ liệu cần thiết vẫn được khôi phục.
- Consent và authorization được ghi vào kho dùng chung.
- Sau khi restart một node, người dùng có thể tiếp tục hoặc được yêu cầu đăng nhập lại đúng theo chính sách session.

Nếu hệ thống cố ý yêu cầu đăng nhập lại sau khi node lỗi, test phải xác minh luồng quay lại authorization request an toàn, giữ đúng state/nonce và không cấp token cho request bị sửa đổi. Không coi việc phải đăng nhập lại là lỗi nếu đó là chính sách bảo mật đã định nghĩa.

## 10. Kiểm thử lỗi database, replica lag và phục hồi kết nối

Một ứng dụng nhiều instance cần xử lý lỗi database rõ ràng. Kiểm thử nên mô phỏng database tạm thời không truy cập được, transaction rollback, connection pool cạn, deadlock và replica lag nếu kiến trúc có read replica.

Các tình huống quan trọng:

- Không thể lưu authorization: token endpoint không trả thành công giả khi trạng thái bắt buộc chưa được lưu.
- Transaction rollback: dữ liệu không ở trạng thái nửa chừng, ví dụ token đã được ghi nhưng metadata invalidation chưa cập nhật.
- Database phục hồi: connection pool kết nối lại và node tiếp tục hoạt động theo chính sách retry.
- Read replica chậm: node không đọc nhầm trạng thái cũ sau khi thao tác revoke hoặc cập nhật authorization vừa được commit.
- Deadlock hoặc lock timeout: lỗi được xử lý có giới hạn, có log và không retry vô hạn gây khuếch đại tải.
- Schema migration: các node không chạy phiên bản ứng dụng tương thích với schema chưa được nâng cấp hoặc rollback.

Đối với thao tác token exchange, refresh và revocation, đọc dữ liệu từ replica có độ trễ có thể gây ra kết quả bảo mật sai. Nếu hệ thống dùng read replica, cần định nghĩa rõ thao tác nào phải đọc từ primary hoặc cần read-your-writes consistency. Test phải đo hành vi thực tế sau commit, thay vì chỉ xác nhận replica eventually nhận dữ liệu.

Không dùng retry mù cho token request. Một request có thể đã commit nhưng response bị mất trên đường mạng. Nếu client gửi lại authorization code hoặc refresh token, server cần áp dụng đúng semantics của credential dùng một lần và chính sách replay. Test cần mô phỏng trường hợp timeout sau khi server đã commit để xác minh trạng thái cuối cùng và hành vi request retry.

## 11. Bộ kiểm thử chức năng đề xuất

Một bộ test có thể được chia thành các tầng để cân bằng tốc độ và độ tin cậy:

| Tầng | Thành phần | Mục tiêu |
|---|---|---|
| Unit test | Mapper, validator, logic chính sách, event handler | Kiểm tra quy tắc nhỏ, nhanh |
| Repository integration | JDBC service với database thật | Kiểm tra mapping, truy vấn, transaction và schema |
| Restart integration | Hai application context/process tuần tự | Kiểm tra dữ liệu sống sót qua restart |
| Multi-instance integration | Hai server cùng database và key ring | Kiểm tra đọc/ghi xuyên node |
| Concurrency test | Request đồng thời tới hai instance | Kiểm tra code/refresh dùng một lần và cập nhật trạng thái |
| Failure test | Database/KMS/network bị gián đoạn | Kiểm tra rollback, retry, failover và phục hồi |
| End-to-end test | Client, Authorization Server và Resource Server | Kiểm tra luồng OAuth2/OIDC hoàn chỉnh |

Danh sách test tối thiểu nên gồm:

- [ ] RegisteredClient được đọc đúng sau khi tạo application context mới.
- [ ] Consent được lưu, thay đổi và gỡ bỏ vẫn đúng sau restart.
- [ ] Authorization code được tạo trước restart có thể đổi sau restart khi vẫn hợp lệ.
- [ ] Authorization code đã dùng không thể đổi lần thứ hai, kể cả khi request đến node khác.
- [ ] Refresh token rotation và trạng thái invalidation còn nguyên sau restart.
- [ ] Token bị revoke ở A bị B nhìn thấy theo mức nhất quán đã cam kết.
- [ ] Token do A phát hành được xác minh bằng JWKS sau khi A restart.
- [ ] Token do B phát hành được xác minh bởi Resource Server dùng cùng issuer.
- [ ] Hai request đồng thời không thể cùng sử dụng một authorization code.
- [ ] Hai node không ghi đè consent hoặc cấu hình client theo cách mất cập nhật ngoài ý muốn.
- [ ] Session trình duyệt được chia sẻ hoặc phục hồi đúng theo chính sách.
- [ ] Database lỗi, rollback, replica lag và reconnect không tạo trạng thái authorization sai.
- [ ] Không có private key, client secret, authorization code hoặc token nguyên bản trong log test.

## 12. Tiêu chí hoàn thành và cách đọc kết quả

Một bài kiểm thử chỉ có giá trị khi nêu rõ dữ liệu đầu vào, điểm quan sát và trạng thái mong đợi. Ví dụ “test restart thành công” chưa đủ rõ. Nên ghi cụ thể: tạo consent cho principal P và client C, đóng process A, mở process B cùng database, truy vấn consent và xác minh tập authority bằng đúng giá trị đã lưu.

Khi test thất bại, phân loại nguyên nhân theo lớp:

- **Persistence**: dữ liệu không được ghi, mapping sai hoặc schema không tương thích.
- **Lifecycle**: trạng thái authorization không được cập nhật đúng khi code được dùng, token bị revoke hoặc refresh.
- **Coordination**: node đọc cache cũ, dùng key ring khác hoặc không chia sẻ session.
- **Concurrency**: hai request cùng vượt qua kiểm tra trạng thái trước khi cập nhật.
- **Infrastructure**: connection pool, DNS, load balancer, KMS/HSM hoặc replica gây lỗi.

Lưu lại instance ID, request correlation ID, thời điểm, database transaction hoặc authorization ID nội bộ trong báo cáo test. Không đưa raw token hoặc credential vào artifact kiểm thử. Dùng test data riêng và dọn dữ liệu sau mỗi kịch bản để các test không phụ thuộc thứ tự chạy.

Khi các kiểm thử restart, multi-instance và concurrency đều đạt trên database và cấu hình khóa gần production, đội phát triển có bằng chứng rằng Authorization Server duy trì trạng thái OAuth2/OIDC qua vòng đời triển khai. Điều này giúp phát hiện sớm lỗi chỉ xuất hiện khi node thay đổi, ứng dụng khởi động lại hoặc nhiều request cùng tác động lên một credential.

