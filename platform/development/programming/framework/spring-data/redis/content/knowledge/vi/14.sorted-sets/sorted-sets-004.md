# Đọc thứ tự tăng dần, giảm dần và kèm điểm số trong Spring Data Redis

**Redis Sorted Set** (thường viết là **ZSet**, kiểu dữ liệu Redis `zset`) là một tập hợp các **member không trùng nhau**, trong đó mỗi member gắn với một **score dạng số thực**. Redis duy trì thứ tự dựa trên score, giúp lấy nhanh những phần tử có điểm thấp nhất, cao nhất, thứ hạng của một member hoặc các member có điểm nằm trong một khoảng.

Trong **Spring Data Redis**, các thao tác đọc Sorted Set thường được cung cấp qua `ZSetOperations<K, V>`:

- `range(key, start, end)`: đọc từ score **thấp đến cao**.
- `reverseRange(key, start, end)`: đọc từ score **cao xuống thấp**.
- `rangeWithScores(key, start, end)`: đọc tăng dần và **giữ lại score**.
- `reverseRangeWithScores(key, start, end)`: đọc giảm dần và **giữ lại score**.

Những phương thức này khác với `GET` của Redis String: chúng đọc một **đoạn theo vị trí trong Sorted Set đã sắp xếp**, chứ không đọc một khoảng byte trong giá trị. Bài học sẽ làm rõ hướng sắp xếp, chỉ số `start/end`, kết quả có hoặc không có score, cách xử lý khi điểm bằng nhau, phân trang và các ví dụ Java thực tế.

## 1. Mô hình dữ liệu: member, score và rank

Giả sử một bảng xếp hạng có các kết quả:

| Member | Score |
|---|---:|
| `alice` | 1250 |
| `bob` | 920 |
| `carol` | 1250 |
| `dave` | 1100 |
| `erin` | 640 |

Tạo Sorted Set trong Redis:

```redis
ZADD leaderboard:weekly 1250 alice 920 bob 1250 carol 1100 dave 640 erin
```

Redis có thể sắp xếp theo hai hướng:

```text
TĂNG DẦN (score thấp → cao)

rank 0     640   erin
rank 1     920   bob
rank 2    1100   dave
rank 3    1250   alice
rank 4    1250   carol

GIẢM DẦN (score cao → thấp)

reverse rank 0    1250   carol
reverse rank 1    1250   alice
reverse rank 2    1100   dave
reverse rank 3     920   bob
reverse rank 4     640   erin
```

**Member là duy nhất nhưng score không bắt buộc duy nhất.** `alice` và `carol` có thể cùng đạt 1250 điểm. Khi score trùng nhau, Redis sử dụng thứ tự từ điển của **chuỗi byte member** làm tiêu chí phân xử: ở hướng tăng dần, `alice` đứng trước `carol`; ở hướng giảm dần, thứ tự tương ứng đảo ngược.

Điều này dẫn đến ba khái niệm phải phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| **Member** | Giá trị duy nhất của phần tử, ví dụ `alice` |
| **Score** | Số dùng để xác định thứ tự, ví dụ `1250` |
| **Rank** | Vị trí của member trong kết quả sắp xếp tại thời điểm truy vấn, **bắt đầu từ 0** |

Hai member cùng score vẫn có hai vị trí khác nhau trong tập đã sắp xếp. Nếu nghiệp vụ muốn “đồng hạng” theo điểm số, ứng dụng phải định nghĩa và tính đồng hạng riêng; `ZRANK`/`ZREVRANK` không tự trả “cùng thứ hạng” cho các member trùng điểm.

## 2. Đọc theo thứ tự tăng dần với Redis `ZRANGE`

### 2.1. Cú pháp cơ bản

```redis
ZRANGE key start stop
```

Ở chế độ đọc theo rank thông thường:

- `start` là **vị trí bắt đầu**, tính từ 0.
- `stop` là **vị trí kết thúc và được tính vào kết quả** (*inclusive*).
- `0` là phần tử có score **thấp nhất**; `1` là phần tử tiếp theo.
- Chỉ số âm được tính từ cuối tập: `-1` là phần tử cuối cùng; `0 -1` nghĩa là lấy toàn bộ member.
- Nếu key không tồn tại hoặc khoảng không có phần tử, kết quả là một tập kết quả rỗng.

Ví dụ:

```redis
ZRANGE leaderboard:weekly 0 2
# erin
# bob
# dave

ZRANGE leaderboard:weekly 0 -1
# erin
# bob
# dave
# alice
# carol

ZRANGE leaderboard:weekly -2 -1
# alice
# carol
```

`ZRANGE key 0 2` trả **3 phần tử**, không phải 2 phần tử. Đây là lỗi lệch một chỉ số (*off-by-one*) dễ gặp khi chuyển từ API phân trang có tham số `offset` và `limit` sang Redis.

### 2.2. Nhận diện tăng dần thật sự là tăng dần theo score

Tên member không quyết định vị trí trước tiên. Dù `alice` đứng trước `bob` trong thứ tự chữ cái, `bob` có score 920 và `alice` có score 1250, vì vậy `bob` đứng trước `alice` trong `ZRANGE` thông thường.

Tính chất này làm Sorted Set phù hợp cho:

- Tìm sản phẩm có mức giá/rating số thấp nhất hoặc cao nhất, nếu model nghiệp vụ dùng score đúng nghĩa.
- Bảng xếp hạng, điểm số, thứ tự ưu tiên.
- Danh sách công việc theo thời điểm thực thi (score là timestamp).
- Truy vấn một dải số đã được sắp xếp mà không quét toàn bộ member ở ứng dụng.

Sorted Set **không tự biết** rằng “mức ưu tiên cao” nghĩa là số lớn hơn hay số nhỏ hơn. Nếu score là thời điểm đến hạn, tăng dần thường đọc việc đến hạn sớm nhất; nếu score là điểm thành tích, giảm dần thường đọc người đứng đầu.

## 3. Đọc theo thứ tự giảm dần

Từ Redis 6.2, `ZRANGE` hỗ trợ tùy chọn `REV`:

```redis
ZRANGE key start stop REV
```

Đối với ví dụ:

```redis
ZRANGE leaderboard:weekly 0 2 REV
# carol
# alice
# dave

ZRANGE leaderboard:weekly 0 -1 REV
# carol
# alice
# dave
# bob
# erin
```

Điểm quan trọng: khi có `REV`, **rank 0 là member có score cao nhất**. Các chỉ số `start`/`stop` lúc này được tính trong thứ tự giảm dần, không phải theo tập tăng dần rồi mới đảo ba phần tử đã chọn.

