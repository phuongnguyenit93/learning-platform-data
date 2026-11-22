# @ConditionalOnJndi và điều kiện hạ tầng tra cứu JNDI trong Spring Boot

## 1. Mục tiêu bài học

Trong Spring Boot Auto-configuration, không phải bean nào cũng nên được đăng ký ở mọi môi trường triển khai. Một ứng dụng chạy trên **application server** có thể sử dụng tài nguyên do máy chủ đưa vào **JNDI** như `DataSource`, tài nguyên tích hợp hoặc thông số môi trường. Cùng ứng dụng đó khi chạy bằng một JVM độc lập có thể **không có dịch vụ đặt tên JNDI tương ứng**.

`@ConditionalOnJndi` thuộc gói `org.springframework.boot.autoconfigure.condition` dùng để **chỉ kích hoạt một cấu hình hoặc bean khi JNDI sẵn dùng**, và tùy chọn kiểm tra một hay nhiều vị trí JNDI cụ thể.

Sau bài này, người học cần phân biệt được:
- Có hạ tầng `InitialContext` để tra cứu JNDI;
- Có thể tra cứu **một tên JNDI cụ thể**;
- Có thể tra cứu **ít nhất một trong nhiều tên**;
- Điều kiện match và việc tài nguyên thực sự tương thích, hoạt động tốt lúc sử dụng.

Ba trường hợp đầu là điều `@ConditionalOnJndi` hỗ trợ trực tiếp. Trường hợp cuối vẫn cần xác nhận bằng kiểu dữ liệu, cấu hình và hành vi của dịch vụ thực tế.

## 2. JNDI là gì và tại sao ảnh hưởng đến auto-configuration?

**JNDI (Java Naming and Directory Interface)** là API tiêu chuẩn của Java để tìm đối tượng/tài nguyên theo một tên trong hệ thống đặt tên. Hai thành phần cốt lõi:

1. **`javax.naming.InitialContext`**: điểm bắt đầu để tra cứu một tên.
2. **`lookup(name)`**: thao tác yêu cầu hệ thống JNDI trả về đối tượng đã được gắn (bind) vào tên đó.

Ví dụ khái niệm:

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;

class JndiLookupExample {
    static Object findResource() throws NamingException {
        InitialContext context = new InitialContext();
        try {
            return context.lookup("java:comp/env/jdbc/OrdersDS");
        }
        finally {
            context.close();
        }
    }
}
~~~

Đây là **đoạn minh họa phương thức**, không phải chương trình có `main`. Nó chỉ chạy thành công khi môi trường đã cung cấp hệ thống JNDI và đăng ký tên `java:comp/env/jdbc/OrdersDS`.

`java:comp/env` thường là **environment naming context** trong môi trường ứng dụng Java có container hỗ trợ. Đây là **tên JNDI**, không phải đường dẫn file, URL HTTP, tên bean Spring hay khóa `application.properties`.

Lưu ý tên gói: trên **Java 17 / Spring Boot 3.x**, API chuẩn JNDI vẫn là **`javax.naming.*`** thuộc module Java `java.naming`. Không đổi thành `jakarta.naming.*` chỉ vì dự án sử dụng Jakarta Servlet hay Jakarta Persistence.

Hệ thống JNDI được hình thành từ **nhà cung cấp naming service / InitialContextFactory**, container hoặc cấu hình runtime. Tạo đối tượng `new InitialContext()` không có nghĩa chắc chắn `lookup` sẽ hoạt động: một số implementation chỉ phát hiện thiếu provider khi thực sự thực hiện thao tác.

## 3. Hợp đồng chính xác của @ConditionalOnJndi

Annotation có thể đặt trên **lớp** cấu hình hoặc **phương thức `@Bean`**:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;

// Chỉ kiểm tra hạ tầng JNDI.
@ConditionalOnJndi

// Kiểm tra một vị trí cụ thể.
@ConditionalOnJndi("java:comp/env/jdbc/OrdersDS")

// Kiểm tra NHIỀU vị trí: chỉ cần MỘT vị trí tồn tại.
@ConditionalOnJndi({
    "java:comp/env/jdbc/OrdersDS",
    "java:comp/env/jdbc/ArchiveDS"
})
~~~

