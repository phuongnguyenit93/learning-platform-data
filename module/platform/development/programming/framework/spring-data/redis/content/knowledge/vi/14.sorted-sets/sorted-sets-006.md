# Xóa thành viên theo giá trị hoặc khoảng

## 1. Bài toán: cần xóa gì trong Redis Sorted Set?

**Redis Sorted Set (ZSet)** lưu một tập các **member duy nhất**, mỗi member gắn với một **score** kiểu số. Redis sắp xếp theo score tăng dần; khi score bằng nhau, member được sắp theo thứ tự từ điển của chuỗi bytes. Trong Spring Data Redis, nhóm API tương ứng là **opsForZSet()** của RedisTemplate hoặc StringRedisTemplate.

Ví dụ, một bảng xếp hạng chứa:

~~~text
Member       Score
erin           75
bob            95
dave          110
alice         120
carol         120
~~~

Ứng dụng có thể cần:

- **Xóa một người chơi đã rời cuộc thi** bằng member ID, không cần biết score hiện tại.
- **Xóa những người đứng cuối** dựa trên thứ hạng, chẳng hạn bỏ 10 người có điểm thấp nhất.
- **Loại bỏ các bản ghi cũ** có score là timestamp nằm trước một thời điểm cắt.
- **Xóa thành viên nằm trong một khoảng từ điển** khi tất cả phần tử được tổ chức theo điều kiện score phù hợp.
- **Giữ tối đa N phần tử có score cao nhất** để giới hạn bộ nhớ của bảng xếp hạng.

Redis có nhiều lệnh xóa với ngữ nghĩa khác nhau:

| Mục tiêu | Lệnh Redis | API thông dụng trong Spring Data Redis |
| --- | --- | --- |
| Xóa chính xác member | **ZREM** | **opsForZSet().remove(key, members...)** |
| Xóa theo khoảng thứ hạng tăng dần | **ZREMRANGEBYRANK** | **opsForZSet().removeRange(key, start, end)** |
| Xóa theo khoảng score | **ZREMRANGEBYSCORE** | **opsForZSet().removeRangeByScore(key, min, max)** |
| Xóa theo khoảng từ điển của member | **ZREMRANGEBYLEX** | API tùy phiên bản; có thể sử dụng lớp Redis command ở mức thấp hơn |
| Lấy và xóa member nhỏ nhất/lớn nhất | **ZPOPMIN / ZPOPMAX** | **popMin(...) / popMax(...)** |

Điểm quan trọng nhất là **xóa theo member**, **xóa theo vị trí** và **xóa theo score** không tương đương. Chọn sai lệnh có thể xóa cả một nhóm dữ liệu hợp lệ.

## 2. Chuẩn bị dữ liệu và quan sát thứ tự

Các lệnh ở phần Redis CLI được viết cho **redis-cli ở chế độ tương tác**. Trên một Redis Server học tập:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Sau đó tạo Sorted Set thử nghiệm bằng các lệnh Redis:

~~~text
ZADD lesson:row149:board 120 alice 95 bob 120 carol 110 dave 75 erin
TYPE lesson:row149:board
ZCARD lesson:row149:board
ZRANGE lesson:row149:board 0 -1 WITHSCORES
~~~

Ý nghĩa:

- **ZADD** thêm cặp score–member. Member chưa có được tạo; member đã tồn tại được cập nhật score thay vì tạo bản sao.
- **TYPE** cho biết key có kiểu **zset**.
- **ZCARD** đếm số member duy nhất.
- **ZRANGE key 0 -1 WITHSCORES** xem toàn bộ member theo **score tăng dần**, kèm score.

Thứ tự mong đợi từ thấp lên cao:

~~~text
erin 75
bob 95
dave 110
alice 120
carol 120
~~~

**alice và carol có cùng score 120 nhưng vẫn là hai member khác nhau.** Vì score bằng nhau nên thứ tự của chúng phụ thuộc so sánh từ điển theo bytes của member.

Quan sát chiều ngược lại:

~~~text
ZRANGE lesson:row149:board 0 -1 REV WITHSCORES
~~~

Lệnh này đọc từ score **cao xuống thấp**. Khi cần xác định người có điểm cao nhất, hãy chú ý chữ **REV**; các lệnh xóa theo rank thông thường không mặc định làm việc theo thứ tự này.

## 3. Xóa theo đúng member: ZREM

### 3.1. Cú pháp và kết quả

~~~text
ZREM key member [member ...]
~~~

ZREM xóa những member được chỉ định **theo giá trị member**, không phải theo score. Có thể xóa nhiều member trong một lệnh.

Ví dụ:

~~~text
ZREM lesson:row149:board alice
ZRANGE lesson:row149:board 0 -1 WITHSCORES
~~~

Member **alice** biến mất, còn **carol** vẫn tồn tại với score 120. Dù hai member có cùng score, xóa alice không xóa carol.

Thử xóa nhiều member:

~~~text
ZREM lesson:row149:board bob unknown-member
ZCARD lesson:row149:board
ZSCORE lesson:row149:board bob
~~~

Giả sử bob còn tồn tại và unknown-member chưa từng có, **ZREM trả 1**: đó là số member **thực sự bị xóa**, không phải số tên member được truyền vào. **ZSCORE** với member đã xóa trả nil.

Nếu gọi lại cùng một member đã bị xóa:

~~~text
ZREM lesson:row149:board bob
~~~

Kết quả là **0**, vì không còn gì để xóa. Hành vi này thuận tiện cho thao tác dọn dữ liệu có thể được yêu cầu lặp, nhưng **không có nghĩa toàn bộ workflow xung quanh lệnh luôn idempotent**.

### 3.2. Member duy nhất, score không duy nhất

Xét hai lệnh:

~~~text
ZADD lesson:row149:members 100 user-1 100 user-2
ZREM lesson:row149:members user-1
~~~

Chỉ **user-1** bị xóa. Redis xác định thành viên bằng **member value**; score là thuộc tính dùng để sắp xếp, không phải ID duy nhất.

Nếu yêu cầu nghiệp vụ là “xóa tất cả người có score 100”, cần **ZREMRANGEBYSCORE**, không phải ZREM.

