# Nạp dữ liệu mẫu và tách cấu hình theo môi trường

Một ứng dụng Spring Data Neo4j thường cần dữ liệu mẫu để phát triển, kiểm thử và trình diễn. Đồng thời, ứng dụng có thể chạy ở nhiều môi trường như máy cá nhân, kiểm thử tích hợp, staging và production. Mỗi môi trường có địa chỉ Neo4j, database, thông tin xác thực và chính sách dữ liệu riêng.

Bài học này trình bày cách nạp dữ liệu mẫu có thể chạy lặp lại an toàn, sau đó tổ chức cấu hình bằng Spring Boot profiles và biến môi trường. Mục tiêu là giúp tầng dữ liệu đồ thị khởi động nhất quán, giữ bí mật kết nối và tránh để dữ liệu minh họa đi vào hệ thống thật.

## 1. Phân biệt dữ liệu mẫu, dữ liệu kiểm thử và dữ liệu production

Trước khi viết mã khởi tạo, cần xác định dữ liệu nào được nạp và ở môi trường nào:

| Loại dữ liệu | Mục đích | Nơi sử dụng | Cách quản lý |
|---|---|---|---|
| Dữ liệu mẫu (seed data) | Tạo một đồ thị nhỏ, dễ hiểu để phát triển hoặc demo | Chủ yếu môi trường `dev` | Script Cypher hoặc initializer có kiểm soát |
| Dữ liệu fixture kiểm thử | Chuẩn bị trạng thái xác định cho từng test | Unit/integration test | Test setup, transaction hoặc database dùng riêng |
| Dữ liệu production | Dữ liệu nghiệp vụ thực tế | `prod` | Luồng nghiệp vụ và quy trình nhập dữ liệu được phê duyệt |

Không nên dùng cùng một cách khởi tạo cho cả ba loại. Dữ liệu mẫu thường có thể tạo lại; fixture cần cô lập để test có kết quả lặp lại; dữ liệu production cần quy trình nhập, kiểm tra và kiểm toán phù hợp.

Với module Spring Data Neo4j, ví dụ xuyên suốt sẽ dùng hai loại node `Person` và `Movie`, nối với nhau bằng relationship `ACTED_IN`:

```text
(Person {personId, name})-[:ACTED_IN]->(Movie {movieId, title})
```

Các thuộc tính `personId` và `movieId` là khóa nghiệp vụ ổn định dùng để nhận diện dữ liệu mẫu. Chúng giúp initializer tìm lại đúng node khi ứng dụng khởi động lần sau.

## 2. Chuẩn bị ràng buộc trước khi nạp dữ liệu

Seed data nên có khóa nhận diện rõ ràng. Nếu chỉ dùng `CREATE`, mỗi lần khởi động ứng dụng có thể tạo thêm node giống nhau. Dùng `MERGE` theo khóa ổn định giúp câu lệnh có thể chạy lặp lại mà không tạo bản sao mới.

Để bảo vệ khóa nghiệp vụ khi có nhiều tiến trình cùng khởi tạo, tạo uniqueness constraint trong Neo4j:

```cypher
CREATE CONSTRAINT person_person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT movie_movie_id_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.movieId IS UNIQUE;
```

Các constraint này bảo đảm mỗi `personId` chỉ thuộc về một node `Person` và mỗi `movieId` chỉ thuộc về một node `Movie`. Tên constraint nên có quy ước nhất quán để dễ quản lý khi schema phát triển.

Trong hệ thống thực tế, schema constraint nên được quản lý bằng migration hoặc quy trình triển khai schema có phiên bản. Có thể chạy các lệnh trên bằng Neo4j Browser trong môi trường học tập, nhưng không nên để mọi instance ứng dụng production tự ý thay đổi schema khi khởi động.

## 3. Nạp dữ liệu bằng Cypher với MERGE

Một câu lệnh Cypher có thể tạo hoặc tìm lại node theo khóa, cập nhật các thuộc tính mẫu và tạo relationship:

```cypher
MERGE (p:Person {personId: $personId})
SET p.name = $personName
MERGE (m:Movie {movieId: $movieId})
SET m.title = $movieTitle
MERGE (p)-[:ACTED_IN]->(m)
```

`MERGE` tìm pattern đã tồn tại; nếu chưa có thì tạo pattern đó. `SET` cập nhật thuộc tính theo dữ liệu truyền vào. Vì các node được nhận diện bằng khóa ổn định, chạy lại câu lệnh sẽ tìm đúng node cũ. Relationship cũng được `MERGE` theo cặp node và kiểu `ACTED_IN`, tránh tạo relationship trùng cho cùng cặp node theo pattern này.

