# Cấu hình JPA bằng Java khi không dùng Spring Boot

Spring Data JPA có thể chạy trong một ứng dụng Spring Framework thông thường mà không cần Spring Boot. Khi không dùng Boot, bạn vẫn sử dụng được Spring IoC container, Spring Data repositories, JPA và Hibernate; tuy nhiên, bạn phải tự khai báo các thành phần hạ tầng mà Boot thường tự cấu hình.

Bài này trình bày cách cấu hình bằng Java Configuration: tạo DataSource, khởi tạo EntityManagerFactory, đăng ký transaction manager, bật quét repository và component, rồi khởi chạy Spring ApplicationContext. Ví dụ dùng Hibernate làm JPA provider và H2 làm cơ sở dữ liệu để có thể chạy thử độc lập.

## 1. Phân biệt các thành phần

Trước khi cấu hình, cần hiểu vai trò của từng thư viện:

- **Jakarta Persistence (JPA)** là đặc tả quy định API và quy tắc ORM: entity, mapping, persistence context, EntityManager và các thao tác persistence.
- **Hibernate ORM** là một implementation của JPA. Nó đọc metadata entity, tạo SQL và giao tiếp với database thông qua JDBC.
- **Spring Framework** cung cấp IoC container, dependency injection, quản lý bean, tích hợp transaction và hỗ trợ tích hợp JPA.
- **Spring Data JPA** xây dựng abstraction repository trên JPA. Nó tạo implementation cho các interface repository và cung cấp derived query, paging, sorting cùng nhiều tiện ích khác.
- **DataSource** cung cấp kết nối JDBC. Ứng dụng thường dùng connection pool như HikariCP để tái sử dụng kết nối.
- **EntityManagerFactory** tạo EntityManager. Nó được khởi tạo một lần cho mỗi persistence unit và thường tồn tại trong suốt vòng đời ứng dụng.
- **EntityManager** thực hiện thao tác với entity trong một persistence context.
- **PlatformTransactionManager** kết nối cơ chế transaction của Spring với transaction của JPA.

Spring Data JPA không tự thay thế JPA provider hay database. Repository gọi vào JPA; provider như Hibernate chuyển thao tác thành SQL; JDBC driver gửi SQL đến database.

## 2. Không dùng Spring Boot thì cần tự cấu hình những gì?

Trong ứng dụng Spring Boot, các starter, auto-configuration và externalized configuration giúp tự động tạo nhiều bean dựa trên dependency và cấu hình. Khi không dùng Boot, bạn phải chủ động đăng ký:

1. Dependency của Spring Framework, Spring Data JPA, JPA provider và JDBC driver.
2. Một DataSource trỏ đến database.
3. Một LocalContainerEntityManagerFactoryBean để xây dựng EntityManagerFactory.
4. JPA vendor adapter và các thuộc tính Hibernate/JPA.
5. Một JpaTransactionManager.
6. Cơ chế quét repository bằng @EnableJpaRepositories.
7. Cơ chế quét service và component bằng @ComponentScan hoặc khai báo bean tường minh.
8. ApplicationContext để khởi chạy và quản lý vòng đời các bean.

Luồng khởi tạo có thể hình dung như sau:

~~~text
AnnotationConfigApplicationContext
             |
             v
       Java @Configuration
             |
      +------+----------------+
      |                       |
      v                       v
   DataSource          EntityManagerFactory
                              |
                              v
                       Spring Data JPA
                       Repository proxies
                              |
                              v
                       JpaTransactionManager
~~~

DataSource phải được cung cấp trước khi EntityManagerFactory có thể khởi tạo. Repository cần EntityManagerFactory để tạo implementation. Transaction manager cần EntityManagerFactory để điều phối transaction.

## 3. Chuẩn bị dependency

