# Thêm, cập nhật điểm và tăng điểm của thành viên

Redis **Sorted Set** (còn gọi là **ZSet**, tập có thứ tự) lưu các **thành viên duy nhất** (*member*), mỗi thành viên được gắn với một **điểm số** (*score*). Redis tự duy trì thứ tự theo điểm, vì vậy cấu trúc này đặc biệt hữu ích khi triển khai bảng xếp hạng, hệ thống ưu tiên, danh sách có thứ tự thời gian hoặc những tập dữ liệu thường được truy vấn theo khoảng điểm.

Trong Spring Data Redis, ba nhu cầu thường gặp là:

1. **Thêm thành viên kèm điểm khởi tạo**: dùng lệnh Redis **ZADD**, tương ứng với **opsForZSet().add(...)**.
2. **Đặt lại điểm tuyệt đối cho thành viên đã tồn tại**: vẫn dùng **ZADD**, vì mặc định lệnh này thêm mới hoặc cập nhật score.
3. **Cộng hoặc trừ một lượng điểm**: dùng **ZINCRBY**, tương ứng với **opsForZSet().incrementScore(...)**.

Sự khác biệt giữa **đặt score bằng 100** và **cộng thêm 100 vào score hiện tại** là điểm cốt lõi. Hai cách ghi có ý nghĩa nghiệp vụ và hành vi đồng thời khác nhau.

## 1. Member và score trong Sorted Set

Giả sử xây bảng xếp hạng một tuần:

~~~text
Redis key: leaderboard:2026-W46
Redis TYPE: zset

member       score
-----------  -----
user:an       120
user:binh      90
user:chi      110
~~~

Các khái niệm:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Key | Địa chỉ của cả Sorted Set trong Redis | leaderboard:2026-W46 |
| Member | Phần tử duy nhất trong tập, được nhận diện theo byte | user:an |
| Score | Giá trị số dùng để sắp thứ tự | 120 |
| Rank | Vị trí được tính từ thứ tự score, bắt đầu từ 0 | 0 |
| Cardinality | Tổng số member trong tập | 3 |

Redis không lưu thêm một danh sách thứ tự riêng do ứng dụng quản lý. Khi score đổi, thứ tự của Sorted Set được cập nhật theo score mới.

Khởi tạo ví dụ với Redis CLI:

~~~redis
ZADD leaderboard:2026-W46 120 user:an
ZADD leaderboard:2026-W46 90 user:binh
ZADD leaderboard:2026-W46 110 user:chi

TYPE leaderboard:2026-W46
ZCARD leaderboard:2026-W46
ZRANGE leaderboard:2026-W46 0 -1 WITHSCORES
~~~

Kết quả của **TYPE** là **zset**, **ZCARD** bằng **3**. Câu truy vấn **ZRANGE** thông thường trả member theo score **tăng dần**:

~~~text
user:binh   90
user:chi   110
user:an    120
~~~

Nếu muốn xem điểm cao trước:

~~~redis
ZRANGE leaderboard:2026-W46 0 -1 REV WITHSCORES
~~~

Tùy phiên bản Redis, mã nguồn cũ có thể sử dụng **ZREVRANGE** cho truy vấn giảm dần. Với Redis hỗ trợ cú pháp **ZRANGE ... REV**, hai cách biểu diễn cùng ý tưởng sắp theo chiều giảm.

### 1.1. Member chỉ duy nhất trong phạm vi một key

Cùng một ID người dùng có thể xuất hiện trong nhiều bảng:

~~~text
leaderboard:daily:2026-11-12  -> user:an có 15 điểm
leaderboard:weekly:2026-W46  -> user:an có 120 điểm
leaderboard:season:2026      -> user:an có 920 điểm
~~~

Tính duy nhất của member áp dụng **trong từng Sorted Set**, không phải toàn bộ Redis.

Nên sử dụng định danh ổn định như **user:42**, **player:ABC**, **team:blue**. Nếu member là tên hiển thị có thể thay đổi, việc đổi tên có thể khiến Redis coi đó là một member khác.

### 1.2. Khi nhiều member bằng điểm

Nếu hai member có score bằng nhau, Redis sắp chúng theo thứ tự từ điển của biểu diễn byte member. Chiều đảo ngược sẽ đảo thứ tự tương ứng.

~~~redis
ZADD rank:tie 100 user:an 100 user:binh 100 user:chi
ZRANGE rank:tie 0 -1 WITHSCORES
ZRANGE rank:tie 0 -1 REV WITHSCORES
~~~

Không nên coi thứ tự khi bằng điểm là “ai đạt điểm trước được xếp trên”. Sorted Set không tự ghi lại thời điểm member đạt score. Nếu nghiệp vụ muốn người đến trước thắng khi đồng điểm hoặc muốn đồng hạng, phải định nghĩa quy tắc tie-break riêng.

## 2. Thêm thành viên bằng ZADD

Cú pháp Redis:

~~~redis
ZADD key score member [score member ...]
~~~

Ví dụ:

~~~redis
ZADD leaderboard:week 120 user:an
ZADD leaderboard:week 90 user:binh
ZADD leaderboard:week 110 user:chi
~~~

Có thể thêm nhiều member bằng một lệnh:

~~~redis
ZADD leaderboard:week 120 user:an 90 user:binh 110 user:chi
~~~

Nếu key chưa tồn tại, **ZADD tạo một Sorted Set mới**. Nếu key tồn tại nhưng là kiểu Redis khác như String hoặc Hash, Redis sẽ trả lỗi **WRONGTYPE**.

### 2.1. ZADD trả về số thành viên mới

Mặc định, Redis trả về **số member được thêm mới**, không phải số score đã thay đổi.

~~~redis
ZADD demo:ranking 10 alice 20 bob
# 2: có hai member được thêm

ZADD demo:ranking 30 alice
# 0: alice đã tồn tại

ZCARD demo:ranking
# 2: vẫn chỉ có hai member

ZSCORE demo:ranking alice
# "30": score đã được cập nhật
~~~

Điểm dễ nhầm: kết quả **0** của lần gọi ZADD thứ hai **không có nghĩa lệnh thất bại**. Nó có nghĩa không có member mới; score của member hiện hữu vẫn có thể đã thay đổi.

Muốn đếm cả việc score bị thay đổi, Redis cung cấp tùy chọn **CH**, được giải thích ở phần sau.

### 2.2. Một lệnh ZADD có thể thêm nhiều cặp

Lệnh thêm ba member bằng một ZADD là một thao tác Redis, khác với ứng dụng gửi ba ZADD rời rạc. Gộp nhiều cặp giúp giảm round-trip và thực hiện việc thêm/cập nhật trong cùng một lệnh.

Tuy nhiên, một ZADD chỉ thao tác trên **một key Sorted Set**. Nó không biến các cập nhật tới key Hash, String hoặc database bên ngoài thành một transaction duy nhất.

## 3. Đặt lại điểm tuyệt đối: dùng ZADD lần nữa

ZADD mặc định có hành vi **upsert theo member**:

- Member chưa tồn tại: thêm member với score được chỉ định.
- Member đã tồn tại: **thay score cũ bằng score mới**.

~~~redis
ZADD leaderboard:week 90 user:binh
ZSCORE leaderboard:week user:binh
# "90"

ZADD leaderboard:week 125 user:binh
ZSCORE leaderboard:week user:binh
# "125"
~~~

Kết quả là **125**, không phải **90 + 125 = 215**.

Cập nhật tuyệt đối phù hợp khi:

- Điểm tổng đã được tính từ database hoặc nguồn dữ liệu đáng tin cậy.
- Cần khôi phục bảng xếp hạng từ snapshot.
- Quản trị viên sửa điểm thành một giá trị xác định.
- Score biểu diễn một timestamp, một mức ưu tiên hoặc giá trị đo đã biết.
- Một batch đồng bộ cần thiết lập score cuối cùng cho nhiều member.

Ví dụ, database xác nhận điểm hiện tại của người chơi là 135:

~~~redis
ZADD leaderboard:week 135 user:binh
~~~

Gọi lại cùng lệnh có thể giữ nguyên kết quả cuối nếu không có thay đổi cạnh tranh. Tuy nhiên, nếu tiến trình khác vừa đặt 140, một snapshot cũ tiếp tục ZADD 135 sẽ ghi đè 140 thành 135. **ZADD không tự biết score nào mới hơn về mặt nghiệp vụ.**

### 3.1. Đặt điểm không đồng nghĩa cộng điểm

Nếu muốn người chơi nhận **thêm 10 điểm**, lệnh sau sai ý định:

~~~redis
ZADD leaderboard:week 10 user:binh
~~~

Lệnh này đặt điểm user:binh bằng **10**.

Lệnh phù hợp là:

~~~redis
ZINCRBY leaderboard:week 10 user:binh
~~~

Cần phân biệt rõ API trong service để tránh nhầm. Ví dụ đặt tên phương thức **setAbsoluteScore** khi dùng ZADD và **addPoints** khi dùng ZINCRBY.

## 4. Cộng hoặc trừ điểm bằng ZINCRBY

Cú pháp:

~~~redis
ZINCRBY key increment member
~~~

Ví dụ:

~~~redis
ZADD leaderboard:week 90 user:binh

ZINCRBY leaderboard:week 10 user:binh
# "100"

ZINCRBY leaderboard:week 25 user:binh
# "125"
~~~

ZINCRBY lấy score hiện tại của member, cộng delta và trả về **score mới**. Đối với thao tác này, member không cần phải được khởi tạo bằng ZADD từ trước.

### 4.1. Thành viên chưa tồn tại

~~~redis
ZINCRBY leaderboard:week 15 user:new
# "15"

ZSCORE leaderboard:week user:new
# "15"
~~~

Nếu member chưa có, Redis coi điểm ban đầu là 0 và tạo member với score bằng increment.

Hành vi này thuận tiện cho hệ thống tích lũy điểm theo sự kiện. Nhưng nếu chỉ người đã đăng ký mới được nhận điểm, ứng dụng cần ràng buộc quy trình đăng ký; việc ZINCRBY tự tạo member có thể không phù hợp.

