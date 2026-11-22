# Tạo chỉ mục phụ bằng Set trong Spring Data Redis

Redis là kho dữ liệu key–value: khi đã biết chính xác key, ứng dụng có thể đọc dữ liệu rất nhanh. Nhưng một câu hỏi nghiệp vụ như **“Lấy tất cả sản phẩm thuộc danh mục bàn phím”**, **“Tìm sản phẩm vừa thuộc danh mục bàn phím vừa có thương hiệu Acme”** hoặc **“Tìm các tài khoản có vai trò quản trị”** không thể được giải quyết bằng một lệnh `GET` nếu dữ liệu chỉ lưu theo ID.

Một cách xây dựng khả năng tra cứu theo thuộc tính là sử dụng **Redis Set làm chỉ mục phụ (secondary index)**. Mỗi key chỉ mục biểu diễn một điều kiện; các phần tử của Set là **ID của bản ghi** thỏa điều kiện đó. Spring Data Redis cung cấp `SetOperations<K, V>` để tạo, cập nhật, kiểm tra và kết hợp các tập ID bằng những lệnh như `SADD`, `SREM`, `SMEMBERS`, `SISMEMBER`, `SINTER` và `SUNION`.

Cách làm này đơn giản và hữu ích khi bộ lọc ít thuộc tính, dữ liệu có cấu trúc rõ và ứng dụng tự quản lý việc đồng bộ chỉ mục. Điểm khó không nằm ở lệnh `SADD` mà ở **giữ Set chỉ mục nhất quán với dữ liệu gốc**, kiểm soát cardinality, tránh kết quả stale, và biết giới hạn của thao tác nhiều key trong Redis Cluster.

## 1. Chỉ mục phụ là gì?

Giả sử dữ liệu sản phẩm được lưu theo ID:

```text
shop:prod:catalog:product:p101
    -> {id: p101, category: keyboard, brand: acme, name: "Bàn phím A"}

shop:prod:catalog:product:p102
    -> {id: p102, category: mouse, brand: acme, name: "Chuột B"}

shop:prod:catalog:product:p103
    -> {id: p103, category: keyboard, brand: nova, name: "Bàn phím C"}
```

Các key `product:p101`, `product:p102` và `product:p103` cho phép đọc theo ID, nhưng chúng không cung cấp một danh sách có sẵn các ID thuộc `category=keyboard`.

Ta tạo thêm Redis Set:

```text
shop:prod:catalog:idx:category:keyboard
    -> {p101, p103}

shop:prod:catalog:idx:category:mouse
    -> {p102}

shop:prod:catalog:idx:brand:acme
    -> {p101, p102}

shop:prod:catalog:idx:brand:nova
    -> {p103}
```

Khi cần tìm sản phẩm thuộc danh mục `keyboard`, ứng dụng lấy các ID từ Set `idx:category:keyboard`, sau đó đọc bản ghi theo từng ID. Khi cần thêm điều kiện `brand=acme`, lấy **giao** của hai Set.

Sơ đồ dữ liệu:

```text
                  PRIMARY RECORDS
            +---------------------------+
            | product:p101  keyboard    |
            | product:p102  mouse       |
            | product:p103  keyboard    |
            +---------------------------+
                       ^
                       | lookup by ID
                       |
                 SECONDARY INDEX
      +----------------+------------------+
      |                                   |
idx:category:keyboard               idx:brand:acme
      |                                   |
   {p101, p103}                       {p101, p102}
      |                                   |
      +------------ SINTER ---------------+
                       |
                     {p101}
                       |
              GET/HGETALL product:p101
```

**Dữ liệu gốc (primary record)** chứa nội dung sản phẩm. **Chỉ mục phụ** chỉ ánh xạ một điều kiện tìm kiếm sang các ID. Chỉ mục thường có thể xây dựng lại từ dữ liệu gốc; nó không nên trở thành một nguồn sự thật độc lập nếu ứng dụng chưa thiết kế rõ điều đó.

## 2. Vì sao dùng Redis Set?

Redis Set là tập hợp các phần tử **duy nhất** và **không có thứ tự sắp xếp được bảo đảm**.

Ví dụ:

```redis
SADD shop:prod:catalog:idx:category:keyboard p101 p103
SADD shop:prod:catalog:idx:category:keyboard p101
SMEMBERS shop:prod:catalog:idx:category:keyboard
```

Phần tử `p101` không bị nhân đôi khi thêm lần thứ hai. Redis không hứa trả `SMEMBERS` theo thứ tự `p101` rồi `p103`; tập được thiết kế để kiểm tra thành viên và tính toán giao/hợp/hiệu, không phải để sắp xếp theo thời gian hay xếp hạng.

Những thuộc tính khiến Set phù hợp làm chỉ mục:

- **Duy nhất:** một ID chỉ xuất hiện một lần trong mỗi Set.
- **Tra cứu thành viên nhanh:** `SISMEMBER` kiểm tra một ID có thuộc chỉ mục hay không.
- **Kết hợp điều kiện:** `SINTER` cho AND, `SUNION` cho OR, `SDIFF` cho hiệu tập.
- **Cập nhật đơn giản:** `SADD` thêm ID, `SREM` xóa ID.
- **Đếm số phần tử:** `SCARD` trả cardinality của Set, với lưu ý phải xử lý index stale.

Redis Set không tự hiểu thuộc tính của sản phẩm. Khi `category` đổi, **ứng dụng phải chủ động** xóa ID khỏi Set chỉ mục cũ và thêm ID vào Set chỉ mục mới.

## 3. Quy ước đặt tên key và phần tử chỉ mục

Một quy ước hữu ích:

```text
<application>:<environment>:<domain>:idx:<attribute>:<normalized-value>
```

Ví dụ:

```text
shop:prod:catalog:idx:category:keyboard
shop:prod:catalog:idx:brand:acme
shop:prod:identity:idx:role:admin
shop:prod:orders:idx:status:pending
```

Key bản ghi gốc:

```text
<application>:<environment>:<domain>:<entity>:<id>

shop:prod:catalog:product:p101
shop:prod:orders:order:o501
```

Cách đặt tên này tách được hai khái niệm:

| Loại key | Ví dụ | Redis type / ý nghĩa |
|---|---|---|
| Dữ liệu gốc | `shop:prod:catalog:product:p101` | Hash hoặc string chứa dữ liệu sản phẩm |
| Chỉ mục danh mục | `shop:prod:catalog:idx:category:keyboard` | Set chứa ID sản phẩm có category=keyboard |
| Chỉ mục thương hiệu | `shop:prod:catalog:idx:brand:acme` | Set chứa ID sản phẩm có brand=acme |
| Chỉ mục vai trò | `shop:prod:identity:idx:role:admin` | Set chứa ID user có role admin |

Giá trị trong Set nên là **ID ổn định**, không phải toàn bộ JSON hoặc object Java. Nếu lưu bản sao JSON ở nhiều Set, mỗi lần đổi thông tin sản phẩm sẽ phải cập nhật nhiều bản sao và chi phí bộ nhớ tăng nhanh.

Chuẩn hóa `category`, `brand`, `status` hoặc `tenantId` trước khi tạo key. Nếu `Keyboard`, `keyboard` và `KEYBOARD` cùng chỉ một danh mục, hãy đưa về một **slug canonical** như `keyboard`. Ngược lại, không tự đổi case của những ID mà hệ thống quy định phân biệt chữ hoa/chữ thường.

Không đưa email, token, mật khẩu hoặc dữ liệu nhạy cảm dạng rõ vào tên key. Tên key có thể xuất hiện trong log, bản sao lưu và công cụ quản trị.

