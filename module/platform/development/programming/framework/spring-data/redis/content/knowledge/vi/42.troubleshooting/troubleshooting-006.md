# Truy vấn Repository thiếu kết quả do chỉ mục không đồng bộ trong Spring Data Redis

## 1. Hiện tượng: dữ liệu vẫn còn nhưng phương thức findBy… trả rỗng

Một ứng dụng Spring Boot lưu khách hàng vào Redis bằng Spring Data Redis Repository. Sau khi ghi dữ liệu, truy vấn theo ID hoạt động, nhưng truy vấn theo email lại trả kết quả rỗng:

```java
repository.findById("c-101");                 // Optional có Customer
repository.findByEmail("an@example.test");   // Optional.empty()
```

Người phát triển mở Redis CLI và thấy hash của khách hàng vẫn tồn tại. Điều này gây nhầm lẫn: **nếu dữ liệu ở Redis còn, tại sao repository lại không tìm được?**

Nguyên nhân có thể là **chỉ mục phụ (secondary index) mà Spring Data Redis dùng cho derived query không chứa membership tương ứng với dữ liệu gốc**. Repository không thực hiện một phép quét toàn bộ Redis hashes để tìm tất cả đối tượng có `email` bằng giá trị yêu cầu. Với thuộc tính truy vấn được hỗ trợ, nó dựa vào chỉ mục được quản lý riêng.

Tình huống minh họa:

```text
                 CustomerRepository
                   /            \
                  /              \
        findById("c-101")   findByEmail("an@example.test")
                |                     |
                v                     v
       Redis hash "customers:c-101"   Redis secondary index SET
                |                     |
                v                     v
          email tồn tại          không có membership c-101
                |                     |
                v                     v
          Trả Customer             Trả empty
```

Bài học này hướng dẫn **xác định đúng lớp lỗi, đọc trạng thái hash/index, phân biệt các nguyên nhân, tái hiện có kiểm soát và phục hồi chỉ mục an toàn**. Mục tiêu cuối cùng là tránh tình huống âm thầm bỏ sót dữ liệu trong tra cứu nghiệp vụ.

> **Nguyên tắc:** `findById` và `findBy<Field>` có thể đi theo hai đường truy cập khác nhau. Dữ liệu gốc còn tồn tại **không tự chứng minh** secondary index đang đúng.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Spring Data Redis Repository xây và sử dụng secondary indexes như thế nào.
2. Phân biệt entity hash, index set và metadata phụ trợ của repository.
3. Phân biệt **missing index**, **stale index**, **dữ liệu thật sự không tồn tại** và **sai điều kiện query**.
4. Chẩn đoán trường hợp `findById` có dữ liệu nhưng `findByEmail`/`findByRegion` thiếu kết quả.
5. Nhận ra rủi ro khi cập nhật trực tiếp bằng `RedisTemplate`, `HSET`, `DEL`, Lua hoặc tiến trình ngoài Repository.
6. Phân tích tác động của TTL, expiration, Redis keyspace notifications, restart và downtime của listener.
7. Thiết kế bước kiểm tra và khôi phục chỉ mục không xóa nhầm dữ liệu.
8. Viết integration tests chứng minh index cập nhật khi save đúng đường Repository và có thể sai khi ghi ngoài đường đó.
9. Thiết kế monitoring và runbook nhằm phát hiện index drift sớm.

Các ví dụ dùng tên khách hàng, email và vùng giả định; trong hệ thống thật phải tránh ghi dữ liệu cá nhân vào log hoặc dashboard.

## 3. Spring Data Redis Repository khác một cơ sở dữ liệu quan hệ

Trong Spring Data JPA, một query có thể được database engine xử lý bằng index table hoặc scan theo query planner. Với Spring Data Redis Repository, Redis không cung cấp sẵn bộ máy SQL để tự hiểu `findByEmail`.

Spring Data Redis lưu entity dưới dạng Redis data structures và duy trì một số **secondary indexes** để hỗ trợ các query methods.

Ví dụ:

```java
@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;
}
```

Về mặt khái niệm, hệ thống có:

```text
Entity hash:
    customers:c-101
       id    = c-101
       email = an@example.test
       displayName = An

Index for email=an@example.test:
    <repository-managed index SET>
       member -> c-101 / key reference
```

Khi gọi `findByEmail("an@example.test")`, Repository tìm các identifiers thông qua index, rồi nạp entities tương ứng.

**Quan trọng:** Tên key index, cách encode value và cấu trúc metadata là chi tiết thuộc phiên bản mapping/converter của Spring Data Redis. Ví dụ minh họa các key dạng `customers:email:an@example.test`, nhưng **không tự coi format đó là hợp đồng ổn định trong mọi phiên bản**. Khi chẩn đoán phải kiểm tra keys thực tế do ứng dụng tạo.

## 4. Các dạng dữ liệu liên quan đến secondary index

Một Redis Repository có thể quản lý nhiều loại key:

| Nhóm dữ liệu | Vai trò | Có thể gặp |
| --- | --- | --- |
| Hash entity | Chứa các thuộc tính của object | `customers:c-101` |
| Secondary index set | Ánh xạ giá trị thuộc tính sang entity identifiers | Index theo email, region |
| Helper/reference index metadata | Giúp quản lý index membership khi entity thay đổi/xóa | Các keys phụ trợ do mapping layer tạo |
| TTL/expiration metadata | Quản lý vòng đời object | Expiring entity keys, shadow copies khi bật |
| Keyspace notification subscription | Nhận expired events để cleanup index khi cần | Redis Pub/Sub/keyevent |

Đừng xóa các keys lạ có prefix liên quan entity trước khi biết chúng là entity hashes, index sets hay metadata của Repository.

Nếu chỉ xóa hash mà vẫn giữ index, query có thể tìm thấy **membership trỏ tới entity đã mất**. Nếu chỉ xóa membership mà giữ hash, query theo field có thể **thiếu entity**.

## 5. Hai loại sai lệch chỉ mục cần phân biệt

### 5.1. Missing index entry — thiếu kết quả

```text
Hash:
  customers:c-101
  email = an@example.test

Index email=an@example.test:
  không chứa c-101
```

Hệ quả:

```java
findById("c-101")                 // Có entity
findByEmail("an@example.test")   // Không tìm thấy entity đó
```

Đây là kiểu lỗi đúng với đề bài: **truy vấn Repository thiếu kết quả do chỉ mục không đồng bộ**.

### 5.2. Stale index entry — chỉ mục trỏ tới trạng thái cũ

```text
Hash:
  customers:c-101
  email = binh@example.test

Index email=an@example.test:
  vẫn có membership của c-101

Index email=binh@example.test:
  chưa có membership của c-101
```

Tùy phiên bản và query execution path, truy vấn email cũ có thể còn xét đến ID đó hoặc phải bỏ qua entity không còn; truy vấn email mới vẫn có thể không tìm thấy.

Cả hai tình huống đều thể hiện: **index không còn phản ánh đúng giá trị trong hash**.

### 5.3. Dangling index entry — membership trỏ tới key đã biến mất

```text
Index region=north:
  chứa c-101

Hash customers:c-101:
  không tồn tại
```

Hệ quả thường là lookup có thể đi qua một ID không còn entity hoặc nhận thiếu kết quả. Loại drift này xuất hiện trong các tình huống expiration/DEL không được cleanup đầy đủ.

Không nên gọi chung cả ba trường hợp là “Redis mất dữ liệu”, vì chúng cần biện pháp xử lý khác nhau.

## 6. Chẩn đoán theo thứ tự: entity, index, query, topology

Sơ đồ quyết định:

```text
Repository findByEmail trả thiếu
                 |
                 v
      Đang kết nối đúng Redis?
                 |
          +------+------+
          |             |
         Không          Có
          |             |
   Sửa config       findById(id)
                        |
                  +-----+------+
                  |            |
                Empty        Có entity
                  |            |
          Kiểm tra key       Kiểm tra field
          đã hết TTL         được index
          /DB/prefix             |
                                 v
                     So sánh actual value
                        với query input
                                 |
                                 v
                        Kiểm tra index set
                          membership
                                 |
                    +------------+------------+
                    |                         |
                 Thiếu entry               Entry có
                    |                         |
          Điều tra write path         Kiểm tra read path,
          /migration/@Indexed         TTL, stale ID,
                                      serializer, query
```

Không bắt đầu bằng `FLUSHDB`, đổi Redis version hoặc “rebuild toàn bộ” trước khi xác định đang sai ở đâu.

## 7. Bước 1: xác nhận môi trường Redis thực sự được dùng

Kiểm tra thông tin kết nối từ deployment và cấu hình Spring Boot:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      database: 0
      timeout: 3s
```

Các khả năng cần loại trừ:

- App A ghi Redis development, app B đọc Redis staging.
- Một service trỏ port khác.
- `spring.data.redis.database` khác khi dùng Redis standalone.
- Prefix entity thay đổi sau deploy.
- Service đọc replica và gặp replication lag.
- Redis Sentinel master đã chuyển mà một client giữ địa chỉ cũ.
- Redis Cluster key được route sang shard khác.
- Test dùng một embedded/mock cache thay vì Redis thật.
- TLS/ACL khiến một số operations lỗi, nhưng exception bị catch và chuyển thành danh sách rỗng.

**Redis Cluster chỉ hỗ trợ database 0 theo mô hình cluster**; không dùng `SELECT 1` làm cách cách ly logical database ở Cluster.

Nếu bất kỳ exception nào bị bắt và chuyển thành `Collections.emptyList()`, phải sửa behavior này khi chẩn đoán: **query thất bại** và **query hợp lệ nhưng rỗng** là hai sự kiện khác nhau.

## 8. Bước 2: kiểm tra theo ID trước

Nếu đã biết entity ID, gọi:

```java
Optional<Customer> byId =
    repository.findById("c-101");
