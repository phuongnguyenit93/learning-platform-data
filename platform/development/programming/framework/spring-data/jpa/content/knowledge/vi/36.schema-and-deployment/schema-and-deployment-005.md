# Thứ tự schema.sql, data.sql và khởi tạo dữ liệu của Spring Boot

Spring Boot có thể khởi tạo database bằng script SQL, Hibernate/JPA hoặc công cụ migration như Flyway và Liquibase. Những cơ chế này chạy ở các thời điểm khác nhau. Nếu không hiểu thứ tự, ứng dụng có thể gặp lỗi như data.sql chạy trước khi bảng tồn tại, Hibernate tạo lại schema sau khi script đã nạp dữ liệu, hoặc nhiều cơ chế cùng cố tạo một bảng.

Với Spring Boot 3.x, cần phân biệt ba việc:

- **Schema initialization:** tạo hoặc thay đổi cấu trúc bảng, khóa, index và constraint.
- **Data initialization:** chèn dữ liệu ban đầu hoặc dữ liệu mẫu.
- **Versioned migration:** quản lý thay đổi schema và dữ liệu theo từng phiên bản triển khai.

Bài này giải thích thứ tự chạy mặc định của schema.sql, data.sql và Hibernate, cách dùng spring.jpa.defer-datasource-initialization, cách cấu hình theo môi trường, sự khác nhau giữa script đơn giản và migration, cùng cách kiểm thử quá trình khởi động.

**Điều kiện của ví dụ:** Java 17 trở lên, Spring Boot 3.x, Spring Data JPA, Hibernate và JDBC. Ứng dụng cần spring-boot-starter-data-jpa, driver phù hợp và DataSource. Cú pháp SQL phụ thuộc database; ví dụ PostgreSQL được ghi rõ khi cần. Các cấu hình là phần của ứng dụng Spring Boot, không phải chương trình Java độc lập chạy chỉ bằng javac.

## 1. Các cơ chế khởi tạo database trong Spring Boot

Một ứng dụng Spring Boot có thể dùng một hoặc nhiều cơ chế sau:

| Cơ chế | Vai trò | Phạm vi sử dụng |
|---|---|---|
| schema.sql | Tạo bảng, index, constraint hoặc cấu trúc ban đầu | Khởi tạo đơn giản, demo, test hoặc hệ thống nhỏ |
| data.sql | Chèn dữ liệu khởi tạo | Dữ liệu mẫu, dữ liệu tham chiếu ban đầu |
| Hibernate ddl-auto | Tạo, cập nhật, xác thực hoặc xóa schema dựa trên entity mapping | Phát triển, kiểm tra mapping hoặc môi trường được kiểm soát |
| Flyway | Chạy migration có version theo thứ tự | Quản lý schema theo release |
| Liquibase | Chạy changeset/changelog có lịch sử | Quản lý schema theo release |

Không nên để nhiều công cụ cùng sở hữu việc thay đổi một schema mà không có quy ước rõ ràng. Ví dụ, nếu Flyway đã tạo bảng customers thì schema.sql và Hibernate không nên tiếp tục tự tạo lại bảng đó.

Trong production, thường chọn Flyway hoặc Liquibase làm nguồn quản lý schema chính, rồi cấu hình Hibernate validate để phát hiện mapping không khớp.

## 2. schema.sql và data.sql là gì?

Spring Boot hỗ trợ script SQL cơ bản với hai tên mặc định:

- **schema.sql:** chạy các lệnh tạo hoặc chuẩn bị cấu trúc database.
- **data.sql:** chạy các lệnh chèn dữ liệu.

Ví dụ cấu trúc tài nguyên:

~~~text
src/
  main/
    resources/
      schema.sql
      data.sql
  main/
    java/
      com/example/
        Application.java
~~~

schema.sql:

~~~sql
CREATE TABLE departments (
    id BIGINT PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_employees_department
        FOREIGN KEY (department_id)
        REFERENCES departments(id)
);
~~~

data.sql:

~~~sql
INSERT INTO departments (id, code, name)
VALUES (1, 'ENG', 'Engineering');

INSERT INTO departments (id, code, name)
VALUES (2, 'HR', 'Human Resources');

INSERT INTO employees (id, department_id, full_name)
VALUES (100, 1, 'An Nguyen');
~~~