Ví dụ dưới đây dùng Java 17+, Spring Framework 6.1.13, Spring Data JPA 3.3.4, Hibernate ORM 6.5.3.Final, HikariCP 5.1.0 và H2 2.3.232. Đây là một bộ phiên bản minh họa có cùng thế hệ Jakarta; khi bắt đầu dự án mới, hãy chọn các phiên bản Spring Framework, Spring Data và Hibernate theo compatibility matrix của Spring Data release train đang sử dụng.

Các dependency cần có:

| Artifact | Mục đích |
|---|---|
| spring-context | ApplicationContext, @Configuration, @ComponentScan |
| spring-orm | LocalContainerEntityManagerFactoryBean và JpaTransactionManager |
| spring-jdbc | Tích hợp DataSource và JDBC |
| spring-data-jpa | JpaRepository và @EnableJpaRepositories |
| hibernate-core | JPA provider |
| jakarta.persistence-api | Các annotation và API JPA |
| HikariCP | Connection pool |
| H2 | Database in-memory cho ví dụ |
| slf4j-simple | Logging provider đơn giản cho ví dụ |

Ví dụ Maven tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>jpa-without-boot</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.1.13</spring-framework.version>
        <spring-data-jpa.version>3.3.4</spring-data-jpa.version>
        <hibernate.version>6.5.3.Final</hibernate.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-orm</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-jpa</artifactId>
            <version>${spring-data-jpa.version}</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-core</artifactId>
            <version>${hibernate.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.persistence</groupId>
            <artifactId>jakarta.persistence-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.16</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không có spring-boot-starter hay plugin Spring Boot trong project này. Các dependency được khai báo trực tiếp để bạn nhìn rõ những thành phần mà ứng dụng sử dụng.

## 4. Tổ chức package cho ví dụ

Có thể tổ chức mã nguồn như sau:

~~~text
src/main/java/
└── example/
    ├── Main.java
    ├── config/
    │   └── JpaConfig.java
    ├── domain/
    │   └── Customer.java
    ├── repository/
    │   └── CustomerRepository.java
    └── service/
        └── CustomerService.java

src/main/resources/
└── application.properties
~~~

Trong ví dụ:

- **config** chứa cấu hình Spring và persistence.
- **domain** chứa entity.
- **repository** chứa interface Spring Data JPA.
- **service** chứa logic nghiệp vụ.
- **Main** khởi tạo ApplicationContext.
- **application.properties** chứa thông tin kết nối database.

## 5. Khai báo cấu hình kết nối database

Tạo file **src/main/resources/application.properties**:

~~~properties
app.datasource.driver-class-name=org.h2.Driver
app.datasource.url=jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1
app.datasource.username=sa
app.datasource.password=
~~~

H2 chạy trong bộ nhớ nên ví dụ không cần cài database server. Tham số **DB_CLOSE_DELAY=-1** giữ database in-memory tồn tại cho đến khi JVM kết thúc, kể cả khi một kết nối tạm thời đóng.

Trong môi trường thật, URL, username và password cần lấy từ cấu hình môi trường hoặc secret manager. Không commit mật khẩu production vào repository.

Khi không dùng Boot, **@PropertySource** có thể nạp file properties và Spring **Environment** đọc giá trị. Bạn cũng có thể tự đăng ký một **PropertySource** khác hoặc dùng system properties và environment variables.

## 6. Tạo Java Configuration cho JPA

Đây là phần quan trọng nhất. Tạo file **JpaConfig.java**:

~~~java
package example.config;

import example.domain.Customer;
import example.repository.CustomerRepository;
import example.service.CustomerService;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import javax.sql.DataSource;
import java.util.Properties;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:application.properties")
@ComponentScan(basePackageClasses = CustomerService.class)
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class,
    entityManagerFactoryRef = "entityManagerFactory",
    transactionManagerRef = "transactionManager"
)
public class JpaConfig {