Tham số `$personId`, `$personName`, `$movieId` và `$movieTitle` được truyền riêng. Không nối dữ liệu vào chuỗi Cypher bằng phép cộng chuỗi; tham số giúp truy vấn an toàn và dễ tái sử dụng.

Lưu ý: `SET` ở ví dụ trên ghi đè `name` và `title` bằng giá trị seed mỗi lần chạy. Đây là hành vi phù hợp cho dữ liệu demo có giá trị cố định. Với dữ liệu có thể được người dùng chỉnh sửa, hãy cân nhắc `ON CREATE SET` để chỉ đặt giá trị ban đầu, hoặc chỉ chạy seed trên database dành riêng cho phát triển.

## 4. Tự động nạp dữ liệu khi ứng dụng khởi động

Spring Boot cung cấp `CommandLineRunner` và `ApplicationRunner` để thực hiện công việc sau khi context được khởi tạo. Có thể kết hợp `CommandLineRunner` với `Neo4jClient` để chạy câu lệnh Cypher khi profile phát triển đang hoạt động.

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevelopmentDataInitializer implements CommandLineRunner {

    private final Neo4jClient neo4jClient;

    public DevelopmentDataInitializer(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Override
    public void run(String... args) {
        neo4jClient.query("""
            MERGE (p:Person {personId: $personId})
            SET p.name = $personName
            MERGE (m:Movie {movieId: $movieId})
            SET m.title = $movieTitle
            MERGE (p)-[:ACTED_IN]->(m)
            """)
            .bind("person-001").to("personId")
            .bind("An").to("personName")
            .bind("movie-001").to("movieId")
            .bind("Mùa hè").to("movieTitle")
            .run();
    }
}
```

`Neo4jClient` là API của Spring Data Neo4j để chạy Cypher và xử lý kết quả. Các lời gọi `bind(value).to("parameterName")` liên kết giá trị Java với tham số có tên trong truy vấn. `@Profile("dev")` khiến component này chỉ được đăng ký khi profile `dev` hoạt động.

Vì vậy, khi chạy ứng dụng với profile `dev`, dữ liệu mẫu được nạp tự động. Khi chạy với profile `prod`, initializer không được tạo và không ghi dữ liệu demo vào database production.

Nếu cần nạp nhiều node và relationship, có thể gom chúng vào một hoặc một số câu lệnh Cypher có tham số. Với tập dữ liệu lớn, không nên nhồi hàng trăm nghìn thao tác vào một `CommandLineRunner`; hãy dùng công cụ import, batch có kiểm soát hoặc pipeline dữ liệu riêng.

### MERGE, CREATE và tính lặp an toàn

| Câu lệnh | Hành vi | Khi phù hợp |
|---|---|---|
| `CREATE` | Luôn tạo node hoặc relationship mới | Khi mỗi lần chạy phải tạo một thực thể mới theo chủ đích |
| `MERGE` | Tìm pattern; chỉ tạo nếu pattern chưa tồn tại | Seed data có khóa ổn định và có thể chạy lại |
| `SET` | Gán hoặc cập nhật property | Đồng bộ thuộc tính theo giá trị seed |
| `ON CREATE SET` | Chỉ gán property khi `MERGE` tạo pattern mới | Khởi tạo giá trị mặc định mà không ghi đè thay đổi về sau |
| `ON MATCH SET` | Chỉ cập nhật property khi pattern đã tồn tại | Điều chỉnh dữ liệu cũ khi seed được chạy lại có chủ đích |

`MERGE` không thay thế uniqueness constraint. Khi có nhiều tiến trình chạy đồng thời, constraint giúp bảo vệ tính duy nhất ở database. Ngoài ra, pattern trong `MERGE` cần được thiết kế cẩn thận: nếu đưa quá nhiều property biến đổi vào pattern, Neo4j có thể coi đó là pattern khác và tạo thêm node. Hãy dùng khóa ổn định trong phần pattern, rồi cập nhật thuộc tính còn lại bằng `SET`.

## 5. Tách cấu hình chung và cấu hình theo profile

Spring Boot hỗ trợ file cấu hình chung `application.yml` và file riêng theo profile như `application-dev.yml`, `application-test.yml` hoặc `application-prod.yml`. Cấu hình profile được nạp khi profile tương ứng được kích hoạt và có thể ghi đè giá trị chung.

Ví dụ cấu trúc:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
```

`application.yml` giữ cấu hình chung của ứng dụng:

```yaml
spring:
  application:
    name: graph-learning
  neo4j:
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}
    database: ${NEO4J_DATABASE:neo4j}
```

Thông tin URI có thể được đặt theo từng profile để tránh dùng nhầm địa chỉ database giữa môi trường.

### Profile dev

`application-dev.yml` dành cho máy phát triển:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
```

Giá trị mặc định trỏ đến Neo4j cục bộ. Username có mặc định phục vụ môi trường học tập, còn password vẫn phải được cung cấp qua biến môi trường `NEO4J_PASSWORD`.

### Profile test

`application-test.yml` có thể trỏ đến một Neo4j riêng cho kiểm thử:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7688}
```

Trong CI hoặc integration test, nên cấp phát database tạm bằng Testcontainers hoặc môi trường kiểm thử cô lập. Không dùng database production làm nơi chạy test vì fixture có thể tạo, sửa hoặc xóa dữ liệu.

### Profile prod

`application-prod.yml` yêu cầu URI được cấp từ môi trường triển khai:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI}
```

Trong production, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` và database cần được cung cấp qua cấu hình triển khai hoặc secret manager. Với dịch vụ Neo4j hỗ trợ kết nối TLS, dùng URI bảo mật phù hợp như `neo4j+s://...` theo hướng dẫn của nhà cung cấp. Không commit mật khẩu, token hoặc URI có chứa thông tin xác thực vào Git.

