# Thêm và lấy phần tử ở hai đầu List trong Spring Data Redis

**Redis List** là cấu trúc dữ liệu lưu một dãy phần tử có thứ tự, cho phép thêm và lấy phần tử ở **đầu trái (head)** hoặc **đầu phải (tail)**. Trong Spring Data Redis, những thao tác này được cung cấp chủ yếu qua `ListOperations<K, V>` và các phương thức `leftPush`, `rightPush`, `leftPop`, `rightPop` của `RedisTemplate`/`StringRedisTemplate`.

Chỉ với bốn thao tác cơ bản, ứng dụng có thể xây dựng một hàng đợi FIFO, một ngăn xếp LIFO hoặc một deque (hàng đợi hai đầu). Tuy nhiên, khi Redis List được dùng cho các tác vụ có nhiều producer/consumer, cần hiểu rõ thứ tự phần tử, cách xử lý list trống, thao tác blocking, TTL, tính nguyên tử và giới hạn của mô hình xử lý công việc.

## 1. Redis List là gì?

Redis List là một dãy các giá trị string nhị phân theo thứ tự. Redis giữ **thứ tự giữa các phần tử**, chấp nhận **giá trị trùng nhau** và cho phép thêm/lấy ở hai đầu mà không cần di chuyển toàn bộ dãy theo cách của một mảng thông thường.

Ví dụ một list tên `shop:dev:jobs:email` chứa ba phần tử:

```text
Redis key: shop:dev:jobs:email

LEFT / HEAD                                RIGHT / TAIL
    |                                          |
    v                                          v
  +-------------+-------------+----------------+
  | send-mail-1 | send-mail-2 | send-mail-3    |
  +-------------+-------------+----------------+
      index 0       index 1       index 2
```

Các phần tử trong hình được trình bày từ trái sang phải theo thứ tự `LRANGE key 0 -1`.

Khác với Redis Set, List không tự loại bỏ phần tử trùng nhau. Khác với Sorted Set, Redis List không sắp xếp theo score. Nếu thêm cùng chuỗi `send-mail-1` hai lần, list có thể chứa hai phần tử bằng nhau ở hai vị trí khác nhau.

### Một Redis key có kiểu dữ liệu List

Redis key là `shop:dev:jobs:email`; còn `send-mail-1`, `send-mail-2` là **các phần tử bên trong List**. Không có Redis key riêng cho từng phần tử.

```redis
TYPE shop:dev:jobs:email
```

Nếu key đang chứa một Redis List, lệnh trả:

```text
list
```

Không thể dùng `GET shop:dev:jobs:email` để đọc list. `GET` dành cho Redis string; với List cần các lệnh như `LRANGE`, `LINDEX`, `LPOP` hoặc `RPOP`.

## 2. Bốn lệnh nền tảng: `LPUSH`, `RPUSH`, `LPOP`, `RPOP`

Redis đặt tên lệnh theo hướng thao tác:

| Lệnh Redis | Ý nghĩa | Spring Data Redis |
|---|---|---|
| `LPUSH key value` | Thêm phần tử vào **bên trái / head** | `opsForList().leftPush(key, value)` |
| `RPUSH key value` | Thêm phần tử vào **bên phải / tail** | `opsForList().rightPush(key, value)` |
| `LPOP key` | Lấy và **xóa** phần tử ở bên trái | `opsForList().leftPop(key)` |
| `RPOP key` | Lấy và **xóa** phần tử ở bên phải | `opsForList().rightPop(key)` |

Chữ **L** viết tắt cho *left*, chữ **R** viết tắt cho *right*, và **PUSH/POP** có cùng ý nghĩa với thao tác thêm/lấy trong stack hoặc deque.

Các thao tác trên một đầu của List có độ phức tạp trung bình **O(1) cho một phần tử**. Vì vậy, Redis List phù hợp với nhu cầu thường xuyên thêm/lấy phần tử tại hai đầu. Các thao tác duyệt một khoảng hoặc tìm phần tử giữa list có chi phí khác, tùy số phần tử cần xử lý.

### 2.1. `RPUSH`: thêm vào đuôi

Bắt đầu với key chưa tồn tại:

```redis
RPUSH demo:list:ends A
RPUSH demo:list:ends B
RPUSH demo:list:ends C
LRANGE demo:list:ends 0 -1
```

Kết quả:

```text
1) "A"
2) "B"
3) "C"
```

Diễn tiến:

```text
Ban đầu : []
RPUSH A : [A]
RPUSH B : [A, B]
RPUSH C : [A, B, C]
```

Redis `RPUSH` trả về **độ dài mới của List**. Khi key chưa tồn tại, Redis tạo List mới. Nếu key tồn tại nhưng thuộc Redis data type không tương thích, Redis báo `WRONGTYPE`.

### 2.2. `LPUSH`: thêm vào đầu

Tiếp tục từ `[A, B, C]`:

```redis
LPUSH demo:list:ends X
LRANGE demo:list:ends 0 -1
```

Kết quả:

```text
1) "X"
2) "A"
3) "B"
4) "C"
```

`LPUSH X` biến list thành `[X, A, B, C]`. Nếu lại gọi `LPUSH Y`, danh sách mới là `[Y, X, A, B, C]`.

### 2.3. `LPOP`: lấy và xóa phần tử đầu

```redis
LPOP demo:list:ends
LRANGE demo:list:ends 0 -1
```

Nếu list đang là `[X, A, B, C]`, `LPOP` trả `"X"` và list còn:

```text
[A, B, C]
```

Đây là thao tác **tiêu thụ phần tử**: giá trị bị xóa khỏi List trong cùng một lệnh. Nếu chỉ muốn quan sát phần tử đầu mà giữ nguyên list, hãy dùng `LINDEX key 0` hoặc API `index(key, 0)`.

### 2.4. `RPOP`: lấy và xóa phần tử cuối

```redis
RPOP demo:list:ends
LRANGE demo:list:ends 0 -1
```

Nếu list đang là `[A, B, C]`, `RPOP` trả `"C"` và list còn `[A, B]`.

### 2.5. Hình dung bốn thao tác cùng lúc

```text
             LPUSH                 RPUSH
               |                     |
               v                     v
         +-----+-----+-----+-----+-----+
HEAD --> |  A  |  B  |  C  |  D  |  E  | <-- TAIL
         +-----+-----+-----+-----+-----+
               ^                     ^
               |                     |
              LPOP                  RPOP

LPUSH X -> [X, A, B, C, D, E]
RPUSH X -> [A, B, C, D, E, X]
LPOP    -> trả A, list còn [B, C, D, E]
RPOP    -> trả E, list còn [A, B, C, D]
```

