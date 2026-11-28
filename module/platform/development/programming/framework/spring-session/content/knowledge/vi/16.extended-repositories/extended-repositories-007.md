# Tuần tự hóa, lớp dữ liệu và tương thích giữa các nút

Spring Session cho phép nhiều instance của một ứng dụng cùng sử dụng một kho lưu trữ phiên. Một instance có thể ghi session, trong khi request tiếp theo được load balancer chuyển đến instance khác. Để luồng này hoạt động, mọi node phải hiểu cùng cấu trúc session và có thể đọc dữ liệu mà node còn lại đã ghi. Đây là vấn đề về tuần tự hóa, thiết kế lớp dữ liệu và tương thích giữa các phiên bản ứng dụng.

Spring Session cung cấp abstraction `SessionRepository` để tạo, tìm, lưu và xóa session. Repository cụ thể quyết định cách lưu dữ liệu: Redis có thể dùng `RedisSerializer`, JDBC chuyển thuộc tính thành bytes qua converter, còn repository tự triển khai có thể dùng định dạng hoặc schema riêng. Dù chọn cơ chế nào, dữ liệu được ghi vào kho dùng chung phải có hợp đồng ổn định giữa các node.

## 1. Vì sao tương thích giữa các node quan trọng?

Trong ứng dụng chỉ có một instance, object session thường được tạo và đọc bởi cùng một phiên bản code trong một JVM. Khi triển khai nhiều instance hoặc rolling deployment, tình huống thay đổi:

- Node A phiên bản cũ ghi session.
- Node B phiên bản mới đọc session đó.
- Node B cập nhật thuộc tính rồi lưu lại.
- Request tiếp theo có thể đến Node A và Node A phải đọc được dữ liệu Node B vừa ghi.

Vì vậy, tương thích không chỉ là khả năng đọc dữ liệu cũ của phiên bản mới. Trong giai đoạn hai phiên bản cùng chạy, cần xem xét cả chiều ngược lại: node cũ có thể phải đọc dữ liệu do node mới ghi.

Nếu serializer hoặc class model không tương thích, metadata session có thể vẫn tìm thấy nhưng việc khôi phục một thuộc tính có thể thất bại. Hệ quả có thể là lỗi request, mất trạng thái giỏ hàng, người dùng bị yêu cầu đăng nhập lại hoặc lỗi xác thực nếu dữ liệu SecurityContext không thể khôi phục.

~~~mermaid
flowchart LR
    A[Node A - phiên bản cũ] -->|ghi session| R[(Kho session dùng chung)]
    R -->|đọc session| B[Node B - phiên bản mới]
    B -->|cập nhật và ghi| R
    R -->|request kế tiếp| A
    A -->|phải deserialize được| R
~~~

Kho lưu trữ dùng chung tạo ra một hợp đồng dữ liệu giữa các tiến trình. Phiên bản code, serializer, classpath và schema đều là một phần của hợp đồng đó.

## 2. Phân biệt Session API, lớp dữ liệu và định dạng lưu trữ

Ba lớp khái niệm cần được tách biệt:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Session API | Mô tả thao tác và trạng thái phiên mà ứng dụng sử dụng | `Session`, `MapSession`, `SessionRepository` |
| Lớp dữ liệu | Mô hình hóa thuộc tính ứng dụng đặt trong session | `UserSessionContext`, `CartSnapshot` |
| Định dạng lưu trữ | Biểu diễn object thành bytes hoặc cấu trúc có thể lưu | Java serialization, JSON, converter riêng |

`SessionRepository` không bắt buộc mọi implementation phải dùng cùng một định dạng serialization. Một repository Redis, repository JDBC và repository tùy chỉnh có thể lưu cùng dữ liệu theo các cách khác nhau. Nhưng trong cùng một nhóm node dùng chung repository, tất cả node phải tương thích với định dạng thực tế đang được ghi.

`Session` cung cấp các thao tác thuộc tính theo tên, ví dụ `getAttribute`, `setAttribute` và `removeAttribute`. Giá trị thuộc tính là object; việc object có cần triển khai `Serializable` hay không phụ thuộc repository và serializer. Không nên kết luận rằng mọi `SessionRepository` đều yêu cầu Java serialization.

