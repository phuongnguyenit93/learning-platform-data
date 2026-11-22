# Thành viên, điểm số và thứ tự trong Sorted Set của Spring Data Redis

**Redis Sorted Set (ZSET)** là một tập hợp có các **thành viên không trùng nhau (member)**; mỗi thành viên gắn với một **điểm số (score)**. Redis dùng score để duy trì thứ tự tự động, vì vậy ứng dụng có thể lấy phần tử điểm cao nhất, xem thứ hạng, truy vấn theo khoảng điểm hoặc cập nhật điểm mà không cần đọc toàn bộ tập hợp về Java để sắp xếp lại.

Trong **Spring Data Redis**, thao tác với Sorted Set thường được thực hiện qua `ZSetOperations<K, V>`, chẳng hạn `StringRedisTemplate.opsForZSet()`. API của Spring giúp dùng các lệnh Redis như `ZADD`, `ZSCORE`, `ZRANK`, `ZREVRANK` và `ZRANGE` với kiểu dữ liệu Java quen thuộc. Tuy nhiên, để xây dựng bảng xếp hạng hoặc danh sách ưu tiên đúng, cần phân biệt rõ **member**, **score**, **rank**, **thứ tự tăng/giảm**, **quy tắc xử lý khi bằng điểm** và **định dạng serializer**.

Bài học giải thích trực tiếp các khái niệm đó, bao gồm ví dụ Redis CLI, cách gọi Spring Data Redis, các quy tắc khi cập nhật cùng member, sự khác biệt giữa xếp hạng theo điểm và theo thời gian, hiệu năng, cạnh tranh đồng thời và bài thực hành cuối bài.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích Sorted Set khác `Set` và `List` ở điểm nào.
2. Nhận biết rằng **một member chỉ xuất hiện một lần trong cùng ZSET**, còn nhiều member có thể có cùng score.
3. Hiểu score có bản chất số thực dấu phẩy động kiểu **double**, các giới hạn độ chính xác và những hệ quả khi lưu số lớn.
4. Giải thích thứ tự mặc định **score tăng dần** và cách Redis xử lý **hai member bằng score**.
5. Dùng `ZADD`, `ZSCORE`, `ZCARD`, `ZRANK`, `ZREVRANK`, `ZRANGE`, `ZREM`, `ZINCRBY`.
6. Dùng các phương thức tương ứng của `ZSetOperations` để lưu, đọc điểm, lấy top N, tra thứ hạng và thay đổi score.
7. Tránh nhầm **rank tính từ 0** với thứ hạng hiển thị cho người dùng tính từ 1.
8. Thiết kế key và member nhất quán giữa các writer, chọn serializer phù hợp và xác định nguồn dữ liệu chính.
9. Phân biệt xếp hạng theo **điểm** với yêu cầu truy vấn theo **thời điểm/độ ưu tiên**; biết khi nào Sorted Set phù hợp hoặc không phù hợp.

**Kiến thức chuẩn bị:** Java, Spring Boot, Dependency Injection, `StringRedisTemplate` và các lệnh Redis cơ bản. Mã minh họa dùng Java 17+, Spring Boot 3.x và Spring Data Redis 3.x; tên API cơ bản của `ZSetOperations` cũng xuất hiện ở các dòng phiên bản gần đó, nhưng cần kiểm tra dependency của dự án.

## 2. Ba khái niệm cốt lõi: key, member và score

Một Redis Sorted Set được lưu dưới **một key Redis**. Bên trong key có nhiều **member** và mỗi member được gán **một score**.

Ví dụ bảng điểm:

~~~text
Redis key: game:season-1:leaderboard

              Sorted Set
       +------------+--------+
       | member     | score  |
       +------------+--------+
       | player:17  |   90   |
       | player:42  |  120   |
       | player:93  |  120   |
       | player:58  |  150   |
       +------------+--------+
~~~

- **Key** `game:season-1:leaderboard` nhận diện toàn bộ bảng xếp hạng.
- **Member** `player:42` nhận diện một phần tử bên trong tập hợp.
- **Score** `120` là giá trị dùng để định vị phần tử khi Redis sắp xếp.
- **Rank** là vị trí của phần tử trong thứ tự đã chọn. Redis bắt đầu từ **0**, còn UI có thể chuyển thành 1, 2, 3…

Nếu trong cùng bảng xếp hạng đã có member `player:42` với score 120, lệnh cập nhật member đó thành 160 **không tạo thêm một player:42 thứ hai**. Redis thay score và tự thay đổi vị trí của member.

### 2.1. So sánh Set, List và Sorted Set

| Cấu trúc | Có phần tử trùng? | Có thứ tự không? | Cơ chế thứ tự | Khi thích hợp |
| --- | --- | --- | --- | --- |
| Redis Set | Không | Không bảo đảm thứ tự đọc | Không có rank theo score | Tập tag, danh sách ID duy nhất |
| Redis List | Có | Có | Vị trí trái/phải, thứ tự thêm/xóa | Lịch sử gần đây, queue đơn giản |
| Redis Sorted Set | **Không trùng member** | **Có** | Score tăng dần; xử lý tie theo member | Bảng xếp hạng, lịch hẹn, ưu tiên, điểm số |

Điểm quan trọng: Sorted Set không phải “Set có giữ thứ tự chèn”. Vị trí của member có thể thay đổi bất cứ khi nào score được cập nhật. Nếu nghiệp vụ cần giữ lịch sử **tất cả lần tham gia** của cùng một người, không thể lưu mọi lần bằng cùng một member ID và kỳ vọng ZSET giữ đủ bản ghi; cần member ID theo từng sự kiện hoặc cấu trúc lưu lịch sử khác.

## 3. Tạo Sorted Set bằng Redis CLI

Giả sử chúng ta lưu điểm của bốn người chơi:

~~~redis
DEL demo:leaderboard
ZADD demo:leaderboard 120 alice 95 bob 120 carol 80 david
TYPE demo:leaderboard
ZCARD demo:leaderboard
ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

Kết quả mong đợi:

~~~text
TYPE  => zset
ZCARD => 4

Thứ tự tăng dần khi ZRANGE:
  david   80
  bob     95
  alice  120
  carol  120
~~~

Lệnh `ZADD key score member [score member ...]` có thể thêm nhiều cặp score/member trong một lệnh. Redis duy trì tập hợp theo **score**, rồi dùng member để phân định vị trí khi score bằng nhau.

### 3.1. Vì sao Alice đứng trước Carol?

Alice và Carol cùng score 120. Khi score bằng nhau, Redis sắp thứ tự thành viên theo **thứ tự từ điển dựa trên các byte của member**, nên `alice` đứng trước `carol` trong chiều tăng dần.

Điều này **không phải** thứ tự người nào được thêm trước, không phải quy tắc sắp xếp tiếng Việt và không sử dụng tên hiển thị theo locale. Nếu member là ID khác nhau nhưng cùng score, thứ tự tie-break dựa trên **bytes của chính member được Redis lưu**.

### 3.2. Thêm một member chưa có

~~~redis
ZADD demo:leaderboard 110 erin
ZCARD demo:leaderboard
ZSCORE demo:leaderboard erin
~~~

`ZCARD` trở thành 5; `ZSCORE` của `erin` là 110. Trong chế độ bình thường, số nguyên trả về từ `ZADD` đếm **member mới được thêm**, không nhất thiết là số member có score thay đổi.

### 3.3. Cập nhật score của member đã có

~~~redis
ZADD demo:leaderboard 140 bob
ZCARD demo:leaderboard
ZSCORE demo:leaderboard bob
ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

`bob` đã tồn tại, nên `ZADD` cập nhật score từ 95 lên 140. **ZCARD vẫn bằng 5**: không sinh member Bob thứ hai. Bob tự di chuyển đến vị trí phù hợp với score 140.

Phân biệt hai thao tác:

- **Thêm hoặc đặt score tuyệt đối:** `ZADD key 140 bob`.
- **Cộng điểm vào score hiện có:** `ZINCRBY key 10 bob`.

Nếu Bob đang có 140, `ZINCRBY key 10 bob` làm score thành 150. Nếu Bob chưa có trong ZSET, `ZINCRBY` coi score cũ là 0 và tạo member với score mới.

## 4. Thứ tự tăng dần, giảm dần và ý nghĩa của “đầu bảng”

Redis Sorted Set có thứ tự mặc định **tăng dần theo score**. Nhiều bảng xếp hạng người chơi lại muốn điểm cao nhất đứng đầu. Hai nhu cầu này dùng hai hướng đọc khác nhau.

Với dữ liệu ban đầu:

~~~text
member   score
david      80
bob        95
alice     120
carol     120
~~~

