# Cấu hình ghi nhật ký SQL và tham số truy vấn theo môi trường

## 1. Mục tiêu và phạm vi

Khi Spring Data JPA thực thi một truy vấn, Hibernate thường gửi SQL tới cơ sở dữ liệu dưới dạng câu lệnh có tham số, chẳng hạn `WHERE status = ?`. Để điều tra truy vấn, cần quan sát hai phần riêng biệt: câu SQL mà Hibernate tạo ra và giá trị được gắn vào từng dấu hỏi. Hai phần này có logger và mức log khác nhau.

Bài này áp dụng cho ứng dụng Spring Boot dùng Hibernate làm JPA provider, đặc biệt là Hibernate 6 trong các dòng Spring Boot 3.x. Cấu hình theo profile giúp bật log chi tiết trong môi trường phát triển và giữ log an toàn, ít nhiễu trong môi trường production.

## 2. Hai logger cần phân biệt

| Nội dung | Logger | Mức log thường dùng |
| --- | --- | --- |
| Câu SQL do Hibernate tạo | `org.hibernate.SQL` | `DEBUG` |
| Giá trị bind vào tham số JDBC | `org.hibernate.orm.jdbc.bind` | `TRACE` |

- `org.hibernate.SQL` hiển thị câu SQL. Các giá trị đầu vào thường vẫn xuất hiện dưới dạng dấu `?` vì Hibernate dùng prepared statement.
- `org.hibernate.orm.jdbc.bind` hiển thị kiểu dữ liệu và giá trị thực tế được bind vào từng vị trí tham số. Logger này cần mức `TRACE`; đặt `DEBUG` thường không đủ.
- `spring.jpa.properties.hibernate.format_sql` chỉ định dạng SQL nhiều dòng để dễ đọc. Nó không bật logger và không làm thay đổi ý nghĩa truy vấn.

Không nhầm hai logger trên với `spring.jpa.show-sql`. Thuộc tính `show-sql` yêu cầu Hibernate in SQL trực tiếp ra console, khiến việc kiểm soát bằng logging framework, profile và appender kém nhất quán. Nên để `false` và quản lý log qua `logging.level`.

## 3. Cấu hình mặc định trong application.yml

Đặt cấu hình nền an toàn trong `src/main/resources/application.yml`. Ở cấu hình chung, SQL chỉ được ghi ở mức cảnh báo và log giá trị bind bị tắt:

```yaml
spring:
  jpa:
    show-sql: false
    properties:
      hibernate:
        format_sql: true

logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: 'OFF'
```

`format_sql: true` giúp câu SQL dễ đọc khi logger được bật. Nếu ứng dụng cần log gọn hơn, có thể đặt thành `false`; thay đổi này chỉ ảnh hưởng cách trình bày.

## 4. Bật log chi tiết ở môi trường development

Tạo `src/main/resources/application-dev.yml`:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Khi chạy với profile `dev`, Hibernate sẽ ghi câu SQL ở mức `DEBUG` và giá trị tham số ở mức `TRACE`. Ví dụ minh họa một truy vấn tìm người dùng theo trạng thái:

```text
DEBUG org.hibernate.SQL - select u.id, u.email, u.status from users u where u.status = ?
TRACE org.hibernate.orm.jdbc.bind - binding parameter (1:VARCHAR) <- [ACTIVE]
```

Định dạng chính xác của dòng log phụ thuộc phiên bản Hibernate và logging backend. Điều cần xác nhận là câu SQL xuất hiện ở logger `org.hibernate.SQL`, còn giá trị tham số xuất hiện ở logger `org.hibernate.orm.jdbc.bind`.

## 5. Giữ log an toàn ở production

Tạo `src/main/resources/application-prod.yml` hoặc giữ nguyên các giá trị mặc định trong `application.yml`. Nếu muốn thể hiện chính sách production một cách tường minh, dùng:

```yaml
logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: 'OFF'
```

Không bật `TRACE` cho bind parameters thường trực ở production. Giá trị bind có thể chứa email, số điện thoại, mã định danh, dữ liệu nghiệp vụ hoặc thông tin bí mật. Log chi tiết cũng làm tăng dung lượng log và có thể ảnh hưởng hiệu năng. Khi cần điều tra sự cố production, hãy dùng một khoảng thời gian ngắn, phạm vi logger hẹp, dữ liệu đã được kiểm soát và chính sách truy cập/lưu trữ log phù hợp.

## 6. Chọn profile khi chạy ứng dụng

Spring Boot nạp `application.yml` làm cấu hình chung và nạp thêm file theo profile đang hoạt động. Giá trị trong `application-dev.yml` hoặc `application-prod.yml` sẽ ghi đè cấu hình tương ứng trong file chung.

Cách khuyến nghị là chọn profile từ môi trường triển khai, thay vì cố định profile trong file cấu hình được đóng gói:

```bash
export SPRING_PROFILES_ACTIVE=dev
./gradlew bootRun
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
.\gradlew.bat bootRun
```

Khi chạy JAR, có thể truyền profile bằng tham số:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Trong Docker hoặc môi trường triển khai, đặt biến môi trường `SPRING_PROFILES_ACTIVE` theo cấu hình của môi trường đó. Tránh đưa thông tin bí mật hoặc dữ liệu môi trường thật vào file cấu hình được commit.

