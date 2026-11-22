# Thay đổi schema JSON và kế hoạch di chuyển dữ liệu cũ trong Spring Data Redis

Trong ứng dụng Spring Data Redis, một object Java có thể được tuần tự hóa thành JSON rồi lưu dưới dạng value của Redis string, hoặc dùng JSON ở một thành phần cache cụ thể. Khi class Java thay đổi, JSON cũ vẫn còn trong Redis: Redis không tự đổi tên field, chuyển kiểu dữ liệu hay thêm những giá trị mà phiên bản ứng dụng mới mong đợi. Nếu không chuẩn bị trước, một lần triển khai tưởng như chỉ đổi DTO có thể gây `SerializationException`, cache miss hàng loạt, sai giá trị nghiệp vụ hoặc lỗi đọc dữ liệu giữa các phiên bản ứng dụng.

**Thay đổi schema JSON** là thay đổi hợp đồng của payload đã lưu: tên field, kiểu dữ liệu, cấu trúc lồng nhau, cách biểu diễn thời gian/tiền tệ, thông tin kiểu Java hoặc quy tắc diễn giải dữ liệu. **Di chuyển dữ liệu cũ (data migration)** là quá trình chuyển các payload đã tồn tại sang hợp đồng mới, trong khi vẫn kiểm soát tương thích, TTL, ghi đồng thời, lỗi chuyển đổi và khả năng quay về phiên bản trước.

Bài học xây dựng một ví dụ xuyên suốt với Spring Boot 3.x, Spring Data Redis và Jackson; so sánh các chiến lược migration; đưa ra mã Java cho cách đọc tương thích và ghi theo schema mới; đồng thời trình bày cách triển khai an toàn khi Redis đang chứa dữ liệu thật.

## 1. Schema JSON thực sự tồn tại ở đâu?

Redis lưu key và value là dữ liệu nhị phân. Nếu ứng dụng dùng `StringRedisTemplate` để ghi một chuỗi JSON, hoặc `RedisTemplate` với JSON serializer, Redis nhận những byte JSON đó dưới một **Redis key**. Redis không biết rằng value phải có `productId`, `name` hay `priceMinor`.

Ví dụ phiên bản đầu của một bản ghi sản phẩm:

```json
{
  "id": "p42",
  "name": "Sổ tay",
  "priceMinor": 199000
}
```

Payload này có thể nằm ở:

```text
Redis key  : shop:prod:catalog:product:v1:p42
Redis type : string
Value      : JSON UTF-8 như ví dụ trên
TTL        : 15 phút (nếu đây là cache)
```

Ứng dụng mới muốn dùng model có cấu trúc rõ hơn:

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Sổ tay",
  "money": {
    "amountMinor": 199000,
    "currency": "VND"
  }
}
```

Thay đổi trên bao gồm ba quyết định: đổi `name` thành `displayName`, đổi `priceMinor` thành một object `money`, và thêm `schemaVersion`. Trong ví dụ học tập này, hệ thống **đã có quy ước từ phiên bản 1 rằng tất cả số tiền đều tính bằng VND và đơn vị nhỏ nhất là đồng**; vì thế có thể điền `currency: "VND"` một cách có căn cứ. Nếu dữ liệu cũ có nhiều đơn vị tiền hoặc thiếu thông tin xác định đơn vị, quá trình migration phải tra cứu nguồn nghiệp vụ đáng tin cậy, không được tự gán `VND` theo suy đoán.

Redis sẽ giữ nguyên payload v1 cho tới khi một client ghi thay thế, key hết hạn, hoặc có quá trình chuyển đổi có chủ đích.

## 2. Điều gì có thể hỏng khi ứng dụng đổi class Java?

Giả sử phiên bản 1 dùng record:

```java
public record ProductV1(String id, String name, long priceMinor) {}
```

Phiên bản 2 đổi thành:

```java
public record MoneyV2(long amountMinor, String currency) {}

public record ProductV2(
        int schemaVersion,
        String id,
        String displayName,
        MoneyV2 money) {}
