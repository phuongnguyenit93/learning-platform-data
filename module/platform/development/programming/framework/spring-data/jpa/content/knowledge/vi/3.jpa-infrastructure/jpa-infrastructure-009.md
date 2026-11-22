# Cấu hình XML, persistence.xml và phạm vi áp dụng trong hệ thống cũ

## 1. Vì sao hệ thống cũ thường có cấu hình JPA bằng XML?

Các ứng dụng Java dùng JPA trước đây thường khai báo cấu hình persistence trong tệp `persistence.xml`. Cách làm này phổ biến trong ứng dụng Java EE/Jakarta EE chạy trên application server, ứng dụng Java SE tự bootstrap JPA, hoặc hệ thống Spring cũ cần giữ cấu hình đã tồn tại qua nhiều năm.

Khi chuyển một ứng dụng như vậy sang Spring Boot và Spring Data JPA, cần hiểu XML đang mô tả phần nào. Cấu hình JPA thường gồm nhiều lớp trách nhiệm:

- **Persistence unit metadata:** tên persistence unit, provider, loại transaction, datasource và danh sách lớp được quản lý.
- **Mapping metadata:** cách ánh xạ entity, bảng, cột, khóa, quan hệ, converter và listener. Metadata có thể nằm trong annotation hoặc tệp XML như `orm.xml`.
- **Provider properties:** cấu hình riêng cho Hibernate hoặc JPA provider khác, ví dụ hành vi tạo schema, batching, cache hoặc SQL logging.
- **Spring integration:** cách Spring tạo `EntityManagerFactory`, quản lý transaction, inject `EntityManager` và tạo repository proxy.

`persistence.xml` thuộc phần metadata của JPA. Nó không phải tệp cấu hình bean Spring, không tự bật component scanning và cũng không tự đăng ký repository interface của Spring Data.

## 2. Persistence unit là gì?

**Persistence unit** là một nhóm logic gồm các entity và metadata mà một JPA provider quản lý cùng nhau. Một persistence unit thường xác định:

- Tên để ứng dụng tham chiếu, ví dụ `legacyUnit`.
- JPA provider, ví dụ Hibernate.
- Kiểu transaction là `RESOURCE_LOCAL` hoặc `JTA`.
- Datasource hoặc thông tin kết nối.
- Danh sách entity và mapping file.
- Các thuộc tính cấu hình cho provider.

Từ một persistence unit, ứng dụng tạo một `EntityManagerFactory`. Mỗi `EntityManagerFactory` tạo ra các `EntityManager`; mỗi EntityManager quản lý một persistence context. Entity được quản lý trong persistence context gắn với EntityManager đó.

~~~text
persistence.xml
      |
      v
Persistence Unit: legacyUnit
      |
      v
EntityManagerFactory
      |
      +---- EntityManager A ---- Persistence Context A
      |
      +---- EntityManager B ---- Persistence Context B
~~~

Một lớp Java có annotation `@Entity` chưa chắc đã thuộc mọi persistence unit. Nó phải được đưa vào metadata của persistence unit tương ứng, thông qua danh sách lớp, quy tắc phát hiện lớp hoặc cấu hình Spring/provider phù hợp. Vì thế, repository có thể được tạo thành công nhưng vẫn lỗi khi chạy nếu entity mà repository tham chiếu không thuộc persistence unit được gắn với nó.

Tên persistence unit không phải tên database, schema hay tên Spring profile. Nó là định danh của nhóm cấu hình JPA.

## 3. Vị trí và cấu trúc của persistence.xml

Theo quy ước JPA, tệp cấu hình thường được đặt tại:

~~~text
src/main/resources/
└── META-INF/
    └── persistence.xml
~~~

Sau khi build, tệp nằm trên classpath tại `META-INF/persistence.xml`. Nếu dùng Maven hoặc Gradle với cấu trúc tài nguyên chuẩn, thư mục `src/main/resources` sẽ được đóng gói vào artifact.