## 7. Bật tạm thời bằng biến môi trường

Nếu chỉ cần điều tra nhanh mà không muốn sửa file profile, Spring Boot cho phép đặt mức log qua biến môi trường:

```bash
LOGGING_LEVEL_ORG_HIBERNATE_SQL=DEBUG
LOGGING_LEVEL_ORG_HIBERNATE_ORM_JDBC_BIND=TRACE
```

Đặt các biến này trong tiến trình/container cần kiểm tra và gỡ chúng sau khi hoàn tất. Khi đồng thời có cấu hình từ file, biến môi trường và tham số dòng lệnh, Spring Boot áp dụng thứ tự ưu tiên của hệ thống externalized configuration; hãy kiểm tra cấu hình triển khai thực tế nếu mức log không như mong đợi.

## 8. Quy trình xác minh

1. Chạy ứng dụng với profile `dev` và xác nhận profile đã được kích hoạt.
2. Thực hiện một thao tác thực sự gọi repository Spring Data JPA, chẳng hạn tìm bản ghi theo một thuộc tính.
3. Kiểm tra log có câu SQL từ `org.hibernate.SQL` ở mức `DEBUG`.
4. Kiểm tra log có dòng bind từ `org.hibernate.orm.jdbc.bind` ở mức `TRACE`; đối chiếu thứ tự tham số với các dấu `?` trong câu SQL.
5. Chạy lại với profile `prod` và xác nhận giá trị bind không xuất hiện.
6. Sau khi điều tra xong, bỏ các override tạm thời và giữ cấu hình theo chính sách của từng môi trường.

Không phải mọi thao tác repository đều phát sinh SQL ngay tại dòng gọi phương thức. Hibernate có thể trì hoãn việc gửi lệnh đến thời điểm flush hoặc commit transaction. Vì vậy, khi xác minh, hãy quan sát toàn bộ thao tác trong transaction và chắc chắn rằng truy vấn thực sự cần truy cập cơ sở dữ liệu.

## 9. Các lỗi cấu hình thường gặp

**Có SQL nhưng không thấy giá trị tham số.** Kiểm tra logger `org.hibernate.orm.jdbc.bind` đã được đặt ở `TRACE` chưa. Logger SQL ở `DEBUG` không tự hiển thị giá trị bind.

**Đã đặt `TRACE` nhưng vẫn không thấy bind.** Xác nhận ứng dụng đang dùng Hibernate 6 và logger category đúng. Nếu dự án dùng Hibernate 5, category bind thường gặp là `org.hibernate.type.descriptor.sql.BasicBinder`; không bật đồng thời nhiều category cũ/mới nếu chưa xác định phiên bản provider.

**SQL không được định dạng.** Kiểm tra `spring.jpa.properties.hibernate.format_sql: true`. Thuộc tính này chỉ định dạng câu SQL; nó không thay thế `logging.level.org.hibernate.SQL`.

**Dùng `spring.jpa.show-sql: true` nhưng không kiểm soát được log.** Chuyển về `false` và cấu hình logger của Hibernate để log đi qua hệ thống logging của ứng dụng.

**Không thấy SQL khi gọi repository.** Kiểm tra thao tác có thực sự truy cập database không, có được phục vụ từ cache không, transaction đã flush chưa và ứng dụng có đang dùng đúng profile/cấu hình hay không.

**Log có dấu `?` thay vì giá trị.** Đây là hành vi bình thường của prepared statement. Giá trị bind được ghi ở logger riêng, theo vị trí tham số.

## 10. Lưu ý bảo mật và vận hành

- Chỉ bật log giá trị bind ở môi trường phát triển hoặc trong đợt điều tra có kiểm soát.
- Không ghi mật khẩu, token, khóa truy cập, dữ liệu cá nhân hoặc payload nhạy cảm vào log dùng chung.
- Dùng dữ liệu kiểm thử đã được làm giả/ẩn danh khi cần quan sát tham số.
- Giới hạn thời gian bật `TRACE`, quyền đọc log và thời gian lưu log; tắt cấu hình tạm ngay sau khi điều tra.
- Với production, ưu tiên metric, tracing, slow query log và công cụ quan sát của database. Chỉ bật SQL/bind log khi có lý do vận hành cụ thể.

## 11. Bảng tra cứu nhanh

| Nhu cầu | Cấu hình |
| --- | --- |
| Tắt in SQL trực tiếp ra console | `spring.jpa.show-sql: false` |
| Định dạng SQL | `spring.jpa.properties.hibernate.format_sql: true` |
| Ghi câu SQL ở development | `logging.level.org.hibernate.SQL: DEBUG` |
| Ghi giá trị bind ở development | `logging.level.org.hibernate.orm.jdbc.bind: TRACE` |
| Tắt giá trị bind ở production | `logging.level.org.hibernate.orm.jdbc.bind: 'OFF'` |

Thiết kế này giúp mỗi môi trường có mức quan sát phù hợp: development có đủ SQL và tham số để tìm lỗi truy vấn; production giữ log gọn và hạn chế rò rỉ dữ liệu.