```

Nếu code mới đọc JSON cũ trực tiếp thành `ProductV2`, kết quả phụ thuộc cấu hình Jackson và ràng buộc kiểu:

- Trường `name` cũ có thể bị coi là trường không biết đến và gây lỗi khi `FAIL_ON_UNKNOWN_PROPERTIES` được bật, hoặc bị bỏ qua khi cấu hình cho phép.
- `displayName` và `money` không xuất hiện trong JSON cũ, vì vậy có thể nhận `null` nếu model/mapper không bắt buộc giá trị.
- `schemaVersion` là `int` nguyên thủy nên có thể bị gán giá trị mặc định `0` khi field vắng mặt, làm ứng dụng hiểu sai rằng dữ liệu hợp lệ.
- Nếu code mặc định gọi `product.money().amountMinor()`, giá trị `money == null` có thể gây `NullPointerException` sau khi deserialize tưởng như thành công.

Điểm nguy hiểm là **không phải mọi bất tương thích đều biểu hiện thành exception ở bước parse JSON**. Payload có thể được đọc thành object thiếu dữ liệu rồi gây lỗi nghiệp vụ ở bước sau.

Một hợp đồng JSON ổn định cần làm rõ cả hai chiều:

1. **Writer** ghi những field và giá trị nào?
2. **Reader** chấp nhận những phiên bản và điều kiện hợp lệ nào?

Trong hệ thống rolling deployment, hai chiều này đặc biệt quan trọng vì phiên bản cũ và mới có thể chạy cùng lúc.

## 3. Phân biệt đổi Java class, đổi JSON schema và đổi key

Ba thay đổi thường đi cùng nhau nhưng là ba vấn đề khác nhau:

| Thay đổi | Ví dụ | Tác động |
|---|---|---|
| Đổi class/package Java | `ProductDto` thành `CatalogProduct` | Có thể không ảnh hưởng JSON thuần nếu tên field giữ nguyên; có thể phá tương thích nếu JSON chứa metadata tên class |
| Đổi schema payload | `priceMinor` thành `money.amountMinor` | Reader cũ/mới có thể không hiểu payload của nhau |
| Đổi Redis key | `product:p42` thành `shop:prod:catalog:product:v2:p42` | Ứng dụng mới không tự tìm được dữ liệu ở key cũ |
| Đổi serializer | JDK serialization thành JSON | Byte format thay đổi hoàn toàn; đọc cùng key bằng serializer mới thường thất bại |
| Đổi Redis data type | String JSON sang Redis hash | `GET` và `HGETALL` là hai nhóm command khác nhau; phải đổi cách truy cập |

Ví dụ với `GenericJackson2JsonRedisSerializer`, JSON có thể chứa metadata kiểu để tái tạo giá trị đa hình. Nếu metadata chỉ tới một Java class không còn tồn tại sau khi đổi package hoặc đổi tên class, việc deserialize có thể thất bại dù các field JSON về nghiệp vụ không đổi. Khi đó cần chiến lược migration metadata kiểu, cấu hình mapping có kiểm soát hoặc ngừng phụ thuộc vào tên class Java trong payload dài hạn.

`Jackson2JsonRedisSerializer<T>` dùng kiểu đích xác định có hợp đồng khác với serializer JSON tổng quát. Khi lập kế hoạch, luôn ghi lại **serializer và cấu hình `ObjectMapper` thực tế đã dùng khi ghi dữ liệu v1**; chỉ nhìn thấy ký tự `{` ở đầu value không đủ để chứng minh mọi payload đều có cùng schema.

## 4. Phân loại mức độ tương thích của thay đổi JSON

Không phải thay đổi nào cũng bắt buộc di trú mọi key. Hãy phân loại theo những reader và writer còn hoạt động:

| Loại thay đổi | Ví dụ | Rủi ro | Hướng xử lý thường gặp |
|---|---|---|---|
| Thêm field tùy chọn | Thêm `description` | Reader cũ có thể từ chối unknown property; reader mới phải chấp nhận field thiếu | Cho phép đọc field bổ sung có chủ đích; áp giá trị mặc định có căn cứ |
| Thêm field bắt buộc | Thêm `currency` | Payload cũ thiếu thông tin; `null` gây lỗi | Migration có nguồn dữ liệu hoặc policy rõ ràng; kiểm tra tính hợp lệ |
| Đổi tên field | `name` → `displayName` | Reader mới không thấy field cũ | `@JsonAlias` giai đoạn chuyển tiếp hoặc migrator tường minh |
| Xóa field | Bỏ `legacyCode` | Reader cũ có thể vẫn cần | Triển khai reader mới trước khi ngừng writer cũ; loại bỏ theo giai đoạn |
| Đổi kiểu | `"199000"` → `199000` | Parsing hoặc diễn giải giá trị khác | Converter có kiểm soát, kiểm tra overflow và dữ liệu không hợp lệ |
| Thay đổi đơn vị | Đồng → nghìn đồng | Có thể đọc được nhưng sai số tiền | Version hóa schema, chuyển đổi với công thức và làm tròn xác định |
| Đổi cấu trúc lồng nhau | `priceMinor` → `money.amountMinor` | Reader cũ không biết cấu trúc mới | Version key/payload, adapter và kế hoạch triển khai đồng bộ |
| Đổi format thời gian | Epoch millis → ISO-8601 | Sai timezone hoặc parse fail | Ghi rõ đơn vị, timezone và serializer/module hỗ trợ |
| Đổi metadata kiểu | Đổi package/class trong JSON polymorphic | Không dựng được đối tượng | Chuyển metadata/schema hoặc sử dụng wire DTO độc lập class |
| Đổi Redis data type | String → Hash | Command sai trả `WRONGTYPE` | Chuyển sang key khác và migration dữ liệu |

**Tương thích tiến/lùi** không phải thuộc tính của JSON tự thân. Một payload chỉ tương thích khi đúng reader có thể đọc và hiểu nó theo cùng ngữ nghĩa. Hệ thống cần định nghĩa chính xác phiên bản nào có thể đọc phiên bản nào.

## 5. Hợp đồng JSON nên độc lập với domain object

Một lựa chọn giúp giảm rủi ro là tách **model lưu trong Redis** khỏi domain model và API response. Khi class nội bộ thay đổi, định dạng Redis có thể tiếp tục giữ nguyên; khi thật sự cần đổi định dạng, tầng chuyển đổi sẽ đảm nhận việc migration.

```text
REST Controller / Domain Service
              |
              v
       Product domain model
              |
         mapper rõ ràng
              |
              v
        ProductRedisV2
              |
     ObjectMapper / serializer
              |
              v
      JSON UTF-8 trong Redis
```

Ví dụ quy tắc dữ liệu v2:

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Sổ tay",
  "money": {
    "amountMinor": 199000,
    "currency": "VND"
  }
}
```

Điều kiện hợp lệ có thể gồm `schemaVersion == 2`, `id` không rỗng, `money` bắt buộc có mặt, `currency` thuộc danh sách hỗ trợ và `amountMinor >= 0` nếu đó là ràng buộc của nghiệp vụ. Cần kiểm tra các điều kiện này **sau khi parse JSON**, bởi Jackson không tự biết tất cả bất biến của nghiệp vụ.

Nếu cần giữ tương thích với các consumer ngoài Java, tránh để payload Redis chứa tên class/package Java mà consumer không hiểu. Dùng trường version và DTO biểu diễn dữ liệu độc lập với implementation sẽ làm hợp đồng dễ duy trì hơn.

## 6. Hai vị trí đặt phiên bản schema

Có thể ghi version **trong payload**, **trong tên Redis key**, hoặc dùng cả hai khi có lý do cụ thể.

### 6.1. Version nằm trong JSON

```text
Key: shop:prod:catalog:product:p42
```

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Sổ tay",
  "money": {"amountMinor": 199000, "currency": "VND"}
}
```

Ưu điểm: ứng dụng có thể đọc `schemaVersion` và chọn decoder phù hợp mà không cần đổi định danh key. Nhược điểm: nếu old/new writers ghi cùng một key khi rolling deployment, chúng có thể **ghi đè schema của nhau**, và reader cũ có thể không đọc nổi payload mới. Đường ghi phải được phối hợp cẩn thận.

### 6.2. Version nằm trong tên key

```text
shop:prod:catalog:product:v1:p42
shop:prod:catalog:product:v2:p42
```

Ưu điểm: old/new payload có thể tồn tại song song, mỗi reader biết chính xác format mình cần; dễ triển khai cơ chế ưu tiên v2 rồi fallback v1. Nhược điểm: cần chính sách giữ TTL, dọn dữ liệu cũ, đọc hai key khi cache miss và xử lý chênh lệch dữ liệu giữa hai version.

Thêm version trong key không tự giải quyết tính nhất quán khi cùng lúc có nhiều writer. Nếu value v1 thay đổi sau khi đã tạo v2, v2 có thể trở nên cũ; phải xác định nguồn sự thật và quy tắc đồng bộ.

### 6.3. Chọn cách nào?

| Bối cảnh | Lựa chọn phù hợp để cân nhắc |
|---|---|
| Cache có TTL ngắn, có thể dựng lại từ database | Đổi cache prefix/version và để v1 tự hết hạn, thường không cần migrate từng key |
| Cùng một key bắt buộc giữ nguyên vì bên ngoài tham chiếu | Version trong payload và reader hỗ trợ nhiều schema, sau đó phối hợp nâng writer |
| Payload mới khác lớn, cần chạy hai phiên bản song song | Key v1/v2 song song với kế hoạch fallback và đồng bộ |
| Dữ liệu lâu dài hoặc là nguồn sự thật | Migration được kiểm soát, backfill, xác minh và rollback theo hợp đồng dữ liệu |
| Redis hash/repository có key phụ/index | Thiết kế migration cho toàn bộ cấu trúc, không chỉ JSON của value chính |

Không cần gắn `v1`, `v2` vào mọi key Redis. Version có giá trị khi nó giúp phân biệt các biểu diễn **không tương thích** hoặc phục vụ rollout/rollback có kiểm soát.

## 7. Chọn chiến lược di chuyển dữ liệu cũ

Có bốn chiến lược thường gặp. Chúng có thể kết hợp, nhưng cần quyết định rõ đâu là cơ chế chính và điều kiện kết thúc migration.

### 7.1. Bỏ cache cũ, dựng cache mới

Đối với cache có thể tạo lại từ nguồn dữ liệu đáng tin cậy, cách đơn giản là đổi prefix cache sang v2:

```text
Cache v1: shop:prod:cache:catalog-products:v1::p42
Cache v2: shop:prod:cache:catalog-products:v2::p42
```

Ứng dụng mới chỉ đọc/ghi v2. Dữ liệu v1 tự hết hạn theo TTL. Cần dự kiến tỷ lệ cache miss tăng sau triển khai; nếu quá nhiều request đồng thời cùng nạp lại dữ liệu, database nguồn có thể bị đột biến tải. Có thể prewarm hoặc rollout theo tỷ lệ phù hợp.

Phương án này không phù hợp nếu Redis đang lưu state không thể khôi phục hoặc dữ liệu nghiệp vụ không có nguồn thay thế.

### 7.2. Lazy migration / read repair

Ứng dụng mới đọc key v2 trước. Nếu v2 chưa tồn tại, nó đọc v1, giải mã đúng schema cũ, chuyển thành v2, ghi key mới và trả kết quả.

```text
GET key:v2
   |
   +-- HIT ----------> parse/validate v2 --> return
   |
   +-- MISS
        |
      GET key:v1
        |
        +-- MISS ------> lấy dữ liệu nguồn / trả cache miss
        |
        +-- HIT ------> parse v1 -> transform -> ghi v2 -> return
