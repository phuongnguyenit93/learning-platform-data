# Phân biệt xóa chủ động, hết hạn và loại bỏ do áp lực bộ nhớ trong Spring Data Redis

Trong Redis, một khóa (*key*) có thể biến mất vì ba nguyên nhân khác nhau: ứng dụng **chủ động xóa**, khóa **hết thời gian sống (TTL)**, hoặc Redis **loại bỏ khóa để giải phóng bộ nhớ (eviction)**. Cả ba đều có thể khiến lệnh `GET` trả về `nil` và Spring Data Redis trả về `null`, nhưng nguyên nhân, thời điểm, mức độ kiểm soát và cách xử lý lại khác nhau.

Hiểu rõ ba cơ chế này giúp thiết kế cache, phiên đăng nhập, mã xác thực, dữ liệu tạm và hệ thống theo dõi sự kiện mà không nhầm lẫn giữa “đã hết hạn theo nghiệp vụ” với “không còn trong Redis”.

## 1. Nhìn tổng quan: ba lý do khiến một khóa biến mất

| Tiêu chí | Xóa chủ động (*deletion*) | Hết hạn (*expiration*) | Loại bỏ do bộ nhớ (*eviction*) |
|---|---|---|---|
| Ai quyết định? | Ứng dụng hoặc người vận hành gọi lệnh xóa | Ứng dụng đặt TTL; Redis xác định khi TTL kết thúc | Redis lựa chọn khóa theo chính sách `maxmemory-policy` |
| Tác nhân trực tiếp | `DEL`, `UNLINK` hoặc thao tác xóa tương đương | `EXPIRE`, `PEXPIRE`, `SET ... EX/PX` đã thiết lập thời hạn | Áp lực bộ nhớ khi Redis áp dụng giới hạn `maxmemory` |
| Có cần TTL? | Không | Có | Không nhất thiết; tùy chính sách eviction |
| Có cần thiếu bộ nhớ? | Không | Không | Có, khi cơ chế giới hạn bộ nhớ được kích hoạt |
| Thời điểm mất hiệu lực | Khi lệnh xóa được thực thi | Khi thời điểm hết hạn đã đến | Có thể xảy ra **trước TTL** hoặc với khóa không có TTL |
| Khả năng kiểm soát | Xác định đúng khóa cần xóa | Xác định thời hạn, nhưng không bảo đảm thời điểm dọn bộ nhớ chính xác tuyệt đối | Chọn chính sách và giới hạn bộ nhớ, thường không chọn chính xác khóa bị loại |
| Redis keyevent điển hình | `del` | `expired` | `evicted` |
| Số liệu liên quan | Log/metric phía ứng dụng, sự kiện xóa nếu bật | `expired_keys` | `evicted_keys` |

Ba cơ chế **không loại trừ lẫn nhau**. Một khóa có TTL 30 phút vẫn có thể bị `DEL` sau 5 phút hoặc bị eviction sau 10 phút. Khi khóa đã bị xóa, TTL cũ của khóa cũng không còn.

## 2. Xóa chủ động: ứng dụng biết khi nào cần bỏ dữ liệu

### 2.1. `DEL` — xóa theo yêu cầu

`DEL key` xóa khóa đang tồn tại, bất kể khóa có TTL hay không. Lệnh này thường được dùng khi dữ liệu phải bị vô hiệu ngay theo nghiệp vụ, chẳng hạn:

- Người dùng đăng xuất: xóa phiên đăng nhập hiện tại.
- Bản ghi sản phẩm được sửa: xóa cache của sản phẩm để lần đọc sau lấy dữ liệu mới.
- Hủy một tác vụ: xóa trạng thái tạm không còn cần thiết.
- Thu hồi mã truy cập: bỏ mã trước thời điểm hết hạn dự kiến.

Ví dụ trong Redis CLI:

```redis
SET app:session:42 "user=42" EX 1800
TTL app:session:42
DEL app:session:42
EXISTS app:session:42
TTL app:session:42
```

Sau `DEL`, `EXISTS` trả `0` và `TTL` trả `-2` vì khóa không tồn tại. `DEL` trả về số khóa thực sự bị xóa; gọi lại với một khóa đã mất trả về `0`. Đây là thao tác có thể lặp lại an toàn theo nghĩa “khóa vẫn không tồn tại”.

