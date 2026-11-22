# Nạp dữ liệu mẫu và giữ bí mật kết nối ngoài mã nguồn

Trong một ứng dụng **Spring Data MongoDB**, việc kết nối thành công tới MongoDB Server mới là bước đầu. Lập trình viên thường cần một bộ **dữ liệu mẫu (seed data)** để kiểm tra repository, `MongoTemplate`, truy vấn và giao diện. Đồng thời, URI kết nối có thể chứa tài khoản, mật khẩu, hostname hoặc tham số xác thực: những thông tin này phải được quản lý **bên ngoài mã nguồn**.

Bài học thuộc chương **Khởi tạo** của module `SPRING_DATA_MONGODB`. Ta sẽ chuẩn bị database phát triển, cấu hình Spring Boot nhận URI từ môi trường, nạp sản phẩm mẫu bằng Spring Data MongoDB, kiểm tra lại dữ liệu, rồi nhận diện các lỗi về truy vấn, index, quyền truy cập và bảo mật. Các kỹ thuật này cũng giúp tạo dữ liệu đầu vào cho việc học aggregation, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Sau bài này, bạn có thể:

- Cấu hình kết nối qua biến môi trường/secret manager, không commit credential.
- Viết seed **có thể chạy lại (idempotent)** và chỉ tác động tới database được phép.
- Chọn giữa `MongoTemplate`, repository và `mongoimport` khi chuẩn bị dữ liệu.
- Xác minh số document, mapping, index, truy vấn và các lỗi kết nối phổ biến.

## 1. Các thành phần tham gia

```mermaid
flowchart TD
    ENV[Biến môi trường hoặc secret manager] --> BOOT[Spring Boot: đọc cấu hình, tạo bean]
    BOOT --> DATA[Spring Data MongoDB: MongoTemplate, Repository]
    DATA --> DRIVER[Java Driver: MongoClient, giao thức, pool]
    DRIVER <--> MONGO[(MongoDB Server: collection, index, dữ liệu)]
    SEED[ApplicationRunner chỉ cho môi trường local] --> DATA
```

**Spring Boot** nhận cấu hình và khởi tạo các bean, **Spring Data MongoDB** chuyển yêu cầu từ Java thành thao tác dữ liệu, **MongoDB Java Driver** gửi lệnh và quản lý kết nối, còn **MongoDB Server** thực sự lưu và truy vấn BSON document. Dữ liệu mẫu được ghi vào server thông qua các tầng này; Boot không tự sinh dữ liệu mẫu chỉ vì đã thêm dependency MongoDB.

Có hai cách chuẩn bị dữ liệu thường dùng:

| Cách | Phù hợp khi | Điều cần chú ý |
| --- | --- | --- |
| `ApplicationRunner` kết hợp `MongoTemplate` | Muốn seed theo domain Java, sử dụng mapping Spring Data và điều khiển theo cấu hình chạy | Phải tắt theo mặc định, giới hạn profile/database, tránh ghi đè dữ liệu cũ |
| `mongoimport` hoặc script `mongosh` | Có sẵn fixture JSON/CSV, cần nhập nhiều document độc lập với ứng dụng | Chọn đúng database, kiểm soát upsert/ghi đè và kiểu BSON khi import |

## 2. Giữ thông tin kết nối ngoài mã nguồn

### 2.1. Không ghi URI nhạy cảm trực tiếp trong repository

Đây là **ví dụ cấu hình cần tránh** nếu URI chứa credential:

```yaml
# KHÔNG commit URI thật có mật khẩu vào mã nguồn.
spring:
  data:
    mongodb:
      uri: "mongodb://user:password-placeholder@db.internal:27017/shop"
```

Credential có thể lộ qua lịch sử Git, pull request, bản sao lưu, bản build, ảnh chụp màn hình và log CI. Xóa credential khỏi bản commit mới không xóa các bản sao trước đó. Nếu credential thật đã lộ, cần **thu hồi/đổi credential** và kiểm tra phạm vi ảnh hưởng.

Với **Spring Boot 3.x**, có thể khai báo một placeholder:

```yaml
# src/main/resources/application.yml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}

app:
  seed:
    enabled: false
```

