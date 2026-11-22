# Di chuyển dữ liệu khi đổi namespace, serializer hoặc cấu trúc lưu

## 1. Bài toán: nâng cấp ứng dụng nhưng dữ liệu Redis vẫn tồn tại

Một ứng dụng Spring Boot sử dụng Spring Data Redis đã hoạt động trong thời gian dài. Phiên bản cũ có thể lưu hồ sơ khách hàng dưới dạng Java serialization với khóa:

```text
customer:42
```

Sau khi nâng cấp, nhóm phát triển muốn:

1. Đổi tên khóa thành namespace có phiên bản rõ ràng: `app:customer:profile:v2:42`.
2. Thay Java serialization bằng JSON để dễ quan sát và độc lập hơn với định nghĩa lớp Java.
3. Thay cách lưu từ một Redis String chứa object sang Redis Hash để chỉ cập nhật những trường cần thiết.

Nếu chỉ sửa code rồi triển khai:

```java
redisTemplate.opsForValue().get("app:customer:profile:v2:42");
```

ứng dụng mới có thể không tìm thấy dữ liệu cũ dù Redis vẫn chứa nhiều khóa phiên bản trước. Ngay cả khi tìm đúng khóa, serializer mới có thể không giải mã được những byte do serializer cũ tạo ra. Nếu đổi từ String sang Hash, lệnh `HGETALL` trên khóa kiểu String có thể báo `WRONGTYPE`.

Một hệ thống cần khả năng chạy liên tục còn phải xét:

- Một phần instance vẫn dùng code cũ trong lúc rolling deployment.
- Khóa có TTL và có thể hết hạn trong quá trình sao chép.
- Một người dùng cập nhật dữ liệu khi công việc backfill đang chạy.
- Redis có replica, Sentinel hoặc Cluster và có thể failover.
- Nhiều phiên bản application có thể đọc/ghi cùng lúc.
- Dữ liệu mới phải có phương án quay lại phiên bản cũ khi deployment thất bại.

**Di chuyển dữ liệu Redis là thay đổi giao thức lưu trữ giữa các phiên bản ứng dụng, không chỉ là đổi một chuỗi prefix.**

Bài học thuộc chương **Độ bền dữ liệu** trong **Spring Data Redis**. Trọng tâm là lập kế hoạch chuyển đổi giữa namespace, serializer và cấu trúc Redis sao cho có thể triển khai theo giai đoạn, quan sát được, bảo toàn đúng ngữ nghĩa và có khả năng khôi phục khi gặp lỗi.

## 2. Ba loại thay đổi cần phân biệt

### 2.1. Đổi namespace của khóa

Ví dụ trước và sau:

```text
Cũ: profile:42
Mới: app:profile:v2:42
```

Dữ liệu có thể vẫn là Redis String với cùng encoding, nhưng **đường tìm kiếm khóa** đã đổi.

Trong Spring Data Redis, key serializer quyết định tên khóa ở dạng byte. Vì thế ngay cả khi Java code gọi `"profile:42"`, dữ liệu Redis thực tế có thể mang byte JDK serialization nếu key serializer cũ không phải `StringRedisSerializer`.

**Lỗi điển hình:** chỉ thay prefix trong code khiến mọi lượt đọc trở thành miss. Nếu Redis là cache, app có thể tái tạo từ nguồn khác; nếu Redis lưu dữ liệu có thẩm quyền, người dùng có thể tưởng dữ liệu đã mất.

### 2.2. Đổi serializer

Cùng một logical object:

```json
{
  "id": 42,
  "displayName": "Lan",
  "level": 3
}
```

có thể được lưu thành những byte khác nhau:

```text
Java serialization -> binary stream với class metadata
JSON serialization -> UTF-8 JSON string
String serializer   -> byte UTF-8 của chuỗi
Custom binary codec -> định dạng riêng do ứng dụng quy định
```

Chỉ thay:

```java
template.setValueSerializer(...);
```

không tự chuyển đổi những value đã có trong Redis.

Nếu serializer cũ là JDK mà serializer mới là JSON, đọc bằng cấu hình mới có thể ném lỗi giải mã. Nếu key serializer cũng đổi, lệnh `GET` có thể không tìm đúng khóa.

Đối với thay đổi serializer, cần định nghĩa rõ **reader cũ**, **writer mới** và cách ánh xạ schema từ model cũ sang model mới.

### 2.3. Đổi cấu trúc dữ liệu

Ví dụ cũ lưu một String JSON:

```redis
SET app:profile:v1:42 "{\"displayName\":\"Lan\",\"level\":3}"
```

Phiên bản mới chuyển sang Hash:

```redis
HSET app:profile:v2:42 displayName "Lan" level "3"
```

Đây không chỉ là thay serializer. Kiểu dữ liệu Redis đã đổi:

| Redis type | Lệnh thường dùng | Đặc điểm |
|---|---|---|
| String | `GET`, `SET` | Một value nguyên khối, phù hợp blob/JSON |
| Hash | `HGET`, `HSET`, `HGETALL` | Nhiều field/value trong một key |
| List | `LPUSH`, `LRANGE` | Dữ liệu có thứ tự và thao tác theo hai đầu |
| Set | `SADD`, `SMEMBERS` | Tập các phần tử không trùng |
| Sorted Set | `ZADD`, `ZRANGE` | Phần tử kèm score |
| Stream | `XADD`, `XREADGROUP` | Bản ghi sự kiện, có ID và consumer group |

Không thể thay `GET` bằng `HGETALL` rồi kỳ vọng Redis tự hiểu rằng JSON cần được phân rã thành Hash. Khi truy cập sai kiểu, Redis có thể trả lỗi `WRONGTYPE`.

### 2.4. Ba thay đổi có thể xảy ra cùng lúc

Ví dụ:

```text
Version 1:
  key      = profile:42
  type     = String
  encoding = JDK Serializable object

Version 2:
  key      = app:profile:v2:42
  type     = Hash
  encoding = String fields UTF-8
```

Nếu đổi tất cả trong một deployment mà không có kế hoạch chuyển tiếp, rủi ro cao hơn nhiều so với việc đổi riêng một prefix.

## 3. Trước tiên: xác định Redis là cache hay nguồn dữ liệu có thẩm quyền

Cùng là Redis nhưng yêu cầu migration khác nhau đáng kể.

### 3.1. Redis chỉ là cache

Ví dụ dữ liệu nguồn nằm ở PostgreSQL:

```text
PostgreSQL (source of truth)
           |
           v
       Redis cache
           |
           v
      Spring API
```

Nếu có thể dựng lại toàn bộ cache từ PostgreSQL, cách triển khai đơn giản có thể là:

1. Phát hành namespace mới.
2. Cho phiên bản mới chỉ ghi cache mới.
3. Cho cache mới warm dần hoặc chủ động warm có giới hạn.
4. Duy trì khóa cũ trong thời gian rolling deployment.
5. Xóa khóa cũ sau khi mọi instance cũ dừng và dữ liệu cũ hết TTL.

Không nhất thiết phải copy từng khóa cache. Nhưng vẫn phải tính tới **cache stampede**: nếu hàng triệu khóa mới cùng miss, database có thể bị quá tải.

### 3.2. Redis chứa dữ liệu không thể tái tạo dễ dàng

Ví dụ:

- Counter được ghi duy nhất vào Redis.
- Dữ liệu phiên hoặc trạng thái workflow không có bản sao ở database.
- Queue, Stream, Sorted Set chứa công việc chưa xử lý.
- Trạng thái khóa, idempotency hoặc quyền thao tác có ý nghĩa nghiệp vụ.

Với loại này, “đổi namespace và để tự nạp lại” có thể làm mất dữ liệu thực sự.

Cần:

- Kiểm kê cấu trúc và trạng thái.
- Xác định nguồn có thẩm quyền và cơ chế khôi phục.
- Đảm bảo không bỏ sót write phát sinh trong khi migration.
- Duy trì tính tăng đơn điệu của counter và các trạng thái cạnh tranh.
- Không tái tạo trạng thái xử lý bằng cách chỉ copy payload nếu metadata quan trọng nằm ở Redis.

**Không áp dụng quy trình cache disposable cho dữ liệu durable chỉ vì cả hai đều được lưu trong Redis.**

## 4. Lập bản kiểm kê trước khi đổi schema

Tài liệu migration nên mô tả cả **logic** lẫn **dạng byte thực tế**.

| Hạng mục | Ví dụ cần xác định |
|---|---|
| Tập khóa cũ | `profile:*` |
| Tập khóa mới | `app:profile:v2:*` |
| Key serializer | String UTF-8 hay JDK binary |
| Value serializer | JDK, JSON, String, custom |
| Redis type | String, Hash, Set, Stream... |
| Schema cũ | Các field, kiểu, giá trị tùy chọn |
| Schema mới | Field đổi tên, enum, default |
| TTL | Có hạn, không hạn, hết hạn theo thời điểm nào |
| Nguồn dữ liệu | Database, Redis chính, event log |
| Các writer | API, job, listener, consumer |
| Các reader | Web, batch, cron, service khác |
| Độ chính xác | Có được đọc dữ liệu cũ không |
| Retention | Khi nào được xóa dữ liệu cũ |
| Topology | Standalone, Sentinel, Cluster |
| Khả năng rollback | Code cũ đọc được dữ liệu nào |
| Backup và restore | Có được kiểm chứng khôi phục không |

Một điểm dễ bị bỏ sót là **writer ngoài luồng HTTP**: scheduled job, consumer group, script Lua, service nội bộ hoặc ứng dụng còn chạy phiên bản cũ. Chúng vẫn có thể ghi lại dữ liệu theo schema cũ sau khi API chính đã chuyển đổi.

### 4.1. Nhìn kiểu dữ liệu thật trong Redis

Với khóa đã biết:

