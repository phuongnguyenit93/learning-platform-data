# JDK proxy, CGLIB và ảnh hưởng của interface, final, private

> **Chủ đề:** Spring Security – authorization → **Proxy và giao dịch**. Khi dùng `@PreAuthorize`, `@PostAuthorize` hoặc `@Transactional`, hiểu kiểu proxy và đường đi của lời gọi quan trọng không kém nội dung annotation. Bài viết sử dụng Java 17+, Spring Boot 3.x và Spring Security 6.x làm nền tảng cho ví dụ có thể chạy.

## 1. Điều cần hiểu trước: Spring bảo vệ lời gọi thông qua proxy

Với Method Security ở chế độ Spring AOP mặc định, Spring thường cung cấp cho caller một **proxy** bọc bean nghiệp vụ:

~~~text
Bean khác / Controller
         |
         | gọi method trên đối tượng lấy từ Spring Context
         v
     [AOP proxy] -------> Security advice (ví dụ @PreAuthorize)
         |               Transaction advice (nếu có @Transactional)
         |               Các advice khác
         v
   [Target service]
         |
         v
     Trả kết quả
~~~

Proxy là đối tượng trung gian có thể chạy kiểm tra quyền trước khi gọi target; nếu `@PreAuthorize` trả false, phương thức không được phép chạy và thông thường Spring Security ném `AccessDeniedException`. Transaction interceptor cũng làm việc quanh lời gọi qua proxy: mở/tham gia giao dịch, commit hoặc rollback tùy quy tắc.

Vì cơ chế **theo lời gọi qua proxy**, tồn tại khác biệt rất lớn giữa:

~~~text
otherBean.securedService.approve()  -> proxy -> advice -> target.approve()

this.approve() bên trong target   -------------> target.approve()
                                                    (không đi qua proxy)
~~~

Nếu phương thức đang chạy tự gọi method khác của chính đối tượng bằng `this`, advice riêng của method bên trong **không chạy ở lượt gọi đó**, dù method được gắn annotation. Điều này đúng với cả JDK proxy lẫn CGLIB và ảnh hưởng đồng thời tới Method Security và `@Transactional`.

## 2. Hai dạng proxy: JDK dynamic proxy và CGLIB

### 2.1. JDK dynamic proxy

JDK tạo proxy **triển khai interface**, không kế thừa lớp target. Ví dụ:

~~~java
public interface ReportReader {
    String read();
}

public class ReportReaderImpl implements ReportReader {
    @Override
    public String read() {
        return "report";
    }
}
~~~

Khi bean được proxy kiểu JDK, caller nhận một đối tượng triển khai `ReportReader`, có thể gọi `read()` qua interface. Nhưng proxy **không phải** `ReportReaderImpl`; ép kiểu proxy về implementation sẽ thất bại. Các public method chỉ có ở implementation mà không xuất hiện trong interface được proxy cũng không phải API caller có thể gọi qua JDK proxy.

~~~text
        ReportReader (interface)
           ^            ^
           | implements | implements
ReportReaderImpl     JDK proxy
   (target)           |
                      | advice rồi chuyển tiếp đến target
                      v
               ReportReaderImpl
~~~

Đặc điểm quan trọng: JDK proxy chặn được lời gọi theo **phương thức interface** ngay cả khi lớp target hoặc phương thức triển khai được khai báo `final`; nó không cần tạo subclass của target. Điều này chỉ áp dụng cho cuộc gọi thực sự đi qua interface của proxy.

### 2.2. CGLIB proxy

CGLIB tạo một **subclass** sinh ở runtime, override các phương thức của target có thể override:

~~~text
ReportReaderImpl
       ^
       | extends
ReportReaderImpl$$SpringCGLIB$$...
       |
       +--- intercept -> target behavior
~~~

Vì dựa vào kế thừa:

- Lớp `final` không thể được CGLIB subclass.
- Method `final` không thể được override nên không thể gắn advice vào lời gọi method đó.
- Method `private` không thể được override; cũng không thể là điểm chặn proxy.
- Method không có đủ visibility cho subclass cũng có thể không được advice.
- Self-invocation (`this.method()`) vẫn bỏ qua proxy.