Ví dụ dưới đây minh họa một persistence unit JPA 3.1 dùng Hibernate và transaction loại resource-local trong môi trường Java SE. Tên driver, URL và thông tin kết nối chỉ là ví dụ; không nên ghi mật khẩu thật vào mã nguồn hoặc commit vào Git.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="https://jakarta.ee/xml/ns/persistence
                                 https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">

    <persistence-unit name="legacyUnit"
                      transaction-type="RESOURCE_LOCAL">

        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <class>com.legacy.domain.Customer</class>
        <class>com.legacy.domain.Invoice</class>
        <mapping-file>META-INF/orm.xml</mapping-file>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/legacydb"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="app_user"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="replace-with-secret"/>

            <property name="hibernate.hbm2ddl.auto"
                      value="validate"/>
            <property name="hibernate.show_sql"
                      value="false"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Các thành phần đáng chú ý:

- `persistence-unit name="legacyUnit"` khai báo một persistence unit có tên `legacyUnit`. Tên này được dùng khi bootstrap hoặc khi Spring chọn persistence unit.
- `transaction-type="RESOURCE_LOCAL"` chỉ định transaction được quản lý theo cơ chế resource-local.
- `provider` chỉ rõ implementation JPA, ở đây là Hibernate.
- Các phần tử `class` liệt kê entity được đưa vào persistence unit.
- `mapping-file` khai báo tệp mapping XML bổ sung.
- `exclude-unlisted-classes` điều khiển việc có đưa các lớp entity chưa được liệt kê tường minh vào persistence unit hay không. Khi cần danh sách chính xác, hãy khai báo rõ các lớp và đặt giá trị phù hợp.
- Các phần tử `property` truyền cấu hình cho JPA provider. Một số thuộc tính thuộc chuẩn Jakarta Persistence, một số khác là thuộc tính riêng của Hibernate.

Schema và namespace trong ví dụ là Jakarta Persistence 3.1. Hãy chọn phiên bản XML phù hợp với JPA provider và nền tảng của ứng dụng. Dự án cũ dùng JPA 2.x thường có namespace `javax.persistence` và schema cũ; không thể đổi riêng tên namespace mà không nâng cấp đồng bộ dependency và mã nguồn.

## 4. Các thành phần cấu hình quan trọng

### 4.1. Tên persistence unit

Một tệp `persistence.xml` có thể khai báo nhiều phần tử `persistence-unit`. Mỗi unit có tên riêng:

~~~xml
<persistence-unit name="customerUnit">
    ...
</persistence-unit>

<persistence-unit name="reportingUnit">
    ...
</persistence-unit>
~~~

Ứng dụng có thể tạo hai EntityManagerFactory với cấu hình, tập entity hoặc datasource khác nhau. Đây là cách một hệ thống cũ có thể tách dữ liệu giao dịch và dữ liệu báo cáo, hoặc tách các module sử dụng database khác nhau.

Không nên tạo nhiều persistence unit chỉ vì muốn chia package. Mỗi unit tạo thêm ranh giới quản lý entity, transaction và kết nối cần vận hành.

### 4.2. Transaction type: RESOURCE_LOCAL và JTA

Hai kiểu transaction có mục đích khác nhau:

| Kiểu | Cách hoạt động | Bối cảnh thường gặp |
|---|---|---|
| `RESOURCE_LOCAL` | Transaction được điều khiển ở mức persistence resource, thường thông qua EntityTransaction hoặc transaction manager tích hợp với resource | Ứng dụng Java SE, ứng dụng Spring dùng một datasource và JpaTransactionManager |
| `JTA` | Transaction được điều phối bởi JTA transaction manager, có thể phối hợp nhiều resource tham gia giao dịch | Jakarta EE application server hoặc hệ thống có distributed transaction |

Trong ứng dụng Spring, `@Transactional` là cách khai báo ranh giới transaction ở tầng nghiệp vụ. Annotation này không tự quyết định persistence unit là JTA hay resource-local; transaction manager được cấu hình mới là thành phần điều phối thực tế.

Với resource-local và một datasource, Spring thường dùng `JpaTransactionManager`. Với JTA, cần JTA transaction manager và datasource/provider phù hợp. Không nên đổi `transaction-type` từ JTA sang RESOURCE_LOCAL chỉ để làm ứng dụng khởi động nếu hệ thống cũ đang phụ thuộc vào transaction phân tán.

### 4.3. Datasource: JNDI, JTA và non-JTA

