# Ảnh hưởng của FlushMode, SaveMode và việc đọc thuộc tính

Spring Session lưu trạng thái phiên ngoài JVM để nhiều request và nhiều instance có thể dùng chung HttpSession. Mỗi request có thể đọc hoặc thay đổi các thuộc tính như giỏ hàng, tùy chọn giao diện, thông tin xác thực và tiến độ quy trình. Cách repository ghi những thay đổi này ảnh hưởng trực tiếp đến độ trễ, số lần truy cập Redis/JDBC, lượng dữ liệu serialize và nguy cơ ghi đè khi nhiều request cùng cập nhật một phiên.

Hai cấu hình thường bị nhầm lẫn là FlushMode và SaveMode. FlushMode quyết định **khi nào** thay đổi được đẩy xuống kho lưu trữ. SaveMode quyết định **những thuộc tính nào** được đưa vào lần lưu. Việc đọc thuộc tính cũng có thể ảnh hưởng đến SaveMode: với ON_GET_ATTRIBUTE, thuộc tính đã được đọc được đánh dấu để lưu, giúp ghi nhận các thay đổi bên trong object mutable dù ứng dụng không gọi setAttribute() lại.

Không có một lựa chọn tối ưu cho mọi ứng dụng. Dùng ON_SAVE kết hợp ON_SET_ATTRIBUTE thường tiết kiệm I/O khi ứng dụng cập nhật thuộc tính theo cách tường minh. ON_GET_ATTRIBUTE hữu ích với object mutable được sửa tại chỗ. ALWAYS có thể hỗ trợ code cũ nhưng tăng lượng ghi. IMMEDIATE giảm độ trễ trước khi thay đổi được gửi xuống store nhưng có thể tạo nhiều thao tác ghi trong một request và làm lộ trạng thái trung gian.

## 1. Vòng đời đọc và lưu session

Trong ứng dụng Servlet, Spring Session tích hợp HttpSession thông qua SessionRepositoryFilter. Filter cung cấp một HttpSession wrapper được kết nối với SessionRepository. Khi request cần session, Spring Session tải session từ repository hoặc tạo mới. Khi ứng dụng đọc và cập nhật thuộc tính, wrapper theo dõi các thay đổi theo chính sách của repository.

Với cấu hình lưu khi kết thúc request, các thay đổi được đẩy xuống repository khi response được commit hoặc khi filter gọi thao tác save theo lifecycle. Luồng khái quát:

    HTTP request
        |
        v
    SessionRepositoryFilter
        |
        v
    Tải Session từ Redis/JDBC
        |
        v
    Controller đọc / sửa thuộc tính
        |
        v
    Session wrapper theo dõi thay đổi
        |
        v
    Response commit / repository.save()
        |
        v
    Flush các thuộc tính theo SaveMode
        |
        v
    Redis hoặc JDBC

Với code gọi SessionRepository trực tiếp, ứng dụng phải gọi save(session) theo contract của repository. Với HttpSession integration, không gọi một phương thức save không tồn tại trên Servlet HttpSession; Spring Session filter điều phối việc lưu.

## 2. FlushMode điều khiển thời điểm ghi

FlushMode có hai lựa chọn phổ biến:

- ON_SAVE: thay đổi được ghi khi SessionRepository.save(session) được gọi.
- IMMEDIATE: thay đổi được ghi sớm nhất có thể ngay khi session thay đổi, tùy cách repository triển khai.

ON_SAVE gom các thay đổi trong request và thường phù hợp với ứng dụng web thông thường. Khi request cập nhật nhiều thuộc tính, repository có thể lưu chúng tại ranh giới save thay vì gửi một lần ghi cho từng thao tác setAttribute.

IMMEDIATE giảm khoảng thời gian thay đổi chỉ tồn tại trong bộ nhớ của request. Điều này có thể hữu ích nếu một thành phần khác cần thấy thay đổi trước khi response kết thúc hoặc nếu ứng dụng có luồng lưu session tường minh giữa request. Đổi lại, nhiều thay đổi nhỏ có thể tạo nhiều thao tác I/O, tăng latency và tải lên store.

FlushMode không quyết định thuộc tính nào được lưu. Nó chỉ quyết định thời điểm repository đẩy những thay đổi đã được đánh dấu xuống store.

## 3. SaveMode điều khiển thuộc tính nào được ghi

SaveMode quyết định tập thuộc tính session được đưa vào thao tác lưu. Các lựa chọn phổ biến:

| SaveMode | Hành vi |
|---|---|
| ON_SET_ATTRIBUTE | Lưu thuộc tính được đặt qua Session.setAttribute() |
| ON_GET_ATTRIBUTE | Lưu thuộc tính đã được đặt hoặc đã được đọc qua Session.getAttribute() |
| ALWAYS | Lưu tất cả thuộc tính của session trong lần save |

ON_SET_ATTRIBUTE phù hợp khi code thay thế thuộc tính bằng một giá trị mới mỗi khi cập nhật. Repository không phải ghi lại các thuộc tính chỉ được đọc.

ON_GET_ATTRIBUTE hỗ trợ object mutable. Khi ứng dụng đọc một thuộc tính, repository đánh dấu thuộc tính đó để được lưu ở lần flush/save. Nếu code sửa object tại chỗ sau khi đọc mà không gọi setAttribute() lại, thay đổi vẫn có thể được ghi.

ALWAYS yêu cầu lưu toàn bộ thuộc tính trong mỗi lần save. Đây là lựa chọn dễ hiểu với code legacy không có quy tắc cập nhật nhất quán, nhưng thường có chi phí serialize và ghi cao nhất.

## 4. Phân biệt hai trục cấu hình

Có thể ghi nhớ:

- FlushMode = thời điểm ghi.
- SaveMode = phạm vi thuộc tính ghi.

Ví dụ:

| Cấu hình | Khi nào ghi? | Ghi thuộc tính nào? |
|---|---|---|
| ON_SAVE + ON_SET_ATTRIBUTE | Khi repository save | Thuộc tính được set |
| ON_SAVE + ON_GET_ATTRIBUTE | Khi repository save | Thuộc tính được set hoặc được đọc |
| ON_SAVE + ALWAYS | Khi repository save | Tất cả thuộc tính |
| IMMEDIATE + ON_SET_ATTRIBUTE | Sớm nhất có thể sau thay đổi | Thuộc tính được set |
| IMMEDIATE + ON_GET_ATTRIBUTE | Theo cơ chế immediate của repository | Thuộc tính được set hoặc được đánh dấu khi đọc |
| IMMEDIATE + ALWAYS | Theo cơ chế immediate của repository | Toàn bộ thuộc tính theo semantics implementation |

Hai trục có thể phối hợp nhưng không thay thế nhau. Chọn IMMEDIATE không tự làm repository lưu mọi thuộc tính; chọn ALWAYS cũng không có nghĩa dữ liệu được ghi ngay khi setAttribute nếu FlushMode vẫn là ON_SAVE.

Với IMMEDIATE và ON_GET_ATTRIBUTE, cần kiểm tra semantics cụ thể của phiên bản repository. Việc đánh dấu thuộc tính khi đọc và thời điểm flush có thể tạo hành vi khác với ON_SAVE, đặc biệt nếu ứng dụng sửa object sau khi đọc. Hãy kiểm thử thay vì suy đoán từ tên enum.

## 5. Cấu hình Redis với FlushMode và SaveMode

Ví dụ cấu hình Servlet application dùng Spring Session Redis:

~~~java
@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE,
    redisNamespace = "shop:prod:spring-session"
)
public class SessionConfiguration {
}
~~~

Các import tương ứng nằm trong Spring Session:

~~~java
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;
~~~

Cấu hình trên phù hợp với code cập nhật thuộc tính theo cách tường minh: mỗi thay đổi quan trọng gọi setAttribute(), rồi Spring Session lưu ở ranh giới save. Cần bảo đảm mọi instance của cùng ứng dụng dùng cấu hình tương thích.

Spring Boot cũng có các property để cấu hình Redis session theo phiên bản. Nếu dùng auto-configuration, kiểm tra metadata của đúng phiên bản Boot thay vì bật annotation cùng lúc một cách không chủ đích. Không tạo hai SessionRepositoryFilter hoặc hai repository cạnh tranh.

## 6. Cập nhật thuộc tính theo cách ON_SET_ATTRIBUTE có thể theo dõi

Với ON_SET_ATTRIBUTE, cách rõ ràng là tạo giá trị mới hoặc gọi setAttribute() sau khi cập nhật:

~~~java
Cart cart = (Cart) session.getAttribute("cart");

if (cart == null) {
    cart = new Cart();
}

cart.add(product);

session.setAttribute("cart", cart);
~~~

Dòng setAttribute() thông báo cho session wrapper rằng thuộc tính cart đã được đặt và cần lưu. Cách này cũng dễ đọc trong code review: nơi thay đổi trạng thái được thể hiện rõ.

Với object bất biến, có thể tạo bản mới:

~~~java
Cart current = (Cart) session.getAttribute("cart");
Cart updated = current.adding(product);

session.setAttribute("cart", updated);
~~~

Cách cập nhật bất biến giảm nguy cơ thay đổi object mà repository không nhận ra. Nó cũng giúp suy luận tốt hơn khi nhiều request cùng xử lý, dù bản thân nó không giải quyết lost update giữa các request.

Nếu code chỉ sửa object bên trong rồi không gọi setAttribute(), ON_SET_ATTRIBUTE có thể không biết thuộc tính đã thay đổi. Đây là nguyên nhân thường gặp khiến dữ liệu trong request hiện tại đúng nhưng request tiếp theo lại đọc giá trị cũ.

## 7. Vì sao đọc thuộc tính có thể quan trọng?

Java object được lưu trong session thường là object mutable. Khi gọi getAttribute(), ứng dụng nhận tham chiếu đến object đó. Thay đổi qua tham chiếu không nhất thiết gọi lại API của Session:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(product);
// Không gọi session.setAttribute("cart", cart)
~~~

Với ON_SET_ATTRIBUTE, repository chỉ biết thuộc tính được đặt khi setAttribute() được gọi. Thao tác cart.add() chỉ thay đổi object trong bộ nhớ; wrapper có thể không nhận được tín hiệu dirty.

Với ON_GET_ATTRIBUTE, thao tác đọc qua getAttribute() đánh dấu thuộc tính để được lưu trong lần save. Khi request kết thúc và session được lưu, repository có thể ghi lại object cart đã bị sửa tại chỗ.

Đây là lý do SaveMode.ON_GET_ATTRIBUTE hữu ích cho code dùng collection, map hoặc object mutable. Tuy nhiên, một thuộc tính chỉ được đọc mà không thay đổi cũng có thể bị đưa vào lần lưu, làm tăng I/O.

## 8. Ví dụ cấu hình ON_GET_ATTRIBUTE cho object mutable

Ví dụ:

~~~java
@Configuration
@EnableRedisHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_GET_ATTRIBUTE
)
public class MutableSessionConfiguration {
}
~~~

Và code cập nhật:

~~~java
public void addProduct(HttpSession session, Product product) {
    Cart cart = (Cart) session.getAttribute("cart");

    if (cart == null) {
        cart = new Cart();
        session.setAttribute("cart", cart);
    }

    cart.add(product);
}
~~~

Khi cart đã tồn tại, getAttribute("cart") đánh dấu thuộc tính để lưu theo ON_GET_ATTRIBUTE. Sau khi cart.add() sửa object, lần save cuối request có thể ghi phiên bản đã cập nhật.

Nếu cart mới được tạo, setAttribute() vẫn đánh dấu thuộc tính. Vì vậy cả nhánh tạo mới và nhánh cập nhật đều có đường lưu.

Hãy xác nhận bằng integration test trên repository thật. Đừng chỉ kiểm tra object trong cùng request, vì object trong bộ nhớ có thể đã thay đổi ngay cả khi thay đổi chưa được ghi xuống Redis.

## 9. Đọc thuộc tính nhưng không sửa vẫn có thể tạo ghi

ON_GET_ATTRIBUTE có chi phí đặc biệt đối với request đọc dữ liệu. Ví dụ controller chỉ hiển thị giỏ hàng:

~~~java
@GetMapping("/cart")
public Cart viewCart(HttpSession session) {
    return (Cart) session.getAttribute("cart");
}
~~~

Nếu SaveMode là ON_GET_ATTRIBUTE, cart đã đọc có thể được đánh dấu để ghi khi session được lưu. Vì thế một request chỉ đọc vẫn có thể gây serialization và write vào repository.

Nếu người dùng mở nhiều tab hoặc frontend gọi nhiều endpoint song song, các request đọc cùng thuộc tính có thể tạo thêm lượng ghi đáng kể. Với session chứa object lớn, chi phí này dễ trở thành nút thắt.

Đừng chọn ON_GET_ATTRIBUTE chỉ vì code có getAttribute(). Chỉ dùng khi có thuộc tính mutable thực sự được sửa tại chỗ và không thể dễ dàng chuyển sang cập nhật tường minh.

## 10. SaveMode.ALWAYS và chi phí ghi toàn bộ

ALWAYS lưu tất cả thuộc tính trong lần save, bất kể thuộc tính có được đặt hoặc đọc trong request hay không. Nó có thể giúp code cũ hoạt động khi nhiều nơi giữ tham chiếu mutable và thay đổi object mà không thông báo lại cho session wrapper.