CGLIB đã được tích hợp vào `spring-core`; không cần tự thêm một thư viện `cglib` riêng trong ứng dụng Spring thông thường. Vấn đề lựa chọn proxy là **khả năng intercept và kiểu đối tượng**, không phải một cuộc đua hiệu năng giữa JDK và CGLIB.

### 2.3. Bảng đối chiếu

| Tiêu chí | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| Proxy tạo ra là | Đối tượng triển khai interface | Lớp con của target |
| Điều kiện chọn thông thường | Bean có interface, không ép class proxy | Bean không có interface hoặc cấu hình ép class proxy |
| Có thể inject theo interface | Có | Có nếu target triển khai interface |
| Có thể inject theo class target | Không | Có, khi tạo subclass được |
| Method public không khai báo trong interface | Không được công bố qua JDK proxy | Có thể advice khi override được |
| Class target `final` | Vẫn có thể proxy qua interface | Không thể tạo subclass |
| Method target `final` | Có thể intercept lời gọi trên interface | Không thể override/advice |
| Method `private` | Không thuộc interface proxy | Không thể override/advice |
| `this.other()` nội bộ | Bỏ qua advice của `other` | Bỏ qua advice của `other` |
| Dùng cho Method Security | Có | Có |
| Dùng cho `@Transactional` | Có | Có |

**Không suy đoán kiểu proxy chỉ từ class:** một bean triển khai interface vẫn có thể được CGLIB proxy nếu Spring Boot/cấu hình AOP đang ép kiểu class.

## 3. Interface tác động thế nào tới bảo mật?

Một service có hợp đồng public:

~~~java
public interface PaymentActions {
    void approve(long paymentId);
}
~~~

Implementation:

~~~java
@Service
public class PaymentActionsImpl implements PaymentActions {
    @Override
    @PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
    public void approve(long paymentId) {
        // Business logic, sau khi được cấp quyền.
    }
}
~~~

Đây là hai mảnh minh họa cần đặt trong các tệp và import tương ứng; chưa phải ứng dụng độc lập.

Nếu caller inject `PaymentActions`, cả JDK và CGLIB có thể đáp ứng hợp đồng đó. Nếu caller inject `PaymentActionsImpl`, JDK proxy thường làm phát sinh lỗi cấu hình hoặc lỗi gán kiểu bởi proxy chỉ triển khai interface. Bởi vậy, **inject theo interface** là hướng thực tế nếu service có giao diện nghiệp vụ rõ.

Spring Security Method Security có thể tìm security annotation trên method, class và cây kiểu (bao gồm interface) khi dùng Spring AOP. Tuy nhiên, nên đặt quy tắc quyền có chủ đích tại điểm vào service, tránh các interface thừa kế đặt annotation xung đột lên cùng chữ ký, và viết test tích hợp cho cả đường cho phép lẫn bị từ chối.

Đặc biệt, `@Transactional` có quy tắc khác ở chế độ **AspectJ weaving**: Java không kế thừa annotation trên interface theo cách AspectJ cần, nên Spring Framework khuyên đặt `@Transactional` ở lớp/method triển khai cụ thể. Đừng tự coi annotation trên interface hoạt động giống nhau trong mọi cơ chế AOP.

### Method không nằm trong interface có được bảo vệ không?

Với JDK proxy, một method chỉ có trên implementation không thuộc tập phương thức mà caller có thể gọi từ proxy interface thông thường. CGLIB proxy có thể expose method này, miễn có thể override và truy cập được. Vì vậy, nếu đó là một hành động nhạy cảm, phải thiết kế hợp đồng public có chủ đích và gắn authorization; không dựa vào việc một kiểu proxy tình cờ che method để thay thế kiểm tra quyền.

## 4. Final class, final method, private và static: hệ quả riêng

### 4.1. Class final với interface vẫn có đường JDK proxy

~~~java
public interface InventoryLookup {
    String view();
}