Mỗi dòng ở trên minh họa **một thao tác riêng** trên list ban đầu, không phải bốn thao tác thực hiện nối tiếp.

## 3. Thêm nhiều phần tử: thứ tự của `LPUSH` và `RPUSH`

Redis cho phép thêm nhiều phần tử bằng một lệnh:

```redis
RPUSH demo:list:many A B C
LRANGE demo:list:many 0 -1
```

Kết quả là `[A, B, C]`, vì `RPUSH` lần lượt thêm từng phần tử vào bên phải.

Điểm dễ nhầm nằm ở `LPUSH`:

```redis
LPUSH demo:list:many X Y Z
LRANGE demo:list:many 0 -1
```

Giả sử list trước lệnh là `[A, B, C]`. Redis lần lượt đẩy `X`, rồi `Y`, rồi `Z` vào đầu, nên kết quả:

```text
[Z, Y, X, A, B, C]
```

Các giá trị trong câu lệnh `LPUSH key X Y Z` sẽ xuất hiện theo **thứ tự đảo ngược** khi nhìn từ trái sang phải trên list.

Điều này cũng đúng khi ứng dụng sử dụng các phương thức Spring Data Redis:

```java
Long size = redis.opsForList().rightPushAll(
        "demo:list:many",
        List.of("A", "B", "C")
);

Long newSize = redis.opsForList().leftPushAll(
        "demo:list:many",
        List.of("X", "Y", "Z")
);
```

`leftPushAll` không có nghĩa Spring tự đảo danh sách input để giữ nguyên thứ tự hiển thị. Cần dựa trên semantics `LPUSH`.

Nếu muốn một list trống có thứ tự `[A, B, C]`, `rightPushAll(key, List.of("A","B","C"))` là cách dễ hiểu. Nếu muốn đẩy nhiều phần tử vào đầu nhưng vẫn giữ thứ tự `A, B, C` khi duyệt từ trái, hãy suy nghĩ về thứ tự truyền và sử dụng `LPUSH` một cách có chủ đích.

## 4. Cấu hình Spring Data Redis và dùng `ListOperations`

Ví dụ Spring Boot 3.x sử dụng starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Kết nối Redis standalone trong môi trường phát triển:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

Khi điều kiện auto-configuration phù hợp, Spring Boot tạo `RedisConnectionFactory` và `StringRedisTemplate`. Không cần khởi tạo connection mới ở từng service.

`StringRedisTemplate` có key và value serializer theo chuỗi, rất tiện cho ví dụ minh họa lệnh List. Nếu thực tế phần tử là object Java, có thể dùng `RedisTemplate<String, Task>` với value serializer JSON hoặc định dạng tương ứng; khi đó List vẫn là **Redis List**, còn từng phần tử List chứa byte payload của object.

### Lấy `ListOperations` từ template

```java
import org.springframework.data.redis.core.ListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class QueueService {
    private final ListOperations<String, String> listOps;

    public QueueService(StringRedisTemplate redis) {
        this.listOps = redis.opsForList();
    }
}
```

`ListOperations<K,V>` dùng key kiểu `K` và value kiểu `V` theo cấu hình của template. Với `StringRedisTemplate`, cả hai đều là `String`.

Các thao tác chính:

```java
Long count = listOps.leftPush(key, value);
Long count2 = listOps.rightPush(key, value);

String first = listOps.leftPop(key);
String last = listOps.rightPop(key);
```

`leftPush` và `rightPush` trả về **độ dài List sau khi thêm** (dạng `Long`). `leftPop` và `rightPop` trả về **giá trị được lấy ra**, hoặc `null` nếu không có phần tử trong lần đọc không blocking. Trong pipeline/transaction, kết quả trực tiếp của một số lời gọi có thể là `null` vì framework trả kết quả sau.

## 5. Ví dụ Java đầy đủ: deque có thể thêm/lấy ở cả hai đầu

Ta xây dựng một service quản lý list thông báo dưới namespace `shop:dev:notifications:`.

```java
package com.example.shop.redis;

import java.util.List;
import java.util.Objects;
import org.springframework.data.redis.core.ListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationDeque {

    private final ListOperations<String, String> lists;

    public NotificationDeque(StringRedisTemplate redis) {
        this.lists = redis.opsForList();
    }

    private String key(String userId) {
        Objects.requireNonNull(userId, "userId");
        if (!userId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid userId");
        }
        return "shop:dev:notifications:" + userId;
    }

    public Long addFirst(String userId, String notificationId) {
        Objects.requireNonNull(notificationId, "notificationId");
        return lists.leftPush(key(userId), notificationId);
    }

    public Long addLast(String userId, String notificationId) {
        Objects.requireNonNull(notificationId, "notificationId");
        return lists.rightPush(key(userId), notificationId);
    }

    public String removeFirst(String userId) {
        return lists.leftPop(key(userId));
    }

    public String removeLast(String userId) {
        return lists.rightPop(key(userId));
    }

    public List<String> snapshot(String userId) {
        List<String> items = lists.range(key(userId), 0, -1);
        return items == null ? List.of() : items;
    }
}
```

Giả sử khởi đầu key chưa tồn tại:

```java
deque.addLast("u42", "n1");  // [n1]
deque.addLast("u42", "n2");  // [n1, n2]
deque.addFirst("u42", "n0"); // [n0, n1, n2]

String first = deque.removeFirst("u42"); // "n0"
String last = deque.removeLast("u42");   // "n2"

List<String> rest = deque.snapshot("u42"); // ["n1"]
```

Với `snapshot`, `range(key, 0, -1)` trả toàn bộ phần tử theo thứ tự hiện tại của list. Mã trên trả về danh sách rỗng nếu kết quả trực tiếp bằng `null`; trong code sản phẩm cần tránh gọi `snapshot` theo cách này bên trong pipeline/transaction, nơi `null` có thể có nghĩa **kết quả chưa được trả về**, không phải list trống.

Ví dụ này lưu **ID thông báo**, thay vì nội dung thông báo dài hoặc thông tin nhạy cảm. Có thể lấy nội dung từ nguồn dữ liệu tương ứng khi cần. Cách lưu ID thường giúp giảm kích thước phần tử và giữ cấu trúc key dễ quản lý.

## 6. Thiết kế FIFO queue và LIFO stack