Với cách hoạt động mặc định, `DEL` gỡ khóa và giải phóng cấu trúc dữ liệu của nó trong quá trình thực hiện lệnh. Xóa những cấu trúc rất lớn có thể tạo độ trễ trên luồng xử lý lệnh của Redis.

### 2.2. `UNLINK` — xóa logic ngay, thu hồi bộ nhớ về sau

`UNLINK key` tách khóa khỏi keyspace ngay lập tức, khiến ứng dụng không còn đọc được khóa đó; phần thu hồi bộ nhớ được chuyển sang xử lý bất đồng bộ khi phù hợp. Nó hữu ích khi xóa những giá trị lớn và muốn hạn chế thời gian Redis phải làm việc trong luồng xử lý lệnh.

```redis
UNLINK app:report:large
EXISTS app:report:large
```

Điểm dễ nhầm: `UNLINK` **không phải** là “đặt lịch xóa khóa vào lúc khác”. Sau khi lệnh hoàn thành, khóa đã bị xóa về mặt logic; chỉ công việc giải phóng vùng nhớ có thể tiếp tục ở nền. Vì vậy không được dùng `UNLINK` với giả định rằng lượng RAM sẽ giảm ngay lập tức.

### 2.3. Xóa với Spring Data Redis

`RedisTemplate` và `StringRedisTemplate` cung cấp các thao tác tương ứng:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionInvalidationService {

    private final StringRedisTemplate redis;

    public SessionInvalidationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean logout(String sessionId) {
        String key = "app:session:" + sessionId;
        return Boolean.TRUE.equals(redis.delete(key)); // DEL
    }

    public boolean removeLargeCachedObject(String reportId) {
        String key = "app:report:" + reportId;
        return Boolean.TRUE.equals(redis.unlink(key)); // UNLINK
    }
}
```

Ở đây giá trị `true` chỉ cho biết có khóa được gỡ ở thời điểm gọi. Nếu một tiến trình khác đã xóa khóa, giá trị `false` không nhất thiết là lỗi nghiệp vụ. Trong những đường xử lý quan trọng, hãy xác định rõ liệu yêu cầu là “khóa cuối cùng không còn tồn tại” hay “chính lệnh này phải xóa được khóa”.

Đừng nhầm thao tác xóa của Spring Data Redis với việc xóa bản ghi nguồn trong cơ sở dữ liệu quan hệ. `redis.delete(...)` chỉ tác động tới Redis; nếu Redis là cache, bản ghi trong hệ thống nguồn vẫn tồn tại và có thể được nạp lại.

## 3. Hết hạn: Redis tự làm khóa mất hiệu lực theo TTL

### 3.1. TTL diễn tả điều gì?

TTL (*time to live*) là khoảng thời gian còn lại trước khi Redis coi khóa là hết hạn. Ứng dụng có thể tạo khóa kèm TTL hoặc đặt thời hạn cho một khóa đang tồn tại:

```redis
SET app:otp:42 "837219" EX 120
SET app:cache:item:17 "{...}" PX 15000
EXPIRE app:cache:item:17 60
```

Trong ví dụ này:

- `EX 120` đặt thời hạn 120 giây ngay khi ghi giá trị.
- `PX 15000` đặt thời hạn 15.000 mili giây.
- `EXPIRE ... 60` thay thời hạn hiện có bằng 60 giây tính từ lúc gọi lệnh.

`EXPIRE` không làm khóa biến mất ngay nếu TTL mới còn dương. Nó gắn thời điểm hết hạn cho khóa. Khi đến hạn, các lần truy cập sau không còn nhận giá trị cũ; Redis cũng có cơ chế dọn khóa hết hạn trong nền.

### 3.2. Hết hạn theo thời gian khác với lúc bộ nhớ được thu hồi

Redis phối hợp hai cách xử lý khóa hết hạn:

1. **Hết hạn thụ động (*passive/lazy expiration*):** khi truy cập một khóa đã quá hạn, Redis nhận ra khóa hết hạn, loại bỏ nó và xử lý như khóa không tồn tại.
2. **Hết hạn chủ động (*active expiration*):** Redis định kỳ kiểm tra một phần các khóa có TTL và loại bỏ những khóa đã quá hạn, ngay cả khi ứng dụng chưa truy cập chúng.

Vì vậy, cần phân biệt **thời điểm khóa hết hiệu lực về mặt truy cập** với **thời điểm Redis thật sự dọn cấu trúc dữ liệu trong bộ nhớ**. Một khóa có thể đã đến hạn nhưng vẫn chiếm bộ nhớ trong thời gian ngắn trước khi được bộ dọn nền xử lý. Không thiết kế tác vụ yêu cầu sự kiện `expired` phải đến đúng tại mili giây hết hạn.

Ví dụ:

```text
10:00:00  SET app:otp:42 ... EX 120
10:02:00  TTL kết thúc; khóa không còn hợp lệ để đọc
10:02:01  Lần GET tiếp theo có thể kích hoạt xóa thụ động
           (hoặc Redis đã dọn bằng cơ chế chủ động trước đó)