**Ba khai báo trên là ba lựa chọn độc lập**, không viết cả ba trên cùng một phương thức/lớp. Định nghĩa annotation có thuộc tính **`String[] value() default {}`**.

Theo Spring Boot Javadoc:
- **Không có `value`** (`@ConditionalOnJndi` hoặc `@ConditionalOnJndi()`): điều kiện dựa trên **sự hiện diện của một JNDI `InitialContext` khả dụng**.
- **Một tên**: cần JNDI khả dụng và **tra cứu được tên đó**.
- **Nhiều tên**: cần JNDI khả dụng và **ít nhất một tên tra cứu được**; các tên quan hệ **OR (HOẶC)**, không phải AND.

Đây là điểm thường bị nhầm: `@ConditionalOnJndi({"nameA", "nameB"})` **không yêu cầu cả hai tên đều tồn tại**. Nó khác với `@ConditionalOnProperty(name={"a","b"})`, nơi nhiều thuộc tính trong cùng annotation phải đều đạt.

`@ConditionalOnJndi` không có `name`, `prefix`, `havingValue` hay `matchIfMissing` giống annotation điều kiện theo property. Giá trị của nó là **tên JNDI**, không phải giá trị cấu hình để so sánh chuỗi.

## 4. Bảng quyết định: khi nào match?

Giả sử mã kiểm tra `java:comp/env/app/cache` và `java:comp/env/app/queue`.

| Hạ tầng `InitialContext` khả dụng | Tra cứu `cache` | Tra cứu `queue` | `@ConditionalOnJndi` (không tên) | `@ConditionalOnJndi(".../cache")` | `@ConditionalOnJndi({".../cache",".../queue"})` |
| --- | --- | --- | --- | --- | --- |
| Không | Không | Không | **Không match** | **Không match** | **Không match** |
| Có | Không | Không | **Match** | Không match | Không match |
| Có | Có | Không | **Match** | **Match** | **Match** |
| Có | Không | Có | **Match** | Không match | **Match** |
| Có | Có | Có | **Match** | **Match** | **Match** |

Các cột "Có/Không" trong bảng nói về **kết quả tra cứu JNDI ở thời điểm điều kiện được đánh giá**, không chỉ về dòng khai báo tên trên giấy. Nếu một hệ thống từ chối tra cứu do cấu hình hoặc quyền truy cập, không thể mặc nhiên coi tên đó là dùng được.

**Ví dụ:**
- Một ứng dụng có `InitialContext` hoạt động nhưng không bind `jdbc/OrdersDS`: `@ConditionalOnJndi` có thể match, còn `@ConditionalOnJndi("java:comp/env/jdbc/OrdersDS")` không match.
- Server bind `jdbc/ArchiveDS` nhưng không bind `jdbc/OrdersDS`: điều kiện với mảng hai tên sẽ **match** vì ArchiveDS có mặt.
- Một JAR chạy độc lập không có JNDI provider hoặc environment naming context tương ứng: điều kiện thường **không match**.

Đừng suy ra rằng "ứng dụng web" thì chắc chắn có JNDI, hoặc "ứng dụng CLI" thì tuyệt đối không thể có JNDI. Điều kiện dựa trên **hạ tầng naming thực tế tại runtime**, không dựa trực tiếp trên Servlet/WebFlux hay loại đóng gói của ứng dụng.

## 5. Ví dụ Spring Boot chạy được: có tài nguyên JNDI mới tạo bean

Giả sử dự án đã có **Java 17+**, `spring-boot-starter` và plugin Maven Spring Boot (hỗ trợ dòng lệnh `spring-boot:run`). Tạo file **`src/main/java/example/JndiFeatureApplication.java`**:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringBootApplication(proxyBeanMethods = false)
@Import(JndiFeatureApplication.JndiFeatureConfiguration.class)
public class JndiFeatureApplication {

    public static void main(String[] args) {
        SpringApplication.run(JndiFeatureApplication.class, args);
    }

    @Bean
    CommandLineRunner showDecision(ApplicationContext context) {
        return args -> System.out.println(
                "JNDI_FEATURE_REGISTERED="
                        + context.containsBean("jndiFeature"));
    }

    @Configuration(proxyBeanMethods = false)
    static class JndiFeatureConfiguration {

        @Bean
        @ConditionalOnJndi("java:comp/env/app/feature")
        FeatureMarker jndiFeature() {
            return new FeatureMarker("JNDI resource detected");
        }
    }