Đổi lại:

- Nhiều thuộc tính không liên quan cũng bị serialize.
- Read-only request có thể tạo write toàn bộ session.
- Session lớn làm tăng băng thông và thời gian ghi.
- Nhiều request đồng thời có thể ghi các snapshot cũ lên nhau.
- Tải Redis/JDBC tăng theo số request có session.

Ví dụ cấu hình:

~~~java
@EnableRedisHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ALWAYS
)
class LegacySessionConfiguration {
}
~~~

ALWAYS nên được xem là lựa chọn có chủ đích cho code legacy hoặc trường hợp đã đo được lợi ích, không phải cấu hình mặc định để “chắc chắn không mất dữ liệu”. Nó không cung cấp locking, version check hay merge thuộc tính.

## 11. FlushMode.ON_SAVE và ranh giới request

ON_SAVE gom các thay đổi đã được đánh dấu và ghi khi repository.save() được gọi. Trong Servlet integration, Spring Session filter quản lý thời điểm lưu theo response/request lifecycle. Điều này thường tránh ghi Redis hoặc JDBC cho mỗi lần setAttribute() trong cùng một request.

Ví dụ controller thay đổi nhiều thuộc tính:

~~~java
session.setAttribute("checkout.step", "ADDRESS");
session.setAttribute("checkout.address", address);
session.setAttribute("checkout.updatedAt", Instant.now());
~~~

Với ON_SAVE, các thay đổi được lưu ở ranh giới save. Repository có thể dùng một hoặc nhiều lệnh nội bộ; không nên giả định tất cả thay đổi trở thành một transaction nguyên tử chỉ vì save() được gọi một lần.

Nếu code gọi SessionRepository trực tiếp, phải gọi save(session) trong pipeline đồng bộ hoặc reactive tương ứng. ON_SAVE không tự lưu một Session tùy ý mà service chưa bao giờ gửi tới repository.save().

## 12. FlushMode.IMMEDIATE và write amplification

IMMEDIATE yêu cầu repository đẩy thay đổi xuống store sớm nhất có thể. Với request đặt nhiều thuộc tính:

~~~java
session.setAttribute("profile.name", name);
session.setAttribute("profile.locale", locale);
session.setAttribute("profile.timezone", timezone);
~~~

Tùy implementation, các thay đổi có thể tạo nhiều lần ghi thay vì được gom đến save cuối request. Điều này làm tăng:

- Số lệnh Redis hoặc câu lệnh JDBC.
- Round-trip mạng.
- Serialization và chi phí CPU.
- Connection occupancy.
- Latency ở các request có nhiều thay đổi.

IMMEDIATE có thể giảm khoảng thời gian dữ liệu chỉ tồn tại trong bộ nhớ của node xử lý request. Nhưng nếu store chậm hoặc lỗi, request có thể gặp lỗi ngay tại thao tác cập nhật thay vì cuối response. Hành vi chính xác phụ thuộc repository và phiên bản.

Không chọn IMMEDIATE chỉ để tăng độ bền dữ liệu. Độ bền thực tế còn phụ thuộc Redis persistence/replication hoặc transaction và durability của database. Flush sớm không thay thế backup, replication policy hay transaction nghiệp vụ.

## 13. IMMEDIATE có thể làm lộ trạng thái trung gian

Giả sử một request cập nhật trạng thái checkout qua ba bước:

1. Đặt checkout.status = ADDRESS.
2. Ghi địa chỉ giao hàng.
3. Đặt checkout.status = PAYMENT.

Với IMMEDIATE, một request khác có thể quan sát một phần thay đổi trước khi toàn bộ logic nghiệp vụ hoàn tất, tùy thứ tự flush và cách repository lưu. Nếu một bước sau thất bại, store có thể vẫn giữ một phần trạng thái đã ghi.

ON_SAVE giúp gom thay đổi trong phạm vi request trước khi save, nhưng không bảo đảm atomicity cho toàn bộ quy trình hoặc cho nhiều request. Nếu trạng thái cần chuyển đổi nguyên tử, hãy dùng transaction nghiệp vụ hoặc một aggregate có version ở database chuyên dụng.

Session nên chứa trạng thái UI/tạm thời. Không dùng FlushMode để biến nhiều thuộc tính session thành một transaction checkout, chuyển tiền hoặc cập nhật tồn kho.

## 14. So sánh các tổ hợp thường gặp

