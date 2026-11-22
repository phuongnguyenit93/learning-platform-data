# Quản lý bí mật kết nối và quyền tối thiểu cho tài khoản ứng dụng

Ứng dụng Spring Data JPA cần thông tin xác thực để kết nối database, nhưng username và password của database là bí mật vận hành. Nếu lưu chúng trực tiếp trong source code, commit vào Git hoặc ghi vào log, người không có quyền truy cập database có thể lấy được thông tin để đọc hoặc sửa dữ liệu.

Ngoài việc bảo vệ bí mật, tài khoản mà ứng dụng sử dụng cần có đúng quyền phục vụ nghiệp vụ. Một service chạy bình thường thường chỉ cần đọc và ghi một tập bảng xác định; nó không cần quyền tạo database, thay đổi schema, xóa bảng hoặc quản trị server. Đây là nguyên tắc quyền tối thiểu (least privilege).

## 1. Phân biệt cấu hình kết nối và bí mật

Một datasource thường cần các thông tin:

- JDBC URL: địa chỉ server, port, database và các tham số kết nối.
- Username: danh tính database mà ứng dụng sử dụng.
- Password hoặc credential tương đương: xác thực danh tính đó.
- TLS và các thiết lập mạng: bảo vệ kết nối và giới hạn nơi được phép kết nối.

JDBC URL thường không phải bí mật nếu chỉ chứa hostname, port và tên database. Tuy nhiên, một số định dạng URL cho phép nhúng username/password hoặc token. Không đặt credential trong URL vì URL dễ xuất hiện trong log, exception, metric hoặc thông tin chẩn đoán.

Cấu hình ứng dụng có thể được quản lý trong file version control nếu không chứa giá trị bí mật. Ví dụ, có thể commit tên biến môi trường và cấu trúc cấu hình, còn giá trị thật được cấp lúc chạy.

## 2. Không hard-code credential trong source code

Không viết password trực tiếp trong Java:

```java
// Không nên: bí mật bị đóng gói cùng mã nguồn.
String password = "production-password";
```

Cũng không commit password thật trong `application.yml`:

```yaml
spring:
  datasource:
    username: shop_app
    password: production-password
```

Các cách này khiến credential có thể tồn tại trong Git history, bản build, image container, log hoặc bản sao source code. Xóa password khỏi file hiện tại không làm nó biến mất khỏi lịch sử Git; nếu bí mật đã bị lộ, cần thu hồi hoặc rotate credential.

Thay vào đó, dùng placeholder:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/shop
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

Khi khởi chạy, Spring Boot resolve `DB_USERNAME` và `DB_PASSWORD` từ môi trường hoặc nguồn cấu hình ngoài. File YAML có thể được commit vì nó không chứa giá trị credential thật.

Không đặt giá trị mặc định là password production trong placeholder, ví dụ `${DB_PASSWORD:secret123}`. Nếu thiếu secret, ứng dụng nên báo lỗi cấu hình rõ ràng thay vì âm thầm dùng một mật khẩu dự phòng yếu.

## 3. Cấp secret từ môi trường chạy

Có thể cấp biến môi trường khi triển khai:

```bash
export DB_USERNAME=shop_app
export DB_PASSWORD='<injected-at-runtime>'
java -jar store-app.jar
```

Trong môi trường container hoặc orchestrator, secret có thể được đưa vào process qua environment variable hoặc mount thành file. Hãy chọn cơ chế mà nền tảng triển khai hỗ trợ và giới hạn ai có thể đọc giá trị đó.

Một số nguồn thường dùng:

| Nguồn | Cách sử dụng | Lưu ý |
|---|---|---|
| Environment variable | Platform inject biến khi start process | Tránh in toàn bộ environment vào log hoặc diagnostic dump. |
| Secret manager | Ứng dụng hoặc deployment platform lấy secret theo danh tính được cấp quyền | Cần quản lý IAM/access policy và rotation. |
| Mounted secret file | Nền tảng mount file chỉ người dùng/process phù hợp mới đọc được | Giới hạn filesystem permission và không copy vào image. |
| Config tree của Spring Boot | Map file trong một thư mục thành property | Hữu ích với Docker/Kubernetes secret được mount thành file. |

Với Spring Boot hỗ trợ Config Data API, có thể import thư mục secret:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Ví dụ thư mục được mount có các file:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Nội dung mỗi file là giá trị tương ứng. Tên file được map thành property key; không cần ghi credential vào YAML. Bỏ tiền tố `optional:` nếu secret là bắt buộc để ứng dụng khởi động và cần fail-fast khi thư mục không tồn tại.

Với Kubernetes, Secret object không nên được xem là an toàn chỉ vì dữ liệu hiển thị ở dạng Base64. Base64 là encoding, không phải encryption. Cần bật encryption at rest phù hợp cho cluster, giới hạn RBAC, giới hạn quyền đọc secret theo namespace/service account và cân nhắc external secret manager.