Cùng một Redis List có thể thực hiện các mô hình truy cập khác nhau. **FIFO** (*first in, first out*) nghĩa là phần tử vào trước được lấy ra trước. **LIFO** (*last in, first out*) nghĩa là phần tử vào sau được lấy ra trước.

### 6.1. FIFO: thêm bên phải, lấy bên trái

```text
Producer: RPUSH / rightPush
Consumer: LPOP / leftPop

RPUSH A -> [A]
RPUSH B -> [A, B]
RPUSH C -> [A, B, C]

LPOP   -> A ; list còn [B, C]
LPOP   -> B ; list còn [C]
LPOP   -> C ; list còn []
```

Java:

```java
public Long enqueue(String queueKey, String taskId) {
    return redis.opsForList().rightPush(queueKey, taskId);
}

public String dequeue(String queueKey) {
    return redis.opsForList().leftPop(queueKey);
}
```

Một mô hình FIFO khác vẫn hợp lệ là **`LPUSH` + `RPOP`**, miễn là producer và consumer nhất quán về hai đầu.

### 6.2. LIFO: thêm và lấy cùng một đầu

```text
Producer: LPUSH / leftPush
Consumer: LPOP / leftPop

LPUSH A -> [A]
LPUSH B -> [B, A]
LPUSH C -> [C, B, A]

LPOP   -> C ; list còn [B, A]
LPOP   -> B ; list còn [A]
LPOP   -> A ; list còn []
```

Java:

```java
public Long push(String stackKey, String item) {
    return redis.opsForList().leftPush(stackKey, item);
}

public String pop(String stackKey) {
    return redis.opsForList().leftPop(stackKey);
}
```

`RPUSH` + `RPOP` cũng là một stack LIFO. Không có đầu trái hoặc phải nào mặc định là “đúng” cho FIFO/LIFO; **cặp thao tác** mới quyết định hành vi.

### Bảng chọn nhanh

| Cách thêm | Cách lấy | Hành vi |
|---|---|---|
| `RPUSH` | `LPOP` | FIFO |
| `LPUSH` | `RPOP` | FIFO |
| `LPUSH` | `LPOP` | LIFO |
| `RPUSH` | `RPOP` | LIFO |
| Cả hai đầu | Cả hai đầu | Deque, tùy quyết định nghiệp vụ |

Ví dụ, hàng đợi xử lý tác vụ theo thứ tự nhận yêu cầu nên dùng mô hình FIFO nhất quán. Ngược lại, một danh sách lịch sử thao tác mới nhất ở đầu có thể dùng `LPUSH`, đọc bằng `LRANGE` hoặc `LINDEX` rồi chỉ xóa khi cần, thay vì `LPOP` làm mất lịch sử ngay.

## 7. Pop trên List rỗng và khi không có key

Redis List key **không cần tạo trước** khi `LPUSH` hoặc `RPUSH`. Nếu chưa tồn tại, lệnh push tự tạo key kiểu List với phần tử đầu tiên.

Với một key chưa tồn tại hoặc list đã rỗng, `LPOP`/`RPOP` trả về nil:

```redis
LPOP demo:list:missing
RPOP demo:list:missing
```

Đối với `StringRedisTemplate` trong lời gọi thông thường:

```java
String value = redis.opsForList().leftPop("demo:list:missing");
// value == null
```

Việc trả `null` giúp consumer biết **hiện không có phần tử**, khác với lỗi kết nối hoặc exception. Consumer có thể trả kết quả “queue empty”, chờ lần gọi tiếp theo, hoặc sử dụng thao tác blocking nếu nghiệp vụ phù hợp.

Một Redis List không duy trì một key rỗng có độ dài 0 như một thực thể tồn tại độc lập. Khi `LPOP`/`RPOP` lấy phần tử cuối cùng, Redis xóa luôn key List đó. Do đó:

```redis
RPUSH demo:list:single only-one
LPOP demo:list:single
EXISTS demo:list:single
```

`EXISTS` trả `0` sau khi phần tử cuối bị lấy, nếu không có writer khác thêm lại key.

### Phân biệt `null` trong pipeline hoặc transaction

Trong Spring Data Redis, nếu các lệnh được **queue** trong pipeline hoặc transaction, phương thức có thể trả `null` ngay cả khi Redis sẽ thực thi lệnh sau đó. Khi đó không được coi `null` ngay tại lời gọi là queue rỗng. Cần lấy kết quả từ cơ chế pipeline/transaction tương ứng.

## 8. Xem phần tử ở hai đầu mà không xóa

`leftPop` và `rightPop` là thao tác **destructive**: sau khi trả value, phần tử không còn trong list. Nếu chỉ muốn quan sát, dùng `LINDEX`:

```redis
RPUSH demo:list:peek A B C

LINDEX demo:list:peek 0
# "A"

LINDEX demo:list:peek -1
# "C"
```

Trong Spring Data Redis:

```java
String first = redis.opsForList()
        .index("demo:list:peek", 0);

String last = redis.opsForList()
        .index("demo:list:peek", -1);
```

Index `0` là phần tử đầu trái, `-1` là phần tử cuối phải. Redis cho phép chỉ số âm để đếm từ đuôi list. Chỉ số nằm ngoài phạm vi trả về nil ở Redis, thường thành `null` trong API Java tương ứng.

Đọc snapshot nhiều phần tử:

```java
List<String> full = redis.opsForList()
        .range("demo:list:peek", 0, -1);

List<String> firstThree = redis.opsForList()
        .range("demo:list:peek", 0, 2);
```

`range(key, start, end)` dùng khoảng **bao gồm cả hai đầu**. `range(key, 0, 2)` tối đa trả ba phần tử đầu. Lệnh `LRANGE` là thao tác đọc, không tự xóa phần tử.

`LLEN` xem độ dài:

```java
Long size = redis.opsForList().size("demo:list:peek");
```

Thông thường `size` trả `0` nếu key chưa tồn tại. Khi chạy pipeline/transaction, kết quả tức thời vẫn có thể là `null`.

## 9. Lấy nhiều phần tử trong một lần pop

Các phiên bản Redis và Spring Data Redis hiện đại hỗ trợ pop nhiều phần tử ở một đầu, ví dụ Redis `LPOP key count` và `RPOP key count`.

```redis
RPUSH demo:list:batch A B C D E
LPOP demo:list:batch 2
```

Kết quả:

```text
1) "A"
2) "B"
```

List còn `[C, D, E]`.