| Nhu cầu | Cấu hình nên cân nhắc | Lý do |
|---|---|---|
| Giá trị bất biến hoặc được thay thế bằng setAttribute | ON_SAVE + ON_SET_ATTRIBUTE | Ít ghi, dễ kiểm soát |
| Object mutable được đọc rồi sửa tại chỗ | ON_SAVE + ON_GET_ATTRIBUTE | Đọc đánh dấu thuộc tính để lưu ở cuối request |
| Code legacy thay đổi nhiều object mà không set lại | ON_SAVE + ALWAYS | Bao phủ thuộc tính nhưng chi phí cao |
| Thành phần khác cần thấy thay đổi sớm | IMMEDIATE + SaveMode phù hợp | Giảm thời gian chờ trước khi ghi |
| Session lớn, nhiều request đọc | ON_SAVE + ON_SET_ATTRIBUTE | Tránh ghi lại các thuộc tính chỉ được đọc |
| Dữ liệu nghiệp vụ cần atomicity | Không dựa vào tổ hợp session mode | Dùng transaction/store nghiệp vụ |

Bảng này là định hướng. Hãy xác minh default và semantics của repository cụ thể. Đặc biệt, IMMEDIATE kết hợp ON_GET_ATTRIBUTE có thể có hành vi phụ thuộc thời điểm đánh dấu và flush; kiểm thử với đúng phiên bản trước khi sử dụng.

## 15. Ảnh hưởng của kích thước thuộc tính

Chi phí lưu session phụ thuộc số lượng và kích thước thuộc tính. Một session có vài chuỗi ngắn sẽ khác nhiều so với session chứa một object graph lớn gồm giỏ hàng, danh sách kết quả tìm kiếm và entity liên kết.

Ví dụ, ON_GET_ATTRIBUTE có thể làm một request đọc thuộc tính search.results lớn cũng gây serialization/write. ALWAYS có thể ghi lại toàn bộ các thuộc tính lớn trong mỗi lần save. IMMEDIATE có thể gửi nhiều bản cập nhật trong một request.

Các biện pháp:

- Lưu ID/reference thay vì toàn bộ entity hoặc danh sách lớn.
- Giữ DTO session nhỏ và ổn định.
- Không lưu file, ảnh hoặc binary lớn trong session.
- Không serialize proxy JPA hoặc object graph vòng.
- Dùng immutable value nếu có thể.
- Tách cache có thể tái tạo khỏi session xác thực.
- Đo payload serialized thay vì chỉ đếm số thuộc tính.

Nếu một thuộc tính lớn chỉ phục vụ một trang, cân nhắc tải dữ liệu từ service/cache theo ID thay vì giữ trong session qua mọi request.

## 16. Ảnh hưởng lên Redis

Với Redis, thay đổi session thường được lưu dưới dạng key/hash và metadata expiration theo implementation. SaveMode quyết định thuộc tính nào được ghi; FlushMode quyết định thời điểm các thay đổi được gửi.

ON_GET_ATTRIBUTE và ALWAYS có thể làm tăng số field được ghi và số byte serialize. IMMEDIATE có thể tăng số round-trip hoặc lệnh cập nhật. Với nhiều node, tăng write load có thể ảnh hưởng latency của các request khác dùng cùng Redis.

Theo dõi:

- Lệnh ghi trên mỗi request có session.
- Redis command latency p50/p95/p99.
- Bytes vào/ra.
- CPU Redis và application.
- Số key/session và memory usage.
- Serialization time và payload size.
- Connection pool active/pending.
- Tỷ lệ lỗi ghi và timeout.

Không suy luận chi phí chỉ từ số lần gọi setAttribute trong code. Repository có thể gộp hoặc tách lệnh theo flush mode, serializer và phiên bản. Đo trên Redis thật hoặc môi trường tương thích production.

## 17. Ảnh hưởng lên JDBC

Với JDBC repository, việc ghi thuộc tính có thể tạo thao tác SQL cập nhật metadata và bảng attributes. Cách implementation phát lệnh và transaction phụ thuộc phiên bản Spring Session, database và cấu hình.

ON_GET_ATTRIBUTE có thể làm các thuộc tính được đọc tham gia lần lưu. ALWAYS có thể làm nhiều thuộc tính bị ghi lại. IMMEDIATE có thể tăng số lần SQL hoặc transaction ngắn. Hệ quả là:

- Tăng row update và index maintenance.
- Tăng transaction/connection time.
- Tăng lock contention khi nhiều request cùng sửa session.
- Tăng WAL/redo log và I/O database.
- Làm cleanup cạnh tranh với các thao tác save.