Trong môi trường application server, datasource thường được quản lý bên ngoài ứng dụng và tra cứu qua JNDI. Ví dụ:

~~~xml
<persistence-unit name="legacyUnit" transaction-type="JTA">
    <jta-data-source>java:comp/env/jdbc/LegacyDS</jta-data-source>
</persistence-unit>
~~~

`jta-data-source` tham chiếu datasource tham gia JTA transaction. Với datasource không tham gia JTA, metadata có thể dùng `non-jta-data-source`.

Trong ứng dụng Spring Boot tự quản lý datasource, datasource thường được cấu hình bằng `spring.datasource.*` và tạo thành bean Spring. Khi tích hợp persistence unit XML vào Spring, cần chọn rõ nguồn datasource: dùng datasource do Spring cấp hoặc dùng JNDI datasource của môi trường triển khai. Tránh cấu hình hai nguồn kết nối mâu thuẫn trong cùng một persistence unit.

### 4.4. Danh sách lớp và exclude-unlisted-classes

Có hai cách thường gặp để xác định entity trong persistence unit:

- Liệt kê lớp bằng phần tử `class`.
- Cho provider phát hiện các lớp entity trong phạm vi archive/persistence unit theo quy tắc JPA.

Ví dụ khai báo rõ:

~~~xml
<class>com.legacy.customer.Customer</class>
<class>com.legacy.order.Order</class>
<exclude-unlisted-classes>true</exclude-unlisted-classes>
~~~

Cách liệt kê rõ hữu ích khi hệ thống cũ có nhiều module hoặc cần kiểm soát chính xác entity thuộc từng persistence unit. Tuy nhiên, mỗi lần thêm entity mới phải cập nhật danh sách tương ứng nếu đang loại trừ các lớp chưa liệt kê.

`exclude-unlisted-classes` không phải annotation quét package của Spring. Nó điều khiển việc phát hiện lớp trong persistence unit theo metadata JPA.

## 5. Phân biệt persistence.xml, orm.xml và hibernate.cfg.xml

Ba tệp XML thường bị nhầm lẫn nhưng có vai trò khác nhau:

| Tệp | Mục đích |
|---|---|
| `META-INF/persistence.xml` | Khai báo persistence unit, provider, transaction type, datasource, danh sách lớp và các thuộc tính JPA/provider |
| `META-INF/orm.xml` | Khai báo hoặc bổ sung mapping entity theo chuẩn ORM XML của JPA |
| `hibernate.cfg.xml` | Tệp cấu hình bootstrap riêng của Hibernate trong cách tích hợp Hibernate truyền thống |

### 5.1. orm.xml dùng để ánh xạ entity

Có thể dùng `orm.xml` khi hệ thống muốn giữ mapping ngoài mã Java, khi mapping phụ thuộc vào module hoặc khi cần duy trì metadata XML trong giai đoạn chuyển đổi.

Ví dụ rút gọn:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings xmlns="https://jakarta.ee/xml/ns/persistence/orm"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="https://jakarta.ee/xml/ns/persistence/orm
                                     https://jakarta.ee/xml/ns/persistence/orm_3_1.xsd"
                 version="3.1">

    <entity class="com.legacy.domain.Customer" access="FIELD">
        <table name="customers"/>
        <attributes>
            <id name="id">
                <generated-value strategy="IDENTITY"/>
            </id>
            <basic name="name">
                <column name="customer_name" nullable="false"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
~~~

Tệp này mô tả mapping của lớp `Customer`: bảng `customers`, khóa chính `id` và cột `customer_name` cho thuộc tính `name`. Cần bảo đảm tên thuộc tính trong XML khớp với cấu trúc lớp Java và mapping không mâu thuẫn với metadata còn lại.

ORM XML là metadata ánh xạ. Nó không thay thế persistence unit và cũng không tạo Spring bean.

### 5.2. hibernate.cfg.xml không đồng nghĩa với persistence.xml

`hibernate.cfg.xml` thuộc cách bootstrap và cấu hình riêng của Hibernate. Một hệ thống Hibernate cũ có thể dùng nó để khai báo datasource, mapping resource và property của Hibernate. Khi chuyển sang JPA chuẩn hoặc Spring Data JPA, cần xác định cấu hình đang được đọc bởi bootstrap API nào.

