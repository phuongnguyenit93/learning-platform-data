# Cách ly namespace và dữ liệu thử nghiệm giữa các ca kiểm thử

Spring Session lưu trạng thái phiên bên ngoài bộ nhớ của một request, thường trong Redis hoặc JDBC. Vì dữ liệu sống lâu hơn một test method và có thể được dùng bởi nhiều instance ứng dụng, test có nguy cơ đọc nhầm session do test trước tạo ra. Hai ca kiểm thử có thể dùng cùng cookie, cùng principal, cùng namespace hoặc cùng bảng session; khi đó kết quả phụ thuộc thứ tự chạy, chạy song song hay chạy lại sau lỗi.

Cách ly test cần được thiết kế ở nhiều lớp: kho dữ liệu, namespace của Spring Session, định danh test, cookie/session ID, dữ liệu phụ trợ và cleanup. Một namespace riêng giúp tách key của các nhóm test trong Redis; một schema hoặc database riêng giúp cô lập dữ liệu JDBC. Trong phạm vi một namespace, mỗi test vẫn cần principal và session ID riêng, đồng thời phải xóa dữ liệu do chính nó tạo ra. `@Transactional` hoặc `@DirtiesContext` không tự động dọn mọi dữ liệu session ở Redis/JDBC.

## 1. Vì sao session làm test bị phụ thuộc lẫn nhau?

Trong test không dùng Spring Session, một `MockHttpSession` có thể chỉ sống trong bộ nhớ của test. Khi bật Spring Session, `SessionRepositoryFilter` thay đổi cách `HttpSession` được lưu và khôi phục. Response có thể phát cookie chứa session ID; request tiếp theo dùng cookie đó để đọc session từ Redis/JDBC.

Nếu test A tạo session rồi kết thúc mà không xóa, test B có thể vô tình:

- Khôi phục SecurityContext đã đăng nhập của test A.
- Đọc cart, workflow hoặc attribute do test A để lại.
- Thấy session count lớn hơn dự kiến khi kiểm thử giới hạn đăng nhập đồng thời.
- Thất bại khi test kỳ vọng principal chưa có session.
- Ghi đè attributes hoặc xóa session mà test khác đang sử dụng.
- Phụ thuộc vào thứ tự chạy, khiến test pass riêng nhưng fail khi chạy toàn bộ suite.

Vấn đề này càng dễ xuất hiện khi test chạy song song, khi Maven/Gradle fork nhiều JVM hoặc khi nhiều pipeline CI cùng dùng một Redis/database dùng chung.

## 2. Phân biệt các lớp cách ly

Không có một biện pháp duy nhất xử lý mọi loại rò rỉ test. Hãy phân biệt các lớp sau:

| Lớp | Cần cách ly điều gì? | Biện pháp thường dùng |
|---|---|---|
| Hạ tầng | Redis/database của test với môi trường khác | Testcontainers hoặc instance test chuyên dụng |
| Namespace/schema | Key hoặc bảng Spring Session của một nhóm test | Redis namespace riêng; JDBC schema/database/table riêng |
| Test identity | Principal, session và dữ liệu nghiệp vụ của từng ca | UUID/prefix riêng cho mỗi test |
| Cookie/client | Session ID và cookie jar giữa các test | Tạo client mới, không dùng cookie tĩnh dùng chung |
| Application context | Bean, filter, cache và security state trong JVM | Context test được cấu hình nhất quán; đóng/rebuild khi cần |
| Cleanup | Dữ liệu còn lại sau test | Xóa session theo ID/principal và dọn dữ liệu phụ trợ |

Namespace tách dữ liệu theo nhóm nhưng không thay thế test identity. Một namespace dùng chung cho toàn bộ suite vẫn có thể chứa session của nhiều test; vì vậy cần định danh duy nhất và cleanup rõ ràng.

## 3. Redis namespace của Spring Session

Spring Session Redis thường thêm một namespace vào các key session. Namespace mặc định phổ biến là `spring:session`. Có thể thay đổi bằng thuộc tính `redisNamespace` của cấu hình annotation hoặc property tương ứng của Spring Boot.

Ví dụ cấu hình Servlet:

```java
@Configuration
@EnableRedisHttpSession(
        redisNamespace = "test:servlet-session",
        maxInactiveIntervalInSeconds = 600)
class TestSessionConfiguration {
}
```

