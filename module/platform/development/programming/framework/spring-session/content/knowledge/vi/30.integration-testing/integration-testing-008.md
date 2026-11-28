# Tra cứu theo principal và thu hồi nhiều phiên đăng nhập

Một người dùng có thể đăng nhập trên nhiều trình duyệt, thiết bị hoặc cửa sổ ứng dụng. Khi đổi mật khẩu, nghi ngờ lộ tài khoản, nhân viên hỗ trợ xử lý sự cố hoặc quản trị viên yêu cầu đăng xuất mọi thiết bị, ứng dụng cần tìm được tất cả phiên thuộc principal đó và thu hồi chúng. Spring Session hỗ trợ việc này thông qua FindByIndexNameSessionRepository, một repository có khả năng tìm session theo chỉ mục, trong đó chỉ mục quan trọng nhất là principal name.

Tra cứu và xóa session là thao tác nhạy cảm. Nếu principal không được lập chỉ mục đúng, chức năng logout-all có thể bỏ sót phiên. Nếu chỉ xóa dữ liệu trực tiếp trong Redis hoặc database, các index phụ có thể còn tham chiếu đến session đã xóa. Nếu nhiều node hoặc nhiều request cùng tạo và thu hồi phiên, một session mới có thể xuất hiện ngay sau lần tra cứu. Bài học này trình bày cách lập chỉ mục principal, tra cứu và thu hồi nhiều phiên bằng API Spring Session, tích hợp với Spring Security, và kiểm thử các trường hợp đồng thời.

## 1. Principal và session ID là hai khái niệm khác nhau

Principal biểu diễn danh tính đã được xác thực, thường là username hoặc tên định danh ổn định của tài khoản. Session ID là mã ngẫu nhiên mà client gửi lại để máy chủ tìm trạng thái phiên. Một principal có thể sở hữu nhiều session ID:

~~~text
principal: alice@example.test
  |-- session ID: random-A  (trình duyệt máy tính)
  |-- session ID: random-B  (điện thoại)
  |-- session ID: random-C  (trình duyệt khác)
~~~

Không dùng session ID để suy ra username, và không nhúng username vào session ID. Repository cần một index phụ liên kết principal với các session tương ứng. Khi tra cứu, ứng dụng truyền principal name vào repository và nhận về các session có index khớp.

FindByIndexNameSessionRepository mở rộng SessionRepository để cung cấp khả năng tra cứu theo index. Hợp đồng chính gồm:

- PRINCIPAL_NAME_INDEX_NAME: tên index chuẩn để tìm phiên theo principal.
- findByIndexNameAndIndexValue(indexName, indexValue): trả về map các session khớp với index.
- findByPrincipalName(principalName): phương thức tiện ích để tra cứu theo principal name.

Map kết quả được đánh chỉ mục bằng session ID; giá trị là đối tượng Session. Ứng dụng có thể dùng các key để gọi deleteById, nhưng không nên đưa chúng vào response API, log hoặc ticket hỗ trợ.

## 2. Repository nào hỗ trợ tra cứu principal?

Không phải mọi SessionRepository đều cung cấp index principal. Cần kiểm tra kiểu repository thực tế có triển khai FindByIndexNameSessionRepository hay không.

| Repository | Khả năng tra cứu principal |
|---|---|
| JdbcIndexedSessionRepository | Có hỗ trợ index principal thông qua dữ liệu principal trong schema JDBC |
| RedisIndexedSessionRepository | Có hỗ trợ index principal bằng cấu trúc index trong Redis |
| Repository tối giản chỉ triển khai SessionRepository | Không có API tra cứu theo index nếu không bổ sung |
| Custom repository | Phải tự duy trì index và triển khai hợp đồng tương ứng |

Với JDBC, bảng SPRING_SESSION có cột PRINCIPAL_NAME trong schema indexed repository và index database phù hợp để tra cứu. Với Redis indexed repository, principal index được quản lý cùng vòng đời session. Nếu dùng một repository Redis không lập chỉ mục, không thể mặc định rằng findByPrincipalName có sẵn.

Không viết SQL hoặc Redis query trực tiếp chỉ vì thấy cấu trúc lưu trữ có vẻ đơn giản. Repository biết cách đồng bộ session record, attributes và secondary index; thao tác qua API giúp giữ đúng logic đó.