    @Bean(destroyMethod = "close")
    public HikariDataSource dataSource(Environment environment) {
        HikariConfig config = new HikariConfig();

        config.setDriverClassName(
            environment.getRequiredProperty(
                "app.datasource.driver-class-name"
            )
        );
        config.setJdbcUrl(
            environment.getRequiredProperty("app.datasource.url")
        );
        config.setUsername(
            environment.getRequiredProperty("app.datasource.username")
        );
        config.setPassword(
            environment.getProperty("app.datasource.password", "")
        );

        config.setMaximumPoolSize(5);
        config.setMinimumIdle(1);

        return new HikariDataSource(config);
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean entityManagerFactory(
        DataSource dataSource
    ) {
        LocalContainerEntityManagerFactoryBean factory =
            new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan(Customer.class.getPackageName());
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());

        Properties properties = new Properties();
        properties.setProperty("hibernate.hbm2ddl.auto", "create-drop");
        properties.setProperty("hibernate.show_sql", "false");
        properties.setProperty("hibernate.jdbc.time_zone", "UTC");

        factory.setJpaProperties(properties);

        return factory;
    }

    @Bean
    public PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory
    ) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Phân tích từng phần:

### 6.1. @Configuration

**@Configuration** đánh dấu class chứa các phương thức khai báo bean. Spring đọc metadata của class và gọi các phương thức **@Bean** để đăng ký object vào ApplicationContext.

**proxyBeanMethods = false** tắt cơ chế proxy giữa các phương thức **@Bean** trong class cấu hình. Ở ví dụ này, mỗi bean nhận dependency qua tham số phương thức nên không cần gọi trực tiếp một phương thức **@Bean** khác.

### 6.2. @PropertySource và Environment

**@PropertySource("classpath:application.properties")** nạp file cấu hình vào Environment.

Spring inject Environment vào phương thức **dataSource()**. Phương thức này đọc URL, username, password và driver bằng **getRequiredProperty()** hoặc **getProperty()**.

- **getRequiredProperty()** ném lỗi nếu thuộc tính bắt buộc không tồn tại.
- **getProperty(key, defaultValue)** trả giá trị mặc định khi thuộc tính không có.

Cách này giúp tách cấu hình khỏi mã nguồn. Trong môi trường production, có thể cung cấp giá trị bằng system properties hoặc environment variables. Ví dụ, biến môi trường **APP_DATASOURCE_URL** có thể được ánh xạ tới thuộc tính **app.datasource.url** bởi SystemEnvironmentPropertySource mặc định của Spring.

### 6.3. DataSource và HikariCP

**DataSource** là abstraction JDBC cung cấp connection. HikariCP triển khai DataSource và quản lý connection pool.

Các tham số trong ví dụ:

- **setJdbcUrl()** khai báo JDBC URL.
- **setUsername()** và **setPassword()** khai báo tài khoản kết nối.
- **setDriverClassName()** chỉ định JDBC driver.
- **setMaximumPoolSize(5)** giới hạn số connection tối đa của pool.
- **setMinimumIdle(1)** đặt số connection nhàn rỗi tối thiểu.

Kích thước pool phải được chọn theo tải ứng dụng, giới hạn connection của database và số instance ứng dụng. Không nên tăng pool tùy ý vì mỗi connection cũng tiêu thụ tài nguyên ở database.

**@Bean(destroyMethod = "close")** yêu cầu Spring đóng HikariDataSource khi ApplicationContext đóng. Nhờ đó pool giải phóng connection đúng vòng đời.

### 6.4. LocalContainerEntityManagerFactoryBean

Đây là FactoryBean của Spring dùng để tạo và quản lý JPA EntityManagerFactory.

Các cấu hình quan trọng:

- **setDataSource(dataSource)** kết nối persistence unit với DataSource.
- **setPackagesToScan(...)** chỉ định package chứa entity cần được phát hiện.
- **setJpaVendorAdapter(...)** khai báo adapter cho JPA provider.
- **setJpaProperties(...)** truyền các thuộc tính riêng của provider hoặc JPA.

**HibernateJpaVendorAdapter** giúp Spring ORM tích hợp với Hibernate. Ở ví dụ này, Hibernate có thể tự nhận diện dialect dựa trên JDBC metadata do H2 cung cấp. Với các trường hợp đặc biệt, có thể cấu hình dialect tường minh bằng thuộc tính **hibernate.dialect**.

