# Tạo chỉ mục phụ bằng `@Indexed`

Trong Spring Data Redis, Redis Repository cho phép lưu một thực thể Java dưới dạng Redis Hash và truy xuất nó qua định danh (`@Id`). Nhưng nhiều nghiệp vụ cần tìm đối tượng bằng thuộc tính khác: email, trạng thái tài khoản, mã đơn hàng bên ngoài hoặc thành phố. Redis không tự tạo công cụ tìm kiếm theo từng trường của Hash. **Chỉ mục phụ (secondary index)** là cơ chế giúp ứng dụng tìm ra ID của các thực thể có cùng một giá trị thuộc tính mà không phải quét lần lượt toàn bộ Hash.

Với **Spring Data Redis Repository**, annotation `@Indexed` khai báo một thuộc tính cần được lập chỉ mục. Framework ghi thêm dữ liệu chỉ mục khi lưu thực thể và sử dụng chỉ mục đó cho những phương thức truy vấn repository được hỗ trợ.

Bài học này tập trung vào `org.springframework.data.redis.core.index.Indexed` trong mô hình `@RedisHash`, cách các Redis Set lưu quan hệ *giá trị thuộc tính → ID*, truy vấn theo chỉ mục và những hệ quả khi dữ liệu thay đổi.

## 1. Vì sao tra cứu bằng ID chưa đủ?

Giả sử Redis chứa hồ sơ khách hàng:

| ID | Email | Trạng thái | Thành phố |
| --- | --- | --- | --- |
| `c-101` | `lan@example.test` | `ACTIVE` | Hà Nội |
| `c-102` | `minh@example.test` | `ACTIVE` | Đà Nẵng |
| `c-103` | `hoa@example.test` | `BLOCKED` | Hà Nội |

Với `CrudRepository<Customer, String>`, việc tìm `c-101` bằng `findById("c-101")` là trực tiếp: Spring Data Redis biết key lưu thực thể từ keyspace và ID.

Nhưng để giải quyết câu hỏi *“khách hàng có email `lan@example.test` là ai?”*, ứng dụng cần một lối tra cứu khác. Nếu không có cấu trúc dữ liệu phụ hoặc công cụ tìm kiếm riêng, Redis Hash không cung cấp một lệnh tổng quát tương đương:

~~~sql
SELECT * FROM customers WHERE email = 'lan@example.test';
~~~

Spring Data Redis có thể duy trì một Redis Set đại diện cho giá trị email:

~~~text
customers:email:lan@example.test  →  { "c-101" }
customers:status:ACTIVE           →  { "c-101", "c-102" }
customers:address.city:Hà Nội     →  { "c-101", "c-103" }
~~~

Khi truy vấn theo email, repository đọc tập ID tương ứng rồi tải các Hash thực thể. Tên key ở đây minh họa quy ước mặc định; định dạng thực tế có thể thay đổi theo keyspace, mapping và phiên bản.

**`@Indexed` không thay đổi cấu trúc chính của thực thể.** Nó bổ sung các cấu trúc Redis phục vụ tra cứu. Một giá trị trùng nhau có thể gắn với nhiều ID vì Set chứa nhiều phần tử; chỉ mục không mặc nhiên bảo đảm tính duy nhất.

## 2. Ngữ cảnh hoạt động của `@Indexed`

Các thành phần chính của mô hình:

| Thành phần | Vai trò |
| --- | --- |
| `@RedisHash("customers")` | Khai báo thực thể lưu dưới dạng Redis Hash, với keyspace `customers` |
| `@Id` | Đánh dấu định danh dùng để lấy thực thể |
| `@Indexed` | Đánh dấu thuộc tính cần chỉ mục phụ cho truy vấn |
| `CrudRepository` | Cung cấp `save`, `findById`, `deleteById` và các phương thức truy vấn hỗ trợ |
| Redis Hash | Lưu nội dung từng thực thể |
| Redis Set | Chứa các ID gắn với giá trị chỉ mục |

Import đúng annotation:

~~~java
import org.springframework.data.redis.core.index.Indexed;
~~~

Đây là annotation thuộc **Spring Data Redis**. Không nhầm với annotation lập chỉ mục trong JPA, MongoDB, tìm kiếm toàn văn hoặc một thư viện khác.