Tương ứng trong Spring Data Redis 3.x:

```java
List<String> firstTwo = redis.opsForList()
        .leftPop("demo:list:batch", 2);

List<String> lastTwo = redis.opsForList()
        .rightPop("demo:list:batch", 2);
```

Với `rightPop(key, 2)`, thứ tự trả ra theo hướng lấy từ phải sang trái; không giả định kết quả luôn giữ thứ tự `LRANGE` ban đầu.

Ví dụ list `[A, B, C, D]`:

```text
LPOP key 2 -> [A, B], list còn [C, D]
RPOP key 2 -> [D, C], list còn [A, B]
```

Mỗi lệnh pop nhiều phần tử là một thao tác Redis; không cần tách thành nhiều `LPOP` nếu thực sự cần lấy tối đa một nhóm trong cùng một lệnh. Tuy vậy, việc pop nhiều vẫn **xóa** phần tử khỏi list ngay tại thời điểm thực thi.

Các overload này phụ thuộc phiên bản thư viện và Redis server; khi làm việc với hệ thống legacy, cần đối chiếu API thực tế của Spring Data Redis và các lệnh Redis được server hỗ trợ.

## 10. Blocking pop: chờ phần tử thay vì polling liên tục

`LPOP` và `RPOP` trả ngay khi list trống. Nếu một worker liên tục gọi `LPOP` mỗi vài mili giây, nó tạo nhiều request không có việc và tiêu tốn CPU/network.

Redis cung cấp `BLPOP` và `BRPOP` để **chờ có phần tử**, tối đa theo timeout quy định.

```redis
BLPOP demo:list:blocking 5
```

Lệnh trên chờ tối đa khoảng 5 giây. Nếu producer kịp thực hiện:

```redis
RPUSH demo:list:blocking task-101
```

`BLPOP` có thể thức dậy và trả về **tên key cùng giá trị**:

```text
1) "demo:list:blocking"
2) "task-101"
```

Redis trả tên key vì `BLPOP` native có thể chờ nhiều key. Khi gọi `leftPop` qua `ListOperations` với một key, ứng dụng nhận trực tiếp **value** tương ứng.

### Spring Data Redis: `leftPop(key, timeout)` và `rightPop(key, timeout)`

```java
import java.time.Duration;

String task = redis.opsForList().leftPop(
        "demo:list:blocking",
        Duration.ofSeconds(5)
);
```

Trong Spring Data Redis 3.x, overload nhận `Duration` hỗ trợ cách gọi blocking pop tương ứng. Nếu không có item trong thời gian timeout, phương thức thường trả `null`. Redis/native client có thể có khác biệt về độ phân giải timeout hoặc cách quy đổi thời gian theo phiên bản; nên sử dụng thời hạn hữu hạn rõ ràng.

Một consumer FIFO có thể dùng:

```java
public String awaitNextJob(String queueKey) {
    return redis.opsForList().leftPop(
            queueKey, Duration.ofSeconds(5));
}
```

Để bảo đảm FIFO, producer phải thêm bằng `rightPush` hoặc `rightPushAll`. Nếu producer lại dùng `leftPush`, consumer `leftPop` sẽ tạo semantics LIFO.

### Điều gì xảy ra khi nhiều consumer cùng chờ?

Giả sử hai worker cùng gọi blocking pop trên một Redis List. Khi một phần tử được thêm, Redis chỉ giao phần tử đó cho **một** thao tác pop thành công; nó không cho cả hai worker cùng lấy đúng một phần tử trong hai lệnh pop đơn lẻ.

Tuy nhiên, điều này chỉ ngăn một phần tử bị pop hai lần khi nó còn trong list. Nó **không đảm bảo** task được xử lý thành công: worker nhận item rồi chết trước khi lưu kết quả thì item đã bị xóa.

### Blocking pop chiếm tài nguyên chờ

Trong ứng dụng Spring MVC/Jedis đồng bộ, một blocking pop có thể giữ một thread và một connection trong thời gian chờ. Với nhiều worker đang chờ, cần tính toán kích thước connection pool, số thread và timeout; không mở hàng nghìn blocking pop vô hạn mà không có kế hoạch năng lực hạ tầng.

Với ứng dụng reactive, cần chọn driver và API phù hợp để tránh chặn event-loop. Đừng gọi API đồng bộ blocking trực tiếp trên event-loop của WebFlux.

## 11. Ví dụ consumer Java với timeout hữu hạn

Một service đơn giản nhận tác vụ từ Redis List:

```java
package com.example.jobs;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class EmailTaskQueue {

    private static final String KEY = "shop:dev:jobs:email";

    private final StringRedisTemplate redis;

    public EmailTaskQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Producer: thêm vào đuôi (FIFO).
    public Long submit(String taskId) {
        return redis.opsForList().rightPush(KEY, taskId);
    }

    // Consumer: lấy từ đầu, tối đa 3 giây.
    public String takeNext() {
        return redis.opsForList().leftPop(
                KEY, Duration.ofSeconds(3));
    }
}
```

Worker có thể gọi:

```java
String taskId = queue.takeNext();

if (taskId == null) {
    // Hết thời gian chờ, hiện không có tác vụ mới.
    return;
}

// Chỉ là ví dụ minh họa. Việc xử lý thật cần
// quản lý retry, idempotency và trạng thái thành công.
process(taskId);
```

Đây là mô hình consumer **đơn giản**. Phần tử bị loại khỏi Redis ngay khi `takeNext` trả về, nên nếu `process(taskId)` thất bại thì Redis List không tự đưa tác vụ trở lại. Với công việc quan trọng, phải có thêm thiết kế xác nhận xử lý, retry và khôi phục lỗi.

Nếu producer muốn chèn việc ưu tiên vào **đầu** danh sách, `leftPush` có thể làm việc đó, nhưng trật tự xử lý không còn FIFO tuyệt đối. Khi hệ thống cần priority queue, nên cân nhắc data structure phù hợp thay vì trộn nhiều mức ưu tiên vào một List mà không có hợp đồng rõ ràng.

## 12. Atomicity: mỗi push/pop là một lệnh nguyên tử

Các lệnh `LPUSH`, `RPUSH`, `LPOP` và `RPOP` là những thao tác Redis đơn lẻ. Trên Redis server thực thi lệnh, một lệnh pop không trả cùng phần tử cho hai consumer ở hai lần pop đồng thời.

Ví dụ hai worker cùng lấy list `[task-1]`:

```text
Worker A: LPOP jobs -> "task-1"
Worker B: LPOP jobs -> nil

Hoặc nếu B đến trước:
Worker B: LPOP jobs -> "task-1"
Worker A: LPOP jobs -> nil
```

Không có trạng thái trong đó cả hai lệnh pop thành công đều lấy cùng một phần tử `task-1` từ cùng một lần tồn tại trong list. Điều này xuất phát từ việc thao tác pop và xóa là một lệnh.

### Tránh dùng `LLEN` rồi mới `LPOP` để kiểm tra

Một đoạn code tưởng như hợp lý:

```java
Long size = redis.opsForList().size(key);

if (size != null && size > 0) {
    return redis.opsForList().leftPop(key);
}
return null;
```

Có **race condition**: sau khi đọc `LLEN` nhưng trước `LPOP`, worker khác có thể đã lấy phần tử cuối. Khi đó `leftPop` vẫn trả `null`. Ngược lại, sau khi `LLEN` báo 0, producer có thể thêm phần tử ngay sau đó.

Thay vì `LLEN` trước để “bảo đảm có phần tử”, hãy gọi `leftPop` trực tiếp và xử lý `null`. `LLEN` phù hợp để quan sát độ dài, không phải cơ chế giữ chỗ một phần tử cho worker.

### Đẩy và lấy ở hai đầu không tạo transaction nghiệp vụ

Nếu một service vừa `RPUSH` queue vừa ghi database quan hệ, hai thao tác nằm ở hai hệ thống khác nhau. Redis không tự bảo đảm cả hai thành công hoặc cả hai rollback. Tương tự, worker pop rồi xử lý HTTP request có thể gặp lỗi sau pop.

Atomicity của **một Redis command** không đồng nghĩa với exactly-once processing trên toàn ứng dụng.

## 13. Khi cần giữ tác vụ đang xử lý: chuyển phần tử sang List khác

`LPOP`/`RPOP` xóa item khỏi List ngay lập tức. Với queue tác vụ không được phép mất âm thầm, một mô hình cổ điển là chuyển atomically từ List **pending** sang List **processing**, sau đó chỉ xóa khỏi processing khi đã xử lý thành công.

Redis hiện đại có lệnh `LMOVE`:

```redis
LMOVE jobs:pending jobs:processing LEFT RIGHT
```

Nó lấy phần tử bên trái của `jobs:pending`, đồng thời thêm vào bên phải của `jobs:processing` trong **một lệnh atomic trên một Redis server**.

```text
Trước:
pending:    [task-1, task-2, task-3]
processing: []

LMOVE pending processing LEFT RIGHT

Sau:
pending:    [task-2, task-3]
processing: [task-1]
```

Spring Data Redis có API `ListOperations.move(...)` trong các phiên bản phù hợp:

```java
import org.springframework.data.redis.connection.RedisListCommands.Direction;

String task = redis.opsForList().move(
        "shop:dev:jobs:pending",
        Direction.LEFT,
        "shop:dev:jobs:processing",
        Direction.RIGHT
);
```

Khi cần **chờ** phần tử trước khi di chuyển, Redis hỗ trợ `BLMOVE` (và Spring Data Redis hỗ trợ overload move với thời gian chờ ở những phiên bản tương ứng). Tên API/khả năng hỗ trợ phụ thuộc vào phiên bản Redis, Spring Data Redis và driver.

### Vì sao vẫn chưa phải reliable queue hoàn chỉnh?

Di chuyển từ pending sang processing giảm rủi ro “pop xong worker chết và không biết item ở đâu”, nhưng còn những vấn đề bắt buộc phải giải quyết:

1. **Acknowledgment:** làm sao biết task nào đã xử lý xong và được phép xóa khỏi processing?
2. **Recovery:** nếu worker chết, ai quét các task bị kẹt trong processing và chuyển lại pending?
3. **Ownership/timeout:** worker nào đang xử lý task, và bao lâu thì có thể retry?
4. **Idempotency:** nếu task được xử lý xong nhưng ACK thất bại, retry có gây thực thi tác dụng phụ lần hai không?
5. **Trùng payload:** `LREM` dựa vào giá trị có thể xóa nhầm phần tử nếu nhiều task có payload trùng nhau; nên dùng ID duy nhất và quy tắc ACK có kiểm soát.

Với Redis Cluster, hai key `pending` và `processing` của `LMOVE` phải thuộc **cùng hash slot** để hỗ trợ thao tác multi-key atomic, ví dụ:

```text
shop:dev:jobs:{email}:pending
shop:dev:jobs:{email}:processing
```

Cả hai dùng hash tag `email` nên nằm cùng slot. Không dùng một hash tag quá rộng cho mọi queue của hệ thống nếu điều đó dồn tải về một node.

Khi cần consumer group, theo dõi pending message và cơ chế ACK/reclaim được thiết kế sẵn, **Redis Streams** với consumer groups thường là lựa chọn thích hợp hơn Redis List thuần. Redis List vẫn hữu ích với queue đơn giản, deque và các cấu trúc cần thao tác hai đầu nhanh.

## 14. TTL và vòng đời của Redis List

Redis TTL được áp dụng ở **mức key**, không phải từng phần tử List. Khi đặt:

```redis
RPUSH demo:list:ttl A B C
EXPIRE demo:list:ttl 60
```

Thì cả Redis List sẽ hết hạn sau khoảng 60 giây. Redis không tự cho `A` TTL 60 giây nhưng `B` TTL 120 giây trong cùng key theo mô hình TTL thông thường.

### Push/pop thông thường có giữ TTL không?

Các lệnh `LPUSH`/`RPUSH` cập nhật nội dung **trong cùng key List**, và nhìn chung **không xóa TTL đang có** của key khi key vẫn tồn tại. Trái lại, nếu key đã không tồn tại vì hết hạn hoặc do pop phần tử cuối, một `RPUSH` mới sẽ tạo lại key **không có TTL** cho đến khi ứng dụng đặt expiry lần nữa.

Ví dụ:

```redis
RPUSH demo:list:ttl one
EXPIRE demo:list:ttl 120
RPUSH demo:list:ttl two
TTL demo:list:ttl
```

`TTL` vẫn phản ánh thời gian còn lại, không tự được đặt về 120 giây do `RPUSH`.

Nhưng nếu lần lượt `LPOP` hết cả hai phần tử, key sẽ biến mất. Một lần `RPUSH` sau đó tạo key mới, và key mới không tự kế thừa expiry cũ.