## 3. Hợp đồng của SessionRepository

Repository chuẩn hóa vòng đời session qua các thao tác chính:

| Thao tác | Ý nghĩa |
|---|---|
| `createSession()` | Tạo một đối tượng session mới |
| `save(session)` | Lưu session hoặc các thay đổi của nó |
| `findById(id)` | Tìm session theo định danh |
| `deleteById(id)` | Xóa session theo định danh |

Một implementation lưu trữ phân tán phải bảo đảm các thao tác này có ý nghĩa nhất quán khi được gọi từ nhiều node. Ví dụ, `findById` phải khôi phục được dữ liệu do node khác ghi; `save` phải ghi đủ metadata và attributes theo chính sách đã định; `deleteById` phải làm session không còn được chấp nhận.

Nếu repository triển khai thêm `FindByIndexNameSessionRepository`, dữ liệu phục vụ tra cứu theo principal cũng phải được duy trì nhất quán. Không để một node hiểu principal index theo quy tắc khác node còn lại.

## 4. Thiết kế lớp dữ liệu dành cho session

Session thường được đọc trên nhiều request và có thể tồn tại lâu hơn vòng đời một object Java cụ thể. Vì vậy, lớp dữ liệu nên đơn giản, ổn định và độc lập với hạ tầng.

Một DTO phù hợp có thể như sau:

~~~java
import java.io.Serializable;
import java.util.List;

public final class CartSnapshot implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String cartId;
    private final List<String> productIds;

    public CartSnapshot(String cartId, List<String> productIds) {
        this.cartId = cartId;
        this.productIds = List.copyOf(productIds);
    }

    public String getCartId() {
        return cartId;
    }

    public List<String> getProductIds() {
        return productIds;
    }
}
~~~

DTO này chỉ chứa mã giỏ hàng và danh sách mã sản phẩm. Nó không giữ entity ORM, service, connection hoặc tài nguyên của request. Danh sách được sao chép thành cấu trúc không thể sửa qua reference bên ngoài, giúp giảm thay đổi ngoài ý muốn.

Ví dụ lưu vào session:

~~~java
CartSnapshot cart = new CartSnapshot(
    "CART-908",
    List.of("P-100", "P-205")
);
session.setAttribute("cart", cart);
~~~

Ví dụ đọc lại:

~~~java
CartSnapshot cart = (CartSnapshot) session.getAttribute("cart");
if (cart != null) {
    String cartId = cart.getCartId();
}
~~~

### 4.1. Nên lưu những gì?

Các giá trị thường phù hợp:

- ID người dùng hoặc ID nghiệp vụ.
- Locale, múi giờ hoặc lựa chọn giao diện nhỏ.
- ID giỏ hàng, ID quy trình tạm hoặc mã tham chiếu.
- Một DTO nhỏ chứa dữ liệu cần thiết cho request kế tiếp.
- Dữ liệu bảo mật mà framework yêu cầu lưu trong session, với serializer tương thích.

### 4.2. Không nên lưu những gì?

Tránh lưu:

- `HttpServletRequest`, `HttpServletResponse`, `ServletContext`.
- JDBC connection, transaction, stream, socket, file handle.
- Thread, executor, callback gắn với một tiến trình hoặc lambda không có hợp đồng serialization rõ ràng.
- Spring bean, service, repository hoặc object chứa dependency container.
- Hibernate entity/proxy với quan hệ lazy hoặc graph lớn.
- Object lớn, mutable và được nhiều request cập nhật đồng thời.

Thay vì lưu cả entity `User`, lưu `userId` rồi đọc dữ liệu mới nhất từ service nghiệp vụ. Cách này giảm payload session và tránh dùng snapshot cũ làm nguồn dữ liệu chính.

## 5. Thiết kế DTO có khả năng tiến hóa

Một lớp dữ liệu session có thể tồn tại trong kho lâu hơn một lần triển khai. Vì vậy, nên thiết kế từ đầu để có thể thêm trường hoặc thay đổi schema có kiểm soát.

Ví dụ DTO có version:

~~~java
public final class UserSessionContext {