## 4. Các lệnh Redis nền tảng để tạo chỉ mục

Giả sử dữ liệu được tạo trong Redis môi trường thực hành:

```redis
HSET shop:demo:catalog:product:p101 id p101 name "Bàn phím A" category keyboard brand acme
HSET shop:demo:catalog:product:p102 id p102 name "Chuột B" category mouse brand acme
HSET shop:demo:catalog:product:p103 id p103 name "Bàn phím C" category keyboard brand nova
```

Thêm ID vào các Set chỉ mục:

```redis
SADD shop:demo:catalog:idx:category:keyboard p101 p103
SADD shop:demo:catalog:idx:category:mouse p102
SADD shop:demo:catalog:idx:brand:acme p101 p102
SADD shop:demo:catalog:idx:brand:nova p103
```

Những lệnh thường dùng:

| Redis command | Ý nghĩa | Giá trị trả về / đặc điểm |
|---|---|---|
| `SADD key member...` | Thêm một hoặc nhiều ID | Số thành viên **mới** thực sự được thêm |
| `SREM key member...` | Xóa một hoặc nhiều ID | Số thành viên thực sự bị xóa |
| `SISMEMBER key member` | Kiểm tra ID thuộc Set | 1 nếu có, 0 nếu không |
| `SMEMBERS key` | Lấy toàn bộ ID | Không bảo đảm thứ tự |
| `SCARD key` | Đếm số ID | Số phần tử của Set |
| `SINTER key1 key2 ...` | Giao các Set | ID thỏa **tất cả** điều kiện |
| `SUNION key1 key2 ...` | Hợp các Set | ID thỏa **ít nhất một** điều kiện |
| `SDIFF key1 key2 ...` | Hiệu tập | ID thuộc Set thứ nhất nhưng không thuộc các Set sau |
| `SSCAN key cursor ...` | Duyệt tăng dần các ID | Không phải snapshot ổn định khi Set đang thay đổi |

Một ví dụ kiểm tra thành viên:

```redis
SISMEMBER shop:demo:catalog:idx:category:keyboard p101
# (integer) 1

SISMEMBER shop:demo:catalog:idx:category:keyboard p102
# (integer) 0
```

Ví dụ đếm:

```redis
SCARD shop:demo:catalog:idx:category:keyboard
# (integer) 2
```

Các kết quả được minh họa trên dữ liệu cố định nói trên. Trong ứng dụng nhiều writer, Set có thể thay đổi giữa các lệnh quan sát.

## 5. Tìm kiếm theo một điều kiện: `SMEMBERS` và `SISMEMBER`

Yêu cầu: **“Tìm tất cả sản phẩm thuộc danh mục keyboard”**.

Bước 1, lấy ID:

```redis
SMEMBERS shop:demo:catalog:idx:category:keyboard
```

Kết quả là một tập chứa `p101` và `p103`, với thứ tự không xác định.

Bước 2, đọc nội dung từng bản ghi:

```redis
HGETALL shop:demo:catalog:product:p101
HGETALL shop:demo:catalog:product:p103
```

Không phải mọi Redis Set member đều chắc chắn có bản ghi gốc còn tồn tại. Trong khoảng giữa bước 1 và bước 2, sản phẩm có thể bị xóa hoặc TTL có thể hết hạn. Một chỉ mục có thể chứa ID cũ nếu việc cập nhật không đồng bộ. Bên đọc nên xử lý ID không tìm thấy, và khi tính đúng đắn quan trọng cần kiểm tra lại thuộc tính từ dữ liệu gốc.

Nếu đã biết ID và chỉ cần trả lời **“p101 còn thuộc danh mục keyboard không?”**, sử dụng `SISMEMBER` thay vì tải toàn bộ Set:

```redis
SISMEMBER shop:demo:catalog:idx:category:keyboard p101
```

`SISMEMBER` trả về membership trong **chỉ mục hiện tại**. Nếu index stale, nó không thay thế phép kiểm tra trạng thái authoritative của sản phẩm.

## 6. Kết hợp nhiều điều kiện bằng giao Set: `SINTER`

Yêu cầu: **“Tìm các sản phẩm category=keyboard và brand=acme”**.

Ta đã có:

```text
Category keyboard = {p101, p103}
Brand acme        = {p101, p102}
```

Giao của hai Set:

```redis
SINTER shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:acme
```

Kết quả:

```text
{p101}
```

Biểu diễn logic:

```text
category = keyboard  AND  brand = acme

Set(category:keyboard) ∩ Set(brand:acme)
                        |
                        v
                      {p101}
```

Có thể thêm điều kiện thứ ba nếu cũng có chỉ mục tương ứng, ví dụ `status=active`:

```redis
SINTER shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:acme shop:demo:catalog:idx:status:active
```

**Lưu ý:** Đây là thao tác trên nhiều Redis key. Khi dùng Redis Cluster, các Set key phải đáp ứng ràng buộc hash slot của `SINTER`; sẽ được phân tích riêng ở phần Cluster.

## 7. Điều kiện OR và loại trừ với `SUNION`, `SDIFF`

Yêu cầu: **“Sản phẩm thuộc category keyboard hoặc mouse”**:

```redis
SUNION shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:category:mouse
```

Kết quả:

```text
{p101, p102, p103}
```

Phép hợp loại bỏ ID trùng nhau ngay cả khi một ID nằm trong cả hai Set.

Yêu cầu: **“Sản phẩm keyboard nhưng không thuộc brand=nova”**:

```redis
SDIFF shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:nova
```

Kết quả:

```text
{p101}
```

Với phép hiệu, **thứ tự các Set quan trọng**:

```text
A - B != B - A
```

`SDIFF A B C` chọn những member thuộc `A` nhưng không thuộc `B` và `C`. Nó không có ý nghĩa “NOT brand=nova” trên toàn bộ hệ thống nếu không xác định được **tập nguồn** mà phép phủ định đang áp dụng.

Cả giao, hợp và hiệu đều trả **ID**, không trả nội dung entity hoặc thứ tự phân trang của bản ghi.

## 8. Spring Data Redis cung cấp `SetOperations<K,V>`

Với `StringRedisTemplate`, có thể lấy:

```java
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

SetOperations<String, String> sets = redis.opsForSet();
```

Các API cơ bản:

```java
Long added = sets.add(indexKey, "p101", "p103");
Long removed = sets.remove(indexKey, "p103");

Boolean member = sets.isMember(indexKey, "p101");
Long count = sets.size(indexKey);

Set<String> ids = sets.members(indexKey);
```

Đối chiếu với Redis:

| Spring Data Redis | Redis command |
|---|---|
| `sets.add(key, members...)` | `SADD` |
| `sets.remove(key, members...)` | `SREM` |
| `sets.isMember(key, value)` | `SISMEMBER` |
| `sets.members(key)` | `SMEMBERS` |
| `sets.size(key)` | `SCARD` |
| `sets.intersect(keyA, keyB)` | `SINTER` |
| `sets.union(keyA, keyB)` | `SUNION` |
| `sets.difference(keyA, keyB)` | `SDIFF` |
| `sets.scan(key, options)` | `SSCAN` |

`StringRedisTemplate` lưu ID thành chuỗi UTF-8, thuận tiện khi nhiều ứng dụng cùng sử dụng Redis. Với `RedisTemplate<String, UUID>` hoặc object khác, serializer tương ứng sẽ quyết định byte thành viên Set; các bên đọc phải sử dụng cùng một hợp đồng định dạng.