Với Spring Boot, có thể đặt property trong test configuration:

```properties
spring.session.redis.namespace=test:servlet-session
spring.session.timeout=10m
```

Tên property và cách auto-configuration được áp dụng cần đối chiếu với phiên bản Spring Boot/Spring Session đang dùng. Nếu ứng dụng tự khai báo `@EnableRedisHttpSession`, cấu hình annotation và property phải được kiểm tra để tránh nghĩ rằng property đã ghi đè một bean cấu hình tường minh.

Namespace tạo prefix cho key của Spring Session. Ví dụ, dữ liệu session của suite có thể nằm dưới `test:servlet-session:*`, trong khi ứng dụng khác dùng `app:session:*`. Không nên dùng namespace production trong test tự động.

Namespace chỉ là cách phân vùng key. Nó không phải ranh giới bảo mật độc lập: tiến trình có quyền Redis rộng vẫn có thể đọc/xóa key của namespace khác. Hãy dùng Redis ACL, network isolation và instance riêng khi cần cô lập an toàn giữa môi trường hoặc tenant.

## 4. Tách namespace theo suite, class và test method

Chọn mức namespace dựa trên cách Spring context được tạo và cache:

- **Theo suite:** dễ quản lý, dùng một namespace cho một lần chạy test; mỗi test method vẫn dùng principal/session ID duy nhất và cleanup.
- **Theo test class:** giảm va chạm giữa các nhóm test, phù hợp khi mỗi class có cấu hình hoặc tập dữ liệu riêng.
- **Theo test method:** cách ly mạnh hơn, nhưng cần khởi tạo context/repository với namespace mới cho từng method hoặc dùng hạ tầng riêng. Có thể làm chậm suite và tương tác với Spring TestContext cache.

Không nên giả định một property động được đánh giá lại mỗi test method. `@DynamicPropertySource` thường cung cấp property khi Spring TestContext tạo context; nếu context được cache, giá trị namespace có thể tiếp tục được dùng giữa nhiều method. Tạo chuỗi UUID trong một method rồi kỳ vọng bean đã khởi tạo sẽ tự chuyển namespace là không đúng.

Một lựa chọn đơn giản là dùng namespace cố định theo class, sau đó dùng principal duy nhất và cleanup sau mỗi method. Khi thật sự cần namespace theo method, hãy tạo context riêng có vòng đời rõ ràng hoặc dùng repository/connection được khởi tạo trực tiếp trong fixture của test.

## 5. Testcontainers cho Redis riêng của suite

Testcontainers có thể khởi chạy Redis dùng riêng cho test suite. Điều này tránh phụ thuộc vào Redis developer hoặc Redis dùng chung của CI.

Ví dụ với JUnit 5 và Spring Boot:

```java
@SpringBootTest
@Testcontainers
class SessionRepositoryIntegrationTests {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () ->
                REDIS.getMappedPort(6379));
        registry.add("spring.session.redis.namespace", () ->
                "test:servlet-session");
    }
}
```

Ví dụ dùng property `spring.data.redis.*` của các dòng Spring Boot mới; dự án cũ có thể dùng prefix `spring.redis.*`. Hãy dùng đúng dependency và API Testcontainers trong dự án. Nếu ứng dụng dùng reactive Redis, vẫn cần cấu hình reactive connection factory tương ứng.

Container tĩnh thường sống trong phạm vi class hoặc suite tùy cách quản lý lifecycle. Không cần tạo một Redis container mới cho từng test method nếu test identity và cleanup đã bảo đảm độc lập. Một container riêng cho mỗi suite thường cân bằng giữa tốc độ và cách ly.

Nếu nhiều JVM/fork CI dùng chung một Redis test service thay vì container riêng, hãy tạo namespace có thành phần build ID/fork ID để không đụng dữ liệu giữa các tiến trình.

## 6. Tách JDBC session data

Với Spring Session JDBC, dữ liệu thường nằm trong bảng `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`. Các ứng dụng hoặc test suite dùng chung database có thể va chạm nếu cùng bảng và cùng session ID.

Các cách cách ly phổ biến:

1. Dùng database riêng cho mỗi suite hoặc mỗi CI job.
2. Dùng schema riêng cho từng suite nếu database hỗ trợ schema.
3. Dùng tên bảng riêng được cấu hình qua `spring.session.jdbc.table-name` hoặc API cấu hình tương ứng của phiên bản.
4. Dùng cùng bảng test nhưng principal/session ID riêng và cleanup theo ID.

Ví dụ property minh họa:

```properties
spring.session.jdbc.initialize-schema=always
spring.session.jdbc.table-name=TEST_SESSION
spring.session.timeout=10m
```

Kiểm tra schema script của đúng phiên bản để biết cách tạo cả bảng attributes và các constraint/index liên quan. Nếu đổi tên bảng, xác nhận repository dùng tên tương ứng cho các bảng phụ; không chỉ tạo một bảng metadata rồi bỏ sót bảng attributes.

Không chạy test tự động vào database production hoặc database dùng chung với dữ liệu thật. Dùng credentials riêng, quyền tối thiểu và schema được tạo cho test. Nếu database không hỗ trợ schema riêng, hãy dùng database/container riêng hoặc table name riêng theo khả năng repository.

## 7. Vì sao @Transactional không đủ để dọn session?

Rollback transaction là cách tốt để cách ly dữ liệu nghiệp vụ khi mọi thao tác nằm trong cùng transaction. Tuy nhiên, không thể mặc định Spring Session session write tham gia transaction của test:

- Redis không tham gia transaction JDBC của test.
- Request HTTP thật có thể được xử lý trên thread/transaction khác với test method.
- Session thường được lưu ở thời điểm filter flush hoặc response hoàn tất.
- Repository có thể dùng transaction/connection riêng tùy cấu hình.
- Các thao tác cleanup, expiration hoặc event có thể chạy ngoài transaction của test.

Với JDBC, một số thao tác repository có thể tham gia transaction hiện hành trong một cấu hình cụ thể, nhưng chỉ dựa vào `@Transactional` là chưa đủ để chứng minh điều đó. Kiểm thử bằng repository thật và đọc lại dữ liệu sau rollback để xác nhận semantics. Với Redis, cần cleanup tường minh hoặc hạ tầng riêng.

Hãy dùng transaction rollback cho dữ liệu nghiệp vụ nếu phù hợp, đồng thời có chiến lược riêng cho session store. Không dùng một annotation để thay thế việc kiểm soát vòng đời của external state.

## 8. Dùng principal và test ID duy nhất

Ngay cả khi toàn bộ suite dùng một namespace, mỗi test nên tạo định danh không trùng:

```java
String testRunId = UUID.randomUUID().toString();
String principal = "test-user-" + testRunId;
String cartId = "test-cart-" + testRunId;
```

Không dùng principal cố định như `alice` cho mọi test nếu repository index theo principal và test chạy song song. Một test có thể xóa mọi session của `alice` trong khi test khác đang kiểm tra số phiên.

Đối với CI, có thể thêm build ID, fork ID hoặc worker ID vào prefix:

```text
test:<build-id>:<fork-id>:<test-class>:<test-id>
```

Tránh đưa email hoặc dữ liệu cá nhân thật vào test principal. Dùng dữ liệu giả và ID không chứa thông tin nhận dạng thật.

## 9. Theo dõi session ID được tạo bởi test

Để cleanup chính xác, ghi nhận session ID do test tạo. Với HTTP test, ID thường được trả qua `Set-Cookie`; test client cần giữ cookie trong phạm vi test đó.

Ví dụ với `MockMvc`:

```java
MvcResult result = mockMvc.perform(post("/login")
                .param("username", testUsername)
                .param("password", testPassword)
                .with(csrf()))
        .andExpect(status().is3xxRedirection())
        .andReturn();

Cookie sessionCookie = result.getResponse().getCookie("SESSION");
assertThat(sessionCookie).isNotNull();
String sessionId = sessionCookie.getValue();
```

Cookie name phải khớp `DefaultCookieSerializer` đang cấu hình; có ứng dụng dùng `JSESSIONID` hoặc tên riêng. Nếu test chỉ gọi controller mà không đi qua filter chain, nó có thể không kiểm tra được session persistence/cookie behavior thực tế.

Không lưu session ID vào log test lâu dài hoặc báo cáo CI nếu không cần. Dùng ID trong bộ nhớ để cleanup, sau đó bỏ tham chiếu khi test kết thúc.