```

**TTL là giới hạn hiệu lực dữ liệu, không phải đồng hồ thực thi công việc chính xác.** Nếu cần xử lý một tác vụ đúng thời điểm, hãy dùng cơ chế lập lịch/hàng đợi thích hợp; keyspace notification chỉ có thể là tín hiệu hỗ trợ.

### 3.3. Cách đọc `TTL` và `PTTL`

```redis
TTL app:otp:42
PTTL app:otp:42
```

| Kết quả | Ý nghĩa |
|---|---|
| Số không âm | Thời gian còn lại: giây với `TTL`, mili giây với `PTTL` |
| `-1` | Khóa tồn tại nhưng **không có thời hạn hết hạn** |
| `-2` | Khóa **không tồn tại**, không thể suy ra nguyên nhân mất khóa chỉ từ giá trị này |

Khóa có TTL rất ngắn có thể cho `TTL = 0` vì Redis trả số giây nguyên, dù khóa chưa hết hạn. Khi cần độ phân giải tốt hơn, dùng `PTTL`.

Để bỏ thời hạn của một khóa mà vẫn giữ giá trị:

```redis
PERSIST app:cache:item:17
TTL app:cache:item:17
```

Nếu `PERSIST` thành công, `TTL` trả `-1`. Điều này **không bảo vệ** khóa khỏi eviction nếu Redis dùng chính sách thuộc nhóm `allkeys-*`.

### 3.4. Những thao tác ảnh hưởng đến TTL

- `EXPIRE`/`PEXPIRE` gán hoặc thay thế thời hạn của khóa hiện có; lệnh có thể thất bại nếu khóa không tồn tại.
- Ghi đè khóa bằng `SET` thông thường thường xóa TTL trước đó, trừ khi dùng cách ghi giữ TTL được Redis hỗ trợ. Đây là nguyên nhân phổ biến khiến cache vô tình tồn tại mãi.
- Thay đổi nội dung ngay trong cấu trúc dữ liệu, chẳng hạn tăng bộ đếm bằng `INCR`, thông thường giữ nguyên TTL của khóa.
- `DEL` hoặc `UNLINK` làm mất cả khóa lẫn TTL; tạo khóa mới cùng tên về sau là một vòng đời mới.
- Lệnh đặt thời hạn bằng 0 hoặc một thời hạn đã qua có thể dẫn tới xóa khóa ngay; trường hợp này có thể phát sinh sự kiện `del` thay vì `expired`.

Nếu toàn bộ yêu cầu là “ghi giá trị và cho hết hạn sau 15 phút”, nên dùng một thao tác ghi **kèm TTL** thay vì tách `SET` và `EXPIRE` thành hai lệnh. Hai lệnh độc lập để lại khoảng trống nếu tiến trình bị dừng giữa chừng, khiến khóa có giá trị nhưng không có TTL.

### 3.5. Ghi và đọc TTL bằng Spring Data Redis

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OneTimeCodeStore {

    private static final Duration CODE_TTL = Duration.ofMinutes(2);
    private final StringRedisTemplate redis;

    public OneTimeCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String userId, String hashedCode) {
        // Redis ghi giá trị và TTL trong một thao tác.
        redis.opsForValue().set("app:otp:" + userId, hashedCode, CODE_TTL);
    }

    public String find(String userId) {
        return redis.opsForValue().get("app:otp:" + userId);
    }

    public Long remainingSeconds(String userId) {
        return redis.getExpire("app:otp:" + userId, TimeUnit.SECONDS);
    }

    public boolean extend(String userId) {
        return Boolean.TRUE.equals(
            redis.expire("app:otp:" + userId, Duration.ofMinutes(2))
        );
    }

    public boolean cancel(String userId) {
        return Boolean.TRUE.equals(redis.delete("app:otp:" + userId));
    }
}
```

