# Tích hợp Redis qua Spring Data và kiểm tra vòng đời dịch vụ

Redis thường được dùng làm cache phân tán, kho session, bộ đếm, rate limiter và hàng đợi nhẹ. Trong Spring Boot, **Spring Data Redis** cung cấp `RedisTemplate`, repository và tích hợp với Spring Cache; **Lettuce** là Redis client mặc định phổ biến nhờ hỗ trợ đồng bộ, bất đồng bộ, reactive và Redis Cluster. Trên Azure, ứng dụng có thể gặp hai dòng dịch vụ: **Azure Cache for Redis** (dịch vụ cũ đang trong lộ trình nghỉ hưu) và **Azure Managed Redis** (dịch vụ chiến lược mới dựa trên Redis Enterprise).

Tích hợp cần xét cả hai vòng đời: vòng đời của **ứng dụng/client** (khởi tạo connection factory, xác thực, refresh token, reconnect và shutdown) và vòng đời của **dịch vụ Redis** (provision, TTL/eviction, scale, failover, backup, migration và retirement). Một ứng dụng chạy được sau khi cấu hình host/password vẫn chưa đủ để vận hành an toàn nếu cache hết hạn token, service failover hoặc dữ liệu bị eviction.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào Spring Data Redis, Lettuce và vòng đời vận hành Azure Redis.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt Azure Cache for Redis và Azure Managed Redis, hiểu lộ trình retirement/migration.
- Giải thích vai trò của Spring Data Redis, RedisConnectionFactory, Lettuce, RedisTemplate, repository và RedisCacheManager.
- Cấu hình starter Spring Cloud Azure Redis cho Azure Cache for Redis theo tài liệu hỗ trợ.
- Kết nối Azure Managed Redis bằng Lettuce và Microsoft Entra ID qua `redis-authx-entraid`.
- Tích hợp credential provider có refresh vào Spring Data Redis thông qua Lettuce connection configuration.
- Chọn Redis Cluster hay single-endpoint client theo clustering policy của Azure Managed Redis.
- Dùng `@Cacheable`, `@CachePut`, `@CacheEvict`, TTL và cache-aside đúng cách.
- Quản lý serializer, key prefix, eviction, cache invalidation và cache stampede.
- Hiểu lifecycle của LettuceConnectionFactory, token provider, connection, failover và shutdown.
- Thiết kế readiness/health check, retry, timeout, backup, geo-replication và migration.

## 2. Azure Redis: chọn đúng dịch vụ

### 2.1. Azure Cache for Redis và Azure Managed Redis

| Tiêu chí | Azure Cache for Redis | Azure Managed Redis |
| --- | --- | --- |
| Kiến trúc | Dịch vụ dựa trên Redis community edition ở các tier Basic/Standard/Premium; Enterprise có kiến trúc riêng | Dựa trên Redis Enterprise, nhiều shard chạy song song trên các node |
| Vai trò hiện tại | Dịch vụ cũ trong lộ trình retirement | Dịch vụ chiến lược được khuyến nghị cho workload mới |
| Spring integration | Microsoft có Spring Cloud Azure starter `spring-cloud-azure-starter-data-redis-lettuce` | Spring Data Redis/Lettuce kết nối qua Redis protocol; Entra dùng `redis-authx-entraid` |
| Entra authentication | Được hỗ trợ theo SKU/cấu hình; starter có property passwordless | Bật mặc định cho cache mới; access key authentication tắt mặc định |
| Endpoint/port | Phụ thuộc SKU; thường gặp 6380 hoặc 10000 | FQDN dạng `<dns>.<region>.redis.azure.net`, port 10000 |
| Clustering | Phụ thuộc SKU/tier | Chọn OSS, Enterprise hoặc Non-clustered policy khi provision |
| Vòng đời | Basic/Standard/Premium và Enterprise có mốc retirement khác nhau | Dịch vụ mới, một số tier/tính năng có thể vẫn ở preview |

Không dùng tên “Azure Redis” như thể hai dịch vụ có cùng hostname, port, clustering, authentication và starter. Kiểm tra SKU, endpoint và hướng dẫn của đúng dịch vụ trước khi cấu hình Spring.

### 2.2. Lộ trình retirement của Azure Cache for Redis

Microsoft đã công bố retirement cho tất cả SKU Azure Cache for Redis. Theo lịch cập nhật tháng 7/2026 cho **Azure public cloud**:

| SKU | Mốc quan trọng |
| --- | --- |
| Enterprise và Enterprise Flash | Chặn tạo cache mới từ 01/04/2026; dịch vụ retirement ngày 31/03/2027, quá trình chuyển các instance còn lại sang Azure Managed Redis bắt đầu từ 01/04/2027 |
| Basic, Standard, Premium | Chặn tạo mới cho tenant/new customers từ 01/04/2026; tenant hiện hữu đủ điều kiện có thể tiếp tục tạo đến ngày retirement; toàn bộ cache retirement ngày 30/09/2028 |

Tenant được xem là hiện hữu nếu có ít nhất một subscription trong tenant đã có Azure Cache for Redis trước 01/04/2026. Lịch của Azure Government và Azure operated by 21Vianet có khác biệt; kiểm tra FAQ/What's New nếu triển khai ở sovereign cloud.

Đối với ứng dụng mới, ưu tiên đánh giá Azure Managed Redis. Với hệ thống đang chạy Azure Cache for Redis, lập kế hoạch migration, kiểm thử compatibility, benchmark và cutover trước ngày retirement. Không đợi tới thời điểm dịch vụ bị tắt mới bắt đầu.

## 3. Kiến trúc Spring Data Redis

Spring Data Redis tách logic nghiệp vụ khỏi Redis client và giao thức:

~~~mermaid
flowchart LR
    A[Application service] --> B[Spring Cache / RedisTemplate / Repository]
    B --> C[RedisConnectionFactory]
    C --> D[Lettuce client]
    D --> E[TLS + Redis protocol]
    E --> F[Azure Cache for Redis / Azure Managed Redis]
    G[Microsoft Entra token provider] -. credentials / refresh .-> D
    H[Spring ApplicationContext] -. bean lifecycle .-> C