## 6. Kích hoạt profile và cung cấp biến môi trường

Profile có thể được kích hoạt bằng biến môi trường `SPRING_PROFILES_ACTIVE` hoặc tham số dòng lệnh.

Ví dụ trên PowerShell khi phát triển cục bộ:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USERNAME = "neo4j"
$env:NEO4J_PASSWORD = "your-local-password"
$env:NEO4J_DATABASE = "neo4j"
./mvnw spring-boot:run
```

Ví dụ trên Bash:

```bash
export SPRING_PROFILES_ACTIVE=dev
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD='your-local-password'
export NEO4J_DATABASE=neo4j
./mvnw spring-boot:run
```

Hoặc truyền profile khi chạy ứng dụng:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Không nên đặt `spring.profiles.active: dev` cố định trong `application.yml` dùng chung. Nếu cấu hình đó được đóng gói vào artifact triển khai, ứng dụng có thể vô tình bật initializer dữ liệu mẫu ở môi trường khác. Hãy để pipeline triển khai chọn profile rõ ràng.

Các biến môi trường cũng giúp cùng một artifact có thể chạy ở nhiều môi trường mà không cần sửa file cấu hình trong JAR. Cần lưu ý quy tắc ưu tiên cấu hình của Spring Boot: tham số dòng lệnh và biến môi trường có thể ghi đè giá trị trong file cấu hình. Khi debug, hãy kiểm tra profile thực sự đang hoạt động và nguồn cấu hình đã cung cấp giá trị kết nối.

## 7. Giữ bí mật và tránh cấu hình sai môi trường

Một số nguyên tắc quan trọng khi quản lý cấu hình Neo4j:

- Không lưu password thật trong `application.yml`, `application-dev.yml` hoặc file được commit vào Git.
- Dùng biến môi trường, secret manager hoặc cơ chế quản lý secret của nền tảng triển khai để cấp credential.
- Tách tài khoản và database giữa dev, test, staging và production khi có thể.
- Cấp quyền tối thiểu cần thiết cho từng ứng dụng; không dùng tài khoản quản trị để chạy ứng dụng thường ngày.
- Không bật initializer dữ liệu mẫu trong production. Dùng `@Profile("dev")` và có thể bổ sung `@ConditionalOnProperty` nếu cần công tắc bật/tắt rõ ràng.
- Không ghi password hoặc chuỗi kết nối chứa credential vào log khi ứng dụng khởi động hay khi báo lỗi.
- Khi thay đổi URI hoặc credential, cập nhật secret ở đúng môi trường và kiểm tra kết nối trước khi đưa phiên bản mới vào phục vụ.

Nếu cần thêm công tắc cho phép seed data, có thể kết hợp profile với property:

```java
@Component
@Profile("dev")
@ConditionalOnProperty(
    name = "app.neo4j.seed.enabled",
    havingValue = "true"
)
public class DevelopmentDataInitializer implements CommandLineRunner {
    // Phần thực thi seed data như ví dụ phía trên.
}
```

Và cấu hình trong `application-dev.yml`:

```yaml
app:
  neo4j:
    seed:
      enabled: true
```

Khi đó, initializer chỉ chạy khi profile `dev` đang hoạt động và property được bật. Trong môi trường cần kiểm soát chặt, có thể đặt mặc định `false` rồi bật rõ ràng trong file cấu hình local hoặc lệnh chạy.

## 8. Kiểm tra dữ liệu và cấu hình sau khi khởi động

Sau khi ứng dụng khởi động với profile `dev`, có thể dùng Neo4j Browser để xác minh dữ liệu:

```cypher
MATCH (p:Person {personId: 'person-001'})
OPTIONAL MATCH (p)-[r:ACTED_IN]->(m:Movie)
RETURN p, r, m
```

Kiểm tra số lượng node theo khóa:

```cypher
MATCH (p:Person)
RETURN count(p) AS people;

