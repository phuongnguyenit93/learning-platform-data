# Tổ chức mã cấu hình, dịch vụ và Repository

## 1. Mục tiêu của cách tổ chức mã Spring Data Redis

Khi mới kết nối Redis với Spring Boot, ta có thể viết toàn bộ logic trong một controller: đọc cấu hình Redis, tạo client, ghép tên key, gọi lệnh Redis, chuyển dữ liệu và trả HTTP response. Cách này có thể hoạt động với một ví dụ nhỏ, nhưng nhanh chóng khó bảo trì khi nhiều tính năng cùng truy cập Redis.

Với Spring Data Redis, nên xác định ba ranh giới chính:

- **Configuration (cấu hình):** xây dựng và cấu hình các thành phần hạ tầng như kết nối, template, serializer và thuộc tính dành riêng cho Redis.
- **Repository (truy cập dữ liệu):** cung cấp cách lưu, tìm, xóa dữ liệu; có thể là repository do Spring Data tự triển khai hoặc adapter tự viết trên RedisTemplate.
- **Service (nghiệp vụ):** quyết định khi nào cần đọc/ghi, dữ liệu nào hợp lệ, thao tác nào phải phối hợp với nhau và kết quả nào trả về cho phần còn lại của ứng dụng.

Ở ngoài ba tầng này thường còn có **domain/model** (định nghĩa dữ liệu) và **controller/handler** (nhận request, chuyển dữ liệu ra/vào HTTP hoặc message).

~~~text
                HTTP / Message / Scheduler
                           |
                           v
                Controller / Handler
                - request / response
                - giao thức bên ngoài
                           |
                           v
                     Service
                - quy tắc nghiệp vụ
                - phối hợp các thao tác
                           |
             +-------------+--------------+
             |                            |
             v                            v
    Spring Data Repository       RedisTemplate Adapter
    - CRUD đối tượng              - command Redis cụ thể
    - mapping @RedisHash          - key / TTL / counter / script
             |                            |
             +-------------+--------------+
                           |
                           v
               ConnectionFactory / Redis
               - kết nối, xác thực, topology
               - serialization / driver
~~~

Sơ đồ trên thể hiện chiều phụ thuộc phổ biến. **Service không cần biết địa chỉ Redis, chi tiết Lettuce connection hoặc serializer của từng giá trị**; những yếu tố đó thuộc tầng cấu hình và truy cập dữ liệu.

## 2. Phân biệt cấu hình, service và repository bằng trách nhiệm

| Thành phần | Chịu trách nhiệm | Không nên chịu trách nhiệm |
|---|---|---|
| **Configuration** | Bean connection factory, template, serializer, cấu hình connection, property binding | Xử lý đơn hàng, kiểm tra quyền sửa hồ sơ, quyết định nghiệp vụ |
| **Repository** | Lưu và truy xuất dữ liệu Redis theo một hợp đồng rõ ràng | Quyết định luồng HTTP, trả mã 404, định dạng response |
| **Service** | Quy tắc nghiệp vụ, validation liên quan nghiệp vụ, phối hợp repository | Tạo Redis connection mỗi request, viết URL Redis hoặc credentials cố định |
| **Domain/Model** | Cấu trúc thực thể, dữ liệu và ý nghĩa thuộc tính | Gọi Redis trong getter/setter |
| **Controller** | Nhận input, chuyển sang service, chuyển kết quả ra HTTP | Tự viết Redis command hoặc tự quản lý Redis key |

Ví dụ nghiệp vụ: “Tạo hồ sơ khách hàng và lưu vào Redis”.

1. Controller nhận **email** và **displayName**.
2. Service xác định định dạng hợp lệ, tạo ID và gọi repository lưu.
3. Repository chuyển thực thể sang dữ liệu Redis bằng mapping của Spring Data.
4. Connection factory và driver gửi lệnh tới Redis.
5. Service nhận kết quả và controller chuyển thành response.

Nếu một ngày thay Redis bằng nguồn lưu khác hoặc thêm database làm nguồn dữ liệu chính, phần cần xem xét chủ yếu là hợp đồng lưu trữ và tầng infrastructure. Ngược lại, nếu API thay đổi từ HTTP sang message consumer, service có thể được giữ nguyên.

## 3. Cấu trúc thư mục mẫu cho một Spring Boot application

Ví dụ ứng dụng theo package **com.example.customer**:

~~~text
src/main/java/com/example/customer/
├── CustomerApplication.java
├── config/
│   ├── RedisClientConfig.java            # Chỉ khi cần custom template
│   └── RedisKeyNames.java                # Quy tắc tên key cho command Redis
├── domain/
│   └── CustomerProfile.java              # Model lưu bằng Redis Repository
├── repository/
│   └── CustomerProfileRepository.java    # Hợp đồng CRUD/query
├── service/
│   ├── CustomerProfileService.java       # Nghiệp vụ hồ sơ
│   └── PageViewService.java              # Nghiệp vụ đếm lượt xem
└── web/
    └── CustomerProfileController.java   # HTTP API

