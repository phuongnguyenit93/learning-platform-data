# Số lần truy cập kho do một yêu cầu đọc hoặc sửa phiên

Mỗi HTTP request có thể làm phát sinh một hoặc nhiều thao tác đến kho session, nhưng số lần truy cập không phải lúc nào cũng bằng số lần controller gọi getAttribute() hoặc setAttribute(). Spring Session tải session qua SessionRepositoryFilter, giữ session trong request hiện tại, cập nhật metadata và lưu thay đổi khi response được commit. Flush mode, save mode, repository Redis/JDBC và các thành phần như Spring Security đều ảnh hưởng đến số thao tác thực tế.

Để tối ưu hiệu năng, cần đo riêng hai lớp:

- **Repository call:** số lần ứng dụng gọi createSession(), findById(), save() hoặc deleteById().
- **Backend operation:** số Redis command, pipeline/script hoặc SQL statement mà một repository call tạo ra.

Một lần findById() có thể cần nhiều thao tác ở backend để đọc metadata, attributes hoặc index. Một lần save() có thể ghi nhiều field, cập nhật TTL và index. Vì vậy, không thể suy ra số Redis command hoặc SQL statement chỉ từ số lần gọi SessionRepository.

## 1. Vòng đời session trong một HTTP request

Với ứng dụng Servlet, SessionRepositoryFilter bọc request/response và cung cấp HttpSession dựa trên repository. Khi một thành phần trong ứng dụng cần session, filter dùng HttpSessionIdResolver để lấy session ID từ cookie hoặc header rồi tải session từ kho.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SessionRepositoryFilter
    participant R as SessionRepository
    participant A as Controller/Security
    participant S as Redis/JDBC

    C->>F: HTTP request + session ID
    F->>F: Resolve ID; tạo request wrapper
    A->>F: getSession()
    F->>R: findById(id)
    R->>S: Đọc dữ liệu session
    S-->>R: Session record
    R-->>F: Session object
    F-->>A: HttpSession wrapper
    A->>F: getAttribute / setAttribute
    Note over F,A: Thao tác thuộc tính chủ yếu trên object trong request
    F->>R: save(session) nếu mới hoặc thay đổi
    R->>S: Ghi dữ liệu và expiration
    F-->>C: HTTP response
~~~

Các bước chính:

1. Resolver đọc định danh từ request. Bản thân việc đọc cookie/header chưa nhất thiết truy cập Redis/JDBC.
2. Session thường được tải khi một thành phần thực sự yêu cầu HttpSession.
3. Filter giữ session object trong request wrapper để các lần truy cập sau dùng lại.
4. Controller và security code đọc hoặc thay đổi attributes trên session object.
5. Khi response được commit, filter lưu session mới hoặc session đã thay đổi theo lifecycle của repository.
6. Nếu session bị invalidate, filter/repository xử lý xóa session và resolver xóa định danh ở response.

Điều này giải thích vì sao số lần gọi repository không tăng tuyến tính theo số lần gọi getAttribute() trong cùng một request.

## 2. Phân biệt số lần gọi repository và số lần truy cập backend

Giả sử controller gọi getAttribute() năm lần. Nếu session đã được tải một lần ở đầu request, năm lần đọc đó thường chỉ thao tác trên session object trong bộ nhớ của request. Chúng không nhất thiết tạo năm lần findById().

Ngược lại, một lần save(session) có thể dẫn đến nhiều thao tác backend:

- Redis: ghi hash/field, cập nhật TTL, cập nhật key expiration hoặc index tùy repository và cấu hình.
- JDBC: cập nhật hàng metadata, ghi/xóa các hàng attributes và thực hiện transaction hoặc batch statement.

| Lớp đo | Ví dụ | Dùng để trả lời |
| --- | --- | --- |
| HTTP request | Một request GET hoặc POST | Một thao tác nghiệp vụ tạo ra tải session thế nào? |
| Repository API | findById, save, deleteById | Spring Session gọi abstraction bao nhiêu lần? |
| Backend operation | Redis command, SQL statement | Một repository call tiêu tốn bao nhiêu thao tác dữ liệu? |
| Network round trip | Request/response giữa app và kho | Độ trễ mạng đóng góp bao nhiêu? |
| Resource usage | CPU, connection pool, Redis memory | Chi phí tổng thể của session store là gì? |