## 3. Principal được lấy từ đâu?

Khi dùng Spring Security với Servlet session, trạng thái xác thực thường được lưu trong thuộc tính SPRING_SECURITY_CONTEXT. PrincipalNameIndexResolver của Spring Session có thể trích tên principal từ SecurityContext để lập chỉ mục. Nhờ đó, ứng dụng không cần tự thêm username vào session trong luồng xác thực chuẩn nếu repository đang dùng resolver phù hợp.

Có thể gặp các trường hợp index không được tạo:

- Ứng dụng dùng cơ chế xác thực tùy chỉnh không lưu SecurityContext theo định dạng mà resolver nhận diện.
- Session được tạo thủ công trong test nhưng không có thuộc tính SecurityContext.
- Ứng dụng dùng repository custom với index resolver chưa được cấu hình.
- Principal chỉ được thêm vào sau khi session đã được persist, nhưng thay đổi chưa được lưu.
- Principal name thay đổi hoặc được chuẩn hóa khác nhau giữa lúc lưu và lúc tra cứu.

Với cơ chế xác thực tùy chỉnh, ứng dụng có thể đặt giá trị principal index một cách tường minh:

~~~java
session.setAttribute(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    principalName
);
~~~

Đây là thuộc tính index dành cho repository hỗ trợ principal lookup. Hãy dùng một giá trị ổn định, không nhạy cảm quá mức và thống nhất giữa mọi node. Không dùng display name có thể thay đổi hoặc email chưa chuẩn hóa nếu hệ thống có một user ID ổn định hơn.

### 3.1. Chuẩn hóa principal name

Tra cứu index thường là phép so khớp giá trị, không phải tìm kiếm gần đúng. Nếu lúc lưu dùng Alice@example.test nhưng lúc thu hồi dùng alice@example.test, kết quả có thể khác nhau tùy quy tắc so sánh của store.

Chọn một quy tắc canonical:

- Dùng user ID bất biến nếu hệ thống có.
- Nếu dùng username/email, áp dụng cùng quy tắc chuẩn hóa khi ghi index và khi tra cứu.
- Không tự ý đổi chữ hoa/thường nếu hệ thống phân biệt chúng.
- Xử lý Unicode và khoảng trắng theo chính sách danh tính của ứng dụng.
- Khi đổi username, xác định cách cập nhật hoặc giữ alias cho phiên cũ.

Không lấy principal name trực tiếp từ query parameter do người dùng gửi để thu hồi session. Chức năng quản trị phải lấy target principal từ yêu cầu đã xác thực và kiểm tra quyền quản trị.

## 4. Lập chỉ mục principal trong vòng đời session

Principal index chỉ hữu ích nếu được cập nhật nhất quán khi session được tạo, lưu, thay đổi principal, xóa hoặc hết hạn.

| Sự kiện | Điều cần xảy ra với principal index |
|---|---|
| Tạo session trước đăng nhập | Chưa có principal hoặc chưa được lập chỉ mục |
| Xác thực thành công | Index được thêm theo principal mới |
| Lưu session sau xác thực | Repository persist index tương ứng |
| Principal thay đổi | Gỡ index cũ và thêm index mới |
| Logout một session | Xóa session và index liên quan |
| Logout mọi session | Xóa từng session thuộc principal qua repository |
| Session hết hạn | Index phải được dọn theo cơ chế repository |

Một test chỉ tạo session rồi gán thuộc tính trong memory chưa chứng minh index đã được lưu. Phải gọi save(session) theo hợp đồng repository và thực hiện truy vấn bằng một lần đọc mới.

Trong luồng HTTP thực, hãy kiểm tra sau khi request đăng nhập hoàn tất. SecurityContext có thể chỉ được persist khi request kết thúc; truy vấn index quá sớm trong cùng thời điểm có thể không phản ánh trạng thái đã commit.

## 5. Tra cứu các phiên bằng FindByIndexNameSessionRepository

Ví dụ service nhận repository có hỗ trợ principal index:

~~~java
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class PrincipalSessionQueryService {
    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public PrincipalSessionQueryService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int countSessions(String principalName) {
        Map<String, ? extends Session> found =
            this.sessions.findByPrincipalName(principalName);
        return found.size();
    }
}
~~~

Service chỉ trả số lượng, không trả session ID. Trong hệ thống thực, bảo vệ endpoint gọi service bằng quyền phù hợp và tránh để người dùng tra cứu principal của tài khoản khác.

Nếu cần thông tin tổng quan, có thể chỉ trả số phiên, thời điểm hoạt động gần nhất đã làm tròn hoặc trạng thái thiết bị do ứng dụng lưu riêng. Không trả toàn bộ attributes của Session; chúng có thể chứa SecurityContext, token hoặc dữ liệu cá nhân.

### 5.1. Xem map kết quả như một snapshot

Kết quả của findByPrincipalName là tập session được repository tìm thấy tại thời điểm truy vấn. Nó không phải một lock giữ nguyên trạng thái trong suốt quá trình xử lý. Một request khác có thể tạo session mới ngay sau đó, hoặc một session có thể hết hạn trong khi service đang xử lý.

Do đó, không diễn giải found.size() là số phiên tuyệt đối của principal trong mọi thời điểm. Đây là snapshot phục vụ truy vấn và xử lý theo chính sách.

## 6. Thu hồi tất cả session của một principal

Để thu hồi các phiên đã tìm thấy, dùng deleteById trên repository:

~~~java
import java.util.ArrayList;
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class PrincipalSessionRevocationService {
    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public PrincipalSessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int revokeAll(String principalName) {
        Map<String, ? extends Session> found =
            this.sessions.findByPrincipalName(principalName);
        var ids = new ArrayList<>(found.keySet());
        for (String id : ids) {
            this.sessions.deleteById(id);
        }
        return ids.size();
    }
}
~~~

Ví dụ thể hiện ý tưởng cốt lõi: tra cứu theo principal, lấy các session ID nội bộ từ map rồi xóa từng session bằng repository API. Không trả danh sách ID ra bên ngoài. Giá trị trả về chỉ là số phiên đã được chọn để thu hồi; nếu cần số lượng xóa thành công chính xác, phải thiết kế kết quả theo semantics của repository và xử lý lỗi từng thao tác.

deleteById là API repository để xóa session. Không xóa trực tiếp row SPRING_SESSION mà bỏ qua SPRING_SESSION_ATTRIBUTES, không xóa Redis key bằng lệnh DEL nếu repository còn quản lý principal index, expiry index hoặc event. Repository cần có cơ hội cập nhật các cấu trúc liên quan.

### 6.1. Thu hồi một phiên hiện tại

Logout phiên đang dùng thường được thực hiện qua HttpSession.invalidate() hoặc logout handler của Spring Security. Cách này gắn với request hiện tại và cho phép framework xử lý cookie, SecurityContext và sự kiện liên quan theo cấu hình.

Thu hồi phiên từ một công cụ quản trị khác với logout current session. Service quản trị không có request HttpSession của từng thiết bị; nó dùng repository để tìm và xóa session theo principal.

Không dùng một thao tác quản trị logout-all để thay thế logout endpoint thông thường. Hai luồng có mục tiêu và quyền truy cập khác nhau.

## 7. Tích hợp với Spring Security concurrent session control

Spring Security có cơ chế giới hạn số phiên đăng nhập đồng thời thông qua maximumSessions. Để cơ chế này làm việc trên nhiều instance dùng Spring Session, cần một SessionRegistry được hỗ trợ bởi repository dùng chung.

SpringSessionBackedSessionRegistry là implementation của Spring Security SessionRegistry, sử dụng FindByIndexNameSessionRepository làm nguồn dữ liệu session. Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.security.SpringSessionBackedSessionRegistry;

@Configuration
public class SessionRegistryConfiguration {
    @Bean
    SpringSessionBackedSessionRegistry<? extends Session> sessionRegistry(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        return new SpringSessionBackedSessionRegistry<>(repository);
    }
}
~~~

Sau đó dùng registry trong cấu hình Spring Security Servlet:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
    .sessionRegistry(sessionRegistry)
);
~~~