public final class FinalInventoryLookup implements InventoryLookup {
    @Override
    public String view() {
        return "stock";
    }
}
~~~

Vì JDK proxy chỉ triển khai `InventoryLookup`, lớp `FinalInventoryLookup` có thể là final mà proxy vẫn được tạo. Nếu cấu hình ép CGLIB, Spring không thể tạo subclass của lớp này; thường sẽ gặp lỗi khi khởi tạo proxy thay vì có một lớp con làm việc đúng.

### 4.2. Final method: JDK có thể chặn, CGLIB không thể

~~~java
public class InventoryLookupImpl implements InventoryLookup {
    @Override
    public final String view() {
        return "stock";
    }
}
~~~

JDK proxy có thể chặn lời gọi `InventoryLookup.view()` rồi chuyển đến final implementation. CGLIB không override được `view()`, nên việc đặt `@PreAuthorize` hoặc `@Transactional` trên method này **không bảo đảm được advice khi dùng class proxy**.

Phân biệt rõ:
- **Final class** chặn khả năng CGLIB tạo subclass.
- **Final method** khiến CGLIB không intercept được riêng method đó, dù lớp không final.
- **JDK proxy** không gặp giới hạn subclass này đối với lời gọi interface, nhưng vẫn phải có đúng annotation/advisor và người gọi thực sự sử dụng proxy.

### 4.3. Private method không phải ranh giới security

Ví dụ nguy hiểm:

~~~java
// Minh họa lỗi thiết kế; không đặt trong ứng dụng mẫu.
@Service
public class DocumentService {
    public String getDocument() {
        return internalRead();
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    private String internalRead() {
        return "sensitive";
    }
}
~~~

`getDocument()` là điểm vào public chưa có chốt. Annotation trên `internalRead()` không thể được proxy advice vì method private không override/không có interface join point. Một lời gọi tới `getDocument()` có thể đi thẳng vào logic nhạy cảm.

Thiết kế đúng là đặt chốt trên method public mà bean khác gọi qua proxy:

~~~java
@Service
public class DocumentService {
    @PreAuthorize("hasAuthority('DOC_READ')")
    public String getDocument() {
        return loadFromRepository();
    }

    private String loadFromRepository() {
        return "sensitive";
    }
}
~~~

Ở đây private helper là hợp lệ vì caller đã đi qua chốt của `getDocument()`. Private method chỉ nên là chi tiết triển khai, không dùng annotation trên private helper như một điểm chặn độc lập.

### 4.4. Protected và package-private: cẩn thận theo từng loại advice

Không có một quy tắc duy nhất cho mọi annotation AOP. Spring Framework từ **6.0** cho phép `@Transactional` trên method `protected` hoặc package-visible với **class-based proxy** trong cấu hình mặc định; JDK interface proxy yêu cầu transactional method public và có trên interface. Nhưng điều đó **không tự chứng minh** rằng mọi method `@PreAuthorize` không public đều được xử lý giống transaction advice.

Trong service có yêu cầu phân quyền, chọn một public method không final làm ranh giới bảo vệ, gọi từ bean khác và kiểm chứng bằng test. Đừng đặt một method protected/package-private làm cổng duy nhất rồi suy luận từ một tính năng AOP khác.

### 4.5. Static method và constructor

Static method thuộc lớp, không phải lời gọi instance method qua một Spring bean proxy; constructor chạy khi tạo đối tượng trước khi proxy có thể được sử dụng như một bean hoàn chỉnh. Các annotation Method Security hoặc transaction trên static method/constructor không trở thành chốt quyền qua proxy theo cách gọi service thông thường. Với `@PostConstruct` cũng không nên dựa vào lời gọi nội bộ tới method có annotation vì proxy chưa ở trạng thái sử dụng như caller bên ngoài.

### 4.6. Kotlin và record

Kotlin khai báo class/method là final theo mặc định; khi dùng class-based proxy, thường cần cơ chế `kotlin-spring`/`all-open` để mở các kiểu Spring bean thích hợp. Java record cũng là final class nên không thể tạo CGLIB subclass theo cách thông thường. Record thường phù hợp làm DTO/model, không nên tự biến thành Spring service cần class proxy.

## 5. Self-invocation: điểm mù dù đã chọn đúng proxy type

Xét code:

~~~java
// Minh họa lỗi: external() chưa bảo vệ, protectedRead() tự được gọi qua this.
@Service
public class UnsafeDocumentService {
    public String external() {
        return this.protectedRead();
    }