Không nên sao chép nguyên nội dung từ `hibernate.cfg.xml` sang `persistence.xml` mà không đối chiếu tên thuộc tính và ý nghĩa. Một số cấu hình Hibernate có thể chuyển thành property của provider, một số thuộc về datasource hoặc transaction manager của môi trường.

## 6. Spring Data JPA sử dụng persistence.xml như thế nào?

Spring Data JPA không trực tiếp đọc `persistence.xml` để tạo repository. Luồng trách nhiệm thường là:

1. Spring tạo hoặc nhận một `EntityManagerFactory`.
2. EntityManagerFactory được bootstrap từ persistence unit và provider.
3. Spring Data JPA tạo repository proxy và gắn repository với EntityManagerFactory tương ứng.
4. Service gọi repository; transaction manager quản lý ranh giới giao dịch.

Trong ứng dụng Spring Boot hiện đại, cấu hình phổ biến là để Boot tạo EntityManagerFactory từ datasource, package entity và các thuộc tính trong `application.properties` hoặc `application.yml`. Khi dùng cách này, thường không cần tự viết `persistence.xml`.

Một hệ thống legacy có thể cần giữ persistence unit XML vì đang dùng JNDI, JTA, mapping XML hoặc nhiều persistence unit. Khi đó, hãy tích hợp rõ persistence unit với Spring.

### 6.1. Tích hợp persistence unit XML vào Spring

Spring Framework cung cấp `LocalContainerEntityManagerFactoryBean` để tạo EntityManagerFactory từ metadata persistence unit. Ví dụ dưới đây minh họa một persistence unit resource-local, dùng datasource do Spring cung cấp:

~~~java
package com.legacy.config;

import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.orm.jpa.JpaVendorAdapter;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.legacy.customer.repository",
    entityManagerFactoryRef = "legacyEntityManagerFactory",
    transactionManagerRef = "legacyTransactionManager"
)
public class LegacyJpaConfiguration {

    @Bean
    public JpaVendorAdapter jpaVendorAdapter() {
        return new HibernateJpaVendorAdapter();
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean legacyEntityManagerFactory(
            DataSource dataSource,
            JpaVendorAdapter jpaVendorAdapter) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setPersistenceXmlLocation(
                "classpath:META-INF/persistence.xml");
        factory.setPersistenceUnitName("legacyUnit");
        factory.setDataSource(dataSource);
        factory.setJpaVendorAdapter(jpaVendorAdapter);

        return factory;
    }

    @Bean
    public PlatformTransactionManager legacyTransactionManager(
            EntityManagerFactory legacyEntityManagerFactory) {
        return new JpaTransactionManager(legacyEntityManagerFactory);
    }
}
~~~

Ý nghĩa:

- `setPersistenceXmlLocation` chỉ vị trí tệp XML trên classpath.
- `setPersistenceUnitName` chọn đúng unit đã khai báo trong XML.
- `setDataSource` đưa datasource do Spring quản lý vào persistence unit theo cách tích hợp này.
- `JpaVendorAdapter` cung cấp tích hợp giữa Spring ORM và provider, ở đây là Hibernate.
- `@EnableJpaRepositories` chỉ định package repository và gắn chúng với đúng EntityManagerFactory cùng transaction manager.
- `JpaTransactionManager` điều phối transaction JPA resource-local cho EntityManagerFactory được truyền vào.

Ví dụ dùng import `jakarta.persistence` cho Spring Boot 3+ và Spring Framework tương thích. Trong dự án Spring Boot 2/JPA 2.x, import JPA thường dùng `javax.persistence`. Không trộn hai thế hệ API.

Nếu dùng datasource do Spring quản lý, hãy chọn một nguồn cấu hình kết nối thống nhất. Trong ví dụ này, datasource được truyền qua `setDataSource`; không nên đồng thời duy trì URL/driver/mật khẩu khác nhau trong XML khiến người vận hành không biết cấu hình nào có hiệu lực.