MATCH (m:Movie)
RETURN count(m) AS movies;
```

Khởi động ứng dụng lần thứ hai rồi chạy lại các truy vấn. Nếu seed được thiết kế idempotent, node có cùng `personId` và `movieId` không tăng lên theo mỗi lần chạy; relationship `ACTED_IN` cũng không bị nhân bản cho cùng pattern.

Khi kiểm tra cấu hình, cần xác nhận:

1. Profile mong muốn đã được kích hoạt, ví dụ `dev` hoặc `test`.
2. URI trỏ đúng máy chủ và cổng Neo4j của môi trường hiện tại.
3. Username, password và database được cấp đúng, không phải giá trị còn sót từ môi trường khác.
4. Ứng dụng kết nối được và có quyền thực hiện truy vấn cần thiết.
5. Component seed chỉ được tạo trong profile cho phép và không xuất hiện trong production.

Không nên chỉ dựa vào việc ứng dụng khởi động thành công để kết luận dữ liệu đã đúng. Hãy xác minh node, relationship và số lượng bản ghi bằng truy vấn cụ thể.

## 9. Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không kết nối được Neo4j | URI sai, server chưa chạy, cổng không mở hoặc credential không đúng | Kiểm tra URI, trạng thái server, username/password và quyền truy cập. |
| Password không được nạp | Biến `NEO4J_PASSWORD` chưa được khai báo hoặc tên biến sai | Kiểm tra môi trường chạy ứng dụng và nguồn secret. |
| Seed tạo node trùng | Dùng `CREATE`, `MERGE` theo thuộc tính không ổn định hoặc thiếu constraint | Dùng khóa nghiệp vụ ổn định trong `MERGE` và tạo uniqueness constraint. |
| Seed ghi đè dữ liệu đã chỉnh sửa | Dùng `SET` mỗi lần khởi động | Dùng `ON CREATE SET`, hoặc chỉ seed database demo riêng. |
| Seed chạy ở production | Profile dev được kích hoạt nhầm hoặc component không giới hạn profile | Kiểm tra `SPRING_PROFILES_ACTIVE`, dùng `@Profile("dev")` và công tắc cấu hình. |
| Không tìm thấy dữ liệu sau khởi động | Initializer chưa được đăng ký, profile không đúng hoặc lệnh seed thất bại | Kiểm tra log khởi động, profile và chạy truy vấn xác minh. |
| Test làm bẩn database dùng chung | Fixture chạy trên database không cô lập | Dùng Neo4j riêng cho test, Testcontainers hoặc dọn dữ liệu trong quy trình test. |

## 10. Quy trình đề xuất cho dự án

1. Khai báo dependency `spring-boot-starter-data-neo4j` và cấu hình kết nối cơ bản.
2. Tạo các profile `dev`, `test` và `prod` với URI cùng thông số riêng.
3. Đưa credential ra biến môi trường hoặc secret manager.
4. Xác định khóa nghiệp vụ cho dữ liệu mẫu và tạo uniqueness constraint tương ứng.
5. Viết seed Cypher dùng `MERGE` và tham số có tên để có thể chạy lặp lại.
6. Đóng gói initializer trong `@Profile("dev")`; tách fixture test khỏi dữ liệu demo.
7. Khởi động theo profile, xác minh node và relationship bằng Cypher, sau đó thử khởi động lần nữa để kiểm tra tính idempotent.
8. Trong production, để pipeline triển khai cấp profile, URI và secret; không kích hoạt seed demo.

## 11. Ghi nhớ

Nạp dữ liệu mẫu tốt cần có khóa nhận diện ổn định, dùng `MERGE` thay cho `CREATE` khi muốn chạy lặp, và bảo vệ khóa bằng uniqueness constraint. Với Spring Data Neo4j, có thể dùng `Neo4jClient` trong `CommandLineRunner` để nạp seed data khi ứng dụng khởi động; giới hạn component bằng `@Profile("dev")` để tránh tác động đến môi trường thật.

Spring Boot profiles giúp tách cấu hình theo môi trường, còn biến môi trường và secret manager giữ thông tin kết nối bên ngoài mã nguồn. Khi kết hợp hai cơ chế này với bước xác minh bằng Cypher, ứng dụng có thể khởi tạo dữ liệu phát triển nhất quán và kết nối đúng Neo4j ở từng môi trường triển khai.