Với cách tổ chức này, script schema tạo bảng trước rồi script data chèn dữ liệu vào bảng đã có. Các lệnh SQL phải phù hợp với database và schema đang dùng.

Các script cơ bản được chạy khi ứng dụng khởi động theo cấu hình SQL initialization. Chúng không phải một hệ thống migration có lịch sử version: Spring Boot không ghi nhận rằng một câu INSERT trong data.sql chỉ được chạy đúng một lần qua mọi lần khởi động.

## 3. Thứ tự mặc định: SQL scripts chạy trước Hibernate

Mặc định, quá trình khởi tạo SQL cơ bản được thực hiện trước khi các JPA EntityManagerFactory được khởi tạo hoàn tất. Trong luồng thông thường:

~~~text
Spring Boot tạo DataSource
          |
          v
SQL script initialization
          |
          +--> schema.sql
          |
          +--> data.sql
          |
          v
Khởi tạo JPA EntityManagerFactory
          |
          v
Hibernate áp dụng ddl-auto
          |
          v
Ứng dụng hoàn tất startup
~~~

Vì vậy, thứ tự giữa các cơ chế rất quan trọng.

Giả sử schema.sql đã tạo bảng products và data.sql đã INSERT dữ liệu. Nếu Hibernate sau đó chạy với ddl-auto=create hoặc create-drop, Hibernate có thể tạo lại hoặc xóa rồi tạo schema theo entity mapping. Dữ liệu vừa được chèn bởi data.sql có thể bị mất.

Đây là nguyên nhân phổ biến khiến ứng dụng khởi động thành công nhưng dữ liệu seed không còn sau startup.

Thứ tự script schema.sql trước data.sql giúp data.sql có bảng để chèn. Tuy nhiên, thứ tự này không có nghĩa data.sql luôn chạy sau Hibernate. Theo mặc định, cả SQL initialization đều xảy ra trước khi JPA được khởi tạo hoàn tất.

## 4. spring.jpa.defer-datasource-initialization thay đổi thứ tự ra sao?

Nếu muốn Hibernate tạo schema trước rồi data.sql chèn dữ liệu, có thể bật:

~~~yaml
spring:
  jpa:
    defer-datasource-initialization: true
~~~

Khi bật thuộc tính này, Spring Boot trì hoãn SQL script initialization cho tới sau khi các EntityManagerFactory đã được tạo và khởi tạo. Với cấu hình Hibernate tạo schema, luồng sẽ là:

~~~text
Spring Boot tạo DataSource
          |
          v
Khởi tạo JPA EntityManagerFactory
          |
          v
Hibernate áp dụng ddl-auto
          |
          v
SQL script initialization
          |
          +--> schema.sql nếu được cấu hình/tìm thấy
          |
          +--> data.sql
          |
          v
Ứng dụng hoàn tất startup
~~~

Điểm cần nhớ:

- Thuộc tính này trì hoãn SQL initialization, không chỉ riêng data.sql.
- Nếu Hibernate đã tạo bảng và schema.sql cũng chứa CREATE TABLE cho cùng bảng, script có thể lỗi vì bảng đã tồn tại.
- Trường hợp thường dùng là Hibernate tạo schema trong môi trường dev/test, còn data.sql chỉ INSERT dữ liệu sau khi bảng đã có.
- Không bật thuộc tính này một cách máy móc nếu schema.sql đang là nguồn tạo bảng chính.

Giá trị mặc định của spring.jpa.defer-datasource-initialization là false.

## 5. Trường hợp A: schema.sql tạo bảng, data.sql chèn dữ liệu

Nếu muốn SQL scripts là nguồn tạo schema, cấu hình Hibernate để xác thực mapping thay vì tạo lại bảng:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:db/init/schema.sql
      data-locations: classpath:db/init/data.sql
      continue-on-error: false
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Luồng:

1. DataSource được tạo.
2. schema.sql tạo bảng và constraint.
3. data.sql chèn dữ liệu ban đầu.
4. Hibernate khởi tạo và validate entity mapping với schema đã có.
5. Ứng dụng sẵn sàng.

Ở đây không cần bật defer-datasource-initialization vì SQL scripts phải chạy trước Hibernate. Hibernate validate không tạo hoặc xóa bảng.

Cấu hình này có thể hữu ích cho môi trường test hoặc hệ thống đơn giản. Với ứng dụng production có nhiều phiên bản schema, Flyway/Liquibase thường phù hợp hơn vì chúng quản lý thay đổi theo version.

