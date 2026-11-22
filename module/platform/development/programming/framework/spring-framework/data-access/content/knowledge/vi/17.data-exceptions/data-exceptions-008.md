# @Repository và PersistenceExceptionTranslationPostProcessor: dịch ngoại lệ dữ liệu đúng cách

Khi tầng truy cập dữ liệu gọi JDBC, JPA, Hibernate hoặc một persistence provider khác, lỗi thường xuất hiện dưới dạng ngoại lệ của thư viện/driver đang dùng. Ví dụ một thao tác lưu có thể phát sinh lỗi vi phạm unique constraint, mất kết nối, khóa lạc quan (optimistic locking) hoặc câu truy vấn không hợp lệ. Nếu tầng service phải biết từng loại ngoại lệ đặc thù của provider, mã nghiệp vụ sẽ phụ thuộc chặt vào công nghệ lưu trữ.

Spring Framework có cơ chế **persistence exception translation** để chuyển *những ngoại lệ phù hợp* thành các lớp thuộc hệ phân cấp `org.springframework.dao.DataAccessException`. Với repository trực tiếp dùng JPA/Hibernate hoặc API persistence riêng, cơ chế khai báo được xây dựng quanh ba yếu tố:

1. `@Repository` đánh dấu bean thuộc tầng truy cập dữ liệu và là điểm áp dụng advice.
2. `PersistenceExceptionTranslationPostProcessor` đăng ký **Spring AOP advisor** trên những repository bean phù hợp.
3. Một hoặc nhiều bean triển khai `PersistenceExceptionTranslator` hiểu ngoại lệ native và quyết định có thể chuyển nó sang `DataAccessException` nào.

Đây là ba vai trò khác nhau. **Chỉ gắn `@Repository` lên class không bảo đảm mọi ngoại lệ tự được dịch.** Ngược lại, một repository dùng `JdbcTemplate` thường đã nhận `DataAccessException` ngay từ `JdbcTemplate`, vì template tự dịch nhiều `SQLException` trong quá trình thực thi JDBC.

Bài này giải thích **khi nào nên dùng `@Repository` cùng `PersistenceExceptionTranslationPostProcessor`, điều kiện hoạt động, cấu hình, các giới hạn quan trọng và cách kiểm chứng bằng ví dụ Java 17+**.

## 1. Vì sao cần dịch ngoại lệ persistence?

Xem một tình huống: service gọi repository thêm mã sản phẩm, nhưng cơ sở dữ liệu từ chối vì mã đã tồn tại. Với mỗi provider, ngoại lệ native có thể khác nhau:

- JDBC driver thường báo lỗi SQL qua `SQLException` hoặc subclass.
- JPA có các ngoại lệ runtime thuộc API/provider, ví dụ một số biến thể `jakarta.persistence.PersistenceException`.
- Hibernate có hệ ngoại lệ riêng, như `org.hibernate.exception.ConstraintViolationException` (khác với Bean Validation `ConstraintViolationException`).
- Một thư viện persistence tự viết có thể ném `VendorUniqueKeyException`.

Nếu service bắt trực tiếp từng ngoại lệ provider, khi đổi provider hoặc thay cách truy cập dữ liệu, tầng service phải thay đổi. Spring cung cấp hệ phân cấp **unchecked `DataAccessException`** để diễn đạt các lỗi phổ biến bằng ngôn ngữ gần với ứng dụng hơn.

Một số kiểu thường gặp:

| Ngoại lệ Spring | Ý nghĩa thường thấy | Hướng xử lý tùy ngữ cảnh |
| --- | --- | --- |
| `DuplicateKeyException` | Vi phạm khóa duy nhất/primary key | Trả thông báo trùng dữ liệu phù hợp, không tự retry thao tác y hệt |
| `DataIntegrityViolationException` | Vi phạm ràng buộc toàn vẹn (bao quát hơn duplicate key) | Kiểm tra input và constraint cụ thể, tránh lộ chi tiết DB |
| `OptimisticLockingFailureException` | Xung đột phiên bản khi cập nhật lạc quan | Xem xét cơ chế báo conflict hoặc retry có kiểm soát |
| `DataAccessResourceFailureException` | Lỗi tài nguyên truy cập dữ liệu, ví dụ không thể kết nối | Kiểm tra hạ tầng và khả năng phục hồi |
| `QueryTimeoutException` | Truy vấn vượt thời gian chờ | Đánh giá timeout, kế hoạch truy vấn và chính sách retry |
| `InvalidDataAccessResourceUsageException` | Sử dụng tài nguyên dữ liệu không hợp lệ | Thường là vấn đề SQL/cấu hình/mã cần sửa |

Danh sách là ví dụ **ý nghĩa lớp**, không phải một ánh xạ cứng áp dụng cho mọi driver. Một provider có thể trả lỗi quá chung khiến translator chỉ chọn một lớp `DataAccessException` tổng quát, hoặc không dịch được.

`DataAccessException` là `RuntimeException`, nên không cần khai báo `throws` trong chữ ký phương thức Java. Nó giữ `cause` để hỗ trợ chẩn đoán lỗi gốc. **Dịch lỗi không có nghĩa đã xử lý xong lỗi**: service vẫn cần quyết định phản hồi, transaction và retry theo ý nghĩa nghiệp vụ.

## 2. @Repository thực sự làm gì?