src/main/resources/
└── application.yml
~~~

Đây là một cách tổ chức theo tầng cho ứng dụng vừa và nhỏ; không bắt buộc mọi project phải có đúng tên thư mục này. Với hệ thống lớn, có thể nhóm theo feature, chẳng hạn **customer/**, **session/**, **metrics/**, và đặt **config/** ở phần dùng chung. Điều quan trọng là mỗi thành phần giữ trách nhiệm nhất quán.

Lớp **CustomerApplication** nên nằm ở package cha để cơ chế component scanning của Spring Boot tìm được các **@Configuration**, **@Service**, **@RestController** và repository dưới các package con:

~~~java
package com.example.customer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomerApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomerApplication.class, args);
    }
}
~~~

Đặt các package phân tán ngoài phạm vi scan mà không cấu hình bổ sung là nguyên nhân thường gặp khiến Spring không tìm thấy bean.

## 4. Khởi tạo dependency và cấu hình kết nối

### 4.1. Dependency

Một ứng dụng Spring Boot dùng Redis theo kiểu imperative thường khai báo starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**spring-boot-starter-data-redis** tích hợp Spring Data Redis và driver Redis phù hợp với cấu hình Spring Boot, mặc định phổ biến là Lettuce. Starter web chỉ cần khi ví dụ có HTTP controller; ứng dụng worker hoặc CLI không nhất thiết cần nó.

Không tự khai báo đồng thời nhiều phiên bản thư viện Spring Data Redis, Lettuce và Spring Boot khác nhau nếu đã dùng quản lý dependency của Spring Boot, trừ khi có yêu cầu tương thích được kiểm soát.

### 4.2. application.yml

Ví dụ ứng dụng kết nối Redis local:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Thông tin như host, port, TLS, credential, timeout và Cluster/Sentinel topology nên được truyền qua môi trường triển khai hoặc cơ chế cấu hình của ứng dụng. Không đưa mật khẩu thật vào file source.

Trong cấu hình thông thường, Spring Boot tự cung cấp **RedisConnectionFactory**, **RedisTemplate** và **StringRedisTemplate** khi đủ điều kiện auto-configuration. Vì vậy **không cần tạo LettuceConnectionFactory bằng tay chỉ để thực hiện CRUD cơ bản**.

Những trường hợp nên thêm configuration class riêng gồm: cần serializer được chỉ định rõ, nhiều template ứng với các định dạng dữ liệu khác nhau, tùy chỉnh driver/connection hoặc quy tắc infrastructure khác chưa được đáp ứng qua properties.

### 4.3. Phạm vi của RedisConnectionFactory

~~~text
application.yml
   |
   v
Spring Boot auto-configuration
   |
   v
LettuceConnectionFactory
   |-- RedisTemplate<String, ...>
   |-- StringRedisTemplate
   +-- Spring Data Redis repositories
   |
   v
Redis server
~~~

**RedisConnectionFactory** là abstraction cấp hạ tầng cho truy cập Redis đồng bộ. Nó cung cấp connection cho template và cơ chế mapping repository. Factory nên có vòng đời do Spring quản lý, không được khởi tạo mới trong mỗi lần gọi service.

**RedisTemplate** cung cấp API mức cao để thao tác Redis và sử dụng serializer. **StringRedisTemplate** chuyên dùng key/value dạng chuỗi, thường dễ dùng cho counter và flag. Việc inject một template không tự yêu cầu service quản lý connection hay giải phóng connection thủ công.

## 5. Tổ chức domain model với Redis Repository

Spring Data Redis hỗ trợ cơ chế **key-value repository** cho đối tượng được mapping bằng các annotation như **@RedisHash** và **@Id**.

Xét thực thể hồ sơ khách hàng:

~~~java
package com.example.customer.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customer_profile")
public class CustomerProfile {
    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;

    public CustomerProfile() {
    }

    public CustomerProfile(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Ý nghĩa các annotation:

| Annotation | Vai trò |
|---|---|
| **@RedisHash("customer_profile")** | Khai báo thực thể lưu trong Redis keyspace có tên **customer_profile**. |
| **@Id** | Đánh dấu định danh thực thể, dùng để tạo khóa lưu trữ. |
| **@Indexed** | Yêu cầu Spring Data Redis duy trì chỉ mục phụ cho truy vấn theo thuộc tính được đánh dấu. |

Khi lưu một đối tượng có ID **42**, Spring Data Redis thường sử dụng key thuộc keyspace kiểu **customer_profile:42** để lưu hash và có thể tạo thêm dữ liệu metadata/index. Đây **không phải** một chuỗi JSON được lưu bằng lệnh **SET** thông thường. Vì vậy việc thử đọc cùng key bằng **StringRedisTemplate.opsForValue().get(...)** có thể gặp lỗi Redis **WRONGTYPE**; muốn đọc đối tượng đã mapping nên dùng repository tương ứng.

Đánh dấu **@Indexed** không tạo ràng buộc unique. Hai đối tượng vẫn có thể cùng **email** nếu ứng dụng không có cơ chế bảo đảm duy nhất riêng. Chỉ mục này cũng phát sinh dữ liệu phụ và chi phí cập nhật; chỉ tạo khi có nhu cầu truy vấn.

Model cho repository là cách biểu diễn dữ liệu lưu trữ. Với ứng dụng lớn, có thể tách **storage entity** khỏi **domain model** và DTO công khai để tránh làm định dạng HTTP phụ thuộc trực tiếp vào schema Redis.

## 6. Tạo Redis Repository: tập trung vào truy cập dữ liệu

Interface repository kế thừa một hợp đồng của Spring Data:

~~~java
package com.example.customer.repository;

import com.example.customer.domain.CustomerProfile;
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {

    List<CustomerProfile> findByEmail(String email);
}
~~~

Đây là interface; với cấu hình repository thích hợp, Spring Data Redis tạo implementation lúc ứng dụng khởi động. Các phương thức phổ biến:

- **save(entity)**: lưu hoặc cập nhật thực thể theo ID.
- **findById(id)**: nhận **Optional<CustomerProfile>**.
- **existsById(id)**: kiểm tra một ID.
- **deleteById(id)**: xóa thực thể.
- **findByEmail(email)**: truy vấn theo thuộc tính được chỉ mục.

Chú ý: khả năng suy diễn query trong **Redis Repository** không tương đương với hệ thống query SQL/JPA. Redis không phải database quan hệ, không có join và không tự giải quyết các truy vấn phức tạp chỉ nhờ đổi tên method. Query theo thuộc tính cần được hỗ trợ bởi cơ chế index/mapping của Spring Data Redis.

### Khi nào phải dùng @EnableRedisRepositories?

Trong ứng dụng Spring Boot đặt package đúng và dùng starter tương ứng, auto-configuration thường phát hiện và kích hoạt Redis repositories. Không nên thêm annotation cấu hình thủ công chỉ vì muốn một interface hoạt động.

Khi cần chỉ định package scan hoặc có nhiều module/config phức tạp, có thể cấu hình tường minh:

~~~java
package com.example.customer.config;

import com.example.customer.repository.CustomerProfileRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(basePackageClasses = CustomerProfileRepository.class)
public class RedisRepositoryConfig {
}
~~~

Chỉ thêm cấu hình này khi thực sự cần kiểm soát phạm vi quét. Tránh khai báo nhiều cấu hình repository trùng nhau dẫn đến xung đột bean hoặc đăng ký lặp.

## 7. Đưa quy tắc nghiệp vụ vào Service

Service nhận repository qua constructor injection và cung cấp hành vi có nghĩa ở tầng ứng dụng:

~~~java
package com.example.customer.service;

import com.example.customer.domain.CustomerProfile;
import com.example.customer.repository.CustomerProfileRepository;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {
    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public CustomerProfile create(String email, String displayName) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Display name is required");
        }

        CustomerProfile profile = new CustomerProfile(
            UUID.randomUUID().toString(),
            email,
            displayName
        );
        return repository.save(profile);
    }

    public Optional<CustomerProfile> findById(String id) {
        return repository.findById(id);
    }

    public CustomerProfile rename(String id, String newDisplayName) {
        if (newDisplayName == null || newDisplayName.isBlank()) {
            throw new IllegalArgumentException("Display name is required");
        }

        CustomerProfile profile = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Profile not found"));

        profile.setDisplayName(newDisplayName);
        return repository.save(profile);
    }
}
~~~

Service không cần biết **customer_profile:42** được Redis lưu bằng hash ra sao, không tự chuyển POJO thành bytes, và không tạo Redis connection. Chức năng tạo ID, kiểm tra input và phối hợp tìm/sửa/lưu đã được đặt ở vị trí có thể dùng lại từ HTTP controller, scheduled job hoặc message handler.

Ví dụ **rename** là quy trình đọc rồi ghi, nên có thể gặp **lost update** khi nhiều request sửa cùng một hồ sơ. Việc tách service và repository **không tự bảo đảm tính nguyên tử cho nghiệp vụ**; nếu cần kiểm soát cập nhật đồng thời, phải chọn cơ chế điều kiện phiên bản hoặc command/script Redis phù hợp với contract dữ liệu. Đồng thời, kiểm tra “email không trùng” chỉ bằng **findByEmail** rồi **save** cũng có race condition; **@Indexed** không phải unique constraint.

Khi service ngày càng phức tạp, nên tách các quy tắc nghiệp vụ thành phương thức hoặc đối tượng có tên rõ nghĩa, nhưng không biến repository thành nơi chứa toàn bộ điều kiện nghiệp vụ.

## 8. Controller chỉ tiếp nhận request và trả kết quả

HTTP layer gọi service, chuyển **Optional.empty()** thành **404** và xây dựng response:

~~~java
package com.example.customer.web;

import com.example.customer.domain.CustomerProfile;
import com.example.customer.service.CustomerProfileService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class CustomerProfileController {
    private final CustomerProfileService service;

    public CustomerProfileController(CustomerProfileService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerProfile> create(
            @RequestBody CreateProfileRequest request) {
        CustomerProfile saved = service.create(
            request.email(),
            request.displayName()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    @GetMapping("/{id}")
    public ResponseEntity<CustomerProfile> get(@PathVariable String id) {
        return ResponseEntity.of(service.findById(id));
    }

    public record CreateProfileRequest(
        String email,
        String displayName
    ) {}
}
~~~

Controller không dùng **RedisTemplate** hoặc gọi trực tiếp **repository.save()**. Khi cần thêm quy tắc kiểm tra và phối hợp nhiều nguồn dữ liệu, có thể chỉnh service mà không khiến HTTP layer trở thành nơi tập trung nghiệp vụ.

Ví dụ tập trung vào cấu trúc tầng. Ở ứng dụng thực tế cần quy định DTO response riêng, xử lý validation/error bằng cơ chế phù hợp, cùng chính sách xác thực và quyền truy cập.

## 9. Khi nào dùng RedisTemplate thay cho Redis Repository?

Không phải dữ liệu Redis nào cũng nên được ánh xạ thành một entity với **CrudRepository**.

Ví dụ “tăng số lượt xem” thực chất là một lệnh Redis **INCR**; tạo cả một entity để biểu diễn counter có thể làm code phức tạp không cần thiết.

Service dùng **StringRedisTemplate**:

~~~java
package com.example.customer.service;

import com.example.customer.config.RedisKeyNames;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PageViewService {
    private final StringRedisTemplate redis;

    public PageViewService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long registerView(String pageId) {
        return redis.opsForValue().increment(
            RedisKeyNames.pageViews(pageId)
        );
    }
}
~~~

**INCR** tăng số một cách nguyên tử trong một Redis command. Với counter, cách này diễn đạt mục đích rõ hơn **GET → chuyển sang long → cộng một → SET**, vốn có thể mất cập nhật khi nhiều request chạy đồng thời.

Tách quy tắc tên key:

~~~java
package com.example.customer.config;

public final class RedisKeyNames {
    private RedisKeyNames() {
    }

    public static String pageViews(String pageId) {
        if (pageId == null || pageId.isBlank()) {
            throw new IllegalArgumentException("Page id is required");
        }
        return "page:views:" + pageId;
    }
}
~~~

Giữ key prefix ở một nơi giúp service không sao chép nhiều chuỗi như **"page:views:"**, nhất là khi các feature cần thống nhất TTL, namespace hoặc cách biểu diễn ID.

**Lưu ý:** chuỗi key do chính service quản lý qua template và keyspace của repository không nhất thiết có cùng cách tổ chức. Tránh dùng hai cơ chế cùng ghi vào một key nếu chưa thiết kế rõ Redis data type, serializer và nguồn chịu trách nhiệm cập nhật.

### Bảng chọn abstraction

| Nhu cầu | Công cụ thường phù hợp | Lý do |
|---|---|---|
| CRUD một đối tượng theo ID | **RedisRepository/CrudRepository** với **@RedisHash** | Mapping thực thể và các thao tác lưu/truy xuất có sẵn |
| Tra cứu theo trường đã index | **Redis Repository** với **@Indexed** | Tích hợp secondary index của Spring Data Redis |
| Bộ đếm, flag, key string có TTL | **StringRedisTemplate** | Gọi trực tiếp các command Redis đơn giản |
| List/set/zset, hash theo cấu trúc tùy biến | **RedisTemplate** | Kiểm soát command và dữ liệu Redis |
| Lua script, thao tác nguyên tử theo điều kiện | **RedisTemplate.execute(...)** hoặc adapter chuyên biệt | Điều khiển cách Redis thực thi nghiệp vụ gần dữ liệu |
| Cache kết quả method theo key | **Spring Cache abstraction** nếu phù hợp | Ngữ nghĩa cache tách khỏi kho thực thể |
| Ứng dụng reactive/WebFlux | **ReactiveRedisTemplate** / **ReactiveStringRedisTemplate** | Publisher **Mono/Flux** và đường I/O non-blocking |

Redis repository của Spring Data Redis theo mô hình thông dụng là **imperative**. Không nên inject một **CrudRepository** đồng bộ rồi gọi trực tiếp trên event-loop WebFlux và nghĩ rằng nó tự trở thành non-blocking. Nếu toàn bộ ứng dụng đã dùng Reactor, hãy chọn các API reactive phù hợp và đặt ranh giới rõ ràng với nguồn dữ liệu còn blocking.

## 10. Viết adapter repository riêng khi cần che giấu RedisTemplate

Đôi khi nghiệp vụ cần nhiều command Redis nhưng không muốn mọi service biết key format. Khi đó có thể tự định nghĩa một **port/interface** theo ngôn ngữ nghiệp vụ, rồi triển khai bằng RedisTemplate.

Ví dụ bộ đếm:

~~~java
package com.example.customer.repository;

public interface PageViewCounter {
    long increment(String pageId);
}
~~~

~~~java
package com.example.customer.repository;

import com.example.customer.config.RedisKeyNames;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RedisPageViewCounter implements PageViewCounter {
    private final StringRedisTemplate redis;

    public RedisPageViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public long increment(String pageId) {
        Long result = redis.opsForValue()
            .increment(RedisKeyNames.pageViews(pageId));

        if (result == null) {
            throw new IllegalStateException("Redis returned no counter value");
        }
        return result;
    }
}
~~~

Sau đó, **PageViewService** có thể phụ thuộc **PageViewCounter** thay vì trực tiếp **StringRedisTemplate**:

~~~java
@Service
public class PageViewService {
    private final PageViewCounter counter;

    public PageViewService(PageViewCounter counter) {
        this.counter = counter;
    }

    public long registerView(String pageId) {
        return counter.increment(pageId);
    }
}
~~~

Trong ví dụ cuối, các import của **PageViewService** tương ứng gồm **PageViewCounter** và **org.springframework.stereotype.Service**.

Không cần tạo interface cho mọi lệnh Redis ở ứng dụng rất nhỏ. Adapter riêng hữu ích khi logic key/TTL/serialization dùng lại ở nhiều nơi, cần thay implementation, hoặc muốn kiểm soát rõ quyền truy cập Redis của các service. Còn **Spring Data Redis Repository** đã là một abstraction được framework triển khai, nên không cần bọc thêm một tầng chỉ để chuyển tiếp mọi lời gọi **save/findById**.

## 11. Đặt serializer ở tầng cấu hình

Redis lưu các chuỗi byte. Nếu hai service cùng truy cập một key nhưng dùng serializer khác nhau, service đọc có thể không giải mã được dữ liệu hoặc gặp lỗi kiểu Redis.

Khi ứng dụng chỉ thao tác với chuỗi, **StringRedisTemplate** thường đủ. Khi lưu dữ liệu bằng template tùy biến, có thể định nghĩa một bean riêng:

~~~java
package com.example.customer.config;

import com.example.customer.domain.CustomerProfile;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisClientConfig {
    @Bean("profileJsonRedisTemplate")
    public RedisTemplate<String, CustomerProfile> profileJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, CustomerProfile> template =
            new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
            new Jackson2JsonRedisSerializer<>(CustomerProfile.class)
        );
        template.afterPropertiesSet();
        return template;
    }
}
~~~

Đây là **một cách lưu CustomerProfile thành JSON value qua RedisTemplate**, dành cho key do template này quản lý. Nó **khác với** cách **@RedisHash** mapping cùng class vào Redis hash bằng Redis Repository ở phần trước. Nếu chọn cách JSON này cho một feature, cần đặt keyspace tách biệt và xác định một cơ chế sở hữu dữ liệu, thay vì để repository và template đồng thời cập nhật cùng một key.

Tại vị trí sử dụng, khi có nhiều bean template kiểu khác nhau hoặc type erasure khiến lựa chọn bean không rõ ràng, đặt tên bean và dùng **@Qualifier("profileJsonRedisTemplate")** giúp xác định chính xác instance/serializer.

### Các câu hỏi về serializer trước khi chạy production

1. Key là **String**, binary hay một kiểu mã hóa khác?
2. Value là chuỗi, hash hay JSON?
3. Nếu đổi trường trong DTO, phiên bản mới có đọc được dữ liệu phiên bản cũ không?
4. Có client/ngôn ngữ khác cùng truy cập key không?
5. TTL, data type và serialization có thống nhất giữa các lần ghi không?

Các câu hỏi này thuộc thiết kế hạ tầng lưu trữ; business service không nên tự tạo **ObjectMapper** và tự chuyển bytes cho mỗi request.

## 12. Ranh giới transaction và tính nguyên tử

Việc tổ chức mã thành controller → service → repository chỉ giải quyết **separation of concerns**, không tự bảo đảm transaction Redis.

Ví dụ:

~~~java
public void transferPoints(String fromId, String toId, long amount) {
    // Đọc điểm người gửi.
    // Trừ điểm người gửi rồi lưu.
    // Cộng điểm người nhận rồi lưu.
}
~~~

Nếu hai thao tác lưu là hai chuỗi Redis command riêng biệt, một lỗi giữa chừng có thể khiến trạng thái thiếu nhất quán. Đặt tất cả code trong một method service cũng không làm Redis tự rollback các lệnh đã thành công.

Đặc biệt:

- **INCR/DECRBY** là command nguyên tử đối với phép thay đổi bộ đếm riêng lẻ.
- **MULTI/EXEC** thực thi các command đã queue liền nhau, không bị client khác chen vào; Redis không rollback toàn bộ sau lỗi runtime ở một lệnh.
- **WATCH + MULTI/EXEC** giúp phát hiện key đã đổi giữa đọc và ghi, nhưng cần retry có giới hạn và quản lý cùng connection/session.
- **Lua script/Redis Function** có thể đặt cả điều kiện và thay đổi vào một lần thực thi phía Redis, nhưng script cũng không có rollback tự động cho những lệnh đã thành công trước khi phát sinh lỗi.
- **@Transactional** của Spring không tự biến thao tác Redis và SQL thành distributed transaction nguyên tử. Hỗ trợ Redis transaction còn phụ thuộc cấu hình template, transaction manager và cách sử dụng.

Khi thiết kế service, xác định rõ **điều kiện nào cần kiểm tra**, **những key nào cần thay đổi** và **kết quả lỗi có cần retry/compensate không**. Đưa logic nguyên tử xuống đúng tầng data adapter khi cần; service vẫn chịu trách nhiệm quyết định nghiệp vụ.

Trong Redis Cluster, lệnh nhiều key và script thường bị ràng buộc bởi **hash slot**. Cấu trúc package tốt không giải quyết được việc key nằm trên các node khác nhau.

## 13. Tổ chức TTL, keyspace và vòng đời dữ liệu

TTL không phải chi tiết nhỏ có thể tùy tiện bổ sung sau khi triển khai. Nó quyết định thời gian dữ liệu còn tồn tại và nhiều hành vi của nghiệp vụ.

### Entity với @RedisHash

Một thực thể có thể đặt thời hạn mặc định:

~~~java
@RedisHash(value = "login_session", timeToLive = 1800)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    public LoginSession() {
    }

    public LoginSession(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }
}
~~~

Trong ví dụ, **timeToLive = 1800** là thời hạn bằng giây. Một số model có thể dùng **@TimeToLive** trên property để kiểm soát TTL theo từng thực thể. Nếu logic cần refresh thời hạn ở một thời điểm cụ thể, service phải xác định điều kiện refresh và adapter phải hiện thực bằng lệnh phù hợp.

Khi dùng Spring Data Redis secondary index và expiration event, hành vi làm sạch index và thông báo hết hạn phụ thuộc cấu hình Redis/Spring Data Redis; không nên xem Redis Pub/Sub event là hàng đợi thông báo bền vững. Dữ liệu hết hạn cũng có thể bị loại bỏ theo cơ chế expiration của Redis, nên không thiết kế nghiệp vụ dựa trên giả định event đến đúng giây.

### Key do RedisTemplate quản lý

~~~java
redis.opsForValue().set(
    "verification:code:" + requestId,
    code,
    java.time.Duration.ofMinutes(5)
);
~~~

Sử dụng thao tác **set(key, value, timeout)** để ghi và gắn TTL trong cùng command phù hợp hơn việc **SET** trước rồi **EXPIRE** sau khi muốn tránh key tồn tại vô thời hạn nếu ứng dụng dừng giữa hai bước.

Chọn keyspace và TTL nên xuất phát từ semantics dữ liệu:

| Dữ liệu | Ví dụ keyspace | Quyết định cần đặt ra |
|---|---|---|
| Hồ sơ dạng repository | **customer_profile** | Dữ liệu có phải nguồn chính hay chỉ bản sao tạm? |
| Phiên đăng nhập | **login_session** | TTL, gia hạn phiên, revoke |
| Bộ đếm lượt xem | **page:views:{id}** | Có reset định kỳ hay giữ lâu dài? |
| Marker/idempotency | **request:dedupe:{id}** | Khi nào một request được phép xử lý lại? |
| Cache kết quả | **cache:{feature}:{key}** | TTL, cache invalidation, dữ liệu nguồn |

Đừng dùng key prefix của một tính năng cho dữ liệu tính năng khác chỉ vì cùng kiểu value; điều này khiến xóa hàng loạt, đổi schema và điều chỉnh TTL khó kiểm soát.

## 14. Phân biệt Spring Data Repository với Spring Cache

**Repository** định nghĩa cách lưu và đọc một thực thể trong kho dữ liệu. Nếu Redis là data store của entity, repository là một interface truy cập dữ liệu.

**Spring Cache** định nghĩa hành vi cache kết quả tính toán hoặc kết quả method. Redis có thể là backend cho cache, nhưng **@Cacheable** không đồng nghĩa với **@RedisHash** hay repository.

~~~java
@Cacheable(cacheNames = "productLookup", key = "#productId")
public ProductDto getProduct(String productId) {
    return productDatabase.load(productId);
}
~~~

Ví dụ trên chỉ minh họa chỗ sử dụng cache; class **ProductDto** và **productDatabase** thuộc một feature riêng. Để hoạt động với Redis, cần bật và cấu hình Spring Cache/Redis cache manager tương ứng.

Nếu đã sử dụng cache abstraction, không nên tự ý dùng Redis repository sửa cùng key cache mà framework quản lý. Ngược lại, repository không tự giải quyết cache invalidation của dữ liệu nguồn. Tách hai khái niệm giúp chọn lifecycle phù hợp: cache có thể xóa rồi tải lại, còn entity là dữ liệu nghiệp vụ cần quy tắc tồn tại/đồng bộ rõ ràng.

## 15. Kiểm thử theo từng ranh giới

Cấu trúc này cũng làm cách kiểm thử rõ ràng:

**Service unit test:** mock **CustomerProfileRepository**, xác nhận quy tắc nghiệp vụ như input rỗng bị từ chối và service gọi đúng operation. Không cần mở Redis để kiểm tra phần logic thuần Java.

**Repository integration test:** dùng một Redis instance thử nghiệm để xác nhận **save/findById**, **findByEmail** với secondary index, serializer, TTL và keyspace thực tế. Mock không thể chứng minh Spring Data mapping/driver hoạt động đúng.

**Controller test:** kiểm tra mapping request/response, HTTP status, và việc controller chuyển dữ liệu tới service. Không cần sao chép toàn bộ logic Redis vào controller test.

**End-to-end test:** xác nhận một luồng đi qua HTTP đến Redis và kiểm tra những tình huống cần quan sát ở cấp hệ thống như xóa key, ngắt kết nối, retry hoặc thao tác đồng thời quan trọng.

Các phép kiểm tra này là trách nhiệm của quy trình phát triển ứng dụng. Việc chỉ tạo repository interface chưa đủ để chứng minh cách mapping dữ liệu, secondary indexes và serializer tương thích với Redis đang vận hành.

## 16. Những sai lầm tổ chức mã thường gặp

### 16.1. Controller gọi Redis trực tiếp

~~~java
@GetMapping("/views/{id}")
public Long views(@PathVariable String id) {
    return redis.opsForValue().increment("page:views:" + id);
}
~~~

Khi thêm quy tắc chống spam view, TTL hoặc đổi key prefix, controller sẽ phải kiêm thêm trách nhiệm dữ liệu và nghiệp vụ. Nên đặt những quyết định này vào service và adapter.

### 16.2. Mỗi service tự tạo Redis connection

~~~java
// Không tạo factory mới cho từng request/service call:
LettuceConnectionFactory factory = new LettuceConnectionFactory();
factory.afterPropertiesSet();
~~~

Đoạn này bỏ qua cách Spring Boot quản lý cấu hình, resource và vòng đời bean. Thay vào đó, inject một template hoặc repository đã được Spring tạo.

### 16.3. Repository chứa logic HTTP

Repository không nên trả **ResponseEntity**, nhận **HttpServletRequest** hoặc quyết định mã HTTP 404. Đây là chi tiết của adapter web.

### 16.4. Service ghép key và chọn serializer ở mọi phương thức

Khi cần đổi prefix hoặc định dạng JSON, thay đổi rải khắp nhiều file rất dễ thiếu sót. Đưa key naming và serialization vào configuration/data adapter phù hợp.

### 16.5. Trộn repository mapping với template trên cùng key

**@RedisHash** lưu theo hash/mapping của Spring Data. Một template khác có thể ghi string hoặc JSON bằng **SET** vào cùng key, làm hỏng giả định về Redis data type và metadata. Chọn một owner cho mỗi keyspace, xác định schema và không ghi đè key do framework khác quản lý.

### 16.6. Cho rằng mọi repository đều có query kiểu JPA

**findByEmail** chỉ hoạt động theo cơ chế query/index được Spring Data Redis hỗ trợ. Không thể suy ra khả năng join, transaction nhiều bảng hay ràng buộc unique từ một interface thừa kế **CrudRepository**.

### 16.7. Dùng @Transactional như bảo đảm cho mọi nguồn dữ liệu

Một method lưu Redis rồi ghi SQL vẫn có thể chỉ thành công một phía nếu không có thiết kế nhất quán liên hệ thống. Service cần xác định hệ thống nguồn dữ liệu, cơ chế idempotency và đường phục hồi cụ thể.

## 17. Quy trình thêm một tính năng Redis mới

Giả sử tính năng mới cần lưu **verification code** trong năm phút.

1. **Mô tả dữ liệu và quy tắc:** key được tạo theo request ID, value là code, TTL năm phút; xác định hành vi khi key không tồn tại hoặc bị ghi trùng.
2. **Chọn abstraction:** vì đây là một key/value nhỏ có TTL, dùng **StringRedisTemplate** hoặc adapter tự viết thay vì tạo entity repository nếu không có lợi ích mapping.
3. **Đặt tên key nhất quán:** định nghĩa prefix **verification:code:** trong lớp key naming hoặc adapter.
4. **Viết data adapter khi cần:** triển khai **save(code, ttl)**, **get** và **consume** theo semantics mong muốn. Nếu việc “đọc rồi xóa chỉ một lần” phải nguyên tử, chọn lệnh/cơ chế Redis tương ứng thay vì hai lời gọi rời.
5. **Viết service:** kiểm tra request, quyết định cách phát mã, xác minh và giới hạn số lần thử.
6. **Expose API:** controller chuyển request/response, không biết serializer, key prefix hoặc Redis command.
7. **Kiểm chứng ở tầng thích hợp:** test mapping/key/TTL thực tế và đường lỗi kết nối.

Quy trình này áp dụng tương tự cho session, giới hạn tần suất, bộ đếm và các loại dữ liệu tạm thời. Với các thực thể cần CRUD và truy vấn index, bắt đầu bằng model **@RedisHash** và **CrudRepository**; sau đó thêm service chịu trách nhiệm nghiệp vụ.

## 18. Câu hỏi thực hành

**Câu 1.** Một lớp **OrderController** nhận request rồi dùng **RedisTemplate** gọi **HSET** và **EXPIRE**. Nếu chính sách TTL thay đổi thì nên sửa ở đâu?

**Gợi ý:** Trong service/adapter sở hữu cách lưu dữ liệu, hoặc cấu hình tương ứng, thay vì rải chi tiết Redis vào controller. Nếu mục tiêu là ghi và đặt TTL nguyên tử, cần tìm giải pháp phù hợp với kiểu dữ liệu/hash và hành vi Redis.

**Câu 2.** Hai service cùng đọc một entity **@RedisHash** bằng repository và dùng **StringRedisTemplate.opsForValue().set(...)** để cập nhật key thực tế. Có an toàn không?

**Gợi ý:** Không thể giả định an toàn. Repository mapping dùng Redis hash và có thể có metadata/index riêng; thao tác SET của template khác có thể làm biến đổi Redis type hoặc phá tính nhất quán của mapping. Hãy chọn một cơ chế quản lý keyspace.

**Câu 3.** Một **RedisRepository** có **findByEmail** và thuộc tính **@Indexed**. Điều đó có chắc email là duy nhất không?

**Gợi ý:** Không. Secondary index hỗ trợ lookup, không tự là unique constraint. Cần thiết kế điều kiện ghi nguyên tử nếu nghiệp vụ đòi hỏi duy nhất giữa nhiều request.

**Câu 4.** Vì sao không tạo một **LettuceConnectionFactory** trong constructor của mỗi service?

**Gợi ý:** Service sẽ bị buộc vào kết nối, cấu hình, resources và lifecycle của Redis. Spring Boot đã có cơ chế tạo và quản lý factory/template phù hợp; inject dependency sẽ nhất quán hơn.

**Câu 5.** Ứng dụng WebFlux đang gọi trực tiếp **CrudRepository** trong pipeline. Có phải toàn bộ pipeline trở thành non-blocking?

**Gợi ý:** Không. Repository imperative có thể chặn thread của pipeline. Nếu muốn đường I/O reactive, cần sử dụng Redis API reactive hoặc tổ chức ranh giới blocking một cách chủ động.

## 19. Tổng kết

Trong Spring Data Redis, một thiết kế rõ ràng bắt đầu từ việc **chia trách nhiệm đúng nơi**:

- **Configuration** quản lý kết nối, template, serializer và các thuộc tính hạ tầng.
- **Repository** diễn đạt truy cập dữ liệu, dùng **@RedisHash + CrudRepository** cho entity hoặc adapter trên **RedisTemplate** khi cần command cụ thể.
- **Service** nắm quy tắc nghiệp vụ và cách phối hợp các thao tác.
- **Controller** tiếp nhận và trả kết quả theo giao thức, không chứa thao tác Redis.
- **Domain/Model** mô tả dữ liệu và vòng đời của thực thể.

Điều quan trọng hơn tên package là sự nhất quán: **một keyspace có người sở hữu rõ ràng, một định dạng lưu trữ xác định, một tầng quyết định nghiệp vụ và một ranh giới kết nối do Spring quản lý**. Tách lớp đúng giúp dễ thay đổi, kiểm thử và vận hành, nhưng vẫn phải thiết kế riêng tính nguyên tử, TTL và khả năng xử lý lỗi của Redis.