## 6. Trường hợp B: Hibernate tạo schema, data.sql chèn dữ liệu

Trong môi trường phát triển hoặc test, có thể để Hibernate tạo schema rồi chạy data.sql:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
      data-locations: classpath:db/seed/data.sql
      continue-on-error: false
~~~

Luồng:

1. Hibernate tạo bảng từ entity mapping.
2. SQL initialization được trì hoãn.
3. data.sql INSERT dữ liệu vào các bảng vừa được tạo.
4. Ứng dụng hoàn tất startup.

Không đặt một schema.sql tạo lại cùng bảng trong cấu hình này. Nếu cần script schema bổ sung sau Hibernate, chỉ chứa các cấu trúc bổ sung chưa được Hibernate quản lý và phải kiểm tra sự tương thích.

**Lưu ý:** ddl-auto=create xóa/tạo lại schema theo hành vi của provider. Không dùng cấu hình này với database chứa dữ liệu cần giữ.

## 7. Hibernate ddl-auto và ý nghĩa từng giá trị

Thuộc tính spring.jpa.hibernate.ddl-auto điều khiển cách Hibernate xử lý schema khi khởi tạo:

| Giá trị | Hành vi khái quát | Mục đích thường gặp |
|---|---|---|
| none | Không tự tạo, cập nhật hoặc validate schema | Schema do công cụ khác quản lý |
| validate | Kiểm tra mapping có tương thích schema hiện tại | Phát hiện lệch mapping/schema |
| update | Cố gắng điều chỉnh schema theo mapping | Thử nghiệm/phát triển có kiểm soát |
| create | Tạo schema theo mapping khi khởi động | Dev/test với dữ liệu có thể xóa |
| create-drop | Tạo schema khi khởi động, xóa khi SessionFactory đóng | Test hoặc demo |

Một số điểm quan trọng:

- update không phải công cụ migration đầy đủ. Nó không thay thế việc kiểm soát rename, chuyển đổi dữ liệu, index và constraint theo release.
- create và create-drop có thể làm mất dữ liệu.
- validate chỉ xác nhận một số khía cạnh mapping/schema; không thay thế migration test hoặc kiểm tra mọi index/constraint.
- none không có nghĩa database không cần schema. Nó chỉ nói Hibernate không quản lý schema trong quá trình khởi động.

Spring Boot có thể chọn mặc định khác nhau tùy môi trường. Thông thường, khi dùng embedded database và không có schema manager như Flyway/Liquibase, Boot có thể mặc định create-drop; với database khác hoặc khi có schema manager, mặc định thường là none. Hãy khai báo tường minh cho môi trường quan trọng thay vì dựa vào mặc định.

## 8. Cấu hình SQL initialization: mode, locations và platform

Các thuộc tính chính nằm dưới spring.sql.init:

~~~yaml
spring:
  sql:
    init:
      mode: always
      platform: postgresql
      schema-locations: classpath:db/init/schema.sql
      data-locations: classpath:db/init/data.sql
      encoding: UTF-8
      continue-on-error: false
~~~

Ý nghĩa:

| Thuộc tính | Tác dụng |
|---|---|
| mode | Chọn có chạy script hay không |
| platform | Chọn hậu tố script theo database |
| schema-locations | Vị trí script schema |
| data-locations | Vị trí script data |
| encoding | Encoding của file SQL |
| continue-on-error | Có tiếp tục khi script có lỗi hay không |

Các giá trị mode:

- **embedded:** chỉ chạy cho embedded database; đây là mặc định thường gặp.
- **always:** chạy với cả embedded và database ngoài như PostgreSQL/MySQL.
- **never:** tắt SQL initialization cơ bản.

Nếu dùng PostgreSQL hoặc MySQL bên ngoài, việc có schema.sql/data.sql trong classpath không tự bảo đảm chúng được chạy. Cần kiểm tra mode. Với mode embedded, database ngoài thường không được khởi tạo bằng các script này.

## 9. Platform-specific scripts

Khi cần SQL khác nhau theo database, có thể dùng script theo platform:

~~~text
src/main/resources/
  schema.sql
  data.sql
  schema-postgresql.sql
  data-postgresql.sql
  schema-mysql.sql
  data-mysql.sql
~~~

Chọn platform:

~~~yaml
spring:
  sql:
    init:
      platform: postgresql
      mode: always
~~~

Spring Boot hỗ trợ tên script có hậu tố platform để chọn nội dung phù hợp. Ví dụ PostgreSQL có thể dùng cú pháp ON CONFLICT, trong khi MySQL có thể dùng cú pháp riêng như INSERT IGNORE hoặc ON DUPLICATE KEY UPDATE.

Không đặt một câu SQL chỉ hợp lệ trên PostgreSQL vào script dùng chung nếu ứng dụng cũng chạy trên MySQL. Có thể dùng script chung cho phần SQL portable và script theo platform cho khác biệt cụ thể. Kiểm tra tài nguyên được nạp thực tế khi tùy chỉnh schema-locations/data-locations; các vị trí được cấu hình phải trỏ đúng file.

## 10. Tùy chỉnh vị trí script và tài nguyên optional

Mặc định Spring Boot tìm các script theo tên chuẩn ở classpath. Có thể tổ chức thư mục riêng:

~~~text
src/main/resources/
  db/
    init/
      schema.sql
      data.sql
~~~

Cấu hình:

~~~yaml
spring:
  sql:
    init:
      schema-locations: classpath:db/init/schema.sql
      data-locations: classpath:db/init/data.sql
~~~

Nếu một tài nguyên có thể không tồn tại ở một số profile, dùng tiền tố optional phù hợp với resource location, ví dụ:

~~~yaml
spring:
  sql:
    init:
      data-locations: optional:classpath:db/init/data.sql
~~~

Không dùng optional để che lỗi thiếu script bắt buộc. Nếu schema initialization là điều kiện để ứng dụng hoạt động, thiếu file phải khiến startup thất bại để vấn đề được phát hiện sớm.

Khi đặt schema-locations hoặc data-locations tùy chỉnh, hãy quản lý rõ danh sách file cần chạy. Không giả định một file trong thư mục bất kỳ sẽ tự được phát hiện.

## 11. data.sql chạy lại ở mỗi lần khởi động

Một điểm rất quan trọng: data.sql là script khởi tạo, không phải migration chạy đúng một lần. Nếu ứng dụng khởi động nhiều lần trên cùng database, các INSERT có thể chạy lại.

Ví dụ:

~~~sql
INSERT INTO roles (id, code, name)
VALUES (1, 'ADMIN', 'Administrator');
~~~

Nếu cột id hoặc code có UNIQUE constraint, lần khởi động tiếp theo có thể lỗi duplicate key.

Có một số cách xử lý:

1. Chỉ dùng data.sql cho database được tạo mới mỗi lần, chẳng hạn test hoặc demo.
2. Thiết kế seed insert idempotent theo database, để chạy lại không tạo duplicate.
3. Dùng migration versioned để dữ liệu khởi tạo chỉ được áp dụng một lần theo lịch sử migration.
4. Dùng dữ liệu tham chiếu do quy trình triển khai quản lý riêng.

Ví dụ PostgreSQL-specific:

~~~sql
INSERT INTO roles (id, code, name)
VALUES (1, 'ADMIN', 'Administrator')
ON CONFLICT (code) DO NOTHING;
~~~

Đây không phải SQL portable cho mọi database. MySQL, SQL Server và Oracle có cú pháp hoặc cơ chế khác. Nếu cần hỗ trợ nhiều engine, dùng script theo platform hoặc migration tương ứng.

Không dùng một INSERT idempotent theo kiểu bỏ qua mọi lỗi nếu điều đó có thể che giấu dữ liệu seed sai. Hãy xác định khóa tự nhiên, giá trị mong muốn và cách cập nhật khi dữ liệu tham chiếu thay đổi.

## 12. schema.sql không thay thế Flyway/Liquibase

schema.sql thường mô tả trạng thái schema ban đầu. Nó không tự quản lý lịch sử thay đổi theo release.

Giả sử phiên bản đầu có bảng customers, phiên bản sau cần thêm cột status, phiên bản tiếp theo đổi cấu trúc email. Nếu chỉ sửa schema.sql thành trạng thái mới, database đã được tạo từ phiên bản trước không tự biết cần chạy phần ALTER nào.

Flyway/Liquibase giải quyết vấn đề bằng migration có version/changelog:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_customers.sql
      V2__add_customer_status.sql
      V3__add_customer_email_index.sql