### 4.2. Delta âm dùng để giảm điểm

~~~redis
ZADD leaderboard:week 125 user:binh

ZINCRBY leaderboard:week -20 user:binh
# "105"

ZINCRBY leaderboard:week -5 user:binh
# "100"
~~~

Redis cho phép score âm. Nếu nghiệp vụ cấm điểm âm, hãy thực hiện kiểm tra score hiện tại và phép trừ **trong một cơ chế nguyên tử**, không đơn thuần đọc điểm ở Java rồi trừ sau đó vì nhiều request có thể đan xen.

### 4.3. Tăng score là một lệnh nguyên tử

Giả sử user có 90 điểm và hai request đến đồng thời:

~~~text
Request A: thưởng +10
Request B: thưởng +20
~~~

Nếu cả hai lệnh ZINCRBY thực thi thành công đúng một lần, điểm cuối là **120**, bất kể lệnh nào đến trước.

Ngược lại, cách ứng dụng tự làm:

~~~text
A: ZSCORE -> 90          B: ZSCORE -> 90
A: tính 90 + 10          B: tính 90 + 20
A: ZADD 100              B: ZADD 110
~~~

có thể cho điểm cuối chỉ **110**. Một lần thưởng bị mất vì cả hai luồng đọc điểm cũ. Dùng **ZINCRBY** giúp Redis thực hiện đọc–cộng–ghi trong một lệnh duy nhất.

### 4.4. Atomicity không đồng nghĩa xử lý sự kiện đúng một lần

Nếu Redis đã thực thi ZINCRBY nhưng kết nối rớt trước khi trả phản hồi, ứng dụng có thể nhìn thấy timeout dù điểm đã tăng. Retry cùng delta sẽ có nguy cơ cộng **lần thứ hai**.

Cần phân biệt:

- **Atomicity:** một lệnh ZINCRBY không bị mất cập nhật bởi một lệnh ZINCRBY đồng thời khác.
- **Idempotency:** cùng một sự kiện nghiệp vụ được phát lại không bị áp dụng nhiều lần.
- **Delivery:** hệ thống message có thể gửi lại sự kiện khi chưa nhận được xác nhận.

ZINCRBY giải quyết vấn đề đầu tiên. Hai vấn đề còn lại cần cơ chế nhận diện sự kiện và xác nhận xử lý phù hợp.

## 5. Thực hành theo dõi thay đổi score và rank

Khởi tạo:

~~~redis
ZADD leaderboard:demo 120 user:an 90 user:binh 110 user:chi
ZRANGE leaderboard:demo 0 -1 REV WITHSCORES
~~~

Khi đó thứ tự giảm dần:

| Thứ hạng giao diện | Member | Score |
|---:|---|---:|
| 1 | user:an | 120 |
| 2 | user:chi | 110 |
| 3 | user:binh | 90 |

Tiếp tục cập nhật **điểm tuyệt đối**:

~~~redis
ZADD leaderboard:demo 115 user:binh
~~~

| Thứ hạng giao diện | Member | Score |
|---:|---|---:|
| 1 | user:an | 120 |
| 2 | user:binh | 115 |
| 3 | user:chi | 110 |

Sau đó tăng thêm 15:

~~~redis
ZINCRBY leaderboard:demo 15 user:binh
~~~

| Thứ hạng giao diện | Member | Score |
|---:|---|---:|
| 1 | user:binh | 130 |
| 2 | user:an | 120 |
| 3 | user:chi | 110 |

Redis tự cập nhật thứ tự theo score mới. Không cần tải toàn bộ danh sách về Java để sort rồi ghi lại.

Để xem điểm và rank:

~~~redis
ZSCORE leaderboard:demo user:binh
# "130"

ZREVRANK leaderboard:demo user:binh
# 0: vị trí cao nhất theo score giảm dần

ZRANK leaderboard:demo user:binh
# 2: vị trí theo score tăng dần
~~~

**Rank của Redis bắt đầu từ 0.** Nếu giao diện muốn hiện “hạng 1”, có thể hiển thị **reverseRank + 1** khi member có tồn tại. Nếu member vắng mặt, ZSCORE hoặc ZREVRANK có thể trả nil; không nên coi nil là rank 0.

## 6. Các tùy chọn ZADD để kiểm soát cập nhật

Không phải lúc nào một lần ZADD cũng được phép thêm mới hoặc ghi đè score hiện hữu. Redis cung cấp các tùy chọn điều kiện:

| Tùy chọn | Ý nghĩa | Tình huống |
|---|---|---|
| Không có | Thêm mới hoặc đặt lại score | Đồng bộ điểm tuyệt đối |
| **NX** | Chỉ thêm member chưa tồn tại | Điểm khởi tạo một lần |
| **XX** | Chỉ cập nhật member đã có | Không tự tạo người tham gia |
| **GT** | Chỉ thay score hiện hữu nếu score mới lớn hơn; vẫn có thể thêm member mới | Giữ kỷ lục cao nhất |
| **LT** | Chỉ thay score hiện hữu nếu score mới nhỏ hơn; vẫn có thể thêm member mới | Giữ kết quả thấp nhất |
| **CH** | Đếm cả member mới và member có score thay đổi | Quan sát số thay đổi |
| **INCR** | Cộng score thay vì đặt giá trị tuyệt đối | Chức năng tương tự ZINCRBY |