`@Repository` thuộc:

~~~java
import org.springframework.stereotype.Repository;
~~~

Ví dụ:

~~~java
@Repository
public class ProductRepository {
    // Các phương thức truy cập database.
}
~~~

Đây là **mảnh code minh họa**, chưa chứa cách truy cập DB. Trong Spring:

- `@Repository` là một **stereotype annotation**, chuyên dùng để biểu thị tầng DAO/repository.
- Nó được meta-annotate bằng `@Component`. Nếu dự án bật component scanning tại package phù hợp, Spring có thể phát hiện class và tạo bean.
- Đối với exception translation, `PersistenceExceptionTranslationPostProcessor` dùng annotation này để xác định **bean nào đủ điều kiện được thêm advisor**.
- `@Repository` **không phải** transaction annotation; nó không tự bắt đầu/commit/rollback transaction.
- `@Repository` cũng không xác định schema, driver hoặc luật chuyển từng ngoại lệ.

So sánh với `@Component`: cả hai có thể tạo bean qua component scan, nhưng cấu hình mặc định của `PersistenceExceptionTranslationPostProcessor` tìm **`@Repository`**. Một class chỉ gắn `@Component` không nên được xem là chắc chắn nhận cùng advice. `@Service` biểu thị tầng nghiệp vụ và thông thường không phải điểm gắn persistence translation advisor.

Một class có thể được đăng ký qua `@Bean` mà không cần component scan; miễn đối tượng thực tế là repository phù hợp và đi qua Spring bean lifecycle, post-processor vẫn có cơ hội xử lý. Điều kiện quan trọng là **Spring sở hữu bean đó**, không phải ứng dụng tự tạo bằng `new` rồi gọi độc lập.

## 3. PersistenceExceptionTranslationPostProcessor hoạt động như thế nào?

Class `org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor` là một `BeanPostProcessor` chuyên dụng. Khi Spring khởi tạo bean repository, post-processor áp dụng `PersistenceExceptionTranslationAdvisor` cho bean đủ điều kiện. Advisor sử dụng `PersistenceExceptionTranslationInterceptor` làm advice và truy vấn các bean `PersistenceExceptionTranslator`.

Luồng ý tưởng:

~~~text
Service
  │ gọi phương thức trên repository bean lấy từ Spring
  ▼
Spring AOP proxy của repository
  │
  ├─ gọi phương thức repository thật
  │      └─ API JPA/Hibernate/native persistence có thể ném RuntimeException
  │
  └─ nếu ngoại lệ đi ra qua proxy:
         PersistenceExceptionTranslationInterceptor
           ├─ hỏi các PersistenceExceptionTranslator phù hợp
           ├─ translator trả DataAccessException → ném ngoại lệ đã dịch
           └─ không translator nào dịch được → giữ ngoại lệ gốc
  ▼
Service thấy ngoại lệ Spring (nếu đã dịch) hoặc ngoại lệ gốc
~~~

Các bước chính:

1. **Khởi tạo bean:** Spring đăng ký post-processor từ application context và duyệt các bean đủ điều kiện.
2. **Tạo hoặc bổ sung proxy:** Post-processor có thể áp dụng advisor trên proxy AOP đang tồn tại hoặc tạo proxy mới. Kiểu proxy thực tế tùy interface, cấu hình AOP và điều kiện của bean.
3. **Gọi repository:** Đối tượng gọi phải đi qua proxy Spring. Advice có thể thấy ngoại lệ runtime ném ra khỏi phương thức được intercept.
4. **Dịch ngoại lệ:** Interceptor nhờ `PersistenceExceptionTranslator.translateExceptionIfPossible(RuntimeException)`. Một translator có thể trả `DataAccessException` hoặc `null` nếu nó không hiểu ngoại lệ.
5. **Trả lại cho caller:** Nếu dịch thành công, caller nhận ngoại lệ mới có thể mang `cause` gốc; nếu không dịch được, exception native tiếp tục được ném.

Spring không dùng cách chuyển “mọi `RuntimeException` thành `DataAccessException`”. Những lỗi không liên quan đến persistence, như `NullPointerException` do code lỗi, **không nên** bị một translator tự viết gắn nhầm thành lỗi database.

### Điều kiện thiết yếu

| Thành phần | Nếu thiếu hoặc sai |
| --- | --- |
| Repository là bean Spring | Tạo trực tiếp bằng `new` không đi qua BeanPostProcessor/AOP |
| Class/bean được đánh dấu `@Repository` phù hợp | Cấu hình mặc định không tự advise mọi `@Component`/`@Service` |
| Có bean `PersistenceExceptionTranslationPostProcessor` hoạt động | Annotation vẫn là stereotype nhưng không tự sinh exception-translation advisor |
| Có translator hiểu ngoại lệ hiện tại | Interceptor không thể đoán đúng loại `DataAccessException` từ một lỗi bất kỳ |
| Lời gọi đi qua phương thức/proxy được advise | Self-invocation hoặc lời gọi trên object đích bỏ qua advice |
| Ngoại lệ thực sự thoát ra khỏi repository method | Exception bị catch/nuốt trong method hoặc phát sinh sau khi thoát khỏi boundary thì advice không có cơ hội dịch tại đó |

## 4. PersistenceExceptionTranslator là hợp đồng quan trọng nhất