**Phạm vi quan trọng:** `@Indexed` phát huy tác dụng khi đối tượng được ghi qua cơ chế mapping của **Spring Data Redis repositories**. Nếu tự lưu JSON vào Redis bằng `RedisTemplate.opsForValue().set(...)`, một serializer tùy ý sẽ không tự tạo các Redis Set chỉ mục như repository.

## 3. Khai báo thực thể có chỉ mục phụ

Ví dụ dùng hai lớp: `Customer` là thực thể gốc, `Address` là đối tượng lồng trong thực thể. Lớp `Address` được lưu như dữ liệu nhúng, không tham chiếu tới một Redis Hash độc lập.

**`Customer.java`**

~~~java
package com.example.redis.customer;

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
    private String status;

    private Address address;

    public Customer() {
        // Constructor để Spring Data khôi phục đối tượng.
    }

    public Customer(String id, String email, String status, Address address) {
        this.id = id;
        this.email = email;
        this.status = status;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

**`Address.java`**

~~~java
package com.example.redis.customer;

import org.springframework.data.redis.core.index.Indexed;

public class Address {

    @Indexed
    private String city;

    private String street;

    public Address() {
    }

    public Address(String city, String street) {
        this.city = city;
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }
}
~~~

Ý nghĩa:

- `email` và `status` có `@Indexed` trực tiếp trên thực thể gốc.
- `address.city` được lập chỉ mục vì `city` trong đối tượng lồng `Address` có `@Indexed`.
- `address.street` vẫn được lưu trong Hash nhưng không có chỉ mục phụ.
- `id` dùng làm định danh chính; không cần gắn `@Indexed` chỉ để gọi `findById`.

Khi cần truy vấn một thuộc tính lồng nhau, đường dẫn của thuộc tính được hiểu theo cấu trúc của object, chẳng hạn `address.city`.

### Tránh nhầm thuộc tính nhúng với tham chiếu

Trong ví dụ, `Address` là **value object nhúng**. Spring Data Redis có thể ánh xạ và lập chỉ mục các thuộc tính bên trong nó. Trường hợp dùng `@Reference` để trỏ tới một thực thể khác có cách lưu và vòng đời riêng; không nên mặc định rằng repository sẽ tự đi qua tham chiếu, lập chỉ mục tất cả thuộc tính của đối tượng được tham chiếu rồi hỗ trợ truy vấn nối giống SQL.

## 4. Viết repository và truy vấn theo chỉ mục

**`CustomerRepository.java`**

~~~java
package com.example.redis.customer;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);

    List<Customer> findByAddress_City(String city);

    List<Customer> findByEmailAndStatus(String email, String status);
}
~~~

Spring Data phân tích tên phương thức và tìm các thuộc tính cần tra cứu. Với những trường đã được lập chỉ mục:

~~~java
Customer lan = new Customer(
    "c-101",
    "lan@example.test",
    "ACTIVE",
    new Address("Hà Nội", "Phố Huế")
);

Customer minh = new Customer(
    "c-102",
    "minh@example.test",
    "ACTIVE",
    new Address("Đà Nẵng", "Hải Châu")
);

repository.save(lan);
repository.save(minh);

List<Customer> byEmail =
    repository.findByEmail("lan@example.test");

List<Customer> activeCustomers =
    repository.findByStatus("ACTIVE");

List<Customer> inHaNoi =
    repository.findByAddress_City("Hà Nội");

List<Customer> activeLan =
    repository.findByEmailAndStatus("lan@example.test", "ACTIVE");
~~~

Về ý nghĩa, các kết quả là:

| Phương thức | ID mong đợi |
| --- | --- |
| `findByEmail("lan@example.test")` | `c-101` |
| `findByStatus("ACTIVE")` | `c-101`, `c-102` |
| `findByAddress_City("Hà Nội")` | `c-101` |
| `findByEmailAndStatus("lan@example.test", "ACTIVE")` | `c-101` |

Tên phương thức `findByAddress_City` dùng dấu gạch dưới để diễn đạt ranh giới thuộc tính lồng nhau. Dạng tên này giúp tránh việc parser hiểu nhập nhằng các tên property liền nhau.

Trong ví dụ, `findByEmailAndStatus` là truy vấn ghép điều kiện bằng phép giao logic giữa hai tập ID được lập chỉ mục. Khả năng kết hợp điều kiện và những toán tử truy vấn được hỗ trợ tùy theo tính năng Redis Repository; nó không đồng nghĩa với một công cụ truy vấn SQL hoàn chỉnh.

### Truy vấn phụ thuộc chính xác vào giá trị đã lập chỉ mục