### 3.1. Lệnh `ZREVRANGE` cũ

Trên các phiên bản Redis cũ hoặc trong tài liệu trước đây, có thể gặp:

```redis
ZREVRANGE leaderboard:weekly 0 2
```

`ZREVRANGE` có ngữ nghĩa đọc giảm dần theo rank, nhưng Redis 6.2 đánh dấu lệnh này là **deprecated** và khuyến nghị dùng `ZRANGE ... REV`. Tùy phiên bản Spring Data Redis/driver, API trừu tượng có thể thực thi bằng những command Redis phù hợp; người viết code Java nên quan tâm ngữ nghĩa của `reverseRange` hơn là tự giả định wire command luôn trùng một tên lệnh.

### 3.2. Một lỗi thường gặp: tưởng `reverseRange` chỉ đảo kết quả `range`

Giả sử `range(key, 0, 2)` trả:

```text
erin, bob, dave
```

Đảo danh sách này ở Java sẽ cho:

```text
dave, bob, erin
```

Nhưng `reverseRange(key, 0, 2)` thực sự trả:

```text
carol, alice, dave
```

Hai kết quả hoàn toàn khác nhau: **đọc top 3 trong hướng giảm dần** không phải **đảo bottom 3 đã lấy theo hướng tăng dần**. Redis áp dụng thứ tự trước khi tính cửa sổ vị trí.

## 4. Đọc member kèm score với `WITHSCORES`

Mặc định `ZRANGE` chỉ trả member. Nếu ứng dụng cần hiển thị cả điểm — ví dụ bảng xếp hạng “tên người chơi – điểm” — hãy yêu cầu Redis trả score trong **chính lệnh đọc**:

```redis
ZRANGE leaderboard:weekly 0 2 WITHSCORES
# erin
# 640
# bob
# 920
# dave
# 1100
```

Thứ tự CLI hiển thị là member rồi score tương ứng. Trong dữ liệu giao thức, kết quả gồm các cặp member–score; cách terminal định dạng có thể khác tùy `redis-cli` và chế độ hiển thị.

Lấy top 3 theo điểm giảm dần, kèm score:

```redis
ZRANGE leaderboard:weekly 0 2 REV WITHSCORES
# carol
# 1250
# alice
# 1250
# dave
# 1100
```

Lệnh cũ tương đương về mặt ý nghĩa:

```redis
ZREVRANGE leaderboard:weekly 0 2 WITHSCORES
```

### 4.1. Vì sao nên lấy member và score cùng một lệnh?

Một cách làm tốn round trip là:

```text
1. ZRANGE key 0 9
2. ZSCORE key member1
3. ZSCORE key member2
...
11. ZSCORE key member10
```

Cách này gửi nhiều lệnh. Hơn nữa, giữa lúc đọc danh sách và từng lần `ZSCORE`, score có thể đã được cập nhật, khiến danh sách thứ hạng và các điểm hiển thị không còn cùng trạng thái.

Sử dụng `ZRANGE ... WITHSCORES` giúp **lấy thứ tự và score tại một thời điểm thực thi lệnh Redis**. Nó giảm round trip và tránh mâu thuẫn nội bộ giữa member và score do tách thành nhiều lệnh. Tuy vậy, kết quả vẫn có thể trở nên cũ ngay sau khi lệnh hoàn thành nếu producer liên tục cập nhật điểm.

### 4.2. Khi chỉ cần score của một member

Không cần tải cả một dải:

```redis
ZSCORE leaderboard:weekly alice
# "1250"

ZSCORE leaderboard:weekly unknown
# nil
```

Nếu chỉ muốn thứ hạng:

```redis
ZRANK leaderboard:weekly alice
# 3 — thứ tự tăng dần, bắt đầu từ 0

ZREVRANK leaderboard:weekly alice
# 1 — thứ tự giảm dần, bắt đầu từ 0
```

`ZRANK` và `ZREVRANK` trả **vị trí**, còn `ZSCORE` trả **điểm**. Đây là các thông tin khác nhau.

## 5. Tương ứng trong Spring Data Redis: `ZSetOperations`

Spring Data Redis cung cấp abstraction `ZSetOperations<K, V>` để thao tác Sorted Set qua `RedisTemplate`. Với member là chuỗi đơn giản, `StringRedisTemplate` là lựa chọn dễ quan sát vì key/member được serialize thành chuỗi UTF-8.

Ví dụ dependency Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Kết nối Redis thử nghiệm:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Các lệnh cơ bản:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;

public class SortedSetReader {

    private final ZSetOperations<String, String> zset;

    public SortedSetReader(StringRedisTemplate template) {
        this.zset = template.opsForZSet();
    }

    public Set<String> lowestThree() {
        return zset.range("leaderboard:weekly", 0, 2);
    }

    public Set<String> highestThree() {
        return zset.reverseRange("leaderboard:weekly", 0, 2);
    }

    public Set<ZSetOperations.TypedTuple<String>> lowestWithScores() {
        return zset.rangeWithScores("leaderboard:weekly", 0, 2);
    }

    public Set<ZSetOperations.TypedTuple<String>> highestWithScores() {
        return zset.reverseRangeWithScores(
            "leaderboard:weekly", 0, 2
        );
    }
}
```

Đối chiếu:

| Redis CLI (Redis 6.2+) | Spring Data Redis |
|---|---|
| `ZRANGE key 0 2` | `range(key, 0, 2)` |
| `ZRANGE key 0 2 REV` | `reverseRange(key, 0, 2)` |
| `ZRANGE key 0 2 WITHSCORES` | `rangeWithScores(key, 0, 2)` |
| `ZRANGE key 0 2 REV WITHSCORES` | `reverseRangeWithScores(key, 0, 2)` |
| `ZSCORE key member` | `score(key, member)` |
| `ZRANK key member` | `rank(key, member)` |
| `ZREVRANK key member` | `reverseRank(key, member)` |
| `ZCARD key` | `size(key)` |

Các phương thức Java trả kiểu `Set`, không phải `List`; đây là API của Spring Data Redis, không phải lý do để bỏ thứ tự Redis đã trả về. Khi cần hiển thị theo thứ tự, hãy duyệt kết quả trực tiếp theo thứ tự được operation trả về hoặc chuyển ngay sang một `List`. **Không đổ kết quả sang `HashSet` hoặc một Map không giữ thứ tự** rồi kỳ vọng hiển thị đúng bảng xếp hạng.

### 5.1. Lấy tăng dần

```java
Set<String> members =
    stringRedisTemplate.opsForZSet()
        .range("leaderboard:weekly", 0, 2);

