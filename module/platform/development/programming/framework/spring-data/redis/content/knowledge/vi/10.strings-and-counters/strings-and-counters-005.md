# Tăng, giảm và kiểm soát kiểu dữ liệu của bộ đếm trong Spring Data Redis

Redis rất phù hợp để quản lý những **bộ đếm (counter)** cần cập nhật nhanh: số lượt xem bài viết, số request trong một cửa sổ thời gian, số lần thử đăng nhập, số công việc còn chờ hoặc số lượng tác vụ đã hoàn thành. Spring Data Redis cho phép thực hiện những thao tác này thông qua `StringRedisTemplate` và `ValueOperations` mà không phải tự viết giao thức Redis.

Tuy nhiên, bộ đếm đúng nghĩa không chỉ là “đọc một con số rồi cộng thêm 1”. Một hệ thống thực tế còn phải giải quyết **kiểu dữ liệu lưu trong Redis, tính nguyên tử khi nhiều request cập nhật đồng thời, giới hạn số âm/số tối đa, TTL, phạm vi khóa, tràn số và sai lệch khi kết nối lỗi**. Bài học này tập trung vào các quyết định đó, bắt đầu từ những lệnh đơn giản và tiến tới các tình huống cần bảo vệ tính đúng đắn.

Các đoạn mã sử dụng Java 17+, Spring Boot 3.x, Spring Data Redis 3.x và Redis server thông dụng. Ý tưởng của API `StringRedisTemplate` áp dụng rộng hơn, nhưng thuộc tính cấu hình và dependency phải được đối chiếu theo phiên bản Spring Boot đang sử dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Biết vì sao một counter nguyên trong Redis thường là **Redis String chứa biểu diễn số nguyên**, không phải một kiểu dữ liệu Redis riêng tên `integer`.
2. Dùng `INCR`, `DECR`, `INCRBY`, `DECRBY` và API Spring Data Redis tương ứng.
3. Hiểu điều gì xảy ra nếu key **chưa tồn tại**, value **không phải số nguyên**, key có **kiểu dữ liệu khác String**, hoặc phép tính **vượt giới hạn số nguyên 64 bit**.
4. Phân biệt phép tăng/giảm **nguyên tử tại Redis** với mô hình đọc–sửa–ghi có thể bị race condition.
5. Thiết kế namespace và serializer để nhiều service không vô tình ghi đè bộ đếm bằng JSON hoặc Java binary serialization.
6. Xử lý TTL cho bộ đếm ngắn hạn và biết khi nào phải dùng thao tác nguyên tử kết hợp tăng và đặt thời hạn.
7. Bảo vệ những quy tắc như không âm, không vượt hạn mức và không tính trùng yêu cầu theo đúng nhu cầu nghiệp vụ.
8. Phân biệt counter phục vụ quan sát/cache với số liệu cần lưu bền vững, kiểm toán hoặc nhất quán với database.

## 2. Redis thực sự lưu bộ đếm như thế nào?

Trong Redis, một bộ đếm số nguyên thông thường dùng **key thuộc kiểu Redis String**; phần value chứa chuỗi chữ số mà các lệnh số nguyên của Redis đọc và cập nhật.

~~~redis
SET demo:counter:views "12"
TYPE demo:counter:views
GET demo:counter:views
INCR demo:counter:views
GET demo:counter:views
~~~

Kết quả quan trọng:

~~~text
TYPE  -> string
GET   -> "12"
INCR  -> (integer) 13
GET   -> "13"
~~~

Lệnh `TYPE` trả `string` kể cả khi ứng dụng coi giá trị là số. Lệnh `INCR` yêu cầu **nội dung của String** là một số nguyên hợp lệ; Redis không lưu đây là một field `Long` của Java.

### 2.1. Mỗi key có một kiểu dữ liệu Redis

Redis hỗ trợ String, Hash, List, Set, Sorted Set, Stream… Một key đang là Hash sẽ không thể dùng `INCR` như với String:

~~~redis
HSET demo:user:42 name "Lan"
INCR demo:user:42
~~~

Redis trả lỗi tương tự:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

Muốn tăng một **field số nguyên trong Redis Hash**, dùng `HINCRBY` thay vì `INCR`:

~~~redis
HSET demo:article:42 views 10
HINCRBY demo:article:42 views 1
HGET demo:article:42 views
~~~

Lệnh `HINCRBY` có thể tăng hoặc giảm một field bằng số nguyên; field chưa tồn tại được xem như 0. Đây là phép toán **nguyên tử cho field Hash được chỉ định**, phù hợp khi gom nhiều trường của một entity trong một Hash. Bài này chủ yếu đi theo counter String, nhưng cần biết lựa chọn Hash để tránh chọn nhầm API.

### 2.2. Kiểu String chứa số nguyên khác JSON chứa số

So sánh:

| Dữ liệu Redis | Có dùng trực tiếp `INCR`? | Giải thích |
| --- | --- | --- |
| `"42"` | Có | String chứa biểu diễn số nguyên hợp lệ |
| `"-4"` | Có | Số nguyên âm cũng được hỗ trợ |
| `"0"` | Có | Giá trị 0 hợp lệ |
| `"42.0"` | Không | Không phải dạng số nguyên được lệnh `INCR` chấp nhận |
| `"{\"count\":42}"` | Không | Đây là text JSON, không phải một số nguyên đơn lẻ |
| `"42 lượt"` | Không | Có ký tự không thuộc biểu diễn số nguyên |
| Redis Hash chứa field `views=42` | Không | Key có kiểu Hash; dùng `HINCRBY` |
| Value viết bằng JDK serializer | Thông thường không | Bytes là Java serialization, không phải chuỗi số Redis có thể parse |

Nếu đã chọn counter String, cần bảo đảm **mọi writer** dùng chung key đều tuân theo định dạng số nguyên. Một service vô tình `SET key {"count":42}` sẽ khiến các thao tác tăng sau đó lỗi.

## 3. Các lệnh Redis cơ bản: INCR, DECR, INCRBY, DECRBY

### 3.1. `INCR`: tăng 1

~~~redis
DEL demo:counter:signup
INCR demo:counter:signup
INCR demo:counter:signup
GET demo:counter:signup
~~~

Với một key **chưa tồn tại**, Redis coi giá trị ban đầu là 0 cho phép toán tăng, nên lần `INCR` đầu trả 1 và tạo key mới. Lần thứ hai trả 2.

### 3.2. `DECR`: giảm 1

~~~redis
SET demo:counter:stock 5
DECR demo:counter:stock
GET demo:counter:stock
~~~

Giá trị sau `DECR` là 4. Nếu key chưa tồn tại:

~~~redis
DEL demo:counter:test-decr
DECR demo:counter:test-decr
~~~