Giao diện:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.support.PersistenceExceptionTranslator;
~~~

Phương thức cốt lõi:

~~~java
DataAccessException translateExceptionIfPossible(RuntimeException ex);
~~~

Đây là **chữ ký minh họa**, không phải phương thức top-level Java có thể chạy độc lập. Hợp đồng yêu cầu:

- Nếu có thể chuyển ngoại lệ native này, trả một `DataAccessException` cụ thể và phù hợp.
- Nếu không thể chuyển, **trả `null`**. Không biến mọi exception runtime thành `DataAccessException`.
- Cố gắng giữ nguyên ngoại lệ gốc làm `cause` để chẩn đoán stack trace, SQL state/vendor code khi hợp lệ.
- Một context có thể có **nhiều translator**; Spring có thể kết hợp chúng thành chuỗi, và cách sắp xếp phụ thuộc các quy tắc dependency ordering/`Ordered` khi áp dụng.

Một bean adapter của Spring dành cho JPA, ví dụ `LocalContainerEntityManagerFactoryBean`, có thể cung cấp implementation `PersistenceExceptionTranslator` sẵn. Với công nghệ không có adapter hỗ trợ, ứng dụng có thể cần viết translator của chính mình.

**Lưu ý:** Khi một translator trả `null`, điều đó có nghĩa “tôi không xử lý loại lỗi này”, không có nghĩa “không có lỗi”. Ngoại lệ gốc vẫn có thể được ném ra khỏi proxy.

## 5. Cấu hình rõ ràng trong Spring Framework thuần

Khi không dựa vào auto-configuration của Spring Boot, đăng ký post-processor dưới dạng bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;

@Configuration(proxyBeanMethods = false)
public class PersistenceTranslationConfig {
    @Bean
    public static PersistenceExceptionTranslationPostProcessor
            persistenceExceptionTranslationPostProcessor() {
        return new PersistenceExceptionTranslationPostProcessor();
    }
}
~~~

Đây là **class cấu hình Spring hoàn chỉnh**, lưu thành `PersistenceTranslationConfig.java` trong package phù hợp. `@Bean static` hữu ích cho một `BeanPostProcessor` vì giúp Spring đăng ký hạ tầng sớm mà không phải khởi tạo instance cấu hình trước thời điểm thích hợp. Đồng thời repository phải là bean Spring, ví dụ được phát hiện qua `@ComponentScan` hoặc khai báo `@Bean`.

Nếu dùng **Spring Boot 3.x**, `PersistenceExceptionTranslationAutoConfiguration` thường có thể đăng ký post-processor khi các điều kiện auto-configuration thỏa mãn. Các bản Boot 3.x có property `spring.dao.exceptiontranslation.enabled` với giá trị mặc định cho phép bật. Không nên thêm bean thứ hai một cách máy móc vào một dự án Boot đã có bean này; hãy kiểm tra context và cấu hình thực tế trước.

Có post-processor **vẫn chưa đủ** nếu không có translator tương ứng. Khi kết nối JPA/Hibernate qua integration chuẩn của Spring, translator thường được adapter/persistence factory cung cấp; khi dùng client thư viện riêng, bạn phải xác nhận điều này.

## 6. Ví dụ Java 17+ chạy được: dịch ngoại lệ native mô phỏng

Ví dụ sau dùng **Spring Framework 6.2.14** và không cần database. Mục đích là chứng minh chính xác:

- `@Repository` được nhận diện;
- `PersistenceExceptionTranslationPostProcessor` tạo AOP proxy;
- `PersistenceExceptionTranslator` đổi một lỗi native giả lập thành `DuplicateKeyException`;
- lỗi runtime không được translator nhận diện **giữ nguyên**;
- lời gọi diễn ra qua bean interface mà Spring trả về.

**Lưu ý:** `VendorUniqueConstraintException` là một exception mô phỏng cho bài học, không phải class của Hibernate/JPA hay một JDBC driver thật. Trong dự án thực tế, translator phải ánh xạ theo lỗi/cause/code mà provider tài liệu hóa.

Tạo thư mục:

~~~text
repository-translation-demo/
├── build.gradle
└── src/main/java/demo/
    └── RepositoryTranslationDemo.java
~~~

File `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-aop:6.2.14'
    implementation 'org.springframework:spring-tx:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.RepositoryTranslationDemo'
}
~~~

File `src/main/java/demo/RepositoryTranslationDemo.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;
import org.springframework.dao.support.PersistenceExceptionTranslator;
import org.springframework.stereotype.Repository;