```

Ưu điểm: chỉ chuyển những key được truy cập. Nhược điểm: read miss tốn thêm lệnh Redis, key ít được đọc có thể không bao giờ chuyển, và việc đọc v1 khi nó đang được ghi đồng thời cần quy tắc nhất quán riêng.

### 7.3. Batch backfill

Một job chuyên dụng quét key v1 theo từng batch có giới hạn tốc độ, chuyển payload sang schema mới và theo dõi tiến độ. Trên standalone có thể sử dụng `SCAN MATCH <pattern>`; trên Redis Cluster phải dùng client/công cụ hiểu topology và quét các primary phù hợp.

`SCAN` không cung cấp snapshot nhất quán và có thể trả cùng key nhiều lần, vì vậy job migration phải **idempotent**. Không dùng `KEYS *` làm cơ chế quét production với hàng triệu key. Backfill hữu ích khi cần di chuyển cả key không được truy cập, nhưng phải kiểm soát cạnh tranh với writer đang hoạt động.

### 7.4. Dual-write trong giai đoạn chuyển tiếp

Khi cả consumer v1 và consumer v2 còn chạy, writer mới có thể ghi hai biểu diễn:

```text
Business update
   |
   +--> write v1 cho reader cũ
   |
   +--> write v2 cho reader mới
```

Việc ghi hai key bằng hai lệnh riêng **không tự bảo đảm atomicity**. Nếu một lệnh thành công và lệnh kia thất bại, dữ liệu sẽ khác nhau. Với Redis Cluster, nếu các key ở hash slot khác nhau, không thể đơn giản bao chúng trong một transaction/Lua script đa key. Cần chọn cơ chế bảo đảm dữ liệu theo yêu cầu: nguồn dữ liệu chính bên ngoài Redis, event có thể replay, migration có thể chạy lại, hoặc đồng nhất slot khi cần và khi thực sự hợp lý.

Dual-write là giai đoạn tạm thời có ngày kết thúc; giữ mãi hai định dạng làm tăng khả năng divergence và chi phí bảo trì.

## 8. So sánh chiến lược theo thuộc tính dữ liệu

| Chiến lược | Thích hợp | Lợi ích | Rủi ro cần kiểm soát |
|---|---|---|---|
| Đổi prefix rồi dựng lại | Cache có nguồn gốc, TTL ngắn | Đơn giản, không parse dữ liệu cũ | Cache miss spike và tải nguồn |
| Lazy migration | Tập key lớn nhưng phần lớn ít được đọc | Chỉ migrate dữ liệu đang dùng | Lỗi đọc v1 ở request path; stale write |
| Batch backfill | Dữ liệu dài hạn, muốn hoàn tất migration | Có tiến độ và thống kê rõ | Tải Redis, thay đổi đồng thời, key bị bỏ sót |
| Dual-write | Rolling deployment, consumer cũ/mới cùng tồn tại | Duy trì hai hệ đọc | Ghi không đồng bộ; cần kết thúc giai đoạn chuyển tiếp |
| Big-bang migration với đóng băng ghi | Bộ dữ liệu nhỏ, cho phép downtime | Dễ xác lập thời điểm nhất quán | Dừng ghi/downtime và rollback phức tạp |

Một hệ thống thường dùng **dual-read + v2-only-write + backfill** cho dữ liệu có thể chuyển dần, nhưng chỉ áp dụng khi mọi consumer v1 đã ngừng ghi hoặc writer cũ không còn gây cập nhật khác biệt. Nếu không, cần giải quyết xung đột trước thay vì mặc định bản v2 luôn mới nhất.

## 9. Ví dụ thực hành: schema v1 và schema v2 bằng Jackson

Giả sử ứng dụng Spring Boot 3.x/Java 21 dùng `StringRedisTemplate` để lưu JSON UTF-8. Cả hai schema có Redis type là **string**; việc chuyển schema không làm Redis tự đổi sang hash.

### JSON v1

```json
{
  "id": "p42",
  "name": "Sổ tay",
  "priceMinor": 199000
}
```

### JSON v2

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Sổ tay",
  "money": {
    "amountMinor": 199000,
    "currency": "VND"
  }
}
```

Các DTO dành riêng cho định dạng Redis:

```java
public record ProductV1(String id, String name, long priceMinor) {}

public record MoneyV2(long amountMinor, String currency) {}

public record ProductV2(
        int schemaVersion,
        String id,
        String displayName,
        MoneyV2 money) {}
```

Hàm chuyển đổi nghiệp vụ:

```java
public final class ProductSchemaMigration {
    private ProductSchemaMigration() {}

    public static ProductV2 toV2(ProductV1 legacy) {
        if (legacy == null || legacy.id() == null || legacy.id().isBlank()) {
            throw new IllegalArgumentException("Invalid legacy product id");
        }
        if (legacy.name() == null || legacy.name().isBlank()) {
            throw new IllegalArgumentException("Invalid legacy product name");
        }
        if (legacy.priceMinor() < 0) {
            throw new IllegalArgumentException("Invalid legacy price");
        }
        // Hợp đồng dữ liệu v1 của ví dụ xác định giá luôn tính bằng VND.
        return new ProductV2(
                2,
                legacy.id(),
                legacy.name(),
                new MoneyV2(legacy.priceMinor(), "VND"));
    }
}
```

Đây là phép chuyển đổi **có ý nghĩa nghiệp vụ**: không chỉ đổi tên field mà còn tạo cấu trúc tiền mới. Với dữ liệu thực tế, cần bổ sung quy tắc về null, loại tiền, số tiền âm, sản phẩm đã bị xóa hoặc dữ liệu v1 từng có lỗi.

## 10. Ví dụ đọc tương thích và chuyển dữ liệu khi truy cập

Đoạn code sau minh họa chiến lược **read v2 → fallback v1 → convert → write v2**, đồng thời cố gắng giữ thời gian sống còn lại của key v1. Nó phù hợp như một bản mẫu cho cache có **một writer điều phối**, nơi dữ liệu v1 không tiếp tục được cập nhật sau khi triển khai v2. Các tình huống nhiều writer và tính nhất quán cao cần thiết kế bổ sung ở phần sau.