~~~

- **Spring Cache abstraction:** cung cấp annotation `@Cacheable`, `@CachePut`, `@CacheEvict`; code nghiệp vụ không phải tự viết GET/SET cho mọi method.
- **RedisTemplate/StringRedisTemplate:** thao tác Redis command trực tiếp như value, hash, list, set, sorted set, stream và pub/sub.
- **Spring Data Redis repositories:** ánh xạ object thành Redis hash/keyspace với `@RedisHash` và `CrudRepository`.
- **RedisConnectionFactory:** cung cấp connection cho Spring Data. Với Lettuce, implementation là `LettuceConnectionFactory`.
- **Lettuce:** quản lý Redis client, connection, cluster topology, reconnect, command timeout và credential provider.
- **Azure Redis:** quản lý node/shard, replication, failover, maintenance và giới hạn dịch vụ.

Một ứng dụng có thể dùng đồng thời Spring Cache và RedisTemplate, nhưng phải thống nhất key namespace, serializer, TTL và quy tắc invalidation để các đường truy cập không ghi đè hoặc đọc sai dữ liệu của nhau.

## 4. Thêm dependency và quản lý BOM

Với Spring Cloud Azure, Microsoft cung cấp starter:

`com.azure.spring:spring-cloud-azure-starter-data-redis-lettuce`

Ví dụ Maven cho Spring Data Redis với Azure Cache for Redis:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-data-redis-lettuce</artifactId>
    </dependency>
</dependencies>
~~~

Starter Azure Redis được Microsoft Spring guide mô tả cho **Azure Cache for Redis**. Không suy ra starter này tự động cung cấp mọi cấu hình Azure Managed Redis/Redis Enterprise clustering và Entra token refresh. Với Azure Managed Redis, bài này dùng Spring Data Redis/Lettuce và credential provider của Redis.

Chọn Spring Cloud Azure BOM theo dòng Spring Boot. Tài liệu hiện hành có các nhánh 4.x/5.x/6.x/7.x; không trộn version riêng lẻ của Spring Data Redis, Lettuce và Azure starter. Kiểm tra [Spring Cloud Azure version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview) trước khi pin dependency.

Đối với Azure Managed Redis qua Entra, cần thêm thư viện:

~~~xml
<dependency>
    <groupId>redis.clients.authentication</groupId>
    <artifactId>redis-authx-entraid</artifactId>
    <version>${redis-authx-entraid.version}</version>
</dependency>
~~~

Lettuce cần phiên bản hỗ trợ Entra/streaming credentials (Lettuce 6.6 trở lên); API credential provider mới `CredentialsProvider` và adapter tương thích Spring Data được giới thiệu trong dòng Lettuce 7.9. Hãy xác minh compatibility giữa Spring Boot, Spring Data Redis, Lettuce và `redis-authx-entraid` trong dependency tree thực tế.

## 5. Cấu hình Azure Cache for Redis với Spring Cloud Azure

### 5.1. Entra passwordless

Với Azure Cache for Redis SKU/endpoint có hỗ trợ Entra, Spring Cloud Azure starter cung cấp property passwordless. Ví dụ:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
      username: ${REDIS_ENTRA_USERNAME}
      ssl:
        enabled: true
      azure:
        passwordless-enabled: true
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Chỉ khai báo khi dùng user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
~~~

`REDIS_HOST`, `REDIS_PORT` và `REDIS_ENTRA_USERNAME` lấy từ cache resource/Redis user configuration. Với Azure Cache for Redis, port có thể là 6380 hoặc 10000 tùy SKU/deployment. Không copy port từ môi trường khác mà không kiểm tra portal.

Managed Identity giúp ứng dụng lấy token; principal vẫn phải được thêm vào Redis authentication/authorization configuration. Entra authentication chỉ hoạt động trên SSL/TLS. Không tắt TLS để sửa lỗi xác thực.

### 5.2. Access key/password authentication

Nếu hệ thống cũ chưa chuyển sang Entra, có thể dùng access key theo cấu hình của đúng SKU:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
      password: ${REDIS_ACCESS_KEY}
      ssl:
        enabled: true
~~~

Access key là secret; lưu trong Key Vault/secret manager, không commit vào `application.yml`, image hoặc log. Có kế hoạch rotation và chuyển sang Entra nếu dịch vụ/ứng dụng hỗ trợ. Nếu bật/tắt authentication hoặc đổi key, các connection hiện hữu có thể bị ngắt; kiểm thử reconnect trước khi triển khai.

## 6. Azure Managed Redis với Microsoft Entra và Lettuce

### 6.1. Provisioning và endpoint

Khi tạo Azure Managed Redis, chọn:

- Region và tier phù hợp với latency, dung lượng, CPU và workload.
- High availability/zone redundancy theo yêu cầu.
- **Clustering policy**: OSS, Enterprise hoặc Non-clustered.
- Redis modules cần dùng (ví dụ RediSearch) ngay khi provision; không thể bổ sung module sau khi cache đã tạo.
- Active geo-replication ngay lúc tạo nếu kiến trúc cần tham gia replication group; cache không được tạo sẵn active geo-replication thì không thể thêm vào group sau này theo quy trình thông thường.
- Private access/network và authentication.

Cache mới bật Microsoft Entra ID mặc định và tắt access key authentication mặc định. Hostname có dạng:

`<dns-name>.<azure-region>.redis.azure.net`

Port client là **10000**. Sử dụng FQDN, TLS và network path được cấu hình trong Azure; không hard-code IP hoặc shard port.

### 6.2. Clustering policy quyết định client

Azure Managed Redis chạy kiến trúc Redis Enterprise với shard; clustering policy xác định cách client nhìn thấy topology:

| Policy | Client model | Khi phù hợp |
| --- | --- | --- |
| **Enterprise** | Single endpoint/proxy; client dùng Redis standalone API | Muốn client interface đơn giản; proxy định tuyến nội bộ |
| **OSS** | Redis Cluster API; client tự discovery shard và theo redirect | Muốn client kết nối trực tiếp tới shard, dùng Lettuce cluster-aware |
| **Non-clustered** | Single endpoint, không sharding; chỉ hỗ trợ cache nhỏ theo giới hạn dịch vụ | Workload nhỏ, cần single-process semantics |