~~~

Flyway ghi lại migration đã chạy trong bảng lịch sử. Khi deploy phiên bản mới, chỉ các migration chưa áp dụng mới được chạy theo thứ tự.

Liquibase quản lý changeset trong changelog và lưu lịch sử thực thi tương ứng.

Đối với production:

- Dùng Flyway hoặc Liquibase làm nguồn schema chính.
- Không đồng thời để schema.sql và Hibernate ddl-auto=create/update cùng thay đổi các bảng do migration quản lý.
- Có thể dùng Hibernate ddl-auto=validate để kiểm tra entity mapping sau migration.
- Quản lý thay đổi schema bằng migration mới, không sửa script versioned đã chạy trên môi trường dùng chung.

## 13. Thứ tự Flyway/Liquibase và Hibernate

Khi có Flyway hoặc Liquibase, Spring Boot tích hợp các công cụ này vào quá trình khởi tạo. Mục tiêu thường là migration chạy trước khi Hibernate khởi tạo EntityManagerFactory, để Hibernate nhìn thấy schema đã được cập nhật.

Luồng điển hình:

~~~text
DataSource
    |
    v
Flyway hoặc Liquibase migration
    |
    v
Database schema ở version mới
    |
    v
Hibernate EntityManagerFactory
    |
    v
ddl-auto=validate
    |
    v
Ứng dụng sẵn sàng
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  sql:
    init:
      mode: never
~~~

Migration tạo bảng và seed dữ liệu cần thiết. Hibernate chỉ kiểm tra mapping. SQL initialization cơ bản được tắt để tránh schema.sql/data.sql vô tình chạy thêm lần nữa.

Không cần bật defer-datasource-initialization chỉ để Flyway chạy trước Hibernate. Thuộc tính defer phục vụ thứ tự giữa basic SQL script initialization và JPA EntityManagerFactory, đặc biệt khi muốn script chạy sau schema do Hibernate tạo.

Nếu cần nạp dữ liệu tham chiếu theo release, đặt INSERT trong migration versioned để dữ liệu được quản lý cùng schema.

## 14. Spring Boot profiles cho dev, test và production

Không nên dùng cùng một chính sách khởi tạo database cho mọi môi trường.

Ví dụ application-dev.yaml:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
      data-locations: classpath:db/seed/dev-data.sql
~~~

Ví dụ application-test.yaml:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
      data-locations: classpath:db/seed/test-data.sql
~~~

Ví dụ application-prod.yaml khi dùng Flyway:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  sql:
    init:
      mode: never
~~~

Các cấu hình dev/test trên giả định Hibernate sở hữu schema và script chỉ nạp dữ liệu sau khi schema đã được tạo. Production giả định Flyway hoặc Liquibase quản lý schema. Hãy bảo đảm profile đúng được kích hoạt khi deploy; không để cấu hình create/create-drop lọt vào production.

## 15. Spring Data JPA entity mapping phải khớp schema

Hibernate validate có thể phát hiện một số lỗi như bảng/cột không tồn tại hoặc kiểu dữ liệu mapping không tương thích. Vì vậy, khi schema.sql hoặc migration tạo schema, cần đối chiếu entity mapping.

Ví dụ entity:

~~~java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    private Long id;

    @Column(nullable = false, length = 30, unique = true)
    private String code;

    @Column(nullable = false, length = 120)
    private String name;

    protected Department() {
    }
}
~~~

DDL cần có bảng departments và các cột tương ứng. Các khác biệt về naming strategy, schema name, sequence, identity, enum mapping, precision/scale và timezone có thể khiến validate hoặc runtime query thất bại.

Đừng cho rằng chỉ cần tên cột giống nhau là đủ. Ví dụ:

- Java Long có thể map tới kiểu số khác nhau tùy database.
- Enum STRING cần cột lưu tên enum, không phải ordinal.
- BigDecimal cần precision/scale phù hợp.
- IDENTITY và SEQUENCE có DDL khác nhau.
- Tên bảng/cột là từ khóa SQL cần quoting theo quy tắc database.

Khi schema do migration quản lý, migration phải phản ánh đúng mapping được ứng dụng sử dụng.

## 16. Dữ liệu seed, dữ liệu tham chiếu và dữ liệu nghiệp vụ

Không phải mọi dữ liệu ban đầu đều nên đặt trong data.sql.

