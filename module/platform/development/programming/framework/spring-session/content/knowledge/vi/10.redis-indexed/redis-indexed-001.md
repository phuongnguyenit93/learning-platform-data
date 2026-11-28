# RedisIndexedSessionRepository và nhu cầu tra cứu phiên theo principal

Trong ứng dụng Spring Session, một người dùng có thể đăng nhập từ nhiều trình duyệt hoặc thiết bị. Mỗi lần đăng nhập thường tạo một session riêng, nhưng ứng dụng quản trị có thể cần tìm tất cả session của người dùng để hiển thị thiết bị đang hoạt động, giới hạn số phiên hoặc thu hồi một phiên cụ thể khi người dùng báo mất thiết bị.

Repository Redis cơ bản chủ yếu tìm session theo session ID. Khi cần tìm theo danh tính người dùng, Spring Session cung cấp RedisIndexedSessionRepository và API FindByIndexNameSessionRepository. Repository indexed duy trì chỉ mục principal name trong Redis để ứng dụng truy vấn các session thuộc một principal mà không phải tự quét toàn bộ key session.

Bài này trình bày cách hoạt động của chỉ mục principal, cách cấu hình và gọi API, cách tích hợp với Spring Security, cách thu hồi session an toàn, cùng các giới hạn cần tính đến khi vận hành nhiều instance.

## 1. Vì sao cần tra cứu session theo principal?

Session ID xác định một phiên cụ thể. Principal name xác định danh tính đã đăng nhập, ví dụ username hoặc tên định danh do Authentication cung cấp. Một principal có thể sở hữu nhiều session:

| Principal | Thiết bị | Session |
|---|---|---|
| linh.nguyen | Laptop | Session A |
| linh.nguyen | Điện thoại | Session B |
| linh.nguyen | Máy tính bảng | Session C |
| minh.tran | Laptop | Session D |

Nếu ứng dụng chỉ biết session ID, nó có thể tải một session cụ thể nhưng không có cách tổng quát để hỏi “người dùng linh.nguyen đang có những session nào?”. Việc quét toàn bộ key trong Redis để tìm thuộc tính người dùng vừa tốn kém vừa phụ thuộc cấu trúc key nội bộ.

Tra cứu theo principal hữu ích cho các chức năng:

- Xem các phiên đăng nhập của một tài khoản.
- Đăng xuất một thiết bị bị mất hoặc không còn tin cậy.
- Thu hồi tất cả session khi tài khoản bị khóa hoặc mật khẩu bị thay đổi.
- Áp dụng chính sách giới hạn số phiên đồng thời.
- Hỗ trợ bộ phận vận hành điều tra sự cố đăng nhập.
- Kiểm tra session của người dùng khi xử lý yêu cầu bảo mật.

Cần phân biệt principal với session ID:

- **Session ID** là định danh của một phiên cụ thể, thường được gửi trong cookie.
- **Principal name** là tên định danh của người dùng sau khi xác thực, thường lấy từ Authentication.getName().
- **Index** là cấu trúc phụ trong repository, ánh xạ principal name tới các session ID tương ứng.

Principal name không nhất thiết là email. Nó phải là định danh ổn định mà hệ thống xác thực sử dụng. Nếu username có thể đổi, cần xác định cách xử lý chỉ mục và các session đang tồn tại khi đổi tên.

## 2. RedisSessionRepository và RedisIndexedSessionRepository

Spring Session cung cấp hai implementation Redis thường gặp:

| Repository | Cách tìm session | Tra cứu theo principal | Mục đích |
|---|---|---|---|
| RedisSessionRepository | Theo session ID | Không cung cấp API indexed theo principal | Ứng dụng chỉ cần lưu và tải session bằng ID |
| RedisIndexedSessionRepository | Theo session ID và các chỉ mục | Có, qua FindByIndexNameSessionRepository | Ứng dụng cần quản trị hoặc tìm nhiều session theo principal |

Cả hai đều lưu session vào Redis và có thể dùng trong ứng dụng nhiều instance. Điểm khác biệt chính của repository indexed là duy trì các chỉ mục bổ sung, trong đó chỉ mục principal name là trường hợp quan trọng nhất.

