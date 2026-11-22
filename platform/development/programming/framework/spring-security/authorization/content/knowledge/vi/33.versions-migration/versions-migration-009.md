# Thay đổi check, authorize, AuthorizationResult và cách kết hợp manager

## 1. Mục tiêu và ngữ cảnh

**AuthorizationManager<T>** trong Spring Security là điểm mở rộng để quyết định một **Authentication** có được truy cập một đối tượng bảo vệ hay không. Đối tượng ấy có thể là **RequestAuthorizationContext** khi xét HTTP, **MethodInvocation** khi xét method hoặc một lớp domain trong bài kiểm thử. Cùng một người dùng có thể được phép ở đối tượng này nhưng bị từ chối ở đối tượng khác.

Khi chuyển Spring Security giữa các phiên bản, logic cấp quyền thường hỏng ở ba chỗ: mã vẫn gọi phương thức cũ **check(...)**; biến kết quả còn gắn chặt với **AuthorizationDecision** trong khi API mới trả **AuthorizationResult**; và cách ghép **AuthorizationManagers.allOf/anyOf** vô tình biến điều kiện bắt buộc thành tùy chọn hoặc xử lý **abstain (null)** thành allow.

Sau bài học, bạn sẽ:

1. Phân biệt chính xác sự thay đổi từ **check** sang **authorize**, lúc **AuthorizationResult** xuất hiện và điều kiện biên dịch ở Spring Security 6.x/7.x.
2. Hiểu **allow**, **deny**, **abstain**, cách dùng **verify(...)**, và tại sao null cần chính sách rõ ràng.
3. Ghép nhiều AuthorizationManager bằng **allOf**, **anyOf**, **not** mà giữ nguyên ranh giới bảo mật.
4. Xây dựng một ví dụ Java 17+ chạy được với Spring Security 7, đưa manager vào HTTP/method security và kiểm thử hồi quy chuyển phiên bản.

**Giới hạn:** tập trung vào thay đổi API AuthorizationManager và cách tổng hợp chính sách của module Spring Security authorization. Những phần liên quan xác thực, cache và ACL chỉ được đề cập khi tác động trực tiếp đến quyết định.

## 2. Các mốc thay đổi API theo phiên bản

| Dòng phiên bản | Phương thức AuthorizationManager | Kiểu kết quả | Lưu ý khi chuyển đổi |
| --- | --- | --- | --- |
| **6.2–6.3** | **check(Supplier<Authentication>, T)** | **AuthorizationDecision** hoặc null | Sử dụng check ở mã chưa nâng dependency |
| **6.4–6.5** | **check(...)** deprecated; **authorize(...)** được thêm như **default method** | authorize trả **AuthorizationResult** hoặc null | Thay call site sang authorize; lớp custom ở 6.5 vẫn cần đáp ứng phương thức abstract check |
| **7.0+** | **authorize(...)** là phương thức chức năng/abstract; **check(...)** không còn trên interface | **AuthorizationResult** hoặc null | Chuyển class override check sang override authorize và sửa các call site còn check |

**AuthorizationResult** được giới thiệu từ **6.3**; **AuthorizationManager.authorize** có từ **6.4**. Điều này giải thích vì sao một dự án có type **AuthorizationResult** nhưng vẫn không thể gọi **manager.authorize** khi dùng Spring Security 6.3.

Ở Spring Security 6.4–6.5, **authorize** mặc định có thể gọi **check** trong implementation cũ. Vì thế lớp chỉ override **check** có thể tiếp tục làm việc với caller mới gọi **authorize**. Nhưng thêm mỗi override **authorize** vào một custom class 6.5 có thể không biên dịch vì interface lúc đó vẫn có phương thức abstract **check**. Đến 7.x, phải triển khai **authorize** theo chữ ký mới.

**AuthorizationDecision** không bị loại bỏ ở 7.x: đây vẫn là lớp đơn giản thực hiện **AuthorizationResult**. Mã mới có thể tiếp tục **return new AuthorizationDecision(true)** hoặc **false**. Sự thay đổi nằm ở hợp đồng trả về của manager, không bắt buộc tạo lớp kết quả mới.

