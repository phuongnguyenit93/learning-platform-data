# Đối tượng khả biến và ranh giới theo dõi thay đổi của repository

Spring Session lưu các thuộc tính của phiên theo tên thuộc tính. Repository có thể theo dõi những thao tác ở cấp thuộc tính như đặt, đọc hoặc xóa để quyết định dữ liệu nào cần ghi xuống Redis, JDBC hoặc kho lưu trữ khác. Tuy nhiên, repository không tự động quan sát mọi thay đổi diễn ra bên trong đồ thị object Java.

Điều này đặc biệt quan trọng khi session chứa object khả biến như ArrayList, HashMap, DTO có setter hoặc object nghiệp vụ có collection lồng nhau. Nếu request lấy một object từ session rồi sửa trực tiếp field hoặc collection bên trong, Spring Session có thể không nhận ra thuộc tính cấp cao nhất đã thay đổi. Dữ liệu trong bộ nhớ của request trông có vẻ đúng nhưng thay đổi có thể không được lưu xuống repository.

Bài này giải thích ranh giới dirty tracking của Spring Session, cách SaveMode và FlushMode ảnh hưởng đến việc ghi, vì sao thay đổi object lồng nhau dễ bị bỏ sót, cách cập nhật bằng object bất biến hoặc thay thế thuộc tính tường minh, và cách kiểm thử các trường hợp đồng thời trong ứng dụng nhiều instance.

## 1. Repository theo dõi thay đổi ở cấp nào?

Một session có metadata do Spring Session quản lý và các thuộc tính do ứng dụng thêm vào. Ví dụ:

~~~text
Session
  id
  creationTime
  lastAccessedTime
  maxInactiveInterval
  attributes
    app.locale
    app.cart
    app.preferences
    SPRING_SECURITY_CONTEXT
~~~

Khi ứng dụng gọi setAttribute("app.locale", "vi-VN"), nó thực hiện một thao tác rõ ràng trên session. Tương tự, removeAttribute("app.preferences") biểu thị một thay đổi có thể được repository ghi nhận.

Nhưng nếu thuộc tính app.cart là một object chứa List<CartLine>, rồi ứng dụng gọi cart.getLines().add(newLine), thay đổi xảy ra bên trong object đã được trả về. Session không nhất thiết nhận được một lời gọi setAttribute mới. Repository cũng không quan sát từng lệnh add() của collection.

| Thao tác | Ranh giới thay đổi | Repository có thể nhận biết ra sao |
|---|---|---|
| session.setAttribute("x", value) | Thuộc tính session | Có lời gọi đặt thuộc tính rõ ràng |
| session.removeAttribute("x") | Thuộc tính session | Có lời gọi xóa thuộc tính rõ ràng |
| session.getAttribute("x") | Truy cập thuộc tính | Có thể được tính là thay đổi tùy SaveMode |
| value.setName("new") sau khi lấy value | Field bên trong object | Không có lời gọi session tương ứng |
| value.getItems().add(item) | Collection lồng nhau | Không có deep dirty tracking mặc định |
| Sửa một object con trong object cha | Đồ thị object | Không được repository tự động theo dõi từng field |

Đây là ranh giới quan trọng: Spring Session quản lý việc lưu thuộc tính session, không phải một ORM có cơ chế dirty checking sâu cho mọi object trong thuộc tính.

### Ví dụ object khả biến

~~~java
public class ShoppingCart implements Serializable {

    private static final long serialVersionUID = 1L;

    private final List<String> itemIds = new ArrayList<>();

    public List<String> getItemIds() {
        return itemIds;
    }

    public void add(String itemId) {
        itemIds.add(itemId);
    }
}
~~~

Controller hoặc service có thể lấy giỏ hàng rồi sửa trực tiếp:

~~~java
ShoppingCart cart =
        (ShoppingCart) session.getAttribute("app.cart");

cart.add("item-42");
~~~

Trong bộ nhớ của request, danh sách đã có item-42. Nhưng nếu repository chỉ ghi các thuộc tính được đánh dấu thay đổi qua setAttribute, thì thuộc tính app.cart có thể không được lưu lại. Request kế tiếp có thể tải phiên bản cũ từ Redis/JDBC.

Không nên dựa vào việc object vẫn nằm trong map session để kết luận thay đổi bên trong nó sẽ tự động được ghi.

