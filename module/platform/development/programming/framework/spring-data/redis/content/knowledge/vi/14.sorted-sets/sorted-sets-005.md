# Xử lý điểm số bằng nhau và phân trang ổn định

Redis **Sorted Set (ZSet)** lưu tập hợp các **member duy nhất**, mỗi member có một **score** dạng số thực. Spring Data Redis cung cấp `ZSetOperations` để lưu, cập nhật điểm, truy xuất thứ hạng và lấy một đoạn kết quả. Trong thực tế, ZSet thường được dùng cho leaderboard, danh sách ưu tiên, bảng điểm, xếp hạng sản phẩm và những danh sách có thứ tự.

Khi nhiều member cùng score hoặc khi dữ liệu liên tục thay đổi, hai vấn đề dễ bị nhầm là:

1. **Cùng điểm thì ai đứng trước?** Redis có một quy tắc tie-break xác định, nhưng quy tắc này không tự đồng nghĩa với “đồng hạng” của nghiệp vụ.
2. **Trang tiếp theo bắt đầu ở đâu?** Một kết quả có thứ tự xác định tại mỗi thời điểm chưa chắc phân trang ổn định qua nhiều HTTP request.

**Định nghĩa cần nhớ:**

- **Deterministic ordering**: một tập dữ liệu không đổi luôn trả cùng thứ tự.
- **Stable pagination**: các trang kế tiếp không vô tình lặp hoặc bỏ sót member do cách đặt ranh giới trang.
- **Snapshot consistency**: tất cả trang đại diện cho cùng một phiên bản dữ liệu, ngay cả khi bảng xếp hạng đang cập nhật ở nơi khác.

Redis cung cấp thứ tự xác định trong một ZSet tại thời điểm lệnh chạy. **Redis không tự tạo snapshot xuyên nhiều request phân trang**.

## 1. Thứ tự của Redis Sorted Set khi bằng điểm

Redis sắp xếp ZSet theo hai cấp:

1. **Score** là tiêu chí chính.
2. Khi **score bằng nhau**, member được sắp xếp theo thứ tự **từ điển của chuỗi byte** (lexicographical byte order).

Thứ tự này độc lập với thứ tự `ZADD`. Không nên giả định Redis giữ insertion order.

Ví dụ tạo dữ liệu:

~~~bash
redis-cli DEL demo:leaderboard

redis-cli ZADD demo:leaderboard \
  100 bob \
   95 dave \
  100 carol \
  100 alice
~~~

Truy vấn tăng dần:

~~~bash
redis-cli ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

Kết quả minh họa:

~~~text
dave   95
alice 100
bob   100
carol 100
~~~

Truy vấn giảm dần:

~~~bash
redis-cli ZRANGE demo:leaderboard 0 -1 REV WITHSCORES
~~~

Kết quả:

~~~text
carol 100
bob   100
alice 100
dave   95
~~~

Khi đọc giảm dần, Redis đảo chiều cả **score** và **member lex trong nhóm bằng điểm**. Redis 6.2+ hỗ trợ cú pháp `ZRANGE ... REV`; trong code/tài liệu cũ có thể gặp `ZREVRANGE`, cho kết quả tương ứng.

### 1.1. Ties không làm kết quả trở nên ngẫu nhiên

| Tình huống | Hành vi |
|---|---|
| Hai member khác nhau có cùng score | Cả hai cùng tồn tại, có thứ tự theo byte member |
| `ZADD` cùng member với score mới | Cập nhật score của member hiện có |
| `ZADD` cùng member với score cũ | Không tạo một bản sao member |
| Thay thứ tự thêm các member cùng score | Không làm thay đổi kết quả sắp xếp của tập cuối |
| `ZRANGE` tăng dần | Score tăng, tie member lex tăng |
| `ZRANGE ... REV` | Score giảm, tie member lex giảm |
| Tên member là `user:2`, `user:10` | Sắp theo chữ/byte, không tự hiểu số |

Redis ZSet lưu member theo byte. Với các serializer khác nhau, cùng một Java object có thể tạo ra những byte member khác nhau và ảnh hưởng tới tie-break.

### 1.2. Không dùng tên hiển thị để làm tie-break ngầm

Nếu member là display name, người dùng đổi tên có thể biến một entry thành member mới hoặc thay đổi thứ tự ở nhóm bằng điểm. Thứ tự Redis cũng không hiểu quy tắc alphabet tiếng Việt hoặc các locale khác.

Mẫu an toàn hơn:

~~~text
ZSet member: userId ổn định
ZSet score : điểm của user

DB/Hash riêng:
    userId -> displayName, avatar, metadata
~~~

Nếu yêu cầu đồng điểm phải ưu tiên người hoàn thành sớm, tên theo locale hoặc ID số, cần thiết kế **sort key phụ** có quy tắc rõ ràng, không chỉ kỳ vọng ZSet tự đọc metadata ngoài member.

## 2. Điểm số bằng nhau khác với đồng hạng

Với dữ liệu:

~~~text
carol 100
bob   100
alice 100
dave   95
~~~

Redis vẫn trả **vị trí riêng** cho từng member:

~~~bash
redis-cli ZREVRANK demo:leaderboard carol
# 0

redis-cli ZREVRANK demo:leaderboard bob
# 1

redis-cli ZREVRANK demo:leaderboard alice
# 2

redis-cli ZREVRANK demo:leaderboard dave
# 3
~~~

`ZREVRANK` trả **vị trí 0-based trong thứ tự Redis**, không phải số thứ hạng đồng hạng.

| Cách xếp hạng | carol | bob | alice | dave |
|---|---:|---:|---:|---:|
| Index giảm dần của Redis | 0 | 1 | 2 | 3 |
| Vị trí hiển thị theo index + 1 | 1 | 2 | 3 | 4 |
| Competition rank | 1 | 1 | 1 | 4 |
| Dense rank | 1 | 1 | 1 | 2 |

**Competition rank** của score `s`:

~~~text
rank(s) = 1 + số member có score lớn hơn s
~~~