`@Indexed` thích hợp nhất cho **tra cứu bằng giá trị chính xác**. Nếu email trong Redis là `lan@example.test` thì câu hỏi `findByEmail("LAN@example.test")` không tự động tương đương. Cơ chế này không mặc nhiên thực hiện so khớp không phân biệt chữ hoa/chữ thường, chuẩn hóa Unicode, tìm mờ hoặc tìm chuỗi con.

Nếu hệ thống coi email không phân biệt chữ hoa/chữ thường, hãy xác định một quy tắc chuẩn hóa nhất quán trước lúc lưu và trước lúc truy vấn. Ví dụ, có thể chuẩn hóa email theo chính sách nghiệp vụ của ứng dụng và lưu giá trị chuẩn hóa thành thuộc tính được lập chỉ mục.

## 5. Bên trong Redis: Set ánh xạ giá trị sang ID

Với `@RedisHash("customers")`, key của thực thể thường có dạng:

~~~text
customers:c-101
~~~

Hash biểu diễn dữ liệu của khách hàng có thể bao gồm các field tương đương:

~~~text
email         → lan@example.test
status        → ACTIVE
address.city  → Hà Nội
address.street→ Phố Huế
_class        → metadata kiểu nếu mapper sử dụng
~~~

Ngoài Hash, Redis Repository ghi các tập chỉ mục. Mô hình logic:

~~~text
                              save(Customer)
                                    │
                                    ▼
                            Spring Data Mapper
                       ┌────────────┼─────────────┐
                       ▼            ▼             ▼
                  Redis Hash    Email Index    Status Index
                 customers:c-101   (SET)          (SET)
                       │            │             │
                  dữ liệu gốc      c-101          c-101
                                    │
                                    ▼
                              findByEmail(...)
                                    │
                                    ▼
                          lấy ID từ Redis Set
                                    │
                                    ▼
                         tải Hash theo từng ID
                                    │
                                    ▼
                           List<Customer>
~~~

Minh họa lệnh Redis để hình dung các cấu trúc:

~~~redis
HGETALL customers:c-101
SMEMBERS customers:email:lan@example.test
SMEMBERS customers:status:ACTIVE
SMEMBERS customers:address.city:Hà Nội
~~~

Trong một cấu hình mapping theo quy ước thông thường, các `SMEMBERS` trên cho thấy tập ID được gắn với giá trị chỉ mục. **Đây là ví dụ quan sát**, không phải cam kết rằng mọi cách cấu hình Redis Serializer/keyspace đều tạo ra key byte-for-byte giống vậy.

Redis Repository còn phải theo dõi những index mà một thực thể đã tham gia để có thể gỡ membership cũ khi cập nhật hoặc xóa. Những key phụ phục vụ quản lý chỉ mục là chi tiết nội bộ của mapper; không nên xây dựng nghiệp vụ dựa trực tiếp vào tên key nội bộ hoặc sửa chúng qua Redis CLI.

### Vì sao dùng Redis Set?

Set cho phép chứa các ID **không trùng lặp**. Khi nhiều khách hàng có `status = ACTIVE`, một Set ghi lại tất cả ID thỏa mãn. Với truy vấn kết hợp các giá trị đã lập chỉ mục, các phép toán tập hợp như giao/hợp cung cấp nền tảng để xác định ID ứng viên.

Điều này khác hoàn toàn việc tạo một key ánh xạ `email → customer` duy nhất. Chẳng hạn, hai bản ghi có cùng email vẫn có thể cùng nằm trong một Set. `@Indexed` **không phải unique constraint**.

## 6. Tạo và cập nhật chỉ mục theo vòng đời thực thể

### 6.1. Khi lưu lần đầu

Gọi `repository.save(customer)` khiến Spring Data Redis lưu dữ liệu Hash và cập nhật các tập chỉ mục tương ứng với các giá trị thuộc tính có đánh dấu `@Indexed`. Nhờ vậy, truy vấn repository được hỗ trợ có thể tìm thực thể qua email, trạng thái hoặc thành phố.

### 6.2. Khi thay đổi giá trị chỉ mục

Giả sử email của `c-101` thay đổi:

~~~java
Customer customer = repository.findById("c-101")
    .orElseThrow();

customer.setEmail("lan.new@example.test");
repository.save(customer);

// Kết quả mong đợi:
repository.findByEmail("lan@example.test");     // Không còn c-101
repository.findByEmail("lan.new@example.test"); // Có c-101
~~~

