# DISCARD và hủy giao dịch trước khi thực thi

Trong Spring Data Redis, một giao dịch Redis thường bắt đầu bằng lệnh `MULTI`, tiếp tục bằng việc đưa các lệnh vào hàng đợi và kết thúc bằng **`EXEC`** hoặc **`DISCARD`**. `EXEC` yêu cầu Redis thực thi các lệnh đã xếp hàng; ngược lại, **`DISCARD` hủy toàn bộ hàng đợi và đưa kết nối ra khỏi chế độ giao dịch trước khi bất kỳ lệnh nào trong hàng đợi được thực thi**.

Đây là một cơ chế rất hữu ích khi ứng dụng đã bắt đầu chuẩn bị một nhóm thao tác nhưng sau đó quyết định không thực hiện: người dùng rút yêu cầu, kiểm tra nghiệp vụ phát hiện điều kiện không đạt hoặc một bước chuẩn bị bị lỗi trước khi gọi `EXEC`.

Điều quan trọng nhất phải hiểu là **`DISCARD` chỉ hủy các lệnh còn đang chờ trong giao dịch**. Nó không hoàn tác lệnh đã được `EXEC` thực thi, không khôi phục tác động lên hệ thống khác và không thay thế mọi loại rollback của cơ sở dữ liệu quan hệ.

## 1. Vòng đời một giao dịch Redis

Redis Transaction có thể hình dung như một máy trạng thái:

~~~text
        Kết nối ở trạng thái bình thường
                         |
                         | MULTI
                         v
               Giao dịch đang mở
                         |
             +-----------+------------+
             |                        |
       Lệnh SET, INCR, ...        Quyết định kết thúc
             |                        |
             v               +--------+---------+
         QUEUED              |                  |
             |               v                  v
             +---------->  EXEC              DISCARD
                             |                  |
                             v                  v
                      Thực thi các lệnh   Bỏ toàn bộ lệnh
                      đã xếp hàng         chưa thực thi
                             |                  |
                             +---------+--------+
                                       |
                                       v
                         Kết nối về trạng thái bình thường
~~~

| Lệnh | Tác dụng | Kết quả đối với dữ liệu |
| --- | --- | --- |
| `MULTI` | Bắt đầu chế độ giao dịch trên kết nối hiện tại | Chưa áp dụng các lệnh sau đó |
| `SET`, `INCR`, `DEL`… sau `MULTI` | Được xếp vào hàng đợi, thường phản hồi `QUEUED` | Chưa sửa dữ liệu ở thời điểm xếp hàng |
| `EXEC` | Thực thi chuỗi lệnh trong hàng đợi | Các thay đổi có thể trở thành hiện thực |
| `DISCARD` | Xóa toàn bộ hàng đợi và kết thúc giao dịch | Không có lệnh đang chờ nào được thực thi |
| `WATCH` | Theo dõi thay đổi của key trước `MULTI` cho cơ chế kiểm soát đồng thời lạc quan | Không tự ghi dữ liệu; ảnh hưởng quyết định thực thi của `EXEC` |
| `UNWATCH` | Bỏ theo dõi các key đã `WATCH` | Hữu ích khi hủy một quy trình trước khi bắt đầu `MULTI` |

Một đặc điểm quan trọng: trạng thái `MULTI` gắn với **connection**, không gắn đơn thuần với tên key hay đối tượng Java. Vì vậy, khi dùng Spring Data Redis, các lời gọi `MULTI`, lệnh cần xếp hàng và `DISCARD` hoặc `EXEC` phải được thực hiện trong cùng một ngữ cảnh kết nối.

## 2. Ví dụ Redis CLI: `DISCARD` giữ nguyên dữ liệu ban đầu

Giả sử số lượng tồn kho của một sản phẩm là 10. Một luồng xử lý tạm chuẩn bị giảm tồn kho và tạo trạng thái đặt chỗ, nhưng người mua hủy thao tác trước khi giao dịch được thực thi.

Trước hết đặt giá trị ban đầu:

~~~redis
SET demo:stock:sku-42 10
DEL demo:reservation:r-101
~~~