Không tự trộn **spring-security-core**, **spring-security-web**, **spring-security-config** khác major version; hãy để BOM Spring Boot/Spring Security thống nhất phiên bản và build kiểm chứng.

## 3. AuthorizationManager nhận gì và trả gì?

Hai tham số chủ đạo:

- **Supplier<Authentication> authentication**: một hàm cung cấp người dùng đã xác thực. Việc truyền Supplier giúp các manager không cần truy xuất Authentication nếu policy chưa đòi hỏi. Không lưu Authentication lấy từ request hiện tại làm kết quả cho request khác.
- **T object**: ngữ cảnh/đối tượng đang được kiểm tra. Ví dụ **RequestAuthorizationContext** chứa request, còn **MethodInvocation** có method và tham số; bản thân domain object có thể chứa id/owner/tenant. Kiểu T phải khớp với nơi manager được sử dụng.

**AuthorizationResult** là interface có **boolean isGranted()**. **AuthorizationDecision** là một implementation phổ biến:

~~~java
AuthorizationResult yes = new AuthorizationDecision(true);
AuthorizationResult no = new AuthorizationDecision(false);
boolean allow = yes.isGranted(); // true
boolean deny = no.isGranted();   // false
~~~

Đây là ví dụ một phần, cần imports từ **org.springframework.security.authorization** và Spring Security dependency. Không thể viết **new AuthorizationResult(true)** vì đó là interface. Không ép kiểu kết quả sang AuthorizationDecision khi không thực sự cần; một manager có thể trả loại AuthorizationResult khác.

**Ba trạng thái quyết định:**

| authorize(...) trả về | Nghĩa | Ứng dụng tự xử lý kết quả thế nào? |
| --- | --- | --- |
| **result != null && result.isGranted()** | ALLOW | Chỉ cấp quyền khi đã là kết quả cuối của policy |
| **result != null && !result.isGranted()** | DENY | Từ chối theo hợp đồng security hiện hành |
| **result == null** | ABSTAIN, không đưa quyết định | Không suy diễn thành ALLOW; dùng fallback/tổng hợp đã định nghĩa |

Ví dụ mã gây lỗi:

~~~java
AuthorizationResult result = manager.authorize(authSupplier, target);
boolean allow = result == null || result.isGranted(); // SAI nếu null chưa được xử lý
~~~

Nếu policy trả null vì thiếu tenant hoặc không hỗ trợ loại object, đoạn trên sẽ cho phép một yêu cầu mà không manager nào chịu trách nhiệm. Tại điểm gọi quyết định nhạy cảm, chuyển theo **fail closed** nếu policy yêu cầu:

~~~java
AuthorizationResult result = manager.authorize(authSupplier, target);
boolean allow = result != null && result.isGranted();
~~~

Phân biệt: **null** không có nghĩa mặc định là deny trong mọi filter/interceptor; phải hiểu nơi dùng AuthorizationManager và fallback của bộ tổng hợp. Với điều kiện **bắt buộc**, nên trả một quyết định deny rõ ràng khi không đủ dữ liệu thay vì abstain.

## 4. check, authorize, verify

**check(Supplier<Authentication>, T)** là phương thức lịch sử; trả **AuthorizationDecision**. Trong 6.4–6.5 nó deprecated, ở 7.x không còn. Dùng **check** trong code mới nhắm đến 7.x sẽ không biên dịch.

**authorize(Supplier<Authentication>, T)** (chữ ký chi tiết có thể khác theo phiên bản) trả **AuthorizationResult** hoặc null. Nó hữu ích khi cần lấy quyết định để audit, ghi log, kiểm tra policy tổng hợp hoặc sử dụng thuộc tính result mà implementation cung cấp.

**verify(...)** là default method nhằm **ném AccessDeniedException khi nhận quyết định từ chối**. Nó phù hợp ở code chỉ cần bảo đảm access, nhưng **không tự giải quyết null thành deny trong mọi tình huống**. Nếu yêu cầu nghiêm ngặt, hãy cấu hình manager tổng hợp trả deny khi all-abstain hoặc tự xử lý kết quả:

~~~java
AuthorizationResult result = manager.authorize(() -> authentication, document);
if (result == null || !result.isGranted()) {
    throw new AccessDeniedException("Access denied");
}
~~~

Đoạn trên **không độc lập**, các tên manager/authentication/document phải có sẵn và cần import **AccessDeniedException** đúng module/phiên bản.

**AuthorizationManager khác AuthenticationManager:** AuthenticationManager giải quyết đăng nhập/credential; AuthorizationManager quyết định quyền trên HTTP/method/object của một Authentication. Đổi từ check sang authorize không phải đổi API xác thực.

## 5. Custom implementation: mã cũ và mã mới

### Spring Security 6.4–6.5

Khi dự án vẫn dùng API cũ, có thể có custom manager:

~~~java
final class DocumentOwnerManager implements AuthorizationManager<Document> {
    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            Document document) {
        Authentication user = authentication.get();
        return new AuthorizationDecision(
                user != null && user.getName().equals(document.owner()));
    }
}
~~~

Đây là **mã minh họa**, chưa gồm các import/kiểu domain. Phiên bản 6.5 có **authorize** mặc định nên caller dùng **manager.authorize(...)** vẫn có thể đi qua logic check này. Khi target chuyển sang 7.x, đổi điểm override.

### Spring Security 7.x

Một implementation tương ứng ở 7.x:

~~~java
final class DocumentOwnerManager implements AuthorizationManager<Document> {
    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            Document document) {
        Authentication user = authentication.get();
        return new AuthorizationDecision(
                user != null
                && user.isAuthenticated()
                && user.getName().equals(document.owner()));
    }
}
~~~

Điểm khác là **authorize**, **AuthorizationResult** và chữ ký Supplier có wildcard theo API 7.x. Với file Java phải chạy nhiều version, cần compile kiểm chứng trên từng dòng: generic **Supplier<Authentication>** và **Supplier<? extends Authentication>** ở override không nên được coi là cùng chữ ký.

Một lambda đơn giản trả AuthorizationDecision có thể giảm mã boilerplate và dễ tương thích hơn giữa 6.5/7.x vì compiler chọn abstract method theo interface hiện tại:

~~~java
AuthorizationManager<Document> owner = (authentication, document) -> {
    Authentication user = authentication.get();
    return new AuthorizationDecision(user != null
            && user.isAuthenticated()
            && user.getName().equals(document.owner()));
};
~~~

Khi cần dependency, truy vấn database, quan sát hoặc policy phức tạp, một class có tên rõ ràng dễ kiểm thử và rà soát hơn.

## 6. Kết hợp manager bằng AuthorizationManagers

**AuthorizationManagers** (số nhiều) là utility tạo một AuthorizationManager hợp thành. Ba factory chính:

| Factory | Tư duy | Ví dụ |
| --- | --- | --- |
| **allOf(m1, m2, …)** | AND: chính sách phải thỏa mọi điều kiện yêu cầu | authentication AND cùng tenant AND có scope đọc |
| **anyOf(m1, m2, …)** | OR: có ít nhất một đường cho phép hợp lệ | chủ sở hữu OR tài liệu công khai |
| **not(m)** | Đảo quyết định của m | không thuộc nhóm bị cấm, nếu policy m luôn có quyết định rõ |

**Ví dụ đúng về ranh giới:**

~~~text
ALLOW = authenticated
    AND sameTenant
    AND hasAuthority("document:read")
    AND (isOwner OR isPublished)
~~~

Nếu viết **anyOf(authenticated, sameTenant, hasRead, isOwner, isPublished)**, người dùng chỉ cần thỏa một điều kiện (ví dụ đã đăng nhập) để được allow. Đây là lỗi bảo mật dù API compile thành công. Hãy dùng **allOf** cho hàng rào bắt buộc, và chỉ dùng **anyOf** cho các con đường thay thế *thực sự*.

### 6.1. all-abstain và trường hợp không có manager