Một số phương thức có thể trả `null` trong ngữ cảnh Redis pipeline/transaction vì kết quả được thu thập sau. Ví dụ Java bên dưới giả định thao tác đồng bộ trực tiếp với Redis, ngoài pipeline và transaction.

## 9. Cấu hình Spring Boot cho ví dụ

Dependency Gradle Groovy DSL với Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Một cấu hình Redis standalone trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

Spring Boot có thể tự cung cấp `StringRedisTemplate` và `RedisConnectionFactory` nếu các điều kiện auto-configuration phù hợp. Trong ví dụ, dùng `StringRedisTemplate` cho cả hash của sản phẩm lẫn Set chỉ mục; cách đặt key và serialization được ứng dụng chủ động quản lý.

Nếu chạy ứng dụng trong Docker Compose hoặc Kubernetes, thay `localhost` bằng endpoint Redis có thể truy cập từ ứng dụng. Với Redis Cluster, dùng cấu hình `spring.data.redis.cluster.nodes` và hiểu giới hạn thao tác nhiều key; một cấu hình standalone chỉ nhằm minh họa cách truy cập.

## 10. Xây dựng mô hình sản phẩm và lớp tạo key

Dữ liệu nghiệp vụ đơn giản:

```java
package com.example.catalog;

public record Product(
        String id,
        String name,
        String category,
        String brand
) {}
```

Định nghĩa key theo một nơi duy nhất giúp tránh lỗi gõ:

```java
package com.example.catalog;

import java.util.Objects;
import java.util.regex.Pattern;

public final class CatalogRedisKeys {
    private static final String PREFIX = "shop:demo:catalog";
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[a-z0-9_-]+");

    private CatalogRedisKeys() {}

    public static String product(String id) {
        return PREFIX + ":product:" + segment(id);
    }

    public static String categoryIndex(String category) {
        return PREFIX + ":idx:category:" + segment(category);
    }

    public static String brandIndex(String brand) {
        return PREFIX + ":idx:brand:" + segment(brand);
    }

    private static String segment(String value) {
        Objects.requireNonNull(value, "Redis key segment");
        if (!SAFE_SEGMENT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid Redis key segment");
        }
        return value;
    }
}
```

Các ví dụ sử dụng ID `p101`, category `keyboard` và brand `acme`, đều đã được chuẩn hóa. Nếu domain có Unicode, ký tự `:` hoặc ID phân biệt chữ hoa, hệ thống cần quy tắc canonical/mã hóa phù hợp thay vì sử dụng regex này một cách máy móc.

Ở production, prefix môi trường `shop:prod`/`shop:staging` nên đến từ cấu hình triển khai. Không nên hard-code `prod` vào mọi source file rồi chạy cùng binary trên nhiều môi trường chia sẻ Redis.

## 11. Java service: ghi dữ liệu gốc và cập nhật Set chỉ mục

Một implementation minh họa, dùng Redis hash làm dữ liệu gốc và Redis Set làm chỉ mục phụ:

```java
package com.example.catalog;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexStore {

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashes;
    private final SetOperations<String, String> sets;

    public ProductIndexStore(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashes = redis.opsForHash();
        this.sets = redis.opsForSet();
    }

    public void save(Product p) {
        Objects.requireNonNull(p, "product");
        String productKey = CatalogRedisKeys.product(p.id());
        String categoryKey = CatalogRedisKeys.categoryIndex(p.category());
        String brandKey = CatalogRedisKeys.brandIndex(p.brand());

        // Chỉ dùng để minh họa cập nhật index trên Redis standalone.
        String oldCategory = hashes.get(productKey, "category");
        String oldBrand = hashes.get(productKey, "brand");

        hashes.putAll(productKey, Map.of(
                "id", p.id(),
                "name", p.name(),
                "category", p.category(),
                "brand", p.brand()
        ));

        if (oldCategory != null && !oldCategory.equals(p.category())) {
            sets.remove(CatalogRedisKeys.categoryIndex(oldCategory), p.id());
        }
        if (oldBrand != null && !oldBrand.equals(p.brand())) {
            sets.remove(CatalogRedisKeys.brandIndex(oldBrand), p.id());
        }

        sets.add(categoryKey, p.id());
        sets.add(brandKey, p.id());
    }

    public Product find(String id) {
        Map<String, String> row =
                hashes.entries(CatalogRedisKeys.product(id));

        if (row.isEmpty()) {
            return null;
        }

        String name = row.get("name");
        String category = row.get("category");
        String brand = row.get("brand");

        if (name == null || category == null || brand == null) {
            return null;
        }

        return new Product(id, name, category, brand);
    }

    public List<Product> findByCategoryAndBrand(
            String category,
            String brand) {

        Set<String> ids = sets.intersect(
                CatalogRedisKeys.categoryIndex(category),
                CatalogRedisKeys.brandIndex(brand)
        );

        if (ids == null || ids.isEmpty()) {
            return List.of();
        }

        return ids.stream()
                .map(this::find)
                .filter(Objects::nonNull)
                // Loại ID stale nếu dữ liệu gốc đã đổi thuộc tính.
                .filter(p -> category.equals(p.category()))
                .filter(p -> brand.equals(p.brand()))
                .toList();
    }

    public void delete(String id) {
        Product current = find(id);
        if (current == null) {
            return;
        }

        sets.remove(
                CatalogRedisKeys.categoryIndex(current.category()), id);
        sets.remove(
                CatalogRedisKeys.brandIndex(current.brand()), id);
        redis.delete(CatalogRedisKeys.product(id));
    }
}
```

Cách dùng:

```java
store.save(new Product("p101", "Bàn phím A", "keyboard", "acme"));
store.save(new Product("p102", "Chuột B", "mouse", "acme"));
store.save(new Product("p103", "Bàn phím C", "keyboard", "nova"));

List<Product> selected =
        store.findByCategoryAndBrand("keyboard", "acme");
```

Kết quả hợp lý trên dữ liệu ổn định là danh sách chứa sản phẩm `p101`. **Thứ tự trả về không được bảo đảm**, vì `SINTER` trả một Set, nên nếu API đòi hỏi sắp xếp, cần áp dụng bước sắp xếp theo tiêu chí nghiệp vụ.

> **Giới hạn quan trọng của ví dụ:** `save` và `delete` gồm nhiều Redis command riêng, và `save` đọc thuộc tính cũ trước khi ghi. Vì thế code này **không bảo đảm cập nhật dữ liệu gốc và chỉ mục một cách atomic**, cũng không an toàn trước mọi cuộc đua của nhiều writer. Nó giúp thấy vai trò từng lệnh và phù hợp để học cơ chế; phần sau trình bày những chiến lược cần có khi triển khai thực tế.

## 12. Đồng bộ chỉ mục khi cập nhật thuộc tính

Giả sử sản phẩm `p101` ban đầu thuộc:

```text
category = keyboard
brand    = acme
```

Sau đó danh mục đổi thành `accessories`. Nếu chỉ cập nhật hash:

```redis
HSET shop:demo:catalog:product:p101 category accessories
```

Nhưng không cập nhật chỉ mục:

```text
idx:category:keyboard   -> vẫn chứa p101
idx:category:accessories -> chưa có p101
```

Kết quả: tìm `keyboard` có thể trả sản phẩm sai (false positive), còn tìm `accessories` bỏ sót sản phẩm (false negative).

Cập nhật Set thủ công:

```redis
SREM shop:demo:catalog:idx:category:keyboard p101
SADD shop:demo:catalog:idx:category:accessories p101
```

