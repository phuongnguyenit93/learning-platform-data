# DataSource lấy qua JNDI trong môi trường được quản lý

Khi ứng dụng Java/Spring chạy trong **môi trường được quản lý** (ví dụ ứng dụng WAR triển khai trên Apache Tomcat hoặc một Jakarta EE application server), người quản trị thường cấu hình kết nối cơ sở dữ liệu tại container. Ứng dụng không tự tạo pool và nhúng cấu hình JDBC trong mã nguồn, mà **tra cứu một đối tượng `javax.sql.DataSource` đã được môi trường đăng ký** bằng JNDI (Java Naming and Directory Interface). Đối tượng `DataSource` này sau đó được đưa vào các thành phần Spring như `JdbcTemplate`, repository hoặc transaction manager.

Bài học tập trung vào cơ chế *DataSource lấy qua JNDI*, cách cấu hình tài nguyên phía container, kết nối tài nguyên với Spring, kiểm thử và các lỗi vận hành thường gặp. Ví dụ dùng Java 17+, Spring Framework 6+ và Tomcat 10.1; các server khác có cách khai báo và namespace khác nhau.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích được vai trò khác nhau của `DataSource`, JNDI naming service, JDBC driver, connection pool và Spring.
2. Phân biệt tên JNDI `java:comp/env/jdbc/LearningDB` với JDBC URL `jdbc:h2:mem:learning`, cũng như namespace tương đối `jdbc/LearningDB`.
3. Khai báo một tài nguyên `DataSource` trong container, ánh xạ nó vào môi trường của web application và tra cứu bằng Java hoặc Spring.
4. Tạo bean Spring `DataSource` từ `JndiDataSourceLookup`, inject vào `JdbcTemplate`, và quản lý kết nối đúng cách.
5. Nhận diện khác biệt giữa việc *container quản lý pool* và *container quản lý transaction*; tránh cấu hình hai cơ chế transaction không tương thích.
6. Chẩn đoán lỗi thiếu JNDI context, sai tên tài nguyên, thiếu JDBC driver và không kết nối được database.

## 2. Mô hình hoạt động: ai cung cấp cái gì?

**`javax.sql.DataSource`** là interface JDBC đại diện cho một nguồn cung cấp `java.sql.Connection`. Nó không bắt buộc là một connection pool: implementation có thể tạo connection mới mỗi lần, dùng pool, hoặc cung cấp connection chịu quản lý giao dịch. Với Tomcat trong ví dụ này, tài nguyên JNDI trỏ tới một `DataSource` do pool của container tạo và quản lý.

**JNDI** là API đặt tên và tra cứu object hoặc tài nguyên. Ứng dụng hỏi naming provider một tên logic; provider trả về tài nguyên đã được binding/configuration. JNDI không phải giao thức kết nối database, không tự thực thi SQL và tự nó không bảo đảm pooling.

**JDBC driver** hiện thực kết nối cụ thể tới database. Nó có thể được nạp bởi classloader của container khi container xây dựng pool. **Spring JDBC** sử dụng `DataSource` được inject và cung cấp các abstraction như `JdbcTemplate`; Spring không nhất thiết biết URL, user hoặc mật khẩu của database.

~~~text
Bộ phận vận hành / cấu hình container
  ├─ JDBC driver + JDBC URL + credentials
  ├─ Connection pool, giới hạn kết nối, timeout
  └─ JNDI binding: java:comp/env/jdbc/LearningDB
                          │
               InitialContext / lookup
                          ▼
             DataSource (javax.sql.DataSource)
                          │
             @Bean dataSource() trong Spring
                          │
          JdbcTemplate / Repository / Service
                          │
                    getConnection()
                          ▼
                       Database
~~~

Điểm cốt lõi: **Spring nhận `DataSource` thông qua một tên JNDI ổn định**, trong khi các tham số kết nối thật nằm ở môi trường triển khai. Ứng dụng có thể sử dụng cùng interface trên các môi trường khác nhau, nếu mỗi môi trường cung cấp tài nguyên đúng tên và đúng kiểu.

### So sánh JNDI và tự cấu hình pool

| Tiêu chí | DataSource qua JNDI | DataSource do ứng dụng cấu hình |
| --- | --- | --- |
| Ai tạo `DataSource`? | Container/naming provider | Ứng dụng hoặc framework auto-configuration |
| Ai cấu hình JDBC URL/credentials? | Môi trường triển khai | Cấu hình ứng dụng/secret manager |
| Pool do ai quản lý? | Theo resource factory của container | Theo pool implementation của ứng dụng |
| Dependency của business code | Thường chỉ phụ thuộc `DataSource` | Cũng chỉ nên phụ thuộc `DataSource` |
| Phù hợp | WAR trong external container/application server có JNDI | Standalone service, executable JAR, môi trường không cấp JNDI |

Không có lựa chọn nào tự động tốt hơn trong mọi trường hợp. Quyết định phụ thuộc mô hình triển khai, yêu cầu vận hành và ownership của hạ tầng.