Chọn OSS hay Enterprise khi provision vì đổi policy sau này thường cần xóa/tạo lại cache; Non-clustered có khả năng chuyển sang clustered trong một số điều kiện. Với OSS, client phải hỗ trợ Redis Cluster API. Với Enterprise/Non-clustered, dùng client standalone. Không dùng `RedisClusterConfiguration` cho một endpoint Enterprise chỉ vì tên sản phẩm là Redis Enterprise.

Nếu dùng OSS cluster, các lệnh nhiều key phải tuân thủ hash slot; các key cần thao tác cùng lệnh atomic nên dùng hash tag nhất quán, ví dụ `order:{tenant-42}:header` và `order:{tenant-42}:lines`. Không hard-code port shard được discovery; service có thể thay đổi topology.

### 6.3. Tạo Entra credential provider

Azure Managed Redis dùng token audience `https://redis.azure.com/.default`. Thư viện `redis-authx-entraid` lấy và làm mới token cho Lettuce. Ví dụ system-assigned Managed Identity:

~~~java
import java.util.Set;
import redis.clients.authentication.core.TokenBasedRedisCredentialsProvider;
import redis.clients.authentication.entraid.EntraIDTokenAuthConfigBuilder;

public TokenBasedRedisCredentialsProvider createRedisCredentials() {
    try (EntraIDTokenAuthConfigBuilder builder =
            EntraIDTokenAuthConfigBuilder.builder()) {
        builder.systemAssignedManagedIdentity();
        builder.scopes(Set.of("https://redis.azure.com/.default"));
        return TokenBasedRedisCredentialsProvider.create(builder.build());
    }
}
~~~

Với user-assigned Managed Identity, cấu hình `userAssignedManagedIdentity` cùng loại định danh (client ID, object ID hoặc resource ID) theo API version của thư viện. Service principal cũng được hỗ trợ; nếu dùng client secret, lấy secret từ Key Vault/secret provider thay vì source code.

Trong Azure portal, thêm user/service principal tương ứng vào danh sách Redis users. Mặc định principal có thể được cấp quyền rộng trên command/key; dùng custom data access permissions khi tính năng và policy của môi trường hỗ trợ để giới hạn command/key. Azure Managed Redis không hỗ trợ Entra groups theo tài liệu hiện hành, vì vậy không giả định gán group sẽ thay thế việc thêm principal trực tiếp.

Khi thay đổi setting Access Keys Authentication (ví dụ tắt key sau khi chuyển sang Entra), Azure Managed Redis có thể **đóng toàn bộ connection hiện hữu**, kể cả connection đã dùng Entra. Sau thay đổi, client phải reconnect và xác thực lại; thực hiện theo rolling change có quan sát, tránh đổi đồng thời trên tất cả cache/ứng dụng.

### 6.4. Tích hợp credential provider vào Spring Data Redis

Tài liệu Spring Cloud Azure hiện có starter Redis riêng cho Azure Cache for Redis; với Azure Managed Redis, hướng Java được tài liệu Microsoft/Redis hướng dẫn là dùng `redis-authx-entraid` với Lettuce. Spring Data Redis cho phép cấu hình `RedisCredentialsProviderFactory` trong `LettuceClientConfiguration`. Với Lettuce 7.9+, có thể chuyển `CredentialsProvider` mới sang SPI mà Spring Data Redis yêu cầu bằng `RedisCredentialsProvider.adapt(...)`.

Ví dụ dưới đây minh họa Azure Managed Redis dùng **OSS clustering policy**:

~~~java
import java.util.List;
import java.util.Set;
import io.lettuce.core.ClientOptions;
import io.lettuce.core.RedisCredentialsProvider;
import io.lettuce.core.cluster.ClusterClientOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.RedisCredentialsProviderFactory;
import redis.clients.authentication.core.TokenBasedRedisCredentialsProvider;
import redis.clients.authentication.entraid.EntraIDTokenAuthConfigBuilder;

@Configuration(proxyBeanMethods = false)
public class ManagedRedisConfiguration {

    @Bean(destroyMethod = "close")
    TokenBasedRedisCredentialsProvider redisCredentialsProvider() {
        try (EntraIDTokenAuthConfigBuilder builder =
                EntraIDTokenAuthConfigBuilder.builder()) {
            builder.systemAssignedManagedIdentity();
            builder.scopes(Set.of("https://redis.azure.com/.default"));
            return TokenBasedRedisCredentialsProvider.create(builder.build());
        }
    }

    @Bean
    RedisConnectionFactory redisConnectionFactory(
            TokenBasedRedisCredentialsProvider credentialsProvider) {

        RedisClusterConfiguration cluster =
            new RedisClusterConfiguration(
                List.of(System.getenv("REDIS_HOST") + ":10000"));

        ClusterClientOptions clientOptions = ClusterClientOptions.builder()
            .reauthenticateBehavior(
                ClientOptions.ReauthenticateBehavior.ON_NEW_CREDENTIALS)
            .build();

        LettuceClientConfiguration clientConfiguration =
            LettuceClientConfiguration.builder()
                .useSsl()
                .clientOptions(clientOptions)
                .redisCredentialsProviderFactory(
                    new RedisCredentialsProviderFactory() {
                        @Override
                        public RedisCredentialsProvider createCredentialsProvider(
                                RedisConfiguration configuration) {
                            return RedisCredentialsProvider.adapt(
                                credentialsProvider);
                        }
                    })
                .build();

        return new LettuceConnectionFactory(cluster, clientConfiguration);
    }
}
~~~

Bean `redisCredentialsProvider()` tạo provider và để Spring đóng provider khi ApplicationContext shutdown. Với Enterprise hoặc Non-clustered policy, thay `RedisClusterConfiguration` bằng `RedisStandaloneConfiguration(host, 10000)` và dùng `ClientOptions` phù hợp. Ví dụ này yêu cầu phiên bản Spring Data Redis/Lettuce có các API `redisCredentialsProviderFactory`, `CredentialsProvider` và `RedisCredentialsProvider.adapt`; nếu BOM hiện tại chưa hỗ trợ, nâng cấp đồng bộ hoặc dùng client integration đã được xác minh cho version đó.

