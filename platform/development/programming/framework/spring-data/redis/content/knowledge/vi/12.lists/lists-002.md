# Đọc khoảng phần tử và giới hạn kích thước danh sách trong Spring Data Redis

Redis List là cấu trúc dữ liệu lưu một **dãy phần tử có thứ tự**, trong đó ứng dụng có thể thêm và lấy phần tử ở hai đầu. Với Spring Data Redis, bạn thường thao tác Redis List qua `ListOperations<K, V>`, chẳng hạn `StringRedisTemplate.opsForList()`. Khi danh sách có nhiều phần tử, hai thao tác đặc biệt quan trọng là **đọc một đoạn bằng `LRANGE`** và **chỉ giữ phần cần thiết bằng `LTRIM`**.

Ví dụ, ứng dụng quản lý lịch sử 100 thông báo gần nhất của một người dùng. Mỗi lần có thông báo mới, hệ thống thêm thông báo vào Redis List. API chỉ đọc 10 thông báo gần đây và không muốn Redis giữ vô hạn các thông báo cũ. Bài toán tưởng đơn giản này đòi hỏi hiểu rõ **đầu trái/đầu phải**, **chỉ số bắt đầu–kết thúc**, **chỉ số âm**, **chi phí đọc**, **cách giới hạn kích thước**, và **tính nguyên tử khi có nhiều request ghi đồng thời**.

Bài này giải thích đầy đủ các thao tác trên trong ngữ cảnh **Spring Data Redis / Danh sách**, kèm ví dụ Redis CLI và Java, cách phân trang, giới hạn số phần tử, xử lý TTL, tình huống cạnh tranh và hướng lựa chọn cấu trúc dữ liệu khi danh sách tăng lớn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích thứ tự phần tử trong Redis List khi dùng `LPUSH` và `RPUSH`.
2. Đọc một khoảng phần tử bằng `LRANGE key start stop` và Spring Data Redis `opsForList().range(key, start, end)`.
3. Hiểu rằng **cả start và stop đều được tính vào kết quả**, biết cách dùng index âm như `-1` và `-N`.
4. Dùng `LLEN` / `opsForList().size(key)` để xem số lượng phần tử và xác định giới hạn đọc.
5. Dùng `LTRIM` / `opsForList().trim(key, start, end)` để **giữ lại một khoảng**, loại bỏ phần tử nằm ngoài khoảng đó.
6. Thiết kế danh sách chỉ giữ **N phần tử mới nhất** theo hai chiều ghi khác nhau: `LPUSH + LTRIM 0 N-1` hoặc `RPUSH + LTRIM -N -1`.
7. Hiểu tại sao hai lời gọi thêm và trim riêng lẻ có thể tạo trạng thái trung gian; dùng Redis Lua script khi cần cập nhật nguyên tử.
8. Nhận diện vấn đề của phân trang bằng offset khi danh sách đang thay đổi, tránh đọc toàn bộ danh sách lớn và kiểm soát cả số phần tử lẫn dung lượng.

**Điều kiện đầu vào:** biết Java/Spring Boot căn bản, Dependency Injection, thao tác cơ bản với `StringRedisTemplate` và key/value Redis. Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data Redis 3.x và Redis server thông thường; các lệnh `LRANGE`, `LLEN`, `LTRIM` là các lệnh Redis nền tảng.

## 2. Redis List: thứ tự chính là nền tảng

Một Redis List có thứ tự từ **trái sang phải**. Phần tử bên trái ở index 0; phần tử tiếp theo ở index 1; phần tử cuối cùng ở index `-1`. Redis cho phép nhiều phần tử có giá trị trùng nhau: List khác với Set.

Hình dung một danh sách năm phần tử:

~~~text
Redis key: demo:list:letters

    LEFT / HEAD                         RIGHT / TAIL
      |                                        |
      v                                        v
    +-----+-----+-----+-----+-----+
    |  A  |  B  |  C  |  D  |  E  |
    +-----+-----+-----+-----+-----+
       0     1     2     3     4     index dương
      -5    -4    -3    -2    -1     index âm
~~~

### 2.1. Hai cách thêm vào List

**`LPUSH`** thêm phần tử vào đầu **trái**:

~~~redis
DEL demo:list:letters
LPUSH demo:list:letters A
LPUSH demo:list:letters B
LPUSH demo:list:letters C
LRANGE demo:list:letters 0 -1
~~~

Kết quả theo thứ tự trái → phải là:

~~~text
C, B, A
~~~

**`RPUSH`** thêm phần tử vào đầu **phải**:

~~~redis
DEL demo:list:letters
RPUSH demo:list:letters A
RPUSH demo:list:letters B
RPUSH demo:list:letters C
LRANGE demo:list:letters 0 -1
~~~

Kết quả:

~~~text
A, B, C
~~~

**Hệ quả với danh sách theo thời gian:**

| Cách thêm | Phần tử mới nhất nằm ở đâu? | Cách đọc N mới nhất | Cách giữ N mới nhất |
| --- | --- | --- | --- |
| `LPUSH` | Đầu trái, index 0 | `LRANGE key 0 N-1` | `LTRIM key 0 N-1` |
| `RPUSH` | Đầu phải, index -1 | `LRANGE key -N -1` | `LTRIM key -N -1` |

Hai cách đều hợp lệ. Quan trọng nhất là **toàn bộ những chỗ ghi, đọc và trim phải thống nhất một quy ước**. Nếu service ghi bằng `RPUSH` nhưng lại trim bằng `LTRIM 0 N-1`, nó sẽ giữ các phần tử **cũ nhất** thay vì mới nhất.

### 2.2. Danh sách khác String hoặc Set

- **Redis String** phù hợp một giá trị, JSON hoặc bộ đếm; không có khả năng cắt khoảng theo số phần tử danh sách.
- **Redis List** giữ thứ tự phần tử và cho phép trùng, thích hợp danh sách tuần tự, lịch sử gần đây, queue đơn giản.
- **Redis Set** không giữ thứ tự đọc theo vị trí List và loại bỏ phần tử trùng.
- **Redis Sorted Set** sắp xếp bằng score, có thể phù hợp timeline có timestamp/ID và truy vấn theo mốc.
- **Redis Stream** có ID sự kiện, consumer group và cơ chế đọc sự kiện, thích hợp nhu cầu event processing khác danh sách đơn giản.

Không nên dùng Redis List chỉ vì dữ liệu “có nhiều phần tử”. Hãy chọn khi **thứ tự theo đầu trái/đầu phải** và các thao tác List thực sự phù hợp.

## 3. Đọc khoảng phần tử với LRANGE

Lệnh Redis:

~~~redis
LRANGE key start stop
~~~

`start` và `stop` là **chỉ số theo vị trí trong List**, không phải số lượng phần tử. **Khoảng đọc bao gồm cả hai đầu**, vì vậy:

~~~redis
LRANGE demo:list:letters 0 0
~~~

đọc **một** phần tử đầu tiên, còn:

~~~redis
LRANGE demo:list:letters 0 9
~~~

đọc tối đa **10** phần tử: các index 0 đến 9.

### 3.1. Tạo danh sách mẫu để thử

Đặt danh sách về trạng thái xác định:

~~~redis
DEL demo:list:letters
RPUSH demo:list:letters A B C D E
LRANGE demo:list:letters 0 -1
LLEN demo:list:letters
~~~

Danh sách hiện có `[A, B, C, D, E]` và độ dài là 5.

| Lệnh | Kết quả trả về | Vì sao? |
| --- | --- | --- |
| `LRANGE key 0 0` | `[A]` | Chỉ index 0 |
| `LRANGE key 0 2` | `[A, B, C]` | Index 0, 1, 2 |
| `LRANGE key 1 3` | `[B, C, D]` | Index 1, 2, 3 |
| `LRANGE key 2 4` | `[C, D, E]` | Ba phần tử cuối theo chỉ số dương |
| `LRANGE key -3 -1` | `[C, D, E]` | Ba phần tử cuối theo chỉ số âm |
| `LRANGE key -2 -2` | `[D]` | Index -2 là D |
| `LRANGE key 0 -1` | `[A, B, C, D, E]` | Toàn bộ danh sách |
| `LRANGE key 3 1` | `[]` | Start đứng sau stop |
| `LRANGE key 10 12` | `[]` | Start ngoài độ dài List |
| `LRANGE key -100 1` | `[A, B]` | Start âm vượt trái được kẹp về đầu |
| `LRANGE key 2 100` | `[C, D, E]` | Stop vượt phải được kẹp về cuối |

