# Ảnh hưởng của save mode đến ghi đè giữa các yêu cầu đồng thời

## Mục tiêu bài học

Spring Session cho phép nhiều request cùng sử dụng một session, kể cả khi các request được xử lý trên những instance Spring khác nhau. Mỗi request có thể tải một bản trạng thái session, đọc thuộc tính, thay đổi dữ liệu rồi lưu lại. Khi hai request chồng lấn, cả hai có thể ghi các snapshot khác nhau của cùng session. Nếu không hiểu cách repository chọn thuộc tính để lưu, một request có thể vô tình ghi đè thay đổi mà request kia vừa thực hiện.

Spring Session cung cấp `SaveMode` để xác định thuộc tính nào được đưa vào quá trình lưu session. Save mode ảnh hưởng đến phạm vi dữ liệu có thể bị ghi đè, nhưng không tự giải quyết xung đột khi hai request cùng sửa một thuộc tính.

Sau bài học, bạn có thể:

- Giải thích vì sao các request đồng thời có thể giữ những snapshot session khác nhau.
- Phân biệt `SaveMode.ON_SET_ATTRIBUTE`, `ON_GET_ATTRIBUTE` và `ALWAYS`.
- Dự đoán nguy cơ ghi đè khi các request sửa thuộc tính khác nhau hoặc cùng một thuộc tính.
- Hiểu quan hệ giữa save mode và flush mode.
- Viết code cập nhật session rõ ràng bằng `setAttribute` và `removeAttribute`.
- Chọn nơi lưu phù hợp cho bộ đếm và dữ liệu nghiệp vụ cần cập nhật nguyên tử.
- Thiết kế optimistic locking, atomic operation hoặc distributed lock khi cần.
- Kiểm thử race condition trên Redis/JDBC bằng cùng Session ID.

## 1. Vì sao request đồng thời có thể ghi đè session?

Một session thường được truy cập qua nhiều request. Người dùng có thể mở nhiều tab, trình duyệt gửi request nền, frontend gọi nhiều API song song hoặc load balancer chuyển request đến nhiều instance.

Giả sử session chứa:

~~~text
cart = { itemCount: 1 }
theme = "light"
locale = "vi"
~~~

Hai request A và B cùng mang một Session ID. Chúng có thể tải session gần như cùng thời điểm:

- A tải snapshot S0.
- B tải snapshot S0.
- A đổi giỏ hàng rồi lưu.
- B đổi theme rồi lưu.

Mỗi request làm việc trên trạng thái mà nó đã tải. B không tự động nhận được thay đổi mới nhất mà A vừa ghi. Nếu B lưu toàn bộ snapshot S0 đã sửa, dữ liệu giỏ hàng mới của A có thể bị ghi đè.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant R as Session Repository
    participant B as Request B

    A->>R: Load session S0
    B->>R: Load session S0
    Note over A,B: Hai request giữ hai snapshot riêng
    A->>A: Update cart
    B->>B: Update theme
    A->>R: Save session
    R-->>A: Cart đã cập nhật
    B->>R: Save session snapshot
    R-->>B: Theme đã cập nhật
    Note over R: Nếu B ghi cả snapshot cũ,<br/>cart của A có thể bị ghi đè
~~~

Đây là dạng lost update: một thay đổi đã được lưu nhưng bị một lần ghi khác dựa trên dữ liệu cũ thay thế.

Tình huống này có thể xảy ra trong một JVM và cũng có thể xảy ra giữa nhiều instance. Redis hoặc JDBC là kho chia sẻ, nhưng việc dùng chung kho dữ liệu không tự biến các thao tác đọc-sửa-ghi thành một transaction nguyên tử.

## 2. SaveMode điều khiển điều gì?

`SaveMode` xác định tập thuộc tính session được đưa vào quá trình lưu khi session được save. Nó ảnh hưởng đến phạm vi ghi dữ liệu và do đó ảnh hưởng đến khả năng một request ghi đè thuộc tính do request khác cập nhật.

Ba chế độ phổ biến:

| Save mode | Thuộc tính được đưa vào lần lưu | Đặc điểm |
|---|---|---|
| `ON_SET_ATTRIBUTE` | Thuộc tính được đặt qua `setAttribute` trong request hiện tại; các thay đổi thuộc tính được repository theo dõi | Giảm việc ghi lại những thuộc tính chỉ được đọc hoặc không thay đổi |
| `ON_GET_ATTRIBUTE` | Thuộc tính được đọc qua `getAttribute` hoặc được đặt trong request | Hỗ trợ trường hợp object khả biến được sửa sau khi đọc mà không gọi lại setAttribute |
| `ALWAYS` | Tất cả thuộc tính session | Cách lưu rộng nhất; dễ ghi lại snapshot cũ và tăng lượng dữ liệu được ghi |

Trong nhiều cấu hình Spring Session hiện đại, `ON_SET_ATTRIBUTE` là lựa chọn mặc định. Hãy kiểm tra mặc định và khả năng hỗ trợ của repository trong phiên bản đang dùng.

