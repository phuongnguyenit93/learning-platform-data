# AOT, native image và kiểm tra tương thích proxy, biểu thức theo phiên bản

## 1. Mục tiêu và phạm vi

Spring Security thực thi authorization ở mức HTTP request thông qua SecurityFilterChain/AuthorizationManager và ở mức method thông qua @EnableMethodSecurity, @PreAuthorize, @PostAuthorize cùng các advisor của Spring AOP. Khi chuyển ứng dụng từ JVM thường sang **Spring AOT** (Ahead-of-Time) hoặc **GraalVM Native Image**, các quy tắc bảo mật phải tiếp tục hoạt động đúng dù cách framework chuẩn bị bean, proxy, reflection và metadata thay đổi.

Câu hỏi quan trọng là: người dùng thiếu quyền có thật sự bị chặn **trước khi** service nhạy cảm thực hiện hành động? Một biểu thức SpEL có còn tìm được method, field, custom principal và bean policy trên native? Đường gọi tới bean có thực sự đi qua security proxy? Phiên bản Spring Security/Framework có hỗ trợ annotation và runtime hint đang sử dụng? Các câu hỏi này phải được trả lời bằng test, không chỉ bằng việc executable khởi động thành công.

Sau bài học, người học cần biết:

1. Phân biệt **JVM thường, JVM dùng generated AOT code và native image**; biết điều gì được xác định ở build time.
2. Giải thích proxy-based method security, JDK interface proxy, class-based proxy và những vị trí advice không được gọi.
3. Nhận diện lỗi SpEL do parameter metadata, dynamic property access, custom principal, policy bean hoặc reflection hints thiếu.
4. Lập ma trận tương thích theo Spring Boot, Spring Framework, Spring Security, GraalVM, Native Build Tools và cấu hình build.
5. Kiểm thử cả **ALLOW, DENY, lỗi biểu thức và side effect** trên JVM/AOT/native; chỉ phát hành khi không có regression phân quyền.

Bài học thuộc nhóm **Hiệu năng và vận hành**, nên đồng thời phân tích startup, bộ nhớ, build time, latency và vận hành. Tuyệt đối không nới lỏng authorization để native compile được hoặc để cải thiện thời gian khởi động.

## 2. AOT khác native image như thế nào?

| Chế độ | Cơ chế | Điều kiểm thử xác minh |
| --- | --- | --- |
| JVM thường | Spring dựng context, tạo proxy và dùng reflection linh hoạt ở runtime | Baseline về hành vi phân quyền |
| JVM AOT | Spring dùng bean definitions/initializer/proxy assets được tạo trước, chạy trên JVM | Tác động của bean graph và proxy được xác định ở build time |
| GraalVM Native Image | GraalVM phân tích closed world và đóng thành executable theo platform | Reachability của class, method, resource, reflection, dynamic proxy; hành vi security thực |

**AOT không đồng nghĩa native.** Spring AOT có thể tạo Java source và bytecode proxy để ứng dụng chạy trên JVM hoặc để GraalVM đóng image. Native bổ sung ràng buộc về phân tích tĩnh, reflection, resource loading, serialization và các dạng proxy. Một JVM test pass không bảo đảm native pass. Một nativeCompile pass cũng không bảo đảm @PreAuthorize hoạt động trên mọi service.

Spring AOT thường sinh:

- Mã Java khởi tạo bean thay cho một phần phân tích cấu hình tại runtime.
- Bytecode proxy tạo trước khi ứng dụng chạy.
- Runtime hints cho reflection, JDK proxies, resources, serialization và JNI khi cần.

Với Gradle, các assets có thể nằm tại build/generated/aotSources, build/generated/aotClasses và build/generated/aotResources. Đường dẫn có thể khác theo bản plugin; hãy kiểm tra artifacts thực tế.

### 2.1. Ranh giới của build-time configuration

Spring AOT đánh giá nhiều điều kiện tạo bean khi build. Vì vậy, không thể mặc định đổi @Profile, @ConditionalOnProperty hoặc một điều kiện tạo SecurityFilterChain ở runtime sẽ sinh graph bean hoàn toàn mới. Cần dùng **đúng profile và các điều kiện tạo bean** cho bản native dự định phát hành. Giá trị runtime như URL hoặc credential của policy service được quản lý tách biệt với sự tồn tại của bean; không đưa secret vào artifact build để ép kích hoạt cấu hình.