## 3. Namespace JNDI và tên tài nguyên

JNDI làm việc với **tên**, chẳng hạn:

- `java:comp/env`: vùng *environment naming context* (ENC) của một component/web application theo mô hình Jakarta EE.
- `jdbc/LearningDB`: tên logic thường khai báo tương đối bên trong ENC của ứng dụng.
- `java:comp/env/jdbc/LearningDB`: đường dẫn đầy đủ tới tài nguyên khi môi trường triển khai cung cấp namespace tương ứng.

Trong Tomcat, việc khai báo tài nguyên với `name="jdbc/LearningDB"` ở `<Context>` sẽ làm tài nguyên khả dụng trong namespace `java:comp/env` của web application đó. Tên `jdbc/LearningDB` ở đây không phải JDBC URL; nó chỉ là key để tìm object.

Ví dụ Java dùng JNDI API:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;

InitialContext initialContext = new InitialContext();
DataSource dataSource = (DataSource)
        initialContext.lookup("java:comp/env/jdbc/LearningDB");
~~~

Đây là **đoạn mã minh họa trong một môi trường có JNDI provider**, không phải Java file độc lập hoàn chỉnh. Nếu chạy trong JVM thông thường không được cấp naming context, `new InitialContext()` có thể tạo đối tượng nhưng thao tác `lookup(...)` thất bại, thường với `NoInitialContextException`.

Có thể tra cứu tương đối qua ENC đã lấy trước:

~~~java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.sql.DataSource;

Context environment = (Context)
        new InitialContext().lookup("java:comp/env");
DataSource dataSource = (DataSource)
        environment.lookup("jdbc/LearningDB");
~~~

Hai cách trên nhắm cùng tài nguyên trong **cấu hình Tomcat ví dụ**. Một application server khác có thể cấp namespace như `java:jboss/datasources/...` hoặc tên toàn cục riêng; không được tùy tiện thêm `java:comp/env/` cho mọi loại tên.

**Lưu ý về package:** `javax.naming.*` và `javax.sql.DataSource` vẫn thuộc Java SE. Dù mã Servlet của Tomcat 10+ sử dụng `jakarta.servlet.*`, không đổi `javax.sql.DataSource` thành `jakarta.sql.DataSource`; kiểu sau không phải interface JDBC tương ứng.

## 4. Ví dụ container: đăng ký DataSource trong Tomcat 10.1

Ta tạo một tài nguyên phục vụ môi trường phát triển với H2 in-memory. Để chạy ví dụ thực tế cần có Tomcat 10.1 (Java 11+; các snippet ứng dụng dùng Java 17+), JAR H2 JDBC driver trong classpath mà Tomcat resource factory nhìn thấy, và một web application được deploy vào Tomcat. Trong sản xuất, thay H2 bằng hệ quản trị thật và lưu credentials trong cơ chế quản lý bí mật của môi trường.

### 4.1. Khai báo `<Resource>` trong Context của ứng dụng

Một cách cấu hình Tomcat theo từng ứng dụng là đặt file `META-INF/context.xml` trong WAR (tùy deployment policy của server) hoặc cấu hình Context tương ứng tại phía container. Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Context>
    <Resource
        name="jdbc/LearningDB"
        auth="Container"
        type="javax.sql.DataSource"
        driverClassName="org.h2.Driver"
        url="jdbc:h2:mem:learning;DB_CLOSE_DELAY=-1"
        username="sa"
        password=""
        maxTotal="10"
        maxIdle="5"
        maxWaitMillis="10000"
        testOnBorrow="true"
        validationQuery="SELECT 1" />
</Context>
~~~

Ý nghĩa của từng thuộc tính:

| Thuộc tính | Vai trò |
| --- | --- |
| `name` | Tên resource tương đối trong ENC: `jdbc/LearningDB` |
| `auth="Container"` | Container cung cấp cơ chế xác thực tài nguyên theo cấu hình |
| `type="javax.sql.DataSource"` | Interface mà ứng dụng mong đợi khi lookup |
| `driverClassName` | Tên lớp JDBC driver; H2 phải có trên classpath phù hợp |
| `url` | JDBC URL thực tế; ở đây H2 in-memory cho bài thực hành |
| `username` / `password` | Tài khoản kết nối; mẫu `sa` và mật khẩu rỗng chỉ dành cho môi trường thực hành |
| `maxTotal` | Giới hạn tổng số connection đồng thời được pool cấp phát, theo pool implementation |
| `maxIdle` | Số connection nhàn rỗi tối đa mà pool giữ |
| `maxWaitMillis` | Thời gian chờ tối đa khi mượn connection, tính theo mili giây trong cấu hình pool này |
| `testOnBorrow` / `validationQuery` | Kiểm tra connection trước khi trao cho caller, với query ví dụ `SELECT 1` |

