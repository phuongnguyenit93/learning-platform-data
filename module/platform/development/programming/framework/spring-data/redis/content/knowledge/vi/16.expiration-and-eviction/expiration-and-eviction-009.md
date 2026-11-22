# Chọn TTL theo độ mới dữ liệu và rủi ro khóa hết hạn đồng loạt

Trong Spring Data Redis, **TTL (Time To Live)** quyết định một bản ghi cache có thể tồn tại bao lâu trước khi Redis coi nó là hết hạn. Chọn TTL là một quyết định về **độ mới dữ liệu, tải lên hệ thống gốc và khả năng chịu lỗi**, không chỉ là chọn số phút cho Redis.

Nếu TTL quá dài, ứng dụng có thể phục vụ thông tin đã thay đổi. Nếu TTL quá ngắn, Redis liên tục bỏ dữ liệu và ứng dụng phải truy vấn lại cơ sở dữ liệu hoặc dịch vụ nguồn. Ngay cả khi từng TTL có vẻ hợp lý, hàng nghìn khóa hết hạn gần như cùng lúc cũng có thể tạo ra một đợt tải đột biến.

## 1. TTL thực sự bảo đảm điều gì?

Giả sử ứng dụng đọc thông tin một sản phẩm từ database và ghi vào Redis lúc 10:00:00 với TTL 120 giây. Nếu không có thao tác cập nhật hay xóa khóa, bản ghi đó hết hạn vào khoảng 10:02:00.

- **Tuổi dữ liệu trong cache:** khoảng thời gian kể từ lúc ứng dụng ghi phiên bản đó vào Redis.
- **Độ trễ đồng bộ (staleness):** khoảng thời gian cache tiếp tục trả một phiên bản cũ sau khi nguồn đã thay đổi.
- **TTL:** giới hạn thời gian tồn tại của bản ghi kể từ lần ghi TTL gần nhất; nó không tự phát hiện thay đổi ở database.
- **Chính sách loại bỏ do thiếu bộ nhớ (eviction):** Redis có thể loại bỏ khóa *trước khi hết TTL* nếu cấu hình giới hạn bộ nhớ và chính sách eviction cho phép.

Ví dụ, database đổi giá lúc 10:00:10 nhưng cache chưa bị vô hiệu hóa. Với TTL 120 giây từ 10:00:00, giá cũ vẫn có thể được trả gần 110 giây nữa. Vì vậy, TTL đặt trần tương đối cho **thời gian dữ liệu cũ có thể được phục vụ** trong một mô hình cache-aside đơn giản; nó không đồng nghĩa với “dữ liệu luôn mới”.

Một số chi tiết Redis cần nắm:

| Hành vi | Ý nghĩa khi chọn TTL |
|---|---|
| `SET key value EX 120` / `SET key value PX ...` | Ghi giá trị và đặt thời gian hết hạn ngay trong một lệnh. |
| `EXPIRE key 120` | Đặt hoặc thay thời gian hết hạn cho khóa đã tồn tại. |
| `TTL key` trả `-2` | Khóa không còn tồn tại. |
| `TTL key` trả `-1` | Khóa tồn tại nhưng **không có thời gian hết hạn**. |
| `TTL key` trả số không âm | Số giây còn lại; `PTTL` dùng mili giây. |
| `GET key` | Chỉ đọc, mặc định **không gia hạn TTL**. |
| `SET key value` không kèm tùy chọn giữ TTL | Thường làm mất TTL cũ của khóa; cần đặt hạn khi ghi lại. |

Redis kiểm tra hết hạn theo cả cơ chế thụ động khi truy cập và chủ động ở nền. Không nên diễn giải TTL là cam kết Redis giải phóng bộ nhớ chính xác tại từng mili giây, nhưng ứng dụng sẽ không nhận giá trị hợp lệ đã hết hạn qua truy cập thông thường.

## 2. Xác định TTL từ yêu cầu độ mới và tác động nghiệp vụ

Trước khi cấu hình, hãy trả lời bốn câu hỏi cho **từng loại dữ liệu**:

1. **Dữ liệu thay đổi nhanh đến đâu?** Giá, tồn kho, cấu hình, bài viết và danh mục có nhịp thay đổi khác nhau.
2. **Người dùng chấp nhận dữ liệu cũ tối đa bao lâu?** Đây là giới hạn nghiệp vụ, có thể được diễn đạt thành SLA độ mới.
3. **Trả dữ liệu cũ gây hại đến mức nào?** Giá tham khảo khác với giá thanh toán; thông tin quyền truy cập khác với mô tả sản phẩm.
4. **Tái tạo một giá trị cache tốn bao nhiêu?** Một truy vấn đơn giản khác với tổng hợp hàng triệu bản ghi hoặc gọi API tính phí.

Một điểm khởi đầu có thể dùng trong thiết kế:

| Dữ liệu minh họa | Độ mới mong muốn | TTL khởi đầu để thử nghiệm | Chiến lược bổ sung |
|---|---|---|---|
| Giá hiển thị trên trang danh mục | Chậm tối đa khoảng 30–60 giây | 20–30 giây | Xóa cache theo sự kiện đổi giá; **đọc lại giá khi chốt đơn** |
| Tồn kho hiển thị gần đúng | Chậm vài giây | 2–5 giây, hoặc không cache | Kiểm tra/giữ hàng tại nguồn khi đặt đơn |
| Chi tiết sản phẩm ít đổi | Chậm vài phút | 5–15 phút | Invalidate khi sửa sản phẩm |
| Danh mục hoặc cấu hình ít đổi | Chậm 15–60 phút tùy chức năng | 10–30 phút | Làm mới theo phiên bản/sự kiện |
| Kết quả thống kê tốn tài nguyên | Có thể chậm vài phút | 1–5 phút | Làm mới sớm, giới hạn đồng thời, có thể phục vụ bản cũ |
| Kết quả “không tìm thấy” | Chỉ chấp nhận chậm rất ngắn | 5–30 giây | Negative caching, TTL riêng và chống truy vấn lặp |
| Quyền truy cập, hạn mức, số dư dùng cho quyết định quan trọng | Có thể yêu cầu dữ liệu hiện thời | Không dựa vào TTL đơn thuần | Xác thực tại nguồn hoặc cơ chế nhất quán/chủ động vô hiệu hóa phù hợp |

**Các con số trong bảng là ví dụ để bắt đầu đo lường, không phải giá trị mặc định cho mọi hệ thống.** Đặc biệt, không dùng cache TTL dài làm căn cứ cuối cùng cho giao dịch tài chính, phân quyền hay kiểm soát tồn kho.

### Xác lập giới hạn

Gọi `F` là độ cũ tối đa mà nghiệp vụ chấp nhận, `S` là giới hạn an toàn riêng cho loại dữ liệu đó, và `T` là TTL thiết kế. Trong cache-aside không có cơ chế invalidation đáng tin cậy:

```text
T <= min(F, S)   (khi cả hai giới hạn cùng tồn tại)
```

Đây là **điều kiện giới hạn**, chưa phải tối ưu hiệu năng. Còn phải đo tải nguồn, tỷ lệ cache hit, thời gian khôi phục và độ lệch dữ liệu thực tế. Nếu chỉ có giới hạn 60 giây, một TTL 60 giây chưa chắc phù hợp nếu vòng ghi/tạo cache có độ trễ lớn hoặc dữ liệu nguồn đã cũ khi đọc.

Có thể chọn TTL theo quy trình:

1. Định nghĩa độ cũ cho phép từ góc nhìn người dùng hoặc quyết định nghiệp vụ.
2. Chọn một TTL ban đầu **không vượt giới hạn đó**; giảm TTL khi dữ liệu biến động nhanh.
3. Đo thời gian tái tạo dữ liệu, lưu lượng miss, CPU/IO database và hit ratio trên tải thực.
4. Nếu tải nguồn quá lớn, cân nhắc invalidation theo sự kiện, làm mới sớm, cache nhiều tầng hoặc đổi cách tính; không tự kéo dài TTL vượt giới hạn nghiệp vụ.
5. Điều chỉnh TTL theo nhóm khóa và quan sát tác động qua các chu kỳ tải.