Đo số SQL statement, rows affected, lock wait, transaction duration và connection pool. Không giả định JDBC và Redis có cùng write amplification chỉ vì dùng cùng enum.

## 18. Ảnh hưởng của việc đọc thuộc tính lên tải ứng dụng

Để đánh giá ON_GET_ATTRIBUTE, cần đo cả request đọc lẫn request ghi. Một dashboard có thể đọc 5 thuộc tính session ở mỗi request; nếu mỗi lần đọc đánh dấu thuộc tính để lưu, tải ghi có thể tăng dù người dùng không thay đổi gì.

Phân tích theo loại endpoint:

| Endpoint | Hành vi session | Cấu hình cần cân nhắc |
|---|---|---|
| Trang hồ sơ chỉ đọc | Đọc locale/theme | ON_SET_ATTRIBUTE tránh write không cần thiết |
| Cập nhật giỏ hàng mutable | Đọc rồi sửa Cart tại chỗ | ON_GET_ATTRIBUTE hoặc setAttribute lại |
| Đổi locale | Thay một giá trị nhỏ | ON_SET_ATTRIBUTE |
| API stateless | Không cần session | Tránh tạo/tải session nếu có thể |
| Legacy workflow | Nhiều object mutable khó sửa | Đo ALWAYS trước khi chấp nhận chi phí |

Nếu code có thể sửa theo cách rõ ràng, setAttribute sau cập nhật thường giúp giữ SaveMode tiết kiệm hơn và làm ý định code dễ kiểm tra.

## 19. Cập nhật đồng thời và stale write

FlushMode và SaveMode không phải cơ chế khóa. Chúng không ngăn hai request cùng tải một snapshot rồi lưu theo thứ tự bất kỳ.

Ví dụ:

- Request A tải cart với hai sản phẩm.
- Request B tải cùng cart, thêm sản phẩm thứ ba và lưu.
- Request A sửa một thuộc tính khác nhưng dùng ALWAYS, ghi lại snapshot cart cũ.
- Sản phẩm thứ ba có thể bị mất.

ON_SET_ATTRIBUTE giảm phạm vi thuộc tính được ghi nếu request A không set cart. ON_GET_ATTRIBUTE có thể vẫn đánh dấu cart nếu A đọc nó. ALWAYS có phạm vi ghi rộng nhất. Tuy vậy, nếu A và B cùng set một thuộc tính, last-write-wins vẫn có thể xảy ra.

Nếu dữ liệu cần tính đúng tuyệt đối, dùng optimistic locking, atomic operation hoặc transaction nghiệp vụ. Không coi SaveMode là cơ chế merge hay compare-and-set.

## 20. Lỗi thường gặp với object mutable

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Sửa List nhưng request sau thấy dữ liệu cũ | ON_SET_ATTRIBUTE không nhận ra thay đổi trong object | Gọi setAttribute lại hoặc dùng ON_GET_ATTRIBUTE |
| Request chỉ đọc nhưng Redis có nhiều write | ON_GET_ATTRIBUTE đánh dấu thuộc tính được đọc | Chỉ dùng khi cần; chuyển sang immutable/explicit set |
| Mỗi request ghi cả session lớn | SaveMode.ALWAYS | Chuyển sang ON_SET_ATTRIBUTE nếu code cho phép |
| Nhiều lệnh ghi trong một request | FlushMode.IMMEDIATE | Dùng ON_SAVE nếu không cần visibility sớm |
| Node khác thấy trạng thái chưa hoàn chỉnh | IMMEDIATE ghi từng thay đổi | Gộp trạng thái hoặc dùng transaction nghiệp vụ |
| Cập nhật bị mất khi request chạy đồng thời | Stale snapshot và last-write-wins | Versioning, lock hoặc atomic update |
| Lưu thất bại ở cuối response | ON_SAVE phát sinh lỗi tại ranh giới save | Theo dõi lỗi persistence và không bỏ qua |
| Session attribute deserialize chậm | Payload lớn hoặc serializer tốn CPU | Thu nhỏ DTO và đo serialization |

Không sửa lỗi mất thuộc tính bằng cách chuyển thẳng sang ALWAYS trước khi xác định nguyên nhân. Cấu hình đó có thể che giấu lỗi tracking nhưng đồng thời tăng ghi và làm stale overwrite nghiêm trọng hơn.

## 21. Kiểm thử SaveMode theo hành vi thực tế

Một integration test nên dùng repository thật hoặc môi trường tương thích với production và nhiều request riêng biệt. Mỗi request cần tải lại session từ store, không dùng cùng object trong bộ nhớ.

