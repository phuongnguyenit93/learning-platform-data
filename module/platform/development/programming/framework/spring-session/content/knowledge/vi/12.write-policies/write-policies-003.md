# SaveMode.ON_SET_ATTRIBUTE, ON_GET_ATTRIBUTE và ALWAYS

Spring Session có thể lưu dữ liệu phiên vào Redis để nhiều instance Spring cùng sử dụng. Khi request kết thúc, repository cần quyết định thuộc tính nào của phiên sẽ được ghi lại. `SaveMode` điều khiển phạm vi thuộc tính được lưu trong lần cập nhật đó.

Ba chế độ thường gặp là `ON_SET_ATTRIBUTE`, `ON_GET_ATTRIBUTE` và `ALWAYS`. Khác biệt chính nằm ở cách Spring Session nhận biết thuộc tính nào cần ghi: thuộc tính được ứng dụng đặt, thuộc tính được đọc hoặc toàn bộ thuộc tính. Lựa chọn phù hợp ảnh hưởng đến số lần tuần tự hóa, lượng dữ liệu gửi tới Redis, khả năng lưu thay đổi bên trong object mutable và nguy cơ ghi đè dữ liệu khi request chạy đồng thời.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích chính xác hành vi của ba giá trị `SaveMode`.
- Chọn chế độ phù hợp với cách ứng dụng cập nhật thuộc tính session.
- Nhận biết vì sao sửa object mutable mà không gọi lại `setAttribute` có thể làm mất thay đổi.
- Cấu hình save mode bằng Spring Boot hoặc Java configuration.
- Phân biệt `SaveMode` với `FlushMode`.
- Đánh giá chi phí ghi, rủi ro ghi đè và cách kiểm thử với Redis.

## 1. SaveMode giải quyết vấn đề gì?

Một session thường chứa nhiều thuộc tính, nhưng mỗi request chỉ sử dụng hoặc thay đổi một phần trong số đó. Nếu repository luôn ghi toàn bộ thuộc tính sau mỗi request, nó có thể tuần tự hóa và gửi nhiều dữ liệu không thay đổi. Ngược lại, nếu chỉ ghi các thuộc tính được đánh dấu rõ ràng là đã thay đổi, ứng dụng phải tuân thủ cách cập nhật mà repository có thể nhận biết.

Ví dụ session có các thuộc tính:

| Thuộc tính | Kích thước giả định | Request hiện tại |
|---|---:|---|
| `cart` | 12 KB | Đọc và thêm một sản phẩm |
| `locale` | 10 byte | Chỉ đọc |
| `checkoutStep` | 20 byte | Đặt giá trị mới |
| `recentSearches` | 8 KB | Không truy cập |

Nếu chỉ thay đổi `checkoutStep`, việc ghi lại tất cả thuộc tính có thể tốn thêm thời gian tuần tự hóa và lưu lượng mạng. `SaveMode` cho phép chọn phạm vi thuộc tính được đưa vào lần lưu.

`SaveMode` không quyết định thời điểm ghi dữ liệu. Nó quyết định thuộc tính nào được xem xét để lưu. Thời điểm đẩy thay đổi xuống Redis được điều khiển bởi `FlushMode`, là một cấu hình riêng.

## 2. Ba chế độ hoạt động

Spring Session định nghĩa ba lựa chọn:

| Chế độ | Thuộc tính được lưu | Đặc điểm |
|---|---|---|
| `ON_SET_ATTRIBUTE` | Thuộc tính được đặt bằng `session.setAttribute(...)` trong request hiện tại | Hạn chế ghi vào các thuộc tính được ứng dụng chủ động đánh dấu bằng thao tác set |
| `ON_GET_ATTRIBUTE` | Thuộc tính được đọc bằng `session.getAttribute(...)` hoặc được đặt trong request | Có thể lưu thay đổi bên trong object mutable đã được đọc, nhưng có thể ghi cả thuộc tính chỉ đọc |
| `ALWAYS` | Tất cả thuộc tính của session | Đơn giản về cách nhận biết thay đổi, nhưng có thể tuần tự hóa và ghi nhiều dữ liệu hơn |

Các chế độ trên nói về thuộc tính session. Metadata như thời gian truy cập, thời gian không hoạt động và thao tác xóa thuộc tính vẫn được repository quản lý theo vòng đời riêng.