**Tăng dần:**

~~~redis
ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

Kết quả:

~~~text
david 80 -> bob 95 -> alice 120 -> carol 120
~~~

**Giảm dần:**

~~~redis
ZRANGE demo:leaderboard 0 -1 REV WITHSCORES
~~~

Kết quả:

~~~text
carol 120 -> alice 120 -> bob 95 -> david 80
~~~

Với Redis hiện đại, `ZRANGE ... REV` là cách diễn đạt phổ biến cho truy vấn theo thứ tự giảm dần. Bạn cũng sẽ gặp lệnh `ZREVRANGE` trong nhiều ví dụ và API cũ; từ Redis 6.2, `ZREVRANGE` được đánh dấu deprecated để ưu tiên `ZRANGE ... REV`. Spring Data Redis vẫn cung cấp các phương thức `reverseRange(...)` tương ứng để thao tác thuận tiện.

### 4.1. Tie-break cũng đảo chiều

Hai member bằng score 120:

~~~text
Tăng dần: alice trước carol
Giảm dần: carol trước alice
~~~

Đảo chiều không chỉ đảo score; Redis đảo cả thứ tự member trong nhóm có cùng score. Với bảng xếp hạng, đừng hứa rằng “ai đạt 120 trước thì đứng trên” nếu bạn chỉ lưu score 120 trong một ZSET. **Thời gian đạt điểm không tự trở thành tie-breaker.**

### 4.2. Rank và reverse rank

Redis hỗ trợ:

~~~redis
ZRANK demo:leaderboard alice
ZREVRANK demo:leaderboard alice
~~~

- `ZRANK` trả vị trí theo **score tăng dần**.
- `ZREVRANK` trả vị trí theo **score giảm dần**.
- Vị trí bắt đầu từ **0**.
- Nếu member không tồn tại, Redis trả nil; Spring Data Redis thường trả `null` cho lời gọi tương ứng.

Ví dụ ban đầu có 4 member:

| Member | Score | `ZRANK` tăng dần | `ZREVRANK` giảm dần | Vị trí UI nếu điểm cao đứng đầu |
| --- | ---: | ---: | ---: | ---: |
| david | 80 | 0 | 3 | 4 |
| bob | 95 | 1 | 2 | 3 |
| alice | 120 | 2 | 1 | 2 |
| carol | 120 | 3 | 0 | 1 |

Để hiển thị thứ hạng bắt đầu từ 1:

~~~java
Long zeroBasedRank = redis.opsForZSet()
        .reverseRank("demo:leaderboard", "alice");

Long displayRank = zeroBasedRank == null
        ? null
        : zeroBasedRank + 1;
~~~

**Rank của Redis là vị trí phần tử, không phải thứ hạng đồng hạng theo điểm.** Trong ví dụ, Alice và Carol cùng 120 nhưng có reverse rank khác nhau. Nếu sản phẩm yêu cầu cả hai đều là “hạng 1”, cần tự định nghĩa và tính **competition rank**, **dense rank** hoặc quy tắc hiển thị tương ứng.

## 5. Member duy nhất: điểm số có thể trùng, thành viên thì không

Một Redis ZSET có thể có:

~~~text
alice = 100
bob   = 100
carol = 100
~~~

Đó là **ba member khác nhau, cùng một score**, hoàn toàn hợp lệ. Nhưng hai mục sau không thể cùng tồn tại như hai bản ghi tách biệt trong một ZSET:

~~~text
alice = 100
alice = 200
~~~

Khi bạn thêm lại `alice`, Redis chỉ giữ **một member alice với score mới**.

### 5.1. Ý nghĩa với mô hình dữ liệu

| Yêu cầu nghiệp vụ | Member nên là gì? | Điểm cần lưu ý |
| --- | --- | --- |
| Điểm hiện tại của mỗi người chơi | User ID ổn định, ví dụ `user:42` | Một member/user, score được cập nhật |
| Nhiệm vụ đang chờ theo thời gian | Task ID duy nhất | Score có thể là deadline timestamp |
| Mỗi lần mua hàng là một sự kiện riêng | Order/event ID duy nhất | Dùng User ID sẽ ghi đè sự kiện trước |
| Top sản phẩm bán chạy | Product ID ổn định | Score là tổng số bán hoặc chỉ số xếp hạng |
| Nhiều phiên tham gia của một người | Session ID hoặc key có phiên | Không dùng cùng user ID nếu muốn giữ từng phiên |

Nếu một member đại diện cho object có tên hiển thị thay đổi, nên lưu **ID ổn định trong ZSET** và lấy dữ liệu hiển thị từ DB/cache khác. Dùng tên hiển thị làm member có thể khiến đổi tên tạo một member mới, làm mất liên kết với điểm trước đó.

### 5.2. Định dạng byte của member quyết định tính duy nhất

Redis coi các member là byte strings. Hai giá trị nhìn giống nhau về ý nghĩa có thể khác khi được mã hóa:

~~~text
"user:42"   -> bytes UTF-8
Một object Java được JDK-serialize -> bytes nhị phân khác
~~~

Một ứng dụng sử dụng `StringRedisTemplate` và ứng dụng khác dùng `RedisTemplate` với JDK serializer có thể tạo ra **hai member khác nhau về byte**, dù cả hai đều đại diện logic cho user 42. Vì vậy phải thống nhất member serializer, quy ước ID, chữ hoa/thường và chuẩn hóa ký tự khi nhiều client chia sẻ ZSET.

Không nên dùng JSON object đầy đủ làm member nếu chỉ muốn nhận diện một thực thể: thay đổi bất kỳ field JSON nào có thể tạo ra **member mới**, để lại member cũ trong cùng ZSET.

## 6. Score là kiểu số nào?

Redis Sorted Set lưu score dưới dạng **số dấu phẩy động độ chính xác kép (IEEE-754 double)**. Điều này cho phép điểm nguyên, điểm thập phân, giá trị âm và các biểu diễn số mà Redis hỗ trợ, nhưng **không phải mọi số nguyên lớn đều được biểu diễn chính xác**.

Ví dụ:

~~~redis
DEL demo:scores
ZADD demo:scores 1 alice
ZADD demo:scores 1.5 bob
ZADD demo:scores -3 carol
ZRANGE demo:scores 0 -1 WITHSCORES
~~~

Thứ tự tăng dần:

~~~text
carol -3
alice  1
bob    1.5
~~~

Không có yêu cầu score luôn dương. Nhưng nếu một bài toán có quy tắc điểm từ 0 trở lên, **phần ứng dụng phải kiểm tra** trước khi ghi.

### 6.1. Giới hạn độ chính xác

Các **số nguyên** trong khoảng:

\[
-2^{53} \le n \le 2^{53}
\]

có thể được biểu diễn chính xác bằng double. Ngoài khoảng đó, không phải mọi số nguyên kế tiếp đều có biểu diễn riêng.

Ví dụ timestamp hiện đại theo **milliseconds** kể từ Unix epoch thường nằm dưới ngưỡng này, nên có thể hữu ích làm score cho danh sách thời gian. Nhưng timestamp theo **nanoseconds** thường vượt xa ngưỡng chính xác của double; hai thời điểm khác nhau có thể bị làm tròn thành cùng score.

Với score thập phân như 0.1, biểu diễn nhị phân floating point còn có giới hạn chính xác thông thường. Không nên dùng Sorted Set score làm **sổ cái tiền tệ** cần phép cộng tuyệt đối chính xác; cân nhắc lưu đơn vị nhỏ nhất thành số nguyên trong khoảng an toàn hoặc dùng database/định dạng số thích hợp để tính toán nghiệp vụ.

### 6.2. Chuẩn hóa score trong Java

Java gọi API ZSET bằng `double`:

~~~java
redis.opsForZSet().add("demo:scores", "alice", 120.0);
~~~

Nên kiểm tra giá trị ở ranh giới service:

~~~java
private static void validateScore(double score) {
    if (!Double.isFinite(score)) {
        throw new IllegalArgumentException(
                "Score must be a finite number");
    }
}
~~~

Điều này tránh dữ liệu NaN/vô hạn từ input hoặc tính toán Java đi vào bảng xếp hạng mà ứng dụng chỉ dự kiến chứa điểm hữu hạn. Redis có thể chấp nhận một số biểu diễn vô cực trong ngữ cảnh score/range, nhưng business rule nên minh bạch về phạm vi cho phép; Redis từ chối NaN.

### 6.3. Score không phải số nguyên đếm sự kiện