// Theo dữ liệu ví dụ: erin, bob, dave
```

### 5.2. Lấy giảm dần

```java
Set<String> members =
    stringRedisTemplate.opsForZSet()
        .reverseRange("leaderboard:weekly", 0, 2);

// Theo dữ liệu ví dụ: carol, alice, dave
```

### 5.3. Lấy member và score cùng nhau

```java
Set<ZSetOperations.TypedTuple<String>> tuples =
    stringRedisTemplate.opsForZSet()
        .reverseRangeWithScores("leaderboard:weekly", 0, 2);

if (tuples != null) {
    for (ZSetOperations.TypedTuple<String> tuple : tuples) {
        String member = tuple.getValue();
        Double score = tuple.getScore();

        System.out.println(member + " -> " + score);
    }
}
```

`TypedTuple<V>` chứa **member** qua `getValue()` và **score** qua `getScore()`. Kiểu score ở tầng API là `Double`, vì Redis score dùng biểu diễn số thực double-precision.

Khi lập trình, lưu ý:

- `getValue()` là member đã được deserializer của template chuyển thành kiểu `V`.
- `getScore()` biểu diễn score, không phải rank.
- Trong thao tác thông thường, key không tồn tại hoặc khoảng không có phần tử thường dẫn đến kết quả rỗng; `null` còn có thể được trả về trong một số ngữ cảnh pipeline/transaction do kết quả bị hoãn. Không xem mọi `null` đều là “key không tồn tại”.
- Nếu logic yêu cầu score chắc chắn có giá trị, hãy kiểm tra dữ liệu đầu vào và hợp đồng API thay vì im lặng biến `null` thành `0.0`.

## 6. Xây dựng bảng xếp hạng với Spring Data Redis

Giả sử cần lưu điểm của người chơi và lấy top 10 cùng điểm. Một service có thể cung cấp phương thức cập nhật score và truy vấn bảng xếp hạng.

```java
package com.example.redis.leaderboard;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardService {

    private static final String KEY = "leaderboard:weekly";

    private final ZSetOperations<String, String> zset;

    public LeaderboardService(StringRedisTemplate template) {
        this.zset = template.opsForZSet();
    }

    public void setScore(String playerId, double score) {
        // ZADD: member đã tồn tại sẽ được cập nhật score.
        zset.add(KEY, playerId, score);
    }

    public Double increaseScore(String playerId, double amount) {
        return zset.incrementScore(KEY, playerId, amount);
    }

    public List<LeaderboardEntry> top(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 100"
            );
        }

        Set<ZSetOperations.TypedTuple<String>> tuples =
            zset.reverseRangeWithScores(KEY, 0, limit - 1L);

        if (tuples == null) {
            throw new IllegalStateException(
                "No immediate Redis result; check execution context"
            );
        }

        List<LeaderboardEntry> entries = new ArrayList<>();
        long position = 1L;

        for (ZSetOperations.TypedTuple<String> tuple : tuples) {
            if (tuple.getValue() == null || tuple.getScore() == null) {
                throw new IllegalStateException("Incomplete zset tuple");
            }

            entries.add(new LeaderboardEntry(
                position++,
                tuple.getValue(),
                tuple.getScore()
            ));
        }

        return List.copyOf(entries);
    }

    public Long rankFromTop(String playerId) {
        Long zeroBasedRank = zset.reverseRank(KEY, playerId);
        return zeroBasedRank == null ? null : zeroBasedRank + 1;
    }

    public record LeaderboardEntry(
        long displayRank,
        String playerId,
        double score
    ) {}
}
```

Ví dụ gọi:

```java
leaderboardService.setScore("alice", 1250);
leaderboardService.setScore("bob", 920);
leaderboardService.setScore("carol", 1250);
leaderboardService.setScore("dave", 1100);
leaderboardService.setScore("erin", 640);

List<LeaderboardService.LeaderboardEntry> top =
    leaderboardService.top(3);