### 2.1. ON_SET_ATTRIBUTE

Với `ON_SET_ATTRIBUTE`, repository chỉ lưu những thuộc tính mà ứng dụng đã đặt trong request hiện tại. Thao tác `setAttribute` đánh dấu thuộc tính cần ghi:

~~~java
session.setAttribute("locale", "vi");
session.setAttribute("checkoutStep", "PAYMENT");
~~~

Trong request này, các thuộc tính được đặt sẽ được đưa vào lần lưu. Những thuộc tính khác chỉ được đọc hoặc không được truy cập sẽ không bị ghi lại chỉ vì chúng tồn tại trong session.

Chế độ này phù hợp khi ứng dụng cập nhật session theo kiểu thay thế giá trị: đọc dữ liệu, tạo giá trị mới rồi gọi `setAttribute`. Nó giúp giảm việc ghi các thuộc tính không thay đổi.

Điểm cần chú ý là sửa một object mutable đã lấy từ session mà không gọi lại `setAttribute` có thể không được nhận biết:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(productId);
// Không gọi session.setAttribute("cart", cart).
~~~

Nếu dùng `ON_SET_ATTRIBUTE`, đoạn code trên không đánh dấu `cart` là thuộc tính đã được đặt trong request. Vì vậy, thay đổi bên trong object có thể không được lưu vào Redis.

Cách cập nhật rõ ràng:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(productId);
session.setAttribute("cart", cart);
~~~

Việc gọi lại `setAttribute` làm cho ý định cập nhật trở nên rõ ràng và phù hợp với `ON_SET_ATTRIBUTE`.

### 2.2. ON_GET_ATTRIBUTE

Với `ON_GET_ATTRIBUTE`, thuộc tính được lưu nếu ứng dụng đã đọc nó bằng `getAttribute` hoặc đặt nó trong request. Điều này hữu ích khi ứng dụng lấy một object mutable từ session rồi sửa trực tiếp object đó:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(productId);
~~~

Lời gọi `getAttribute("cart")` đánh dấu thuộc tính đã được truy cập. Khi repository lưu session, `cart` được đưa vào phạm vi ghi dù ứng dụng không gọi lại `setAttribute`.

Đổi lại, thuộc tính chỉ đọc cũng có thể được ghi lại:

~~~java
String locale = (String) session.getAttribute("locale");
return renderPage(locale);
~~~

Nếu request chỉ đọc `locale`, chế độ này vẫn có thể đưa thuộc tính đó vào lần lưu. Với thuộc tính lớn, việc đọc một giá trị có thể kéo theo tuần tự hóa và ghi lại dữ liệu không thay đổi.

`ON_GET_ATTRIBUTE` là lựa chọn cân nhắc khi code hiện tại dựa nhiều vào mutation của object mutable và khó chuyển ngay sang cách replace-on-write. Tuy nhiên, cần đo chi phí ghi và xem xét tác động khi nhiều request cùng đọc rồi cập nhật các thuộc tính khác nhau trong một session.

### 2.3. ALWAYS

Với `ALWAYS`, repository lưu tất cả thuộc tính session trong lần lưu, bất kể request đã đọc hoặc đặt thuộc tính nào. Ví dụ:

~~~java
String locale = (String) session.getAttribute("locale");
return renderPage(locale);
~~~

Ngay cả khi request chỉ đọc `locale`, các thuộc tính session khác cũng nằm trong phạm vi được lưu.

Chế độ này giảm sự phụ thuộc vào việc đánh dấu từng thuộc tính đã được đọc hoặc đặt. Nó có thể hữu ích khi ứng dụng có cách thao tác session khó chuẩn hóa hoặc cần duy trì tương thích với code cũ. Đổi lại, session có nhiều thuộc tính lớn sẽ làm tăng công việc tuần tự hóa và ghi Redis ở mỗi lần lưu.

`ALWAYS` cũng không phải cơ chế khóa hay giải quyết xung đột cập nhật. Nếu request A và request B cùng tải snapshot cũ, việc cả hai ghi toàn bộ thuộc tính có thể khiến lần ghi sau ghi đè thay đổi của lần ghi trước.

## 3. Ví dụ so sánh trên cùng một request

Giả sử session có ba thuộc tính:

~~~java
session.setAttribute("cart", cart);
session.setAttribute("locale", "vi");
session.setAttribute("theme", "dark");
~~~

Request hiện tại thực hiện:

~~~java
Cart currentCart = (Cart) session.getAttribute("cart");
currentCart.add(productId);

String locale = (String) session.getAttribute("locale");
session.setAttribute("theme", "light");
~~~

Phạm vi thuộc tính được lưu:

| Thuộc tính | Được đọc? | Được đặt? | ON_SET_ATTRIBUTE | ON_GET_ATTRIBUTE | ALWAYS |
|---|---:|---:|---:|---:|---:|
| `cart` | Có | Không | Không được đánh dấu chỉ vì mutation | Có | Có |
| `locale` | Có | Không | Không | Có | Có |
| `theme` | Không | Có | Có | Có | Có |

Ở cột `ON_SET_ATTRIBUTE`, `cart` có thể không được ghi dù object đã bị sửa. Nếu thêm `session.setAttribute("cart", currentCart)` sau khi gọi `add`, thuộc tính `cart` cũng được đánh dấu và sẽ được lưu.

Ở cột `ON_GET_ATTRIBUTE`, `cart` được ghi vì đã được đọc; `locale` cũng được ghi dù chỉ đọc. Đây là sự đánh đổi cốt lõi của chế độ này.

Ở cột `ALWAYS`, cả ba thuộc tính đều được đưa vào phạm vi ghi, kể cả `locale` và `theme` không được đọc trong request.

## 4. Chọn chế độ theo cách thiết kế thuộc tính

### 4.1. Ưu tiên ON_SET_ATTRIBUTE khi có thể

`ON_SET_ATTRIBUTE` thường phù hợp với ứng dụng mới hoặc code đã chuẩn hóa cách cập nhật session. Ưu điểm:

- Chỉ ghi thuộc tính được ứng dụng chủ động đặt.
- Giảm việc ghi lại thuộc tính chỉ đọc.
- Dễ nhận biết nơi nào trong code tạo thay đổi session.
- Khuyến khích cách cập nhật rõ ràng và có thể kiểm thử.

Nên ưu tiên object bất biến hoặc cách replace-on-write. Ví dụ, thay vì sửa trực tiếp object đang nằm trong session, tạo object mới:

~~~java
Cart oldCart = (Cart) session.getAttribute("cart");
Cart updatedCart = oldCart.withAddedProduct(productId);
session.setAttribute("cart", updatedCart);
~~~

Với object bất biến, thay đổi phải tạo giá trị mới và đặt lại vào session. Điều này giúp việc lưu có thể dự đoán được và giảm lỗi do mutation ẩn.

### 4.2. Cân nhắc ON_GET_ATTRIBUTE khi có mutable object

Nếu ứng dụng đang dùng nhiều object mutable và các luồng xử lý thường lấy object bằng `getAttribute` rồi sửa nội dung, `ON_GET_ATTRIBUTE` có thể giúp lưu những thay đổi đó mà không cần sửa ngay mọi điểm gọi.

Trước khi chọn, hãy kiểm tra:

- Tỷ lệ thuộc tính được đọc so với số thuộc tính được sửa.
- Kích thước trung bình của thuộc tính.
- Số request chỉ đọc session.
- Chi phí tuần tự hóa và ghi Redis.
- Khả năng hai request cùng đọc rồi ghi lại một thuộc tính.

Nếu phần lớn request chỉ đọc dữ liệu, chế độ này có thể tạo ra nhiều lần ghi không cần thiết. Hãy cân nhắc refactor các điểm cập nhật quan trọng sang replace-on-write.

### 4.3. Dùng ALWAYS khi có lý do rõ ràng

`ALWAYS` có thể phù hợp trong giai đoạn chuyển tiếp khi code cũ cập nhật session theo nhiều cách và chưa thể xác định chính xác thuộc tính nào đã bị thay đổi. Nó cũng đơn giản hóa hành vi lưu khi session có ít thuộc tính nhỏ.

Không nên chọn `ALWAYS` chỉ để “chắc chắn mọi thay đổi được lưu” mà không đo chi phí. Khi session chứa object graph lớn hoặc nhiều thuộc tính, mỗi lần lưu có thể tốn CPU, bộ nhớ tạm, lưu lượng mạng và thời gian Redis nhiều hơn.

