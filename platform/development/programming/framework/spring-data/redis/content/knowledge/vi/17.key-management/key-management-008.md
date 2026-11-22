# Kiểm soát quyền cho lệnh quản trị và lệnh xóa dữ liệu diện rộng trong Spring Data Redis

## 1. Vì sao quản lý khóa cần kiểm soát quyền?

Redis thường lưu session, cache, khóa phối hợp và dữ liệu tạm của nhiều tính năng. Một lệnh xóa đúng một khóa có thể là thao tác nghiệp vụ bình thường; cùng loại lệnh đó, khi áp dụng cho hàng nghìn khóa hoặc kết hợp với thao tác liệt kê toàn bộ keyspace, có thể gây mất dữ liệu diện rộng. Lệnh quản trị còn có khả năng thay đổi cấu hình, ngắt kết nối, dừng máy chủ hoặc xóa toàn bộ cơ sở dữ liệu.

Trong ứng dụng Spring Data Redis, `RedisTemplate`, `StringRedisTemplate` và abstraction như Spring Cache đều thực thi lệnh bằng danh tính của kết nối Redis. **Spring Data Redis không tự quyết định tài khoản nào được chạy lệnh nguy hiểm**: Redis ACL (Access Control List) là lớp kiểm soát quyền tại máy chủ. Ứng dụng cần kết nối bằng đúng tài khoản, thiết kế API có giới hạn và bố trí riêng các tác vụ bảo trì.

Mục tiêu học tập:

- Phân biệt thao tác với một khóa, xóa nhiều khóa và lệnh quản trị toàn bộ Redis.
- Cấp quyền tối thiểu theo cả **lệnh** lẫn **mẫu tên khóa**.
- Tách tài khoản vận hành ứng dụng, tác vụ dọn dẹp và quản trị.
- Thiết kế thao tác xóa có giới hạn, có chế độ xem trước và có thể kiểm toán.
- Xác minh quyền mà không cần thực thi lệnh phá hủy dữ liệu.

## 2. Mức độ tác động của các nhóm lệnh

| Nhóm | Lệnh tiêu biểu | Rủi ro chính |
| --- | --- | --- |
| Đọc/ghi khóa thông thường | `GET`, `SET`, `EXPIRE`, `TTL` | Truy cập dữ liệu ngoài phạm vi nghiệp vụ nếu không giới hạn tên khóa. |
| Xóa khóa | `DEL key [key ...]`, `UNLINK key [key ...]` | Xóa một hoặc nhiều khóa; khi kết hợp với vòng lặp quét có thể xóa hàng loạt. |
| Liệt kê khóa | `KEYS pattern`, `SCAN cursor MATCH pattern` | `KEYS` duyệt toàn bộ keyspace trong một lệnh và có thể chặn máy chủ khi dữ liệu lớn; `SCAN` duyệt tăng dần nhưng vẫn có thể liệt kê rất nhiều tên khóa. |
| Xóa database/instance | `FLUSHDB`, `FLUSHALL` | `FLUSHDB` xóa dữ liệu ở database hiện hành; `FLUSHALL` xóa dữ liệu ở tất cả database của Redis instance. Không giới hạn theo prefix. |
| Quản trị máy chủ | `CONFIG`, `SHUTDOWN`, `DEBUG`, `REPLICAOF` | Thay đổi vận hành, ảnh hưởng khả dụng, cấu hình hoặc trạng thái nhân bản. |
| Bảo mật và kết nối | `ACL`, `CLIENT KILL` | Thay đổi quyền hoặc ngắt các kết nối khác. |
| Scripting/extension | `EVAL`, `EVALSHA`, `FUNCTION`, `MODULE` | Mở thêm đường thực thi nhiều thao tác đối với dữ liệu hoặc máy chủ. |

Cần hiểu một số khác biệt:

1. `UNLINK` tách khóa khỏi keyspace ngay và chủ yếu giải phóng bộ nhớ ở luồng nền. **Dữ liệu vẫn bị xóa**; đây không phải cách để khôi phục một lệnh xóa nhầm.
2. `SCAN` duyệt tăng dần với `MATCH` và `COUNT`. `COUNT` chỉ là gợi ý về lượng công việc, không phải giới hạn cứng. Kết quả có thể trùng lặp hoặc thay đổi khi keyspace biến động; `SCAN` không tạo snapshot nhất quán.
3. `FLUSHDB` và `FLUSHALL` có thể hỗ trợ cơ chế giải phóng bộ nhớ bất đồng bộ, nhưng phạm vi dữ liệu bị xóa không thay đổi.
4. Chặn `FLUSHALL` chưa đủ: vòng lặp `SCAN` + `UNLINK`, hay `DEL` với danh sách rất lớn, vẫn có thể xóa dữ liệu diện rộng.
5. Tách logical database bằng `SELECT` không tạo ranh giới bảo mật mạnh. `FLUSHALL` ảnh hưởng toàn instance; Redis Cluster thông thường chỉ dùng database 0.

## 3. Thiết kế các vai trò truy cập

Thay vì để mọi thành phần dùng chung tài khoản có quyền rộng, hãy tách các danh tính:

| Danh tính | Nhu cầu | Quyền nên cấp |
| --- | --- | --- |
| `app_runtime` | Đọc, ghi và đặt TTL cho session | Chỉ các lệnh thực sự dùng đối với `app:session:*`; không cấp quyền xóa hàng loạt hay lệnh quản trị. |
| `cleanup_job` | Dọn một namespace cache được chỉ định | Quyền `SCAN` và `UNLINK` giới hạn ở tác vụ bảo trì có kiểm soát. |
| `observer` | Kiểm tra tình trạng hệ thống | Một số lệnh quan sát được lựa chọn; không mặc nhiên cấp toàn bộ `@admin`. |
| `redis_operator` | Xử lý sự cố, thay đổi cấu hình, phục hồi | Danh tính quản trị riêng, truy cập có thời hạn và gắn với quy trình vận hành. |

Ví dụ, ứng dụng session có TTL có thể không cần `DEL` hay `UNLINK`. Nếu nghiệp vụ logout đòi xóa session ngay, có thể cấp quyền xóa trong namespace session, nhưng phải biết ACL không tự khống chế số khóa được xóa.

### Ranh giới của Redis ACL

Redis 6 trở lên hỗ trợ ACL cho phép hoặc từ chối từng lệnh, nhóm lệnh và pattern khóa. Ví dụ `~app:session:*` chỉ cho phép những lệnh có đối số khóa được Redis nhận diện thao tác với key thuộc prefix đó.

**ACL không đặt điều kiện “mỗi lệnh chỉ xóa tối đa một khóa”, “tối đa 100 khóa/phút”, “phải dry-run” hoặc “phải được duyệt”.** Nếu user được phép `DEL` trong `app:session:*`, nó vẫn có thể xóa nhiều khóa thuộc namespace này. Những giới hạn theo số lượng, thời gian, người vận hành và ngữ cảnh nghiệp vụ phải nằm ở lớp ứng dụng hoặc job.

Một ranh giới quan trọng khác: pattern `~prefix:*` được kiểm tra đối với các đối số được định nghĩa là **khóa**; kết quả `SCAN` không tự bị lọc theo ACL key pattern. Một kết nối có quyền `SCAN` có thể nhìn thấy tên khóa nằm ngoài prefix mà nó được phép sửa. `MATCH` là bộ lọc do người gọi chọn, không phải hàng rào bảo mật. Vì thế chỉ cấp quyền quét cho danh tính tin cậy và cân nhắc tách Redis instance khi yêu cầu cô lập nghiêm ngặt.

## 4. Khai báo ACL theo nguyên tắc cho phép tường minh

Ví dụ file ACL dưới đây minh họa chính sách, trong đó `REPLACE_*` chỉ là chỗ giữ chỗ cho mật khẩu được quản lý an toàn:

```text
# users.acl — ví dụ, không lưu mật khẩu thật trong Git
user default off
user app_runtime on >REPLACE_APP_SECRET resetkeys ~app:session:* -@all +ping +get +set +exists +expire +ttl +pttl
user cleanup_job on >REPLACE_CLEANUP_SECRET resetkeys ~app:cache:expired:* -@all +ping +scan +unlink
```