Nếu mục tiêu chỉ là tăng một số nguyên theo ID và không cần xếp hạng, Redis String với `INCR` có thể đơn giản hơn. ZSET hữu ích khi cần **kết hợp member với score có thứ tự**, chẳng hạn top N, xếp hạng hoặc tìm nhiệm vụ đến hạn.

## 7. Các lệnh Redis cần biết

| Lệnh | Tác dụng | Ghi chú |
| --- | --- | --- |
| `ZADD key score member` | Thêm member hoặc cập nhật score của member đã có | Không tạo member trùng |
| `ZSCORE key member` | Lấy score của một member | Member không tồn tại → nil |
| `ZCARD key` | Đếm số member | Không cần đọc toàn bộ tập hợp |
| `ZRANK key member` | Vị trí từ score thấp lên cao | Bắt đầu từ 0 |
| `ZREVRANK key member` | Vị trí từ score cao xuống thấp | Bắt đầu từ 0 |
| `ZRANGE key start stop WITHSCORES` | Đọc theo vị trí tăng dần | Start và stop đều được tính |
| `ZRANGE key start stop REV WITHSCORES` | Đọc theo vị trí giảm dần | Tie-break đảo cùng chiều |
| `ZINCRBY key increment member` | Tăng score của một member | Nguyên tử ở cấp lệnh |
| `ZREM key member` | Xóa member | Không xóa member khác |
| `ZCOUNT key min max` | Đếm member có score trong khoảng | Hỗ trợ biên gồm/loại trừ |
| `ZRANGE key min max BYSCORE` | Đọc theo khoảng score | Dùng cú pháp score thay vì chỉ số |
| `ZPOPMIN` / `ZPOPMAX` | Lấy **và xóa** member điểm thấp/cao | Khác truy vấn chỉ đọc |
| `ZSCAN` | Duyệt từng phần phục vụ quản trị/scan | Không bảo đảm thứ tự xếp hạng |

### 7.1. Thêm và cập nhật

~~~redis
ZADD demo:leaderboard 40 alice
ZADD demo:leaderboard 55 bob
ZADD demo:leaderboard 80 carol
ZADD demo:leaderboard 60 alice
ZCARD demo:leaderboard
ZSCORE demo:leaderboard alice
~~~

Kết quả:

~~~text
ZCARD -> 3
ZSCORE alice -> 60
~~~

Alice được cập nhật score, không bị thêm một lần nữa. Nếu UI cần lịch sử thay đổi 40 → 60, phải lưu sự kiện đó ở nơi khác; ZSET chỉ giữ **score hiện tại** của member.

### 7.2. Tăng điểm thay vì ghi đè

~~~redis
ZINCRBY demo:leaderboard 5 alice
ZSCORE demo:leaderboard alice
~~~

Alice từ 60 thành 65. Khi nhiều client cùng tăng một member bằng `ZINCRBY`, Redis xử lý từng lệnh tăng nguyên tử; tránh mô hình:

~~~text
ZSCORE -> cộng trong Java -> ZADD
~~~

vì hai request có thể đọc cùng một score cũ và ghi đè thay đổi của nhau.

**Atomic không đồng nghĩa exactly-once:** nếu request bị timeout sau khi Redis đã tăng nhưng client chưa nhận phản hồi, retry có thể cộng điểm lần thứ hai. Nếu điểm phải tương ứng chính xác với một event duy nhất, cần request/event ID và cơ chế chống trùng.

### 7.3. Xóa thành viên

~~~redis
ZREM demo:leaderboard bob
ZSCORE demo:leaderboard bob
ZCARD demo:leaderboard
~~~

Sau khi `ZREM` xóa Bob, `ZSCORE` của Bob trả nil, số lượng giảm đi một. Nếu ZSET bị xóa hết phần tử, Redis không giữ một ZSET rỗng có key độc lập.

## 8. Đọc khoảng theo rank: ZRANGE và ZREVRANGE

Trong `ZRANGE`, `start` và `stop` có thể là vị trí dương hoặc âm, và **bao gồm cả hai đầu**.

~~~text
ZSET tăng dần:

member  A      B      C      D      E
score   10     20     30     40     50
index    0      1      2      3      4
index   -5     -4     -3     -2     -1
~~~

| Lệnh | Kết quả |
| --- | --- |
| `ZRANGE key 0 0` | A |
| `ZRANGE key 0 2` | A, B, C |
| `ZRANGE key 1 3` | B, C, D |
| `ZRANGE key -2 -1` | D, E |
| `ZRANGE key 0 -1` | Cả 5 member theo thứ tự tăng |
| `ZRANGE key 0 2 REV` | E, D, C |
| `ZRANGE key 0 -1 REV` | E, D, C, B, A |

Ở đây `key` biểu diễn ZSET mẫu có score phân biệt. Khi reverse, Redis đếm vị trí trên danh sách **đã đảo chiều**, nên `ZRANGE key 0 2 REV` là **top 3 điểm cao**, không phải lấy 3 điểm thấp rồi đảo kết quả.

### 8.1. Top N và bottom N

Với bảng xếp hạng điểm cao tốt hơn:

~~~redis
ZRANGE demo:leaderboard 0 9 REV WITHSCORES
~~~

trả tối đa **10 người đứng đầu**.

Với bảng xếp hạng cần xem các điểm thấp nhất:

~~~redis
ZRANGE demo:leaderboard 0 9 WITHSCORES
~~~

trả tối đa **10 member có score thấp nhất**.

**Không nhầm stop là số lượng.** `0 9` trả tối đa 10 phần tử; `0 10` trả tối đa 11.

### 8.2. Khi ZSET thay đổi, rank cũng thay đổi

Một người đang đứng top 10 có thể xuống top 11 ngay khi người khác cập nhật điểm. Redis tính rank theo trạng thái hiện tại, không lưu “hạng đã từng đạt được”. Nếu cần lịch sử thứ hạng theo ngày/tuần, hãy lưu snapshot theo kỳ hoặc có nguồn dữ liệu lịch sử riêng.

## 9. Đọc theo score: khoảng điểm khác khoảng rank

Hai loại truy vấn rất dễ bị nhầm:

| Truy vấn | Tập giá trị đầu vào | Câu hỏi trả lời |
| --- | --- | --- |
| **Theo rank** | Vị trí 0, 1, 2… | “Ai đứng top 10?” |
| **Theo score** | Giá trị score từ A đến B | “Ai có điểm từ 100 đến 200?” |

Ví dụ:

~~~redis
DEL demo:leaderboard
ZADD demo:leaderboard 80 david 95 bob 120 alice 120 carol 150 erin
ZRANGE demo:leaderboard 0 2 WITHSCORES
ZRANGE demo:leaderboard 100 150 BYSCORE WITHSCORES
ZCOUNT demo:leaderboard 100 150
~~~

Lệnh thứ nhất đọc **3 vị trí thấp nhất**: David, Bob, Alice. Lệnh thứ hai đọc các member có **score từ 100 đến 150**: Alice, Carol, Erin. `ZCOUNT` đếm số member trong khoảng điểm này, kết quả là 3.

### 9.1. Khoảng score có biên bao gồm hoặc loại trừ

Mặc định Redis dùng biên **bao gồm**:

~~~redis
ZRANGE demo:leaderboard 100 150 BYSCORE WITHSCORES
~~~

Có thể loại trừ biên bằng dấu `(` trong cú pháp Redis:

~~~redis
ZRANGE demo:leaderboard (100 150 BYSCORE WITHSCORES
~~~

Lệnh này loại score 100, vẫn gồm 150. Redis cũng hỗ trợ `-inf`, `+inf`:

~~~redis
ZRANGE demo:leaderboard 100 +inf BYSCORE WITHSCORES
ZCOUNT demo:leaderboard -inf 99
~~~

Nếu cần **đảo chiều khi BYSCORE**, thứ tự tham số phạm vi cũng phải phù hợp với chiều truy vấn; ví dụ:

~~~redis
ZRANGE demo:leaderboard +inf 100 BYSCORE REV WITHSCORES
~~~

trả member có score từ cao xuống thấp, dừng ở ngưỡng 100. Dùng nhầm `100 +inf` khi đã `REV` có thể khiến khoảng truy vấn không đúng ý định.

### 9.2. Lấy trang đầu của một khoảng score

Redis hỗ trợ `LIMIT offset count` khi truy vấn `BYSCORE`:

~~~redis
ZRANGE demo:leaderboard 100 +inf BYSCORE LIMIT 0 10 WITHSCORES
~~~

Ở đây `LIMIT 0 10` là **offset 0, số lượng 10**, khác với `ZRANGE key 0 9` theo rank, nơi 9 là **stop index bao gồm**.

Offset lớn trong dữ liệu luôn thay đổi có thể gây chi phí và kết quả không ổn định. Khi cần phân trang lâu dài theo score, có thể thiết kế cursor theo cặp **(score, member)** hoặc sử dụng nguồn dữ liệu hỗ trợ snapshot, tùy yêu cầu.

## 10. Spring Data Redis: chuẩn bị StringRedisTemplate

Nếu dùng Spring Boot với Redis starter, cấu hình thường chỉ cần:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Ví dụ `application.yml` cho Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Chạy Redis cục bộ bằng Docker:

~~~bash
docker run --name redis-zset-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-zset-lab redis-cli PING
~~~

Lệnh `PING` trả `PONG` khi kết nối thành công. Nếu port 6379 đang được dùng, thay port phía host và sửa cấu hình tương ứng. Ví dụ bind cổng thử nghiệm vào loopback; ở môi trường production phải giới hạn mạng, bật ACL/xác thực và TLS nếu hạ tầng yêu cầu.

Trong ứng dụng chạy cùng Redis trong Docker Compose, `localhost` của container ứng dụng không phải container Redis. Hãy dùng hostname service Redis hoặc endpoint phù hợp với mạng triển khai.

### 10.1. Tại sao dùng StringRedisTemplate?

`StringRedisTemplate` mặc định tuần tự hóa key và member theo String. Điều này giúp:

- Redis CLI hiển thị member dạng ID có thể đọc được.
- Nhiều ứng dụng đồng bộ với nhau về biểu diễn ID.
- Tránh ghi một member bằng Java serialization nhị phân trong khi reader dùng UTF-8.
- Tập trung vào score/rank mà không cần cấu hình JSON serializer phức tạp.

Với `RedisTemplate<String, PlayerDto>`, phải chọn **serializer cho value/member** rõ ràng. Trong ZSET, phần tử được lấy từ value serializer; có thể sử dụng JSON typed serializer nếu thật sự cần lưu DTO làm member, nhưng cách này khiến thay đổi JSON schema có thể tạo member khác về byte. Thường nên dùng **ID ổn định làm member** và lưu DTO ở key khác.

## 11. Các phương thức ZSetOperations cơ bản

Spring Data Redis cung cấp:

~~~java
ZSetOperations<String, String> zset =
        stringRedisTemplate.opsForZSet();
~~~

| Thao tác | Spring Data Redis | Ý nghĩa |
| --- | --- | --- |
| Thêm/đặt score | `zset.add(key, member, score)` | Thêm member hoặc đổi score |
| Đọc score | `zset.score(key, member)` | Trả `Double` hoặc null |
| Đếm member | `zset.size(key)` | Trả `Long` |
| Rank tăng | `zset.rank(key, member)` | Trả `Long` bắt đầu từ 0 |
| Rank giảm | `zset.reverseRank(key, member)` | Rank top điểm cao |
| Range tăng | `zset.range(key, start, end)` | Đọc member theo vị trí |
| Range giảm | `zset.reverseRange(key, start, end)` | Đọc member theo vị trí đảo chiều |
| Range có điểm | `zset.rangeWithScores(...)` | Trả member và score |
| Top N có điểm | `zset.reverseRangeWithScores(...)` | Member và score, thứ tự giảm |
| Tăng score | `zset.incrementScore(key, member, delta)` | Tăng theo delta nguyên tử |
| Xóa member | `zset.remove(key, member)` | Trả số phần tử xóa |
| Đếm khoảng score | `zset.count(key, min, max)` | Đếm member trong khoảng |
| Đọc khoảng score | `zset.rangeByScore(key, min, max)` | Member trong khoảng điểm |

Các lời gọi này thường có kiểu trả về boxed (`Boolean`, `Double`, `Long`, `Set`) và **có thể nullable**, đặc biệt trong pipeline/transaction khi kết quả chỉ được thu thập sau. Với các lời gọi đồng bộ thông thường, member không tồn tại khiến `score()`/`rank()` trả `null`, còn range trên key chưa có trả tập rỗng. Không nên mặc định mọi giá trị nullable đều có cùng nghĩa.

## 12. Ví dụ service: bảng xếp hạng có member, score và rank

Giả sử ứng dụng cần một bảng xếp hạng cho một mùa chơi. Member là player ID, score là điểm tích lũy. Người dùng muốn xem **top N**, **điểm hiện tại** và **vị trí khi điểm cao đứng đầu**.

### 12.1. DTO cho kết quả

Tạo `LeaderboardEntry.java`:

~~~java
package com.example.redis;

public record LeaderboardEntry(
        String playerId,
        double score,
        long position
) {
}
~~~

`position` là thứ hạng hiển thị **bắt đầu từ 1** trong chiều score giảm dần. Đây là **vị trí có tie-break theo member** của Redis, không phải competition rank cho các thành viên đồng điểm.

### 12.2. Service dùng StringRedisTemplate

~~~java
package com.example.redis;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardService {

    private static final String KEY = "game:season-1:leaderboard";
    private final ZSetOperations<String, String> zset;

    public LeaderboardService(StringRedisTemplate redis) {
        this.zset = redis.opsForZSet();
    }

    public void setScore(String playerId, double score) {
        validatePlayer(playerId);
        validateScore(score);
        zset.add(KEY, member(playerId), score);
    }

    public double addPoints(String playerId, double delta) {
        validatePlayer(playerId);
        validateScore(delta);

        Double updated = zset.incrementScore(
                KEY, member(playerId), delta);
        if (updated == null) {
            throw new IllegalStateException(
                    "Redis did not return updated score");
        }
        return updated;
    }

    public Optional<Double> scoreOf(String playerId) {
        validatePlayer(playerId);
        return Optional.ofNullable(zset.score(KEY, member(playerId)));
    }

    public Optional<Long> positionOf(String playerId) {
        validatePlayer(playerId);
        Long zeroBased = zset.reverseRank(KEY, member(playerId));
        return zeroBased == null
                ? Optional.empty()
                : Optional.of(zeroBased + 1);
    }

    public List<LeaderboardEntry> top(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Limit must be between 1 and 100");
        }

        Set<ZSetOperations.TypedTuple<String>> tuples =
                zset.reverseRangeWithScores(KEY, 0, limit - 1L);
        if (tuples == null) {
            throw new IllegalStateException(
                    "Redis did not return range results");
        }

        List<LeaderboardEntry> entries =
                new ArrayList<>(tuples.size());
        long position = 1;

        for (ZSetOperations.TypedTuple<String> tuple : tuples) {
            String rawMember = tuple.getValue();
            Double score = tuple.getScore();

            if (rawMember == null || score == null) {
                throw new IllegalStateException(
                        "Unexpected empty sorted-set tuple");
            }

            entries.add(new LeaderboardEntry(
                    rawMember.substring("player:".length()),
                    score,
                    position++
            ));
        }

        return List.copyOf(entries);
    }

    public long removePlayer(String playerId) {
        validatePlayer(playerId);
        Long removed = zset.remove(KEY, member(playerId));
        if (removed == null) {
            throw new IllegalStateException(
                    "Redis did not return remove result");
        }
        return removed;
    }

    public long size() {
        Long count = zset.size(KEY);
        if (count == null) {
            throw new IllegalStateException(
                    "Redis did not return cardinality");
        }
        return count;
    }

    private String member(String playerId) {
        return "player:" + playerId;
    }

    private void validatePlayer(String playerId) {
        if (playerId == null || playerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Player ID is required");
        }
    }

    private void validateScore(double score) {
        if (!Double.isFinite(score)) {
            throw new IllegalArgumentException(
                    "Score must be finite");
        }
    }
}
~~~

**Lưu ý cách diễn giải ví dụ:**

- `setScore(...)` ghi **score tuyệt đối**. Nếu đã có player ID, score cũ bị thay thế.
- `addPoints(...)` sử dụng `ZINCRBY`, thích hợp cộng điểm mà không làm lost update do `ZSCORE` rồi `ZADD` ở hai lệnh riêng.
- `scoreOf(...)` cho `Optional.empty()` khi member không tồn tại.
- `positionOf(...)` dựa trên **reverse rank** và cộng 1 để trả thứ hạng UI.
- `top(limit)` lấy score kèm member trong **một lệnh**, tránh gọi `score()` một lần cho mỗi thành viên của top N.
- `removePlayer(...)` trả số member thực sự bị xóa (0 hoặc 1 đối với một member).
- Dùng key cố định để tập trung vào khái niệm. Ứng dụng nhiều mùa/tenant nên xây key từ định danh đã xác thực và kiểm soát quyền truy cập.