## 5. Cấu hình bằng Spring Boot

Với Spring Boot có hỗ trợ thuộc tính Redis save mode, có thể cấu hình trong `application.yml`:

~~~yaml
spring:
  session:
    redis:
      save-mode: on_set_attribute
~~~

Các giá trị cấu hình thường dùng:

~~~yaml
spring:
  session:
    redis:
      save-mode: on_get_attribute
~~~

hoặc:

~~~yaml
spring:
  session:
    redis:
      save-mode: always
~~~

Spring Boot bind tên enum theo dạng kebab/lowercase. Hãy xác minh property có sẵn trong đúng dòng Spring Boot và Spring Session của dự án; tên property hoặc cách auto-configuration có thể khác giữa các phiên bản cũ.

Không khai báo nhiều giá trị cùng lúc. Chọn một save mode cho repository của ứng dụng và kiểm tra cấu hình thực tế được áp dụng trong môi trường chạy.

## 6. Cấu hình bằng Java

Nếu tự cấu hình Spring Session Redis bằng annotation, các phiên bản hỗ trợ có thể khai báo save mode qua `@EnableRedisHttpSession`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SaveMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(saveMode = SaveMode.ON_SET_ATTRIBUTE)
public class RedisSessionConfiguration {
}
~~~

Đổi giá trị thành `SaveMode.ON_GET_ATTRIBUTE` hoặc `SaveMode.ALWAYS` để chọn chế độ tương ứng. Nếu ứng dụng dùng `@EnableRedisIndexedHttpSession`, hãy kiểm tra annotation và thuộc tính được hỗ trợ trong phiên bản Spring Session hiện tại.

Không cấu hình đồng thời nhiều cơ chế tạo repository khác nhau nếu chưa xác định rõ bean nào đang được dùng. Với Spring Boot, thường nên để auto-configuration quản lý repository và đặt property; với cấu hình Java thủ công, cần tránh tạo repository thứ hai ngoài ý muốn.

## 7. SaveMode không phải FlushMode

Hai cấu hình này giải quyết hai câu hỏi khác nhau:

| Cấu hình | Câu hỏi | Ví dụ |
|---|---|---|
| `SaveMode` | Thuộc tính nào được ghi? | `ON_SET_ATTRIBUTE` chỉ đưa các thuộc tính đã được đặt vào phạm vi ghi |
| `FlushMode` | Khi nào thay đổi được đẩy tới Redis? | `ON_SAVE` lưu theo lần save cuối request; `IMMEDIATE` đẩy thay đổi ngay khi có thao tác cập nhật theo repository |

Ví dụ, cấu hình:

~~~yaml
spring:
  session:
    redis:
      save-mode: on_set_attribute
      flush-mode: on_save
~~~

có nghĩa repository chọn các thuộc tính đã được đặt trong request và thực hiện lưu theo chính sách flush khi save. Nếu chuyển sang `flush-mode: immediate`, thời điểm gửi thay đổi có thể sớm hơn, nhưng tập thuộc tính chịu ảnh hưởng vẫn do save mode và thao tác session quyết định.

Không suy ra rằng `IMMEDIATE` sẽ tự phát hiện mọi mutation bên trong object mutable. Nếu ứng dụng sửa object mà không gọi API session để đánh dấu thay đổi, hành vi vẫn phụ thuộc save mode và cách repository theo dõi thuộc tính.

## 8. Thuộc tính bị xóa và thuộc tính mới

Thao tác xóa thuộc tính cần được repository ghi nhận như một thay đổi, độc lập với việc ứng dụng có đọc lại giá trị hay không:

~~~java
session.removeAttribute("temporaryState");
~~~

Tương tự, thuộc tính mới hoặc thuộc tính được thay thế bằng `setAttribute` phải được lưu theo chính sách của repository. Không nên tự sửa Redis hash để xóa trường `sessionAttr:*`, vì repository có thể còn metadata hoặc index phụ trợ liên quan.

Hãy kiểm thử riêng:

- Thêm một thuộc tính mới.
- Ghi đè thuộc tính đã tồn tại.
- Xóa thuộc tính.
- Ghi giá trị `null` theo semantics của Servlet session, thường tương đương xóa thuộc tính.
- Thay object mutable bằng một object mới.

