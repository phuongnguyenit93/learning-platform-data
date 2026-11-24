# Spring authorization boundary — Ranh giới phân quyền trong Spring

Bài học thuộc chương **Spring Security Integration** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào việc đặt kiểm soát phân quyền ở đúng ranh giới thực thi để bảo vệ đối tượng, trạng thái, phê duyệt và tác động nghiệp vụ.

Một API có thể yêu cầu đăng nhập và role đúng nhưng vẫn cho người dùng sửa yêu cầu của tenant khác. Một service có `@PreAuthorize` cũng có thể bị gọi theo đường không đi qua proxy. Ngược lại, một kiểm tra quyền đúng vẫn chưa ngăn hai transaction cùng sử dụng một approval hoặc cùng vượt hạn mức.

**Authorization boundary** là nơi hệ thống quyết định một chủ thể có được thực hiện một hành động trên một tài nguyên trong ngữ cảnh cụ thể hay không, trước khi hành động đó tạo tác động được bảo vệ.

Ví dụ dùng Servlet stack với API của Spring Security **7.0** và Spring Framework **7.0** làm mốc tham chiếu. Các lớp miền và repository trong ví dụ là hợp đồng minh họa cần hiện thực trong ứng dụng; không suy phiên bản hay cấu hình dự án từ tên module.

Sau bài học, bạn cần có thể:

- Phân biệt authentication, authority, quyền theo đối tượng và guard nghiệp vụ.
- Kết hợp request authorization với method security trên application service.
- Giải quyết actor và tenant từ nguồn đáng tin thay vì payload client.
- Giữ quyết định quyền, state/version và phê duyệt nhất quán khi cập nhật.
- Nhận diện self-invocation, bean không được quản lý và đường gọi bỏ qua ranh giới.
- Thiết kế đường worker, retry và tác động ngoài có trách nhiệm phân quyền rõ.
- Kiểm thử sự cưỡng chế qua filter chain, proxy Spring và dữ liệu bền vững.

## 1. Những câu hỏi khác nhau cần các lớp kiểm soát khác nhau

Giả sử hệ thống cho checker duyệt yêu cầu hoàn tiền. Một thao tác hợp lệ cần trả lời ít nhất bốn câu hỏi:

| Lớp quyết định | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Caller là ai, bằng chứng danh tính có hợp lệ không? | Token được xác minh theo hợp đồng issuer/audience |
| Quyền hành động tổng quát | Caller có khả năng phê duyệt không? | Authority `SCOPE_refund.approve` |
| Quyền theo đối tượng | Caller có được duyệt request này không? | Đúng tenant, đúng phạm vi phụ trách, không vượt giới hạn quyền |
| Guard nghiệp vụ | Đối tượng có thể chuyển trạng thái theo dữ liệu hiện tại không? | Chờ duyệt, đúng version, checker độc lập maker, nội dung đúng snapshot |

`authenticated()` chỉ giải quyết yêu cầu tối thiểu về danh tính theo cấu hình. `hasAuthority(...)` không tự biết mọi request trong database có thuộc quyền của caller hay không.

Một thiết kế có thể dùng cùng authority cho nhiều tenant nhưng vẫn cần membership và object policy riêng. Cũng không nên đưa điều kiện state, số tiền, lịch sử phê duyệt và mọi hạn mức vào một role tĩnh rồi coi như đã bảo vệ workflow.

### 1.1. Bất biến của ví dụ

~~~text
Checker chỉ duyệt request trong tenant và scope được phép.
Checker độc lập maker theo policy định danh của hệ thống.
Approval gắn với nội dung trọng yếu và contentVersion đã xem xét.
Request chỉ được duyệt từ trạng thái chờ duyệt và workflowVersion phù hợp.
Một lần phê duyệt không tự tạo lệnh hoàn tiền hoặc bỏ qua bước thực thi.
Thay đổi dữ liệu và bằng chứng quyết định được lưu nhất quán theo thiết kế.
~~~

Những bất biến này định hướng nơi đặt guard và cách kiểm tra tác động sau khi từ chối.

## 2. Bản đồ ranh giới từ HTTP tới dữ liệu

~~~text
HTTP request + thông tin xác thực
  → SecurityFilterChain: xác thực và quyền truy cập route
  → Controller: parse/validate command, gọi use case
  → Spring-managed service proxy: method authorization
  → Application service: actor, tenant, quyền theo đối tượng
  → Transaction/domain: state, version, approval và bất biến chung
  → Repository/outbox: dữ liệu và ý định bền vững
  → Worker/provider adapter: quyền thực thi và tác động bên ngoài
~~~

Mỗi đoạn bảo vệ một ranh giới khác nhau. HTTP rule có thể từ chối sớm traffic không phù hợp. Method security đặt điều kiện trên use case được gọi qua bean. Guard trong service/transaction giải quyết dữ liệu và nghiệp vụ cụ thể.

Một scheduler hoặc message consumer không đi qua controller HTTP vẫn có thể gọi use case. Nếu kiểm soát chỉ nằm ở controller, đường nội bộ có thể thiếu cùng điều kiện quyền.

Ngược lại, đặt annotation trên service không tự hạn chế một script dùng credential database để sửa trực tiếp bảng. Thiết kế cần quản lý quyền dữ liệu, đường quản trị và kiến trúc phụ thuộc phù hợp với threat model.

