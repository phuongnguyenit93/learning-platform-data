# Thiết kế namespace cho nhiều môi trường và khách thuê trong Spring Data Redis

Khi một ứng dụng lưu dữ liệu vào Redis, mỗi khóa là một chuỗi byte được Redis Server dùng để xác định giá trị. Redis không tự hiểu rằng khóa nào thuộc **môi trường development, staging, production** hay thuộc **khách thuê (tenant)** nào. Nếu các ứng dụng cùng ghi những tên khóa như `cart:42` hoặc `session:123`, rất dễ xảy ra va chạm tên, đọc nhầm dữ liệu hoặc xóa nhầm dữ liệu của hệ thống khác.

**Namespace** là quy ước đưa thông tin về hệ thống, môi trường, phiên bản cấu trúc, phạm vi dữ liệu và tenant vào tên khóa Redis. Ví dụ:

```text
shop:prod:v1:tenant:acme:cart:c-42
shop:prod:v1:tenant:beta:cart:c-42
shop:staging:v1:tenant:acme:cart:c-42
shop:prod:v1:global:feature:checkout
```

Bốn khóa này khác nhau mặc dù hai khách thuê có cùng ID giỏ hàng `c-42`. Namespace giúp ứng dụng định danh và quản lý dữ liệu nhất quán, nhưng **không phải hàng rào bảo mật**: Redis vẫn xem mỗi khóa là một tên thuộc cùng không gian khóa của Redis database. Bảo vệ dữ liệu giữa tenant còn cần kiểm tra quyền truy cập ở ứng dụng và, khi yêu cầu cách ly cao, cách ly Redis instance/cluster hoặc cơ chế truy cập phù hợp.

Trong Spring Data Redis, namespace phải được tính đến ở mọi đường ghi/đọc: `StringRedisTemplate`, `RedisTemplate`, `RedisCacheManager`, Redis Repository, session, distributed lock, rate limiter và các tác vụ nền. Chỉ thêm prefix cho một vài lệnh `SET` sẽ không tạo ra kiến trúc namespace thống nhất.

## 1. Vì sao cần namespace?

Giả sử một dịch vụ thương mại điện tử có:

- Ba môi trường: `dev`, `staging`, `prod`.
- Hai khách thuê: `acme` và `beta`.
- Nhiều loại dữ liệu: cache sản phẩm, giỏ hàng, phiên đăng nhập, kết quả tính giá và khóa idempotency.
- Một Redis Server đang phục vụ nhiều dịch vụ hoặc nhiều môi trường.

Nếu dùng tên khóa `cart:42` ở mọi nơi:

| Hoạt động | Hậu quả có thể xảy ra |
|---|---|
| Dev ghi đè `cart:42` của production | Dữ liệu sản xuất bị thay đổi |
| Tenant `acme` và `beta` đều dùng cart ID `42` | Tenant này có thể thấy dữ liệu của tenant kia nếu ứng dụng truy cập sai |
| Service giỏ hàng và service thanh toán cùng dùng `lock:42` | Hai luồng nghiệp vụ vô tình chặn nhau |
| Một phiên bản phần mềm thay đổi kiểu dữ liệu dưới cùng key | Bản cũ đọc lỗi định dạng hoặc ghi đè dữ liệu |
| Script dọn cache xóa theo tên quá rộng | Xóa dữ liệu không thuộc phạm vi cần dọn |

Namespace giải quyết vấn đề **đặt tên có quy tắc** và tạo cơ sở cho các thao tác vận hành theo phạm vi. Nó không tự kiểm soát ai được gọi lệnh Redis.

## 2. Mô hình tên khóa đề xuất

Một cấu trúc dễ đọc và dễ mở rộng:

```text
<application>:<environment>:<schema-version>:<scope>:<tenant-id?>:<resource>:<object-id>
```

Trong đó, dấu `:` là ký tự phân tách do nhóm phát triển quy ước, không phải cú pháp namespace đặc biệt của Redis.

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| `application` | Nhận diện ứng dụng/dịch vụ sở hữu dữ liệu | `shop`, `billing` |
| `environment` | Phân biệt môi trường triển khai | `dev`, `staging`, `prod` |
| `schema-version` | Phân biệt đời định dạng và quy ước key | `v1`, `v2` |
| `scope` | Xác định loại phạm vi dữ liệu | `tenant` hoặc `global` |
| `tenant-id` | Định danh tenant trong phạm vi `tenant` | `acme`, `beta` |
| `resource` | Loại nghiệp vụ hoặc cấu trúc dữ liệu | `cart`, `product`, `rate-limit` |
| `object-id` | ID của đối tượng hoặc mục đích thao tác | `c-42`, `sku-100` |

Ví dụ với dữ liệu thuộc tenant:

```text
shop:prod:v1:tenant:acme:cart:c-42
│    │    │  │      │    │    └── ID giỏ hàng
│    │    │  │      │    └─────── loại dữ liệu
│    │    │  │      └──────────── tenant ID
│    │    │  └─────────────────── dữ liệu theo tenant
│    │    └────────────────────── phiên bản quy ước
│    └─────────────────────────── môi trường
└──────────────────────────────── ứng dụng sở hữu key
```

Ví dụ với dữ liệu dùng chung **trong một môi trường**:

```text
shop:prod:v1:global:feature:checkout
shop:prod:v1:global:currency-rate:usd-vnd
```

`global` ở đây chỉ nghĩa là không thuộc tenant cụ thể; nó **không có nghĩa dùng chung giữa các môi trường**, cũng không mặc nhiên là dữ liệu công khai.

### Quy tắc nhất quán

1. Dùng một kiểu chữ và dấu phân tách nhất quán, chẳng hạn chữ thường và dấu `:`.
2. Quy định rõ thứ tự các thành phần; tránh nơi dùng `tenant:app:...`, nơi khác dùng `app:tenant:...`.
3. Với dữ liệu gắn tenant, **tenant ID là thành phần bắt buộc**. Không tự bỏ tenant khi không có context.
4. Không đưa dữ liệu cá nhân dễ đọc như email, số điện thoại, access token hoặc mật khẩu vào key.
5. Phân biệt tên **resource** với **ID**; một đối tượng có thể trùng ID với resource khác mà không va chạm.
6. Có quy ước cụ thể cho khóa phụ như index, lock, counter và phiên bản định dạng, thay vì sáng tạo prefix mới ở mỗi service.

