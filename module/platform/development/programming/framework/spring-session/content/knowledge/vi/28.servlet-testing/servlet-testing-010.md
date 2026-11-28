# Kiểm tra hành vi khi repository ném lỗi

Trong ứng dụng Servlet, Spring Session thay nơi lưu HttpSession bằng một SessionRepository như Redis hoặc JDBC. SessionRepositoryFilter khôi phục session trước khi request đi vào phần xử lý ứng dụng và lưu các thay đổi theo vòng đời response. Nếu repository ném lỗi do Redis timeout, database unavailable, lỗi serialization hoặc vi phạm schema, ứng dụng phải xử lý như một sự cố hạ tầng.

Điểm quan trọng nhất khi kiểm thử là phân biệt **session không tồn tại** với **không thể đọc session vì repository đang lỗi**. Theo hợp đồng SessionRepository, findById trả null khi không có session tương ứng hoặc session không còn hợp lệ. Một exception từ backend có nghĩa hệ thống chưa xác định được trạng thái session. Không được bắt exception rồi trả null, vì request có thể bị coi như anonymous và tiếp tục theo một đường xử lý khác mà không phản ánh sự cố thật.

Bài học này tập trung vào kiểm thử toàn bộ đường đi Servlet khi repository thất bại: khôi phục, tạo, lưu, xóa và xử lý hết hạn. Mục tiêu là chứng minh lỗi được quan sát rõ, không làm rò rỉ dữ liệu, không biến lỗi storage thành đăng xuất giả hoặc xác thực sai, và không báo thành công cho một thao tác cần session bền vững nhưng chưa được lưu.

## 1. Hiểu hợp đồng lỗi của SessionRepository

SessionRepository là API đồng bộ dùng trong ứng dụng Servlet. Các thao tác chính:

| Phương thức | Mục đích | Kết quả bình thường |
|---|---|---|
| createSession() | Tạo session mới trong bộ nhớ để request sử dụng | Trả session mới |
| findById(id) | Khôi phục session theo ID | Trả session hoặc null nếu không tồn tại/không còn hợp lệ |
| save(session) | Lưu trạng thái session | Hoàn tất hoặc ném exception |
| deleteById(id) | Xóa session | Hoàn tất hoặc ném exception |

Các lỗi từ storage thường là unchecked exception, ví dụ DataAccessException từ Spring JDBC hoặc exception của Redis client. Repository custom cũng có thể bọc lỗi thành SessionStoreUnavailableException hoặc một exception hạ tầng riêng.

Không được nhập nhằng các trường hợp:

| Tình huống | Ý nghĩa | Cách xử lý |
|---|---|---|
| findById trả null | Session không tồn tại hoặc không còn hợp lệ | Xử lý như request chưa có session |
| findById trả session hợp lệ | Repository đã khôi phục được phiên | Tiếp tục xử lý theo SecurityContext và chính sách |
| findById ném lỗi kết nối | Không xác định được trạng thái phiên | Báo lỗi hạ tầng; không giả thành session missing |
| findById ném lỗi deserialize | Có dữ liệu nhưng không khôi phục được | Ghi nhận lỗi dữ liệu; không dùng payload không hợp lệ |
| save ném lỗi | Thay đổi session chưa được lưu bền vững | Không giả định request đã có session state mới |
| deleteById ném lỗi | Không xác nhận được session đã bị thu hồi | Không tuyên bố logout hoàn tất ở phía server |

Việc phân biệt này là một phần của contract test. Nếu repository bắt lỗi backend và trả null, test phải phát hiện lỗi thiết kế đó.

## 2. Những điểm trong request lifecycle có thể gọi repository

Với Servlet, SessionRepositoryFilter bọc request/response để ứng dụng tiếp tục dùng HttpSession. Các thao tác repository có thể xảy ra ở những thời điểm khác nhau:

1. Request có cookie session: filter cần gọi findById để khôi phục session.
2. Ứng dụng gọi getSession(true): session mới được tạo qua createSession.
3. Controller hoặc service thay đổi session attributes: dữ liệu được đánh dấu thay đổi.
4. Response được commit hoặc request kết thúc theo lifecycle của filter: repository được gọi để lưu thay đổi.
5. Logout hoặc invalidate: repository cần xóa session.