`${MONGODB_URI}` yêu cầu Spring lấy `MONGODB_URI` từ môi trường của tiến trình. Thiếu giá trị phải được xem là lỗi cấu hình; **đừng đặt mật khẩu thật làm giá trị dự phòng**. Tên property MongoDB có thể khác ở phiên bản Spring Boot khác; luôn đối chiếu tài liệu đúng phiên bản đang chạy.

Trong ví dụ trên, cờ `app.seed.enabled` mặc định là `false`. Thêm cấu hình cho profile phát triển để chỉ bật seed khi yêu cầu:

```yaml
# src/main/resources/application-local.yml
app:
  seed:
    enabled: ${SEED_SAMPLE_DATA:false}
```

`${SEED_SAMPLE_DATA:false}` lấy giá trị `SEED_SAMPLE_DATA`, mặc định `false`. Các tệp `application*.yml` trong repository chỉ chứa **tên biến và cờ điều khiển**, không chứa secret.

**Lưu ý về `.env`:** Spring Boot không mặc định đọc một file `.env` bất kỳ trong thư mục dự án. Muốn dùng file này, phải có công cụ nạp nó thành biến môi trường trước khi chạy. Không commit `.env` có secret; có thể giữ `.env.example` với giá trị giả để hướng dẫn. Các biến môi trường cũng không phải kho lưu bí mật tuyệt đối: người có quyền truy cập tiến trình/máy chủ có thể đọc chúng.

### 2.2. Ví dụ chạy local trên Windows

Giả sử MongoDB cục bộ chỉ lắng nghe loopback và **không yêu cầu xác thực trong môi trường học tập riêng**. Ví dụ với PowerShell:

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/shop_local'
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:SEED_SAMPLE_DATA = 'true'

# Ví dụ nếu dự án có Maven Wrapper:
.\mvnw.cmd spring-boot:run
```

Nếu chạy từ IDE hoặc Gradle, đưa **cùng các biến** vào cấu hình chạy tương ứng. IDE có thể không nhận được biến đã khai báo trong một terminal riêng.

Khi URI có tên đăng nhập/mật khẩu, không dán URI thật vào ví dụ lệnh, commit, ticket hay log. Với staging/production, hãy dùng secret manager, cơ chế bí mật của nền tảng triển khai hoặc CI/CD để cấp giá trị lúc chạy. Tránh truyền URI chứa mật khẩu trên dòng lệnh vì thông tin có thể xuất hiện trong lịch sử shell hoặc danh sách tiến trình.

### 2.3. Nguyên tắc bảo vệ kết nối ở môi trường thật

- **Tách môi trường:** local, test, staging và production sử dụng database, tài khoản và secret riêng.
- **Quyền tối thiểu:** tài khoản ứng dụng chỉ có quyền phù hợp với database của nó; tài khoản quản lý index/migration có thể tách riêng.
- **Bảo vệ đường truyền:** dùng TLS khi truy cập qua mạng cần bảo vệ; kiểm tra DNS, cấu hình replica set, `authSource` và các tùy chọn xác thực theo deployment.
- **Tránh lộ qua quan sát:** không log `MONGODB_URI`, config dump, password, hoặc đối tượng exception chứa dữ liệu nhạy cảm. Cẩn thận với debug log và endpoint cấu hình.
- **Quản lý vòng đời credential:** hỗ trợ thu hồi/xoay vòng; URL-encode các ký tự đặc biệt trong credential nếu truyền qua URI theo yêu cầu định dạng.

## 3. Chuẩn bị bộ sản phẩm mẫu

Ta dùng collection `products` trong database `shop_local`. Mỗi document gồm `_id`, `sku`, `name`, `priceVnd`, `stock` và `active`:

```javascript
// shop_local.products
{
  _id: "demo-book-001",
  sku: "BK-001",
  name: "Sổ tay",
  priceVnd: NumberLong("85000"),
  stock: 40,
  active: true
}
{
  _id: "demo-pen-002",
  sku: "PN-002",
  name: "Bút mực",
  priceVnd: NumberLong("25000"),
  stock: 100,
  active: true
}
```

Lựa chọn `_id` ổn định, có tiền tố `demo-`, giúp phân biệt fixture với dữ liệu khác. Các thuộc tính cần được mô tả rõ để cả repository, aggregation và kiểm thử đều có một cấu trúc nhất quán. `priceVnd` dùng số nguyên VND (`long` trong Java) để tránh vấn đề làm tròn của kiểu floating point khi biểu diễn số tiền nguyên.

Một seed tốt có ba tính chất:

1. **Idempotent:** chạy nhiều lần không nhân đôi bản ghi.
2. **Có giới hạn:** chỉ chạy ở môi trường và database cho phép.
3. **Có quy tắc cập nhật rõ:** không bất ngờ xóa collection hoặc ghi đè dữ liệu mà người dùng đã thay đổi trong quá trình phát triển.

Không nên đặt `deleteMany({})` hay `drop()` vào logic khởi động ứng dụng. Nếu cần reset, thiết kế lệnh riêng với bước xác nhận và kiểm tra database đích.

## 4. Seed bằng Spring Data MongoDB

### 4.1. Ánh xạ `Product`

Ví dụ dùng Java 17+ và Spring Data MongoDB. Các đoạn code Java được đặt trong những file phù hợp khi tích hợp vào dự án:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record Product(
        @Id String id,
        String sku,
        String name,
        long priceVnd,
        int stock,
        boolean active
) {}
```