### TTL trong Spring Data Redis

```java
String key = "shop:dev:notifications:u42";

redis.opsForList().rightPush(key, "n101");
redis.expire(key, Duration.ofMinutes(30));
```

Hai lời gọi là **hai lệnh riêng**. Nếu ứng dụng lỗi sau `rightPush` nhưng trước `expire`, key có thể không có TTL. Nếu TTL là yêu cầu bắt buộc cho toàn bộ thao tác, cần thiết kế cơ chế atomic phù hợp (ví dụ Lua script), đồng thời xét đến Redis Cluster và kích thước công việc.

Nếu nhiều phần tử có vòng đời độc lập, việc dồn tất cả vào một List có TTL ở key có thể không phù hợp. Cân nhắc dùng key riêng theo phần tử, Sorted Set theo timestamp hoặc data structure khác tùy mục đích.

## 15. Kiểm soát độ dài List và áp lực bộ nhớ

Một List nhận `RPUSH` liên tục mà không có consumer hoặc cơ chế giới hạn có thể tăng rất lớn. Redis sẽ phải giữ dữ liệu trong RAM; điều này ảnh hưởng tới dung lượng, persistence và chính sách eviction.

Có thể quan sát bằng:

```redis
LLEN shop:dev:jobs:email
```

Hoặc trong Spring Data Redis:

```java
Long length = redis.opsForList().size("shop:dev:jobs:email");
```

### Ví dụ giữ tối đa N phần tử lịch sử mới nhất

Nếu List phục vụ lịch sử mới nhất ở đầu, producer có thể `LPUSH` item mới rồi `LTRIM` giữ N item đầu:

```redis
LPUSH shop:dev:history:u42 event-new
LTRIM shop:dev:history:u42 0 99
```

Kết quả dự kiến giữ tối đa 100 phần tử gần đây nhất, nếu không có thao tác đồng thời làm thay đổi list giữa hai lệnh. Trong Spring Data Redis:

```java
String key = "shop:dev:history:u42";
redis.opsForList().leftPush(key, "event-new");
redis.opsForList().trim(key, 0, 99);
```

**Lưu ý:** `LPUSH` rồi `LTRIM` là hai Redis commands. Trong khoảng giữa chúng, client khác có thể nhìn thấy list dài hơn giới hạn hoặc có writer khác thêm phần tử. Nếu cần quy tắc “thêm và trim” atomic, hãy dùng một script/transaction phù hợp và có giới hạn tài nguyên.

Không nên đặt giới hạn bằng cách xóa phần tử chưa xử lý khỏi một **queue công việc** trừ khi chính sách mất tác vụ là chấp nhận được. Quy tắc cắt List dùng tốt cho recent events/cache, nhưng không tự thích hợp cho job queue quan trọng.

## 16. Serializer: List chứa byte values, không tự hiểu đối tượng Java

Redis List không biết phần tử là Java `String`, `UUID`, `Task` hay JSON. Spring Data Redis sử dụng **value serializer** của template để mã hóa từng phần tử khi `leftPush`/`rightPush` và giải mã khi `leftPop`/`rightPop`.

Với `StringRedisTemplate`:

```java
redis.opsForList().rightPush("demo:list:string", "task-101");
```

Value được lưu ở dạng chuỗi UTF-8.

Với `RedisTemplate<String, Task>` sử dụng serializer JSON, mỗi phần tử List là payload JSON (vẫn thuộc Redis data type List).

Ví dụ DTO:

```java
public record EmailTask(String id, String recipientId) {}
```

Cấu hình template chuyên biệt:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class EmailTaskRedisConfig {

    @Bean
    RedisTemplate<String, EmailTask> emailTaskRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, EmailTask> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(EmailTask.class));
        template.afterPropertiesSet();
        return template;
    }
}
```

Sử dụng:

```java
String queueKey = "shop:dev:jobs:email-json";

emailTaskRedisTemplate.opsForList().rightPush(
        queueKey, new EmailTask("t101", "u42"));

EmailTask task = emailTaskRedisTemplate.opsForList()
        .leftPop(queueKey);
```

Các nơi ghi và đọc cùng queue phải thống nhất serializer và schema. Nếu producer ghi JSON còn consumer sử dụng `JdkSerializationRedisSerializer` hoặc serializer cho class khác, quá trình giải mã có thể lỗi, dù Redis List vẫn còn nguyên byte payload.

Khi muốn tương tác với service không dùng Java, việc thống nhất JSON có schema hoặc một format độc lập với Java thường dễ quản lý hơn việc phụ thuộc Java native serialization.

### Tên key không bị serialize giống value

`RedisTemplate` có `keySerializer` riêng. Nếu muốn dễ thao tác với Redis CLI và chia sẻ key giữa service, thường dùng `StringRedisSerializer` cho tên key và serializer riêng cho List item.

`ListOperations` không có một serializer “list” duy nhất biến toàn bộ Java `List<T>` thành một Redis List. Nó thực hiện lệnh Redis List lên các phần tử, mỗi phần tử được serialize theo cấu hình template. Lưu một Java `List<T>` như JSON vào Redis string qua `opsForValue()` là mô hình dữ liệu **khác** với Redis List.

## 17. Redis Cluster và thao tác ở hai đầu List

`LPUSH`, `RPUSH`, `LPOP`, `RPOP` với **một key** hoạt động tự nhiên trong Redis Cluster, vì một Redis key được ánh xạ tới một hash slot và client cluster-aware gửi lệnh tới node sở hữu slot đó.

Ví dụ các queue độc lập:

```text
shop:prod:jobs:email
shop:prod:jobs:sms
shop:prod:jobs:reports
```

Các key có thể nằm ở các slot/node khác nhau mà việc push/pop trên từng key không có vấn đề multi-key.

Tuy nhiên, các thao tác kết hợp nhiều key như `LMOVE source destination LEFT RIGHT` phải thỏa ràng buộc cùng slot. Nếu không, có thể gặp `CROSSSLOT`.

```text
shop:prod:jobs:{email}:pending
shop:prod:jobs:{email}:processing
```

Cùng hash tag `email` giúp hai key cùng slot, nhưng không nên ép **toàn bộ queue** của hệ thống về một slot bằng hash tag quá chung.

Redis Cluster chỉ hỗ trợ logical database `0`. Phân tách queue theo namespace trong tên key, thay vì cố chọn DB 1/DB 2 trong Cluster.

Đối với lỗi `MOVED`, `ASK` và thay đổi topology, client hỗ trợ Cluster như Lettuce/Jedis ở chế độ phù hợp có nhiệm vụ định tuyến/redirect; ứng dụng không nên tự ghim một Redis node làm nơi xử lý mọi queue nếu Cluster có nhiều primary.

## 18. Concurrency: producer, consumer và thứ tự xử lý

Một List có thể có nhiều producer và consumer. Redis thực thi từng lệnh `RPUSH`/`LPOP` atomically, nhưng **thứ tự xử lý hoàn tất** ngoài Redis không nhất thiết giống **thứ tự lấy** khỏi queue.

Ví dụ:

```text
Queue FIFO: [task-A, task-B]