Vì vậy, kiểm thử controller đơn lẻ có thể không bắt được lỗi save hoặc delete. Cần chạy request qua đầy đủ servlet filter chain, bao gồm SessionRepositoryFilter và Spring Security filter chain nếu ứng dụng có xác thực.

Trong cấu hình chuẩn, SessionRepositoryFilter phải chạy trước Spring Security filter chain để SecurityContextRepository có thể đọc/ghi HttpSession đã được Spring Session quản lý. Nếu test tự đăng ký filter hoặc tạo MockMvc thủ công, hãy xác nhận thứ tự filter tương ứng với ứng dụng thực tế.

Không giả định mọi repository call đều xảy ra trong controller. Một lỗi có thể phát sinh ở bước commit response sau khi controller đã trả về. Điều này ảnh hưởng cách test nhận exception và cách ứng dụng chuyển lỗi thành HTTP response.

## 3. Xác định chính sách fail-closed

Khi repository không thể xác định session, ứng dụng cần bảo vệ tài nguyên nhạy cảm theo hướng fail-closed. Điều đó có nghĩa là không cho phép request dựa vào một Authentication mà server không thể khôi phục và xác minh theo chính sách.

Các nguyên tắc:

- Không biến backend timeout thành findById trả null.
- Không tự tạo session anonymous rồi cho request truy cập tài nguyên cần đăng nhập.
- Không dùng cache cục bộ cũ để tiếp tục xác thực nếu chính sách không cho phép stale session.
- Không chuyển sang repository local tạm thời trong khi node khác vẫn dùng Redis/JDBC.
- Không trả nội dung tài nguyên bảo vệ khi session store chưa xác định được trạng thái.
- Ghi nhận lỗi hạ tầng riêng với lỗi credential sai hoặc session hết hạn.

Fail-closed không có nghĩa mọi endpoint đều phải ngừng hoạt động. Endpoint công khai không phụ thuộc session có thể tiếp tục phục vụ nếu kiến trúc cho phép. Nhưng request cần Authentication từ session phải bị từ chối hoặc trả lỗi tạm thời thay vì được coi là người dùng anonymous một cách âm thầm.

## 4. Phân loại lỗi cần kiểm thử

Một bộ test tốt không chỉ dùng một RuntimeException chung. Hãy mô phỏng các nhóm lỗi có hành vi khác nhau:

| Nhóm lỗi | Ví dụ | Mục tiêu kiểm thử |
|---|---|---|
| Tạm thời | timeout, connection reset, pool exhausted | Xác nhận timeout/retry có giới hạn và request không được xác thực sai |
| Backend unavailable | Redis down, database unavailable | Xác nhận fail-closed và error handling có thể quan sát |
| Authentication/authorization storage | Redis ACL denied, database permission denied | Phát hiện lỗi cấu hình/quyền, không retry vô hạn |
| Schema | thiếu bảng/cột/index, sai migration | Báo lỗi triển khai rõ ràng |
| Serialization | class không tương thích, payload hỏng | Không dùng session dữ liệu lỗi |
| Transaction | deadlock, transaction rollback | Xác nhận không báo lưu thành công khi commit thất bại |
| Capacity | Redis OOM, database quota đầy | Xác nhận create/save fail được truyền đúng |
| Concurrency | optimistic conflict hoặc write race | Xác nhận retry/conflict theo semantics đã định nghĩa |

Lỗi tạm thời có thể được retry với số lần và deadline giới hạn nếu thao tác an toàn. Lỗi schema hoặc permission thường cần can thiệp cấu hình và không nên retry dày. Lỗi serialization cần được ghi nhận như dữ liệu không tương thích hoặc hỏng, không xử lý như một session không tồn tại nếu điều đó che giấu lỗi.

## 5. Kiểm thử findById ném lỗi

Đây là trường hợp quan trọng nhất đối với request đã đăng nhập. Tạo một session hợp lệ, giữ lại cookie session ID, sau đó cấu hình repository test double để ném exception khi filter gọi findById.

Kết quả cần xác nhận:

- Request không đi đến controller bảo vệ như một người dùng anonymous.
- Không trả nội dung được bảo vệ.
- Exception được ghi nhận hoặc chuyển thành response lỗi hạ tầng theo error handling của ứng dụng.
- Không có fallback sang session local hoặc dữ liệu xác thực cũ ngoài chính sách.
- Log/metric chỉ chứa operation, backend và correlation ID; không chứa session ID hay cookie.

Ví dụ với Mockito khi test một component trực tiếp:

~~~java
doThrow(new SessionStoreUnavailableException("session store unavailable"))
        .when(repository).findById("known-session");

assertThrows(SessionStoreUnavailableException.class,
        () -> repository.findById("known-session"));
~~~

Đoạn trên chỉ chứng minh mock được cấu hình ném lỗi. Để kiểm tra hành vi của Spring Session, phải đưa repository lỗi vào application context hoặc filter chain và gửi HTTP request có cookie session tương ứng.

Không cố định mọi ứng dụng phải trả đúng một status code trong mọi môi trường. Nếu exception xảy ra trước DispatcherServlet, ControllerAdvice có thể không bắt được vì lỗi phát sinh ở filter. Servlet container error page, filter-level handler hoặc error dispatch có thể tham gia. Hãy kiểm tra response quan sát được ở runtime thật; thường có thể chọn 503 cho backend tạm thời không sẵn sàng hoặc 500 cho lỗi nội bộ, nhưng không trả 200 với dữ liệu thiếu.

## 6. Kiểm thử createSession ném lỗi

Request có thể tạo session mới khi controller gọi getSession(true), khi authentication flow cần lưu SecurityContext hoặc khi ứng dụng cần ghi flash/session attributes. Nếu createSession thất bại, request không có một session mới hợp lệ để tiếp tục dùng.

Các ca kiểm thử:

- Endpoint tạo session mới khi repository unavailable.
- Login thành công về credential nhưng repository không thể tạo/lưu session.
- Request công khai có thể hoạt động mà không cần session; request có side effect cần session phải xử lý lỗi rõ ràng.
- Không có cookie session giả được phát ra như thể session đã được tạo bền vững.

Nếu ứng dụng dùng form login, lỗi có thể xảy ra ở bước tạo hoặc lưu SecurityContext tùy cấu hình và lifecycle. Test cần xác minh kết quả cuối cùng: request tiếp theo không được xác thực bằng một session không hề tồn tại trong repository.

Không chỉ kiểm tra controller có gọi createSession. Hãy gửi request tiếp theo bằng cookie nhận từ response trước và xác nhận repository có thể khôi phục đúng session cùng Authentication. Đây là cách kiểm tra end-to-end bền vững.

## 7. Kiểm thử save ném lỗi

save có thể được gọi khi session được tạo hoặc thay đổi. Trong Servlet, việc lưu có thể diễn ra khi response được commit hoặc filter hoàn tất lifecycle, nên exception có thể xuất hiện sau khi logic controller đã chạy.

Một test save failure nên:

1. Gửi request làm thay đổi session attribute.
2. Cấu hình repository ném lỗi ở save.
3. Quan sát exception/response cuối cùng sau khi response lifecycle hoàn tất.
4. Dùng một request mới hoặc repository trực tiếp để kiểm tra thay đổi chưa được lưu không xuất hiện như trạng thái bền vững.
5. Xác nhận không có log thành công gây hiểu nhầm.

Không giả định mọi response đã gửi một phần đều có thể đổi thành 5xx. Nếu response đã commit trước khi lỗi được phát hiện, container có thể chỉ ghi log hoặc đóng kết nối. Do đó, test cần bao gồm cả thời điểm lỗi trước commit và lỗi tại commit. Thiết kế ứng dụng không nên gửi xác nhận thành công nghiệp vụ quan trọng trước khi các ghi dữ liệu bắt buộc hoàn tất.

Session không phải nguồn chuẩn cho giao dịch nghiệp vụ. Nếu business transaction đã commit nhưng save session thất bại, giao dịch nghiệp vụ vẫn có thể đã thành công. API cần idempotency và khả năng truy vấn trạng thái nghiệp vụ để client không tạo giao dịch trùng khi retry.

## 8. Kiểm thử deleteById ném lỗi khi logout

