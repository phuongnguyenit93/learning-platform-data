# Phân biệt thuộc tính cấu hình chuẩn và thuộc tính riêng của provider trong Persistence Unit

Khi cấu hình JPA, ta thường thấy các tên như `jakarta.persistence.jdbc.url`, `jakarta.persistence.schema-generation.database.action`, `hibernate.jdbc.batch_size` hay `eclipselink.logging.level` nằm cạnh nhau trong `persistence.xml`. Chúng đều có thể được truyền tới bộ triển khai JPA, nhưng **không thuộc cùng một tiêu chuẩn**.

- **Thuộc tính cấu hình chuẩn** được Jakarta Persistence/JPA đặc tả: có tên, kiểu giá trị và ý nghĩa được chuẩn hóa trong phạm vi đặc tả. Mục tiêu là viết cấu hình có khả năng chuyển đổi giữa các provider phù hợp.
- **Thuộc tính riêng của provider** do một bộ triển khai cụ thể định nghĩa, chẳng hạn Hibernate hoặc EclipseLink. Chúng điều khiển những khả năng, tối ưu và hành vi đặc thù; provider khác không có nghĩa vụ hiểu chúng.

Phân biệt hai loại này là kỹ năng quan trọng khi thiết kế **Persistence Unit**, đọc `persistence.xml`, di chuyển từ Hibernate sang EclipseLink, nâng cấp Jakarta Persistence, hoặc tìm nguyên nhân tại sao một thiết lập không phát huy tác dụng.

## 1. Persistence Unit và các tầng cấu hình

### Persistence Unit là gì?

*Persistence Unit* (PU) là một đơn vị cấu hình JPA có tên, xác định tập entity, tài nguyên dữ liệu, kiểu quản lý giao dịch và các thiết lập dành cho quá trình persistence. Trong Java SE, một PU thường được khai báo trong:

~~~text
src/main/resources/
└── META-INF/
    └── persistence.xml
~~~

Ví dụ một ứng dụng khai báo PU tên `shopPU`, sau đó bootstrap:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("shopPU");
~~~

`EntityManagerFactory` được tạo theo cấu hình của PU. Từ đó ứng dụng tạo/lấy `EntityManager` để quản lý entity. PU không phải một entity, và cũng không phải một JDBC connection.

### Ba tầng thường xuất hiện trong cùng dự án

~~~text
Cấu hình ứng dụng / framework
   ví dụ spring.datasource.*, spring.jpa.*
                    |
                    v
Jakarta Persistence / JPA
   persistence.xml, <persistence-unit>, jakarta.persistence.*
                    |
                    v
JPA provider
   Hibernate: hibernate.*
   EclipseLink: eclipselink.*
                    |
                    v
Driver JDBC, connection pool, cơ sở dữ liệu
~~~

Tầng phía trên có thể chuyển đổi cấu hình thành thuộc tính hoặc đối tượng mà tầng dưới hiểu được. Vì thế không nên phân loại một khóa chỉ bằng việc nó nằm trong file nào. **Tên thuộc tính và bên định nghĩa ý nghĩa của nó** mới là tiêu chí phân biệt.

Ví dụ `spring.jpa.properties.hibernate.jdbc.batch_size` là khóa cấu hình của Spring Boot; phần `hibernate.jdbc.batch_size` mới là thuộc tính được chuyển cho Hibernate. Nó không trở thành thuộc tính chuẩn JPA chỉ vì được viết trong cấu hình ứng dụng Spring Boot.

## 2. Thuộc tính cấu hình chuẩn: hợp đồng chung của Jakarta Persistence

Một thuộc tính thuộc nhóm chuẩn khi đặc tả Jakarta Persistence quy định nó và provider phù hợp được kỳ vọng xử lý theo các quy tắc của đặc tả. Với Jakarta Persistence 3.x, nhiều thuộc tính chuẩn dùng tiền tố `jakarta.persistence.`.

Các nhóm tiêu biểu:

| Nhóm | Tên chuẩn | Vai trò |
|---|---|---|
| Kết nối JDBC | `jakarta.persistence.jdbc.driver` | Tên lớp JDBC driver khi kết nối bằng thông tin JDBC |
| Kết nối JDBC | `jakarta.persistence.jdbc.url` | JDBC URL |
| Kết nối JDBC | `jakarta.persistence.jdbc.user` | Tên người dùng cơ sở dữ liệu |
| Kết nối JDBC | `jakarta.persistence.jdbc.password` | Mật khẩu cơ sở dữ liệu |
| Tạo schema | `jakarta.persistence.schema-generation.database.action` | Chọn hành động tạo/xóa schema trong cơ sở dữ liệu |
| Tạo script DDL | `jakarta.persistence.schema-generation.scripts.action` | Chọn hành động sinh script DDL |
| Nguồn schema | `jakarta.persistence.schema-generation.create-source` | Chọn nguồn dùng khi tạo schema, chẳng hạn metadata hoặc script |
| Nguồn schema | `jakarta.persistence.schema-generation.drop-source` | Chọn nguồn dùng khi xóa schema |
| Validation | `jakarta.persistence.validation.mode` | Điều khiển chế độ Bean Validation khi tích hợp validation |
| Timeout (hint) | `jakarta.persistence.query.timeout` | Gợi ý timeout thực thi truy vấn, thường tính bằng mili giây |
| Timeout (hint) | `jakarta.persistence.lock.timeout` | Gợi ý thời gian chờ khóa, tính bằng mili giây |

**Lưu ý về phạm vi:** Hai khóa `jakarta.persistence.query.timeout` và `jakarta.persistence.lock.timeout` cũng được dùng làm *query hints* trong khi chạy chương trình. Tính chuẩn của tên hint không bảo đảm mọi database/driver hỗ trợ và thực thi timeout giống hệt nhau. Tùy đặc tả và provider, hint không được hỗ trợ có thể bị bỏ qua.

Có những cơ chế chuẩn khác được khai báo bằng **phần tử XML**, không nhất thiết là một thuộc tính có tên `jakarta.persistence.*`. Ví dụ:

| Phần tử trong `persistence.xml` | Ý nghĩa |
|---|---|
| `<persistence-unit name="...">` | Đặt tên PU |
| `<provider>` | Chọn lớp triển khai PersistenceProvider |
| `<jta-data-source>` / `<non-jta-data-source>` | Chỉ định nguồn kết nối được quản lý phù hợp |
| `<class>` | Đăng ký lớp entity |
| `<mapping-file>` | Khai báo tài liệu ORM mapping XML |
| `<shared-cache-mode>` | Chính sách shared cache chuẩn |
| `<validation-mode>` | Chế độ Bean Validation |
| `<properties>` / `<property>` | Nơi khai báo các cặp tên–giá trị |

Nói cách khác, **cấu trúc `persistence.xml` cũng do đặc tả JPA quy định**, dù nội dung một số `<property>` bên trong có thể là phần mở rộng của provider.

### 2.1. Ví dụ cấu hình chuẩn trong `persistence.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">

    <persistence-unit name="shopPU"
                      transaction-type="RESOURCE_LOCAL">

        <class>com.example.domain.Customer</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <shared-cache-mode>NONE</shared-cache-mode>
        <validation-mode>AUTO</validation-mode>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/shop"/>

            <property name="jakarta.persistence.schema-generation.database.action"
                      value="none"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Những điểm cần chú ý:

1. `<persistence>`, `<persistence-unit>`, `<class>`, `<shared-cache-mode>` và `<properties>` là các thành phần của định dạng chuẩn.
2. `jakarta.persistence.jdbc.*` và `jakarta.persistence.schema-generation.database.action` là tên thuộc tính chuẩn.
3. `org.postgresql.Driver` và chuỗi JDBC URL mô tả **driver/database cụ thể**; việc tên thuộc tính là chuẩn không có nghĩa giá trị kết nối dùng được với mọi DB.
4. Cấu hình dùng `RESOURCE_LOCAL` để minh họa bootstrap Java SE. Trong môi trường JTA/container, cách khai báo datasource và quản lý giao dịch có thể khác.
5. Tài khoản và mật khẩu được cố ý bỏ khỏi XML ví dụ. Trong ứng dụng thực, nên đưa thông tin nhạy cảm qua cơ chế cấu hình an toàn của môi trường triển khai.

