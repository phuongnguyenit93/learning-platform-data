# Metadata, thuộc tính và cách tổ chức dữ liệu phiên ở mức khái niệm

Khi Spring Session dùng Redis, phiên làm việc được lưu ở phía máy chủ dưới dạng dữ liệu Redis. Trình duyệt thường chỉ giữ session ID trong cookie; session ID giúp ứng dụng tìm đúng dữ liệu phiên trong repository. Để vận hành và chẩn đoán hệ thống, cần hiểu dữ liệu phiên gồm những phần nào, metadata khác thuộc tính nghiệp vụ ra sao và Redis tổ chức các phần đó như thế nào.

Spring Session Data Redis thường biểu diễn một phiên bằng Redis hash. Hash chứa metadata quản lý vòng đời và các trường thuộc tính của ứng dụng. Tùy repository, phiên bản Spring Session và cấu hình, Redis còn có thể có key theo dõi hết hạn, index phục vụ tìm phiên và kênh phát sự kiện. Những key phụ trợ này là chi tiết triển khai; ứng dụng nên thao tác phiên qua API Spring Session thay vì tự sửa cấu trúc Redis.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt metadata của phiên với thuộc tính do ứng dụng lưu.
- Hiểu cấu trúc Redis hash đại diện cho một session.
- Giải thích vai trò của namespace, session ID, key hết hạn và index.
- Hiểu vì sao giá trị thuộc tính cần được tuần tự hóa.
- Tổ chức dữ liệu phiên nhỏ gọn, nhất quán và tương thích khi nâng cấp.
- Dùng các lệnh Redis chỉ đọc để quan sát dữ liệu phiên an toàn.

## 1. Một phiên gồm metadata và thuộc tính ứng dụng

Một session có hai nhóm dữ liệu chính:

| Nhóm dữ liệu | Ví dụ | Ai quản lý? |
|---|---|---|
| Metadata phiên | ID, thời điểm tạo, lần truy cập gần nhất, thời gian không hoạt động tối đa | Spring Session và repository |
| Thuộc tính phiên | Mã người dùng, mã giỏ hàng, ngôn ngữ, trạng thái quy trình | Ứng dụng đặt qua API session |

Metadata giúp Spring Session nhận biết phiên được tạo khi nào, lần gần nhất được truy cập lúc nào và khi nào cần hết hạn. Thuộc tính ứng dụng chứa trạng thái mà nghiệp vụ muốn chia sẻ giữa nhiều request.

Ví dụ, một ứng dụng thương mại điện tử có thể lưu `cartId`, `locale` và một số lựa chọn giao diện trong session. Thông tin hồ sơ người dùng, danh sách sản phẩm đầy đủ hoặc nội dung file lớn nên được lưu trong kho dữ liệu nghiệp vụ phù hợp; session chỉ giữ mã tham chiếu cần thiết.

Trong ứng dụng Servlet, code thường thao tác với `HttpSession`:

~~~java
HttpSession session = request.getSession();
session.setAttribute("cartId", cartId);
session.setAttribute("locale", "vi");

String currentLocale =
        (String) session.getAttribute("locale");
~~~

Với Spring Session, API Servlet vẫn được giữ lại. Repository Redis nhận các thay đổi và lưu dữ liệu phiên ở phía máy chủ. Ứng dụng không cần tự tạo Redis key hoặc tự tuần tự hóa từng thuộc tính.

## 2. Redis hash đại diện cho một session

Trong cấu trúc phổ biến của Spring Session Data Redis, mỗi phiên có một Redis hash riêng. Với namespace mặc định thường gặp là `spring:session`, key của hash có dạng:

~~~text
spring:session:sessions:<sessionId>
~~~

Trong đó `<sessionId>` là ID do Spring Session cấp phát. Hash chứa các trường metadata và các trường thuộc tính. Có thể hình dung cấu trúc như sau:

~~~text
Redis
└── spring:session:sessions:<sessionId>   (HASH)
    ├── creationTime                      (metadata)
    ├── lastAccessedTime                  (metadata)
    ├── maxInactiveInterval                (metadata)
    ├── sessionAttr:cartId                 (attribute)
    ├── sessionAttr:locale                 (attribute)
    └── sessionAttr:checkoutStep           (attribute)