Nếu production policy bean chỉ xuất hiện với profile prod nhưng native image được build theo profile khác, lỗi có thể biểu hiện bằng bean không tồn tại hoặc authorization fallback khác. Đây là lỗi cấu hình build/runtime, không phải lý do cho phép mặc định. Kiểm tra các SecurityFilterChain và method-security advisors đã được AOT phát hiện trước khi đóng image.

## 3. Method security và cơ chế proxy

Khi @EnableMethodSecurity được bật, Spring Security cung cấp các method interceptors. @PreAuthorize được xử lý **trước** lời gọi method đích; @PostAuthorize được xử lý **sau** khi method trả kết quả. Cơ chế dựa trên lời gọi qua **Spring-managed proxy**, không tự chèn authorization check vào mọi lời gọi Java.

~~~text
Controller / Bean gọi
       |
       v
Spring-managed DocumentService proxy
       |
       +--> @PreAuthorize advisor
       |       DENY => ngừng, target không được gọi
       |
       +--> DocumentService.method(...)
       |
       +--> @PostAuthorize advisor (nếu cấu hình)
       |
       v
     Kết quả
~~~

| Đặc điểm | JDK interface proxy | Class-based proxy, thường CGLIB |
| --- | --- | --- |
| Tạo proxy | Đối tượng triển khai một hay nhiều interface | Subclass của class đích |
| Điểm gọi | Caller cần làm việc qua interface được proxy | Method/class cần có khả năng override |
| Rủi ro | Cast/inject trực tiếp sang concrete class không phù hợp; method không có trong interface | final class hoặc final method không thể override; private method không được advice theo kiểu subclass |
| Với AOT/native | JDK proxy động tùy biến có thể cần proxy hint nếu AOT không suy ra | Cần proxy class được sinh/đăng ký trước |
| Test | Kiểm tra proxy và gọi qua bean/interface thực | Kiểm tra proxy, method visibility và lời gọi qua Spring bean |

Spring có khả năng chuẩn bị trước nhiều proxy chuẩn của chính framework. Không thêm reflection/proxy hints cho toàn bộ package như một cách sửa lỗi chung: cần xác định chính xác type và member thiếu.

### 3.1. Self-invocation

~~~text
bean khác -> proxy.export() -> advice -> target.export()
bean khác -> proxy.batch() -> target.batch() -> this.export()
                                                   |
                                                   +-- không quay lại proxy
~~~

Giả sử @PreAuthorize chỉ đặt trên export(), còn batch() gọi this.export(). Trong mô hình proxy thông thường, lời gọi this.export() có thể **bỏ qua advisor của export()**. Lỗ hổng này tồn tại trên cả JVM và native; đăng ký RuntimeHints không sửa được.

Ưu tiên bảo vệ cả entry point batch(), hoặc tách export() sang một Spring bean khác và gọi qua proxy do Spring quản lý. Không dựa vào tự lấy proxy từ context/self-injection nếu có thể thiết kế ranh giới service rõ ràng hơn. Test cần cố ý đi qua cả lời gọi trực tiếp từ bean khác và lời gọi nội bộ.

### 3.2. @PostAuthorize không hoàn tác side effect

@PreAuthorize từ chối trước khi method chạy; @PostAuthorize có thể từ chối **kết quả trả về** sau khi method đã gửi thông báo, xóa tài liệu hoặc thực hiện giao dịch. Không dùng riêng hậu kiểm để bảo vệ hành động ghi không thể hoàn tác. @PreFilter/@PostFilter cũng cần test hành vi thực với collection/input/output; chúng không thay thế việc kiểm tra quyền tại điểm thực thi side effect.


## 4. Biểu thức SpEL và khác biệt về runtime hints

Ví dụ trong Spring Security:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public Document getDocument(String documentId) { /* ... */ }

@PreAuthorize("@documentPolicy.mayUpdate(authentication, #documentId)")
public void updateDocument(String documentId) { /* ... */ }

@PostAuthorize("returnObject.owner == authentication.name")
public Document getOwnedDocument(String documentId) { /* ... */ }
~~~

Đây là **trích đoạn method trong Spring-managed bean**, cần @EnableMethodSecurity, bean documentPolicy và type Document tương ứng; không phải Java độc lập. Kiểm tra chủ sở hữu bằng @PostAuthorize chỉ có ý nghĩa cho đường đọc, không dùng để bảo vệ thao tác ghi có side effect.