### Các ví dụ đầy đủ

| Mục đích | Key |
|---|---|
| Giỏ hàng tenant `acme` | `shop:prod:v1:tenant:acme:cart:c-42` |
| Giỏ hàng tenant `beta` cùng ID | `shop:prod:v1:tenant:beta:cart:c-42` |
| Sản phẩm của tenant | `shop:prod:v1:tenant:acme:product:sku-100` |
| Số lượt yêu cầu theo tenant và user | `shop:prod:v1:tenant:acme:rate-limit:user-9` |
| Khóa idempotency cho đơn hàng | `shop:prod:v1:tenant:acme:idempotency:req-7f1` |
| Feature flag của môi trường | `shop:prod:v1:global:feature:new-checkout` |
| Cùng giỏ hàng trong staging | `shop:staging:v1:tenant:acme:cart:c-42` |
| Dịch vụ khác sở hữu dữ liệu | `billing:prod:v1:tenant:acme:invoice:inv-52` |

**Lưu ý:** Nếu một loại dữ liệu thực sự thuộc user bên trong tenant, có thể thêm một cấp `user` khi cần, chẳng hạn `shop:prod:v1:tenant:acme:user:u-9:preferences`. Đây là quyết định mô hình dữ liệu, không phải lý do để bỏ kiểm tra ủy quyền của user.

## 3. Phân biệt môi trường: prefix và cách ly hạ tầng

Có ba chiến lược triển khai thường gặp:

| Chiến lược | Mức độ tách biệt | Phù hợp với |
|---|---|---|
| Cùng Redis database, khác prefix theo môi trường | Tách biệt **logic** theo tên key, chia sẻ RAM/CPU/network/config | Môi trường thử nghiệm nhỏ, đã chấp nhận chia sẻ tài nguyên |
| Cùng Redis instance, khác Redis logical DB number | Tách biệt theo DB của Redis trong một số chế độ standalone; vẫn chia sẻ tài nguyên và giới hạn | Tình huống giới hạn, không dùng làm ranh giới bảo mật |
| Redis instance/cluster riêng cho production và môi trường khác | Tách biệt cấu hình, tài nguyên và phạm vi vận hành tốt hơn | Production, dữ liệu quan trọng, yêu cầu an toàn triển khai |

**Khuyến nghị:** Production thường nên dùng Redis instance/cluster độc lập với development và staging. Ngay cả khi đã cách ly vật lý, vẫn nên có prefix ứng dụng và phiên bản để tránh va chạm giữa các service trong cùng môi trường và hỗ trợ điều tra.

Không dựa vào `SELECT 1`, `SELECT 2` làm chiến lược namespace có thể áp dụng mọi nơi: Redis Cluster dùng DB số 0 và không hỗ trợ chuyển logical database theo cách Redis standalone truyền thống. Ngoài ra, các logical DB cùng instance vẫn chia sẻ khả năng xử lý, bộ nhớ, cấu hình eviction và rủi ro thao tác quản trị.

### Cấu hình theo deployment

Ví dụ trên Spring Boot:

```yaml
# application.yml
app:
  redis:
    namespace:
      application: shop
      environment: prod
      schema: v1

spring:
  data:
    redis:
      host: redis-prod.internal
      port: 6379
```

Giá trị minh họa; trong hệ thống thực tế, `environment` và endpoint Redis nên được cung cấp từ cấu hình triển khai hoặc profile phù hợp. **Không hardcode `prod` trong mã Java**, không để profile local vô tình trỏ vào Redis production, và không xem biến tên môi trường là bằng chứng quyền truy cập.

Khi chạy nhiều instance ứng dụng thuộc **cùng môi trường và cùng phiên bản cấu trúc**, chúng phải dùng cùng quy ước namespace. Nếu mỗi instance tự thêm hostname hoặc random UUID vào prefix, các instance sẽ không chia sẻ cache như thiết kế.

## 4. Multi-tenancy: tenant ID phải là một phần định danh dữ liệu

Một hệ thống nhiều khách thuê có thể chọn mô hình database riêng cho từng tenant, hoặc nhiều tenant dùng chung một Redis. Với mô hình dùng chung, key cần chứa **tenant ID ổn định**:

```text
shop:prod:v1:tenant:acme:cart:c-42
shop:prod:v1:tenant:beta:cart:c-42
```

Hai khóa có tên đối tượng giống nhau vẫn không va chạm nhờ tenant ID.

Tuy nhiên, **prefix không thay cho authorization**. Nếu ứng dụng cho người dùng `acme` gửi trực tiếp `tenantId=beta` rồi ghép thành tên key của `beta`, họ vẫn có thể truy cập nhầm dữ liệu. Phân tách tên khóa chỉ hiệu quả khi hệ thống kiểm tra ngữ cảnh tenant đáng tin cậy ở phía server.

### Nguồn tenant ID đáng tin cậy

Trong ứng dụng web:

1. Xác thực request bằng phiên, access token hoặc cơ chế định danh được hệ thống chấp nhận.
2. Từ danh tính đã xác thực, xác định tenant mà người dùng được phép truy cập.
3. Với các thao tác cho phép chọn tenant, kiểm tra người dùng có quyền trên tenant được chọn.
4. Chỉ sau bước đó mới truyền tenant ID đã được xác nhận vào service/repository và key builder.

Một request header như `X-Tenant-Id` **chỉ là thông tin do client gửi** nếu chưa được kiểm tra. Không nên lấy header đó rồi ghép key Redis trực tiếp.

### Truyền tenant tường minh vào service

Nên thiết kế phương thức nghiệp vụ nhận tenant đã được xác minh:

```java
String saveCart(String authorizedTenantId, String cartId, String cartJson);
String findCart(String authorizedTenantId, String cartId);
```