    private final int schemaVersion;
    private final String userId;
    private final String locale;
    private final String displayZone;

    public UserSessionContext(
            int schemaVersion,
            String userId,
            String locale,
            String displayZone) {
        this.schemaVersion = schemaVersion;
        this.userId = userId;
        this.locale = locale;
        this.displayZone = displayZone;
    }

    public int getSchemaVersion() { return schemaVersion; }
    public String getUserId() { return userId; }
    public String getLocale() { return locale; }
    public String getDisplayZone() { return displayZone; }
}
~~~

Trường `schemaVersion` giúp bộ chuyển đổi biết dữ liệu được ghi theo cấu trúc nào. Không nhất thiết mọi DTO đều cần version riêng; với JSON, có thể version ở envelope hoặc schema tổng thể. Điều quan trọng là phải có cách phân biệt format cũ và mới nếu định dạng thay đổi không tương thích.

Các quy tắc hữu ích:

- Dùng tên trường ổn định và có ý nghĩa.
- Khi thêm trường mới, định nghĩa giá trị mặc định cho dữ liệu cũ.
- Không đổi kiểu trường một cách âm thầm.
- Tránh đổi tên package/class trong Java serialization khi session cũ còn tồn tại.
- Giữ enum ổn định; thêm giá trị enum có thể làm node cũ không hiểu giá trị mới.
- Dùng kiểu thời gian và timezone rõ ràng, ví dụ epoch hoặc ISO-8601 với offset.
- Không đưa logic nghiệp vụ vào constructor hoặc quá trình deserialize.

## 6. Java serialization và phụ thuộc vào class

Java serialization ghi object graph theo định dạng gắn với tên lớp và cấu trúc class. Các lớp cần triển khai `Serializable` nếu serializer dùng cơ chế này, và các object được tham chiếu cũng phải serialize được.

`serialVersionUID` giúp kiểm tra tương thích phiên bản của lớp:

~~~java
private static final long serialVersionUID = 1L;
~~~

Khai báo UID rõ ràng giúp tránh việc JVM tự tính UID thay đổi ngoài dự kiến khi cấu trúc lớp thay đổi. Tuy nhiên, giữ nguyên UID không có nghĩa mọi thay đổi đều an toàn. Xóa trường, đổi kiểu trường, thay hierarchy hoặc thay đổi serialization hook vẫn có thể làm dữ liệu cũ không khôi phục đúng.

Các vấn đề thường gặp:

- Node mới không có class cũ trong classpath nên không thể đọc dữ liệu.
- Node cũ không nhận ra class mới hoặc trường mới.
- Hai module cùng tên lớp nhưng khác phiên bản được nạp bởi classloader khác nhau.
- Một trường mới có giá trị mặc định `null` hoặc `0`, làm logic ứng dụng thay đổi.
- Enum được bổ sung giá trị mới mà node cũ không có.

Java serialization phù hợp với một hệ thống Java có classpath và vòng đời phiên bản được quản lý chặt. Nó ít thuận tiện khi cần chia sẻ session giữa nhiều ngôn ngữ hoặc muốn kiểm tra dữ liệu bằng công cụ bên ngoài.

## 7. JSON và định dạng dữ liệu tường minh

JSON thường dễ quan sát và ít gắn chặt với package Java hơn. Với Spring Session Redis, có thể tùy chỉnh serializer thông qua bean `springSessionDefaultRedisSerializer` theo API của phiên bản đang dùng. Với JDBC, điểm mở rộng thường liên quan đến `ConversionService` và các converter chuyển object thành bytes.

Ví dụ cấu hình Redis dùng serializer JSON:

~~~java
@Bean
public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
    return new GenericJackson2JsonRedisSerializer();
}
~~~

Đây là ví dụ cấu hình khái niệm; cần dùng đúng Jackson/Spring Data Redis API trong dependency của dự án. Nếu dùng type metadata để khôi phục object polymorphic, phải giới hạn kiểu được phép deserialize và kiểm thử format thực tế.

Một JSON payload có thể trông như:

~~~json
{
  "schemaVersion": 2,
  "userId": "u-42",
  "locale": "vi-VN",
  "displayZone": "Asia/Ho_Chi_Minh"
}
~~~