Chú ý sự khác nhau giữa `extend(...)` và `cancel(...)`: một thao tác **đặt lại thời hạn** của khóa còn tồn tại, thao tác kia **xóa khóa ngay**. Sau khi `find(...)` trả `null`, không thể kết luận khóa bị xóa thủ công hay hết hạn; eviction cũng tạo cùng biểu hiện.

Với Redis repositories, Spring Data Redis còn hỗ trợ TTL theo mô hình đối tượng, chẳng hạn đặt `@RedisHash(timeToLive = 900)` trên lớp hoặc dùng thuộc tính `@TimeToLive`. Đây vẫn là cách thiết lập thời gian hết hạn của Redis. Annotation không có nghĩa đối tượng được miễn eviction hoặc sự kiện hết hạn luôn được nhận đúng lúc.

## 4. Eviction: Redis bỏ dữ liệu khi bị áp lực bộ nhớ

### 4.1. Eviction được kích hoạt như thế nào?

Redis có thể được cấu hình giới hạn bộ nhớ bằng `maxmemory`. Khi cần thêm bộ nhớ trong tình trạng vượt ngưỡng, Redis áp dụng `maxmemory-policy` để chọn khóa loại bỏ hoặc trả lỗi cho một số lệnh ghi nếu chính sách không cho phép eviction.

Ví dụ cấu hình ở phía Redis:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Đây là cấu hình máy chủ Redis, không phải TTL do Spring Data Redis đặt cho từng khóa. Các giá trị này chỉ mang tính minh họa; chọn hạn mức theo bộ nhớ sẵn có, loại dữ liệu và cách triển khai thực tế.

Đặc trưng của eviction:

- Khóa có thể bị xóa **khi TTL vẫn còn**. Ví dụ TTL còn 25 phút nhưng hệ thống cần thu hồi bộ nhớ ngay.
- Khóa **không có TTL** cũng có thể bị loại nếu chính sách `allkeys-*` cho phép.
- Việc chọn khóa phụ thuộc chính sách và thông tin Redis thu thập; không nên xem LRU/LFU như một cam kết tuyệt đối rằng khóa cụ thể nào chắc chắn được giữ.
- Eviction giải quyết áp lực bộ nhớ cho Redis. Nó không mang ý nghĩa dữ liệu đã hết hiệu lực theo quy tắc nghiệp vụ.

Giới hạn `maxmemory` và số liệu bộ nhớ Redis không đồng nhất hoàn toàn với RAM mà hệ điều hành quan sát (ví dụ có bộ đệm và chi phí của bộ cấp phát bộ nhớ). Không dựa vào một con số duy nhất để kết luận hệ thống sẽ không bao giờ vượt ngưỡng RAM vật lý.

### 4.2. Các chính sách `maxmemory-policy`

| Chính sách | Tập khóa có thể bị chọn | Ý tưởng chọn khóa |
|---|---|---|
| `noeviction` | Không tự loại khóa vì bộ nhớ | Một số lệnh ghi cần thêm bộ nhớ có thể nhận lỗi OOM |
| `allkeys-lru` | Tất cả khóa | Ưu tiên khóa ít được sử dụng gần đây theo xấp xỉ LRU |
| `allkeys-lfu` | Tất cả khóa | Ưu tiên khóa ít được truy cập thường xuyên theo xấp xỉ LFU |
| `allkeys-random` | Tất cả khóa | Chọn ngẫu nhiên |
| `volatile-lru` | Chỉ khóa có TTL | Xấp xỉ LRU trong nhóm có TTL |
| `volatile-lfu` | Chỉ khóa có TTL | Xấp xỉ LFU trong nhóm có TTL |
| `volatile-random` | Chỉ khóa có TTL | Chọn ngẫu nhiên trong nhóm có TTL |
| `volatile-ttl` | Chỉ khóa có TTL | Ưu tiên khóa có thời hạn hết hạn gần hơn |