Chỉ mục mang lại khả năng truy vấn nhanh theo danh tính nhưng cũng tạo thêm công việc ghi và dọn dữ liệu. Khi session được tạo, cập nhật principal hoặc bị xóa/hết hạn, repository phải cập nhật cấu trúc chỉ mục tương ứng. Vì vậy, không nên chọn repository indexed chỉ vì tên gọi có vẻ đầy đủ hơn; hãy chọn khi ứng dụng thực sự cần truy vấn theo principal hoặc các index đã cấu hình.

### API FindByIndexNameSessionRepository

Giao diện FindByIndexNameSessionRepository mở rộng SessionRepository và bổ sung thao tác tìm theo tên chỉ mục cùng giá trị chỉ mục. API thường dùng nhất là:

~~~java
Map<String, S> findByIndexNameAndIndexValue(
        String indexName,
        String indexValue
);

Map<String, S> findByPrincipalName(String principalName);
~~~

findByPrincipalName là phương thức tiện ích sử dụng chỉ mục principal name mặc định. Kết quả là Map trong đó key là session ID và value là đối tượng Session tương ứng.

Hằng số tên chỉ mục mặc định được cung cấp bởi:

~~~java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
~~~

Không cần tự xây dựng câu lệnh Redis để đọc set index. Hãy dùng API repository để Spring Session chịu trách nhiệm về cấu trúc lưu trữ và tính nhất quán của index.

## 3. Cấu hình RedisIndexedSessionRepository

Với cấu hình Java, bật repository indexed bằng EnableRedisIndexedHttpSession:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisIndexedHttpSession;

@Configuration
@EnableRedisIndexedHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    redisNamespace = "acme:shop:prod:spring-session"
)
public class SessionConfiguration {
}
~~~

Cấu hình này yêu cầu ứng dụng có RedisConnectionFactory phù hợp. Trong Spring Boot, connection factory thường được auto-configure từ thông tin kết nối Redis. Với ứng dụng Spring Framework độc lập, cần khai báo connection factory và các dependency Spring Data Redis tương ứng.

Không dùng cùng một namespace cho những ứng dụng độc lập có session riêng. Tất cả instance của cùng ứng dụng trong cùng môi trường phải dùng chung namespace, repository type và serializer tương thích. Nếu một node dùng RedisSessionRepository còn node khác dùng RedisIndexedSessionRepository hoặc namespace khác, hành vi đọc/ghi và index có thể không đồng nhất.

Nếu ứng dụng đang bật EnableRedisHttpSession, hãy rà soát cấu hình hiện có trước khi chuyển sang EnableRedisIndexedHttpSession. Chỉ nên có một cấu hình quản lý HttpSession chính cho cùng ứng dụng. Tránh khai báo hai annotation tạo hai repository/filter khác nhau cho cùng Servlet context.

## 4. PrincipalNameIndexResolver tìm principal như thế nào?

RedisIndexedSessionRepository cần biết session thuộc về principal nào để cập nhật chỉ mục. Spring Session sử dụng IndexResolver<Session> để lấy các giá trị index từ session. PrincipalNameIndexResolver là resolver mặc định dành cho principal name.

Trong ứng dụng tích hợp Spring Security, resolver có thể lấy tên principal từ SecurityContext được lưu trong session. Khi người dùng đã xác thực và SecurityContext chứa Authentication, Spring Session có thể dùng Authentication.getName() để xác định principal name.

Điều này giúp ứng dụng không phải tự thêm username vào session trong luồng đăng nhập Spring Security thông thường. Tuy nhiên, điều kiện quan trọng là SecurityContext thực sự được lưu trong session và resolver có thể đọc được nó.

### Xác định principal cho cơ chế xác thực tùy chỉnh

Nếu ứng dụng không dùng Spring Security hoặc không lưu SecurityContext theo cách resolver mặc định nhận diện, ứng dụng có thể đặt thuộc tính principal index name vào session:

~~~java
import org.springframework.session.FindByIndexNameSessionRepository;

session.setAttribute(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    principalName
);
~~~

Giá trị principalName phải đến từ kết quả xác thực đáng tin cậy phía máy chủ. Không lấy trực tiếp username do client gửi lên rồi đặt làm principal index, vì điều đó có thể gắn session của người này vào chỉ mục của người khác.