Các thuộc tính pool trong bảng thuộc resource factory mặc định phù hợp của Tomcat/DBCP ở cấu hình ví dụ, **không phải API chuẩn của `DataSource`**. JNDI provider hoặc server khác có thể dùng tên thuộc tính khác.

**Vị trí JDBC driver:** Với tài nguyên được tạo bởi Tomcat, đặt JAR JDBC driver ở nơi classloader của Tomcat có thể thấy, thường là thư mục `$CATALINA_BASE/lib` hoặc `$CATALINA_HOME/lib`. Chỉ khai báo dependency trong WAR có thể không đủ cho resource factory do container tạo. Nếu driver vắng mặt hoặc URL sai, lỗi kết nối có thể xảy ra ngay lúc pool được tạo hoặc chỉ khi mượn connection.

**Tính chất H2:** `jdbc:h2:mem:learning;DB_CLOSE_DELAY=-1` là database trong bộ nhớ phục vụ ví dụ, không đại diện cho lưu trữ bền vững. `DB_CLOSE_DELAY=-1` giúp database còn tồn tại khi connection cuối đóng trong cùng JVM; khi JVM dừng thì dữ liệu biến mất.

### 4.2. Khai báo contract trong `web.xml`

Có thể khai báo yêu cầu về tài nguyên trong `WEB-INF/web.xml` của WAR:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <resource-ref>
        <description>DataSource do container cung cấp</description>
        <res-ref-name>jdbc/LearningDB</res-ref-name>
        <res-type>javax.sql.DataSource</res-type>
        <res-auth>Container</res-auth>
    </resource-ref>
</web-app>
~~~

Trong Tomcat, nếu tài nguyên đã được định nghĩa hợp lệ trong `<Context>`, việc thêm `resource-ref` thường không bắt buộc để thực hiện lookup, nhưng hữu ích để **công bố dependency** của ứng dụng. Một container khác có thể cần cấu hình deployment descriptor hoặc cơ chế binding khác. Tên trong `res-ref-name` và tên đã công bố ở ENC phải khớp.

Không nhầm `<Resource>` trong Context (cấu hình container thực hiện) với `<resource-ref>` trong `web.xml` (yêu cầu của ứng dụng). Khai báo contract đơn thuần không bảo đảm có pool hoạt động nếu container chưa cung cấp tài nguyên tương ứng.

### 4.3. Tài nguyên global và ResourceLink

Tomcat còn hỗ trợ `<GlobalNamingResources>` trong `server.xml` để khai báo tài nguyên dùng ở phạm vi server. Một web application không tự động nhìn thấy mọi global resource; có thể cần `<ResourceLink>` trong Context của ứng dụng.

~~~xml
<Context>
    <ResourceLink
        name="jdbc/LearningDB"
        global="sharedLearningDataSource"
        type="javax.sql.DataSource" />
</Context>
~~~

Đoạn này **chỉ minh họa liên kết** đến resource global đã được quản trị viên định nghĩa tên `sharedLearningDataSource`; không tạo resource global mới. Ứng dụng vẫn lookup ở tên local `java:comp/env/jdbc/LearningDB`. Chia sẻ một pool giữa nhiều ứng dụng cần cân nhắc isolation, credentials, quota và tác động của từng ứng dụng tới pool.

## 5. Thử tra cứu bằng Java SE/JDBC trước khi tích hợp Spring

Mục tiêu của bước này là xác nhận ba điều độc lập: (1) tên JNDI tồn tại, (2) object thực sự là `DataSource`, và (3) có thể mượn connection thực thi SQL.

Lưu đoạn sau thành `JndiProbe.java`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public final class JndiProbe {
    public static void main(String[] args)
            throws NamingException, SQLException {
        InitialContext context = new InitialContext();
        DataSource dataSource = (DataSource)
                context.lookup("java:comp/env/jdbc/LearningDB");

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement("SELECT 1");
             ResultSet results = statement.executeQuery()) {
            if (!results.next()) {
                throw new IllegalStateException("Query returned no rows");
            }
            System.out.println("DB ready: " + results.getInt(1));
        }
    }
}
~~~

Cú pháp dùng các API có sẵn trong JDK; có thể **kiểm tra biên dịch** với Java 17 trở lên mà không cần thư viện Spring:

~~~bash
javac --release 17 JndiProbe.java
~~~

Khi đoạn `main` được gọi trong một **JVM có naming provider và binding JNDI hợp lệ**, với H2 và tài nguyên như cấu hình, kết quả kỳ vọng:

~~~text
DB ready: 1
~~~

Điều kiện chạy là bắt buộc: lệnh `java JndiProbe` từ một terminal thông thường **không tự kế thừa ENC của ứng dụng đang chạy trong Tomcat**, nên có thể thất bại trước khi lấy connection. Vì thế kiểm thử tích hợp đúng cách phải gọi code tra cứu trong runtime/container có JNDI context, ví dụ qua một endpoint/servlet hoặc một kiểm thử chạy trong container. Kết quả trên chỉ là kết quả **khi môi trường đã cấu hình đúng**, không phải đầu ra chắc chắn của một chương trình CLI độc lập.