| Cấu phần trong biểu thức | Điều phải xác minh |
| --- | --- |
| hasAuthority('DOC_READ') | Chính xác tên GrantedAuthority đã có trong Authentication |
| hasRole('ADMIN') | Quy tắc prefix ROLE_ theo cấu hình; không nhầm với hasAuthority |
| authentication, principal | Đúng Authentication/principal thực tế khi request tới Spring Security |
| #documentId | Tên method parameter được lưu hoặc khám phá đúng |
| @documentPolicy.mayUpdate(...) | Bean policy có trong context và method được SpEL resolve |
| principal.isAdmin() hoặc principal.canExport(id) | Method custom principal có thể cần reflection hints trên native |
| returnObject.owner | Property getter/field/type có thể được SpEL truy cập động |
| hasPermission(...), PermissionEvaluator | Custom evaluation handler và bean có tương thích AOT? |
| @PreFilter/@PostFilter | filterObject/returnObject, type generic, kết quả theo object |
| Annotation/API từ version mới | Có thật trong dependency hay chỉ xuất hiện ở tài liệu bản mới? |

### 4.1. Tên tham số phải rõ ràng

SpEL dùng #documentId có thể lỗi khi method parameter names không tồn tại trong bytecode hoặc interface khác implementation. Dùng Java compiler flag -parameters hoặc annotation @P của Spring Security để đặt tên rõ ràng; không mặc định JVM và native cùng suy ra tên qua debug metadata.

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("@documentPolicy.mayUpdate(authentication, #docId)")
public void update(@P("docId") String documentId) {
    // Đặt bên trong Spring bean thực
}
~~~

Trích đoạn trên cần bean documentPolicy và các dependency Spring Security. Việc đổi #docId thành null hoặc lỗi evaluation không được tự động suy diễn là cho phép. Viết test cho tên tham số, null, ID khác tenant, principal thiếu quyền và lỗi của bean policy.

### 4.2. Reflection của custom principal

Trên JVM, SpEL thường gọi method của custom UserDetails/Authentication principal qua reflection. Trên native, method không nằm trong reachability graph có thể thiếu metadata phản chiếu, dẫn đến SpelEvaluationException (ví dụ EL1004E: không tìm thấy method isAdmin() trên kiểu principal). Có **nhiều** nguyên nhân EL1004E: tên sai, principal runtime type khác, method không public, bean không tồn tại hoặc thiếu hint. Phải chứng minh trước khi thêm hint.

Nếu expression tham chiếu bean theo tên khi bean bị loại do @ConditionalOnProperty/profile ở AOT build, reflection hint không tạo lại bean bị thiếu; cần sửa cấu hình tạo bean và rebuild.


### 4.3. RuntimeHintsRegistrar cho đúng method

Giả sử dự án có class AppPrincipal với public boolean canExport(String documentId), và @PreAuthorize gọi principal.canExport(#documentId). Khi test native chứng minh SpEL thiếu khả năng invoke method này, đăng ký **đúng method**:

~~~java
import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

final class PrincipalExpressionHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader loader) {
        try {
            hints.reflection().registerMethod(
                    AppPrincipal.class.getMethod("canExport", String.class),
                    ExecutableMode.INVOKE
            );
        } catch (NoSuchMethodException exception) {
            throw new IllegalStateException(
                    "SpEL accessor is missing", exception);
        }
    }
}

@Configuration
@ImportRuntimeHints(PrincipalExpressionHints.class)
class NativeAuthorizationHintsConfiguration {
}
~~~

Đây là **mẫu tích hợp với Spring Framework**, cần AppPrincipal và phiên bản RuntimeHints API tương thích; không biên dịch độc lập bằng javac. Nếu expression truy cập getter/field khác, đăng ký đúng member. Với dữ liệu cần bind/serialize, @RegisterReflectionForBinding có thể hữu ích trong một số phiên bản, nhưng không mặc định thay thế mọi hint cho method SpEL tùy biến.

Không đăng ký nguyên package/loạt class “cho chắc”. Runtime hints giúp giữ metadata trong native image, **không thay đổi quyền**. Sau khi thêm hint, chạy lại test denied và allowed trên native executable. Test chỉ kiểm tra hints có mặt chưa chứng minh policy được áp đúng.

Nếu custom library tự tạo JDK dynamic proxy hoặc đọc file cấu hình bên ngoài classpath, có thể cần proxy/resource hints. Spring AOT thường sinh proxy của Spring AOP; chỉ thêm thủ công khi có bằng chứng. GraalVM tracing agent hỗ trợ tìm reflection/resource/proxy thiếu, nhưng metadata thu thập được phải review và lọc bỏ dữ liệu chỉ phục vụ test.