**`volatile-*` không có nghĩa Redis chờ đến khi khóa hết TTL.** Redis vẫn có thể xóa khóa trước hạn; TTL chỉ là điều kiện để khóa được chọn. Nếu không có đủ khóa mang TTL để loại bỏ, các chính sách này có thể dẫn tới lỗi ghi tương tự `noeviction`.

**`noeviction` không tắt expiration hoặc xóa thủ công.** Khóa hết TTL vẫn bị xử lý; `DEL`/`UNLINK` vẫn hoạt động. Nó chỉ không tự loại khóa đang hợp lệ do chính sách áp lực bộ nhớ.

LRU (*least recently used*) dựa trên mức độ truy cập gần đây; LFU (*least frequently used*) dựa trên tần suất truy cập đã được Redis ước lượng. Các thuật toán Redis sử dụng thông tin xấp xỉ và lấy mẫu, không phải thứ tự tuyệt đối của mọi khóa.

### 4.3. Ví dụ: TTL chưa hết nhưng dữ liệu đã bị eviction

Giả sử một cache được đặt TTL 30 phút, còn Redis dùng `allkeys-lru`:

```text
12:00  SET app:cache:product:17 ... EX 1800
12:05  Redis chịu áp lực bộ nhớ; khóa ít được truy cập bị chọn
12:05  app:cache:product:17 bị eviction, dù TTL còn khoảng 25 phút
12:06  GET app:cache:product:17 -> nil
12:06  Ứng dụng nạp lại dữ liệu từ nguồn và ghi cache mới
```

Nếu hệ thống chỉ nhìn kết quả `GET -> nil`, nó không thể phân biệt sự kiện này với một cache miss do hết hạn hoặc do ứng dụng vừa xóa cache. Vì vậy luồng đọc cache cần **xử lý được trường hợp không có dữ liệu tại bất kỳ thời điểm nào**, ngay cả khi vừa đặt TTL thành công.

### 4.4. Nên chọn chính sách nào?

| Tình huống | Hướng cân nhắc | Lý do |
|---|---|---|
| Redis chủ yếu làm cache, có thể tái tạo dữ liệu | `allkeys-lru` hoặc `allkeys-lfu` | Cho phép mọi khóa cache cạnh tranh bộ nhớ |
| Chỉ một nhóm khóa được phép hy sinh, nhóm đó đều có TTL | Xem xét `volatile-*` | Tách nhóm đủ điều kiện eviction, nhưng cần tính đến nguy cơ lỗi ghi khi nhóm này không đủ |
| Redis chứa dữ liệu không được phép mất vì áp lực bộ nhớ | `noeviction` **cùng thiết kế dung lượng và lưu trữ phù hợp** | Tránh chủ động loại khóa vì thiếu bộ nhớ; đổi lại ứng dụng phải xử lý lỗi ghi và Redis không thay thế hệ thống lưu trữ bền vững |
| Muốn ưu tiên bỏ khóa có hạn gần nhất | `volatile-ttl` | Dùng TTL như tín hiệu lựa chọn, không có nghĩa đợi đến hạn mới xóa |

Khi một Redis instance chứa cả cache có thể tái tạo lẫn dữ liệu phiên hoặc trạng thái quan trọng, dùng cùng một chính sách cho tất cả có thể tạo tác động khó dự đoán. Cân nhắc tách workload hoặc instance theo mức độ chấp nhận mất dữ liệu và đặc điểm bộ nhớ.

## 5. Quan hệ giữa ba cơ chế qua các tình huống

### Tình huống A: Người dùng đăng xuất trước hạn

Phiên được tạo với TTL 1 giờ. Sau 10 phút, ứng dụng gọi `DEL` hoặc `UNLINK` khi người dùng đăng xuất. Phiên biến mất **do xóa chủ động**, không cần đợi đủ 1 giờ. Đây là quyết định nghiệp vụ và phải được thực hiện ngay khi đăng xuất thành công.

### Tình huống B: Mã OTP hết hai phút mà không được sử dụng

Ứng dụng ghi mã với TTL 120 giây. Khi đủ thời gian, Redis coi mã là hết hạn và các lần đọc sau không còn thấy mã. Đây là **expiration**; không đòi hỏi thiếu bộ nhớ, cũng không cần ứng dụng gửi lệnh `DEL` đúng vào giây thứ 120.

### Tình huống C: Cache chưa hết hạn nhưng Redis đầy