## 4. Cấu hình datasource trong Spring Boot

Ví dụ cấu hình tối thiểu:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000

  jpa:
    hibernate:
      ddl-auto: validate
```

Các property datasource được Spring Boot bind vào datasource và connection pool. HikariCP là pool mặc định trong nhiều ứng dụng Spring Boot JDBC/JPA nếu có trên classpath.

Một số lưu ý:

- Đặt JDBC URL theo môi trường, ví dụ development, staging và production.
- Mỗi môi trường nên có credential riêng; không dùng chung password production với máy cá nhân.
- Chỉ cấp quyền kết nối từ network/subnet mà ứng dụng cần.
- Dùng TLS khi database và môi trường triển khai hỗ trợ, đồng thời xác minh certificate theo chính sách hệ thống.
- Không đưa username/password vào query parameter hoặc log URL.
- Không trả cấu hình datasource ra API hoặc trang chẩn đoán công khai.

Profile như `application-prod.yml` chỉ là cách chọn cấu hình theo môi trường. Profile không phải secret store: file profile có thể chứa placeholder, hostname và pool settings, nhưng không nên chứa password thật.

## 5. Tách tài khoản chạy ứng dụng và tài khoản migration

Một lỗi thiết kế phổ biến là dùng cùng một database account cho cả ứng dụng và công cụ migration. Khi đó, nếu ứng dụng bị khai thác, kẻ tấn công có thể dùng quyền DDL để thay đổi schema, tạo object hoặc phá hủy dữ liệu.

Nên tách ít nhất hai danh tính:

- **Runtime account:** được ứng dụng Spring Data JPA sử dụng trong thời gian chạy; chỉ có quyền cần thiết để thực hiện nghiệp vụ.
- **Migration account:** được Flyway, Liquibase hoặc quy trình triển khai dùng để tạo/sửa schema. Quyền DDL được giới hạn trong database/schema cần quản lý.

Ví dụ, runtime account có thể cần `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên một số bảng. Nó thường không cần `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, quyền tạo database, superuser hoặc replication.

Migration account có thể cần tạo bảng, index, constraint và thay đổi schema. Credential này chỉ được cấp cho pipeline/deployment job cần chạy migration, không đưa vào runtime container nếu không cần.

Với production, không nên dựa vào Hibernate `ddl-auto=create` hoặc `update` để tự thay đổi schema bằng tài khoản ứng dụng. Có thể dùng Flyway/Liquibase để migration có version và audit rõ ràng, còn Hibernate `ddl-auto=validate` giúp phát hiện mapping không khớp schema mà không yêu cầu ứng dụng có quyền DDL. Tùy chính sách triển khai, `none` cũng có thể được chọn nếu schema validation được thực hiện ở bước khác.

## 6. Ví dụ cấp quyền tối thiểu trên PostgreSQL

Cú pháp quyền phụ thuộc database. Ví dụ sau dành riêng cho PostgreSQL và chỉ minh họa runtime account cho một schema `app`.

Tạo login role:

```sql
CREATE ROLE shop_app LOGIN;
```

Thiết lập password hoặc cơ chế xác thực của role bằng quy trình quản trị database an toàn. Không đặt password thật trong migration script, repository hoặc log CI/CD.

Cấp quyền kết nối và sử dụng schema:

```sql
GRANT CONNECT ON DATABASE shop TO shop_app;
GRANT USAGE ON SCHEMA app TO shop_app;
```

Cấp đúng thao tác trên các bảng mà ứng dụng cần:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app.orders, app.order_items
TO shop_app;
```

Nếu ứng dụng dùng sequence cho khóa sinh tự động, cấp quyền cần thiết cho sequence tương ứng:

```sql
GRANT USAGE, SELECT
ON SEQUENCE app.orders_id_seq
TO shop_app;
```

Tên sequence phải khớp schema thực tế. Nếu có nhiều sequence, cấp quyền trên từng sequence cần dùng hoặc dùng default privileges phù hợp.

Để các bảng được tạo sau này bởi schema owner cũng tự có quyền runtime, PostgreSQL hỗ trợ default privileges:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE shop_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO shop_app;