Cách này giúp quan hệ tenant → dữ liệu được nhìn thấy ngay ở API service và dễ dùng trong các tác vụ nền. Nếu ứng dụng dùng `ThreadLocal` để lưu tenant hiện tại, cần đặc biệt chú ý luồng async, thread pool và WebFlux/Reactor: context có thể không tự truyền qua thread, gây mất tenant hoặc lẫn tenant. Đừng phụ thuộc một global mutable tenant ID cho tất cả request.

### Định dạng tenant ID

Tenant ID nên là **mã nội bộ ổn định, không chứa dữ liệu nhạy cảm và không tái sử dụng cho tenant khác**. Ví dụ `acme` hoặc một opaque ID như `t-8f21`. Không nên dùng tên hiển thị công ty, email của người quản trị hay tên miền có thể đổi làm định danh chính.

Chọn một trong hai cách sau và áp dụng nhất quán:

- **Giới hạn bảng ký tự**: chỉ cho phép `[a-z0-9_-]`, với độ dài đã quy định; dùng ID được chuẩn hóa từ lúc tạo tenant.
- **Mã hóa thành phần**: nếu thực sự cần nhận ID chứa ký tự đặc biệt, dùng một thuật toán mã hóa xác định, không nhập nhằng để các dấu phân tách trong ID không làm thay đổi cấu trúc key.

Không ghép trực tiếp chuỗi người dùng nhập, ví dụ email có dấu `:` hoặc một chuỗi chứa `*`, vào công cụ tìm/xóa key. Các ký tự wildcard và dấu phân tách có thể dẫn tới thao tác sai phạm vi nếu xuất hiện trong biểu thức `MATCH`.

## 5. Tạo key tập trung trong Spring Data Redis

Để mọi service tạo cùng một loại khóa, nên gom quy tắc đặt tên vào một thành phần dùng chung. Ví dụ bên dưới sử dụng Spring Boot 3.x, Java 21 và `StringRedisTemplate`.

### 5.1. Binding cấu hình namespace

```java
package com.example.shop.redis;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.redis.namespace")
public record RedisNamespaceProperties(
        String application,
        String environment,
        String schema
) {
}
```

Đăng ký cấu hình này bằng `@EnableConfigurationProperties`:

```java
package com.example.shop.redis;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(RedisNamespaceProperties.class)
public class RedisNamespaceConfiguration {
}
```

### 5.2. Key builder có kiểm tra từng thành phần

```java
package com.example.shop.redis;

import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public final class RedisKeys {
    // Giới hạn tên component cho ví dụ học tập; ID thực tế cần có hợp đồng rõ ràng.
    private static final Pattern COMPONENT =
            Pattern.compile("[a-zA-Z0-9_-]{1,64}");

    private final String root;

    public RedisKeys(RedisNamespaceProperties properties) {
        root = component(properties.application()) + ":"
             + component(properties.environment()) + ":"
             + component(properties.schema());
    }

    public String root() {
        return root;
    }

    public String tenant(String tenantId, String resource, String objectId) {
        return root + ":tenant:"
                + component(tenantId) + ":"
                + component(resource) + ":"
                + component(objectId);
    }

    public String global(String resource, String objectId) {
        return root + ":global:"
                + component(resource) + ":"
                + component(objectId);
    }

    public String cacheItem(String tenantId, String objectId) {
        // Dùng với prefix riêng của RedisCacheManager.
        return "tenant:" + component(tenantId) + ":id:" + component(objectId);
    }

    private static String component(String value) {
        if (value == null || !COMPONENT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Invalid Redis key component"
            );
        }
        return value;
    }
}
```

Ví dụ:

```java
redisKeys.tenant("acme", "cart", "c-42");
// shop:prod:v1:tenant:acme:cart:c-42

redisKeys.tenant("beta", "cart", "c-42");
// shop:prod:v1:tenant:beta:cart:c-42

redisKeys.global("feature", "checkout");
// shop:prod:v1:global:feature:checkout
```

Mã ví dụ chỉ chấp nhận thành phần không có dấu `:`, dấu `*` hay ký tự khoảng trắng. Nếu ID ngoài đời thực chứa Unicode, dấu chấm, dấu slash hoặc ký tự khác, phải quyết định **cách chuẩn hóa/mã hóa ổn định** thay vì âm thầm bỏ ký tự. Nếu ID quá dài, có thể dùng opaque ID hoặc một digest được tạo có chủ đích; cần bảo đảm cách mã hóa không làm mất khả năng đối chiếu ngược với định danh nghiệp vụ cần thiết.

Việc validate cú pháp của `tenantId` **không xác nhận quyền truy cập**. Nó chỉ ngăn key sai định dạng. Authorization vẫn phải xảy ra trước khi dùng tenant đó để đọc hoặc ghi.

### 5.3. Dùng cùng key builder khi đọc, ghi và xóa

```java
package com.example.shop.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartCache {
    private final StringRedisTemplate redis;
    private final RedisKeys keys;

    public CartCache(StringRedisTemplate redis, RedisKeys keys) {
        this.redis = redis;
        this.keys = keys;
    }

    public void save(
            String authorizedTenantId,
            String cartId,
            String cartJson
    ) {
        String key = keys.tenant(authorizedTenantId, "cart", cartId);
        redis.opsForValue().set(key, cartJson, Duration.ofMinutes(30));
    }

    public String find(String authorizedTenantId, String cartId) {
        String key = keys.tenant(authorizedTenantId, "cart", cartId);
        return redis.opsForValue().get(key);
    }

    public void delete(String authorizedTenantId, String cartId) {
        String key = keys.tenant(authorizedTenantId, "cart", cartId);
        redis.delete(key);
    }
}
```

Lưu ý `cartJson` chỉ là chuỗi minh họa; ở dự án thực tế nên thống nhất cơ chế serialization và xác thực dữ liệu. Điểm chính là **cả ba thao tác đều đi qua cùng key builder** nên không có tình huống ghi có tenant nhưng đọc hoặc xóa lại quên tenant.

### 5.4. Không chỉ ghép prefix ở lớp controller