~~~

Đây là mô hình khái niệm của repository Redis phổ biến, không phải cam kết mọi phiên bản hoặc mọi repository đều có chính xác cùng tên trường. Không dựa vào tên key nội bộ để viết logic nghiệp vụ. Khi cần kiểm tra cấu trúc cụ thể, hãy đối chiếu tài liệu đúng phiên bản Spring Session và cấu hình namespace của ứng dụng.

Ba trường metadata thường gặp:

- `creationTime`: thời điểm tạo phiên, thường được lưu dưới dạng thời gian epoch tính bằng mili giây.
- `lastAccessedTime`: thời điểm truy cập gần nhất được repository ghi nhận.
- `maxInactiveInterval`: khoảng không hoạt động tối đa trước khi phiên hết hạn, thường tính bằng giây.

Các trường bắt đầu bằng `sessionAttr:` chứa giá trị thuộc tính của ứng dụng. Tiền tố này giúp phân biệt dữ liệu nghiệp vụ với metadata do Spring Session quản lý.

## 3. Session ID, namespace và Redis key

Session ID là định danh của một phiên. Cookie session thường mang ID này để request tiếp theo có thể gửi lại. Spring Session sử dụng ID để tìm hash tương ứng trong Redis.

Namespace là tiền tố giúp tách dữ liệu của các ứng dụng hoặc môi trường dùng chung Redis. Ví dụ:

~~~yaml
spring:
  session:
    redis:
      namespace: portal:session
~~~

Với namespace này, các key phiên có thể bắt đầu bằng `portal:session:sessions:` thay vì `spring:session:sessions:`. Tên key phụ trợ cũng được tổ chức dưới namespace tương ứng theo repository.

Namespace có ích khi:

- Nhiều ứng dụng dùng chung một Redis cluster.
- Staging và production cần tách dữ liệu.
- Một ứng dụng có nhiều nhóm phiên độc lập.
- Cần tránh trùng key giữa các dịch vụ.

Namespace không phải là một Redis database riêng. Nó là tiền tố trong tên key. Nếu hai ứng dụng dùng cùng namespace và cùng quy ước ID, dữ liệu có thể va chạm hoặc bị đọc nhầm. Hãy đặt namespace riêng, ổn định và dễ nhận biết cho từng ứng dụng/môi trường.

Không đưa tên người dùng, email, access token hoặc dữ liệu nhạy cảm vào namespace hay tên key. Key có thể xuất hiện trong log, metric, công cụ giám sát và bản sao dữ liệu.

## 4. Thuộc tính phiên được tuần tự hóa

Giá trị trong Redis không phải đối tượng Java đang nằm trong heap của JVM. Spring Session cần tuần tự hóa thuộc tính thành dạng byte trước khi lưu và giải tuần tự hóa khi tải phiên.

Ví dụ, ứng dụng lưu một đối tượng:

~~~java
session.setAttribute("cartSummary", cartSummary);
~~~

Repository dùng serializer đã cấu hình để chuyển `cartSummary` thành dữ liệu có thể lưu trong Redis. Khi request khác tải phiên, serializer chuyển dữ liệu đó trở lại đối tượng mà ứng dụng sử dụng.

Serializer ảnh hưởng trực tiếp đến:

- Định dạng byte được lưu trong từng trường thuộc tính.
- Khả năng đọc dữ liệu giữa các instance chạy các phiên bản ứng dụng khác nhau.
- Kích thước dữ liệu, thời gian tuần tự hóa và giải tuần tự hóa.
- Khả năng tương thích khi thay đổi class hoặc cấu trúc đối tượng.
- Rủi ro bảo mật nếu dữ liệu không tin cậy được giải tuần tự hóa không an toàn.