## 2. Dirty tracking của Spring Session khác dirty checking của ORM

Các ORM như Hibernate có thể theo dõi entity đang được quản lý trong persistence context và phát hiện một số thay đổi field khi flush. Spring Session có ranh giới khác: nó lưu các thuộc tính session theo API Session/HttpSession và chính sách SaveMode.

Spring Session không tự động:

- Theo dõi mọi setter được gọi trên object thuộc tính.
- Theo dõi mọi phần tử được thêm hoặc xóa khỏi collection lồng nhau.
- So sánh đệ quy toàn bộ đồ thị object trước và sau request.
- Phát hiện thay đổi chỉ vì một object Java đã bị sửa tại chỗ.
- Tạo transaction nghiệp vụ cho các thuộc tính session.

Vì vậy, không áp dụng suy luận “đã lấy object từ session, sửa field, nên repository sẽ tự biết” như khi làm việc với một entity được ORM quản lý.

Hãy coi mỗi thuộc tính session là một đơn vị lưu trữ. Nếu giá trị của thuộc tính thay đổi, ứng dụng nên thông báo thay đổi ở đúng ranh giới đó bằng cách đặt lại thuộc tính hoặc dùng SaveMode phù hợp với cách truy cập.

## 3. SaveMode quyết định thuộc tính nào được đưa vào thao tác lưu

Spring Session cung cấp SaveMode để điều khiển các thuộc tính session được lưu khi repository nhận thao tác save. Ba chế độ thường gặp:

| SaveMode | Hành vi | Hệ quả |
|---|---|---|
| ON_SET_ATTRIBUTE | Lưu thuộc tính được đặt bằng setAttribute | Phù hợp khi ứng dụng cập nhật bằng cách thay thế/đặt lại thuộc tính |
| ON_GET_ATTRIBUTE | Lưu cả thuộc tính được đọc qua getAttribute | Có thể hỗ trợ code sửa object khả biến sau khi đọc |
| ALWAYS | Lưu tất cả thuộc tính khi session được lưu | Dễ tránh bỏ sót dirty attribute nhưng tăng công việc serialize và ghi |

ON_SET_ATTRIBUTE thường là lựa chọn tiết kiệm khi ứng dụng luôn gọi setAttribute sau mỗi lần cập nhật. Nếu code chỉ sửa object con mà không đặt lại thuộc tính, repository có thể không xem thuộc tính đó là đã thay đổi.

ON_GET_ATTRIBUTE đánh dấu thuộc tính được đọc để lưu khi session được lưu. Điều này có thể giúp các trường hợp đọc object rồi sửa tại chỗ, nhưng cũng có thể làm các thuộc tính chỉ đọc bị ghi lại, tăng lượng dữ liệu serialize và I/O.

ALWAYS đưa tất cả thuộc tính vào thao tác lưu. Cách này có thể hữu ích khi ứng dụng có nhiều object khả biến khó kiểm soát, nhưng không phải cơ chế deep dirty tracking. Nó không tạo ra merge an toàn giữa các request đồng thời và có thể làm tăng đáng kể chi phí ghi.

Tên và hành vi chi tiết cần được kiểm tra theo phiên bản Spring Session đang dùng. Không thay SaveMode chỉ dựa vào một lỗi mất cập nhật; trước tiên cần xác định thuộc tính nào đã bị sửa và cách ứng dụng tương tác với session.

## 4. ON_SET_ATTRIBUTE và thay đổi object tại chỗ

Với ON_SET_ATTRIBUTE, repository tập trung vào các thuộc tính được đặt bằng API session. Ví dụ:

~~~java
ShoppingCart cart =
        (ShoppingCart) session.getAttribute("app.cart");

cart.add("item-42");

// Không có setAttribute sau khi thay đổi object.
~~~

Ở đây, lời gọi getAttribute lấy tham chiếu object. Lời gọi add chỉ thay đổi collection bên trong object. Session không nhận một thao tác đặt thuộc tính mới.

Cách cập nhật rõ ràng hơn:

~~~java
ShoppingCart cart =
        (ShoppingCart) session.getAttribute("app.cart");

cart.add("item-42");
session.setAttribute("app.cart", cart);
~~~