// Theo dữ liệu minh họa:
// (1, "carol", 1250)
// (2, "alice", 1250)
// (3, "dave", 1100)
```

Trong ví dụ, `displayRank` là **vị trí hiển thị 1-based** dựa trên thứ tự Redis trả về. Nếu yêu cầu các người chơi bằng điểm phải “đồng hạng”, service cần thêm một quy tắc riêng:

```text
Thứ tự Redis:    carol 1250, alice 1250, dave 1100
Vị trí Redis:         0           1          2
Rank hiển thị 1-based:1           2          3
Rank đồng hạng:       1           1          3  (kiểu competition ranking)
```

`ZREVRANK` trả rank theo vị trí, không tự biểu diễn rank đồng hạng. Khi thiết kế bảng xếp hạng sản phẩm, cần quyết định hiển thị kiểu “1, 2, 3”, “1, 1, 3” hay “1, 1, 2” trước khi triển khai logic.

### 6.1. Vì sao dùng `incrementScore` thay vì đọc rồi ghi?

Đây là hai cách khác nhau:

```java
// Không phù hợp khi nhiều request tăng điểm cùng lúc:
Double oldScore = zset.score(KEY, playerId);
zset.add(KEY, playerId, (oldScore == null ? 0 : oldScore) + amount);
```

Giữa bước đọc và bước ghi, client khác có thể cập nhật score; lệnh cuối cùng có thể ghi đè mất một lần tăng. `incrementScore` sử dụng thao tác cập nhật điểm số ở Redis trong một lệnh tương ứng (ngữ nghĩa `ZINCRBY`), phù hợp cho bộ đếm điểm có cập nhật đồng thời.

Việc **đọc top N** và **cập nhật score** vẫn là những operation độc lập. Có thể có một lần cập nhật xảy ra ngay sau khi đọc top N; bảng xếp hạng hiển thị vì vậy là snapshot logic của một lệnh tại thời điểm đọc, không phải trạng thái bất biến.

### 6.2. Không dùng score làm định danh

Member phải được xác định ổn định, chẳng hạn `playerId`. Nếu member là tên hiển thị và người chơi đổi tên, ứng dụng có thể vô tình tạo một phần tử khác. Score có thể thay đổi nhiều lần mà member vẫn là một đối tượng.

Trong hệ thống đa tenant, tên key và member cần được thiết kế để tránh trộn dữ liệu:

```text
shop:prod:tenant:acme:leaderboard:weekly
shop:prod:tenant:beta:leaderboard:weekly
```

Tenant ID phải được xác thực ở phía ứng dụng trước khi tạo key. Prefix không thay thế authorization; một client có quyền vào Redis vẫn có thể đọc nhiều key nếu ứng dụng hoặc Redis ACL không giới hạn quyền truy cập thích hợp.

## 7. Đọc theo khoảng điểm số thay vì khoảng thứ hạng

`ZRANGE key start stop` thông thường hiểu `start` và `stop` là **rank**. Nhưng có nhiều yêu cầu thực tế như “liệt kê người chơi từ 1000 đến 1300 điểm”, không phải “lấy người chơi ở vị trí thứ 1000 đến 1300”.

Redis 6.2+ hỗ trợ tùy chọn `BYSCORE`:

```redis
ZRANGE leaderboard:weekly 1000 1300 BYSCORE WITHSCORES
# dave  1100
# alice 1250
# carol 1250
```

Lúc này `1000` và `1300` **là giới hạn score**, không phải vị trí. Kết quả vẫn được sắp xếp tăng dần theo score.

### 7.1. Giới hạn vô cực và loại trừ biên

`BYSCORE` hiểu các giá trị đặc biệt:

- `-inf`: âm vô cực, tương ứng không đặt đáy score hữu hạn.
- `+inf`: dương vô cực, tương ứng không đặt đỉnh score hữu hạn.
- `(1000`: loại trừ giá trị score 1000 (exclusive).
- `1000`: bao gồm giá trị score 1000 (inclusive).

Ví dụ:

```redis
# Member có score lớn hơn 1000, tăng dần:
ZRANGE leaderboard:weekly (1000 +inf BYSCORE WITHSCORES

# Member có score không vượt 1100, tăng dần:
ZRANGE leaderboard:weekly -inf 1100 BYSCORE WITHSCORES
```

Dấu ngoặc `(` là một phần của biểu thức giới hạn score ở Redis CLI. Nó không phải phép gọi hàm; cần truyền đúng chuỗi tham số khi dùng client API cấp thấp.

### 7.2. Kết hợp `BYSCORE` và `REV`

Khi truy vấn **giảm dần theo score** ở Redis CLI hiện đại, cú pháp với `REV BYSCORE` đặt **giới hạn cao trước, giới hạn thấp sau**:

```redis
ZRANGE leaderboard:weekly +inf 1000 BYSCORE REV WITHSCORES
# carol 1250
# alice 1250
# dave  1100
```

Trong trường hợp này, `1000` là giới hạn dưới được bao gồm, còn `+inf` là giới hạn trên.

Đừng nhầm thứ tự tham số ở cú pháp raw Redis với chữ ký API Java. Các phương thức như `rangeByScore(key, min, max)` ở tầng Spring Data cung cấp tham số theo quy ước của API; khi dùng phương thức reverse-by-score, cần đọc chữ ký và tài liệu của phiên bản Spring Data đang chạy, không tự đảo tham số `min/max` chỉ vì command Redis dùng `REV`.

### 7.3. Đọc theo score qua `ZSetOperations`

Spring Data Redis có các operation hỗ trợ lọc theo khoảng điểm:

```java
ZSetOperations<String, String> zset =
    stringRedisTemplate.opsForZSet();

// Từ 1000 đến 1300 điểm; kết quả tăng dần.
Set<String> byScore =
    zset.rangeByScore("leaderboard:weekly", 1000, 1300);

Set<ZSetOperations.TypedTuple<String>> byScoreWithScores =
    zset.rangeByScoreWithScores(
        "leaderboard:weekly", 1000, 1300
    );
```

`rangeByScoreWithScores` trả về member và score giống `rangeWithScores`, nhưng **tiêu chí lọc là dải score**. Những phương thức reverse/offset và các abstraction `Range`, `Limit` được hỗ trợ ở các phiên bản API Spring Data tương ứng; khi dùng hãy kiểm tra overload chính xác trong dependency của dự án.

### 7.4. Score range không tương đương rank range

So sánh:

```redis
ZRANGE leaderboard:weekly 0 2 WITHSCORES
# erin 640, bob 920, dave 1100

ZRANGE leaderboard:weekly 0 2 BYSCORE WITHSCORES
# Không có phần tử vì không ai có score từ 0 đến 2.
```

Hai lệnh có cùng cặp số `0 2` nhưng trả kết quả khác nhau hoàn toàn. API Spring cũng phân biệt `range(...)` và `rangeByScore(...)` để tránh sự nhầm lẫn này.

## 8. Phân trang theo rank

Vì Redis dùng chỉ số từ 0 và `stop` inclusive, trang `pageSize = 10` có công thức:

```text
start = pageIndex * pageSize
stop  = start + pageSize - 1
```

Với `pageIndex` bắt đầu từ 0:

| Trang | `start` | `stop` | Redis CLI (tăng dần) | Redis CLI (giảm dần) |
|---|---:|---:|---|---|
| 0 | 0 | 9 | `ZRANGE key 0 9` | `ZRANGE key 0 9 REV` |
| 1 | 10 | 19 | `ZRANGE key 10 19` | `ZRANGE key 10 19 REV` |
| 2 | 20 | 29 | `ZRANGE key 20 29` | `ZRANGE key 20 29 REV` |

### 8.1. Ví dụ Java phân trang bảng xếp hạng

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.springframework.data.redis.core.ZSetOperations;

public List<String> pageFromTop(
        ZSetOperations<String, String> zset,
        String key,
        long pageIndex,
        int pageSize
) {
    if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid page parameters");
    }

    long start = Math.multiplyExact(pageIndex, (long) pageSize);
    long stop = Math.addExact(start, pageSize - 1L);

    Set<String> result = zset.reverseRange(key, start, stop);
    if (result == null) {
        throw new IllegalStateException(
            "No immediate result in this execution context"
        );
    }
    return new ArrayList<>(result);
}
```

Ở đây:

- `pageIndex = 0` lấy các member có điểm cao nhất.
- Trang thứ hai bắt đầu ở vị trí `pageSize`, không bắt đầu ở vị trí `pageSize - 1`.
- `Math.multiplyExact`/`Math.addExact` giúp phát hiện overflow nếu tham số trang quá lớn.
- Giới hạn `pageSize` bảo vệ API khỏi yêu cầu trả khối dữ liệu quá lớn.
- Nếu cần cả score, thay `reverseRange` bằng `reverseRangeWithScores` rồi ánh xạ `TypedTuple` sang DTO.

### 8.2. Phân trang trên bảng xếp hạng đang thay đổi

Giả sử client đọc trang 0, sau đó một người chơi mới nhận điểm rất cao và được đưa lên đầu bảng. Khi client đọc trang 1, vị trí của những member cũ đã dịch chuyển. Có thể gặp:

- Một member xuất hiện ở cả hai trang.
- Một member bị bỏ qua giữa hai trang.
- Thứ hạng nhìn thấy trên các trang không còn thống nhất tại cùng một thời điểm.

Đây không nhất thiết là lỗi Redis. Mỗi lệnh `ZRANGE` nhìn thấy trạng thái Sorted Set ở **thời điểm riêng**. Phân trang dựa vào offset không tạo một snapshot xuyên suốt nhiều request.

Nếu cần kết quả phân trang **ổn định**:

1. Chụp một bảng xếp hạng theo kỳ, phiên bản hoặc snapshot key riêng.
2. Hạn chế thay đổi dữ liệu trong phạm vi phân trang, chẳng hạn khóa thời điểm kết thúc một cuộc thi.
3. Thiết kế cursor theo score cùng member (để xử lý điểm trùng nhau) hoặc một snapshot ID; với cách này cần xem kỹ điều kiện truy vấn và ngữ nghĩa tie-break thay vì chỉ lưu score.
4. Nếu cần truy vấn và phân trang phức tạp với nhiều điều kiện, cân nhắc một storage/index có mô hình phù hợp hơn.

**Không xem `ZSCAN` như API duyệt theo thứ tự bảng xếp hạng.** `ZSCAN` phục vụ quét tập dữ liệu theo cursor và không bảo đảm thứ tự score; muốn đọc thành các trang đã sắp xếp, dùng range phù hợp hoặc thiết kế snapshot/cursor có chủ đích.

## 9. Phân trang theo score và giới hạn `LIMIT`

Redis hỗ trợ giới hạn số phần tử trả về khi dùng `BYSCORE`:

```redis
ZRANGE leaderboard:weekly 1000 +inf BYSCORE LIMIT 0 2 WITHSCORES
# dave 1100
# alice 1250

ZRANGE leaderboard:weekly 1000 +inf BYSCORE LIMIT 2 2 WITHSCORES
# carol 1250
```

Các tham số `LIMIT offset count` có nghĩa:

- `offset`: bỏ qua bao nhiêu phần tử đầu trong **dải score đã lọc**.
- `count`: tối đa bao nhiêu phần tử trả về.

Chúng khác với `start/stop` trong rank mode, vì `LIMIT 0 2` lấy tối đa **2** phần tử chứ không phải các vị trí từ 0 đến 2 inclusive.

Với score range giảm dần:

```redis
ZRANGE leaderboard:weekly +inf 1000 BYSCORE REV LIMIT 0 2 WITHSCORES
# carol 1250
# alice 1250
```

Nếu offset rất lớn, Redis vẫn có chi phí bỏ qua những phần tử trước đó trong dải; phân trang offset sâu có thể tốn kém. Với luồng dữ liệu lớn cần tải liên tục, hãy cân nhắc mẫu cursor/snapshot phù hợp thay vì tăng offset không giới hạn.

### Khi nhiều người có cùng score

Dùng duy nhất `lastScore` làm cursor có thể gây lỗi. Ví dụ trang đầu chứa một phần trong nhóm score 1250; trang tiếp theo lọc `score < 1250` sẽ **bỏ qua những member 1250 còn lại**. Nếu trang tiếp theo dùng `score <= 1250`, các member đã xuất hiện có thể lặp lại.

Cần phối hợp score và thứ tự member trong thiết kế cursor, hoặc chọn một snapshot/score range có thể hiển thị toàn bộ nhóm cùng điểm. Redis Sorted Set hỗ trợ các primitive về score và lexicographical range, nhưng không có một “cursor pagination luôn ổn định với mọi cập nhật” tự động cho toàn bộ nghiệp vụ.

## 10. Khi score trùng nhau: thứ tự từ điển của member

Redis sắp xếp Sorted Set theo **score trước**, và dùng **lexicographical ordering của member** khi score bằng nhau.

Giả sử:

```redis
ZADD demo:ties 10 alpha 10 beta 10 gamma 20 delta
```

Tăng dần:

```redis
ZRANGE demo:ties 0 -1 WITHSCORES
# alpha 10
# beta  10
# gamma 10
# delta 20
```

Giảm dần:

```redis
ZRANGE demo:ties 0 -1 REV WITHSCORES
# delta 20
# gamma 10
# beta  10
# alpha 10
```

Với member là UTF-8, thứ tự so sánh ở Redis dựa trên **byte**, không phải thứ tự ngôn ngữ theo locale tiếng Việt, không tự bỏ dấu hay không phân biệt chữ hoa/chữ thường. Tên hiển thị giống nhau ở cấp người dùng có thể có byte khác nhau, nhất là khi Unicode có nhiều cách biểu diễn tương đương.

### 10.1. `BYLEX` là trường hợp khác

Redis có truy vấn theo khoảng từ điển bằng các thao tác lexicographical. Tuy nhiên, `BYLEX` không có nghĩa “sắp mọi member theo chữ cái bất kể score” khi các score khác nhau. Các truy vấn lexicographical trong Sorted Set dựa trên giả định phù hợp, phổ biến là **tất cả member có cùng score**.

Nếu muốn lưu một chỉ mục chỉ theo tên, có thể tạo một Sorted Set riêng mà tất cả member cùng score, hoặc dùng cấu trúc chỉ mục phù hợp. Không nhầm thứ tự tie-break của `ZRANGE` với một cơ chế sắp xếp tiếng Việt toàn diện.

### 10.2. Tránh phụ thuộc tie-break cho xếp hạng nghiệp vụ

Nếu hai người cùng 1250 điểm:

- Redis có vị trí xác định dựa trên member bytes.
- “Ai đạt 1250 trước” **không** được Redis tự suy ra.
- “Hai người đồng hạng” **không** phải ngữ nghĩa mặc định của rank.

Muốn xếp hạng theo tiêu chí phụ như thời điểm đạt điểm, cần thiết kế mô hình rõ ràng: tạo thêm chỉ mục có score thể hiện quy tắc phụ, hoặc lưu metadata và xếp hạng ở tầng thích hợp. Không nên cố nhồi nhiều đại lượng không liên quan vào một score double nếu điều đó làm mất độ chính xác hoặc khó giải thích.

## 11. Score là số thực: độ chính xác và thứ tự

Redis sử dụng score kiểu **double-precision floating-point**. Điều này phù hợp cho nhiều bài toán điểm số, timestamp có độ phân giải phù hợp và chỉ số sắp xếp. Tuy nhiên, không phải mọi số có thể biểu diễn chính xác ở dạng double.

### 11.1. Số nguyên lớn

Trong khoảng số nguyên có độ lớn không vượt quá `2^53`, các giá trị nguyên có thể được biểu diễn chính xác bằng double. Với số nguyên lớn hơn, hai giá trị nguyên liên tiếp có thể bị làm tròn về cùng một biểu diễn hoặc không còn giữ được độ phân giải mong muốn.

Nếu dùng timestamp với đơn vị **milliseconds**, số lớn hiện tại thường vẫn nằm trong vùng số nguyên chính xác của double. Nếu dùng nanoseconds từ epoch hoặc nối nhiều field thành một số nguyên rất lớn, cần kiểm tra giới hạn biểu diễn thay vì giả định mọi giá trị giữ nguyên từng đơn vị.

### 11.2. Không dùng score double như kho tiền tệ chính xác

Giá trị như `0.1` trong hệ nhị phân không được biểu diễn chính xác như số thập phân toán học. Nếu score đại diện giá bán hay tiền thưởng, cần xác định:

- Dữ liệu tài chính nguồn chính nằm ở đâu.
- Có sử dụng đơn vị nguyên nhỏ nhất (ví dụ xu, đồng) trong vùng chính xác không.
- Cần làm tròn như thế nào.
- Khi hiển thị score `Double`, có thể chuyển sang cách hiển thị số nguyên/định dạng tiền tệ theo quy tắc nghiệp vụ không.

Redis Sorted Set rất thích hợp làm **index sắp xếp**, nhưng không nên tự xem score double là nguồn lưu tiền có tính chính xác kế toán.

### 11.3. Cập nhật score có thể đổi thứ hạng

`ZADD` với member đã tồn tại sẽ cập nhật score:

```redis
ZADD leaderboard:weekly 1400 bob

ZRANGE leaderboard:weekly 0 2 REV WITHSCORES
# bob   1400
# carol 1250
# alice 1250
```

Sau lần cập nhật này, `bob` có reverse rank 0 dù trước đó chỉ có 920 điểm. Những kết quả phân trang/rank đã đọc trước đó không còn mô tả trạng thái mới.

## 12. Các lệnh liên quan giúp làm rõ kết quả đọc

| Lệnh | Ý nghĩa | Khi dùng |
|---|---|---|
| `ZCARD key` | Đếm số member trong Sorted Set | Tổng số phần tử cho UI phân trang |
| `ZSCORE key member` | Lấy score của một member | Hiển thị điểm một người |
| `ZMSCORE key member [member ...]` | Lấy score của nhiều member, giữ thứ tự member được yêu cầu | Tra cứu một danh sách ID đã biết |
| `ZRANK key member` | Rank 0-based theo hướng tăng dần | Vị trí từ điểm thấp lên |
| `ZREVRANK key member` | Rank 0-based theo hướng giảm dần | Vị trí bảng xếp hạng từ điểm cao xuống |
| `ZCOUNT key min max` | Đếm member trong khoảng score | Đếm số người thuộc một dải điểm |
| `ZRANGE ... WITHSCORES` | Đọc dải member theo rank/score kèm score | Hiển thị top/bottom và điểm |
| `ZPOPMIN key` / `ZPOPMAX key` | **Lấy và xóa** member thấp nhất/cao nhất | Queue/priority processing có chủ đích, không dùng để chỉ hiển thị |

### Đọc khác với xóa

`ZRANGE`, `ZRANK`, `ZSCORE` là các thao tác **đọc**, không loại member khỏi Sorted Set. Ngược lại:

```redis
ZPOPMAX leaderboard:weekly
```

sẽ **xóa** một member có score cao nhất. Với bảng xếp hạng muốn hiển thị mà không làm mất dữ liệu, cần `ZRANGE ... REV` thay vì `ZPOPMAX`.

### Tổng số phần tử và đếm theo dải

```redis
ZCARD leaderboard:weekly
# 5 trong tập ví dụ ban đầu

ZCOUNT leaderboard:weekly 1000 1300
# 3 trong tập ví dụ ban đầu (dave, alice, carol)
```

Lưu ý nếu đã chạy lệnh cập nhật điểm `bob` lên 1400 ở phần trước thì tổng số member vẫn là 5 nhưng thứ tự/đếm trong từng dải có thể đổi. Các kết quả minh họa ở đây xét **tập dữ liệu ban đầu**.

## 13. Tính chất hiệu năng và giới hạn kết quả

Redis Sorted Set duy trì cấu trúc dữ liệu hỗ trợ truy cập theo score/rank. Những thao tác range phổ biến có độ phức tạp tài liệu Redis mô tả xấp xỉ **O(log N + M)**, với:

- `N`: số member trong Sorted Set.
- `M`: số phần tử được trả về.

Vì vậy lấy top 10 của một tập lớn thường có chi phí khác đáng kể với đọc **toàn bộ** tập.

```redis
# Thường thích hợp cho một trang bảng xếp hạng:
ZRANGE leaderboard:weekly 0 9 REV WITHSCORES

# Có thể trả dữ liệu khổng lồ nếu tập rất lớn:
ZRANGE leaderboard:weekly 0 -1 REV WITHSCORES
```

Lưu ý:

- `WITHSCORES` tăng lượng dữ liệu cần truyền vì mỗi member đi kèm score.
- Thứ tự truy vấn là một phần chi phí của Sorted Set; nhưng số phần tử `M` được yêu cầu vẫn ảnh hưởng tới thời gian trả về và memory của ứng dụng.
- Truy vấn với `BYSCORE LIMIT offset count` và offset rất sâu có thể chịu chi phí duyệt bỏ các phần tử ban đầu trong dải.
- Phân trang theo rank của một tập đang cập nhật không tạo snapshot xuyên request.
- Lưu member dài hoặc payload lớn trực tiếp trong Sorted Set làm tăng bộ nhớ và traffic. Nên dùng ID member ngắn, còn thông tin hiển thị lấy từ cache/database khác theo thiết kế.

Ở lớp HTTP/API, nên áp đặt giới hạn page size và timeout hợp lý, đồng thời giám sát latency, kích thước tập và Redis memory thay vì cho client yêu cầu `0 -1` không giới hạn.

## 14. Test minh họa với Spring Data Redis

Để thấy rõ khác biệt tăng dần, giảm dần và score, có thể dùng kiểm thử tích hợp JUnit với Redis dành riêng cho test.

```java
package com.example.redis.leaderboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;

@SpringBootTest
class SortedSetReadIntegrationTest {

    private static final String KEY = "test:zset:leaderboard";

    @Autowired
    private StringRedisTemplate redis;

    @BeforeEach
    void prepare() {
        redis.delete(KEY);
        ZSetOperations<String, String> zset = redis.opsForZSet();
        zset.add(KEY, "alice", 1250);
        zset.add(KEY, "bob", 920);
        zset.add(KEY, "carol", 1250);
        zset.add(KEY, "dave", 1100);
        zset.add(KEY, "erin", 640);
    }

    @AfterEach
    void cleanup() {
        redis.delete(KEY);
    }

    @Test
    void rangeReadsAscendingByScore() {
        Set<String> members = redis.opsForZSet().range(KEY, 0, 2);

        assertNotNull(members);
        assertEquals(
            List.of("erin", "bob", "dave"),
            List.copyOf(members)
        );
    }

    @Test
    void reverseRangeReadsHighestFirst() {
        Set<String> members =
            redis.opsForZSet().reverseRange(KEY, 0, 2);

        assertNotNull(members);
        assertEquals(
            List.of("carol", "alice", "dave"),
            List.copyOf(members)
        );
    }

    @Test
    void reverseRangeWithScoresReturnsTuples() {
        Set<ZSetOperations.TypedTuple<String>> result =
            redis.opsForZSet().reverseRangeWithScores(KEY, 0, 1);

        assertNotNull(result);
        List<ZSetOperations.TypedTuple<String>> tuples =
            List.copyOf(result);

        assertEquals("carol", tuples.get(0).getValue());
        assertEquals(1250.0, tuples.get(0).getScore());
        assertEquals("alice", tuples.get(1).getValue());
        assertEquals(1250.0, tuples.get(1).getScore());
    }

    @Test
    void rankAndScoreAreDifferentConcepts() {
        assertEquals(1250.0, redis.opsForZSet().score(KEY, "alice"));
        assertEquals(3L, redis.opsForZSet().rank(KEY, "alice"));
        assertEquals(1L, redis.opsForZSet().reverseRank(KEY, "alice"));
    }

    @Test
    void scoreRangeFiltersByScoreNotRank() {
        Set<String> result =
            redis.opsForZSet().rangeByScore(KEY, 1000, 1300);

        assertNotNull(result);
        assertEquals(
            List.of("dave", "alice", "carol"),
            List.copyOf(result)
        );
    }
}
```

Trong môi trường chạy test:

- Dùng Redis dành riêng cho bài test, không dùng Redis production.
- Các trường hợp thử nên có key prefix/ID riêng nếu chạy song song.
- Kết quả có thể phụ thuộc serializer của template: ví dụ sử dụng `StringRedisTemplate` để member là chuỗi UTF-8.
- Code trên minh họa hành vi của API, không thay cho việc đánh giá nghiệp vụ về đồng hạng, phân trang đang thay đổi hoặc khả năng chịu lỗi hạ tầng.

### 14.1. Trường hợp cần kiểm thử thêm

Ngoài tập dữ liệu cơ bản, có thể đặt các tình huống:

1. Key không tồn tại, tập rỗng, khoảng rank ngoài giới hạn.
2. Score âm, bằng 0, không nguyên và số rất lớn gần giới hạn độ chính xác double.
3. Nhiều member trùng score, tên member có chữ hoa/chữ thường và Unicode.
4. `start/end` âm, `stop` inclusive, trang cuối ít hơn page size.
5. Score của member thay đổi trong khi client đang tải nhiều trang.
6. Kết quả `rangeWithScores` và `reverseRangeWithScores` có đủ member/score đúng không.
7. Key sai Redis type, kết nối lỗi hoặc Redis timeout.
8. Serializer value thay đổi giữa hai phiên bản ứng dụng.

Các trường hợp này giúp nhận diện rủi ro thiết kế khi dùng Sorted Set. Khi triển khai thực tế, ngữ nghĩa Redis luôn phải được kiểm tra trong phiên bản Redis/Spring Data đang sử dụng.

## 15. Bài thực hành từng bước với Redis CLI

Thực hiện trên một Redis dành riêng cho học tập.

**Bước 1 — Chuẩn bị dữ liệu:**

```redis
DEL lab:ranking
ZADD lab:ranking 90 alice 75 bob 95 carol 75 dave 60 erin
ZCARD lab:ranking
# 5
```

**Bước 2 — Đọc tăng dần theo score:**

```redis
ZRANGE lab:ranking 0 -1 WITHSCORES
# erin 60
# bob 75
# dave 75
# alice 90
# carol 95
```

**Bước 3 — Đọc giảm dần theo score:**

```redis
ZRANGE lab:ranking 0 -1 REV WITHSCORES
# carol 95
# alice 90
# dave 75
# bob 75
# erin 60
```

**Bước 4 — Lấy top 2 và bottom 2:**

```redis
ZRANGE lab:ranking 0 1 REV WITHSCORES
# carol 95, alice 90

ZRANGE lab:ranking 0 1 WITHSCORES
# erin 60, bob 75
```

**Bước 5 — Chỉ đọc dải 70–90 điểm:**

```redis
ZRANGE lab:ranking 70 90 BYSCORE WITHSCORES
# bob 75, dave 75, alice 90
```

**Bước 6 — So sánh score và rank:**

```redis
ZSCORE lab:ranking alice
# 90

ZRANK lab:ranking alice
# 3 — theo thứ tự tăng dần

ZREVRANK lab:ranking alice
# 1 — theo thứ tự giảm dần
```

**Bước 7 — Cập nhật score rồi đọc lại:**

```redis
ZINCRBY lab:ranking 30 bob
# 105

ZRANGE lab:ranking 0 2 REV WITHSCORES
# bob 105
# carol 95
# alice 90
```

**Bước 8 — Dọn dữ liệu thử nghiệm:**

```redis
DEL lab:ranking
```

Trong bài thực hành, các comment kết quả chỉ diễn tả member/score để dễ đọc. Redis CLI thường hiển thị từng phần tử của câu trả lời trên các dòng riêng.

## 16. Các sai lầm thường gặp

| Sai lầm | Vì sao sai? | Cách đúng |
|---|---|---|
| Dùng `range(key, 0, 9)` để lấy top 10 điểm cao | `range` đọc **tăng dần**, tức 10 member thấp nhất | Dùng `reverseRange(key, 0, 9)` |
| Nghĩ `reverseRange(0, 9)` là đảo `range(0, 9)` | Đảo danh sách bottom 10 không tạo top 10 | Xác định hướng sắp xếp trước, rồi chọn rank range |
| Lấy `range(key, 0, 10)` cho 10 phần tử | `stop` inclusive nên có thể trả **11** phần tử | Dùng `0, 9` |
| Cần điểm nhưng chỉ gọi `range` | Kết quả chỉ có member | Dùng `rangeWithScores` / `reverseRangeWithScores` |
| Dùng nhiều `ZSCORE` sau khi đọc danh sách | Nhiều round trip và có thể lệch trạng thái khi score thay đổi | Ưu tiên `WITHSCORES` cho danh sách hiển thị |
| Nhầm `range(key, 100, 200)` là lọc score 100–200 | Tham số của `range` là rank | Dùng `rangeByScore` |
| Nhầm rank 0 là “không có thứ hạng” | Rank Redis bắt đầu từ 0 | Chỉ chuyển +1 khi hiển thị, kiểm tra `null` cho member không tồn tại |
| Cho rằng cùng score sẽ nhận cùng rank | Redis vẫn sắp member có score trùng theo byte | Tự định nghĩa quy tắc đồng hạng nếu cần |
| Dùng `ZPOPMAX` để xem top 1 | `ZPOPMAX` xóa member | Dùng `reverseRange(key, 0, 0)` |
| Dùng `ZSCAN` để lấy trang xếp hạng | `ZSCAN` không bảo đảm thứ tự | Dùng rank range hoặc snapshot/cursor phù hợp |
| Đổ kết quả vào `HashSet` rồi hiển thị | Mất thứ tự member | Giữ thứ tự operation trả về khi ánh xạ sang List |
| Dùng score double như một số tiền chính xác tuyệt đối | Sai số biểu diễn floating point | Dùng đơn vị nguyên nhỏ nhất khi phù hợp và nguồn tiền tệ chính xác riêng |
| Đọc mọi member bằng `0 -1` không giới hạn | Có thể tải tập rất lớn về ứng dụng | Giới hạn kích thước trang |
| Coi nhiều trang là một snapshot | Score/rank có thể đổi giữa các lần gọi | Dùng snapshot hoặc chiến lược phân trang ổn định |

## 17. Câu hỏi tự kiểm tra

**1. `ZRANGE leaderboard 0 2` trả những phần tử nào?**  
Tối đa ba member có score thấp nhất, theo thứ tự tăng dần. Nếu score bằng nhau, Redis xét thứ tự từ điển của bytes member.

**2. Muốn top 3 theo điểm cao nhất với Spring Data Redis, gọi gì?**  
`opsForZSet().reverseRange(key, 0, 2)`. Nếu muốn kèm điểm, dùng `reverseRangeWithScores(key, 0, 2)`.

**3. Trong Redis 6.2+, đọc giảm dần và có điểm bằng CLI ra sao?**  
`ZRANGE key 0 2 REV WITHSCORES`.

**4. `WITHSCORES` giúp tránh vấn đề gì?**  
Trả member và score trong cùng một lệnh, giảm round trip và tránh sự không nhất quán do đọc danh sách rồi gọi riêng `ZSCORE` nhiều lần.

**5. Vì sao `ZREVRANK key alice` không phải score của alice?**  
Vì nó là vị trí 0-based trong thứ tự giảm dần; để lấy score dùng `ZSCORE` hoặc `ZSetOperations.score(...)`.

**6. Có hai member đều score 1250; Redis có tự cho chúng cùng rank không?**  
Không. Redis dùng thứ tự từ điển theo byte member để phân xử, vì thế hai member vẫn có vị trí khác nhau.

**7. Khác biệt giữa `range(key, 10, 20)` và `rangeByScore(key, 10, 20)`?**  
Hàm đầu lọc theo vị trí rank 10–20 inclusive; hàm sau lọc member có score từ 10 đến 20.

**8. `ZRANGE key +inf 1000 BYSCORE REV` có ý nghĩa gì?**  
Đọc score từ cao xuống thấp với giới hạn dưới 1000, tức những member có score từ 1000 trở lên, không trả score nếu không kèm `WITHSCORES`.

**9. Tại sao trang thứ hai có thể xuất hiện member vừa thấy ở trang đầu?**  
Vì score/rank thay đổi giữa hai lệnh Redis; phân trang theo offset không tạo snapshot xuyên thời gian.

**10. Chọn `rangeWithScores` hay `reverseRangeWithScores` để hiển thị 10 người điểm thấp nhất?**  
`rangeWithScores(key, 0, 9)`, vì cần thứ tự tăng dần và hiển thị score.

**11. Khi key không tồn tại, `score(key, member)` trả gì?**  
Không có score tương ứng; API Spring có thể trả `null`. Phải phân biệt member/key không tồn tại với score bằng 0.

**12. `ZPOPMAX` có thay thế `ZRANGE ... REV` khi chỉ muốn xem người dẫn đầu không?**  
Không. `ZPOPMAX` loại member khỏi tập; `ZRANGE ... REV` chỉ đọc.

**13. Có thể dùng `ZSCAN` để lấy chính xác top 10 không?**  
Không. `ZSCAN` không bảo đảm trả dữ liệu theo score; dùng `ZRANGE ... REV` hoặc `reverseRange`.

**14. Vì sao score double không thích hợp để lưu tiền tệ cần chính xác tuyệt đối?**  
Vì floating-point nhị phân có thể không biểu diễn chính xác mọi số thập phân. Nếu dùng score để sắp xếp giá, cần mô hình đơn vị và nguồn dữ liệu chính xác phù hợp.

## 18. Ghi nhớ

- **Redis Sorted Set sắp xếp theo score**; member không trùng nhưng nhiều member có thể trùng score.
- **`ZRANGE` / `range` đọc tăng dần** theo score; **`ZRANGE ... REV` / `reverseRange` đọc giảm dần**.
- **`WITHSCORES` / `rangeWithScores` / `reverseRangeWithScores` trả cả member và score**, phù hợp để dựng bảng xếp hạng.
- **Chỉ số theo rank bắt đầu từ 0, `stop` được tính vào kết quả**, và chỉ số âm tính từ cuối thứ tự đang đọc.
- **`BYSCORE` / `rangeByScore` lọc theo giá trị score**, không phải vị trí trong danh sách.
- **Member bằng điểm được phân xử theo thứ tự byte**, không mặc nhiên đồng hạng theo nghiệp vụ.
- **Phân trang rank trên tập đang thay đổi không phải snapshot**, nên cần chiến lược phiên bản hoặc cursor khi yêu cầu ổn định.
- **`ZPOPMIN/MAX` là lệnh thay đổi dữ liệu**, khác với lệnh đọc `ZRANGE`.

Khi viết ứng dụng Spring Data Redis, trước mỗi lệnh đọc Sorted Set hãy xác định **cần đầu thấp hay đầu cao, muốn lọc theo vị trí hay score, và có cần score trong kết quả hay không**. Chọn đúng `range`, `reverseRange` và biến thể `WithScores` sẽ giúp thao tác ngắn gọn, có thứ tự xác định và tránh mất thông tin khi xây dựng bảng xếp hạng, danh sách ưu tiên hoặc phân trang.