Khả năng hỗ trợ các tùy chọn, đặc biệt GT/LT, phụ thuộc phiên bản Redis. Một số tùy chọn không được kết hợp tùy tiện; cần theo đúng cú pháp Redis đang dùng.

### 6.1. NX: chỉ thêm một lần

~~~redis
ZADD leaderboard:init NX 100 alice
# Thêm alice nếu chưa tồn tại

ZADD leaderboard:init NX 200 alice
# Không đổi điểm của alice hiện hữu

ZSCORE leaderboard:init alice
# "100"
~~~

NX có ích khi thiết lập **điểm khởi tạo**, tránh vô tình reset điểm đã tích lũy. Các phiên bản Spring Data Redis có API **addIfAbsent** có thể dùng cho mục đích tương ứng; nếu phiên bản không cung cấp overload phù hợp, cần dùng API Redis thấp hơn với cấu hình rõ ràng.

### 6.2. XX: chỉ cập nhật thành viên hiện có

~~~redis
ZADD leaderboard:init XX 150 alice
# Alice đã có, score được cập nhật

ZADD leaderboard:init XX 50 unknown
# unknown chưa có, Redis không thêm
~~~

XX phù hợp khi thành viên phải được đăng ký qua một quy trình khác. Lưu ý ZINCRBY mặc định tự tạo member nên không thể dùng nguyên nó nếu yêu cầu bắt buộc “chỉ tăng khi member đã tồn tại”.

### 6.3. GT và LT: so sánh điểm tuyệt đối

~~~redis
ZADD best:score 120 alice
ZADD best:score GT 100 alice
# Vẫn 120

ZADD best:score GT 140 alice
# Thành 140
~~~

GT là điều kiện **score mới lớn hơn score cũ**, không có nghĩa cộng thêm. Tương tự, LT chỉ đổi score khi score mới thấp hơn.

GT phù hợp với **điểm kỷ lục cao nhất**, LT phù hợp với **thời gian/chi phí tốt nhất** nếu nhỏ hơn nghĩa là tốt hơn. Nếu nghiệp vụ có điều chỉnh điểm âm hợp lệ, dùng GT có thể làm mất việc điều chỉnh đó.

### 6.4. CH thay ý nghĩa kết quả trả về

~~~redis
ZADD rank:change 10 alice
# 1: thêm mới

ZADD rank:change 20 alice
# 0: member đã tồn tại

ZADD rank:change CH 30 alice
# 1: score thay đổi

ZADD rank:change CH 30 alice
# 0: score không đổi
~~~

CH không thay ý nghĩa điểm mới, chỉ thay cách đếm kết quả thành số member mới hoặc member có score được cập nhật.

## 7. Spring Data Redis với StringRedisTemplate

Trong Spring Boot, có thể sử dụng **StringRedisTemplate** để lưu key/member dưới dạng chuỗi. Spring Data Redis cung cấp **ZSetOperations** qua **opsForZSet()**.

Ví dụ service quản lý bảng xếp hạng:

~~~java
import java.time.Duration;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class WeeklyLeaderboardService {

    private static final String KEY = "leaderboard:2026-W46";

    private final StringRedisTemplate redis;
    private final ZSetOperations<String, String> zset;

    public WeeklyLeaderboardService(StringRedisTemplate redis) {
        this.redis = redis;
        this.zset = redis.opsForZSet();
    }

    public boolean setAbsoluteScore(String userId, double score) {
        requireFinite(score);
        Boolean added = zset.add(KEY, member(userId), score);

        // true: member mới; false: member đã có
        return Boolean.TRUE.equals(added);
    }

    public double addPoints(String userId, double delta) {
        requireFinite(delta);

        Double newScore =
                zset.incrementScore(KEY, member(userId), delta);

        return Objects.requireNonNull(
                newScore, "Redis did not return a new score");
    }

    public Double findScore(String userId) {
        return zset.score(KEY, member(userId));
    }

    public Long findDescendingRank(String userId) {
        return zset.reverseRank(KEY, member(userId));
    }

    public void setLeaderboardTtl(Duration ttl) {
        redis.expire(KEY, ttl);
    }

    private static String member(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException(
                    "userId must not be blank");
        }
        return "user:" + userId;
    }

    private static void requireFinite(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException(
                    "score or delta must be finite");
        }
    }
}
~~~

### 7.1. Hiểu kết quả của add()

~~~java
Boolean added = zset.add(KEY, "user:an", 120.0);
~~~

Trong cách thực thi thông thường:

- **true**: member chưa có và được **thêm mới**.
- **false**: member đã có; score vẫn có thể được **đặt lại**.
- **null**: có thể xuất hiện trong bối cảnh đặc biệt như pipeline/transaction, khi kết quả chưa có ngay.