API cấu hình có thể khác đôi chút theo phiên bản Spring Security. Hãy dùng đúng DSL của dự án và bảo đảm SpringSessionBackedSessionRegistry được dùng thay cho registry chỉ lưu trong bộ nhớ của một node.

Với maximumSessions(2), Spring Security áp dụng giới hạn hai phiên cho một principal. Chính sách khi có lần đăng nhập thứ ba phụ thuộc cấu hình:

- Theo mặc định thông dụng, phiên cũ hơn có thể bị đánh dấu hết hiệu lực và bị từ chối khi request tiếp theo đi qua cơ chế kiểm tra concurrent session.
- Khi bật maxSessionsPreventsLogin(true), lần đăng nhập mới bị từ chối khi đã đạt giới hạn.

Hãy kiểm thử đúng chính sách mà sản phẩm yêu cầu. Không giả định đánh dấu một session hết hiệu lực và xóa session khỏi repository là cùng một thao tác.

### 7.1. Giới hạn của SessionRegistry

SpringSessionBackedSessionRegistry hỗ trợ tra cứu session theo principal thông qua repository. Tuy nhiên, repository index thường không cung cấp khả năng liệt kê mọi principal trong hệ thống. Không thiết kế dashboard dựa vào việc getAllPrincipals() phải trả đầy đủ mọi người dùng nếu implementation không hỗ trợ enumeration.

Concurrent session control cũng không thay thế chức năng thu hồi tài khoản, đổi mật khẩu hoặc thu hồi token ở các hệ thống khác. Nó quản lý session web được lưu trong repository tương ứng.

## 8. Logout-all là thao tác nhiều bước, không mặc nhiên nguyên tử

Phương thức revokeAll ở trên thực hiện một truy vấn rồi gọi deleteById cho từng session. Đây là một quy trình nhiều thao tác. Không nên mặc định rằng toàn bộ lần xóa sẽ nằm trong một transaction phân tán hoặc một lệnh nguyên tử.

Một số tình huống có thể xảy ra:

- Xóa ba session thành công nhưng session thứ tư lỗi do store tạm thời không khả dụng.
- Người dùng đăng nhập ở node khác sau khi truy vấn principal hoàn tất.
- Một request đang xử lý giữ snapshot session và cố lưu lại sau khi session đã bị xóa.
- Session hết hạn tự nhiên giữa lúc tra cứu và lúc xóa.
- Một index phụ chưa cập nhật kịp theo cơ chế event/cleanup của backend.

Vì vậy, API quản trị nên xác định chính sách:

- Báo thành công khi đã yêu cầu thu hồi toàn bộ snapshot và ghi nhận lỗi riêng nếu có.
- Có retry có giới hạn cho lỗi store tạm thời.
- Ghi audit tổng số phiên được tìm thấy, số thao tác xóa thành công và số lỗi; không ghi ID.
- Có cơ chế reconciliation nếu backend có thể để lại index stale.

Nếu yêu cầu nghiệp vụ là sau thời điểm này không request nào của tài khoản được tiếp tục, chỉ xóa snapshot session có thể chưa đủ.

## 9. Chống session mới xuất hiện trong lúc logout-all

Hãy xét trình tự:

1. Quản trị viên bắt đầu logout-all cho principal Alice.
2. Repository trả về ba session đang được index.
3. Alice đăng nhập ở node B và tạo session thứ tư.
4. Service xóa ba ID trong snapshot.
5. Session thứ tư vẫn tồn tại.

Đây là race giữa việc liệt kê và tạo session mới. Với chức năng đăng xuất các phiên hiện đang tồn tại, có thể chấp nhận snapshot semantics và ghi rõ hành vi. Với yêu cầu thu hồi tuyệt đối, cần một cơ chế cấp tài khoản có thẩm quyền.

### 9.1. Session generation hoặc security version

Một cách thiết kế là lưu sessionGeneration hoặc securityVersion trên bản ghi tài khoản:

- Khi tạo session sau xác thực, lưu generation hiện tại vào session.
- Khi logout-all, tăng generation của tài khoản bằng một cập nhật nguyên tử.
- Ở mỗi request cần xác thực, so sánh generation trong session với generation hiện tại của tài khoản.
- Nếu khác nhau, từ chối request và invalidate session.