    @PreAuthorize("denyAll()")
    public String protectedRead() {
        return "secret";
    }
}
~~~

Lời gọi `springBean.protectedRead()` từ bên ngoài đi qua proxy, nên bị `denyAll()` chặn. Nhưng `springBean.external()` đi qua proxy đến target, sau đó `this.protectedRead()` chạy trực tiếp trong target mà không qua proxy; chốt riêng của `protectedRead()` **bị bỏ qua**. Thay JDK bằng CGLIB không tự sửa được vấn đề này.

### Sửa bằng cách tách bean và điểm vào

~~~java
// Minh họa một thiết kế đúng hướng; cần import/package như các ví dụ Spring khác.
@Service
public class ProtectedReader {
    @PreAuthorize("hasAuthority('DOC_READ')")
    public String read() {
        return "secret";
    }
}

@Service
public class DocumentFacade {
    private final ProtectedReader reader;

    public DocumentFacade(ProtectedReader reader) {
        this.reader = reader;
    }

    public String view() {
        return reader.read(); // lời gọi qua bean khác: có proxy
    }
}
~~~

Nguyên tắc là đưa hành động cần chốt riêng thành public method của **một bean khác**; Spring inject proxy của bean đó vào facade. Tránh dùng self-injection hoặc `AopContext.currentProxy()` làm lựa chọn mặc định vì chúng tạo kết dính với AOP, phức tạp hóa vòng đời bean và khó bảo trì.

### Self-invocation và `@Transactional`

~~~java
// Minh họa, giả sử ứng dụng có PlatformTransactionManager phù hợp.
@Service
public class OrderWorkflow {
    public void process() {
        this.saveInNewTransaction();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveInNewTransaction() {
        // Ghi dữ liệu.
    }
}
~~~

Khi gọi `process()` từ bên ngoài, `saveInNewTransaction()` không đi qua transaction proxy, nên **quy tắc REQUIRES_NEW của method đó không được kích hoạt ở lần gọi nội bộ**. Nếu outer caller đã mở một transaction, code bên trong vẫn có thể chạy trong transaction hiện có; không phải mọi trường hợp đều “không có transaction”. Nếu cần transaction riêng, chuyển thao tác sang bean có public method không final rồi gọi qua proxy, hoặc dùng `TransactionTemplate` khi cần điều khiển chương trình.

## 6. Spring Boot chọn proxy nào?

Spring Framework AOP thông thường chọn JDK dynamic proxy khi bean có interface; nếu không có interface, dùng CGLIB. Spring Boot **AOP auto-configuration** thường bật class-based proxy mặc định. Có thể đặt property:

~~~properties
# Ưu tiên JDK dynamic proxy khi có interface
spring.aop.proxy-target-class=false
~~~

~~~properties
# Class-based proxy / CGLIB
spring.aop.proxy-target-class=true
~~~

Để dùng Spring Security ở cấp phương thức:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`spring-boot-starter-security` không tự động bật Method Security; cần `@EnableMethodSecurity` (hoặc cấu hình XML tương đương). Ngoài ra `@EnableMethodSecurity(proxyTargetClass = true)` có thể ép class proxy. `@EnableAspectJAutoProxy`, `@EnableTransactionManagement` hay auto-proxy creator khác cũng có thể tác động lựa chọn này. Spring có thể hợp nhất nhiều cấu hình proxy, nên một property riêng không đủ để đoán mọi trường hợp.

**Chẩn đoán trên bean thực:**

~~~java
// Khi biến service đã là Spring-managed bean:
AopUtils.isAopProxy(service);
AopUtils.isJdkDynamicProxy(service);
AopUtils.isCglibProxy(service);
~~~

Import: `org.springframework.aop.support.AopUtils`. Các lời gọi trên giúp quan sát **loại proxy** nhưng chưa đảm bảo phương thức nhạy cảm đã được chặn; phải có test người không có quyền bị từ chối.

## 7. Ví dụ chạy được: Spring Boot, Method Security và hai kiểu proxy

Các tệp dưới đây thuộc project Gradle Spring Boot đã cấu hình plugin `org.springframework.boot`/`java`, Java 17+ và JUnit 5. Mọi file Java đặt trong package `demo.proxysec`. `spring-boot-starter-aop` được thêm để minh bạch việc cấu hình proxy class/interface trong demo.

### 7.1. Build dependencies

Trong `build.gradle` hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Cấu hình ứng dụng

**`src/main/java/demo/proxysec/ProxySecurityApplication.java`**

~~~java
package demo.proxysec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class ProxySecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxySecurityApplication.class, args);
    }
}
~~~