- `user default off` tắt tài khoản mặc định. **Phải tạo và xác minh đường đăng nhập quản trị khác trước khi bật chính sách này**, nếu không dễ tự khóa quyền quản trị.
- `on` bật user, `>...` thiết lập mật khẩu, `resetkeys` xóa các pattern khóa cũ và `~...` đặt phạm vi khóa được phép.
- `-@all` thu hồi toàn bộ quyền chạy lệnh; `+...` cho phép tường minh từng lệnh cần thiết.
- `app_runtime` không có `DEL`, `UNLINK`, `KEYS`, `SCAN`, `FLUSHDB` và `FLUSHALL`.
- `cleanup_job` có quyền `UNLINK` với các khóa thuộc `app:cache:expired:*`. Quyền `SCAN` cần được coi là quyền nhạy cảm vì có thể liệt kê tên khóa khác.

Redis có nhóm quyền như `@read`, `@write`, `@keyspace`, `@admin`, `@dangerous`. Những nhóm này hữu ích khi xem quyền nhưng cấp quyền theo lệnh thường dễ kiểm soát hơn cho user chuyên dụng. Đặc biệt, `-@dangerous` **không chặn mọi hình thức xóa dữ liệu diện rộng**: `DEL` và `UNLINK` vẫn có thể được cấp theo nhóm khác.

Tùy Redis và phiên bản client, bước kết nối có thể dùng thêm lệnh bắt tay hoặc kiểm tra như `HELLO`, `CLIENT SETINFO`, `SELECT`. Hãy ghi nhận lệnh thực tế và thêm đúng lệnh hoặc subcommand cần dùng, thay vì cấp `+@all` để che giấu lỗi. Bảo vệ file ACL và secret bằng quyền đọc thích hợp; luân chuyển thông tin xác thực theo quy trình.

### Kiểm tra chính sách một cách an toàn

Redis 7 trở lên hỗ trợ `ACL DRYRUN` để kiểm tra quyền giả định mà **không thực hiện lệnh**. Bằng danh tính quản trị có quyền kiểm tra ACL:

```redis
ACL DRYRUN app_runtime GET app:session:123
ACL DRYRUN app_runtime GET other-service:session:123
ACL DRYRUN app_runtime DEL app:session:123
ACL DRYRUN app_runtime FLUSHALL
ACL DRYRUN cleanup_job UNLINK app:cache:expired:123
ACL DRYRUN cleanup_job UNLINK app:session:123
```

Với chính sách ví dụ, kết quả mong muốn lần lượt là: cho phép; từ chối do pattern khóa; từ chối do lệnh; từ chối do lệnh; cho phép; từ chối do pattern khóa. Với Redis 6, thử các lệnh không phá hủy bằng user thử nghiệm và kiểm tra phản hồi quyền; không gửi `FLUSH*` lên dữ liệu thật để “thử chặn”.

`ACL LOG` hỗ trợ điều tra sự kiện xác thực hoặc từ chối quyền, nhưng **không phải nhật ký toàn bộ lệnh được thực thi thành công**. Muốn truy vết thao tác xóa, cần log từ ứng dụng, job và hệ thống quản trị kèm mã yêu cầu.

## 5. Danh tính kết nối trong Spring Data Redis

Spring Boot 3.x có thể lấy cấu hình Redis thông thường từ các biến môi trường hoặc secret do nền tảng triển khai cấp:

```text
SPRING_DATA_REDIS_HOST=redis.internal.example
SPRING_DATA_REDIS_PORT=6379
SPRING_DATA_REDIS_USERNAME=app_runtime
SPRING_DATA_REDIS_PASSWORD=<injected-secret>
SPRING_DATA_REDIS_SSL_ENABLED=true
```

Ví dụ giả định môi trường đã cấu hình Redis có TLS; điều chỉnh host, port và SSL theo triển khai. Không đặt mật khẩu thật trong `application.yml` được commit, mã nguồn, URL kết nối hay log. Cùng với ACL, cần giới hạn mạng kết nối đến Redis và dùng TLS khi lưu lượng đi qua môi trường không tin cậy.

Một worker dọn cache nên dùng connection factory riêng với tài khoản `cleanup_job`. Không inject kết nối dọn dẹp vào controller nhận yêu cầu thông thường. Nếu phải sử dụng hai kết nối trong một tiến trình, hãy đặt tên bean và qualifier tường minh:

```java
@Configuration
class CleanupRedisConfig {

    @Bean("cleanupConnectionFactory")
    RedisConnectionFactory cleanupConnectionFactory(Environment env) {
        String host = env.getRequiredProperty("cleanup.redis.host");
        int port = env.getRequiredProperty("cleanup.redis.port", Integer.class);
        String username = env.getRequiredProperty("cleanup.redis.username");
        String password = env.getRequiredProperty("cleanup.redis.password");

        RedisStandaloneConfiguration config =
                new RedisStandaloneConfiguration(host, port);
        config.setUsername(username);
        config.setPassword(RedisPassword.of(password));

        return new LettuceConnectionFactory(config);
    }

    @Bean("cleanupRedisTemplate")
    StringRedisTemplate cleanupRedisTemplate(
            @Qualifier("cleanupConnectionFactory") RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
```

Các import tương ứng nằm trong Spring Framework, Spring Data Redis và Lettuce integration của Spring Data Redis. Đây là ví dụ tách danh tính đối với kết nối standalone: nếu endpoint yêu cầu TLS, phải cấu hình `LettuceClientConfiguration` thích hợp cho factory này; nó không tự kế thừa SSL của factory chính. Các thuộc tính `cleanup.redis.*` do secret/config riêng cung cấp, không lấy từ request của người dùng.

## 6. Dọn khóa theo namespace và hạn mức

Cần phân biệt **quyền được xóa** với **chính sách quyết định được xóa gì, khi nào và bao nhiêu**. Redis ACL giải quyết vế đầu; ứng dụng hoặc job bảo trì giải quyết vế sau.

Một job dọn dẹp nên thực hiện đồng thời:

1. **Phạm vi cố định:** prefix như `app:cache:expired:` được cấu hình cứng ở job, không cho request tự truyền mẫu `*`.
2. **Xem trước:** chạy dry-run để thu thập số khóa ứng viên và gửi kết quả cho operator kiểm tra.
3. **Giới hạn số lượng:** mỗi lượt có số khóa tối đa, hạn mức tốc độ, thời gian chạy và quyền kích hoạt riêng.
4. **Xóa theo lô nhỏ:** dùng `SCAN` để duyệt và `UNLINK` khi phù hợp; kiểm tra prefix trước khi xóa.
5. **Ghi nhận:** lưu namespace, số ứng viên, số khóa thực xóa, thời điểm, danh tính job và mã phê duyệt.
6. **Khóa đường truy cập:** chỉ scheduler hoặc operator được phép kích hoạt; không tạo endpoint công khai mang quyền của `cleanup_job`.

Ví dụ dịch vụ bảo trì cho Redis standalone, với `StringRedisTemplate` riêng mang tài khoản `cleanup_job`:

```java
@Service
public class ScopedCacheCleanup {

    private static final String PREFIX = "app:cache:expired:";
    private final StringRedisTemplate redis;

    public ScopedCacheCleanup(
            @Qualifier("cleanupRedisTemplate") StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record Result(int candidates, long removed, boolean dryRun) {}

    public Result execute(boolean dryRun, int maxKeys) {
        if (maxKeys < 1 || maxKeys > 200) {
            throw new IllegalArgumentException("maxKeys phải trong khoảng 1..200");
        }

        Set<String> candidates = new LinkedHashSet<>();
        ScanOptions options = ScanOptions.scanOptions()
                .match(PREFIX + "*")
                .count(100)
                .build();

        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext() && candidates.size() < maxKeys) {
                String key = cursor.next();
                if (key.startsWith(PREFIX)) {
                    candidates.add(key);
                }
            }
        }

        if (dryRun) {
            return new Result(candidates.size(), 0, true);
        }

        long removed = 0;
        for (String key : candidates) {
            if (Boolean.TRUE.equals(redis.unlink(key))) {
                removed++;
            }
        }
        return new Result(candidates.size(), removed, false);
    }
}
```

Cần import `java.util.Set`, `java.util.LinkedHashSet`, `org.springframework.data.redis.core.Cursor`, `org.springframework.data.redis.core.ScanOptions`, `org.springframework.data.redis.core.StringRedisTemplate` và các annotation Spring tương ứng. Đoạn mã minh họa cơ chế giới hạn khóa; khi dùng thực tế phải bổ sung xác thực người chạy, phê duyệt, rate limit, log và metric.