Logout có ít nhất hai mục tiêu: xóa SecurityContext/Authentication khỏi ngữ cảnh hiện tại và thu hồi session ở phía server. Nếu deleteById thất bại, cookie bị xóa ở browser không chứng minh session đã bị thu hồi. Một bản sao cookie cũ có thể vẫn dùng được nếu session còn trong repository.

Test logout failure cần:

- đăng nhập và giữ session ID;
- cấu hình repository ném lỗi khi deleteById;
- gọi endpoint logout;
- quan sát response/error theo cấu hình logout handler;
- gửi lại session ID cũ bằng một client độc lập;
- xác minh chính sách bảo vệ khi trạng thái thu hồi chưa được xác nhận.

Nếu yêu cầu bảo mật cần thu hồi ngay, có thể dùng revocation marker hoặc credential/session version trong kho dữ liệu có consistency phù hợp. Marker phải được kiểm tra trên request bảo vệ và có cơ chế hết hạn/cleanup. Đây là thiết kế bổ sung của ứng dụng; Spring Session repository không tự tạo revocation marker khi delete thất bại.

Không báo logout hoàn tất nếu server chưa xác nhận session bị invalidate hoặc có một cơ chế thu hồi thay thế đã được xác nhận. Nếu response logout đã xóa cookie nhưng delete thất bại, phải có cảnh báo và cách xử lý để người dùng không hiểu nhầm rằng mọi bản sao session ID đều vô hiệu.

## 9. Phân biệt session hết hạn với repository lỗi

Một session hết hạn là kết quả nghiệp vụ bình thường. Repository có thể trả null sau khi kiểm tra expiry và thực hiện cleanup theo implementation. Backend unavailable là lỗi hạ tầng; repository không thể xác định session còn tồn tại hay không.

| Tình huống | Kết quả dự kiến |
|---|---|
| Session ID không có trong store | Request không có session |
| Session vượt maxInactiveInterval | Request không có session hợp lệ |
| Redis/JDBC không kết nối được | Request phụ thuộc session gặp lỗi hạ tầng |
| Session payload không deserialize được | Lỗi dữ liệu/serialization được quan sát, không giả thành anonymous |
| Cleanup job thất bại nhưng findById vẫn kiểm tra expiry | Session hết hạn vẫn không được trả như session hợp lệ |

Với JDBC, bản ghi hết hạn có thể còn trong bảng cho đến cleanup job, nhưng repository phải kiểm tra expiry khi tìm theo ID. Với Redis, key expiration và event có thể có độ trễ; không dựa duy nhất vào notification để quyết định session có hợp lệ. Test phải phân biệt trạng thái logic với việc dữ liệu vật lý đã được dọn hay chưa.

## 10. Xây repository test double có thể bật/tắt lỗi

Một cách hữu ích là bọc repository thật bằng decorator có thể ném lỗi theo operation. Test double cần giữ nguyên hành vi bình thường khi không bật lỗi và chỉ ném tại phương thức được chọn.

~~~java
enum RepositoryOperation {
    CREATE, FIND, SAVE, DELETE
}

final class FailingSessionRepository
        implements SessionRepository<MapSession> {

    private final SessionRepository<MapSession> delegate;
    private final AtomicReference<RepositoryOperation> failOn =
            new AtomicReference<>();

    FailingSessionRepository(SessionRepository<MapSession> delegate) {
        this.delegate = delegate;
    }

    void failOn(RepositoryOperation operation) {
        failOn.set(operation);
    }

    void recover() {
        failOn.set(null);
    }

    private void maybeFail(RepositoryOperation operation) {
        if (failOn.compareAndSet(operation, null)) {
            throw new SessionStoreUnavailableException(
                    "Injected repository failure: " + operation);
        }
    }

    @Override
    public MapSession createSession() {
        maybeFail(RepositoryOperation.CREATE);
        return delegate.createSession();
    }

    @Override
    public MapSession findById(String id) {
        maybeFail(RepositoryOperation.FIND);
        return delegate.findById(id);
    }

    @Override
    public void save(MapSession session) {
        maybeFail(RepositoryOperation.SAVE);
        delegate.save(session);
    }

    @Override
    public void deleteById(String id) {
        maybeFail(RepositoryOperation.DELETE);
        delegate.deleteById(id);
    }
}
~~~