```

Kết quả cho biết Repository có nạp được entity theo ID hay không.

Các tình huống:

| findById | findByEmail | Diễn giải sơ bộ |
| --- | --- | --- |
| Có | Có | Đường tìm kiếm đang phù hợp cho dữ liệu đó |
| Có | Không | Kiểm tra field/index/query input |
| Không | Không | Dữ liệu không có, expired, sai prefix/DB hoặc mapping |
| Không | Query có membership cũ | Có thể dangling index |
| Có | Query trả entity không phù hợp | Có thể stale index hoặc query semantics |

`findById` không tự chứng minh email đã được index. Chỉ nó chỉ xác minh đường nạp entity.

Với truy vấn thiếu kết quả của nhiều entities, cần tập IDs kỳ vọng từ một **nguồn xác thực độc lập**. `findAll()` của cùng Redis Repository chưa chắc là ground truth cho mọi write thủ công ngoài repository, nên không mặc định nó đại diện toàn bộ keyspace.

## 9. Bước 3: quan sát Redis bằng CLI

Chạy trên một Redis **test** hoặc môi trường có quyền đọc được phép:

```bash
redis-cli -h redis.internal -p 6379 PING
redis-cli -h redis.internal -p 6379 TYPE customers:c-101
redis-cli -h redis.internal -p 6379 HGETALL customers:c-101
redis-cli -h redis.internal -p 6379 TTL customers:c-101
```

`TYPE` giúp xác nhận key thực là hash. `HGETALL` cho thấy các fields nếu serializer/mapping ghi dưới dạng đọc được.

**Lưu ý bảo mật:** Không in toàn bộ hash có email/số điện thoại/token thật ra logs hoặc ticket công khai. Chỉ xem field cần thiết và che dữ liệu.

Nếu serializer lưu nhị phân, output `HGETALL` có thể khó đọc. Đừng suy ra hash “rỗng” chỉ vì công cụ viewer không giải mã đúng; dùng Redis CLI ở cấp bytes hoặc converter tương ứng.

Kiểm tra keyspace bằng `SCAN`:

```bash
redis-cli -h redis.internal -p 6379 --scan --pattern 'customers:*'
```

`SCAN` không tạo snapshot transaction và có thể trả trùng/thiếu tùy keyspace thay đổi trong lúc duyệt; cần xử lý lặp và không giả định toàn bộ namespace đã ổn định khi đang có writes.

Tránh `KEYS customers:*` trên keyspace lớn trong production vì có thể chặn Redis server trong quá trình quét.

## 10. Bước 4: xác định key index thật

Sau khi `repository.save(customer)` trong môi trường cô lập, quan sát những keys mới:

```bash
redis-cli --scan --pattern 'customers:*'
```

Nếu nghi một key là index:

```redis
TYPE customers:email:an@example.test
SMEMBERS customers:email:an@example.test
SCARD customers:email:an@example.test
```

**Tên `customers:email:an@example.test` chỉ là ví dụ.** Tham chiếu tới key do ứng dụng thực tế tạo, không áp đặt hard-code theo bài viết.

Khi `TYPE` là `set`, xem các members. Cần phân biệt members là ID thuần, serialized IDs hay key references; đừng viết script repair trước khi xác nhận encoding.

Nếu có thể, tạo một record test với email giả trên Redis test và so sánh keyspace **trước/sau save** để thấy chính xác Spring Data Redis version đang tạo những keys nào.

## 11. Bước 5: kiểm tra email và normalization

Không phải query rỗng nào cũng do index drift.

Ví dụ:

```text
Hash email = "An@Example.Test"
Query = "an@example.test"
```

Redis index lookup có thể dựa trên giá trị được serialize/chỉ mục chính xác; đừng giả định case-insensitive matching như một database collation.

Các khác biệt khác:

- Dấu cách đầu/cuối.
- Unicode normalization.
- Email/phone normalization không đồng nhất giữa writer và reader.
- Trường indexed bị `null`.
- Enum được chuyển thành chuỗi khác sau nâng cấp.
- Thay đổi `@Indexed` từ field này sang field khác.
- Truy vấn dùng alias property không tương ứng mapping.
- Query kết hợp nhiều predicates mà không có indexes phù hợp.

Ví dụ normalization hợp đồng ứng dụng:

```java
public static String normalizeEmail(String email) {
    if (email == null) {
        throw new IllegalArgumentException(
            "Email is required"
        );
    }

    return email.trim().toLowerCase(
        java.util.Locale.ROOT
    );
}
```

Đây là chính sách minh họa. Email canonicalization có nhiều chi tiết (đặc biệt local part), nên phải định nghĩa theo use case; không tự ép lower-case mà không xét yêu cầu nghiệp vụ.

**Quan trọng:** Cả lúc `save` và lúc `findByEmail` phải áp dụng chính sách normalization nhất quán. Nếu chỉ sửa reader, chỉ mục cũ có thể vẫn không phù hợp.

## 12. Ví dụ project tối giản: Customer Repository

Để tái hiện có kiểm soát, tạo Spring Boot project với:

- Spring Data Redis.
- Spring Boot Test.
- Testcontainers JUnit Jupiter.
- Redis server/container cho integration tests.

Trong Maven, dependencies cốt lõi (quản lý version bằng BOM Spring Boot):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Chọn phiên bản Spring Boot, Spring Data Redis, Java và Testcontainers phù hợp với project đang dùng. Không nâng cấp toàn bộ dependency chỉ để “làm index tự hiện” trước khi xác định nguyên nhân.

## 13. Tạo entity có @Indexed

File `Customer.java`:

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    @Indexed
    private String region;

    private String displayName;

    protected Customer() {
    }

    public Customer(
            String id,
            String email,
            String region,
            String displayName) {
        this.id = id;
        this.email = email;
        this.region = region;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getRegion() {
        return region;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Các annotation:

| Annotation | Vai trò |
| --- | --- |
| `@RedisHash("customers")` | Chỉ định keyspace của Redis Repository |
| `@Id` | Định danh entity |
| `@Indexed` trên `email` | Đề xuất secondary index cho email |
| `@Indexed` trên `region` | Đề xuất secondary index cho vùng |
| Getter/setter | Phục vụ mapping và cập nhật trạng thái mẫu |

`@Indexed` là một yêu cầu về indexing ở tầng mapping. Nó **không tự quét lại mọi hash đã tồn tại trước khi annotation được thêm**.

## 14. Tạo Repository interface

File `CustomerRepository.java`:

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByRegion(String region);
}
```

Lưu ý:

- `findById` tra cứu trực tiếp ID.
- `findByEmail` và `findByRegion` phụ thuộc secondary index cho thuộc tính tương ứng.
- Derived query support của Spring Data Redis **không tương đương mọi phép SQL WHERE/JOIN**.
- Không viết `findByDisplayName` rồi mặc định nó hoạt động nếu field không được index/không được query mechanism hỗ trợ.

Nếu query không được framework hỗ trợ, có thể bị từ chối khi tạo Repository hoặc khi thực thi tùy cấu hình/version. Đừng biến exception thành kết quả rỗng.

## 15. Kích hoạt Redis Repositories

File `CustomerApplication.java`:

```java
package com.example.customer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@SpringBootApplication
@EnableRedisRepositories(
    basePackageClasses = CustomerRepository.class
)
public class CustomerApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            CustomerApplication.class,
            args
        );
    }
}
```

Với Spring Boot, Redis Repositories còn có thể được auto-configure theo dependency/setting; ví dụ khai báo rõ package nhằm tránh scan nhầm repositories khác.

Nếu ứng dụng đồng thời dùng Spring Data JPA, MongoDB hoặc nhiều modules Spring Data, nên phân định package/repository types để tránh ambiguity giữa các repository factories.

Cấu hình Redis connection dành cho Spring Boot gần đây:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

Trong môi trường Sentinel/Cluster, cần cấu hình topology phù hợp thay vì một địa chỉ standalone cố định.

## 16. Đường save chuẩn tạo index

Ví dụ chạy trong Spring-managed service:

```java
Customer customer = new Customer(
    "c-101",
    "an@example.test",
    "north",
    "An"
);

repository.save(customer);

Customer byId =
    repository.findById("c-101").orElseThrow();

Customer byEmail =
    repository.findByEmail("an@example.test")
        .orElseThrow();
```

Với data và metadata hợp lệ, Repository mapping layer duy trì hash và các secondary index cần thiết cho các trường được đánh dấu.

Luồng khái quát:

```text
repository.save(customer)
           |
           v
Redis mapping converter
           |
           +-- serialize entity -> hash by ID
           |
           +-- maintain email index membership
           |
           +-- maintain region index membership
           |
           +-- maintain internal reference metadata
```