JSON không tự giải quyết tương thích. Node vẫn cần hiểu schema và quy tắc diễn giải trường. Nếu một node mong `displayZone` là chuỗi nhưng node khác ghi object timezone phức tạp, deserialize có thể thất bại hoặc tạo giá trị sai.

### 7.1. Tránh phụ thuộc vào tên lớp trong payload

Nếu payload chứa tên lớp Java đầy đủ, việc đổi package có thể làm node mới hoặc node cũ không khôi phục được object. Khi cần định dạng bền vững, ưu tiên DTO có schema rõ ràng, type discriminator do ứng dụng quản lý và bộ chuyển đổi tường minh thay vì cho phép payload chỉ định tùy ý class cần khởi tạo.

Không bật polymorphic default typing quá rộng. Chỉ cho phép các kiểu cụ thể mà ứng dụng cần và chỉ deserialize dữ liệu từ kho lưu trữ được bảo vệ.

## 8. Repository tùy chỉnh và định dạng lưu trữ

Khi triển khai repository riêng, cần xác định rõ dữ liệu nào được serialize và ở ranh giới nào. Một cách thiết kế là tách session model nội bộ khỏi DTO persistence:

~~~text
Session API
    |
    v
Domain/session model
    |
    v
Persistence mapper
    |
    v
Versioned payload / record
    |
    v
Redis, JDBC hoặc store khác
~~~

Ví dụ một record lưu trữ có thể chứa:

| Trường | Mục đích |
|---|---|
| `formatVersion` | Phiên bản envelope hoặc định dạng |
| `sessionId` | Định danh session |
| `createdAt` | Thời điểm tạo |
| `lastAccessedAt` | Lần truy cập gần nhất |
| `maxInactiveInterval` | Thời gian không hoạt động tối đa |
| `attributes` | Map tên thuộc tính đến DTO/payload đã chuyển đổi |

Không bắt buộc phải lưu đúng các trường này theo cùng một cấu trúc cho mọi repository. Đây là ví dụ về hợp đồng persistence. Metadata cần đủ để repository thực hiện create, find, save, delete và expiration theo chính sách của nó.

Repository tùy chỉnh cần xác định:

- Serializer/deserializer cho từng kiểu thuộc tính.
- Cách xử lý trường thiếu, trường không biết và version không hỗ trợ.
- Quy tắc đặt TTL và cập nhật last access.
- Cách lưu thay đổi thuộc tính và xóa thuộc tính.
- Hành vi khi deserialize lỗi hoặc dữ liệu bị hỏng.
- Cách đồng bộ ghi đồng thời từ nhiều node.
- Cách index theo principal nếu repository triển khai API tìm theo principal.

Không để controller hoặc service nghiệp vụ tự thao tác bytes của repository. Giữ logic serialization trong một thành phần có thể kiểm thử độc lập.

## 9. Tương thích giữa các phiên bản khi rolling deployment

Giả sử hệ thống đang chạy phiên bản N và chuẩn bị triển khai N+1. Trong một khoảng thời gian, cả hai phiên bản có thể cùng nhận request. Cần lập ma trận đọc/ghi:

| Node đọc | Dữ liệu do N ghi | Dữ liệu do N+1 ghi |
|---|---|---|
| N | Bắt buộc đọc được | Có thể cần đọc được trong rolling deployment |
| N+1 | Bắt buộc đọc được | Bắt buộc đọc được |

Nếu N+1 ghi một field hoặc type mà N không hiểu, request kế tiếp vào node N có thể lỗi. Một chiến lược rollout an toàn cho schema có thể tiến hóa:

1. **Giai đoạn mở rộng reader:** triển khai phiên bản có khả năng đọc cả format cũ và format mới, nhưng vẫn ghi format cũ.
2. **Đảm bảo toàn bộ node tương thích:** chờ đến khi không còn node chỉ hiểu format cũ.
3. **Chuyển writer:** bật ghi format mới khi tất cả node còn phục vụ đều đọc được format mới.
4. **Duy trì dual-read:** tiếp tục đọc format cũ trong thời gian session cũ còn tồn tại.
5. **Thu hồi hỗ trợ cũ:** chỉ bỏ decoder cũ sau khi TTL tối đa của session cũ đã qua hoặc dữ liệu cũ đã được migration.