### 3.3. Liên hệ Spring Data Redis

Với StringRedisTemplate:

~~~java
Long removed = stringRedisTemplate.opsForZSet()
        .remove("lesson:row149:members", "user-1", "user-2");
~~~

Trong một lời gọi trực tiếp thông thường, **removed** là số member bị xóa. API dùng kiểu **Long** vì đây là giá trị Redis trả về, và có thể không có giá trị ngay tại thời điểm xếp lệnh trong pipeline/transaction.

**Khi nào dùng ZREM?** Khi bạn biết ID member cần xóa, ví dụ người chơi rút khỏi leaderboard, một tác vụ không còn hợp lệ hoặc người dùng hủy đăng ký khỏi một tập có thứ tự.

## 4. Xóa theo khoảng thứ hạng: ZREMRANGEBYRANK

### 4.1. Rank bắt đầu từ 0 và đi theo score tăng dần

Redis ZSet có một thứ tự được xác định bằng score và member. **Rank** là vị trí trong thứ tự đó, bắt đầu từ **0**:

~~~text
Rank   Member      Score
 0     erin           75
 1     bob            95
 2     dave          110
 3     alice         120
 4     carol         120
~~~

Lệnh:

~~~text
ZRANK key member
~~~

trả rank từ score thấp lên cao. **ZREVRANK key member** trả rank theo thứ tự ngược, tức người có score cao hơn đứng trước.

Để xóa theo vị trí trong thứ tự tăng dần:

~~~text
ZREMRANGEBYRANK key start stop
~~~

**Cả start và stop đều được tính trong khoảng xóa** (inclusive). Index âm đếm từ cuối, tương tự nhiều lệnh Redis khác:

- **0**: member đầu tiên có thứ hạng thấp nhất.
- **1**: member thứ hai từ dưới lên.
- **-1**: member cuối cùng trong thứ tự tăng dần, tức member đứng đầu khi xét score cao nhất.
- **-2**: member áp cuối.

### 4.2. Ví dụ xóa hai thành viên thấp điểm nhất

Tạo dữ liệu độc lập:

~~~text
ZADD lesson:row149:rank 120 alice 95 bob 120 carol 110 dave 75 erin
ZRANGE lesson:row149:rank 0 -1 WITHSCORES
ZREMRANGEBYRANK lesson:row149:rank 0 1
ZRANGE lesson:row149:rank 0 -1 WITHSCORES
~~~

Lệnh ZREMRANGEBYRANK xóa member ở rank **0 và 1**, tức **erin** và **bob**, trả về số lượng member bị xóa là **2**. Kết quả còn lại:

~~~text
dave 110
alice 120
carol 120
~~~

### 4.3. Ví dụ xóa hai thành viên cao điểm nhất

~~~text
ZREMRANGEBYRANK lesson:row149:rank -2 -1
ZRANGE lesson:row149:rank 0 -1 WITHSCORES
~~~

Sau khi đã xóa erin và bob ở bước trước, phạm vi **-2 -1** gồm hai member cuối theo thứ tự tăng dần: **alice và carol**. Còn lại **dave**.

Điểm dễ nhầm là **ZREMRANGEBYRANK key 0 1** xóa **hai member thấp nhất**, không phải hai member cao nhất. Nếu muốn xóa top 2 theo score giảm dần, bạn phải tính phạm vi ở **cuối** dãy tăng dần hoặc chọn lệnh khác phù hợp.

### 4.4. Giữ lại top N thành viên có score cao nhất

Một mẫu dùng nhiều trong leaderboard là giới hạn còn tối đa 100 member:

~~~text
ZREMRANGEBYRANK leaderboard 0 -101
~~~

Lý do:

- ZSet mặc định sắp xếp **score tăng dần**.
- Muốn giữ 100 member có score cao nhất, phải xóa những member nằm **trước 100 phần tử cuối**.
- **-101** là vị trí đứng ngay trước 100 phần tử cuối khi độ dài đủ lớn.

Ví dụ minh họa dễ kiểm tra với giới hạn 3:

~~~text
ZADD lesson:row149:top 10 a 20 b 30 c 40 d 50 e
ZREMRANGEBYRANK lesson:row149:top 0 -4
ZRANGE lesson:row149:top 0 -1 WITHSCORES
~~~

Lệnh xóa **a** và **b**, giữ **c**, **d**, **e**. Nếu độ dài chưa vượt giới hạn, phạm vi này không xóa phần tử đang cần giữ.

**Chú ý khi đồng điểm:** nếu các member có cùng score đúng tại ngưỡng top N, Redis vẫn chọn vị trí dựa trên thứ tự từ điển của member. Nếu nghiệp vụ cần giữ **tất cả người đồng điểm**, số người giữ lại có thể vượt N; không thể áp dụng máy móc trim theo rank mà vẫn bảo toàn quy tắc đồng điểm đó.

### 4.5. Mapping sang Spring Data Redis

~~~java
Long removed = stringRedisTemplate.opsForZSet()
        .removeRange("lesson:row149:rank", 0, 1);
~~~

Tham số **start=0, end=1** bao gồm cả hai đầu. Để giới hạn top 100:

~~~java
stringRedisTemplate.opsForZSet()
        .removeRange("leaderboard", 0, -101);
~~~

Đây là thao tác xóa **theo vị trí hiện tại**. Khi ZADD cập nhật score của một member, vị trí có thể thay đổi; vì vậy rank không phải định danh bền vững của member.

## 5. Xóa theo khoảng score: ZREMRANGEBYSCORE

### 5.1. Score là điều kiện, không phải vị trí

Cú pháp:

~~~text
ZREMRANGEBYSCORE key min max
~~~

Lệnh xóa tất cả member có score nằm trong khoảng **min..max**. Với cú pháp số thông thường, **hai đầu đều bao gồm**.

Ví dụ:

~~~text
ZADD lesson:row149:score 50 a 100 b 100 c 120 d 180 e
ZRANGE lesson:row149:score 0 -1 WITHSCORES
ZREMRANGEBYSCORE lesson:row149:score 100 120
ZRANGE lesson:row149:score 0 -1 WITHSCORES
~~~