Spring Session Data Redis thường dùng Java serialization làm mặc định nếu ứng dụng không cấu hình serializer khác. Ứng dụng có thể cung cấp bean serializer với tên `springSessionDefaultRedisSerializer` để tùy chỉnh định dạng. Ví dụ dưới đây minh họa việc dùng JSON:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
public class SessionRedisSerializationConfiguration {

    @Bean
    RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
~~~

Đây là ví dụ định hướng; cần xác nhận bean name và serializer hook theo phiên bản Spring Session đang dùng. Với JSON, cần thiết kế type metadata và chính sách kiểu được phép giải tuần tự hóa phù hợp. Không bật cơ chế polymorphic typing rộng cho dữ liệu không tin cậy. Chỉ lưu các kiểu ứng dụng đã kiểm soát và kiểm thử tương thích giữa các phiên bản.

Không thay serializer trên một phần instance trong lúc các phiên đang hoạt động nếu node mới không thể đọc dữ liệu node cũ đã ghi. Khi cần đổi định dạng, hãy có kế hoạch migration: hỗ trợ đọc định dạng cũ trong thời gian chuyển tiếp, chuyển đổi dữ liệu có kiểm soát hoặc chờ các phiên cũ hết hạn trước khi loại bỏ serializer cũ.

## 5. Tổ chức thuộc tính phiên

Session phù hợp với trạng thái nhỏ, cần dùng qua nhiều request và có vòng đời ngắn. Nên ưu tiên:

- ID người dùng hoặc ID tenant đã được xác thực.
- Mã tham chiếu tới giỏ hàng, bản nháp hoặc quy trình nghiệp vụ.
- Ngôn ngữ, múi giờ hoặc một vài lựa chọn giao diện.
- Cờ trạng thái nhỏ và dữ liệu điều hướng tạm thời.

Tránh lưu:

- Toàn bộ JPA entity hoặc object graph có nhiều quan hệ.
- Danh sách kết quả tìm kiếm lớn hoặc toàn bộ giỏ hàng nhiều mặt hàng.
- File, ảnh, nội dung nhị phân lớn hoặc dữ liệu báo cáo.
- Đối tượng chứa connection, stream, request, response hoặc tài nguyên runtime.
- Mật khẩu, access token dài hạn hoặc bí mật không cần thiết cho request tiếp theo.

Một session quá lớn làm tăng dung lượng Redis, lưu lượng mạng, chi phí serializer và độ trễ đọc/ghi. Nếu nhiều request đồng thời cập nhật cùng session, payload lớn cũng làm tăng chi phí xử lý và khả năng ghi đè thay đổi.

Ví dụ, thay vì lưu toàn bộ đối tượng đơn hàng:

~~~java
// Không nên: object graph lớn, có thể chứa dữ liệu thay đổi liên tục.
session.setAttribute("order", orderEntity);

// Gọn hơn: chỉ lưu mã tham chiếu cần thiết.
session.setAttribute("activeOrderId", orderId);
~~~

Khi cần thông tin đơn hàng, service đọc theo `orderId` từ database và kiểm tra quyền truy cập. Session không nên trở thành một bản sao thứ hai của database nghiệp vụ.

## 6. Đặt tên thuộc tính và tránh xung đột

Tên thuộc tính nên có ý nghĩa, ổn định và nhất quán giữa các module. Nếu nhiều thành phần cùng dùng session, hãy thống nhất quy ước đặt tên để tránh ghi đè ngoài ý muốn.

Ví dụ:

| Tên thuộc tính | Nội dung | Ghi chú |
|---|---|---|
| `auth.userId` | ID người dùng | Chỉ dùng nếu phù hợp với cơ chế bảo mật hiện tại |
| `cart.id` | ID giỏ hàng | Dữ liệu chính nằm trong database |
| `ui.locale` | Mã ngôn ngữ | Giá trị nhỏ |
| `flow.checkoutId` | ID quy trình checkout | Trạng thái nghiệp vụ chính nằm ở service/domain store |

Tên có dấu chấm chỉ là quy ước tên chuỗi do ứng dụng chọn; Redis hash field có thể chứa tên này sau tiền tố `sessionAttr:`. Spring Session không tự diễn giải dấu chấm thành cấu trúc lồng nhau.

Không để nhiều module tự dùng những tên chung như `data`, `state` hoặc `user` với ý nghĩa khác nhau. Khi thay đổi tên thuộc tính, cần xem xét phiên đang tồn tại do phiên bản cũ ghi. Có thể đọc cả tên cũ và tên mới trong giai đoạn chuyển đổi, sau đó loại bỏ tên cũ khi phiên cũ hết hạn.

## 7. Metadata và TTL: vòng đời của key

Metadata `lastAccessedTime` và `maxInactiveInterval` giúp Spring Session tính thời điểm hết hạn. Redis cũng hỗ trợ TTL ở cấp key. Repository kết hợp metadata và cơ chế hết hạn để quản lý vòng đời phiên.

Không nên hiểu rằng một session chỉ có một key duy nhất và Redis TTL luôn là toàn bộ chính sách vòng đời. Các repository Redis có thể tạo key phụ trợ cho expiration, giữ hash chính thêm một khoảng thời gian để xử lý sự kiện hoặc duy trì index. Cấu trúc cụ thể phụ thuộc repository và phiên bản.

Với repository Redis được lập chỉ mục, có thể có key expiration riêng để Redis phát sự kiện hết hạn, và key/hash phục vụ tra cứu phiên. Một số cấu trúc nội bộ được giữ lại lâu hơn TTL logic để bảo đảm sự kiện hết hạn được xử lý. Vì thế, khi quan sát Redis, đừng kết luận phiên còn hợp lệ chỉ vì thấy một key phụ trợ vẫn tồn tại.

TTL của phiên nên được cấu hình thông qua Spring Session hoặc API session phù hợp. Không tự ý chạy `EXPIRE`, `PERSIST` hoặc `DEL` trên key nội bộ để thay đổi vòng đời phiên. Việc chỉnh một key mà không cập nhật metadata, expiration key và index có thể khiến trạng thái không nhất quán.

## 8. Index và dữ liệu phụ trợ

Ngoài hash chính, một repository có thể duy trì index để tìm phiên theo thuộc tính, ví dụ principal name. Điều này hỗ trợ các thao tác như tìm những phiên thuộc về một người dùng hoặc thu hồi các phiên của tài khoản.

Index không phải thuộc tính nghiệp vụ thông thường trong session hash. Nó là cấu trúc phụ trợ do repository quản lý. Khi phiên được tạo, cập nhật hoặc xóa, repository có thể cập nhật index tương ứng.

Không nên tự thêm hoặc xóa thành viên khỏi index bằng lệnh Redis. Nếu index bị sai lệch so với hash phiên, truy vấn tìm phiên có thể trả về ID không còn tồn tại hoặc bỏ sót phiên hợp lệ. Hãy dùng API Spring Session như `FindByIndexNameSessionRepository` nếu repository đang dùng hỗ trợ khả năng tìm theo index.

Một số repository còn dùng Redis Pub/Sub hoặc keyspace notifications để phát hiện session expired/deleted và tạo sự kiện vòng đời. Những cơ chế này phục vụ đồng bộ và quan sát; ứng dụng không nên phụ thuộc trực tiếp vào tên channel hoặc cấu trúc key nội bộ nếu không có yêu cầu tích hợp chuyên biệt.

## 9. Quan sát dữ liệu Redis bằng lệnh chỉ đọc

Khi cần chẩn đoán, có thể dùng `SCAN` để tìm key theo namespace. Tránh dùng `KEYS` trên Redis production vì lệnh này có thể quét toàn bộ keyspace và làm ảnh hưởng độ trễ.

Ví dụ với namespace mặc định:

~~~bash
SCAN 0 MATCH "spring:session:sessions:*" COUNT 100
~~~

Sau khi xác định một key cụ thể từ môi trường test hoặc staging, có thể xem kiểu dữ liệu:

~~~bash
TYPE "spring:session:sessions:<sessionId>"
~~~

Nếu key là hash, có thể xem các trường:

~~~bash
HGETALL "spring:session:sessions:<sessionId>"
~~~

Và kiểm tra TTL:

~~~bash
PTTL "spring:session:sessions:<sessionId>"
~~~

Các lệnh trên chỉ phục vụ quan sát. Giá trị thuộc tính có thể là byte đã tuần tự hóa, không hiển thị thành chuỗi dễ đọc. Không giả định dữ liệu nhị phân là dữ liệu hỏng chỉ vì `redis-cli` hiển thị ký tự lạ.

Khi kiểm tra production:

- Không đưa session ID thật vào ticket, ảnh chụp màn hình hoặc log chia sẻ.
- Không chạy `HGETALL` hàng loạt trên toàn bộ session.
- Không xuất dữ liệu thuộc tính có thể chứa thông tin cá nhân hoặc bí mật.
- Dùng namespace và ID đã được che hoặc dữ liệu giả trong ví dụ.
- Ưu tiên metric tổng hợp như số phiên, TTL, kích thước và lỗi serializer.

## 10. Flush mode, save mode và cập nhật thuộc tính

Spring Session có các chính sách lưu thay đổi phiên. Tùy phiên bản và repository, cấu hình có thể điều khiển thời điểm flush và cách xác định thuộc tính cần lưu. Điều này quan trọng khi ứng dụng giữ một đối tượng mutable trong session.

Ví dụ:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(productId);
~~~

Nếu chỉ sửa nội dung object trong bộ nhớ mà không gọi lại `setAttribute`, việc phát hiện thay đổi phụ thuộc `SaveMode` và cách repository theo dõi thuộc tính. Với chính sách chỉ lưu khi thuộc tính được set, thay đổi bên trong object có thể không được ghi như mong muốn.

Một cách rõ ràng hơn là đặt lại thuộc tính sau khi thay đổi:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(productId);
session.setAttribute("cart", cart);
~~~

Hoặc chọn save mode phù hợp và kiểm thử với đúng repository. Không giả định thay đổi bất kỳ field nào bên trong object luôn tự động được nhận biết.

Flush mode ảnh hưởng thời điểm các thay đổi được gửi tới Redis. Chế độ lưu ngay có thể giảm khoảng thời gian dữ liệu chưa được ghi, nhưng làm tăng số thao tác Redis; chế độ lưu khi request hoàn tất có thể gom thay đổi, nhưng có nghĩa dữ liệu có thể chưa được lưu cho tới giai đoạn cuối request. Hãy cân nhắc độ trễ, request đồng thời và yêu cầu nhất quán của ứng dụng.

## 11. Request đồng thời và cập nhật cùng session

Redis hash hỗ trợ thao tác trên từng field, nhưng điều đó không tự tạo ra một giao dịch nghiệp vụ nguyên tử cho toàn bộ session. Hai request có thể cùng tải một phiên, sửa cùng một thuộc tính và ghi lại ở thời điểm khác nhau. Thay đổi của request ghi sau có thể ghi đè thay đổi của request ghi trước.

Ví dụ:

1. Request A đọc `cart` có hai sản phẩm.
2. Request B cũng đọc cùng giá trị.
3. A thêm sản phẩm X và lưu.
4. B thêm sản phẩm Y dựa trên bản cũ và lưu.
5. Giá trị cuối cùng có thể chỉ chứa Y cùng hai sản phẩm cũ, làm mất cập nhật X.

Với dữ liệu quan trọng hoặc cần cập nhật đồng thời, hãy lưu trạng thái nghiệp vụ trong database với transaction, optimistic locking hoặc cơ chế đồng bộ phù hợp. Session nên giữ mã tham chiếu và trạng thái điều hướng nhỏ. Nếu một thuộc tính session phải được cập nhật bởi nhiều request đồng thời, hãy xác định rõ chính sách merge hoặc serialize cập nhật thay vì dựa vào thứ tự request.

## 12. Tương thích dữ liệu khi rolling deployment

Trong triển khai nhiều instance, các node có thể chạy hai phiên bản ứng dụng trong một khoảng thời gian. Một node cũ có thể ghi thuộc tính theo class hoặc serializer cũ, trong khi node mới tải cùng session.

Để tránh lỗi:

- Giữ cấu trúc thuộc tính ổn định qua các phiên bản nếu có thể.
- Tránh lưu trực tiếp entity hoặc object graph thay đổi thường xuyên.
- Dùng kiểu dữ liệu đơn giản hoặc DTO phiên bản hóa.
- Khi đổi serializer, thiết kế khả năng đọc dữ liệu cũ trong giai đoạn chuyển đổi.
- Không xóa class hoặc đổi tên field khiến phiên cũ không thể giải tuần tự hóa trước khi hết TTL.
- Kiểm thử request luân phiên qua instance cũ và mới trong rolling deployment.

Ví dụ một thuộc tính có thể lưu object với version:

~~~java
public record CheckoutState(
        int schemaVersion,
        String checkoutId,
        String currentStep) {
}
~~~

Khi tải trạng thái, ứng dụng có thể kiểm tra `schemaVersion` và chuyển đổi dữ liệu cũ sang cấu trúc mới. Với Java baseline chưa hỗ trợ record, dùng một DTO thông thường có constructor/getter tương ứng.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Redis có nhiều hash session lớn | Ứng dụng lưu entity, danh sách hoặc payload lớn | Chuyển dữ liệu chính sang database/object storage, session chỉ giữ ID |
| Node mới không đọc được session cũ | Serializer hoặc class thay đổi không tương thích | Hỗ trợ đọc định dạng cũ, migration có kiểm soát hoặc chờ TTL cũ hết |
| Thay đổi object trong session không được lưu | Save mode chỉ nhận thay đổi khi set attribute hoặc repository không phát hiện mutation nội bộ | Gọi lại `setAttribute` và kiểm thử save mode |
| Không tìm thấy phiên theo người dùng | Index principal chưa được cấu hình hoặc dữ liệu index không đồng bộ | Kiểm tra repository/index support và dùng API Spring Session |
| Key phụ trợ còn tồn tại sau khi session hết hạn | Cơ chế expiration/event cleanup có vòng đời khác hash chính | Đối chiếu repository/version; không kết luận chỉ từ một key |
| Session bị ghi đè khi nhiều request chạy cùng lúc | Các request cùng đọc snapshot cũ rồi ghi lại | Đưa dữ liệu nghiệp vụ vào kho có transaction/locking phù hợp |
| Redis key bị trùng giữa ứng dụng | Namespace dùng chung hoặc không phân tách môi trường | Đặt namespace riêng và ổn định cho từng ứng dụng/môi trường |

## 14. Checklist tổ chức dữ liệu phiên

- [ ] Phân biệt rõ metadata do Spring Session quản lý và thuộc tính do ứng dụng đặt.
- [ ] Dùng namespace riêng cho ứng dụng và môi trường.
- [ ] Chỉ lưu dữ liệu nhỏ, cần dùng qua nhiều request.
- [ ] Lưu ID tham chiếu thay vì toàn bộ entity hoặc payload lớn.
- [ ] Tên thuộc tính rõ ràng và không xung đột giữa các module.
- [ ] Serializer thống nhất giữa mọi instance và có kế hoạch migration.
- [ ] Hiểu `SaveMode` và `FlushMode` của cấu hình đang dùng.
- [ ] Không tự sửa key, hash field, expiration key hoặc index nội bộ.
- [ ] Kiểm thử cập nhật đồng thời và rolling deployment.
- [ ] Quan sát Redis bằng `SCAN` và lệnh chỉ đọc; không lộ session ID hoặc dữ liệu nhạy cảm.

Trong Spring Session Data Redis, session thường được tổ chức thành hash gồm metadata vòng đời và các trường thuộc tính đã tuần tự hóa. Namespace tách dữ liệu giữa ứng dụng, còn key hết hạn và index hỗ trợ repository quản lý vòng đời và tìm kiếm. Khi giữ session nhỏ, chọn serializer tương thích và để Spring Session quản lý các cấu trúc nội bộ, ứng dụng sẽ dễ vận hành, nâng cấp và mở rộng trên nhiều instance hơn.