Worker 1: LPOP -> task-A, xử lý mất 10 giây
Worker 2: LPOP -> task-B, xử lý mất 1 giây

Hoàn tất:
task-B xong trước task-A
```

Queue vẫn đã **phát task theo FIFO**, nhưng completion order bị đảo vì thực thi song song. Nếu nghiệp vụ yêu cầu xử lý hoàn tất theo đúng thứ tự, cần cơ chế điều phối bổ sung (ví dụ consumer tuần tự trên từng partition/entity), không chỉ chọn `RPUSH` + `LPOP`.

### Chờ nhiều queue và ưu tiên

Lệnh Redis `BLPOP` native có thể nhận nhiều key theo thứ tự ưu tiên trong câu lệnh. Khi nhiều key đang có sẵn item, Redis chọn theo thứ tự key được liệt kê trong lệnh, theo semantics của `BLPOP`. API `leftPop(key, timeout)` ở mức `ListOperations` minh họa trong bài tập trung vào một key; nếu cần chờ nhiều queue cùng lúc, cần dùng API driver/Spring Data Redis tương thích và thiết kế ràng buộc Cluster.

Không nên tự suy ra semantics “ưu tiên công việc” chỉ từ tên queue hoặc việc nhiều worker cùng chờ. Cần định nghĩa rõ fairness, starvation, retry và thứ tự khi có nhiều hàng đợi.

## 19. Vấn đề độ tin cậy: mất, lặp và xử lý lại tác vụ

Một câu chuyện thường gặp:

```text
Producer -> RPUSH task-101 -> Redis List
                                |
Consumer <- LPOP task-101 -----+
     |
     +--> gọi dịch vụ bên ngoài
              |
              +--> lỗi hoặc consumer chết
```

Tác vụ đã được lấy ra khỏi List. Redis không biết nó thành công hay thất bại, và không tự khôi phục lại task đã pop.

Điều này dẫn tới hai lựa chọn kiến trúc:

| Mức yêu cầu | Hướng thiết kế |
|---|---|
| Queue đơn giản, có thể mất một số phần tử | `RPUSH` + `LPOP` hoặc `LPUSH` + `RPOP` |
| Cần chờ item và tránh polling | `BLPOP`/`BRPOP` với timeout phù hợp |
| Muốn theo dõi task đã nhận nhưng chưa ACK | Mô hình pending/processing với `LMOVE`/`BLMOVE`, recovery và ACK được thiết kế đầy đủ |
| Cần consumer group, pending tracking, ACK và claim | Xem xét Redis Streams |
| Đòi hỏi giao dịch bền vững với database ngoài Redis | Thiết kế outbox/transactional messaging phù hợp với nguồn dữ liệu và yêu cầu nghiệp vụ |

Redis persistence (RDB/AOF) cũng có các mức bảo đảm riêng. Chỉ vì thao tác `RPUSH` trả thành công không có nghĩa dữ liệu đã được đồng bộ bền vững trong mọi kịch bản mất điện, failover hoặc cấu hình persistence. Khi cần bảo đảm giao nhận chặt chẽ, phải xem toàn bộ pipeline từ producer đến consumer, chứ không chỉ chọn lệnh Redis List.

Để giảm tác dụng phụ khi retry, mỗi task nên có **định danh idempotency** ổn định; xử lý nghiệp vụ phải xác định việc nhận cùng task lần thứ hai có được chấp nhận hoặc bỏ qua thế nào.

## 20. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lấy ra theo thứ tự ngược dự kiến | Dùng `LPUSH` + `LPOP` khi mong FIFO | Dùng `RPUSH` + `LPOP` hoặc `LPUSH` + `RPOP` |
| `leftPop` trả `null` | List/key không tồn tại hoặc đã hết item | Xử lý queue empty; trong pipeline/transaction đọc kết quả qua cơ chế tương ứng |
| `rightPush` bị `WRONGTYPE` | Key đang tồn tại với Redis string/hash/set khác List | Kiểm tra `TYPE key` và quy ước key namespace |
| `leftPushAll` đảo thứ tự các phần tử truyền vào | Semantics đẩy từng phần tử về phía head | Tính đúng thứ tự hoặc chọn `rightPushAll` |
| Worker chờ rất lâu ở `leftPop(key, timeout)` | Blocking pop và timeout được cấu hình dài | Dùng timeout hữu hạn, kiểm soát connection/thread pool |
| Task biến mất khi worker lỗi | `LPOP` xóa item trước lúc xử lý xong | Thiết kế ACK/retry; cân nhắc pending/processing hoặc Streams |
| Queue ngày càng dài | Producer nhanh hơn consumer; không có cơ chế backpressure | Quan sát `LLEN`, điều chỉnh throughput, chính sách overload |
| List hết TTL bất ngờ | TTL nằm ở key, không ở từng phần tử | Xác định chính sách expiry và cách tái tạo key |
| Key tạo lại sau khi queue rỗng không có TTL | Pop phần tử cuối làm Redis xóa key cũ | Áp lại expiry khi tạo key mới hoặc thay mô hình |
| Lỗi deserialize payload | Writer/reader dùng serializer hoặc class khác | Thống nhất format, version và serializer |
| Lỗi `CROSSSLOT` khi move từ pending sang processing | Hai Redis List key ở slot khác nhau | Dùng hash tag phù hợp cho cặp key liên quan |

### Đừng dùng `KEYS *` để kiểm tra một queue lớn

Để kiểm tra một list cụ thể, dùng `TYPE`, `LLEN` và một khoảng `LRANGE` có giới hạn:

```bash
redis-cli TYPE shop:dev:jobs:email
redis-cli LLEN shop:dev:jobs:email
redis-cli LRANGE shop:dev:jobs:email 0 9
redis-cli TTL shop:dev:jobs:email
```

Lệnh `LRANGE key 0 -1` trả toàn bộ list, có thể tốn network/bộ nhớ nếu list rất lớn. Trong production, chỉ lấy một khoảng nhỏ khi debug; tránh in các payload chứa thông tin nhạy cảm.

## 21. Bài thực hành: một List đóng vai trò FIFO và LIFO

Các lệnh sau minh họa trên Redis standalone thử nghiệm, với namespace `demo:`. Nên chạy trên môi trường Redis dùng riêng cho thực hành.

### Thực hành A — FIFO

```bash
redis-cli RPUSH demo:lesson127:fifo job-1 job-2 job-3