Sau khi cả dữ liệu gốc và các Set đều được cập nhật hoàn tất, index mới phản ánh category mới.

Sơ đồ thay đổi:

```text
TRƯỚC: category keyboard
  product:p101          -> keyboard
  idx:category:keyboard -> {p101, p103}

ĐỔI THUỘC TÍNH:
  1. Cập nhật dữ liệu gốc sang accessories
  2. SREM p101 khỏi index keyboard
  3. SADD p101 vào index accessories

SAU:
  product:p101            -> accessories
  idx:category:keyboard   -> {p103}
  idx:category:accessories -> {p101}
```

Tuy nhiên, ba bước này chưa tạo ra giao dịch nguyên tử. Nếu ứng dụng chết sau bước 1, Set có thể bị stale. Nếu có hai writer cùng sửa category, việc mỗi writer đọc trạng thái cũ rồi thay index có thể làm mất/còn thừa thành viên. Không thể giải quyết triệt để chỉ bằng cách đổi thứ tự `SREM` và `SADD`.

## 13. Vì sao dữ liệu gốc và chỉ mục có thể lệch nhau?

Các kiểu lệch phổ biến:

| Tình huống | Hậu quả |
|---|---|
| Ghi dữ liệu gốc thành công, thêm vào Set thất bại | Bản ghi tồn tại nhưng truy vấn theo thuộc tính bỏ sót |
| `SADD` thành công, ghi dữ liệu gốc thất bại | Set có ID không tìm thấy bản ghi |
| Đổi category nhưng quên `SREM` chỉ mục cũ | Kết quả tìm kiếm chứa ID không còn thuộc category |
| Xóa bản ghi nhưng quên xóa khỏi Set | Chỉ mục trỏ tới bản ghi không tồn tại |
| Bản ghi có TTL và tự hết hạn | Set vẫn có thể giữ ID hết hạn |
| Hai writer cập nhật cùng ID đồng thời | Trạng thái index có thể phụ thuộc thứ tự xen kẽ các lệnh |
| Một key index hết TTL trước dữ liệu gốc | Mất toàn bộ khả năng tra cứu một nhóm dù bản ghi vẫn còn |

Vì thế, khi chỉ mục cần độ chính xác cao, việc giữ nhất quán **phải là một phần của thiết kế ghi**, không phải công việc phụ được thêm sau này.

### Có thể kiểm tra lại dữ liệu gốc khi đọc không?

Có. Trong `findByCategoryAndBrand`, service đọc ID từ giao Set, tải product rồi kiểm tra lại `category` và `brand`. Cách này loại nhiều false positive do chỉ mục stale. Nhưng nó **không khắc phục false negative**: một ID không nằm trong Set mới sẽ không được truy vấn để kiểm tra, dù bản ghi gốc thực sự phù hợp.

Đó là sự khác nhau giữa **lọc kết quả sai** và **đảm bảo chỉ mục đầy đủ**. Nếu kết quả dùng cho nghiệp vụ không được phép bỏ sót, cần đảm bảo chất lượng index từ đường ghi và có cơ chế đối soát/khôi phục.

## 14. Chiến lược cập nhật nhất quán

Có vài cách, phụ thuộc dữ liệu gốc và hạ tầng:

### 14.1. Thao tác atomic trên một Redis server

Khi dữ liệu gốc và các index key liên quan thuộc cùng một Redis server, có thể dùng **Lua script** hoặc một mô hình transaction Redis phù hợp để cập nhật cùng nhau.

Một script có thể nhận key của bản ghi, key Set cũ, key Set mới và các giá trị mới, sau đó:

1. Kiểm tra trạng thái cũ/các điều kiện kỳ vọng.
2. Ghi trường dữ liệu gốc.
3. Xóa ID khỏi Set cũ nếu cần.
4. Thêm ID vào Set mới.
5. Trả trạng thái thành công hoặc xung đột.

Các lệnh trong một Lua script Redis được xử lý atomic ở cấp thực thi lệnh trên server. Tuy nhiên, **Lua atomic không đồng nghĩa tự rollback mọi thay đổi nếu script phát sinh lỗi sau một số lệnh ghi**. Cần validate input và các điều kiện có thể gây lỗi trước khi bắt đầu ghi; quản lý thời gian chạy script để tránh chặn Redis.

Với Redis Cluster, **tất cả key mà script thao tác phải phù hợp ràng buộc hash slot** và phải được khai báo/đi qua API đúng cách. Nếu dữ liệu gốc và các index thuộc các slot khác nhau, một script không thể tạo transaction atomic xuyên các primary nodes.

### 14.2. Redis transaction với `WATCH`/`MULTI`/`EXEC`

Trong Redis standalone, có thể dùng `WATCH` để giám sát key và `MULTI`/`EXEC` để thực hiện nhóm lệnh khi không có thay đổi cạnh tranh với các key được watch.

Nhưng Spring Data Redis sử dụng abstraction kết nối, nên muốn dùng transaction đúng phải đảm bảo các lệnh phụ thuộc nằm trong **cùng connection/transaction context**. Gọi nhiều method trên template rồi gắn `@Transactional` của JPA không tự biến chúng thành một Redis transaction.

`MULTI`/`EXEC` cũng có semantics khác giao dịch SQL: nếu một lệnh queued gặp lỗi ở thời điểm thực thi, Redis không mặc định rollback mọi lệnh thành công khác. Cần thiết kế và xử lý lỗi theo đúng semantics Redis.

### 14.3. Nguồn dữ liệu chính nằm ở database khác

Nếu sản phẩm gốc nằm trong PostgreSQL/MySQL và Redis Set chỉ là chỉ mục tăng tốc, đừng giả định một Redis transaction có thể commit atomic cùng SQL transaction.

Một mô hình thường dùng:

```text
API cập nhật sản phẩm
    |
    v
SQL transaction cập nhật product
    |
    +--> ghi outbox event trong cùng SQL transaction
              |
              v
        Worker đọc outbox
              |
              v
    Redis: cập nhật/xây lại các Set index
```

Worker cần có retry, idempotency, thứ tự version sự kiện và cơ chế xử lý lỗi. Trong khoảng thời gian chưa đồng bộ, Redis index có thể mang tính **eventual consistency**. Nếu nghiệp vụ đòi hỏi đọc chính xác ngay sau khi ghi, cần quyết định đường đọc authoritative hoặc chính sách chờ đồng bộ phù hợp.

### 14.4. Index có thể tái tạo

Với Set là dữ liệu dẫn xuất, một cách quan trọng để giảm rủi ro là có **rebuild/reconciliation job**. Job đọc nguồn dữ liệu gốc, tạo lại Set index theo namespace phiên bản mới, đối soát trước khi chuyển sang sử dụng phiên bản mới. Không nên chỉ tin rằng mọi sự kiện cập nhật sẽ luôn được giao đúng một lần.

## 15. Xóa bản ghi: phải dọn những Set nào?

Xóa product `p101` yêu cầu xử lý ít nhất:

```text
product:p101
idx:category:keyboard -> SREM p101
idx:brand:acme        -> SREM p101
```

Nếu sản phẩm có nhiều tags, ví dụ `gaming` và `wireless`, nó còn là thành viên của:

```text
idx:tag:gaming
idx:tag:wireless
```

Vì vậy, khi xóa một bản ghi, ứng dụng cần biết **toàn bộ giá trị thuộc tính đã được index** để xóa các membership tương ứng. Có thể lấy từ bản ghi hiện tại trước khi xóa, hoặc duy trì metadata/reverse index theo ID khi số lượng index động lớn.

