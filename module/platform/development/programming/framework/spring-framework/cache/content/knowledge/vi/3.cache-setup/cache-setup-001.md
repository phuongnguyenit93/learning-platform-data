# Các thư viện Spring cần thiết và phụ thuộc nhà cung cấp cache

> Chủ đề: **Thiết lập Spring Cache**. Bài này giải thích phải thêm thư viện nào để dùng các annotation cache của Spring, thư viện nào do cache provider cung cấp, và cách cấu hình dependency đúng cho từng lựa chọn. Ví dụ Maven dùng **Spring Boot 4.1.2, Java 17+**; với dự án đang dùng dòng Spring Boot khác, hãy giữ phiên bản dependency đồng bộ theo BOM/parent của dòng đó.

## Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **Spring Cache abstraction**, **Spring Boot auto-configuration** và **cache provider**.
2. Biết vai trò của `spring-context`, `spring-context-support`, `spring-boot-starter-cache`, cùng các dependency Caffeine, Redis, JCache/Ehcache.
3. Thêm đúng dependency với Maven hoặc Gradle, tránh khai báo trùng và lệch phiên bản.
4. Kích hoạt caching, chọn provider, kiểm tra `CacheManager` thực tế và xử lý những lỗi classpath/cấu hình thường gặp.
5. Chạy một ứng dụng Spring Boot tối thiểu để xác nhận `@Cacheable` thật sự bỏ qua xử lý lặp.

## 1. Hiểu đúng ba lớp trong hệ thống cache

Khi nhìn thấy `@Cacheable`, đừng cho rằng một annotation đã tự tạo bộ nhớ cache hoàn chỉnh. Mô hình có ba lớp:

```text
Phương thức nghiệp vụ
    |
    | @Cacheable / @CacheEvict / @CachePut
    v
Spring Cache abstraction
    |  org.springframework.cache.Cache
    |  org.springframework.cache.CacheManager
    v
Provider/adapter cụ thể
    +-- ConcurrentMapCacheManager --> Map trong JVM
    +-- CaffeineCacheManager ----- > Cache trong JVM của Caffeine
    +-- RedisCacheManager -------- > Redis server
    +-- JCacheCacheManager ------- > JSR-107 provider (ví dụ Ehcache 3)
```

- **Spring Cache abstraction** cung cấp các hợp đồng `Cache`/`CacheManager` và cơ chế annotation để quyết định khi nào đọc, điền hoặc xóa cache.
- **Cache provider** hiện thực cách lưu, trục xuất, hết hạn, đồng bộ và/hoặc truy cập một cache server. Spring không mặc định biến mọi cache thành cache phân tán, có TTL hay có giới hạn dung lượng.
- **Spring Boot auto-configuration** phát hiện các dependency và bean đang có rồi, nếu điều kiện phù hợp, cấu hình `CacheManager` tự động. Trong ứng dụng Spring Framework thuần (không Boot), bạn thường khai báo `CacheManager` bằng `@Bean` hoặc XML.

Hai câu hỏi độc lập cần trả lời trước khi thêm dependency: **(1) ứng dụng tích hợp Spring Cache bằng cách nào?** và **(2) dữ liệu thực tế được cache ở đâu, bởi thư viện nào?**

## 2. Các dependency nền tảng của Spring

| Maven coordinates | Công dụng | Khi nào cần |
| --- | --- | --- |
| `org.springframework:spring-context` | Các API Spring Cache, annotation, `ConcurrentMapCacheManager` và phần hỗ trợ cấu hình cache | Cốt lõi khi dùng Spring Framework thuần; thường đã có qua các starter Spring Boot |
| `org.springframework:spring-context-support` | Các adapter/tích hợp bổ sung, đặc biệt `CaffeineCacheManager` và `JCacheCacheManager` | Khi dùng Caffeine/JCache với dependencies thủ công; `spring-boot-starter-cache` đã mang vào |
| `org.springframework.boot:spring-boot-starter-cache` | Starter để triển khai Spring Cache thuận tiện trong ứng dụng Spring Boot, gồm các thành phần Spring hỗ trợ cache | Cách khai báo nền tảng được khuyến nghị cho ứng dụng Spring Boot |
| `org.springframework.boot:spring-boot-autoconfigure` | Điều kiện và cấu hình tự động của Boot | Thường là phụ thuộc bắc cầu từ starter Boot, không cần thêm thủ công |
| `org.springframework:spring-aop` | Hạ tầng proxy cần cho cơ chế chặn lời gọi phương thức | Thường đã là phụ thuộc bắc cầu của Spring Context/starter; **không đồng nghĩa phải thêm `spring-boot-starter-aop`** chỉ để dùng `@Cacheable` mặc định |