**Về thứ tự trả kết quả:** API `reverseRangeWithScores(...)` trả tập tuple theo thứ tự kết quả ZSET. Ví dụ duyệt tập đó để gán vị trí tăng dần; khi xây API tổng quát, cần giữ nguyên thứ tự mà Redis/Spring Data Redis cung cấp, không tự chuyển thành một `HashSet` làm mất trật tự. Nếu cần kiểm soát tuyệt đối biểu diễn kết quả, có thể đọc dữ liệu theo API đã xác định thứ tự và chuyển trực tiếp sang `List`.

**Về member prefix:** ví dụ dùng `player:` để minh họa. Phần bóc prefix trong `top()` giả định **mọi member của key đều bắt đầu bằng `player:`**. Trong production, đây phải là hợp đồng dữ liệu; không cho code khác ghi member tùy ý vào bảng xếp hạng này.

### 12.3. Ví dụ gọi service

~~~java
leaderboardService.setScore("17", 90);
leaderboardService.setScore("42", 120);
leaderboardService.setScore("93", 120);
leaderboardService.setScore("58", 150);

List<LeaderboardEntry> top = leaderboardService.top(3);
Optional<Double> score42 = leaderboardService.scoreOf("42");
Optional<Long> rank42 = leaderboardService.positionOf("42");

leaderboardService.addPoints("17", 80);
List<LeaderboardEntry> newTop = leaderboardService.top(3);
~~~

Sau khi thêm 80 điểm cho player 17, score của player này từ 90 thành 170 và player 17 lên đầu bảng. Trong ứng dụng thực, đoạn gọi trên phải nằm trong controller/service/test có bean `leaderboardService` được inject.

### 12.4. Khi nào không nên dùng double trực tiếp cho điểm nguyên?

Nếu điểm là số nguyên có thể tăng rất lớn, API nhận `double` vẫn chạy nhưng không đảm bảo mọi số nguyên ngoài khoảng chính xác của IEEE-754 được giữ nguyên. Hãy giới hạn score trong miền hợp lệ, kiểm tra giá trị nghiệp vụ và lưu nguồn sự kiện/tổng điểm có độ chính xác cần thiết ở database khi cần.

## 13. Chọn `range` hay `rangeWithScores`?

Trong Spring Data Redis:

~~~java
Set<String> members =
        redis.opsForZSet().reverseRange(key, 0, 9);
~~~

trả danh sách member theo thứ tự ZSET nhưng **không mang score** trong từng phần tử.

Khi UI hiển thị cả tên ID và điểm, dùng:

~~~java
Set<ZSetOperations.TypedTuple<String>> entries =
        redis.opsForZSet().reverseRangeWithScores(key, 0, 9);
~~~

Mỗi `TypedTuple<String>` cung cấp `getValue()` (member) và `getScore()` (score). Điều này giúp tránh mô hình:

~~~text
1 lần reverseRange -> lấy 10 member
10 lần score(member) -> lấy 10 score
~~~

vì có thể tạo nhiều round trip hơn và các score có thể thay đổi giữa các lần đọc khi hệ thống có writer đồng thời.

Một lệnh range-with-scores phản ánh danh sách member/score tại thời điểm Redis xử lý lệnh đó. Nó vẫn không đảm bảo dữ liệu tiếp tục giữ nguyên đến khi HTTP response tới client.

## 14. Khoảng điểm và thứ hạng trong API Spring Data Redis

Một số ví dụ:

~~~java
ZSetOperations<String, String> zset = redis.opsForZSet();

// Member có score trong [100, 150], theo thứ tự tăng dần.
Set<String> qualifying = zset.rangeByScore(
        "demo:leaderboard", 100.0, 150.0);

// Đếm member có score trong [100, 150].
Long numberOfQualifying = zset.count(
        "demo:leaderboard", 100.0, 150.0);

// Điểm cụ thể của alice.
Double aliceScore = zset.score("demo:leaderboard", "alice");

// Rank theo điểm thấp -> cao.
Long ascendingRank = zset.rank("demo:leaderboard", "alice");

// Rank theo điểm cao -> thấp.
Long descendingRank = zset.reverseRank(
        "demo:leaderboard", "alice");
~~~

**Phạm vi theo score** dùng giá trị `double min, max`, còn **phạm vi theo rank** dùng chỉ số `long start, end`. Hai overload/nhóm method này có thể có kiểu tham số khác nhau nhưng nhìn rất giống nhau nếu tên method không được đọc kỹ.

Đối với các khoảng điểm cần loại trừ biên, Redis có cú pháp `(min`. Spring Data Redis cung cấp các lớp range/bound phù hợp ở những phiên bản API nhất định; với yêu cầu cụ thể này, hãy dùng API range có cấu hình biên đúng phiên bản thay vì mặc định `rangeByScore(key, min, max)` thể hiện toàn bộ điều kiện.

## 15. Những trường hợp cập nhật điểm đồng thời

### 15.1. Race condition khi đọc rồi ghi

Score của Alice hiện là 100. Hai request cùng muốn cộng 10 điểm:

~~~text
Request A: ZSCORE alice -> 100
Request B: ZSCORE alice -> 100
Request A: ZADD alice 110
Request B: ZADD alice 110

Kết quả cuối: 110
Kỳ vọng hai lần cộng thành công: 120
~~~

Đây là lost update. Khi cần cộng điểm, sử dụng:

~~~redis
ZINCRBY demo:leaderboard 10 alice
~~~

Trong Java:

~~~java
Double updated = redis.opsForZSet()
        .incrementScore("demo:leaderboard", "alice", 10);
~~~

Mỗi lần tăng là một lệnh Redis nguyên tử cho score của member. Nhiều request cùng tăng sẽ không mắc lỗi đọc/cộng/ghi tách rời.

### 15.2. Atomicity không đồng nghĩa idempotency

Giả sử request “hoàn thành nhiệm vụ X, thưởng 10 điểm” được gửi hai lần vì timeout. Nếu không chống trùng sự kiện, hai lần `ZINCRBY 10` sẽ cộng 20 điểm. Redis thực thi từng lệnh đúng, nhưng ứng dụng đã tính một sự kiện hai lần.

Nếu điểm phải gắn với event ID duy nhất, cần cơ chế **deduplication/idempotency** và cách kết hợp đánh dấu sự kiện với cập nhật score đủ chặt. Ví dụ, một script có thể kiểm tra event ID chưa xử lý rồi mới tăng điểm trong cùng thao tác Redis; tuy nhiên vẫn phải cân nhắc TTL của dấu đã xử lý và yêu cầu bền vững. Với sự kiện kinh doanh cần kiểm toán, lưu event ở nguồn dữ liệu bền vững và có quy trình đối soát.

### 15.3. Ghi score tuyệt đối có thể ghi đè thay đổi gần nhất

Nếu hai service cùng tính lại điểm từ hai snapshot cũ và gọi `ZADD`, lời ghi đến sau quyết định score cuối. Redis không biết kết quả nào “mới hơn” về nghĩa nghiệp vụ. Khi cập nhật score tổng hợp từ DB, cần quy ước version/timestamp hoặc luồng cập nhật được quản lý; có thể sử dụng tùy chọn `ZADD GT/LT` nếu logic chỉ cho phép điểm tăng/giảm đơn điệu, nhưng những tùy chọn đó **không thay thế version check cho mọi bài toán**.

## 16. Kiểm soát hành vi ZADD: NX, XX, GT, LT, CH

Lệnh `ZADD` hỗ trợ các tùy chọn để điều khiển việc thêm hoặc cập nhật:

~~~redis
ZADD key NX score member
ZADD key XX score member
ZADD key GT score member
ZADD key LT score member
ZADD key CH score member
~~~

| Tùy chọn | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| `NX` | Chỉ thêm member **chưa tồn tại** | Khởi tạo điểm lần đầu, không ghi đè |
| `XX` | Chỉ cập nhật member **đã tồn tại** | Bỏ qua người chưa đăng ký trong bảng |
| `GT` | Chỉ cập nhật member có score mới **lớn hơn score hiện tại**; member mới vẫn có thể được thêm nếu không kết hợp XX | Điểm cao nhất từng đạt được |
| `LT` | Chỉ cập nhật nếu score mới **nhỏ hơn score hiện tại**; member mới vẫn có thể được thêm nếu không kết hợp XX | Thời gian nhanh nhất hoặc điểm thấp tốt hơn |
| `CH` | Thay cách đếm kết quả để tính cả member được cập nhật score | Cần phân biệt số member bị thay đổi với chỉ số thêm mới |

Tùy chọn có những giới hạn kết hợp: không dùng `NX` đồng thời với `XX`, `GT` hoặc `LT` theo cách Redis cấm; `GT` và `LT` cũng loại trừ nhau. Đọc cú pháp lệnh đúng phiên bản Redis đang chạy.