Trong bảng, `key` viết tắt cho `demo:list:letters`. Redis không coi index vượt quá biên là lỗi trong các trường hợp trên; nó điều chỉnh phạm vi hoặc trả về danh sách rỗng. Điều này hữu ích khi trang cuối chỉ còn ít phần tử.

### 3.2. Chỉ số âm

Chỉ số âm được đếm từ phía **phải**:

~~~text
List:             A    B    C    D    E
Index dương:      0    1    2    3    4
Index âm:        -5   -4   -3   -2   -1
~~~

Theo đó:

~~~redis
LRANGE demo:list:letters -1 -1
~~~

trả phần tử cuối `E`, còn:

~~~redis
LRANGE demo:list:letters -3 -1
~~~

trả `C, D, E` theo **thứ tự lưu từ trái sang phải**. Dùng chỉ số âm không tự đảo thứ tự kết quả.

Muốn lấy **N mới nhất ở đầu phải**, dùng `-N` đến `-1`. Nếu List có ít hơn N phần tử, Redis trả tất cả phần tử đang có.

### 3.3. Cẩn thận với biểu thức N - 1

Nếu muốn đọc 20 phần tử đầu tiên:

~~~redis
LRANGE demo:list:items 0 19
~~~

Không viết `LRANGE key 0 20` vì câu lệnh đó có thể trả **21 phần tử**. Tương tự, phân trang với `pageSize=10` bắt đầu từ 0 có các khoảng:

~~~text
Trang 0: [0, 9]
Trang 1: [10, 19]
Trang 2: [20, 29]
...
~~~

Đây là lý do ở Java thường tính:

~~~java
long start = (long) pageIndex * pageSize;
long end = start + pageSize - 1;
~~~

Cần đảm bảo `pageIndex >= 0` và `pageSize > 0`; ở hệ thống thật nên giới hạn `pageSize` để một request không thể yêu cầu đọc hàng triệu phần tử.

### 3.4. LRANGE không xóa phần tử

`LRANGE` là lệnh **đọc**. Nó giữ nguyên List, không giống `LPOP` hoặc `RPOP` là lệnh lấy và loại bỏ phần tử. Ví dụ:

~~~redis
LRANGE demo:list:letters 0 1
LLEN demo:list:letters
~~~

Sau khi đọc 2 phần tử, độ dài List vẫn là 5.

Đặc tính này thích hợp cho API hiển thị lịch sử hoặc danh sách gần đây. Nếu đang xây một queue mà consumer phải **nhận và lấy phần tử khỏi queue**, hãy dùng các thao tác pop hoặc cơ chế queue phù hợp; `LRANGE` không xác nhận xử lý và không lấy phần tử khỏi hàng đợi.

## 4. Đọc khoảng bằng Spring Data Redis

Trong Spring Data Redis, giao diện thường dùng:

~~~java
ListOperations<String, String> operations =
        stringRedisTemplate.opsForList();

List<String> values = operations.range(
        "demo:list:letters", 1, 3
);
~~~

Kết quả ví dụ là `[B, C, D]`.

Các API chính:

| Redis | Spring Data Redis | Ý nghĩa |
| --- | --- | --- |
| `LRANGE key start stop` | `opsForList().range(key, start, end)` | Đọc khoảng, không xóa |
| `LLEN key` | `opsForList().size(key)` | Đọc số phần tử |
| `LTRIM key start stop` | `opsForList().trim(key, start, end)` | Giữ khoảng, xóa phần ngoài |
| `LINDEX key index` | `opsForList().index(key, index)` | Đọc một phần tử theo index |
| `LPUSH key value` | `opsForList().leftPush(key, value)` | Thêm ở đầu trái |
| `RPUSH key value` | `opsForList().rightPush(key, value)` | Thêm ở đầu phải |
| `LPOP key` | `opsForList().leftPop(key)` | Lấy và xóa phần tử trái |
| `RPOP key` | `opsForList().rightPop(key)` | Lấy và xóa phần tử phải |

`range(...)` và `size(...)` có thể trả về `null` khi được gọi trong một số ngữ cảnh pipeline hoặc transaction vì kết quả được gom lại và trả sau. Khi gọi đồng bộ thông thường, `range(...)` cho key không tồn tại thường trả danh sách rỗng, còn `size(...)` trả số 0. Đừng mặc định rằng `null` đồng nghĩa một List trống trong mọi ngữ cảnh.

### 4.1. Cấu hình ứng dụng tối thiểu

Trong một ứng dụng Spring Boot có BOM quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Chạy Redis cục bộ cho thực hành:

~~~bash
docker run --name redis-list-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-list-lab redis-cli PING
~~~

Lệnh `PING` thành công trả `PONG`. Nếu cổng 6379 đã bị chiếm, chọn cổng host khác và chỉnh cấu hình ứng dụng.

Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Ví dụ này giả định ứng dụng chạy trên máy host, Redis Docker bind cổng host vào loopback. Nếu ứng dụng cũng chạy trong Docker Compose, cần dùng tên service Redis trong cùng mạng. Ở môi trường thật, phải cấu hình ACL/xác thực, TLS khi cần, giới hạn mạng và secret phù hợp; không đưa Redis không xác thực ra Internet.

### 4.2. Vì sao StringRedisTemplate phù hợp với bài thực hành?

`StringRedisTemplate` sử dụng serializer chuỗi cho key và value. Với List lưu thông báo như text ngắn hoặc một chuỗi JSON do ứng dụng tự tạo, dữ liệu có thể đọc bằng `redis-cli LRANGE`.

Khi dùng `RedisTemplate<String, EventDto>` để lưu object, cần **cấu hình serializer tường minh** cho key và value. Nếu dùng serializer mặc định nhị phân, giá trị trong CLI có thể khó đọc và không thể cùng một ứng dụng khác giải mã nếu không biết format. Generic type `<String, EventDto>` không tự đặt value JSON serializer.

Trong các đoạn code dưới đây, mỗi phần tử List là một `String`. Đây là một hợp đồng dữ liệu đơn giản, giúp tập trung vào vấn đề index, range và trim.

## 5. Service Java: đọc phần tử và phân trang

Giả sử List lưu các thông báo theo thứ tự **cũ nhất bên trái, mới nhất bên phải**, vì service thêm bằng `RPUSH`.

Tạo `RecentMessageService.java`:

~~~java
package com.example.redis;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentMessageService {

    private final StringRedisTemplate redis;

    public RecentMessageService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void append(String userId, String message) {
        validateUserId(userId);
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("Message is required");
        }

        redis.opsForList().rightPush(key(userId), message);
    }

    public List<String> firstPage(String userId, int size) {
        validatePageSize(size);
        List<String> values = redis.opsForList()
                .range(key(userId), 0, size - 1L);
        return requireDirectResult(values);
    }

    public List<String> lastMessages(String userId, int limit) {
        validatePageSize(limit);
        List<String> values = redis.opsForList()
                .range(key(userId), -((long) limit), -1);
        return requireDirectResult(values);
    }

    public List<String> lastMessagesNewestFirst(String userId, int limit) {
        List<String> result = new ArrayList<>(lastMessages(userId, limit));
        Collections.reverse(result);
        return result;
    }

    public List<String> page(String userId, int pageIndex, int pageSize) {
        if (pageIndex < 0) {
            throw new IllegalArgumentException("Page index must be >= 0");
        }
        validatePageSize(pageSize);

        long start = Math.multiplyExact((long) pageIndex, pageSize);
        long end = Math.addExact(start, pageSize - 1L);

        List<String> values = redis.opsForList()
                .range(key(userId), start, end);
        return requireDirectResult(values);
    }

    public long size(String userId) {
        Long value = redis.opsForList().size(key(userId));
        if (value == null) {
            throw new IllegalStateException("Redis length is unavailable");
        }
        return value;
    }

    private List<String> requireDirectResult(List<String> values) {
        if (values == null) {
            throw new IllegalStateException(
                    "LRANGE did not return a direct result");
        }
        return List.copyOf(values);
    }

    private void validatePageSize(int size) {
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Page size must be between 1 and 100");
        }
    }

    private void validateUserId(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("User ID is required");
        }
    }

    private String key(String userId) {
        validateUserId(userId);
        return "shop:user:" + userId + ":recent-messages";
    }
}
~~~