Khi thay đổi dữ liệu **qua Repository**, hạ tầng ánh xạ phụ trách cập nhật membership của những tập chỉ mục. Cách sử dụng đúng là sửa thực thể rồi lưu lại qua repository.

Không nên tự sửa trực tiếp Hash mà bỏ qua đường mapping:

~~~redis
HSET customers:c-101 email lan.other@example.test
~~~

Lệnh `HSET` trên thay đổi một field của Hash nhưng không tự động cập nhật các Redis Set chỉ mục mà Spring Data Redis đã quản lý. Khi đó, một truy vấn theo email cũ có thể vẫn lấy được ID, còn email mới có thể chưa tìm ra được. Một luồng ghi dữ liệu nhất quán phải thống nhất cơ chế cập nhật Hash và index.

### 6.3. Khi xóa thực thể

~~~java
repository.deleteById("c-101");
~~~

Đường xóa của Redis Repository xử lý dữ liệu thực thể và metadata chỉ mục liên quan. Nếu tự xóa Hash qua `DEL`, các tập phụ có thể còn membership cũ vì ứng dụng đã bỏ qua logic quản lý index.

Việc lưu/xóa thực thể và các tập chỉ mục liên quan có thể gồm nhiều lệnh Redis. Không nên giả định toàn bộ chuỗi cập nhật index là một giao dịch đa key nguyên tử, trừ khi đã kiểm tra và thiết kế riêng điều kiện nhất quán cần thiết.

### 6.4. Khi thuộc tính có giá trị `null`

Một thuộc tính không có giá trị thì không có giá trị cụ thể để làm khóa index. Chẳng hạn:

~~~java
Customer customer = new Customer(
    "c-104",
    null,
    "PENDING",
    new Address("Huế", null)
);

repository.save(customer);
~~~

Ứng dụng không nên mong đợi `findByEmail(null)` hoạt động như một cơ chế tìm tất cả bản ghi thiếu email qua chỉ mục phụ. Nếu cần truy vấn “chưa có email”, hãy thiết kế dữ liệu nghiệp vụ hoặc một thuộc tính trạng thái có thể lập chỉ mục rõ ràng.

### 6.5. Khi thêm `@Indexed` vào entity đã có dữ liệu

Thêm annotation vào mã nguồn không tự quét và tạo membership cho tất cả Hash đã được lưu từ các phiên bản cũ. Những bản ghi cũ có thể chưa xuất hiện trong truy vấn theo chỉ mục mới.

Khi triển khai chức năng này trên dữ liệu đang tồn tại, phải có chiến lược **backfill/reindex**: đọc dữ liệu gốc hợp lệ, đưa thực thể qua đường ghi của repository hoặc thực hiện quy trình tái lập index có kiểm soát. Cần cân nhắc khóa hiện hữu, TTL, cập nhật đồng thời và khả năng chạy lại mà không làm hỏng dữ liệu.

## 7. Kiểm thử tích hợp `@Indexed` với Redis thật

Chỉ nhìn thấy annotation trong code chưa đủ chứng minh truy vấn hoạt động. Một bài kiểm thử hữu ích nên chứng minh được ba hành vi: **lưu rồi tìm thấy**, **đổi giá trị rồi chỉ mục được cập nhật**, và **xóa rồi không còn tìm thấy**.

Ví dụ dependency cho một dự án Spring Boot có quản lý phiên bản bằng BOM/plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Giả sử hai lớp `Customer` và `Address` cùng repository đã được khai báo như ở trên. Kiểm thử dưới đây sử dụng Redis trong Testcontainers. Lớp cấu hình test cho phép Spring Boot auto-configuration thiết lập kết nối Redis và bật repository trong package chứa `CustomerRepository`.