Đây là mẫu test double minh họa. SessionStoreUnavailableException là exception do ứng dụng định nghĩa; các import và bean wiring cần bổ sung theo project. compareAndSet làm lỗi chỉ xảy ra một lần ở operation được chọn, giúp test có thể quan sát retry hoặc request kế tiếp.

Trong integration test, đưa decorator này vào vị trí repository mà SessionRepositoryFilter thực sự sử dụng. Tránh chỉ inject test double vào service nhưng filter vẫn dùng repository khác. Nếu dùng Spring Boot auto-configuration, kiểm tra bean override/primary và xác nhận filter nhận đúng bean.

## 11. Ví dụ kiểm thử qua MockMvc

MockMvc có thể chạy request qua Spring MVC và filter chain nếu được cấu hình với WebApplicationContext. Với Spring Boot, thường dùng @SpringBootTest và @AutoConfigureMockMvc để giữ cấu hình gần ứng dụng thật.

Ví dụ khái niệm kiểm thử lỗi khi khôi phục session:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionRepositoryFailureMvcTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    FailingSessionRepository failingRepository;

    @Test
    void repositoryReadFailureMustNotReachProtectedController()
            throws Exception {
        failingRepository.failOn(RepositoryOperation.FIND);

        assertThrows(ServletException.class, () ->
                mockMvc.perform(get("/private")
                        .cookie(new Cookie("SESSION", "known-session"))));
    }
}
~~~

Test minh họa exception có thể thoát khỏi MockMvc nếu không có error dispatch/handler chuyển đổi. Trong ứng dụng có error mapping, thay assertThrows bằng assertion trên status/body phù hợp. Không dùng một assertion duy nhất cho mọi cấu hình; điều cần chứng minh là endpoint bảo vệ không trả dữ liệu và lỗi hạ tầng được ghi nhận.

Cookie name trong ví dụ phải khớp CookieSerializer/HttpSessionIdResolver của ứng dụng. known-session cần được chuẩn bị từ repository test fixture trước khi bật failure nếu filter hoặc resolver cần dữ liệu liên quan.

Nếu MockMvc setup không chạy SessionRepositoryFilter, test này không kiểm tra được Spring Session. Xác minh filter có trong FilterChainProxy/servlet filter registrations của test context hoặc dùng embedded servlet container với HTTP client thật.

## 12. Kiểm thử save failure ở cuối response

Để bắt lỗi xảy ra khi response được commit, tạo endpoint test chỉ sửa session:

~~~java
@PostMapping("/test/session-value")
ResponseEntity<Void> updateSession(HttpServletRequest request) {
    request.getSession(true).setAttribute("theme", "dark");
    return ResponseEntity.noContent().build();
}
~~~

Sau đó cấu hình repository fail ở SAVE và gửi POST qua đầy đủ filter chain. Tùy thời điểm commit, MockMvc có thể ném exception hoặc response có thể đã được commit. Test cần ghi nhận hành vi thực tế và xác nhận một request mới không đọc được giá trị dark như thể save đã thành công.

Trong test production-like, dùng embedded Tomcat/Jetty/Undertow và HTTP client để quan sát response, log và kết nối. Một số khác biệt về commit/flush không được mô phỏng đầy đủ bằng mock request/response.

## 13. Kiểm thử logout failure và replay

Logout là thao tác có side effect ở cả SecurityContext, repository và cookie. Một test mạnh phải giữ lại cookie cũ trước khi logout, vì browser thông thường sẽ tự cập nhật cookie mới hoặc xóa cookie sau response.

Trình tự:

1. Đăng nhập qua endpoint thật và lấy cookie session.
2. Gọi một endpoint bảo vệ để xác nhận cookie hoạt động.
3. Bật lỗi DELETE trong repository test double.
4. Gọi logout và ghi nhận response/exception.
5. Tắt lỗi hoặc phục hồi backend.
6. Gửi lại cookie cũ bằng client không chia sẻ cookie jar.
7. Xác nhận kết quả phù hợp với trạng thái thu hồi thực tế; nếu delete chưa thành công thì phải có cơ chế bảo vệ thay thế hoặc cảnh báo.