Các factory có overload nhận **AuthorizationDecision allAbstainDefaultDecision**. Nó xác định fallback khi toàn bộ delegate abstain hoặc không có delegate phù hợp; rất hữu ích khi policy cần deny-by-default:

~~~java
AuthorizationManager<Document> guardedAnd = AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        authenticated, sameTenant, canRead);

AuthorizationManager<Document> guardedOr = AuthorizationManagers.anyOf(
        new AuthorizationDecision(false),
        isOwner, isPublished);
~~~

Đây là đoạn minh họa; các biến **authenticated**, **sameTenant**, **canRead**, **isOwner**, **isPublished** phải là những manager cùng kiểu **AuthorizationManager<Document>**. Tránh tự hiểu khác kiểu T có thể ghép trực tiếp.

Javadoc mô tả **allOf(...)** không truyền default có kết quả **grant** khi danh sách delegate rỗng; **anyOf(...)** không truyền default có kết quả **deny** khi danh sách rỗng. Đừng tạo danh sách manager rỗng vì cấu hình thiếu rồi tin rằng allOf sẽ tự bảo vệ. Khi manager có thể trả null, hãy đặt default deny tường minh theo yêu cầu.

Một điều kiện bắt buộc như **sameTenant** cần **deny** nếu không xác minh được tenant, thay vì null. **allOf** có thể bỏ qua một delegate abstain khi các delegate khác chấp nhận; default deny cho *all-abstain* không biến mọi null thành deny. Do đó, tính bắt buộc phải xuất phát từ từng manager và ma trận test, không chỉ từ factory.

### 6.2. Ma trận quan trọng

Ký hiệu **A**: allow, **D**: deny, **Ø**: abstain.

| Manager 1 | Manager 2 | allOf (định hướng) | anyOf (định hướng) |
| --- | --- | --- | --- |
| A | A | A | A |
| A | D | D | A |
| D | D | D | D |
| D | Ø | D | D khi có fallback deny |
| Ø | Ø | D khi cấu hình all-abstain default = deny | D khi cấu hình all-abstain default = deny |
| A | Ø | Có thể A vì policy còn lại abstain | A |

**A + Ø** là trường hợp nguy hiểm nếu Ø phát sinh do thiếu dữ liệu của điều kiện bắt buộc. Không cố ép mọi null thành false một cách mù quáng; thay vì vậy, xác định manager nào được phép abstain và manager nào buộc phải đưa quyết định.

**not(manager)** không tự bảo đảm null trở thành grant; nếu manager có thể abstain thì phải kiểm thử và xử lý fallback. Khi diễn đạt phủ định của một quyền bắt buộc, dùng logic trả boolean rõ ràng sẽ dễ bảo đảm fail closed hơn.

## 7. Ví dụ Java 17+ chạy với Spring Security 7

Bài chạy độc lập dưới đây tạo các manager: có authority **document:read**, sở hữu tài liệu, tài liệu công khai. Quy tắc cuối: **hasRead AND (isOwner OR isPublished)**. Có một manager trả null để chứng minh all-abstain default deny. Chương trình dùng **Spring Security 7.0.7** và JDK 17 trở lên; nó không mở web server, không giả định controller hay database.

Tạo **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.0.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AuthorizationMigrationDemo'
}
~~~

Tạo **src/main/java/demo/AuthorizationMigrationDemo.java**:

~~~java
package demo;