~~~java
package com.example.redis.customer;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = CustomerIndexIntegrationTest.TestApp.class)
@Testcontainers
class CustomerIndexIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableRedisRepositories(basePackageClasses = CustomerRepository.class)
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.data.redis.host", REDIS::getHost);
        properties.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void findByIndexedPropertyAndRefreshIndexAfterUpdate() {
        String id = "it-" + UUID.randomUUID();
        String originalEmail = id + "@example.test";
        String newEmail = id + ".new@example.test";

        try {
            Customer customer = new Customer(
                id,
                originalEmail,
                "ACTIVE",
                new Address("Huế", "Lê Lợi")
            );
            repository.save(customer);

            assertThat(ids(repository.findByEmail(originalEmail)))
                .contains(id);
            assertThat(ids(repository.findByAddress_City("Huế")))
                .contains(id);

            customer.setEmail(newEmail);
            repository.save(customer);

            assertThat(ids(repository.findByEmail(originalEmail)))
                .doesNotContain(id);
            assertThat(ids(repository.findByEmail(newEmail)))
                .contains(id);

            repository.deleteById(id);

            assertThat(ids(repository.findByEmail(newEmail)))
                .doesNotContain(id);
        } finally {
            repository.deleteById(id);
        }
    }

    private static List<String> ids(List<Customer> customers) {
        return customers.stream().map(Customer::getId).toList();
    }
}
~~~

Mỗi lần chạy tạo một ID và email riêng, tránh xung đột giữa những lần test song song. Đoạn kiểm thử sử dụng đường ghi/xóa của repository để kiểm tra chính hành vi index mà framework sở hữu. Máy chạy integration test cần Docker hoặc một môi trường container tương thích.

Với ứng dụng có cấu hình Redis hoặc repository riêng, hãy sử dụng cấu hình Spring thực tế của dự án và bảo đảm test trỏ vào Redis trong container. Không dùng Redis production để chạy bài test.

## 8. Giới hạn của chỉ mục phụ bằng `@Indexed`

### 8.1. Không thay thế một bộ máy truy vấn tổng quát

`@Indexed` hỗ trợ tra cứu dựa trên chỉ mục thuộc tính trong mô hình Redis Repository. Nó không biến Redis thành cơ sở dữ liệu quan hệ và không tự bổ sung mọi khả năng như:

- Tìm kiếm toàn văn, chấm điểm mức độ liên quan hoặc fuzzy search.
- Truy vấn `LIKE '%abc%'` cho mọi chuỗi.
- `JOIN` tùy ý giữa nhiều loại entity.
- Sắp xếp và phân trang trên tập dữ liệu lớn theo một thuộc tính bất kỳ giống SQL.
- Phân tích truy vấn phức tạp hoặc tổng hợp nhiều trường linh hoạt.

Nếu cần tìm kiếm toàn văn hoặc truy vấn tài liệu phong phú, hãy đánh giá một công cụ tìm kiếm hoặc khả năng indexing/query chuyên dụng phù hợp với Redis được triển khai. **Redis Repository `@Indexed` và Redis Search/RediSearch là hai cơ chế khác nhau**; không thể suy luận rằng thêm `@Indexed` sẽ tạo ra một search index cho Redis Search.

### 8.2. Chỉ mục không bảo đảm email duy nhất

Hai khách hàng có cùng email có thể cùng nằm trong Redis Set:

~~~text
customers:email:shared@example.test → { "c-201", "c-202" }
~~~

Phương thức trả về `List<Customer>` hợp lý khi nhiều thực thể có thể trùng giá trị. Nếu nghiệp vụ yêu cầu email là duy nhất, cần **ràng buộc và cơ chế ghi bảo đảm tính duy nhất** được thiết kế riêng, nhất là khi có nhiều instance ứng dụng lưu đồng thời. Chỉ đặt return type `Optional<Customer>` hoặc thêm `@Indexed` không tạo unique constraint.

### 8.3. Chỉ mục có chi phí lưu trữ và cập nhật

Với mỗi thuộc tính được đánh dấu, hệ thống phải duy trì thêm các Set và metadata quản lý index. Chỉ mục giúp tăng tốc một số cách tìm kiếm, nhưng có chi phí:

| Khía cạnh | Lợi ích | Chi phí/đánh đổi |
| --- | --- | --- |
| Đọc theo thuộc tính | Tra ra nhóm ID bằng Redis Set | Có thể phải tải nhiều Hash sau khi lấy ID |
| Ghi mới | Dữ liệu có thể truy vấn theo thuộc tính ngay | Phải ghi Hash và thêm membership vào các Set |
| Cập nhật | Truy vấn phản ánh giá trị mới qua repository | Phải gỡ membership cũ và thêm membership mới |
| Xóa | Không còn trả về bản ghi bị xóa sau khi index được dọn | Phải dọn metadata/index liên quan |
| Bộ nhớ Redis | Tránh quét toàn bộ dữ liệu khi truy vấn | Tốn bộ nhớ cho Set và key phụ |