Do đó, nếu hàm trả false, không nên ghi log “cập nhật thất bại”. Nếu caller chỉ cần thực hiện upsert, có thể không cần dùng Boolean trả về làm kết quả nghiệp vụ.

### 7.2. Hiểu kết quả của incrementScore()

~~~java
Double after = zset.incrementScore(
        KEY, "user:an", 10.0);
~~~

Giá trị trả về là **score sau khi cộng**, không phải delta, số thành viên hay rank. Trong ví dụ, nếu user:an có 120 điểm thì after bằng 130.0.

### 7.3. Member không tồn tại và member có score bằng 0

~~~redis
ZADD leaderboard:zero 0 user:zero

ZSCORE leaderboard:zero user:zero
# "0"

ZSCORE leaderboard:zero user:missing
# nil
~~~

Một điểm bằng 0 vẫn có nghĩa member **đang tồn tại**. Khi gọi **score()** từ Spring Data Redis, kết quả null trong lần đọc thông thường có thể mang nghĩa member vắng mặt. Nếu nghiệp vụ cần phân biệt “chưa tham gia” và “đã tham gia nhưng 0 điểm”, đừng chuyển null thành 0 một cách vô điều kiện.

## 8. Thêm nhiều cặp thành viên–điểm

Spring Data Redis có thể gửi nhiều **TypedTuple** trong một lần gọi:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.redis.core.DefaultTypedTuple;
import org.springframework.data.redis.core.ZSetOperations;

Set<ZSetOperations.TypedTuple<String>> members =
        new LinkedHashSet<>();

members.add(new DefaultTypedTuple<>("user:an", 120.0));
members.add(new DefaultTypedTuple<>("user:binh", 90.0));
members.add(new DefaultTypedTuple<>("user:chi", 110.0));

Long addedCount = zset.add("leaderboard:week", members);
~~~

Mỗi tuple gồm member và score. Với semantics mặc định của ZADD, một member đã tồn tại sẽ được **đặt lại score**, còn số trả về thường là **số member mới**.

Lợi ích:

- Giảm số round-trip so với gửi nhiều lời gọi độc lập.
- Có thể đồng bộ một snapshot nhiều member.
- Mỗi member trong batch có score xác định rõ.

Nhưng **batch add không phải batch increment**. Nếu một sự kiện cộng +10 cho user:an, gọi add với score 10 vẫn chỉ đặt điểm bằng 10. Muốn tăng điểm theo delta, phải dùng **incrementScore** hoặc cơ chế tích lũy được thiết kế riêng.

Khi nguồn dữ liệu có nhiều bản ghi cho cùng member, hãy quyết định rõ cách tổng hợp trước khi batch để tránh hai giá trị khác nhau của cùng member gây ra kết quả khó dự đoán.

## 9. Lấy Top N và thứ hạng sau khi cập nhật

Một Sorted Set có score là bảng xếp hạng tự nhiên. Để lấy 10 thành viên có điểm cao nhất:

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardQueryService {

    private final ZSetOperations<String, String> zset;

    public LeaderboardQueryService(StringRedisTemplate redis) {
        this.zset = redis.opsForZSet();
    }

    public record MemberScore(String member, double score) {}

    public List<MemberScore> top(String key, long limit) {
        if (limit <= 0) {
            return List.of();
        }

        Set<ZSetOperations.TypedTuple<String>> tuples =
                zset.reverseRangeWithScores(key, 0, limit - 1);

        if (tuples == null || tuples.isEmpty()) {
            return List.of();
        }

        return tuples.stream()
                .map(tuple -> new MemberScore(
                        tuple.getValue(),
                        tuple.getScore()))
                .toList();
    }
}
~~~

**reverseRangeWithScores(key, 0, limit - 1)** lấy member theo score giảm dần kèm điểm. Khi triển khai API public, nên giới hạn **limit** tối đa để tránh đọc hàng trăm nghìn member trong một request.

Để xem một thành viên cụ thể:

~~~java
Double score = zset.score(key, "user:an");
Long rankAscending = zset.rank(key, "user:an");
Long rankDescending = zset.reverseRank(key, "user:an");
~~~

Cả hai loại rank đều tính từ **0**; **reverseRank = 0** là vị trí dẫn đầu theo điểm cao nhất. Khi score bị cập nhật đồng thời, một lần đọc score và một lần đọc rank là **hai lời gọi** có thể phản ánh những thời điểm khác nhau.

## 10. Score có kiểu double: độ chính xác và quy ước

Redis Sorted Set lưu score bằng **số dấu phẩy động double**. Điều này tạo ra những điểm cần cân nhắc khi score là số lượng lớn hoặc có phần thập phân.

### 10.1. Số nguyên lớn

Các số nguyên có độ lớn không quá **2^53** có thể được biểu diễn chính xác trong double. Ngoài khoảng này, không phải mọi số nguyên liền kề còn được phân biệt.