```java
package com.example.catalog.redis;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRedisStore {

    public record ProductV1(String id, String name, long priceMinor) {}
    public record MoneyV2(long amountMinor, String currency) {}
    public record ProductV2(
            int schemaVersion,
            String id,
            String displayName,
            MoneyV2 money) {}

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public ProductRedisStore(StringRedisTemplate redis, ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public ProductV2 read(String productId) throws JsonProcessingException {
        String id = validId(productId);
        String currentKey = keyV2(id);

        String currentJson = redis.opsForValue().get(currentKey);
        if (currentJson != null) {
            return parseV2(currentJson, id);
        }

        String legacyKey = keyV1(id);
        String legacyJson = redis.opsForValue().get(legacyKey);
        if (legacyJson == null) {
            return null; // Không có cache ở cả hai phiên bản.
        }

        ProductV1 old = mapper.readValue(legacyJson, ProductV1.class);
        if (!id.equals(old.id()) || old.name() == null || old.name().isBlank()
                || old.priceMinor() < 0) {
            throw new IllegalStateException("Invalid ProductV1 payload");
        }

        ProductV2 converted = new ProductV2(
                2, old.id(), old.name(),
                new MoneyV2(old.priceMinor(), "VND"));

        // Lấy TTL sau khi đọc value v1; key có thể đã hết hạn trong lúc đó.
        Long ttlMillis = redis.getExpire(legacyKey, TimeUnit.MILLISECONDS);
        if (ttlMillis == null || ttlMillis == -2L || ttlMillis == 0L) {
            return null;
        }

        String migratedJson = mapper.writeValueAsString(converted);
        if (ttlMillis == -1L) {
            // V1 không có TTL: chỉ dùng nếu hợp đồng thực sự cho phép tồn tại lâu dài.
            redis.opsForValue().setIfAbsent(currentKey, migratedJson);
        } else if (ttlMillis > 0L) {
            redis.opsForValue().setIfAbsent(
                    currentKey, migratedJson, Duration.ofMillis(ttlMillis));
        }

        // Một writer khác có thể đã ghi v2 trước; đọc lại giá trị cuối tại v2.
        String finalJson = redis.opsForValue().get(currentKey);
        return finalJson == null ? null : parseV2(finalJson, id);
    }

    private ProductV2 parseV2(String json, String expectedId)
            throws JsonProcessingException {
        ProductV2 value = mapper.readValue(json, ProductV2.class);
        if (value.schemaVersion() != 2
                || !expectedId.equals(value.id())
                || value.displayName() == null
                || value.displayName().isBlank()
                || value.money() == null
                || value.money().amountMinor() < 0
                || !"VND".equals(value.money().currency())) {
            throw new IllegalStateException("Invalid ProductV2 payload");
        }
        return value;
    }

    private static String validId(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid product ID");
        }
        return id;
    }

    private static String keyV1(String id) {
        return "shop:prod:catalog:product:v1:" + id;
    }

    private static String keyV2(String id) {
        return "shop:prod:catalog:product:v2:" + id;
    }
}
```

**Điều mã minh họa bảo đảm ở mức ý tưởng:** reader ưu tiên schema v2, dùng riêng class v1 để đọc payload cũ, không ghi đè key v2 đã tồn tại nhờ `setIfAbsent`, kiểm tra trường bắt buộc và giữ TTL còn lại theo số mili giây khi có thể.

**Những giới hạn phải hiểu trước khi ứng dụng thực tế:**

- `GET v1`, `PTTL v1` và `SET ... NX v2` là những lệnh riêng. Giá trị v1 hoặc TTL có thể đổi giữa các lệnh; đoạn code **không cung cấp snapshot/transaction** và không bảo đảm tính nhất quán tuyệt đối khi có writer song song.
- TTL bị trừ dần trong thời gian các lệnh chạy; TTL đặt cho v2 chỉ là một nỗ lực giữ thời hạn tương đương, có thể lệch thời gian thực. Với dữ liệu cần ngày hết hạn tuyệt đối, hãy lưu `expiresAt` có nghĩa nghiệp vụ và dùng cơ chế chuyển đổi phù hợp.
- Nếu key v1 đã biến mất ở thời điểm kiểm tra TTL, đoạn code trả cache miss; hệ thống phải nạp dữ liệu lại từ nguồn chính thay vì phục hồi key vừa hết hạn.
- `setIfAbsent` trả về `Boolean` hoặc `null` trong một số ngữ cảnh; ở đây không dựa vào giá trị trả về mà đọc lại v2. Nếu không được phép đọc/ghi Redis, lỗi được truyền tới caller, không âm thầm thay bằng kết quả rỗng.
- Đoạn code giả định mọi dữ liệu v1 đều mang đơn vị tiền `VND`, đã được định nghĩa trong hợp đồng lịch sử của ví dụ. Không suy ra currency từ tên field hoặc giá trị số ở dữ liệu thật.
- Prefix `shop:prod` được viết cố định cho mục đích minh họa; trong ứng dụng nên tạo qua cấu hình môi trường và key builder tập trung.

Một hệ thống cần bảo đảm không trả dữ liệu cũ khi v1 đang cập nhật phải bổ sung cơ chế version nguồn, fencing, event sequence, khóa thích hợp hoặc lấy dữ liệu từ database chính. Không dùng read repair đơn giản làm cơ chế đồng bộ authoritative state nhiều writer.

## 11. Tách reader và writer để tránh ghi ngược schema

Trong rollout nhiều phiên bản, mô hình an toàn hơn là làm rõ **năng lực đọc** và **quyền ghi** theo từng giai đoạn:

```text
Giai đoạn A: ứng dụng cũ     -> read v1, write v1
Giai đoạn B: ứng dụng mới    -> read v1/v2, write v1 (nếu còn cần old reader)
Giai đoạn C: tất cả reader   -> read v1/v2; writer chuyển sang v2
Giai đoạn D: backfill        -> chuyển v1 còn lại sang v2
Giai đoạn E: hết fallback    -> chỉ read/write v2
```

Sơ đồ này là **trình tự năng lực**; cách triển khai chính xác phụ thuộc việc old reader có thể chạy song song với new writer hay không. Nếu old reader không đọc được v2 trong cùng một key, không được thay payload ở chính key v1 khi old reader còn hoạt động.

Ví dụ sử dụng key v1 và v2 riêng:

```text
Old application: GET/SET key:v1
New application: GET key:v2; fallback key:v1; SET key:v2
```

Nếu old application tiếp tục cập nhật v1, key v2 vừa migrate có thể thành stale. Muốn chạy song song, cần một trong các cách sau:

- Quy định một nguồn sự thật bên ngoài Redis và invalidation cả hai cache theo sự kiện cập nhật.
- Dual-write có cơ chế xử lý khi ghi một phiên bản thất bại.
- Tạm dừng hoặc chuyển hẳn quyền ghi v1 trước khi backfill và ưu tiên v2.
- Gắn `revision` hoặc `updatedAt` có ý nghĩa nghiệp vụ, so sánh phiên bản khi quyết định nguồn nào mới hơn.

Tránh chọn “v2 luôn đúng vì tên lớn hơn” khi không có bằng chứng về trình tự ghi.

