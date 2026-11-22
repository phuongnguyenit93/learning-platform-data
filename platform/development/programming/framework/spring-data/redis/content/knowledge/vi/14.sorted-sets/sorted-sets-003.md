# Truy vấn theo vị trí, điểm số hoặc thứ tự từ điển

Redis Sorted Set (thường gọi là **ZSet**) lưu các **member không trùng nhau**, mỗi member gắn với một **score** kiểu số thực. Redis dùng score để sắp xếp; khi nhiều member có cùng score, chúng được phân thứ tự tiếp theo giá trị byte của member. Trong Spring Data Redis, các thao tác tương ứng nằm ở `ZSetOperations<K, V>`, thường được lấy bằng `redisTemplate.opsForZSet()`.

Khác với Redis Set thông thường, Sorted Set cho phép truy vấn một lát cắt đã sắp xếp theo ba trục:

1. **Vị trí (rank/index):** lấy phần tử thứ 0, 1, 2… sau khi sắp xếp; ví dụ top 10 bảng xếp hạng.
2. **Điểm số (score):** lấy member có điểm nằm trong một khoảng; ví dụ lịch sự kiện theo timestamp hoặc học viên đạt từ 70 đến 90 điểm.
3. **Thứ tự từ điển (lexicographical order):** lấy member nằm trong khoảng chuỗi theo so sánh byte; ví dụ gợi ý một nhóm mã có cùng tiền tố.

Bài học đi từ lệnh Redis trực tiếp đến API Spring Data Redis, minh họa cả chiều tăng/giảm, điều kiện biên, phân trang, lấy kèm score, thiết kế key và những sai lầm thường gặp.

> **Quy ước phiên bản:** Các ví dụ CLI chính dùng cú pháp `ZRANGE ... BYSCORE/BYLEX/REV` có từ Redis **6.2**. Một số lệnh truyền thống `ZRANGEBYSCORE`, `ZREVRANGE`, `ZRANGEBYLEX` vẫn có thể gặp trong hệ thống cũ. Phần Java sử dụng các API phổ biến của Spring Data Redis **3.x và 4.x**; hãy đối chiếu tài liệu API với phiên bản dự án đang chạy.

## 1. Cấu trúc dữ liệu và nguyên tắc sắp xếp của ZSet

### 1.1. Một member ứng với một score

Dùng Redis CLI tạo danh sách điểm mẫu:

```redis
DEL lab:zset:scores
ZADD lab:zset:scores 10 alice 20 bob 20 carol 40 dave 60 erin
ZRANGE lab:zset:scores 0 -1 WITHSCORES
```

Kết quả logic:

```text
Rank   Member   Score
  0    alice      10
  1    bob        20
  2    carol      20
  3    dave       40
  4    erin       60
```

Trong ZSet:

- **Member là duy nhất** trong phạm vi một key. Không thể có hai bản ghi riêng cùng member `alice`.
- **Score không bắt buộc duy nhất**: `bob` và `carol` đều có score `20`.
- **Thứ tự mặc định** là score **tăng dần**.
- **Khi hòa score**, Redis sắp xếp member theo thứ tự **byte lexicographical**: `bob` đứng trước `carol`.
- Gọi `ZADD` cho member đã tồn tại với score khác sẽ **cập nhật score**, có thể làm thay đổi rank của member ấy.

Ví dụ:

```redis
ZADD lab:zset:scores 90 alice
ZRANGE lab:zset:scores 0 -1 WITHSCORES
```

Lúc này `alice` có thể đứng cuối vì score được đổi thành `90`. Nếu các bài thực hành sau cần dữ liệu ban đầu, hãy chạy lại phần `DEL` + `ZADD` trước mỗi nhóm ví dụ.

### 1.2. Hình dung hai trục của ZSet

```text
Member (duy nhất)  <----->  Score (double)
       |                       |
       |                Trục sắp xếp chính
       |                       |
       +---- Thứ tự phụ khi score bằng nhau
                           |
                     Rank 0, 1, 2...
```

Ba kiểu truy vấn đọc từ cùng một ZSet nhưng diễn giải **hai tham số giới hạn** theo cách khác nhau:

| Kiểu truy vấn | Tham số khoảng có ý nghĩa gì? | Ví dụ |
|---|---|---|
| **By rank** | Hai **chỉ số** trong danh sách đã sắp xếp | Lấy rank từ 0 đến 9. |
| **By score** | Hai **giá trị score** tối thiểu/tối đa | Lấy điểm từ 20 đến 40. |
| **By lex** | Hai **chuỗi biên** của member | Lấy các mã từ `alpha` đến `charlie`. |

Không thể thay thế các truy vấn này cho nhau: **rank 20 không có nghĩa score 20**, còn ký tự đầu của member không tự quyết định score.

### 1.3. Tên các lệnh phổ biến

| Mục đích | Redis | Spring Data Redis |
|---|---|---|
| Thêm hoặc cập nhật score | `ZADD` | `opsForZSet().add(key, value, score)` |
| Lấy theo rank tăng | `ZRANGE key start stop` | `range(key, start, end)` |
| Lấy theo rank giảm | `ZRANGE key start stop REV` | `reverseRange(key, start, end)` |
| Lấy member kèm score | `ZRANGE ... WITHSCORES` | `rangeWithScores` / `reverseRangeWithScores` |
| Tìm rank của một member | `ZRANK` / `ZREVRANK` | `rank(key, value)` / `reverseRank(key, value)` |
| Lấy theo khoảng score | `ZRANGE ... BYSCORE` | `rangeByScore(key, min, max)` |
| Lấy khoảng score giảm dần | `ZRANGE ... REV BYSCORE` | `reverseRangeByScore(key, min, max)` |
| Lấy khoảng member theo lex | `ZRANGE ... BYLEX` | `rangeByLex(key, Range<String>)` |
| Lấy lex theo thứ tự ngược | `ZRANGE ... REV BYLEX` | `reverseRangeByLex(key, Range<String>)` |
| Đếm member trong khoảng score | `ZCOUNT` | `count(key, min, max)` |
| Đếm member trong khoảng lex | `ZLEXCOUNT` | API ở cấp Redis connection nếu cần |
| Tìm score của một member | `ZSCORE` | `score(key, value)` |
| Đếm tổng member | `ZCARD` | `size(key)` |

Tên `ZSetOperations` nằm ở package `org.springframework.data.redis.core`. Spring Data trả về `Set<V>` hoặc `Set<TypedTuple<V>>` cho nhiều lệnh range, vì một member không lặp lại trong ZSet. Khi trả kết quả ra API của ứng dụng, cần giữ ngữ nghĩa thứ tự mà Redis đã trả thay vì tùy ý chuyển sang một collection không có thứ tự.

## 2. Truy vấn theo vị trí (rank)

### 2.1. Rank bắt đầu từ 0

Với dữ liệu gốc:

```text
alice(10), bob(20), carol(20), dave(40), erin(60)
```

Lệnh:

```redis
ZRANGE lab:zset:scores 0 2
```

trả:

```text
alice
bob
carol
```

Chỉ số `start=0` là member thấp nhất theo score; `stop=2` là member thứ ba. **Hai đầu đều được tính vào kết quả**.

| Lệnh | Kết quả logic |
|---|---|
| `ZRANGE key 0 0` | Member đầu tiên. |
| `ZRANGE key 0 2` | Ba member đầu. |
| `ZRANGE key 1 3` | Member ở rank 1, 2 và 3. |
| `ZRANGE key 0 -1` | Tất cả member tăng dần. |
| `ZRANGE key -2 -1` | Hai member cuối của thứ tự tăng dần. |
| `ZRANGE key 99 120` | Danh sách rỗng nếu chỉ có năm member. |