Có thể phân biệt:

- **Seed data:** dữ liệu cố định phục vụ môi trường dev/test, ví dụ vài customer mẫu.
- **Reference data:** dữ liệu tham chiếu cần thiết cho ứng dụng, ví dụ role, currency, status code.
- **Business data:** dữ liệu phát sinh từ hoạt động người dùng, không nên tự nạp lại mỗi lần khởi động.

Seed data có thể phù hợp với data.sql trong test. Reference data quan trọng cho production thường nên được quản lý bằng migration có version hoặc quy trình đồng bộ dữ liệu riêng. Business data không nên bị reset hoặc chèn lại khi ứng dụng khởi động.

Nếu dữ liệu tham chiếu cần thay đổi theo release, migration có thể cập nhật bằng khóa ổn định. Cần quy định rõ migration có được phép sửa giá trị do người vận hành thay đổi hay không.

## 17. Script lỗi và continue-on-error

Thuộc tính:

~~~yaml
spring:
  sql:
    init:
      continue-on-error: false
~~~

Với continue-on-error=false, lỗi script làm quá trình khởi tạo thất bại. Đây thường là lựa chọn an toàn vì ứng dụng không nên khởi động với schema hoặc seed data chỉ được áp dụng một phần.

Nếu bật true, Spring Boot có thể tiếp tục sau một số lỗi script. Điều này hữu ích trong một số kịch bản đặc biệt nhưng có nguy cơ che giấu:

- Bảng chưa được tạo.
- INSERT thất bại.
- Constraint không tồn tại.
- Seed data không đầy đủ.
- Một phần script đã chạy nhưng phần sau không chạy.

Không bật continue-on-error=true chỉ để ứng dụng khởi động được. Hãy sửa script hoặc phân loại rõ lỗi nào thực sự được phép bỏ qua.

Các lỗi DDL/DML và tính atomic của script phụ thuộc database. Không giả định toàn bộ file SQL luôn rollback như một transaction duy nhất trên mọi engine.

## 18. Test với @DataJpaTest và Testcontainers

@DataJpaTest thường cấu hình test slice cho JPA, repository và database test. Với embedded database, SQL initialization có thể chạy theo mặc định phù hợp. Tuy nhiên, hành vi test có thể khác production nếu engine khác nhau.

Ví dụ kiểm tra repository sau khi dữ liệu seed đã được nạp:

~~~java
@DataJpaTest
class DepartmentRepositoryTest {

    @Autowired
    private DepartmentRepository repository;

    @Test
    void loadsSeedDepartment() {
        Department department =
            repository.findById(1L).orElseThrow();

        assertThat(department.getCode()).isEqualTo("ENG");
        assertThat(department.getName()).isEqualTo("Engineering");
    }
}
~~~

Test này giả định schema và seed data đã được khởi tạo trước khi test method chạy. Nếu dùng data.sql với Hibernate tạo schema, cần cấu hình defer-datasource-initialization phù hợp.

Với PostgreSQL/MySQL production, dùng Testcontainers để kiểm tra đúng dialect, DDL và SQL behavior. Ví dụ khung:

~~~java
@Testcontainers
@DataJpaTest
class DepartmentPostgresTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    // Cấu hình DataSource từ container bằng DynamicPropertySource
    // và để Spring chạy migration/script trong test context.
}
~~~

Đây là khung minh họa; cần cấu hình spring.datasource.url, username, password từ container. Testcontainers giúp phát hiện khác biệt giữa H2 và database production, nhất là cú pháp SQL, sequence/identity, constraint và kiểu dữ liệu.

## 19. Nhiều DataSource và thứ tự khởi tạo

Ứng dụng có nhiều DataSource có thể có nhiều schema và nhiều cơ chế khởi tạo. Các thuộc tính SQL initialization mặc định thường gắn với DataSource được Spring Boot auto-configure. Khi tự khai báo nhiều DataSource, không nên giả định schema.sql/data.sql sẽ tự chạy cho tất cả.

Cần xác định:

- DataSource nào là primary.
- Repository nào dùng EntityManagerFactory nào.
- Migration tool nào quản lý từng schema.
- Script nào được chạy trên database nào.
- Thứ tự migration giữa các database có phụ thuộc nhau không.