`version="3.1"` ở đây là ví dụ cho Jakarta Persistence 3.1. Khi triển khai thực tế, lựa chọn phiên bản schema XML, API và provider tương thích với nhau; không nâng version của XML bằng cách đoán tên thuộc tính.

### 2.2. Ví dụ cấu hình tạo schema theo chuẩn

~~~xml
<properties>
    <property name="jakarta.persistence.schema-generation.database.action"
              value="none"/>

    <property name="jakarta.persistence.schema-generation.scripts.action"
              value="create"/>

    <property name="jakarta.persistence.schema-generation.scripts.create-target"
              value="schema-create.sql"/>
</properties>
~~~

Ý định của đoạn này là **không thực hiện DDL lên database** (`database.action=none`) nhưng yêu cầu provider sinh script tạo schema. Các giá trị action chuẩn thường gặp là `none`, `create`, `drop` và `drop-and-create`; không phải tùy chọn vendor nào cũng nằm trong tập giá trị chuẩn.

Với `create-source` hoặc `drop-source`, ta còn có thể điều khiển nguồn tạo DDL từ metadata và/hoặc script theo đặc tả. Đường dẫn script, định dạng và khả năng xử lý DDL phụ thuộc ngữ cảnh triển khai, provider và database.

Tạo schema tự động thường chỉ phù hợp cho học tập, thử nghiệm hoặc quá trình chuẩn bị môi trường được kiểm soát. Đối với schema production, nhiều dự án dùng công cụ migration như Flyway hoặc Liquibase để quản lý phiên bản thay đổi.

## 3. Thuộc tính riêng của provider: phần mở rộng không di động mặc định

*Provider* là bộ triển khai JPA, ví dụ Hibernate ORM và EclipseLink. Bên cạnh API chuẩn, provider cung cấp các thuộc tính riêng nhằm bật các tính năng hoặc tinh chỉnh hiệu năng.

### 3.1. Ví dụ Hibernate

| Thuộc tính Hibernate | Mục đích thường gặp |
|---|---|
| `hibernate.dialect` | Điều chỉnh cách tạo SQL theo dialect database; nhiều phiên bản Hibernate hiện đại có thể tự phát hiện |
| `hibernate.show_sql` | In SQL ra đầu ra thông thường, chủ yếu phục vụ phát triển |
| `hibernate.format_sql` | Định dạng SQL được in/log để dễ đọc |
| `hibernate.jdbc.batch_size` | Cấu hình batch cho các thao tác JDBC đủ điều kiện |
| `hibernate.order_inserts` | Sắp xếp các INSERT để tăng cơ hội batching |
| `hibernate.order_updates` | Sắp xếp các UPDATE theo một thứ tự có ích cho batching |
| `hibernate.default_batch_fetch_size` | Đặt kích thước mặc định cho một số thao tác batch fetching |
| `hibernate.generate_statistics` | Thu thập thống kê hoạt động Hibernate |
| `hibernate.hbm2ddl.auto` | Điều khiển các thao tác xử lý schema của Hibernate như validate, update, create |
| `hibernate.cache.use_second_level_cache` | Điều khiển hành vi cache cấp hai theo cấu hình Hibernate |

Ví dụ trong cùng PU:

~~~xml
<properties>
    <property name="jakarta.persistence.jdbc.url"
              value="jdbc:postgresql://localhost:5432/shop"/>

    <property name="hibernate.jdbc.batch_size"
              value="30"/>
    <property name="hibernate.order_inserts"
              value="true"/>
    <property name="hibernate.show_sql"
              value="false"/>
</properties>
~~~

Dòng JDBC URL là **thuộc tính chuẩn JPA**; ba dòng `hibernate.*` là **thuộc tính riêng Hibernate**. Chúng có thể cùng nằm trong `<properties>` vì cấu trúc XML chỉ định nơi chuyển các cặp tên/giá trị cho provider. **Vị trí trong XML không biến phần mở rộng Hibernate thành chuẩn JPA.**

Các khóa vendor có thể thay đổi hoặc khác ý nghĩa giữa các phiên bản. Ví dụ batch size là mong muốn tối ưu, không bảo đảm mọi lệnh INSERT sẽ được batch: chiến lược sinh ID, loại lệnh, driver và mapping có thể làm thay đổi kết quả thực tế.

### 3.2. Ví dụ EclipseLink