### 4.4. Phân loại nguyên nhân

- **Lỗi policy**: expression sai, role/authority không khớp, dữ liệu tenant sai -> sửa quy tắc.
- **Lỗi proxy**: this.method(), bean tạo bằng new, final/private method, inject target sai -> sửa ranh giới AOP.
- **Lỗi bean graph**: bean conditional không được AOT tạo -> sửa build profile/conditions.
- **Lỗi reachability**: method/resource/dynamic proxy thiếu metadata -> thêm đúng hint.
- **Lỗi thư viện phiên bản**: API không có, annotation thay đổi, plugin không tương thích -> dùng BOM/migration guide.

Giữ nguyên fail closed: mọi lỗi đánh giá policy không thể trở thành ALLOW. Native 500 là lỗi vận hành cần khắc phục; native 200 khi principal thiếu quyền là regression bảo mật nghiêm trọng.

## 5. Ma trận phiên bản và tài liệu đúng nhánh

| Thành phần | Cần pin/kiểm tra | Rủi ro |
| --- | --- | --- |
| JDK, GraalVM | Version, Native Image toolchain, OS/architecture | Native executable và reflection compatibility |
| Spring Boot | Major/minor/patch và Gradle/Maven plugin | AOT tasks, auto-config, buildpack, hints |
| Spring Framework | Version do Boot BOM quản lý | AOP, bean initialization, RuntimeHints API |
| Spring Security | Version do Boot BOM quản lý | AuthorizationManager, SpEL, advisors, feature có sẵn |
| Native Build Tools | Plugin version tương thích GraalVM/Boot | nativeCompile/nativeTest |
| Policy/JSON/HTTP libraries | Exact versions, reachability metadata | Serialization, TLS, dynamic proxy |
| Build profiles/conditions | Điều kiện tạo bean, feature flags | Build-time bean graph và chain đúng |
| Deployment | JVM/AOT/native cùng dữ liệu và security contract | Không hiểu sai do cấu hình khác nhau |

Với **Spring Boot 3.3.x**, thông thường Spring Framework thuộc nhánh **6.1.x** và Spring Security thuộc nhánh **6.3.x** theo dependency management của Boot. Hãy kiểm tra resolved versions của ứng dụng, đừng ghi cứng patch. Khi nâng Boot 3.4/3.5/4.x hoặc Spring Security 6.5/7.x, đọc migration guide và chạy toàn bộ test lại.

Một số cơ chế proxy return-object, @AuthorizeReturnObject và registrar/hints xuất hiện trong Spring Security phiên bản mới có thể **chưa có hoặc khác API** ở nhánh 6.3. Không copy code 6.5/7.x vào 6.3 chỉ vì trang docs mặc định ở latest. Lỗi cannot find symbol là vấn đề API/version, không giải quyết bằng reflection hint.

Kiểm tra thêm: @EnableMethodSecurity có được bật không? Spring Boot Starter Security không tự kích hoạt method-level authorization. Những annotation nào được bật (prePostEnabled, securedEnabled, jsr250Enabled)? Có nhiều SecurityFilterChain với thứ tự khác nhau không? Rule tại URL và tại method có cùng ý định bảo vệ không?

Cần tách **compile error** (sai API), **AOT generation error** (bean/proxy graph), **native-image build error** (reachability/toolchain), **native startup error** (resource/initialization) và **runtime authorization error** (SpEL/permission/proxy). Không dùng một loại hint chung để chữa mọi lỗi.



## 6. Ví dụ Java 17+ độc lập: thấy rõ self-invocation

Chương trình sau chỉ sử dụng JDK, mô phỏng JDK interface proxy. Nó cố ý cho thấy lỗi **guard chỉ bảo vệ method export** và một method khác gọi export bằng this, làm mất advisor. Đây là phản ví dụ để kiểm thử, không phải cách cấu hình Spring Method Security hoặc một native image.

