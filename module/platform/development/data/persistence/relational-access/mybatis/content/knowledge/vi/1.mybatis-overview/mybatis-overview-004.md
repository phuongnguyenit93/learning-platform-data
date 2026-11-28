# Phân biệt MyBatis lõi, MyBatis-Spring và Spring Boot Starter

Trong ứng dụng Java, MyBatis giúp lập trình viên chủ động viết SQL, truyền tham số vào câu lệnh và ánh xạ kết quả truy vấn về đối tượng. Khi thêm Spring hoặc Spring Boot, công việc này vẫn do MyBatis thực hiện. Những thư viện tích hợp bổ sung cách khởi tạo thành phần, cung cấp Mapper cho ứng dụng và phối hợp phiên làm việc với giao dịch.

Vì vậy, cần phân biệt ba thành phần theo trách nhiệm:

- **MyBatis lõi** thực thi cơ chế ánh xạ SQL và làm việc với JDBC.
- **MyBatis-Spring** kết nối MyBatis với container và cơ chế giao dịch của Spring.
- **MyBatis Spring Boot Starter** cung cấp tập phụ thuộc và tự cấu hình để dùng MyBatis trong ứng dụng Spring Boot với ít cấu hình thủ công hơn.

Bài học thuộc phần định hướng sử dụng MyBatis. Mục tiêu là nhận diện thành phần cần dùng, hiểu ai quản lý `SqlSession` và chọn đúng nơi cấu hình trước khi đi sâu vào Mapper, SQL động, `resultMap`, TypeHandler, cache hay batch.

## 1. Quan hệ giữa ba thành phần

Có thể hình dung quan hệ phụ thuộc thường gặp như sau:

```text
Ứng dụng Spring Boot dùng MyBatis
    |
    +-- MyBatis Spring Boot Starter
            |
            +-- Tự cấu hình MyBatis theo bean và thuộc tính của ứng dụng
            |
            +-- MyBatis-Spring
                    |
                    +-- Tích hợp Mapper, SqlSession và giao dịch với Spring
                    |
                    +-- MyBatis lõi
                            |
                            +-- SQL, tham số, resultMap, TypeHandler, Executor
                                    |
                                    +-- JDBC -> Cơ sở dữ liệu
```

Sơ đồ mô tả các lớp trách nhiệm, không phải yêu cầu mọi chương trình Java phải dùng đủ ba thành phần. Ứng dụng Java thuần có thể sử dụng MyBatis lõi trực tiếp. Ứng dụng Spring không dùng Boot có thể sử dụng MyBatis-Spring cùng MyBatis lõi.

| Tiêu chí | MyBatis lõi | MyBatis-Spring | MyBatis Spring Boot Starter |
| --- | --- | --- | --- |
| Tọa độ phụ thuộc chính | `org.mybatis:mybatis` | `org.mybatis:mybatis-spring` | `org.mybatis.spring.boot:mybatis-spring-boot-starter` |
| Trách nhiệm chính | Nạp câu lệnh, bind tham số, ánh xạ kết quả, thực thi qua JDBC | Tạo và cung cấp thành phần MyBatis dưới dạng bean; tham gia giao dịch Spring | Bổ sung phụ thuộc tích hợp và tự cấu hình theo điều kiện trong ứng dụng Boot |
| Thành phần tiêu biểu | `SqlSessionFactoryBuilder`, `SqlSessionFactory`, `SqlSession`, `Configuration` | `SqlSessionFactoryBean`, `SqlSessionTemplate`, `MapperFactoryBean`, `@MapperScan` | Cấu hình tự động và các thuộc tính `mybatis.*` |
| Nơi định nghĩa SQL | XML Mapper, annotation hoặc SQL provider | Tiếp tục dùng SQL của MyBatis lõi | Tiếp tục dùng SQL của MyBatis lõi |
| Quản lý phiên phổ biến | Ứng dụng mở, commit/rollback và đóng phiên | Cơ chế tích hợp phối hợp phiên với Spring | Cơ chế MyBatis-Spring do Boot cấu hình |
| Phụ thuộc Spring | Không bắt buộc | Có | Có, trong môi trường Spring Boot |

Starter không cung cấp một ngôn ngữ SQL riêng. Cũng không có yêu cầu phải viết lại `resultMap` hoặc TypeHandler chỉ vì chuyển từ cấu hình MyBatis-Spring thủ công sang Starter.