## 12. Rolling deployment: ma trận đọc/ghi phải được viết trước

Một bảng quyết định giúp phát hiện lỗi triển khai trước khi chạy:

| Phiên bản ứng dụng | Đọc v1 | Đọc v2 | Ghi v1 | Ghi v2 |
|---|---|---|---|---|
| Ứng dụng cũ | Có | Không | Có | Không |
| Phiên bản tương thích (bridge) | Có | Có | Theo giai đoạn | Theo giai đoạn |
| Ứng dụng mới cuối cùng | Tạm thời, sau đó bỏ | Có | Không | Có |

Không nên sử dụng “deploy tất cả pod thật nhanh” để thay cho một kế hoạch tương thích. Với Kubernetes, rolling update hoặc nhiều instance chạy song song, chỉ cần một old writer còn hoạt động cũng có thể làm hỏng giả định của migration.

Với schema trong **cùng một key**, thứ tự an toàn thường là triển khai **reader mới có thể chấp nhận schema cũ**, xác nhận toàn bộ reader đã được nâng, rồi mới thay đổi định dạng writer. Nếu cần rollback về phiên bản cũ sau khi writer đã phát JSON v2, phải xem phiên bản cũ có đọc được JSON v2 hay không; rollback code đơn thuần có thể không phục hồi khả năng đọc dữ liệu.

Với **hai key version riêng**, có thể giữ v1 để hỗ trợ rollback trong khoảng thời gian xác định, nhưng phải quyết định cách đồng bộ cập nhật và khi nào được dọn key cũ.

## 13. Chuyển dữ liệu theo batch: thuật toán và điều kiện idempotent

Một batch migrator nên có quy trình rõ ràng:

```text
1. Xác định phạm vi: namespace, environment, tenant, schema/version nguồn.
2. Duyệt tăng dần các key v1 bằng SCAN và giữ giới hạn batch.
3. Kiểm tra TYPE, đọc dữ liệu và TTL bằng API phù hợp.
4. Parse bằng schema/serializer v1; xác thực dữ liệu nguồn.
5. Transform sang v2 bằng hàm thuần có quy tắc nghiệp vụ rõ ràng.
6. Ghi sang key v2 với điều kiện không ghi đè dữ liệu mới hơn.
7. Ghi nhận số key chuyển thành công, bị bỏ qua, lỗi, quá hạn.
8. Chạy tiếp từ checkpoint có thể khôi phục và đối chiếu dữ liệu.
9. Khi read fallback gần bằng 0 và owner xác nhận, kết thúc migration.
```

Ví dụ lệnh duyệt trên standalone thử nghiệm:

```bash
redis-cli --scan --pattern 'shop:prod:catalog:product:v1:*'
```

Không nên dùng `KEYS shop:prod:catalog:product:v1:*` làm phương án mặc định với dữ liệu lớn vì `KEYS` có thể làm Redis bận xử lý một khối lượng key đáng kể trong một lệnh.

`SCAN` không phải snapshot và không bảo đảm key nào cũng chỉ xuất hiện một lần trong lúc keyspace đang thay đổi. Migrator phải xử lý duplicate, key hết hạn trong lúc đọc, key bị ghi lại và những key tạo mới giữa các vòng scan. Checkpoint kiểu `lastKey` không phải cursor an toàn nếu keyspace được duyệt không có thứ tự; với dữ liệu phải di chuyển hết, có thể cần quét lại nhiều vòng hoặc dựa vào nguồn sự thật độc lập.

### Quy tắc idempotence

Nếu job chuyển v1 của `p42` thành v2 rồi bị dừng, chạy lại không được làm hỏng v2 hoặc tiếp tục gia hạn TTL vô hạn. Việc ghi `SET ... NX`/`setIfAbsent` có thể tránh ghi đè v2, nhưng nếu dữ liệu v1 đã đổi và v2 được tạo trước đó thì chỉ “không ghi đè” **không giải quyết sự nhất quán**. Cần biết key v1 đã bị đóng ghi chưa, hoặc có revision/version để chọn dữ liệu đúng.

Với lỗi chuyển đổi, nên phân nhóm như `invalid-json`, `missing-required-field`, `unknown-currency`, `serializer-mismatch`, `expired-during-migration` và `redis-write-error` trong thống kê kỹ thuật. Tránh ghi toàn bộ payload người dùng hoặc secret vào log/dead-letter chỉ để dễ debug.

## 14. Giữ TTL khi chuyển schema

TTL là một phần của hợp đồng dữ liệu, đặc biệt với cache, session, token và rate limit. Nếu key v1 chỉ còn 120 giây mà migrator ghi key v2 với TTL mặc định 24 giờ, ứng dụng có thể giữ dữ liệu cũ lâu hơn dự kiến.

Redis cung cấp:

```redis
TTL shop:prod:catalog:product:v1:p42
PTTL shop:prod:catalog:product:v1:p42
```

Ý nghĩa kết quả:

| Kết quả | `TTL` | `PTTL` |
|---|---|---|
| Số dương | Số giây còn lại | Số mili giây còn lại |
| `-1` | Key tồn tại nhưng không có expiry | Tương tự |
| `-2` | Key không còn tồn tại | Tương tự |
| `0` | Có thể còn dưới một đơn vị đo tương ứng trước khi hết hạn | Có thể hết hạn sát thời điểm đo |

Khi tạo key v2, cần chọn một trong các quy tắc có chủ đích:

1. **Giữ thời điểm hết hạn tương đương:** lấy TTL còn lại và áp vào v2, có xét độ trễ migration; phù hợp cache/session mà không muốn gia hạn vòng đời.
2. **Giữ expiry tuyệt đối:** nếu nghiệp vụ lưu `expiresAt` ở nguồn đáng tin cậy, dùng thời điểm đó và quy tắc nhất quán giữa các writer để tránh sai lệch do độ trễ.
3. **Tạo TTL mới:** chỉ khi nghiệp vụ cho phép reset thời hạn khi dữ liệu được làm mới.
4. **Không TTL:** chỉ khi dữ liệu được phép tồn tại vô hạn; không biến một key cache có TTL thành key vĩnh viễn do bỏ sót `EXPIRE`.

Các lệnh `GET`, `PTTL`, `SET` riêng lẻ có race condition. Trên một node hoặc các key cùng slot trong Cluster, một script Lua hoặc transaction phù hợp có thể giúp gom những thao tác cần atomicity; cần thiết kế cụ thể và kiểm tra tính khả thi, không mặc định mọi cặp key cũ/mới có thể được thao tác atomic trên Cluster.

Đối với key **không có TTL**, phải xem nó thực sự là dữ liệu lưu lâu dài hay chỉ là key bị thiếu cấu hình expiry trong phiên bản cũ. Một migration không nên tự động hợp thức hóa lỗi TTL trước đây mà không có quyết định nghiệp vụ.

## 15. Xử lý cập nhật đồng thời và thứ tự phiên bản

Trường hợp nguy hiểm:

```text
T1: Migrator đọc v1 = giá 100
T2: Ứng dụng cũ cập nhật v1 = giá 120
T3: Migrator ghi v2 = giá 100
T4: Ứng dụng mới đọc v2 = giá 100 (đã cũ)
```