    record FeatureMarker(String description) {
    }
}
~~~

**Giải thích:**
1. `@Import` bảo đảm lớp cấu hình `JndiFeatureConfiguration` được xử lý.
2. Phương thức `jndiFeature()` chỉ tạo bean khi tên `java:comp/env/app/feature` tra cứu được.
3. `CommandLineRunner` in kết quả ứng dụng có đăng ký bean hay không.

Lệnh chạy trong thư mục dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

**Kết quả quan sát tùy môi trường:** nếu không có naming context/tên trên, dòng được in là:

~~~text
JNDI_FEATURE_REGISTERED=false
~~~

Nếu môi trường cung cấp `InitialContext` và tên `java:comp/env/app/feature` tra cứu thành công, kết quả là:

~~~text
JNDI_FEATURE_REGISTERED=true
~~~

Đây là **hai kết quả có điều kiện**, không khẳng định mọi máy sẽ luôn in `false` hoặc `true`. Lệnh khởi động có thể in thêm log Spring Boot/Maven.

**Giới hạn của ví dụ:** `FeatureMarker` là bean tượng trưng. Mã chỉ chứng minh **bean registration được điều kiện hóa**; trong hệ thống thực tế, nếu bean phải sử dụng chính đối tượng JNDI, cần thực hiện lookup và kiểm tra kiểu của đối tượng đó, như minh họa ở phần sau.

### Tại sao đặt điều kiện ngay trên @Bean?

Trong ví dụ này chỉ `jndiFeature` cần tài nguyên JNDI. Nếu đặt `@ConditionalOnJndi` trên toàn bộ `JndiFeatureConfiguration`, **mọi bean trong lớp** cùng bị điều kiện đó chi phối. Đặt trên phương thức giúp giới hạn phạm vi ảnh hưởng.