**Các giới hạn phải chấp nhận:** job chỉ xử lý tối đa 200 ứng viên mỗi lần, không bảo đảm đã duyệt hết keyspace; `SCAN` không bảo đảm snapshot nhất quán; khóa có thể hết hạn hoặc bị sửa giữa quét và xóa; số khóa xóa thành công có thể khác số ứng viên. Trong Redis Cluster, việc duyệt cần xử lý từng primary node; không mặc định một `scan()` đã bao phủ toàn cluster. Tránh xóa nhiều khóa thuộc các hash slot khác nhau trong cùng lệnh; ví dụ gọi `unlink(key)` từng khóa.

Với nhu cầu xóa số lượng rất lớn, thiết kế job có checkpoint, giới hạn tốc độ, khả năng tạm dừng và xác nhận từng đợt. Không chỉ tăng `maxKeys` để xử lý nhanh hơn.

### Những API Spring Data Redis dễ gây tác động rộng

- `redisTemplate.keys("app:*")` sử dụng `KEYS`, không phù hợp để quét keyspace lớn trong môi trường sản xuất.
- `redisTemplate.delete(collection)` và `unlink(collection)` có thể xóa nhiều khóa; phải kiểm soát nguồn danh sách và giới hạn số lượng.
- `Cache.clear()`, `@CacheEvict(allEntries = true)` và endpoint xóa cache có thể dẫn đến lệnh xóa nhiều khóa. Tùy cấu hình `RedisCacheWriter`, thao tác clear cache có thể dùng `KEYS` cùng `DEL`. Chiến lược batch dùng `SCAN` giảm nguy cơ block khi duyệt nhưng vẫn xóa nhiều dữ liệu.

Đối với cache thông thường, ưu tiên TTL, namespace có version hoặc cơ chế hết hạn đã thiết kế trước. Chức năng clear cache diện rộng nên đi qua job bảo trì có phân quyền riêng thay vì controller nghiệp vụ.

## 7. Quy trình vận hành cho các lệnh nguy hiểm

Các lệnh như `FLUSHDB`, `FLUSHALL`, `CONFIG`, `SHUTDOWN`, `ACL SETUSER` hay `REPLICAOF` chỉ nên được dùng trong đường quản trị có kiểm soát. Tài khoản runtime và job dọn cache không nên sở hữu quyền này.

| Bước | Thông tin cần xác nhận |
| --- | --- |
| Chọn đích | Redis instance/cluster, môi trường, database, namespace, các dịch vụ cùng sử dụng. |
| Đánh giá ảnh hưởng | Dữ liệu có thể tái tạo không? Có liên quan session, hàng đợi, lock hoặc dữ liệu nghiệp vụ không? |
| Sẵn sàng phục hồi | Snapshot/backup, thời điểm khôi phục, kế hoạch xử lý gián đoạn; diễn tập khi cần. |
| Phê duyệt | Người yêu cầu, người duyệt, mã thay đổi, cửa sổ bảo trì và thời hạn quyền quản trị. |
| Thực thi | Xác thực lại chính xác môi trường và máy chủ trước khi chạy lệnh đã duyệt. |
| Hậu kiểm | Kiểm tra số khóa, error rate, latency, hit/miss cache, kết nối và mức phục hồi dịch vụ. |

Nếu buộc phải dùng `FLUSH*`, nên dùng phiên/công cụ quản trị tạm thời và ghi lại thao tác. Trong Redis instance dùng chung, không thể coi `FLUSHDB` hay `FLUSHALL` là một thao tác dọn cache cục bộ; hãy đánh giá phương án xóa theo namespace trước khi mở quyền đó.

## 8. Phòng vệ bổ sung và xử lý sự cố

ACL chỉ là một lớp trong kiến trúc an toàn:

- **Phân tách tài nguyên:** dữ liệu có mức độ quan trọng hoặc yêu cầu cô lập khác nhau nên được cân nhắc tách Redis instance/cluster. Prefix không thay thế ranh giới cô lập.
- **Bảo vệ kết nối:** giới hạn truy cập mạng, dùng TLS khi cần, tách secret theo danh tính, luân chuyển và hạn chế quyền đọc secret.
- **Quản lý chính sách:** lưu ACL trong cấu hình có kiểm soát, theo dõi thay đổi và kiểm tra lại quyền khi nâng cấp Redis hoặc driver.
- **Giám sát:** theo dõi latency, số khóa, memory, eviction, hit rate, lỗi `NOPERM` và hiệu ứng của job dọn cache; ghi nhận mã lần chạy.
- **Tránh đường vòng:** không cấp `EVAL`, `FUNCTION`, `MODULE` hoặc cả nhóm quyền rộng chỉ để giải quyết một thao tác nhỏ.