Một thiết kế khó bảo trì:

```java
// Tránh để mỗi nơi tự quyết định format:
redis.opsForValue().set("prod:cart:" + cartId, json);
redis.opsForValue().get("tenant:" + tenantId + ":cart:" + cartId);
redis.delete("cart:" + cartId);
```

Ba câu lệnh tạo ba cấu trúc key khác nhau. Khi hệ thống lớn hơn, cùng một service có thể thao tác lên ba bản dữ liệu mà không nhận ra. Key builder tập trung còn giúp thay đổi `v1` sang `v2` có kiểm soát.

## 6. Tích hợp namespace với Spring Cache

Khi dùng `@Cacheable`, tên key cuối cùng có thể được tạo từ nhiều thành phần: **cache name**, **cache key** và **key prefix** do `RedisCacheManager` cấu hình. Vì vậy không thể giả định tên key Redis sẽ giống trực tiếp giá trị truyền vào `@Cacheable(key = ...)`.

### 6.1. Cấu hình prefix cố định cho môi trường và cache

```java
package com.example.shop.redis;

import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory factory,
            RedisKeys keys
    ) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(cacheName ->
                        keys.root() + ":cache:" + cacheName + ":")
                .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

Ở đây prefix cho cache `priceByProduct` trở thành:

```text
shop:prod:v1:cache:priceByProduct:
```

Do `RedisCacheManager` đã thêm prefix ứng dụng/môi trường/phiên bản/cache name, phần key do phương thức `@Cacheable` tạo ra vẫn **phải chứa tenant**.

### 6.2. Đưa tenant vào cache key

```java
package com.example.shop.service;

import com.example.shop.redis.RedisKeys;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {

    @Cacheable(
        cacheNames = "priceByProduct",
        key = "@redisKeys.cacheItem(#p0, #p1)"
    )
    public String loadPrice(
            String authorizedTenantId,
            String productId
    ) {
        // Truy vấn giá đã được tính theo tenant từ nguồn dữ liệu chính.
        return loadFromPrimaryStore(authorizedTenantId, productId);
    }

    private String loadFromPrimaryStore(String tenantId, String productId) {
        // Mã minh họa: ứng dụng thực tế thay bằng repository/service nghiệp vụ.
        return "price-for-" + tenantId + "-" + productId;
    }
}
```

Với cấu hình ở trên, key Redis cho `loadPrice("acme", "sku-100")` có dạng:

```text
shop:prod:v1:cache:priceByProduct:tenant:acme:id:sku-100
```

Đây là một biến thể hợp lệ của schema namespace dành riêng cho Spring Cache: **cache name được đặt trước scope tenant** vì `RedisCacheManager` xây prefix ở mức cache. Thứ tự này phải được tài liệu hóa và áp dụng nhất quán cho các cache tương tự.

**Lỗi nghiêm trọng cần tránh:**

```java
@Cacheable(cacheNames = "priceByProduct", key = "#p1")
public String loadPrice(String tenantId, String productId) { ... }
```

Nếu hai tenant cùng dùng `productId=sku-100`, họ sẽ dùng chung cache entry. Với dữ liệu khác nhau theo tenant, kết quả có thể rò rỉ hoặc sai giá. Việc nguồn dữ liệu chính kiểm tra quyền tốt **không cứu được một cache hit trả kết quả của tenant khác**, vì body phương thức có thể không được gọi khi cache hit.

Điều tương tự áp dụng cho `@CachePut` và `@CacheEvict`: các annotation đọc/ghi/xóa cùng một cache phải dùng cách tính key tương thích. Nếu giá phụ thuộc currency, region, loại người dùng hoặc biến thể nghiệp vụ, phải cân nhắc đưa những chiều đó vào cache key hoặc tách cache theo ngữ cảnh thích hợp.

### 6.3. Đừng giả định cache prefix có thể tự đổi theo từng request

`computePrefixWith(cacheName -> ...)` được cấu hình ở cấp cache name; callback không nhận tenant đang được xác thực trong từng request. Nếu muốn một cache chung xử lý nhiều tenant, hãy đưa tenant vào **phần key** do `@Cacheable` tạo hoặc viết `KeyGenerator` phù hợp. Tránh lấy tenant từ một biến global hoặc ThreadLocal thiếu cơ chế truyền context an toàn.

## 7. Namespace khi sử dụng Redis Repository

Redis Repository lưu entity theo keyspace, ID và có thể duy trì các key phụ như ID set và secondary index. Cơ chế này cần được xử lý riêng; không thể chỉ giả định `@RedisHash` tự động dùng tenant hiện tại.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("orderViews")
public class OrderView {
    @Id
    private String id;

    @Indexed
    private String tenantId;

    private String orderNumber;

    // Constructors, getters, setters...
}
```

Với keyspace `orderViews`, entity có ID `42` của tenant `acme` và entity có ID `42` của tenant `beta` sẽ **va chạm** nếu dùng chung Redis database. Giải pháp ở mức ID là tạo định danh tổng hợp:

```text
acme~42
beta~42
```

Trong ví dụ này, `~` chỉ là dấu phân tách được chọn vì hai thành phần đầu vào đã được giới hạn không chứa `~`. Có thể thay bằng các định danh opaque/UUID duy nhất toàn hệ thống.

Repository sẽ hình thành key tương ứng như:

```text
orderViews:acme~42
orderViews:beta~42
```