ALTER DEFAULT PRIVILEGES
FOR ROLE shop_owner
IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES TO shop_app;
```

Lệnh default privileges áp dụng cho object được tạo trong tương lai bởi role được chỉ định, ở đây là `shop_owner`. Nó không tự cấp lại quyền cho các bảng đã tồn tại; cần chạy `GRANT` riêng cho object hiện có.

Trong production, nên giới hạn quyền đến từng bảng hoặc nhóm bảng cần thiết. Ví dụ trên dùng hai bảng để minh họa, không có nghĩa mọi ứng dụng đều cần đủ cả bốn quyền trên mọi bảng.

Tránh cấp `ALL PRIVILEGES`, `CREATE` trên schema hoặc quyền owner cho runtime account nếu nghiệp vụ không cần. Với một số use case, có thể cấp quyền theo cột, view hoặc stored procedure để giới hạn dữ liệu được truy cập.

## 7. Kiểm tra quyền ứng dụng có thực sự tối thiểu

Sau khi cấp quyền, kiểm tra bằng chính runtime account, không chỉ bằng tài khoản DBA.

Ví dụ với PostgreSQL:

```sql
-- Các thao tác được cho phép nếu phù hợp nghiệp vụ:
SELECT id, status FROM app.orders LIMIT 1;