## 3. Request authorization: bảo vệ đường vào HTTP

Spring Security hỗ trợ cấu hình quyền theo request bằng `authorizeHttpRequests`. Các matcher cần đúng thứ tự và có rule cuối phù hợp. [Spring Security 7.0: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html).

Ví dụ cấu hình cho hai route minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    HttpMethod.POST, "/api/refunds/*/approve")
                    .hasAuthority("SCOPE_refund.approve")
                .requestMatchers(
                    HttpMethod.GET, "/api/refunds/*")
                    .hasAuthority("SCOPE_refund.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Mẫu giả định decoder và cơ chế xác minh token đã được cấu hình theo issuer, audience và chính sách của ứng dụng. Các dependency resource server cần có trong ứng dụng thực tế. Bài học không cung cấp một hệ thống authentication hoàn chỉnh qua đoạn cấu hình này.

### 3.1. Rule này chứng minh gì?

Với request khớp route approve, caller phải có authority tổng quát tương ứng. Rule chưa xác nhận request ID trên URL thuộc tenant nào, checker có được phép duyệt đối tượng đó hay approval có vi phạm phân tách nhiệm vụ không.

Các route chưa liệt kê bị deny trong mẫu. Ứng dụng thực tế cần khai báo có chủ đích những route khác như callback, error handling hoặc health endpoint theo cách triển khai của mình. Không đổi catch-all thành permit chỉ để một endpoint mới hoạt động.

CSRF, CORS, session và cách browser gửi credential cần có hợp đồng riêng. Không thêm `csrf.disable()` chỉ để một ca POST qua được kiểm thử. Khi kiểm thử quyền hành động, bảo đảm request đã đáp ứng các kiểm soát độc lập cần thiết để biết lý do nó thực sự bị chặn.

### 3.2. Đừng nhầm securityMatcher với requestMatchers

`securityMatcher` chọn phạm vi áp dụng của một `SecurityFilterChain`; `requestMatchers` đặt rule bên trong chain đã được chọn. Nếu không chain nào khớp một request, request đó không được Spring Security bảo vệ. Khi có nhiều chain, cần kiểm tra độ bao phủ và fallback chain. [Spring Security 7.0: Java Configuration](https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html).

Ví dụ chỉ có một chain khớp `/api/**` không tự bảo vệ một endpoint `/internal/refund-repair`. `anyRequest().denyAll()` nằm trong chain đó chỉ xử lý request thuộc phạm vi chain đã chọn.

Khi thêm management port, servlet path, API phiên bản cũ hoặc chain có độ ưu tiên cao hơn, phải kiểm tra request thực tế đi vào chain nào. Một cấu hình nhìn đúng trong một file chưa chứng minh mọi endpoint đang được bao phủ.

## 4. Method security: đặt điều kiện trên use case

Spring Boot Starter Security không tự bật method authorization. Với mô hình annotation trong bài, cần `@EnableMethodSecurity`; `@PreAuthorize` có thể khai báo ở class hoặc method. Method không có rule áp dụng sẽ không tự được bảo vệ chỉ vì method security đã bật. [Spring Security 7.0: Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html).

Một cách tổ chức cho service nhạy cảm:

~~~java
@Service
@PreAuthorize("denyAll()")
public class RefundApprovalService {
    @PreAuthorize("hasAuthority('SCOPE_refund.approve')")
    public ApprovalReceipt approve(UUID requestId, long expectedVersion) {
        // Actor, object policy và guard nghiệp vụ được xử lý trong use case.
        return approvalUseCase(requestId, expectedVersion);
    }
}
~~~

Đây là phác thảo cấu trúc; phiên bản đầy đủ về trách nhiệm transaction xuất hiện ở phần sau. Method có rule riêng trong mẫu dùng rule đó thay cho rule class; những method còn lại thuộc rule class khi được gọi qua ranh giới proxy tương ứng.

Mặc định deny ở class là một lựa chọn thiết kế cho bề mặt use case này. Nó cần review và test khi thêm public method mới; không phải một cơ chế tự động bảo vệ mọi helper, repository và code trong cùng tiến trình.

### 4.1. Route rule và method rule có thể cùng cần thiết

Trong ví dụ, cả route approve và method approve yêu cầu cùng authority. Sự lặp có chủ đích bảo vệ hai đường vào khác nhau:

- Request HTTP không đủ quyền bị chặn trước khi tới use case.
- Caller trong ứng dụng gọi bean qua method boundary cũng phải đáp ứng rule.

Cần kiểm thử mỗi ranh giới riêng. Nếu chỉ gọi HTTP và thấy bị chặn, chưa biết method security có đang hoạt động hay toàn bộ kết quả chỉ đến từ filter chain.

### 4.2. Authority và object policy không nên bị trộn nghĩa

Authority `SCOPE_refund.approve` thể hiện khả năng tổng quát theo hợp đồng token/ứng dụng. Object policy có thể yêu cầu thêm membership đang hoạt động, phạm vi chi nhánh, đối tượng được phân công và giới hạn giá trị.

Nếu biểu thức SpEL trở nên dài, phụ thuộc nhiều truy vấn và state thay đổi, cần phân chia trách nhiệm rõ: rule nào là điều kiện method-level, rule nào phải được đánh giá trên dữ liệu được cập nhật nhất quán. Không dùng một biểu thức phức tạp như cách che mất ranh giới transaction.

## 5. Actor và tenant phải có nguồn đáng tin

Một command HTTP có thể chứa request ID và expected version. Các trường như actor, role, tenant thực sự có quyền hoặc maker/checker person ID phải được giải quyết từ nguồn có thẩm quyền.

### 5.1. Hợp đồng của adapter CurrentActor

~~~text
Đọc Authentication từ ngữ cảnh bảo mật của lần gọi hiện tại.
Yêu cầu loại principal và trạng thái xác thực đúng hợp đồng ứng dụng.
Giải quyết danh tính bằng issuer + subject hoặc mapping tương đương.
Xác minh membership/scope tenant theo policy được chọn.
Trả Actor nội bộ gồm danh tính, tenant và person reference cần thiết.
Thiếu hoặc không tin cậy dữ liệu thì không tự tạo actor đặc quyền.
~~~

Trong resource server JWT, Spring cung cấp cơ chế xác minh token và chuyển scope thành authority theo cấu hình; cách mặc định dùng prefix `SCOPE_`. Principal và claim cần được hiểu theo hợp đồng của issuer. [Spring Security 7.0: Resource Server JWT](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/resource-server/jwt.html).

Một JWT hợp lệ không tự chứng minh caller được hành động trên mọi object hoặc membership chưa từng thay đổi từ lúc token được phát. Ứng dụng cần quyết định dữ liệu nào được chấp nhận từ token, dữ liệu nào phải tra cứu và giới hạn độ cũ nào cho phép.

### 5.2. Tenant trong request là dữ liệu cần kiểm tra

Nếu API hỗ trợ chọn tenant bằng URL/header, giá trị đó là **scope được yêu cầu**. Adapter phải đối chiếu nó với quyền của principal. Không đổi CurrentActor sang tenant mới chỉ vì client gửi một header khác.

Nếu người dùng có nhiều tenant, hãy mô tả cách chọn một scope hoạt động có xác minh. Query repository vẫn cần tenant đã được giải quyết, không dùng tenant chưa kiểm tra từ payload.

Không dùng `authentication.name` như mặc định luôn là person ID toàn cục. Một subject có thể chỉ duy nhất trong issuer; hai account cũng có thể thuộc cùng một con người khi kiểm tra phân tách nhiệm vụ.

### 5.3. Đừng công khai đường dựng Actor đặc quyền

Nếu use case nhận `Actor` từ controller mà không phân biệt đối tượng nội bộ với dữ liệu client, một đường batch hoặc test helper có thể truyền actor giả. Trong mẫu phía sau, service tự gọi adapter CurrentActor để giải quyết caller của ranh giới đang được bảo vệ.

Đường machine-to-machine hoặc delegated command cần cơ chế xác minh riêng. Không tự gán `SYSTEM` khi thiếu SecurityContext hoặc khi parser không hiểu principal.

## 6. Quyền theo đối tượng phải gắn với dữ liệu được dùng

Một trình tự hợp lý cho approve:

~~~text
1. Method boundary kiểm tra authority tổng quát.
2. Service giải quyết Actor hiện tại từ nguồn đáng tin.
3. Tải request bằng tenant + ID theo cơ chế đồng thời đã thiết kế.
4. Kiểm tra Actor có quyền approve chính request này.
5. Kiểm tra state, workflowVersion, phân tách và nội dung trình duyệt.
6. Ghi approval, trạng thái và bằng chứng nhất quán.
~~~

Kiểm tra trước bằng object A rồi cập nhật object B từ body tạo một khoảng hở. Vì vậy, định danh dùng cho policy, repository và thay đổi phải thống nhất.

Nếu một early check tải request để quyết định allow, request vẫn có thể thay đổi trước lúc body cập nhật. Những guard phụ thuộc dữ liệu biến động phải được bảo vệ tại ranh giới cập nhật phù hợp; early check hỗ trợ từ chối sớm nhưng không thay thế điều đó.

### 6.1. Query có scope là một lớp bảo vệ

Repository có thể cung cấp port như:

~~~java
Optional<RefundRequest> lockByTenantAndId(
        TenantId tenantId,
        UUID requestId);
~~~

Tên method không tự tạo lock. Implementation phải hiện thực đúng lock/version contract và có kiểm thử cạnh tranh. Query theo tenant giúp tránh tải nhầm dữ liệu scope khác, nhưng vẫn chưa chứng minh quyền của từng checker trong cùng tenant.

### 6.2. Thứ tự lỗi cần hạn chế lộ dữ liệu

Caller không có quyền biết request tồn tại không nên nhận chi tiết số tiền, maker hoặc trạng thái duyệt. Chọn hợp đồng lỗi không tiết lộ object ngoài scope; dùng reason nội bộ có phân quyền cho điều tra.

Không làm lộ entity nhạy cảm rồi mới dựa vào client để ẩn field. Response projection, query scope và kiểm tra read policy cũng thuộc ranh giới phân quyền.

## 7. Application service: quyết định quyền và cập nhật trong một use case

Mẫu sau thay thế phác thảo service ở phần 4. Nó minh họa một lần duyệt, chưa hiện thực ledger idempotency hay luồng chuyển tiền. Các kiểu miền, exception và repository là **hợp đồng do ứng dụng tự định nghĩa**, không phải API sẵn có của Spring. Phần import chỉ liệt kê Java và Spring; cần hiện thực các hợp đồng miền để chạy trong ứng dụng.

~~~java
import java.time.Clock;
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@PreAuthorize("denyAll()")
public class RefundApprovalService {
    private final CurrentActor currentActor;
    private final RefundRequests requests;
    private final RefundApprovalPolicy policy;
    private final ApprovalEvidenceRepository evidence;
    private final Clock clock;

    public RefundApprovalService(
            CurrentActor currentActor,
            RefundRequests requests,
            RefundApprovalPolicy policy,
            ApprovalEvidenceRepository evidence,
            Clock clock) {
        this.currentActor = currentActor;
        this.requests = requests;
        this.policy = policy;
        this.evidence = evidence;
        this.clock = clock;
    }

    @PreAuthorize("hasAuthority('SCOPE_refund.approve')")
    @Transactional(rollbackFor = Exception.class)
    public ApprovalReceipt approve(UUID requestId, long expectedVersion) {
        Actor actor = currentActor.require();

        RefundRequest request = requests
                .lockByTenantAndId(actor.tenantId(), requestId)
                .orElseThrow(RequestNotVisibleException::new);

        policy.requireCanApprove(actor, request);
        request.requireWorkflowVersion(expectedVersion);
        request.requirePendingApproval();
        request.requireIndependentChecker(actor.personId());
        request.requireSubmittedSnapshotUnchanged();

        ApprovalReceipt receipt = request.approve(
                actor.personId(), clock.instant());

        requests.save(request);
        evidence.append(request, actor, receipt);
        return receipt;
    }
}
~~~

### 7.1. Các hợp đồng cần hiện thực

| Thành phần | Trách nhiệm bắt buộc trong mẫu |
|---|---|
| `CurrentActor.require()` | Giải quyết principal và tenant đã xác minh; từ chối khi thiếu ngữ cảnh hợp lệ |
| `lockByTenantAndId` | Query đúng tenant, khóa bản ghi đến hết transaction theo hợp đồng database đã chọn |
| `policy.requireCanApprove` | Kiểm tra scope, membership, phân công và giới hạn quyền trên request đã tải; từ chối trước mutation |
| `requireWorkflowVersion` | So sánh version phía server với version người duyệt đã xem; dữ liệu client chỉ là điều kiện đồng thời |
| `requirePendingApproval` | Chỉ cho phép chuyển từ trạng thái chờ duyệt |
| `requireIndependentChecker` | Kiểm tra định danh người duyệt khác người tạo theo policy; hai account không nhất thiết là hai người |
| `requireSubmittedSnapshotUnchanged` | Bảo đảm nội dung trọng yếu hiện tại đúng snapshot được trình duyệt |
| `approve` | Tạo approval gắn với tenant, request, người duyệt, content version/snapshot; đổi trạng thái và tăng workflow version |
| `save` và `evidence.append` | Ghi aggregate cùng bằng chứng thành công trong cùng transaction, cùng tài nguyên giao dịch của mẫu |

`ApprovalReceipt` là kết quả duyệt, không phải bằng chứng đã chuyển tiền. Nội dung trọng yếu có thể gồm số tiền, tiền tệ, tài khoản nhận và lý do hoàn tiền. Mọi đường sửa các trường này phải làm mất hiệu lực approval cũ hoặc tạo revision mới theo quy tắc miền.

Mẫu dùng một workflow version để phát hiện màn hình duyệt đã cũ. Vì vậy, **mọi sửa đổi nội dung trọng yếu cũng phải tăng workflow version**. Nếu mô hình tách riêng content version và workflow version, command cần mang đủ điều kiện để ràng buộc nội dung người dùng đã xem. Không chỉ kiểm tra version trạng thái rồi duyệt một nội dung khác.

### 7.2. Annotation transaction cần hạ tầng thực thi

Cần có transaction manager phù hợp và cơ chế transaction annotation được bật, chẳng hạn `@EnableTransactionManagement` khi tự cấu hình. Với chế độ proxy, lời gọi phải đi qua proxy. Mẫu chọn `rollbackFor = Exception.class` để các lỗi kiểm tra phát ra từ thân method làm rollback theo cấu hình đó; không bắt lỗi rồi trả thành công. Tham chiếu: [Spring Framework 7.0: Using @Transactional](https://docs.spring.io/spring-framework/reference/7.0/data-access/transaction/declarative/annotations.html).

`@Transactional` không tự khóa một request, tạo unique constraint hay bảo vệ một giới hạn tổng trên nhiều request. Các cơ chế đó thuộc hợp đồng repository và database. Nếu evidence dùng database khác hoặc gọi dịch vụ audit qua HTTP, annotation ở đây không tự làm hai nơi commit nguyên tử.

`@PreAuthorize` trong mẫu kiểm tra authority; object policy và guard phụ thuộc dữ liệu nằm trong thân method có transaction. Không suy rằng một bean được gọi từ SpEL đã chạy trong transaction của method chỉ vì method có cả hai annotation. Thứ tự advisor phải được thiết kế nếu ứng dụng phụ thuộc vào điều đó.

### 7.3. Chọn cơ chế đồng thời theo bất biến

Với khóa request, hai checker cùng duyệt một request sẽ được tuần tự hóa trên bản ghi đó. Sau khi transaction thứ nhất commit, transaction thứ hai cần đọc trạng thái/version mới và từ chối chuyển trạng thái lần nữa.

Nếu dùng optimistic locking thay cho khóa bi quan, repository phải kiểm tra version tại write và xử lý conflict. Không phát tác động ngoài trước khi biết write/commit đã thành công. `expectedVersion` do client gửi hỗ trợ phát hiện dữ liệu cũ; người có version đúng vẫn phải có quyền.

Một giới hạn tổng như "mỗi checker chỉ được duyệt tối đa X trong ngày" cần bảo vệ cả dữ liệu tổng hợp tương ứng. Khóa hai request khác nhau không ngăn hai transaction cùng vượt giới hạn đó.

Membership hoặc policy cũng có thể thay đổi đồng thời. Transaction và khóa trên request **không tự khóa dữ liệu quyền**. Ứng dụng cần xác định thời điểm quyền có hiệu lực: tại quyết định được chấp nhận, hay phải phối hợp việc thu hồi quyền với cập nhật nghiệp vụ bằng khóa/version/protocol riêng. Ghi lại policy version giúp điều tra; bản thân việc ghi version chưa ngăn race.

## 8. Proxy Spring: annotation chỉ cưỡng chế trên đường gọi phù hợp

Trong mô hình Spring AOP dùng proxy, lời gọi `this.method()` không đi qua advice của proxy. Với proxy dựa trên lớp, `private` hoặc `final` method không thể được advice theo cơ chế override; `final` class không thể được tạo subclass proxy. Hãy xác định loại proxy thực tế. [Spring Framework 7.0: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/7.0/core/aop/proxying.html).

### 8.1. Một đường gọi làm yếu điều kiện quyền

Phác thảo dưới đây cố ý có lỗi; `performApproval` đại diện cho thân xử lý cập nhật:

~~~java
@Service
public class UnsafeRefundWorkflow {
    @PreAuthorize("isAuthenticated()")
    public ApprovalReceipt reviewAndApprove(UUID id, long version) {
        return this.approve(id, version);
    }

    @PreAuthorize("hasAuthority('SCOPE_refund.approve')")
    @Transactional
    public ApprovalReceipt approve(UUID id, long version) {
        return performApproval(id, version);
    }
}
~~~

Caller đi qua proxy vào `reviewAndApprove` chỉ gặp điều kiện đã đăng nhập của method ngoài. Lời gọi `this.approve` không kích hoạt riêng kiểm tra authority và transaction advice đặt ở method trong. Nếu có transaction từ caller thì thân xử lý có thể vẫn chạy trong transaction đó; điều này không chứng minh annotation bên trong đã có hiệu lực.

Cách tổ chức cho tình huống này là chuyển use case duyệt sang bean `RefundApprovalService` ở phần 7 và inject bean đó vào bean điều phối. Bean điều phối gọi `approvalService.approve(...)` qua proxy. Giữ các guard miền trong use case để mọi đường duyệt cùng tuân theo một hợp đồng.

Nếu một helper chỉ là chi tiết nội bộ của use case đã được bảo vệ, nó có thể là method private bình thường. Đừng coi annotation đặt trên helper là ranh giới phân quyền độc lập.

### 8.2. Những đường gọi khác cần kiểm tra

| Đường gọi | Điều cần chứng minh |
|---|---|
| Controller inject service | Reference được inject là bean được quản lý, rule và transaction được kích hoạt khi gọi |
| Consumer/scheduler inject service | Có principal/machine policy phù hợp và đi qua cùng ranh giới use case |
| `new RefundApprovalService(...)` | Đối tượng được dựng thủ công không tự có proxy Spring; không dùng cách này cho đường chạy cần advice |
| Gọi trong cùng instance | Không trông chờ method advice ở lời gọi nội bộ; kiểm tra điều kiện tại entry point thực tế |
| Repository được inject trực tiếp vào controller quản trị | Đường này có thể tránh application service; phải có thiết kế quyền và guard riêng hoặc đổi phụ thuộc |
| Unit test dựng service bằng `new` | Có thể kiểm tra guard thuần Java, nhưng chưa kiểm tra cưỡng chế annotation |

Chỉ thêm annotation khi review code chưa đủ. Cần vẽ được caller nào giữ reference nào và lời gọi nào thực sự đi qua proxy.

## 9. Kiểm tra sau khi trả kết quả không thay thế guard trước mutation

`@PostAuthorize` đánh giá kết quả sau khi method chạy. Không dùng nó làm điều kiện chính cho command ghi dữ liệu; tài liệu Spring cũng lưu ý tránh cách này với database write. [Spring Security 7.0: Authorization Method Results](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html#_authorization_method_results_with_postauthorize).

Giả sử method cập nhật trạng thái, gọi provider rồi mới kiểm tra owner trên `returnObject`. Khi bị từ chối, provider đã có thể nhận lệnh. Việc rollback database không thu hồi được tác động đó. Với nhiều advisor, còn phải xác định chính xác transaction đã commit ở thời điểm nào.

Đối với read use case, kiểm tra kết quả có thể là một lớp bổ sung nếu việc đọc không tạo tác động và dữ liệu không thoát qua cache, log hoặc callback trước đó. Query theo scope và trả projection tối thiểu vẫn giúp giới hạn dữ liệu được tải.

Tương tự, lọc collection sau khi đọc không tự giải quyết quyền trên tổng số kết quả, phân trang hay aggregate. Một response đã bỏ các dòng không được phép vẫn có thể để lộ count hoặc tổng tiền nếu phép tổng hợp lấy toàn bộ tenant. Hợp đồng read phải bảo vệ cả metadata lẫn từng item.

## 10. Worker, retry và idempotency cũng cần ranh giới quyền

### 10.1. Tách duyệt khỏi thực thi tác động

Một state machine minh họa:

~~~text
DRAFT
  → PENDING_APPROVAL
  → APPROVED
  → EXECUTION_QUEUED
  → EXECUTING
  → SUCCEEDED
~~~

Các chuyển trạng thái hủy, thất bại hoặc thử lại cần được khai báo riêng. Authority duyệt không mặc nhiên cấp quyền tạo execution, đổi tài khoản nhận hoặc đánh dấu thành công. Mỗi use case bảo vệ transition mà nó sở hữu.

Nếu cần phát sự kiện `RefundApproved`, có thể ghi outbox cùng transaction duyệt. Sự kiện cho biết một quyết định đã được ghi nhận; nó không tự cho phép consumer thực hiện mọi hành động có liên quan. Luồng tạo execution vẫn phải xác nhận approval hợp lệ với đúng nội dung và trạng thái hiện tại theo hợp đồng của hệ thống.

### 10.2. Không giả định SecurityContext tự đi theo thread hay message

Spring Security thường lưu SecurityContext theo thread. Khi chuyển công việc sang thread khác, cần cơ chế truyền ngữ cảnh có chủ đích; Spring cung cấp các wrapper như `DelegatingSecurityContextRunnable` và executor liên quan. [Spring Security 7.0: Concurrency Support](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/concurrency.html).

Truyền ngữ cảnh trong cùng tiến trình không phải một giao thức ủy quyền bền vững cho message queue. Consumer ở tiến trình khác cần xác minh nguồn lệnh, actor máy, tenant và phạm vi được phép theo cơ chế riêng.

Một command bất đồng bộ có thể lưu `tenantId`, `requestId`, `initiatedBy`, `approvedContentVersion`, `decisionId`, `commandId` và policy version. Các field này chỉ đáng tin khi đến từ producer đã được kiểm soát và được consumer đối chiếu với dữ liệu có thẩm quyền. JSON tự ghi `initiatedBy = admin` không tạo ra quyền.

Phân biệt người khởi tạo, người phê duyệt và principal đang thực thi. Nếu worker dùng service account, account đó chỉ cần quyền cho loại command và tenant mà nó được phân công. Không fallback sang quyền hệ thống khi thiếu ngữ cảnh.

Hệ thống phải quyết định một lệnh đã chấp nhận có tiếp tục hợp lệ sau khi người khởi tạo bị thu hồi quyền hay không. Với hành động rủi ro cao, bước thực thi có thể cần kiểm tra lại điều kiện hiện thời. Quyết định này phải được mô tả theo workflow; không để retry vô tình chọn chính sách khác lần chạy đầu.

### 10.3. Request trùng không được đi vòng authorization

Service ở phần 7 dùng state/version để ngăn phê duyệt lần hai. Nếu gửi lại cùng request và version sau khi lần đầu commit, kết quả có thể là conflict; mẫu chưa hứa trả lại cùng receipt.

Để hỗ trợ retry trả cùng kết quả, cần ledger idempotency với phạm vi khóa và fingerprint rõ ràng, chẳng hạn:

~~~text
key scope = tenant + actor/delegation scope + action + client key
fingerprint = request ID + command fields trọng yếu + expected version
stored result = receipt tối thiểu + operation ID + trạng thái xử lý
~~~

Scope có thể khác tùy nghiệp vụ, nhưng phải ngăn một caller lấy được kết quả riêng tư của caller khác. Cùng key và khác fingerprint phải bị từ chối theo hợp đồng API. Claim key, ghi thay đổi và lưu kết quả cần nhất quán, có unique constraint/cơ chế đồng thời phù hợp.

**Trước khi trả receipt đã lưu, vẫn phải xác thực caller và kiểm tra quyền đọc kết quả đó trong scope hiện tại.** Nhánh replay cần nhận diện một lệnh đã hoàn tất mà không yêu cầu trạng thái vẫn là chờ duyệt; nếu áp lại toàn bộ guard chuyển trạng thái, lần retry hợp lệ có thể bị từ chối chỉ vì lần đầu đã thành công. Điều này không cho phép bỏ object authorization.

Đối với provider, outbox có thể phát lại. Consumer phải nhận diện command trùng, dùng khả năng deduplicate của provider khi có, và đối soát kết quả không rõ sau timeout. Annotation phân quyền và transaction database không tự bảo đảm tác động ngoài xảy ra đúng một lần.

## 11. Lỗi và audit phải phản ánh đúng quyết định

| Tình huống | Ý nghĩa cần giữ trong hợp đồng |
|---|---|
| Không có credential hợp lệ | Authentication chưa đạt; với bearer API thường được xử lý bằng response 401 theo cấu hình |
| Caller hợp lệ nhưng thiếu authority hoặc object policy không cho phép | Từ chối quyền; có thể là 403, hoặc phản hồi che sự tồn tại của object theo policy |
| Object không thấy trong scope | Không trả dữ liệu ngoài scope; phân biệt lý do nội bộ với thông điệp public |
| Caller có quyền nhưng state/version không còn phù hợp | Conflict nghiệp vụ, chẳng hạn 409 theo hợp đồng API; không tự đổi thành "đã duyệt thành công" |
| Lỗi lưu dữ liệu/evidence | Không trả receipt thành công khi transaction không commit |

Không ánh xạ mọi exception thành 403: cách đó che mất lỗi hệ thống và conflict. Cũng không bắt `AccessDeniedException` rồi trả HTTP 200 với một object nhạy cảm. Bên ngoài HTTP, caller cần xử lý lỗi từ chối rõ ràng; không có response HTTP tự xuất hiện trong message consumer.

Bằng chứng thành công có thể gồm tenant, request ID, action, định danh actor đã giải quyết, người được ủy quyền nếu có, version/snapshot được duyệt, policy version và correlation/command ID. Chọn dữ liệu tối thiểu đủ truy vết; không lưu bearer token hoặc toàn bộ payload nhạy cảm vào log.

Trong mẫu, evidence thành công cùng transaction sẽ rollback khi mutation thất bại. Sự kiện **từ chối** cần kênh ghi nhận riêng nếu muốn giữ sau rollback; xác định hành vi khi kênh đó lỗi và tránh biến log thành đường rò rỉ dữ liệu. Một ca bị từ chối có thể có security event, nhưng không được có approval, outbox thực thi hoặc thay đổi số dư ngoài ý muốn.

## 12. Kiểm thử từng ranh giới và tác động sau cùng

Một response 403 chưa chứng minh đúng rule đã chạy. Nó có thể do CSRF, route rule hoặc object policy. Cần thiết kế dữ liệu đầu vào để ca kiểm thử chỉ đi tới ranh giới đang cần quan sát.

### 12.1. Ma trận ca tấn công

| Ca kiểm thử | Kết quả cần chứng minh |
|---|---|
| Token hợp lệ nhưng thiếu `SCOPE_refund.approve` | Route từ chối; use case chưa tạo tác động |
| Gọi bean service trực tiếp với authority đọc | Method security từ chối trước thân method |
| Có authority duyệt nhưng request thuộc tenant khác | Không lộ chi tiết, không đổi dữ liệu của tenant đó |
| Cùng tenant nhưng ngoài phạm vi phân công | Object policy từ chối dù route và method rule đều cho qua |
| Maker dùng account thứ hai cùng person identity | Không vượt quy tắc checker độc lập |
| Duyệt request đang ở DRAFT hoặc đã hủy | State guard từ chối, không tạo approval |
| Thay số tiền hoặc người nhận sau khi mở màn hình duyệt | Version/snapshot guard ngăn duyệt nội dung chưa xem |
| Hai transaction cùng duyệt một version | Chỉ có số approval được policy cho phép; ca còn lại conflict hoặc replay theo hợp đồng |
| Hai request khác nhau cùng dùng hạn mức cuối | Giới hạn tổng không bị vượt do race |
| Replay key bởi actor/tenant khác | Không lấy được receipt hoặc kết quả riêng tư |
| Cùng key nhưng đổi request ID/nội dung command | Phát hiện fingerprint khác, không tạo tác động mới |
| Gọi qua endpoint batch, quản trị hoặc consumer | Không bỏ qua method/object/state guard tương ứng |
| Thêm route hoặc public method mới | Mặc định từ chối ở bề mặt đã thiết kế, có ca kiểm thử cho quyền được mở |
| Thu hồi membership trước quyết định mới | Áp dụng đúng chính sách hiệu lực quyền đã công bố |
| Transaction ghi evidence hoặc save thất bại | Không còn approval đã commit một phần trong mẫu cùng database |

Mỗi ca từ chối nên kiểm tra dữ liệu bền vững, số approval, outbox và lời gọi provider liên quan. Khi cần kiểm tra sau commit/rollback, đọc bằng transaction/connection mới theo hạ tầng test; một entity còn trong persistence context của test có thể che kết quả thực tế.

### 12.2. Ví dụ nhỏ: chứng minh method security chạy qua bean

Đây là một test độc lập để quan sát việc chặn trước thân method, không phải bản test hoàn chỉnh của aggregate hoàn tiền. Nó cần JUnit Jupiter, `spring-test`, Spring Security và `spring-security-test` tương thích mốc phiên bản. Spring hỗ trợ tạo SecurityContext kiểm thử bằng `@WithMockUser`. [Spring Security 7.0: Testing Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/test/method.html).

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(MethodBoundaryTest.Config.class)
class MethodBoundaryTest {
    @Autowired ApprovalProbe probe;
    @Autowired AtomicInteger effectCounter;

    @BeforeEach
    void resetCounter() {
        effectCounter.set(0);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_refund.read")
    void missingApproveAuthorityIsDeniedBeforeBody() {
        assertThrows(AccessDeniedException.class, () -> probe.approve());
        assertEquals(0, effectCounter.get());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_refund.approve")
    void approveAuthorityReachesBody() {
        probe.approve();
        assertEquals(1, effectCounter.get());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class Config {
        @Bean
        AtomicInteger effectCounter() {
            return new AtomicInteger();
        }

        @Bean
        ApprovalProbe approvalProbe(AtomicInteger effectCounter) {
            return new ApprovalProbe(effectCounter);
        }
    }

    public static class ApprovalProbe {
        private final AtomicInteger effectCounter;

        public ApprovalProbe(AtomicInteger effectCounter) {
            this.effectCounter = effectCounter;
        }

        @PreAuthorize("hasAuthority('SCOPE_refund.approve')")
        public void approve() {
            effectCounter.incrementAndGet();
        }
    }
}
~~~

Test inject `probe` từ context đã bật method security; không tự dựng probe trong method test. Ca cho phép giúp xác nhận thân method hoạt động, còn ca từ chối chứng minh authority thiếu làm body chưa chạy.

`@WithMockUser` tạo principal phục vụ test, không phải JWT thật. Với service thực tế có `CurrentActor` yêu cầu JWT hoặc custom principal, cần fixture đúng loại principal, chẳng hạn `@WithSecurityContext` tùy biến, và mapping membership tương ứng. Nếu cố dùng principal sai loại rồi thấy lỗi, kết quả đó chưa kiểm tra object policy mong muốn.

### 12.3. HTTP test phải giữ filter chain hoạt động

Với MockMvc, cần tích hợp Spring Security filter chain theo cách thiết lập test của ứng dụng. Không tắt filter để làm các ca quyền chạy qua. Với CSRF đang bật, ca POST kiểm tra authority cần token CSRF hợp lệ. [Spring Security 7.0: Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/7.0/servlet/test/mockmvc/csrf.html).

Đoạn sau đặt trong fixture có controller, security configuration và MockMvc đã tích hợp filter; `requestId` là ID dữ liệu kiểm thử. Nó chủ đích thiếu authority duyệt:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Bên trong một test method:
mvc.perform(post("/api/refunds/{id}/approve", requestId)
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_refund.read")))
        .with(csrf())
        .contentType(APPLICATION_JSON)
        .content("{\"expectedVersion\":4}"))
    .andExpect(status().isForbidden());
~~~

Với rule HTTP ở phần 3, ca này phải bị chặn trước service. Cần xác minh thêm service/provider chưa được gọi hoặc dữ liệu chưa thay đổi theo cấp độ test đã chọn.

`jwt()` cung cấp JWT/principal giả cho authorization test. Nó không chứng minh decoder thực sự kiểm tra chữ ký, expiry, issuer hay audience. Cần nhóm test authentication riêng qua đường bearer token/decoder thực tế phù hợp. [Spring Security 7.0: Testing JWT Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/test/mockmvc/oauth2.html#_testing_jwt_authentication).

Để kiểm tra object policy, dùng authority duyệt hợp lệ, principal đúng hợp đồng và CSRF hợp lệ nếu cần; sau đó chọn object ngoài scope. Để kiểm tra proxy service, gọi bean trực tiếp thay vì đi qua route đã chặn. Để kiểm tra transaction/lock, dùng database và transaction thật của môi trường test, tạo cạnh tranh có điều phối thay vì chỉ gọi hai lần tuần tự.

Các đoạn mã trong bài là mẫu để triển khai và kiểm thử tại ứng dụng; chúng chưa được chạy đối với một repository ứng dụng cụ thể trong bước biên soạn này.

## 13. Bài thực hành: xác định ranh giới của một luồng duyệt

Cho API `POST /api/refunds/{id}/approve` nhận `expectedVersion`. Người dùng có thể gọi API trực tiếp; hệ thống còn có endpoint batch và một consumer. Tenant được chọn bằng header nhưng caller có membership ở nhiều tenant.

1. Vẽ các đường gọi từ từng entry point tới nơi ghi approval. Đánh dấu filter chain, proxy, nơi giải quyết tenant và transaction thực sự.
2. Viết bất biến cho đúng object, checker độc lập, snapshot nội dung và state/version. Nêu dữ liệu nào từ principal, dữ liệu nào phải tra cứu và field nào chỉ là đầu vào chưa đáng tin.
3. Đặt authority rule trên use case và object policy trên request được dùng để cập nhật. Giải thích vì sao caller có authority tổng quát vẫn có thể bị từ chối.
4. Chọn khóa/version cùng cơ chế bảo vệ hạn mức tổng nếu có. Chỉ ra điều gì xảy ra khi hai checker duyệt cùng lúc hoặc khi membership bị thu hồi.
5. Thiết kế replay: người có key nhưng không có quyền đọc receipt sẽ nhận gì; cùng key nhưng thay request ID sẽ bị xử lý ra sao.
6. Lập ca kiểm thử gọi HTTP, gọi bean và gọi consumer. Với mỗi ca từ chối, ghi rõ dữ liệu nào phải giữ nguyên và security event nào được phép xuất hiện.

Kết quả cần nộp là bản đồ đường gọi, hợp đồng quyền/state và các kiểm tra tác động có thể quan sát. Một vị trí đặt `@PreAuthorize` chỉ được coi là ranh giới có hiệu lực khi đường gọi thực tế đi qua nó và những bất biến phụ thuộc dữ liệu vẫn được bảo vệ tại thời điểm thay đổi.