Save mode không phải cơ chế khóa, không so sánh version của snapshot và không tự hợp nhất hai thay đổi. Nó chỉ quyết định thuộc tính nào được đưa vào lần lưu.

### Thuộc tính được theo dõi như thế nào?

Với `ON_SET_ATTRIBUTE`, ứng dụng nên biểu đạt rõ thay đổi bằng API session:

~~~java
session.setAttribute("cart", updatedCart);
session.removeAttribute("temporarySelection");
~~~

Nếu chỉ lấy một object khả biến ra rồi sửa field bên trong, repository có thể không nhận biết rằng thuộc tính đã thay đổi theo cách bạn mong đợi.

Ví dụ:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.setItemCount(cart.getItemCount() + 1);

// Đặt lại thuộc tính để đánh dấu thay đổi rõ ràng.
session.setAttribute("cart", cart);
~~~

Thiết kế tốt hơn thường là dùng object bất biến hoặc tạo một snapshot mới, sau đó gọi `setAttribute`. Điều này làm rõ thời điểm thay đổi và giảm phụ thuộc vào việc phát hiện mutation bên trong object.

## 3. ON_SET_ATTRIBUTE: chỉ lưu thuộc tính được thay đổi

`SaveMode.ON_SET_ATTRIBUTE` giới hạn việc lưu vào những thuộc tính được đặt trong request thông qua API session. Đây thường là lựa chọn phù hợp khi muốn giảm ghi đè giữa các request sửa các thuộc tính khác nhau.

Giả sử hai request cùng tải:

~~~text
S0:
cart = C0
theme = light
locale = vi
~~~

Request A:

~~~java
session.setAttribute("cart", updatedCart);
~~~

Request B:

~~~java
session.setAttribute("theme", "dark");
~~~

Với `ON_SET_ATTRIBUTE`, A chỉ cần lưu thuộc tính cart mà nó đã thay đổi, B chỉ cần lưu theme. Khi repository hỗ trợ cập nhật thuộc tính theo cách tương ứng, thay đổi ở hai thuộc tính độc lập có thể cùng tồn tại thay vì request cuối ghi lại toàn bộ snapshot.

### Timeline khi thay đổi thuộc tính khác nhau

| Thời điểm | Request A | Request B | Repository |
|---|---|---|---|
| T1 | Đọc cart=C0, theme=light | | S0 |
| T2 | | Đọc cart=C0, theme=light | S0 |
| T3 | Đặt cart=C1 | | S0 |
| T4 | | Đặt theme=dark | S0 |
| T5 | Lưu cart=C1 | | cart=C1, theme=light |
| T6 | | Lưu theme=dark | cart=C1, theme=dark |

Save mode này giảm việc B ghi lại cart cũ khi B chỉ thay theme.

Tuy nhiên, kết quả phụ thuộc repository và phiên bản triển khai. Hãy kiểm thử với Redis/JDBC repository thực tế, đặc biệt khi dùng custom repository hoặc custom session implementation.

### ON_SET_ATTRIBUTE không bảo vệ cùng một thuộc tính

Nếu cả A và B đều sửa cart:

- A tải C0 và tạo C1.
- B tải C0 và tạo C2.
- A lưu C1.
- B lưu C2.

Cả hai đều gọi `setAttribute("cart", ...)`. Vì vậy cả hai đều có quyền ghi thuộc tính cart theo snapshot riêng. Lần ghi sau có thể thay thế lần ghi trước.

`ON_SET_ATTRIBUTE` không biết rằng C2 được tính từ C0 đã cũ. Nó không phát hiện xung đột logic và không tự merge hai giỏ hàng.

Đây là giới hạn quan trọng nhất cần nhớ: save mode giảm ghi đè thuộc tính không thay đổi, nhưng không giải quyết xung đột trên cùng một thuộc tính.

## 4. ON_GET_ATTRIBUTE: lưu cả thuộc tính được đọc

`SaveMode.ON_GET_ATTRIBUTE` đưa vào lần lưu các thuộc tính được đọc qua `getAttribute`, cùng với các thuộc tính được đặt trong request.

Chế độ này hữu ích khi ứng dụng lưu object khả biến và thay đổi object sau khi đọc mà không gọi lại `setAttribute`.

Ví dụ:

~~~java
Cart cart = (Cart) session.getAttribute("cart");

// Sửa object đã lấy từ session.
cart.setItemCount(cart.getItemCount() + 1);

// Không gọi session.setAttribute("cart", cart).
~~~

Với `ON_SET_ATTRIBUTE`, thay đổi bên trong object có thể không được ghi vì thuộc tính chưa được đánh dấu là đã đặt trong request. Với `ON_GET_ATTRIBUTE`, việc đọc cart làm thuộc tính đó nằm trong tập được lưu, do đó thay đổi bên trong object có thể được ghi lại.

### Rủi ro stale read