Khi báo cáo hiệu năng, ghi rõ đang đếm lớp nào. Một chỉ số mang tên session store calls không nên trộn repository method với Redis command hoặc SQL statement.

## 3. Request không sử dụng session

Một request công khai không truy cập HttpSession thường không cần tải session từ repository. Nếu không có controller, security filter hoặc framework component nào gọi getSession(), repository có thể không nhận findById() hay save() cho request đó.

Tuy nhiên, đừng chỉ nhìn controller để kết luận request không dùng session. Các thành phần sau có thể truy cập session:

- Spring Security lưu hoặc tải SecurityContext theo chiến lược session.
- CSRF token repository có thể dùng HttpSession.
- Saved request hoặc authentication flow có thể tạo session.
- Flash attributes, MVC flow hoặc thư viện ứng dụng có thể dùng session.
- Custom filter/interceptor có thể gọi getSession() để ghi metadata.

Do đó, một endpoint tưởng như stateless vẫn có thể tạo repository traffic nếu filter chain hoặc middleware chạm vào session.

Để kiểm chứng, gửi request qua toàn bộ filter chain thật và đo repository call. Unit test gọi trực tiếp controller không thể phát hiện truy cập session ẩn ở tầng Servlet filter.

## 4. Tải session một lần trong request

Khi request có session ID hợp lệ và một thành phần yêu cầu session, filter thường gọi findById() để tải session. Session object sau đó được giữ trong request wrapper.

Ví dụ:

~~~java
@GetMapping("/profile")
ProfileView profile(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }

    String displayName =
        (String) session.getAttribute("displayName");
    String locale =
        (String) session.getAttribute("locale");
    Integer cartCount =
        (Integer) session.getAttribute("cartCount");

    return new ProfileView(displayName, locale, cartCount);
}
~~~

Trong request này, ba lần getAttribute() thường đọc từ cùng session object đã tải. Không cần gọi findById() riêng cho từng attribute. Nếu code gọi getSession(false) nhiều lần, request wrapper thường trả lại session hiện có thay vì tải lại.

Hành vi này phụ thuộc việc dùng đúng HttpServletRequest wrapper do SessionRepositoryFilter cung cấp. Nếu code tự tạo repository lookup ngoài filter, gọi trực tiếp SessionRepository nhiều lần hoặc chạy tác vụ ngoài request, số lần truy cập có thể tăng.

## 5. Request chỉ đọc session

Một request chỉ đọc attributes thường có ít nhất một lần tải session nếu session chưa được tải trước đó. Nhưng số lần save ở cuối request phụ thuộc việc session có được xem là thay đổi hay không.

Spring Session cập nhật lastAccessedTime khi session được sử dụng theo request lifecycle. Việc cập nhật metadata này có thể làm session cần được lưu lại dù controller không gọi setAttribute(). Vì vậy, không mặc định một request đọc session chỉ có một repository call.

Một mô hình phổ biến:

| Bước | Repository call có thể phát sinh | Lý do |
| --- | --- | --- |
| Lấy session hiện có | 1 findById | Tải session theo ID |
| Đọc nhiều attributes | Thường 0 call bổ sung | Đọc từ session object trong request |
| Cập nhật lastAccessedTime | Không nhất thiết là call ngay | Metadata thay đổi trong session object |
| Commit response | Có thể 1 save | Persist lastAccessedTime hoặc thay đổi được theo dõi |

Với repository và cấu hình tối ưu không ghi khi không có thay đổi cần lưu, request chỉ đọc có thể chỉ cần một lần findById. Với implementation lưu lastAccessedTime ở cuối request, nó có thể cần thêm một lần save. Đo trên phiên bản và cấu hình thực tế để biết chính xác.

## 6. Request sửa một hoặc nhiều attributes

Khi request tải session rồi gọi setAttribute(), thay đổi thường được giữ trên session object cho đến khi filter commit response. Với flush mode lưu cuối request, nhiều lần sửa trong cùng request có thể được gom vào một lần save ở cuối.

Ví dụ:

~~~java
@PostMapping("/preferences")
void updatePreferences(
        HttpServletRequest request,
        @RequestBody PreferenceUpdate update) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }

    session.setAttribute("locale", update.locale());
    session.setAttribute("theme", update.theme());
    session.setAttribute("compactMode", update.compactMode());
}
~~~

Nếu session đã tồn tại, một mô hình điển hình là một findById() khi tải và một save() khi commit. Ba lần setAttribute() không đồng nghĩa ba lần save() khi các thay đổi được buffer đến cuối request.