### 1.1. Tên tương tự nhưng khác vai trò

`SqlSessionFactory` là interface của MyBatis lõi. `SqlSessionFactoryBean` là thành phần tích hợp Spring dùng để tạo ra một `SqlSessionFactory`. Hậu tố `Bean` ở đây gắn với cơ chế `FactoryBean` của Spring.

Tương tự, `SqlSessionTemplate` thuộc MyBatis-Spring và triển khai interface `SqlSession`. Nó điều phối việc lấy, sử dụng và giải phóng phiên theo ngữ cảnh Spring, thay vì đại diện cho một phiên cơ sở dữ liệu cố định tồn tại suốt vòng đời ứng dụng.

Việc một interface Mapper được inject vào service cũng không có nghĩa Mapper đó là một lớp triển khai do lập trình viên viết. MyBatis tạo proxy cho Mapper; lớp tích hợp giúp đăng ký và cung cấp proxy đó qua Spring.

## 2. MyBatis lõi chịu trách nhiệm gì?

MyBatis lõi xử lý các công việc sát với truy cập dữ liệu:

1. Đọc cấu hình và đăng ký Mapper.
2. Tìm mapped statement tương ứng với lời gọi Mapper.
3. Tạo SQL, bao gồm xử lý các thành phần SQL động nếu được khai báo.
4. Bind tham số vào JDBC statement thông qua các TypeHandler thích hợp.
5. Thực thi câu lệnh và ánh xạ kết quả sang Java theo `resultType` hoặc `resultMap`.
6. Cung cấp cơ chế cache và kiểu thực thi, chẳng hạn thực thi thông thường hoặc batch.

Ví dụ, ánh xạ cột `product_name` vào thuộc tính `name` là trách nhiệm của cấu hình MyBatis. Việc lấy `DataSource` từ Spring là vấn đề tích hợp. Việc đọc khóa `mybatis.mapper-locations` trong `application.yml` là công việc của tích hợp Boot.

Trong cách dùng Java thuần, vòng đời phổ biến là:

```text
Đọc cấu hình
    -> xây dựng SqlSessionFactory
    -> mở SqlSession cho một đơn vị công việc
    -> lấy Mapper và thực thi SQL
    -> commit hoặc rollback khi cần
    -> đóng SqlSession
```

`SqlSessionFactory` thường được tạo một lần cho một cấu hình nguồn dữ liệu rồi tái sử dụng. `SqlSession` thông thường, chẳng hạn `DefaultSqlSession`, không được chia sẻ đồng thời giữa nhiều luồng. Một Mapper lấy trực tiếp từ phiên đó cũng gắn với vòng đời của phiên.

## 3. Bộ ví dụ dùng chung

Để thấy rõ khác biệt cấu hình, ba phương án bên dưới dùng cùng mô hình và SQL. Các đoạn mã là ví dụ minh họa để đặt trong dự án phù hợp; chỉ chọn một phương án cấu hình ứng dụng.

Giả định:

- Ứng dụng có JDBC driver PostgreSQL trên classpath và cơ sở dữ liệu có thể kết nối.
- Các phiên bản Java, MyBatis, Spring và Spring Boot, nếu sử dụng, được chọn tương thích với nhau trong cấu hình build.
- Các giá trị kết nối được cung cấp qua biến môi trường `DEMO_JDBC_URL`, `DEMO_JDBC_USER`, `DEMO_JDBC_PASSWORD`.
- Schema và dữ liệu ví dụ đã được tạo trước khi chạy thao tác truy cập dữ liệu.

Starter không thay thế JDBC driver. Các tọa độ thư viện trong bài cũng không ấn định phiên bản: cần dùng bộ phiên bản phù hợp với dự án và cơ chế quản lý phụ thuộc của dự án đó.

### 3.1. Bảng dữ liệu

```sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL
);

INSERT INTO product (id, product_name, price)
VALUES (1, 'Keyboard', 750000.00),
       (2, 'Mouse', 250000.00);
```

### 3.2. Đối tượng Java

```java
package com.example.catalog.model;

import java.math.BigDecimal;

public class Product {
    private Long id;
    private String name;
    private BigDecimal price;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

### 3.3. Interface Mapper

```java
package com.example.catalog.mapper;

import java.math.BigDecimal;
import org.apache.ibatis.annotations.Param;
import com.example.catalog.model.Product;

public interface ProductMapper {
    Product findById(@Param("id") long id);