Tên phương thức **entityManagerFactory** cũng là tên bean mặc định mà Spring Data JPA mong đợi. Nếu đổi tên bean, cần cập nhật **entityManagerFactoryRef** tương ứng.

### 6.5. Thuộc tính Hibernate

**hibernate.hbm2ddl.auto** điều khiển việc Hibernate xử lý schema:

- **create**: tạo lại schema khi khởi động.
- **create-drop**: tạo schema khi khởi động và xóa khi SessionFactory/EntityManagerFactory đóng.
- **update**: cố gắng điều chỉnh schema theo mapping.
- **validate**: kiểm tra schema có phù hợp mapping hay không.
- **none**: không tự động tạo, cập nhật hoặc kiểm tra schema.

Ví dụ dùng **create-drop** để thuận tiện cho database in-memory. Với production, thường dùng Flyway hoặc Liquibase để quản lý migration và đặt Hibernate ở chế độ **validate** hoặc **none**. Không nên dựa vào **update** như công cụ migration production vì thay đổi schema cần được kiểm soát và review.

**hibernate.show_sql=false** tắt việc in SQL trực tiếp từ Hibernate. Khi cần debug, có thể bật logging phù hợp cho Hibernate SQL và bind parameter; cần tránh để lộ dữ liệu nhạy cảm trong log production.

**hibernate.jdbc.time_zone=UTC** yêu cầu Hibernate dùng UTC cho các thao tác JDBC liên quan thời gian ở những kiểu được hỗ trợ. Ứng dụng vẫn cần thống nhất quy tắc biểu diễn thời gian trong domain và database.

### 6.6. JpaTransactionManager

**JpaTransactionManager** triển khai **PlatformTransactionManager** và quản lý transaction cho một JPA EntityManagerFactory.

Bean có tên **transactionManager** là tên mặc định được Spring Data JPA và cơ chế transaction tìm kiếm. Annotation **@EnableTransactionManagement** kích hoạt xử lý **@Transactional** thông qua proxy của Spring.

Nếu ứng dụng có nhiều EntityManagerFactory hoặc nhiều database, thường cần khai báo transaction manager riêng và chỉ rõ repository nào dùng persistence unit nào.

## 7. Bật quét Repository và Component

Trong class cấu hình:

**@EnableJpaRepositories(basePackageClasses = CustomerRepository.class)** yêu cầu Spring Data JPA quét package chứa interface marker CustomerRepository và tạo implementation proxy cho các repository tìm thấy.

Bạn không cần tự viết class implement JpaRepository. Spring Data tạo bean repository trong lúc khởi tạo ApplicationContext.

**@ComponentScan(basePackageClasses = CustomerService.class)** yêu cầu Spring quét package chứa service marker để tìm các bean như **@Service**, **@Component** và **@Repository** thông thường.

Entity được tìm qua **setPackagesToScan()** của EntityManagerFactory. Đây là cơ chế riêng, không đồng nghĩa với component scan.

Ba phạm vi quét cần được cấu hình đúng:

| Cơ chế | Tìm thành phần |
|---|---|
| @ComponentScan | Service, component và các bean Spring khác |
| @EnableJpaRepositories | Interface Spring Data repository |
| setPackagesToScan | JPA entity |

Nếu package không nằm trong phạm vi quét, bean hoặc entity tương ứng sẽ không được phát hiện. Dùng **basePackageClasses** giúp tránh phụ thuộc vào chuỗi package viết tay và dễ đổi tên package hơn.

## 8. Tạo Entity và Repository

Tạo entity **Customer.java**:

~~~java
package example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
        // JPA cần constructor không tham số với visibility phù hợp.
    }

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getName() {
        return name;
    }
}
~~~

Entity phải được đặt trong package mà EntityManagerFactory quét. JPA dùng annotation để ánh xạ class và field với bảng, cột, khóa chính và chiến lược sinh ID.