`@Document` chỉ định collection và `@Id` ánh xạ `id` thành `_id`. Spring Data đảm nhận chuyển đổi giữa Java và BSON qua Java Driver. Vì ID mẫu `demo-*` không có định dạng ObjectId, ví dụ này sử dụng khóa dạng chuỗi như dự định.

### 4.2. Seeder được điều khiển bằng profile và cờ cấu hình

Ta dùng `ApplicationRunner` để thực hiện sau khi Spring Boot tạo application context, kết hợp `@Profile("local")` và `@ConditionalOnProperty` để chỉ chạy khi chủ động bật. `MongoTemplate.upsert` với `setOnInsert` chỉ ghi khi document chưa tồn tại:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
@ConditionalOnProperty(name = "app.seed.enabled", havingValue = "true")
public class LocalProductSeeder implements ApplicationRunner {
    private final MongoTemplate mongoTemplate;

    public LocalProductSeeder(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        String databaseName = mongoTemplate.getDb().getName();
        if (!"shop_local".equals(databaseName)) {
            throw new IllegalStateException(
                    "Chỉ cho phép seed database shop_local, hiện tại: "
                            + databaseName
            );
        }

        insertIfMissing("demo-book-001", "BK-001", "Sổ tay",
                85_000L, 40, true);
        insertIfMissing("demo-pen-002", "PN-002", "Bút mực",
                25_000L, 100, true);
    }

    private void insertIfMissing(
            String id, String sku, String name,
            long priceVnd, int stock, boolean active
    ) {
        Query query = Query.query(Criteria.where("_id").is(id));
        Update update = new Update()
                .setOnInsert("sku", sku)
                .setOnInsert("name", name)
                .setOnInsert("priceVnd", priceVnd)
                .setOnInsert("stock", stock)
                .setOnInsert("active", active);

        mongoTemplate.upsert(query, update, Product.class);
    }
}
```

Ý nghĩa từng hàng rào:

- `@Profile("local")`: bean chỉ được tạo khi profile local hoạt động.
- `app.seed.enabled=true`: yêu cầu người chạy bật cờ rõ ràng; mặc định tắt.
- `shop_local`: kiểm tra lại database đích trước khi thực hiện bất kỳ thao tác ghi nào.
- `_id` cố định và `$setOnInsert`: nếu đã có document, không chèn thêm hoặc thay `stock`/`name` vốn đã được chỉnh thử.

Spring Data chuyển lệnh `upsert` thành thao tác MongoDB, driver gửi tới server. Từng upsert lên một document có tính nguyên tử ở cấp document; seed gồm nhiều document **không mặc nhiên là một transaction**. Khi sửa fixture trong source, `$setOnInsert` cũng **không cập nhật** document đã tồn tại; nếu cần cập nhật có chủ đích, phải thiết kế chính sách `$set`/version fixture hoặc reset giới hạn rõ ràng.

### 4.3. Kiểm tra qua repository và index

```java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {
    Optional<Product> findBySku(String sku);
}
```

`findBySku("BK-001")` giúp kiểm tra mapping từ MongoDB sang `Product`. Tuy nhiên Spring Data không tự đảm bảo rằng server có index phù hợp. Trên database local, có thể tạo index theo SKU:

```javascript
// Chỉ chạy sau khi kiểm tra không có SKU trùng.
db.products.createIndex({ sku: 1 }, { unique: true });
```

`@Indexed(unique = true)` là metadata Spring Data; việc tự động tạo index phụ thuộc cấu hình. Trong môi trường triển khai thật, hãy quản lý index có chủ đích qua quy trình migration/script và xác nhận lại trên MongoDB Server.

## 5. Nạp JSON mẫu bằng `mongoimport`

Nếu đã có sẵn dữ liệu mẫu dưới dạng JSON/CSV, không nhất thiết phải khởi động ứng dụng Java chỉ để tạo fixture. `mongoimport` thuộc bộ **MongoDB Database Tools**, có thể nhập một mảng document vào collection.

Ví dụ nội dung `products.json` dùng **MongoDB Extended JSON** để giữ kiểu BSON 64-bit của `priceVnd`:

```json
[
  {
    "_id": "demo-book-001",
    "sku": "BK-001",
    "name": "Sổ tay",
    "priceVnd": {"$numberLong": "85000"},
    "stock": 40,
    "active": true
  },
  {
    "_id": "demo-pen-002",
    "sku": "PN-002",
    "name": "Bút mực",
    "priceVnd": {"$numberLong": "25000"},
    "stock": 100,
    "active": true
  }
]
```

Trong PowerShell, nếu MongoDB đang chạy **cục bộ và không yêu cầu xác thực**, có thể nhập bằng:

```powershell
mongoimport --host 127.0.0.1 --port 27017 `
    --db shop_local --collection products `
    --file products.json --jsonArray `
    --mode upsert --upsertFields _id
```

