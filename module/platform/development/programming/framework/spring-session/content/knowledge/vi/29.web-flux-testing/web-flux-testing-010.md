# Kiểm tra mốc thời gian logic và TTL backend theo các cơ chế khác nhau

Trong ứng dụng Spring WebFlux dùng Spring Session, cần phân biệt thời điểm một session hết hạn theo logic của framework với thời điểm dữ liệu session bị xóa vật lý khỏi Redis hoặc database. Hai thời điểm này có liên quan nhưng không nhất thiết trùng nhau. Một session có thể đã hết hạn về logic trong khi key Redis hoặc row database vẫn còn; ngược lại, dữ liệu có thể bị xóa sớm do thao tác quản trị hoặc lỗi lưu trữ dù thời gian logic chưa tới hạn.

Kiểm thử đúng phải xác minh cả hai lớp: repository không khôi phục session đã hết hạn, và backend thực hiện TTL/cleanup theo chính sách đã cấu hình. Với WebFlux, cần dùng reactive repository và kiểm thử qua WebTestClient/StepVerifier. Không dùng thời gian ảo của Reactor để kết luận Redis server đã chạy hết TTL: virtual scheduler không tự thay đổi clock của JVM hoặc đồng hồ của datastore.

## 1. Hai khái niệm: logical expiration và physical TTL

Logical expiration là quy tắc xác định session không còn hợp lệ để khôi phục. Với idle timeout, thời điểm hết hạn thường được tính từ lần truy cập gần nhất:

~~~text
expiresAt = lastAccessTime + maxIdleTime
expired   = now >= expiresAt
~~~

Physical TTL/cleanup là cơ chế của backend để xóa dữ liệu đã hết hạn hoặc làm cho key/row không còn được tìm thấy. Redis có TTL trên key; database có thể lưu expiresAt và chạy cleanup theo batch; in-memory store có thể chỉ kiểm tra timestamp khi đọc mà không có TTL engine riêng.

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Logical expiration | Request này còn được khôi phục session không? | Session hết hạn thì repository không trả session |
| Backend TTL | Dữ liệu còn tồn tại vật lý trong store bao lâu? | Redis key hết TTL; job database xóa row đã hết hạn |
| HTTP/WebFlux lifecycle | Khi nào client nhận cookie/định danh mới hoặc bị từ chối? | WebSession được lưu khi response hoàn tất; session cũ không được khôi phục |

Không dùng việc key đã biến mất để thay thế kiểm tra logical expiration. Cũng không coi việc row còn tồn tại là bằng chứng session còn hợp lệ.

## 2. Idle timeout khác absolute lifetime

Spring Session thường quản lý thời gian không hoạt động thông qua max inactive interval/max idle time. Mỗi lần session được truy cập hợp lệ, last access time có thể được cập nhật theo lifecycle của WebSession. Nếu người dùng tiếp tục hoạt động, idle timeout được tính lại từ lần truy cập mới nhất.

Absolute lifetime là giới hạn tổng thời gian từ khi session được tạo hoặc xác thực, kể cả khi người dùng hoạt động liên tục. Đây là chính sách bổ sung ở tầng ứng dụng nếu nghiệp vụ yêu cầu; không suy ra absolute lifetime từ idle timeout.

Ví dụ:

- Session được tạo lúc 09:00, idle timeout 30 phút.
- Request hợp lệ lúc 09:20 làm mới last access time.
- Nếu không có hoạt động tiếp theo, session hết hạn logic khoảng 09:50.
- Nếu hệ thống còn giới hạn absolute lifetime 8 giờ, session vẫn phải kết thúc lúc 17:00 dù người dùng liên tục gửi request.

Khi test, phải xác định đang kiểm tra idle timeout hay absolute lifetime. Một bài test chỉ chờ quá max idle time không chứng minh absolute lifetime được áp dụng.

## 3. WebSession và ReactiveSessionRepository

Trong WebFlux, controller và filter làm việc với WebSession thay vì Servlet HttpSession. Có thể lấy session qua ServerWebExchange:

~~~java
@RestController
class SessionProbeController {