Tạo **CustomerRepository.java**:

~~~java
package example.repository;

import example.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
    extends JpaRepository<Customer, Long> {

    boolean existsByEmail(String email);
}
~~~

Spring Data JPA sẽ tạo implementation cho interface này. **JpaRepository<Customer, Long>** xác định entity là Customer và kiểu ID là Long. Phương thức **existsByEmail** là derived query: Spring Data phân tích tên method để xây dựng truy vấn kiểm tra email.

## 9. Tạo Service và dùng transaction

Tạo **CustomerService.java**:

~~~java
package example.service;

import example.domain.Customer;
import example.repository.CustomerRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email, String name) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }

        if (repository.existsByEmail(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        return repository.save(new Customer(email, name));
    }

    @Transactional(readOnly = true)
    public long count() {
        return repository.count();
    }
}
~~~

Constructor injection giúp dependency được thể hiện rõ và thuận tiện cho unit test. Service không tự tạo repository bằng **new**; Spring cung cấp repository bean đã được Spring Data JPA tạo.

**@Transactional** trên **register()** tạo ranh giới transaction cho thao tác nghiệp vụ. Việc kiểm tra email và lưu Customer tham gia transaction do service quản lý.

**@Transactional(readOnly = true)** thể hiện phương thức chỉ đọc. Đây là gợi ý cho transaction manager và provider; không nên coi nó là cơ chế bảo vệ tuyệt đối ngăn mọi câu lệnh ghi.

Mặc định phổ biến của Spring là rollback với unchecked exception và Error. Nếu cần rollback với checked exception, hãy cấu hình **rollbackFor** phù hợp.

Một lưu ý quan trọng: transaction proxy chỉ áp dụng khi lời gọi đi qua proxy Spring. Gọi một method **@Transactional** từ một method khác trong cùng object (self-invocation) thường không đi qua proxy, nên không kích hoạt ranh giới transaction mới như mong đợi.

## 10. Khởi chạy ApplicationContext

Tạo **Main.java**:

~~~java
package example;

import example.config.JpaConfig;
import example.domain.Customer;
import example.service.CustomerService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        System.setProperty(
            "org.slf4j.simpleLogger.defaultLogLevel",
            "warn"
        );

        try (var context =
                 new AnnotationConfigApplicationContext(JpaConfig.class)) {

            CustomerService service =
                context.getBean(CustomerService.class);

            Customer customer =
                service.register("an@example.com", "An");

            System.out.println("created=" + (customer.getId() != null));
            System.out.println("count=" + service.count());
        }
    }
}
~~~

**AnnotationConfigApplicationContext** tạo Spring container từ class Java Configuration. Khi khởi tạo context, Spring đăng ký bean, tạo DataSource, EntityManagerFactory, transaction manager và repository proxy. Sau đó **getBean()** lấy CustomerService đã được inject dependency.

Khối try-with-resources đóng ApplicationContext khi kết thúc. Spring sẽ đóng các bean có lifecycle callback, trong đó có HikariDataSource và EntityManagerFactory.

Chạy từ thư mục chứa **pom.xml**:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.Main
~~~

Hai dòng do chương trình chủ động in ra:

~~~text
created=true
count=1
~~~

**created=true** cho biết database đã cấp ID cho entity sau khi lưu. **count=1** cho biết repository truy vấn được một bản ghi trong bảng customers. Các log framework có thể xuất hiện tùy cấu hình logging của môi trường.

## 11. Vòng đời của một thao tác Repository

Khi gọi **service.register(...)**, luồng xử lý cơ bản như sau:

1. Lời gọi đi qua Spring proxy của CustomerService.
2. Transaction manager bắt đầu hoặc tham gia transaction phù hợp.
3. Service gọi **CustomerRepository.existsByEmail(...)**.
4. Repository proxy dùng EntityManager để thực hiện truy vấn.
5. Hibernate tạo SQL và JDBC driver gửi SQL tới database.
6. Nếu chưa có email, service tạo Customer và gọi **save()**.
7. JPA quản lý entity trong persistence context và đồng bộ thay đổi khi cần flush.
8. Transaction commit khi method kết thúc thành công; nếu có lỗi cần rollback thì transaction manager xử lý rollback theo quy tắc.
9. Kết quả được trả về cho caller.