Có hai test riêng cần giữ:

- **Delete thành công:** session ID cũ không còn khôi phục được và cookie được xóa.
- **Delete thất bại:** ứng dụng không ghi nhận thu hồi thành công; hệ thống quan sát cảnh báo và chính sách bảo vệ bổ sung hoạt động.

Không viết test chỉ kiểm tra response logout 200 rồi kết luận session đã bị xóa. Hãy xác minh repository state hoặc thử replay ID cũ.

## 14. Retry phải có giới hạn và tính idempotent

Retry có thể hữu ích khi Redis/database gặp lỗi tạm thời, nhưng retry mọi operation vô hạn sẽ giữ request thread, làm cạn connection pool và khuếch đại sự cố.

| Operation | Tính chất retry | Điều cần bảo đảm |
|---|---|---|
| findById | Thường an toàn để retry có giới hạn | Tổng deadline phù hợp request; không chuyển lỗi thành null |
| createSession | Có thể tạo ID/session mới nếu lần đầu đã ghi nhưng response lỗi | Dùng định danh/operation semantics rõ, tránh session mồ côi |
| save | Có thể ghi lặp nhưng phải xác định update có idempotent không | Version/CAS hoặc upsert có semantics rõ |
| deleteById | Xóa lặp thường có thể idempotent nếu contract cho phép | Không trả thành công trước khi biết trạng thái cuối |

Nếu dùng Resilience4j hoặc retry ở client backend, chỉ cấu hình một lớp retry có chủ đích, có backoff và jitter. Không lồng nhiều tầng retry khiến số lần gọi tăng theo cấp số nhân. Phân biệt lỗi transient với lỗi permission, schema hoặc serialization không thể khắc phục bằng retry.

## 15. Không dùng fallback local để che repository outage

Một fallback như “nếu Redis lỗi thì chuyển sang MapSessionRepository” có thể khiến node này tạo session local trong khi các node khác vẫn dùng Redis. Người dùng sẽ gặp đăng xuất ngẫu nhiên theo node, và một số node có thể không áp dụng cùng chính sách thu hồi.

Fallback chỉ hợp lệ nếu đó là một chế độ degraded được thiết kế rõ, có giới hạn chức năng, không duy trì Authentication hoặc quyền nhạy cảm ngoài kho có thẩm quyền, và được kiểm thử. Trong đa số ứng dụng có đăng nhập dựa trên session, trả lỗi tạm thời cho request cần session an toàn hơn việc âm thầm đổi sang store khác.

## 16. Kiểm thử với backend thật

Test double chứng minh ứng dụng phản ứng với exception được tiêm vào, nhưng không mô phỏng hết lỗi mạng, timeout, transaction hoặc connection pool. Cần integration test với backend cùng loại production:

| Backend | Cách gây lỗi trong môi trường test | Điều cần quan sát |
|---|---|---|
| Redis | Dừng container, chặn kết nối, cấu hình timeout ngắn hoặc từ chối ACL | Redis client exception, retry, timeout và response |
| JDBC | Dừng database, thu hồi quyền, dùng connection pool cạn hoặc transaction timeout | DataAccessException, rollback và pool recovery |
| Serialization | Lưu payload không tương thích hoặc converter ném lỗi | Session không bị coi như missing |
| Network | Proxy fault injection hoặc ngắt kết nối có kiểm soát | Thời gian phát hiện lỗi và hành vi fail-closed |

Testcontainers có thể cung cấp Redis/database cô lập cho integration test. Với lỗi mạng, dùng proxy/fault injection trong môi trường test; không làm gián đoạn backend dùng chung của developer hoặc môi trường khác.

Sau khi backend phục hồi, kiểm tra repository có thể phục vụ request mới, connection pool tái tạo kết nối và không còn circuit breaker mở ngoài thời gian dự kiến. Đừng chỉ test thời điểm lỗi; test cả quá trình hồi phục.

## 17. Kiểm thử nhiều instance

Spring Session thường được dùng để chia sẻ session giữa các node. Khi repository gặp lỗi, cần xác minh mọi instance phản ứng nhất quán:

1. Đăng nhập qua node A và lưu cookie.
2. Gửi request tiếp theo qua node B để xác nhận session được chia sẻ.
3. Làm repository unavailable đối với một node hoặc toàn cụm theo kịch bản kiểm thử.
4. Gửi request có cookie cũ qua từng node.
5. Xác nhận không node nào coi lỗi store là session missing rồi cho phép một luồng truy cập sai.
6. Phục hồi backend và xác minh session/thu hồi theo trạng thái đã lưu.

Nếu chỉ một node mất kết nối, cần biết load balancer có tiếp tục gửi request tới node đó hay không. Health check/readiness có thể loại node khỏi traffic khi không thể phục vụ request cần session. Không trả readiness healthy nếu ứng dụng không thể thực hiện chức năng cốt lõi phụ thuộc session.

## 18. Lỗi ở filter và lỗi ở controller khác nhau

SessionRepositoryFilter nằm trước DispatcherServlet. Vì vậy, exception lúc khôi phục session có thể xảy ra trước khi controller được gọi. @ControllerAdvice thường chỉ xử lý exception đi qua cơ chế xử lý của DispatcherServlet; nó không tự động bao phủ mọi exception phát sinh ở servlet filter phía trước.

Để xử lý lỗi đúng:

- dùng error page/Servlet container error dispatch hoặc filter-level exception handling phù hợp;
- giữ thứ tự filter chính xác;
- ánh xạ lỗi hạ tầng sang response thống nhất mà không tiết lộ stack trace;
- ghi log có correlation ID và operation name;
- bảo đảm response không chứa dữ liệu nhạy cảm;
- kiểm thử qua embedded container, không chỉ unit test controller.

Nếu lỗi xảy ra sau khi response đã commit, không thể bảo đảm đổi status/body. Do đó, hãy phát hiện và hoàn tất các thao tác cần thiết trước khi gửi response thành công khi có thể; đồng thời có metric/log cho lỗi commit muộn.

## 19. Quan sát và cảnh báo

Nên theo dõi:

- số lần lỗi theo repository operation: create, find, save, delete;
- tỷ lệ timeout, connection refused, pool exhausted và serialization failure;
- thời gian xử lý repository và retry count;
- số request bị lỗi do session store;
- số lần logout/delete thất bại;
- số session lookup trả missing so với số lookup ném exception;
- thời gian phục hồi sau backend outage;
- số node không đạt readiness do session repository.

Không dùng session ID làm label metric vì cardinality rất lớn và có thể làm lộ credential. Không log cookie hoặc header chứa ID. Dùng operation, backend type, exception class, node ID và correlation ID đã được làm sạch.

Alert cần phân biệt lỗi kéo dài với một lần timeout đơn lẻ. Với tỷ lệ lỗi find/save tăng, có thể cảnh báo mức cao vì đăng nhập, xác thực và trạng thái người dùng bị ảnh hưởng. Với lỗi cleanup job, đánh giá riêng vì repository có thể vẫn kiểm tra expiry trong findById.

## 20. Ma trận kiểm thử tối thiểu

| ID | Điểm lỗi | Thiết lập | Kết quả cần xác nhận |
|---|---|---|---|
| R-01 | findById | Trả null | Request không có session và không được coi là authenticated |
| R-02 | findById | Ném timeout | Lỗi hạ tầng được quan sát; endpoint bảo vệ không trả dữ liệu |
| R-03 | findById | Ném serialization exception | Không giả thành session missing |
| R-04 | createSession | Ném lỗi | Không tạo cookie/session thành công giả |
| R-05 | save | Ném lỗi trước commit | Thay đổi session không được xem là đã lưu |
| R-06 | save | Ném lỗi khi commit response | Ghi nhận lỗi muộn; không báo thành công bền vững |
| R-07 | deleteById | Ném lỗi khi logout | Không tuyên bố revoke thành công; replay được kiểm tra |
| R-08 | deleteById | Thành công | ID cũ không khôi phục session |
| R-09 | expiration | Session hết hạn | Repository không trả session hợp lệ |
| R-10 | recovery | Backend phục hồi | Request mới hoạt động, không cần restart node nếu client hỗ trợ |
| R-11 | multi-node | A và B cùng store | Mọi node áp dụng cùng kết quả lỗi/thu hồi |
| R-12 | fallback | Backend down | Không chuyển âm thầm sang local session store |