Các phương thức trên minh họa những kiểu đọc khác nhau:

- `firstPage(userId, 10)` lấy 10 phần tử đầu trái (trong ví dụ RPUSH là những thông báo cũ nhất).
- `lastMessages(userId, 10)` lấy tối đa 10 phần tử **cuối phải**, theo thứ tự **cũ → mới**.
- `lastMessagesNewestFirst(...)` lấy cùng nhóm nhưng đảo trong Java để hiển thị **mới → cũ**. Danh sách gốc trong Redis không đổi.
- `page(userId, 0, 10)` đọc index 0..9; `page(userId, 1, 10)` đọc 10..19.
- `size(userId)` ánh xạ sang `LLEN`; không cần tải tất cả phần tử chỉ để đếm.

Giới hạn 100 phần tử trong ví dụ nhằm tránh request không kiểm soát trả về quá nhiều dữ liệu. Ứng dụng thật nên đặt giới hạn theo độ lớn phần tử, tải mạng và UX; không nhất thiết là 100.

`List.copyOf(values)` tạo một bản danh sách Java bất biến để bên ngoài không vô tình sửa collection trả về. Nó không thêm tính nhất quán liên request ở Redis. Nếu service chạy trong pipeline/transaction, logic nhận `null` cần được thiết kế theo API đó thay vì cố dùng kết quả trực tiếp như trong ví dụ đồng bộ.

### 5.1. Dùng ví dụ trong controller

Một REST controller tối giản:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users/{userId}/messages")
public class RecentMessageController {

    private final RecentMessageService messages;

    public RecentMessageController(RecentMessageService messages) {
        this.messages = messages;
    }

    @GetMapping("/latest")
    public List<String> latest(
            @PathVariable String userId,
            @RequestParam(defaultValue = "10") int limit) {
        return messages.lastMessagesNewestFirst(userId, limit);
    }

    @GetMapping
    public List<String> page(
            @PathVariable String userId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return messages.page(userId, page, size);
    }
}
~~~

Ví dụ API:

~~~http
GET /users/u42/messages/latest?limit=10
GET /users/u42/messages?page=0&size=10
~~~

Controller chỉ minh họa đọc List. Trong hệ thống thực, cần xác thực và kiểm tra quyền truy cập: **không được tin rằng người gọi có quyền xem thông báo chỉ vì họ biết `userId` trong URL**. Nếu chứa thông tin nhạy cảm, cũng cần cân nhắc nội dung List, TTL và log.

### 5.2. Nếu ghi bằng LPUSH thì logic đọc sẽ đổi

Nếu thêm mới bằng:

~~~java
redis.opsForList().leftPush(key, message);
~~~

thì đầu trái là phần tử **mới nhất**. Lúc này:

~~~java
List<String> newest = redis.opsForList().range(key, 0, 9);
~~~

đã trả tối đa 10 phần tử theo thứ tự mới → cũ. Không cần dùng `-10,-1` rồi đảo kết quả, vì đó là 10 phần tử ở đầu phải (những phần tử cũ hơn).

## 6. LLEN: đọc kích thước mà không tải dữ liệu

Redis:

~~~redis
LLEN demo:list:letters
~~~

Spring Data Redis:

~~~java
Long length = stringRedisTemplate.opsForList()
        .size("demo:list:letters");
~~~

Nếu key là List gồm 5 phần tử, kết quả là 5. Nếu key **chưa tồn tại**, Redis `LLEN` trả 0. Nếu key tồn tại nhưng thuộc kiểu Redis khác (ví dụ String), lệnh trả `WRONGTYPE`.

**Không nên dùng `LRANGE key 0 -1` rồi lấy `list.size()` chỉ để đếm.** `LLEN` có độ phức tạp **O(1)**, trong khi đọc toàn bộ List tốn thời gian và dữ liệu truyền qua mạng tỷ lệ với số phần tử.

### 6.1. LLEN và LRANGE không tự tạo một snapshot chung

Giả sử:

~~~text
T1: Request A gọi LLEN -> 100
T2: Request B RPUSH thêm 1 -> 101
T3: Request A gọi LRANGE 90 99 -> đọc một đoạn theo trạng thái mới
~~~

Hai lệnh của A thực thi ở **hai thời điểm khác nhau**. Nếu có writer đồng thời, count và range có thể phản ánh hai trạng thái khác nhau. Điều này thường chấp nhận được với UI lịch sử gần đây; nếu cần count và các phần tử nhất quán trong cùng một snapshot, cần chọn cơ chế transaction/script hoặc thiết kế dữ liệu tương ứng.

Trong API pagination, độ dài được trả về như `totalCount` nên được coi là **độ dài quan sát tại thời điểm đọc**, trừ khi đã thiết kế snapshot chính xác.

### 6.2. Redis List trống và key không tồn tại

Khi List bị pop hoặc trim hết phần tử, Redis thường xóa luôn key rỗng. Do đó `LLEN key = 0` không giúp bạn phân biệt “chưa bao giờ tạo List” với “List đã bị xóa hết”. Nếu nghiệp vụ cần ghi nhận trạng thái đã tạo hoặc tiến trình xử lý, phải lưu metadata ở key riêng hoặc nguồn dữ liệu khác.

## 7. LTRIM: giữ một khoảng, xóa phần còn lại

Tên `LTRIM` đôi khi khiến người học nghĩ lệnh “xóa từ phía trái”. Thực tế, lệnh:

~~~redis
LTRIM key start stop
~~~

**giữ lại các phần tử từ index start đến stop, bao gồm hai đầu**; tất cả phần tử **bên ngoài khoảng** bị loại bỏ. Các index được diễn giải trên trạng thái List tại thời điểm lệnh thực thi.

Ví dụ:

~~~redis
DEL demo:list:letters
RPUSH demo:list:letters A B C D E
LTRIM demo:list:letters 1 3
LRANGE demo:list:letters 0 -1
~~~

Kết quả còn lại:

~~~text
B, C, D
~~~

Không phải `LTRIM key 1 3` sẽ xóa phần tử index 1..3; nó làm điều ngược lại: **giữ** các phần tử đó.

### 7.1. Một số trường hợp LTRIM

Giả sử mỗi hàng bắt đầu từ List `[A, B, C, D, E]`:

| Lệnh | Danh sách còn lại | Diễn giải |
| --- | --- | --- |
| `LTRIM key 0 2` | `[A, B, C]` | Giữ 3 phần tử đầu trái |
| `LTRIM key -3 -1` | `[C, D, E]` | Giữ 3 phần tử cuối phải |
| `LTRIM key 1 3` | `[B, C, D]` | Giữ khoảng ở giữa |
| `LTRIM key 0 -1` | `[A, B, C, D, E]` | Giữ toàn bộ |
| `LTRIM key 3 1` | List bị xóa hết | Khoảng rỗng |
| `LTRIM key 20 30` | List bị xóa hết | Start vượt kích thước |
| `LTRIM key -100 1` | `[A, B]` | Giữ từ đầu đến index 1 |

Khi không còn phần tử nào sau trim, Redis không giữ một List rỗng như key độc lập; key thường bị xóa.

### 7.2. LTRIM là thao tác làm mất dữ liệu

`LRANGE` chỉ đọc; `LTRIM` **thực sự loại bỏ phần tử**. Nếu List chứa dữ liệu nghiệp vụ quan trọng chưa có nơi lưu khác, một lần trim nhầm chiều có thể gây mất dữ liệu.

Trước khi đặt `LTRIM` vào luồng ghi, cần trả lời: “Những phần tử bị loại bỏ có còn ở database/log khác không?”, “Chúng đã được tiêu thụ/xử lý chưa?” và “Danh sách này có chủ đích chỉ là cache/window gần đây hay không?”.

Đối với danh sách thông báo tạm có thể tạo lại, trim thường phù hợp. Đối với danh sách nhiệm vụ cần xử lý một lần và không được mất, Redis List đơn giản với trim có thể không đáp ứng yêu cầu; cần thiết kế queue, retry, acknowledgement hoặc Redis Streams.

## 8. Giới hạn kích thước danh sách: giữ N phần tử mới nhất