Một khóa cache có TTL 30 phút bị Redis loại sau 3 phút theo `allkeys-lfu`. Đây là **eviction**; nội dung có thể vẫn còn “mới” theo TTL nhưng Redis buộc phải dành chỗ cho các khóa khác. Ứng dụng phải xử lý cache miss và tái tạo dữ liệu nếu phù hợp.

### Tình huống D: Chọn `volatile-lru` nhưng toàn bộ khóa đều không có TTL

Redis không có ứng viên đủ điều kiện eviction. Khi cần thêm bộ nhớ và đã vượt hạn mức, một số lệnh ghi có thể thất bại với lỗi thiếu bộ nhớ. Đừng hiểu `volatile-lru` là mọi khóa đều được bảo vệ hoặc Redis sẽ tự động xóa dữ liệu cũ bất kể có TTL hay không.

### Tình huống E: Đã xóa khóa, sau đó tiến trình khác tạo lại cùng tên

Một tác vụ gọi `DEL app:cache:item:17`, nhưng tác vụ khác lập tức `SET app:cache:item:17` với giá trị mới. Quan sát `EXISTS = 1` sau đó **không chứng minh lệnh `DEL` thất bại**. Đó có thể là một vòng đời khóa mới. Khi cần chống race condition, hãy xác định rõ yêu cầu đồng bộ hóa và dùng thao tác nguyên tử hoặc cơ chế phiên bản hóa thích hợp.

## 6. Thiết kế Spring Data Redis để chịu được cả expiration và eviction

Đối với cache có thể nạp lại, ba hành vi thường gắn với ba nhu cầu khác nhau:

```text
Ứng dụng ghi cache ----- SET k v EX <ttl> ------> Redis
      |                                           |
      | dữ liệu nguồn thay đổi                    | TTL kết thúc
      +----------------- DEL k ------------------>+--> khóa biến mất
                                                  |
                                                  | áp lực maxmemory
                                                  +--> khóa có thể biến mất sớm

Ứng dụng đọc GET k --> có giá trị: dùng cache
                  \--> nil: lấy dữ liệu nguồn rồi ghi cache lại
```

Một cách đóng gói thao tác cache với Spring Data Redis:

```java
import java.time.Duration;
import java.util.function.Supplier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductCache {

    private static final Duration CACHE_TTL = Duration.ofMinutes(20);
    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String getOrLoad(String productId, Supplier<String> loadFromDatabase) {
        String key = "app:cache:product:" + productId;
        String cached = redis.opsForValue().get(key);
        if (cached != null) {
            return cached;
        }

        // Cache miss có thể do chưa từng ghi, đã xóa, hết TTL hoặc eviction.
        String loaded = loadFromDatabase.get();
        if (loaded != null) {
            redis.opsForValue().set(key, loaded, CACHE_TTL);
        }
        return loaded;
    }

    public void invalidate(String productId) {
        redis.delete("app:cache:product:" + productId);
    }
}
```

Đây là ví dụ cho dữ liệu cache có thể tái tạo. Trong hệ thống thật, cần xem xét thêm cache stampede (nhiều yêu cầu cùng tái tạo một khóa), cập nhật đồng thời và thứ tự giữa ghi dữ liệu nguồn với việc xóa cache. Việc ghi lại cache cũng có thể gặp lỗi OOM nếu Redis dùng `noeviction` hoặc thiếu ứng viên eviction; chính sách xử lý lỗi phải phù hợp với việc cache có bắt buộc cho request hay không.

Với dữ liệu xác thực như OTP, TTL giới hạn thời gian sử dụng nhưng **không bảo đảm dữ liệu tồn tại đủ đến hạn** nếu có eviction. Nếu mã phải chỉ được tiêu thụ một lần, chuỗi `GET` rồi `DEL` ở hai lệnh riêng còn có nguy cơ race giữa các request. Có thể dùng thao tác nguyên tử như `GETDEL` khi phiên bản Redis và API đang dùng hỗ trợ, hoặc Lua script phù hợp để tránh hai request cùng tiêu thụ một mã.

## 7. Quan sát và chẩn đoán khóa biến mất

### 7.1. Bắt đầu từ tình trạng khóa và cấu hình Redis

Các lệnh hữu ích để quan sát:

```redis
EXISTS app:cache:product:17
TTL app:cache:product:17
PTTL app:cache:product:17
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
```

Tập trung vào các chỉ số:

- `expired_keys`: số khóa Redis đã xử lý hết hạn; tăng nhanh khi nhiều dữ liệu tự hết TTL.
- `evicted_keys`: số khóa bị loại do chính sách áp lực bộ nhớ; tăng là tín hiệu cần xem xét dung lượng hoặc eviction policy.
- `used_memory` và `maxmemory`: giúp đánh giá Redis đang gần ngưỡng bộ nhớ tới đâu.
- `keyspace_hits` và `keyspace_misses`: thể hiện hành vi truy cập cache, nhưng **không tự chỉ ra** nguyên nhân cụ thể của mỗi cache miss.

Các thống kê này chủ yếu mô tả toàn instance theo khoảng thời gian quan sát, không xác định chính xác nguyên nhân mất của từng key. `TTL = -2` hoặc `EXISTS = 0` cũng không đủ để khẳng định “đã hết hạn”. Muốn chẩn đoán sâu hơn cần phối hợp log thao tác của ứng dụng, cấu hình Redis, metric và sự kiện được ghi nhận trước đó.

### 7.2. Keyspace notifications: phân biệt sự kiện nếu đã bật

Redis có thể phát sự kiện theo loại thao tác, ví dụ:

| Keyevent | Diễn giải thường gặp |
|---|---|
| `del` | Khóa bị xóa bởi lệnh xóa hoặc thao tác có hiệu lực xóa tương ứng |
| `expired` | Redis phát hiện và xóa khóa do hết hạn |
| `evicted` | Redis loại khóa vì bộ nhớ |

Ví dụ cấu hình trên một instance thử nghiệm:

```redis
CONFIG SET notify-keyspace-events Egxe
PSUBSCRIBE __keyevent@0__:*
```

Trong chuỗi cấu hình, `E` bật kiểu thông báo keyevent, `g` gồm sự kiện thông dụng như `del`, `x` là expired và `e` là evicted. Tên kênh `@0` chỉ database 0; môi trường khác cần chọn database và cấu hình phù hợp. Redis được quản lý bởi nhà cung cấp dịch vụ có thể không cho phép thay đổi `CONFIG` động.

**Keyspace notifications dùng Pub/Sub, không phải nhật ký bền vững.** Subscriber có thể bỏ lỡ sự kiện khi ngắt kết nối, cấu hình chưa bật hoặc sự kiện diễn ra trước khi đăng ký. Sự kiện `expired` không nhất thiết phát đúng tại thời điểm TTL về 0; Redis phát khi khóa thực sự bị loại vì hết hạn. Không dùng thông báo này như nguồn duy nhất để quyết định một giao dịch tài chính, xóa dữ liệu bền vững hoặc bảo đảm xử lý đúng một lần.

Trong Spring Data Redis, listener cho sự kiện hết hạn có thể được xây dựng bằng `RedisMessageListenerContainer`; Redis repositories cũng có cơ chế lắng nghe expiration events. Những listener này vẫn chịu tính chất best effort của Pub/Sub. Nếu quá trình nghiệp vụ cần bảo đảm xử lý, hãy dùng hàng đợi/lịch xử lý bền vững và lưu trạng thái trong nguồn dữ liệu thích hợp.

### 7.3. Bảng truy tìm nguyên nhân

| Triệu chứng quan sát | Nguyên nhân cần kiểm tra | Cách xử lý hướng tới |
|---|---|---|
| Khóa biến mất ngay sau logout hoặc cập nhật dữ liệu | `delete`, `unlink`, lệnh invalidation, job dọn cache | Kiểm tra luồng gọi xóa và log nghiệp vụ |
| Khóa thường mất sau khoảng thời gian cố định | TTL qua `SET ... EX`, `expire`, repository annotation | Kiểm tra giá trị TTL, thao tác ghi lại và quy tắc hết hạn |
| Khóa mất sớm, nhất là khi tải hoặc bộ nhớ tăng | Eviction | Xem `evicted_keys`, `maxmemory`, chính sách eviction và phân bố kích thước khóa |
| TTL đột nhiên thành `-1` sau cập nhật giá trị | Lệnh ghi đè đã xóa TTL | Ghi giá trị kèm TTL trong cùng thao tác hoặc chủ động giữ TTL theo thiết kế |
| Ghi dữ liệu trả lỗi OOM dù còn khóa trong Redis | `noeviction`, hoặc `volatile-*` không đủ ứng viên để loại | Kiểm tra policy, TTL của dữ liệu, giới hạn bộ nhớ và sức chứa |
| Không nhận được event `expired` | Chưa bật keyspace notifications, subscriber gián đoạn, khóa bị xóa theo nguyên nhân khác | Kiểm tra cấu hình/sự kiện; tránh dựa vào event để bảo đảm nghiệp vụ |