Ví dụ lưu thành tích **cao nhất từng đạt**:

~~~redis
DEL demo:best-score
ZADD demo:best-score 100 alice
ZADD demo:best-score GT 80 alice
ZSCORE demo:best-score alice
ZADD demo:best-score GT 140 alice
ZSCORE demo:best-score alice
~~~

Score của Alice vẫn 100 sau lần thử ghi 80, sau đó tăng lên 140. Cách này phù hợp khi “điểm tốt nhất” chỉ được tăng. Nếu nghiệp vụ cho phép phạt điểm hoặc cần tính điểm mới từ nhiều sự kiện, không nên tùy tiện dùng `GT`.

**Phân biệt kết quả Boolean của API Spring:** `ZSetOperations.add(...)` thường ánh xạ thành công/thêm mới theo lệnh Redis, nhưng **không nên coi giá trị `false` là một lỗi kết nối**. Member đã có có thể được cập nhật score mà lệnh `ZADD` không trả số member mới được thêm. Để biết score cuối, đọc `score(...)` hoặc dùng API trả kết quả phù hợp với điều kiện nghiệp vụ.

## 17. Đồng điểm: xác định chính sách thứ hạng theo sản phẩm

Redis luôn có thứ tự xác định cho member bằng score theo quy tắc bytes, nhưng **quy tắc xếp hạng nghiệp vụ** có thể khác.

Giả sử:

~~~text
carol: 120
alice: 120
bob:   95
david: 80
~~~

Theo chiều điểm giảm dần, Redis trả:

~~~text
0 carol 120
1 alice 120
2 bob    95
3 david  80
~~~

Ba kiểu hiển thị thường gặp:

| Kiểu xếp hạng | Carol | Alice | Bob | David |
| --- | ---: | ---: | ---: | ---: |
| Vị trí Redis (1-based) | 1 | 2 | 3 | 4 |
| Competition rank (1,1,3,4) | 1 | 1 | 3 | 4 |
| Dense rank (1,1,2,3) | 1 | 1 | 2 | 3 |

Redis cung cấp **rank theo vị trí**, tức kiểu thứ nhất. Nếu sản phẩm cần kiểu thứ hai hoặc ba, service phải tính từ **số member có score cao hơn** hoặc **số mức score phân biệt**, không được chỉ cộng 1 vào `reverseRank` rồi gọi đó là “đồng hạng”.

### 17.1. Competition rank minh họa

Với người chơi có score `s`, thứ hạng competition có thể hiểu là:

~~~text
rank = 1 + số member có score lớn hơn s
~~~

Để đếm score **lớn hơn** một ngưỡng, Redis có hỗ trợ phạm vi loại trừ biên:

~~~redis
ZCOUNT demo:leaderboard (120 +inf
~~~

Nếu score cao nhất là 120, kết quả bằng 0 và competition rank của các member score 120 là 1. Nếu có một member score 150, rank của nhóm 120 sẽ trở thành 2.

**Cần nhất quán snapshot:** gọi `ZSCORE` rồi `ZCOUNT` là hai lệnh; nếu score thay đổi ở giữa, kết quả tính rank đồng hạng có thể lệch. Với yêu cầu chính xác ở một thời điểm, cần một thao tác nguyên tử phù hợp hoặc snapshot đã cố định.

### 17.2. Tại sao không thêm timestamp vào score tùy tiện?

Một cách nghĩ tới là tạo score bằng điểm cộng với một phần nhỏ từ timestamp để phân định ai đạt trước. Cách này có thể:

- Làm sai thứ tự điểm nếu hệ số không được kiểm soát.
- Mất độ chính xác double khi score lớn.
- Không còn bảo đảm những người bằng điểm có cùng score.
- Khó giải thích thứ hạng khi đổi thuật toán.

Nếu cần quy tắc “điểm giảm dần; nếu bằng điểm, người đạt trước đứng trên”, nên **thiết kế rõ tie-break**: lưu timestamp riêng hoặc đưa vào một mô hình dữ liệu/sort key có tính đúng đắn được chứng minh. Redis ZSET mặc định tie-break theo bytes của member, **không tự ưu tiên thời gian tham gia**.

## 18. Điểm số và thời gian: dùng Sorted Set cho lịch hẹn

ZSET không chỉ dành cho leaderboard. Score có thể là **thời điểm dự kiến thực thi**, member là **task ID**.

~~~text
key: scheduler:pending
member: task:42
score: thời điểm chạy (Unix epoch milliseconds)
~~~

Ví dụ:

~~~redis
ZADD scheduler:pending 1730000000000 task:42
ZADD scheduler:pending 1730000060000 task:43
ZRANGE scheduler:pending 0 -1 WITHSCORES
~~~

Các task có score nhỏ hơn là task đến hạn sớm hơn. Cách lấy nhiệm vụ đến một mốc:

~~~redis
ZRANGE scheduler:pending -inf 1730000030000 BYSCORE WITHSCORES
~~~

Ở Java:

~~~java
double nowMillis = (double) System.currentTimeMillis();
Set<String> dueTaskIds =
        redis.opsForZSet().rangeByScore(
                "scheduler:pending",
                Double.NEGATIVE_INFINITY,
                nowMillis
        );
~~~

**Đây chỉ là cách tìm các task đến hạn, chưa phải queue có xác nhận xử lý.** Nhiều worker cùng đọc có thể nhìn thấy cùng task. Muốn nhiều worker nhận nhiệm vụ mà không xử lý trùng, cần cơ chế claim/remove nguyên tử, lease/retry và idempotency. Không nên dùng riêng `rangeByScore(...)` rồi `remove(...)` tách rời và mặc định bảo đảm exactly-once.

Thời điểm dựa trên milliseconds thường nằm trong miền nguyên chính xác của double ở thời gian thực tế hiện nay, nhưng phải thống nhất timezone (timestamp epoch là mốc UTC), đơn vị thời gian và độ chính xác giữa tất cả writer.

## 19. Giới hạn kích thước Sorted Set và top N

Nếu bảng xếp hạng chỉ cần giữ N member có điểm cao nhất, có thể thêm điểm rồi xóa nhóm có rank thấp nhất:

~~~redis
ZADD demo:top-score 120 alice
ZADD demo:top-score 100 bob
ZADD demo:top-score 150 carol
ZADD demo:top-score 90 david
ZREMRANGEBYRANK demo:top-score 0 -4
ZRANGE demo:top-score 0 -1 REV WITHSCORES
~~~

Với **N = 3**, `ZREMRANGEBYRANK key 0 -(N+1)` loại bỏ mọi member ngoài **top 3 score cao nhất**. Trong ví dụ, David bị loại bỏ và giữ Carol, Alice, Bob.

Nhưng:

- Việc xóa làm mất member/score khỏi bảng. Nếu đây là bảng xếp hạng đầy đủ để tra thứ hạng của từng người, đừng trim nó.
- Với cùng score, member bị giữ hay bị xóa phụ thuộc tie-break bytes của Redis, không phải “vào bảng trước”.
- `ZADD` và `ZREMRANGEBYRANK` là hai lệnh riêng nếu gọi tách từ Java; reader có thể quan sát thời điểm tập hợp tạm vượt N.
- Nếu cần “add rồi trim” nguyên tử, có thể dùng Lua script ngắn hoặc transaction Redis phù hợp.

### 19.1. Script minh họa giữ top N nguyên tử

~~~lua
-- KEYS[1]: Sorted Set key
-- ARGV[1]: score, ARGV[2]: member, ARGV[3]: maxItems
local maxItems = tonumber(ARGV[3])
if not maxItems or maxItems < 1 or maxItems % 1 ~= 0 then
    return redis.error_reply("maxItems must be positive")
end

redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -(maxItems + 1))
return redis.call('ZCARD', KEYS[1])
~~~

Redis chạy script như một thao tác không bị lệnh client khác chen giữa. Code gọi nên kiểm tra score/member/maxItems trước, và bảo đảm key thuộc loại ZSET. Script này là ví dụ về **bounded top-N cache**, không nên áp dụng vào bảng dữ liệu mà member điểm thấp vẫn cần lưu và truy vấn.

## 20. TTL và vòng đời của ZSET

Redis TTL áp dụng lên **cả key Sorted Set**, không áp dụng độc lập cho từng member.

~~~redis
EXPIRE demo:leaderboard 3600
TTL demo:leaderboard
~~~