Ví dụ interface:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderViewRepository
        extends CrudRepository<OrderView, String> {

    List<OrderView> findByTenantId(String tenantId);
}
```

Với `@Indexed` trên `tenantId`, Spring Data Redis có thể duy trì secondary index để tìm những `OrderView` theo tenant. Tuy nhiên:

- `@RedisHash("orderViews")` là keyspace cố định từ metadata entity trong ví dụ, **không tự động chuyển thành `orderViews:<tenantId>` theo request**.
- Các set ID và index do repository quản lý có thể chứa dữ liệu của nhiều tenant trong cùng một keyspace.
- ID tổng hợp giảm va chạm key, nhưng không tự thực thi chính sách truy cập. Một lời gọi `findById("beta~42")` vẫn phải được kiểm tra quyền tenant ở lớp nghiệp vụ.
- `findAll()` trên repository chung có thể trả dữ liệu của nhiều tenant. Đừng xuất nó trực tiếp cho tenant hiện tại.
- Thay đổi dữ liệu qua lệnh Redis trực tiếp mà bỏ qua repository có thể làm index bị lỗi thời.

Nếu ứng dụng **phải dùng namespace đầy đủ có environment/tenant ngay trong từng key repository**, hãy thiết kế cấu hình keyspace/mapping chuyên biệt, ID scheme và các index phụ phù hợp, hoặc dùng `RedisTemplate` cùng key builder cho phần dữ liệu đó. Không giả định chỉ thêm một parameter `tenantId` vào hàm repository sẽ đổi keyspace của `@RedisHash`.

Trong production đa tenant, tính đúng đắn của tenant isolation quan trọng hơn sự tiện lợi của `CrudRepository`. Cần cân nhắc khi nào repository chung phù hợp và khi nào nên dùng mô hình dữ liệu Redis riêng biệt hoặc storage cách ly.

## 8. Redis Cluster: hash tag có ảnh hưởng đến namespace

Redis Cluster phân phối key vào các **hash slot**. Nếu một key chứa một cặp dấu ngoặc nhọn hợp lệ `{...}`, phần nằm giữa cặp ngoặc đó có thể được dùng làm **hash tag** để quyết định slot.

Ví dụ:

```text
shop:prod:v1:tenant:{acme}:cart:c-42
shop:prod:v1:tenant:{acme}:cart:items:c-42
shop:prod:v1:tenant:{beta}:cart:c-42
```

Các key có cùng hash tag `{acme}` được đặt vào cùng hash slot. Điều này hữu ích khi một thao tác đa key, script hoặc transaction Redis Cluster yêu cầu các key tham gia nằm cùng slot.

Tuy vậy, **không nên bọc toàn bộ tenant ID trong `{...}` cho mọi key một cách máy móc**. Nếu tenant `acme` có lượng truy cập lớn, tất cả key mang tag `{acme}` sẽ dồn vào một slot, dễ tạo điểm nóng và làm giảm hiệu quả phân phối dữ liệu của cluster.

Chỉ dùng hash tag khi có yêu cầu thao tác đa key cụ thể. Ví dụ muốn hai key của cùng một giỏ hàng ở cùng slot:

```text
shop:prod:v1:tenant:acme:cart:{acme~c-42}:header
shop:prod:v1:tenant:acme:cart:{acme~c-42}:items
```

Hai key có cùng tag `{acme~c-42}`. Những giỏ hàng khác có tag khác, cho phép phân bố vào nhiều slot hơn. Nội dung trong dấu ngoặc vẫn cần được xác định từ ID đã xác thực và đã chuẩn hóa.

**Cần nhớ:** Prefix trước dấu `{...}` không làm hai key chung slot nếu hash tag khác nhau. Ngược lại, cùng hash tag sẽ chung slot dù prefix bên ngoài khác nhau. Redis hash slot là cơ chế định tuyến dữ liệu, không phải cơ chế kiểm soát quyền tenant.

## 9. TTL, eviction và quota theo tenant

Namespace xác định key thuộc ai và dùng làm gì, nhưng **không tự cấp bộ nhớ hay tuổi thọ riêng** cho từng tenant.

Ví dụ:

```redis
SET shop:prod:v1:tenant:acme:cart:c-42 "{\"count\":2}" EX 1800
SET shop:prod:v1:tenant:beta:cart:c-42 "{\"count\":1}" EX 1800
TTL shop:prod:v1:tenant:acme:cart:c-42
```

Mỗi key có TTL riêng. Khi đến hạn, Redis xử lý expiration; nếu Redis có giới hạn `maxmemory` và policy eviction, key có thể bị loại vì áp lực bộ nhớ trước khi TTL hết. Redis không mặc nhiên giữ “30 phút riêng cho từng tenant”.

| Nhu cầu | Cách xử lý |
|---|---|
| Giỏ hàng cần hết hạn sau 30 phút | Đặt TTL cho key cart khi ghi |
| Cache dữ liệu có thể tính lại | Đặt TTL, xử lý cache miss và theo dõi eviction |
| Tenant lớn không được chiếm hết RAM của tenant khác | Thiết kế quota/giới hạn dữ liệu ở ứng dụng, quan sát theo tenant hoặc tách Redis instance |
| Rate limit mỗi tenant | Dùng key có tenant ID, cập nhật counter và TTL theo thuật toán |
| Token/session phải hết hạn đúng chính sách | Bảo đảm TTL hoặc logic hết hạn ở ứng dụng; chuẩn bị cách xử lý khi key bị mất sớm |

Redis `maxmemory-policy` thông thường áp dụng ở phạm vi Redis instance, **không biết các phần prefix tương ứng với tenant**. Một tenant tạo rất nhiều key có thể gây eviction lên key của tenant khác nếu dùng chung bộ nhớ. Nếu yêu cầu quota hoặc tài nguyên độc lập nghiêm ngặt, cần thêm cơ chế kiểm soát hoặc cách ly hạ tầng, không chỉ thêm prefix.

## 10. Xóa dữ liệu theo namespace an toàn

Khi cần xóa cache của một tenant hoặc dọn key staging, phải bảo đảm **phạm vi** đúng. Mọi lệnh dọn dữ liệu đều có khả năng gây gián đoạn nên cần thử trên môi trường thích hợp và đánh giá số key trước khi thao tác.

### 10.1. Quan sát bằng `SCAN`

Thay vì dùng `KEYS *` trên Redis lớn, có thể duyệt theo cursor bằng `SCAN`:

```redis
SCAN 0 MATCH shop:staging:v1:tenant:acme:* COUNT 100
```

Redis trả về cursor mới và danh sách key của lần quét. Tiếp tục `SCAN <cursor> ...` cho đến khi cursor trở lại `0`. `COUNT` là gợi ý về lượng công việc cho một lần duyệt, không bảo đảm trả đúng số key.

`SCAN` không tạo snapshot nhất quán: dữ liệu có thể thay đổi trong lúc quét, có thể gặp lại một key ở những lượt khác, và không phải mọi lần gọi đều trả key. Trong Redis Cluster, việc duyệt tổng thể cần thực hiện trên các node giữ key phù hợp; một lượt quét ở một node không đại diện cho toàn cluster.

Khi chỉ muốn thống kê, nên tránh đọc nội dung của tất cả key nếu không cần; có thể dùng metrics, thống kê số lượng theo nghiệp vụ hoặc các cấu trúc tracking phù hợp.

### 10.2. Xóa từng key, theo batch, đúng tenant

Với một key cụ thể, có thể gọi:

```java
redisTemplate.delete(redisKeys.tenant("acme", "cart", "c-42"));
```

Với hàng nghìn key thuộc tenant, một job có thể duyệt `SCAN` rồi dùng `UNLINK` hoặc thao tác delete theo batch có kiểm soát. Cần giới hạn tốc độ và kiểm tra target Redis thật kỹ; `UNLINK` giải phóng bộ nhớ bất đồng bộ ở phía Redis nhưng vẫn tác động dữ liệu ngay về mặt logic.

Không dùng `FLUSHDB`, `FLUSHALL` hay một pattern quá rộng để dọn riêng một tenant trên Redis được chia sẻ. Dù key prefix được thiết kế tốt, `FLUSHDB` và `FLUSHALL` không hiểu namespace của ứng dụng.

### 10.3. Khi cần dọn dữ liệu lớn thường xuyên

Quét toàn bộ keyspace có thể tốn chi phí khi dữ liệu lớn. Có thể cân nhắc:

- Dùng TTL để key ngắn hạn tự hết hạn.
- Duy trì một set tracking các key thuộc tenant nếu cần lifecycle rõ ràng; khi ghi/xóa phải giữ metadata đồng bộ.
- Dùng version/generation trong key của cache có thể tái tạo, chuyển đọc sang namespace mới thay vì xóa ngay toàn bộ key cũ, rồi để TTL dọn dần.
- Nếu tenant có khối dữ liệu rất lớn hoặc yêu cầu xóa độc lập mạnh, cân nhắc tách Redis instance hoặc mô hình sở hữu dữ liệu khác.

Set tracking cũng có thể bị lỗi thời nếu key tự hết hạn hoặc bị eviction. Nếu dùng nó để xóa tất cả dữ liệu tenant, cần thiết kế rõ cách dọn metadata và giới hạn bộ nhớ; đừng xem set tracking là bằng chứng tuyệt đối về tất cả key hiện còn tồn tại.

## 11. Nâng cấp schema và di chuyển namespace

Namespace thường cần thay đổi khi cấu trúc dữ liệu thay đổi. Ví dụ `v1` lưu một cart dưới dạng string JSON, còn `v2` lưu cart bằng hash hoặc đổi cách tính giá. Nếu chỉ đổi code mà giữ cùng tên key, bản mới có thể gặp Redis `WRONGTYPE` hoặc đọc dữ liệu theo schema cũ.

Một chiến lược có kiểm soát:

```text
Phiên bản cũ:
shop:prod:v1:tenant:acme:cart:c-42