**save()** không nhất thiết lập tức phát lệnh INSERT tại đúng dòng gọi. Với entity mới, JPA provider có thể trì hoãn SQL đến lúc flush hoặc commit. Thời điểm thực thi phụ thuộc chiến lược ID, trạng thái entity và nhu cầu đồng bộ persistence context.

## 12. EntityManager và cách inject trực tiếp khi cần

Spring ORM cũng hỗ trợ inject EntityManager bằng **@PersistenceContext**:

~~~java
package example.repository;

import example.domain.Customer;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerLookup {

    @PersistenceContext
    private EntityManager entityManager;

    public Customer findById(Long id) {
        return entityManager.find(Customer.class, id);
    }
}
~~~

Spring cung cấp EntityManager proxy phù hợp với transaction và persistence context hiện tại. Không nên tự tạo một EntityManager dùng chung cho nhiều thread hoặc giữ EntityManager lâu dài trong field của singleton.

Khi đã dùng Spring Data JPA, hãy ưu tiên repository cho các thao tác CRUD và truy vấn thông thường. Dùng EntityManager trực tiếp khi cần JPQL, Criteria API, bulk operation hoặc chức năng persistence mà repository abstraction không thể hiện rõ.

## 13. Cấu hình khi dùng database thật

Để kết nối PostgreSQL, MySQL hoặc database khác, cần:

1. Thêm JDBC driver tương ứng vào dependency.
2. Thay JDBC URL, driver class, username và password.
3. Cấu hình pool size và timeout phù hợp với tải.
4. Xác định cách quản lý schema, ưu tiên migration có version.
5. Chọn kiểu dữ liệu và chiến lược ID tương thích với database.
6. Kiểm tra quyền của tài khoản ứng dụng, chỉ cấp quyền cần thiết.

Ví dụ, với PostgreSQL, JDBC URL thường có dạng **jdbc:postgresql://host:5432/database**. Driver tương ứng là **org.postgresql.Driver**; dependency là **org.postgresql:postgresql**.

Không cần chỉ định Hibernate dialect trong mọi trường hợp. Hibernate 6 thường nhận diện database từ JDBC metadata. Nếu phải khai báo tường minh, hãy dùng dialect tương ứng với phiên bản Hibernate đang chạy.

Trong môi trường production, hãy đặt **hibernate.hbm2ddl.auto=validate** hoặc **none** theo quy trình schema đã chọn. Migration tool nên chịu trách nhiệm thay đổi schema; Hibernate nên kiểm tra mapping hoặc thực hiện persistence.

## 14. Nhiều persistence unit hoặc nhiều database

Ứng dụng nâng cao có thể cần nhiều DataSource và nhiều EntityManagerFactory, ví dụ một database cho đơn hàng và một database cho báo cáo.

Khi đó cần khai báo riêng:

- Mỗi DataSource.
- Mỗi LocalContainerEntityManagerFactoryBean và persistence unit.
- Mỗi PlatformTransactionManager.
- Phạm vi package repository tương ứng.
- **entityManagerFactoryRef** và **transactionManagerRef** cho từng nhóm repository.

Không nên để repository vô tình sử dụng nhầm EntityManagerFactory. Đặt tên bean có ý nghĩa và cấu hình rõ package giúp tránh lỗi khởi tạo hoặc transaction đi nhầm database.

## 15. So sánh cấu hình Java thuần với Spring Boot