Sau thời hạn, **toàn bộ ZSET** có thể biến mất. Thêm/cập nhật score bằng `ZADD` hoặc `ZINCRBY` thông thường không tự xóa TTL của key đã có. Tuy nhiên, nếu key đã hết hạn và một lệnh mới tạo lại, key mới **không tự có TTL** nếu ứng dụng không đặt lại.

### 20.1. Nếu từng member cần expiration riêng?

Sorted Set không có TTL độc lập cho từng member theo cơ chế `EXPIRE key`. Một cách ứng dụng tự thiết kế là:

- Score chứa thời điểm hết hạn.
- Định kỳ truy vấn/xóa member đã hết hạn theo score.
- Hoặc thiết kế key riêng theo member để sử dụng TTL thực sự.

Nhưng dùng score làm expiration time đồng nghĩa **không thể đồng thời sử dụng chính score đó làm điểm leaderboard** theo cách thông thường. Nếu cần cả điểm và thời hạn cho mỗi người chơi, có thể cần thêm key cấu trúc khác hoặc mô hình dữ liệu khác.

### 20.2. Redis không tự xóa member có score là timestamp cũ

Nếu bạn lưu task với score = thời điểm chạy hoặc thời điểm hết hạn, Redis **không tự xóa member khi clock vượt score**. Score là dữ liệu để truy vấn; expiration là tính năng khác. Phải có tác vụ xử lý/xóa riêng.

## 21. Chi phí hiệu năng và giới hạn thực tế

Redis tối ưu Sorted Set cho tra cứu, thay đổi score và truy vấn thứ tự. Một số độ phức tạp tham khảo:

| Thao tác | Độ phức tạp thường gặp | Ý nghĩa |
| --- | --- | --- |
| `ZADD` một member | **O(log N)** | Thêm/cập nhật trong tập có N member |
| `ZINCRBY` | **O(log N)** | Cập nhật score và thứ tự |
| `ZSCORE` | **O(1)** | Tra score theo member |
| `ZCARD` | **O(1)** | Lấy tổng số member |
| `ZRANK`/`ZREVRANK` | **O(log N)** | Tìm vị trí member |
| `ZRANGE` | **O(log N + M)** | Truy cập và trả M member |
| `ZCOUNT` | **O(log N)** | Đếm member trong score range |
| `ZREMRANGEBYRANK` | **O(log N + M)** | Xóa M member trong khoảng |

Độ phức tạp không thay thế việc đo đạc. Giá trị member rất dài, tập hợp hàng triệu phần tử, lệnh range trả quá nhiều dữ liệu và kết nối mạng có thể tác động mạnh đến latency.

### 21.1. Tránh tải cả ZSET lên Java chỉ để lấy top 10

Đoạn:

~~~redis
ZRANGE key 0 -1 REV WITHSCORES
~~~

có thể trả hàng triệu member nếu ZSET lớn. Khi chỉ cần top 10, hãy sử dụng:

~~~redis
ZRANGE key 0 9 REV WITHSCORES
~~~

Đây là lựa chọn giảm dữ liệu trả về và chi phí object Java. Đồng thời giới hạn số `limit` do client cung cấp.

### 21.2. Tránh tuần tự hóa DTO lớn làm member

Một member JSON dài hàng kilobyte gây chi phí lưu trữ, truyền mạng và so sánh tie-break theo bytes. Nếu chỉ cần xếp hạng theo user ID, lưu **member là ID ngắn ổn định** rồi lấy metadata từ nguồn khác. Điều này còn giúp đổi tên người dùng mà không làm thay đổi identity của member.

### 21.3. Phân trang theo rank không phải snapshot

Nếu client đọc top 10 hôm nay rồi trang 2 vài giây sau, có thể có thành viên tăng điểm hoặc vào bảng khiến member chuyển vị trí. Hai trang có thể trùng hoặc bỏ sót, giống nhiều kiểu offset pagination trên tập dữ liệu đang thay đổi.

Với dashboard cập nhật liên tục, có thể chấp nhận sự thay đổi này. Với báo cáo cần snapshot cố định, phải tạo mốc dữ liệu hoặc lưu snapshot theo kỳ.

### 21.4. ZSCAN không phải cách đọc bảng xếp hạng theo thứ tự

`ZSCAN` giúp duyệt từng phần tử mà không trả cả ZSET trong một lệnh lớn. Tuy nhiên, **thứ tự các item trong quá trình scan không phải thứ tự theo score**. Nếu cần top N theo thứ tự, dùng `ZRANGE`/API range tương ứng; nếu chỉ muốn duyệt để kiểm kê hoặc di chuyển dữ liệu, cân nhắc `ZSCAN` với cursor.

## 22. Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Điểm cập nhật nhưng `ZCARD` không tăng | Member đã tồn tại, `ZADD` đổi score | Đây là hành vi bình thường của ZSET |
| Hai người bằng điểm nhưng rank khác nhau | Redis tie-break theo member bytes | Định nghĩa rank UI và quy tắc đồng hạng |
| Top 10 trả những người điểm thấp | Dùng `range` thay vì `reverseRange` | Dùng chiều giảm nếu điểm cao tốt hơn |
| Top 10 trả 11 member | Dùng stop = 10 thay vì 9 | Range bao gồm stop |
| `score()`/`rank()` trả null | Member không tồn tại hoặc ngữ cảnh pipeline/transaction | Xem `ZSCORE`, key, ngữ cảnh thực thi |
| Redis báo `WRONGTYPE` | Key đang là String/List/Hash | Kiểm tra `TYPE key`; không trộn cấu trúc |
| Score mất chính xác | Dùng double cho số nguyên rất lớn hoặc tính tiền | Giới hạn miền score, đổi mô hình dữ liệu |
| Một người xuất hiện hai lần dưới hai ID | Writer không thống nhất member ID/serializer | Dùng ID ổn định và codec thống nhất |
| Đồng điểm nhưng thứ tự “lạ” | Member so sánh theo bytes, không theo locale | Thiết kế tie-break nghiệp vụ riêng |
| `ZINCRBY` làm tăng đôi | Retry sau timeout, event lặp | Dùng idempotency/dedup nếu cần |
| Đọc score khác với rank vừa lấy | Writer cập nhật giữa hai lệnh | Snapshot hoặc thao tác nguyên tử khi cần |
| ZSET biến mất | TTL, eviction, xóa member cuối hoặc writer khác | Kiểm tra `TTL`, memory, logs, ownership |
| Không thấy member từ CLI | Value/member serializer nhị phân hoặc khác DB | Kiểm tra serializer, host/port/database |
| Range theo score trả khác mong đợi | Nhầm `BYSCORE` với rank, đảo min/max khi `REV` | Xem cú pháp lệnh và điều kiện biên |
| Data tăng RAM nhanh | Nhiều ZSET, member quá dài, không retention | Theo dõi `ZCARD`, `MEMORY USAGE` và TTL |
| Timer task vẫn còn sau deadline | Score không tự tạo expiration | Cần xử lý và xóa member quá hạn |

## 23. Kiểm tra kết quả bằng Redis CLI

Sau khi ứng dụng đã ghi dữ liệu:

~~~redis
TYPE game:season-1:leaderboard
ZCARD game:season-1:leaderboard
ZRANGE game:season-1:leaderboard 0 9 REV WITHSCORES
ZRANGE game:season-1:leaderboard 0 -1 WITHSCORES
ZSCORE game:season-1:leaderboard player:42
ZRANK game:season-1:leaderboard player:42
ZREVRANK game:season-1:leaderboard player:42
TTL game:season-1:leaderboard
MEMORY USAGE game:season-1:leaderboard
~~~

Kiểm tra theo trình tự:

1. Cùng host, port, logical database và namespace với Spring Boot.
2. `TYPE` phải là `zset` nếu key tồn tại.
3. `ZCARD` cho số member duy nhất.
4. `ZRANGE ... WITHSCORES` cho thứ tự và score đã lưu.
5. `ZSCORE` chỉ ra member hiện có hay không.
6. `ZRANK`/`ZREVRANK` xác nhận chiều xếp hạng.
7. `TTL` giúp xác định key có expiration; `MEMORY USAGE` giúp ước lượng memory của key khi Redis hỗ trợ.

Nếu cần duyệt key theo namespace, dùng `SCAN` theo cursor thay vì `KEYS *` trên Redis production lớn. Đừng dùng `FLUSHDB` hoặc `FLUSHALL` để thử “reset bảng xếp hạng” khi Redis còn chứa dữ liệu của hệ thống khác.

## 24. Bài thực hành tổng hợp: bảng xếp hạng mùa giải