redis-cli LRANGE demo:lesson127:fifo 0 -1
# job-1, job-2, job-3

redis-cli LPOP demo:lesson127:fifo
# job-1

redis-cli LPOP demo:lesson127:fifo
# job-2

redis-cli LLEN demo:lesson127:fifo
# 1
```

`RPUSH` đưa item mới vào đuôi. `LPOP` lấy item cũ nhất ở đầu.

### Thực hành B — LIFO

```bash
redis-cli LPUSH demo:lesson127:lifo job-1 job-2 job-3

redis-cli LRANGE demo:lesson127:lifo 0 -1
# job-3, job-2, job-1

redis-cli LPOP demo:lesson127:lifo
# job-3

redis-cli LPOP demo:lesson127:lifo
# job-2
```

Vì `LPUSH` thêm mỗi item vào đầu, `LPOP` lấy item vừa được thêm gần nhất.

### Thực hành C — Quan sát hai đầu và TTL

```bash
redis-cli RPUSH demo:lesson127:ends A B C

redis-cli LINDEX demo:lesson127:ends 0
# A

redis-cli LINDEX demo:lesson127:ends -1
# C

redis-cli EXPIRE demo:lesson127:ends 60
redis-cli LPUSH demo:lesson127:ends X
redis-cli TTL demo:lesson127:ends
# Vẫn có thời gian hết hạn còn lại
```

Lệnh `LINDEX` quan sát mà không xóa phần tử; `LPUSH` thêm phần tử đầu nhưng không tự kéo dài TTL của key đang tồn tại.

### Thực hành D — Blocking pop với hai terminal

Terminal A:

```bash
redis-cli BLPOP demo:lesson127:blocking 10
```

Trong khoảng thời gian chờ, Terminal B:

```bash
redis-cli RPUSH demo:lesson127:blocking task-42
```

Terminal A có thể nhận kết quả gồm tên key và `task-42`. Nếu đã hết 10 giây trước khi Terminal B push, Terminal A nhận nil; thực hành lại để quan sát trường hợp có item trong thời hạn chờ.

Lệnh `BLPOP` **tiêu thụ** item, không chỉ “nghe” thông báo. Nếu muốn fan-out để nhiều subscriber cùng nhận sự kiện, List pop không phải mô hình Pub/Sub; cần chọn Redis Pub/Sub hoặc Redis Streams tùy yêu cầu phát và lưu giữ sự kiện.

## 22. Câu hỏi tự kiểm tra

**1. Với List `[A, B]`, gọi `LPUSH key X Y` thì danh sách mới là gì?**

Lệnh đẩy `X` rồi `Y` vào đầu, nên kết quả `[Y, X, A, B]`.

**2. Muốn queue FIFO, producer `rightPush` thì consumer phải gọi gì?**

Consumer dùng `leftPop` (hoặc blocking `leftPop(key, Duration)`) để lấy item cũ nhất ở đầu.

**3. Muốn đọc phần tử cuối nhưng giữ nguyên List, dùng API nào?**

Dùng `opsForList().index(key, -1)`, tương ứng Redis `LINDEX key -1`. `rightPop` sẽ xóa phần tử.

**4. Nếu Redis List chỉ còn một phần tử rồi consumer `LPOP`, key còn tồn tại không?**

Thông thường không. Redis xóa key List khi phần tử cuối được lấy ra. Một lần push sau tạo key mới.

**5. `leftPop(key, Duration.ofSeconds(5))` khác `leftPop(key)` ở đâu?**

Bản có timeout chờ phần tử xuất hiện tối đa khoảng 5 giây; bản không timeout trả ngay. Trong hệ thống đồng bộ, thời gian chờ có thể chiếm một connection/thread.

**6. Vì sao việc pop atomic chưa đủ bảo đảm mỗi task được xử lý thành công đúng một lần?**

Bởi task bị xóa ngay khi pop. Worker có thể chết trước khi xử lý xong, hoặc đã xử lý xong nhưng lỗi trước ACK ở mô hình có ACK; cần retry, idempotency và tracking trạng thái riêng.

**7. Trong Redis Cluster, hai List key dùng `LMOVE` cần điều kiện gì?**

Chúng phải thuộc cùng hash slot để Redis có thể thực hiện thao tác nhiều key atomic theo giới hạn Cluster.

**8. Vì sao không nên dùng `LTRIM` tự động trên một queue quan trọng?**

Vì `LTRIM` xóa phần tử nằm ngoài khoảng giữ lại. Với queue chưa xử lý, đó có thể là mất task; chỉ nên trim khi chính sách nghiệp vụ chấp nhận việc loại bỏ phần tử.

## 23. Kết luận

Trong Spring Data Redis, thao tác với hai đầu Redis List được thể hiện rõ qua **`leftPush`, `rightPush`, `leftPop` và `rightPop`**. Cặp thêm/lấy ở **hai đầu đối diện** tạo queue FIFO; cặp thêm/lấy ở **cùng một đầu** tạo stack LIFO. `leftPushAll`/`rightPushAll` thêm nhiều phần tử nhưng cần hiểu thứ tự, trong khi `index` và `range` giúp quan sát list mà không xóa phần tử.

Mỗi push/pop là một Redis command atomic, song **pop xóa item ngay lập tức** nên chưa đủ cho hệ thống xử lý công việc cần retry và ACK. Blocking pop giúp tránh polling, nhưng cần timeout và quản lý connection phù hợp. TTL áp dụng lên **toàn bộ List key**; khi key trống và được tạo lại, thời hạn cũ không tự quay lại. Với Redis Cluster, thao tác trên một List key thường đơn giản, còn những lệnh chuyển giữa nhiều List key phải tôn trọng hash slot. Nắm rõ những quy tắc này giúp chọn đúng API của Spring Data Redis và xây dựng queue, stack hoặc deque có hành vi dự đoán được.