Nếu flush mode là IMMEDIATE, repository có thể ghi ngay khi thay đổi được thực hiện. Khi đó, nhiều lần cập nhật có thể tạo nhiều lần save hoặc backend write. Một số implementation có thể gộp hoặc tối ưu một phần thao tác; không giả định một setAttribute luôn bằng đúng một Redis command.

## 7. Request tạo session mới

Khi request gọi getSession(true) và không có session hợp lệ, Spring Session tạo session object mới. createSession() thường tạo object và ID ở tầng repository; thao tác lưu bền vững thường xảy ra khi session được commit.

Mô hình phổ biến:

| Bước | Repository call | Ý nghĩa |
| --- | --- | --- |
| Tạo session object | 1 createSession | Cấp ID và metadata ban đầu |
| Đặt nhiều attributes | Không nhất thiết gọi repository ngay | Cập nhật object mới trong request |
| Commit response | 1 save | Lưu session mới vào kho |
| Phát định danh | Không phải repository call | Resolver ghi cookie/header vào response |

Nếu request có cookie chứa ID cũ nhưng session không tồn tại hoặc đã hết hạn, filter có thể cần lookup trước khi tạo session mới. Vì vậy, một request tạo mới không có cookie và một request mang cookie stale có thể có số repository call khác nhau.

## 8. Request invalidate hoặc logout

Khi ứng dụng gọi HttpSession.invalidate() hoặc Spring Security logout handler kết thúc session, repository cần xóa session tương ứng. Nếu session chưa được tải trước đó, thao tác logout có thể cần lookup để xác định phiên; nếu đã tải, filter có thể đã có ID và session object trong request.

Một luồng logout có thể bao gồm:

- Tải session hiện tại nếu cần.
- Xóa SecurityContext và các thuộc tính theo logout handlers.
- Gọi deleteById() hoặc thao tác tương đương để xóa session.
- Resolver phát Set-Cookie hết hạn hoặc header định danh rỗng.

Việc xóa cookie/header là thao tác response, không phải repository call. Một request logout có thể có một lần findById và một lần deleteById, nhưng số lần thực tế phụ thuộc session đã được tải trước đó và cách logout filter tích hợp với Spring Session.

Không dùng endpoint logout tự viết chỉ gọi removeAttribute() để thay thế invalidate nếu mục tiêu là kết thúc toàn bộ phiên.

## 9. FlushMode và thời điểm ghi

Với Spring Session Redis, flush mode quyết định khi nào thay đổi session được ghi xuống Redis:

- ON_SAVE: ghi thay đổi khi repository save được gọi, thường ở cuối request khi filter commit session.
- IMMEDIATE: ghi thay đổi sớm nhất có thể khi session được thay đổi.

Ví dụ cấu hình:

~~~yaml
spring:
  session:
    redis:
      flush-mode: on-save
~~~

ON_SAVE thường giúp gom nhiều thay đổi trong một request và giảm số lần ghi. Đổi lại, dữ liệu chỉ được lưu khi request hoàn tất/commit theo lifecycle. Nếu tiến trình dừng giữa request, thay đổi chưa commit có thể không được ghi.

IMMEDIATE phù hợp với một số nhu cầu cần ghi sớm, nhưng có thể tăng write traffic khi một request sửa nhiều attributes. Đo số lần save và backend command trước khi chọn.

Property và hành vi cụ thể cần được xác nhận theo phiên bản Spring Session đang dùng. Không áp dụng kết luận từ Redis repository cho JDBC hoặc custom repository nếu implementation có semantics khác.

## 10. SaveMode và phạm vi attributes được ghi

Save mode của Redis repository quyết định attribute nào được đưa vào thao tác lưu:

- ON_SET_ATTRIBUTE: lưu attributes được set trong request.
- ON_GET_ATTRIBUTE: lưu attributes được set hoặc được truy cập, theo semantics của implementation.
- ALWAYS: lưu toàn bộ attributes của session.

Ví dụ:

~~~yaml
spring:
  session:
    redis:
      save-mode: on-set-attribute
~~~

SaveMode không phải bộ đếm số lần gọi repository. Nó ảnh hưởng phạm vi dữ liệu được ghi trong save. Một repository save() vẫn có thể chỉ là một lần gọi API nhưng serialize/ghi số lượng attributes khác nhau.