    @GetMapping("/probe")
    Mono<Map<String, Object>> probe(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            session.getAttributes().putIfAbsent("visits", 0);
            int visits = (Integer) session.getAttributes().get("visits") + 1;
            session.getAttributes().put("visits", visits);

            return Map.of(
                    "visits", visits,
                    "lastAccessTime", session.getLastAccessTime(),
                    "maxIdleTime", session.getMaxIdleTime(),
                    "expired", session.isExpired()
            );
        });
    }
}
~~~

Ví dụ minh họa các thuộc tính WebSession; ứng dụng thực tế cần import và xử lý lỗi theo phiên bản Spring Framework đang dùng. Không trả session ID ra response body hoặc log. Việc sửa attributes làm session được đánh dấu cần lưu; WebFlux session lifecycle sẽ lưu theo cơ chế WebSessionStore/repository khi response được hoàn tất.

Ở tầng Spring Session reactive, ReactiveSessionRepository cung cấp các thao tác reactive như tạo, lưu, tìm và xóa session. Khi tìm ID không tồn tại hoặc session đã hết hạn, repository cần phát Mono.empty() theo contract tương ứng thay vì phát một session không hợp lệ. Lỗi kết nối hoặc deserialize phải phát lỗi reactive, không được biến thành Mono.empty() giả.

ReactiveSessionRepository và Servlet SessionRepository là hai contract khác nhau. Không lấy một repository blocking rồi gọi trực tiếp trên event-loop của WebFlux. Nếu dùng backend không có reactive implementation, cần đánh giá adapter phù hợp hoặc chuyển thao tác blocking sang scheduler chuyên dụng; không để JDBC blocking chiếm event-loop.

## 4. Các mốc thời gian cần quan sát

Một test TTL nên quan sát các giá trị sau:

- creation time: thời điểm session được tạo.
- last access time: lần truy cập gần nhất được ghi nhận.
- max idle time: khoảng không hoạt động tối đa.
- logical expiresAt: thời điểm suy ra từ last access và max idle time.
- backend TTL còn lại: thời gian backend dự kiến giữ key/record trước khi xóa.
- cleanup time: thời điểm dữ liệu thực sự được dọn khỏi backend.

Không phải repository nào cũng lưu riêng expiresAt hoặc trả backend TTL qua API Spring Session. Một số giá trị phải được suy ra trong test hoặc quan sát qua công cụ của backend. Hãy tách dữ liệu đo được từ API công khai với dữ liệu nội bộ phụ thuộc implementation.

| Thời điểm | lastAccessTime | maxIdleTime | Logical expiry | Backend TTL |
| --- | --- | --- | --- | --- |
| Tạo session | 10:00:00 | 5 phút | 10:05:00 | khoảng 300 giây |
| Request tiếp theo | 10:02:00 | 5 phút | 10:07:00 | được refresh theo repository |
| Sau 10:07:00 | 10:02:00 | 5 phút | Đã hết hạn | Có thể vẫn còn trong một khoảng ngắn |
| Sau cleanup | 10:02:00 | 5 phút | Đã hết hạn | Key/row đã bị xóa |

Các mốc chỉ minh họa. Thời điểm lưu, làm mới TTL, độ chính xác timer và cleanup phụ thuộc repository, backend và phiên bản.

## 5. Cấu hình timeout cho WebFlux session

Với Spring Boot, timeout session thường được cấu hình bằng property Spring Session phù hợp với phiên bản:

~~~yaml
spring:
  session:
    timeout: 5m
    redis:
      namespace: webflux:test-sessions
~~~

Ví dụ dùng timeout ngắn trong test profile để giảm thời gian kiểm thử. Kiểm tra property metadata của phiên bản Spring Boot đang dùng; không đồng thời bật nhiều cấu hình repository trái ngược nhau.

Với reactive Redis session, ứng dụng cần dùng cấu hình Redis phù hợp và repository reactive do Spring Session hỗ trợ. Nếu dùng annotation cấu hình Redis WebSession ở phiên bản tương ứng, xác minh bean repository và WebSessionStore thực tế trong application context. Không chỉ nhìn property file rồi kết luận repository đã được kích hoạt.

Trong test, nên cấu hình timeout ngắn nhưng đủ lớn để request đầu tiên hoàn tất trước khi bắt đầu đo expiry. Ví dụ 2–5 giây có thể phù hợp cho integration test; test logic có thể dùng timestamp điều khiển để không phải chờ thời gian thật.