Cùng hành vi đó có thể làm tăng nguy cơ ghi đè snapshot cũ.

Ví dụ:

1. A tải cart=C0.
2. B tải cart=C0.
3. B thay cart thành C1 và lưu.
4. A chỉ đọc cart, sau đó thay đổi một thuộc tính khác.
5. Vì A đã đọc cart, `ON_GET_ATTRIBUTE` đưa cart=C0 vào lần lưu của A.
6. Nếu A lưu sau B, cart=C1 có thể bị thay bằng C0.

A không chủ ý sửa cart nhưng việc đọc thuộc tính khiến nó được đưa vào tập lưu. Vì vậy, `ON_GET_ATTRIBUTE` có thể làm tăng lượng dữ liệu ghi và tạo thêm cơ hội ghi đè dữ liệu mới bằng snapshot cũ.

Chọn chế độ này khi thật sự cần hỗ trợ mutation bên trong object và đã đánh giá tác động đồng thời. Nếu có thể, hãy sửa code để dùng object bất biến hoặc gọi `setAttribute` sau mutation.

## 5. ALWAYS: lưu tất cả thuộc tính

`SaveMode.ALWAYS` yêu cầu repository lưu tất cả thuộc tính session mỗi khi session được lưu.

Ưu điểm là đơn giản đối với ứng dụng có object khả biến và không muốn phụ thuộc vào việc theo dõi thuộc tính được đọc hoặc được đặt. Tuy nhiên, đây là chế độ có phạm vi ghi rộng nhất.

### Nguy cơ ghi đè snapshot

Giả sử A và B tải cùng S0:

- A đổi cart thành C1.
- B đổi theme thành dark.
- A lưu toàn bộ thuộc tính.
- B lưu toàn bộ snapshot của nó, trong đó cart vẫn là C0.

Sau khi B lưu, cart có thể trở về C0 dù A đã ghi C1. B chỉ định đổi theme nhưng thao tác lưu toàn bộ snapshot làm mất thay đổi của A.

`ALWAYS` cũng làm tăng serialization, số byte ghi và tải database/Redis. Khi session có nhiều thuộc tính hoặc object lớn, chi phí này có thể đáng kể.

Không nên chọn `ALWAYS` chỉ vì nó làm một lỗi mutation biến mất. Hãy đo chi phí và kiểm tra các request đồng thời trước khi áp dụng.

## 6. So sánh ba chế độ qua các tình huống

| Tình huống | ON_SET_ATTRIBUTE | ON_GET_ATTRIBUTE | ALWAYS |
|---|---|---|---|
| Request chỉ đọc thuộc tính | Thường không ghi lại thuộc tính chỉ đọc | Thuộc tính đã đọc được đưa vào tập lưu | Tất cả thuộc tính được lưu |
| Request gọi setAttribute | Lưu thuộc tính được đặt | Lưu thuộc tính được đặt | Lưu toàn bộ thuộc tính |
| Sửa object khả biến sau getAttribute, không set lại | Có thể không lưu thay đổi bên trong | Có thể lưu vì thuộc tính đã được đọc | Lưu toàn bộ object |
| Hai request sửa hai thuộc tính khác nhau | Giảm nguy cơ ghi đè chéo | Có thể ghi lại thuộc tính đọc nhưng không đổi | Có nguy cơ ghi đè chéo cao hơn |
| Hai request sửa cùng một thuộc tính | Vẫn có thể last-write-wins | Vẫn có thể last-write-wins | Vẫn có thể last-write-wins |
| Lượng dữ liệu ghi | Thường thấp hơn | Phụ thuộc số thuộc tính đọc/đặt | Thường cao nhất |

Bảng mô tả nguyên tắc chung. Chi tiết cách repository phát hiện thuộc tính, ghi xóa thuộc tính và cập nhật metadata có thể khác theo implementation. Cần xác minh hành vi thực tế của Redis, JDBC hoặc custom repository đang dùng.

### Ví dụ về cùng một thuộc tính

Giả sử thuộc tính visits bắt đầu bằng 0. Hai request cùng thực hiện:

~~~java
Integer visits = (Integer) session.getAttribute("visits");
session.setAttribute("visits", visits + 1);
~~~

Cả A và B có thể đọc 0 rồi cùng ghi 1. Kết quả cuối có thể là 1 thay vì 2, dù dùng `ON_SET_ATTRIBUTE`.

Lý do là cả hai request đều ghi cùng thuộc tính với giá trị tính từ cùng snapshot cũ. Save mode không thực hiện phép cộng nguyên tử và không biết giá trị 1 của request B cần được cộng tiếp lên giá trị 1 mà A đã ghi.

## 7. SaveMode khác FlushMode như thế nào?

`SaveMode` và `FlushMode` giải quyết hai câu hỏi khác nhau:

- Save mode: thuộc tính nào được đưa vào lần lưu?
- Flush mode: thay đổi được ghi xuống repository vào thời điểm nào?