Phiên bản mới:
shop:prod:v2:tenant:acme:cart:c-42
```

Các bước có thể áp dụng tùy nghiệp vụ:

1. **Định nghĩa schema mới:** Đặt rõ `v2` ở key, format giá trị, TTL và cách xử lý index.
2. **Triển khai khả năng đọc phù hợp:** Với cache có thể tính lại, thử `v2` rồi cache miss thì tính từ nguồn chuẩn. Với dữ liệu cần di chuyển, thiết kế cách đọc `v1` và chuyển đổi, có kiểm tra quyền tenant.
3. **Chuyển tuyến ghi:** Bản ứng dụng mới ghi theo `v2`; tránh để các bản cũ ghi đè dữ liệu không tương thích.
4. **Theo dõi cutover:** Quan sát cache hit/miss, lỗi deserialize, dung lượng và tỉ lệ dữ liệu còn ở `v1`.
5. **Dọn `v1`:** Để TTL hết hạn hoặc chạy tác vụ xóa có kiểm soát khi chắc chắn không còn consumer dùng format cũ.

Nếu dùng **dual-write** trong giai đoạn chuyển đổi, phải định nghĩa dữ liệu nào là nguồn chuẩn, cách xử lý một lần ghi thành công một lần thất bại và cách tránh đọc trạng thái không nhất quán. Dual-write không tự mang đến tính atomic trên hai key.

Đối với dữ liệu chỉ là cache, **namespace versioning + cache miss rồi tái tạo** thường đơn giản hơn chuyển đổi mọi key. Nhưng với dữ liệu nghiệp vụ không thể tái tạo, cần một kế hoạch migration đầy đủ và nơi lưu chính đáng tin cậy.

Một cách đơn giản khác là thêm generation cho cache:

```text
shop:prod:v1:tenant:acme:cache-g3:product:sku-100
shop:prod:v1:tenant:acme:cache-g4:product:sku-100
```

Khi đổi generation, app sẽ đọc namespace `g4` và bỏ qua cache `g3`. Cách này giúp invalidation theo nhóm nhưng có thể làm tăng bộ nhớ trong giai đoạn tồn tại song song; TTL và việc dọn generation cũ vẫn cần được quản lý.

## 12. Quan sát và xử lý lỗi đa môi trường, đa tenant

Khi một key “không tìm thấy”, trước tiên xác nhận **key thực tế** mà ứng dụng đã gửi lên Redis, thay vì chỉ nhìn ID nghiệp vụ:

```text
application = shop
environment = staging
schema = v1
tenant = acme
resource = cart
id = c-42
result = shop:staging:v1:tenant:acme:cart:c-42
```

Một số lỗi phổ biến:

| Hiện tượng | Khả năng cần kiểm tra |
|---|---|
| Local có dữ liệu nhưng staging không đọc được | Khác environment/endpoint/DB/prefix |
| Tenant A đọc được dữ liệu tenant B | Thiếu tenant trong cache key, lấy tenant từ input chưa kiểm tra hoặc lỗi authorization |
| Repository `findById` trả object của tenant khác | ID không chứa tenant và không có quy tắc kiểm tra quyền tương ứng |
| Sau deploy xuất hiện nhiều cache miss | Schema version/generation thay đổi, prefix cache thay đổi hoặc TTL hết |
| Xóa cache tenant nhưng vài key vẫn còn | Quét `SCAN` chưa hết cursor, thiếu loại key/index khác hoặc có ghi mới đồng thời |
| Redis bị đầy dù key có prefix theo tenant | Prefix không tạo quota; kiểm tra TTL, eviction, số lượng và kích thước key |
| Redis Cluster báo lỗi liên quan khác slot | Các key trong thao tác đa key có hash slot khác nhau |
| Nhiều môi trường ảnh hưởng hiệu năng lẫn nhau | Các môi trường đang chia sẻ hạ tầng Redis thực tế |
| Đổi key version nhưng app cũ vẫn đọc key cũ | Rolling deployment cần thời gian tương thích hoặc kế hoạch cutover rõ |

### Logging và metrics

Để điều tra, nên log các thành phần **không nhạy cảm** như application, environment, resource, trạng thái cache hit/miss và tenant ID nội bộ đã được mã hóa hoặc che phù hợp. Không log raw key chứa token/PII. Tránh gắn toàn bộ tenant ID có cardinality lớn vào mọi label metric; lượng chuỗi thời gian có thể tăng mạnh. Với tenant quan trọng hoặc cần phân tích riêng, có thể dùng log hoặc bảng thống kê ngoài hệ metrics tổng hợp.

Theo dõi thêm:

- Tổng số key, memory, eviction, expiration ở Redis Server.
- Hit/miss và độ trễ theo cache/resource.
- Kích thước dữ liệu và tốc độ tăng theo tenant nếu hệ thống có cơ chế thống kê phù hợp.
- Lỗi do namespace mismatch, quyền tenant hoặc kiểu Redis không tương thích.
- Kết quả tác vụ cleanup/migration, đặc biệt phạm vi key đã được duyệt.

## 13. Những điều namespace không giải quyết được

### 13.1. Namespace không tự áp dụng Redis ACL

Redis ACL có khả năng giới hạn lệnh và mẫu key được truy cập khi cấu hình người dùng Redis, nhưng một prefix trong tên key **không tự kích hoạt ACL**. Nếu một application dùng cùng một Redis credential có quyền đọc mọi key, lỗi ứng dụng vẫn có thể cho phép truy cập sai tenant.

Muốn tách quyền ở cấp Redis, cần thiết kế người dùng/credential, pattern truy cập, vòng đời kết nối và phạm vi triển khai thực sự phù hợp. Một ứng dụng đơn sử dụng cùng connection cho hàng nghìn tenant thường không thể coi việc gắn prefix là thay thế cho kiểm tra quyền theo request.

### 13.2. Namespace không tự giới hạn CPU/RAM của tenant

Redis không tự đọc `:tenant:acme:` rồi cấp quota riêng. Những tenant cùng instance vẫn có thể ảnh hưởng nhau về RAM, CPU, network và chính sách eviction. Với yêu cầu cách ly nghiêm ngặt hoặc cam kết hiệu năng độc lập, cần xét instance/cluster riêng hay cơ chế hạn chế tài nguyên bên ngoài Redis.

### 13.3. Namespace không thay thế mô hình dữ liệu

Ví dụ chỉ đặt tên `shop:prod:v1:tenant:acme:order:42` không giúp đảm bảo:

- Thao tác tạo đơn chỉ xảy ra một lần.
- Cập nhật nhiều key luôn atomic.
- Một sự kiện quan trọng không bao giờ mất.
- Tenant không vượt giới hạn số đơn.
- Dữ liệu có thể khôi phục sau lỗi hạ tầng nếu chưa có persistence/backup phù hợp.

Các bảo đảm này phải được thiết kế ở lớp nghiệp vụ, thuật toán Redis, transaction/script, cơ chế lưu bền vững hoặc hạ tầng.

## 14. Bài thực hành: hai tenant, hai môi trường

Có thể thực hành trên Redis dành riêng cho học tập.

### Bước 1 — Tạo key có cùng object ID

```redis
SET shop:dev:v1:tenant:acme:cart:c-42 "dev-acme" EX 120
SET shop:dev:v1:tenant:beta:cart:c-42 "dev-beta" EX 120
SET shop:staging:v1:tenant:acme:cart:c-42 "staging-acme" EX 120
```

### Bước 2 — Đọc từng phạm vi

```redis
GET shop:dev:v1:tenant:acme:cart:c-42
GET shop:dev:v1:tenant:beta:cart:c-42
GET shop:staging:v1:tenant:acme:cart:c-42
```

Ba lệnh trả về ba giá trị khác nhau dù cùng cart ID. Khi TTL kết thúc, Redis có thể xóa từng key độc lập.

### Bước 3 — Khảo sát namespace

```redis
SCAN 0 MATCH shop:dev:v1:tenant:acme:* COUNT 100
SCAN 0 MATCH shop:staging:v1:* COUNT 100
```

Nếu cursor trả về khác `0`, phải tiếp tục quét ở các cursor sau để duyệt hết. Không nên dùng kết quả một lần `SCAN` làm bằng chứng namespace chỉ có một vài key.

### Bước 4 — Kiểm tra bằng Spring

Tạo `RedisKeys` như phần trên, sau đó dùng `CartCache.save("acme", "c-42", ...)` và `CartCache.find("acme", "c-42")`. Đổi cấu hình `environment` từ `dev` sang `staging` trong một lần chạy riêng trên Redis học tập để quan sát việc đổi prefix làm thay đổi key được truy cập.

Để kiểm tra cách ly theo tenant, thử `save("acme", "c-42", "A")` và `save("beta", "c-42", "B")` rồi đọc tương ứng. Hai giá trị phải tồn tại ở hai key khác nhau. Thử đưa `tenantId` chứa dấu `:` sẽ bị key builder từ chối theo hợp đồng đặt tên của ví dụ.

### Bước 5 — Thử quy ước phiên bản

Tạo thêm:

```redis
SET shop:dev:v2:tenant:acme:cart:c-42 "new-format" EX 120
GET shop:dev:v1:tenant:acme:cart:c-42
GET shop:dev:v2:tenant:acme:cart:c-42
```

Hai phiên bản có thể tồn tại đồng thời; ứng dụng quyết định đọc version nào và khi nào dọn dữ liệu cũ.

## 15. Bộ quy tắc sử dụng trong dự án thật

Khi xây dựng một module Spring Data Redis nhiều tenant, nên thống nhất và đưa vào mã nguồn những quy tắc sau:

1. **Một schema key được công bố:** `application:environment:version:scope:tenant:resource:id`, với ngoại lệ có chủ đích cho cache/repository.
2. **Không có key tenant thiếu tenant ID:** Mọi API đọc/ghi/xóa dữ liệu tenant nhận tenant đã xác minh.
3. **Một key builder dùng chung:** Không phân tán logic ghép chuỗi qua các controller, service và scheduled task.
4. **Kiểm soát ký tự và độ dài:** Thành phần key có định dạng không nhập nhằng; không nhúng dữ liệu cá nhân hoặc bí mật.
5. **Tách namespace khỏi quyền truy cập:** Spring Security/authorization quyết định ai được dùng tenant; prefix chỉ định vị key.
6. **TTL và retention có chủ đích:** Mỗi loại resource xác định thời hạn, khả năng tái tạo và xử lý khi mất key.
7. **Định nghĩa cơ chế invalidation:** Các thao tác `@CacheEvict`, cleanup job và thay đổi dữ liệu đều dùng cùng convention.
8. **Cân nhắc giới hạn hạ tầng:** Production quan trọng nên có Redis riêng; prefix không tạo quota hay cách ly lỗi.
9. **Giữ tính tương thích khi đổi schema:** Dùng version/generation và kế hoạch triển khai thay vì đổi format dữ liệu dưới cùng key mà không kiểm soát.
10. **Quan sát theo phạm vi an toàn:** Log metadata phù hợp, theo dõi cache miss/eviction và không đưa dữ liệu bí mật vào tên key.

### Tóm tắt khái niệm

Namespace là một **hợp đồng đặt tên** giữa các thành phần sử dụng Redis:

```text
Ứng dụng xác thực tenant
           │
           ▼