## 6. Kiểm tra logical expiration mà không chờ TTL thật

Logical expiration nên được test độc lập với cơ chế xóa vật lý. Với custom reactive repository, có thể inject Clock để test điều khiển thời gian. Repository tính isExpired theo Clock được cung cấp, lưu session metadata và trả Mono.empty() khi session hết hạn.

Ví dụ ý tưởng kiểm thử:

~~~java
StepVerifier.create(repository.findById(sessionId))
        .expectNextCount(0)
        .verifyComplete();
~~~

Trước assertion, test phải tạo hoặc lưu session có lastAccessTime nằm trước thời điểm hiện tại một khoảng lớn hơn maxInactiveInterval. Test cũng nên có trường hợp session còn hạn để chứng minh repository không trả empty quá sớm.

Với implementation dùng trực tiếp thời gian hệ thống, có thể tạo session fixture có timestamp cũ hoặc dùng test hook phù hợp. Không giả định mọi implementation Spring Session đều cho thay Clock. Nếu không thể inject clock, tránh sửa private field hoặc phụ thuộc reflection vào internals; dùng timestamp session được hỗ trợ hoặc kiểm thử qua thời gian thật có giới hạn.

Khi dùng StepVerifier.withVirtualTime, chỉ các tác vụ dùng Reactor scheduler ảo mới được điều khiển. Instant.now(), Clock.systemUTC(), timer nội bộ của Redis và TTL trên Redis server không tự nhảy theo virtual time. Vì vậy, virtual time phù hợp để test retry/delay reactive, nhưng không đủ để chứng minh backend key đã hết TTL.

## 7. Kiểm tra Redis TTL thật

Redis có expiration cho key. Khi session được lưu, repository thiết lập TTL tương ứng với thời hạn còn lại; khi session được làm mới, TTL có thể được cập nhật theo lifecycle của repository. Khi TTL về 0, Redis có thể làm key không còn truy cập được, nhưng việc xóa vật lý không nhất thiết xảy ra đúng tại một millisecond cố định vì cơ chế expiration của Redis kết hợp truy cập và kiểm tra nền.

Các cách kiểm tra:

1. Dùng repository API để xác minh session không còn được khôi phục sau logical expiry.
2. Trong test chuyên biệt, quan sát TTL/remaining TTL của key do đúng phiên bản repository tạo ra.
3. Poll trạng thái key hoặc repository với deadline thay vì assert đúng một thời điểm tuyệt đối.
4. Xác minh TTL được refresh sau một request hợp lệ nếu repository semantics yêu cầu.
5. Xác minh session đã logout không được khôi phục ngay cả khi client còn giữ cookie cũ.

Redis cung cấp TTL theo giây và PTTL theo millisecond. Giá trị âm có thể biểu thị key không tồn tại hoặc key không có expiration, tùy giá trị trả về. Phải phân biệt các trường hợp đó khi viết test. Không giả định TTL chính xác bằng maxIdleTime tại mọi thời điểm vì thời gian đã trôi qua, thời điểm flush và các key phụ có thể làm con số khác nhau.

Không hard-code cấu trúc key nội bộ của Spring Session vào code nghiệp vụ. Nếu test cần quan sát PTTL, hãy cô lập việc truy vấn key theo đúng implementation/version đang kiểm tra và ghi rõ đó là integration test phụ thuộc backend. Assertion chính vẫn nên dùng ReactiveSessionRepository/WebSession API.

## 8. Kiểm tra cleanup trong backend có cơ chế quét

Không phải backend nào cũng có TTL engine giống Redis. Một repository dùng relational database có thể lưu expiresAt trong row và chạy cleanup theo lịch. Một custom repository có thể chỉ kiểm tra expiration khi findById rồi xóa theo batch. In-memory repository có thể không dọn ngay khi hết hạn mà chỉ từ chối khôi phục.

Vì vậy, tách hai assertion:

- Không khôi phục: findById hoặc WebSession retrieval không trả session sau logical expiry.
- Đã dọn vật lý: record/key đã bị xóa sau TTL hoặc cleanup.