## 3. Vì sao hết hạn đồng loạt nguy hiểm?

Redis có thể chứa rất nhiều khóa có hạn sử dụng độc lập. Vấn đề xuất hiện khi **thời điểm hết hạn của chúng tập trung vào cùng một khoảng ngắn**:

```text
10:00:00  Batch job ghi 20.000 khóa, mỗi khóa TTL = 300 giây
             |
10:05:00  Nhiều khóa cùng hết hạn
             |
             +--> Hàng loạt request gặp cache miss
                       |
                       +--> Database / API nguồn nhận đợt truy vấn lớn
                       +--> Độ trễ và tỷ lệ lỗi tăng
                       +--> Retry có thể khiến đợt tải nghiêm trọng hơn
```

Đây là một dạng **cache avalanche** (nhiều khóa cùng hết hạn hoặc cache mất diện rộng). Cần phân biệt với **cache stampede** của một *khóa nóng*: nhiều request cùng phát hiện một khóa hết hạn và đều chạy truy vấn tái tạo dữ liệu. Một hệ thống có thể gặp cả hai cùng lúc.

Những tình huống thường dẫn đến đồng bộ thời điểm hết hạn:

- Nạp nóng hàng loạt khóa lúc khởi động hoặc triển khai phiên bản mới.
- Batch job ghi lại nhiều khóa trong cùng vài giây.
- Mọi khóa đều có một TTL tròn, cùng được tạo sau một đợt truy cập đồng thời.
- Chủ động xóa nhiều khóa khi nguồn thay đổi, sau đó mọi request cùng tái tạo.
- Nhiều request phụ thuộc một khóa tổng hợp rất đắt để tính lại.

TTL bằng nhau **không tự động** khiến tất cả khóa hết hạn đồng thời; vấn đề là **thời điểm ghi gần nhau cộng với thời lượng TTL giống nhau**. Jitter giúp trải thời điểm hết hạn, nhưng không ngăn được nhiều request cùng tranh nhau tái tạo một khóa nóng.

## 4. Rải thời điểm hết hạn bằng TTL jitter

**TTL jitter** là cộng hoặc trừ một lượng ngẫu nhiên vào TTL riêng của từng khóa, giúp tránh các đợt hết hạn bị đồng bộ. Có hai cách chọn khoảng dao động:

- Nếu `TTL_base` chỉ là mốc tham khảo và nghiệp vụ cho phép độ cũ cao hơn, có thể dùng `TTL_base ± jitter`.
- Nếu `TTL_max` là **trần độ cũ tuyệt đối**, chỉ nên **trừ** jitter:

```text
TTL_thuc_te = TTL_max - random(0, J)
0 <= J < TTL_max
```

Ví dụ, với TTL tối đa 120 giây và cửa sổ jitter 24 giây, mỗi khóa được ghi với TTL nằm trong khoảng **96–120 giây**. Khóa ghi cùng thời điểm sẽ không nhất thiết hết hạn cùng một giây.

Chọn `J` dựa vào khối lượng khóa được ghi đồng thời, khả năng chịu tải khi miss và độ ngắn TTL được chấp nhận. Với 12.000 khóa phân bố *tương đối đều* trong cửa sổ 24 giây, số khóa đến hạn trung bình là khoảng 500 khóa/giây, thay vì 12.000 khóa cùng một thời điểm. Đây là trực giác về phân bố, **không phải bảo đảm** số miss/giây: tần suất truy cập và sự phân bố thực tế của các khóa vẫn quyết định tải nguồn.