Bảng xếp hạng vài nghìn hay vài triệu điểm thường không gặp giới hạn này. Nhưng nếu score là timestamp ở độ phân giải rất cao hoặc tổng bộ đếm cực lớn, cần kiểm tra dải giá trị thật.

### 10.2. Thập phân và sai số

Một số số thập phân như 0.1 không có biểu diễn nhị phân chính xác tuyệt đối. Khi cộng nhiều lần delta lẻ, kết quả có thể có sai số rất nhỏ.

Nếu nghiệp vụ có đơn vị 0.01 điểm, có thể quy ước:

~~~text
Điểm hiển thị: 12.35
Score lưu trong Redis: 1235
Đơn vị nội bộ: 1/100 điểm
~~~

Cách này giúp giữ các lần cộng điểm trong miền số nguyên, miễn là tổng vẫn nằm trong dải biểu diễn chính xác.

Không nên dùng double score làm nguồn kế toán chính thức cho tiền hoặc số dư tài chính; các hệ thống đó thường cần decimal/integer chính xác và transaction theo nghiệp vụ.

### 10.3. Đặt giới hạn ở tầng ứng dụng

Một service nên có quy ước:

- Có cho phép score âm không?
- Có cho phép delta âm để điều chỉnh không?
- Dải điểm tối thiểu/tối đa là bao nhiêu?
- Làm tròn score ở bước nào?
- Giá trị thiếu có nghĩa là 0 hay “chưa tham gia”?
- Score là số điểm tích lũy hay giá trị tuyệt đối mới nhất?

Một ứng dụng có thể chủ động từ chối NaN hoặc vô cực thông qua **Double.isFinite(...)**, ngay cả khi Redis có cách biểu diễn đặc biệt cho vài giá trị số. Điều quan trọng là giữ dữ liệu phù hợp hợp đồng nghiệp vụ.

## 11. Đồng thời, retry và idempotency

Một hệ thống tính điểm thường xử lý nhiều sự kiện cùng lúc. Dùng ZINCRBY là đúng khi cần cộng dồn, nhưng vẫn phải xác định **một sự kiện có thể xuất hiện nhiều lần hay không**.

Giả sử:

~~~text
eventId = evt-123
member  = user:an
delta   = 10
~~~

Service gửi:

~~~redis
ZINCRBY leaderboard:week 10 user:an
~~~

Redis đã tăng điểm nhưng mạng mất trước khi trả kết quả. Message broker phát lại evt-123 và service gửi lại ZINCRBY. Nếu không có kiểm soát, user:an nhận 20 điểm cho cùng một sự kiện.

### 11.1. Cần một mã sự kiện ổn định

Một thiết kế idempotency có thể dùng:

~~~text
processed:event:evt-123 -> đã xử lý
leaderboard:week         -> điểm tổng theo user
~~~

Nhưng không nên thực hiện thành ba thao tác độc lập:

~~~text
1. Kiểm tra EXISTS processed:event:evt-123
2. ZINCRBY leaderboard:week 10 user:an
3. Ghi processed:event:evt-123
~~~

Hai worker có thể cùng đọc trạng thái chưa xử lý rồi cùng cộng điểm. Hoặc worker crash giữa bước 2 và 3, khiến retry cộng thêm một lần.

Khi cần bảo đảm trong phạm vi Redis, logic kiểm tra event và cộng điểm phải được phối hợp **nguyên tử**, chẳng hạn bằng Lua script hoặc cơ chế transaction phù hợp. Nếu Redis Cluster được sử dụng, các key trong một script nhiều key cần được thiết kế theo quy tắc hash slot.

Dữ liệu chống trùng có thể lớn dần; cũng phải quy định **thời gian giữ event ID** theo cửa sổ retry của nguồn sự kiện. TTL quá ngắn có thể cho phép một sự kiện cũ bị xử lý lại.

### 11.2. Đặt điểm tuyệt đối vẫn có nguy cơ stale write

Nếu database lưu điểm chính và một tác vụ định kỳ đồng bộ về Redis bằng ZADD, cần ngăn snapshot cũ ghi đè score mới.

Ví dụ:

~~~text
T1: realtime ZINCRBY +10 -> score Redis = 110
T2: batch dùng snapshot cũ ZADD 100 -> Redis = 100
~~~

Hai lệnh đều hoạt động theo đặc tính của Redis nhưng hợp đồng đồng bộ chưa chính xác.

Hãy xác định Redis là **nguồn điểm chính** hay **projection của nguồn dữ liệu khác**, rồi chọn chính sách cập nhật, version hoặc điều kiện so sánh phù hợp. Nếu score chỉ tăng theo nghiệp vụ, **ZADD GT** có thể hỗ trợ giữ score cao nhất, nhưng nó không thay được logic khi có các điều chỉnh giảm hợp lệ.

### 11.3. Điều kiện điểm không âm phải nguyên tử

Nếu hai request đồng thời giảm điểm, việc làm:

~~~text
current = ZSCORE
if current + delta >= 0:
    ZINCRBY delta
~~~

có thể vi phạm giới hạn khi cả hai cùng đọc current cũ.