Các tình huống:

1. Với ON_SET_ATTRIBUTE, đặt thuộc tính bằng setAttribute và xác nhận request sau đọc được giá trị mới.
2. Với ON_SET_ATTRIBUTE, đọc object mutable rồi sửa tại chỗ nhưng không set lại; xác nhận test tái hiện việc thay đổi không được lưu.
3. Với ON_GET_ATTRIBUTE, lặp lại trường hợp trên và xác nhận thay đổi được lưu sau khi thuộc tính đã được đọc.
4. Với ON_GET_ATTRIBUTE, chỉ đọc thuộc tính rồi đo xem có phát sinh save/write hay không.
5. Với ALWAYS, sửa object mutable và xác nhận thuộc tính được ghi trong lần save.
6. So sánh session có một thuộc tính nhỏ với session có payload lớn.
7. Kiểm tra nhiều request đọc cùng thuộc tính.
8. Kiểm tra hai request cập nhật cùng thuộc tính và ghi nhận stale write.
9. Kiểm tra thuộc tính được set nhưng request lỗi trước response commit.
10. Kiểm tra serialization error và repository unavailable.
11. Lặp lại trên Redis và JDBC nếu cả hai store được hỗ trợ.
12. Chạy hai instance để xác nhận dữ liệu đọc lại từ node khác.

Mock repository giúp kiểm tra lời gọi API nhưng không chứng minh serialization, Redis commands, SQL statements, TTL và concurrency semantics.

## 22. Kiểm thử FlushMode và ranh giới ghi

Để phân biệt ON_SAVE và IMMEDIATE:

1. Gửi request cập nhật nhiều thuộc tính.
2. Dùng test observer hoặc repository instrumentation để ghi nhận thời điểm save/flush.
3. Với ON_SAVE, xác nhận các thay đổi được đẩy tại ranh giới save.
4. Với IMMEDIATE, xác nhận thay đổi được gửi sớm theo semantics repository.
5. Tạo request thứ hai đọc session trong khi request đầu đang cập nhật để quan sát khả năng nhìn thấy trạng thái trung gian.
6. Giả lập lỗi store giữa các lần cập nhật.
7. Đo số lệnh và latency trên mỗi request.
8. Kiểm tra response và session store khi request bị hủy hoặc node dừng.

Không dùng Thread.sleep() làm bằng chứng về thứ tự flush. Dùng latch, barrier, test hook hoặc instrumentation để điều khiển chính xác các điểm trong request.

## 23. Đo hiệu năng có thể so sánh

Khi so sánh các cấu hình, giữ các yếu tố khác giống nhau:

- Cùng số node và số request đồng thời.
- Cùng session payload và serializer.
- Cùng repository/store version.
- Cùng timeout, namespace và network path.
- Cùng tỷ lệ request đọc và ghi.
- Cùng dữ liệu khởi tạo và thời gian warm-up.

Các chỉ số nên thu thập:

| Chỉ số | Mục đích |
|---|---|
| Request latency p50/p95/p99 | Nhìn tác động lên người dùng |
| Repository save count/request | Đo tần suất ghi |
| Bytes serialized/session | Đo chi phí payload |
| Attribute count saved | Đo phạm vi SaveMode |
| Redis commands hoặc SQL statements | Đo I/O store |
| CPU serialize/deserialize | Đo chi phí xử lý object |
| Connection wait/hold time | Đo áp lực pool |
| Error/timeout rate | Phát hiện cấu hình quá tải |
| Stale update/conflict count | Đánh giá tính nhất quán |

So sánh ON_SAVE + ON_SET_ATTRIBUTE, ON_SAVE + ON_GET_ATTRIBUTE, ON_SAVE + ALWAYS và IMMEDIATE với SaveMode phù hợp. Đừng chỉ đo throughput; cấu hình có thể tăng throughput nhưng làm mất cập nhật mutable hoặc tạo stale write.

## 24. Chọn cấu hình theo kiểu dữ liệu session

Một cách tiếp cận thực tế:

**Dữ liệu bất biến hoặc cập nhật bằng setAttribute**

Dùng ON_SAVE + ON_SET_ATTRIBUTE. Đây thường là lựa chọn hiệu quả vì chỉ các thuộc tính được thay thế rõ ràng mới cần ghi.

**Object mutable được sửa tại chỗ**

Ưu tiên sửa code để gọi setAttribute lại hoặc tạo object bất biến mới. Nếu không thể thay đổi code, cân nhắc ON_GET_ATTRIBUTE và đo write amplification do read.