## 9. SaveMode và request đồng thời

`SaveMode` không cung cấp transaction hoặc optimistic locking cho toàn bộ session. Hai request có thể cùng tải một phiên, sau đó cập nhật các thuộc tính khác nhau hoặc cùng một thuộc tính.

Ví dụ:

1. Request A tải session với `cart` và `locale`.
2. Request B cũng tải cùng snapshot.
3. A thêm sản phẩm vào `cart` và lưu.
4. B thay đổi `locale` và lưu.
5. Tùy save mode và repository, B có thể chỉ ghi `locale` hoặc ghi thêm những thuộc tính đã đọc/toàn bộ thuộc tính. Nếu `cart` cũ nằm trong phạm vi ghi của B, thay đổi của A có thể bị ghi đè.

Vì vậy:

- `ON_SET_ATTRIBUTE` có thể giảm phạm vi ghi, nhưng không tự giải quyết hai request cùng sửa một thuộc tính.
- `ON_GET_ATTRIBUTE` có thể ghi lại thuộc tính chỉ đọc trong request và tăng khả năng ghi đè snapshot cũ.
- `ALWAYS` có phạm vi ghi lớn nhất và có thể làm tăng rủi ro stale write khi nhiều request cùng lưu.

Với dữ liệu nghiệp vụ quan trọng như số dư, giỏ hàng, trạng thái thanh toán hoặc quyền truy cập, hãy dùng database có transaction, optimistic locking hoặc cơ chế cập nhật nguyên tử phù hợp. Session nên giữ trạng thái điều hướng nhỏ hoặc ID tham chiếu. Không dựa vào save mode để bảo đảm tính nhất quán nghiệp vụ.

## 10. Đo chi phí và chọn mode

Trước khi đổi save mode trong production, hãy đo bằng dữ liệu đại diện:

- Số thuộc tính trung bình và phân vị cao của mỗi session.
- Kích thước payload sau tuần tự hóa.
- Số thuộc tính được đọc, đặt và xóa trên mỗi request.
- Tỷ lệ request chỉ đọc session.
- Thời gian tuần tự hóa, ghi Redis và tổng độ trễ request.
- Số lỗi hoặc lần cập nhật mất mát khi có request đồng thời.

Một định hướng lựa chọn:

| Kiểu ứng dụng | Lựa chọn nên đánh giá trước | Lý do |
|---|---|---|
| Dữ liệu session được thay thế qua `setAttribute` | `ON_SET_ATTRIBUTE` | Ghi có chủ đích, tránh ghi thuộc tính chỉ đọc |
| Nhiều object mutable được đọc rồi sửa tại chỗ | `ON_GET_ATTRIBUTE` | Thuộc tính đã đọc cũng được đưa vào phạm vi lưu |
| Code cũ khó kiểm soát thao tác đọc/đặt và session nhỏ | `ALWAYS` | Đơn giản hóa phạm vi lưu, đổi lại nhiều dữ liệu có thể được ghi hơn |

Đây là định hướng, không phải quy tắc tuyệt đối. Hãy kiểm thử trên repository và phiên bản thực tế vì cách flush, serializer và dữ liệu session ảnh hưởng kết quả vận hành.

## 11. Kiểm thử hành vi từng SaveMode

Nên dùng integration test với Redis để xác minh dữ liệu được lưu sau khi request kết thúc. Unit test chỉ mock `HttpSession` thường không mô phỏng đầy đủ cách repository đánh dấu thuộc tính đã đọc hoặc đã đặt.

Các tình huống cần kiểm thử:

| Tình huống | ON_SET_ATTRIBUTE | ON_GET_ATTRIBUTE | ALWAYS |
|---|---|---|---|
| Đặt thuộc tính mới | Lưu | Lưu | Lưu |
| Đọc rồi sửa object mutable, không gọi lại set | Không được đánh dấu chỉ vì mutation | Lưu thuộc tính đã đọc | Lưu thuộc tính |
| Chỉ đọc thuộc tính, không sửa | Không ghi thuộc tính đó chỉ vì đọc | Có thể ghi lại | Ghi |
| Không đọc hoặc đặt thuộc tính | Không ghi thuộc tính đó | Không ghi thuộc tính đó | Ghi |
| Gọi setAttribute với giá trị mới | Lưu | Lưu | Lưu |

