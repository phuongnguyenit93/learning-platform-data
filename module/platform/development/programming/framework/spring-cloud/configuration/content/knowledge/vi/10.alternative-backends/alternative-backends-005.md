# JDBC backend: mô hình khóa theo application, profile và label

Spring Cloud Config Server thường lấy cấu hình từ Git, nhưng trong một số hệ thống tổ chức muốn lưu cấu hình trong cơ sở dữ liệu quan hệ. JDBC backend cho phép Config Server truy vấn các property theo thông tin application, profile và label mà client yêu cầu. Mỗi property được biểu diễn thành một dòng dữ liệu, nhờ đó có thể quản lý cấu hình bằng schema, SQL, quyền truy cập và quy trình vận hành của database.

Điểm quan trọng khi thiết kế là xác định đúng khóa của một property. Một key như `orders.timeout` có thể có giá trị khác nhau giữa `order-service` và `payment-service`, giữa `dev` và `prod`, hoặc giữa hai phiên bản cấu hình. Vì vậy, chỉ dùng tên property làm khóa là không đủ. Mô hình cần phân biệt application, profile, label và key; đồng thời phải quy định cách cập nhật, truy vết và rollback dữ liệu.

## 1. JDBC backend phù hợp khi nào?

JDBC backend phù hợp khi tổ chức đã có nền tảng database và cần lưu cấu hình theo mô hình dữ liệu quan hệ, ví dụ:

- Một nhóm vận hành muốn quản lý cấu hình qua quy trình database migration và phân quyền SQL.
- Cấu hình được tạo hoặc cập nhật bởi một hệ thống quản trị nội bộ đã làm việc với database.
- Cần truy vấn, báo cáo hoặc kiểm toán các thay đổi cấu hình bằng công cụ database hiện có.
- Hạ tầng yêu cầu cấu hình được lưu trong database có backup, replication và quy trình khôi phục riêng.

Git thường thuận tiện hơn khi cần review theo diff, branch, tag và lịch sử commit. JDBC phù hợp khi database là nguồn dữ liệu được quản trị chính thức và tổ chức đã có quy trình kiểm soát thay đổi tương ứng. Việc chuyển từ Git sang JDBC không tự động mang theo lịch sử commit, mô hình pull request hoặc quy tắc merge; cần thiết kế các cơ chế tương đương nếu chúng vẫn cần thiết.

## 2. Mô hình một dòng cho một property

JDBC backend tiêu chuẩn sử dụng truy vấn trả về hai cột `KEY` và `VALUE`. Các tham số truy vấn lần lượt xác định `APPLICATION`, `PROFILE` và `LABEL`.

Mô hình dữ liệu cơ bản:

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `APPLICATION` | Tên ứng dụng yêu cầu cấu hình | `order-service` |
| `PROFILE` | Profile đang được phân giải | `prod` |
| `LABEL` | Nhãn phiên bản cấu hình | `release-2026.11` |
| `KEY` | Tên property trong Spring | `orders.timeout` |
| `VALUE` | Giá trị của property | `5s` |

Một dòng dữ liệu hoàn chỉnh có thể đọc như sau:

```text
APPLICATION    = order-service
PROFILE        = prod
LABEL          = release-2026.11
KEY            = orders.timeout
VALUE          = 5s
```

Như vậy, cùng một `KEY` có thể xuất hiện nhiều lần nếu application, profile hoặc label khác nhau. Khóa duy nhất nên bao gồm cả bốn thành phần `APPLICATION`, `PROFILE`, `LABEL` và `KEY`.

Ví dụ dữ liệu cho cùng một property ở hai môi trường và hai label:

| APPLICATION | PROFILE | LABEL | KEY | VALUE |
|---|---|---|---|---|
| `order-service` | `dev` | `main` | `orders.timeout` | `2s` |
| `order-service` | `prod` | `main` | `orders.timeout` | `5s` |
| `order-service` | `prod` | `release-2026.11` | `orders.timeout` | `5s` |
| `payment-service` | `prod` | `release-2026.11` | `orders.timeout` | `8s` |

Mỗi bộ application/profile/label tạo thành một không gian tên riêng. Vì thế, `orders.timeout` của `payment-service` không ghi đè property cùng tên của `order-service`.