import java.util.List;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class AuthorizationMigrationDemo {

    record Document(long id, String owner, boolean published) {}

    private static boolean allowed(AuthorizationManager<Document> manager,
                                   Authentication auth, Document document) {
        AuthorizationResult result = manager.authorize(() -> auth, document);
        return result != null && result.isGranted();
    }

    public static void main(String[] args) {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
                "alice", "n/a",
                List.of(new SimpleGrantedAuthority("document:read")));
        Authentication bob = UsernamePasswordAuthenticationToken.authenticated(
                "bob", "n/a",
                List.of(new SimpleGrantedAuthority("document:write")));

        AuthorizationManager<Document> hasRead =
                AuthorityAuthorizationManager.hasAuthority("document:read");

        AuthorizationManager<Document> isOwner = (authentication, doc) -> {
            Authentication user = authentication.get();
            return new AuthorizationDecision(user != null
                    && user.isAuthenticated()
                    && user.getName().equals(doc.owner()));
        };

        AuthorizationManager<Document> isPublished =
                (authentication, doc) -> new AuthorizationDecision(doc.published());

        AuthorizationManager<Document> ownerOrPublic = AuthorizationManagers.anyOf(
                new AuthorizationDecision(false), isOwner, isPublished);

        AuthorizationManager<Document> readPolicy = AuthorizationManagers.allOf(
                new AuthorizationDecision(false), hasRead, ownerOrPublic);

        Document ownPrivate = new Document(101L, "alice", false);
        Document otherPublic = new Document(102L, "carol", true);
        Document otherPrivate = new Document(103L, "carol", false);

        System.out.println("alice-own=" + allowed(readPolicy, alice, ownPrivate));
        System.out.println("alice-public=" + allowed(readPolicy, alice, otherPublic));
        System.out.println("alice-other-private=" +
                allowed(readPolicy, alice, otherPrivate));
        System.out.println("bob-no-read=" +
                allowed(readPolicy, bob, otherPublic));

        AuthorizationManager<Document> abstain =
                (authentication, doc) -> null;

        AuthorizationManager<Document> strict = AuthorizationManagers.allOf(
                new AuthorizationDecision(false), abstain);
        System.out.println("all-abstain=" + allowed(strict, alice, ownPrivate));

        try {
            readPolicy.verify(() -> alice, otherPrivate);
            System.out.println("verify=allow");
        } catch (AccessDeniedException ex) {
            System.out.println("verify=deny");
        }
    }
}
~~~

Chạy từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew run --quiet
~~~

Nếu chưa có Wrapper, dùng **gradle run --quiet** khi đã cài Gradle; trên Windows dùng **gradlew.bat run --quiet**. Với JDK/Gradle/dependency hoạt động, stdout từ chương trình là:

~~~text
alice-own=true
alice-public=true
alice-other-private=false
bob-no-read=false
all-abstain=false
verify=deny
~~~

Giải thích: Alice có quyền đọc và là chủ của tài liệu 101; có quyền đọc tài liệu 102 public; bị chặn ở tài liệu 103 private không thuộc sở hữu. Bob có write nhưng thiếu read nên bị chặn ở tài liệu public. Một manager chỉ abstain được bọc bởi **allOf(default deny, …)** sẽ không cấp quyền. **verify** ném lỗi khi readPolicy trả deny.

Chương trình có **Authentication giả cho minh họa**, không có bộ xác thực tài khoản thật. Trong ứng dụng web, chỉ tin Authentication do hệ thống authentication đáng tin cấp; không tự tạo Authentication authenticated từ dữ liệu client gửi.

**Giới hạn phiên bản:** Ví dụ dùng 7.0.7 cố định để có API authorize mới. Ở dự án Spring Boot đang quản lý version, lấy Spring Security version tương thích từ BOM thay vì kéo lẻ module 7.x vào tập 6.x. Nếu target là 6.3, mã gọi authorize không biên dịch; cần nâng dependency hoặc đổi về check khi chưa thể nâng.

## 8. Gắn manager vào HTTP authorization

**HttpSecurity.authorizeHttpRequests** cho phép dùng manager tùy chỉnh qua **.access(...)**. Ví dụ cấu hình Servlet (mã minh họa, cần imports, bean và dependency Spring Security web/config):

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        AuthorizationManager<RequestAuthorizationContext> reportPolicy)
        throws Exception {

    return http
            .authorizeHttpRequests(registry -> registry
                    .requestMatchers("/reports/**").access(reportPolicy)
                    .anyRequest().denyAll())
            .build();
}
~~~

Một manager cùng kiểu RequestAuthorizationContext có thể kết hợp:

~~~java
AuthorizationManager<RequestAuthorizationContext> scope =
        AuthorityAuthorizationManager.hasAuthority("SCOPE_reports.read");