Mở giao dịch và xếp hàng hai lệnh:

~~~redis
MULTI
DECRBY demo:stock:sku-42 2
SET demo:reservation:r-101 "PENDING"
~~~

Phản hồi điển hình từ Redis:

~~~text
OK
QUEUED
QUEUED
~~~

Khi chưa gọi `EXEC`, các lệnh `DECRBY` và `SET` vẫn ở trạng thái chờ. Nếu ứng dụng quyết định hủy, gửi:

~~~redis
DISCARD
~~~

Redis trả về:

~~~text
OK
~~~

Kiểm tra lại ở trạng thái bình thường:

~~~redis
GET demo:stock:sku-42
EXISTS demo:reservation:r-101
~~~

Kết quả:

~~~text
"10"
(integer) 0
~~~

**Tồn kho không bị giảm và reservation không được tạo.** Không cần chạy lệnh tăng lại tồn kho hay xóa reservation để “đảo ngược” giao dịch, vì hai lệnh đó chưa từng được thực thi.

Nếu thay `DISCARD` bằng `EXEC`, Redis sẽ thực thi các lệnh đã xếp hàng và trả lại các kết quả tương ứng. Sau đó, gọi `DISCARD` **không thể** đưa tồn kho từ 8 trở lại 10.

## 3. `DISCARD` thực sự hủy những gì?

`DISCARD` chỉ có hiệu lực đối với hàng đợi lệnh của giao dịch Redis **đang mở trên chính kết nối đó**.

Nó thực hiện những việc sau:

1. Bỏ tất cả lệnh đã được xếp hàng sau `MULTI`.
2. Kết thúc chế độ giao dịch, cho phép kết nối xử lý lệnh Redis bình thường trở lại.
3. Bỏ các key đang được theo dõi bằng `WATCH` trên kết nối đó, nếu có.

`DISCARD` **không** thực hiện các việc sau:

- Không đảo ngược những lệnh Redis đã chạy **trước** `MULTI`.
- Không hoàn tác bất cứ lệnh nào đã được `EXEC` thực thi.
- Không xóa hay sửa một object Java chỉ vì lệnh ghi object đó bị hủy.
- Không hủy lệnh của một giao dịch trên connection khác.
- Không khôi phục thay đổi của JDBC, HTTP, hệ thống file hoặc message broker.
- Không bảo đảm rollback cho các thao tác đã được thực hiện ngoài giao dịch Redis.

Ví dụ:

~~~redis
SET demo:outside "done"
MULTI
SET demo:inside "queued"
DISCARD
~~~

Sau `DISCARD`, `demo:outside` vẫn mang giá trị `"done"` vì lệnh đó chạy **trước `MULTI`**. Key `demo:inside` không được tạo bởi giao dịch vừa hủy.

Tương tự, sau khi hủy giao dịch, `EXEC` không còn một giao dịch đang mở để thực thi. Gọi `EXEC` hoặc `DISCARD` khi không ở trong `MULTI` sẽ dẫn tới lỗi Redis tương ứng, chẳng hạn `ERR EXEC without MULTI` hoặc `ERR DISCARD without MULTI`.

## 4. Hủy giao dịch trong Spring Data Redis bằng `RedisCallback`

Spring Data Redis cung cấp `RedisTemplate` và `StringRedisTemplate` để làm việc với Redis. Khi muốn điều khiển trực tiếp các lệnh `MULTI`, `EXEC` và `DISCARD` trên cùng một Redis connection, có thể dùng **`RedisCallback`**.

Ví dụ dưới đây cố tình xếp hàng một lệnh ghi rồi **hủy trước `EXEC`**, giúp thể hiện chính xác vai trò của `DISCARD`.

~~~java
package com.example.redis.transaction;