Ví dụ reverse index theo từng sản phẩm:

```text
shop:prod:catalog:idx-refs:p101
    -> {
         category:keyboard,
         brand:acme,
         tag:gaming,
         tag:wireless
       }
```

Reverse index giúp tìm các chỉ mục cần dọn, nhưng chính nó lại là dữ liệu phải duy trì nhất quán. Không nhất thiết tạo reverse index cho một mô hình đơn giản chỉ có 2–3 thuộc tính cố định.

Khi `SREM` xóa thành viên cuối cùng của một Redis Set, key Set đó không còn tồn tại. Nếu ứng dụng định kỳ đọc `SMEMBERS` trên một index rỗng, kết quả bình thường là tập rỗng; không cần tạo Redis key Set rỗng để làm “container” sẵn.

## 16. Chỉ mục nhiều giá trị: tags, roles, permissions

Không phải thuộc tính nào cũng có đúng một giá trị. Một sản phẩm có thể có nhiều tag:

```text
p101: [gaming, wireless]
p102: [wireless]
p103: [gaming]
```

Lập Set theo từng tag:

```redis
SADD shop:demo:catalog:idx:tag:gaming p101 p103
SADD shop:demo:catalog:idx:tag:wireless p101 p102
```

Truy vấn sản phẩm có **cả hai** tag:

```redis
SINTER shop:demo:catalog:idx:tag:gaming shop:demo:catalog:idx:tag:wireless
# {p101}
```

Truy vấn sản phẩm có **ít nhất một** trong hai tag:

```redis
SUNION shop:demo:catalog:idx:tag:gaming shop:demo:catalog:idx:tag:wireless
# {p101, p102, p103}
```

Nếu `p101` bỏ tag `gaming`, cần:

```redis
SREM shop:demo:catalog:idx:tag:gaming p101
```

Nếu chỉ `SADD` các tag mới mà không tính toán chênh lệch tag cũ–mới, index sẽ ngày càng chứa những membership không còn hợp lệ.

Tương tự có thể áp dụng cho user roles, bài viết thuộc topics, tài liệu gắn nhãn hoặc đơn hàng có nhiều trạng thái phụ. Với role/permission, Set index chỉ là dữ liệu tra cứu; **không nên thay kiểm tra ủy quyền trên nguồn authoritative bằng việc tin tuyệt đối vào một index có thể stale**.

## 17. Hạn chế của việc dùng `SMEMBERS` để tải toàn bộ Set

`SMEMBERS key` trả về **toàn bộ** thành viên Set. Với một Set vài chục ID, thao tác này đơn giản. Với Set vài triệu ID, việc trả toàn bộ có thể gây:

- Redis phải đọc và gửi lượng dữ liệu lớn.
- Băng thông mạng và bộ nhớ JVM tăng đột biến.
- Tăng latency của request, đặc biệt khi nhiều request truy vấn cùng một Set.
- Không có thứ tự ổn định để phân trang theo offset.

Phức tạp của `SMEMBERS` tỷ lệ với số member trả về (thường biểu diễn là **O(N)**). Trong Spring Data Redis, `sets.members(indexKey)` tạo một Java `Set<String>`, nên ứng dụng phải có đủ bộ nhớ để giữ kết quả.

### `SSCAN` để duyệt tăng dần

Redis cung cấp `SSCAN`. Trong Spring Data Redis:

```java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import java.util.ArrayList;
import java.util.List;

public List<String> firstUpTo(
        StringRedisTemplate redis,
        String indexKey,
        int limit) {

    if (limit <= 0) {
        return List.of();
    }

    List<String> result = new ArrayList<>(limit);

    try (Cursor<String> cursor = redis.opsForSet().scan(
            indexKey,
            ScanOptions.scanOptions().count(100).build())) {

        while (cursor.hasNext() && result.size() < limit) {
            result.add(cursor.next());
        }
    }

    return result;
}
```

`count(100)` chỉ là **hint** về số phần tử xử lý mỗi lần scan, không phải cam kết Redis luôn trả đúng 100 phần tử. `SSCAN` có thể trả trùng member trong quá trình quét, và nếu Set thay đổi đồng thời thì một số kết quả có thể bị bỏ qua hoặc xuất hiện thêm. Vì vậy, **`SSCAN` không cung cấp snapshot nhất quán hay cơ chế pagination ổn định theo trang số**.

Nếu cần danh sách ổn định được sắp xếp theo ngày tạo, giá hoặc điểm xếp hạng, cân nhắc thêm **Sorted Set**, một lớp truy vấn khác hoặc hệ thống tìm kiếm chuyên dụng thay vì cố dùng `SMEMBERS`/`SSCAN` làm phân trang có thứ tự.

## 18. Tối ưu truy vấn nhiều điều kiện

Giả sử:

```text
idx:category:keyboard -> 500.000 IDs
idx:brand:acme        -> 2.000 IDs
idx:status:active     -> 10.000.000 IDs
```

Nếu cần cả ba điều kiện, về mặt logic có thể dùng `SINTER` trên các Set. Nhưng việc xử lý Set kích thước lớn, đặc biệt trong Cluster, có thể tốn thời gian/mạng hoặc không thể thực hiện một lệnh native cross-slot.

Một hướng khác là:

1. Đo `SCARD` các Set liên quan.
2. Chọn Set có ít thành viên nhất làm **candidate set**.
3. Duyệt ID candidate, kiểm tra từng điều kiện còn lại bằng `SISMEMBER`.
4. Đọc dữ liệu gốc và xác minh kết quả trước khi trả về.

Ví dụ `brand=acme` chỉ chứa 2.000 ID, nên dùng nó làm tập candidate có thể giảm số ID phải tải và kiểm tra so với việc lấy toàn bộ 10 triệu ID active.

Đây là một chiến lược xử lý **ở tầng ứng dụng**, không phải một transaction snapshot. Giữa `SCARD`, `SSCAN` và `SISMEMBER`, dữ liệu có thể thay đổi. Khi dữ liệu cần kết quả nhất quán tuyệt đối, cần thiết kế cơ chế đồng bộ/phiên bản hoặc đọc từ nguồn authoritative.

### Độ phức tạp thường gặp

| Lệnh | Đặc tính chi phí khái quát |
|---|---|
| `SADD` / `SREM` một member | Trung bình O(1) cho mỗi member |
| `SISMEMBER` | Trung bình O(1) |
| `SCARD` | O(1) |
| `SMEMBERS` | O(N), N là số member được trả |
| `SINTER` | Phụ thuộc số lượng Set và số member phải duyệt/so khớp |
| `SUNION` / `SDIFF` | Phụ thuộc tổng số phần tử và số Set |
| `SSCAN` | Duyệt tăng dần; tổng chi phí phụ thuộc toàn bộ lần quét và số member |

Chi phí thực tế còn chịu ảnh hưởng kích thước ID, số index, tốc độ mạng, số client, CPU Redis và nhu cầu deserialize ở JVM. Đừng chỉ nhìn vào Big-O để dự đoán latency sản xuất; hãy đo với dữ liệu và cardinality gần thực tế.

## 19. Redis Cluster: `SINTER` giữa các Set có thể gây `CROSSSLOT`

Redis Cluster phân phối key lên **16.384 hash slots**. Một số lệnh Redis nhận nhiều key, như `SINTER`, `SUNION` và `SDIFF`, yêu cầu các key tham gia nằm trong **cùng hash slot** để thực thi như một lệnh native trong Cluster.