Các member bị xóa là **b (100)**, **c (100)** và **d (120)**. Có **3 member bị xóa**; chỉ còn **a (50)** và **e (180)**.

Khác ZREMRANGEBYRANK, lệnh này không quan tâm vị trí thứ mấy. Khi nhiều member có score giống nhau trong khoảng, **tất cả đều bị xóa**.

### 5.2. Biên inclusive, exclusive và vô cực

Redis cho phép biểu diễn những ranh giới sau:

| Biểu thức giới hạn | Ý nghĩa |
| --- | --- |
| **100** | Bao gồm score = 100. |
| **(100** | Không bao gồm score = 100; chỉ xét score lớn hơn 100 khi dùng làm min, hoặc nhỏ hơn 100 khi dùng làm max. |
| **-inf** | Từ âm vô cực, không có cận dưới thực tế. |
| **+inf** | Đến dương vô cực, không có cận trên thực tế. |

Ví dụ:

~~~text
ZADD lesson:row149:bounds 50 p 100 q 100 r 120 s 150 t
ZREMRANGEBYSCORE lesson:row149:bounds (100 150
ZRANGE lesson:row149:bounds 0 -1 WITHSCORES
~~~

Vì **(100** là cận dưới **loại trừ**, lệnh chỉ xóa score **120** và **150**. Hai member score 100 vẫn còn, cùng member score 50.

Nếu muốn xóa **mọi phần tử có score không quá 100**:

~~~text
ZREMRANGEBYSCORE lesson:row149:bounds -inf 100
~~~

Nếu muốn xóa toàn bộ Sorted Set theo score:

~~~text
ZREMRANGEBYSCORE some:zset -inf +inf
~~~

Tuy nhiên, nếu mục tiêu đơn giản là **xóa cả key**, dùng **DEL key** thường rõ ý định hơn. Cần cẩn thận nếu Redis ACL, cấu trúc dữ liệu hoặc các code path khác dựa trên key này.

### 5.3. Dọn dữ liệu có score là timestamp

Một ứng dụng có thể lưu sự kiện theo timestamp trong score:

~~~text
Key: audit:recent
Member: event:<eventId>
Score: thời điểm xảy ra (Unix epoch milliseconds)
~~~

Để xóa mọi entry quá hạn tính tới mốc **cutoffMillis**, dùng:

~~~text
ZREMRANGEBYSCORE audit:recent -inf 1730000000000
~~~

Số ở trên **chỉ minh họa định dạng timestamp**, không đại diện cho “thời điểm hiện tại”. Với nghiệp vụ muốn xóa những phần tử có thời hạn **nhỏ hơn hoặc bằng** cutoff, dùng cận trên inclusive. Nếu cần xóa khi score **nhỏ hơn** cutoff nhưng giữ đúng bằng cutoff, dùng cận trên loại trừ như **(1730000000000**.

Trong Java, khi score được định nghĩa là epoch milliseconds và luôn không âm:

~~~java
long cutoffMillis = java.time.Instant.now()
        .minus(java.time.Duration.ofHours(1))
        .toEpochMilli();

Long removed = stringRedisTemplate.opsForZSet()
        .removeRangeByScore("audit:recent", 0, (double) cutoffMillis);
~~~

Mẫu trên giả định mọi score đều là timestamp mili giây **không âm**. Nếu có thể tồn tại score âm, cận dưới **0** sẽ bỏ sót chúng; khi đó phải chọn cận dưới rộng hơn theo hợp đồng dữ liệu.

Đối với timestamp hiện đại tính bằng mili giây, giá trị vẫn nằm trong phạm vi số nguyên biểu diễn chính xác của số thực double (tới 2^53); nếu dùng nanosecond timestamp hoặc ID số rất lớn, không thể giả định độ chính xác tương tự.

**Quan trọng: score là timestamp không làm member tự hết hạn.** Redis không tự chạy ZREMRANGEBYSCORE theo đồng hồ hệ thống. Muốn dọn thường xuyên, ứng dụng hoặc một worker có lịch chạy phải thực hiện lệnh dọn phù hợp. TTL của Redis là **TTL của cả key**, hoàn toàn khác việc “mỗi member hết hạn theo score”.

### 5.4. Khi nào dùng removeRangeByScore?

Thao tác này hợp với dữ liệu mà **score đã mang ý nghĩa nghiệp vụ có thể so sánh trực tiếp**, chẳng hạn điểm thấp hơn ngưỡng, sự kiện cũ hơn cutoff, tác vụ có thời hạn xử lý trước một thời điểm.

Không nên dùng removeRangeByScore chỉ vì biết thứ hạng hiện tại của member. Khi cần xóa chính xác một user, **remove(key, userId)** vẫn rõ ràng hơn; khi cần giữ N thành viên đứng đầu, **removeRange theo rank** mới mô tả đúng ràng buộc số lượng.

## 6. Xóa theo khoảng từ điển: ZREMRANGEBYLEX

### 6.1. Khoảng từ điển là gì?

Redis Sorted Set có khả năng so sánh **member theo thứ tự từ điển của bytes**, ngoài việc sắp theo score. Lệnh:

~~~text
ZREMRANGEBYLEX key min max
~~~

xóa các member thuộc một khoảng từ điển. Cách áp dụng điển hình là Sorted Set mà **mọi member có cùng score** (thường bằng 0), để thứ tự có ý nghĩa chính là tên member.

Ví dụ tạo một tập member cùng score 0:

~~~text
ZADD lesson:row149:lex 0 alpha 0 beta 0 delta 0 omega
ZRANGE lesson:row149:lex 0 -1 WITHSCORES
~~~

Sau đó:

~~~text
ZREMRANGEBYLEX lesson:row149:lex [alpha (delta
ZRANGE lesson:row149:lex 0 -1 WITHSCORES
~~~

**[alpha** bao gồm member alpha; **(delta** loại trừ delta. Kết quả xóa **alpha** và **beta**, còn lại **delta** và **omega**.

### 6.2. Quy tắc biên từ điển

| Ký hiệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **[** | **[alpha** | Bao gồm giới hạn alpha. |
| **(** | **(alpha** | Loại trừ giới hạn alpha. |
| **-** | **-** | Biên từ điển thấp nhất. |
| **+** | **+** | Biên từ điển cao nhất. |

Ví dụ xóa toàn bộ member trong Sorted Set có cùng score:

~~~text
ZREMRANGEBYLEX lesson:row149:lex - +
~~~

Lưu ý quan trọng: **khi score của member khác nhau, thứ tự chính của Sorted Set là score**. Các lệnh khoảng lex được thiết kế cho tập mà các member cần xét có **cùng score**; khi trộn score và mong chọn một khoảng tên theo thứ tự từ điển toàn cục, kết quả không phải ngữ nghĩa phù hợp và không nên dựa vào.

Ngoài ra, so sánh lex dựa trên **bytes**, không phải quy tắc sắp xếp tiếng Việt theo locale. UTF-8, chữ hoa/chữ thường, dấu và ký tự phân cách có thể ảnh hưởng thứ tự.

### 6.3. Khác biệt với xóa theo score và rank

Giả sử member **alpha** và **beta** có score 0 nhưng **delta** có score 100. Một khoảng lex từ alpha đến delta không thể được hiểu đơn giản là “mọi member có tên trong khoảng chữ cái A–D” bất kể score.

Nếu cần truy vấn theo tên và điểm đồng thời, cân nhắc thêm chỉ mục riêng hoặc mô hình dữ liệu khác. Tránh dùng ZREMRANGEBYLEX cho leaderboard đa dạng score chỉ vì tên lệnh có chữ BYLEX.

Về Spring Data Redis, khả năng thao tác khoảng lex tùy thuộc API và phiên bản Spring Data Redis đang dùng; khi cần thao tác này, hãy xem hợp đồng lệnh Redis **ZREMRANGEBYLEX** và lớp command tương ứng. Những thao tác theo member/rank/score thường được cung cấp trực tiếp và ổn định hơn qua ZSetOperations.

## 7. Xóa theo member so với xóa theo khoảng: chọn đúng ý định

### 7.1. Cùng một bảng xếp hạng nhưng nhiều yêu cầu khác nhau

Giả sử:

~~~text
Member      Score
u1             10
u2             20
u3             30
u4             40
u5             50
~~~

Các yêu cầu sau dẫn tới lệnh khác nhau:

| Yêu cầu | Lệnh đề xuất | Kết quả |
| --- | --- | --- |
| Người dùng u3 rời cuộc thi | **ZREM board u3** | Chỉ u3 bị xóa. |
| Xóa 2 người thấp điểm nhất | **ZREMRANGEBYRANK board 0 1** | Xóa hai member đầu theo rank tăng. |
| Xóa mọi người có điểm không quá 20 | **ZREMRANGEBYSCORE board -inf 20** | Xóa mọi member score ≤ 20. |
| Giữ đúng tối đa 3 người điểm cao | **ZREMRANGEBYRANK board 0 -4** | Xóa các member nằm trước 3 phần tử cuối. |
| Lấy rồi xóa người có score thấp nhất | **ZPOPMIN board** | Trả member/score và xóa khỏi ZSet. |

Hai lệnh **xóa 2 người thấp nhất** và **xóa score ≤ 20** tình cờ có kết quả giống nhau trong dữ liệu ví dụ, nhưng **không tương đương**. Nếu có ba người cùng score 20, xóa theo score có thể xóa nhiều hơn 2; xóa theo rank chỉ xóa hai vị trí.

### 7.2. Xóa phần tử đúng theo giá trị member

Nếu biết member ID, không cần đọc score hay rank trước:

~~~text
ZREM board u3
~~~

So với luồng:

~~~text
ZRANK board u3
ZREMRANGEBYRANK board <rank-vua-doc> <rank-vua-doc>
~~~

ZREM ngắn hơn, rõ ý nghĩa hơn và tránh lỗi **rank thay đổi giữa hai lời gọi** khi có client khác ZADD/ZREM.

Trong ví dụ trên, chuỗi **<rank-vua-doc>** là placeholder diễn giải, không phải số được nhập nguyên văn trong CLI.

### 7.3. Xóa một phần tử nhưng cần lấy cả score trước khi xóa

Nếu muốn **lấy và xóa** phần tử có score nhỏ/lớn nhất, có thể dùng:

~~~text
ZPOPMIN board
ZPOPMAX board
~~~

Kết quả chứa **member và score** được lấy ra. Trong khi đó, ZREM và ZREMRANGE thường trả **số lượng member đã xóa**, không trả danh sách member đã bị xóa.

Điều này quan trọng khi làm queue có ưu tiên hoặc xử lý tác vụ: nếu cần biết tác vụ được lấy ra là gì, ZPOPMIN/ZPOPMAX phù hợp hơn việc đọc ZRANGE rồi xóa bằng một lệnh riêng, vì hai lệnh riêng có thể bị thao tác khác chen vào.

Tuy nhiên, lấy phần tử ra rồi xử lý nghiệp vụ sau đó vẫn có **khoảng lỗi sau pop**: nếu worker crash, phần tử đã bị xóa khỏi ZSet. Khi cần acknowledgment/retry đáng tin cậy, phải thiết kế workflow xử lý riêng.

## 8. Tính nguyên tử và concurrency của các lệnh xóa

### 8.1. Mỗi lệnh xóa đơn lẻ là nguyên tử

Redis xử lý ZREM, ZREMRANGEBYRANK và ZREMRANGEBYSCORE như **một lệnh**. Một client khác không thể chen lệnh vào giữa việc Redis duyệt phạm vi và loại từng member trong cùng lệnh đó.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot A
    participant R as Redis
    participant B as Spring Boot B
    A->>R: ZREMRANGEBYRANK board 0 9
    Note over R: Xác định và xóa 10 vị trí trong một lệnh
    R-->>A: Số member bị xóa
    B->>R: ZADD board 200 user-new
    R-->>B: Kết quả ZADD
~~~

Nếu hai request tới gần nhau, thứ tự Redis xử lý mới quyết định trạng thái cuối. Không có bảo đảm lệnh A luôn đến trước B chỉ vì log của máy A có timestamp nhỏ hơn.

### 8.2. Hai lệnh Java liên tiếp không tự trở thành transaction

Ví dụ một service:

~~~java
redis.opsForZSet().add(boardKey, memberId, score);
redis.opsForZSet().removeRange(boardKey, 0, -101);
~~~

Ý định là thêm/cập nhật điểm rồi chỉ giữ top 100. Tuy nhiên, giữa hai lời gọi:

- Có thể có client khác chèn/cập nhật thêm member.
- Một API đọc có thể nhìn thấy ZSet tạm thời nhiều hơn 100 member.
- Ứng dụng có thể crash sau ZADD và chưa kịp trim.

Nếu hệ thống yêu cầu **mỗi lần cập nhật luôn kết thúc với tối đa 100 member và không có thao tác khác chen vào**, cần gộp logic trong script hoặc Redis transaction phù hợp. Nếu chỉ là cache leaderboard và chấp nhận một khoảng ngắn vượt N, hai lệnh riêng có thể là lựa chọn đơn giản hơn.

### 8.3. Mẫu Lua: ZADD rồi giữ top N

Script minh họa:

~~~lua
-- KEYS[1] : key leaderboard
-- ARGV[1] : score mới
-- ARGV[2] : member ID
-- ARGV[3] : giới hạn số member được giữ

local limit = tonumber(ARGV[3])
local score = tonumber(ARGV[1])

if not limit or limit < 1 or limit ~= math.floor(limit) then
    return redis.error_reply('limit must be a positive integer')
end
if not score then
    return redis.error_reply('invalid score')
end

redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -limit - 1)

return redis.call('ZCARD', KEYS[1])
~~~

Script nhận **một key**, thêm/cập nhật member, xóa những member nằm trước top N và trả cardinality mới. Redis không cho các client khác chen lệnh vào giữa các thao tác script.

Phải xác thực limit trước khi sửa dữ liệu. Lua script không cung cấp rollback tổng quát cho những thay đổi đã xảy ra nếu một lệnh về sau gặp lỗi; cần đảm bảo kiểu key và score hợp lệ, cùng xử lý exception phía ứng dụng.

Trên Redis Cluster, script một key được định tuyến theo slot của key đó. Khi script dùng nhiều key, phải tuân thủ ràng buộc cùng slot và truyền các tên key phù hợp qua **KEYS**.

### 8.4. Khi số member đang thay đổi, rank là ảnh chụp tức thời

Giả sử request A đọc:

~~~text
ZRANK leaderboard alice
~~~

Nó nhận rank 4. Trong lúc đó request B ZADD người chơi khác có điểm thấp hơn, khiến alice chuyển sang rank 5. Nếu request A dùng:

~~~text
ZREMRANGEBYRANK leaderboard 4 4
~~~

nó sẽ xóa **member hiện ở rank 4**, chưa chắc là alice.

Nếu mục tiêu là xóa alice, dùng **ZREM leaderboard alice**. Nếu mục tiêu là xóa member hiện đứng ở một vị trí bất kể là ai, dùng ZREMRANGEBYRANK trực tiếp. Đây là sự khác biệt giữa **xóa theo ID** và **xóa theo vị trí** trong hệ thống concurrent.

## 9. Độ phức tạp và chi phí vận hành

Gọi:

- **N** là tổng số member đang có trong Sorted Set.
- **M** là số member bị xóa.

Độ phức tạp thường được mô tả:

| Lệnh | Độ phức tạp | Điều cần chú ý |
| --- | --- | --- |
| **ZREM key member...** | O(M log N) với M là số member được yêu cầu xử lý | Xóa nhiều member trong một lệnh có chi phí tăng theo số phần tử. |
| **ZREMRANGEBYRANK** | O(log N + M) | Tìm vị trí rồi xóa M member trong khoảng. |
| **ZREMRANGEBYSCORE** | O(log N + M) | Tìm biên score rồi xóa M member thỏa điều kiện. |
| **ZREMRANGEBYLEX** | O(log N + M) trong trường hợp được áp dụng phù hợp | Dùng cho khoảng lex với score đồng nhất. |
| **ZCARD** | O(1) | Đếm member, hữu ích để kiểm tra kích thước. |
| **ZRANGE** | Phụ thuộc vị trí và số kết quả trả về | Tránh lấy toàn bộ dữ liệu lớn để đếm/xác định phạm vi xóa. |

Một lệnh **nguyên tử** vẫn có thể **tốn tài nguyên**. Ví dụ ZREMRANGEBYSCORE xóa hàng triệu member trong một lần có thể chiếm CPU và làm những client khác chờ Redis xử lý xong lệnh. Không nên nhầm “một lệnh” với “chi phí thấp”.

### 9.1. Dọn dữ liệu theo từng đợt khi số lượng quá lớn

Nếu một ZSet rất lớn và cần xóa nhiều dữ liệu cũ, có thể:

1. Xác định cutoff score phù hợp.
2. Dọn theo batch hoặc theo cửa sổ score nhỏ.
3. Theo dõi thời gian thực hiện, số member đã xóa và tải Redis.
4. Lặp lại theo lịch đến khi đạt mục tiêu.

Việc chia nhỏ thành nhiều lệnh có thể giúp giới hạn thời gian chiếm dụng Redis mỗi lần, nhưng **toàn bộ quá trình dọn không còn nguyên tử**. Các request khác có thể thêm/xóa member giữa các batch. Điều này phải phù hợp ngữ nghĩa nghiệp vụ.

Nếu ứng dụng cần hủy cả ZSet lớn và không cần lọc thành viên, có thể xem xét xóa key bằng **UNLINK** (giải phóng bộ nhớ bất đồng bộ theo khả năng Redis hỗ trợ) thay vì xóa từng member trong một lệnh rất lớn.

### 9.2. Xóa không phải cách phân trang thông thường

Đừng dùng ZREMRANGEBYRANK để “chuyển sang trang tiếp theo” nếu mục tiêu chỉ là đọc. Lệnh đó **phá hủy dữ liệu**. Hãy dùng **ZRANGE**/truy vấn phạm vi để đọc; dùng xóa chỉ khi nghiệp vụ thật sự cần loại member.

## 10. TTL, key rỗng và dữ liệu được xóa

Redis ZSet là một key chứa nhiều member. **TTL áp dụng cho toàn bộ key**, không cho từng member.

Ví dụ:

~~~text
ZADD lesson:row149:ttl 1 one 2 two
EXPIRE lesson:row149:ttl 90
TTL lesson:row149:ttl
ZREM lesson:row149:ttl one
TTL lesson:row149:ttl
~~~

Khi còn member **two**, TTL của key vẫn được duy trì và tiếp tục giảm theo thời gian. ZREM thông thường không reset expiration.

Tiếp tục:

~~~text
ZREM lesson:row149:ttl two
EXISTS lesson:row149:ttl
TTL lesson:row149:ttl
~~~

Khi member cuối bị xóa, Sorted Set rỗng và Redis thường xóa luôn **key**. Vì vậy EXISTS trả 0, TTL trả **-2**. Nếu ứng dụng sau đó gọi ZADD để tạo lại key, key mới **không tự kế thừa TTL cũ**.

| Hiện tượng | Cách hiểu |
| --- | --- |
| **ZCARD key = 0** | Có thể key không tồn tại, vì ZCARD trên key vắng mặt trả 0. |
| **TYPE key = none** | Key không tồn tại. |
| **TTL key = -2** | Key không tồn tại. |
| **TTL key = -1** | Key có tồn tại nhưng không có expiration. |
| **TTL key >= 0** | Key còn hạn tính bằng giây, nếu dùng TTL. |

### Score dạng thời gian không thay thế TTL

Nếu một Sorted Set lưu score là thời điểm hết hạn riêng của từng member:

~~~text
tokens:expirations
    token-A -> 1730000000000
    token-B -> 1730000060000
~~~

Redis **không tự xóa token-A** khi đồng hồ đi qua score của nó. Ứng dụng phải gọi ZREMRANGEBYSCORE hoặc một workflow tương ứng. Thậm chí nếu key được đặt TTL, đến hạn key sẽ bị xóa **toàn bộ**, chứ không chỉ xóa những member cũ.

Điều này rất quan trọng nếu ZSet được dùng làm một **chỉ mục thời gian**: xóa member khỏi ZSet chưa chắc xóa dữ liệu thật của token nằm ở key khác. Cần thiết kế nhất quán giữa chỉ mục và bản ghi gốc.

## 11. Ví dụ Spring Boot: API xóa theo member, rank và score

### 11.1. Dependency và kết nối

Với Spring Boot 3.x và Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ Redis Server đang chạy tại localhost:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Nếu Redis có ACL, TLS hoặc chạy trong container/Cluster, phải cấu hình endpoint và credentials thực tế. **StringRedisTemplate** phù hợp trong ví dụ vì key và member ID đều là String, dễ quan sát bằng redis-cli.

### 11.2. Service minh họa

~~~java
package example.redis;

import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardRemovalService {

    private static final String KEY_PREFIX = "lesson:leaderboard:";
    private final StringRedisTemplate redis;

    public LeaderboardRemovalService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String key(String boardId) {
        if (boardId == null || !boardId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid boardId");
        }
        return KEY_PREFIX + boardId;
    }

    /** Xóa đúng các member đã chỉ định; không dựa vào score. */
    public long removeUsers(String boardId, List<String> userIds) {
        Objects.requireNonNull(userIds, "userIds");
        if (userIds.isEmpty()) {
            return 0;
        }
        if (userIds.stream().anyMatch(
                id -> id == null || !id.matches("[A-Za-z0-9_-]+"))) {
            throw new IllegalArgumentException("Invalid userId");
        }
        Long removed = redis.opsForZSet()
                .remove(key(boardId), userIds.toArray());
        return Objects.requireNonNull(removed, "Missing remove result");
    }

    /** Xóa số lượng member thấp điểm nhất từ đầu bảng. */
    public long removeLowest(String boardId, long amount) {
        if (amount <= 0) {
            return 0;
        }
        Long removed = redis.opsForZSet()
                .removeRange(key(boardId), 0, amount - 1);
        return Objects.requireNonNull(removed, "Missing remove result");
    }

    /** Xóa tất cả member có score nằm trong [minScore, maxScore]. */
    public long removeScoreRange(
            String boardId, double minScore, double maxScore) {
        if (!Double.isFinite(minScore)
                || !Double.isFinite(maxScore)
                || minScore > maxScore) {
            throw new IllegalArgumentException("Invalid score range");
        }
        Long removed = redis.opsForZSet()
                .removeRangeByScore(key(boardId), minScore, maxScore);
        return Objects.requireNonNull(removed, "Missing remove result");
    }

    /** Chỉ giữ tối đa limit member đứng đầu theo score giảm dần. */
    public long keepTop(String boardId, long limit) {
        if (limit <= 0 || limit == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid limit");
        }
        Long removed = redis.opsForZSet()
                .removeRange(key(boardId), 0, -limit - 1);
        return Objects.requireNonNull(removed, "Missing remove result");
    }
}
~~~

Ý nghĩa:

- **removeUsers** xóa theo ID member. Nếu một ID không có trong ZSet, nó không làm thay đổi kết quả.
- **removeLowest** xóa một số lượng xác định ở đầu thứ tự tăng theo score.
- **removeScoreRange** xóa tất cả member có score trong khoảng inclusive theo API được sử dụng.
- **keepTop** xóa từ đầu tới vị trí đứng trước N member cao điểm nhất, giữ lại tối đa N member.

Các method này đều gọi **một lệnh Redis** trong ngữ cảnh thông thường. Nếu ứng dụng sử dụng pipeline/transaction, một số API trả kết quả theo cơ chế khác; ví dụ trên dành cho lời gọi trực tiếp từ service.

### 11.3. Ví dụ cách gọi và quan sát kết quả

Khởi tạo bảng từ redis-cli:

~~~text
ZADD lesson:leaderboard:weekly 5 u1 10 u2 15 u3 20 u4 25 u5
ZRANGE lesson:leaderboard:weekly 0 -1 WITHSCORES
~~~

Trong Java:

~~~java
long removedById = service.removeUsers(
        "weekly", List.of("u3", "missing"));

long removedByScore = service.removeScoreRange(
        "weekly", 0.0, 10.0);

long removedByLimit = service.keepTop("weekly", 2);
~~~

Sau khi chạy tuần tự:

1. **removeUsers** xóa **u3** và bỏ qua missing.
2. **removeScoreRange** xóa **u1** và **u2** (score 5 và 10).
3. **keepTop** giữ tối đa 2 member còn lại; trong trạng thái này **u4** và **u5** đã là hai member cuối nên không cần xóa thêm.

Kiểm tra bằng CLI:

~~~text
ZRANGE lesson:leaderboard:weekly 0 -1 WITHSCORES
ZCARD lesson:leaderboard:weekly
ZSCORE lesson:leaderboard:weekly u3
~~~

Kết quả ZSet còn **u4 (20)** và **u5 (25)**, số member là 2; ZSCORE cho u3 trả nil.

## 12. Ví dụ thực tế: retention theo timestamp

Giả sử service ghi những lần thiết bị phát tín hiệu, với mỗi lần phát có ID duy nhất và score là timestamp mili giây:

~~~text
Key: telemetry:seen:device-7
Member: event:1001, event:1002, ...
Score: eventTimeMillis
~~~

Mỗi sự kiện có thể được ghi:

~~~java
redis.opsForZSet().add(
        "telemetry:seen:device-7",
        "event:1001",
        (double) eventTimeMillis
);
~~~

Định kỳ xóa sự kiện cũ hơn mốc giữ lại 24 giờ:

~~~java
long cutoff = java.time.Instant.now()
        .minus(java.time.Duration.ofHours(24))
        .toEpochMilli();

Long removed = redis.opsForZSet().removeRangeByScore(
        "telemetry:seen:device-7",
        0,
        (double) cutoff
);
~~~

**Cần xác định chính xác quy tắc biên:** đoạn trên xóa score **≤ cutoff**. Nếu muốn giữ event xảy ra đúng tại cutoff, cần một cận exclusive và API/lệnh phù hợp.

Không được dùng một member cố định như **device-7** cho mọi sự kiện nếu cần lưu nhiều lần phát, vì ZADD cùng member sẽ **cập nhật score** chứ không thêm entry mới.

Và không nên nhầm việc dọn ZSet với dọn bản ghi nguồn. Nếu payload của event nằm trong Hash hoặc database khác, chỉ số ZSet biến mất không tự xóa payload ở nơi khác.

### Dọn nhiều thiết bị trong Cluster

Nếu mỗi thiết bị có một ZSet riêng, các lệnh xóa một key có thể được định tuyến độc lập tới slot phù hợp. Nếu thiết kế phải cập nhật nhiều key trong **một script/transaction**, cần bảo đảm các key tham gia nằm trong cùng hash slot và được truyền đúng qua KEYS.

Đừng thêm hash tag global vào toàn bộ thiết bị chỉ để dọn chung: điều đó có thể dồn rất nhiều dữ liệu vào một slot. Hash tag nên phản ánh nhóm dữ liệu thực sự cần thao tác atomically.

## 13. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| ZREM trả 0 dù member được truyền | Member không tồn tại hoặc đã bị xóa trước đó | **ZSCORE**, **ZRANK**, kiểm tra serializer/key. |
| Xóa một member nhưng người khác cùng điểm vẫn còn | ZREM dựa trên **member**, không dựa trên score | Nếu cần xóa tất cả điểm bằng nhau, xem ZREMRANGEBYSCORE. |
| Xóa top nhưng lại mất người thấp điểm | ZREMRANGEBYRANK bắt đầu từ thứ tự score **tăng dần** | Dùng rank âm ở cuối hoặc quy tắc keepTop. |
| Xóa theo score lấy mất member bằng ngưỡng | Biên mặc định là **inclusive** | Dùng cú pháp exclusive khi cần. |
| Xóa nhiều hơn số lượng mong muốn | Dùng khoảng score chứa nhiều member đồng điểm | Nếu cần đúng số lượng, xóa theo rank. |
| ZREMRANGEBYLEX cho kết quả khó hiểu | Member có score khác nhau, không có thứ tự lex toàn cục như mong muốn | Dành riêng ZSet score đồng nhất cho truy vấn lex. |
| GET báo WRONGTYPE | Key là Sorted Set, không phải String | Dùng **TYPE** rồi **ZRANGE**, **ZSCORE**. |
| ZCARD bằng 0 và TTL bằng -2 | Đã xóa member cuối, key không còn | Kiểm tra EXISTS/TYPE; không giả định key rỗng vẫn tồn tại. |
| TTL không được reset sau ZREM | ZREM xóa member, thường giữ TTL của key còn tồn tại | Dùng EXPIRE riêng nếu nghiệp vụ cần đổi TTL. |
| Dữ liệu cũ chưa biến mất dù score là timestamp | Score không phải cơ chế expiration tự động | Đặt lịch chạy ZREMRANGEBYSCORE. |
| Trim top N vẫn vượt giới hạn ngắn hạn | ZADD và trim là hai lệnh riêng | Dùng Lua/MULTI khi cần gộp logic. |
| Xóa theo vị trí ảnh hưởng người khác | Rank thay đổi khi các client cập nhật đồng thời | Nếu biết ID, dùng ZREM trực tiếp. |
| Lệnh xóa quá lâu | Một lần xóa quá nhiều member | Xem chi phí O(log N + M), chia batch nếu chính sách cho phép. |
| Java và redis-cli thấy member khác nhau | Khác serializer hoặc tên key thực tế | Kiểm tra RedisTemplate, StringRedisTemplate và prefix. |
| CROSSSLOT trên Cluster | Lệnh/script dùng key ở nhiều slot | Dùng hash tag đúng nhóm, hoặc chia thao tác theo key. |

### Một lưu ý về kiểu trả về của Spring Data Redis

Các method remove/removeRange/removeRangeByScore thường trả **Long** là số phần tử đã xóa. Đừng nhầm Long này với:

- **score** của member;
- **rank** trước khi xóa;
- danh sách member đã bị xóa;
- một boolean biểu thị “toàn bộ các member yêu cầu đều đã tồn tại”.

Ví dụ khi xóa hai ID mà một ID không tồn tại, Long trả về 1 không phải lỗi. Nếu nghiệp vụ cần biết **tên nào đã bị xóa**, phải có cơ chế dữ liệu hoặc API khác phù hợp; đọc trước rồi xóa không cho một snapshot nguyên tử khi có concurrency.

## 14. Bài thực hành tổng hợp bằng redis-cli

Các bước sau dùng **key thử nghiệm riêng** để tránh phụ thuộc vào trạng thái đã chạy ở những mục trước.

### Bước 1. Tạo Sorted Set gồm score trùng

~~~text
ZADD lesson:row149:lab 10 alpha 20 beta 20 gamma 30 delta 40 epsilon
ZCARD lesson:row149:lab
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

Kỳ vọng ZCARD = 5; **beta** và **gamma** cùng score 20 nhưng là hai member.

### Bước 2. Xóa theo chính xác member

~~~text
ZREM lesson:row149:lab beta unknown
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

ZREM trả **1**. gamma vẫn còn với score 20.

### Bước 3. Xóa theo khoảng score

~~~text
ZREMRANGEBYSCORE lesson:row149:lab 20 30
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

Lệnh xóa gamma (20) và delta (30), trả **2**. Còn alpha (10), epsilon (40).

### Bước 4. Xóa theo rank

~~~text
ZREMRANGEBYRANK lesson:row149:lab 0 0
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

Xóa member thấp điểm nhất đang còn là alpha. Chỉ còn epsilon.

### Bước 5. Quan sát key rỗng và TTL

~~~text
ZREM lesson:row149:lab epsilon
ZCARD lesson:row149:lab
TYPE lesson:row149:lab
TTL lesson:row149:lab
~~~

Kỳ vọng ZCARD = 0, TYPE = none, TTL = -2 vì member cuối đã bị xóa và key không còn.

### Bước 6. Thử giữ top 3 bằng rank âm

~~~text
ZADD lesson:row149:labtop 10 a 20 b 30 c 40 d 50 e
ZREMRANGEBYRANK lesson:row149:labtop 0 -4
ZRANGE lesson:row149:labtop 0 -1 WITHSCORES
~~~

Kỳ vọng còn **c (30), d (40), e (50)**. Cần nhớ: đây là giữ **đúng tối đa 3 vị trí**, không phải giữ toàn bộ các member đồng điểm với người đứng thứ ba.

### Bước 7. Thử khoảng lex khi tất cả score bằng nhau

~~~text
ZADD lesson:row149:lablex 0 alpha 0 beta 0 delta 0 omega
ZREMRANGEBYLEX lesson:row149:lablex [alpha (delta
ZRANGE lesson:row149:lablex 0 -1
~~~

Kỳ vọng còn **delta** và **omega**. Cặp **[alpha** / **(delta** thể hiện khoảng bao gồm alpha nhưng loại trừ delta.

### Bước 8. Dọn đúng key dùng cho bài thực hành

~~~text
DEL lesson:row149:lab
DEL lesson:row149:labtop
DEL lesson:row149:lablex
~~~

Chỉ dọn những key bạn sở hữu trong môi trường học tập. Không dùng **FLUSHDB** hay **FLUSHALL** để dọn vài key của bài.

## 15. Quy tắc chọn lệnh trong một service thực tế

Khi cần xóa dữ liệu khỏi Redis Sorted Set, hãy xác định:

1. **Bạn có biết ID member cần xóa không?** Nếu có, dùng **ZREM**; đây là cách biểu diễn xóa theo định danh rõ nhất.
2. **Bạn muốn xóa đúng N vị trí thấp/cao nhất hay mọi member dưới một ngưỡng?** Đúng số lượng thì dùng **ZREMRANGEBYRANK**; ngưỡng score thì dùng **ZREMRANGEBYSCORE**.
3. **Bạn có cần giữ tất cả member đồng điểm ở ranh giới không?** Xóa theo rank và xóa theo score có thể cho kết quả khác nhau.
4. **Bạn đang xử lý timestamp hay ranking?** Timestamp là một cách dùng score; dữ liệu không tự hết hạn theo score nếu không có lệnh dọn.
5. **Bạn có muốn xóa theo tên member không?** Chỉ dùng **ZREMRANGEBYLEX** khi mô hình score và cách so sánh bytes phù hợp với truy vấn lex.
6. **Bạn cần nhận lại phần tử bị loại không?** Dùng **ZPOPMIN/ZPOPMAX** khi mục đích là lấy rồi xóa ở hai đầu score; các lệnh ZREM/ZREMRANGE chỉ trả số lượng.
7. **Có nhiều client cùng cập nhật không?** Tránh đọc rank rồi xóa theo rank trong hai lệnh nếu ý định thực sự là xóa một member cụ thể.
8. **Một lần xóa có thể rất lớn không?** Tính đến chi phí O(log N + M), tác động lên latency và phương án dọn theo batch.
9. **Key có TTL không?** Xóa member không đồng nghĩa xóa key, trừ khi đã xóa hết member; TTL của key còn lại vẫn tiếp tục.
10. **Bạn có dùng Redis Cluster hoặc nhiều Redis key trong một script không?** Phải bảo đảm định tuyến đúng slot và giới hạn phạm vi nguyên tử.

**Ghi nhớ:** Sorted Set cung cấp nhiều cách xóa vì **member, thứ hạng và score là ba trục khác nhau**. **ZREM** xóa đúng member theo ID; **ZREMRANGEBYRANK** xóa một đoạn vị trí trong thứ tự score tăng dần; **ZREMRANGEBYSCORE** xóa mọi member có score nằm trong khoảng; còn **ZREMRANGEBYLEX** dành cho những khoảng từ điển phù hợp với cách tổ chức score. Trong Spring Data Redis, chọn API ZSetOperations dựa trên điều kiện nghiệp vụ cần xóa, rồi kiểm tra ranh giới, concurrency, TTL và chi phí trước khi áp dụng trên dữ liệu lớn.