Đối với **starter/library** tự tạo, có thể dùng `@AutoConfiguration` thay `@Configuration`, đồng thời đăng ký tên lớp cấu hình trong tệp `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Tệp đó phục vụ việc tự nạp auto-configuration trong thư viện; ví dụ ứng dụng ở trên dùng `@Import` trực tiếp nên không cần tệp imports.

## 6. Ví dụ ứng dụng thực tế: JNDI DataSource do container quản lý

Một môi trường Java EE/Jakarta EE hoặc servlet container có thể đăng ký một `javax.sql.DataSource` tại tên:

~~~text
java:comp/env/jdbc/OrdersDS
~~~

Khi ứng dụng chạy trong hạ tầng ấy, cấu hình có thể chỉ tạo bean tích hợp khi vị trí đó tồn tại:

~~~java
// Đoạn minh họa trong một lớp cấu hình Spring Boot.
import javax.sql.DataSource;

import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;
import org.springframework.context.annotation.Bean;
import org.springframework.jndi.JndiDataSourceLookup;

@Bean
@ConditionalOnJndi("java:comp/env/jdbc/OrdersDS")
DataSource ordersDataSource() {
    return new JndiDataSourceLookup()
            .getDataSource("java:comp/env/jdbc/OrdersDS");
}
~~~

**Các điểm cần hiểu:**
- Điều kiện trước hết xác minh rằng vị trí JNDI có thể được tra cứu.
- Khi `ordersDataSource()` chạy, `JndiDataSourceLookup` lấy đối tượng từ naming service và yêu cầu đó là **DataSource**.
- Lookup thành công ở thời điểm đánh giá điều kiện **không bảo đảm** truy vấn database sẽ thành công: tài nguyên có thể bị thay đổi, kết nối hết hạn, thông tin xác thực sai hoặc database không khả dụng.
- Nếu đối tượng JNDI có kiểu không phải `DataSource`, lỗi có thể xảy ra lúc tạo bean; annotation không phải phép xác thực kiểu đầy đủ.

Đối với ứng dụng chỉ cần cấu hình DataSource JNDI theo cách chuẩn, Spring Boot có cơ chế cấu hình `spring.datasource.jndi-name` trong các phiên bản/hình thức tích hợp phù hợp. Trước khi tự viết một `@Bean` DataSource, hãy xem auto-configuration DataSource hiện hữu của phiên bản dự án để tránh trùng bean hoặc thay thế cấu hình mặc định ngoài ý muốn.

**Thiết lập tài nguyên phía server** phụ thuộc máy chủ (Tomcat, WildFly, WebLogic, v.v.), phạm vi naming context và descriptor triển khai. Thêm chuỗi `java:comp/env/jdbc/OrdersDS` vào `application.properties` **không tự tạo ra** một binding JNDI trong server. Hãy đăng ký binding trong naming service/container trước, sau đó mới trỏ ứng dụng tới nó.

## 7. Nhiều vị trí JNDI: OR và cách xử lý ứng viên

Annotation:

~~~java
@ConditionalOnJndi({
    "java:comp/env/jdbc/PrimaryDS",
    "java:comp/env/jdbc/LegacyDS"
})
~~~

sẽ match nếu **ít nhất một** trong hai tên có thể tra cứu. Nhưng **annotation không trả về tên nào đã match** và không có chức năng "tự chọn DataSource". Ví dụ sai về giả định:

~~~java
// ĐOẠN MINH HỌA CÓ LỖI THIẾT KẾ:
@Bean
@ConditionalOnJndi({
    "java:comp/env/jdbc/PrimaryDS",
    "java:comp/env/jdbc/LegacyDS"
})
DataSource badDataSource() {
    // Sai: có thể chỉ LegacyDS tồn tại, khi đó lookup PrimaryDS vẫn thất bại.
    return new JndiDataSourceLookup()
            .getDataSource("java:comp/env/jdbc/PrimaryDS");
}
~~~

**Cách thiết kế tốt hơn:** nếu ứng dụng cần tương thích hai tên JNDI, trong logic tạo bean hãy thử các tên theo thứ tự ưu tiên, hoặc định nghĩa các cấu hình riêng cho từng naming contract. Đừng dựa vào danh sách tên của annotation như một cơ chế fallback tự động.

Nếu nghiệp vụ đòi **cả hai** tài nguyên cùng tồn tại, một annotation có mảng `value` **không đáp ứng phép AND**. Có thể tách thành nhiều bean/cấu hình được quản lý bởi điều kiện phù hợp, hoặc xây dựng `Condition` riêng có phép tra cứu cả hai tên; kiểm tra cách kết hợp annotation theo phiên bản trước khi áp dụng.

## 8. Kiểm thử chủ động bằng ApplicationContextRunner và naming service giả lập

Kiểm thử `@ConditionalOnJndi` thường khó hơn kiểm thử `@ConditionalOnProperty`, vì điều kiện **phụ thuộc trạng thái naming service của runtime**, chứ không chỉ phụ thuộc các PropertySource của Spring. Đặt `app.jndi.enabled=true` trong `application.yml` sẽ **không tự làm điều kiện match**.

Một cách tạo fixture trong **JUnit 5 + Spring Boot 3.x/Java 17+** là cài đặt một `InitialContextFactory` đơn giản cho phạm vi test. Mẫu dưới đây sử dụng một **JNDI `Context` giả lập bằng dynamic proxy**: chỉ tên `java:comp/env/app/present` và các context nền được trả về; tên còn lại ném `NameNotFoundException`.

Tạo **`src/test/java/example/JndiConditionTests.java`**. Dự án cần `spring-boot-starter-test`.

~~~java
package example;

import java.lang.reflect.Proxy;
import java.util.Hashtable;

import javax.naming.Context;
import javax.naming.NameNotFoundException;
import javax.naming.OperationNotSupportedException;
import javax.naming.spi.InitialContextFactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

public class JndiConditionTests {

    public static class InMemoryContextFactory
            implements InitialContextFactory {

        @Override
        public Context getInitialContext(Hashtable<?, ?> environment) {
            return (Context) Proxy.newProxyInstance(
                    JndiConditionTests.class.getClassLoader(),
                    new Class<?>[] {Context.class},
                    (proxy, method, args) -> {
                        if (method.getName().equals("lookup")) {
                            String name = String.valueOf(args[0]);

                            if (name.equals("java:comp")
                                    || name.equals("java:comp/env")) {
                                return proxy;
                            }
                            if (name.equals(
                                    "java:comp/env/app/present")) {
                                return "bound-value";
                            }
                            throw new NameNotFoundException(name);
                        }
                        if (method.getName().equals("close")) {
                            return null;
                        }
                        if (method.getName().equals("getEnvironment")) {
                            return new Hashtable<>();
                        }
                        throw new OperationNotSupportedException(
                                method.getName());
                    });
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class JndiConditions {

        @Bean
        @ConditionalOnJndi
        String anyContext() {
            return "context-available";
        }

        @Bean
        @ConditionalOnJndi("java:comp/env/app/present")
        String presentName() {
            return "present";
        }

        @Bean
        @ConditionalOnJndi("java:comp/env/app/missing")
        String missingName() {
            return "missing";
        }

        @Bean
        @ConditionalOnJndi({
                "java:comp/env/app/missing",
                "java:comp/env/app/present"
        })
        String oneOfTwo() {
            return "one-of-two";
        }
    }

    @Test
    void namedAndUnnamedJndiConditions() {
        // Thay đổi thuộc tính JVM mang tính toàn cục:
        // không chạy song song với test khác sử dụng JNDI.
        String key = Context.INITIAL_CONTEXT_FACTORY;
        String oldValue = System.getProperty(key);

        try {
            System.setProperty(
                    key, InMemoryContextFactory.class.getName());

            new ApplicationContextRunner()
                    .withUserConfiguration(JndiConditions.class)
                    .run(context -> {
                        assertThat(context).hasBean("anyContext");
                        assertThat(context).hasBean("presentName");
                        assertThat(context).doesNotHaveBean("missingName");
                        assertThat(context).hasBean("oneOfTwo");
                    });
        }
        finally {
            if (oldValue == null) {
                System.clearProperty(key);
            }
            else {
                System.setProperty(key, oldValue);
            }
        }
    }
}
~~~

Chạy:

~~~bash
./mvnw test -Dtest=JndiConditionTests
~~~

PowerShell:

~~~powershell
.\mvnw.cmd test -Dtest=JndiConditionTests
~~~

**Kết quả kỳ vọng:** một test thành công khi nhà cung cấp JNDI giả lập được sử dụng và không có test khác can thiệp vào trạng thái JNDI toàn cục. Các assertion diễn tả: hạ tầng khả dụng; tên có mặt match; tên thiếu không match; mảng hai tên match nếu một tên có mặt.

**Giới hạn của fixture:** nó phục vụ minh họa điều kiện tra cứu, **không triển khai đầy đủ API JNDI**. Context động chỉ hỗ trợ một số method; không dùng nó như server thực. Do thuộc tính `Context.INITIAL_CONTEXT_FACTORY` là **system property toàn JVM**, phải khôi phục ở `finally` và không chạy song song với test khác tự thay đổi provider. Một số server/test framework thiết lập naming service theo cách khác; khi đó nên dùng fixture container riêng hoặc kiểm thử tích hợp trong môi trường gần production.

Nếu chỉ muốn xem tình trạng ứng dụng thực, có thể bổ sung một test **tích hợp** chạy trong runtime JNDI thật và đối chiếu có/không có bean. Tách test đó khỏi bộ unit test chạy độc lập để tránh phụ thuộc máy của lập trình viên.

## 9. Những điều @ConditionalOnJndi không bảo đảm

1. **Không kiểm tra kiểu đối tượng được trả về.** Một tên có thể trả `String`, đối tượng tùy biến hoặc `DataSource`. Cần xác minh kiểu khi lấy đối tượng thật.
2. **Không tự tạo hay cấu hình naming service.** Nếu container chưa bind tên, khai báo annotation không làm tài nguyên xuất hiện.
3. **Không chờ tài nguyên từ bên ngoài sẵn sàng hoàn toàn.** JNDI lookup có thể thành công nhưng kết nối database/JMS sau đó vẫn lỗi.
4. **Không chuyển điều kiện thành công tắc runtime động.** Điều kiện được xét khi Spring xử lý cấu hình và đăng ký bean; tên JNDI xuất hiện sau lúc context khởi tạo thường không khiến bean đã bị bỏ qua tự động được tạo.
5. **Không có toán tử AND giữa nhiều tên trong `value`.** Danh sách chỉ cần một tên, phù hợp với tình huống chấp nhận nhiều tên thay thế.
6. **Không đồng nhất với việc thư viện `javax.naming` tồn tại trên classpath.** Có API JNDI trong JDK chưa nói lên có provider hoặc môi trường tên tra cứu được.
7. **Không tương đương việc ứng dụng có web server.** `@ConditionalOnWebApplication` kiểm tra loại ứng dụng web; `@ConditionalOnJndi` kiểm tra naming infrastructure/lookup.
8. **Không bảo đảm startup thành công.** Bean có thể phát sinh lỗi trong constructor hoặc dependency khác ngay cả khi điều kiện match.

### Nên kết hợp điều kiện khi nào?

Có thể cần thêm `@ConditionalOnClass` nếu thư viện sử dụng là dependency tùy chọn, `@ConditionalOnMissingBean` để cho phép người dùng tự định nghĩa bean thay thế, hoặc `@ConditionalOnProperty` nếu muốn thêm công tắc bật tính năng.

Ví dụ:

~~~java
// Đoạn minh họa: MyJndiAdapter là kiểu do ứng dụng định nghĩa.
@Bean
@ConditionalOnJndi("java:comp/env/app/feature")
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "enabled",
        havingValue = "true")
MyJndiAdapter myJndiAdapter() {
    return new MyJndiAdapter();
}
~~~

Khi ghép các annotation `@Conditional...` trên cùng phương thức, **tất cả điều kiện ở đó phải match**. Cần vừa có vị trí JNDI, vừa có property `app.integration.enabled=true`. Đoạn này không phải chương trình Java độc lập: `MyJndiAdapter` và vị trí phương thức `@Bean` phải được định nghĩa trong dự án.

## 10. Chẩn đoán khi không có bean như dự kiến

**Bước 1 — Kiểm tra tên JNDI hiệu lực.** Ghi nhận tên đầy đủ (ví dụ `java:comp/env/jdbc/OrdersDS`) trong container/runtime, bao gồm dấu chấm, chữ hoa chữ thường và namespace. Không giả định `jdbc/OrdersDS` và `java:comp/env/jdbc/OrdersDS` luôn tương đương trong mọi naming provider.

**Bước 2 — Thử lookup trực tiếp trong cùng runtime.** Dùng `InitialContext.lookup(...)` hoặc công cụ do container cung cấp. Kiểm tra các ngoại lệ JNDI như `NoInitialContextException` và `NameNotFoundException`. Chạy thử ngay trong JVM/môi trường triển khai để tránh nhầm provider của máy cục bộ với provider của server.

**Bước 3 — Xem báo cáo điều kiện Spring Boot.** Bật tham số `--debug` khi khởi động:

~~~bash
java -jar target/my-application.jar --debug
~~~

Thay tên JAR đúng với artifact dự án. Spring Boot có thể in **Condition Evaluation Report**, trong đó có kết quả của `OnJndiCondition`. Nếu dùng Actuator và đã bật/expose endpoint tương ứng, `/actuator/conditions` có thể giúp tra cứu nguyên nhân cấu hình match hoặc không match. Hạn chế công khai endpoint chẩn đoán nếu môi trường không cần.

**Bước 4 — Đánh giá đúng phạm vi annotation.** Đặt trên lớp cấu hình khiến toàn bộ nội dung của lớp bị kiểm soát, còn đặt trên từng phương thức `@Bean` chỉ kiểm soát method đó.

**Bước 5 — Kiểm tra nguyên nhân sau khi match.** Nếu log cho thấy điều kiện match nhưng bean vẫn lỗi, đọc stack trace lúc tạo bean và kiểm tra kiểu của tài nguyên, kết nối hoặc injection; đừng kết luận chính annotation hoạt động sai.

## 11. So sánh với các điều kiện môi trường khác

| Annotation | Điều được kiểm tra | Ví dụ |
| --- | --- | --- |
| `@ConditionalOnJndi` | Hạ tầng `InitialContext`, tùy chọn tên JNDI tra cứu được | Container bind `java:comp/env/jdbc/OrdersDS` |
| `@ConditionalOnProperty` | Giá trị cấu hình của Spring `Environment` | `app.feature.enabled=true` |
| `@ConditionalOnResource` | Sự hiện diện của resource theo đường dẫn Spring hiểu được | `classpath:feature.properties` |
| `@ConditionalOnClass` | Class cụ thể có trên classpath | Thư viện JDBC/JMS tùy chọn |
| `@ConditionalOnBean` | Spring BeanFactory đã có bean phù hợp | `DataSource` được đăng ký như bean |
| `@ConditionalOnWebApplication` | Ứng dụng được nhận diện là web application | Servlet hoặc reactive context |

Một `DataSource` tồn tại **trong JNDI** không có nghĩa đã tồn tại một Spring bean `DataSource`. Chúng thuộc hai hệ thống tra cứu khác nhau. Spring có thể tạo bean từ tài nguyên JNDI, nhưng chỉ sau khi được cấu hình/auto-configuration phù hợp.

## 12. Lỗi phổ biến và cách tránh

| Lỗi hiểu hoặc cấu hình | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tưởng `@ConditionalOnJndi({"A","B"})` là phép AND | Bean được tạo khi chỉ một tên tồn tại | Ghi nhớ phép OR; tự viết điều kiện khác nếu bắt buộc cả A và B |
| Dùng annotation không có tên để kiểm tra tài nguyên cụ thể | Điều kiện match khi có naming context dù thiếu tài nguyên | Chỉ rõ một hoặc nhiều tên trong `value` |
| Tưởng có `javax.naming.InitialContext` là đã có naming server | Sai môi trường và sai kết quả lookup | Thử tra cứu thật bằng cùng provider/runtime |
| Khai báo `application.properties` rồi cho rằng JNDI được bind | Lookup thất bại | Bind tài nguyên ở container/naming provider |
| Dùng OR nhiều tên nhưng phương thức luôn lookup tên đầu tiên | Điều kiện match nhưng tạo bean lỗi nếu chỉ tên thứ hai tồn tại | Cài đặt fallback lookup phù hợp |
| Nhầm `javax.naming` thành `jakarta.naming` | Mã Java không biên dịch | Dùng chuẩn JNDI `javax.naming` |
| Soạn unit test dựa vào JNDI của máy chạy test | Test thiếu ổn định giữa CI và laptop | Dùng naming fixture độc lập và kiểm soát trạng thái JVM |
| Tưởng condition match là kết nối database hoạt động | Startup/truy vấn lỗi sau khi điều kiện đã match | Kiểm tra kiểu đối tượng, kết nối và health checks riêng |

## 13. Câu hỏi tự kiểm tra

**1.** `@ConditionalOnJndi` không truyền tên sẽ match khi nào?

**Đáp án:** Khi có hạ tầng JNDI `InitialContext` khả dụng theo phép kiểm tra của Spring Boot; không yêu cầu một tên riêng do người viết annotation chỉ định.

**2.** Có naming context, tên `java:comp/env/A` không tồn tại nhưng `java:comp/env/B` tồn tại. Điều kiện `@ConditionalOnJndi({"java:comp/env/A","java:comp/env/B"})` có match không?

**Đáp án:** Có. Danh sách tên dùng phép **OR**: chỉ cần một vị trí được tra cứu.

**3.** Nếu điều kiện match ở tên JNDI `jdbc/OrdersDS`, kết nối database có chắc chắn hoạt động không?

**Đáp án:** Không. Điều kiện không xác nhận khả năng mở kết nối, quyền truy cập hoặc tình trạng database; cần kiểm thử riêng.

**4.** Tại sao một ứng dụng Boot trong Tomcat có thể match, còn cùng JAR chạy riêng lại không match?

**Đáp án:** Hạ tầng JNDI và binding có thể được container bên ngoài cung cấp cho ứng dụng triển khai trong container, trong khi JVM chạy riêng không có cấu hình tương ứng.

**5.** Nếu cần vừa có tên JNDI vừa có `app.integration.enabled=true`, nên làm gì?

**Đáp án:** Kết hợp `@ConditionalOnJndi("...")` và `@ConditionalOnProperty(..., havingValue="true")` trên cùng cấu hình hoặc bean; cả hai điều kiện đều phải match.

## 14. Tài liệu tham khảo chính thức

- Spring Boot Javadoc — `ConditionalOnJndi` (mô tả `InitialContext` và quy tắc "one of which must exist"): https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnJndi.html
- Spring Boot Reference — Creating Your Own Auto-configuration / Testing Your Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Java SE API — `javax.naming.InitialContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/InitialContext.html
- Java SE API — `javax.naming.spi.InitialContextFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/InitialContextFactory.html