Các tên key sau có prefix chung:

```text
shop:prod:catalog:idx:category:keyboard
shop:prod:catalog:idx:brand:acme
```

Nhưng dấu `:` và prefix `shop:prod:catalog:` **không đảm bảo cùng slot**. Do đó:

```redis
SINTER shop:prod:catalog:idx:category:keyboard shop:prod:catalog:idx:brand:acme
```

có thể bị từ chối trong Redis Cluster với lỗi `CROSSSLOT`.

### 19.1. Hash tag: cùng slot khi cần lệnh đa key

Redis Cluster hỗ trợ hash tag qua dấu ngoặc nhọn. Nếu đặt:

```text
shop:prod:catalog:{catalog-index}:idx:category:keyboard
shop:prod:catalog:{catalog-index}:idx:brand:acme
```

thì cả hai key được tính slot dựa trên `catalog-index`, nhờ đó `SINTER` có thể áp dụng trong cùng slot.

Tuy nhiên, cách này có một **đánh đổi lớn**: mọi chỉ mục cùng hash tag sẽ dồn vào **một slot**, thuộc một primary tại một thời điểm. Nếu tập chỉ mục lớn và có tải cao, nó trở thành điểm nóng; thiết kế như vậy có thể làm mất lợi ích phân phối dữ liệu của Cluster.

Không nên áp dụng một hash tag chung toàn ứng dụng chỉ để mọi lệnh đa key hoạt động.

### 19.2. Khi các chỉ mục nằm ở nhiều slot

Có thể dùng chiến lược ở tầng ứng dụng:

```text
1. Lấy candidate IDs từ một Set chọn lọc.
2. Với mỗi ID, kiểm tra membership trên các Set khác bằng SISMEMBER.
3. Chỉ lấy product record của candidate vượt qua các điều kiện.
4. Kiểm tra lại thuộc tính thực tế và xử lý kết quả stale.
```

Mỗi lệnh `SISMEMBER` chỉ nhắm đến **một key**, nên driver hiểu Cluster có thể định tuyến nó tới slot phù hợp. Đổi lại, số thao tác tăng, cần chú ý RTT/pipelining và không có atomic snapshot xuyên node.

Nếu cần nhiều truy vấn động AND/OR trên tập dữ liệu lớn với ordering/pagination, một hệ thống search/index chuyên dụng có thể phù hợp hơn việc ép nhiều Redis Set vào một slot.

### 19.3. Thao tác cập nhật đa key cũng bị giới hạn

Một Lua script hoặc Redis transaction cập nhật đồng thời hash sản phẩm và nhiều Set index cần thỏa ràng buộc slot. Nếu primary record và các secondary index ở khác slot, **không thể có một transaction Redis atomic xuyên toàn Cluster** chỉ bằng `MULTI` hoặc Lua.

Khi dùng Cluster, cần quyết định rõ một trong những chiến lược: chấp nhận index eventual consistency và có reconciliation, giới hạn phạm vi atomic trong một slot, hoặc sử dụng hệ thống dữ liệu có khả năng truy vấn/transaction phù hợp hơn.

## 20. TTL: chỉ mục Set và dữ liệu gốc không hết hạn cùng nhau

TTL của Redis được đặt trên **toàn bộ key Set**, không phải trên từng member. Ví dụ:

```redis
EXPIRE shop:demo:catalog:idx:category:keyboard 600
```

Sau 600 giây, cả Set chỉ mục biến mất, không chỉ ID cũ nhất.

Nếu dữ liệu gốc có TTL 5 phút nhưng Set chỉ mục không có TTL:

```text
product:p101 hết hạn
idx:category:keyboard vẫn chứa p101
```

Khi đó chỉ mục chứa **dangling reference** đến product không còn tồn tại.

Ngược lại, nếu key Set index hết TTL trước khi dữ liệu gốc hết hạn:

```text
idx:category:keyboard hết hạn
product:p101 vẫn tồn tại
```

Khi đó truy vấn theo category có thể **bỏ sót toàn bộ nhóm**, dù dữ liệu gốc vẫn còn.

### Chính sách TTL nên dựa trên ý nghĩa dữ liệu

- Với chỉ mục dùng như **cấu trúc tra cứu cho dữ liệu bền vững**, thường không đặt TTL ngắn tùy tiện lên Set index; mỗi lần thêm/xóa record phải cập nhật membership.
- Với chỉ mục dẫn xuất của **cache có TTL**, phải có chiến lược đồng bộ expiry, sửa index stale và hồi phục chỉ mục bị thiếu.
- Với tập chỉ mục tạm thời dùng cho một báo cáo hoặc phiên truy vấn, TTL có thể hợp lý; cần đảm bảo phần code đọc hiểu đây là dữ liệu tạm.
- Nếu `SREM` xóa member cuối, Redis xóa Set key. Khi `SADD` tạo lại key sau đó, TTL cũ không tự được khôi phục.

Redis keyspace notifications có thể hỗ trợ nghe sự kiện expiry khi được cấu hình phù hợp, nhưng chúng **không phải nhật ký sự kiện bền vững để bảo đảm không bao giờ bỏ sót**. Worker có thể offline, sự kiện không được lưu để replay theo cách hàng đợi bền vững, hoặc cấu hình notification không bật. Không dùng riêng event expiry làm cơ chế duy nhất bảo đảm chính xác của chỉ mục quan trọng.

## 21. Materialize kết quả giao Set bằng `SINTERSTORE`

Đôi khi một truy vấn được chạy nhiều lần với cùng bộ lọc. Redis có lệnh lưu kết quả giao vào một Set khác:

```redis
SINTERSTORE shop:demo:catalog:tmp:keyboard-acme shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:acme
```

Key đích `tmp:keyboard-acme` sẽ chứa tập kết quả tại thời điểm lệnh thực thi. Redis còn có `SUNIONSTORE` và `SDIFFSTORE` với semantics tương tự cho hợp và hiệu.

Nhưng đây là **bản materialized tại một thời điểm**, không phải view tự động được cập nhật. Sau khi sản phẩm đổi brand, Set tạm **không tự đồng bộ** theo hai Set nguồn.

Nếu kết quả chỉ sử dụng trong thời gian ngắn, có thể đặt TTL:

```redis
EXPIRE shop:demo:catalog:tmp:keyboard-acme 60
```

Hai lệnh `SINTERSTORE` và `EXPIRE` riêng lẻ có khoảng thời gian giữa chúng; nếu TTL cần được bảo đảm atomically, phải thiết kế khác.

Trong Redis Cluster, key đích và mọi key nguồn của `SINTERSTORE` đều phải đáp ứng quy tắc cùng slot. Ngoài ra, materialize nhiều kết quả lớn làm tăng sử dụng bộ nhớ; cần đặt chính sách dọn dẹp và giới hạn số bản kết quả tạm.

## 22. Khi nào dùng `@Indexed` của Redis Repository?

Spring Data Redis Repository có cơ chế ánh xạ entity vào Redis, và có thể hỗ trợ **chỉ mục thứ cấp qua metadata/annotation như `@Indexed`** để phục vụ các truy vấn repository được hỗ trợ.

Đây là đường xử lý khác với việc tự dùng `StringRedisTemplate.opsForSet()`:

| Tự quản lý Set chỉ mục | Chỉ mục do Redis Repository quản lý |
|---|---|
| Ứng dụng tự chọn key index và member ID | Framework áp dụng quy ước mapping/index của repository |
| Ứng dụng tự viết `SADD`, `SREM`, kết hợp Set | Repository quản lý index khi lưu/xóa entity theo cơ chế của nó |
| Tự quyết định query bằng `SINTER`/`SISMEMBER` | Truy vấn qua method repository phù hợp với các thuộc tính được index |
| Phải tự xử lý mọi đường ghi có thể bỏ qua index | Vẫn cần dùng đúng đường repository và hiểu cập nhật/expiry |
| Phù hợp khi dùng `RedisTemplate` trực tiếp hoặc cần quy tắc key riêng | Phù hợp khi model ứng dụng đi theo Spring Data Redis Repository |

Ví dụ ý tưởng với entity repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;

    @Indexed
    private String category;

    private String name;

    // Constructor, getters/setters phù hợp...
}
```

Khi sử dụng Redis Repository, metadata trên `category` có thể được dùng để duy trì index và hỗ trợ truy vấn theo category trong các trường hợp được Spring Data Redis hỗ trợ. Không nên mặc định mọi biểu thức truy vấn phức tạp, full-text, sort hoặc pagination đều được Redis Repository chuyển thành chỉ mục tối ưu.

**Quan trọng:** Chỉ mục repository có cấu trúc key và metadata do framework quản lý. Đừng tự ý `SREM`/`SADD` vào key nội bộ của repository chỉ vì nhìn thấy đó là Redis Set. Và đừng mong rằng thay đổi dữ liệu qua `RedisTemplate` bên ngoài repository sẽ tự cập nhật những chỉ mục repository tương ứng.

Bài học đang tập trung vào **tự xây dựng chỉ mục phụ bằng Redis Set** để hiểu cơ chế nền tảng. Khi dự án đã dùng repository, hãy quyết định rõ ai sở hữu index để tránh có hai cơ chế duy trì cùng một sự thật.

## 23. Đối soát và xây lại chỉ mục

Một hệ thống sống lâu sẽ gặp tình huống process crash, lỗi network, triển khai nhiều version, thay TTL hoặc thay schema. Vì vậy, nên có cách xác minh index không bị lệch vĩnh viễn.

Các loại sai lệch cần tìm:

1. **Dangling ID:** Set chứa `p101` nhưng bản ghi gốc không tồn tại.
2. **Wrong membership:** Set `category:keyboard` chứa ID mà bản ghi gốc đã có `category=mouse`.
3. **Missing membership:** bản ghi gốc có `category=keyboard` nhưng Set không chứa ID.
4. **Orphan index:** key chỉ mục của category đã bị bỏ dùng nhưng vẫn có rất nhiều ID.
5. **Version drift:** phiên bản app cũ vẫn ghi index theo namespace hoặc serializer cũ.

Ví dụ quy trình rebuild từ nguồn dữ liệu authoritative:

```text
Nguồn dữ liệu chính (SQL hoặc kho sản phẩm canonical)
        |
        v
Duyệt tất cả sản phẩm theo từng batch
        |
        v
Tạo các Set mới:
    idx:v2:category:keyboard
    idx:v2:brand:acme
    ...
        |
        v
Đối soát số lượng, membership mẫu và nguồn cập nhật
        |
        v
Chuyển reader sang namespace index v2 theo cơ chế triển khai
        |
        v
Ngừng writer index v1 và dọn v1 theo quy trình
```

Không nên rebuild bằng cách xóa index đang phục vụ traffic rồi thêm từ đầu nếu việc mất kết quả trong khoảng rebuild là không chấp nhận được. Có thể xây index vào **namespace mới**, sau đó chuyển cấu hình/phiên bản reader có kiểm soát.

Nếu có ghi mới trong khi rebuild, cần cơ chế bắt kịp thay đổi: event log/outbox, dual-write có kiểm soát, hoặc tạm ngừng ghi trong khoảng chuyển đổi. Nếu không, bản rebuild vừa xong có thể đã thiếu những cập nhật xảy ra trong lúc quét.

Việc đếm `SCARD` các Set là một tín hiệu vận hành, nhưng **không tự chứng minh index đúng**. Hai tập có cùng số lượng member vẫn có thể chứa những ID hoàn toàn khác nhau. Đối soát membership và dữ liệu gốc mới tìm ra lỗi nội dung.

## 24. Bảo mật và ranh giới đa tenant

Nếu hệ thống có nhiều tenant, có thể thêm tenant vào namespace:

```text
shop:prod:t27:catalog:idx:category:keyboard
shop:prod:t91:catalog:idx:category:keyboard
```

Các Set đó chứa ID chỉ trong phạm vi tenant tương ứng. Tuy nhiên, tenant ID phải được lấy từ ngữ cảnh đã xác thực/ủy quyền của request, không để client tùy tiện chọn tenant khác chỉ bằng một tham số.

Một Set index có thể tiết lộ **sự tồn tại của các đối tượng** nếu người không có quyền được phép đọc member. ACL của Redis có thể hạn chế phạm vi key mà một credential được phép truy cập; vẫn cần kiểm tra quyền nghiệp vụ trước khi trả dữ liệu cho người dùng.

Prefix `t27` không tự tạo ranh giới bảo mật. Các ứng dụng cùng dùng credential có quyền rộng vẫn có thể đọc Set của tenant khác nếu application code không kiểm soát.

Nếu người dùng có quyền truy vấn `category=keyboard` nhưng chỉ được xem một phần sản phẩm, việc lấy toàn bộ ID từ index rồi trả ra bên ngoài là sai. Cần kết hợp điều kiện truy cập ở tầng phù hợp, hoặc thiết kế index đáp ứng policy cho những truy vấn an toàn và kiểm tra lại quyền tại bản ghi.

## 25. Redis Set index so với các giải pháp khác

| Nhu cầu | Redis Set index | Cách khác có thể phù hợp hơn |
|---|---|---|
| Tra cứu ID theo một thuộc tính chính xác | Rất phù hợp | Database index nếu dữ liệu gốc ở SQL |
| AND/OR trên vài nhóm nhỏ | `SINTER`/`SUNION` thuận tiện | Query planner của database/search engine nếu tổ hợp phức tạp |
| Kiểm tra một ID có thuộc nhóm | `SISMEMBER` nhanh | Truy vấn theo primary record nếu cần tính đúng tuyệt đối |
| Sắp xếp theo giá, điểm, ngày tạo | Set không có thứ tự | Redis Sorted Set hoặc database ORDER BY |
| Phân trang ổn định hàng triệu kết quả | Set không có thứ tự ổn định | Cursor trên cơ sở dữ liệu/search index phù hợp |
| Full-text search, prefix, fuzzy, ranking | Set thủ công khó mở rộng | Công cụ tìm kiếm chuyên dụng hoặc Redis Search khi môi trường hỗ trợ |
| Nhiều điều kiện trên Redis Cluster khác slot | Lệnh native nhiều key bị giới hạn | Lọc ở client, bố trí slot có chủ đích hoặc hệ thống truy vấn khác |
| Cập nhật dữ liệu gốc và index atomic xuyên SQL + Redis | Không tự hỗ trợ | Outbox/event-driven sync và reconciliation; source-of-truth ở database |

Lựa chọn Set index phù hợp khi ứng dụng biết trước số lượng thuộc tính cần index, phần lớn truy vấn là membership và kết hợp tập, cùng với việc chấp nhận và quản lý chi phí duy trì index.

Nếu phải hỗ trợ hàng chục trường lọc động, sắp xếp nhiều kiểu, phân trang ổn định, thống kê phức tạp và giao dịch đồng thời, hãy xem xét lại việc xây dựng một query engine thủ công bằng nhiều Set.

## 26. Thực hành với Redis CLI

Các lệnh trong phần này ghi dữ liệu thử nghiệm có prefix `demo:lesson141:`. Chỉ chạy trên Redis được phép sử dụng cho thực hành, không trên hệ thống có dữ liệu quan trọng mà chưa được đồng ý.

### Bước 1 — Tạo ba bản ghi

```bash
redis-cli HSET demo:lesson141:product:p101 id p101 name "Keyboard A" category keyboard brand acme
redis-cli HSET demo:lesson141:product:p102 id p102 name "Mouse B" category mouse brand acme
redis-cli HSET demo:lesson141:product:p103 id p103 name "Keyboard C" category keyboard brand nova
```

### Bước 2 — Tạo secondary indexes bằng Set

```bash
redis-cli SADD demo:lesson141:idx:category:keyboard p101 p103
redis-cli SADD demo:lesson141:idx:category:mouse p102
redis-cli SADD demo:lesson141:idx:brand:acme p101 p102
redis-cli SADD demo:lesson141:idx:brand:nova p103
```

### Bước 3 — Tìm kiếm và kiểm tra thành viên

```bash
redis-cli SISMEMBER demo:lesson141:idx:category:keyboard p101
redis-cli SCARD demo:lesson141:idx:category:keyboard
redis-cli SMEMBERS demo:lesson141:idx:category:keyboard