import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisDiscardService {

    private final StringRedisTemplate redis;

    public RedisDiscardService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void prepareAndCancel(String key, String proposedValue) {
        redis.execute((RedisCallback<Void>) connection -> {
            // StringRedisTemplate mặc định dùng UTF-8 cho key và value.
            byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);
            byte[] rawValue =
                proposedValue.getBytes(StandardCharsets.UTF_8);

            connection.multi();

            try {
                // Chỉ xếp hàng, chưa ghi rawValue vào Redis.
                connection.stringCommands().set(rawKey, rawValue);
            } catch (RuntimeException cause) {
                // Nếu khâu chuẩn bị thất bại, đóng giao dịch đang mở.
                try {
                    connection.discard();
                } catch (RuntimeException cleanupFailure) {
                    cause.addSuppressed(cleanupFailure);
                }
                throw cause;
            }

            // Quyết định hủy: không gọi EXEC.
            connection.discard();
            return null;
        });
    }
}
~~~

Sử dụng:

~~~java
redis.opsForValue().set("demo:order:1", "OLD");

discardService.prepareAndCancel("demo:order:1", "NEW");

String current = redis.opsForValue().get("demo:order:1");
System.out.println(current); // OLD
~~~

Điểm cần ghi nhớ:

- `redis.execute(RedisCallback)` cung cấp một connection cho toàn bộ callback, nên các lệnh nằm cùng phiên làm việc Redis.
- `connection.multi()` mở giao dịch trước khi xếp lệnh `SET`.
- `connection.stringCommands().set(...)` chỉ được Redis đưa vào hàng đợi trong chế độ `MULTI`.
- `connection.discard()` loại bỏ lệnh `SET` đang chờ và kết thúc giao dịch.
- Lời gọi `redis.opsForValue().get(...)` **sau callback** đọc dữ liệu thật và vẫn thấy giá trị cũ.
- Trong ví dụ dùng `StringRedisTemplate` mặc định, chuỗi được chuyển thành byte bằng UTF-8. Nếu ứng dụng tùy biến serializer, nên dùng serializer phù hợp thay cho `getBytes(...)`.

Đây là một giao dịch **chủ động hủy**, vì vậy không có `exec()` ở cuối callback. Tránh viết luồng điều khiển mà sau khi gọi `discard()` vẫn rơi xuống nhánh `exec()`.

### Vì sao không gọi `multi` rồi `discard` trên template thành các thao tác rời?

Ví dụ sau khó bảo đảm cùng một connection:

~~~java
// KHÔNG nên coi đây là mẫu giao dịch an toàn:
redis.multi();
redis.opsForValue().set("demo:key", "value");
redis.discard();
~~~

`RedisTemplate` có cơ chế lấy và giải phóng Redis connection cho từng lời gọi, trừ khi đang ở một ngữ cảnh ràng buộc connection phù hợp. Tách lệnh như trên có thể khiến chuỗi thao tác không nằm trên một connection giao dịch nhất quán.

Với nhóm thao tác dùng API template cấp cao, **`SessionCallback`** là cách quen thuộc để ghim cùng một Redis connection trong suốt phiên xử lý. Với ví dụ muốn trực tiếp điều khiển các lệnh Redis ở mức connection, `RedisCallback` trình bày rõ ràng hơn và tránh nhầm lẫn về phiên giao dịch.

## 5. Quyết định hủy trước hay sau khi mở `MULTI`?

Không phải cứ từ chối một yêu cầu nghiệp vụ là cần gửi `DISCARD`.

**Trường hợp A — điều kiện không đạt trước `MULTI`:** Chưa có giao dịch nào bắt đầu. Chỉ cần dừng xử lý, không gọi `DISCARD`.

~~~java
if (!request.isValid()) {
    return; // Chưa MULTI, không cần DISCARD.
}

// Chỉ mở giao dịch nếu có lý do tiếp tục chuẩn bị ghi.
~~~

**Trường hợp B — đã `MULTI`, chưa `EXEC`:** Có lệnh đang chờ, ứng dụng quyết định hủy. Khi đó gọi `DISCARD` trên cùng connection.

**Trường hợp C — đã `EXEC`:** Dữ liệu có thể đã thay đổi. Muốn sửa sai phải thực hiện hành động bù trừ thích hợp hoặc thiết kế quy trình khôi phục; `DISCARD` không phải giải pháp.

Sơ đồ quyết định:

~~~text
            Có cần tiếp tục nghiệp vụ?
                      |
            +---------+---------+
            |                   |
           Không                Có
            |                   |
    Đã mở MULTI chưa?      Kiểm tra/trang bị
       /          \         các điều kiện cần
      /            \              |
    Chưa           Rồi            v
     |              |           MULTI
     v              v             |
  Dừng xử lý      DISCARD         v
                           Xếp lệnh Redis
                                  |
                          Có cần hủy không?
                            /           \
                           Có           Không
                            |             |
                            v             v
                          DISCARD        EXEC
~~~

Một thiết kế rõ ràng thường kiểm tra được càng nhiều điều kiện nghiệp vụ **trước `MULTI`** càng tốt. Điều này giảm thời gian giữ connection ở trạng thái giao dịch và giảm số lần phải dọn bỏ hàng đợi.

## 6. Cấu trúc mã để tránh bỏ quên giao dịch đang mở

Lỗi phổ biến là `multi()` rồi ném exception hoặc `return` sớm mà không gọi `exec()` hay `discard()`. Một connection còn ở trạng thái MULTI có thể gây những hành vi khó dự đoán nếu được tái sử dụng.

Vì vậy, khi tự quản lý giao dịch bằng connection callback, nên xây dựng luồng điều khiển với một điểm kết thúc rõ ràng: **hoặc thực thi, hoặc hủy**.

Ví dụ với nhánh hủy **trước lúc thực thi**:

~~~java
public void cancelWhenNotApproved(
        String key, String value, boolean approved) {

    redis.execute((RedisCallback<Void>) connection -> {
        byte[] k = key.getBytes(StandardCharsets.UTF_8);
        byte[] v = value.getBytes(StandardCharsets.UTF_8);

        connection.multi();
        boolean stillOpen = true;

        try {
            connection.stringCommands().set(k, v);

            if (!approved) {
                connection.discard();
                stillOpen = false;
                return null;
            }

            // Nhánh quyết định thực thi.
            // Sau khi phát EXEC, không thể coi DISCARD là rollback.
            stillOpen = false;
            connection.exec();
            return null;
        } finally {
            // Dọn hàng đợi nếu lỗi xảy ra TRƯỚC khi gửi EXEC.
            if (stillOpen) {
                connection.discard();
            }
        }
    });
}
~~~

Trong ví dụ này, `stillOpen` chỉ dùng để xác định nhánh cần dọn hàng đợi trước `EXEC`. Nếu `exec()` đã được gửi rồi bị lỗi kết nối hoặc timeout, trạng thái thực thi có thể **không chắc chắn**: server có thể đã nhận và chạy các lệnh trong khi client không nhận được phản hồi. Không được tự kết luận rằng lỗi client đồng nghĩa với rollback hoặc lập tức thực thi lại một giao dịch không idempotent.

Đối với code production, cần thêm chiến lược quan sát kết quả, retry có kiểm soát, khóa định danh/idempotency key hoặc đối soát trạng thái tùy nghiệp vụ. Việc xử lý ngoại lệ của Redis connection và bảo đảm trả connection sạch cho pool cũng phải phù hợp driver được sử dụng.

### Phân biệt lỗi chuẩn bị và lỗi sau `EXEC`

| Thời điểm lỗi | Điều gì có thể xảy ra? | Cách xử lý |
| --- | --- | --- |
| Trước `MULTI` | Chưa có Redis transaction | Dừng xử lý, không cần `DISCARD` |
| Sau `MULTI`, trước `EXEC` | Có thể còn lệnh đã `QUEUED` | `DISCARD` nếu connection còn dùng được; báo lỗi gốc |
| Khi `DISCARD` thất bại | Connection/Redis có vấn đề | Báo lỗi, không giả định đã dọn thành công |
| Sau khi phát `EXEC` | Redis có thể đã chạy một phần hoặc toàn bộ chuỗi theo quy tắc lỗi của Redis | Kiểm tra kết quả và trạng thái thực tế; không gọi `DISCARD` như rollback |
| Khi lỗi xảy ra ở hệ thống khác | Không nằm trong phạm vi Redis transaction | Thiết kế bù trừ hoặc điều phối nghiệp vụ riêng |