Test suite nên chạy định kỳ với backend thật và trong pipeline trước khi nâng phiên bản Spring Session, Spring Security, Redis client hoặc JDBC driver.

## 21. Lỗi thường gặp khi viết test

| Sai lầm | Vì sao không đủ | Cách sửa |
|---|---|---|
| Mock controller/service thay vì repository | Không đi qua SessionRepositoryFilter | Tiêm lỗi vào repository bean mà filter dùng |
| Chỉ test findById trả null | Không kiểm tra exception từ storage | Thêm timeout/unavailable/serialization failure |
| Chỉ assert status 500 | Không chứng minh dữ liệu bảo vệ không bị trả | Assert body, controller invocation và Authentication |
| Chỉ assert logout trả 200 | Cookie có thể đã xóa nhưng session server còn | Replay ID cũ và kiểm tra repository |
| Chỉ test unit | Không mô phỏng filter order và response commit | Thêm MockMvc filter-chain và embedded-container test |
| Catch exception rồi trả null | Che giấu backend outage | Giữ exception phân loại và error mapping |
| Retry vô hạn | Có thể làm cạn thread/connection pool | Deadline, backoff, giới hạn retry và circuit breaker |
| Test chỉ trên một node | Bỏ sót khác biệt store/namespace | Test request luân phiên giữa các instance |
| Log cookie để debug | Làm lộ bearer credential | Redact và dùng correlation ID |

## 22. Quy trình thực hiện kiểm thử

1. Xác định repository bean thực tế được SessionRepositoryFilter sử dụng.
2. Liệt kê các operation và exception có thể phát sinh.
3. Viết contract test cho missing, expired và storage failure.
4. Dùng repository decorator để tiêm lỗi theo operation.
5. Chạy MockMvc qua toàn bộ filter chain.
6. Chạy embedded-container test cho response commit và error dispatch.
7. Chạy integration test với Redis/JDBC thật và fault injection.
8. Chạy test nhiều instance và replay cookie cũ.
9. Kiểm tra metric, log, alert và recovery sau khi backend hoạt động lại.
10. Tài liệu hóa status code, retry policy và runbook theo ứng dụng.

## 23. Nguyên tắc kết luận

- null từ findById là không có session; exception là không thể xác định trạng thái vì lỗi.
- Không chuyển backend outage thành anonymous session hoặc fallback local ngoài thiết kế.
- Kiểm thử cả create, find, save và delete; mỗi operation có thời điểm lỗi riêng.
- Kiểm thử qua SessionRepositoryFilter và Spring Security filter chain.
- Xác nhận lỗi save có thể xảy ra khi response commit, sau khi controller đã chạy.
- Xác nhận logout chỉ hoàn tất khi session bị thu hồi hoặc cơ chế revoke thay thế được xác nhận.
- Replay cookie cũ sau logout/expiration để chứng minh ID không còn dùng được.
- Dùng backend thật, fault injection và nhiều instance để kiểm tra timeout, transaction và recovery.
- Giới hạn retry, phân biệt lỗi tạm thời với lỗi cấu hình/dữ liệu.
- Không log session ID, cookie hoặc SecurityContext.

Kiểm thử repository failure phải chứng minh ứng dụng giữ được ranh giới giữa session không tồn tại và session store không thể truy cập. Khi repository ném lỗi, request phụ thuộc xác thực session cần đi vào error path có thể quan sát và không được cấp quyền dựa trên trạng thái không xác định. Khi save hoặc delete thất bại, ứng dụng phải phản ánh đúng việc dữ liệu chưa được lưu hoặc chưa được thu hồi. Chỉ test xuyên filter chain, response lifecycle, backend thật và nhiều instance mới cho thấy hành vi đó có đúng trong môi trường Servlet đang vận hành hay không.

## Tài liệu tham khảo

- Spring Session – HttpSession integration: https://docs.spring.io/spring-session/reference/http-session.html
- Spring Session – API SessionRepository: https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/SessionRepository.html
- Spring Framework – Servlet filters: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot – Testing Spring Boot applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Testcontainers for Java: https://java.testcontainers.org/