Một ứng dụng ghi liên tục vào Redis List có thể khiến số phần tử tăng không giới hạn nếu không có chính sách vòng đời. Cách phổ biến là **mỗi lần thêm một phần tử thì chỉ giữ N phần tử mới nhất**.

### 8.1. Dùng RPUSH: giữ N phần tử cuối phải

Giả sử List biểu diễn lịch sử từ cũ → mới. Thêm bên phải:

~~~redis
DEL demo:recent:events
RPUSH demo:recent:events event-1
RPUSH demo:recent:events event-2
RPUSH demo:recent:events event-3
RPUSH demo:recent:events event-4
RPUSH demo:recent:events event-5
LRANGE demo:recent:events 0 -1
~~~

Trước trim:

~~~text
[event-1, event-2, event-3, event-4, event-5]
~~~

Chỉ giữ 3 phần tử mới nhất:

~~~redis
LTRIM demo:recent:events -3 -1
LRANGE demo:recent:events 0 -1
LLEN demo:recent:events
~~~

Sau trim:

~~~text
[event-3, event-4, event-5]
LLEN = 3
~~~

Tổng quát:

~~~text
RPUSH key newItem
LTRIM key -N -1
~~~

Nếu N lớn hơn số phần tử đang có, `LTRIM -N -1` vẫn giữ toàn bộ List. Không cần gọi `LLEN` trước để biết có nên trim hay không.

### 8.2. Dùng LPUSH: giữ N phần tử đầu trái

Trong một số UI, thứ tự mới nhất → cũ nhất thuận tiện hơn:

~~~redis
DEL demo:recent:events
LPUSH demo:recent:events event-1
LPUSH demo:recent:events event-2
LPUSH demo:recent:events event-3
LPUSH demo:recent:events event-4
LPUSH demo:recent:events event-5
LRANGE demo:recent:events 0 -1
~~~

List trước trim:

~~~text
[event-5, event-4, event-3, event-2, event-1]
~~~

Chỉ giữ 3 phần tử mới nhất:

~~~redis
LTRIM demo:recent:events 0 2
LRANGE demo:recent:events 0 -1
~~~

Kết quả:

~~~text
[event-5, event-4, event-3]
~~~

Tổng quát:

~~~text
LPUSH key newItem
LTRIM key 0 N-1
~~~

### 8.3. Tại sao không dùng LLEN rồi tính khoảng?

Cách nhiều người nghĩ tới:

~~~text
RPUSH key item
length = LLEN key
if length > N:
    LTRIM key length-N length-1
~~~

Với mục tiêu giữ cuối phải, `LTRIM key -N -1` đã diễn đạt trực tiếp yêu cầu. Phương án dựa vào `LLEN` tốn thêm round trip và có thể lấy chiều dài ở một thời điểm khác nếu writer đồng thời thay đổi List.

**N phải lớn hơn 0.** Với N=0, biểu thức `-N` trở thành 0; `LTRIM key 0 -1` lại giữ toàn bộ List, trái với ý định “giữ 0 phần tử”. Nếu nghiệp vụ muốn không lưu phần tử nào, hãy xử lý nhánh riêng bằng cách không thêm hoặc xóa key có kiểm soát.

## 9. Java: thêm rồi giới hạn kích thước

Sau khi đã thống nhất ghi bằng `RPUSH`, một service đơn giản có thể viết:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BoundedRecentListService {

    private static final int MAX_ALLOWED_ITEMS = 500;
    private final StringRedisTemplate redis;

    public BoundedRecentListService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void append(String feedId, String event, int maxItems) {
        validateFeedId(feedId);
        validateMaxItems(maxItems);
        if (event == null || event.isBlank()) {
            throw new IllegalArgumentException("Event is required");
        }

        String key = key(feedId);
        redis.opsForList().rightPush(key, event);
        redis.opsForList().trim(key, -((long) maxItems), -1);
    }

    public List<String> readLatest(String feedId, int limit) {
        validateFeedId(feedId);
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Limit must be between 1 and 100");
        }

        List<String> result = redis.opsForList()
                .range(key(feedId), -((long) limit), -1);
        if (result == null) {
            throw new IllegalStateException("Redis range unavailable");
        }
        return List.copyOf(result);
    }

    public long size(String feedId) {
        Long result = redis.opsForList().size(key(feedId));
        if (result == null) {
            throw new IllegalStateException("Redis size unavailable");
        }
        return result;
    }

    private void validateFeedId(String feedId) {
        if (feedId == null || feedId.isBlank()) {
            throw new IllegalArgumentException("Feed ID is required");
        }
    }

    private void validateMaxItems(int maxItems) {
        if (maxItems < 1 || maxItems > MAX_ALLOWED_ITEMS) {
            throw new IllegalArgumentException(
                    "maxItems must be between 1 and " + MAX_ALLOWED_ITEMS);
        }
    }

    private String key(String feedId) {
        validateFeedId(feedId);
        return "shop:feed:" + feedId + ":recent";
    }
}
~~~

Ví dụ gọi:

~~~java
boundedRecentListService.append("feed-42", "event-A", 3);
boundedRecentListService.append("feed-42", "event-B", 3);
boundedRecentListService.append("feed-42", "event-C", 3);
boundedRecentListService.append("feed-42", "event-D", 3);

List<String> latest =
        boundedRecentListService.readLatest("feed-42", 3);
long count = boundedRecentListService.size("feed-42");
~~~

Theo thứ tự RPUSH, kết quả kỳ vọng:

~~~text
latest = [event-B, event-C, event-D]
count  = 3
~~~

Ở code trên, `maxItems` nên là giới hạn do **ứng dụng** quản lý, không nên để client bên ngoài tùy ý tăng lên hàng triệu. Nếu mọi feed phải giữ đúng 100 phần tử, có thể dùng một hằng cấu hình cố định thay vì nhận tham số trong mỗi lời gọi.

**Giới hạn quan trọng của ví dụ:** `rightPush(...)` và `trim(...)` là **hai lệnh Redis tách biệt**. Với nhiều writer đồng thời hoặc yêu cầu “List không bao giờ vượt quá N phần tử, kể cả tạm thời”, nên dùng một thao tác nguyên tử như Lua script hoặc transaction phù hợp, được trình bày tiếp theo.

## 10. Vì sao RPUSH + LTRIM riêng lẻ chưa hoàn toàn nguyên tử?

Mỗi lệnh Redis như `RPUSH` hay `LTRIM` được thực thi nguyên tử ở cấp một lệnh. Nhưng **chuỗi hai lệnh** không tự động nguyên tử.

Giả sử List có giới hạn 3:

~~~text
Ban đầu: [A, B, C] (3 phần tử)

Writer 1: RPUSH D
             List: [A, B, C, D]             (4 phần tử)

Reader:   LRANGE key 0 -1
             nhìn thấy 4 phần tử

Writer 1: LTRIM key -3 -1
             List: [B, C, D]                (3 phần tử)
~~~

Trong khoảng giữa `RPUSH` và `LTRIM`, người đọc có thể thấy kích thước vượt giới hạn. Nếu ứng dụng bị crash hoặc mất kết nối sau push nhưng trước trim, List có thể giữ trạng thái vượt giới hạn cho tới lần trim tiếp theo.

Khi nhiều writer cùng append, các lệnh có thể xen kẽ:

~~~text
Writer A: RPUSH D
Writer B: RPUSH E
Writer A: LTRIM -3 -1
Writer B: LTRIM -3 -1
~~~

Sau khi các thao tác trim thành công, List sẽ về kích thước được giới hạn; nhưng **trạng thái trung gian** không được bảo vệ. Nếu yêu cầu nghiệp vụ chấp nhận độ dài nhỉnh hơn N trong thời gian rất ngắn và có cơ chế tự sửa, phương án hai lệnh có thể đủ đơn giản. Nếu cần ràng buộc chặt ở mọi thời điểm, hãy gộp chúng thành thao tác nguyên tử phía Redis.

### 10.1. Pipelining không đồng nghĩa transaction

Một cách thường được đề xuất là gửi `RPUSH` và `LTRIM` trong pipeline để giảm round trip. Pipelining chỉ giúp **gom lệnh khi giao tiếp mạng**; nó **không tự đảm bảo hai lệnh không bị xen vào bởi các lệnh từ client khác**.

`MULTI/EXEC` có thể bảo đảm các lệnh được chạy liên tiếp trong một transaction Redis, còn Lua script thực thi logic kết hợp trên server trong một lần gọi. Với logic ngắn “push rồi trim”, Lua thường là cách diễn đạt trực tiếp và dễ tái sử dụng.