Có thể dùng điều kiện score **exclusive** trong Redis:

~~~bash
redis-cli ZCOUNT demo:leaderboard '(100' +inf
# 0 => rank 1

redis-cli ZCOUNT demo:leaderboard '(95' +inf
# 3 => rank 4
~~~

**Dense rank** yêu cầu đếm **số giá trị score phân biệt lớn hơn s**, không phải số member, nên không tính trực tiếp bằng `ZCOUNT`. Nếu thường xuyên cần dense rank với nhiều ties, có thể xây chỉ mục score distinct hoặc tổng hợp từ dữ liệu snapshot.

**Kết luận:** API trả danh sách có thể dùng thứ tự member để bảo đảm phân trang, nhưng API hiển thị rank cần tuân theo quy tắc nghiệp vụ riêng.

## 3. Thiết kế member để tie-break dễ kiểm soát

Khi Redis so sánh member bằng byte, chuỗi chứa số có thể gây bất ngờ:

~~~text
user:1
user:10
user:2
~~~

Thứ tự lex tăng là như trên, không phải `1, 2, 10`. Nếu nghiệp vụ muốn ID số tăng trong nhóm cùng điểm, có thể dùng một định dạng zero-padding đủ rộng:

~~~text
user:000001
user:000002
user:000010
~~~

Nhưng phải thống nhất độ rộng, xử lý khi ID vượt miền, và có kế hoạch đổi schema để cursor cũ không mất tương thích.

Các lựa chọn thường gặp:

- Member = database ID dạng String ASCII chuẩn hóa.
- Member = UUID/ULID chuẩn hóa, chỉ khi mỗi thực thể có **một ID không đổi**.
- Member = mã định danh nghiệp vụ được normalize thống nhất giữa producer và consumer.

Không dùng `hashCode()`, `toString()` của object tùy ý hoặc UUID mới mỗi lần `ZADD` như một ID bền vững.

### 3.1. Unicode không có collation theo locale

Redis sắp xếp byte đã được serializer tạo ra. `String.compareTo(...)` trong Java sử dụng thứ tự theo đơn vị UTF-16, có thể không khớp so sánh byte UTF-8 ở một số chuỗi Unicode. Vì vậy, nếu xử lý cursor theo member trong Java, hãy dùng ID ASCII chuẩn hóa hoặc comparator phù hợp với byte encoding Redis.

Đối với giao diện người dùng cần alphabet tiếng Việt, nên tách việc **sắp xếp theo locale nghiệp vụ** khỏi tie-break kỹ thuật của ZSet, bằng index riêng hoặc nơi lưu dữ liệu có khả năng collation tương ứng.

## 4. Spring Data Redis: đọc score và rank

