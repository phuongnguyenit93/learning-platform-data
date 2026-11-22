# Bỏ qua thuộc tính không lưu trữ bằng `@Transient`

Khi sử dụng **Spring Data Redis Repository**, một đối tượng Java có thể được ánh xạ thành **Redis Hash**: các thuộc tính của thực thể trở thành dữ liệu được ghi xuống Redis và được khôi phục khi đọc lại. Tuy nhiên, không phải mọi thông tin có trong đối tượng đều nên được lưu. Có thuộc tính chỉ phục vụ hiển thị, tính toán tạm thời, theo dõi một request hoặc lưu kết quả trung gian.

Trong trường hợp đó, dùng **`@Transient` của Spring Data** để yêu cầu cơ chế ánh xạ bỏ qua thuộc tính. Đây là một quyết định về **mô hình dữ liệu lưu trữ**, không chỉ là cách ẩn một trường khi trả JSON qua HTTP.

## 1. `@Transient` giải quyết vấn đề gì?

Giả sử ứng dụng quản lý hồ sơ khách hàng trong Redis:

- **`id`**: định danh để lấy lại hồ sơ.
- **`fullName`** và **`loyaltyPoints`**: dữ liệu nghiệp vụ cần được lưu.
- **`requestTraceId`**: mã theo dõi chỉ có ý nghĩa trong request hiện tại.
- **`displayBadge`**: nhãn hiển thị được tính riêng cho giao diện.

Nếu lưu cả năm thuộc tính, Redis sẽ chứa thông tin tạm thời không cần thiết. Điều đó làm tăng dữ liệu lưu, tạo nguy cơ đọc lại thông tin đã cũ và khiến ranh giới giữa trạng thái nghiệp vụ với trạng thái trình bày trở nên khó hiểu.

Đánh dấu các thuộc tính tạm thời bằng:

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String requestTraceId;
~~~

Spring Data nhận diện thuộc tính này là **không bền vững** (*non-persistent property*) trong mô hình ánh xạ. Khi thực thể được ghi thông qua Spring Data Redis Repository, giá trị của nó không được đưa vào Redis Hash. Khi thực thể được tái tạo từ Redis, framework cũng không đọc giá trị đó từ Redis.

> Cần import đúng `org.springframework.data.annotation.Transient`. Trong bài này, mọi ví dụ đều nói về ánh xạ thực thể bằng Spring Data Redis, đặc biệt là mô hình `@RedisHash` và Redis Repository.

## 2. Ví dụ thực thể: lưu dữ liệu nghiệp vụ, bỏ qua dữ liệu tạm

Định nghĩa một thực thể `CustomerProfile`:

~~~java
package com.example.redis.profile;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customer-profile")
public class CustomerProfile {

    @Id
    private String id;

    private String fullName;

    private int loyaltyPoints;

    @Transient
    private String requestTraceId;

    @Transient
    private String displayBadge;

    public CustomerProfile() {
        // Cho phép framework tạo instance khi đọc dữ liệu.
    }

    public CustomerProfile(String id, String fullName, int loyaltyPoints) {
        this.id = id;
        this.fullName = fullName;
        this.loyaltyPoints = loyaltyPoints;
    }

    public String getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public int getLoyaltyPoints() {
        return loyaltyPoints;
    }

    public void setLoyaltyPoints(int loyaltyPoints) {
        this.loyaltyPoints = loyaltyPoints;
    }

    public String getRequestTraceId() {
        return requestTraceId;
    }

    public void setRequestTraceId(String requestTraceId) {
        this.requestTraceId = requestTraceId;
    }

    public String getDisplayBadge() {
        return displayBadge;
    }

    public void setDisplayBadge(String displayBadge) {
        this.displayBadge = displayBadge;
    }
}
~~~

Định nghĩa repository:

~~~java
package com.example.redis.profile;

import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {
}
~~~

Trong một ứng dụng Spring Boot có Spring Data Redis và Redis Repository được bật, phương thức `save` sẽ ánh xạ thực thể sang dữ liệu Redis, còn `findById` sẽ dựng lại đối tượng từ dữ liệu đã lưu.

Ví dụ sử dụng:

~~~java
CustomerProfile profile =
    new CustomerProfile("customer-42", "Nguyễn Lan", 120);