## 10. Cleanup session bằng repository API

Nếu biết session ID, xóa đúng phiên bằng repository:

```java
@Autowired
SessionRepository<? extends Session> sessionRepository;

void deleteSession(String sessionId) {
    if (sessionId != null) {
        sessionRepository.deleteById(sessionId);
    }
}
```

Đoạn mã minh họa injection; kiểu generic cụ thể có thể cần điều chỉnh theo repository bean của ứng dụng. Gọi cleanup trong `@AfterEach` hoặc fixture teardown, kể cả khi assertion thất bại. Dùng `try/finally` hoặc JUnit extension để bảo đảm cleanup luôn được thực hiện.

Nếu repository hỗ trợ `FindByIndexNameSessionRepository`, có thể tìm session theo principal test duy nhất rồi xóa tất cả ID của principal đó:

```java
@Autowired
FindByIndexNameSessionRepository<? extends Session> indexedRepository;

void deleteSessionsForTestPrincipal(String principal) {
    indexedRepository.findByPrincipalName(principal)
            .keySet()
            .forEach(indexedRepository::deleteById);
}
```

Chỉ dùng principal được tạo bởi test hiện tại. Không gọi xóa theo principal chung có thể được test khác dùng.

Nếu test dùng repository không hỗ trợ principal index, hãy lưu session ID trong fixture ngay khi tạo và xóa từng ID. Đừng quét toàn bộ session store chỉ để dọn một test.

## 11. Không dùng FLUSHDB hoặc FLUSHALL trên kho dùng chung

`FLUSHDB` xóa toàn bộ key trong Redis logical database hiện tại; `FLUSHALL` xóa key trên mọi logical database. Hai lệnh này có thể xóa dữ liệu của test khác hoặc ứng dụng khác nếu Redis đang được chia sẻ.

Chỉ cân nhắc lệnh xóa toàn database khi Redis container được tạo riêng cho đúng test suite, không có consumer khác và lifecycle container bảo đảm bị hủy sau test. Ngay cả khi đó, xóa container hoặc tạo container mới thường rõ ràng hơn.

Với Redis dùng chung, cleanup phải giới hạn theo namespace hoặc session ID. Nếu cần xóa theo prefix, dùng `SCAN` theo batch và xác minh pattern chỉ thuộc test hiện tại; tránh `KEYS *` trên môi trường có tải. Repository API vẫn là lựa chọn ưu tiên vì hiểu cấu trúc session và metadata phụ trợ.

Với JDBC, không chạy `DELETE FROM SPRING_SESSION` trên database dùng chung. Nó có thể xóa session của test khác hoặc người dùng thật. Nếu cần truncate bảng, chỉ thực hiện trong database/schema test riêng mà không có consumer khác.

## 12. Cách ly cookie jar và client giữa test

Cookie session ID là trạng thái của client. Dùng một HTTP client hoặc cookie jar static cho toàn bộ test có thể làm test sau gửi session của test trước.

Nguyên tắc:

- Tạo client/cookie jar mới cho mỗi test method hoặc mỗi test user.
- Không giữ cookie session trong static field hoặc singleton test fixture.
- Khi test logout, giữ một bản sao cookie cũ để xác minh server từ chối ID đã thu hồi; không vô tình dùng cookie jar đã tự xóa cookie làm mất ý nghĩa kiểm tra.
- Với `MockMvc`, truyền cookie rõ ràng cho request cần kiểm tra và không chia sẻ `MockHttpSession` giữa test.
- Với HTTP client thật, tắt hoặc reset cookie store giữa các test.
- Xác nhận response `Set-Cookie` xóa đúng name, domain và path.

Một cookie jar riêng không xóa session ở repository. Ngược lại, xóa session ở repository không tự xóa cookie trong một client khác. Cần xử lý cả hai lớp.

## 13. Context caching và @DirtiesContext

Spring TestContext cache `ApplicationContext` để tăng tốc suite. Nhiều test class có cấu hình giống nhau có thể dùng cùng context, cùng bean, cùng filter và cùng repository. Điều này không nhất thiết là vấn đề nếu test data được cách ly.