public final class RepositoryTranslationDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            Store store = context.getBean(Store.class);
            System.out.println("proxied=" + AopUtils.isAopProxy(store));

            store.save("ok");
            System.out.println("ok");

            try {
                store.save("duplicate");
            } catch (DuplicateKeyException ex) {
                System.out.println(
                        "translated=" + ex.getClass().getSimpleName());
                System.out.println(
                        "cause=" + ex.getCause().getClass().getSimpleName());
            }

            try {
                store.save("unknown");
            } catch (VendorUnknownException ex) {
                System.out.println(
                        "untranslated=" + ex.getClass().getSimpleName());
            }
        }
    }

    public interface Store {
        void save(String code);
    }

    @Repository
    public static class StoreImpl implements Store {
        @Override
        public void save(String code) {
            if ("duplicate".equals(code)) {
                throw new VendorUniqueConstraintException("duplicate code");
            }
            if ("unknown".equals(code)) {
                throw new VendorUnknownException("unknown vendor error");
            }
        }
    }

    public static class VendorUniqueConstraintException
            extends RuntimeException {
        public VendorUniqueConstraintException(String message) {
            super(message);
        }
    }

    public static class VendorUnknownException extends RuntimeException {
        public VendorUnknownException(String message) {
            super(message);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public static PersistenceExceptionTranslationPostProcessor
                persistenceExceptionTranslationPostProcessor() {
            return new PersistenceExceptionTranslationPostProcessor();
        }

        @Bean
        public PersistenceExceptionTranslator vendorTranslator() {
            return exception -> {
                if (exception instanceof VendorUniqueConstraintException) {
                    return new DuplicateKeyException(
                            "Duplicate catalog code", exception);
                }
                return null;
            };
        }

        @Bean
        public Store store() {
            // @Bean đăng ký đối tượng; annotation @Repository nằm trên class.
            return new StoreImpl();
        }
    }
}
~~~

Chạy ở thư mục chứa `build.gradle` bằng Gradle đã cài:

~~~bash
gradle run
~~~

Nếu project đã có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). Gradle sẽ lấy dependency nếu chưa có trong cache. Với cấu hình trên, stdout của **chương trình**:

~~~text
proxied=true
ok
translated=DuplicateKeyException
cause=VendorUniqueConstraintException
untranslated=VendorUnknownException
~~~

Gradle có log build riêng. Những dòng này minh họa khác biệt giữa lỗi được dịch và lỗi không được dịch. `AopUtils.isAopProxy(store)` kiểm tra bean nhận về là AOP proxy; nó **không tự chứng minh mọi loại ngoại lệ native sẽ dịch được**.

### Đọc từng bước của ví dụ

1. `AnnotationConfigApplicationContext(Config.class)` khởi động context và đăng ký bean qua `@Configuration`.
2. Method `@Bean static` đưa `PersistenceExceptionTranslationPostProcessor` vào quá trình tạo bean.
3. Bean `store()` trả về một `StoreImpl` có `@Repository`. Chương trình gọi qua interface `Store`, tránh giả định luôn có thể truy cập proxy theo class implementation.
4. Bean `vendorTranslator()` chỉ nhận biết `VendorUniqueConstraintException` và trả `DuplicateKeyException`; mọi lỗi khác trả `null`.
5. `store.save("ok")` đi qua proxy nhưng không ném exception, nên thành công.
6. `store.save("duplicate")` ném lỗi native từ target. Interceptor hỏi translator rồi đưa `DuplicateKeyException` ra caller, với `cause` là lỗi gốc.
7. `store.save("unknown")` ném lỗi native khác. Translator trả `null`, nên caller nhận `VendorUnknownException` ban đầu.

Nếu gọi trực tiếp `new StoreImpl().save("duplicate")`, lời gọi không đi qua Spring proxy và sẽ ném **`VendorUniqueConstraintException`** gốc. Đây là cách kiểm chứng vai trò của proxy; không cần thay đổi mã translator.

### Giới hạn của demo

Ví dụ cố ý **không sử dụng database**, vì mục tiêu là kiểm tra cơ chế AOP và hợp đồng translator một cách tất định. Nó không chứng minh mapping từ bất kỳ phiên bản JDBC/JPA/Hibernate driver cụ thể nào. Đối với hệ thống thật, bổ sung integration test truy cập DB thật, mô phỏng constraint hợp lệ và quan sát exception/cause qua repository bean được inject.

## 7. Khi repository dùng JDBC: phân biệt hai cơ chế dịch lỗi

Đối với Spring JDBC, `JdbcTemplate` đã có cơ chế dịch những `SQLException` mà nó gặp khi chạy câu lệnh. Lớp DAO sau là ví dụ **mảnh code repository**, giả định bảng và `JdbcTemplate` đã được cấu hình:

~~~java
@Repository
public class UserJdbcRepository {
    private final JdbcTemplate jdbcTemplate;

    public UserJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int insert(String username) {
        return jdbcTemplate.update(
                "INSERT INTO app_user (username) VALUES (?)",
                username);
    }
}
~~~

Để biên dịch riêng, cần import `org.springframework.stereotype.Repository` và `org.springframework.jdbc.core.JdbcTemplate`. Đây không phải `main` độc lập. Nếu username bị trùng unique key, `JdbcTemplate` có thể ném `DuplicateKeyException` hoặc `DataIntegrityViolationException` theo khả năng diễn giải SQL state/vendor error code của driver.

**Điểm mấu chốt:** trong ví dụ trên, việc `SQLException` được dịch thường diễn ra **ngay trong `JdbcTemplate`**, trước khi exception rời phương thức `insert`. Không được kết luận “`@Repository` đã tự dịch SQLException” chỉ vì class có annotation và lỗi trả về đã là `DataAccessException`.