Kết quả là **-1**. Redis không tự áp dụng quy tắc “bộ đếm không được âm”. Nếu nghiệp vụ không cho âm, bạn phải thiết kế bảo vệ ở tầng thao tác Redis.

### 3.3. `INCRBY`: tăng nhiều đơn vị

~~~redis
SET demo:counter:downloads 10
INCRBY demo:counter:downloads 5
GET demo:counter:downloads
~~~

Kết quả là 15. Với key chưa tồn tại, `INCRBY key 5` trả 5.

### 3.4. `DECRBY`: giảm nhiều đơn vị

~~~redis
SET demo:counter:queue 25
DECRBY demo:counter:queue 7
GET demo:counter:queue
~~~

Kết quả là 18. Với key chưa tồn tại, `DECRBY key 7` tạo giá trị -7.

### 3.5. Bảng hành vi tổng hợp

| Lệnh | Giá trị trước | Kết quả sau | Đặc điểm |
| --- | ---: | ---: | --- |
| `INCR k` | key chưa có | 1 | Coi giá trị ban đầu là 0 |
| `INCR k` | 10 | 11 | Tăng 1 |
| `DECR k` | key chưa có | -1 | Có thể sinh số âm |
| `DECR k` | 10 | 9 | Giảm 1 |
| `INCRBY k 4` | key chưa có | 4 | Tăng theo delta |
| `INCRBY k 4` | 10 | 14 | Delta nguyên |
| `DECRBY k 4` | key chưa có | -4 | Giảm từ giá trị 0 |
| `DECRBY k 4` | 10 | 6 | Delta nguyên |

Các lệnh tăng/giảm trả về **giá trị sau cập nhật**. Đừng nhầm với các API đôi khi trả về giá trị *trước khi* sửa như `GETSET`/`getAndSet(...)`.

## 4. Vì sao cần thao tác tăng/giảm nguyên tử?

Giả sử counter ban đầu bằng 5. Hai request A và B cùng tăng:

~~~text
Cách dễ sai: GET -> cộng bằng Java -> SET

Request A: GET => 5
Request B: GET => 5
Request A: SET 6
Request B: SET 6

Kết quả cuối: 6
Giá trị đúng sau hai lần tăng: 7
~~~

Đây là **lost update**, một dạng race condition. Việc đặt `synchronized` ở một instance Java cũng không giải quyết đủ nếu hệ thống chạy nhiều process/replica khác nhau.

Khi dùng `INCR`:

~~~text
Redis xử lý INCR từ A: 5 -> 6
Redis xử lý INCR từ B: 6 -> 7

Kết quả cuối: 7
~~~

Redis thực hiện thao tác tăng/giảm trên key một cách nguyên tử ở cấp lệnh. Các request đồng thời không chen một phép cập nhật khác vào giữa nội bộ một lệnh `INCR`.

**Giới hạn quan trọng:** tính nguyên tử của một lệnh **không** biến một chuỗi nhiều lệnh thành một transaction. Ví dụ `INCR key` rồi `EXPIRE key 60` là **hai thao tác**; lỗi, ngắt kết nối hoặc một thao tác từ client khác có thể xảy ra ở giữa. Khi cần bảo đảm điều kiện có nhiều bước, phải dùng primitive phù hợp như Lua script, transaction hoặc một lệnh Redis vốn đã đáp ứng yêu cầu.

## 5. Tăng/giảm với StringRedisTemplate trong Spring Data Redis

### 5.1. Chuẩn bị ứng dụng

Trong dự án Spring Boot có quản lý phiên bản dependency phù hợp, thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Chạy Redis cục bộ:

~~~bash
docker run --name redis-counter-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-counter-lab redis-cli PING
~~~

Kỳ vọng lệnh `PING` trả `PONG`. Nếu port 6379 đã được sử dụng, chọn port host khác và cập nhật cấu hình. Container ở ví dụ bind vào loopback cho thực hành, không mở Redis không có xác thực ra Internet.

`application.yml` (Spring Boot 3.x):

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Khi ứng dụng và Redis nằm trong hai container cùng Docker Compose, host kết nối thường là **tên Redis service**, không phải `localhost` của container ứng dụng. Trong môi trường thật, còn cần ACL/password/TLS, giới hạn mạng và cấu hình timeout phù hợp.

### 5.2. Tại sao ưu tiên StringRedisTemplate?

`StringRedisTemplate` mặc định sử dụng serializer dạng String cho cả key và value. Counter Redis lưu biểu diễn số nguyên dạng text; việc ghi `"10"` và sau đó gọi `INCR` không phải đối mặt với Java binary serialization.

Ví dụ service:

~~~java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CounterService {

    private final StringRedisTemplate redis;

    public CounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increment(String key) {
        Long value = redis.opsForValue().increment(key);
        return requireResult(value);
    }

    public long decrement(String key) {
        Long value = redis.opsForValue().decrement(key);
        return requireResult(value);
    }

    public long incrementBy(String key, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        Long value = redis.opsForValue().increment(key, amount);
        return requireResult(value);
    }

    public long decrementBy(String key, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        Long value = redis.opsForValue().decrement(key, amount);
        return requireResult(value);
    }

    private long requireResult(Long value) {
        if (value == null) {
            throw new IllegalStateException(
                    "Redis did not return a counter result");
        }
        return value;
    }
}
~~~

Service này cho thấy bốn API chính:

| Spring Data Redis | Lệnh Redis tương ứng | Giá trị trả về thông thường |
| --- | --- | --- |
| `opsForValue().increment(key)` | `INCR key` | `Long` mới |
| `opsForValue().decrement(key)` | `DECR key` | `Long` mới |
| `opsForValue().increment(key, amount)` | `INCRBY key amount` | `Long` mới |
| `opsForValue().decrement(key, amount)` | `DECRBY key amount` | `Long` mới |

Khi gọi template thông thường, các API có thể trả về `Long`. Trong một số ngữ cảnh đặc biệt như pipeline/transaction, lời gọi trung gian có thể trả `null` vì kết quả được thu thập hoặc xử lý sau. Ví dụ trên giả định chạy trực tiếp như một operation thông thường và nêu lỗi nếu không nhận được kết quả; đừng bỏ kiểm tra nullable nếu kiểu trả về là `Long`.

### 5.3. Truy vấn và khởi tạo giá trị bộ đếm

Có thể đọc raw value bằng:

~~~java
String raw = redis.opsForValue().get("shop:article:42:views");
~~~

Với key chưa tồn tại, `raw` thường là `null`; với key chứa số hợp lệ, ví dụ `"15"`. Để chuyển về `long`:

~~~java
public long readCounter(String key) {
    String value = redis.opsForValue().get(key);
    if (value == null) {
        return 0L; // Quy ước nghiệp vụ: key chưa có tương đương 0.
    }
    return Long.parseLong(value);
}
~~~