### Ví dụ với `StringRedisTemplate`

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWriter {
    private static final long MAX_TTL_SECONDS = 120;
    private static final long JITTER_WINDOW_SECONDS = 24;

    private final StringRedisTemplate redis;

    public ProductCacheWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cacheProduct(String productId, String jsonPayload) {
        // Trừ 0..24 giây, không vượt trần 120 giây.
        long subtractSeconds =
                ThreadLocalRandom.current().nextLong(JITTER_WINDOW_SECONDS + 1);
        long ttlSeconds = MAX_TTL_SECONDS - subtractSeconds;

        String key = "product:v1:" + productId;
        redis.opsForValue().set(key, jsonPayload, Duration.ofSeconds(ttlSeconds));
    }
}
```

Lệnh `set(key, value, Duration)` lưu giá trị và thời gian hết hạn trong cùng một thao tác Redis. Điều này tránh khoảng thời gian khóa tồn tại mà không có TTL nếu ghi `SET` rồi mới gửi `EXPIRE` riêng biệt.

Trong ví dụ này, jitter được chọn **mỗi lần ghi cache**. Nếu ứng dụng có các nhóm dữ liệu khác nhau, hãy đặt trần TTL và cửa sổ jitter theo nhóm; không dùng chung một con số ngẫu nhiên cho mọi khóa trong cùng batch.

## 5. Đặt TTL trong Spring Data Redis

Spring Data Redis có nhiều đường lưu dữ liệu. Cần chọn nơi áp TTL phù hợp với API đang dùng.

### 5.1. Với Spring Cache (`@Cacheable`): cấu hình TTL cho từng cache

```java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .disableCachingNullValues()
                        .entryTtl(Duration.ofMinutes(5));

        Map<String, RedisCacheConfiguration> perCache = Map.of(
                "productDetail", defaults.entryTtl(Duration.ofMinutes(10)),
                "productPrice", defaults.entryTtl(Duration.ofSeconds(30))
        );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(perCache)
                .build();
    }
}
```

Khi một phương thức dùng `@Cacheable("productPrice")`, các entry thuộc cache đó nhận TTL 30 giây khi ghi. `@Cacheable` xử lý việc tra cứu và tái sử dụng giá trị; **không tự bảo đảm chỉ một request thực hiện truy vấn nguồn trong mọi trường hợp đồng thời, mọi instance**. Nếu cần chống stampede đa instance, phải thiết kế thêm cơ chế điều phối.

Với cấu hình trên, TTL cố định theo cache. Nếu cần jitter **riêng từng entry**, có thể ghi qua `RedisTemplate` như ví dụ trước, hoặc dùng cơ chế TTL động phù hợp phiên bản Spring Data Redis (chẳng hạn `RedisCacheWriter.TtlFunction` trong các phiên bản hỗ trợ). Đừng giả định thêm jitter vào một TTL mặc định ở cấp cache sẽ tạo được sự khác nhau giữa các khóa.

Lưu ý rằng `RedisCacheManager` và `RedisTemplate` là hai lớp sử dụng khác nhau. Hãy thống nhất cách tạo key, serializer và chiến lược xóa cache để không xuất hiện hai bộ dữ liệu khác nhau cho cùng một nghiệp vụ.

### 5.2. Với `RedisTemplate`: chủ động kiểm soát TTL trên thao tác ghi

```java
// Dữ liệu có thể cũ tối đa 45 giây:
redisTemplate.opsForValue()
        .set("price:v1:" + productId, priceJson, Duration.ofSeconds(45));

// Tái đặt thời hạn cho khóa hiện có nếu nghiệp vụ thật sự cần:
Boolean updated = redisTemplate.expire(
        "price:v1:" + productId, Duration.ofSeconds(15));