    int updatePrice(
        @Param("id") long id,
        @Param("price") BigDecimal price
    );
}
```

`@Param` thuộc MyBatis lõi, dùng để đặt tên tham số cho SQL. Ví dụ đặt tên rõ ràng để không phụ thuộc cách biên dịch hoặc suy luận tên tham số Java.

### 3.4. XML Mapper

Đặt tài nguyên tại `src/main/resources/mappers/ProductMapper.xml`:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
    PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
    "https://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="com.example.catalog.mapper.ProductMapper">
    <resultMap id="productResult" type="com.example.catalog.model.Product">
        <id property="id" column="id" />
        <result property="name" column="product_name" />
        <result property="price" column="price" />
    </resultMap>

    <select id="findById" resultMap="productResult">
        SELECT id, product_name, price
        FROM product
        WHERE id = #{id}
    </select>

    <update id="updatePrice">
        UPDATE product
        SET price = #{price}
        WHERE id = #{id}
    </update>
</mapper>
```

`namespace` phải khớp tên đầy đủ của interface; `id` của câu lệnh phải khớp tên phương thức. Với `updatePrice`, MyBatis trả về số dòng bị tác động để phía nghiệp vụ kiểm tra kết quả cập nhật.

Các biểu thức `#{id}` và `#{price}` được bind thành tham số JDBC. Chúng không phải cú pháp của Spring. `resultMap` cũng tiếp tục có hiệu lực trong cả ba cách cấu hình.

## 4. Phương án A: dùng MyBatis lõi trong Java thuần

Ứng dụng cần MyBatis lõi và JDBC driver. Không cần Spring chỉ để sử dụng Mapper hoặc XML Mapper.

### 4.1. Cấu hình MyBatis

Đặt `mybatis-config.xml` trong thư mục tài nguyên:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE configuration
    PUBLIC "-//mybatis.org//DTD Config 3.0//EN"
    "https://mybatis.org/dtd/mybatis-3-config.dtd">
<configuration>
    <environments default="demo">
        <environment id="demo">
            <transactionManager type="JDBC" />
            <dataSource type="POOLED">
                <property name="driver" value="org.postgresql.Driver" />
                <property name="url" value="${jdbc.url}" />
                <property name="username" value="${jdbc.username}" />
                <property name="password" value="${jdbc.password}" />
            </dataSource>
        </environment>
    </environments>

    <mappers>
        <mapper resource="mappers/ProductMapper.xml" />
    </mappers>
</configuration>
```

`JDBC` và `POOLED` trong ví dụ là các thành phần cấu hình của MyBatis lõi. Các placeholder `${jdbc.*}` ở file cấu hình được nhận từ `Properties` khi tạo factory. Đây là cơ chế thay thế thuộc tính cấu hình; không nên nhầm nó với cách nội suy `${...}` trong câu SQL.

### 4.2. Mở phiên và điều khiển giao dịch

```java
package com.example.catalog;

import java.io.IOException;
import java.io.Reader;
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Properties;
import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import com.example.catalog.mapper.ProductMapper;

public class CoreDemo {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();
        properties.setProperty("jdbc.url", requiredEnv("DEMO_JDBC_URL"));
        properties.setProperty("jdbc.username", requiredEnv("DEMO_JDBC_USER"));
        properties.setProperty("jdbc.password", requiredEnv("DEMO_JDBC_PASSWORD"));

        SqlSessionFactory factory;
        try (Reader reader = Resources.getResourceAsReader("mybatis-config.xml")) {
            factory = new SqlSessionFactoryBuilder().build(reader, properties);
        }