Nếu không thể triển khai reader tương thích, có thể dùng namespace/version store riêng và yêu cầu đăng nhập lại có kế hoạch. Không nên để hai phiên bản không tương thích ghi vào cùng một namespace.

## 10. Thay đổi lớp dữ liệu an toàn

Các thay đổi có mức độ rủi ro khác nhau:

| Thay đổi | Rủi ro | Cách xử lý |
|---|---|---|
| Thêm trường optional | Thường thấp nếu có default | Kiểm thử dữ liệu cũ thiếu trường |
| Đổi tên trường JSON | Trung bình/cao | Hỗ trợ alias hoặc đọc cả tên cũ và mới |
| Đổi kiểu trường | Cao | Dùng converter versioned, không ép kiểu âm thầm |
| Xóa trường | Trung bình | Bảo đảm code mới không còn cần trường và node cũ không còn ghi |
| Đổi tên class/package Java | Cao với Java serialization | Giữ lớp tương thích hoặc chuyển format |
| Thêm giá trị enum | Có thể làm node cũ lỗi | Dùng fallback/unknown value hoặc triển khai theo giai đoạn |
| Thay serializer | Cao | Dual-read, kiểm thử fixture và có kế hoạch migration |
| Thay principal mapping | Cao với index | Đồng bộ resolver và tái lập index có kiểm soát |

Đối với JSON, có thể giữ alias cho tên trường cũ trong giai đoạn chuyển đổi. Đối với Java serialization, có thể cần lớp adapter hoặc migration dữ liệu thay vì chỉ đổi class. Mọi thay đổi phải kiểm thử bằng dữ liệu thật được ghi từ phiên bản trước.

## 11. Xử lý thuộc tính không tương thích hoặc deserialize lỗi

Deserialize failure là lỗi dữ liệu hoặc hợp đồng, không phải trường hợp nên âm thầm bỏ qua mọi thuộc tính. Cách xử lý cần dựa trên mức độ quan trọng:

- **Thuộc tính giao diện không thiết yếu:** có thể bỏ giá trị lỗi và dùng mặc định nếu chính sách cho phép; ghi metric để điều tra.
- **Giỏ hàng hoặc trạng thái quy trình:** không tự tạo trạng thái rỗng nếu điều đó làm mất dữ liệu người dùng; có thể trả lỗi có kiểm soát và khôi phục từ nguồn nghiệp vụ.
- **Thông tin xác thực/SecurityContext:** không cấp quyền khi không thể khôi phục dữ liệu xác thực. Yêu cầu xác thực lại hoặc từ chối request an toàn.
- **Payload không nhận biết version:** từ chối xử lý và ghi nhận lỗi tương thích; không cố đoán kiểu dữ liệu.

Không ghi toàn bộ payload session hoặc session ID vào log. Ghi version, loại thuộc tính, node/phiên bản ứng dụng, loại exception và correlation ID đã được làm sạch.

## 12. Đồng thời và cập nhật từ nhiều node

Tương thích serialization không bảo đảm cập nhật session không bị mất. Hai node có thể cùng đọc một snapshot rồi ghi các thay đổi theo thứ tự khác nhau:

1. Node A đọc giỏ hàng với hai sản phẩm.
2. Node B đọc cùng trạng thái và thêm sản phẩm thứ ba.
3. Node A thêm sản phẩm thứ tư dựa trên snapshot cũ.
4. Node A lưu sau Node B và ghi đè thay đổi của B.

Đây là lost update. Repository tùy chỉnh cần xác định chính sách đồng thời, ví dụ version field, optimistic locking, compare-and-set hoặc thao tác cập nhật nguyên tử theo store. Không phải mọi implementation Spring Session cung cấp optimistic locking tự động cho toàn bộ object graph.

Đối với dữ liệu nghiệp vụ quan trọng, nên lưu ở database nghiệp vụ với version/transaction phù hợp. Session chỉ nên giữ ID hoặc snapshot nhỏ. Điều này giảm xung đột và tránh biến session thành nơi lưu dữ liệu cần tính nhất quán mạnh.