**Điểm mấu chốt:** `spring-boot-starter-cache` giúp có hạ tầng tích hợp; nó **không tự kèm mọi provider**. Để dùng Caffeine, Redis hoặc JCache, bạn còn phải có thư viện provider tương ứng trên runtime classpath. Ngược lại, chỉ thêm `caffeine` mà không có adapter Spring sẽ không làm `@Cacheable` tự hoạt động.

### Những API và lớp thường gặp

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.jcache.JCacheCacheManager;
```

Đây là danh sách **import để nhận diện dependency**; không phải một chương trình độc lập. `CaffeineCacheManager` và `JCacheCacheManager` cần `spring-context-support` cùng API/provider liên quan; không phải mọi ứng dụng đều cần import cả hai.

## 3. Cách 1: Spring Boot + cache đơn giản (để học và thử nghiệm)

Trong ứng dụng Spring Boot đã có parent hoặc BOM quản lý phiên bản, thêm dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
```

Hoặc Gradle Kotlin DSL trong một dự án Boot đã cấu hình dependency management:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-cache")
}
```

Thêm cấu hình Java để bật cơ chế annotation:

```java
@Configuration
@EnableCaching
public class CacheConfig {
}
```

Trong trường hợp không tìm thấy provider chuyên dụng và không có `CacheManager` tự khai báo, Spring Boot có thể chọn **Simple provider**, sử dụng các `ConcurrentMap` trong JVM. Cách này dễ quan sát hit/miss nhưng **không có eviction/TTL sản xuất được cấu hình sẵn**, không chia sẻ cache giữa nhiều tiến trình. Đừng mặc nhiên xem nó là lời giải production.

Chỉ có annotation trên phương thức là chưa đủ nếu chưa bật `@EnableCaching`. Hơn nữa, lời gọi nội bộ bằng `this.method()` trong cùng bean không đi qua Spring proxy ở chế độ mặc định; hãy gọi qua bean do Spring quản lý.

## 4. Cách 2: Spring Boot + Caffeine (in-memory, thường dùng cho một instance)

Caffeine phù hợp khi truy cập cache rất thường xuyên trong cùng JVM, cần giới hạn số mục và chính sách hết hạn, không cần các instance dùng chung giá trị.

### Maven: thêm hai dependency

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</groupId>
        <artifactId>caffeine</artifactId>
    </dependency>
</dependencies>
```

### Gradle Kotlin DSL: hai dependency tương ứng

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-cache")
    implementation("com.github.ben-manes.caffeine:caffeine")
}
```

Ở ứng dụng Boot có BOM, không cần khai báo phiên bản cho những artifact được BOM quản lý. `spring-boot-starter-cache` đã mang `spring-context-support`, nơi có adapter `CaffeineCacheManager`.

Ví dụ `src/main/resources/application.properties`:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=productPrices
spring.cache.caffeine.spec=maximumSize=200,expireAfterWrite=300s
```

- `spring.cache.type=caffeine` chọn rõ provider, tránh phụ thuộc thứ tự auto-detection nếu có nhiều thư viện cache.
- `spring.cache.cache-names=productPrices` khai báo cache dùng trong ví dụ.
- `maximumSize=200` giới hạn số mục theo chính sách của Caffeine.
- `expireAfterWrite=300s` là thời gian hết hiệu lực tính từ lần ghi/cập nhật cache, **không** bảo đảm dữ liệu nguồn mới ngay khi thay đổi.
- Trong các dự án thực tế, cân nhắc TTL, eviction, thống kê hit rate và chiến lược invalidation theo yêu cầu nghiệp vụ.

## 5. Ví dụ hoàn chỉnh, chạy được: Spring Boot + Caffeine

Ví dụ dưới đây tạo đúng **một** provider, không cần Redis server hoặc database. Nó cho thấy cache hoạt động qua Spring proxy. Cấu trúc dự án:

```text
cache-dependencies-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/cache/
        │       ├── CacheApplication.java
        │       ├── CacheConfiguration.java
        │       └── CatalogService.java
        └── resources/
            └── application.properties
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-dependencies-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Parent của Spring Boot quản lý phiên bản của Spring và những dependency thông dụng. Ví dụ dùng Boot 4.1.2 (phát hành tháng 10/2026), nhưng dự án hiện có cần giữ bản vá đang được hỗ trợ của chính dòng Boot dự án đó; không sao chép một phiên bản Boot mới vào dự án cũ mà không kiểm tra tương thích.

### 5.2. `src/main/java/example/cache/CacheApplication.java`

```java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CacheApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(CacheApplication.class, args)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("L1: " + service.getPrice("P42"));
            System.out.println("L2: " + service.getPrice("P42"));
            System.out.println("L3: " + service.getPrice("P43"));

            CacheManager manager = context.getBean(CacheManager.class);
            System.out.println("Manager: "
                    + manager.getClass().getSimpleName());
        }
    }
}
```

### 5.3. `src/main/java/example/cache/CacheConfiguration.java`

```java
package example.cache;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

### 5.4. `src/main/java/example/cache/CatalogService.java`

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger sourceCalls = new AtomicInteger();

    @Cacheable(cacheNames = "productPrices")
    public String getPrice(String productId) {
        int call = sourceCalls.incrementAndGet();
        System.out.println("Tai tu nguon: " + productId + " (#" + call + ")");
        return "gia-" + productId + "-lan-" + call;
    }
}
```

### 5.5. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
logging.level.root=OFF
spring.cache.type=caffeine
spring.cache.cache-names=productPrices
spring.cache.caffeine.spec=maximumSize=200,expireAfterWrite=300s
```

### 5.6. Chạy thử

Cần JDK 17 trở lên, Maven 3.9+, kết nối Maven Central cho lần đầu tải dependency. Tại thư mục gốc dự án:

```bash
java -version
mvn -q spring-boot:run
```

Các dòng **do mã ứng dụng in ra** (không tính thông báo từ Maven/runtime bên ngoài) theo thứ tự:

```text
Tai tu nguon: P42 (#1)
L1: gia-P42-lan-1
L2: gia-P42-lan-1
Tai tu nguon: P43 (#2)
L3: gia-P43-lan-2
Manager: CaffeineCacheManager
```

**Tại sao đúng?** Gọi lần đầu với `P42` bị miss nên chạy thân phương thức và ghi cache. Gọi lần hai qua Spring bean với `P42` là hit nên không thấy thêm dòng `Tai tu nguon`. `P43` là key mới, nên phải tính tiếp. Dòng `Manager` là một cách xác nhận provider thật sự được Spring chọn. `getPrice` ở đây mô phỏng nguồn dữ liệu, không phải giao diện truy cập database thực.

Nếu bỏ dependency `caffeine` và dòng `spring.cache.type=caffeine`, Boot có thể dùng Simple provider. Nếu giữ `spring.cache.type=caffeine` nhưng thiếu các class cần thiết, cấu hình không còn hợp lệ; hãy kiểm tra runtime classpath và lỗi khởi tạo thay vì cho rằng provider vẫn hoạt động.

## 6. Cách 3: Spring Boot + Redis (cache chia sẻ giữa các instance)

Redis là một hệ thống lưu trữ riêng, cần kết nối mạng. Nó phù hợp nếu nhiều instance ứng dụng cần dùng chung vùng cache hoặc cần invalidation tập trung. Với Boot, thường dùng hai dependency Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
```

Hoặc Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-cache")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

`spring-boot-starter-data-redis` mang Spring Data Redis và client Redis (thông thường Lettuce) cùng các dependency liên quan. Adapter Spring Cache cho Redis là `org.springframework.data.redis.cache.RedisCacheManager`. Nó **khác** `org.springframework.cache.caffeine.CaffeineCacheManager` và không yêu cầu phải thêm Caffeine.

Ví dụ phần cấu hình khi đã có Redis server reachable:

```properties
spring.cache.type=redis
spring.cache.cache-names=productPrices
spring.cache.redis.time-to-live=5m
spring.data.redis.host=localhost
spring.data.redis.port=6379
```

Không thể coi đây là ví dụ chạy độc lập như Caffeine: Redis server phải đang hoạt động và được cấu hình mạng, xác thực, TLS nếu môi trường yêu cầu. TTL Redis cache không thay thế việc xóa key khi dữ liệu nguồn thay đổi; cần xem xét serialization, tương thích schema, tiền tố key, kết nối lỗi và chi phí mạng.

**Lưu ý:** nếu `spring.cache.type` chưa đặt và classpath chứa nhiều provider, đừng đoán provider từ tên thư viện mới thêm. Spring Boot có thứ tự nhận diện, ví dụ JCache có thể được chọn trước Redis hay Caffeine trong một số cấu hình. Luôn kiểm tra bean `CacheManager` và chọn rõ `spring.cache.type` khi cần.

## 7. Cách 4: JCache (JSR-107) và các provider như Ehcache 3

**JCache** là một tiêu chuẩn API cache Java; nó không phải kho lưu trữ cụ thể. Một dự án muốn dùng JCache cần:
1. Spring Cache abstraction + adapter JCache (trong `spring-context-support`, starter cache của Boot đã bao gồm).
2. API JCache cùng thư viện hiện thực `CachingProvider`.
3. Cấu hình cache/provider phù hợp.

Các coordinates quan trọng:

```text
org.springframework.boot:spring-boot-starter-cache
javax.cache:cache-api
org.ehcache:ehcache
```

Ở các phiên bản JCache phổ biến, package API vẫn là `javax.cache`; **không tự đổi thành `jakarta.cache`** chỉ vì ứng dụng dùng Spring phiên bản mới. Trên thực tế, `cache-api` đôi khi đã được provider kéo vào theo phụ thuộc bắc cầu; nếu cần khai báo trực tiếp, để BOM quản lý phiên bản khi có thể.

Ví dụ thêm provider Ehcache 3 trong ứng dụng Boot đã có starter cache:

```xml
<dependency>
    <groupId>org.ehcache</groupId>
    <artifactId>ehcache</artifactId>