Đánh dấu quá nhiều field có thể tạo số lượng key/Set đáng kể. Ví dụ một thuộc tính có hàng triệu giá trị phân biệt có thể kéo theo rất nhiều Set nhỏ; một trạng thái phổ biến như `ACTIVE` có thể tạo một Set chứa rất nhiều ID. Chỉ nên lập chỉ mục cho những truy vấn nghiệp vụ thật sự cần.

### 8.4. Giá trị có thể lộ qua tên key chỉ mục

Trong cách đặt tên key thông thường, giá trị thuộc tính tham gia vào tên key chỉ mục. Nếu dùng dữ liệu nhạy cảm như email, mã định danh cá nhân hoặc token làm giá trị chỉ mục, cần xét chính sách bảo mật, quyền truy cập Redis và log/backup/quan sát key. Đừng lập chỉ mục trực tiếp bí mật như access token chỉ vì tiện truy vấn. Nếu cần tra cứu chính xác theo một giá trị nhạy cảm, hãy thiết kế khóa tìm kiếm đã được chuẩn hóa và bảo vệ phù hợp với yêu cầu bảo mật.

## 9. Chỉ mục và TTL: chuyện gì xảy ra khi key hết hạn?

Một thực thể Redis có thể có thời gian sống, chẳng hạn:

~~~java
@RedisHash(value = "customers", timeToLive = 300)
public class Customer {
    // ...
}
~~~

`timeToLive = 300` trong ví dụ là 300 giây. Khi Redis Hash hết hạn, dữ liệu thực thể không còn đọc được. Tuy nhiên, **dọn membership trong secondary index là một việc liên quan khác**.

Spring Data Redis có cơ chế lắng nghe **Redis keyspace expiration events** để hỗ trợ xử lý các thực thể đã hết hạn và dọn thông tin index tương ứng. Việc nhận được event phụ thuộc cấu hình của Redis, việc listener đang chạy và thời điểm sự kiện xảy ra. Những trường hợp cần chú ý:

- Keyspace notifications bị tắt hoặc môi trường Redis không cho phép ứng dụng tự bật chúng.
- Ứng dụng/lifecycle listener không hoạt động vào lúc Redis phát thông báo.
- Key bị xóa trực tiếp ngoài repository.
- Key hết hạn trước khi một listener bắt đầu lắng nghe.

Redis Pub/Sub keyspace notification không phải một hàng đợi bền vững có thể phát lại mọi sự kiện đã bỏ lỡ. Vì vậy, **không mặc định mọi Set chỉ mục đều được dọn sạch tức thì chỉ vì Hash đã hết TTL**.

Ví dụ kết quả có thể thấy:

~~~text
GET/HGETALL customers:c-101  → key đã hết hạn hoặc không tồn tại
SMEMBERS customers:status:ACTIVE → có thể còn "c-101" nếu cleanup bị bỏ lỡ
~~~

Điều này có thể dẫn tới membership mồ côi và tăng sử dụng bộ nhớ, cho dù thao tác tải Hash thực tế không tìm thấy entity đó. Với dữ liệu TTL cao, cần kiểm tra cấu hình keyspace events, cách khởi động listener, khả năng chạy trong Redis được quản lý, và xây dựng phương án quan sát/dọn index khi thích hợp.

TTL không phải thuộc tính của chính annotation `@Indexed`. Các chính sách hết hạn, index cleanup và hiệu quả truy vấn cần được thiết kế như những mối quan tâm liên quan nhưng riêng biệt.