Một script có thể kết hợp kiểm tra và cộng trong một thao tác Redis:

~~~lua
-- KEYS[1] = leaderboard key
-- ARGV[1] = member
-- ARGV[2] = delta

local current = tonumber(redis.call('ZSCORE', KEYS[1], ARGV[1]) or '0')
local delta = tonumber(ARGV[2])
local nextScore = current + delta

if nextScore < 0 then
    return redis.error_reply('NEGATIVE_SCORE')
end

return redis.call('ZINCRBY', KEYS[1], ARGV[2], ARGV[1])
~~~

Ví dụ này minh họa yêu cầu kiểm tra nguyên tử. Khi triển khai thực tế còn cần xác thực input, xử lý lỗi, giới hạn score và thiết kế retry/idempotency riêng.

## 12. TTL, vòng đời và xóa thành viên

Sorted Set là **một key Redis**. TTL được đặt trên key đó, không tự áp dụng cho từng member:

~~~redis
ZADD leaderboard:2026-W46 120 user:an
EXPIRE leaderboard:2026-W46 604800
TTL leaderboard:2026-W46
~~~

**604800 giây** là 7 ngày. Khi key hết hạn, toàn bộ thành viên của bảng xếp hạng biến mất.

Các cập nhật ZADD hoặc ZINCRBY trên một Sorted Set còn tồn tại thông thường **không tự làm mới TTL**. Nếu ứng dụng muốn gia hạn toàn bảng sau mỗi hoạt động, cần chủ động quyết định và gọi EXPIRE.

### 12.1. Tách key theo kỳ

~~~text
leaderboard:day:2026-11-12
leaderboard:week:2026-W46
leaderboard:season:2026-fall
~~~

Phân tách theo kỳ giúp điểm của tuần mới không bị trộn với tuần cũ. Mỗi key có thể có TTL hoặc chính sách lưu lịch sử riêng.

Nếu code tạo key bằng ZADD rồi đặt EXPIRE bằng lệnh thứ hai, một lỗi mạng giữa hai lệnh có thể để lại key chưa có TTL. Với dữ liệu có yêu cầu expiration chặt, cần phối hợp hai thao tác theo cách phù hợp, chẳng hạn transaction/script hoặc quy trình kiểm tra và sửa TTL.

### 12.2. Xóa một thành viên

~~~redis
ZREM leaderboard:2026-W46 user:an
ZSCORE leaderboard:2026-W46 user:an
# nil
~~~

ZREM xóa member ra khỏi Sorted Set. Không nên dùng ZADD score 0 để biểu diễn “xóa”, bởi score 0 vẫn có nghĩa member tồn tại và vẫn có thứ hạng. Khi không còn member nào, Redis có thể không còn key của tập rỗng.

## 13. Sorted Set so với các kiểu Redis khác

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Bộ đếm đơn lẻ | String + INCRBY | Không cần sắp hạng |
| Nhiều bộ đếm theo field | Hash + HINCRBY | Nhóm thuộc tính trong một key |
| Tập member duy nhất, không cần điểm | Set | Kiểm tra thành viên và phép tập hợp |
| Member duy nhất kèm score và rank | Sorted Set | ZADD, ZINCRBY, ZRANK, ZRANGE |
| Danh sách theo thứ tự chèn, có thể trùng | List | Thao tác đầu/cuối |
| Sự kiện có ID và consumer group | Stream | Lưu và xử lý chuỗi sự kiện |

Nếu chỉ muốn lưu điểm một người, có thể dùng String counter. Nếu muốn truy vấn **top 10 người điểm cao nhất**, Sorted Set có lợi thế vì nó duy trì thứ tự theo score.

Thông tin hồ sơ như tên, avatar, email nên nằm ở dữ liệu riêng; Sorted Set có thể chỉ chứa **ID ổn định và score**. Tên hiển thị có thể đổi mà không cần đổi định danh member.

## 14. Ví dụ nghiệp vụ hoàn chỉnh

Một trò chơi gửi các sự kiện điểm:

~~~text
evt-101: user:an   +20
evt-102: user:binh +15
evt-103: user:chi  +10
evt-104: user:an    -5
~~~

Nếu các sự kiện đã được xác nhận là chưa xử lý, có thể cập nhật bảng theo delta:

~~~redis
ZINCRBY leaderboard:season:2026 20 user:an
ZINCRBY leaderboard:season:2026 15 user:binh
ZINCRBY leaderboard:season:2026 10 user:chi
ZINCRBY leaderboard:season:2026 -5 user:an
~~~

Điểm cuối:

~~~text
user:an    15
user:binh  15
user:chi   10
~~~

Truy vấn top:

~~~redis
ZRANGE leaderboard:season:2026 0 9 REV WITHSCORES
~~~

Do user:an và user:binh đồng điểm, Redis sử dụng quy tắc thứ tự member khi score bằng nhau. Nếu giao diện cần hiển thị cả hai cùng “hạng 1”, service phải quy định cách gán đồng hạng theo score.

Nếu quản trị viên cần sửa **điểm tuyệt đối** của user:an thành 50:

~~~redis
ZADD leaderboard:season:2026 50 user:an
ZSCORE leaderboard:season:2026 user:an
# "50"
~~~

Lệnh này **không cộng 50 vào 15**. Nếu chỉ thưởng thêm 50, phải gọi ZINCRBY.

### 14.1. Các lời gọi Spring Data Redis tương ứng

~~~java
String key = "leaderboard:season:2026";
var zset = stringRedisTemplate.opsForZSet();

// Đặt score tuyệt đối; return biểu thị có thêm member mới hay không.
Boolean newlyAdded = zset.add(key, "user:an", 50.0);

// Cộng thêm điểm và nhận score sau khi cộng.
Double scoreAfterBonus = zset.incrementScore(
        key, "user:an", 10.0);

// Tra cứu điểm:
Double currentScore = zset.score(key, "user:an");

// Thứ hạng giảm dần, bắt đầu bằng 0:
Long rank = zset.reverseRank(key, "user:an");

// Lấy top 10 kèm điểm:
var top10 = zset.reverseRangeWithScores(key, 0, 9);
~~~

## 15. Những lỗi thường gặp

**Nhầm add với incrementScore.** Phương thức add(key, member, 10) đặt score thành 10; incrementScore(key, member, 10) cộng thêm 10.

**Diễn giải sai false của add.** False không có nghĩa Redis không cập nhật; member có thể đã tồn tại và score bị thay đổi.

**Dùng GET score rồi tính rồi ZADD để cộng điểm.** Chuỗi nhiều lệnh có thể bị lost update. Dùng ZINCRBY cho delta.

**Không phân biệt score 0 và member chưa có.** Score 0 là thành viên hợp lệ; thiếu member cần được xử lý riêng.

**Hiển thị rank từ 0.** ZRANK/ZREVRANK trả vị trí 0-based; giao diện thường hiển thị 1-based.

**Giả định bằng điểm là cùng hạng theo Redis.** Redis vẫn có thứ tự giữa các member cùng score; quy tắc đồng hạng phải do nghiệp vụ thiết kế.

**Lấy tên hiển thị làm member.** Tên có thể đổi, khiến Redis tạo member khác. Dùng ID bất biến.

**Cộng điểm lại khi timeout.** Một lệnh ZINCRBY có thể đã chạy trước khi client mất phản hồi. Retry phải cân nhắc idempotency.

**Không đặt vòng đời cho leaderboard.** Dùng key theo ngày/tuần/mùa và chính sách expiration phù hợp.

**Dùng score double cho dữ liệu cần chính xác tuyệt đối.** Với tiền hoặc bộ đếm lớn, cần mô hình lưu trữ chính xác hơn và quy ước chuyển đổi rõ ràng.

## 16. Cách chọn thao tác

~~~text
Muốn thêm member với score ban đầu:
    ZADD key score member

Muốn tạo member một lần, không ghi đè:
    ZADD key NX score member

Muốn đặt score thành giá trị mới:
    ZADD key newScore member

Muốn chỉ sửa member đã tồn tại:
    ZADD key XX newScore member

Muốn chỉ giữ score cao nhất đã đạt:
    ZADD key GT newScore member

Muốn chỉ giữ score thấp nhất đã đạt:
    ZADD key LT newScore member

Muốn cộng/thưởng/trừ delta:
    ZINCRBY key delta member

Muốn lấy score hiện tại:
    ZSCORE key member

Muốn lấy thứ hạng giảm dần:
    ZREVRANK key member

Muốn lấy top kèm score:
    ZRANGE key 0 9 REV WITHSCORES
~~~

Ánh xạ với Spring Data Redis:

| Redis | Spring Data Redis | Kết quả đáng chú ý |
|---|---|---|
| ZADD | opsForZSet().add(key, member, score) | Boolean: có thêm member mới hay không |
| ZINCRBY | opsForZSet().incrementScore(key, member, delta) | Double: score mới |
| ZSCORE | opsForZSet().score(key, member) | Double hoặc null nếu vắng mặt |
| ZRANK | opsForZSet().rank(key, member) | Long, từ 0 |
| ZREVRANK | opsForZSet().reverseRank(key, member) | Long, từ 0 theo điểm giảm |
| ZRANGE giảm dần kèm điểm | opsForZSet().reverseRangeWithScores(...) | Các member và score trong khoảng |
| ZREM | opsForZSet().remove(key, member) | Số member bị xóa |
| ZCARD | opsForZSet().zCard(key) | Số member trong tập |

**Điểm cần nhớ:** ZADD biểu diễn việc **thiết lập score tuyệt đối** của một member, còn ZINCRBY biểu diễn việc **thay đổi score theo delta**. Sorted Set tự cập nhật thứ tự dựa trên score mới. Dùng đúng thao tác giúp tránh lost update cơ bản và giữ bảng xếp hạng có thứ tự, trong khi các yêu cầu như retry an toàn, xử lý sự kiện đúng một lần, TTL và đồng bộ dữ liệu giữa nhiều hệ thống vẫn cần quy tắc nghiệp vụ riêng.