Ở đây:

- `--db` và `--collection` xác định **nơi nhận dữ liệu**, phải kiểm tra trước khi chạy.
- `--jsonArray` cho biết file chứa một mảng JSON.
- `--mode upsert --upsertFields _id` giúp tìm document có `_id` tương ứng trước khi nhập, tránh tạo document mới cho cùng ID.

**Đánh đổi quan trọng:** khi dùng `mongoimport` ở chế độ upsert, document đã tồn tại có thể bị **cập nhật theo nội dung file**. Điều này khác với `$setOnInsert` trong seeder Java vốn chỉ gán trường khi insert lần đầu. Chỉ dùng import có ghi đè khi việc đồng bộ lại fixture là chủ đích.

Lệnh minh họa không chứa username/password và chỉ dành cho database local. Với database có xác thực, dùng cách cung cấp credential an toàn được công cụ/nền tảng hỗ trợ; tránh gõ URI thật chứa mật khẩu trực tiếp vào command line. Một fixture nên chỉ chứa **dữ liệu giả**, không sao chép thông tin cá nhân hay mật khẩu của người dùng thật.

### 5.1. Chọn phương án nào?

| Nhu cầu | Giải pháp thích hợp |
| --- | --- |
| Tạo vài bản ghi nền khi chạy một ứng dụng demo | `MongoTemplate` với `ApplicationRunner` có điều kiện |
| Fixture phụ thuộc logic domain, mapping, converter của ứng dụng | Seed bằng Spring Data và kiểm thử mapping |
| Nạp hàng nghìn bản ghi mẫu từ tệp có sẵn | `mongoimport` hoặc script nhập dữ liệu riêng |
| Kiểm thử cần bộ dữ liệu khác nhau cho mỗi test case | Thiết lập fixture trong từng test, dùng database/container cô lập |
| Dữ liệu khởi tạo thật của production | Dùng migration/job được kiểm soát và có kế hoạch rollback, không bật seeder local |

## 6. Xác minh sau khi nạp dữ liệu

Chỉ xem log “seed đã chạy” là chưa đủ. Cần kiểm tra **đúng database**, đúng số document, giá trị, kiểu BSON và khả năng truy vấn.

Với MongoDB phát triển trên loopback, mở shell:

```powershell
mongosh mongodb://127.0.0.1:27017/shop_local
```

Sau đó thực hiện:

```javascript
db.getName(); // mong đợi: "shop_local"

db.products.find(
  { _id: { $in: ["demo-book-001", "demo-pen-002"] } },
  { _id: 1, sku: 1, name: 1, priceVnd: 1, stock: 1 }
);

db.products.countDocuments({
  _id: { $in: ["demo-book-001", "demo-pen-002"] }
}); // mong đợi: 2

db.products.getIndexes();

db.products.find({ sku: "BK-001" }).explain("executionStats");
```