Với database, cleanup có thể chạy mỗi phút hoặc theo batch; row vẫn còn sau khi hết hạn không có nghĩa repository được phép trả session. Kiểm tra query/contract tìm session phải loại row hết hạn ngay cả khi job cleanup chưa chạy.

Với WebFlux, không mặc định Spring Session JDBC blocking repository là một reactive backend. Nếu dùng R2DBC/custom reactive store, kiểm tra riêng cách lưu expiresAt, query expiry và cleanup scheduler. Nếu phải gọi JDBC, không chạy blocking call trực tiếp trên event-loop.

## 9. Kiểm thử HTTP cookie round-trip bằng WebTestClient

Để test qua toàn bộ WebFlux session lifecycle, dùng WebTestClient gửi request tạo session, lấy cookie từ response rồi gửi cookie đó trong request tiếp theo. Nên cấu hình tên cookie rõ ràng trong test để tránh phụ thuộc mặc định.

Ví dụ resolver cookie của WebFlux:

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
    resolver.setCookieName("SESSION");
    return resolver;
}
~~~

Ví dụ test khái quát:

~~~java
EntityExchangeResult<Map> created = webTestClient.post()
        .uri("/probe/create")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Map.class)
        .returnResult();

ResponseCookie cookie =
        created.getResponseCookies().getFirst("SESSION");

assertThat(cookie).isNotNull();

webTestClient.get()
        .uri("/probe/read")
        .cookie("SESSION", cookie.getValue())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.sessionPresent").isEqualTo(true);
~~~

Đây là ví dụ minh họa; endpoint và response DTO tùy ứng dụng. Không in cookie value ra log. Nếu resolver hoặc client test tự động quản lý cookie jar, xác minh rõ cookie có được gửi lại hay không; tránh test pass chỉ vì client giữ state ngầm mà test không biết.

## 10. Kiểm thử lastAccessTime và việc refresh TTL

Một session có thể được truy cập nhưng chưa chắc backend đã ghi lại thời điểm mới ngay ở thời điểm controller gọi getSession(). Việc lưu có thể diễn ra ở bước hoàn tất response hoặc theo flush mode/repository. Test nên chờ request hoàn tất rồi mới đọc lại session từ repository hoặc gửi request tiếp theo.

Kịch bản:

1. Tạo session với max idle time ngắn.
2. Lưu lastAccessTime ban đầu.
3. Gửi request hợp lệ dùng session trước khi hết hạn.
4. Đợi response hoàn tất.
5. Đọc session từ repository và xác minh lastAccessTime/expiration đã được cập nhật theo semantics.
6. Không gửi request tiếp theo và chờ vượt idle timeout mới.
7. Xác minh session không còn được khôi phục.

Không dùng request health check hoặc background polling để giữ session sống nếu mục tiêu là kiểm thử idle timeout. Một request chỉ đọc session cũng có thể được tính là activity theo integration; hãy kiểm soát mọi request mang session cookie trong test.

## 11. Kiểm thử TTL refresh khác nhau theo backend

Các backend có thể triển khai TTL theo cách khác:

| Backend | Logical check | Physical expiration/cleanup | Điều cần kiểm thử |
| --- | --- | --- | --- |
| Reactive Redis repository | Kiểm tra metadata session và trạng thái hết hạn | Redis key TTL/expiration; có thể có key phụ và event | TTL được đặt/refresh, session không được trả sau expiry, key cuối cùng biến mất |
| Custom reactive relational repository | Query expiresAt/maxInactiveInterval trước khi phát session | Scheduled delete hoặc database TTL feature nếu có | Query loại row hết hạn ngay, cleanup batch chạy đúng và không xóa nhầm row vừa refresh |
| In-memory reactive test store | Kiểm tra timestamp trong object | Có thể không có physical TTL engine | Repository từ chối session hết hạn; không khẳng định có physical deletion |
| Custom distributed cache | Theo metadata và version | TTL cache hoặc cleanup riêng | Độ trễ TTL, stale replica, invalidation và race giữa refresh/delete |

Không nên so sánh số giây TTL giữa các backend như một contract tuyệt đối. Điều quan trọng là semantics: không trả session hết hạn, refresh khi có activity hợp lệ, và eventual cleanup trong giới hạn đã thiết kế.