Không đồng thời để Spring Boot auto-configuration tạo thêm một RedisConnectionFactory khác dùng access key. Nếu định nghĩa bean riêng, kiểm tra chỉ có một connection factory đang được `RedisTemplate`, `RedisCacheManager` và repository sử dụng.

## 7. Sử dụng RedisTemplate và Spring Data repositories

### 7.1. StringRedisTemplate

`StringRedisTemplate` phù hợp khi key/value là chuỗi hoặc JSON đã serialize:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SessionStore {
    private final StringRedisTemplate redis;

    public SessionStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sessionId, String json) {
        redis.opsForValue().set(
            "session:" + sessionId,
            json,
            Duration.ofMinutes(30));
    }

    public String find(String sessionId) {
        return redis.opsForValue().get("session:" + sessionId);
    }

    public Boolean delete(String sessionId) {
        return redis.delete("session:" + sessionId);
    }
}
~~~

TTL 30 phút được đặt ngay trong lệnh `SET`; key tự hết hạn nếu không được gia hạn. Không lưu session có dữ liệu nhạy cảm dưới dạng plain text nếu cần mã hóa/giảm dữ liệu. Không log JSON/session token.

### 7.2. RedisTemplate cho object

Khi lưu object, cấu hình serializer tường minh:

- Key serializer ổn định, thường là `StringRedisSerializer`.
- Value serializer theo schema JSON có version hoặc format tương thích giữa các phiên bản service.
- Không dựa vào Java native serialization mặc định cho dữ liệu chia sẻ lâu dài giữa nhiều service/version.
- Tránh bật polymorphic default typing không kiểm soát; chỉ deserialize các kiểu được cho phép.

Thay đổi class Java không tự migration dữ liệu cũ trong Redis. Khi đổi schema, dùng version field/namespace hoặc chuyển đổi đọc kép có thời hạn.

### 7.3. Spring Data Redis repositories

Spring Data Redis có thể ánh xạ entity thành Redis hash:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "customer-session", timeToLive = 1800)
public class CustomerSession {
    @Id
    private String id;
    private String customerId;
    private String state;

    public CustomerSession() {}
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerSessionRepository
        extends CrudRepository<CustomerSession, String> {
}
~~~

`timeToLive = 1800` là thời gian sống tính bằng giây. Repository hỗ trợ CRUD và query derivation theo property được lập chỉ mục/được hỗ trợ; không xem Redis repository như relational database có join và transaction tùy ý. Thiết kế keyspace và index theo access pattern, tránh query toàn bộ keyspace trên đường request.

## 8. Spring Cache abstraction với Redis

### 8.1. Cache-aside bằng annotation

Spring Cache kiểm tra cache trước khi chạy method. Cache hit trả kết quả đã lưu; cache miss gọi method rồi ghi kết quả:

~~~java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(String id) {
        return repository.findViewById(id);
    }

    @CachePut(cacheNames = "productById", key = "#result.id")
    public ProductView update(ProductCommand command) {
        return repository.update(command);
    }

    @CacheEvict(cacheNames = "productById", key = "#id")
    public void delete(String id) {
        repository.deleteById(id);
    }
}
~~~

Ví dụ giả định `ProductRepository`, `ProductView` và `ProductCommand` là các kiểu của ứng dụng. `@Cacheable` không làm cache trở thành nguồn dữ liệu chính. Nếu Redis tạm thời không khả dụng, service phải có fallback hoặc degraded behavior theo yêu cầu; cache-aside thường đọc lại database nguồn khi cache miss.

### 8.2. Cấu hình RedisCacheManager và TTL

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class RedisCachingConfiguration {

    @Bean
    CacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues()
                .computePrefixWith(
                    cacheName -> "provider-integration:" + cacheName + "::");

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(Map.of(
                "productById", defaults.entryTtl(Duration.ofMinutes(10)),
                "productSearch", defaults.entryTtl(Duration.ofMinutes(2))))
            .build();
    }
}
~~~

Ví dụ cấu hình TTL mặc định 5 phút, cache chi tiết sản phẩm 10 phút và kết quả tìm kiếm 2 phút. Chọn TTL theo mức độ chấp nhận stale data và tần suất thay đổi nguồn; không dùng một TTL duy nhất cho mọi cache nếu dữ liệu có vòng đời khác nhau.

Nếu không cấu hình TTL, cache entry có thể tồn tại vô thời hạn cho tới khi bị xóa hoặc eviction. Đặt TTL rõ ràng cho dữ liệu có thể tái tạo và có chính sách invalidation; chỉ giữ key không-expiry khi đã có lý do vận hành và giới hạn memory phù hợp. RedisCacheManager mặc định dùng writer không khóa; các thao tác 
`putIfAbsent` và `clean` có thể gồm nhiều command, không mặc định là một thao tác atomic. Locking writer giảm chồng lấn ở cấp cache nhưng tạo thêm request và contention.

Spring Data Redis mặc định dùng cache key prefix theo cache name, nhưng cấu hình prefix riêng giúp tránh đụng key giữa ứng dụng/môi trường. Mặc định serializer value có thể là Java serialization; hãy cấu hình serializer phù hợp schema thay vì coi default là hợp đồng dữ liệu lâu dài.

### 8.3. TTL và TTI không giống nhau

- **TTL (time-to-live):** thời gian đếm từ lần tạo/ghi gần nhất. Đọc key không làm TTL reset.
- **TTI (time-to-idle):** thời gian tính từ lần truy cập gần nhất. Redis không có TTI nguyên bản, nhưng Spring Data Redis có thể mô phỏng bằng cách dùng `GETEX` khi đọc.

TTI-like cần Redis 6.2 trở lên và cấu hình `enableTimeToIdle()` cùng TTL. Mọi đường đọc/ghi phải dùng lệnh có expiration phù hợp; nếu `@Cacheable` đọc qua cache abstraction nhưng code khác đọc cùng key bằng RedisTemplate/repository với GET thông thường, lần đọc đó không reset TTL. Không trộn hai cách truy cập rồi kỳ vọng TTI luôn đúng.