Đừng tự thay thế bước `save` bằng `HSET` trực tiếp rồi mong những bước index sẽ tự chạy. Redis chỉ thực hiện `HSET` mà client yêu cầu; Redis server không biết annotation `@Indexed` trong Java.

## 17. Cách cố ý tạo index drift trong môi trường test

Chỉ làm trên Redis test riêng.

**Trạng thái ban đầu:**

```java
repository.save(new Customer(
    "c-101",
    "an@example.test",
    "north",
    "An"
));
```

Lúc này query email cũ có thể trả entity.

Giả sử một đoạn code khác ghi thẳng Redis hash:

```java
StringRedisTemplate template = ...;

template.opsForHash().put(
    "customers:c-101",
    "email",
    "binh@example.test"
);
```

Nó thay giá trị field ở hash nhưng không gọi Redis Repository index maintenance.

Trạng thái có thể thành:

```text
Entity hash:
    customers:c-101
       email = binh@example.test

Index for an@example.test:
    vẫn có c-101

Index for binh@example.test:
    không có c-101
```

Khi đó:

```java
repository.findById("c-101");               // Có entity
repository.findByEmail("binh@example.test"); // Có thể empty
```

**Điểm quan trọng:** Nếu serializer field/value hoặc mapping khác ví dụ, một lệnh raw `HSET` cũng có thể tạo payload mà converter không hiểu. Khi tái hiện, kiểm tra cách entity hash thực tế được lưu trong Redis version của project, không áp đặt raw field encoding nếu nó khác.

Thử nghiệm cũng minh họa tại sao sửa hash bằng Redis CLI trong production có thể phá vỡ chỉ mục.

## 18. Một integration test bắt lỗi viết ngoài Repository

Dùng Spring Boot, Testcontainers và Redis thật. Ví dụ:

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class CustomerIndexIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.4.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            REDIS::getHost
        );

        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    CustomerRepository repository;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void repositorySaveCreatesSecondaryIndex() {
        String id = "c-test-101";

        repository.save(new Customer(
            id,
            "an@example.test",
            "north",
            "An"
        ));

        assertThat(repository.findById(id)).isPresent();

        assertThat(
            repository.findByEmail("an@example.test")
        ).isPresent();

        assertThat(
            repository.findByRegion("north")
        ).extracting(Customer::getId)
         .contains(id);
    }

    @Test
    void rawHashUpdateDoesNotMaintainEmailIndex() {
        String id = "c-test-102";

        repository.save(new Customer(
            id,
            "old@example.test",
            "north",
            "An"
        ));

        // Can thiệp chỉ trong Redis test.
        // Giả định field được lưu dưới dạng String.
        redis.opsForHash().put(
            "customers:" + id,
            "email",
            "new@example.test"
        );

        assertThat(
            repository.findById(id)
        ).isPresent();

        // Không có lời gọi save của repository để thêm
        // membership cho email mới.
        assertThat(
            repository.findByEmail("new@example.test")
        ).isEmpty();
    }
}
```

### Giới hạn của ví dụ

- Test dựa trên mapping mặc định của field `email` thành một string-compatible hash field. Với custom converters/serializers, phải điều chỉnh raw write tương ứng.
- Trong suite lớn, nên dùng IDs duy nhất hoặc cleanup namespace test chính xác.
- Test này **minh họa một nguyên nhân**, không khẳng định mọi tình huống `findByEmail` empty đều là missing index.
- Không được chạy biến thể phá hoại chỉ mục này trên Redis production.

Khi code thực sự tạo index drift, đừng “chữa” bằng cách bổ sung `SCAN` toàn keyspace vào mỗi request; phải sửa write path.

## 19. Cập nhật thông qua Repository thay vì Redis hash API

Một cách cập nhật:

```java
public Customer changeEmail(
        String id,
        String newEmail) {

    Customer customer =
        repository.findById(id).orElseThrow();

    customer.setEmail(newEmail);

    return repository.save(customer);
}
```

Mục tiêu là để Repository có cơ hội cập nhật index metadata cùng với entity.

Nếu ứng dụng dùng nhiều service cùng ghi một entity hoặc vừa Repository vừa raw Redis API, cần thống nhất **một write ownership strategy**.

Không phải mọi `save` đều có nghĩa:

- Có transaction phân tán nguyên tử với database khác.
- Không tồn tại race khi hai writers cập nhật cùng ID.
- Index luôn nhất quán trong mọi cửa sổ ngắn giữa nhiều Redis commands.
- Không thể mất thay đổi do failover.

Ở cấp nghiệp vụ cần xác định concurrency/versioning/locking policy nếu nhiều writers có thể đua nhau.

## 20. Lưu ý về PartialUpdate và những write paths khác

Spring Data Redis có cơ chế cập nhật một phần entity trong một số API/phiên bản, ví dụ `PartialUpdate` kết hợp RedisKeyValueTemplate. Khi dùng API chính thức được hỗ trợ, mapping layer có thể quản lý các tác động lên indexes/TTL theo khả năng implementation.

Nhưng điều đó **không đồng nghĩa** mọi thao tác partial ở bất kỳ lớp nào cũng biết update index.

Phân biệt:

| Đường ghi | Index maintenance |
| --- | --- |
| `repository.save(entity)` | Mapping layer quản lý theo metadata |
| Repository delete methods | Có cơ chế cleanup theo repository path |
| API `PartialUpdate` được hỗ trợ | Cần kiểm tra behavior theo phiên bản và thao tác |
| `StringRedisTemplate.opsForHash().put` | Không tự áp dụng annotation `@Indexed` |
| `redis-cli HSET` | Không biết Java mapping metadata |
| Lua viết trực tiếp hash | Không tự quản lý Repository index |
| Một ứng dụng bên ngoài viết Redis | Không có bảo đảm Repository index maintenance |
| `DEL customers:c-101` từ CLI | Không tự cleanup các metadata do repository quản lý |

Nếu code hiện tại dùng raw `HSET`, hãy xem nó là một ứng viên gây drift trước khi nghi Redis driver hoặc Spring query bị lỗi.

## 21. Thêm @Indexed sau khi dữ liệu đã tồn tại

Tình huống deployment:

```text
Version 1:
    Customer.email không có @Indexed
    repository.save() tạo hàng triệu customer hashes

Version 2:
    Thêm @Indexed cho email
    deploy ứng dụng mới