Lời gọi cuối thông báo cho session rằng thuộc tính app.cart đã được đặt lại. Tuy nhiên, dùng lại cùng một object đã sửa vẫn có thể làm code khó hiểu và dễ phát sinh race condition nếu nhiều request cùng giữ tham chiếu tới trạng thái tương tự.

Tốt hơn là tạo giá trị mới rồi đặt lại:

~~~java
ShoppingCart current =
        (ShoppingCart) session.getAttribute("app.cart");

ShoppingCart updated = current.withAddedItem("item-42");

session.setAttribute("app.cart", updated);
~~~

Cách này làm thay đổi rõ ràng hơn: giá trị cũ được đọc, giá trị mới được tạo và thuộc tính session được thay thế.

## 5. ON_GET_ATTRIBUTE không phải deep dirty tracking

ON_GET_ATTRIBUTE có thể hữu ích khi code cần sửa object khả biến tại chỗ:

~~~java
ShoppingCart cart =
        (ShoppingCart) session.getAttribute("app.cart");

cart.add("item-42");
~~~

Vì thuộc tính đã được đọc qua API session, chế độ này đưa nó vào tập thuộc tính cần lưu khi session được save. Điều đó giúp thay đổi bên trong object có cơ hội được serialize lại.

Tuy nhiên, cần hiểu chính xác giới hạn:

- Repository không theo dõi từng field hoặc từng phần tử collection.
- Việc đọc một thuộc tính có thể khiến thuộc tính đó được ghi lại dù request không sửa gì.
- Nếu object được giữ ở một biến khác và bị sửa sau khi không còn nằm trong luồng truy cập được theo dõi, không nên giả định repository sẽ nhận biết.
- Nếu hai request cùng sửa một thuộc tính, SaveMode không cung cấp cơ chế merge hoặc khóa phân tán.
- Nếu code truy cập session qua cách không đi qua API được repository/wrapper theo dõi, hành vi có thể khác.

Do đó, ON_GET_ATTRIBUTE là chính sách chọn thuộc tính dựa trên thao tác đọc, không phải một hệ thống so sánh object graph.

### Khi nào cân nhắc ON_GET_ATTRIBUTE?

Có thể cân nhắc khi ứng dụng có các lớp legacy thường sửa collection hoặc DTO khả biến tại chỗ sau khi lấy từ session và chưa thể refactor ngay. Trước khi bật:

1. Đo số thuộc tính được đọc trong một request.
2. Ước lượng kích thước các object được đọc.
3. Kiểm tra số lần serialize và ghi tăng thêm.
4. Kiểm thử request chỉ đọc để xác định thuộc tính nào bị ghi lại.
5. Kiểm tra tải Redis/JDBC ở mức concurrency gần production.

Nếu đa số request đọc nhiều thuộc tính lớn, ON_GET_ATTRIBUTE có thể làm chi phí ghi tăng mạnh.

## 6. ALWAYS và cái giá của việc lưu mọi thuộc tính

ALWAYS đưa tất cả thuộc tính session vào thao tác save, kể cả thuộc tính không được đặt lại trong request hiện tại.

Điều này có thể tránh trường hợp một thuộc tính mutable bị bỏ sót chỉ vì không có lời gọi setAttribute. Nhưng nó có một số chi phí:

- Serialize lại các thuộc tính không thay đổi.
- Tăng số byte truyền tới Redis hoặc database.
- Tăng số lần ghi và thời gian transaction.
- Tăng tải CPU do serialize/deserialize.
- Tăng khả năng hai request ghi snapshot thuộc tính cũ đè lên cập nhật mới hơn.
- Làm các session lớn ảnh hưởng độ trễ của request.

ALWAYS không giải quyết xung đột đồng thời. Nếu request A và B cùng tải một session, B cập nhật giỏ hàng rồi lưu, sau đó A lưu snapshot cũ, ALWAYS có thể khiến dữ liệu cũ được ghi lại tùy semantics repository. Cần kiểm thử hành vi thực tế và dùng cơ chế đồng bộ hoặc lưu dữ liệu nghiệp vụ bên ngoài session nếu cần đảm bảo mạnh hơn.

Không bật ALWAYS như một biện pháp mặc định để che giấu việc code sửa object mà không gọi setAttribute.

## 7. FlushMode điều khiển thời điểm ghi, không phải phạm vi dirty tracking