## 9. Thiết kế key, serialization và invalidation

Một cache key nên chứa namespace, loại dữ liệu và các tham số ảnh hưởng kết quả:

`<application>:<environment>:<cache-name>:<entity-id-or-query-hash>`

Ví dụ:

- `catalog:prod:productById:SKU-1001`
- `catalog:prod:search:sha256(filter+sort+page)`
- `orders:prod:session:session-abc`

Không đưa access token, email/PII hoặc secret vào key. Với Redis Cluster, nhiều key dùng chung trong một multi-key command phải cùng hash slot; hash tag như `{tenant-42}` giúp nhóm key liên quan.

### 9.1. Cache invalidation

Khi dữ liệu nguồn thay đổi, chọn một quy tắc nhất quán:

- `@CachePut` cập nhật cache với kết quả mới.
- `@CacheEvict` xóa key để lần đọc sau lấy lại nguồn.
- Event/outbox phát invalidation khi update xảy ra ở service khác.
- TTL giới hạn khoảng thời gian stale nếu event invalidation bị trễ/mất.

Nếu database commit thành công nhưng Redis update thất bại, dữ liệu cache có thể stale. Có thể ưu tiên xóa key sau commit, phát invalidation qua outbox, hoặc dùng version trong key để tránh phục vụ entry cũ. Không coi một lệnh Redis và một transaction database là atomic.

### 9.2. Cache stampede và thundering herd

Khi một key phổ biến hết TTL, nhiều request đồng thời có thể cùng gọi database. Biện pháp:

- TTL có jitter để tránh nhiều key hết hạn cùng lúc.
- Single-flight/request coalescing cho cùng một key.
- Warm-up có giới hạn cho dữ liệu phổ biến.
- Stale-while-revalidate khi nghiệp vụ chấp nhận stale response.
- Rate limit hoặc bulkhead để bảo vệ database nguồn.

Không dùng distributed lock cho mọi cache miss nếu chưa cần; lock có thể tạo contention và phải xử lý owner crash/lease expiry. Nếu dùng lock, thiết kế token ownership và release an toàn.

## 10. Redis command và giới hạn dịch vụ

Redis protocol tương thích không có nghĩa mọi command đều được Azure Managed Redis cho phép. Một số command quản trị/cluster topology bị chặn vì Azure quản lý hạ tầng. Kiểm tra danh sách command hỗ trợ của đúng service và clustering policy.

- Tránh `KEYS *` trên keyspace lớn; dùng `SCAN` có cursor và batch size phù hợp.
- Với cache lớn, cấu hình Spring Data Redis writer dùng `SCAN` strategy nếu driver/mode hỗ trợ. Spring Data Redis mặc định có thể dùng `KEYS` + `DEL` khi clear cache.
- Với OSS clustering, client phải theo redirect/discovery; không gọi command thay đổi cluster topology.
- Các multi-key command trong cluster có thể yêu cầu keys cùng hash slot.
- Pub/Sub không phải durable queue; nếu consumer offline, message không được lưu để replay như broker.
- Redis transaction/Lua script có giới hạn theo server và cluster slot; không giả định multi-key transaction xuyên shard là atomic.

## 11. Vòng đời ứng dụng và Redis client

### 11.1. Vòng đời LettuceConnectionFactory

`LettuceConnectionFactory` của Spring Data Redis triển khai `InitializingBean`, `SmartLifecycle` và `DisposableBean`. Spring khởi tạo và start factory trong ApplicationContext; khi context shutdown, factory đóng client/connection theo lifecycle. Nó thường chia sẻ native thread-safe connection cho thao tác thông thường; object `LettuceConnection` của Spring không nên được chia sẻ giữa nhiều thread.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Initialized: afterPropertiesSet
    Initialized --> Started: ApplicationContext lifecycle
    Started --> Reconnecting: socket failure / failover
    Reconnecting --> Started: reconnect succeeds
    Reconnecting --> Degraded: retry budget exhausted
    Degraded --> Reconnecting: recovery / backoff
    Started --> Stopping: context shutdown
    Degraded --> Stopping: context shutdown
    Stopping --> Destroyed: close client/resources
    Destroyed --> [*]
~~~

Không tạo Lettuce client hoặc connection factory cho từng request. Dùng bean singleton do Spring quản lý; tránh giữ connection object qua nhiều thread. Với các thao tác blocking/transaction/pub-sub, kiểm tra quy tắc connection riêng theo Spring Data Redis/Lettuce.

### 11.2. Vòng đời token provider

Entra token có thời hạn. Azure Managed Redis yêu cầu client định kỳ refresh token và gửi `AUTH` với token mới trước khi token cũ hết hạn; Microsoft khuyến nghị gửi token mới ít nhất 3 phút trước expiry và thêm jitter để các client không refresh cùng lúc.

Lettuce + `redis-authx-entraid` có token provider streaming và tự động re-authentication khi credential mới được phát ra nếu bật `ReauthenticateBehavior.ON_NEW_CREDENTIALS`. Lettuce không tự quản lý vòng đời `TokenBasedRedisCredentialsProvider`; ứng dụng phải đóng provider khi shutdown. Trong ví dụ Spring, khai báo bean với `destroyMethod = "close"` để Spring gọi khi context dừng.

Không lấy token một lần lúc startup rồi dùng làm password tĩnh lâu dài. Không log token hoặc đưa token vào application.yml.

### 11.3. Startup, readiness và shutdown

- Startup có thể kiểm tra DNS, TLS, authentication và một lệnh `PING` nhẹ.
- Readiness nên phản ánh ứng dụng có thể phục vụ yêu cầu cần Redis hay không; tránh liveness phụ thuộc Redis khiến orchestrator restart toàn bộ pod khi cache tạm thời lỗi.
- Shutdown nên ngừng nhận traffic, hoàn tất request đang chạy trong deadline, đóng subscription/connection factory và token provider.
- Không gọi `FLUSHALL` hoặc xóa cache toàn bộ khi ứng dụng restart.
- Nếu cache không bắt buộc để xử lý request, thiết kế degraded mode thay vì fail toàn bộ startup chỉ vì Redis tạm thời unavailable.