Chỉ số âm đếm từ cuối: `-1` là phần tử cuối, `-2` là phần tử áp cuối. Redis không báo lỗi chỉ vì range vượt kích thước; kết quả được giới hạn theo dữ liệu hiện có.

### 2.2. Top N theo thứ tự score giảm dần

Một bảng xếp hạng thường muốn người có **score cao nhất đứng đầu**:

```redis
ZRANGE lab:zset:scores 0 2 REV WITHSCORES
```

Kết quả logic:

```text
erin   60
dave   40
carol  20
```

Ở chế độ `REV`, rank 0 được hiểu là member có score cao nhất. Với cùng score `20`, thứ tự byte cũng đảo nên `carol` đứng trước `bob` ở danh sách giảm dần.

Đừng viết `ZRANGE key 0 2` rồi tự đảo thứ tự nếu chỉ muốn top cao nhất: dùng `REV` để Redis thực hiện đúng thứ tự xếp hạng.

### 2.3. Tìm rank của một member

`ZRANK` cho thứ hạng tính từ score thấp lên:

```redis
ZRANK lab:zset:scores carol
```

Kết quả `2`.

`ZREVRANK` cho thứ hạng tính từ score cao xuống:

```redis
ZREVRANK lab:zset:scores carol
```

Với dữ liệu gốc, kết quả cũng là `2`, chỉ là tình cờ vì `carol` nằm giữa năm phần tử. Với `erin`, `ZRANK` cho `4` và `ZREVRANK` cho `0`.

Nếu member không tồn tại, Redis trả nil/null reply. Trong Spring Data Redis, `rank` / `reverseRank` trả `Long` có thể bằng `null` nếu member vắng mặt hoặc khi kết quả chưa có ngay trong pipeline/transaction.

### 2.4. Java với StringRedisTemplate

```java
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardReader {

    private final ZSetOperations<String, String> zsets;

    public LeaderboardReader(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    public Set<String> lowestThree(String key) {
        return zsets.range(key, 0, 2);
    }

    public Set<String> highestThree(String key) {
        return zsets.reverseRange(key, 0, 2);
    }

    public Long rankingFromTop(String key, String member) {
        return zsets.reverseRank(key, member);
    }
}
```

Phương thức `range` và `reverseRange` trả `Set<String>` theo hợp đồng API, hoặc `null` khi đang pipeline/transaction. Ở nơi cần trả một danh sách JSON theo thứ tự, hãy thiết kế tầng trả kết quả sao cho bảo toàn thứ tự đọc từ Redis và không xem đây là một tập hợp toán học không có thứ tự.

### 2.5. Top N kèm score bằng TypedTuple

Nếu chỉ trả member, một endpoint leaderboard không thể hiển thị điểm tương ứng mà không gửi thêm lệnh `ZSCORE` cho từng member. Thay vào đó, lấy cả score trong một truy vấn:

```java
import java.util.Set;
import org.springframework.data.redis.core.ZSetOperations;

Set<ZSetOperations.TypedTuple<String>> top =
        zsets.reverseRangeWithScores("lab:zset:scores", 0, 2);

if (top != null) {
    for (ZSetOperations.TypedTuple<String> item : top) {
        String member = item.getValue();
        Double score = item.getScore();
        System.out.println(member + " = " + score);
    }
}
```

`TypedTuple<V>` chứa member và score. Đây là kết quả tự nhiên khi Redis trả `WITHSCORES`. Score ở Java thường biểu diễn bằng `Double`; lưu ý double có giới hạn độ chính xác, nhất là khi dùng score làm timestamp hay khóa sắp xếp số nguyên lớn.

## 3. Truy vấn theo điểm số (score)

### 3.1. Score range khác rank range

Giả sử bảng điểm vẫn là:

```text
alice(10), bob(20), carol(20), dave(40), erin(60)
```

Truy vấn member có score từ **20 đến 40**:

```redis
ZRANGE lab:zset:scores 20 40 BYSCORE WITHSCORES
```

Kết quả:

```text
bob    20
carol  20
dave   40
```

Các con số `20` và `40` lần này là **điểm số**, không phải vị trí. Nếu bỏ `BYSCORE`, lệnh sẽ cố lấy rank từ 20 đến 40, và trả rỗng vì ZSet chỉ có năm phần tử.

Theo mặc định, hai biên score là **bao gồm**:

```text
20 <= score <= 40
```

### 3.2. Biên mở, biên đóng và vô hạn

Redis dùng dấu `(` đứng trước số để chỉ **biên mở (exclusive)**; không có dấu `(` nghĩa là inclusive.

```redis
ZRANGE lab:zset:scores (20 60 BYSCORE WITHSCORES
```

Kết quả là `dave(40)` và `erin(60)`: loại score đúng bằng `20`, giữ score `60`.

```redis
ZRANGE lab:zset:scores (20 (60 BYSCORE WITHSCORES
```

Kết quả chỉ có `dave(40)` vì cả `20` lẫn `60` đều bị loại.

Có thể dùng:

- `-inf`: không giới hạn dưới.
- `+inf`: không giới hạn trên.

Ví dụ:

```redis
ZRANGE lab:zset:scores -inf 20 BYSCORE
ZRANGE lab:zset:scores 40 +inf BYSCORE
```

Tương ứng lấy các member có score không lớn hơn 20, hoặc không nhỏ hơn 40.

Trong shell, chuỗi chứa `(` có thể cần đặt trong dấu nháy để tránh shell diễn giải ký tự đặc biệt. Bên trong cửa sổ `redis-cli` tương tác, cú pháp trên được Redis phân tích trực tiếp.

### 3.3. Chiều giảm của score range

Một báo cáo có thể cần chọn các member trong khoảng điểm rồi sắp xếp **cao xuống thấp**:

```redis
ZRANGE lab:zset:scores 40 20 BYSCORE REV WITHSCORES
```

Ở lệnh Redis này, khi có `REV BYSCORE`, **biên cao đặt trước, biên thấp đặt sau**. Kết quả:

```text
dave   40
carol  20
bob    20
```

Khi dùng Spring Data Redis `reverseRangeByScore(key, min, max)`, chữ ký Java vẫn nhận **min trước, max sau**:

```java
Set<String> members = zsets.reverseRangeByScore(
        "lab:zset:scores", 20, 40
);
```

Đây là khác biệt quan trọng giữa cú pháp lệnh Redis có `REV` và tên tham số API Spring. Không đảo min/max khi gọi `reverseRangeByScore` trong Java.

### 3.4. Truy vấn theo score từ Spring Data Redis

```java
import java.util.Set;
import org.springframework.data.redis.core.ZSetOperations;

Set<String> atLeastTwenty =
        zsets.rangeByScore("lab:zset:scores", 20, Double.POSITIVE_INFINITY);

Set<String> twentyToForty =
        zsets.rangeByScore("lab:zset:scores", 20, 40);

Set<String> twentyToFortyDescending =
        zsets.reverseRangeByScore("lab:zset:scores", 20, 40);

Set<ZSetOperations.TypedTuple<String>> scored =
        zsets.rangeByScoreWithScores("lab:zset:scores", 20, 40);
```

Các overload `double min, double max` của `rangeByScore` diễn giải khoảng **inclusive**. Khi cần biên mở như `score > 20`, một cách tương thích giữa các phiên bản API là dùng `Range` ở tầng Redis connection hoặc lệnh Redis phù hợp; đừng thay `20` bằng một số `20.00000001` theo cảm tính vì độ chính xác và thang đo của score có thể khác.