Lưu thành **AuthorizationProxyDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AuthorizationProxyDemo {
    interface DocumentOperations {
        String export();
        String batchExport();
    }

    static final class DocumentService implements DocumentOperations {
        @Override
        public String export() {
            return "PRIVATE-DATA";
        }

        @Override
        public String batchExport() {
            return this.export();
        }
    }

    static DocumentOperations guarded(DocumentOperations target, boolean allowed) {
        return (DocumentOperations) Proxy.newProxyInstance(
                DocumentOperations.class.getClassLoader(),
                new Class<?>[] { DocumentOperations.class },
                (proxy, method, args) -> {
                    if (method.getName().equals("export") && !allowed) {
                        throw new SecurityException("export denied");
                    }
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        DocumentOperations service = guarded(new DocumentService(), false);

        try {
            service.export();
            throw new AssertionError("expected denial");
        } catch (SecurityException expected) {
            System.out.println("proxy.export -> DENIED");
        }

        String bypass = service.batchExport();
        if (!"PRIVATE-DATA".equals(bypass)) {
            throw new AssertionError("unexpected example result");
        }
        System.out.println("proxy.batchExport -> PRIVATE-DATA (self-invocation)");

        DocumentOperations privileged = guarded(new DocumentService(), true);
        System.out.println("privileged.export -> " + privileged.export());
    }
}
~~~

Biên dịch bằng Java 17+ và chạy:

~~~bash
javac --release 17 AuthorizationProxyDemo.java
java AuthorizationProxyDemo
~~~

Stdout chính xác:

~~~text
proxy.export -> DENIED
proxy.batchExport -> PRIVATE-DATA (self-invocation)
privileged.export -> PRIVATE-DATA
~~~

**Giải thích:** gọi service.export() đi vào handler của proxy và bị chặn khi allowed=false. Gọi service.batchExport() chỉ được intercept ở entry point batchExport; bên trong target, this.export() đi thẳng tới implementation, nên dữ liệu vẫn được trả ra. Bài học ở đây là phải bảo vệ entry point và kiểm thử ranh giới proxy. Trong ứng dụng Spring thật, hãy bảo vệ batchExport bằng policy thích hợp hoặc chuyển logic xuất tài liệu sang một bean khác để gọi qua security proxy. Không dựa vào reflection hints để vá hành vi này.

### 6.1. Phân biệt đoạn Java độc lập và ví dụ framework

Trong demo, Proxy.newProxyInstance được gọi trực tiếp. Ứng dụng Spring thường để Spring AOP quản lý proxy; với native, Spring AOT tạo nhiều proxy cần thiết từ trước. Nếu chính ứng dụng tự xây dựng dynamic JDK proxy dựa trên type được quyết định ở runtime, lúc đó mới đánh giá có cần registerJdkProxy trong RuntimeHints. Không khai báo tràn lan cho mọi interface mà không có ca kiểm thử minh chứng.

## 7. Ví dụ tích hợp Spring Security 6.x

Các đoạn sau là **mã trích từ một ứng dụng Spring Boot/Spring Security**, cần dependencies và controller/bean tương ứng; không thể chạy độc lập bằng javac như mục 6.

Cấu hình HTTP và method security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class AuthorizationConfiguration {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("DOC_READ")
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("DOC_WRITE")
                .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Method security ở service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class DocumentApplicationService {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public String read(String id) {
        return "document:" + id;
    }

    @PreAuthorize("hasAuthority('DOC_WRITE')")
    public void change(String id, String content) {
        // Ghi dữ liệu chỉ sau khi proxy đã cho phép
    }
}
~~~

Cấu hình này chỉ minh họa quyền; một ứng dụng thực còn cần authentication, CSRF/CORS, endpoint mapping và object-level authorization cho tenant/owner. HTTP matcher không đủ để bảo vệ quyền trên từng tài liệu. Những method không có annotation sẽ không tự có kiểm tra method security; rule cuối denyAll ở tầng HTTP chỉ bảo vệ request đi qua chain đó, không thay cho security ở lời gọi service từ batch/job/event consumer.

Test đúng: inject **Spring-managed DocumentApplicationService** vào controller hoặc bean khác, đăng nhập một identity chỉ có DOC_READ rồi gọi change(). Assert bị DENY **và** database/service ghi không đổi. Gọi new DocumentApplicationService() trực tiếp không có proxy và không phải phép kiểm thử @PreAuthorize. Đối với JDK proxy qua interface, inject interface phù hợp thay vì ép cast về class đích.

### 7.1. Có thể thay SpEL phức tạp bằng Java AuthorizationManager

Quyết định dựa nhiều thuộc tính tenant, resource, policy service hoặc remote timeout thường dễ kiểm thử khi logic được định kiểu trong một AuthorizationManager/bean policy. Với HTTP request, có thể dùng access(customAuthorizationManager); ở method-level, cấu hình method-security advisor/authorization manager tương ứng phiên bản. Lợi ích là tách rõ kết quả ALLOW/DENY/INVALID/UNAVAILABLE, dễ telemetry và giảm phụ thuộc truy cập property tùy biến qua reflection. Tuy vậy, **Java typed code không tự khắc phục self-invocation hoặc mất proxy**; vẫn cần test toàn bộ đường gọi.


## 8. Xây dựng và kiểm thử Gradle

Những lệnh dưới đây minh họa cho ứng dụng Spring Boot Gradle **đã áp dụng plugin GraalVM Native Build Tools phù hợp với version của Spring Boot và GraalVM**. Tên task có thể khác hoặc không tồn tại ở subproject chưa cấu hình native. Dùng Gradle Wrapper của repository và chỉ target project được hỗ trợ.

~~~bash
# JVM baseline
./gradlew test

# Xử lý Spring AOT để sinh Java/proxy/hints assets
./gradlew processAot

# Tạo GraalVM native executable (cần native-image toolchain)
./gradlew nativeCompile

# Kiểm thử native, cần native test support
./gradlew nativeTest

# Lựa chọn container image qua Docker/Buildpacks đã cấu hình
./gradlew bootBuildImage
~~~

Với Windows, thường dùng gradlew.bat; multi-project cần chỉ định Gradle project path và task (ví dụ :service:nativeCompile) phù hợp. Không giả định root project tự áp tất cả plugin. nativeCompile có thể tốn CPU/RAM và thời gian build đáng kể. bootBuildImage cần Docker daemon và builder tương thích native; không bắt buộc cài native-image trên host trong mọi cách dùng buildpacks.

**JVM AOT kiểm chứng riêng:** nếu build đã đóng gói mã AOT, tài liệu Spring Boot mô tả cách chạy JAR trên JVM với system property spring.aot.enabled=true. Chỉ bật property này trên một JAR không chứa generated AOT assets thì chưa phải phép thử AOT hợp lệ. Trước khi tin kết quả, kiểm tra artifact có Java initialization/proxy bytecode/hints do AOT sinh.

### 8.1. Ba mức QA trước khi phát hành

1. **Unit tests** cho policy bean/AuthorizationManager: input, authority, tenant, deny, invalid, timeout; không đòi native toolchain.
2. **Spring integration tests** với ApplicationContext/SecurityFilterChain: gọi qua managed bean/HTTP thật, xác minh @PreAuthorize và không có side effect. Đồng thời kiểm tra biểu thức custom principal/bean có thể resolve.
3. **Native tests**: chạy executable thật và gửi request giống production; đối chiếu dữ liệu, status, audit/metric, database state với JVM baseline. Có thể dùng nativeTest hoặc external HTTP tests nhắm tới image đã build tùy dự án.

Một test chỉ xác minh ứng dụng khởi động hoặc chỉ kiểm tra allowed path là không đủ. Phải chứng minh các đường denied; không biến một exception thành permitAll. Đối với hành động ghi, xem bản ghi DB trước/sau, hoặc verify target service không được gọi.

### 8.2. Ma trận hành vi xuyên môi trường

| Tình huống | JVM thường | JVM AOT | Native | Bằng chứng cần assert |
| --- | --- | --- | --- | --- |
| Principal có DOC_READ gọi read | ALLOW | ALLOW | ALLOW | Đúng dữ liệu/endpoint |
| Principal không có DOC_READ | DENY | DENY | DENY | Không trả dữ liệu nhạy cảm |
| Chỉ có DOC_READ gọi change | DENY | DENY | DENY | Target không chạy, DB không đổi |
| Có DOC_WRITE gọi change hợp lệ | ALLOW | ALLOW | ALLOW | Có quyền trên object/tenant |
| Sai tenant hoặc object ID | DENY | DENY | DENY | Không có IDOR/BOLA |
| Gọi từ bean khác qua proxy | Advisor chạy | Advisor chạy | Advisor chạy | Interceptor áp đúng method |
| Tự gọi nội bộ hoặc final method | Test phát hiện và sửa kiến trúc | Cùng hợp đồng | Cùng hợp đồng | Không có bypass |
| SpEL #paramName | Resolve đúng | Resolve đúng | Resolve đúng | Không null bất ngờ |
| @documentPolicy bean method | Gọi đúng bean | Gọi đúng bean | Gọi đúng bean | Không lỗi resolution |
| Custom principal method | Kết quả đúng | Kết quả đúng | Kết quả đúng | Reflection hints đủ nếu cần |
| @PostAuthorize với owner check | DENY đúng object | DENY | DENY | Không rò return value |
| Anonymous/invalid token | Không vào service | Không vào service | Không vào service | Entry point phù hợp |
| Policy exception/timeout | Không ALLOW | Không ALLOW | Không ALLOW | Fail closed, có telemetry |
| Nhiều SecurityFilterChain | Match đúng | Match đúng | Match đúng | Không lộ route khác |
| Build profile/feature flag | Bean graph đúng | Bean graph đúng | Bean graph đúng | Config dùng cùng test contract |

Mã HTTP chi tiết có thể thay đổi theo AuthenticationEntryPoint, AccessDeniedHandler hoặc cách bắt ngoại lệ; khi thiếu quyền, endpoint nhạy cảm **không được thực hiện side effect** là bất biến cơ bản. Một lỗi SpEL có thể dẫn tới 500 thay vì 403; trường hợp này vẫn cần sửa, không được coi là thành công vì chưa cấp quyền.

### 8.3. Test proxy tại Spring ApplicationContext

Với service dùng method security chuẩn, kiểm tra bean được Spring quản lý có proxy phù hợp, sau đó **phải test DENY thực**. Trích đoạn JUnit/Spring Boot, không phải file Java độc lập:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MethodSecurityProxyIT {
    @Autowired DocumentApplicationService documents;

    @Test
    void beanUsesSpringAopProxy() {
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
    }
}
~~~

Kết quả isAopProxy=true chưa chứng minh advisor chứa đúng policy. Thêm test dùng principal thiếu DOC_WRITE gọi documents.change() qua bean này, assert AccessDeniedException hoặc HTTP 403 theo bối cảnh và verify dữ liệu không đổi. Nếu setup hợp lệ dùng một cơ chế authorization không dựa trên Spring AOP proxy, đừng áp test này một cách máy móc; kiểm thử ranh giới cơ chế thực tế.

### 8.4. Kiểm thử hints

Có thể tạo RuntimeHints, gọi registrar và dùng RuntimeHintsPredicates để xác minh reflection method/resource/proxy metadata theo API của phiên bản đang dùng. Đây chỉ kiểm tra **hint registration**, cần native integration test để chứng minh SpEL và policy thật chạy thành công. Thử cả principal có/không có quyền, object khác tenant và bean policy ném lỗi.

Đối với @PostAuthorize/@PostFilter, kiểm tra property của returnObject/filterObject thật, kể cả collection có generic type; Spring Security mới hơn có thêm cơ chế proxy đối tượng trả về và hint registrars, nhưng chỉ dùng nếu dependency đã pin hỗ trợ. Không đánh đồng một annotation có tên giống nhau ở nhiều nhánh phiên bản.



## 9. Chẩn đoán sự cố trên native image

Nên điều tra theo thứ tự từ biểu hiện đến tầng bị lỗi, giữ cùng principal/request/resource khi đối chiếu:

1. **Ghi version và input:** Spring Boot/Security/Framework versions, JDK/GraalVM, build profile, authorities, object ID/tenant, URL và root exception. Tránh log token/secret.
2. **Chạy JVM baseline:** nếu JVM cũng sai, ưu tiên rule/matcher/proxy/SpEL logic; nếu chỉ native sai, tiếp tục bước AOT/reachability.
3. **Xác nhận bean và advice:** @EnableMethodSecurity có hiệu lực không? Bean có Spring proxy không? Method final/private hoặc this.method() có bỏ qua interceptor không?
4. **Kiểm tra biểu thức:** tên #parameter, @P/-parameters, actual principal type, policy bean name và property getter có đúng không?
5. **Kiểm tra AOT outputs:** generated bean registration/proxy classes và resource metadata có chứa điều cần dùng không? Profile build có loại bean không?
6. **Xác minh hints thiếu:** method/property/resource/JDK proxy nào thật sự cần reflect/dynamic access? Đăng ký đúng target rồi rebuild.
7. **Chạy lại native tests:** thử ALLOW và DENY, cả object cross-tenant và sự cố policy; xác nhận không có side effect trái phép.
8. **So sánh khi nâng version:** đối chiếu dependency lock/BOM, migration guide, công cụ native và thay đổi cấu hình mới.

| Triệu chứng | Hướng kiểm tra | Không nên làm |
| --- | --- | --- |
| EL1004E: method not found trong expression | Actual principal, tên method, reflection metadata | Mở permitAll để bỏ qua lỗi |
| 403 JVM nhưng 500 native | SpEL expression root cause, custom method/bean hint | Xem 500 là thành công vì không lộ data |
| 200 khi thiếu quyền | Proxy bị bypass, rule rộng, annotation không active, fail-open logic | Đổ lỗi cho GraalVM mà không xem advisor |
| Bean cast lỗi sau khi proxy | JDK interface proxy vs concrete class injection | Ép cast implementation |
| nativeCompile thất bại ở proxy | Dynamic proxy do ai tạo, hints hiện có, version plugin | Thêm hints cho toàn package |
| Resource policy template không tồn tại | Resource có được đóng gói/hint đúng không? | Giả định local file system của JVM còn nguyên |
| Build native với profile A nhưng chạy B | Build-time bean graph cố định | Chờ @ConditionalOnProperty tạo bean mới ở runtime |
| Self-invocation không bị chặn | Entry point và lời gọi this.method() | Trông chờ AOT tự sửa logic Spring AOP |

### 9.1. Phân biệt độ tin cậy và hiệu năng

Ghi các metric tối thiểu: số lượng authorization granted/denied, số SpEL/reflective errors, thời gian đánh giá policy, timeout, failure của policy adapter, và latency của endpoint được bảo vệ. Nếu có cache quyền, key phải có đủ principal, action, resource, tenant, policy-version/TTL theo hợp đồng; không tái sử dụng ALLOW cũ vô hạn khi PDP lỗi.

Native image có thể giảm thời gian startup/bộ nhớ trong một số workload, nhưng compile lâu hơn, throughput/JIT và kích thước artifact có trade-off. Đo trên cùng workload, cùng CPU/RAM, cùng Spring Security policy và HTTP client. **Không được tắt Spring Security advisors hay giảm số kiểm tra quyền để đạt benchmark đẹp hơn.** Nếu policy service từ xa chiếm phần lớn latency, native startup nhanh không làm mất chi phí network request.

## 10. Checklist phát hành

Một bản phát hành AOT/native đủ tin cậy phải có bằng chứng:

- Versions của Boot/Framework/Security/Native Build Tools/GraalVM/JDK đã khóa; đường build/profiles tái tạo được.
- SecurityFilterChain và policy beans có trong generated AOT graph; không dựa vào bean được tạo mới ngầm ở runtime.
- Method security thật sự active; method nhạy cảm được gọi qua proxy; không còn self-invocation/final/private bypass chưa xử lý.
- Custom principal, expression, policy bean, DTO, resource và dynamic proxy được kiểm chứng đúng hint nếu có.
- JVM, JVM AOT và native cho cùng quyết định ALLOW/DENY khi principal/action/resource tương đương.
- Test denied xác nhận không có ghi dữ liệu, không có lộ return value; test allowed xác nhận nghiệp vụ vẫn chạy.
- Policy timeout, malformed response, missing reflection method hay exception không bao giờ trở thành ALLOW.
- Hệ thống có log/metric đúng loại lỗi, không log token/credential, và có kế hoạch rollback artifact.
- Các chỉ số startup, RAM, build time, throughput, latency có số đo thực; tối ưu chỉ được chấp nhận khi authorization vẫn đúng.

**Tiêu chí cuối cùng:** AOT/native thay đổi cách ứng dụng được đóng gói, khởi tạo và giữ metadata. Nó **không được** thay đổi ai có quyền đọc, sửa hay xóa tài nguyên. Mọi thay đổi version/build mode đều phải giữ bất biến này.

## 11. Nguồn tham khảo chính thức

Các liên kết sau dùng để đối chiếu phiên bản framework trước khi áp dụng cấu hình hoặc API:

- [Spring Boot 3.3 — Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html): tracing agent, RuntimeHints, resource/proxy configuration, hạn chế native.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed world, AOT Java source, hints và proxy bytecode.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): AOT engine, RuntimeHints API.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity, @PreAuthorize, @PostAuthorize, proxy, SpEL.
- [Spring Security — Method Security in GraalVM Native Image](https://docs.spring.io/spring-security/reference/native-image/method-security.html): custom UserDetails/Authentication reflection và hints; trang hiện hành có thể khác nhánh 6.3, cần chọn đúng version trước khi dùng API.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): AuthorizationManager và HTTP rules.