| Trường hợp | Ai thường thực hiện dịch? |
| --- | --- |
| `JdbcTemplate.update/query(...)` bắt `SQLException` | `SQLExceptionTranslator` được Spring JDBC dùng bên trong template |
| DAO gọi trực tiếp API JPA/Hibernate và nhận native `RuntimeException` | `PersistenceExceptionTranslationInterceptor` có thể nhờ `PersistenceExceptionTranslator` khi lời gọi đi qua proxy |
| DAO dùng JDBC thuần, phương thức khai báo `throws SQLException` | `SQLException` là checked exception; interceptor persistence chỉ xét runtime exception, nên không thể dựa vào post-processor để tự dịch như `JdbcTemplate` |
| DAO bắt native exception rồi tự ném một `IllegalStateException` | Chỉ còn wrapper đi qua proxy; translator có thể không nhận ra hoặc chọn sai ngữ nghĩa nếu tự viết không đúng |
| Native exception bị ném sau khi repository method đã return | Advice tại boundary repository không nhất thiết còn cơ hội nhìn thấy exception |

Với mã JDBC thuần, có thể dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` để nhận exception translation chuẩn, hoặc chủ động dùng `SQLExceptionTranslator` nếu cần thao tác JDBC mức thấp. Không viết một translator chung kiểu “mọi `RuntimeException` → `DataAccessException`” để che lấp lỗi lập trình.

## 8. Khi repository dùng JPA hoặc Hibernate

Trong một repository gọi `EntityManager` trực tiếp, ví dụ sau là **mảnh code dùng trong ứng dụng JPA có bean `EntityManager` và entity `Product` hợp lệ**:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class JpaProductRepository {
    @PersistenceContext
    private EntityManager entityManager;

    public void save(Product product) {
        entityManager.persist(product);
    }
}
~~~

`@PersistenceContext` yêu cầu hạ tầng JPA phù hợp, và `Product` là entity đã mapping; đoạn này không chạy độc lập nếu thiếu entity/persistence unit. Khi native runtime exception ném trong lời gọi repository và translator JPA phù hợp có trong Spring context, `PersistenceExceptionTranslationPostProcessor` có thể giúp đưa lỗi về `DataAccessException`.

Một số điều cần hiểu kỹ:

- `EntityManager.persist(...)` có thể **chưa thực thi SQL INSERT ngay lập tức**. Lỗi unique constraint có thể chỉ lộ ra ở `flush` hoặc lúc transaction commit.
- Nếu exception phát sinh **sau khi phương thức repository đã trả về** (chẳng hạn flush/commit do hạ tầng transaction điều khiển ở lớp khác), không thể giả định riêng advisor trên repository sẽ thấy ngoại lệ ấy.
- Việc mở/commit transaction do transaction manager và `@Transactional` quyết định; `@Repository` không tự cấp transaction.
- `JpaTransactionManager` và adapter JPA có cơ chế chuyển đổi lỗi riêng trong những luồng xử lý transaction; đó là đường đi khác cần hiểu khi chẩn đoán.

**Không thêm `entityManager.flush()` bừa bãi chỉ để “làm @Repository dịch lỗi ngay”**. Flush sớm thay đổi thời điểm SQL và hiệu năng. Nếu nghiệp vụ đòi kiểm tra ngay (ví dụ phát hiện trùng dữ liệu trước thao tác tiếp theo), hãy thiết kế boundary transaction, thời điểm flush và xử lý lỗi có chủ đích.

## 9. Proxy AOP: bốn tình huống dễ bỏ sót

### 9.1. Gọi nội bộ cùng object (self-invocation)

~~~java
@Repository
public class ProductDao {
    public void outer() {
        inner(); // gọi trên 'this', không đi qua proxy của chính bean
    }

    public void inner() {
        // Có thể phát sinh native persistence RuntimeException.
    }
}
~~~

Đây là mã minh họa phạm vi lời gọi. Khi service gọi `proxy.outer()`, advice bao quanh `outer` có thể dịch exception runtime **nếu exception cuối cùng thoát ra khỏi `outer`**. Tuy nhiên, lời gọi `this.inner()` **không có riêng một lần intercept cho `inner`**. Sự khác biệt này quan trọng nếu code kỳ vọng advice cho chính `inner`, nhất là khi các phương thức bắt/rethrow exception khác nhau.

Đừng diễn giải đơn giản rằng “self-invocation luôn khiến ngoại lệ không được dịch”: nếu exception thoát ra khỏi phương thức ngoài đang được proxy intercept, advisor bên ngoài vẫn có cơ hội dịch. Cần quan sát **boundary nào nhận được exception**.

### 9.2. Tự new repository

~~~java
ProductDao direct = new ProductDao();
direct.inner();
~~~

Không có bean lifecycle/proxy. Không có post-processor nào tự chặn lời gọi trên instance `direct` này. Hãy inject repository bean từ container khi muốn hạ tầng Spring áp dụng.

### 9.3. Catch exception bên trong repository

~~~java
public void save() {
    try {
        callNativePersistenceApi();
    } catch (RuntimeException ex) {
        logFailure(ex);
        // Nếu nuốt lỗi tại đây, proxy sẽ thấy method kết thúc bình thường.
    }
}
~~~

Đây là **pseudocode Java**, không thể biên dịch độc lập: `callNativePersistenceApi` và `logFailure` đại diện cho hàm thực tế. Nếu repository bắt lỗi rồi trả về bình thường, advice ở ngoài không có gì để dịch. Nếu repository cần xử lý exception, hãy giữ nguyên semantics, không biến lỗi ghi dữ liệu thành thành công giả.

### 9.4. Kiểu proxy và chữ ký phương thức

Với JDK dynamic proxy, caller thường truy cập qua interface mà proxy triển khai. Với class-based proxy, caller có thể truy cập qua concrete class theo điều kiện AOP. Mức độ phù hợp chịu ảnh hưởng của class/method final, visibility, loại proxy và cấu hình framework. Không giả định một concrete class luôn có thể cast từ bean proxy được Spring tạo.

Khi debug, có thể kiểm tra `AopUtils.isAopProxy(bean)` hoặc `AopUtils.getTargetClass(bean)`. Đây là bằng chứng về cấu trúc proxy, **không thay thế** test exception thực sự đi qua advisor.

### Một điều ít được chú ý: khai báo ngoại lệ trong method signature

`PersistenceExceptionTranslationInterceptor` mặc định **để nguyên ngoại lệ runtime nếu target method khai báo rằng ngoại lệ đó có thể được ném**, kể cả khi chữ ký khai báo một superclass tương thích như `Exception`; có cấu hình `alwaysTranslate` ở interceptor nếu cần thay đổi hành vi này. Trong thực tế, các repository interface thường không khai báo `throws Exception` chung chung, và bạn không nên dựa vào việc tự động dịch khi chữ ký cố ý cho phép ngoại lệ native đi qua.

## 10. Tạo một translator đúng ngữ nghĩa cho persistence provider tùy chỉnh

Giả sử một client tự viết ném:

~~~java
public class VendorConstraintException extends RuntimeException {
    private final String errorCode;

    public VendorConstraintException(
            String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
~~~

Đây là một class Java hoàn chỉnh nếu lưu `VendorConstraintException.java`, dành làm minh họa. Giả sử vendor tài liệu hóa `UK_DUPLICATE` là **unique constraint** và `FK_MISSING` là **foreign key violation**, có thể tạo một translator:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.support.PersistenceExceptionTranslator;

public final class VendorConstraintTranslator
        implements PersistenceExceptionTranslator {
    @Override
    public DataAccessException translateExceptionIfPossible(
            RuntimeException ex) {
        if (!(ex instanceof VendorConstraintException vendor)) {
            return null;
        }

        return switch (vendor.getErrorCode()) {
            case "UK_DUPLICATE" ->
                    new DuplicateKeyException("Unique key conflict", vendor);
            case "FK_MISSING" ->
                    new DataIntegrityViolationException(
                            "Referenced row does not exist", vendor);
            default -> null;
        };
    }
}
~~~

Đây là class Java 17+ độc lập ở mức source, **phụ thuộc** class `VendorConstraintException` phía trên và Spring `spring-tx`. Tên error code chỉ là giả định **được định nghĩa trong ví dụ**, không đại diện cho mã lỗi của PostgreSQL, MySQL, Oracle, SQL Server hay một provider cụ thể.

Đăng ký như bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorTranslationConfig {
    @Bean
    public PersistenceExceptionTranslator vendorConstraintTranslator() {
        return new VendorConstraintTranslator();
    }
}
~~~

Đây là mảnh cấu hình cần import `Configuration`/`Bean` và các class translator; nó bổ sung translator, còn `PersistenceExceptionTranslationPostProcessor` phải được đăng ký theo phần 5 hoặc bằng auto-configuration đang hoạt động.

### Vì sao mapping cần chính xác?

- Không gán mọi lỗi constraint thành `DuplicateKeyException`; foreign key, check constraint và not-null có ý nghĩa khác.
- Nếu vendor có mã tương đương “deadlock”, “timeout”, “connection refused”, hãy cân nhắc subclass Spring phù hợp và tính transient theo hợp đồng provider, **không suy diễn chỉ từ text message**.
- Giữ exception gốc trong `cause`, nhưng đừng nhét SQL chứa thông tin nhạy cảm vào thông điệp trả cho HTTP client.
- Không dịch `NullPointerException`, lỗi validation đầu vào hoặc lỗi nghiệp vụ thành `DataAccessException` trừ khi thật sự có hợp đồng dữ liệu rõ ràng cho việc đó.
- Khi không biết mã lỗi hoặc provider không cam kết ý nghĩa, trả `null` để ngoại lệ gốc đi qua; đó là lựa chọn an toàn hơn việc dịch sai.

Đối với JDBC, `SQLErrorCodeSQLExceptionTranslator`/translator chuẩn và cấu hình SQL state của Spring có thể đã bao phủ nhiều mã lỗi phổ biến; không nên tự làm lại toàn bộ cơ chế ấy khi dùng `JdbcTemplate`.

## 11. Kiểm tra cấu hình và hành vi ở runtime

Một checklist thực tiễn khi thấy `@Repository` nhưng exception vẫn là native:

1. **Bean có do Spring tạo?** Kiểm tra nơi đăng ký qua `@ComponentScan`, `@Import`, `@Bean` hay auto-configuration. Tránh tự `new` ở service.
2. **Đúng annotation chưa?** `@Repository` nằm trên implementation/proxy target phù hợp; không chỉ có `@Service` hoặc `@Component`.
3. **Đã đăng ký `PersistenceExceptionTranslationPostProcessor` chưa?** Ở Spring Framework thuần cần cấu hình bean; ở Spring Boot hãy kiểm tra auto-configuration có kích hoạt.
4. **Bean đang được gọi có là AOP proxy?** Dùng `AopUtils.isAopProxy(...)` để xác minh. Nếu không, xem BeanPostProcessor setup, class/interface, vòng đời khởi tạo.
5. **Có `PersistenceExceptionTranslator` phù hợp?** Với JPA kiểm tra entity manager factory/adapter Spring; với client riêng cần một translator biết native exception.
6. **Exception phát sinh lúc nào?** Ngay trong repository method, khi flush, khi transaction commit, hay bên trong task async? Điểm phát sinh quyết định advisor nào có cơ hội thấy.
7. **Exception type và cause thực tế?** Xem stack trace và chain gốc; nếu đã bị ứng dụng wrap, translator có thể không nhận ra.
8. **Method signature/đường gọi?** Không giả định lời gọi nội bộ hoặc khai báo `throws Exception` có cùng hành vi translation với phương thức interface đi qua proxy.
9. **Có interceptor/advisor khác không?** Transaction, caching, async, retry hoặc security cũng có thể tạo proxy. Đọc order và boundary của chúng khi test cho kết quả bất ngờ.

Có thể kiểm tra bean thực tế trong một test Spring:

~~~java
Object repositoryBean = context.getBean(Store.class);
boolean proxied = AopUtils.isAopProxy(repositoryBean);
System.out.println(proxied);
~~~

Đây là **mảnh code trong ngữ cảnh có `context`, interface `Store` và import `AopUtils`** như demo phần 6. Không dùng kết quả proxy đơn lẻ để khẳng định translator đã chọn đúng loại exception: cần **assert chính lỗi được ném khi gọi API**.

## 12. Kiểm thử exception translation đúng cách

Với cùng repository và provider version production, bộ test nên phân biệt ít nhất ba tình huống:

| Test | Điều cần assert |
| --- | --- |
| Native error đã có mapping | Qua bean proxy nhận `DataAccessException` đúng subclass, có `cause` gốc |
| Runtime error không được translator nhận biết | Giữ nguyên lỗi gốc, không bị dịch sai thành lỗi dữ liệu |
| Gọi target trực tiếp không qua Spring | Không được kỳ vọng post-processor can thiệp |
| Vi phạm unique/foreign key trên DB thật | Kết quả đúng ý nghĩa theo database + provider + driver + thời điểm flush |
| Lỗi tại transaction commit | Kiểm tra boundary transaction, không nhầm với translation tại repository method |
| Repository dùng `JdbcTemplate` | Xác định exception đã được template dịch và root cause là `SQLException` khi thích hợp |

### Kiểm thử thủ công cho demo phần 6

Trong chương trình:

- Lệnh `store.save("ok")` chạy bình thường.
- Lệnh `store.save("duplicate")` trả `DuplicateKeyException`, với `cause` là `VendorUniqueConstraintException`.
- Lệnh `store.save("unknown")` trả `VendorUnknownException`.
- `AopUtils.isAopProxy(store)` trả `true` với cấu hình AOP được sử dụng.

Đây là test cho **cơ chế proxy + translator**, chưa phải integration test của persistence provider. Test DB phải thực thi constraint thật và kiểm tra trạng thái sau rollback, không chỉ assert exception class.

### Những khác biệt cần đưa vào integration test

- Loại exception native của provider khi gọi `persist`, `flush` và commit.
- Mã SQL state/vendor code liên quan tới constraint, unique key hoặc transaction conflict.
- Translator nào đang tồn tại trong context nếu có nhiều factory hoặc nhiều DB.
- Cách Spring transaction manager rollback khi `DataAccessException` (unchecked) thoát khỏi transaction boundary.
- Exception gốc còn được giữ trong `cause`, không lộ message nhạy cảm trong API response.
- Hệ thống dùng reactive data access hay AOP proxy thông thường: chỉ áp dụng hướng dẫn này đúng cho mô hình bean/interceptor đang sử dụng; không tự suy rộng sang cơ chế xử lý reactive khác.

## 13. Dịch exception khác với transaction, HTTP error mapping và retry

Đây là những mối quan hệ độc lập nhưng thường bị nhầm:

**Exception translation:** một lỗi native có thể được biểu diễn thành subclass của `DataAccessException`. Việc này không khiến lệnh SQL thành công hay tự phục hồi kết nối.

**Transaction rollback:** khi một unchecked exception thoát khỏi phương thức được quản lý bởi `@Transactional`, Spring mặc định đánh dấu rollback theo quy tắc rollback thông thường (trừ khi được cấu hình khác). Việc dịch lỗi có thể giúp tầng trên nhận diện lỗi, nhưng không phải bản thân annotation `@Repository` quyết định commit hay rollback.

**HTTP response:** `DuplicateKeyException` không tự động có nghĩa HTTP 409 hoặc một JSON response theo ý ứng dụng. Tầng API có thể dùng `@ControllerAdvice`/exception handler để đổi thành mã phản hồi phù hợp mà không đưa SQL/stack trace ra ngoài.

**Retry:** không nên tự retry mọi `DataAccessException`. Ví dụ retry unique constraint với cùng dữ liệu có thể tạo nhiều request vô nghĩa; với lỗi kết nối hoặc deadlock, retry cũng cần xác định thao tác idempotent và trạng thái transaction. Các subclass transient/non-transient giúp phân loại, nhưng không thay thế quyết định nghiệp vụ.

Một cách tổ chức dễ bảo trì:

~~~text
HTTP/Controller
    ↓
Service (@Transactional nếu có nghiệp vụ nhiều thao tác)
    ↓
Repository (@Repository)
    ↓
JDBC/JPA/Hibernate/provider
    ↑ native exception
Spring JDBC translator hoặc Repository AOP translator
    ↑ DataAccessException (nếu ánh xạ được)
Service quyết định nghiệp vụ / rollback / retry có kiểm soát
    ↑
API exception handler quyết định HTTP response
~~~

Những đường dịch lỗi trong sơ đồ mang tính lựa chọn theo công nghệ: `JdbcTemplate` và repository AOP không phải hai bước luôn nối tiếp nhau, và một số lỗi transaction có thể được chuyển đổi tại transaction manager.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Cứ thêm `@Repository` là tất cả lỗi tự thành `DataAccessException`” | Cần BeanPostProcessor/advisor, translator phù hợp, proxy boundary và loại exception tương thích |
| “Post-processor biết hết mã lỗi của mọi database” | Nó phối hợp translator; mapping thực tế do translator/provider đảm nhiệm |
| “`@Component` với `@Repository` hoàn toàn giống nhau” | Cùng khả năng component scan, nhưng `@Repository` là marker chuyên dụng cho persistence translation |
| “`@Repository` tương đương `@Transactional`” | Annotation đánh dấu tầng DAO; transaction cần hạ tầng/config riêng |
| “Spring sẽ luôn dịch exception khi `EntityManager.persist` được gọi” | DB có thể phát hiện lỗi muộn lúc flush/commit, ngoài repository AOP boundary |
| “Proxy sẽ can thiệp mọi lần gọi cùng object” | Self-invocation không mở thêm một lượt advice; lời gọi ngoài qua proxy mới được intercept |
| “`JdbcTemplate` cần post-processor để dịch `SQLException`” | `JdbcTemplate` tự dịch `SQLException` bên trong template |
| “Translator nên bắt tất cả `RuntimeException`” | Translator chỉ nên xử lý loại lỗi nó hiểu; trả `null` với lỗi khác |
| “Có `DataAccessException` nghĩa là thao tác đã rollback” | Rollback phụ thuộc transaction boundary và cấu hình transaction |
| “`DuplicateKeyException` sẽ tự trả HTTP 409” | HTTP error mapping là trách nhiệm của tầng API/handler |

## 15. Quy trình áp dụng thực tế

Khi xây một repository dựa trên API persistence trả native runtime exception:

1. Đánh dấu implementation bằng `@Repository`, để Spring quản lý đối tượng qua component scanning hoặc khai báo bean.
2. Xác minh context có `PersistenceExceptionTranslationPostProcessor` (Spring Framework thuần: thêm cấu hình; Spring Boot: kiểm tra auto-configuration).
3. Xác minh có `PersistenceExceptionTranslator` tương thích với công nghệ đang dùng; bổ sung translator riêng chỉ khi cần.
4. Viết một test từ service gọi repository bean được inject và cố ý gây lỗi native có ý nghĩa rõ ràng.
5. Assert subclass `DataAccessException` phù hợp và `cause` gốc; đồng thời test lỗi chưa có mapping giữ nguyên.
6. Kiểm tra điểm phát sinh lỗi trong quá trình flush/commit và chính sách transaction.
7. Chỉ sau đó thiết kế retry, thông báo nghiệp vụ và ánh xạ HTTP. Giữ log chẩn đoán ở phía máy chủ, tránh tiết lộ SQL và dữ liệu nhạy cảm cho người dùng cuối.

**Nguyên tắc ghi nhớ:** `@Repository` chọn **đúng tầng và đúng bean**; `PersistenceExceptionTranslationPostProcessor` thiết lập **AOP advice**; `PersistenceExceptionTranslator` quyết định **loại lỗi nào có thể dịch và dịch sang `DataAccessException` nào**. Thiếu một mắt xích hoặc lời gọi không đi qua proxy, ứng dụng có thể vẫn thấy lỗi native. Dịch lỗi chính xác phải được chứng minh qua test với công nghệ và transaction boundary thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — Exception Translation trong ORM integration](https://docs.spring.io/spring-framework/reference/data-access/orm/general.html): mục đích, `@Repository` và post-processor.
- [Spring Framework Javadoc — PersistenceExceptionTranslationPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/dao/annotation/PersistenceExceptionTranslationPostProcessor.html): phạm vi bean được advice, AOP proxy và translator discovery.
- [Spring Framework Javadoc — PersistenceExceptionTranslator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/dao/support/PersistenceExceptionTranslator.html): hợp đồng ánh xạ hoặc trả `null`.
- [Spring Framework Javadoc — PersistenceExceptionTranslationInterceptor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/dao/support/PersistenceExceptionTranslationInterceptor.html): advice và việc bảo lưu exception được khai báo trong chữ ký.
- [Spring Framework Reference — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` và cơ chế dịch `SQLException`.
- [Spring Boot 3.2 API — PersistenceExceptionTranslationAutoConfiguration](https://docs.spring.io/spring-boot/docs/3.2.12/api/org/springframework/boot/autoconfigure/dao/PersistenceExceptionTranslationAutoConfiguration.html): điều kiện auto-configuration của Spring Boot 3.x.