## 3. Thiết kế bảng và khóa chính

Một schema minh họa cho PostgreSQL:

```sql
CREATE TABLE config_properties (
    application   VARCHAR(200) NOT NULL,
    profile       VARCHAR(100) NOT NULL,
    label         VARCHAR(200) NOT NULL,
    property_key  VARCHAR(300) NOT NULL,
    property_value TEXT NOT NULL,
    PRIMARY KEY (application, profile, label, property_key)
);

CREATE INDEX idx_config_properties_lookup
    ON config_properties (application, profile, label);
```

Tên `property_key` và `property_value` tránh phụ thuộc vào việc database có coi `KEY` hoặc `VALUE` là từ khóa đặc biệt hay không. Truy vấn JDBC có thể đặt alias để trả về đúng tên cột mà Config Server mong đợi:

```sql
SELECT
    property_key AS "KEY",
    property_value AS "VALUE"
FROM config_properties
WHERE application = ?
  AND profile = ?
  AND label = ?
```

Ví dụ dùng alias có dấu nháy kép theo cú pháp PostgreSQL. Với MySQL, SQL Server, Oracle hoặc database khác, hãy điều chỉnh cách quote identifier và alias theo dialect. Điều kiện quan trọng là kết quả truy vấn phải cung cấp hai cột có nhãn `KEY` và `VALUE` theo cách JDBC driver trả về.

Nếu dùng đúng schema mặc định với tên bảng `PROPERTIES` và cột `APPLICATION`, `PROFILE`, `LABEL`, `KEY`, `VALUE`, truy vấn thường có dạng:

```sql
SELECT KEY, VALUE
FROM PROPERTIES
WHERE APPLICATION = ?
  AND PROFILE = ?
  AND LABEL = ?
```

`KEY` có thể là từ khóa hoặc tên cần quote ở một số database. Khi gặp lỗi cú pháp, dùng tên cột riêng như `PROPERTY_KEY` và `PROPERTY_VALUE`, sau đó cấu hình SQL tùy chỉnh cùng alias phù hợp với database.

Khóa chính tổng hợp ngăn hai dòng có cùng application/profile/label/key tồn tại đồng thời. Index theo ba cột đầu hỗ trợ truy vấn theo bộ định tuyến cấu hình. Với bảng lớn, kiểm tra execution plan và số dòng trả về; tránh truy vấn toàn bảng rồi lọc trong Java.

## 4. Cấu hình Config Server kết nối JDBC

Config Server cần dependency cho JDBC và driver của database. Với Maven, các dependency cốt lõi có thể gồm:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Quản lý phiên bản Spring Boot và Spring Cloud bằng các BOM tương thích với nhau. Nếu dùng MySQL, Oracle hoặc SQL Server, thay driver PostgreSQL bằng driver phù hợp.

Ví dụ `application.yml` của Config Server:

```yaml
spring:
  profiles:
    active: jdbc

  datasource:
    url: jdbc:postgresql://config-db.internal:5432/configuration
    username: ${CONFIG_DB_USERNAME}
    password: ${CONFIG_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000

  cloud:
    config:
      server:
        jdbc:
          sql: >
            SELECT property_key AS "KEY", property_value AS "VALUE"
            FROM config_properties
            WHERE application = ?
              AND profile = ?
              AND label = ?
```

Profile `jdbc` kích hoạt JDBC environment repository. Nếu Config Server cần chạy thêm profile khác, hãy khai báo các active profile theo cú pháp Spring Boot tương ứng và xác nhận JDBC repository vẫn được kích hoạt. `spring.datasource` cung cấp kết nối database cho repository.

Các placeholder `${CONFIG_DB_USERNAME}` và `${CONFIG_DB_PASSWORD}` cần được cấp từ secret manager hoặc môi trường triển khai. Không ghi username/password thật vào repository cấu hình hoặc commit trong source code.

Thuộc tính `spring.cloud.config.server.jdbc.sql` cho phép thay đổi truy vấn. Truy vấn nhận ba tham số theo thứ tự application, profile và label; giữ placeholder `?` để JDBC bind tham số. Không nối trực tiếp giá trị từ URL request vào chuỗi SQL.

## 5. Client chọn application, profile và label

Config Client vẫn yêu cầu cấu hình theo endpoint Environment quen thuộc:

```text
/{application}/{profile}/{label}
```

Ví dụ client khai báo:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026.11
```

Khi khởi động, client yêu cầu cấu hình với:

```text
application = order-service
profile     = prod
label       = release-2026.11
```

JDBC backend dùng ba thông tin này trong truy vấn để lấy các dòng property tương ứng. Nếu client thay profile thành `dev`, server truy vấn tập dòng `order-service/dev/release-2026.11`. Nếu đổi label, server truy vấn partition label khác trong cùng database.

Trong JDBC backend, label là giá trị định danh phiên bản do hệ thống quy ước. Nó không tự động là Git branch hoặc Git tag vì không có Git repository tham gia vào backend này. Có thể dùng các tên như `main`, `release-2026.11` hoặc `config-v42`, miễn là client và dữ liệu database thống nhất cùng quy ước.

## 6. Ví dụ ghi và truy vấn dữ liệu

Thêm các property cho `order-service`:

```sql
INSERT INTO config_properties
    (application, profile, label, property_key, property_value)
VALUES
    ('order-service', 'prod', 'release-2026.11', 'orders.timeout', '5s'),
    ('order-service', 'prod', 'release-2026.11', 'orders.max-items', '20'),
    ('order-service', 'prod', 'release-2026.11', 'feature.bulk-import-enabled', 'false');
```

Truy vấn trực tiếp để xác nhận dữ liệu:

```sql
SELECT property_key, property_value
FROM config_properties
WHERE application = 'order-service'
  AND profile = 'prod'
  AND label = 'release-2026.11'
ORDER BY property_key;
```

Config Server chạy SQL đã cấu hình với các tham số request và chuyển kết quả thành property source. Response Environment có thể chứa các key như:

```json
{
  "name": "order-service",
  "profiles": ["prod"],
  "label": "release-2026.11",
  "propertySources": [
    {
      "name": "jdbc",
      "source": {
        "orders.timeout": "5s",
        "orders.max-items": "20",
        "feature.bulk-import-enabled": "false"
      }
    }
  ]
}
```

Response thực tế có thể khác về tên property source và cách trình bày; `jdbc` ở đây là tên minh họa. Hãy xác minh các key trong `source` của property source thay vì dựa vào tên nguồn ở ví dụ.

## 7. Quy ước cấu hình dùng chung và kế thừa

Git backend có quy ước tệp như `application.yml`, `application-prod.yml`, `order-service.yml` và `order-service-prod.yml`. JDBC backend lưu các dòng theo khóa application/profile/label/key, vì vậy không nên giả định rằng một hàng có `APPLICATION='application'` sẽ tự động được ghép vào cấu hình riêng của mọi dịch vụ giống hệt `application.yml` của Git.

Nếu cần cấu hình dùng chung, hãy chọn và tài liệu hóa một cơ chế rõ ràng:

- Lưu bản sao các baseline nhỏ trong từng application khi số lượng dịch vụ ít và cần đơn giản.
- Dùng database view hoặc truy vấn tùy chỉnh để kết hợp scope dùng chung và scope riêng, đồng thời quy định rõ key trùng nhau được ưu tiên thế nào.
- Triển khai `EnvironmentRepository` tùy chỉnh nếu cần nhiều lớp cấu hình, nhiều nguồn hoặc quy tắc hợp nhất phức tạp.
- Dùng composite repository nếu muốn kết hợp nhiều backend theo cơ chế mà Spring Cloud Config hỗ trợ.

Với truy vấn trả về các key trùng tên từ nhiều scope, cần xác định thứ tự và cách tạo property source một cách tường minh. Không phụ thuộc vào thứ tự dòng ngẫu nhiên của database. Kiểm tra response Environment để xác nhận nguồn nào thắng và thử với key trùng giữa baseline và application-specific config.

## 8. Kiểu dữ liệu và chuyển đổi ở Config Client

Trong bảng JDBC, `VALUE` thường được lưu dưới dạng chuỗi. Config Server trả property source cho client; Spring Boot chuyển đổi giá trị khi bind vào kiểu Java tương ứng.

Ví dụ dữ liệu:

| KEY | VALUE | Kiểu Java phía client |
|---|---|---|
| `orders.timeout` | `5s` | `java.time.Duration` |
| `orders.max-items` | `20` | `int` |
| `feature.bulk-import-enabled` | `false` | `boolean` |
| `upload.max-size` | `10MB` | `org.springframework.util.unit.DataSize` |

Bean cấu hình có thể dùng `@ConfigurationProperties`:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrderProperties(
        Duration timeout,
        int maxItems) {
}
```