Kết quả mong muốn:

1. Tên database là `shop_local`.
2. Hai ID mẫu được tìm thấy, mỗi ID xuất hiện một lần do `_id` là khóa duy nhất.
3. Giá `priceVnd`, `stock`, `active` đúng; repository đọc được chúng vào kiểu `Product`.
4. Index trên `sku` xuất hiện nếu đã chạy lệnh tạo index.
5. Khi chạy seed Java lần thứ hai, số bản ghi **theo hai ID mẫu** vẫn bằng 2.

Chỉ đếm hai ID mẫu vì collection có thể chứa sản phẩm thử nghiệm khác. Không dùng `countDocuments({}) == 2` làm khẳng định nếu môi trường local không trống.

`explain("executionStats")` hiển thị kế hoạch và thống kê thực thi của truy vấn, giúp quan sát `IXSCAN` hay `COLLSCAN`. Với bộ dữ liệu chỉ có hai document, server có thể chọn collection scan dù có index; điều này không tự động là lỗi. Khi học tối ưu hiệu năng, cần dùng dữ liệu đủ lớn và đặc trưng truy cập gần thực tế để đưa ra kết luận.

Nếu chạy nạp dữ liệu qua code Spring Data, có thể xác minh ở tầng ứng dụng:

```java
Product product = productRepository.findBySku("BK-001")
        .orElseThrow(() -> new IllegalStateException("Thiếu dữ liệu mẫu"));

if (product.priceVnd() != 85_000L) {
    throw new IllegalStateException("Giá sản phẩm mẫu không đúng");
}
```

Đoạn trên minh họa code bên trong một phương thức đã có biến `productRepository`. Khi viết kiểm thử thực tế, hãy dùng assertion của framework test để báo lỗi rõ ràng hơn.

## 7. Kiểm thử và tách biệt các môi trường

`@DataMongoTest` hỗ trợ kiểm thử phần truy cập MongoDB trong Spring Boot. Với các hành vi như tạo index, upsert, aggregation, transaction hoặc mapping BSON, nên dùng **MongoDB thực trong môi trường kiểm thử riêng**, ví dụ MongoDB chạy bằng Testcontainers. Mock repository chỉ kiểm tra hành vi mock, không chứng minh driver đã giao tiếp đúng với server.

Các tình huống kiểm thử đáng làm:

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Profile `local` + cờ seed bật + URI vào `shop_local` | Seeder ghi đúng hai ID mẫu |
| Gọi seeder hoặc khởi động lại lần thứ hai | Không sinh dữ liệu trùng và không ghi đè giá trị sẵn có vì dùng `setOnInsert` |
| Profile khác `local` | Seeder không được tạo |
| Profile `local` nhưng cờ seed tắt | Seeder không chạy |
| URI vô tình trỏ sang database khác | Seeder từ chối ghi bằng kiểm tra tên database |
| Kiểm tra `ProductRepository.findBySku` | Đọc đúng record và các kiểu Java đã khai báo |
| Tạo unique index `sku` | Server từ chối mã SKU trùng, nếu index tạo thành công |

Hãy tự tạo fixture riêng trong mỗi nhóm test, hoặc bật seed một cách tường minh nếu thật sự cần. Đừng để các test dựa vào thứ tự chạy hoặc phụ thuộc dữ liệu trong một database chung. Đối với môi trường staging/production, cờ seed local nên luôn **tắt**; tài khoản có quyền đọc/ghi cũng phải được tách riêng theo môi trường.

Nếu một bộ seed yêu cầu cập nhật nhiều document theo kiểu “tất cả cùng thành công hoặc cùng thất bại”, cần thiết kế transaction dựa trên **MongoDB deployment hỗ trợ** và cấu hình transaction manager của Spring Data. Không mặc định một MongoDB standalone cục bộ có đầy đủ khả năng transaction nhiều document. Seed nhỏ bằng các thao tác upsert độc lập thường không cần transaction.

Đối với ứng dụng reactive, có thể dùng `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository` và khởi tạo dữ liệu theo chuỗi `Mono`/`Flux` phù hợp. Đừng gọi `MongoTemplate` blocking trong một luồng xử lý reactive rồi cho rằng thao tác đã trở thành non-blocking. Quy tắc bí mật kết nối, giới hạn database và idempotency không thay đổi khi dùng reactive.