## 7. `DISCARD` so với rollback sau `EXEC`

Redis transaction có tính chất quan trọng: khi `EXEC` được chấp nhận, Redis thực thi các lệnh trong hàng đợi theo thứ tự và không chen lệnh của client khác vào giữa chuỗi đó. Tuy nhiên, nó **không có rollback tổng quát** cho lỗi phát sinh khi các lệnh đang được thực thi.

Giả sử một giao dịch:

~~~redis
SET demo:counter "not-a-number"
MULTI
INCR demo:counter
SET demo:flag "created"
EXEC
~~~

`INCR` sẽ thất bại do `demo:counter` không chứa số nguyên hợp lệ. Nhưng `SET demo:flag "created"` vẫn có thể được thực thi trong cùng lệnh `EXEC`. Redis trả về danh sách kết quả có một phần tử là lỗi, chứ không tự hoàn tác toàn bộ các thay đổi khác vì lỗi lúc chạy.

Đây là khác biệt rất lớn so với kỳ vọng rằng “giao dịch nào cũng rollback tất cả nếu một lệnh lỗi”. `DISCARD` tránh việc chạy cả hàng đợi **nếu được gọi trước `EXEC`**; nó không giải quyết lỗi xuất hiện trong quá trình `EXEC`.

Cũng cần phân biệt **lỗi khi đưa lệnh vào hàng đợi**. Với Redis hiện đại, nếu có lỗi cú pháp hoặc loại lệnh khiến lệnh không thể được xếp hàng đúng trong chế độ `MULTI`, `EXEC` thường bị từ chối bằng lỗi như `EXECABORT`. Ứng dụng đã biết có lỗi chuẩn bị nên chủ động hủy giao dịch bằng `DISCARD` thay vì vẫn cố thực thi.

## 8. `WATCH`, `UNWATCH` và `DISCARD`

Trong bài toán kiểm soát cập nhật đồng thời, `WATCH` giúp theo dõi một hoặc nhiều key trước `MULTI`. Redis chỉ thực thi `EXEC` nếu những key được theo dõi không bị client khác sửa đổi theo điều kiện của cơ chế optimistic locking.

Luồng minh họa:

~~~text
Connection A                         Connection B
     |                                    |
 WATCH stock:sku-42                       |
     |                                    |
 GET stock:sku-42                         |
     |                            SET stock:sku-42 ...
     |                                    |
 MULTI                                    |
 DECRBY stock:sku-42 2                   |
     |                                    |
 EXEC  --------------------> Không thực thi do WATCH conflict
~~~

Nếu một key đã `WATCH` bị thay đổi trước `EXEC`, giao dịch được Redis **hủy khi thực thi** theo quy tắc của `WATCH`; client thường nhận kết quả `EXEC` rỗng kiểu nil/null để biểu thị việc thực thi không diễn ra vì xung đột. Không nên xem kết quả này giống danh sách kết quả thành công của các lệnh.

Trong quy trình đó:

- **`UNWATCH`**: bỏ theo dõi key nếu ứng dụng dừng xử lý **trước khi mở `MULTI`**.
- **`DISCARD`**: hủy các lệnh đang xếp hàng **sau khi đã mở `MULTI`**, đồng thời bỏ trạng thái WATCH.
- **`EXEC`**: yêu cầu thực thi; Redis tự từ chối nếu điều kiện WATCH không còn thỏa.

Ví dụ Redis CLI:

~~~redis
WATCH demo:balance
GET demo:balance
~~~

Nếu ứng dụng kiểm tra và quyết định không giao dịch:

~~~redis
UNWATCH
~~~

Nếu ứng dụng đã chuyển sang giai đoạn giao dịch:

~~~redis
WATCH demo:balance
MULTI
DECRBY demo:balance 100
DISCARD
~~~

Sau `DISCARD`, lệnh `DECRBY` không chạy và WATCH cũng được bỏ. Một connection mới bắt đầu các thao tác thông thường không thừa hưởng trạng thái WATCH đó.