**Đề bài:** Viết service Spring Boot quản lý bảng xếp hạng theo player ID. Mỗi player có đúng một score hiện tại trong một mùa; điểm cao hơn đứng trước. API hỗ trợ ghi điểm tuyệt đối, cộng điểm, đọc top 5, tra thứ hạng, đọc khoảng điểm và xóa người chơi.

### 24.1. Quy ước dữ liệu

~~~text
Key:        game:season-2026:leaderboard
Member:     player:<playerId>
Score:      điểm số nguyên không âm trong miền chính xác của double
Top N:      score giảm dần
Rank Redis: zero-based
Rank UI:    one-based, tie-break mặc định theo member bytes
~~~

Ở bài thực hành, để tránh nhập số thập phân hoặc score quá lớn, service có thể nhận `long points` và kiểm tra miền hợp lệ trước khi chuyển sang `double`. Điều này chưa làm Sorted Set thành một kiểu lưu nguyên 64 bit; miền an toàn phải được giữ rõ ràng.

### 24.2. Dữ liệu ban đầu

~~~redis
DEL game:season-2026:leaderboard
ZADD game:season-2026:leaderboard 95 player:17
ZADD game:season-2026:leaderboard 120 player:42
ZADD game:season-2026:leaderboard 120 player:93
ZADD game:season-2026:leaderboard 150 player:58
ZCARD game:season-2026:leaderboard
ZRANGE game:season-2026:leaderboard 0 -1 REV WITHSCORES
~~~

Kỳ vọng:

~~~text
ZCARD = 4

Top score giảm:
player:58 -> 150
player:93 -> 120
player:42 -> 120
player:17 -> 95
~~~

Vì hai member `player:42` và `player:93` bằng score, chiều giảm sắp `player:93` trước `player:42` theo thứ tự member bytes đảo chiều.

### 24.3. Những thao tác cần thực hiện

1. Ghi score tuyệt đối 95 cho player 17, 120 cho player 42, 120 cho player 93, 150 cho player 58.
2. Kiểm tra `ZCARD=4` và `TYPE=zset`.
3. Lấy top 3 theo thứ tự giảm, kèm score.
4. Tra `scoreOf("42")` và `positionOf("42")` bằng Spring Data Redis.
5. Cập nhật score tuyệt đối của player 42 lên 160; xác nhận không tăng số member.
6. Cộng thêm 10 cho player 17 bằng `incrementScore(...)`; không dùng đọc/cộng/ghi tách lệnh.
7. Truy vấn tất cả member có score từ 100 đến 160.
8. Xóa player 93; xác nhận `ZSCORE` của player này trả nil.
9. Thêm một player khác cùng score và giải thích quy tắc tie-break.
10. Thử nhập score âm hoặc vô hạn và xử lý theo validation đã chọn.

### 24.4. Kết quả logic kỳ vọng

Sau bước 5 và 6, trước khi xóa player 93:

~~~text
player:42 = 160
player:58 = 150
player:17 = 105
player:93 = 120

Top giảm:
player:42, player:58, player:93, player:17

ZCARD = 4
~~~

Sau khi xóa player 93, `ZCARD=3`. Đây là kết quả **dự kiến theo các thao tác mô tả**, không phải đầu ra từ một lần chạy test thực tế.

### 24.5. Bài tập mở rộng

**A. Bảng điểm cao nhất:** Dùng `ZADD GT` để chỉ giữ score tốt nhất của từng người chơi. Giải thích khác biệt với tổng điểm tích lũy theo `ZINCRBY`.

**B. Đồng hạng:** Thay yêu cầu từ rank theo vị trí sang competition rank. Mô tả công thức `1 + số member có score cao hơn`, giải thích vì sao cần snapshot nhất quán nếu điểm thay đổi liên tục.

**C. Mùa giải:** Lưu nhiều bảng độc lập bằng key chứa season ID. Xác định TTL hoặc cách lưu trữ kết quả cuối mùa để không mất dữ liệu lịch sử.

**D. Top 100 cache:** Tạo một ZSET dành riêng cho top 100, áp dụng thêm rồi trim theo rank bằng script ngắn. So sánh với việc giữ toàn bộ bảng để mọi player có thể tra rank.

**E. Scheduler:** Dùng ZSET khác có score là epoch milliseconds và member là task ID. Truy vấn nhiệm vụ đến hạn; nêu những bước bổ sung để worker có thể claim task an toàn.

## 25. Câu hỏi tự ôn

1. Một ZSET có cho phép hai member giống nhau nhưng score khác nhau cùng tồn tại không?
2. Hai member khác nhau có thể cùng score không? Khi đó Redis sắp xếp như thế nào?
3. Key, member, score và rank là bốn khái niệm khác nhau ra sao?
4. `ZRANK` khác `ZREVRANK` ở chiều sắp xếp nào?
5. Vì sao `ZRANK` của phần tử đứng đầu trong chiều tăng lại là 0?
6. Với leaderboard điểm cao tốt hơn, phải dùng `range` hay `reverseRange`?
7. Trong `ZRANGE key 0 9`, số 9 là stop index hay số lượng?
8. Khi dùng `ZRANGE ... REV`, thứ tự giữa các member cùng score có thay đổi không?
9. `ZADD` với member đã tồn tại ảnh hưởng đến score và cardinality như thế nào?
10. `ZINCRBY` tránh race condition gì so với `ZSCORE` rồi `ZADD`?
11. Tại sao retry `ZINCRBY` sau timeout có thể làm cộng điểm hai lần?
12. Score của Sorted Set lưu kiểu gì? Giới hạn độ chính xác nguyên có liên quan đến `2^53` ra sao?
13. Vì sao member nên dùng ID ổn định hơn là JSON DTO có thể thay đổi?
14. `reverseRangeWithScores(...)` khác `reverseRange(...)` ở kết quả trả về nào?
15. Redis có tự động xóa member khi score là timestamp quá hạn không?
16. Nếu cần đồng hạng theo competition rank, tại sao `reverseRank + 1` chưa đủ?
17. Khi nào `ZADD GT` hợp lý hơn `ZINCRBY`?
18. `ZCOUNT key 100 150` khác `ZRANGE key 0 10` ở tiêu chí lựa chọn ra sao?
19. Tại sao không nên dùng `ZSCAN` để hiển thị top 10 theo thứ tự score?
20. Nếu chỉ giữ top 100 trong ZSET, điều gì xảy ra khi muốn tra rank của người đứng thứ 500?
21. Vì sao hai ứng dụng sử dụng serializer khác nhau có thể xem hai bytes member là hai thành viên khác nhau?
22. Nếu cần báo cáo thứ hạng chính xác tại một thời điểm, phải giải quyết những thay đổi score đồng thời ra sao?

## 26. Tài liệu tham khảo

- [Redis — Sorted sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/): mô hình member, score và các tình huống sử dụng.
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/): thêm/cập nhật member, các tùy chọn NX/XX/GT/LT/CH.
- [Redis — ZSCORE](https://redis.io/docs/latest/commands/zscore/) và [ZCARD](https://redis.io/docs/latest/commands/zcard/): đọc điểm và số lượng member.
- [Redis — ZRANGE](https://redis.io/docs/latest/commands/zrange/): đọc theo rank, score, thứ tự tăng/giảm, biên và giới hạn kết quả.
- [Redis — ZRANK](https://redis.io/docs/latest/commands/zrank/) và [ZREVRANK](https://redis.io/docs/latest/commands/zrevrank/): vị trí theo hai chiều.
- [Redis — ZINCRBY](https://redis.io/docs/latest/commands/zincrby/): cập nhật điểm số nguyên tử.
- [Redis — ZCOUNT](https://redis.io/docs/latest/commands/zcount/): đếm số member theo khoảng điểm.
- [Redis — ZREMRANGEBYRANK](https://redis.io/docs/latest/commands/zremrangebyrank/): loại member theo khoảng rank.
- [Spring Data Redis — ZSetOperations JavaDoc](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ZSetOperations.html): các API add, score, rank, range, incrementScore và TypedTuple.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): tích hợp RedisTemplate, serializer, scripting và thao tác dữ liệu.

**Điểm cốt lõi:** Sorted Set lưu **member duy nhất kèm score** và Redis tự duy trì **thứ tự theo score**. Khi score bằng nhau, Redis dùng **thứ tự byte của member** để phân định vị trí; rank bắt đầu từ 0. Với Spring Data Redis, hãy dùng `ZSetOperations` để thêm/đọc/tăng điểm và lấy top N bằng `reverseRangeWithScores` khi điểm cao tốt hơn. Một bảng xếp hạng đáng tin cậy còn cần **member ID ổn định, serializer thống nhất, phạm vi score hợp lý, chính sách đồng hạng và xử lý cập nhật đồng thời**.