`@DirtiesContext` đánh dấu context cần đóng và tạo lại cho test tiếp theo. Nó hữu ích khi test thay đổi singleton bean hoặc cấu hình context theo cách không thể hoàn nguyên. Tuy nhiên, đóng context không tự xóa dữ liệu đã ghi vào Redis hoặc JDBC. External session data có thể tồn tại sau khi bean bị hủy.

Đừng dùng `@DirtiesContext` làm cơ chế cleanup session mặc định. Dùng nó cho state của ApplicationContext; dùng repository API, namespace/schema riêng hoặc container lifecycle cho external state.

## 14. Chạy test song song an toàn

Test chạy song song cần tránh cả xung đột dữ liệu và xung đột cleanup:

1. Namespace riêng theo suite/fork hoặc kho test riêng.
2. Principal và session ID duy nhất theo test.
3. Cookie jar độc lập.
4. Cleanup chỉ xóa ID/principal thuộc test hiện tại.
5. Không dùng chung tài khoản test cố định cho các test kiểm tra session count hoặc logout-all.
6. Không đổi namespace động trong context đã cache.
7. Dùng lock/serial execution cho test thật sự kiểm tra singleton/global configuration.
8. Đặt timeout cho cleanup và chờ repository operation hoàn tất trước khi kết thúc test.

Nếu một test kiểm tra giới hạn “mỗi người dùng chỉ có một session”, hai test chạy song song với cùng principal sẽ làm kết quả không xác định. Dùng principal riêng hoặc đánh dấu test đó chạy tuần tự trong một môi trường riêng.

## 15. Test isolation cho Redis và JDBC

| Đặc điểm | Redis | JDBC |
|---|---|---|
| Cách tách nhóm test | `redisNamespace` riêng | Database/schema/table riêng |
| Định danh từng test | Principal và session ID duy nhất | Principal và session ID duy nhất |
| Cleanup | Repository `deleteById`; xóa key theo prefix chỉ trong môi trường test riêng | Repository `deleteById`; cleanup bảng phụ trong schema riêng |
| Transaction rollback | Không rollback bằng transaction JDBC | Chỉ hiệu quả nếu thao tác session thật sự tham gia transaction test |
| Rủi ro đặc thù | `FLUSHDB`, keyspace và TTL còn tồn tại sau test | Bảng attributes, FK, cleanup job và table name không khớp |
| Kiểm thử tích hợp | Redis container riêng | Database container/schema riêng gần production |

Với Redis, xác minh TTL và expiration marker nếu implementation indexed sử dụng chúng. Với JDBC, xác minh cả metadata và attributes được xóa; nếu chỉ xóa bảng chính mà bỏ sót bảng attributes, dữ liệu thử nghiệm có thể còn lại hoặc constraint gây lỗi.

## 16. Ví dụ fixture JUnit cho principal và session cleanup

Một fixture có thể tạo principal duy nhất và cleanup mọi session của nó sau test:

```java
@SpringBootTest
class SessionIsolationTests {

    @Autowired
    FindByIndexNameSessionRepository<? extends Session> sessions;

    private String testPrincipal;

    @BeforeEach
    void setUp() {
        testPrincipal = "test-user-" + UUID.randomUUID();
    }

    @AfterEach
    void tearDown() {
        sessions.findByPrincipalName(testPrincipal)
                .keySet()
                .forEach(sessions::deleteById);
    }
}
```

Ví dụ giả định repository đang dùng hỗ trợ principal index và test authentication flow thực sự ghi principal vào session. Nếu test tạo session không có SecurityContext/index, hãy track ID trực tiếp thay vì trông chờ `findByPrincipalName` tìm thấy nó.

Trong test có thể phát sinh exception khi cleanup, hãy bảo đảm lỗi teardown không che mất lỗi assertion ban đầu. Có thể thu thập cleanup failure và gắn như suppressed exception hoặc dùng extension quản lý resource.

## 17. Kiểm thử namespace isolation giữa hai ứng dụng

Một test có thể chứng minh hai namespace không nhìn thấy session của nhau dù cùng dùng một Redis container:

1. Khởi chạy context A với namespace `test:app-a`.
2. Khởi chạy context B với namespace `test:app-b`.
3. Đăng nhập/tạo session qua A và lấy cookie A.
4. Gửi cookie A tới B.
5. Xác nhận B không khôi phục session A và xử lý request như anonymous hoặc tạo session B mới theo endpoint.
6. Tạo session qua B và xác nhận A không nhìn thấy session đó.
7. Dọn session của từng namespace bằng repository tương ứng.