**Code legacy không kiểm soát được cách sửa thuộc tính**

ALWAYS có thể là giải pháp chuyển tiếp. Đo payload, write rate và concurrency trước khi triển khai rộng; lập kế hoạch giảm phụ thuộc vào cấu hình này.

**Cần thay đổi xuất hiện sớm ở node khác**

Cân nhắc IMMEDIATE khi yêu cầu thực sự cần visibility trước ranh giới save. Xác định rằng nhiều thay đổi có thể được ghi riêng và trạng thái trung gian có thể quan sát được. Nếu cần atomicity, dùng kho dữ liệu nghiệp vụ.

**Request đọc nhiều và session lớn**

Tránh ON_GET_ATTRIBUTE và ALWAYS nếu không cần. Dùng ON_SET_ATTRIBUTE, giảm kích thước session và không tạo session cho endpoint stateless.

## 25. Lưu ý khi dùng JDBC và Redis trong cùng hệ thống

Một ứng dụng thường chỉ chọn một SessionRepository chính cho một Web application context. Nếu có nhiều ứng dụng hoặc profile dùng store khác nhau, mỗi cấu hình cần được kiểm soát để không tạo filter/repository trùng.

FlushMode và SaveMode có thể được hỗ trợ bởi các repository khác nhau, nhưng cách chúng chuyển thành Redis command hoặc SQL statement là implementation-specific. Kiểm tra API, annotation và configuration property của phiên bản Spring Session đang triển khai. Đừng suy ra một cấu hình annotation Redis có thể dùng nguyên xi cho JDBC hoặc ngược lại.

Nếu thay store trong test, cần kiểm tra lại:
- Thời điểm lưu.
- Thuộc tính nào được ghi.
- Serialization.
- Transaction boundary.
- TTL/expiration.
- Hành vi khi hai request cập nhật đồng thời.
- Số thao tác I/O và latency.

## 26. Quy trình tối ưu có kiểm soát

1. Đo baseline với FlushMode và SaveMode hiện tại.
2. Xác định thuộc tính mutable và vị trí code chỉ sửa object tại chỗ.
3. Sửa code để gọi setAttribute hoặc dùng immutable value nếu có thể.
4. Thử ON_SAVE + ON_SET_ATTRIBUTE và xác minh dữ liệu qua request mới.
5. Nếu vẫn cần tracking khi đọc, thử ON_GET_ATTRIBUTE và đo write phát sinh từ read-only request.
6. Chỉ thử ALWAYS khi có lý do tương thích legacy và đã đo payload/write rate.
7. Chỉ thử IMMEDIATE khi yêu cầu visibility sớm có căn cứ.
8. Kiểm tra trạng thái trung gian và lỗi store.
9. Kiểm thử concurrency và stale write trên nhiều instance.
10. So sánh latency, throughput, repository writes, serialized bytes và error rate.
11. Triển khai canary, theo dõi metrics và giữ khả năng rollback.
12. Ghi lại cấu hình đã chọn cùng giả định về kiểu thuộc tính.

Không tối ưu chỉ dựa trên một benchmark nhỏ. Session payload và tỷ lệ request đọc/ghi trong production thường khác môi trường dev.

## Kết luận

FlushMode và SaveMode giải quyết hai vấn đề khác nhau. FlushMode.ON_SAVE trì hoãn ghi đến khi repository.save() được gọi; IMMEDIATE đẩy thay đổi sớm hơn nhưng có thể làm tăng I/O và để lộ trạng thái trung gian. SaveMode.ON_SET_ATTRIBUTE chỉ lưu thuộc tính được đặt tường minh; ON_GET_ATTRIBUTE còn đánh dấu thuộc tính được đọc để hỗ trợ object mutable bị sửa tại chỗ; ALWAYS lưu mọi thuộc tính và thường tốn kém nhất. Đọc thuộc tính vì thế có thể biến một request tưởng như read-only thành một request có write. Hãy ưu tiên cập nhật tường minh hoặc immutable object, chọn mode theo dữ liệu thực tế, đo Redis/JDBC operations và serialization, rồi kiểm thử concurrency để bảo đảm tối ưu hiệu năng không làm mất hoặc ghi đè trạng thái phiên.

## Tài liệu tham khảo

- Spring Session Reference: https://docs.spring.io/spring-session/reference/
- Spring Session Redis Configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session API - FlushMode: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FlushMode.html
- Spring Session API - SaveMode: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SaveMode.html
- Spring Session Redis API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/config/annotation/web/http/EnableRedisHttpSession.html