Đoạn trên đặt trong service có field `redis`. Nếu value hiện tại không biểu diễn số nguyên hợp lệ hoặc vượt giới hạn `long`, `Long.parseLong(...)` sẽ báo lỗi. Với dữ liệu quan trọng, không nên catch mọi lỗi parse rồi âm thầm trả 0 vì có thể che mất sự cố schema hoặc một writer đã ghi sai dữ liệu.

Khi chỉ cần tăng từ 0, **không cần gọi `SET key 0` trước**: `INCR` đã tự xử lý key chưa tồn tại. Việc khởi tạo trước chỉ có lý do nếu cần TTL từ thời điểm chuẩn bị, hoặc cần quy tắc tạo key riêng.

### 5.4. Định dạng key theo nghiệp vụ

Không nên nhận key tùy ý từ người dùng rồi trực tiếp truyền vào Redis. Service nên tạo key từ namespace và ID đã được kiểm tra:

~~~java
public long recordArticleView(long articleId) {
    if (articleId <= 0) {
        throw new IllegalArgumentException("Invalid article ID");
    }
    String key = "shop:article:" + articleId + ":views";
    return increment(key);
}
~~~

Ví dụ key có cấu trúc:

~~~text
shop:article:42:views
shop:article:43:views
shop:product:42:views
shop:quota:user-17:2026-11-12
~~~

Key cần phân biệt entity, feature, tenant hoặc thời gian khi nghiệp vụ yêu cầu. Tránh đưa token, mật khẩu hoặc thông tin cá nhân không cần thiết vào key vì tên key thường được nhìn thấy trong công cụ quản trị và log.

## 6. Kiểm soát kiểu dữ liệu bộ đếm

Đây là nguyên nhân phổ biến gây lỗi: Java khai báo một kiểu nhưng Redis value do **serializer** quyết định.

### 6.1. RedisTemplate<K, V> không tự biến Long thành chuỗi số

Đoạn code sau có thể gây hiểu nhầm:

~~~java
RedisTemplate<String, Long> template = new RedisTemplate<>();
template.setConnectionFactory(redisConnectionFactory);
~~~

Type parameter `Long` **không bảo đảm** Redis lưu value thành text `"42"`. Nếu template dùng `JdkSerializationRedisSerializer`, value có thể là các bytes nhị phân; sau đó lệnh `INCR` không parse được như số nguyên.

Để thao tác counter rõ ràng, nên dùng:

~~~java
StringRedisTemplate redis = ...;
redis.opsForValue().set("demo:counter", "42");
redis.opsForValue().increment("demo:counter");
~~~

Hoặc tự tạo template với serializer cụ thể phù hợp kiểu Java, chẳng hạn `GenericToStringSerializer<Long>` cho value `Long` trong những tình huống cần một `RedisTemplate<String, Long>`. Nhưng cách này chỉ nên chọn khi có lý do; với counter đơn giản, `StringRedisTemplate` dễ quan sát và dễ đồng bộ giữa nhiều client.

### 6.2. Không trộn serializer trên cùng một key

Giả sử service A sử dụng `StringRedisTemplate`:

~~~java
redis.opsForValue().set("demo:counter:views", "10");
~~~

Service B dùng template lưu JSON:

~~~json
{"views":10}
~~~

Nếu B ghi JSON vào **chính key** `demo:counter:views`, service A gọi `increment(...)` sẽ thất bại. Cả JSON object và số `"10"` đều là Redis String, nên `TYPE key` chỉ cho biết `string` mà **không chứng minh value phù hợp để tăng**.

Quy ước tốt:

1. Mỗi namespace có **một hợp đồng định dạng dữ liệu**.
2. Counter nguyên dùng String thể hiện số nguyên, cùng charset/serializer ở các writer.
3. DTO JSON dùng key riêng, ví dụ `shop:article:42:detail`.
4. Redis Hash counter sử dụng `HINCRBY` hoặc `HashOperations.increment(...)` tương ứng.
5. Khi đổi serializer, xử lý key cũ và triển khai version/prefix rõ ràng thay vì viết đè tùy tiện.

### 6.3. Lỗi do value không phải số nguyên

~~~redis
SET demo:bad-counter "12.5"
INCR demo:bad-counter
~~~

Lỗi có dạng:

~~~text
ERR value is not an integer or out of range
~~~

Tương tự, value `"abc"`, JSON, số quá lớn hoặc binary bytes không phù hợp đều có thể khiến lệnh tăng/giảm nguyên báo lỗi.

**Không nên tự bắt lỗi rồi xóa key để thử lại** nếu key mang dữ liệu nghiệp vụ quan trọng. Trước tiên xác định writer, schema, serializer và vai trò của key. Với cache/bộ đếm tạm có thể tái tạo, cần chính sách khôi phục đã được thống nhất trước.

## 7. Giới hạn 64 bit và tràn số

Các lệnh tăng/giảm số nguyên của Redis hoạt động với **signed 64-bit integer**. Khoảng giá trị hợp lệ tương ứng:

\[
-2^{63} \leq n \leq 2^{63}-1
\]

Tức là từ **-9.223.372.036.854.775.808** đến **9.223.372.036.854.775.807**. Kiểu `long` của Java có cùng giới hạn.

Thử nghiệm với số lớn nhất:

~~~redis
SET demo:counter:max 9223372036854775807
INCR demo:counter:max
~~~

Redis từ chối phép tăng gây overflow thay vì âm thầm quấn vòng về số âm. Tương tự, `DECR` trên giá trị thấp nhất cũng vượt giới hạn.

### 7.1. Ứng dụng cần quyết định cách xử lý tràn số

Tùy nghiệp vụ:

- Bộ đếm lượt xem có thể cần lưu tổng hợp định kỳ vào database và bắt đầu một key/cửa sổ mới.
- Bộ đếm hạn mức có giới hạn nhỏ hơn rất nhiều so với `Long.MAX_VALUE`, nên phải kiểm tra hạn mức trước khi tăng.
- Nếu số liệu thực sự vượt 64 bit, cần một mô hình dữ liệu/thuật toán khác; không thể chỉ đổi kiểu Java sang `BigInteger` rồi kỳ vọng `INCR` hỗ trợ.

Redis và Java đều có thể trả lỗi khi không thể biểu diễn kết quả. Không nên tự chuyển sang `double` chỉ để tránh giới hạn nguyên vì có thể làm mất độ chính xác.

## 8. Bộ đếm số thực và INCRBYFLOAT

Redis có lệnh `INCRBYFLOAT` cho phép tăng một String chứa số thập phân:

~~~redis
SET demo:score "1.5"
INCRBYFLOAT demo:score 0.25
GET demo:score
~~~

Kết quả là giá trị biểu diễn 1.75. Trong Spring Data Redis:

~~~java
Double value = stringRedisTemplate.opsForValue()
        .increment("demo:score", 0.25d);