`try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection`, ngay cả khi có ngoại lệ. Với pooled `DataSource`, `Connection.close()` thường trả connection logic về pool chứ không nhất thiết đóng socket vật lý. **Không giữ `Connection` lâu dài trong singleton bean hoặc dùng chung một Connection giữa các request.**

### Nhận biết lỗi theo tầng

- `new InitialContext().lookup(...)` thất bại → kiểm tra naming provider, namespace, tên resource, descriptor và thời điểm đăng ký JNDI.
- Lookup thành công nhưng kiểu object sai → kiểm tra `type`, resource factory và classloader/interface.
- `dataSource.getConnection()` thất bại → kiểm tra JDBC driver, database, credentials, network, TLS, timeout hoặc pool cạn.
- Lấy connection thành công nhưng SQL thất bại → kiểm tra cú pháp SQL, schema, quyền user và tính tương thích dialect.

Không bỏ qua lỗi bằng cách tạo một `DriverManagerDataSource` tạm thời ở production: làm vậy có thể che giấu sự cố cấu hình JNDI và thay đổi cơ chế quản lý connection/transaction ngoài chủ đích.

## 6. Tích hợp vào Spring Framework bằng JndiDataSourceLookup

Trong Spring, business code nên nhận bean `DataSource` qua constructor injection và không gọi JNDI trực tiếp ở mọi repository. Spring cung cấp `org.springframework.jdbc.datasource.lookup.JndiDataSourceLookup` để nhận một `DataSource` từ JNDI với kiểu dữ liệu đã kiểm tra.

### 6.1. Java-based configuration (Spring Framework 6+)

Ví dụ class `DataAccessConfig.java` trong application context của web app đã được triển khai lên container:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.lookup.JndiDataSourceLookup;

@Configuration
public class DataAccessConfig {