Khi test hai context, cần bảo đảm chúng thực sự dùng namespace khác nhau. Nếu Spring context cache làm tái sử dụng bean cấu hình A cho B, test có thể vô tình kiểm tra cùng namespace. Hãy kiểm tra property/bean cấu hình trong từng context và tránh thay đổi property sau khi context đã được tạo.

Namespace isolation không có nghĩa Redis ACL đã cô lập hai ứng dụng. Test trên chỉ chứng minh repository prefix không trùng; quyền Redis vẫn cần được kiểm soát riêng.

## 18. Kiểm thử dữ liệu không rò rỉ giữa hai test method

Một kiểm thử regression hữu ích:

1. Test A tạo session với principal và attribute có marker duy nhất, ví dụ `ownerTestId`.
2. A kết thúc và cleanup session.
3. Test B dùng client mới, không gửi cookie A.
4. B kiểm tra không thể tìm session A theo principal hoặc session ID.
5. B tạo session riêng và xác nhận chỉ dữ liệu B xuất hiện.

Không dùng một giá trị marker chung như `test-data`; dùng UUID để phát hiện rò rỉ chính xác. Khi cleanup bị bỏ sót, test B có thể phát hiện session còn lại. Tuy nhiên, test B vẫn cần được cách ly để không tự xóa dữ liệu của test chạy song song.

## 19. Test context và security state

Session có thể giữ `SecurityContext`. Nếu test dùng cùng cookie hoặc `MockHttpSession`, request sau có thể được xác thực bằng principal từ test trước. Điều này khiến test authorization có kết quả sai dù test method đã tạo user mới.

Các nguyên tắc:

- Tạo user/principal riêng cho mỗi test khi kiểm tra session persistence.
- Xóa session repository record sau test.
- Không dùng lại `MockHttpSession` giữa các test method.
- Dùng security test support để thiết lập authentication cho unit test, nhưng dùng login flow thật trong integration test cần xác minh lưu session.
- Dọn `SecurityContextHolder` nếu test trực tiếp thiết lập ThreadLocal; Spring Security Test thường có listener quản lý context, nhưng không thay thế cleanup session đã lưu.
- Kiểm tra logout bằng cookie ID cũ thay vì chỉ xóa authentication trong test thread.

Với WebFlux, context bảo mật nằm trong Reactor Context của publisher hiện tại; điều đó khác với SecurityContext được lưu vào WebSession qua repository. Dọn Reactor Context của một test không xóa WebSession trong Redis.

## 20. Cleanup job và thời gian chạy test

Spring Session có thể có cleanup/expiration task. Test dùng timeout rất ngắn có thể bị ảnh hưởng bởi lịch chạy cleanup, Redis expiration notification hoặc scheduler. Không giả định key vật lý biến mất chính xác tại mili giây timeout.

Để test ổn định:

- Assert session không còn hợp lệ theo repository/API trước khi assert key vật lý đã bị xóa.
- Nếu cần kiểm tra cleanup, chờ điều kiện cuối bằng polling có timeout hữu hạn.
- Không dùng `Thread.sleep` cố định như bằng chứng cleanup đã chạy.
- Tắt hoặc điều chỉnh scheduled cleanup trong test chỉ khi test không kiểm tra chính cleanup behavior.
- Khi kiểm tra expiration thật, giữ scheduler/notification tương tự production và chấp nhận độ trễ hợp lý.
- Cleanup test data trực tiếp bằng repository API sau mỗi test; không chờ TTL hết để giữ suite nhanh và độc lập.

## 21. Những cách cleanup nguy hiểm

| Cách làm | Rủi ro | Cách an toàn hơn |
|---|---|---|
| `FLUSHALL` trên Redis dùng chung | Xóa session của mọi database/ứng dụng | Redis container riêng hoặc xóa theo ID/namespace test |
| `FLUSHDB` trên database dùng chung | Xóa dữ liệu test khác | Container riêng hoặc cleanup theo namespace |
| `DELETE FROM SPRING_SESSION` trên DB chung | Xóa session của test/người dùng khác | Database/schema/table riêng hoặc delete theo session ID |
| Xóa theo principal cố định | Xóa session của test song song | Principal UUID riêng cho mỗi test |
| Chỉ dùng `@Transactional` | External Redis/session write có thể không rollback | Cleanup repository tường minh |
| Chỉ dùng `@DirtiesContext` | Dữ liệu Redis/JDBC vẫn còn | Context lifecycle cộng cleanup external state |
| Chỉ chờ TTL | Suite chậm và phụ thuộc scheduler | Delete theo repository sau test |
| Dùng static cookie jar | Test sau mang session của test trước | Cookie jar riêng theo test |