Hai lựa chọn phổ biến của flush mode:

| Flush mode | Hành vi tổng quát |
|---|---|
| `FlushMode.ON_SAVE` | Gom thay đổi và ghi khi session được lưu, thường trong quá trình hoàn tất request |
| `FlushMode.IMMEDIATE` | Đẩy thay đổi xuống repository sớm ngay khi có thao tác cập nhật |

Ví dụ:

~~~java
@EnableRedisHttpSession(
    saveMode = SaveMode.ON_SET_ATTRIBUTE,
    flushMode = FlushMode.ON_SAVE
)
class SessionConfiguration {
}
~~~

Cấu hình này giới hạn tập thuộc tính theo dõi và gom thay đổi đến lúc lưu session.

Nếu chuyển sang `FlushMode.IMMEDIATE`, thay đổi có thể xuất hiện trong repository sớm hơn, nhưng điều đó không biến chuỗi đọc-sửa-ghi thành atomic operation. A và B vẫn có thể đọc cùng giá trị cũ rồi ghi hai kết quả khác nhau.

### Vì sao flush mode cũng ảnh hưởng cảm nhận race?

Với `ON_SAVE`, nhiều thay đổi trong request có thể được ghi khi request kết thúc. Hai request có thể hoàn tất theo thứ tự khác với thứ tự bắt đầu.

Với `IMMEDIATE`, một thay đổi có thể được ghi giữa lúc request khác vẫn đang xử lý. Điều này thay đổi thứ tự quan sát được của các lần ghi, nhưng không có nghĩa repository tự khóa session hoặc hợp nhất dữ liệu.

Không chọn flush mode để thay thế chiến lược đồng bộ. Hãy chọn theo yêu cầu độ trễ ghi, số lần ghi và hành vi repository, rồi xử lý race ở tầng dữ liệu cần tính đúng đắn.

## 8. Cấu hình SaveMode cho Redis và JDBC

Spring Session cung cấp cấu hình repository để chọn save mode. Ví dụ với Redis:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SaveMode;
import org.springframework.session.FlushMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(
        saveMode = SaveMode.ON_SET_ATTRIBUTE,
        flushMode = FlushMode.ON_SAVE
)
public class RedisSessionConfiguration {
}
~~~

Với JDBC:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SaveMode;
import org.springframework.session.FlushMode;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession(
        saveMode = SaveMode.ON_SET_ATTRIBUTE,
        flushMode = FlushMode.ON_SAVE
)
public class JdbcSessionConfiguration {
}
~~~

Các ví dụ sử dụng annotation cấu hình Servlet. Không dùng chúng cho WebFlux; ứng dụng reactive có repository và API cấu hình riêng.

Nếu dùng Spring Boot auto-configuration, có thể cấu hình bằng properties được phiên bản Boot hỗ trợ thay vì bật annotation thủ công. Tên property và khả năng hỗ trợ có thể khác giữa các dòng Boot. Hãy kiểm tra configuration metadata của đúng release và tránh đăng ký đồng thời nhiều cấu hình repository.

### Cần đồng nhất cấu hình giữa các instance

Trong môi trường nhiều nút, tất cả instance nên dùng cùng save mode, flush mode, serializer và phiên bản Spring Session tương thích.

Nếu A dùng `ON_SET_ATTRIBUTE` còn B dùng `ALWAYS`, cùng một session có thể được lưu theo các quy tắc khác nhau tùy request đi đến instance nào. Điều này làm kết quả khó dự đoán và khó tái hiện.

Không nên thay save mode trong rolling deployment mà không kiểm thử tương tác giữa instance cũ và mới. Nếu cấu hình lưu thay đổi, kiểm thử cả hai chiều trong giai đoạn chuyển tiếp.

## 9. Viết code để giảm ghi đè ngoài ý muốn

Một nguyên tắc hữu ích là mỗi request chỉ cập nhật thuộc tính mà nó thực sự sở hữu và thay đổi.

Ví dụ không tốt:

~~~java
SessionState state = (SessionState) session.getAttribute("state");

state.setTheme("dark");
state.setCart(updatedCart);
state.setLocale("vi");

session.setAttribute("state", state);
~~~

Nếu state là một object lớn chứa nhiều phần dữ liệu do các request khác nhau cập nhật, một thay đổi theme có thể ghi lại cả cart cũ.

Một cách tổ chức tốt hơn là tách các thuộc tính độc lập:

~~~java
session.setAttribute("theme", "dark");
session.setAttribute("locale", "vi");
session.setAttribute("cartSnapshot", updatedCart);
~~~

Việc tách thuộc tính giúp `ON_SET_ATTRIBUTE` giới hạn tập dữ liệu cần lưu. Tuy nhiên, nếu các giá trị phải nhất quán như một đơn vị, tách thuộc tính có thể tạo trạng thái cập nhật dở dang. Khi đó, hãy lưu chúng trong một aggregate nghiệp vụ có version và cập nhật nguyên tử ở kho dữ liệu phù hợp.