Với DataSource tùy chỉnh, có thể cần cấu hình initializer riêng như DataSourceScriptDatabaseInitializer hoặc cấu hình Flyway/Liquibase riêng cho từng DataSource. Mỗi initializer phải được gắn đúng DataSource và có thứ tự rõ ràng trước EntityManagerFactory tương ứng.

Không chạy cùng một data.sql trên nhiều database nếu nội dung không phù hợp với tất cả schema.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| data.sql báo table not found | Script chạy trước Hibernate nhưng chưa có schema | Dùng schema.sql trước hoặc defer khi Hibernate tạo bảng |
| Dữ liệu seed biến mất sau startup | Hibernate create/create-drop chạy sau script và tạo lại schema | Đổi thứ tự hoặc dùng một cơ chế tạo schema duy nhất |
| data.sql không chạy trên PostgreSQL | mode đang là embedded | Đặt spring.sql.init.mode=always nếu thực sự cần |
| Duplicate key khi restart | data.sql được chạy lại mỗi lần khởi động | Dùng seed idempotent hoặc migration versioned |
| schema.sql tạo bảng trùng với Hibernate | Cả hai cùng sở hữu schema | Chọn một nguồn tạo schema |
| Hibernate validate thất bại | Entity mapping khác DDL | Sửa migration/schema hoặc mapping |
| Script theo platform không được chọn | platform hoặc tên file sai | Kiểm tra spring.sql.init.platform và resource path |
| Ứng dụng khởi động dù seed thiếu | continue-on-error=true che lỗi | Đặt false và sửa nguyên nhân |
| Dev chạy được nhưng production lỗi | Dùng H2 hoặc cú pháp SQL khác engine | Test trên database production bằng Testcontainers |
| Migration chạy sau Hibernate | Cấu hình dependency/initializer không đúng | Dùng tích hợp Flyway/Liquibase chuẩn và kiểm tra startup logs |
| Nhiều DataSource chỉ một database có dữ liệu | Initializer chỉ gắn với một DataSource | Cấu hình initializer/migration riêng cho từng nguồn |
| ddl-auto=update làm schema khó kiểm soát | Dùng Hibernate thay cho migration versioning | Dùng Flyway/Liquibase và validate |

## 21. Checklist chọn đúng thứ tự khởi tạo

- [ ] Xác định schema do schema.sql, Hibernate hay Flyway/Liquibase quản lý.
- [ ] Nếu schema.sql tạo bảng, để SQL initialization chạy trước JPA và chọn ddl-auto phù hợp như validate.
- [ ] Nếu Hibernate tạo schema rồi data.sql mới INSERT, bật defer-datasource-initialization=true.
- [ ] Không để schema.sql và Hibernate create cùng tạo một bảng.
- [ ] Hiểu spring.sql.init.mode: embedded, always và never.
- [ ] Kiểm tra platform-specific script và resource locations.
- [ ] Thiết kế data.sql có thể chạy lại an toàn hoặc dùng migration versioned.
- [ ] Giữ continue-on-error=false cho khởi tạo bắt buộc.
- [ ] Dùng profile riêng cho dev, test và production.
- [ ] Dùng Flyway/Liquibase cho schema production có lịch sử thay đổi.
- [ ] Dùng ddl-auto=validate khi Hibernate cần kiểm tra schema do migration tạo.
- [ ] Kiểm thử startup từ database rỗng và từ schema phiên bản trước.
- [ ] Kiểm thử trên đúng database engine/driver bằng Testcontainers.
- [ ] Với nhiều DataSource, gắn initializer/migration đúng từng nguồn.

## 22. Kết luận

Mặc định, SQL initialization cơ bản của Spring Boot chạy trước khi JPA EntityManagerFactory được khởi tạo hoàn tất; schema.sql chạy trước data.sql. Hibernate sau đó áp dụng ddl-auto. Vì vậy, nếu Hibernate tạo lại schema sau khi data.sql đã chèn dữ liệu, seed data có thể bị mất.

Nếu schema.sql là nguồn tạo bảng, hãy để script chạy trước Hibernate và dùng ddl-auto phù hợp như validate. Nếu Hibernate tạo schema rồi data.sql mới chèn dữ liệu, bật spring.jpa.defer-datasource-initialization=true và tránh để schema.sql tạo trùng bảng. Với production, ưu tiên Flyway hoặc Liquibase quản lý schema theo version, Hibernate validate mapping và kiểm thử startup trên đúng database triển khai.