Đây là cấu hình tích hợp tường minh cho tình huống legacy. Trước khi áp dụng, cần kiểm tra phiên bản Spring Framework, JPA provider, loại transaction và cách datasource được quản lý trong môi trường thực tế. Với JTA, cần cấu hình JTA transaction manager và datasource/provider tương ứng thay vì dùng `JpaTransactionManager` như ví dụ resource-local.

### 6.2. Chọn EntityManager theo persistence unit

Nếu ứng dụng có nhiều EntityManagerFactory, có thể chỉ rõ persistence unit khi inject EntityManager:

~~~java
@PersistenceContext(unitName = "legacyUnit")
private EntityManager entityManager;
~~~

Tên `legacyUnit` phải khớp với persistence unit đã cấu hình. Nếu bỏ qua tên trong ứng dụng có nhiều unit, việc chọn EntityManager có thể mơ hồ hoặc gắn nhầm persistence unit.

Với repository Spring Data, các thuộc tính `entityManagerFactoryRef` và `transactionManagerRef` trong `@EnableJpaRepositories` có vai trò tương tự: chúng chỉ định hạ tầng mà nhóm repository sẽ sử dụng.

## 7. Phạm vi áp dụng trong hệ thống legacy

### 7.1. Persistence unit xác định phạm vi entity

Một persistence unit quản lý tập entity và mapping của nó. Nếu một entity không thuộc unit, EntityManagerFactory của unit đó không thể quản lý entity như mong đợi.

Ví dụ, nếu `legacyUnit` chỉ chứa:

~~~xml
<class>com.legacy.customer.Customer</class>
<class>com.legacy.customer.Address</class>
~~~

thì không thể mặc định cho rằng entity `com.legacy.audit.AuditEvent` cũng được quản lý trong cùng unit. Cần đưa nó vào metadata hoặc điều chỉnh cách phát hiện entity có chủ đích.

Đây là phạm vi quản lý của JPA, khác với phạm vi component scan của Spring.

### 7.2. Repository package xác định nhóm interface được đăng ký

Repository scan xác định các interface nào được Spring Data tạo proxy. Nó không tự bổ sung entity vào persistence unit.

Với nhiều persistence unit, nên chia package repository theo module hoặc theo datasource và khai báo rõ:

~~~java
@EnableJpaRepositories(
    basePackages = "com.legacy.customer.repository",
    entityManagerFactoryRef = "customerEntityManagerFactory",
    transactionManagerRef = "customerTransactionManager"
)
~~~

Nhóm repository này sẽ sử dụng EntityManagerFactory và transaction manager được chỉ định. Cấu hình một nhóm repository vào nhầm factory có thể gây lỗi entity không được quản lý hoặc truy vấn sai database.

### 7.3. Một ứng dụng có thể có nhiều persistence unit

Ví dụ một hệ thống có database giao dịch và database báo cáo:

~~~text
Ứng dụng Spring
  |
  +-- customer repositories
  |       |
  |       +-- customerEntityManagerFactory
  |               |
  |               +-- customerUnit
  |                       |
  |                       +-- customerDataSource
  |
  +-- reporting repositories
          |
          +-- reportingEntityManagerFactory
                  |
                  +-- reportingUnit
                          |
                          +-- reportingDataSource
~~~

Mỗi nhóm cần cấu hình rõ:

- Persistence unit và tập entity tương ứng.
- EntityManagerFactory.
- Datasource hoặc JNDI datasource.
- Transaction manager.
- Package repository được gắn với factory đó.

Nếu cần một transaction nguyên tử bao phủ nhiều database/resource, không thể mặc định rằng hai JpaTransactionManager riêng biệt sẽ phối hợp thành một transaction phân tán. Cần JTA hoặc một thiết kế nhất quán khác phù hợp với yêu cầu nghiệp vụ.

## 8. Khi nào nên giữ XML và khi nào nên chuyển sang cấu hình hiện đại?

Không phải hệ thống nào cũng cần xóa `persistence.xml`. Quyết định phụ thuộc vào những gì XML đang kiểm soát.

**Nên cân nhắc giữ XML khi:**