**`src/main/java/demo/proxysec/ReportReader.java`**

~~~java
package demo.proxysec;

public interface ReportReader {
    String read();
}
~~~

**`src/main/java/demo/proxysec/ReportReaderService.java`**

~~~java
package demo.proxysec;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportReaderService implements ReportReader {
    @Override
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String read() {
        return "report-42";
    }
}
~~~

Phương thức `read` public, không final và có trong interface; đó là điểm vào phù hợp để thử cả hai kiểu proxy.

### 7.3. Test JDK proxy

**`src/test/java/demo/proxysec/JdkMethodSecurityTest.java`**

~~~java
package demo.proxysec;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ProxySecurityApplication.class,
    properties = "spring.aop.proxy-target-class=false")
class JdkMethodSecurityTest {
    @Autowired
    private ReportReader reader;

    @Test
    void isJdkProxy() {
        assertTrue(AopUtils.isJdkDynamicProxy(reader));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void allowed() {
        assertEquals("report-42", reader.read());
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void denied() {
        assertThrows(AccessDeniedException.class, reader::read);
    }
}
~~~

### 7.4. Test CGLIB proxy

**`src/test/java/demo/proxysec/CglibMethodSecurityTest.java`**

~~~java
package demo.proxysec;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ProxySecurityApplication.class,
    properties = "spring.aop.proxy-target-class=true")
class CglibMethodSecurityTest {
    @Autowired
    private ReportReaderService reader;