## 8. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể gặp | Cách kiểm tra |
| --- | --- | --- |
| Ứng dụng không khởi động khi thiếu `MONGODB_URI` | Biến chưa được cấp cho đúng process, tên property không đúng phiên bản Boot | Kiểm tra run configuration, profile và cú pháp placeholder |
| `Connection refused` hoặc timeout | MongoDB chưa chạy, sai host/port, firewall/VPN, DNS hoặc topology | Kiểm tra server, địa chỉ và khả năng kết nối từ máy chạy ứng dụng |
| `Authentication failed` | Sai username, password, `authSource` hoặc quyền | Kiểm tra secret từ hệ quản lý, tài khoản và vai trò, không in credential ra log |
| Chạy ứng dụng nhưng không thấy mẫu | Chưa bật profile/cờ seed, bean ngoài phạm vi component scan, trỏ nhầm database | Kiểm tra profile, `app.seed.enabled`, `db.getName()` và query bằng shell |
| Chạy lại tạo thêm bản ghi | Seed dùng ID ngẫu nhiên hoặc insert không có khóa cố định | Dùng `_id` ổn định và upsert theo điều kiện xác định |
| `E11000 duplicate key` | Trùng `_id` hoặc unique index trên `sku` | Kiểm tra dữ liệu và index, sửa fixture trước khi chạy lại |
| Sản phẩm mẫu vẫn giữ giá cũ sau khi sửa code seeder | `$setOnInsert` không cập nhật document đã tồn tại | Thiết kế chính sách cập nhật hoặc reset fixture riêng có kiểm soát |
| Truy vấn SKU chậm khi dữ liệu lớn | Index thiếu/không phù hợp, dữ liệu nhiều hoặc bộ lọc không chọn lọc | `getIndexes()`, `explain("executionStats")` và đo truy vấn thực tế |
| URI/mật khẩu xuất hiện trong log hoặc pipeline | In cấu hình, log debug quá rộng, đưa secret vào command line | Dừng phát tán, ẩn giá trị, thu hồi/đổi credential đã lộ |

Một trường hợp thực tế: biến `MONGODB_URI` được đặt trong PowerShell nhưng ứng dụng lại chạy trực tiếp từ IDE đã mở trước đó. IDE có thể không kế thừa biến mới, dẫn tới lỗi dù terminal in ra biến đúng. Hãy kiểm tra **môi trường của đúng tiến trình** chạy ứng dụng và dùng tính năng quản lý secret trong IDE/nền tảng nếu được hỗ trợ.

## 9. Thực hành hoàn chỉnh

1. Chuẩn bị MongoDB Server dành cho phát triển, chỉ kết nối đến database `shop_local`.
2. Tạo cấu hình Spring Boot 3.x với `spring.data.mongodb.uri: ${MONGODB_URI}` và cờ `app.seed.enabled` mặc định tắt.
3. Cấp `MONGODB_URI` từ môi trường/secret manager; xác minh không commit credential.
4. Viết `Product`, `ProductRepository` và `LocalProductSeeder` có ID cố định, profile `local`, cờ seed và kiểm tra database đích.
5. Chạy ứng dụng với profile `local` và `SEED_SAMPLE_DATA=true`; xác minh hai bản ghi qua `mongosh` và repository.
6. Khởi động lại để kiểm tra idempotency; thử tắt cờ seed hoặc đổi database để xác minh cơ chế từ chối ghi.
7. Tạo index phục vụ `findBySku`, đọc `explain` và kiểm thử trên một MongoDB test instance độc lập.
8. Khi triển khai staging/production, nhận kết nối qua secret manager, sử dụng quyền tối thiểu, TLS phù hợp và giữ chức năng seed local ở trạng thái tắt.

**Ghi nhớ:** dữ liệu mẫu phục vụ phát triển chỉ an toàn khi có **phạm vi, khóa định danh và quy tắc ghi rõ ràng**. Spring Boot nhận thông tin kết nối từ môi trường; Spring Data MongoDB tạo truy vấn/update; Java Driver giao tiếp và MongoDB Server lưu dữ liệu. Mục tiêu là có thể dựng lại trạng thái học tập, thử repository/aggregation/index và chẩn đoán hiệu năng mà không để lộ bí mật kết nối hoặc tác động ngoài ý muốn lên dữ liệu thật.