Service nhận authorizedTenantId
           │
           ▼
Key builder: app + env + version + tenant + resource + ID
           │
           ├── RedisTemplate / StringRedisTemplate
           │
           ├── RedisCacheManager + tenant-aware cache key
           │
           └── Redis Repository (cần xem kỹ keyspace và ID)
           │
           ▼
Redis Server: tập key nằm trong cùng Redis database/cluster
```

Nhờ namespace, các service và tenant có thể tránh va chạm tên và quản lý vòng đời dữ liệu có tổ chức. Quyền truy cập, quota bộ nhớ, transaction và tính bền vững vẫn cần cơ chế riêng.

## 16. Câu hỏi tự kiểm tra

**1. Tại sao chỉ dùng `cart:<id>` không phù hợp với ứng dụng đa tenant?**  
Vì ID chỉ duy nhất trong một tenant có thể trùng ID ở tenant khác, khiến hai đối tượng dùng cùng Redis key.

**2. Cùng Redis instance, dev dùng `shop:dev:...` còn prod dùng `shop:prod:...` đã được cách ly hoàn toàn chưa?**  
Chưa. Namespace tách key ở mức tên, nhưng cả hai vẫn dùng chung bộ nhớ, CPU, cấu hình Redis, quyền của credential đang dùng và rủi ro thao tác quản trị.

**3. Tại sao `@Cacheable(key = "#p1")` có thể nguy hiểm khi method nhận `tenantId` và `productId`?**  
Vì cache key chỉ chứa product ID. Hai tenant có cùng product ID có thể dùng chung cache entry; cache hit còn bỏ qua phần thực thi bên trong method, nơi thường có logic lấy dữ liệu.

**4. `@RedisHash("orders")` có tự tạo prefix tenant cho Redis Repository không?**  
Không. Keyspace được khai báo là metadata cố định trong ví dụ; cần thiết kế ID, mapping/index, kiểm tra quyền và/hoặc cấu hình keyspace chuyên biệt.

**5. Redis Cluster có cần thêm `{tenantId}` vào mọi key không?**  
Không. Hash tag hữu ích cho thao tác đa key cần cùng slot, nhưng dồn toàn bộ key của tenant lớn vào một slot có thể gây điểm nóng.

**6. Có thể xóa mọi dữ liệu tenant `acme` bằng `FLUSHDB` vì đã có prefix không?**  
Không. `FLUSHDB` xóa mọi key trong Redis logical database, không lọc theo prefix. Cần thiết kế tác vụ dọn theo phạm vi key, có kiểm soát và hiểu tác động lên hạ tầng chung.

**7. Đổi từ `v1` sang `v2` có đồng nghĩa dữ liệu cũ đã biến mất không?**  
Không. Hai namespace có thể cùng tồn tại đến khi TTL hết hạn hoặc có tác vụ cleanup; triển khai phải xác định phiên bản đang đọc và kế hoạch chuyển đổi.

**8. Vì sao validate format tenant ID vẫn chưa đủ để bảo mật?**  
Vì một ID hợp lệ như `beta` vẫn có thể là tenant mà người dùng hiện tại không được phép truy cập. Cần xác minh danh tính và quyền trước khi tạo key.

**Điều cốt lõi:** Hãy thiết kế namespace Redis thành một hợp đồng rõ ràng, được thực thi thống nhất bằng Spring Data Redis và gắn với tenant đã được xác minh. Prefix cho phép phân biệt dữ liệu; quyền truy cập và cách ly tài nguyên vẫn là những trách nhiệm độc lập của ứng dụng và kiến trúc triển khai.