### 3.5. Giới hạn số kết quả trong khoảng score

Redis có `LIMIT offset count` để lấy một phần trong các member khớp:

```redis
ZRANGE lab:zset:scores 20 60 BYSCORE LIMIT 0 2 WITHSCORES
```

Kết quả:

```text
bob   20
carol 20
```

Lấy hai member kế tiếp trong cùng score range:

```redis
ZRANGE lab:zset:scores 20 60 BYSCORE LIMIT 2 2 WITHSCORES
```

Kết quả:

```text
dave 40
erin 60
```

Trong Spring:

```java
Set<ZSetOperations.TypedTuple<String>> firstPage =
        zsets.rangeByScoreWithScores(
                "lab:zset:scores",
                20,
                60,
                0, // offset trong tập kết quả thỏa score range
                2  // số member tối đa
        );

Set<ZSetOperations.TypedTuple<String>> secondPage =
        zsets.rangeByScoreWithScores("lab:zset:scores", 20, 60, 2, 2);
```

Tham số `offset` đếm **số phần tử bỏ qua trong tập đã khớp khoảng score**, không phải score và cũng không phải rank tuyệt đối của ZSet. `count` là giới hạn số phần tử trả về.

Chú ý: `LIMIT` chỉ được dùng với `BYSCORE` hoặc `BYLEX` trong cú pháp `ZRANGE` hiện đại; để phân trang theo rank, hãy dùng hai chỉ số `start/stop`.

### 3.6. Đếm trong khoảng mà không tải dữ liệu

Nếu chỉ muốn biết có bao nhiêu member có score 20–40, không cần lấy toàn bộ rồi đếm ở Java:

```redis
ZCOUNT lab:zset:scores 20 40
```

Kết quả là `3`.

Spring:

```java
Long count = zsets.count("lab:zset:scores", 20, 40);
```

`ZCOUNT` tính số member thỏa điều kiện score. `ZCARD` (Spring `size(key)`) đếm tổng số member trong key, không xét score range. Khi chỉ kiểm tra số lượng, gửi truy vấn đếm sẽ giảm dữ liệu truyền qua mạng so với `rangeByScore` tải hết member.

## 4. Score dùng làm timestamp và cửa sổ thời gian

### 4.1. Một ứng dụng thực tế

Giả sử ứng dụng muốn sắp xếp các sự kiện theo thời điểm xảy ra. Có thể lưu mỗi event ID làm member, timestamp epoch milliseconds làm score:

```text
Key:    event:timeline:v1
Member: event:<event-id>
Score:  epoch milliseconds
```

Ví dụ Redis:

```redis
DEL lab:zset:timeline

ZADD lab:zset:timeline 1700000000000 event:a
ZADD lab:zset:timeline 1700000060000 event:b
ZADD lab:zset:timeline 1700000120000 event:c

ZRANGE lab:zset:timeline 1700000000000 1700000060000 BYSCORE WITHSCORES
```

Kết quả gồm `event:a` và `event:b`. Khi query theo score, ứng dụng không cần duyệt mọi event ID để biết event nào nằm trong khoảng thời gian.

### 4.2. Java tạo score từ Instant

```java
import java.time.Instant;

Instant occurredAt = Instant.parse("2026-11-12T08:15:30Z");
double score = occurredAt.toEpochMilli();

Boolean added = zsets.add(
        "event:timeline:v1",
        "event:order-created:1001",
        score
);
```

Dùng `toEpochMilli()` phù hợp với epoch milliseconds hiện tại, vẫn nằm trong miền số nguyên mà double có thể biểu diễn chính xác. Nhưng **epoch nanoseconds ngày nay lớn hơn miền số nguyên chính xác liên tục của IEEE-754 double**, nên không lưu nguyên nanoseconds làm score nếu cần bảo toàn mọi đơn vị nanosecond.

Một số lưu ý:

- Score là **double**, không phải kiểu ngày giờ Redis riêng biệt.
- Nếu nhiều event cùng timestamp, thứ tự phụ là **byte của member**, không phải thứ tự request tới Redis.
- Nếu sự kiện cần sắp xếp theo thứ tự chặt chẽ hơn timestamp, cần thêm một chiến lược tie-break phù hợp.
- Thay score của cùng member sẽ thay vị trí của nó, không tạo thêm một lần xuất hiện mới.

### 4.3. Score không nên dùng làm thứ tự business nếu dễ đổi

Leaderboard có thể cập nhật score thường xuyên, khiến member đổi rank. Trong một danh sách event log, nếu cùng member được `ZADD` lại với score mới, “lịch sử” bị thay vị trí. Nếu yêu cầu lưu mọi sự kiện bất biến, hãy dùng member ID duy nhất hoặc xem xét Redis Streams.

## 5. Truy vấn theo thứ tự từ điển (lex)

### 5.1. Điều kiện quan trọng nhất: các member cùng score

Redis hỗ trợ truy vấn khoảng theo thứ tự byte của member qua `ZRANGE ... BYLEX` hoặc các lệnh truyền thống `ZRANGEBYLEX`, `ZREVRANGEBYLEX`.

**Điều kiện cần:** mọi member trong ZSet dùng cho lex-range phải có **cùng score**, ví dụ đều bằng `0`. Nếu các member có score khác nhau, kết quả của truy vấn lex-range **không được Redis bảo đảm** theo thứ tự từ điển toàn cục.

Lý do: cấu trúc Sorted Set có score làm khóa sắp xếp chính. Thứ tự theo member chỉ dùng để phân giải khi hòa score; nếu các score khác nhau, một khoảng lex không còn là đoạn liên tiếp theo toàn ZSet.

Đây là cách dùng đúng:

```redis
DEL lab:zset:words
ZADD lab:zset:words 0 alpha 0 alpine 0 beta 0 bravo 0 charlie 0 delta
ZRANGE lab:zset:words 0 -1
```

Danh sách:

```text
alpha
alpine
beta
bravo
charlie
delta
```

Đây không phải “sắp xếp theo từ điển tiếng Việt” hay collation theo locale; Redis so sánh **byte nhị phân** của member.

### 5.2. Biên lex: [ và (

Redis yêu cầu mỗi biên hữu hạn của lex-range bắt đầu bằng:

- `[`: **bao gồm** member đúng bằng biên (inclusive).
- `(`: **loại trừ** member đúng bằng biên (exclusive).

Ví dụ lấy member từ `alpha` đến `charlie`, gồm cả hai:

```redis
ZRANGE lab:zset:words [alpha [charlie BYLEX
```

Kết quả:

```text
alpha
alpine
beta
bravo
charlie
```

Nếu loại `alpha` và giữ `charlie`:

```redis
ZRANGE lab:zset:words (alpha [charlie BYLEX
```

Kết quả:

```text
alpine
beta
bravo
charlie
```

Nếu cần một biên không giới hạn:

- `-` có nghĩa từ chuỗi nhỏ nhất, tương tự âm vô hạn.
- `+` có nghĩa đến chuỗi lớn nhất, tương tự dương vô hạn.

```redis
ZRANGE lab:zset:words - + BYLEX
```

Lệnh lấy toàn bộ ZSet theo thứ tự byte lex, **với điều kiện tất cả score bằng nhau**.

### 5.3. Truy vấn lex theo thứ tự ngược

Với `REV BYLEX`, **biên trên phải đặt trước, biên dưới đặt sau** ở lệnh Redis:

```redis
ZRANGE lab:zset:words [charlie [alpha BYLEX REV
```

Kết quả:

```text
charlie
bravo
beta
alpine
alpha
```

Trong Spring Data Redis, `reverseRangeByLex(key, Range<String>)` nhận một đối tượng `Range` theo nghĩa lower/upper bình thường; không cần tự đảo hai biên khi tạo `Range`.

### 5.4. Spring Data Redis dùng Range<String>

Spring Data Redis 3.x và 4.x hỗ trợ:

```java
import java.util.Set;

import org.springframework.data.domain.Range;
import org.springframework.data.redis.core.ZSetOperations;

Range<String> inclusive = Range.closed("alpha", "charlie");

Set<String> names = zsets.rangeByLex(
        "lab:zset:words", inclusive
);

Set<String> descending = zsets.reverseRangeByLex(
        "lab:zset:words", inclusive
);
```

`Range.closed(a, b)` bao gồm hai biên. Một số lựa chọn khác của `org.springframework.data.domain.Range`:

| Java Range | Ý nghĩa |
|---|---|
| `Range.closed("alpha", "charlie")` | Bao gồm `alpha` và `charlie`. |
| `Range.open("alpha", "charlie")` | Loại trừ cả hai biên. |
| `Range.leftOpen("alpha", "charlie")` | Loại trừ `alpha`, gồm `charlie`. |
| `Range.rightOpen("alpha", "charlie")` | Gồm `alpha`, loại trừ `charlie`. |
| `Range.unbounded()` | Không giới hạn hai phía. |

Chữ ký thường dùng:

```java
Set<V> rangeByLex(K key, Range<String> range);
Set<V> reverseRangeByLex(K key, Range<String> range);
```

API `rangeByLex` trả member, không có score trong kết quả mặc định. Trong mô hình đúng cho lex-range, score là như nhau; nếu cần xem score hãy lấy riêng qua `score(key, value)` hoặc thiết kế dữ liệu phù hợp.

### 5.5. Phân trang lex với Limit

Redis cho phép `LIMIT offset count` khi query lex:

```redis
ZRANGE lab:zset:words [alpha [delta BYLEX LIMIT 1 3
```

Kết quả:

```text
alpine
beta
bravo
```

Spring Data Redis:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;