### Ưu tiên object bất biến

Ví dụ DTO bất biến:

~~~java
public record CartSnapshot(int itemCount, long version) {
}
~~~

Cập nhật tạo object mới:

~~~java
CartSnapshot current =
        (CartSnapshot) session.getAttribute("cart");

CartSnapshot updated =
        new CartSnapshot(current.itemCount() + 1, current.version() + 1);

session.setAttribute("cart", updated);
~~~

Cách này làm thay đổi rõ ràng và tương thích tốt với `ON_SET_ATTRIBUTE`. Nhưng version trong ví dụ mới chỉ là dữ liệu đi kèm; nếu không có thao tác compare-and-set hoặc kiểm tra version ở kho dữ liệu, nó chưa tự ngăn lost update.

## 10. Khi nào cần atomic operation thay vì session attribute?

Không nên dùng session làm nơi duy nhất lưu dữ liệu cần cập nhật đồng thời và chính xác.

Các ví dụ thường cần atomicity:

- Bộ đếm lượt dùng hoặc số lần thử.
- Số lượng tồn kho.
- Số dư hoặc hạn mức.
- Trạng thái đơn hàng.
- Điểm thưởng.
- Giới hạn số kết nối hoặc số thiết bị.
- Trạng thái quy trình được nhiều request cập nhật.

Với bộ đếm Redis, dùng lệnh nguyên tử trên key nghiệp vụ riêng:

~~~java
Long value = stringRedisTemplate
        .opsForValue()
        .increment("metrics:login-attempts");
~~~

Lệnh increment được Redis thực hiện nguyên tử cho key đó. Đây là dữ liệu nghiệp vụ riêng của ứng dụng, không phải key nội bộ do Spring Session quản lý.

Với SQL, có thể dùng câu lệnh cập nhật nguyên tử:

~~~sql
UPDATE shopping_cart
SET item_count = item_count + 1
WHERE cart_id = :cartId;
~~~

Database thực hiện phép tăng trong một câu lệnh thay vì ứng dụng đọc giá trị rồi ghi giá trị mới dựa trên snapshot cũ.

Session có thể giữ cart ID hoặc thông tin giao diện. Trạng thái nghiệp vụ chính nên nằm ở kho dữ liệu được thiết kế cho transaction và concurrency.

## 11. Optimistic locking cho cập nhật cùng một bản ghi

Nếu hai request cần sửa cùng một aggregate và không thể dùng phép cập nhật nguyên tử đơn giản, có thể dùng optimistic locking.

Mỗi bản ghi có version. Request đọc version V, tính trạng thái mới rồi chỉ cập nhật nếu version trong database vẫn là V.

Ví dụ:

~~~sql
UPDATE shopping_cart
SET payload = :newPayload,
    version = version + 1
WHERE cart_id = :cartId
  AND version = :expectedVersion;
~~~

Nếu số hàng được cập nhật là 1, request thắng và version được tăng. Nếu số hàng là 0, một request khác đã cập nhật trước; request hiện tại cần tải lại, hợp nhất hoặc báo xung đột theo nghiệp vụ.

### Quy trình optimistic locking

1. Đọc dữ liệu cùng version.
2. Tính thay đổi trên snapshot.
3. Gửi update có điều kiện version.
4. Nếu update thành công, trả kết quả.
5. Nếu version không còn khớp, tải lại dữ liệu.
6. Áp dụng lại thao tác nếu có thể hoặc trả conflict.

Không chỉ đặt một field version trong session rồi so sánh ở Java. Việc kiểm tra và ghi version phải được thực hiện nguyên tử ở kho dữ liệu có thẩm quyền. Nếu không, hai request vẫn có thể cùng đọc một version và cùng ghi đè.

## 12. Distributed lock: chỉ dùng khi thật sự cần

Một số nghiệp vụ phức tạp cần tuần tự hóa thao tác trên một tài nguyên. Khi đó có thể cân nhắc distributed lock trong Redis hoặc hệ thống khóa chuyên dụng.

Không dùng:

~~~java
synchronized (session) {
    // Cập nhật session
}
~~~

Đối tượng session trong request A không nhất thiết là cùng một object Java với request B. Trên nhiều instance, monitor trong JVM A hoàn toàn không khóa được JVM B.

Nếu dùng distributed lock, cần thiết kế:

- Khóa có TTL để tránh giữ vô hạn khi worker chết.
- Token chủ sở hữu duy nhất.
- Cơ chế release chỉ bởi đúng chủ sở hữu.
- Timeout chờ khóa và xử lý contention.
- Fencing token hoặc cơ chế bảo vệ thao tác cũ sau khi lease hết hạn.
- Idempotency cho retry.
- Metric về thời gian chờ và số lần timeout.

Một lock đơn giản với TTL vẫn có thể gặp trường hợp worker cũ tiếp tục chạy sau khi khóa hết hạn và worker mới đã lấy khóa. Fencing token giúp kho dữ liệu từ chối thao tác của worker cũ có token thấp hơn.