## 12. Thời gian ảo, Clock và scheduler

Có ba nguồn thời gian thường bị nhầm:

- Clock của JVM, ví dụ Instant.now() hoặc Clock.systemUTC().
- Scheduler của Reactor, có thể được thay bằng virtual scheduler trong test.
- Clock/expiration engine của backend, ví dụ Redis server TTL hoặc database CURRENT_TIMESTAMP.

Điều khiển một nguồn không tự điều khiển hai nguồn còn lại. Nếu custom repository nhận Clock qua constructor, unit test có thể tiến clock để kiểm tra logical expiration mà không chờ thật. Nhưng nếu repository ghi TTL vào Redis, Redis server vẫn đếm thời gian thực. Nếu test dùng virtual scheduler để chạy cleanup job, scheduler có thể kích hoạt job sớm nhưng Redis TTL vẫn chưa hết.

Thiết kế test tốt:

- Unit test logic expiry với Clock giả có thể điều khiển.
- Reactor test dùng virtual time cho timeout/retry/backoff của pipeline.
- Integration test dùng Redis/database thật để đo TTL và cleanup thực.
- Dùng deadline và polling có giới hạn cho eventual behavior.
- Không dùng một test duy nhất để khẳng định cả logical clock và backend TTL.

## 13. Xác định biên thời gian và sai số

TTL backend thường có độ phân giải và lịch cleanup riêng. Nếu session timeout là 2 giây, test không nên khẳng định ở đúng 2000 ms key đã biến mất. Có thể có sai số do:

- Thời điểm session được lưu muộn hơn thời điểm controller tạo session.
- Độ phân giải TTL của backend.
- Network round-trip giữa app và datastore.
- Clock skew giữa JVM và backend.
- Event loop scheduling và thời gian commit response.
- Redis expiration cycle hoặc database cleanup interval.

Hãy kiểm tra logical expiry tại mốc đã xác định, sau đó kiểm tra physical deletion trong một cửa sổ cho phép, ví dụ trong vòng vài giây sau thời điểm hết hạn. Cửa sổ cụ thể phải phù hợp với backend và cấu hình, không lấy một con số chung áp dụng mọi hệ thống.

## 14. Kiểm thử logout và xóa session trước TTL

Logout là một đường xóa tường minh, không phải chờ TTL. Khi session bị invalidate, repository cần xóa hoặc đánh dấu session không còn hợp lệ; request tiếp theo dùng cookie cũ không được khôi phục phiên đó.

Test nên:

1. Tạo session và giữ cookie.
2. Gửi logout qua WebFlux endpoint/security handler.
3. Xác minh response xử lý cookie theo resolver.
4. Gửi request tiếp theo bằng cookie cũ.
5. Xác minh session không còn được khôi phục.
6. Nếu backend có TTL/key phụ, xác minh chúng được cleanup theo semantics của repository.

Không chỉ assert cookie bị xóa ở client. Browser có thể tiếp tục gửi cookie cũ từ tab khác hoặc test client; server-side invalidation phải làm ID cũ không còn hợp lệ. Với custom store, delete cần idempotent và xử lý race với request đang save.

## 15. Phân biệt lỗi datastore với session hết hạn

Nếu Redis hoặc database không truy cập được, repository không thể kết luận session đã hết hạn hay không tồn tại. Trong reactive flow, lỗi nên được phát dưới dạng onError, không đổi thành Mono.empty() một cách tùy tiện.

| Tình huống | Kết quả repository |
| --- | --- |
| Session hợp lệ | Mono phát session |
| ID không tồn tại | Mono.empty() |
| Session đã hết hạn | Mono.empty() |
| Redis timeout/connection failure | Mono phát lỗi |
| Database unavailable | Mono phát lỗi |
| Payload deserialize lỗi | Mono phát lỗi dữ liệu theo policy |

Nếu onErrorResume(error -> Mono.empty()) được dùng quá rộng, ứng dụng sẽ biến sự cố hạ tầng thành hàng loạt session miss. Điều đó có thể làm người dùng bị coi là anonymous và che giấu outage. Chỉ fallback khi lỗi đã được phân loại và policy cho phép.

## 16. Kiểm thử expiration event và cleanup event