    @Bean
    public DataSource dataSource() {
        JndiDataSourceLookup lookup = new JndiDataSourceLookup();
        return lookup.getDataSource("jdbc/LearningDB");
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

Cần có các module Spring tương ứng như `spring-context`, `spring-jdbc` và dependency vận hành web application phù hợp. Đoạn class cấu hình này **không phải executable Java CLI**: nó cần một Spring application context trong container đã có tài nguyên JNDI.

Tại sao tên ngắn `jdbc/LearningDB` hợp lệ? Constructor của `JndiDataSourceLookup` bật `resourceRef=true`. Với tên tương đối chưa có scheme, Spring thêm prefix `java:comp/env/` để tìm `java:comp/env/jdbc/LearningDB`. Có thể cung cấp **tên đầy đủ** thay thế:

~~~java
return lookup.getDataSource("java:comp/env/jdbc/LearningDB");
~~~

Không đồng nhất hành vi này với mọi lớp JNDI của Spring: `JndiLocatorSupport` cơ sở mặc định `resourceRef=false`; chính `JndiDataSourceLookup` chọn mặc định phù hợp với DataSource trong ENC. Tên có scheme riêng không bị áp prefix theo cách tên tương đối.

Khi Spring tạo bean `dataSource`, nó lookup tài nguyên. Nếu tên không tồn tại, `getDataSource(...)` có thể ném `DataSourceLookupFailureException` (wrap `NamingException`), dẫn đến lỗi khởi tạo application context. Đây là tín hiệu hợp lý khi phụ thuộc hạ tầng bắt buộc không có. Cách trên chỉ thực hiện lookup khi khởi tạo bean, không tra cứu JNDI cho mỗi câu SQL.

### 6.2. Repository chỉ biết JdbcTemplate

Ví dụ `DatabaseCheckRepository.java` trong ứng dụng có component scanning phù hợp:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DatabaseCheckRepository {
    private final JdbcTemplate jdbcTemplate;

    public DatabaseCheckRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int probe() {
        Integer value =
                jdbcTemplate.queryForObject("SELECT 1", Integer.class);
        if (value == null) {
            throw new IllegalStateException("Database returned NULL");
        }
        return value;
    }
}
~~~

Với H2 trong ví dụ, `probe()` trả `1`. `JdbcTemplate` mượn connection thông qua Spring JDBC, tạo và đóng JDBC resource; repository không cần biết URL và cách lookup. Nếu chạy với Spring-managed transaction, `JdbcTemplate` dùng cơ chế `DataSourceUtils` để tham gia connection đang gắn với transaction đúng context.

Ví dụ cho thấy *wiring*, không bảo đảm ứng dụng sẽ tự chạy chỉ từ hai class. Cần WAR/container deployment, Spring context, dependency, pool và database đã cấu hình như các phần trước.

## 7. Cách khai báo bean khác: JndiObjectFactoryBean

Spring còn có `org.springframework.jndi.JndiObjectFactoryBean`: một `FactoryBean` tìm một object JNDI và phơi bày object đó dưới dạng bean Spring. Có thể dùng khi muốn tích hợp một tài nguyên JNDI bằng XML hoặc cấu hình lookup có nhiều tùy chọn.

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jndi.JndiObjectFactoryBean;

@Configuration
public class AlternativeJndiConfig {
    @Bean
    public JndiObjectFactoryBean dataSource() {
        JndiObjectFactoryBean factory = new JndiObjectFactoryBean();
        factory.setJndiName("java:comp/env/jdbc/LearningDB");
        factory.setExpectedType(DataSource.class);
        return factory;
    }
}
~~~

Đây là **phương án thay thế** cho bean `dataSource()` trong phần 6, không khai báo cả hai bean trùng tên trong cùng application context. Khi các thành phần inject `DataSource`, Spring giải quyết object mà `FactoryBean` cung cấp, không yêu cầu repository phụ thuộc trực tiếp `JndiObjectFactoryBean`.

Các lựa chọn nâng cao của `JndiObjectFactoryBean`:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `jndiName` | Tên JNDI cần lookup |
| `expectedType` | Kiểu object mong đợi, ví dụ `DataSource.class` |
| `resourceRef` | Nếu bật, tên tương đối được định hướng về `java:comp/env/` |
| `lookupOnStartup` | Mặc định `true`: lookup trong giai đoạn khởi tạo bean |
| `cache` | Mặc định `true`: giữ kết quả lookup |
| `proxyInterface` | Interface proxy cần thiết cho các cách cấu hình lazy lookup/hot redeploy phù hợp |

Nếu cần hoãn lookup:

~~~java
factory.setJndiName("jdbc/LearningDB");
factory.setResourceRef(true);
factory.setExpectedType(DataSource.class);
factory.setLookupOnStartup(false);
factory.setProxyInterface(DataSource.class);
~~~

Đây là **thay đổi hành vi**: ứng dụng có thể tạo bean proxy trước khi tài nguyên JNDI sẵn sàng; lỗi sẽ xuất hiện khi sử dụng thực tế nếu binding vẫn vắng mặt. Không bật lazy lookup để “giấu” lỗi cấu hình; dùng nó chỉ khi có nhu cầu triển khai tài nguyên muộn rõ ràng. `cache=false` có thể khiến lookup xảy ra nhiều lần theo proxy invocation, không có nghĩa là tự động cân bằng tải hoặc quản lý pool.

## 8. Nếu dùng Spring Boot triển khai vào application server

Spring Boot có lựa chọn cấu hình JNDI DataSource bằng property, thay cho việc tự khai báo `@Bean DataSource`:

~~~yaml
spring:
  datasource:
    jndi-name: "java:comp/env/jdbc/LearningDB"
~~~

Trong môi trường Boot có auto-configuration JDBC phù hợp, property `spring.datasource.jndi-name` chỉ định nơi lấy `DataSource`. Khi chọn JNDI, các cấu hình tạo DataSource trực tiếp như `spring.datasource.url`, `username` và `password` không còn là nguồn cung cấp DataSource theo đường auto-configuration này.

Điều kiện rất quan trọng: **property không tạo resource JNDI**. Nếu server không bind tên đó, ứng dụng vẫn không kết nối được. Một executable JAR dùng embedded servlet container **không mặc nhiên có ENC/pool cấu hình giống WAR trên external Tomcat**; phải có cơ chế đăng ký JNDI riêng nếu thực sự muốn dùng JNDI.

Cấu hình bean thủ công ở phần 6 và cấu hình Boot property ở phần này là **hai cách thay thế**. Khi đã định nghĩa custom `DataSource` bean, cần hiểu auto-configuration sẽ back off/được điều chỉnh thế nào; tránh thêm cả hai mà không có chủ ý, vì có thể khiến dependency injection và quản lý pool/transaction khó xác định.

Bài học không yêu cầu Spring Boot: bản chất việc tra cứu JNDI nằm ở Java naming API, DataSource interface, container và cơ chế wiring của Spring.

## 9. Ai sở hữu pool, vòng đời và cấu hình?

Với mô hình container-managed trong bài, **container tạo/đóng pool** theo vòng đời ứng dụng hoặc server, tùy cách scope tài nguyên. Spring có thể chỉ giữ tham chiếu tới `DataSource` để sử dụng; việc Spring application context đóng **không đồng nghĩa** Spring sở hữu pool để tự gọi `close()`.

Phân biệt ba thao tác:

1. **Lookup**: lấy object DataSource từ JNDI. Thường thực hiện một lần trong quá trình khởi tạo bean.
2. **Borrow connection**: gọi `dataSource.getConnection()` khi cần thực hiện JDBC; có thể đợi nếu pool cạn.
3. **Release connection**: đóng connection logic đúng cách sau thao tác/transaction để pool có thể dùng lại.

Cả khi object `DataSource` là singleton, **không** suy ra có một `Connection` duy nhất. Một singleton `DataSource` có thể đồng thời cho nhiều thread mượn các connection khác nhau. Một connection đơn lẻ không nên được chia sẻ tùy ý giữa request/thread.

### Cấu hình theo môi trường và quản lý bí mật

Ví dụ các môi trường khác nhau có cùng tên local:

| Môi trường | JNDI name mà ứng dụng dùng | Cấu hình thật ở container |
| --- | --- | --- |
| Development | `jdbc/LearningDB` | H2 hoặc database thử nghiệm |
| Staging | `jdbc/LearningDB` | Database staging, quyền truy cập giới hạn |
| Production | `jdbc/LearningDB` | Database production, TLS/pool/giám sát theo chính sách |

Ứng dụng **không phải thay đổi business code** khi các môi trường xuất bản tài nguyên thống nhất tên và contract. Tuy nhiên, schema, dialect và transaction semantics vẫn cần tương thích; chỉ trùng JNDI name không bảo đảm mọi hành vi database giống nhau.

Credentials production không nên commit vào `context.xml` nằm trong mã nguồn. Tùy nền tảng, dùng hệ thống secrets/credential store, cấu hình container ngoài artifact và phân quyền phù hợp. Giảm quyền database user theo chức năng; tránh log mật khẩu hoặc thông tin kết nối nhạy cảm. Một JNDI binding không phải cơ chế kiểm soát truy cập database đầy đủ.

## 10. JNDI DataSource và transaction: không đánh đồng hai loại “managed”

“Môi trường được quản lý” dễ gây nhầm lẫn vì **container-managed DataSource** (container cung cấp pool) và **container-managed transaction/JTA** (container điều phối transaction) là hai quyết định riêng.

### Trường hợp A — Container cung cấp pool, Spring quản lý JDBC transaction cục bộ

Nếu ứng dụng sử dụng một non-JTA DataSource từ container và muốn Spring quản lý JDBC transaction, có thể cấu hình transaction manager của Spring cho DataSource đó, ví dụ `JdbcTransactionManager` hoặc `DataSourceTransactionManager`:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LocalJdbcTransactionConfig {
    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Đây là ví dụ wiring bổ sung cho DataSource ở phần 6, dùng khi kiến trúc đã chọn **local JDBC transaction**. Service có thể dùng `@Transactional` khi transaction management được bật/thiết lập đúng. Spring JDBC lấy connection nhất quán từ `DataSourceUtils`; thực hiện SQL bằng `JdbcTemplate` giúp tham gia transaction hiện hành. Với code JDBC tự viết, phải chú ý dùng `DataSourceUtils` hoặc cơ chế Spring tương đương, tránh vô tình lấy connection khác ngoài transaction.

### Trường hợp B — Container/JTA quản lý distributed transaction

Nếu tài nguyên thuộc transaction do application server quản lý, hoặc một transaction cần phối hợp nhiều tài nguyên XA, có thể cần `JtaTransactionManager` cùng cấu hình JTA của môi trường:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.jta.JtaTransactionManager;

@Configuration
public class ManagedTransactionConfig {
    @Bean
    public PlatformTransactionManager transactionManager() {
        return new JtaTransactionManager();
    }
}
~~~

Đây là mô hình cấu hình minh họa, **không đủ để tự cung cấp JTA coordinator**. Application server phải hỗ trợ và cấu hình JTA thích hợp; không phải Tomcat mặc định nào cũng cung cấp đầy đủ JTA transaction coordinator. Trong hệ thống cụ thể, có thể cần cấu hình transaction manager theo vendor/server.

**Quy tắc:** Nếu Spring tự quản lý JDBC transaction bằng non-JTA manager, dùng DataSource không bị container tự động quản lý transaction JTA trên cùng kết nối theo cách xung đột. Nếu container quản lý JTA, chọn transaction manager tích hợp JTA và tài nguyên phù hợp. **Có tên JNDI không tự nói lên nên dùng transaction manager nào.**

## 11. Kiểm thử theo lớp, từ container đến repository

Một trình tự kiểm chứng hợp lý:

1. **Xác nhận deployment:** Web application chạy trong Tomcat/application server dự kiến; file Context thực sự được nạp theo chính sách deploy của server.
2. **Xác nhận tên:** Namespace đã đăng ký `jdbc/LearningDB`, phân biệt tên tương đối và tên đầy đủ.
3. **Xác nhận kiểu:** Lookup trả về object tương thích `javax.sql.DataSource`. Nếu dùng Spring, bean `DataSource` có thể được resolve khi context khởi tạo.
4. **Xác nhận connection:** Dùng query đơn giản `SELECT 1` trong môi trường container. Kết quả ví dụ với H2 là `1`.
5. **Xác nhận JDBC/Spring:** Gọi `DatabaseCheckRepository.probe()` và kiểm tra trả `1` trong test triển khai thực tế.
6. **Xác nhận pool:** Quan sát active/idle connection, thời gian chờ, timeout và hành vi khi nhiều request đồng thời; hoàn trả connection bằng cơ chế đóng đúng.
7. **Xác nhận transaction:** Kiểm tra rollback khi lỗi ở nhiều thao tác ghi; đặc biệt khi sử dụng `@Transactional` và container/JTA.

Nếu thiếu naming provider trong unit test chạy ngoài container, có thể **inject DataSource thử nghiệm riêng** (ví dụ H2 được tạo bởi test configuration) vào repository để kiểm tra logic SQL. Đây là unit/integration test Spring JDBC không phải phép thử JNDI. Muốn chứng minh binding JNDI hoạt động thì cần môi trường JNDI thực hoặc một naming provider kiểm thử được cấu hình có chủ đích.

Khi kiểm thử mã JNDI thật, cần dùng đúng runtime classpath và lifecycle. Không mặc định Spring tạo tài nguyên JNDI giúp ứng dụng chỉ vì trong project có `spring-jdbc`.

## 12. Bảng chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách tiếp cận |
| --- | --- | --- |
| `NoInitialContextException` | Chạy ngoài môi trường có provider; cấu hình naming chưa tồn tại | Xác nhận app đang chạy bên trong container/naming provider hợp lệ |
| `NameNotFoundException` | Sai tên, sai namespace, Context thiếu `<Resource>` hoặc `<ResourceLink>` | Đối chiếu tên local `jdbc/LearningDB` với full name `java:comp/env/jdbc/LearningDB` |
| `DataSourceLookupFailureException` lúc start Spring | JNDI lookup thất bại | Đọc root cause `NamingException`, kiểm tra thứ tự khởi tạo và cấu hình container |
| `ClassCastException` hoặc type mismatch | Resource không phải `DataSource` hoặc classloader/type sai | Kiểm tra `type="javax.sql.DataSource"`, factory và jar/classloader |
| `ClassNotFoundException: org.h2.Driver` | JDBC driver không khả dụng với pool factory | Đưa driver vào classpath phù hợp của Tomcat, kiểm tra version |
| `SQLException` khi `getConnection()` | URL, credentials, quyền, network, TLS, pool cạn hoặc DB ngừng chạy | Kiểm tra JDBC URL thật, log pool/driver, timeout và quyền truy cập |
| Lookup thành công nhưng chậm khi tải lớn | Pool thiếu connection, giữ connection quá lâu, query chậm | Quan sát active/idle/wait time và truy vấn, đóng resource kịp thời |
| `@Transactional` không rollback như mong đợi | Dùng sai transaction manager, connection không tham gia transaction | Xác minh local vs JTA transaction, `DataSourceUtils` và ranh giới proxy |
| Chạy tốt trên WAR, lỗi ở executable JAR | Khác biệt naming provider và config container | Chọn cấu hình DataSource phù hợp từng packaging/runtime |
| DB ngắt kết nối sau thời gian idle | Connection cũ/timeout của mạng hoặc server, pool validation chưa phù hợp | Điều chỉnh validation/eviction/lifetime theo pool và đặc tính DB |

Luôn bắt đầu từ **root cause** và tầng lỗi thực tế. Đừng chẩn đoán mọi lỗi JNDI là lỗi database: nhiều trường hợp lookup chưa hề trả về `DataSource`, nên JDBC driver và câu SQL chưa được gọi.

## 13. Các sai lầm cần tránh

**Sai 1 — Nhầm JNDI name với JDBC URL.**

~~~text
JNDI: java:comp/env/jdbc/LearningDB
JDBC: jdbc:h2:mem:learning;DB_CLOSE_DELAY=-1
~~~

JNDI chọn tài nguyên theo tên; JDBC URL dùng cho driver kết nối database. Hai chuỗi có tiền tố `jdbc` nhưng phục vụ hai tầng khác nhau.

**Sai 2 — Tạo pool thứ hai sau khi đã lookup DataSource.** Nếu container đã tạo pooled DataSource, bọc nó trong một pool độc lập khác có thể gây double pooling, khó kiểm soát connection và timeout. Chỉ thêm proxy/wrapper khi hiểu rõ mục đích như transaction-aware hoặc lazy connection, không tự cho rằng lookup JNDI trả về connection đơn lẻ.

**Sai 3 — Đặt tên ngắn vào API không tự thêm ENC prefix.** `new InitialContext().lookup("jdbc/LearningDB")` không giống `JndiDataSourceLookup.getDataSource("jdbc/LearningDB")`. Với `InitialContext` trực tiếp, hãy lookup full name hoặc lấy ENC context trước. Với `JndiDataSourceLookup`, constructor bật `resourceRef`, nên tên tương đối được chuyển thành ENC name.

**Sai 4 — Quên close Connection.** Khi JDBC resource không được giải phóng, pool có thể cạn dần. Dùng `try-with-resources` hoặc `JdbcTemplate`, không giữ connection ở field của singleton/repository.

**Sai 5 — Cho rằng JNDI tự tạo transaction và pooling.** Lookup chỉ lấy object; hành vi pool, local/JTA transaction, retry và recovery đến từ implementation và cấu hình liên quan.

**Sai 6 — Mặc định mọi server giống Tomcat.** Cách cấu hình XML, classloader, namespace, driver placement, pool attribute và JTA khác theo Tomcat, WildFly/JBoss, WebLogic và các môi trường khác. Có thể giữ nguyên interface Java `DataSource`, nhưng phần vận hành phải theo tài liệu của server thật.

**Sai 7 — Trộn hai chiến lược DataSource.** Dùng đồng thời Boot auto-config JNDI, custom bean, Hikari pool app-managed và container pool mà không xác định bean thực sự được inject dễ gây lỗi khó tìm. Hãy chọn cấu hình rõ ràng theo mô hình triển khai.

**Sai 8 — Không tách kiểm thử nghiệp vụ và kiểm thử JNDI.** Một unit test repository có thể dùng DataSource test độc lập; chỉ integration test trong naming environment mới xác nhận được resource JNDI. Hai loại test trả lời những câu hỏi khác nhau.

## 14. Bài tập áp dụng

1. **Giải thích đường đi:** Với khai báo `<Resource name="jdbc/LearningDB">` trong Tomcat, hãy viết full name để `InitialContext.lookup(...)` truy vấn và name ngắn để `JndiDataSourceLookup.getDataSource(...)` truy vấn.  
   **Đáp án:** `java:comp/env/jdbc/LearningDB` và `jdbc/LearningDB`.

2. **Chọn nơi cấu hình:** Nếu đổi DB staging sang PostgreSQL nhưng giữ nguyên tên `jdbc/LearningDB`, nên chỉnh tầng nào trước?  
   **Đáp án:** Cấu hình resource/container (driver, URL, credentials, pool) và schema/migration tương thích. Repository chỉ phụ thuộc `DataSource` nên không cần thay vì đổi JNDI binding.

3. **Phân tích lỗi:** `JndiDataSourceLookup` ném `DataSourceLookupFailureException` khi khởi động. Có nên sửa JDBC URL trong repository ngay không?  
   **Đáp án:** Chưa. Trước hết kiểm tra root cause của lookup, container và tên JNDI. Khi lookup chưa trả về DataSource, code repository có thể chưa chạy.

4. **Vòng đời connection:** Vì sao `try (Connection conn = ds.getConnection())` vẫn cần thiết nếu connection được pool quản lý?  
   **Đáp án:** `close()` giải phóng connection logic về pool để request khác có thể mượn; bỏ close làm cạn pool.

5. **Transaction:** Một DataSource xuất hiện trong JNDI có chứng minh server đang quản lý mọi transaction bằng JTA không?  
   **Đáp án:** Không. Cần xác minh loại resource và kiến trúc transaction. Local Spring JDBC transaction và JTA có transaction manager/configuration riêng.

6. **Kiểm thử:** Unit test `DatabaseCheckRepository` inject H2 DataSource và trả `1`. Test này chứng minh điều gì, và chưa chứng minh điều gì?  
   **Đáp án:** Nó chứng minh repository/JdbcTemplate truy vấn được H2 test DB; chưa chứng minh JNDI resource tồn tại trong container của môi trường triển khai.

## 15. Điểm cần nhớ

- **JNDI là cơ chế tra cứu theo tên**; tài nguyên được trả về ở bài này là một object `javax.sql.DataSource` do container quản lý.
- **Tên JNDI và JDBC URL khác nhau**; ứng dụng sử dụng tên logic, container nắm thông tin kết nối/pool.
- Với Tomcat, `jdbc/LearningDB` trong Context xuất hiện ở `java:comp/env/jdbc/LearningDB`; quy tắc tên cần được kiểm tra theo server thực tế.
- `JndiDataSourceLookup` hoặc `JndiObjectFactoryBean` giúp tạo bean Spring từ tài nguyên JNDI; repository tiếp tục dùng `JdbcTemplate` qua dependency injection.
- Pool lifecycle, việc trả connection và loại transaction manager phải được xác định rõ. **JNDI DataSource không mặc nhiên đồng nghĩa JTA.**
- Test unit cho repository và test integration cho JNDI là hai lớp kiểm chứng khác nhau.

### Tài liệu tham khảo chính thức

- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): cách Spring sử dụng DataSource, JdbcTemplate, DataSourceUtils và transaction-aware access.
- [Spring Framework — JndiDataSourceLookup API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/lookup/JndiDataSourceLookup.html): lookup DataSource qua JNDI.
- [Spring Framework — JndiObjectFactoryBean API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jndi/JndiObjectFactoryBean.html): lookup lúc startup, cache và proxy.
- [Apache Tomcat 10.1 — JNDI Resources How-To](https://tomcat.apache.org/tomcat-10.1-doc/jndi-resources-howto.html): khai báo Context, resource-ref, cách sử dụng DataSource.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình `spring.datasource.jndi-name` khi ứng dụng chạy trên application server.