| Thuộc tính EclipseLink | Mục đích thường gặp |
|---|---|
| `eclipselink.target-database` | Cấu hình nền tảng cơ sở dữ liệu được EclipseLink nhắm đến |
| `eclipselink.logging.level` | Chọn mức ghi log trong EclipseLink |
| `eclipselink.ddl-generation` | Cấu hình việc tạo/xóa DDL theo cơ chế EclipseLink |
| `eclipselink.weaving` | Điều chỉnh cơ chế weaving/enhancement hỗ trợ các tính năng ORM |
| `eclipselink.jdbc.batch-writing` | Điều chỉnh batching ghi JDBC theo cơ chế EclipseLink |

Ví dụ:

~~~xml
<properties>
    <property name="jakarta.persistence.jdbc.url"
              value="jdbc:postgresql://localhost:5432/shop"/>

    <property name="eclipselink.logging.level"
              value="FINE"/>
    <property name="eclipselink.ddl-generation"
              value="none"/>
</properties>
~~~

Tên `eclipselink.*` không tương đương một-một với tên `hibernate.*`. Hai provider có thể cung cấp tính năng giống mục đích, nhưng giá trị, thuật toán, giới hạn và điều kiện áp dụng khác nhau. Khi đổi provider, cần chọn cấu hình tương ứng dựa vào tài liệu của phiên bản đích.

### 3.3. Bảng so sánh khái quát

| Tiêu chí | Thuộc tính chuẩn JPA | Thuộc tính riêng provider |
|---|---|---|
| Bên định nghĩa | Đặc tả JPA/Jakarta Persistence | Nhà phát triển Hibernate, EclipseLink, … |
| Tiền tố thường gặp | `jakarta.persistence.*` trong Jakarta Persistence 3.x | `hibernate.*`, `eclipselink.*`, … |
| Tính di động | Được chuẩn hóa trong phạm vi đặc tả | Cần xử lý khi chuyển provider |
| Phạm vi tính năng | Kết nối, validation, schema generation, hints và các khả năng mà đặc tả định nghĩa | Tuning batching, log, dialect, cache, schema tools và các khả năng riêng |
| Đảm bảo hoạt động | Theo ngữ nghĩa đặc tả, có xét điều kiện hỗ trợ được đặc tả cho phép | Theo phiên bản và tài liệu vendor |
| Khi nâng cấp | Đối chiếu phiên bản API/đặc tả JPA | Đối chiếu thêm tài liệu nâng cấp của provider |
| Khi đổi provider | Có khả năng giữ lại nhiều tên và giá trị chuẩn | Cần rà soát, thay thế hoặc bỏ đi |

Không nên suy ra **“chuẩn” đồng nghĩa với “có cùng mọi hiệu ứng trên mọi database”**. Chẳng hạn, cú pháp DDL, khóa và timeout còn chịu ảnh hưởng của database, driver và những khoảng linh hoạt trong đặc tả.

## 4. Phân biệt tên chuẩn, tên cũ và tên framework

### 4.1. `javax.persistence.*` và `jakarta.persistence.*`

Một nguồn nhầm lẫn lớn là sự chuyển đổi namespace từ Java Persistence API/JPA 2.x sang Jakarta Persistence 3.x:

~~~text
JPA 2.x (Java EE / javax)
    javax.persistence.jdbc.url
    javax.persistence.schema-generation.database.action
    javax.persistence.query.timeout

Jakarta Persistence 3.x (Jakarta EE / jakarta)
    jakarta.persistence.jdbc.url
    jakarta.persistence.schema-generation.database.action
    jakarta.persistence.query.timeout
~~~

Tương tự, code entity và `EntityManager` ở thế hệ mới sử dụng `jakarta.persistence.Entity`, `jakarta.persistence.EntityManager`, thay cho `javax.persistence.*`.

Điều cần làm là **đồng bộ API, thư viện provider và cấu hình theo cùng thế hệ**. Không nên trộn các namespace vì một khóa cũ có thể không còn được nhận diện, hoặc chỉ được hỗ trợ qua cơ chế tương thích riêng. Những thuộc tính `hibernate.*` hoặc `eclipselink.*` không tự đổi tiền tố thành `jakarta.persistence.*` trong quá trình nâng cấp.