Có thể xây dựng test theo trình tự:

1. Tạo session và lưu một object mutable cùng một thuộc tính khác.
2. Kết thúc request đầu để repository ghi dữ liệu ban đầu.
3. Request tiếp theo tải session, sửa object theo cách cần kiểm tra.
4. Đóng request để Spring Session lưu theo save mode đang cấu hình.
5. Tải lại session từ repository bằng một request mới.
6. Xác nhận giá trị được lưu hoặc không lưu đúng với semantics của mode.

Chạy cùng bộ test với cả ba mode. Đừng chỉ kiểm tra object trong bộ nhớ của request đã sửa; phải tải lại từ repository để xác nhận dữ liệu bền vững.

Ngoài ra, hãy chạy test đồng thời:

- Hai request cập nhật hai thuộc tính khác nhau.
- Hai request cùng cập nhật một thuộc tính.
- Một request đọc thuộc tính trong khi request khác cập nhật nó.
- Một request logout hoặc xóa phiên trong lúc request khác đang lưu.

Những bài test này giúp phát hiện stale write và xác định mức độ phù hợp của save mode với luồng cập nhật thực tế.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Sửa object trong session nhưng dữ liệu không đổi sau request | Dùng `ON_SET_ATTRIBUTE` và không gọi lại `setAttribute` | Đặt lại thuộc tính hoặc dùng object bất biến/replace-on-write |
| Request chỉ đọc nhưng Redis vẫn có thao tác ghi | Dùng `ON_GET_ATTRIBUTE` hoặc `ALWAYS` | Đo lại save mode và giới hạn dữ liệu được đọc |
| Mọi request ghi nhiều dữ liệu | `ALWAYS` với session có nhiều thuộc tính lớn | Chuyển sang mode phù hợp với cách cập nhật và giảm kích thước session |
| Dữ liệu session bị ghi đè khi request đồng thời | Request lưu snapshot cũ; save mode không phải cơ chế khóa | Dùng transaction/optimistic locking cho dữ liệu nghiệp vụ và giảm phạm vi session |
| Đổi save mode nhưng hành vi không thay đổi | Cấu hình không được bind hoặc repository khác đang được dùng | Kiểm tra property, bean repository và cấu hình runtime |
| Dữ liệu chỉ xuất hiện trong request hiện tại | Chưa kiểm tra sau khi request kết thúc hoặc flush mode chưa lưu | Tải lại session từ repository và kiểm tra flush mode |

## 13. Checklist trước khi chọn SaveMode

- [ ] Đã hiểu rõ khác biệt giữa `ON_SET_ATTRIBUTE`, `ON_GET_ATTRIBUTE` và `ALWAYS`.
- [ ] Đã rà soát code có mutation object mutable trong session.
- [ ] Với `ON_SET_ATTRIBUTE`, mọi thay đổi cần lưu đều gọi lại `setAttribute`.
- [ ] Đã đo tỷ lệ request chỉ đọc và kích thước thuộc tính.
- [ ] Đã phân biệt `SaveMode` với `FlushMode`.
- [ ] Cấu hình được áp dụng thống nhất trên tất cả instance.
- [ ] Đã kiểm thử bằng Redis và tải lại session sau khi request kết thúc.
- [ ] Đã kiểm thử request đồng thời và stale write.
- [ ] Dữ liệu nghiệp vụ quan trọng có transaction hoặc cơ chế đồng bộ riêng.
- [ ] Có kế hoạch triển khai và theo dõi độ trễ sau khi đổi mode.

`ON_SET_ATTRIBUTE` phù hợp khi ứng dụng cập nhật session rõ ràng bằng `setAttribute`; `ON_GET_ATTRIBUTE` hữu ích khi cần lưu thay đổi của object đã được đọc nhưng có thể ghi lại cả dữ liệu chỉ đọc; `ALWAYS` lưu toàn bộ thuộc tính và đơn giản hóa việc nhận biết thay đổi nhưng có chi phí cao hơn. Hãy chọn mode theo cách code thực sự thao tác session, phân biệt nó với thời điểm flush và kiểm thử dữ liệu sau khi tải lại từ Redis, đặc biệt khi nhiều request cùng cập nhật một phiên.