## 12. Vòng đời dịch vụ Azure Managed Redis

### 12.1. Provision và cấu hình bất biến

Một số lựa chọn cần chốt ngay khi tạo cache:

- Clustering policy OSS/Enterprise; đổi policy thường cần tạo lại cache.
- Redis modules; không thể thêm module sau khi tạo.
- Active geo-replication; phải bật trong provisioning nếu cần tham gia replication group.
- Region/tier/dung lượng, HA/zone redundancy và network exposure.

Chọn sai clustering policy có thể khiến client Spring Data đang cấu hình standalone không kết nối đúng một cache OSS cluster hoặc ngược lại. Việc chọn module sai có thể buộc tạo instance mới và migration dữ liệu.

### 12.2. Scaling, maintenance và failover

Azure Managed Redis phân phối primary/replica shard trên nhiều node. Khi HA được bật, service quản lý replica, health monitoring và failover trong phạm vi cache/availability zone. Planned failover trong maintenance/scale thường hoàn tất nhanh; unplanned failover có thể lâu hơn và làm các connection hiện tại bị đóng.

Theo hướng dẫn dịch vụ, planned failover thường dưới 1 giây; unplanned failover thường khoảng 10–15 giây do cần phát hiện và xác minh lỗi. Đây là thời gian tham khảo, không phải SLA cho từng request.

Ứng dụng có thể gặp:

- Connection reset, socket error hoặc timeout.
- Lệnh đã gửi nhưng response chưa về khi failover xảy ra.
- Connection cũ bị từ chối cho đến khi reconnect thành công.
- Latency tăng do replica promotion và data synchronization.

Lettuce có reconnect behavior, nhưng không nên giả định mọi command được thực thi đúng một lần. Nếu timeout sau một lệnh ghi, kết quả có thể không rõ; retry `INCR`, `LPUSH` hoặc side effect tương tự có thể tạo dữ liệu trùng. Dùng operation ID/idempotency hoặc kiểm tra trạng thái trước khi retry.

### 12.3. Region failover và active geo-replication

HA/zone redundancy xử lý lỗi node/zone trong một region. **Region-wide failover** là trách nhiệm kiến trúc ứng dụng:

- Nếu không cấu hình active geo-replication, không có automatic regional failover sang cache ở region khác.
- Nếu có active geo-replication, ứng dụng cần theo dõi health/replication metric, quyết định chuyển traffic và định tuyến sang cache region còn khỏe.
- Khi region cũ phục hồi, service đồng bộ lại dữ liệu; ứng dụng cần kiểm tra trạng thái trước khi chuyển traffic trở lại.
- Test firewall, DNS, routing, failover và recovery process.

Active geo-replication là replication của Redis cache, không thay thế backup/restore và không tự đảm bảo mọi workflow business nhất quán giữa nhiều region.

### 12.4. Persistence, backup và eviction

Redis thường được dùng như cache có thể tái tạo, nhưng Azure Managed Redis có các tính năng persistence/import-export theo tier/feature support. Cần phân biệt:

- **Replication/HA:** bảo vệ khỏi một số lỗi node/zone.
- **Persistence:** ghi snapshot/data ra storage theo cấu hình để phục hồi cache instance trong các tình huống hỗ trợ.
- **Export/import backup:** tạo bản backup để khôi phục cùng hoặc instance khác theo khả năng dịch vụ.
- **Eviction policy:** quyết định key nào bị loại khi đạt giới hạn memory.

Persistence không bảo vệ mọi lỗi logic, xóa nhầm hoặc corruption; backup/export cần lịch riêng và kiểm thử restore. Nếu dữ liệu là nguồn sự thật, hãy lưu ở database phù hợp và coi Redis là bản sao có thể tái tạo.

## 13. Kết nối bền vững: retry, timeout và keepalive

Azure Managed Redis khuyến nghị retry command với exponential backoff, giới hạn retry budget và cấu hình connect/command timeout hợp lý. Các nguyên tắc:

1. Connect timeout ban đầu khoảng vài giây (Microsoft đưa ra mốc tham khảo 5 giây); điều chỉnh theo môi trường và p95 thực tế.
2. Command timeout nên phù hợp latency mục tiêu; giá trị quá thấp gây false timeout, quá cao làm request treo lâu.
3. Retry có exponential backoff + jitter; không retry authentication/authorization errors như lỗi transient.
4. Giới hạn số lần retry và tổng deadline để không kéo dài request vô hạn.
5. Stagger reconnect sau failover để tránh hàng loạt instance cùng tạo connection.
6. Đóng connection/client cũ khi thay thế để tránh vượt connection quota.

Azure Managed Redis có idle connection timeout 10 phút. Nếu connection có thể nhàn rỗi lâu, bật keepalive/heartbeat dưới 10 phút hoặc gửi PING theo thiết kế phù hợp. Với workload Linux, kiểm tra TCP keepalive/retry setting của host/container; Microsoft lưu ý một số mặc định Linux có thể trì hoãn phát hiện connection đã chết nhiều phút.

### 13.1. Retry theo loại lệnh

| Lệnh/workflow | Retry sau timeout? | Lưu ý |
| --- | --- | --- |
| `GET` | Thường có thể retry | Read idempotent, nhưng giá trị có thể đã thay đổi |
| `SET key value` với cùng value | Có thể retry nếu semantics chấp nhận | Nếu có TTL, retry có thể reset TTL |
| `INCR` | Không retry mù quáng | Có thể tăng hai lần nếu lần đầu đã commit |
| `LPUSH`/append | Không retry mù quáng | Có thể tạo duplicate |
| `DEL` | Thường idempotent theo trạng thái cuối | Cần xét side effect/application event |
| Lua script/transaction | Phụ thuộc nội dung | Dùng operation ID/deduplication khi có side effect |

Không chuyển mọi exception thành cache miss rồi gọi database vô hạn. Cần circuit breaker hoặc giới hạn concurrency để Redis outage không làm database nguồn quá tải.

## 14. Monitoring và chẩn đoán

Theo dõi cả application và cache:

| Tầng | Chỉ số |
| --- | --- |
| Spring Cache | Hit/miss, evictions, cache operation latency |
| Lettuce | Active connections, reconnect count, command latency, timeout, connection errors |
| Entra | Token acquisition failure, refresh failure, AUTH/re-authentication errors |
| Azure Managed Redis | CPU, memory, connected clients, throughput, latency, shard health, failover/maintenance event |
| Active geo-replication | Replication health/lag và trạng thái group |
| Application | p50/p95/p99, fallback rate, database load khi Redis unavailable |

Spring Data Redis cache statistics có thể bật qua `RedisCacheManagerBuilder.enableStatistics()`; số liệu là local snapshot theo process, không tự động là tổng cluster. Đưa metrics về hệ thống monitoring tập trung và tránh log cache value/token/PII.

Khi lỗi kết nối:

1. Kiểm tra FQDN/port và DNS resolve từ đúng pod/VM.
2. Kiểm tra private network, firewall, route, TLS và certificate validation.
3. Kiểm tra Entra principal có được thêm vào Redis user và scope token là `https://redis.azure.com/.default`.
4. Xác minh token được refresh trước expiry và re-authentication bật.
5. Kiểm tra clustering policy có khớp standalone/cluster client không.
6. Xem connected clients, quota, CPU, memory, failover và maintenance event.
7. Chạy Azure CLI `az redisenterprise test-connection` để kiểm tra end-to-end nếu có quyền.

## 15. Kiểm thử

### 15.1. Unit test

Mock repository/cache abstraction để kiểm tra business rule, invalidation và fallback khi cache miss/error. Unit test không xác minh TLS, token, Redis command support hoặc cluster redirection.

### 15.2. Local integration test

Dùng Redis container (Testcontainers hoặc Docker Compose) để kiểm tra:

- RedisTemplate serializer/deserializer.
- Repository CRUD và keyspace mapping.
- `@Cacheable`, `@CachePut`, `@CacheEvict`.
- TTL expiration và prefix isolation.
- Serialization compatibility giữa các phiên bản application.
- Lua script, transaction hoặc Pub/Sub nếu ứng dụng sử dụng.

Local Redis không mô phỏng đầy đủ Azure Entra, Redis Enterprise clustering policy, private networking, token refresh, geo-replication, quota và failover.

### 15.3. Azure integration test

Trên Azure test cache, xác minh:

- Managed Identity hoặc service principal lấy token đúng scope.
- Principal được thêm vào cache và có quyền command/key phù hợp.
- TLS và private endpoint hoạt động.
- OSS cluster client hoặc Enterprise standalone client đúng policy.
- Token được refresh và re-authenticate khi connection sống lâu.
- Failover/maintenance gây reconnect và request phục hồi trong SLA.
- TTL/eviction, persistence, export/import và restore theo cấu hình.
- Active geo-replication và application routing nếu use case cần đa vùng.

### 15.4. Test vòng đời ứng dụng

| Sự kiện | Điều cần xác minh |
| --- | --- |
| Application startup | Connection factory khởi tạo đúng; readiness không tạo request storm |
| Token gần expiry | Provider cấp token mới, Lettuce gửi AUTH lại |
| Application rolling restart | Client cũ đóng sạch, client mới kết nối không vượt quota |
| Redis maintenance/failover | Request timeout/reconnect, retry an toàn, cache fallback hoạt động |
| Redis unavailable | Database nguồn không bị thundering herd |
| Application shutdown | Subscription, connection factory và token provider được đóng |
| Cache migration | Key format, TTL, serialization và data loss được đối soát |

## 16. Migration từ Azure Cache for Redis sang Azure Managed Redis

Một kế hoạch migration nên đi theo các bước:

1. **Inventory:** SKU, capacity, endpoint, port, TLS, Entra/access key, clustering, modules, commands, Pub/Sub, Lua, key count và traffic.
2. **Compatibility:** kiểm tra Redis version, command support, cluster behavior, key hash slot và serializer.
3. **Provision target:** chọn region/tier, clustering policy, modules, HA, network, Entra và active geo-replication ngay từ đầu.
4. **Identity:** thêm Managed Identity/service principal vào target Redis user, cấp quyền tối thiểu và test token refresh.
5. **Client:** cập nhật host/port, Lettuce topology và credential provider; không dùng cấu hình ACR cũ một cách máy móc.
6. **Data strategy:** xác định cache có thể warm lại hay cần export/import/dual-write; Redis cache không nhất thiết cần copy toàn bộ key nếu nguồn dữ liệu có thể tái tạo.
7. **Canary:** chuyển một instance/traffic nhỏ, đo hit ratio, latency, error, CPU, memory và reconnect.
8. **Cutover:** chuyển traffic theo kế hoạch, có rollback window và không ghi song song không kiểm soát.
9. **Reconcile:** so sánh key count, critical data, TTL, stale data và business behavior.
10. **Retire source:** chỉ xóa cache cũ khi xác nhận workload không còn kết nối và retention/rollback window đã kết thúc.

Nếu cache là session store hoặc giữ dữ liệu không thể tái tạo, migration cần chiến lược consistency/dual-write/maintenance window riêng. Không coi việc đổi DNS/endpoint là migration dữ liệu hoàn chỉnh.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng starter Azure Cache for Redis rồi nghĩ mọi cấu hình áp dụng cho Azure Managed Redis | Sai endpoint, auth hoặc topology | Phân biệt ACR và AMR; cấu hình AMR theo Lettuce/Redis auth extension |
| Chọn OSS cluster nhưng dùng standalone client | Redirect/cluster routing lỗi | Dùng RedisClusterConfiguration/RedisClusterClient |
| Chọn Enterprise policy nhưng dùng cluster assumptions | Command discovery bị chặn | Dùng single endpoint client và bỏ cluster-management commands |
| Dùng access key lâu dài | Secret rotation và lộ key | Entra Managed Identity và token refresh |
| Lấy token một lần rồi giữ làm password | Connection lỗi khi token hết hạn | TokenBasedRedisCredentialsProvider + re-authentication |
| Không đóng token provider/client | Thread, connection và background task rò rỉ | Spring lifecycle bean + destroy method |
| Không đặt TTL | Key tồn tại vô hạn, memory tăng | TTL theo cache domain và eviction policy |
| Cho rằng TTL reset khi đọc | Key hết hạn dù vẫn được truy cập | Phân biệt TTL và TTI; dùng GETEX/TTI nhất quán |
| Dùng JDK serialization mặc định giữa nhiều service | Khó tương thích và rủi ro deserialization | JSON/schema version, serializer rõ ràng |
| Clear cache bằng KEYS trên keyspace lớn | Block/latency tăng | SCAN batch strategy với Lettuce |
| Retry INCR/LPUSH sau timeout mù quáng | Duplicate side effect | Idempotency key hoặc xác minh trạng thái |
| Dùng Redis như database chính | Mất dữ liệu khi eviction/outage | Lưu nguồn sự thật ở database; cache-aside fallback |
| Không chuẩn bị retirement Azure Cache for Redis | Bị động khi tới hạn dịch vụ | Lập migration trước mốc retirement |