## 11. Lua script: append và giới hạn kích thước trong một thao tác

Redis hỗ trợ Lua script thực thi tuần tự phía server. Có thể kết hợp `RPUSH`, `LTRIM` và `LLEN` vào **một script nguyên tử**.

### 11.1. Lua script

~~~lua
-- KEYS[1]: Redis List key
-- ARGV[1]: value mới
-- ARGV[2]: maxItems nguyên dương

local maxItems = tonumber(ARGV[2])
if not maxItems or maxItems < 1 or maxItems % 1 ~= 0 then
    return redis.error_reply("maxItems must be a positive integer")
end

redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], -maxItems, -1)
return redis.call('LLEN', KEYS[1])
~~~

Trên Redis, các lệnh bên trong script được thực thi như một đơn vị không bị request khác chen vào giữa. Reader chỉ thấy List **trước hoặc sau** script; không thấy trạng thái `RPUSH` xong nhưng chưa `LTRIM`.

Script trả về kích thước List sau khi trim, hữu ích cho quan sát. Code Java cần kiểm tra `maxItems` hợp lệ trước khi truyền vào và giới hạn value/payload phù hợp.

**Lưu ý:** việc chạy script nguyên tử không đồng nghĩa mọi lỗi đều “rollback” như database transaction. Nếu script sửa dữ liệu rồi phát sinh runtime error ở bước sau, Redis không tự hoàn tác các lệnh đã thực thi trước lỗi. Vì vậy script nên ngắn, được xây dựng với input hợp lệ, và tránh logic có thể lỗi sau bước ghi.

### 11.2. Cấu hình RedisScript bean

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration(proxyBeanMethods = false)
public class BoundedListScriptConfig {

    @Bean
    RedisScript<Long> appendAndTrimScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setResultType(Long.class);
        script.setScriptText("""
            local n = tonumber(ARGV[2])
            if not n or n < 1 or n % 1 ~= 0 then
                return redis.error_reply("maxItems must be positive")
            end
            redis.call('RPUSH', KEYS[1], ARGV[1])
            redis.call('LTRIM', KEYS[1], -n, -1)
            return redis.call('LLEN', KEYS[1])
            """);
        return script;
    }
}
~~~

`DefaultRedisScript<Long>` chỉ định loại kết quả Java là `Long`. Kết quả của lệnh `LLEN` trong script là số nguyên Redis nên phù hợp loại này. Khi dùng `StringRedisTemplate`, key và tham số truyền cho script được serialize dưới dạng String.

### 11.3. Gọi script bằng StringRedisTemplate

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class AtomicBoundedListService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> appendAndTrimScript;

    public AtomicBoundedListService(
            StringRedisTemplate redis,
            RedisScript<Long> appendAndTrimScript) {
        this.redis = redis;
        this.appendAndTrimScript = appendAndTrimScript;
    }

    public long append(String feedId, String value, int maxItems) {
        if (feedId == null || feedId.isBlank()) {
            throw new IllegalArgumentException("Feed ID is required");
        }
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Value is required");
        }
        if (maxItems < 1 || maxItems > 500) {
            throw new IllegalArgumentException("maxItems out of range");
        }

        String key = "shop:feed:" + feedId + ":recent";
        Long size = redis.execute(
                appendAndTrimScript,
                List.of(key),
                value,
                Integer.toString(maxItems)
        );

        if (size == null) {
            throw new IllegalStateException("Redis returned no size");
        }
        return size;
    }
}
~~~

Ưu điểm của đoạn code:

1. Chỉ một lần gọi `execute(...)` từ Java.
2. Redis làm `RPUSH` và `LTRIM` trong cùng script, tránh reader thấy List tạm thời vượt N.
3. Service không cần gọi `LLEN` trước rồi tự tính khoảng trim.
4. Kết quả trả về là độ dài List sau thao tác.

Đổi sang **LPUSH** nếu muốn mới nhất ở đầu trái:

~~~lua
redis.call('LPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], 0, n - 1)
return redis.call('LLEN', KEYS[1])
~~~

Đừng dùng bản LPUSH mà vẫn giữ `LTRIM -n -1`: như vậy có thể vô tình bỏ phần tử mới thêm và giữ phần tử cũ hơn.

### 11.4. Nếu dùng MULTI/EXEC thay vì Lua

Redis transaction cho phép xếp nhiều lệnh giữa `MULTI` và `EXEC` để server thực thi liên tiếp khi `EXEC` chạy. Nó cũng có thể phục vụ yêu cầu `RPUSH + LTRIM` không bị thao tác khác chen giữa. Tuy nhiên, cần hiểu cách Spring Data Redis quản lý connection và transaction; không nên gọi `multi()`/`exec()` trên các kết nối tùy tiện trong service mà chưa kiểm soát vòng đời.

Nếu chỉ cần một thao tác ngắn có đầu vào và kết quả rõ ràng như “append rồi giữ N”, Lua script thường dễ mô tả và bảo trì hơn. Với quy tắc phức tạp hơn, cần so sánh transaction, Lua và mô hình dữ liệu trước khi triển khai.

## 12. Giới hạn số phần tử khác với giới hạn bộ nhớ

`LTRIM` giới hạn **số lượng element**, nhưng không giới hạn kích thước byte của từng element:

~~~text
List A: 100 phần tử × 20 bytes    ≈ 2 KB payload
List B: 100 phần tử × 200 KB     ≈ 20 MB payload
~~~

Đây là ví dụ ước lượng payload, chưa tính overhead cấu trúc dữ liệu, key và memory allocator Redis. Cả hai đều có `LLEN = 100` nhưng dùng bộ nhớ rất khác nhau.

### 12.1. Vì sao nên giới hạn cả payload?

Một client có thể đưa vào List một JSON rất lớn, khiến:

- Redis dùng nhiều RAM dù số phần tử không vượt N.
- `LRANGE` đọc một trang nhỏ vẫn truyền nhiều MB qua mạng.
- Deserialization tốn CPU và tạo áp lực GC ở Java.
- Response HTTP lớn hơn yêu cầu của giao diện.
- Lệnh trim phải giải phóng nhiều dữ liệu, tạo chi phí xử lý bộ nhớ.

Thiết kế thực tế nên quy định **kích thước tối đa một phần tử**, **số phần tử tối đa của List**, **độ dài request page**, và **TTL/retention** nếu dữ liệu không cần giữ mãi. Có thể chỉ lưu ID/tóm tắt trong List, còn nội dung đầy đủ trong một kho khác khi phù hợp.

### 12.2. Tăng trưởng theo số user hoặc số key

Giới hạn 100 phần tử trên mỗi List không có nghĩa hệ thống chỉ giữ 100 phần tử. Nếu mỗi người dùng có một List:

~~~text
1.000.000 người dùng × 100 phần tử/List
   = tối đa 100.000.000 phần tử
~~~

Đây là phép nhân số phần tử tiềm năng, không phải dự đoán chính xác RAM. Cần tính số lượng key, độ dài value trung bình, TTL, memory policy và quy mô người dùng, tránh chỉ nhìn `LLEN` của một key mẫu rồi kết luận bộ nhớ an toàn.

## 13. Chi phí thời gian của LRANGE, LLEN và LTRIM

Redis có tối ưu nội bộ cho List, nhưng mỗi lệnh vẫn có chi phí khác nhau.

| Lệnh | Độ phức tạp thường nêu | Ý nghĩa |
| --- | --- | --- |
| `LLEN` | **O(1)** | Lấy độ dài mà không đọc toàn bộ element |
| `LRANGE` | **O(S + N)** | S liên quan đến khoảng cần đi tới vị trí bắt đầu, N là số phần tử được trả về |
| `LTRIM` | **O(N)** với N là số phần tử bị loại bỏ | Xóa nhiều phần tử có thể tốn chi phí lớn |
| `LINDEX` | **O(N)** tùy vị trí | Không nên đọc lặp từng phần tử ở sâu trong List nếu có thể dùng LRANGE |
| `LPUSH` / `RPUSH` | Thường **O(1)** cho một phần tử | Thêm ở đầu phù hợp cho luồng dữ liệu tuần tự |

Với List lớn, Redis có tối ưu truy cập từ đầu gần nhất; tuy nhiên, **offset sâu** và **khoảng đọc dài** vẫn có thể tốn tài nguyên. Một lần `LRANGE 0 -1` trên List hàng triệu phần tử có chi phí truyền dữ liệu và tạo object lớn ngay cả khi Redis phản hồi được.

### 13.1. Không dùng LRANGE để đọc toàn bộ List khổng lồ

Câu lệnh:

~~~redis
LRANGE shop:feed:global 0 -1
~~~

có thể tiện khi debug một List nhỏ. Nhưng ở production, nếu List dài, nó:

1. Buộc Redis tập hợp và trả số lượng lớn phần tử.
2. Tạo gói phản hồi lớn, tốn băng thông mạng.
3. Khiến Java client tạo nhiều String/object và có thể tăng GC.
4. Có thể làm chậm những request cùng dùng Redis.

Với API giao diện, giới hạn trang hoặc chỉ lấy các phần tử gần đầu List, ví dụ `LRANGE key 0 19` hoặc `LRANGE key -20 -1`. Nếu nhu cầu là truy vấn hàng trăm nghìn phần tử sâu trong List, cần đánh giá lại cấu trúc dữ liệu.

### 13.2. LTRIM thường rẻ khi mỗi lần chỉ loại một vài phần tử

Nếu List được duy trì ở giới hạn 100 và mỗi request thêm một phần tử rồi trim, thường chỉ có một phần tử cũ phải loại bỏ sau khi danh sách đã đầy. Nhưng nếu List vô tình tăng lên hàng triệu phần tử rồi chạy `LTRIM -100 -1`, Redis phải loại bỏ rất nhiều phần tử cùng lúc; thao tác có thể gây độ trễ đáng kể.

Vì vậy nên **áp dụng giới hạn ngay trên đường ghi**, thay vì chỉ chạy cron job trim định kỳ sau khi dữ liệu đã phình to. Với dữ liệu cũ rất lớn cần dọn, có thể thiết kế quy trình vận hành và đo tác động trước khi trim hàng loạt.

## 14. Phân trang offset khi danh sách đang thay đổi

`LRANGE` là một cách phân trang theo index:

~~~text
pageIndex = 0, pageSize = 10 -> LRANGE 0 9
pageIndex = 1, pageSize = 10 -> LRANGE 10 19
pageIndex = 2, pageSize = 10 -> LRANGE 20 29
~~~

Điều này hoạt động thuận tiện với List **gần như không đổi** hoặc một danh sách ngắn. Nhưng nếu List luôn nhận phần tử mới, offset có thể gây **trùng hoặc bỏ sót phần tử** giữa các request.

### 14.1. Ví dụ với LPUSH

Giả sử List lưu mới → cũ:

~~~text
Ban đầu: [F, E, D, C, B, A]
Client đọc page 0, size 3 -> [F, E, D]

Có message mới G được LPUSH:
List mới: [G, F, E, D, C, B, A]

Client đọc page 1, size 3 -> index 3..5 -> [D, C, B]
~~~

Phần tử D xuất hiện **hai lần** ở hai trang vì index bị đẩy sang phải khi thêm đầu trái. Nếu item bị trim/xóa giữa các lần đọc, client cũng có thể bỏ sót phần tử.

### 14.2. Nếu RPUSH rồi LTRIM thì sao?

Với RPUSH, phần tử mới thêm ở cuối; khi trim giữ N cuối, các phần tử ở đầu bị loại bỏ, làm offset của những phần tử còn lại dịch sang trái. Một client đang đọc page 1 theo offset có thể thấy tập dữ liệu thay đổi giữa các lần gọi.

Vì vậy, **offset pagination trên List không đảm bảo snapshot ổn định** khi có ghi/xóa đồng thời. Đây không phải lỗi của Spring Data Redis mà là đặc tính của việc dùng chỉ số vị trí cho dữ liệu biến động.

### 14.3. Những lựa chọn thay thế

- Nếu UI chỉ cần “10 sự kiện mới nhất”, một lệnh `LRANGE` với giới hạn nhỏ thường đủ.
- Nếu cần xem lịch sử theo trang trong một snapshot, cân nhắc cố định tập kết quả theo request/session hoặc dùng nguồn dữ liệu hỗ trợ snapshot.
- Nếu cần pagination theo thời gian/ID mà dữ liệu liên tục thay đổi, Redis Sorted Set với score/ID hoặc một database có keyset pagination có thể phù hợp hơn.
- Với sự kiện cần truy xuất theo ID, consumer group và retention policy, Redis Streams có thể là lựa chọn tốt hơn Redis List.
- Với dữ liệu phải lưu lâu và truy vấn phức tạp, database chuyên dụng thường là nguồn chính, Redis làm cache của trang gần đây.

Chọn công cụ dựa trên **tính ổn định của trang, khả năng bỏ sót/trùng chấp nhận được và yêu cầu lưu trữ**, không chỉ dựa vào sự tiện lợi của `LRANGE`.

## 15. TTL và chính sách vòng đời của List

`LTRIM` giới hạn số phần tử; `EXPIRE` giới hạn **thời gian tồn tại của key**. Hai cơ chế độc lập:

~~~redis
RPUSH demo:recent:events event-1 event-2
EXPIRE demo:recent:events 3600
TTL demo:recent:events
~~~

Key có thể hết hạn sau một giờ ngay cả khi List chỉ có hai phần tử. Ngược lại, nếu chỉ dùng `LTRIM -100 -1` mà không đặt TTL, Redis có thể giữ 100 phần tử của một người dùng không còn hoạt động trong thời gian dài.

### 15.1. Push/trim có giữ TTL không?

Với một List đang có thời hạn, các thao tác sửa nội dung như `LPUSH`, `RPUSH` và `LTRIM` thông thường **không tự xóa TTL** của key. Tuy nhiên, khi `LTRIM` loại bỏ hết element khiến key bị xóa, expiration của key đó cũng không còn.

Nếu List chưa tồn tại và một lệnh `RPUSH` tạo key mới, key mới **không tự có TTL**. Cần quyết định:

- **TTL từ lần tạo đầu:** đặt expiration khi key mới hình thành, không gia hạn ở mỗi append.
- **TTL từ lần hoạt động gần nhất:** gia hạn expiration sau mỗi append.
- **Không TTL nhưng giới hạn N:** giữ dữ liệu gần nhất vô thời hạn, phải quản lý key không hoạt động và tổng memory.

### 15.2. Tránh khoảng hở khi append và đặt TTL

Nếu cần chắc chắn khi tạo List mới thì sẽ đặt TTL, gọi riêng:

~~~java
redis.opsForList().rightPush(key, value);
redis.expire(key, Duration.ofHours(1));
~~~

có khoảng hở giữa hai lệnh. Nếu process chết sau push và trước expire, List có thể sống vô hạn. Nếu bạn gọi `expire(...)` mỗi lần, TTL lại được gia hạn liên tục, thay đổi chính sách retention.

Có thể thêm TTL vào script phần 11:

~~~lua
local maxItems = tonumber(ARGV[2])
local ttlSeconds = tonumber(ARGV[3])
if not maxItems or maxItems < 1 or maxItems % 1 ~= 0 then
    return redis.error_reply("invalid maxItems")
end
if not ttlSeconds or ttlSeconds < 1 or ttlSeconds % 1 ~= 0 then
    return redis.error_reply("invalid ttl")
end

redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], -maxItems, -1)