AuthorizationManager<RequestAuthorizationContext> sameTenant =
        (authentication, context) -> {
            Authentication user = authentication.get();
            boolean permitted = user != null
                    && tenantPolicy.canAccessRequest(user, context.getRequest());
            return new AuthorizationDecision(permitted);
        };

AuthorizationManager<RequestAuthorizationContext> reportPolicy =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false), scope, sameTenant);
~~~

**tenantPolicy** trong đoạn minh họa là service phải có implementation kiểm tra tenant từ nguồn đáng tin. Không cấp quyền chỉ dựa trên header/ID do người dùng tự khai; và nếu tenant không xác định được thì trả deny. Khi HTTP route không mang đủ thông tin của tài nguyên, còn cần object-level check tại service.

**Chọn rule khác với ghép policy:** **RequestMatcherDelegatingAuthorizationManager** chọn delegate theo request matcher, phụ thuộc thứ tự matcher. Rule **/reports/** không tự AND với **anyRequest()** ở dưới; nếu muốn cả scope và tenant trên /reports/**, truyền **một manager allOf(...)** vào chính matcher đó. Đặt matcher cụ thể trước matcher bao quát.

Không ghép trực tiếp **AuthorizationManager<Document>** từ mục 7 với **AuthorizationManager<RequestAuthorizationContext>** bằng ép kiểu. Cả hai có ngữ cảnh khác nhau. Cần manager thích hợp hoặc một lớp adapter chuyển ngữ cảnh một cách có kiểm soát.

## 9. Phương thức Java và AuthorizationManager

Ở method security, ngữ cảnh có thể là **MethodInvocation**, khác với HTTP request. Spring Security cung cấp các interceptor như **AuthorizationManagerBeforeMethodInterceptor** và **AuthorizationManagerAfterMethodInterceptor** cùng annotation **@PreAuthorize**, **@PostAuthorize**. Gắn manager đúng nơi kiểm soát quan trọng hơn việc tự gọi nó trong một helper không được sử dụng.

Ví dụ method security:

~~~java
@Service
class DocumentService {

    @PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
    public Document read(long documentId) {
        return repository.findById(documentId).orElseThrow();
    }
}
~~~

Đây là mã **không độc lập**, cần **@EnableMethodSecurity**, bean **documentPolicy**, repository và cấu hình parameter names (ví dụ build với **-parameters**). documentPolicy phải kiểm tra quyền thực tế theo Authentication/documentId; annotation không tự cung cấp ACL hay database. Với Spring AOP proxy, **self-invocation** trong cùng bean có thể đi vòng advice; test nên gọi qua bean proxy thực tế.

Một lớp **AuthorizationManager<MethodInvocation>** có thể lấy tham số phương thức và quyết định trước khi gọi. Với bài toán kiểm tra giá trị trả về, cân nhắc post-authorization. Đừng dùng HTTP request context ở nơi đang thực thi method vì kiểu T và ngữ cảnh thực thi khác nhau.

## 10. Spring Security 7: AuthorizationManagerFactory

Spring Security **7.0** giới thiệu **AuthorizationManagerFactory<T>** để tạo các manager cơ bản như **hasRole**, **hasAuthority**, **authenticated**, **permitAll**, **denyAll** và một số biến thể. **DefaultAuthorizationManagerFactory** hỗ trợ cấu hình role prefix, role hierarchy và cách xác định trạng thái authentication cho những manager được factory tạo.

Cần phân biệt:

- **AuthorizationManagerFactory**: tạo từng manager từ một điều kiện có sẵn.
- **AuthorizationManagers**: kết hợp các manager bằng **allOf**, **anyOf**, **not**.
- **RequestMatcherDelegatingAuthorizationManager**: chọn manager theo matcher HTTP.
- **AuthorizationManager**: interface thực thi quyết định cho T cụ thể.

Với dự án đang ở 6.x, không sao chép API factory chỉ có ở 7.x. Với role thông thường **hasRole("ADMIN")** kiểm tra authority được prefix thành **ROLE_ADMIN**; **hasAuthority("ROLE_ADMIN")** so khớp chuỗi cụ thể. Cấu hình prefix không nhất quán có thể làm quyền bị deny hoặc allow sai khi migrate.

## 11. Khi chuyển từ AccessDecisionManager/AccessDecisionVoter

Các mô hình cũ gồm **AccessDecisionVoter** với **ACCESS_GRANTED**, **ACCESS_DENIED**, **ACCESS_ABSTAIN**; **AffirmativeBased**, **UnanimousBased**, **ConsensusBased** tổng hợp phiếu theo chiến lược. **AuthorizationManager** thay thế hướng này, nhưng ghép bằng allOf/anyOf không phải phép đổi tên tương đương hoàn toàn.

- **AffirmativeBased** có thể chấp nhận khi tồn tại phiếu grant dù voter khác deny (theo cơ chế cụ thể); chuyển sang **allOf** sẽ từ chối nếu có một manager deny.
- **UnanimousBased** và **allOf** khác nhau ở chi tiết abstain/all-abstain và cấu hình mặc định; cần regression test.
- **ConsensusBased** đếm phiếu/tie, không tương đương **anyOf** chỉ cần một allow.
- Một voter cũ có thể **abstain** khi không nhận dạng được attribute; khi chuyển sang manager cần phân định không áp dụng chính sách, thiếu dữ liệu và explicit deny.

Nếu policy cũ có trọng số, ưu tiên hoặc veto, có thể cần **custom composite AuthorizationManager** với semantics rõ thay vì ép vào allOf/anyOf. Hãy ghi ma trận đầu vào → quyết định cũ, rồi kiểm tra mã mới với cùng fixture.

## 12. Kiểm thử hồi quy và ma trận quyết định

| Test | Input | Mong đợi |
| --- | --- | --- |
| **T1** | User có read, là owner | ALLOW |
| **T2** | User có read, object public | ALLOW |
| **T3** | User có read, object private của người khác | DENY |
| **T4** | User chỉ có write, object public | DENY |
| **T5** | Thiếu Authentication hoặc user chưa được xác thực | DENY |
| **T6** | User có role nhưng tenant khác | DENY |
| **T7** | Manager trả null, tất cả delegate abstain | DENY khi dùng allAbstainDefaultDecision=false |
| **T8** | Một manager allow, một manager abstain vì thiếu tenant | Mandatory tenant manager phải trả DENY |
| **T9** | Manager trả explicit deny, gọi verify | Ném AccessDeniedException |
| **T10** | Danh sách delegate rỗng vì cấu hình sai | Không được vô tình allow |
| **T11** | Phương thức custom đã chuyển từ check sang authorize | Cùng policy decision ở mọi fixture |
| **T12** | HTTP matcher cụ thể và matcher tổng quát | Đúng rule ưu tiên, không bỏ sót AND condition |
| **T13** | Method gọi qua proxy và self-invocation | Tường minh đường thực sự có interceptor |
| **T14** | Spring Security 7 compile target | Không còn lời gọi/override check cũ |

Kiểm thử **unit** trên manager để phát hiện logic sai, rồi **integration** qua SecurityFilterChain hoặc method proxy để chứng minh điểm kiểm soát thực sự gọi manager. Với HTTP cần assert cả mã 401/403 theo authentication/authorization handler và việc không lộ dữ liệu; code có thể cố ý trả 404 để che sự tồn tại tài nguyên.

### Checklist chuyển đổi an toàn

1. Kiểm tra dependency tree và BOM, ghi chính xác phiên bản Spring Security modules đang dùng.
2. Tìm mọi **.check(...)** trên AuthorizationManager và **@Override check(...)** trong custom class; xác định code 6.x hay 7.x.
3. Đổi **call site** thành **authorize(...)** (nếu target 6.4+), đổi biến kết quả sang **AuthorizationResult**.
4. Kiểm tra nhánh **null**. Không coi không có quyết định là allow tại điểm xử lý cuối khi chính sách yêu cầu deny-by-default.
5. Với custom class build 7.x, override **authorize(...)** đúng chữ ký; với 6.5 vẫn phải tuân theo abstract check nếu chưa nâng major.
6. Xem lại cấu trúc allOf/anyOf, phân biệt bắt buộc và thay thế; cấu hình **allAbstainDefaultDecision** khi cần.
7. Kiểm tra generic T ở HTTP/method/domain; không ép kiểu giữa context không tương thích.
8. So sánh ma trận allow/deny/abstain trước–sau, bao gồm trường hợp không Authentication, tenant khác, role/authority thiếu, dữ liệu lỗi.
9. Chạy build/test đầy đủ khi đổi dependency; kiểm tra runtime Spring Security filter chain và method interceptors.
10. Quan sát sự kiện/metric authorization và đảm bảo không ghi credential nhạy cảm; các lỗi denied phải được xử lý theo chính sách hệ thống.

### Lỗi phổ biến

**Lỗi 1 – chỉ đổi tên method ở interface custom:** Code 6.5 còn yêu cầu abstract check; code 7.x loại check. Cần chọn target version chính xác.

**Lỗi 2 – ép AuthorizationResult về AuthorizationDecision:** Một implementation khác có thể trả kết quả hợp lệ nhưng không thuộc lớp cụ thể; chỉ cần isGranted là đủ cho quyết định boolean.

**Lỗi 3 – allOf không có delegate:** Mặc định có thể grant với tập rỗng; nếu chính sách nhạy cảm, validate cấu hình và dùng default deny.

**Lỗi 4 – dùng anyOf để ghép role với tenant:** Cho phép vì role đúng dù tenant sai. Dùng allOf cho hàng rào bắt buộc.

**Lỗi 5 – hiểu abstain là deny hoặc allow ở mọi tầng:** Ý nghĩa null phụ thuộc composite và nơi xử lý. Bắt buộc viết test cả null.

**Lỗi 6 – test chỉ gọi manager trực tiếp:** Không chứng minh route/method đã thực sự gắn policy. Cần tích hợp theo HTTP filter hoặc AOP proxy.

**Lỗi 7 – áp dụng API 7.x trong mã 6.3:** AuthorizationManager.authorize chỉ có từ 6.4; compilation và tài liệu phải cùng target version.

**Lỗi 8 – không kiểm tra semantics của voter cũ:** Chuyển AffirmativeBased sang allOf có thể làm thay đổi chính sách, dù tất cả class compile.

## 13. Bài tập vận dụng

**Bài tập A – API migration:** trên Spring Security 6.5, viết manager custom với **check(...)** và caller **authorize(...)**. Sau đó nâng lên 7.x, chuyển custom class sang override **authorize(...)**. Chạy cùng bộ test để chứng minh kết quả không đổi.

**Bài tập B – AND/OR:** dựng policy **sameTenant AND hasRead AND (isOwner OR isPublished)**. Dùng ít nhất hai user, hai tenant, ba object; so sánh cố ý dùng anyOf sai với allOf đúng để nhận diện privilege escalation.

**Bài tập C – abstain:** dựng một manager trả null khi thiếu tenant. So sánh allOf/anyOf với **allAbstainDefaultDecision=deny** và thiết kế lại manager bắt buộc theo hướng thiếu dữ liệu → deny.

**Bài tập D – điểm thực thi:** đưa manager vào **authorizeHttpRequests().access(...)** của một endpoint, rồi kiểm thử request thật cho allow, deny, anonymous và cross-tenant. Bổ sung một method security test qua proxy.

**Tiêu chí đạt:** hiểu chênh lệch check/authorize theo version; dùng AuthorizationResult và isGranted đúng cách; phân biệt allow/deny/abstain; ghép policy đúng AND/OR; không để default/rỗng/null tạo lỗ hổng; có regression test trên điểm cưỡng chế và version đích.

## Tài liệu chính thức

- [Spring Security 6.5 — AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7 — AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [AuthorizationResult](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html)
- [AuthorizationDecision](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html)
- [AuthorizationManagers — allOf/anyOf/not](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagers.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorization Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html)