Distributed lock tăng độ phức tạp và có thể giảm throughput. Nếu có thể biểu diễn nghiệp vụ bằng atomic update, optimistic locking hoặc transaction, các cách đó thường dễ kiểm soát hơn.

## 13. Cùng một thuộc tính và nhiều thuộc tính: phân tích ví dụ

Giả sử session có:

~~~text
profile = { theme: light, locale: vi }
cart = { itemCount: 1 }
~~~

Hai request:

- A thay đổi theme trong profile.
- B thay đổi locale trong profile.

Nếu cả hai cùng lưu một object profile duy nhất, chúng cùng sửa một thuộc tính session là profile. Dù save mode là `ON_SET_ATTRIBUTE`, cả hai có thể ghi toàn bộ object profile từ snapshot riêng. Thay đổi của request ghi sau có thể mất thay đổi của request trước.

Nếu tách thành hai session attributes `theme` và `locale`, `ON_SET_ATTRIBUTE` có thể giới hạn mỗi lần lưu vào đúng thuộc tính được thay đổi. Điều này giảm ghi đè chéo.

Tuy nhiên, nếu theme và locale phải được cập nhật cùng nhau theo một quy tắc nghiệp vụ, tách chúng thành hai thuộc tính có thể không phù hợp. Cần xác định ranh giới aggregate theo tính nhất quán, không tách chỉ để giảm số byte ghi.

### Bảng quyết định

| Kiểu dữ liệu | Hướng xử lý |
|---|---|
| Thuộc tính độc lập, ít phụ thuộc nhau | Tách thuộc tính và dùng ON_SET_ATTRIBUTE |
| DTO nhỏ, bất biến, request cập nhật rõ ràng | Gọi setAttribute với object mới |
| Object khả biến cần mutation tại chỗ | Cân nhắc ON_GET_ATTRIBUTE hoặc đặt lại thuộc tính; đánh giá stale overwrite |
| Nhiều request sửa cùng counter | Dùng atomic increment ngoài session |
| Aggregate cần kiểm tra xung đột | Dùng optimistic locking/version ở database |
| Tác vụ cần tuần tự hóa phức tạp | Cân nhắc distributed lock có fencing |

## 14. Kiểm thử race condition với cùng Session ID

Kiểm thử cần bảo đảm hai request thực sự dùng cùng một Session ID và có phần thực thi chồng lấn.

Một quy trình:

1. Khởi động ứng dụng với Redis hoặc JDBC repository thật.
2. Tạo session có cart=C0 và theme=light.
3. Lấy cookie Session ID.
4. Tạo hai request client cùng gửi cookie đó.
5. Dùng barrier hoặc latch trong test để cả hai request tải session trước khi một request lưu.
6. A chỉ sửa cart.
7. B chỉ sửa theme.
8. Điều khiển thứ tự lưu để tái hiện race.
9. Đọc session bằng request thứ ba.
10. So sánh kết quả với kỳ vọng của save mode.

### Kiểm thử same-attribute race

Lặp lại kịch bản nhưng A và B cùng đọc visits=0 rồi cùng đặt visits=1. Test cần thể hiện rằng `ON_SET_ATTRIBUTE` không tự cộng dồn hai lần tăng.

Không nên viết test chỉ gửi hai request nhanh rồi hy vọng chúng chồng lấn. Nếu không có barrier, test có thể chạy tuần tự và không tái hiện race.

### So sánh các save mode

Có thể chạy cùng kịch bản với:

- `ON_SET_ATTRIBUTE`: kiểm tra thay đổi ở thuộc tính độc lập có tránh ghi lại thuộc tính không được đặt không.
- `ON_GET_ATTRIBUTE`: kiểm tra thuộc tính được đọc có thể bị lưu lại từ snapshot cũ.
- `ALWAYS`: kiểm tra request cuối có thể ghi lại toàn bộ snapshot.
- Flush mode `ON_SAVE` và `IMMEDIATE`: quan sát khác biệt về thời điểm ghi, nhưng không kỳ vọng mode nào tự giải quyết same-attribute lost update.

Các assertion phải dựa trên repository và phiên bản thực tế. Không giả định mọi implementation lưu từng thuộc tính theo cùng một câu SQL hoặc cùng thứ tự.

## 15. Kiểm thử bằng MockMvc và repository thật

MockMvc hữu ích để kiểm tra Servlet filter chain và cùng một application context. Nhưng nếu dùng mock session trong bộ nhớ, nó không xác minh cách Spring Session lưu các thuộc tính hoặc hành vi giữa nhiều instance.

Để kiểm thử đúng save mode:

- Dùng Spring Session repository thật.
- Dùng Redis test instance hoặc Testcontainers nếu dùng Redis.
- Dùng database tương ứng nếu dùng JDBC.
- Gửi hai request HTTP với cùng cookie.
- Đảm bảo request chồng lấn bằng latch/barrier.
- Kiểm tra thuộc tính cuối qua request mới hoặc repository API.
- Lặp lại với hai instance để xác minh hành vi phân tán.