## 22. Kiểm tra tính độc lập của suite

Ngoài test từng method, cần kiểm tra suite ở các cách chạy khác nhau:

1. Chạy từng test class riêng lẻ.
2. Chạy toàn bộ suite theo thứ tự mặc định.
3. Chạy lại một test class nhiều lần.
4. Chạy test song song nếu dự án bật parallel execution.
5. Chạy nhiều fork/worker CI nếu cấu hình hỗ trợ.
6. Chạy test sau một lần build thất bại trước đó, khi external container hoặc service có thể còn dữ liệu.
7. Kiểm tra teardown khi test fail giữa chừng.

Một suite thực sự được cách ly phải cho cùng kết quả bất kể thứ tự chạy và không dựa vào dữ liệu do lần chạy trước để lại. Nếu test chỉ pass khi chạy riêng, hãy kiểm tra namespace, principal, cookie jar, context cache và cleanup trước khi tăng timeout hoặc thêm retry.

## 23. Checklist thiết kế test Spring Session

| Câu hỏi | Kỳ vọng |
|---|---|
| Test có dùng Redis/JDBC riêng hoặc namespace/schema riêng không? | Có |
| Mỗi test có principal và session ID riêng không? | Có |
| Cookie jar có được tạo mới theo test không? | Có |
| Session ID được track để cleanup không? | Có |
| Cleanup chạy kể cả khi assertion thất bại không? | Có |
| Cleanup chỉ xóa dữ liệu thuộc test hiện tại không? | Có |
| Có tránh `FLUSHDB`/`FLUSHALL` trên kho dùng chung không? | Có |
| Có hiểu giới hạn rollback của `@Transactional` không? | Có |
| Có phân biệt context cache với external session data không? | Có |
| Test song song có dùng dữ liệu riêng không? | Có |
| Có kiểm tra session thực sự qua filter/cookie/repository không? | Có |
| Có xác minh dữ liệu không còn sau cleanup không? | Có |

## 24. Quy trình triển khai trong dự án

1. Chọn Redis/JDBC container hoặc dịch vụ test chuyên dụng; không trỏ test vào kho production.
2. Đặt namespace Redis hoặc schema/table JDBC riêng cho suite/class.
3. Dùng principal, session ID và dữ liệu nghiệp vụ giả duy nhất cho từng test.
4. Tạo HTTP client/cookie jar mới theo test method.
5. Track session ID hoặc principal index được tạo để cleanup.
6. Dọn session bằng `SessionRepository`/`FindByIndexNameSessionRepository` trong teardown.
7. Không dựa vào transaction rollback hoặc `@DirtiesContext` để xóa external session data.
8. Không dùng lệnh xóa toàn kho trên Redis/database dùng chung.
9. Kiểm thử expiration/cleanup bằng điều kiện quan sát được và timeout hữu hạn.
10. Chạy suite theo thứ tự khác nhau, song song và trên nhiều CI worker để phát hiện rò rỉ.

## 25. Tài liệu chính thức để đối chiếu

Property và annotation thay đổi theo phiên bản Spring Boot/Spring Session. Khi cấu hình test, hãy đối chiếu tài liệu của đúng dòng đang dùng:

- [Spring Session — Redis configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Boot — Application properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring TestContext Framework — Context caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)

Cách ly namespace và dữ liệu test giúp mỗi ca kiểm thử bắt đầu từ trạng thái có thể dự đoán và kết thúc mà không để lại session cho ca khác. Dùng Redis namespace hoặc JDBC schema riêng để phân vùng, principal/session ID và cookie jar riêng để tránh va chạm trong cùng vùng, rồi cleanup bằng repository API. Hãy xem transaction rollback, context caching và TTL là những cơ chế có phạm vi riêng; không cơ chế nào tự thay thế toàn bộ chiến lược cách ly external session state.