    @Test
    void isCglibProxy() {
        assertTrue(AopUtils.isCglibProxy(reader));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void allowed() {
        assertEquals("report-42", reader.read());
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void denied() {
        assertThrows(AccessDeniedException.class, reader::read);
    }
}
~~~

Ở JDK test, bean được inject theo interface; CGLIB test cố ý inject theo concrete class. Hai class test chạy ở các Spring Context có property khác nhau. Nếu project thật có cấu hình khác ép proxy type, assertion `isJdkProxy`/`isCglibProxy` sẽ báo bất đồng, cho phép chẩn đoán thay vì âm thầm tin rằng cấu hình đã áp dụng.

### 7.5. Test cơ chế: final, private và self-invocation

Để quan sát bản chất AOP tách khỏi Spring Security, ta dùng `ProxyFactory` và một `MethodInterceptor` đếm số lần nó **thực sự nhìn thấy lời gọi**. Đây là bài test cấp proxy: nó không tự cấp hoặc từ chối quyền, nhưng lý giải vì sao advice bảo mật hoặc transaction không thể chạy khi proxy không intercept method.

**`src/test/java/demo/proxysec/ProxyMechanismTest.java`**

~~~java
package demo.proxysec;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.aopalliance.intercept.MethodInterceptor;
import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProxyMechanismTest {
    public interface Reader {
        String read();
    }

    public static class FinalMethodReader implements Reader {
        @Override
        public final String read() {
            return "secret";
        }
    }

    public static class PrivateHelperReader {
        public String entry() {
            return loadPrivate();
        }

        private String loadPrivate() {
            return "private-result";
        }
    }

    public static class SelfCallingReader {
        public String entry() {
            return this.securedRead();
        }

        public String securedRead() {
            return "self-result";
        }
    }

    @Test
    void jdkInterceptsInterfaceCallEvenWhenTargetMethodIsFinal() {
        AtomicInteger hits = new AtomicInteger();
        ProxyFactory factory = new ProxyFactory(new FinalMethodReader());
        factory.setInterfaces(Reader.class);
        factory.setProxyTargetClass(false);
        factory.addAdvice((MethodInterceptor) invocation -> {
            if (invocation.getMethod().getName().equals("read")) {
                hits.incrementAndGet();
            }
            return invocation.proceed();
        });

        Reader proxy = (Reader) factory.getProxy();

        assertTrue(AopUtils.isJdkDynamicProxy(proxy));
        assertEquals("secret", proxy.read());
        assertEquals(1, hits.get());
    }

    @Test
    void cglibCannotAdviseFinalMethod() {
        AtomicInteger hits = new AtomicInteger();
        ProxyFactory factory = new ProxyFactory(new FinalMethodReader());
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> {
            if (invocation.getMethod().getName().equals("read")) {
                hits.incrementAndGet();
            }
            return invocation.proceed();
        });

        FinalMethodReader proxy = (FinalMethodReader) factory.getProxy();

        assertTrue(AopUtils.isCglibProxy(proxy));
        assertEquals("secret", proxy.read());
        assertEquals(0, hits.get());
    }

    @Test
    void privateHelperCannotBeInterceptedSeparately() {
        List<String> seen = new ArrayList<>();
        ProxyFactory factory = new ProxyFactory(new PrivateHelperReader());
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> {
            seen.add(invocation.getMethod().getName());
            return invocation.proceed();
        });

        PrivateHelperReader proxy = (PrivateHelperReader) factory.getProxy();

        assertEquals("private-result", proxy.entry());
        assertEquals(List.of("entry"), seen);
    }

    @Test
    void selfCallBypassesInnerMethodAdvice() {
        AtomicInteger innerHits = new AtomicInteger();
        ProxyFactory factory = new ProxyFactory(new SelfCallingReader());
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> {
            if (invocation.getMethod().getName().equals("securedRead")) {
                innerHits.incrementAndGet();
            }
            return invocation.proceed();
        });

        SelfCallingReader proxy = (SelfCallingReader) factory.getProxy();

        assertEquals("self-result", proxy.entry());
        assertEquals(0, innerHits.get());
        assertEquals("self-result", proxy.securedRead());
        assertEquals(1, innerHits.get());
    }
}
~~~

Kết quả mong đợi: JDK proxy gọi `Reader.read()` đến target có method final nhưng interceptor vẫn đếm 1; CGLIB proxy gọi cùng method final và interceptor đếm 0; private helper không được intercept riêng; self-invocation không kích hoạt advice của inner method, còn lời gọi trực tiếp qua proxy thì có.

CGLIB có thể ghi log cảnh báo khi phát hiện final method. **Cảnh báo log không phải biện pháp kiểm soát quyền**; chỉ test hành vi thực tế giúp phát hiện lỗ hổng.

### 7.6. Chạy test

Trong thư mục dự án Gradle:

~~~text
./gradlew test --tests 'demo.proxysec.*'
~~~

Trên Windows:

~~~text
gradlew.bat test --tests "demo.proxysec.*"
~~~

Ví dụ không in `System.out.println` nên không có stdout nghiệp vụ đặc biệt. Kết quả mong đợi: mọi assertion của ba nhóm test đều thành công và tác vụ Gradle `test` hoàn thành. Nếu test `isJdkProxy` thất bại, hãy xem lại cấu hình proxy chung của application context trước khi kết luận Method Security sai.

## 8. Kết hợp proxy bảo mật và proxy giao dịch

Khi method vừa có `@PreAuthorize` vừa có `@Transactional`:

~~~java
// Minh họa: giả định repository/transaction manager đã có.
@Service
public class ApprovalService {
    @PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
    @Transactional
    public void approve(long paymentId) {
        // Đọc trạng thái và ghi cập nhật.
    }
}
~~~

Cả hai advisor có thể nằm trong chuỗi xử lý của cùng lời gọi, nhưng **chỉ khi lời gọi thực sự đi qua proxy và method có thể được advice**. Vì vậy:

- Method `final` + CGLIB có thể làm mất cả kiểm tra quyền lẫn transaction advice của riêng method.
- Method `private` không trở thành transactional/secured chỉ vì có annotation.
- `this.approve()` bỏ qua cả hai advice gắn với method được gọi nội bộ.
- Public interface method qua JDK proxy có thể được advice ngay cả khi method triển khai final, nhưng nên tránh cố ý dựa vào final với proxy type dễ thay đổi.
- `@Transactional` trên method protected/package-visible của Spring Framework 6+ có thể hoạt động với class proxy, không có nghĩa đây là thiết kế an toàn cho public Method Security boundary.

### Advisor order và thời điểm transaction

Theo cấu hình thường gặp, advisor `@PreAuthorize` có order trước transaction advisor mặc định `Ordered.LOWEST_PRECEDENCE`. Điều đó có nghĩa kiểm tra quyền có thể chạy **trước khi transaction của service được mở**. Nếu policy gọi JPA lazy relation và nghĩ transaction đã bắt đầu, nó có thể thất bại. Tuy nhiên, Spring có thể thay đổi advisor order theo cấu hình, nên cần kiểm tra phiên bản và chain thực tế.

Dù đang có transaction, `@PreAuthorize` vẫn chỉ kiểm tra ở **thời điểm gọi**. Với cập nhật nhạy cảm, phải bảo vệ điều kiện owner/tenant/trạng thái ở truy vấn/transaction phù hợp để tránh khoảng cách giữa kiểm tra và ghi. `@PostAuthorize` chạy sau thân method và không phải chốt duy nhất cho hành động có tác dụng phụ.

## 9. Những nhầm lẫn dễ tạo lỗi bảo mật

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `@PreAuthorize` hiện trên code nhưng không chặn | Không bật Method Security, method không đi qua proxy, final/private | Bật `@EnableMethodSecurity`, test qua Spring bean, đổi điểm chặn |
| Service có interface nhưng bean lại CGLIB | Spring Boot AOP mặc định hoặc cấu hình khác ép class proxy | Dùng `AopUtils` và kiểm tra cấu hình chung |
| Inject implementation được ở máy này nhưng lỗi ở máy khác | Cấu hình đổi CGLIB sang JDK proxy | Inject qua interface |
| CGLIB báo không proxy được final class | Lớp target final nên không subclass được | Đổi service thành non-final hoặc dùng JDK qua interface |
| Không bị chặn trên final method | CGLIB không override được | Đặt authorization trên public non-final method |
| Private method `@Transactional` không rollback như mong đợi | Private method không được proxy advice | Chuyển boundary sang public method/bean khác |
| `this.save()` không kích hoạt `REQUIRES_NEW` | Self-invocation bypass | Gọi qua bean khác hoặc dùng `TransactionTemplate` |
| `@Transactional` ở interface biến mất sau khi đổi AspectJ | Annotation của interface không được Java kế thừa cho weaving | Gắn annotation vào concrete class/method |
| Test `isAopProxy` xanh nhưng vẫn lộ dữ liệu | Có proxy nhưng advisor không match đúng method | Test thật với người thiếu authority |
| `@PostAuthorize` từ chối sau khi ghi dữ liệu | Hậu kiểm chạy sau thân method | Kiểm tra trước cập nhật và kiểm soát transaction |
| Phương thức chỉ có trong implementation không gọi được | JDK proxy chỉ công bố interface method | Đặt hành động cần gọi vào interface thích hợp |
| Kotlin service final bị lỗi khi CGLIB proxy | Kotlin mặc định final | Kiểm tra `kotlin-spring`/`all-open` hoặc dùng interface phù hợp |