FlushMode trả lời câu hỏi “khi nào thay đổi được đẩy xuống repository?”. SaveMode trả lời câu hỏi “thuộc tính nào được đưa vào thao tác lưu?”.

| Cấu hình | Câu hỏi được trả lời |
|---|---|
| FlushMode.ON_SAVE | Ghi khi repository/filter thực hiện save, thường ở cuối request |
| FlushMode.IMMEDIATE | Ghi thay đổi sớm hơn theo thao tác session |
| SaveMode.ON_SET_ATTRIBUTE | Chọn thuộc tính được đặt |
| SaveMode.ON_GET_ATTRIBUTE | Chọn thuộc tính đã đọc |
| SaveMode.ALWAYS | Chọn tất cả thuộc tính |

Ví dụ cấu hình Servlet với Redis:

~~~java
@Configuration
@EnableRedisHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE,
    maxInactiveIntervalInSeconds = 1800
)
public class SessionConfiguration {
}
~~~

Với JDBC, cấu hình @EnableJdbcHttpSession cũng hỗ trợ các chính sách tương ứng ở những phiên bản phù hợp. Hãy xác nhận property và annotation API trong phiên bản dự án.

Một request có thể cập nhật lastAccessedTime dù không thay đổi thuộc tính ứng dụng. FlushMode và SaveMode không nên được hiểu là cách tắt mọi ghi metadata. Tương tự, IMMEDIATE không thể tự phát hiện một field lồng nhau vừa bị sửa nếu không có thao tác session đánh dấu thuộc tính.

## 8. Cập nhật object bất biến và thay thế thuộc tính

Cách dễ kiểm soát nhất là dùng object bất biến hoặc tạo bản sao mới khi cập nhật.

Ví dụ DTO giỏ hàng:

~~~java
public record CartState(
        List<CartLine> lines,
        String currency
) implements Serializable {

    public CartState {
        lines = List.copyOf(lines);
    }

    public CartState withAddedLine(CartLine line) {
        List<CartLine> updated = new ArrayList<>(lines);
        updated.add(line);
        return new CartState(updated, currency);
    }
}
~~~

Cập nhật trong controller/service:

~~~java
CartState current =
        (CartState) session.getAttribute("app.cart");

CartState updated = current.withAddedLine(newLine);

session.setAttribute("app.cart", updated);
~~~

Lợi ích:

- Không sửa object cũ tại chỗ.
- Có lời gọi setAttribute rõ ràng.
- Dễ viết unit test cho phép biến đổi.
- Giảm khả năng hai phần code vô tình chia sẻ cùng một tham chiếu mutable.
- Dễ thêm schema version và migration khi cấu trúc DTO thay đổi.

List.copyOf tạo collection không thể sửa qua tham chiếu trả về. Nhưng object bên trong list cũng cần bất biến nếu muốn bảo vệ toàn bộ đồ thị. Nếu CartLine vẫn mutable, hãy dùng kiểu giá trị bất biến hoặc sao chép sâu phù hợp.

### Khi chưa thể bỏ object mutable

Có thể dùng chiến lược copy-update-set:

1. Lấy object hiện tại.
2. Sao chép các collection/field cần thay đổi.
3. Tạo object mới.
4. Gọi setAttribute với object mới.
5. Không giữ tham chiếu cũ để sửa sau khi đã đặt vào session.

Ví dụ:

~~~java
Preferences current =
        (Preferences) session.getAttribute("app.preferences");

Preferences updated = new Preferences(
        request.theme(),
        request.locale(),
        new HashMap<>(current.getFlags())
);

updated.getFlags().put("compactMode", true);
session.setAttribute("app.preferences", updated);
~~~

Ví dụ này vẫn có mutable map bên trong updated, nhưng map được tạo mới và thuộc tính được đặt lại sau khi hoàn tất thay đổi. Với code dài hạn, nên thiết kế Preferences bất biến để tránh lộ collection mutable.

## 9. Xóa thuộc tính cũng là một thay đổi cần được ghi nhận

Khi muốn loại bỏ thuộc tính, dùng API session:

~~~java
session.removeAttribute("app.cart");
~~~

Không chỉ gọi session.getAttribute("app.cart") rồi đặt field bên trong thành null. Thay đổi bên trong object vẫn không tương đương với việc xóa thuộc tính khỏi session.