        try (SqlSession session = factory.openSession(false)) {
            ProductMapper mapper = session.getMapper(ProductMapper.class);
            try {
                int first = mapper.updatePrice(1L, new BigDecimal("700000.00"));
                int second = mapper.updatePrice(2L, new BigDecimal("230000.00"));
                if (first != 1 || second != 1) {
                    throw new IllegalStateException("Không tìm thấy đủ hai sản phẩm");
                }
                session.commit();
            } catch (RuntimeException ex) {
                session.rollback();
                throw ex;
            }
        }
    }

    private static String requiredEnv(String name) {
        return Objects.requireNonNull(System.getenv(name), "Thiếu biến " + name);
    }
}
```

`openSession(false)` chỉ rõ phiên không dùng auto-commit. Hai lần cập nhật nằm trong đơn vị công việc do ứng dụng quản lý: thành công thì commit; lỗi thì rollback; `try-with-resources` đóng phiên.

Việc đăng ký tài nguyên Mapper trong cấu hình cho phép MyBatis nạp câu lệnh và liên kết với interface có `namespace` tương ứng. Trong một ứng dụng chạy lâu dài, factory cần được giữ lại để dùng chung, thay vì xây dựng lại cho mỗi yêu cầu.

Cách này phù hợp với chương trình Java thuần hoặc công cụ xử lý dữ liệu nhỏ khi ứng dụng chủ động quản lý tài nguyên và giao dịch. Khi chương trình mở rộng, trách nhiệm quản lý đó vẫn phải được thực hiện đầy đủ.

## 5. Phương án B: dùng MyBatis-Spring trong ứng dụng Spring

Khi ứng dụng đã dùng Spring, ta thường muốn inject `ProductMapper` vào service và dùng `@Transactional` cho ranh giới nghiệp vụ. MyBatis-Spring cung cấp cầu nối này.

Ngoài MyBatis lõi và JDBC driver, phương án sau cần MyBatis-Spring cùng các thành phần Spring cho container, JDBC và giao dịch, chẳng hạn `spring-context` và `spring-jdbc` với các phụ thuộc liên quan. Không cần Spring Boot để sử dụng chúng.

### 5.1. Những thành phần được bổ sung

- `SqlSessionFactoryBean` tạo factory từ `DataSource`, Mapper XML và các cấu hình liên quan.
- `SqlSessionTemplate` điều phối lời gọi MyBatis với phiên được quản lý theo ngữ cảnh Spring; nó có thể được dùng chung giữa các luồng theo thiết kế tích hợp.
- `@MapperScan` đăng ký các interface Mapper thành bean để inject.
- Transaction manager của Spring điều khiển giao dịch; MyBatis-Spring tham gia giao dịch đó thay vì tự tạo một ranh giới độc lập cho mỗi thao tác.

MyBatis-Spring còn hỗ trợ chuyển các ngoại lệ truy cập dữ liệu thích hợp sang hệ thống `DataAccessException` của Spring qua cơ chế dịch ngoại lệ. Điều đó không làm mất nhu cầu phân tích nguyên nhân JDBC hoặc SQL gốc khi xử lý lỗi.

### 5.2. Cấu hình Spring bằng Java

```java
package com.example.catalog.springplain;

import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import com.example.catalog.mapper.ProductMapper;