Nếu ứng dụng lưu nhiều attributes lớn, ALWAYS có thể làm tăng serialization và dữ liệu truyền. ON_SET_ATTRIBUTE có thể giảm lượng ghi nhưng yêu cầu code cập nhật attributes theo cách implementation nhận biết được thay đổi. Kiểm thử cả mutable object và thao tác removeAttribute().

## 11. Redis: một repository call có thể thành nhiều command

Redis repository có thể lưu session thành hash và quản lý expiration/index bằng các key phụ trợ. Tùy implementation, một lần findById() hoặc save() có thể cần nhiều lệnh Redis.

Ví dụ các thao tác backend có thể bao gồm:

- Đọc hash chứa session metadata và attributes.
- Cập nhật lastAccessedTime.
- Ghi field attributes thay đổi.
- Đặt hoặc gia hạn TTL.
- Tạo/xóa key expiration.
- Cập nhật principal index nếu dùng indexed repository.
- Xóa session và các key phụ trợ khi logout/expiration.

Pipeline, script hoặc client implementation có thể thay đổi số round trip. Redis Cluster cũng có thể ảnh hưởng phân phối key và độ trễ. Vì vậy, đo bằng Redis command stats, client metrics hoặc tracing ở tầng Redis khi cần phân tích chi tiết.

Không suy ra một save() luôn bằng một lệnh HSET hoặc một findById() luôn bằng một lệnh HGETALL. Đó là chi tiết implementation và có thể đổi giữa phiên bản.

## 12. JDBC: một repository call có thể thành nhiều SQL statement

Spring Session JDBC thường lưu metadata trong bảng session và attributes trong bảng phụ. Một lần findById() có thể đọc hàng session và attributes; một lần save() có thể insert/update metadata và thay đổi rows attributes.

Các yếu tố ảnh hưởng:

- Số lượng attributes.
- Attribute nào thay đổi hoặc bị xóa.
- Batch update và transaction.
- Index và query plan.
- Connection pool và database latency.
- Cơ chế cleanup session hết hạn.

Đếm repository.save() không cho biết chính xác số SQL statement. Dùng datasource proxy, JDBC metrics hoặc database statement statistics để đo số SELECT/INSERT/UPDATE/DELETE và thời gian của chúng.

Không bật SQL bind parameter logging chứa session attributes nhạy cảm ở production chỉ để đếm query. Dùng metrics an toàn hoặc môi trường kiểm thử với dữ liệu giả.

## 13. Các yếu tố làm tăng số lần truy cập kho

Một request có thể tạo thêm repository calls do:

- Nhiều filter/interceptor cùng truy cập session nhưng wrapper cache có thể vẫn tránh lookup lặp.
- Code gọi trực tiếp repository thay vì dùng HttpSession hiện tại.
- Principal/session index lookup để tìm các phiên của người dùng.
- Session fixation protection đổi ID sau authentication.
- Logout hoặc thu hồi session.
- Session mới được tạo trong request vốn ban đầu không cần session.
- FlushMode IMMEDIATE khiến nhiều lần cập nhật được ghi sớm.
- Retry khi backend lỗi hoặc transaction cần chạy lại.
- Event listener hoặc tác vụ phụ trợ thực hiện lookup riêng.

Ngược lại, một số thao tác không tạo repository call:

- Đọc nhiều attributes từ session object đã tải trong request.
- Gọi getSession() lần thứ hai trong cùng request khi wrapper đã có session.
- Đọc cookie/header để lấy ID trước khi repository thực sự được yêu cầu.
- Ghi response cookie sau khi ID đã được xác định.

Hãy phân tích call graph thực tế thay vì đếm số lần xuất hiện của getAttribute() trong source code.

## 14. Đo repository calls bằng decorator

Có thể bọc SessionRepository để đếm số lần gọi từng phương thức ở abstraction level. Ví dụ dưới đây minh họa một decorator dùng Micrometer:

~~~java
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import io.micrometer.core.instrument.MeterRegistry;

class MeteredSessionRepository<S extends Session>
        implements SessionRepository<S> {

    private final SessionRepository<S> delegate;
    private final MeterRegistry meters;

    MeteredSessionRepository(
            SessionRepository<S> delegate,
            MeterRegistry meters) {
        this.delegate = delegate;
        this.meters = meters;
    }

    private void count(String operation) {
        meters.counter(
            "spring.session.repository.calls",
            "operation", operation
        ).increment();
    }

    @Override
    public S createSession() {
        count("create");
        return delegate.createSession();
    }

    @Override
    public void save(S session) {
        count("save");
        delegate.save(session);
    }

    @Override
    public S findById(String id) {
        count("find");
        return delegate.findById(id);
    }

    @Override
    public void deleteById(String id) {
        count("delete");
        delegate.deleteById(id);
    }
}
~~~