Ví dụ logic:

~~~java
long currentGeneration = accountService.getSessionGeneration(userId);
Long sessionGeneration = (Long) session.getAttribute("SESSION_GENERATION");

if (sessionGeneration == null || sessionGeneration != currentGeneration) {
    session.invalidate();
    throw new SessionRevokedException();
}
~~~

Đây là mã minh họa cho một filter/service kiểm tra. session.invalidate() ở Servlet trả về void; đoạn code phải được điều chỉnh theo kiểu session và luồng exception của ứng dụng. Việc đọc generation cần đi tới nguồn có thẩm quyền hoặc cache có bảo đảm invalidation phù hợp. Nếu cache còn giữ generation cũ quá lâu, việc thu hồi không còn tức thời.

Khi logout-all, tăng generation trước hoặc trong cùng transaction nghiệp vụ với trạng thái thu hồi. Session được tạo đồng thời nhưng đã mang generation cũ sẽ bị từ chối ở request tiếp theo. Session tạo sau khi generation tăng sẽ nhận generation mới.

### 9.2. Kết hợp generation với xóa session

Generation check giúp chặn phiên cũ ngay cả khi một index lookup bỏ sót session. findByPrincipalName và deleteById vẫn hữu ích để dọn dữ liệu và giảm số session tồn tại. Hai cơ chế có vai trò khác nhau:

- Generation/version là hàng rào xác thực.
- Repository deletion là dọn session và index.

Nếu yêu cầu thu hồi mạnh, đừng chỉ dựa vào event bất đồng bộ hoặc việc mọi node nhận thông báo đúng lúc. Mỗi request nhạy cảm phải có cách xác minh phiên chưa bị thu hồi theo chính sách consistency đã chọn.

## 10. Thu hồi session sau đổi mật khẩu hoặc nghi ngờ xâm nhập

Các tình huống thường cần thu hồi nhiều phiên:

- Người dùng đổi hoặc reset mật khẩu.
- Quản trị viên khóa tài khoản.
- Phát hiện credential bị lộ.
- Người dùng chọn đăng xuất khỏi tất cả thiết bị.
- Nhân viên rời tổ chức hoặc mất quyền truy cập.

Quy trình nên:

1. Xác thực người yêu cầu và kiểm tra quyền tác động lên principal mục tiêu.
2. Chuẩn hóa principal theo cùng quy tắc đã dùng để lập index.
3. Nếu yêu cầu thu hồi tuyệt đối, tăng security version/session generation.
4. Tra cứu session bằng findByPrincipalName.
5. Xóa từng session bằng deleteById.
6. Ghi audit kết quả tổng hợp và lỗi.
7. Thu hồi thêm refresh token, API token hoặc phiên ở hệ thống khác nếu chúng nằm ngoài Spring Session.
8. Gửi thông báo cho người dùng theo chính sách bảo mật, không kèm session ID.

Không trả session ID hoặc cookie trong response quản trị. Chỉ trả kết quả tổng hợp như số phiên được yêu cầu thu hồi và trạng thái xử lý.

## 11. Tích hợp với JDBC và Redis

### 11.1. JDBC indexed repository

JdbcIndexedSessionRepository lưu metadata trong bảng SPRING_SESSION, attributes trong bảng SPRING_SESSION_ATTRIBUTES và có cột principal name để hỗ trợ tra cứu. Khi xóa qua repository, implementation có thể xử lý các bản ghi liên quan theo schema và transaction của nó.

Kiểm tra:

- Đã chạy schema/migration đúng phiên bản Spring Session.
- Cột principal name và index database tồn tại.
- Repository được cấu hình index resolver phù hợp.
- Tài khoản ứng dụng có quyền đọc/xóa các bảng liên quan.
- Không xóa trực tiếp row trong SPRING_SESSION mà bỏ sót attributes.

Nếu custom schema hoặc đổi tên bảng, đảm bảo migration vẫn giữ index principal và các query repository tương ứng.

### 11.2. Redis indexed repository

RedisIndexedSessionRepository duy trì dữ liệu session và index phụ trong Redis. Khi xóa bằng repository, nó có thể cập nhật cấu trúc index theo implementation.

Kiểm tra:

- Các node dùng cùng Redis namespace.
- Cấu hình serializer tương thích.
- Principal index được tạo từ SecurityContext hoặc index resolver tùy chỉnh.
- Redis keyspace notifications và event configuration được thiết lập theo yêu cầu của phiên bản nếu ứng dụng dựa vào expiration events.
- ACL Redis cho phép các thao tác repository cần thiết.

Không dùng KEYS hoặc xóa key theo pattern để logout một principal trong production. Những lệnh đó có thể quét nhiều dữ liệu, xóa nhầm session của ứng dụng khác hoặc bỏ sót cấu trúc index.

## 12. Bảo mật endpoint thu hồi nhiều phiên

Endpoint logout-all có tác động lớn. Cần phân biệt hai luồng:

- Người dùng tự đăng xuất mọi phiên của chính mình.
- Quản trị viên thu hồi phiên của một principal khác.

Với luồng tự phục vụ, lấy principal từ Authentication đã xác thực, không tin principal trong request body. Với luồng quản trị, yêu cầu authority riêng, kiểm tra tenant/scope và audit người thực hiện cùng mục tiêu.

Các biện pháp bổ sung:

- Bảo vệ endpoint bằng POST và CSRF protection phù hợp ứng dụng browser.
- Giới hạn tần suất để tránh lạm dụng hoặc tạo tải xóa lớn.
- Không cho phép principal tùy ý trong query parameter nếu người dùng không có quyền quản trị.
- Không trả thông tin giúp dò tài khoản hoặc số session của principal khác.
- Ghi audit an toàn, không chứa cookie, session ID hoặc token.
- Yêu cầu xác thực lại hoặc MFA cho thao tác thu hồi có tác động lớn nếu chính sách yêu cầu.

Không coi việc xóa session là thay thế kiểm tra authorization. Mỗi thao tác quản trị phải được xác thực và phân quyền độc lập.

## 13. Kiểm thử repository tra cứu theo principal

Test repository cần chứng minh index thực sự được tạo và tìm thấy:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