Nếu Redis chỉ là cache, có thể giải quyết bằng invalidation v2 khi giá thay đổi trong nguồn dữ liệu chính, sau đó nạp lại dữ liệu. Nếu Redis là nơi sở hữu dữ liệu có cập nhật quan trọng, phải định nghĩa chiến lược concurrency chặt hơn.

Các cách xử lý thường thấy:

- **Chuyển quyền ghi:** đóng writer v1, xác nhận không còn cập nhật v1, rồi batch migrate dữ liệu còn lại.
- **Revision/sequence:** mỗi bản ghi có version tăng đơn điệu từ nguồn nghiệp vụ; migrator chỉ ghi nếu revision nguồn phù hợp và không cũ hơn v2.
- **Compare-and-set:** đọc version và thực hiện ghi có điều kiện bằng cơ chế atomic phù hợp với topology.
- **Event-driven synchronization:** các thay đổi được ghi vào nguồn bền vững, phát event có thể replay và apply đúng thứ tự/phiên bản cho cache v2.
- **Đặt một nguồn sự thật:** luôn lấy trạng thái xác thực từ database nghiệp vụ, Redis là bản sao có thể tạo lại.

Không giải quyết concurrency chỉ bằng cách “chạy migration vào giờ ít người dùng”: tải thấp giảm xác suất race, nhưng không bảo đảm v1 không được cập nhật.

### Redis Cluster làm gì khác?

Redis Cluster yêu cầu những thao tác đa key có tính atomic nằm trên các key cùng hash slot. Hai key như:

```text
shop:prod:catalog:product:v1:p42
shop:prod:catalog:product:v2:p42
```

có thể thuộc hai slot khác nhau. Client có thể `GET` từ một slot rồi `SET` ở slot khác, nhưng không có transaction/Lua atomic chung cho hai key khác slot bằng một lệnh Redis Cluster thông thường.

Nếu ngay từ đầu biết cần atomic thao tác nhiều phiên bản của cùng một thực thể, có thể thiết kế hash tag theo ID:

```text
shop:prod:catalog:product:{p42}:v1
shop:prod:catalog:product:{p42}:v2
```

Hai key này cùng slot. Tuy vậy, việc đổi key hiện có sang định dạng hash tag cũng là một migration khác; đừng thay tên key production tùy tiện chỉ để chạy một script ngắn hạn. Dồn tất cả key vào một hash tag như `{catalog}` có thể tạo điểm nóng và làm mất lợi ích phân phối tải.

## 16. Sử dụng Jackson để hỗ trợ chuyển tiếp nhỏ

Với thay đổi nhỏ, đôi khi không cần batch migration ngay. Jackson có thể giúp reader mới chấp nhận field cũ trong giai đoạn chuyển tiếp.

Ví dụ chỉ đổi tên `name` thành `displayName`:

```java
import com.fasterxml.jackson.annotation.JsonAlias;

public record ProductCompatible(
        String id,
        @JsonAlias("name") String displayName,
        long priceMinor) {}
```

`@JsonAlias("name")` cho phép nhận tên trường cũ khi đọc; khi ghi bằng serializer Jackson thông thường, property vẫn dùng tên chính `displayName`. **Alias không tự cập nhật byte JSON cũ trong Redis** và không giải quyết việc nhiều writer tiếp tục sử dụng hai tên field khác nhau.

Một DTO có thể cho phép bỏ qua unknown property:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProductReader(
        String id,
        String displayName,
        long priceMinor) {}
```

Điều này hỗ trợ reader chịu được field bổ sung, nhưng có thể che giấu lỗi schema nếu field bị đổi nhầm hoặc reader thiếu giá trị bắt buộc. Luôn có bước **validate dữ liệu sau deserialize** khi độ chính xác nghiệp vụ quan trọng.

Các lựa chọn khác gồm `@JsonProperty`, `@JsonCreator`, custom deserializer và adapter đọc nhiều schema. Chọn công cụ nào phụ thuộc mức độ thay đổi:

- **Alias** phù hợp rename field đơn giản trong giai đoạn tương thích.
- **Custom deserializer** phù hợp khi cấu trúc khác nhau nhưng có quy tắc ánh xạ rõ.
- **Versioned DTO + migrator** phù hợp khi schema khác lớn, cần audit, backfill hoặc hỗ trợ rollback.

Không nên lạm dụng một DTO với hàng chục alias và default để đọc vô hạn các schema lịch sử. Khi reader cũ đã hết vòng đời và dữ liệu cũ đã chuyển, loại bỏ đường xử lý cũ để giảm gánh nặng bảo trì.

## 17. `RedisTemplate`, Spring Cache và Repository có hợp đồng riêng

Migration phải xác định **ai tạo payload**, bởi cấu hình serialization trong Spring Data Redis khác nhau theo API.

### 17.1. `RedisTemplate` với JSON serializer

Ví dụ:

```java
RedisTemplate<String, ProductV2> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);
template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(
        new Jackson2JsonRedisSerializer<>(ProductV2.class));