</dependency>
```

Ehcache 3 có JCache provider; tùy phiên bản, Java và định dạng cấu hình, có thể cần điều chỉnh dependency JAXB, classifier hoặc cách nạp file XML theo tài liệu của Ehcache. Việc thêm jar đơn thuần chưa thay thế bước cấu hình cache cụ thể. **Không dùng cấu hình của Ehcache 2 cho Ehcache 3**: đây là hai thế hệ API khác nhau.

Ví dụ một số thuộc tính Boot:

```properties
spring.cache.type=jcache
spring.cache.jcache.config=classpath:ehcache.xml
```

`ehcache.xml` ở đây phải là tài nguyên cấu hình **thật sự có trong classpath và đúng định dạng mà provider hỗ trợ**; dòng properties chỉ minh họa cách liên kết, không có nghĩa file XML được tạo tự động. Nếu có hơn một `CachingProvider`, cần chỉ định `spring.cache.jcache.provider` đúng tên class theo thư viện hiện đang dùng. Tránh vừa dùng annotation `@Cacheable` của Spring vừa dùng `@CacheResult` của JCache trên cùng luồng mà không có chủ đích.

### Bảng lựa chọn provider theo bài toán

| Provider | Dependency chính ngoài starter cache | Vị trí lưu | Phù hợp |
| --- | --- | --- | --- |
| Simple (`ConcurrentMap`) | Không cần provider jar riêng | Trong một JVM | Demo, test, tác vụ rất đơn giản |
| Caffeine | `com.github.ben-manes.caffeine:caffeine` | Trong một JVM | Cache nội bộ, TTL/giới hạn dung lượng, độ trễ thấp |
| Redis | `spring-boot-starter-data-redis` | Redis server dùng chung | Nhiều instance, chia sẻ dữ liệu cache |
| Ehcache 3 qua JCache | `org.ehcache:ehcache` (+ JCache API nếu thiếu) | Theo cấu hình Ehcache/provider | Cần JSR-107, chiến lược lưu trữ do Ehcache cung cấp |
| Hazelcast / Infinispan / Couchbase | Dependency vendor và adapter phù hợp | Theo kiến trúc vendor | Hệ thống có sẵn công nghệ đó và cần tích hợp với Spring Cache |

Danh sách không có nghĩa một ứng dụng phải cài tất cả. **Mỗi ví dụ nên bắt đầu từ một provider rõ ràng**, chỉ thêm nhiều provider khi thật sự có yêu cầu đa tầng hoặc nhiều loại cache.

## 8. Dự án Spring Framework thuần: khai báo dependency và CacheManager thủ công

Nếu **không** dùng Spring Boot, không dùng `spring-boot-starter-cache` hay properties `spring.cache.*` của Boot. Một ứng dụng Spring thuần có thể bắt đầu với:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>
```

Đoạn XML trên giả định phiên bản `spring-context` đã được quản lý trong Maven `dependencyManagement`/Spring Framework BOM; nếu không có BOM thì phải khai báo **phiên bản Spring Framework cụ thể, tương thích cho toàn bộ module**. Để dùng Simple provider, tạo `CacheManager`:

```java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productPrices");
    }
}
```

Đây là một **class cấu hình** để đặt trong ứng dụng có Spring ApplicationContext, không phải chương trình có `main`. Dùng Caffeine thủ công thì thêm:

```text
org.springframework:spring-context-support
com.github.ben-manes.caffeine:caffeine
```

Và thay bean cache manager bằng:

```java
@Bean
public CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("productPrices");
    manager.setCacheSpecification("maximumSize=200,expireAfterWrite=300s");
    return manager;
}
```

Cần import `org.springframework.cache.caffeine.CaffeineCacheManager`; đoạn bean nằm trong class `@Configuration` đã bật `@EnableCaching`. Đây là **minh họa thay thế bean**, không chèn thêm song song với bean `ConcurrentMapCacheManager` cùng tên. Khi dùng Redis/JCache trong Spring thuần, thêm Spring Data Redis/adapter JCache cùng thư viện provider và tự tạo, cấu hình bean `CacheManager` tương ứng.

## 9. Quản lý phiên bản: tránh phụ thuộc xung đột

Spring Framework, Spring Boot và các provider có ma trận tương thích theo phiên bản. Cách quản lý bền vững:

- **Maven + Spring Boot:** dùng `spring-boot-starter-parent` hoặc import `spring-boot-dependencies` BOM. Khai báo dependency được BOM quản lý **không cần số version riêng**.
- **Gradle + Spring Boot:** sử dụng `io.spring.dependency-management` đi cùng Boot plugin hoặc import Boot BOM bằng Gradle `platform(...)`, theo thiết lập hiện có.
- **Spring Framework thuần:** dùng Spring Framework BOM và thêm version phù hợp cho các provider không do BOM đó quản lý.
- Không tự gắn phiên bản Spring Framework mới vào một Boot cũ, hoặc ép version Caffeine/Ehcache mới khi chưa kiểm tra API/Java compatibility.
- Phân biệt dependency ở **compile classpath** và **runtime classpath**: `@Cacheable` có thể biên dịch dù runtime thiếu adapter/provider cần thiết; nhiều lỗi chỉ bộc lộ lúc tạo bean hoặc lúc tra cache.