Đây là mẫu minh họa; cần đăng ký decorator sao cho nó bọc đúng repository mà SessionRepositoryFilter sử dụng. Tránh tạo vòng phụ thuộc khi bean decorator inject chính bean đã bị thay thế. Có thể dùng bean delegate có qualifier hoặc BeanPostProcessor/FactoryBean phù hợp với cấu hình ứng dụng.

Không gắn session ID, username, tenant ID hoặc cookie vào metric tag vì sẽ tạo high cardinality và có thể làm lộ dữ liệu nhạy cảm. Dùng tag có tập giá trị nhỏ như operation, backend và result.

Decorator trên đếm số lần gọi method, không đếm Redis command hay SQL statement. Để đo backend, bổ sung instrumentation ở Redis client hoặc DataSource.

## 15. Đo latency và lỗi theo từng thao tác

Ngoài số lần gọi, cần đo thời gian và tỷ lệ lỗi:

- findById latency và lỗi.
- save latency và lỗi.
- deleteById latency và lỗi.
- createSession rate.
- Repository call count trên mỗi HTTP request.
- Backend connection pool wait và network round trip.

Micrometer Timer có thể ghi thời gian của từng thao tác. Khi triển khai, dùng try/finally để timer luôn được dừng kể cả khi delegate ném exception. Tách kết quả success/error bằng tag có số lượng giá trị nhỏ.

Đo p50, p95 và p99 thay vì chỉ xem trung bình. Một tỷ lệ nhỏ request có save chậm hoặc Redis timeout có thể ảnh hưởng lớn đến p99 và trải nghiệm đăng nhập.

## 16. Kiểm thử số lần gọi repository cho một request

Có thể dùng repository decorator đếm calls trong integration test. Đặt counter về 0 trước request, gửi request qua HTTP filter chain, rồi đọc số lần find/save/delete.

Ma trận ví dụ:

| Scenario | findById | createSession | save | deleteById |
| --- | ---: | ---: | ---: | ---: |
| Request không dùng session | Thường 0 | 0 | 0 | 0 |
| Tạo session mới không có ID cũ | 0 | Thường 1 | Thường 1 | 0 |
| Đọc session hiện có | Thường 1 | 0 | Có thể 0 hoặc 1 | 0 |
| Sửa session hiện có với ON_SAVE | Thường 1 | 0 | Thường 1 | 0 |
| Sửa session với IMMEDIATE | Thường 1 | 0 | Có thể nhiều hơn 1 | 0 |
| Invalidate session hiện có | Có thể 1 | 0 | Thường 0 | Thường 1 |

Bảng là mô hình thường gặp, không phải cam kết số lượng bất biến cho mọi phiên bản/repository. Việc đọc session có thể kích hoạt save để lưu lastAccessedTime. Request có cookie stale có thể cần lookup trước khi tạo mới. Security filter cũng có thể làm thay đổi số calls.

Test nên cố định:

- Spring Session version và backend.
- FlushMode/SaveMode.
- Filter chain và controller.
- Cookie/header resolver.
- Session state ban đầu.
- Có hay không Spring Security.

Sau đó, đặt assertion theo hợp đồng của ứng dụng. Nếu nâng phiên bản làm số call thay đổi, xem xét lý do trước khi điều chỉnh test; đừng tự động nới assertion để che một regression.

## 17. Kiểm thử backend operation count

Để đếm Redis command:

- Dùng Redis client metrics hoặc instrumentation phù hợp.
- Dùng command statistics trong môi trường kiểm thử cô lập.
- Phân biệt lệnh do Spring Session với lệnh của cache hoặc ứng dụng khác.
- Gắn correlation ID ở tracing, không gắn session ID.

Để đếm SQL:

- Dùng datasource-proxy hoặc JDBC instrumentation.
- Lọc statement theo schema/table session.
- Phân biệt statement thực thi, batch statement và round trip.
- Tắt bind parameter capture nếu payload có dữ liệu nhạy cảm.