redis-cli SINTER demo:lesson141:idx:category:keyboard demo:lesson141:idx:brand:acme
redis-cli SUNION demo:lesson141:idx:category:keyboard demo:lesson141:idx:category:mouse
redis-cli SDIFF demo:lesson141:idx:category:keyboard demo:lesson141:idx:brand:nova
```

Dự kiến:

```text
SISMEMBER keyboard p101 -> 1
SCARD keyboard          -> 2
SINTER keyboard acme    -> {p101}
SUNION keyboard mouse   -> {p101, p102, p103}
SDIFF keyboard nova     -> {p101}
```

Thứ tự ID khi xuất ra `SMEMBERS`, `SINTER`, `SUNION` hoặc `SDIFF` có thể khác giữa các lần và không phải cơ sở để suy ra xếp hạng.

### Bước 4 — Đổi category và cập nhật chỉ mục

```bash
redis-cli HSET demo:lesson141:product:p101 category accessories
redis-cli SREM demo:lesson141:idx:category:keyboard p101
redis-cli SADD demo:lesson141:idx:category:accessories p101

redis-cli SISMEMBER demo:lesson141:idx:category:keyboard p101
redis-cli SISMEMBER demo:lesson141:idx:category:accessories p101
```

Kết quả cuối dự kiến:

```text
keyboard     -> 0
accessories  -> 1
```

Nếu chỉ chạy `HSET` mà không chạy `SREM`/`SADD`, Set index sẽ không tự cập nhật theo trường category trong Redis hash. Đó là điểm cốt lõi của bài thực hành.

### Bước 5 — Quan sát Redis type và TTL

```bash
redis-cli TYPE demo:lesson141:product:p101
# hash

redis-cli TYPE demo:lesson141:idx:category:accessories
# set

redis-cli TTL demo:lesson141:idx:category:accessories
# -1 khi key tồn tại và chưa được gắn expiry
```

Nếu muốn làm lại thực hành, hãy dùng một bộ ID/prefix thử nghiệm mới hoặc dọn từng key đã tạo bằng quy trình được phép. Không dùng `FLUSHDB` để reset một Redis server dùng chung.

## 27. Câu hỏi tự kiểm tra

**1. Vì sao Set index thường lưu ID thay vì lưu toàn bộ object?**

Vì lưu ID giúp tránh nhân bản payload ở nhiều chỉ mục. Khi truy vấn, ứng dụng lấy ID rồi đọc dữ liệu gốc; thay đổi một trường không buộc phải cập nhật nhiều bản JSON trong các Set.

**2. Nếu `SADD key p101` được gọi hai lần, Set có hai `p101` không?**

Không. Redis Set chỉ chứa mỗi member duy nhất một lần. Lệnh `SADD` sau có thể trả 0 vì không thêm thành viên mới.

**3. Tìm các sản phẩm cùng thuộc category keyboard và brand acme cần thao tác Set nào?**

Dùng giao `SINTER` giữa Set `idx:category:keyboard` và `idx:brand:acme` khi điều kiện topology/slot cho phép.

**4. Đổi category của product từ keyboard sang mouse nhưng chỉ ghi lại hash sẽ gây lỗi gì?**

Chỉ mục cũ có thể còn ID (false positive), chỉ mục mới thiếu ID (false negative). Cần cập nhật membership theo thay đổi thuộc tính.

**5. `SMEMBERS` có thích hợp làm API phân trang theo ngày tạo không?**

Không. Set không giữ thứ tự được bảo đảm; `SMEMBERS` trả toàn bộ Set, còn `SSCAN` là quét tăng dần chứ không phải snapshot ổn định. Dùng dữ liệu có thứ tự/sorted index phù hợp khi cần.

**6. Tại sao `SINTER` có thể bị `CROSSSLOT` trong Redis Cluster?**

Vì các Set key thuộc những hash slot khác nhau. Prefix giống nhau không bảo đảm cùng slot; hash tag có thể đặt key về cùng slot nhưng có nguy cơ gây hotspot.

**7. Bản ghi gốc có TTL 5 phút, nhưng Set index không có TTL, điều gì xảy ra sau khi bản ghi hết hạn?**

Set có thể vẫn chứa ID của bản ghi đã biến mất. Cần chính sách dọn index hoặc tái tạo/reconciliation; Redis không tự loại member theo TTL của key gốc.

**8. Redis Repository `@Indexed` và index Set tự viết có tự đồng bộ với nhau không?**

Không thể mặc định như vậy. Repository quản lý index theo cơ chế mapping của nó, còn `RedisTemplate.opsForSet()` thực hiện các lệnh Set do ứng dụng yêu cầu. Phải xác định rõ cơ chế sở hữu và các đường ghi dữ liệu.

**9. Kiểm tra lại category của dữ liệu gốc sau khi lấy ID từ Set khắc phục được mọi lỗi index không?**

Không. Nó có thể lọc false positive nhưng không phục hồi những ID bị bỏ sót khỏi Set chỉ mục mới, tức false negative.

## 28. Kết luận

Tạo chỉ mục phụ bằng Redis Set nghĩa là **ánh xạ một giá trị thuộc tính sang tập ID của các bản ghi phù hợp**. Trong Spring Data Redis, `SetOperations` cung cấp những thao tác nền tảng: `add`/`remove` để duy trì index, `isMember` để kiểm tra, `members`/`scan` để duyệt, `intersect`/`union`/`difference` để kết hợp điều kiện tìm kiếm.

Điều quan trọng nhất là coi secondary index là **dữ liệu dẫn xuất có vòng đời riêng**. Mọi thao tác tạo, đổi thuộc tính, xóa bản ghi và hết hạn đều có thể làm index lệch khỏi dữ liệu gốc nếu không có thiết kế đồng bộ. Với dữ liệu quan trọng, cần kiểm soát ghi đồng thời, cơ chế retry/reconciliation và khả năng rebuild. Với Redis Cluster, phải xét hash slot cho mọi thao tác nhiều key và đánh đổi giữa co-location với phân phối tải. Khi những giới hạn này được hiểu rõ, Set index là công cụ đơn giản, hiệu quả để bổ sung khả năng tra cứu theo thuộc tính cho ứng dụng Spring Data Redis.