```

**Việc thêm annotation không tự quét toàn bộ Redis keys cũ để backfill index cho tất cả entities.**

Khi đó:

- Customers được tạo sau deploy có thể tìm được theo email.
- Customers cũ chưa được re-save/backfill có thể không có membership.
- Query `findById` vẫn chạy.
- Mẫu lỗi thường là **chỉ một phần dữ liệu cũ bị bỏ sót**.

### Hướng xử lý

1. Lập kế hoạch backfill index có kiểm soát.
2. Xác định tập IDs từ nguồn đáng tin cậy.
3. Đọc entities và ghi lại qua đường Repository khi an toàn.
4. Không làm mất TTL hoặc ghi đè dữ liệu đang được cập nhật đồng thời.
5. Đặt checkpoint và metrics cho tiến độ.
6. Kiểm tra samples trước, trong và sau backfill.
7. Thực hiện với rate limit để Redis không bị quá tải.

Không tạo một script Redis CLI `SADD` đại trà theo format đoán mò nếu chưa xác nhận index metadata và các helper sets mà Repository quản lý.

## 22. Thay đổi tên field hoặc mapping path

Ví dụ:

```text
Version 1: customer.email
Version 2: customer.primaryEmail
```

Nếu `@Indexed` được chuyển sang field mới nhưng dữ liệu cũ vẫn lưu `email`, query theo `primaryEmail` không thể tự tìm đủ entities.

Các khả năng:

- Hash cũ thiếu field mới.
- Converter alias/mapping không đúng.
- Index cũ còn nhưng index mới chưa được tạo.
- Một phần pods chạy v1, phần khác v2.
- Serializer hoặc custom conversions thay đổi.
- API normalization khác nhau giữa deployments.

Đây là một vấn đề **schema migration**, không phải chỉ Redis memory issue.

Cần quy trình versioned rollout:

1. Xác định payload schema và index schema.
2. Đảm bảo reader mới đọc được dữ liệu cũ hoặc chuyển namespace.
3. Backfill dữ liệu/index nếu cần.
4. Chuyển query traffic khi độ phủ index đạt yêu cầu.
5. Thu hồi đường cũ sau khi không còn producers sử dụng.
6. Có kế hoạch rollback nếu index drift tăng.

## 23. Redis Repository không tự hiểu mọi loại query

Một số hiểu nhầm:

```java
List<Customer> findByDisplayNameContaining(String text);
List<Customer> findByEmailIgnoreCase(String email);
List<Customer> findByRegionOrderByDisplayNameAsc(String region);
```

Không được mặc định mọi derived query giống Spring Data JPA đều có hiệu lực tương đương trong Redis Repository.

Spring Data Redis hỗ trợ những query patterns nhất định dựa trên indexed fields, và khả năng tùy phiên bản. Những truy vấn partial text, sort phức tạp, joins hoặc relational-style filters có thể không phù hợp.

Khi một query không trả kết quả kỳ vọng, trước hết phải kiểm tra:

- Query method có được Spring Data Redis hỗ trợ không?
- Field có `@Indexed` hoặc index configuration tương ứng không?
- Có điều kiện query nào không tương ứng index không?
- Chữ hoa/thường và serialization có nhất quán không?
- Có cần Redis Search/RediSearch hoặc một data store khác cho full-text/range queries không?

Không tạo index giả bằng tay để ép một query unsupported chạy như SQL.

## 24. TTL: entity có thể hết hạn nhưng index chưa được cleanup

Một entity có TTL:

```java
@RedisHash(value = "customers", timeToLive = 600)
public class Customer {
    // @Id, @Indexed ...
}
```

Giá trị `timeToLive` trong annotation này được biểu diễn theo đơn vị Redis mapping hỗ trợ, thường là seconds trong cấu hình như ví dụ.

Khi hết TTL:

```text
Entity hash customers:c-101 -> expired
Secondary index SET        -> có thể cần cleanup membership
```

Spring Data Redis có cơ chế lắng nghe Redis keyspace expiration events để quản lý một số hành vi cleanup/index metadata.

**Điểm quan trọng:** Redis keyspace notifications dùng Pub/Sub; nếu listener không hoạt động, events có thể bị bỏ lỡ. Đừng coi event delivery là durable queue.

### Các ảnh hưởng có thể gặp

- Hash đã mất nhưng index còn membership → dangling entry.
- Listener bị tắt hoặc không có quyền thiết lập notifications.
- Application downtime trùng thời điểm expiration.
- Managed Redis cấm `CONFIG SET`.
- Key bị eviction/xóa raw thay vì expiration theo đường dự kiến.
- Replica/failover làm thời điểm event khác kỳ vọng.

Tùy mapping và query execution, dangling entries có thể tạo chi phí lookup hoặc kết quả bất thường; **thiếu kết quả với hash vẫn còn** cần tìm thêm nguyên nhân khác như missing membership hoặc normalization.

## 25. Keyspace notifications: cấu hình và quan sát

Redis cung cấp:

```bash
redis-cli -h redis.internal -p 6379 CONFIG GET notify-keyspace-events
```

Khi cần event expiration kiểu keyevent, một cấu hình thường gặp:

```conf
notify-keyspace-events Ex
```

Trong đó:

- `E`: keyevent notification channels.
- `x`: expired events.

Các flags thực tế có thể được kết hợp với những flags khác; đừng ghi đè cấu hình production chưa hiểu ý nghĩa.

Trong môi trường test có quyền quản trị:

```bash
redis-cli -h redis-test.internal -p 6379 CONFIG SET notify-keyspace-events Ex
```

Đây là **thay đổi runtime trên Redis server**, không phải annotation Spring đơn thuần.

### Khi nào Spring tạo listener?

Spring Data Redis cung cấp cấu hình `@EnableRedisRepositories` và tùy chọn quản lý keyspace events theo phiên bản, ví dụ `ON_STARTUP`, `ON_DEMAND` hoặc `OFF` trong `RedisKeyValueAdapter.EnableKeyspaceEvents`.

Một minh họa:

```java
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@EnableRedisRepositories(
    basePackageClasses = CustomerRepository.class,
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
class RedisRepositoryConfiguration {
}
```

Nếu đã bật repositories ở `CustomerApplication`, không thêm một lớp configuration trùng lặp như đoạn này mà không điều chỉnh cấu hình cũ. Đây là **một lựa chọn thay thế**, không phải bước cần copy nguyên vào cùng project.

Tùy version và option, Spring có thể tìm cách thiết lập notification flags qua Redis `CONFIG`; managed services có thể không cho phép. Cần đọc logs startup và cấu hình hạ tầng phù hợp.

## 26. Tại sao listener downtime tạo index drift?

Timeline:

```text
T0 Customer c-101 có TTL 60 giây
T1 Spring app restart, listener không online
T2 Redis key customers:c-101 hết hạn
T3 Redis phát expired event
T4 Không có subscriber nhận event
T5 Spring app online lại
T6 Secondary index metadata có thể vẫn trỏ c-101
```

Redis Pub/Sub **không replay** event ở T3 cho subscriber kết nối ở T5.

Cần phân biệt:

- **Missing index:** hash còn nhưng membership thiếu.
- **Dangling index:** hash mất nhưng membership còn sau expiration.
- **Operational consequence:** cả hai có thể làm query không phản ánh trạng thái mong đợi; lý do và hướng sửa khác nhau.

Với hệ thống đòi chỉ mục chính xác, cần cơ chế reconciliation/backfill định kỳ, không chỉ tin vào notifications.

## 27. Shadow copy và expired key events

Một số phiên bản Spring Data Redis Repository có cơ chế giữ **phantom/shadow copy** của entity trong một thời gian sau TTL để phát `RedisKeyExpiredEvent` kèm dữ liệu đối tượng.

Điểm cần biết:

- Shadow copy có thể tăng memory usage.
- Nội dung shadow copy có thể chứa dữ liệu cần được bảo vệ.
- Có cấu hình liên quan việc tạo shadow copy theo phiên bản.
- Nếu tắt shadow copy, event payload có thể không còn đủ entity data dù ID vẫn có thể được biết.
- Listener downtime vẫn không biến Pub/Sub thành event queue bền vững.

Không “chữa” index drift bằng cách bật shadow copy vô hạn hoặc tăng TTL mà chưa xác định nguyên nhân. Phải đánh giá memory/retention và yêu cầu privacy.

## 28. Key eviction và expiration không giống nhau

Một Redis instance có:

```conf
maxmemory 512mb
maxmemory-policy allkeys-lru
```

có thể evict entity key **trước khi TTL hết**. Eviction không đồng nhất với expiration, và không nên mặc định mọi expired-key cleanup listener sẽ tự xử lý các key bị eviction hoặc bị `DEL` thủ công.

Các đường key biến mất:

| Nguyên nhân | Điều cần xem |
| --- | --- |
| TTL expiration | Keyspace expired events, listener state |
| Memory eviction | `evicted_keys`, maxmemory policy |
| Repository delete | Repository index cleanup path |
| Raw `DEL` | Không chạy Java repository index maintenance |
| Admin cleanup/flush | Có thể mất metadata theo cách không mong muốn |
| Failover/replication lag | Khác trạng thái giữa primaries/replicas |
| Schema/prefix change | Reader đang nhìn keyspace khác |

Nếu hệ thống dùng Redis Repository như kho lưu trạng thái quan trọng, không nên đặt nó chung Redis eviction pool với cache có thể tái tạo nếu eviction sớm làm mất data semantics.

## 29. Dữ liệu ở replica có thể chậm so với index ở primary

Redis replication thường bất đồng bộ.

Nếu ứng dụng đọc qua replicas:

```text
Primary: entity hash đã ghi
Replica: chưa áp dụng toàn bộ thay đổi
```

Trong khoảng replication lag, query có thể không thấy index membership hoặc hash mới.

Cần xem:

- `INFO replication`.
- Read routing của Lettuce/Jedis.
- Primary vs replica endpoints.
- Tình trạng failover và promotion.
- Những write/read có cần read-your-writes không.

Tuy nhiên trong một Redis stream, các commands được replication theo thứ tự; không nên tự khẳng định replica đã nhận hash mà chắc chắn chưa nhận index trong mọi tình huống. Phải quan sát thực tế và thời điểm.

Nếu yêu cầu đọc lại ngay sau write, cân nhắc đọc primary hoặc nguồn có consistency phù hợp.

## 30. Race giữa nhiều writers

Hai services cùng chỉnh một customer:

```text
Writer A đọc email cũ
Writer B đọc email cũ

Writer A đổi email -> a1@example.test
Writer B đổi region -> south bằng object cũ

Writer A repository.save(...)
Writer B repository.save(...)
```

Nếu B ghi lại toàn bộ entity cũ, nó có thể ghi đè thay đổi email của A, khiến hiện trạng và index membership khác điều người dùng kỳ vọng.

Đây là vấn đề **concurrent update/lost update**; không phải mọi thiếu kết quả đều do bug index maintenance.

Các hướng thiết kế:

- Có một owner service cho write operations.
- Dùng optimistic locking/versioning khi được mapping hỗ trợ.
- Tránh read-modify-write trên bản snapshot cũ.
- Xác định field-level update semantics.
- Dùng Redis operations nguyên tử khi phù hợp.
- Thử concurrency trên Redis thật, không chỉ Mockito.
- Đo và đối soát trạng thái hash lẫn indexes sau các races.

Không dựng manual secondary index schema như một cách giải quyết lost updates.

## 31. Tiếp cận phục hồi: đừng xóa toàn bộ index trước

Khi phát hiện index drift, các thao tác **không nên thực hiện ngay**:

```bash
redis-cli FLUSHDB
redis-cli FLUSHALL
redis-cli KEYS '*'
```

`FLUSHDB`/`FLUSHALL` xóa dữ liệu; `KEYS` có thể gây chi phí lớn trên production.

Cũng không nên:

- Xóa bừa mọi key bắt đầu bằng `customers:`.
- Chạy `SADD`/`SREM` theo một pattern chưa xác nhận.
- Ghi đè hàng triệu hashes bằng phiên bản cũ từ script.
- Reset TTL của các keys có deadline nghiệp vụ mà không xét tác động.
- Rebuild trong lúc có hàng nghìn concurrent writers mà không có kế hoạch nhất quán.
- Bỏ qua backup/snapshot trước thao tác lớn.

**Ưu tiên sửa write path và lập kế hoạch backfill có checkpoints**, thay vì xử lý triệu chứng bằng lệnh Redis thủ công.

## 32. Kế hoạch chẩn đoán trước khi repair

Thu thập một tập records mẫu:

| ID | `findById` | Actual field | `findByField` | Index membership |
| --- | --- | --- | --- | --- |
| c-101 | Có | an@example.test | Thiếu | Thiếu |
| c-102 | Có | binh@example.test | Có | Có |
| c-103 | Không | — | Có entry tham chiếu | Stale |
| c-104 | Có | south | Thiếu | Sai normalization |

Số liệu minh họa; membership thực phải được xác nhận.

Nhóm phân loại:

- A: entity hash có dữ liệu, index thiếu.
- B: index có nhưng entity đã mất.
- C: giá trị hash và index khác nhau.
- D: query sai/case mismatch.
- E: serializer/prefix/topology thay đổi.
- F: query method không được hỗ trợ.

Việc chia nhóm giúp tránh một “repair” duy nhất làm hỏng thêm các nhóm còn lại.

## 33. Repair cho một entity: dùng đường Repository có kiểm soát

Trong môi trường test hoặc maintenance được cho phép:

```java
Customer customer =
    repository.findById("c-101").orElseThrow();

repository.save(customer);
```

Với mapping layer đang hoạt động và metadata đầy đủ, việc save có thể tái tạo/cập nhật secondary indexes cho entity đó.

**Nhưng không mặc định lời gọi này an toàn trong mọi trường hợp:**

- Nó có thể làm thay đổi TTL còn lại hoặc trigger các callbacks/event handlers.
- Entity hash có thể chứa schema cũ không đọc được.
- Concurrent writer có thể bị ghi đè nếu script giữ snapshot cũ.
- Repository index helper metadata có thể đã mất hoặc bị sai.
- Một index cũ stale có thể cần cleanup bổ sung theo behavior phiên bản.
- Mapping của version hiện tại có thể tạo lại những index khác version cũ.

Sau thao tác, phải kiểm tra `findById`, `findByField`, actual Redis index membership và TTL.

Một repair thành công cho một entity **không chứng minh hàng triệu entity khác đã được sửa**.

## 34. Vì sao phải bảo toàn TTL?

Giả sử:

```text
customers:c-101
TTL trước repair = 120 giây
```

Nếu script read → `repository.save(customer)` vô điều kiện mà mapping lại đặt TTL 600 giây, retention của customer có thể bị kéo dài thêm 8 phút.

Với session/OTP/temporary records, đó có thể là lỗi nghiệp vụ.

Trước repair:

```redis
PTTL customers:c-101
```

Xác định:

- TTL của entity do `@RedisHash(timeToLive=...)` hay `@TimeToLive` quản lý?
- `@TimeToLive` có giữ được remaining expiration đúng không?
- Save lại có reset deadline không?
- Key không có TTL có phải intentional không?
- Key có thể expire giữa lúc đọc và ghi không?

Nếu không có cách bảo toàn expiration được kiểm chứng, **không chạy backfill production tự động** chỉ dựa trên ví dụ read-save.

Có thể cần một migration tool chuyên biệt dựng index membership theo cách an toàn với schema hiện tại và concurrent writers.

## 35. Backfill nhiều entities: kế hoạch an toàn

Khi thêm `@Indexed` cho dữ liệu cũ, cần một job có kiểm soát:

```text
Identify source-of-truth IDs
           |
           v
Read entity by ID
           |
           v
Verify schema + required indexed field
           |
           v
Maintain index via repository-aware path
           |
           v
Verify query/index membership
           |
           v
Checkpoint success/failure
           |
           v
Repeat with rate limit
```

Các yêu cầu:

1. **Nguồn IDs đáng tin cậy:** database/source of truth hoặc scan có kiểm soát; không chỉ query index đang bị lỗi.
2. **Idempotent job:** chạy lại không tạo entries trùng/logic sai.
3. **Rate limit:** không gây latency spike trên Redis.
4. **Checkpoint:** resume sau restart.
5. **TTL policy:** không gia hạn dữ liệu sắp hết hạn một cách vô ý.
6. **Concurrency policy:** tránh ghi đè update mới.
7. **Observability:** số records scanned, repaired, skipped, failed.
8. **Verification:** sample và thống kê coverage trước/sau.
9. **Rollback plan:** backup và kế hoạch khôi phục.
10. **Multi-version rollout:** không để writer v1 tiếp tục phá index mới.

Không chạy một vòng lặp `KEYS *` + `save` không giới hạn chỉ vì bài test trên 10 records thành công.

## 36. Khi nào cần rebuild toàn bộ index?

Rebuild diện rộng có thể cần khi:

- Annotation mới được thêm sau khi nhiều hashes tồn tại.
- Một external writer đã chỉnh raw hashes trong thời gian dài.
- Một deployment cũ và mới dùng index schema khác nhau.
- Index helper metadata bị mất.
- Index drift lan rộng theo nhiều tenants hoặc shards.
- Redis instance được restore từ snapshot ở một trạng thái không đồng bộ với writer/mapping.

Nhưng “rebuild” phải được định nghĩa rõ:

- Từ nguồn dữ liệu chuẩn nào?
- Index key naming và serialization của phiên bản nào?
- Có xóa index cũ không, xóa như thế nào?
- Có downtime hay dual-read/dual-write không?
- Làm sao tránh query chạy giữa rebuild trả thiếu?
- Có đủ memory cho hai bộ index tạm trong migration không?
- Có khả năng rollback không?

Đừng tự đặt TTL cho index SETs theo TTL của từng entity nếu metadata cần chứa nhiều IDs với expirations khác nhau; lifecycle index phải tuân theo cơ chế của Repository/version tương ứng.

## 37. Một chiến lược migration có phiên bản

Nếu có thể xây hệ thống mới, ưu tiên:

```text
Repository schema v1:
    customers:v1:* + index v1

Repository schema v2:
    customers:v2:* + index v2
```

Quy trình khái quát:

1. Triển khai reader hỗ trợ migration.
2. Ghi/sync vào namespace mới có kiểm soát.
3. Backfill toàn bộ dữ liệu đủ điều kiện.
4. Xác nhận counts, samples, index memberships.
5. Chuyển traffic query sang v2.
6. Theo dõi mismatch/latency.
7. Ngừng writer v1.
8. Chỉ cleanup v1 sau thời gian rollback an toàn.

Đây là pattern thiết kế, không tự kích hoạt khi thay `@RedisHash` value.

Tách namespaces có thể tốn RAM gấp đôi trong migration; cần capacity planning, đặc biệt khi Redis bật `maxmemory`/eviction.

## 38. Một hướng khác: xây query từ nguồn dữ liệu có thẩm quyền

Nếu entity có dữ liệu rất quan trọng, Redis Repository có thể chỉ nên là cache/index đọc, còn database giữ tính đúng.

Ví dụ:

```text
GET customer by email
      |
      v
Redis Repository index
      |
      +-- HIT -> Validate business constraints
      |
      +-- MISS / suspected drift
               |
               v
         Authoritative DB query
               |
               v
          Repair or refresh cache
```

**Không được tự động coi mọi miss là index drift**: có thể không có khách hàng thật.

Nếu dùng fallback:

- Phải có nguồn chuẩn query chính xác.
- Giới hạn tần suất fallback, tránh DB overload.
- Không tạo tài khoản/đơn hàng trùng chỉ vì Redis query miss.
- Có metric mismatch giữa Redis và nguồn chuẩn.
- Repair phải tránh đè lên update mới.
- Không bỏ qua authorization/tenant filtering khi lấy dữ liệu từ DB.

Cách này giảm ảnh hưởng của index drift nhưng không thay thế việc sửa write path.

## 39. Dùng Redis Search khi truy vấn vượt khả năng Repository indexes

Nếu yêu cầu truy vấn là:

```text
Email prefix
Full-text name search
Numeric range
Sorting
Compound filters
Vector search
```

thì basic Spring Data Redis Repository secondary indexes có thể không phù hợp.

Có thể cần:

- Redis Search/Query Engine với schema/indexing riêng, nếu deployment hỗ trợ.
- Relational database query/index.
- Elasticsearch/OpenSearch hoặc search engine phù hợp.
- Denormalized keys và custom indexes do service quản lý nếu complexity nhỏ và có maintenance contract rõ.

**Không trộn lẫn hai cơ chế:** `@Indexed` của Redis Repository không đồng nghĩa với Redis Search index schema. Tìm thấy index bằng một sản phẩm Redis Search không chứng minh Repository derived query đang dùng index đó.

## 40. Redis Cluster: chẩn đoán index theo topology

Redis Cluster chia dữ liệu theo 16.384 hash slots.

Một entity hash và secondary index SET có thể là những Redis keys khác nhau. Khi thao tác có nhiều keys/transactions/scripts, Cluster có ràng buộc đồng slot và khả năng hỗ trợ repository operations phụ thuộc phiên bản/cách mapping.

Khi production là Cluster:

- Xác định Redis Cluster support/giới hạn của Repository version đang dùng.
- Không giả định mọi operation multi-key của Repository chạy atomically trên toàn Cluster.
- Truy vấn từng shard/node khi cần, không dùng một seed node như thể toàn keyspace nằm ở đó.
- `SCAN` trên một node không đại diện toàn Cluster.
- Lưu topology và node ID lúc lỗi xảy ra.
- Phân biệt `MOVED`/`ASK`/`CROSSSLOT` errors với query legitimately empty.
- Không diễn giải lỗi Cluster thành `Optional.empty()`.

Nếu Redis Repository index model cần các operations không tương thích Cluster topology, phải thiết kế lại data placement/query architecture; không sửa bằng cách lạm dụng một hash tag toàn cục và dồn toàn bộ dataset vào một slot.

## 41. Redis replica reads và consistency

Trong một topology primary–replica:

```text
Primary A writes:
   hash update
   index SET membership

Replica B reads:
   replication chưa bắt kịp
```

Một query đọc từ replica có thể thấy trạng thái cũ trong cửa sổ replication bất đồng bộ.

Cần kiểm tra:

- Lettuce `ReadFrom` policy.
- Client đang đọc primary hay replica.
- `INFO replication` offsets/link.
- Failover đã xảy ra chưa.
- Read-after-write consistency requirement.
- Lỗi timeout có bị catch và chuyển thành empty không.

Nếu vừa ghi xong cần đọc thấy ngay, ưu tiên query primary hoặc nguồn có consistency phù hợp, không coi replica read giống transaction commit.

## 42. Metrics phát hiện index drift

Một dashboard hữu ích:

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `redis_repository_find_by_id_hit` | ID lookup có entity |
| `redis_repository_index_query_miss` | Secondary-index query không ra kết quả |
| `redis_repository_index_mismatch` | Probe so sánh entity/hash và index bị lệch |
| `redis_repository_repair_success` | Số entities được sửa thành công |
| `redis_repository_repair_failure` | Số entities không sửa được |
| `redis_repository_repair_backlog` | Số entities chờ repair |
| `redis_keyspace_expiry_event_gap` | Tín hiệu monitoring về event/cleanup không ổn |
| `redis_connection_errors` | Lỗi client/connection |
| `redis_replication_lag` | Thông tin replication theo định nghĩa metric |
| `redis_key_evictions` | Số keys bị memory eviction |

Tên metric là **đề xuất**, không mặc định được Spring Boot/Micrometer sinh tự động.

Một tỷ lệ hữu ích:

```text
index_coverage_ratio =
    number_of_authoritative_sample_records_found_by_index
    /
    number_of_authoritative_sample_records_tested
```

Cần xác định nguồn sample chính xác, bảo vệ dữ liệu cá nhân và thống kê theo namespace/version.

Nếu chỉ đếm “query email trả empty” mà không biết expected entities, không thể kết luận mọi empty đều là index drift.

## 43. Thiết kế sample reconciliation

Không quét hàng triệu records trên mỗi request. Có thể chạy job kiểm tra định kỳ:

1. Lấy một mẫu IDs từ nguồn chuẩn.
2. Đọc mỗi record theo ID.
3. Lấy giá trị field được `@Indexed`.
4. Query theo field đó.
5. Kiểm tra entity ID có nằm trong kết quả.
6. Ghi metric mismatch với **hash identifier đã ẩn danh**, không log email plaintext.
7. Phân loại missing/stale/dangling.
8. Chỉ repair theo policy đã được phê duyệt.

Ví dụ pseudo-code:

```java
for (String id : sampledIds) {
    Optional<Customer> byId =
        repository.findById(id);

    if (byId.isEmpty()) {
        continue;
    }

    Customer customer = byId.get();

    boolean found = repository
        .findByEmail(customer.getEmail())
        .map(Customer::getId)
        .filter(id::equals)
        .isPresent();

    if (!found) {
        metrics.increment("index_mismatch");
    }
}
```

Hạn chế: đoạn này không phân biệt lỗi network với empty nếu exception bị che ở tầng nào đó; không kiểm tra stale entries của email cũ; và chỉ phủ mẫu IDs đã chọn. Dùng để phát hiện drift, không tuyên bố chỉ mục toàn bộ chính xác tuyệt đối.

## 44. Phân loại root cause bằng audit trail

Nếu có log đổi email:

```text
T0 Repository saved c-101: email=an@example.test
T1 External job executed HSET email=binh@example.test
T2 Query findByEmail(binh@example.test) returned empty
```

Timeline này chỉ ra external writer là ứng viên mạnh.

Nếu:

```text
T0 Deploy v2 adds @Indexed
T1 New customers query correctly
T2 Old customers not found by email
```

thiếu backfill là ứng viên mạnh.

Nếu:

```text
T0 Customer TTL expires
T1 App listener offline
T2 Redis index set still contains old ID
```

đây là dạng dangling membership do cleanup missed.

Cần điều tra dựa trên logs/deployment history/Redis snapshots chứ không chỉ đoán vì “Spring Redis index bug”.

## 45. Tại sao không dùng SCAN + HGETALL trên mỗi API query?

Một workaround nguy hiểm:

```text
findByEmail failed
    |
    v
SCAN toàn Redis
    |
    v
HGETALL từng customer
    |
    v
so sánh email thủ công
```

Nhược điểm:

- O(N) hoặc tệ hơn theo số lượng keys/hashes.
- Tăng network round trips.
- Có thể gây latency spike và quá tải Redis.
- Không có snapshot nhất quán khi keyspace đang thay đổi.
- Dễ quét nhầm nhiều tenants.
- Không scale với millions of entities.

Có thể dùng scan **offline/maintenance với rate limit** để inventory/backfill; không biến nó thành query engine ở đường nóng của API.

Nếu cần query theo field lớn và linh hoạt, phải chọn index/query architecture phù hợp.

## 46. Không sửa index bằng SADD đơn lẻ nếu chưa hiểu metadata

Thấy thiếu membership, một người có thể thử:

```redis
SADD customers:email:binh@example.test c-101
```

Về mặt demo, lệnh có thể tạo member trong một SET. Nhưng Spring Data Redis Repository có thể còn **helper/reference index metadata**, mapping conventions và serializer cần đồng bộ.

Các rủi ro:

- Member cần lưu ID theo một encoding khác.
- Đã có stale membership trong index cũ.
- Repository lần save/delete sau không biết phải cleanup thủ công.
- Keys sử dụng namespace/tenant/version khác.
- TTL của entity không còn.
- Một concurrent writer vừa đổi email lần nữa.

Chỉ dùng manual `SADD`/`SREM` trong một **công cụ repair đã kiểm chứng implementation/version** và có test/backup rõ, không phải thao tác phản xạ khi thấy query thiếu.

## 47. Duplicate values và nhiều IDs trong cùng index

Ví dụ index `region=north`:

```text
Index region=north:
    c-101
    c-102
    c-103
```

`findByRegion("north")` thường có thể trả nhiều entities. Việc index là Redis SET nghĩa là:

- Không có duplicates của **cùng member** trong một SET.
- Một giá trị region có thể ứng với nhiều IDs.
- Thứ tự SET members không bảo đảm sorting nghiệp vụ.
- Nếu một hash mất, index còn membership có thể gây dangling entry.
- Nếu một hash mới không có membership, danh sách trả thiếu.

Đừng dựa vào thứ tự Redis SET làm thứ tự API. Nếu cần stable sorting/pagination, phải thiết kế strategy rõ và hiểu khả năng hỗ trợ của Repository.

## 48. Tại sao findById không đủ để khẳng định Repository khỏe?

Các thao tác:

```java
repository.save(customer);
repository.findById(customer.getId());
```

có thể thành công dù `@Indexed` bị thiếu hoặc query index không đúng.

Vì vậy smoke test cho Redis Repository có indexed queries nên bao gồm:

```text
save entity
findById exact ID
findByEmail exact value
update indexed field through repository
findByEmail new value
check old value no longer resolves incorrectly
delete entity
findById empty
findByEmail does not expose dangling stale entity
```

Đối với TTL-enabled entities, thêm:

```text
wait for expiration (bounded polling)
findById empty
monitor index cleanup behavior
```

Các test đó cần Redis thật; Mockito giả index membership không kiểm chứng Spring Data Redis mapping.

## 49. Test update indexed field qua Repository

Một integration test minh họa:

```java
@Test
void savingChangedEmailUpdatesIndex() {
    Customer customer = new Customer(
        "c-test-201",
        "first@example.test",
        "north",
        "An"
    );

    repository.save(customer);

    assertThat(
        repository.findByEmail("first@example.test")
    ).isPresent();

    customer.setEmail("second@example.test");

    repository.save(customer);

    assertThat(
        repository.findByEmail("second@example.test")
    ).isPresent();

    assertThat(
        repository.findByEmail("first@example.test")
    ).isEmpty();
}
```

Test này nên được chạy trên project và Spring Data Redis version thực tế để xác nhận contract của mapping/index maintenance khi đổi field.

Nếu test thất bại, có thể điều tra index helper metadata, mapping, serializer, write path, TTL và concurrent operations; không kết luận ngay rằng `@Indexed` vô dụng.

Trong môi trường chạy nhiều test, dùng IDs unique, reset namespace có kiểm soát và tránh chạy song song cùng email.

## 50. Test xóa qua Repository

Ví dụ:

```java
@Test
void deletingEntityDoesNotLeaveItQueryable() {
    Customer customer = new Customer(
        "c-test-301",
        "delete@example.test",
        "south",
        "Binh"
    );

    repository.save(customer);

    repository.deleteById(customer.getId());

    assertThat(
        repository.findById(customer.getId())
    ).isEmpty();

    assertThat(
        repository.findByEmail("delete@example.test")
    ).isEmpty();
}
```

Test xác nhận behavior nhìn từ Repository, nhưng không chứng minh mọi helper set key đã bị xóa hoàn toàn trong mọi trường hợp nếu không kiểm tra Redis keyspace/metadata.

Để điều tra memory leak do dangling indexes, có thể bổ sung kiểm tra memberships ở Redis test theo cấu trúc thực tế của phiên bản.

## 51. Kiểm thử expiration cần thời gian có kiểm soát

Đặt TTL ngắn cho một entity test hoặc dùng repository configuration dành riêng cho test.

Quy trình:

1. `repository.save` entity có TTL.
2. Kiểm tra `PTTL` dương.
3. Kiểm tra `findByEmail` trước expiration.
4. Poll `findById` tới khi empty với timeout hữu hạn.
5. Quan sát expired event listener và index cleanup ở môi trường test.
6. Kiểm tra query không trả dữ liệu đã hết hạn.
7. Kiểm tra dư thừa metadata nếu cần.
8. Không đòi event đến đúng thời điểm millisecond của TTL.

Tránh `Thread.sleep(1000)` rồi assert cứng ở ranh giới 1 giây; scheduler, server load và network làm test flaky.

Redis keyspace notifications là event best-effort, không phải timer giao hàng chính xác tuyệt đối.

## 52. Trường hợp test có giá trị bảo vệ khi deploy

Một ma trận:

| Test | Mục tiêu |
| --- | --- |
| Save rồi findById | Entity hash mapping |
| Save rồi findByEmail | Email index được tạo |
| Save rồi findByRegion | Index nhiều kết quả |
| Update email qua Repository | Xóa index cũ/thêm index mới |
| Update qua raw HSET | Phát hiện rủi ro index drift |
| Delete qua Repository | Không còn query entity |
| Raw DEL | Nhận diện dangling metadata |
| TTL expiration với listener online | Cleanup behavior |
| TTL expiration lúc listener offline | Khả năng miss cleanup/reconciliation |
| Deploy thêm @Indexed vào data cũ | Cần backfill |
| Query sau Redis failover | Read routing/consistency |
| Mixed-version deployment | Schema/index compatibility |
| Rebuild có concurrent writes | Không ghi đè update mới |
| Redis Cluster | Xác minh hỗ trợ topology |
| Redis outage | Không coi exception là kết quả empty |

Một Redis standalone Testcontainers chỉ xác minh behavior standalone; không chứng minh Sentinel failover hoặc Cluster support.

## 53. Monitoring keyspace và index cardinality

Một số tín hiệu Redis server:

```bash
redis-cli -h redis.internal -p 6379 INFO keyspace
redis-cli -h redis.internal -p 6379 INFO memory
redis-cli -h redis.internal -p 6379 INFO stats
```

Theo dõi:

- Số keys và keys có TTL.
- Used memory/RSS và maxmemory.
- Expired keys, evicted keys.
- Redis command errors.
- Application query hit/miss ratio.
- Redis Repository index mismatch probes.
- Repair backlog và throughput.
- Keyspace notification listener health.
- Node role/replication lag.

**Lưu ý:** Số Redis keys không bằng số entities: một entity có thể tạo nhiều index/helper keys. Không dùng `dbsize` làm tổng số Customer chính xác nếu không biết keyspace model.

Nếu cần đếm entities, dùng nguồn chuẩn hoặc enumeration theo index/root metadata đã được xác minh.

## 54. Monitoring listener và missed events

Có thể theo dõi:

```text
redis_repository_expiry_event_received_total
redis_repository_listener_connected
redis_repository_reconciliation_mismatch_total
redis_repository_repair_backlog
```

Đây là tên metric gợi ý; Spring/Micrometer không mặc định có chúng.

Nếu listener disconnect, việc keyspace events không được replay có thể khiến cần reconciliation. Đặc biệt cần quan sát:

- Redis reconnect/timeout.
- Redis restarted.
- Spring pod restart và listener startup.
- Managed Redis `notify-keyspace-events` bị chỉnh về trạng thái không phù hợp.
- Key bị evict trước hạn.
- Full resync/failover.
- Application instances cùng subscribe và hành vi event handling.

Không chỉ dùng “event count = 0” làm bằng chứng có lỗi; có thể thực sự không có key nào expire trong khoảng đó.

## 55. Runbook xử lý query thiếu kết quả

### Bước 1 — Xác nhận triệu chứng

Lấy một entity ID đã biết từ nguồn đáng tin cậy.

```java
repository.findById(id);
repository.findByEmail(expectedEmail);
```

Ghi timestamp, version ứng dụng và môi trường.

### Bước 2 — Xác minh input và topology

- Email chuẩn hóa đúng?
- Tenant/environment đúng?
- Redis primary/replica đọc ở đâu?
- Prefix/keyspace có đổi?
- Có bị catch exception và trả empty?

### Bước 3 — Xem Redis hash

Dùng `TYPE`, `HGETALL` hoặc mapping-aware inspection với các trường tối thiểu.

### Bước 4 — Xem index

Xác nhận key SET và membership thật theo Spring Data Redis version.

### Bước 5 — Kiểm tra nguyên nhân

- Raw `RedisTemplate`/CLI/Lua writers.
- Mới thêm `@Indexed`, chưa backfill.
- Mixed-version schema hoặc serializer.
- TTL, eviction, listener downtime.
- Concurrent updates.
- Cluster/replica lag.
- Query method unsupported.

### Bước 6 — Đánh giá phạm vi

Lấy mẫu IDs đáng tin cậy, ước lượng tỷ lệ mismatch, xác định ảnh hưởng business.

### Bước 7 — Chặn nguồn drift mới

Sửa writer, migration hoặc cấu hình listener trước.

### Bước 8 — Repair có kiểm soát

Thử trước trên test/staging, bảo toàn TTL, có backup, rate limit và checkpoint.

### Bước 9 — Verify kết quả

So sánh `findById`, indexed query, Redis membership và business source.

### Bước 10 — Theo dõi sau khắc phục

Đo mismatch/fallback/latency trong một khoảng thời gian, đảm bảo drift không tái diễn.

## 56. Một sơ đồ nguyên nhân – cách xử lý

```text
Query thiếu kết quả
       |
       +-- Entity không còn
       |       -> kiểm tra TTL / DB / eviction / keyspace
       |
       +-- Entity còn, index thiếu
       |       -> @Indexed? raw write? backfill?
       |
       +-- Entity còn, index cũ
       |       -> update ngoài repository / schema migration
       |
       +-- Index trỏ tới entity mất
       |       -> expiration listener / raw DEL / event gap
       |
       +-- Index đúng nhưng query sai
       |       -> case normalization / query support / serializer
       |
       +-- Query bị lỗi nhưng trả empty
       |       -> bỏ catch lỗi không phân biệt / metric errors
       |
       +-- Topology khác
               -> primary/replica lag / Cluster routing / DB/prefix
```

Điểm khác biệt quan trọng là **không phải mọi ô “không tìm thấy” đều do cùng một nguyên nhân**.

## 57. Bài tập A: tạo và kiểm tra secondary index

Tạo hai customers:

```java
repository.save(new Customer(
    "c-1", "an@example.test", "north", "An"
));

repository.save(new Customer(
    "c-2", "binh@example.test", "north", "Binh"
));
```

Hãy:

1. Gọi `findById` cho cả hai.
2. Gọi `findByEmail` cho từng email.
3. Gọi `findByRegion("north")` và xác nhận hai IDs.
4. Dùng Redis CLI `SCAN` xem các keys được Repository tạo.
5. Xác định các index SET và memberships.
6. Giải thích tại sao index SET không phải entity hash.

## 58. Bài tập B: tái hiện thiếu index khi dùng raw HSET

Trên Redis test:

1. `repository.save` một customer.
2. Dùng raw `HSET` đổi trường email.
3. Đọc entity bằng `findById`.
4. Gọi `findByEmail(newEmail)`.
5. Xem index membership cho email cũ và mới.
6. Viết một cách sửa write path không cần scan mọi key.
7. Giải thích vì sao dùng `SADD` thủ công một lần chưa chắc là repair hoàn chỉnh.

## 59. Bài tập C: thêm @Indexed sau khi deploy

Giả sử một triệu Customer records đã tồn tại từ trước.

Version mới thêm:

```java
@Indexed
private String email;
```

Hãy:

1. Giải thích tại sao records cũ chưa chắc tìm được.
2. Chọn nguồn IDs để backfill.
3. Thiết kế job có checkpoint/rate limit.
4. Đảm bảo TTL không bị kéo dài vô ý.
5. Chọn chiến lược khi có concurrent writer.
6. Thiết kế sample verification và rollback plan.
7. Đề xuất thời điểm chuyển traffic query sang index mới.

## 60. Bài tập D: TTL và listener outage

Một customer có TTL 60 giây, Spring app tắt ở giây 30 và chạy lại ở giây 120.

Hãy:

1. Mô tả kết quả có thể xảy ra với hash.
2. Mô tả index membership có thể còn lại.
3. Giải thích vì sao Redis Pub/Sub không replay expired event.
4. Phân biệt expired/evicted/raw delete.
5. Đề xuất reconciliation job cho dangling index.
6. Thiết kế test dùng polling có timeout thay vì sleep đúng ranh giới.

## 61. Bài tập E: nhận diện query không đúng

Các customer lưu email:

```text
An@Example.Test
binh@example.test
```

Query:

```java
findByEmail("an@example.test");
```

Hãy:

1. Phân tích normalization policy.
2. Xác định liệu index lookup có thể thiếu do case mismatch không.
3. Viết validation/normalization ở đường save và query.
4. Thiết kế migration cho dữ liệu cũ.
5. Viết integration test để tránh behavior khác nhau giữa hai deployments.

## 62. Bài tập F: Redis Cluster và index maintenance

Giả sử ứng dụng dùng Redis Cluster và `@RedisHash`/`@Indexed`.

Hãy:

1. Xác định Spring Data Redis version và Cluster support giới hạn.
2. Kiểm tra entity/hash và index SET được route đến đâu.
3. Xác định multi-key operations có cần cùng hash slot không.
4. Xem errors `CROSSSLOT`, `MOVED`, `ASK`.
5. Đề xuất cách thay đổi key placement hoặc query architecture khi cần.
6. Giải thích vì sao một Redis standalone Testcontainers không đủ chứng minh Cluster compatibility.

## 63. Những ngộ nhận thường gặp

**“findById có dữ liệu nghĩa là findByEmail phải thấy.”**

Không. `findById` có thể dùng entity hash, còn `findByEmail` cần secondary index membership.

**“Redis tự tạo index khi có HSET.”**

Không. Redis không biết Java annotation `@Indexed`; index là trách nhiệm mapping layer hoặc một hệ thống indexing riêng.

**“Chỉ cần gắn @Indexed là dữ liệu cũ tự có index.”**

Không. Dữ liệu tồn tại trước khi khai báo index có thể cần migration/backfill.

**“Mọi derived query của JPA đều dùng được trong Redis Repository.”**

Không. Redis Repository có tập query capabilities và giới hạn riêng.

**“HGETALL đúng mà query sai thì chắc Redis server bị hỏng.”**

Không nhất thiết. Có thể thiếu index, query input không khớp, serializer hoặc mapping version khác.

**“Nếu email đổi thì raw HSET đủ rồi.”**

Không. Raw `HSET` không tự update Repository index sets.

**“Keyspace notification xử lý mọi trường hợp key mất.”**

Không. Expiration, eviction, raw deletion và downtime có cơ chế khác nhau; Pub/Sub không replay khi subscriber offline.

**“Expired key events là durable queue.”**

Không. Redis Pub/Sub events có thể mất nếu subscriber không kết nối.

**“Redis logical DB/prefix khác nhau đảm bảo indexes nhất quán.”**

Không. Chúng chỉ phân tách tên/không gian key ở mức tương ứng, không thay mapping index maintenance.

**“SADD member vào index là repair an toàn.”**

Không nếu chưa biết encoding/helper metadata, TTL và concurrent writes.

**“SCAN mọi hash trên mỗi request là cách chữa thiếu index.”**

Không. Nó có thể gây tải O(N) và không scale.

**“Redis Cluster chỉ giống standalone với nhiều nodes.”**

Không. Cluster có slots, redirects và ràng buộc multi-key operations.

**“Một read sau write luôn thấy dữ liệu mới nếu dùng Redis.”**

Không khi có replica routing/replication lag, hoặc nhiều write operations chưa có tính nguyên tử toàn cục.

**“Save lại hàng triệu entity là backfill an toàn.”**

Không mặc định. Có thể reset TTL, ghi đè dữ liệu mới, tạo tải và gây rủi ro khác.

## 64. Câu hỏi thường gặp

### Vì sao findById trả kết quả nhưng findByEmail không?

Do hai đường truy cập khác nhau. Query email cần secondary index được maintain đúng; nếu entity hash tồn tại nhưng index thiếu membership, query có thể rỗng.

### @Indexed có tự tạo Redis Search index không?

Không. Spring Data Redis Repository secondary indexing khác Redis Search/Query Engine indexing. Hai hệ thống có schema và query flow riêng.

### Có thể cập nhật Redis hash bằng StringRedisTemplate không?

Về mặt Redis command thì được, nhưng khi đó phải quản lý tác động lên Repository indexes. Nếu không có cơ chế đồng bộ riêng, không nên vừa dùng raw writes vừa mong Repository query indexes tự cập nhật.

### Có cần index cho mọi property?

Không. Chỉ index những fields cần query và được hỗ trợ, vì indexes tốn memory và thêm chi phí maintenance khi writes/updates/deletes.

### Tại sao chỉ khách hàng cũ không tìm thấy?

Có thể `@Indexed` được thêm sau khi dữ liệu đã tồn tại và chưa chạy backfill.

### Vì sao index vẫn còn ID đã hết TTL?

Expiration event listener có thể không nhận event hoặc cleanup không hoàn tất. Cũng có thể key bị xóa ngoài Repository. Cần kiểm tra lifecycle và metadata.

### Redis Repository có đảm bảo transaction atomic giữa hash và mọi index SET không?

Không nên mặc định coi mọi write vào hash và các index sets là một transaction phân tán nguyên tử với hệ thống khác. Kiểm tra behavior/API/version khi concurrency và consistency quan trọng.

### Có thể dùng Redis CLI để repair index không?

Chỉ khi hiểu và kiểm chứng đầy đủ key layout, index metadata, encoding và concurrent writers; ưu tiên repository-aware repair trên môi trường test trước.

### Có nên xóa index cũ rồi tạo lại?

Không tự động. Một rebuild lớn cần nguồn dữ liệu chuẩn, kiểm soát downtime, TTL, memory, rollback và verification.

### Redis Cluster có ảnh hưởng Redis Repository indexes không?

Có thể, do placement keys, multi-key restrictions và các giới hạn mapping/version. Cần test trên topology Cluster thực tế.

### Làm sao phân biệt query empty với Redis outage?

Không swallow exceptions thành empty. Ghi nhận lỗi connection/timeout riêng; empty chỉ dành cho query thành công nhưng không tìm được dữ liệu.

### Có thể hoàn toàn tránh index drift không?

Giảm rủi ro bằng một write owner, thống nhất repository path, schema migrations, controlled TTL, monitoring và reconciliation. Nhưng với hệ thống phân tán, vẫn phải thiết kế phát hiện/khắc phục sai lệch.

### Có nên dùng findAll để backfill mọi entity?

Cần hiểu semantics và dữ liệu thực tế do Repository biết. Nếu raw records nằm ngoài cơ chế quản lý, findAll chưa chắc phản ánh đầy đủ. Ưu tiên nguồn IDs được kiểm chứng.

### Thêm cache trước Redis Repository có giúp sửa vấn đề không?

Không. Cache có thể làm lỗi khó thấy hơn; cần sửa index maintenance/source-of-truth query trước.

## 65. Tổng kết

Khi Spring Data Redis Repository trả thiếu kết quả, hãy xác định **dữ liệu gốc còn hay không** và **chỉ mục phụ đã phản ánh đúng field chưa**.

Các kết luận cốt lõi:

1. `findById` và `findBy<Field>` có thể đi theo những đường truy cập khác nhau.
2. `@Indexed` khiến Repository duy trì secondary indexes nhưng không tự backfill dữ liệu cũ.
3. Raw `HSET`, `DEL`, Lua và external writers **không tự cập nhật index metadata** của Spring Data Redis.
4. Missing index, stale index và dangling index là các trạng thái khác nhau.
5. TTL/expiration, listener downtime và Redis keyspace notification Pub/Sub có thể để lại metadata cần reconciliation.
6. Không nên mặc định query semantics/serializer của Redis Repository giống JPA.
7. Phục hồi cần hiểu schema thực tế, bảo toàn TTL, tránh ghi đè concurrent updates và có checkpoint/rollback.
8. Nên kiểm tra bằng **Redis integration tests**, không chỉ Mockito.
9. Trong Redis Cluster/replicas, phải xét topology/replication consistency và multi-key constraints.
10. Với dữ liệu quan trọng, cần một nguồn dữ liệu có thẩm quyền và cơ chế phát hiện/sửa drift, thay vì tin rằng mọi secondary index đều luôn hoàn hảo.

> **Quy trình an toàn:** xác nhận triệu chứng → kiểm tra ID và hash → tìm index membership → phân loại root cause → sửa đường ghi → repair có kiểm soát → xác nhận bằng query và monitoring.

Khi tuân theo quy trình này, nhóm phát triển có thể chẩn đoán được tình trạng “dữ liệu vẫn có nhưng tìm kiếm không thấy” mà không làm mất dữ liệu hoặc gây thêm lỗi trong quá trình sửa.

## Tài liệu tham khảo

- [Spring Data Redis – Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis – Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis – Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – Keyspace Events](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Redis – SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis – HGETALL](https://redis.io/docs/latest/commands/hgetall/)
- [Redis – SADD](https://redis.io/docs/latest/commands/sadd/)
- [Redis – SMEMBERS](https://redis.io/docs/latest/commands/smembers/)
- [Redis – TYPE](https://redis.io/docs/latest/commands/type/)
- [Redis – TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Testcontainers for Java](https://java.testcontainers.org/)