// Quan sát thời gian còn lại (đơn vị giây):
Long remaining = redisTemplate.getExpire("price:v1:" + productId);
```

`updated` có thể là `false` nếu khóa không tồn tại. `remaining` có thể là `-2` (không có khóa) hoặc `-1` (không có TTL), nên không được xử lý mọi giá trị âm như một thời gian hợp lệ.

Không gọi `expire` sau **mỗi lần đọc** nếu mục tiêu là buộc dữ liệu phải được làm mới theo một trần thời gian: việc gia hạn theo truy cập sẽ biến TTL tuyệt đối thành cơ chế giống *sliding expiration*, khiến khóa nóng có thể tồn tại rất lâu cùng phiên bản cũ.

### 5.3. Phân biệt TTL của Redis với tuổi bản ghi nghiệp vụ

Một mã xác thực hết hạn lúc 10:05 có **deadline thực**. Nếu cache làm mới lúc 10:04 rồi cấp lại TTL 5 phút, ứng dụng có thể chấp nhận mã quá hạn. Với dữ liệu có thời điểm hết hạn nghiệp vụ, TTL phải dựa vào **thời gian còn lại tới deadline** (và bước xác thực chính) thay vì đặt lại một TTL cố định khi ghi.

Tương tự, `@RedisHash(timeToLive = ...)` và `@TimeToLive` thuộc cơ chế Redis repositories cho entity, còn TTL của `RedisCacheManager` thuộc Spring Cache. Cần biết mình đang dùng cơ chế nào trước khi kỳ vọng các cấu hình tác động lẫn nhau.

## 6. Kết hợp TTL với chống stampede và bảo vệ nguồn

**Jitter xử lý hiện tượng nhiều khóa cùng hết hạn; nó không giải quyết hoàn toàn việc nhiều request tái tạo cùng một khóa.** Với khóa nóng hoặc nguồn đắt tiền, cân nhắc kết hợp các phương án sau.

### 6.1. Cache-aside với gộp request

```text
Request A/B/C cùng truy cập khóa K đã hết hạn
                 |
       Kiểm tra cache: MISS
                 |
    Chỉ một luồng/instance được tái tạo K
                 |
       Đọc nguồn, ghi K + TTL
                 |
    Những request còn lại đọc lại K
```

Trong **một JVM**, có thể gộp các tác vụ đồng thời theo key bằng future/in-flight map hoặc cơ chế tương đương. Trong **nhiều instance**, cần phối hợp phân tán nếu cùng một khóa có thể được tái tạo tốn tài nguyên ở nhiều nơi. Khi sử dụng Redis lock, phải có TTL của lock, token sở hữu và thao tác giải phóng chỉ khi token khớp (ví dụ Lua compare-and-delete); không `DEL` bừa lock mà instance khác có thể đã sở hữu.

Ngay cả khi có lock, đường thất bại vẫn cần được thiết kế: request đợi bao lâu, đọc lại cache mấy lần, xử lý khi chủ lock lỗi, thời gian tính lại vượt TTL lock, và cách hạn chế số truy vấn đồng thời tới nguồn. Với thao tác ghi cần tính đúng tuyệt đối, lock cache không thay thế transaction hoặc điều kiện nhất quán tại database.

### 6.2. Soft TTL và hard TTL cho dữ liệu cho phép trả bản cũ

Một giá trị có thể lưu cả thời điểm `refreshAfter` và `expireAt` hoặc metadata tương tự:

```text
Ghi lúc t0
   |
   +---- t0 + 60s: soft TTL → ưu tiên làm mới nền
   |
   +---- t0 + 180s: hard TTL → không được phục vụ bản cũ nữa