Cũng không giữ một tham chiếu tới collection đã lấy từ session rồi gọi clear() mà không đặt lại hoặc xóa thuộc tính. Nếu muốn lưu một collection rỗng, đặt giá trị mới:

~~~java
session.setAttribute("app.recentItems", List.of());
~~~

Nếu muốn không còn thuộc tính, dùng removeAttribute. Hai trạng thái “có thuộc tính với collection rỗng” và “không có thuộc tính” có thể mang ý nghĩa khác nhau trong ứng dụng.

## 10. Tránh sửa cùng một object session từ nhiều thread

Một session có thể được dùng bởi nhiều request đồng thời, ví dụ người dùng mở nhiều tab hoặc client gửi hai request gần như cùng lúc. Không nên chia sẻ một tham chiếu object mutable trong session rồi để nhiều thread cùng sửa.

Ví dụ rủi ro:

~~~java
List<String> viewedItems =
        (List<String>) session.getAttribute("app.viewedItems");

// Hai request đồng thời cùng gọi add/remove trên cùng trạng thái.
viewedItems.add(itemId);
~~~

Ngay cả khi collection được đồng bộ thread-safe trong một JVM, điều đó không giải quyết các vấn đề:

- Hai request có thể tải hai snapshot khác nhau từ repository.
- Mỗi node có object trong bộ nhớ riêng.
- Đồng bộ hóa Java chỉ có hiệu lực trong process hiện tại.
- Request lưu sau có thể ghi đè thay đổi của request lưu trước.
- Repository không tự động cung cấp transaction nghiệp vụ hoặc compare-and-set cho object lồng nhau.

Không dùng synchronized(session) như một khóa phân tán. Nó chỉ đồng bộ các thread cùng dùng đúng một object trong một JVM và không khóa được các instance khác.

Nếu dữ liệu session nhỏ và chỉ mang tính giao diện, có thể chấp nhận chính sách last-write-wins sau khi hiểu tác động. Nếu cần giữ mọi cập nhật, hãy dùng kho dữ liệu có atomic update, optimistic locking/version hoặc transaction nghiệp vụ.

## 11. Hai request cùng cập nhật một thuộc tính

Giả sử session lưu giỏ hàng ban đầu có hai sản phẩm A và B. Hai request đồng thời:

- Request 1 tải snapshot [A, B], thêm C thành [A, B, C].
- Request 2 tải snapshot [A, B], thêm D thành [A, B, D].
- Request 1 lưu trước.
- Request 2 lưu sau.

Nếu cả hai ghi toàn bộ giá trị thuộc tính, kết quả cuối có thể là [A, B, D]; sản phẩm C bị mất. Đây là lost update.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant R as Repository
    participant B as Request B
    A->>R: Đọc cart [A,B]
    B->>R: Đọc cart [A,B]
    A->>A: Thêm C -> [A,B,C]
    B->>B: Thêm D -> [A,B,D]
    A->>R: Lưu [A,B,C]
    B->>R: Lưu [A,B,D]
    Note over R: Có thể còn [A,B,D], mất cập nhật C
~~~

SaveMode không giải quyết lost update. ON_SET_ATTRIBUTE giúp xác định thuộc tính nào đã được đặt, nhưng nếu cùng thuộc tính bị ghi từ hai snapshot khác nhau, repository vẫn cần một cơ chế xử lý xung đột nếu nghiệp vụ yêu cầu.

Với dữ liệu giỏ hàng cần giữ từng thao tác, hãy lưu cart trong database nghiệp vụ và cập nhật bằng câu lệnh/transaction có kiểm soát. Session chỉ giữ cart ID hoặc thông tin lựa chọn giao diện.

## 12. Khi nào cần versioning hoặc optimistic locking?

Nếu dữ liệu được phép nằm trong session nhưng có yêu cầu không mất cập nhật, có thể thêm version vào object:

~~~java
public record VersionedCart(
        long version,
        List<CartLine> lines
) implements Serializable {
}
~~~

Tuy nhiên, chỉ thêm trường version vào DTO không tự tạo optimistic locking. Repository phải có thao tác nguyên tử kiểu compare-and-set: chỉ cập nhật nếu version hiện tại bằng version mà request đã đọc.