**WATCH không phải cơ chế giữ khóa độc quyền.** Client khác vẫn có thể thay đổi key. Đây là cách Redis nhận biết xung đột và từ chối một `EXEC` không còn hợp lệ. Khi có xung đột, ứng dụng thường cần đọc lại trạng thái và quyết định thử lại theo giới hạn nhất định.

## 9. `@Transactional` và `DISCARD` do Spring quản lý

Trong Spring, annotation `@Transactional` điều khiển **giao dịch của transaction manager được cấu hình**. Không nên giả định chỉ thêm `@Transactional` lên service là mọi lời gọi `StringRedisTemplate` tự động chạy trong Redis `MULTI/EXEC`.

Spring Data Redis có cơ chế tham gia vào giao dịch Spring đang tồn tại khi bật transaction support cho template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
class RedisTemplateConfiguration {

    @Bean
    StringRedisTemplate transactionalRedisTemplate(
            RedisConnectionFactory factory) {
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
~~~

Khi có một Spring transaction thực sự đang được quản lý, các lệnh ghi Redis có thể được đưa vào hàng đợi và Spring Data Redis gửi `EXEC` khi transaction hoàn tất thành công hoặc `DISCARD` khi rollback. Ví dụ minh họa:

~~~java
@Transactional
public void reserveOrder(String orderId) {
    redis.opsForValue().set("order:" + orderId, "RESERVED");

    if (!allowedToReserve(orderId)) {
        throw new IllegalStateException("Reservation not allowed");
    }
}
~~~

Ví dụ này **giả định** ứng dụng đã có `PlatformTransactionManager` thích hợp và template được bật transaction support, đồng thời lời gọi đang đi qua proxy giao dịch Spring. Spring Data Redis không cung cấp sẵn một `RedisTransactionManager` chuyên biệt để chỉ cần đánh dấu `@Transactional` là xong.

Trong chế độ transaction-managed:

- Spring quyết định commit/rollback dựa trên transaction boundary và các quy tắc rollback.
- Template tham gia transaction để thực hiện `MULTI`, `EXEC` hoặc `DISCARD` theo lifecycle.
- **Không nên tự gọi `discard()` trong cùng luồng đã giao quyền điều khiển transaction cho Spring**, vì có thể làm lệch trạng thái connection và logic transaction synchronization.
- Các lệnh đọc có thể được Spring Data Redis chuyển sang connection khác vì kết quả từ connection đang `MULTI` chỉ là `QUEUED`; vì vậy cách đọc dữ liệu trong transaction cần hiểu đúng.

Nếu transaction chính được quản lý bởi JDBC/JPA, việc Spring Data Redis tham gia **không biến hai kho dữ liệu thành một giao dịch phân tán nguyên tử**. Một phía có thể commit trong khi phía kia gặp lỗi. Những nghiệp vụ nhiều tài nguyên cần thiết kế điều phối, outbox, idempotency hoặc bù trừ phù hợp.

## 10. `DISCARD` không giống pipeline, Lua hay thao tác bù trừ

Các cơ chế này đều có thể xuất hiện trong một ứng dụng Redis nhưng giải quyết những vấn đề khác nhau:

| Cơ chế | Mục đích | Có hủy lệnh đã thực thi không? |
| --- | --- | --- |
| `MULTI` + `DISCARD` | Hủy hàng đợi transaction trước `EXEC` | Không |
| `MULTI` + `EXEC` | Thực thi tuần tự các lệnh đã xếp hàng | Không có rollback tổng quát |
| `WATCH` | Phát hiện xung đột trước khi `EXEC` | Ngăn `EXEC` khi key bị thay đổi; không đảo ngược lệnh đã chạy |
| Pipelining | Giảm số lượt round-trip mạng bằng cách gửi lệnh theo lô | Không phải cơ chế rollback hay transaction tự động |
| Lua script / Redis Functions | Đưa logic vào phía Redis để thực thi tập trung/atomic theo ngữ nghĩa Redis | Không có rollback SQL tự động cho mọi lỗi khi script đang chạy |
| Thao tác bù trừ | Sửa/đảo một tác động đã xảy ra theo quy tắc nghiệp vụ | Là thao tác mới; cần thiết kế và kiểm soát rủi ro |

Không thể dựa vào `DISCARD` để “hủy pipeline” sau khi các lệnh pipeline đã đến Redis và được thực thi. Pipelining là tối ưu hóa việc truyền lệnh; nó không mặc nhiên chuyển lệnh thành hàng đợi của `MULTI`.

Nếu một quyết định nghiệp vụ phải dựa trên kết quả của chính các lệnh trong nhóm thao tác, cần lưu ý rằng **không thể đọc kết quả của `GET` đang `QUEUED` trước `EXEC` rồi dùng nó để quyết định có `DISCARD` hay không**. Với Redis CLI, lệnh `GET` trong `MULTI` trả `QUEUED`; trong Spring Data Redis, một số API trả về `null` hoặc giá trị placeholder trong thời gian queueing, không phải giá trị Redis thực.

Với kiểm tra-điều kiện-ghi cần atomicity, hãy cân nhắc `WATCH` + retry, script Lua hoặc một thiết kế key/cấu trúc dữ liệu thích hợp, thay vì kỳ vọng kiểm tra giá trị mới ngay bên trong `MULTI`.

## 11. Kiểm thử tích hợp: lệnh đã `QUEUED` không làm thay đổi key sau `DISCARD`

Để kiểm chứng hành vi, nên dùng Redis thực trong kiểm thử tích hợp. Kiểm thử bằng mock `RedisTemplate` chỉ chứng minh phương thức `discard()` đã được gọi, không chứng minh Redis thật có bỏ hàng đợi.

Ví dụ dùng Spring Boot, JUnit 5, AssertJ và Testcontainers:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

**Kiểm thử**:

~~~java
package com.example.redis.transaction;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = RedisDiscardIntegrationTest.TestApp.class)
class RedisDiscardIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void discardPreventsQueuedWriteFromExecuting() {
        String key = "test:discard:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(key, "before");