```

Trước soft TTL, trả dữ liệu từ Redis. Sau soft TTL nhưng trước hard TTL, một request kích hoạt làm mới có điều phối và các request khác tạm dùng dữ liệu cũ, **nếu nghiệp vụ cho phép**. Sau hard TTL, phải làm mới hoặc trả lỗi/fallback được chấp thuận, không tiếp tục trả bản cũ vô hạn.

Nếu Redis đặt TTL thực đúng bằng soft TTL thì giá trị sẽ biến mất trước khi ứng dụng có cơ hội phục vụ stale; Redis TTL thực cần phù hợp hard TTL (hoặc chiến lược lưu trữ tương đương). Đặt metadata thời gian trong payload và dùng đồng hồ nhất quán đủ tốt cho ứng dụng. Không áp dụng stale-while-revalidate một cách tùy tiện cho số dư, quyền truy cập hoặc dữ liệu giao dịch nhạy cảm.

### 6.3. Làm mới chủ động và vô hiệu hóa theo sự kiện

Với dữ liệu thay đổi theo sự kiện (đổi giá, sửa hồ sơ, cập nhật cấu hình), có thể xóa hoặc cập nhật cache ngay khi thay đổi nguồn thành công. TTL lúc này là **hàng rào dự phòng** nếu có sự kiện bị bỏ sót, chứ không phải công cụ cập nhật duy nhất.

Cần cân nhắc tình huống ghi lại phiên bản cũ sau khi đã invalidate: request A đọc dữ liệu cũ, request B cập nhật DB rồi xóa cache, request A ghi lại giá trị cũ. Có thể cần version, kiểm tra phiên bản trước khi ghi, hoặc thiết kế thứ tự write/invalidate. Chọn chiến lược phù hợp với tính nhất quán bắt buộc.

### 6.4. Bảo vệ khi cache miss hàng loạt

Tùy tải và độ quan trọng của hệ thống, sử dụng giới hạn đồng thời khi tái tạo, rate limit, circuit breaker, backoff có jitter, prewarming có kiểm soát, và fallback đã được nghiệp vụ cho phép. Tránh retry tức thì từ nhiều instance khi Redis hoặc database đang chậm; retry có thể khuếch đại chính đợt tải mà cache được tạo ra để giảm.

Negative caching (ghi lại kết quả “không có dữ liệu”) bằng TTL ngắn giúp ngăn các request lặp cho key không tồn tại. Phải phân biệt “không tồn tại” với “nguồn đang lỗi”, và cân nhắc khả năng dữ liệu mới được tạo trong thời gian TTL âm còn hiệu lực.

## 7. Tình huống thiết kế: 10.000 sản phẩm được nạp cùng lúc

Một trang thương mại điện tử nạp trước 10.000 bản ghi chi tiết sản phẩm khi triển khai. Nghiệp vụ chấp nhận nội dung mô tả chậm tối đa khoảng 5 phút, nhưng không chấp nhận giá sai ở bước thanh toán.

**Thiết kế ban đầu:** tất cả chi tiết sản phẩm nhận TTL 300 giây vào khoảng 09:00. Đến 09:05, nhiều request đồng thời khiến cache miss và truy vấn database tăng mạnh.

**Thiết kế có kiểm soát:**

1. Giữ **TTL tối đa 300 giây** cho mô tả; mỗi khóa có TTL ngẫu nhiên trong khoảng 240–300 giây. Trần độ cũ vẫn được tôn trọng.
2. Nạp cache thành nhiều nhóm ở các thời điểm khác nhau thay vì cùng một nhịp; với khóa truy cập nóng, cân nhắc làm mới trước soft TTL.
3. Điều phối tái tạo cho từng khóa nóng, giới hạn số truy vấn database đang thực thi và xử lý fallback có kiểm soát.
4. Khi quản trị viên sửa mô tả, phát sự kiện vô hiệu hóa cache. TTL vẫn ngăn dữ liệu cũ nằm lại vô thời hạn nếu cơ chế sự kiện thất bại.
5. Cho **giá** một chiến lược cache riêng với TTL ngắn hơn, và lấy giá hợp lệ tại nguồn ở bước xác nhận giao dịch.

Đánh đổi cần đo là **số cache miss theo thời gian**, không chỉ tổng hit ratio: hai phương án có cùng hit ratio trong 10 phút nhưng một phương án dồn toàn bộ miss vào vài giây sẽ có độ ổn định rất khác nhau.

## 8. Quan sát và điều chỉnh TTL khi vận hành

Chọn một bộ chỉ số phản ánh cả độ mới lẫn tải:

| Chỉ số | Điều cần phát hiện |
|---|---|
| Hit/miss ratio theo tên cache, nhóm key và khoảng thời gian ngắn | Miss tăng đột ngột ở một nhóm khóa hoặc sau một batch. |
| QPS, độ trễ p95/p99 và lỗi của database/API nguồn | Cache miss có gây quá tải phụ thuộc phía sau không? |
| Số lần và thời gian tái tạo cache, số request đồng thời cho cùng key | Có stampede trên khóa nóng không? |
| Chênh lệch phiên bản hoặc tuổi dữ liệu trả về | Dữ liệu thực tế có vượt giới hạn freshness không? |
| Redis `expired_keys`, `evicted_keys`, bộ nhớ và độ trễ | Phân biệt hết hạn thông thường với loại bỏ do áp lực bộ nhớ. |
| Phân bố TTL còn lại lấy mẫu qua `TTL` / `PTTL` | Có nhiều khóa sắp hết hạn cùng lúc hoặc bị mất TTL bất ngờ không? |

Lưu ý `expired_keys` là chỉ số tích lũy của Redis; muốn tìm đỉnh bất thường phải xét **tốc độ tăng** trên khoảng thời gian. Khi lấy mẫu khóa, dùng cách quét an toàn như `SCAN`/công cụ quan sát phù hợp; không chạy `KEYS *` trên Redis production lớn để thống kê hàng loạt. Tránh log dữ liệu nhạy cảm hoặc key chứa thông tin cá nhân.

Đo trên tải thực và thử tình huống tải cao có chủ đích: sau deploy/prewarm, khi batch cập nhật, khi một key nóng hết hạn, khi database chậm, và khi Redis eviction xảy ra. Việc “đo” ở đây phục vụ lựa chọn TTL của hệ thống; không thay thế kiểm thử tích hợp của ứng dụng.

## 9. Những sai lầm cần tránh

- **Một TTL cho mọi loại dữ liệu:** làm dữ liệu nhạy độ mới bị cũ hoặc dữ liệu ổn định phải tái tạo quá thường xuyên.
- **TTL tròn đồng nhất cho batch lớn:** dễ tạo cụm hết hạn; dùng jitter và trải nhịp nạp dữ liệu.
- **Cộng jitter vượt mức stale cho phép:** vi phạm trần độ mới; nếu TTL là mức tối đa thì chọn jitter theo hướng trừ.
- **Chỉ dùng jitter để chống cache stampede:** vẫn có thể nhiều request tranh nhau tính lại cùng một khóa nóng.
- **Gia hạn TTL mỗi lần đọc mà không chủ đích:** giữ mãi phiên bản cũ của key nóng.
- **Ghi đè khóa rồi quên TTL:** có thể tạo khóa không hết hạn; kiểm tra trường hợp `TTL = -1`.
- **Nhầm TTL với eviction:** Redis có thể loại bỏ khóa trước hạn khi thiếu bộ nhớ; đừng coi TTL là bảo đảm dữ liệu luôn sẵn.
- **Trả stale vô hạn khi nguồn lỗi:** chỉ cho phép trong giới hạn hard TTL và với loại dữ liệu được nghiệp vụ chấp nhận.
- **Chỉ quan sát hit ratio trung bình:** bỏ sót những giây cache miss dồn dập gây quá tải.

## 10. Cách ra quyết định cho một nhóm khóa mới

Khi thêm một cache vào ứng dụng Spring Data Redis, dùng chuỗi quyết định sau:

```text
Dữ liệu có phục vụ quyết định cần chính xác tức thời không?
    |
    +-- Có --> Xác thực nguồn/thiết kế nhất quán trước;
    |           cache chỉ là tối ưu an toàn khi có cơ chế phù hợp.
    |
    +-- Không --> Xác định độ cũ tối đa được chấp nhận (F)
                   |
                   +--> Chọn TTL <= F và đo tải tái tạo
                   |
                   +--> Có nhiều khóa được ghi cùng lúc?
                   |       |
                   |       +-- Có --> Thêm jitter theo từng khóa;
                   |                  trải nhịp prewarm/refresh.
                   |
                   +--> Có khóa nóng hoặc nguồn tính toán đắt?
                   |       |
                   |       +-- Có --> Gộp request, giới hạn đồng thời;
                   |                  cân nhắc soft/hard TTL.
                   |
                   +--> Nguồn có phát sự kiện thay đổi đáng tin cậy?
                           |
                           +-- Có --> Invalidate/update chủ động;
                                      giữ TTL làm hàng rào dự phòng.
```

**Nguyên tắc thiết kế:** chọn TTL từ độ mới và rủi ro nghiệp vụ trước, sau đó tối ưu tải nguồn bằng cách rải thời điểm hết hạn và điều phối làm mới. Trong Spring Data Redis, TTL theo cache phù hợp khi các entry cùng đặc tính; TTL theo entry phù hợp khi cần jitter, deadline riêng hoặc độ mới khác nhau. Bất kể dùng cách nào, hãy quan sát **độ cũ thật sự của dữ liệu và các đỉnh cache miss** để kiểm chứng quyết định.