| Hiện tượng | Diễn giải ban đầu | Hướng xử lý |
| --- | --- | --- |
| `WRONGPASS` hoặc `NOAUTH` | Sai thông tin xác thực hoặc chưa xác thực. | Kiểm tra danh tính, secret và luồng tạo kết nối. |
| `NOPERM` | Không có quyền chạy lệnh hoặc quyền trên khóa. | Kiểm tra lệnh và key pattern; dùng `ACL DRYRUN`/`ACL LOG` trước khi xét mở quyền. |
| `CROSSSLOT` | Lệnh nhiều khóa trong Redis Cluster không thỏa hash slot. | Tách thao tác theo slot/khóa; cấp thêm ACL không giải quyết lỗi này. |
| Cache biến mất trên diện rộng | Job/API có thể sở hữu quyền và phạm vi quá rộng. | Tra log job, lịch chạy, lời gọi clear cache và quyền tài khoản. |
| Độ trễ tăng khi bảo trì | Quét rộng, lệnh nặng hoặc lưu lượng xóa cao. | Hạ batch/rate, kiểm tra metric và tạm dừng job theo runbook. |

## 9. Ví dụ tổng hợp: session và cache được dọn theo lịch

Giả sử cùng một Redis có các key:

```text
app:session:<session-id>          # session có TTL
app:cache:expired:<cache-id>      # nhóm khóa được phép dọn
other-service:*                   # dữ liệu của dịch vụ khác
```

Phương án triển khai:

1. Luồng HTTP dùng `app_runtime`, chỉ đọc/ghi khóa `app:session:*` và cập nhật TTL. Tài khoản không có quyền `FLUSHALL` hoặc `SCAN`.
2. Scheduler bảo trì dùng `cleanup_job`, chạy dry-run trước, ghi nhận số ứng viên, giới hạn tối đa 200 khóa/lượt và chỉ `UNLINK` khóa thuộc `app:cache:expired:*`.
3. Dữ liệu `other-service:*` nằm ngoài quyền thao tác khóa của hai tài khoản. Vì `SCAN` có thể lộ tên khóa, job dọn dẹp được cô lập trong môi trường tin cậy.
4. Xóa toàn instance chỉ diễn ra qua quy trình của operator với danh tính quản trị riêng, sau khi xác định tác động và khả năng phục hồi.

Thiết kế này kết hợp **quyền tối thiểu tại Redis** với **giới hạn nghiệp vụ tại Spring Data Redis**. ACL kiểm soát lệnh và khóa; ứng dụng giới hạn lý do, số lượng, thời điểm và người được kích hoạt. Cả hai lớp đều cần thiết để giảm hậu quả của lỗi lập trình, cấu hình sai và thao tác nhầm.

## 10. Câu hỏi tự kiểm tra

1. Vì sao cấm `FLUSHALL` nhưng cấp `SCAN` + `UNLINK` trên toàn bộ keyspace vẫn không an toàn?
2. ACL `~app:session:*` có bảo đảm mỗi lệnh `DEL` chỉ xóa đúng một khóa không? Cần kiểm soát ở lớp nào?
3. `UNLINK` khác `DEL` ra sao về việc giải phóng bộ nhớ, và vì sao cả hai đều cần hạn mức?
4. Vì sao `@CacheEvict(allEntries = true)` nên được xem như thao tác bảo trì có rủi ro?
5. `ACL DRYRUN` và `ACL LOG` hỗ trợ xác minh, chẩn đoán điều gì, và chúng không thay thế nhật ký nào?

**Bài thực hành an toàn:** trên Redis thử nghiệm, tạo các tài khoản theo tập lệnh tối thiểu, dùng `ACL DRYRUN` xác nhận ca cho phép/từ chối, sau đó chạy một job dọn dẹp ở chế độ dry-run với hạn mức thấp. Kiểm tra danh sách ứng viên và log trước khi cho phép xóa dữ liệu thử nghiệm trong namespace riêng.