### 4.2. Thuộc tính Spring Boot không phải thuộc tính JPA chuẩn

Ví dụ file `application.properties` của Spring Boot:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_app
spring.datasource.hikari.maximum-pool-size=20

spring.jpa.properties.hibernate.jdbc.batch_size=30
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.hibernate.ddl-auto=validate
~~~

Phân loại:

- `spring.datasource.*`: cấu hình ứng dụng của **Spring Boot** để thiết lập `DataSource`.
- `spring.datasource.hikari.maximum-pool-size`: cấu hình pool HikariCP thông qua Spring Boot.
- `spring.jpa.properties.hibernate.jdbc.batch_size`: khóa **Spring Boot** có cơ chế chuyển phần `hibernate.jdbc.batch_size` sang Hibernate.
- `spring.jpa.hibernate.ddl-auto`: tiện ích cấu hình của **Spring Boot cho Hibernate**; không phải `jakarta.persistence.schema-generation.database.action`.

Do đó, phải đọc tài liệu đúng tầng. Một khóa hợp lệ trong `application.properties` chưa chắc là khóa có thể sao chép nguyên vẹn vào `persistence.xml`, và ngược lại.

### 4.3. `DataSource`/connection pool là tầng riêng

Chẳng hạn:

~~~xml
<persistence-unit name="shopJtaPU" transaction-type="JTA">
    <jta-data-source>java:comp/env/jdbc/ShopDS</jta-data-source>
    <!-- Entities, mapping và properties khác -->
</persistence-unit>
~~~

`<jta-data-source>` là phần tử chuẩn trỏ đến một nguồn kết nối do môi trường cung cấp, nhưng cách cấu hình pool, timeout mượn connection và giới hạn connection thuộc container/pool/framework. Không có quy tắc “mọi tùy chọn của pool đều có bản sao `jakarta.persistence.*`”.

Khi đã giao nguồn kết nối cho container, phải xem xét việc có cần đặt thêm `jakarta.persistence.jdbc.url`, `user` hoặc `password` hay không; tránh cấu hình hai nguồn có thể xung đột. Cơ chế ưu tiên dữ liệu kết nối phải theo môi trường triển khai và provider được sử dụng.

## 5. Cách provider đọc cấu hình của Persistence Unit

Một chương trình JPA có thể gửi các thuộc tính cho provider qua nhiều kênh:

1. `persistence.xml`: khai báo tĩnh và chọn PU bằng tên.
2. Bản đồ thuộc tính truyền lúc tạo `EntityManagerFactory` bằng `Persistence.createEntityManagerFactory(...)` trong cách bootstrap Java SE.
3. Cấu hình của container/framework: chuyển đổi thông tin thành PU, datasource, transaction manager hoặc thuộc tính provider.
4. Một số cấu hình/hint có thể đặt ở cấp `EntityManager` hoặc `Query` khi API cho phép.

Ví dụ truyền cấu hình lúc bootstrap:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

import java.util.HashMap;
import java.util.Map;

public class JpaBootstrap {
    public static EntityManagerFactory createFactory() {
        String password = System.getenv("SHOP_DB_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "Missing SHOP_DB_PASSWORD environment variable");
        }

        Map<String, Object> overrides = new HashMap<>();

        // Thuộc tính chuẩn Jakarta Persistence
        overrides.put("jakarta.persistence.jdbc.user", "shop_app");
        overrides.put("jakarta.persistence.jdbc.password", password);

        // Thuộc tính riêng Hibernate (chỉ dùng khi chọn Hibernate)
        overrides.put("hibernate.jdbc.batch_size", "30");

        return Persistence.createEntityManagerFactory(
                "shopPU", overrides);
    }
}
~~~

Đoạn code giả định `shopPU` có URL/driver tương thích đã được cung cấp và ứng dụng sử dụng bootstrap `RESOURCE_LOCAL`. Khi ứng dụng kết thúc, cần gọi `EntityManagerFactory.close()` ở điểm quản lý vòng đời thích hợp.

Thông thường, thuộc tính truyền lúc bootstrap có thể ghi đè giá trị tương ứng trong XML theo cơ chế JPA; tuy nhiên cách hợp nhất từ framework, nguồn cấu hình bên ngoài và các tiện ích vendor còn phụ thuộc vào môi trường. Không nên mặc định một thứ tự ưu tiên thống nhất cho mọi lớp cấu hình của mọi sản phẩm.