Một quy trình khái niệm:

1. Đọc session attribute và version N.
2. Tạo giá trị mới với version N+1.
3. Ghi bằng thao tác compare-and-set có điều kiện version = N.
4. Nếu không cập nhật được vì version đã đổi, tải lại và hợp nhất hoặc trả conflict.
5. Không ghi đè snapshot cũ một cách âm thầm.

Spring Session repository thông thường không nên được xem là kho optimistic-locking cho mọi thuộc tính. Nếu cần cơ chế này, có thể đặt dữ liệu vào bảng nghiệp vụ hoặc một repository riêng có API cập nhật có điều kiện.

Với Redis, Lua script hoặc thao tác atomic có thể triển khai compare-and-set nếu các key được thiết kế đúng cho Redis Cluster. Với database quan hệ, có thể dùng câu UPDATE có điều kiện version. Cần cân nhắc transaction, retry và idempotency.

## 13. Tách dữ liệu session khỏi dữ liệu nghiệp vụ

Session thích hợp cho trạng thái tương tác ngắn hạn, ví dụ:

- Ngôn ngữ hoặc theme đang chọn.
- ID giỏ hàng hiện tại.
- Bước hiện tại trong một wizard.
- Một số lựa chọn giao diện.
- SecurityContext theo cấu hình bảo mật.

Các dữ liệu sau thường nên nằm trong kho nghiệp vụ:

- Đơn hàng và trạng thái thanh toán.
- Số dư, tồn kho và hạn mức.
- Lịch sử giao dịch.
- Giỏ hàng cần giữ qua nhiều thiết bị hoặc nhiều ngày.
- Bộ đếm mà không được phép mất cập nhật.
- Quy trình phê duyệt hoặc workflow có audit.

Ví dụ session chỉ giữ ID:

~~~java
session.setAttribute("app.cartId", cartId);
~~~

Khi cần đọc giỏ hàng, service tải dữ liệu từ database:

~~~java
String cartId = (String) session.getAttribute("app.cartId");
return cartService.load(cartId);
~~~

Khi cập nhật, cartService dùng transaction/locking phù hợp. Điều này giúp repository session không phải chịu trách nhiệm bảo đảm nhất quán cho dữ liệu nghiệp vụ phức tạp.

## 14. Tác động của serialization

Spring Session thường serialize thuộc tính khi ghi vào kho dữ liệu và deserialize khi tải session. Thay đổi object trong bộ nhớ không nhất thiết đồng nghĩa byte đã được cập nhật trong Redis/JDBC.

Quy trình khái niệm:

1. Repository tải byte thuộc tính.
2. Serializer tạo object Java.
3. Request đọc object từ session.
4. Ứng dụng sửa object trong bộ nhớ.
5. SaveMode quyết định thuộc tính có được đưa vào lần save không.
6. Repository serialize giá trị được chọn và ghi xuống kho.

Nếu thuộc tính không được đánh dấu cần lưu, serializer có thể không chạy cho thuộc tính đó trong request. Dữ liệu bền vững vẫn là phiên bản trước.

Kích thước object cũng quan trọng. ALWAYS hoặc ON_GET_ATTRIBUTE trên session chứa đồ thị lớn có thể làm tăng CPU và băng thông. Tránh lưu object graph sâu, entity/proxy ORM, stream, request/response hoặc object không có chiến lược serialization ổn định.

Nếu dùng JSON serializer, thay đổi schema DTO cũng cần được kiểm thử. Nếu dùng Java serialization, class và serialVersionUID cần tương thích với session còn tồn tại từ phiên bản cũ. Dirty tracking không giải quyết schema evolution.

## 15. Kiểm thử ranh giới theo dõi thay đổi

Nên viết integration test với repository thực tế, vì mock repository không chứng minh cách SaveMode và serialization hoạt động qua filter/session wrapper.

Một ma trận kiểm thử:

| Ca kiểm thử | Cấu hình/thao tác | Kết quả cần xác nhận |
|---|---|---|
| Đặt thuộc tính | ON_SET_ATTRIBUTE + setAttribute | Giá trị mới được lưu |
| Sửa object tại chỗ | ON_SET_ATTRIBUTE + getAttribute rồi mutate | Không giả định thay đổi được lưu; xác nhận hành vi |
| Sửa rồi đặt lại | ON_SET_ATTRIBUTE + setAttribute sau mutate | Thuộc tính được lưu |
| Đọc rồi sửa | ON_GET_ATTRIBUTE + getAttribute rồi mutate | Thuộc tính đã đọc được lưu theo chính sách |
| Chỉ đọc thuộc tính | ON_GET_ATTRIBUTE không sửa | Đo việc thuộc tính vẫn bị ghi lại |
| Lưu mọi thuộc tính | ALWAYS | Tất cả thuộc tính được ghi khi save |
| Xóa thuộc tính | removeAttribute | Thuộc tính không còn sau khi tải lại |
| Collection lồng nhau | Thêm/xóa phần tử | Xác nhận dirty boundary |
| Hai request đồng thời | Cùng sửa một thuộc tính | Quan sát lost update và chính sách xung đột |
| Nhiều instance | Node A cập nhật, node B tải lại | Dữ liệu đã lưu được chia sẻ |
| Serialization cũ | Tải fixture từ phiên bản trước | Giá trị cũ đọc/chuyển đổi đúng |

### Ví dụ test minh họa với ON_SET_ATTRIBUTE

~~~java
@Test
void replacingAttributeIsPersisted() {
    Session session = repository.createSession();

    session.setAttribute("app.locale", "vi-VN");
    repository.save(session);

    Session loaded = repository.findById(session.getId());
    assertThat(loaded).isNotNull();

    loaded.setAttribute("app.locale", "en-US");
    repository.save(loaded);

    Session reloaded = repository.findById(session.getId());

    assertThat(reloaded.getAttribute("app.locale"))
            .isEqualTo("en-US");
}
~~~

Test trên minh họa thao tác thay thế thuộc tính ở tầng repository. Để xác minh SaveMode trong ứng dụng Servlet, cần test qua SessionRepositoryFilter và HttpSession wrapper, vì đó là nơi SaveMode điều khiển thuộc tính được đưa vào save. API repository trực tiếp có thể không tái hiện đầy đủ hành vi dirty tracking của request.

### Test thay đổi object mutable

Có thể viết hai request riêng:

1. Request đầu tạo app.cart và lưu.
2. Request sau tải cart, sửa collection tại chỗ nhưng không gọi setAttribute.
3. Request tiếp theo tải lại và so sánh giá trị.
4. Lặp lại với thao tác setAttribute sau khi sửa.
5. Chạy với ON_SET_ATTRIBUTE và ON_GET_ATTRIBUTE để xác nhận khác biệt.

Không hard-code kỳ vọng chỉ từ một mock. Dùng Redis/JDBC test repository cùng phiên bản dependency production và kiểm tra giá trị đã deserialize ở request kế tiếp.

## 16. Kiểm thử request đồng thời và nhiều instance

Để kiểm tra lost update:

1. Tạo một session có thuộc tính cart ban đầu.
2. Dùng hai client/request đồng thời để tải cùng session.
3. Giữ cả hai snapshot trước khi ghi.
4. Request A thêm một phần tử và lưu.
5. Request B thêm phần tử khác từ snapshot cũ và lưu sau.
6. Tải session mới từ repository.
7. Xác nhận kết quả theo chính sách đã thiết kế: last-write-wins, merge, conflict hoặc atomic update.

Lặp lại trên hai application instance dùng cùng Redis/JDBC. Đồng bộ hóa bằng latch trong test để tạo đúng thứ tự đọc/ghi. Không dựa vào Thread.sleep cố định vì nó không đảm bảo thứ tự cạnh tranh.