| Công việc | Spring Framework không Boot | Spring Boot |
|---|---|---|
| Khởi tạo context | Tạo AnnotationConfigApplicationContext hoặc context phù hợp | SpringApplication.run(...) |
| DataSource | Tự khai báo bean và connection pool | Thường auto-config từ dependency và properties |
| EntityManagerFactory | Tự khai báo LocalContainerEntityManagerFactoryBean | Thường auto-config |
| Transaction manager | Tự khai báo JpaTransactionManager | Thường auto-config |
| Repository scanning | Khai báo @EnableJpaRepositories | Có thể auto-config hoặc khai báo rõ |
| Component scanning | Khai báo @ComponentScan | @SpringBootApplication bao gồm component scan |
| External configuration | Environment, @PropertySource, system properties hoặc custom PropertySource | Thêm cơ chế binding và externalized config của Boot |
| Dependency | Chọn từng artifact | Có thể dùng starter |

Không dùng Boot không có nghĩa là không dùng Spring. Bạn vẫn dùng Spring Framework và Spring Data JPA; chỉ là các bean hạ tầng phải được cấu hình tường minh.

## 16. Lỗi thường gặp và cách kiểm tra

**1. Không tìm thấy repository bean**

Kiểm tra package của interface có nằm trong phạm vi **@EnableJpaRepositories** hay không. Xác minh interface kế thừa repository phù hợp và ApplicationContext đã nạp đúng class cấu hình.

**2. Không tìm thấy entity hoặc báo Unknown entity**

Kiểm tra package entity có được truyền vào **setPackagesToScan()** hay không. Đảm bảo entity có **@Entity**, có khóa chính **@Id** và được đặt trong persistence unit đúng.

**3. Không tạo được EntityManagerFactory**

Kiểm tra DataSource, JDBC URL, driver, username/password, dependency Hibernate và thuộc tính JPA. Xem nguyên nhân gốc trong stack trace; lỗi khởi tạo có thể là kết nối database, dialect, mapping hoặc schema.

**4. Không tìm thấy transaction manager**

Kiểm tra bean **transactionManager** có được đăng ký và repository có tham chiếu đúng **transactionManagerRef** không. Kiểm tra **@EnableTransactionManagement** và dependency spring-tx/spring-orm.

**5. @Transactional không có hiệu lực**

Đảm bảo object được Spring quản lý, method được gọi thông qua Spring proxy và transaction management đã bật. Kiểm tra self-invocation, visibility của method và cấu hình proxy.

**6. Database báo thiếu bảng hoặc sai cột**

So sánh mapping entity với schema thực tế. Kiểm tra migration đã chạy chưa, kiểu dữ liệu và tên bảng/cột có khớp không. Với chế độ validate, Hibernate báo lỗi nếu schema không tương thích.

**7. Connection pool cạn hoặc kết nối bị giữ lâu**

Kiểm tra transaction kéo dài, connection chưa được trả về, pool size, timeout và tải database. Đừng giải quyết bằng cách tăng pool trước khi xác định nguyên nhân.

**8. Dùng nhầm javax.persistence và jakarta.persistence**

Spring Framework 6 và Spring Data JPA 3 sử dụng namespace Jakarta (**jakarta.persistence.***). Các ví dụ cũ dựa trên **javax.persistence.*** thuộc thế hệ trước và không thể trộn tùy ý với stack Jakarta.

## 17. Những nguyên tắc vận hành quan trọng

- Dùng một EntityManagerFactory dùng chung cho mỗi persistence unit trong ứng dụng thông thường; không tạo mới cho từng request.
- Để Spring quản lý vòng đời DataSource, EntityManagerFactory và transaction manager.
- Không chia sẻ một EntityManager thật giữa nhiều thread.
- Đặt transaction tại ranh giới nghiệp vụ, thường là service.
- Không giữ transaction mở trong lúc gọi API bên ngoài hoặc chờ người dùng.
- Dùng migration có version cho schema production.
- Không log password, token hoặc bind parameter nhạy cảm.
- Cấu hình pool theo giới hạn database và tổng số instance ứng dụng.
- Kiểm tra repository query và execution plan khi có vấn đề hiệu năng.
- Giữ cấu hình database tách khỏi mã nguồn và quản lý secret qua cơ chế phù hợp.