- Ứng dụng đang chạy trong application server và sử dụng JNDI/JTA.
- Có nhiều persistence unit với tập entity và datasource riêng.
- Mapping XML có nhiều quy tắc, override hoặc metadata không nên thay đổi trong giai đoạn nâng cấp.
- Nhiều module cũ cùng dựa vào tên persistence unit hoặc cách bootstrap hiện tại.
- Cần giảm phạm vi thay đổi khi nâng cấp một hệ thống đang vận hành ổn định.

**Có thể chuyển dần sang cấu hình Spring Boot khi:**

- Ứng dụng chỉ có một datasource và một persistence unit đơn giản.
- Entity đã được quản lý bằng annotation và không cần mapping XML đặc biệt.
- Không phụ thuộc vào JNDI/JTA của application server.
- Muốn quản lý cấu hình kết nối và provider tập trung bằng Spring configuration.
- Đội ngũ có thể kiểm thử đầy đủ hành vi trước và sau khi chuyển.

Cấu hình Boot thường đặt kết nối trong `spring.datasource.*` và các tùy chọn JPA trong `spring.jpa.*`. Việc khai báo package entity có thể dựa trên package gốc hoặc cấu hình entity scan. Repository có thể được auto-configure theo cấu trúc package mặc định hoặc khai báo tường minh khi có nhiều nhóm.

Không nên chuyển tất cả XML sang annotation chỉ vì muốn dùng Spring Boot. Nếu XML đang chứa mapping có ý nghĩa nghiệp vụ hoặc cấu hình transaction của môi trường, hãy giữ lại cho tới khi có kiểm thử chứng minh việc thay đổi không làm đổi hành vi.

## 9. Quy trình chuyển đổi một hệ thống cũ

Một lộ trình thận trọng có thể gồm các bước sau:

1. **Kiểm kê persistence unit:** ghi lại tên unit, provider, transaction type, datasource/JNDI name, danh sách class, mapping file và provider properties.
2. **Kiểm kê mapping:** xác định mapping nằm trong annotation, `orm.xml`, Hibernate mapping XML hay được tạo từ convention. Ghi lại generator, converter, listener, named query, quan hệ và fetch strategy.
3. **Xác định môi trường transaction:** ứng dụng dùng resource-local, JTA hay transaction manager riêng của framework/application server. Xác định rõ ai mở, commit và rollback transaction.
4. **Giữ schema ổn định:** dùng chế độ kiểm tra schema như `validate` trong giai đoạn kiểm chứng. Không bật tự động tạo/xóa schema trên database đang chứa dữ liệu sản xuất.
5. **Nâng cấp API đồng bộ:** khi chuyển từ Spring Boot 2/JPA 2.x sang Spring Boot 3+/Jakarta Persistence, cập nhật namespace `javax.persistence` sang `jakarta.persistence` cùng provider và dependency tương thích.
6. **Chuyển từng persistence unit:** nếu có nhiều unit, thực hiện và kiểm thử từng nhóm, giữ đúng datasource và repository mapping.
7. **Kiểm thử transaction và truy vấn:** kiểm tra commit/rollback, lazy loading, quan hệ, khóa sinh tự động, named query, native query, optimistic locking và các thao tác repository.
8. **Đối chiếu SQL và dữ liệu:** so sánh SQL được sinh, kết quả truy vấn và schema trước/sau. Dùng log SQL ở môi trường kiểm thử khi cần.
9. **Triển khai có kiểm soát:** theo dõi lỗi bootstrap, kết nối, transaction và truy vấn sau khi nâng cấp; chuẩn bị phương án rollback phù hợp.

Nếu schema cần thay đổi, nên dùng công cụ quản lý migration như Flyway hoặc Liquibase để version hóa thay đổi. Việc chuyển cấu hình JPA không nên đồng thời thay đổi schema không liên quan nếu chưa có kiểm thử riêng.

## 10. Lỗi thường gặp và hướng xử lý

### 10.1. Không tìm thấy persistence unit

Lỗi thường xuất hiện khi provider hoặc Spring không tìm thấy unit có tên được yêu cầu.

Kiểm tra:

- Tệp có được đóng gói tại `META-INF/persistence.xml` không?
- Tên trong `setPersistenceUnitName` hoặc `@PersistenceContext(unitName=...)` có khớp chính xác không?
- Tệp có được đặt ở classpath của module đang bootstrap JPA không?
- XML có đúng namespace và schema version với provider không?