Ví dụ dùng Spring Boot 3.x và `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardStore {

    private static final String KEY = "leaderboard:weekly";

    private final ZSetOperations<String, String> zset;

    public LeaderboardStore(StringRedisTemplate redis) {
        this.zset = redis.opsForZSet();
    }

    public void updateScore(String userId, double score) {
        zset.add(KEY, userId, score);
    }

    public Double findScore(String userId) {
        return zset.score(KEY, userId);
    }

    public Long positionZeroBased(String userId) {
        return zset.reverseRank(KEY, userId);
    }

    public Long totalMembers() {
        return zset.zCard(KEY);
    }
}
~~~

`zset.add(...)` thêm member hoặc cập nhật score nếu member đã có. `score(...)` và `reverseRank(...)` trả null nếu member không tồn tại trong ZSet.

Score của Redis dùng dạng double. Với điểm nghiệp vụ là số nguyên, giữ trong miền biểu diễn chính xác của double; không dùng phép cộng số thực không kiểm soát để tạo tie-break.

### 4.1. Truy vấn trang bằng rank: offset pagination

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardOffsetReader {

    private static final String KEY = "leaderboard:weekly";

    private final StringRedisTemplate redis;

    public LeaderboardOffsetReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Entry> page(long pageIndex, int pageSize) {
        if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page");
        }

        long from = Math.multiplyExact(pageIndex, (long) pageSize);
        long to = Math.addExact(from, pageSize - 1L);

        Set<ZSetOperations.TypedTuple<String>> tuples =
                redis.opsForZSet()
                     .reverseRangeWithScores(KEY, from, to);

        if (tuples == null) {
            return List.of();
        }

        return tuples.stream()
                .map(t -> new Entry(t.getValue(), t.getScore()))
                .toList();
    }

    public record Entry(String memberId, Double score) {}
}
~~~

`reverseRangeWithScores` lấy member kèm score theo thứ tự giảm. API trả một tập `TypedTuple`, thường giữ thứ tự kết quả Redis khi duyệt. Đầu ra đã có thứ tự mong muốn, không nên bỏ vào `HashSet` khác rồi kỳ vọng thứ tự vẫn giữ.

Với page index 0-based, page size 2:

~~~text
page(0, 2) -> rank 0..1
page(1, 2) -> rank 2..3
page(2, 2) -> rank 4..5
~~~

Trong lệnh `ZRANGE`/`ZREVRANGE`, chỉ số cuối **được bao gồm**; vì thế `to = from + pageSize - 1`.

Offset pagination phù hợp cho bảng xếp hạng nhỏ hoặc dữ liệu được đóng băng, nhưng **không bảo đảm không lặp/bỏ sót** khi leaderboard thay đổi giữa những lần đọc.

## 5. Vì sao offset bị trùng hoặc bỏ sót?

Giả sử kết quả ban đầu:

~~~text
Rank    Member   Score
0       bob      100
1       alice    100
2       zoe       90
3       yuna      90
4       tom       85
~~~

Client gọi trang đầu (2 phần tử):

~~~text
ZRANGE leaderboard 0 1 REV WITHSCORES
=> bob, alice
~~~

Trước khi client gọi trang thứ hai, một thành viên mới được thêm với score 105:

~~~text
Rank    Member     Score
0       newuser    105
1       bob        100
2       alice      100
3       zoe         90
4       yuna        90
5       tom         85
~~~

Trang thứ hai theo offset `2..3` bây giờ trả:

~~~text
alice, zoe
~~~

`alice` xuất hiện lần thứ hai. Nếu ngược lại `bob` bị xóa, `zoe` có thể bị bỏ sót do index các member phía sau dịch lên.

Các thay đổi phổ biến:

| Mutation | Rủi ro với offset |
|---|---|
| Thêm member trước vị trí trang kế tiếp | Member đã đọc có thể lặp |
| Xóa member trước vị trí trang kế tiếp | Member chưa đọc có thể bị bỏ qua |
| Cập nhật score làm member di chuyển | Có thể vừa lặp vừa bỏ sót |
| Đổi cùng một score của nhiều member | Redis vẫn deterministic tại một thời điểm, nhưng page boundary có thể dịch |
| Dữ liệu bất biến trong suốt phiên xem | Offset ổn định với cùng sort order |

Ties không phải nguyên nhân duy nhất của lỗi offset. Ngay cả khi mọi member có score khác nhau, những mutation trước vị trí offset vẫn làm dịch index.

## 6. Cursor chỉ dựa trên score vẫn sai khi có ties

Giả sử giảm dần:

~~~text
carol 100
bob   100
alice 100
dave   95
~~~

Trang đầu size 2:

~~~text
carol 100
bob   100
~~~

Nếu cursor chỉ lưu `score = 100`, request tiếp theo lọc `score < 100` sẽ trả:

~~~text
dave 95
~~~

và bỏ sót `alice 100`.

Nếu dùng `score <= 100`, những người đã trả như `carol` và `bob` có thể lặp lại. Do đó, **score không phải một cursor đầy đủ khi nhiều member bằng điểm**.

### 6.1. Cursor phải xác định một vị trí trong thứ tự toàn phần

Với thứ tự score giảm, tie member lex giảm, cursor có thể biểu diễn:

~~~json
{
  "member": "bob",
  "score": 100.0
}
~~~

Một member đứng sau cursor nếu:

~~~text
score < cursor.score

HOẶC

score == cursor.score
VÀ member đứng sau cursor.member theo lex giảm
~~~

Nếu dùng member ID ASCII chuẩn hóa, phần thứ hai có thể hiểu là `member < cursor.member` theo thứ tự lex byte.

Nếu business muốn tie member **tăng dần** trong khi score giảm, quy tắc này không còn đúng y nguyên; phải chọn một sort key/index khác.

## 7. Phân trang bằng anchor member trong ZSet hiện tại

Một cách thực tế là dùng **member cuối trang trước** làm điểm neo (*anchor*):

1. Dùng `ZREVRANK` tìm vị trí hiện tại của member đó.
2. Kiểm tra `ZSCORE` để chắc anchor không đổi điểm.
3. Lấy tiếp từ `rank + 1` bằng `ZRANGE ... REV WITHSCORES`.

Ví dụ:

~~~text
Trang 1: [carol 100, bob 100]
Cursor: member=bob, score=100

Trang 2:
  rank hiện tại của bob = 1
  lấy tiếp từ rank=2
  => alice 100, dave 95
~~~

Nếu thêm một member mới ở **trước bob**, rank của bob tăng theo. Việc tìm rank mới giúp tiếp tục **sau bob hiện tại** thay vì giữ offset cũ.

### 7.1. Cần lấy anchor rank và trang trong cùng một script

Nếu Java gọi `ZREVRANK`, `ZSCORE` và `ZRANGE` qua ba request Redis độc lập, leaderboard có thể thay đổi giữa các lệnh. Có thể gói lại bằng Lua script:

~~~lua
-- KEYS[1]: ZSet
-- ARGV[1]: cursor member, chuỗi rỗng nếu trang đầu
-- ARGV[2]: cursor score, chuỗi rỗng nếu trang đầu
-- ARGV[3]: pageSize + 1

local member = ARGV[1]
local score = ARGV[2]
local size = tonumber(ARGV[3])

if not size or size < 1 or size > 101 then
    return redis.error_reply('INVALID_PAGE_SIZE')
end

local startRank = 0

if member ~= '' then
    local rank = redis.call('ZREVRANK', KEYS[1], member)
    if not rank then
        return redis.error_reply('CURSOR_MEMBER_GONE')
    end

    local currentScore = redis.call('ZSCORE', KEYS[1], member)
    if tonumber(currentScore) ~= tonumber(score) then
        return redis.error_reply('CURSOR_SCORE_CHANGED')
    end

    startRank = rank + 1
end

return redis.call(
    'ZRANGE',
    KEYS[1],
    startRank,
    startRank + size - 1,
    'REV',
    'WITHSCORES'
)
~~~

Script chỉ truy cập **một ZSet key**, nên không vướng quy tắc multi-key cross-slot của Redis Cluster. Redis thực thi script như một thao tác nguyên tử; không có `ZADD`/`ZREM` khác chen vào giữa bước tính rank và đọc trang.

Dùng cú pháp `ZRANGE ... REV` yêu cầu Redis 6.2+. Nếu ZSet trống, script trả danh sách rỗng. Nếu anchor đã mất hoặc đổi score, script báo lỗi cụ thể thay vì âm thầm tiếp tục sai vị trí.

### 7.2. Spring Data Redis gọi script

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardCursorReader {

    private static final String KEY = "leaderboard:weekly";

    private static final String LUA = """
            local member = ARGV[1]
            local score = ARGV[2]
            local size = tonumber(ARGV[3])

            if not size or size < 1 or size > 101 then
                return redis.error_reply('INVALID_PAGE_SIZE')
            end

            local startRank = 0
            if member ~= '' then
                local rank = redis.call('ZREVRANK', KEYS[1], member)
                if not rank then
                    return redis.error_reply('CURSOR_MEMBER_GONE')
                end

                local actual = redis.call('ZSCORE', KEYS[1], member)
                if tonumber(actual) ~= tonumber(score) then
                    return redis.error_reply('CURSOR_SCORE_CHANGED')
                end
                startRank = rank + 1
            end

            return redis.call(
                'ZRANGE', KEYS[1],
                startRank, startRank + size - 1,
                'REV', 'WITHSCORES'
            )
            """;

    private static final RedisScript<List> PAGE_SCRIPT =
            createScript();

    private final StringRedisTemplate redis;

    public LeaderboardCursorReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static RedisScript<List> createScript() {
        DefaultRedisScript<List> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(List.class);
        return script;
    }

    public Page load(Cursor cursor, int pageSize) {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize must be 1..100");
        }

        String afterMember =
                cursor == null ? "" : cursor.member();
        String afterScore =
                cursor == null ? "" : Double.toString(cursor.score());

        // Lấy dư một member để biết còn trang sau không.
        List<?> raw = redis.execute(
                PAGE_SCRIPT,
                List.of(KEY),
                afterMember,
                afterScore,
                Integer.toString(pageSize + 1)
        );

        if (raw == null) {
            throw new IllegalStateException("Missing Redis script result");
        }

        // StringRedisTemplate giải mã các phần tử thành String.
        List<Entry> all = new ArrayList<>();
        for (int i = 0; i + 1 < raw.size(); i += 2) {
            String member = (String) raw.get(i);
            double score = Double.parseDouble((String) raw.get(i + 1));
            all.add(new Entry(member, score));
        }

        boolean hasMore = all.size() > pageSize;
        int count = Math.min(pageSize, all.size());

        List<Entry> visible = List.copyOf(all.subList(0, count));
        Cursor nextCursor = null;

        if (hasMore) {
            Entry last = visible.get(visible.size() - 1);
            nextCursor = new Cursor(last.member(), last.score());
        }

        return new Page(visible, nextCursor);
    }

    public record Entry(String member, double score) {}
    public record Cursor(String member, double score) {}
    public record Page(List<Entry> items, Cursor nextCursor) {}
}
~~~

Ví dụ này dùng một `StringRedisTemplate` nhất quán để deserialize member/score do Lua trả về. Với các template dùng serializer khác, cần cấu hình serializer cho script result phù hợp. Cursor dạng record là **dữ liệu nội bộ**; khi truyền qua HTTP cần có codec và validation riêng.

`pageSize + 1` giúp xác định còn kết quả sau trang hiện tại hay không, không buộc client gọi thêm request vô ích ở trang cuối.

### 7.3. Anchor cursor giải quyết gì và không giải quyết gì?

| Tình huống | Hành vi |
|---|---|
| Thêm một member đứng trước anchor | Anchor rank dịch, vẫn có thể lấy phần tử ngay sau anchor hiện tại |
| Xóa một member đứng trước anchor | Anchor rank dịch, không phải giữ offset cũ |
| Nhiều member có cùng score | Redis tie-break theo member, anchor xác định vị trí |
| Anchor bị xóa | Không tìm được rank, trả cursor stale |
| Anchor đổi score | Score check phát hiện cursor stale |
| Member đã xem chuyển score xuống sau anchor | Có thể xuất hiện lại |
| Member chưa xem chuyển score lên trước anchor | Có thể không bao giờ xuất hiện trong lượt cuộn này |
| Member mới xuất hiện sau anchor | Có thể được trả ở trang sau |
| Muốn toàn bộ trang phản ánh cùng dữ liệu bất biến | Anchor không tự bảo đảm |

**Anchor bảo đảm từng trang được tính nhất quán tại một thời điểm**, nhưng không tạo một snapshot giữa các request. Nếu cần mỗi member đúng một lần trong toàn bộ phiên xem bất kể update, phải dùng dữ liệu bất biến/version.

## 8. Keyset cursor theo (score, member)

Một chiến lược tổng quát là mô tả ranh giới trang bằng tuple:

~~~text
(score, member)
~~~

Với thứ tự **score giảm, member lex giảm**, predicate logic cho phần tử đứng sau cursor là:

~~~text
entry.score < cursor.score
OR (
    entry.score == cursor.score
    AND entry.member < cursor.member theo byte order
)
~~~

Đây là ý tưởng của keyset pagination. Nó không dùng số thứ tự tuyệt đối nên ít bị ảnh hưởng bởi việc chèn/xóa các phần tử trước cursor.

Tuy nhiên, **Redis ZSet một score không có sẵn truy vấn phối hợp hai điều kiện này như một SQL ORDER BY nhiều cột**. Cần chú ý hai bẫy:

### 8.1. Lọc chỉ bằng score làm mất ties

~~~bash
# Lấy mọi entry có score nhỏ hơn 100
redis-cli ZRANGE demo:leaderboard '(100' -inf BYSCORE REV LIMIT 0 20
~~~

Lệnh này sẽ bỏ qua tất cả member score 100 chưa được đọc sau cursor. Nó không phải một keyset cursor hoàn chỉnh cho ties.

### 8.2. ZRANGEBYLEX không thể áp dụng trực tiếp cho tập nhiều score

Redis hỗ trợ `ZRANGEBYLEX` và `ZRANGE ... BYLEX`. Nhưng lex range đúng nghĩa được thiết kế cho các member **có cùng score**. Nếu ZSet có nhiều score khác nhau, không thể lấy lex range như một phép lọc bổ sung độc lập cho toàn bộ score rồi mong nó trả đúng predicate score/member.

Một cách xử lý giản đơn là lấy cả nhóm member cùng score cursor, lọc theo tie-break rồi lấy các score thấp hơn. Nó có thể hợp logic, nhưng khi **hàng trăm nghìn member cùng điểm**, mỗi lần đọc tiếp có thể cần quét nhóm ties rất lớn. Khi ties nhiều và phân trang sâu, nên xét mô hình index hoặc anchor khác.

## 9. Dùng index lex với composite member khi ties rất lớn

Nếu yêu cầu sắp xếp:

~~~text
score thật GIẢM DẦN
nếu bằng score: userId TĂNG DẦN
~~~

và score là số nguyên trong một miền hữu hạn, có thể xây một ZSet **chỉ dùng score Redis = 0**, đưa thứ tự nghiệp vụ vào **member String**.

### 9.1. Encode score theo thứ tự đảo

Giả sử điểm nguyên nằm trong `0..1000`:

~~~text
invertedScore = 1000 - businessScore

indexMember =
    zeroPad(invertedScore, 4)
    + ":"
    + stableUserId
~~~

Ví dụ:

~~~text
user-02, score 900 -> 0100:user-02
user-10, score 900 -> 0100:user-10
user-01, score 850 -> 0150:user-01
~~~

Tạo ZSet:

~~~bash
redis-cli DEL leaderboard:lex

redis-cli ZADD leaderboard:lex \
  0 0100:user-02 \
  0 0100:user-10 \
  0 0150:user-01
~~~

Vì mọi Redis score bằng 0, thứ tự lex **tăng** chính là thứ tự điểm thật **giảm**, ties theo userId tăng.

### 9.2. Cursor lex exclusive ở tầng Redis

Trang đầu:

~~~bash
redis-cli ZRANGEBYLEX leaderboard:lex - + LIMIT 0 2
~~~

Kết quả:

~~~text
0100:user-02
0100:user-10
~~~

Trang tiếp theo dựa vào member cuối `0100:user-10`:

~~~bash
redis-cli ZRANGEBYLEX \
  leaderboard:lex \
  '(0100:user-10' \
  + \
  LIMIT 0 2
~~~

Dấu `(` tạo lower bound **exclusive** nên không lặp chính cursor. Kết quả:

~~~text
0150:user-01
~~~

Không cần tải toàn bộ nhóm member cùng score để tìm vị trí sau cursor. Cách này đặc biệt hữu ích khi hàng trăm nghìn người có cùng điểm.

### 9.3. Hàm encode trong Java

~~~java
import java.util.Locale;

public final class LeaderboardLexKey {

    private static final long MAX_SCORE = 1_000L;

    private LeaderboardLexKey() {}

    public static String encode(long score, String stableUserId) {
        if (score < 0 || score > MAX_SCORE) {
            throw new IllegalArgumentException("Score out of range");
        }
        if (stableUserId == null || stableUserId.isBlank()) {
            throw new IllegalArgumentException("Missing user ID");
        }

        long inverse = MAX_SCORE - score;

        return String.format(
                Locale.ROOT, "%04d:%s", inverse, stableUserId);
    }
}
~~~

Đây là encoding **chỉ đúng cho miền score giả định**. Nếu score có số âm, giá trị thập phân hoặc tăng vượt 1000, phải thiết kế encoding bảo toàn byte order khác. Nếu ID có Unicode hoặc phải escape, cần normalize theo cùng quy tắc cho mọi producer và consumer.

### 9.4. Chi phí duy trì lex index

Ở ZSet bình thường:

~~~text
ZADD leaderboard 920 user-02
~~~

chỉ cập nhật score của member `user-02`.

Ở index lex:

~~~text
score 900 -> 0100:user-02
score 920 -> 0080:user-02
~~~

Member phải đổi tên. Nếu chỉ `ZADD` member mới mà không `ZREM` member cũ, cùng user sẽ xuất hiện hai lần.

Có thể duy trì mapping:

~~~text
Hash leaderboard:lex:by-user
    user-02 -> "0100:user-02"
~~~

và cập nhật cả ZSet lẫn Hash **nguyên tử** bằng Lua:

~~~text
oldIndexMember = HGET mapping userId
if oldIndexMember tồn tại:
    ZREM lexIndex oldIndexMember

newIndexMember = encode(score, userId)
ZADD lexIndex 0 newIndexMember
HSET mapping userId newIndexMember
~~~

Khi dùng Redis Cluster, cả ZSet index và Hash mapping trong script phải cùng hash slot. Ví dụ:

~~~text
leaderboard:{weekly}:lex
leaderboard:{weekly}:by-user
~~~

Một lex index live **vẫn không phải snapshot**. Khi score đổi, composite member di chuyển qua cursor; member đã đọc có thể xuất hiện lại hoặc chưa đọc có thể bị bỏ qua.

## 10. Muốn phân trang nhất quán xuyên các request: dùng snapshot/version

Hợp đồng mạnh nhất thường là:

> Người dùng mở leaderboard tại phiên bản V; mọi trang đều đọc đúng phiên bản V, không bị ảnh hưởng bởi cập nhật live.

Một mô hình:

~~~text
leaderboard:{weekly}:live
    liên tục ZADD/ZREM

leaderboard:{weekly}:snapshot:v17
    đã chốt
    không thay đổi sau khi publish
~~~

Cursor nên gắn với version:

~~~json
{
  "snapshot": "v17",
  "afterMember": "bob",
  "afterScore": 100.0
}
~~~

Mọi trang kế tiếp dùng lại snapshot `v17`, không tự chuyển sang `v18`.

### 10.1. Sao chép ZSet thành snapshot

Redis 6.2+ cung cấp `ZRANGESTORE`, có thể materialize một range thành ZSet khác:

~~~bash
redis-cli ZRANGESTORE \
  'leaderboard:{weekly}:snapshot:v17' \
  'leaderboard:{weekly}:live' \
  0 -1

redis-cli EXPIRE \
  'leaderboard:{weekly}:snapshot:v17' \
  3600
~~~

Kết quả chứa các member và score từ nguồn trong khoảng được chọn. Snapshot phải không bị cập nhật thêm sau khi công bố.

Lệnh tạo bản sao lớn có thể tốn CPU, RAM và làm tăng latency Redis. **Không sao chép leaderboard đầy đủ cho mỗi HTTP request.** Với tập dữ liệu khổng lồ, cân nhắc tạo snapshot theo kỳ, batch ngoài giờ cao điểm hoặc kho dữ liệu có khả năng snapshot khác.

Ví dụ dùng hash tag `{weekly}` để source và destination của lệnh nhiều key thuộc cùng slot trong Redis Cluster. Trong hệ thống nhiều tenant/kỳ, dùng tag theo phạm vi hợp lý, không gom mọi leaderboard vào một slot.

### 10.2. Offset trên snapshot là một lựa chọn đơn giản

Với snapshot bất biến:

~~~text
v17 page 1: rank 0..19
v17 page 2: rank 20..39
v17 page 3: rank 40..59
~~~

Không có mutation làm dịch offset. Do đó `reverseRangeWithScores` đủ để phân trang ổn định; không bắt buộc triển khai keyset để giải quyết vấn đề cập nhật đồng thời.

Nếu một snapshot hết hạn trước khi người dùng tải trang tiếp, API cần trả lỗi rõ và cho phép bắt đầu lại từ version mới. Nên quy định TTL snapshot lớn hơn thời hạn cursor sử dụng hợp lệ, và tránh chính sách eviction có thể xóa snapshot quan trọng sớm hơn dự kiến.

### 10.3. Leaderboard theo kỳ có thể tự là snapshot

Ví dụ bảng tuần đã kết thúc:

~~~text
leaderboard:week:2026-W46:final
leaderboard:week:2026-W47:live
~~~

Khi kỳ W46 đã chốt, key `final` không bị thay đổi nữa. Không cần nhân bản mỗi lần xem; chỉ cần quản lý quyền ghi, version và retention của bảng final.

## 11. Thay đổi score giữa hai trang: giới hạn của live pagination

Ví dụ ban đầu:

~~~text
alice 100
bob    95
carol  90
~~~

Client đọc trang đầu:

~~~text
alice, bob
cursor = bob@95
~~~

Sau đó:

~~~text
carol 110
alice  80
bob    95
~~~

Nếu đọc trang tiếp theo bằng anchor `bob@95` trên dữ liệu live:

- `carol` đã chuyển lên **trước** cursor nên có thể bị bỏ sót trong phiên cuộn.
- `alice` đã chuyển xuống **sau** cursor dù đã được trả ở trang trước, nên có thể xuất hiện lại.

Vấn đề này không do Redis mất ổn định; nó xuất phát từ **dữ liệu thay đổi giữa hai trạng thái đọc**.

Các hợp đồng API có thể chọn:

| Chính sách | Ý nghĩa |
|---|---|
| Live view | Mỗi trang phản ánh dữ liệu ở lúc request; có thể lặp/bỏ sót giữa các trang |
| Anchor/keyset live | Tiếp tục sau ranh giới có thứ tự; giảm lỗi dịch offset nhưng không bảo đảm snapshot |
| Cursor trên immutable snapshot | Tất cả trang đọc cùng version, tránh mutation từ live |
| Chỉ top N mới nhất | Không cần phiên phân trang dài; thường đủ cho dashboard realtime |

Hãy ghi rõ chính sách trong API docs, thay vì hứa “không lặp, không bỏ sót” chỉ vì đã dùng cursor.

## 12. Khi nghiệp vụ yêu cầu tie-break theo nhiều cột

Một yêu cầu thường gặp:

~~~text
ORDER BY score DESC, completedAt ASC, userId ASC
~~~

ZSet thông thường chỉ có một score và một member. Redis **không tự đọc** `completedAt` từ Hash/JSON bên ngoài khi score bằng nhau.

Các hướng có thể dùng:

1. Chấp nhận member ID làm tie-break và hiển thị rank đồng hạng theo score.
2. Tạo composite lex index với schema điểm/thời gian/ID có thể sắp xếp bằng byte.
3. Duy trì chỉ mục phụ hoặc dựng snapshot theo đúng thứ tự nghiệp vụ.
4. Sử dụng datastore hỗ trợ ORDER BY đa cột nếu đó là yêu cầu truy vấn chính.

### 12.1. Cẩn thận với mẹo cộng epsilon

Ví dụ:

~~~text
effectiveScore = score + tinyFractionFromTimestamp
~~~

Rủi ro:

- Hai score khác nhau nhưng rất gần nhau có thể bị đảo thứ tự.
- Float/double có giới hạn độ chính xác.
- Điểm lưu không còn đúng score nghiệp vụ.
- Dữ liệu có thể tràn/khó diễn giải khi thay đổi miền giá trị.

Có thể encode score tổng hợp bằng số nguyên nếu chứng minh miền giá trị và thứ tự; phải bảo đảm kết quả nằm trong giới hạn **số nguyên double biểu diễn chính xác**, thường lưu ý mốc `2^53`. Không tùy tiện pack nhiều chiều vào double.

### 12.2. Không dùng thời điểm thêm ZADD như một tie-break

Redis không giữ “ai được ZADD trước” làm tiêu chí thứ hai. Nếu cần completedAt, phải lưu và encode rõ thời điểm đó vào sort key hoặc có index hỗ trợ. Một lần gọi `ZADD` sau không có nghĩa sẽ đứng sau trong nhóm score bằng nhau.

## 13. Redis Cluster và phân trang leaderboard

Trong Redis Cluster, **mỗi ZSet là một key**. Tất cả member của key đó thuộc một hash slot và một primary ở một thời điểm. Vì vậy:

- Lệnh đọc `ZRANGE`, `ZREVRANK`, `ZSCORE` trên một key hoạt động bình thường.
- Anchor Lua script một key không có vấn đề cross-slot.
- Script cập nhật nhiều key (ví dụ ZSet lex + Hash mapping) phải dùng các key cùng slot.
- Một leaderboard quá nóng có thể trở thành hot key/hot slot; Cluster không tự chia các member của một ZSet ra nhiều primary.

Nếu cần chia leaderboard toàn cục thành nhiều shard, API phải merge theo **score và tie-break** giữa các shard. Pagination ổn định khi đó cần cursor/snapshot ở quy mô phân tán; không thể thay bằng một `ZRANGE` trên bất kỳ shard nào.

Ví dụ dùng hash tag theo từng tenant/kỳ:

~~~text
leaderboard:{acme-W46}:scores
leaderboard:{acme-W46}:mapping
leaderboard:{acme-W46}:snapshot:v17
~~~

Không dùng cùng một hash tag như `{all}` cho mọi tenant nếu không muốn dồn tải vào một slot.

## 14. Serializer ảnh hưởng trực tiếp tie-break và cursor

Redis sắp xếp **byte member**, không phải instance Java. Với `StringRedisTemplate`, member ID String được mã hóa nhất quán theo string serializer.

Với `RedisTemplate<String, UserDto>` dùng serializer JSON/JDK cho member:

- Member có thể dài và khó quan sát.
- Thứ tự tie theo byte JSON/JDK, không theo userId.
- Đổi field/serializer có thể làm byte member đổi và cursor cũ không tìm được.
- Hai bản object cùng đại diện một user nhưng serialize khác có thể là **hai member khác nhau**.

Vì thế, mô hình thường phù hợp:

~~~text
Sorted Set:
    member = stable user ID
    score  = business score

Database/cache theo user ID:
    display name, avatar, extra fields
~~~

Khi ghép dữ liệu hiển thị, hãy **bảo toàn thứ tự ID từ ZSet**. Không tin rằng kết quả query `WHERE id IN (...)` của database sẽ tự sắp theo thứ tự điểm.

Nếu đổi serializer hoặc schema member ở production, cần migration/version và chính sách hết hạn cursor phù hợp.

## 15. Quản lý cursor trong HTTP API

Một cursor có thể gồm:

~~~json
{
  "version": 1,
  "sort": "score_desc_member_desc",
  "scope": "acme/2026-W46",
  "afterMember": "bob",
  "afterScore": 100.0,
  "snapshot": "v17",
  "expiresAt": "2026-11-13T00:00:00Z"
}
~~~

Khi áp dụng thực tế:

- Xác định key/tenant/period từ ngữ cảnh đáng tin cậy.
- Validate page size, member ID, score, version và thời hạn.
- Dùng Base64URL để truyền token nếu muốn, nhưng **Base64URL không phải chữ ký bảo mật**.
- Nếu cursor có thông tin điều khiển quyền truy cập hoặc scope, server phải kiểm tra authorization và cân nhắc ký token.
- Không dùng tên hiển thị làm anchor.
- Không để client tự ý thay snapshot/key Redis để đọc dữ liệu tenant khác.

Trường hợp cursor không còn hợp lệ, API có thể trả lỗi domain/HTTP thích hợp để client bắt đầu lại: token sai định dạng, snapshot hết hạn, anchor mất, hoặc score anchor đã đổi. Quy định rõ contract thay vì tự bắt đầu ở trang sai vị trí.

## 16. Hiệu năng khi phân trang sâu hoặc có nhiều ties

### 16.1. Page size cần giới hạn

Ví dụ chính sách:

~~~text
1 <= pageSize <= 100
~~~

Đây không phải giới hạn Redis, mà là hạn mức API để tránh trả payload quá lớn và giảm thời gian xử lý.

### 16.2. Đừng đọc toàn bộ ZSet để tự cắt trang

~~~bash
# Không nên gọi trên leaderboard cực lớn chỉ để lấy trang đầu:
redis-cli ZRANGE leaderboard:weekly 0 -1 REV WITHSCORES
~~~

Hãy gọi `reverseRangeWithScores` với khoảng rank phù hợp, hoặc script trả tối đa `pageSize + 1`.

### 16.3. Các truy vấn score/lex với offset sâu

Các lệnh `ZRANGEBYSCORE ... LIMIT offset count` hoặc lex range với offset lớn có thể phải bỏ qua nhiều phần tử trước kết quả. Keyset cursor với bound exclusive có thể tránh việc quét lại prefix đã thấy.

Cần phân biệt truy vấn theo **rank** và truy vấn theo **score range**; không đánh đồng chi phí của mọi dạng `ZRANGE`.

### 16.4. Khi một triệu member cùng score

Nếu tất cả score = 0:

- Redis vẫn sắp xếp theo member, deterministic.
- Cursor chỉ chứa score = 0 không có tác dụng.
- Lấy toàn nhóm ties để lọc ở Java rất tốn RAM/băng thông.
- Anchor hoặc lex index có thể phù hợp.
- Nếu chỉ hiển thị top 100, không nhất thiết xây phân trang tới member thứ một triệu.

### 16.5. Giới hạn vòng đời snapshot

Tạo một snapshot ZSet lớn cho mỗi user mở leaderboard có thể làm RAM tăng không kiểm soát. Tốt hơn là tạo snapshot theo **kỳ/version dùng chung**, đặt retention và giới hạn số version còn tồn tại.

## 17. Những tình huống cần nghĩ tới khi triển khai

| Tình huống | Điều cần xác định |
|---|---|
| Leaderboard trống | Trả danh sách rỗng, cursor null |
| Page cuối ít hơn pageSize | Trả đúng số phần tử còn lại |
| Mọi member cùng score | Tie-break vẫn phải xác định, score-only cursor không đủ |
| Member ID có số | Lex hay numeric ID order? |
| Member có Unicode | Quy tắc encoding/so sánh byte |
| Score = 0 hoặc âm | Không nhầm 0 với “không tồn tại” |
| Thêm member trước cursor | Offset có thể lặp, anchor có thể tiếp tục đúng sau member neo |
| Xóa member trước cursor | Offset có thể bỏ sót |
| Xóa member neo | Cursor stale, không âm thầm dùng offset cũ |
| Đổi score member neo | Phát hiện stale nếu có kiểm tra |
| Đổi score member đã đọc | Live cursor có thể lặp |
| Đổi score member chưa đọc | Live cursor có thể bỏ sót |
| Snapshot bị evict/hết TTL | Cần lỗi và cơ chế bắt đầu lại |
| Redis failover | Một request có thể timeout; không tự mặc định script chưa chạy |
| Nhiều tenant | Cursor phải ràng buộc scope và quyền truy cập |

### 17.1. Ví dụ quan sát bằng Redis CLI

~~~bash
redis-cli DEL example:ties
redis-cli ZADD example:ties \
  10 user:2 \
  10 user:10 \
  10 user:1 \
   9 user:3

redis-cli ZRANGE example:ties 0 -1 WITHSCORES
redis-cli ZRANGE example:ties 0 -1 REV WITHSCORES
redis-cli ZREVRANK example:ties user:10
redis-cli ZSCORE example:ties user:10
redis-cli ZCARD example:ties
~~~

Các lệnh trên giúp thấy rõ score, member order và index. Kết quả phụ thuộc byte member, không phải thứ tự `ZADD`.

## 18. Các sai lầm thường gặp

### Sai lầm 1 — “Redis trả ngẫu nhiên khi bằng điểm”

Sai. Redis có thứ tự lex theo byte member. Nhưng đó không phải locale sorting hay insertion order.

### Sai lầm 2 — “ZREVRANK + 1 là rank đồng hạng”

Sai. `ZREVRANK` trả vị trí của từng member; muốn competition rank cần đếm số member có score lớn hơn.

### Sai lầm 3 — “Cursor chỉ chứa score đã đủ”

Sai khi có ties. Dùng score exclusive sẽ bỏ sót member cùng điểm; inclusive có thể lặp.

### Sai lầm 4 — “Offset không bị ảnh hưởng bởi update”

Sai. Chèn, xóa hoặc đổi score trước offset làm các vị trí dịch chuyển.

### Sai lầm 5 — “Anchor cursor tương đương snapshot”

Sai. Anchor cải thiện tiếp tục theo vị trí hiện tại; các member khác vẫn có thể di chuyển qua ranh giới cursor.

### Sai lầm 6 — “ZRANGEBYLEX lọc member trên mọi ZSet”

Sai nếu ZSet chứa nhiều score và ta kỳ vọng một thứ tự lex độc lập toàn cục. Lex index hiệu quả cần thiết kế các member cùng score Redis.

### Sai lầm 7 — “Cộng số rất nhỏ vào score để phân biệt ties là vô hại”

Sai. Floating-point có giới hạn độ chính xác; business score và thứ tự có thể bị thay đổi.

### Sai lầm 8 — “Lưu JSON object làm member vẫn tie-break theo user ID”

Sai. Redis so sánh byte JSON được serialize. Dùng ID ổn định cho leaderboard.

### Sai lầm 9 — “Đổi score trong composite lex index chỉ cần ZADD”

Sai. Composite member đã đổi. Phải xóa index member cũ và thêm mới, đồng bộ mapping.

### Sai lầm 10 — “Snapshot có thể giữ mãi mà không tính bộ nhớ”

Sai. Nhiều bản sao ZSet lớn có thể tốn RAM đáng kể; cần version/TTL/capacity planning.

### Sai lầm 11 — “Base64URL cursor giúp chống giả mạo”

Sai. Đây chỉ là encoding. Scope và quyền truy cập phải kiểm tra ở backend.

### Sai lầm 12 — “Redis Cluster tự chia member của một ZSet lên nhiều node”

Sai. Một ZSet là một key; key thuộc một slot ở một thời điểm. Shard leaderboard là mô hình khác và đòi hỏi merge.

## 19. Chọn chiến lược phù hợp

| Yêu cầu | Cách triển khai | Giới hạn |
|---|---|---|
| Top 10/top 100 cập nhật liên tục | `reverseRangeWithScores` | Mỗi lượt là trạng thái hiện tại |
| Leaderboard nhỏ, ít thay đổi | Offset pagination | Có thể lặp/bỏ sót khi cập nhật |
| Live leaderboard, nhiều trang | Anchor cursor + check score | Cursor stale, không phải snapshot |
| Ties rất lớn, phân trang sâu | Composite lex index + exclusive bound | Phải duy trì mapping/update nguyên tử |
| Trang phải nhất quán cùng một thời điểm | Immutable snapshot/version | Chi phí tạo bản sao và retention |
| Muốn hiển thị đồng hạng | Tính business rank theo score | Không đồng nhất với ZREVRANK |
| Cần sort score + timestamp + ID | Index/snapshot hỗ trợ sort tuple | Không được ZSet một score cung cấp trực tiếp |
| Leaderboard phân mảnh trên nhiều node | Merge/snapshot phân tán | Tăng phức tạp consistency/cursor |

## 20. Quy trình lựa chọn thiết kế

~~~text
                Cần hiển thị danh sách theo điểm
                              |
                     Score ASC hay DESC?
                              |
                       Có thể có ties?
                       /            \
                     Có             Không
                      |               |
            Chọn tie-break ổn định     |
            dựa trên member hoặc index |
                      +-------+-------+
                              |
                  Cần rank đồng hạng không?
                     /             \
                   Có              Không
                    |                |
              Tính rank riêng        |
                    +--------+-------+
                             |
                  Có nhiều trang kết quả?
                     /              \
                   Không             Có
                     |                |
                 Top N range      Dữ liệu thay đổi
                                 giữa request?
                                    /     \
                                  Có      Không
                                   |        |
                             Cần snapshot? Offset
                               /       \
                             Có        Không
                              |          |
                          Immutable    Anchor /
                          snapshot     keyset live
                              \          /
                               +--------+
                                   |
                     Cursor scope + expiry + size limit
                                   |
                     Serializer, Cluster, memory
                                   |
                     Quan sát mutation và ties
~~~

**Kết luận:** Redis ZSet có thứ tự xác định ngay cả khi điểm số bằng nhau: score trước, member byte lex sau. Nhưng phân trang ổn định là một hợp đồng riêng. `reverseRangeWithScores` đủ cho top N hoặc dữ liệu bất biến; cursor theo score đơn không đủ khi có ties; anchor/keyset hỗ trợ phân trang trên dữ liệu live với những giới hạn rõ ràng. Khi yêu cầu mọi trang phản ánh chính xác cùng một trạng thái, hãy chọn **snapshot/version bất biến** và quản lý vòng đời của nó. Trong Spring Data Redis, member ID ổn định, serializer nhất quán và quy tắc tie-break được công bố rõ ràng là nền tảng để leaderboard hoạt động dễ dự đoán.