template.afterPropertiesSet();
```

Đây là mẫu cấu hình minh họa: key dùng UTF-8 string, value dùng JSON theo `ProductV2`. Nếu trước đó value được ghi bằng `Jackson2JsonRedisSerializer<ProductV1>` hoặc một `ObjectMapper` khác, không thể mặc định serializer v2 sẽ đọc được mọi key v1. Cần xác định format nguồn, sau đó có converter hoặc đường đọc v1 tương ứng.

Nếu `RedisTemplate` có nhiều kiểu value qua một serializer polymorphic, metadata kiểu và trust configuration là một phần hợp đồng. Không bật default typing tùy tiện để đọc “mọi kiểu JSON”; cần giới hạn type phù hợp và tránh deserialize dữ liệu không tin cậy thành class ngoài ý muốn.

### 17.2. Spring Cache dùng `RedisCacheConfiguration`

`@Cacheable` có thể ghi dữ liệu qua `RedisCacheManager`, với cấu hình key prefix, TTL và value serializer riêng. Thay serializer của một bean `RedisTemplate` **không bảo đảm** cache cùng đổi format. Một cách đơn giản cho cache có thể dựng lại là đổi tên cache hoặc prefix/version của Redis Cache để tạo key v2 mới, rồi để cache v1 hết hạn.

```text
Trước: shop:prod:cache:products:v1::p42
Sau:   shop:prod:cache:products:v2::p42
```

Khi muốn thực hiện lazy migration từ v1 sang v2 trong Spring Cache, thường phải đưa logic fallback vào tầng cache adapter/custom wrapper phù hợp. Chỉ đổi `@Cacheable(cacheNames = "products")` không tự cung cấp cơ chế đọc hai phiên bản JSON.

### 17.3. Redis Repository sử dụng mapping riêng

Spring Data Redis Repository với `@RedisHash` thường ánh xạ object thành **Redis hash** qua `MappingRedisConverter`, có thể kèm key metadata/index. Đây không nhất thiết là một JSON string được đọc qua `GET`.

Nếu entity repository thay đổi field hoặc converter, migration có thể cần xử lý tên hash field, keyspace, index, metadata `_class` và các key phụ do framework quản lý. Không áp dụng nguyên xi ví dụ `StringRedisTemplate` v1/v2 ở trên cho repository nếu cấu trúc lưu trữ thực sự là Redis hash. Phải xác định `TYPE <key>` và API tạo dữ liệu trước khi viết migrator.

## 18. Khi serializer cũ không phải JSON

Một hệ thống có thể bắt đầu với `JdkSerializationRedisSerializer`, rồi muốn đổi sang JSON. Đây là chuyển đổi **byte format** chứ không chỉ đổi schema JSON.

```text
V1: Java native serialization bytes
V2: JSON UTF-8
```

Không thể yêu cầu Jackson đọc trực tiếp byte JDK serialization như JSON. Migration cần một decoder tương thích format cũ, một bước chuyển đổi Java object sang DTO v2, rồi một JSON writer mới.

Việc deserialize Java native payload tiềm ẩn rủi ro bảo mật khi dữ liệu không đáng tin cậy hoặc classpath có các class nguy hiểm. Nếu hệ thống cũ bắt buộc dùng JDK deserialization, hãy hạn chế nguồn dữ liệu và áp dụng cơ chế lọc kiểu được JVM/thư viện hỗ trợ; tránh xây dựng công cụ migration chung tùy tiện deserialize mọi byte được tìm thấy trong Redis.

Tương tự, nếu source dùng MessagePack, CBOR, Protocol Buffers hoặc JSON được nén, cần đúng decoder và schema tương ứng. Không nên dựa trên phần mở rộng tên key hay vài ký tự đầu payload để suy đoán serializer.

## 19. Kế hoạch triển khai end-to-end

Giả sử cần chuyển cache sản phẩm từ v1 sang v2 mà vẫn giữ API hoạt động liên tục. Một kế hoạch có thể chia thành các giai đoạn:

### Giai đoạn 0 — Khảo sát và chốt hợp đồng

Ghi nhận `key pattern`, owner, Redis type, serializer, `ObjectMapper`, schema field, thời gian sống, số lượng key ước tính, các writer/reader đang chạy và các quy tắc nghiệp vụ. Phân biệt cache có nguồn gốc với dữ liệu đang đóng vai trò nguồn sự thật. Kiểm kê cả framework-managed keys, không chỉ những key code nghiệp vụ chủ động tạo.

### Giai đoạn 1 — Xây dựng bộ đọc tương thích

Tạo DTO v1 và v2, hàm chuyển đổi có kiểm tra dữ liệu, phân loại lỗi rõ ràng. Với mô hình key version, reader mới ưu tiên v2 và fallback v1. Triển khai reader trước khi thay đổi writer để giảm rủi ro trong rolling deployment.

### Giai đoạn 2 — Điều phối đường ghi

Quy định rõ thời điểm writer v1 dừng hoặc khi nào dual-write bắt đầu. Nếu old reader còn chạy, giữ hợp đồng cũ ở những nơi old reader truy cập. Nếu migration có thể gây cạnh tranh cập nhật, cần nguồn sự thật, revision hoặc cơ chế synchronization phù hợp.

### Giai đoạn 3 — Bật chuyển đổi có giới hạn

Với lazy migration, giới hạn tốc độ chuyển đổi ở request path nếu nó làm tăng latency; với batch migration, giới hạn concurrency, số lệnh/giây và tải Redis. Theo dõi số lượng chuyển đổi thành công/thất bại và chất lượng payload. Các lỗi không hợp lệ cần được xử lý theo policy thay vì âm thầm ghi default sai.

### Giai đoạn 4 — Xác minh dữ liệu mới

Đối chiếu các mẫu đại diện theo tenant/domain/schema, giá trị số, format thời gian, null, dữ liệu có dấu tiếng Việt, array rỗng, key hết hạn và các trường hợp trước đây không hợp lệ. Với data quan trọng, xác minh theo nguồn nghiệp vụ hoặc revision, không chỉ so sánh số lượng key.

### Giai đoạn 5 — Tắt hỗ trợ cũ

Khi không còn reader/writer v1, mức fallback giảm về ngưỡng được chấp nhận và toàn bộ dữ liệu cần giữ đã chuyển, ngừng đường đọc v1. Key v1 có TTL có thể hết hạn tự nhiên; với key dài hạn, cần quy trình xóa riêng đã được xác nhận đúng phạm vi.

### Giai đoạn 6 — Kết thúc và ghi lại hợp đồng

Ghi nhận schema v2, key version, serializer, TTL, owner, release nào đã cắt đường cũ và khả năng rollback còn lại. Loại bỏ các DTO/converter tạm thời sau khi hết thời hạn cần hỗ trợ; giữ lại tài liệu migration để người vận hành biết vì sao từng có key v1/v2.

## 20. Theo dõi migration bằng những tín hiệu gì?

Không chỉ theo dõi job “chạy xong”. Những chỉ số sau giúp quyết định có thể chuyển sang giai đoạn tiếp theo hay không:

| Tín hiệu | Ý nghĩa |
|---|---|
| Tỷ lệ đọc v2 thành công | Reader mới đã phục vụ bao nhiêu yêu cầu bằng schema mới |
| Tỷ lệ fallback v1 | Còn bao nhiêu request phụ thuộc dữ liệu cũ |
| Số key v1/v2 theo mẫu | Ước tính quy mô còn lại; cần hiểu SCAN và topology |
| Lỗi parse/validate theo schema | Dữ liệu không hợp lệ hoặc serializer mismatch |
| Số key hết hạn trong lúc migrate | Xác định hành vi TTL và cache miss |
| Số write conflict / bỏ qua vì v2 tồn tại | Giúp phát hiện cạnh tranh ghi hoặc idempotence |
| Latency p95/p99 của đường đọc | Read fallback/migration có làm chậm request không |
| CPU/network/memory Redis và tải nguồn | Migration có ảnh hưởng workload chính không |
| Số consumer/writer còn dùng v1 | Điều kiện thực tế để tắt đường cũ |

Không nên coi `DBSIZE` hoặc một `SCAN` trên một node là số lượng key của toàn Redis Cluster. Nếu cần kiểm kê toàn cụm, phải tổng hợp từ các primary theo topology tại thời điểm đo. Đối với cache có TTL, số lượng key thay đổi tự nhiên nên metric về **tỷ lệ fallback và lỗi** thường hữu ích hơn việc đòi tổng số key v1 chính xác tuyệt đối.

Trong log lỗi migration, chỉ lưu thông tin đủ để điều tra như schema version, exception category, key prefix đã rút gọn hoặc hash ID, correlation ID và thời điểm; tránh ghi payload chứa thông tin nhạy cảm hoặc token vào log.

## 21. Rollback phải được thiết kế trước khi ghi dữ liệu v2

Rollback ứng dụng về bản cũ không nhất thiết rollback được dữ liệu Redis. Ví dụ:

```text
Ứng dụng v1: chỉ hiểu JSON schema v1
Ứng dụng v2: ghi JSON schema v2 vào cùng key
Rollback app về v1: v1 đọc payload v2 -> lỗi
```

Để có khả năng rollback, có thể giữ v1 key riêng trong thời gian nhất định, duy trì dual-write có kiểm soát hoặc triển khai phiên bản bridge biết đọc v2. Mọi phương án có điều kiện: nếu writer mới đã tạo thông tin v2 không thể diễn đạt bằng schema v1, việc “ghi ngược” có thể mất dữ liệu.

Một ma trận rollback cần trả lời:

| Câu hỏi | Vì sao cần trả lời |
|---|---|
| Phiên bản cũ có đọc được v2 không? | Tránh rollback code nhưng vẫn lỗi deserialize |
| Sau cutover ai còn ghi v1? | Biết dữ liệu v1 có còn cập nhật hay đã cũ |
| Có mất thông tin khi v2 → v1 không? | Tránh biến rollback thành ghi đè mất dữ liệu |
| TTL có còn hợp lệ không? | Tránh khôi phục key đã phải hết hạn |
| Khi nào được xóa v1? | Giữ cửa sổ rollback đủ theo chính sách |
| Nếu Redis mất kết nối khi dual-write? | Cần cách đối soát và đồng bộ lại |

Với cache có thể dựng lại, rollback có thể dùng prefix v1 riêng và tái tạo cache theo writer cũ. Với dữ liệu nguồn sự thật, rollback dữ liệu cần một quy trình chuyển đổi và kiểm chứng chặt chẽ hơn.

## 22. Sai lầm thường gặp

**“Chỉ đổi tên field Java thì Redis tự hiểu schema mới.”**

Không. Redis lưu byte được writer cũ ghi. Jackson có thể hỗ trợ alias hoặc quy tắc deserialize riêng, nhưng không tự thay JSON đã lưu trong Redis.

**“JSON đọc được bằng `redis-cli` nghĩa là schema tương thích.”**

Không. JSON hợp cú pháp vẫn có thể thiếu field bắt buộc, sai đơn vị tiền, sai timezone hoặc chứa metadata kiểu Java không còn tồn tại.

**“Đổi `valueSerializer` của `RedisTemplate` là đủ để chuyển mọi cache.”**

Không. Spring Cache dùng `RedisCacheConfiguration`, Spring Session có cấu hình riêng và Redis Repository thường dùng hash mapping qua converter. Phải xác định thành phần đã tạo dữ liệu.

**“Có `@JsonIgnoreProperties(ignoreUnknown = true)` là tương thích mọi phiên bản.”**

Không. Bỏ qua field lạ không tạo ra những giá trị bắt buộc đang thiếu và có thể che giấu lỗi schema.

**“Đổi sang key v2 là xong migration.”**

Chưa đủ. Còn TTL, writer v1, dữ liệu v1 dài hạn, cache miss spike, index/key phụ và chiến lược rollback.

**“`setIfAbsent` bảo đảm luôn chọn dữ liệu mới nhất.”**

Không. Nó chỉ tránh ghi đè key đã tồn tại tại thời điểm lệnh chạy. Nếu v1 bị cập nhật sau khi v2 được tạo, v2 vẫn có thể stale.

**“Di trú từ `v1` sang `v2` trong Cluster có thể luôn dùng một Lua script.”**

Không. Atomic Lua đa key trong Redis Cluster đòi hỏi các key liên quan ở cùng slot. Key v1 và v2 tạo từ tên khác nhau có thể nằm ở các slot khác nhau.

**“Có thể xóa tất cả key v1 khi batch báo đã chạy hết.”**

Không nên. Cần biết batch có bỏ sót do thay đổi keyspace, có writer cũ còn hoạt động không, dữ liệu đã được xác minh chưa và cửa sổ rollback còn cần key v1 hay không.

## 23. Bài thực hành có kiểm soát

Trong môi trường Redis thử nghiệm, có thể tự tạo JSON v1 và v2 ở hai key khác nhau:

```bash
redis-cli SET shop:dev:catalog:product:v1:p42 \
  '{"id":"p42","name":"So tay","priceMinor":199000}' EX 300