~~~

**Đây không phải phép cộng số nguyên.** Nếu sau đó dùng `INCR demo:score` trên value thập phân, Redis có thể báo “not an integer”. Vì vậy hãy tách namespace cho counter nguyên và accumulator số thực:

~~~text
demo:counter:orders       # số nguyên -> INCR / INCRBY
demo:score:rolling        # số thực  -> INCRBYFLOAT
~~~

### 8.1. Khi nào không nên dùng INCRBYFLOAT?

Không dùng số thực nhị phân như một giải pháp mặc định cho **tiền, số dư, hạn mức thanh toán hoặc giao dịch yêu cầu chính xác tuyệt đối**. Dù Redis xử lý biểu diễn số thập phân cho lệnh này, việc chuyển qua kiểu `double` của Java và khác biệt về biểu diễn/rounding có thể gây sai lệch nghiệp vụ.

Nếu đơn vị nhỏ nhất được xác định (ví dụ đồng, cent, điểm nguyên), có thể **quy đổi sang số nguyên** và dùng `INCRBY` khi giới hạn 64 bit đủ dùng. Với dữ liệu tài chính cần độ chính xác, kiểm toán và transaction, phải chọn kho dữ liệu và thiết kế nghiệp vụ phù hợp; một counter Redis riêng lẻ không thay thế cơ chế sổ cái.

## 9. TTL: bộ đếm nên tồn tại bao lâu?

Không phải counter nào cũng cần lưu mãi:

| Nhu cầu | Cách đặt vòng đời gợi ý | Điều phải quyết định |
| --- | --- | --- |
| Tổng lượt xem từ trước đến nay | Có thể không TTL, nhưng cần persistence/đồng bộ nếu quan trọng | Redis có phải nguồn dữ liệu cuối cùng không? |
| Số request mỗi phút | TTL theo cửa sổ hoặc cấu trúc key gắn thời gian | Fixed window, sliding window hay token bucket? |
| Số lần thử OTP | TTL ngắn gắn với khoảng bảo vệ | Có cần reset sau thành công không? |
| Số tác vụ đang chạy | Theo job lifecycle, có cleanup/timeout | Nếu worker crash thì bộ đếm có lệch không? |
| Bộ đếm dùng cho dashboard tạm | Có thể TTL vài giờ/ngày | Có nguồn thay thế khi key hết hạn không? |

Redis hỗ trợ:

~~~redis
SET demo:attempts:42 0 EX 60
INCR demo:attempts:42
TTL demo:attempts:42
PTTL demo:attempts:42
~~~

`TTL` trả số giây còn lại, `PTTL` trả thời gian theo mili giây. Những giá trị đặc biệt:

- `-1`: key tồn tại nhưng **không có expiration**.
- `-2`: key **không tồn tại**.
- Giá trị không âm: thời gian còn lại theo đơn vị của lệnh.

Với một key đã có TTL, `INCR`/`DECR` thông thường **không xóa TTL hiện tại**; chúng sửa value nhưng giữ thời hạn. Ngược lại, lệnh `SET key value` thông thường có thể loại bỏ TTL cũ nếu không dùng tùy chọn giữ expiration phù hợp. Tránh vô tình dùng `set(key, "0")` để reset counter định kỳ khi đang muốn giữ TTL.

### 9.1. Hai lệnh tăng rồi đặt TTL có một khoảng hở

Ví dụ dễ viết:

~~~java
String key = "demo:attempts:user-42";
redis.opsForValue().increment(key);
redis.expire(key, Duration.ofMinutes(5));
~~~

Nhưng có hai vấn đề:

1. Nếu tiến trình lỗi **sau `INCR` nhưng trước `EXPIRE`**, key có thể tồn tại không thời hạn.
2. Mỗi lần gọi `expire(...)` sẽ **làm mới TTL**; đó là vòng đời “5 phút kể từ lần cập nhật gần nhất”, không còn là “5 phút kể từ lần đầu”.

Hai chiến lược này có ý nghĩa khác nhau:

~~~text
Fixed lifetime từ lần đầu:
  lần 1 -> TTL 5 phút
  lần 2 -> TTL còn 4 phút, không reset
  lần 3 -> TTL còn 2 phút, không reset

Sliding idle timeout:
  lần 1 -> TTL 5 phút
  lần 2 -> TTL lại 5 phút
  lần 3 -> TTL lại 5 phút
~~~

Chọn đúng theo nghiệp vụ trước khi viết code. Nếu cần tăng và đặt TTL theo một quy tắc **nguyên tử**, dùng lệnh phù hợp hoặc Lua script.

## 10. Tăng và thiết lập TTL nguyên tử bằng Lua

Redis thực thi Lua script như một thao tác nguyên tử tại server. Ví dụ dưới đây dùng cho **namespace bộ đếm ngắn hạn**, cần:

- Tăng giá trị lên 1.
- Nếu key chưa có TTL, đặt TTL một lần.
- Nếu key đã có TTL thì giữ thời hạn hiện tại.

Script:

~~~lua
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])

if ttl == -1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end

return count
~~~

Sau `INCR`, key chắc chắn đã tồn tại nếu không có lỗi. Vì vậy `TTL == -1` nghĩa là chưa được đặt thời hạn và script sẽ đặt TTL. Các lần tăng tiếp theo giữ TTL đang chạy, trừ khi dữ liệu trước đó bị writer khác chủ động xóa expiration. **Chỉ dùng script trên namespace mà mọi counter đều được phép có TTL**, bởi nó cũng bổ sung TTL cho key đã tồn tại nhưng trước đây được định nghĩa là không hết hạn.

### 10.1. Tạo RedisScript bean trong Spring

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration(proxyBeanMethods = false)
public class CounterScriptConfig {