```redis
TYPE profile:42
PTTL profile:42
```

`TYPE` cho biết Redis data type hiện tại. `PTTL` cho biết TTL còn lại tính bằng mili giây.

Ví dụ:

```text
TYPE => string
PTTL => 29500
```

Không nên trực tiếp `GET` mọi khóa rồi in ra log, vì nội dung có thể lớn hoặc nhạy cảm.

### 4.2. Key serializer cũng là schema

Hai thao tác Java sau có thể tạo **hai khóa vật lý khác nhau** dù cùng logical key:

```java
stringRedisTemplate.opsForValue().set("profile:42", "...");
```

và:

```java
redisTemplateWithJdkKeySerializer.opsForValue()
        .set("profile:42", someValue);
```

Một bên lưu byte UTF-8; bên kia có thể lưu byte serialized của một Java String. `SCAN MATCH profile:*` từ Redis CLI chỉ khớp tiền tố byte phù hợp và có thể **không thấy** khóa binary mà ứng dụng gọi là `"profile:42"`.

Vì vậy, kiểm kê phải dựa trên serializer thực tế của phiên bản cũ, không chỉ dựa vào chuỗi key trong mã nguồn.

## 5. Các chiến lược migration phổ biến

### 5.1. Big-bang: chuyển đổi trong một lần dừng ghi

```text
Tạm dừng writers
      |
      v
Đọc toàn bộ dữ liệu cũ
      |
      v
Chuyển đổi + ghi dữ liệu mới
      |
      v
Đối soát
      |
      v
Đổi code đồng loạt
      |
      v
Mở lại writers
```

Ưu điểm:

- Ít race với dữ liệu đang thay đổi.
- Dễ xác định mốc snapshot nếu hệ thống có khả năng khóa/đóng băng ghi thực sự.
- Quy trình reasoning đơn giản hơn.

Nhược điểm:

- Có downtime hoặc thời gian hạn chế chức năng ghi.
- Dữ liệu lớn có thể khiến thời gian maintenance khó dự đoán.
- Nếu bước chuyển đổi thất bại giữa chừng, cần rollback hoặc chạy lại idempotent.

Phù hợp với tập dữ liệu vừa, nghiệp vụ chấp nhận maintenance window hoặc hệ thống có cách tạm dừng hoàn toàn mọi writer.

### 5.2. Lazy migration: chuyển đổi khi đọc

```text
App v2 nhận GET
      |
      v
Đọc key v2
      |
    +-----+
    |     |
   Hit   Miss
    |     |
    v     v
  Return  Đọc key v1
                 |
          +------+------+
          |             |
         Hit           Miss
          |             |
          v             v
      Chuyển đổi      Not found /
      sang v2          đọc nguồn
          |
          v
      Ghi key v2
          |
          v
      Trả dữ liệu
```

Ưu điểm:

- Chi phí chuyển đổi trải đều theo traffic.
- Các khóa ít được đọc không gây tải backfill ngay.
- Có thể triển khai dần.

Nhược điểm:

- Một số khóa không bao giờ được đọc sẽ không được chuyển.
- Lần đọc đầu có thêm độ trễ.
- Có thể xảy ra race giữa đọc key cũ và ghi key mới.
- Nếu cả hai thế hệ writer còn hoạt động, dữ liệu có thể lệch.

Lazy migration phù hợp với cache hoặc dữ liệu có thể đối soát. Đối với dữ liệu durable cần chuyển toàn bộ, thường phải kết hợp **backfill**.

### 5.3. Backfill theo batch và cutover

```text
Giai đoạn 1: Deploy code có thể đọc cả v1 và v2
Giai đoạn 2: Bắt đầu ghi dữ liệu v2 theo chính sách
Giai đoạn 3: Quét v1, chuyển từng batch sang v2
Giai đoạn 4: Đối soát và shadow-read
Giai đoạn 5: Chuyển đọc chính thức sang v2
Giai đoạn 6: Duy trì khả năng rollback
Giai đoạn 7: Ngừng hỗ trợ v1 và dọn dữ liệu cũ
```

Đây là chiến lược **expand → migrate → contract**: trước tiên mở rộng tương thích, sau đó chuyển dữ liệu, cuối cùng mới loại bỏ đường cũ.

### 5.4. Dual-write và dual-read

Khi ứng dụng phải vận hành liên tục, có thể duy trì cả hai đường ghi trong một giai đoạn:

```text
Write business data
          |
      +---+---+
      |       |
      v       v
   Write v1  Write v2
```

Nhưng **hai lệnh Redis độc lập không tự có transaction xuyên mọi topology**, nhất là khi key nằm ở hai hash slot khác nhau trong Redis Cluster. Có thể ghi v1 thành công và v2 thất bại.

Nếu dữ liệu nằm trong database có thẩm quyền, ưu tiên ghi business data vào database rồi xây lại cache theo quy tắc rõ ràng. Nếu Redis là nguồn dữ liệu chính, cần version/atomicity/idempotency hoặc một log sự kiện bền vững thích hợp; không coi dual-write là bảo đảm dữ liệu đã nhất quán.

## 6. Thiết kế key namespace có khả năng tiến hóa

Một tên khóa nên chứa đủ ngữ cảnh mà không biến thành một chuỗi khó quản lý.

Ví dụ:

```text
svc:catalog:product:v2:42
```

Có thể đọc thành:

- `svc`: nhóm ứng dụng.
- `catalog`: miền nghiệp vụ.
- `product`: loại dữ liệu.
- `v2`: phiên bản schema hoặc cách lưu.
- `42`: logical identifier.

Nếu dữ liệu phụ thuộc tenant:

```text
tenant:acme:catalog:product:v2:42
tenant:other:catalog:product:v2:42
```

Nếu bỏ tenant trong key có thể tạo lỗi chia sẻ dữ liệu ngoài phạm vi quyền.

### 6.1. Đừng trộn nhiều kiểu Redis dưới cùng một key

Không nên để code cũ dùng:

```redis
SET profile:42 "{\"name\":\"Lan\"}"
```

trong lúc code mới dùng:

```redis
HSET profile:42 name "Lan"
```

Nếu `profile:42` đang là String, `HSET` trả `WRONGTYPE`. Nếu xóa String rồi tạo Hash tại cùng tên, reader cũ có thể lỗi ngay.

Dùng **key mới tách biệt**:

```text
profile:v1:42  -> Redis String
profile:v2:42  -> Redis Hash
```

cho phép hai phiên bản ứng dụng cùng chạy trong giai đoạn chuyển tiếp.

### 6.2. Version trong key khác với version của dữ liệu

Ví dụ:

```text
Key schema version: profile:v2:42
Data revision:      revision=187
```

`v2` biểu thị **giao thức lưu trữ**. `revision=187` biểu thị **phiên bản nội dung** và có thể dùng để giải quyết cạnh tranh cập nhật.

Không dùng `v2` như một cơ chế bảo đảm rằng payload đã mới hơn mọi bản ở namespace `v1`.

### 6.3. Lưu ý Redis Cluster hash slots

Redis Cluster gán mỗi key cho một hash slot. Nếu muốn chạy Lua script trên cả key cũ và mới, hai key phải thuộc cùng hash slot.

Có thể đặt cùng hash tag:

```text
profile:{42}:v1
profile:{42}:v2
```

Redis tính slot từ phần nằm trong `{42}`, nên hai khóa này có cùng slot.

Ví dụ:

```redis
CLUSTER KEYSLOT profile:{42}:v1
CLUSTER KEYSLOT profile:{42}:v2
```

Nếu cấu trúc key v1 ban đầu không có hash tag, không thể tự giả định có thể thực thi một Lua script gồm cả key v1 và key v2 trên Redis Cluster. **CROSSSLOT** là lỗi thường gặp khi chuyển namespace kèm atomic operation.

Không ép mọi key vào cùng một hash tag cố định cho toàn hệ thống, vì như vậy có thể gây dồn tải vào một slot.

## 7. Serializer trong Spring Data Redis phải được quản lý tường minh

### 7.1. Cấu hình key và value độc lập

`RedisTemplate` dùng các serializer cho key, value và có thể hash key/hash value.

Ví dụ một template JSON cho Redis String:

```java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProfileRedisConfig {

    @Bean("profileV2Template")
    public RedisTemplate<String, ProfileV2> profileV2Template(
            RedisConnectionFactory factory) {

        RedisTemplate<String, ProfileV2> template =
                new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(
                new StringRedisSerializer()
        );
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        ProfileV2.class
                )
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

Ở đây:

- Key được lưu ở dạng String UTF-8.
- Value được serialize thành JSON cho `ProfileV2`.
- Không có cơ chế tự chuyển dữ liệu của template cũ.
- Nếu sau này muốn đổi sang Hash, code phải thay cả API truy cập dữ liệu và hash serializers phù hợp.

Spring Data Redis có nhiều serializer và chi tiết constructor có thể thay đổi giữa các phiên bản; cần dùng cấu hình tương ứng phiên bản Spring Data Redis/Jackson mà ứng dụng sử dụng.

### 7.2. Vì sao Java native serialization cần thận trọng?

Java serialization lưu các thông tin phụ thuộc lớp Java và cơ chế tuần tự hóa của JVM. Một số vấn đề khi nâng cấp:

- Thay package/class name khiến giải mã khó hoặc thất bại.
- Thay cấu trúc object có thể gây không tương thích.
- Payload khó quan sát bằng redis-cli.
- Không nên deserialize dữ liệu JDK từ nguồn không đáng tin; native Java deserialization có bề mặt tấn công đáng lưu ý.

Một migration hợp lệ có thể dùng **reader JDK cũ** chỉ để đọc dữ liệu do chính hệ thống tạo ra, hạn chế quyền truy cập và tắt đường cũ sau khi hoàn tất. JSON có schema rõ ràng giúp dễ tiến hóa hơn, nhưng vẫn cần versioning, kiểm tra dữ liệu đầu vào và bảo mật.

### 7.3. Đổi hash serializer cũng là thay định dạng

Nếu dữ liệu cũ lưu Hash:

```redis
HSET profile:42 name "Lan" points "20"
```

nhưng Java dùng JDK serializer cho **hash field names**, một ứng dụng khác dùng `StringRedisSerializer` có thể không tìm được field `name` dù Redis key tồn tại.

Cần kiểm kê đủ:

```text
keySerializer
valueSerializer
hashKeySerializer
hashValueSerializer
```

Không chỉ kiểm tra value serializer của String.

## 8. Ví dụ chuyển dữ liệu từ JDK serialization sang JSON

Giả sử ứng dụng cũ sử dụng:

```text
Key:       profile:v1:42
Redis type: String
Key bytes: UTF-8
Value:     JDK-serialized LegacyProfile
```

Ứng dụng mới muốn:

```text
Key:       profile:v2:42
Redis type: String
Key bytes: UTF-8
Value:     JSON ProfileV2
```

### 8.1. Model cũ và model mới

```java
package com.example.migration;