Không dùng Redis MONITOR hoặc SQL debug logging rộng trong production để theo dõi liên tục; các công cụ này có thể tạo overhead lớn hoặc lộ dữ liệu. Dùng chúng ngắn hạn trong môi trường được kiểm soát nếu thực sự cần.

## 18. Tối ưu khi số lần truy cập quá cao

Nếu mỗi request tạo nhiều repository calls hơn dự kiến:

1. Xác định thành phần nào đầu tiên gọi getSession().
2. Kiểm tra có code gọi repository trực tiếp nhiều lần ngoài request wrapper không.
3. Kiểm tra FlushMode và SaveMode.
4. Kiểm tra có nhiều filter/interceptor cùng sửa attributes không.
5. Kiểm tra Session ID rotation, principal index và logout flow.
6. Đo backend command/SQL để tìm save nặng hay lookup chậm.
7. Giảm kích thước và số lượng attributes trong session.
8. Đưa dữ liệu nghiệp vụ lớn hoặc thường xuyên thay đổi ra cache/database chuyên biệt.

Không loại bỏ cập nhật lastAccessedTime chỉ để giảm một lần ghi nếu việc đó làm thay đổi semantics timeout. Cần hiểu tác động bảo mật và thời hạn session trước khi tùy chỉnh.

Nếu một request chỉ cần một giá trị nhỏ nhưng đang tải session rất lớn, xem xét giảm dữ liệu lưu trong session. Session nên giữ trạng thái xác thực và dữ liệu tạm cần thiết, không phải một bản sao của toàn bộ hồ sơ hoặc giỏ hàng lớn.

## 19. Các lỗi đo lường thường gặp

| Nhận định sai | Vì sao sai | Cách đo đúng |
| --- | --- | --- |
| Năm lần getAttribute là năm lần Redis read | Attributes thường được đọc từ session object đã tải | Đếm findById ở repository và command ở Redis |
| Một save tương đương một SQL UPDATE | JDBC có thể cập nhật metadata và nhiều rows attributes | Dùng JDBC statement instrumentation |
| Request đọc session không bao giờ ghi | lastAccessedTime có thể được cập nhật và lưu | Đo save ở cuối request với cấu hình thật |
| Cookie có mặt nghĩa là đã đọc Redis | Resolver có thể chỉ đọc header; repository load thường lazy | Đo khi session thực sự được truy cập |
| Tất cả request POST đều tạo session | Chỉ request có thành phần yêu cầu session mới tạo | Kiểm tra filter chain và session creation |
| FlushMode IMMEDIATE chỉ nhanh hơn | Nó có thể tăng số lần ghi và round trip | So sánh throughput, write count và p99 |
| Số repository call bằng số network round trip | Một method có thể dùng pipeline hoặc nhiều command | Đo ở client/backend layer |

## 20. Checklist giám sát và kiểm thử

- [ ] Đo riêng createSession, findById, save và deleteById.
- [ ] Đếm repository calls theo request và theo loại endpoint.
- [ ] Đo Redis command hoặc SQL statement ở tầng backend riêng.
- [ ] Ghi latency p50/p95/p99 và tỷ lệ lỗi cho từng thao tác.
- [ ] Kiểm tra request không dùng session có thực sự không truy cập repository.
- [ ] Kiểm tra request đọc có cập nhật lastAccessedTime và có save hay không.
- [ ] So sánh ON_SAVE với IMMEDIATE bằng workload thực tế.
- [ ] So sánh SaveMode theo kích thước attributes và số lần ghi.
- [ ] Đo tác động của Spring Security, CSRF, saved request và logout.
- [ ] Không dùng session ID, cookie hoặc username làm metric tag.
- [ ] Không bật Redis MONITOR hoặc SQL bind logging liên tục trong production.
- [ ] Giữ assertion call count gắn với phiên bản, backend và cấu hình đã cố định.

Số lần truy cập kho của một request phụ thuộc vào việc session có được yêu cầu hay không, session có tồn tại hay phải tạo mới, metadata có thay đổi, request có sửa attributes, session có bị invalidate và repository đang dùng flush/save mode nào. Trong một request, nhiều lần đọc attributes thường dùng cùng session object đã tải; số repository calls vì vậy không tăng theo từng getAttribute(). Để tối ưu đúng, hãy đo riêng repository API và backend operations, sau đó đối chiếu kết quả với vòng đời SessionRepositoryFilter và cấu hình Redis/JDBC thực tế.