## 18. Bài tập thực hành

**Bài tập 1 — Spring Cache.** Tạo Spring Boot service đọc Product từ database. Dùng `@Cacheable`, `@CachePut`, `@CacheEvict`; kiểm tra cache hit/miss và invalidation khi update/delete.

**Bài tập 2 — TTL.** Cấu hình cache chi tiết sản phẩm 10 phút và kết quả tìm kiếm 2 phút. Chứng minh TTL không reset chỉ bằng GET; bật TTI-like với `enableTimeToIdle()` và Redis 6.2+ rồi so sánh khi đọc qua Cache API và RedisTemplate.

**Bài tập 3 — Azure Cache starter.** Kết nối một cache hiện hữu bằng `spring-cloud-azure-starter-data-redis-lettuce`. Thử Entra passwordless và access key ở môi trường test; xác minh TLS, port và Redis username.

**Bài tập 4 — Azure Managed Redis Entra.** Tạo AMR với OSS clustering policy, gán system-assigned Managed Identity cho workload, thêm principal vào Redis user, cấu hình `redis-authx-entraid` và Lettuce re-authentication. Kiểm tra token refresh mà không log token.

**Bài tập 5 — Clustering policy.** So sánh OSS và Enterprise policy. Xác định client class, multi-key command, hash slot và module RediSearch; giải thích lựa chọn nào cần tạo lại cache khi muốn đổi.

**Bài tập 6 — Failover.** Mô phỏng Redis connection interruption trong test environment. Đo reconnect time, p95, retry count và fallback rate. Chứng minh `GET` retry an toàn hơn `INCR` retry mù quáng.

**Bài tập 7 — Cache stampede.** Cho 100 request cùng gọi một key vừa hết TTL. Đo số query database và thử jitter/single-flight/stale-while-revalidate.

**Bài tập 8 — Migration.** Lập kế hoạch chuyển Azure Cache for Redis sang Azure Managed Redis trước mốc retirement phù hợp. Bao gồm inventory, endpoint, Entra, clustering, modules, data strategy, canary, cutover, rollback và reconciliation.

## 19. Ghi nhớ

- Spring Data Redis cung cấp **RedisTemplate, repositories và Spring Cache**; Lettuce là client quản lý connection/protocol/topology.
- Spring Cloud Azure starter `spring-cloud-azure-starter-data-redis-lettuce` được tài liệu Spring Azure mô tả cho **Azure Cache for Redis**; Azure Managed Redis cần đánh giá riêng Entra token provider và clustering policy.
- Azure Managed Redis bật Entra và tắt access key mặc định cho cache mới; dùng `redis-authx-entraid`, scope `https://redis.azure.com/.default` và tự động re-authenticate trước khi token hết hạn.
- **OSS clustering policy** cần cluster-aware client; **Enterprise policy** dùng single endpoint. Modules và một số lựa chọn phải chốt khi provision.
- Redis Cache TTL không reset khi đọc; TTI-like cần GETEX/Redis 6.2+ và mọi đường truy cập phải tuân thủ.
- `LettuceConnectionFactory` và token provider có lifecycle riêng; đóng client/provider khi Spring context shutdown.
- Azure Managed Redis có thể failover/patch và đóng connection; dùng reconnect, exponential backoff, jitter, keepalive dưới idle timeout 10 phút và retry có idempotency.
- Redis nên là cache có thể tái tạo trừ khi có thiết kế durability riêng. Dùng database nguồn, TTL, eviction, backup/persistence và geo-replication theo RPO/RTO.
- Azure Cache for Redis đang retirement; lên kế hoạch chuyển Basic/Standard/Premium trước 30/09/2028 và Enterprise/Enterprise Flash trước 31/03/2027.

## 20. Tài liệu tham khảo

- [Spring Cloud Azure — Connect Spring Boot to Azure Cache for Redis](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-initializer-java-app-with-redis-cache)
- [Spring Cloud Azure developer guide và starter version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
- [Azure Managed Redis — Java quickstart](https://learn.microsoft.com/en-us/azure/redis/java-get-started)
- [Azure Managed Redis — Microsoft Entra authentication](https://learn.microsoft.com/en-us/azure/redis/entra-for-authentication)
- [Redis Lettuce — Connect to Azure Managed Redis](https://redis.io/docs/latest/develop/clients/lettuce/amr/)
- [Lettuce — Connecting Redis and streaming credentials](https://redis.github.io/lettuce/user-guide/connecting-redis/)
- [Spring Data Redis — Redis Cache, TTL và TTI](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Azure Managed Redis — Clustering policy](https://learn.microsoft.com/en-us/azure/redis/choose-clustering-policy)
- [Azure Managed Redis — Failover and patching](https://learn.microsoft.com/en-us/azure/redis/failover)
- [Azure Managed Redis — Connection resilience](https://learn.microsoft.com/en-us/azure/redis/best-practices-connection)
- [Azure Managed Redis — Reliability, backup and geo-replication](https://learn.microsoft.com/en-us/azure/reliability/reliability-managed-redis)
- [Azure Cache for Redis — What's New and retirement dates](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-whats-new)