### 10.2. Entity không được quản lý

Thông báo như `Not a managed type` thường có nghĩa entity không thuộc persistence unit đang được sử dụng.

Kiểm tra:

- Lớp có `@Entity` hoặc mapping XML phù hợp không?
- Lớp đã được liệt kê trong unit chưa?
- `exclude-unlisted-classes` có loại trừ lớp đó không?
- Repository có đang gắn nhầm EntityManagerFactory không?
- Entity có được đăng ký trong persistence unit khác thay vì unit mà repository sử dụng không?

Không giải quyết lỗi này bằng cách chỉ mở rộng component scan; đó là cơ chế khác.

### 10.3. Datasource hoặc JNDI không tồn tại

Nếu ứng dụng báo không tìm thấy datasource, kiểm tra tên JNDI, cấu hình resource trên application server, quyền truy cập, driver và môi trường triển khai. Tên datasource ở máy phát triển có thể khác với môi trường staging hoặc production.

Nếu dùng Spring Boot tự quản lý datasource, kiểm tra cấu hình `spring.datasource.*` và bean DataSource được truyền cho EntityManagerFactory. Tránh vừa trỏ JNDI vừa truyền một datasource khác mà không có chủ đích.

### 10.4. Transaction không được quản lý đúng

Các dấu hiệu có thể gồm dữ liệu không rollback như mong đợi, lỗi không có transaction đang hoạt động, hoặc nhiều thao tác trên các datasource không nằm trong cùng một transaction.

Kiểm tra transaction type trong persistence unit, transaction manager Spring, cách datasource tham gia JTA và nơi đặt `@Transactional`. Với nhiều persistence unit, cần xác định rõ transaction manager nào điều khiển mỗi service/repository.

### 10.5. Dùng sai namespace javax và jakarta

Spring Boot 3+ chuyển sang Jakarta EE namespace. Nếu entity dùng `jakarta.persistence.Entity` nhưng provider hoặc thư viện cũ chỉ hỗ trợ `javax.persistence.Entity`, lớp có thể không được nhận diện đúng.

Kiểm tra dependency tree và phiên bản của Spring Boot, Spring Data JPA, Hibernate, JPA API cùng các module dùng chung. Cần nâng cấp đồng bộ, không sửa riêng import trong một vài lớp.

### 10.6. Cấu hình bị khai báo ở nhiều nơi

Một hệ thống có thể cùng khai báo datasource trong XML, application properties, biến môi trường và cấu hình application server. Khi đó, giá trị thực tế có thể khác với giá trị người vận hành nghĩ rằng đang được dùng.

Hãy xác định một nguồn cấu hình có thẩm quyền cho từng môi trường, quản lý secret bên ngoài mã nguồn và ghi lại các override có chủ đích. Không ghi mật khẩu hoặc token kết nối vào Git.

## 11. Ghi nhớ

- `persistence.xml` khai báo persistence unit và metadata bootstrap JPA.
- Persistence unit xác định tập entity, mapping, provider, transaction và datasource được quản lý cùng nhau.
- `orm.xml` mô tả mapping entity bằng XML; `hibernate.cfg.xml` thuộc cơ chế cấu hình riêng của Hibernate.
- Spring Data JPA cần một EntityManagerFactory được Spring quản lý hoặc được cung cấp; nó tạo repository proxy dựa trên factory đó.
- Component scan, entity membership và repository scan là các phạm vi khác nhau.
- Hệ thống legacy có thể giữ XML nếu XML đang thể hiện ranh giới transaction, datasource hoặc mapping cần thiết.
- Khi chuyển sang Spring Boot/Jakarta, cần nâng cấp API, provider, datasource và transaction đồng bộ, rồi kiểm thử hành vi trước khi thay đổi môi trường thật.

Hiểu đúng phạm vi của persistence unit giúp tránh nhầm lẫn giữa việc tìm thấy một class, việc JPA quản lý entity đó và việc Spring Data tạo repository cho entity. Đây là điểm quan trọng khi bảo trì ứng dụng Spring Data JPA lâu năm hoặc tích hợp nhiều module dữ liệu.