Lệnh kiểm tra thực tế (chạy tại thư mục dự án):

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework,org.springframework.boot,com.github.ben-manes.caffeine,org.ehcache,javax.cache
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency caffeine --configuration runtimeClasspath
```

Trên Windows có thể chạy `gradlew.bat` thay `./gradlew`. Kết quả giúp xác minh bạn thực sự có adapter và provider trên runtime classpath, tìm dependency bị loại trừ (*excluded*), version bị ép hoặc nhiều provider cùng tồn tại.

## 10. Kích hoạt đúng và kiểm tra đúng provider

Các điều kiện cần cùng đúng để có cache thực sự:

1. Annotation cache xuất hiện trên phương thức của bean Spring.
2. Cơ chế annotation được bật bằng `@EnableCaching`.
3. Lời gọi đi qua proxy Spring ở chế độ proxy (đặc biệt không self-invocation).
4. Có `CacheManager` phù hợp với cache name dùng trong annotation.
5. Dependency provider có mặt trên runtime classpath và hạ tầng bên ngoài (nếu có) hoạt động.

### Kiểm tra bean CacheManager

Trong một bean Spring hoặc đoạn mã khởi động có `ApplicationContext`, có thể kiểm tra:

```java
CacheManager manager = context.getBean(CacheManager.class);
System.out.println(manager.getClass().getName());
System.out.println(manager.getCacheNames());
```

Ở đây `context` là `ApplicationContext` đã được khởi tạo, và `manager` là bean mà Spring thật sự sử dụng. Với ví dụ Caffeine ở trên, ta mong chờ class `CaffeineCacheManager`; với Redis là `RedisCacheManager`. Khi có nhiều bean `CacheManager`, cách tra theo type có thể không duy nhất; cần xét `@Primary`, tên bean, cache resolver và cấu hình của ứng dụng.

### Lỗi phổ biến và hướng kiểm tra

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Có `@Cacheable` nhưng phương thức vẫn chạy mọi lần | Thiếu `@EnableCaching`, tự gọi bằng `this`, key thay đổi, cache bị invalidation | Kiểm tra proxy, cách lấy bean, tham số/key và cấu hình cache |
| Không tìm thấy `CaffeineCacheManager` khi compile | Thiếu `spring-context-support` hoặc project không dùng starter cache | Kiểm tra module trên compile classpath |
| Boot chọn Simple dù muốn Caffeine | Thiếu Caffeine jar; hoặc provider chưa được nhận diện | Kiểm tra dependency, `CacheManager`, `spring.cache.type` |
| Thêm Redis starter nhưng không dùng Redis cache | Có provider khác được ưu tiên, tự khai báo `CacheManager` hoặc `spring.cache.type` khác | Kiểm tra auto-config và bean manager thực tế |
| Ứng dụng Redis báo lỗi kết nối | Redis server/địa chỉ/cổng/credentials/TLS không đúng | Kiểm tra kết nối tới Redis và cấu hình môi trường |
| JCache báo không tìm thấy provider hoặc cache | Thiếu JCache implementation, nhiều provider hoặc cache chưa khai báo | Xem service provider, provider class, file cấu hình và cache name |
| `No cache could be resolved` / `Cannot find cache` | Tên cache không tồn tại trong provider đang dùng | Đối chiếu `@Cacheable(cacheNames=...)` với `spring.cache.cache-names` hoặc cấu hình vendor |
| Chạy được nhưng giá trị trả ra đã cũ | TTL/invalidation không phù hợp | Xác định nguồn dữ liệu, cơ chế xóa/cập nhật cache sau ghi |

Một số property `spring.cache.*` chỉ có tác dụng khi Spring Boot đang auto-configure đúng provider. Khi bạn tự tạo `CacheManager` bean, provider và bean đó có thể quyết định cấu hình thực tế; đừng cho rằng chỉnh `spring.cache.caffeine.spec` luôn tác động lên bean thủ công.

## 11. Chọn dependency tối thiểu theo từng dự án

- **Demo ban đầu bằng Spring Boot:** `spring-boot-starter-cache`, `@EnableCaching`, kiểm tra Simple provider.
- **Local cache có giới hạn và TTL:** `spring-boot-starter-cache` + `caffeine`, chọn `spring.cache.type=caffeine`.
- **Cache dùng chung nhiều instance:** `spring-boot-starter-cache` + `spring-boot-starter-data-redis`, có Redis server và chọn `spring.cache.type=redis`.
- **Bắt buộc JSR-107:** `spring-boot-starter-cache` + provider triển khai JCache, kiểm tra `javax.cache:cache-api` và cấu hình provider; cân nhắc Ehcache 3.
- **Spring Framework không Boot:** `spring-context` + adapter/provider cần thiết, tự định nghĩa `CacheManager` và quản lý version qua BOM.

Một dependency list đúng là danh sách **vừa đủ cho một lựa chọn lưu cache cụ thể**. Nó phải được xác minh bằng dependency tree và type của `CacheManager` đang chạy, chứ không chỉ bằng việc dự án compile thành công.

## 12. Câu hỏi tự kiểm tra

1. `spring-boot-starter-cache` mang lại những thành phần nào, và vì sao thêm starter đó chưa có nghĩa dữ liệu đã nằm trong Redis?
2. Nếu dùng `CaffeineCacheManager` trong ứng dụng Spring Framework thuần, bạn phải thêm các module nào ngoài `spring-context`?
3. Vì sao `javax.cache:cache-api` không thể một mình thay thế `org.ehcache:ehcache`?
4. Dự án có cả Ehcache JCache và Caffeine trên classpath: muốn dùng Caffeine thì cấu hình và kiểm tra điều gì?
5. Caffeine đang cache tốt trên một instance, nhưng có ba instance chạy sau load balancer: các giá trị có tự đồng bộ không?
6. Đã thêm dependency đầy đủ nhưng `@Cacheable` không hoạt động khi gọi `this.getPrice(...)` trong cùng bean: vấn đề nằm ở dependency hay đường gọi qua proxy?
7. Vì sao nên để Spring Boot BOM quản lý phiên bản provider đã hỗ trợ thay vì tự pin từng jar?

## Tài liệu chính thức

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Ghi nhớ:** Spring Cache quyết định *lúc nào* dùng cache; provider quyết định *lưu và quản lý dữ liệu ở đâu, thế nào*; Spring Boot giúp liên kết các thành phần nếu đúng dependency và cấu hình. Hãy chọn một provider, thêm các jar cần thiết, bật annotation, rồi xác minh `CacheManager` và hành vi hit/miss trước khi đưa vào sử dụng.