profile.setRequestTraceId("req-8f22");
profile.setDisplayBadge("Khách hàng thân thiết");

repository.save(profile);

CustomerProfile loaded = repository.findById("customer-42")
    .orElseThrow();

System.out.println(loaded.getFullName());       // Nguyễn Lan
System.out.println(loaded.getLoyaltyPoints());   // 120
System.out.println(loaded.getRequestTraceId()); // null
System.out.println(loaded.getDisplayBadge());   // null
~~~

Hai thuộc tính có `@Transient` vẫn tồn tại như những field bình thường **trong đối tượng Java đang nằm trong bộ nhớ**. Ví dụ, ngay trước hoặc sau khi gọi `save(profile)`, lời gọi `profile.getRequestTraceId()` vẫn có thể trả về `"req-8f22"`. Annotation không tự xóa giá trị khỏi object.

Sự khác biệt chỉ hiện ra khi tạo **một instance mới từ dữ liệu Redis**: các thuộc tính không được lưu sẽ có giá trị mặc định của Java (`null` với `String`, `false` với `boolean`, `0` với kiểu số nguyên thủy), trừ khi constructor, field initializer hoặc logic ứng dụng tự thiết lập chúng.

## 3. Redis Hash chứa những gì?

Với `@RedisHash("customer-profile")` và ID `customer-42`, Spring Data Redis thường lưu thực thể dưới key có dạng:

~~~text
customer-profile:customer-42
~~~

Về mặt ý nghĩa, dữ liệu tương ứng là:

| Thuộc tính | Có lưu trong Redis Hash? | Lý do |
| --- | --- | --- |
| `id` | Tham gia định danh thực thể | Được đánh dấu `@Id` |
| `fullName` | Có | Thuộc tính bền vững bình thường |
| `loyaltyPoints` | Có | Thuộc tính bền vững bình thường |
| `requestTraceId` | Không | Có `@Transient` |
| `displayBadge` | Không | Có `@Transient` |

Một Hash có thể chứa cả thông tin kiểu của Spring Data, chẳng hạn `_class`, tùy cấu hình mapper. Vì vậy, không nên kiểm thử bằng cách khẳng định toàn bộ Hash chỉ có đúng hai field dữ liệu. Điều cần khẳng định là các field nghiệp vụ có giá trị đúng và các field được bỏ qua **không xuất hiện**.

Sơ đồ luồng dữ liệu:

~~~text
        CustomerProfile trong Java
     ┌──────────────────────────────┐
     │ id = "customer-42"           │
     │ fullName = "Nguyễn Lan"      │
     │ loyaltyPoints = 120          │
     │ requestTraceId = "req-8f22"  │
     │ displayBadge = "Thân thiết"  │
     └──────────────┬───────────────┘
                    │ repository.save(...)
                    ▼
          Spring Data Redis Mapper
             │              │
             │              └── @Transient → bỏ qua
             ▼
       Redis Hash (dữ liệu lưu)
     ┌──────────────────────────────┐
     │ fullName = "Nguyễn Lan"      │
     │ loyaltyPoints = 120          │
     │ [metadata ánh xạ nếu có]     │
     └──────────────┬───────────────┘
                    │ repository.findById(...)
                    ▼
         CustomerProfile mới trong Java
     ┌──────────────────────────────┐
     │ fullName = "Nguyễn Lan"      │
     │ loyaltyPoints = 120          │
     │ requestTraceId = null        │
     │ displayBadge = null          │
     └──────────────────────────────┘
~~~

Không nên suy ra định dạng Hash chính xác từ tên class Java. Prefix key, serializer, kiểu dữ liệu lồng nhau và metadata có thể phụ thuộc cấu hình. Với ví dụ đơn giản ở trên, trường hợp kiểm tra được quan tâm là hai thuộc tính `requestTraceId` và `displayBadge` không được mapper ghi xuống Redis.

## 4. Kiểm chứng bằng kiểm thử tích hợp

Cách chắc chắn nhất để kiểm tra thuộc tính được bỏ qua là **ghi một thực thể có giá trị khác null**, đọc lại bằng repository, đồng thời kiểm tra Hash ở Redis. Nếu chỉ đặt giá trị `null` rồi lưu, việc Redis không có field đó chưa chứng minh `@Transient` hoạt động.