Nếu `VALUE` chứa chuỗi không thể chuyển đổi, ví dụ `five seconds` cho một `Duration`, client có thể lỗi khi bind hoặc dùng logic xử lý không như mong đợi. Nên kiểm tra kiểu và miền giá trị trước khi cập nhật database; không đợi đến lúc nhiều client khởi động mới phát hiện lỗi.

## 9. Quản lý label và phiên bản cấu hình trong database

Vì JDBC backend không có branch/tag như Git, tổ chức cần quy ước label và quy trình phát hành riêng. Một cách làm là tạo label bất biến cho từng bản phát hành:

```text
dev                 -> dữ liệu thử nghiệm đang phát triển
release-2026.11     -> bộ cấu hình đã duyệt cho một đợt phát hành
release-2026.12     -> bộ cấu hình của đợt tiếp theo
```

Không sửa trực tiếp dữ liệu của label production đã phát hành nếu cần khả năng tái lập. Thay đổi tạo label mới, kiểm tra bằng HTTP request và sau đó cập nhật client hoặc deployment để sử dụng label mới.

Có thể thêm bảng audit để ghi lại ai thay đổi, lúc nào, key nào, giá trị cũ/mới và lý do:

```sql
CREATE TABLE config_property_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    application VARCHAR(200) NOT NULL,
    profile VARCHAR(100) NOT NULL,
    label VARCHAR(200) NOT NULL,
    property_key VARCHAR(300) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(200) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    change_reason TEXT
);
```

Bảng audit này là ví dụ thiết kế riêng, không được Spring Cloud Config tự tạo. Hệ thống ghi cấu hình cần ghi audit trong cùng transaction với thay đổi dữ liệu hoặc dùng cơ chế outbox phù hợp để tránh trường hợp dữ liệu đã đổi nhưng không có dấu vết.

## 10. Bảo mật và vận hành database

Config Server trở thành client có quyền đọc dữ liệu cấu hình. Tài khoản database nên chỉ có quyền `SELECT` trên bảng cần thiết. Một dịch vụ quản trị riêng có thể được cấp quyền ghi thông qua quy trình đã kiểm soát; không cấp quyền `UPDATE` hoặc `DELETE` rộng cho mọi ứng dụng.

Các điểm cần bảo vệ:

- Dùng TLS khi kết nối database qua mạng và xác minh chứng chỉ theo chính sách của nền tảng.
- Lưu database credentials trong secret manager; luân chuyển định kỳ và giới hạn quyền.
- Phân quyền theo schema hoặc view nếu các nhóm ứng dụng không được đọc cấu hình của nhau.
- Không lưu secret dạng rõ nếu database hoặc người vận hành không được phép xem chúng; ưu tiên secret manager chuyên dụng.
- Hạn chế log SQL bind values vì chúng có thể chứa cấu hình nhạy cảm.
- Backup database, kiểm tra khả năng restore và giám sát connection pool, latency, lỗi truy vấn.
- Dùng migration có phiên bản để tạo bảng, index và thay đổi schema; tránh sửa trực tiếp production mà không có lịch sử.

Nếu mọi client đều truy cập cùng Config Server, phân quyền đọc tại database thường áp dụng cho tài khoản của Config Server. Muốn giới hạn từng client chỉ thấy cấu hình của chính nó, cần bổ sung xác thực/phân quyền ở Config Server hoặc thiết kế lớp phân phối phù hợp; quyền đọc database của Config Server không tự động trở thành quyền theo từng application request.

## 11. Cập nhật cấu hình và ảnh hưởng đến client đang chạy

Khi một dòng trong database được thay đổi, JDBC backend có thể đọc giá trị mới trong những request tiếp theo theo cách triển khai và transaction visibility của database. Điều đó không có nghĩa các ứng dụng đang chạy tự động nhận giá trị mới.

Thông thường cần phân biệt:

1. **Cập nhật database:** transaction ghi property mới được commit.
2. **Đọc lại từ Config Server:** client gọi lại Config Server hoặc nhận một cơ chế refresh để yêu cầu đọc cấu hình.
3. **Áp dụng tại client:** `Environment` cập nhật; bean phải hỗ trợ rebind hoặc refresh nếu muốn giá trị thay đổi trong tiến trình hiện tại.

Nếu ứng dụng chỉ đọc property khi khởi động, cần restart ứng dụng để nạp giá trị mới. Với nhiều instance, có thể phối hợp Spring Cloud Bus để phát sự kiện refresh; Bus chỉ phân phối tín hiệu, còn client vẫn cần đọc lại cấu hình và bean phải hỗ trợ cập nhật.

## 12. Kiểm thử JDBC backend qua HTTP

Sau khi cấu hình datasource và chèn dữ liệu, gọi endpoint Environment:

```bash
curl -i "http://localhost:8888/order-service/prod/release-2026.11"
```

Kiểm tra:

1. HTTP status cho biết request có được xử lý thành công không.
2. `name`, `profiles` và `label` có khớp với bộ khóa trong database không.
3. `propertySources` có chứa các key đã chèn không.
4. Giá trị có được client bind thành kiểu mong muốn không.
5. Khi đổi application, profile hoặc label, server có trả đúng bộ dữ liệu khác không.

Nên có kiểm thử tự động cho các trường hợp:

- Cùng key nhưng application khác nhau.
- Cùng application nhưng profile khác nhau.
- Cùng application/profile nhưng label khác nhau.
- Key không tồn tại.
- Giá trị sai kiểu hoặc vượt giới hạn nghiệp vụ.
- Database tạm thời không truy cập được.
- Query không trả dòng trùng ngoài dự kiến.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Config Server không khởi động với JDBC profile | Thiếu JDBC starter/driver hoặc datasource chưa cấu hình | Kiểm tra dependency, active profile và log DataSource |
| Lỗi cú pháp SQL | Tên `KEY`/`VALUE` là từ khóa hoặc alias không đúng dialect | Chạy query trực tiếp trên database và xác nhận tên cột trả về |
| Response không có property | Không có dòng khớp đủ application/profile/label | Query trực tiếp với đúng ba giá trị từ request |
| Nhận nhầm phiên bản cấu hình | Client gửi label khác hoặc dữ liệu được ghi sai label | Kiểm tra request URL và các dòng theo label |
| Hai lần ghi tạo dữ liệu trùng | Thiếu khóa chính/unique constraint | Dùng composite primary key `(application, profile, label, key)` |
| Giá trị trong client khác database | Remote sources khác, local override hoặc bean giữ giá trị cũ | Kiểm tra Environment phía client và thời điểm refresh |
| Config Server truy vấn chậm | Thiếu index hoặc query trả quá nhiều dòng | Xem execution plan, index và connection pool |
| Lộ thông tin nhạy cảm | Credential hoặc secret được lưu/log dạng rõ | Rà soát grants, logs, secret manager và quyền truy cập endpoint |

## 14. Checklist thiết kế

Trước khi dùng JDBC backend trong môi trường chung, hãy xác nhận:

- Schema có khóa duy nhất theo application, profile, label và key.
- Query dùng placeholder và trả về đúng hai cột `KEY`, `VALUE`.
- Tên cột và cách quote tương thích với database cụ thể.
- Có index phù hợp với điều kiện tìm kiếm.
- Quy ước label, profile và cách chia sẻ cấu hình được tài liệu hóa.
- Cơ chế audit, migration, backup và rollback đã được xác định.
- Config Server có quyền đọc tối thiểu; credential và secret được bảo vệ.
- Đã kiểm thử HTTP response và giá trị bind thực tế ở client.
- Đã xác định cách refresh hoặc restart client sau khi cập nhật database.

JDBC backend biến cấu hình thành dữ liệu có khóa theo application, profile, label và property key. Khi schema, truy vấn và quy ước label được thiết kế rõ ràng, Config Server có thể lấy đúng bộ property cho từng client. Database cung cấp khả năng quản trị dữ liệu và phân quyền, còn quy trình migration, audit, bảo mật và refresh cần được tổ chức chủ động để cấu hình có thể truy vết và vận hành an toàn.