## 8. Những nhầm lẫn cần tránh

**“Đã đặt TTL thì chắc chắn khóa tồn tại cho đến lúc hết TTL.”** Sai. Eviction và xóa chủ động có thể loại khóa sớm hơn. TTL chỉ quy định lúc Redis không còn coi giá trị là hợp lệ vì thời gian.

**“Redis đầy bộ nhớ sẽ xóa khóa đã hết hạn trước, nên không ảnh hưởng khóa chưa hết TTL.”** Không thể giả định như vậy. Redis có cơ chế dọn expired keys riêng và chính sách eviction riêng; tùy chính sách, khóa hợp lệ vẫn có thể bị chọn loại.

**“`GET` trả `null` nghĩa là khóa vừa hết hạn.”** Sai. Có thể chưa từng tồn tại, bị xóa chủ động, bị eviction hoặc đã bị xử lý hết hạn trước đó. Trên đường đọc cache, hãy xem đó là cache miss và xử lý theo thiết kế.

**“`volatile-lru` bảo vệ tất cả khóa có TTL khỏi mất dữ liệu.”** Ngược lại, chính những khóa có TTL mới là ứng viên eviction. Khóa không có TTL không nằm trong nhóm ứng viên của policy này.

**“`noeviction` làm Redis giữ khóa mãi mãi.”** Sai. TTL và lệnh xóa vẫn có hiệu lực. Đồng thời, `noeviction` có thể khiến thao tác ghi thất bại nếu thiếu bộ nhớ.

**“`UNLINK` là xóa chậm, ứng dụng có thể đọc khóa thêm một lúc.”** Sai. Khóa bị gỡ khỏi không gian khóa ngay; chỉ việc giải phóng bộ nhớ có thể được xử lý bất đồng bộ.

**“Bật keyspace notifications là đủ để xây dựng lịch xử lý đảm bảo.”** Sai. Pub/Sub không lưu lại thông báo cho subscriber vắng mặt; sự kiện expiration cũng không có cam kết phát đúng tại thời điểm TTL về 0.

## 9. Quy tắc chọn thao tác trong ứng dụng

1. **Cần bỏ dữ liệu ngay vì nghiệp vụ đã thay đổi?** Gọi `delete` (`DEL`) hoặc `unlink` (`UNLINK`); với đối tượng lớn, cân nhắc `UNLINK` để giảm thời gian thu hồi bộ nhớ trong luồng xử lý lệnh.
2. **Cần dữ liệu chỉ hợp lệ trong một khoảng thời gian?** Ghi kèm TTL bằng `opsForValue().set(key, value, Duration)` hoặc cấu hình TTL repository phù hợp. Thiết kế đầu đọc chấp nhận khóa biến mất sớm.
3. **Cần giữ Redis trong ngân sách RAM?** Cấu hình `maxmemory` và `maxmemory-policy` ở máy chủ theo tính chất dữ liệu; monitor `evicted_keys` và lỗi OOM. Chính sách eviction không thay thế TTL nghiệp vụ.
4. **Cần phân tích vì sao một khóa biến mất?** Kết hợp log chủ động xóa, chỉ số expiration/eviction, TTL và sự kiện nếu có. Không suy luận nguyên nhân chỉ từ `GET`/`EXISTS` sau khi khóa đã mất.

Điểm cần ghi nhớ khi dùng Spring Data Redis là ba cơ chế tác động ở **ba cấp độ khác nhau**: ứng dụng ra lệnh xóa, ứng dụng khai báo hạn sử dụng, còn Redis quản lý bộ nhớ theo chính sách toàn instance. Thiết kế đúng phải cho phép chúng xảy ra độc lập và xử lý an toàn khi một khóa không còn hiện diện.