Với Gradle Groovy và Spring Boot quản lý dependency versions, một cấu hình tối thiểu cho bài kiểm thử có thể là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Ví dụ sau đặt trong một dự án Spring Boot đã quét và tạo `CustomerProfileRepository`. Redis được khởi động bằng Testcontainers, tránh đụng tới Redis dùng chung:

~~~java
package com.example.redis.profile;

import java.util.UUID;

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

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers
class CustomerProfileRepositoryTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    CustomerProfileRepository repository;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void transientPropertiesAreNotSavedToRedisHash() {
        String id = "customer-" + UUID.randomUUID();
        String redisKey = "customer-profile:" + id;

        try {
            CustomerProfile profile =
                new CustomerProfile(id, "Nguyễn Lan", 120);
            profile.setRequestTraceId("req-test-123");
            profile.setDisplayBadge("VIP");

            repository.save(profile);

            // Dữ liệu nghiệp vụ được lưu.
            assertThat(redis.opsForHash().get(redisKey, "fullName"))
                .isEqualTo("Nguyễn Lan");
            assertThat(redis.opsForHash().get(redisKey, "loyaltyPoints"))
                .isEqualTo("120");

            // Dữ liệu tạm thời không xuất hiện trong Redis Hash.
            assertThat(redis.opsForHash().hasKey(redisKey, "requestTraceId"))
                .isFalse();
            assertThat(redis.opsForHash().hasKey(redisKey, "displayBadge"))
                .isFalse();

            // Lần đọc tiếp theo tạo thực thể từ trạng thái đã lưu.
            CustomerProfile loaded = repository.findById(id)
                .orElseThrow();

            assertThat(loaded.getFullName()).isEqualTo("Nguyễn Lan");
            assertThat(loaded.getLoyaltyPoints()).isEqualTo(120);
            assertThat(loaded.getRequestTraceId()).isNull();
            assertThat(loaded.getDisplayBadge()).isNull();
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

Trong ví dụ, key Redis sử dụng keyspace từ `@RedisHash("customer-profile")`. Khi ứng dụng tùy biến keyspace, đổi key bằng converter riêng hoặc sửa chiến lược định danh, phải điều chỉnh cách xác định key trong kiểm thử. Để chạy Testcontainers, máy test cần Docker hoặc môi trường container tương thích.

Nếu muốn tự quan sát bằng Redis CLI sau khi chạy đoạn mã lưu:

~~~redis
HGETALL customer-profile:customer-42
HGET customer-profile:customer-42 requestTraceId
HGET customer-profile:customer-42 displayBadge
~~~

Hai lệnh `HGET` cho các field đã đánh dấu `@Transient` sẽ không tìm thấy giá trị trong Hash do mapper vừa ghi. Tránh nhầm kết quả `nil` với việc một field đang có giá trị Java là `null`: chỉ khi thử với giá trị ban đầu khác null và đọc lại mới chứng minh rõ hành vi mong đợi.

## 5. Phân biệt `@Transient` với các cơ chế khác

Các cơ chế trông có vẻ giống nhau nhưng tác động lên những pipeline khác nhau.

| Cơ chế | Phạm vi chính | Ví dụ sử dụng |
| --- | --- | --- |
| `org.springframework.data.annotation.Transient` | Ánh xạ thuộc tính bền vững của Spring Data, gồm Redis Repository | Không lưu `requestTraceId` trong Redis Hash |
| Từ khóa Java `transient` | Java Object Serialization và cơ chế phản ánh/mapping có xét modifier | Field không tham gia Java serialization mặc định |
| `com.fasterxml.jackson.annotation.JsonIgnore` | Jackson JSON serialization/deserialization | Ẩn field khỏi JSON API khi dùng Jackson |
| `jakarta.persistence.Transient` | Ánh xạ JPA/Hibernate | Không ánh xạ field thành cột trong cơ sở dữ liệu quan hệ |
| Gán thuộc tính bằng `null` | Giá trị của object ở thời điểm cụ thể | Không đồng nghĩa với việc loại bỏ thuộc tính khỏi mô hình mapping |

### 5.1. `@Transient` không đồng nghĩa `@JsonIgnore`

Xét thuộc tính:

~~~java
@Transient
private String requestTraceId;
~~~

Spring Data Redis Repository bỏ qua field khi ánh xạ sang Redis Hash. Tuy nhiên, nếu đối tượng Java còn chứa `requestTraceId` được trả qua REST Controller, Jackson **vẫn có thể xuất field đó ra JSON** thông qua getter. Muốn thay đổi JSON API, dùng DTO phù hợp hoặc cấu hình Jackson như `@JsonIgnore`.

Ngược lại:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

@JsonIgnore
private String internalNote;
~~~

Annotation của Jackson không tự biến `internalNote` thành thuộc tính transient trong Spring Data Redis Repository. Đừng dùng một annotation thuộc JSON để thay thế quy tắc lưu trữ.

Nếu cần bỏ qua field ở cả hai lớp, có thể áp dụng cả hai annotation hoặc tách entity và API DTO:

~~~java
@Transient
@JsonIgnore
private String requestTraceId;
~~~

Chỉ sử dụng kết hợp này khi thực sự có cả hai yêu cầu. Đối với API lớn, **DTO riêng** thường giúp xác định rõ trường nào được phép xuất hiện trong response.

### 5.2. `@Transient` trong Repository khác với `RedisTemplate` lưu một giá trị tùy ý

Spring Data Redis cung cấp nhiều cách làm việc với dữ liệu:

~~~java
repository.save(profile);                  // Ánh xạ entity → Redis Hash
redisTemplate.opsForValue().set(key, obj); // Serializer được cấu hình cho value
~~~

Trường hợp đầu sử dụng hạ tầng mapping entity của Spring Data Redis, nơi `@Transient` có ý nghĩa. Trường hợp thứ hai sử dụng serializer của `RedisTemplate`: có thể là JDK serialization, Jackson JSON hoặc serializer tự viết. **Không được mặc định rằng serializer bất kỳ đều hiểu `@Transient`.**

Tương tự, một cache Redis do Spring Cache (`@Cacheable` + `RedisCacheManager`) quản lý thường ghi giá trị thông qua serializer của cache. Muốn loại bỏ thuộc tính khỏi cache payload, cần xem serializer thực tế và cấu hình serialization tương ứng; `@Transient` của entity không phải cam kết chung cho mọi đường ghi Redis.

Đây là lỗi nhận thức thường gặp: thấy cùng một máy chủ Redis rồi cho rằng tất cả thao tác lưu dữ liệu đều sử dụng cùng bộ chuyển đổi entity.

### 5.3. `@Transient` và `transient` Java

Có thể viết:

~~~java
private transient String requestTraceId;
~~~

Từ khóa Java `transient` có ngữ nghĩa ở cấp ngôn ngữ, đặc biệt đối với Java serialization. Spring Data cũng có thể nhận diện modifier này khi xây dựng metadata thuộc tính. Tuy vậy, khi muốn diễn đạt rõ **ý định loại trừ khỏi mô hình bền vững của Spring Data**, nên dùng annotation `org.springframework.data.annotation.Transient`. Nó mô tả trực tiếp hợp đồng mapping mà người đọc mã đang cần hiểu.

Không thể suy luận rằng bất kỳ cơ chế serialization nào cũng bỏ qua field theo cùng cách; cần kiểm tra đường lưu cụ thể.

## 6. Ứng dụng điển hình của thuộc tính không lưu trữ

### 6.1. Giá trị được tính lại từ dữ liệu đã lưu

Thay vì ghi nhãn hiển thị xuống Redis rồi phải cập nhật nó mỗi khi điểm thưởng thay đổi, có thể tính khi cần:

~~~java
@Transient
private String displayBadge;

public String getDisplayBadge() {
    return loyaltyPoints >= 100 ? "VIP" : "Thường";
}
~~~

Trong cách này, Redis chỉ cần chứa `loyaltyPoints`. Sau khi tải lại entity, getter vẫn tính được nhãn phù hợp. Lưu ý: một getter có logic tính toán không tự động làm thuộc tính trở thành transient; annotation trên field là tín hiệu rõ ràng cho Spring Data mapper.

Nếu getter đơn thuần trả về một field transient mà không tính lại, giá trị sau khi tải từ Redis thường là `null`. Vì thế, hãy quyết định cụ thể thuộc tính đó được **tính theo yêu cầu**, **thiết lập sau khi tải**, hay **không cần tồn tại ngoài request ban đầu**.

### 6.2. Context của request hoặc dữ liệu chỉ dùng trong một thao tác

Ví dụ `requestTraceId`, tên người dùng đang xem dữ liệu, trạng thái kiểm tra trong một workflow. Chúng thay đổi theo request và không có ý nghĩa như trạng thái tồn tại lâu dài của entity.

Nhiều trường hợp tốt hơn nên giữ context ở service/request-scoped object hoặc DTO, bởi cùng một entity bền vững có thể được sử dụng ở nhiều request khác nhau. Khi vẫn cần gắn field phụ vào entity trong một luồng xử lý, `@Transient` giúp tránh vô tình lưu nó.

### 6.3. Thuộc tính không nên lập chỉ mục hoặc truy vấn từ Redis

Một field đã bị loại khỏi dữ liệu lưu cũng không thể được giả định là có mặt trong chỉ mục hoặc truy vấn repository. Chẳng hạn, nếu `displayBadge` được tính động nhưng yêu cầu tìm mọi khách hàng “VIP” ngay trong Redis, việc chỉ thêm phương thức truy vấn theo `displayBadge` là không đủ.

Hãy lựa chọn giữa:

- Lưu một thuộc tính nghiệp vụ có thể truy vấn và cập nhật nó theo quy tắc rõ ràng.
- Truy vấn từ các dữ liệu nền đã lưu, ví dụ `loyaltyPoints`, với cơ chế indexing/truy vấn tương thích.
- Tính nhãn sau khi đọc dữ liệu nếu khối lượng và mục tiêu truy vấn cho phép.

`@Transient` thể hiện quyết định rằng thuộc tính đó **không thuộc trạng thái lưu trữ**, nên không nên thiết kế truy vấn Redis như thể field vẫn được ghi.

## 7. Lưu ý khi dùng constructor, getter và property access

### Constructor khôi phục entity

Spring Data cần tạo đối tượng và gán những thuộc tính bền vững khi đọc từ Redis. Với entity sử dụng constructor phục vụ persistence, không nên bắt buộc truyền một giá trị chỉ tồn tại ở field `@Transient`:

~~~java
// Thiết kế cần tránh khi đây là constructor bắt buộc để materialize entity:
public CustomerProfile(
        String id,
        String fullName,
        String requestTraceId) {
    // requestTraceId không có trong Redis để framework khôi phục.
}
~~~

Trong ví dụ chính, constructor không tham số cùng các field có thể gán cho phép mapping thực hiện đơn giản. Nếu thiết kế entity bất biến, hãy đảm bảo persistence constructor hoặc factory chỉ yêu cầu dữ liệu mà mapper có thể cung cấp, đồng thời tính giá trị tạm thời sau khi dựng object hoặc bên ngoài entity.

### Đặt annotation trên thuộc tính được Spring Data nhận diện

Đối với cách khai báo field như `CustomerProfile`, đặt `@Transient` ngay trên field cần bỏ qua là rõ ràng nhất. Nếu dự án sử dụng property access, constructor binding hoặc mapping tùy biến, phải xác định annotation được đặt trên đúng property mà Spring Data phát hiện; đừng đánh dấu một phương thức không liên quan rồi kỳ vọng một field khác biến mất khỏi Redis.

Nếu vô tình khai báo hai trạng thái khác nhau, chẳng hạn field `displayBadge` và một property khác được getter/setter ánh xạ độc lập, cần làm rõ accessor tương ứng với property nào.

### Đừng hiểu `@Transient` là bảo vệ dữ liệu nhạy cảm

Annotation giúp bỏ qua một field ở **đường lưu sử dụng Spring Data mapping**; nó không mã hóa dữ liệu, không ngăn log, không ngăn REST serialization, và không bảo đảm các serializer khác bỏ qua field đó. Với dữ liệu nhạy cảm, vẫn cần thiết kế DTO, cấu hình log, quản lý quyền truy cập và chính sách lưu trữ phù hợp.

## 8. Khi thay đổi entity đã có dữ liệu trong Redis

Giả sử phiên bản cũ từng lưu `displayBadge`, sau đó mới thêm `@Transient`:

~~~java
@Transient
private String displayBadge;
~~~

Kể từ khi code sử dụng mapper mới, các lần ghi tiếp theo sẽ bỏ qua property đó. Nhưng **annotation không tự chạy một migration xóa field cũ khỏi mọi Redis Hash đã tồn tại**. Cần phân biệt rõ:

1. **Cách ánh xạ mới**: thuộc tính không còn được xem là dữ liệu bền vững.
2. **Dữ liệu vật lý cũ**: key đã có trong Redis có thể vẫn còn field cũ cho đến khi được ghi lại, xóa, hết hạn hoặc được dọn bằng migration riêng.

Nếu cần loại bỏ hoàn toàn dữ liệu cũ, lên kế hoạch dọn theo keyspace và vòng đời dữ liệu thực tế. Đặc biệt với dữ liệu hết hạn bằng TTL, cần cân nhắc liệu chờ key tự hết hạn có đủ hay không. Không sử dụng lệnh xóa toàn bộ database chỉ để xử lý một thuộc tính.

`@Transient` cũng **không tự điều chỉnh TTL** của key. Thời gian sống được điều khiển bằng cấu hình Redis Hash, `@RedisHash(timeToLive = ...)`, cơ chế `@TimeToLive` hoặc thao tác Redis tương ứng; đó là một mối quan tâm khác với việc loại bỏ property khỏi dữ liệu lưu.

## 9. Những lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Field vẫn xuất hiện trong REST JSON | `@Transient` chỉ áp dụng cho Spring Data mapping | Dùng DTO, `@JsonIgnore` hoặc cấu hình Jackson nếu muốn điều chỉnh JSON |
| Field vẫn có giá trị ngay sau `save` | Object đang dùng vẫn là instance trong bộ nhớ | Tải lại entity bằng `findById` để kiểm tra trạng thái đã lưu |
| Field xuất hiện trong payload `opsForValue().set(...)` | Lưu bằng serializer khác với Redis Repository | Kiểm tra `RedisSerializer` thực tế |
| Đọc từ Redis thấy field transient là `null` | Không có dữ liệu để khôi phục | Tính lại hoặc thiết lập sau khi đọc nếu nghiệp vụ cần |
| Redis cũ vẫn có field từng được lưu | Chưa dọn key/Hash từ phiên bản trước | Xác định chính sách migration hoặc TTL |
| Repository không thể truy vấn field transient | Field không có mặt trong mô hình dữ liệu lưu/index | Truy vấn bằng thuộc tính bền vững hoặc đổi mô hình lưu |
| Constructor khôi phục thất bại | Constructor yêu cầu dữ liệu thuộc property bị bỏ qua | Thiết kế persistence constructor phù hợp |
| Dùng nhầm annotation từ thư viện khác | Import không đúng `org.springframework.data.annotation.Transient` | Kiểm tra import và cấu hình mapper |

## 10. Nguyên tắc thiết kế

Khi quyết định đánh dấu một property bằng `@Transient`, hãy đặt câu hỏi: **Nếu tạo một entity mới chỉ từ Redis, có cần và có thể tái tạo giá trị của property này không?**

- Nếu thuộc tính là dữ liệu nghiệp vụ cần giữ qua nhiều request, nên lưu nó bằng một cơ chế persistence thích hợp.
- Nếu thuộc tính có thể tính lại từ dữ liệu đã lưu, có thể đánh dấu transient và tính khi đọc/sử dụng.
- Nếu thuộc tính chỉ phục vụ request hoặc hiển thị, có thể không lưu và thậm chí chuyển sang DTO/context riêng.
- Nếu thuộc tính cần truy vấn, lập chỉ mục hoặc tham gia quan hệ dữ liệu trong Redis, phải thiết kế nó như dữ liệu lưu trữ thực sự.

Với Spring Data Redis Repository, `@Transient` là công cụ đơn giản để giữ Redis Hash tập trung vào trạng thái nghiệp vụ cần tồn tại. Cách dùng đúng là **đánh dấu rõ property**, **kiểm tra bằng một lần ghi và đọc lại**, và **phân biệt đường mapping entity với JSON/cache/value serialization**. Nhờ đó, đối tượng Java vẫn linh hoạt cho tính toán tạm thời trong khi dữ liệu Redis tránh bị phình to hoặc mang theo trạng thái đã lỗi thời.