Nếu ứng dụng chấp nhận last-write-wins cho một thuộc tính UI, test cần ghi rõ đó là hành vi được chấp nhận. Nếu không chấp nhận mất cập nhật, test phải xác nhận cơ chế version/CAS hoặc transaction nghiệp vụ ngăn xung đột.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Thay đổi collection biến mất sau request | Chỉ sửa object lồng nhau, không đặt lại thuộc tính | Dùng object bất biến hoặc setAttribute sau cập nhật |
| Đổi sang ON_GET_ATTRIBUTE thì tải ghi tăng | Nhiều thuộc tính chỉ đọc cũng được lưu | Đo số thuộc tính được đọc; cân nhắc refactor |
| Bật ALWAYS nhưng vẫn mất cập nhật | Request đồng thời ghi snapshot cũ | Dùng version/CAS hoặc lưu dữ liệu nghiệp vụ riêng |
| Chỉ một số request thấy giá trị mới | Request khác tải snapshot trước khi request cập nhật lưu | Xác định thứ tự đọc/ghi và consistency requirement |
| Session có object quá lớn | Lưu toàn bộ entity hoặc đồ thị collection | Chỉ lưu ID/DTO nhỏ |
| Dữ liệu khác nhau giữa node | Node dùng serializer/SaveMode khác nhau hoặc namespace khác | Đồng bộ cấu hình và dependency |
| Xóa field trong object nhưng dữ liệu cũ còn | Không gọi setAttribute hoặc removeAttribute | Đặt lại hoặc xóa thuộc tính ở session boundary |
| Test unit pass nhưng production mất dữ liệu | Test không chạy qua filter/repository thật | Thêm integration test với Redis/JDBC và nhiều node |

## 18. Checklist thiết kế thuộc tính session

Trước khi lưu object vào Spring Session, hãy tự kiểm tra:

- Thuộc tính có nhỏ và cần thiết cho request tiếp theo không?
- Object có mutable không? Nếu có, có thể chuyển sang immutable DTO không?
- Nếu sửa object, code có gọi setAttribute lại không?
- SaveMode đang là ON_SET_ATTRIBUTE, ON_GET_ATTRIBUTE hay ALWAYS?
- Có hiểu rõ chi phí serialize/ghi của chế độ đã chọn không?
- Có object con hoặc collection lồng nhau bị sửa tại chỗ không?
- Có hai request đồng thời cùng cập nhật thuộc tính không?
- Dữ liệu có cần atomicity hoặc optimistic locking không?
- Có nên lưu dữ liệu nghiệp vụ ở database thay vì session không?
- Các instance có cùng serializer và write policy không?
- Integration test có xác minh giá trị sau khi tải lại từ repository không?
- Log và metric có tránh chứa session ID, cookie và dữ liệu nhạy cảm không?

## 19. Quy tắc thực hành

Với thuộc tính session, hãy áp dụng các quy tắc sau:

1. Coi mỗi thuộc tính là một đơn vị lưu trữ, không giả định repository theo dõi mọi field bên trong object.
2. Ưu tiên object bất biến và thay thế thuộc tính bằng setAttribute.
3. Nếu phải sửa object mutable tại chỗ, hiểu SaveMode và kiểm thử đúng request wrapper/repository.
4. Dùng ON_SET_ATTRIBUTE khi ứng dụng có thể đặt lại thuộc tính sau mỗi thay đổi.
5. Chỉ cân nhắc ON_GET_ATTRIBUTE hoặc ALWAYS sau khi đo tải và xác định rõ trade-off.
6. Không coi FlushMode là cơ chế phát hiện thay đổi; nó chỉ điều khiển thời điểm flush.
7. Không dùng session làm nơi lưu dữ liệu nghiệp vụ cần transaction hoặc không được mất cập nhật.
8. Kiểm thử hai request và nhiều instance cùng sửa một thuộc tính.
9. Đồng bộ serializer, SaveMode, FlushMode và phiên bản giữa mọi node.
10. Đưa trạng thái quan trọng vào kho dữ liệu có cơ chế concurrency phù hợp.

Spring Session có thể theo dõi thao tác trên thuộc tính session, nhưng không tự động theo dõi sâu mọi thay đổi của object khả biến. SaveMode xác định tập thuộc tính được lưu; FlushMode xác định thời điểm ghi. Khi ứng dụng sửa collection hoặc field lồng nhau mà không đặt lại thuộc tính, thay đổi có thể không được lưu với chính sách phù hợp. Hãy ưu tiên object bất biến, thay thế thuộc tính tường minh và kiểm thử bằng repository thật. Với dữ liệu cần nhất quán mạnh giữa request hoặc nhiều instance, dùng transaction, version/CAS hoặc kho dữ liệu nghiệp vụ chuyên dụng thay vì kỳ vọng session repository tự merge các object mutable.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session — SaveMode API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SaveMode.html)
- [Spring Session — FlushMode API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FlushMode.html)
- [Spring Session — Session API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/Session.html)