class PrincipalSessionRepositoryTests {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    PrincipalSessionRepositoryTests(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    @Test
    void findsSessionsByPrincipal() {
        var first = this.repository.createSession();
        first.setAttribute(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            "alice@example.test"
        );
        this.repository.save(first);

        var found = this.repository.findByPrincipalName("alice@example.test");
        assertThat(found).containsKey(first.getId());
    }
}
~~~

Ví dụ dùng thuộc tính principal index tường minh để kiểm thử repository độc lập với Spring Security authentication flow. Khi kiểm thử luồng đăng nhập thật, nên xác minh resolver có thể lấy principal từ SecurityContext và index được tạo sau khi request xác thực hoàn tất.

Test này cần repository integration với Redis/JDBC thật hoặc Testcontainers. Nếu dùng mock repository, test chỉ chứng minh service gọi đúng method; nó không chứng minh index backend hoạt động.

## 14. Kiểm thử thu hồi nhiều session

Tạo ít nhất hai session cùng principal và một session của principal khác:

1. Tạo session A và B với principal Alice.
2. Tạo session C với principal Bob.
3. Lưu tất cả qua repository.
4. Gọi service thu hồi Alice.
5. Xác nhận A và B không còn tìm thấy bằng ID.
6. Xác nhận truy vấn principal Alice trả map rỗng.
7. Xác nhận C vẫn tồn tại và Bob vẫn tra cứu được.

Các assertion cần kiểm tra cả session record lẫn principal index. Nếu chỉ kiểm tra findByPrincipalName trả rỗng, có thể index đã bị xóa nhưng session record vẫn còn. Ngược lại, session có thể đã bị xóa nhưng index stale vẫn trả ID cũ.

Không ghi ID của session test ra log. Có thể giữ ID trong biến test để assert findById(id) trả null.

## 15. Kiểm thử qua HTTP và Spring Security

Repository test không chứng minh luồng xác thực đã lập chỉ mục đúng. Cần integration test qua HTTP:

- Đăng nhập principal Alice trên client A và B.
- Giữ cookie riêng cho mỗi client.
- Xác minh cả hai request được xác thực.
- Gọi endpoint logout-all của Alice.
- Gửi lại cookie A và B tới endpoint được bảo vệ.
- Xác nhận các request không còn được xác thực theo chính sách.
- Đăng nhập Bob và xác nhận phiên Bob không bị ảnh hưởng.

Với MockMvc, có thể kiểm tra Spring Security filter chain và session repository filter trong application context. Với test server thật, dùng HTTP client riêng cho mỗi client để giữ cookie tách biệt. Đừng chia sẻ cookie jar giữa các client, vì test có thể vô tình chỉ dùng một session.

Nếu dùng maximumSessions, kiểm thử cả:

- Đăng nhập lần đầu.
- Đăng nhập lần hai dưới giới hạn.
- Đăng nhập vượt giới hạn.
- Chính sách expire phiên cũ hoặc ngăn đăng nhập mới.
- Request tiếp theo từ phiên bị expire.
- Hành vi trên node khác.

## 16. Kiểm thử nhiều instance

Để xác minh khả năng thu hồi trên nhiều node:

1. Khởi động node A và B với cùng Redis/JDBC repository.
2. Đăng nhập Alice qua A.
3. Đăng nhập Alice qua B bằng client thứ hai.
4. Tra cứu principal từ một service bất kỳ.
5. Thu hồi tất cả phiên.
6. Gửi request bằng cả hai cookie đến cả A và B.
7. Xác nhận không node nào tiếp tục chấp nhận session đã thu hồi.

Không bật sticky session trong bài test này nếu mục tiêu là xác minh shared repository. Mỗi node phải dùng cùng namespace, schema, serializer và principal index resolver.

Thêm một kịch bản node restart: tạo session ở A, dừng A, rồi dùng cookie trên B. Sau logout-all ở B, xác minh cookie cũ bị từ chối ở mọi node còn hoạt động.

## 17. Kiểm thử race giữa login và logout-all

Đây là kịch bản thường bị bỏ sót:

- Thread 1 truy vấn principal và nhận map session.
- Thread 2 đăng nhập cùng principal và lưu session mới.
- Thread 1 xóa các session trong map cũ.

Nếu chỉ kiểm tra map cũ đã bị xóa, test có thể pass nhưng session mới vẫn tồn tại. Cần xác định semantics:

| Yêu cầu | Cách kiểm thử/kỳ vọng |
|---|---|
| Thu hồi snapshot hiện tại | Session có trong map tại thời điểm tra cứu bị xóa; login mới sau snapshot có thể còn |
| Thu hồi tuyệt đối theo generation | Session được tạo với generation cũ bị từ chối dù được lưu sau thao tác liệt kê |
| Concurrent login control | Hai node cùng đăng nhập không vượt giới hạn theo chính sách |
| Request đang chạy | Request bắt đầu trước revoke không được ghi lại session cũ nếu hệ thống yêu cầu strict revoke |

Dùng barrier/latch để điều khiển thứ tự hai thread. Không dùng sleep tùy tiện vì race test sẽ chập chờn và khó tái hiện.

## 18. Xử lý lỗi và tính lặp an toàn

Khi thu hồi nhiều phiên, một số lần xóa có thể thành công trước khi store gặp lỗi. Thiết kế service nên:

- Thu thập kết quả theo từng thao tác mà không ghi ID vào log.
- Retry có giới hạn cho lỗi tạm thời.
- Dùng deleteById theo semantics idempotent của repository; xóa session đã không còn tồn tại không nên tạo session mới.
- Không retry vô hạn khi database hoặc Redis đang lỗi.
- Nếu dùng generation, tăng generation bằng thao tác nguyên tử và lưu audit ngay cả khi bước cleanup bị lỗi.
- Có job reconciliation hoặc thao tác hỗ trợ để hoàn tất cleanup.

Không báo đã đăng xuất mọi thiết bị nếu chỉ một phần thao tác xóa thành công và không có generation barrier. Response nên phân biệt yêu cầu đã được ghi nhận, số phiên được xử lý và trạng thái cleanup nếu nghiệp vụ cần độ chính xác cao.

## 19. Metric và audit

Metric hữu ích:

- Số session được tìm thấy theo principal, ở dạng tổng hợp.
- Số session delete thành công/thất bại.
- Thời gian truy vấn principal index.
- Số lần index lookup rỗng bất thường sau login.
- Số concurrent-session limit violation.
- Số lỗi Redis/JDBC khi revoke.
- Số session bị từ chối do generation mismatch.

Không dùng principal name hoặc session ID làm metric label. Principal có thể là dữ liệu cá nhân và tạo cardinality cao. Dùng operation, result, store type, environment và error class đã chuẩn hóa.

Audit record có thể chứa:

- Người thực hiện (actor ID nội bộ).
- Principal mục tiêu ở dạng đã được tổ chức cho phép lưu hoặc pseudonymized.
- Lý do thu hồi.
- Thời điểm và correlation ID.
- Số session được tìm thấy, số lần xóa thành công và số lỗi.

Không ghi cookie, session ID, Authorization header hoặc toàn bộ session attributes vào audit log.

## 20. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| findByPrincipalName trả map rỗng sau login | Repository không hỗ trợ index hoặc principal chưa được resolve | Kiểm tra FindByIndexNameSessionRepository, SecurityContext và index resolver |
| Tìm được session trong test nhưng không ở production | Test tự set principal index còn production không có | Kiểm tra authentication persistence và cấu hình resolver |
| Logout-all chỉ xóa một thiết bị | Chỉ xóa session hiện tại thay vì tra principal index | Tìm tất cả ID bằng findByPrincipalName |
| Session record còn sau khi index rỗng | Xóa trực tiếp index hoặc cleanup không đồng bộ | Dùng repository deleteById và reconciliation |
| Index còn ID cũ sau delete | Bỏ qua API repository hoặc lỗi cleanup | Kiểm tra repository implementation và event/index cleanup |
| Node khác vẫn chấp nhận cookie cũ | Namespace/store khác nhau hoặc request stale save | Đồng bộ cấu hình, version/generation check |
| Login đồng thời tạo session sau logout-all | Race giữa snapshot lookup và session creation | Dùng session generation/security version nếu cần strict revoke |
| Concurrent session limit không áp dụng giữa node | Dùng SessionRegistry chỉ lưu trong bộ nhớ | Dùng SpringSessionBackedSessionRegistry |
| Principal đổi nhưng index cũ còn | Không cập nhật index cũ khi danh tính thay đổi | Xóa index cũ và thêm index mới trong cùng thao tác lưu |
| Endpoint thu hồi cho phép xóa tài khoản khác | Tin principal từ request hoặc thiếu authority | Lấy principal hiện tại từ Authentication và kiểm tra quyền quản trị |

## 21. Quy trình triển khai

1. Xác nhận repository đang dùng triển khai FindByIndexNameSessionRepository.
2. Xác nhận principal index được resolve từ SecurityContext hoặc thuộc tính custom đã chuẩn hóa.
3. Kiểm thử login thực tế và xác nhận findByPrincipalName trả đúng các session.
4. Dùng repository API để xóa từng session; không sửa trực tiếp bảng/key.
5. Tích hợp SpringSessionBackedSessionRegistry nếu cần concurrent-session control giữa nhiều node.
6. Xác định logout-all là thu hồi snapshot hay thu hồi tuyệt đối.
7. Nếu cần strict revoke, dùng session generation/security version làm hàng rào xác thực.
8. Bảo vệ endpoint bằng authentication, authorization, CSRF và audit phù hợp.
9. Kiểm thử nhiều session, nhiều principal, nhiều node, concurrent login và store failure.
10. Theo dõi index lookup, delete result và generation mismatch bằng metric không chứa dữ liệu nhạy cảm.

Tra cứu theo principal và thu hồi nhiều phiên là chức năng dựa trên index, repository và chính sách xác thực cùng lúc. FindByIndexNameSessionRepository cung cấp cách tìm các phiên thuộc một principal; deleteById giúp repository cập nhật dữ liệu session và index liên quan; SpringSessionBackedSessionRegistry hỗ trợ Spring Security quản lý giới hạn phiên trên nhiều node. Với yêu cầu thu hồi tuyệt đối trong lúc có login đồng thời, cần thêm generation/version có thẩm quyền để mọi request nhận ra phiên cũ đã bị thu hồi.