Với nhiều instance, cần bảo đảm hai request thật sự đi đến hai JVM khác nhau. Nếu sticky session khiến cả hai đến cùng một node, test không chứng minh được concurrency qua repository dùng chung.

### Các kết quả nên kiểm tra

1. Request chỉ đọc thuộc tính không vô tình làm thay đổi dữ liệu theo mode đã chọn.
2. Request gọi setAttribute lưu được giá trị mới.
3. Hai request sửa hai thuộc tính độc lập không ghi đè ngoài ý muốn với mode phù hợp.
4. Hai request sửa cùng thuộc tính thể hiện rõ lost update nếu không có concurrency control.
5. ON_GET_ATTRIBUTE lưu mutation bên trong object đã đọc nhưng có thể ghi snapshot cũ.
6. ALWAYS ghi rộng hơn và có thể tạo nhiều ghi hơn.
7. Flush mode thay đổi thời điểm ghi, không tạo atomic merge.

## 16. Đo tác động hiệu năng của SaveMode

Save mode ảnh hưởng số thuộc tính cần serialize và ghi xuống repository. Khi session chứa nhiều object hoặc payload lớn, khác biệt có thể đáng kể.

Các metric hữu ích:

- Số lần save session trên request.
- Số thuộc tính được serialize.
- Tổng byte session được ghi.
- Thời gian serialize/deserialize.
- Thời gian repository save.
- Redis command latency hoặc JDBC update latency.
- Số request gặp lost update hoặc conflict ở tầng nghiệp vụ.
- Tỷ lệ lỗi serialization.

Không đo hiệu năng chỉ bằng một request đơn lẻ. Hãy dùng workload có nhiều request đồng thời và phân bố thuộc tính tương tự production.

`ON_SET_ATTRIBUTE` thường giảm công việc khi request chỉ sửa một vài thuộc tính. `ON_GET_ATTRIBUTE` phụ thuộc số thuộc tính được đọc. `ALWAYS` thường có chi phí cao hơn vì lưu toàn bộ thuộc tính. Nhưng kết quả thực tế còn phụ thuộc repository, serializer, kích thước object và cách request sử dụng session.

Đừng tối ưu save mode mà bỏ qua tính đúng đắn. Giảm byte ghi không có ý nghĩa nếu làm mất cập nhật nghiệp vụ.

## 17. Những lỗi và hiểu nhầm thường gặp

**ON_SET_ATTRIBUTE ngăn mọi lost update.**  
Không. Hai request cùng đặt một thuộc tính vẫn có thể ghi đè nhau. Save mode không có version check hoặc merge.

**ALWAYS an toàn hơn vì luôn lưu mọi thứ.**  
Không. Lưu toàn bộ snapshot cũ có thể ghi đè nhiều thuộc tính mới hơn và tăng chi phí ghi.

**ON_GET_ATTRIBUTE chỉ lưu thuộc tính đã sửa.**  
Không. Việc đọc thuộc tính cũng có thể đưa nó vào tập được lưu. Một snapshot cũ đã đọc có thể ghi đè thay đổi mới của request khác.

**Sửa object trong session là repository tự nhận ra.**  
Không nên giả định điều đó. Với ON_SET_ATTRIBUTE, gọi setAttribute sau khi sửa hoặc dùng object bất biến để đánh dấu thay đổi rõ ràng.

**FlushMode.IMMEDIATE giải quyết race.**  
Không. Nó thay đổi thời điểm ghi, không cung cấp atomic read-modify-write hay conflict detection.

**synchronized(session) khóa session trên mọi instance.**  
Không. Monitor Java chỉ đồng bộ các thread dùng cùng object trong cùng JVM, không phải khóa phân tán.

**Hai request dùng cùng cookie là dữ liệu tự động merge.**  
Không. Cùng Session ID chỉ giúp tìm cùng session trong repository; mỗi request vẫn có thể giữ snapshot riêng.

**Sticky session là cách giải quyết concurrency.**  
Không. Nó có thể giữ request ở một node nhưng không loại bỏ request song song trong cùng JVM và không thay thế concurrency control.

**Session là nơi phù hợp để giữ counter nghiệp vụ.**  
Không nếu counter cần cập nhật chính xác dưới tải đồng thời. Dùng atomic operation hoặc transaction ở kho dữ liệu nghiệp vụ.

## 18. Checklist lựa chọn và vận hành

Trước khi chọn save mode, hãy trả lời:

- Session có bao nhiêu thuộc tính và kích thước trung bình là bao nhiêu?
- Request thường đọc hay ghi những thuộc tính nào?
- Object có khả biến không?
- Có nhiều request cùng cập nhật một thuộc tính không?
- Thuộc tính có độc lập hay thuộc cùng một aggregate cần nhất quán?
- Repository có theo dõi thay đổi bằng set/remove attribute như mong đợi không?
- Save mode và flush mode nào được hỗ trợ trong phiên bản đang dùng?
- Tất cả instance có cùng cấu hình không?
- Có integration test race với cùng Session ID không?
- Dữ liệu nào nên chuyển khỏi session sang database/Redis nghiệp vụ?
- Có optimistic locking hoặc atomic operation cho dữ liệu quan trọng không?
- Có metric về số byte ghi và lỗi cập nhật không?

Một lựa chọn khởi đầu phổ biến là `ON_SET_ATTRIBUTE` cùng code cập nhật rõ ràng bằng `setAttribute`. Sau đó, đo workload và kiểm thử race. Chỉ chọn `ON_GET_ATTRIBUTE` hoặc `ALWAYS` khi hành vi mutation yêu cầu và tác động ghi đè đã được hiểu rõ.

## 19. Tự kiểm tra

1. Vì sao hai request có cùng Session ID vẫn có thể ghi đè dữ liệu của nhau?
2. `SaveMode` quyết định điều gì khi session được lưu?
3. `ON_SET_ATTRIBUTE` giúp giảm loại ghi đè nào?
4. Vì sao `ON_SET_ATTRIBUTE` không giải quyết được hai request cùng sửa một thuộc tính?
5. `ON_GET_ATTRIBUTE` hỗ trợ object khả biến như thế nào?
6. Vì sao ON_GET_ATTRIBUTE có thể ghi lại một snapshot cũ dù request chỉ đọc thuộc tính?
7. Vì sao `ALWAYS` có nguy cơ ghi đè rộng hơn?
8. `SaveMode` khác `FlushMode` ở điểm nào?
9. Vì sao `FlushMode.IMMEDIATE` không phải atomic operation?
10. Khi nào nên chuyển counter ra khỏi session?
11. Optimistic locking phát hiện xung đột bằng cách nào?
12. Vì sao `synchronized(session)` không bảo vệ session giữa nhiều instance?
13. Cần làm gì để test thật sự tái hiện hai request đồng thời?
14. Những metric nào giúp đánh giá tác động hiệu năng của save mode?

### Gợi ý trả lời

1. Mỗi request có thể tải một snapshot riêng; lần lưu sau có thể ghi dữ liệu dựa trên snapshot đã cũ.
2. Tập thuộc tính được đưa vào lần lưu.
3. Nó giảm việc ghi lại thuộc tính chỉ được đọc hoặc không thay đổi trong request.
4. Cả hai request đều đặt cùng thuộc tính; lần ghi sau có thể thay thế giá trị của lần ghi trước.
5. Thuộc tính đã đọc được đưa vào tập lưu, nên mutation bên trong object có thể được ghi dù không gọi setAttribute lại.
6. Vì request giữ object từ snapshot cũ và việc đọc khiến thuộc tính được lưu lại.
7. Nó lưu tất cả thuộc tính, bao gồm những thuộc tính request không sửa nhưng có thể đã cũ.
8. SaveMode chọn thuộc tính nào được lưu; FlushMode chọn thời điểm ghi.
9. Nó chỉ đẩy ghi sớm hơn, không khóa chuỗi đọc-sửa-ghi hoặc so sánh version.
10. Khi counter cần tăng chính xác, không được mất cập nhật và có nhiều request đồng thời.
11. Update chỉ thành công nếu version hiện tại vẫn bằng version đã đọc; nếu không, request phát hiện conflict.
12. Monitor chỉ đồng bộ thread dùng cùng object trong cùng JVM, không phối hợp giữa JVM.
13. Dùng cùng cookie, barrier/latch để cả hai request đọc trước khi một request ghi, rồi điều khiển thứ tự lưu.
14. Số lần save, số thuộc tính serialize, byte ghi, thời gian serialize/save, Redis/JDBC latency và conflict rate.

## Kết luận

`SaveMode` quyết định thuộc tính nào được đưa vào lần lưu session. `ON_SET_ATTRIBUTE` thường là lựa chọn khởi đầu tốt vì chỉ ghi những thuộc tính được request thay đổi rõ ràng, giúp giảm việc một request ghi lại snapshot cũ của các thuộc tính khác. `ON_GET_ATTRIBUTE` hỗ trợ object khả biến đã được đọc nhưng có thể lưu lại dữ liệu stale; `ALWAYS` lưu toàn bộ thuộc tính và có phạm vi ghi rộng nhất.

Không save mode nào tự giải quyết xung đột khi hai request cùng sửa một thuộc tính. `FlushMode` cũng chỉ điều khiển thời điểm ghi. Với counter, số dư, tồn kho hoặc aggregate cần nhất quán, hãy dùng atomic operation, transaction hoặc optimistic locking ở kho dữ liệu nghiệp vụ. Kiểm thử bằng cùng Session ID, request chồng lấn và Redis/JDBC repository thật để xác nhận cả tính đúng đắn lẫn chi phí ghi.