@Configuration
@EnableTransactionManagement
@ComponentScan("com.example.catalog.service")
@MapperScan(
    basePackageClasses = ProductMapper.class,
    sqlSessionTemplateRef = "sqlSessionTemplate"
)
public class PersistenceConfig {
    @Bean
    public DataSource dataSource(Environment environment) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(environment.getRequiredProperty("DEMO_JDBC_URL"));
        dataSource.setUsername(environment.getRequiredProperty("DEMO_JDBC_USER"));
        dataSource.setPassword(environment.getRequiredProperty("DEMO_JDBC_PASSWORD"));
        return dataSource;
    }

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource) throws Exception {
        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(dataSource);
        factoryBean.setMapperLocations(
            new PathMatchingResourcePatternResolver()
                .getResources("classpath*:mappers/**/*.xml")
        );
        return factoryBean.getObject();
    }

    @Bean
    public SqlSessionTemplate sqlSessionTemplate(SqlSessionFactory factory) {
        return new SqlSessionTemplate(factory);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

`DriverManagerDataSource` được dùng để ví dụ ngắn và dễ theo dõi; nó không phải connection pool. Ứng dụng cần pooling có thể cung cấp một `DataSource` có pool phù hợp mà không phải đổi interface Mapper hoặc SQL.

Factory và transaction manager ở đây dùng **cùng một `DataSource`**. Đây là điều kiện quan trọng để chúng phối hợp trong cùng giao dịch. `SqlSessionFactoryBean` mặc định sử dụng cơ chế giao dịch tích hợp Spring của MyBatis-Spring; không chuyển nguyên cấu hình `<environments>` dùng `JDBC` ở phương án Java thuần vào ví dụ này.

### 5.3. Service với ranh giới giao dịch

```java
package com.example.catalog.service;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.example.catalog.mapper.ProductMapper;

@Service
public class PriceService {
    private final ProductMapper mapper;

    public PriceService(ProductMapper mapper) {
        this.mapper = mapper;
    }

    @Transactional
    public void changeTwoPrices(
        long firstId, BigDecimal firstPrice,
        long secondId, BigDecimal secondPrice
    ) {
        updateRequired(firstId, firstPrice);
        updateRequired(secondId, secondPrice);
    }

    private void updateRequired(long id, BigDecimal price) {
        if (mapper.updatePrice(id, price) != 1) {
            throw new IllegalStateException("Không tìm thấy sản phẩm " + id);
        }
    }
}
```

Ví dụ gọi service từ container Spring:

```java
try (var context = new org.springframework.context.annotation.AnnotationConfigApplicationContext(
        com.example.catalog.springplain.PersistenceConfig.class)) {
    var service = context.getBean(com.example.catalog.service.PriceService.class);
    service.changeTwoPrices(
        1L, new java.math.BigDecimal("700000.00"),
        2L, new java.math.BigDecimal("230000.00")
    );
}
```

Đoạn gọi dùng cú pháp `var`, nên cần Java hỗ trợ cú pháp này. Service được lấy từ Spring để lời gọi đi qua proxy giao dịch. Nếu lần cập nhật thứ hai phát sinh `IllegalStateException`, giao dịch rollback cả thay đổi thứ nhất.

Mặc định của `@Transactional` là rollback khi có `RuntimeException` hoặc `Error` thoát khỏi phương thức qua interceptor giao dịch. Checked exception cần được xem xét với quy tắc rollback tương ứng, chẳng hạn `rollbackFor`, nếu nghiệp vụ yêu cầu. Việc bắt rồi bỏ qua ngoại lệ có thể làm thay đổi kết quả mong đợi.

Trong mô hình proxy thông thường, lời gọi một phương thức `@Transactional` từ phương thức khác trong cùng đối tượng không tự đi qua proxy. Chỉ thêm annotation vào mã nguồn chưa đủ để bảo đảm ranh giới giao dịch đã được áp dụng.

### 5.4. Điều gì xảy ra khi gọi Mapper?

```text
Bên gọi
    -> proxy giao dịch của Spring
    -> PriceService
    -> Mapper được inject
    -> SqlSessionTemplate
    -> SqlSession gắn với giao dịch hiện tại
    -> Executor của MyBatis
    -> JDBC Connection của DataSource
```

Trong giao dịch Spring với cấu hình phù hợp, MyBatis-Spring phối hợp việc dùng phiên và connection với giao dịch hiện hành. Khi giao dịch kết thúc, cơ chế quản lý tài nguyên thực hiện commit/rollback và giải phóng tài nguyên tương ứng.

Vì thế, service không gọi `commit()`, `rollback()` hoặc `close()` trên `SqlSessionTemplate`. Cũng không mở thêm một `SqlSession` thủ công chỉ để thực thi SQL trong phương thức nghiệp vụ đã được Spring quản lý.

Nếu gọi Mapper qua cơ chế này bên ngoài giao dịch Spring, mỗi lời gọi được quản lý và hoàn tất riêng; không được giả định hai lần gọi liên tiếp sẽ tự tạo thành một giao dịch nghiệp vụ chung. Với cấu hình chuẩn của `SqlSessionTemplate`, lời gọi ngoài giao dịch được commit sau khi thực thi thành công.

## 6. Phương án C: dùng MyBatis Spring Boot Starter

Starter phù hợp khi ứng dụng sử dụng Spring Boot và muốn khai thác cơ chế tự cấu hình của Boot. Thay vì tự viết toàn bộ `PersistenceConfig` ở phần trước, ứng dụng khai báo Starter, cung cấp nguồn dữ liệu và chỉ rõ phạm vi Mapper cần dùng.

Với cấu hình Boot phù hợp, Starter có thể:

- Sử dụng `DataSource` có trong Spring context.
- Tạo `SqlSessionFactory` nếu ứng dụng chưa tự cung cấp factory tương ứng và thỏa điều kiện cấu hình.
- Tạo `SqlSessionTemplate` khi phù hợp với các bean hiện có.
- Áp dụng các thuộc tính `mybatis.*` và hỗ trợ đăng ký Mapper.

Boot và các thành phần JDBC/giao dịch liên quan cung cấp phần tự cấu hình nguồn dữ liệu và transaction manager khi đủ điều kiện. Không nên quy mọi chức năng của Spring Boot cho riêng Starter MyBatis.

### 6.1. Phụ thuộc và cấu hình

Phụ thuộc tích hợp chính là:

```text
org.mybatis.spring.boot:mybatis-spring-boot-starter
```

Dự án cũng cần JDBC driver PostgreSQL. Phiên bản Starter phải phù hợp với dòng Spring Boot của dự án; không suy ra sự tương thích chỉ từ việc số phiên bản của hai thư viện trông giống nhau. Đồng thời, không tự thêm các phiên bản MyBatis-Spring hoặc MyBatis lõi khác với bộ phụ thuộc đã chọn khi chưa có lý do và kiểm chứng tương thích.

Ví dụ `application.yml`:

```yaml
spring:
  datasource:
    url: ${DEMO_JDBC_URL}
    username: ${DEMO_JDBC_USER}
    password: ${DEMO_JDBC_PASSWORD}

mybatis:
  mapper-locations: classpath*:mappers/**/*.xml
```

Các khóa có vai trò khác nhau:

| Khóa | Vai trò |
| --- | --- |
| `spring.datasource.*` | Cung cấp thông tin để cấu hình `DataSource` trong ứng dụng Boot |
| `mybatis.mapper-locations` | Chỉ vị trí tài nguyên XML chứa các câu lệnh và ánh xạ MyBatis |

Trong ví dụ, không cần khai báo lại `mybatis-config.xml` của phương án Java thuần. `DataSource` do Spring quản lý; các Mapper XML vẫn là tài nguyên riêng được nạp vào factory.

Nếu cần cấu hình MyBatis bằng file XML trong Boot, có thể sử dụng `mybatis.config-location` với một file cấu hình thích hợp cho môi trường Spring. Cần phân biệt file cấu hình chung này với các file Mapper được trỏ bởi `mybatis.mapper-locations`. Không dùng cấu hình `<environments>` của ứng dụng Java thuần để tạo thêm một nguồn dữ liệu ngoài cơ chế quản lý của Spring.

### 6.2. Khai báo phạm vi Mapper rõ ràng

```java
package com.example.catalog;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import com.example.catalog.mapper.ProductMapper;

@SpringBootApplication
@MapperScan(basePackageClasses = ProductMapper.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Ở phương án Boot, dùng lớp khởi động này cùng `PriceService` và bộ Mapper chung; không đưa thêm `PersistenceConfig` của phương án Spring thủ công vào cùng ứng dụng. Nếu giữ cả hai cấu hình, các bean tự khai báo có thể thay đổi hoặc làm mất tác dụng của một số phần tự cấu hình, khiến ví dụ không còn minh họa cách dùng Starter tối thiểu.

`@MapperScan` xác định package của `ProductMapper` để tìm interface cần đăng ký. Khi sử dụng cơ chế quét mặc định của Starter, một cách khác là đánh dấu các interface bằng `org.apache.ibatis.annotations.Mapper` trong phạm vi package được Boot xác định. Ví dụ:

```java
@org.apache.ibatis.annotations.Mapper
public interface ProductMapper {
    // Các phương thức Mapper của ứng dụng.
}
```

Đây là hai cách đăng ký cần lựa chọn và hiểu phạm vi quét, không phải yêu cầu bắt buộc đặt cả hai annotation. Với ví dụ hoàn chỉnh trong bài, `@MapperScan` đã đăng ký interface nên không cần thêm `@Mapper`.

Cần tách bạch hai công việc:

- **Quét interface Mapper** để có bean phục vụ dependency injection.
- **Nạp Mapper XML** để có câu lệnh và `resultMap` cho interface đó.

Một interface đã được quét vẫn có thể thiếu câu SQL nếu tài nguyên XML chưa được nạp. Ngược lại, một file XML nằm trên classpath không tự bảo đảm ứng dụng đã có bean Mapper để inject ở mọi cấu hình.

### 6.3. Tự cấu hình có điều kiện

Tự cấu hình hoạt động dựa trên môi trường và các bean hiện hữu. Vì vậy cần chú ý:

- Có `DataSource` phù hợp thì việc tạo factory tự động mới có nền tảng để thực hiện. Khi có nhiều `DataSource`, cần xác định nguồn mặc định hoặc cấu hình rõ factory và nhóm Mapper tương ứng.
- Khi ứng dụng tự cung cấp `SqlSessionFactory` hoặc `SqlSessionTemplate`, một số bean mặc định sẽ không được tạo lại. Không giả định mọi thuộc tính `mybatis.*` đều tự áp dụng vào một factory mà ứng dụng tự xây dựng hoàn toàn.
- Với nhiều cơ sở dữ liệu, cần ghép đúng `DataSource`, factory/template, transaction manager và phạm vi Mapper. Một Starter không tự suy ra ranh giới nghiệp vụ giữa các nguồn dữ liệu.

Starter giúp giảm cấu hình ban đầu. Quyền quyết định SQL, mô hình ánh xạ và giao dịch nghiệp vụ vẫn thuộc về cấu hình và mã của ứng dụng.

## 7. So sánh vòng đời phiên và giao dịch

| Tình huống | Phiên được lấy từ đâu? | Ai quyết định hoàn tất giao dịch? | Cách sử dụng đúng |
| --- | --- | --- | --- |
| Java thuần dùng `openSession(false)` | Ứng dụng mở trực tiếp từ factory | Mã ứng dụng gọi commit/rollback | Đóng phiên sau đơn vị công việc; không dùng chung phiên giữa các luồng |
| Spring dùng Mapper trong `@Transactional` | MyBatis-Spring phối hợp với ngữ cảnh giao dịch | Spring transaction manager theo ranh giới đã thiết lập | Inject Mapper; gọi service qua cơ chế giao dịch của Spring |
| Spring dùng Mapper ngoài giao dịch | Cơ chế tích hợp quản lý riêng cho lời gọi | `SqlSessionTemplate` hoàn tất lời gọi ngoài giao dịch theo cơ chế của nó | Không kỳ vọng nhiều lời gọi tự có tính nguyên tử chung |
| Boot Starter trong `@Transactional` | Vẫn là cơ chế MyBatis-Spring | Vẫn là transaction manager của Spring | Hiểu bean và điều kiện tự cấu hình; khai báo ranh giới nghiệp vụ |

`SqlSessionTemplate` có thể được dùng chung không có nghĩa mọi lời gọi dùng một `SqlSession` hay một JDBC connection duy nhất. Tính an toàn của template đến từ cách nó điều phối phiên, không phải từ việc biến `DefaultSqlSession` thành đối tượng có thể chia sẻ tùy ý.

Sự khác biệt vòng đời cũng ảnh hưởng đến các chủ đề nâng cao. Chẳng hạn cache cấp một của MyBatis gắn với `SqlSession`; không thể chỉ nhìn một bean Mapper dùng chung rồi kết luận các lần gọi ngoài giao dịch cùng dùng một cache phiên. Batch và cache vẫn là tính năng của lõi, nhưng kết quả thực tế còn phụ thuộc cách tổ chức phiên và giao dịch.

## 8. Những nhầm lẫn thường gặp

### 8.1. “Có Starter thì không cần viết SQL”

Starter không sinh ra các truy vấn nghiệp vụ như một hệ thống repository tự suy luận tên phương thức. Với MyBatis trong phạm vi bài này, ứng dụng vẫn khai báo statement thông qua XML, annotation hoặc SQL provider. Nếu `ProductMapper.updatePrice` không có statement tương ứng, thêm Starter không giải quyết được lỗi đó.

### 8.2. “Đã có `@Mapper` thì tự có giao dịch”

`@Mapper` là dấu hiệu nhận diện interface trong cơ chế đăng ký phù hợp. Nó không mở giao dịch nghiệp vụ. Hai lần cập nhật cần cùng thành công hoặc cùng thất bại phải nằm trong ranh giới giao dịch được thiết lập đúng.

### 8.3. “XML Mapper là cấu hình kết nối cơ sở dữ liệu”

XML Mapper chứa statement và ánh xạ. Trong Java thuần, cấu hình môi trường có thể nằm ở `mybatis-config.xml`. Trong Spring/Boot, `DataSource` thường do Spring quản lý. Không trộn lẫn các vai trò chỉ vì tất cả đều là file cấu hình.

### 8.4. “Thêm `@Transactional` ở đâu cũng được”

Annotation cần cơ chế xử lý giao dịch hoạt động, bean được quản lý và lời gọi đi qua đường áp dụng giao dịch phù hợp. Việc tự tạo `new PriceService(...)`, tự mở phiên khác hoặc gọi nội bộ trong cùng đối tượng có thể khiến thao tác chạy ngoài ranh giới dự kiến.

### 8.5. “Starter tự tạo bảng và tối ưu truy vấn”

Starter không tự suy schema từ `Product`, không tạo index dựa trên câu truy vấn và không tự loại bỏ N+1. Tạo schema cần cơ chế khởi tạo hoặc migration được cấu hình riêng. Tối ưu SQL vẫn cần đo đạc, xem kế hoạch thực thi và kiểm thử với dữ liệu phù hợp.

## 9. Chẩn đoán theo đúng lớp trách nhiệm

Khi ứng dụng lỗi, hãy xác định vấn đề thuộc lớp nào trước khi thay thư viện hoặc thêm cấu hình.

| Biểu hiện | Lớp cần kiểm tra trước | Điểm kiểm tra cụ thể |
| --- | --- | --- |
| Không inject được `ProductMapper` | Đăng ký bean qua Spring/MyBatis-Spring | Package quét, `@MapperScan`, annotation nhận diện, cấu hình đã được nạp |
| `Invalid bound statement (not found)` | Đăng ký statement của MyBatis lõi | Mapper XML đã nạp chưa; `namespace` và `id` có khớp interface/phương thức không |
| Không tạo được `DataSource` hoặc không kết nối được | Cấu hình JDBC/Spring Boot và cơ sở dữ liệu | Driver, URL, biến môi trường, quyền kết nối, trạng thái máy chủ |
| Ánh xạ thiếu hoặc sai thuộc tính | Cấu hình MyBatis lõi | Tên cột, `resultMap`, kiểu Java, TypeHandler và giá trị thực tế |
| Lần cập nhật trước không rollback khi lần sau lỗi | Tích hợp giao dịch | Service có được gọi qua proxy không; cùng `DataSource` không; có nuốt ngoại lệ không |
| Khai báo thuộc tính nhưng factory không nhận | Cách tạo factory trong Boot | Factory do tự cấu hình tạo hay ứng dụng tự khai báo; thuộc tính có được áp dụng vào factory đó không |

Ví dụ kiểm chứng giao dịch với bộ dữ liệu trên: gọi `changeTwoPrices(1L, ..., 999L, ...)` khi sản phẩm `999` không tồn tại. Với ranh giới giao dịch Spring được áp dụng đúng, cập nhật cho sản phẩm `1` phải được rollback khi service ném `IllegalStateException`. Cần kiểm tra giá trị đã lưu bằng một thao tác đọc độc lập sau khi giao dịch kết thúc; chỉ nhìn thấy annotation hoặc không thấy lỗi khởi động chưa chứng minh được hành vi rollback.

## 10. Chọn thành phần theo môi trường ứng dụng

| Môi trường | Cách tiếp cận phù hợp | Trách nhiệm cần nắm |
| --- | --- | --- |
| Java thuần, CLI hoặc ví dụ học JDBC/MyBatis | Bắt đầu từ MyBatis lõi | Tạo factory, quản lý session, commit/rollback và đóng tài nguyên |
| Ứng dụng Spring không sử dụng Boot | MyBatis lõi kết hợp MyBatis-Spring | Khai báo bean, Mapper scanning, `DataSource` và transaction manager |
| Ứng dụng Spring Boot | Starter tương thích với phiên bản Boot của dự án | Cấu hình thuộc tính, phạm vi Mapper, ranh giới giao dịch và điều kiện tự cấu hình |
| Spring/Boot với nhiều nguồn dữ liệu hoặc yêu cầu tùy biến | Dùng tích hợp Spring và khai báo rõ các thành phần cần kiểm soát | Ghép đúng Mapper với factory/template và transaction manager của từng nguồn |

Khi chuyển từ cấu hình Spring thủ công sang Starter, phần thường được giản lược là mã tạo bean. Câu SQL, interface Mapper và `resultMap` có thể tiếp tục sử dụng nếu giữ nguyên hợp đồng ánh xạ. Cần kiểm chứng lại cách nạp tài nguyên, nguồn dữ liệu và hành vi giao dịch sau khi thay cấu hình.

Ba trách nhiệm cần nhớ là: **MyBatis lõi xử lý SQL và ánh xạ; MyBatis-Spring phối hợp với Spring; Starter chuẩn bị và tự cấu hình cách tích hợp trong Spring Boot.** Nắm được ranh giới đó giúp xác định đúng nơi cấu hình, tránh quản lý phiên sai và đọc lỗi truy cập dữ liệu có căn cứ.