Nếu ứng dụng có mô hình danh tính phức tạp, chẳng hạn username có thể trùng giữa các tenant, hãy chọn principal key ổn định và duy nhất trong phạm vi ứng dụng. Có thể chuẩn hóa thành một định danh có tenant, ví dụ tenantId:userId, miễn là cùng một quy tắc được áp dụng khi lưu và truy vấn.

Không nên dùng email hiển thị hoặc tên có thể đổi làm khóa index nếu hệ thống có định danh nội bộ ổn định hơn. Thay đổi principal name khi session đang tồn tại phải được xử lý như một thay đổi dữ liệu index.

## 5. Tra cứu tất cả session của một principal

Sau khi cấu hình repository indexed và principal đã được nhận diện, ứng dụng có thể truy vấn các session của người dùng:

~~~java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

import java.util.Map;

public class UserSessionLookup {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    public UserSessionLookup(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    public Map<String, ? extends Session> findSessions(String principalName) {
        return repository.findByPrincipalName(principalName);
    }
}
~~~

Map trả về có dạng khái niệm:

~~~text
{
  "session-id-A" -> Session A,
  "session-id-B" -> Session B,
  "session-id-C" -> Session C
}
~~~

Không nên trả trực tiếp toàn bộ đối tượng Session ra REST API. Session có thể chứa thuộc tính xác thực, dữ liệu nội bộ hoặc thông tin không nên hiển thị. Hãy chuyển thành DTO an toàn chỉ chứa thông tin cần cho giao diện, ví dụ thời điểm truy cập gần nhất, thời điểm tạo, thiết bị đã ghi nhận và nhãn hiển thị.

Nếu muốn hiển thị thiết bị, ứng dụng cần tự lưu metadata thiết bị đã được kiểm soát, chẳng hạn user-agent đã rút gọn, tên thiết bị do người dùng đặt hoặc thời điểm đăng nhập. Spring Session không tự biết session thuộc laptop hay điện thoại. User-Agent là dữ liệu do client cung cấp và có thể giả mạo; chỉ dùng như thông tin tham khảo, không dùng làm yếu tố xác thực.

### Tra cứu theo index name/value

Khi cần dùng một index cụ thể, API tổng quát có thể được gọi:

~~~java
Map<String, ? extends Session> sessions =
    repository.findByIndexNameAndIndexValue(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName
    );
~~~

Với index principal mặc định, findByPrincipalName thường dễ đọc hơn. API tổng quát có ích khi ứng dụng đã cấu hình các index khác bằng IndexResolver phù hợp.

## 6. Thu hồi một session cụ thể

Chức năng quản lý thiết bị thường cần cho phép người dùng đăng xuất một thiết bị. Repository indexed giúp tìm các session của principal, sau đó xóa session ID được chọn.

Ví dụ ở tầng service:

~~~java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class SessionRevocationService {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public SessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public boolean revoke(String principalName, String sessionId) {
        Map<String, ? extends Session> ownedSessions =
                sessions.findByPrincipalName(principalName);

        if (!ownedSessions.containsKey(sessionId)) {
            return false;
        }

        sessions.deleteById(sessionId);
        return true;
    }
}
~~~

Kiểm tra session ID có nằm trong kết quả của principal trước khi xóa giúp tránh việc một người dùng gửi ID của session thuộc tài khoản khác. Tuy nhiên, quyền gọi service vẫn phải được bảo vệ ở controller/security layer. Đối với chức năng “đăng xuất thiết bị khác”, principalName nên lấy từ Authentication hiện tại thay vì nhận một giá trị tùy ý từ request.

Session ID là bearer credential. Không đưa ID thô vào log, metric, URL hoặc thông báo lỗi. Nếu giao diện cần cho phép người dùng chọn một phiên, hãy cân nhắc cấp một handle quản lý riêng có thời hạn và ràng buộc với tài khoản, thay vì phơi bày session ID thật.

### Thu hồi tất cả session của một principal

Khi tài khoản bị khóa hoặc người dùng yêu cầu đăng xuất khỏi mọi thiết bị:

~~~java
public int revokeAll(String principalName) {
    Map<String, ? extends Session> ownedSessions =
            sessions.findByPrincipalName(principalName);

    int count = ownedSessions.size();

    ownedSessions.keySet().forEach(sessions::deleteById);

    return count;
}
~~~

Đây là ví dụ đơn giản. Trong môi trường có request đồng thời, một session mới có thể được tạo sau lần tra cứu nhưng trước khi vòng lặp hoàn tất. Nếu yêu cầu nghiệp vụ là thu hồi tuyệt đối mọi phiên, cần phối hợp thêm trạng thái tài khoản, phiên bản xác thực hoặc cơ chế thu hồi ở tầng bảo mật để request mới không thể tiếp tục dùng thông tin xác thực cũ.

Một chiến lược thường dùng là tăng security/session version của tài khoản hoặc đánh dấu tài khoản cần xác thực lại. Khi request đến, ứng dụng so sánh trạng thái hiện tại với trạng thái trong session hoặc principal. Điều này giúp kiểm soát các session được tạo đồng thời với thao tác thu hồi.

## 7. Giới hạn số session đồng thời

Một số hệ thống cần giới hạn mỗi tài khoản chỉ có tối đa N phiên đăng nhập. Chỉ mục principal cung cấp danh sách session để kiểm tra số lượng hiện có:

~~~java
int activeCount = sessions.findByPrincipalName(principalName).size();

if (activeCount >= maxSessions) {
    // Áp dụng chính sách: từ chối đăng nhập mới hoặc thu hồi phiên cũ.
}
~~~

Không nên coi đoạn kiểm tra rồi tạo session là thao tác nguyên tử. Hai request đăng nhập đồng thời có thể cùng đọc activeCount bằng N-1, rồi cả hai cùng tạo session, khiến số lượng vượt giới hạn. Nếu giới hạn là yêu cầu bảo mật bắt buộc, cần cơ chế đồng bộ hoặc transaction/lock phù hợp với kiến trúc triển khai.

Spring Security có cơ chế kiểm soát session đồng thời thông qua session management và SessionRegistry. Khi sử dụng Spring Session, có thể tích hợp SessionRegistry dựa trên Spring Session để tra cứu và quản lý session theo principal. Cần chọn đúng integration cho phiên bản Spring Security/Spring Session đang dùng và kiểm thử vòng đời khi session hết hạn hoặc bị xóa.

Đừng tự viết một bộ đếm trong session để giới hạn số phiên; nhiều request và nhiều instance có thể cập nhật bộ đếm đồng thời. Chỉ mục principal là dữ liệu để tra cứu, còn tính nguyên tử của chính sách giới hạn phải được giải quyết riêng.

## 8. Index được cập nhật và dọn như thế nào?

Chỉ mục principal không phải một bảng tĩnh. Nó phải thay đổi cùng vòng đời session.

| Sự kiện | Tác động mong đợi lên index |
|---|---|
| Session mới được lưu với principal | Thêm session ID vào index principal |
| Session được gán principal khác | Cập nhật liên kết principal theo dữ liệu session |
| Session bị xóa chủ động | Loại session ID khỏi index |
| Session hết hạn | Dọn liên kết index khi repository xử lý vòng đời hết hạn |
| Session không còn được tìm thấy | Kết quả truy vấn có thể không còn chứa session hợp lệ |

RedisIndexedSessionRepository dùng các key phụ để quản lý index. Ứng dụng không nên tự thêm/xóa phần tử trực tiếp trong các key nội bộ đó, vì repository còn quản lý expiration, event và các cấu trúc liên quan.

Với session expiration, Redis keyspace notification là một phần quan trọng của cơ chế xử lý sự kiện và dọn index. Môi trường Redis cần cho phép các notification cần thiết. Nếu Redis được quản lý không cho ứng dụng chạy CONFIG, quản trị viên cần bật notification theo hướng dẫn của Spring Session và cấu hình ConfigureRedisAction phù hợp.

Không dựa vào event hết hạn như một hàng đợi nghiệp vụ bền vững. Redis keyspace notification có đặc tính Pub/Sub và listener có thể mất kết nối. Việc kiểm tra session còn hợp lệ vẫn phải dựa vào repository. Với tác vụ kiểm toán hoặc thu hồi bắt buộc, lưu trạng thái nghiệp vụ bằng cơ chế bền vững riêng.

## 9. Chỉ mục principal và nhiều instance

Trong môi trường nhiều instance, mọi node phải dùng cùng Redis endpoint/cluster, namespace, serializer và repository type. Khi một instance ghi session, instance khác phải có khả năng đọc session và index tương ứng.

Ví dụ:

~~~text
web-1 ─┐
web-2 ─┼── RedisIndexedSessionRepository
web-3 ─┘        │
                ├── session data
                └── principal index
~~~

Nếu một node dùng repository indexed còn node khác dùng repository không indexed, node không indexed vẫn có thể đọc session theo ID nhưng không quản lý chỉ mục principal theo cùng cách. Điều này làm các chức năng tra cứu và cleanup thiếu nhất quán.

Khi triển khai rolling update, giữ cấu hình namespace và serializer tương thích giữa các phiên bản. Nếu đổi tên thuộc tính principal hoặc thay cấu trúc SecurityContext, kiểm tra việc đọc session cũ và cập nhật index trong giai đoạn chuyển tiếp.

Nếu Redis Cluster được dùng, cần kiểm tra giới hạn và cấu hình keyspace notification theo phiên bản Redis/Spring Session. Các thao tác index và expiration có thể liên quan tới nhiều key; không giả định mọi subscription hoặc event đều được phân phối như một Redis standalone. Kiểm thử trên đúng topology production là cần thiết.

## 10. Bảo mật khi cung cấp chức năng quản lý session

Tra cứu theo principal là chức năng nhạy cảm vì có thể tiết lộ thiết bị và trạng thái đăng nhập của tài khoản. Một endpoint quản trị session cần có kiểm soát truy cập rõ ràng.

Các nguyên tắc quan trọng:

- Lấy principal hiện tại từ Authentication đã được xác thực.
- Chỉ cho phép người dùng xem session của chính họ, trừ endpoint quản trị được phân quyền riêng.
- Khi xóa session, kiểm tra session ID thuộc principal mục tiêu.
- Không chấp nhận principalName tùy ý từ client nếu người gọi không có quyền quản trị.
- Không trả session ID hoặc thuộc tính xác thực ra API.
- Không ghi cookie/session ID vào log.
- Kiểm tra tenant và phạm vi tổ chức nếu hệ thống đa tenant.
- Giới hạn tần suất endpoint quản lý session để tránh lạm dụng.

Ví dụ controller chỉ dùng principal hiện tại:

~~~java
@GetMapping("/me/sessions")
public List<SessionSummary> mySessions(Authentication authentication) {
    String principalName = authentication.getName();

    return sessionService.findSummaries(principalName);
}
~~~

SessionSummary là DTO do ứng dụng định nghĩa, chỉ nên chứa các trường an toàn như nhãn thiết bị, thời điểm đăng nhập và lần truy cập gần nhất. Không serialize trực tiếp đối tượng Session.

Đối với endpoint quản trị có thể tìm session của người khác, yêu cầu role/authority rõ ràng, ghi audit event không chứa session ID thô và kiểm tra tenant/ownership. Một lỗi phân quyền ở endpoint này có thể cho phép thu hồi session của tài khoản khác.

## 11. Kiểm thử tra cứu theo principal

Kiểm thử cần xác nhận cả việc index được tạo, truy vấn đúng và index được cập nhật khi session bị xóa/hết hạn.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Một principal, một session | Đăng nhập và truy vấn principal | Map có một session |
| Một principal, nhiều thiết bị | Tạo nhiều session cùng principal | Map chứa các session tương ứng |
| Hai principal khác nhau | Tạo session cho hai người dùng | Không trả session của principal khác |
| Principal từ Spring Security | Lưu SecurityContext vào session | PrincipalNameIndexResolver nhận diện đúng tên |
| Principal tùy chỉnh | Đặt PRINCIPAL_NAME_INDEX_NAME | Repository tạo index theo giá trị đã đặt |
| Xóa một session | Gọi deleteById | Session không còn trong truy vấn principal sau khi cleanup hoàn tất |
| Hết hạn session | Cho session hết TTL | Session không còn được xem là hợp lệ; index được dọn theo cơ chế repository |
| Nhiều instance | Ghi ở node A, tra cứu ở node B | Node B thấy cùng session/index |
| Request đồng thời | Tạo và xóa session song song | Không giả định kết quả truy vấn là snapshot nguyên tử |
| Principal đổi tên | Thay đổi định danh xác thực | Index cũ/mới được xử lý theo chính sách migration |

Có thể viết integration test với Redis thật hoặc Testcontainers để xác minh index. Unit test với mock repository chỉ xác nhận service gọi đúng API, không chứng minh Redis index, expiration event hoặc keyspace notification hoạt động.

Ví dụ kiểm tra API repository:

~~~java
Map<String, ? extends Session> found =
        repository.findByPrincipalName("linh.nguyen");

assertThat(found).hasSize(2);
~~~

Test cần tạo session qua repository hoặc qua luồng đăng nhập thực tế, đặt principal index đúng cách, rồi chờ repository hoàn tất thao tác lưu. Với kiểm thử expiration, dùng TTL ngắn và polling có giới hạn thay vì sleep dài cố định. Khi test event, cấu hình Redis notification tương ứng trong test environment.

## 12. Chẩn đoán khi không tìm thấy session theo principal

Nếu findByPrincipalName trả Map rỗng trong khi người dùng đang đăng nhập, hãy kiểm tra theo thứ tự:

1. Ứng dụng có thực sự dùng RedisIndexedSessionRepository không?
2. Các instance có cùng namespace và Redis endpoint không?
3. SecurityContext có được lưu trong HttpSession không?
4. PrincipalNameIndexResolver có đọc được Authentication.getName() không?
5. Nếu dùng xác thực tùy chỉnh, thuộc tính PRINCIPAL_NAME_INDEX_NAME đã được đặt chưa?
6. Principal name lúc ghi và lúc truy vấn có cùng định dạng, chữ hoa/thường và quy tắc chuẩn hóa không?
7. Redis keyspace notification và cleanup có được cấu hình theo yêu cầu không?
8. Có node nào dùng serializer, repository type hoặc namespace khác không?
9. Session có thực sự còn tồn tại và chưa hết hạn không?
10. Có luồng logout hoặc thao tác quản trị nào vừa xóa session không?

Không bắt đầu bằng cách chạy KEYS * hoặc sửa trực tiếp index key trong Redis. Trước hết, kiểm tra cấu hình repository, log lỗi và API tra cứu. Nếu cần quan sát key, dùng SCAN có pattern giới hạn trong môi trường phù hợp và không công khai session ID.

Các metric nên theo dõi gồm số lần tra cứu principal, số session trả về, số lần không tìm thấy, lỗi Redis, lỗi serialization, số session bị xóa và độ trễ truy vấn. Tránh gắn principal name hoặc session ID vào metric label có cardinality cao hoặc dữ liệu nhận dạng cá nhân.

## 13. Khi nào nên dùng RedisIndexedSessionRepository?

| Nhu cầu | Lựa chọn |
|---|---|
| Chỉ cần tải một session khi biết session ID | RedisSessionRepository có thể đủ |
| Cần liệt kê session theo principal | RedisIndexedSessionRepository |
| Cần quản trị đăng xuất một hoặc mọi thiết bị của người dùng | RedisIndexedSessionRepository cùng API quản trị an toàn |
| Cần giới hạn phiên đồng thời | Repository indexed hỗ trợ tra cứu; cần thêm cơ chế đồng bộ cho giới hạn nguyên tử |
| Chỉ cần lưu session đơn giản, không truy vấn theo principal | Cân nhắc repository Redis không indexed để giảm chi phí index |
| Cần audit bền vững cho sự kiện bảo mật | Kết hợp repository với audit/event store riêng |

RedisIndexedSessionRepository phù hợp khi việc tìm session theo principal là một yêu cầu ứng dụng rõ ràng. Nó giúp xây dựng chức năng quản lý thiết bị, thu hồi session và giám sát đăng nhập mà không phải tự quét key Redis. Đổi lại, ứng dụng phải vận hành các chỉ mục phụ, cấu hình Redis notification phù hợp và kiểm thử tính nhất quán trong môi trường nhiều instance.

Hãy dùng principal name ổn định, lấy từ nguồn xác thực đáng tin cậy, kiểm tra quyền ở mọi thao tác quản trị và không để session ID lộ ra ngoài. Chỉ mục là công cụ tra cứu; nó không thay thế xác thực, phân quyền hoặc cơ chế đồng bộ cho các chính sách cần tính nguyên tử.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [RedisIndexedSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [FindByIndexNameSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [PrincipalNameIndexResolver Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/PrincipalNameIndexResolver.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)