### Phân biệt thiết lập cấp PU với query hint

Một số khóa chuẩn còn tồn tại dưới dạng hint điều chỉnh hành vi truy vấn:

~~~java
var customers = entityManager
        .createQuery("SELECT c FROM Customer c", Customer.class)
        .setHint("jakarta.persistence.query.timeout", 2_000)
        .getResultList();
~~~

Ở đây `jakarta.persistence.query.timeout` là tên hint chuẩn được gắn cho truy vấn cụ thể, thời lượng tính bằng mili giây. Provider hoặc database có thể không hỗ trợ hoàn toàn, nên cần xác minh hành vi và quan sát timeout thực tế. Đây là thiết lập thuộc phạm vi truy vấn; không phải lúc nào cũng là một giá trị cấu hình PU mặc định có hiệu lực cho mọi query.

## 6. Tình huống lựa chọn: cùng một nhu cầu, hai cách cấu hình

### 6.1. Nhu cầu: điều khiển DDL

**Cách chuẩn JPA:**

~~~xml
<property name="jakarta.persistence.schema-generation.database.action"
          value="create"/>
~~~

**Cách riêng của Hibernate:**

~~~xml
<property name="hibernate.hbm2ddl.auto"
          value="create"/>
~~~

Cả hai có thể hướng tới việc tạo schema, nhưng **khác hợp đồng cấu hình**. Hibernate còn có các lựa chọn vendor như `validate` và `update`, không nên đưa nguyên những giá trị đó vào thuộc tính action chuẩn rồi kỳ vọng được hiểu.

**Tránh khai báo cả hai cơ chế schema generation với hành động mâu thuẫn**, chẳng hạn chuẩn yêu cầu `none` trong khi vendor yêu cầu `update`. Cách provider giải quyết xung đột giữa các thiết lập không phải một chính sách di động; hãy chọn một hướng chính, xác minh phiên bản và thử ở môi trường phù hợp.

### 6.2. Nhu cầu: xem SQL đã phát sinh

~~~xml
<property name="hibernate.show_sql" value="true"/>
<property name="hibernate.format_sql" value="true"/>
~~~

Đây là tính năng quan sát của Hibernate, **không có một cặp khóa chuẩn `jakarta.persistence.show_sql` và `jakarta.persistence.format_sql` tương ứng trong JPA**. Nếu dùng EclipseLink, phải chọn công cụ logging/cấu hình khác. Khi gỡ lỗi ứng dụng thực tế, logging SQL cùng tham số cần tuân thủ chính sách dữ liệu nhạy cảm.

### 6.3. Nhu cầu: tối ưu batch insert

~~~xml
<property name="hibernate.jdbc.batch_size" value="50"/>
<property name="hibernate.order_inserts" value="true"/>
~~~

Hai thuộc tính trên có thể giúp Hibernate tối ưu số lần round-trip JDBC trong các trường hợp đủ điều kiện. Chúng không quy định số lần `persist()` được gọi và không biến một transaction thành 50 transaction. Nếu đổi provider, hãy tìm tùy chọn batching tương ứng của provider mới, sau đó đo số SQL/round-trip và hiệu năng bằng dữ liệu thực tế.

### 6.4. Nhu cầu: bật Bean Validation

~~~xml
<validation-mode>AUTO</validation-mode>
~~~

Đây là phần tử chuẩn trong `persistence.xml`. Trong trường hợp phù hợp, `AUTO` cho phép tích hợp Bean Validation theo đặc tả nếu có validation provider; `CALLBACK` và `NONE` là các chế độ chuẩn khác. Chế độ validation không giống với quy tắc SQL `NOT NULL` hoặc việc tạo schema database.

## 7. Cách nhận diện một thuộc tính khi gặp trong dự án

Khi đọc một dòng cấu hình chưa quen, hãy kiểm tra theo trình tự:

1. **Nó được khai báo ở đâu?** `persistence.xml`, `application.properties`, cấu hình container hay code `setHint`?
2. **Ai định nghĩa tên khóa?** Đặc tả Jakarta Persistence, tài liệu Hibernate, EclipseLink, Spring Boot, HikariCP hay một thư viện khác?
3. **Tên có đúng với phiên bản đang dùng?** Nhất là `javax.persistence.*` so với `jakarta.persistence.*` hoặc thay đổi giữa các phiên bản Hibernate.
4. **Phạm vi hiệu lực là gì?** Toàn PU/`EntityManagerFactory`, datasource, transaction, `EntityManager` hay chỉ một query?
5. **Giá trị được chấp nhận và mặc định là gì?** Không suy đoán vì trông tương tự một key của vendor khác.
6. **Có tính di động hoặc yêu cầu hỗ trợ đặc biệt không?** Một tên chuẩn vẫn có thể chịu giới hạn từ database/driver; một key vendor chỉ có tác dụng trong provider thích hợp.

Nếu tài liệu nói “JPA property” một cách chung chung, hãy xem kỹ nó thực sự thuộc đặc tả hay chỉ là một cấu hình được nhà cung cấp cho phép truyền qua JPA.

### Một số lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân cần xem xét | Hướng kiểm tra |
|---|---|---|
| Tùy chọn batching không có tác dụng sau khi đổi provider | Vẫn giữ `hibernate.jdbc.batch_size` khi không còn dùng Hibernate | Tra tài liệu provider hiện tại; bỏ hoặc thay thuộc tính |
| Schema bất ngờ bị thay đổi khi chạy ứng dụng | Cấu hình schema generation của JPA và vendor chồng lấn hoặc chọn action nguy hiểm | Kiểm tra cả `jakarta.persistence.schema-generation.*` lẫn `hibernate.hbm2ddl.auto`/tương đương |
| Đặt một key nhưng provider dường như bỏ qua | Sai chính tả, sai namespace, sai phạm vi hoặc key không được hỗ trợ | Đối chiếu tài liệu theo phiên bản, bật log cấu hình và kiểm tra kết quả |
| Chuyển sang Jakarta Persistence 3.x rồi không nhận cấu hình cũ | Vẫn dùng tiền tố `javax.persistence.*` trong môi trường không có tương thích | Đồng bộ namespace API, XML và tên property chuẩn |
| Pool không tăng kích thước dù sửa JPA property | Điều chỉnh nhầm tầng ORM thay vì DataSource/pool | Xem cấu hình pool thực sự đang dùng, ví dụ HikariCP |
| Query timeout không hoạt động như dự kiến | Provider, driver hoặc database không thực thi timeout như kỳ vọng | Xem hỗ trợ hint và kiểm thử timeout thực tế |
| Dùng `create` hoặc `update` trên database có dữ liệu | Tưởng mọi cơ chế migration/schema đều tương đương | Dùng quy trình migration quản lý schema ở môi trường thật |

### Nếu đổi từ Hibernate sang EclipseLink

Giả sử PU đang có:

~~~xml
<properties>
    <property name="jakarta.persistence.jdbc.url"
              value="jdbc:postgresql://localhost:5432/shop"/>
    <property name="jakarta.persistence.jdbc.user"
              value="shop_app"/>
    <property name="jakarta.persistence.schema-generation.database.action"
              value="none"/>

    <property name="hibernate.show_sql" value="true"/>
    <property name="hibernate.jdbc.batch_size" value="30"/>
    <property name="hibernate.hbm2ddl.auto" value="validate"/>
</properties>
~~~

Cách phân tích:

- Ba khóa `jakarta.persistence.*` là phần cấu hình theo đặc tả; có thể giữ trong môi trường provider mới phù hợp, sau khi kiểm tra kết nối và hỗ trợ thực tế.
- Ba khóa `hibernate.*` là phần phụ thuộc Hibernate; phải đánh giá nhu cầu tương ứng theo EclipseLink, không tự động thay tiền tố.
- Ngoài thuộc tính, vẫn cần rà soát `<provider>`, thư viện trong classpath/module path, cách bootstrap, annotation/extension riêng và khác biệt SQL. Đổi các key chưa đủ chứng minh ứng dụng hoàn toàn di động.

Có thể nhóm cấu hình theo mục đích ngay trong file:

~~~xml
<properties>
    <!-- Chuẩn Jakarta Persistence -->
    <property name="jakarta.persistence.schema-generation.database.action"
              value="none"/>

    <!-- Chỉ dành cho Hibernate; rà soát khi thay provider -->
    <property name="hibernate.jdbc.batch_size" value="30"/>
    <property name="hibernate.generate_statistics" value="false"/>
</properties>
~~~

Nhận xét ngay cạnh nhóm vendor giúp người bảo trì nhận ra sự phụ thuộc mà không cần đoán từ tên file.

## 8. Bài tập tự kiểm tra

### Bài tập 1: phân loại từng dòng

Cho các khóa sau:

~~~properties
jakarta.persistence.jdbc.url=jdbc:postgresql://localhost:5432/shop
hibernate.show_sql=true
eclipselink.weaving=false
spring.datasource.hikari.maximum-pool-size=10
jakarta.persistence.schema-generation.database.action=none
spring.jpa.properties.hibernate.jdbc.batch_size=25
~~~

Phân loại:

| Dòng | Kết luận |
|---|---|
| `jakarta.persistence.jdbc.url` | Thuộc tính chuẩn Jakarta Persistence |
| `hibernate.show_sql` | Thuộc tính riêng Hibernate |
| `eclipselink.weaving` | Thuộc tính riêng EclipseLink |
| `spring.datasource.hikari.maximum-pool-size` | Thuộc tính Spring Boot cấu hình HikariCP |
| `jakarta.persistence.schema-generation.database.action` | Thuộc tính chuẩn Jakarta Persistence |
| `spring.jpa.properties.hibernate.jdbc.batch_size` | Khóa Spring Boot chuyển một thuộc tính riêng Hibernate xuống provider |

### Bài tập 2: dự đoán tính di động

PU sử dụng Hibernate và chỉ có các key:

~~~xml
<property name="jakarta.persistence.jdbc.url" value="jdbc:h2:mem:demo"/>
<property name="hibernate.format_sql" value="true"/>
~~~

Hỏi: khi thay Hibernate bằng một provider khác tương thích Jakarta Persistence, có thể giữ nguyên cả hai không?

**Gợi ý trả lời:** `jakarta.persistence.jdbc.url` là tên thuộc tính chuẩn, nhưng JDBC URL và driver vẫn phải hợp lệ với môi trường; `hibernate.format_sql` là phần mở rộng không được provider mới cam kết xử lý. Cần tìm cấu hình log của provider mới nếu vẫn muốn định dạng SQL.

### Bài tập 3: xác định phạm vi

Một lập trình viên đặt `spring.datasource.hikari.maximum-pool-size=20` và khẳng định đó là “JPA quy định dùng tối đa 20 entity đồng thời”.

**Giải thích:** thuộc tính này cấu hình kích thước tối đa của HikariCP qua Spring Boot. Nó liên quan pool connection, không phải số entity mà persistence context được phép quản lý.

## 9. Nguyên tắc ghi nhớ

- **Chuẩn JPA xác định hợp đồng; provider hiện thực hợp đồng và có thể bổ sung phần mở rộng.**
- **`persistence.xml` là định dạng chuẩn**, nhưng những cặp `name=value` trong `<properties>` có thể là chuẩn hoặc vendor-specific.
- **Namespace cần khớp thế hệ API:** `javax.persistence.*` thường thuộc JPA 2.x; `jakarta.persistence.*` thuộc Jakarta Persistence 3.x.
- **Không trộn phạm vi:** thuộc tính Spring Boot, DataSource/pool, JPA, provider và query hint có vai trò khác nhau.
- **Tính di động cần xét cả tên, giá trị, phiên bản và nền tảng thực thi.** Dùng key chuẩn giúp giảm phụ thuộc, nhưng không loại bỏ hoàn toàn khác biệt giữa provider và database.
- **Khi thay provider, ưu tiên giữ phần chuẩn và rà soát từng phần mở rộng**, đặc biệt với schema generation, batching, caching và logging.

Nhờ phân loại từ đầu, một Persistence Unit sẽ dễ bảo trì hơn: người viết biết cấu hình nào là hợp đồng chung của Jakarta Persistence, cấu hình nào tối ưu cho provider đang dùng, và chỗ nào cần thay đổi khi nâng cấp hoặc di chuyển hệ thống.