## 18. Bài thực hành

Hãy mở rộng ví dụ Customer thành một ứng dụng nhỏ:

1. Thêm entity Order và quan hệ nhiều-một với Customer.
2. Tạo OrderRepository kế thừa JpaRepository.
3. Viết OrderService có constructor injection và @Transactional.
4. Tạo một query tìm các đơn hàng của Customer theo email.
5. Thử chạy ứng dụng với H2, sau đó đổi DataSource sang PostgreSQL.
6. Thay **create-drop** bằng migration tạo bảng và Hibernate **validate**.
7. Thử bỏ **@EnableTransactionManagement** rồi quan sát hành vi khi có nhiều thao tác dữ liệu trong một service method.
8. Viết integration test khởi tạo ApplicationContext và lưu/đọc một entity.

Qua bài thực hành, hãy giải thích được mỗi bean được tạo ở đâu, bean nào phụ thuộc bean nào, repository lấy EntityManager từ đâu và transaction manager kết nối với persistence unit thế nào.

## 19. Checklist tự đánh giá

- [ ] Tôi phân biệt được JPA, Hibernate, Spring Framework và Spring Data JPA.
- [ ] Tôi biết vì sao ứng dụng không dùng Boot phải khai báo DataSource.
- [ ] Tôi hiểu vai trò của LocalContainerEntityManagerFactoryBean.
- [ ] Tôi biết cấu hình package chứa entity bằng **setPackagesToScan()**.
- [ ] Tôi hiểu HibernateJpaVendorAdapter và JPA properties.
- [ ] Tôi biết vì sao cần JpaTransactionManager.
- [ ] Tôi phân biệt được @ComponentScan và @EnableJpaRepositories.
- [ ] Tôi có thể khởi chạy AnnotationConfigApplicationContext.
- [ ] Tôi hiểu cách Spring inject repository vào service.
- [ ] Tôi hiểu transaction proxy và vấn đề self-invocation.
- [ ] Tôi biết cấu hình schema demo khác với schema production.
- [ ] Tôi có thể lần theo stack trace khi DataSource hoặc EntityManagerFactory khởi tạo thất bại.

## 20. Câu hỏi ôn tập

**1. Vì sao vẫn có thể dùng Spring Data JPA khi không dùng Spring Boot?**

Vì Spring Data JPA là thư viện tích hợp với Spring Framework và JPA. Boot chủ yếu cung cấp cách khởi tạo và auto-configuration; nó không phải điều kiện bắt buộc để repository hoạt động.

**2. LocalContainerEntityManagerFactoryBean làm nhiệm vụ gì?**

Nó tích hợp vòng đời EntityManagerFactory với Spring, cấu hình DataSource, entity packages, JPA provider và các thuộc tính persistence.

**3. Vì sao cần JpaTransactionManager?**

Nó nối cơ chế transaction của Spring với EntityManagerFactory để các method @Transactional quản lý transaction JPA đúng cách.

**4. @EnableJpaRepositories khác @ComponentScan thế nào?**

@EnableJpaRepositories tìm interface Spring Data và tạo repository proxy. @ComponentScan tìm các component Spring như service và component thông thường.

**5. Vì sao không nên dùng create-drop trong production?**

Vì schema có thể bị tạo lại hoặc xóa theo vòng đời ứng dụng, gây mất dữ liệu. Production nên dùng migration có version và cấu hình Hibernate phù hợp như validate hoặc none.

**6. Vì sao không nên tự tạo EntityManager trong từng service?**

Vì Spring cần quản lý EntityManager gắn với transaction và persistence context hiện tại. Tự tạo thủ công dễ gây rò rỉ tài nguyên, sai ranh giới transaction và không đồng bộ với repository.

Khi hiểu và tự cấu hình được các bean trên, bạn đã nắm được cách Spring Data JPA hoạt động bên trong một ứng dụng Spring Framework không sử dụng Spring Boot.