import java.io.Serializable;

public record LegacyProfile(
        String displayName,
        int points
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

Model mới:

```java
package com.example.migration;

public record ProfileV2(
        long id,
        String displayName,
        int loyaltyPoints,
        int schemaVersion
) {
}
```

Đây là một ví dụ minh họa. Với dữ liệu JDK serialization thực tế, phải giữ được tương thích với lớp/serialVersionUID đã dùng khi ghi dữ liệu cũ; việc chỉ tạo lớp mới tên giống nhau không bảo đảm đọc được byte đã lưu.

### 8.2. Hai template với serializer khác nhau

```java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class LegacyProfileTemplateConfig {

    @Bean("legacyProfileTemplate")
    public RedisTemplate<String, LegacyProfile> legacyProfileTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, LegacyProfile> template =
                new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new JdkSerializationRedisSerializer()
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

Reader mới dùng `profileV2Template` với `Jackson2JsonRedisSerializer<ProfileV2>` ở phần trước.

**Điều kiện giả định:** key serializer của phiên bản cũ là UTF-8 String. Nếu hệ thống cũ dùng JDK serializer cho key, phải cấu hình reader old-key giống hệt; không thể âm thầm chuyển key serializer trong ví dụ và vẫn kỳ vọng đọc được dữ liệu cũ.

### 8.3. Lazy migration một khóa

Dịch vụ dưới đây:

1. Ưu tiên đọc key v2.
2. Nếu v2 không tồn tại, đọc key v1 bằng serializer cũ.
3. Chuyển model cũ sang model mới.
4. Giữ TTL còn lại ở thời điểm di chuyển, không tự reset.
5. Chỉ tạo key v2 **nếu chưa có**, tránh ghi đè trực tiếp một key mới do tiến trình khác tạo trước.

```java
package com.example.migration;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProfileLazyMigrationService {

    private final RedisTemplate<String, LegacyProfile> oldTemplate;
    private final RedisTemplate<String, ProfileV2> newTemplate;

    public ProfileLazyMigrationService(
            @Qualifier("legacyProfileTemplate")
            RedisTemplate<String, LegacyProfile> oldTemplate,
            @Qualifier("profileV2Template")
            RedisTemplate<String, ProfileV2> newTemplate) {

        this.oldTemplate = oldTemplate;
        this.newTemplate = newTemplate;
    }

    public Optional<ProfileV2> find(long id) {

        String oldKey = "profile:v1:" + id;
        String newKey = "profile:v2:" + id;

        // 1. Read new first.
        ProfileV2 current = newTemplate.opsForValue().get(newKey);
        if (current != null) {
            return Optional.of(current);
        }

        // 2. Fall back to the legacy serializer.
        LegacyProfile legacy = oldTemplate.opsForValue().get(oldKey);
        if (legacy == null) {
            return Optional.empty();
        }

        // 3. Check the source key's remaining TTL.
        Long ttlMillis = oldTemplate.getExpire(
                oldKey,
                TimeUnit.MILLISECONDS
        );

        // The key might have disappeared between GET and PTTL.
        if (ttlMillis == null || ttlMillis == -2 || ttlMillis == 0) {
            return Optional.empty();
        }

        ProfileV2 converted = new ProfileV2(
                id,
                legacy.displayName(),
                legacy.points(),
                2
        );

        Boolean inserted;

        if (ttlMillis == -1) {
            // Explicit temporary policy for legacy values with no TTL.
            // In a real system choose a documented retention policy.
            inserted = newTemplate.opsForValue().setIfAbsent(
                    newKey,
                    converted,
                    Duration.ofMinutes(5)
            );
        } else {
            inserted = newTemplate.opsForValue().setIfAbsent(
                    newKey,
                    converted,
                    Duration.ofMillis(ttlMillis)
            );
        }

        // If another request populated the new key first, prefer it.
        ProfileV2 latest = newTemplate.opsForValue().get(newKey);
        if (latest != null) {
            return Optional.of(latest);
        }

        // The newly inserted key could already have expired.
        // Do not treat this best-effort migration as strong consistency.
        return Optional.empty();
    }
}
```

Lưu ý:

- `getExpire` với đơn vị milliseconds có thể trả giá trị `-1` khi khóa tồn tại mà không có TTL và `-2` khi khóa không tồn tại.
- Nếu khóa không có TTL, ví dụ áp dụng **quy tắc mới 5 phút**; đây là một quyết định chính sách, **không phải bảo toàn TTL nguyên vẹn**.
- `setIfAbsent` tránh ghi đè một key mới **đang tồn tại**, nhưng không giải quyết mọi race với các writer đang thay đổi cả v1 và v2.
- Nếu key v2 tồn tại nhưng dữ liệu không giải mã được, quá trình đọc cần báo lỗi, cách ly hoặc xử lý theo chính sách. Không nên coi mọi lỗi deserialize là cache miss rồi tự ghi lại dữ liệu cũ.
- Phương thức trả `Optional.empty()` khi key biến mất giữa các bước; ứng dụng có thể truy vấn nguồn có thẩm quyền hoặc retry có giới hạn. Không nên tự coi đó là “khách hàng không tồn tại” nếu Redis chỉ là cache.
- Đoạn code là **lazy migration best-effort**, không phải giải pháp nhất quán mạnh với ghi đồng thời.

### 8.4. Vì sao không gọi SET trực tiếp?

Ví dụ rủi ro:

```text
T0: Migration đọc profile v1: points=10.
T1: Ứng dụng mới cập nhật profile v2: points=20.
T2: Migration gọi SET profile:v2:42 points=10.
```

Nếu dùng `SET` không điều kiện, migration có thể **ghi đè dữ liệu mới**.

Dùng `SET ... NX` hoặc `setIfAbsent` ngăn một dạng overwrite khi target đã tồn tại, nhưng vẫn phải đối phó với các trường hợp:

- Một writer xóa target để invalidation, sau đó migration nạp lại bản cũ.
- Writer cũ vẫn tiếp tục cập nhật namespace v1.
- Việc tạo target và cập nhật dữ liệu mới xảy ra theo thứ tự không mong muốn.
- Migration đọc object từ một nguồn đã bị thay đổi sau lúc GET.
- Target đã được tạo nhưng sau đó bị cập nhật/xóa trước khi request đọc lại.

Với dữ liệu có thẩm quyền, phải kết hợp revision/version, một transaction ở nguồn authoritative hoặc giao thức cutover ngăn writer cũ tiếp tục ghi sai phiên bản.

## 9. Chuyển từ Redis String sang Hash

Giả sử v1:

```redis
SET cart:v1:42 "{\"userId\":42,\"status\":\"OPEN\",\"items\":3}"
```

V2:

```redis
HSET cart:v2:42 userId "42" status "OPEN" items "3"
```

Ở đây, `cart:v1:42` và `cart:v2:42` khác key, nên hai kiểu dữ liệu có thể cùng tồn tại.

### 9.1. Đọc String JSON bằng Spring

```java
String json = stringRedisTemplate
        .opsForValue()
        .get("cart:v1:42");
```

Giải mã với Jackson (ví dụ):

```java
CartV1 cart = objectMapper.readValue(json, CartV1.class);
```

Model minh họa:

```java
public record CartV1(
        long userId,
        String status,
        int items
) {
}
```

### 9.2. Ghi sang Hash

```java
Map<String, String> fields = Map.of(
        "userId", Long.toString(cart.userId()),
        "status", cart.status(),
        "items", Integer.toString(cart.items())
);

stringRedisTemplate.opsForHash()
        .putAll("cart:v2:42", fields);
```

Đọc sau chuyển đổi:

```java
Map<Object, Object> migrated =
        stringRedisTemplate.opsForHash()
                .entries("cart:v2:42");
```

Nếu Hash fields thay đổi kiểu theo thời gian, code phải định nghĩa cách parse: `items` là số nguyên hợp lệ, `status` thuộc enum nào, field thiếu có được mặc định hay phải từ chối.

### 9.3. HSET không giữ TTL theo cách người đọc thường mong đợi

Redis TTL gắn với **key**, không gắn với từng field của Hash trong mô hình cơ bản. Với một target key Hash **mới tạo**, ghi bằng `HSET`/`putAll` **không tự lấy TTL từ String nguồn**.

Cần chủ động đặt:

```java
stringRedisTemplate.expire(
        "cart:v2:42",
        Duration.ofMinutes(10)
);
```

Tuy nhiên, việc `putAll` rồi `expire` là **hai thao tác**. Nếu tiến trình crash giữa hai thao tác, key v2 có thể tồn tại không TTL.

Các phương án chặt chẽ hơn:

- Sử dụng `MULTI/EXEC` hoặc Lua script để ghi fields và TTL nguyên tử **khi mọi key cần tham gia nằm trong cùng slot** và các thao tác được phép.
- Dùng cấu trúc dữ liệu versioned để tránh ghi đè dữ liệu đang thay đổi.
- Có tác vụ quét/đối soát kiểm tra những key v2 không có TTL đúng kỳ vọng.
- Nếu Redis chỉ là cache, chấp nhận dọn lại một key khi gặp dữ liệu bất thường.

### 9.4. Khi nào Hash có lợi hơn JSON String?

Redis Hash cho phép thao tác theo field:

```redis
HGET cart:v2:42 status
HSET cart:v2:42 status CHECKED_OUT
```

Nhưng nó cũng có các đánh đổi:

- Cần quản lý field name và field-value serializer.
- Các object lồng nhau vẫn cần chiến lược biểu diễn.
- Việc đọc toàn bộ object có thể vẫn tốn nhiều byte.
- Mỗi cập nhật field phải duy trì quy tắc schema và revision.
- Chuyển `String` sang `Hash` không tự động tốt hơn về bộ nhớ hoặc tốc độ trong mọi workload.

Quyết định phải dựa trên cách đọc/ghi thực tế, không chỉ vì Hash có nhiều lệnh.

## 10. Bảo toàn TTL khi di chuyển

### 10.1. PTTL có những kết quả đặc biệt

```redis
PTTL profile:v1:42
```

| Kết quả | Ý nghĩa |
|---|---|
| Số dương | Mili giây còn lại |
| `-1` | Key tồn tại nhưng không có TTL |
| `-2` | Key không tồn tại |
| `0` | Có thể xuất hiện ở thời điểm rất sát hết hạn |

Khi migration, không nên ép mọi giá trị thành `Duration.ofMillis(ttl)`; `-1` và `-2` có ý nghĩa khác nhau.

### 10.2. Lỗi reset TTL khi copy

Ví dụ:

```text
Old key:
  TTL còn 17 giây

Migration:
  SET newKey value EX 3600
```

Bản dữ liệu đáng lẽ hết hạn trong 17 giây bỗng tồn tại **thêm một giờ**. Với session, quyền truy cập, token hoặc khóa nghiệp vụ, đây có thể là lỗi nghiêm trọng.

Đối với cache có TTL, nên giữ **thời điểm hết hạn dự kiến** hoặc dùng chính sách mới được phê duyệt, không vô tình reset.

### 10.3. PTTL rồi SET vẫn có race

Trình tự:

```text
T0: PTTL oldKey => 17.000 ms
T1: App xử lý, mạng trễ 3 giây
T2: SET newKey PX 17.000
```

Key mới có thể hết hạn muộn hơn nguồn khoảng 3 giây.

Ngoài ra, nguồn có thể bị xóa hoặc cập nhật giữa `GET`, `PTTL` và `SET`:

```text
GET old value
  |
PTTL old
  |
[old bị DEL]
  |
SET new value
```

**Không coi GET + PTTL + SET là một transaction.**

### 10.4. Dùng thời điểm hết hạn tuyệt đối khi phù hợp

Redis có lệnh:

```redis
PEXPIRETIME profile:v1:42
```

Với phiên bản Redis hỗ trợ, lệnh trả thời điểm hết hạn Unix epoch tính bằng mili giây (hoặc giá trị đặc biệt với key không có hạn/không tồn tại). Khi thực hiện migration, giữ deadline tuyệt đối có thể tránh kéo dài TTL do xử lý chậm.

Một cách biểu diễn:

```text
Source expireAt = T
Target expireAt = T
```

Nhưng **đọc deadline và ghi target vẫn có race** với cập nhật/xóa nguồn nếu không có cơ chế đồng bộ. Cần kiểm tra thời điểm hiện tại, trạng thái phiên bản và nguyên tắc xử lý khi nguồn hết hạn giữa chừng.

### 10.5. COPY, RENAME và TTL

Các lệnh Redis như `COPY` hoặc `RENAME` có thể hữu ích khi chỉ cần di chuyển/nhân bản **đúng kiểu dữ liệu và byte hiện có**.

Ví dụ:

```redis
RENAME profile:v1:42 profile:v2:42
```

`RENAME` đổi tên key và giữ dữ liệu/TTL của key, nhưng **ghi đè key đích nếu đã tồn tại**. Đây có thể là hành động mất dữ liệu nếu target đang chứa bản mới hơn.

Nếu muốn tránh overwrite:

```redis
RENAMENX profile:v1:42 profile:v2:42
```

`RENAMENX` chỉ đổi tên nếu đích chưa tồn tại. Tuy nhiên nó **di chuyển**, không giữ source key cho rolling deployment hoặc rollback.

Một bản sao không xóa nguồn:

```redis
COPY profile:v1:42 profile:v2:42
```

`COPY` không thay serializer hoặc Redis type. Nó chỉ sao chép dữ liệu; vẫn phải kiểm tra chính sách TTL và version/đích khi tích hợp vào luồng migration.

Trong Redis Cluster, các thao tác nhiều key như `RENAME`/`COPY` thông thường yêu cầu các key cùng hash slot. Không mặc định chúng có thể chuyển key giữa hai slot tùy ý.

**Đổi serializer hoặc String ↔ Hash không được giải quyết bằng RENAME/COPY.** Chúng chỉ hữu ích khi dữ liệu gốc vẫn dùng được nguyên dạng.

## 11. Quét nhiều key: dùng SCAN, không KEYS trên production

Một migration hàng trăm nghìn key cần một cơ chế duyệt keyspace có kiểm soát.

### 11.1. KEYS dễ gây áp lực lớn

Ví dụ:

```redis
KEYS profile:v1:*
```

`KEYS` duyệt toàn bộ keyspace theo cách có thể khiến Redis bận xử lý. Không nên dùng với tập khóa lớn trên production chỉ để lấy danh sách migration.

### 11.2. SCAN trả từng lô

Ví dụ:

```redis
SCAN 0 MATCH profile:v1:* COUNT 500
```

Redis trả một **cursor mới** và một danh sách key trong lượt quét. Tiếp tục dùng cursor đó cho tới khi cursor về `0`.

Ví dụ cách suy nghĩ:

```text
SCAN cursor=0
    |
    +--> cursor=1048, 120 keys
    |
SCAN cursor=1048
    |
    +--> cursor=200, 80 keys
    |
SCAN cursor=200
    |
    +--> cursor=0, 110 keys
```

`COUNT 500` chỉ là **gợi ý mức công việc** cho Redis, không phải bảo đảm mỗi lần trả đúng 500 key.

Các đặc tính quan trọng của SCAN:

- Có thể trả key trùng trong một lượt quét.
- Có thể trả danh sách rỗng dù cursor chưa về `0`.
- Không phải snapshot nguyên tử toàn keyspace.
- Key được tạo hoặc xóa trong lúc quét có thể khiến kết quả không phản ánh một thời điểm duy nhất.
- Phải thiết kế migration **idempotent** để xử lý key lặp.
- Đừng cho mỗi key được quét tạo vô hạn request cùng lúc.

### 11.3. Spring Data Redis scan

Với key serializer String:

```java
package com.example.migration;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProfileKeyScanner {

    private final StringRedisTemplate redis;

    public ProfileKeyScanner(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void scanOldKeys() {

        ScanOptions options = ScanOptions.scanOptions()
                .match("profile:v1:*")
                .count(500)
                .build();

        try (Cursor<String> cursor = redis.scan(options)) {

            while (cursor.hasNext()) {
                String oldKey = cursor.next();

                // Gọi migration idempotent có rate limit riêng.
                // Không tự DELETE nguồn ở đây.
                System.out.println(oldKey);
            }
        }
    }
}
```

Đây là ví dụ cho thấy cách duyệt. Trong hệ thống thật không in mọi tên key nhạy cảm ra stdout. Worker nên ghi metric tiến độ và log lấy mẫu.

**Redis Cluster:** các node có những phân vùng keyspace khác nhau. Cần dùng cơ chế scan cluster-aware đã được kiểm chứng của client/thư viện hoặc quét riêng từng primary, không kết luận một `SCAN` tại một endpoint đã bao phủ tất cả slot. Nếu topology đổi trong lúc chạy, cần tính tới việc quét bù.

### 11.4. Xử lý cursor, checkpoint và chạy lại

Một quy trình backfill cần lưu tiến độ:

```text
migrationRunId
namespaceVersion
scanTarget / node
cursor / phạm vi
processedCount
convertedCount
skippedCount
failedCount
lastCheckpointTime
```

Vì SCAN không phải snapshot và cursor phụ thuộc trạng thái duyệt, checkpoint cursor không thay thế idempotency. Sau sự cố hoặc chuyển topology, một cách an toàn thường là chạy lại scan theo chính sách và **bỏ qua các key đã có target hợp lệ**.

Không xóa source ngay sau khi đã scan qua một lần. Cần đối soát riêng rằng dữ liệu mới có thể được đọc và các writer cũ không còn tạo dữ liệu chưa chuyển.

## 12. Chuyển đổi khi có ghi đồng thời

Đây là phần quan trọng nhất đối với dữ liệu không thể tái tạo.

### 12.1. Race: backfill ghi đè dữ liệu mới

```text
T0: Backfill đọc v1, revision=10.
T1: API cập nhật v2, revision=11.
T2: Backfill ghi v2 từ revision=10.
```

Kết quả: v2 trở về revision cũ nếu backfill dùng `SET` không điều kiện.

Giải pháp không chỉ là “chạy SCAN nhanh hơn”, mà là thiết kế điều kiện cập nhật:

- Target chỉ được tạo khi chưa có (`SET NX`) trong trường hợp phù hợp.
- Hoặc target được cập nhật **chỉ khi revision nguồn mới hơn revision target**.
- Việc so sánh revision và ghi phải **nguyên tử**.
- Revision phải do một nguồn có thẩm quyền cấp và không quay ngược.
- Nếu có delete/update, tombstone hoặc delete marker cũng phải tham gia so sánh phiên bản.

### 12.2. Race: writer cũ làm v1 mới hơn v2

```text
T0: Backfill copy v1(revision=10) sang v2.
T1: Một instance phiên bản cũ cập nhật v1(revision=11).
T2: App mới chỉ đọc v2(revision=10).
```

V2 hiện đã stale. `SET NX` không giải quyết tình huống **target đã có nhưng dữ liệu nguồn tiếp tục thay đổi**.

Các cách xử lý:

1. Trong giai đoạn chuyển tiếp, mọi writer phải cập nhật đường canonical và phát thay đổi theo hợp đồng.
2. Nếu dual-write, đảm bảo có cơ chế retry/đối soát khi một nhánh ghi lỗi.
3. Chặn các writer cũ còn hoạt động trước thời điểm cutover cuối.
4. Có mốc revision/sequence và bước catch-up chuyển những write phát sinh trong lúc backfill.
5. Sau cutover, khóa hoặc loại bỏ đường ghi v1 để không xuất hiện “writer ma”.

### 12.3. Race: xóa dữ liệu và resurrect

```text
T0: Backfill đọc profile v1:42.
T1: Người dùng xóa hồ sơ ở nguồn canonical.
T2: Hệ thống xóa profile v2:42.
T3: Backfill ghi lại profile v2:42 từ snapshot cũ.
```

Dữ liệu đã xóa bị **hồi sinh**.

Cần:

- Một versioned delete marker/tombstone.
- Hoặc nguồn có thẩm quyền được kiểm tra lại trong transaction/cơ chế đồng bộ phù hợp.
- Hoặc giai đoạn dừng ghi cho migration.
- Không dùng `setIfAbsent` đơn thuần nếu deletion có ý nghĩa nghiệp vụ và source cũ có thể còn tồn tại.

### 12.4. Lựa chọn theo mức nhất quán yêu cầu

| Mức yêu cầu | Cách tiếp cận |
|---|---|
| Cache có thể dựng lại | Namespace mới + TTL, lazy warm, không cần copy từng key |
| Cache có giá trị nhưng chấp nhận stale | Dual-read + backfill throttled + TTL + đối soát |
| Dữ liệu Redis duy nhất, cho phép maintenance | Dừng writer → snapshot/convert → đối soát → cutover |
| Dữ liệu duy nhất, phải zero-downtime | Revision/CDC hoặc event log + backfill + catch-up + write barrier |
| Dữ liệu cần nhất quán rất mạnh | Thiết kế nguồn authoritative/transaction/coordinator phù hợp; không chỉ dùng `SCAN` + `SET` |

## 13. Kiểm soát thay đổi bằng feature flags

Không nên gắn mọi giai đoạn migration vào một thay đổi code không thể điều chỉnh.

Một số cờ chuyển đổi hữu ích:

```text
profile.readPolicy = OLD_ONLY | NEW_THEN_OLD | NEW_ONLY
profile.writePolicy = OLD_ONLY | DUAL | NEW_ONLY
profile.backfillEnabled = true/false
profile.shadowCompareEnabled = true/false
profile.deleteLegacyEnabled = false
```

Ví dụ luồng tương thích:

```text
          API đọc
            |
       readPolicy?
            |
   +--------+----------+
   |        |          |
OLD_ONLY NEW_THEN_OLD NEW_ONLY
   |        |          |
   v        v          v
   v1      v2          v2
           |             |
          miss           |
           |             |
           v             v
           v1         return/error
```

**Không nên bật `NEW_ONLY` khi còn writer cũ duy nhất chỉ ghi v1**, vì những cập nhật đó sẽ không xuất hiện ở đường đọc mới.

Feature flags cần có kế hoạch thay đổi có kiểm soát: ai được bật, thứ tự bật, metric nào phải đạt và thời điểm có thể rollback.

### 13.1. Quy trình chuyển đổi có thể lặp lại

Một ví dụ điển hình cho dữ liệu bền vững:

| Giai đoạn | Readers | Writers | Backfill | Dọn v1 |
|---|---|---|---|---|
| Chuẩn bị | v1 | v1 | Chưa | Không |
| Triển khai tương thích | Ưu tiên v2, fallback v1 | Ghi theo cơ chế tương thích đã thiết kế | Chưa/nhỏ | Không |
| Chuyển dữ liệu | Ưu tiên v2, fallback v1 | Có kiểm soát revision | Có, giới hạn tải | Không |
| Bắt kịp thay đổi | Ưu tiên v2 | Chuyển canonical sang v2 | Có catch-up | Không |
| Cutover | v2, fallback tùy kế hoạch | v2 | Đối soát | Không |
| Ổn định | v2 | v2 | Có thể quét bù | Không |
| Contract | v2 | v2 | Dừng | Xóa sau retention |

Bảng này là **khung quy trình**, không phải lịch trình bắt buộc. Với cache có thể dựng lại, nhiều bước có thể đơn giản hơn.

## 14. Chọn phương án cutover và rollback an toàn

### 14.1. Cutover không phải chỉ đổi một biến

Trước khi tắt đường đọc v1, nên xác định:

- Có còn instance phiên bản cũ không?
- Có job/consumer nào ghi v1 không?
- Số lượng key cần chuyển còn lại là bao nhiêu?
- Các key mới có đúng type/serializer/TTL không?
- Những key bị lỗi chuyển đổi đã được xử lý chưa?
- Có chính sách cho những key không bao giờ được đọc không?
- Nếu chuyển thất bại, có thể quay lại trạng thái nào?

Một lỗi vận hành phổ biến là triển khai code v2 xong rồi **xóa ngay key v1**. Khi phát hiện lỗi và rollback binary về v1, ứng dụng cũ không còn đọc được dữ liệu.

### 14.2. Rollback khi code mới đã ghi dữ liệu mới

Giả sử v2 chỉ ghi Redis Hash, còn code v1 chỉ hiểu String JDK serialized. Nếu rollback v1 khi nó không còn nhận được các write gần nhất, dữ liệu có thể quay về trạng thái cũ.

Vì vậy, rollback có các mức:

- **Rollback code không đổi dữ liệu:** chỉ khả thi nếu code cũ vẫn đọc được dữ liệu cập nhật hiện tại.
- **Rollback có dual-write tương thích:** phải xác minh cả v1 và v2 được cập nhật nhất quán và không mất write.
- **Rollback cần reverse migration:** phải chuyển đổi ngược từ v2 về v1, có đối soát/versioning.
- **Không thể rollback trực tiếp:** cần forward-fix hoặc chuyển sang chế độ read-only trong lúc phục hồi.

**Không hứa có rollback chỉ vì chưa xóa key v1.** Nếu key v1 đã ngừng được cập nhật, nó có thể stale ngay sau cutover.

### 14.3. Xóa dữ liệu cũ sau retention

Chỉ xóa khi:

1. Mọi reader/writer đã được chuyển.
2. Đã hết cửa sổ rollback.
3. Đối soát đạt tiêu chí.
4. Dữ liệu backup/restore phù hợp.
5. Không có nhóm consumer hoặc script còn phụ thuộc v1.
6. TTL và chính sách lưu giữ cho phép.

Đối với key cache, nhiều trường hợp chỉ cần để tự hết TTL. Nếu chủ động dọn lượng khóa lớn, cân nhắc `UNLINK` thay vì `DEL` khi phù hợp, vì `UNLINK` cho phép Redis giải phóng phần bộ nhớ của object theo cơ chế không đồng bộ.

Cần xóa **đúng namespace**; không dùng wildcard thiếu giới hạn làm ảnh hưởng dữ liệu của phiên bản khác.

## 15. Spring Data Redis Repository: những cấu trúc phụ cần tính đến

Nếu dùng Spring Data Redis Repository với `@RedisHash`, việc đổi tên keyspace hoặc cách ánh xạ object có thể ảnh hưởng **nhiều khóa Redis**, không chỉ một String/Hash chính.

Ví dụ model:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("profiles")
public class ProfileEntity {

    @Id
    private String id;

    private String displayName;
}
```

Repository có thể sử dụng cấu trúc keyspace và metadata phục vụ việc tìm kiếm/truy cập thực thể.

Tùy annotation và cách cấu hình, còn có thể tồn tại:

- Key Hash lưu nội dung thực thể.
- Tập hợp lưu danh sách ID theo keyspace.
- Secondary index cho các trường được đánh chỉ mục.
- Các key phụ liên quan TTL, keyspace notifications hoặc bản sao phục vụ expiry event.
- Metadata phục vụ quan hệ Redis Repository.

Nếu đổi:

```java
@RedisHash("profiles")
```

thành:

```java
@RedisHash("profilesV2")
```

thì không nên giả định chỉ đổi tên một nhóm key là repository mới tự hoạt động đúng. Các **index, ID set và metadata phụ** có thể cần được xây dựng lại hoặc chuyển theo quy trình riêng.

### 15.1. Rebuild index an toàn

Một chiến lược:

1. Giữ reader cũ hoạt động.
2. Định nghĩa mapping mới và namespace mới.
3. Đọc thực thể cũ qua repository/template phù hợp.
4. Lưu bằng repository mới để framework xây các cấu trúc phụ tương ứng.
5. Đối soát truy vấn theo ID và theo secondary index.
6. Chỉ cutover khi các đường truy vấn quan trọng đạt yêu cầu.

Không tự `RENAME` một Hash chính rồi kỳ vọng toàn bộ secondary index của Repository sẽ được cập nhật.

### 15.2. TTL và shadow copy

Các tính năng TTL của repository có thể tạo những key phụ để hỗ trợ sự kiện hết hạn, tùy cấu hình. Nếu thay namespace, phải hiểu:

- Key chính có TTL hay không.
- Có bản sao phụ hoặc key tạm nào không.
- Các key phụ có chính sách retention khác key chính không.
- Listener và notification có tiếp tục trỏ tới namespace cũ không.

Nếu migrate nhầm key phụ như một entity chính, có thể tạo dữ liệu trùng hoặc sai mapping.

## 16. Không thể copy Redis Streams như một tập String bình thường

Thay đổi cấu trúc lưu của Redis Streams cần được xử lý theo mô hình của nó.

Stream có:

- Entry ID và các field/value.
- Consumer groups.
- Pending Entries List (PEL).
- Consumer ownership, delivery count và tiến độ xử lý.
- Chính sách retention/trim.

Nếu chỉ đọc các entry bằng `XRANGE` rồi `XADD` vào Stream mới, bạn có thể **không giữ nguyên đầy đủ trạng thái consumer group và pending**, thậm chí tạo ID mới hoặc thay đổi thứ tự/semantics.

Ví dụ:

```text
orders:stream:v1
  entries + group billing + group analytics + pending

orders:stream:v2
  entries được copy lại
  nhưng chưa chắc có group/PEL tương ứng
```

Một chiến lược chuyển Stream cần quyết định riêng:

- Dừng producers/consumers ở mốc nào?
- Entry ID cần giữ nguyên hay có thể sinh mới?
- Consumer groups mới bắt đầu ở offset nào?
- Pending cũ sẽ được xử lý hết trước cutover hay claim/replay?
- XACK của Stream cũ có còn ý nghĩa trên Stream mới không?
- Sự kiện có yêu cầu idempotency khi được xử lý lại không?

Không áp dụng máy móc quy trình `SCAN key -> GET -> SET` cho Stream hoặc các cấu trúc mang trạng thái xử lý.

## 17. Dữ liệu số và lock cần chính sách riêng

### 17.1. Counters

Một counter lưu trong Redis:

```redis
INCR stats:orders:v1
```

Nếu migration đọc giá trị 100 rồi `SET` cho v2, trong lúc đó writer cũ tiếp tục `INCR` v1 lên 101, giá trị v2 không tự đồng bộ.

Với counter là nguồn authoritative, cần:

- Chuyển writer theo một điểm cắt rõ ràng.
- Hoặc ghi lại các thay đổi phát sinh trong lúc copy.
- Hoặc sử dụng transaction/atomic protocol để di chuyển mốc.
- Không chỉ chạy hai lệnh `GET` và `SET`.

### 17.2. Distributed locks và fencing sequence

Một key lease có TTL:

```text
lock:job:42
```

không nên được copy sang namespace mới giống key cache thông thường.

Nếu cả hai hệ thống khóa cũ và mới cùng tồn tại, có thể xuất hiện **hai worker đều tin mình đã có lock**:

```text
Worker v1 giữ lock:v1:job42
Worker v2 giữ lock:v2:job42
```

Đối với locking:

- Phải thiết kế chuyển giao quyền giữa hai thế hệ worker.
- Không tạo hai namespace lock độc lập khi các worker cùng bảo vệ một tài nguyên.
- Fencing token/sequence nếu có phải giữ được tính không tái sử dụng và tăng đơn điệu.
- Không reset sequence chỉ vì đổi key prefix.
- Kiểm tra việc sử dụng token tại nơi tài nguyên được thay đổi.

Những key này không nên tham gia backfill tự động chỉ dựa trên pattern tên khóa nếu chưa có quy tắc riêng.

## 18. Redis Cluster, replica và failover trong migration

### 18.1. Quét và ghi phải đúng topology

Trong Redis Cluster, mỗi key thuộc một hash slot. Khi migration:

- `SCAN` cần bao phủ đúng tập primary.
- `GET`/`HGETALL` phải được định tuyến tới owner của slot.
- Lệnh đa-key hoặc Lua script phải tuân thủ giới hạn cùng slot.
- Một key mới có prefix khác có thể nằm ở slot khác so với key cũ.
- Resharding làm danh sách owner thay đổi trong lúc chạy.

Nếu chỉ scan một primary rồi báo “đã chuyển 100%”, các key trên primary khác có thể bị bỏ sót.

### 18.2. Không đọc dữ liệu nguồn cũ từ replica stale mà không tính đến lag

Redis replication thường bất đồng bộ. Nếu backfill đọc replica trong lúc writer cập nhật primary, nó có thể lấy snapshot cũ rồi ghi sang namespace mới.

Với dữ liệu không chấp nhận stale, nên lấy dữ liệu từ nguồn authoritative/canonical hoặc có revision để xác minh và cập nhật có điều kiện.

### 18.3. Redis persistence không thay thế đối soát

RDB snapshot, AOF và replication có vai trò đối với độ bền và khả năng phục hồi của Redis, nhưng chúng không tự bảo đảm rằng:

- Mọi key v1 đã được chuyển sang v2.
- Mọi giá trị đã được giải mã đúng.
- TTL mới có đúng hay không.
- Ghi đồng thời không bị mất.
- Index Repository mới được tạo.
- Consumer group Stream mới có tiến độ chính xác.

Cần cả **backup/restore** và **đối soát dữ liệu ở mức nghiệp vụ**.

### 18.4. Failover có thể làm trạng thái migration lùi lại

Với replication bất đồng bộ, khi Redis primary gặp sự cố, một số write đã được xác nhận nhưng chưa đến replica được promote có thể bị mất. Đây là rủi ro chung của Redis replication và có thể ảnh hưởng cả dữ liệu ứng dụng lẫn checkpoint migration nếu checkpoint chỉ lưu trong Redis đó.

Với dữ liệu quan trọng:

- Xem xét cơ chế persistence và failover thực tế.
- Không dùng một bộ đếm “đã di chuyển N keys” làm bằng chứng duy nhất.
- Giữ job migration có thể chạy lại an toàn.
- Đối chiếu trạng thái nguồn và đích sau khi hệ thống ổn định.
- Cân nhắc lưu checkpoint bền vững ở một hệ thống có cam kết phù hợp.

## 19. Đối soát dữ liệu trước cutover

### 19.1. Đếm key là chưa đủ

Nếu v1 có 100.000 key và v2 có 100.000 key, chưa chắc dữ liệu đã đúng:

- Có thể trùng logical ID.
- Một số key v2 chứa payload sai schema.
- Revision cũ có thể ghi đè revision mới.
- TTL có thể bị reset.
- Các field Hash có thể thiếu hoặc sai kiểu.
- Dữ liệu đã xóa có thể bị phục hồi.
- Một số key phụ của repository có thể chưa được tái tạo.

### 19.2. Định nghĩa hàm chuyển đổi canonical

Thay vì so sánh byte thô giữa JDK và JSON:

```text
old bytes -> LegacyProfile -> canonical view
new bytes -> ProfileV2    -> canonical view
```

So sánh các trường nghiệp vụ chung:

```text
logicalId
displayName
loyaltyPoints
revision
expiresAt (với dữ liệu có hạn)
```

Ví dụ:

```text
Old:  LegacyProfile("Lan", 20)
New:  ProfileV2(42, "Lan", 20, 2)

=> Nội dung nghiệp vụ tương đương
```

Không thể so byte JDK serialized với byte JSON rồi kết luận khác nhau là lỗi, vì định dạng vốn khác nhau.

### 19.3. Các metric cần ghi nhận

| Chỉ số | Giải thích |
|---|---|
| `keys_scanned` | Số lượt key được SCAN trả về |
| `unique_ids_seen` | Số logical IDs đã ghi nhận theo cơ chế thống kê phù hợp |
| `converted_success` | Số chuyển đổi thành công |
| `already_current` | Target đã có đúng phiên bản |
| `skipped_expired` | Source đã hết hạn trước lúc chuyển |
| `decode_errors` | Serializer cũ không giải mã được |
| `schema_errors` | Dữ liệu không đáp ứng schema mới |
| `write_conflicts` | Target mới hơn hoặc điều kiện CAS thất bại |
| `ttl_mismatches` | TTL/expireAt nằm ngoài sai số cho phép |
| `missing_in_target` | Có source hợp lệ mà không thấy target |
| `revision_mismatches` | Dữ liệu target chưa theo kịp nguồn |
| `scan_rate` | Số key chuyển mỗi giây |
| `redis_latency_p99` | Độ trễ Redis trong lúc migration |

Một bộ metric tốt phải phân biệt **key không có vì TTL hợp lệ** với **key bị mất do lỗi migration**.

### 19.4. Shadow-read

Trong giai đoạn chuyển tiếp, ứng dụng có thể:

```text
Reader production -> đọc v1 theo hợp đồng hiện tại
                   -> đọc v2 để đối soát nền
                   -> so sánh canonical data
                   -> trả kết quả chính thức từ đường hiện tại
```

Shadow-read giúp phát hiện sai lệch mà chưa thay đổi dữ liệu trả cho người dùng. Tuy nhiên:

- Tăng gấp đôi một phần tải Redis.
- Không nên log toàn bộ payload người dùng.
- Cần sample theo tỷ lệ có kiểm soát.
- Hai bản đọc ở hai thời điểm khác nhau có thể khác do ghi đồng thời; cần xét revision.
- Không kết luận lỗi nếu một key đã hết hạn hợp lệ giữa hai lượt đọc.

## 20. Điều tiết tốc độ backfill để không làm Redis quá tải

Migration có thể chạy hàng giờ hoặc nhiều ngày. Nếu phát hàng chục nghìn `GET` và `SET` mỗi giây, nó cạnh tranh trực tiếp với traffic production.

Một worker backfill nên có:

- **Batch size** được đo theo số key và kích thước payload.
- **Concurrency limit** cho số thao tác Redis in-flight.
- **Rate limit** để giữ ngân sách commands/giây.
- **Timeout** và retry với backoff, jitter.
- **Cơ chế pause/resume** khi Redis đang quá tải.
- **Checkpoint** và thống kê tiến độ.
- **Dead-letter/report** cho dữ liệu không thể giải mã.
- **Điều kiện ghi idempotent**, không overwrite dữ liệu mới hơn.

```text
SCAN keys
    |
    v
Bounded queue
    |
    v
Rate limiter + concurrency limit
    |
    v
Read old -> convert -> conditional write new
    |
    +---- Success ------> metrics
    |
    +---- Conflict -----> metrics / skip or reconcile
    |
    +---- Decode error -> quarantine + investigate
```

Không tạo một danh sách chứa toàn bộ keyspace trong JVM trước khi xử lý. Hãy xử lý theo các page/batch có dung lượng giới hạn.

Nếu dùng reactive Spring Data Redis, `flatMap(..., concurrency)` chỉ giới hạn concurrency trong pipeline, không tự giới hạn toàn bộ ứng dụng hoặc QPS. Với nhiều worker chạy song song phải xem tổng ngân sách.

## 21. Một số công cụ Redis hỗ trợ migration

| Công cụ | Dùng khi nào | Giới hạn cần nhớ |
|---|---|---|
| `SCAN` | Liệt kê key theo lô | Không snapshot, có thể trùng, phải bao phủ Cluster |
| `TYPE` | Xác nhận Redis type | Không giải mã object |
| `PTTL` | TTL tương đối | Có race với thời gian trôi |
| `PEXPIRETIME` | Lấy deadline tuyệt đối khi hỗ trợ | Vẫn cần kiểm soát race |
| `RENAME` | Đổi tên key giữ nguyên dữ liệu | Có thể ghi đè đích, mất key cũ |
| `RENAMENX` | Đổi tên nếu đích chưa có | Không đổi serializer/type |
| `COPY` | Nhân bản dữ liệu giữ nguyên kiểu | Không chuyển đổi schema |
| `DUMP` / `RESTORE` | Di chuyển dữ liệu ở định dạng nội bộ Redis | Không chuyển JDK serializer sang JSON |
| `MIGRATE` | Chuyển key giữa Redis instances khi thích hợp | Không phải converter ứng dụng, có rủi ro vận hành |
| `MULTI/EXEC` | Gộp thao tác Redis được hỗ trợ | Không tự tạo transaction với database, hạn chế theo slot |
| `EVAL` | Thực hiện logic Lua nguyên tử trên node/slot phù hợp | Không giải mã Java object một cách tự nhiên |
| `UNLINK` | Dọn key cũ giảm phần việc giải phóng bộ nhớ đồng bộ | Vẫn là thao tác xóa dữ liệu |
| `MEMORY USAGE` | Ước lượng bộ nhớ một key | Không thay đo tổng tải/memory |
| `INFO` / `SLOWLOG` | Quan sát tình trạng server | Không thay thế latency từ ứng dụng |

### 21.1. DUMP/RESTORE không chuyển value serializer ứng dụng

Ví dụ:

```redis
DUMP profile:v1:42
```

trả dữ liệu serialized theo **định dạng nội bộ của Redis**, khác với JSON hay JDK serialization do Spring Data Redis thực hiện bên trong value.

Nếu source key là Redis String chứa byte JDK serialized, việc `DUMP` rồi `RESTORE` ở tên khác vẫn giữ byte JDK serialized đó. Template JSON mới vẫn không tự đọc được.

**Chuyển đổi serializer** yêu cầu reader hiểu schema cũ và writer phát schema mới.

### 21.2. Không dùng MIGRATE như một phép biến đổi schema

Lệnh `MIGRATE` phục vụ việc chuyển key giữa Redis instances, không tự chuyển String thành Hash hoặc Java binary thành JSON. Nó còn liên quan tới quyền truy cập, topology, TTL và rủi ro khi thao tác trên dữ liệu thật.

Nếu mục đích chỉ là đổi object model trong cùng Redis, thường cần một job chuyển đổi ở tầng ứng dụng thay vì lệnh hạ tầng di chuyển key.

## 22. Kế hoạch phục hồi khi migration bị lỗi

Một migration thực tế phải dự kiến thất bại ở nhiều bước.

### 22.1. Decode error

Nếu một value cũ không thể deserialize:

```text
Key có tồn tại
    |
    v
Legacy deserializer throws
    |
    v
Không ghi target bằng dữ liệu mặc định
    |
    v
Đưa ID vào danh sách lỗi + metric
    |
    v
Điều tra class version / payload / serializer
```

Không nên:

- Nuốt exception rồi coi như key không tồn tại.
- Ghi một object rỗng vào v2.
- Xóa key v1 trước khi đã xác định nguyên nhân.
- Log toàn bộ byte dữ liệu chứa thông tin nhạy cảm.

### 22.2. Target đã có dữ liệu khác

Nếu target tồn tại với revision khác:

```text
source revision = 12
target revision = 14
```

Không được overwrite target bằng source cũ. Ghi nhận conflict và đối soát theo nguồn canonical.

Ngược lại, nếu source revision lớn hơn target, cũng không nên dùng lệnh `SET` vô điều kiện nếu một writer khác có thể cập nhật target ở cùng thời điểm. Phải có điều kiện atomic/version check.

### 22.3. Writer lỗi một nửa khi dual-write

```text
Write v1: thành công
Write v2: timeout / lỗi
```

Lúc này dữ liệu lệch. Cần một trong các chiến lược:

- Ghi canonical source rồi dùng outbox/change log để tái dựng target.
- Retry idempotent dựa trên operation ID và revision.
- Tạm dừng cutover, đối soát những key bị lệch.
- Trong phạm vi các key cùng slot, dùng Lua/transaction Redis để gộp các cập nhật có thể thực hiện nguyên tử.

Không giả định retry một lệnh ghi không idempotent luôn an toàn sau timeout; Redis có thể đã thực thi lệnh dù client chưa nhận được phản hồi.

### 22.4. Migration crash giữa batch

Job phải có thể chạy lại:

```text
Batch 1: done
Batch 2: done
Batch 3: xử lý dở -> crash
Restart -> xử lý lại có điều kiện/idempotent
```

Không phụ thuộc vào việc mỗi key chỉ xuất hiện đúng một lần trong SCAN.

### 22.5. Failover giữa lúc chuyển đổi

Sau failover, checkpoint hoặc write migration có thể không còn ở trạng thái mong đợi nếu replication chưa hoàn thành. Cần đọc lại trạng thái thực tế, kiểm tra nguồn canonical và chạy quét bù nếu cần. Không đánh dấu hoàn thành chỉ dựa vào bộ đếm trong RAM.

## 23. Những lỗi thường gặp

### Lỗi 1: Đổi key prefix trong code mà không chuyển dữ liệu

Các key cũ vẫn còn, nhưng reader mới chỉ tìm namespace mới nên thấy miss.

### Lỗi 2: Chỉ đổi valueSerializer

Dữ liệu đã lưu bằng serializer cũ không tự biến thành dữ liệu mới. Lỗi decode có thể xảy ra với từng key cũ.

### Lỗi 3: Quên keySerializer hoặc hashKeySerializer

Tên khóa hoặc tên field vật lý có thể không khớp chuỗi Java, làm reader mới không tìm được dữ liệu.

### Lỗi 4: Dùng HGETALL trên String cũ

Redis không tự convert String JSON thành Hash và có thể báo `WRONGTYPE`. Cần key mới và bước chuyển đổi rõ ràng.

### Lỗi 5: Reset TTL khi di chuyển

Khóa đáng lẽ hết hạn sau vài giây bị đặt lại TTL nhiều giờ hoặc thành key vô hạn.

### Lỗi 6: Sao chép dữ liệu hết hạn rồi hồi sinh

Source bị hết hạn hoặc xóa trong lúc migration nhưng job vẫn ghi target từ payload đã đọc trước đó.

### Lỗi 7: Dùng KEYS trên Redis production lớn

Làm Redis bận quét và có thể tăng latency cho request thật. Dùng SCAN có điều tiết, vẫn phải tính tới tính không snapshot.

### Lỗi 8: Cho rằng SCAN trả key đúng một lần

SCAN có thể trả trùng; job không idempotent sẽ tạo tác dụng phụ lặp hoặc ghi chồng dữ liệu.

### Lỗi 9: Quét một node rồi kết luận đã xong Cluster

Các hash slot nằm trên nhiều primary. Cần bao phủ topology và tính tới reshard/failover.

### Lỗi 10: Backfill SET ghi đè target mới hơn

Một writer mới có thể cập nhật v2 trong lúc backfill chuyển v1. Phải so revision và ghi có điều kiện.

### Lỗi 11: Không khóa writer cũ ở giai đoạn cutover

Một instance/job cũ vẫn ghi v1 sau khi ứng dụng đã đọc v2-only, gây sai lệch âm thầm.

### Lỗi 12: Xóa key cũ quá sớm

Rollback app về phiên bản cũ không còn dữ liệu để đọc; đặc biệt nguy hiểm với dữ liệu authoritative.

### Lỗi 13: Coi dual-write hai lệnh là atomic

Một nhánh có thể thất bại, hoặc lệnh nằm ở hai slot không cho phép gộp trong một transaction Redis.

### Lỗi 14: Chỉ kiểm tra tổng số key

Tổng key có thể bằng nhau nhưng payload, revision, TTL và secondary index khác nhau.

### Lỗi 15: Đổi @RedisHash mà không chuyển metadata phụ

Repository mới có thể thiếu danh sách ID, secondary index hoặc cấu trúc phục vụ expiration events.

### Lỗi 16: Copy Stream như String

Consumer groups và PEL không tự được chuyển khi chỉ copy entry payload. Có thể mất tiến độ xử lý.

### Lỗi 17: Reset fencing sequence khi đổi namespace

Token có thể bị tái sử dụng, phá vỡ điều kiện bảo vệ stale worker.

### Lỗi 18: Dùng Redis replica stale làm nguồn duy nhất để backfill

Migration có thể mang dữ liệu cũ sang namespace mới ngay khi primary đã có thay đổi mới hơn.

### Lỗi 19: Không có giới hạn tải

Backfill cạnh tranh với traffic thật, làm Redis p99 tăng và có thể gây timeout/retry storm.

### Lỗi 20: Nghĩ backup tự chứng minh migration đúng

Backup phục vụ khôi phục dữ liệu ở một thời điểm; nó không chứng minh mapping, TTL hay cutover đã chính xác.

## 24. Bài tập thực hành

### Bài tập A: Đổi namespace khi không đổi serializer

1. Tạo một key demo:

```redis
SET demo:profile:v1:42 "{\"name\":\"Lan\"}" EX 120
```

2. Kiểm tra:

```redis
TYPE demo:profile:v1:42
PTTL demo:profile:v1:42
```

3. Dùng `COPY` sang key v2:

```redis
COPY demo:profile:v1:42 demo:profile:v2:42
```

4. So sánh `GET`, `TYPE`, `PTTL` và nhận xét: **copy cùng byte chưa phải schema migration**.

5. Kiểm tra hành vi khi key đích đã tồn tại. Không dùng `REPLACE` nếu chưa có chính sách overwrite.

### Bài tập B: Chuyển String JSON thành Hash

1. Tạo String:

```redis
SET demo:cart:v1:42 "{\"userId\":42,\"status\":\"OPEN\",\"items\":3}" EX 120
```

2. Dùng Java `ObjectMapper` đọc JSON cũ.
3. Ghi một Hash mới với key `demo:cart:v2:42`.
4. Chủ động giữ TTL.
5. Dùng `TYPE`, `HGETALL`, `PTTL` đối soát kết quả.
6. Thử `HGETALL` trên String v1 để hiểu lỗi type.

### Bài tập C: Quan sát race backfill

1. Backfill đọc `revision=10` từ v1.
2. Tạo một write mới tại v2 với `revision=11`.
3. Thử `SET` không điều kiện bằng revision 10 để thấy lost update.
4. Thay bằng giao thức conditional write/version để ngăn ghi đè.

Chạy trên namespace demo, không trên dữ liệu production.

### Bài tập D: Mô phỏng TTL gần hết

1. Tạo key có TTL ngắn.
2. Đọc `PTTL`, đợi vài giây rồi tạo target với TTL cũ.
3. Quan sát target có thể tồn tại lâu hơn mốc hết hạn ban đầu.
4. Thảo luận việc dùng `PEXPIRETIME` và kiểm tra trạng thái source khi chuyển.

### Bài tập E: Backfill chạy lại

1. Tạo khoảng vài trăm key test với namespace v1.
2. Dùng SCAN theo batch.
3. Tạo một lần dừng job giữa chừng.
4. Chạy lại và bảo đảm không tạo bản ghi trùng hoặc ghi đè dữ liệu mới.
5. Báo số `converted`, `already_exists`, `expired`, `failed`.

### Bài tập F: Rolling deployment

Mô phỏng hai phiên bản service:

```text
App v1: chỉ hiểu key v1
App v2: đọc v2 rồi fallback v1
```

Cho cả hai chạy đồng thời. Thử ghi dữ liệu bằng v1 sau khi v2 đã backfill, rồi giải thích vì sao cần quy trình chuyển writer hoặc catch-up trước khi bật `NEW_ONLY`.

### Bài tập G: Kế hoạch rollback

Giả sử cutover xong 10 phút thì phát hiện JSON serializer mới lỗi với một loại enum. Hãy mô tả:

- Có thể tạm quay về đọc v1 không?
- V1 có còn chứa mọi write mới nhất không?
- Có cần reverse migration không?
- Có cách nào tạm dừng writer để bảo vệ dữ liệu không?
- Tiêu chí nào cho phép tiếp tục v2 sau khi sửa lỗi?

## 25. Câu hỏi tự kiểm tra

**1. Vì sao đổi `profile:42` thành `profile:v2:42` có thể làm ứng dụng thấy dữ liệu trống?**

Vì tên key vật lý đã đổi. Redis không tự chuyển khóa cũ sang namespace mới.

**2. Chỉ đổi JdkSerializationRedisSerializer thành JSON serializer có tự chuyển dữ liệu cũ không?**

Không. Các byte đã lưu vẫn ở định dạng cũ; cần reader cũ và converter/writer mới.

**3. Đổi Redis String JSON sang Hash có dùng RENAME là đủ không?**

Không. RENAME chỉ đổi tên key và giữ nguyên Redis type, không phân rã JSON thành các Hash fields.

**4. Vì sao không nên SET TTL mới 1 giờ khi key nguồn chỉ còn 10 giây?**

Nó kéo dài tuổi dữ liệu ngoài chính sách cũ, có thể làm session/quyền/metadata đã hết hạn tiếp tục xuất hiện.

**5. SCAN có bảo đảm snapshot không?**

Không. SCAN có thể trả trùng và bị ảnh hưởng bởi dữ liệu thêm/xóa trong lúc quét.

**6. SET NX có giải quyết mọi race giữa backfill và writer không?**

Không. Nó ngăn overwrite khi target đang tồn tại, nhưng không giải quyết writer cũ cập nhật v1 sau khi đã chuyển, xóa rồi hồi sinh hoặc target bị xóa.

**7. Khi nào có thể bỏ hẳn backfill?**

Khi Redis chỉ là cache tái tạo được từ nguồn có thẩm quyền và chấp nhận chi phí warm lại, với biện pháp tránh quá tải nguồn.

**8. Khi nào phải tính cả index của Spring Data Redis Repository?**

Khi đổi keyspace/serializer/cấu trúc cho thực thể lưu bằng Repository, nhất là khi có secondary index hoặc metadata TTL.

**9. Tại sao rollback code không chắc rollback được dữ liệu?**

Vì phiên bản cũ có thể không đọc được schema mới và các key v1 có thể đã ngừng được cập nhật.

**10. Nếu Redis Cluster có ba primary, SCAN một primary đủ chưa?**

Chưa. Phải quét đúng các phân vùng có dữ liệu liên quan và xét topology thay đổi.

**11. Tại sao không nên copy nguyên trạng một Stream đang có consumer group?**

Vì entry payload không đại diện đầy đủ cho tiến độ phân phối, Pending Entries List và ownership của consumers.

**12. Có thể dùng DUMP/RESTORE để chuyển Java serialized object sang JSON không?**

Không. DUMP/RESTORE bảo toàn định dạng Redis object, không hiểu schema Java và không chuyển value serializer ứng dụng.

**13. Để xác nhận migration hoàn tất, chỉ đếm key đủ không?**

Không. Cần đối soát logical IDs, field values, revision, TTL, index, writer coverage và lỗi chuyển đổi.

**14. Khi một writer vẫn dùng schema cũ, điều gì có thể xảy ra sau cutover?**

Dữ liệu v1 tiếp tục đổi còn v2 đứng yên, làm ứng dụng mới đọc dữ liệu stale hoặc mất cập nhật.

**15. Vì sao đổi namespace của distributed lock nguy hiểm hơn đổi namespace cache?**

Hai namespace có thể cho phép hai worker cùng giành quyền trên cùng tài nguyên. Lock và fencing sequence cần giao thức chuyển đổi riêng, không chỉ copy key.

## 26. Ghi nhớ

- **Migration Redis phải bảo vệ cả dữ liệu lẫn ngữ nghĩa.** Đổi namespace, serializer và Redis type là ba thay đổi khác nhau.
- **Phân loại Redis là cache hay nguồn authoritative.** Cache có thể warm lại; dữ liệu nghiệp vụ bền vững cần chuyển đổi/đối soát chặt chẽ.
- **Quản lý key/value/hash serializers rõ ràng** và duy trì reader cũ trong giai đoạn tương thích. Không tự deserialize native Java từ nguồn không đáng tin.
- **Dùng namespace có phiên bản** để hai schema cùng tồn tại khi rolling deployment; tránh `WRONGTYPE` và ghi đè đích.
- **Bảo toàn TTL và thời điểm hết hạn.** `GET` + `PTTL` + `SET` không atomic; đừng vô tình kéo dài tuổi khóa.
- **Quét bằng SCAN có giới hạn**, chấp nhận key lặp và dữ liệu thay đổi; trong Cluster phải bao phủ các primary.
- **Backfill phải idempotent và có kiểm soát revision.** `SET NX` giúp một phần nhưng không giải quyết toàn bộ vấn đề concurrent writes/delete.
- **Triển khai theo expand → migrate → contract**, có cutover, shadow-read, metrics, đối soát và kế hoạch rollback thực tế.
- **Dọn key cũ chỉ sau khi hết cửa sổ rollback**, các writer đã chuyển và chính sách retention cho phép.
- **Streams, Repository indexes, counters và distributed locks cần quy trình riêng**, không được xử lý như những Redis String cache thông thường.

### Tài liệu tham khảo

- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/template.html#redis:serializer).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/).
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/).
- [Redis — PEXPIRETIME](https://redis.io/docs/latest/commands/pexpiretime/).
- [Redis — COPY](https://redis.io/docs/latest/commands/copy/).
- [Redis — RENAME](https://redis.io/docs/latest/commands/rename/).
- [Redis — XINFO](https://redis.io/docs/latest/commands/xinfo/).
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