Một số phương thức trong ví dụ phục vụ việc minh họa cơ chế proxy, còn ứng dụng thực tế có thể bổ sung AOT, module system, nhiều advisor, reactive security hoặc AspectJ weaving. Không suy luận rằng hành vi AOP proxy của một Spring Boot servlet service đồng nhất với mọi cơ chế đó.

## 10. Cách kiểm thử bảo mật ở ranh giới proxy

Test chỉ gọi `new SomeService()` không đủ để xác minh annotation vì đối tượng đó không có Spring proxy. Test proxy type bằng `AopUtils` chỉ là bước chẩn đoán; cần test cả **quyền được phép** lẫn **quyền bị từ chối**.

Bộ kiểm tra thực tế:

1. Gọi bean được inject từ Spring Context qua đường mà controller/service ngoài sẽ gọi.
2. Dùng `@WithMockUser(authorities = "...")` cho test được phép và một authority khác cho test bị chặn.
3. Xác minh người thiếu quyền nhận `AccessDeniedException` trước khi thao tác ghi dữ liệu xảy ra.
4. Kiểm thử riêng method được gọi từ bean khác, qua interface và qua self-invocation.
5. Khi đổi `spring.aop.proxy-target-class`, chạy lại cùng các test bảo mật; test kiểu proxy không thay thế test kết quả quyền.
6. Với transaction, kiểm tra dữ liệu sau lỗi và propagation; không chỉ kiểm tra `@Transactional` có mặt trên mã nguồn.

## 11. Bài tập thực hành

**Bài 1 – Interface và final.** Dùng `ProxyMechanismTest` để giải thích vì sao JDK có thể intercept lời gọi interface tới final method, còn CGLIB thì không. Thử đổi cả class sang final và quan sát sự khác nhau giữa hai cơ chế.

**Bài 2 – Phương thức ngoài interface.** Thêm public method `exportAll()` vào `ReportReaderService` nhưng không khai báo trong `ReportReader`. Quan sát khả năng gọi từ bean có JDK proxy và CGLIB. Nếu đây là hành động nhạy cảm, sửa thiết kế để có public contract và chốt quyền rõ.

**Bài 3 – Self-invocation.** Trong một service, để `handle()` gọi `this.restricted()` trong khi `restricted()` có `@PreAuthorize("denyAll()")`. Viết test chứng minh lời gọi trực tiếp `restricted()` qua proxy bị từ chối nhưng lời gọi nội bộ bỏ qua chốt. Tách `restricted` sang bean khác, xác minh cả đường facade bị chặn.

**Bài 4 – Transaction.** Thử một method public non-final có `@Transactional(propagation = REQUIRES_NEW)`. So sánh gọi qua bean khác và `this.method()`, rồi kiểm chứng transaction bằng thay đổi dữ liệu sau commit/rollback.

**Bài 5 – Checklist nâng cấp.** Với phiên bản Boot/Spring Framework/Security đang dùng, ghi lại proxy type, method signatures cần bảo vệ, tính final/private, đường caller và kết quả test từ chối. Khi thay đổi dependency hoặc proxy property, chạy lại test để bảo đảm ranh giới không bị thay đổi âm thầm.

**Tiêu chí hoàn thành:** phân biệt interface proxy với class proxy, hiểu class final khác method final, xác định được method private/static không có proxy join point, giải thích self-invocation ảnh hưởng đồng thời tới `@PreAuthorize` và `@Transactional`, và chứng minh hành vi bằng integration test.

## Tài liệu tham khảo chính

- Spring Framework – **Proxying Mechanisms** (JDK/CGLIB, final, private, self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework – **AOP Proxies**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Boot – **Aspect-Oriented Programming** (`spring.aop.proxy-target-class`): https://docs.spring.io/spring-boot/reference/features/aop.html
- Spring Security – **Method Security** (`@EnableMethodSecurity`, security interceptors): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework – **Using @Transactional** (visibility, interface annotation, self-invocation và AspectJ): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