Một số backend phát event khi key hết hạn hoặc bị xóa. Event hữu ích để cập nhật index, đóng tài nguyên phụ hoặc quan sát lifecycle, nhưng không nên là cơ chế duy nhất bảo đảm session hết hạn không được khôi phục.

Redis keyspace notification là Pub/Sub và có thể bị bỏ lỡ khi subscriber mất kết nối. Test cần phân biệt:

- Repository lookup trả empty sau logical expiry.
- Event được phát và consumer nhận được trong điều kiện bình thường.
- Subscriber reconnect sau outage.
- Cleanup/đối soát vẫn hoàn tất nếu event bị mất.

Với database cleanup theo lịch, event có thể do ứng dụng phát sau khi job xóa row; semantics khác Redis keyspace notification. Không giả định mọi backend phát event cùng thời điểm hoặc đúng một lần.

## 17. Test matrix đề xuất

| Test | Đồng hồ điều khiển | Backend | Assertion |
| --- | --- | --- | --- |
| Session còn hạn | Clock giả hoặc timestamp hiện tại | In-memory/custom repo | findById phát session |
| Session logic hết hạn | Clock giả | In-memory/custom repo | findById empty |
| ID không tồn tại | Không cần thời gian | Mọi repo | findById empty |
| Backend TTL Redis | Thời gian thật | Redis Testcontainers | Key/session cuối cùng không còn trong deadline |
| TTL refresh | Thời gian thật và request HTTP | Redis | Activity hợp lệ cập nhật last access/TTL theo semantics |
| DB expiry query | Timestamp cố định | Reactive relational store | Query loại row hết hạn trước cleanup |
| DB cleanup job | Scheduler/job test | Reactive relational store | Row được xóa theo batch |
| Logout trước TTL | Không cần đợi TTL | Redis/DB | Cookie cũ không khôi phục session |
| Store outage | Fault injection | Redis/DB | onError, không giả Mono.empty |
| Expiry event | Event listener | Backend hỗ trợ | Event quan sát được; lookup vẫn đúng nếu event trễ |

Mỗi test nên có một mục tiêu chính. Không dùng một integration test dài vừa đo TTL, kiểm tra login, CORS, failover và serialization vì khi lỗi sẽ khó xác định nguyên nhân.

## 18. Ví dụ kiểm thử reactive repository bằng StepVerifier

Với một reactive repository có sẵn test fixture, StepVerifier kiểm tra tín hiệu Mono:

~~~java
@Test
void missingSessionCompletesEmpty() {
    StepVerifier.create(repository.findById("unknown-id"))
            .verifyComplete();
}

@Test
void storeFailureIsNotConvertedToEmpty() {
    StepVerifier.create(repository.findById("any-id"))
            .expectError()
            .verify();
}
~~~

Ví dụ đầu xác minh ID không tồn tại tạo Mono.empty(). Ví dụ thứ hai cần test double hoặc datastore fault injection được cấu hình để phát lỗi; không thể kỳ vọng lỗi nếu repository vẫn hoạt động bình thường. Dùng expectErrorSatisfies nếu cần xác minh exception class cụ thể.

Với session hết hạn, tạo fixture có lastAccessTime và maxInactiveInterval sao cho đã vượt ngưỡng theo clock của repository, lưu fixture rồi kiểm tra findById hoàn tất empty. Nếu repository chỉ xác định expiry trong WebSession adapter, hãy kiểm thử qua WebSessionStore/WebTestClient thay vì giả định direct repository có cùng wrapper semantics.

## 19. Tránh flaky test

Các lỗi phổ biến:

- Dùng timeout 100 ms nhưng CI máy chậm làm request chưa kịp lưu trước khi session hết hạn.
- Dùng Thread.sleep cố định rồi assert key phải biến mất đúng lúc.
- Dùng StepVerifier.withVirtualTime nhưng mong Redis TTL thay đổi.
- Gửi request nền vô tình refresh lastAccessTime.
- Dùng cookie jar tự động khiến test không biết request nào mang cookie.
- Đọc backend replica thay vì primary rồi kết luận TTL chưa refresh.
- Test song song dùng chung Redis namespace và xóa session của nhau.

Giải pháp:

- Dùng namespace riêng cho từng test run hoặc test class.
- Đặt timeout đủ dài cho phần setup, chỉ dùng clock giả cho logic.
- Dùng polling có deadline cho physical expiration.
- Tắt background poller không liên quan trong test profile.
- Dùng test ID/correlation ID riêng, không log session ID thật.
- Dọn test data bằng API repository sau test.
- Phân biệt lỗi setup, logical expiry, backend TTL và event delivery.

## 20. Quan sát production

Theo dõi riêng logical session lifecycle và backend storage:

**WebFlux/Spring Session**

- Số session tạo mới, khôi phục, miss và hết hạn.
- Latency của create/save/find/delete reactive operations.
- Tỷ lệ request tạo session mới bất thường sau khi session miss.
- Lỗi serialize/deserialize và lỗi WebSessionStore.
- Tỷ lệ logout thành công và lỗi repository.

**Backend**

- Redis key TTL/expired key rate, memory, eviction, replication lag và event listener health.
- Database số row hết hạn, cleanup batch duration, index/query latency và connection pool.
- Độ trễ từ logical expiry tới physical cleanup.
- Số lỗi datastore được phân biệt với session miss.

Không đưa session ID hoặc cookie vào metric label. Dùng repository type, node ID, error class và correlation ID đã được bảo vệ.

## 21. Quy trình kiểm thử từ logic tới backend

1. Xác định timeout đang kiểm tra là idle timeout hay absolute lifetime.
2. Xác định WebFlux đang dùng WebSessionStore và ReactiveSessionRepository nào.
3. Viết unit test logical expiry với timestamp/Clock có thể điều khiển.
4. Xác minh findById trả Mono.empty() cho ID không tồn tại và session hết hạn.
5. Xác minh datastore failure phát onError, không biến thành miss.
6. Dùng WebTestClient tạo session, lấy cookie và gửi lại request để xác minh round-trip.
7. Dùng Redis thật hoặc reactive backend thật để kiểm tra TTL/cleanup.
8. Poll physical deletion trong deadline, không assert thời điểm chính xác tuyệt đối.
9. Test refresh lastAccessTime, logout và cookie cũ.
10. Kiểm tra expiry event riêng với lookup contract.
11. Chạy test dưới tải và quan sát clock skew, lag, retry, event delay.

## 22. Checklist

- [ ] Phân biệt logical expiration với physical TTL/cleanup.
- [ ] Xác định idle timeout và absolute lifetime riêng biệt.
- [ ] Dùng WebSession/ReactiveSessionRepository đúng reactive stack.
- [ ] Không chạy blocking JDBC trực tiếp trên WebFlux event-loop.
- [ ] Kiểm tra lastAccessTime, maxIdleTime và thời điểm hết hạn.
- [ ] Logical expired/missing trả empty; datastore failure phát lỗi.
- [ ] Không phụ thuộc hoàn toàn vào TTL vật lý hoặc cleanup job.
- [ ] Không dùng Reactor virtual time để kết luận Redis/database clock đã chạy.
- [ ] Redis TTL được kiểm tra bằng backend thật và deadline có sai số.
- [ ] Database query loại row hết hạn ngay cả khi cleanup chưa chạy.
- [ ] Refresh và cleanup không xóa nhầm session mới được cập nhật.
- [ ] Logout làm cookie/session ID cũ không thể khôi phục.
- [ ] Expiration event được kiểm thử riêng và có phương án khi event bị bỏ lỡ.
- [ ] Test cô lập namespace và không log session credential.

Kiểm thử mốc thời gian logic và TTL backend cần hai lớp assertion độc lập. Logical expiration quyết định repository có được phép trả session hay không; physical TTL/cleanup quyết định dữ liệu còn nằm trong backend bao lâu. Với WebFlux, dùng Clock/timestamp điều khiển và StepVerifier cho logic reactive, WebTestClient cho cookie/session round-trip, rồi dùng Redis hoặc reactive store thật để kiểm tra TTL vật lý. Tách các lớp này giúp test chính xác, tránh flaky timing và phát hiện trường hợp dữ liệu đã hết hạn nhưng vẫn bị khôi phục hoặc backend không dọn dữ liệu theo kỳ vọng.