## 13. Serialization và an toàn dữ liệu

Serialization không phải mã hóa. Bytes Java hoặc JSON vẫn có thể chứa thông tin người dùng và trạng thái xác thực. Cần bảo vệ kho lưu trữ và kết nối:

- Giới hạn quyền đọc/ghi Redis hoặc database cho service account của ứng dụng.
- Dùng TLS cho kết nối qua mạng và mã hóa at-rest theo khả năng hạ tầng.
- Không lưu mật khẩu dạng rõ, secret dài hạn hoặc dữ liệu nhạy cảm không cần thiết trong session.
- Chỉ deserialize dữ liệu từ repository đáng tin cậy.
- Giới hạn class/type được phép nếu serializer hỗ trợ polymorphic typing.
- Với Java serialization, cân nhắc cơ chế lọc kiểu của JDK và giới hạn object graph/độ sâu nếu phù hợp phiên bản runtime.
- Redact session ID và payload khỏi log, tracing, metrics label và error report.

Nếu cần mã hóa payload ở tầng ứng dụng, phải có thiết kế quản lý khóa, xoay vòng khóa và khả năng giải mã dữ liệu cũ trong thời gian chuyển đổi. Không tự thêm encryption mà không định nghĩa cách các node cùng giải mã.

## 14. Kiểm thử tương thích giữa node và phiên bản

Unit test round-trip trong một JVM chỉ xác nhận serializer hiện tại đọc được dữ liệu do chính nó ghi. Để kiểm tra tương thích phân tán, cần fixture và nhiều phiên bản:

| Kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Round-trip cùng phiên bản | N ghi, N đọc | Dữ liệu khôi phục đúng |
| Đọc dữ liệu cũ | N ghi fixture, N+1 đọc | Không mất trường quan trọng |
| Node mới đọc dữ liệu cũ | Node N+1 đọc session đang tồn tại | Request tiếp tục hoạt động |
| Node cũ đọc dữ liệu mới | N đọc payload do N+1 ghi trong giai đoạn rolling | Đọc được hoặc rollout bảo đảm N không còn nhận traffic |
| Thêm trường | Fixture cũ không có field mới | Giá trị mặc định hợp lệ |
| Enum mới | Payload có enum mới | Node cũ có fallback hoặc không nhận payload mới |
| Deserialize lỗi | Payload bị hỏng hoặc version lạ | Từ chối an toàn, có metric và log phù hợp |
| Multi-node | Node A ghi, node B đọc và cập nhật | Hai node hiểu cùng format |
| Concurrent update | Hai node cập nhật cùng session | Không mất cập nhật theo chính sách đã thiết kế |
| Serializer migration | Đọc format cũ, ghi format mới | Dữ liệu chuyển đổi có kiểm soát |

Nên lưu fixture đại diện được tạo từ phiên bản phát hành trước trong test resources. Khi thay DTO hoặc serializer, chạy lại các fixture đó để phát hiện lỗi tương thích trước khi triển khai.

### 14.1. Kiểm thử với repository thật

Với Redis, dùng Redis test instance hoặc container và khởi tạo hai application context có cùng cấu hình store. Với JDBC, dùng database cùng engine với production. Trình tự:

1. Node A tạo session và ghi các thuộc tính đại diện.
2. Node B dùng cùng session ID để tìm và khôi phục session.
3. Node B cập nhật một thuộc tính.
4. Node A đọc lại dữ liệu do B ghi.
5. Chạy thử với phiên bản DTO/serializer cũ và mới.
6. Kiểm tra session expiration, logout và deserialize failure.

Test phải dùng cùng serializer, schema, namespace và cấu hình classpath như môi trường triển khai.

## 15. Theo dõi lỗi tương thích trong production

Các chỉ số hữu ích:

| Metric/log | Mục đích |
|---|---|
| Số lỗi serialize | Phát hiện object session không được hỗ trợ |
| Số lỗi deserialize | Phát hiện payload cũ, hỏng hoặc không tương thích |
| Lỗi theo format/schema version | Nhận biết node nào đang ghi/đọc version nào |
| Tỷ lệ session phải xác thực lại sau deploy | Phát hiện ảnh hưởng đến người dùng |
| Kích thước payload session | Theo dõi session phình to |
| Thời gian serialize/deserialize | Đánh giá chi phí CPU và độ trễ |
| Lỗi repository theo node | Phát hiện cấu hình khác nhau giữa instance |
| Lost update hoặc conflict count | Theo dõi vấn đề ghi đồng thời nếu repository có versioning |

Gắn version ứng dụng và format vào log/metric, nhưng không đưa session ID hoặc principal nhạy cảm vào label có cardinality cao. Khi deploy, so sánh lỗi giữa các node và theo dõi trong toàn bộ thời gian session cũ có thể còn tồn tại.

## 16. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Node mới không đọc session cũ | Class hoặc serializer đã đổi | Giữ decoder cũ, thêm migration hoặc kết thúc session có kế hoạch |
| Node cũ lỗi sau khi node mới ghi | Payload mới không tương thích ngược | Triển khai reader trước, đổi writer sau khi node cũ được rút |
| `InvalidClassException` | `serialVersionUID` hoặc cấu trúc class không tương thích | Kiểm tra class version và fixture cũ |
| `ClassNotFoundException` | Node thiếu class hoặc package đã đổi | Đồng bộ dependency/classpath hoặc adapter |
| JSON trả về Map thay vì DTO | Thiếu type mapping hoặc schema không rõ | Dùng DTO/schema tường minh và converter |
| Một enum làm node cũ lỗi | Giá trị enum mới chưa được node cũ hỗ trợ | Dùng fallback hoặc trì hoãn ghi giá trị mới |
| Session đọc được nhưng thiếu thuộc tính | Field bị đổi tên, converter bỏ qua hoặc SaveMode không lưu thay đổi | Kiểm tra schema mapping và chính sách lưu |
| Session bị ghi đè | Nhiều node cập nhật snapshot cũ | Dùng version/CAS hoặc chuyển dữ liệu nghiệp vụ ra store riêng |
| Lỗi chỉ xuất hiện sau rolling deploy | Hai phiên bản cùng đọc/ghi một namespace | Kiểm tra ma trận tương thích writer-reader |
| Log chứa thông tin nhạy cảm | Debug serializer ghi payload hoặc session ID | Redact log và giới hạn dữ liệu quan sát |

## 17. Nguyên tắc triển khai

- Xem serializer và lớp dữ liệu là hợp đồng giữa tất cả node dùng chung repository.
- Phân biệt API session với DTO thuộc tính và định dạng persistence.
- Ưu tiên DTO nhỏ, ổn định, không phụ thuộc request, ORM proxy hoặc Spring bean.
- Chọn Java serialization hoặc JSON có chủ đích; hiểu rõ ràng buộc tương thích và bảo mật của từng loại.
- Version hóa payload/schema khi cần tiến hóa không tương thích.
- Triển khai reader tương thích trước khi chuyển writer trong rolling deployment.
- Giữ decoder cũ ít nhất bằng thời gian session cũ còn tồn tại hoặc đến khi migration hoàn tất.
- Kiểm thử cả N đọc dữ liệu N+1 ghi nếu hai phiên bản có thể cùng chạy.
- Thiết kế chính sách deserialize failure an toàn, đặc biệt với dữ liệu xác thực.
- Xử lý cập nhật đồng thời riêng; serialization không tự giải quyết lost update.
- Theo dõi lỗi serialize/deserialize, payload size và khác biệt cấu hình giữa node.

Spring Session giúp nhiều instance chia sẻ trạng thái phiên, nhưng sự chia sẻ đó chỉ bền vững khi mọi node cùng hiểu dữ liệu được lưu. Thiết kế DTO ổn định, chọn serializer phù hợp, quản lý version và triển khai theo thứ tự reader trước writer giúp tránh lỗi khi mở rộng cụm hoặc nâng cấp ứng dụng. Với repository tùy chỉnh, hợp đồng serialization và chính sách tương thích phải được xem là một phần của thiết kế lưu trữ, không phải chi tiết phụ của controller.