    @Bean
    RedisScript<Long> incrementWithTtlScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
            local count = redis.call('INCR', KEYS[1])
            if redis.call('TTL', KEYS[1]) == -1 then
                redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
            end
            return count
            """);
        script.setResultType(Long.class);
        return script;
    }
}
~~~

### 10.2. Gọi script từ service

~~~java
package com.example.redis;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class ExpiringCounterService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> incrementWithTtlScript;

    public ExpiringCounterService(
            StringRedisTemplate redis,
            RedisScript<Long> incrementWithTtlScript) {
        this.redis = redis;
        this.incrementWithTtlScript = incrementWithTtlScript;
    }

    public long increaseOnceAndStartTtl(String key, Duration ttl) {
        if (ttl == null || ttl.getSeconds() < 1) {
            throw new IllegalArgumentException("TTL must be at least 1 second");
        }

        Long result = redis.execute(
                incrementWithTtlScript,
                List.of(key),
                Long.toString(ttl.getSeconds())
        );
        if (result == null) {
            throw new IllegalStateException("Missing script result");
        }
        return result;
    }
}
~~~

Code sử dụng `StringRedisTemplate` để serialize key và tham số script thành String; script nhận key qua `KEYS[1]` và TTL qua `ARGV[1]`. Việc tăng và đặt TTL đều diễn ra trong **một lần thực thi script Redis**, loại bỏ khoảng hở giữa hai lệnh độc lập.

**Không nên biến script thành nơi xử lý nghiệp vụ phức tạp kéo dài**: script chạy trên Redis và có thể làm chậm các lệnh khác nếu chiếm CPU quá lâu. Script ngắn, thao tác trên ít key và có thời gian thực thi kiểm soát được là lựa chọn hợp lý.

### 10.3. TTL vẫn không phải bảo đảm dữ liệu bền vững

TTL quyết định thời điểm key hết hạn, không đảm bảo Redis sẽ giữ key trong mọi trường hợp lỗi. Nếu Redis dùng eviction do thiếu memory, key có thể biến mất sớm tùy chính sách `maxmemory-policy`; nếu thiếu persistence/replication phù hợp, dữ liệu có thể mất khi server gặp sự cố. Bộ đếm mang ý nghĩa tài chính hoặc cần kiểm toán phải có thiết kế lưu bền vững riêng.

## 11. Bộ đếm không được âm: vì sao DECR chưa đủ?

Giả sử Redis đang giữ số lượng tồn kho bằng 1, hai request cùng bán hàng:

~~~text
Request A: GET stock -> 1
Request B: GET stock -> 1
Request A: thấy còn hàng -> DECR -> 0
Request B: thấy còn hàng -> DECR -> -1
~~~

`DECR` tự nó là nguyên tử, nhưng **điều kiện “chỉ giảm nếu còn hàng”** nằm ngoài lệnh nên vẫn bị race condition. Kiểm tra bằng `GET` trước khi `DECR` không bảo vệ được quy tắc.

Có thể giải quyết bằng Lua script kiểm tra và giảm trong cùng một thao tác:

~~~lua
local current = redis.call('GET', KEYS[1])
if not current then
    return -1
end

local count = tonumber(current)
if not count then
    return redis.error_reply('counter must be numeric')
end

if count <= 0 then
    return -1
end

return redis.call('DECR', KEYS[1])
~~~

Trong ví dụ này:

- Trả `-1` là tín hiệu **không giảm** vì key không có hoặc đã đạt 0.
- Nếu key có value số hợp lệ và lớn hơn 0, script mới thực hiện `DECR`.
- Script đảm bảo kiểm tra và giảm không bị một lệnh khác chen vào giữa trên Redis server.
- Đây chỉ là mô hình **counter có phạm vi số nhỏ và không âm**. Khi dùng làm tồn kho đặt hàng thật, còn phải tính đến idempotency, thanh toán, hủy đơn, database là nguồn chính và đồng bộ sau lỗi.

**Lưu ý độ chính xác Lua:** Redis Lua truyền thống sử dụng số dạng double cho nhiều biểu thức `tonumber(...)`. Với counter rất lớn gần giới hạn signed 64-bit, không dùng phép so sánh Lua dạng double như một cơ chế bảo vệ chính xác tuyệt đối; cần thiết kế giới hạn nghiệp vụ nhỏ, kiểm tra giới hạn hoặc dùng một primitive hỗ trợ so sánh nguyên 64-bit chính xác phù hợp.

## 12. Bộ đếm có giới hạn tối đa: không thể chỉ GET rồi INCR

Ví dụ mỗi người dùng chỉ có tối đa 3 lần thử trong một cửa sổ. Cách dễ sai:

~~~java
long current = readCounter(key);
if (current < 3) {
    increment(key);
}
~~~

Hai request có thể cùng đọc 2, cả hai thấy nhỏ hơn 3 rồi tăng, kết quả thành 4.

Với hạn mức nhỏ, có thể kiểm tra và tăng bằng Lua:

~~~lua
local currentRaw = redis.call('GET', KEYS[1])
local current = 0

if currentRaw then
    current = tonumber(currentRaw)
    if not current then
        return redis.error_reply('counter must be numeric')
    end
end

local maximum = tonumber(ARGV[1])
if not maximum or maximum < 1 then
    return redis.error_reply('invalid maximum')
end

if current >= maximum then
    return -1
end

return redis.call('INCR', KEYS[1])
~~~

Với `ARGV[1] = "3"`, script trả 1, 2, 3 cho các lần tăng thành công và trả -1 cho lần bị từ chối. Khi cần giới hạn **và TTL** của cửa sổ, phải mở rộng script để đặt thời gian hết hạn theo quy tắc nghiệp vụ.

### 12.1. Counter đơn giản không phải thuật toán rate limiting hoàn chỉnh

Một hạn mức theo key và TTL có thể thực hiện chính sách **fixed-window**, nhưng có các vấn đề:

- Request dồn ở ranh giới hai cửa sổ có thể vượt tốc độ kỳ vọng trong một khoảng ngắn.
- Phải định nghĩa cửa sổ tính theo lịch (theo phút/giờ) hay từ lần request đầu.
- Cần xác định key dựa trên user/token/IP/tenant và điều kiện truy cập đáng tin.
- Có thể cần chống trùng request và bảo vệ nhiều application instance.
- Redis gián đoạn: phải chọn fail-open hay fail-closed theo tính năng và rủi ro.

Sliding-window log, sliding-window counter, token bucket hoặc leaky bucket có yêu cầu khác nhau. Redis counter là nền tảng xây dựng chúng, không tự biến một `INCR` thành giải pháp rate limit có mọi thuộc tính mong muốn.

## 13. Số dư và tồn kho: phân biệt thao tác nguyên tử với giao dịch nghiệp vụ

Một ứng dụng có thể dùng Redis đếm số lượng sản phẩm còn khả dụng, số vé còn giữ hoặc số job đang chạy. Nhưng tính nguyên tử của `DECR` không đảm bảo mọi quy tắc lớn hơn:

~~~text
1. Người dùng đặt hàng
2. Redis DECR tồn kho
3. Database INSERT order
4. Hệ thống gọi thanh toán
~~~

Nếu bước 3 hoặc 4 thất bại, Redis đã giảm tồn kho nhưng đơn hàng chưa được ghi/hoàn thành. Nếu client không nhận phản hồi ở bước 2, retry có thể giảm thêm. Cần một thiết kế nghiệp vụ gồm bù trừ, state machine, idempotency, transaction ở nguồn chính hoặc cơ chế đồng bộ/đối soát.

Trong nhiều hệ thống, **database là nguồn xác thực tồn kho**, Redis hỗ trợ truy cập nhanh hoặc giữ trạng thái có TTL. Chọn nguồn chính theo yêu cầu consistency, không chỉ theo tốc độ.

### 13.1. Không dùng bộ đếm làm quyết định duy nhất cho những trường hợp cần kiểm toán

Bộ đếm sự kiện phục vụ dashboard có thể chấp nhận lệch nhỏ tùy sản phẩm; số dư tiền hoặc số vé bán cần quy tắc chặt chẽ hơn. Redis `INCR` giúp tránh lost update tại một key, nhưng không tự cung cấp chứng từ giao dịch, lịch sử thay đổi, đối soát hoặc exactly-once.

## 14. Khi request timeout: một lần tăng có thể đã xảy ra

Giả sử ứng dụng gọi:

~~~java
redis.opsForValue().increment("shop:article:42:views");
~~~

Redis thực hiện thành công, nhưng đường mạng bị lỗi trước khi Java nhận response. Ứng dụng có thể nhận timeout và không biết lệnh **đã được thực thi hay chưa**.

Nếu client tự retry:

~~~text
Lệnh đầu: Redis INCR 100 -> 101, response bị mất
Retry:   Redis INCR 101 -> 102, response nhận thành công

Một request nghiệp vụ nhưng counter tăng hai lần.
~~~

**Atomicity không đồng nghĩa idempotency**:

- Atomic: mỗi lần `INCR` được thực hiện trọn vẹn tại Redis.
- Idempotent: xử lý lại cùng một yêu cầu không làm thay đổi kết quả nghiệp vụ lần thứ hai.

Để đếm chính xác các sự kiện cần chống trùng, phải có **event/request ID** và cơ chế xác nhận ID chỉ được xử lý một lần, có thể qua lệnh/script Redis phù hợp hoặc nguồn dữ liệu bền vững. Một lệnh `SET NX` ghi dấu đã xử lý và `INCR` thực hiện tách riêng cũng có thể có khoảng hở nếu Redis/process lỗi giữa hai thao tác; khi cần bảo đảm trong Redis, nên kết hợp chúng nguyên tử. Việc bảo đảm qua cả Redis và database cần thiết kế sâu hơn.

Đối với lượt xem trang vốn chỉ là chỉ số gần đúng, sản phẩm có thể chấp nhận số đếm có sai lệch nhỏ. Đối với thanh toán, hạn mức pháp lý hoặc sự kiện phải kiểm toán, không được tùy tiện chấp nhận đặc tính này.

## 15. Reset và đọc bộ đếm: tránh hai lệnh không nguyên tử

Nếu muốn lấy giá trị hiện tại rồi reset về 0, cách dễ sai:

~~~java
String current = redis.opsForValue().get(key);
redis.opsForValue().set(key, "0");
~~~

Giữa `GET` và `SET`, một request khác có thể `INCR`; số lần tăng đó bị mất khi set 0.

Redis cung cấp thao tác `GETSET`, được Spring Data Redis expose qua:

~~~java
String previous = redis.opsForValue().getAndSet(key, "0");
~~~

`getAndSet(...)` trả **giá trị trước khi thay đổi** và ghi giá trị mới như một thao tác nguyên tử. Với key chưa tồn tại, giá trị cũ thường là `null`. Tuy nhiên, một thao tác ghi `SET`/`GETSET` có thể ảnh hưởng TTL của key; khi reset bộ đếm có TTL, phải quyết định rõ cách giữ hoặc thiết lập lại hạn.

Một cách khác là đọc và xóa trong một thao tác:

~~~java
String previous = redis.opsForValue().getAndDelete(key);
~~~

Với các phiên bản Redis và Spring Data Redis hỗ trợ `GETDEL`, lệnh này lấy giá trị cũ và xóa key nguyên tử. Lần `INCR` kế tiếp trên key đã xóa sẽ bắt đầu từ 1. Nên cân nhắc mô hình bucket theo thời gian hoặc log sự kiện nếu số liệu tổng hợp không được phép mất trong lúc reset.

### 15.1. Counter rolling window bằng key theo khoảng thời gian

Một hướng thường đơn giản hơn reset một key:

~~~text
shop:article:42:views:2026-11-12
shop:article:42:views:2026-11-13
shop:article:42:views:2026-11-14
~~~

Mỗi ngày có key riêng và đặt TTL đủ dài để tổng hợp. Không cần reset một key chung đúng thời điểm chuyển ngày. Cần thống nhất timezone của cửa sổ (ví dụ UTC hoặc timezone nghiệp vụ) và xử lý sự kiện đến trễ.

## 16. Khi nào dùng INCRBYFLOAT, HINCRBY hoặc INCR trong Spring?

| Bài toán | Redis data structure | Lệnh | Spring Data Redis |
| --- | --- | --- | --- |
| Đếm request/lượt xem nguyên | String chứa số nguyên | `INCR` | `StringRedisTemplate.opsForValue().increment(key)` |
| Tăng số lượng theo lô | String chứa số nguyên | `INCRBY` | `opsForValue().increment(key, long)` |
| Giảm số lượng | String chứa số nguyên | `DECR`/`DECRBY` | `opsForValue().decrement(...)` |
| Tăng một giá trị thập phân | String chứa số thực | `INCRBYFLOAT` | `opsForValue().increment(key, double)` |
| Tăng field trong Hash | Hash chứa field số nguyên | `HINCRBY` | `opsForHash().increment(key, hashKey, long)` |
| Tăng field số thực trong Hash | Hash chứa field số thực | `HINCRBYFLOAT` | `opsForHash().increment(key, hashKey, double)` |
| Đếm có điều kiện không âm/tối đa | String/Hash | Lua script hoặc transaction phù hợp | `RedisTemplate.execute(RedisScript, ...)` |

Lưu ý overload `increment(key, long)` và `increment(key, double)` có ý nghĩa khác nhau. Ví dụ:

~~~java
redis.opsForValue().increment("demo:counter", 2L);   // INCRBY 2
redis.opsForValue().increment("demo:score", 2.0d);    // INCRBYFLOAT 2.0
~~~

Dù delta `2.0d` nhìn như số nguyên, overload được chọn theo **kiểu Java**, không phải giá trị hiển thị. Tránh vô tình chuyển counter nguyên sang kiểu float.

## 17. Kiểm thử các tình huống quan trọng

Unit test có thể xác nhận service tạo key đúng và gọi phương thức template mong muốn. Nhưng những hành vi như atomically increment, Redis TTL và lỗi WRONGTYPE cần **integration test với Redis thật** (Redis local/Testcontainers).

### 17.1. Những kịch bản tối thiểu

1. **Key chưa có:** `INCR` lần đầu trả 1.
2. **Tăng nhiều lần:** gọi 1.000 lượt, kết quả tăng đúng theo số thao tác thực thi thành công.
3. **Giảm từ 0:** `DECR` cho -1; đối chiếu với quy tắc nghiệp vụ có cần chặn số âm không.
4. **Tăng theo delta:** `INCRBY 5` từ 10 cho 15, `DECRBY 3` cho 12.
5. **Value sai định dạng:** key chứa `"12.5"` hoặc JSON khiến `INCR` báo lỗi.
6. **Key sai Redis type:** Redis Hash chứa key cùng tên khiến `INCR` trả WRONGTYPE.
7. **Overflow:** tăng từ `Long.MAX_VALUE` báo lỗi.
8. **TTL:** `INCR` giữ TTL hiện tại; script tăng/đặt TTL không reset TTL ở lần sau.
9. **Nhiều thread:** nhiều request cùng `INCR` một key cho kết quả cuối tương ứng tổng số lệnh thành công.
10. **Timeout/retry:** mô tả hoặc mô phỏng việc không biết lệnh đã thực thi và áp dụng chính sách retry theo yêu cầu nghiệp vụ.

### 17.2. Ví dụ JUnit integration test

Đây là ví dụ ý tưởng với một Redis thật đã được cấu hình cho profile test; trong dự án cần bảo đảm namespace test độc lập và có dependency Spring Boot Test:

~~~java
@SpringBootTest
class CounterServiceIntegrationTest {

    @Autowired
    CounterService counterService;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void incrementsMissingKeyFromZero() {
        String key = "test:counter:missing";
        redis.delete(key);

        assertEquals(1L, counterService.increment(key));
        assertEquals(2L, counterService.increment(key));
        assertEquals("2", redis.opsForValue().get(key));
    }

    @Test
    void preservesExpirationWhenIncrementing() {
        String key = "test:counter:ttl";
        redis.opsForValue().set(key, "0", Duration.ofMinutes(1));

        counterService.increment(key);

        Long ttl = redis.getExpire(key, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0);
    }
}
~~~

Bổ sung các import JUnit 5 (`@Test`, `assertEquals`, `assertNotNull`, `assertTrue`), Spring Test (`@SpringBootTest`, `@Autowired`), `Duration`, `TimeUnit` và các class ứng dụng tương ứng. Test thứ hai chỉ xác nhận TTL còn dương ngay sau thao tác, tránh kiểm tra chính xác từng giây vì thời gian thực thi có dao động. Với suite thật, dùng key ngẫu nhiên/test database hoặc container riêng, dọn key test có kiểm soát.

**Không kiểm thử bằng cách giả định mọi kết quả tăng trong pipeline trả Long ngay lập tức**; API có thể hoãn kết quả đến khi pipeline được thực thi. Chọn bài kiểm thử đúng ngữ cảnh.

## 18. Quan sát bộ đếm bằng Redis CLI

Khi điều tra value bất thường:

~~~redis
TYPE shop:article:42:views
GET shop:article:42:views
TTL shop:article:42:views
PTTL shop:article:42:views
SCAN 0 MATCH shop:article:*:views COUNT 100
~~~

Thứ tự hợp lý:

1. Xác nhận ứng dụng và CLI cùng trỏ tới **host/port/Redis logical database**.
2. Dùng `TYPE` để kiểm tra String hay Hash.
3. Với String, dùng `GET` để nhìn định dạng số đang lưu.
4. Dùng `TTL` để biết key hết hạn, không có TTL hay không tồn tại.
5. Nếu key “biến mất”, kiểm tra namespace, serializer key, TTL, eviction, failover và các writer khác.
6. Nếu số đếm lệch, kiểm tra retry, request trùng, race condition trong logic điều kiện và việc có nhiều writer.

`SCAN` là thao tác duyệt dần bằng cursor: muốn quét hết cần lặp với cursor Redis trả về cho đến khi cursor trở lại 0. Tránh `KEYS *` trên hệ thống lớn và không sử dụng `FLUSHDB`/`FLUSHALL` để xử lý lỗi trên Redis đang có dữ liệu thật.

### 18.1. Theo dõi lỗi vận hành

Có thể quan sát số lượng request đã xử lý, độ trễ Redis, lỗi timeout, memory và số client. Tuy nhiên, **giá trị tăng của Redis không chứng minh một sự kiện nghiệp vụ đã hoàn tất**. Ví dụ HTTP response lỗi sau khi `INCR` thành công vẫn làm counter tăng; cần quyết định lúc nào sự kiện được coi là “đã xảy ra”.

Redis server có thể trả lỗi do memory pressure, kết nối, permission ACL, read-only replica hoặc sai định dạng. Service không nên âm thầm nuốt lỗi rồi trả một số giả là thành công.

## 19. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ERR value is not an integer or out of range` | Value chứa JSON, decimal, text không hợp lệ hoặc số vượt 64 bit | Kiểm tra `GET`, serializer và writer; xử lý schema |
| `WRONGTYPE` | Key đang là Hash/List/Set… | Kiểm tra `TYPE`; chọn `HINCRBY` nếu đúng là Hash field |
| Key không tìm thấy nhưng code đã ghi | Khác database, host, prefix hoặc key serializer | So sánh endpoint/DB và bytes của key; kiểm tra TTL |
| Redis trả số âm bất ngờ | `DECR` trên key thiếu hoặc nghiệp vụ không chặn số âm | Thêm kiểm tra–giảm nguyên tử, không chỉ `GET` rồi `DECR` |
| Counter bị mất cập nhật | Dùng `GET`/cộng Java/`SET` trong concurrency | Dùng `INCR`/`INCRBY` |
| Counter vượt hạn mức | Check và tăng bằng hai lệnh khác nhau | Dùng Lua/transaction với điều kiện nguyên tử |
| Key tồn tại mãi dù mong TTL | Chạy `INCR` rồi lỗi trước `EXPIRE`, hoặc key cũ không TTL | Dùng script nguyên tử; kiểm tra chính sách TTL |
| TTL liên tục quay về đầy đủ | Gọi `expire(...)` sau mỗi lần tăng | Phân biệt fixed TTL với sliding timeout |
| TTL biến mất sau reset | Ghi lại key bằng `SET`/`GETSET` | Xem lại quy tắc reset và cách giữ expiration |
| Lỗi serialize hoặc value nhị phân | Template dùng serializer không phù hợp | Ưu tiên `StringRedisTemplate` hoặc String-compatible serializer |
| Double-count sau timeout | Retry `INCR` không idempotent | Dùng request ID/dedup phù hợp hoặc chấp nhận tính gần đúng |
| Lệch số sau restart/failover | Persistence/replication/eviction không đáp ứng yêu cầu | Thiết kế durability, backup, reconciliation |
| Counter tăng nhưng business operation thất bại | Không có transaction thống nhất với nguồn chính | Bổ sung bù trừ/idempotency/đối soát |
| `INCR` thất bại sau khi ghi `INCRBYFLOAT` | Value đã thành chuỗi số thập phân | Tách key và API cho hai loại số |

## 20. Bài thực hành tổng hợp

**Bài toán:** xây dựng một service Spring Boot quản lý số lượt xem bài viết và số lần thử xác thực trong một cửa sổ 5 phút.

### 20.1. Bộ đếm lượt xem

Yêu cầu:

- Mỗi lần gọi `recordView(articleId)` tăng giá trị 1 bằng một lệnh nguyên tử.
- Key theo mẫu `shop:article:{id}:views`.
- Đọc current count được, key chưa tồn tại coi là 0 ở tầng nghiệp vụ.
- Không tự dùng `GET` rồi `SET` để tăng.
- Có thể giải thích mức sai lệch chấp nhận được khi request bị gửi trùng hoặc Redis gặp sự cố.

### 20.2. Bộ đếm lần thử xác thực

Yêu cầu:

- Key theo mẫu `shop:auth:attempts:{userId}`, không chứa mật khẩu/token.
- Lần tăng đầu đặt TTL 5 phút, các lần sau **không kéo dài TTL** nếu chọn fixed lifetime.
- Giới hạn số lần thử, ví dụ tối đa 5; bước kiểm tra giới hạn và tăng cần nguyên tử.
- Khi key hết hạn, lần thử mới bắt đầu từ 1.
- Có chính sách rõ ràng khi Redis không khả dụng; không tự giả định fail-open luôn an toàn.

Có thể bắt đầu bằng script tăng/TTL ở phần 10 rồi mở rộng thêm kiểm tra hạn mức từ phần 12 trong **cùng một script**. Việc dùng hai script tách rời để “tăng trước, kiểm tra hạn mức sau” vẫn có thể cho phép vượt giới hạn hoặc phải hoàn tác.

### 20.3. Những quan sát cần ghi lại

| Kịch bản | Kiểm tra ở service | Kiểm tra Redis |
| --- | --- | --- |
| Lượt xem lần đầu | Trả 1 | `GET` có `"1"` |
| Hai lượt xem tiếp theo | Trả 2, rồi 3 | Key vẫn là String |
| Counter có TTL | Trả giá trị mới | `TTL` dương và giảm dần |
| Hạn mức đạt ngưỡng | Request vượt ngưỡng bị từ chối | Counter không vượt quá max |
| Value bị ghi thành JSON | Service nhận lỗi phù hợp | `GET` cho thấy JSON, `INCR` lỗi |
| Key bị ghi thành Hash | Service nhận lỗi phù hợp | `TYPE` trả `hash` |
| Nhiều request cùng tăng | Tổng thao tác thành công được phản ánh | Kết quả không có lost update do đọc–sửa–ghi |
| Redis timeout | Có chính sách lỗi cụ thể | Cân nhắc khả năng lệnh đã được thực hiện |

Không ghi sẵn các con số benchmark như thể đã được đo. Mục tiêu là giải thích và kiểm tra hành vi của counter bằng code, Redis CLI và dữ liệu test thực tế.

## 21. Những câu hỏi tự ôn

1. Tại sao `TYPE counterKey` trả `string` dù ứng dụng Java coi value là `Long`?
2. Nếu `INCR` được gọi trên key chưa tồn tại, kết quả là bao nhiêu?
3. Nếu `DECR` được gọi trên key chưa tồn tại, điều gì xảy ra?
4. Vì sao Redis có thể từ chối `INCR` trên value `"12.0"`?
5. `INCRBY`, `DECRBY` và `INCRBYFLOAT` khác nhau ở loại số và kiểu trả về thế nào?
6. Redis Hash field muốn tăng nên dùng lệnh nào?
7. Hai request cùng `GET`/cộng 1/`SET` có thể mất cập nhật ra sao?
8. Một `INCR` nguyên tử có bảo vệ được điều kiện “không giảm dưới 0” nếu điều kiện được kiểm tra bằng `GET` riêng không?
9. Vì sao `StringRedisTemplate` thường là lựa chọn tốt cho counter String?
10. Sử dụng `RedisTemplate<String, Long>` có bảo đảm Redis value được lưu thành ASCII số nguyên không?
11. Giá trị lớn nhất có thể tăng qua `INCR` là bao nhiêu, và overflow được xử lý thế nào?
12. `TTL` trả -1 và -2 có nghĩa khác nhau ra sao?
13. `INCR` có làm mất TTL của một key đang hết hạn không?
14. Vì sao `INCR` rồi `EXPIRE` là hai thao tác chưa đủ nếu cần bảo đảm TTL được đặt nguyên tử?
15. Sự khác nhau giữa fixed lifetime và sliding idle timeout của bộ đếm là gì?
16. Vì sao retry `INCR` sau timeout có nguy cơ tăng gấp đôi?
17. Nếu bộ đếm dùng cho tồn kho, ngoài `DECR` nguyên tử còn cần đảm bảo những gì?
18. Vì sao dùng `double`/`INCRBYFLOAT` cho tiền có thể không phù hợp?
19. Khi đọc và reset counter, vì sao `getAndSet(...)` đáng tin hơn `GET` rồi `SET` riêng?
20. Làm sao phân biệt lỗi sai Redis type, sai value format, sai key serializer và key đã hết TTL?

## 22. Tài liệu tham khảo

- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): tăng số nguyên, xử lý key chưa tồn tại và các giới hạn.
- [Redis — DECR](https://redis.io/docs/latest/commands/decr/), [INCRBY](https://redis.io/docs/latest/commands/incrby/), [DECRBY](https://redis.io/docs/latest/commands/decrby/): các phép cộng/trừ theo số nguyên.
- [Redis — INCRBYFLOAT](https://redis.io/docs/latest/commands/incrbyfloat/): thao tác tăng giá trị số thập phân.
- [Redis — HINCRBY](https://redis.io/docs/latest/commands/hincrby/): tăng field số nguyên trong Redis Hash.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/), [TTL](https://redis.io/docs/latest/commands/ttl/): đặt và kiểm tra thời gian hết hạn key.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): thực thi Lua script phía Redis.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): tài liệu chính thức về RedisTemplate, StringRedisTemplate, serialization, scripting và transaction.
- [Spring Data Redis — ValueOperations API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ValueOperations.html): các overload `increment(...)`, `decrement(...)`, `getAndSet(...)` và `getAndDelete(...)`.

**Điểm cốt lõi:** Một bộ đếm Redis đúng nghĩa cần thống nhất **Redis String chứa số nguyên**, dùng **`INCR`/`DECR`/`INCRBY`/`DECRBY`** để tránh lost update, và thiết kế riêng các quy tắc phức tạp như TTL, hạn mức, không âm hay chống trùng request. `StringRedisTemplate` cung cấp API ngắn gọn để thao tác; tính đúng đắn cuối cùng vẫn phụ thuộc vào kiểu dữ liệu, vòng đời key và yêu cầu nghiệp vụ mà ứng dụng đặt ra.