-- Thao tác này cần bị từ chối với runtime account:
CREATE TABLE app.unexpected_table (id BIGINT);
```

Một bài kiểm tra quyền nên xác nhận:

- Ứng dụng đọc được các bảng cần đọc.
- Ứng dụng ghi/cập nhật/xóa được đúng dữ liệu cần thao tác.
- Ứng dụng không thể tạo, alter hoặc drop schema/table khi không có yêu cầu.
- Ứng dụng không đọc được bảng quản trị hoặc dữ liệu thuộc service khác.
- Runtime account không có quyền superuser, owner hoặc quyền quản trị không cần thiết.
- Migration job vẫn thực hiện được thay đổi schema bằng danh tính riêng.

Không nên kiểm tra destructive command trên production chỉ để xác nhận bị từ chối. Có thể dùng database test hoặc staging với cùng grant policy.

## 8. Secret rotation và connection pool

Credential cần được rotate định kỳ hoặc khi có dấu hiệu bị lộ. Tuy nhiên, thay giá trị secret trong secret manager không nhất thiết làm connection pool đang chạy tự cập nhật password.

HikariCP giữ các connection đã mở. Khi một connection mới cần được tạo sau khi password database thay đổi, pool có thể vẫn dùng credential đã bind khi datasource được khởi tạo. Vì vậy, quy trình rotation phải tính đến cả database và datasource đang chạy.

Một quy trình rotation an toàn thường gồm:

1. Tạo credential mới hoặc chuẩn bị cơ chế cho phép hai credential cùng tồn tại trong giai đoạn chuyển tiếp nếu database hỗ trợ.
2. Cập nhật secret ở nơi cấp cho ứng dụng.
3. Tái tạo datasource/connection pool hoặc restart instance theo chiến lược triển khai đã kiểm thử.
4. Xác nhận instance mới mở được connection và health check thành công.
5. Chuyển toàn bộ traffic sang instance đã dùng credential mới.
6. Thu hồi credential cũ sau khi chắc chắn không còn instance hoặc job nào sử dụng nó.

Nếu database chỉ cho phép một password trên một account, cần lên kế hoạch thời gian chuyển đổi và khả năng gián đoạn. Có thể dùng hai login role cùng được cấp một nhóm quyền runtime để chuyển đổi tuần tự: tạo role mới, cấp quyền tương đương, triển khai secret mới, sau đó thu hồi role cũ. Đây là cách phụ thuộc chính sách database và quy trình vận hành.

Không giả định chỉ refresh environment variable là đủ. Hãy kiểm thử hành vi tạo connection mới của pool sau rotation.

## 9. Không để lộ secret qua log và endpoint chẩn đoán

Credential có thể vô tình bị lộ ngoài file cấu hình:

- Log toàn bộ object cấu hình datasource.
- In exception có chứa URL hoặc thông tin xác thực.
- Ghi environment variables vào startup diagnostic.
- Trả `/actuator/env`, `/actuator/configprops` hoặc endpoint quản trị ra Internet mà không có kiểm soát.
- Đưa secret vào command line, Dockerfile, image layer hoặc CI build argument.
- Đính kèm file cấu hình thật trong issue, chat, ticket hoặc báo cáo.

Spring Boot có cơ chế sanitization một số property nhạy cảm ở endpoint Actuator, nhưng không nên dựa vào đó để công khai endpoint. Chỉ expose endpoint cần thiết, bảo vệ bằng authentication/authorization và giới hạn network. Không tự log raw password hoặc token.

Nếu credential đã xuất hiện trong Git, log hoặc ticket, cần coi là đã bị lộ: thu hồi/rotate ngay, điều tra phạm vi truy cập và xử lý bản sao lịch sử theo quy trình tổ chức. Xóa dòng password khỏi commit mới không thu hồi credential đã lộ.

## 10. Phân quyền theo môi trường và service

Không nên dùng một tài khoản database chung cho mọi ứng dụng và môi trường.

Ví dụ:

| Danh tính | Môi trường/phạm vi | Quyền |
|---|---|---|
| `shop_dev_app` | Development | Quyền runtime trên database dev |
| `shop_stage_app` | Staging | Quyền runtime trên database staging |
| `shop_prod_app` | Production | Quyền runtime tối thiểu trên database production |
| `shop_migrator` | Pipeline migration | Quyền DDL cần thiết trên schema ứng dụng |
| `reporting_reader` | Báo cáo | Chỉ đọc view/bảng báo cáo cần thiết |

Tách biệt danh tính giúp:

- Thu hồi quyền một service mà không ảnh hưởng service khác.
- Xác định log/audit thuộc ứng dụng nào.
- Giới hạn thiệt hại khi một credential bị lộ.
- Rotate credential theo lịch riêng.
- Tránh ứng dụng dev vô tình truy cập production.

Nếu nhiều service cùng truy cập một database, mỗi service nên có role riêng và chỉ được cấp quyền lên phần dữ liệu nó cần. Nếu database hỗ trợ row-level security, có thể dùng như một lớp bảo vệ bổ sung, nhưng cần hiểu rõ cách session role và connection pool tương tác với policy.

## 11. Quyền tối thiểu liên quan đến Spring Data JPA

Spring Data JPA không yêu cầu tài khoản runtime phải có quyền quản trị database. Các quyền thực tế phụ thuộc thao tác của ứng dụng:

- Entity đọc dữ liệu cần quyền `SELECT`.
- Persist entity mới thường cần `INSERT` và quyền sequence/identity phù hợp.
- Dirty checking cập nhật entity cần `UPDATE`.
- Xóa entity cần `DELETE`.
- Native query hoặc stored procedure cần quyền tương ứng, ví dụ `EXECUTE`.
- Schema validation cần đọc metadata/catalog ở mức database hỗ trợ; không đồng nghĩa cần quyền DDL.
- Hibernate schema generation hoặc migration cần quyền DDL, nên chạy bằng danh tính riêng.

Nếu ứng dụng dùng auditing, trigger, stored procedure hoặc database view, quyền cần thiết có thể khác. Hãy dựa trên SQL thực tế của use case và grant tối thiểu cần có. Không cấp quyền rộng chỉ vì một lỗi `permission denied`; xác định đúng bảng, sequence, schema hoặc procedure bị từ chối.

## 12. Kiểm thử cấu hình an toàn

Nên có các kiểm tra ở nhiều tầng:

**Kiểm tra cấu hình**

- File cấu hình trong Git chỉ chứa placeholder hoặc giá trị không nhạy cảm.
- Secret được cấp ở runtime từ nguồn đã phê duyệt.
- Thiếu secret bắt buộc khiến ứng dụng fail-fast.
- Không có password thật trong Docker image, artifact hoặc CI log.

**Kiểm tra kết nối**

- Ứng dụng kết nối được bằng runtime account.
- Database endpoint và TLS đúng môi trường.
- Connection pool tạo được connection mới sau rotation thử nghiệm.
- Khi credential sai hoặc bị thu hồi, health check và log thể hiện lỗi xác thực mà không in secret.

**Kiểm tra quyền**

- Runtime account thực hiện được thao tác nghiệp vụ cần thiết.
- Runtime account bị từ chối thao tác DDL/quản trị không cần thiết.
- Migration account có quyền schema đúng phạm vi.
- Mỗi môi trường/service dùng danh tính riêng.

**Kiểm tra vận hành**

- Có người hoặc quy trình chịu trách nhiệm rotation.
- Có quy trình thu hồi khi secret bị lộ.
- Quyền đọc secret và quyền database được rà soát định kỳ.
- Có audit log để truy vết việc cấp, sử dụng và thu hồi credential.

## 13. Checklist triển khai

- Không hard-code hoặc commit password database.
- Dùng placeholder và secret injection từ environment, secret manager hoặc config tree.
- Không nhúng credential trong JDBC URL, log, Dockerfile hoặc image.
- Giới hạn người và process có thể đọc secret.
- Dùng tài khoản runtime riêng, không dùng DBA hoặc schema owner.
- Chỉ cấp quyền SQL mà use case thực sự cần.
- Dùng migration identity riêng cho Flyway/Liquibase hoặc quy trình DDL.
- Cấu hình TLS và network allowlist khi phù hợp.
- Có quy trình rotation tính đến HikariCP và connection đang chạy.
- Kiểm thử cả thao tác được phép và thao tác phải bị từ chối.
- Thu hồi ngay credential đã lộ và điều tra log liên quan.

Quản lý bí mật và quyền database là một phần của thiết kế triển khai ứng dụng Spring Data JPA. Secret manager bảo vệ cách cấp và thay đổi credential; quyền tối thiểu giới hạn những gì ứng dụng có thể làm nếu credential bị lộ. Kết hợp hai biện pháp này với danh tính riêng cho runtime và migration giúp giảm rủi ro mà vẫn giữ quy trình phát triển và triển khai rõ ràng.