if redis.call('TTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], ttlSeconds)
end

return redis.call('LLEN', KEYS[1])
~~~

Ở đây `ARGV[3]` là TTL theo giây. Cấu hình này theo chính sách **key nào chưa có expiration thì được đặt TTL**. Nó cũng sẽ đặt TTL cho một key cũ đang tồn tại nhưng trước đó không có hạn, nên chỉ dùng cho namespace có hợp đồng mọi List đều phải hết hạn. Nếu cần xác định nghiêm ngặt “key mới được tạo trong chính script này”, logic có thể kiểm tra `EXISTS` **trước** `RPUSH`.

### 15.3. TTL không thay thế trim

TTL xóa cả key khi hết hạn; nó không đảm bảo số phần tử của List luôn nằm trong giới hạn trong lúc key còn sống. Ngược lại, LTRIM chỉ giới hạn độ dài, không tự dọn những key của người dùng không hoạt động. Khi cần cả hai ràng buộc, phải dùng kết hợp có chủ đích.

## 16. Redis List và lựa chọn serializer

Spring Data Redis truyền các phần tử vào Redis dưới dạng byte. Việc dùng:

~~~java
RedisTemplate<String, MessageDto> redisTemplate;
~~~

không tự đảm bảo JSON. Bạn cần chỉ định serializer phù hợp cho key và value.

### 16.1. Danh sách chuỗi

Với thông báo ngắn hoặc ID:

~~~java
StringRedisTemplate template = ...;
template.opsForList().rightPush("shop:recent:ids", "id-42");
template.opsForList().rightPush("shop:recent:ids", "id-43");
List<String> ids = template.opsForList()
        .range("shop:recent:ids", 0, -1);
~~~

CLI sẽ hiển thị phần tử dưới dạng chuỗi thông thường:

~~~redis
LRANGE shop:recent:ids 0 -1
~~~

### 16.2. Danh sách object JSON

Nếu List chứa DTO, nên dùng một `RedisTemplate<String, MessageDto>` có:

- `StringRedisSerializer` cho **key**.
- JSON serializer **typed** cho `MessageDto` (theo phiên bản Spring Data Redis đang chạy).
- Quy tắc schema và version cho phần tử.
- Giới hạn kích thước JSON để tránh mỗi `LRANGE` chuyển quá nhiều dữ liệu.

Với Spring Data Redis 3.x, typed JSON thường sử dụng `Jackson2JsonRedisSerializer<MessageDto>`; ở dòng Spring Data Redis 4.x, serializer Jackson 3 tương ứng là `JacksonJsonRedisSerializer<MessageDto>`. Không trộn code nhánh 3.x và 4.x khi import class. Redis List không quan tâm JSON hợp lệ hay không; client đọc phải biết định dạng của value.

### 16.3. Tránh dùng nhiều serializer cho cùng một List

Nếu Writer A ghi phần tử String, Writer B ghi object bằng JDK serializer và Reader C dùng JSON serializer, một lệnh `LRANGE` có thể trả về nhiều byte value thuộc các định dạng không tương thích. Deserializer có thể lỗi **toàn bộ thao tác đọc trang** chỉ vì một phần tử.

Mỗi List nên có **hợp đồng định dạng nhất quán**: key prefix, value type, serializer, version, và chính sách đổi schema. Khi cần nâng cấp định dạng, dùng namespace mới hoặc migration rõ ràng thay vì trộn lẫn các phần tử trong cùng một List.

## 17. Concurrency và tính nhất quán khi đọc

Một lệnh `LRANGE` đọc một khoảng theo trạng thái List khi Redis xử lý lệnh đó; một lệnh `LTRIM` sửa List như một thao tác riêng. Nhưng một chuỗi lệnh độc lập không tạo snapshot xuyên thời gian.

### 17.1. Một trang có thể thay đổi khi request tiếp theo đến

~~~text
Request A -> LRANGE 0 9           (trạng thái T1)
Writer B  -> LPUSH newItem        (trạng thái T2)
Request A -> LRANGE 10 19         (trạng thái T3)
~~~

Các trang có thể chồng lặp hoặc bỏ sót. Nếu yêu cầu chỉ hiển thị “gần nhất”, đây thường là đặc tính chấp nhận được; nếu hệ thống phải báo cáo chính xác theo một thời điểm, cần cơ chế khác.

### 17.2. Atomic script không bảo đảm dữ liệu không mất vì hạ tầng

Script `RPUSH + LTRIM` đảm bảo hai thao tác không bị client khác chen vào giữa **trong lúc script chạy trên Redis server**. Nhưng việc ghi thành công không tự đảm bảo dữ liệu đã được lưu bền vững ra đĩa hoặc được replica nhận trước khi server lỗi. Nếu dữ liệu quan trọng, cần thiết kế persistence, replication, acknowledgement, backup và đối soát phù hợp.

### 17.3. Tránh giữ dữ liệu phải xử lý trong List có trim

Nếu List là queue và worker chưa kịp nhận một task, `LTRIM` có thể xóa task đó chỉ để giữ kích thước. Với lịch sử UI có thể tái tạo, việc xóa phần tử cũ có thể được phép. Với job processing, cần thiết kế riêng cơ chế nhận việc, retry và bảo đảm không bỏ mất công việc.

## 18. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `LRANGE key 0 10` trả 11 phần tử | Stop là chỉ số bao gồm | Dùng `0 9` để đọc tối đa 10 phần tử |
| Đọc mới nhất nhưng thấy phần tử cũ | Dùng `RPUSH` rồi `LRANGE 0 N-1` | Đọc `-N -1` hoặc chuyển quy ước LPUSH |
| Trim xong chỉ còn item cũ | Dùng `RPUSH` nhưng trim đầu trái | Dùng `LTRIM -N -1` |
| Trim xong mất phần tử mới | Dùng `LPUSH` nhưng trim cuối phải | Dùng `LTRIM 0 N-1` |
| Danh sách bị xóa hết | Start > stop hoặc start quá xa | Kiểm tra cách tính và validation N |
| Giới hạn N=0 nhưng List vẫn giữ nguyên | `LTRIM key -0 -1` tương đương `LTRIM 0 -1` | Chặn `N <= 0` hoặc xử lý chính sách không lưu riêng |
| List đôi lúc vượt N | `RPUSH` và `LTRIM` là hai lệnh | Dùng Lua script/transaction khi cần bất biến tức thời |
| `LLEN` trả 0, không rõ key đã từng tồn tại chưa | Redis không giữ List rỗng | Dùng metadata riêng nếu phải phân biệt |
| API trả chậm với trang lớn | `LRANGE` trả quá nhiều element hoặc payload lớn | Giới hạn page size, value size và offset |
| Phân trang bị trùng item | Ghi/xóa làm index dịch chuyển | Dùng snapshot/cursor/Sorted Set nếu yêu cầu ổn định |
| Redis báo `WRONGTYPE` | Key đang là String/Hash/Set, không phải List | Kiểm tra `TYPE key` và namespace |
| Java deserialize lỗi | Writer/reader dùng serializer khác nhau | Thống nhất value format, migration |
| Key biến mất bất ngờ | TTL, eviction, xóa hết bằng LTRIM, xóa bởi service khác | Kiểm tra TTL, policy, logs và ownership key |
| Danh sách không hết hạn | Tạo key bằng RPUSH nhưng không EXPIRE | Thiết kế TTL ngay từ lúc tạo, có thể dùng script |
| Bộ nhớ tăng dù LLEN bị giới hạn | Quá nhiều key hoặc từng element rất lớn | Giới hạn payload, TTL, tổng số key và theo dõi memory |

### 18.1. Hướng kiểm tra bằng redis-cli

~~~redis
TYPE shop:feed:feed-42:recent
LLEN shop:feed:feed-42:recent
LRANGE shop:feed:feed-42:recent 0 9
LRANGE shop:feed:feed-42:recent -10 -1
TTL shop:feed:feed-42:recent
MEMORY USAGE shop:feed:feed-42:recent
SCAN 0 MATCH shop:feed:*:recent COUNT 100
~~~

`MEMORY USAGE` có thể hữu ích để ước lượng memory của một key khi command được Redis server hỗ trợ. `SCAN` trả cursor; muốn duyệt hết thì tiếp tục gọi với cursor trả về cho đến khi cursor 0.

Không sử dụng `KEYS *` trên keyspace production lớn và không dùng `FLUSHDB`/`FLUSHALL` để “sửa nhanh” khi chưa hiểu phạm vi dữ liệu bị xóa. Khi điều tra lỗi, chỉ thử `LTRIM` trên key thử nghiệm hoặc key đã được xác nhận có thể mất phần tử.

## 19. Bài thực hành: lịch sử 20 sự kiện gần nhất

**Bài toán:** xây dựng một API ghi sự kiện ngắn cho mỗi thiết bị và chỉ giữ tối đa 20 sự kiện gần nhất. Frontend có thể đọc 5 sự kiện mới nhất hoặc phân trang theo index trong List hiện tại.

### 19.1. Quy ước dữ liệu

~~~text
Key:      demo:device:<deviceId>:events
Value:    mỗi phần tử là một String chứa thông tin sự kiện
Thứ tự:   RPUSH -> cũ nhất ở trái, mới nhất ở phải
Giới hạn: 20 phần tử / thiết bị
Đọc gần nhất: LRANGE key -5 -1
Giới hạn:  RPUSH + LTRIM -20 -1 trong một Lua script
~~~

Nếu muốn hiển thị mới nhất đầu tiên, đảo phần tử trên response hoặc dùng quy ước LPUSH nhất quán ngay từ đầu. Không đổi chiều ghi trong khi List cũ vẫn tồn tại mà chưa migration dữ liệu.

### 19.2. Các bước thực hành

1. Chạy Redis local và xác nhận `PING` trả `PONG`.
2. Tạo Spring Boot app có `StringRedisTemplate` và kết nối Redis.
3. Tạo service với phương thức `appendEvent(deviceId, text)` gọi script `RPUSH + LTRIM -20 -1`.
4. Tạo phương thức `latest(deviceId, 5)` dùng `range(key, -5, -1)`.
5. Tạo phương thức `page(deviceId, pageIndex, pageSize)`; giới hạn `pageSize` tối đa 20.
6. Ghi 25 sự kiện đánh số từ `event-1` đến `event-25`.
7. Kiểm tra `LLEN` và `LRANGE key 0 -1`; chỉ nên còn `event-6` đến `event-25`.
8. Kiểm tra `LRANGE key -5 -1`; kỳ vọng `event-21` đến `event-25` theo thứ tự cũ → mới.
9. Thử hai writer đồng thời với cùng key; nếu dùng script, List không được để lộ trạng thái vượt 20 phần tử giữa push và trim.
10. Nếu muốn, đặt thêm TTL theo quy tắc định trước để key của thiết bị không còn hoạt động được dọn theo thời gian.

### 19.3. Quan sát kết quả trên Redis

Sau khi thực hiện 25 lần append:

~~~redis
LLEN demo:device:d42:events
LRANGE demo:device:d42:events 0 -1
LRANGE demo:device:d42:events -5 -1
LRANGE demo:device:d42:events 0 4
TTL demo:device:d42:events
~~~

Kết quả logic kỳ vọng khi không có writer khác hoặc expiration can thiệp:

| Lệnh | Kết quả |
| --- | --- |
| `LLEN` | 20 |
| `LRANGE 0 -1` | `event-6` đến `event-25` |
| `LRANGE -5 -1` | `event-21` đến `event-25` |
| `LRANGE 0 4` | `event-6` đến `event-10` |
| `TTL` | -1 nếu chưa thiết lập expiration, còn lại tính giây nếu đã đặt TTL |

Đây là **kết quả kỳ vọng của bài thực hành**, không phải kết quả một lượt chạy có sẵn. Khi điều tra sai khác, kiểm tra chiều thêm, chỉ số stop bao gồm, TTL, key và cách serializer ghi phần tử.

### 19.4. Bài tập mở rộng

**Bài tập A — Mới nhất bên trái:** đổi service sang `LPUSH` và `LTRIM 0 19`, rồi sửa API đọc 5 sự kiện mới nhất thành `LRANGE 0 4`. Giải thích vì sao không cần đảo thứ tự trả về.

**Bài tập B — Giới hạn kích thước byte:** nếu một sự kiện có thể dài 1 MB, đề xuất cách giới hạn payload hoặc chỉ lưu ID trong List rồi đọc chi tiết từ nguồn khác.

**Bài tập C — Phân trang khi có ghi mới:** yêu cầu frontend đọc trang 0 và trang 1 trong lúc thiết bị tiếp tục gửi sự kiện. Quan sát trùng/bỏ sót, rồi giải thích vì sao offset pagination không đảm bảo snapshot ổn định.

**Bài tập D — TTL:** thiết kế sao cho List hết hạn sau 24 giờ kể từ sự kiện đầu, hoặc 24 giờ kể từ sự kiện mới nhất. So sánh cách đặt TTL và tác động đến dữ liệu.

**Bài tập E — Dữ liệu không thể mất:** thay đổi yêu cầu: mọi sự kiện phải được xử lý đúng theo ID, có retry khi worker lỗi. Giải thích vì sao nên đánh giá Redis Streams hoặc message broker thay vì chỉ dùng Redis List có trim.

## 20. Những câu hỏi tự ôn

1. Khi dùng `LPUSH`, phần tử mới nằm ở index nào? Còn khi dùng `RPUSH`?
2. `LRANGE key 0 9` trả tối đa bao nhiêu phần tử? Vì sao?
3. `LRANGE key -1 -1` lấy phần tử nào?
4. Chỉ số âm trong Redis List tính từ đầu nào của danh sách?
5. Vì sao `LRANGE key -3 -1` không tự đảo thứ tự phần tử?
6. Điều gì xảy ra khi `start > stop` hoặc start vượt độ dài List?
7. `LRANGE` khác `LPOP`/`RPOP` ở hành vi làm thay đổi List như thế nào?
8. `LLEN` có lợi thế gì so với đọc toàn bộ List rồi đếm phần tử ở Java?
9. `opsForList().range(key, start, end)` có phải dùng `end` là vị trí không bao gồm không?
10. `LTRIM key 1 3` xóa các phần tử 1..3 hay giữ các phần tử đó?
11. Muốn giữ 100 phần tử mới nhất sau `RPUSH`, dùng khoảng nào của `LTRIM`?
12. Muốn giữ 100 phần tử mới nhất sau `LPUSH`, dùng khoảng nào?
13. Vì sao `LTRIM key -0 -1` không phải cách xóa toàn bộ List?
14. Nếu hai lệnh `RPUSH` và `LTRIM` chạy tách biệt, người đọc có thể thấy trạng thái gì?
15. Pipelining có biến hai lệnh push/trim thành một thao tác nguyên tử không?
16. Lua script giúp bảo đảm giới hạn kích thước List trong một thao tác như thế nào?
17. Nếu List luôn ở giới hạn 100 phần tử, tại sao Redis vẫn có thể dùng nhiều RAM?
18. Vì sao đọc page 1 sau khi một phần tử mới được `LPUSH` có thể bị trùng phần tử của page 0?
19. `TTL` và `LTRIM` kiểm soát hai khía cạnh khác nhau của vòng đời List ra sao?
20. Redis có giữ một key List rỗng sau khi `LTRIM` loại bỏ mọi phần tử không?
21. Trường hợp nào Sorted Set/Streams hoặc database phù hợp hơn List với phân trang offset?
22. Nếu code đang dùng `RedisTemplate<String, MyDto>`, điều gì quyết định định dạng bytes của từng phần tử List?

## 21. Tài liệu tham khảo

- [Redis — LRANGE](https://redis.io/docs/latest/commands/lrange/): chỉ số start/stop, chỉ số âm, giới hạn kết quả và độ phức tạp.
- [Redis — LTRIM](https://redis.io/docs/latest/commands/ltrim/): giữ khoảng phần tử và cách áp dụng bounded list.
- [Redis — LLEN](https://redis.io/docs/latest/commands/llen/): lấy số phần tử với độ phức tạp O(1).
- [Redis — LPUSH](https://redis.io/docs/latest/commands/lpush/) và [RPUSH](https://redis.io/docs/latest/commands/rpush/): thêm phần tử ở hai đầu List.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/) và [TTL](https://redis.io/docs/latest/commands/ttl/): quản lý thời gian sống của key.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): kết hợp các thao tác trong Lua script phía Redis.
- [Spring Data Redis Reference — Redis support](https://docs.spring.io/spring-data/redis/reference/redis.html): làm việc với Redis qua template và các cấu trúc dữ liệu.
- [Spring Data Redis — ListOperations JavaDoc](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ListOperations.html): API `range`, `trim`, `size`, `leftPush` và `rightPush`.

**Ghi nhớ:** `LRANGE` đọc **khoảng có cả start và stop**; `LLEN` lấy độ dài mà không tải phần tử; `LTRIM` **giữ khoảng được chỉ định và xóa phần còn lại**. Muốn giữ N phần tử mới nhất, hãy thống nhất chiều ghi: **`LPUSH + LTRIM 0 N-1`** hoặc **`RPUSH + LTRIM -N -1`**. Khi giới hạn là ràng buộc cần đúng tại mọi thời điểm, kết hợp push và trim bằng Lua script hoặc transaction phù hợp; đồng thời kiểm soát dung lượng mỗi phần tử, TTL và tính ổn định của phân trang khi List thay đổi liên tục.