## 10. Lỗi thường gặp khi dùng `@Indexed`

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `findByEmail` không tìm ra dữ liệu đã lưu | Field thiếu `@Indexed` hoặc bản ghi cũ chưa được index | Xác nhận annotation và kế hoạch reindex dữ liệu hiện hữu |
| `findById` hoạt động nhưng `findByStatus` không có kết quả | ID lookup và secondary index là hai đường truy cập khác nhau | Kiểm tra index của `status` và quá trình `save` qua repository |
| Sửa email bằng `HSET` nhưng truy vấn trả kết quả cũ | Thao tác trực tiếp không đồng bộ các Set index | Cập nhật qua repository hoặc quản lý index tường minh |
| `findByEmail("LAN@...")` không khớp email chữ thường | Giá trị trong index không được chuẩn hóa theo quy tắc đó | Chuẩn hóa dữ liệu khi ghi và khi truy vấn |
| Hai bản ghi có cùng email | `@Indexed` không có unique constraint | Thiết kế cơ chế ràng buộc duy nhất riêng |
| Thêm `@Indexed` nhưng dữ liệu cũ không xuất hiện | Annotation không tự backfill Hash cũ | Thực hiện quy trình reindex có kiểm soát |
| Key Hash hết hạn nhưng Set index còn ID | Expiration event/cleanup không được nhận hoặc xử lý | Xem cấu hình notification, listener và phương án dọn |
| Truy vấn tìm chuỗi con không hoạt động | Secondary index không phải full-text search | Dùng mô hình truy vấn hoặc công cụ tìm kiếm khác |
| Ghi JSON bằng `RedisTemplate` rồi mong repository tìm thấy | Serializer thông thường không tạo secondary index | Chọn một đường ghi nhất quán với repository |
| Tìm theo thuộc tính của `@Reference` như một phép JOIN | Spring Data Redis không tự JOIN tham chiếu theo kiểu SQL | Thiết kế truy vấn/index dựa trên thuộc tính thực sự được ánh xạ |

## 11. Thiết kế chỉ mục theo nhu cầu truy vấn

Giả sử một ứng dụng hỗ trợ các use case:

1. Tìm khách hàng bằng ID để mở trang chi tiết.
2. Tìm khách hàng bằng email khi đăng nhập.
3. Liệt kê toàn bộ khách hàng trạng thái `ACTIVE`.
4. Tìm khách hàng theo từ khóa trong nhiều trường văn bản.

Lựa chọn tương ứng:

| Use case | Lựa chọn |
| --- | --- |
| Theo ID | `@Id` và `findById`, không cần secondary index |
| Theo email chính xác | `@Indexed` trên thuộc tính email đã chuẩn hóa |
| Theo trạng thái | `@Indexed` trên `status` nếu truy vấn này thật sự cần và kích thước kết quả phù hợp |
| Tìm kiếm văn bản nâng cao | Đánh giá khả năng search chuyên dụng; `@Indexed` không đủ |

Trước khi thêm annotation, hãy cân nhắc liệu kết quả tra cứu có thể quá lớn hay không. Một index cho `status=ACTIVE` giúp xác định nhanh tập ID, nhưng nếu hàng triệu thực thể đang hoạt động thì việc tải toàn bộ kết quả thành `List<Customer>` vẫn tốn bộ nhớ và thời gian. Có thể cần tổ chức lại dữ liệu truy cập, giới hạn tập kết quả hoặc xây dựng một read model khác phù hợp với quy mô.

Một số thực hành hữu ích:

- **Thống nhất một đường ghi.** Nếu repository sở hữu Hash và index, những luồng sửa dữ liệu khác phải tôn trọng cơ chế cập nhật chỉ mục.
- **Chuẩn hóa giá trị có quy tắc rõ ràng.** Email, mã vùng hoặc trạng thái cần được ghi và truy vấn theo cùng quy ước.
- **Kiểm thử sau cập nhật và xóa.** Chỉ mục phải phản ánh vòng đời thực thể, không chỉ lượt lưu đầu tiên.
- **Lập kế hoạch cho dữ liệu cũ.** Thêm `@Indexed` trên một hệ thống đang hoạt động thường cần backfill.
- **Theo dõi TTL và index cleanup.** Không coi notification mất mát là bằng chứng dữ liệu đã được dọn sạch.
- **Đo chi phí bộ nhớ và thời gian thực tế.** Số lượng key, kích thước Set và tần suất cập nhật ảnh hưởng trực tiếp đến lựa chọn index.

## 12. Kết luận

`@Indexed` là cách khai báo **chỉ mục phụ dựa trên thuộc tính** trong Spring Data Redis Repository. Khi lưu một `@RedisHash`, framework có thể duy trì các Redis Set liên kết giá trị thuộc tính với ID thực thể; các phương thức truy vấn repository được hỗ trợ dùng tập ID đó để tải đối tượng.

Để sử dụng đúng, cần phân biệt rõ **ID lookup** với **secondary index**, sử dụng annotation của Spring Data Redis trên property cần truy vấn, và giữ đường ghi/xóa nhất quán qua repository. Chỉ mục phụ hữu ích cho tra cứu chính xác, nhưng không bảo đảm tính duy nhất, không thay thế full-text search và có chi phí cập nhật, bộ nhớ cùng vòng đời dọn dữ liệu khi TTL hết hạn.