Set<String> page = zsets.rangeByLex(
        "lab:zset:words",
        Range.closed("alpha", "delta"),
        Limit.limit().offset(1).count(3)
);
```

Ở đây:

- `Range.closed(...)` xác định tập member hợp lệ theo lex.
- `offset(1)` bỏ qua một member đầu của khoảng khớp.
- `count(3)` lấy tối đa ba member tiếp theo.

`Limit` dùng package `org.springframework.data.redis.connection`, không phải `org.springframework.data.domain.PageRequest`. Đừng truyền một `Pageable` vào method không hỗ trợ kiểu đó rồi kỳ vọng Spring tự chuyển.

### 5.6. Tìm theo tiền tố (prefix) với lex

Một trường hợp ứng dụng hay gặp là gợi ý các từ bắt đầu bằng `al`:

```text
alpha
alpine
beta
bravo
charlie
delta
```

Với **member chỉ gồm ký tự ASCII và quy ước định dạng phù hợp**, một khoảng có thể là:

```redis
ZRANGE lab:zset:words [al (am BYLEX
```

Kết quả:

```text
alpha
alpine
```

Lý do: các chuỗi bắt đầu bằng `al` nằm sau hoặc bằng `al` và trước chuỗi `am` theo so sánh byte ASCII. Biên `(am` có nghĩa không gồm member chính xác `am`.

Trong Spring:

```java
Range<String> prefixRange = Range.rightOpen("al", "am");

Set<String> suggestions = zsets.rangeByLex(
        "lab:zset:words",
        prefixRange,
        Limit.limit().offset(0).count(10)
);
```

Đây là minh họa cho **tiền tố ASCII**. Không có một quy tắc đơn giản là “tăng ký tự cuối” áp dụng đúng cho mọi chuỗi Unicode/UTF-8, mọi locale hay dữ liệu đã được normalize. Đối với tìm kiếm tiếng Việt có dấu, phân biệt hoa/thường hoặc natural language search, cần chuẩn hóa dữ liệu và xác định thứ tự byte/collation mong muốn; cân nhắc công cụ tìm kiếm chuyên dụng nếu cần search ngôn ngữ tự nhiên.

### 5.7. Đếm số member trong khoảng lex

Redis có `ZLEXCOUNT`:

```redis
ZLEXCOUNT lab:zset:words [alpha [charlie
```

Với dữ liệu mẫu, kết quả là `5`. Dùng `ZLEXCOUNT` nếu chỉ cần số lượng. API Spring cấp cao thường dùng `ZSetOperations.rangeByLex` để đọc member; nếu cần trực tiếp `ZLEXCOUNT`, hãy đối chiếu phương thức ở `RedisZSetCommands` / connection API hoặc Lettuce theo phiên bản dự án để tránh tải toàn bộ danh sách chỉ phục vụ đếm.

## 6. Không nhầm lex của member với so sánh ngôn ngữ tự nhiên

### 6.1. Redis so sánh byte, không theo locale

Redis xem member như byte sequence và dùng thứ tự từ điển theo byte. Điều này có vài hệ quả:

- Chữ hoa ASCII thường sắp xếp khác chữ thường, ví dụ `"A"` và `"a"` không được xem là tương đương.
- Chữ tiếng Việt có dấu trong UTF-8 không tự được sắp theo quy tắc chữ cái tiếng Việt.
- Hai chuỗi hiển thị giống nhau nhưng Unicode normalization khác nhau có thể có byte khác nhau và được xem là **hai member khác nhau**.
- JSON serialized object không phải member phù hợp để query lex theo một field bên trong; Redis so sánh **toàn bộ byte của member**.

Ví dụ:

```text
"cafe"
"café"
"cafe\u0301"
```

Hai chuỗi sau có thể trông tương tự nhưng biểu diễn Unicode khác nhau. Nếu bài toán yêu cầu tìm kiếm người dùng cuối, ứng dụng phải quy định:

1. Chuẩn hóa Unicode, ví dụ NFC.
2. Quy tắc chuyển chữ thường/hoa theo locale.
3. Có hoặc không bỏ dấu phục vụ index.
4. Tách **search key** đã chuẩn hóa khỏi **display label** nguyên bản.
5. Đồng bộ serializer và encoding giữa các service.

### 6.2. Mô hình member để gợi ý tìm kiếm

Một cách thiết kế là lưu dạng:

```text
member = <normalized-search-text>:<stable-id>
score  = 0 cho mọi member
```

Ví dụ:

```redis
DEL lab:zset:autocomplete
ZADD lab:zset:autocomplete 0 apple:101 0 application:102 0 apply:103 0 banana:201
```

Client truy vấn một khoảng byte tương ứng tiền tố `app`, nhận lại member chứa cả search text và ID:

```redis
ZRANGE lab:zset:autocomplete [app (apq BYLEX LIMIT 0 10
```

Đoạn `[app` tới `(apq` được chọn để minh họa ASCII đơn giản: mọi chuỗi bắt đầu bằng `app` nằm trước các chuỗi bắt đầu bằng `apq`. Đây là cách đóng khung prefix trong một alphabet đã kiểm soát; với Unicode hay dữ liệu tổng quát phải dùng chiến lược biên chuẩn xác hơn.

Ứng dụng có thể lấy ID rồi đọc payload hiển thị từ Redis Hash hoặc cơ sở dữ liệu. Như vậy, việc thay display name không buộc member của index phải giữ một object JSON dài và dễ thay format.

## 7. Phân trang: rank, score và lex có chi phí khác nhau

### 7.1. Phân trang bằng rank

Nếu một leaderboard có 100 member, muốn hiển thị trang 0 với 10 member:

```redis
ZRANGE leaderboard 0 9 REV WITHSCORES
```

Trang 1:

```redis
ZRANGE leaderboard 10 19 REV WITHSCORES
```

Spring:

```java
public Set<ZSetOperations.TypedTuple<String>> topPage(
        String key, long page, long pageSize) {

    if (page < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("Invalid pagination");
    }

    long start = Math.multiplyExact(page, pageSize);
    long end = Math.addExact(start, pageSize - 1);

    return zsets.reverseRangeWithScores(key, start, end);
}
```

Kiểm tra phép nhân/cộng tránh tràn `long` khi client gửi page cực lớn. Trong API thực tế, cũng nên đặt giới hạn `pageSize` tối đa.

**Rank offset không cố định trong hệ thống đang ghi.** Nếu một member mới có score cao xuất hiện trước khi client lấy trang kế, các member có thể dịch rank khiến trang sau bị trùng/mất kết quả so với một ảnh chụp nhất quán.

### 7.2. Phân trang bằng score range

Lệnh:

```redis
ZRANGE leaderboard 50 100 BYSCORE LIMIT 20 10 WITHSCORES
```

bỏ 20 member đầu có score trong khoảng 50–100 rồi lấy tối đa 10 member tiếp theo.

Cách này phù hợp khi người dùng thực sự đang lọc theo **miền điểm**, không phải toàn bộ bảng rank.

Tuy vậy, `LIMIT` offset lớn có thể đòi hỏi Redis bỏ qua nhiều phần tử trước khi trả dữ liệu. Với tập kết quả rất lớn và truy vấn sâu, cần cân nhắc cursor/range tiếp diễn hoặc cấu trúc index khác.

### 7.3. Khi nhiều member có cùng score

Giả sử:

```text
alice(10), bob(20), carol(20), dave(20), erin(30)
```

Sau khi đọc đến `bob(20)`, nếu trang kế chỉ query `score > 20`, bạn **bỏ qua carol và dave** vì họ cũng có score 20.

Một cursor chính xác cần xét **cặp (score, member)** theo thứ tự so sánh mà Redis sử dụng, hoặc dùng một cách phân trang ổn định khác. Redis range-by-score một mình không mang điều kiện “score bằng và member lớn hơn X” của một composite cursor; ứng dụng cần thiết kế chiến lược truy vấn/tiếp diễn đầy đủ, có thể dùng script hoặc một index phụ.

Không tạo score “20.000000001” một cách tùy tiện để phân biệt member hòa điểm; giới hạn chính xác double và việc cập nhật dữ liệu có thể tạo lỗi khó truy vết.

### 7.4. Cursor lex và tiền tố

Với index lex có **cùng score**, các member được sắp theo byte; ứng dụng có thể dùng member cuối đã đọc làm mốc tiếp diễn:

```text
Trang 1: các member trong khoảng [start, end), LIMIT 0 10
Trang 2: các member > lastMember, dưới end, LIMIT 0 10
```

Trong Spring có thể dùng `Range.leftOpen(lastMember, upperBound)` khi cần loại trừ member đã trả. Tuy nhiên, việc thêm/xóa member giữa hai trang vẫn khiến toàn bộ kết quả **không phải một snapshot bất biến**.

Với yêu cầu snapshot chính xác (ví dụ báo cáo tài chính), phải thiết kế cơ chế snapshot, version hoặc storage khác thay vì coi các câu lệnh range ở những thời điểm khác nhau là một transaction.

## 8. Chi tiết quan trọng: score là double, member là byte

### 8.1. Không dùng score cho số nguyên lớn không thể biểu diễn chính xác

Redis lưu score bằng số thực double. Các số nguyên có trị tuyệt đối **không quá 2^53** có thể được biểu diễn chính xác theo phạm vi liên tục của IEEE-754, trong khi số nguyên lớn hơn có thể bị làm tròn.

Ví dụ timestamp epoch milliseconds vào thời điểm hiện nay nằm trong giới hạn tiện dụng, nhưng epoch nanoseconds có độ lớn vượt quá 2^53.

Không nên coi score là nơi lưu ID 64-bit chính xác bất kỳ. Nếu cần ID 64-bit, đặt nó trong member (kèm codec định dạng) và dùng score theo nghĩa riêng.

### 8.2. Member không tự là JSON object

Với `StringRedisTemplate`, Redis member thường là chuỗi UTF-8. Với `RedisTemplate<String, MyObject>`, member có thể được serializer chuyển thành JSON hoặc byte nhị phân. Điều này ảnh hưởng trực tiếp đến:

- Thứ tự lex giữa member.
- Cách member được nhận diện là trùng nhau.
- Khả năng tìm bằng `rank(key, value)` hoặc `score(key, value)`.
- Kết quả nếu serializer đổi giữa hai phiên bản ứng dụng.

Muốn query lex có ý nghĩa, hãy dùng **chuỗi khóa index ổn định và được chuẩn hóa**, thay vì hy vọng JSON serializer tự sinh thứ tự theo một thuộc tính trong object.

### 8.3. TTL áp dụng cho key, không riêng member

Redis TTL thông thường đặt cho **toàn bộ Sorted Set key**:

```redis
EXPIRE leaderboard 3600
TTL leaderboard
```

Nó không có nghĩa “mỗi member tự hết hạn sau một giờ kể từ lúc `ZADD`”. Nếu score là timestamp và cần xóa event cũ, có thể dùng `ZREMRANGEBYSCORE` theo một cutoff; đó là cơ chế chủ động dọn dữ liệu theo score, khác với TTL của key.

Ví dụ:

```redis
ZREMRANGEBYSCORE event:timeline:v1 -inf 1700000000000
```

Lệnh xóa các event có score đến cutoff **bao gồm**. Cần phân biệt: khi query `ZRANGE ... BYSCORE` chỉ **đọc**, còn `ZREMRANGEBYSCORE` **xóa** dữ liệu.

## 9. Xây dựng service đọc Sorted Set với Spring Data Redis

### 9.1. Khởi tạo dữ liệu mẫu bằng Spring

Khi dự án Spring Boot đã có dependency `spring-boot-starter-data-redis` và kết nối Redis hoạt động:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Component;

@Component
public class ScoreSeed {

    private final ZSetOperations<String, String> zsets;

    public ScoreSeed(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    public void seed() {
        String key = "lab:zset:scores";

        zsets.add(key, "alice", 10.0);
        zsets.add(key, "bob", 20.0);
        zsets.add(key, "carol", 20.0);
        zsets.add(key, "dave", 40.0);
        zsets.add(key, "erin", 60.0);
    }
}
```

Đây là ví dụ minh họa cách ghi; vì `ZADD` cập nhật score của member đã có, nó không xóa các member khác còn sót lại từ lần chạy trước. Để có môi trường thực hành xác định, nên xóa **key lab riêng** trước khi seed.

### 9.2. Một service đọc theo rank, score và lex

```java
import java.util.Set;

import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class ZSetQueryService {

    private final ZSetOperations<String, String> zsets;

    public ZSetQueryService(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    // Lấy một lát cắt tăng dần theo rank.
    public Set<String> byRank(String key, long from, long to) {
        return zsets.range(key, from, to);
    }

    // Lấy top member có score cao nhất, kèm score.
    public Set<ZSetOperations.TypedTuple<String>> topWithScores(
            String key, long size) {

        if (size < 1 || size > 1000) {
            throw new IllegalArgumentException("size must be 1..1000");
        }

        return zsets.reverseRangeWithScores(key, 0, size - 1);
    }

    // Lọc theo khoảng score, hai biên inclusive.
    public Set<ZSetOperations.TypedTuple<String>> byScore(
            String key, double min, double max) {

        if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
            throw new IllegalArgumentException("Invalid score interval");
        }

        return zsets.rangeByScoreWithScores(key, min, max);
    }

    // Lấy khoảng lex với phân trang.
    // Key này phải chứa các member có cùng score.
    public Set<String> byLex(
            String key, String from, String to, int offset, int count) {

        if (offset < 0 || count <= 0 || count > 1000) {
            throw new IllegalArgumentException("Invalid pagination");
        }

        return zsets.rangeByLex(
                key,
                Range.closed(from, to),
                Limit.limit().offset(offset).count(count)
        );
    }

    public Long rankFromTop(String key, String member) {
        return zsets.reverseRank(key, member);
    }

    public Double memberScore(String key, String member) {
        return zsets.score(key, member);
    }
}
```

**Phạm vi của ví dụ:** code dùng đồng bộ qua `StringRedisTemplate`; không xử lý pipeline/transaction hoặc retry. Method trả `Set`/`Long`/`Double` có thể nhận `null` theo API trong pipeline/transaction, và `rank`/`score` có thể trả null khi member không có trong ZSet.

Điều kiện `Double.isFinite` trong phương thức `byScore` là chính sách validate của service mẫu, không phải vì Redis không hỗ trợ biên `-inf` hoặc `+inf`. Nếu nghiệp vụ cần truy vấn biên vô hạn, thiết kế API cho phép hai biên đặc biệt một cách rõ ràng.

### 9.3. Dùng bound operations cho cùng một key

Khi một service thường xuyên truy vấn cùng key:

```java
import java.util.Set;
import org.springframework.data.redis.core.BoundZSetOperations;

BoundZSetOperations<String, String> ranking =
        stringRedisTemplate.boundZSetOps("leaderboard:weekly");

Set<String> top = ranking.reverseRange(0, 9);
Set<String> qualified = ranking.rangeByScore(70, 100);
```

`BoundZSetOperations` gắn key vào đối tượng thao tác, tránh truyền tên key ở mỗi lần gọi. Nó **không tạo snapshot, khóa giao dịch hoặc kết nối chuyên biệt** chỉ vì được “bound”; semantics truy vấn vẫn như thao tác trên Redis.

## 10. Ví dụ theo tình huống nghiệp vụ

### 10.1. Bảng xếp hạng top 10

Yêu cầu: hiển thị mười user có điểm cao nhất, gồm điểm.

```java
Set<ZSetOperations.TypedTuple<String>> topTen =
        zsets.reverseRangeWithScores("leaderboard:season-1", 0, 9);
```

Có thể lấy rank của một user:

```java
Long zeroBasedRank = zsets.reverseRank("leaderboard:season-1", userId);

Long displayRank = zeroBasedRank == null
        ? null
        : zeroBasedRank + 1;
```

Redis rank bắt đầu từ 0, còn UI thường hiển thị thứ hạng bắt đầu từ 1. Nếu có nhiều người cùng score, Redis vẫn có **thứ tự xác định theo member byte**, nhưng không có nghĩa ứng dụng nghiệp vụ nên gán “hạng 1 cùng điểm” hay “hạng 2” tùy ý. Quy tắc đồng hạng hiển thị phải được định nghĩa riêng.

### 10.2. Timeline theo khoảng thời gian

Yêu cầu: lấy event từ `from` đến `to` theo UTC.

```java
import java.time.Instant;

public Set<String> eventsBetween(
        ZSetOperations<String, String> zsets,
        String key,
        Instant from,
        Instant to) {

    if (from.isAfter(to)) {
        throw new IllegalArgumentException("from is after to");
    }

    return zsets.rangeByScore(
            key,
            from.toEpochMilli(),
            to.toEpochMilli()
    );
}
```

Truy vấn này **bao gồm hai đầu**. Nếu hệ thống định nghĩa khoảng thời gian `[from, to)` (loại trừ thời điểm cuối), cần dùng biên mở phù hợp ở lệnh Redis hoặc tầng connection thay vì suy đoán rằng chỉ cần trừ một số tùy ý khỏi timestamp. Với epoch milliseconds rời rạc và hợp đồng chắc chắn, một cách riêng có thể dùng toMillis−1, nhưng phải chú ý tràn số và đơn vị; sử dụng biên mở thường rõ nghĩa hơn.

### 10.3. Gợi ý theo tiền tố ASCII

Yêu cầu: lấy tối đa 10 mã bắt đầu bằng `al` từ index có mọi score bằng 0.

```java
Set<String> suggestionIds = zsets.rangeByLex(
        "autocomplete:ascii:v1",
        Range.rightOpen("al", "am"),
        Limit.limit().offset(0).count(10)
);
```

Nếu cần tìm kiếm tiếng Việt có dấu, áp dụng quy tắc normalize/index riêng; không giả định byte ordering có thể thay thế thứ tự từ điển ngôn ngữ tự nhiên.

### 10.4. Top theo score trong một phân khúc

Giả sử chỉ lấy thành viên có điểm 50–90, sắp cao xuống thấp:

```java
Set<ZSetOperations.TypedTuple<String>> topQualified =
        zsets.reverseRangeByScoreWithScores(
                "leaderboard:weekly", 50, 90, 0, 20);
```

Tham số `0, 20` là phân trang kết quả, còn `50, 90` là khoảng score. Dùng một truy vấn trực tiếp với Redis thay vì tải toàn bảng rồi filter/sort trong Java.

## 11. Tính nguyên tử và biến động vị trí khi nhiều client cùng ghi

### 11.1. Rank thay đổi khi score đổi

Giả sử bảng xếp hạng ban đầu:

```text
alice(10), bob(20), carol(20), dave(40), erin(60)
```

Client A đọc top 3. Giữa hai lần request, client B cập nhật `bob` từ 20 lên 100. Bảng mới:

```text
alice(10), carol(20), dave(40), erin(60), bob(100)
```

Nếu client A lấy trang 2 bằng `offset 3` theo rank cũ, có thể nhận phần tử khác với kỳ vọng. Redis đảm bảo từng lệnh range phản ánh trạng thái ở lúc xử lý lệnh; nó **không đảm bảo một loạt truy vấn phân trang là cùng snapshot**.

### 11.2. Tìm rank rồi truy vấn rank không nguyên tử như một workflow

Ví dụ:

```java
Long rank = zsets.reverseRank(key, member);
if (rank != null) {
    Set<String> neighbors = zsets.reverseRange(key, rank - 2, rank + 2);
}
```

Nếu giữa hai lệnh có cập nhật score, cửa sổ `neighbors` có thể không còn bao quanh member. Nếu cần kết quả nhất quán cho cả rank và lân cận, cân nhắc Lua script, transaction có phương án đọc nhất quán hoặc một thiết kế snapshot/version tùy yêu cầu.

Lưu ý thêm về index: `rank - 2` có thể âm, mà chỉ số âm trong `ZRANGE` có ý nghĩa “đếm từ cuối” chứ không phải “giới hạn dưới là 0”. Nếu chỉ muốn hai thành viên trước rank, phải clamp rõ ràng:

```java
long start = Math.max(0L, rank - 2);
long end = rank + 2;
```

### 11.3. Redis là nguồn sắp xếp, nhưng hợp đồng nghiệp vụ quyết định hạng

Nếu hai user đều có score 100, Redis vẫn sắp theo member byte. Với ứng dụng muốn **đồng hạng**, cần cách tính riêng:

- **Dense ranking:** điểm giống nhau cùng hạng, không bỏ số hạng kế.
- **Competition ranking:** điểm giống nhau cùng hạng, hạng sau có thể nhảy số.
- **Unique ordering:** mọi user có rank riêng theo cặp (score, member) như ZSet.

`ZREVRANK` thực hiện kiểu thứ ba, không tự làm dense ranking theo score. Cần phân biệt thứ tự hiển thị (order) với quy tắc trao giải/hạng nghiệp vụ.

## 12. Hiệu năng và độ phức tạp

### 12.1. Tại sao truy vấn range thường hiệu quả?

ZSet được tối ưu để truy cập theo score và rank. Những lệnh range phổ biến thường có độ phức tạp dạng:

```text
O(log(N) + M)
```

với:

- `N` là số member trong Sorted Set.
- `M` là số member được trả hoặc xử lý.

Điều này rất hữu ích khi cần top 10 của ZSet lớn: Redis không phải gửi toàn bộ hàng triệu member cho Java rồi sort tại application.

Tuy nhiên, những yếu tố sau có thể làm tăng chi phí thực tế:

- Yêu cầu trả quá nhiều member trong một lần.
- `LIMIT offset` lớn ở score/lex range khiến Redis phải bỏ qua nhiều member.
- Dữ liệu member có JSON/binary payload lớn, làm tăng serialization và băng thông.
- Đồng thời có nhiều truy vấn nặng hoặc script chặn Redis.
- Redis chạy với network latency cao, TLS, hoặc môi trường Cluster có routing khác nhau.

### 12.2. Có nên `ZRANGE key 0 -1` trên ZSet rất lớn?

Không nên dùng mặc định trong endpoint người dùng nếu ZSet có thể tăng không giới hạn. Lệnh có thể gửi nhiều dữ liệu, tốn thời gian Redis, mạng và bộ nhớ Java.

Thay bằng:

- Rank page có kích thước giới hạn.
- Score/lex range có LIMIT phù hợp.
- Query count riêng nếu chỉ muốn đếm.
- Mô hình precompute hoặc index riêng khi có nhiều chiều lọc.

### 12.3. Redis Cluster và tính cùng slot

Một lệnh `ZRANGE` đọc **một key**, nên trong Redis Cluster, driver có thể định tuyến tới node giữ hash slot của key. Nhưng nếu một nghiệp vụ muốn lấy ZSet A rồi giao/kết hợp với ZSet B bằng lệnh nhiều key, quy tắc cùng hash slot có thể áp dụng cho thao tác tương ứng.

Không nhầm việc query từng key riêng lẻ với việc nhiều key được đọc nhất quán trong một thao tác nguyên tử.

## 13. Các lỗi điển hình và cách điều tra

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ZRANGE key 20 40` trả rỗng dù có score 20–40 | Quên `BYSCORE`, Redis hiểu 20/40 là rank | Dùng `ZRANGE ... BYSCORE` hoặc `rangeByScore`. |
| Top 10 trả điểm thấp nhất | Dùng `range(0,9)` thay vì `reverseRange(0,9)` | Dùng thứ tự giảm. |
| `REV BYSCORE` trả rỗng | Đặt min trước max như chiều thường ở cú pháp Redis | Với CLI `REV BYSCORE`, đặt **max trước min**. |
| Java `reverseRangeByScore` trả sai khoảng | Đảo min/max khi gọi Java | Spring API nhận `min, max` như thông thường. |
| Lex query trả dữ liệu bất thường | ZSet có score khác nhau | Tách key lex index riêng, cho mọi member cùng score. |
| Tìm theo tiền tố tiếng Việt sai thứ tự | Redis so sánh byte, không theo locale | Chuẩn hóa index, dùng công cụ collation/search phù hợp. |
| `rank()` hoặc `score()` trả null | Member vắng mặt hoặc callback pipeline/transaction chưa có phản hồi | Phân biệt ngữ cảnh; tránh unbox null. |
| `WITHSCORES` hiển thị số lẻ bất ngờ | Score dùng double | Thống nhất thang điểm, lưu ý IEEE-754 và serializer. |
| Một member “bị mất” sau ZADD | `ZADD` cùng member cập nhật score thay vì tạo bản sao | Kiểm tra member ID, `ZCARD` và `ZSCORE`. |
| Trang sau có item lặp/mất | Rank thay đổi vì update; nhiều item cùng score | Chấp nhận eventual pagination hoặc dùng chiến lược cursor/snapshot. |
| `WRONGTYPE` | Key hiện chứa String/Hash/List, không phải ZSet | Kiểm tra `TYPE key` và namespace. |
| `LIMIT` không hoạt động ở rank range | `ZRANGE ... LIMIT` chỉ dùng với BYSCORE/BYLEX | Dùng `start/stop` theo rank. |
| Query chậm dù chỉ lấy ít member | Offset lớn, nhiều dữ liệu hoặc tải Redis cao | Đo latency, giảm offset, giới hạn dữ liệu và xem lại model. |

### 13.1. Các lệnh chẩn đoán hữu ích

```redis
TYPE lab:zset:scores
ZCARD lab:zset:scores
ZSCORE lab:zset:scores carol
ZRANK lab:zset:scores carol
ZREVRANK lab:zset:scores carol
ZCOUNT lab:zset:scores 20 40
ZRANGE lab:zset:scores 0 4 WITHSCORES
TTL lab:zset:scores
```

Các lệnh này cho biết kiểu key, kích thước ZSet, score của member, thứ hạng, số lượng trong một khoảng và TTL toàn key.

Chỉ nên dùng các lệnh quan sát trên namespace đã xác định; dữ liệu production có thể chứa member nhạy cảm, không đưa nguyên văn vào log/issue chia sẻ.

## 14. Bài thực hành tổng hợp

### 14.1. Thực hành A: bảng xếp hạng

Khởi tạo dữ liệu:

```redis
DEL lab:practice:rank
ZADD lab:practice:rank 11 ann 30 ben 30 chris 42 dana 70 evan
```

Thực hiện:

```redis
ZRANGE lab:practice:rank 0 2 WITHSCORES
ZRANGE lab:practice:rank 0 2 REV WITHSCORES
ZRANK lab:practice:rank chris
ZREVRANK lab:practice:rank chris
ZRANGE lab:practice:rank 30 42 BYSCORE WITHSCORES
```

Kết quả mong đợi:

1. Tăng dần: `ann(11), ben(30), chris(30)`.
2. Giảm dần: `evan(70), dana(42), chris(30)`.
3. `ZRANK chris` trả `2`.
4. `ZREVRANK chris` trả `2`.
5. Trong khoảng score 30–42: `ben(30), chris(30), dana(42)`.

### 14.2. Thực hành B: biên điểm và trang

Vẫn trên dữ liệu `lab:practice:rank`:

```redis
ZRANGE lab:practice:rank (30 70 BYSCORE WITHSCORES
ZRANGE lab:practice:rank (30 (70 BYSCORE WITHSCORES
ZRANGE lab:practice:rank 70 30 BYSCORE REV WITHSCORES
ZRANGE lab:practice:rank 30 70 BYSCORE LIMIT 1 2 WITHSCORES
ZCOUNT lab:practice:rank 30 70
```

Diễn giải:

- `(30 70` bỏ các member có score đúng 30, giữ 70.
- `(30 (70` chỉ giữ member có score nằm giữa hai biên, ví dụ `dana(42)`.
- `70 30 BYSCORE REV` trả giảm dần, gồm 70, 42 và hai member 30.
- `LIMIT 1 2` bỏ thành viên khớp đầu rồi lấy hai member.
- `ZCOUNT 30 70` đếm các member thỏa 30–70, kết quả 4.

### 14.3. Thực hành C: thứ tự từ điển

Dùng key riêng, tất cả score bằng 0:

```redis
DEL lab:practice:lex
ZADD lab:practice:lex 0 apple 0 application 0 apply 0 apricot 0 banana

ZRANGE lab:practice:lex - + BYLEX
ZRANGE lab:practice:lex [app (apq BYLEX
ZRANGE lab:practice:lex [banana [app BYLEX REV
ZLEXCOUNT lab:practice:lex [app (apq
```

Kết quả dự kiến:

- Toàn bộ: `apple, application, apply, apricot, banana`.
- Prefix ASCII `app`: `apple, application, apply`.
- `REV` từ `banana` tới `app`: `banana, apricot, apply, application, apple`.
- `ZLEXCOUNT` cho khoảng `[app, apq)`: `3`.

Lưu ý lệnh `REV BYLEX` có **biên trên trước**; nếu hai biên bị đặt ngược, kết quả có thể rỗng.

### 14.4. Thực hành D: Spring Data Redis

Giả sử bạn có `StringRedisTemplate redis`:

```java
import java.util.Set;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;
import org.springframework.data.redis.core.ZSetOperations;

ZSetOperations<String, String> zset = redis.opsForZSet();

Set<String> firstThree =
        zset.range("lab:practice:rank", 0, 2);

Set<ZSetOperations.TypedTuple<String>> bestThree =
        zset.reverseRangeWithScores("lab:practice:rank", 0, 2);

Set<String> from30To42 =
        zset.rangeByScore("lab:practice:rank", 30, 42);

Set<String> wordPrefix =
        zset.rangeByLex(
                "lab:practice:lex",
                Range.rightOpen("app", "apq"),
                Limit.limit().offset(0).count(10)
        );
```

Các truy vấn lần lượt minh họa rank, reverse rank với score, score interval và lex prefix.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** ZSet có `A(5), B(5), C(10)`. Kết quả `ZRANGE key 0 -1` là gì?

**Đáp án:** `A, B, C` nếu so sánh byte member ASCII cho thấy `A < B`. Score chính, byte lex phụ.

**Câu 2.** Khi muốn lấy top 3 từ score cao đến thấp, dùng `range` hay `reverseRange`?

**Đáp án:** `reverseRange(key, 0, 2)`. Muốn điểm đi kèm, dùng `reverseRangeWithScores`.

**Câu 3.** `ZRANGE key 10 100` có lọc score 10 đến 100 không?

**Đáp án:** không. Không có `BYSCORE`, 10 và 100 là rank. Dùng `ZRANGE key 10 100 BYSCORE` hoặc `rangeByScore(key, 10, 100)`.

**Câu 4.** `ZRANGE key (10 20 BYSCORE` có bao gồm score 10, 20 không?

**Đáp án:** loại 10, gồm 20.

**Câu 5.** Tại sao lex query trong ZSet có score khác nhau không đáng tin cậy?

**Đáp án:** Redis sắp xếp theo score trước, nên member không nằm theo một trật tự lex toàn cục nếu score khác. Truy vấn BYLEX được xác định có nghĩa khi các member đều có score bằng nhau.

**Câu 6.** Redis có tự sắp tiếng Việt có dấu đúng quy tắc từ điển không?

**Đáp án:** không. Redis so sánh byte của member, không thực hiện Unicode collation theo ngôn ngữ.

**Câu 7.** `ZREVRANK` trả 0 nghĩa là gì?

**Đáp án:** member đang đứng đầu theo thứ tự score giảm, có xét thứ tự byte đảo khi đồng score.

**Câu 8.** Trang kế query `score > lastScore` có thể bỏ sót dữ liệu nào?

**Đáp án:** các member còn lại có **cùng score bằng lastScore** nhưng chưa được trả ở trang trước.

**Câu 9.** Thay score của một member bằng `ZADD` có tạo bản sao member không?

**Đáp án:** không. Member là duy nhất; score của member đó được cập nhật.

**Câu 10.** `ZCOUNT` khác `ZCARD` thế nào?

**Đáp án:** `ZCOUNT` chỉ đếm member trong khoảng score; `ZCARD` đếm toàn bộ member trong key.

## 16. Ghi nhớ

Ba kiểu truy vấn Sorted Set dùng một nền tảng dữ liệu nhưng phục vụ ba ý định khác nhau:

- **Theo vị trí:** `range/reverseRange` và `ZRANGE`, chỉ số từ 0; thích hợp bảng xếp hạng và lấy top N.
- **Theo điểm số:** `rangeByScore/reverseRangeByScore` và `ZRANGE ... BYSCORE`, lọc khoảng số có biên đóng/mở; thích hợp timeline và lọc theo ngưỡng.
- **Theo thứ tự từ điển:** `rangeByLex/reverseRangeByLex` và `ZRANGE ... BYLEX`; thích hợp prefix/index member **khi tất cả member cùng score**, với thứ tự byte chứ không phải collation theo ngôn ngữ.

Luôn xác định rõ **khoảng đang là rank, score hay chuỗi byte**, chiều sắp xếp và cách hiểu biên trước khi gọi API. Khi dữ liệu thay đổi đồng thời, rank và phân trang có thể dịch; khi có nhiều member hòa score, cursor chỉ theo score có thể bỏ sót. Đối với những yêu cầu cần snapshot hoặc tìm kiếm theo locale, hãy thiết kế bổ sung thay vì chỉ dựa vào một lệnh range.

### Tài liệu chính thức

- [Redis — Sorted Sets](https://redis.io/docs/latest/data-types/sorted-sets/): mô hình member/score và thứ tự trong ZSet.
- [Redis — ZRANGE](https://redis.io/docs/latest/commands/zrange/): rank range, `BYSCORE`, `BYLEX`, `REV`, `LIMIT`, `WITHSCORES`.
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/): cập nhật score, member duy nhất và thứ tự khi hòa điểm.
- [Redis — ZRANGEBYSCORE](https://redis.io/docs/latest/commands/zrangebyscore/): khoảng score, biên mở/đóng và LIMIT.
- [Redis — ZRANGEBYLEX](https://redis.io/docs/latest/commands/zrangebylex/): lex-range, cùng score và so sánh byte.
- [Redis — ZCOUNT](https://redis.io/docs/latest/commands/zcount/), [ZLEXCOUNT](https://redis.io/docs/latest/commands/zlexcount/): đếm theo khoảng.
- [Redis — ZRANK](https://redis.io/docs/latest/commands/zrank/), [ZREVRANK](https://redis.io/docs/latest/commands/zrevrank/): rank tăng và giảm.
- [Spring Data Redis — ZSetOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ZSetOperations.html): Java APIs cho rank, score, lex và TypedTuple.
- [Spring Data Redis — BoundZSetOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/BoundZSetOperations.html): thao tác với key đã bind.
- [Spring Data Commons — Range API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Range.html): khoảng biên đóng/mở ở Java.
- [Spring Data Redis — Limit API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/Limit.html): offset/count cho lex/score ranges.