redis-cli --raw GET shop:dev:catalog:product:v1:p42
redis-cli PTTL shop:dev:catalog:product:v1:p42
```

Sau khi chạy một lớp đọc tương thích tương tự ví dụ Java, quan sát:

```bash
redis-cli --raw GET shop:dev:catalog:product:v2:p42
redis-cli PTTL shop:dev:catalog:product:v2:p42
redis-cli TYPE shop:dev:catalog:product:v2:p42
```

Khi key v2 tồn tại, nó vẫn có Redis type là `string`, nhưng JSON có `schemaVersion: 2`, `displayName` và `money`. TTL v2 nên phản ánh chính sách đã định, thường gần thời hạn còn lại của v1 nếu đang giữ expiry.

Thực hành thêm ba tình huống:

1. Cho v1 thiếu `name` để thấy converter từ chối dữ liệu không hợp lệ.
2. Tạo v2 trước, sau đó chạy fallback v1 để thấy ghi có điều kiện không ghi đè v2.
3. Để v1 hết hạn, xác định reader trả cache miss và ứng dụng phải nạp dữ liệu từ nguồn chính.

Trong ứng dụng thật, không chạy migration kiểu thử nghiệm trên Redis production; cần giới hạn phạm vi và có chiến lược quan sát/rollback tương ứng.

## 24. Câu hỏi tự kiểm tra

1. Thêm một field bắt buộc vào JSON có khác gì thêm một field tùy chọn đối với reader cũ và reader mới?
2. Vì sao `@JsonAlias` hỗ trợ đọc dữ liệu cũ nhưng không tự thay JSON đang nằm trong Redis?
3. Khi nào nên đổi key prefix/schema version thay vì ghi đè payload cùng một key?
4. Lazy migration có thể tạo dữ liệu cũ hơn thực tế trong trường hợp writer v1 còn hoạt động như thế nào?
5. Vì sao `PTTL == -1` và `PTTL == -2` phải được xử lý khác nhau?
6. Nếu cache v1 có thể dựng lại từ database, tại sao không nhất thiết chuyển từng key v1?
7. Trong Redis Cluster, điều kiện nào cho phép chạy script atomic liên quan cả key v1 và v2?
8. Vì sao rollback ứng dụng về code cũ có thể thất bại dù code cũ hoàn toàn không đổi?
9. `RedisCacheManager`, `RedisTemplate` và `@RedisHash` có nhất thiết dùng chung serializer không?
10. Với dữ liệu tiền tệ cũ không ghi currency, cần căn cứ nào trước khi điền `currency` ở schema mới?

## 25. Kết luận

Trong Spring Data Redis, schema JSON và cách mã hóa byte là **hợp đồng lưu trữ giữa nhiều phiên bản ứng dụng**, không chỉ là chi tiết của một class Java. Khi cần đổi tên field, kiểu dữ liệu hoặc cấu trúc payload, hãy xác định reader/writer tương thích, chọn version trong payload hay tên key, quyết định cách di trú theo vòng đời dữ liệu và giữ đúng ý nghĩa TTL.

Với cache có thể tạo lại, đổi namespace và để dữ liệu cũ hết hạn thường đủ đơn giản. Với dữ liệu cần giữ, hãy dùng reader tương thích, phép chuyển đổi tường minh, batch/lazy migration có kiểm soát, xử lý ghi đồng thời và theo dõi các tín hiệu hoàn tất trước khi loại bỏ schema cũ. Một migration chỉ thực sự kết thúc khi mọi consumer dùng được định dạng mới, dữ liệu quan trọng đã được xác minh, quyền ghi cũ đã chấm dứt và kế hoạch rollback không còn phụ thuộc vào một giả định sai về byte trong Redis.