            redis.execute((RedisCallback<Void>) connection -> {
                byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);
                byte[] rawValue =
                    "after".getBytes(StandardCharsets.UTF_8);

                connection.multi();
                connection.stringCommands().set(rawKey, rawValue);
                connection.discard();
                return null;
            });

            // Giá trị vẫn là "before", vì SET "after" bị hủy.
            assertThat(redis.opsForValue().get(key))
                .isEqualTo("before");
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void execAppliesQueuedWriteForComparison() {
        String key = "test:exec:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(key, "before");

            redis.execute((RedisCallback<Void>) connection -> {
                connection.multi();
                connection.stringCommands().set(
                    key.getBytes(StandardCharsets.UTF_8),
                    "after".getBytes(StandardCharsets.UTF_8)
                );
                connection.exec();
                return null;
            });

            assertThat(redis.opsForValue().get(key))
                .isEqualTo("after");
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Hai bài kiểm thử sử dụng key có UUID để tránh đụng nhau khi chạy song song. Test đầu xác nhận `DISCARD` giữ nguyên giá trị; test thứ hai đặt đối chứng với `EXEC` để thấy sự khác nhau của hai cách kết thúc. Máy chạy cần Docker hoặc môi trường container tương thích.

Trong dự án có serializer tùy biến, nên dùng cùng serializer khi chuyển key/value thành bytes thay vì tự gọi `getBytes(UTF_8)`. Khi dùng một Spring application context có giao dịch Spring đang hoạt động, cần tách biệt bài kiểm thử giao dịch quản lý thủ công khỏi cơ chế transaction support của template để không tạo hai nguồn điều khiển cùng một connection.

## 12. Những lỗi phổ biến cần nhận diện

| Hiện tượng | Nguyên nhân thường gặp | Cách giải quyết |
| --- | --- | --- |
| `DISCARD` báo `without MULTI` | Chưa mở `MULTI` hoặc giao dịch đã kết thúc | Chỉ gọi `DISCARD` khi còn transaction đang mở trên connection hiện tại |
| Gọi `DISCARD` rồi dữ liệu vẫn đổi | Lệnh được thực thi trước `MULTI`, trên connection khác hoặc đã `EXEC` | Xác định chính xác ranh giới và connection |
| `MULTI` được gọi nhưng lệnh sau không `QUEUED` | Lời gọi không dùng cùng connection hoặc cơ chế template chưa đúng | Dùng `SessionCallback` hoặc `RedisCallback` phù hợp |
| Dùng `GET` trong `MULTI` nhưng nhận `null`/`QUEUED` | Lệnh đọc đang trong hàng đợi | Đọc trước `MULTI` hoặc dùng cách kiểm soát đồng thời phù hợp |
| `EXEC` có lỗi nhưng một số key vẫn đổi | Lỗi thực thi lệnh Redis không luôn kéo theo rollback | Kiểm soát dữ liệu đầu vào và xử lý kết quả từng lệnh |
| Exception giữa `MULTI` và `EXEC` khiến connection còn mở giao dịch | Không có nhánh cleanup | Thêm `DISCARD` trên đường hủy/lỗi trước khi thực thi |
| Giao dịch hủy nhưng hệ thống khác đã ghi dữ liệu | `DISCARD` chỉ áp dụng cho Redis queued commands | Thiết kế giao dịch nhiều tài nguyên/bù trừ riêng |
| `@Transactional` không tự hủy Redis write | Redis template chưa tham gia transaction hoặc boundary không phù hợp | Cấu hình transaction support và hiểu transaction manager thực tế |
| Gọi `DISCARD` sau lỗi timeout khi `EXEC` | Client không biết chắc server đã thực thi chưa | Đối soát trạng thái; dùng idempotency, không giả định rollback |
| Kỳ vọng `DISCARD` hủy pipeline | Pipelining và transaction khác nhau | Dùng `MULTI` nếu cần queueing giao dịch trước `EXEC` |

## 13. Vận dụng trong thiết kế nghiệp vụ

Giả sử một API chuẩn bị nhiều thay đổi Redis để đăng ký phiên xử lý:

~~~text
1. Kiểm tra dữ liệu đầu vào và quyền truy cập
2. Mở MULTI
3. Xếp lệnh SET session:<id>, SADD user:sessions:<userId>
4. Nếu phát hiện không thể tiếp tục trước EXEC → DISCARD
5. Nếu điều kiện đã thỏa và quyết định commit → EXEC
6. Kiểm tra kết quả và trả response tương ứng
~~~

Một số nguyên tắc thiết kế:

- **Kiểm tra trước khi xếp hàng khi có thể.** Giảm thời gian ở trong trạng thái `MULTI` và tránh phải hủy.
- **Gắn giao dịch với một connection.** Dùng callback hoặc transaction context phù hợp trong Spring Data Redis.
- **Tách riêng hai đường kết thúc.** Mỗi giao dịch tự quản lý phải đi tới `EXEC` hoặc `DISCARD`, không vô tình cả hai.
- **Không dựa vào giá trị trả về của lệnh đang QUEUED để ra quyết định.** Thực hiện kiểm tra trước giao dịch hoặc dùng cơ chế concurrency đúng.
- **Đặt ranh giới hiệu lực rõ ràng.** `DISCARD` chỉ bảo đảm không chạy những lệnh đã xếp hàng trong transaction đó.
- **Thiết kế xử lý lỗi sau commit.** `EXEC` có thể đã chạy ngay cả khi client gặp timeout; tránh retry mù các lệnh tăng/giảm hoặc tạo tài nguyên.
- **Kiểm thử bằng Redis thật khi cần chứng minh hành vi giao dịch.** So sánh trạng thái trước và sau `DISCARD` thay vì chỉ kiểm tra mock được gọi.

`DISCARD` là cách sạch và rõ ràng để **bỏ toàn bộ lệnh đang chờ trong một giao dịch Redis chưa thực thi**. Trong Spring Data Redis, sử dụng nó đúng nghĩa đòi hỏi hiểu trạng thái connection, ranh giới `MULTI/EXEC`, khác biệt giữa lỗi trước và sau thực thi, và cách Spring có thể quản lý transaction thay cho mã thủ công. Khi những ranh giới này được thiết kế rõ, ứng dụng có thể hủy thao tác đúng lúc mà không vô tình phát sinh thay đổi dữ liệu Redis.
